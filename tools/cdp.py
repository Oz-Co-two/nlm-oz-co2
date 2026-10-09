"""ヘッドレスEdgeでエディタを実際に動かして検証するツール（Node/追加ライブラリ不要）。

Chrome DevTools Protocol(CDP)を標準ライブラリだけの最小WebSocketで話す。できること:
  - 画面のスクリーンショット（WebGLの3Dビューも写る。ソフトウェア描画）
  - 本物のマウス/キーボード入力（クリック・ドラッグ・ホイール・Ctrl+Z等。合成イベントではなくブラウザ入力として届く）
  - ページ内JSの実行と結果取得、コンソール/例外ログの回収
  - テスト素材(tools/fixtures/)の読込（ファイル選択ダイアログを経由しない）

ページは editor.html?dev=1 で開くので、開発用窓口（window._dbg / window._dbgApp）が有効になる。
設定の書き込みは一時フォルダ（NLM_DATA_DIR）へ向けるので、手元の config/settings.json は汚さない。
exe版固有の動き（pywebviewの×ボタン確認・ネイティブのファイル選択）はブラウザでは再現できない。

■ コマンドラインから（.venv-build のPythonで実行）
  python tools/cdp.py shot out.png                     起動直後の画面を撮る
  python tools/cdp.py shot out.png --fixture basic     テスト素材を読み込んでから撮る
  python tools/cdp.py shot out.png --clip 0,560,1600,420   範囲を切り出して撮る(x,y,幅,高さ)
  python tools/cdp.py eval "window._dbgApp.state()"    JSの結果をJSONで表示
  オプション: --size 1600x980 / --wait 秒（起動待ち・既定6）/ --js "撮る前に実行するJS"

■ Pythonから（検証スクリプトを書くとき）
  import sys; sys.path.insert(0, 'tools'); from cdp import Editor
  with Editor(fixture='basic') as ed:
      p = ed.js("window._dbgApp.cellScreen(1,0)")   # マスの画面座標
      ed.click(p['x'], p['y']); ed.wait(0.5)
      ed.key('z', ctrl=True)                          # Ctrl+Z
      ed.shot('after.png')
      print(ed.js("window._dbgApp.state()"), ed.errors())
"""
import base64
import http.server
import json
import os
import shutil
import socket
import struct
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from pathlib import Path

if sys.platform == "win32":
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8")
        except Exception:
            pass

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = Path(__file__).resolve().parent / "fixtures"
EDGE_CANDIDATES = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    "/usr/bin/microsoft-edge", "/usr/bin/google-chrome", "/usr/bin/chromium",
]


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class CdpError(RuntimeError):
    pass


def _allow_static_cache(serve):
    """テスト中だけ、静的ファイル（js/css/json/画像）をブラウザにキャッシュさせる（serve.py は開発時のために常にキャッシュ無効）。
    テストはページを何百回も開き直すので、毎回の読み込み・コンパイルし直しが大きい（開き直し 1.4秒→1.1秒）。
    Edge のプロファイルは起動ごとに新しい一時フォルダ＝前回の実行の古いファイルが残ることは無い"""
    H = serve.NoCacheHandler
    if getattr(H, "_nlm_test_cache", False):
        return
    base = H.end_headers

    def end_headers(self):
        p = self.path.split("?", 1)[0]
        if self.command == "GET" and not p.startswith("/__") and p.endswith((".js", ".css", ".json", ".png", ".svg", ".jpg", ".woff2")):
            self.send_header("Cache-Control", "max-age=3600")
            http.server.SimpleHTTPRequestHandler.end_headers(self)
        else:
            base(self)
    H.end_headers = end_headers
    H._nlm_test_cache = True


class _WebSocket:
    """CDP用の最小WebSocketクライアント（テキストフレームのみ・クライアント側マスク付き）"""

    def __init__(self, url):
        rest = url.split("://", 1)[1]
        hostport, path = rest.split("/", 1)
        host, port = hostport.rsplit(":", 1)
        self.sock = socket.create_connection((host, int(port)), timeout=60)
        key = base64.b64encode(os.urandom(16)).decode()
        self.sock.sendall((f"GET /{path} HTTP/1.1\r\nHost: {hostport}\r\nUpgrade: websocket\r\n"
                           f"Connection: Upgrade\r\nSec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n").encode())
        buf = b""
        while b"\r\n\r\n" not in buf:
            chunk = self.sock.recv(4096)
            if not chunk:
                raise CdpError("WebSocketの接続に失敗しました")
            buf += chunk
        if b" 101 " not in buf.split(b"\r\n", 1)[0]:
            raise CdpError("WebSocketのハンドシェイクに失敗しました: " + buf.split(b"\r\n", 1)[0].decode(errors="replace"))
        self.buf = buf.split(b"\r\n\r\n", 1)[1]

    def _recvn(self, n):
        while len(self.buf) < n:
            chunk = self.sock.recv(1 << 20)
            if not chunk:
                raise CdpError("ブラウザとの接続が切れました")
            self.buf += chunk
        data, self.buf = self.buf[:n], self.buf[n:]
        return data

    def send(self, obj):
        data = json.dumps(obj).encode()
        mask = os.urandom(4)
        n = len(data)
        head = bytes([0x81])
        if n < 126:
            head += bytes([0x80 | n])
        elif n < 65536:
            head += bytes([0x80 | 126]) + struct.pack(">H", n)
        else:
            head += bytes([0x80 | 127]) + struct.pack(">Q", n)
        self.sock.sendall(head + mask + bytes(b ^ mask[i % 4] for i, b in enumerate(data)))

    def recv(self):
        """1メッセージ受信（継続フレームも連結）。テキスト以外(ping等)は None"""
        payload, opcode = b"", None
        while True:
            b1, b2 = self._recvn(2)
            n = b2 & 0x7F
            if n == 126:
                n = struct.unpack(">H", self._recvn(2))[0]
            elif n == 127:
                n = struct.unpack(">Q", self._recvn(8))[0]
            if opcode is None:
                opcode = b1 & 0x0F
            payload += self._recvn(n)
            if b1 & 0x80:
                break
        return json.loads(payload) if opcode == 1 else None

    def close(self):
        try:
            self.sock.close()
        except Exception:
            pass


class Editor:
    """serve.py + ヘッドレスEdgeでエディタを開いて操作する。with文で使う（終了時に後始末）"""

    def __init__(self, width=1600, height=980, wait=6.0, fixture=None, keep_data=False, ready=False, auto_dialog=True):
        """ready=True: 固定のwait秒ではなく起動完了を検知して進む（テスト用）。auto_dialog: ページのダイアログを自動で承諾"""
        self.width, self.height, self.wait_s, self.fixture = width, height, wait, fixture
        self.keep_data, self.ready, self.auto_dialog = keep_data, ready, auto_dialog
        self._id = 0
        self._events = []   # 受信したCDPイベント（コンソール/例外）
        self.edge = self.httpd = self.ws = None

    # ---- 起動・終了 ----
    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *exc):
        self.close()

    def start(self):
        edge = next((p for p in EDGE_CANDIDATES if Path(p).exists()), None)
        if not edge:
            raise CdpError("Microsoft Edge（またはChrome/Chromium）が見つかりません")
        # 設定の書き込み先を一時フォルダへ（手元の config/settings.json を汚さない）。serve は import 時に環境変数を読む
        self.data_dir = tempfile.mkdtemp(prefix="nlm_cdp_data_")
        os.environ["NLM_DATA_DIR"] = self.data_dir
        sys.path.insert(0, str(ROOT))
        if "serve" in sys.modules:
            del sys.modules["serve"]
        import serve
        _allow_static_cache(serve)
        self.port = _free_port()
        self.httpd = serve.make_server(port=self.port)
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        dport = self.dport = _free_port()
        self.profile = tempfile.mkdtemp(prefix="nlm_cdp_edge_")
        self.edge = subprocess.Popen([
            edge, "--headless=new", f"--user-data-dir={self.profile}", f"--remote-debugging-port={dport}",
            f"--window-size={self.width},{self.height}", "--hide-scrollbars", "--mute-audio",
            "--use-angle=swiftshader", "--enable-unsafe-swiftshader",   # GPU無しでもWebGL(3Dビュー)を描く
            "--autoplay-policy=no-user-gesture-required",
            # ヘッドレスはバックグラウンド扱いで requestAnimationFrame（=エディタの描画ループ）が止まることがある＝抑制を切る
            "--disable-renderer-backgrounding", "--disable-background-timer-throttling",
            "--disable-backgrounding-occluded-windows",
            # 新しいプロファイルだと起動の数秒後に edge://sync-confirmation-dialog/（同期の確認）が勝手に開き、
            # その時にエディタのページとの接続が切れる（タイミング次第で起きる＝テストがたまに全滅する）。同期・初回の案内・拡張機能を止める
            "--no-first-run", "--no-default-browser-check", "--disable-sync", "--disable-extensions",
            "--disable-component-extensions-with-background-pages", "--disable-default-apps",
            "--disable-features=msEdgeSyncConsent,msImplicitSignin,msSignInPromo,EdgeSignIn,Translate",
            "about:blank",
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        tabs = None
        for _ in range(100):
            try:
                tabs = json.loads(urllib.request.urlopen(f"http://127.0.0.1:{dport}/json", timeout=2).read())
                if any(t.get("type") == "page" for t in tabs):
                    break
            except Exception:
                pass
            time.sleep(0.2)
        page = next((t for t in (tabs or []) if t.get("type") == "page"), None)
        if not page:
            raise CdpError("Edgeのデバッグ接続に失敗しました")
        self.ws = _WebSocket(page["webSocketDebuggerUrl"])
        self.call("Runtime.enable")
        self.call("Page.enable")
        self.call("Log.enable")   # 通信の失敗（Failed to load resource）等も受け取る。errors() には入れない＝診断用（tests/visual の例外の記録）
        self.call("Emulation.setDeviceMetricsOverride", width=self.width, height=self.height, deviceScaleFactor=1, mobile=False)
        self.call("Emulation.setFocusEmulationEnabled", enabled=True)   # 常に前面・フォーカス中として扱う（描画ループを止めない）
        self.call("Page.bringToFront")
        self.call("Page.navigate", url=self.url())
        if self.ready:
            self.wait_ready()
        else:
            self.wait(self.wait_s)
        if self.fixture:
            self.load_fixture(self.fixture)

    def url(self):
        return f"http://127.0.0.1:{self.port}/editor.html?dev=1"

    def wait_ready(self, timeout=30.0, settle=0.15):
        """起動完了（開発用窓口ができ、描画ループが回り始めた）まで待つ。固定秒数の待ちより速く、遅いPCでも取りこぼさない"""
        end = time.time() + timeout
        while time.time() < end:
            try:
                # booted: 起動処理の非同期の続き（アイコン読込の後の配置モードへの切替など）まで終わったか。古い版には無いので無ければ待たない
                if self.js("document.readyState==='complete'&&!!window._dbgApp&&!!(window._dbg&&window._dbg.rt)"
                           "&&(!window._dbgApp.booted||window._dbgApp.booted())"):
                    self.wait(settle)
                    return
            except CdpError:
                pass   # 読み込み途中で実行コンテキストが入れ替わった
            time.sleep(0.1)
        raise CdpError(f"エディタの起動が {timeout} 秒以内に終わりませんでした")

    def reload(self, fixture=None, clear_storage=True):
        """ページを開き直して初期状態に戻す（Edgeは起動したまま＝テストごとの起動待ちを省く）。
        未保存の変更があっても確認ダイアログは自動で承諾する。clear_storage=True で localStorage も消す"""
        if clear_storage:
            try:
                self.js("localStorage.clear();sessionStorage.clear();true")
            except CdpError:
                pass
        self.call("Page.navigate", url=self.url())
        self.wait_ready()
        self._events.clear()
        if fixture:
            self.load_fixture(fixture)

    def close(self):
        if self.ws:
            self.ws.close()
        if self.edge:
            self.edge.kill()
            try:
                self.edge.wait(5)
            except Exception:
                pass
        if self.httpd:
            self.httpd.shutdown()
        for d in (getattr(self, "profile", None), None if self.keep_data else getattr(self, "data_dir", None)):
            if d:
                shutil.rmtree(d, ignore_errors=True)

    def new_tab(self, path="tests/visual/blank.html"):
        """同じEdgeに別のタブを開いて Tab を返す（ページと同じサーバーの path を開く＝同じオリジンで fetch できる）。
        画像の比較など重い処理を、描画ループの回るエディタのページと分けて行うために使う"""
        # 裏で開き、エディタを前面に戻す。エディタのタブが裏に回ると描画ループ（requestAnimationFrame）が止まり、
        # 撮影がフレーム待ちで毎回3.5秒ほどかかる・入力が遅れる
        tid = self.call("Target.createTarget", url=f"http://127.0.0.1:{self.port}/{path}", background=True)["targetId"]
        self.call("Page.bringToFront")
        for _ in range(50):
            tabs = json.loads(urllib.request.urlopen(f"http://127.0.0.1:{self.dport}/json", timeout=2).read())
            t = next((t for t in tabs if t.get("id") == tid and t.get("webSocketDebuggerUrl")), None)
            if t:
                tab = Tab(self, tid, _WebSocket(t["webSocketDebuggerUrl"]))
                # 開いた直後のタブは、目的のページへ移る前に一瞬 about:blank（これも readyState は complete）になる。
                # そこで返すと、入れたJSが直後のページ移動で消える・相対URLが使えない（PCが混んでいる時に画面テストが46件まとめて落ちた。
                # tests/README.md「たまに出るエラーの記録」）。目的のページに移ったことも確かめる
                for _ in range(200):
                    if tab.js("location.protocol.startsWith('http')&&document.readyState==='complete'"):
                        return tab
                    time.sleep(0.05)
                raise CdpError(f"補助タブが {path} を開けませんでした（10秒）")
            time.sleep(0.1)
        raise CdpError("タブを開けませんでした")

    # ---- CDP基本 ----
    def call(self, method, **params):
        self._id += 1
        my = self._id
        self.ws.send({"id": my, "method": method, "params": params})
        while True:
            msg = self.ws.recv()
            if msg is None:
                continue
            if msg.get("id") == my:
                if "error" in msg:
                    raise CdpError(f"{method}: {msg['error']}")
                return msg.get("result", {})
            if "method" in msg:
                self._events.append(msg)
                if msg["method"] == "Page.javascriptDialogOpening" and self.auto_dialog:
                    # alert/confirm/beforeunload を自動で承諾（開いたままだとページが止まりテストが固まる）。応答は待たない
                    self._id += 1
                    self.ws.send({"id": self._id, "method": "Page.handleJavaScriptDialog", "params": {"accept": True}})

    def js(self, expr, await_promise=True):
        """ページ内でJSを実行し、結果（JSON化できる値）を返す。例外はCdpErrorで送出"""
        r = self.call("Runtime.evaluate", expression=expr, awaitPromise=await_promise, returnByValue=True)
        if "exceptionDetails" in r:
            d = r["exceptionDetails"]
            raise CdpError("JS例外: " + (d.get("exception", {}).get("description") or d.get("text", "")))
        return r.get("result", {}).get("value")

    def wait(self, seconds):
        """待つ（その間に届いたコンソール/例外イベントも回収する）"""
        end = time.time() + seconds
        while time.time() < end:
            self.js("0")   # 往復でイベントを取り込む
            time.sleep(min(0.2, max(0, end - time.time())))

    def frames(self, ms=500):
        """ms ミリ秒の間に描画フレーム(requestAnimationFrame)が何回来たか。0なら描画ループが止まっている"""
        return self.js(f"new Promise(r=>{{let n=0;const f=()=>{{n++;requestAnimationFrame(f)}};requestAnimationFrame(f);setTimeout(()=>r(n),{ms})}})")

    def errors(self):
        """これまでに出たページ内の例外・console.error を文字列のリストで返す"""
        out = []
        for e in self._events:
            m, p = e.get("method"), e.get("params", {})
            if m == "Runtime.exceptionThrown":
                d = p.get("exceptionDetails", {})
                out.append("例外: " + (d.get("exception", {}).get("description") or d.get("text", "")))
            elif m == "Runtime.consoleAPICalled" and p.get("type") in ("error", "assert"):
                out.append("console.error: " + " ".join(str(a.get("value", a.get("description", ""))) for a in p.get("args", [])))
        return out

    # ---- 撮影 ----
    def shot(self, path, clip=None):
        """スクリーンショットをPNGで保存。clip=(x,y,幅,高さ) で範囲指定"""
        params = {"format": "png"}
        if clip:
            x, y, w, h = clip
            params["clip"] = {"x": x, "y": y, "width": w, "height": h, "scale": 1}
        data = self.call("Page.captureScreenshot", **params)["data"]
        Path(path).write_bytes(base64.b64decode(data))
        return str(path)

    # ---- 入力（ブラウザの本物の入力として届く） ----
    def _mods(self, ctrl=False, shift=False, alt=False):
        return (2 if ctrl else 0) | (8 if shift else 0) | (1 if alt else 0)

    def move(self, x, y, buttons=0, **mods):
        self.call("Input.dispatchMouseEvent", type="mouseMoved", x=x, y=y, buttons=buttons, modifiers=self._mods(**mods))

    def click(self, x, y, button="left", count=1, **mods):
        m = self._mods(**mods)
        bmask = {"left": 1, "right": 2, "middle": 4}[button]
        self.move(x, y, **mods)
        self.call("Input.dispatchMouseEvent", type="mousePressed", x=x, y=y, button=button, buttons=bmask, clickCount=count, modifiers=m)
        self.call("Input.dispatchMouseEvent", type="mouseReleased", x=x, y=y, button=button, buttons=0, clickCount=count, modifiers=m)

    def drag(self, x0, y0, x1, y1, steps=12, button="left", **mods):
        m = self._mods(**mods)
        bmask = {"left": 1, "right": 2, "middle": 4}[button]
        self.move(x0, y0, **mods)
        self.call("Input.dispatchMouseEvent", type="mousePressed", x=x0, y=y0, button=button, buttons=bmask, clickCount=1, modifiers=m)
        for i in range(1, steps + 1):
            t = i / steps
            self.call("Input.dispatchMouseEvent", type="mouseMoved", x=x0 + (x1 - x0) * t, y=y0 + (y1 - y0) * t,
                      button=button, buttons=bmask, modifiers=m)
        self.call("Input.dispatchMouseEvent", type="mouseReleased", x=x1, y=y1, button=button, buttons=0, clickCount=1, modifiers=m)

    def wheel(self, x, y, dy, dx=0, **mods):
        self.call("Input.dispatchMouseEvent", type="mouseWheel", x=x, y=y, deltaX=dx, deltaY=dy, modifiers=self._mods(**mods))

    _KEYS = {  # key → (code, windowsVirtualKeyCode)
        "Enter": ("Enter", 13), "Escape": ("Escape", 27), "Tab": ("Tab", 9), " ": ("Space", 32),
        "Backspace": ("Backspace", 8), "Delete": ("Delete", 46),
        "ArrowLeft": ("ArrowLeft", 37), "ArrowUp": ("ArrowUp", 38), "ArrowRight": ("ArrowRight", 39), "ArrowDown": ("ArrowDown", 40),
        ",": ("Comma", 188), ".": ("Period", 190), "[": ("BracketLeft", 219), "]": ("BracketRight", 221),
    }

    def key(self, key, ctrl=False, shift=False, alt=False):
        """1キー押して離す。key は 'z' / 'Enter' / 'ArrowLeft' / ' ' など（KeyboardEvent.key と同じ表記）"""
        m = self._mods(ctrl, shift, alt)
        if len(key) == 1 and key.isalnum():
            code = ("Key" + key.upper()) if key.isalpha() else ("Digit" + key)
            vk = ord(key.upper())
            text = "" if (ctrl or alt) else (key.upper() if shift else key)
        else:
            code, vk = self._KEYS.get(key, (key, 0))
            text = key if (len(key) == 1 and not (ctrl or alt)) else ""
        base = dict(key=key, code=code, windowsVirtualKeyCode=vk, nativeVirtualKeyCode=vk, modifiers=m)
        self.call("Input.dispatchKeyEvent", type="keyDown" if text else "rawKeyDown", text=text, **base)
        self.call("Input.dispatchKeyEvent", type="keyUp", **base)

    # ---- テスト素材 ----
    # 音源を他の素材と使い回すテスト素材（素材名 → 使う .wav の名前）。無ければ同名の .wav
    FIXTURE_WAV = {"rich": "basic"}

    def load_fixture(self, name, wav=None, settle=1.5):
        """tools/fixtures/<name>.nlmf を開き、同名（または FIXTURE_WAV / wav 引数で指定）の .wav があれば音源として読み込む
        （ダイアログ無し・未保存扱いにしない）。settle=読込後に描画等が落ち着くまで待つ秒数（状態を待ち合わせるテストは短くてよい）"""
        proj = FIXTURES / f"{name}.nlmf"
        if not proj.exists():
            raise CdpError(f"テスト素材が見つかりません: {proj}")
        url = f"tools/fixtures/{name}"
        wname = wav or self.FIXTURE_WAV.get(name, name)
        wav = (FIXTURES / f"{wname}.wav").exists()
        self.js(f"""(async()=>{{
          const rt=window._dbg.rt;
          const pj=await (await fetch('{url}.nlmf',{{cache:'no-store'}})).json();
          await rt.applyProject(pj);
          if({str(wav).lower()}){{
            const blob=await (await fetch('tools/fixtures/{wname}.wav',{{cache:'no-store'}})).blob();
            const file=new File([blob],'{wname}.wav',{{type:'audio/wav'}});
            await rt.loadSongFromItem({{isMusic:true,name:'{name}',songFh:{{getFile:async()=>file}},info:{{_beatsPerMinute:pj.bpm}}}},pj.musicBeat||0);
          }}
          return true; }})()""")
        self.wait(settle)


class Tab:
    """Editor.new_tab() が開く補助のタブ。js() で JS を実行できる（入力・撮影は持たない）"""

    def __init__(self, editor, target_id, ws):
        self.editor, self.target_id, self.ws, self._id = editor, target_id, ws, 0

    def call(self, method, **params):
        self._id += 1
        my = self._id
        self.ws.send({"id": my, "method": method, "params": params})
        while True:
            msg = self.ws.recv()
            if msg is not None and msg.get("id") == my:
                if "error" in msg:
                    raise CdpError(f"{method}: {msg['error']}")
                return msg.get("result", {})

    def js(self, expr, await_promise=True):
        r = self.call("Runtime.evaluate", expression=expr, awaitPromise=await_promise, returnByValue=True)
        if "exceptionDetails" in r:
            d = r["exceptionDetails"]
            raise CdpError("JS例外: " + (d.get("exception", {}).get("description") or d.get("text", "")))
        return r.get("result", {}).get("value")

    def close(self):
        try:
            self.editor.call("Target.closeTarget", targetId=self.target_id)
        except Exception:
            pass
        self.ws.close()


def _main(argv):
    import argparse
    ap = argparse.ArgumentParser(description="ヘッドレスEdgeでエディタを開いて撮影/JS実行")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("shot", "eval"):
        p = sub.add_parser(name)
        p.add_argument("target", help="shot=保存先PNG / eval=実行するJS式")
        p.add_argument("--fixture", help="読み込むテスト素材名（tools/fixtures/<名前>.nlmf）")
        p.add_argument("--size", default="1600x980")
        p.add_argument("--wait", type=float, default=6.0, help="起動後の待ち秒数")
        p.add_argument("--js", help="撮影/評価の前に実行するJS")
        p.add_argument("--clip", help="撮影範囲 x,y,幅,高さ")
    a = ap.parse_args(argv)
    w, h = (int(v) for v in a.size.lower().split("x"))
    with Editor(width=w, height=h, wait=a.wait, fixture=a.fixture) as ed:
        if a.js:
            ed.js(a.js)
            ed.wait(0.8)
        if a.cmd == "shot":
            clip = tuple(float(v) for v in a.clip.split(",")) if a.clip else None
            print("保存しました:", ed.shot(a.target, clip))
        else:
            print(json.dumps(ed.js(a.target), ensure_ascii=False, indent=1))
        errs = ed.errors()
        if errs:
            print("※ページ内エラー:", *errs, sep="\n  ")
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))

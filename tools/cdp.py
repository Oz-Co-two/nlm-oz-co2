"""ヘッドレスEdgeでエディタを実際に動かして検証するツール（Node/追加ライブラリ不要）。

Chrome DevTools Protocol(CDP)を標準ライブラリだけで、起動したEdgeとのパイプ（--remote-debugging-pipe）越しに話す。
TCPのデバッグポートは開かない（認証が無く、同じPCの別のユーザーからも繋いでブラウザを操作できてしまうため）。できること:
  - 画面のスクリーンショット（WebGLの3Dビューも写る。GPUで描画し、GPUが無いPCではソフトウェア描画。_gl_args()）
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
import collections
import http.server
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
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


def _gl_args():
    """描画の方式。既定はGPU（ヘッドレスでも使える）。以前はソフトウェア描画（SwiftShader）を指定していたが、
    エディタは毎フレーム画面を描き直すので、何もしていない時でも Edge 1つで約14コア分のCPUを使い、テストを並列に回すとCPUを使い切っていた
    （GPUでは約1コア分・開き直し 1.5秒→0.9秒。2026-10-11に測定）。
    --enable-unsafe-swiftshader は、GPUが無い・使えないPCで WebGL をソフトウェア描画へ戻すために残す。
    環境変数 NLM_TEST_SOFTWARE_GL=1 で従来のソフトウェア描画に固定する（GPUのせいか切り分ける時）"""
    if os.environ.get("NLM_TEST_SOFTWARE_GL") == "1":
        return ["--use-angle=swiftshader", "--enable-unsafe-swiftshader"]
    return ["--enable-unsafe-swiftshader"]


def _fps_cap_js(fps):
    """ページの requestAnimationFrame を毎秒 fps 回までにする（ページのJSより先に入れる）。GPU描画ではモニターのリフレッシュレート
    （このPCでは144回）で回り、エディタは毎フレーム描き直すので、何もしていなくても Edge 1つで約1.5コア分のCPUを使っていた
    （8つ同時で: 上限なし 約50%・30回 約12%。2026-10-11に測定）。同じフレームに頼まれた分はまとめて同じ時刻で呼ぶ（本来と同じ）"""
    return """(()=>{ const raf=window.requestAnimationFrame.bind(window), gap=1000/%d-2;
  let q=new Map(), id=0, asked=false, last=-Infinity;
  const pump=t=>{ if(t-last<gap){ raf(pump); return; } last=t; asked=false; const cbs=q; q=new Map();
    for(const cb of cbs.values()){ try{ cb(t); }catch(e){ reportError(e); } } };
  window.requestAnimationFrame=cb=>{ q.set(++id,cb); if(!asked){ asked=true; raf(pump); } return id; };
  window.cancelAnimationFrame=n=>{ q.delete(n); }; })()""" % fps


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


class _Pipe:
    """Edge との CDP のパイプ（--remote-debugging-pipe）。メッセージは JSON を \\0 で区切って送り合う。
    1本のパイプをブラウザ自身（sessionId 無し）と各タブのセッション（Target.attachToTarget の flatten）で共有するので、
    受信は専用のスレッドで読み、sessionId ごとの箱に振り分ける"""
    TIMEOUT = 60   # 何も届かないまま待つ上限（秒）。以前の WebSocket の受信待ち（ソケットのタイムアウト）と同じ

    def __init__(self, rfd, wfd):
        self.wfd = wfd
        # ブラウザ自身へ送る命令の番号。タブ側の番号（Editor._id / Tab._id）と重ならない範囲にする
        # （閉じたばかりのタブへ送った命令のエラーは sessionId 無し＝ブラウザ宛てとして返ってくるため）
        self._bid = 1 << 30
        self._cv = threading.Condition()
        self._wlock = threading.Lock()
        self._boxes = {}      # sessionId（ブラウザ自身は None）→ 届いたメッセージの列
        self._gone = set()    # 切り離された（タブが閉じた・こちらで閉じた）セッション
        self._eof = False     # パイプが閉じた＝Edge が終了した
        threading.Thread(target=self._read_loop, args=(rfd,), daemon=True).start()

    def _read_loop(self, rfd):
        buf = bytearray()
        try:
            while True:
                chunk = os.read(rfd, 1 << 20)
                if not chunk:
                    break
                start = len(buf)
                buf += chunk
                i = buf.find(b"\0", start)
                while i >= 0:
                    self._dispatch(json.loads(buf[:i]))
                    del buf[:i + 1]
                    i = buf.find(b"\0")
        except Exception:
            pass
        finally:
            with self._cv:
                self._eof = True
                self._cv.notify_all()
            # 読む側はこのスレッドが閉じる（Windows では読んでいる最中の fd を別のスレッドから閉じると、読み終わるまで止まる）
            try:
                os.close(rfd)
            except OSError:
                pass

    def _dispatch(self, msg):
        sid = msg.pop("sessionId", None)   # 受け取る側には以前の WebSocket と同じ形（sessionId 無し）で渡す
        with self._cv:
            if sid is None and "id" not in msg:
                # ブラウザ自身へのイベント。使うのはタブが閉じた知らせだけ（以前はタブの WebSocket が切れて
                # すぐ「接続が切れました」になった。知らせを捨てると、閉じたタブへの命令が応答を待って60秒止まる）
                if msg.get("method") != "Target.detachedFromTarget":
                    return
                self._gone.add(msg.get("params", {}).get("sessionId"))
            elif sid not in self._gone:
                self._boxes.setdefault(sid, collections.deque()).append(msg)
            self._cv.notify_all()

    def send(self, sid, obj):
        if sid is not None:
            obj = {**obj, "sessionId": sid}
        data = memoryview(json.dumps(obj).encode() + b"\0")
        with self._cv:
            if self._eof or sid in self._gone:
                raise CdpError("ブラウザとの接続が切れました")
        with self._wlock:
            try:
                if self.wfd is None:
                    raise OSError("closed")
                while data:
                    data = data[os.write(self.wfd, data):]
            except OSError:
                raise CdpError("ブラウザとの接続が切れました") from None

    def recv(self, sid, timeout=None):
        """sid 宛ての次のメッセージ。セッションが切り離された・Edge が終了した時は（届いていた分を渡し終えた後）CdpError"""
        end = time.monotonic() + (self.TIMEOUT if timeout is None else timeout)
        with self._cv:
            while True:
                box = self._boxes.get(sid)
                if box:
                    return box.popleft()
                if self._eof or sid in self._gone:
                    raise CdpError("ブラウザとの接続が切れました")
                left = end - time.monotonic()
                if left <= 0:
                    raise TimeoutError("timed out")   # 以前（ソケットの受信待ち）と同じ例外
                self._cv.wait(left)

    def call(self, method, timeout=None, **params):
        """ブラウザ自身へ命令を送り、結果を返す（タブ宛ての命令は Editor.call / Tab.call）"""
        self._bid += 1
        my = self._bid
        self.send(None, {"id": my, "method": method, "params": params})
        while True:
            msg = self.recv(None, timeout)
            if msg.get("id") == my:
                if "error" in msg:
                    raise CdpError(f"{method}: {msg['error']}")
                return msg.get("result", {})

    def attach(self, target_id):
        """タブにセッションを張って返す"""
        return _PipeSession(self, self.call("Target.attachToTarget", targetId=target_id, flatten=True)["sessionId"])

    def forget(self, sid):
        with self._cv:
            self._gone.add(sid)
            self._boxes.pop(sid, None)
            self._cv.notify_all()

    def close(self):
        """書く側を閉じる（読む側は、Edge が終了してパイプが閉じた時に読み取りのスレッドが閉じる）"""
        with self._wlock:
            if self.wfd is not None:
                try:
                    os.close(self.wfd)
                except OSError:
                    pass
                self.wfd = None


class _PipeSession:
    """パイプ越しの1つのタブとのセッション。以前の WebSocket と同じ send / recv / close を持つ"""

    def __init__(self, pipe, sid):
        self.pipe, self.sid = pipe, sid

    def send(self, obj):
        self.pipe.send(self.sid, obj)

    def recv(self):
        return self.pipe.recv(self.sid)

    def close(self):
        self.pipe.forget(self.sid)


def _launch_with_pipe(args):
    """Edge（args[0]）を CDP のパイプ付きで起動し、(プロセス, _Pipe) を返す。
    Windows は渡すハンドルの番号を --remote-debugging-io-pipes で伝え（子にはその2つだけを継承させる）、
    それ以外は Chromium の決まりどおり fd 3（ブラウザが読む）/ fd 4（ブラウザが書く）に付け替えて渡す"""
    to_r, to_w = os.pipe()       # こちら → Edge
    from_r, from_w = os.pipe()   # Edge → こちら
    try:
        if sys.platform == "win32":
            import msvcrt
            hr, hw = msvcrt.get_osfhandle(to_r), msvcrt.get_osfhandle(from_w)
            os.set_handle_inheritable(hr, True)
            os.set_handle_inheritable(hw, True)
            si = subprocess.STARTUPINFO(lpAttributeList={"handle_list": [hr, hw]})
            proc = subprocess.Popen([args[0], f"--remote-debugging-io-pipes={hr},{hw}", *args[1:]], startupinfo=si,
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            proc = subprocess.Popen(["/bin/sh", "-c", 'exec "$@" 3<&0 4>&1 </dev/null >/dev/null', "sh", *args],
                                    stdin=to_r, stdout=from_w, stderr=subprocess.DEVNULL)
    except BaseException:
        os.close(to_w)
        os.close(from_r)
        raise
    finally:
        os.close(to_r)     # 子へ渡した側はこちらでは閉じる（Edge が終了した時に読む側が終わりを受け取れるように）
        os.close(from_w)
    return proc, _Pipe(from_r, to_w)


class Editor:
    """serve.py + ヘッドレスEdgeでエディタを開いて操作する。with文で使う（終了時に後始末）"""

    # 検証・テスト・撮影の環境の既定の環境設定（初期値 config/settings.default.json の上に重ねて、一時のデータフォルダの config/settings.json に書く）。
    # bsnm_anaAsk='0': 曲を読み込むたびに出る「曲を解析しますか？」を出さない（多くのテスト・撮影が曲を読み込むため）。
    # その画面を確かめるテストは localStorage の bsnm_anaAsk を消して（キーが無い＝聞く）出す
    # bsnm_anaGuide='0': 解析が終わった時の「次にやること」の案内を出さない（多くのテスト・撮影が解析を走らせるため）。確かめる時は同じくキーを消す
    TEST_SETTINGS = {"bsnm_anaAsk": "0", "bsnm_anaGuide": "0"}

    def __init__(self, width=1600, height=980, wait=6.0, fixture=None, keep_data=False, ready=False, auto_dialog=True, max_fps=None):
        """ready=True: 固定のwait秒ではなく起動完了を検知して進む（テスト用）。auto_dialog: ページのダイアログを自動で承諾。
        max_fps: 描画ループ（requestAnimationFrame）を毎秒この回数までに抑える（テストを並列に回す時のCPU節約。_fps_cap_js）"""
        self.width, self.height, self.wait_s, self.fixture = width, height, wait, fixture
        self.keep_data, self.ready, self.auto_dialog, self.max_fps = keep_data, ready, auto_dialog, max_fps
        self._id = 0
        self._events = []   # 受信したCDPイベント（コンソール/例外）
        self.edge = self.httpd = self.ws = self.pipe = None

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
        # MEDIA ライブラリのプレイ記録の既定の場所も一時フォルダへ（利用者の本物の PlayerData.dat を読まない。テストはここに置いて使う）
        os.environ["NLM_PLAYDATA"] = os.path.join(self.data_dir, "PlayerData.dat")
        # ネットへ出ない（記録したライブラリを読むと画面が全曲データの取得を頼む＝毎回 jsDelivr から約10MB を取りに行かないように）。
        # 実際に取得して確かめる時だけ、先に NLM_NO_NET=0 を設定しておく
        os.environ.setdefault("NLM_NO_NET", "1")
        sys.path.insert(0, str(ROOT))
        if "serve" in sys.modules:
            del sys.modules["serve"]
        import serve
        _allow_static_cache(serve)
        self._serve = serve
        self.seed_settings()
        self.token = serve.SESSION_TOKEN   # 合言葉。ページへは URL の #k= で渡す（url()）。Python から直接要求する時は X-NLM-Token に付ける
        self.port = _free_port()
        self.httpd = serve.make_server(port=self.port)
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.profile = tempfile.mkdtemp(prefix="nlm_cdp_edge_")
        # CDP はパイプで話す。TCP のデバッグポート（--remote-debugging-port）は認証が無く、127.0.0.1 でも
        # 同じPCの別のユーザーから繋いで、このブラウザを開発者の権限で操作できてしまうため使わない
        self.edge, self.pipe = _launch_with_pipe([
            edge, "--headless=new", f"--user-data-dir={self.profile}", "--remote-debugging-pipe",
            f"--window-size={self.width},{self.height}", "--hide-scrollbars", "--mute-audio",
            *_gl_args(),
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
        ])
        page, end = None, time.time() + 20
        while not page and time.time() < end:
            try:
                tabs = self.pipe.call("Target.getTargets", timeout=max(0.1, end - time.time()))["targetInfos"]
            except (CdpError, TimeoutError):
                break   # Edge が終了した・パイプで応答しない
            page = next((t for t in tabs if t.get("type") == "page"), None)
            if not page:
                time.sleep(0.2)
        if not page:
            raise CdpError("Edgeのデバッグ接続に失敗しました")
        self.ws = self.pipe.attach(page["targetId"])   # 以前の WebSocket と同じ send / recv / close
        self.call("Runtime.enable")
        self.call("Page.enable")
        self.call("Log.enable")   # 通信の失敗（Failed to load resource）等も受け取る。errors() には入れない＝診断用（tests/visual の例外の記録）
        self.call("Emulation.setDeviceMetricsOverride", width=self.width, height=self.height, deviceScaleFactor=1, mobile=False)
        self.call("Emulation.setFocusEmulationEnabled", enabled=True)   # 常に前面・フォーカス中として扱う（描画ループを止めない）
        self.call("Page.bringToFront")
        if self.max_fps:   # このタブで開くページ全部（reload も）に、ページのJSより先に入る
            self.call("Page.addScriptToEvaluateOnNewDocument", source=_fps_cap_js(self.max_fps))
        self.call("Page.navigate", url=self.url())
        if self.ready:
            self.wait_ready()
        else:
            self.wait(self.wait_s)
        if self.fixture:
            self.load_fixture(self.fixture)

    def seed_settings(self):
        """一時のデータフォルダの config/settings.json を「初期値（config/settings.default.json）＋TEST_SETTINGS」にする（次にページを開いた時に読まれる）"""
        try:
            base = json.loads((ROOT / "config" / "settings.default.json").read_text(encoding="utf-8"))
        except Exception:
            base = {}
        base.update(self.TEST_SETTINGS)
        cfg = Path(self.data_dir) / "config"
        cfg.mkdir(parents=True, exist_ok=True)
        with self._serve._settings_lock:   # ページの保存（__settings/save）・配信と交互にする（書きかけを読ませない）
            self._serve._write_text_atomic(str(cfg / "settings.json"), json.dumps(base, ensure_ascii=False, indent=1))

    def url(self):
        # 合言葉は #k=。# 付きの同じ URL へ移ると「同じページ内の移動」になって読み込み直さないので、呼ぶたびに n を変える
        self._nav = getattr(self, "_nav", 0) + 1
        return f"http://127.0.0.1:{self.port}/editor.html?dev=1&n={self._nav}#k={self.token}"

    def wait_ready(self, timeout=30.0, settle=0.15):
        """起動完了（開発用窓口ができ、描画ループが回り始めた）まで待つ。固定秒数の待ちより速く、遅いPCでも取りこぼさない"""
        end = time.time() + timeout
        while time.time() < end:
            try:
                # booted: 起動処理の非同期の続き（アイコン読込の後の配置モードへの切替など）まで終わったか。古い版には無いので無ければ待たない。
                # bootCover: 起動中に画面を覆うカバー。booted の後、2フレーム待って大きさを測り直し（キャンバスが一度消える）、薄くして0.24秒後に
                # 取り除く。残っている間はクリックがカバーに当たる（GPU描画で起動が速くなり、開き直した直後のクリックが外れるテストが出た）
                if self.js("document.readyState==='complete'&&!!window._dbgApp&&!!(window._dbg&&window._dbg.rt)"
                           "&&(!window._dbgApp.booted||window._dbgApp.booted())&&!document.getElementById('bootCover')"):
                    self.wait(settle)
                    return
            except CdpError:
                pass   # 読み込み途中で実行コンテキストが入れ替わった
            time.sleep(0.1)
        raise CdpError(f"エディタの起動が {timeout} 秒以内に終わりませんでした\n{self._boot_diag()}")

    def _boot_diag(self):
        """起動待ちの時間切れの時に、どこで止まっていたかの手がかり（tests/README.md「たまに出るエラーの記録」用）"""
        out = []
        try:
            st = self.call("Runtime.evaluate", returnByValue=True, expression=(
                "(()=>{const a=window._dbgApp;let b=null;try{b=a&&a.booted?a.booted():null}catch(e){b=String(e)}"
                "return {href:location.href,ready:document.readyState,dbgApp:!!a,rt:!!(window._dbg&&window._dbg.rt),"
                "booted:b,bootCover:!!document.getElementById('bootCover'),hidden:document.hidden}})()"))
            out.append(f"ページの状態: {json.dumps(st.get('result', {}).get('value'), ensure_ascii=False)}")
        except Exception as e:
            out.append(f"ページの状態: 取れない（{e}）")
        try:
            out.append(f"描画フレーム（0.5秒間）: {self.frames()}")
        except Exception as e:
            out.append(f"描画フレーム: 取れない（{e}）")
        notable = ("Inspector.targetCrashed", "Inspector.detached", "Target.targetCrashed",
                   "Runtime.executionContextDestroyed", "Page.javascriptDialogOpening")
        for e in self._events:
            m, p = e.get("method", ""), e.get("params", {})
            if m == "Log.entryAdded" and p.get("entry", {}).get("level") in ("error", "warning"):
                en = p["entry"]
                out.append(f"ログ: {en.get('level')} [{en.get('source')}] {en.get('text', '')} {en.get('url', '')}".rstrip())
            elif m in notable:
                out.append(f"出来事: {m} {p.get('reason') or p.get('message') or ''}".rstrip())
        out += self.errors()
        return "\n".join(out[:40])

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
        if self.pipe:
            self.pipe.close()
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
        # 補助タブのページはアプリのJS（合言葉を付ける settings-mirror.js）を持たないので、このタブの全通信に合言葉のヘッダーを
        # 付ける設定をしてから開く。エディタのタブには使わない（アプリ側の付け忘れをテストで見逃さないため）
        tid = self.call("Target.createTarget", url="about:blank", background=True)["targetId"]
        self.call("Page.bringToFront")
        try:
            tab = Tab(self, tid, self.pipe.attach(tid))
            tab.call("Network.enable")
            tab.call("Network.setExtraHTTPHeaders", headers={"X-NLM-Token": self.token})
            tab.call("Page.navigate", url=f"http://127.0.0.1:{self.port}/{path}")
        except CdpError:
            raise CdpError("タブを開けませんでした") from None
        # 開いた直後のタブは、目的のページへ移る前に一瞬 about:blank（これも readyState は complete）になる。
        # そこで返すと、入れたJSが直後のページ移動で消える・相対URLが使えない（PCが混んでいる時に画面テストが46件まとめて落ちた。
        # tests/README.md「たまに出るエラーの記録」）。目的のページに移ったことも確かめる
        for _ in range(200):
            if tab.js("location.protocol.startsWith('http')&&document.readyState==='complete'"):
                return tab
            time.sleep(0.05)
        raise CdpError(f"補助タブが {path} を開けませんでした（10秒）")

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

    def _frame(self):
        """描画ループを抑えている時（max_fps）は、ボタン・キーを押す前に1回の描画を待つ。エディタは、マウスの下にある物・置いたノーツの3Dの形・
        NLEの◆の位置などを描画のたびに作り直すので、それより速く次の操作をすると古い状態に当たる（人の操作ではありえない速さ。
        毎秒30回にした時に「置いた直後のノーツのクリック」「足した直後の◆のダブルクリック」が外れた）"""
        if self.max_fps:
            self.js("new Promise(r=>requestAnimationFrame(()=>r(0)))")

    def move(self, x, y, buttons=0, **mods):
        self.call("Input.dispatchMouseEvent", type="mouseMoved", x=x, y=y, buttons=buttons, modifiers=self._mods(**mods))

    def click(self, x, y, button="left", count=1, **mods):
        m = self._mods(**mods)
        bmask = {"left": 1, "right": 2, "middle": 4}[button]
        self.move(x, y, **mods)
        self._frame()
        self.call("Input.dispatchMouseEvent", type="mousePressed", x=x, y=y, button=button, buttons=bmask, clickCount=count, modifiers=m)
        self.call("Input.dispatchMouseEvent", type="mouseReleased", x=x, y=y, button=button, buttons=0, clickCount=count, modifiers=m)

    def drag(self, x0, y0, x1, y1, steps=12, button="left", **mods):
        m = self._mods(**mods)
        bmask = {"left": 1, "right": 2, "middle": 4}[button]
        self.move(x0, y0, **mods)
        self._frame()
        self.call("Input.dispatchMouseEvent", type="mousePressed", x=x0, y=y0, button=button, buttons=bmask, clickCount=1, modifiers=m)
        for i in range(1, steps + 1):
            t = i / steps
            self.call("Input.dispatchMouseEvent", type="mouseMoved", x=x0 + (x1 - x0) * t, y=y0 + (y1 - y0) * t,
                      button=button, buttons=bmask, modifiers=m)
        self._frame()
        self.call("Input.dispatchMouseEvent", type="mouseReleased", x=x1, y=y1, button=button, buttons=0, clickCount=1, modifiers=m)

    def wheel(self, x, y, dy, dx=0, **mods):
        self._frame()
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
        self._frame()
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

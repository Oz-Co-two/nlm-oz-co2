"""serve.py のアクセス制御と静的配信（Host/Origin/CSRFヘッダー/パス検査/フォルダ一覧）"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import unitpy_helpers as H


def test_host_local_names_ok(t):
    '''Hostがローカル名（127.0.0.1・localhost・::1・ポート付き）なら通る'''
    s = H.server()
    for host in (f"127.0.0.1:{s.port}", "127.0.0.1", f"localhost:{s.port}", "LOCALHOST", f"[::1]:{s.port}"):
        st, _, _ = H.req("GET", "/editor.html", host=host)
        t.eq(st, 200, f"Host={host}")


def test_host_foreign_denied(t):
    '''Hostがローカル名でない要求は403（DNSリバインディング対策）'''
    for host in ("evil.example.com", "evil.example.com:80", "127.0.0.1.evil.com", "10.0.0.5", ""):
        st, _, _ = H.req("GET", "/editor.html", host=host)
        t.eq(st, 403, f"Host={host!r}")
    st, _, _ = H.req("HEAD", "/editor.html", host="evil.example.com")
    t.eq(st, 403, "HEAD")


def test_host_extra_allowed(t):
    '''NLM_ALLOWED_HOSTS で足したホスト名は通る（大文字小文字は無視）'''
    st, _, _ = H.req("GET", "/editor.html", host=H.EXTRA_HOST)
    t.eq(st, 200, "追加ホスト")
    st, _, _ = H.req("GET", "/editor.html", host=H.EXTRA_HOST.upper() + ":8000")
    t.eq(st, 200, "追加ホスト(大文字・ポート付き)")


def test_origin_foreign_denied(t):
    '''Originが他サイトなら403。同じローカルのOriginと "null" は通る'''
    s = H.server()
    st, _, _ = H.req("GET", "/editor.html", origin="https://evil.example.com")
    t.eq(st, 403, "他サイトOrigin")
    st, _, _ = H.req("GET", "/editor.html", origin=f"http://127.0.0.1:{s.port}")
    t.eq(st, 200, "ローカルOrigin")
    st, _, _ = H.req("GET", "/editor.html", origin="null")
    t.eq(st, 200, "Origin: null")


def test_post_needs_header(t):
    '''POSTは X-NLM-Request: 1 が無い（や値が違う）と403、あれば通る'''
    body = b'{"data":{}}'
    st, _, _ = H.req("POST", "/__settings/save", body=body, headers={"Content-Type": "application/json"})
    t.eq(st, 403, "ヘッダー無し")
    st, _, _ = H.req("POST", "/__settings/save", body=body, headers={"X-NLM-Request": "0"})
    t.eq(st, 403, "値が違う")
    st, obj = H.post_json("/__settings/save", {"data": {"a": 1}})
    t.eq((st, obj), (200, {"ok": True}), "ヘッダーあり")
    st, obj = H.post_json("/__settings/save", {"data": {}}, host="evil.example.com")
    t.eq(st, 403, "ヘッダーありでも外部Host")
    st, obj = H.post_json("/__settings/save", {"data": {}}, origin="https://evil.example.com")
    t.eq(st, 403, "ヘッダーありでも外部Origin")


def test_post_unknown_endpoint(t):
    '''知らないPOST先は404のJSON'''
    st, obj = H.post_json("/__nothing/here", {})
    t.eq(st, 404, "status")
    t.eq(obj.get("ok"), False, "ok")


def test_static_files_ok(t):
    '''通常の静的ファイル（editor.html・js）は200で、キャッシュ無効ヘッダーが付く'''
    st, hd, body = H.req("GET", "/editor.html")
    t.eq(st, 200, "editor.html")
    t.ok(b"<html" in body.lower(), "HTMLの中身")
    t.ok("no-store" in hd.get("Cache-Control", ""), "Cache-Control")
    st, _, _ = H.req("GET", "/js/main.js")
    t.eq(st, 200, "js/main.js")
    st, _, _ = H.req("GET", "/editor.html?x=1#frag")
    t.eq(st, 200, "クエリ付き")
    st, _, _ = H.req("GET", "/no-such-file.html")
    t.eq(st, 404, "存在しない")


def test_path_traversal_denied(t):
    '''\\・ドライブ名・..（エンコード形も）を含むパスは404でフォルダ外を返さない'''
    paths = [
        "/..%2f..%2fwindows/win.ini",
        "/C:%5CWindows%5Cwin.ini",
        "/C:/Windows/win.ini",
        "/c%3A/Windows/win.ini",
        "/..%5Cserve.py",
        "/js%5C..%5C..%5Cserve.py",
        "/asset/..%5C..%5Cserve.py",
        "/lang/..%5C..%5Cserve.py",
        "/%5Cserve.py",
        "/editor.html:stream",
    ]
    for p in paths:
        st, _, body = H.req("GET", p)
        t.eq(st, 404, p)
        t.ok(b"import http.server" not in body, f"serve.py の中身を返した: {p}")


def test_dotdot_collapsed_stays_in_root(t):
    '''ルートより上へ行く .. は normpath で潰れてルート内のファイルになる（フォルダの外は返らない）'''
    own = (H.ROOT / "serve.py").read_bytes()
    for p in ("/../serve.py", "/%2e%2e/serve.py", "/js/../../serve.py", "/asset/../../serve.py", "/lang/../serve.py"):
        st, _, body = H.req("GET", p)
        t.ok(st == 404 or body == own, f"ルート内以外を返した可能性: {p} -> {st}")


def test_directory_listing_only_asset(t):
    '''フォルダ一覧は asset/ 配下だけ。アプリ本体のフォルダ（/js/ /lang/ /config/ 等）は一覧を返さない'''
    st, _, body = H.req("GET", "/asset/")
    t.eq(st, 200, "/asset/")
    t.ok(b"Directory listing" in body, "一覧が出る")
    for p in ("/js/", "/js", "/lang/", "/config/", "/tools/", "/preview-v4/"):
        st, _, body = H.req("GET", p)
        t.ok(b"Directory listing" not in body, f"一覧を返した: {p}")
        t.ok(st in (301, 404), f"{p} -> {st}")


def test_asset_seed_fallback(t):
    '''データフォルダのasset/に無いクリップは同梱の見本から返る'''
    seeds = [f for f in os.listdir(H.ROOT / "asset") if f.endswith(".nlmclip")]
    if not seeds:
        t.skip("同梱の見本クリップが無い")
    from urllib.parse import quote
    st, _, body = H.req("GET", "/asset/" + quote(seeds[0]))
    t.eq(st, 200, "見本クリップ")
    t.ok(len(body) > 2, "中身がある")


def test_settings_fallback_default(t):
    '''config/settings.json はデータフォルダに無ければ settings.default.json を返し、保存後は保存した方を返す'''
    s = H.server()
    live = Path(s.data_dir) / "config" / "settings.json"
    if live.exists():
        live.unlink()
    st, _, body = H.req("GET", "/config/settings.json")
    t.eq(st, 200, "status")
    t.eq(body, (H.ROOT / "config" / "settings.default.json").read_bytes(), "既定の設定")
    H.post_json("/__settings/save", {"data": {"bsnm_test": "1"}})
    st, _, body = H.req("GET", "/config/settings.json")
    t.ok(b"bsnm_test" in body, "保存した設定が返る")


def test_token_required(t):
    '''API・利用者のデータ（設定・アセット・開いたファイル）・翻訳・開発用のファイルは、合言葉（X-NLM-Token）が無い・違う・
    Cookie や URL で渡した時は403。ヘッダーで正しく渡せば通る（ブラウザ以外の同じPCの別アカウントや LAN から使わせない）'''
    s = H.server()
    tok = s.serve.SESSION_TOKEN
    t.ok(len(tok) >= 40, "合言葉の長さ")
    gets = ["/__openarg", "/config/settings.json", "/asset/", "/lang/ja.json", "/tools/fixtures/basic.nlmf", "/serve.py", "/"]
    for bad in (False, "x" * len(tok), tok[:-1], tok + "x", "日本語".encode("utf-8")):   # ASCII 以外の値でも落ちずに断る
        for p in gets:
            st, _, _ = H.req("GET", p, token=bad)
            t.eq(st, 403, f"GET {p} 合言葉={bad!r}")
        st, _, _ = H.req("HEAD", "/config/settings.json", token=bad)
        t.eq(st, 403, f"HEAD 合言葉={bad!r}")
        for p in ("/__settings/save", "/__asset/delete", "/__openarg/save", "/__update/status", "/__nothing"):
            st, _, _ = H.req("POST", p, headers={"X-NLM-Request": "1"}, body=b"{}", token=bad)
            t.eq(st, 403, f"POST {p} 合言葉={bad!r}")
    for how in ({"Cookie": f"X-NLM-Token={tok}"}, {"Cookie": f"nlm_session_{s.port}={tok}"}, {"Authorization": f"Bearer {tok}"}):
        st, _, _ = H.req("GET", "/config/settings.json", headers=how, token=False)
        t.eq(st, 403, f"ヘッダー以外では渡せない: {list(how)}")
    st, _, _ = H.req("GET", f"/config/settings.json?k={tok}", token=False)
    t.eq(st, 403, "URLの ?k= では渡せない")
    st, _, _ = H.req("GET", "/config/settings.json", headers={"x-nlm-token": tok}, token=False)
    t.eq(st, 200, "ヘッダー名の大文字小文字は問わない")
    for p in ("/config/settings.json", "/asset/", "/lang/ja.json"):
        st, _, _ = H.req("GET", p)
        t.eq(st, 200, f"合言葉付き {p}")


def test_public_static_without_token(t):
    '''画面の部品（editor.html・js・css・icons・fonts・preview-v4・guide）は合言葉なしで返す（<script src>・<link>・<img>・import() は
    ヘッダーを付けられない）'''
    font = next((H.ROOT / "fonts").glob("*.ttf")).name
    for p in ("/editor.html", "/editor.html?dev=1", "/js/main.js", "/js/vendor/three/three.module.js", "/css/base.css",
              "/icons/app_icon.svg", f"/fonts/{font}", "/preview-v4/preview-v4.js", "/preview-v4/env/DefaultEnvironment.json",
              "/guide/ana-clips-btn-ja.png", "/guide/ana-clips-btn-en.png"):
        st, _, _ = H.req("GET", p, token=False)
        t.eq(st, 200, p)


def test_token_aliases_and_junction(t):
    '''合言葉なしで返す物は名前の完全一致で決める＝別名（大文字・末尾の点・%xx・.. で戻る・二重スラッシュ）や、
    asset/ 内のジャンクション経由では、守っている場所を合言葉なしで読めない'''
    s = H.server()
    settings = (H.ROOT / "config" / "settings.default.json").read_bytes()
    for p in ("/ASSET/", "/asset./", "/%61sset/", "/js/../config/settings.json", "/js/%2e%2e/config/settings.json",
              "/editor.html/../config/settings.json", "/./config/settings.json", "//config/settings.json",
              "/CONFIG~1/SETTIN~1.JSO", "/config./settings.json", "/js/..%5Cconfig%5Csettings.json", "/fonts/../serve.py"):
        st, _, body = H.req("GET", p, token=False)
        t.ok(st in (403, 404), f"{p} -> {st}")
        t.ok(body != settings and b"import http.server" not in body, f"中身を返した: {p}")
    import subprocess
    import tempfile
    outside = Path(tempfile.mkdtemp(prefix="nlm_unitpy_out_"))
    (outside / "secret.nlmclip").write_text('{"secret":1}', encoding="utf-8")
    link = Path(s.data_dir) / "asset" / "linked"
    try:
        os.symlink(str(outside), str(link), target_is_directory=True)
    except (OSError, NotImplementedError):
        if subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(outside)], capture_output=True).returncode != 0:
            t.skip("リンクを作れない環境")
    try:
        for p in ("/asset/linked/", "/asset/linked/secret.nlmclip"):
            st, _, body = H.req("GET", p, token=False)
            t.eq(st, 403, f"ジャンクション経由・合言葉なし {p}")
        st, _, body = H.req("GET", "/asset/linked/secret.nlmclip")
        t.eq((st, body), (200, b'{"secret":1}'), "合言葉付きなら従来どおり読める")
    finally:
        os.rmdir(str(link))   # リンク（シンボリックリンク・ジャンクション）だけを外す。リンク先は消えない


def test_standalone_start_message(t):
    '''python serve.py 単体の起動: 合言葉付きの URL を英語(ASCII)で表示し、日本語を表せない文字コードで出力をファイルへ回しても
    落ちずに待ち受ける（以前の修正案は日本語の表示で起動前に落ちた）。表示された合言葉で使える'''
    import http.client
    import re
    import subprocess
    import tempfile
    import time
    port = H._free_port()
    env = dict(os.environ, NLM_DATA_DIR=tempfile.mkdtemp(prefix="nlm_unitpy_sa_"), PYTHONIOENCODING="cp1252", PYTHONUTF8="0")
    env.pop("NLM_OPEN_FILE", None)
    p = subprocess.Popen([sys.executable, str(H.ROOT / "serve.py"), f"--port={port}", "--no-browser"], cwd=str(H.ROOT),
                         env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    try:
        def get(path, tok=None):
            c = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
            try:
                c.request("GET", path, headers={"Host": f"127.0.0.1:{port}", **({"X-NLM-Token": tok} if tok else {})})
                return c.getresponse().status
            finally:
                c.close()
        for _ in range(100):
            if p.poll() is not None:
                break
            try:
                if get("/editor.html") == 200:
                    break
            except OSError:
                time.sleep(0.1)
        t.ok(p.poll() is None, "起動して待ち受けている: " + (p.stderr.read().decode("cp1252", "replace") if p.poll() is not None else ""))
        out = b"".join(p.stdout.readline() for _ in range(3))   # 待ち受ける前に表示し終えている
        t.ok(out.isascii(), "表示は ASCII だけ")
        m = re.search(rb"http://127\.0\.0\.1:%d/editor\.html#k=([A-Za-z0-9_-]+)" % port, out)
        t.ok(m, "合言葉付きの URL を表示: " + out.decode("ascii", "replace"))
        t.eq(get("/config/settings.json"), 403, "合言葉なし")
        t.eq(get("/config/settings.json", m.group(1).decode("ascii")), 200, "表示された合言葉で使える")
    finally:
        p.terminate()
        try:
            p.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            p.kill()

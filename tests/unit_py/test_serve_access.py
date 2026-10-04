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

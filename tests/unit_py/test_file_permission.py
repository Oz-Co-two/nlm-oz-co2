"""app.py の「ファイルの書き込みの許可」: exe版（WebView2）で、選んだファイルへの書き込みの許可の確認を出さずに許可する条件（画面は出さない）。
許可するのは、ファイルの読み書きの種類・このアプリ自身の画面（この起動の http://127.0.0.1:<port>）から、の両方を満たす時だけ。
「利用者の操作から始まった要求だけ」は WebView2 が常に False と報告するため条件にしていない（app.py の説明）"""
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent))
import unitpy_helpers as H

ORIGIN = "http://127.0.0.1:54321"


def _app():
    sys.path.insert(0, str(H.ROOT))
    import app   # import しても画面は出ない（webview は main() の中で import される）
    return app


def test_file_rw_allowed_only_own_page(t):
    '''このアプリ自身の画面（同じスキーム・ホスト・ポート）からの要求だけ許可する。別のポート・別のホスト名・https・userinfo を使った偽装・壊れたURLは許可しない'''
    app = _app()
    ok = lambda uri: app._file_rw_allowed(uri, ORIGIN, True)
    t.ok(ok("http://127.0.0.1:54321/editor.html#k=abc"), "この起動の画面（合言葉付きのURL）")
    t.ok(ok("http://127.0.0.1:54321/"), "同じ画面の別のパス")
    t.ok(ok("HTTP://127.0.0.1:54321/editor.html"), "スキームの大文字小文字は区別しない")
    for uri, why in (("http://127.0.0.1:54322/editor.html", "別のポート（別のアプリ・前の起動）"),
                     ("http://localhost:54321/editor.html", "別のホスト名"),
                     ("https://127.0.0.1:54321/editor.html", "https"),
                     ("http://127.0.0.1:54321@evil.example/editor.html", "userinfo で自分の画面に見せかけた別のサイト"),
                     ("http://evil.example/?http://127.0.0.1:54321", "URLの途中に自分の画面のアドレスがあるだけ"),
                     ("http://[::1/editor.html", "壊れたURL"),
                     ("", "空")):
        t.ok(not ok(uri), f"許可しない: {why}")


def test_file_rw_allowed_needs_kind(t):
    '''ファイルの読み書きの種類でない要求（カメラ・マイク等）は、自分の画面からでも許可しない'''
    app = _app()
    t.ok(not app._file_rw_allowed(ORIGIN + "/editor.html", ORIGIN, False), "別の種類")


class _Args:
    """CoreWebView2PermissionRequestedEventArgs の偽物（使う項目だけ）"""
    def __init__(self, uri, kind, user, no_saves=False):
        self.Uri, self.PermissionKind, self.IsUserInitiated, self.State = uri, kind, user, "Default"
        if not no_saves:
            self.SavesInProfile = True

    def __setattr__(self, name, value):
        if name == "SavesInProfile" and getattr(self, "_ro", False):
            raise AttributeError("古い WebView2 には無い")
        object.__setattr__(self, name, value)


def test_file_rw_handler_sets_allow_without_saving(t):
    '''ハンドラー: 条件を満たす要求は「許可」にし、プロファイルに保存しない（SavesInProfile=False）。満たさない要求は何も変えない（WebView2 の既定の確認が出る）。
    WebView2 は IsUserInitiated を常に False と報告するので、False でも許可する。SavesInProfile が無い古い WebView2 でも許可はする'''
    app = _app()
    FILE_RW, CAMERA, ALLOW = SimpleNamespace(n="FileReadWrite"), SimpleNamespace(n="Camera"), "Allow"
    h = app._file_rw_handler(ORIGIN, FILE_RW, ALLOW)
    a = _Args(ORIGIN + "/editor.html", FILE_RW, False)   # 実機の WebView2 と同じく「操作からではない」と報告される
    h(None, a)
    t.eq((a.State, a.SavesInProfile), ("Allow", False), "許可し、保存しない")
    for args, why in ((_Args(ORIGIN + "/editor.html", CAMERA, True), "別の種類"),
                      (_Args("http://127.0.0.1:1/editor.html", FILE_RW, True), "別の画面")):
        h(None, args)
        t.eq((args.State, args.SavesInProfile), ("Default", True), f"何も変えない: {why}")
    old = _Args(ORIGIN + "/editor.html", FILE_RW, False, no_saves=True)
    object.__setattr__(old, "_ro", True)
    h(None, old)
    t.eq(old.State, "Allow", "SavesInProfile が無くても許可する")
    broken = SimpleNamespace(PermissionKind=FILE_RW)   # Uri 等が読めない
    h(None, broken)
    t.ok(not hasattr(broken, "State"), "読めない項目があっても例外を出さず、何も変えない")

"""app.py の窓の位置・大きさの記憶（閉じた時の状態で次も開く・2026-10-18。画面は出さない）。
閉じる時に config/window.json へ残し（_window_geometry → _save_window）、次に開く時に create_window へ渡す（_load_window）。
実際の exe での確認（閉じて開き直すと同じ位置・大きさ）は手で行う（pywebview の窓はテストで作れないため）"""
import json
import sys
import tempfile
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import unitpy_helpers as H

SCREEN = types.SimpleNamespace(x=0, y=0, width=1920, height=1080)


def _app():
    sys.path.insert(0, str(H.ROOT))
    import app   # import しても画面は出ない（webview は main() の中で import される）
    return app


def _dir():
    return Path(tempfile.mkdtemp(prefix="nlm_unitpy_win_"))


def _write(d, **w):
    (d / _app().WINDOW_FILE).write_text(json.dumps(w), encoding="utf-8")


def _form(state, bounds, restore=None):
    rect = lambda r: types.SimpleNamespace(X=r[0], Y=r[1], Width=r[2], Height=r[3])   # noqa: E731
    return types.SimpleNamespace(WindowState=state, Bounds=rect(bounds), RestoreBounds=rect(restore or bounds))


def test_load_window(t):
    '''記録が無ければ初めての大きさ（1600×980・真ん中）。あれば位置・大きさ・最大化を使う。最小（1100×720）より小さくしない。
    壊れた記録は無視する'''
    app, d = _app(), _dir()
    first = {"width": 1600, "height": 980}
    t.eq(app._load_window(str(d), [SCREEN]), first, "記録が無い")
    _write(d, x=100, y=50, width=1500, height=900, maximized=True)
    t.eq(app._load_window(str(d), [SCREEN]), {"x": 100, "y": 50, "width": 1500, "height": 900, "maximized": True}, "記録どおり")
    _write(d, x=100, y=50, width=300, height=200, maximized=False)
    r = app._load_window(str(d), [SCREEN])
    t.eq((r["width"], r["height"], r["maximized"]), (1100, 720, False), "最小より小さくしない")
    for bad in ("{", "[]", '{"x": 1}', '{"x": "a", "y": 0, "width": 1, "height": 1}'):
        (d / app.WINDOW_FILE).write_text(bad, encoding="utf-8")
        t.eq(app._load_window(str(d), [SCREEN]), first, f"壊れた記録 {bad}")


def test_load_window_offscreen(t):
    '''外したモニターの上だった（タイトルバーが今の画面に見えない）時は、位置を使わず真ん中に開く（大きさは使う）。
    その画面がつながっていれば使う。画面が分からない時も真ん中'''
    app, d = _app(), _dir()
    for x, y in ((2500, 100), (100, 1070), (-1500, 100), (100, -500)):
        _write(d, x=x, y=y, width=1500, height=900)
        r = app._load_window(str(d), [SCREEN])
        t.ok("x" not in r and r["width"] == 1500, f"見えない位置 ({x},{y}): {r}")
    _write(d, x=-1500, y=100, width=1500, height=900)
    left = types.SimpleNamespace(x=-1920, y=0, width=1920, height=1080)
    t.eq(app._load_window(str(d), [SCREEN, left]).get("x"), -1500, "左のモニターがつながっていれば使う")
    t.ok("x" not in app._load_window(str(d), []), "画面が分からない")


def test_window_geometry(t):
    '''閉じる時の値は create_window と同じ論理の値（DPI の倍率で割る。125% なら 120dpi）。
    最大化・最小化している時は、元に戻した時の位置・大きさ'''
    app = _app()
    t.eq(app._window_geometry(_form("Normal", (125, 250, 1875, 1250)), dpi=120),
         {"x": 100, "y": 200, "width": 1500, "height": 1000, "maximized": False}, "普通（125%）")
    t.eq(app._window_geometry(_form("Maximized", (-10, -10, 2420, 1310), (125, 250, 1875, 1250)), dpi=120),
         {"x": 100, "y": 200, "width": 1500, "height": 1000, "maximized": True}, "最大化")
    t.eq(app._window_geometry(_form("Minimized", (-32000, -32000, 200, 40), (10, 20, 1300, 900)), dpi=96),
         {"x": 10, "y": 20, "width": 1300, "height": 900, "maximized": False}, "最小化")


def test_save_then_load(t):
    '''閉じる時に残した値で、次に同じ位置・大きさ・最大化で開く（config/ が無ければ作る。書きかけの .tmp は残らない）'''
    app, d = _app(), _dir()
    cfg = d / "config"
    app._save_window(str(cfg), app._window_geometry(_form("Maximized", (-8, -8, 1936, 1056), (100, 50, 1500, 900)), dpi=96))
    t.eq(app._load_window(str(cfg), [SCREEN]), {"x": 100, "y": 50, "width": 1500, "height": 900, "maximized": True}, "開き直し")
    t.eq(sorted(p.name for p in cfg.iterdir()), [app.WINDOW_FILE], "window.json だけ")

"""app.py の _NativeAccess（ファイル読み書きの許可範囲）と Api の fs_* の入口検査（画面は出さない）"""
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import unitpy_helpers as H


def _app():
    sys.path.insert(0, str(H.ROOT))
    import app   # import しても画面は出ない（webview は main() の中で import される）
    return app


def _setup():
    """(app, _NativeAccess, 許可済みフォルダ, 保存先json) を一時フォルダで作る"""
    app = _app()
    base = Path(tempfile.mkdtemp(prefix="nlm_unitpy_na_"))
    out = base / "out"
    out.mkdir()
    store = base / "config" / "native_out_dirs.json"
    acc = app._NativeAccess(str(store))
    acc.approve_dir(str(out))
    return app, acc, out, store, base


def test_write_only_inside_approved_dir(t):
    '''書き込みは許可済み出力フォルダの中（サブフォルダ含む）だけ'''
    app, acc, out, store, base = _setup()
    (out / "Song").mkdir()
    t.ok(acc.can_write(str(out / "Info.dat")), "直下")
    t.ok(acc.can_write(str(out / "Song" / "ExpertStandard.dat")), "サブフォルダ")
    t.ok(not acc.can_write(str(base / "Info.dat")), "親フォルダ")
    t.ok(not acc.can_write(str(base / "other" / "Info.dat")), "別フォルダ")
    t.ok(not acc.can_write(str(out) + "x" + os.sep + "Info.dat"), "名前が前方一致するだけの別フォルダ")


def test_write_extensions(t):
    '''書き込める拡張子は _WRITE_EXTS だけ（.dat/.egg/.json/画像）。実行ファイル系は不可・大文字小文字は無視'''
    app, acc, out, store, base = _setup()
    t.eq(app._WRITE_EXTS, {".dat", ".egg", ".json", ".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}, "許可拡張子の一覧")
    for n in ("Info.dat", "song.egg", ".nlm-egg.json", "cover.png", "cover.JPG", "A.Dat"):
        t.ok(acc.can_write(str(out / n)), n)
    for n in ("evil.exe", "evil.bat", "evil.cmd", "evil.lnk", "evil.ps1", "evil.dll", "evil.js", "evil", "evil.dat.exe", "a.txt"):
        t.ok(not acc.can_write(str(out / n)), n)


def test_write_blocks_escape(t):
    '''.. で出力フォルダの外へ出るパス・ADS(:)付きの名前は書けない'''
    app, acc, out, store, base = _setup()
    t.ok(not acc.can_write(str(out / ".." / "Info.dat")), "..で親へ")
    t.ok(not acc.can_write(str(out / "sub" / ".." / ".." / "Info.dat")), "..を重ねて親へ")
    t.ok(not acc.can_write(str(out / "Info.dat:evil.exe")), "代替データストリーム")
    t.ok(not acc.can_write(""), "空")
    t.ok(not acc.can_write("Info.dat"), "相対パス（カレントは許可外）")


def test_symlink_escape(t):
    '''出力フォルダ内のジャンクション/シンボリックリンクで外へ出られない（実体へ解決して判定）'''
    app, acc, out, store, base = _setup()
    outside = base / "outside"
    outside.mkdir()
    link = out / "link"
    try:
        os.symlink(str(outside), str(link), target_is_directory=True)
    except (OSError, NotImplementedError):
        import subprocess
        r = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(outside)], capture_output=True)
        if r.returncode != 0:
            t.skip("リンクを作れない環境")
    t.ok(not acc.can_write(str(link / "Info.dat")), "リンク経由は書けない")
    t.ok(not acc.can_read(str(link / "x.unknown")), "リンク経由は読めない")


def test_read_rules(t):
    '''読み込みは 音源/画像の拡張子 か ダイアログで選んだファイル か 許可済みフォルダの中、のどれか'''
    app, acc, out, store, base = _setup()
    t.ok(acc.can_read(str(base / "elsewhere" / "a.mp3")), "音源の拡張子")
    t.ok(acc.can_read(str(base / "elsewhere" / "a.PNG")), "画像の拡張子(大文字)")
    t.ok(not acc.can_read(str(base / "elsewhere" / "secret.txt")), "それ以外の拡張子は不可")
    t.ok(not acc.can_read(str(base / "elsewhere" / "id_rsa")), "拡張子なし")
    t.ok(acc.can_read(str(out / "Info.dat")), "許可済みフォルダの中なら任意の拡張子")
    t.ok(acc.can_read(str(out / "sub" / "note.txt")), "サブフォルダ")
    odd = base / "elsewhere" / "picked.weird"
    t.ok(not acc.can_read(str(odd)), "選ぶ前は不可")
    acc.picked_files.add(app._npath(str(odd)))
    t.ok(acc.can_read(str(odd)), "ダイアログで選んだ後は可")
    t.ok(not acc.can_read(str(base / "elsewhere" / "other.weird")), "選んだのは1つだけ")


def test_approved_dirs_persist(t):
    '''許可済みフォルダは保存先jsonに書かれ、次回起動（新しいインスタンス）でも有効。壊れたjsonは空扱い'''
    app, acc, out, store, base = _setup()
    t.ok(store.is_file(), "保存される")
    data = json.loads(store.read_text(encoding="utf-8"))
    t.eq(len(data["out_dirs"]), 1, "1件")
    acc2 = app._NativeAccess(str(store))
    t.ok(acc2.can_write(str(out / "Info.dat")), "再読込後も許可")
    store.write_text("{壊れた", encoding="utf-8")
    acc3 = app._NativeAccess(str(store))
    t.ok(not acc3.can_write(str(out / "Info.dat")), "壊れたjsonなら許可なし")
    store.write_text(json.dumps({"out_dirs": [123, None, str(out)]}), encoding="utf-8")
    acc4 = app._NativeAccess(str(store))
    t.ok(acc4.can_write(str(out / "Info.dat")), "文字列以外は読み飛ばす")


def test_not_approved_without_dialog(t):
    '''何も許可していない状態では、どこにも書けない'''
    app = _app()
    base = Path(tempfile.mkdtemp(prefix="nlm_unitpy_na_"))
    acc = app._NativeAccess(str(base / "config" / "native_out_dirs.json"))
    t.ok(not acc.can_write(str(base / "Info.dat")), "未許可")
    t.ok(not acc.in_out_dir(str(base)), "in_out_dir")


def test_npath_case_and_commonpath(t):
    '''_npath は大文字小文字を無視、_is_under は別ドライブでも例外にならない'''
    app = _app()
    t.eq(app._npath("C:\\Windows\\SYSTEM32"), app._npath("c:\\windows\\system32"), "大文字小文字")
    t.ok(app._is_under(app._npath("C:\\a"), app._npath("C:\\a\\b")), "配下")
    t.ok(not app._is_under(app._npath("C:\\a"), app._npath("C:\\ab")), "前方一致だけ")
    t.ok(not app._is_under(app._npath("C:\\a"), app._npath("D:\\a\\b")), "別ドライブ")


def test_data_root_dev(t):
    '''_data_root（開発時）は渡したフォルダ直下に config/asset/lang を作る。見本は空の時だけコピー'''
    app = _app()
    base = Path(tempfile.mkdtemp(prefix="nlm_unitpy_dr_"))
    root = base / "app"
    (root / "asset").mkdir(parents=True)
    d = app._data_root(str(root))
    t.eq(os.path.normcase(d), os.path.normcase(str(root)), "データフォルダ=app_root")
    for n in ("config", "asset", "lang"):
        t.ok((root / n).is_dir(), n)
    # 見本がデータフォルダと同じ場合はコピーしない（自分自身への複製をしない）
    t.eq(sorted(os.listdir(root / "asset")), [], "asset は空のまま")


def test_app_version_reads_constants(t):
    '''_app_version は js/constants.js の APP_VERSION を読む。読めなければ空文字'''
    app = _app()
    v = app._app_version(str(H.ROOT))
    t.ok(v.startswith("v"), f"版番号: {v!r}")
    src = (H.ROOT / "js" / "constants.js").read_text(encoding="utf-8")
    t.ok(f"'{v}'" in src, "constants.js と一致")
    t.eq(app._app_version(str(Path(tempfile.mkdtemp()))), "", "読めない時")


def test_open_file_arg(t):
    '''_open_file_arg は .nlmf/.bslm/.bsnm の実在ファイルだけ受け付ける'''
    app = _app()
    d = Path(tempfile.mkdtemp(prefix="nlm_unitpy_oa_"))
    good, bad, miss = d / "a.nlmf", d / "a.txt", d / "none.nlmf"
    good.write_text("{}")
    bad.write_text("x")
    old = sys.argv
    try:
        sys.argv = ["app.py", str(bad), str(miss)]
        t.eq(app._open_file_arg(), "", "不適当な拡張子・実在しない")
        sys.argv = ["app.py", str(bad), str(good)]
        t.eq(os.path.normcase(app._open_file_arg()), os.path.normcase(str(good)), "実在する.nlmf")
    finally:
        sys.argv = old

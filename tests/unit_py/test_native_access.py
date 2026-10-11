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


class _NetGuard:
    """ntpath の実体解決・存在確認を差し替え、ネットワーク上やNTパスらしいパス（区切り文字で始まる・?を含む）では
    本物を呼ばずに記録だけする（テストでは実際に接続しない）。resolve を渡すとその realpath は resolve(p) を返す"""
    NAMES = ("realpath", "isfile", "isdir", "exists")

    def __init__(self, resolve=None):
        self.resolve = resolve
        self.touched = []

    def __enter__(self):
        import ntpath
        self.orig = {n: getattr(ntpath, n) for n in self.NAMES}
        for n in self.NAMES:
            setattr(ntpath, n, self._wrap(n))
        return self

    def __exit__(self, *exc):
        import ntpath
        for n, f in self.orig.items():
            setattr(ntpath, n, f)

    def _wrap(self, n):
        def f(p, *a, **k):
            s = str(p)
            if s.replace("/", "\\").startswith("\\") or "?" in s:
                self.touched.append((n, s))
                if n == "realpath":
                    return self.resolve(s) if self.resolve else s
                return False
            return self.orig[n](p, *a, **k)
        return f


def test_path_kind(t):
    '''_path_kind は字面だけで分類: ドライブ名の絶対パス=local / \\\\server\\share=unc / それ以外（デバイス・NTパス・相対等）=None'''
    app = _app()
    for p in ("C:\\a\\b.mp3", "c:/a/b.mp3", "Z:\\"):
        t.eq(app._path_kind(p), "local", p)
    for p in ("\\\\nas\\music\\a.mp3", "//nas/music/a.mp3", "\\\\nas@80\\dav\\a.mp3", "\\\\nas\\share"):
        t.eq(app._path_kind(p), "unc", p)
    for p in ("\\\\?\\C:\\a.mp3", "\\\\?\\UNC\\nas\\s\\a.mp3", "\\\\.\\UNC\\nas\\s\\a.mp3", "//?/UNC/nas/s/a.mp3",
              "\\??\\UNC\\nas\\s\\a.mp3", "/??/UNC/nas/s/a.mp3", "\\??\\C:\\Windows\\win.ini", "\\\\\\nas\\s\\a",
              "\\\\nas", "\\\\nas\\", "\\a.mp3", "/a.mp3", "a.mp3", "C:a.mp3", "1:\\a.mp3", "\u0130:\\a.mp3",
              "", "C:\\a\0.mp3", None, 123):
        t.eq(app._path_kind(p), None, repr(p))


def test_network_paths_not_touched(t):
    '''このPCで選んでいないネットワーク上のパス・NTパス・デバイスパスは、判定の前に実体の解決・存在確認をしない
    （出力フォルダにドライブのルートを許可していても \\??\\UNC\\... が通らない）'''
    app, acc, out, store, base = _setup()
    acc.approve_dir(Path(str(out)).anchor)   # ドライブのルート（C:\ 等）を出力フォルダとして許可済みの利用者
    host = "nlm-unc-test.invalid"
    bad = ["\\\\%s\\x\\song.mp3" % host, "//%s/x/song.mp3" % host, "\\\\%s@80\\x\\song.mp3" % host,
           "\\??\\UNC\\%s\\x\\song.mp3" % host, "/??/UNC/%s/x/song.mp3" % host, "\\??\\C:\\Windows\\win.ini",
           "\\\\?\\UNC\\%s\\x\\song.mp3" % host, "\\\\.\\UNC\\%s\\x\\song.mp3" % host, "\\x\\song.mp3"]
    with _NetGuard() as g:
        for p in bad:
            t.ok(not acc.may_touch(p), "may_touch: " + p)
            t.ok(not acc.can_read(p), "can_read: " + p)
            t.ok(not acc.in_out_dir(p), "in_out_dir: " + p)
            t.ok(not acc.can_write(p.replace("song.mp3", "Info.dat")), "can_write: " + p)
    t.eq(g.touched, [], "ネットワーク上のパスに触れていない")
    t.ok(acc.may_touch(str(base / "elsewhere" / "a.mp3")), "ドライブ名から始まるパスは従来どおり")


def test_unc_picks_persist(t):
    '''ダイアログで選んだネットワーク上のファイルは保存され、次回起動でも自動読込できる。選んでいない物は不可'''
    import ntpath
    app, acc, out, store, base = _setup()
    song = "\\\\nas-test.invalid\\Music\\a.mp3"
    with _NetGuard(resolve=ntpath.abspath):
        acc.approve_file(song)
        acc.approve_file(str(base / "local.mp3"))
        data = json.loads(store.read_text(encoding="utf-8"))
        t.eq(data.get("unc_files"), [app._lpath(song)], "UNCのファイルだけ保存される")
        acc2 = app._NativeAccess(str(store))
        t.ok(acc2.may_touch(song), "次回起動でも可")
        t.ok(acc2.may_touch("//NAS-TEST.invalid/music/a.mp3"), "大文字小文字・区切り文字の違いは同じ扱い")
        t.ok(acc2.can_read(song), "読み込める")
        t.ok(not acc2.may_touch("\\\\nas-test.invalid\\Music\\b.mp3"), "同じフォルダの別ファイルは不可")
        t.ok(not acc2.may_touch("\\\\nas-test.invalid\\Music\\x\\..\\..\\Other\\a.mp3"), "..で別の場所へ")
        t.ok(not acc2.may_touch("\\\\other-test.invalid\\Music\\a.mp3"), "別のサーバーは不可")
        t.ok(acc2.can_write(str(out / "Info.dat")), "出力フォルダの許可も残る")


def test_unc_out_dir_matches_as_picked(t):
    '''ネットワーク上の出力フォルダは選んだ時の字面でも照合する（DFS等で実体のパスが違っても使える）。旧版の保存先jsonも有効'''
    app, acc, out, store, base = _setup()
    real = lambda p: p.replace("\\\\dfs-test.invalid\\ns", "\\\\srv-test.invalid\\share")
    dfs = "\\\\dfs-test.invalid\\ns\\out"
    with _NetGuard(resolve=real):
        acc.approve_dir(dfs)
        t.ok(acc.in_out_dir(dfs), "選んだ直後")
        t.ok(acc.can_write(dfs + "\\Song\\Info.dat"), "サブフォルダへ書ける")
        t.ok(not acc.may_touch("\\\\dfs-test.invalid\\ns\\other\\a.mp3"), "許可したフォルダの外は不可")
        t.ok(not acc.may_touch(dfs + "\\..\\other\\a.mp3"), "..で外へ")
        acc2 = app._NativeAccess(str(store))
        t.ok(acc2.in_out_dir(dfs), "次回起動でも可")
        store.write_text(json.dumps({"out_dirs": ["\\\\nas-test.invalid\\share\\out"]}), encoding="utf-8")
        acc3 = app._NativeAccess(str(store))
        t.ok(acc3.may_touch("\\\\nas-test.invalid\\share\\out\\Info.dat"), "旧版で許可したUNCの出力フォルダ")
        t.ok(not acc3.may_touch("\\\\nas-test.invalid\\share\\a.mp3"), "その外は不可")


class _FakeWebview:
    """_make_api に渡す偽の webview。ファイル選択ダイアログは開かず、呼ばれた引数を記録して result を返す"""
    class FileDialog:
        OPEN, FOLDER = "open", "folder"

    def __init__(self, result=None):
        self.result = result
        self.calls = []
        self.windows = [self]

    def create_file_dialog(self, kind, **kw):
        self.calls.append((kind, kw))
        return [self.result] if self.result else None


def _api(root=False):
    """(app, 本物のApi, 偽のwebview, _NativeAccess, 許可済みフォルダ, 一時フォルダ)。root=True ならドライブのルートも出力フォルダとして許可済み"""
    app, acc, out, store, base = _setup()
    if root:
        acc.approve_dir(Path(str(out)).anchor)
    wv = _FakeWebview()
    return app, app._make_api(acc, str(base), {"dirty": False, "force": False}, wv), wv, acc, out, base


def test_api_network_paths_not_touched(t):
    '''JSから呼ばれる入口（Api）は、このPCで選んでいないネットワーク上のパス・NTパス・デバイスパスを、
    存在確認・実体の解決・読み書き・ダイアログの開始位置のどれにも使わずに断る（.nlmf に書かれたパスで接続させない）。
    出力フォルダにドライブのルートを許可している利用者でも \\??\\UNC\\... が通らない'''
    app, api, wv, acc, out, base = _api(root=True)
    host = "nlm-unc-test.invalid"
    bad = ["\\\\%s\\x" % host, "//%s/x" % host, "\\\\%s@80\\x" % host, "\\??\\UNC\\%s\\x" % host,
           "/??/UNC/%s/x" % host, "\\\\?\\UNC\\%s\\x" % host, "\\\\.\\UNC\\%s\\x" % host, "\\x"]
    with _NetGuard() as g:
        for d in bad:
            song, info = d + "\\song.mp3", d + "\\Info.dat"
            t.eq(api.read_song_file(song), {"ok": False, "error": "not-allowed"}, "read_song_file: " + song)
            t.eq(api.fs_isfile(song), False, "fs_isfile: " + song)
            t.eq(api.out_dir_ok(d), "unapproved", "out_dir_ok: " + d)
            t.eq(api.fs_subdir(d, "Song", True), {"ok": False, "error": "not-allowed"}, "fs_subdir: " + d)
            t.eq(api.fs_file(d, "Info.dat", True), {"ok": False, "error": "not-allowed"}, "fs_file: " + d)
            t.eq(api.fs_write(info, "e30="), {"ok": False, "error": "not-allowed"}, "fs_write: " + info)
            api.pick_folder(d)
            api.pick_image_file(d + "\\cover.png")
    t.eq(g.touched, [], "ネットワーク上のパスに触れていない")
    t.ok(all("directory" not in kw for _, kw in wv.calls), "ダイアログの開始位置に使っていない")
    t.eq(len(wv.calls), len(bad) * 2, "ダイアログは開く（開始位置なし）")


def test_api_local_paths_unchanged(t):
    '''ドライブ名から始まるパスは、入口の検査を足す前と同じ結果（読込・存在確認・出力フォルダの判定・書き出し・ダイアログの開始位置）'''
    import base64
    app, api, wv, acc, out, base = _api()
    other = base / "elsewhere"
    other.mkdir()
    song = other / "a.mp3"
    song.write_bytes(b"ID3\x03abc")
    r = api.read_song_file(str(song))
    t.ok(r.get("ok"), "音源の拡張子は読める")
    t.eq((r["name"], base64.b64decode(r["data"])), ("a.mp3", b"ID3\x03abc"), "名前と中身")
    t.eq(api.read_song_file(str(other / "none.mp3")), {"ok": False, "error": "not-found"}, "無いファイル")
    (other / "secret.txt").write_text("x")
    t.eq(api.read_song_file(str(other / "secret.txt")), {"ok": False, "error": "not-allowed"}, "許可外の拡張子")
    t.eq(api.read_song_file(""), {"ok": False, "error": "not-found"}, "空")
    t.ok(api.fs_isfile(str(song)), "fs_isfile: 有る")
    t.ok(not api.fs_isfile(str(other / "none.mp3")), "fs_isfile: 無い")
    t.eq(api.out_dir_ok(str(out)), "ok", "許可済み出力フォルダ")
    t.eq(api.out_dir_ok(str(base / "none")), "missing", "存在しない")
    t.eq(api.out_dir_ok(str(other)), "unapproved", "有るが選んでいないフォルダ")
    t.eq(api.out_dir_ok(""), "missing", "空")
    sub = api.fs_subdir(str(out), "Song", True)
    t.ok(sub.get("ok") and os.path.isdir(sub["path"]), "サブフォルダを作れる")
    f = api.fs_file(sub["path"], "Info.dat", True)
    t.ok(f.get("ok"), "ファイルの場所")
    t.eq(api.fs_write(f["path"], base64.b64encode(b"{}").decode()), {"ok": True}, "書ける")
    t.eq(Path(f["path"]).read_bytes(), b"{}", "書いた中身")
    t.eq(api.fs_subdir(str(out), "..", True), {"ok": False, "error": "bad-name"}, "..は不可")
    t.eq(api.fs_write(str(out / "Song" / "none" / "Info.dat"), "e30="), {"ok": False, "error": "no-dir"}, "フォルダが無い")
    api.pick_folder(str(out))
    api.pick_image_file(str(out / "cover.png"))
    t.eq([kw.get("directory") for _, kw in wv.calls], [str(out), str(out)], "ダイアログは保存済みの場所から開く")


def test_api_dialog_picks_are_allowed(t):
    '''ダイアログで選んだものは入口を通る: 想定外の拡張子のファイルも読め、選んだフォルダは出力先になり、
    選んだネットワーク上のファイルは存在確認まで進む（選んでいない物は従来どおり断る）'''
    import ntpath
    app, api, wv, acc, out, base = _api()
    odd = base / "picked.weird"
    odd.write_bytes(b"x")
    t.eq(api.read_song_file(str(odd)), {"ok": False, "error": "not-allowed"}, "選ぶ前")
    wv.result = str(odd)
    t.eq(api.pick_song_file(), str(odd), "選んだパスを返す")
    t.ok(api.read_song_file(str(odd)).get("ok"), "選んだ後は読める")
    newdir = base / "out2"
    newdir.mkdir()
    t.eq(api.out_dir_ok(str(newdir)), "unapproved", "選ぶ前の出力フォルダ")
    wv.result = str(newdir)
    api.pick_folder()
    t.eq(api.out_dir_ok(str(newdir)), "ok", "選んだ後は出力先")
    song = "\\\\nas-test.invalid\\Music\\a.mp3"
    with _NetGuard(resolve=ntpath.abspath) as g:
        wv.result = song
        api.pick_image_file()
        t.eq(api.read_song_file(song), {"ok": False, "error": "not-found"}, "選んだUNCは存在確認まで進む（テストでは無い扱い）")
        t.ok(("isfile", song) in g.touched, "存在確認をした")
        n = len(g.touched)
        t.eq(api.read_song_file("\\\\nas-test.invalid\\Music\\b.mp3"), {"ok": False, "error": "not-allowed"}, "選んでいない物")
        t.eq(len(g.touched), n, "選んでいない物には触れない")


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


def test_ui_lang_from_settings(t):
    '''exe版の表示言語（ファイル選択ダイアログの種類名・エクスプローラーの種類名に使う）は config/settings.json の bsnm_lang。
    無い・壊れている・en以外なら日本語'''
    app = _app()
    base = Path(tempfile.mkdtemp(prefix="nlm_unitpy_lang_"))
    t.eq(app._ui_lang(str(base)), "ja", "settings.json が無ければ日本語")
    (base / "config").mkdir()
    cfg = base / "config" / "settings.json"
    cfg.write_text(json.dumps({"bsnm_lang": "en"}), encoding="utf-8")
    t.eq(app._ui_lang(str(base)), "en", "English を選んでいれば英語")
    cfg.write_text(json.dumps({"bsnm_lang": "ja"}), encoding="utf-8")
    t.eq(app._ui_lang(str(base)), "ja", "日本語")
    cfg.write_text("{壊れたjson", encoding="utf-8")
    t.eq(app._ui_lang(str(base)), "ja", "壊れていたら日本語")
    t.eq(sorted(app._DLG_TEXT), ["en", "ja"], "ダイアログの文言は日英")
    t.ok(all(set(n) == {"ja", "en"} for _, _, n, _ in app._ASSOC), "ファイルの種類名も日英")

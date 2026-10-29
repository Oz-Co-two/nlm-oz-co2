"""automodder_plugin.py と serve.py の /__automodder/*（AutoModder の判定のプラグイン nlm-automodder の取り込み・照合・実行）。
ネットには繋がない（取得は _get を差し替え）。実行は subprocess.run を差し替えて「プラグインの標準出力」を再現する。
手元に本物の配布の zip がある時は、環境変数 NLM_AUTOMODDER_ZIP にその場所を入れると本物でも動かす（無ければ飛ばす）。"""
import hashlib
import io
import json
import os
import sys
import tempfile
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import unitpy_helpers as H

sys.path.insert(0, str(H.ROOT))
import automodder_plugin as ap  # noqa: E402

FILES = [{"name": "Info.dat", "text": "{}"}, {"name": "ExpertStandard.dat", "text": "{}"}]


def _manifest(ver="0.1.0", proto=None, sha=None, size=100, **over):
    m = {"name": "nlm-automodder", "version": ver, "protocol": ap.PROTOCOL if proto is None else proto, "platform": ap.PLATFORM,
         "exe": "nlm-automodder.exe", "automodder": "1.6.6",
         "zip": {"name": f"nlm-automodder-{ver}-{ap.PLATFORM}.zip", "sha256": sha or "a" * 64, "size": size}}
    m.update(over)
    return m


def _zip(ver="0.1.0", proto=None, name="nlm-automodder", extra=None, with_exe=True):
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w") as z:
        z.writestr("plugin.json", json.dumps({"name": name, "version": ver, "protocol": ap.PROTOCOL if proto is None else proto,
                                              "automodder": "1.6.6"}))
        if with_exe:
            z.writestr("nlm-automodder.exe", b"MZ-dummy")
        for k, v in (extra or {}).items():
            zi = zipfile.ZipInfo("tmp")
            zi.filename = k   # ZipInfo の初期化は \ を / に直してしまうので、後から生の名前を入れる
            z.writestr(zi, v)
    return b.getvalue()


def _plugin(tmp=None):
    d = tmp or tempfile.mkdtemp(prefix="nlm_unitpy_am_")
    return ap.AutoModderPlugin(d), Path(d)


def _code(fn, *a):
    try:
        fn(*a)
    except ap.PluginError as e:
        return e.code
    return None


class _Fake:
    """subprocess.run の差し替え。stdout に返す物（辞書なら JSON にする）と、受け取った物の記録"""
    def __init__(self, out, stderr=b"", rc=0, exc=None):
        self.out, self.stderr, self.rc, self.exc, self.seen = out, stderr, rc, exc, []

    def __call__(self, cmd, input=None, **kw):
        self.seen.append({"cmd": cmd, "input": json.loads(input), "kw": kw})
        if self.exc:
            raise self.exc
        r = type("R", (), {})()
        r.returncode, r.stderr = self.rc, self.stderr
        r.stdout = json.dumps(self.out).encode() if isinstance(self.out, (dict, list)) else self.out
        return r


def _with_run(fake, fn):
    orig = ap.subprocess.run
    try:
        ap.subprocess.run = fake
        return fn()
    finally:
        ap.subprocess.run = orig


def _ok_out(**over):
    o = {"protocol": 1, "ok": True, "plugin": {"name": "nlm-automodder", "version": "0.1.0"},
         "automodder": {"version": "1.6.6", "commit": "0c2621507170c427506297457c8abdef7765dad1", "parts": {}},
         "config": "default", "songLength": 61.5, "elapsedMs": 812.7, "results": [], "criteria": {"info": {}, "diff": {}}, "errors": []}
    o.update(over)
    return o


# ---------------------------------------------------------------- manifest・取り込み
def test_manifest_valid(t):
    '''正しい manifest は通る（exe の名前が無い古い形も通る）'''
    t.eq(ap.AutoModderPlugin._check_manifest(json.dumps(_manifest()))["version"], "0.1.0", "version")
    m = _manifest()
    del m["exe"]
    t.eq(ap.AutoModderPlugin._check_manifest(json.dumps(m))["version"], "0.1.0", "exe の欄が無くてもよい")


def test_manifest_rejects_bad(t):
    '''不正な manifest（名前・版・platform・protocol・exe・zip名・sha256・サイズ・JSON）は badManifest'''
    bad = {
        "name違い": _manifest(name="nlm-rating"),
        "版が不正": _manifest(ver="1.2"),
        "版にパス": _manifest(ver="1.2.3/../x"),
        "platform違い": _manifest(platform="linux-x64"),
        "protocolが文字列": _manifest(proto="1"),
        "protocolが真偽値": _manifest(proto=True),
        "exeの名前違い": _manifest(exe="evil.exe"),
        "zip名が版と不一致": _manifest(zip={"name": "evil.zip", "sha256": "a" * 64, "size": 1}),
        "zip名にパス": _manifest(zip={"name": "../nlm-automodder-0.1.0-win-x64.zip", "sha256": "a" * 64, "size": 1}),
        "sha256が短い": _manifest(sha="abc"),
        "sha256が大文字": _manifest(sha="A" * 64),
        "サイズ0": _manifest(size=0),
        "サイズ過大": _manifest(size=ap.MAX_ZIP + 1),
    }
    for label, m in bad.items():
        t.eq(_code(ap.AutoModderPlugin._check_manifest, json.dumps(m)), "badManifest", label)
    for raw in ("{壊れ", "[]", "null", "{}"):
        t.eq(_code(ap.AutoModderPlugin._check_manifest, raw), "badManifest", raw)


def test_install_rejects_hash_and_size_mismatch(t):
    '''install は zip の SHA-256 またはサイズが manifest と違えば hash で拒否し、何も展開しない'''
    p, d = _plugin()
    data = _zip()
    sha = hashlib.sha256(data).hexdigest()
    orig = ap.AutoModderPlugin.__dict__["_get"]   # staticmethod のまま戻す（関数で戻すと後のテストで self が渡る）
    try:
        for label, m in (("sha違い", _manifest(sha="b" * 64, size=len(data))), ("サイズ違い", _manifest(sha=sha, size=len(data) + 1))):
            raw = json.dumps(m).encode()
            ap.AutoModderPlugin._get = staticmethod(lambda url, limit, raw=raw: raw if url == ap.MANIFEST_URL else data)
            t.eq(_code(p.install), "hash", label)
            t.eq(p.installed(), [], f"{label}: 取り込まれていない")
            t.ok(not (d / "plugins" / "automodder" / "current.json").exists(), f"{label}: current.json無し")
    finally:
        ap.AutoModderPlugin._get = orig


def test_install_ok_and_urls_fixed(t):
    '''照合が合えば plugins/automodder/<版>/ へ展開して使う版にする。取得先は固定のURLだけ（manifest→公式のzip）'''
    p, d = _plugin()
    data = _zip()
    raw = json.dumps(_manifest(sha=hashlib.sha256(data).hexdigest(), size=len(data))).encode()
    urls = []
    orig = ap.AutoModderPlugin.__dict__["_get"]   # staticmethod のまま戻す（関数で戻すと後のテストで self が渡る）
    try:
        def fake(url, limit):
            urls.append(url)
            return raw if url == ap.MANIFEST_URL else data
        ap.AutoModderPlugin._get = staticmethod(fake)
        st = p.install()
    finally:
        ap.AutoModderPlugin._get = orig
    t.eq((st["current"], st["automodder"]), ("0.1.0", "1.6.6"), "使う版・AutoModder の版")
    t.eq(urls, ["https://github.com/Oz-Co-two/nlm-automodder/releases/latest/download/manifest.json",
                "https://github.com/Oz-Co-two/nlm-automodder/releases/download/v0.1.0/nlm-automodder-0.1.0-win-x64.zip"], "取得先は固定")
    t.ok((d / "plugins" / "automodder" / "0.1.0" / "nlm-automodder.exe").is_file(), "exeが展開される")
    t.eq(json.loads((d / "plugins" / "automodder" / "current.json").read_text()), {"version": "0.1.0"}, "current.json")
    t.eq(st["repo"], "https://github.com/Oz-Co-two/nlm-automodder", "配布元")


def test_install_rejects_new_protocol(t):
    '''NLMの知らない protocol のプラグインは取り込まない（zipの取得もしない）'''
    p, d = _plugin()
    raw = json.dumps(_manifest(proto=ap.PROTOCOL + 1)).encode()
    urls = []
    orig = ap.AutoModderPlugin.__dict__["_get"]   # staticmethod のまま戻す（関数で戻すと後のテストで self が渡る）
    try:
        ap.AutoModderPlugin._get = staticmethod(lambda url, limit: (urls.append(url), raw)[1])
        t.eq(_code(p.install), "protocol", "拒否")
        st = p.check()
        t.eq((st["latest"]["version"], st["latest"]["compatible"], st["latest"]["installed"]), ("0.1.0", False, False), "更新の確認は非互換と知らせる")
    finally:
        ap.AutoModderPlugin._get = orig
    t.eq(urls, [ap.MANIFEST_URL, ap.MANIFEST_URL], "zipは取りに行かない")
    t.eq(p.installed(), [], "取り込まれていない")


def test_network_errors(t):
    '''取得の失敗: 404 は notFound、それ以外は network（NLM_NO_NET のテストの環境で本物の _get も通信しない）'''
    import urllib.error
    import urllib.request
    p, d = _plugin()
    orig = urllib.request.urlopen
    try:
        def e404(*a, **k):
            raise urllib.error.HTTPError(ap.MANIFEST_URL, 404, "nf", {}, None)
        urllib.request.urlopen = e404
        t.eq(_code(p.check), "notFound", "404")
        def eoff(*a, **k):
            raise urllib.error.URLError("offline")
        urllib.request.urlopen = eoff
        t.eq(_code(p.install), "network", "繋がらない")
    finally:
        urllib.request.urlopen = orig


def test_install_zip_slip(t):
    '''zip内の ..・絶対パス・ドライブ名・. を含む名前は badZip で拒否し、外へ書かない'''
    for name in ("../evil.txt", "a/../../evil.txt", "/abs.txt", "C:evil.txt", "./x.txt"):
        p, d = _plugin()
        t.eq(_code(p.install_zip, _zip(extra={name: "x"}), "0.1.0"), "badZip", name)
        t.eq(p.installed(), [], f"{name}: 取り込まれない")
        t.ok(not (d / "evil.txt").exists() and not (d.parent / "evil.txt").exists(), f"{name}: 外に書かれていない")


def test_install_zip_checks_meta(t):
    '''plugin.json の名前・版・protocol が合わない／exeが無い／zipでない物は badZip。展開後の大きさの上限は tooLarge'''
    p, d = _plugin()
    t.eq(_code(p.install_zip, _zip(ver="0.2.0"), "0.1.0"), "badZip", "版が違う")
    t.eq(_code(p.install_zip, _zip(proto=ap.PROTOCOL + 1), "0.1.0"), "badZip", "protocolが違う")
    t.eq(_code(p.install_zip, _zip(name="nlm-rating"), "0.1.0"), "badZip", "名前が違う（別のプラグイン）")
    t.eq(_code(p.install_zip, _zip(with_exe=False), "0.1.0"), "badZip", "exe無し")
    t.eq(_code(p.install_zip, b"not a zip", "0.1.0"), "badZip", "zipでない")
    orig = ap.MAX_UNZIP
    try:
        ap.MAX_UNZIP = 10
        t.eq(_code(p.install_zip, _zip(extra={"big.bin": "x" * 100}), "0.1.0"), "tooLarge", "展開後が大きすぎる")
    finally:
        ap.MAX_UNZIP = orig
    t.eq(p.installed(), [], "どれも取り込まれていない")
    t.ok(not any(n.startswith(".tmp-") for n in os.listdir(p.root)), "一時フォルダが残らない")


def test_installed_and_current_selection(t):
    '''installed は新しい順・protocol違いは compatible=false・名前の違う plugin.json は無視。current は current.json の版→無ければ使える最新。
    use は未導入/非互換を拒否。手で置いた版（ネットに繋がらない PC）も同じ形なら使える'''
    p, d = _plugin()
    p.install_zip(_zip(ver="0.1.0"), "0.1.0")
    base = d / "plugins" / "automodder"
    for ver, meta in (("0.10.0", {"name": "nlm-automodder", "version": "0.10.0", "protocol": ap.PROTOCOL, "automodder": "1.7.0"}),
                      ("9.0.0", {"name": "nlm-automodder", "version": "9.0.0", "protocol": ap.PROTOCOL + 5}),
                      ("2.0.0", {"name": "nlm-rating", "version": "2.0.0", "protocol": ap.PROTOCOL})):
        (base / ver).mkdir(parents=True)
        (base / ver / "plugin.json").write_text(json.dumps(meta))
        (base / ver / "nlm-automodder.exe").write_bytes(b"x")
    (base / "junk").mkdir()
    (base / "1.0.0").mkdir()
    (base / "1.0.0" / "plugin.json").write_text("{壊れ")
    t.eq([(m["version"], m["compatible"], m["automodder"]) for m in p.installed()],
         [("9.0.0", False, None), ("0.10.0", True, "1.7.0"), ("0.1.0", True, "1.6.6")], "一覧（数値で比較して新しい順）")
    t.eq(p.current()["version"], "0.10.0", "current.json が無ければ使える最新（手で置いた版も。非互換の9.0.0は選ばない）")
    t.eq(p.status()["automodder"], "1.7.0", "AutoModder の版は使う版の plugin.json から")
    t.eq(p.use("0.1.0")["current"], "0.1.0", "旧版へ戻せる")
    t.eq((p.current()["version"], p.status()["automodder"]), ("0.1.0", "1.6.6"), "current.json に従う")
    t.eq(_code(p.use, "9.0.0"), "protocol", "非互換は選べない")
    t.eq(_code(p.use, "2.0.0"), "notInstalled", "別のプラグインの物は選べない")
    t.eq(_code(p.use, "../0.1.0"), "notInstalled", "パスのような値")
    (base / "current.json").write_text(json.dumps({"version": "3.3.3"}))
    t.eq(p.current()["version"], "0.10.0", "current.json の版が無ければ使える最新へ")


# ---------------------------------------------------------------- 実行
def test_run_input_validation(t):
    '''run は入力の検査（ファイル数・名前・Info.dat は先頭に1つ・文字列・曲の長さ・合計サイズ）を、プラグイン未導入でも先に行う'''
    p, d = _plugin()
    f = lambda n, x="{}": {"name": n, "text": x}
    cases = {
        "files無し": {},
        "files が文字": {"files": "x", "songLength": 10},
        "1個だけ": {"files": [f("Info.dat")], "songLength": 10},
        "33個": {"files": [f("Info.dat")] + [f(f"{i}.dat") for i in range(32)], "songLength": 10},
        "Info.dat が先頭でない": {"files": [f("ExpertStandard.dat"), f("Info.dat")], "songLength": 10},
        "Info.dat が2つ": {"files": [f("Info.dat"), f("info.dat")], "songLength": 10},
        "パス": {"files": [f("Info.dat"), f("../a.dat")], "songLength": 10},
        "拡張子": {"files": [f("Info.dat"), f("a.dat.exe")], "songLength": 10},
        "日本語": {"files": [f("Info.dat"), f("日本語.dat")], "songLength": 10},
        "文字でない": {"files": [f("Info.dat"), {"name": "a.dat", "text": 5}], "songLength": 10},
        "None": {"files": [f("Info.dat"), None], "songLength": 10},
        "曲の長さ無し": {"files": FILES},
        "曲の長さ0": {"files": FILES, "songLength": 0},
        "曲の長さが文字": {"files": FILES, "songLength": "60"},
        "曲の長さが真偽値": {"files": FILES, "songLength": True},
        "曲の長さが大きすぎる": {"files": FILES, "songLength": 86401},
        "本体がリスト": [],
    }
    for label, body in cases.items():
        t.eq(_code(p.run, body), "badInput", label)
    t.eq(_code(p.run, {"files": FILES, "songLength": 61.5}), "notInstalled", "正しい入力・未導入")
    orig = ap.MAX_INPUT
    try:
        ap.MAX_INPUT = 5
        t.eq(_code(p.run, {"files": [f("Info.dat", "123"), f("A.dat", "456")], "songLength": 10}), "tooLarge", "合計サイズ")
    finally:
        ap.MAX_INPUT = orig


def test_run_passes_input_and_filters_output(t):
    '''run は取り込み済みの exe だけを起動し、標準入力に protocol・info・difficulties・songLength を渡す。
    出力は知っている項目・形だけを通す（重さ・物の種類・信号機の値は決まった物だけ・文字は切り詰め・数は有限の物だけ）'''
    p, d = _plugin()
    p.install_zip(_zip(), "0.1.0")
    out = _ok_out(results=[
        {"name": "Vision Block", "characteristic": "Standard", "difficulty": "ExpertPlus", "difficultyRank": 9, "severity": "Warning",
         "checkType": "Vision", "description": "Notes must be placed with enough time to react" + "x" * 3000,
         "objects": [{"type": "note", "beat": 31.25, "x": 1, "y": 2, "color": 0, "seconds": 15.6, "d": 0, "evil": "<script>"},
                     {"type": "bogus", "beat": 1}, {"type": "wall", "beat": "1"}, {"type": "bomb", "beat": 2, "x": None, "color": 99}],
         "data": {"currentReactionTime": "125", "list": ["a", 5, None], "num": 3, "": "x", "obj": {"a": 1}}},
        {"name": "Song Name", "characteristic": None, "difficulty": None, "difficultyRank": None, "severity": "Passed",
         "checkType": "SongInfo", "description": "ok", "objects": [], "data": {}},
        {"name": "Evil", "severity": "Fatal", "objects": []},
        "not a dict",
    ], criteria={"info": {"SongName": "Success", "BPM": "Warning", "Bad": "Maybe", "a b": "Fail"},
                 "diff": {"Standard": {"ExpertPlus": {"difficultyRank": 9, "filename": "ExpertPlusStandard.dat", "notes": 198,
                                                      "skipped": None, "highest": "Warning", "crit": {"HotStart": "Success", "X": 1}},
                                       "Hard": {"difficultyRank": 5, "notes": None, "skipped": "notLoaded", "highest": None, "crit": None},
                                       "Easy": {"skipped": "<x>", "highest": "Purple", "error": True}},
                          "../x": {}}},
        errors=[{"stage": "difficulty", "type": "NullReferenceException", "message": "m" * 900, "where": "BLMapCheck.X()",
                 "characteristic": "Standard", "difficulty": "Easy"}, {"stage": "evil"}, 5])
    fake = _Fake(out)
    res = _with_run(fake, lambda: p.run({"files": FILES, "songLength": 61.5}))
    seen = fake.seen[0]
    t.eq(os.path.normcase(seen["cmd"][0]), os.path.normcase(str(d / "plugins" / "automodder" / "0.1.0" / "nlm-automodder.exe")), "取り込み済みのexeだけ")
    t.eq(seen["input"], {"protocol": 1, "info": {"filename": "Info.dat", "json": "{}"},
                         "difficulties": [{"filename": "ExpertStandard.dat", "json": "{}"}], "songLength": 61.5}, "標準入力の形")
    t.ok(not any(k.startswith(("_PYI_", "NLM_")) for k in seen["kw"]["env"]), "PyInstaller・NLM の環境変数は渡さない")
    t.eq((seen["kw"]["cwd"], seen["kw"]["timeout"]), (str(d / "plugins" / "automodder" / "0.1.0"), ap.RUN_TIMEOUT), "作業フォルダ・時間切れ")
    t.eq((res["ok"], res["version"], res["automodder"]["version"], res["elapsedMs"], res["songLength"], res["config"]),
         (True, "0.1.0", "1.6.6", 812, 61.5, "default"), "全体の値")
    t.eq(len(res["results"]), 2, "知らない重さ・辞書でない結果は捨てる")
    r = res["results"][0]
    t.eq(len(r["description"]), 2000, "文は切り詰め")
    t.eq(r["objects"], [{"type": "note", "beat": 31.25, "x": 1.0, "y": 2.0, "color": 0, "seconds": 15.6},
                        {"type": "bomb", "beat": 2.0, "x": None, "y": None, "color": None, "seconds": None}],
         "物は知っている種類・数の拍だけ（知らない項目は捨てる）")
    t.eq(r["data"], {"currentReactionTime": "125", "list": ["a", "5"], "num": "3"}, "値は文字（配列は文字の配列）だけ")
    t.eq((res["results"][1]["difficulty"], res["results"][1]["characteristic"]), (None, None), "曲の情報は難易度が null")
    t.eq(res["criteria"]["info"], {"SongName": "Success", "BPM": "Warning"}, "信号機の欄は決まった値だけ")
    dd = res["criteria"]["diff"]
    t.eq(list(dd.keys()), ["Standard"], "characteristic の名前は英数字だけ")
    t.eq(dd["Standard"]["ExpertPlus"], {"difficultyRank": 9, "notes": 198, "skipped": None, "highest": "Warning", "error": False,
                                        "crit": {"HotStart": "Success"}}, "難易度の欄")
    t.eq(dd["Standard"]["Hard"]["skipped"], "notLoaded", "skipped")
    t.eq((dd["Standard"]["Easy"]["skipped"], dd["Standard"]["Easy"]["highest"], dd["Standard"]["Easy"]["error"]), (None, None, True), "知らない値は捨てる")
    t.eq(len(res["errors"]), 2, "辞書でない errors は捨てる")
    t.eq((res["errors"][0]["difficulty"], len(res["errors"][0]["message"]), res["errors"][1]["stage"]), ("Easy", 500, None), "errors の値")
    t.eq(res["truncated"], False, "切り捨て無し")


def test_run_truncates_large_output(t):
    '''結果・物が多すぎる時は上限で切り、truncated で知らせる。出力の JSON 自体が大きすぎる時は tooLarge'''
    p, d = _plugin()
    p.install_zip(_zip(), "0.1.0")
    om, oo, ox = ap.MAX_RESULTS, ap.MAX_OBJS, ap.MAX_OUTPUT
    try:
        ap.MAX_RESULTS, ap.MAX_OBJS = 3, 2
        one = {"name": "X", "difficulty": "Expert", "severity": "Error", "objects": [{"type": "note", "beat": i} for i in range(5)]}
        res = _with_run(_Fake(_ok_out(results=[one] * 5)), lambda: p.run({"files": FILES, "songLength": 10}))
        t.eq((len(res["results"]), len(res["results"][0]["objects"]), res["truncated"]), (3, 2, True), "上限で切る")
        ap.MAX_OUTPUT = 50
        t.eq(_with_run(_Fake(_ok_out()), lambda: _code(p.run, {"files": FILES, "songLength": 10})), "tooLarge", "出力が大きすぎる")
    finally:
        ap.MAX_RESULTS, ap.MAX_OBJS, ap.MAX_OUTPUT = om, oo, ox


def test_run_failures(t):
    '''実行の失敗の形: ok:false は run（種類・文・場所を detail に）、JSON でない出力は run（標準エラーの終わり）、
    時間切れは timeout、起動できない時は run、出力の protocol 違いは run'''
    import subprocess
    p, d = _plugin()
    p.install_zip(_zip(), "0.1.0")

    def err(fake):
        try:
            _with_run(fake, lambda: p.run({"files": FILES, "songLength": 10}))
        except ap.PluginError as e:
            return e.code, e.detail
        return None
    t.eq(err(_Fake({"protocol": 1, "ok": False, "error": {"type": "InvalidDataException", "message": "map could not be read: ExpertStandard.dat",
                                                           "where": "NlmAutoModder.Program.CheckLoadable()"}}, rc=1)),
         ("run", "InvalidDataException: map could not be read: ExpertStandard.dat (NlmAutoModder.Program.CheckLoadable())"), "ok:false")
    t.eq(err(_Fake({"protocol": 1, "ok": False})), ("run", ""), "ok:false・error 無し")
    t.eq(err(_Fake(b"Unhandled exception", stderr=b"boom at X", rc=3)), ("run", "boom at X"), "JSON でない出力（標準エラー）")
    t.eq(err(_Fake(b"", rc=3)), ("run", "exit 3"), "何も出さない（終了コード）")
    t.eq(err(_Fake([1, 2])), ("run", "exit 0"), "辞書でない出力")
    t.eq(err(_Fake(_ok_out(protocol=2))), ("run", "protocol 2"), "出力の protocol 違い")
    t.eq(err(_Fake(None, exc=subprocess.TimeoutExpired("x", 1))), ("timeout", ""), "時間切れ")
    t.eq(err(_Fake(None, exc=OSError("cannot run"))), ("run", "cannot run"), "起動できない")


def test_run_one_at_a_time(t):
    '''実行は1つずつ（同時に頼まれても順番に動く）。取り込み中は実行を待たせる'''
    import threading
    import time
    p, d = _plugin()
    p.install_zip(_zip(), "0.1.0")
    state = {"now": 0, "max": 0}
    lock = threading.Lock()

    def slow(cmd, input=None, **kw):
        with lock:
            state["now"] += 1
            state["max"] = max(state["max"], state["now"])
        time.sleep(0.12)
        with lock:
            state["now"] -= 1
        return _Fake(_ok_out())(cmd, input=input)
    orig = ap.subprocess.run
    try:
        ap.subprocess.run = slow
        ths = [threading.Thread(target=p.run, args=({"files": FILES, "songLength": 10},)) for _ in range(3)]
        for th in ths:
            th.start()
        for th in ths:
            th.join(10)
        t.eq(state["max"], 1, "1つずつ")
        started = []
        with ap._Install():
            th = threading.Thread(target=lambda: started.append(p.run({"files": FILES, "songLength": 10})))
            th.start()
            time.sleep(0.2)
            t.eq(started, [], "取り込みが終わるまで待つ")
        th.join(5)
        t.eq(len(started), 1, "取り込みの後に動く")
    finally:
        ap.subprocess.run = orig


# ---------------------------------------------------------------- serve.py の /__automodder/*
def test_serve_endpoints_guarded(t):
    '''/__automodder/* の POST もヘッダーと合言葉が必須。知らない操作は404。status は未導入の形'''
    st, _, _ = H.req("POST", "/__automodder/status", body=b"{}")
    t.eq(st, 403, "ヘッダー無し")
    st, _, _ = H.req("POST", "/__automodder/status", headers={"X-NLM-Request": "1"}, body=b"{}", token=False)
    t.eq(st, 403, "合言葉無し")
    st, obj = H.post_json("/__automodder/status", {})
    t.eq((st, obj["ok"], obj["current"], obj["installed"], obj["protocol"]), (200, True, None, [], ap.PROTOCOL), "未導入")
    t.eq(obj["repo"], "https://github.com/Oz-Co-two/nlm-automodder", "配布元")
    st, obj = H.post_json("/__automodder/bogus", {})
    t.eq(st, 404, "不明")
    for v in ("9.9.9", "../../x", "", None):
        st, obj = H.post_json("/__automodder/use", {"version": v})
        t.eq((st, obj.get("ok"), obj.get("error")), (200, False, "notInstalled"), f"use version={v!r}")
    st, obj = H.post_json("/__automodder/run", {"files": FILES, "songLength": 60})
    t.eq((obj.get("ok"), obj.get("error")), (False, "notInstalled"), "未導入の run")
    st, _, body = H.req("POST", "/__automodder/run", headers={"X-NLM-Request": "1", "Content-Type": "application/json"}, body=b"{not json")
    t.eq((st, json.loads(body).get("error")), (200, "badInput"), "JSON でない本体")


def test_serve_run_with_installed_plugin(t):
    '''取り込み済みなら /__automodder/run がプラグインを動かして、整えた結果を返す（exe は差し替え）'''
    s = H.server()
    p = ap.AutoModderPlugin(s.data_dir)
    p.install_zip(_zip(), "0.1.0")
    try:
        out = _ok_out(results=[{"name": "Hot Start", "characteristic": "Standard", "difficulty": "Expert", "severity": "Error",
                                "checkType": "Duration", "description": "There must be at least 1.5 seconds",
                                "objects": [{"type": "note", "beat": 1, "x": 1, "y": 0, "color": 0, "seconds": 0.5}], "data": {}}])
        fake = _Fake(out)
        st, obj = _with_run(fake, lambda: H.post_json("/__automodder/run", {"files": FILES, "songLength": 16.25, "evil": "x"}))
        t.eq((st, obj["ok"], obj["version"], len(obj["results"])), (200, True, "0.1.0", 1), "結果")
        t.eq(obj["results"][0]["objects"][0]["beat"], 1.0, "拍")
        t.eq(fake.seen[0]["input"]["songLength"], 16.25, "曲の長さを渡す")
        st, obj = H.post_json("/__automodder/status", {})
        t.eq((obj["current"], obj["automodder"]), ("0.1.0", "1.6.6"), "status は取り込み済み")
    finally:
        import shutil
        shutil.rmtree(os.path.join(s.data_dir, "plugins", "automodder"), ignore_errors=True)


# ---------------------------------------------------------------- 本物（手元に配布の zip がある時だけ）
def test_real_plugin_if_available(t):
    '''NLM_AUTOMODDER_ZIP（配布の zip。隣に manifest.json）がある時だけ: manifest と照合して取り込み、素材の譜面（tools/fixtures/rich_map）を
    本物の AutoModder で確かめる。Hard はノーツ20個未満で確かめない・Expert は Hot Start のエラーが出る'''
    zp = os.environ.get("NLM_AUTOMODDER_ZIP")
    if not zp or not os.path.isfile(zp):
        t.skip("NLM_AUTOMODDER_ZIP が無い（本物の配布の zip がある時だけ動かす）")
    data = Path(zp).read_bytes()
    man = ap.AutoModderPlugin._check_manifest((Path(zp).parent / "manifest.json").read_text(encoding="utf-8"))
    t.eq((len(data), hashlib.sha256(data).hexdigest()), (man["zip"]["size"], man["zip"]["sha256"]), "zip は manifest と同じ")
    p, d = _plugin()
    p.install_zip(data, man["version"])
    fx = H.ROOT / "tools" / "fixtures" / "rich_map"
    files = [{"name": n, "text": (fx / n).read_text(encoding="utf-8")} for n in ("Info.dat", "HardStandard.dat", "ExpertStandard.dat")]
    res = p.run({"files": files, "songLength": 16.0})
    t.eq((res["ok"], res["automodder"]["version"], res["errors"]), (True, man.get("automodder"), []), "動いた")
    dd = res["criteria"]["diff"]["Standard"]
    t.eq((dd["Hard"]["skipped"], dd["Expert"]["skipped"]), ("tooFewNotes", None), "ノーツ20個未満は確かめない")
    hot = [r for r in res["results"] if r["difficulty"] == "Expert" and r["name"] == "Hot Start" and r["severity"] == "Error"]
    t.ok(hot and hot[0]["objects"] and hot[0]["objects"][0]["beat"] == 1.0, f"Hot Start のエラー（拍1）: {hot[:1]}")
    t.ok(any(r["difficulty"] is None and r["name"] == "BPM" for r in res["results"]), "曲の情報の結果もある")


def test_check_newer_and_notes(t):
    '''check は取り込み済みのどの版より新しいかと、その間の版の更新内容（新しい順・形と長さを整えた物）を返す（起動時の更新の知らせ用）'''
    p, d = _plugin()
    p.install_zip(_zip(ver="0.1.0"), "0.1.0")
    notes = [{"version": "0.2.0", "ja": ["二", "x" * 400], "en": ["two", None]},
             {"version": "0.1.0", "ja": ["一"], "en": ["one"]}, {"version": "v0.3.0", "ja": ["版が不正"]}]
    orig = ap.AutoModderPlugin._get
    try:
        ap.AutoModderPlugin._get = staticmethod(lambda url, limit: json.dumps(_manifest(ver="0.2.0", notes=notes)).encode())
        L = p.check()["latest"]
        t.eq((L["version"], L["newer"], L["installed"]), ("0.2.0", True, False), "新しい版がある")
        t.eq(L["notes"], [{"version": "0.2.0", "ja": ["二", "x" * 300], "en": ["two"]}], "取り込み済みより新しい版だけ・整えた形")
        ap.AutoModderPlugin._get = staticmethod(lambda url, limit: json.dumps(_manifest(ver="0.1.0", notes=notes)).encode())
        L = p.check()["latest"]
        t.eq((L["newer"], L["notes"]), (False, []), "最新を取り込み済み")
    finally:
        ap.AutoModderPlugin._get = orig


def test_open_notes_url_fixed(t):
    '''「詳しく見る」はその版のリリースのページだけを開く（版の形でなければリリースの一覧）'''
    import webbrowser
    p, _ = _plugin()
    opened, orig = [], webbrowser.open
    try:
        webbrowser.open = lambda url: opened.append(url)
        for v in ("0.1.0", "x", None):
            p.open_notes(v)
    finally:
        webbrowser.open = orig
    base = "https://github.com/Oz-Co-two/nlm-automodder/releases"
    t.eq(opened, [base + "/tag/v0.1.0", base, base], "開く先は固定")

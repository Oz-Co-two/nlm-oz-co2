"""rating_plugin.py（ネットに繋がずに確かめられる部分: manifest検査・SHA-256照合・zip slip・PROTOCOL・版の選択）"""
import hashlib
import io
import json
import sys
import tempfile
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import unitpy_helpers as H

sys.path.insert(0, str(H.ROOT))
import rating_plugin as rp  # noqa: E402


def _manifest(ver="0.1.0", proto=None, sha=None, size=100, **over):
    m = {"name": "nlm-rating", "version": ver, "platform": rp.PLATFORM,
         "protocol": rp.PROTOCOL if proto is None else proto,
         "zip": {"name": f"nlm-rating-{ver}-{rp.PLATFORM}.zip", "sha256": sha or "a" * 64, "size": size}}
    m.update(over)
    return m


def _zip(ver="0.1.0", proto=None, extra=None, with_exe=True):
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w") as z:
        z.writestr("plugin.json", json.dumps({"version": ver, "protocol": rp.PROTOCOL if proto is None else proto}))
        if with_exe:
            z.writestr("nlm-rating.exe", b"MZ-dummy")
        for k, v in (extra or {}).items():
            zi = zipfile.ZipInfo("tmp")
            zi.filename = k   # ZipInfo の初期化は \ を / に直してしまうので、後から生の名前を入れる
            z.writestr(zi, v)
    return b.getvalue()


def _plugin(tmp=None):
    d = tmp or tempfile.mkdtemp(prefix="nlm_unitpy_rp_")
    return rp.RatingPlugin(d), Path(d)


def _code(fn, *a):
    try:
        fn(*a)
    except rp.PluginError as e:
        return e.code
    return None


def test_manifest_valid(t):
    '''正しい manifest は通る'''
    m = rp.RatingPlugin._check_manifest(json.dumps(_manifest()))
    t.eq(m["version"], "0.1.0", "version")


def test_manifest_rejects_bad(t):
    '''不正な manifest（名前・版・platform・zip名・sha256・サイズ・JSON）は badManifest'''
    bad = {
        "name違い": _manifest(name="other"),
        "版が不正": _manifest(ver="1.2"),
        "版にパス": _manifest(ver="1.2.3/../x"),
        "platform違い": _manifest(platform="linux-x64"),
        "protocolが文字列": _manifest(proto="1"),
        "zip名が版と不一致": _manifest(zip={"name": "evil.zip", "sha256": "a" * 64, "size": 1}),
        "zip名にパス": _manifest(zip={"name": "../nlm-rating-0.1.0-win-x64.zip", "sha256": "a" * 64, "size": 1}),
        "sha256が短い": _manifest(sha="abc"),
        "sha256が大文字": _manifest(sha="A" * 64),
        "サイズ0": _manifest(size=0),
        "サイズ過大": _manifest(size=rp.MAX_ZIP + 1),
    }
    for label, m in bad.items():
        t.eq(_code(rp.RatingPlugin._check_manifest, json.dumps(m)), "badManifest", label)
    for raw in ("{壊れ", "[]", "null", "{}"):
        t.eq(_code(rp.RatingPlugin._check_manifest, raw), "badManifest", raw)


def test_install_rejects_hash_and_size_mismatch(t):
    '''install は zip の SHA-256 またはサイズが manifest と違えば hash で拒否し、何も展開しない'''
    p, d = _plugin()
    data = _zip()
    sha = hashlib.sha256(data).hexdigest()
    orig = rp.RatingPlugin._get
    try:
        for label, m in (("sha違い", _manifest(sha="b" * 64, size=len(data))),
                         ("サイズ違い", _manifest(sha=sha, size=len(data) + 1))):
            raw = json.dumps(m).encode()
            rp.RatingPlugin._get = staticmethod(lambda url, limit, raw=raw: raw if url == rp.MANIFEST_URL else data)
            t.eq(_code(p.install), "hash", label)
            t.eq(p.installed(), [], f"{label}: 取り込まれていない")
            t.ok(not (d / "plugins" / "rating" / "current.json").exists(), f"{label}: current.json無し")
    finally:
        rp.RatingPlugin._get = orig


def test_install_ok_and_urls_fixed(t):
    '''照合が合えば展開して現在の版にする。取得先は固定のURLだけ（manifest→公式のzip）'''
    p, d = _plugin()
    data = _zip()
    raw = json.dumps(_manifest(sha=hashlib.sha256(data).hexdigest(), size=len(data))).encode()
    urls = []
    orig = rp.RatingPlugin._get
    try:
        def fake(url, limit):
            urls.append(url)
            return raw if url == rp.MANIFEST_URL else data
        rp.RatingPlugin._get = staticmethod(fake)
        st = p.install()
    finally:
        rp.RatingPlugin._get = orig
    t.eq(st["current"], "0.1.0", "使う版")
    t.eq(urls[0], rp.MANIFEST_URL, "最初はmanifest")
    t.eq(urls[1], "https://github.com/Oz-Co-two/nlm-rating/releases/download/v0.1.0/nlm-rating-0.1.0-win-x64.zip", "zipの取得先")
    t.ok(all(u.startswith("https://github.com/Oz-Co-two/nlm-rating/") for u in urls), "取得先は固定")
    t.ok((d / "plugins" / "rating" / "0.1.0" / "nlm-rating.exe").is_file(), "exeが展開される")


def test_install_rejects_new_protocol(t):
    '''NLMの知らない protocol のプラグインは取り込まない（zipの取得もしない）'''
    p, d = _plugin()
    raw = json.dumps(_manifest(proto=rp.PROTOCOL + 1)).encode()
    urls = []
    orig = rp.RatingPlugin._get
    try:
        rp.RatingPlugin._get = staticmethod(lambda url, limit: (urls.append(url), raw)[1])
        t.eq(_code(p.install), "protocol", "拒否")
    finally:
        rp.RatingPlugin._get = orig
    t.eq(urls, [rp.MANIFEST_URL], "zipは取りに行かない")


def test_install_zip_slip(t):
    '''zip内の ..・絶対パス・ドライブ名・. を含む名前は badZip で拒否し、外へ書かない（\\はWindowsのzipfileが読込時に/へ直すので対象外）'''
    for name in ("../evil.txt", "a/../../evil.txt", "/abs.txt", "C:evil.txt", "./x.txt"):
        p, d = _plugin()
        data = _zip(extra={name: "x"})
        t.eq(_code(p.install_zip, data, "0.1.0"), "badZip", name)
        t.eq(p.installed(), [], f"{name}: 取り込まれない")
        t.ok(not (d / "evil.txt").exists() and not (d.parent / "evil.txt").exists(), f"{name}: 外に書かれていない")


def test_install_zip_checks_meta(t):
    '''plugin.json の版・protocol が合わない／exeが無い zip は badZip'''
    p, d = _plugin()
    t.eq(_code(p.install_zip, _zip(ver="0.2.0"), "0.1.0"), "badZip", "版が違う")
    t.eq(_code(p.install_zip, _zip(proto=rp.PROTOCOL + 1), "0.1.0"), "badZip", "protocolが違う")
    t.eq(_code(p.install_zip, _zip(with_exe=False), "0.1.0"), "badZip", "exe無し")
    t.eq(_code(p.install_zip, b"not a zip", "0.1.0"), "badZip", "zipでない")
    t.eq(p.installed(), [], "どれも取り込まれていない")
    import os
    t.ok(not any(n.startswith(".tmp-") for n in os.listdir(p.root)), "一時フォルダが残らない")


def test_install_zip_replaces_old(t):
    '''同じ版を取り込み直すと入れ替わる（古いファイルは残らない）'''
    p, d = _plugin()
    p.install_zip(_zip(extra={"old.txt": "1"}), "0.1.0")
    p.install_zip(_zip(extra={"new.txt": "1"}), "0.1.0")
    base = d / "plugins" / "rating" / "0.1.0"
    t.ok((base / "new.txt").exists() and not (base / "old.txt").exists(), "入れ替え")


def test_installed_and_current_selection(t):
    '''installed は新しい順・protocol違いは compatible=false。current は current.json の版→無ければ使える最新。use は未導入/非互換を拒否'''
    p, d = _plugin()
    p.install_zip(_zip(ver="0.1.0"), "0.1.0")
    p.install_zip(_zip(ver="0.10.0"), "0.10.0")
    # protocolが違う版を直接置く
    bad = d / "plugins" / "rating" / "9.0.0"
    bad.mkdir(parents=True)
    (bad / "plugin.json").write_text(json.dumps({"version": "9.0.0", "protocol": rp.PROTOCOL + 5}))
    (bad / "nlm-rating.exe").write_bytes(b"x")
    # 版名として不正なフォルダや壊れたplugin.jsonは無視
    (d / "plugins" / "rating" / "junk").mkdir()
    broken = d / "plugins" / "rating" / "1.0.0"
    broken.mkdir()
    (broken / "plugin.json").write_text("{壊れ")
    inst = p.installed()
    t.eq([(m["version"], m["compatible"]) for m in inst], [("9.0.0", False), ("0.10.0", True), ("0.1.0", True)], "一覧(数値で比較して新しい順)")
    t.eq(p.current()["version"], "0.10.0", "使える最新（非互換の9.0.0は選ばない）")
    t.eq(p.use("0.1.0")["current"], "0.1.0", "旧版へ戻せる")
    t.eq(p.current()["version"], "0.1.0", "current.json に従う")
    t.eq(_code(p.use, "9.0.0"), "protocol", "非互換は選べない")
    t.eq(_code(p.use, "7.7.7"), "notInstalled", "未導入")
    t.eq(_code(p.use, "../0.1.0"), "notInstalled", "パスのような値")
    (d / "plugins" / "rating" / "current.json").write_text(json.dumps({"version": "3.3.3"}))
    t.eq(p.current()["version"], "0.10.0", "current.json の版が無ければ最新へ")


def test_measure_input_limits(t):
    '''measure は入力の検査（ファイル数・名前の形・文字列・合計サイズ）を、プラグイン未導入でも先に行う'''
    p, d = _plugin()
    f = lambda n: {"name": n, "text": "{}"}
    t.eq(_code(p.measure, {}), "badInput", "files無し")
    t.eq(_code(p.measure, {"files": [f("Info.dat")] * 33}), "badInput", "33個")
    t.eq(_code(p.measure, {"files": [f("Info.dat"), f("a b-c_1.dat")]}), "notInstalled", "許される名前")
    for bad in ("../a.dat", "a/b.dat", "a\\b.dat", "a.dat.exe", ".dat", "x" * 65 + ".dat", "日本語.dat"):
        t.eq(_code(p.measure, {"files": [f("Info.dat"), f(bad)]}), "badInput", bad)
    t.eq(_code(p.measure, {"files": [f("Info.dat"), None]}), "badInput", "None")
    orig = rp.MAX_INPUT
    try:
        rp.MAX_INPUT = 5
        t.eq(_code(p.measure, {"files": [{"name": "Info.dat", "text": "123"}, {"name": "A.dat", "text": "456"}]}), "tooLarge", "合計サイズ")
    finally:
        rp.MAX_INPUT = orig


def test_measure_filters_plugin_output(t):
    '''measure はプラグイン出力のうち数値と既知の文字列だけを通す（偽の実行ファイルで確認・Windowsのみ）'''
    import os
    import shutil
    import sys as _s
    if _s.platform != "win32":
        t.skip("Windows専用")
    p, d = _plugin()
    p.install_zip(_zip(), "0.1.0")
    # 本物のexeの代わりに、固定のJSONを返す小さなexeが要る。python.exe をコピーしても引数なしでは動かないので、
    # subprocess.run を差し替えて「プラグインの標準出力」を再現する
    out = {"ok": True, "elapsedMs": 12.9, "results": [
        {"characteristic": "Standard" * 10, "difficulty": "Expert", "notes": 100, "skipped": "<script>",
         "ratings": {"none": {"stars": 5.5, "pass": 1, "tech": "x", "acc": 2, "predictedAcc": 0.9, "evil": 9}, "SS": "bad"}}]}
    seen = {}

    class R:
        returncode = 0
        stdout = json.dumps(out).encode()
        stderr = b""

    def fake_run(cmd, input=None, **kw):
        seen["input"] = json.loads(input)
        seen["cmd"] = cmd
        return R()
    orig = rp.subprocess.run
    try:
        rp.subprocess.run = fake_run
        res = p.measure({"files": [{"name": "Info.dat", "text": "{}"}, {"name": "A.dat", "text": "{}"}], "modifiers": ["none", "SS", "BAD"]})
    finally:
        rp.subprocess.run = orig
    t.eq(seen["input"]["modifiers"], ["none", "SS"], "知らない修飾子は渡さない")
    t.eq(os.path.normcase(seen["cmd"][0]), os.path.normcase(str(d / "plugins" / "rating" / "0.1.0" / "nlm-rating.exe")), "導入済みのexeだけを起動")
    r = res["results"][0]
    t.eq(len(r["characteristic"]), 32, "文字列は切り詰め")
    t.eq(r["skipped"], None, "知らない skipped は捨てる")
    t.eq(r["ratings"]["none"], {"stars": 5.5, "pass": 1.0, "acc": 2.0, "predictedAcc": 0.9}, "数値だけ・知らないキーと非数値は捨てる")
    t.eq(r["ratings"]["SS"], None, "辞書でない値はNone")
    t.eq(res["elapsedMs"], 12, "elapsedMs は整数")

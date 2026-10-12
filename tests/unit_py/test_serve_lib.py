"""serve.py の MEDIA ライブラリの入口（/__lib/*）と、app.py の Api のフォルダ・プレイ記録の選択（2026-10-12）。
フォルダの記録はダイアログ（Api.lib_pick_folder）からだけ増える＝ここでは serve.LIBRARY.approve_dir を直接呼んで「選ばれた」ことにする。
全曲データ・BeatSaver・プラグインはネットや実行ファイルに頼らないよう、それぞれの口を差し替えて確かめる"""
import json
import os
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import unitpy_helpers as H
import test_media_library as TML   # 一時のライブラリ（譜面 v2/v3/v4 等）を作る部品を使う


def _lib():
    """(serve, 記録の id, ライブラリの根, 素材の情報)。一時フォルダのライブラリを「ダイアログで選んだ」ことにして記録する"""
    s = H.server()
    base = Path(tempfile.mkdtemp(prefix="nlm_unitpy_lib_"))
    root, fx = TML._make_lib(base)
    lid = s.serve.LIBRARY.approve_dir(str(root))["id"]
    return s.serve, lid, root, fx


def _scan(lid, timeout=30):
    maps, nxt, t0 = [], 0, time.time()
    while True:
        st, r = H.post_json("/__lib/scan", {"id": lid, "from": nxt})
        assert st == 200 and r, (st, r)
        maps += r["maps"]
        nxt = r["next"]
        if r["done"]:
            return maps, r
        if time.time() - t0 > timeout:
            raise AssertionError("走査が終わらない")
        time.sleep(0.02)


def _post_raw(path, obj):
    return H.req("POST", path, headers={"Content-Type": "application/json", "X-NLM-Request": "1"},
                 body=json.dumps(obj).encode("utf-8"))


def test_lib_list_scan_file(t):
    '''記録したライブラリが list に出て、scan で曲が返り、file でその中のファイルだけを読める'''
    serve, lid, root, fx = _lib()
    st, r = H.post_json("/__lib/list", {})
    t.eq(st, 200, "list の応答")
    t.ok(any(l["id"] == lid and l["state"] == "ok" for l in r["libs"]), "記録したライブラリが出る")
    t.ok("details" in r and "playdata" in r, "全曲データ・プレイ記録の状態も返す")
    maps, last = _scan(lid)
    m = next(x for x in maps if x["rel"] == "1a2b (Song V2 - Mapper)")
    t.eq(m["name"], "Song V2", "曲の情報")
    st, hd, body = _post_raw("/__lib/file", {"id": lid, "rel": m["rel"], "name": "cover.jpg"})
    t.eq(st, 200, "カバーを読める")
    t.eq(body, (fx["v2"] / "cover.jpg").read_bytes(), "中身はそのまま")
    t.eq(hd.get("Content-Type"), "image/jpeg", "種類")
    t.eq(hd.get("X-NLM-File"), "1", "ファイルの中身には目印のヘッダー（失敗の {ok:false} と見分ける）")
    st, hd, body = _post_raw("/__lib/file", {"id": lid, "rel": m["rel"], "name": "ExpertStandard.dat"})
    t.eq((st, body), (200, (fx["v2"] / "ExpertStandard.dat").read_bytes()), "譜面ファイルも読める")


def test_lib_file_rejects_outside_and_bad_kinds(t):
    '''file はライブラリの根の外・知らない種類・空の名前を返さない（.. ・ドライブ名・区切り文字・NUL）'''
    serve, lid, root, fx = _lib()
    (root.parent / "secret.dat").write_text("{}", encoding="utf-8")
    (fx["v2"] / "evil.exe").write_bytes(b"MZ")
    for rel, name in [("..", "secret.dat"), ("1a2b (Song V2 - Mapper)/..", "../secret.dat"), ("C:\\Windows", "win.ini"),
                      ("1a2b (Song V2 - Mapper)", "..\\..\\secret.dat"), ("1a2b (Song V2 - Mapper)", "evil.exe"),
                      ("1a2b (Song V2 - Mapper)", "a\x00.dat"), ("", "")]:
        st, r = H.post_json("/__lib/file", {"id": lid, "rel": rel, "name": name})
        t.eq(st, 200, f"応答: {rel!r} {name!r}")
        t.ok(r and r.get("ok") is False and r.get("error") in ("bad-path", "not-allowed", "not-found"), f"断る: {rel!r} {name!r} → {r}")
    st, r = H.post_json("/__lib/file", {"id": "nope", "rel": "x", "name": "Info.dat"})
    t.eq(r, {"ok": False, "error": "unknown-lib"}, "記録に無い id")
    st, r = H.post_json("/__lib/file", {"id": lid, "rel": ["x"], "name": {"a": 1}})
    t.eq(r.get("ok"), False, "文字列でない値は使わない")


def test_lib_no_way_to_add_from_js(t):
    '''JS からフォルダを増やす口は無い（パスを渡しても記録されない）。ヘッダー・合言葉が無い要求は断る'''
    serve, lid, root, fx = _lib()
    other = Path(tempfile.mkdtemp(prefix="nlm_unitpy_lib_other_"))
    before = [l["id"] for l in serve.LIBRARY.list()]
    for path in ("/__lib/add", "/__lib/approve", "/__lib/approve_dir"):
        st, r = H.post_json(path, {"path": str(other)})
        t.eq(st, 404, f"{path} は無い")
    st, r = H.post_json("/__lib/scan", {"id": lid, "path": str(other)})
    t.eq([l["id"] for l in serve.LIBRARY.list()], before, "パスを渡しても記録は増えない")
    st, hd, body = H.req("POST", "/__lib/list", headers={"Content-Type": "application/json"}, body=b"{}")
    t.eq(st, 403, "X-NLM-Request が無い")
    st, hd, body = H.req("POST", "/__lib/list", headers={"Content-Type": "application/json", "X-NLM-Request": "1"}, body=b"{}", token=False)
    t.eq(st, 403, "合言葉が無い")


def test_lib_remove_and_open(t):
    '''remove で記録から外れる（フォルダの中身は消さない）。open は根の中の実在するフォルダだけを開く'''
    serve, lid, root, fx = _lib()
    opened = []
    orig = serve.LIBRARY.opener
    serve.LIBRARY.opener = opened.append
    try:
        st, r = H.post_json("/__lib/open", {"id": lid, "rel": "1a2b (Song V2 - Mapper)"})
        t.eq(r, {"ok": True}, "開ける")
        t.eq([os.path.normcase(p) for p in opened], [os.path.normcase(str(fx["v2"]))], "その譜面フォルダを開く")
        st, r = H.post_json("/__lib/open", {"id": lid, "rel": ".."})
        t.eq(r.get("ok"), False, "根の外は開かない")
        t.eq(len(opened), 1, "外は開いていない")
    finally:
        serve.LIBRARY.opener = orig
    st, r = H.post_json("/__lib/remove", {"id": lid})
    t.eq(r, {"ok": True}, "外せる")
    st, r = H.post_json("/__lib/list", {})
    t.ok(all(l["id"] != lid for l in r["libs"]), "list から消える")
    t.ok((fx["v2"] / "Info.dat").is_file(), "フォルダの中身は消さない")


def test_lib_extra_prefers_matching_version(t):
    '''extra の net: 版が一致する（ハッシュで当たった）物を優先し、全曲データ＞BeatSaver の記録。どちらにも無ければ src:none
    （BeatSaver にも無かった曲は bsMissAt 付き）。net:false なら全曲データを使わない。プレイ記録・NLM推定の★も載る'''
    serve, lid, root, fx = _lib()
    maps, _ = _scan(lid)
    by = {m["rel"]: m for m in maps}
    v2, v3 = by["1a2b (Song V2 - Mapper)"], next(m for m in maps if m["fmt"] == 2 and m["rel"] != "1a2b (Song V2 - Mapper)" and m.get("hash"))
    dump_key = {"src": "dump", "match": "key", "key": "1a2b", "uploaded": 1}
    bs_hash = {"src": "beatsaver", "match": "hash", "key": "1a2b", "uploaded": 2}
    looks = {}

    def fake_lookup(hash=None, key=None):
        looks[hash] = key
        return dump_key if hash == v2["hash"] else None

    def fake_cached(h):
        if h == v2["hash"]:
            return bs_hash
        if h == v3["hash"]:
            return {"src": "none", "bsMissAt": 123}
        return None
    o_lookup, o_cached = serve.SONG_DETAILS.lookup, serve.BEATSAVER.cached
    serve.SONG_DETAILS.lookup, serve.BEATSAVER.cached = fake_lookup, fake_cached
    try:
        serve.RATING_CACHE.get = (lambda orig: (lambda h, v: {"Standard/Expert": {"stars": 7.5}} if h == v2["hash"] else orig(h, v)))(serve.RATING_CACHE.get)
        st, r = H.post_json("/__lib/extra", {"id": lid})
        ex = r["extra"]
        t.eq(ex[v2["rel"]]["net"], bs_hash, "ハッシュで当たった BeatSaver の記録を、キーだけの全曲データより優先")
        t.eq(ex[v3["rel"]]["net"], {"src": "none", "bsMissAt": 123}, "BeatSaver にも無い")
        others = [m for m in maps if m["rel"] not in (v2["rel"], v3["rel"])]
        t.ok(all(ex[m["rel"]]["net"] == {"src": "none"} for m in others), "どちらにも無い曲は src:none")
        serve.BEATSAVER.cached = lambda h: None
        st, r = H.post_json("/__lib/extra", {"id": lid})
        t.eq(r["extra"][v2["rel"]]["net"], dump_key, "BeatSaver の記録が無ければ全曲データ（キーだけでも）")
        looks.clear()
        st, r = H.post_json("/__lib/extra", {"id": lid, "net": False})
        t.eq((looks, r["extra"][v2["rel"]]["net"]), ({}, {"src": "none"}), "net:false なら全曲データを見ない")
    finally:
        serve.SONG_DETAILS.lookup, serve.BEATSAVER.cached = o_lookup, o_cached
        try:
            del serve.RATING_CACHE.get
        except AttributeError:
            pass


def test_lib_beatsaver_one_map(t):
    '''beatsaver はその1曲のハッシュだけを問い合わせ、結果の net を返す。失敗（busy 等）はそのまま伝える。走査に無い曲は断る'''
    serve, lid, root, fx = _lib()
    maps, _ = _scan(lid)
    m = next(x for x in maps if x["rel"] == "1a2b (Song V2 - Mapper)")
    asked = []
    store = {}

    def fake_lookup(h):
        asked.append(h)
        store[h] = {"src": "beatsaver", "match": "hash", "key": "1a2b", "uploaded": 5}
        return store[h]
    o_lookup, o_cached = serve.BEATSAVER.lookup, serve.BEATSAVER.cached
    serve.BEATSAVER.lookup, serve.BEATSAVER.cached = fake_lookup, lambda h: store.get(h)
    try:
        st, r = H.post_json("/__lib/beatsaver", {"id": lid, "rel": m["rel"], "net": False})
        t.eq(asked, [m["hash"]], "その1曲のハッシュだけ")
        t.eq(r, {"ok": True, "net": store[m["hash"]]}, "net を返す")
        serve.BEATSAVER.lookup = lambda h: {"error": "busy", "retryAfter": 30}
        st, r = H.post_json("/__lib/beatsaver", {"id": lid, "rel": m["rel"]})
        t.eq(r, {"ok": False, "error": "busy", "retryAfter": 30}, "混んでいる時はそのまま伝える")
        st, r = H.post_json("/__lib/beatsaver", {"id": lid, "rel": "no such map"})
        t.eq(r, {"ok": False, "error": "not-found"}, "走査に無い曲")
    finally:
        serve.BEATSAVER.lookup, serve.BEATSAVER.cached = o_lookup, o_cached


def test_lib_rate_uses_plugin_once(t):
    '''rate はその曲の Info.dat と譜面をプラグインへ渡して★を返し、ハッシュ＋プラグインの版ごとに記録する（2回目はプラグインを動かさない）。
    プラグインが無ければ notInstalled'''
    import rating_plugin as rp
    import test_rating_plugin as TRP
    serve, lid, root, fx = _lib()
    maps, _ = _scan(lid)
    m = next(x for x in maps if x["rel"] == "1a2b (Song V2 - Mapper)")
    st, r = H.post_json("/__lib/rate", {"id": lid, "rel": m["rel"]})
    if r.get("error") == "notInstalled":
        t.ok(True, "プラグインが無ければ notInstalled")
    rp.RatingPlugin(serve.DATA_DIR).install_zip(TRP._zip(ver="9.9.9"), "9.9.9")
    rp.RatingPlugin(serve.DATA_DIR)._write_current("9.9.9")
    runs = []

    class R:
        returncode = 0
        stderr = b""
        stdout = json.dumps({"ok": True, "results": [
            {"characteristic": "Standard", "difficulty": "Expert", "notes": 3, "ratings": {"none": {"stars": 7.126}}},
            {"characteristic": "Standard", "difficulty": "ExpertPlus", "notes": 16, "skipped": "tooFewNotes", "ratings": {}}]}).encode()

    def fake_run(cmd, input=None, **kw):
        runs.append(json.loads(input))
        return R()
    orig = rp.subprocess.run
    rp.subprocess.run = fake_run
    try:
        st, r = H.post_json("/__lib/rate", {"id": lid, "rel": m["rel"], "parallel": 4})
        want = {"Standard/Expert": {"stars": 7.13}, "Standard/ExpertPlus": {"skipped": "tooFewNotes"}}
        t.eq(r, {"ok": True, "est": {"version": "9.9.9", "diffs": want}}, "★と飛ばした理由")
        t.eq(len(runs), 1, "プラグインを1回動かした")
        t.eq([f["name"] for f in runs[0]["files"]][0], "Info.dat", "Info.dat と譜面を渡す")
        t.eq(runs[0]["modifiers"], ["none"], "速度の変更なしだけ")
        st, r = H.post_json("/__lib/rate", {"id": lid, "rel": m["rel"]})
        t.eq((len(runs), r["est"]["diffs"]), (1, want), "2回目は記録から（プラグインを動かさない）")
        st, r = H.post_json("/__lib/extra", {"id": lid})
        t.eq(r["extra"][m["rel"]].get("est"), {"version": "9.9.9", "diffs": want}, "extra にも載る")
    finally:
        rp.subprocess.run = orig
        import shutil
        shutil.rmtree(os.path.join(serve.DATA_DIR, "plugins"), ignore_errors=True)


def test_lib_no_net_for_tests(t):
    '''NLM_NO_NET=1（自動テストのサーバー）では、全曲データ・BeatSaver の取得がネットへ出ない（通信の失敗として扱われる）'''
    serve = H.server().serve
    t.ok(serve._NET is serve._no_net, "テストのサーバーはネットへ出ない設定")
    t.ok(serve.SONG_DETAILS._open is serve._no_net and serve.BEATSAVER._open is serve._no_net, "全曲データ・BeatSaver の通信の口")
    try:
        serve._no_net(None)
        t.ok(False, "通信の失敗にならない")
    except Exception as e:
        t.ok("NLM_NO_NET" in str(e), f"通信の失敗: {e}")
    import song_details
    sd = song_details.SongDetails(H.server().data_dir + "/no_net_check", opener=serve._no_net)
    r = sd.update()
    t.eq((r["did"], r["state"]), ("failed", "error"), "取得は失敗として記録される（前のデータがあればそれを使う）")


def test_lib_details_and_playdata_status(t):
    '''details は全曲データの状態（update は song_details の決まりに任せる）、playdata はプレイ記録の状態と既定の場所への戻し'''
    serve, lid, root, fx = _lib()
    called = []
    orig = serve.SONG_DETAILS.update
    serve.SONG_DETAILS.update = lambda: called.append(1) or {"state": "ok", "did": "throttled"}
    try:
        st, r = H.post_json("/__lib/details", {"act": "status"})
        t.ok(r.get("state") in ("none", "ok", "error", "unsupported"), f"状態: {r}")
        t.eq(called, [], "status では取得しない")
        st, r = H.post_json("/__lib/details", {"act": "update"})
        t.eq((called, r.get("did")), ([1], "throttled"), "update で取得を頼む")
    finally:
        serve.SONG_DETAILS.update = orig
    st, r = H.post_json("/__lib/playdata", {"act": "reset"})
    t.eq((r.get("mode"), r.get("state")), ("auto", "missing"), "既定の場所（テストでは無い場所）")


def test_api_lib_pick_folder_and_playdata(t):
    '''Api.lib_pick_folder はダイアログで選ばれたフォルダだけをライブラリに記録する（書き出し先の許可にはしない）。
    キャンセルなら何もしない。lib_pick_playdata は選ばれたファイルをプレイ記録の場所にする'''
    import test_native_access as TNA
    app, acc, out, store, base = TNA._setup()
    ML = TML._ml()
    lib = ML.MediaLibrary(str(base / "libdata"), opener=lambda p: None, default_playdata=str(base / "nope" / "PlayerData.dat"))
    folder = base / "MyLevels"
    folder.mkdir()
    wv = TNA._FakeWebview(str(folder))
    api = app._make_api(acc, str(base), {"dirty": False, "force": False}, wv, lib)
    r = api.lib_pick_folder()
    t.eq(r["name"], "MyLevels", "記録して名前を返す")
    t.ok(any(l["id"] == r["id"] for l in lib.list()), "ライブラリに入る")
    t.ok(not acc.in_out_dir(str(folder)), "書き出し先の許可にはしない")
    wv.result = None
    t.eq(api.lib_pick_folder(), None, "キャンセル")
    t.eq(len(lib.list()), 1, "キャンセルでは増えない")
    pd = base / "elsewhere" / "PlayerData.dat"
    pd.parent.mkdir()
    pd.write_text(json.dumps({"localPlayers": [{"levelsStatsData": [], "favoritesLevelIds": []}]}), encoding="utf-8")
    wv.result = str(pd)
    r = api.lib_pick_playdata()
    t.eq((r["mode"], os.path.normcase(r["path"]), r["state"]), ("custom", os.path.normcase(str(pd)), "ok"), "選んだプレイ記録")
    t.eq(wv.calls[-1][0], "open", "ファイル選択ダイアログ")
    no_lib = app._make_api(acc, str(base), {"dirty": False, "force": False}, wv)
    t.eq((no_lib.lib_pick_folder(), no_lib.lib_pick_playdata()), (None, None), "ライブラリが無い時は何もしない")

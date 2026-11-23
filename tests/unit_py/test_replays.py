"""REPLAY の窓の裏側（bsor.py・replays.py・serve.py の /__replay/*・viewer・app.py の replay_pick_folder・2026-11-22）。
合成の .bsor と書き出しの控え（tests/_lib/replay_fixture.py）で確かめる。利用者の本物のリプレイ・他人の譜面は使わない。
BL のリプレイアプリの写し（replay-viewer/）は、一時フォルダに小さな偽物を作って差し替える（写しが無くても通る）"""
import hashlib
import http.client
import io
import json
import os
import socket
import sys
import tempfile
import time
import zipfile
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qs, quote, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "_lib"))
import unitpy_helpers as H
import replay_fixture as RF


def _mods():
    sys.path.insert(0, str(H.ROOT))
    import bsor
    import replays
    return bsor, replays


INDEX = '<!doctype html><html><head><title>BL</title></head><body><div id="app"></div>\n</body></html>'


def _env(env=True):
    """一時のデータフォルダ・偽物の viewer（replay-viewer/blreplay/index.html・build/app.js・bridge.js）・リプレイのフォルダで ReplayStore を作る"""
    bsor, R = _mods()
    tmp = Path(tempfile.mkdtemp(prefix="nlm_unitpy_rp_"))
    base, data, rdir = tmp / "base", tmp / "data", tmp / "Replays"
    (base / "replay-viewer" / "blreplay" / "build").mkdir(parents=True)
    (base / "replay-viewer" / "blreplay" / "index.html").write_text(INDEX, encoding="utf-8")
    (base / "replay-viewer" / "blreplay" / "build" / "app.js").write_text("console.log(1)", encoding="utf-8")
    (base / "replay-viewer" / "bridge.js").write_text("// bridge", encoding="utf-8")
    (tmp / "secret.txt").write_text("secret", encoding="utf-8")
    rdir.mkdir()
    store = R.ReplayStore(str(data), str(base), env_dirs=str(rdir) if env else None)
    store.steam_default = str(tmp / "no-steam")
    return SimpleNamespace(R=R, bsor=bsor, store=store, tmp=tmp, base=base, data=data, rdir=rdir)


def _kept(e, song="Test Song", mapper="Tester", diffs=("Expert",), egg=b"OggS-egg"):
    """API（keep・keepEgg）で控える → hash"""
    files = RF.make_map(song=song, mapper=mapper, diffs=diffs)
    m, body = RF.keep_body(files)
    r = e.store.keep(m, body)
    if egg is not None:
        e.store.keep_egg(r["hash"], hashlib.sha1(egg).hexdigest(), io.BytesIO(egg), len(egg))
    return r["hash"], files


def _err(fn, *a):
    _, R = _mods()
    try:
        fn(*a)
    except R.ReplayError as x:
        return x.code
    return None


# ---------------------------------------------------------------- bsor.py

def test_bsor_read_info_notes_quirks(t):
    '''.bsor の頭・ノーツ・壁を読む（壊れた文字列の長さは 1 バイトずらして読み直す・-1 はボム・フレームを読み飛ばしても全部読んだ時と同じ）'''
    e = _env()
    B = e.bsor
    f = RF.write_replay(e.rdir, notes=RF.NOTES, walls=[(1, 0.1, 4.0, 4.0)], broken=True, mods="FS,NF", end=5.0, jd=16.5)
    info = B.read_info(f, head=64)   # 頭が 64 バイトを超えても読み足す
    t.eq((info["song_name"], info["mapper"], info["difficulty"], info["hash"], info["modifiers"], info["mode"]),
         ("Test Song", "Tester", "Expert", "AB" * 20, "FS,NF", "Standard"), "頭")
    t.eq(info["player_name"], "プレイヤー", "長さの前の余計な 1 バイトを飛ばす")
    t.ok(abs(info["jump_distance"] - 16.5) < 1e-6, "JD")
    r = B.read(f)
    t.eq(r, B.parse(f.read_bytes()), "読み飛ばす道と全部読む道で同じ")
    t.eq((r["frames"], len(r["notes"]), len(r["walls"]), r["pauses"]), (3, 7, 1, [(3, 12.5)]), "数")
    t.eq([n["type"] for n in r["notes"]], [B.GOOD, B.GOOD, B.BAD, B.MISS, B.BOMB, B.GOOD, B.GOOD], "-1 はボム")
    t.eq(r["notes"][4]["id"], 3, "ボムの番号に 4 を足す")
    t.eq(r["end"], 5.0, "最後のフレームの時刻")
    t.eq(B.note_params(RF.nid(3, 2, 1, 1, 7)), (3, 2, 1, 1, 7), "番号の分け方")
    t.eq(B.note_params(30000000 + 2 * 1000000 + 1 * 100000 + 15), (3, 2, 1, 1, 5), "大きい譜面の形")
    t.eq(B.max_score(r["notes"]), 115 + 115 * 2 * 3 + 85 * 2 + 20 * 4, "満点（ボムを除く 6 個・倍率 1→2→4）")
    s = B.summary(r)
    t.eq((s["notes"], s["misses"], s["bad"], s["bombs"], s["walls"], s["end"]), (6, 1, 1, 1, 1, 5.0), "一覧の数")


def test_bsor_score_and_acc(t):
    '''1 つの点は BL のリプレイアプリと同じ式（振り始め 70・振り終わり 30・真ん中 15・アーク・チェーンの種類ごと・.5 は上へ）。
    精度＝修飾の前の点（倍率は良い切り方で上がり、悪い切り方・見逃し・ボム・壁で下がる）÷満点'''
    e = _env()
    B = e.bsor

    def cut(st, before, after, dist, kind=0):
        return {"id": RF.nid(st, 1, 0, 0, 1), "type": kind, "cut": {"before": before, "after": after, "distance": dist}}
    t.eq(B.cut_score(cut(3, 1.0, 1.0, 0.0)), 115, "通常の満点")
    t.eq(B.cut_score(cut(3, 0.75, 0.5, 0.15)), 53 + 15 + 8, "通常（52.5→53・7.5→8＝.5 は上へ）")
    t.eq(B.cut_score(cut(3, 2.0, -1.0, 0.5)), 70 + 0 + 0, "はみ出しは 0〜70・0〜30・0〜15 に収める")
    t.eq(B.cut_score(cut(4, 0.5, 0.0, 0.0)), 35 + 30 + 15, "アークの頭は振り終わり 30 のまま")
    t.eq(B.cut_score(cut(5, 0.0, 0.5, 0.0)), 70 + 15 + 15, "アークの尾は振り始め 70 のまま")
    t.eq(B.cut_score(cut(6, 1.0, 1.0, 0.0)), 85, "チェーンの頭は振り終わり 0")
    t.eq(B.cut_score(cut(7, 0.0, 0.0, 1.0)), 20, "チェーンの後ろは 20")
    t.eq(B.cut_score(cut(8, 0.0, 0.0, 0.0)), 115, "アークの頭と尾")
    t.eq([B.note_max(RF.nid(s, 0, 0, 0, 0)) for s in (0, 2, 3, 6, 7)] + [B.note_max(10 * 10000000)], [115, 0, 115, 85, 20, 20],
         "種類ごとの満点（10 以上は大きい譜面の形の番号）")
    ok = [(RF.nid(3, i % 4, 0, i % 2, 1), 1.0 + i, 1.0 + i, RF.GOOD, 1.0, 1.0, 0.0) for i in range(4)]
    f = RF.write_replay(e.rdir, name="full.bsor", notes=ok)
    rep = B.read(f)
    t.eq((B.base_score(rep), B.max_score(rep["notes"])), (115 * (1 + 2 + 2 + 2), 115 * 7), "全部満点の点＝満点（倍率 1→2・4 へは 4 つ要る）")
    t.eq(B.summary(rep)["acc"], 1.0, "精度 1")
    # 2 つ目を見逃す: 倍率 1→（見逃しで 1 のまま・進みは 0）→ 3 つ目 1（進み 1）→ 4 つ目で 2
    miss = list(ok)
    miss[1] = (miss[1][0], 2.0, 2.0, RF.MISS, 0, 0, 0)
    rep = B.read(RF.write_replay(e.rdir, name="miss.bsor", notes=miss))
    t.eq(B.base_score(rep), 115 * 1 + 115 * 1 + 115 * 2, "見逃すと倍率の進みが 0 に戻る")
    # 壁: 4 つ満点で倍率 2 になった後に壁 → 1 に下がる
    more = ok + [(RF.nid(3, 0, 0, 0, 1), 6.0, 6.0, RF.GOOD, 1.0, 1.0, 0.0)]
    rep = B.read(RF.write_replay(e.rdir, name="wall.bsor", notes=more, walls=[(1, 0.1, 5.5, 5.5)]))
    t.eq(B.base_score(rep), 115 * (1 + 2 + 2 + 2) + 115 * 1, "壁で倍率が下がる")


def test_bsor_bad_files(t):
    '''.bsor でない・途中で終わる・頭の文字列の長さが壊れた物は BsorError（読み足すのは途中で終わる時だけ・上限まで）'''
    e = _env()
    B = e.bsor
    for name, data in (("zero.bsor", b"\x00" * 40), ("short.bsor", RF.bsor_bytes()[:30]), ("empty.bsor", b""),
                       ("big-junk.bsor", b"\x69\x3d\x2d\x44\x01\x00" + b"\xff" * 300000)):
        p = e.rdir / name
        p.write_bytes(data)
        for fn in (B.read_info, B.read):
            try:
                fn(p)
                t.ok(False, f"{name}: {fn.__name__} は断る")
            except B.BsorError:
                pass
    full = RF.bsor_bytes(notes=RF.NOTES, end=2.0)
    (e.rdir / "cut.bsor").write_bytes(full[:-30])   # ノーツの途中で終わる
    try:
        B.read(e.rdir / "cut.bsor")
        t.ok(False, "途中で終わる物は断る")
    except B.BsorError:
        pass


def test_bsor_events(t):
    '''出来事（/__replay/events の中身）: ノーツはノーツの秒（spawn）の順・good だけ点と満点・ボムは色と向きが None・壁は入った秒'''
    e = _env()
    B = e.bsor
    rep = B.read(RF.write_replay(e.rdir, notes=RF.NOTES, walls=[(1, 0.1, 4.25, 4.0)], end=6.5))
    ev = B.events(rep)
    t.eq([n["type"] for n in ev["notes"]], ["good", "good", "bad", "miss", "bomb", "good", "good"], "種類")
    t.eq([n["t"] for n in ev["notes"]], [1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 3.55], "ノーツの秒（spawn）")
    g = ev["notes"][1]
    t.eq((g["x"], g["y"], g["c"], g["d"], g["score"], g["max"]), (2, 0, 1, 1, 70 + 15 + 7, 115), "good の位置・点")
    t.eq((ev["notes"][2]["score"], ev["notes"][2]["max"]), (None, None), "bad は点なし")
    t.eq((ev["notes"][4]["c"], ev["notes"][4]["d"]), (None, None), "ボムの色と向き")
    t.eq((ev["notes"][5]["max"], ev["notes"][6]["score"]), (85, 20), "チェーンの頭・後ろ")
    t.eq((ev["walls"], ev["endSec"]), ([{"t": 4.25}], 6.5), "壁・記録が終わった秒")


# ---------------------------------------------------------------- フォルダの決め方

class _Lib:
    def __init__(self, paths):
        self.paths = paths

    def list(self):
        return [{"id": str(i), "path": p, "state": "ok"} for i, p in enumerate(self.paths)]


def test_folders_env_chosen_auto(t):
    '''リプレイのフォルダ: ① NLM_REPLAYS（あれば自動の検出をしない・空でも）② 選んだフォルダ ③ 自動（MEDIA のライブラリから推定・
    BSManager は全部の版・ゲームのフォルダ・Steam の既定・重なりは 1 つ・UNC からは推定しない）'''
    e = _env(env=False)
    R, st, tmp = e.R, e.store, e.tmp
    bsm = tmp / "BSManager"
    shared = bsm / "SharedContent" / "SharedMaps" / "CustomLevels"
    shared.mkdir(parents=True)
    for v in ("1.39.1", "1.40.8"):
        (bsm / "BSInstances" / v / "UserData" / "BeatLeader" / "Replays").mkdir(parents=True)
    (bsm / "BSInstances" / "1.38.0").mkdir(parents=True)   # リプレイの無い版
    game = tmp / "Beat Saber"
    (game / "Beat Saber_Data" / "CustomLevels").mkdir(parents=True)
    (game / "UserData" / "BeatLeader" / "Replays").mkdir(parents=True)
    steam = tmp / "steam" / "Replays"
    steam.mkdir(parents=True)
    RF.write_replay(steam, name="a.bsor")
    RF.write_replay(steam, name="b.BSOR")
    (steam / "c.txt").write_text("x", encoding="utf-8")
    st.steam_default = str(steam)
    st.library = _Lib([str(shared), str(game / "Beat Saber_Data" / "CustomLevels"), str(shared), r"\\server\share\CustomLevels",
                       str(tmp / "other")])
    src, dirs = st.folders()
    t.eq(src, "auto", "自動")
    t.eq([Path(d).relative_to(tmp).as_posix() for d in dirs],
         ["BSManager/BSInstances/1.40.8/UserData/BeatLeader/Replays", "BSManager/BSInstances/1.39.1/UserData/BeatLeader/Replays",
          "Beat Saber/UserData/BeatLeader/Replays", "steam/Replays"], "新しい版から・重なりは 1 つ・無い場所は出さない")
    s = st.status()
    t.eq((s["ok"], s["source"], s["dirs"][-1]), (True, "auto", {"path": str(steam), "count": 2}), "数は .bsor だけ（大文字小文字は問わない）")
    st.library, st.steam_default = None, str(tmp / "nope")
    t.eq(st.status(), {"ok": True, "source": "none", "dirs": []}, "見つからない")
    st.env_dirs = []
    t.eq(st.folders(), ("env", []), "NLM_REPLAYS が空でも自動の検出をしない")
    st.env_dirs = [str(steam), str(tmp / "gone")]
    s = st.status()
    t.eq((s["source"], s["dirs"][1]), ("env", {"path": str(tmp / "gone"), "count": 0, "missing": True}), "無いフォルダは missing")
    t.eq(R.ReplayStore(str(e.data), str(e.base), env_dirs=os.pathsep.join([str(steam), str(game)])).env_dirs,
         [str(steam), str(game)], "os.pathsep 区切り")


def test_choose_and_reset_folder(t):
    '''選んだフォルダ（config/replays.json）は自動より先・無いフォルダや場所でない物は記録しない・resetFolder で自動へ戻す・
    壊れた・書き換えられた記録は使わない'''
    e = _env(env=False)
    st = e.store
    st.steam_default = str(e.rdir)
    t.eq(st.status()["source"], "auto", "最初は自動")
    mine = e.tmp / "MyReplays"
    mine.mkdir()
    s = st.choose_dir(str(mine))
    t.eq((s["source"], [d["path"] for d in s["dirs"]]), ("chosen", [str(mine)]), "選んだフォルダ")
    t.eq(json.loads((e.data / "config" / "replays.json").read_text(encoding="utf-8")), {"dir": str(mine)}, "記録")
    t.eq(_err(st.choose_dir, str(e.tmp / "nope")), "not-found", "無いフォルダ")
    t.eq(_err(st.choose_dir, "relative\\dir"), "bad-path", "相対パス")
    t.eq(_err(st.choose_dir, "\\\\?\\C:\\x"), "bad-path", "デバイスパス")
    t.eq(st.status()["source"], "chosen", "断った時は前のまま")
    (e.data / "config" / "replays.json").write_text(json.dumps({"dir": "..\\..\\x"}), encoding="utf-8")
    t.eq(st.status()["source"], "auto", "場所でない記録は使わない")
    st.choose_dir(str(mine))
    s = st.reset_folder()
    t.eq((s["source"], (e.data / "config" / "replays.json").exists()), ("auto", False), "自動へ戻す")
    t.eq(st.reset_folder()["source"], "auto", "2 回目も")


# ---------------------------------------------------------------- 書き出しの控え

def test_keep_and_egg(t):
    '''keep: Info.dat が指す難易度・カバーを hash（map_hash.py と同じ）ごとに控える・nlm.json・同じ hash は書き出した時刻を新しくする。
    keepEgg: SHA-1 を確かめて eggs/ に 1 つ（同じ音は置き直さない）・控えの音は後から書いた方が勝つ'''
    e = _env()
    st = e.store
    files = RF.make_map(song="Song A", mapper="Oz", diffs=("Hard", "Expert"))
    files["extra.png"] = b"\x89PNGx"   # Info.dat が指さない物は控えない
    m, body = RF.keep_body(files)
    r = st.keep(m, body)
    h = RF.map_hash_of(files)
    t.eq(r, {"ok": True, "hash": h, "isNew": True, "needEgg": True}, "新しい控え")
    d = e.data / "replays" / "maps" / h
    t.eq(sorted(p.name for p in d.iterdir()), ["ExpertStandard.dat", "HardStandard.dat", "Info.dat", "cover.jpg", "nlm.json"], "控えの中身")
    meta = json.loads((d / "nlm.json").read_text(encoding="utf-8"))
    t.eq((meta["songName"], meta["levelAuthor"], meta["egg"]), ("Song A", "Oz", None), "nlm.json")
    t.ok(abs(meta["exportedAt"] - time.time()) < 60, "書き出した時刻（unix 秒）")
    t.eq((d / "ExpertStandard.dat").read_bytes(), files["ExpertStandard.dat"], "バイト列のまま")
    t.ok(not list((e.data / "replays" / "maps").glob("*.tmp")), "一時フォルダは残らない")
    egg = b"OggS-first"
    t.eq(st.keep_egg(h.upper(), hashlib.sha1(egg).hexdigest(), io.BytesIO(egg), len(egg)), {"ok": True}, "音を控える")
    ef = e.data / "replays" / "eggs" / (hashlib.sha1(egg).hexdigest() + ".egg")
    t.eq(ef.read_bytes(), egg, "eggs/<sha1>.egg")
    t.eq(json.loads((d / "nlm.json").read_text(encoding="utf-8"))["egg"], hashlib.sha1(egg).hexdigest(), "控えの音")
    meta = json.loads((d / "nlm.json").read_text(encoding="utf-8"))
    meta["exportedAt"] = 1000
    (d / "nlm.json").write_text(json.dumps(meta), encoding="utf-8")
    files["cover.jpg"] = b"\xff\xd8\xff\xe0new"
    r = st.keep(*RF.keep_body(files))
    t.eq((r["isNew"], r["needEgg"]), (False, False), "同じ hash（カバーは hash に入らない）")
    meta2 = json.loads((d / "nlm.json").read_text(encoding="utf-8"))
    t.ok(meta2["exportedAt"] > 1000 and meta2["egg"] == hashlib.sha1(egg).hexdigest(), "時刻は新しく・音はそのまま")
    t.eq((d / "cover.jpg").read_bytes(), b"\xff\xd8\xff\xe0new", "カバーは新しい物")
    egg2 = b"OggS-lead-in-changed"
    st.keep_egg(h, hashlib.sha1(egg2).hexdigest(), io.BytesIO(egg2), len(egg2))
    t.eq(json.loads((d / "nlm.json").read_text(encoding="utf-8"))["egg"], hashlib.sha1(egg2).hexdigest(), "後から書いた音が勝つ")
    mt = ef.stat().st_mtime_ns
    time.sleep(0.02)
    st.keep_egg(h, hashlib.sha1(egg).hexdigest(), io.BytesIO(egg), len(egg))
    t.eq((ef.stat().st_mtime_ns, len(list(ef.parent.iterdir()))), (mt, 2), "同じ音は置き直さない・一時ファイルは残らない")
    files2 = RF.make_map(song="Song A", mapper="Oz", diffs=("Expert",))
    t.ok(st.keep(*RF.keep_body(files2))["needEgg"], "別の hash は音がまだ")


def test_keep_rejects_bad_input(t):
    '''keep は名前（1 つの名前・.dat と画像だけ・重なり無し）・大きさの合計・Info.dat（読める・指す .dat がそろう・名前が 1 つの名前）を確かめる'''
    e = _env()
    st = e.store
    good = RF.make_map()

    def keep_with(files):
        return _err(st.keep, *RF.keep_body(files))
    for bad in ("../x.dat", "a/b.dat", "a\\b.dat", "C:x.dat", "x.exe", "x.dat.", " x.dat", "a\x00.dat", "", "." * 3, "x" * 200 + ".dat",
                "CON.dat", "nul.png", "com1.dat", "a?.dat", "a\n.dat"):
        t.eq(keep_with(dict(good, **{bad: b"{}"})), "bad-name", f"名前 {bad!r}")
    t.eq(keep_with({"Info.dat": good["Info.dat"], "INFO.DAT": good["Info.dat"]}), "bad-name", "大文字小文字だけ違う重なり")
    m, body = RF.keep_body(good)
    t.eq(_err(st.keep, m, body + b"x"), "bad-request", "大きさの合計が合わない")
    t.eq(_err(st.keep, m, body[:-1]), "bad-request", "足りない")
    for mm in ("", "{", "[]", json.dumps({"files": []}), json.dumps({"files": [{"name": "Info.dat", "size": True}]}),
               json.dumps({"files": [{"name": "Info.dat", "size": -1}]}), json.dumps({"files": [{"name": "Info.dat"}] * 65})):
        t.eq(_err(st.keep, mm, b""), "bad-request", f"m={mm[:40]!r}")
    t.eq(keep_with({k: v for k, v in good.items() if k != "Info.dat"}), "bad-map", "Info.dat が無い")
    t.eq(keep_with({k: v for k, v in good.items() if k != "ExpertStandard.dat"}), "bad-map", "指す難易度が無い")
    t.eq(keep_with(dict(good, **{"Info.dat": b"not json"})), "bad-map", "読めない Info.dat")
    info = json.loads(good["Info.dat"])
    info["_difficultyBeatmapSets"][0]["_difficultyBeatmaps"][0]["_beatmapFilename"] = "..\\..\\secret.dat"
    t.eq(keep_with(dict(good, **{"Info.dat": json.dumps(info).encode()})), "bad-map", "Info.dat の中の名前が外を指す")
    t.ok(not (e.data / "replays" / "maps").exists() or not list((e.data / "replays" / "maps").iterdir()), "何も控えない")


def test_keep_egg_rejects(t):
    '''keepEgg: 控えの無い hash は no-map・SHA-1 が違えば置かない（bad-sha1）・形の違う値は bad-request。どれも本体を読み切る'''
    e = _env()
    st = e.store
    h, _ = _kept(e, egg=None)
    egg = b"OggS-x" * 100

    class Body(io.BytesIO):
        pass
    for args, want in (((("f" * 40), hashlib.sha1(egg).hexdigest()), "no-map"), (("xyz", hashlib.sha1(egg).hexdigest()), "bad-request"),
                       ((h, "nope"), "bad-request"), ((h, "0" * 40), "bad-sha1")):
        b = Body(egg + b"NEXT")
        t.eq(_err(st.keep_egg, args[0], args[1], b, len(egg)), want, f"{args} → {want}")
        t.eq(b.read(), b"NEXT", f"{want}: 本体を読み切る（次の要求の分は読まない）")
    t.ok(not (e.data / "replays" / "eggs").exists() or not list((e.data / "replays" / "eggs").iterdir()), "何も置かない")
    t.eq(_err(st.keep_egg, h, hashlib.sha1(egg).hexdigest(), io.BytesIO(egg[:10]), len(egg)), "bad-request", "本体が途中で終わる")


# ---------------------------------------------------------------- 一覧

def test_list_this_song(t):
    '''一覧は「この曲」だけ: 控えの曲名・マッパー名（前後の空白・大文字小文字は問わない）が同じ控えの hash の物＝playable、同じ曲名・マッパーで
    控えに無い版（音の無い控えも）＝playable:false。ほかの曲・同じ曲名の他人の譜面は出さない・新しい順・印（fail・exit・practice）'''
    e = _env()
    st, rd = e.store, e.rdir
    h1, _ = _kept(e, song="My Song", mapper="Oz", diffs=("Expert",))
    h2, _ = _kept(e, song="My Song", mapper="Oz", diffs=("Hard", "Expert"))       # 一番新しい書き出し
    h3, _ = _kept(e, song="My Song", mapper="Oz", diffs=("Easy",), egg=None)      # 音の無い控え
    for h, at in ((h1, 100), (h2, 300.5), (h3, 200)):
        d1 = e.data / "replays" / "maps" / h / "nlm.json"
        d1.write_text(json.dumps(dict(json.loads(d1.read_text(encoding="utf-8")), exportedAt=at)), encoding="utf-8")
    hx, _ = _kept(e, song="Other Song", mapper="Oz", diffs=("Expert",))
    RF.write_replay(rd, song="My Song", mapper="Oz", h=h1, ts=1000, notes=RF.NOTES, end=4.0, mods="FS")
    RF.write_replay(rd, song="My Song", mapper="Oz", h=h2, ts=3000, diff="Hard", flags=("fail",))
    RF.write_replay(rd, song="My Song", mapper="Oz", h=h2, ts=2500, flags=("exit", "practice"), end=1.25, jd=15.0)
    RF.write_replay(rd, song="My Song", mapper="Oz", h=h3, ts=2000, diff="Easy")
    RF.write_replay(rd, song="my song ", mapper=" OZ", h="CD" * 20, ts=1500)                # 控えに無い版
    RF.write_replay(rd, song="My Song", mapper="Someone", h="CE" * 20, ts=1600)              # 同じ曲名の他人の譜面
    RF.write_replay(rd, song="Other Song", mapper="Oz", h=hx, ts=1700)                       # ほかの曲
    (rd / "broken.bsor").write_bytes(b"junk")
    r = st.list({"name": "  my SONG", "mapper": "oz"})
    t.eq(r["ok"], True, "ok")
    t.eq(r["status"]["source"], "env", "status も返す")
    got = [(x["playedAt"], x["hash"], x["playable"]) for x in r["items"]]
    t.eq(got, [(3000, h2, True), (2500, h2, True), (2000, h3, False), (1500, "cd" * 20, False), (1000, h1, True)], "この曲だけ・新しい順")
    by = {x["playedAt"]: x for x in r["items"]}
    a = by[1000]
    t.eq({k: a[k] for k in ("diff", "mode", "fail", "exit", "practice", "misses", "bad", "bombs", "walls", "mods", "endSec", "jd", "latest")},
         {"diff": "Expert", "mode": "Standard", "fail": False, "exit": False, "practice": False, "misses": 1, "bad": 1, "bombs": 1,
          "walls": 0, "mods": "FS", "endSec": 4.0, "jd": 17.0, "latest": False}, "項目")
    t.ok(isinstance(a["acc"], float) and 0 < a["acc"] < 1, "精度は 0〜1")
    t.eq(a["exportedAt"], 100, "控えの時刻")
    t.eq((by[3000]["fail"], by[3000]["latest"], by[3000]["diff"]), (True, True, "Hard"), "失敗の印・一番新しい控え")
    t.eq((by[2500]["exit"], by[2500]["practice"], by[2500]["endSec"], by[2500]["jd"]), (True, True, 1.25, 15.0), "やめた・練習")
    t.eq((by[1500]["exportedAt"], by[2000]["exportedAt"] is not None), (None, True), "控えに無い版の時刻は null")
    t.ok(all(x["file"].endswith(".bsor") and "\\" not in x["file"] for x in r["items"]), "file はファイル名だけ")
    t.ok(len({x["id"] for x in r["items"]}) == 5 and all(str(rd) not in x["id"] for x in r["items"]), "id は場所を含まない")
    t.eq(st.list({"name": "My Song", "mapper": "Oz"})["items"][0]["id"], r["items"][0]["id"], "id はこの起動の間は同じ")
    t.eq(st.list({"name": "", "mapper": ""})["items"], [], "曲名が空なら何も出さない")
    t.eq(st.list({"name": "Nothing", "mapper": ""})["items"], [], "知らない曲")
    for bad in (None, "x", {"name": 1}, {"name": "a", "mapper": 2}):
        t.eq(_err(st.list, bad), "bad-request", f"song={bad!r}")


def test_list_cache(t):
    '''.bsor の頭と数は config/replays_cache.json に控え、次（起動し直した後も）は読み直さない。書き換わったファイルは読み直す・消えたファイルの分は消す'''
    e = _env()
    st, rd, B = e.store, e.rdir, e.bsor
    h, _ = _kept(e, song="S", mapper="M")
    f1 = RF.write_replay(rd, song="S", mapper="M", h=h, ts=10, notes=RF.NOTES)
    f2 = RF.write_replay(rd, song="S", mapper="M", h=h, ts=20)
    t.eq(len(st.list({"name": "S", "mapper": "M"})["items"]), 2, "2 件")
    cf = e.data / "config" / "replays_cache.json"
    c = json.loads(cf.read_text(encoding="utf-8"))
    t.eq((c["v"], len(c["items"])), (e.R.CACHE_VER, 2), "控え")
    orig_info, orig_read = B.read_info, B.read
    calls = []
    B.read_info = lambda *a, **k: calls.append(a) or orig_info(*a, **k)
    B.read = lambda *a, **k: calls.append(a) or orig_read(*a, **k)
    try:
        st2 = e.R.ReplayStore(str(e.data), str(e.base), env_dirs=str(rd))   # 起動し直した
        r = st2.list({"name": "S", "mapper": "M"})
        t.eq((len(r["items"]), calls), (2, []), "控えから（.bsor を読まない）")
        time.sleep(0.02)
        f2.write_bytes(RF.bsor_bytes(song="S", mapper="M", h=h, ts=30, notes=RF.NOTES[:1]))
        r = st2.list({"name": "S", "mapper": "M"})
        t.eq((sorted(x["playedAt"] for x in r["items"]), len(calls)), ([10, 30], 2), "書き換わった 1 つだけ読み直す（頭と数）")
        f1.unlink()
        st2.list({"name": "S", "mapper": "M"})
        t.eq(len(json.loads(cf.read_text(encoding="utf-8"))["items"]), 1, "消えたファイルの分は消す")
    finally:
        B.read_info, B.read = orig_info, orig_read
    cf.write_text("{broken", encoding="utf-8")
    t.eq(len(e.R.ReplayStore(str(e.data), str(e.base), env_dirs=str(rd)).list({"name": "S", "mapper": "M"})["items"]), 1, "壊れた控えは読み直すだけ")


# ---------------------------------------------------------------- 開く・使い捨ての鍵・出来事

def _q(url):
    q = parse_qs(urlsplit(url).query)
    return {k: v[0] for k, v in q.items()}


def test_open_token_and_zip(t):
    '''open: viewer のページの URL（link＝その 1 件の .bsor・mapLink＝譜面の zip・どちらも使い捨ての鍵の場所・t があれば time=ミリ秒）。
    zip は控えの Info.dat・難易度・カバー・song.egg（名前は Info.dat の _songFilename・STORED）。鍵で渡すのは開いた 1 件だけ'''
    e = _env()
    st, rd, R = e.store, e.rdir, e.R
    egg = b"OggS-the-egg"
    h, files = _kept(e, song="Z", mapper="M", diffs=("Hard", "Expert"), egg=egg)
    f = RF.write_replay(rd, song="Z", mapper="M", h=h, diff="Hard", notes=RF.NOTES, end=7.5)
    RF.write_replay(rd, song="Z", mapper="M", h=h, ts=5, name="second.bsor")
    rid = next(x["id"] for x in st.list({"name": "Z", "mapper": "M"})["items"] if x["file"] == f.name)
    port = H._free_port()
    try:
        o = st.open(rid, 12.3456, port)
        org = o["origin"]
        t.ok(org.startswith("http://localhost:") and int(org.rsplit(":", 1)[1]) != port, "viewer は localhost の別の番号")
        t.eq({k: o[k] for k in ("ok", "endSec", "diff", "mode", "hash")}, {"ok": True, "endSec": 7.5, "diff": "Hard", "mode": "Standard", "hash": h}, "答え")
        t.ok(o["url"].startswith(org + "/blreplay/index.html?"), "BL のリプレイアプリのページ")
        q = _q(o["url"])
        t.eq(q["time"], "12346", "time はミリ秒")
        t.ok(q["link"].startswith(org + "/blr/") and q["link"].endswith("/" + quote(f.name, safe="")), "link")
        t.eq(q["mapLink"], q["link"].rsplit("/", 1)[0] + "/map.zip", "mapLink")
        tok = q["link"].split("/")[4]
        t.ok(R.TOKEN_RE.fullmatch(tok) is not None, "鍵")
        got = st.token_file(tok, f.name)
        t.eq(got, (f.read_bytes(), "application/octet-stream"), ".bsor")
        z, ct = st.token_file(tok, "map.zip")
        zf = zipfile.ZipFile(io.BytesIO(z))
        t.eq((ct, sorted(zf.namelist())), ("application/zip", ["ExpertStandard.dat", "HardStandard.dat", "Info.dat", "cover.jpg", "song.egg"]), "zip の中身")
        t.ok(all(i.compress_type == zipfile.ZIP_STORED for i in zf.infolist()), "STORED")
        t.eq((zf.read("song.egg"), zf.read("Info.dat")), (egg, files["Info.dat"]), "音・Info.dat")
        for name in ("second.bsor", "../" + f.name, "Info.dat", ""):
            t.eq(st.token_file(tok, name), None, f"鍵で渡すのは開いた 1 件だけ: {name!r}")
        t.eq(st.token_file("x" * 32, "map.zip"), None, "知らない鍵")
        t.eq(st.token_file("../" * 10, "map.zip"), None, "鍵の形でない")
        o2 = st.open(rid, None, port)
        t.ok("time=" not in o2["url"] and o2["origin"] == org, "t が無ければ time なし・viewer は同じ番号")
        toks = [_q(st.open(rid, 0, port)["url"])["link"].split("/")[4] for _ in range(R.TOKENS_MAX)]
        t.eq((st.token_file(tok, "map.zip"), st.token_file(toks[-1], f.name) is not None), (None, True), "鍵は新しい物から TOKENS_MAX 個だけ覚える")
    finally:
        R.stop_viewers(port)


def test_map_zip_tempo_from_zero(t):
    '''map.zip の難易度の .dat: v3 の bpmEvents に拍 0 の物が無ければ、拍 0 に Info.dat の BPM を足す（BL のリプレイアプリは最初の変化が拍 0 に無いと
    その前の拍まで変化の後の BPM で秒にする＝テンポパートのある NLM の書き出しでノーツが出なかった）。拍 0 がある・空・v3 でない物は元のバイト列のまま。
    控えの hash は元のファイルで数えた物のまま'''
    e = _env()
    st, rd, R = e.store, e.rdir, e.R
    files = RF.make_map(song="T", mapper="M", diffs=("Normal", "Hard", "Expert"), bpm=120.0)
    ex = json.loads(files["ExpertStandard.dat"])
    ex["bpmEvents"] = [{"b": 32, "m": 90}, {"b": 16, "m": 150}]   # 並びが拍の順でない物も
    files["ExpertStandard.dat"] = json.dumps(ex).encode("utf-8")
    hd = json.loads(files["HardStandard.dat"])
    hd["bpmEvents"] = [{"b": 0, "m": 100}, {"b": 8, "m": 150}]
    files["HardStandard.dat"] = json.dumps(hd).encode("utf-8")
    m, body = RF.keep_body(files)
    h = st.keep(m, body)["hash"]
    t.eq(h, RF.map_hash_of(files), "控えの hash は書き出したファイルのまま")
    egg = b"OggS-tempo"
    st.keep_egg(h, hashlib.sha1(egg).hexdigest(), io.BytesIO(egg), len(egg))
    f = RF.write_replay(rd, song="T", mapper="M", h=h, diff="Expert", notes=RF.NOTES, end=7.5)
    rid = next(x["id"] for x in st.list({"name": "T", "mapper": "M"})["items"] if x["file"] == f.name)
    port = H._free_port()
    try:
        tok = _q(st.open(rid, None, port)["url"])["link"].split("/")[4]
        zf = zipfile.ZipFile(io.BytesIO(st.token_file(tok, "map.zip")[0]))
        got = json.loads(zf.read("ExpertStandard.dat"))
        t.eq(got["bpmEvents"], [{"b": 0, "m": 120.0}, {"b": 16, "m": 150}, {"b": 32, "m": 90}], "拍 0 に Info.dat の BPM・拍の順")
        t.eq({k: v for k, v in got.items() if k != "bpmEvents"}, {k: v for k, v in ex.items() if k != "bpmEvents"}, "ほかの項目はそのまま")
        t.eq(zf.read("HardStandard.dat"), files["HardStandard.dat"], "拍 0 がある物は元のバイト列のまま")
        t.eq(zf.read("NormalStandard.dat"), files["NormalStandard.dat"], "空の bpmEvents は元のバイト列のまま")
        t.eq(zf.read("Info.dat"), files["Info.dat"], "Info.dat は元のまま")
    finally:
        R.stop_viewers(port)
    vd = R._viewer_dat
    for b in (b"not json", b'{"_version":"2.0.0","_notes":[]}', b'{"bpmEvents":[{"b":"x","m":1}]}', b'{"bpmEvents":[{"b":4,"m":150}]}'):
        t.eq(vd(b, None if b.startswith(b'{"bpmEvents":[{"b":4') else 120), b, f"直さない: {b[:30]!r}")
    t.eq(json.loads(vd(b'{"bpmEvents":[{"m":150,"b":4}]}', 98.5))["bpmEvents"][0], {"b": 0, "m": 98.5}, "基準の BPM の小数")
    t.eq((R._info_bpm({"_beatsPerMinute": 128}), R._info_bpm({"audio": {"bpm": 140.5}}), R._info_bpm({"_beatsPerMinute": True}),
          R._info_bpm({"_beatsPerMinute": -1}), R._info_bpm({})), (128, 140.5, None, None, None), "基準の BPM の読み方")


def test_open_errors(t):
    '''open・events の失敗: 知らない id（not-found）・控えの無い版／音の無い控え（no-map）・壊れた .bsor（bad-replay）・t が数でない（bad-request）・
    viewer の写しが無い（viewer-failed）。events は控えが無くても出す'''
    e = _env()
    st, rd, R = e.store, e.rdir, e.R
    h, _ = _kept(e, song="E", mapper="M")
    hn, _ = _kept(e, song="E", mapper="M", diffs=("Hard",), egg=None)
    RF.write_replay(rd, name="ok.bsor", song="E", mapper="M", h=h, notes=RF.NOTES)
    RF.write_replay(rd, name="noegg.bsor", song="E", mapper="M", h=hn)
    RF.write_replay(rd, name="old.bsor", song="E", mapper="M", h="CD" * 20, notes=RF.NOTES)
    ids = {x["file"]: x["id"] for x in st.list({"name": "E", "mapper": "M"})["items"]}
    port = H._free_port()
    try:
        for bad in ("", None, 123, "../x", "0" * 24, "g" * 24):
            t.eq(_err(st.open, bad, None, port), "not-found", f"id={bad!r}")
            t.eq(_err(st.events, bad), "not-found", f"events id={bad!r}")
        t.eq(_err(st.open, ids["old.bsor"], None, port), "no-map", "控えに無い版")
        t.eq(_err(st.open, ids["noegg.bsor"], None, port), "no-map", "音の無い控え")
        ev = st.events(ids["old.bsor"])
        t.eq((ev["ok"], len(ev["notes"])), (True, 7), "events は控えが無くても")
        for bad in ("1", True, float("nan"), [1]):
            t.eq(_err(st.open, ids["ok.bsor"], bad, port), "bad-request", f"t={bad!r}")
        (rd / "ok.bsor").write_bytes(b"\x00" * 50)
        t.eq(_err(st.open, ids["ok.bsor"], None, port), "bad-replay", "壊れた .bsor")
        t.eq(_err(st.events, ids["ok.bsor"]), "bad-replay", "events も")
        RF.write_replay(rd, name="ok.bsor", song="E", mapper="M", h=h)
        (rd / "ok.bsor").rename(rd / "moved.bsor")
        t.eq(_err(st.open, ids["ok.bsor"], None, port), "not-found", "消えたファイル")
        (rd / "moved.bsor").rename(rd / "ok.bsor")
        os.remove(e.base / "replay-viewer" / "blreplay" / "index.html")
        t.eq(_err(st.open, ids["ok.bsor"], None, port), "viewer-failed", "BL のリプレイアプリの写しが無い")
        st.env_dirs = [str(e.tmp)]
        t.eq(_err(st.events, ids["ok.bsor"]), "not-found", "今のフォルダの外の物は使わない")
    finally:
        R.stop_viewers(port)


# ---------------------------------------------------------------- serve.py の /__replay/*（本物の HTTP）

def _swap_store(e):
    s = H.server()
    old = s.serve.REPLAYS
    s.serve.REPLAYS = e.store
    return s, old


def _post_raw(path, body, ctype="application/octet-stream", **kw):
    st, hd, b = H.req("POST", path, headers={"Content-Type": ctype, "X-NLM-Request": "1"}, body=body, **kw)
    try:
        return st, json.loads(b.decode("utf-8"))
    except Exception:
        return st, None


def test_http_replay_api(t):
    '''/__replay/*（status・resetFolder・list・open・events・keep・keepEgg）は合言葉と X-NLM-Request が要る POST。エラーは {ok:false, error}・
    大きすぎる本体は読み捨てて too-large'''
    e = _env()
    s, old = _swap_store(e)
    try:
        st, r = H.post_json("/__replay/status", {})
        t.eq((st, r), (200, {"ok": True, "source": "env", "dirs": [{"path": str(e.rdir), "count": 0}]}), "status")
        st, r = H.post_json("/__replay/resetFolder", {})
        t.eq((st, r["source"]), (200, "env"), "resetFolder")
        for path in ("/__replay/status", "/__replay/list", "/__replay/keep"):
            t.eq(H.post_json(path, {}, token=False)[0], 403, f"{path}: 合言葉が要る")
            t.eq(H.req("POST", path, body=b"{}", headers={"Content-Type": "application/json"})[0], 403, f"{path}: X-NLM-Request が要る")
            t.eq(H.post_json(path, {}, origin="https://evil.example")[0], 403, f"{path}: ほかのサイトから")
        t.eq(H.req("GET", "/__replay/status")[0], 404, "GET では無い")
        files = RF.make_map(song="Http Song", mapper="Oz")
        m, body = RF.keep_body(files)
        st, r = _post_raw("/__replay/keep?m=" + quote(m, safe=""), body)
        t.eq((st, r["ok"], r["hash"], r["isNew"], r["needEgg"]), (200, True, RF.map_hash_of(files), True, True), "keep")
        h = r["hash"]
        egg = b"OggS-http" * 1000
        st, r = _post_raw(f"/__replay/keepEgg?hash={h}&sha1={hashlib.sha1(egg).hexdigest()}", egg)
        t.eq((st, r), (200, {"ok": True}), "keepEgg")
        st, r = _post_raw(f"/__replay/keepEgg?hash={h}&sha1={'0' * 40}", egg)
        t.eq(r, {"ok": False, "error": "bad-sha1"}, "keepEgg の SHA-1 違い")
        RF.write_replay(e.rdir, song="Http Song", mapper="Oz", h=h, notes=RF.NOTES, end=3.0)
        st, r = H.post_json("/__replay/list", {"song": {"name": "Http Song", "mapper": "Oz"}})
        t.eq((st, r["ok"], len(r["items"]), r["items"][0]["playable"], r["status"]["dirs"][0]["count"]), (200, True, 1, True, 1), "list")
        rid = r["items"][0]["id"]
        st, r = H.post_json("/__replay/events", {"id": rid})
        t.eq((r["ok"], len(r["notes"]), r["endSec"]), (True, 7, 3.0), "events")
        st, r = H.post_json("/__replay/open", {"id": rid, "t": 1.5})
        t.ok(r["ok"] and r["url"].startswith(r["origin"] + "/blreplay/index.html?") and "&time=1500" in r["url"], "open")
        vp = int(r["origin"].rsplit(":", 1)[1])
        t.ok(vp != s.port, "viewer は別の番号")
        st, r = H.post_json("/__replay/open", {"id": "nope"})
        t.eq(r, {"ok": False, "error": "not-found"}, "知らない id")
        st, r = H.post_json("/__replay/list", {"song": "x"})
        t.eq(r, {"ok": False, "error": "bad-request"}, "形の違う song")
        st, r = _post_raw("/__replay/list", b"{broken", "application/json")
        t.eq(r, {"ok": False, "error": "bad-request"}, "読めない JSON")
        st, r = H.post_json("/__replay/nope", {})
        t.eq(st, 404, "知らない口")
        # 上限を小さくして、大きすぎる本体を読み捨てて答えるか（本物の上限 300MB は送らない）
        o1, o2 = s.serve.REPLAY_EGG_MAX, s.serve.REPLAY_KEEP_MAX
        s.serve.REPLAY_EGG_MAX, s.serve.REPLAY_KEEP_MAX = 1000, 100
        try:
            st, r = _post_raw(f"/__replay/keepEgg?hash={h}&sha1={hashlib.sha1(egg).hexdigest()}", egg)
            t.eq((st, r), (200, {"ok": False, "error": "too-large"}), "keepEgg の上限")
            st, r = _post_raw("/__replay/keep?m=" + quote(m, safe=""), body)
            t.eq((st, r), (200, {"ok": False, "error": "too-large"}), "keep の上限")
        finally:
            s.serve.REPLAY_EGG_MAX, s.serve.REPLAY_KEEP_MAX = o1, o2
    finally:
        s.serve.REPLAYS = old
        s.serve.stop_viewers(s.port)


# ---------------------------------------------------------------- viewer の守り（本物の HTTP）

def _vreq(vp, path, host=None, headers=None, method="GET", body=None, addr="127.0.0.1"):
    h = {"Host": f"localhost:{vp}" if host is None else host}
    h.update(headers or {})
    c = http.client.HTTPConnection(addr, vp, timeout=10)
    try:
        c.putrequest(method, path, skip_host=True)
        for k, v in h.items():
            c.putheader(k, v)
        if body is not None:
            c.putheader("Content-Length", str(len(body)))
        c.endheaders(body)
        r = c.getresponse()
        return r.status, {k.lower(): v for k, v in r.getheaders()}, r.read()
    finally:
        c.close()


def test_viewer_guard(t):
    '''viewer（別のオリジン）: 出すのは GET の /blreplay/…・/bridge.js・/blr/<鍵>/<名前> だけ。index.html にだけ伝言の受け手の script を
    </body> の前に 1 つ足す（data-parent＝本体）・frame-ancestors は本体だけ・Host はこの PC の名前＋この番号・Origin が付けばこの番号のページだけ・
    POST 等は断る・本体の画面・API・写しの外は出さない'''
    e = _env()
    s, old = _swap_store(e)
    _, R = _mods()
    try:
        h, _ = _kept(e, song="V", mapper="M")
        f = RF.write_replay(e.rdir, song="V", mapper="M", h=h, notes=RF.NOTES)
        rid = H.post_json("/__replay/list", {"song": {"name": "V", "mapper": "M"}})[1]["items"][0]["id"]
        o = H.post_json("/__replay/open", {"id": rid})[1]
        org = o["origin"]
        vp = int(org.rsplit(":", 1)[1])
        parent = f"http://127.0.0.1:{s.port}"
        st, hd, body = _vreq(vp, "/blreplay/index.html?link=x")
        html = body.decode("utf-8")
        t.eq(st, 200, "index.html")
        t.eq(hd["content-security-policy"], "frame-ancestors " + parent, "埋め込めるのは本体の画面だけ")
        tag = f'<script src="/bridge.js" data-parent="{parent}"></script>'
        t.ok(html.count("bridge.js") == 1 and tag in html and html.index(tag) < html.rindex("</body>"), "</body> の前に 1 つ")
        t.eq(html.replace(tag + "\n", ""), INDEX, "写した物はほかは変えない")
        t.eq(_vreq(vp, "/blreplay/")[2], body, "/blreplay/ も index.html")
        st, hd, _ = _vreq(vp, "/blreplay?link=1")
        t.eq((st, hd.get("location")), (301, "/blreplay/?link=1"), "/blreplay は / 付きへ")
        st, hd, b = _vreq(vp, "/blreplay/build/app.js")
        t.eq((st, b, hd["content-type"].split(";")[0], "frame-ancestors" in hd["content-security-policy"]),
             (200, b"console.log(1)", "text/javascript", True), "写しのファイル")
        st2, hd2, _ = _vreq(vp, "/blreplay/build/app.js", headers={"If-None-Match": hd["etag"]})
        t.eq(st2, 304, "変わっていなければ 304")
        t.eq(_vreq(vp, "/bridge.js")[:1] + (_vreq(vp, "/bridge.js")[2],), (200, b"// bridge"), "bridge.js")
        q = _q(o["url"])
        lp, mp = urlsplit(q["link"]).path, urlsplit(q["mapLink"]).path
        st, hd, b = _vreq(vp, lp)
        t.eq((st, b, hd["cache-control"]), (200, f.read_bytes(), "no-store"), "鍵の場所の .bsor")
        t.eq(_vreq(vp, mp)[0], 200, "鍵の場所の map.zip")
        raw = f.read_bytes()
        for rg, code, part, cr in (("bytes=0-99", 206, raw[:100], f"bytes 0-99/{len(raw)}"),
                                   ("bytes=100-", 206, raw[100:], f"bytes 100-{len(raw) - 1}/{len(raw)}"),
                                   ("bytes=-10", 206, raw[-10:], f"bytes {len(raw) - 10}-{len(raw) - 1}/{len(raw)}"),
                                   (f"bytes={len(raw)}-", 416, b"", f"bytes */{len(raw)}"),
                                   ("bytes=5-1,7-9", 200, raw, None)):   # BL のリプレイアプリは頭から少しずつ読む（1 つの範囲だけ受ける）
            st, hd, b = _vreq(vp, lp, headers={"Range": rg})
            t.eq((st, b, hd.get("content-range")), (code, part, cr), f"Range: {rg}")
        t.eq(_vreq(vp, "/blr/" + "y" * 32 + "/map.zip")[0], 404, "知らない鍵")
        t.eq(_vreq(vp, mp, method="HEAD")[:1], (200,), "HEAD")
        # Host・Origin
        for host in (f"127.0.0.1:{vp}", f"LOCALHOST:{vp}", f"[::1]:{vp}"):
            t.eq(_vreq(vp, "/bridge.js", host=host)[0], 200, f"Host={host}")
        for host in ("evil.example", f"evil.example:{vp}", "localhost", f"localhost:{s.port}", f"localhost:{vp}0", ""):
            t.eq(_vreq(vp, "/bridge.js", host=host)[0], 403, f"Host={host!r}")
        for o_ in (org, f"http://127.0.0.1:{vp}", "null"):
            t.eq(_vreq(vp, mp, headers={"Origin": o_})[0], 200, f"Origin={o_}")
        for o_ in (parent, "https://evil.example", f"https://localhost:{vp}", f"http://localhost:{s.port}", "http://[::1"):
            t.eq(_vreq(vp, mp, headers={"Origin": o_})[0], 403, f"Origin={o_}")
        # 出さない物
        for path in ("/", "/editor.html", "/js/main.js", "/__replay/list", "/config/settings.json", "/blr", "/secret.txt",
                     "/blreplay/../bridge.js", "/blreplay/..%5c..%5csecret.txt", "/blreplay/%2e%2e/%2e%2e/secret.txt", "/blreplay/C:/x",
                     "/blreplay/build", "/blreplay/nope.js", "/replay-viewer/bridge.js"):
            t.ok(_vreq(vp, path)[0] in (403, 404), f"出さない: {path}")
        t.eq(_vreq(vp, "/__replay/list", method="POST", body=b"{}", headers={"Content-Type": "application/json", "X-NLM-Request": "1",
                                                                             "X-NLM-Token": s.serve.SESSION_TOKEN})[0], 403, "POST は断る")
        t.ok(_vreq(vp, "/bridge.js", method="PUT", body=b"x")[0] in (403, 501), "PUT も")
        t.eq(_vreq(vp, "/bridge.js", method="OPTIONS")[0], 403, "OPTIONS も")
        if len(R._VIEWERS.get(s.port, [])) == 2:   # ::1 でも同じ番号で待つ（::1 で待てない PC は 127.0.0.1 だけ）
            st, hd, b = _vreq(vp, "/blreplay/index.html", host=f"[::1]:{vp}", addr="::1")
            t.ok(st == 200 and tag.encode() in b, "::1 でも同じ物を出す")
        else:
            t.info("この PC は ::1 で待てない（127.0.0.1 だけで確かめた）")
        t.eq(H.req("GET", "/blreplay/index.html")[0] in (403, 404), True, "本体の番号では BL のリプレイアプリを出さない")
    finally:
        s.serve.REPLAYS = old
        s.serve.stop_viewers(s.port)


def test_viewer_index_without_body_and_stop_with_server(t):
    '''index.html に </body> が無ければ最後に足す（大文字の </BODY> も見る）。viewer は本体のサーバーを止める（shutdown・server_close）と一緒に止まる'''
    e = _env()
    s = H.server()
    serve = s.serve
    old = serve.REPLAYS
    serve.REPLAYS = e.store
    port = H._free_port()
    httpd = serve.make_server(port=port)
    import threading
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        h, _ = _kept(e, song="W", mapper="M")
        RF.write_replay(e.rdir, song="W", mapper="M", h=h)

        def call(path, obj):
            c = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
            c.request("POST", path, body=json.dumps(obj), headers={"Host": f"127.0.0.1:{port}", "X-NLM-Request": "1",
                                                                  "X-NLM-Token": serve.SESSION_TOKEN, "Content-Type": "application/json"})
            return json.loads(c.getresponse().read())
        rid = call("/__replay/list", {"song": {"name": "W", "mapper": "M"}})["items"][0]["id"]
        org = call("/__replay/open", {"id": rid})["origin"]
        vp = int(org.rsplit(":", 1)[1])
        idx = e.base / "replay-viewer" / "blreplay" / "index.html"
        idx.write_text("<html><BODY>x</BODY></html>", encoding="utf-8")
        b = _vreq(vp, "/blreplay/index.html")[2].decode()
        t.ok(b.index("bridge.js") < b.index("</BODY>"), "大文字の </BODY> の前")
        idx.write_text("<p>no body", encoding="utf-8")
        b = _vreq(vp, "/blreplay/index.html")[2].decode()
        t.ok(b.startswith("<p>no body<script src=\"/bridge.js\""), "</body> が無ければ最後に")
    finally:
        httpd.shutdown()
        httpd.server_close()
        serve.REPLAYS = old
    try:
        socket.create_connection(("127.0.0.1", vp), timeout=2).close()
        t.ok(False, "本体を止めたら viewer も止まる")
    except OSError:
        pass
    t.ok(port not in e.R._VIEWERS, "viewer の表からも消える")


# ---------------------------------------------------------------- app.py

def test_api_replay_pick_folder(t):
    '''Api.replay_pick_folder はダイアログで選ばれたフォルダだけを記録して status の形を返す（取り消し＝None・REPLAY の窓が無い時は None）。
    ダイアログは今のリプレイのフォルダから開く'''
    import test_native_access as TNA
    app, acc, out, store, base = TNA._setup()
    e = _env(env=False)
    e.store.steam_default = str(e.rdir)
    folder = e.tmp / "Picked"
    folder.mkdir()
    RF.write_replay(folder, name="a.bsor")
    wv = TNA._FakeWebview(str(folder))
    api = app._make_api(acc, str(base), {"dirty": False, "force": False}, wv, None, e.store)
    r = api.replay_pick_folder()
    t.eq(r, {"ok": True, "source": "chosen", "dirs": [{"path": str(folder), "count": 1}]}, "選んだフォルダ")
    t.eq(wv.calls[-1], ("folder", {"directory": str(e.rdir)}), "今のフォルダ（自動で見つけた所）から開く")
    t.ok(not acc.in_out_dir(str(folder)), "書き出し先の許可にはしない")
    wv.result = None
    t.eq(api.replay_pick_folder(), None, "取り消し")
    t.eq(e.store.status()["source"], "chosen", "取り消しでは変えない")
    wv.result = str(e.tmp / "gone")
    t.eq(api.replay_pick_folder(), {"ok": False, "error": "not-found"}, "無いフォルダ")
    no = app._make_api(acc, str(base), {"dirty": False, "force": False}, wv)
    t.eq(no.replay_pick_folder(), None, "REPLAY の窓が無い時は何もしない")


def test_fixture_keep_map_and_reset(t):
    '''テスト用の部品（replay_fixture）: keep_map で直接置いた控えも一覧で playable・folder_hash は書き出したフォルダの hash・reset で全部消える'''
    e = _env()
    files = RF.make_map(song="Fx", mapper="M", diffs=("Hard", "Expert"))
    h = RF.keep_map(e.data, files, egg=b"OggS-fx")
    lv = e.tmp / "exported"
    lv.mkdir()
    for n, b in files.items():
        (lv / n).write_bytes(b)
    t.eq(RF.folder_hash(lv), h, "書き出したフォルダの hash")
    RF.write_replay(e.rdir, song="Fx", mapper="M", h=h, flags=("exit",))
    items = e.store.list({"name": "Fx", "mapper": "M"})["items"]
    t.eq([(x["playable"], x["exit"], x["latest"]) for x in items], [(True, True, True)], "直接置いた控え")
    port = H._free_port()
    t.ok(e.store.open(items[0]["id"], None, port)["ok"], "開ける")
    e.R.stop_viewers(port)
    RF.reset(e.data, e.rdir)
    t.eq((list(e.rdir.iterdir()), (e.data / "replays").exists(), e.store.list({"name": "Fx", "mapper": "M"})["items"]), ([], False, []), "reset")

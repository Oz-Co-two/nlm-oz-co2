"""media_library.py（MEDIAライブラリの記録・走査・キャッシュ・ファイル読み出し・プレイ記録）。一時フォルダに作った小さな譜面で確かめる
（実際の CustomLevels・ネットには頼らない）"""
import json
import ntpath
import os
import struct
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import unitpy_helpers as H


def _ml():
    sys.path.insert(0, str(H.ROOT))
    import media_library
    return media_library


def _map_hash():
    sys.path.insert(0, str(H.ROOT))
    import map_hash
    return map_hash


# ---------------------------------------------------------------- 素材づくり

def _ogg_page(granule, serial, seq, payload, htype=0):
    segs, n = [], len(payload)
    while n >= 255:
        segs.append(255)
        n -= 255
    segs.append(n)
    return (b"OggS" + bytes([0, htype]) + struct.pack("<qII", granule, serial, seq) + b"\0\0\0\0"
            + bytes([len(segs)]) + bytes(segs) + payload)


def _ogg(rate, granule, serial=7, last_granule_minus1=False):
    """最小の OGG Vorbis（識別ヘッダーのページ・中身のページ・最後のページ）。granule÷rate 秒"""
    ident = b"\x01vorbis" + struct.pack("<I", 0) + bytes([2]) + struct.pack("<I", rate) + struct.pack("<iii", 0, 128000, 0) + b"\xb8\x01"
    out = _ogg_page(0, serial, 0, ident, htype=2) + _ogg_page(0, serial, 1, b"c" * 300)
    out += _ogg_page(granule, serial, 2, b"x" * 700)
    if last_granule_minus1:   # 最後のページで終わるパケットが無い（granule=-1）＝1つ前のページの値を使う
        out += _ogg_page(-1, serial, 3, b"y" * 255, htype=0)
    else:
        out += _ogg_page(granule, serial, 3, b"y" * 50, htype=4)
    return out


def _opus(granule, preskip=312, serial=9):
    head = b"OpusHead" + bytes([1, 2]) + struct.pack("<H", preskip) + struct.pack("<I", 44100) + b"\0\0\0"
    return _ogg_page(0, serial, 0, head, htype=2) + _ogg_page(granule, serial, 1, b"z" * 100, htype=4)


def _wav(sec, rate=8000):
    data = b"\0" * int(rate * 2 * sec)
    fmt = struct.pack("<HHIIHH", 1, 1, rate, rate * 2, 2, 16)
    body = b"WAVE" + b"fmt " + struct.pack("<I", len(fmt)) + fmt + b"LIST" + struct.pack("<I", 4) + b"INFO" + b"data" + struct.pack("<I", len(data)) + data
    return b"RIFF" + struct.pack("<I", len(body)) + body


def _w(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(data, (dict, list)):
        data = json.dumps(data).encode("utf-8")
    elif isinstance(data, str):
        data = data.encode("utf-8")
    path.write_bytes(data)
    return path


V2_INFO = {"_version": "2.0.0", "_songName": "Song V2", "_songSubName": "Sub", "_songAuthorName": "Artist2", "_levelAuthorName": "Mapper2",
           "_beatsPerMinute": 120, "_songFilename": "song.egg", "_coverImageFilename": "cover.jpg", "_environmentName": "BigMirrorEnvironment",
           "_difficultyBeatmapSets": [
               {"_beatmapCharacteristicName": "Standard", "_difficultyBeatmaps": [
                   {"_difficulty": "Expert", "_beatmapFilename": "ExpertStandard.dat", "_noteJumpMovementSpeed": 16,
                    "_noteJumpStartBeatOffset": -0.4000000059604645,
                    "_customData": {"_difficultyLabel": "Label E", "_requirements": ["Noodle Extensions"],
                                    "_suggestions": ["Chroma", "Cinema", "Unknown Mod"]}},
                   {"_difficulty": "ExpertPlus", "_beatmapFilename": "ExpertPlusStandard.dat", "_noteJumpMovementSpeed": 18,
                    "_noteJumpStartBeatOffset": 0}]},
               {"_beatmapCharacteristicName": "OneSaber", "_difficultyBeatmaps": [
                   {"_difficulty": "Hard", "_beatmapFilename": "Missing.dat", "_noteJumpMovementSpeed": 10, "_noteJumpStartBeatOffset": 0}]}]}
# 色ノーツ 4・6・20拍、ボム 2拍（色ノーツより前）、偽物（_fake）30拍、使われない種類(2) 50拍。壁2＋偽物1
V2_EXPERT = {"_version": "2.2.0", "_events": [{"_time": 99, "_type": 1, "_value": 1}],
             "_notes": [{"_time": 4, "_type": 0}, {"_time": 6, "_type": 1}, {"_time": 20, "_type": 0}, {"_time": 2, "_type": 3},
                        {"_time": 30, "_type": 1, "_customData": {"_fake": True}}, {"_time": 50, "_type": 2}],
             "_obstacles": [{"_time": 1, "_duration": 40}, {"_time": 3, "_duration": 1}, {"_time": 60, "_customData": {"_fake": True}}]}
V2_EXPERTPLUS = {"_version": "2.2.0", "_notes": [{"_time": i, "_type": i % 2} for i in range(16)], "_obstacles": []}

V3_INFO = {"_version": "2.1.0", "_songName": "Song V3", "_songAuthorName": "Artist3", "_levelAuthorName": "Mapper3",
           "_beatsPerMinute": 60, "_songFilename": "song.wav", "_coverImageFilename": "nope.png", "_environmentName": "WeaveEnvironment",
           "_difficultyBeatmapSets": [{"_beatmapCharacteristicName": "Standard", "_difficultyBeatmaps": [
               {"_difficulty": "Hard", "_beatmapFilename": "Hard.dat", "_noteJumpMovementSpeed": 12, "_noteJumpStartBeatOffset": 0},
               {"_difficulty": "Expert", "_beatmapFilename": "Expert.dat", "_noteJumpMovementSpeed": 14, "_noteJumpStartBeatOffset": 0}]}]}
# b の無い色ノーツ＝0拍。ボムは色ノーツより後ろ（v3 は長さに入れない）。チェーンのリンクは数えない
V3_HARD = {"version": "3.2.0", "colorNotes": [{"x": 1}, {"b": 2, "x": 0}, {"b": 8, "x": 2}], "bombNotes": [{"b": 20}],
           "obstacles": [{"b": 1, "d": 2}], "burstSliders": [{"b": 2, "tb": 3, "sc": 8}], "sliders": []}
# v2 の中身を残したまま v3 で保存し直した .dat（両方ある）＝v3 として数える
V3_HYBRID = {"_version": "2.2.0", "_notes": [{"_time": t, "_type": 0} for t in range(5)], "_obstacles": [{"_time": 1}],
             "version": "3.3.0", "colorNotes": [{"b": 1}, {"b": 3}], "bombNotes": [], "obstacles": []}

V4_INFO = {"version": "4.0.0", "song": {"title": "Song V4", "subTitle": "Sub4", "author": "Artist4"},
           "audio": {"songFilename": "song.mp3", "songDuration": 123.5, "audioDataFilename": "AudioData.dat", "bpm": 150,
                     "lufs": 0, "previewStartTime": 0, "previewDuration": 0},
           "songPreviewFilename": "song.mp3", "coverImageFilename": "cover.png",
           "environmentNames": ["WeaveEnvironment"], "colorSchemes": [],
           "difficultyBeatmaps": [
               {"characteristic": "Standard", "difficulty": "Easy", "beatmapAuthors": {"mappers": ["M1", "M2"], "lighters": ["L1"]},
                "environmentNameIdx": 0, "beatmapColorSchemeIdx": 0, "noteJumpMovementSpeed": 10, "noteJumpStartBeatOffset": 0.5,
                "lightshowDataFilename": "Lightshow.dat", "beatmapDataFilename": "Easy.dat",
                "customData": {"difficultyLabel": "EZ", "requirements": ["Vivify"]}},
               {"characteristic": "Standard", "difficulty": "Hard", "beatmapAuthors": {"mappers": ["M2", "M3"]},
                "environmentNameIdx": 0, "beatmapColorSchemeIdx": 0, "noteJumpMovementSpeed": 14, "noteJumpStartBeatOffset": 0,
                "lightshowDataFilename": "Lightshow.dat", "beatmapDataFilename": "Hard.dat"}]}
V4_EASY = {"version": "4.0.0", "colorNotes": [{"b": 4, "i": 0}, {"b": 8, "i": 1}, {"b": 14, "i": 0}],
           "colorNotesData": [{"x": 1, "y": 0, "c": 0, "d": 1}, {"x": 2, "y": 0, "c": 1, "d": 1}],
           "bombNotes": [{"b": 1, "i": 0}], "bombNotesData": [{"x": 0, "y": 0}],
           "obstacles": [{"b": 2, "i": 0}, {"b": 3, "i": 0}], "obstaclesData": [{"d": 1, "x": 0, "y": 0, "w": 1, "h": 5}],
           "chains": [{"hb": 4, "tb": 5, "i": 0, "ci": 0}], "chainsData": [{"tx": 1, "ty": 1, "c": 4, "s": 1}], "arcs": [], "arcsData": []}
V4_HARD = {"version": "4.0.0", "colorNotes": [{"b": b, "i": 0} for b in (0, 2, 4, 6, 8, 10)], "colorNotesData": [{"x": 0}],
           "bombNotes": [], "bombNotesData": [], "obstacles": [], "obstaclesData": []}


def _make_lib(base):
    """一時フォルダにライブラリ（譜面 v2/v3/v4・壊れた譜面・深い階層・譜面の外の音源と画像）を作る → (根, 情報)"""
    root = base / "Lib"
    v2 = root / "1a2b (Song V2 - Mapper)"
    _w(v2 / "Info.dat", b"\xef\xbb\xbf" + json.dumps(V2_INFO, indent=2).replace("\n", "\r\n").encode("utf-8"))   # BOM・CRLF 付き
    _w(v2 / "ExpertStandard.dat", V2_EXPERT)
    _w(v2 / "ExpertPlusStandard.dat", V2_EXPERTPLUS)
    _w(v2 / "song.egg", _ogg(44100, 44100 * 90))
    _w(v2 / "cover.jpg", b"\xff\xd8\xff\xe0jpeg")
    _w(v2 / "sub" / "extra.mp3", b"ID3")   # 譜面フォルダの中へは降りない
    os.utime(v2 / "Info.dat", (1600000000, 1600000000))   # 推定ダウンロード日＝フォルダの作成日と Info.dat の更新日の早い方
    v3 = root / "c3d4 (Song V3 - Mapper)"
    _w(v3 / "INFO.DAT", V3_INFO)   # 大文字の名前でも譜面
    _w(v3 / "Hard.dat", V3_HARD)
    _w(v3 / "Expert.dat", V3_HYBRID)
    _w(v3 / "song.wav", _wav(2.0))
    v4 = root / "My V4 Map"
    _w(v4 / "Info.dat", V4_INFO)
    _w(v4 / "Easy.dat", V4_EASY)
    _w(v4 / "Hard.dat", V4_HARD)
    _w(v4 / "Lightshow.dat", {"version": "4.0.0", "basicEvents": []})
    _w(v4 / "AudioData.dat", {"version": "4.0.0", "songChecksum": "", "songSampleCount": 0, "songFrequency": 44100, "bpmData": []})
    _w(v4 / "song.mp3", b"ID3\x03mp3")
    _w(v4 / "cover.png", b"\x89PNG")
    _w(root / "dead (Broken - X)" / "Info.dat", b"{not json")
    _w(root / "Music Folder" / "Artist" / "track one.mp3", b"ID3")
    _w(root / "Music Folder" / "art.PNG", b"\x89PNG")
    _w(root / "notes.txt", "x")
    _w(root / "top.ogg", _ogg(48000, 48000 * 3))
    deep = root.joinpath(*["d%d" % i for i in range(1, 9)])   # 根から8階層下のフォルダ＝まだたどる
    _w(deep / "deep8.mp3", b"ID3")
    _w(deep / "aaaa (Deep Map - X)" / "Info.dat", {"_version": "2.0.0", "_songName": "Deep", "_beatsPerMinute": 100,
                                                   "_difficultyBeatmapSets": []})
    _w(deep / "d9" / "deep9.mp3", b"ID3")   # 9階層下はたどらない
    _w(deep / "d9" / "bbbb (Too Deep - X)" / "Info.dat", {"_version": "2.0.0", "_songName": "TooDeep", "_difficultyBeatmapSets": []})
    deep_rel = "/".join("d%d" % i for i in range(1, 9))
    return root, {"v2": v2, "v3": v3, "v4": v4, "deep_rel": deep_rel}


def _new(base=None, **kw):
    """(media_library, MediaLibrary, 一時フォルダ)。データフォルダは一時フォルダの data"""
    ML = _ml()
    base = base or Path(tempfile.mkdtemp(prefix="nlm_unitpy_ml_"))
    kw.setdefault("opener", lambda p: None)
    kw.setdefault("default_playdata", str(base / "nope" / "PlayerData.dat"))
    return ML, ML.MediaLibrary(str(base / "data"), **kw), base


def _scan_all(ml, lid, timeout=30, rescan=False):
    if rescan:
        ml.rescan(lid)
    maps, nxt, t0 = [], 0, time.time()
    while True:
        r = ml.scan(lid, nxt)
        maps += r["maps"]
        nxt = r["next"]
        if r["done"]:
            return maps, r
        if time.time() - t0 > timeout:
            raise AssertionError("走査が終わらない")
        time.sleep(0.01)


def _err(fn, *a):
    """LibError の code（起きなければ None）"""
    ML = _ml()
    try:
        fn(*a)
    except ML.LibError as e:
        return e.code
    return None


def _expected_hash(folder, info_name):
    mh = _map_hash()
    ib = (folder / info_name).read_bytes()
    info = json.loads(ib.decode("utf-8-sig"))
    fb = [(folder / n).read_bytes() if (folder / n).is_file() else None for n in mh.files_for_hash(info)]
    return mh.compute(ib, fb)


def _junction(link, target):
    try:
        os.symlink(str(target), str(link), target_is_directory=True)
        return True
    except (OSError, NotImplementedError):
        r = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)], capture_output=True)
        return r.returncode == 0


# ---------------------------------------------------------------- 走査の値

def test_scan_v2_values(t):
    '''v2 の譜面: 曲の情報・音源(OGG)の長さ・難易度ごとの数（偽物・使われない種類は数えない）・長さ（ボムも含めた最初〜最後）・NPS・Mod・ハッシュ'''
    ML, ml, base = _new()
    root, fx = _make_lib(base)
    lid = ml.approve_dir(str(root))["id"]
    maps, r = _scan_all(ml, lid)
    t.ok(r["ok"], "走査できた")
    m = next(x for x in maps if x["rel"] == "1a2b (Song V2 - Mapper)")
    for k, v in {"key": "1a2b", "fmt": 2, "name": "Song V2", "subName": "Sub", "artist": "Artist2", "mapper": "Mapper2",
                 "bpm": 120.0, "env": "BigMirrorEnvironment", "songFile": "song.egg", "coverFile": "cover.jpg",
                 "durationSec": 90.0, "dlTime": 1600000000}.items():
        t.eq(m[k], v, k)
    t.eq(m["hash"], _expected_hash(fx["v2"], "Info.dat"), "ハッシュ＝map_hash（BOM・CRLF のまま）")
    t.eq(len(m["hash"]), 40, "ハッシュは40文字")
    d = {(x["char"], x["diff"]): x for x in m["diffs"]}
    e = d[("Standard", "Expert")]
    t.eq((e["notes"], e["bombs"], e["walls"]), (3, 1, 2), "Expert のノーツ・ボム・壁")
    t.eq((e["lengthSec"], e["nps"]), (9.0, 0.333), "Expert の長さ＝ボム(2拍)〜最後の色ノーツ(20拍)・NPS")
    t.eq((e["label"], e["file"], e["njs"], e["offset"]), ("Label E", "ExpertStandard.dat", 16.0, -0.4), "名前・ファイル・NJS・オフセット")
    t.eq(e["mods"], ["chroma", "noodle", "cinema"], "必要/推奨の Mod（知らない Mod は入れない）")
    t.eq(e["req"], ["noodle"], "必要な Mod だけ（推奨の Chroma・Cinema は入れない）")
    ep = d[("Standard", "ExpertPlus")]
    t.eq((ep["notes"], ep["lengthSec"], ep["nps"], ep["mods"]), (16, 7.5, 2.133, []), "ExpertPlus")
    t.eq(ep["req"], [], "Mod の指定が無ければ req も空")
    miss = d[("OneSaber", "Hard")]
    t.eq((miss["notes"], miss["lengthSec"], miss["file"]), (None, None, "Missing.dat"), "ファイルの無い難易度は数が不明")
    t.eq(r["skipped"], 1, "Info.dat が壊れた譜面は飛ばす")
    t.ok(all(x["rel"] != "dead (Broken - X)" for x in maps), "壊れた譜面は結果に入れない")


def test_download_date_from_metadata(t):
    '''ダウンロード日は metadata.json の addedDate を優先し、無い・壊れている・ありえない日付なら推定（作成日と Info.dat の更新日の早い方）'''
    import datetime
    ML, ml, base = _new()
    root, fx = _make_lib(base)
    meta = fx["v2"] / "metadata.json"
    added = "2026-03-30T21:15:50.573"
    meta.write_text(json.dumps({"addedDate": added}), encoding="utf-8")
    lid = ml.approve_dir(str(root))["id"]
    maps, r = _scan_all(ml, lid)
    m = next(x for x in maps if x["rel"] == "1a2b (Song V2 - Mapper)")
    t.eq(m["dlTime"], int(datetime.datetime.fromisoformat(added).timestamp()), "addedDate（この PC の時刻として読む）")
    for bad in ("{broken", json.dumps({"addedDate": "x"}), json.dumps({"addedDate": "1999-01-01T00:00:00"})):
        meta.write_text(bad, encoding="utf-8")
        maps, r = _scan_all(ml, lid, rescan=True)
        m = next(x for x in maps if x["rel"] == "1a2b (Song V2 - Mapper)")
        t.eq(m["dlTime"], 1600000000, f"使えない metadata.json は推定に戻る: {bad[:30]}")


def test_record_reload_when_file_changes(t):
    '''記録ファイル（library.json）が外で書き換わったら、次の list で読み直す（自動テストが記録を用意する時）。外れたライブラリは list から消える'''
    ML, ml, base = _new()
    root, fx = _make_lib(base)
    t.eq(ml.list(), [], "最初は空")
    rec = base / "data" / "config" / "library.json"
    rec.parent.mkdir(parents=True, exist_ok=True)
    rec.write_text(json.dumps({"libs": [{"path": str(root)}]}), encoding="utf-8")
    libs = ml.list()
    t.eq([(l["name"], l["state"]) for l in libs], [("Lib", "ok")], "書き足した記録が出る")
    maps, r = _scan_all(ml, libs[0]["id"])
    t.ok(len(maps) > 0, "そのまま走査できる")
    time.sleep(0.02)
    rec.write_text(json.dumps({"libs": []}), encoding="utf-8")
    t.eq(ml.list(), [], "外した記録は消える")
    t.eq(_err(ml.scan, libs[0]["id"]), "unknown-lib", "外したライブラリは使えない")


def test_scan_v3_and_hybrid(t):
    '''v3 の譜面: colorNotes（チェーンのリンクは数えない・b の無いノーツは0拍）・長さにボムを入れない・v2 と v3 の両方を持つ .dat は v3 で数える・WAV の長さ'''
    ML, ml, base = _new()
    root, fx = _make_lib(base)
    lid = ml.approve_dir(str(root))["id"]
    maps, r = _scan_all(ml, lid)
    m = next(x for x in maps if x["rel"] == "c3d4 (Song V3 - Mapper)")
    t.eq((m["fmt"], m["name"], m["bpm"], m["songFile"], m["coverFile"], m["durationSec"]),
         (2, "Song V3", 60.0, "song.wav", None, 2.0), "曲の情報（無いカバーは null）・WAV の長さ")
    t.eq(m["hash"], _expected_hash(fx["v3"], "INFO.DAT"), "ハッシュ")
    d = {x["diff"]: x for x in m["diffs"]}
    t.eq((d["Hard"]["notes"], d["Hard"]["bombs"], d["Hard"]["walls"]), (3, 1, 1), "Hard の数")
    t.eq((d["Hard"]["lengthSec"], d["Hard"]["nps"]), (8.0, 0.375), "Hard の長さ（0〜8拍・ボムの20拍は入れない）")
    t.eq((d["Expert"]["notes"], d["Expert"]["bombs"], d["Expert"]["walls"], d["Expert"]["lengthSec"]), (2, 0, 0, 2.0),
         "v2 の中身も残る .dat は version を見て v3 として数える")


def test_scan_v4_values(t):
    '''v4 の譜面: song/audio の項目・マッパー（全難易度をつなぐ）・音源の長さ（audio.songDuration）・数・ハッシュ
    マッパーは全難易度の mappers を重ねずにつなぐ。音源（mp3）が測れなければ audio.songDuration。
    数は *Data への添字の配列の長さ。ハッシュは map_hash の並び（音の情報・ライトのファイル込み）と一致'''
    ML, ml, base = _new()
    root, fx = _make_lib(base)
    lid = ml.approve_dir(str(root))["id"]
    maps, r = _scan_all(ml, lid)
    m = next(x for x in maps if x["rel"] == "My V4 Map")
    for k, v in {"key": None, "fmt": 4, "name": "Song V4", "subName": "Sub4", "artist": "Artist4", "mapper": "M1, M2, M3",
                 "bpm": 150.0, "env": "WeaveEnvironment", "songFile": "song.mp3", "coverFile": "cover.png", "durationSec": 123.5}.items():
        t.eq(m[k], v, k)
    t.eq(m["hash"], _expected_hash(fx["v4"], "Info.dat"), "ハッシュ＝map_hash.compute（files_for_hash の並び）")
    d = {x["diff"]: x for x in m["diffs"]}
    e = d["Easy"]
    t.eq((e["notes"], e["bombs"], e["walls"], e["lengthSec"], e["nps"]), (3, 1, 2, 4.0, 0.75), "Easy の数・長さ・NPS")
    t.eq((e["label"], e["file"], e["njs"], e["offset"], e["mods"]), ("EZ", "Easy.dat", 10.0, 0.5, ["vivify"]), "Easy の項目")
    t.eq(e["req"], ["vivify"], "v4 の requirements は必要な Mod")
    t.eq((d["Hard"]["notes"], d["Hard"]["lengthSec"], d["Hard"]["nps"]), (6, 4.0, 1.5), "Hard")


def test_length_rule_matches_beatsaver(t):
    '''長さ・NPS の規則: 最初〜最後のノーツの拍を基本の BPM で秒にし、小数3桁に四捨五入（実データの 103fb ExpertPlus と同じ形: 160BPM・6〜331.5拍＝122.063秒）'''
    ML = _ml()
    notes = [{"_time": 6, "_type": 0}] + [{"_time": 6 + i * 0.25, "_type": i % 2} for i in range(1, 1235)] + [{"_time": 331.5, "_type": 1}]
    c = ML.count_diff({"_version": "2.0.0", "_notes": notes, "_obstacles": [{"_time": 331.6, "_duration": 1}],
                       "_events": [{"_time": 400}]}, 160.0)
    t.eq((c["notes"], c["lengthSec"], c["nps"]), (1236, 122.063, 10.126), "BeatSaver の seconds・nps と同じ値")
    t.eq(ML._round_half_up(121.3125), 121.313, "四捨五入（偶数への丸めではない）")
    t.eq(ML.count_diff({"_notes": [{"_time": 1, "_type": 0}], "_obstacles": []}, None)["lengthSec"], None, "BPM が無ければ長さは不明")
    t.eq(ML.count_diff({"_notes": [], "_obstacles": []}, 120)["nps"], 0.0, "ノーツが無ければ NPS は 0")
    t.eq(ML.count_diff({"foo": 1}, 120)["notes"], None, "形が分からなければ不明")
    bad = ML.count_diff({"_notes": [{"_time": float("nan"), "_type": 0}, {"_time": True, "_type": 1}, {"_time": 1e300, "_type": 0},
                                    {"_time": 2, "_type": 0}, {"_time": 4, "_type": 1}, "x", None], "_obstacles": ["x"]}, 60)
    t.eq((bad["notes"], bad["lengthSec"], bad["walls"]), (5, 2.0, 0), "おかしな拍は長さに使わない（数には入る）・変な要素は飛ばす")


def test_scan_files_and_depth(t):
    '''走査の範囲: 譜面フォルダの外の音源・画像を files へ・深さ8まで・譜面フォルダの中へは降りない・from 以降を返す
    他の種類のファイルは入れない。根から9階層下の譜面フォルダまで見つけ、10階層下は見つけない'''
    ML, ml, base = _new()
    root, fx = _make_lib(base)
    lid = ml.approve_dir(str(root))["id"]
    maps, r = _scan_all(ml, lid)
    files = sorted((f["kind"], f["rel"], f["name"]) for f in r["files"])
    t.eq(files, sorted([("music", "Music Folder/Artist/track one.mp3", "track one"), ("image", "Music Folder/art.PNG", "art"),
                        ("music", "top.ogg", "top"), ("music", fx["deep_rel"] + "/deep8.mp3", "deep8")]), "files")
    rels = sorted(m["rel"] for m in maps)
    t.eq(rels, sorted(["1a2b (Song V2 - Mapper)", "c3d4 (Song V3 - Mapper)", "My V4 Map", fx["deep_rel"] + "/aaaa (Deep Map - X)"]), "譜面")
    t.eq((r["progress"]["done"], r["progress"]["total"]), (5, 5), "進み具合（壊れた譜面も処理した数に入る）")
    t.eq(r["next"], 4, "next＝返した数")
    r2 = ml.scan(lid, 2)
    t.eq((len(r2["maps"]), r2["next"]), (2, 4), "from 以降だけ返す")
    t.eq(ml.scan(lid, 99)["maps"], [], "範囲の外は空")


def test_cache_reuse_and_invalidate(t):
    '''2回目の起動（新しい MediaLibrary）はキャッシュを使い、解析し直さない。.dat を更新した曲だけ作り直し、消した曲はキャッシュからも消える'''
    ML, ml, base = _new()
    root, fx = _make_lib(base)
    lid = ml.approve_dir(str(root))["id"]
    first, _ = _scan_all(ml, lid)
    calls = []
    orig = ML.parse_map

    def counting(folder, *a):
        calls.append(os.path.basename(folder))
        return orig(folder, *a)
    ML.parse_map = counting
    try:
        ml2 = ML.MediaLibrary(str(base / "data"), opener=lambda p: None, default_playdata=str(base / "nope.dat"))
        t.eq(ml2.list()[0]["id"], lid, "記録は次の起動でも残る")
        second, _ = _scan_all(ml2, lid)
        t.eq(json.dumps(second, sort_keys=True), json.dumps(first, sort_keys=True), "同じ結果")
        t.eq(calls, ["dead (Broken - X)"], "解析し直すのは前回も読めなかった物だけ")
        calls.clear()
        p = fx["v2"] / "ExpertStandard.dat"
        d = dict(V2_EXPERT)
        d["_notes"] = V2_EXPERT["_notes"] + [{"_time": 21, "_type": 1}]
        _w(p, d)
        st = p.stat()
        os.utime(p, ns=(st.st_atime_ns, st.st_mtime_ns + 5_000_000_000))
        import shutil
        shutil.rmtree(fx["v3"])
        third, _ = _scan_all(ml2, lid, rescan=True)
        t.eq(sorted(calls), sorted(["1a2b (Song V2 - Mapper)", "dead (Broken - X)"]), "更新した曲だけ作り直す")
        m = next(x for x in third if x["rel"] == "1a2b (Song V2 - Mapper)")
        e = next(x for x in m["diffs"] if x["diff"] == "Expert")
        t.eq(e["notes"], 4, "新しい数")
        t.eq(m["hash"], _expected_hash(fx["v2"], "Info.dat"), "新しいハッシュ")
        t.ok(all(x["rel"] != "c3d4 (Song V3 - Mapper)" for x in third), "消した曲は出ない")
        cache = json.loads((base / "data" / "config" / "library_cache.json").read_text(encoding="utf-8"))
        t.ok("c3d4 (Song V3 - Mapper)" not in cache["libs"][lid], "消した曲はキャッシュからも消える")
        (base / "data" / "config" / "library_cache.json").write_text("{壊れた", encoding="utf-8")
        calls.clear()
        ml3 = ML.MediaLibrary(str(base / "data"), opener=lambda p: None, default_playdata=str(base / "nope.dat"))
        fourth, r = _scan_all(ml3, lid)
        t.ok(r["ok"] and len(fourth) == len(third), "壊れたキャッシュは捨てて作り直す")
        t.eq(len(calls), len(third) + 1, "全部を解析し直した")
    finally:
        ML.parse_map = orig


def test_scan_runs_once_per_library(t):
    '''走査は裏で進み、呼び出しはすぐ返る。読み直しを続けて押しても、同じライブラリを同時に2つ走査しない。途中の結果も next で重ねずに受け取れる'''
    ML, ml, base = _new()
    root, fx = _make_lib(base)
    lid = ml.approve_dir(str(root))["id"]
    orig = ML.parse_map
    state = {"now": 0, "max": 0}
    lock = threading.Lock()

    def slow(*a):
        with lock:
            state["now"] += 1
            state["max"] = max(state["max"], state["now"])
        time.sleep(0.05)
        try:
            return orig(*a)
        finally:
            with lock:
                state["now"] -= 1
    ML.parse_map = slow
    try:
        t0 = time.time()
        r = ml.scan(lid, 0)
        t.ok(time.time() - t0 < 0.5 and not r["done"], "すぐ返る（まだ終わっていない）")
        ml.rescan(lid)
        ml.rescan(lid)
        maps, r = _scan_all(ml, lid)
        t.eq(state["max"], 1, "同時に走る解析は1つだけ")
        t.eq(len(maps), 4, "最後の走査の結果が全部そろう")
        t.eq(len({m["rel"] for m in maps}), 4, "重なりなし")
    finally:
        ML.parse_map = orig


# ---------------------------------------------------------------- 記録

def test_record_persist_and_remove(t):
    '''記録（library.json）: 同じフォルダは1つ・次の起動でも残る・remove で消え（キャッシュも）・未記録の id は拒否・壊れた記録や変なパスは読み飛ばす'''
    ML, ml, base = _new()
    root, fx = _make_lib(base)
    a = ml.approve_dir(str(root))
    t.eq(ml.approve_dir(str(root).upper()), a, "同じフォルダ（大文字小文字違い）は同じ記録")
    t.eq(a["name"], "Lib", "名前はフォルダ名")
    t.eq([(x["id"], x["state"]) for x in ml.list()], [(a["id"], "ok")], "list")
    t.eq(_err(ml.approve_dir, "relative\\path"), "bad-path", "相対パスは記録しない")
    t.eq(_err(ml.approve_dir, str(base / "none")), "not-found", "無いフォルダ")
    _scan_all(ml, a["id"])
    rec = json.loads((base / "data" / "config" / "library.json").read_text(encoding="utf-8"))
    t.eq(rec["libs"], [{"path": str(root)}], "記録の中身")
    t.eq(ml.remove(a["id"]), {"ok": True}, "remove")
    t.eq(ml.list(), [], "消えた")
    t.eq(_err(ml.scan, a["id"], 0), "unknown-lib", "消した id は使えない")
    t.eq(_err(ml.read_file, "nope", "", "x.dat"), "unknown-lib", "未記録の id")
    t.eq(_err(ml.remove, "nope"), "unknown-lib", "未記録の id は消せない")
    cache = json.loads((base / "data" / "config" / "library_cache.json").read_text(encoding="utf-8"))
    t.ok(a["id"] not in cache["libs"], "キャッシュからも消える")
    (base / "data" / "config" / "library.json").write_text(json.dumps(
        {"libs": [{"path": "relative"}, {"path": "\\\\?\\C:\\x"}, {"path": 5}, "x", {"path": str(root)}], "playdata": "\\??\\C:\\x"}),
        encoding="utf-8")
    ml2 = ML.MediaLibrary(str(base / "data"), default_playdata=str(base / "nope.dat"))
    t.eq([x["path"] for x in ml2.list()], [str(root)], "使えるパスだけ読む")
    t.eq(ml2.playdata_status()["mode"], "auto", "変なプレイ記録の場所は読まない")
    (base / "data" / "config" / "library.json").write_text("{壊れた", encoding="utf-8")
    t.eq(ML.MediaLibrary(str(base / "data"), default_playdata=str(base / "nope.dat")).list(), [], "壊れた記録は空")


def test_missing_library(t):
    '''記録したフォルダが無くなった時: list は missing、走査は ok=false・error=missing で終わる'''
    ML, ml, base = _new()
    d = base / "Gone"
    d.mkdir()
    lid = ml.approve_dir(str(d))["id"]
    d.rmdir()
    t.eq(ml.list()[0]["state"], "missing", "list")
    maps, r = _scan_all(ml, lid)
    t.eq((r["ok"], r["done"], r.get("error"), maps), (False, True, "missing", []), "走査")


# ---------------------------------------------------------------- ファイル読み出し・フォルダを開く

def test_read_file(t):
    '''read_file: .dat/.json/音源/画像を Content-Type 付きで返す。files の rel（ファイルまで書いた形）でも読める'''
    ML, ml, base = _new()
    root, fx = _make_lib(base)
    lid = ml.approve_dir(str(root))["id"]
    rel = "1a2b (Song V2 - Mapper)"
    b, ct = ml.read_file(lid, rel, "Info.dat")
    t.eq((b, ct), ((fx["v2"] / "Info.dat").read_bytes(), "application/json"), "Info.dat")
    t.eq(ml.read_file(lid, rel, "song.egg")[1], "audio/ogg", "song.egg")
    t.eq(ml.read_file(lid, rel, "cover.jpg")[1], "image/jpeg", "cover.jpg")
    t.eq(ml.read_file(lid, "Music Folder/Artist/track one.mp3", ""), (b"ID3", "audio/mpeg"), "files の rel")
    t.eq(ml.read_file(lid, "Music Folder", "art.PNG")[1], "image/png", "大文字の拡張子")
    t.eq(_err(ml.read_file, lid, rel, "none.dat"), "not-found", "無いファイル")
    t.eq(_err(ml.read_file, lid, "", "notes.txt"), "not-allowed", "許可していない種類")
    t.eq(_err(ml.read_file, lid, rel, ""), "not-allowed", "フォルダは読めない")
    t.eq(_err(ml.read_file, lid, "", ""), "not-allowed", "根は読めない")
    old = ML.MAX_READ
    ML.MAX_READ = 10
    try:
        t.eq(_err(ml.read_file, lid, rel, "song.egg"), "too-large", "大きすぎるファイル")
    finally:
        ML.MAX_READ = old


def test_read_file_blocks_escape(t):
    '''read_file: .. ・ドライブ名・\\・:（代替データストリーム）・NUL・絶対パスを含む rel/name は拒否。根の外の実在するファイルも読めない'''
    ML, ml, base = _new()
    root, fx = _make_lib(base)
    _w(base / "secret.dat", "{}")
    lid = ml.approve_dir(str(root))["id"]
    bad = [("..", "secret.dat"), ("1a2b (Song V2 - Mapper)/..", "Info.dat"), ("../..", "x.dat"), ("", "../secret.dat"),
           ("", "..\\secret.dat"), ("C:", "x.dat"), ("C:\\Windows", "win.ini"), ("1a2b (Song V2 - Mapper)", "C:x.dat"),
           ("a\\..\\..", "secret.dat"), ("1a2b (Song V2 - Mapper)", "Info.dat:evil"), ("x\0", "a.dat"), ("", "a\0.dat"),
           ("/1a2b (Song V2 - Mapper)", "Info.dat"), ("1a2b (Song V2 - Mapper)//", "Info.dat"), (".", "secret.dat"),
           ("\\\\server\\share", "a.dat"), (None, "a.dat"), ("x" * 2000, "a.dat")]
    for rel, name in bad:
        t.eq(_err(ml.read_file, lid, rel, name), "bad-path", "拒否: %r %r" % (rel, name))
    t.eq(_err(ml.read_file, lid, "1a2b (Song V2 - Mapper)", "a/b.dat"), "bad-path", "名前に区切り文字")


def test_junction_not_followed(t):
    '''ライブラリの中のジャンクションは、走査でたどらず、read_file・open_folder・rating_input でも外へ出られない'''
    ML, ml, base = _new()
    root, fx = _make_lib(base)
    outside = base / "Outside"
    _w(outside / "eeee (Outside - X)" / "Info.dat", V2_INFO)
    _w(outside / "eeee (Outside - X)" / "ExpertStandard.dat", V2_EXPERT)
    _w(outside / "outside.mp3", b"ID3")
    if not _junction(root / "linked", outside):
        t.skip("リンクを作れない環境")
    opened = []
    ml.opener = opened.append
    lid = ml.approve_dir(str(root))["id"]
    maps, r = _scan_all(ml, lid)
    t.ok(all(not m["rel"].startswith("linked") for m in maps), "譜面をたどらない")
    t.ok(all(not f["rel"].startswith("linked") for f in r["files"]), "ファイルをたどらない")
    t.eq(_err(ml.read_file, lid, "linked/eeee (Outside - X)", "Info.dat"), "not-allowed", "read_file")
    t.eq(_err(ml.read_file, lid, "linked", "outside.mp3"), "not-allowed", "read_file（音源）")
    t.eq(_err(ml.open_folder, lid, "linked"), "not-allowed", "open_folder")
    t.eq(_err(ml.rating_input, lid, "linked/eeee (Outside - X)"), "not-allowed", "rating_input")
    t.eq(opened, [], "開いていない")


def test_open_folder(t):
    '''open_folder: 根の中の実在するフォルダだけ開く（開く関数は差し替え）。ファイル・無いフォルダ・..・未記録の id は開かない'''
    ML, ml, base = _new()
    root, fx = _make_lib(base)
    opened = []
    ml.opener = opened.append
    lid = ml.approve_dir(str(root))["id"]
    t.eq(ml.open_folder(lid, "1a2b (Song V2 - Mapper)"), {"ok": True}, "譜面フォルダ")
    t.eq(ml.open_folder(lid, ""), {"ok": True}, "根")
    t.eq([os.path.normcase(p) for p in opened], [os.path.normcase(str(fx["v2"])), os.path.normcase(str(root))], "開いた場所")
    t.eq(_err(ml.open_folder, lid, "notes.txt"), "not-found", "ファイル")
    t.eq(_err(ml.open_folder, lid, "none"), "not-found", "無いフォルダ")
    t.eq(_err(ml.open_folder, lid, ".."), "bad-path", "..")
    t.eq(_err(ml.open_folder, "nope", ""), "unknown-lib", "未記録の id")
    t.eq(len(opened), 2, "失敗した時は開かない")


# ---------------------------------------------------------------- UNC

class _NetGuard:
    """ntpath の実体解決・存在確認を差し替え、ネットワーク上らしいパス（区切り文字で始まる・?を含む）では本物を呼ばずに記録だけする
    （テストでは実際に接続しない）。dirs に入れた字面のフォルダは「有る」と答える（test_native_access.py の _NetGuard と同じ考え方）"""
    NAMES = ("realpath", "isfile", "isdir", "exists")

    def __init__(self, dirs=()):
        self.dirs = {ntpath.normcase(d) for d in dirs}
        self.touched = []

    def __enter__(self):
        self.orig = {n: getattr(ntpath, n) for n in self.NAMES}
        for n in self.NAMES:
            setattr(ntpath, n, self._wrap(n))
        self._stat, self._scandir = os.stat, os.scandir
        os.stat = self._wrap_fn(os.stat, "stat")
        os.scandir = self._wrap_fn(os.scandir, "scandir")
        return self

    def __exit__(self, *exc):
        for n, f in self.orig.items():
            setattr(ntpath, n, f)
        os.stat, os.scandir = self._stat, self._scandir

    @staticmethod
    def _net(s):
        return s.replace("/", "\\").startswith("\\") or "?" in s

    def _wrap(self, n):
        def f(p, *a, **k):
            s = str(p)
            if self._net(s):
                self.touched.append((n, s))
                if n == "realpath":
                    return ntpath.abspath(s)
                return n == "isdir" and ntpath.normcase(ntpath.normpath(s)) in self.dirs
            return self.orig[n](p, *a, **k)
        return f

    def _wrap_fn(self, fn, n):
        def f(p=".", *a, **k):
            if isinstance(p, str) and self._net(p):
                self.touched.append((n, p))
                raise FileNotFoundError(p)
            return fn(p, *a, **k)
        return f


def test_unc_library(t):
    '''UNC のライブラリ: ダイアログで選んだ字面の中だけ触る。その外・別のサーバー・.. で外へ・デバイスパスは、存在確認もせずに断る'''
    ML, ml, base = _new()
    lib = "\\\\nas-test.invalid\\share\\Songs"
    with _NetGuard(dirs=[lib]) as g:
        a = ml.approve_dir(lib)
        t.eq(a["name"], "Songs", "名前")
        t.ok(ml.may_touch(lib + "\\1a2b\\Info.dat"), "記録した字面の中")
        t.ok(ml.may_touch("//NAS-TEST.invalid/share/songs/x"), "大文字小文字・区切り文字の違いは同じ扱い")
        for p in ("\\\\nas-test.invalid\\share\\Other\\a.dat", "\\\\other-test.invalid\\share\\Songs\\a.dat",
                  lib + "\\..\\Other\\a.dat", "\\\\?\\UNC\\nas-test.invalid\\share\\Songs\\a.dat", "\\??\\UNC\\nas-test.invalid\\share\\Songs",
                  "\\x\\a.dat", "relative.dat", ""):
            t.ok(not ml.may_touch(p), "触らない: " + p)
        n = len(g.touched)
        t.ok(not ml.may_touch("\\\\evil-test.invalid\\x\\a.dat"), "判定は字面だけ")
        t.eq(len(g.touched), n, "判定のために触っていない")
        t.eq(ml.list()[0]["state"], "ok", "list（記録した UNC は確かめてよい）")
        t.eq(_err(ml.read_file, a["id"], "1a2b", "Info.dat"), "not-found", "中のファイルは存在確認まで進む（テストでは無い扱い）")
        t.ok(any(s.startswith(lib) for _, s in g.touched), "記録した UNC には触る")
        t.ok(all(s.lower().startswith(lib.lower()) for _, s in g.touched), "記録した UNC の外には触らない")
        maps, r = _scan_all(ml, a["id"])
        t.eq((r["ok"], maps), (True, []), "走査（テストでは中身なし）")
        t.ok(all(s.lower().startswith(lib.lower()) for _, s in g.touched), "走査でも外には触らない")
        rec = json.loads((base / "data" / "config" / "library.json").read_text(encoding="utf-8"))
        t.eq(rec["libs"], [{"path": lib}], "選んだ字面のまま記録")
        ml2 = ML.MediaLibrary(str(base / "data"), default_playdata=str(base / "nope.dat"))
        t.ok(ml2.may_touch(lib + "\\x\\Info.dat"), "次の起動でも有効")


# ---------------------------------------------------------------- プレイ記録

def _playerdata(hashes, name="SecretPlayerName", pid="76561190000000000"):
    h1, h2 = hashes
    return {"version": "2.0.26", "guestPlayers": [], "localPlayers": [{
        "playerId": pid, "playerName": name, "agreedToEula": True,
        "levelsStatsData": [
            {"levelId": "custom_level_" + h1.upper(), "difficulty": 3, "beatmapCharacteristicName": "Standard", "highScore": 123456,
             "maxCombo": 300, "fullCombo": True, "maxRank": 6, "validScore": True, "playCount": 12},
            {"levelId": "custom_level_" + h1.upper(), "difficulty": 4, "beatmapCharacteristicName": "Standard", "highScore": 0,
             "maxCombo": 0, "fullCombo": False, "maxRank": 0, "validScore": False, "playCount": 3},
            {"levelId": "custom_level_" + h1.upper(), "difficulty": 2, "beatmapCharacteristicName": "OneSaber", "highScore": 999,
             "maxCombo": 1, "fullCombo": False, "maxRank": 4, "validScore": True, "playCount": 0},   # 遊んでいない＝入れない
            {"levelId": "custom_level_" + h2.upper(), "difficulty": 0, "beatmapCharacteristicName": "OneSaber", "highScore": 5000,
             "maxCombo": 10, "fullCombo": False, "maxRank": 5, "validScore": True, "playCount": 1},
            {"levelId": "100Bills", "difficulty": 1, "beatmapCharacteristicName": "Standard", "highScore": 1, "maxRank": 1,
             "validScore": True, "playCount": 4},   # 公式曲は入れない
            {"levelId": "custom_level_XYZ", "difficulty": 9, "beatmapCharacteristicName": "Standard", "playCount": 1},
            "x", None],
        "favoritesLevelIds": ["custom_level_" + h2.upper(), "100Bills", 5]}]}


def test_playdata(t):
    '''プレイ記録（PlayerData.dat）: ハッシュごとの回数・自己ベスト・ランク・FC・お気に入り／名前・ID は返さない／読み直し／missing・bad
    ランクは数値→E〜SSS。遊んでいない記録・公式曲は入れない。更新日が変われば読み直す。無い=missing・壊れた/大きすぎ=bad'''
    ML, ml, base = _new()
    root, fx = _make_lib(base)
    pdp = Path(ml.default_playdata)
    st = ml.playdata_status()
    t.eq((st["mode"], st["state"], st["count"]), ("auto", "missing", 0), "無い時")
    lid = ml.approve_dir(str(root))["id"]
    maps, _ = _scan_all(ml, lid)
    h1 = next(m["hash"] for m in maps if m["rel"].startswith("1a2b"))
    h2 = "ab" * 20
    _w(pdp, _playerdata((h1, h2)))
    st = ml.playdata_status()
    t.eq((st["mode"], st["path"], st["state"], st["count"]), ("auto", str(pdp), "ok", 3), "読めた（遊んだ記録3件）")
    t.ok(isinstance(st["mtime"], int), "更新日")
    p = ml.play_for(h1)
    t.eq(p, {"fav": False, "diffs": {"Standard/Expert": {"plays": 12, "best": 123456, "rank": "SS", "fc": True},
                                     "Standard/ExpertPlus": {"plays": 3, "best": None, "rank": None, "fc": False}}}, "曲1")
    t.eq(ml.play_for(h2.upper()), {"fav": True, "diffs": {"OneSaber/Easy": {"plays": 1, "best": 5000, "rank": "S", "fc": False}}},
         "曲2（大文字のハッシュでも引ける）")
    t.eq(ml.play_for("cd" * 20), None, "記録の無い曲")
    t.eq(ml.play_for(None), None, "ハッシュが無い")
    t.eq(ml.play_all(lid), {"1a2b (Song V2 - Mapper)": p}, "play_all（記録のある曲だけ）")
    blob = json.dumps([ml.playdata_status(), ml.play_all(lid), ml.play_for(h2)])
    t.ok("SecretPlayerName" not in blob and "76561190000000000" not in blob, "名前・ID は返さない")
    d = _playerdata((h1, h2))
    d["localPlayers"][0]["levelsStatsData"][0]["playCount"] = 13
    _w(pdp, d)
    os.utime(pdp, ns=(pdp.stat().st_atime_ns, pdp.stat().st_mtime_ns + 3_000_000_000))
    t.eq(ml.playdata_status()["state"], "ok", "更新後")
    t.eq(ml.play_for(h1)["diffs"]["Standard/Expert"]["plays"], 13, "更新日が変われば読み直す")
    _w(pdp, b"{broken")
    t.eq(ml.playdata_status()["state"], "bad", "壊れていたら bad")
    t.eq(ml.play_for(h1), None, "bad の時は記録なし")
    _w(pdp, json.dumps(_playerdata((h1, h2))))
    old = ML.MAX_PLAYDATA
    ML.MAX_PLAYDATA = 100
    try:
        os.utime(pdp, ns=(pdp.stat().st_atime_ns, pdp.stat().st_mtime_ns + 3_000_000_000))
        t.eq(ml.playdata_status()["state"], "bad", "大きすぎたら bad")
    finally:
        ML.MAX_PLAYDATA = old
    _w(pdp, {"localPlayers": []})
    t.eq(ml.playdata_status()["state"], "bad", "形が違えば bad")


def test_playdata_custom_path(t):
    '''プレイ記録の場所: ダイアログで選んだ物を記録して使い（custom）、reset で既定（auto）に戻す。次の起動でも残る'''
    ML, ml, base = _new()
    other = base / "elsewhere" / "PlayerData.dat"
    _w(other, _playerdata(("ab" * 20, "cd" * 20)))
    st = ml.set_playdata(str(other))
    t.eq((st["mode"], st["path"], st["state"]), ("custom", str(other), "ok"), "選んだ場所")
    t.eq(_err(ml.set_playdata, "relative.dat"), "bad-path", "相対パスは不可")
    ml2 = ML.MediaLibrary(str(base / "data"), default_playdata=ml.default_playdata)
    t.eq(ml2.playdata_status()["mode"], "custom", "次の起動でも残る")
    t.ok(ml2.play_for("ab" * 20) is not None, "選んだ場所から読む")
    st = ml2.reset_playdata()
    t.eq((st["mode"], st["path"], st["state"]), ("auto", ml.default_playdata, "missing"), "既定に戻す")


# ---------------------------------------------------------------- プラグインへの入力・音源の長さ・キー

def test_rating_input(t):
    '''rating_input: nlm-rating に渡す [{name:'Info.dat', text}, {name:'<難易度>.dat', text}…]。渡せる名前の物だけ・BOM は外す・32個まで'''
    ML, ml, base = _new()
    root, fx = _make_lib(base)
    lid = ml.approve_dir(str(root))["id"]
    out = ml.rating_input(lid, "1a2b (Song V2 - Mapper)")
    t.eq([f["name"] for f in out], ["Info.dat", "ExpertStandard.dat", "ExpertPlusStandard.dat"], "名前（無いファイルは入れない）")
    t.eq(json.loads(out[0]["text"])["_songName"], "Song V2", "Info.dat の中身（BOM を外した文字列）")
    t.eq(out[1]["text"], (fx["v2"] / "ExpertStandard.dat").read_text(encoding="utf-8"), "難易度の中身")
    out = ml.rating_input(lid, "c3d4 (Song V3 - Mapper)")
    t.eq([f["name"] for f in out], ["Info.dat", "Hard.dat", "Expert.dat"], "INFO.DAT も Info.dat として渡す")
    out = ml.rating_input(lid, "My V4 Map")
    t.ok({"Info.dat", "Easy.dat", "Hard.dat", "AudioData.dat"} <= {f["name"] for f in out}, "v4 は音の情報も渡す")
    rx = ML._DAT_RE
    many = base / "Lib" / "Many"
    info = {"_version": "2.0.0", "_beatsPerMinute": 120, "_difficultyBeatmapSets": [{"_beatmapCharacteristicName": "Standard",
            "_difficultyBeatmaps": [{"_difficulty": "Easy", "_beatmapFilename": "D%02d.dat" % i} for i in range(40)]
            + [{"_difficulty": "Hard", "_beatmapFilename": "エキスパート.dat"}]}]}
    _w(many / "Info.dat", info)
    for i in range(40):
        _w(many / ("D%02d.dat" % i), "{}")
    _w(many / "エキスパート.dat", "{}")
    out = ml.rating_input(lid, "Many")
    t.eq(len(out), 32, "32個まで")
    t.ok(all(rx.fullmatch(f["name"]) for f in out), "渡せる名前だけ")
    t.eq(_err(ml.rating_input, lid, "Music Folder"), "not-found", "譜面でないフォルダ")
    t.eq(_err(ml.rating_input, lid, ""), "not-found", "根")
    t.eq(_err(ml.rating_input, lid, "dead (Broken - X)"), "bad-info", "壊れた Info.dat")
    t.eq(_err(ml.rating_input, lid, ".."), "bad-path", "..")


def test_audio_duration(t):
    '''音源の長さ: OGG Vorbis（最後のページの granule ÷ サンプルレート。最後が -1 なら1つ前）・Opus（48kHz・pre-skip を引く）・WAV。他は不明'''
    ML = _ml()
    base = Path(tempfile.mkdtemp(prefix="nlm_unitpy_ml_"))

    def dur(name, data):
        p = _w(base / name, data)
        return ML.audio_duration(str(p), p.stat().st_size)
    t.eq(dur("a.egg", _ogg(44100, 44100 * 90)), 90.0, "egg")
    t.eq(dur("b.ogg", _ogg(48000, 48000 * 5 + 24000, last_granule_minus1=True)), 5.5, "最後のページが -1")
    big = _ogg(22050, 22050 * 2)
    t.eq(dur("c.ogg", big[:-60] + b"\0" * 200000 + big[-60:]), 2.0, "末尾まで遠い（64KBより前にページの頭がある）")
    t.eq(dur("d.opus", _opus(48000 * 3 + 312)), 3.0, "Opus")
    t.eq(dur("e.wav", _wav(1.5)), 1.5, "WAV")
    t.eq(dur("f.mp3", b"ID3\x03" + b"\0" * 100), None, "mp3 は不明")
    t.eq(dur("g.egg", b"not ogg at all"), None, "OGG でない egg")
    t.eq(dur("h.ogg", _ogg(44100, 44100)[:40]), None, "途中で切れた OGG")
    t.eq(dur("i.wav", b"RIFF\0\0\0\0WAVE"), None, "中身の無い WAV")


def test_key_from_folder_name(t):
    '''フォルダ名の先頭の BeatSaver のキー: 「キー (曲 - マッパー)」「キー」だけ。英単語（Bad Apple 等）・大文字・7文字以上は拾わない'''
    ML = _ml()
    for name, key in (("103fb (Song Name - Mapper)", "103fb"), ("1a2b", "1a2b"), ("a - Song", "a"),
                      ("Bad Apple", None), ("bad apple", None), ("ABCD (x)", None), ("1234567 (x)", None), ("My V4 Map", None),
                      ("", None), ("12ab(x)", None)):
        t.eq(ML._key_of(name), key, name)


def test_approve_after_record_deleted(t):
    '''記録ファイルが外で消された後にダイアログで同じフォルダを選ぶと、記録し直して保存する（古い記録を見て「記録済み」としない）'''
    ML, ml, base = _new()
    root, fx = _make_lib(base)
    lid = ml.approve_dir(str(root))["id"]
    Path(ml.record_file).unlink()
    r = ml.approve_dir(str(root))
    t.eq(r["id"], lid, "同じ id")
    t.ok(Path(ml.record_file).is_file(), "記録ファイルを書き直す")
    t.eq([l["id"] for l in ml.list()], [lid], "一覧に出る")


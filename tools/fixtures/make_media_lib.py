"""MEDIA ライブラリのテスト用の小さなライブラリ（tools/fixtures/media_lib/）を作り直す。

  .venv-build/Scripts/python.exe tools/fixtures/make_media_lib.py

中身（tests/e2e_nle/test_media_library.py の期待値はここに合わせてある。変えたらテストも直す）:
  1a01 (Alpha Song - MapperA)/   v2・BPM120・音源3秒（WAV）・カバー画像。Standard の Hard/Expert/ExpertPlus と OneSaber の Expert
  1b02 (Beta Song - MapperB)/    v2 の Info＋v3 の譜面・BPM150・音源2秒・カバー無し。Standard の Easy/Normal/Hard（Expert は無い）
  1c03 (Gamma V4 - MapperC)/     v4・BPM100・音源の長さは Info の songDuration（61.5秒）。Standard の Expert
  Delta Noodle/                  キーの無いフォルダ名・v2・BPM200・音源なし。Standard の Hard（Chroma は推奨）・ExpertPlus（Noodle が必要）と Lawless の Expert
  Extras/loose.wav・Extras/art.png  譜面フォルダの外の音楽ファイル・画像
各曲に metadata.json の addedDate（ダウンロード日）。音源は 8kHz・8bit の無音の WAV（小さくするため）
"""
import json
import shutil
import struct
import zlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "media_lib"


def wav(sec, rate=8000):
    data = b"\x80" * int(rate * sec)   # 8bit の無音（中心＝128）
    fmt = struct.pack("<HHIIHH", 1, 1, rate, rate, 1, 8)
    body = b"WAVE" + b"fmt " + struct.pack("<I", len(fmt)) + fmt + b"data" + struct.pack("<I", len(data)) + data
    return b"RIFF" + struct.pack("<I", len(body)) + body


def png(w, h, rgb):
    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xffffffff)
    raw = b"".join(b"\0" + bytes(rgb) * w for _ in range(h))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def v2_notes(n, step=1.0):
    return {"_version": "2.2.0", "_events": [{"_time": 0, "_type": 1, "_value": 1}],
            "_notes": [{"_time": 1 + i * step, "_lineIndex": i % 4, "_lineLayer": 0, "_type": i % 2, "_cutDirection": 1} for i in range(n)],
            "_obstacles": [{"_time": 2, "_lineIndex": 0, "_type": 0, "_duration": 1, "_width": 1}]}


def v3_notes(n, step=1.0):
    return {"version": "3.2.0", "bpmEvents": [], "rotationEvents": [],
            "colorNotes": [{"b": 1 + i * step, "x": i % 4, "y": 0, "c": i % 2, "d": 1, "a": 0} for i in range(n)],
            "bombNotes": [{"b": 3, "x": 1, "y": 2}], "obstacles": [], "sliders": [], "burstSliders": [],
            "basicBeatmapEvents": [{"b": 0, "et": 1, "i": 1, "f": 1}], "colorBoostBeatmapEvents": []}


def v4_notes(n):
    return {"version": "4.0.0", "colorNotes": [{"b": 1 + i, "i": i % 2} for i in range(n)],
            "colorNotesData": [{"x": 1, "y": 0, "c": 0, "d": 1}, {"x": 2, "y": 0, "c": 1, "d": 1}],
            "bombNotes": [], "bombNotesData": [], "obstacles": [], "obstaclesData": [], "arcs": [], "arcsData": [], "chains": [], "chainsData": []}


def d2(diff, fn, njs, off=0.0, cd=None):
    d = {"_difficulty": diff, "_difficultyRank": {"Easy": 1, "Normal": 3, "Hard": 5, "Expert": 7, "ExpertPlus": 9}[diff],
         "_beatmapFilename": fn, "_noteJumpMovementSpeed": njs, "_noteJumpStartBeatOffset": off}
    if cd:
        d["_customData"] = cd
    return d


def info2(name, sub, artist, mapper, bpm, song, cover, sets, prev=(1, 2)):
    return {"_version": "2.1.0", "_songName": name, "_songSubName": sub, "_songAuthorName": artist, "_levelAuthorName": mapper,
            "_beatsPerMinute": bpm, "_songTimeOffset": 0, "_shuffle": 0, "_shufflePeriod": 0.5,
            "_previewStartTime": prev[0], "_previewDuration": prev[1], "_songFilename": song, "_coverImageFilename": cover,
            "_environmentName": "DefaultEnvironment", "_allDirectionsEnvironmentName": "GlassDesertEnvironment",
            "_difficultyBeatmapSets": [{"_beatmapCharacteristicName": ch, "_difficultyBeatmaps": lst} for ch, lst in sets]}


def put(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(data, (dict, list)):
        data = json.dumps(data, ensure_ascii=False, indent=1).encode("utf-8")
    path.write_bytes(data)


def meta(folder, added):
    put(folder / "metadata.json", {"id": folder.name.split(" ")[0], "addedDate": added})


def make():
    if OUT.exists():
        shutil.rmtree(OUT)
    a = OUT / "1a01 (Alpha Song - MapperA)"
    put(a / "Info.dat", info2("Alpha Song", "Alpha Sub", "Artist Alpha", "MapperA", 120, "song.wav", "cover.png", [
        ("Standard", [d2("Hard", "HardStandard.dat", 14), d2("Expert", "ExpertStandard.dat", 16, -0.5), d2("ExpertPlus", "ExpertPlusStandard.dat", 18)]),
        ("OneSaber", [d2("Expert", "ExpertOneSaber.dat", 15)])]))
    put(a / "HardStandard.dat", v2_notes(8))
    put(a / "ExpertStandard.dat", v2_notes(16, 0.5))
    put(a / "ExpertPlusStandard.dat", v2_notes(24, 0.5))
    put(a / "ExpertOneSaber.dat", v2_notes(10))
    put(a / "song.wav", wav(3.0))
    put(a / "cover.png", png(8, 8, (220, 60, 90)))
    meta(a, "2025-01-10T12:00:00")

    b = OUT / "1b02 (Beta Song - MapperB)"
    put(b / "Info.dat", info2("Beta Song", "", "Artist Beta", "MapperB", 150, "song.wav", "", [
        ("Standard", [d2("Easy", "EasyStandard.dat", 10), d2("Normal", "NormalStandard.dat", 12), d2("Hard", "HardStandard.dat", 13)])]))
    put(b / "EasyStandard.dat", v3_notes(4, 2))
    put(b / "NormalStandard.dat", v3_notes(6, 1))
    put(b / "HardStandard.dat", v3_notes(12, 0.5))
    put(b / "song.wav", wav(2.0))
    meta(b, "2025-03-05T12:00:00")

    c = OUT / "1c03 (Gamma V4 - MapperC)"
    put(c / "Info.dat", {"version": "4.0.0", "song": {"title": "Gamma V4", "subTitle": "", "author": "Artist Gamma"},
                         "audio": {"songFilename": "song.ogg", "songDuration": 61.5, "audioDataFilename": "AudioData.dat", "bpm": 100,
                                   "lufs": 0, "previewStartTime": 3, "previewDuration": 5},
                         "songPreviewFilename": "song.ogg", "coverImageFilename": "",
                         "environmentNames": ["WeaveEnvironment"], "colorSchemes": [],
                         "difficultyBeatmaps": [
                             {"characteristic": "Standard", "difficulty": "Expert", "beatmapAuthors": {"mappers": ["MapperC"], "lighters": []},
                              "environmentNameIdx": 0, "beatmapColorSchemeIdx": 0, "noteJumpMovementSpeed": 17, "noteJumpStartBeatOffset": 0,
                              "lightshowDataFilename": "Lightshow.dat", "beatmapDataFilename": "Expert.dat"}]})
    put(c / "Expert.dat", v4_notes(20))
    put(c / "Lightshow.dat", {"version": "4.0.0", "basicEvents": [], "basicEventsData": []})
    put(c / "AudioData.dat", {"version": "4.0.0", "songChecksum": "", "songSampleCount": 0, "songFrequency": 44100, "bpmData": []})
    meta(c, "2025-02-01T12:00:00")

    d = OUT / "Delta Noodle"
    put(d / "Info.dat", info2("Delta Noodle", "", "Artist Delta", "MapperD", 200, "song.egg", "", [
        ("Standard", [d2("Hard", "HardStandard.dat", 16, 0, {"_suggestions": ["Chroma"]}),
                      d2("ExpertPlus", "ExpertPlusStandard.dat", 20, 0, {"_requirements": ["Noodle Extensions"]})]),
        ("Lawless", [d2("Expert", "ExpertLawless.dat", 18)])]))
    put(d / "HardStandard.dat", v2_notes(10))
    put(d / "ExpertPlusStandard.dat", v2_notes(30, 0.5))
    put(d / "ExpertLawless.dat", v2_notes(12))
    meta(d, "2025-04-20T12:00:00")

    put(OUT / "Extras" / "loose.wav", wav(1.0))
    put(OUT / "Extras" / "art.png", png(8, 8, (60, 120, 220)))


if __name__ == "__main__":
    make()
    print("作成:", OUT)

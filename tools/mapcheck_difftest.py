"""譜面チェック（js/mapcheck/mapcheck.js）と原作 BS Map Check（公開サイト）の結果を突き合わせる差分テスト。

乱数で問題の多い譜面（v3/v2・v2環境/v3環境）を作ってzipにし、
  原作: https://kivalevan.me/BeatSaber-MapCheck/ をヘッドレスEdgeで開き、プリセットBeatLeaderでzipを読ませて結果欄を読む
  移植: editor.html?dev=1 で mapcheck.js を import して runMapCheck を実行
の両方で「項目名(英語) → 指摘された拍の集合」を比べる。原作はブラウザ内で処理が完結する（譜面はどこにも送られない）。
必要: ffmpeg（短い無音のsong.eggを作る）、ネット接続。

使い方: .venv-build/Scripts/python.exe tools/mapcheck_difftest.py [seed ...]   （既定 1 2 3）
  seed%3==2 → Weave(v3環境)、seed%4==3 → v2形式の.dat

既知の差（2026-09-28時点。これ以外が出たら移植のずれ）:
  - 「Invalid event box group ID / filter」が移植のみに出る: 原作は不正IDのグループにフィルタ種別2の
    ボックスがあると例外になり、この項目を丸ごと出さない。移植は判定できた分を出す
"""
import json, random, subprocess, sys, tempfile, zipfile, re, html
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cdp import Editor  # noqa

OUT = Path(tempfile.gettempdir()) / "nlm_mapcheck_difftest"
OUT.mkdir(exist_ok=True)
DIFFS = ["Easy", "Normal", "Hard", "Expert", "ExpertPlus"]


def gen_diff(rng, v3env, dense):
    t = 1.0
    notes, bombs, walls, arcs, chains, evs = [], [], [], [], [], []
    steps = [1/8, 1/6, 1/4, 1/2, 1, 0.3, 1/16, 0.05, 0]
    while t < 70:
        k = rng.randint(1, 2 if dense else 1)
        for _ in range(k):
            notes.append({"b": round(t, 4), "x": rng.randint(0, 3), "y": rng.randint(0, 2), "c": rng.randint(0, 1),
                          "d": rng.randint(0, 8), "a": rng.choice([0, 0, 0, 15, -30])})
        if rng.random() < 0.15:
            bombs.append({"b": round(t + rng.choice([0, 0.02, 0.1, 0.5]), 4), "x": rng.randint(0, 3), "y": rng.randint(0, 2)})
        if rng.random() < 0.06:
            walls.append({"b": round(t, 4), "x": rng.randint(-1, 3), "y": rng.choice([0, 0, 2, 1]), "d": rng.choice([0, 0.01, 0.02, 0.5, 2, 4]),
                          "w": rng.choice([0, 1, 1, 2, 2, 3, 4]), "h": rng.choice([0, 1, 3, 5, 5])})
        if rng.random() < 0.05 and notes:
            h = rng.choice(notes[-3:])
            tb = round(t + rng.choice([0, 0.5, 1, 2]), 4)
            arcs.append({"b": h["b"] if rng.random() < 0.7 else round(t, 4), "c": h["c"] if rng.random() < 0.8 else 1 - h["c"],
                         "x": h["x"], "y": h["y"], "d": rng.randint(0, 8), "mu": rng.choice([1, 0.5, 2]), "tb": tb,
                         "tx": rng.randint(0, 3), "ty": rng.randint(0, 2), "tc": rng.randint(0, 8), "tmu": 1, "m": rng.randint(0, 2)})
        if rng.random() < 0.05 and notes:
            h = rng.choice(notes[-3:])
            same = rng.random() < 0.6
            chains.append({"b": h["b"] if same else round(t, 4), "c": h["c"], "x": h["x"] if same else rng.randint(0, 3), "y": h["y"] if same else rng.randint(0, 2),
                           "d": h["d"] if same and h["d"] != 8 else rng.randint(0, 7), "tb": round(t + rng.choice([0.1, 0.25, 0.5]), 4),
                           "tx": rng.randint(-1, 4), "ty": rng.randint(0, 3), "sc": rng.choice([2, 3, 5, 8]), "s": rng.choice([1, 0.5, 1.5])})
        t += rng.choice(steps)
    nev = rng.choice([3, 8, 60]) if not v3env else rng.choice([5, 40])
    for _ in range(nev):
        evs.append({"b": round(rng.uniform(0, 72), 3), "et": rng.choice([0, 1, 2, 3, 4, 8, 12, 25]), "i": rng.randint(0, 12), "f": rng.choice([1, 1, 0.1, 0.5])})
    evs.sort(key=lambda e: e["b"])
    d = {"version": "3.3.0", "bpmEvents": [], "rotationEvents": [], "colorNotes": notes, "bombNotes": bombs, "obstacles": walls,
         "sliders": arcs, "burstSliders": chains, "waypoints": [], "basicBeatmapEvents": evs,
         "colorBoostBeatmapEvents": [{"b": 5, "o": True}], "lightColorEventBoxGroups": [], "lightRotationEventBoxGroups": [],
         "lightTranslationEventBoxGroups": [], "basicEventTypesWithKeywords": {}, "useNormalEventsAsCompatibleEvents": True}
    if rng.random() < 0.5:
        d["bpmEvents"] = [{"b": 0, "m": 128}, {"b": 30, "m": rng.choice([100, 160, 200])}]
    if rng.random() < 0.5:
        d["rotationEvents"] = [{"b": 3, "e": rng.choice([0, 1]), "r": 15}]
    if v3env:
        d["lightColorEventBoxGroups"] = [{"b": round(rng.uniform(0, 70), 2), "g": rng.randint(0, 20), "e": [
            {"f": {"f": rng.choice([1, 2]), "p": rng.randint(0, 30), "t": 1, "r": 0}, "w": 1, "d": rng.choice([1, 2]), "r": 1, "t": 1, "b": 0, "i": 0,
             "e": [{"b": 0, "i": 0, "c": rng.choice([0, 1, 2]), "s": 1, "f": 0}]}]} for _ in range(4)]
    return d


def to_v2(d):
    notes = [{"_time": n["b"], "_lineIndex": n["x"], "_lineLayer": n["y"], "_type": n["c"], "_cutDirection": n["d"]} for n in d["colorNotes"]]
    notes += [{"_time": n["b"], "_lineIndex": n["x"], "_lineLayer": n["y"], "_type": 3, "_cutDirection": 0} for n in d["bombNotes"]]
    notes.sort(key=lambda n: n["_time"])
    obs = [{"_time": o["b"], "_lineIndex": o["x"], "_type": 1 if o["y"] == 2 else 0, "_duration": o["d"], "_width": o["w"]} for o in d["obstacles"]]
    evs = [{"_time": e["b"], "_type": e["et"], "_value": e["i"], "_floatValue": e["f"]} for e in d["basicBeatmapEvents"]]
    return {"_version": "2.6.0", "_notes": notes, "_obstacles": obs, "_events": evs, "_waypoints": []}


def make_zip(seed):
    rng = random.Random(seed)
    v3env = seed % 3 == 2
    env = "WeaveEnvironment" if v3env else rng.choice(["DefaultEnvironment", "BigMirrorEnvironment"])
    bpm = rng.choice([90, 128, 175])
    diffs = []
    for i, dn in enumerate(DIFFS):
        njs = rng.choice([8, 12, 16, 19, 24, 2])
        off = rng.choice([0, 0, -0.5, 0.75, -3])
        j = gen_diff(rng, v3env, i >= 2)
        diffs.append({"dn": dn, "njs": njs, "off": off, "json": to_v2(j) if seed % 4 == 3 and not v3env else j})
    info = {"_version": "2.1.0", "_songName": "difftest", "_songSubName": "", "_songAuthorName": "x", "_levelAuthorName": "y",
            "_beatsPerMinute": bpm, "_songTimeOffset": 0, "_shuffle": 0, "_shufflePeriod": 0.5,
            "_previewStartTime": 12, "_previewDuration": 10, "_songFilename": "song.egg", "_coverImageFilename": "",
            "_environmentName": env, "_allDirectionsEnvironmentName": "GlassDesertEnvironment",
            "_difficultyBeatmapSets": [{"_beatmapCharacteristicName": "Standard", "_difficultyBeatmaps": [
                {"_difficulty": d["dn"], "_difficultyRank": [1, 3, 5, 7, 9][i], "_beatmapFilename": d["dn"] + "Standard.dat",
                 "_noteJumpMovementSpeed": d["njs"], "_noteJumpStartBeatOffset": d["off"]} for i, d in enumerate(diffs)]}]}
    dur = rng.choice([15, 25, 40])   # 短い音源で「曲の後ろにはみ出し」と「短すぎる音源」も出す
    egg = OUT / f"song{dur}.ogg"
    if not egg.exists():
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono", "-t", str(dur),
                        "-c:a", "libvorbis", str(egg)], check=True)
    zp = OUT / f"map{seed}.zip"
    with zipfile.ZipFile(zp, "w") as z:
        z.writestr("Info.dat", json.dumps(info))
        for d in diffs:
            z.writestr(d["dn"] + "Standard.dat", json.dumps(d["json"]))
        z.write(egg, "song.egg")
    return zp, info, diffs, dur


def parse_mc(html_text):
    """原作の出力欄のHTML → {ラベル: 拍の集合 or None}"""
    res = {}
    for m in re.finditer(r"<(p|div)>(.*?)</\1>", html_text, re.S):
        body = m.group(2)
        b = re.search(r"<b>(.*?)</b>", body, re.S)
        if not b:
            continue
        lab = re.sub(r"<[^>]+>", "", b.group(1))
        lab = html.unescape(lab).replace("🚧", "").replace("❌", "").replace("❗", "").replace("⚠️", "").strip()
        lab = re.sub(r"\s*\[\d+\]:?$", "", lab).rstrip(":").strip()
        times = [t.split(" in group")[0] for t in re.findall(r'class="checks__output-time"[^>]*>([^<]*)<', body)]
        res.setdefault(lab, set()).update(times)
    return res


def run_mc(ed, zp, diffs):
    ed.call("Page.navigate", url="https://kivalevan.me/BeatSaber-MapCheck/")
    ed.wait(6)
    ed.js("(()=>{const s=document.querySelector('.checks__preset'); s.value='BeatLeader'; s.dispatchEvent(new Event('change')); return 1})()")
    doc = ed.call("DOM.getDocument")
    node = ed.call("DOM.querySelector", nodeId=doc["root"]["nodeId"], selector="#input__file")
    ed.call("DOM.setFileInputFiles", files=[str(zp)], nodeId=node["nodeId"])
    for _ in range(60):
        ed.wait(0.5)
        n = ed.js("document.querySelectorAll('#select-difficulty input').length")
        if n and n >= len(diffs):
            break
    ed.wait(2)
    out = {}
    for d in diffs:
        ed.js(f"(()=>{{const r=[...document.querySelectorAll('#select-difficulty input')].find(x=>x.value==='{d['dn']}'); r.click(); return 1}})()")
        ed.wait(0.6)
        out[d["dn"]] = parse_mc(ed.js("document.querySelector('.checks__output-diff').innerHTML"))
    return out


def run_port(ed, info, diffs, dur):
    ed.call("Page.navigate", url=f"http://127.0.0.1:{ed.port}/editor.html?dev=1")
    ed.wait(4)
    payload = json.dumps({"info": {"bpm": info["_beatsPerMinute"], "environment": info["_environmentName"], "previewStart": 12, "previewDuration": 10},
                          "diffs": [{"difficulty": d["dn"], "json": d["json"], "njs": d["njs"], "njsOffset": d["off"]} for d in diffs],
                          "audioDuration": dur, "cover": None})
    r = ed.js(f"""(async()=>{{ const m=await import('/js/mapcheck/mapcheck.js'); const p={payload};
      const r=m.runMapCheck(p); return r; }})()""")
    out = {}
    for dd in r["diffs"]:
        res = {}
        if dd.get("error"):
            res["__error__"] = {dd["error"]}
        for it in dd["results"]:
            s = res.setdefault(it["label"], set())
            if it["objs"]:
                s.update(fmt(o["mc"]) for o in it["objs"])
        out[dd["difficulty"]] = res
    return out


def fmt(v):
    import math
    r = math.floor(v * 1000 + 0.5) / 1000   # JSのMath.roundと同じ四捨五入（bsmapのround）
    return str(int(r)) if r == int(r) else repr(r)


def main():
    seeds = [int(s) for s in sys.argv[1:]] or [1, 2, 3]
    total_bad = 0
    with Editor(wait=2) as ed:
        ed.call("DOM.enable")
        for seed in seeds:
            zp, info, diffs, dur = make_zip(seed)
            mc = run_mc(ed, zp, diffs)
            po = run_port(ed, info, diffs, dur)
            print(f"=== seed {seed} env={info['_environmentName']} bpm={info['_beatsPerMinute']} audio={dur}s")
            for d in diffs:
                a, b = mc[d["dn"]], po[d["dn"]]
                labels = sorted(set(a) | set(b))
                bad = []
                for lab in labels:
                    if lab not in a:
                        bad.append(f"  移植のみ: {lab} {sorted(b[lab])[:8]}")
                    elif lab not in b:
                        bad.append(f"  原作のみ: {lab} {sorted(a[lab])[:8]}")
                    elif a[lab] != b[lab]:
                        bad.append(f"  差: {lab} 原作だけ={sorted(a[lab]-b[lab])[:8]} 移植だけ={sorted(b[lab]-a[lab])[:8]}")
                print(f"- {d['dn']}: 項目 原作{len(a)} / 移植{len(b)}  {'一致' if not bad else '不一致'}")
                for x in bad:
                    print(x)
                total_bad += len(bad)
        errs = ed.errors()
    print("不一致の合計:", total_bad)
    if errs:
        print("ページのエラー(先頭5件):", errs[:5])


if __name__ == "__main__":
    main()

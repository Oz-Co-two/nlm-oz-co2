"""曲データを読み込む（bulkLoadSongData）のテンポと環境の取り込み（2026-10-26）:
拍0のBPM変化・難易度ごとに違うBPM変化（拍を付け替える）・v2 の _events type 100・環境を書き出しへ引き継ぐ。
譜面は偽のフォルダ（ページ内の JSON）で渡し、音源だけ tools/fixtures/basic.wav を使う"""
import json

from e2e_helpers import wait_until

_LOAD_JS = """(async()=>{
  const info=%s, files=%s;
  const wav=await (await fetch('tools/fixtures/basic.wav',{cache:'no-store'})).blob();
  const dir={name:'tempo_map', getFileHandle:async nm=>{
    if(nm===info._songFilename) return {name:nm,getFile:async()=>new File([wav],'basic.wav',{type:'audio/wav'})};
    if(!(nm in files)) throw new DOMException('not found','NotFoundError');
    return {name:nm,getFile:async()=>new File([JSON.stringify(files[nm])],nm,{type:'application/json'})}; }};
  await window._dbg.rt.bulkLoadSongData({name:'tempo_map',info,dir});
  return true; })()"""


def _info(bpm, diffs, env="DefaultEnvironment"):
    return {"_version": "2.1.0", "_songName": "Tempo Test", "_songSubName": "", "_songAuthorName": "a", "_levelAuthorName": "m",
            "_beatsPerMinute": bpm, "_songTimeOffset": 0, "_shuffle": 0, "_shufflePeriod": 0, "_previewStartTime": 1, "_previewDuration": 2,
            "_songFilename": "song.egg", "_coverImageFilename": "", "_environmentName": env,
            "_difficultyBeatmapSets": [{"_beatmapCharacteristicName": "Standard", "_difficultyBeatmaps": [
                {"_difficulty": d, "_difficultyRank": r, "_beatmapFilename": d + "Standard.dat", "_noteJumpMovementSpeed": 16, "_noteJumpStartBeatOffset": 0}
                for d, r in diffs]}]}


def _v3(bpm_events, beats):
    return {"version": "3.3.0", "bpmEvents": bpm_events,
            "colorNotes": [{"b": b, "x": 1, "y": 0, "c": 0, "d": 1, "a": 0} for b in beats],
            "bombNotes": [], "obstacles": [{"b": beats[0], "x": 0, "y": 0, "d": 2, "w": 1, "h": 5}], "sliders": [], "burstSliders": [],
            "basicBeatmapEvents": [{"b": b, "et": 0, "i": 1, "f": 1} for b in beats]}


def _load(ed, info, files):
    ed.js(_LOAD_JS % (json.dumps(info), json.dumps(files)))
    wait_until(ed, "document.getElementById('errToast').textContent.includes('一括読み込みしました')", label="一括読み込みの終わり")


def _export(ed):
    """書き出すのと同じ .dat（譜面チェックの入力）: {難易度: json}"""
    inp = ed.js("window._dbgApp.mapCheckInput()")
    return {d["difficulty"]: d["json"] for d in inp["diffs"]}, inp


def test_bpm_at_beat0(t):
    '''拍0のBPM変化（Info.dat のBPMと違う）を拍0のテンポパートとして取り込み、書き出しの bpmEvents にも出す。Info.dat のBPMは変えない'''
    ed = t.fresh()
    _load(ed, _info(120, [("Expert", 7)]), {"ExpertStandard.dat": _v3([{"b": 0, "m": 150}, {"b": 8, "m": 200}], [4, 12])})
    pj = json.loads(ed.js("window._dbg.rt.buildProjectText()"))
    t.eq(pj["tempoParts"], [{"beat": 0, "bpm": 150}, {"beat": 8, "bpm": 200}], "テンポパート（拍0を含む）")
    t.eq(pj["bpm"], 120, "基準のBPM（Info.dat）はそのまま")
    dats, inp = _export(ed)
    t.eq(dats["Expert"]["bpmEvents"], [{"b": 0, "m": 150}, {"b": 8, "m": 200}], "書き出しの bpmEvents")
    t.eq(inp["info"]["bpm"], 120, "書き出しの Info.dat のBPM")
    t.eq(sorted(n["b"] for n in dats["Expert"]["colorNotes"]), [4, 12], "拍は元のまま")
    t.no_errors()


def test_bpm_differs_per_difficulty(t):
    '''難易度ごとにBPM変化が違う: 一番多くの難易度が使うテンポを全体にし、違う難易度は秒が同じになるよう拍を付け替える'''
    ed = t.fresh()
    files = {"HardStandard.dat": _v3([], [4, 8]), "ExpertStandard.dat": _v3([], [4, 8]),
             "ExpertPlusStandard.dat": _v3([{"b": 4, "m": 240}], [4, 8])}
    _load(ed, _info(120, [("Hard", 5), ("Expert", 7), ("ExpertPlus", 9)]), files)
    toast = ed.js("document.getElementById('errToast').textContent")
    t.ok("Expert+ の拍を全体のテンポに合わせて付け替えました" in toast, f"知らせ: {toast}")
    t.eq(json.loads(ed.js("window._dbg.rt.buildProjectText()"))["tempoParts"], [], "全体のテンポ＝2つの難易度が使う（BPM変化なし）")
    dats, _ = _export(ed)
    t.eq(sorted(n["b"] for n in dats["Hard"]["colorNotes"]), [4, 8], "Hard はそのまま")
    # Expert+: 拍8＝4拍(120)+4拍(240)＝3秒 → 120 で拍6
    t.eq(sorted(n["b"] for n in dats["ExpertPlus"]["colorNotes"]), [4, 6], "Expert+ は秒が同じ拍へ")
    w = dats["ExpertPlus"]["obstacles"][0]
    t.eq((w["b"], w["d"]), (4, 1), "壁の長さも付け替える（2拍(240)＝1拍(120)）")
    t.eq(sorted(e["b"] for e in dats["ExpertPlus"]["basicBeatmapEvents"]), [4, 6], "ライトも")
    t.no_errors()


def test_bpm_tie_prefers_harder(t):
    '''使う難易度の数が同じなら難しい方のテンポを全体にする'''
    ed = t.fresh()
    files = {"ExpertStandard.dat": _v3([], [4, 8]), "ExpertPlusStandard.dat": _v3([{"b": 4, "m": 240}], [4, 8])}
    _load(ed, _info(120, [("Expert", 7), ("ExpertPlus", 9)]), files)
    t.eq(json.loads(ed.js("window._dbg.rt.buildProjectText()"))["tempoParts"], [{"beat": 4, "bpm": 240}], "全体のテンポ＝Expert+")
    dats, _ = _export(ed)
    t.eq(sorted(n["b"] for n in dats["ExpertPlus"]["colorNotes"]), [4, 8], "Expert+ はそのまま")
    t.eq(sorted(n["b"] for n in dats["Expert"]["colorNotes"]), [4, 12], "Expert は拍8（4秒）→240 で拍12")
    t.no_errors()


def test_v2_type100_bpm(t):
    '''v2 の _events type 100（公式のBPM変化）をテンポパートとして読み、ライトとしては書き出さない'''
    ed = t.fresh()
    v2 = {"_version": "2.6.0",
          "_notes": [{"_time": 4, "_lineIndex": 1, "_lineLayer": 0, "_type": 0, "_cutDirection": 1},
                     {"_time": 12, "_lineIndex": 2, "_lineLayer": 0, "_type": 1, "_cutDirection": 1}],
          "_obstacles": [],
          "_events": [{"_time": 0, "_type": 100, "_value": 0, "_floatValue": 120}, {"_time": 8, "_type": 100, "_value": 0, "_floatValue": 180},
                      {"_time": 4, "_type": 1, "_value": 1, "_floatValue": 1}]}
    _load(ed, _info(120, [("Expert", 7)]), {"ExpertStandard.dat": v2})
    t.eq(json.loads(ed.js("window._dbg.rt.buildProjectText()"))["tempoParts"], [{"beat": 8, "bpm": 180}], "type 100 をテンポパートに（拍0は Info と同じなので省く）")
    dats, _ = _export(ed)
    t.eq([e["et"] for e in dats["Expert"]["basicBeatmapEvents"]], [1], "ライトに type 100 が残らない")
    t.eq(dats["Expert"]["bpmEvents"], [{"b": 8, "m": 180}], "書き出しの bpmEvents")
    t.no_errors()


def _boosts(dat):
    return sorted([e["b"], e["o"]] for e in dat["colorBoostBeatmapEvents"])


def test_v3_color_boost(t):
    '''v3 の色のブースト（colorBoostBeatmapEvents の b・o・2026-10-27）: ライトの種類5（オン=1・オフ=0。o を省いた物はオフ）として読み、
    書き出しでは basicBeatmapEvents ではなく colorBoostBeatmapEvents へ書く（customData は残す）。読み込み→書き出し→読み込み→書き出しで同じ形に戻る。
    以前の NLM が v3 の basicBeatmapEvents に書いた種類5（廃止された書き方）も、ブーストとして読んで colorBoostBeatmapEvents へ移す'''
    ed = t.fresh()
    dat = _v3([], [4, 12])
    dat["colorBoostBeatmapEvents"] = [{"b": 2, "o": True}, {"b": 6, "o": False}, {"b": 8, "o": True, "customData": {"k": 1}}, {"b": 10}]
    dat["basicBeatmapEvents"].append({"b": 14, "et": 5, "i": 1, "f": 1})
    _load(ed, _info(120, [("Hard", 5)]), {"HardStandard.dat": dat})   # Hard＝開いた直後の今の難易度
    ev = ed.js("window._dbgApp.lights().events")
    t.eq(sorted([e["beat"], e["i"]] for e in ev if e["et"] == 5), [[2, 1], [6, 0], [8, 1], [10, 0], [14, 1]], "ライトの種類5として読む")
    t.eq(sorted(e["beat"] for e in ev if e["et"] != 5), [4, 12], "基本のライトはそのまま")
    dats, _ = _export(ed)
    d = dats["Hard"]
    t.eq(_boosts(d), [[2, True], [6, False], [8, True], [10, False], [14, True]], "書き出しの colorBoostBeatmapEvents")
    t.eq([e for e in d["colorBoostBeatmapEvents"] if e["b"] == 8], [{"b": 8, "o": True, "customData": {"k": 1}}], "customData は残す・余計な項目は無い")
    t.ok(all(set(e) <= {"b", "o", "customData"} for e in d["colorBoostBeatmapEvents"]), f"ブーストの項目: {d['colorBoostBeatmapEvents']}")
    t.eq(sorted([e["b"], e["et"]] for e in d["basicBeatmapEvents"]), [[4, 0], [12, 0]], "basicBeatmapEvents に種類5を書かない")
    # 往復: 書き出した物を読み込んで書き出すと同じ（消えない・増えない）
    ed = t.fresh()
    _load(ed, _info(120, [("Hard", 5)]), {"HardStandard.dat": d})
    d2 = _export(ed)[0]["Hard"]
    t.eq(d2["colorBoostBeatmapEvents"], d["colorBoostBeatmapEvents"], "往復で colorBoostBeatmapEvents が同じ")
    t.eq(d2["basicBeatmapEvents"], d["basicBeatmapEvents"], "往復で basicBeatmapEvents が同じ")
    # 保存→開き直しても同じ（o は保存しない＝i が正）
    pj = json.loads(ed.js("window._dbg.rt.buildProjectText()"))
    ed.js("(async()=>{ await window._dbg.rt.applyProject(%s); return true; })()" % json.dumps(pj))
    t.eq(_export(ed)[0]["Hard"]["colorBoostBeatmapEvents"], d["colorBoostBeatmapEvents"], "保存→開き直しても同じ")
    # v2 の難易度（古い版のプロジェクト）の書き出しは今までどおり _events の type 5
    pj["difficulties"]["hardstandard.dat"]["v3"] = False
    pj["difficulties"]["hardstandard.dat"]["base"] = {"_version": "2.2.0", "_notes": [], "_obstacles": [], "_events": []}
    ed.js("(async()=>{ await window._dbg.rt.applyProject(%s); return true; })()" % json.dumps(pj))
    v2 = _export(ed)[0]["Hard"]
    t.eq(sorted([e["_time"], e["_value"]] for e in v2["_events"] if e["_type"] == 5), [[2, 1], [6, 0], [8, 1], [10, 0], [14, 1]], "v2 は _events の type 5")
    t.ok("colorBoostBeatmapEvents" not in v2, "v2 に v3 の配列を足さない")
    t.no_errors()


def test_v3_color_boost_old_base(t):
    '''古い版のプロジェクト（読み込んだ .dat を土台にしていた頃）の土台にある colorBoostBeatmapEvents は、以前と同じく書き出しに残す。
    ライトの種類5と同じ拍・同じオン/オフの物は1つにする'''
    ed = t.fresh()
    _load(ed, _info(120, [("Hard", 5)]), {"HardStandard.dat": dict(_v3([], [4, 12]), colorBoostBeatmapEvents=[{"b": 2, "o": True}])})
    pj = json.loads(ed.js("window._dbg.rt.buildProjectText()"))
    pj["difficulties"]["hardstandard.dat"]["base"]["colorBoostBeatmapEvents"] = [{"b": 2, "o": True}, {"b": 20, "o": True}, {"b": 24, "o": False}]
    ed.js("(async()=>{ await window._dbg.rt.applyProject(%s); return true; })()" % json.dumps(pj))
    t.eq(_boosts(_export(ed)[0]["Hard"]), [[2, True], [20, True], [24, False]], "土台の物＋ライトの種類5（同じ物は1つ）")
    t.no_errors()


def test_env_carried(t):
    '''新しく曲を取り込んだ時は、読み込んだ譜面の環境を書き出し・譜面チェック・トップバーの環境へ引き継ぐ'''
    ed = t.fresh()
    _load(ed, _info(120, [("Expert", 7)], env="KaleidoscopeEnvironment"), {"ExpertStandard.dat": _v3([], [4, 12])})
    _, inp = _export(ed)
    t.eq(inp["info"]["environment"], "KaleidoscopeEnvironment", "書き出す Info.dat の環境")
    wait_until(ed, "document.getElementById('sqEnvName').textContent==='Kaleidoscope'", label="トップバーの環境")
    t.no_errors()


def test_env_outside_preview_list(t):
    '''3Dプレビューに無い環境（v3 の環境など）も名前はそのまま書き出す（プレビューは Default で見せる）'''
    ed = t.fresh()
    _load(ed, _info(120, [("Expert", 7)], env="BillieEnvironment"), {"ExpertStandard.dat": _v3([], [4, 12])})
    _, inp = _export(ed)
    t.eq(inp["info"]["environment"], "BillieEnvironment", "書き出す Info.dat の環境")
    t.no_errors()


def test_env_kept_when_music_exists(t):
    '''音源が既にある所へ読み込んだ時は、今の環境のまま（音源・BPMと同じ）'''
    ed = t.fresh()
    ed.js("""(async()=>{ const blob=await (await fetch('tools/fixtures/basic.wav',{cache:'no-store'})).blob();
      const file=new File([blob],'basic.wav',{type:'audio/wav'});
      await window._dbg.rt.loadSongFromItem({isMusic:true,name:'basic',songFh:{getFile:async()=>file},info:{_beatsPerMinute:120}},0);
      return true; })()""")
    _load(ed, _info(120, [("Expert", 7)], env="KaleidoscopeEnvironment"), {"ExpertStandard.dat": _v3([], [4, 12])})
    _, inp = _export(ed)
    t.eq(inp["info"]["environment"], "DefaultEnvironment", "環境は今のまま")
    t.no_errors()


# ---- 0 を省いた V3・Standard 以外のモード・ライトボックス・プレビューに無い環境・読み込み中の画面・ライトがとても多い警告（2026-10-27）----

def _info_modes(bpm, diffs, modes, env="DefaultEnvironment"):
    info = _info(bpm, diffs, env)
    for m, ds in modes:
        info["_difficultyBeatmapSets"].append({"_beatmapCharacteristicName": m, "_difficultyBeatmaps": [
            {"_difficulty": d, "_difficultyRank": r, "_beatmapFilename": d + m + ".dat", "_noteJumpMovementSpeed": 16, "_noteJumpStartBeatOffset": 0}
            for d, r in ds]})
    return info


def _toast(ed):
    return ed.js("document.getElementById('errToast').textContent")


def test_v3_omitted_zero_fields(t):
    '''V3 で 0 の項目を省いた書き方（"x":0 等を書かない）: 省かれた項目を既定の値（0。アークの mu・tmu、チェーンの sc・s、ライトの f は 1）で持ち、3D に NaN を出さない'''
    ed = t.fresh()
    dat = {"version": "3.3.0", "bpmEvents": [],
           "colorNotes": [{"b": 4}, {"b": 5, "x": 1, "c": 1, "d": 1}, {"b": 6, "x": 3, "y": 2, "c": 1}],
           "bombNotes": [{"b": 7, "y": 1}, {"b": 7.5}],
           "obstacles": [{"b": 8, "d": 1, "w": 1, "h": 5}],
           "sliders": [{"b": 9, "x": 1, "d": 1, "mu": 1, "tb": 10, "tx": 2, "tmu": 1}],
           "burstSliders": [{"b": 11, "x": 2, "y": 1, "d": 1, "tb": 11.5, "ty": 2, "sc": 4, "s": 1}],
           "basicBeatmapEvents": [{"et": 1, "i": 1, "f": 1}, {"b": 2, "i": 1}, {"b": 3, "et": 4}]}
    _load(ed, _info(120, [("Hard", 5)]), {"HardStandard.dat": dat})   # Hard＝開いた直後の今の難易度（3D に出る）
    n = ed.js("window._dbgApp.notes()")
    got = sorted([o["beat"], o["x"], o["y"], o["c"], o["d"]] for o in n["notes"])
    t.eq(got, [[4, 0, 0, 0, 0], [5, 1, 0, 1, 1], [6, 3, 2, 1, 0]], "ノーツの省いた項目は 0")
    ch = n["chains"][0]
    t.eq([ch[k] for k in ("c", "x", "y", "d", "tx", "ty", "sc", "s")], [0, 2, 1, 1, 0, 2, 4, 1], "チェーン（c・tx は 0）")
    dats, _ = _export(ed)
    d = dats["Hard"]
    a = d["sliders"][0]
    t.eq([a.get(k) for k in ("c", "x", "y", "d", "mu", "tb", "tx", "ty", "tc", "tmu", "m")], [0, 1, 0, 1, 1, 10, 2, 0, 0, 1, 0],
         "アーク: 省いた尾の向き tc は 0（以前は頭の向き d になっていた）")
    t.eq(sorted([o["b"], o["x"], o["y"]] for o in d["bombNotes"]), [[7, 0, 1], [7.5, 0, 0]], "ボム")
    w = d["obstacles"][0]
    t.eq([w.get(k) for k in ("b", "x", "y", "d", "w", "h")], [8, 0, 0, 1, 1, 5], "壁")
    t.eq(sorted([e["b"], e["et"], e["i"], e["f"]] for e in d["basicBeatmapEvents"]), [[0, 1, 1, 1], [2, 0, 1, 1], [3, 4, 0, 1]],
         "ライト（拍・種類・値は 0、f は 1）")
    wait_until(ed, "window._dbgApp.objScreen().length>=3", label="3D の物")
    bad = ed.js("window._dbgApp.objScreen().filter(o=>!(Number.isFinite(o.sx)&&Number.isFinite(o.sy))).map(o=>[o.kind,o.beat])")
    t.eq(bad, [], "3D の位置に NaN が無い")
    t.no_errors()


def test_other_modes_notice(t):
    '''Standard 以外のモード（OneSaber・Lawless 等）は読み込まないまま、知らせに「Standard 以外の難易度（…）は読み込んでいません」と出す'''
    ed = t.fresh()
    info = _info_modes(120, [("Expert", 7)], [("OneSaber", [("Hard", 5), ("Expert", 7)]), ("Lawless", [("ExpertPlus", 9)])])
    files = {"ExpertStandard.dat": _v3([], [4, 8]), "HardOneSaber.dat": _v3([], [4]), "ExpertOneSaber.dat": _v3([], [4]),
             "ExpertPlusLawless.dat": _v3([], [4, 5, 6])}
    _load(ed, info, files)
    t.ok("Standard 以外の難易度（OneSaber 2つ・Lawless 1つ）は読み込んでいません" in _toast(ed), f"知らせ: {_toast(ed)}")
    dats, _ = _export(ed)
    t.eq(sorted(dats), ["Expert"], "読み込んだのは Standard だけ")
    t.eq(sorted(n["b"] for n in dats["Expert"]["colorNotes"]), [4, 8], "Expert は Standard の譜面")
    # Standard だけの譜面では出さない
    ed = t.fresh()
    _load(ed, _info(120, [("Expert", 7)]), {"ExpertStandard.dat": _v3([], [4])})
    t.ok("Standard 以外" not in _toast(ed), "Standard だけなら知らせない")
    t.ok("ライトボックス" not in _toast(ed), "ライトボックスの無い譜面ではライトボックスも知らせない")
    t.eq([d["srcLightBoxes"] for d in _export(ed)[1]["diffs"]], [0], "srcLightBoxes は 0")
    t.no_errors()


def _lbx(inp):
    return {d["difficulty"]: d["srcLightBoxes"] for d in inp["diffs"]}


def test_light_boxes(t):
    '''V3 のライトボックス（lightColor/lightRotation/lightTranslation/vfx の EventBoxGroups）: グループの数を難易度ごとに持ち（読み込んだクリップの srcLbx）、
    知らせに出し、譜面チェックの入力（diffs[i].srcLightBoxes）へ渡す。保存→開き直しでも残り、ファイル由来の値は数として確かめる'''
    ed = t.fresh()
    ex = _v3([], [4, 8])
    ex.update({"lightColorEventBoxGroups": [{"b": 1, "g": 0, "e": []}, {"b": 2, "g": 1, "e": []}, {"b": 3, "g": 2, "e": []}],
               "lightRotationEventBoxGroups": [{"b": 1, "g": 0, "e": []}], "lightTranslationEventBoxGroups": [],
               "vfxEventBoxGroups": [{"b": 1, "g": 0, "e": [], "t": 1}]})
    _load(ed, _info(120, [("Hard", 5), ("Expert", 7)]), {"HardStandard.dat": _v3([], [4]), "ExpertStandard.dat": ex})
    t.ok("この譜面のライトボックス（5グループ）はNLMでは読めず、書き出すと消えます" in _toast(ed), f"知らせ: {_toast(ed)}")
    t.eq(_lbx(_export(ed)[1]), {"Hard": 0, "Expert": 5}, "譜面チェックの入力の srcLightBoxes")
    pj = json.loads(ed.js("window._dbg.rt.buildProjectText()"))
    secs = pj["difficulties"]["expertstandard.dat"]["sections"]
    t.eq(sorted([s["lk"], s.get("srcLbx")] for s in secs if s.get("kind") != "null"), [["l", 5], ["n", None]], "ライトのクリップに持たせる")
    # 保存→開き直し
    ed.js("(async()=>{ const rt=window._dbg.rt; await rt.applyProject(JSON.parse(rt.buildProjectText())); return true; })()")
    t.eq(_lbx(_export(ed)[1]), {"Hard": 0, "Expert": 5}, "開き直しても残る")
    # ファイル由来の値は数として確かめる（数でない値は捨てる）
    bad = json.loads(ed.js("window._dbg.rt.buildProjectText()"))
    for s in bad["difficulties"]["expertstandard.dat"]["sections"]:
        if s.get("srcLbx"):
            s["srcLbx"] = "<b>5</b>"
    ed.js("(async()=>{ await window._dbg.rt.applyProject(%s); return true; })()" % json.dumps(bad))
    t.eq(_lbx(_export(ed)[1]), {"Hard": 0, "Expert": 0}, "数でない値は捨てる")
    t.no_errors()


def test_light_boxes_undo_and_delete(t):
    '''ライトボックスの印は、読み込みの Undo と、読み込んだライトのクリップを消すと無くなる（書き出しにボックスが無い＝対象外にする理由が無い）'''
    ed = t.fresh()
    ex = _v3([], [4, 8])
    ex["lightColorEventBoxGroups"] = [{"b": 1, "g": 0, "e": []}, {"b": 2, "g": 1, "e": []}]
    _load(ed, _info(120, [("Hard", 5)]), {"HardStandard.dat": ex})   # Hard＝開いた直後の今の難易度（NLE に出る）
    t.eq(_lbx(_export(ed)[1]), {"Hard": 2}, "読み込んだ後")
    ed.js("window._dbg.rt.undo();true")
    wait_until(ed, "window._dbgApp.nle().clips.length===0", label="Undo でクリップが消える")
    pj = json.loads(ed.js("window._dbg.rt.buildProjectText()"))
    t.eq([s.get("srcLbx") for d in pj["difficulties"].values() for s in d.get("sections", []) if s.get("srcLbx")], [], "Undo で印も消える")
    ed.js("window._dbg.rt.redo();true")
    wait_until(ed, "window._dbgApp.nle().clips.length===2", label="やり直し")
    t.eq(_lbx(_export(ed)[1]), {"Hard": 2}, "やり直しで戻る")
    # 読み込んだライトのクリップを消す（NLE でクリックして選び、Delete）
    c = next(c for c in ed.js("window._dbgApp.nle().clips") if c["lk"] == "l")
    g = ed.js(f"window._dbgApp.nleScreen({c['beat'] + 1})")
    v0, v1 = ed.js("window._dbgApp.nle().vp.l")
    top = g["lights"][c["track"]]
    y = min(max(top + g["laneHL"] * 0.7, top + 5, v0 + 2), top + g["laneHL"] - 5, v1 - 3)
    ed.click(g["x"], y)
    wait_until(ed, f"window._dbgApp.nle().sel.includes({json.dumps(c['id'])})", label="ライトのクリップの選択")
    ed.key("Delete")
    wait_until(ed, "!window._dbgApp.nle().clips.some(c=>c.lk==='l')", label="ライトのクリップを消す")
    t.eq(_lbx(_export(ed)[1]), {"Hard": 0}, "読み込んだライトのクリップを消すと印も消える")
    t.no_errors()


def test_env_not_in_preview_mark(t):
    '''3Dプレビューに無い環境（Weave など）: トップバーの環境に印（⚠）とツールチップ「プレビューに無い環境のため Default で表示」を添える。プレビューにある環境では出さない'''
    ed = t.fresh()
    _load(ed, _info(120, [("Expert", 7)], env="WeaveEnvironment"), {"ExpertStandard.dat": _v3([], [4, 12])})
    wait_until(ed, "document.getElementById('sqEnvName').textContent==='Weave'&&!document.getElementById('sqEnvNoPv').hidden", label="印")
    title = ed.js("document.getElementById('sqEnvBtn').title")
    t.ok("「Weave」は3Dプレビューに無い環境のため、プレビューは Default で表示しています" in title, f"ツールチップ: {title}")
    w = ed.js("document.getElementById('sqEnvBtn').getBoundingClientRect().width")
    # プレビューにある環境へ切り替える→印が消え、ボタンの幅は同じ
    ed.js("(()=>{ const nd=window._dbg.rt.quickSetNode(); nd.data.env='KaleidoscopeEnvironment'; window._dbg.rt.applyInfoGraph(); return 1; })()")
    wait_until(ed, "document.getElementById('sqEnvName').textContent==='Kaleidoscope'&&document.getElementById('sqEnvNoPv').hidden", label="印が消える")
    t.eq(ed.js("document.getElementById('sqEnvBtn').title"), "環境（ステージ）", "ツールチップは元のまま")
    t.ok(abs(ed.js("document.getElementById('sqEnvBtn').getBoundingClientRect().width") - w) < 0.5, "ボタンの幅は印があっても同じ")
    t.no_errors()


def test_busy_dialog(t):
    '''読み込み中の画面: 譜面を読んでいる間「譜面を読み込み中… Expert（1/1）」が出て、裏のキーを止め、終わると消える'''
    from e2e_helpers import synth_load_js
    ed = t.fresh()
    ed.js(synth_load_js(lights=40, gate=True))
    wait_until(ed, "(b=>!!b&&b.classList.contains('on'))(document.getElementById('busyDlgBg'))", label="読み込み中の画面")
    t.eq(ed.js("document.querySelector('#busyDlg .bdTitle').textContent"), "「Synth Map」を読み込んでいます", "題名")
    t.eq(ed.js("document.querySelector('#busyDlg .bdMsg').textContent"), "譜面を読み込み中… Expert（1/1）", "今していること")
    before = ed.js("window._dbg.rt.undoStack.length")
    ed.key("z", ctrl=True)   # 読み込みの途中で Undo が動かない
    ed.wait(0.2)
    t.eq(ed.js("window._dbg.rt.undoStack.length"), before, "裏のキーは止まる")
    ed.js("window.__gateOpen()")
    wait_until(ed, "window.__bulkDone&&!document.getElementById('busyDlgBg')", label="終わると消える")
    t.ok("一括読み込みしました" in _toast(ed), "読み込みは終わる")
    t.no_errors()


def test_light_heavy_warning(t):
    '''ライトがとても多い（合計 15万個以上）時は、曲データを読み込んだ時・プロジェクトを開いた時に1回警告を出す。急に出るので Enter では閉じない。少なければ出さない'''
    from e2e_helpers import synth_load_js
    sel = "#dirtyDlg[data-dlg=lightHeavy]"
    ed = t.fresh()
    ed.js(synth_load_js(lights=150000, diffs=("Hard", "Expert")))
    wait_until(ed, f"window.__bulkDone&&!!document.querySelector('{sel}')", timeout=60, label="警告")
    t.eq(ed.js(f"document.querySelectorAll('{sel}').length"), 1, "1回だけ")
    msg = ed.js(f"document.querySelector('{sel} .ddMsg').textContent")
    t.ok(msg.startswith("ライトが合計 150,000 個あります。"), f"合計の数: {msg}")
    ed.key("Enter"); ed.wait(0.3)
    t.ok(ed.js(f"!!document.querySelector('{sel}')"), "Enter では閉じない")
    ed.key("Escape"); ed.wait(0.2)
    t.ok(ed.js(f"!document.querySelector('{sel}')"), "Esc で閉じる")
    # 開いた時（保存した物を開く）も出す
    ed.js("(async()=>{ const rt=window._dbg.rt; await rt.applyOpenedProject(JSON.parse(rt.buildProjectText()),{name:'heavy.nlmf'}); return true; })()")
    wait_until(ed, f"!!document.querySelector('{sel}')", timeout=60, label="開いた時の警告")
    ed.js(f"document.querySelector('{sel} .ddBtns button').click();true")
    wait_until(ed, f"!document.querySelector('{sel}')", label="OK で閉じる")
    # 目安より少なければ出さない
    ed = t.fresh()
    ed.js(synth_load_js(lights=149000, diffs=("Expert",)))
    wait_until(ed, "window.__bulkDone", timeout=60, label="読み込みの終わり")
    ed.wait(0.3)
    t.ok(ed.js(f"!document.querySelector('{sel}')"), "目安より少なければ出さない")
    t.no_errors()


# ---- v4（Info.dat 4.x・難易度 4.x・ライトショー・AudioData.dat・2026-10-27）----
# 記録したライブラリの曲と同じ形の項目（走査の結果だけ持ち、本物の Info.dat は ensureItemInfo が読む）で渡す。見本は自作の小さな譜面

_LOAD_V4_JS = """(async()=>{
  const files=%s;
  const wav=await (await fetch('tools/fixtures/basic.wav',{cache:'no-store'})).blob();
  const dir={name:'v4_map', getFileHandle:async nm=>{
    if(nm==='song.ogg') return {name:nm,getFile:async()=>new File([wav],'basic.wav',{type:'audio/wav'})};
    if(!(nm in files)) throw new DOMException('not found','NotFoundError');
    return {name:nm,getFile:async()=>new File([JSON.stringify(files[nm])],nm,{type:'application/json'})}; }};
  await window._dbg.rt.bulkLoadSongData({name:'v4_map',native:true,entry:{},_v4:true,info:{},dir});
  return true; })()"""


def _v4_info(diffs, envs=("DefaultEnvironment",), bpm=120):
    """diffs: [(難易度, 環境の番号, 譜面のファイル, ライトショーのファイル)]"""
    return {"version": "4.0.1", "song": {"title": "V4 Test", "subTitle": "", "author": "a"},
            "audio": {"songFilename": "song.ogg", "songDuration": 30, "audioDataFilename": "AudioData.dat", "bpm": bpm, "lufs": 0,
                      "previewStartTime": 1, "previewDuration": 2},
            "songPreviewFilename": "song.ogg", "coverImageFilename": "", "environmentNames": list(envs), "colorSchemes": [],
            "difficultyBeatmaps": [{"characteristic": "Standard", "difficulty": d, "beatmapAuthors": {"mappers": ["m"], "lighters": []},
                                    "environmentNameIdx": e, "beatmapColorSchemeIdx": 0, "noteJumpMovementSpeed": 16, "noteJumpStartBeatOffset": 0,
                                    "beatmapDataFilename": f, "lightshowDataFilename": ls} for d, e, f, ls in diffs],
            "customData": {}}


def _audio_data(regions, fq=44100):
    """regions: [(拍の始め, 拍の終わり, BPM)] → AudioData.dat（サンプルは整数・拍は小数6桁＝実物と同じ書き方。端数の出る BPM も作れる）"""
    out, s = [], 0
    for sb, eb, bpm in regions:
        n = round((eb - sb) * 60 / bpm * fq)
        out.append({"si": s, "ei": s + n, "sb": round(sb, 6), "eb": round(eb, 6)})
        s += n
    return {"version": "4.0.0", "songChecksum": "", "songSampleCount": s, "songFrequency": fq, "bpmData": out, "lufsData": []}


def _v4_diff(beats, njs=None):
    """beats の拍に赤のノーツだけの v4 の難易度。njs＝[(拍, p, e, d)]"""
    d = {"version": "4.1.0", "colorNotes": [{"b": b, "i": 0} for b in beats], "colorNotesData": [{"x": 1, "c": 0, "d": 1}],
         "bombNotes": [], "bombNotesData": [], "obstacles": [], "obstaclesData": [], "arcs": [], "arcsData": [], "chains": [], "chainsData": [],
         "njsEvents": [], "njsEventData": []}
    for b, p, e, dd in njs or []:
        d["njsEvents"].append({"b": b, "i": len(d["njsEventData"])})
        d["njsEventData"].append({"p": p, "e": e, "d": dd})
    return d


def _v4_rich():
    """省いた項目・番号の省略・使い回し・アーク・チェーン（頭の colorNote 付き）・ボム・壁・NJS の変化・番号の合わない物 1 つ"""
    return {"version": "4.1.0",
            "colorNotes": [{"b": 4, "i": 0}, {"b": 5, "i": 1}, {"b": 6}, {"b": 7, "i": 2}, {"b": 10, "i": 3, "r": 0}, {"b": 12, "i": 0},
                           {"b": 14, "i": 4}, {"b": 20, "i": 99}],
            "colorNotesData": [{"x": 1, "c": 0, "d": 1}, {"x": 2, "c": 1, "d": 1}, {}, {"x": 3, "y": 2, "c": 1, "a": 15}, {"x": 1, "y": 2, "d": 1}],
            "bombNotes": [{"b": 8, "i": 0}, {"b": 9, "i": 1}], "bombNotesData": [{"y": 2}, {}],
            "obstacles": [{"b": 4, "i": 0}], "obstaclesData": [{"d": 1, "w": 1, "h": 5}],
            "arcs": [{"hb": 16, "tb": 18, "hi": 0, "ti": 1, "ai": 0}], "arcsData": [{"m": 1, "tm": 0.5, "a": 1}],
            "chains": [{"hb": 14, "tb": 14.5, "i": 4, "ci": 0}], "chainsData": [{"tx": 1, "c": 4, "s": 1}],
            "njsEvents": [{"b": 0, "i": 0}, {"b": 8, "i": 1}, {"b": 12}], "njsEventData": [{"p": 0, "e": -1, "d": 2}, {"e": 3, "d": -2}]}


def _lightshow(boxes=3):
    return {"version": "4.0.0",
            "basicEvents": [{"b": 2, "i": 0}, {"b": 3, "i": 1}, {"i": 2}], "basicEventsData": [{"t": 0, "i": 1, "f": 1}, {"t": 1, "i": 3}, {"t": 4}],
            "colorBoostEvents": [{"b": 6, "i": 0}, {"b": 10, "i": 1}], "colorBoostEventsData": [{"b": 1}, {}],
            "waypoints": [], "waypointsData": [], "indexFilters": [], "lightColorEventBoxes": [], "lightColorEvents": [],
            "eventBoxGroups": [{"b": i, "g": i, "t": 1, "e": []} for i in range(boxes)],
            "basicEventTypesWithKeywords": {"d": []}, "useNormalEventsAsCompatibleEvents": True}


def _load_v4(ed, info, files):
    files = dict(files, **{"Info.dat": info})
    ed.js(_LOAD_V4_JS % json.dumps(files))
    wait_until(ed, "document.getElementById('errToast').textContent.includes('一括読み込みしました')", label="一括読み込みの終わり")


def _v4_files():
    info = _v4_info([("Hard", 1, "Hard.beatmap.dat", "Lightshow.dat"), ("Expert", 0, "Expert.beatmap.dat", "Lightshow.dat"),
                     ("ExpertPlus", 0, "ExpertPlus.beatmap.dat", "Lightshow.dat")], envs=("DefaultEnvironment", "KaleidoscopeEnvironment"))
    files = {"AudioData.dat": _audio_data([(0, 8, 120), (8, 16, 240), (16, 20, 195)]), "Lightshow.dat": _lightshow(),
             "Hard.beatmap.dat": _v4_diff([4, 8]), "Expert.beatmap.dat": _v4_rich(), "ExpertPlus.beatmap.dat": _v4_diff([4, 6, 8])}
    return info, files


def _by_diff(inp):
    return {d["difficulty"]: d["json"] for d in inp["diffs"]}


def test_v4_chart(t):
    '''v4 の譜面を読む: 「いつ」と「何を」の組・省いた項目（0。アークの tm 等は書いた値）・番号の省略（0 番）・アーク（頭と尾は colorNotesData）・
    チェーン（頭の colorNote はチェーンへ）・ボム・壁・ライトショー（基本のライト・ブースト）を v3 で書き出す。番号の合わない物は読まずに知らせる'''
    ed = t.fresh()
    _load_v4(ed, *_v4_files())
    dats, inp = _export(ed)
    t.eq(sorted(dats), ["Expert", "ExpertPlus", "Hard"], "3つの難易度")
    d = dats["Expert"]
    got = sorted([n["b"], n["x"], n["y"], n["c"], n["d"], n.get("a", 0)] for n in d["colorNotes"])
    t.eq(got, [[4, 1, 0, 0, 1, 0], [5, 2, 0, 1, 1, 0], [6, 1, 0, 0, 1, 0], [7, 0, 0, 0, 0, 0], [10, 3, 2, 1, 0, 15], [12, 1, 0, 0, 1, 0],
               [14, 1, 2, 0, 1, 0]], "ノーツ（拍20 は番号が合わず読まない・拍14 はチェーンの頭）")
    t.eq(sorted([o["b"], o["x"], o["y"]] for o in d["bombNotes"]), [[8, 0, 2], [9, 0, 0]], "ボム")
    t.eq([[w[k] for k in ("b", "x", "y", "d", "w", "h")] for w in d["obstacles"]], [[4, 0, 0, 1, 1, 5]], "壁")
    a = d["sliders"][0]
    t.eq([a[k] for k in ("b", "c", "x", "y", "d", "mu", "tb", "tx", "ty", "tc", "tmu", "m")], [16, 0, 1, 0, 1, 1, 18, 2, 0, 1, 0.5, 1],
         "アーク（頭＝番号0・尾＝番号1 の中身・形は arcsData）")
    c = d["burstSliders"][0]
    t.eq([c[k] for k in ("b", "c", "x", "y", "d", "tb", "tx", "ty", "sc", "s")], [14, 0, 1, 2, 1, 14.5, 1, 0, 4, 1], "チェーン")
    t.eq(sorted([e["b"], e["et"], e["i"], e["f"]] for e in d["basicBeatmapEvents"]),
         [[0, 4, 0, 1], [2, 0, 1, 1], [3, 1, 3, 1]], "基本のライト（ブーストは入れない）")
    t.eq(d["colorBoostBeatmapEvents"], [{"b": 6, "o": True}, {"b": 10, "o": False}], "ブースト（NLM の中では種類5）は v3 の colorBoostBeatmapEvents へ")
    t.eq(sorted(n["b"] for n in dats["Hard"]["colorNotes"]), [4, 8], "Hard")
    t.eq((len(dats["Hard"]["basicBeatmapEvents"]), len(dats["Hard"]["colorBoostBeatmapEvents"])), (3, 2), "全難易度が同じライトショーを使う")
    toast = _toast(ed)
    t.ok("中身の番号が合わない物（1個）は読み込んでいません" in toast, f"知らせ: {toast}")
    t.no_errors()


def test_v4_tempo_env(t):
    '''v4 のテンポは AudioData.dat（区間ごとの BPM。端数は区間の長さが1サンプル以内で合う値に丸める）。基準の BPM は Info の audio.bpm。
    難易度ごとに違う環境は一番多い物を使い（同じ数なら難しい方）、知らせる'''
    ed = t.fresh()
    _load_v4(ed, *_v4_files())
    pj = json.loads(ed.js("window._dbg.rt.buildProjectText()"))
    t.eq(pj["bpm"], 120, "基準の BPM＝audio.bpm")
    t.eq(pj["tempoParts"], [{"beat": 8, "bpm": 240}, {"beat": 16, "bpm": 195}], "テンポパート（194.9997…→195）")
    dats, inp = _export(ed)
    t.eq(dats["Expert"]["bpmEvents"], [{"b": 8, "m": 240}, {"b": 16, "m": 195}], "書き出しの bpmEvents")
    t.eq(inp["info"]["environment"], "DefaultEnvironment", "環境は一番多い物")
    toast = _toast(ed)
    t.ok("難易度ごとに環境が違います（KaleidoscopeEnvironment: Hard / DefaultEnvironment: Expert・Expert+）。NLMの環境は1つなので DefaultEnvironment にしました" in toast,
         f"知らせ: {toast}")
    t.ok("ずれます" not in toast, "丸めてもずれない")
    # 区間が1つで audio.bpm と同じ（ランク譜面に多い形・端数あり）＝テンポパート無し。環境が1つなら環境の知らせも無い
    ed = t.fresh()
    info = _v4_info([("Expert", 0, "E.dat", "L.dat")], bpm=100)
    _load_v4(ed, info, {"AudioData.dat": _audio_data([(0, 425.555511, 99.9999984)]), "L.dat": _lightshow(0), "E.dat": _v4_diff([4, 8])})
    t.eq(json.loads(ed.js("window._dbg.rt.buildProjectText()"))["tempoParts"], [], "テンポパート無し")
    t.ok("環境が違います" not in _toast(ed) and "ライトボックス" not in _toast(ed), f"知らせ: {_toast(ed)}")
    t.no_errors()


def test_v4_light_boxes_and_njs(t):
    '''v4 のライトボックス（eventBoxGroups）はグループの数を srcLightBoxes へ（v3 と同じ道）。NJS の変化は読み込んだノーツのクリップに持たせ、
    譜面チェックの入力の json にだけ v4 の形で足す（書き出す .dat には入れず、書き出しの知らせに出す）。保存→開き直しでも残り、ファイル由来の形は確かめる'''
    from e2e_helpers import export_files
    ed = t.fresh()
    _load_v4(ed, *_v4_files())
    toast = _toast(ed)
    t.ok("この譜面のライトボックス（3グループ）はNLMでは読めず、書き出すと消えます" in toast, f"知らせ: {toast}")
    t.ok("NJSの変化（Expert 3回）はNLMでは編集できず、書き出すと消えます" in toast, f"知らせ: {toast}")
    _, inp = _export(ed)
    t.eq(_lbx(inp), {"Hard": 3, "Expert": 3, "ExpertPlus": 3}, "srcLightBoxes")
    by = _by_diff(inp)
    t.eq(by["Expert"]["njsEvents"], [{"b": 0, "i": 0}, {"b": 8, "i": 1}, {"b": 12, "i": 2}], "njsEvents（番号を省いた物は 0 番）")
    t.eq(by["Expert"]["njsEventData"], [{"p": 0, "e": -1, "d": 2}, {"p": 0, "e": 3, "d": -2}, {"p": 0, "e": -1, "d": 2}], "njsEventData")
    t.ok("njsEvents" not in by["Hard"], "NJS の変化の無い難易度には足さない")
    # BL評価リスト: R9（目視）・R3.A.1 と R3.C の注記・R10.A は対象外
    res = ed.js("""(async()=>{ const inp=await window._dbgApp.mapCheckInput();
      const MC=await import('/js/mapcheck/mapcheck.js'), BL=await import('/js/mapcheck/blcriteria.js');
      const r=BL.runBlCriteria(inp,MC.runMapCheck(inp));
      return Object.fromEntries(['R9','R3.A.1','R3.C','R10.A'].map(id=>{ const x=r.rules.find(q=>q.id===id);
        return [id,x.findings.filter(f=>f.d==='Expert').map(f=>f.status+' '+f.key)]; })); })()""")
    t.eq(res["R9"], ["check njsEventsUsed"], "R9")
    t.ok("note zIntersectNjs" in res["R3.A.1"], f"R3.A.1: {res['R3.A.1']}")
    t.ok("note njsBaseMc" in res["R3.C"], f"R3.C: {res['R3.C']}")
    t.eq(res["R10.A"], ["manual boxLightsUnread"], "R10.A は対象外（ライトボックス）")
    # 書き出し: .dat に NJS の変化は無く、書き出さない物を知らせる
    files = export_files(ed)
    t.ok("njsEvents" not in json.loads(files["ExpertStandard.dat"]), "書き出した .dat に NJS の変化は無い")
    st = ed.js("document.getElementById('stat').textContent")
    t.ok("NLMで扱えない物は書き出していません（Hard: ライトボックス 3グループ / Expert: ライトボックス 3グループ・NJSの変化 3回 / Expert+: ライトボックス 3グループ）" in st,
         f"書き出しの知らせ: {st}")
    # 保存→開き直し
    good = ed.js("window._dbg.rt.buildProjectText()")
    ed.js("(async()=>{ await window._dbg.rt.applyProject(%s); return true; })()" % good)
    t.eq(_by_diff(ed.js("window._dbgApp.mapCheckInput()"))["Expert"].get("njsEventData"), by["Expert"]["njsEventData"], "開き直しても残る")
    # ファイル由来の形を確かめる（形の違う物は捨てる）
    for bad in (["<b>1</b>"], [[1, 0, 0]], [[1, 2, 0, 0]], [[1, 0, 0.5, 0]], [[1, 0, 0, "2"]], "x", []):
        pj = json.loads(good)
        for s in pj["difficulties"]["expertstandard.dat"]["sections"]:
            if s.get("srcNjs"):
                s["srcNjs"] = bad
        ed.js("(async()=>{ await window._dbg.rt.applyProject(%s); return true; })()" % json.dumps(pj))
        t.ok("njsEvents" not in _by_diff(ed.js("window._dbgApp.mapCheckInput()"))["Expert"], f"形の違う srcNjs は捨てる: {bad}")
    t.no_errors()


def test_v4_undo_and_projsig(t):
    '''v4 の NJS の変化の印は読み込んだクリップの項目＝未保存の判定に入り、読み込みの Undo で消える'''
    ed = t.fresh()
    info = _v4_info([("Hard", 0, "H.dat", "L.dat")])
    _load_v4(ed, info, {"AudioData.dat": _audio_data([(0, 20, 120)]), "L.dat": _lightshow(0), "H.dat": _v4_diff([4, 8], njs=[(2, 0, 0, -3)])})
    t.eq(_by_diff(ed.js("window._dbgApp.mapCheckInput()"))["Hard"].get("njsEventData"), [{"p": 0, "e": 0, "d": -3}], "読み込んだ後")
    t.ok("srcNjs" in ed.js("window._dbgApp.sigPair().now"), "未保存の判定の中身に入る")
    ed.js("window._dbg.rt.undo();true")
    wait_until(ed, "window._dbgApp.nle().clips.length===0", label="Undo でクリップが消える")
    pj = json.loads(ed.js("window._dbg.rt.buildProjectText()"))
    t.eq([s.get("srcNjs") for d in pj["difficulties"].values() for s in d.get("sections", []) if s.get("srcNjs")], [], "Undo で印も消える")
    t.no_errors()


def test_v4_mixed_v3_file(t):
    '''v4 の Info.dat から v3 の難易度のファイルを指す譜面（ランク譜面にある）: その難易度はファイルの中のライト・BPM の変化を読む（ライトショーは使わない）'''
    ed = t.fresh()
    info = _v4_info([("Expert", 0, "E.dat", "L.dat")])
    _load_v4(ed, info, {"AudioData.dat": _audio_data([(0, 8, 120), (8, 30, 240)]), "L.dat": _lightshow(2), "E.dat": _v3([{"b": 8, "m": 240}], [4, 12])})
    dats, inp = _export(ed)
    t.eq(sorted(n["b"] for n in dats["Expert"]["colorNotes"]), [4, 12], "ノーツ")
    t.eq(sorted(e["b"] for e in dats["Expert"]["basicBeatmapEvents"]), [4, 12], "ライトはファイルの中の物")
    t.eq(json.loads(ed.js("window._dbg.rt.buildProjectText()"))["tempoParts"], [{"beat": 8, "bpm": 240}], "BPM の変化はファイルの bpmEvents")
    t.eq(_lbx(inp), {"Expert": 0}, "ライトショーのライトボックスは数えない")
    t.no_errors()

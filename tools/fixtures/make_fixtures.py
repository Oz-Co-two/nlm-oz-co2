"""テスト素材(tools/fixtures/)を作り直すスクリプト。

  basic.wav   … 120BPM・16秒のクリック音（4拍目ごとに高い音）。プログラム生成なので著作物の問題なし
  basic.nlmf  … basic.wav 用のプロジェクト。tools/cdp.py で実際にクリックして赤青ノーツを8個置いたもの
                （＝アプリ自身が保存した正規の形式。形式が変わったら作り直す）
  rich_map/   … 主要機能をひととおり含む Beat Saber の譜面フォルダ（Info.dat＋v3形式の Hard/Expert）。このスクリプトが生成
  rich.nlmf   … rich_map/ を「曲データを読み込む」（bulkLoadSongData）で読ませ、曲情報の接続・テンポパート(拍16→BPM150)の
                追加をマウス/キー入力で行って、アプリ自身に保存させたもの。音源は basic.wav を使い回す（cdp.py の FIXTURE_WAV）

使い方: .venv-build/Scripts/python.exe tools/fixtures/make_fixtures.py [basic] [rich]   （指定なし＝全部）
"""
import json
import math
import struct
import sys
import wave
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from cdp import Editor  # noqa: E402

BPM, SECONDS, RATE = 120, 16, 22050


def make_wav(path):
    n = SECONDS * RATE
    samples = [0.0] * n
    beat_len = 60 / BPM
    for i in range(int(SECONDS / beat_len)):
        start = int(i * beat_len * RATE)
        freq = 1760 if i % 4 == 0 else 880   # 小節頭は高い音
        for k in range(int(0.05 * RATE)):     # 50msの減衰クリック
            if start + k < n:
                samples[start + k] += 0.6 * math.exp(-k / (0.008 * RATE)) * math.sin(2 * math.pi * freq * k / RATE)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(b"".join(struct.pack("<h", int(max(-1, min(1, s)) * 32767)) for s in samples))


def make_project(path):
    # 空の状態から音源だけ読み、配置モードの赤枠にクリックでノーツを置く（1拍ずつ進めながら赤青交互）
    with Editor() as ed:
        ed.js("""(async()=>{ const blob=await (await fetch('tools/fixtures/basic.wav',{cache:'no-store'})).blob();
          const file=new File([blob],'basic.wav',{type:'audio/wav'});
          await window._dbg.rt.loadSongFromItem({isMusic:true,name:'basic',songFh:{getFile:async()=>file},info:{_beatsPerMinute:120}},0);
          return true; })()""")
        ed.wait(1.0)
        cells = [(1, 0), (2, 0), (0, 1), (3, 1), (1, 0), (2, 0), (1, 2), (2, 2)]
        for i, (x, y) in enumerate(cells):
            want = 0 if x < 2 else 1          # 左2列=赤 / 右2列=青
            if ed.js("window._dbgApp.state().brush.c") != want:
                ed.key("f")                   # F=ブラシ色反転
            ed.key("ArrowRight"); ed.key("ArrowRight")   # 1拍進める（スナップ1/2×2）
            ed.wait(0.3)
            p = ed.js(f"window._dbgApp.cellScreen({x},{y})")
            ed.move(p["x"], p["y"]); ed.wait(0.3)
            ed.click(p["x"], p["y"]); ed.wait(0.3)
        st = ed.js("window._dbgApp.state()")
        if st["counts"]["notes"] != len(cells):
            raise SystemExit(f"ノーツ配置に失敗: {st['counts']}（期待 {len(cells)}個）\n{ed.errors()}")
        text = ed.js("window._dbg.rt.buildProjectText()")
        pj = json.loads(text)
        pj["savedAt"] = "2026-01-01T00:00:00.000Z"   # 作り直しても差分が出にくいよう固定
        path.write_text(json.dumps(pj, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        print("ノーツ", st["counts"]["notes"], "個・エラー", ed.errors() or "なし")


# ---------------------------------------------------------------------------
# rich: 主要機能をひととおり含む素材（2難易度・赤青ノーツ全方向・ボム・壁・アーク・チェーン・ライト・テンポ変化・曲情報）
# 作り方: Beat Saber の譜面フォルダ（rich_map/）を用意し、MEDIA右クリック「曲データを読み込む」と同じ
# bulkLoadSongData に（ファイル選択の代わりに）偽のフォルダハンドルで渡して読ませる → 曲情報の接続・テンポパート追加は
# 本物のマウス/キー入力で行う → アプリ自身に保存させる（buildProjectText）。音源は basic.wav を使い回す。
# ---------------------------------------------------------------------------
RICH_INFO = {
    "_version": "2.1.0", "_songName": "リッチ テスト曲", "_songSubName": "fixture", "_songAuthorName": "NLM Test Artist",
    "_levelAuthorName": "NLM Tester", "_beatsPerMinute": 120, "_songTimeOffset": 0, "_shuffle": 0, "_shufflePeriod": 0.5,
    "_previewStartTime": 4, "_previewDuration": 6, "_songFilename": "song.egg", "_coverImageFilename": "",
    "_environmentName": "DefaultEnvironment", "_allDirectionsEnvironmentName": "GlassDesertEnvironment",
    "_difficultyBeatmapSets": [{"_beatmapCharacteristicName": "Standard", "_difficultyBeatmaps": [
        {"_difficulty": "Hard", "_difficultyRank": 5, "_beatmapFilename": "HardStandard.dat",
         "_noteJumpMovementSpeed": 14, "_noteJumpStartBeatOffset": 0},
        {"_difficulty": "Expert", "_difficultyRank": 7, "_beatmapFilename": "ExpertStandard.dat",
         "_noteJumpMovementSpeed": 17, "_noteJumpStartBeatOffset": -0.25},
    ]}],
}


def _v3(notes, bombs, walls, arcs, chains, lights):
    n = lambda b, x, y, c, d, a=0: {"b": b, "x": x, "y": y, "a": a, "c": c, "d": d}
    return {
        "version": "3.2.0",
        "bpmEvents": [{"b": 0, "m": 120}, {"b": 16, "m": 150}],   # 読み込みでは使われない（NLMのテンポはテンポパート）
        "rotationEvents": [],
        "colorNotes": [n(*v) for v in notes],
        "bombNotes": [{"b": b, "x": x, "y": y} for b, x, y in bombs],
        "obstacles": [{"b": b, "x": x, "y": y, "d": d, "w": w, "h": h} for b, x, y, d, w, h in walls],
        "sliders": [{"b": b, "c": c, "x": x, "y": y, "d": d, "mu": 1, "tb": tb, "tx": tx, "ty": ty, "tc": tc, "tmu": 1, "m": m}
                    for b, c, x, y, d, tb, tx, ty, tc, m in arcs],
        "burstSliders": [{"b": b, "c": c, "x": x, "y": y, "d": d, "tb": tb, "tx": tx, "ty": ty, "sc": sc, "s": s}
                         for b, c, x, y, d, tb, tx, ty, sc, s in chains],
        "waypoints": [],
        "basicBeatmapEvents": [{"b": b, "et": et, "i": i, "f": f} for b, et, i, f in lights],
        "colorBoostBeatmapEvents": [], "lightColorEventBoxGroups": [], "lightRotationEventBoxGroups": [],
        "lightTranslationEventBoxGroups": [], "basicEventTypesWithKeywords": {"d": []}, "useNormalEventsAsCompatibleEvents": True,
    }


def rich_map_files():
    """rich_map/ の中身（ファイル名→JSON）。数を変えたら tests/e2e の期待値（e2e_helpers.RICH）も直す"""
    # Expert: 赤青の全9方向（8=ドット）＋角度付き1個・チェーン2本（頭のノーツ付き＝実機の.datと同じ）・アーク2本（両端にノーツ）
    ex_notes = [
        (1, 1, 0, 0, 1), (1, 2, 0, 1, 1), (2, 1, 0, 0, 0), (2, 2, 0, 1, 0),
        (3, 0, 1, 0, 2), (3, 3, 1, 1, 3), (4, 1, 2, 0, 4), (4, 2, 2, 1, 5),
        (5, 0, 0, 0, 6), (5, 3, 0, 1, 7), (6, 1, 1, 0, 8), (6, 2, 1, 1, 8),
        (7.5, 1, 0, 0, 1, 45),                              # 角度オフセット付き（標準外の値も保存・書き出しで残るか）
        (10, 1, 2, 0, 1), (12, 2, 2, 1, 1),                 # チェーンの頭（読込でチェーンへ吸収→書き出しで再合成）
        (14, 1, 0, 0, 1), (16, 1, 2, 0, 0),                 # 赤アークの両端
        (18, 2, 0, 1, 1), (20, 2, 2, 1, 0),                 # 青アークの両端
        (17, 0, 1, 0, 2), (19, 3, 1, 1, 3), (22, 1, 0, 0, 1), (22, 2, 0, 1, 1), (24, 1, 1, 0, 8), (24, 2, 1, 1, 8),
    ]
    ex = _v3(
        ex_notes,
        bombs=[(8, 0, 0), (8, 3, 0), (21, 1, 2)],
        walls=[(9, 0, 0, 1, 1, 5), (23, 0, 2, 2, 4, 3)],
        arcs=[(14, 0, 1, 0, 1, 16, 1, 2, 0, 0), (18, 1, 2, 0, 1, 20, 2, 2, 0, 1)],
        chains=[(10, 0, 1, 2, 1, 10.5, 1, 0, 5, 0.8), (12, 1, 2, 2, 1, 12.5, 2, 0, 4, 1)],
        lights=[(0, 0, 1, 1), (0, 1, 5, 1), (2, 4, 3, 1), (4, 2, 2, 1), (4, 3, 6, 0.8), (8, 0, 0, 1),
                (8, 8, 0, 1), (12, 9, 0, 1), (12, 12, 3, 1), (16, 1, 7, 1), (20, 0, 1, 0.5), (24, 4, 0, 1)],
    )
    # Hard: Expert と中身が違う（難易度の混ざりを見分けられるように）。チェーン無し・アーク1本
    hd = _v3(
        [(2, 1, 0, 0, 1), (3, 2, 0, 1, 1), (4, 0, 1, 0, 2), (5, 3, 1, 1, 3), (6, 1, 0, 0, 8), (8, 2, 0, 1, 1), (10, 2, 2, 1, 0)],
        bombs=[(7, 3, 0)],
        walls=[(12, 3, 0, 2, 1, 5)],
        arcs=[(8, 1, 2, 0, 1, 10, 2, 2, 0, 0)],
        chains=[],
        lights=[(0, 0, 5, 1), (4, 1, 1, 1), (8, 4, 0, 1)],
    )
    return {"Info.dat": RICH_INFO, "ExpertStandard.dat": ex, "HardStandard.dat": hd}


def bulk_load_js(base_url, names, wav_url):
    """譜面フォルダ（base_url 配下の names）を MEDIA右クリック「曲データを読み込む」と同じ bulkLoadSongData で読ませるJS。
    ファイル選択の代わりに fetch で読む偽のフォルダハンドルを渡す。Info.dat の _songFilename は wav_url の中身を返す。
    tests/e2e からも使う（一括読込の経路の確認）"""
    return f"""(async()=>{{
      const base={json.dumps(base_url)}, names={json.dumps(names)};
      const info=await (await fetch(base+'Info.dat',{{cache:'no-store'}})).json();
      const wav=await (await fetch({json.dumps(wav_url)},{{cache:'no-store'}})).blob();
      const wavName={json.dumps(wav_url.rsplit('/', 1)[-1])};
      const dir={{name:base.split('/').filter(Boolean).pop(), getFileHandle:async nm=>{{
        if(nm===info._songFilename) return {{name:nm,getFile:async()=>new File([wav],wavName,{{type:'audio/wav'}})}};
        if(!names.includes(nm)) throw new DOMException('not found','NotFoundError');
        const txt=await (await fetch(base+nm,{{cache:'no-store'}})).text();
        return {{name:nm,getFile:async()=>new File([txt],nm,{{type:'application/json'}})}}; }}}};
      await window._dbg.rt.bulkLoadSongData({{name:dir.name,info,dir}});
      return true; }})()"""


def _fix_random_ids(pj):
    """クリップ/旧ノードのidは「連番＋乱数4文字」＝作り直すたびに変わる。乱数部分を決まった文字に置き換える（参照も同じ値へ）"""
    ids = [x["id"] for x in pj["graph"].get("extra", [])]
    for st in pj["difficulties"].values():
        ids += [s["id"] for s in st.get("sections") or [] if "id" in s]
    ren = {old: old[:-4] + f"fx{i:02d}" for i, old in enumerate(dict.fromkeys(ids)) if len(old) > 5}

    def walk(v):
        if isinstance(v, dict):
            return {k: walk(x) for k, x in v.items()}
        if isinstance(v, list):
            return [walk(x) for x in v]
        return ren.get(v, v) if isinstance(v, str) else v
    return walk(pj)


def make_rich(proj_path, map_dir):
    map_dir.mkdir(exist_ok=True)
    files = rich_map_files()
    for name, obj in files.items():
        (map_dir / name).write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")
    with Editor(ready=True) as ed:
        # 1) 曲データの一括読込（音源・BPM・試聴区間・曲情報ノード・全難易度のNJS/譜面クリップ）。song.egg の中身は basic.wav
        ed.js(bulk_load_js("tools/fixtures/rich_map/", list(files), "tools/fixtures/basic.wav"))
        ed.wait(1.0)
        # 2) INFO画面: 読み込まれた曲情報ノード（未接続）を書き出しノードの曲情報ポートへドラッグで繋ぐ（既存の空の曲情報は外れる）
        nle = ed.js("window._dbgApp.nleScreen(0)")
        hx, hy = nle["left"] + nle["w"] * 0.6, nle["lanes"] + 40   # NLEの上にマウスを置いてTab=INFOへ（切替はTabのみ）
        ed.move(hx, hy); ed.key("Tab"); ed.wait(0.6)
        if ed.js("window._dbgApp.view()") != "info":
            raise SystemExit("INFO画面に切り替わりません")
        meta_new = ed.js("Object.entries(window._dbgApp.infoGraph().nodes).filter(([k,n])=>n.t==='meta'&&n.data.name).map(([k])=>k)[0]||null")
        # 読み込んだノードは既存ノードの下に置かれる＝表示範囲の外のことがある。左上を基準にホイールで縮小して見える所へ
        ir = ed.js("(()=>{const r=document.getElementById('inspcol').getBoundingClientRect();return {x:r.left,y:r.top}})()")
        for _ in range(12):
            if ed.js(f"""(()=>{{const r=document.getElementById('inspcol').getBoundingClientRect(),
                p=document.querySelector('[data-port="{meta_new}"]').getBoundingClientRect(); return p.top>r.top+50&&p.bottom<r.bottom-10}})()"""):
                break
            ed.wheel(ir["x"] + 30, ir["y"] + 60, 120); ed.wait(0.2)
        pos = ed.js(f"""(()=>{{const c=e=>{{const r=e.getBoundingClientRect();return {{x:r.left+r.width/2,y:r.top+r.height/2}}}};
          return {{a:c(document.querySelector('[data-port="{meta_new}"]')),b:c(document.querySelector('[data-oport="o1|meta"]'))}}}})()""")
        ed.drag(pos["a"]["x"], pos["a"]["y"], pos["b"]["x"], pos["b"]["y"], steps=20); ed.wait(0.4)
        # 設定ノード: 書き出す難易度（Hard / Expert）にチェック
        for d in ("Hard", "Expert"):
            p = ed.js(f"(()=>{{const e=document.querySelector('.iGrp[data-node=\"s1\"] input[data-d=\"{d}\"]');const r=e.getBoundingClientRect();return {{x:r.left+r.width/2,y:r.top+r.height/2}}}})()")
            ed.click(p["x"], p["y"]); ed.wait(0.2)
        # NLEへ戻す（チェックボックスにフォーカスがあるとキーが入力欄扱いで届かない＝空き地をクリックしてからTab）
        r = ed.js("(()=>{const r=document.getElementById('inspcol').getBoundingClientRect();return {x:r.left+8,y:r.bottom-8}})()")
        ed.click(r["x"], r["y"]); ed.key("Tab"); ed.wait(0.6)
        if ed.js("window._dbgApp.view()") != "nle":
            raise SystemExit("NLE画面に戻りません")
        # テンポ変化（拍16で150）と、開いていない難易度（Expert）の中身は一括読込だけで入る（下で確かめる）

        pj = json.loads(ed.js("window._dbg.rt.buildProjectText()"))
        st = ed.js("window._dbgApp.state()")
        ig = ed.js("window._dbgApp.infoGraph()")
        errs = ed.errors()
    meta_on = [e["s"] for e in ig["edges"] if ig["nodes"].get(e["s"], {}).get("t") == "meta"]
    problems = []
    if pj.get("tempoParts") != [{"beat": 16, "bpm": 150}]:
        problems.append(f"テンポパート: {pj.get('tempoParts')}")
    if meta_on != [meta_new] or ig["nodes"][meta_new]["data"]["name"] != RICH_INFO["_songName"]:
        problems.append(f"曲情報の接続: {meta_on} / {meta_new}")
    if (pj.get("info") or {}).get("_songName") != RICH_INFO["_songName"]:
        problems.append(f"曲名: {(pj.get('info') or {}).get('_songName')}")
    if sorted(pj["difficulties"]) != ["expertstandard.dat", "hardstandard.dat"]:
        problems.append(f"難易度: {sorted(pj['difficulties'])}")
    if errs or problems:
        raise SystemExit(f"rich の作成に失敗: {problems} / エラー {errs}")
    pj["savedAt"] = "2026-01-01T00:00:00.000Z"   # 作り直しても差分が出にくいよう固定
    pj = _fix_random_ids(pj)
    proj_path.write_text(json.dumps(pj, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print("rich: 現在の難易度", st["diff"], st["counts"], "・テンポ", pj["tempoParts"])


if __name__ == "__main__":
    only = sys.argv[1:]   # 例: make_fixtures.py rich（指定が無ければ全部）
    if not only or "basic" in only:
        make_wav(HERE / "basic.wav")
        print("作成:", HERE / "basic.wav")
        make_project(HERE / "basic.nlmf")
        print("作成:", HERE / "basic.nlmf")
    if not only or "rich" in only:
        make_rich(HERE / "rich.nlmf", HERE / "rich_map")
        print("作成:", HERE / "rich.nlmf", "/", HERE / "rich_map")

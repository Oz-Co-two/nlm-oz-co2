"""REPLAY の窓を本物どうしでつなぐ（2026-11-22）: 本物の裏側（serve.py の /__replay/*・viewer のサーバー＝http://localhost:<番号>）・
本物の BL のリプレイアプリの写し（replay-viewer/blreplay/）・本物の伝言の受け手（replay-viewer/bridge.js）。

画面の細かい決まり（一覧の行・灰色・同期の間隔など）は偽物で速く確かめる test_replay.py が受け持つ。ここは「つないだら本当に動くか」だけ:
合成の控え（tests/_lib/replay_fixture.py・音は素材の basic.wav）と合成のリプレイを置き、REPLAY を出す → 一覧 → 自動で開く →
BL のリプレイアプリが曲を読めた（ready）→ 位置の同期（両方向）→ ▶ でリプレイが進み NLM が付いてくる → 窓の上のホイールでズーム →
窓の中を押した後の Tab で窓が切り替わる。BL のリプレイアプリは WebGL・A-Frame を読むので、1 本にまとめている。
"""
from pathlib import Path

import replay_fixture as RF
from misc_helpers import open_fixture_ready, wait_until
from replay_helpers import rp, to_replay, wait_list, wait_state

ROOT = Path(__file__).resolve().parents[2]
SONG, MAPPER = "リッチ テスト曲", "NLM Tester"


def _frame_rect(ed):
    return ed.js("(r=>({x:r.left+r.width/2,y:r.top+r.height/2,w:r.width,h:r.height}))(document.getElementById('rpFrame').getBoundingClientRect())")


def test_replay_real_viewer(t):
    '''本物どうし: 一覧 → 自動で開く（localhost の別のオリジン）→ BL のリプレイアプリが曲を読める → NLM の位置へ動く・リプレイの位置へ NLM が
    付いてくる → ▶ でリプレイが進み NLM が付いてくる（NLM の曲の音は鳴らさない）→ 窓の上のホイールでズーム（重ねた表示が倍率に）→
    窓の中を押した後の Tab で REPLAY → MEDIA'''
    ed = open_fixture_ready(t, "rich")
    RF.reset(ed.data_dir, ed.replays_dir)
    files = RF.make_map(song=SONG, mapper=MAPPER, diffs=("Expert",), bpm=120.0)
    h = RF.keep_map(ed.data_dir, files, egg=(ROOT / "tools" / "fixtures" / "basic.wav").read_bytes())
    RF.write_replay(ed.replays_dir, song=SONG, mapper=MAPPER, h=h, diff="Expert", notes=RF.NOTES, end=15.0)

    to_replay(ed)
    wait_list(ed, 1)
    r = rp(ed)
    t.eq([(x["playable"], x["latest"]) for x in r["rows"]], [(True, True)], f"一覧＝控えのある版が 1 件: {r['rows']}")
    st = wait_state(ed, "linked", timeout=60)
    r = rp(ed)
    t.ok(r["origin"].startswith("http://localhost:"), f"窓は別のオリジン（localhost）: {r['origin']}")
    t.ok(r["src"].startswith(r["origin"] + "/blreplay/"), f"窓は BL のリプレイアプリ: {r['src']}")
    wait_until(ed, "(r=>r.ready&&r.dur>10)(window._dbgApp.replay())", timeout=60, label="BL のリプレイアプリが曲を読めた")

    # NLM → リプレイ: 8 拍（4 秒）へ
    g = ed.js("window._dbgApp.nleScreen(8)")
    ed.click(g["x"], g["ruler"] + 6)
    wait_until(ed, "(r=>Math.abs(r.t-4)<0.05&&!r.hold)(window._dbgApp.replay())", timeout=15, label="リプレイが 4 秒へ")
    t.ok(abs(rp(ed)["nlm"]["sec"] - 4) < 1e-6, f"NLM は 4 秒のまま: {rp(ed)['nlm']}")

    # ▶（NLM の Space）→ リプレイが進み、NLM が付いてくる
    g = ed.js("window._dbgApp.nleScreen(0)")
    ed.move(g["left"] + g["w"] * 0.6, g["lanes"] + 40)
    ed.key(" ")
    wait_until(ed, "(r=>r.playing&&r.nlm.playing&&r.t>4.3)(window._dbgApp.replay())", timeout=15, label="リプレイが再生で進む")
    r = rp(ed)
    t.ok(abs(r["nlm"]["sec"] - r["t"]) < 0.2, f"NLM がリプレイの時刻に付いてくる: NLM {r['nlm']['sec']} / リプレイ {r['t']}")
    t.eq(r["nlm"]["srcs"], 0, "NLM の曲の音は鳴らさない")
    ed.key(" ")
    wait_until(ed, "(r=>!r.playing&&!r.nlm.playing)(window._dbgApp.replay())", timeout=10, label="Space で止まる")

    # リプレイ → NLM: 窓の中の位置の変化（伝言の受け手の seek と同じ道＝BL の時刻の棒）は同期のテスト（偽物）で見ているので、ここは NLM から 2 秒へ戻して付いてくるかだけ
    g = ed.js("window._dbgApp.nleScreen(4)")
    ed.click(g["x"], g["ruler"] + 6)
    wait_until(ed, "(r=>Math.abs(r.t-2)<0.05&&!r.hold)(window._dbgApp.replay())", timeout=15, label="リプレイが 2 秒へ")

    # 窓の上のホイール＝ズーム（BL のリプレイアプリの 3D の上）
    f = _frame_rect(ed)
    t.ok(rp(ed)["zoomText"] != "", f"重ねた「ホイールでズーム」が出ている: {rp(ed)['zoomText']!r}")
    for _ in range(3):
        ed.wheel(f["x"], f["y"] - f["h"] * 0.1, -100)
        ed.wait(0.1)
    wait_until(ed, "window._dbgApp.replay().zoom>1.4", timeout=10, label="ホイールで寄る（倍率が伝言で届く）")
    z = rp(ed)
    t.ok("1.5" in z["zoomText"] or "×" in z["zoomText"], f"重ねた表示が倍率に: {z['zoomText']!r}（{z['zoom']}）")
    for _ in range(4):
        ed.wheel(f["x"], f["y"] - f["h"] * 0.1, 100)
        ed.wait(0.1)
    wait_until(ed, "window._dbgApp.replay().zoom===1", timeout=10, label="戻すと 1 倍")

    # 窓の中を押した後の Tab（入力は窓へ行く → bridge.js が NLM へ渡す）
    ed.click(f["x"], f["y"] - f["h"] * 0.1)
    ed.wait(0.3)
    t.eq(ed.js("document.activeElement&&document.activeElement.id"), "rpFrame", "窓の中を押すと入力は窓へ")
    ed.key("Tab")
    wait_until(ed, "window._dbgApp.replay().pvMode==='media'", timeout=10, label="窓の中の Tab で REPLAY → MEDIA")
    t.ok(ed.js("document.activeElement&&document.activeElement.id") != "rpFrame", "切り替えた後は入力を NLM へ戻す")
    errs = [m for m in ed.console_errors() if "localhost" not in m and "beatleader" not in m.lower()] if hasattr(ed, "console_errors") else []
    t.eq(errs, [], "NLM の画面に例外が無い（BL のリプレイアプリの中の BeatLeader への問い合わせの失敗は除く）")


def _viewer_tab(ed):
    """リプレイの窓（localhost の別のオリジンの iframe）に CDP でつなぎ、JS を流せる Tab（閉じない＝窓は NLM の物）"""
    from cdp import Tab
    tg = ed.pipe.call("Target.getTargets")["targetInfos"]
    fr = next(x for x in tg if x["type"] == "iframe" and "localhost" in x["url"])
    tab = Tab(ed, fr["targetId"], ed.pipe.attach(fr["targetId"]))
    tab.call("Runtime.enable")
    return tab


def test_replay_real_tempo_not_from_zero(t):
    '''テンポパートのある書き出し（bpmEvents の最初が拍 0 に無い＝NLM の書き出しの形）でも、BL のリプレイアプリの中のノーツの秒が Info.dat の BPM で
    数えた秒になる。BL のリプレイアプリは最初の変化の前の拍まで変化の後の BPM で数える＝直す前は拍 2 のノーツが 1.0 秒でなく 1.5 秒になり、
    リプレイの出来事より後になってノーツが出なかった（viewer へ渡す map.zip で拍 0 に基準の BPM を足して直した・replays._viewer_dat）'''
    import json
    ed = open_fixture_ready(t, "rich")
    RF.reset(ed.data_dir, ed.replays_dir)
    files = RF.make_map(song=SONG, mapper=MAPPER, diffs=("Expert",), bpm=120.0, notes=4)   # ノーツは拍 2・3・4・5
    dat = json.loads(files["ExpertStandard.dat"])
    dat["bpmEvents"] = [{"b": 4, "m": 240}]   # 拍 4 から BPM 240（拍 0〜4 は 120＝2 秒）
    files["ExpertStandard.dat"] = json.dumps(dat).encode("utf-8")
    h = RF.keep_map(ed.data_dir, files, egg=(ROOT / "tools" / "fixtures" / "basic.wav").read_bytes())
    RF.write_replay(ed.replays_dir, song=SONG, mapper=MAPPER, h=h, diff="Expert", notes=RF.NOTES, end=15.0)
    to_replay(ed)
    wait_list(ed, 1)
    wait_state(ed, "linked", timeout=60)
    wait_until(ed, "(r=>r.ready&&r.dur>10)(window._dbgApp.replay())", timeout=60, label="BL のリプレイアプリが曲を読めた")
    tab = _viewer_tab(ed)
    got = tab.js("(()=>{const bg=document.querySelector('a-scene').components['beat-generator'];"
                 "return bg.beatData._notes.map(n=>[n._time,+n._songTime.toFixed(4)]);})()")
    t.eq(got, [[2, 1.0], [3, 1.5], [4, 2.0], [5, 2.25]], f"ノーツの拍と秒（拍 4 までは BPM 120・後は 240）: {got}")

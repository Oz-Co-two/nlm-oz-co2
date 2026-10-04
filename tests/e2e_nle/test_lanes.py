"""NLEのレーン: ロック/ソロ/ミュート（L/S/M キーと左端のボタン）・レーンの追加/削除。
仕様（docs/tutorial-advanced.md 3章）: ミュートとソロは表示を切り替えるだけで、書き出しには全部のレーンの中身が入る。
ロックは3Dビューで選んだり直したりできなくなる。レーンの状態はプロジェクトと一緒に保存される"""
import json

from e2e_helpers import wait_until, counts
from nle_helpers import (open_nle, clips, hover, menu, export_dat, nle, nle_mouse, scr, lane_y, undo, take_errors, hover_canvas)


def _visible_notes(ed):
    """3Dビューに出ているノーツ系（ノーツ・ボム・壁・アーク・チェーン）の数"""
    return ed.js("window._dbgApp.objScreen().filter(o=>o.kind!=='light').length")


def _gutter_btn(ed, kind, lk, track):
    """レーン左端の L/S/M ボタンの中心（drawLayers の配置: L=溝の右端-62, S=-42, M=-22・幅16 / 上端+5・高さ14）"""
    s = scr(ed)
    off = {"l": 62, "s": 42, "m": 22}[kind]
    top = (s["notes"] if lk == "n" else s["lights"])[track]
    return s["left"] + s["gut"] - off + 8, top + 12


def test_mute_key_display_only(t):
    '''Notes 3 にマウスを置いてM→3Dのノーツが消える・書き出しは変わらない・保存内容に残る→もう一度Mで戻る'''
    ed = open_nle(t, "rich")
    before = export_dat(ed)
    nc = clips(ed, "n")[0]
    v0 = _visible_notes(ed)
    t.ok(v0 > 0, f"最初は3Dにノーツが出ている（{v0}）")
    hover(ed, 8, "n", nc["track"])
    ed.key("m")
    wait_until(ed, f"window._dbgApp.nle().mute.includes('n{nc['track']}')", label="ミュート")
    wait_until(ed, "window._dbgApp.objScreen().filter(o=>o.kind!=='light').length===0", label="3Dからノーツが消える")
    t.eq(counts(ed)["notes"], 7, "中身（ノーツの数）は減らない")
    t.eq(export_dat(ed), before, "ミュートしても書き出しには全部のレーンの中身が入る")
    pj = json.loads(ed.js("window._dbg.rt.buildProjectText()"))
    t.eq(pj["laneStates"]["mute"], [f"n{nc['track']}"], "ミュートの状態がプロジェクトに保存される")
    hover(ed, 8, "n", nc["track"])
    ed.key("m")
    wait_until(ed, "window._dbgApp.nle().mute.length===0", label="ミュート解除")
    wait_until(ed, f"window._dbgApp.objScreen().filter(o=>o.kind!=='light').length==={v0}", label="3Dにノーツが戻る")
    t.no_errors()


def test_solo_key(t):
    '''空のレーンをS（ソロ）→同じグループの他のレーンのノーツが3Dから消える・ライトのレーンには効かない・ソロとミュートは同時にONにならない'''
    ed = open_nle(t, "rich")
    before = export_dat(ed)
    nc = clips(ed, "n")[0]
    lights0 = ed.js("window._dbgApp.lights().events.length")
    hover(ed, 8, "n", 2)   # 空の Notes 1
    ed.key("s")
    wait_until(ed, "window._dbgApp.nle().solo.includes('n2')", label="Notes 1 をソロ")
    wait_until(ed, "window._dbgApp.objScreen().filter(o=>o.kind!=='light').length===0", label="ソロでないレーンのノーツが消える")
    t.eq(export_dat(ed), before, "ソロでも書き出しは変わらない")
    t.eq(ed.js("window._dbgApp.lights().events.length"), lights0, "ライトはノーツのソロの影響を受けない")
    hover(ed, 8, "n", nc["track"])
    ed.key("s")   # Notes 3 もソロ＝表示される
    wait_until(ed, "window._dbgApp.objScreen().filter(o=>o.kind!=='light').length>0", label="ソロに加えたレーンが出る")
    ed.key("m")   # 同じレーンをミュート＝ソロが外れる
    wait_until(ed, f"window._dbgApp.nle().mute.includes('n{nc['track']}')", label="ミュート")
    st = nle(ed)
    t.ok(f"n{nc['track']}" not in st["solo"], f"ミュートするとそのレーンのソロは外れる: {st['solo']}")
    t.no_errors()


def test_lock_blocks_3d_select(t):
    '''Notes 3 をL（ロック）→選んでいたノーツは外れ、3Dでクリックしても選べず中身も変わらない→もう一度Lで解除すると選べる'''
    ed = open_nle(t, "rich")
    nc = clips(ed, "n")[0]
    notes_js = "window._dbgApp.notes().notes.map(n=>[n.beat,n.x,n.y,n.c,n.d,n._tr])"

    def click_note():
        o = next(o for o in ed.js("window._dbgApp.objScreen()") if o["kind"] == "note" and o["inView"])
        ed.move(o["sx"], o["sy"]); ed.wait(0.1)
        ed.click(o["sx"], o["sy"]); ed.wait(0.15)
        return o
    hover_canvas(ed)
    ed.key("q")   # カメラ固定モード（配置済みのオブジェクトのクリック=選択）
    wait_until(ed, "window._dbgApp.state().camMode==='edit'", label="カメラ固定モード")
    ed.wait(0.15)
    click_note()
    wait_until(ed, "window._dbgApp.state().sel===1", label="ロック前はクリックで選べる")
    hover(ed, 8, "n", nc["track"])
    ed.key("l")
    wait_until(ed, f"window._dbgApp.nle().lock.includes('n{nc['track']}')", label="ロック")
    t.eq(ed.js("window._dbgApp.state().sel"), 0, "ロックしたレーンの選択は外れる")
    notes0, undo0 = ed.js(notes_js), ed.js("window._dbgApp.state().undo")
    click_note()
    t.eq(ed.js(notes_js), notes0, "ロック中のレーンのノーツはクリックしても変わらない")
    t.eq(ed.js("window._dbgApp.state().sel"), 0, "ロック中はクリックしても選べない")
    t.eq(ed.js("window._dbgApp.state().undo"), undo0, "ロック中のクリックは履歴を積まない")
    hover(ed, 8, "n", nc["track"])
    ed.key("l")
    wait_until(ed, "window._dbgApp.nle().lock.length===0", label="ロック解除")
    click_note()
    wait_until(ed, "window._dbgApp.state().sel===1", label="解除後は選べる")
    t.no_errors()


def test_lane_states_saved_and_restored(t):
    '''左端の L/S/M ボタンでも切り替わる／レーンの状態（ミュート/ソロ/ロック）は保存したプロジェクトを開き直しても戻る'''
    ed = open_nle(t, "rich")
    # 左端のボタン（Light 2）でもキーと同じように切り替わる
    for kind, field in (("l", "lock"), ("s", "solo"), ("m", "mute")):
        ed.click(*_gutter_btn(ed, kind, "l", 1))
        wait_until(ed, f"window._dbgApp.nle().{field}.includes('l1')", label=f"Light 2 の{field}ボタン")
    st = nle(ed)
    t.eq((st["lock"], st["solo"], st["mute"]), (["l1"], [], ["l1"]), "ボタン: ロックは独立・ソロはミュートで外れる")
    ed.click(*_gutter_btn(ed, "m", "l", 1))
    wait_until(ed, "window._dbgApp.nle().mute.length===0", label="もう一度押すと解除")
    hover(ed, 8, "n", 0); ed.key("m")
    hover(ed, 8, "l", 0); ed.key("l")
    hover(ed, 8, "l", 2); ed.key("s")
    wait_until(ed, "window._dbgApp.nle().solo.length===1", label="キーで状態を設定")
    want = {k: nle(ed)[k] for k in ("mute", "solo", "lock")}
    t.eq({k: sorted(v) for k, v in want.items()}, {"mute": ["n0"], "solo": ["l2"], "lock": ["l0", "l1"]}, "設定した状態")
    text = ed.js("window._dbg.rt.buildProjectText()")
    ed = t.fresh()
    ed.js(f"window._dbg.rt.applyProject(JSON.parse({json.dumps(text)}))")
    wait_until(ed, "window._dbgApp.nle().clips.length===2", label="開き直し")
    t.eq({k: nle(ed)[k] for k in ("mute", "solo", "lock")}, want, "開き直した後のレーンの状態")
    t.no_errors()


def test_lane_add_remove(t):
    '''一番上にクリップがあると削除できない／溝の右クリックでノーツのレーンを一番上に追加→既存のクリップは番号を保ったまま1段下がる→Undo。一番上が空なら削除できる'''
    ed = open_nle(t, "rich")
    before = export_dat(ed)
    s = scr(ed)
    gx = s["left"] + 20
    menu(ed, gx, lane_y(ed, "l", 1), "レーンを削除")   # 一番上（Light 3）にクリップがある＝削除できない
    ed.wait(0.2)
    t.eq(nle(ed)["lanes"]["l"], 3, "一番上にクリップがあるとライトのレーンは削除できない")
    t.eq(take_errors(ed, "クリップがあるため削除できません"), 1, "削除できない旨のエラー")
    menu(ed, gx, lane_y(ed, "n", 1), "レーンを追加")
    wait_until(ed, "window._dbgApp.nle().lanes.n===4", label="ノーツのレーンの追加")
    nc = clips(ed, "n")[0]
    t.eq(nc["track"], 1, "クリップは1段下がる（表示の番号 Notes 3 は同じ）")
    t.eq(nle(ed)["lanes"]["l"], 3, "ライトのレーンは変わらない")
    t.eq(export_dat(ed), before, "書き出しは変わらない")
    nle_mouse(ed)
    undo(ed)
    wait_until(ed, "window._dbgApp.nle().lanes.n===3", label="追加のUndo")
    t.eq(clips(ed, "n")[0]["track"], 0, "Undoでクリップの段も戻る")
    # 追加→一番上（空）を削除
    menu(ed, gx, lane_y(ed, "n", 1), "レーンを追加")
    wait_until(ed, "window._dbgApp.nle().lanes.n===4", label="もう一度追加")
    menu(ed, gx, lane_y(ed, "n", 1), "レーンを削除")
    wait_until(ed, "window._dbgApp.nle().lanes.n===3", label="空の一番上のレーンを削除")
    t.eq(clips(ed, "n")[0]["track"], 0, "削除でクリップは1段上がる")
    t.eq(export_dat(ed), before, "書き出しは変わらない")
    t.no_errors()


def test_lane_add_resets_solo_mute(t):
    '''レーンを追加するとソロ/ミュートは外れ（位置で覚えているため）、ロックは同じレーンに付いたまま1段ずれる'''
    ed = open_nle(t, "rich")
    hover(ed, 8, "n", 0); ed.key("l")
    hover(ed, 8, "n", 1); ed.key("m")
    wait_until(ed, "window._dbgApp.nle().mute.length===1&&window._dbgApp.nle().lock.length===1", label="ロックとミュート")
    menu(ed, scr(ed)["left"] + 20, lane_y(ed, "n", 2), "レーンを追加")
    wait_until(ed, "window._dbgApp.nle().lanes.n===4", label="レーンの追加")
    st = nle(ed)
    t.eq(st["mute"], [], "ミュートは外れる")
    t.eq(st["lock"], ["n1"], "ロックは同じレーン（1段下がった Notes 3）に付いたまま")
    t.no_errors()

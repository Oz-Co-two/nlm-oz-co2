"""NLEのクリップの分割（C・分割モードR・マーカーでカット）と結合（Ctrl+G）。
分けてもつなげても中身（ノーツ・ライトの数と絶対拍）と書き出しが変わらないこと、Undo/Redoで戻ることを確かめる"""
from e2e_helpers import wait_until
from nle_helpers import (open_nle, clips, total, select, hover, menu, clip_xy, export_dat, nle, nle_mouse, scr,
                         undo, redo)


def _note_clip(ed):
    return clips(ed, "n")[0]


def test_cut_c_key(t):
    '''クリップを選んで拍6にマウスを置きCで分割→2つに分かれ中身と書き出しは同じ・後ろは「'」付き→Undo/Redo'''
    ed = open_nle(t, "rich")
    before = export_dat(ed)
    c0 = _note_clip(ed)
    n0 = total([c0])
    select(ed, c0)
    hover(ed, 6, "n", c0["track"])
    ed.key("c")
    wait_until(ed, "window._dbgApp.nle().clips.filter(c=>c.lk==='n').length===2", label="Cで分割")
    a, b = clips(ed, "n")
    t.eq((a["beat"], a["len"], b["beat"], b["len"]), (0, 6, 6, 10), "分割後の位置と長さ（拍）")
    t.eq((a["track"], b["track"]), (c0["track"], c0["track"]), "分割後も同じレーン")
    t.eq(b["label"], c0["label"] + "'", "後ろ側の名前に「'」が付く")
    t.ok(a["id"] != b["id"], "別のクリップになる")
    t.eq(total([a, b]), n0, "中身の数の合計は変わらない")
    t.eq(a["n"]["notes"], 4, "拍6より前のノーツ（拍2,3,4,5）が前側に入る")
    t.eq(nle(ed)["sel"], [], "分割後は選択が外れる")
    t.eq(export_dat(ed), before, "書き出し（全難易度の.dat）は分割の前と同じ")
    nle_mouse(ed)
    undo(ed)
    wait_until(ed, "window._dbgApp.nle().clips.filter(c=>c.lk==='n').length===1", label="分割のUndo")
    c1 = _note_clip(ed)
    t.eq((c1["beat"], c1["len"], c1["label"], c1["n"]), (0, 16, c0["label"], c0["n"]), "Undoで元の1つに戻る")
    redo(ed)
    wait_until(ed, "window._dbgApp.nle().clips.filter(c=>c.lk==='n').length===2", label="分割のRedo")
    t.eq([(c["beat"], c["len"]) for c in clips(ed, "n")], [(0, 6), (6, 10)], "Redoで再び分かれる")
    t.no_errors()


def test_cut_c_needs_selection_and_range(t):
    '''Cは選んだクリップだけを切る: 未選択のクリップ・クリップの外にマウスがある時は何もしない'''
    ed = open_nle(t, "rich")
    nc, lc = clips(ed, "n")[0], clips(ed, "l")[0]
    hover(ed, 6, "n", nc["track"])
    ed.key("c")   # 何も選んでいない
    ed.wait(0.2)
    t.eq(len(clips(ed)), 2, "未選択ならどのクリップも切れない")
    select(ed, lc)   # ライトのクリップだけ選ぶ
    hover(ed, 20, "l", lc["track"])   # クリップの外（拍20）
    ed.key("c")
    ed.wait(0.2)
    t.eq(len(clips(ed)), 2, "クリップの範囲外では切れない")
    hover(ed, 4, "n", nc["track"])
    ed.key("c")
    wait_until(ed, "window._dbgApp.nle().clips.length===3", label="選んだライトのクリップだけ分割")
    t.eq([(c["beat"], c["len"]) for c in clips(ed, "l")], [(0, 4), (4, 12)], "ライトのクリップが拍4で分かれる")
    t.eq(len(clips(ed, "n")), 1, "選んでいないノーツのクリップはそのまま")
    t.eq(total(clips(ed, "l"))["lights"], 3, "ライトの数は変わらない")
    t.no_errors()


def test_razor_mode_click(t):
    '''Rで分割モード→クリップをクリックした位置で分割（スナップ幅に揃う）→Escで分割モードが切れる'''
    ed = open_nle(t, "rich")
    before = export_dat(ed)
    c0 = _note_clip(ed)
    nle_mouse(ed)
    ed.key("r")
    wait_until(ed, "window._dbgApp.nle().razor===true", label="分割モードON")
    x, y = clip_xy(ed, c0, 8)
    ed.click(x, y)
    wait_until(ed, "window._dbgApp.nle().clips.filter(c=>c.lk==='n').length===2", label="クリックで分割")
    t.eq([(c["beat"], c["len"]) for c in clips(ed, "n")], [(0, 8), (8, 8)], "クリックした拍8で分かれる")
    t.eq(export_dat(ed), before, "書き出しは変わらない")
    ed.key("Escape")
    wait_until(ed, "window._dbgApp.nle().razor===false", label="Escで分割モードOFF")
    # 拍の途中（スナップ幅0.5拍の間）をクリックした時もスナップ幅に揃う（Cや移動と同じ。端数の拍で切れると長さが半端な数になる）
    ed.key("r")
    wait_until(ed, "window._dbgApp.nle().razor===true", label="分割モードON（2回目）")
    s = scr(ed, 4)
    x4 = s["x"] + (scr(ed, 4.5)["x"] - s["x"]) * 0.3   # 拍4と4.5の間（4.15拍）
    ed.click(x4, y)
    wait_until(ed, "window._dbgApp.nle().clips.filter(c=>c.lk==='n').length===3", label="2回目の分割")
    cut = clips(ed, "n")[1]["beat"]
    snap = nle(ed)["snap"]
    t.eq(cut, 4.0, "スナップ幅に揃った拍で分かれる")
    t.no_errors()


def test_merge_ctrl_g(t):
    '''Ctrl+Gは1つだけ・種類違いでは何もしない／Cで分けた2つをShift+クリックで選びCtrl+Gで結合→1つ・長さと中身と書き出しは元どおり→Undoで2つに戻る'''
    ed = open_nle(t, "rich")
    before = export_dat(ed)
    c0 = _note_clip(ed)
    select(ed, c0)
    ed.key("g", ctrl=True)
    ed.wait(0.2)
    t.eq(len(clips(ed)), 2, "1つだけでは結合しない")
    select(ed, clips(ed, "l")[0], shift=True)
    undo_n = ed.js("window._dbgApp.state().undo")
    ed.key("g", ctrl=True)
    ed.wait(0.2)
    t.eq(len(clips(ed)), 2, "ノーツとライトのクリップは結合しない")
    t.eq(ed.js("window._dbgApp.state().undo"), undo_n, "何もしない時は履歴を積まない")
    select(ed, c0)
    hover(ed, 6, "n", c0["track"])
    ed.key("c")
    wait_until(ed, "window._dbgApp.nle().clips.filter(c=>c.lk==='n').length===2", label="Cで分割")
    a, b = clips(ed, "n")
    select(ed, a)
    select(ed, b, shift=True)
    t.eq(sorted(nle(ed)["sel"]), sorted([a["id"], b["id"]]), "Shift+クリックで2つ選ぶ")
    ed.key("g", ctrl=True)
    wait_until(ed, "window._dbgApp.nle().clips.filter(c=>c.lk==='n').length===1", label="Ctrl+Gで結合")
    m = _note_clip(ed)
    t.eq((m["beat"], m["len"], m["label"]), (0, 16, c0["label"]), "結合後の位置・長さ・名前（先頭のクリップの名前）")
    t.eq(m["n"], c0["n"], "中身の数は分割前と同じ")
    t.eq(nle(ed)["sel"], [m["id"]], "結合したクリップが選ばれる")
    t.eq(export_dat(ed), before, "書き出しは分割前と同じ")
    nle_mouse(ed)
    undo(ed)
    wait_until(ed, "window._dbgApp.nle().clips.filter(c=>c.lk==='n').length===2", label="結合のUndo")
    t.eq([(c["beat"], c["len"]) for c in clips(ed, "n")], [(0, 6), (6, 10)], "Undoで2つに戻る")
    t.no_errors()


def test_merge_across_lanes_and_gap(t):
    '''別レーンで時間が重なるクリップ・間が空いたクリップもCtrl+Gで1つになり、ノーツの絶対拍（書き出し）は変わらない'''
    ed = open_nle(t, "rich")
    c0 = _note_clip(ed)
    select(ed, c0)
    ed.key("c", ctrl=True)
    # 拍8へ貼り付け＝元と時間が重なるので1つ下のレーンへ、拍20へ貼り付け＝元と同じレーン（間が4拍空く）
    for at, n in ((8, 2), (20, 3)):
        ed.key("v", ctrl=True)
        wait_until(ed, "!!window._dbgApp.nle().paste", label="貼り付けの追従")
        hover(ed, at, "n", 2)
        ed.click(*clip_xy(ed, {"beat": at, "len": 0, "lk": "n", "track": 2}))
        wait_until(ed, f"window._dbgApp.nle().clips.filter(c=>c.lk==='n').length==={n}", label=f"拍{at}への貼り付け")
    cs = clips(ed, "n")
    t.eq([(c["beat"], c["track"]) for c in cs], [(0, 0), (8, 1), (20, 0)], "貼り付けた位置とレーン")
    before = export_dat(ed)
    select(ed, cs[0])
    for c in cs[1:]:
        select(ed, c, shift=True)
    ed.key("g", ctrl=True)
    wait_until(ed, "window._dbgApp.nle().clips.filter(c=>c.lk==='n').length===1", label="Ctrl+Gで結合")
    m = _note_clip(ed)
    t.eq((m["beat"], m["len"]), (0, 36), "先頭の拍から最も遠い終わり（20+16）までの1つになる")
    t.eq(m["track"], 2, "結合したクリップは空いている一番下のレーン（Notes 1）へ入る")
    t.eq(m["n"], total(cs), "中身は3つの合計")
    t.eq(export_dat(ed), before, "書き出しは結合の前と同じ（絶対拍が変わらない）")
    t.no_errors()


def test_cut_by_markers(t):
    '''Ctrl+Eで拍4と拍12にマーカー→クリップの右クリック「マーカーでカット」で3つに分かれる（中身・書き出しは同じ）→Undo1回で元に戻る'''
    ed = open_nle(t, "rich")
    before = export_dat(ed)
    c0 = _note_clip(ed)
    for b in (4, 12):
        hover(ed, b, "n", 2)   # 空いているレーンの上
        ed.key("e", ctrl=True)
        wait_until(ed, f"window._dbgApp.nle().markers.some(m=>m.beat==={b})", label=f"拍{b}にマーカー")
    t.eq([m["beat"] for m in nle(ed)["markers"]], [4, 12], "マーカーが拍順に並ぶ")
    menu(ed, *clip_xy(ed, c0, 8), "マーカーでカット")
    wait_until(ed, "window._dbgApp.nle().clips.filter(c=>c.lk==='n').length===3", label="マーカーでカット")
    cs = clips(ed, "n")
    t.eq([(c["beat"], c["len"]) for c in cs], [(0, 4), (4, 8), (12, 4)], "マーカーの拍で3つに分かれる")
    t.eq(total(cs), total([c0]), "中身の数の合計は変わらない")
    t.eq(len(clips(ed, "l")), 1, "右クリックしていないライトのクリップは切れない")
    t.eq(export_dat(ed), before, "書き出しは変わらない")
    nle_mouse(ed)
    undo(ed)
    wait_until(ed, "window._dbgApp.nle().clips.filter(c=>c.lk==='n').length===1", label="マーカーでカットのUndo（1回）")
    t.eq(len(nle(ed)["markers"]), 2, "マーカーは残る")
    t.no_errors()

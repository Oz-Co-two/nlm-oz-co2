"""NLEのクリップの編集: コピー/切り取り/貼り付け・ドラッグで移動・端のドラッグで長さ変更・空のクリップの作成・名前の変更"""
from e2e_helpers import wait_until, counts
from nle_helpers import (open_nle, clips, total, select, hover, menu, clip_xy, export_dat, nle, nle_mouse, scr, lane_y,
                         undo, redo, take_errors)


def _shift_dat(dat, d):
    """書き出しの.datの全オブジェクトの拍を d だけずらしたもの（移動後の期待値）"""
    import copy
    out = copy.deepcopy(dat)
    for k in ("colorNotes", "bombNotes", "obstacles", "basicBeatmapEvents"):
        for o in out.get(k, []):
            o["b"] = o["b"] + d
    for k in ("sliders", "burstSliders"):
        for o in out.get(k, []):
            o["b"] = o["b"] + d
            o["tb"] = o["tb"] + d
    return out


def _objs(dat):
    keys = ("colorNotes", "bombNotes", "obstacles", "sliders", "burstSliders", "basicBeatmapEvents")
    return {k: dat.get(k, []) for k in keys}


def test_copy_paste(t):
    '''Ctrl+C→Ctrl+V→マウスで拍20へ→クリックで確定: 同じ中身のクリップが拍20にでき、ノーツは拍+20で増える→Undoで消える'''
    ed = open_nle(t, "rich")
    hard0 = export_dat(ed)["HardStandard.dat"]
    c0 = clips(ed, "n")[0]
    select(ed, c0)
    ed.key("c", ctrl=True)
    wait_until(ed, "window._dbgApp.nle().clipboard===1", label="コピー")
    ed.key("v", ctrl=True)
    wait_until(ed, "!!window._dbgApp.nle().paste", label="貼り付けの追従")
    x, y = hover(ed, 20, "n", c0["track"])
    t.eq(nle(ed)["paste"]["at"], 20, "貼り付け位置がマウスの拍に追従する")
    ed.click(x, y)
    wait_until(ed, "window._dbgApp.nle().clips.filter(c=>c.lk==='n').length===2", label="貼り付けの確定")
    a, b = clips(ed, "n")
    t.eq((b["beat"], b["len"], b["track"], b["label"]), (20, 16, c0["track"], c0["label"]), "貼り付けたクリップの位置・長さ・レーン・名前")
    t.eq(b["n"], c0["n"], "中身は元と同じ")
    t.eq(nle(ed)["sel"], [b["id"]], "貼り付けたクリップが選ばれる")
    t.eq(counts(ed)["notes"], 14, "3Dのノーツが2倍になる")
    hard = export_dat(ed)["HardStandard.dat"]
    want = _shift_dat(hard0, 20)
    for k in ("colorNotes", "bombNotes", "obstacles", "sliders"):
        t.eq(hard[k], hard0[k] + want[k], f"書き出しの{k}（元＋拍を+20したもの）")
    t.eq(hard["basicBeatmapEvents"], hard0["basicBeatmapEvents"], "ライトはノーツのクリップを貼っても変わらない")
    nle_mouse(ed)
    undo(ed)
    wait_until(ed, "window._dbgApp.nle().clips.filter(c=>c.lk==='n').length===1", label="貼り付けのUndo")
    t.eq(_objs(export_dat(ed)["HardStandard.dat"]), _objs(hard0), "Undoで書き出しが元に戻る")
    t.no_errors()


def test_paste_cancel_and_cut(t):
    '''貼り付けの追従中にEscで取り消す／Ctrl+Xで切り取ると消えてクリップボードに入り、貼り付けで戻せる'''
    ed = open_nle(t, "rich")
    lc = clips(ed, "l")[0]
    select(ed, lc)
    ed.key("c", ctrl=True)
    ed.key("v", ctrl=True)
    wait_until(ed, "!!window._dbgApp.nle().paste", label="貼り付けの追従")
    hover(ed, 20, "l", 1)
    ed.key("Escape")
    wait_until(ed, "window._dbgApp.nle().paste===null", label="Escで取り消し")
    t.eq(len(clips(ed)), 2, "Escで取り消すとクリップは増えない")
    select(ed, lc)
    ed.key("x", ctrl=True)
    wait_until(ed, "window._dbgApp.nle().clips.filter(c=>c.lk==='l').length===0", label="Ctrl+Xで切り取り")
    t.eq(counts(ed)["lights"], 0, "切り取るとライトが消える")
    t.eq(nle(ed)["clipboard"], 1, "クリップボードに入る")
    ed.key("v", ctrl=True)
    wait_until(ed, "!!window._dbgApp.nle().paste", label="貼り付けの追従")
    x, y = hover(ed, 4, "l", lc["track"])
    ed.click(x, y)
    wait_until(ed, "window._dbgApp.nle().clips.filter(c=>c.lk==='l').length===1", label="貼り付けの確定")
    c = clips(ed, "l")[0]
    t.eq((c["beat"], c["n"]["lights"]), (4, 3), "拍4に同じ中身で戻る")
    t.eq([e["beat"] for e in ed.js("window._dbgApp.lights().events")], [4, 8, 12], "ライトの拍が+4される")
    t.no_errors()


def test_drag_move(t):
    '''クリップの本体をドラッグして拍8へ移動→中身も一緒に動き書き出しの拍が+8→Undo/Redo'''
    ed = open_nle(t, "rich")
    hard0 = export_dat(ed)["HardStandard.dat"]
    c0 = clips(ed, "n")[0]
    x0, y0 = clip_xy(ed, c0, 4)
    x1 = scr(ed, 12)["x"]
    ed.drag(x0, y0, x1, y0, steps=16)
    wait_until(ed, "window._dbgApp.nle().clips.find(c=>c.lk==='n').beat===8", label="ドラッグで移動")
    c1 = clips(ed, "n")[0]
    t.eq((c1["beat"], c1["len"], c1["track"], c1["n"]), (8, 16, c0["track"], c0["n"]), "移動後の位置（長さ・レーン・中身は同じ）")
    t.eq(clips(ed, "l")[0]["beat"], 0, "掴んでいないライトのクリップは動かない")
    t.eq([n["beat"] for n in ed.js("window._dbgApp.notes().notes")], [10, 11, 12, 13, 14, 16, 18], "3Dのノーツが+8拍")
    hard = export_dat(ed)["HardStandard.dat"]
    want = _shift_dat(hard0, 8)
    for k in ("colorNotes", "bombNotes", "obstacles", "sliders"):
        t.eq(hard[k], want[k], f"書き出しの{k}が+8拍")
    t.eq(hard["basicBeatmapEvents"], hard0["basicBeatmapEvents"], "ライトはそのまま")
    nle_mouse(ed)
    undo(ed)
    wait_until(ed, "window._dbgApp.nle().clips.find(c=>c.lk==='n').beat===0", label="移動のUndo")
    t.eq(_objs(export_dat(ed)["HardStandard.dat"]), _objs(hard0), "Undoで書き出しが元に戻る")
    redo(ed)
    wait_until(ed, "window._dbgApp.nle().clips.find(c=>c.lk==='n').beat===8", label="移動のRedo")
    t.no_errors()


def test_drag_lane_change(t):
    '''クリップを下のレーンへドラッグするとレーンだけ変わる（拍・中身・書き出しは同じ）。ライトのレーン・同じレーンの他のクリップに重なる所へは入らない'''
    ed = open_nle(t, "rich")
    before = export_dat(ed)
    c0 = clips(ed, "n")[0]
    x0, y0 = clip_xy(ed, c0, 4)
    ed.drag(x0, y0, x0, lane_y(ed, "n", 2), steps=10)
    wait_until(ed, "window._dbgApp.nle().clips.find(c=>c.lk==='n').track===2", label="Notes 1 へ移動")
    c1 = clips(ed, "n")[0]
    t.eq((c1["beat"], c1["n"]), (0, c0["n"]), "拍と中身は同じ")
    t.eq(export_dat(ed), before, "書き出しは変わらない")
    x0, y0 = clip_xy(ed, c1, 4)
    ed.drag(x0, y0, x0, lane_y(ed, "l", 1), steps=10)   # ライトのレーンの上で離す
    ed.wait(0.2)
    c2 = clips(ed, "n")[0]
    t.eq((c2["lk"], c2["track"], c2["beat"]), ("n", 2, 0), "ノーツのクリップはノーツのレーンに留まる")
    t.eq(len(clips(ed, "l")), 1, "ライトのクリップは増えない")
    # 同じレーンのクリップに重なる所へはドラッグしても入らない: 拍20へ貼ったコピーを拍8の方へ引く
    select(ed, c2)
    ed.key("c", ctrl=True)
    ed.key("v", ctrl=True)
    wait_until(ed, "!!window._dbgApp.nle().paste", label="貼り付けの追従")
    x, y = hover(ed, 20, "n", 2)
    ed.click(x, y)
    wait_until(ed, "window._dbgApp.nle().clips.filter(c=>c.lk==='n').length===2", label="拍20へ貼り付け")
    b = clips(ed, "n")[1]
    t.eq((b["beat"], b["track"]), (20, 2), "コピーは同じレーンの拍20")
    x0, y0 = clip_xy(ed, b, 22)
    ed.drag(x0, y0, scr(ed, 10)["x"], y0, steps=24)   # 拍8の位置へ（元のクリップ[0,16)と重なる）
    ed.wait(0.2)
    a, b2 = clips(ed, "n")
    t.eq((a["beat"], a["track"]), (0, 2), "元のクリップは動かない")
    t.eq((b2["beat"], b2["track"]), (16, 2), "重なる手前（元のクリップの終わり＝拍16）で止まる")
    t.no_errors()


def test_trim_right_edge(t):
    '''右端のクリックだけでは何も変わらない／右端を拍8までドラッグ→長さ8・拍8以降の中身は隠れて書き出されない→右端を戻すと元どおり（中身は消えない）→Undo'''
    ed = open_nle(t, "rich")
    hard0 = export_dat(ed)["HardStandard.dat"]
    c0 = clips(ed, "n")[0]
    y = lane_y(ed, "n", c0["track"])
    n0 = ed.js("window._dbgApp.state().undo")
    ed.click(scr(ed, 16)["x"] - 1, y)   # 端をクリックしただけ＝長さは変わらず履歴も積まない
    ed.wait(0.2)
    t.eq((clips(ed, "n")[0]["len"], ed.js("window._dbgApp.state().undo")), (16, n0), "端のクリックだけでは長さも履歴も変わらない")
    ed.drag(scr(ed, 16)["x"] - 1, y, scr(ed, 8)["x"], y, steps=12)
    wait_until(ed, "window._dbgApp.nle().clips.find(c=>c.lk==='n').len===8", label="右端のトリム")
    c1 = clips(ed, "n")[0]
    t.eq((c1["beat"], c1["n"]), (0, c0["n"]), "位置は同じ・中身はクリップに残る（隠れるだけ）")
    t.eq([n["beat"] for n in ed.js("window._dbgApp.notes().notes")], [2, 3, 4, 5, 6], "3Dに出るのは拍8より前のノーツだけ")
    hard = export_dat(ed)["HardStandard.dat"]
    t.eq(hard["colorNotes"], [n for n in hard0["colorNotes"] if n["b"] < 8], "書き出しは拍8より前のノーツだけ")
    t.eq(hard["basicBeatmapEvents"], hard0["basicBeatmapEvents"], "ライトのクリップは変わらない")
    ed.drag(scr(ed, 8)["x"] - 1, y, scr(ed, 16)["x"], y, steps=12)   # 右端を拍16へ戻す
    wait_until(ed, "window._dbgApp.nle().clips.find(c=>c.lk==='n').len===16", label="右端を戻す")
    t.eq(_objs(export_dat(ed)["HardStandard.dat"]), _objs(hard0), "隠れていた中身が戻る（書き出しが元どおり）")
    nle_mouse(ed)
    undo(ed)
    wait_until(ed, "window._dbgApp.nle().clips.find(c=>c.lk==='n').len===8", label="戻したトリムのUndo")
    undo(ed)
    wait_until(ed, "window._dbgApp.nle().clips.find(c=>c.lk==='n').len===16", label="最初のトリムのUndo")
    t.no_errors()


def test_trim_left_edge(t):
    '''左端を拍4までドラッグ→開始4・長さ12・中身の絶対拍は動かず拍4より前は隠れる→Undo'''
    ed = open_nle(t, "rich")
    hard0 = export_dat(ed)["HardStandard.dat"]
    c0 = clips(ed, "n")[0]
    y = lane_y(ed, "n", c0["track"])
    ed.drag(scr(ed, 0)["x"] + 1, y, scr(ed, 4)["x"], y, steps=12)
    wait_until(ed, "window._dbgApp.nle().clips.find(c=>c.lk==='n').beat===4", label="左端のトリム")
    c1 = clips(ed, "n")[0]
    t.eq((c1["beat"], c1["len"], c1["n"]), (4, 12, c0["n"]), "開始・長さが変わり中身はクリップに残る")
    t.eq([n["beat"] for n in ed.js("window._dbgApp.notes().notes")], [4, 5, 6, 8, 10], "残ったノーツの絶対拍は変わらない")
    hard = export_dat(ed)["HardStandard.dat"]
    t.eq(hard["colorNotes"], [n for n in hard0["colorNotes"] if n["b"] >= 4], "書き出しは拍4以降のノーツだけ（拍はそのまま）")
    nle_mouse(ed)
    undo(ed)
    wait_until(ed, "window._dbgApp.nle().clips.find(c=>c.lk==='n').beat===0", label="左端トリムのUndo")
    t.eq(_objs(export_dat(ed)["HardStandard.dat"]), _objs(hard0), "Undoで書き出しが元に戻る")
    t.no_errors()


def test_create_empty_clip(t):
    '''空いている所を右クリック「空のクリップを作成」→その拍・レーンに16拍の空クリップ→Undo。重なる所では作らない'''
    ed = open_nle(t, "rich")
    x, y = scr(ed, 20)["x"], lane_y(ed, "n", 1)
    menu(ed, x, y, "空のクリップを作成")
    wait_until(ed, "window._dbgApp.nle().clips.filter(c=>c.lk==='n').length===2", label="空のクリップの作成")
    c = clips(ed, "n")[1]
    t.eq((c["beat"], c["len"], c["track"], c["label"]), (20, 16, 1, "Sheet"), "作ったクリップの位置・長さ・レーン・名前")
    t.eq(total([c]), {k: 0 for k in total([c])}, "中身は空")
    t.eq(nle(ed)["sel"], [c["id"]], "作ったクリップが選ばれる")
    # 同じレーンの拍8から16拍＝拍20のクリップと重なる位置には作らない
    menu(ed, scr(ed, 8)["x"], y, "空のクリップを作成")
    ed.wait(0.2)
    t.eq(len(clips(ed, "n")), 2, "重なる位置には作らない")
    t.eq(take_errors(ed, "重なります"), 1, "重なる旨のエラーが出る")
    nle_mouse(ed)
    undo(ed)
    wait_until(ed, "window._dbgApp.nle().clips.filter(c=>c.lk==='n').length===1", label="作成のUndo")
    t.no_errors()


def test_rename_dblclick(t):
    '''クリップの上端（名前の帯）をダブルクリック→名前を入力してEnter→名前が変わる→Undoで戻る'''
    ed = open_nle(t, "rich")
    c0 = clips(ed, "n")[0]
    x, y = clip_xy(ed, c0, 8, frac=0.25)   # 上端16pxの名前の帯
    ed.click(x, y)
    ed.click(x, y, count=2)
    wait_until(ed, "document.activeElement&&document.activeElement.tagName==='INPUT'", label="名前の入力欄")
    ed.key("a", ctrl=True)
    ed.call("Input.insertText", text="サビ1")
    ed.key("Enter")
    wait_until(ed, "window._dbgApp.nle().clips.find(c=>c.lk==='n').label==='サビ1'", label="名前の変更")
    t.eq(clips(ed, "l")[0]["label"], c0["label"], "他のクリップの名前は変わらない")
    nle_mouse(ed)
    undo(ed)
    wait_until(ed, f"window._dbgApp.nle().clips.find(c=>c.lk==='n').label==={c0['label']!r}", label="名前変更のUndo")
    t.no_errors()


def test_delete_x_key(t):
    '''Xで選んだクリップを消す（中身ごと書き出しからも消える）→Undoで戻る'''
    ed = open_nle(t, "rich")
    before = export_dat(ed)
    lc = clips(ed, "l")[0]
    select(ed, lc)
    ed.key("x")
    wait_until(ed, "window._dbgApp.nle().clips.filter(c=>c.lk==='l').length===0", label="Xで削除")
    t.eq(export_dat(ed)["HardStandard.dat"]["basicBeatmapEvents"], [], "Hardのライトが書き出されない")
    t.eq(export_dat(ed)["ExpertStandard.dat"], before["ExpertStandard.dat"], "他の難易度は変わらない")
    nle_mouse(ed)
    undo(ed)
    wait_until(ed, "window._dbgApp.nle().clips.filter(c=>c.lk==='l').length===1", label="削除のUndo")
    t.eq(export_dat(ed), before, "Undoで書き出しが元に戻る")
    t.no_errors()


def test_rename_from_menu_light_clip(t):
    '''ライトのクリップの右クリック「ラベルを変更…」→入力欄がそのクリップの上に出る→名前を入れてEnterで変わる'''
    ed = open_nle(t, "rich")
    lc = clips(ed, "l")[0]
    menu(ed, *clip_xy(ed, lc, 8), "ラベルを変更")
    wait_until(ed, "document.activeElement&&document.activeElement.tagName==='INPUT'", label="名前の入力欄")
    r = ed.js("(r=>({top:r.top,bottom:r.bottom}))(document.activeElement.getBoundingClientRect())")
    top = scr(ed)["lights"][lc["track"]]
    on_clip = top - 2 <= r["top"] <= top + scr(ed)["laneH"]
    ed.key("a", ctrl=True)
    ed.call("Input.insertText", text="ライト1")
    ed.key("Enter")
    wait_until(ed, "window._dbgApp.nle().clips.find(c=>c.lk==='l').label==='ライト1'", label="名前の変更")
    t.eq(clips(ed, "n")[0]["label"], lc["label"], "ノーツのクリップの名前は変わらない")
    t.ok(on_clip, f"入力欄がライトのクリップのレーンに出る（入力欄の上端y={r['top']:.0f}、レーンの上端y={top:.0f}）")
    t.no_errors()

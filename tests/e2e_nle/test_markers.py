"""NLEのマーカー: 追加（Ctrl+E）・前後のマーカーへジャンプ（Ctrl+[ / Ctrl+]）・ドラッグで移動・名前の変更・削除"""
from e2e_helpers import wait_until
from nle_helpers import open_nle, hover, menu, nle, nle_mouse, scr, undo, redo


def _add_markers(ed, beats, lane_track=1):
    for b in beats:
        hover(ed, b, "n", lane_track)
        ed.key("e", ctrl=True)
        wait_until(ed, f"window._dbgApp.nle().markers.some(m=>m.beat==={b})", label=f"拍{b}にマーカー")


def _mk_y(ed):
    s = scr(ed)
    return (s["marker"] + s["lanes"]) / 2   # マーカーの帯（数字の目盛りとレーンの間）


def test_marker_add_ctrl_e(t):
    '''Ctrl+Eでマウスの拍にマーカーを追加（拍順に並ぶ・同じ拍には重ねない）→Undo/Redo／右クリック「マーカーを作成」は再生位置に作る'''
    ed = open_nle(t, "basic")
    _add_markers(ed, [12, 4])
    mk = nle(ed)["markers"]
    t.eq([m["beat"] for m in mk], [4, 12], "マーカーは拍順に並ぶ")
    t.ok(all(m["name"] for m in mk), f"名前が付く: {mk}")
    hover(ed, 4, "n", 1)
    ed.key("e", ctrl=True)
    ed.wait(0.2)
    t.eq(len(nle(ed)["markers"]), 2, "同じ拍には追加しない")
    nle_mouse(ed)
    undo(ed)
    wait_until(ed, "window._dbgApp.nle().markers.length===1", label="追加のUndo")
    t.eq([m["beat"] for m in nle(ed)["markers"]], [12], "最後に追加した拍4のマーカーが消える")
    redo(ed)
    wait_until(ed, "window._dbgApp.nle().markers.length===2", label="追加のRedo")
    # 空いている所の右クリック「マーカーを作成」は、右クリックした拍ではなく再生位置（再生ヘッド）に作る
    s = scr(ed, 6)
    ed.click(s["x"], (s["ruler"] + s["tempo"]) / 2)   # 数字の目盛りをクリック＝再生位置を拍6へ
    wait_until(ed, "window._dbgApp.state().cur===6", label="目盛りのクリックで再生位置を移動")
    menu(ed, scr(ed, 20)["x"], s["notes"][0] + s["laneH"] * 0.6, "マーカーを作成")
    wait_until(ed, "window._dbgApp.nle().markers.length===3", label="右クリックでマーカーの作成")
    t.eq([m["beat"] for m in nle(ed)["markers"]], [4, 6, 12], "再生位置（拍6）に作る")
    t.no_errors()


def test_marker_jump(t):
    '''Ctrl+]で次のマーカー、Ctrl+[で前のマーカーへ再生位置が移る（先頭より前は拍0）'''
    ed = open_nle(t, "basic")
    _add_markers(ed, [4, 12])
    nle_mouse(ed)
    for want in (4, 12):
        ed.key("]", ctrl=True)
        wait_until(ed, f"Math.abs(window._dbgApp.state().cur-{want})<1e-6", label=f"次のマーカー（拍{want}）へ")
    ed.key("]", ctrl=True)
    ed.wait(0.3)
    t.eq(ed.js("window._dbgApp.state().cur"), 12, "最後のマーカーより先へは動かない")
    for want in (4, 0):
        ed.key("[", ctrl=True)
        wait_until(ed, f"Math.abs(window._dbgApp.state().cur-{want})<1e-6", label=f"前のマーカー（拍{want}）へ")
    t.eq(len(nle(ed)["markers"]), 2, "ジャンプでマーカーは変わらない")
    t.no_errors()


def test_marker_drag_move(t):
    '''マーカーの帯でマーカーを拍4→拍10へドラッグ→拍10に移り拍順に並び直す→Undoで拍4へ戻る'''
    ed = open_nle(t, "basic")
    _add_markers(ed, [4, 8])
    y = _mk_y(ed)
    ed.drag(scr(ed, 4)["x"], y, scr(ed, 10)["x"], y, steps=12)
    wait_until(ed, "window._dbgApp.nle().markers.some(m=>m.beat===10)", label="マーカーの移動")
    mk = nle(ed)["markers"]
    t.eq([m["beat"] for m in mk], [8, 10], "移動後は拍順に並び直す")
    t.eq(ed.js("window._dbgApp.state().cur"), 0, "マーカーの帯のクリック・ドラッグでは再生位置は動かない")
    nle_mouse(ed)
    undo(ed)
    ed.wait(0.3)
    beats = [m["beat"] for m in nle(ed)["markers"]]
    t.eq(beats, [4, 8], "Undoで元の拍へ戻る")
    t.no_errors()


def test_marker_rename_and_delete(t):
    '''マーカーの名前をダブルクリックで変更・空にすると削除／右クリック「マーカーを削除」→Undoで戻る'''
    ed = open_nle(t, "basic")
    _add_markers(ed, [4, 12])
    y = _mk_y(ed)
    x = scr(ed, 4)["x"] + 14   # ラベルはマーカーの線の右
    ed.click(x, y)
    ed.click(x, y, count=2)
    wait_until(ed, "document.activeElement&&document.activeElement.tagName==='INPUT'", label="名前の入力欄")
    ed.key("a", ctrl=True)
    ed.call("Input.insertText", text="サビ")
    ed.key("Enter")
    wait_until(ed, "window._dbgApp.nle().markers[0].name==='サビ'", label="名前の変更")
    ed.click(x, y)
    ed.click(x, y, count=2)
    wait_until(ed, "document.activeElement&&document.activeElement.tagName==='INPUT'", label="名前の入力欄（2回目）")
    ed.key("a", ctrl=True)
    ed.key("Delete")
    ed.key("Enter")
    wait_until(ed, "window._dbgApp.nle().markers.length===1", label="空にして削除")
    t.eq(nle(ed)["markers"][0]["beat"], 12, "拍12のマーカーが残る")
    menu(ed, scr(ed, 12)["x"] + 2, y, "マーカーを削除")
    wait_until(ed, "window._dbgApp.nle().markers.length===0", label="右クリックで削除")
    nle_mouse(ed)
    undo(ed)
    wait_until(ed, "window._dbgApp.nle().markers.length===1", label="削除のUndo")
    t.eq(nle(ed)["markers"][0]["beat"], 12, "Undoで拍12のマーカーが戻る")
    t.no_errors()

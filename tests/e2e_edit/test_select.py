"""3Dビュー（NOTES）の選択: 範囲選択・Shiftでの追加/解除・Aでの選択解除"""
from e2e_helpers import counts, state, wait_until
from edit_helpers import (open_ed, objs_on_screen, find_obj, click_obj, sel_keys, to_edit_cam, drag_box, bbox_of, undo, redo)

BEAT3 = sorted([(3, 0, 1), (3, 3, 1), (3, 1, 0), (3, 2, 0), (3, 1, 2), (3, 2, 2)])   # basic の拍3のノーツ6個（拍, x, y）


def test_box_select(t):
    '''カメラ固定モードで空き地から左ドラッグ＝枠内のノーツだけが選ばれ（前の選択は置き換え）、選択もUndo/Redoで戻り、空き地のクリックで外れる'''
    ed = open_ed(t)
    to_edit_cam(ed)
    click_obj(ed, beat=1, x=1, y=0)
    wait_until(ed, "window._dbgApp.state().sel===1", label='クリックで1個選択')
    pts = [o for o in objs_on_screen(ed) if o['beat'] == 3]
    others = [o for o in objs_on_screen(ed) if o['beat'] != 3]
    t.eq(len(pts), 6, '拍3のノーツが画面に6個')
    x0, y0, x1, y1 = bbox_of(pts)
    t.ok(all(not (x0 <= o['sx'] <= x1 and y0 <= o['sy'] <= y1) for o in others), '枠に拍3以外のノーツが入らない（素材・カメラの前提）')
    drag_box(ed, x0, y0, x1, y1)
    wait_until(ed, "window._dbgApp.state().sel===6", label='範囲選択で6個')
    t.eq(sel_keys(ed), BEAT3, '選ばれたのは拍3の6個（拍1の選択は置き換え）')
    t.eq(counts(ed)['notes'], 8, '範囲選択でノーツは増えない（配置されない）')
    undo(ed)
    wait_until(ed, "window._dbgApp.state().sel===1", label='範囲選択のUndo（前の選択へ）')
    t.eq(sel_keys(ed), [(1, 1, 0)], 'Undo後の選択')
    redo(ed)
    wait_until(ed, "window._dbgApp.state().sel===6", label='範囲選択のRedo')
    t.eq(sel_keys(ed), BEAT3, 'Redo後の選択')
    ed.click(x1 + 40, y0 - 40)   # 何も無い所のクリック（ドラッグしない）
    wait_until(ed, "window._dbgApp.state().sel===0", label='空き地のクリックで選択解除')
    t.eq(counts(ed)['notes'], 8, 'カメラ固定モードのマス外クリックでノーツは置かれない')
    t.no_errors()


def test_shift_add_toggle_deselect(t):
    '''配置モードでノーツをクリック→Shift+クリックで追加・もう一度で解除→Shift+ドラッグで追加→Aで全解除（どれもノーツは置かれない）'''
    ed = open_ed(t)
    click_obj(ed, beat=3, x=1, y=0)
    wait_until(ed, "window._dbgApp.state().sel===1", label='クリックで選択')
    t.eq(sel_keys(ed), [(3, 1, 0)], 'クリックしたノーツが選ばれる')
    click_obj(ed, shift=True, beat=2, x=2, y=0)
    wait_until(ed, "window._dbgApp.state().sel===2", label='Shift+クリックで追加')
    t.eq(sel_keys(ed), [(2, 2, 0), (3, 1, 0)], '追加後の選択')
    click_obj(ed, shift=True, beat=2, x=2, y=0)
    wait_until(ed, "window._dbgApp.state().sel===1", label='もう一度Shift+クリックで解除')
    t.eq(sel_keys(ed), [(3, 1, 0)], '解除後の選択')
    # Shift+ドラッグ＝追加の範囲選択（配置モードでもShift付きは配置にならない）。拍1のノーツ（離れた所にある）を囲む
    x0, y0, x1, y1 = bbox_of([find_obj(ed, beat=1, x=1, y=0)], pad=45)
    t.ok(all(not (x0 <= o['sx'] <= x1 and y0 <= o['sy'] <= y1) for o in objs_on_screen(ed) if o['beat'] != 1), '枠には拍1のノーツだけ（カメラの前提）')
    drag_box(ed, x0, y1, x1, y0, shift=True)
    wait_until(ed, "window._dbgApp.state().sel===2", label='Shift+ドラッグで追加')
    t.eq(sel_keys(ed), [(1, 1, 0), (3, 1, 0)], '元の選択は残り、枠内が足される')
    t.eq(counts(ed)['notes'], 8, 'Shift付きの操作でノーツは置かれない')
    ed.key('a')
    wait_until(ed, "window._dbgApp.state().sel===0", label='Aで選択解除')
    t.eq(counts(ed)['notes'], 8, '選択解除でノーツ数は変わらない')
    t.no_errors()

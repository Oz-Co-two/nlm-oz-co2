"""3Dビュー（NOTES）のギズモ（移動のつまみ）: 配置済みをクリックで選ぶと矢印のつまみが出て、引いた向きへマス単位で動く"""
from e2e_helpers import counts, state, wait_until, cell, place_at
from edit_helpers import (open_ed, notes, note_keys, click_obj, edit, undo, redo, drag_handle, hover_off_grid, frames)


def _delta(ed, a, b):
    """マス a→b の画面上の移動量（拍0＝配置グリッドの深さ）"""
    pa, pb = cell(ed, *a), cell(ed, *b)
    return pb['x'] - pa['x'], pb['y'] - pa['y']


def _drag_by(ed, axis, sign, d):
    frames(ed)
    g = ed.js("window._dbgApp.gizmoScreen()")
    h = [h for h in g['handles'] if h['axis'] == axis and h['sign'] == sign][0]
    drag_handle(ed, axis, sign, to={'x': h['x'] + d[0], 'y': h['y'] + d[1]})


def test_gizmo_move_note(t):
    '''拍0に置いたノーツをクリックで選ぶ→横のつまみを1マス分引くと1列、縦のつまみで1段動く→Undoで1つずつ戻る→大きく引いても盤の端で止まる'''
    ed = open_ed(t)
    place_at(ed, 1, 1)   # 再生ヘッド（拍0）＝配置グリッドと同じ深さ＝マスの間隔がそのままつまみの1段
    hover_off_grid(ed)
    t.eq(edit(ed)['gizmo'], None, '置いた直後はつまみを出さない（連続配置の邪魔をしない）')
    click_obj(ed, beat=0, x=1, y=1)
    wait_until(ed, "window._dbgApp.edit().gizmo==='move'&&window._dbgApp.gizmoScreen().handles.length>0", label='選択で移動のつまみ')
    hs = ed.js("window._dbgApp.gizmoScreen()")['handles']
    t.ok(all(not h['size'] for h in hs), '移動のつまみ（円錐）')
    t.eq(sorted({h['axis'] for h in hs}), ['x', 'y', 'z'], '列・段・拍の3方向のつまみ')
    # x の sign=+1 ＝列番号が増える向き
    _drag_by(ed, 'x', 1, _delta(ed, (1, 1), (2, 1)))
    wait_until(ed, "window._dbgApp.notes().notes.some(n=>n.beat===0&&n.x===2&&n.y===1)", label='1列移動')
    _drag_by(ed, 'y', 1, _delta(ed, (2, 1), (2, 2)))
    wait_until(ed, "window._dbgApp.notes().notes.some(n=>n.beat===0&&n.x===2&&n.y===2)", label='1段移動')
    t.eq(sorted(k[1:3] for k in note_keys(ed) if k[0] == 0), [(2, 2)], '拍0のノーツは1個のまま (2,2) へ')
    t.eq(counts(ed)['notes'], 9, '移動で数は変わらない')
    undo(ed)
    wait_until(ed, "window._dbgApp.notes().notes.some(n=>n.beat===0&&n.x===2&&n.y===1)", label='段の移動のUndo')
    undo(ed)
    wait_until(ed, "window._dbgApp.notes().notes.some(n=>n.beat===0&&n.x===1&&n.y===1)", label='列の移動のUndo')
    # 盤の端（4列目＝x 3）を越える量を引いても端で止まる
    dx, dy = _delta(ed, (0, 1), (3, 1))   # 3列分（1列目から引くと盤の外まで）
    _drag_by(ed, 'x', 1, (dx * 1.5, dy * 1.5))
    wait_until(ed, "window._dbgApp.notes().notes.some(n=>n.beat===0&&n.x===3&&n.y===1)", label='端（3）で止まる')
    t.eq(sorted(k[1:3] for k in note_keys(ed) if k[0] == 0), [(3, 1)], '盤の外へは出ない')
    t.no_errors()

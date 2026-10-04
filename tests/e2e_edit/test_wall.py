"""3Dビュー（NOTES）の壁: Wパイで壁を選び、段階式（クリック→横幅→高さ→奥行き）で置く／Esc・右クリックで中止／S＝サイズのつまみ"""
from e2e_helpers import counts, state, wait_until, cell
from edit_helpers import (open_ed, mv, objs, edit, undo, redo, pie_pick, hover_off_grid, drag_handle)


def _wall(ed):
    ws = objs(ed)['walls']
    assert len(ws) == 1, ws
    w = ws[0]
    return {k: w[k] for k in ('beat', 'x', 'y', 'w', 'h', 'dur')}


def _click_cell(ed, x, y):
    p = cell(ed, x, y)
    mv(ed, p['x'], p['y'])
    ed.click(p['x'], p['y'])


def _move_cell(ed, x, y):
    p = cell(ed, x, y)
    mv(ed, p['x'], p['y'])


def _to_wall_brush(ed):
    hover_off_grid(ed)
    pie_pick(ed, 'w', 240)   # 配置パイ: 上=ノーツ・右下=ボム・左下(240°)=壁
    wait_until(ed, "window._dbgApp.state().brush.type==='wall'", label='Wパイで壁')


def _place_wall(ed):
    """マス(1,0)から 横幅→(2,0)=2列・高さ→(2,1)=2段・奥行き→床の拍2 で壁を置く"""
    _to_wall_brush(ed)
    _click_cell(ed, 1, 0)
    wait_until(ed, "window._dbgApp.edit().wallStage==='width'", label='仮配置→横幅の調整')
    _move_cell(ed, 2, 0)
    wait_until(ed, "window._dbgApp.objs().walls[0]?.w===2", label='横幅が2列に')
    _click_cell(ed, 2, 0)
    wait_until(ed, "window._dbgApp.edit().wallStage==='height'", label='高さの調整へ')
    _move_cell(ed, 2, 1)
    wait_until(ed, "window._dbgApp.objs().walls[0]?.h===2", label='高さが2段に')
    _click_cell(ed, 2, 1)
    wait_until(ed, "window._dbgApp.edit().wallStage==='depth'", label='奥行きの調整へ')
    p = ed.js("window._dbgApp.lightLaneScreen(0,2)")   # 床の上の拍2の位置（奥行きは床の拍で決まる）
    mv(ed, p['x'], p['y'])
    wait_until(ed, "window._dbgApp.objs().walls[0]?.dur===2", label='奥行きが2拍に')
    ed.click(p['x'], p['y'])
    wait_until(ed, "window._dbgApp.edit().wallStage===null", label='壁の確定')


def test_wall_staged_place(t):
    '''Wパイで壁→マスをクリックで最小の壁を仮置き→横幅・高さ・奥行きをマウスで決めて各クリックで確定→Undoで消える'''
    ed = open_ed(t)
    _to_wall_brush(ed)
    _click_cell(ed, 1, 0)
    wait_until(ed, "window._dbgApp.edit().wallStage==='width'", label='仮配置')
    w0 = _wall(ed)
    t.eq({k: w0[k] for k in ('beat', 'x', 'y', 'w', 'h')}, {'beat': 0, 'x': 1, 'y': 0, 'w': 1, 'h': 1}, '仮置きは押したマスの1マス・再生ヘッドの拍')
    t.ok(0 < w0['dur'] < 0.5, f'仮置きの奥行きは1ボックス分（0.5拍未満）: {w0["dur"]}')
    ed.key('Escape')   # 途中の段階で消せることも確かめてから、改めて置く
    wait_until(ed, "window._dbgApp.state().counts.walls===0", label='Escで中止')
    _place_wall(ed)
    t.eq(_wall(ed), {'beat': 0, 'x': 1, 'y': 0, 'w': 2, 'h': 2, 'dur': 2}, '確定した壁（列1〜2・段0〜1・拍0から2拍）')
    t.eq(state(ed)['sel'], 1, '確定した壁が選択される')
    t.eq(counts(ed)['notes'], 8, 'ノーツは増えない')
    # 選択の変化も1操作として履歴に積む仕様＝1回目のUndoは「確定時の選択」を戻し、2回目で壁が消える
    undo(ed)
    wait_until(ed, "window._dbgApp.state().sel===0", label='確定時の選択のUndo')
    undo(ed)
    wait_until(ed, "window._dbgApp.state().counts.walls===0", label='壁の配置のUndo')
    redo(ed); redo(ed)
    wait_until(ed, "window._dbgApp.state().counts.walls===1", label='壁の配置のRedo')
    t.eq(_wall(ed), {'beat': 0, 'x': 1, 'y': 0, 'w': 2, 'h': 2, 'dur': 2}, 'Redo後の壁')
    t.no_errors()


def test_wall_stage_cancel(t):
    '''壁の調整中のEsc・右クリックは仮置きの壁を消し、履歴も残さない（壁を選んでいない時のSはサイズモードにならない）'''
    ed = open_ed(t)
    hover_off_grid(ed)
    ed.key('s'); ed.wait(0.2)
    t.eq(edit(ed)['gizmo'], None, '壁の選択なしのS＝サイズモードにならない')
    _to_wall_brush(ed)
    u0 = state(ed)['undo']
    _click_cell(ed, 0, 0)
    wait_until(ed, "window._dbgApp.edit().wallStage==='width'", label='仮配置')
    _click_cell(ed, 0, 0)
    wait_until(ed, "window._dbgApp.edit().wallStage==='height'", label='高さの段階')
    ed.key('Escape')
    wait_until(ed, "window._dbgApp.state().counts.walls===0", label='Escで中止')
    t.eq(edit(ed)['wallStage'], None, 'Esc後は調整中でない')
    t.eq(state(ed)['undo'], u0, 'Escの中止は履歴を残さない')
    _click_cell(ed, 3, 2)
    wait_until(ed, "window._dbgApp.edit().wallStage==='width'", label='もう一度仮配置')
    p = cell(ed, 3, 2)
    ed.click(p['x'], p['y'], button='right')
    wait_until(ed, "window._dbgApp.state().counts.walls===0", label='右クリックで中止')
    t.eq(state(ed)['undo'], u0, '右クリックの中止も履歴を残さない')
    t.eq(counts(ed)['notes'], 8, '右クリックで他のノーツは消えない')
    t.no_errors()


def test_wall_size_handles(t):
    '''壁を選んでS＝サイズのつまみ（四角）に替わり、横のつまみを外へ引くと幅が盤の端（4列目）まで広がる・Undoで戻る・もう一度Sで解除'''
    ed = open_ed(t)
    _place_wall(ed)   # 確定した壁は選択中
    hover_off_grid(ed)
    ed.key('s')
    wait_until(ed, "window._dbgApp.edit().gizmo==='size'", label='Sでサイズモード')
    wait_until(ed, "window._dbgApp.gizmoScreen().handles.some(h=>h.size)", label='つまみの表示（描画の次のフレームで出る）')
    g = ed.js("window._dbgApp.gizmoScreen()")
    t.ok(g['visible'] and g['handles'] and all(h['size'] for h in g['handles']), f'つまみはすべてサイズ用（四角）: {g}')
    # x の sign=+1 側＝幅を増やす向き（レーン軸は画面上で反転しているため、つまみの向き(dir)は -x）
    drag_handle(ed, 'x', 1, dist_px=400)
    wait_until(ed, "window._dbgApp.objs().walls[0].w===3", label='幅が3列に（列1から盤の端まで）')
    t.eq(_wall(ed), {'beat': 0, 'x': 1, 'y': 0, 'w': 3, 'h': 2, 'dur': 2}, '広げた後の壁（位置・高さ・奥行きは変わらない）')
    undo(ed)
    wait_until(ed, "window._dbgApp.objs().walls[0].w===2", label='サイズ変更のUndo')
    hover_off_grid(ed)
    ed.key('s')
    wait_until(ed, "window._dbgApp.edit().gizmo===null", label='もう一度Sで解除')
    t.no_errors()

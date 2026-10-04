"""3Dビュー（LIGHTING）の編集。Tabで切替え、カメラ固定モード（俯瞰＝拍をマウスで選べる）で操作する。
ライトの値 i は「色の基準(赤=4・青=0・白=8)＋動作(オフ=0/ライト=1/フラッシュ=2/フェード=3/トランジション=4)」（Beat Saber のイベント値）"""
from e2e_helpers import counts, state, wait_until
from edit_helpers import (open_ed, mv, lights, light_at, light_lane, place_light, edit, undo, redo, wheel, pie_pick,
                          to_edit_cam, to_light_mode, drag_box, drag_handle, hover_off_grid)

L_LASER, RINGS, BACK = 6, 7, 8   # レーン番号（0=左端）。種別はそれぞれ 2 / 1 / 0


def _open(t):
    ed = open_ed(t)
    to_edit_cam(ed)
    to_light_mode(ed)
    return ed


def _ev(e):
    return {k: e[k] for k in ('beat', 'et', 'i', 'f')}


def _select_light(ed, li, beat):
    p = light_lane(ed, li, beat)
    mv(ed, p['x'], p['y'])
    ed.click(p['x'], p['y'])
    wait_until(ed, "window._dbgApp.edit().lightSel.length===1", label=f'ライト選択 レーン{li} 拍{beat}')
    return p


def _copy_paste_at(ed, li, src_beat, dst_beat):
    """（選択中の）ライトをコピーし、レーン li の拍 dst_beat にマウスを置いて貼り付ける。マウスの位置を返す"""
    ed.key('c', ctrl=True)
    p = light_lane(ed, li, dst_beat)
    mv(ed, p['x'], p['y'])
    n0 = counts(ed)['lights']
    ed.key('v', ctrl=True)
    wait_until(ed, f"window._dbgApp.state().counts.lights==={n0 + 1}", label='貼り付け')
    return p


def test_light_place_delete(t):
    '''Tabで LIGHTING→レーンをクリックで既定のブラシ（赤・ライト）のライトが置かれ、右クリックで消え、Undo/Redoで戻る→Tabで NOTES に戻る'''
    ed = _open(t)
    t.eq(state(ed)['lightMode'], True, 'LIGHTING モード')
    place_light(ed, L_LASER, 1)
    place_light(ed, BACK, 2)
    t.eq(_ev(light_at(ed, L_LASER, 1)), {'beat': 1, 'et': 2, 'i': 5, 'f': 1}, 'L LASER 拍1（赤のライト＝4+1）')
    t.eq(_ev(light_at(ed, BACK, 2)), {'beat': 2, 'et': 0, 'i': 5, 'f': 1}, 'BACK 拍2')
    t.eq(counts(ed)['notes'], 8, 'LIGHTING のクリックでノーツは置かれない')
    p = light_lane(ed, L_LASER, 1)
    mv(ed, p['x'], p['y'])
    ed.click(p['x'], p['y'], button='right')
    wait_until(ed, "window._dbgApp.state().counts.lights===1", label='右クリックで削除')
    t.eq(light_at(ed, L_LASER, 1), None, '消したのは L LASER 拍1')
    t.ok(light_at(ed, BACK, 2) is not None, 'BACK 拍2 は残る')
    undo(ed)
    wait_until(ed, "window._dbgApp.state().counts.lights===2", label='削除のUndo')
    t.eq(_ev(light_at(ed, L_LASER, 1)), {'beat': 1, 'et': 2, 'i': 5, 'f': 1}, 'Undoで戻ったライト')
    redo(ed)
    wait_until(ed, "window._dbgApp.state().counts.lights===1", label='削除のRedo')
    hover_off_grid(ed)
    ed.key('Tab')
    wait_until(ed, "window._dbgApp.state().lightMode===false", label='Tabで NOTES へ戻る')
    t.eq(counts(ed), {'notes': 8, 'bombs': 0, 'walls': 0, 'arcs': 0, 'chains': 0, 'lights': 1}, '切替で中身は変わらない')
    t.no_errors()


def test_light_pie_behavior(t):
    '''Wのパイで動作を選ぶ（フラッシュ＝右下144°・オフ＝上）と、その動作のライトが置かれる'''
    ed = _open(t)
    hover_off_grid(ed)
    pie_pick(ed, 'w', 144)
    wait_until(ed, "window._dbgApp.edit().lightBrush.behav===2", label='フラッシュ')
    place_light(ed, BACK, 1)
    t.eq(light_at(ed, BACK, 1)['i'], 6, 'フラッシュ（赤）＝4+2')
    hover_off_grid(ed)
    pie_pick(ed, 'w', 0)
    wait_until(ed, "window._dbgApp.edit().lightBrush.behav===0", label='オフ')
    place_light(ed, BACK, 2)
    t.eq(light_at(ed, BACK, 2)['i'], 0, 'オフ＝0')
    t.no_errors()


def test_light_color_intensity(t):
    '''選んだライトにF＝色が 青→白→赤 と巡り（動作は保つ）、Alt+ホイール＝強さ±0.1・Ctrl+Alt+ホイール＝±0.01。Undoで戻る'''
    ed = _open(t)
    place_light(ed, BACK, 1)
    _select_light(ed, BACK, 1)
    seq = []
    for _ in range(3):
        n0 = state(ed)['undo']
        ed.key('f')
        wait_until(ed, f"window._dbgApp.state().undo==={n0 + 1}", label='Fで色の巡回')
        seq.append((edit(ed)['lightBrush']['base'], light_at(ed, BACK, 1)['i']))
    t.eq(seq, [(0, 1), (8, 9), (4, 5)], '（ブラシの色の基準, ライトの値）: 青のライト→白のライト→赤のライト')
    undo(ed)
    wait_until(ed, "window._dbgApp.lights().events[0].i===9", label='FのUndo（白へ戻る）')
    p = hover_off_grid(ed)
    wheel(ed, p['x'], p['y'], -100, alt=True)
    wait_until(ed, "Math.abs(window._dbgApp.lights().events[0].f-1.1)<1e-9", label='強さ +0.1')
    ed.wait(0.6)   # 0.5秒以内の連続操作は1回の履歴にまとめる仕様＝間を空けて別の操作にする
    wheel(ed, p['x'], p['y'], 100, alt=True, ctrl=True)
    wait_until(ed, "Math.abs(window._dbgApp.lights().events[0].f-1.09)<1e-9", label='強さ -0.01')
    t.eq(light_at(ed, BACK, 1)['i'], 9, '強さを変えても色・動作は変わらない')
    undo(ed)
    wait_until(ed, "Math.abs(window._dbgApp.lights().events[0].f-1.1)<1e-9", label='-0.01 のUndo')
    undo(ed)
    wait_until(ed, "window._dbgApp.lights().events[0].f===1", label='+0.1 のUndo')
    t.no_errors()


def test_light_move_gizmo(t):
    '''ライトをクリックで選ぶと拍方向だけのつまみが出て、1拍分引くと1拍後ろへ動く（レーン＝種別は変わらない）・Undoで戻る'''
    ed = _open(t)
    place_light(ed, RINGS, 1)
    _select_light(ed, RINGS, 1)
    wait_until(ed, "window._dbgApp.edit().gizmo==='move'&&window._dbgApp.gizmoScreen().handles.length>0", label='移動のつまみ')
    t.eq(sorted({h['axis'] for h in ed.js("window._dbgApp.gizmoScreen()")['handles']}), ['z'], 'つまみは拍の向きだけ（レーンを跨ぐと種別が変わるため）')
    a, b = ed.js(f"window._dbgApp.lightLaneScreen({RINGS},1)"), ed.js(f"window._dbgApp.lightLaneScreen({RINGS},2)")
    h = [h for h in ed.js("window._dbgApp.gizmoScreen()")['handles'] if h['sign'] == 1][0]
    drag_handle(ed, 'z', 1, to={'x': h['x'] + b['x'] - a['x'], 'y': h['y'] + b['y'] - a['y']})
    wait_until(ed, "window._dbgApp.lights().events[0].beat===2", label='1拍移動')
    t.eq(_ev(lights(ed)[0]), {'beat': 2, 'et': 1, 'i': 5, 'f': 1}, '移動後（種別・値はそのまま）')
    undo(ed)
    wait_until(ed, "window._dbgApp.lights().events[0].beat===1", label='移動のUndo')
    t.no_errors()


def test_light_copy_paste(t):
    '''ライトをCtrl+C→別の拍のレーンにマウスを置いてCtrl+V＝マウスの拍へ仮置き→クリックで確定・Undoで消える。位置決め中の右クリックは貼ったものだけ取り消す'''
    ed = _open(t)
    place_light(ed, BACK, 1)
    _select_light(ed, BACK, 1)
    p = _copy_paste_at(ed, BACK, 1, 3)
    t.eq(edit(ed)['lightMove'], True, '貼り付け直後は位置決め中')
    t.eq(_ev(light_at(ed, BACK, 3)), {'beat': 3, 'et': 0, 'i': 5, 'f': 1}, 'マウスの拍(3)に同じライト')
    ed.click(p['x'], p['y'])
    wait_until(ed, "window._dbgApp.edit().lightMove===false", label='クリックで確定')
    t.eq(counts(ed)['lights'], 2, '確定後の数')
    undo(ed)
    wait_until(ed, "window._dbgApp.state().counts.lights===1", label='貼り付けのUndo')
    t.ok(light_at(ed, BACK, 1) is not None, '元のライトは残る')
    # 位置決め中の右クリック＝取消
    _select_light(ed, BACK, 1)
    p = _copy_paste_at(ed, BACK, 1, 2)
    ed.click(p['x'], p['y'], button='right')
    wait_until(ed, "window._dbgApp.state().counts.lights===1", label='右クリックで取消')
    t.ok(light_at(ed, BACK, 1) is not None and light_at(ed, BACK, 2) is None, '右クリック取消後に残るのは元のライトだけ')
    t.eq(edit(ed)['lightMove'], False, '取消後は位置決め中でない')
    t.no_errors()


def test_light_paste_cancel_esc(t):
    '''ライトの貼り付けの位置決め中にEsc＝貼ったものごと取り消す（画面の案内「右クリック・Escで取消」）'''
    ed = _open(t)
    place_light(ed, BACK, 1)
    _select_light(ed, BACK, 1)   # 選択で移動のつまみが出ている状態
    _copy_paste_at(ed, BACK, 1, 3)
    ed.key('Escape')
    wait_until(ed, "window._dbgApp.state().counts.lights===1", label='1回目のEscで取消')
    t.eq(edit(ed)['lightMove'], False, '取消後は位置決め中でない')
    t.no_errors()


def test_light_box_select_delete(t):
    '''レーンの外から左ドラッグで範囲選択→Xで選んだライトだけ消える→Undoで戻る'''
    ed = _open(t)
    for li, b in ((L_LASER, 1), (RINGS, 1), (BACK, 1), (BACK, 3)):
        place_light(ed, li, b)
    hover_off_grid(ed)
    ed.key('a')   # 置いた直後の選択を外しておく
    # 拍1の3個を囲む（拍3は入れない）。始点はレーンの外（左端のレーン0より外側）
    a = ed.js("window._dbgApp.lightLaneScreen(9,0.5)"); b = ed.js("window._dbgApp.lightLaneScreen(5,1.5)")
    s = ed.js("window._dbgApp.lightLaneScreen(0,0.5)")
    x0 = min(a['x'], b['x']) - 10; x1 = max(a['x'], b['x']) + 10
    y0 = min(s['y'], b['y']) - 25; y1 = max(a['y'], b['y']) + 20
    drag_box(ed, x1, y0, x0, y1)
    wait_until(ed, "window._dbgApp.edit().lightSel.length===3", label='範囲選択で3個')
    hover_off_grid(ed)
    ed.key('x')
    wait_until(ed, "window._dbgApp.state().counts.lights===1", label='Xで削除')
    t.eq(_ev(lights(ed)[0]), {'beat': 3, 'et': 0, 'i': 5, 'f': 1}, '枠の外（拍3）のライトは残る')
    undo(ed)
    wait_until(ed, "window._dbgApp.state().counts.lights===4", label='削除のUndo')
    t.no_errors()

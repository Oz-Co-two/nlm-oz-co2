"""配置・削除・Undo/Redo（本物のマウス/キー入力で操作し、数と中身で確かめる）"""
from e2e_helpers import open_fixture, counts, hover_3d, notes_at, place_at, state, wait_until


def test_place_undo_redo(t):
    '''配置モードでマスをクリックするとノーツが増え、Ctrl+Zで減り、Ctrl+Shift+Zで戻る'''
    ed = open_fixture(t, 'basic')
    t.eq(state(ed)['cur'], 0, '開いた直後の再生位置（拍0は空き）')
    t.eq(notes_at(ed, 0), [], '拍0のノーツ（置く前）')
    place_at(ed, 1, 1)
    t.eq(notes_at(ed, 0), [{'x': 1, 'y': 1, 'c': state(ed)['brush']['c'], 'd': state(ed)['brush']['d']}], '置いたノーツの位置・色・向き')
    t.eq(state(ed)['undo'] > 0, True, '履歴に積まれている')
    hover_3d(ed)
    ed.key('z', ctrl=True)
    wait_until(ed, "window._dbgApp.state().counts.notes===8", label='Undoで8個へ')
    t.eq(notes_at(ed, 0), [], 'Undo後の拍0')
    ed.key('z', ctrl=True, shift=True)
    wait_until(ed, "window._dbgApp.state().counts.notes===9", label='Redoで9個へ')
    t.eq(notes_at(ed, 0), [{'x': 1, 'y': 1, 'c': state(ed)['brush']['c'], 'd': state(ed)['brush']['d']}], 'Redo後の拍0')
    t.no_errors()


def test_place_color_flip(t):
    '''Fでブラシの色を反転してから置くと、反対の色のノーツになる'''
    ed = open_fixture(t, 'basic')
    c0 = state(ed)['brush']['c']
    hover_3d(ed)
    ed.key('f')
    wait_until(ed, f"window._dbgApp.state().brush.c==={1 - c0}", label='ブラシ色の反転')
    place_at(ed, 2, 0)
    t.eq([n['c'] for n in notes_at(ed, 0)], [1 - c0], '置いたノーツの色')
    t.no_errors()


def test_delete_right_click(t):
    '''置いたノーツを右クリックで削除でき、Undoで戻る'''
    ed = open_fixture(t, 'basic')
    place_at(ed, 1, 0)
    p = ed.js("window._dbgApp.cellScreen(1,0)")
    ed.move(p['x'], p['y']); ed.wait(0.15)
    ed.click(p['x'], p['y'], button='right')
    wait_until(ed, "window._dbgApp.state().counts.notes===8", label='右クリックで削除')
    t.eq(notes_at(ed, 0), [], '削除後の拍0')
    hover_3d(ed)
    ed.key('z', ctrl=True)
    wait_until(ed, "window._dbgApp.state().counts.notes===9", label='Undoで復活')
    t.eq(len(notes_at(ed, 0)), 1, 'Undo後の拍0')
    t.no_errors()


def test_delete_selection_key(t):
    '''ノーツをクリックで選んでDeleteキーで消す（他のノーツは残る）'''
    ed = open_fixture(t, 'basic')
    place_at(ed, 2, 1)
    p = ed.js("window._dbgApp.cellScreen(2,1)")
    ed.click(p['x'], p['y'])   # 配置済みの上のクリック＝選択
    wait_until(ed, "window._dbgApp.state().sel===1", label='クリックで選択')
    ed.key('Delete')
    wait_until(ed, "window._dbgApp.state().counts.notes===8", label='Deleteで削除')
    t.eq(notes_at(ed, 0), [], '削除後の拍0')
    t.eq(counts(ed)['notes'], 8, '元の8個は残る')
    t.no_errors()


def test_play_stop(t):
    '''Spaceで再生すると再生位置が進み、もう一度Spaceで止まる'''
    ed = open_fixture(t, 'basic')
    hover_3d(ed)
    ed.key(' ')
    wait_until(ed, "window._dbgApp.state().playing===true", label='再生開始')
    wait_until(ed, "window._dbgApp.state().cur>0.5", timeout=6, label='再生位置が進む')
    ed.key(' ')
    wait_until(ed, "window._dbgApp.state().playing===false", label='停止')
    c1 = state(ed)['cur']
    ed.wait(0.4)
    t.eq(state(ed)['cur'], c1, '停止後は再生位置が動かない')
    t.no_errors()

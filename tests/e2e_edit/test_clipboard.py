"""3Dビュー（NOTES）のコピー/貼り付け/切り取り（Ctrl+C / Ctrl+V / Ctrl+X）。
貼り付けは「再生ヘッドの拍へ相対配置→マウスのマスへ追従→Enter（または床クリック）で確定 / Esc・右クリックで取消」"""
from e2e_helpers import counts, state, wait_until, cell
from edit_helpers import (open_ed, mv, note_keys, click_obj, edit, undo, redo, hover_off_grid)

RED_10 = (3, 1, 0, 0, 1)    # basic の拍3・(1,0)・赤・下向き


def _select_pair(ed):
    """拍3の (1,0)赤 → (2,0)青 の順に選ぶ（貼り付けの基準＝先に選んだ方）"""
    click_obj(ed, beat=3, x=1, y=0)
    click_obj(ed, shift=True, beat=3, x=2, y=0)
    wait_until(ed, "window._dbgApp.state().sel===2", label='2個選択')


def _at(ed, beat):
    return sorted(k[1:] for k in note_keys(ed) if abs(k[0] - beat) < 1e-6)


def test_copy_paste_follow_enter(t):
    '''2個コピー→Ctrl+Vで再生ヘッド（拍0）へ同じ並びで仮置き→マウスのマスへ追従→Enterで確定→Undoで消え、Redoで戻る'''
    ed = open_ed(t)
    _select_pair(ed)
    before = note_keys(ed)
    hover_off_grid(ed)   # マスの上に無い＝貼り付けは元の列・段のまま
    ed.key('c', ctrl=True)
    ed.key('v', ctrl=True)
    wait_until(ed, "window._dbgApp.state().counts.notes===10", label='貼り付けで10個')
    t.eq(edit(ed)['pasteFollow'], True, '貼り付け直後は位置決め中（追従）')
    t.eq(state(ed)['sel'], 2, '貼り付けたものが選択される')
    t.eq(_at(ed, 0), [(1, 0, 0, 1), (2, 0, 1, 1)], '拍0に元と同じ列・段・色・向きで置かれる')
    p = cell(ed, 0, 2)
    mv(ed, p['x'], p['y'])
    wait_until(ed, "window._dbgApp.notes().notes.some(n=>n.beat===0&&n.x===0&&n.y===2)", label='マス(0,2)への追従')
    t.eq(_at(ed, 0), [(0, 2, 0, 1), (1, 2, 1, 1)], '基準(赤)が(0,2)へ・青は相対位置（右隣）を保つ')
    ed.key('Enter')
    wait_until(ed, "window._dbgApp.edit().pasteFollow===false", label='Enterで確定')
    hover_off_grid(ed)
    t.eq(_at(ed, 0), [(0, 2, 0, 1), (1, 2, 1, 1)], '確定後はマウスを動かしても動かない')
    t.eq(sorted(set(note_keys(ed)) - set(before)), [(0, 0, 2, 0, 1), (0, 1, 2, 1, 1)], '増えたのは拍0の2個だけ（元は残る）')
    undo(ed)
    wait_until(ed, "window._dbgApp.state().counts.notes===8", label='貼り付けのUndo')
    t.eq(note_keys(ed), before, 'Undoで元どおり')
    redo(ed)
    wait_until(ed, "window._dbgApp.state().counts.notes===10", label='貼り付けのRedo')
    t.eq(_at(ed, 0), [(0, 2, 0, 1), (1, 2, 1, 1)], 'Redo後の拍0（確定した位置）')
    t.no_errors()


def test_paste_cancel(t):
    '''貼り付けの位置決め中にEscで取消＝貼ったものごと消える。右クリックでも同じ'''
    ed = open_ed(t)
    _select_pair(ed)
    before = note_keys(ed)
    p = hover_off_grid(ed)
    ed.key('c', ctrl=True)
    ed.key('v', ctrl=True)
    wait_until(ed, "window._dbgApp.state().counts.notes===10", label='貼り付け')
    ed.key('Escape')
    wait_until(ed, "window._dbgApp.state().counts.notes===8", label='Escで取消')
    t.eq(edit(ed)['pasteFollow'], False, '取消後は追従していない')
    t.eq(note_keys(ed), before, 'Esc取消後は元どおり')
    ed.key('v', ctrl=True)
    wait_until(ed, "window._dbgApp.state().counts.notes===10", label='もう一度貼り付け')
    ed.click(p['x'], p['y'], button='right')
    wait_until(ed, "window._dbgApp.state().counts.notes===8", label='右クリックで取消')
    t.eq(note_keys(ed), before, '右クリック取消後は元どおり')
    t.no_errors()


def test_cut_paste(t):
    '''Ctrl+Xで選んだノーツが消え、Ctrl+V→Enterで拍0に同じものが戻る。Undo2回で切り取り前に戻る'''
    ed = open_ed(t)
    click_obj(ed, beat=3, x=1, y=0)
    wait_until(ed, "window._dbgApp.state().sel===1", label='1個選択')
    before = note_keys(ed)
    hover_off_grid(ed)
    ed.key('x', ctrl=True)
    wait_until(ed, "window._dbgApp.state().counts.notes===7", label='切り取り')
    t.ok(RED_10 not in note_keys(ed), '切り取ったノーツは消える')
    t.eq(state(ed)['sel'], 0, '切り取り後は選択なし')
    ed.key('v', ctrl=True)
    wait_until(ed, "window._dbgApp.state().counts.notes===8", label='貼り付け')
    ed.key('Enter')
    wait_until(ed, "window._dbgApp.edit().pasteFollow===false", label='確定')
    t.eq(_at(ed, 0), [(1, 0, 0, 1)], '拍0に切り取ったノーツ（列・段・色・向き）')
    undo(ed)
    wait_until(ed, "window._dbgApp.state().counts.notes===7", label='貼り付けのUndo')
    undo(ed)
    wait_until(ed, "window._dbgApp.state().counts.notes===8", label='切り取りのUndo')
    t.eq(note_keys(ed), before, '切り取り前に戻る')
    t.no_errors()

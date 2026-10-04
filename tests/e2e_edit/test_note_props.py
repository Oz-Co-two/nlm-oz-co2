"""3Dビュー（NOTES）の選択中ノーツの編集: 削除（X/Del）・向き回転（Alt+ホイール）・ドット化（D）・色反転（F）。
回転/D/Fの対象は「カーソル直下が選択中のノーツなら選択全体、それ以外はブラシだけ」（画面のショートカット表とコードの約束）"""
from e2e_helpers import counts, state, wait_until
from edit_helpers import (open_ed, notes, note_keys, click_obj, hover_obj, undo, redo, wheel, hover_off_grid)

ROT_NODOT = [1, 6, 2, 4, 0, 5, 3, 7]   # 回転順 ↓↙←↖↑↗→↘（ホイールを手前へ＝この順に進む・ドットは含まない）
Y0_D = "window._dbgApp.notes().notes.filter(n=>n.beat===3&&n.y===0).every(n=>n.d==={})"   # 拍3・段0の2個（赤(1,0)・青(2,0)）の向き


def _note(ed, beat, x, y):
    hs = [n for n in notes(ed) if n['beat'] == beat and n['x'] == x and n['y'] == y]
    assert len(hs) == 1, (beat, x, y, hs)
    return hs[0]


def _select(ed, *cells):
    for i, (b, x, y) in enumerate(cells):
        click_obj(ed, shift=i > 0, beat=b, x=x, y=y)
    wait_until(ed, f"window._dbgApp.state().sel==={len(cells)}", label=f'{len(cells)}個選択')


def test_delete_keys(t):
    '''選択が無い時のX/Delは何もしない。2個選んでXで消える（他は残る）→Ctrl+Zで戻る→Ctrl+Shift+Zでまた消える→Delでも消える'''
    ed = open_ed(t)
    before = note_keys(ed)
    hover_off_grid(ed)
    u0 = state(ed)['undo']
    ed.key('Delete'); ed.key('x'); ed.wait(0.2)
    t.eq((counts(ed)['notes'], state(ed)['undo']), (8, u0), '選択なしのDel/X: 数も履歴も変わらない')
    _select(ed, (3, 1, 0), (3, 2, 2))
    hover_off_grid(ed)
    ed.key('x')
    wait_until(ed, "window._dbgApp.state().counts.notes===6", label='Xで削除')
    t.eq(sorted(set(before) - set(note_keys(ed))), [(3, 1, 0, 0, 1), (3, 2, 2, 1, 1)], '消えたのは選んだ2個')
    t.eq(state(ed)['sel'], 0, '削除後は選択なし')
    undo(ed)
    wait_until(ed, "window._dbgApp.state().counts.notes===8", label='削除のUndo')
    t.eq(note_keys(ed), before, 'Undoで元どおり')
    redo(ed)
    wait_until(ed, "window._dbgApp.state().counts.notes===6", label='削除のRedo')
    _select(ed, (1, 1, 0))
    hover_off_grid(ed)
    ed.key('Delete')
    wait_until(ed, "window._dbgApp.state().counts.notes===5", label='Delで削除')
    t.ok((1, 1, 0, 0, 1) not in note_keys(ed), 'Delで消えたのは選んだノーツ')
    t.no_errors()


def test_rotate_alt_wheel(t):
    '''選択中ノーツの上でAlt+ホイール＝選択全体が回転順どおりに1段ずつ回り、Undoで戻る。選択外ではブラシの向きだけが回る'''
    ed = open_ed(t)
    _select(ed, (3, 1, 0), (3, 2, 0))
    o = hover_obj(ed, beat=3, x=1, y=0)
    wheel(ed, o['sx'], o['sy'], 100, alt=True)   # 手前へ1刻み＝次の向き
    nxt = ROT_NODOT[(ROT_NODOT.index(1) + 1) % 8]
    wait_until(ed, Y0_D.format(nxt), label='2個とも回転')
    t.eq(state(ed)['brush']['d'], nxt, 'ブラシの向きも回した向きに揃う')
    t.eq([_note(ed, 3, 0, 1)['d'], _note(ed, 1, 1, 0)['d']], [1, 1], '選んでいないノーツは回らない')
    ed.wait(0.6)   # 0.5秒以内の連続回転は1回の履歴にまとめる仕様＝間を空けて別の操作にする
    wheel(ed, o['sx'], o['sy'], -100, alt=True)   # 奥へ1刻み＝前の向きへ戻る
    wait_until(ed, Y0_D.format(1), label='逆回転で戻る')
    undo(ed)
    wait_until(ed, Y0_D.format(nxt), label='逆回転のUndo')
    undo(ed)
    wait_until(ed, Y0_D.format(1), label='回転のUndo')
    # 選択外（空き地）＝ブラシだけ
    before = note_keys(ed)
    d0 = state(ed)['brush']['d']
    p = hover_off_grid(ed)
    wheel(ed, p['x'], p['y'], 100, alt=True)
    want = ROT_NODOT[(ROT_NODOT.index(d0) + 1) % 8]
    wait_until(ed, f"window._dbgApp.state().brush.d==={want}", label='選択外: ブラシの向きだけ回る')
    t.eq(note_keys(ed), before, '選択外のAlt+ホイールでノーツは変わらない')
    t.no_errors()


def test_dot_key(t):
    '''選択外のD＝ブラシがドット⇄直前の矢印を行き来する。選択中ノーツの上でD＝選択中のノーツがドット(8)になり、Undo/Redoで往復'''
    ed = open_ed(t)
    before = note_keys(ed)
    hover_off_grid(ed)
    d0 = state(ed)['brush']['d']
    t.ok(d0 != 8, f'前提: 開いた直後のブラシは矢印（{d0}）')
    ed.key('d')
    wait_until(ed, "window._dbgApp.state().brush.d===8", label='ブラシをドットへ')
    ed.key('d')
    wait_until(ed, f"window._dbgApp.state().brush.d==={d0}", label='ブラシを直前の矢印へ戻す')
    t.eq(note_keys(ed), before, 'ブラシの切替でノーツは変わらない')
    _select(ed, (3, 1, 0), (3, 2, 0))
    hover_obj(ed, beat=3, x=2, y=0)
    ed.key('d')
    wait_until(ed, Y0_D.format(8), label='Dでドット')
    t.eq(_note(ed, 3, 0, 1)['d'], 1, '選んでいないノーツはそのまま')
    t.eq(state(ed)['brush']['d'], 8, 'ブラシもドットになる')
    undo(ed)
    wait_until(ed, Y0_D.format(1), label='DのUndo')
    redo(ed)
    wait_until(ed, Y0_D.format(8), label='DのRedo')
    t.no_errors()


def test_flip_color_selection(t):
    '''赤と青を選び、選択中ノーツの上でF＝両方の色が入れ替わる・Undoで戻る'''
    ed = open_ed(t)
    _select(ed, (3, 1, 0), (3, 2, 0))
    hover_obj(ed, beat=3, x=1, y=0)
    ed.key('f')
    both = "(n=>n.find(o=>o.beat===3&&o.x===1&&o.y===0).c==={}&&n.find(o=>o.beat===3&&o.x===2&&o.y===0).c==={})(window._dbgApp.notes().notes)"
    wait_until(ed, both.format(1, 0), label='Fで色反転')
    t.eq([_note(ed, 3, 0, 1)['c'], _note(ed, 3, 3, 1)['c']], [0, 1], '選んでいないノーツの色はそのまま')
    t.eq(counts(ed)['notes'], 8, '数は変わらない')
    undo(ed)
    wait_until(ed, both.format(0, 1), label='FのUndo')
    t.no_errors()

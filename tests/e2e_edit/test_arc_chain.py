"""3Dビュー（NOTES）のアーク/チェーン: 選択からの作成（Ctrl+R＝アーク / C＝チェーン。同色の連続ペアごと）と
ホイールでの調整（アーク: Alt=mu・Ctrl+Alt=tmu・Shift+Alt=巻き方向 ／ チェーン: Shift=分割数・Ctrl+Alt=squish）。
※チェーンの Ctrl+T はブラウザ予約（新しいタブ）でページに届かないため、ヘッドレスEdgeでは確かめられない＝C で確かめる"""
from e2e_helpers import counts, state, wait_until
from edit_helpers import (open_ed, chains, objs, note_keys, click_obj, undo, redo, wheel, hover_off_grid)

ARC_KEYS = ('b', 'x', 'y', 'c', 'd', 'tb', 'tx', 'ty', 'tc', 'mu', 'tmu', 'm')
CHAIN_KEYS = ('b', 'x', 'y', 'c', 'd', 'tb', 'tx', 'ty', 'sc', 's')


def _select(ed, *cells):
    for i, (b, x, y) in enumerate(cells):
        click_obj(ed, shift=i > 0, beat=b, x=x, y=y)
    wait_until(ed, f"window._dbgApp.state().sel==={len(cells)}", label=f'{len(cells)}個選択')


def _arcs(ed):
    return sorted(({k: a[k] for k in ARC_KEYS} for a in objs(ed)['arcs']), key=lambda a: (a['b'], a['c']))


def _chains(ed):
    return sorted(({k: c[k] for k in CHAIN_KEYS} for c in chains(ed)), key=lambda c: (c['b'], c['c']))


def test_arc_create_ctrl_r(t):
    '''赤2個を選んでCtrl+R＝早い方を頭・遅い方を尾にしたアークが1本でき、ノーツは残る・Undo/Redoで往復。赤2個＋青2個なら色ごとに1本ずつ'''
    ed = open_ed(t)
    before = note_keys(ed)
    _select(ed, (3, 1, 2), (1, 1, 0))   # 選ぶ順は逆でも、頭は拍の早い方
    hover_off_grid(ed)
    ed.key('r', ctrl=True)
    wait_until(ed, "window._dbgApp.state().counts.arcs===1", label='アーク作成')
    t.eq(_arcs(ed), [dict(b=1, x=1, y=0, c=0, d=1, tb=3, tx=1, ty=2, tc=1, mu=1, tmu=1, m=0)], 'アークの頭・尾・色・向き・既定の曲率')
    t.eq(note_keys(ed), before, '頭と尾のノーツはそのまま残る')
    t.eq(state(ed)['sel'], 1, '作ったアークが選択される')
    undo(ed)
    wait_until(ed, "window._dbgApp.state().counts.arcs===0", label='アーク作成のUndo')
    redo(ed)
    wait_until(ed, "window._dbgApp.state().counts.arcs===1", label='アーク作成のRedo')
    undo(ed)
    wait_until(ed, "window._dbgApp.state().counts.arcs===0", label='もう一度Undo')
    ed.key('a')
    _select(ed, (1, 1, 0), (2, 2, 0), (3, 0, 1), (3, 3, 1))
    hover_off_grid(ed)
    ed.key('r', ctrl=True)
    wait_until(ed, "window._dbgApp.state().counts.arcs===2", label='アーク2本')
    t.eq(_arcs(ed), [dict(b=1, x=1, y=0, c=0, d=1, tb=3, tx=0, ty=1, tc=1, mu=1, tmu=1, m=0),
                     dict(b=2, x=2, y=0, c=1, d=1, tb=3, tx=3, ty=1, tc=1, mu=1, tmu=1, m=0)], '赤→赤・青→青のアーク')
    t.eq(counts(ed)['notes'], 8, 'ノーツは残る')
    t.no_errors()


def test_arc_needs_same_color_pair(t):
    '''赤1個と青1個だけを選んだCtrl+Rはアークを作らず、理由を知らせる'''
    ed = open_ed(t)
    _select(ed, (1, 1, 0), (2, 2, 0))
    hover_off_grid(ed)
    u0 = state(ed)['undo']
    ed.key('r', ctrl=True)
    wait_until(ed, "getComputedStyle(document.getElementById('errToast')).display!=='none'", label='エラー表示')
    t.eq(counts(ed)['arcs'], 0, 'アークはできない')
    t.eq(state(ed)['undo'], u0, '履歴は増えない')
    t.ok('ペア' in ed.js("document.getElementById('errToast').textContent"), '同色のペアが無いことを知らせる')
    # 知らせは console.error にも出る仕様（showErr）＝それ以外のエラーが無いこと
    t.eq([e for e in ed.errors() if 'アーク: 作成できるペアがありません' not in e], [], 'ページ内エラー（想定の知らせ以外）')


def test_arc_adjust_wheel(t):
    '''アークを選んだまま空き地でAlt+ホイール＝mu、Ctrl+Alt+ホイール＝tmu、Shift+Alt+ホイール＝巻き方向が変わり、Undoで1つずつ戻る'''
    ed = open_ed(t)
    _select(ed, (1, 1, 0), (3, 1, 2))
    p = hover_off_grid(ed)
    ed.key('r', ctrl=True)
    wait_until(ed, "window._dbgApp.state().counts.arcs===1", label='アーク作成')
    wheel(ed, p['x'], p['y'], -100, alt=True)               # 奥へ1刻み＝+0.1
    wait_until(ed, "window._dbgApp.objs().arcs[0].mu===1.1", label='mu +0.1')
    wheel(ed, p['x'], p['y'], -100, alt=True, ctrl=True)
    wait_until(ed, "window._dbgApp.objs().arcs[0].tmu===1.1", label='tmu +0.1')
    wheel(ed, p['x'], p['y'], -100, alt=True, shift=True)
    wait_until(ed, "window._dbgApp.objs().arcs[0].m===1", label='巻き方向 自動→時計回り')
    a = _arcs(ed)[0]
    t.eq((a['mu'], a['tmu'], a['m'], a['b'], a['tb']), (1.1, 1.1, 1, 1, 3), '調整後（頭・尾の拍は変わらない）')
    undo(ed)
    wait_until(ed, "window._dbgApp.objs().arcs[0].m===0", label='巻き方向のUndo')
    undo(ed)
    wait_until(ed, "window._dbgApp.objs().arcs[0].tmu===1", label='tmuのUndo')
    undo(ed)
    wait_until(ed, "window._dbgApp.objs().arcs[0].mu===1", label='muのUndo')
    t.no_errors()


def test_chain_create_adjust(t):
    '''赤2個を選んでC＝早い方を頭にしたチェーンができ元の2個は消える→Shift+ホイール＝分割数・Ctrl+Alt+ホイール＝squish→Undoで1つずつ戻り、最後にノーツが戻る'''
    ed = open_ed(t)
    before = note_keys(ed)
    _select(ed, (1, 1, 0), (3, 1, 2))
    p = hover_off_grid(ed)
    ed.key('c')
    wait_until(ed, "window._dbgApp.state().counts.chains===1", label='チェーン作成')
    t.eq(_chains(ed), [dict(b=1, x=1, y=0, c=0, d=1, tb=3, tx=1, ty=2, sc=5, s=1)], 'チェーンの頭・尾・既定の分割数/squish')
    t.eq(sorted(set(before) - set(note_keys(ed))), [(1, 1, 0, 0, 1), (3, 1, 2, 0, 1)], '頭と尾にしたノーツは消える')
    t.eq(counts(ed)['notes'], 6, 'ノーツ数')
    wheel(ed, p['x'], p['y'], -100, shift=True)                # 奥へ＝+1
    wait_until(ed, "window._dbgApp.notes().chains[0].sc===6", label='分割数 +1')
    wheel(ed, p['x'], p['y'], 100, shift=True)
    wheel(ed, p['x'], p['y'], 100, shift=True)
    wait_until(ed, "window._dbgApp.notes().chains[0].sc===4", label='分割数 -2')
    wheel(ed, p['x'], p['y'], -100, ctrl=True, alt=True)
    wait_until(ed, "window._dbgApp.notes().chains[0].s===1.1", label='squish +0.1')
    c = _chains(ed)[0]
    t.eq((c['b'], c['tb'], c['x'], c['y'], c['tx'], c['ty'], c['c'], c['d']), (1, 3, 1, 0, 1, 2, 0, 1), '調整で頭・尾・色・向きは変わらない')
    undo(ed)
    wait_until(ed, "window._dbgApp.notes().chains[0]?.s===1", label='squishのUndo')
    t.eq(chains(ed)[0]['sc'], 4, 'squishだけが戻り分割数はそのまま')
    for _ in range(3):
        undo(ed)
    wait_until(ed, "window._dbgApp.notes().chains[0]?.sc===5", label='分割数のUndo（3回分）')
    undo(ed)
    wait_until(ed, "window._dbgApp.state().counts.chains===0&&window._dbgApp.state().counts.notes===8", label='チェーン作成のUndo')
    t.eq(note_keys(ed), before, 'Undoでノーツが戻る')
    t.no_errors()


def test_chain_adjust_limits(t):
    '''チェーンの分割数は2未満にならず、下限で回しても値が変わらない操作は履歴に積まない'''
    ed = open_ed(t)
    _select(ed, (1, 1, 0), (3, 1, 2))
    p = hover_off_grid(ed)
    ed.key('c')
    wait_until(ed, "window._dbgApp.state().counts.chains===1", label='チェーン作成')
    for _ in range(3):   # 5 → 2
        wheel(ed, p['x'], p['y'], 100, shift=True)
    wait_until(ed, "window._dbgApp.notes().chains[0].sc===2", label='分割数 2')
    u0 = state(ed)['undo']
    wheel(ed, p['x'], p['y'], 100, shift=True)
    ed.wait(0.1)
    t.eq(chains(ed)[0]['sc'], 2, '下限(2)でさらに回しても値は変わらない')
    t.no_errors()
    t.eq(state(ed)['undo'], u0, '値が変わらないホイールでは履歴を積まない（Ctrl+Zが空振りしない）')

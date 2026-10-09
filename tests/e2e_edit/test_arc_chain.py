"""3Dビュー（NOTES）のアーク/チェーン: 選択からの作成（Ctrl+R＝アーク / C＝チェーン。同色の連続ペアごと）と
ホイールでの調整（アーク: Alt=mu・Ctrl+Alt=tmu・Shift+Alt=巻き方向 ／ チェーン: Shift=分割数・Ctrl+Alt=squish）。
アークとその端のノーツの連動（2026-10-06）: クリックはノーツ優先・ノーツを動かすとアークの端がついてくる・アークの全体移動は
端のノーツを連れていく・ノーツの向きの変更はアークの向きへ。
※チェーンの Ctrl+T はブラウザ予約（新しいタブ）でページに届かないため、ヘッドレスEdgeでは確かめられない＝C で確かめる"""
from e2e_helpers import counts, state, wait_until, cell
from edit_helpers import (open_ed, chains, objs, note_keys, notes, click_obj, hover_obj, objs_on_screen, undo, redo, wheel,
                          hover_off_grid, drag_handle, frames, wait_cells_on_screen)

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


# ---- アークと端のノーツの連動（2026-10-06） ----
def _arc_red(ed):
    """赤 (拍1,列1,段0)→(拍3,列1,段2) のアークを作る（作った直後はアークが選ばれている）"""
    _select(ed, (1, 1, 0), (3, 1, 2))
    hover_off_grid(ed)
    ed.key('r', ctrl=True)
    wait_until(ed, "window._dbgApp.state().counts.arcs===1", label='アーク作成')


def _ends(ed):
    """アーク（1本）の頭と尾 (拍,列,段)"""
    a = objs(ed)['arcs'][0]
    return (a['b'], a['x'], a['y']), (a['tb'], a['tx'], a['ty'])


def _red_cells(ed):
    """赤ノーツの (拍,列,段)"""
    return sorted((n['beat'], n['x'], n['y']) for n in notes(ed) if n['c'] == 0)


def _to_beat(ed, beat):
    """再生ヘッドを beat へ（その拍のノーツが配置グリッドの深さに来る＝マスの間隔がそのままつまみの1段）"""
    hover_off_grid(ed)
    for _ in range(int(beat * 2)):   # スナップ1/2＝1回で半拍
        ed.key('ArrowRight')
    wait_until(ed, f"Math.abs(window._dbgApp.state().cur-{beat})<1e-6", label=f'再生ヘッドを拍{beat}へ')
    wait_cells_on_screen(ed)
    frames(ed)


def _drag_by(ed, axis, sign, d):
    frames(ed)
    g = ed.js("window._dbgApp.gizmoScreen()")
    h = [h for h in g['handles'] if h['axis'] == axis and h['sign'] == sign][0]
    drag_handle(ed, axis, sign, to={'x': h['x'] + d[0], 'y': h['y'] + d[1]})


def _delta(ed, a, b):
    pa, pb = cell(ed, *a), cell(ed, *b)
    return pb['x'] - pa['x'], pb['y'] - pa['y']


def test_arc_end_note_click_and_follow(t):
    '''アークの端のノーツをクリック＝アークではなくノーツが選ばれる→段のつまみで1段上げるとアークの頭もついてくる（尾はそのまま）
    →Undo1回でノーツとアークが一緒に戻る→拍のつまみで尾より後ろへ大きく引いても、尾と同じ拍で止まり、その先へのつまみは消える'''
    ed = open_ed(t)
    _arc_red(ed)
    _to_beat(ed, 1)
    click_obj(ed, beat=1, x=1, y=0)
    wait_until(ed, "window._dbgApp.state().sel===1&&window._dbgApp.gizmoScreen().handles.length>0", label='クリックで選択')
    t.eq([o['kind'] for o in objs_on_screen(ed) if o['sel']], ['note'], '端のノーツの上のクリックはノーツを選ぶ（以前はアークの端を掴んだ）')
    t.eq(ed.js("window._dbgApp.gizmoScreen().mini"), 0, 'アークは選ばれない＝頭・尾の小さいつまみは出ない')
    u0 = state(ed)['undo']
    _drag_by(ed, 'y', 1, _delta(ed, (1, 0), (1, 1)))
    wait_until(ed, "window._dbgApp.notes().notes.some(n=>n.beat===1&&n.x===1&&n.y===1)", label='ノーツを1段上げる')
    t.eq(_ends(ed), ((1, 1, 1), (3, 1, 2)), 'アークの頭がノーツについてくる・尾はそのまま')
    t.eq(state(ed)['undo'], u0 + 1, '履歴は1つ')
    undo(ed)
    wait_until(ed, "window._dbgApp.notes().notes.some(n=>n.beat===1&&n.x===1&&n.y===0)", label='Undo')
    t.eq(_ends(ed), ((1, 1, 0), (3, 1, 2)), 'Undo1回でアークも戻る')
    redo(ed)
    wait_until(ed, "window._dbgApp.objs().arcs[0]?.y===1", label='Redo')
    t.eq(_red_cells(ed), [(1, 1, 1), (3, 0, 1), (3, 1, 0), (3, 1, 2)], 'Redoでノーツも上がる')
    # 頭のノーツを尾より後ろの拍へ大きく引く → 尾と同じ拍（3）で止まる
    click_obj(ed, beat=1, x=1, y=1)
    wait_until(ed, "window._dbgApp.gizmoScreen().handles.some(h=>h.axis==='z'&&h.sign===1)", label='拍のつまみ')
    head = [o for o in objs_on_screen(ed) if o['kind'] == 'note' and o['beat'] == 1 and o['x'] == 1][0]
    tail = [o for o in objs_on_screen(ed) if o['kind'] == 'note' and o['beat'] == 3 and o['x'] == 1 and o['y'] == 2][0]
    _drag_by(ed, 'z', 1, ((tail['sx'] - head['sx']) * 1.6, (tail['sy'] - head['sy']) * 1.6))
    wait_until(ed, "window._dbgApp.objs().arcs[0].b>1", label='拍の移動')
    t.eq(_ends(ed), ((3, 1, 1), (3, 1, 2)), '頭は尾と同じ拍で止まる（追い越さない）')
    t.ok((3, 1, 1) in _red_cells(ed) and (1, 1, 1) not in _red_cells(ed), 'ノーツも拍3へ')
    frames(ed)
    hs = ed.js("window._dbgApp.gizmoScreen()")['handles']
    t.ok(not any(h['axis'] == 'z' and h['sign'] == 1 for h in hs), 'それ以上後ろへ動かせないので拍の＋のつまみは消える')
    t.ok(any(h['axis'] == 'z' and h['sign'] == -1 for h in hs), '前へ戻すつまみは出ている')
    t.no_errors()


def test_arc_move_takes_end_notes(t):
    '''アークを選んで全体移動のつまみで1列動かす＝両端のノーツも一緒に動く（形はそのまま）→Undo1回で全部戻る。
    アークを選ぶと頭・尾の小さいつまみが出て、全体移動のつまみはノーツを選んだ時より大きくなる（見分けやすく）'''
    ed = open_ed(t)
    click_obj(ed, beat=1, x=1, y=0)
    wait_until(ed, "window._dbgApp.gizmoScreen().handles.length>0", label='ノーツの選択でつまみ')
    small = {h['scale'] for h in ed.js("window._dbgApp.gizmoScreen()")['handles']}
    before = note_keys(ed)
    _arc_red(ed)
    wait_until(ed, "window._dbgApp.gizmoScreen().mini>0&&window._dbgApp.gizmoScreen().handles.length>0", label='アークのつまみ')
    frames(ed)
    big = {h['scale'] for h in ed.js("window._dbgApp.gizmoScreen()")['handles']}
    t.ok(len(small) == 1 and len(big) == 1 and min(big) > max(small) * 1.4, f'アークの全体移動のつまみは大きい（ノーツ {small} → アーク {big}）')
    _drag_by(ed, 'x', -1, _delta(ed, (1, 0), (0, 0)))
    wait_until(ed, "window._dbgApp.objs().arcs[0].x===0", label='アークを1列動かす')
    t.eq(_ends(ed), ((1, 0, 0), (3, 0, 2)), 'アークの頭・尾が1列動く')
    t.eq(_red_cells(ed), [(1, 0, 0), (3, 0, 1), (3, 0, 2), (3, 1, 0)], '両端のノーツも一緒に動く（他のノーツはそのまま）')
    t.eq(counts(ed)['notes'], 8, '数は変わらない')
    undo(ed)
    wait_until(ed, "window._dbgApp.objs().arcs[0].x===1", label='Undo')
    t.eq(note_keys(ed), before, 'Undo1回でノーツも戻る')
    t.eq(_ends(ed), ((1, 1, 0), (3, 1, 2)), 'アークも戻る')
    t.no_errors()


def test_arc_dir_follows_end_note(t):
    '''端のノーツの向きを変える（Alt+ホイール・D＝ドット）と、つながったアークの向き（頭=d・尾=tc）もそろう。もう一方の端は変わらない'''
    ed = open_ed(t)
    _arc_red(ed)
    click_obj(ed, beat=3, x=1, y=2)
    wait_until(ed, "window._dbgApp.state().sel===1", label='尾のノーツを選ぶ')
    t.eq([o['kind'] for o in objs_on_screen(ed) if o['sel']], ['note'], '尾のノーツが選ばれる')
    p = hover_obj(ed, beat=3, x=1, y=2)
    wheel(ed, p['sx'], p['sy'], 100, alt=True)
    wait_until(ed, "window._dbgApp.notes().notes.find(n=>n.beat===3&&n.x===1&&n.y===2).d!==1", label='尾のノーツを回す')
    d = [n['d'] for n in notes(ed) if (n['beat'], n['x'], n['y']) == (3, 1, 2)][0]
    a = objs(ed)['arcs'][0]
    t.eq((a['tc'], a['d']), (d, 1), 'アークの尾の向きがノーツにそろう・頭はそのまま')
    ed.key('d')
    wait_until(ed, "window._dbgApp.objs().arcs[0].tc===8", label='D＝ドット')
    t.eq(objs(ed)['arcs'][0]['d'], 1, '頭の向きは変わらない')
    undo(ed)
    wait_until(ed, f"window._dbgApp.objs().arcs[0].tc==={d}", label='ドットのUndo')
    t.no_errors()

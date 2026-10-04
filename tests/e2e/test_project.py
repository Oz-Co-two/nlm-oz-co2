"""保存→開き直し・未保存判定・難易度の切り替え"""
import json
import time

from e2e_helpers import (FIXTURE_DIFFS, open_fixture, RICH, counts, diff_counts_from_project, dirty, hover_3d, place_at, project,
                         state, switch_diff, wait_until)


def _roundtrip(t, fx):
    ed = open_fixture(t, fx)
    before = project(ed)
    t.eq(diff_counts_from_project(before), FIXTURE_DIFFS[fx], f'{fx}: 開いた直後の難易度ごとの数')
    # 保存した文字列をそのまま開き直す（アプリの保存→読込の経路）
    ed.js("(async()=>{ const rt=window._dbg.rt; await rt.applyProject(JSON.parse(rt.buildProjectText())); return true; })()")
    after = project(ed)
    t.eq(diff_counts_from_project(after), FIXTURE_DIFFS[fx], f'{fx}: 開き直した後の難易度ごとの数')
    t.eq(after, before, f'{fx}: 保存→開き直し→保存の内容が一致')
    cur = before['current']
    t.eq(state(ed)['diff'], cur, f'{fx}: 開き直した後の現在の難易度')
    t.eq(counts(ed), FIXTURE_DIFFS[fx][cur], f'{fx}: 開き直した後の現在の難易度の数（画面上）')
    return ed, before


def test_roundtrip_basic(t):
    '''basic: 保存→開き直しで内容と数が変わらない'''
    _roundtrip(t, 'basic')
    t.no_errors()


def test_roundtrip_rich(t):
    '''rich: 保存→開き直しで内容と数（2難易度・テンポ・曲情報・NJS）が変わらない'''
    ed, pj = _roundtrip(t, 'rich')
    t.eq(pj['tempoParts'], [{'beat': 16, 'bpm': 150}], 'テンポパート')
    t.eq(pj['info']['_songName'], 'リッチ テスト曲', '曲名')
    t.eq(pj['njsCfg'], {'hardstandard.dat': {'njs': 14, 'offset': 0}, 'expertstandard.dat': {'njs': 17, 'offset': -0.25}}, 'NJS/オフセット')
    # 開き直した後、開いていなかった難易度へ切り替えても中身が揃っている
    switch_diff(ed, 'Expert')
    t.eq(counts(ed), RICH['ExpertStandard.dat'], 'Expertの数（開き直し後に切り替え）')
    t.no_errors()


def test_dirty_lamp_edit_undo(t):
    '''未保存判定: 開いた直後は未保存でない→編集すると未保存→Undoで元に戻ると未保存でなくなる→Redoでまた未保存'''
    ed = open_fixture(t, 'basic')
    t.eq(dirty(ed)['lamp'], False, '開いた直後')
    t.eq(ed.js("document.getElementById('dirtyLamp').classList.contains('on')"), False, '開いた直後のランプ表示')
    place_at(ed, 1, 1)
    wait_until(ed, "window._dbgApp.dirty().lamp===true", label='編集後に未保存になる')
    t.eq(ed.js("document.getElementById('dirtyLamp').classList.contains('on')"), True, '編集後のランプ表示')
    hover_3d(ed)
    ed.key('z', ctrl=True)
    wait_until(ed, "window._dbgApp.dirty().lamp===false", label='Undoで保存時点に戻ると未保存でなくなる')
    t.eq(dirty(ed)['same'], True, 'Undo後は保存時点と同じ内容')
    ed.key('z', ctrl=True, shift=True)
    wait_until(ed, "window._dbgApp.dirty().lamp===true", label='Redoで再び未保存')
    t.no_errors()


def test_dirty_diff_switch_only(t):
    '''未保存判定: 難易度を切り替えただけでは未保存にならない'''
    ed = open_fixture(t, 'rich')
    switch_diff(ed, 'Expert')
    switch_diff(ed, 'Hard')
    ed.wait(0.7)   # 判定は操作が落ち着いて0.5秒後
    t.eq(dirty(ed)['lamp'], False, '切り替えのみ')
    t.no_errors()


def test_fresh_from_dirty(t):
    '''未保存の状態から開き直しても固まらない（ページ離脱の確認は自動で承諾される）'''
    ed = open_fixture(t, 'basic')
    place_at(ed, 1, 1)
    wait_until(ed, "window._dbgApp.dirty().lamp===true", label='未保存にする')
    t0 = time.time()
    ed = t.fresh('basic')   # テスト基盤の開き直しそのものを確かめる
    t.ok(time.time() - t0 < 20, f'開き直しに時間がかかりすぎ: {time.time() - t0:.1f}秒')
    t.eq(counts(ed)['notes'], 8, '開き直した後のノーツ数（編集は捨てられる）')
    t.eq(dirty(ed)['lamp'], False, '開き直した後は未保存でない')
    t.no_errors()


def test_diff_switch_isolation(t):
    '''難易度を切り替えても各難易度の中身が混ざらない（片方へ足したノーツは他方に入らない）'''
    ed = open_fixture(t, 'rich')
    t.eq(counts(ed), RICH['HardStandard.dat'], 'Hard（開いた直後）')
    switch_diff(ed, 'Expert')
    t.eq(counts(ed), RICH['ExpertStandard.dat'], 'Expert')
    ex_notes = ed.js("window._dbgApp.notes().notes.map(n=>[n.beat,n.x,n.y,n.c,n.d])")
    place_at(ed, 0, 2)   # Expert の拍0（空き）へ1個足す
    switch_diff(ed, 'Hard')
    t.eq(counts(ed), RICH['HardStandard.dat'], 'Hard（Expertへ足した後）')
    t.eq(ed.js("window._dbgApp.notes().notes.some(n=>n.beat===0)"), False, 'Hardの拍0にノーツは無い')
    switch_diff(ed, 'Expert')
    want = dict(RICH['ExpertStandard.dat'], notes=RICH['ExpertStandard.dat']['notes'] + 1)
    t.eq(counts(ed), want, 'Expert（足した1個が残る）')
    now = ed.js("window._dbgApp.notes().notes.map(n=>[n.beat,n.x,n.y,n.c,n.d])")
    t.eq(sorted(map(json.dumps, now)), sorted(map(json.dumps, ex_notes + [[0, 0, 2, state(ed)['brush']['c'], state(ed)['brush']['d']]])),
         'Expertのノーツの中身')
    # 空の難易度（Easy）へ切り替えると空
    switch_diff(ed, 'Easy')
    t.eq(counts(ed), dict(notes=0, bombs=0, walls=0, arcs=0, chains=0, lights=0), 'Easy（空）')
    # 保存内容でも分かれている
    got = diff_counts_from_project(project(ed))
    t.eq(got, {'HardStandard.dat': RICH['HardStandard.dat'], 'ExpertStandard.dat': want}, '保存内容の難易度ごとの数')
    t.no_errors()

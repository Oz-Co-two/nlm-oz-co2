"""難易度の操作: ノーツ/ライティングの転送・受信（diffCopy）と全消去（diffClear）。
難易度ボタン（現在選択中のもの）を押して出るメニューを本物のクリックで開き、項目を押して実行する。
rich: Hard = notes7 bombs1 walls1 arcs1 chains0 lights3 / Expert = notes23 bombs3 walls2 arcs2 chains2 lights12"""
from e2e_helpers import RICH, counts, diff_counts_from_project, dirty, hover_3d, project, state, switch_diff, wait_until
from project_helpers import diff_flat, diff_menu_open, diff_totals, menu_pick, toast

HARD = RICH['HardStandard.dat']
EXPERT = RICH['ExpertStandard.dat']
ZERO = dict(notes=0, bombs=0, walls=0, arcs=0, chains=0, lights=0)
NOTE_KINDS = ('notes', 'bombs', 'walls', 'arcs', 'chains')


def _open_rich(t):
    from e2e_helpers import open_fixture
    ed = open_fixture(t, 'rich')
    ed.js("document.getElementById('errToast').style.display='none'")
    t.eq(state(ed)['diff'], 'HardStandard.dat', '開いた直後の難易度')
    return ed


def _undo(ed):
    hover_3d(ed)
    ed.key('z', ctrl=True)


def _redo(ed):
    hover_3d(ed)
    ed.key('z', ctrl=True, shift=True)


def _wait_toast(ed, text):
    wait_until(ed, f"document.getElementById('errToast').textContent.includes({text!r})", label=f'トースト「{text}」')


def test_copy_notes_to_other_diff(t):
    '''Hardのメニュー「ノーツを転送→Expert」: Expertのノーツ類がHardと同じ中身になり（ライトは変わらない）、Hardは変わらない'''
    ed = _open_rich(t)
    hard_before = diff_flat(ed, 'HardStandard.dat')
    diff_menu_open(ed, 'Hard')
    menu_pick(ed, 'ノーツを転送', '→ Expert')
    menu_pick(ed, '⚠')   # Expertに既存のノーツがあるので上書き確認が出る
    _wait_toast(ed, 'コピーしました')
    tot = diff_totals(ed)
    t.eq(tot['ExpertStandard.dat'], dict(HARD, lights=EXPERT['lights']), 'Expertの数（ノーツ類はHard、ライトは元のまま）')
    t.eq(tot['HardStandard.dat'], HARD, 'Hardの数（変わらない）')
    ex, hd = diff_flat(ed, 'ExpertStandard.dat'), diff_flat(ed, 'HardStandard.dat')
    for k in NOTE_KINDS:
        t.eq(ex[k], hd[k], f'Expertの{k}の中身 = Hard')
    t.eq(hd, hard_before, 'Hardの中身は変わらない')
    t.ok('Undoできません' in toast(ed), '画面外の難易度への操作はUndoできないと案内する')
    t.eq(counts(ed), HARD, '現在の難易度（Hard）の表示は変わらない')
    wait_until(ed, "window._dbgApp.dirty().lamp===true", timeout=3, label='未保存になる')
    t.no_errors()


def test_copy_lights_to_other_diff(t):
    '''Hardのメニュー「ライティングを転送→Expert」: Expertのライトだけ置き換わり、ノーツ類は元のまま'''
    ed = _open_rich(t)
    expert_before = diff_flat(ed, 'ExpertStandard.dat')
    diff_menu_open(ed, 'Hard')
    menu_pick(ed, 'ライティングを転送', '→ Expert')
    menu_pick(ed, '⚠')
    _wait_toast(ed, 'コピーしました')
    tot = diff_totals(ed)
    t.eq(tot['ExpertStandard.dat'], dict(EXPERT, lights=HARD['lights']), 'Expertの数（ライトだけHardの3）')
    t.eq(diff_flat(ed, 'ExpertStandard.dat')['lightEvents'], diff_flat(ed, 'HardStandard.dat')['lightEvents'], 'ライトの中身 = Hard')
    ex = diff_flat(ed, 'ExpertStandard.dat')
    for k in NOTE_KINDS:
        t.eq(ex[k], expert_before[k], f'Expertの{k}は変わらない')
    t.eq(tot['HardStandard.dat'], HARD, 'Hardは変わらない')
    t.no_errors()


def test_copy_all_to_empty_diff_no_confirm(t):
    '''空のEasyへ「丸ごと転送」: 上書き確認は出ず、ノーツもライトもHardと同じ数になる。Hardは変わらない'''
    ed = _open_rich(t)
    diff_menu_open(ed, 'Hard')
    menu_pick(ed, '丸ごと転送（ノーツ＋ライト）', '→ Easy')
    _wait_toast(ed, 'コピーしました')   # 確認(⚠)を挟まず実行される（空なので上書きにならない）
    tot = diff_totals(ed)
    t.eq(tot['EasyStandard.dat'], HARD, 'Easyの数 = Hard')
    t.eq(tot['HardStandard.dat'], HARD, 'Hardは変わらない')
    t.eq(tot['ExpertStandard.dat'], EXPERT, 'Expertは変わらない')
    ez, hd = diff_flat(ed, 'EasyStandard.dat'), diff_flat(ed, 'HardStandard.dat')
    t.eq(ez, hd, 'Easyの中身 = Hard（ノーツ・ボム・壁・アーク・ライト）')
    # コピー先を開いても同じ（実際に画面へ出る数）
    switch_diff(ed, 'Easy')
    t.eq(counts(ed), HARD, 'Easyへ切り替えた時の画面の数')
    t.no_errors()


def test_copy_overwrite_cancel(t):
    '''上書き確認で「キャンセル」を選ぶと何もコピーされない'''
    ed = _open_rich(t)
    before = project(ed)
    diff_menu_open(ed, 'Hard')
    menu_pick(ed, 'ノーツを転送', '→ Expert')
    menu_pick(ed, 'キャンセル')
    ed.wait(0.3)
    t.eq(project(ed), before, '内容は変わらない')
    t.eq(dirty(ed)['lamp'], False, '未保存にならない')
    t.no_errors()


def test_receive_into_current_and_undo(t):
    '''Hardのメニュー「ノーツを受信←Expert」: 今の難易度（Hard）がExpertのノーツ類になり（ライトは元のまま）、Undoで戻り、Redoでまた反映'''
    ed = _open_rich(t)
    diff_flat_before = diff_flat(ed, 'HardStandard.dat')
    diff_menu_open(ed, 'Hard')
    menu_pick(ed, 'ノーツを受信', '← Expert')
    menu_pick(ed, '⚠')
    want = dict(EXPERT, lights=HARD['lights'])
    wait_until(ed, f"window._dbgApp.state().counts.notes==={EXPERT['notes']}", label='受信で画面が更新される')
    t.eq(counts(ed), want, '受信後の画面の数')
    t.eq(diff_totals(ed)['ExpertStandard.dat'], EXPERT, '送り元のExpertは変わらない')
    t.ok('Undoできません' not in toast(ed), '現在の難易度への受信はUndoできる（案内が出ない）')
    after_flat = diff_flat(ed, 'HardStandard.dat')
    _undo(ed)
    wait_until(ed, f"window._dbgApp.state().counts.notes==={HARD['notes']}", label='Undoで戻る')
    t.eq(counts(ed), HARD, 'Undo後の画面の数')
    t.eq(diff_flat(ed, 'HardStandard.dat'), diff_flat_before, 'Undo後のHardの中身（ノーツ・ボム・壁・アーク・ライト）= 受信前')
    t.eq(diff_totals(ed)['ExpertStandard.dat'], EXPERT, 'Undoしても送り元のExpertは変わらない')
    _redo(ed)
    wait_until(ed, f"window._dbgApp.state().counts.notes==={EXPERT['notes']}", label='Redoで再び反映')
    t.eq(diff_flat(ed, 'HardStandard.dat'), after_flat, 'Redo後 = 受信直後の中身')
    t.eq(counts(ed), want, 'Redo後の画面の数')
    t.no_errors()


def test_receive_lights_into_current_and_undo(t):
    '''Hardのメニュー「ライティングを受信←Expert」: Hardのライトが12になりノーツは元のまま。Undoで戻る'''
    ed = _open_rich(t)
    flat_before = diff_flat(ed, 'HardStandard.dat')
    diff_menu_open(ed, 'Hard')
    menu_pick(ed, 'ライティングを受信', '← Expert')
    menu_pick(ed, '⚠')
    wait_until(ed, f"window._dbgApp.state().counts.lights==={EXPERT['lights']}", label='ライト受信')
    t.eq(counts(ed), dict(HARD, lights=EXPERT['lights']), '受信後の画面の数')
    _undo(ed)
    wait_until(ed, f"window._dbgApp.state().counts.lights==={HARD['lights']}", label='Undoで戻る')
    t.eq(counts(ed), HARD, 'Undo後の画面の数')
    t.eq(diff_flat(ed, 'HardStandard.dat'), flat_before, 'Undo後のHardの中身 = 受信前')
    t.no_errors()


def test_receive_undo_restores_clip_structure(t):
    '''受信をUndoしたら、中身だけでなくクリップ（箱）の長さ・色・並びも受信前と同じプロジェクト内容に戻る'''
    ed = _open_rich(t)
    before = project(ed)
    diff_menu_open(ed, 'Hard')
    menu_pick(ed, 'ノーツを受信', '← Expert')
    menu_pick(ed, '⚠')
    wait_until(ed, f"window._dbgApp.state().counts.notes==={EXPERT['notes']}", label='受信')
    _undo(ed)
    wait_until(ed, f"window._dbgApp.state().counts.notes==={HARD['notes']}", label='Undo')
    ed.wait(0.3)
    t.eq(project(ed), before, 'Undo後のプロジェクト内容 = 受信前')
    t.no_errors()


def _clear_via_menu(ed, label, confirm='⚠'):
    diff_menu_open(ed, 'Hard')
    menu_pick(ed, label)
    menu_pick(ed, confirm)


def test_clear_notes_current_and_undo(t):
    '''Hardの「全ノーツを削除」: ノーツ・ボム・壁・アーク・チェーンが0になりライトは残る。Undoで全部戻る'''
    ed = _open_rich(t)
    before = project(ed)
    _clear_via_menu(ed, '全ノーツを削除')
    wait_until(ed, "window._dbgApp.state().counts.notes===0", label='全ノーツ削除')
    t.eq(counts(ed), dict(ZERO, lights=HARD['lights']), '削除後の数（ライトは残る）')
    t.eq(diff_totals(ed)['ExpertStandard.dat'], EXPERT, 'Expertは変わらない')
    _undo(ed)
    wait_until(ed, f"window._dbgApp.state().counts.notes==={HARD['notes']}", label='Undoで戻る')
    t.eq(counts(ed), HARD, 'Undo後の数')
    t.eq(project(ed), before, 'Undo後のプロジェクト内容 = 削除前')
    t.no_errors()


def test_clear_lights_current_and_undo(t):
    '''Hardの「全ライティングを削除」: ライトだけ0になりノーツ類は残る。Undoで戻る'''
    ed = _open_rich(t)
    before = project(ed)
    _clear_via_menu(ed, '全ライティングを削除')
    wait_until(ed, "window._dbgApp.state().counts.lights===0", label='全ライト削除')
    t.eq(counts(ed), dict(HARD, lights=0), '削除後の数（ノーツ類は残る）')
    _undo(ed)
    wait_until(ed, f"window._dbgApp.state().counts.lights==={HARD['lights']}", label='Undoで戻る')
    t.eq(project(ed), before, 'Undo後のプロジェクト内容 = 削除前')
    t.no_errors()


def test_clear_all_current_and_undo(t):
    '''Hardの「含まれる内容を全て削除」: ノーツもライトも0になる。Undoを（最大2回）押せば元に戻る'''
    ed = _open_rich(t)
    before = project(ed)
    _clear_via_menu(ed, '含まれる内容を全て削除')
    wait_until(ed, "window._dbgApp.state().counts.notes===0&&window._dbgApp.state().counts.lights===0", label='全て削除')
    t.eq(counts(ed), ZERO, '削除後の数')
    t.eq(diff_totals(ed).get('HardStandard.dat', ZERO), ZERO, '保存内容でもHardは空')
    for _ in range(2):   # 内部でノーツ→ライトの2回に分けて消すため、Undoは最大2回
        if counts(ed) == HARD:
            break
        _undo(ed)
        ed.wait(0.3)
    t.eq(counts(ed), HARD, 'Undo後の数')
    t.eq(project(ed), before, 'Undo後のプロジェクト内容 = 削除前')
    t.no_errors()


def test_clear_cancel(t):
    '''全消去の確認で「キャンセル」を選ぶと何も消えない'''
    ed = _open_rich(t)
    before = project(ed)
    diff_menu_open(ed, 'Hard')
    menu_pick(ed, '全ノーツを削除')
    menu_pick(ed, 'キャンセル')
    ed.wait(0.3)
    t.eq(project(ed), before, '内容は変わらない')
    t.eq(counts(ed), HARD, '画面の数も変わらない')
    t.no_errors()


def test_clear_other_diff(t):
    '''画面外のExpertを全消去（rt.diffClear）: Expertだけ空になり、表示中のHardは変わらない。Undoできない旨が案内される'''
    ed = _open_rich(t)
    ed.js("window._dbg.rt.diffClear('Expert','notes')")
    _wait_toast(ed, '全て削除しました')
    tot = diff_totals(ed)
    t.eq(tot['ExpertStandard.dat'], dict(ZERO, lights=EXPERT['lights']), 'Expertのノーツ類が0・ライトは残る')
    t.eq(tot['HardStandard.dat'], HARD, 'Hardは変わらない')
    t.eq(counts(ed), HARD, '表示中の数も変わらない')
    t.ok('Undoできません' in toast(ed), '画面外の難易度への操作はUndoできないと案内する')
    ed.js("window._dbg.rt.diffClear('Expert','lights')")
    wait_until(ed, "!!window._dbg.rt.diffCountsOf&&window._dbg.rt.diffCountsOf('Expert').l===0", label='Expertのライト削除')
    t.eq(diff_totals(ed).get('ExpertStandard.dat', ZERO), ZERO, 'Expertは完全に空（書き出し対象からも外れる）')
    t.no_errors()


def test_copy_survives_save_and_reopen(t):
    '''転送した結果は保存→開き直しでも保たれる（Easyへ丸ごと転送→保存内容を再適用→Easyの数がHardと同じ）'''
    ed = _open_rich(t)
    diff_menu_open(ed, 'Hard')
    menu_pick(ed, '丸ごと転送（ノーツ＋ライト）', '→ Easy')
    _wait_toast(ed, 'コピーしました')
    before = project(ed)
    ed.js("(async()=>{ const rt=window._dbg.rt; await rt.applyProject(JSON.parse(rt.buildProjectText())); return true; })()")
    after = project(ed)
    t.eq(after, before, '保存→開き直しで内容が一致')
    t.eq(diff_counts_from_project(after)['EasyStandard.dat'], HARD, 'Easyの数')
    t.no_errors()

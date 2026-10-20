"""古い形式のプロジェクトファイルを開いても譜面が消えないこと（2026-10-20）。

見本は今の版で保存した rich.nlmf を古い版の形へ書き換えて作る（old_format_helpers.variant・形の一覧は CLAUDE.md「古い形式のプロジェクトを開く」）。
形ごとに、開く → 難易度を切り替える → クリップから作り直す・NLE でクリップを分割して Undo・3Dで置いて Undo → 保存 → 開き直す、の各所で
ノーツ・ボム・壁・アーク・チェーン・ライト（v2/v3 の難易度）が1つも消えない・増えないことを確かめる。
「消えない」は2つ見る: 今見えている物（フラット）と、クリップの中身（保存して開き直すと見える物＝今の形はクリップの中身が正）。
あわせてクリップの並び（同じレーンで重ならない・レーンの数の中・ノーツのクリップにライトが無い・長さがある）も見る。"""
from old_format_helpers import extra, items, layout_problems, lost, variant   # e2e_nle を読み込み先に足すので nle_helpers より先に
from e2e_helpers import hover_3d, place_at, project, switch_diff, wait_until
from nle_helpers import clips, hover, nle_mouse, select
from project_helpers import fake, install_fake_fs, queue_open


def _open(ed, fname, text):
    install_fake_fs(ed)
    ed.js("document.getElementById('errToast').textContent=''")
    queue_open(ed, fname, text)
    hover_3d(ed)
    ed.key('o', ctrl=True)
    wait_until(ed, f"document.getElementById('errToast').textContent.includes({fname!r})", label=f'{fname} を開き終える')
    ed.wait(0.2)


def _check(fails, ed, want, label):
    """消えた・増えた物、クリップの並びのおかしな所を fails へ（全部の段階を見てから最後にまとめて失敗にする＝どこで消えるかが一度で分かる）"""
    pj = project(ed)
    got = items(pj)
    for what, res in (('見えている物（フラット）から消えた', lost(want, got, 'flat')),
                      ('クリップの中に無い（開き直すと消える）', lost(want, got, 'clips')),
                      ('クリップの中身が増えた', extra(want, got, 'clips'))):
        if res:
            fails.append(f'{label}: {what} {res}')
    for p in layout_problems(pj):
        fails.append(f'{label}: {p}')


def _split_undo(ed):
    """NLE で今の難易度のノーツのクリップ（一番左）を拍6で C で分割 → Undo（クリップから作り直す操作）"""
    c0 = clips(ed, 'n')[0]
    n0 = len(clips(ed, 'n'))
    select(ed, c0)
    hover(ed, 6, 'n', c0['track'])
    ed.key('c')
    wait_until(ed, f"window._dbgApp.nle().clips.filter(c=>c.lk==='n').length==={n0 + 1}", label='C で分割')
    nle_mouse(ed)
    ed.key('z', ctrl=True)
    wait_until(ed, f"window._dbgApp.nle().clips.filter(c=>c.lk==='n').length==={n0}", label='分割の Undo')


def _roundtrip(t, name):
    fname, text, want = variant(name)
    fails = []
    ed = t.fresh()
    _open(ed, fname, text)
    t.eq(ed.js("window._dbgApp.dirty().lamp"), False, '開いた直後は未保存でない（直したのは中身の置き場所だけ）')
    _check(fails, ed, want, '開いた直後')
    switch_diff(ed, 'Expert')
    _check(fails, ed, want, 'Expert へ切り替え')
    switch_diff(ed, 'Hard')
    _check(fails, ed, want, 'Hard へ戻す')
    ed.js("window._dbg.rt.compileLayersToFlat()")   # NLE の操作の後と同じ（クリップから作り直す）
    _check(fails, ed, want, 'クリップから作り直す')
    _split_undo(ed)
    _check(fails, ed, want, 'NLE で分割して Undo')
    n0 = place_at(ed, 1, 1)   # 3Dで置く（クリップへ書き戻す）→ Undo
    hover_3d(ed)
    ed.key('z', ctrl=True)
    wait_until(ed, f"window._dbgApp.state().counts.notes==={n0}", label='置いたノーツの Undo')
    ed.wait(0.2)
    _check(fails, ed, want, '3Dで置いて Undo')
    hover_3d(ed)
    ed.key('s', ctrl=True)
    wait_until(ed, "__fake.writes.length>=1", label='保存')
    saved = fake(ed)['writes'][0]['text']
    ed = t.fresh()
    _open(ed, 'saved.nlmf', saved)
    _check(fails, ed, want, '保存して開き直す')
    switch_diff(ed, 'Expert')
    _check(fails, ed, want, '開き直して Expert')
    t.ok(not fails, '\n'.join(fails))
    t.no_errors()


def test_old_bsnm(t):
    '''format・拡張子が .bsnm（中身は今の形）'''
    _roundtrip(t, 'bsnm')


def test_old_bslm(t):
    '''format・拡張子が .bslm（中身は今の形）'''
    _roundtrip(t, 'bslm')


def test_old_v2_bare(t):
    '''保存形式 v2 で、レーンの数・L/S/M・テンポパート・表示位置・INFOのノード・クリップの色/id 等の無い古い版の形'''
    _roundtrip(t, 'v2_bare')


def test_old_v1_full(t):
    '''保存形式 v1（version 無し・オブジェクトの形）: トップレベルと難易度ごとの両方にクリップ'''
    _roundtrip(t, 'v1_full')


def test_old_v1_top(t):
    '''保存形式 v1: クリップはトップレベルだけ（他の難易度はフラットだけ）'''
    _roundtrip(t, 'v1_top')


def test_old_v1_flat(t):
    '''保存形式 v1: クリップが無い（フラットだけ）'''
    _roundtrip(t, 'v1_flat')


def test_old_v1_node(t):
    '''保存形式 v1: ノードの画面の頃の形（長さ・種類の無いクリップ1つに、ノーツ系とライトの両方）'''
    _roundtrip(t, 'v1_node')


def test_old_v1_node2(t):
    '''保存形式 v1: ノードの画面の頃の形（長さの無いクリップが2つ＝前のクリップは次の頭まで）'''
    _roundtrip(t, 'v1_node2')


def test_old_v2_noclips(t):
    '''保存形式 v2 で、今でない難易度にクリップが無い（フラットだけ）'''
    _roundtrip(t, 'v2_noclips')


def test_old_v2_orphans(t):
    '''保存形式 v2 で、フラットにだけある物（どのクリップの範囲にも無い）はクリップへ入る'''
    _roundtrip(t, 'v2_orphans')


def test_old_v2_stale_not_revived(t):
    '''保存形式 v2 で、クリップの範囲の中なのに中身に無い物（消した物がフラットに残った）は戻さない＝クリップの中身が正（今までどおり）'''
    _roundtrip(t, 'v2_stale')


def test_current_file_unchanged(t):
    '''今の形のファイル（rich.nlmf）は、開いた後の保存の中身が開いたファイルと同じ（古い形式の直しは何もしない）'''
    import json
    from old_format_helpers import RICH
    text = RICH.read_text(encoding='utf-8')
    ed = t.fresh()
    _open(ed, 'rich.nlmf', text)
    want = json.loads(text)
    got = project(ed)
    for k in ('savedAt', 'view', 'coverData'):   # 保存した時刻・表示位置（開いた時の画面で決まる）・カバー画像（無い）は比べない
        want.pop(k, None)
        got.pop(k, None)
    t.eq(got['difficulties'], want['difficulties'], '難易度ごとのフラット・クリップ（中身・並び）が開いたファイルと同じ')
    t.no_errors()

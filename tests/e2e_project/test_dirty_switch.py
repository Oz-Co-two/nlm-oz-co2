"""未保存の判定: 保存した後に難易度を切り替えただけでは未保存にならない（2026-10-27）。
以前は、保存した時と違う難易度を開いているだけで「未保存有り」のランプが点いた（ノーツ・ライトの配線＝今の難易度のクリップの id を比べていた）。
同じく、まだ無い難易度を開いた時（空の退避ができる）・置いた物の並びがクリップの順に作り直された時（難易度を切り替えて戻った時）も点いていた。
入力は本物のマウス・キー（譜面チェックの拍・難易度のボタン・数字キー）。保存のファイル選択は偽物（project_helpers.install_fake_fs）"""
import json

from e2e_helpers import dirty, hover_3d, open_fixture, place_at, state, switch_diff, wait_until
from project_helpers import _click_el, install_fake_fs

DONE = ("(()=>{const p=document.getElementById('mcPanel');return !!p&&p.style.display!=='none'"
        "&&!p.querySelector('.mcRerun').disabled&&p.querySelector('.mcBody').children.length>0})()")


def _save(ed, n=1):
    """Ctrl+S で保存し、ランプが消えるまで待つ"""
    hover_3d(ed)
    ed.key('s', ctrl=True)
    wait_until(ed, f"__fake.writes.length>={n}", label=f'{n}回目の保存')
    wait_until(ed, "window._dbgApp.dirty().lamp===false", label='保存後にランプが消える')


def _setup(t, fx='rich'):
    ed = open_fixture(t, fx)
    install_fake_fs(ed)
    ed.js("document.getElementById('errToast').style.display='none'")
    return ed


def _clean(t, ed, label):
    """操作が落ち着いた後（判定は0.5秒後）にランプが消えたまま・保存した時と同じ内容"""
    ed.wait(0.7)
    d = dirty(ed)
    if not d['same']:   # 失敗した時に何が違ったかを出す
        p = ed.js("window._dbgApp.sigPair()")
        a, b = json.loads(p['saved']), json.loads(p['now'])
        t.info(f"{label}: 違う項目 " + ", ".join(k for k in sorted(set(a) | set(b)) if a.get(k) != b.get(k)))
    t.eq(d['lamp'], False, f'{label}: ランプ')
    t.eq(d['same'], True, f'{label}: 保存した時と同じ内容')


def _open_mapcheck(ed, tab):
    """INFO 画面の「譜面チェック」を押して結果を出し、tab（'mc'＝BS Map Check / 'bl'＝NLM版 BL評価リスト）を開く"""
    n = ed.js("window._dbgApp.nleScreen(0)")
    ed.move(n['left'] + n['w'] * 0.6, n['lanes'] + 40)
    ed.key('Tab')   # NLE の上で Tab＝INFO へ
    wait_until(ed, "window._dbgApp.view()==='info'", label='INFO画面へ')
    _click_el(ed, '#iMapCheck')
    wait_until(ed, DONE, timeout=10, label='チェック結果の表示')
    if ed.js("document.getElementById('mcPanel').classList.contains('blMode')") != (tab == 'bl'):
        _click_el(ed, f'#mcPanel .mcTab[data-tab="{tab}"]')
        wait_until(ed, f"document.getElementById('mcPanel').classList.contains('blMode')==={json.dumps(tab == 'bl')}", label='タブの切り替え')
        wait_until(ed, DONE, label='タブの表示')


def _click_chip(ed, ref):
    """拍のチップ（data-ref）を見える所までスクロールして本物のマウスで押す"""
    sel = f"#mcPanel .mcBeat[data-ref={json.dumps(ref)}]"
    ed.js(f"(()=>{{const c=document.querySelector({json.dumps(sel)});const d=c.closest('details');if(d&&!d.open)d.open=true;"
          f"c.scrollIntoView({{block:'center'}});return true}})()")
    _click_el(ed, sel)


def _jump_other_diff(t, ed, label):
    """チェック結果の拍を、今と違う難易度へ飛ぶ物が見つかるまで順に押す（同じ難易度の拍を押した時も未保存にならないこと）。飛んだ先の難易度を返す"""
    start = state(ed)['diff']
    refs = ed.js("[...document.querySelectorAll('#mcPanel .mcBeat')].map(c=>c.dataset.ref)")
    t.ok(refs, f'{label}: 拍のチップがある')
    for ref in refs:
        _click_chip(ed, ref)
        ed.wait(0.3)
        if state(ed)['diff'] != start:
            wait_until(ed, "window._dbgApp.dirty().inputSinceBase===true", label='操作の記録')
            return state(ed)['diff']
        _clean(t, ed, f'{label}: 同じ難易度の拍 {ref}')
    raise AssertionError(f'{label}: 別の難易度へ飛ぶ拍が見つかりません（{refs}）')


def test_dirty_mapcheck_jump_other_diff(t):
    '''保存した直後に、譜面チェックの拍（BS Map Check のタブ・NLM版 BL評価リストのタブ）で別の難易度へ飛んでも未保存にならない。その後に1つ置くと未保存になる'''
    ed = _setup(t)
    _save(ed)
    _open_mapcheck(ed, 'mc')
    _clean(t, ed, 'チェックを開いた後')
    to = _jump_other_diff(t, ed, 'BS Map Check')
    t.eq(to, 'ExpertStandard.dat', 'BS Map Check の拍で Expert へ')
    _clean(t, ed, 'BS Map Check の拍で Expert へ飛んだ後')
    # 同じパネルの2つ目のタブ（飛んだ後もパネルは開いたまま）
    _click_el(ed, '#mcPanel .mcTab[data-tab="bl"]')
    wait_until(ed, "document.getElementById('mcPanel').classList.contains('blMode')", label='BL評価リストのタブ')
    wait_until(ed, DONE, label='BL評価リストの表示')
    to = _jump_other_diff(t, ed, 'BL評価リスト')
    t.eq(to, 'HardStandard.dat', 'BL評価リストの拍で Hard へ戻る')
    _clean(t, ed, 'BL評価リストの拍で Hard へ飛んだ後')
    # 本当の編集は今までどおり点く（チェックのパネルを閉じてから3Dで置く。(3,2) は rich の Expert の拍 0〜8 で空いている）
    _click_el(ed, '#mcPanel .mcClose')
    switch_diff(ed, 'Expert')
    _clean(t, ed, '数字キーで Expert へ')
    place_at(ed, 3, 2)
    wait_until(ed, "window._dbgApp.dirty().lamp===true", label='置いた後は未保存')
    t.no_errors()


def test_dirty_diff_button_switch_after_save(t):
    '''保存した直後に難易度のボタン（本物のクリック）で切り替えても未保存にならない。その後に1つ置くと未保存・Undo で消える'''
    ed = _setup(t)
    _save(ed)
    _click_el(ed, "#diffBar .dfSeg[data-dn='Expert']")
    wait_until(ed, "window._dbgApp.state().diff==='ExpertStandard.dat'", label='Expert へ')
    _clean(t, ed, 'ボタンで Expert へ')
    place_at(ed, 3, 2)
    wait_until(ed, "window._dbgApp.dirty().lamp===true", label='置いた後は未保存')
    hover_3d(ed)
    ed.key('z', ctrl=True)
    wait_until(ed, "window._dbgApp.dirty().lamp===false", label='Undo で保存した時に戻る')
    # 保存した時の難易度（Hard）以外で保存→Hard へ戻しても点かない
    place_at(ed, 3, 2)
    _save(ed, 2)
    _click_el(ed, "#diffBar .dfSeg[data-dn='Hard']")
    wait_until(ed, "window._dbgApp.state().diff==='HardStandard.dat'", label='Hard へ')
    _clean(t, ed, 'Expert で保存した後にボタンで Hard へ')
    t.no_errors()


def test_dirty_visit_empty_diff(t):
    '''保存した直後に、まだ無い難易度（rich の Easy）を開いて戻っても未保存にならない（空の退避ができるだけ）。その後に置くと未保存'''
    ed = _setup(t)
    _save(ed)
    switch_diff(ed, 'Easy')
    _clean(t, ed, '数字キーで空の Easy へ')
    switch_diff(ed, 'Hard')
    _clean(t, ed, 'Hard へ戻った後')
    place_at(ed, 3, 2)
    wait_until(ed, "window._dbgApp.dirty().lamp===true", label='置いた後は未保存')
    t.no_errors()


def test_dirty_switch_back_reorders_flat(t):
    '''ノーツのクリップが2つある難易度で、置いた後に保存→別の難易度へ行って戻ると、物の並びはクリップの順に作り直される。並びが変わっただけでは未保存にならない'''
    ed = _setup(t)
    # Hard のノーツのクリップの後ろの半分を、同じ範囲の上のレーンの新しいクリップ（クリップの並びの先頭）へ移した形で開き直す
    ed.js("""(async()=>{ const rt=window._dbg.rt; const pj=JSON.parse(rt.buildProjectText());
      const d=pj.difficulties['hardstandard.dat']; const a=d.sections.find(s=>s.lk==='n');
      const b=JSON.parse(JSON.stringify(a)); b.id='nTop'; b.track=1; b.label='Top';
      const ns=a.content.notes; a.content.notes=ns.filter(x=>x[0]<5); b.content.notes=ns.filter(x=>x[0]>=5);
      for(const k of ['bombs','walls','arcs','chains']) b.content[k]=[];
      d.sections.unshift(b); await rt.applyProject(pj); return true; })()""")
    install_fake_fs(ed)
    place_at(ed, 0, 0)   # 一番上のレーン＝先頭のクリップへ入る（フラットでは末尾に足される）
    before = ed.js("window._dbgApp.notes().notes.map(n=>n.beat)")
    _save(ed)
    switch_diff(ed, 'Expert')
    _clean(t, ed, 'Expert へ')
    switch_diff(ed, 'Hard')
    after = ed.js("window._dbgApp.notes().notes.map(n=>n.beat)")
    t.ok(before != after and sorted(before) == sorted(after), f'並びだけが変わった（前提）: {before} → {after}')
    _clean(t, ed, 'Hard へ戻った後（並びが変わった）')
    place_at(ed, 1, 0)
    wait_until(ed, "window._dbgApp.dirty().lamp===true", label='置いた後は未保存')
    t.no_errors()

"""譜面チェック（BeatLeader基準）が rich で例外なく動く・結果のパネルは今の難易度の分だけ開き、別の難易度の拍は確かめてから切り替える"""
import json

from e2e_helpers import open_fixture, state, switch_diff, wait_until


def test_mapcheck_input_rich(t):
    '''rich: 譜面チェックの入力（書き出しと同じ内容）に2難易度・曲情報・音源の長さが入る'''
    ed = open_fixture(t, 'rich')
    p = ed.js("window._dbgApp.mapCheckInput()")
    t.ok(not p.get('error'), f"入力の作成に失敗: {p.get('error')}")
    t.eq([d['difficulty'] for d in p['diffs']], ['Hard', 'Expert'], '難易度')
    t.eq([(d['njs'], d['njsOffset']) for d in p['diffs']], [(14, 0), (17, -0.25)], 'NJS/オフセット')
    t.eq(p['info'], {'bpm': 120, 'environment': 'DefaultEnvironment', 'previewStart': 4, 'previewDuration': 6}, '曲情報')
    t.eq(p['meta']['songName'], 'リッチ テスト曲', '曲名')
    t.ok(abs((p['audioDuration'] or 0) - 16) < 0.05, f"音源の長さ: {p['audioDuration']}")
    t.no_errors()


def test_mapcheck_run_rich(t):
    '''rich: BS Map Check の判定と NLM版BL評価リストが、どの項目も例外（Check failed）を出さずに最後まで動く'''
    ed = open_fixture(t, 'rich')
    r = ed.js("""(async()=>{
      const mc=await import('./js/mapcheck/mapcheck.js'), bl=await import('./js/mapcheck/blcriteria.js');
      const p=await window._dbgApp.mapCheckInput();
      const res=mc.runMapCheck(p), b=bl.runBlCriteria(p,res);
      return {diffs:res.diffs.map(d=>({d:d.difficulty,error:d.error||null,keys:d.results.map(x=>x.key+':'+x.status)})),
        general:res.general.map(x=>x.key),
        blFailed:(b.rules||[]).flatMap(r=>r.findings.filter(f=>f.key==='failed').map(f=>r.id+' '+JSON.stringify(f.vars||{}))),
        blRules:(b.rules||[]).length, blError:b.error||null};
    })()""")
    t.eq([d['d'] for d in r['diffs']], ['Hard', 'Expert'], '判定した難易度')
    for d in r['diffs']:
        t.eq(d['error'], None, f"{d['d']} の読み込みエラー")
        t.eq([k for k in d['keys'] if k.startswith('checkFailed')], [], f"{d['d']} で例外になった判定")
    t.eq(r['blError'], None, 'BL評価リストのエラー')
    t.ok(r['blRules'] > 0, 'BL評価リストの項目がある')
    t.eq(r['blFailed'], [], 'BL評価リストで例外になった項目')
    t.info('Hard: ' + ', '.join(r['diffs'][0]['keys']))
    t.info('Expert: ' + ', '.join(r['diffs'][1]['keys']))
    t.no_errors()


def test_mapcheck_panel_rich(t):
    '''rich: INFO画面の「譜面チェック」ボタンで結果パネルが開き、2つのタブとも描画される'''
    ed = open_fixture(t, 'rich')
    n = ed.js("window._dbgApp.nleScreen(0)")
    hx, hy = n['left'] + n['w'] * 0.6, n['lanes'] + 40
    ed.move(hx, hy); ed.key('Tab')   # NLEの上でTab=INFOへ
    wait_until(ed, "window._dbgApp.view()==='info'", label='INFO画面へ')
    b = wait_until(ed, "(()=>{const e=document.getElementById('iMapCheck');const r=e&&e.getBoundingClientRect();"
                       "return r&&r.width>0?{x:r.left+r.width/2,y:r.top+r.height/2}:null})()", label='譜面チェックボタン')
    ed.click(b['x'], b['y'])
    done = ("(()=>{const p=document.getElementById('mcPanel');return !!p&&p.style.display!=='none'"
            "&&!p.querySelector('.mcRerun').disabled&&p.querySelector('.mcBody').children.length>0})()")
    wait_until(ed, done, timeout=10, label='チェック結果の表示')
    t.eq(ed.js("document.querySelectorAll('#mcPanel .mcErr').length"), 0, 'エラー表示')
    secs = ed.js("[...document.querySelectorAll('#mcPanel .mcSec>summary')].map(s=>s.firstChild.textContent.trim())")
    t.eq(len(secs), 3, f'節の数（全体＋2難易度）: {secs}')
    # 2つ目のタブ（NLM版 BL評価リスト）
    tb = ed.js("(()=>{const r=document.querySelector('#mcPanel .mcTab[data-tab=\"bl\"]').getBoundingClientRect();return {x:r.left+r.width/2,y:r.top+r.height/2}})()")
    ed.click(tb['x'], tb['y'])
    wait_until(ed, "document.getElementById('mcPanel').classList.contains('blMode')", label='BL評価リストのタブ')
    wait_until(ed, done, label='BL評価リストの表示')
    t.eq(ed.js("document.querySelectorAll('#mcPanel .mcErr').length"), 0, 'BL評価リストのエラー表示')
    t.no_errors()


# ---- 複数の難易度: 今の難易度の分だけ開く・別の難易度の拍は確かめてから切り替える（2026-11-03・利用者の要望） ----
DONE = ("(()=>{const p=document.getElementById('mcPanel');return !!p&&p.style.display!=='none'"
        "&&!p.querySelector('.mcRerun').disabled&&p.querySelector('.mcBody').children.length>0})()")
DLG = "document.querySelector('#dirtyDlg')"


def _open_panel(ed):
    n = ed.js("window._dbgApp.nleScreen(0)")
    ed.move(n['left'] + n['w'] * 0.6, n['lanes'] + 40); ed.key('Tab')   # NLEの上でTab=INFOへ
    wait_until(ed, "window._dbgApp.view()==='info'", label='INFO画面へ')
    _click(ed, '#iMapCheck', '譜面チェックボタン')
    wait_until(ed, DONE, timeout=10, label='チェック結果の表示')


def _click(ed, sel, label):
    """見えている要素を本物のマウスで押す（パネルの中なら見える所までスクロール。閉じた見出しの中の物は見えないので押せない）"""
    p = wait_until(ed, f"(()=>{{const e=document.querySelector({json.dumps(sel)});if(!e||!e.getClientRects().length)return null;"
                       f"e.scrollIntoView({{block:'nearest'}});const r=e.getBoundingClientRect();"
                       f"return {{x:r.left+Math.min(r.width/2,24),y:r.top+r.height/2}}}})()", label=label)
    ed.click(p['x'], p['y'])


def _secs(ed):
    """BS Map Check のタブの見出し: [data-sec, 開いているか, 「編集中」の札があるか, 数の札の数]"""
    return ed.js("[...document.querySelectorAll('#mcPanel details.mcSec')].map(d=>[d.dataset.sec,d.open,"
                 "!!d.querySelector(':scope>summary .mcCurTag'),d.querySelectorAll(':scope>summary .mcCnt').length])")


def _in_view(ed, sel):
    """パネルの本文の見えている所にあるか（閉じた見出しの中・スクロールの外＝False）"""
    return ed.js(f"(()=>{{const c=document.querySelector({json.dumps(sel)});if(!c||!c.getClientRects().length)return false;"
                 f"const b=c.closest('.mcBody').getBoundingClientRect(),r=c.getBoundingClientRect();"
                 f"return r.top>=b.top-1&&r.bottom<=b.bottom+1}})()")


def _dialog(ed):
    """確認の画面の文とボタン（無ければ None）"""
    return ed.js(f"(d=>d?{{msg:d.querySelector('.ddMsg').textContent,btns:[...d.querySelectorAll('.ddBtns button')].map(b=>b.textContent)}}:null)({DLG})")


def _cur_chips(ed):
    return ed.js("[...document.querySelectorAll('#mcPanel .mcBeat.cur')].map(e=>e.dataset.ref)")


def test_mapcheck_tabs_keep_open(t):
    '''タブを行き来しても、再チェックしても、自分で開け閉めした状態は保つ（BS Map Check: 全体を閉じ Expert を開く／BL評価リスト: 節を1つ閉じる）。
    難易度を切り替えると BS Map Check は既定（今の難易度だけ開く）に戻り、BL評価リストの節（難易度の区切りではない）はそのまま（2026-11-15。
    以前は描き直す前の中身から開閉を読んでいて、別のタブから戻ると既定に戻っていた）'''
    ed = open_fixture(t, 'rich')
    _open_panel(ed)
    _click(ed, '#mcPanel details[data-sec="mc:gen"]>summary', '全体の見出し（閉じる）')
    _click(ed, '#mcPanel details[data-sec="mc:Expert"]>summary', 'Expert の見出し（開く）')
    want = [['mc:gen', False], ['mc:Hard', True], ['mc:Expert', True]]
    wait_until(ed, f"JSON.stringify([...document.querySelectorAll('#mcPanel details.mcSec')].map(d=>[d.dataset.sec,d.open]))==={json.dumps(json.dumps(want, separators=(',', ':')))}",
               label='全体を閉じ Expert を開く')
    _click(ed, '#mcPanel .mcTab[data-tab="bl"]', 'BL評価リストのタブ')
    wait_until(ed, "document.getElementById('mcPanel').classList.contains('blMode')", label='BL評価リストのタブ')
    wait_until(ed, DONE, label='BL評価リストの表示')
    bl = ed.js("document.querySelector('#mcPanel details.blSec[open]').dataset.sec")
    bsel = f'#mcPanel details.blSec[data-sec="{bl}"]'
    _click(ed, bsel + '>summary', f'BL評価リストの節 {bl}（閉じる）')
    wait_until(ed, f"!document.querySelector({json.dumps(bsel)}).open", label='節を閉じる')
    _click(ed, '#mcPanel .mcTab[data-tab="mc"]', 'BS Map Check のタブへ戻る')
    wait_until(ed, "!document.getElementById('mcPanel').classList.contains('blMode')", label='BS Map Check のタブ')
    t.eq([x[:2] for x in _secs(ed)], want, 'タブを行き来しても BS Map Check の開け閉めを保つ')
    _click(ed, '#mcPanel .mcTab[data-tab="bl"]', 'BL評価リストのタブ（2回目）')
    wait_until(ed, "document.getElementById('mcPanel').classList.contains('blMode')", label='BL評価リストのタブ（2回目）')
    t.eq(ed.js(f"document.querySelector({json.dumps(bsel)}).open"), False, 'タブを行き来しても BL評価リストの節の開け閉めを保つ')
    _click(ed, '#mcPanel .mcTab[data-tab="mc"]', 'BS Map Check のタブ（2回目）')
    wait_until(ed, "!document.getElementById('mcPanel').classList.contains('blMode')", label='BS Map Check のタブ（2回目）')
    _click(ed, '#mcPanel .mcRerun', '再チェック')
    wait_until(ed, DONE, label='再チェックの結果')
    t.eq([x[:2] for x in _secs(ed)], want, '再チェックしても開け閉めを保つ')
    switch_diff(ed, 'Expert')
    wait_until(ed, "!document.querySelector('#mcPanel details[data-sec=\"mc:Hard\"]').open", label='Expert へ切り替えて開き直す')
    t.eq([x[:2] for x in _secs(ed)], [['mc:gen', True], ['mc:Hard', False], ['mc:Expert', True]], '難易度を切り替えると既定に戻る（全体も開く）')
    _click(ed, '#mcPanel .mcTab[data-tab="bl"]', 'BL評価リストのタブ（3回目）')
    wait_until(ed, "document.getElementById('mcPanel').classList.contains('blMode')", label='BL評価リストのタブ（3回目）')
    t.eq(ed.js(f"document.querySelector({json.dumps(bsel)}).open"), False, '難易度を切り替えても BL評価リストの節の開け閉めはそのまま')
    t.no_errors()


def test_mapcheck_other_diff(t):
    '''複数の難易度（rich: Hard を開いている・Expert もある）: BS Map Check のタブは全体と今の難易度だけを開き（見出しに「編集中」）、
    別の難易度は見出しの数だけ見せて閉じる。別の難易度の拍は「切り替えて表示しますか？」で確かめ、キャンセル（Esc も）なら何もしない。
    切り替えると、その難易度を開いて元の難易度を閉じ、押したチップに印を付けて見える所へ出す。数字キーで切り替えても開き直す。
    今の難易度の拍は確かめずに移動。BL評価リストは別の難易度の所見の行（難易度・文・数）を残して拍だけ隠し、行を押すと出す。'''
    ed = open_fixture(t, 'rich')
    t.eq(state(ed)['diff'], 'HardStandard.dat', '前提: Hard を開いている')
    _open_panel(ed)
    s = _secs(ed)
    t.eq([x[:3] for x in s], [['mc:gen', True, False], ['mc:Hard', True, True], ['mc:Expert', False, False]],
         '全体と今の難易度（Hard・編集中の札）だけ開き、Expert は閉じる')
    t.ok(s[2][3] > 0, f'閉じた Expert の見出しにも数が見える: {s}')
    t.eq(ed.js("document.querySelector('#mcPanel .mcCurTag').textContent"), '編集中', '札の文')
    ref = ed.js("document.querySelector('#mcPanel details[data-sec=\"mc:Expert\"] .mcBeat').dataset.ref")
    chip = f'#mcPanel .mcBeat[data-ref="{ref}"]'
    t.eq(_in_view(ed, chip), False, '閉じた Expert の拍は見えない')

    # 見出しを押して開き、Expert の拍 → 確かめる（キャンセル・Esc は何もしない）
    _click(ed, '#mcPanel details[data-sec="mc:Expert"]>summary', 'Expert の見出し')
    wait_until(ed, "document.querySelector('#mcPanel details[data-sec=\"mc:Expert\"]').open", label='Expert を開く')
    _click(ed, chip, 'Expert の拍')
    wait_until(ed, f"!!{DLG}", label='切り替えの確認')
    t.eq(_dialog(ed), {'msg': 'この結果は Expert の物です（今開いているのは Hard）。\nExpert に切り替えて表示しますか？',
                       'btns': ['Expert に切り替える', 'キャンセル']}, '確認の文とボタン')
    _click(ed, '#dirtyDlg .ddBtns button:not(.pri)', 'キャンセル')
    wait_until(ed, f"!{DLG}", label='確認を閉じる')
    ed.wait(0.3)
    t.eq((state(ed)['diff'], _cur_chips(ed)), ('HardStandard.dat', []), 'キャンセル: 切り替えず、チップに印も付けない')
    _click(ed, chip, 'Expert の拍（もう一度）')
    wait_until(ed, f"!!{DLG}", label='切り替えの確認（2回目）')
    ed.key('Escape')
    wait_until(ed, f"!{DLG}", label='Esc で閉じる')
    ed.wait(0.3)
    t.eq(state(ed)['diff'], 'HardStandard.dat', 'Esc: 切り替えない')

    # はい → Expert へ切り替えて選ぶ。Expert を開き Hard を閉じる・押したチップは見える所に印付き
    _click(ed, chip, 'Expert の拍（3回目）')
    wait_until(ed, f"!!{DLG}", label='切り替えの確認（3回目）')
    _click(ed, '#dirtyDlg .ddBtns button.pri', 'Expert に切り替える')
    wait_until(ed, "(s=>s.diff==='ExpertStandard.dat'&&s.sel===1)(window._dbgApp.state())", label='Expert へ切り替えて選ぶ')
    t.eq([x[:3] for x in _secs(ed)], [['mc:gen', True, False], ['mc:Hard', False, False], ['mc:Expert', True, True]],
         '切り替えた後: Expert を開き（編集中）、Hard を閉じる')
    t.eq(_cur_chips(ed), [ref], '押したチップに印')
    t.eq(_in_view(ed, chip), True, '押したチップが見える所にある')

    # 数字キーで Hard へ戻す → Hard を開き Expert を閉じる（手で開けた状態は持ち越さない）
    switch_diff(ed, 'Hard')
    wait_until(ed, "document.querySelector('#mcPanel details[data-sec=\"mc:Hard\"]').open", label='Hard を開き直す')
    t.eq([x[:3] for x in _secs(ed)], [['mc:gen', True, False], ['mc:Hard', True, True], ['mc:Expert', False, False]], '数字キーで Hard へ: 開き直す')

    # 今の難易度（Hard）の拍は確かめずに移動
    href = ed.js("document.querySelector('#mcPanel details[data-sec=\"mc:Hard\"] .mcBeat').dataset.ref")
    _click(ed, f'#mcPanel .mcBeat[data-ref="{href}"]', 'Hard の拍')
    wait_until(ed, f"window._dbgApp.state().sel===1&&!{DLG}", label='確かめずに選ぶ')
    t.eq((state(ed)['diff'], _cur_chips(ed)), ('HardStandard.dat', [href]), 'Hard のまま・押したチップに印')

    # BL評価リスト: 別の難易度（Expert）の拍のある所見は行だけ・押すと拍を出す
    _click(ed, '#mcPanel .mcTab[data-tab="bl"]', 'BL評価リストのタブ')
    wait_until(ed, "document.getElementById('mcPanel').classList.contains('blMode')", label='BL評価リストのタブ')
    wait_until(ed, DONE, label='BL評価リストの表示')
    rows = ed.js("[...document.querySelectorAll('#mcPanel .blF')].filter(f=>f.querySelector('.blDiff')).map(f=>({oref:f.dataset.oref||null,"
                 "diff:f.querySelector('.blDiff').textContent,cur:f.querySelector('.blDiff').classList.contains('cur'),"
                 "other:f.classList.contains('blOther'),chips:f.querySelectorAll('.mcBeat').length,n:!!f.querySelector('.mcN')}))")
    other = [r for r in rows if r['other']]
    t.ok(other, f'前提: rich の BL評価リストに Expert の拍のある所見がある（判定が変わったら素材を見直す）: {rows}')
    t.ok(all(r['diff'] == 'Expert' and not r['cur'] and r['chips'] == 0 and r['n'] for r in other), f'Expert の所見は行と数だけ・拍は隠す: {other}')
    t.ok(all(r['cur'] for r in rows if r['diff'] == 'Hard'), 'Hard の所見は「今の難易度」の印')
    t.ok(any(r['chips'] > 0 for r in rows if r['diff'] == 'Hard'), 'Hard の所見は拍を出したまま')
    row = f'#mcPanel .blF.blOther[data-oref="{other[0]["oref"]}"]'
    msg = row + '>span:not(.blDiff):not(.mcN)'
    _click(ed, msg, 'Expert の所見の行')
    wait_until(ed, f"(f=>!!f&&f.classList.contains('open')&&f.querySelectorAll('.mcBeat').length>0)(document.querySelector({json.dumps(row)}))", label='拍を出す')
    _click(ed, msg, 'Expert の所見の行（もう一度）')
    wait_until(ed, f"(f=>!!f&&!f.classList.contains('open')&&f.querySelectorAll('.mcBeat').length===0)(document.querySelector({json.dumps(row)}))", label='拍を隠す')
    _click(ed, msg, 'Expert の所見の行（3回目）')
    bchip = wait_until(ed, f"(c=>c?c.dataset.ref:null)(document.querySelector({json.dumps(row + ' .mcBeat')}))", label='拍が出る')
    bsel = f'#mcPanel .mcBeat[data-ref="{bchip}"]'
    _click(ed, bsel, 'Expert の所見の拍')
    wait_until(ed, f"!!{DLG}", label='切り替えの確認（BL評価リスト）')
    _click(ed, '#dirtyDlg .ddBtns button.pri', 'Expert に切り替える')
    wait_until(ed, "(s=>s.diff==='ExpertStandard.dat'&&s.sel>=1)(window._dbgApp.state())", label='Expert へ切り替える')
    t.eq(_cur_chips(ed), [bchip], 'BL評価リストでも押したチップに印')
    t.eq(_in_view(ed, bsel), True, '押したチップが見える所にある')
    t.ok(ed.js("[...document.querySelectorAll('#mcPanel .blF.blOther .blDiff')].every(d=>d.textContent==='Hard')"), '切り替えた後は Hard の所見が閉じる側')
    t.no_errors()

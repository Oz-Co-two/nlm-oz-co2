"""譜面チェック（BeatLeader基準）が rich で例外なく動く"""
from e2e_helpers import open_fixture, wait_until


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

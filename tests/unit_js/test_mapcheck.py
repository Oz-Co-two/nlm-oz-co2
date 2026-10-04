"""js/mapcheck/mapcheck.js（runMapCheck）の単体テスト。問題の無い譜面と、違反を1つ仕込んだ譜面を比べる。"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from unitjs_helpers import run_js

HEAD = "const { runMapCheck } = await import('/js/mapcheck/mapcheck.js');\n"
# 「ランク不可・エラー」だけを取り出す（info=参考情報・warn=NJS高め等の注意は基準の譜面にも出るので数えない）
SEV = "const sev = r => [...r.general, ...r.diffs[0].results].filter(x => x.status === 'rank' || x.status === 'error').map(x => x.key);\n"


def _run(t, body):
    ed = t.ed
    return run_js(ed, HEAD + SEV + body)


def test_clean_map(t):
    '''問題の無い譜面では、ランク不可・エラーが1つも出ない'''
    t.fresh()
    r = _run(t, "return { sev: sev(runMapCheck(P(base()))), err: runMapCheck(P(base())).diffs[0].error || null };")
    t.eq(r['err'], None, '検査が例外で止まっていない')
    t.eq(r['sev'], [], '違反なし')
    t.no_errors()


def test_zero_obstacle(t):
    '''幅0の壁を置くと zeroObstacle（エラー）が出る'''
    r = _run(t, "const j = base(); j.obstacles.push({ b: 50, x: 0, y: 0, d: 1, w: 0, h: 5 }); return sev(runMapCheck(P(j)));")
    t.ok('zeroObstacle' in r, f'zeroObstacle が出ること: {r}')
    t.no_errors()


def test_insufficient_light(t):
    '''ライトが無い譜面では insufficientLight（ランク不可）が出る。11個以上あれば出ない'''
    r = _run(t, """
const few = base(); few.basicBeatmapEvents = [];
const ten = base(); ten.basicBeatmapEvents = Array.from({length: 10}, (_, i) => ({ b: i, et: 0, i: 1, f: 1 }));
const eleven = base(); eleven.basicBeatmapEvents = Array.from({length: 11}, (_, i) => ({ b: i, et: 0, i: 1, f: 1 }));
return { few: sev(runMapCheck(P(few))), ten: sev(runMapCheck(P(ten))), eleven: sev(runMapCheck(P(eleven))) };""")
    t.ok('insufficientLight' in r['few'], '0個で出る')
    t.ok('insufficientLight' in r['ten'], '10個で出る（11個以上が必要）')
    t.ok('insufficientLight' not in r['eleven'], '11個で出ない')
    t.no_errors()


def test_dark_events_not_counted(t):
    '''消灯（値0）のライトイベントはライトの数に数えない'''
    r = _run(t, """
const j = base(); j.basicBeatmapEvents = Array.from({length: 30}, (_, i) => ({ b: i, et: 0, i: 0, f: 1 }));
return sev(runMapCheck(P(j)));""")
    t.ok('insufficientLight' in r, '消灯だけなら不足')
    t.no_errors()


def test_stacked_note(t):
    '''同じマスに同じ時刻でノーツを重ねると stackedNote が出る'''
    r = _run(t, """
const j = base(); j.colorNotes.push({ b: 50, x: 1, y: 0, c: 0, d: 1 }); j.colorNotes.sort((a, b) => a.b - b.b);
const r = runMapCheck(P(j)); return r.diffs[0].results.map(x => x.key);""")
    t.ok('stackedNote' in r, f'stackedNote: {r}')
    r0 = _run(t, "return runMapCheck(P(base())).diffs[0].results.map(x => x.key);")
    t.ok('stackedNote' not in r0, '基準の譜面では出ない')
    t.no_errors()


def test_audio_and_cover(t):
    '''音源が20秒未満/無し、カバーが正方形でない/256未満の指摘が出る'''
    r = _run(t, """
const g = x => runMapCheck(x).general.map(y => y.key);
return { short: g(P(base(), { audioDuration: 10 })), none: g(P(base(), { audioDuration: null })),
  cover: g(P(base(), { cover: { w: 200, h: 180, name: 'c.png' } })), nocover: g(P(base(), { cover: null })), ok: g(P(base())) };""")
    t.ok('audioShort' in r['short'], '20秒未満')
    t.ok('noAudio' in r['none'], '音源なし')
    t.ok('coverNotSquare' in r['cover'] and 'coverSmall' in r['cover'], 'カバーが非正方形かつ小さい')
    t.ok('noCover' in r['nocover'], 'カバーなし')
    t.ok(not any(k in r['ok'] for k in ('audioShort', 'noAudio', 'coverNotSquare', 'coverSmall', 'noCover')), '基準では出ない')
    t.no_errors()


def test_notes_after_audio_end(t):
    '''音源より後ろのノーツは afterEnd が出る'''
    r = _run(t, "return runMapCheck(P(base(), { audioDuration: 10 })).diffs[0].results.map(x => x.key);")
    t.ok('afterEnd' in r, f'afterEnd: {r}')
    t.no_errors()


def test_result_shape(t):
    '''結果の形: 項目ごとに key/status を持ち、対象物は拍順の beat/kind を持つ。CHECK_NAMESも出ている'''
    r = _run(t, """
const m = await import('/js/mapcheck/mapcheck.js');
const j = base(); j.colorNotes.push({ b: 90, x: 1, y: 0, c: 0, d: 1 }, { b: 50, x: 1, y: 0, c: 0, d: 1 });
j.colorNotes.sort((a, b) => a.b - b.b);   // 原作は並べ替えないので、時刻順に直してから渡す
const res = m.runMapCheck(P(j)).diffs[0].results.find(x => x.key === 'stackedNote');
return { names: m.CHECK_NAMES.length, st: Object.values(m.STATUS), res };""")
    t.ok(r['names'] > 30, '検査項目の一覧')
    t.eq(sorted(r['st']), ['error', 'info', 'rank', 'warn'], 'STATUS')
    res = r['res']
    t.ok(res and res['objs'], 'stackedNote の対象物')
    beats = [o['beat'] for o in res['objs']]
    t.eq(beats, sorted(beats), '対象物は拍順')
    t.ok({50, 90} <= set(beats), '仕込んだ2か所を含む')
    t.ok(all(o['kind'] == 'note' for o in res['objs']), 'kind=note')
    t.no_errors()


def test_empty_diff(t):
    '''ノーツが1つも無い難易度でも例外にならない'''
    r = _run(t, """
const j = { version: '3.2.0', bpmEvents: [], colorNotes: [], bombNotes: [], obstacles: [], sliders: [], burstSliders: [], basicBeatmapEvents: [] };
const r = runMapCheck(P(j)); return { err: r.diffs[0].error || null, failed: r.diffs[0].results.filter(x => x.key === 'checkFailed').length };""")
    t.eq(r['err'], None, '例外なし')
    t.eq(r['failed'], 0, '個別の検査も失敗していない')
    t.no_errors()


def test_short_obstacle(t):
    '''ごく短い全高の壁(0.015秒未満)は shortObstacle、十分な長さなら出ない'''
    r = _run(t, """
const mk = d => { const j = base(); j.obstacles.push({ b: 60, x: 1, y: 0, d, w: 1, h: 5 }); return runMapCheck(P(j)).diffs[0].results.map(x => x.key); };
return { short: mk(0.02), ok: mk(1) };""")
    t.ok('shortObstacle' in r['short'], f"0.02拍(120BPMで0.01秒): {r['short']}")
    t.ok('shortObstacle' not in r['ok'], '1拍なら出ない')
    t.no_errors()

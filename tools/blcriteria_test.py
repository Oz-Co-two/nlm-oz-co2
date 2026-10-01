"""NLM版 BeatLeader評価リスト（js/mapcheck/blcriteria.js）の自己テスト。
問題の無い譜面を1つ作り、そこへ基準の違反を1つずつ仕込んで、該当項目が「違反/要確認」になるかを見る。
判定を直した時・基準の改訂に追従した時に実行する（ヘッドレスEdge。.venv-build のPythonで）:
  .venv-build/Scripts/python.exe tools/blcriteria_test.py
"""
import sys, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from cdp import Editor

JS = r"""
(async () => {
const { runMapCheck } = await import('/js/mapcheck/mapcheck.js');
const { runBlCriteria } = await import('/js/mapcheck/blcriteria.js');
const base = () => {
  const cn = [], ev = [];
  for (let b = 8; b <= 200; b++) { const d = b % 2 ? 0 : 1; cn.push({ b, x: 1, y: 0, c: 0, d, a: 0 }, { b, x: 2, y: 0, c: 1, d, a: 0 }); }
  for (let b = 0; b <= 240; b++) ev.push({ b, et: 0, i: 1, f: 1 });
  return { version: '3.2.0', bpmEvents: [], colorNotes: cn, bombNotes: [], obstacles: [], sliders: [], burstSliders: [], basicBeatmapEvents: ev };
};
const P = (json, extra = {}) => ({ info: { bpm: 120, environment: 'DefaultEnvironment', previewStart: 12, previewDuration: 10 },
  diffs: [{ difficulty: 'Expert', json, njs: 16, njsOffset: 0 }], audioDuration: 120, cover: { w: 512, h: 512, name: 'cover.png' },
  meta: { songName: 'Test Song', subName: '', author: 'Artist', mapper: 'me' },
  infoRaw: { songTimeOffset: 0, shuffle: 0, shufflePeriod: 0, colorSchemes: [], requirements: [] }, ...extra });
const run = p => { const mc = runMapCheck(p); return runBlCriteria(p, mc); };
const pick = (res, ids) => Object.fromEntries(ids.map(id => { const r = res.rules.find(x => x.id === id); return [id, r.status + (r.findings.length ? ' ' + r.findings.map(f => f.key + (f.objs ? '[' + f.objs.map(o => o.beat).join(',') + ']' : '')).join('|') : '')]; }));
const out = {};
// 基準の譜面: 自動判定の項目で違反・要確認が出ないこと
{ const r = run(P(base())); out.base = r.rules.filter(x => x.status === 'fail' || x.status === 'check').map(x => x.id + ':' + x.findings.map(f => f.key).join('|')); }
const C = (name, mod, ids, extra) => { const j = base(); mod(j); out[name] = pick(run(P(j, extra)), ids); };
const rm = (j, b) => { j.colorNotes = j.colorNotes.filter(n => n.b !== b); };
C('lead', j => j.colorNotes.unshift({ b: 2, x: 0, y: 2, c: 0, d: 1 }), ['R1.D.1']);
C('leadRec', j => j.colorNotes.unshift({ b: 3.5, x: 0, y: 2, c: 0, d: 1 }), ['R1.D.1']);
C('tail', j => j.colorNotes.push({ b: 238, x: 0, y: 2, c: 0, d: 1 }), ['R1.D.2']);
C('length', j => { j.colorNotes = j.colorNotes.filter(n => n.b <= 90); }, ['R1.F']);
C('wallZero', j => j.obstacles.push({ b: 50, x: 0, y: 0, d: 1, w: 0, h: 5 }), ['R1.B.4']);
C('wallNeg', j => j.obstacles.push({ b: 50, x: 0, y: 1, d: 1, w: 1, h: -1 }), ['R1.B.4']);
C('wallNegOk', j => j.obstacles.push({ b: 50, x: 0, y: 0, d: 1, w: 1, h: -1 }), ['R1.B.4']);
C('beyond', j => j.colorNotes.push({ b: 250, x: 0, y: 2, c: 0, d: 1 }), ['R1.B.6', 'R1.D.2']);
C('wallEnd', j => j.obstacles.push({ b: 238, x: 0, y: 0, d: 4, w: 1, h: 5 }), ['R1.B.7']);
C('zInter', j => j.colorNotes.push({ b: 100.02, x: 1, y: 0, c: 1, d: 1 }), ['R3.A.1']);
C('inWall', j => j.obstacles.push({ b: 50.5, x: 1, y: 0, d: 2, w: 1, h: 5 }), ['R3.A.2', 'R5.B.3']);
C('preSwing', j => j.colorNotes.push({ b: 119.9, x: 1, y: 1, c: 1, d: 8 }), ['R3.B']);
C('first16', j => { j.burstSliders.push({ b: 10, x: 1, y: 0, c: 0, d: 1, tb: 10.25, tx: 1, ty: 0, sc: 3, s: 1 }); }, ['R6.A']);
C('chainRev', j => { j.burstSliders.push({ b: 100, x: 1, y: 0, c: 0, d: 1, tb: 99.9, tx: 1, ty: 1, sc: 3, s: 1 }); }, ['R6.B.1']);
C('chainTurn', j => { rm(j, 101); j.colorNotes.push({ b: 101, x: 2, y: 0, c: 1, d: 0 }); j.colorNotes.find(n => n.b === 100 && n.c === 0).d = 1;
  j.burstSliders.push({ b: 100, x: 1, y: 0, c: 0, d: 1, tb: 100.25, tx: 3, ty: 0, sc: 4, s: 1 }); }, ['R6.B.2']);
C('chainOk', j => { rm(j, 101); rm(j, 102); j.colorNotes.push({ b: 102, x: 1, y: 0, c: 0, d: 1 }, { b: 102, x: 2, y: 0, c: 1, d: 1 });
  j.colorNotes.find(n => n.b === 100 && n.c === 0).x = 1; j.colorNotes.find(n => n.b === 100 && n.c === 0).y = 2;
  j.burstSliders.push({ b: 100, x: 1, y: 2, c: 0, d: 1, tb: 100.25, tx: 1, ty: 0, sc: 4, s: 1 }); },
  ['R6.A', 'R6.B.1', 'R6.B.2', 'R6.C.1', 'R6.C.2', 'R6.D', 'R6.E', 'R6.G.1', 'R6.G.2', 'R3.A.1']);
C('linkOut', j => { const n = j.colorNotes.find(n => n.b === 100 && n.c === 1); n.x = 3; n.y = 1; n.d = 3;
  j.burstSliders.push({ b: 100, x: 3, y: 1, c: 1, d: 3, tb: 100.25, tx: 5.5, ty: 1, sc: 4, s: 1 }); }, ['R6.C.2', 'R6.C.1']);
C('sparse', j => { const n = j.colorNotes.find(n => n.b === 100 && n.c === 0); n.y = 2;
  j.burstSliders.push({ b: 100, x: 1, y: 2, c: 0, d: 1, tb: 100.25, tx: 1, ty: 0, sc: 4, s: 0.1 }); }, ['R6.D']);
C('gap', j => { const n = j.colorNotes.find(n => n.b === 100 && n.c === 0); n.y = 2;
  j.burstSliders.push({ b: 100, x: 1, y: 2, c: 0, d: 1, tb: 100.75, tx: 1, ty: 0, sc: 4, s: 1 }); }, ['R6.E']);
C('noHead', j => j.burstSliders.push({ b: 100.5, x: 0, y: 2, c: 0, d: 1, tb: 100.75, tx: 0, ty: 1, sc: 3, s: 1 }), ['R6.G.1']);
C('sc1', j => { const n = j.colorNotes.find(n => n.b === 100 && n.c === 0); n.y = 2;
  j.burstSliders.push({ b: 100, x: 1, y: 2, c: 0, d: 1, tb: 100.25, tx: 1, ty: 1, sc: 1, s: 1 }); }, ['R6.G.2']);
C('arcBomb', j => { j.bombNotes.push({ b: 130.5, x: 0, y: 2 }); j.sliders.push({ b: 130, x: 1, y: 0, c: 0, d: 1, mu: 1, tb: 130.5, tx: 0, ty: 2, tc: 0, tmu: 1, m: 0 }); }, ['R6.F']);
C('shortWall', j => j.obstacles.push({ b: 60, x: 0, y: 0, d: 0.02, w: 1, h: 5 }), ['R8.C']);
C('shortWallOk', j => j.obstacles.push({ b: 60, x: 0, y: 0, d: 1, w: 1, h: 5 }, { b: 61.2, x: 0, y: 0, d: 0.02, w: 1, h: 5 }), ['R8.C']);
C('outer', j => j.obstacles.push({ b: 60, x: 1, y: 0, d: 1, w: 2, h: 5 }), ['R8.B']);
C('outer2', j => j.obstacles.push({ b: 60, x: 0, y: 0, d: 1, w: 2, h: 5 }, { b: 60.5, x: 2, y: 0, d: 1, w: 1, h: 5 }), ['R8.B']);
C('crouch', j => { j.obstacles.push({ b: 60, x: 0, y: 2, d: 4, w: 4, h: 3 }); j.colorNotes.push({ b: 61.5, x: 0, y: 2, c: 0, d: 1 }); }, ['R8.D.1', 'R8.D.2', 'R3.A.2']);
C('dodge', j => j.obstacles.push({ b: 60, x: 1, y: 0, d: 0.5, w: 1, h: 5 }, { b: 60.5, x: 2, y: 0, d: 0.5, w: 1, h: 5 }, { b: 61, x: 1, y: 0, d: 0.5, w: 1, h: 5 }), ['R8.A.3']);
C('light', j => { j.basicBeatmapEvents = j.basicBeatmapEvents.filter(e => e.b < 100); }, ['R10.A', 'R7.B']);
C('bombDark', j => { j.basicBeatmapEvents = [{ b: 0, et: 0, i: 1, f: 1 }, { b: 150, et: 0, i: 0, f: 1 }, ...Array.from({ length: 300 }, (_, i) => ({ b: i * 0.8, et: 1, i: 0, f: 1 }))];
  j.bombNotes.push({ b: 140, x: 0, y: 2 }, { b: 160, x: 0, y: 2 }); }, ['R7.B']);
C('bombPath', j => j.bombNotes.push({ b: 121.2, x: 1, y: 1 }), ['R7.A']);
C('swing45', j => { rm(j, 70); j.colorNotes.push({ b: 70, x: 1, y: 2, c: 0, d: 1 }, { b: 70.0625, x: 1, y: 1, c: 0, d: 7 }, { b: 70.125, x: 2, y: 1, c: 0, d: 3 }, { b: 70, x: 2, y: 0, c: 1, d: 1 }); }, ['R4.B.1', 'R4.B.2']);
C('swingS', j => { rm(j, 70); j.colorNotes.push({ b: 70, x: 1, y: 2, c: 0, d: 1 }, { b: 70.0625, x: 1, y: 1, c: 0, d: 7 }, { b: 70.125, x: 1, y: 0, c: 0, d: 6 }, { b: 70, x: 2, y: 0, c: 1, d: 1 }); }, ['R4.B.1', 'R4.B.2']);
C('slider', j => { rm(j, 70); j.colorNotes.push({ b: 70, x: 1, y: 2, c: 0, d: 1 }, { b: 70.125, x: 1, y: 1, c: 0, d: 8 }, { b: 70.25, x: 1, y: 0, c: 0, d: 8 }, { b: 70, x: 2, y: 0, c: 1, d: 1 }); }, ['R4.A.3', 'R4.A.4']);
C('shuffle', j => {}, ['R1.B.2', 'R1.B.1'], { infoRaw: { songTimeOffset: 0.3, shuffle: 0, shufflePeriod: 0.5 } });
C('meta', j => {}, ['R11.B', 'R11.C', 'R11.D.2', 'R11.F.2', 'R11.G'], { meta: { songName: '海に化ける (feat. X)', subName: '', author: 'Ω feat. Y', mapper: '' } });
C('cover', j => {}, ['R1.A.4'], { cover: { w: 200, h: 180, name: 'c.webp' } });
C('noAudio', j => {}, ['R1.A.3', 'R1.B.6', 'R1.D.2'], { audioDuration: null });
C('vision', j => { rm(j, 80); j.colorNotes.push({ b: 80, x: 1, y: 1, c: 0, d: 1 }, { b: 80, x: 2, y: 0, c: 1, d: 1 }, { b: 80.5, x: 0, y: 1, c: 0, d: 1 }); }, ['R5.A'], { stars: { Expert: { star: 5, tech: 3 } } });
C('visionNoStar', j => {}, ['R5.A']);
return out;
})()
"""
# 各ケースで最初に挙げた項目が、この状態で始まること
EXPECT = {'lead': 'fail', 'tail': 'fail', 'length': 'fail', 'wallZero': 'fail', 'wallNeg': 'fail', 'wallNegOk': 'pass', 'beyond': 'fail',
          'wallEnd': 'fail', 'zInter': 'fail', 'inWall': 'fail', 'preSwing': 'check', 'first16': 'fail', 'chainRev': 'fail', 'chainTurn': 'fail',
          'linkOut': 'fail', 'sparse': 'fail', 'gap': 'fail', 'noHead': 'fail', 'sc1': 'fail', 'arcBomb': 'fail', 'shortWall': 'fail',
          'shortWallOk': 'pass', 'outer': 'fail', 'outer2': 'fail', 'crouch': 'check', 'dodge': 'check', 'light': 'fail', 'bombDark': 'check',
          'bombPath': 'check', 'swing45': 'fail', 'swingS': 'pass', 'slider': 'check', 'shuffle': 'fail', 'meta': 'check', 'cover': 'fail',
          'noAudio': 'check', 'vision': 'check', 'visionNoStar': 'check'}
with Editor() as ed:
    r = ed.js(JS)
    if '-v' in sys.argv:
        print(json.dumps(r, ensure_ascii=False, indent=1))
    ng = []
    if r['base'] != ['R5.A:needStars']:
        ng.append(('base', r['base']))
    for k, v in EXPECT.items():
        first = list(r[k].values())[0]
        if not first.startswith(v):
            ng.append((k, r[k]))
    for k, v in ng:
        print('NG', k, json.dumps(v, ensure_ascii=False))
    errs = ed.errors()
    if errs:
        print('JSエラー:', errs)
    print('OK: 全ケースが期待どおり' if not ng and not errs else f'NG: {len(ng)}件')
    sys.exit(1 if ng or errs else 0)

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
// 難易度の入力に項目を足す版（srcLightBoxes など）
const CD = (name, mod, ids, dx) => { const j = base(); mod(j); const p = P(j); Object.assign(p.diffs[0], dx); out[name] = pick(run(p), ids); };
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
C('preSwing', j => j.colorNotes.push({ b: 119.95, x: 1, y: 1, c: 1, d: 8 }), ['R3.B']);   // 25ms 前＝振る時にまだある
C('preSwingGone', j => j.colorNotes.push({ b: 119.8, x: 1, y: 1, c: 1, d: 8 }), ['R3.B']);   // 100ms 前＝もう切られて消えている
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
// 枠の外（4レーンにかからない）の短い壁は R8.C の対象外／時間を飛ばす区間（BPM 100000）の中の短い壁・重なりは要確認
C('shortWallOut', j => j.obstacles.push({ b: 60, x: 4, y: 0, d: 0.02, w: 1, h: 5 }, { b: 61, x: -1, y: 0, d: 0.02, w: 1, h: 3 }), ['R8.C']);
C('shortWallSkip', j => { j.bpmEvents = [{ b: 59.9, m: 100000 }, { b: 60.5, m: 120 }]; j.obstacles.push({ b: 60, x: 0, y: 0, d: 0.2, w: 1, h: 5 }); }, ['R8.C']);
C('zInterSkip', j => { j.bpmEvents = [{ b: 59.9, m: 100000 }, { b: 60.5, m: 120 }]; j.bombNotes.push({ b: 60.1, x: 0, y: 2 }, { b: 60.3, x: 0, y: 2 }); }, ['R3.A.1']);
// v4 の NJS の変化（njsEvents＋njsEventData）: R3.A.1 は手前の物を切る時刻の NJS で見る（基本 16・120BPM で 1拍＝0.5秒）。
// 拍 100 の赤（x1,y0）と同じマスに 0.03秒後（0.48m＝基本なら違反）／0.04秒後（0.64m＝基本なら通る）のノーツ
const NJ = (j, ev) => { j.njsEvents = ev.map((e, i) => ({ b: e[0], i })); j.njsEventData = ev.map(e => ({ p: e[1], e: e[2], d: e[3] })); };
C('zInterNjsUp', j => { j.colorNotes.push({ b: 100.06, x: 1, y: 0, c: 1, d: 1 }); NJ(j, [[90, 0, -1, 10]]); }, ['R3.A.1']);   // NJS 26＝0.78m で通る
C('zInterNjsDown', j => { j.colorNotes.push({ b: 100.08, x: 1, y: 0, c: 1, d: 1 }); NJ(j, [[90, 0, -1, -6]]); }, ['R3.A.1']);   // NJS 10＝0.4m で違反
// 拍 90（差0）→110（差−12）の間のイージング: 拍 100 で Linear＝−6（NJS 10＝違反）／InQuad＝−3（NJS 13・0.52m＝通る）
C('zInterNjsLin', j => { j.colorNotes.push({ b: 100.08, x: 1, y: 0, c: 1, d: 1 }); NJ(j, [[90, 0, 0, 0], [110, 0, 0, -12]]); }, ['R3.A.1']);
C('zInterNjsQuad', j => { j.colorNotes.push({ b: 100.08, x: 1, y: 0, c: 1, d: 1 }); NJ(j, [[90, 0, 0, 0], [110, 0, 1, -12]]); }, ['R3.A.1']);
// p＝前の値を使う: 拍 90 で −6、拍 95 は −6 のまま（p=1）、拍 110 で 0 へ Linear＝拍 100 は −4（NJS 12・0.48m＝違反）
C('zInterNjsExt', j => { j.colorNotes.push({ b: 100.08, x: 1, y: 0, c: 1, d: 1 }); NJ(j, [[90, 0, -1, -6], [95, 1, 0, 0], [110, 0, 0, 0]]); }, ['R3.A.1']);
// 最初の変化の前は基本の NJS（拍 110 から −6 でも、拍 100 は 16＝通る）
C('zInterNjsBefore', j => { j.colorNotes.push({ b: 100.08, x: 1, y: 0, c: 1, d: 1 }); NJ(j, [[110, 0, -1, -6]]); }, ['R3.A.1']);
// BS Map Check のヒットボックス（R3.C）は基本の NJS のまま＝注記／R1.B.8 のイージング・R9 の目視
C('njsMcNote', j => NJ(j, [[90, 0, 0, 2]]), ['R3.C', 'R9']);
C('njsEaseBad', j => NJ(j, [[90, 0, 5, 2]]), ['R1.B.8']);
C('njsUsed', j => NJ(j, [[90, 0, 0, 2], [100, 0, 0, 0]]), ['R9', 'R1.B.8']);
C('outer', j => j.obstacles.push({ b: 60, x: 1, y: 0, d: 1, w: 2, h: 5 }), ['R8.B']);
C('outer2', j => j.obstacles.push({ b: 60, x: 0, y: 0, d: 1, w: 2, h: 5 }, { b: 60.5, x: 2, y: 0, d: 1, w: 1, h: 5 }), ['R8.B']);
C('crouch', j => { j.obstacles.push({ b: 60, x: 0, y: 2, d: 4, w: 4, h: 3 }); j.colorNotes.push({ b: 61.5, x: 0, y: 2, c: 0, d: 1 }); }, ['R8.D.1', 'R8.D.2', 'R3.A.2']);
C('dodge', j => j.obstacles.push({ b: 60, x: 1, y: 0, d: 0.5, w: 1, h: 5 }, { b: 60.5, x: 2, y: 0, d: 0.5, w: 1, h: 5 }, { b: 61, x: 1, y: 0, d: 0.5, w: 1, h: 5 }), ['R8.A.3']);
// R8.A.3 の段: 塞ぐ側の入れ替わりが 0.4秒＝2回/秒超（正当化）／0.25秒＝3.8回/秒超（例外の承認）／0.24秒＝4回/秒超（例外でも不可）。どれも要確認。120BPM で 1拍＝0.5秒
C('dodgeSlow', j => j.obstacles.push({ b: 60, x: 1, y: 0, d: 0.8, w: 1, h: 5 }, { b: 60.8, x: 2, y: 0, d: 0.8, w: 1, h: 5 }, { b: 61.6, x: 1, y: 0, d: 0.8, w: 1, h: 5 }), ['R8.A.3']);
C('dodge4', j => j.obstacles.push({ b: 60, x: 1, y: 0, d: 0.48, w: 1, h: 5 }, { b: 60.48, x: 2, y: 0, d: 0.48, w: 1, h: 5 }, { b: 60.96, x: 1, y: 0, d: 0.48, w: 1, h: 5 }), ['R8.A.3']);
// R8.A.2: 右の真ん中の壁が終わってから左の真ん中の壁まで 230ms（例外でも不可）／240ms（例外の承認が要る）
C('wallGap230', j => j.obstacles.push({ b: 60, x: 2, y: 0, d: 0.5, w: 1, h: 5 }, { b: 60.96, x: 1, y: 0, d: 0.5, w: 1, h: 5 }), ['R8.A.2']);
C('wallGap240', j => j.obstacles.push({ b: 60, x: 2, y: 0, d: 0.5, w: 1, h: 5 }, { b: 60.98, x: 1, y: 0, d: 0.5, w: 1, h: 5 }), ['R8.A.2']);
C('light', j => { j.basicBeatmapEvents = j.basicBeatmapEvents.filter(e => e.b < 100); }, ['R10.A', 'R7.B']);
C('bombDark', j => { j.basicBeatmapEvents = [{ b: 0, et: 0, i: 1, f: 1 }, { b: 150, et: 0, i: 0, f: 1 }, ...Array.from({ length: 300 }, (_, i) => ({ b: i * 0.8, et: 1, i: 0, f: 1 }))];
  j.bombNotes.push({ b: 140, x: 0, y: 2 }, { b: 160, x: 0, y: 2 }); }, ['R7.B']);
// R7.B の近似（120BPM: 1拍＝0.5秒・250ms＝0.5拍）。ボムは拍 140
const LB = (j, evs) => { j.basicBeatmapEvents = evs; j.bombNotes.push({ b: 140, x: 0, y: 2 }); };
// 点滅（1/8拍＝62.5ms ごとに点く・消える）の中のボム＝明るい（ランク譜面に多い。以前は出ていた）
C('bombStrobe', j => LB(j, Array.from({ length: 960 }, (_, i) => ({ b: i * 0.25, et: 0, i: 1, f: 1 })).flatMap(e => [e, { b: e.b + 0.125, et: 0, i: 0, f: 1 }])), ['R7.B']);
// 長く暗い所で、ボムの 50ms 前に点く＝暗い
C('bombOnLate', j => LB(j, [{ b: 0, et: 0, i: 1, f: 1 }, { b: 130, et: 0, i: 0, f: 1 }, { b: 139.9, et: 0, i: 1, f: 1 }]), ['R7.B']);
// AutoModder と同じ見方: 消灯は 250ms 遅れて効き、ボムの 250ms 前の瞬間だけを見る。
// 250ms 前ちょうどに消えてボムと同時に点く＝明るい扱い（文面より甘い所）／550ms 前に消えた＝暗い
C('bombOffLate', j => LB(j, [{ b: 0, et: 0, i: 1, f: 1 }, { b: 139.5, et: 0, i: 0, f: 1 }, { b: 140, et: 0, i: 1, f: 1 }]), ['R7.B']);
C('bombOffEarly', j => LB(j, [{ b: 0, et: 0, i: 1, f: 1 }, { b: 138.9, et: 0, i: 0, f: 1 }, { b: 140, et: 0, i: 1, f: 1 }]), ['R7.B']);
// フェード（1 秒点灯とみなす）の後に何も無い＝暗い
C('bombFadeOld', j => LB(j, [{ b: 0, et: 0, i: 1, f: 1 }, { b: 130, et: 0, i: 3, f: 1 }, { b: 200, et: 0, i: 1, f: 1 }]), ['R7.B']);
// 明るさ 0.2（0.25 未満）だけ＝暗い／0.3 なら明るい
C('bombDimF', j => LB(j, [{ b: 0, et: 0, i: 1, f: 1 }, { b: 130, et: 0, i: 1, f: 0.2 }]), ['R7.B']);
C('bombDimFOk', j => LB(j, [{ b: 0, et: 0, i: 1, f: 1 }, { b: 130, et: 0, i: 1, f: 0.3 }]), ['R7.B']);
// Chroma の色: ほぼ黒（0.1）＝暗い／暗めの紫（最大 0.45）は明るい
C('bombDimC', j => LB(j, [{ b: 0, et: 0, i: 1, f: 1 }, { b: 130, et: 0, i: 1, f: 1, customData: { color: [0.1, 0.1, 0.1, 1] } }]), ['R7.B']);
C('bombDimCOk', j => LB(j, [{ b: 0, et: 0, i: 1, f: 1 }, { b: 130, et: 0, i: 1, f: 1, customData: { color: [0.3, 0, 0.45, 1] } }]), ['R7.B']);
// Chroma の lightID 付きの消灯は、その ID のライトだけ（種類の他のライトは点いたまま）＝明るい
C('bombLightId', j => LB(j, [{ b: 0, et: 0, i: 1, f: 1 }, ...Array.from({ length: 20 }, (_, i) => ({ b: 130 + i * 0.5, et: 0, i: 0, f: 1, customData: { lightID: [3] } }))]), ['R7.B']);
// lightID 無しの消灯は種類の全部＝暗い
C('bombLightIdAll', j => LB(j, [{ b: 0, et: 0, i: 1, f: 1, customData: { lightID: [1, 2] } }, { b: 130, et: 0, i: 0, f: 1 }]), ['R7.B']);
// 元の譜面のライトがライトボックス（srcLightBoxes>0）: ライトが足りない・ボムが暗い・ライトが1つも無い譜面でも、R10.A・R7.B は手動確認だけ
CD('boxSrcFew', j => { j.basicBeatmapEvents = j.basicBeatmapEvents.filter(e => e.b < 100); j.bombNotes.push({ b: 160, x: 0, y: 2 }); }, ['R10.A', 'R7.B'], { srcLightBoxes: 12 });
CD('boxSrcDark', j => { j.basicBeatmapEvents = [...j.basicBeatmapEvents.filter(e => e.b < 100), { b: 100, et: 0, i: 0, f: 1 }]; j.bombNotes.push({ b: 160, x: 0, y: 2 }); }, ['R7.B', 'R10.A'], { srcLightBoxes: 12 });
// 同じ譜面で srcLightBoxes が無ければ今までどおり（暗いボム・ライト不足）
CD('boxSrcDarkNo', j => { j.basicBeatmapEvents = [...j.basicBeatmapEvents.filter(e => e.b < 100), { b: 100, et: 0, i: 0, f: 1 }]; j.bombNotes.push({ b: 160, x: 0, y: 2 }); }, ['R7.B', 'R10.A'], {});
CD('boxSrcNone', j => { j.basicBeatmapEvents = []; j.bombNotes.push({ b: 140, x: 0, y: 2 }); }, ['R7.B', 'R10.A'], { srcLightBoxes: 3 });
C('bombPath', j => j.bombNotes.push({ b: 121.2, x: 1, y: 1 }), ['R7.A']);
C('swing45', j => { rm(j, 70); j.colorNotes.push({ b: 70, x: 1, y: 2, c: 0, d: 1 }, { b: 70.0625, x: 1, y: 1, c: 0, d: 7 }, { b: 70.125, x: 2, y: 1, c: 0, d: 3 }, { b: 70, x: 2, y: 0, c: 1, d: 1 }); }, ['R4.B.1', 'R4.B.2']);
C('swingS', j => { rm(j, 70); j.colorNotes.push({ b: 70, x: 1, y: 2, c: 0, d: 1 }, { b: 70.0625, x: 1, y: 1, c: 0, d: 7 }, { b: 70.125, x: 1, y: 0, c: 0, d: 6 }, { b: 70, x: 2, y: 0, c: 1, d: 1 }); }, ['R4.B.1', 'R4.B.2']);
// 角度のずらし（a・反時計回り）は向きに足す: 上向き a=-30（右へ30度）から右上の点へ＝3度のずれで通る／a=+30 なら57度で違反
C('angleOff', j => { rm(j, 70); j.colorNotes.push({ b: 70, x: 1, y: 0, c: 0, d: 0, a: -30 }, { b: 70.0625, x: 2, y: 2, c: 0, d: 8 }, { b: 70, x: 3, y: 0, c: 1, d: 1 }); }, ['R4.B.1']);
C('angleOffBad', j => { rm(j, 70); j.colorNotes.push({ b: 70, x: 1, y: 0, c: 0, d: 0, a: 30 }, { b: 70.0625, x: 2, y: 2, c: 0, d: 8 }, { b: 70, x: 3, y: 0, c: 1, d: 1 }); }, ['R4.B.1']);
// 速い連打: 上向きの矢印の62.5ms後に下の点＝逆へ動くので次のスイング／点の上下の往復の後の矢印＝折り返すので次のスイング
C('fastRev', j => { rm(j, 70); j.colorNotes.push({ b: 70, x: 1, y: 2, c: 0, d: 0 }, { b: 70.125, x: 1, y: 0, c: 0, d: 8 }, { b: 70, x: 2, y: 0, c: 1, d: 1 }); }, ['R4.B.1', 'R4.B.2']);
C('zigzag', j => { rm(j, 70); j.colorNotes.push({ b: 70, x: 1, y: 0, c: 0, d: 8 }, { b: 70.125, x: 1, y: 2, c: 0, d: 8 }, { b: 70.25, x: 0, y: 0, c: 0, d: 6 }, { b: 70, x: 3, y: 0, c: 1, d: 1 }); }, ['R4.B.1', 'R4.B.2']);
// 同じ拍＝秒で1ms未満のずれまで: 右向きの赤の横並びで、右のマスの方が先（置いた順だと矢印と逆へ動く）。120BPM で 1拍＝0.5秒
// 0.00003拍（15µs・保存の端数）＝同じ拍とみなして左→右で切れる／0.004拍（2ms）＝置いた順で違反／ちょうど同じ拍＝通る
const sideBySide = (j, dt) => { rm(j, 70); j.colorNotes.push({ b: 70, x: 1, y: 0, c: 0, d: 3 }, { b: 70 + dt, x: 0, y: 0, c: 0, d: 3 }, { b: 70, x: 3, y: 0, c: 1, d: 1 }); };
C('sameBeatTiny', j => sideBySide(j, 0.00003), ['R4.B.1', 'R4.B.2']);
C('sameBeat2ms', j => sideBySide(j, 0.004), ['R4.B.1', 'R4.B.2']);
C('sameBeatExact', j => sideBySide(j, 0), ['R4.B.1', 'R4.B.2']);
// 長さ0のチェーン（尾＝頭）は逆向きではない
C('chainZero', j => { rm(j, 101); rm(j, 102); j.colorNotes.push({ b: 102, x: 1, y: 0, c: 0, d: 1 }, { b: 102, x: 2, y: 0, c: 1, d: 1 });
  j.colorNotes.find(n => n.b === 100 && n.c === 0).x = 1; j.colorNotes.find(n => n.b === 100 && n.c === 0).y = 2;
  j.burstSliders.push({ b: 100, x: 1, y: 2, c: 0, d: 1, tb: 100, tx: 1, ty: 0, sc: 4, s: 1 }); }, ['R6.B.1', 'R6.E']);
// リンクが曲線の計算で枠の下へ0.011マス出る（0.1マスまで許す）
C('linkTiny', j => { const n = j.colorNotes.find(n => n.b === 100 && n.c === 0); n.x = 0; n.y = 1; n.d = 7;
  j.burstSliders.push({ b: 100, x: 0, y: 1, c: 0, d: 7, tb: 100.25, tx: 3, ty: 0, sc: 10, s: 0.9 }); }, ['R6.C.2']);
// 頭→尾は27度・曲線の終わりの向きだけ48.6度（頭の位置から各リンクへの向きで見る＝通る）
C('chainCurve', j => { const n = j.colorNotes.find(n => n.b === 100 && n.c === 1); n.d = 2;
  j.burstSliders.push({ b: 100, x: 2, y: 0, c: 1, d: 2, tb: 100.0625, tx: 0, ty: 1, sc: 7, s: 1 }); }, ['R6.B.2']);
C('slider', j => { rm(j, 70); j.colorNotes.push({ b: 70, x: 1, y: 2, c: 0, d: 1 }, { b: 70.125, x: 1, y: 1, c: 0, d: 8 }, { b: 70.25, x: 1, y: 0, c: 0, d: 8 }, { b: 70, x: 2, y: 0, c: 1, d: 1 }); }, ['R4.A.3', 'R4.A.4']);
// R4.A.6（120BPM: 1拍＝0.5秒）。チェーンは拍 100 の赤（上段→下段）。スライダーは偶数の拍（下向き）の赤の前に1つ上のマスの赤を足して作る
const chainAt = (j, tb) => { j.colorNotes.find(n => n.b === 100 && n.c === 0).y = 2; j.burstSliders.push({ b: 100, x: 1, y: 2, c: 0, d: 1, tb, tx: 1, ty: 0, sc: 4, s: 1 }); };
const slidersAt = (j, beats, gap) => { for (const b of beats) j.colorNotes.push({ b: b - gap, x: 1, y: 1, c: 0, d: 1 }); };
// スライダーが無い＝比べない（合格・注記だけ）／ほぼ同時の組（1/64拍）だけ＝スライダーに数えない
C('chainNoSl', j => chainAt(j, 100.25), ['R4.A.6']);
C('chainInstant', j => { chainAt(j, 100.25); slidersAt(j, [50, 60, 70, 80], 1 / 64); }, ['R4.A.6']);
// 1/8拍（62.5ms）のスライダー3つ＝上限 125ms。125.5ms のチェーン＝ちょうど（1ms以内）で出ない／250ms＝出る／スライダー2つ＝比べない
C('chainExact', j => { chainAt(j, 100.251); slidersAt(j, [50, 60, 70], 1 / 8); }, ['R4.A.6']);
C('chainLongReal', j => { chainAt(j, 100.5); slidersAt(j, [50, 60, 70], 1 / 8); }, ['R4.A.6']);
C('chainFewSl', j => { chainAt(j, 100.5); slidersAt(j, [50, 60], 1 / 8); }, ['R4.A.6']);
C('shuffle', j => {}, ['R1.B.2', 'R1.B.1'], { infoRaw: { songTimeOffset: 0.3, shuffle: 0, shufflePeriod: 0.5 } });
C('meta', j => {}, ['R11.B', 'R11.C', 'R11.D.2', 'R11.F.2', 'R11.G'], { meta: { songName: '架空の歌 (feat. X)', subName: '', author: 'Ω feat. Y', mapper: '' } });
C('cover', j => {}, ['R1.A.4'], { cover: { w: 200, h: 180, name: 'c.webp' } });
C('noAudio', j => {}, ['R1.A.3', 'R1.B.6', 'R1.D.2'], { audioDuration: null });
C('vision', j => { rm(j, 80); j.colorNotes.push({ b: 80, x: 1, y: 1, c: 0, d: 1 }, { b: 80, x: 2, y: 0, c: 1, d: 1 }, { b: 80.5, x: 0, y: 1, c: 0, d: 1 }); }, ['R5.A'], { stars: { Expert: { star: 5, tech: 3 } } });
C('visionNoStar', j => {}, ['R5.A']);
// R11.H.5（★の並び・0.5★まで許容）: 難易度は書き出しの順（易しい順）。隣どうしでなく、それまでの一番高い★と比べる
const D = dn => ({ difficulty: dn, json: base(), njs: 16, njsOffset: 0 });
const ND = () => [D('Normal'), D('Hard'), D('Expert')];
C('starOrder', j => {}, ['R11.H.5'], { diffs: ND(), stars: { Normal: { star: 3, tech: 2 }, Hard: { star: 5, tech: 3 }, Expert: { star: 4.4, tech: 3 } } });
C('starOrderOk', j => {}, ['R11.H.5'], { diffs: ND(), stars: { Normal: { star: 3, tech: 2 }, Hard: { star: 5, tech: 3 }, Expert: { star: 4.6, tech: 3 } } });
C('starOrderPart', j => {}, ['R11.H.5'], { diffs: ND(), stars: { Normal: { star: 3, tech: 2 }, Hard: { star: 5, tech: 3 } } });
C('starOrderNone', j => {}, ['R11.H.5'], { diffs: ND() });
return out;
})()
"""
# 各ケースで最初に挙げた項目が、この状態で始まること
EXPECT = {'lead': 'fail', 'tail': 'fail', 'length': 'fail', 'wallZero': 'fail', 'wallNeg': 'fail', 'wallNegOk': 'pass', 'beyond': 'fail',
          'wallEnd': 'fail', 'zInter': 'fail', 'inWall': 'fail', 'preSwing': 'check', 'preSwingGone': 'pass', 'first16': 'fail', 'chainRev': 'fail', 'chainTurn': 'fail',
          'linkOut': 'fail', 'sparse': 'fail', 'gap': 'fail', 'noHead': 'fail', 'sc1': 'fail', 'arcBomb': 'fail', 'shortWall': 'fail',
          'shortWallOk': 'pass', 'outer': 'fail', 'shortWallOut': 'pass', 'shortWallSkip': 'check illegalWallSkip', 'zInterSkip': 'check zIntersectSkip',
          'zInterNjsUp': 'pass zIntersectNjs', 'zInterNjsDown': 'fail zIntersect[100,100.08]|zIntersectNjs', 'zInterNjsLin': 'fail zIntersect[100,100.08]',
          'zInterNjsQuad': 'pass zIntersectNjs', 'zInterNjsExt': 'fail zIntersect[100,100.08]', 'zInterNjsBefore': 'pass zIntersectNjs',
          'njsMcNote': 'pass njsBaseMc', 'njsEaseBad': 'fail njsEasing', 'njsUsed': 'check njsEventsUsed', 'outer2': 'fail', 'crouch': 'check', 'dodge': 'check dodgeOver38', 'dodgeSlow': 'check dodgeFast', 'dodge4': 'check dodgeOver4', 'wallGap230': 'check wallDodge235', 'wallGap240': 'check wallDodge250', 'light': 'fail', 'bombDark': 'check bombDark[160]',
          'bombStrobe': 'pass', 'bombOnLate': 'check bombDark[140]', 'bombOffLate': 'pass', 'bombOffEarly': 'check bombDark[140]', 'bombFadeOld': 'check bombDark[140]', 'bombDimF': 'check bombDark[140]', 'bombDimFOk': 'pass',
          'bombDimC': 'check bombDark[140]', 'bombDimCOk': 'pass', 'bombLightId': 'pass', 'bombLightIdAll': 'check bombDark[140]',
          'boxSrcFew': 'manual boxLightsUnread', 'boxSrcDark': 'manual boxLightsUnread', 'boxSrcNone': 'manual boxLightsUnread', 'boxSrcDarkNo': 'check bombDark[160]',
          'chainNoSl': 'pass noSliders', 'chainInstant': 'pass noSliders', 'chainExact': 'pass', 'chainLongReal': 'check chainLong[100]', 'chainFewSl': 'pass fewSliders',
          'bombPath': 'check', 'swing45': 'fail', 'swingS': 'pass', 'slider': 'check',
          'angleOff': 'pass', 'angleOffBad': 'fail', 'fastRev': 'pass', 'zigzag': 'pass', 'sameBeatTiny': 'pass', 'sameBeat2ms': 'fail swing45[70]', 'sameBeatExact': 'pass','chainZero': 'pass', 'linkTiny': 'pass', 'chainCurve': 'pass', 'shuffle': 'fail', 'meta': 'check', 'cover': 'fail',
          'noAudio': 'check', 'vision': 'check', 'visionNoStar': 'check',
          'starOrder': 'check starOrder', 'starOrderOk': 'pass starOrderOk', 'starOrderPart': 'manual starOrderOk|orderNeedStars',
          'starOrderNone': 'manual orderNoStars'}
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

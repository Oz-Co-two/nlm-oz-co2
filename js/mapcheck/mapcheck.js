// 譜面チェック（BeatLeader ランク基準）
// KivalEvan/BeatSaber-MapCheck（MIT, (c) 2021 Kival Evan）の BeatLeader プリセットと、
// その判定が使う bsmap（MIT, 同作者）の計算をNLM用に移植したもの（元: MapCheck commit 56d16718 / 2026-06-12）。
// 判定の中身・しきい値は原作どおり。原作との違い:
//  - 入力はNLMが書き出す.datのJSON（v3、またはv2を読み替え）とInfo.datの値。Mapping/Noodle Extensions非対応
//  - 原作で例外になり結果ごと消える組み合わせ（分割数1のチェーン・未定義のイベント種別など）は、その対象だけ飛ばす
//  それ以外は、原作の計算のクセ（chainLinks の説明参照）も含めて同じ結果になるようにしている＝審査で見られる結果と揃える
//  - 原作のエイプリルフール表示・zip検査は対象外（NLMはフォルダへ直接書き出すため）
import { BASIC_TRACKS, GROUP_TRACKS } from './env-tables.js';

export const STATUS = { RANK: 'rank', ERROR: 'error', WARN: 'warn', INFO: 'info' };

// ---------- 基本計算（bsmap） ----------
const DIR_ANGLE = [180, 0, 270, 90, 225, 135, 315, 45, 0];   // 向き→角度（下=0・反時計回り）
const DIR_SPACE = [[0, 1], [0, -1], [-1, 0], [1, 0], [-1, 1], [1, 1], [-1, -1], [1, -1], [0, 0]];
const DIR_FLIP = [1, 0, 3, 2, 7, 6, 5, 4, 8];
const ANY = 8;
const noteAngle = d => DIR_ANGLE[d] ?? 0;
const mod = (x, m) => { if (m < 0) m = -m; const r = x % m; return r < 0 ? r + m : r; };
const lowDiff = (a, b, m) => Math.min(mod(a - b, m), mod(b - a, m));
const nearEq = (a, b, tol = Number.EPSILON) => Math.abs(a - b) <= tol;
const round = (v, d = 0) => { const p = 10 ** d; return Math.round(v * p) / p; };
const radToDeg = r => r * 180 / Math.PI, degToRad = d => d * Math.PI / 180;
const vDist = (a, b) => Math.hypot(a[0] - b[0], a[1] - b[1]);

// グリッド上の位置関係（posX/posY）
const gDist = (a, b) => Math.hypot(a.posX - b.posX, a.posY - b.posY);
const isHorizontal = (a, b, e = 0.001) => Math.abs(a.posY - b.posY) <= e;
const isVertical = (a, b, e = 0.001) => Math.abs(a.posX - b.posX) <= e;
const isDiagonal = (a, b, e = 0.001) => nearEq(Math.abs(a.posX - b.posX), Math.abs(a.posY - b.posY), e);
const isInline = (a, b, lap = 0.5) => gDist(a, b) <= lap;
const isWindow = (a, b, d = 1.8) => gDist(a, b) > d;
const isSlantedWindow = (a, b) => isWindow(a, b) && !isDiagonal(a, b) && !isHorizontal(a, b) && !isVertical(a, b);

// 事前計算済みの位置(pos)・角度(angle)で見る版（MapCheck utils/beatmap.ts）
const noteDistance = (a, b) => vDist(a.pos, b.pos);
function isNotePointing(note, target, tol) {
  const pqA = radToDeg(Math.atan2(target.pos[1] - note.pos[1], target.pos[0] - note.pos[0])) + 90;
  return lowDiff(note.angle, pqA, 360) <= tol;
}
const isNoteSwingable = (a, b, tol) => isNotePointing(a, b, tol) || isNotePointing(b, a, tol);
function isNotePointingRaw(note, target, tol) {
  const pqA = radToDeg(Math.atan2(target.posY - note.posY, target.posX - note.posX)) + 90;
  return lowDiff(noteAngle(note.direction), pqA, 360) <= tol;
}
const isNoteSwingableRaw = (a, b, tol) => isNotePointingRaw(a, b, tol) || isNotePointingRaw(b, a, tol);

// 向きの比較（bsmap extensions/placement/note.ts）
function checkDirection(a, b, tol, equal) {
  if (a == null || b == null) return false;
  let aa, bb;
  if (typeof a === 'number') aa = a; else { if (a.direction === ANY) return false; aa = noteAngle(a.direction); }
  if (typeof b === 'number') bb = b; else { if (b.direction === ANY) return false; bb = noteAngle(b.direction); }
  return equal ? lowDiff(aa, bb, 360) <= tol : lowDiff(aa, bb, 360) >= tol;
}
const angleInRange = (al, lo, hi) => mod(al - lo, 360) <= mod(hi - lo, 360);
const angleOf = (from, to) => radToDeg(Math.atan2(to.posY - from.posY, to.posX - from.posX));
function isEndNote(endNote, startNote, maybeDirection, tol = 85) {
  const fromStart = angleOf(startNote, endNote), fromEnd = angleOf(endNote, startNote);
  if (startNote.direction === ANY) {
    const da = mod(noteAngle(endNote.direction) + 180, 360);
    return angleInRange(fromEnd, da - tol, da + tol);
  }
  if (maybeDirection !== ANY) {
    const da = noteAngle(maybeDirection);
    return angleInRange(fromStart, da - tol, da + tol) || angleInRange(fromEnd, da - tol, da + tol);
  }
  const da = noteAngle(startNote.direction);
  return angleInRange(fromStart, da - tol, da + tol);
}

// 拍⇄秒（bsmap TimeProcessor。v3のbpmEventsによるテンポ変更に対応）
class TimeProcessor {
  constructor(bpm, bpmEvents = []) {
    this.bpm = bpm;
    this.ts = [...bpmEvents].filter(e => 'm' in e && !('o' in e)).sort((a, b) => (a.b || 0) - (b.b || 0))
      .map(e => ({ time: e.b || 0, scale: bpm / (e.m || bpm) }));
  }
  toRealTime(beat, timescale = true) {
    if (!timescale) return beat / this.bpm * 60;
    let calc = 0;
    for (let i = this.ts.length - 1; i >= 0; i--) {
      if (beat > this.ts[i].time) { calc += (beat - this.ts[i].time) * this.ts[i].scale; beat = this.ts[i].time; }
    }
    return (beat + calc) / this.bpm * 60;
  }
  toBeatTime(sec, timescale = true) {
    if (!timescale) return sec * this.bpm / 60;
    let calc = 0;
    for (let i = this.ts.length - 1; i >= 0; i--) {
      const cur = this.toRealTime(this.ts[i].time, timescale);
      if (sec > cur) { calc += (sec - cur) / this.ts[i].scale; sec = cur; }
    }
    return this.toBeatTime(sec + calc, false);
  }
}

// ノーツ飛来の距離計算（bsmap NoteJumpSpeed）
const HJD_START = 4, HJD_MIN = 0.25;
const FALLBACK_NJS = { ExpertPlus: 16, Expert: 12, Hard: 10, Normal: 10, Easy: 10 };
class NoteJumpSpeed {
  constructor(bpm, njs = 10, offset = 0) { this.bpm = bpm; this.value = njs; this.offset = offset; }
  calcHjd(offset = this.offset) {
    const num = 60 / this.bpm; let hjd = HJD_START;
    while (this.value * num * hjd > 17.999) hjd /= 2;
    if (hjd < 1) hjd = 1;
    return Math.max(hjd + offset, HJD_MIN);
  }
  get hjd() { return this.calcHjd(); }
  get jd() { return this.value * (60 / this.bpm) * this.hjd * 2; }
  calcJdOptimal() { return [-(18 / (this.value + 1)) + 18, 18 * (1 / 1.07) ** this.value + 18]; }
}

// ---------- 譜面の読み込みと事前計算（MapCheck load/beatmap.ts 相当） ----------
function toV3(d) {   // v2の.datをv3の形へ読み替え（NLMのv2書き出しはノーツ/ボム/壁/ライトのみ）
  if ('colorNotes' in d || /^[34]/.test(String(d.version || ''))) return d;
  const o = { version: '3.0.0', bpmEvents: [], colorNotes: [], bombNotes: [], obstacles: [], sliders: [], burstSliders: [], basicBeatmapEvents: [] };
  for (const n of d._notes || []) {
    if (n._type === 3) o.bombNotes.push({ b: n._time, x: n._lineIndex, y: n._lineLayer });
    else if (n._type === 0 || n._type === 1) o.colorNotes.push({ b: n._time, x: n._lineIndex, y: n._lineLayer, c: n._type, d: n._cutDirection, a: 0 });
  }
  for (const w of d._obstacles || []) o.obstacles.push({ b: w._time, x: w._lineIndex, y: w._type === 1 ? 2 : 0, d: w._duration, w: w._width, h: w._type === 1 ? 3 : 5 });
  for (const e of d._events || []) o.basicBeatmapEvents.push({ b: e._time, et: e._type, i: e._value, f: e._floatValue ?? 1, customData: e._customData });
  return o;
}
const byTime = (a, b) => a.time - b.time;
const num = (v, d = 0) => (typeof v === 'number' && isFinite(v)) ? v : d;

function mkFilter(f = {}) {
  return { type: f.f ?? 1, p0: f.p ?? 0, p1: f.t ?? 0, reverse: f.r ?? 0, chunks: f.c ?? 0, random: f.n ?? 0,
    limit: f.l ?? 0, limitAffectsType: f.d ?? 0 };
}
function loadEventBoxGroups(d) {   // v3のイベントボックス（元の.datから素通しされたもの）
  const color = (d.lightColorEventBoxGroups || []).map(g => ({ kind: 'lightColor', time: num(g.b), id: num(g.g),
    boxes: (g.e || []).map(x => ({ filter: mkFilter(x.f), beatDistributionType: x.d ?? 1, brightnessDistributionType: x.t ?? 1,
      affectFirst: x.b ?? 0, easing: x.i ?? 0,
      events: (x.e || []).map(e => ({ time: num(e.b), previous: e.i === 2 ? 1 : 0, easing: e.i === 1 ? 0 : -1,
        color: e.c ?? 0, brightness: e.s ?? 0, frequency: e.f ?? 0 })) })) }));
  const rot = (d.lightRotationEventBoxGroups || []).map(g => ({ kind: 'lightRotation', time: num(g.b), id: num(g.g),
    boxes: (g.e || []).map(x => ({ filter: mkFilter(x.f), beatDistributionType: x.d ?? 1, rotationDistributionType: x.t ?? 1,
      axis: x.a ?? 0, flip: x.r ?? 0, affectFirst: x.b ?? 0, easing: x.i ?? 0,
      events: (x.l || []).map(e => ({ time: num(e.b), easing: e.e ?? 0, loop: e.l ?? 0, direction: e.o ?? 0, previous: e.p ?? 0 })) })) }));
  const tra = (d.lightTranslationEventBoxGroups || []).map(g => ({ kind: 'lightTranslation', time: num(g.b), id: num(g.g),
    boxes: (g.e || []).map(x => ({ filter: mkFilter(x.f), beatDistributionType: x.d ?? 1, gapDistributionType: x.t ?? 1,
      axis: x.a ?? 0, flip: x.r ?? 0, affectFirst: x.b ?? 0, easing: x.i ?? 0,
      events: (x.l || []).map(e => ({ time: num(e.b), easing: e.e ?? 0, previous: e.p ?? 0 })) })) }));
  const fl = (d._fxEventsCollection && d._fxEventsCollection._fl) || [];
  const fx = (d.vfxEventBoxGroups || []).map(g => ({ kind: 'fx', time: num(g.b), id: num(g.g),
    boxes: (g.e || []).map(x => ({ filter: mkFilter(x.f), beatDistributionType: x.d ?? 1, fxDistributionType: x.t ?? 1,
      affectFirst: x.b ?? 0, easing: x.i ?? 0,
      events: (x.l || []).map(i => fl[i]).filter(Boolean).map(e => ({ time: num(e.b), easing: e.i ?? 0, previous: e.p ?? 0 })) })) }));
  return { color, rot, tra, fx };
}

// 1スイングのまとまりを判定（bsmap extensions/swing/swing.ts）
function swingNext(cur, prev, tp, ctx) {
  if (ctx && ctx.length > 0) {
    if (tp.toRealTime(prev.time) + 0.005 < tp.toRealTime(cur.time) && cur.direction !== ANY) {
      for (const n of ctx) if (n.direction !== ANY && checkDirection(cur, n, 90, false)) return true;
    }
    for (const o of ctx) if (isInline(cur, o)) return true;
  }
  const dt = tp.toRealTime(cur.time) - tp.toRealTime(prev.time);
  return (isWindow(cur, prev) && dt > 0.08) || dt > 0.07;
}
const calcEbpm = (cur, prev, tp) => tp.bpm / (tp.toBeatTime(tp.toRealTime(cur.time) - tp.toRealTime(prev.time), false) * 2);
function sliderSpeed(notes, tp, isMin) {
  let hasStraight = false, hasDiagonal = false, curved = isMin ? 0 : Number.MAX_SAFE_INTEGER;
  let speed = isMin ? Number.NEGATIVE_INFINITY : Number.POSITIVE_INFINITY;
  const pick = isMin ? Math.max : Math.min;
  for (let i = 0; i < notes.length; i++) {
    if (i === 0) { speed = pick(speed, isMin ? 0 : Number.MAX_SAFE_INTEGER); continue; }
    const dist = gDist(notes[i], notes[i - 1]) || 1;
    const dt = tp.toRealTime(notes[i].time) - tp.toRealTime(notes[i - 1].time);
    if ((isHorizontal(notes[i], notes[i - 1]) || isVertical(notes[i], notes[i - 1])) && !hasStraight) { hasStraight = true; curved = dt / dist; }
    hasDiagonal = isDiagonal(notes[i], notes[i - 1]) || isSlantedWindow(notes[i], notes[i - 1]) || hasDiagonal;
    speed = pick(speed, dt / dist);
  }
  return (hasStraight && hasDiagonal) ? curved : speed;
}
function swingGenerate(notes, tp) {
  const sc = []; let ebpm = 0, ebpmSwing = 0;
  const first = {}, last = {}, arr = { 0: [], 1: [] };
  const push = (c, nextNote) => {
    let minSpeed = sliderSpeed(arr[c], tp, true), maxSpeed = sliderSpeed(arr[c], tp, false);
    if (!(minSpeed > 0 && maxSpeed !== Infinity)) { minSpeed = 0; maxSpeed = 0; }
    if (nextNote) { ebpmSwing = calcEbpm(nextNote, first[c], tp); ebpm = calcEbpm(nextNote, last[c], tp); }
    sc.push({ time: tp.toRealTime(first[c].time), data: arr[c], ebpm, ebpmSwing, maxSpeed, minSpeed });
  };
  for (const n of notes) {
    if (n.color !== 0 && n.color !== 1) continue;
    if (last[n.color]) {
      if (swingNext(n, last[n.color], tp, arr[n.color])) { push(n.color, n); first[n.color] = n; arr[n.color] = []; }
    } else first[n.color] = n;
    last[n.color] = n; arr[n.color].push(n);
  }
  for (let c = 0; c < 2; c++) if (last[c]) push(c, null);
  return sc;
}

// チェーンのリンク位置（MapCheck createChainLinks）。
// 審査で使われる原作と同じ結果にするため、原作の計算のクセをそのまま再現している:
//  - bsmapのvectorMulは「0を掛けると元の値のまま」（n ? x*n : x）。最後のリンクや長さ0のチェーンの位置がずれる
//  - リンクの秒(sec)に拍の値が入る（視界妨害・インライン急角度・アークの判定で、以降の比較に影響する）
const mulQ = (v, n) => n ? [v[0] * n, v[1] * n] : [v[0], v[1]];
const addV = (a, b) => [a[0] + b[0], a[1] + b[1]], subV = (a, b) => [a[0] - b[0], a[1] - b[1]];
function bezierQuad(p0, p1, p2, t) {
  const n = 1 - t;
  const pos = addV(mulQ(p0, n * n), addV(mulQ(p1, 2 * n * t), mulQ(p2, t * t)));
  const tan = addV(mulQ(subV(p1, p0), 2 * n), mulQ(subV(p2, p1), 2 * t));
  return [pos, tan];
}
function chainLinks(ch, tp) {
  const p2 = subV(ch.tailPos, ch.pos);
  const mag = Math.hypot(p2[0], p2[1]), f = degToRad(ch.angle - 90);
  const p1 = mulQ([Math.cos(f), Math.sin(f)], mag * 0.5);
  const out = [];
  for (let i = 1; i < ch.sliceCount; i++) {
    const al = i / (ch.sliceCount - 1);
    let [pos, tan] = bezierQuad([0, 0], p1, p2, al * ch.squish);
    pos = addV(ch.pos, pos);
    const time = ch.time + (ch.tailTime - ch.time) * al;
    out.push({ type: 'link', time, sec: time, mcShown: tp.toRealTime(time), color: ch.color, posX: pos[0], posY: pos[1], direction: ch.direction,
      pos, angle: mod(radToDeg(Math.atan2(tan[1], tan[0])), 360), chain: ch });
  }
  return out;
}

function firstInteractiveTime(m) {
  const ns = [...m.colorNotes, ...m.bombNotes, ...m.chains];
  let t = ns.length ? Math.min(...ns.map(n => n.time)) : Number.MAX_VALUE;
  for (const o of m.obstacles) if (isInteractiveObstacle(o)) { t = Math.min(t, o.time); break; }
  return t;
}
function lastInteractiveTime(m) {
  const ns = [...m.colorNotes, ...m.bombNotes, ...m.chains];
  let t = ns.length ? Math.max(...ns.map(n => n.time)) : 0;
  for (const o of m.obstacles) if (isInteractiveObstacle(o)) t = Math.max(t, o.time + o.duration);
  return t;
}
const isInteractiveObstacle = o => (o.posX < 0 && o.width > 1 - o.posX) || (o.posX === 0 && o.width > 1) || o.posX === 1 || o.posX === 2;

function buildBeatmap(json, bm) {
  const d = toV3(json);
  const tp = new TimeProcessor(bm.bpm, d.bpmEvents || []);
  const note = (n, type) => {
    const o = { type, time: num(n.b), posX: num(n.x), posY: num(n.y), color: num(n.c), direction: num(n.d),
      angleOffset: num(n.a), customData: n.customData || {} };
    o.sec = tp.toRealTime(o.time); o.beatAdj = o.time; o.pos = [o.posX, o.posY];
    o.angle = noteAngle(o.direction) - o.angleOffset + (o.direction === ANY ? 180 : 0);
    return o;
  };
  // 原作は読み込み時に並べ替えない＝ファイルに書かれた順のまま判定する（NLMの書き出しは時刻順）
  const colorNotes = (d.colorNotes || []).map(n => note(n, 'color'));
  const bombNotes = (d.bombNotes || []).map(n => note(n, 'bomb'));
  const obstacles = (d.obstacles || []).map(w => {
    const o = { type: 'wall', time: num(w.b), posX: num(w.x), posY: num(w.y), duration: num(w.d), width: num(w.w), height: num(w.h) };
    o.sec = tp.toRealTime(o.time); o.dsec = tp.toRealTime(o.time + o.duration) - o.sec; return o;
  });
  const arcs = (d.sliders || []).map(a => {
    const o = note(a, 'arc');
    Object.assign(o, { angleOffset: 0, lengthMultiplier: num(a.mu, 1), tailTime: num(a.tb), tailPosX: num(a.tx), tailPosY: num(a.ty),
      tailDirection: num(a.tc), tailLengthMultiplier: num(a.tmu, 1), midAnchor: num(a.m) });
    o.angle = noteAngle(o.direction) + (o.direction === ANY ? 180 : 0);
    o.tailSec = tp.toRealTime(o.tailTime); o.tailPos = [o.tailPosX, o.tailPosY];
    o.tailAngle = noteAngle(o.tailDirection) + (o.tailDirection === ANY ? 180 : 0);
    return o;
  });
  const chains = (d.burstSliders || []).map(c => {
    const o = note(c, 'chain');
    Object.assign(o, { angleOffset: 0, tailTime: num(c.tb), tailPosX: num(c.tx), tailPosY: num(c.ty), sliceCount: num(c.sc, 1), squish: num(c.s, 1) });
    o.angle = noteAngle(o.direction) + (o.direction === ANY ? 180 : 0);
    o.tailSec = tp.toRealTime(o.tailTime); o.tailPos = [o.tailPosX, o.tailPosY];
    return o;
  });
  for (const a of arcs) {   // アークの頭/尾と重なるノーツ
    a.headNotes = colorNotes.filter(n => n.time === a.time && n.posX === a.posX && n.posY === a.posY);
    a.tailNotes = colorNotes.filter(n => n.time === a.tailTime && n.posX === a.tailPosX && n.posY === a.tailPosY);
  }
  const links = [];
  for (const c of chains) { c.links = chainLinks(c, tp); links.push(...c.links); }
  const basicEvents = (d.basicBeatmapEvents || []).map(e => ({ type: 'event', time: num(e.b), etype: num(e.et), value: num(e.i),
    floatValue: e.f ?? 1, customData: e.customData || {} }));
  for (const e of basicEvents) e.sec = tp.toRealTime(e.time);
  const colorBoostEvents = (d.colorBoostBeatmapEvents || []).map(e => ({ type: 'boost', time: num(e.b) }));
  const rotationEvents = (d.rotationEvents || []).map(e => ({ type: 'rotation', time: num(e.b), executionTime: num(e.e) }));
  const waypoints = (d.waypoints || []).map(e => ({ type: 'waypoint', time: num(e.b), posX: num(e.x), posY: num(e.y), direction: num(e.d) }));
  const ebg = loadEventBoxGroups(d);
  for (const arr of [colorBoostEvents, rotationEvents, waypoints, ebg.color, ebg.rot, ebg.tra, ebg.fx]) {
    for (const o of arr) { o.sec = tp.toRealTime(o.time); if (o.boxes) for (const b of o.boxes) for (const e of b.events) e.sec = tp.toRealTime(o.time + e.time); }
  }

  const map = { colorNotes, bombNotes, obstacles, arcs, chains, basicEvents, colorBoostEvents, rotationEvents, waypoints, ebg };
  const swings = swingGenerate(colorNotes, tp);
  for (const s of swings) {   // 同時2個の同色ノーツは、並びの線の向きへ角度を寄せる（MapCheckの事前計算）
    if (s.data.length !== 2) continue;
    const [p, q] = s.data;
    if (nearEq(p.time, q.time) && (p.direction !== ANY && q.direction !== ANY
      ? noteAngle(p.direction) === noteAngle(q.direction) && isNoteSwingableRaw(p, q, 30) : true)) {
      const dir = noteAngle(p.direction) || noteAngle(q.direction);
      const a1 = radToDeg(Math.atan2(p.posY - q.posY, p.posX - q.posX)) + 90;
      const a2 = radToDeg(Math.atan2(q.posY - p.posY, q.posX - p.posX)) + 90;
      p.angle = q.angle = lowDiff(dir, a1, 360) > lowDiff(dir, a2, 360) ? a2 : a1;
    }
  }
  const container = [...colorNotes, ...bombNotes, ...chains, ...arcs, ...links].sort(byTime);   // 安定ソート＝同時刻は ノーツ→ボム→チェーン→アーク→リンク
  const env = bm.environment || 'DefaultEnvironment';
  return { tp, map, swings, container, env, info: bm,
    njs: new NoteJumpSpeed(tp.bpm, bm.njs || FALLBACK_NJS[bm.difficulty] || 0, bm.njsOffset || 0) };
}

// ---------- 個別チェック ----------
// 各チェックは [{key, status, label(英語原文), objs?:[...], vars?:{表示用の数値}}] を返す（日本語の文言はNLM側の翻訳）
const R = (key, status, label, objs, vars) => ({ key, status, label, objs: objs || null, vars: vars || null });

const VB_DIFF = { Easy: [0.025, 1.2], Normal: [0.05, 1], Hard: [0.08, 0.75], Expert: [0.1, 0.625], ExpertPlus: [0.1, 0.5] };
function visionBlock(B) {
  const { tp, njs } = B, cont = B.container.filter(n => n.type !== 'arc');
  const [minTime, vmax] = VB_DIFF[B.info.difficulty] || VB_DIFF.ExpertPlus;
  const maxTime = Math.min(tp.toRealTime(njs.hjd, false), vmax);
  let lastL = null, lastR = null; const res = [];
  for (const n of cont) {
    if (lastL) { const dt = n.sec - lastL.sec;
      if (dt >= minTime && dt <= maxTime) { if (n.posX < 2) res.push(n); } else if (dt > maxTime) lastL = null; }
    if (lastR) { const dt = n.sec - lastR.sec;
      if (dt >= minTime && dt <= maxTime) { if (n.posX > 1) res.push(n); } else if (dt > maxTime) lastR = null; }
    if (n.posY === 1 && n.posX === 1) lastL = n;
    if (n.posY === 1 && n.posX === 2) lastR = n;
  }
  return res.length ? [R('visionBlock', STATUS.WARN, 'Vision block', res)] : [];
}

function stackedNote(B) {
  const cn = B.map.colorNotes, res = []; let lastTime = 0;
  for (let i = 0; i < cn.length; i++) {
    if (cn[i].sec < lastTime + 0.01) continue;
    for (let j = i + 1; j < cn.length; j++) {
      if (cn[j].sec > cn[i].sec + 0.01) break;
      if (isInline(cn[j], cn[i])) { res.push(cn[i]); lastTime = cn[i].sec; }
    }
  }
  const bn = B.map.bombNotes, resB = [];
  for (let i = 0; i < bn.length; i++) {
    for (let j = i + 1; j < bn.length; j++) {
      if (bn[j].sec > bn[i].sec + 1) break;
      if (isInline(bn[i], bn[j]) && (B.njs.value < (bn[j].sec - bn[i].sec) * 2 || bn[j].sec < bn[i].sec + 0.02)) resB.push(bn[i]);
    }
  }
  const out = [];
  if (res.length) out.push(R('stackedNote', STATUS.ERROR, 'Stacked note', res));
  if (resB.length) out.push(R('stackedBomb', STATUS.ERROR, 'Stacked bomb', resB));
  return out;
}

const colorAndBomb = B => B.container.filter(n => n.type === 'bomb' || n.type === 'color');
function handclap(B) {
  const nc = colorAndBomb(B), res = []; let lastTime = 0;
  for (let i = 0; i < nc.length; i++) {
    const a = nc[i];
    if (a.type !== 'color' || a.sec < lastTime + 0.01) continue;
    for (let j = i + 1; j < nc.length; j++) {
      const b = nc[j];
      if (b.sec > a.sec + 0.01) break;
      if (b.type !== 'color' || a.color === b.color || a.direction === ANY || b.direction === ANY) continue;
      const d = noteDistance(a, b), pt = (x, y, t) => isNotePointing(x, y, t);
      if ((d <= 1 && pt(a, b, 45) && pt(b, a, 45)) || (d <= 1.5 && pt(a, b, 30) && pt(b, a, 30)) || (d <= 2 && pt(a, b, 15) && pt(b, a, 15))
        || (d <= 1 && !pt(a, b, 135 - 0.001) && !pt(b, a, 135 - 0.001)) || (d <= 1.5 && !pt(a, b, 160 - 0.001) && !pt(b, a, 160 - 0.001))) {
        res.push(a); lastTime = a.sec;
      }
    }
  }
  return res.length ? [R('handclap', STATUS.ERROR, 'Handclap pattern', res)] : [];
}

function hammerHit(B) {
  const nc = colorAndBomb(B), res = []; let lastTime = 0, lastIndex = 0;
  for (let i = 0; i < nc.length; i++) {
    const a = nc[i];
    if (a.type !== 'color' || a.sec < lastTime + 0.01) continue;
    for (let j = lastIndex; j < nc.length; j++) {
      const b = nc[j];
      if (b.sec + 0.125 < a.sec) { lastIndex = j; continue; }
      if (b.sec > a.sec + 0.075) break;
      if (b.type !== 'bomb' || a.direction === ANY) continue;
      if ((noteDistance(a, b) <= 2 && isNotePointing(a, b, 15)) || (noteDistance(a, b) <= 2 && !isNotePointing(a, b, 165 - 0.001))) {
        res.push(a); lastTime = a.sec;
      }
    }
  }
  return res.length ? [R('hammerHit', STATUS.ERROR, 'Hammer hit', res)] : [];
}

function hitboxPath(B) {
  const nc = colorAndBomb(B), res = []; let lastTime = 0;
  for (let i = 0; i < nc.length; i++) {
    const a = nc[i];
    if (a.type !== 'color' || a.sec < lastTime + 0.01 || a.direction === ANY) continue;
    for (let j = i + 1; j < nc.length; j++) {
      const b = nc[j];
      if (b.sec > a.sec + 0.01) break;
      if (b.type === 'color' && a.color === b.color) continue;
      if (noteDistance(a, b) <= 2 && (!isNotePointing(a, b, 150) || (b.type === 'color' && b.direction !== ANY && !isNotePointing(b, a, 150)))) {
        res.push(a); lastTime = a.sec;
      }
    }
  }
  return res.length ? [R('hitboxPath', STATUS.ERROR, 'Hitbox path', res)] : [];
}

function parallelNotes(B) {
  const nc = colorAndBomb(B), res = []; let lastTime = 0;
  for (let i = 0; i < nc.length; i++) {
    const a = nc[i];
    if (a.type !== 'color' || a.sec < lastTime + 0.01) continue;
    for (let j = i + 1; j < nc.length; j++) {
      const b = nc[j];
      if (b.sec > a.sec + 0.01) break;
      if (b.type !== 'color' || a.color !== b.color || a.direction === ANY || b.direction === ANY || lowDiff(a.angle, b.angle, 360) > 45) continue;
      if (!isNoteSwingable(a, b, 30)) { res.push(a); lastTime = a.sec; }
    }
  }
  return res.length ? [R('parallelNotes', STATUS.ERROR, 'Parallel notes', res)] : [];
}

function acceptablePrec(B, prec = [8, 6]) {
  const res = B.swings.map(s => [...s.data].sort(byTime)[0]).filter(n => {
    for (const p of prec) if ((n.beatAdj + 0.001) % (1 / p) < 0.01) return false;
    return true;
  });
  return res.length ? [R('acceptablePrec', STATUS.WARN, 'Off-beat precision', res)] : [];
}

function effectiveBPM(B) {   // しきい値は曲のBPMに合わせて下げる（MapCheckが譜面読込時に行う調整）
  const ebpmThres = round(Math.min(450, B.tp.bpm * 2 * 1.285714), 1), ebpmsThres = round(Math.min(350, B.tp.bpm * 2), 1);
  const base = B.swings.filter(s => s.ebpm > ebpmThres + 0.001).map(s => s.data[0]);
  const sw = B.swings.filter(s => s.ebpmSwing > ebpmsThres + 0.001).map(s => s.data[0]);
  const out = [];
  if (base.length) out.push(R('ebpm', STATUS.WARN, `>${ebpmThres}EBPM warning`, base, { thres: ebpmThres }));
  if (sw.length) out.push(R('ebpmSwing', STATUS.WARN, `>${ebpmsThres}EBPM (swing) warning`, sw, { thres: ebpmsThres }));
  return out;
}

function excessiveDouble(B, threshold = 0.6) {
  const red = new Set(), blue = new Set();
  for (const s of B.swings) { const n = s.data[0]; (n.color === 0 ? red : blue).add(n.time); }
  let both = 0; for (const t of red) if (blue.has(t)) both++;
  const perc = both / Math.max(blue.size, red.size);
  return perc > threshold ? [R('excessiveDouble', STATUS.WARN, `Excessive double (${round(perc * 100, 1)}%)`, null, { perc: round(perc * 100, 1) })] : [];
}

function varySwing(B) {
  const res = B.swings.filter(s => Math.abs(s.minSpeed - s.maxSpeed) > 0.001).map(s => s.data[0]);
  return res.length ? [R('varySwing', STATUS.ERROR, 'Varying swing speed', res)] : [];
}

function slowSlider(B, minSpeed = 0.025) {
  const res = B.swings.filter(s => s.maxSpeed > minSpeed || s.minSpeed > minSpeed).map(s => s.data[0]);
  return res.length ? [R('slowSlider', STATUS.WARN, `Slow slider (>${round(minSpeed * 1000, 1)}ms)`, res, { ms: round(minSpeed * 1000, 1) })] : [];
}

// 「前の角度」を追いかける系（doubleDirectional / inlineAngle）で共通のボム処理
function bombResetsAngle(n, lastAngle, startDot) {
  if (n.type !== 'bomb') return;
  if (n.posY === 0) {
    if (n.posX === 1) { lastAngle[0] = DIR_ANGLE[0]; startDot[0] = null; }
    if (n.posX === 2) { lastAngle[1] = DIR_ANGLE[0]; startDot[1] = null; }
  }
  if (n.posY === 2) {
    if (n.posX === 1) { lastAngle[0] = DIR_ANGLE[1]; startDot[0] = null; }
    if (n.posX === 2) { lastAngle[1] = DIR_ANGLE[1]; startDot[1] = null; }
  }
}

function doubleDirectional(B) {
  const { tp, container } = B, last = {}, lastAngle = {}, startDot = {}, arr = { 0: [], 1: [] }, res = [];
  for (const n of container) {
    if (n.type === 'color' && last[n.color]) {
      const c = n.color;
      if (swingNext(n, last[c], tp, arr[c])) {
        if (startDot[c]) { startDot[c] = null; lastAngle[c] = (lastAngle[c] + 180) % 360; }
        if (checkDirection(n, lastAngle[c], 45, true)) res.push(n);
        if (n.direction === ANY) startDot[c] = n; else lastAngle[c] = n.angle;
        arr[c] = [];
      } else {
        if (startDot[c] && checkDirection(n, lastAngle[c], 45, true)) { res.push(n); startDot[c] = null; lastAngle[c] = n.angle; }
        if (n.direction !== ANY) { startDot[c] = null; lastAngle[c] = n.angle; }
      }
    } else if (n.type === 'color') lastAngle[n.color] = n.angle;
    if (n.type === 'color') { last[n.color] = n; arr[n.color].push(n); }
    bombResetsAngle(n, lastAngle, startDot);
  }
  return res.length ? [R('doubleDirectional', STATUS.WARN, 'Double-directional', res)] : [];
}

function inlineAngle(B, maxTime = 0.15) {
  const { tp, container } = B, last = {}, lastAngle = {}, startDot = {}, arr = { 0: [], 1: [] }, res = [];
  let lastTime = 0, lastIndex = 0;
  const checkInline = (cur, index) => {
    for (let i = index; i < container.length && container[i].sec < cur.sec; i++) {
      const o = container[i];
      if (o.type !== 'color') continue;
      if (noteDistance(cur, o) < 0.25 && cur.sec - o.sec <= maxTime) return true;
    }
    return false;
  };
  for (let i = 0; i < container.length; i++) {
    const n = container[i];
    if (lastTime + maxTime < n.sec) { lastTime = n.sec; lastIndex = i; }
    if (n.type === 'color' && last[n.color]) {
      const c = n.color;
      if (swingNext(n, last[c], tp, arr[c])) {
        if (startDot[c]) { startDot[c] = null; lastAngle[c] = (lastAngle[c] + 180) % 360; }
        if (checkInline(n, lastIndex) && checkDirection(n, lastAngle[c], 90, true)) res.push(n);
        if (n.direction === ANY) startDot[c] = n; else lastAngle[c] = n.angle;
        arr[c] = [];
      } else {
        if (startDot[c] && checkInline(n, lastIndex) && checkDirection(n, lastAngle[c], 90, true)) { res.push(startDot[c]); startDot[c] = null; }
        if (n.direction !== ANY) lastAngle[c] = n.angle;
      }
    } else if (n.type === 'color') lastAngle[n.color] = n.angle;
    if (n.type === 'color') { last[n.color] = n; arr[n.color].push(n); }
    bombResetsAngle(n, lastAngle, startDot);
  }
  return res.length ? [R('inlineAngle', STATUS.WARN, 'Inline sharp angle', res)] : [];
}

function shradoAngle(B, distance = 1, maxTime = 0.25) {
  const { tp } = B, last = {}, lastDir = {}, startDot = {}, arr = { 0: [], 1: [] }, res = [];
  const shr = (cur, prev, type) => cur !== ANY && prev !== ANY && (type === 0 ? prev === 7 : prev === 6) && cur === 0;
  for (const n of B.container) {
    if (n.type !== 'color') continue;
    const c = n.color;
    if (last[c]) {
      const ok = () => gDist(n, last[c]) >= distance && shr(n.direction, lastDir[c], c) && n.sec - last[c].sec <= maxTime;
      if (swingNext(n, last[c], tp, arr[c])) {
        if (startDot[c]) { startDot[c] = null; lastDir[c] = DIR_FLIP[lastDir[c]] ?? 8; }
        if (ok()) res.push(n);
        if (n.direction === ANY) startDot[c] = n; else lastDir[c] = n.direction;
        arr[c] = [];
      } else {
        if (startDot[c] && ok()) { res.push(startDot[c]); startDot[c] = null; }
        if (n.direction !== ANY) lastDir[c] = n.direction;
      }
    } else lastDir[c] = n.direction;
    last[c] = n; arr[c].push(n);
  }
  return res.length ? [R('shradoAngle', STATUS.WARN, 'Shrado angle', res)] : [];
}

function improperWindow(B) {
  const { tp } = B, last = {}, arr = { 0: [], 1: [] }, res = [];
  for (const n of B.container) {
    if (n.type !== 'color') continue;
    const c = n.color;
    if (last[c]) {
      if (swingNext(n, last[c], tp, arr[c])) { last[c] = n; arr[c] = []; }
      else if (isSlantedWindow(n, last[c]) && n.time - last[c].time >= 0.001 && n.direction === last[c].direction
        && n.direction !== ANY && last[c].direction !== ANY) res.push(last[c]);
    } else last[c] = n;
    arr[c].push(n);
  }
  return res.length ? [R('improperWindow', STATUS.ERROR, 'Improper window snap', res)] : [];
}

function hitboxInline(B) {
  const { tp, njs } = B, last = {}, arr = { 0: [], 1: [] }, res = [];
  for (const n of B.map.colorNotes) {
    const c = n.color;
    if (c !== 0 && c !== 1) continue;
    if (last[c] && swingNext(n, last[c], tp, arr[c])) arr[c] = [];
    for (const o of arr[(c + 1) % 2]) {
      if (njs.value < 1.425 / (n.sec - o.sec) && isInline(n, o)) { res.push(n); break; }   // 1.425=セイバー長＋判定の余裕（原作のマジックナンバー）
    }
    last[c] = n; arr[c].push(n);
  }
  return res.length ? [R('hitboxInline', STATUS.RANK, 'Hitbox inline', res)] : [];
}

function hitboxReverseStair(B) {
  const { tp, njs } = B, last = {}, arr = { 0: [], 1: [] }, res = [], K = 0.03414823529;
  for (const n of B.container) {
    if (n.type !== 'color') continue;
    const c = n.color;
    if (last[c] && swingNext(n, last[c], tp, arr[c])) arr[c] = [];
    for (const o of arr[(c + 1) % 2]) {
      if (o.direction === ANY) continue;
      if (!(n.sec > o.sec + 0.01)) continue;
      if (njs.value < 1.425 / (n.sec - o.sec + K) && noteDistance(n, o) <= 1.5 && isNotePointing(n, o, 15)) { res.push(o); break; }
    }
    last[c] = n; arr[c].push(n);
  }
  return res.length ? [R('hitboxReverseStair', STATUS.RANK, 'Hitbox reverse staircase', res)] : [];
}

function hitboxStair(B) {
  const { tp } = B, notes = B.map.colorNotes, hitboxTime = 0.15;
  const last = {}, lastDir = {}, lastSpeed = {}, arr = { 0: [], 1: [] }, res = [];
  const occ = { 0: { posX: 0, posY: 0 }, 1: { posX: 0, posY: 0 } };
  const isDouble = (n, i) => {
    for (let k = i; k < notes.length; k++) {
      if (notes[k].time < n.time + 0.01 && notes[k].color !== n.color) return true;
      if (notes[k].time > n.time + 0.01) return false;
    }
    return false;
  };
  for (let i = 0; i < notes.length; i++) {
    const n = notes[i], c = n.color;
    if (c !== 0 && c !== 1) continue;
    const sp = DIR_SPACE[n.direction] || [0, 0], oc = (c + 1) % 2;
    if (last[c]) {
      if (swingNext(n, last[c], tp, arr[c])) {
        lastSpeed[c] = n.sec - last[c].sec;
        if (n.direction !== ANY) { occ[c].posX = n.posX + sp[0]; occ[c].posY = n.posY + sp[1]; }
        else { occ[c].posX = -1; occ[c].posY = -1; }
        arr[c] = []; lastDir[c] = n.direction;
      } else if (isEndNote(n, last[c], lastDir[c])) {
        if (n.direction !== ANY) { occ[c].posX = n.posX + sp[0]; occ[c].posY = n.posY + sp[1]; lastDir[c] = n.direction; }
        else { const ls = DIR_SPACE[lastDir[c]]; occ[c].posX = n.posX + (ls ? ls[0] : 0); occ[c].posY = n.posY + (ls ? ls[1] : 0); }
      }
      if (last[oc] && n.sec - last[oc].sec !== 0 && n.sec - last[oc].sec < Math.min(hitboxTime, lastSpeed[oc])) {
        if (n.posX === occ[oc].posX && n.posY === occ[oc].posY && !isDouble(n, i)) res.push(n);
      }
    } else {
      if (n.direction !== ANY) { occ[c].posX = n.posX + sp[0]; occ[c].posY = n.posY + sp[1]; }
      else { occ[c].posX = -1; occ[c].posY = -1; }
      lastDir[c] = n.direction;
    }
    last[c] = n; arr[c].push(n);
  }
  return res.length ? [R('hitboxStair', STATUS.RANK, 'Hitbox staircase', res)] : [];
}

// アーク/チェーン: 種類を先頭に寄せてから時刻順（同時刻では対象が先に来る）
const sortTypeFirst = (cont, type) => [...cont].sort((a, b) => a.type !== type ? 1 : b.type !== type ? -1 : 0).sort(byTime);
function improperArc(B) {
  const nc = sortTypeFirst(B.container, 'arc'), res = [];
  const tailAsNote = a => ({ posX: a.posX, posY: a.posY, direction: a.tailDirection, pos: a.tailPos, angle: a.tailAngle });
  const nearTail = (a, o) => !a.tailNotes.length && nearEq(a.tailSec, o.sec, 0.25) && noteDistance(tailAsNote(a), o) <= 1.5 && isNotePointing(tailAsNote(a), o, 15);
  const touches = (a, o) => (a.posX === o.posX && a.posY === o.posY && nearEq(o.time, a.time))
    || (a.tailPosX === o.posX && a.tailPosY === o.posY && nearEq(o.time, a.tailTime)) || nearTail(a, o);
  for (let i = 0; i < nc.length; i++) {
    const a = nc[i];
    if (a.type !== 'arc') continue;
    if (nearEq(a.time, a.tailTime)) { res.push(a); continue; }
    for (let j = i; j < nc.length; j++) {
      const o = nc[j];
      if (o.sec > a.tailSec + 0.25) break;
      if (o.type === 'color' && a.color !== o.color && touches(a, o)) { res.push(a); break; }
      if (o.type === 'bomb' && touches(a, o)) { res.push(a); break; }
    }
  }
  return res.length ? [R('improperArc', STATUS.ERROR, 'Improper arc', res)] : [];
}

function improperChain(B) {
  const nc = sortTypeFirst(B.container, 'chain'), res = [];
  for (let i = 0; i < nc.length; i++) {
    const ch = nc[i];
    if (ch.type !== 'chain') continue;
    let potential = true;
    for (let j = i; j < nc.length; j++) {
      const o = nc[j];
      if (o.type === 'color') {
        if (ch.posX === o.posX && ch.posY === o.posY && o.time <= ch.time + 0.001 && ch.color === o.color
          && ((o.direction !== ANY && ch.direction === o.direction && (ch.sliceCount === 1
            || (vDist(o.pos, ch.tailPos) > 0.1 && ch.sliceCount > 1 && isNotePointing(o, { pos: ch.tailPos }, 60))))
            || (o.direction === ANY && vDist(o.pos, ch.tailPos) > 0.1 && ch.sliceCount > 1 && lowDiff(o.angle, ch.angle, 360) < 5))) {
          potential = false; break;
        }
      }
      if (o.type === 'bomb' && ch.posX === o.posX && ch.posY === o.posY && o.time <= ch.time + 0.001) break;
      if (o.time > ch.time + 0.001) break;
    }
    if (potential) res.push(ch);
  }
  // ランク不可のチェーン（開始16ノーツ以内・範囲外のリンク・詰めすぎ）
  const nc2 = sortTypeFirst(B.container, 'color'), unr = []; let count = 0;
  for (const o of nc2) {
    if (o.type === 'color') count++;
    if (o.type === 'chain') {
      const lastLink = o.links[o.links.length - 1];
      if (count <= 16 || o.sliceCount < 1
        || o.links.some(l => l.pos[0] < -0.5 || l.pos[1] < -0.5 || l.pos[0] > 3.5 || l.pos[1] > 2.5)
        || (lastLink && (o.tailTime - o.time) / noteDistance(lastLink, o) > 0.1)) unr.push(o);
    }
  }
  const out = [];
  if (res.length) out.push(R('improperChain', STATUS.ERROR, 'Improper chain', res));
  if (unr.length) out.push(R('unrankableChain', STATUS.RANK, 'Unrankable chain', unr));
  return out;
}

function oneSaber(B) {
  const cn = B.map.colorNotes, hasBlue = cn.some(n => n.color === 1), hasRed = cn.some(n => n.color === 0);
  return hasBlue !== hasRed ? [R('oneSaber', STATUS.RANK, 'Unintended One Saber')] : [];
}

function colorCheck() {
  // 原作はInfo.datにカスタム色（_colorLeft/_colorRight・colorSchemes）がある時だけ判定する。
  // NLMの書き出しはカスタム色を書かないため、常に対象外（合格）
  return [];
}

// ---- 壁 ----
const isLonger = (o, c, prev = 0) => o.sec + o.dsec > c.sec + c.dsec + prev;
function centerObstacle(B, recovery = 0.25) {
  const res = []; let L = { sec: 0, dsec: 0 }, Rr = { sec: 0, dsec: 0 };
  const near = (o, x) => o.sec > x.sec - recovery && o.sec < x.sec + x.dsec + recovery;
  for (const o of B.map.obstacles) {
    if (!(o.posY < 2 && o.height > 1)) continue;
    if (o.width > 2) { res.push(o); if (isLonger(o, L)) L = o; if (isLonger(o, Rr)) Rr = o; }
    if (o.width === 2) {
      if (o.posX === 0 && isLonger(o, L)) { if (near(o, Rr)) res.push(o); L = o; }
      if (o.posX === 1) { res.push(o); if (isLonger(o, L)) L = o; if (isLonger(o, Rr)) Rr = o; }
      if (o.posX === 2 && isLonger(o, Rr)) { if (near(o, L)) res.push(o); Rr = o; }
    }
    if (o.width === 1) {
      if (o.posX === 1 && isLonger(o, L)) { if (near(o, Rr)) res.push(o); L = o; }
      if (o.posX === 2 && isLonger(o, Rr)) { if (near(o, L)) res.push(o); Rr = o; }
    }
  }
  return res.length ? [R('centerObstacle', STATUS.ERROR, `2-wide center obstacle (<${round(recovery * 1000)}ms)`, res, { ms: round(recovery * 1000) })] : [];
}

function shortObstacle(B, minDuration = 0.015) {
  const res = [], z = () => ({ sec: 0, dsec: 0 });
  let LF = z(), RF = z(), LH = z(), RH = z();
  for (const o of B.map.obstacles) {
    const du = o.dsec;
    if (nearEq(du, 0)) { res.push(o); continue; }
    if (o.posY === 0 && o.height > 2) {
      const full = (side) => {
        if (side === 'L' && isLonger(o, LF)) { if (du < minDuration) res.push(o); LF = o; }
        if (side === 'R' && isLonger(o, RF)) { if (du < minDuration) res.push(o); RF = o; }
      };
      if (o.width > 2 || (o.width > 1 && o.posX === 1)) { full('L'); full('R'); }
      else if (o.width === 2) { if (o.posX === 0) full('L'); else if (o.posX === 2) full('R'); }
      else if (o.width === 1) { if (o.posX === 1) full('L'); else if (o.posX === 2) full('R'); }
    } else if (o.posY === 2 && o.height > 2 && du > 0) {
      const half = (side) => {
        if (side === 'L' && isLonger(o, LH)) { if (du < minDuration && isLonger(o, LF, minDuration) && isLonger(o, LH, minDuration)) res.push(o); LH = o; }
        if (side === 'R' && isLonger(o, RH)) { if (du < minDuration && isLonger(o, RF, minDuration) && isLonger(o, RH, minDuration)) res.push(o); RH = o; }
      };
      if (o.width > 2 || (o.width > 1 && o.posX === 1)) { half('L'); half('R'); }
      else if (o.width === 2) { if (o.posX === 0) half('L'); else if (o.posX === 2) half('R'); }
      else if (o.width === 1) { if (o.posX === 1) half('L'); else if (o.posX === 2) half('R'); }
    }
  }
  return res.length ? [R('shortObstacle', STATUS.WARN, '<15ms obstacle', res)] : [];
}

const isZeroObstacle = o => o.duration === 0 || o.width === 0 || o.height === 0;
function zeroObstacle(B) {
  const res = B.map.obstacles.filter(isZeroObstacle);
  return res.length ? [R('zeroObstacle', STATUS.ERROR, 'Zero value obstacle', res)] : [];
}

// ---- ライト ----
const V2_ENVS = new Set(['DefaultEnvironment', 'OriginsEnvironment', 'TriangleEnvironment', 'NiceEnvironment', 'BigMirrorEnvironment',
  'DragonsEnvironment', 'KDAEnvironment', 'MonstercatEnvironment', 'CrabRaveEnvironment', 'PanicEnvironment', 'RocketEnvironment',
  'GreenDayEnvironment', 'GreenDayGrenadeEnvironment', 'TimbalandEnvironment', 'FitBeatEnvironment', 'LinkinParkEnvironment',
  'BTSEnvironment', 'KaleidoscopeEnvironment', 'InterscopeEnvironment', 'SkrillexEnvironment', 'BillieEnvironment',
  'HalloweenEnvironment', 'GagaEnvironment', 'Halloween2Environment']);
function isLightEvent(type, env) {
  const t = BASIC_TRACKS[env];
  if (!t || !t.k.includes(type)) return true;   // 定義の無い種別はライト扱い（原作どおり）
  return t.l.includes(type);
}
const isOn = v => v === 1 || v === 5 || v === 9, isFlash = v => v === 2 || v === 6 || v === 10, isFade = v => v === 3 || v === 7 || v === 11;

function insufficientLight(B) {
  let count = 0;
  for (let i = B.map.basicEvents.length - 1; i >= 0; i--) {
    const e = B.map.basicEvents[i];
    if (isLightEvent(e.etype, B.env) && e.value !== 0) { count++; if (count > 10) return []; }
  }
  return V2_ENVS.has(B.env) ? [R('insufficientLight', STATUS.RANK, 'Insufficient light event')]
    : [R('unknownLight', STATUS.RANK, 'Unknown light event')];
}

function invalidEventBox(B) {
  const defs = GROUP_TRACKS[B.env];
  if (!defs) return [];
  const ids = Object.keys(defs).map(Number), badId = [], badFilter = [];
  for (const g of [...B.map.ebg.color, ...B.map.ebg.rot, ...B.map.ebg.tra]) {
    if (!ids.includes(g.id)) badId.push(g);
    for (const b of g.boxes) if (b.filter.type === 2 && defs[g.id] != null && b.filter.p0 > defs[g.id]) badFilter.push(g);
  }
  const out = [];
  if (badId.length) out.push(R('invalidEbgId', STATUS.ERROR, 'Invalid event box group ID', badId));
  if (badFilter.length) out.push(R('invalidEbgFilter', STATUS.ERROR, 'Invalid event box filter', badFilter));
  return out;
}

function unlitBomb(B) {
  const bombs = B.map.bombNotes, events = B.map.basicEvents, env = B.env;
  if (V2_ENVS.has(env) || !events.length) return [];
  const common = (BASIC_TRACKS[env] || BASIC_TRACKS.DefaultEnvironment).k;
  // 原作の `ev.type in commonEvent` は配列の添字判定（0〜長さ-1）になっている。結果を合わせるためそのまま
  const lights = events.filter(e => isLightEvent(e.etype, env) && e.etype >= 0 && e.etype < common.length).sort((a, b) => a.etype - b.etype);
  const OFF = 0, ON = 1;
  const state = {}; for (const k of [0, 1, 2, 3, 4, 6, 7, 10, 11]) state[k] = { state: OFF, time: 0, fadeTime: 0 };
  const lit = {}; for (const k of common) { const s = [0, false]; lit[k] = { last: s, states: [s], ptr: 0 }; }
  const fadeTime = 1, reactTime = 0.25;
  const dimCol = c => !!c && ((typeof c[3] === 'number' && c[3] < 0.25) || Math.max(c[0], c[1], c[2]) < 0.25);
  const dark = e => (e.floatValue ?? 1) < 0.25 || e.value === 0 || dimCol(e.customData._color) || dimCol(e.customData.color);
  // 原作は定義外のライト種別(litに無い)の記録へ触れた時点で例外になり、この判定は何も出さずに終わる
  // （v3環境で使われない種別のイベントがある場合など）。続けると「どのボムも暗い」という誤った結果になるので同じく何も出さない
  for (const e of lights) {
    const L = lit[e.etype];
    if (!state[e.etype]) return [];   // 原作の状態表に無い種別（同じく例外）
    if ((isOn(e.value) || isFlash(e.value)) && state[e.etype].state !== ON) {
      if (!L) return [];
      state[e.etype] = { state: ON, time: e.sec, fadeTime: 0 };
      if (L.last[0] >= e.sec) { L.last[0] = e.sec; L.last[1] = true; }
      else { L.last = [e.sec, true]; L.states.push(L.last); }
    }
    if (isFade(e.value)) {
      if (!L) return [];
      state[e.etype] = { state: OFF, time: e.sec, fadeTime };
      if (L.last[0] >= e.sec) L.last[1] = true;
      else { L.last = [e.sec, true]; L.states.push(L.last); }
      L.last = [e.sec + fadeTime, false]; L.states.push(L.last);
    }
    const cur = state[e.etype];
    if (dark(e) && cur.state !== OFF) {
      if (!L) return [];
      const ft = cur.state === ON ? reactTime : Math.min(reactTime, cur.fadeTime);
      state[e.etype] = { state: OFF, time: e.sec, fadeTime: ft };
      L.last = [e.sec + ft, false]; L.states.push(L.last);
    }
  }
  const res = [];
  for (const b of bombs) {
    let isLit = false;
    for (const k in lit) {
      const L = lit[k]; let t = null;
      while (L.ptr < L.states.length) { if (b.sec - reactTime < L.states[L.ptr][0]) break; t = L.states[L.ptr]; L.ptr++; }
      if (t) isLit = isLit || t[1];
      if (isLit) break;
    }
    if (!isLit) res.push(b);
  }
  return res.length ? [R('unlitBomb', STATUS.WARN, 'Unlit bomb', res)] : [];
}

// ---- その他 ----
function invalidObject(B) {
  const m = B.map, out = [];
  const baseNote = o => o.direction >= 0 && o.direction <= 8;
  const onGrid = o => o.posX >= 0 && o.posX <= 3 && o.posY >= 0 && o.posY <= 2;
  const negObs = o => o.posY < 0 || o.duration < 0 || o.width < 0 || o.height < 0;
  const inverse = o => o.time > o.tailTime;
  const filterOk = f => (f.type === 1 || f.type === 2) && f.p0 >= 0 && f.p1 >= 0 && (f.reverse === 0 || f.reverse === 1) && f.chunks >= 0
    && f.random >= 0 && f.random <= 3 && f.limit >= 0 && f.limit <= 1 && f.limitAffectsType >= 0 && f.limitAffectsType <= 3;
  const boxOk = b => (b.beatDistributionType === 1 || b.beatDistributionType === 2) && b.easing >= -1 && b.easing <= 103 && filterOk(b.filter);
  const prevOk = e => e.previous === 0 || e.previous === 1, easeOk = e => e.easing >= -1 && e.easing <= 103, bit = v => v === 0 || v === 1;
  const axisOk = b => b.axis === 0 || b.axis === 1 || b.axis === 2;
  const colorOk = g => g.boxes.every(b => boxOk(b) && (b.brightnessDistributionType === 1 || b.brightnessDistributionType === 2) && bit(b.affectFirst)
    && b.events.every(e => prevOk(e) && easeOk(e) && e.color >= -1 && e.color <= 2 && e.brightness >= 0 && e.frequency >= 0));
  const rotOk = g => g.boxes.every(b => boxOk(b) && (b.rotationDistributionType === 1 || b.rotationDistributionType === 2) && axisOk(b)
    && bit(b.flip) && bit(b.affectFirst) && b.events.every(e => prevOk(e) && easeOk(e) && e.loop >= 0 && e.direction >= 0 && e.direction <= 2));
  const traOk = g => g.boxes.every(b => boxOk(b) && (b.gapDistributionType === 1 || b.gapDistributionType === 2) && axisOk(b)
    && bit(b.flip) && bit(b.affectFirst) && b.events.every(e => prevOk(e) && easeOk(e)));
  const fxOk = g => g.boxes.every(b => boxOk(b) && (b.fxDistributionType === 1 || b.fxDistributionType === 2) && bit(b.affectFirst)
    && b.events.every(e => prevOk(e) && easeOk(e)));
  const evType = t => (t >= 0 && t <= 19) || (t >= 40 && t <= 43) || t === 100 || t === 1000;
  const add = (key, label, arr) => { if (arr.length) out.push(R(key, STATUS.ERROR, label, arr)); };
  add('invalidNote', 'Invalid note', m.colorNotes.filter(o => !(baseNote(o) && onGrid(o))));
  add('invalidBomb', 'Invalid bomb', m.bombNotes.filter(o => !(baseNote(o) && onGrid(o))));
  add('invalidArc', 'Invalid arc', m.arcs.filter(o => !(baseNote(o) && !(inverse(o) || o.posX < 0 || o.posX > 3 || o.tailPosX < 0 || o.tailPosX > 3
    || (o.posX === o.tailPosX && o.posY === o.tailPosY && o.time === o.tailTime)))));
  add('invalidChain', 'Invalid chain', m.chains.filter(o => !baseNote(o)));
  add('invalidObstacle', 'Invalid obstacle', m.obstacles.filter(o => isZeroObstacle(o) || negObs(o)));
  add('invalidRotation', 'Invalid rotation event', m.rotationEvents.filter(o => !(o.executionTime === 0 || o.executionTime === 1)));
  add('invalidWaypoint', 'Invalid waypoint', m.waypoints.filter(o => !(o.direction >= 0 && o.direction <= 9 && o.direction !== 8)));
  add('invalidEvent', 'Invalid event', m.basicEvents.filter(o => !evType(o.etype)));
  add('invalidLightColor', 'Invalid light color event', m.ebg.color.filter(g => !colorOk(g)));
  add('invalidLightRotation', 'Invalid light rotation event', m.ebg.rot.filter(g => !rotOk(g)));
  add('invalidLightTranslation', 'Invalid light translation event', m.ebg.tra.filter(g => !traOk(g)));
  add('invalidFx', 'Invalid FX event', m.ebg.fx.filter(g => !fxOk(g)));
  return out;
}

function outsidePlayable(B, audioDuration) {
  if (!audioDuration) return [];
  const m = B.map, out = [], end = audioDuration;
  const lists = [['Note', m.colorNotes], ['Bomb', m.bombNotes], ['Obstacle', m.obstacles], ['Arc', m.arcs], ['Chain', m.chains],
    ['Rotation Event', m.rotationEvents], ['Basic Event', m.basicEvents], ['Color Boost Event', m.colorBoostEvents], ['Waypoint', m.waypoints],
    ['Light Color Event Box Group', m.ebg.color], ['Light Rotation Event Box Group', m.ebg.rot],
    ['Light Translation Event Box Group', m.ebg.tra], ['FX Event Box Group', m.ebg.fx]];
  for (const [tag, arr] of lists) {
    const s = arr;
    if (s.length && s[0].time < 0) out.push(R('beforeStart', STATUS.ERROR, tag + '(s) before start time', s.filter(o => o.time < 0), { what: tag }));
  }
  for (const [tag, arr] of lists) {
    const s = arr;
    if (s.length && s[s.length - 1].sec > end) out.push(R('afterEnd', STATUS.ERROR, tag + '(s) after end time', s.filter(o => o.sec > end), { what: tag }));
  }
  for (const [tag, arr] of [['Light Color Event', m.ebg.color], ['Light Rotation Event', m.ebg.rot], ['Light Translation Event', m.ebg.tra], ['FX Event', m.ebg.fx]]) {
    const hit = arr.filter(g => g.boxes.some(b => b.events.some(e => e.sec > end)));
    if (hit.length) out.push(R('afterEnd', STATUS.ERROR, tag + '(s) after end time', hit, { what: tag }));
  }
  return out;
}

function hotStart(B, time = 1.5) {
  const t = B.tp.toRealTime(firstInteractiveTime(B.map));
  return t < time ? [R('hotStart', STATUS.WARN, 'Hot start', null, { sec: round(t, 2) })] : [];
}

function njsCheck(B) {
  const { njs, tp } = B, out = [];
  if (B.info.njs === 0) out.push(R('njsUnset', STATUS.ERROR, 'Unset NJS'));
  if (njs.value > 23) out.push(R('njsHigh', STATUS.WARN, `NJS is too high (${round(njs.value, 2)})`, null, { v: round(njs.value, 2) }));
  if (njs.value < 3) out.push(R('njsLow', STATUS.WARN, `NJS is too low (${round(njs.value, 2)})`, null, { v: round(njs.value, 2) }));
  if (njs.jd > 36) out.push(R('jdVeryHigh', STATUS.WARN, 'Very high jump distance', null, { v: round(njs.jd, 2) }));
  if (njs.jd < 18) out.push(R('jdVeryLow', STATUS.WARN, 'Very low jump distance', null, { v: round(njs.jd, 2) }));
  const opt = njs.calcJdOptimal()[1];
  if (njs.jd > opt) out.push(R('jdHigh', STATUS.WARN, `High jump distance warning (>${round(opt, 2)})`, null, { v: round(opt, 2) }));
  const rt = tp.toRealTime(njs.hjd, false);
  if (rt < 0.42) out.push(R('rtQuick', STATUS.WARN, `Very quick reaction time (${round(rt * 1000)}ms)`, null, { ms: round(rt * 1000) }));
  if (njs.calcHjd(0) + njs.offset < HJD_MIN) out.push(R('negOffset', STATUS.WARN, 'Unnecessary negative offset', null, { v: HJD_MIN }));
  return out;
}

function difficultyLabel(B) {
  const l = B.info.label;
  return (l && l.length > 30) ? [R('diffLabel', STATUS.RANK, `Difficulty label is too long (${l.length} characters)`, null, { n: l.length })] : [];
}

// 表示順（MapCheckのCheckOutputOrderどおり）
const DIFF_CHECKS = [invalidObject, outsidePlayable, hotStart, njsCheck, difficultyLabel,
  insufficientLight, invalidEventBox, unlitBomb,
  oneSaber, excessiveDouble, colorCheck, effectiveBPM, acceptablePrec, varySwing, slowSlider, inlineAngle, shradoAngle,
  improperArc, improperChain, improperWindow, hitboxStair, hitboxReverseStair, hitboxInline, hitboxPath, parallelNotes,
  handclap, hammerHit, stackedNote, doubleDirectional, visionBlock,
  shortObstacle, centerObstacle, zeroObstacle];

/** 検査項目の一覧（パネルの「チェックした項目」表示用） */
export const CHECK_NAMES = ['timingDifference', 'invalidObject', 'outsidePlayable', 'hotStart', 'njs', 'difficultyLabel', 'insufficientLight', 'invalidEventBox',
  'unlitBomb', 'oneSaber', 'excessiveDouble', 'colorCheck', 'effectiveBPM', 'acceptablePrec', 'varySwing', 'slowSlider', 'inlineAngle',
  'shradoAngle', 'improperArc', 'improperChain', 'improperWindow', 'hitboxStair', 'hitboxReverseStair', 'hitboxInline', 'hitboxPath',
  'parallelNotes', 'handclap', 'hammerHit', 'stackedNote', 'doubleDirectional', 'visionBlock', 'shortObstacle', 'centerObstacle',
  'zeroObstacle', 'audio', 'coverImage', 'previewTime'];

// 画面へ返す対象オブジェクトの形（拍・種類・位置。NLM側で選択/ジャンプに使う）
function objRef(o) {
  const kind = o.type === 'color' ? 'note' : o.type === 'link' ? 'chain' : (o.type || 'lightbox');   // イベントボックスはtype無し
  const src = o.type === 'link' ? o.chain : o;
  // mc=原作の画面に出る値（検証用。リンクだけは原作が秒を表示する）
  return { beat: src.time, sec: src.sec, kind, x: src.posX, y: src.posY, c: src.color, mc: o.type === 'link' ? o.mcShown : o.time };
}

/**
 * 全チェックを実行する。
 * @param {object} p
 *  p.info   {bpm, environment, previewStart, previewDuration}（書き出すInfo.datと同じ値）
 *  p.diffs  [{difficulty:'Hard', json:<書き出す.datのJSON>, njs, njsOffset, label?}]
 *  p.audioDuration  書き出されるsong.eggの長さ（秒）。音源が無ければ null
 *  p.cover  {w,h}（カバー画像の画素数）。無ければ null
 * @returns {{general: object[], diffs: {difficulty:string, results:object[], error?:string}[]}}
 */
export function runMapCheck(p) {
  const general = [];
  const ad = p.audioDuration;
  if (ad && ad < 20) general.push(R('audioShort', STATUS.RANK, 'Unrankable audio length', null, { sec: round(ad, 2) }));
  else if (!ad) general.push(R('noAudio', STATUS.INFO, 'No audio'));
  if (p.cover) {
    if (p.cover.w !== p.cover.h) general.push(R('coverNotSquare', STATUS.ERROR, 'Cover image is not square', null, { w: p.cover.w, h: p.cover.h }));
    if (p.cover.w < 256 || p.cover.h < 256) general.push(R('coverSmall', STATUS.ERROR, 'Cover image is too small', null, { w: p.cover.w, h: p.cover.h }));
  } else general.push(R('noCover', STATUS.INFO, 'No cover image'));
  if (p.info.previewStart === 12 && p.info.previewDuration === 10) general.push(R('previewDefault', STATUS.INFO, 'Default preview time'));

  const built = {}, errors = {};
  for (const d of p.diffs) {
    try {
      built[d.difficulty] = buildBeatmap(d.json, { bpm: p.info.bpm, environment: p.info.environment, difficulty: d.difficulty,
        njs: d.njs, njsOffset: d.njsOffset, label: d.label || '' });
    } catch (e) { errors[d.difficulty] = String(e && e.message || e); }
  }
  const diffs = [];
  for (const d of p.diffs) {
    const results = [], B = built[d.difficulty];
    if (!B) { diffs.push({ difficulty: d.difficulty, results, error: errors[d.difficulty] }); continue; }
    for (const fn of DIFF_CHECKS) {
      try { results.push(...(fn === outsidePlayable ? fn(B, ad) : fn(B))); }
      catch (e) { results.push(R('checkFailed', STATUS.INFO, 'Check failed', null, { name: fn.name, err: String(e && e.message || e) })); }
    }
    results.unshift(...timingDifference(B, built));   // 原作の表示順ではタイミング差が先頭
    for (const r of results) if (r.objs) r.objs = r.objs.map(objRef).sort((a, b) => a.beat - b.beat);
    diffs.push({ difficulty: d.difficulty, results });
  }
  return { general, diffs };
}

// 1つ上の難易度に無いタイミングでスイングしている箇所（情報のみ）
const DIFF_RANK = { Easy: 1, Normal: 3, Hard: 5, Expert: 7, ExpertPlus: 9 };
function timingDifference(B, built) {
  const cur = DIFF_RANK[B.info.difficulty];
  const above = Object.keys(built).filter(k => DIFF_RANK[k] > cur).sort((a, b) => DIFF_RANK[a] - DIFF_RANK[b])[0];
  if (!above) return [];
  const aboveTimes = new Set(built[above].swings.map(s => s.time));
  const res = B.swings.filter(s => !aboveTimes.has(s.time)).map(s => s.data[0]);
  return res.length ? [R('timingDifference', STATUS.INFO, 'Timing difference', res, { above })] : [];
}

// テスト・検証用に内部の計算も出しておく
export const _internal = { buildBeatmap, TimeProcessor, NoteJumpSpeed, swingGenerate, DIFF_CHECKS };
// NLM版BL評価リスト（blcriteria.js）が使う基本部品
export const _shared = { buildBeatmap, noteAngle, lowDiff, DIR_SPACE, ANY, V2_ENVS, BASIC_TRACKS };

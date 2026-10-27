// NLM版 BeatLeader評価リスト。
// BeatLeader公式の文章の基準（https://beatleader.wiki/en/ranking/rules/criteria ・下のCRITERIA_DATE時点）を、
// 項目番号どおりに並べた判定表。BS Map Check（mapcheck.js）とは別物で、公式ツールや審査の結果ではない。
//  - 数値で決まる項目（秒数・拍・位置・値の範囲）は基準の文面どおりに判定する（auto）
//  - 文面が図や審査員の判断に頼る項目は「要確認」の候補だけ出す（cand）。一部は BS Map Check の判定を候補として流用
//  - 人が聞く/見るしかない項目（タイミング・メタデータの正しさ等）は「手動確認」の行として残す（manual）
//  - NLMの書き出しでは起こり得ない項目は「対象外」（na）
// 文面に定義が無く解釈した箇所は、各判定のコメントと画面の注記（*Note）に書いてある。
import { _shared } from './mapcheck.js';

const { buildBeatmap, noteAngle, lowDiff, DIR_SPACE, ANY, V2_ENVS, BASIC_TRACKS } = _shared;
export const CRITERIA_DATE = '2026-09-29';
export const BL = { FAIL: 'fail', CHECK: 'check', PASS: 'pass', PARTIAL: 'partial', MANUAL: 'manual', NA: 'na' };

const EPS = 1e-6;
const mod = (x, m) => ((x % m) + m) % m;
const sdiff = (a, b) => { const d = mod(a - b + 180, 360) - 180; return d === -180 ? 180 : d; };   // aからbを引いた符号付きの角度差（-180〜180）
const round = (v, d = 0) => { const p = 10 ** d; return Math.round(v * p) / p; };
const segAngle = (a, b) => Math.atan2(b[1] - a[1], b[0] - a[0]) * 180 / Math.PI + 90;   // 移動方向を「下=0」の角度で
// 角度のずらし（v3 の a・反時計回り）は向きに足す（Beat Saber・BeatLeader の解析と同じ。2026-10-26 まで引いていて、ずらし付きのスライダーが R4.B で違反になった）
const cutAngle = n => noteAngle(n.direction) + (n.angleOffset || 0);
const covers = (w, col) => w.width > 0 ? (col >= w.posX && col < w.posX + w.width) : false;
// 壁の縦の範囲（v3の層単位）。高さがマイナスなら下へ伸びる
const wallY = w => w.height >= 0 ? [w.posY, w.posY + w.height] : [w.posY + w.height, w.posY];
// 頭の高さを塞ぐ壁（しゃがんでもくぐれない）／頭上の壁（しゃがむ壁）
const blocksStand = w => w.height > 0 && w.posY < 2 && w.posY + w.height > 2;
const overhead = w => w.height > 0 && w.posY >= 2;
const middleWall = w => covers(w, 1) || covers(w, 2);

// 画面へ返す対象（拍・種類・位置。NLM側でジャンプ/選択に使う＝mapcheck.jsのobjRefと同じ形）
function ref(o) {
  if (o.type === 'link') return { beat: o.chain.time, sec: o.chain.sec, kind: 'chain', x: o.chain.posX, y: o.chain.posY, c: o.chain.color };
  const kind = o.type === 'color' ? 'note' : o.type;
  return { beat: o.time, sec: o.sec, kind, x: o.posX, y: o.posY, c: o.color };
}
const F = (d, status, key, vars, objs) => ({ d: d || null, status, key, vars: vars || null, objs: objs && objs.length ? objs : null });

// ---- 基準の一覧（項目番号・種類・判定）。文言は blcriteria-panel 側の表（bl.r.<id>）----
// kind: auto=文面どおり自動判定 / partial=一部を自動判定（残りは目視） / cand=候補を出すだけ / manual=手動 / na=対象外
export const RULES = [
  { id: 'R1.A.1', kind: 'manual' }, { id: 'R1.A.2', kind: 'manual' },
  { id: 'R1.A.3', kind: 'partial', g: audioFormat }, { id: 'R1.A.4', kind: 'auto', g: cover },
  { id: 'R1.B.1', kind: 'auto', g: songTimeOffset }, { id: 'R1.B.2', kind: 'auto', g: shuffle },
  { id: 'R1.B.3', kind: 'auto', g: colorSchemes }, { id: 'R1.B.4', kind: 'auto', f: wallValues },
  { id: 'R1.B.5', kind: 'auto', f: chainSquish }, { id: 'R1.B.6', kind: 'auto', f: beatRange },
  { id: 'R1.B.7', kind: 'auto', f: wallEnd }, { id: 'R1.B.8', kind: 'auto', f: njsEasing },
  { id: 'R1.C', kind: 'auto', g: requirements },
  { id: 'R1.D.1', kind: 'auto', f: leadTime }, { id: 'R1.D.2', kind: 'auto', f: tailTime },
  { id: 'R1.E', kind: 'manual' }, { id: 'R1.F', kind: 'auto', f: mapLength }, { id: 'R1.G', kind: 'manual' },
  { id: 'R2.A', kind: 'manual' }, { id: 'R2.B', kind: 'manual' }, { id: 'R2.C', kind: 'manual' },
  { id: 'R3.A.1', kind: 'auto', f: zIntersect }, { id: 'R3.A.2', kind: 'auto', f: inWall },
  { id: 'R3.B', kind: 'cand', f: preSwingBlock }, { id: 'R3.C', kind: 'cand', f: withNjsBaseNote(fromMc(['hitboxStair', 'hitboxReverseStair', 'hitboxInline', 'hitboxPath'])) },
  { id: 'R4.A.1', kind: 'manual' }, { id: 'R4.A.2', kind: 'cand', f: fromMc(['varySwing']) },
  { id: 'R4.A.3', kind: 'cand', f: sliderPrecision }, { id: 'R4.A.4', kind: 'manual', f: precisionList },
  { id: 'R4.A.5', kind: 'manual' }, { id: 'R4.A.6', kind: 'cand', f: chainDuration },
  { id: 'R4.B.1', kind: 'auto', f: swingAngle }, { id: 'R4.B.2', kind: 'auto', f: swingOneWay }, { id: 'R4.B.3', kind: 'manual' },
  { id: 'R4.C', kind: 'cand', f: fromMc(['handclap']) },
  { id: 'R5.A', kind: 'cand', f: visionBlock, input: 'stars' },
  { id: 'R5.B.1', kind: 'manual' }, { id: 'R5.B.3', kind: 'cand', f: wallHidesSpawn }, { id: 'R5.C', kind: 'manual' },
  { id: 'R6.A', kind: 'auto', f: chainFirst16 }, { id: 'R6.B.1', kind: 'auto', f: chainReverse },
  { id: 'R6.B.2', kind: 'auto', f: chainPath }, { id: 'R6.C.1', kind: 'auto', f: chainHeadGrid },
  { id: 'R6.C.2', kind: 'auto', f: chainLinkGrid }, { id: 'R6.D', kind: 'auto', f: chainDensity },
  { id: 'R6.E', kind: 'auto', f: chainGap }, { id: 'R6.F', kind: 'auto', f: arcBomb },
  { id: 'R6.G.1', kind: 'auto', f: chainHead }, { id: 'R6.G.2', kind: 'auto', f: chainSlices },
  { id: 'R7.A', kind: 'cand', f: bombSwingPath }, { id: 'R7.B', kind: 'cand', f: bombLight }, { id: 'R7.C', kind: 'manual' },
  { id: 'R8.A.1', kind: 'manual' }, { id: 'R8.A.2', kind: 'cand', f: wallAvoid },
  { id: 'R8.A.3', kind: 'cand', f: dodgeRate }, { id: 'R8.B', kind: 'auto', f: outerLane },
  { id: 'R8.C', kind: 'auto', f: legalWall }, { id: 'R8.D.1', kind: 'cand', f: crouchBottom },
  { id: 'R8.D.2', kind: 'auto', f: crouchTop },
  { id: 'R9', kind: 'na', f: njsEvents },
  { id: 'R10.A', kind: 'auto', f: lightDensity }, { id: 'R10.B', kind: 'manual' },
  { id: 'R11.A', kind: 'manual' }, { id: 'R11.B', kind: 'cand', g: metaLetters }, { id: 'R11.C', kind: 'cand', g: metaSymbols },
  { id: 'R11.D.1', kind: 'manual' }, { id: 'R11.D.2', kind: 'cand', g: nameTags }, { id: 'R11.E', kind: 'manual' },
  { id: 'R11.F.1', kind: 'manual' }, { id: 'R11.F.2', kind: 'cand', g: authorTags },
  { id: 'R11.G', kind: 'partial', g: mapperField }, { id: 'R11.H.1', kind: 'auto', g: diffNames }, { id: 'R11.H.5', kind: 'cand', g: starOrder },
  { id: 'R11.I', kind: 'manual' }, { id: 'R11.J', kind: 'manual' },
];
export const SECTIONS = ['R1', 'R2', 'R3', 'R4', 'R5', 'R6', 'R7', 'R8', 'R9', 'R10', 'R11'];

/**
 * @param p  runMapCheck と同じ入力＋ p.meta{songName,subName,author,mapper} / p.infoRaw{songTimeOffset,shuffle,shufflePeriod,colorSchemes,requirements}
 *           / p.cover{w,h,name} / p.stars{難易度:{star,tech}}（視界ブロックの式・★の並びに使う。空なら判定しない）
 *           / p.diffs[i].srcLightBoxes（読み込んだ元の譜面にあったライトボックスのグループの数。無ければ0）
 * @param mc runMapCheck の結果（候補の流用元）
 */
export function runBlCriteria(p, mc) {
  const built = {};
  for (const d of p.diffs) {
    try {
      const B = buildBeatmap(d.json, { bpm: p.info.bpm, environment: p.info.environment, difficulty: d.difficulty, njs: d.njs, njsOffset: d.njsOffset });
      prep(B, d.json, p.audioDuration);
      B.srcLightBoxes = Math.max(0, +d.srcLightBoxes || 0);   // 元の譜面にあったライトボックスのグループの数（NLM は読めない。R10.A・R7.B を対象外にする）
      built[d.difficulty] = B;
    } catch (_) { /* 読めない難易度は BS Map Check 側がエラーを出す */ }
  }
  const mcBy = {}; for (const d of (mc && mc.diffs) || []) mcBy[d.difficulty] = d.results;
  const ctx = { p, built, mcBy };
  const rules = RULES.map(rule => {
    const fs = [];
    try {
      if (rule.g) fs.push(...rule.g(ctx));
      if (rule.f) for (const dn of Object.keys(built)) for (const x of rule.f(built[dn], ctx, dn)) fs.push({ ...x, d: dn });
    } catch (e) { fs.push(F(null, BL.CHECK, 'failed', { err: String(e && e.message || e) })); }
    return { id: rule.id, kind: rule.kind, input: rule.input || null, status: ruleStatus(rule.kind, fs), findings: fs };
  });
  return { rules, diffs: Object.keys(built), date: CRITERIA_DATE };
}
function ruleStatus(kind, fs) {
  if (fs.some(f => f.status === BL.FAIL)) return BL.FAIL;
  if (fs.some(f => f.status === BL.CHECK)) return BL.CHECK;
  if (fs.some(f => f.status === BL.MANUAL)) return BL.MANUAL;   // 入力が足りず判定しきれない（★の並び）
  return { auto: BL.PASS, partial: BL.PARTIAL, cand: BL.PASS, manual: BL.MANUAL, na: BL.NA }[kind];
}

// ---- 下ごしらえ: 正しいチェーンのリンク位置・チェーンの頭のノーツ・当たる物の一覧 ----
// （mapcheck.js のリンク位置は原作の計算のクセを再現しているので、ここではゲームどおりに計算し直す）
function prep(B, json, audioSec) {
  const { tp, map } = B;
  B.njsEvents = Array.isArray(json.njsEvents) ? json.njsEvents : null;
  B.njsEventData = Array.isArray(json.njsEventData) ? json.njsEventData : null;
  B.njsVar = njsTimeline(B);   // v4 の NJS の変化（NLM は v4 の譜面を読んだ時に入力へ足す・2026-10-27）。無ければ null
  for (const ch of map.chains) {
    const a = ch.direction === ANY ? 0 : noteAngle(ch.direction);   // R6.B.2: 頭が点ノーツなら下向きとみなす
    ch.headAngle = a;
    const p0 = [ch.posX, ch.posY], p2 = [ch.tailPosX, ch.tailPosY];
    const mag = Math.hypot(p2[0] - p0[0], p2[1] - p0[1]), r = (a - 90) * Math.PI / 180;
    const p1 = [p0[0] + Math.cos(r) * mag / 2, p0[1] + Math.sin(r) * mag / 2];
    ch.pts = [p0]; ch.blLinks = [];
    for (let i = 1; i < ch.sliceCount; i++) {
      const u = i / (ch.sliceCount - 1), t = u * ch.squish, n = 1 - t;
      const pos = [n * n * p0[0] + 2 * n * t * p1[0] + t * t * p2[0], n * n * p0[1] + 2 * n * t * p1[1] + t * t * p2[1]];
      const time = ch.time + (ch.tailTime - ch.time) * u;
      const l = { type: 'link', time, sec: tp.toRealTime(time), color: ch.color, pos, cx: Math.round(pos[0]), cy: Math.round(pos[1]), chain: ch };
      ch.pts.push(pos); ch.blLinks.push(l);
    }
    ch.head = map.colorNotes.find(n => Math.abs(n.time - ch.time) < 0.001 && n.posX === ch.posX && n.posY === ch.posY && n.color === ch.color) || null;
    if (ch.head) ch.head.chainOf = ch;
  }
  const cell = o => o.type === 'link' ? [o.cx, o.cy] : [o.posX, o.posY];
  B.cell = cell;
  B.links = map.chains.flatMap(c => c.blLinks);
  B.hittable = [...map.colorNotes, ...map.bombNotes, ...B.links].sort((a, b) => a.sec - b.sec);
  B.notesByColor = { 0: [], 1: [] };
  for (const n of [...map.colorNotes].sort((a, b) => a.sec - b.sec)) if (n.color === 0 || n.color === 1) B.notesByColor[n.color].push(n);
  B.walls = [...map.obstacles].sort((a, b) => a.sec - b.sec);
  B.maxWallSec = B.walls.reduce((m, w) => Math.max(m, w.dsec), 0);
  // 複数ノーツのスイング: 同じ色で70ms以内（窓は80ms）に続くノーツ。向きが90度を「超えて」変わる（折り返す）か同じマスなら次のスイング。
  // BS Map Check は90度ちょうどでも分けるため、45度ルール（R4.B）の判定には使えない。
  // 次の2つも次のスイング（2026-10-26。速い連打で1/4拍が70〜80ms未満になる譜面で、別のスイングを1つにまとめていた）:
  //  rev＝最後の矢印の向きと90度を超えて逆へ動いた（点ノーツも）／zig＝移動の向きが90度を超えて折り返した（点ノーツの上下の往復）
  B.blSwings = [];
  for (const c of [0, 1]) {
    let cur = [];
    for (const n of B.notesByColor[c]) {
      const prev = cur[cur.length - 1];
      const dt = prev ? n.sec - prev.sec : Infinity, far = Math.hypot(n.posX - prev?.posX, n.posY - prev?.posY) > 1.8;
      const turn = n.direction !== ANY && cur.some(o => o.direction !== ANY && Math.abs(sdiff(cutAngle(n), cutAngle(o))) > 90 + 1e-3);
      const same = cur.some(o => o.posX === n.posX && o.posY === n.posY);
      const moved = prev && (n.posX !== prev.posX || n.posY !== prev.posY), seg = moved ? segAngle([prev.posX, prev.posY], [n.posX, n.posY]) : 0;
      const la = [...cur].reverse().find(o => o.direction !== ANY);
      const rev = !!(moved && la && Math.abs(sdiff(seg, cutAngle(la))) > 90 + 1e-3);
      const pp = moved && [...cur].reverse().find(o => o.posX !== prev.posX || o.posY !== prev.posY);
      const zig = !!(pp && Math.abs(sdiff(seg, segAngle([pp.posX, pp.posY], [prev.posX, prev.posY]))) > 90 + 1e-3);
      if (!prev || dt > (far ? 0.08 : 0.07) || (dt > 0.005 && (turn || rev || zig)) || same) { if (cur.length) B.blSwings.push(cur); cur = []; }
      cur.push(n);
    }
    if (cur.length) B.blSwings.push(cur);
  }
  B.endBeat = audioSec ? tp.toBeatTime(audioSec) : null;   // 曲の最後の拍（エディタの最終拍）
  // 時間を飛ばす区間（拍）: BPM を一瞬とても大きくして（ランク譜面では 100000）、その間の拍をほぼ0秒で過ぎる演出。
  // 中の物はゲームでもほぼ同時に出るので、秒で決まる判定（R3.A.1・R8.C）が文面どおりなら違反になる。違反ではなく要確認にする（2026-10-26・利用者の決定）
  const bev = (Array.isArray(json.bpmEvents) ? json.bpmEvents : []).map(e => ({ b: +(e.b ?? 0), m: +e.m })).filter(e => isFinite(e.b) && e.m > 0).sort((a, b) => a.b - b.b);
  B.skips = bev.map((e, i) => e.m >= SKIP_BPM ? [e.b, i + 1 < bev.length ? bev[i + 1].b : Infinity] : null).filter(Boolean);
}

// v4 の NJS の変化（njsEvents{b,i}＋njsEventData{p,e,d}）→ 秒ごとの NJS（2026-10-27）。BSMG Wiki の v4 の頁: d＝Info.dat の基本の NJS との差、
// e＝前の変化の拍からこの変化の拍までのイージング、p＝前の変化の値を使う（その間は変わらない）。最初の変化の前は基本の NJS。→ {n, at(秒)} か null
function njsTimeline(B) {
  const evs = B.njsEvents, data = B.njsEventData;
  if (!evs || !evs.length || !data) return null;
  const list = [];
  for (const o of evs) {
    const q = o && data[Number.isInteger(o.i) ? o.i : 0];
    if (!o || !q) continue;
    const b = +o.b || 0;
    list.push({ sec: B.tp.toRealTime(b), p: q.p ? 1 : 0, e: Number.isInteger(q.e) ? q.e : 0, d: +q.d || 0 });
  }
  if (!list.length) return null;
  list.sort((a, b) => a.sec - b.sec);
  let prev = 0;
  for (const x of list) { x.v = x.p ? prev : x.d; prev = x.v; }
  const base = B.njs.value;
  const at = sec => {
    let lo = 0, hi = list.length;   // sec より後の最初の変化
    while (lo < hi) { const m = (lo + hi) >> 1; if (list[m].sec <= sec) lo = m + 1; else hi = m; }
    if (lo === 0) return base;
    if (lo >= list.length) return base + list[list.length - 1].v;
    const pv = list[lo - 1], nx = list[lo], span = nx.sec - pv.sec;
    return base + pv.v + (nx.v - pv.v) * ease(nx.e, span > 0 ? (sec - pv.sec) / span : 1);
  };
  return { n: list.length, at };
}
// イージング（Beat Saber の番号: -1=なし 0=Linear 1〜3=Quad 4〜6=Sine 7〜9=Cubic 10〜12=Quart 13〜15=Quint 16〜18=Expo 19〜21=Circ 22〜24=Back
// 25〜27=Elastic 28〜30=Bounce。各3つは In・Out・InOut）。100〜102（BS独自の InOut の Back・Elastic・Bounce）は普通の InOut で近似。t は 0〜1。式は一般的なイージングの式
const bounceOut = t => { const n = 7.5625, d = 2.75;
  if (t < 1 / d) return n * t * t;
  if (t < 2 / d) { t -= 1.5 / d; return n * t * t + 0.75; }
  if (t < 2.5 / d) { t -= 2.25 / d; return n * t * t + 0.9375; }
  t -= 2.625 / d; return n * t * t + 0.984375; };
const EASE_IN = {
  1: t => t * t, 4: t => 1 - Math.cos(t * Math.PI / 2), 7: t => t ** 3, 10: t => t ** 4, 13: t => t ** 5,
  16: t => t <= 0 ? 0 : 2 ** (10 * t - 10), 19: t => 1 - Math.sqrt(Math.max(0, 1 - t * t)),
  22: t => 2.70158 * t ** 3 - 1.70158 * t * t,
  25: t => t <= 0 ? 0 : t >= 1 ? 1 : -(2 ** (10 * t - 10)) * Math.sin((t * 10 - 10.75) * 2 * Math.PI / 3),
  28: t => 1 - bounceOut(1 - t),
};
function ease(e, t) {
  t = Math.min(1, Math.max(0, t));
  if (e === -1) return t >= 1 ? 1 : 0;   // なし＝変化の拍で一度に変わる
  const base = e >= 100 ? [22, 25, 28][e - 100] : e >= 1 && e <= 30 ? Math.floor((e - 1) / 3) * 3 + 1 : 0;
  const f = EASE_IN[base];
  if (!f) return t;   // Linear（と知らない番号）
  const kind = e >= 100 ? 2 : (e - 1) % 3;
  if (kind === 0) return f(t);
  if (kind === 1) return 1 - f(1 - t);
  return t < 0.5 ? f(2 * t) / 2 : 1 - f(2 - 2 * t) / 2;
}

// ---------- R1 全般 ----------
function audioFormat({ p }) {
  if (!p.audioDuration) return [F(null, BL.CHECK, 'noAudio')];
  return [F(null, 'note', 'oggOk')];
}
function cover({ p }) {
  const c = p.cover;
  if (!c) return [F(null, BL.FAIL, 'noCover')];
  const out = [];
  if (c.w !== c.h) out.push(F(null, BL.FAIL, 'coverRatio', { w: c.w, h: c.h }));
  if (c.w < 256 || c.h < 256) out.push(F(null, BL.FAIL, 'coverSize', { w: c.w, h: c.h }));
  if (c.name && !/\.(png|jpe?g)$/i.test(c.name)) out.push(F(null, BL.FAIL, 'coverFormat', { name: c.name }));
  return out;
}
function songTimeOffset({ p }) {
  const v = +(p.infoRaw && p.infoRaw.songTimeOffset) || 0;
  return v !== 0 ? [F(null, BL.FAIL, 'songTimeOffset', { v })] : [];
}
function shuffle({ p }) {
  const r = p.infoRaw || {}, s = +r.shuffle || 0, sp = +r.shufflePeriod || 0;
  return s !== 0 || sp !== 0 ? [F(null, BL.FAIL, 'shuffle', { s, sp })] : [];
}
function colorSchemes({ p }) {
  const list = (p.infoRaw && p.infoRaw.colorSchemes) || [];
  if (!list.length) return [F(null, 'note', 'noSchemes')];
  const need = ['saberAColor', 'saberBColor', 'environmentColor0', 'environmentColor1', 'obstacleColor', 'environmentColor0Boost', 'environmentColor1Boost'];
  const bad = list.filter(s => need.some(k => !(s.colorScheme || s)[k]));
  return bad.length ? [F(null, BL.FAIL, 'schemeMissing', { n: bad.length })] : [];
}
function requirements({ p }) {
  const req = (p.infoRaw && p.infoRaw.requirements) || [];
  return req.length ? [F(null, BL.FAIL, 'requirements', { list: req.join(', ') })] : [];
}
function wallValues(B) {
  const out = [], bad = B.walls.filter(w => w.width <= 0 || w.duration <= 0 || w.height === 0);
  if (bad.length) out.push(F(null, BL.FAIL, 'wallZero', null, bad.map(ref)));
  // 高さがマイナスの壁は、4レーン×3段の枠の中へ入り込まなければ可
  const neg = B.walls.filter(w => {
    if (!(w.height < 0) || w.width <= 0) return false;
    const [lo, hi] = wallY(w), xin = w.posX < 4 && w.posX + w.width > 0;
    return xin && hi > 0 && lo < 3;
  });
  if (neg.length) out.push(F(null, BL.FAIL, 'wallNegIn', null, neg.map(ref)));
  return out;
}
function chainSquish(B) {
  const bad = B.map.chains.filter(c => !(c.squish > 0));
  return bad.length ? [F(null, BL.FAIL, 'squish', null, bad.map(ref))] : [];
}
// 用語集: Object = ノーツ・チェーン・アーク・ボム・壁（ライトイベントは含まない）
function beatRange(B) {
  const m = B.map, end = B.endBeat, out = [];
  const all = [...m.colorNotes, ...m.bombNotes, ...m.obstacles, ...m.arcs, ...m.chains];
  const neg = all.filter(o => o.time < 0 || (o.tailTime != null && o.tailTime < 0));
  if (neg.length) out.push(F(null, BL.FAIL, 'beatNeg', null, neg.map(ref)));
  if (end == null) { out.push(F(null, BL.CHECK, 'noAudioEnd')); return out; }
  const over = all.filter(o => o.time > end + EPS || (o.tailTime != null && o.tailTime > end + EPS));
  if (over.length) out.push(F(null, BL.FAIL, 'beatOver', { end: round(end, 3) }, over.map(ref)));
  return out;
}
function wallEnd(B) {
  if (B.endBeat == null) return [F(null, BL.CHECK, 'noAudioEnd')];
  const bad = B.walls.filter(w => w.time + w.duration > B.endBeat + EPS);
  return bad.length ? [F(null, BL.FAIL, 'wallEnd', { end: round(B.endBeat, 3) }, bad.map(ref))] : [];
}
// v4のNJSイベント（NLMのv3書き出しには無い）。BSのイージング番号: -1=なし 0=Linear 1〜3=Quad 4〜6=Sine 7〜9=Cubic
// 10〜12=Quart 13〜15=Quint 16〜18=Expo 19〜21=Circ 22〜24=Back 25〜27=Elastic 28〜30=Bounce 100〜103=BS独自。Sine〜Expoは使用不可
const EASE_BAD = new Set([4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18]);
function njsEasing(B) {
  if (!B.njsEventData) return [F(null, 'note', 'noNjsEvents')];
  const bad = B.njsEventData.filter(e => { const x = e.e ?? 0; return !Number.isInteger(x) || !((x >= -1 && x <= 30) || (x >= 100 && x <= 103)) || EASE_BAD.has(x); });
  return bad.length ? [F(null, BL.FAIL, 'njsEasing', { n: bad.length })] : [];
}
// 用語集: Interactable = ノーツ・ボム・チェーン＋真ん中2レーンにかかる壁
function interactables(B) {
  const m = B.map, out = [];
  for (const n of [...m.colorNotes, ...m.bombNotes]) out.push({ o: n, s: n.sec, e: n.sec });
  for (const c of m.chains) out.push({ o: c, s: c.sec, e: c.tailSec });
  for (const w of B.walls) if (middleWall(w)) out.push({ o: w, s: w.sec, e: w.sec + w.dsec });
  return out;
}
function leadTime(B) {
  const it = interactables(B); if (!it.length) return [];
  const first = it.reduce((a, b) => b.s < a.s ? b : a), s = first.s;
  if (s < 1.5) return [F(null, BL.FAIL, 'leadShort', { sec: round(s, 3) }, [ref(first.o)])];
  if (s < 2) return [F(null, 'note', 'leadRec', { sec: round(s, 3) })];
  return [];
}
function tailTime(B, { p }) {
  if (!p.audioDuration) return [F(null, BL.CHECK, 'noAudioEnd')];
  const it = interactables(B); if (!it.length) return [];
  const last = it.reduce((a, b) => b.e > a.e ? b : a), rest = p.audioDuration - last.e;
  return rest < 2 ? [F(null, BL.FAIL, 'tailShort', { sec: round(rest, 3) }, [ref(last.o)])] : [];
}
function mapLength(B) {
  const ns = B.map.colorNotes; if (!ns.length) return [];
  const s = Math.min(...ns.map(n => n.sec));
  const e = Math.max(...ns.map(n => n.sec), ...B.map.chains.map(c => c.tailSec));
  return e - s < 45 ? [F(null, BL.FAIL, 'mapShort', { sec: round(e - s, 2) })] : [];
}

// ---------- R3 配置 ----------
// R3.A.1: 同じマスで奥行き0.5m以内（(拍差)/(BPM/60)×NJS < 0.5m）。アークは対象外。同じチェーンの頭とリンク同士は除く。
// 時間を飛ばす区間の中の物どうし（どちらかが中）は要確認（演出で同時に出る物）。
// NJS の変化（v4）がある時は、手前の物を切る時刻の NJS で見る（飛んでいる物は今の NJS で進む＝その時の間隔は 秒差×NJS。2026-10-27・近似なので注記を出す）
function zIntersect(B) {
  const list = B.hittable, res = [], skip = [];
  const njsAt = B.njsVar ? B.njsVar.at : () => B.njs.value;
  if (!B.njsVar && !(B.njs.value > 0)) return [];
  const chainOf = o => o.type === 'link' ? o.chain : (o.chainOf || null);
  for (let i = 0; i < list.length; i++) {
    const a = list[i], [ax, ay] = B.cell(a), njs = njsAt(a.sec);
    if (!(njs > 0)) continue;
    for (let j = i + 1; j < list.length; j++) {
      const b = list[j];
      if ((b.sec - a.sec) * njs >= 0.5) break;
      const [bx, by] = B.cell(b);
      if (ax !== bx || ay !== by) continue;
      if (chainOf(a) && chainOf(a) === chainOf(b)) continue;
      (inSkip(B, a.time) || inSkip(B, b.time) ? skip : res).push(a, b);
    }
  }
  const out = [];
  if (res.length) out.push(F(null, BL.FAIL, 'zIntersect', null, uniq(res).map(ref)));
  if (skip.length) out.push(F(null, BL.CHECK, 'zIntersectSkip', null, uniq(skip).map(ref)));
  if (B.njsVar) out.push(F(null, 'note', 'zIntersectNjs', { n: B.njsVar.n }));
  return out;
}
// BS Map Check の判定（原作と同じ結果にするため NJS の変化を見ない）を流用する項目のうち、NJS で決まる物（R3.C のヒットボックス）:
// NJS の変化がある難易度に「基本の NJS で計算した」注記を添える（2026-10-27）
function withNjsBaseNote(fn) {
  const g = (B, ctx, dn) => [...fn(B, ctx, dn), ...(B.njsVar ? [F(null, 'note', 'njsBaseMc', { n: B.njsVar.n, njs: round(B.njs.value, 2) })] : [])];
  Object.defineProperty(g, 'name', { value: fn.name });
  return g;
}
function inWall(B) {
  const res = [];
  for (const o of B.hittable) {
    const [x, y] = B.cell(o);
    for (const w of wallsAt(B, o.sec)) {
      if (!covers(w, x)) continue;
      const [lo, hi] = wallY(w);
      if (y >= lo && y < hi) { res.push(o); break; }
    }
  }
  return res.length ? [F(null, BL.FAIL, 'inWall', null, res.map(ref))] : [];
}
// R3.B（候補）: ノーツの振り始めのマス（切る向きの反対側の隣のマス）に、ほぼ同時（前後 PRE_SWING_SEC 以内）に反対色のノーツ/チェーンがある
//  ＝振る時にまだそこにある物。図だけで定義された項目なので候補扱い。
//  2026-10-26 までは「同じ手の前のノーツとの間の後半（最大0.5秒）」に1つでもあれば出していて、もう切られて消えた物まで数え、
//  ランク譜面の84%の難易度に出ていた。ランク譜面ではちょうど同時（20ms以内）は0・40ms以内は約2%の難易度だけ（tools/bl_ranked_check.py）
const PRE_SWING_SEC = 0.04;
function preSwingBlock(B) {
  const res = [];
  for (const c of [0, 1]) {
    const own = B.notesByColor[c];
    const opp = B.hittable.filter(o => (o.type === 'color' || o.type === 'link') && o.color === 1 - c);
    for (const n of own) {
      if (n.direction === ANY) continue;
      const [dx, dy] = DIR_SPACE[n.direction], px = n.posX - dx, py = n.posY - dy;
      for (const o of between(opp, n.sec - PRE_SWING_SEC, n.sec + PRE_SWING_SEC)) { const [x, y] = B.cell(o); if (x === px && y === py) { res.push(n); break; } }
    }
  }
  return res.length ? [F(null, BL.CHECK, 'preSwing', null, res.map(ref))] : [];
}
// BS Map Check の判定結果を候補として流用
function fromMc(keys) {
  const fn = (B, ctx, dn) => {
    const rs = (ctx.mcBy[dn] || []).filter(r => keys.includes(r.key) && r.objs && r.objs.length);
    return rs.map(r => F(null, BL.CHECK, 'mc', { key: r.key }, r.objs));
  };
  Object.defineProperty(fn, 'name', { value: 'fromMc_' + keys.join('_') });
  return fn;
}

// ---------- R4 スイング ----------
const sliders = B => B.blSwings.filter(ns => ns.length >= 2 && ns[ns.length - 1].sec - ns[0].sec > EPS);
const effPrec = (a, b) => (b.time - a.time) / Math.max(1, Math.abs(b.posX - a.posX), Math.abs(b.posY - a.posY));   // 窓スライダーは抜けたマスも1つと数える
// R4.A.3（候補）: 実効精度が1/16拍より粗いスライダー（1/4拍刻みの譜面を想定。1/8刻みの区間なら1/32が下限＝区間の精度は目視）
function sliderPrecision(B) {
  const res = [];
  for (const ns of sliders(B)) {
    for (let i = 1; i < ns.length; i++) {
      if (ns[i].time - ns[i - 1].time < EPS) continue;
      if (effPrec(ns[i - 1], ns[i]) > 1 / 16 + EPS) { res.push(ns[0]); break; }
    }
  }
  return res.length ? [F(null, BL.CHECK, 'slowSlider', null, res.map(ref))] : [];
}
const fracName = v => { for (const d of [1, 2, 3, 4, 6, 8, 12, 16, 24, 32, 48, 64]) if (Math.abs(v * d - Math.round(v * d)) < 1e-3) return Math.round(v * d) + '/' + d; return String(round(v, 4)); };
function precisionList(B) {
  const set = new Map();
  for (const ns of sliders(B)) for (let i = 1; i < ns.length; i++) {
    if (ns[i].time - ns[i - 1].time < EPS) continue;
    const k = fracName(effPrec(ns[i - 1], ns[i])); set.set(k, (set.get(k) || 0) + 1);
  }
  if (!set.size) return [];
  return [F(null, 'note', 'precList', { list: [...set].sort((a, b) => b[1] - a[1]).map(([k, n]) => `${k}×${n}`).join(', ') })];
}
// R4.A.6（候補）: チェーンの長さが、スライダーの平均の長さの200%を超える。
//  数え方（2026-10-27・利用者の決定。以前は数msの組までスライダーに数えて平均が下がり、上限が10〜59msになって1/4拍のチェーンまで出ていた）:
//  - ほぼ同時の形（隣のノーツの間隔がどれも1/32拍未満）はスライダーに数えない（R4.A.2「長さの無い形は一瞬とみなしてよい」に合わせる）
//  - 数えるスライダーが無い・3つ未満なら平均を当てにせず比べない（合格扱いで注記だけ）
//  - 上限ちょうど（計算の端数・1ms以内）は出さない
const INSTANT_GAP = 1 / 32, CHAIN_MIN_SLIDERS = 3, CHAIN_TOL = 0.001;
function chainDuration(B) {
  const ch = B.map.chains.filter(c => c.tailSec > c.sec); if (!ch.length) return [];
  const sl = sliders(B).filter(ns => ns.some((n, i) => i > 0 && n.time - ns[i - 1].time > INSTANT_GAP - EPS));
  if (!sl.length) return [F(null, 'note', 'noSliders')];
  if (sl.length < CHAIN_MIN_SLIDERS) return [F(null, 'note', 'fewSliders', { n: sl.length })];
  const avg = sl.reduce((s, ns) => s + ns[ns.length - 1].sec - ns[0].sec, 0) / sl.length;
  const bad = ch.filter(c => c.tailSec - c.sec > avg * 2 + CHAIN_TOL);
  return bad.length ? [F(null, BL.CHECK, 'chainLong', { ms: round(avg * 2000) }, bad.map(ref))] : [];
}
// R4.B.1/2: 複数ノーツのスイングを、最初の向きから45度以内・曲がる向きは片側だけ、で振れるか
//  同じ拍のノーツは「基準を満たしやすい順」に切るとみなす（B.4）＝切る順を全部試し、どれか1つでも満たせば合格
function swingDevs(ord) {   // この順で切った時の、最初の向きからの角度差（ノーツの向きと、ノーツ間の移動の向き）
  const first = ord.find(n => n.direction !== ANY);
  if (!first) return null;
  const a0 = cutAngle(first), devs = [];
  for (let i = 0; i < ord.length; i++) {
    const n = ord[i];
    if (n.direction !== ANY) devs.push(sdiff(cutAngle(n), a0));
    if (i > 0) {
      const a = [ord[i - 1].posX, ord[i - 1].posY], b = [n.posX, n.posY];
      if (a[0] !== b[0] || a[1] !== b[1]) devs.push(sdiff(segAngle(a, b), a0));
    }
  }
  return devs;
}
const perms = a => a.length <= 1 ? [a] : a.flatMap((x, i) => perms([...a.slice(0, i), ...a.slice(i + 1)]).map(r => [x, ...r]));
// 「同じ拍」は秒で1ms未満のずれまで（2026-10-27・利用者の決定。以前は拍で1e-6未満）。保存の端数で極小にずれた横並びを、置いた順で切る扱いにしていた
//  （ランク譜面に 0.000031拍＝約15µs ずれた同じ色・同じ向きの横並びがあり、動きが矢印と180度逆＝R4.B.1 の誤検出。ゲームでは同時）。
//  ランク譜面189で同じ色の続く組の間は、1ms未満が5組（0.015〜0.17ms・端数）・1〜3msが525組（意図したとても速いスライダー）＝1msで分かれる。
//  試す順が増えるだけなので新しい違反は出ない（下の上限＝2000通り・6個以上のまとまりに届かない限り）。他の判定の「同時」の幅（視界ブロック・重なり等）は変えない
const SAME_BEAT_SEC = 0.001;
function swingOrders(ns) {   // 同じ拍のまとまりごとの並べ方の組み合わせ（多すぎる時は時刻順のみ）
  const groups = [];
  for (const n of [...ns].sort((a, b) => a.sec - b.sec)) {
    const g = groups[groups.length - 1];
    if (g && Math.abs(g[0].sec - n.sec) < SAME_BEAT_SEC) g.push(n); else groups.push([n]);
  }
  let orders = [[]];
  for (const g of groups) {
    const ps = g.length <= 5 ? perms(g) : [g];
    if (orders.length * ps.length > 2000) return [groups.flat()];
    orders = orders.flatMap(o => ps.map(p => [...o, ...p]));
  }
  return orders;
}
const within45 = d => d.every(x => Math.abs(x) <= 45 + 1e-3);
const oneWay = d => !(d.some(x => x > 1e-3) && d.some(x => x < -1e-3));
function swingJudge(B, need) {
  const res = [];
  for (const ns of B.blSwings) {
    if (ns.length < 2) continue;
    const all = swingOrders(ns).map(swingDevs).filter(Boolean);
    if (all.length && !all.some(need)) res.push(ns[0]);
  }
  return res;
}
function swingAngle(B) {
  const res = swingJudge(B, within45);
  return res.length ? [F(null, BL.FAIL, 'swing45', null, res.map(ref))] : [];
}
function swingOneWay(B) {
  const res = swingJudge(B, oneWay);
  return res.length ? [F(null, BL.FAIL, 'swingBothWays', null, res.map(ref))] : [];
}

// ---------- R5 視認性 ----------
// R5.A: 最小時間の式（BeatLeader公式のDesmos）: (750-325)·e^(-★/7.6 - Tech·0.06) + 325 [ms]
export const visionMinMs = (star, tech) => (750 - 325) * Math.exp(-star / 7.6 - tech * 0.06) + 325;
// 真ん中2列・中段（x=1/2, y=1）のノーツ/ボムが、同じ側（左列は x≤1、右列は x≥2）の後ろの当たる物を隠す
// 例外（A.3/A.4）: 外側の列は150ms未満、真ん中下段は75ms未満なら見えるとみなす（下段は流れに沿う場合のみ＝目視）
function visionBlock(B, ctx, dn) {
  const st = ctx.p.stars && ctx.p.stars[dn];
  if (!st || !(st.star >= 0) || !(st.tech >= 0)) return [F(null, BL.CHECK, 'needStars')];
  const min = visionMinMs(st.star, st.tech) / 1000, res = [];
  let L = null, R = null;
  const list = B.hittable;
  for (let i = 0; i < list.length;) {
    let j = i; while (j < list.length && list[j].sec - list[i].sec < EPS) j++;
    for (let k = i; k < j; k++) {
      const o = list[k], [x, y] = B.cell(o);
      for (const [bl, side] of [[L, x <= 1], [R, x >= 2]]) {
        if (!bl || !side) continue;
        const dt = o.sec - bl.sec;
        if (!(dt > EPS && dt < min)) continue;
        if ((x === 0 || x === 3) && dt < 0.15) continue;
        res.push(o); break;
      }
    }
    for (let k = i; k < j; k++) {
      const o = list[k];
      if (o.type === 'link' || o.posY !== 1) continue;
      if (o.posX === 1) L = o; else if (o.posX === 2) R = o;
    }
    i = j;
  }
  return [F(null, res.length ? BL.CHECK : 'note', res.length ? 'vision' : 'visionOk', { ms: round(min * 1000) }, uniq(res).map(ref))];
}
// R5.B.3（候補）: 下からの壁は、その列の物の出現を、壁の始まりから終わり＋0.25拍まで隠す（正当化が必要）
function wallHidesSpawn(B) {
  const res = [];
  for (const o of B.hittable) {
    const [x] = B.cell(o);
    for (const w of between(B.walls, o.sec - B.maxWallSec - 1, o.sec)) {   // 0.25拍の延長ぶん1秒余分に遡る（BPM 15以上なら足りる）
      if (w.posY !== 0 || w.height <= 0 || !covers(w, x)) continue;
      if (o.sec <= B.tp.toRealTime(w.time + w.duration + 0.25) + EPS) { res.push(o); break; }
    }
  }
  return res.length ? [F(null, BL.CHECK, 'wallHide', null, res.map(ref))] : [];
}

// ---------- R6 チェーンとアーク ----------
function chainFirst16(B) {
  const seq = [...B.map.colorNotes.map(n => ({ o: n, t: n.time, ch: !!n.chainOf })), ...B.links.map(l => ({ o: l, t: l.time, ch: true }))]
    .sort((a, b) => a.t - b.t).slice(0, 16);
  const bad = seq.filter(s => s.ch).map(s => s.o);
  return bad.length ? [F(null, BL.FAIL, 'first16', null, uniq(bad.map(o => o.type === 'link' ? o.chain : o.chainOf || o)).map(ref))] : [];
}
// 長さ0のチェーン（尾＝頭・リンクが頭と同時に出る作り）は逆向きにしない（AutoModder と同じ。ランク譜面で使われている）
function chainReverse(B) {
  const bad = B.map.chains.filter(c => c.tailTime < c.time - EPS);
  return bad.length ? [F(null, BL.FAIL, 'chainReverse', null, bad.map(ref))] : [];
}
// R6.B.2/3: 頭の向き（点ノーツは下）から、頭の位置から各リンクへの向きが45度を超えて変わらない
//（文面「頭の位置と向きから」。2026-10-26 まではリンクの間の線ごとに見ていて、曲線の終わりだけが45度を超えるチェーンを違反にしていた）
function chainPath(B) {
  const bad = B.map.chains.filter(c => {
    for (let i = 1; i < c.pts.length; i++) {
      const a = c.pts[0], b = c.pts[i];
      if (Math.hypot(b[0] - a[0], b[1] - a[1]) < 1e-6) continue;
      if (Math.abs(sdiff(segAngle(a, b), c.headAngle)) > 45 + 1e-3) return true;
    }
    return false;
  });
  return bad.length ? [F(null, BL.FAIL, 'chainTurn', null, bad.map(ref))] : [];
}
function chainHeadGrid(B) {
  const bad = B.map.chains.filter(c => c.posX < 0 || c.posX > 3 || c.posY < 0 || c.posY > 2);
  return bad.length ? [F(null, BL.FAIL, 'chainHeadOut', null, bad.map(ref))] : [];
}
// リンクのはみ出しは 0.1 マスまで許す（曲線の計算で 0.01 マスほど枠の外へ出るチェーンがランク譜面にある。AutoModder は上下 1/3 マスまで）
const LINK_TOL = 0.1;
function chainLinkGrid(B) {
  const bad = B.map.chains.filter(c => c.blLinks.some(l => l.pos[0] < -1 - LINK_TOL || l.pos[0] > 4 + LINK_TOL || l.pos[1] < -LINK_TOL || l.pos[1] > 2 + LINK_TOL));
  return bad.length ? [F(null, BL.FAIL, 'chainLinkOut', null, bad.map(ref))] : [];
}
// R6.D: 「リンク対すき間」の割合＝チェーンの詰め具合（squish）とみなす（文面に計算方法が無いための解釈）
function chainDensity(B) {
  const out = [], low = B.map.chains.filter(c => c.squish < 0.125 - EPS), high = B.map.chains.filter(c => c.squish >= 0.33 - EPS);
  if (low.length) out.push(F(null, BL.FAIL, 'chainSparse', null, low.map(ref)));
  if (high.length) out.push(F(null, 'note', 'chainDense', { n: high.length }));
  return out;
}
// R6.E: チェーンの最後のリンクから、同じ手の次のノーツまでの時間 ≥ チェーンの長さ
function chainGap(B) {
  const bad = B.map.chains.filter(c => {
    const nx = B.notesByColor[c.color] ? B.notesByColor[c.color].find(n => n.sec > c.tailSec + EPS) : null;
    return nx && nx.sec - c.tailSec < (c.tailSec - c.sec) - EPS;
  });
  return bad.length ? [F(null, BL.FAIL, 'chainGap', null, bad.map(ref))] : [];
}
function arcBomb(B) {
  const hit = (t, x, y) => B.map.bombNotes.some(b => Math.abs(b.time - t) < 0.001 && b.posX === x && b.posY === y);
  const bad = B.map.arcs.filter(a => hit(a.time, a.posX, a.posY) || hit(a.tailTime, a.tailPosX, a.tailPosY));
  return bad.length ? [F(null, BL.FAIL, 'arcBomb', null, bad.map(ref))] : [];
}
function chainHead(B) {
  const bad = B.map.chains.filter(c => !c.head);
  return bad.length ? [F(null, BL.FAIL, 'noHead', null, bad.map(ref))] : [];
}
function chainSlices(B) {
  const bad = B.map.chains.filter(c => !(c.sliceCount >= 2));
  return bad.length ? [F(null, BL.FAIL, 'fewSlices', null, bad.map(ref))] : [];
}

// ---------- R7 ボム ----------
// R7.A（候補）: 切る向きの手前/先の隣のマスに、振る直前（前半）/振った直後（後半）のボム。時間の幅は同じ手の前後のノーツとの間の半分（最大0.5秒）
function bombSwingPath(B) {
  const res = [], bombs = [...B.map.bombNotes].sort((a, b) => a.sec - b.sec);
  for (const c of [0, 1]) {
    const own = B.notesByColor[c];
    own.forEach((n, i) => {
      if (n.direction === ANY) return;
      const [dx, dy] = DIR_SPACE[n.direction];
      const pw = i > 0 ? Math.min((n.sec - own[i - 1].sec) / 2, 0.5) : 0.5, qw = i < own.length - 1 ? Math.min((own[i + 1].sec - n.sec) / 2, 0.5) : 0.5;
      for (const b of between(bombs, n.sec - pw, n.sec + qw)) {
        const pre = b.posX === n.posX - dx && b.posY === n.posY - dy && b.sec <= n.sec + EPS;
        const post = b.posX === n.posX + dx && b.posY === n.posY + dy && b.sec >= n.sec - EPS;
        if (pre || post) res.push(b);
      }
    });
  }
  return res.length ? [F(null, BL.CHECK, 'bombPath', null, uniq(res).map(ref))] : [];
}
// R7.B: 明るさ50（=0.5）以上のライトが、ボムの250ms前からボムが通り過ぎるまで点いている
//  基本ライトイベントを再現して判定する。近似が多いので候補扱い。
//  2026-10-27 から審査の人の道具（AutoModder の Bomb Lit。BS Map Check の unlitBomb が元）と同じ見方にした
//  （以前は 250ms の間ずっと明るいことを求めていて、点滅＝On/Fade と Off を細かく繰り返す所の数十ms の暗がりで、ランク譜面の38%の難易度に出ていた）:
//   - 見るのはボムの 250ms 前の瞬間だけ。消灯（値0・暗いイベント）は 250ms 遅れて効く（AutoModder の LightBombReactionTime）。
//     ＝ボムの 250〜500ms 前のどこかで点いていれば明るい。最後の 250ms が暗くても出ない所は文面より甘い（注記に書いてある）。
//   - 明るさ（floatValue）と Chroma の色（最大の成分・不透明度）は 0.25 未満を消灯とみなす（AutoModder・BS Map Check と同じ。文面の「50」より甘い）。
//   - Chroma の lightID 付きのイベントは、その ID のライトだけを変える（以前は種類の全部を変えたことにしていた）。
//   - フェードは 1 秒点灯・Transition は点灯（AutoModder は Transition を数えない＝ここは NLM の方が甘い）。
const lightTypesOf = env => { const t = BASIC_TRACKS[env]; return t && t.l.length ? t.l : [0, 1, 2, 3, 4]; };
const isOn = v => v === 1 || v === 5 || v === 9, isFlash = v => v === 2 || v === 6 || v === 10, isFade = v => v === 3 || v === 7 || v === 11, isTrans = v => v === 4 || v === 8 || v === 12;
const LIT_MIN = 0.25, LIT_FADE = 1, LIT_REACT = 0.25;
const dimCol = c => !!c && ((typeof c[3] === 'number' && c[3] < LIT_MIN) || Math.max(c[0], c[1], c[2]) < LIT_MIN);
const lightIds = cd => { const v = cd.lightID ?? cd._lightID; if (v == null) return null; const a = (Array.isArray(v) ? v : [v]).filter(x => typeof x === 'number'); return a.length ? a : null; };
// 明るい区間（秒）の一覧。消灯した区間の終わりは LIT_REACT だけ後ろへ延ばす（フェードの1秒の終わりは延ばさない）
function litSegments(B) {
  const tail = LIT_REACT;
  const types = lightTypesOf(B.env), segs = [];
  const bright = e => e.value !== 0 && (e.floatValue ?? 1) >= LIT_MIN && !dimCol(e.customData._color) && !dimCol(e.customData.color)
    && (isOn(e.value) || isFlash(e.value) || isFade(e.value) || isTrans(e.value));
  for (const ty of types) {
    const evs = B.map.basicEvents.filter(e => e.etype === ty).sort((a, b) => a.sec - b.sec);
    const st = new Map();   // 点いているライト: 土台（null＝lightID 無し）か lightID → [点いた秒, フェードの終わり]
    const close = (k, t) => { const s = st.get(k); if (s) { segs.push([s[0], Math.min(t + tail, s[1])]); st.delete(k); } };
    for (const e of evs) {
      const ids = lightIds(e.customData);
      if (!ids) for (const k of [...st.keys()]) close(k, e.sec);   // lightID 無し＝種類の全部を変える
      for (const k of ids || [null]) {
        close(k, e.sec);
        if (bright(e)) st.set(k, [e.sec, isFade(e.value) ? e.sec + LIT_FADE : Infinity]);
      }
    }
    for (const k of [...st.keys()]) close(k, Infinity);
  }
  segs.sort((a, b) => a[0] - b[0]);
  const merged = [];
  for (const s of segs) { const l = merged[merged.length - 1]; if (l && s[0] <= l[1] + EPS) l[1] = Math.max(l[1], s[1]); else merged.push([...s]); }
  return merged;
}
// 元の譜面のライトがライトボックスだった難易度: NLM は読めない（読み込みで消える）ので、ライトの判定（R10.A・R7.B）は手動確認だけにする（2026-10-26・利用者の決定）
const srcBoxesUnread = B => B.srcLightBoxes > 0 ? [F(null, BL.MANUAL, 'boxLightsUnread', { n: B.srcLightBoxes })] : null;
function bombLight(B) {
  const bombs = B.map.bombNotes; if (!bombs.length) return [];
  const unread = srcBoxesUnread(B); if (unread) return unread;
  const hasBoxes = B.map.ebg.color.length > 0;
  if (!V2_ENVS.has(B.env) && hasBoxes) return [F(null, BL.CHECK, 'boxLights')];
  const segs = litSegments(B);
  if (!segs.length) return [F(null, BL.FAIL, 'noLightAtAll', null, bombs.map(ref))];
  const litAt = t => segs.some(g => g[0] <= t + EPS && g[1] >= t - EPS);
  const dark = bombs.filter(b => !litAt(b.sec - LIT_REACT));
  return dark.length ? [F(null, BL.CHECK, 'bombDark', null, dark.map(ref))] : [];
}

// ---------- R8 壁 ----------
// R8.A.2（候補）: 壁の境界を避ける時間が 250ms 以上（例外で 235ms・NQT/RT の承認が要る）。
//  真ん中の片側だけを（立った頭の高さで）塞ぐ壁が来た時、頭を向かわせる反対側の列を塞いでいた壁が終わってから、この壁が来るまでの時間。
//  重なる（両方が同時に塞がれる）所は R8.B。検出が近似（頭を本当に動かす必要があるかは壁の幅・頭の位置で変わる）なので、235ms 未満も要確認にして文で伝える。
//  2026-10-26 から（以前は BS Map Check の「中央の2マス幅の壁」を流用。あれは幅3以上の壁を位置に関係なく必ず出し、ランク譜面の7難易度に出ていた）
const AVOID_MIN = 0.25, AVOID_MIN_EX = 0.235;
function wallAvoid(B) {
  const end = { 1: -Infinity, 2: -Infinity };   // 真ん中の左右の列を最後に塞いでいた壁の終わり（秒）
  const u235 = [], u250 = [];
  for (const w of B.walls) {
    if (!blocksStand(w)) continue;
    const c1 = covers(w, 1), c2 = covers(w, 2), e = w.sec + w.dsec;
    if (c1 && c2) { end[1] = Math.max(end[1], e); end[2] = Math.max(end[2], e); continue; }
    if (!c1 && !c2) continue;
    const blocked = c1 ? 1 : 2, gap = w.sec - end[c1 ? 2 : 1];   // 反対側の列が空いてから、この壁が来るまで
    if (gap > -EPS && gap < AVOID_MIN_EX - EPS) u235.push(w);
    else if (gap > -EPS && gap < AVOID_MIN - EPS) u250.push(w);
    end[blocked] = Math.max(end[blocked], e);
  }
  const out = [];
  if (u235.length) out.push(F(null, BL.CHECK, 'wallDodge235', null, u235.map(ref)));
  if (u250.length) out.push(F(null, BL.CHECK, 'wallDodge250', null, u250.map(ref)));
  return out;
}
// R8.A.3（候補）: 真ん中の片側だけを塞ぐ壁（dodge wall）で頭を左右へ動かす回数。塞ぐ側が入れ替わる間隔から:
//  1秒に2回を超える（0.5秒未満）＝正当化が必要／3.8回を超える＝例外として NQT/RT の承認が要る／4回を超える＝例外でも不可。
//  基準の注の「3.8回/秒＝1/1で227BPM・4回/秒＝241BPM」は、避ける時間 250/235ms＋一番短い壁の長さから出した数。
//  検出が近似なので、どの段も要確認にして文で伝える（2026-10-26 から。以前は2回だけ）
const DODGE_JUSTIFY = 1 / 2, DODGE_MAX = 1 / 3.8, DODGE_MAX_EX = 1 / 4;
function dodgeRate(B) {
  let side = null, lastMove = null; const fast = [], over = [], overEx = [];
  for (const w of B.walls) {
    if (!blocksStand(w)) continue;
    const c1 = covers(w, 1), c2 = covers(w, 2);
    if (c1 === c2) continue;
    const need = c1 ? 'R' : 'L';
    if (side && need !== side) {
      const gap = lastMove != null ? w.sec - lastMove : Infinity;
      if (gap < DODGE_MAX_EX - EPS) overEx.push(w);
      else if (gap < DODGE_MAX - EPS) over.push(w);
      else if (gap < DODGE_JUSTIFY - EPS) fast.push(w);
      lastMove = w.sec;
    }
    side = need;
  }
  const out = [];
  if (overEx.length) out.push(F(null, BL.CHECK, 'dodgeOver4', null, overEx.map(ref)));
  if (over.length) out.push(F(null, BL.CHECK, 'dodgeOver38', null, over.map(ref)));
  if (fast.length) out.push(F(null, BL.CHECK, 'dodgeFast', null, fast.map(ref)));
  return out;
}
// R8.B: 真ん中の2レーンが同時に（立った頭の高さで）塞がれる
function outerLane(B) {
  const full = B.walls.filter(blocksStand), res = [];
  for (const a of full) {
    if (covers(a, 1) && covers(a, 2)) { res.push(a); continue; }
    for (const b of full) {
      if (a === b || !(covers(a, 1) && !covers(a, 2) && covers(b, 2))) continue;
      if (Math.min(a.sec + a.dsec, b.sec + b.dsec) - Math.max(a.sec, b.sec) > EPS) { res.push(a, b); }
    }
  }
  return res.length ? [F(null, BL.FAIL, 'outerLane', null, uniq(res).map(ref))] : [];
}
// R8.C: 13.8ms以下の壁は、同じレーンの正規の壁の後ろ250ms以内、または何かの壁の後ろ100ms以内でないといけない。
//  枠の外（4レーンにかからない）の壁は対象外（「同じレーン」の無い飾りの壁。ランク譜面で列の先頭が違反になっていた・2026-10-26 利用者の決定）。
//  時間を飛ばす区間の中の壁は要確認（演出で長さがほぼ0になる壁）
function legalWall(B) {
  const legal = w => w.dsec * 1000 > 13.8, res = [], skip = [];
  const sameLane = (a, b) => a.posX < b.posX + b.width && b.posX < a.posX + a.width;
  const outside = w => w.posX + w.width <= 0 || w.posX >= 4;
  for (const w of B.walls) {
    if (legal(w) || w.width <= 0 || outside(w)) continue;
    const ok = B.walls.some(o => o !== w && sameLane(o, w) && o.sec <= w.sec + EPS
      && w.sec - (o.sec + o.dsec) <= (legal(o) ? 0.25 : 0.1) + EPS);
    if (!ok) (inSkip(B, w.time) ? skip : res).push(w);
  }
  const out = [];
  if (res.length) out.push(F(null, BL.FAIL, 'illegalWall', null, res.map(ref)));
  if (skip.length) out.push(F(null, BL.CHECK, 'illegalWallSkip', null, skip.map(ref)));
  return out;
}
// しゃがむ区間: 真ん中の2レーンがどちらも「頭の高さの壁」か「頭上の壁」で塞がれ、少なくとも1つは頭上の壁（D.3の半分の壁を含む）
function crouchSpans(B) {
  const ws = B.walls.filter(w => w.dsec > 0 && (blocksStand(w) || overhead(w)) && middleWall(w));
  const ts = [...new Set(ws.flatMap(w => [w.sec, w.sec + w.dsec]))].sort((a, b) => a - b), spans = [];
  for (let i = 0; i < ts.length - 1; i++) {
    const m = (ts[i] + ts[i + 1]) / 2, act = ws.filter(w => w.sec <= m && w.sec + w.dsec >= m);
    const lane = c => act.some(w => covers(w, c) && blocksStand(w)) ? 'full' : act.some(w => covers(w, c) && overhead(w)) ? 'over' : null;
    const l1 = lane(1), l2 = lane(2);
    if (l1 && l2 && (l1 === 'over' || l2 === 'over')) {
      const last = spans[spans.length - 1];
      if (last && Math.abs(last[1] - ts[i]) < EPS) last[1] = ts[i + 1]; else spans.push([ts[i], ts[i + 1]]);
    }
  }
  return spans;
}
function crouchBottom(B) {
  const spans = crouchSpans(B); if (!spans.length) return [];
  const halfBeat = s => B.tp.toRealTime(B.tp.toBeatTime(s) + 0.5);
  const res = B.hittable.filter(o => { const [x, y] = B.cell(o); return y === 0 && (x === 1 || x === 2) && spans.some(([s, e]) => o.sec >= s - EPS && o.sec <= halfBeat(e) + EPS); });
  return res.length ? [F(null, BL.CHECK, 'crouchLow', null, res.map(ref))] : [];
}
function crouchTop(B) {
  const spans = crouchSpans(B); if (!spans.length) return [];
  const res = B.hittable.filter(o => o.type !== 'bomb' && B.cell(o)[1] >= 2 && spans.some(([s, e]) => o.sec >= s - EPS && o.sec <= e + EPS));
  return res.length ? [F(null, BL.FAIL, 'crouchHigh', null, res.map(ref))] : [];
}

// ---------- R9 可変NJS / R10 ライト ----------
function njsEvents(B) {
  return B.njsEvents && B.njsEvents.length ? [F(null, BL.CHECK, 'njsEventsUsed', { n: B.njsEvents.length })] : [];
}
function lightDensity(B, { p }) {
  const unread = srcBoxesUnread(B); if (unread) return unread;
  const types = lightTypesOf(B.env);
  const basic = B.map.basicEvents.filter(e => types.includes(e.etype)).length;
  const boxes = B.map.ebg.color.reduce((s, g) => s + g.boxes.reduce((t, x) => t + x.events.length, 0), 0);
  const all = [...B.map.colorNotes, ...B.map.bombNotes, ...B.map.obstacles];
  const beats = B.endBeat != null ? B.endBeat : (all.length ? Math.max(...all.map(o => o.time)) : 0);
  if (!(beats > 0)) return [];
  const per = (basic + boxes) / beats;
  return [F(null, per < 1 ? BL.FAIL : 'note', per < 1 ? 'lightFew' : 'lightOk', { n: basic + boxes, beats: round(beats, 1), per: round(per, 2) })];
}

// ---------- R11 メタデータ ----------
const META = [['songName', 'fSong'], ['subName', 'fSub'], ['author', 'fAuthor'], ['mapper', 'fMapper']];
// ゲーム内のキーボードで打てない文字（ASCIIの表示文字以外）。
// 翻訳/ローマ字化が要る文字（かな・漢字・ハングル・キリル文字など）→R11.B、それ以外（Ω Δ ∞ や é など）→R11.C
const NEEDS_ROMAN = /[\p{Script=Han}\p{Script=Hiragana}\p{Script=Katakana}\p{Script=Hangul}\p{Script=Cyrillic}\p{Script=Arabic}\p{Script=Hebrew}\p{Script=Thai}\p{Script=Devanagari}ー]/u;
function oddChars(s, letters) {
  const out = new Set();
  for (const ch of String(s || '')) {
    const cp = ch.codePointAt(0); if (cp >= 0x20 && cp <= 0x7e) continue;
    if (NEEDS_ROMAN.test(ch) === letters) out.add(ch);
  }
  return [...out].join('');
}
function metaChars(letters, key) {
  return ({ p }) => {
    const m = p.meta || {}, out = [];
    for (const [k, f] of META) { const c = oddChars(m[k], letters); if (c) out.push(F(null, BL.CHECK, key, { field: f, chars: c, v: m[k] })); }
    return out;
  };
}
function metaLetters(ctx) { return metaChars(true, 'unsearchable')(ctx); }
function metaSymbols(ctx) { return metaChars(false, 'specialChar')(ctx); }
const TAG_RE = /\b(feat\.?|ft\.|remix|cover|covered by|ver\.|version|edit|mix)\b|[（(［\[].*[)）］\]]/i;
function nameTags({ p }) {
  const s = (p.meta || {}).songName || '';
  return TAG_RE.test(s) ? [F(null, BL.CHECK, 'nameTag', { v: s })] : [];
}
function authorTags({ p }) {
  const s = (p.meta || {}).author || '';
  return /\b(feat\.?|ft\.|cover|covered by)\b/i.test(s) ? [F(null, BL.CHECK, 'authorTag', { v: s })] : [];
}
function mapperField({ p }) {
  return String((p.meta || {}).mapper || '').trim() ? [] : [F(null, BL.FAIL, 'noMapper')];
}
function diffNames({ p }) {
  const labels = p.diffs.map(d => d.label).filter(Boolean);
  return labels.length ? [F(null, BL.CHECK, 'customLabels', { list: labels.join(' / ') })] : [F(null, 'note', 'defaultNames')];
}
// R11.H.5（候補）: 難易度は★の低い順（0.5★までの逆転は許容）。★は p.stars（プラグインの近似値か手入力）。
// 並びは書き出しの順（易しい順）。どれかの易しい難易度より0.5★を超えて低い難易度を挙げる（隣どうしだけでなく全体で比べる）。
// 近似値なので違反(FAIL)にはせず要確認。★の無い難易度は除いて判定し、除いたことを手動確認として出す
function starOrder({ p }) {
  const dns = p.diffs.map(d => d.difficulty);
  if (dns.length < 2) return [F(null, 'note', 'oneDiff')];
  const starOf = dn => { const s = p.stars && p.stars[dn]; return s && s.star >= 0 ? s.star : null; };
  const known = dns.filter(dn => starOf(dn) != null), missing = dns.filter(dn => starOf(dn) == null);
  const out = [];
  let top = null;   // ここまでで★が一番高い難易度
  for (const dn of known) {
    if (top && starOf(dn) < starOf(top) - 0.5 - EPS) out.push(F(dn, BL.CHECK, 'starOrder', { star: starOf(dn), lo: top, loStar: starOf(top) }));
    if (!top || starOf(dn) > starOf(top)) top = dn;
  }
  if (known.length < 2) return [F(null, BL.MANUAL, 'orderNoStars')];
  if (!out.length) out.push(F(null, 'note', 'starOrderOk', { order: known.map(dn => [dn, starOf(dn)]) }));
  if (missing.length) out.push(F(null, BL.MANUAL, 'orderNeedStars', { diffs: missing }));
  return out;
}

const uniq = a => [...new Set(a)];
const SKIP_BPM = 10000;   // これ以上の BPM の区間を「時間を飛ばす区間」とみなす（ランク譜面の演出は 100000・普通の曲の BPM は 620 まで）
const inSkip = (B, beat) => B.skips.some(([s, e]) => beat >= s - EPS && beat <= e + EPS);
function lowerSec(arr, s) { let lo = 0, hi = arr.length; while (lo < hi) { const m = (lo + hi) >> 1; if (arr[m].sec < s) lo = m + 1; else hi = m; } return lo; }
function* between(arr, s, e) { for (let i = lowerSec(arr, s - EPS); i < arr.length && arr[i].sec <= e + EPS; i++) yield arr[i]; }
// その秒に続いている壁（壁は開始の時刻順。最長の壁の長さぶんだけ遡って探す）
function* wallsAt(B, sec) { for (const w of between(B.walls, sec - B.maxWallSec, sec)) if (sec <= w.sec + w.dsec + EPS) yield w; }

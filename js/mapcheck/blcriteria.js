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
const cutAngle = n => noteAngle(n.direction) - (n.angleOffset || 0);
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
  { id: 'R3.B', kind: 'cand', f: preSwingBlock }, { id: 'R3.C', kind: 'cand', f: fromMc(['hitboxStair', 'hitboxReverseStair', 'hitboxInline', 'hitboxPath']) },
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
  { id: 'R8.A.1', kind: 'manual' }, { id: 'R8.A.2', kind: 'cand', f: fromMc(['centerObstacle']) },
  { id: 'R8.A.3', kind: 'cand', f: dodgeRate }, { id: 'R8.B', kind: 'auto', f: outerLane },
  { id: 'R8.C', kind: 'auto', f: legalWall }, { id: 'R8.D.1', kind: 'cand', f: crouchBottom },
  { id: 'R8.D.2', kind: 'auto', f: crouchTop },
  { id: 'R9', kind: 'na', f: njsEvents },
  { id: 'R10.A', kind: 'auto', f: lightDensity }, { id: 'R10.B', kind: 'manual' },
  { id: 'R11.A', kind: 'manual' }, { id: 'R11.B', kind: 'cand', g: metaLetters }, { id: 'R11.C', kind: 'cand', g: metaSymbols },
  { id: 'R11.D.1', kind: 'manual' }, { id: 'R11.D.2', kind: 'cand', g: nameTags }, { id: 'R11.E', kind: 'manual' },
  { id: 'R11.F.1', kind: 'manual' }, { id: 'R11.F.2', kind: 'cand', g: authorTags },
  { id: 'R11.G', kind: 'partial', g: mapperField }, { id: 'R11.H.1', kind: 'auto', g: diffNames }, { id: 'R11.H.5', kind: 'manual' },
  { id: 'R11.I', kind: 'manual' }, { id: 'R11.J', kind: 'manual' },
];
export const SECTIONS = ['R1', 'R2', 'R3', 'R4', 'R5', 'R6', 'R7', 'R8', 'R9', 'R10', 'R11'];

/**
 * @param p  runMapCheck と同じ入力＋ p.meta{songName,subName,author,mapper} / p.infoRaw{songTimeOffset,shuffle,shufflePeriod,colorSchemes,requirements}
 *           / p.cover{w,h,name} / p.stars{難易度:{star,tech}}（視界ブロックの式に使う。空なら判定しない）
 * @param mc runMapCheck の結果（候補の流用元）
 */
export function runBlCriteria(p, mc) {
  const built = {};
  for (const d of p.diffs) {
    try {
      const B = buildBeatmap(d.json, { bpm: p.info.bpm, environment: p.info.environment, difficulty: d.difficulty, njs: d.njs, njsOffset: d.njsOffset });
      prep(B, d.json, p.audioDuration);
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
  return { auto: BL.PASS, partial: BL.PARTIAL, cand: BL.PASS, manual: BL.MANUAL, na: BL.NA }[kind];
}

// ---- 下ごしらえ: 正しいチェーンのリンク位置・チェーンの頭のノーツ・当たる物の一覧 ----
// （mapcheck.js のリンク位置は原作の計算のクセを再現しているので、ここではゲームどおりに計算し直す）
function prep(B, json, audioSec) {
  const { tp, map } = B;
  B.njsEvents = Array.isArray(json.njsEvents) ? json.njsEvents : null;
  B.njsEventData = Array.isArray(json.njsEventData) ? json.njsEventData : null;
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
  // BS Map Check は90度ちょうどでも分けるため、45度ルール（R4.B）の判定には使えない
  B.blSwings = [];
  for (const c of [0, 1]) {
    let cur = [];
    for (const n of B.notesByColor[c]) {
      const prev = cur[cur.length - 1];
      const dt = prev ? n.sec - prev.sec : Infinity, far = Math.hypot(n.posX - prev?.posX, n.posY - prev?.posY) > 1.8;
      const turn = n.direction !== ANY && cur.some(o => o.direction !== ANY && Math.abs(sdiff(cutAngle(n), cutAngle(o))) > 90 + 1e-3);
      const same = cur.some(o => o.posX === n.posX && o.posY === n.posY);
      if (!prev || dt > (far ? 0.08 : 0.07) || (dt > 0.005 && turn) || same) { if (cur.length) B.blSwings.push(cur); cur = []; }
      cur.push(n);
    }
    if (cur.length) B.blSwings.push(cur);
  }
  B.endBeat = audioSec ? tp.toBeatTime(audioSec) : null;   // 曲の最後の拍（エディタの最終拍）
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
// R3.A.1: 同じマスで奥行き0.5m以内（(拍差)/(BPM/60)×NJS < 0.5m）。アークは対象外。同じチェーンの頭とリンク同士は除く
function zIntersect(B) {
  const list = B.hittable, njs = B.njs.value, res = [];
  if (!(njs > 0)) return [];
  const chainOf = o => o.type === 'link' ? o.chain : (o.chainOf || null);
  for (let i = 0; i < list.length; i++) {
    const a = list[i], [ax, ay] = B.cell(a);
    for (let j = i + 1; j < list.length; j++) {
      const b = list[j];
      if ((b.sec - a.sec) * njs >= 0.5) break;
      const [bx, by] = B.cell(b);
      if (ax !== bx || ay !== by) continue;
      if (chainOf(a) && chainOf(a) === chainOf(b)) continue;
      res.push(a, b);
    }
  }
  return res.length ? [F(null, BL.FAIL, 'zIntersect', null, uniq(res).map(ref))] : [];
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
// R3.B（候補）: ノーツの振り始めのマス（切る向きの反対側の隣のマス）に、振る直前まで反対色のノーツ/チェーンがある
//  「直前」＝同じ手の1つ前のノーツとの間の後半（最大0.5秒）。図だけで定義された項目なので候補扱い
function preSwingBlock(B) {
  const res = [];
  for (const c of [0, 1]) {
    const own = B.notesByColor[c];
    const opp = B.hittable.filter(o => (o.type === 'color' || o.type === 'link') && o.color === 1 - c);
    own.forEach((n, i) => {
      if (n.direction === ANY) return;
      const [dx, dy] = DIR_SPACE[n.direction], px = n.posX - dx, py = n.posY - dy;
      const win = i > 0 ? Math.min((n.sec - own[i - 1].sec) / 2, 0.5) : 0.5;
      for (const o of between(opp, n.sec - win, n.sec)) { const [x, y] = B.cell(o); if (x === px && y === py) { res.push(n); break; } }
    });
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
// R4.A.6（候補）: チェーンの長さが、スライダーの平均の長さの200%を超える
function chainDuration(B) {
  const ch = B.map.chains.filter(c => c.tailSec > c.sec); if (!ch.length) return [];
  const sl = sliders(B);
  if (!sl.length) return [F(null, BL.CHECK, 'noSliders')];
  const avg = sl.reduce((s, ns) => s + ns[ns.length - 1].sec - ns[0].sec, 0) / sl.length;
  const bad = ch.filter(c => c.tailSec - c.sec > avg * 2 + EPS);
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
function swingOrders(ns) {   // 同じ拍のまとまりごとの並べ方の組み合わせ（多すぎる時は時刻順のみ）
  const groups = [];
  for (const n of [...ns].sort((a, b) => a.time - b.time)) {
    const g = groups[groups.length - 1];
    if (g && Math.abs(g[0].time - n.time) < 1e-6) g.push(n); else groups.push([n]);
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
function chainReverse(B) {
  const bad = B.map.chains.filter(c => !(c.tailTime > c.time));
  return bad.length ? [F(null, BL.FAIL, 'chainReverse', null, bad.map(ref))] : [];
}
// R6.B.2/3: 頭の向き（点ノーツは下）から、リンクへ向かう線の向きが45度を超えて変わらない
function chainPath(B) {
  const bad = B.map.chains.filter(c => {
    for (let i = 1; i < c.pts.length; i++) {
      const a = c.pts[i - 1], b = c.pts[i];
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
function chainLinkGrid(B) {
  const bad = B.map.chains.filter(c => c.blLinks.some(l => l.pos[0] < -1 - 1e-3 || l.pos[0] > 4 + 1e-3 || l.pos[1] < -1e-3 || l.pos[1] > 2 + 1e-3));
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
//  基本ライトイベントを再現して判定する。フェードは1秒点灯とみなす（BS Map Checkと同じ近似）ので候補扱い
const lightTypesOf = env => { const t = BASIC_TRACKS[env]; return t && t.l.length ? t.l : [0, 1, 2, 3, 4]; };
const isOn = v => v === 1 || v === 5 || v === 9, isFlash = v => v === 2 || v === 6 || v === 10, isFade = v => v === 3 || v === 7 || v === 11, isTrans = v => v === 4 || v === 8 || v === 12;
const dimCol = c => !!c && ((typeof c[3] === 'number' && c[3] < 0.5) || Math.max(c[0], c[1], c[2]) < 0.5);
function litSegments(B) {
  const types = lightTypesOf(B.env), segs = [];
  for (const ty of types) {
    const evs = B.map.basicEvents.filter(e => e.etype === ty).sort((a, b) => a.sec - b.sec);
    evs.forEach((e, i) => {
      const end = i < evs.length - 1 ? evs[i + 1].sec : Infinity;
      const bright = (e.floatValue ?? 1) >= 0.5 && !dimCol(e.customData._color) && !dimCol(e.customData.color);
      if (!bright || e.value === 0) return;
      if (isOn(e.value) || isFlash(e.value) || isTrans(e.value)) segs.push([e.sec, end]);
      else if (isFade(e.value)) segs.push([e.sec, Math.min(end, e.sec + 1)]);
    });
  }
  segs.sort((a, b) => a[0] - b[0]);
  const merged = [];
  for (const s of segs) { const l = merged[merged.length - 1]; if (l && s[0] <= l[1] + EPS) l[1] = Math.max(l[1], s[1]); else merged.push([...s]); }
  return merged;
}
function bombLight(B) {
  const bombs = B.map.bombNotes; if (!bombs.length) return [];
  const hasBoxes = B.map.ebg.color.length > 0;
  if (!V2_ENVS.has(B.env) && hasBoxes) return [F(null, BL.CHECK, 'boxLights')];
  const segs = litSegments(B);
  if (!segs.length) return [F(null, BL.FAIL, 'noLightAtAll', null, bombs.map(ref))];
  const covered = (s, e) => segs.some(g => g[0] <= s + EPS && g[1] >= e - EPS);
  const dark = bombs.filter(b => !covered(b.sec - 0.25, b.sec));
  return dark.length ? [F(null, BL.CHECK, 'bombDark', null, dark.map(ref))] : [];
}

// ---------- R8 壁 ----------
// R8.A.3（候補）: 真ん中の片側だけを塞ぐ壁（dodge wall）で頭を左右へ動かす回数が1秒に2回を超える
function dodgeRate(B) {
  let side = null, lastMove = null; const res = [];
  for (const w of B.walls) {
    if (!blocksStand(w)) continue;
    const c1 = covers(w, 1), c2 = covers(w, 2);
    if (c1 === c2) continue;
    const need = c1 ? 'R' : 'L';
    if (side && need !== side) {
      if (lastMove != null && w.sec - lastMove < 0.5 - EPS) res.push(w);
      lastMove = w.sec;
    }
    side = need;
  }
  return res.length ? [F(null, BL.CHECK, 'dodgeFast', null, res.map(ref))] : [];
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
// R8.C: 13.8ms以下の壁は、同じレーンの正規の壁の後ろ250ms以内、または何かの壁の後ろ100ms以内でないといけない
function legalWall(B) {
  const legal = w => w.dsec * 1000 > 13.8, res = [];
  const sameLane = (a, b) => a.posX < b.posX + b.width && b.posX < a.posX + a.width;
  for (const w of B.walls) {
    if (legal(w) || w.width <= 0) continue;
    const ok = B.walls.some(o => o !== w && sameLane(o, w) && o.sec <= w.sec + EPS
      && w.sec - (o.sec + o.dsec) <= (legal(o) ? 0.25 : 0.1) + EPS);
    if (!ok) res.push(w);
  }
  return res.length ? [F(null, BL.FAIL, 'illegalWall', null, res.map(ref))] : [];
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

const uniq = a => [...new Set(a)];
function lowerSec(arr, s) { let lo = 0, hi = arr.length; while (lo < hi) { const m = (lo + hi) >> 1; if (arr[m].sec < s) lo = m + 1; else hi = m; } return lo; }
function* between(arr, s, e) { for (let i = lowerSec(arr, s - EPS); i < arr.length && arr[i].sec <= e + EPS; i++) yield arr[i]; }
// その秒に続いている壁（壁は開始の時刻順。最長の壁の長さぶんだけ遡って探す）
function* wallsAt(B, sec) { for (const w of between(B.walls, sec - B.maxWallSec, sec)) if (sec <= w.sec + w.dsec + EPS) yield w; }

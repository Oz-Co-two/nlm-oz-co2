// REPLAY の窓の「点を重ねる」（2026-11-22）: リプレイの出来事（serve.py の /__replay/events＝bsor.py の events）を、
// NLE の拍番号の帯の印（ミス・バッド・ボム・壁）と、下の 3D のノーツの輪の色（点の段）に直す。DOM・three.js を使わない（unit_js で確かめる）。
//
// - 出来事の秒 t＝そのノーツの曲の秒＝書き出した song.egg の秒＝NLM の beatToTimeTM(拍)（足し引き無し）。拍へは呼ぶ側の timeToBeatTM で直す。
// - 点の段（tierOf）: BL のリプレイアプリ（BeatSaber-Web-Replays の src/components/beat.js の colorAndScaleForScore と HSVConfig.judgments）と
//   同じ決め方・同じ色＝「点数÷満点×115」が 115 以上＝白・113 以上＝紫・110 以上＝青・106 以上＝緑・100 以上＝黄・それ未満＝赤寄りのピンク（2026-11-22・
//   利用者の決定）。満点はノーツの種類ごと（普通 115・チェーンの頭 85・チェーンの後ろ 20）なので、チェーンの頭の 85 も 115 の段。
//   悪い切り方（バッド＝橙）・見逃し（ミス＝赤）・ボム（マゼンタ）は点の色に無い色の別の段。壁の印は灰色（どの段の色とも違う）。
// - 合わせ方（matchObjects）: 遊んだ後に編集した版でも、合うノーツにだけ付ける。同じ難易度の物で、拍が ±tol（既定 0.01 拍）・列 x・段 y・色 c が同じ
//   （ボムは x・y）。候補が複数なら拍の一番近い物。1つの出来事は1つの物にだけ。チェーンは頭（b・x・y・c）と、頭から尾までの同じ色の出来事
//   （チェーンの後ろの部分＝リンク）をまとめて、一番悪い段にする。ノーツ・ボムを先に合わせる（チェーンの範囲の中の普通のノーツを取らない）。
//   合わない出来事は 3D には出さない（NLE の印は秒の位置に出す・薄く）。
// - 速さ: 出来事は拍の順に並べ、物ごとに二分探索で ±tol の範囲だけを見る（物ごとに全部の出来事をなめない）。NLE の印は見えている範囲だけ（marksRange）。
// - 出来事はサーバー由来（.bsor は他人から受け取ることもある）: cleanEvents で知っている項目・形だけにし、数は EV_MAX まで。

export const EV_MAX = 200000;
/** 段の名前（良い順）。輪・凡例・印の色はこの順 */
export const TIERS = ['t115', 't113', 't110', 't106', 't100', 'low', 'bad', 'miss', 'bomb'];
/** 切った物の段の下限（点数÷満点×115。BL のリプレイアプリの judgments の threshold と同じ・上から順に見る） */
export const CUT_TIERS = [[115, 't115'], [113, 't113'], [110, 't110'], [106, 't106'], [100, 't100']];
/** 色（3D の輪・凡例・NLE の印で共通）。NLE の印の形: ミス＝✕・バッド＝◆・ボム＝●・壁＝▬（審査の指摘の ▼ と形で見分ける） */
export const RP_COL = { t115: '#ffffff', t113: '#8500ff', t110: '#00a3ff', t106: '#00ff00', t100: '#ffff00', low: '#ff0038',
  bad: '#ff8000', miss: '#ff0000', bomb: '#ff00d0', wall: '#c8ccd6' };
/** NLE に印を出す種類 */
export const MARK_KINDS = ['miss', 'bad', 'bomb', 'wall'];
const RANK = Object.fromEntries(TIERS.map((k, i) => [k, i]));   // 悪い方ほど大きい
const TYPES = ['good', 'bad', 'miss', 'bomb'];
const fin = v => typeof v === 'number' && isFinite(v);
const smallInt = v => (fin(v) && v === Math.floor(v) && v >= -1000 && v <= 1000) ? v : null;

/** /__replay/events の応答 → {notes:[{t,type,x,y,c,d,score,max}], walls:[{t}], endSec}（知らない項目・形の違う値は捨てる） */
export function cleanEvents(j) {
  const out = { notes: [], walls: [], endSec: null };
  if (!j || typeof j !== 'object') return out;
  const ns = Array.isArray(j.notes) ? j.notes : [], ws = Array.isArray(j.walls) ? j.walls : [];
  for (let i = 0; i < ns.length && out.notes.length < EV_MAX; i++) {
    const e = ns[i];
    if (!e || typeof e !== 'object' || !fin(e.t) || e.t < 0 || e.t > 36000 || !TYPES.includes(e.type)) continue;
    const x = smallInt(e.x), y = smallInt(e.y);
    if (x == null || y == null) continue;
    const c = e.type === 'bomb' ? null : (e.c === 0 || e.c === 1 ? e.c : null);
    if (e.type !== 'bomb' && c == null) continue;
    const good = e.type === 'good' && fin(e.score) && fin(e.max) && e.max >= 0 && e.max <= 1000;
    out.notes.push({ t: e.t, type: e.type, x, y, c, d: e.type === 'bomb' ? null : smallInt(e.d),
      score: good ? Math.max(0, Math.min(e.max, e.score)) : null, max: good ? e.max : null });
  }
  for (let i = 0; i < ws.length && out.walls.length < EV_MAX; i++) {
    const w = ws[i];
    if (w && typeof w === 'object' && fin(w.t) && w.t >= 0 && w.t <= 36000) out.walls.push({ t: w.t });
  }
  if (fin(j.endSec) && j.endSec >= 0) out.endSec = j.endSec;
  return out;
}

/** 出来事の段（TIERS の1つ） */
export function tierOf(e) {
  if (!e) return null;
  if (e.type === 'miss' || e.type === 'bad' || e.type === 'bomb') return e.type;
  if (!fin(e.max) || !fin(e.score) || e.max <= 0) return 't115';   // 点の付かない種類（満点 0）
  const v = e.score / e.max * 115;   // BL のアプリと同じ式・同じ順の計算（端数の出方もそろう）
  for (const [th, k] of CUT_TIERS) if (v >= th) return k;
  return 'low';
}
/** 2つの段の悪い方 */
export const worseTier = (a, b) => a == null ? b : b == null ? a : (RANK[b] > RANK[a] ? b : a);

/** 並んだ数の列で v 以上の最初の番号 */
export function lowerBound(arr, v) {
  let lo = 0, hi = arr.length;
  while (lo < hi) { const m = (lo + hi) >> 1; if (arr[m] < v) lo = m + 1; else hi = m; }
  return lo;
}

/** 拍に直して並べる。toBeat＝秒→拍（NLM の timeToBeatTM）。
 * → {n:[{beat,t,type,x,y,c,score,max,tier}]（ノーツ・ボムの出来事・拍の順）, nb:Float64Array（n の拍）,
 *    m:[{beat,t,kind,ni}]（NLE の印＝ミス・バッド・ボム・壁・拍の順。ni＝n の番号・壁は -1）, mb:Float64Array（m の拍）, walls:数} */
export function prepEvents(ev, toBeat) {
  const n = [];
  for (const e of (ev && ev.notes) || []) {
    const beat = toBeat(e.t);
    if (!fin(beat)) continue;
    n.push({ beat, t: e.t, type: e.type, x: e.x, y: e.y, c: e.c, score: e.score, max: e.max, tier: tierOf(e) });
  }
  n.sort((a, b) => a.beat - b.beat);
  const m = [];
  for (let i = 0; i < n.length; i++) if (n[i].type !== 'good') m.push({ beat: n[i].beat, t: n[i].t, kind: n[i].type, ni: i });
  let walls = 0;
  for (const w of (ev && ev.walls) || []) {
    const beat = toBeat(w.t);
    if (!fin(beat)) continue;
    m.push({ beat, t: w.t, kind: 'wall', ni: -1 }); walls++;
  }
  m.sort((a, b) => a.beat - b.beat || MARK_KINDS.indexOf(a.kind) - MARK_KINDS.indexOf(b.kind));
  return { n, nb: Float64Array.from(n, e => e.beat), m, mb: Float64Array.from(m, e => e.beat), walls };
}

/** NLE の印のうち拍 b0〜b1 の物の番号の範囲 [i0, i1) */
export function marksRange(prep, b0, b1) {
  if (!prep) return [0, 0];
  return [lowerBound(prep.mb, b0), lowerBound(prep.mb, b1 + 1e-9)];
}

/** 今の難易度の物に出来事を合わせる。objs＝{notes:[{beat,x,y,c}], bombs:[{beat,x,y}], chains:[{b,x,y,c,tb}]}（_ghost＝貼り付けの追従中の物は除く）。
 * → {map: Map(物 → {tier, ev（頭の出来事）, links（チェーンの後ろの数）}), used: Uint8Array（n ごとに合った物があるか）, unNotes, unBombs} */
export function matchObjects(prep, objs, tol = 0.01) {
  const map = new Map();
  if (!prep) return { map, used: new Uint8Array(0), unNotes: 0, unBombs: 0 };
  const { n, nb } = prep, used = new Uint8Array(n.length);
  const pick = (beat, ok) => {   // 拍 ±tol で条件に合う・まだ使っていない一番近い出来事の番号
    let best = -1, bd = Infinity;
    for (let i = lowerBound(nb, beat - tol); i < n.length && nb[i] <= beat + tol; i++) {
      if (used[i] || !ok(n[i])) continue;
      const d = Math.abs(nb[i] - beat);
      if (d < bd) { bd = d; best = i; }
    }
    return best;
  };
  const take = (o, i) => { used[i] = 1; const e = n[i]; map.set(o, { tier: e.tier, ev: e, links: 0 }); };
  for (const o of (objs && objs.notes) || []) {
    if (!o || o._ghost || !fin(o.beat)) continue;
    const i = pick(o.beat, e => e.type !== 'bomb' && e.x === o.x && e.y === o.y && e.c === o.c);
    if (i >= 0) take(o, i);
  }
  for (const o of (objs && objs.bombs) || []) {
    if (!o || o._ghost || !fin(o.beat)) continue;
    const i = pick(o.beat, e => e.type === 'bomb' && e.x === o.x && e.y === o.y);
    if (i >= 0) take(o, i);
  }
  for (const o of (objs && objs.chains) || []) {
    if (!o || o._ghost || !fin(o.b)) continue;
    const h = pick(o.b, e => e.type !== 'bomb' && e.x === o.x && e.y === o.y && e.c === o.c);
    if (h < 0) continue;   // 頭の合わないチェーンは後ろも合わせない（編集で動かしたチェーン）
    take(o, h);
    const r = map.get(o), tb = fin(o.tb) ? Math.max(o.b, o.tb) : o.b;
    for (let i = lowerBound(nb, o.b); i < n.length && nb[i] <= tb + tol; i++) {   // 頭の後ろから尾までの同じ色＝チェーンの後ろの部分
      if (used[i] || n[i].type === 'bomb' || n[i].c !== o.c) continue;
      used[i] = 1; r.links++; r.tier = worseTier(r.tier, n[i].tier);
    }
  }
  let unNotes = 0, unBombs = 0;
  for (let i = 0; i < n.length; i++) if (!used[i]) { if (n[i].type === 'bomb') unBombs++; else unNotes++; }
  return { map, used, unNotes, unBombs };
}

/** 段ごとの数（凡例に出す・合った物だけ）。→ {t115:n, …} */
export function tierCounts(match) {
  const out = Object.fromEntries(TIERS.map(k => [k, 0]));
  if (match) for (const r of match.map.values()) if (r.tier in out) out[r.tier]++;
  return out;
}

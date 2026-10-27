// 審査の指摘を画面で扱うための、DOM を使わない部品（2026-10-27）。画面は review-panel.js、読む・書く形は review-txt.js。
//  - importParsed: parseReviewText の結果を、プロジェクトに保存する形（下の「保存する形」）へ移す（難易度の分からない項目に選んだ難易度を入れる・
//    C3＝曲データを読み込んだ時に拍を付け替えた難易度は、指摘の拍を元の譜面の拍として NLM の拍へ直す）
//  - sanitizeReview: 保存した物（.nlmf＝ファイル由来）を、知っている項目・正しい形だけにする
//  - toFormatItems: 保存した形を formatReviewText の形へ戻す（返事を付けた .txt の書き出し）
//  - pickTargets: 指摘の拍に当たる物を探す（±0.01 拍・無ければ ±1/16 拍で一番近い物）
//  - checksToItems: NLM の確かめの結果（BL評価リスト・BS Map Check）を指摘の形にする（英語の文は呼ぶ側が作って渡す）
//  - srcTpOk / origToNlm: 読み込んだクリップに持たせた「元の譜面のテンポ」（srcTp）の形の確かめと、元の拍→NLM の拍
//
// 保存する形（プロジェクトの review。無ければキーごと無し）:
//   {v:1, items:[Item], notes:[Note], srcs:[{id, name, kind:'file'|'paste', at, n}]}
//   Item: {id, src, line, difficulty(null＝分からない), mode('Standard' 等), label, beats:[拍], ranges:[[a,b]],
//          nlmBeats?, nlmRanges?（C3 で直した NLM の拍。無ければ beats・ranges と同じ）, severity('X'|'?'|'S'|'N'|null), mark,
//          text, cont:[続きの行], reply（返事）, done（済み）, repeats, parent（字下げした細かい指摘の親の id）, group, groupText, sameAsPrev, prev（指す項目の id）, ambiguous}
//   Note: {src, line, text, kind('comment'|'divider'|'unreadable'|'mapper'), difficulty, mode, label}
// 文は他人の文章なので、画面では textContent でだけ使う。
import { REVIEW_DIFFS, REVIEW_LIMITS } from './review-txt.js';

export const RV_VERSION = 1;
export const RV_SEVS = Object.freeze(['X', '?', 'S', 'N']);
export const RV_LIMITS = Object.freeze({ items: REVIEW_LIMITS.maxItems, notes: 10000, srcs: 200, text: REVIEW_LIMITS.maxLineChars, cont: 50, spots: 200, reply: 4000 });
export const JUMP_TOL = 0.01;        // 指摘の拍と物の拍の差（丸めて書かれる 1/3 拍＝.33 等も入る）
export const JUMP_NEAR = 1 / 16;     // 見つからない時に「近い物」を探す幅

const CTRL_RE = /[\u0000-\u0008\u000B\u000C\u000E-\u001F\u007F\u200B-\u200F\u202A-\u202E\u2060-\u2069\uFEFF]/g;
const MODE_RE = /^[A-Za-z0-9]{1,20}$/;
const ID_RE = /^[rs]\d{1,9}$/;
const KINDS = ['comment', 'divider', 'unreadable', 'mapper'];
const str = (v, max) => (typeof v === 'string' ? v.replace(CTRL_RE, '').slice(0, max) : '');
const optStr = (v, max) => { const s = str(v, max).trim(); return s ? s : null; };
const beatOk = v => typeof v === 'number' && Number.isFinite(v) && v >= -1e5 && v <= 1e5;
const beatsOf = v => (Array.isArray(v) ? v.filter(beatOk).slice(0, RV_LIMITS.spots) : []);
const rangesOf = v => (Array.isArray(v) ? v.filter(r => Array.isArray(r) && r.length === 2 && beatOk(r[0]) && beatOk(r[1]))
  .map(r => [Math.min(r[0], r[1]), Math.max(r[0], r[1])]).slice(0, RV_LIMITS.spots) : []);
const r6 = v => Math.round(v * 1e6) / 1e6;

// ---------------------------------------------------------------- C3: 元の譜面のテンポ（srcTp）

/** 読み込んだクリップに持たせる srcTp の形（ファイル由来なので確かめる）: {b:基準の BPM, f:[[拍,BPM]…]＝元の譜面のテンポ, t:[[拍,BPM]…]＝読み込んだ時の NLM のテンポ} */
export function srcTpOk(v) {
  const list = a => Array.isArray(a) && a.length <= 10000 && a.every(p => Array.isArray(p) && p.length === 2
    && typeof p[0] === 'number' && Number.isFinite(p[0]) && Math.abs(p[0]) <= 1e7 && typeof p[1] === 'number' && Number.isFinite(p[1]) && p[1] > 0 && p[1] <= 1e7);
  return !!v && typeof v === 'object' && !Array.isArray(v) && typeof v.b === 'number' && Number.isFinite(v.b) && v.b > 0 && v.b <= 1e7 && list(v.f) && list(v.t);
}
// editor-app.js の tpBeatToSec / tpSecToBeat と同じ計算（テンポの表＝基準の BPM ＋ [拍,BPM] の並び）
function beatToSec(base, parts, b) {
  let bb = 0, bpm = base, tt = 0;
  for (const [pb, pm] of parts) { if (pb >= b) break; tt += (pb - bb) * 60 / bpm; bb = pb; bpm = pm; }
  return tt + (b - bb) * 60 / bpm;
}
function secToBeat(base, parts, tm) {
  let bb = 0, bpm = base, tt = 0;
  for (const [pb, pm] of parts) { const seg = (pb - bb) * 60 / bpm; if (tt + seg > tm) break; tt += seg; bb = pb; bpm = pm; }
  return bb + (tm - tt) * bpm / 60;
}
/** 元の譜面の拍 b → NLM の拍（読み込んだ時の付け替え retimeFrag と同じ式・小数6桁） */
export function origToNlm(tp, b) {
  if (!srcTpOk(tp) || !beatOk(b)) return b;
  return r6(secToBeat(tp.b, tp.t, beatToSec(tp.b, tp.f, b)));
}

// ---------------------------------------------------------------- 読み込み

/** 難易度の分からない項目の組（読み込む時に利用者が難易度を選ぶ）。key＝見出しの名前（無ければ ''） */
export function unknownGroups(parsed) {
  const by = new Map();
  for (const it of (parsed && parsed.items) || []) {
    if (it.difficulty || it.otherMode) continue;
    const key = it.label || '';
    by.set(key, (by.get(key) || 0) + 1);
  }
  return [...by].map(([key, n]) => ({ key, label: key || null, n }));
}

/** 読み込んだ結果の数（読み込みの確認の画面用）: 難易度ごとの項目・分からない・Standard 以外・拍の無い行・読めなかった行 */
export function parsedStats(parsed) {
  const by = {}; let unknown = 0, other = 0;
  for (const it of (parsed && parsed.items) || []) {
    if (it.otherMode) { other++; continue; }
    if (!it.difficulty) { unknown++; continue; }
    by[it.difficulty] = (by[it.difficulty] || 0) + 1;
  }
  const notes = (parsed && parsed.notes) || [];
  return { by, unknown, other, notes: notes.filter(n => n.kind !== 'unreadable').length, unreadable: notes.filter(n => n.kind === 'unreadable').length,
    responses: ((parsed && parsed.items) || []).filter(it => it.response).length };
}

/**
 * parseReviewText の結果を保存する形へ。
 * @param parsed parseReviewText の結果
 * @param o {src:取り込みの id, nextId:()=>新しい項目の id, pick:{見出しの名前（無ければ ''）:難易度}, retime:{難易度:srcTp}, asOrig:{難易度:bool}}
 * @returns {{items, notes}}
 */
export function importParsed(parsed, o = {}) {
  const pick = o.pick || {}, retime = o.retime || {}, asOrig = o.asOrig || {};
  const ids = [];
  const items = [];
  for (const it of (parsed && parsed.items) || []) {
    const id = o.nextId(); ids.push(id);
    let d = REVIEW_DIFFS.includes(it.difficulty) ? it.difficulty : null;
    if (!d && !it.otherMode) { const p = pick[it.label || '']; if (REVIEW_DIFFS.includes(p)) d = p; }
    const mode = typeof it.mode === 'string' && MODE_RE.test(it.mode) ? it.mode : 'Standard';
    const x = {
      id, src: o.src || null, line: Number.isInteger(it.line) ? it.line : 0, difficulty: d, mode, label: optStr(it.label, 80),
      beats: beatsOf(it.beats), ranges: rangesOf(it.ranges), severity: RV_SEVS.includes(it.severity) ? it.severity : null, mark: optStr(it.mark, 40),
      text: str(it.text, RV_LIMITS.text), cont: (Array.isArray(it.cont) ? it.cont : []).map(c => str(c, RV_LIMITS.text)).filter(Boolean).slice(0, RV_LIMITS.cont),
      reply: str(it.response || '', RV_LIMITS.reply).trim(), done: false, repeats: !!it.repeats,
      parent: Number.isInteger(it.parent) ? it.parent : null, group: Number.isInteger(it.group) ? it.group : null, groupText: optStr(it.groupText, RV_LIMITS.text),
      sameAsPrev: !!it.sameAsPrev, prev: Number.isInteger(it.prev) ? it.prev : null, ambiguous: !!it.ambiguous,
    };
    const tp = d && mode === 'Standard' && asOrig[d] ? retime[d] : null;
    if (tp && srcTpOk(tp)) { x.nlmBeats = x.beats.map(b => origToNlm(tp, b)); x.nlmRanges = x.ranges.map(r => [origToNlm(tp, r[0]), origToNlm(tp, r[1])]); }
    if (!x.beats.length && !x.ranges.length) continue;   // 拍の無い項目は無い（parseReviewText は拍で始まる行だけを項目にする）
    items.push(x);
  }
  // 添字（読み込んだ結果の中）→ id
  const have = new Set(items.map(x => x.id));
  const idOf = i => (i != null && ids[i] && have.has(ids[i]) ? ids[i] : null);
  for (const x of items) {
    x.parent = idOf(x.parent);
    x.prev = idOf(x.prev);
    if (x.group != null) x.group = `${o.src || ''}:${x.group}`;
  }
  const notes = ((parsed && parsed.notes) || []).slice(0, RV_LIMITS.notes).map(n => ({
    src: o.src || null, line: Number.isInteger(n.line) ? n.line : 0, text: str(n.text, RV_LIMITS.text),
    kind: KINDS.includes(n.kind) ? n.kind : 'comment', difficulty: REVIEW_DIFFS.includes(n.difficulty) ? n.difficulty : null,
    mode: typeof n.mode === 'string' && MODE_RE.test(n.mode) ? n.mode : 'Standard', label: optStr(n.label, 80),
  })).filter(n => n.text.trim());
  return { items, notes };
}

// ---------------------------------------------------------------- 保存した物を確かめる（ファイル由来）

/** プロジェクトの review を、知っている項目・正しい形だけにする。中身が無ければ null */
export function sanitizeReview(v) {
  if (!v || typeof v !== 'object' || Array.isArray(v)) return null;
  const srcs = (Array.isArray(v.srcs) ? v.srcs : []).filter(s => s && typeof s === 'object' && typeof s.id === 'string' && ID_RE.test(s.id))
    .slice(0, RV_LIMITS.srcs).map(s => ({ id: s.id, name: optStr(s.name, 200), kind: s.kind === 'paste' ? 'paste' : 'file',
      at: typeof s.at === 'string' && /^\d{4}-\d\d-\d\dT[\d:.]+Z?$/.test(s.at) ? s.at : null, n: Number.isInteger(s.n) && s.n >= 0 ? s.n : 0 }));
  const srcIds = new Set(srcs.map(s => s.id));
  const seen = new Set();
  const items = [];
  for (const x of (Array.isArray(v.items) ? v.items : []).slice(0, RV_LIMITS.items)) {
    if (!x || typeof x !== 'object' || typeof x.id !== 'string' || !ID_RE.test(x.id) || seen.has(x.id)) continue;
    const beats = beatsOf(x.beats), ranges = rangesOf(x.ranges);
    if (!beats.length && !ranges.length) continue;
    seen.add(x.id);
    const it = {
      id: x.id, src: typeof x.src === 'string' && srcIds.has(x.src) ? x.src : null, line: Number.isInteger(x.line) && x.line >= 0 ? x.line : 0,
      difficulty: REVIEW_DIFFS.includes(x.difficulty) ? x.difficulty : null, mode: typeof x.mode === 'string' && MODE_RE.test(x.mode) ? x.mode : 'Standard',
      label: optStr(x.label, 80), beats, ranges, severity: RV_SEVS.includes(x.severity) ? x.severity : null, mark: optStr(x.mark, 40),
      text: str(x.text, RV_LIMITS.text), cont: (Array.isArray(x.cont) ? x.cont : []).map(c => str(c, RV_LIMITS.text)).filter(Boolean).slice(0, RV_LIMITS.cont),
      reply: str(x.reply, RV_LIMITS.reply), done: x.done === true, repeats: x.repeats === true,
      parent: typeof x.parent === 'string' && ID_RE.test(x.parent) ? x.parent : null,
      group: typeof x.group === 'string' && x.group.length <= 40 ? x.group : null, groupText: optStr(x.groupText, RV_LIMITS.text),
      sameAsPrev: x.sameAsPrev === true, prev: typeof x.prev === 'string' && ID_RE.test(x.prev) ? x.prev : null, ambiguous: x.ambiguous === true,
    };
    // NLM の拍（C3）は、書いた拍と同じ数の時だけ
    const nb = beatsOf(x.nlmBeats), nr = rangesOf(x.nlmRanges);
    if (Array.isArray(x.nlmBeats) && nb.length === beats.length && nr.length === ranges.length) { it.nlmBeats = nb; it.nlmRanges = nr; }
    items.push(it);
  }
  const ids = new Set(items.map(x => x.id));
  for (const x of items) { if (x.parent && !ids.has(x.parent)) x.parent = null; if (x.prev && !ids.has(x.prev)) x.prev = null; }
  const notes = (Array.isArray(v.notes) ? v.notes : []).slice(0, RV_LIMITS.notes).filter(n => n && typeof n === 'object').map(n => ({
    src: typeof n.src === 'string' && srcIds.has(n.src) ? n.src : null, line: Number.isInteger(n.line) && n.line >= 0 ? n.line : 0,
    text: str(n.text, RV_LIMITS.text), kind: KINDS.includes(n.kind) ? n.kind : 'comment',
    difficulty: REVIEW_DIFFS.includes(n.difficulty) ? n.difficulty : null, mode: typeof n.mode === 'string' && MODE_RE.test(n.mode) ? n.mode : 'Standard',
    label: optStr(n.label, 80),
  })).filter(n => n.text.trim());
  if (!items.length && !notes.length) return null;
  return { items, notes, srcs };
}

// ---------------------------------------------------------------- 飛ぶ・書き出す

/** 指摘の位置（NLM の拍）: [{a, b(範囲の終わり・無ければ null)}]。書いた拍→範囲の順 */
export function spotsOf(it) {
  const bs = it.nlmBeats || it.beats || [], rs = it.nlmRanges || it.ranges || [];
  return [...bs.map(a => ({ a, b: null })), ...rs.map(r => ({ a: r[0], b: r[1] }))];
}
/** 書いた拍（元の拍）での位置。spotsOf と同じ順 */
export function writtenSpotsOf(it) {
  return [...(it.beats || []).map(a => ({ a, b: null })), ...(it.ranges || []).map(r => ({ a: r[0], b: r[1] }))];
}
/** 項目が NLM で飛べるか（Standard・難易度が分かっている） */
export const jumpable = it => !!it && !!it.difficulty && it.mode === 'Standard';

/**
 * 指摘の位置に当たる物を探す。pool: [{beat, ref}]（ref＝呼ぶ側の物）
 * 1点の拍: ±tol の物。無ければ ±near の中で一番近い拍の物（同じ拍の物は全部）＝「近い物」。範囲: [a−tol, b+tol] の物
 * @returns {{refs, kinds:('exact'|'near'|'none')[], kind:'exact'|'near'|'none', seek:number, delta:number}} seek＝動かす拍（最初の位置。近い物ならその物の拍）
 */
export function pickTargets(pool, spots, tol = JUMP_TOL, near = JUMP_NEAR) {
  const refs = new Set(), kinds = [];
  let seek = null, delta = 0;
  for (const s of spots || []) {
    if (!s || !Number.isFinite(s.a)) { kinds.push('none'); continue; }
    if (s.b != null && Number.isFinite(s.b)) {
      const hit = pool.filter(p => p.beat >= s.a - tol && p.beat <= s.b + tol);
      for (const p of hit) refs.add(p.ref);
      kinds.push(hit.length ? 'exact' : 'none');
      if (seek == null) seek = s.a;
      continue;
    }
    let hit = pool.filter(p => Math.abs(p.beat - s.a) <= tol);
    if (hit.length) { kinds.push('exact'); if (seek == null) seek = s.a; }
    else {
      let best = Infinity;
      for (const p of pool) { const d = Math.abs(p.beat - s.a); if (d <= near + 1e-9 && d < best) best = d; }
      if (Number.isFinite(best)) {
        hit = pool.filter(p => Math.abs(Math.abs(p.beat - s.a) - best) < 1e-6);
        kinds.push('near');
        if (seek == null) { seek = hit[0].beat; delta = hit[0].beat - s.a; }
      } else { kinds.push('none'); if (seek == null) seek = s.a; }
    }
    for (const p of hit) refs.add(p.ref);
  }
  const kind = !refs.size ? 'none' : kinds.includes('near') ? 'near' : 'exact';
  return { refs: [...refs], kinds, kind, seek: seek == null ? 0 : seek, delta };
}

/**
 * 保存した形 → formatReviewText の形（返事を付けた .txt）。書いた拍（元の拍）のまま書く（審査の人の譜面の拍）。
 * opts.fixedForDone: 済みで返事の無い項目に「fixed」と書く
 */
export function toFormatItems(items, opts = {}) {
  return (items || []).map(x => ({
    difficulty: x.difficulty, mode: x.mode, label: x.label, beats: x.beats, ranges: x.ranges, severity: x.severity, repeats: x.repeats,
    text: x.text, cont: x.cont, parent: x.parent ? 0 : null, group: x.group, groupText: x.groupText,
    response: x.reply && x.reply.trim() ? x.reply.trim() : (opts.fixedForDone && x.done ? 'fixed' : ''),
  }));
}
/** 保存した形の拍の無い行 → formatReviewText の notes */
export const toFormatNotes = notes => (notes || []).map(n => ({ text: n.text, difficulty: n.difficulty, mode: n.mode, kind: n.kind === 'divider' ? 'divider' : 'comment' }));

const DIFF_ORDER = ['ExpertPlus', 'Expert', 'Hard', 'Normal', 'Easy'];   // 実物の .txt と同じく難しい方から
const PER_LINE = 8;   // 1行に書く拍の数（多い所見は行を分ける）

/**
 * NLM の確かめの結果を指摘の形（formatReviewText の items）にする。拍のある所見・結果だけ（拍の無い所見は数だけ返す）。
 * @param mc runMapCheck の結果 / bl runBlCriteria の結果
 * @param o {fail, check（BL評価リストの違反・要確認）, mc（BS Map Check のランク不可・エラー・警告）, blText(rule, finding), mcText(result), statusRank}
 * @returns {{items, noBeat:number, n:{bl, mc}}} items の origin＝'bl'|'mc'（formatReviewText は使わない）
 */
export function checksToItems(mc, bl, o) {
  const out = [];
  let noBeat = 0, nBl = 0, nMc = 0;
  const beatsOfObjs = objs => [...new Set((objs || []).map(x => x && x.beat).filter(b => typeof b === 'number' && Number.isFinite(b) && b >= 0)
    .map(b => r6(b)))].sort((a, b) => a - b);
  const push = (origin, d, beats, text, severity, ord) => {
    for (let i = 0; i < beats.length; i += PER_LINE) out.push({ difficulty: d, mode: 'Standard', beats: beats.slice(i, i + PER_LINE), ranges: [], text, severity, origin, _ord: ord });
  };
  if (bl && Array.isArray(bl.rules)) {
    bl.rules.forEach((r, ri) => {
      for (const f of r.findings || []) {
        const want = (f.status === 'fail' && o.fail) || (f.status === 'check' && o.check);
        if (!want) continue;
        const beats = beatsOfObjs(f.objs);
        if (!f.d || !beats.length) { noBeat++; continue; }
        push('bl', f.d, beats, `[${r.id}] ${o.blText(r, f)} (NLM)`, f.status === 'fail' ? 'X' : '?', ri);
        nBl++;
      }
    });
  }
  if (o.mc && mc && Array.isArray(mc.diffs)) {
    const SEV = { rank: 'X', error: 'X', warn: '?' };
    for (const d of mc.diffs) {
      (d.results || []).forEach((r, ri) => {
        if (!SEV[r.status]) return;
        const beats = beatsOfObjs(r.objs);
        if (!beats.length) { noBeat++; return; }
        push('mc', d.difficulty, beats, `[BS Map Check] ${o.mcText(r)} (NLM)`, SEV[r.status], 1000 + ri);
        nMc++;
      });
    }
    noBeat += ((mc.general || []).filter(r => SEV[r.status])).length;
  }
  out.sort((a, b) => DIFF_ORDER.indexOf(a.difficulty) - DIFF_ORDER.indexOf(b.difficulty) || a._ord - b._ord || a.beats[0] - b.beats[0]);
  for (const x of out) delete x._ord;
  return { items: out, noBeat, n: { bl: nBl, mc: nMc } };
}

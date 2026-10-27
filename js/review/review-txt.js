// BeatLeader の審査の人が手で書く「拍 - コメント」の指摘（.txt・Discord の本文の貼り付け）を読む／同じ形で書き出す（2026-10-27）。
// DOM を使わない純粋な関数だけ。画面（タイムラインの印・3D の選択・一覧・mapCheckJump）への組み込みはまだ（CLAUDE.md「審査の指摘の .txt」）。
//
// 実物の書き方（審査の人 9人・.txt 19件と Discord の本文 192件の調べ）:
//   - 1行に1件。多い順に「拍 - 文」「拍 文」（区切りなし）「拍: 文」。AutoModder の書き出しの形と同じ物は 0件＝全部手書き。
//   - 難易度は見出しの行（Expert+ / Ex+ ⏎ ----- / ex: / Hard (…) / One Saber Ex+ / Someone's Extreme Demon (Ex+)）か、
//     ファイル名（Expert.txt・Hard_1.txt）。1行目が難易度名・2行目が担当マッパー名の人もいる。中の見出しはファイル名より優先。
//   - 拍は譜面ファイルの拍。小数はばらばら（1/3 拍が .33・.333・.667・.583…）＝ここでは丸めない（照合は呼ぶ側が近い物を探す）。
//   - 複数 `12, 12.5`・`and`・`&`、範囲 `210-225`・`72 to 74`・`38 thru 39`・`9>14`、「…など」`30...`・`(etc.)`・`(and repeats)`、
//     括弧で同じ所 `119.5 (343.5)`。` - ` は範囲にも区切りにも使われる（数・-・数で後ろが大きければ範囲、と読む＝AutoModder と同じ目安）。
//   - 拍の無い行（全体への意見・区切りの線・字下げした続きの行・`^`）は捨てずに notes／cont に持つ。読めない行（`231.g`）も notes へ。
//
// 読んだ文は他人の文章なので、画面では textContent でだけ使う（HTML にしない）。大きさ・行数に上限がある（REVIEW_LIMITS）。
//
// 書き出し（formatReviewText）は実物と同じ手書きの形（難易度の見出しの行＋`拍, 拍 - 文`、CRLF）。AutoModder v1.6.6 の取り込み
// （ChroMapper の「Import Mod」）は「数を含む行」を読み、重さの印は任意＝どちらでも取り込める。ただし AutoModder は:
//   - 行のどこかの最初の数を拍として読む（見出し・前書きの行に数を入れると拍として取り込まれる。90Degree・360Degree の見出しも）
//   - 印の無い行は前の行の重さを引き継ぐ（印を付ける時は全部の行に付ける＝severity:true は印の無い項目に (N) を付ける）
//   - 文の先頭の記号（[ や ( 等）を消す
//   - 範囲は `a-b`・`a to b`・`a - b`（後ろが大きい時）だけ読む（`>` は読まない）＝範囲は `a-b` で書く

export const REVIEW_LIMITS = Object.freeze({
  maxBytes: 2 * 1024 * 1024,   // バイト列（decodeReviewBytes）。これを超えたら読まない
  maxChars: 2 * 1024 * 1024,   // 文字列（parseReviewText）。超えた分は読まずに warnings へ
  maxLines: 20000,
  maxLineChars: 4000,          // 1行の長さ。超えた分は切る
  maxItems: 10000,
});

export const REVIEW_DIFFS = Object.freeze(['Easy', 'Normal', 'Hard', 'Expert', 'ExpertPlus']);

// ---------------------------------------------------------------- 文字コード

/**
 * 他人の .txt のバイト列を文字列にする。BOM（UTF-8・UTF-16LE/BE）を見分け、BOM の無い UTF-16 も0のバイトの並びで見分ける。
 * UTF-8 として正しくなければ Shift_JIS（日本語のメモ帳の古い既定）→ Windows-1252 の順に試す。
 * @param {Uint8Array|ArrayBuffer|ArrayBufferView} bytes
 * @param {{maxBytes?:number}} [opts]
 * @returns {string}
 * @throws {RangeError} 大きすぎる時（e.code === 'too-large'）
 */
export function decodeReviewBytes(bytes, opts = {}) {
  let u8;
  if (bytes instanceof Uint8Array) u8 = bytes;
  else if (bytes instanceof ArrayBuffer) u8 = new Uint8Array(bytes);
  else if (ArrayBuffer.isView(bytes)) u8 = new Uint8Array(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  else throw new TypeError('bytes');
  const max = Number.isFinite(opts.maxBytes) ? opts.maxBytes : REVIEW_LIMITS.maxBytes;
  if (u8.length > max) { const e = new RangeError('too-large'); e.code = 'too-large'; throw e; }
  let enc = null, off = 0;
  if (u8[0] === 0xEF && u8[1] === 0xBB && u8[2] === 0xBF) { enc = 'utf-8'; off = 3; }
  else if (u8[0] === 0xFF && u8[1] === 0xFE) { enc = 'utf-16le'; off = 2; }
  else if (u8[0] === 0xFE && u8[1] === 0xFF) { enc = 'utf-16be'; off = 2; }
  else enc = guessUtf16(u8);
  const body = u8.subarray(off);
  if (enc === 'utf-16le' || enc === 'utf-16be') return new TextDecoder(enc, { ignoreBOM: true }).decode(body);
  try { return new TextDecoder('utf-8', { fatal: true, ignoreBOM: true }).decode(body); } catch (_) { /* 次を試す */ }
  try { return new TextDecoder('shift_jis', { fatal: true }).decode(body); } catch (_) { /* 次を試す */ }
  return new TextDecoder('windows-1252').decode(body);
}

// BOM の無い UTF-16: 英語の文は2バイトごとに片側が0になる
function guessUtf16(u8) {
  const n = Math.min(u8.length, 4096) & ~1;
  if (n < 4) return 'utf-8';
  let even = 0, odd = 0;
  for (let i = 0; i < n; i += 2) { if (u8[i] === 0) even++; if (u8[i + 1] === 0) odd++; }
  const pairs = n / 2;
  if (odd > pairs * 0.3 && even < pairs * 0.05) return 'utf-16le';
  if (even > pairs * 0.3 && odd < pairs * 0.05) return 'utf-16be';
  return 'utf-8';
}

// ---------------------------------------------------------------- 難易度・モードの名前

const DIFF_WORD = {
  'expert+': 'ExpertPlus', 'expertplus': 'ExpertPlus', 'exp+': 'ExpertPlus', 'ex+': 'ExpertPlus', 'e+': 'ExpertPlus', 'x+': 'ExpertPlus',
  'expert': 'Expert', 'exp': 'Expert', 'ex': 'Expert', 'e': 'Expert',
  'hard': 'Hard', 'hd': 'Hard', 'h': 'Hard',
  'normal': 'Normal', 'norm': 'Normal', 'nm': 'Normal', 'n': 'Normal',
  'easy': 'Easy', 'ez': 'Easy',
};
const MODE_WORD = {
  'standard': 'Standard', 'std': 'Standard', 'onesaber': 'OneSaber', '1saber': 'OneSaber', 'noarrows': 'NoArrows',
  '90degree': '90Degree', '90degrees': '90Degree', '360degree': '360Degree', '360degrees': '360Degree',
  'lightshow': 'Lightshow', 'lawless': 'Lawless', 'legacy': 'Legacy',
};
const DIFF_SRC = '(expert\\s*\\+|expert\\s*plus|exp\\s*\\+|ex\\s*\\+|e\\s*\\+|x\\s*\\+|expert|exp|ex|e|hard|hd|h|normal|norm|nm|n|easy|ez)';
const MODE_SRC = '(standard|std|one\\s*saber|1\\s*saber|no\\s*arrows|90\\s*degrees?|360\\s*degrees?|lightshow|lawless|legacy)';
// 見出しの行（その語だけの行）: [モード] 難易度 [(注記)] / 難易度 モード / 名前 ([モード] 難易度)
const HEAD_RE1 = new RegExp(`^(?:${MODE_SRC}[\\s_-]*)?${DIFF_SRC}(?:\\s*\\((.{0,120})\\))?$`, 'i');
const HEAD_RE1B = new RegExp(`^${DIFF_SRC}[\\s_-]*${MODE_SRC}$`, 'i');
const HEAD_RE2 = new RegExp(`^(.{1,60}?)\\s*\\(\\s*(?:${MODE_SRC}[\\s_-]*)?${DIFF_SRC}\\s*\\)$`, 'i');
// 「a bit more for for ex+:」のような、コロンで終わる短い行の中の難易度（推測なので warnings に出す）
const HEAD_LOOSE = new RegExp(`(?:^|[\\s(])(?:${MODE_SRC}[\\s_-]*)?(expert\\s*\\+|expert\\s*plus|ex\\s*\\+|e\\s*\\+|expert|ex|hard|normal|easy)(?=$|[\\s):,])`, 'i');

const diffOf = w => DIFF_WORD[String(w || '').toLowerCase().replace(/\s+/g, '')] || null;
const modeOf = w => (w ? MODE_WORD[String(w).toLowerCase().replace(/\s+/g, '')] || null : null) || 'Standard';
const labelKey = s => String(s || '').toLowerCase().replace(/['\u2019`]/g, '').replace(/[\s_-]+/g, ' ').trim();

function normLabels(labels) {
  const m = new Map();
  const add = (label, v) => {
    if (typeof label !== 'string') return;
    const d = typeof v === 'string' ? v : v && typeof v === 'object' ? v.difficulty : null;
    if (!REVIEW_DIFFS.includes(d)) return;
    const mode = v && typeof v === 'object' && typeof v.mode === 'string' && /^[A-Za-z0-9]{1,20}$/.test(v.mode) ? v.mode : null;
    const k = labelKey(label);
    if (k && k.length <= 80) m.set(k, { difficulty: d, mode });
  };
  if (Array.isArray(labels)) { for (const x of labels) if (x && typeof x === 'object') add(x.label, x); }
  else if (labels && typeof labels === 'object') { for (const [k, v] of Object.entries(labels)) add(k, v); }
  return m;
}

function headCore(s) {
  let t = stripEmph(String(s).trim().replace(/^#{1,6}\s+/, '')).trim();
  if (/^\[[^[\]]{1,80}\]$/.test(t)) t = t.slice(1, -1).trim();
  const colon = /:\s*$/.test(t);
  t = t.replace(/\s*:+\s*$/, '').trim();
  return { core: t, colon };
}

// 見出しの行なら {difficulty, mode, label, note, guess, single, override}。strict=false の時だけ「コロンで終わる短い行」も見る
function parseHeading(s, labels, strict) {
  const { core, colon } = headCore(s);
  if (!core || core.length > 80) return null;
  const noParen = core.replace(/\s*\([^()]*\)\s*$/, '').trim();
  const paren = noParen !== core ? (core.slice(noParen.length).trim().replace(/^\(|\)$/g, '').trim() || null) : null;
  const hit = labels.get(labelKey(core)) || (noParen && noParen !== core ? labels.get(labelKey(noParen)) : null);
  if (hit) {
    const lab = labels.get(labelKey(core)) ? core : noParen;
    const std = stdHeading(lab);
    const parenDiff = lab === noParen && paren ? diffOf(paren) : null;
    return { difficulty: hit.difficulty, mode: hit.mode || (std && std.mode) || 'Standard', label: lab,
      note: lab === noParen && paren && !parenDiff ? paren : null, guess: false, single: false,
      override: !!(std && std.difficulty !== hit.difficulty) };
  }
  const std = stdHeading(core);
  if (std) return std;
  let m = HEAD_RE2.exec(core);
  if (m && !/^\d+(?:\.\d+)?$/.test(m[1].trim())) {
    return { difficulty: diffOf(m[3]), mode: modeOf(m[2]), label: m[1].trim(), note: null, guess: false, single: false, override: false };
  }
  if (!strict && colon && core.length <= 40) {
    m = HEAD_LOOSE.exec(core);
    if (m) return { difficulty: diffOf(m[2]), mode: modeOf(m[1]), label: null, note: null, guess: true, single: false, override: false };
  }
  return null;
}

function stdHeading(core) {
  let m = HEAD_RE1.exec(core);
  if (m) {
    return { difficulty: diffOf(m[2]), mode: modeOf(m[1]), label: null, note: m[3] != null && m[3].trim() ? m[3].trim() : null,
      guess: false, single: /^e$/i.test(m[2].trim()), override: false };
  }
  m = HEAD_RE1B.exec(core);
  if (m) return { difficulty: diffOf(m[1]), mode: modeOf(m[2]), label: null, note: null, guess: false, single: /^e$/i.test(m[1].trim()), override: false };
  return null;
}

// ファイル名（Expert.txt・Hard_1.txt・ExpertPlusStandard.txt・AT.txt＋名前の表）から難易度
function fileHeading(fileName, labels) {
  if (typeof fileName !== 'string' || !fileName) return null;
  let stem = fileName.split(/[\\/]/).pop().replace(/\.(?:txt|text|md|log)$/i, '');
  stem = stem.replace(/(?:[\s_-]*\(\d{1,3}\)|[\s_-]+\d{1,3})$/, '').trim();   // Hard_1 / Expert (1)
  if (!stem || stem.length > 80) return null;
  const hit = labels.get(labelKey(stem));
  if (hit) return { difficulty: hit.difficulty, mode: hit.mode || 'Standard', label: stem, stem };
  const h = stdHeading(stem.replace(/_+/g, ' ').trim());
  if (h && !h.note) return { difficulty: h.difficulty, mode: h.mode, label: null, stem };
  return { difficulty: null, mode: null, label: null, stem };
}

// ---------------------------------------------------------------- 1行の下ごしらえ

// 書式に関係しない制御文字・幅0の文字・向きを変える文字（表示を偽装できる）を消す。タブは空白4つ
const CTRL_RE = /[\u0000-\u0008\u000B\u000C\u000E-\u001F\u007F\u200B-\u200F\u202A-\u202E\u2060-\u2069\uFEFF]/g;
const FENCE_LANG = /^(?:txt|text|plaintext|diff|md|markdown|ini|ya?ml|json|js|javascript|py|python|css|fix|ansi|less|cs|c|cpp|lua|sh|bash|ps1|xl|ml|prolog)$/i;
const KANA_KANJI = /[\u3040-\u30FF\u3400-\u9FFF\uFF66-\uFF9F]/;

function stripDiscord(s) {
  return s
    .replace(/<a?:(\w{1,40}):\d{5,25}>/g, ':$1:')     // 自作の絵文字 <a:name:123…> → :name:
    .replace(/<(?:@[!&]?|#)\d{5,25}>/g, '')          // メンション・チャンネル
    .replace(/<t:-?\d{1,13}(?::[a-zA-Z])?>/g, '');   // 時刻の埋め込み
}

// **太字**・*斜体*・***両方***・__下線__・~~取り消し~~・`code` の記号を外す
function stripEmph(s) {
  let t = s;
  for (let k = 0; k < 3; k++) {
    const u = t.replace(/(^|[^\w*~])(\*{1,3}|_{2,3}|~~)(?=\S)(.+?)(?<=\S)\2(?![\w*~])/g, '$1$3');
    if (u === t) break;
    t = u;
  }
  return t.replace(/`([^`]{1,500})`/g, '$1');
}

// ---------------------------------------------------------------- 行頭の拍を読む

const NUM_Y = /\d{1,5}(?:\.\d+)?/y;

// i から数を1つ読む。後ろが数として終わっていなければ null（231.g・2nd・50%・1:23・1/16）
function readNum(s, i) {
  NUM_Y.lastIndex = i;
  const m = NUM_Y.exec(s);
  if (!m) return null;
  const j = i + m[0].length, c = s[j], c2 = s[j + 1];
  if (c !== undefined) {
    if (/[A-Za-z0-9_%'\u2019\u00B0]/.test(c)) return null;
    if (c === '.' && c2 !== undefined && c2 !== '.' && !/\s/.test(c2)) return null;
    if ((c === ':' || c === '/') && c2 !== undefined && /\d/.test(c2)) return null;
  }
  return { v: parseFloat(m[0]), end: j };
}

const SEV_IN = { X: 'X', '?': '?', S: 'S', N: 'N', I: 'N', Q: '?' };
const SEV_WORD = { unrankable: 'X', questionable: '?', suggestion: 'S', note: 'N', info: 'N' };

/**
 * 行（字下げ・Discord の記号を外した後）の頭の拍を読む。拍で始まらなければ null。
 * @returns {null|{spots:{a:number,b:number|null,kind?:string}[], repeats:boolean, severity:string|null, mark:string|null,
 *   text:string, ambiguous:boolean, sep:string, trailingList:boolean}}
 */
function parseHead(body) {
  const s = body;
  let i = 0, severity = null, mark = null, m;
  const skipSp = k => { while (k < s.length && (s[k] === ' ' || s[k] === '\u00A0' || s[k] === '\u3000')) k++; return k; };
  m = /^[-*\u2022\u00B7]\s+(?=\d|\[|\(|beats?\b)/i.exec(s);                 // 箇条書きの印「- 86 (and repeats) …」
  if (m) i = m[0].length;
  m = /^\(([xsniq?])\)\s*/i.exec(s.slice(i));                     // 重さの印 (X)(?)(S)(N)(I)(Q)
  if (m) { severity = SEV_IN[m[1].toUpperCase()]; mark = '(' + m[1] + ')'; i += m[0].length; }
  let bracket = false;
  if (s[i] === '[' && /\d/.test(s[skipSp(i + 1)] || '')) { bracket = true; i = skipSp(i + 1); }
  m = /^beats?\s*[:#]?\s*/i.exec(s.slice(i));                     // 「beat 27.5」「Beats: 12.5, 13」
  if (m && /\d/.test(s[i + m[0].length] || '')) i += m[0].length;
  let cur = readNum(s, i);
  if (!cur) return null;

  const spots = [];
  let repeats = false, trailingList = false;
  for (;;) {
    let j = cur.end;
    if (s[j] === '.' && s[j + 1] !== '.') j++;                     // 「12.」
    const k = skipSp(j), spaced = k > j, rest = s.slice(k);
    let b = null, kind = null, rm;
    if ((rm = /^(?:->|\u2192|>|~|\u301C|\uFF5E)\s*/.exec(rest))) { const n = readNum(s, k + rm[0].length); if (n) { b = n; kind = 'gt'; } }
    else if (spaced && (rm = /^(?:to|thru|through|till|until)\s+/i.exec(rest))) { const n = readNum(s, k + rm[0].length); if (n) { b = n; kind = 'to'; } }
    else if ((rm = /^[-\u2013\u2014\uFF0D]\s*/.exec(rest))) {
      const n = readNum(s, k + rm[0].length);
      if (n && n.v > cur.v) { b = n; kind = spaced || rm[0].length > 1 ? 'spaced' : 'dash'; }   // 後ろが大きい時だけ範囲（小さければ区切り）
    }
    if (b) {
      const a = Math.min(cur.v, b.v), z = Math.max(cur.v, b.v);
      spots.push({ a, b: z, kind });
      i = b.end;
      if (s[i] === '.' && s[i + 1] !== '.') i++;
    } else {
      spots.push({ a: cur.v, b: null });
      i = j;
    }
    // 括弧: 同じ所「119.5 (343.5)」・繰り返し「(etc.)」「(and repeats)」・「(suggestion)」
    for (;;) {
      const k2 = skipSp(i), r2 = s.slice(k2);
      let pm;
      if ((pm = /^\(\s*(?:etc\.?|and\s+repeats?|&\s*repeats?|\+\s*repeats?|repeats?|and\s+so\s+on|\.\.\.|\u2026)\s*\)/i.exec(r2))) { repeats = true; i = k2 + pm[0].length; continue; }
      if ((pm = /^\(\s*suggestion\s*\)/i.exec(r2))) { if (!severity) { severity = 'S'; mark = '(suggestion)'; } i = k2 + pm[0].length; continue; }
      if ((pm = /^\((\s*\d{1,5}(?:\.\d+)?(?:\s*(?:,|&|and)\s*\d{1,5}(?:\.\d+)?)*\s*)\)/i.exec(r2))) {
        for (const x of pm[1].split(/\s*(?:,|&|and)\s*/i)) if (x.trim()) spots.push({ a: parseFloat(x), b: null, kind: 'paren' });
        i = k2 + pm[0].length;
        continue;
      }
      break;
    }
    if (s.startsWith('...', i) || s[i] === '\u2026') { repeats = true; i += s[i] === '\u2026' ? 1 : 3; while (s[i] === '.') i++; }   // 「30...」
    const k4 = skipSp(i), r4 = s.slice(k4);
    const lm = /^(?:,\s*(?:and|&)\s+|,\s*|&\s*|and\s+)/i.exec(r4);
    if (lm) {
      const p = k4 + lm[0].length, n = readNum(s, p);
      if (n) { cur = n; continue; }
      if (s.startsWith('...', p) || s[p] === '\u2026') { repeats = true; i = p + (s[p] === '\u2026' ? 1 : 3); while (s[i] === '.') i++; }
      else if (r4[0] === ',') trailingList = true;                 // 「703.25, 707.25, repeats」
    }
    break;
  }
  if (bracket) { const k = skipSp(i); if (s[k] === ']') i = k + 1; }
  // 区切り（- – — － : | = →）。無ければ空白の後がそのまま文
  let k5 = skipSp(i);
  if (trailingList) { while (s[k5] === ',' || s[k5] === ' ') k5++; }
  const sm = /^(?:[-\u2013\u2014\uFF0D]+>?(?=\s|$|\d)|[:|=]+|\u2192)\s*/.exec(s.slice(k5));
  const sep = sm ? sm[0].trim() : '';
  let text = s.slice(k5 + (sm ? sm[0].length : 0)).trim();
  const last = spots[spots.length - 1];
  const ambiguous = !sep && !bracket && !!last && last.kind === 'spaced';   // 「186 - 188 please …」範囲とも区切りとも読める
  if ((m = /^\(\s*suggestion\s*\)\s*[:\-\u2013\u2014]?\s*/i.exec(text))) { if (!severity) { severity = 'S'; mark = '(suggestion)'; } text = text.slice(m[0].length); }
  else if (/^suggestion\b\s*[,:]/i.test(text) && !severity) { severity = 'S'; mark = 'suggestion'; }
  if (sep === '|' && (m = /^(unrankable|questionable|suggestion|note|info)\b\s*(?:[-\u2013:]\s*|$)/i.exec(text))) {   // AutoModder の BeatLeader 用の形
    if (!severity) { severity = SEV_WORD[m[1].toLowerCase()]; mark = m[1]; }
    text = text.slice(m[0].length);
  }
  return { spots, repeats, severity, mark, text, ambiguous, sep, trailingList };
}

function looksUnreadable(body) {
  return /^(?:[-*\u2022]\s+)?(?:\([xsniq?]\)\s*)?\[?\d{1,5}(?:\.\d*)?\s?[.,]?[a-z](?=$|[^\w])/i.test(body);   // 231.g・12a
}

const SAME_RE = /^(?:\^+|same\s*(?:\^+|as\s+(?:the\s+)?(?:previous|prev|above|before)(?:\s+one)?)?|\^+\s*same|similar\s+to\s+(?:the\s+)?previous(?:\s+one)?|ditto)\s*[.!]*$/i;
const UNIT_AFTER = /^\s*(?:ms\b|bpm\b|njs\b|jd\b|nps\b|fps\b|hz\b|s\b|sec\b|secs\b|seconds?\b|degrees?\b|\u00B0|%|x\b|wide\b|tall\b|lanes?\b|rows?\b|cells?\b|times?\b|stars?\b|votes?\b)/i;

// 文の中の数（拍の候補。自動では印を付けない用）。分数・時刻・単位の付いた数は除く
function hintsOf(text) {
  const out = [];
  const re = /(^|[^\w.:/])(\d{1,5}(?:\.\d+)?)(?![\w%\u00B0'\u2019]|\.\d|[:/]\d)/g;
  let m;
  while ((m = re.exec(text)) && out.length < 30) {
    if (UNIT_AFTER.test(text.slice(m.index + m[0].length, m.index + m[0].length + 10))) continue;
    const v = parseFloat(m[2]);
    if (!out.includes(v)) out.push(v);
  }
  return out;
}

const RESP_KEY = /^(?:fixed|fix\b|no\s+changes?|no\s+changed|not\s+changed|unchanged|changed|done|adjusted|kept|left\s+(?:it\s+)?as\s+is)\b/i;
function splitResponse(text) {
  const m = /^(.*\S)\s+[-\u2013\u2014\uFF0D]\s*(\S.*)$/.exec(text);   // 最後の「 - 」の後ろ
  return m ? [m[1], m[2]] : null;
}

function isNameLike(s) {
  if (s.length > 32 || /[.!?,;:]$/.test(s) || !/[A-Za-z\u00C0-\u024F\u3040-\u30ff\u3400-\u9fff]/.test(s)) return false;
  if (!/^[\w.\-\u00C0-\u024F\u3040-\u30FF\u3400-\u9FFF]{2,32}(?: [\w.\-]{1,32}){0,2}$/.test(s)) return false;
  return !/^(?:fine|ok|okay|good|great|same|none|nothing|overall|notes?|general|lgtm|n\/a|na|repeats?|thanks?|thank you)$/i.test(s);
}

function isFirstLabelLike(s) {
  return s.length <= 40 && !/[.!?,;]/.test(s) && !/^\d/.test(s) && s.split(/\s+/).length <= 5;
}

// ---------------------------------------------------------------- 読む

/**
 * 審査の指摘の文を読む。書かれた順のまま返す（拍の順に並べ替えない）。
 * @param {string} text
 * @param {{fileName?:string, labels?:Object|Array, defaultDifficulty?:string, responses?:boolean|'auto'}} [opts]
 *   labels: 難易度の名前（Info.dat の _difficultyLabel）→難易度。{ 'AT': 'ExpertPlus' } か { 'AT': {difficulty, mode} } か [{label, difficulty, mode}]
 *   responses: 行の後ろに足したマッパーの返事（` - fixed` 等）を分けるか。'auto'（既定）は ` - fixed`・` - no change` 等が3件以上ある時だけ
 * @returns {{items:ReviewItem[], notes:ReviewNote[], sections:ReviewSection[], warnings:{line:number, code:string, text:string}[],
 *   fileDifficulty:string|null, responses:boolean}}
 *
 * ReviewItem: { difficulty, mode, label, otherMode, beats:[number], ranges:[[a,b]], at, repeats, severity('X'|'?'|'S'|'N'|null), mark,
 *   text, raw, line, cont:[string], sameAsPrev, prev, parent, group, groupText, response, quoted, ambiguous, hints:[number] }
 *   - beats・ranges は書かれた順。at は最初に書かれた位置（一覧の並べ替え・飛ぶ先の目安）
 *   - parent: 字下げした拍の行（前の項目の細かい指摘）の時、その項目の添字。cont: 字下げした続きの行（拍なし）
 *   - group/groupText: 行末の「]」で2行以上をまとめる書き方（groupText は「]」の後ろの共通の文）
 *   - sameAsPrev/prev: 「^」「same」「same as previous」＝前の項目と同じ指摘。ambiguous: 「a - b 文」で範囲と読んだ（区切りかもしれない）
 *   - otherMode: Standard 以外のモード（NLM の対象外）。hints: 文の中の数（拍の候補・自動では使わない）
 * ReviewNote: { line, text, kind('comment'|'divider'|'unreadable'|'mapper'), difficulty, mode, label, after(直前の項目の添字), hints }
 */
export function parseReviewText(text, opts = {}) {
  const warnings = [];
  const warn = (line, code, t) => { if (warnings.length < 500) warnings.push({ line, code, text: String(t || '').slice(0, 120) }); };
  let src = typeof text === 'string' ? text : '';
  if (src.length > REVIEW_LIMITS.maxChars) { warn(0, 'too-large', ''); src = src.slice(0, REVIEW_LIMITS.maxChars); }
  if (src.charCodeAt(0) === 0xFEFF) src = src.slice(1);
  let rawLines = src.split(/\r\n|\r|\n/);
  if (rawLines.length > REVIEW_LIMITS.maxLines) { warn(REVIEW_LIMITS.maxLines, 'too-many-lines', ''); rawLines = rawLines.slice(0, REVIEW_LIMITS.maxLines); }
  const labels = normLabels(opts.labels);
  const defDiff = REVIEW_DIFFS.includes(opts.defaultDifficulty) ? opts.defaultDifficulty : null;
  const file = fileHeading(opts.fileName, labels);

  // 下ごしらえ: 行ごとに {raw, body, indent, quoted, skip}
  const L = rawLines.map((r0, idx) => {
    let raw = r0;
    if (raw.length > REVIEW_LIMITS.maxLineChars) { warn(idx + 1, 'line-too-long', ''); raw = raw.slice(0, REVIEW_LIMITS.maxLineChars); }
    let t = raw.replace(CTRL_RE, '').replace(/\t/g, '    ');
    let fence = false;
    if (/^\s*```/.test(t)) { t = t.replace(/^(\s*)`{3,}/, '$1'); fence = true; if (FENCE_LANG.test(t.trim())) t = ''; }
    if (/`{3,}\s*$/.test(t)) { t = t.replace(/\s*`{3,}\s*$/, ''); fence = true; }
    t = stripDiscord(t);
    const indent = (/^ */.exec(t) || [''])[0].length;
    let body = t.trim(), quoted = false;
    const qm = /^>{1,3}\s+/.exec(body);
    if (qm) { quoted = true; body = body.slice(qm[0].length).trim(); }
    body = stripEmph(body).trim();
    return { raw: raw.replace(CTRL_RE, ''), body, indent, quoted, skip: fence && !body };
  });
  let base = Infinity;
  for (const x of L) if (x.body && !x.skip) base = Math.min(base, x.indent);
  if (!Number.isFinite(base)) base = 0;

  const items = [], notes = [], sections = [];
  let sec = null;                       // 今の見出し
  let prevKind = null;                  // 直前の行の種類（'item'|'cont'|'blank'|'note'|'heading'|'divider'|'mapper'）
  let lastItem = null, lastTop = null, firstContent = true, groupId = 0, groupOpen = null;
  let fileDiffers = false, tooMany = false;
  const curDiff = () => (sec ? sec.difficulty : (file && file.difficulty) || defDiff);
  const curMode = () => (sec ? sec.mode : (file && file.difficulty && file.mode) || 'Standard');
  const curLabel = () => (sec ? sec.label : (file && file.difficulty ? file.label : null));
  const nextIdx = i => { let k = i + 1; while (k < L.length && L[k].skip) k++; return k; };
  const addNote = (line, t, kind) => {
    notes.push({ line, text: t, kind, difficulty: curDiff(), mode: curMode(), label: curLabel(), after: lastItem ? items.length - 1 : null, hints: hintsOf(t) });
  };
  const openSection = (i, h) => {
    if (h.guess) warn(i + 1, 'heading-guess', L[i].body);
    if (h.single) warn(i + 1, 'heading-e', L[i].body);
    if (h.override) warn(i + 1, 'label-override', L[i].body);
    if (h.difficulty == null) warn(i + 1, 'unknown-label', h.label || L[i].body);
    if (h.mode !== 'Standard') warn(i + 1, 'other-mode', L[i].body);
    if (!sections.length && file && file.difficulty && h.difficulty && (h.difficulty !== file.difficulty || h.mode !== file.mode)) fileDiffers = true;
    sec = { line: i + 1, difficulty: h.difficulty, mode: h.mode, label: h.label, mapper: null, note: h.note, guess: !!h.guess };
    sections.push(sec);
    lastTop = null; groupOpen = null;
    if (h.note) addNote(i + 1, h.note, 'comment');
    // 見出しの次の行が名前だけで、その次が空行（か終わり）なら担当マッパーの名前
    const n1 = nextIdx(i);
    if (n1 < L.length && L[n1].body && !L[n1].quoted && isNameLike(L[n1].body) && !parseHead(L[n1].body) && !parseHeading(L[n1].body, labels, true)) {
      const n2 = nextIdx(n1);
      if (n2 >= L.length || !L[n2].body) return n1;
    }
    return -1;
  };

  let mapperAt = -1;
  for (let i = 0; i < L.length; i++) {
    const x = L[i];
    if (x.skip) continue;
    const lineNo = i + 1, body = x.body;
    if (!body) { prevKind = 'blank'; groupOpen = null; continue; }
    if (i === mapperAt) {
      sec.mapper = body;
      notes.push({ line: lineNo, text: body, kind: 'mapper', difficulty: sec.difficulty, mode: sec.mode, label: sec.label, after: null, hints: [] });
      prevKind = 'mapper'; firstContent = false; continue;
    }
    // 区切りの線「-----」「--- first drop repeats ---」「-- repeated part no listed --」
    const dm = /^[-=_~]{2,}\s*(.*?)\s*[-=_~]*$/.exec(body);
    if (dm && !/^-\s*\d/.test(body)) {
      const dh = dm[1] && !x.quoted ? parseHeading(dm[1], labels, true) : null;   // 「== Hard ==」「--- Expert+ ---」
      if (dh) { mapperAt = openSection(i, dh); prevKind = 'heading'; firstContent = false; lastItem = null; continue; }
      if (dm[1]) addNote(lineNo, dm[1], 'divider');
      prevKind = 'divider'; groupOpen = null; continue;
    }
    const rel = x.indent - base;
    // 見出しの行（その語だけ）
    let h = !x.quoted && rel <= 1 ? parseHeading(body, labels, true) : null;
    if (h) { mapperAt = openSection(i, h); prevKind = 'heading'; firstContent = false; lastItem = null; continue; }
    const hd = parseHead(body);
    if (hd) {
      if (items.length >= REVIEW_LIMITS.maxItems) { if (!tooMany) warn(lineNo, 'too-many-items', ''); tooMany = true; continue; }
      firstContent = false;
      let t = hd.text, gText = null, inGroup = false;
      const gm = t.includes(']') && !t.includes('[') ? /^(.*?)\s+\](?:\s+(.*))?$/.exec(' ' + t) : null;   // 行末の「]」でまとめる書き方
      if (gm) { inGroup = true; t = gm[1].trim(); gText = gm[2] ? gm[2].trim() : null; }
      let response = null;
      const rm = /\s--\s*response:\s*(.*)$/i.exec(t);   // AutoModder の BeatLeader 用の形の返事
      if (rm) { response = rm[1].trim() || null; t = t.slice(0, rm.index).trim(); }
      const beats = [], ranges = [];
      for (const p of hd.spots) { if (p.b == null) beats.push(p.a); else ranges.push([p.a, p.b]); }
      const it = {
        difficulty: curDiff(), mode: curMode(), label: curLabel(), otherMode: curMode() !== 'Standard',
        beats, ranges, at: hd.spots[0].a, repeats: hd.repeats || (/^(?:etc\b|repeats?\b)/i.test(t) && (!hd.sep || hd.trailingList)),
        severity: hd.severity, mark: hd.mark, text: t, raw: x.raw, line: lineNo, cont: [],
        sameAsPrev: SAME_RE.test(t), prev: null, parent: null, group: null, groupText: null,
        response, quoted: x.quoted, ambiguous: hd.ambiguous, hints: hintsOf(t),
      };
      if (lastTop && rel > lastTop.rel + 1) it.parent = lastTop.idx;   // 字下げした拍の行＝前の項目の細かい指摘
      if (inGroup) {
        if (groupOpen == null || prevKind !== 'item') groupOpen = ++groupId;
        it.group = groupOpen;
        if (gText) {
          for (const o of items) if (o.group === groupOpen) o.groupText = o.groupText ? o.groupText + ' ' + gText : gText;
          it.groupText = items.find(o => o.group === groupOpen)?.groupText || gText;
        } else {
          it.groupText = items.find(o => o.group === groupOpen)?.groupText || null;
        }
      } else groupOpen = null;
      items.push(it);
      lastItem = it;
      if (it.parent == null) lastTop = { idx: items.length - 1, rel };
      lastItem._rel = rel;
      prevKind = 'item';
      continue;
    }
    // ここから拍の無い行
    if (firstContent && !x.quoted && isFirstLabelLike(body)) {
      // 1行目が難易度の名前（AT・IN・HD・EZ 等）: ファイル名と同じか、次の行が名前で、その次が空行
      const core = headCore(body).core;
      const n1 = nextIdx(i), n2 = nextIdx(n1);
      const byFile = file && file.stem && labelKey(file.stem) === labelKey(core);
      const byName = n1 < L.length && L[n1].body && isNameLike(L[n1].body) && !parseHead(L[n1].body) && !parseHeading(L[n1].body, labels, true)
        && (n2 >= L.length || !L[n2].body);
      if (byFile || byName) {
        const lab = labels.get(labelKey(core));
        mapperAt = openSection(i, { difficulty: lab ? lab.difficulty : (file && byFile ? file.difficulty : null), mode: (lab && lab.mode) || 'Standard',
          label: core, note: null, guess: false, single: false, override: false });
        prevKind = 'heading'; firstContent = false; lastItem = null; continue;
      }
    }
    firstContent = false;
    h = !x.quoted && rel <= 1 ? parseHeading(body, labels, false) : null;
    if (h) { mapperAt = openSection(i, h); prevKind = 'heading'; lastItem = null; continue; }
    if (lastItem && (prevKind === 'item' || prevKind === 'cont')) {
      if (rel > lastItem._rel + 1) { lastItem.cont.push(body); prevKind = 'cont'; continue; }   // 字下げした続きの行
      if (prevKind === 'item' && lastItem.quoted && !x.quoted) {                                 // 引用した指摘への返事
        lastItem.response = lastItem.response ? lastItem.response + ' ' + body : body; prevKind = 'cont'; continue;
      }
      if (prevKind === 'item' && !lastItem.text) { lastItem.text = body; lastItem.hints = hintsOf(body); lastItem.sameAsPrev = SAME_RE.test(body); prevKind = 'cont'; continue; }
      if (KANA_KANJI.test(body) && !/[a-z]{4,}/i.test(body)) { lastItem.cont.push(body); prevKind = 'cont'; continue; }   // 日本語の訳の行
    }
    if (looksUnreadable(body)) { warn(lineNo, 'unreadable', body); addNote(lineNo, body, 'unreadable'); }
    else addNote(lineNo, body, 'comment');
    prevKind = 'note';
  }
  if (fileDiffers) warn(sections[0].line, 'file-name-differs', opts.fileName);

  // マッパーが審査の行の後ろに足した返事（` - fixed`・` - No change`・` - changed to 226-227`）
  let resp = opts.responses === true;
  if (opts.responses !== true && opts.responses !== false) {
    let n = 0;
    for (const it of items) { const sp = splitResponse(it.text); if (sp && RESP_KEY.test(sp[1])) n++; }
    resp = n >= 3 && n >= items.length * 0.15;
  }
  if (resp) {
    for (const it of items) {
      if (it.response) continue;
      const sp = splitResponse(it.text);
      if (sp) { it.text = sp[0]; it.response = sp[1]; }
      else { const fm = /^(.*\S)\s+(fixed)\s*[.!]?$/i.exec(it.text); if (fm) { it.text = fm[1]; it.response = fm[2]; } }
      it.hints = hintsOf(it.text);
      it.sameAsPrev = SAME_RE.test(it.text);
    }
  }
  // 「^」「same」の指す前の項目（同じ見出しの中の直前の項目）
  items.forEach((it, k) => {
    delete it._rel;
    it.prev = null;
    if (!it.sameAsPrev) return;
    for (let p = k - 1; p >= 0; p--) {
      const o = items[p];
      if (o.difficulty === it.difficulty && o.mode === it.mode && o.label === it.label) { it.prev = p; break; }
    }
  });
  return { items, notes, sections, warnings, fileDifficulty: file ? file.difficulty : null, responses: resp };
}

// ---------------------------------------------------------------- 書き出す

const DIFF_OUT = { ExpertPlus: 'Expert+', Expert: 'Expert', Hard: 'Hard', Normal: 'Normal', Easy: 'Easy' };
const SEV_OUT = { X: 'X', '?': '?', S: 'S', N: 'N' };

/** 拍を書く形にする（小数3桁まで。1/16 拍のように4桁でちょうど表せる物は4桁）。読めない値は '' */
export function formatBeat(v) {
  const n = typeof v === 'number' ? v : typeof v === 'string' && v.trim() !== '' ? Number(v) : NaN;
  if (!Number.isFinite(n) || n < 0 || n > 99999) return '';
  const r3 = Math.round(n * 1000) / 1000, r4 = Math.round(n * 10000) / 10000;
  const out = Math.abs(r3 - n) < 1e-9 ? r3 : Math.abs(r4 - n) < 1e-9 ? r4 : r3;
  let s = String(out);
  if (/e/i.test(s)) s = out.toFixed(4).replace(/\.?0+$/, '');
  return s;
}

const oneLine = s => String(s == null ? '' : s).replace(CTRL_RE, '').replace(/\s*[\r\n]+\s*/g, ' ').trim().slice(0, REVIEW_LIMITS.maxLineChars);

function headingText(d, mode, label, useLabels) {
  const dn = DIFF_OUT[d] || d;
  const mn = mode && mode !== 'Standard' ? mode : '';
  const b = (mn ? mn + ' ' : '') + dn;
  return useLabels && label ? `${oneLine(label)} (${b})` : b;
}

// 読み直した時に拍・見出しの行と間違えられない形にする（前書き・全体への意見の行）
function safeNoteLine(t) {
  const s = oneLine(t);
  return parseHead(stripEmph(s)) || parseHeading(s, new Map(), false) ? 'Note: ' + s : s;
}

/**
 * NLM の結果・読んだ指摘を、実物と同じ手書きの形にする（難易度の見出しの行＋`拍, 拍 - 文`）。
 * 難易度ごとに、最初に出た順でまとめる（難易度の無い項目は先頭・見出しなし）。項目の中の順はそのまま。
 * @param {Array} items parseReviewText の items と同じ形（beats・ranges・text・difficulty・mode・severity・repeats・cont・response…）
 * @param {{severity?:boolean|'keep', responses?:boolean, eol?:string, header?:string|string[], notes?:Array, useLabels?:boolean, finalNewline?:boolean}} [opts]
 *   severity: 行頭に重さの印（(X)(?)(S)(N)。印の無い項目は (N)＝AutoModder が前の行の重さを引き継がないように）。
 *     'keep' は印のある項目にだけ付ける（読んだ指摘に返事を付けて返す時＝審査の人が書いたとおり・2026-10-27）
 *   responses: 返事を各行の後ろに ` - 返事` で足す。header: 先頭の行（数を入れない＝AutoModder が拍として読む）
 *   notes: 全体への意見 [{text, difficulty?, mode?, kind?}]（その難易度の見出しの直後に書く）。useLabels: 見出しを「名前 (Expert+)」にする
 *   eol: 既定 '\r\n'（メモ帳と同じ）。finalNewline: 最後に改行を付けるか（既定 false＝実物の多く）
 * @returns {string}
 */
export function formatReviewText(items, opts = {}) {
  const eol = opts.eol === '\n' ? '\n' : '\r\n';
  const sev = opts.severity === 'keep' ? 'keep' : !!opts.severity, resp = !!opts.responses, useLabels = !!opts.useLabels;
  const list = Array.isArray(items) ? items.filter(x => x && typeof x === 'object') : [];
  const groups = new Map([['', { d: null, mode: null, label: null, items: [], notes: [] }]]);
  const keyOf = o => (REVIEW_DIFFS.includes(o.difficulty) ? `${o.mode || 'Standard'}|${o.difficulty}|${useLabels ? o.label || '' : ''}` : '');
  const groupOf = o => {
    const k = keyOf(o);
    if (!groups.has(k)) groups.set(k, { d: o.difficulty, mode: o.mode || 'Standard', label: o.label || null, items: [], notes: [] });
    return groups.get(k);
  };
  for (const n of Array.isArray(opts.notes) ? opts.notes : []) if (n && typeof n === 'object' && oneLine(n.text)) groupOf(n).notes.push(n);
  for (const it of list) groupOf(it).items.push(it);
  const out = [];
  for (const h of opts.header == null ? [] : [].concat(opts.header)) out.push(safeNoteLine(h));
  if (out.length) out.push('');
  for (const [k, g] of groups) {
    if (!g.items.length && !g.notes.length) continue;
    if (out.length && out[out.length - 1] !== '') out.push('');
    if (k) out.push(headingText(g.d, g.mode, g.label, useLabels));
    for (const n of g.notes) out.push(n.kind === 'divider' ? `--- ${oneLine(n.text)} ---` : safeNoteLine(n.text));
    if (g.notes.length && g.items.length) out.push('');
    g.items.forEach((it, idx) => {
      const spots = [];
      for (const b of Array.isArray(it.beats) ? it.beats : []) { const s = formatBeat(b); if (s) spots.push(s); }
      for (const r of Array.isArray(it.ranges) ? it.ranges : []) {
        if (!Array.isArray(r)) continue;
        const a = Math.min(Number(r[0]), Number(r[1])), z = Math.max(Number(r[0]), Number(r[1]));
        const sa = formatBeat(a), sz = formatBeat(z);
        if (sa && sz) spots.push(sa === sz ? sa : `${sa}-${sz}`);
      }
      if (!spots.length) return;   // 拍の無い項目は書かない（notes で渡す）
      const ind = it.parent != null ? '    ' : '';
      const mark = sev === 'keep' ? (SEV_OUT[it.severity] ? `(${SEV_OUT[it.severity]}) ` : '') : sev ? `(${SEV_OUT[it.severity] || 'N'}) ` : '';
      let s = ind + mark + spots.join(', ') + (it.repeats ? '...' : '');
      let text = oneLine(it.text);
      if (!text.includes('[')) text = text.replace(/\s+\](?=\s|$)/g, ']');   // 読み直した時に「]」のまとめと読まれないように
      if (resp && oneLine(it.response)) text = (text ? text + ' - ' : '') + oneLine(it.response);
      if (it.group != null) {
        const nx = g.items[idx + 1];
        const lastOfGroup = !nx || nx.group !== it.group;
        text += '  ]' + (lastOfGroup && oneLine(it.groupText) ? ' ' + oneLine(it.groupText) : '');
      }
      if (text) s += (/^[\d.]/.test(text) ? ': ' : ' - ') + text;   // 文が数で始まる時は「:」（「 - 12」は範囲と読まれる）
      out.push(s);
      for (const c of Array.isArray(it.cont) ? it.cont : []) if (oneLine(c)) out.push(ind + '    ' + oneLine(c));
    });
  }
  while (out.length && out[out.length - 1] === '') out.pop();
  return out.join(eol) + (opts.finalNewline && out.length ? eol : '');
}

// 曲の解析（テンポの推定・構成の解析）の画面側（2026-10-19）。解析そのものは serve.py の /__analysis/*（Python）。
//
// 流れ（ボタン1つ「曲を解析」）: 音源を送る(upload) → テンポを推定(tempo) → 今の BPM・無音追加と違えば適用するかを聞く
// （候補B＝半拍ずらしも選べる・適用しないも選べる。自動では変えない）→ 今の目盛りで構成を解析(structure) → 解析の帯に出す。
// 1曲 30秒〜1分かかるので、その間も編集できる（帯に進み具合と［やめる］）。
//
// 帯はスペクトログラムの箱（#specPane）の上の段（#anaPane）。結果がある時と解析中だけ出し、その間スペクトログラムは下へ詰める
// （NLE のレーンの高さは変えない＝1600×980 でもレーンにスクロールが出ない）。帯は曲ごと＝全難易度共通。
// 上の段＝セクション（「Aメロ S3」＝名前＋番号。同じ番号＝同じ中身・同じ色。★＝サビの候補）、下の段＝細かい区切り（A/B/C…）。
// クリック＝その頭へ移動・ダブルクリック＝番号ごとに名前を付け直す（同じ番号のセクション全部）・右クリック＝メニュー。
//
// 保存（save/load。editor-app.js がプロジェクトの analysis に入れる・projSig にも入る＝名前の付け直しで未保存のランプが点く）:
//   {v:1, tempo:テンポの結果, structure:{sub,sections,segments,chorus}, names:{番号:付け直した名前}, grid:解析した時の目盛り,
//    made:true＝この結果からクリップを作った（溝の［クリップを作る］を暗くする。作っていなければキーごと無し）}
//   セクションには解析した時の「元の音源の秒」(a0/a1) も入れる（解析し直した時に、付け直した名前を同じ位置の番号へ引き継ぐため）。
// 目盛り（grid＝BPM・無音追加・テンポパート・Music の配置・音源の名前。editor-app.js の anaGrid）が解析した時と違えば
// 帯を薄くして「目盛りが変わりました。解析し直してください」と出す。
// サーバー・ファイル由来の文字列（名前・番号・エラーの種類）は textContent とキャンバスの fillText にだけ使う（innerHTML に入れない）。
//
// 曲を取り込んだ時の「曲を解析しますか？」（2026-10-20）: editor-app.js が利用者の操作で新しく曲を取り込んだ時だけ songLoaded() を呼ぶ
// （プロジェクトを開いた時の自動読込・再接続・ドラッグ中の波形の先読みでは呼ばない）。ここで聞くかを決める: 環境設定 bsnm_anaAsk='0'（キーが無い＝聞く）・
// この起動で解析を使えないと分かった（no-api・unavailable）・解析中・この曲の結果がある（目盛りが今と同じ）なら聞かない。他の画面（未保存の確認など）が
// 出ていれば閉じるのを待って出す。急に出る画面なので Enter では押さない（テンポの確認と同じ）。Esc＝今はしない。

export const ANA_SUB = 4;          // at（拍→元の音源の秒）の細かさ（1拍を4つ）
const POLL_MS = 500;               // 進み具合を聞く間隔
const ASK_KEY = 'bsnm_anaAsk';     // 曲を取り込んだ時に解析するか聞く（'0'＝聞かない。キーが無い＝聞く）
const ASK_POLL_MS = 400, ASK_WAIT_MAX = 10 * 60 * 1000;   // 他の画面が閉じるのを待つ間隔・最長（それを過ぎたら聞かない）
// 「曲を解析しますか？」の本文の箇条（解析すると何ができるか）
const ASK_POINTS = [
  ['p1', 'BPM と無音追加（曲の頭のずれ）を推定して提案します（今の設定と違う時だけ確認が出ます。自動では変えません）'],
  ['p2', '曲の構成（イントロ・Aメロ・サビ…と細かい区切り）を NLE の帯で表示します（クリックでその位置へ・名前の付け直し・マーカーへ書き出し）'],
  ['p3', '構成から空のクリップをまとめて作れます（同じくり返しは自動でリンク＝1回目のサビを打てば2回目以降にも入ります）'],
  ['p4', '1曲 30秒〜1分。解析中も編集できます。解析は PC の中で行い、曲をネットへ送りません'],
];
const lsGet = k => { try { return localStorage.getItem(k); } catch (_) { return null; } };
const lsSet = (k, v) => { try { localStorage.setItem(k, v); } catch (_) {} };
const GUT = 128;                   // 左の溝（NLE・Music と同じ TLGUT）
const SEC_Y = [3, 21];             // セクションの段（キャンバスの y の範囲）
const SEG_Y = [24, 37];            // 細かい区切りの段
const MAX_ITEMS = 4000;            // ファイル由来の配列の上限
const NAME_MAX = 40;
// 番号（セクション）の色＝報告ページ（tools/analyze_structure.py）と同じ落ち着いた色／細かい区切りのグループの色
const SPAL = ['#5b6c8f', '#8f6b5b', '#5b8f78', '#8a5b8f', '#8f875b', '#5b858f', '#8f5b6e', '#6e8f5b', '#6b5b8f', '#8f7a5b'];
const PAL = ['#e4572e', '#4c9be8', '#f2b134', '#3fb37f', '#a66fd6', '#ef7fb1', '#58c4c4', '#9b8b6e', '#7d8cf0', '#c4c94a', '#d9883b', '#5fa35a'];
// 解析が付ける仮の名前（Python の name_sections は日本語で返す）→ 訳のキー（英語の画面では訳して出す）
const AUTO_NAMES = { 'イントロ': 'intro', 'Aメロ': 'verseA', 'Bメロ': 'verseB', 'サビ': 'chorus', '間奏': 'interlude', 'Cメロ': 'bridge', 'アウトロ': 'outro' };
const ERR_JA = {
  'no-api': 'この版では解析を使えません',
  'no-audio': '先に曲を読み込んでください',
  'no-file': '音源のファイルが見つかりません（曲を読み込み直してください）',
  'too-large': '音源のファイルが大きすぎて解析できません',
  'bad-audio': '音源を読み込めませんでした（壊れているか、対応していない形式です）',
  'unknown-job': '解析の作業が見つかりません（アプリを起動し直した等）。もう一度［曲を解析］を押してください',
  'busy': '別の解析が実行中です。終わってからもう一度押してください',
  'network': '解析のサーバーに接続できませんでした',
  'too-short': "曲が短すぎて解析できません",
  'ffmpeg-not-found': "この形式の音源の解析には ffmpeg が要ります。\"winget install Gyan.FFmpeg\" でインストールし、NLMを起動し直してから、もう一度［曲を解析］を押してください",
  'unknown-audio': "解析用に預けた音源が見つかりません（片付けられた等）。もう一度［曲を解析］を押してください",
  'unavailable': "この版では解析を使えません（解析の部品を読み込めませんでした）",
  'failed': '曲の解析に失敗しました',
};

const num = x => typeof x === 'number' && isFinite(x);
const str = (x, n) => (typeof x === 'string' ? x.slice(0, n) : '');
const fmtN = (x, d = 3) => String(+(+x).toFixed(d));
const mmss = s => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, '0')}`;
const sleep = ms => new Promise(r => setTimeout(r, ms));
const anaErr = code => ({ anaCode: code });
const CANCELLED = { cancelled: true };

// ---- 受け取った結果・ファイルの中身を、知っている項目だけ・正しい形だけにする（知らない項目が増えても壊れない） ----
function cleanTempo(r) {
  if (!r || typeof r !== 'object' || !num(r.bpm) || r.bpm <= 0) return null;
  const o = { bpm: r.bpm, lead_ms: num(r.lead_ms) ? r.lead_ms : 0 };
  for (const k of ['raw_bpm', 'alt_lead_ms', 'offbeat_ratio', 'drift_pct', 'block_mad_ms', 'n_beats', 'family', 'slope', 'resid_mad_ms']) if (num(r[k])) o[k] = r[k];
  o.low_offbeat = !!r.low_offbeat;
  o.slope_sig = !!r.slope_sig;
  o.steps = (Array.isArray(r.steps) ? r.steps : []).filter(s => s && num(s.sec) && num(s.ms)).slice(0, 50).map(s => ({ sec: s.sec, ms: s.ms }));
  o.drift = (Array.isArray(r.drift) ? r.drift : []).filter(d => Array.isArray(d) && num(d[0]) && num(d[1])).slice(0, 400).map(d => [d[0], d[1]]);
  o.alt = (r.alt && num(r.alt.bpm) && num(r.alt.ratio)) ? { bpm: r.alt.bpm, ratio: r.alt.ratio } : null;
  if (r.error) o.error = true;   // 打点が少なすぎる等（Python の文は日本語なので出さない。種類だけ持つ）
  return o;
}
function cleanStructure(r) {
  if (!r || typeof r !== 'object') return null;
  const sections = (Array.isArray(r.sections) ? r.sections : []).filter(s => s && num(s.start) && num(s.end) && s.end > s.start).slice(0, MAX_ITEMS)
    .map(s => {
      const o = { start: s.start, end: s.end, label: str(s.label, 12) || '?', count: num(s.count) ? s.count : 1, chorus: !!s.chorus, name: str(s.name, NAME_MAX) };
      if (num(s.a0)) o.a0 = s.a0;
      if (num(s.a1)) o.a1 = s.a1;
      return o;
    }).sort((a, b) => a.start - b.start);
  const segments = (Array.isArray(r.segments) ? r.segments : []).filter(s => s && num(s.start) && num(s.end) && s.end > s.start).slice(0, MAX_ITEMS)
    .map(s => ({ start: s.start, end: s.end, group: str(s.group, 8) || '?', count: num(s.count) ? s.count : 1,
      best: num(s.best) ? s.best : null, sim: num(s.sim) ? s.sim : null })).sort((a, b) => a.start - b.start);
  if (!sections.length && !segments.length) return null;
  const chorus = (Array.isArray(r.chorus) ? r.chorus : []).filter(x => typeof x === 'string').slice(0, 64).map(x => x.slice(0, 8));
  return { sub: num(r.sub) ? r.sub : ANA_SUB, sections, segments, chorus };
}
function cleanGrid(g) {
  if (!g || typeof g !== 'object' || !num(g.bpm) || !num(g.leadMs)) return null;
  const pairs = (a, n) => (Array.isArray(a) ? a : []).filter(p => Array.isArray(p) && p.length === n && p.every(num)).slice(0, MAX_ITEMS).map(p => p.slice());
  return { bpm: g.bpm, leadMs: g.leadMs, tp: pairs(g.tp, 2), mb: num(g.mb) ? g.mb : 0, ms: Array.isArray(g.ms) ? pairs(g.ms, 3) : null, song: str(g.song, 300) };
}
function cleanNames(n, st) {
  const out = {};
  if (!n || typeof n !== 'object' || !st) return out;
  const labels = new Set(st.sections.map(s => s.label));
  for (const k of Object.keys(n)) if (labels.has(k) && typeof n[k] === 'string' && n[k].trim()) out[k] = n[k].slice(0, NAME_MAX);
  return out;
}
/** 拍 b → 元の音源の秒（at の中で一番近い音のある所。無ければ null） */
function atSec(at, sub, b, dir) {
  if (!Array.isArray(at) || !at.length) return null;
  let k = Math.max(0, Math.min(at.length - 1, Math.round(b * sub)));
  for (let i = k; i >= 0 && i < at.length; i += dir) if (num(at[i])) return at[i];
  for (let i = k; i >= 0 && i < at.length; i -= dir) if (num(at[i])) return at[i];
  return null;
}

export function installSongAnalysis(D) {
  const { t, tf } = D;
  const spec = document.getElementById('specPane'), pane = document.getElementById('anaPane'), cv = document.getElementById('anacv');
  const startBtn = document.getElementById('anaStartBtn'), menuBtn = document.getElementById('anaMenuBtn'), msgEl = document.getElementById('anaMsg');
  const askChk = document.getElementById('anaAskOn');   // 環境設定（アプリケーション設定）の「曲を読み込んだ時に、解析するか聞く」
  if (!spec || !pane || !cv) return null;
  const g = cv.getContext('2d');
  let W = 0, H = 0;
  // data=保存する結果（null=無し） / run=解析中の状態 / win=最後に描いた表示窓 / hover=マウスの下 / dlg=テンポの確認画面
  // ask=「曲を解析しますか？」の画面 / askWait=他の画面が閉じるのを待ち始めた時刻（0=待っていない）/ apiOff=この起動で解析を使えないと分かった
  const S = { data: null, run: null, win: { b0: 0, span: 32 }, hover: null, shown: null, startShown: null, msgKey: '', dlg: null, staleNow: false, tip: '',
    ask: null, askWait: 0, askT: null, apiOff: false };

  function resize() {
    const r = cv.getBoundingClientRect(), dpr = devicePixelRatio || 1;
    W = r.width; H = r.height;
    cv.width = Math.max(1, Math.round(W * dpr)); cv.height = Math.max(1, Math.round(H * dpr));
    g.setTransform(dpr, 0, 0, dpr, 0, 0);
  }
  try { new ResizeObserver(() => resize()).observe(pane); } catch (_) {}   // キャンバスの画素数だけを変える（見ている要素の大きさは変えない）

  const structure = () => (S.data && S.data.structure) || null;
  // ---- 名前・色 ----
  function autoName(s) { const k = AUTO_NAMES[s.name]; return k ? t('ana.nm.' + k, s.name) : (s.name || ''); }
  function dispName(s) { const u = S.data && S.data.names && S.data.names[s.label]; return (typeof u === 'string') ? u : autoName(s); }
  function secTexts(s) { const n = dispName(s); return [(n ? n + ' ' : '') + s.label + (s.chorus ? '★' : ''), n || s.label, s.label]; }
  function colorOf(list, key, pal) { const i = list.indexOf(key); return pal[(i < 0 ? 0 : i) % pal.length]; }
  const secOrder = () => { const st = structure(); return st ? [...new Set(st.sections.map(s => s.label))] : []; };
  const segOrder = () => { const st = structure(); return st ? [...new Set(st.segments.map(s => s.group))] : []; };

  // ---- 目盛り（解析した時と今） ----
  function isStale() { const d = S.data; if (!d || !d.grid || !d.structure) return false; return JSON.stringify(d.grid) !== JSON.stringify(D.grid()); }

  // ---- 通信（すべて POST・X-NLM-Request。合言葉は settings-mirror.js が自動で付ける） ----
  async function post(act, body, raw) {
    let r;
    try {
      r = await fetch('__analysis/' + act, { method: 'POST',
        headers: raw ? { 'X-NLM-Request': '1', 'Content-Type': 'application/octet-stream' } : { 'X-NLM-Request': '1', 'Content-Type': 'application/json' },
        body: raw ? body : JSON.stringify(body || {}) });
    } catch (_) { throw anaErr('network'); }
    let j = null;
    try { j = await r.json(); } catch (_) {}
    const code = j && typeof j.error === 'string' && /^[\w-]{1,40}$/.test(j.error) ? j.error : '';
    if (r.status === 404 && (!code || code === 'unknown' || !j || j.error === 'unknown endpoint')) throw anaErr('no-api');   // この版のサーバーに解析の API が無い
    if (!j || !j.ok) throw anaErr(code || (r.ok ? 'failed' : 'http-' + r.status));
    return j;
  }
  function errText(e) {
    const code = (e && e.anaCode) || 'failed';
    if (ERR_JA[code]) return t('ana.err.' + code, ERR_JA[code]);
    return tf('ana.err.other', '曲の解析に失敗しました（{code}）', { code });
  }
  async function startJob(run, act, body) {
    const j = await post(act, body);
    const job = String(j.job || '');
    if (!job) throw anaErr('failed');
    run.job = job;
    if (run.cancelled) { post('cancel', { job }).catch(() => {}); throw CANCELLED; }   // 頼んでいる間にやめた
    return job;
  }
  async function poll(run, job) {
    for (;;) {
      await sleep(POLL_MS);
      if (run.cancelled) throw CANCELLED;
      const s = await post('status', { job });
      if (run.cancelled) throw CANCELLED;
      if (num(s.progress)) run.progress = Math.max(0, Math.min(1, s.progress));
      if (s.state === 'done') { run.job = null; return s.result; }
      if (s.state === 'error') { run.job = null; throw anaErr(typeof s.error === 'string' && /^[\w-]{1,40}$/.test(s.error) ? s.error : 'failed'); }
    }
  }

  // ---- 曲を解析（ボタン1つ） ----
  async function start() {
    if (S.run) { D.stat(t('ana.busy', '曲を解析しています（やめる時は帯の［やめる］）')); return; }
    if (!D.hasAudio()) { D.showErr(errText(anaErr('no-audio'))); return; }
    const run = S.run = { stage: 'upload', progress: 0, job: null, cancelled: false };
    try {
      const f = await D.songFile();
      if (run.cancelled) return;
      if (!f) throw anaErr('no-file');
      const buf = await f.arrayBuffer();
      if (run.cancelled) return;
      let ext = (String(f.name || '').match(/\.([A-Za-z0-9]{1,8})$/) || [, 'bin'])[1].toLowerCase();
      if (ext === 'egg') ext = 'ogg';   // song.egg は中身が OGG
      const up = await post('upload?ext=' + encodeURIComponent(ext), buf, true);
      if (run.cancelled) return;
      const audioId = String(up.audioId || '');
      if (!/^[0-9a-zA-Z]{8,128}$/.test(audioId)) throw anaErr('failed');
      // テンポ
      run.stage = 'tempo'; run.progress = 0;
      const tempo = cleanTempo(await poll(run, await startJob(run, 'tempo', { audioId })));
      run.stage = 'decide'; run.progress = 0;
      await decideTempo(run, tempo);
      if (run.cancelled) return;
      // 構成（今の目盛りで。at＝NLM の拍 0, 0.25, 0.5 … ごとの元の音源の秒）
      run.stage = 'structure'; run.progress = 0;
      const grid = D.grid(), at = D.atGrid(ANA_SUB);
      const res = await poll(run, await startJob(run, 'structure', { audioId, grid: { bpm: grid.bpm, leadMs: grid.leadMs, sub: ANA_SUB, at } }));
      const st = cleanStructure(res);
      if (!st) throw anaErr('failed');
      for (const s of st.sections) {   // 解析した時の元の音源の秒（名前の引き継ぎ用）
        const a0 = atSec(at, ANA_SUB, s.start, 1), a1 = atSec(at, ANA_SUB, s.end, -1);
        if (a0 != null) s.a0 = a0; if (a1 != null) s.a1 = a1;
      }
      D.snapshot();   // 帯が出る（置き換わる）のも Ctrl+Z で戻せる
      const prev = S.data;
      S.data = { v: 1, tempo, structure: st, names: carryNames(prev, st), grid: cleanGrid(grid) };
      D.dirty();
      D.showOk(tf('ana.done', '曲の構成を解析しました（セクション {s}・細かい区切り {g}）', { s: st.sections.length, g: st.segments.length }));
      setTimeout(guideAfterAnalysis, 0);   // 次にやることの案内（下の finally で解析中を外した後に判断する）
    } catch (e) {
      if (e && (e.anaCode === 'no-api' || e.anaCode === 'unavailable')) S.apiOff = true;   // この起動では曲を取り込んでも解析するか聞かない
      if (!run.cancelled && e !== CANCELLED) { console.warn('曲の解析:', e); D.showErr(errText(e)); }
    } finally {
      if (S.run === run) S.run = null;
      if (S.dlg && S.dlg.run === run) S.dlg.close('none');
    }
  }
  function cancel(quiet) {
    const run = S.run; if (!run) return;
    run.cancelled = true; S.run = null;
    if (run.job) post('cancel', { job: run.job }).catch(() => {});
    if (S.dlg && S.dlg.run === run) S.dlg.close('none');
    if (!quiet) D.stat(t('ana.cancelled', '曲の解析をやめました'));
  }
  // 解析し直した時は帯だけ置き換え、付け直した名前は同じ位置（元の音源の秒。無ければ拍）の番号へできる範囲で引き継ぐ
  function carryNames(prev, st) {
    const out = {};
    const old = prev && prev.structure, names = prev && prev.names;
    if (!old || !names || !Object.keys(names).length) return out;
    const useSec = old.sections.every(s => num(s.a0) && num(s.a1)) && st.sections.every(s => num(s.a0) && num(s.a1));
    const span = s => useSec ? [s.a0, s.a1] : [s.start, s.end];
    const tot = (list, lab) => list.filter(s => s.label === lab).reduce((m, s) => { const [a, b] = span(s); return m + Math.max(0, b - a); }, 0);
    const pairs = [];
    for (const lab of Object.keys(names)) {
      const ov = {};
      for (const o of old.sections) if (o.label === lab) for (const n of st.sections) {
        const [a0, a1] = span(o), [b0, b1] = span(n), v = Math.min(a1, b1) - Math.max(a0, b0);
        if (v > 0) ov[n.label] = (ov[n.label] || 0) + v;
      }
      for (const nl in ov) pairs.push({ lab, nl, v: ov[nl], need: 0.5 * Math.min(tot(old.sections, lab), tot(st.sections, nl)) });
    }
    pairs.sort((a, b) => b.v - a.v);
    const usedOld = new Set();
    for (const p of pairs) if (p.v >= p.need && !usedOld.has(p.lab) && !(p.nl in out)) { out[p.nl] = names[p.lab]; usedOld.add(p.lab); }
    return out;
  }

  // ---- テンポの結果: 今の値と比べる・確認の画面 ----
  function compare(tp) {
    const cur = D.grid();
    const sameBpm = Math.abs(tp.bpm - cur.bpm) < 0.005;
    const a = Math.round(tp.lead_ms), b = num(tp.alt_lead_ms) ? Math.round(tp.alt_lead_ms) : null;
    const isA = sameBpm && Math.abs(cur.leadMs - a) <= 1, isB = sameBpm && b != null && Math.abs(cur.leadMs - b) <= 1;
    // 同じ拍の流れ: BPM が同じ・2倍・半分で、無音追加の差が短い方の拍の長さの整数倍
    const ratio = cur.bpm / tp.bpm, oct = [1, 2, 0.5].some(k => Math.abs(ratio - k) < 0.005 * k);
    const per = 60000 / Math.max(cur.bpm, tp.bpm), d = ((cur.leadMs - tp.lead_ms) % per + per) % per;
    const flow = oct && Math.min(d, per - d) <= 2;
    return { cur, a, b, isA, isB, flow };
  }
  async function decideTempo(run, tp) {
    if (!tp || tp.error) { D.stat(t('ana.tempoFew', '強い打点が少なすぎるため、テンポを推定できませんでした。今の BPM・無音追加のまま構成を解析します')); return; }
    const c = compare(tp);
    if (c.isA || c.isB) { D.stat(t('ana.tempoSame', 'テンポの推定: 今の BPM・無音追加と同じです')); return; }
    const ch = await showTempo(tp, 'ask', run);
    if (run.cancelled) return;
    if (ch === 'a' || ch === 'b') applyTempo(tp, ch);
  }
  function applyTempo(tp, ch) {
    const lead = ch === 'b' ? Math.round(tp.alt_lead_ms) : Math.round(tp.lead_ms);
    D.applyTempo(tp.bpm, lead);
    const cur = D.grid();
    D.showOk(tf('ana.applied', 'BPM {bpm}・無音追加 {lead} ms にしました（Ctrl+Z で戻せます）', { bpm: fmtN(cur.bpm, 3), lead: cur.leadMs }));
  }
  // テンポの結果の画面。mode='ask'＝解析の途中（適用しない＝今のまま構成へ）/ 'view'＝メニューから見返す
  function showTempo(tp, mode, run) {
    if (S.dlg) S.dlg.close('none');
    return new Promise(res => {
      const c = compare(tp);
      const bg = document.createElement('div'); bg.id = 'dirtyDlgBg';
      const dlg = document.createElement('div'); dlg.id = 'dirtyDlg'; dlg.className = 'anaTempo'; bg.appendChild(dlg);
      const line = (txt, cls) => { const e = document.createElement('div'); e.className = 'atLine' + (cls ? ' ' + cls : ''); e.textContent = txt; dlg.appendChild(e); return e; };
      line(t('ana.t.title', 'テンポの推定'), 'atHead');
      if (tp.error) line('⚠ ' + tf('ana.t.few', '強い打点が少なすぎるため、テンポを推定できませんでした（BPM {bpm} は目安です）', { bpm: fmtN(tp.bpm) }), 'atWarn');
      else {
        line(tf('ana.t.prop', '提案: BPM {bpm} ／ 無音追加 {lead} ms', { bpm: fmtN(tp.bpm), lead: c.a }), 'atProp');
        line(tf('ana.t.cur', '今の設定: BPM {bpm} ／ 無音追加 {lead} ms', { bpm: fmtN(c.cur.bpm), lead: c.cur.leadMs }));
        line(tf('ana.t.oct', '2倍の {x2}・半分の {half} も同じ拍の流れです（譜面の細かさで選んでかまいません）', { x2: fmtN(tp.bpm * 2), half: fmtN(tp.bpm / 2) }), 'atNote');
        if (num(tp.raw_bpm) && tp.raw_bpm !== tp.bpm)
          line(tf('ana.t.int', '当てはめの値は {raw}。整数の {bpm} でも曲全体でずれが溜まらないので整数にしました', { raw: fmtN(tp.raw_bpm), bpm: fmtN(tp.bpm) }), 'atNote');
        if (num(tp.block_mad_ms))
          line(tf('ana.t.mad', '8秒ごとの、目盛りとのずれの中央値のばらつき {mad} ms（20ms 前後までなら耳では区別できません）・使った拍 {n}',
            { mad: Math.round(tp.block_mad_ms), n: num(tp.n_beats) ? tp.n_beats : '—' }), 'atNote');
        if (tp.alt) line(tf('ana.t.alt', '2番目の候補: BPM {bpm}（強さ {pct}%）', { bpm: fmtN(tp.alt.bpm), pct: Math.round(tp.alt.ratio * 100) })
          + (tp.alt.ratio >= 0.85 ? t('ana.t.altUnsure', '（迷いあり。こちらも聞いて確かめてください）') : ''), 'atNote');
        for (const s of tp.steps)
          line('⚠ ' + tf('ana.t.step', '{time} あたりから、打点が目盛りより {ms} ms ずれます（それまでとそれ以降はそれぞれ平ら）。拍の長さの違う所があるか、曲がそこで少しずれています。耳で確かめ、必要ならテンポパートで直してください',
            { time: mmss(s.sec), ms: (s.ms > 0 ? '+' : '') + Math.round(s.ms) }), 'atWarn');
        if (num(tp.drift_pct) && tp.drift_pct > 1.5) {
          line('⚠ ' + tf('ana.t.drift', '区間ごとのテンポの幅が {pct}% あります（ライブ録音・テンポの変わる曲の疑い）。1つの BPM では途中から合わなくなります:', { pct: tp.drift_pct.toFixed(1) }), 'atWarn');
          if (tp.drift.length) line(tp.drift.map(([s, b]) => `${mmss(s)} ${b.toFixed(1)}`).join('  '), 'atDrift');
        }
        const offR = num(tp.offbeat_ratio) && tp.offbeat_ratio >= 0.2;
        if (offR || tp.low_offbeat) {
          let s = '';
          if (offR) s += tf('ana.t.offRatio', '6秒区間の {pct}% で、強い打点が半拍ずれた位置にあります（裏拍の疑い）。', { pct: Math.round(tp.offbeat_ratio * 100) });
          if (tp.low_offbeat) s += t('ana.t.offLow', '低い音（キック・ベース）は、半拍ずれた位置の方に強く出ています（裏拍の疑い）。');
          line('⚠ ' + s, 'atWarn');
          if (c.b != null) line(tf('ana.t.offPick', 'どちらが拍の頭かは自動では決められないので、両方を聞いて合う方を選んでください（候補A {a} ms ／ 候補B {b} ms）', { a: c.a, b: c.b }), 'atNote');
        }
        if (c.flow && !c.isA && !c.isB) line(t('ana.t.flow', '今の設定は提案と同じ拍の流れです（BPM が2倍・半分か、無音追加が拍の長さの整数倍だけ違う）。適用しなくても構いません'), 'atNote');
        if (D.tempoParts() > 0) line(t('ana.t.tp', 'テンポパートがあります。適用で変わるのは曲頭の BPM と無音追加だけです'), 'atNote');
        if (D.hasChart()) line(t('ana.t.chart', '置いてあるノーツ・ライトは拍の位置のまま動きません（曲との合い方が変わります）。適用は Ctrl+Z で戻せます'), 'atNote');
        if (mode === 'ask') line(t('ana.t.askNote', '適用しなくても、今の BPM・無音追加のまま構成を解析します'), 'atNote');
      }
      const row = document.createElement('div'); row.className = 'ddBtns'; dlg.appendChild(row);
      const done = v => { if (S.dlg !== ctl) return; S.dlg = null; removeEventListener('keydown', onKey, true); bg.remove(); res(v); };
      const mk = (label, cls, v, dis) => { const b = document.createElement('button'); b.textContent = label; if (cls) b.className = cls; b.dataset.v = v;
        if (dis) b.disabled = true; b.addEventListener('click', () => done(v)); row.appendChild(b); return b; };
      if (!tp.error) {
        mk(t('ana.t.applyA', '提案を適用') + (c.isA ? t('ana.t.isCur', '（今の設定）') : ''), c.flow || c.isA ? '' : 'pri', 'a', c.isA);
        if (c.b != null) mk(t('ana.t.applyB', '候補B（半拍ずらし）を適用') + (c.isB ? t('ana.t.isCur', '（今の設定）') : ''), '', 'b', c.isB);
      }
      mk(mode === 'ask' ? t('ana.t.skip', '適用しない') : t('ui.close', '閉じる'), '', 'none');
      // 解析の途中に急に出るので、Enter では何も押さない（編集中の Enter で適用しないように）。Esc＝適用しない
      const onKey = e => { if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); done('none'); } else { if (e.key === 'Enter' || e.key === ' ') e.preventDefault(); e.stopPropagation(); } };
      addEventListener('keydown', onKey, true);
      const ctl = S.dlg = { run, close: v => done(v) };
      document.body.appendChild(bg);
    }).then(v => {
      if (mode === 'view' && (v === 'a' || v === 'b')) applyTempo(tp, v);
      return v;
    });
  }

  // ---- 曲を取り込んだ時の「曲を解析しますか？」 ----
  const askOn = () => lsGet(ASK_KEY) !== '0';
  function setAskOn(on) { lsSet(ASK_KEY, on ? '1' : '0'); if (askChk) askChk.checked = !!on; }
  if (askChk) { askChk.checked = askOn(); askChk.addEventListener('change', () => setAskOn(askChk.checked)); }
  /** 今聞いてよいか（設定・解析を使えない・解析中・画面を出している・音源が無い・この曲の結果がある＝目盛りが今と同じ） */
  function askWanted() {
    if (!askOn() || S.apiOff || S.run || S.ask || !D.hasAudio()) return false;
    return !(S.data && S.data.structure && !isStale());
  }
  /** 他の画面（未保存の確認・テンポの確認・更新・環境設定など）が出ているか＝重ねない */
  function otherDialog() {
    if (document.querySelector('#dirtyDlgBg, #updDlgBg')) return true;
    const s = document.getElementById('settingsBg');
    return !!s && getComputedStyle(s).display !== 'none';
  }
  function stopAskWait() { clearTimeout(S.askT); S.askT = null; S.askWait = 0; }
  /** editor-app.js から: 利用者の操作で新しく曲を取り込んだ */
  function songLoaded() {
    stopAskWait();
    if (!askWanted()) return;
    S.askWait = Date.now();
    tryAsk();
  }
  function tryAsk() {
    S.askT = null;
    if (!S.askWait) return;
    if (!askWanted()) { S.askWait = 0; return; }
    if (otherDialog()) {   // 閉じるのを待つ（待っている間に条件が変われば出さない）
      if (Date.now() - S.askWait < ASK_WAIT_MAX) S.askT = setTimeout(tryAsk, ASK_POLL_MS); else S.askWait = 0;
      return;
    }
    S.askWait = 0;
    showAsk();
  }
  function showAsk() {
    const el = (tag, cls, text) => { const e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; };
    const bg = el('div'); bg.id = 'dirtyDlgBg';
    const dlg = el('div', 'anaAsk'); dlg.id = 'dirtyDlg'; dlg.dataset.ana = 'ask'; bg.appendChild(dlg);
    dlg.appendChild(el('div', 'aaHead', t('ana.ask.title', '曲を解析しますか？')));
    dlg.appendChild(el('div', 'aaLead', t('ana.ask.lead', '曲を解析すると、次のことができます。')));
    const ul = el('ul', 'aaList'); dlg.appendChild(ul);
    for (const [k, ja] of ASK_POINTS) ul.appendChild(el('li', '', t('ana.ask.' + k, ja)));
    dlg.appendChild(el('div', 'aaNote', tf('ana.ask.later', '後で解析する時は、スペクトログラムの左の［{btn}］か、ファイルメニューの「{menu}」から。',
      { btn: t('ana.startBtn', '🎼 曲を解析'), menu: t('menu.analyze', '曲を解析（テンポ・構成）…') })));
    const lab = el('label', 'aaChk'), chk = el('input'); chk.type = 'checkbox'; chk.id = 'anaAskNever';
    lab.append(chk, el('span', '', t('ana.ask.never', '次から聞かない（環境設定で戻せます）')));
    dlg.appendChild(lab);
    const row = el('div', 'ddBtns'); dlg.appendChild(row);
    const done = v => {
      if (S.ask !== ctl) return;
      S.ask = null; removeEventListener('keydown', onKey, true); bg.remove();
      if (chk.checked) { setAskOn(false); D.stat(t('ana.ask.off', '曲を読み込んだ時に解析するかを聞かないようにしました（環境設定の「アプリケーション設定」で戻せます）')); }
      if (v === 'go') start();
    };
    const mk = (label, cls, v) => { const b = el('button', cls, label); b.type = 'button'; b.dataset.v = v; b.addEventListener('click', () => done(v)); row.appendChild(b); return b; };
    mk(t('ana.ask.go', '解析する'), 'pri', 'go');
    mk(t('ana.ask.notNow', '今はしない'), '', 'later');
    // 曲を読み込んだ直後に急に出るので、Enter では何も押さない（テンポの確認と同じ）。Esc＝今はしない。Space は「次から聞かない」のチェックだけ
    const onKey = e => {
      if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); done('later'); return; }
      if (e.key === 'Enter' || (e.key === ' ' && e.target !== chk)) e.preventDefault();
      e.stopPropagation();   // 裏のショートカットを発火させない
    };
    addEventListener('keydown', onKey, true);
    const ctl = S.ask = { close: v => done(v) };
    document.body.appendChild(bg);
  }

  // ---- 溝の［🧩 クリップを作る］と、解析が終わった時の「次にやること」の案内（2026-10-20・利用者の要望） ----
  // ボタン: 結果がある時だけ、帯の溝を下へ延ばした所（#anaAct）に出す。押す＝帯のメニューの「クリップを作る…」と同じ（D.makeClips＝editor-app.js の anaOpenClips）。
  // 目盛りが変わった（stale）時は薄くし、押すと anaOpenClips が今と同じ理由を知らせて断る。
  // 案内: 「曲を解析」で構成の解析が終わって帯が出た時（テンポの確認の後・解析し直した時も）に1回。保存した結果を開いた時・取り消し・エラーでは出さない。
  // 区切りが良いかは曲を聞かないと決められないので、いきなりクリップを作る画面は出さず、確かめ方とボタンの場所（画像）を案内する。
  // 環境設定 bsnm_anaGuide='0'＝出さない（キーが無い＝出す）。他の画面が出ていれば閉じるまで待つ。急に出るので Enter では閉じない・Esc＝閉じる。
  // 閉じた時に本物のボタンを少しの間光らせる。画像（guide/*.png・tools/make_guide_shots.py が撮る）が読めなくても文だけで分かるように書く。
  const GUIDE_KEY = 'bsnm_anaGuide', GLOW_MS = 2600;
  const GUIDE_STEPS = [
    ['s1', '曲を再生して、帯の区切りが曲に合っているかを耳で確かめてください。上の段＝セクション（大きい区切り。イントロ・Aメロ・サビ…）、下の段＝細かい区切り（A・B・C…）です。'],
    ['s2', 'どちらの区切りで打つかを決めます。帯をクリックするとその位置へ移動し、セクションの名前はダブルクリックで付け直せます。'],
    ['s3', '決めたら、帯の左の［{btn}］を押します。選んだ区切りどおりに空のクリップを新しいレーンへ作り、同じ番号のくり返しは自動でリンクします（両方を選べば両方作れます）。'],
  ];
  const actEl = document.getElementById('anaAct'), clipsBtn = document.getElementById('anaClipsBtn'), guideChk = document.getElementById('anaGuideOn');
  // dlg=案内の画面 / wait=他の画面が閉じるのを待ち始めた時刻（0=待っていない）/ key=ボタンの表示を最後に書いた時の値 / glowT=光らせるのを止めるタイマー
  const G = { dlg: null, wait: 0, timer: null, key: '', glowT: null };
  const clipsLabel = () => t('ana.clipsBtn', '🧩 クリップを作る');
  // この解析の結果から一度クリップを作った後（S.data.made・保存される。解析し直すと新しい結果には無い＝元の紫に戻る）は、彩度を落とした暗い紫（.made）。押せるのは同じ
  function syncClipsBtn() {
    if (!actEl || !clipsBtn) return;
    const on = !!structure(), stale = on && S.staleNow, made = on && !!S.data.made, label = clipsLabel();
    const tip = stale ? t('ana.clipsStaleTip', '目盛り（BPM・無音追加・テンポパート・Music の配置）が解析した時と変わったため、今はクリップを作れません。解析し直してから押してください')
      : made ? t('ana.clipsMadeTip', 'この解析の結果からクリップを作成済みです。もう一度押すと、新しいレーンにもう1組作ります（帯のメニューの「クリップを作る…」と同じです）')
      : t('ana.clipsTip', '帯の区切り（セクション／細かい区切り）どおりに空のクリップを新しいレーンへ作ります（同じ番号のくり返しは自動でリンク）。帯のメニューの「クリップを作る…」と同じです');
    const key = (on ? 1 : 0) + '|' + (stale ? 1 : 0) + '|' + (made ? 1 : 0) + '|' + label + '|' + tip;   // 言語を切り替えたら書き直す
    if (key === G.key) return;
    G.key = key;
    actEl.classList.toggle('on', on);
    clipsBtn.classList.toggle('stale', stale);
    clipsBtn.classList.toggle('made', made);
    clipsBtn.textContent = label; clipsBtn.title = tip;
  }
  if (clipsBtn) clipsBtn.addEventListener('click', e => { e.stopPropagation(); D.makeClips(); });
  function glowClips() {
    if (!clipsBtn) return;
    clearTimeout(G.glowT);
    clipsBtn.classList.remove('glow'); void clipsBtn.offsetWidth;   // 続けて光らせる時もアニメーションを頭から
    clipsBtn.classList.add('glow');
    G.glowT = setTimeout(() => clipsBtn.classList.remove('glow'), GLOW_MS);
  }
  const guideOn = () => lsGet(GUIDE_KEY) !== '0';
  function setGuideOn(on) { lsSet(GUIDE_KEY, on ? '1' : '0'); if (guideChk) guideChk.checked = !!on; }
  if (guideChk) { guideChk.checked = guideOn(); guideChk.addEventListener('change', () => setGuideOn(guideChk.checked)); }
  const guideWanted = () => guideOn() && !!structure() && !S.run && !G.dlg;
  function stopGuideWait() { clearTimeout(G.timer); G.timer = null; G.wait = 0; }
  /** 新規・開く: 待っている案内・出ている案内をやめる（光らせない） */
  function stopGuide() { stopGuideWait(); if (G.dlg) G.dlg.close(false); }
  /** 構成の解析が終わって帯が出た（start の成功の後） */
  function guideAfterAnalysis() {
    stopGuideWait();
    if (!guideWanted()) return;
    G.wait = Date.now();
    tryGuide();
  }
  function tryGuide() {
    G.timer = null;
    if (!G.wait) return;
    if (!guideWanted()) { G.wait = 0; return; }
    if (otherDialog()) {   // 閉じるのを待つ（待っている間に結果が消えた・解析し直し始めた等なら出さない）
      if (Date.now() - G.wait < ASK_WAIT_MAX) G.timer = setTimeout(tryGuide, ASK_POLL_MS); else G.wait = 0;
      return;
    }
    G.wait = 0;
    showGuide();
  }
  function showGuide() {
    const el = (tag, cls, text) => { const e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; };
    const bg = el('div'); bg.id = 'dirtyDlgBg';
    const dlg = el('div', 'anaGuide'); dlg.id = 'dirtyDlg'; dlg.dataset.ana = 'guide'; bg.appendChild(dlg);
    dlg.appendChild(el('div', 'agHead', t('ana.guide.title', '曲の解析が終わりました ― 次にやること')));
    const ol = el('ol', 'agList'); dlg.appendChild(ol);
    for (const [k, ja] of GUIDE_STEPS) ol.appendChild(el('li', '', tf('ana.guide.' + k, ja, { btn: clipsLabel() })));
    // ボタンの場所の画像（言語ごと。訳の値は guide/ の .png の名前だけを受け付ける）。読めなければ図ごと外す＝文だけで分かる
    const src = String(t('ana.guide.img', 'guide/ana-clips-btn-ja.png'));
    if (/^guide\/[\w.-]{1,80}\.png$/.test(src)) {
      const fig = el('figure', 'agFig'), img = el('img');
      img.alt = t('ana.guide.imgAlt', '解析の帯の左の溝にある［クリップを作る］のボタン（赤枠）');
      img.addEventListener('error', () => fig.remove());
      img.src = src;
      fig.append(img, el('figcaption', '', tf('ana.guide.cap', '赤枠＝［{btn}］（帯の左の溝・「構成」の下）', { btn: clipsLabel() })));
      dlg.appendChild(fig);
    }
    const lab = el('label', 'agChk'), chk = el('input'); chk.type = 'checkbox'; chk.id = 'anaGuideNever';
    lab.append(chk, el('span', '', t('ana.guide.never', '次から出さない（環境設定で戻せます）')));
    dlg.appendChild(lab);
    const row = el('div', 'ddBtns'); dlg.appendChild(row);
    const done = glow => {
      if (G.dlg !== ctl) return;
      G.dlg = null; removeEventListener('keydown', onKey, true); bg.remove();
      if (chk.checked) { setGuideOn(false); D.stat(t('ana.guide.off', '解析が終わった時の案内を出さないようにしました（環境設定の「アプリケーション設定」で戻せます）')); }
      if (glow) glowClips();   // 本物のボタンの場所を示す
    };
    const ok = el('button', 'pri', t('ana.guide.ok', 'わかった')); ok.type = 'button'; ok.dataset.v = 'ok';
    ok.addEventListener('click', () => done(true)); row.appendChild(ok);
    // 解析の終わりに急に出るので、Enter では閉じない（編集中の Enter で読まずに閉じないように）。Esc＝閉じる。Space は「次から出さない」のチェックだけ
    const onKey = e => {
      if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); done(true); return; }
      if (e.key === 'Enter' || (e.key === ' ' && e.target !== chk)) e.preventDefault();
      e.stopPropagation();   // 裏のショートカットを発火させない
    };
    addEventListener('keydown', onKey, true);
    const ctl = G.dlg = { close: glow => done(glow) };
    document.body.appendChild(bg);
  }

  // ---- 名前の付け直し・マーカー・消す ----
  function rename(sec) {
    const st = structure(); if (!st) return;
    const X = beatX(S.win);
    const x0 = Math.max(GUT, X(sec.start)), x1 = Math.min(W, X(sec.end));
    const rect = { x: x0 < W - 40 ? x0 : GUT, y: SEC_Y[0] - 1, w: Math.max(120, x1 - x0), h: SEC_Y[1] - SEC_Y[0] + 2 };
    D.inlineEdit(rect, dispName(sec), v => setName(sec.label, v), false, cv);
  }
  function setName(label, v) {
    const d = S.data, st = structure(); if (!st) return;
    v = String(v ?? '').replace(/[\r\n\t]+/g, ' ').trim().slice(0, NAME_MAX);
    const secs = st.sections.filter(s => s.label === label); if (!secs.length) return;
    const allAuto = secs.every(s => autoName(s) === v);   // 自動の名前と同じ＝付け直しをやめる
    const next = (!v || allAuto) ? undefined : v, cur = (d.names || {})[label];
    if (next === cur) return;
    D.snapshot();
    const names = { ...(d.names || {}) };
    if (next === undefined) delete names[label]; else names[label] = next;
    d.names = names; D.dirty();
    D.stat(next === undefined ? tf('ana.renamedAuto', '{label} の名前を自動の名前に戻しました', { label })
      : tf('ana.renamed', '{label} の名前: {name}（同じ番号のセクション全部）', { label, name: next }));
  }
  function exportMarkers() {
    const st = structure(); if (!st) return;
    const items = st.sections.map(s => { const n = dispName(s); return { beat: s.start, name: (n ? n + ' ' : '') + s.label }; });
    const r = D.exportMarkers(items);
    const parts = [];
    if (r.added) parts.push(tf('ana.mk.added', 'セクションの頭にマーカーを {n} 個足しました', { n: r.added }));
    if (r.updated) parts.push(tf('ana.mk.updated', '{n} 個のマーカーの名前を直しました', { n: r.updated }));
    if (r.skipped) parts.push(tf('ana.mk.skipped', '{n} 個は同じ位置に別のマーカーがあるため飛ばしました', { n: r.skipped }));
    if (!r.added && !r.updated) D.stat(parts.concat(t('ana.mk.none', '書き出すマーカーはありません（書き出し済みです）')).join(t('ana.sep', '・')));
    else D.showOk(parts.join(t('ana.sep', '・')));
  }
  function clear() {
    if (!S.data) return;
    D.snapshot(); S.data = null; D.dirty();
    D.stat(t('ana.cleared', '解析の結果を消しました（Ctrl+Z で戻せます）'));
  }
  function menuItems(sec) {
    const st = structure(), it = [];
    if (sec) it.push([tf('ana.m.rename', '{label}「{name}」の名前を付け直す…', { label: sec.label, name: dispName(sec) || '—' }), () => rename(sec)], ['---']);
    if (st) it.push([t('ana.m.clips', 'クリップを作る…'), () => D.makeClips()],   // 解析からクリップを作る（editor-app.js の anaOpenClips。目盛りが変わっていれば理由を出して断る）
      [t('ana.m.markers', 'セクションの頭にマーカーを書き出す'), exportMarkers]);
    if (S.data && S.data.tempo) it.push([t('ana.m.tempo', 'テンポの推定結果…'), () => showTempo(S.data.tempo, 'view', null)]);
    if (S.run) it.push([t('ana.m.cancel', '解析をやめる'), () => cancel()]);
    else it.push([st ? t('ana.reanalyze', '解析し直す') : t('ana.m.analyze', '曲を解析'), start]);
    if (S.data) it.push(['---'], [t('ana.m.clear', '解析の結果を消す'), clear]);
    return it;
  }

  // ---- 描画 ----
  const beatX = win => b => GUT + (b - win.b0) / win.span * (W - GUT);
  function fitText(cands, w) { for (const s of cands) if (s && g.measureText(s).width + 8 <= w) return s; return ''; }
  function syncShown() {
    const on = !!(structure() || S.run);
    if (on !== S.shown) { S.shown = on; spec.classList.toggle('anaOn', on); resize(); try { D.specResize(); } catch (_) {} }
    const sb = !on && D.hasAudio();
    if (sb !== S.startShown) { S.startShown = sb; if (startBtn) startBtn.style.display = sb ? '' : 'none'; }
  }
  // 帯の上の知らせ: 解析中＝帯の左寄せ（溝のすぐ右）の濃い紫・進み具合のバーに流れる縞・枠がゆっくり明滅（見た目は analysis.css）／目盛りが変わった＝右寄せ。
  // 部品は種類（解析中／目盛りが変わった）と言語が変わった時だけ作り直し、文・バーの幅はその場で書き換える
  //（作り直すと縞のアニメーションが頭からになり、進み具合が届くたびに縞が跳ねるため）
  const M = { mode: '', lang: '', tx: null, bar: null };
  function runText(stage, p) {
    return t('ana.run', '曲を解析中:') + ' ' + (stage === 'upload' ? t('ana.st.upload', '音源を送っています…')
      : stage === 'tempo' ? tf('ana.st.tempo', 'テンポを推定 {p}%', { p })
      : stage === 'decide' ? t('ana.st.decide', 'テンポの確認待ち') : tf('ana.st.structure', '構成を解析 {p}%', { p }));
  }
  // 解析中の文の欄は、この言語で一番長くなる文（どの段階も 100%）の幅に固定する＝数字の桁・段階が変わっても箱の長さとバーの位置が動かない
  //（利用者の要望: 1桁→2桁で箱が伸び縮みし、解析が進んだり戻ったりして見えた）
  function fixRunTextWidth() {
    M.tx.style.width = '';
    let w = 0;
    for (const s of ['upload', 'tempo', 'decide', 'structure']) { M.tx.textContent = runText(s, 100); w = Math.max(w, M.tx.scrollWidth); }
    M.tx.style.width = Math.ceil(w + 1) + 'px';
  }
  function syncMsg() {
    if (!msgEl) return;
    const run = S.run, stale = !run && S.staleNow, mode = run ? 'run' : stale ? 'stale' : '';
    let text = '', frac = 0;
    if (run) {
      text = runText(run.stage, Math.round((run.progress || 0) * 100));
      frac = run.stage === 'upload' ? 0.02 : run.stage === 'tempo' ? 0.05 + 0.3 * (run.progress || 0) : run.stage === 'decide' ? 0.35 : 0.35 + 0.65 * (run.progress || 0);
    } else if (stale) text = t('ana.stale', '目盛りが変わりました。解析し直してください');
    const lang = t('ana.cancelBtn', 'やめる') + '|' + t('ana.reanalyze', '解析し直す');   // 言語を切り替えたら作り直す
    const key = mode + '|' + text + '|' + frac.toFixed(3) + '|' + lang;
    if (key === S.msgKey) return;
    S.msgKey = key;
    if (mode !== M.mode || lang !== M.lang) {
      M.mode = mode; M.lang = lang; M.tx = M.bar = null;
      msgEl.textContent = '';
      msgEl.className = mode;
      msgEl.style.display = mode ? 'flex' : 'none';
      msgEl.title = stale ? t('ana.staleTip', '解析した後に BPM・無音追加・テンポパート・Music の配置（または音源）が変わったため、帯の位置が今の目盛りと合っていない可能性があります') : '';
      if (mode) {
        M.tx = document.createElement('span'); M.tx.className = 'amTxt'; msgEl.appendChild(M.tx);
        if (run) { const bar = document.createElement('span'); bar.className = 'amBar'; M.bar = document.createElement('i'); bar.appendChild(M.bar); msgEl.appendChild(bar); }
        const b = document.createElement('button'); b.type = 'button'; b.className = 'amBtn';
        b.textContent = run ? t('ana.cancelBtn', 'やめる') : t('ana.reanalyze', '解析し直す');
        b.addEventListener('click', e => { e.stopPropagation(); if (S.run) cancel(); else start(); });
        msgEl.appendChild(b);
        if (run) fixRunTextWidth();
      }
    }
    if (M.tx) M.tx.textContent = (stale ? '⚠ ' : '') + text;
    if (M.bar) M.bar.style.width = (frac * 100).toFixed(1) + '%';
  }
  function draw(curV) {
    S.staleNow = isStale();
    syncShown(); syncMsg(); syncClipsBtn();
    if (!S.shown || !W || !H) return;
    const win = S.win = D.tlWindow(curV), X = beatX(win), st = structure();
    g.clearRect(0, 0, W, H);
    g.fillStyle = '#121216'; g.fillRect(0, 0, W, H);
    g.textBaseline = 'middle'; g.textAlign = 'left';
    if (st) {
      g.save(); g.beginPath(); g.rect(GUT, 0, W - GUT, H); g.clip();
      g.globalAlpha = S.staleNow ? 0.4 : 1;
      const so = secOrder(), go = segOrder(), hv = S.hover && S.hover.sec ? S.hover.sec.label : null, hg = S.hover && S.hover.seg ? S.hover.seg.group : null;
      g.font = 'bold 10.5px ' + D.FONT;
      for (const s of st.sections) {
        const x0 = X(s.start), x1 = X(s.end); if (x1 < GUT || x0 > W) continue;
        g.fillStyle = colorOf(so, s.label, SPAL); g.fillRect(x0 + 0.5, SEC_Y[0], Math.max(1, x1 - x0 - 1), SEC_Y[1] - SEC_Y[0]);
        if (s.chorus) { g.fillStyle = '#ffd25a'; g.fillRect(x0 + 0.5, SEC_Y[1] - 2, Math.max(1, x1 - x0 - 1), 2); }   // サビの候補＝下の縁を金色に
        if (hv === s.label) { g.strokeStyle = 'rgba(255,255,255,.85)'; g.lineWidth = 1; g.strokeRect(x0 + 1, SEC_Y[0] + 0.5, Math.max(1, x1 - x0 - 2), SEC_Y[1] - SEC_Y[0] - 1); }
        const vx0 = Math.max(x0, GUT), vx1 = Math.min(x1, W), txt = fitText(secTexts(s), vx1 - vx0);   // 収まらない幅では番号を出さない（切れて別の番号に見えるため）
        if (txt) { g.fillStyle = '#fff'; g.fillText(txt, vx0 + 4, (SEC_Y[0] + SEC_Y[1]) / 2 + 0.5); }
      }
      g.font = 'bold 9.5px ' + D.FONT;
      for (const s of st.segments) {
        const x0 = X(s.start), x1 = X(s.end); if (x1 < GUT || x0 > W) continue;
        g.globalAlpha = (S.staleNow ? 0.4 : 1) * 0.85;
        g.fillStyle = colorOf(go, s.group, PAL); g.fillRect(x0 + 0.5, SEG_Y[0], Math.max(1, x1 - x0 - 1), SEG_Y[1] - SEG_Y[0]);
        g.globalAlpha = S.staleNow ? 0.4 : 1;
        if (hg === s.group) { g.strokeStyle = 'rgba(255,255,255,.85)'; g.lineWidth = 1; g.strokeRect(x0 + 1, SEG_Y[0] + 0.5, Math.max(1, x1 - x0 - 2), SEG_Y[1] - SEG_Y[0] - 1); }
        const vx0 = Math.max(x0, GUT), vx1 = Math.min(x1, W), txt = fitText([s.group], vx1 - vx0);
        if (txt) { g.fillStyle = '#fff'; g.fillText(txt, vx0 + 4, (SEG_Y[0] + SEG_Y[1]) / 2 + 0.5); }
      }
      g.restore();
    }
    // 左の溝（ラベル。⋯ のボタンは HTML の #anaMenuBtn を重ねている）
    g.fillStyle = '#1b1b1f'; g.fillRect(0, 0, GUT, H);
    g.strokeStyle = '#161616'; g.lineWidth = 1; g.beginPath(); g.moveTo(GUT + 0.5, 0); g.lineTo(GUT + 0.5, H); g.stroke();
    g.fillStyle = '#9a9a9a'; g.font = 'bold 10px ' + D.FONT;
    g.fillText(t('ana.gSec', '構成'), 8, (SEC_Y[0] + SEC_Y[1]) / 2 + 0.5);
    g.font = '9.5px ' + D.FONT;
    g.fillText(t('ana.gSeg', '細かい区切り'), 8, (SEG_Y[0] + SEG_Y[1]) / 2 + 0.5);
    // マウスの拍（黄）→ 再生ヘッド（赤）の順＝赤が最前面（Music・NLE と同じ）
    const hb = D.hoverBeat(); if (hb != null) { const hx = X(hb); if (hx >= GUT) D.crispVLine(g, cv, hx, 'rgba(255,216,45,.85)'); }
    const px = X(curV); if (px >= GUT) D.phRect(g, cv, px);
  }

  // ---- マウス ----
  function hitAt(e) {
    const r = cv.getBoundingClientRect(), sx = e.clientX - r.left, sy = e.clientY - r.top, st = structure();
    if (sx < GUT || !st) return null;
    const b = S.win.b0 + (sx - GUT) / Math.max(1, W - GUT) * S.win.span;
    if (sy < SEC_Y[1] + 1.5) return { beat: b, sec: st.sections.find(q => b >= q.start && b < q.end) || null };
    return { beat: b, seg: st.segments.find(q => b >= q.start && b < q.end) || null };
  }
  function tipOf(h) {
    if (!h) return '';
    const st = structure();
    if (h.sec) {
      const s = h.sec, n = st.sections.filter(q => q.label === s.label).length;
      return tf('ana.tipSec', '{text}・同じ番号 {count}回・拍 {s}〜{e}{chorus}\nクリック＝この位置へ ／ ダブルクリック＝名前を付け直す（同じ番号の全部）／ 右クリック＝メニュー',
        { text: secTexts(s)[0], count: n, s: fmtN(s.start, 2), e: fmtN(s.end, 2), chorus: s.chorus ? t('ana.tipChorus', '（★サビの候補）') : '' });
    }
    if (h.seg) {
      const s = h.seg;
      const best = s.best == null ? t('ana.tipOnce', '・1回だけ') : tf('ana.tipBest', '・一番似ている所 拍 {b}（{sim}%）', { b: fmtN(s.best, 2), sim: s.sim == null ? '—' : Math.round(s.sim * 100) });
      return tf('ana.tipSeg', '{group}・{count}回・拍 {s}〜{e}{best}{chorus}\nクリック＝この位置へ ／ 右クリック＝メニュー',
        { group: s.group, count: s.count, s: fmtN(s.start, 2), e: fmtN(s.end, 2), best, chorus: st.chorus.includes(s.group) ? t('ana.tipSegChorus', '（サビの候補）') : '' });
    }
    return '';
  }
  cv.addEventListener('pointerdown', e => {
    if (e.button !== 0) return;
    const h = hitAt(e), it = h && (h.sec || h.seg);
    if (it) D.seek(it.start);   // 帯をクリック＝その頭へ（窓は動かさない＝ルーラーのクリックと同じ）
  });
  cv.addEventListener('dblclick', e => { const h = hitAt(e); if (h && h.sec) rename(h.sec); });
  cv.addEventListener('contextmenu', e => {
    e.preventDefault();
    const r = cv.getBoundingClientRect(); if (e.clientX - r.left < GUT && !structure()) return;
    const h = hitAt(e);
    D.showMenu(e.clientX, e.clientY, menuItems(h && h.sec));
  });
  cv.addEventListener('pointermove', e => {
    const h = hitAt(e);
    S.hover = h && (h.sec || h.seg) ? h : null;
    D.setHover(h ? h.beat : null);
    const tip = tipOf(S.hover);
    if (tip !== S.tip) { S.tip = tip; cv.title = tip; }
  });
  cv.addEventListener('mouseleave', () => { S.hover = null; D.setHover(null); if (S.tip) { S.tip = ''; cv.title = ''; } });
  cv.addEventListener('wheel', D.wheel, { passive: false });   // 素=時間移動・Ctrl=ズーム（NLE・Music と同じ）
  if (startBtn) startBtn.addEventListener('click', () => start());
  if (menuBtn) menuBtn.addEventListener('click', e => { const r = menuBtn.getBoundingClientRect(); e.stopPropagation(); D.showMenu(r.left, r.bottom + 2, menuItems(null)); });

  return {
    start, cancel, draw,
    /** 利用者の操作で新しく曲（音源）を取り込んだ（editor-app.js から）: 条件が合えば「曲を解析しますか？」を出す */
    songLoaded,
    /** プロジェクトへ保存する中身（結果が無ければ undefined＝キーごと書かない）。made＝この結果からクリップを作った（作っていなければキーごと無し＝以前の版と同じ中身） */
    save() {
      const d = S.data; if (!d) return undefined;
      const o = { v: 1, tempo: d.tempo || null, structure: d.structure || null, names: { ...(d.names || {}) }, grid: d.grid || null };
      if (d.made && d.structure) o.made = true;
      return o;
    },
    /** プロジェクト（ファイル由来）・履歴から戻す。解析中の作業はそのまま */
    load(raw) {
      if (!raw || typeof raw !== 'object') { S.data = null; return; }
      const structure = cleanStructure(raw.structure), tempo = cleanTempo(raw.tempo);
      S.data = (structure || tempo) ? { v: 1, tempo, structure, names: cleanNames(raw.names, structure), grid: cleanGrid(raw.grid) } : null;
      if (S.data && structure && raw.made === true) S.data.made = true;   // ファイル由来なので真偽値の true だけ受け付ける
    },
    /** この結果からクリップを作ったか（溝のボタンを暗くする印）。editor-app.js の anaMakeClips が作った後に true、
     *  全難易度の履歴 'diffs' が控え・戻す（クリップを作る操作の Ctrl+Z で印も戻る）。結果が無ければ何もしない */
    made() { return !!(S.data && S.data.structure && S.data.made); },
    setMade(on) { const d = S.data; if (!d || !d.structure) return; if (on) d.made = true; else delete d.made; },
    /** 新規・開く: 結果を消し、解析中ならやめる（取り込んだ曲について聞く画面・その待ちもやめる） */
    reset() { cancel(true); S.data = null; S.hover = null; stopAskWait(); if (S.ask) S.ask.close('later'); stopGuide(); },
    /** 未保存の判定（projSig）に入れる文字列 */
    sig() { const v = this.save(); return v ? JSON.stringify(v) : undefined; },
    /** 帯のセクション（表示している名前・番号・拍・サビの候補） */
    sections() { const st = structure(); return st ? st.sections.map(s => ({ start: s.start, end: s.end, label: s.label, name: dispName(s), chorus: s.chorus, count: s.count })) : []; },
    /** 解析からクリップを作る（editor-app.js の anaMakeClips）の材料。結果が無ければ null。
     *  各区間 {start,end,key:番号/グループ, name:クリップ名（「Aメロ S3」＝表示している名前＋番号／細かい区切りは「C」）, color:帯の色, order:番号の順}。
     *  拍が負・前の区間と重なる区間（ファイル由来のおかしな値）は飛ばす（同じレーンにクリップを重ねないため）。stale＝目盛りが解析した時と違う */
    clipSource() {
      const st = structure(); if (!st) return null;
      const so = secOrder(), go = segOrder();
      const tidy = list => { const out = []; let end = 0;
        for (const it of list) { const s = Math.max(0, it.start); if (it.end <= s + 1e-6 || s < end - 1e-6) continue; out.push({ ...it, start: s }); end = it.end; }
        return out; };
      return {
        stale: isStale(),
        sections: tidy(st.sections.map(s => { const n = dispName(s);
          return { start: s.start, end: s.end, key: s.label, name: (n ? n + ' ' : '') + s.label, color: colorOf(so, s.label, SPAL), order: Math.max(0, so.indexOf(s.label)) }; })),
        segments: tidy(st.segments.map(s => ({ start: s.start, end: s.end, key: s.group, name: s.group, color: colorOf(go, s.group, PAL), order: Math.max(0, go.indexOf(s.group)) }))),
      };
    },
    /** 開発用の読み取り（tests）。値の複製だけを返す */
    dbg() {
      const st = structure();
      return JSON.parse(JSON.stringify({
        shown: !!S.shown, startBtn: !!S.startShown, stale: isStale(), dialog: !!S.dlg,
        ask: !!S.ask, askWait: !!S.askWait, askOn: askOn(), apiOff: S.apiOff,
        guide: !!G.dlg, guideWait: !!G.wait, guideOn: guideOn(),
        clipsBtn: { shown: !!(actEl && actEl.classList.contains('on')), stale: !!(clipsBtn && clipsBtn.classList.contains('stale')), glow: !!(clipsBtn && clipsBtn.classList.contains('glow')),
          made: !!(clipsBtn && clipsBtn.classList.contains('made')) },
        running: S.run ? { stage: S.run.stage, progress: S.run.progress } : null,
        msg: msgEl && msgEl.style.display !== 'none' ? msgEl.textContent : '',
        title: cv.title, data: this.save() || null,
        labels: st ? st.sections.map(s => secTexts(s)[0]) : [], groups: st ? st.segments.map(s => s.group) : [],
        canvasH: H, specH: (document.getElementById('speccv') || {}).clientHeight || 0,
      }));
    },
    /** 帯の拍 beat の x と各段の中央の y（ページ座標px） */
    screen(beat) {
      const r = cv.getBoundingClientRect(), X = beatX(S.win);
      return { x: r.left + X(beat), left: r.left, top: r.top, w: r.width, h: r.height, gut: GUT,
        sec: r.top + (SEC_Y[0] + SEC_Y[1]) / 2, seg: r.top + (SEG_Y[0] + SEG_Y[1]) / 2 };
    },
  };
}

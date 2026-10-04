// 自動ライティング: ノーツから「それっぽい」基本ライトイベントを作る（2026-10-03）
// 狙いは譜面チェックのライト項目を満たす最低限＋見た目。
//   - BS Map Check の insufficientLight（消灯以外のライトが11個以上）
//   - NLM版BL評価リストの R10.A（数に入る種別のライトが曲の長さ全体で平均1拍に1個以上）
//   - 同 R7.B（ボムの250ms前から明るさ50%以上のライトが点いている）
// 生成するのは基本イベント（v2の_events / v3のbasicBeatmapEvents）だけ。値の意味は Beat Saber の基本イベント:
//   色 = 0:青 / 4:赤 に 1:点灯 2:フラッシュ 3:フェード を足す。8:リング回転・9:リングズーム(値0)。12/13:レーザー速度(値=速さ)
// 色はバニラ（赤/青）だけ＝customData.color（Chroma）は書かない。実際の色はレーザー色の設定で決まる。
import { BASIC_TRACKS } from '../mapcheck/env-tables.js';

const BLUE = 0, RED = 4, ON = 1, FLASH = 2, FADE = 3;
const T = { BACK: 0, RINGS: 1, LLASER: 2, RLASER: 3, CENTER: 4, RROT: 8, RZOOM: 9, LSPEED: 12, RSPEED: 13 };
const EPS = 1e-6;
const DENSITY_TARGET = 1.2;   // R10.Aの基準(1.0)に余裕を持たせる
const PHRASE = 16;            // マーカーが無い時の場面の区切り（拍）
const LASER_GAP_SEC = 0.12;   // 同じレーザーを続けて光らせる最短間隔（R10.B: チカチカで譜面を見えにくくしない）
const LASER_GAP_BEAT = 0.25;

/** 環境で使える種別(k)と、R10.Aの数に入る種別(l)。表に無い環境はDefault扱い */
export function envTypes(env) {
  const t = BASIC_TRACKS[env];
  const d = BASIC_TRACKS.DefaultEnvironment;
  return t && t.k.length ? { k: t.k, l: t.l.length ? t.l : d.l } : { k: d.k, l: d.l };
}

/**
 * @param {object} p
 * @param {Array} p.notes  {beat,c}（c=0赤/1青）
 * @param {Array} p.chains {b,c}（頭は書き出しでノーツになる）
 * @param {Array} p.others ボム・壁・アーク（最初/最後の位置にだけ使う。{beat|b, dur?, tb?}）
 * @param {number} p.endBeat 曲の最後の拍（書き出しはここで切れる）
 * @param {number} p.bpm
 * @param {string} p.env 環境名
 * @param {number[]} p.markers マーカーの拍（場面の区切りに使う）
 * @returns {{events:Array<{beat,et,i,f}>, counted:number, perBeat:number, endBeat:number}|null} 置く物が無ければnull
 */
export function generateAutoLights({ notes = [], chains = [], others = [], endBeat, bpm = 120, env, markers = [] }) {
  const hits = new Map();   // 拍 → {red,blue}（同じ時刻のノーツは1つにまとめる）
  const addHit = (b, c) => {
    const k = Math.round(b * 1000) / 1000;
    const h = hits.get(k) || { beat: k, red: false, blue: false };
    if (c === 0) h.red = true; else if (c === 1) h.blue = true;
    hits.set(k, h);
  };
  for (const n of notes) addHit(n.beat ?? 0, n.c);
  for (const c of chains) addHit(c.b ?? 0, c.c);
  const times = [...hits.values()].sort((a, b) => a.beat - b.beat);
  let first = Infinity, last = -Infinity;
  const span = (s, e) => { if (s < first) first = s; if (e > last) last = e; };
  for (const h of times) span(h.beat, h.beat);
  for (const o of others) {
    const s = o.beat ?? o.b ?? 0;
    span(s, Math.max(s + (o.dur > 0 ? o.dur : 0), o.tb ?? s));
  }
  if (!Number.isFinite(first)) return null;
  if (!(endBeat > last)) endBeat = Math.ceil((last + 4) / 4) * 4;   // 音源が無い時: 最後の物から1小節先まで
  const { k: avail, l: counted } = envTypes(env);
  const has = et => avail.includes(et);

  const out = new Map();   // 「拍|種別」→イベント（同じ拍・同じ種別は1つ。後から置いた方を優先しない＝先勝ち）
  const put = (beat, et, i) => {
    if (!has(et) || beat < -EPS || beat >= endBeat - EPS) return false;
    const b = Math.round(beat * 1000) / 1000, key = b + '|' + et;
    if (out.has(key)) return false;
    out.set(key, { beat: b, et, i, f: 1 });
    return true;
  };

  // 場面（色を切り替える単位）: マーカーがあればマーカー、無ければ16拍ごと
  const ms = [...new Set(markers.filter(b => b > EPS && b < endBeat - EPS).map(b => Math.round(b * 1000) / 1000))].sort((a, b) => a - b);
  const bounds = [0, ...(ms.length ? ms : Array.from({ length: Math.ceil(endBeat / PHRASE) - 1 }, (_, i) => (i + 1) * PHRASE))];
  const phraseAt = b => { let i = 0; while (i + 1 < bounds.length && bounds[i + 1] <= b + EPS) i++; return i; };
  const colAt = b => (phraseAt(b) % 2 ? RED : BLUE);
  const active = b => b >= first - EPS && b <= last + EPS;   // ノーツ等がある区間

  // 1. ベース照明: BACKを曲の頭から点け、場面ごとに色を変え、最後の物の2拍後にフェードで消す
  //    BACKは途中で消さない＝ボムは常に照らされる（R7.B）
  const baseEnd = Math.min(last + 2, endBeat - 0.5);
  put(0, T.BACK, colAt(0) + ON);
  for (const b of bounds.slice(1)) if (b < baseEnd - EPS) put(b, T.BACK, colAt(b) + FLASH);
  if (baseEnd > 0) put(Math.max(baseEnd, 0), T.BACK, colAt(baseEnd) + FADE);

  // 2. ノーツ連動: 赤ノーツ=左レーザー、青ノーツ=右レーザー（同時なら両方）。
  //    同じレーザーが詰まりすぎる時は反対側へ回し、それも詰まっていれば光らせない
  const gap = Math.max(LASER_GAP_BEAT, LASER_GAP_SEC * bpm / 60);
  const lastAt = { [T.LLASER]: -Infinity, [T.RLASER]: -Infinity };
  times.forEach((h, idx) => {
    const next = times[idx + 1];
    const behav = next && next.beat - h.beat < 0.5 + EPS ? FLASH : FADE;   // 密な所はフラッシュ（点いたまま）、間がある所はフェード
    const want = [];
    if (h.red) want.push([T.LLASER, RED]);
    if (h.blue) want.push([T.RLASER, BLUE]);
    for (const [lane, col] of want) {
      const other = lane === T.LLASER ? T.RLASER : T.LLASER;
      const pick = h.beat - lastAt[lane] >= gap - EPS ? lane
        : (want.length === 1 && h.beat - lastAt[other] >= gap - EPS ? other : null);
      if (pick == null) continue;
      if (put(h.beat, pick, col + behav)) lastAt[pick] = h.beat;
    }
  });

  // 3. レーザー速度: 小節ごとのノーツの密度で速さを決め、変わった時だけ置く
  let lastSpeed = -1;
  for (let bar = Math.floor(first / 4) * 4; bar <= last + EPS; bar += 4) {
    const n = times.filter(h => h.beat >= bar - EPS && h.beat < bar + 4 - EPS).length;
    const sp = n ? Math.max(1, Math.min(8, Math.round(n / 4 * 3) + 1)) : 0;
    const newPhrase = bounds.some(b => Math.abs(b - bar) < EPS);
    if (sp !== lastSpeed || (newPhrase && sp)) {
      put(bar, T.LSPEED, sp); put(bar, T.RSPEED, sp); lastSpeed = sp;
    }
  }

  // 4. アクセント: 場面の頭=リングのズーム＋回転、ノーツのある区間は小節頭でCENTER、2小節ごとにリング回転
  for (const b of bounds) if (active(b) || b === 0) { put(b, T.RZOOM, 0); put(b, T.RROT, 0); }
  for (let bar = Math.floor(first / 4) * 4; bar <= last + EPS; bar += 4) {
    if (!times.some(h => h.beat >= bar - EPS && h.beat < bar + 4 - EPS)) continue;
    put(bar, T.CENTER, colAt(bar) + FADE);
    if (bar % 8 === 0) put(bar, T.RROT, 0);
  }

  // 5. 数の保証（R10.A）: 数に入るライトが曲の長さ×1.2個に届くまで、RINGSのフェードで足りない拍を埋める
  //    ①数に入るライトが1つも無い拍 → ②RINGSがまだ無い拍 → ③半拍の位置、の順に足す
  const isCounted = e => counted.includes(e.et);
  let count = [...out.values()].filter(isCounted).length;
  const target = Math.ceil(endBeat * DENSITY_TARGET);
  const fillType = has(T.RINGS) ? T.RINGS : T.CENTER;
  if (count < target) {
    const occupied = new Set([...out.values()].filter(isCounted).map(e => Math.floor(e.beat + EPS)));
    for (let b = 0; b < endBeat - EPS && count < target; b++)
      if (!occupied.has(b) && put(b, fillType, colAt(b) + FADE)) count++;
  }
  for (let b = 0; b < endBeat - EPS && count < target; b++) if (put(b, fillType, colAt(b) + FADE)) count++;
  for (let b = 0.5; b < endBeat - EPS && count < target; b++) if (put(b, fillType, colAt(b) + FADE)) count++;

  const events = [...out.values()].sort((a, b) => a.beat - b.beat || a.et - b.et);
  return { events, counted: count, perBeat: count / endBeat, endBeat };
}

/**
 * 確認ダイアログ。plan = {source, sourceNotes, targets[], env, endBeat, result} / 決定でonOk()
 * 見た目は未保存確認(#dirtyDlg)と同じ部品を使う
 */
export function showAutoLightDialog({ t, tf, plan, onOk }) {
  const bg = document.createElement('div'); bg.id = 'dirtyDlgBg';
  const dlg = document.createElement('div'); dlg.id = 'dirtyDlg'; bg.appendChild(dlg);
  const head = document.createElement('div'); head.className = 'ddMsg';
  head.style.fontWeight = '700';
  head.textContent = t('al.title', '自動ライティング');
  const msg = document.createElement('div'); msg.className = 'ddMsg';
  msg.textContent = tf('al.body',
    '元にする難易度: {src}（ノーツ {notes}個）\n追加する難易度: {targets}\n環境: {env}\n曲の長さ: {beats}拍 → ライト {n}個（数に入るもの 1拍あたり {per}個）\n\n'
    + 'ライトのレーンを一番上に1本追加し、各難易度に「自動ライト」クリップを置きます。今あるライトはそのまま残ります。'
    + '重なる所は、どちらかのレーンを消すかミュートして選んでください。',
    { src: plan.source, notes: plan.sourceNotes, targets: plan.targets.join(' / '), env: plan.env.replace(/Environment$/, ''),
      beats: Math.round(plan.result.endBeat * 10) / 10, n: plan.result.events.length, per: plan.result.perBeat.toFixed(2) });
  dlg.append(head, msg);
  const row = document.createElement('div'); row.className = 'ddBtns'; dlg.appendChild(row);
  const done = ok => { removeEventListener('keydown', onKey, true); bg.remove(); if (ok) onOk(); };
  const mk = (label, cls, fn) => { const b = document.createElement('button'); b.textContent = label; if (cls) b.className = cls; b.addEventListener('click', fn); row.appendChild(b); return b; };
  const bOk = mk(t('al.create', '作成'), 'pri', () => done(true));
  mk(t('word.cancel', 'キャンセル'), '', () => done(false));
  const onKey = e => {
    if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); done(false); }
    else if (e.key === 'Enter') { e.preventDefault(); e.stopPropagation(); done(true); }
    else e.stopPropagation();   // 裏のショートカットを発火させない
  };
  addEventListener('keydown', onKey, true);
  document.body.appendChild(bg); bOk.focus();
}

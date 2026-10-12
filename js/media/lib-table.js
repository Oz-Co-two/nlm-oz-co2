// MEDIA ライブラリの詳細表示（2026-10-12）: 1行＝1難易度の表・列の表示と並べ替え・選択・画面に見えている行だけを描く（仮想スクロール）。
// 一覧の中身（絞り込み・並べ替えの結果）はグリッドの並びにも使う（refresh → グリッドの各カードを「並べた一覧で最初に出てくる行」の順に）。
//
// 次の担当が足しやすいように:
//  - セルの描き方は renderCell（1か所）。ネットの値の列で「全曲データに無い曲（net.src==='none'）」は netMissingCell に来る＝🔍のボタンはここへ。
//  - 選択は selectedRows()（並んでいる順・{libId, rel, key, char, diff, name, native}）。
//  - 値の取り出しは rowVal（絞り込み lib-filter.js と共通）。
// 行の値は item.entry（走査の MapEntry。media_library.py）と item.extra（/__lib/extra の {net, play, est}）から読む。
// セルの中のボタン（🔍 など）は class="ltBtn" と data-act を付ける。押しても行の選択・ドラッグにはならず、api.onCellButton(行, act) に来る
// （行の要素は見えている分を使い回して描き直すので、ボタンに直接ではなく表でまとめて受ける）。
// 列の幅は一覧の全部の行の中身と見出しの各段から測る（measureWidths・列の定義の mw）。見出しは訳の改行（lib.h.*）で2段に折る。
// 大きさのスライダー（#libSize）は兼用: グリッドの時はサムネイルの大きさ（bsnm_libsz）、詳細の時は一覧の文字の大きさ（bsnm_libFont・Ctrl＋ホイールでも）。

import { cssZoom } from './lib-layout.js';

export const DIFF_ORDER = ['Easy', 'Normal', 'Hard', 'Expert', 'ExpertPlus'];
export const DIFF_SHORT = { Easy: 'E', Normal: 'N', Hard: 'H', Expert: 'Ex', ExpertPlus: 'E+' };
// モード（characteristic）の表示名。キーは lib.char.<名前>
export const CHAR_NAMES = { Standard: 'Standard', OneSaber: '1本', NoArrows: '矢印なし', '360Degree': '360°', '90Degree': '90°',
  Lawless: 'Lawless', Lightshow: 'ライトショー', Legacy: 'Legacy' };
const CHAR_RANK = Object.keys(CHAR_NAMES);
export function charName(c, t) { return CHAR_NAMES[c] ? t('lib.char.' + c, CHAR_NAMES[c]) : String(c || '').slice(0, 40); }
const MOD_NAMES = { chroma: 'Chroma', noodle: 'Noodle', me: 'ME', cinema: 'Cinema', vivify: 'Vivify' };
const FALLBACK_NJS = { ExpertPlus: 16, Expert: 12, Hard: 10, Normal: 10, Easy: 10 };   // NJS が 0・無しの時にゲームが使う値（mapcheck.js と同じ）

// ---------------------------------------------------------------- 行の値
const num = v => (typeof v === 'number' && isFinite(v)) ? v : null;
const ent = r => r.item.entry || null;
/** ネットの情報（全曲データ・BeatSaver）。無い・src:none は null */
const net = r => { const n = r.item.extra && r.item.extra.net; return n && (n.src === 'dump' || n.src === 'beatsaver') ? n : null; };
const netD = r => { const n = net(r); return (n && n.diffs && n.diffs[r.key]) || null; };
const play = r => (r.item.extra && r.item.extra.play) || null;
const playD = r => { const p = play(r); return (p && p.diffs && p.diffs[r.key]) || null; };
const est = r => { const e = r.item.extra && r.item.extra.est; return (e && e.diffs && e.diffs[r.key]) || null; };
const netNone = r => !!(r.item.entry && r.item.extra && r.item.extra.net && r.item.extra.net.src === 'none');
/** その行に★がある（公式の BL★、または曲に NLM推定の記録がある）。★のまとめての計算の対象から外す。
 * failedOk: 前に計算に失敗した曲は「無い」とみなす（選んだ行の計算でやり直せるように） */
export function rowHasStars(r, failedOk) {
  const d = netD(r); if (d && d.bl > 0) return true;
  const e = r.item.extra && r.item.extra.est;
  return !!(e && !(failedOk && e.failed));
}

/** 反応時間・ジャンプ距離: Beat Saber の BeatmapObjectSpawnMovementData と同じ式（Kival Evan の bsmap の NoteJumpSpeed。
 * このリポジトリの mapcheck.js の NoteJumpSpeed・editor-app.js の jdInfoCur と同じ）。半分の飛来の拍 hjd は 4 から始め、
 * NJS×(60/BPM)×hjd が 17.999 を超える間は半分にし、1 未満なら 1、オフセットを足して 0.25 以上。
 * ジャンプ距離＝NJS×(60/BPM)×hjd×2（m）、反応時間＝(60/BPM)×hjd（秒） */
export function jdrt(njs, offset, bpm, diff) {
  bpm = num(bpm); if (!bpm || bpm <= 0) return null;
  let v = num(njs); if (!v || v <= 0) v = FALLBACK_NJS[diff] || 10;
  const spb = 60 / bpm; let hjd = 4;
  while (v * spb * hjd > 17.999) hjd /= 2;
  if (hjd < 1) hjd = 1;
  hjd = Math.max(hjd + (num(offset) || 0), 0.25);
  return { jd: v * spb * hjd * 2, rt: spb * hjd };
}

export const rowVal = {
  /** ★: 公式の BL★（全曲データ・BeatSaver。版が一致した時だけある）が無ければ NLM推定。どちらも無ければ null */
  stars: r => { const d = netD(r); if (d && d.bl > 0) return d.bl; const e = est(r); return e ? num(e.stars) : null; },
  len: r => { const e = ent(r); return e ? num(e.durationSec) : null; },
  njs: r => r.d ? num(r.d.njs) : null,
  nps: r => r.d ? num(r.d.nps) : null,
  bpm: r => { const e = ent(r); return e ? num(e.bpm) : null; },
  uploaded: r => { const n = net(r); return n && n.uploaded > 0 ? n.uploaded : null; },
  /** BeatLeader でランクの付いた難易度か（曲がランク済み＋その難易度に BL★がある） */
  blRanked: r => { const n = net(r), d = netD(r); return !!(n && n.ranked && n.ranked.bl && d && d.bl > 0); },
  fav: r => !!(play(r) && play(r).fav),
  plays: r => { const p = playD(r); return p ? num(p.plays) : null; },
};

// ---------------------------------------------------------------- 表示の小物
const pad = n => String(n).padStart(2, '0');
const fmtDate = s => { if (!(s > 0)) return ''; const d = new Date(s * 1000); return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`; };
const fmtLen = s => { if (s == null) return ''; s = Math.round(s); return `${Math.floor(s / 60)}:${pad(s % 60)}`; };
const fmtNum = (v, nd) => v == null ? '' : String(+v.toFixed(nd));
// 整数の3桁区切り。書式の部品は1つを使い回す（toLocaleString を行ごとに呼ぶと、4000行の列の幅の測り直しで約50ms/列かかった）
const NF_INT = new Intl.NumberFormat('en-US', { maximumFractionDigits: 0 });
const fmtInt = v => v == null ? '' : NF_INT.format(Math.round(v));
const envName = s => String(s || '').replace(/Environment$/, '').slice(0, 60);
const span = (cls, text) => { const s = document.createElement('span'); if (cls) s.className = cls; s.textContent = text; return s; };

// ---------------------------------------------------------------- 列
// get(row) = 並べ替えの値（数・文字・null）。cell(row, td, ctx) = 描き方（無ければ fmt(get) を文字で）。net:true = ネットの値の列
// （全曲データに無い曲は netMissingCell）。def = 初めから表示する列。hl = 見出しの文字（改行で2段に折る。無ければ label）
// 列の幅（2026-10-12）: 「一覧の全部の行の中身」と「見出しの各段」の両方が切れずに入る幅に測る（measureWidths）。
//   mw(row, M) = その行のセルの中身の幅（px。cell で描く列は描き方と合わせて書く。無ければ fmt(get) の文字の幅）。
//   max = 列の幅の上限（11.5px の時の px。文字の大きさに合わせて伸ばす）。長い名前の入る列（アーティスト・マッパー・環境・Mod・フォルダ名・タグ）は
//     全部の行を測って一番長い値に合わせるが、この上限で止め、はみ出す文字は…で省略する（全文はツールチップ）。短い値しか無ければ詰まる。
//   fixed:true = 測らない列（カバー・曲名）。flex = 残りの幅を全部使う列（曲名）
//   セルの描き方を変えたら mw も合わせること（合わないと文字が…で切れる・列が空いて見える）
function makeCols(ctx) {
  const { t, tf } = ctx;
  /** ランク状態の列の文字（BL / SS / BL候補 …・未ランク）。全曲データの値が無ければ null */
  const rankedText = r => { const n = net(r); if (!n || !n.ranked) return null; const d = netD(r) || {}, out = [];
    if (n.ranked.bl && d.bl > 0) out.push(t('lib.rk.bl', 'BL')); else if (n.ranked.blq && d.bl > 0) out.push(t('lib.rk.blq', 'BL候補'));
    if (n.ranked.ss && d.ss > 0) out.push(t('lib.rk.ss', 'SS')); else if (n.ranked.ssq && d.ss > 0) out.push(t('lib.rk.ssq', 'SS候補'));
    return out.length ? out.join(' / ') : t('lib.rk.none', '未ランク'); };
  return [
    { id: 'cover', w: 28, fixed: true, label: ['lib.c.cover', ''], tip: ['lib.c.coverTip', 'カバー'], def: true, nosort: true,   // 幅は行の高さ＋4px
      cell: (r, td) => { td.classList.add('ltCov'); const u = r.item.coverURL;
        if (u) { const im = document.createElement('img'); im.src = u; im.alt = ''; td.appendChild(im); } else ctx.wantCover(r.item); } },
    { id: 'name', w: 220, flex: true, fixed: true, label: ['lib.c.name', '曲名'], def: true,
      get: r => (ent(r) ? ent(r).name : r.item.name) || '',
      cell: (r, td) => { const e = ent(r);
        td.appendChild(span('ltName', (e ? e.name : r.item.name) || ''));
        if (e && e.subName) td.appendChild(span('ltSub', e.subName));
        if (!e) td.appendChild(span('ltKind', r.item.isClip ? t('lib.kind.clip', 'クリップ') : r.item.isImage ? t('lib.kind.image', '画像') : t('lib.kind.music', '音楽')));
        td.title = (e ? [e.name, e.subName].filter(Boolean).join(' ') : r.item.name) || ''; } },
    { id: 'artist', w: 130, max: 130, label: ['lib.c.artist', 'アーティスト'], def: true, get: r => ent(r) ? ent(r).artist : null },
    { id: 'mapper', w: 120, max: 120, label: ['lib.c.mapper', 'マッパー'], def: true, get: r => ent(r) ? ent(r).mapper : null },
    { id: 'diff', w: 92, label: ['lib.c.diff', '難易度'], def: true,
      get: r => r.d ? (DIFF_ORDER.indexOf(r.d.diff) + 1) * 100 + Math.max(0, CHAR_RANK.indexOf(r.d.char)) : null,
      cell: (r, td) => { if (!r.d) return;
        const known = !!DIFF_SHORT[r.d.diff];
        td.appendChild(span('ltDiff ltDiff_' + (known ? r.d.diff : 'X'), known ? DIFF_SHORT[r.d.diff] : String(r.d.diff).slice(0, 12)));
        if (r.d.char !== 'Standard') td.appendChild(span('ltMode', charName(r.d.char, t)));
        td.title = [r.d.label, (r.d.diff === 'ExpertPlus' ? 'Expert+' : r.d.diff) + (r.d.char !== 'Standard' ? ' / ' + charName(r.d.char, t) : '')].filter(Boolean).join(' — '); },
      // 印（太字・左右 3px・最小は文字の大きさの1.9倍＝CSS の .ltDiff）＋モード名（左 4px）
      mw: (r, M) => { if (!r.d) return 0; const known = !!DIFF_SHORT[r.d.diff];
        let w = Math.max(M.fs * 1.9, M.b(known ? DIFF_SHORT[r.d.diff] : String(r.d.diff).slice(0, 12)) + 6);
        if (r.d.char !== 'Standard') w += 4 + M.s(charName(r.d.char, t));
        return w; } },
    { id: 'stars', w: 104, align: 'r', label: ['lib.c.stars', '★'], tip: ['lib.c.starsTip', 'BeatLeader の★（無ければ NLM推定）'], ml: ['lib.m.stars', '★（BL／NLM推定）'], def: true, get: rowVal.stars,
      cell: (r, td) => {
        const d = netD(r), e = est(r);
        if (d && d.bl > 0) { td.textContent = d.bl.toFixed(2); td.title = t('lib.tip.blStar', 'BeatLeader の★'); return; }
        if (e && num(e.stars) != null) {
          td.classList.add('ltEst');
          td.textContent = tf('lib.estStar', 'NLM推定 {v}', { v: e.stars.toFixed(2) });
          td.title = t('lib.tip.est', 'NLM の独自計算による近似値（BeatLeader の公式の★ではありません）');
          return;
        }
        if (e && e.skipped) { td.textContent = '–'; td.title = e.skipped === 'tooFewNotes' ? t('lib.tip.tooFew', 'ノーツが20個未満のため、★は計算していません') : String(e.skipped).slice(0, 80); return; }
        if (e && e.error) { td.textContent = '–'; td.title = tf('lib.tip.estErr', '★の計算に失敗しました: {err}', { err: String(e.error).slice(0, 200) }); return; }
        if (r.d && ctx.starBusy && ctx.starBusy(r)) {   // ★のまとめての計算で、今この曲を計算している
          td.classList.add('ltEst', 'ltBusy'); td.textContent = t('lib.estBusy', '計算中…'); td.title = t('lib.tip.estBusy', 'NLM推定の★を計算しています'); return;
        }
        if (r.d && r.item.extra && r.item.extra.est) td.title = t('lib.tip.estNone', 'NLM推定の★はありません（この難易度は計算の結果に含まれていませんでした）');
        if (netNone(r)) netMissingCell(r, td, ctx, 'stars');
      },
      mw: (r, M) => {   // 上の cell と同じ順で、出す文字の幅
        const d = netD(r), e = est(r);
        if (d && d.bl > 0) return M.n(d.bl.toFixed(2));
        if (e && num(e.stars) != null) return M.n(tf('lib.estStar', 'NLM推定 {v}', { v: e.stars.toFixed(2) }));
        if (e && (e.skipped || e.error)) return M.t('–');
        if (r.d && ctx.starBusy && ctx.starBusy(r)) return M.t(t('lib.estBusy', '計算中…'));
        return netNone(r) ? M.miss(r, 'stars') : 0;
      } },
    { id: 'njs', w: 52, align: 'r', label: ['lib.c.njs', 'NJS'], def: true, get: rowVal.njs, fmt: v => fmtNum(v, 2) },
    { id: 'nps', w: 52, align: 'r', label: ['lib.c.nps', 'NPS'], def: true, get: rowVal.nps, fmt: v => fmtNum(v, 2) },
    { id: 'len', w: 54, align: 'r', label: ['lib.c.len', '長さ'], tip: ['lib.c.lenTip', '音源の長さ'], def: true, get: rowVal.len, fmt: fmtLen },
    { id: 'bpm', w: 56, align: 'r', label: ['lib.c.bpm', 'BPM'], def: true, get: rowVal.bpm, fmt: v => fmtNum(v, 2) },
    { id: 'uploaded', w: 86, label: ['lib.c.uploaded', 'アップロード日'], hl: ['lib.h.uploaded', 'アップロード\n日'], def: true, net: true, get: rowVal.uploaded, fmt: fmtDate },
    { id: 'dl', w: 86, label: ['lib.c.dl', 'ダウンロード日'], hl: ['lib.h.dl', 'ダウンロード\n日'], tip: ['lib.c.dlTip', 'ダウンロード日（Mod の記録。無ければフォルダの日付からの推定）'], def: true,
      get: r => ent(r) && ent(r).dlTime > 0 ? ent(r).dlTime : null, fmt: fmtDate },
    { id: 'plays', w: 50, align: 'r', label: ['lib.c.plays', 'プレイ'], hl: ['lib.h.plays', 'プレイ\n回数'], tip: ['lib.c.playsTip', 'プレイ回数（その難易度）'], def: true,
      get: r => { const v = rowVal.plays(r); return v != null ? v : (r.d && ctx.playOk() && r.item.extra ? 0 : null); }, fmt: v => v ? String(v) : '' },
    // ---- 初めは隠す列 ----
    { id: 'key', w: 60, label: ['lib.c.key', 'キー'], tip: ['lib.c.keyTip', 'BeatSaver のキー'], get: r => { const e = ent(r), n = net(r); return (e && e.key) || (n && n.key) || null; } },
    { id: 'rating', w: 64, align: 'r', label: ['lib.c.rating', '高評価率'], hl: ['lib.h.rating', '高評価\n率'], net: true,
      get: r => { const n = net(r); return n && (n.up + n.down) > 0 ? n.up / (n.up + n.down) * 100 : null; },
      cell: (r, td, c) => { const v = c.get(r); if (v == null) return; const n = net(r);
        td.textContent = v.toFixed(1) + '%'; td.title = tf('lib.tip.votes', '高評価 {up}・低評価 {down}', { up: n.up, down: n.down }); },
      mw: (r, M, c) => { const v = c.get(r); return v == null ? 0 : M.n(v.toFixed(1) + '%'); } },
    { id: 'ranked', w: 84, label: ['lib.c.ranked', 'ランク状態'], hl: ['lib.h.ranked', 'ランク\n状態'], net: true,
      get: r => { const n = net(r); if (!n || !n.ranked) return null; const d = netD(r) || {};
        return n.ranked.bl && d.bl > 0 ? 4 : n.ranked.blq && d.bl > 0 ? 3 : n.ranked.ss && d.ss > 0 ? 2 : n.ranked.ssq && d.ss > 0 ? 1 : 0; },
      cell: (r, td) => { const s = rankedText(r); if (s != null) td.textContent = s; },
      mw: (r, M) => { const s = rankedText(r); return s ? M.t(s) : 0; } },
    { id: 'notes', w: 58, align: 'r', label: ['lib.c.notes', 'ノーツ'], hl: ['lib.h.notes', 'ノーツ\n数'], get: r => r.d ? num(r.d.notes) : null, fmt: fmtInt },
    { id: 'bombs', w: 52, align: 'r', label: ['lib.c.bombs', 'ボム'], get: r => r.d ? num(r.d.bombs) : null, fmt: fmtInt },
    { id: 'walls', w: 52, align: 'r', label: ['lib.c.walls', '壁'], get: r => r.d ? num(r.d.walls) : null, fmt: fmtInt },
    { id: 'env', w: 110, max: 110, label: ['lib.c.env', '環境'], get: r => ent(r) && ent(r).env ? envName(ent(r).env) : null },
    { id: 'mods', w: 110, max: 200, label: ['lib.c.mods', '必要な Mod'], hl: ['lib.h.mods', '必要な\nMod'],
      get: r => r.d && (r.d.req || []).length ? r.d.req.map(m => MOD_NAMES[m] || m).join(', ') : null,
      cell: (r, td, c) => { if (!r.d) return; td.textContent = c.get(r) || '';
        const sug = (r.d.mods || []).filter(m => !(r.d.req || []).includes(m));
        if ((r.d.req || []).length || sug.length) td.title = tf('lib.tip.mods', '必要: {req}／推奨: {sug}',
          { req: (r.d.req || []).map(m => MOD_NAMES[m] || m).join(', ') || '–', sug: sug.map(m => MOD_NAMES[m] || m).join(', ') || '–' }); },
      mw: (r, M, c) => { const s = r.d ? c.get(r) : null; return s ? M.t(s) : 0; } },
    { id: 'best', w: 100, align: 'r', label: ['lib.c.best', '自己ベスト'], hl: ['lib.h.best', '自己\nベスト'],
      get: r => { const p = playD(r); return p ? num(p.best) : null; },
      cell: (r, td) => { const p = playD(r); if (!p || p.best == null) return; td.textContent = fmtInt(p.best) + (p.rank ? ' (' + String(p.rank).slice(0, 4) + ')' : ''); },
      mw: (r, M) => { const p = playD(r); return !p || p.best == null ? 0 : M.n(fmtInt(p.best) + (p.rank ? ' (' + String(p.rank).slice(0, 4) + ')' : '')); } },
    { id: 'fc', w: 40, align: 'c', label: ['lib.c.fc', 'FC'], tip: ['lib.c.fcTip', 'フルコンボ'], ml: ['lib.m.fc', 'フルコンボ（FC）'],
      get: r => { const p = playD(r); return p ? (p.fc ? 1 : 0) : null; }, fmt: v => v ? '✓' : '' },
    { id: 'fav', w: 40, align: 'c', label: ['lib.c.fav', '♥'], tip: ['lib.c.favTip', 'お気に入り'], ml: ['lib.m.fav', 'お気に入り（♥）'],
      get: r => r.item.entry && r.item.extra ? (rowVal.fav(r) ? 1 : 0) : null, fmt: v => v ? '♥' : '' },
    { id: 'folder', w: 180, max: 180, label: ['lib.c.folder', 'フォルダ名'], get: r => { const rel = r.item.rel || (r.item.dir && r.item.dir.name) || ''; return rel ? rel.split('/').pop() : null; } },
    { id: 'ss', w: 56, align: 'r', label: ['lib.c.ss', 'SS★'], tip: ['lib.c.ssTip', 'ScoreSaber の★'], net: true, get: r => { const d = netD(r); return d && d.ss > 0 ? d.ss : null; }, fmt: v => v == null ? '' : v.toFixed(2) },
    { id: 'tags', w: 140, max: 140, label: ['lib.c.tags', 'タグ'], net: true, get: r => { const n = net(r); return n && (n.tags || []).length ? n.tags.join(', ') : null; } },
    { id: 'rt', w: 60, align: 'r', label: ['lib.c.rt', '反応時間'], hl: ['lib.h.rt', '反応\n時間'], tip: ['lib.c.rtTip', '反応時間（ms。NJS・オフセット・BPM から計算）'],
      get: r => { if (!r.d || !ent(r)) return null; const j = jdrt(r.d.njs, r.d.offset, ent(r).bpm, r.d.diff); return j ? Math.round(j.rt * 1000) : null; },
      fmt: v => v == null ? '' : v + 'ms' },
    { id: 'jd', w: 60, align: 'r', label: ['lib.c.jd', 'JD'], hl: ['lib.h.jd', 'ジャンプ\n距離'], tip: ['lib.c.jdTip', 'ジャンプ距離（m。NJS・オフセット・BPM から計算）'], ml: ['lib.m.jd', 'ジャンプ距離（JD）'],
      get: r => { if (!r.d || !ent(r)) return null; const j = jdrt(r.d.njs, r.d.offset, ent(r).bpm, r.d.diff); return j ? j.jd : null; },
      fmt: v => v == null ? '' : v.toFixed(1) + 'm' },
  ];
}

// 全曲データに無い曲の「未照合 🔍」を出す列の優先順（表示中の列のうち最初の物に1つだけ出す。普段はアップロード日）
const MISS_COLS = ['uploaded', 'stars', 'rating', 'ranked', 'ss', 'tags'];

/** 全曲データに無い曲のネットの値の列。表示中の列のうち MISS_COLS で最初の列にだけ ctx.netMissing（🔍）を描く。他の列は空欄 */
export function netMissingCell(row, td, ctx, colId) {
  if (!ctx || typeof ctx.netMissing !== 'function') return;
  const shown = typeof ctx.cols === 'function' ? ctx.cols() : MISS_COLS;
  if (colId !== MISS_COLS.find(c => shown.includes(c))) return;
  ctx.netMissing(row, td);
}

/** セルの描き方（1か所）。td は空にしてから渡す */
export function renderCell(col, row, td, ctx) {
  td.className = 'ltC' + (col.align ? ' lt_' + col.align : '');
  if (col.net && netNone(row)) { netMissingCell(row, td, ctx, col.id); return; }
  if (col.cell) col.cell(row, td, col);
  else {
    const v = col.get ? col.get(row) : null;
    td.textContent = col.fmt ? col.fmt(v) : (v == null ? '' : String(v));
    if (col.max && td.textContent) td.title = td.textContent;   // 幅に上限のある列（長い名前）は…で切れることがある＝全文はツールチップ
  }
  // 🔍 で BeatSaver から直接取った曲は、ネットの値にその旨（全曲データの値と見分けられるように）
  const n = net(row);
  if (n && n.src === 'beatsaver' && td.textContent && (col.net || (col.id === 'stars' && netD(row) && netD(row).bl > 0))) {
    const s = ctx && ctx.t ? ctx.t('lib.tip.fromBs', 'BeatSaver から取得') : 'BeatSaver';
    td.title = td.title ? td.title + '\n' + s : s;
  }
}

// ---------------------------------------------------------------- 列の幅を測る（2026-10-12）
/** 文字の幅を測る部品（canvas の measureText）。同じ字形・同じ文字は1回だけ測って覚える（4000行でも数十ms に収める） */
function makeTextMeasurer() {
  const g = document.createElement('canvas').getContext('2d');
  const caches = new Map();
  let cur = '';
  return {
    w(text, font) {
      let c = caches.get(font); if (!c) { c = new Map(); caches.set(font, c); }
      let v = c.get(text);
      if (v === undefined) { if (cur !== font) { g.font = font; cur = font; } v = g.measureText(text).width; c.set(text, v); }
      return v;
    },
    /** 字形の読み込みが終わった時など: 覚えた幅を捨てる */
    reset() { caches.clear(); cur = ''; },
  };
}
/** 一覧の文字の大きさ fs（px）の時の、各部の字形での幅（mw に渡す M）。数字の列は数字を一番幅の広い数字に置き換えて測る
 * （字形の数字の幅がそろっていなくても切れないように・同じ形の値をまとめて1回で測れるように）。
 * z＝UI文字サイズ（環境設定の bsnm_uiscale。#tabFolder の CSS の zoom）: 画面に実際に描く大きさ（fs×z）で測って z で割り、CSS の px で返す
 * （小さい字は字形の幅の丸めが大きさにきっちり比例するとは限らないため、実際に描く大きさで測る） */
function textMetrics(T, family, fs, z) {
  z = z > 0 ? z : 1;
  const px = v => `${Math.round(v * z * 100) / 100}px ${family}`;
  const F = { t: px(fs), b: '700 ' + px(fs - 1), s: px(fs - 1), h: px(fs - 0.5) };
  let wd = '0', ww = -1;
  for (const ch of '0123456789') { const x = T.w(ch, F.t); if (x > ww) { ww = x; wd = ch; } }
  const ND = /\d/g;
  return {
    fs,
    t: s => T.w(s, F.t) / z,                       // セルの文字
    n: s => T.w(String(s).replace(ND, wd), F.t) / z, // 数字を含むセルの文字（右寄せの列など）
    b: s => T.w(s, F.b) / z,                       // 難易度の印（太字・1px 小さい）
    s: s => T.w(s, F.s) / z,                       // モード名・🔍 のボタン（1px 小さい）
    h: s => T.w(s, F.h) / z,                       // 見出し（0.5px 小さい）
    arrow: T.w('▲', px(9)) / z + 3,                // 並べ替えの印（見出しの文字の右・間 3px）
  };
}

// ---------------------------------------------------------------- 本体
// 一覧の文字の大きさ（詳細表示。大きさのスライダー・Ctrl＋ホイール）。保存は bsnm_libFont（無ければ FONT_DEF）
export const FONT_MIN = 11, FONT_MAX = 18, FONT_DEF = 13;
/** 文字の大きさ fs の時の1行の高さ（px。仮想スクロールの計算と CSS の --lt-rh） */
export const rowHeightOf = fs => Math.round(fs * 1.7 + 4);
const LS_VIEW = 'bsnm_libView', LS_COLS = 'bsnm_libCols', LS_SORT = 'bsnm_libSort', LS_FONT = 'bsnm_libFont', LS_GRID = 'bsnm_libsz';
const lsGet = k => { try { return localStorage.getItem(k); } catch (_) { return null; } };
const lsSet = (k, v) => { try { if (v == null) localStorage.removeItem(k); else localStorage.setItem(k, v); } catch (_) {} };

export function installLibTable(api) {
  const { t, tf } = api;
  const ctx = { t, tf, wantCover: it => api.wantCover(it), playOk: () => api.playOk(), netMissing: api.netMissing, netMissingText: api.netMissingText,
    starBusy: api.starBusy, cols: () => cols };
  const COLS = makeCols(ctx), byId = Object.fromEntries(COLS.map(c => [c.id, c]));
  const coll = new Intl.Collator(undefined, { numeric: true, sensitivity: 'base' });
  const $ = id => document.getElementById(id);
  const grid = $('libGrid'), tbl = $('libTable');

  let mode = lsGet(LS_VIEW) === 'detail' ? 'detail' : 'grid';
  let cols = (() => { try { const a = JSON.parse(lsGet(LS_COLS) || 'null'); if (Array.isArray(a)) { const s = new Set(a); const v = COLS.filter(c => s.has(c.id)).map(c => c.id); if (v.length) return v; } } catch (_) {} return COLS.filter(c => c.def).map(c => c.id); })();
  if (!cols.includes('name')) cols.splice(Math.min(1, cols.length), 0, 'name');   // 曲名の列は隠さない
  let sort = (() => { try { const s = JSON.parse(lsGet(LS_SORT) || 'null'); if (s && byId[s.col] && !byId[s.col].nosort && (s.dir === 1 || s.dir === -1)) return s; } catch (_) {} return null; })();
  // 文字の大きさ（詳細表示）とサムネイルの大きさ（グリッド。4＝6列〜8＝2列）
  let fontPx = (() => { const v = +lsGet(LS_FONT); return v >= FONT_MIN && v <= FONT_MAX ? Math.round(v) : FONT_DEF; })();
  let gridSz = (() => { const v = +lsGet(LS_GRID); return v >= 4 && v <= 8 ? Math.round(v) : 5; })();
  let RH = rowHeightOf(fontPx);   // 1行の高さ（px）。CSS の --lt-rh と同じ
  let view = { rows: [], counts: { songs: 0, rows: 0, total: 0 } };
  let selected = new Set(), anchor = null, ver = 0, gridOrder = [], dragging = false;
  let uid = 0;

  // ---- 行 ----
  function rowsOf(it) {
    if (it._rows && it._rowsOf === it.entry) return it._rows;
    if (!it._uid) it._uid = ++uid;
    const e = it.entry, out = [];
    if (e && (e.diffs || []).length) for (const d of e.diffs) { const key = d.char + '/' + d.diff; out.push({ id: it._uid + '|' + key, item: it, d, key }); }
    else out.push({ id: it._uid + '|', item: it, d: null, key: '' });
    it._rows = out; it._rowsOf = e;
    return out;
  }

  // ---- 一覧を作る（絞り込み → 並べ替え）----
  function compute() {
    const F = api.filter(), condOn = F.condActive(), items = api.items();
    const rows = []; let total = 0, songs = 0, nrows = 0;
    for (const it of items) {
      it._vrows = null;
      if (it.entry) {
        total++;
        if (!F.matchText(it)) continue;
        const all = rowsOf(it);
        const rs = all[0].d ? all.filter(F.rowMatches) : (condOn ? [] : all);   // 難易度の無い曲は、条件で絞っていない時だけ1行で出す
        if (!rs.length) continue;
        it._vrows = rs; songs++; if (rs[0].d) nrows += rs.length;
        for (const r of rs) rows.push(r);
      } else {
        if (condOn) continue;   // 曲の条件で絞り込んでいる間は、曲以外（音楽・画像・クリップ）を隠す
        if (!F.matchText(it)) continue;
        const r = rowsOf(it)[0]; it._vrows = [r]; rows.push(r);
      }
    }
    if (sort) {
      const c = byId[sort.col], dir = sort.dir;
      const k = rows.map((r, i) => { let v = c.get ? c.get(r) : null; if (v === '' || (typeof v === 'number' && !isFinite(v))) v = null; return { r, i, v }; });
      k.sort((a, b) => {
        const an = a.v == null, bn = b.v == null;
        if (an || bn) return an && bn ? a.i - b.i : an ? 1 : -1;   // 値の無い行は、どちら向きでも一番下
        const x = typeof a.v === 'string' || typeof b.v === 'string' ? coll.compare(String(a.v), String(b.v)) : a.v - b.v;
        return x ? x * dir : a.i - b.i;
      });
      for (let i = 0; i < k.length; i++) rows[i] = k[i].r;
    }
    view = { rows, counts: { songs, rows: nrows, total, scan: api.scanState ? api.scanState() : null } };
    const ids = new Set(rows.map(r => r.id));
    for (const id of [...selected]) if (!ids.has(id)) selected.delete(id);
  }

  // ---- グリッドの並び: 各カードを「並べた一覧で最初に出てくる行」の順に。出てこないカードは隠す ----
  function orderGrid() {
    const order = [], seen = new Set();
    for (const r of view.rows) if (!seen.has(r.item)) { seen.add(r.item); if (r.item._el) order.push(r.item._el); }
    for (const el of grid.children) { const on = seen.has(el._item); el.style.display = on ? '' : 'none'; }
    // カードの名前の入力中（アセットの改名）は動かさない: 要素を動かすと入力欄のフォーカスが外れ、改名が途中で確定してしまう
    const ae = document.activeElement;
    if (ae && ae !== document.body && grid.contains(ae)) { gridOrder = []; ae.addEventListener('blur', () => refreshSoon(), { once: true }); return; }
    const same = order.length === gridOrder.length && order.every((e, i) => e === gridOrder[i]);
    if (same) return;
    // 並びの違うカードだけを動かす（全部を入れ直すと、新しい曲が届くたびに全部のカードが作り直しの扱いになる）
    let ref = grid.firstChild;
    for (const el of order) {
      if (el === ref) { ref = ref.nextSibling; continue; }
      grid.insertBefore(el, ref);
    }
    gridOrder = order;
  }

  // ---- 列の幅: 一覧の全部の行（見えている行だけでなく）の中身と、見出しの各段の両方が切れずに入る幅 ----
  // 値・言語・文字の大きさ・列の表示・並べ替えの印が変わったら測り直す（measureSoon。グリッドの間は測らず、詳細表示へ切り替えた時に測る）
  const TM = makeTextMeasurer();
  let widths = null, widthsFor = '', widthsDirty = true, measureT = null, lastMeasure = { ms: 0, rows: 0, n: 0, count: 0 }, capped = [];
  /** 見出しの文字の段（訳の改行で2段まで） */
  const headLines = c => String(c.hl ? t(c.hl[0], c.hl[1]) : t(c.label[0], c.label[1])).split('\n').slice(0, 2);
  const scaleW = w => Math.round(w * fontPx / 11.5);   // 測らない列の幅（11.5px の時の幅を元に、文字の大きさに合わせて伸ばす）
  /** 全曲データに無い曲の「未照合 🔍」の幅（表示中の列のうち最初のネットの列にだけ出す＝netMissingCell と同じ）。
   * 出す文字は ctx.netMissingText（lib-online.js。行ごとに DOM を作らない）から。無ければセルを作って読む */
  function missWidth(r, colId, M) {
    if (colId !== M.missCol || typeof ctx.netMissing !== 'function') return 0;
    if (typeof ctx.netMissingText === 'function') { const p = ctx.netMissingText(r); return p ? M.t(p.text) + 4 + M.s(p.btn) + 8 : 0; }
    const td = document.createElement('div'); ctx.netMissing(r, td);
    const tx = td.querySelector('.ltMissT'), b = td.querySelector('.ltBtn');
    return (tx ? M.t(tx.textContent) : 0) + (b ? 4 + M.s(b.textContent) + 8 : 0);   // 文字・間 4px・ボタン（左右 3px と枠）
  }
  function cellWidth(c, r, M) {
    if (c.net && netNone(r)) return M.miss(r, c.id);
    if (c.mw) return c.mw(r, M, c);
    const v = c.get ? c.get(r) : null;
    const s = c.fmt ? c.fmt(v) : (v == null ? '' : String(v));
    return !s ? 0 : c.align ? M.n(s) : M.t(s);
  }
  function measureWidths() {
    clearTimeout(measureT); measureT = null;
    // グリッドの間・MEDIA が隠れている間（PREVIEW）は測らない。詳細表示に切り替えた時・表が見えるようになった時（下の ResizeObserver）に測る
    if (mode !== 'detail' || !tbl.clientWidth) { widthsDirty = true; return; }
    const t0 = performance.now();
    const fam = getComputedStyle(tbl).fontFamily || 'sans-serif';
    const M = textMetrics(TM, fam, fontPx, cssZoom(tbl));
    M.missCol = MISS_COLS.find(c => cols.includes(c));
    M.miss = (r, id) => missWidth(r, id, M);
    const rows = view.rows, out = [], cap = [];
    for (const id of cols) {
      const c = byId[id];
      const hw = Math.max(0, ...headLines(c).map(s => M.h(s))) + (sort && sort.col === id ? M.arrow : 0);
      if (id === 'cover') { out.push(RH + 4); continue; }
      let cw = 0;
      if (c.fixed) cw = scaleW(c.w) - 12;
      else {
        const lim = c.max ? scaleW(c.max) - 12 : Infinity;   // 上限に届いたら残りの行は測らない
        for (let i = 0; i < rows.length && cw < lim; i++) { const x = cellWidth(c, rows[i], M); if (x > cw) cw = x; }
        if (cw >= lim) { cw = lim; cap.push(id); }
      }
      // セルは左右 6px の余白、見出しはそれと右の枠 1px。小数の幅で…が出ないよう 1px 足す
      out.push(Math.ceil(Math.max(cw + 12, hw + 13, 24)) + 1);
    }
    widths = out; widthsFor = cols.join(); widthsDirty = false; capped = cap;
    lastMeasure = { ms: Math.round((performance.now() - t0) * 10) / 10, rows: rows.length, n: out.length, count: lastMeasure.count + 1 };
    applyWidths();
  }
  function measureSoon(ms) {
    widthsDirty = true;
    if (mode !== 'detail' || measureT) return;
    measureT = setTimeout(() => { measureT = null; measureWidths(); }, ms == null ? 120 : ms);
  }
  /** 列 i の幅（測った幅。まだ測っていない・列が変わった後は w を文字の大きさに合わせた仮の幅） */
  const colW = i => widths && widthsFor === cols.join() ? widths[i] : scaleW(byId[cols[i]].w);
  function colTemplate() {
    return cols.map((id, i) => byId[id].flex ? `minmax(${colW(i)}px,1fr)` : colW(i) + 'px').join(' ');
  }
  function applyWidths() {
    const tpl = colTemplate(), w = cols.reduce((s, id, i) => s + colW(i), 0) + 8;
    if (tbl.style.getPropertyValue('--lt-cols') !== tpl) tbl.style.setProperty('--lt-cols', tpl);
    if (tbl.style.getPropertyValue('--lt-w') !== w + 'px') tbl.style.setProperty('--lt-w', w + 'px');
  }
  // 字形（M PLUS Rounded 1c）の読み込みが終わる前に測った幅は代わりの字形の物＝読み込み後に測り直す
  try { document.fonts.addEventListener('loadingdone', () => { TM.reset(); measureSoon(0); }); document.fonts.ready.then(() => { TM.reset(); measureSoon(0); }); } catch (_) {}

  // ---- 文字の大きさ（詳細表示）: 行の高さ・見出しの1段の高さ・カバーの小さい画像・難易度の印は CSS の変数で合わせる ----
  function applyFont() {
    RH = rowHeightOf(fontPx);
    tbl.style.setProperty('--lt-fs', fontPx + 'px');
    tbl.style.setProperty('--lt-rh', RH + 'px');
    tbl.style.setProperty('--lt-hl', Math.round(fontPx * 1.25) + 'px');
  }
  function setFont(v) {
    v = Math.max(FONT_MIN, Math.min(FONT_MAX, Math.round(+v || FONT_DEF)));
    if (v === fontPx) return;
    const top = mode === 'detail' && body ? Math.floor(Math.max(0, tbl.scrollTop) / RH) : 0;   // 一番上に見えていた行を保つ
    fontPx = v; lsSet(LS_FONT, String(v));
    applyFont(); syncSlider();
    if (mode === 'detail' && body) {
      ver++; measureWidths();
      body.style.height = view.rows.length * RH + 'px';
      tbl.scrollTop = top * RH;
      paint();
    } else widthsDirty = true;
  }
  function setGridSize(v) {
    v = Math.max(4, Math.min(8, Math.round(+v || 5)));
    gridSz = v; lsSet(LS_GRID, String(v));
    grid.style.gridTemplateColumns = `repeat(${10 - v},1fr)`;   // 左=6列(小) 右=2列(大)
  }
  grid.style.gridTemplateColumns = `repeat(${10 - gridSz},1fr)`;
  applyFont();

  // ---- 大きさのスライダー（兼用）: グリッドの時はサムネイルの大きさ、詳細の時は一覧の文字の大きさ ----
  const slider = $('libSize'), sizeGrp = $('libSizeGrp');
  function syncSlider() {
    if (!slider) return;
    const det = mode === 'detail';
    slider.min = det ? FONT_MIN : 4; slider.max = det ? FONT_MAX : 8; slider.step = 1;
    slider.value = det ? fontPx : gridSz;
    slider.title = det ? t('lib.fontSize', '文字の大きさ（一覧の上で Ctrl＋ホイールでも変えられます）') : t('ui.thumbSize', 'サムネイルの大きさ');
    slider.setAttribute('aria-label', slider.title);
    // 左の印（グリッド＝画像・詳細＝Aa）で、今どちらの大きさを変えるのかを見せる。印の上でも同じツールチップ
    if (sizeGrp) { sizeGrp.classList.toggle('det', det); sizeGrp.title = slider.title; }
  }
  if (slider) slider.addEventListener('input', () => { if (mode === 'detail') setFont(slider.value); else setGridSize(slider.value); });
  // 詳細表示の上での Ctrl＋ホイール＝文字の大きさ（ページの拡大にしない）。タッチパッドの細かい量はためて 1 段ずつ
  let wheelAcc = 0;
  tbl.addEventListener('wheel', e => {
    if (!e.ctrlKey || mode !== 'detail') return;
    e.preventDefault();
    wheelAcc += e.deltaMode === 0 ? e.deltaY : e.deltaY * 40;
    if (Math.abs(wheelAcc) < 40) return;
    const step = wheelAcc < 0 ? 1 : -1; wheelAcc = 0;
    setFont(fontPx + step);
  }, { passive: false });

  // ---- 表 ----
  let head = null, body = null, pool = [], paintQ = false;
  function buildTable() {
    tbl.innerHTML = '';
    head = document.createElement('div'); head.className = 'ltHead';
    body = document.createElement('div'); body.className = 'ltRows';
    tbl.append(head, body);
    pool = [];
    applyWidths();
    renderHead();
    head.addEventListener('click', e => { const h = e.target.closest('.ltH'); if (!h) return; const c = byId[h.dataset.col]; if (!c || c.nosort) return; setSort(c.id); });
    head.addEventListener('contextmenu', e => { e.preventDefault(); openColMenu(e.clientX, e.clientY); });
    // セルの中のボタン（.ltBtn）: 押しても行の選択・ドラッグにしない。押した時に行が描き直されても受け取れるよう、表でまとめて受ける
    let btnDown = false;
    body.addEventListener('pointerdown', e => { btnDown = !!(e.target.closest && e.target.closest('.ltBtn')); }, true);
    body.addEventListener('click', e => {
      const b = e.target.closest && e.target.closest('.ltBtn');
      if (b) { const el = b.closest('.ltRow'); if (el && el._row && !b.disabled && api.onCellButton) api.onCellButton(el._row, b.dataset.act || ''); return; }
      onRowClick(e);
    });
    body.addEventListener('contextmenu', e => { const el = e.target.closest('.ltRow'); if (!el || !el._row) return; e.preventDefault();
      if (!selected.has(el._row.id)) { selected = new Set([el._row.id]); anchor = el._row.id; paint(true); }
      api.onRowContext(el._row, e); });
    body.addEventListener('dragstart', e => { const el = e.target.closest('.ltRow'); if (!el || !el._row) return;
      if (btnDown) { e.preventDefault(); return; }   // ボタンを押したまま動かした＝ドラッグにしない
      dragging = true; api.onRowDragStart(el._row, el, e); });
    body.addEventListener('dragend', e => { dragging = false; api.onRowDragEnd(e); setTimeout(() => paint(), 0); });
  }
  function renderHead() {
    head.innerHTML = '';
    for (const id of cols) {
      const c = byId[id], h = document.createElement('div');
      h.className = 'ltH' + (c.align ? ' lt_' + c.align : '') + (c.nosort ? ' nosort' : '');
      h.dataset.col = id;
      const hl = document.createElement('span'); hl.className = 'ltHL';   // 段ごとに1つの span（決めた位置で2段に折る）
      for (const s of headLines(c)) hl.appendChild(span('', s));
      h.appendChild(hl);
      if (sort && sort.col === id) h.appendChild(span('ltArrow', sort.dir > 0 ? '▲' : '▼'));
      h.title = c.tip ? t(c.tip[0], c.tip[1]) : t(c.label[0], c.label[1]);
      head.appendChild(h);
    }
  }
  function fillRow(el, r) {
    el._row = r; el._ver = ver;
    el.textContent = '';
    for (const id of cols) { const td = document.createElement('div'); renderCell(byId[id], r, td, ctx); el.appendChild(td); }
  }
  function paint(selOnly) {
    if (mode !== 'detail' || !body) return;
    const n = view.rows.length, hh = head.offsetHeight || RH;
    const st = Math.max(0, tbl.scrollTop - hh), h = Math.max(RH, tbl.clientHeight);
    const first = Math.max(0, Math.floor(st / RH) - 6), last = Math.min(n, Math.ceil((st + h) / RH) + 6);
    const need = Math.max(0, last - first);
    while (pool.length < need) { const el = document.createElement('div'); el.className = 'ltRow'; el.draggable = true; body.appendChild(el); pool.push(el); }
    for (let k = 0; k < pool.length; k++) {
      const el = pool[k];
      if (k >= need) { if (!dragging) el.style.display = 'none'; continue; }
      const i = first + k, r = view.rows[i];
      el.style.display = '';
      if (!selOnly || el._row !== r) { if (el._row !== r || el._ver !== ver) fillRow(el, r); }
      el.style.transform = `translateY(${i * RH}px)`;
      el._i = i;
      el.classList.toggle('sel', selected.has(r.id));
      el.classList.toggle('odd', (i & 1) === 1);
    }
  }
  function paintSoon() { if (paintQ) return; paintQ = true; requestAnimationFrame(() => { paintQ = false; paint(); }); }
  tbl.addEventListener('scroll', paintSoon, { passive: true });
  // 表の大きさが変わった時（MEDIA が隠れている間に一覧・値が変わって測り直しを後に回し、見えるようになった時も）。
  // ResizeObserver は描く前に呼ばれる＝ここで測れば古い幅の画面は出ない
  if (typeof ResizeObserver === 'function') new ResizeObserver(() => { if (widthsDirty && mode === 'detail' && head && tbl.clientWidth) measureWidths(); paintSoon(); }).observe(tbl);

  function renderTable() {
    if (mode !== 'detail') return;
    if (!head) buildTable();
    if (widthsDirty || !widths || widthsFor !== cols.join()) measureWidths();
    body.style.height = view.rows.length * RH + 'px';
    paint();
  }

  // ---- 選択（クリック＝1行、Ctrl＝追加・解除、Shift＝範囲）----
  function onRowClick(e) {
    const el = e.target.closest('.ltRow'); if (!el || !el._row) return;
    const r = el._row, idx = view.rows.indexOf(r);
    if (e.shiftKey && anchor != null) {
      const ai = view.rows.findIndex(x => x.id === anchor);
      const [a, b] = ai < 0 ? [idx, idx] : ai < idx ? [ai, idx] : [idx, ai];
      if (!(e.ctrlKey || e.metaKey)) selected = new Set();
      for (let i = a; i <= b; i++) selected.add(view.rows[i].id);
    } else if (e.ctrlKey || e.metaKey) {
      if (selected.has(r.id)) selected.delete(r.id); else selected.add(r.id);
      anchor = r.id;
    } else { selected = new Set([r.id]); anchor = r.id; }
    paint(true);
    api.onSelect && api.onSelect();
  }

  // ---- 並べ替え・列 ----
  function setSort(id) {
    sort = sort && sort.col === id ? { col: id, dir: -sort.dir } : { col: id, dir: 1 };   // 1回目＝昇順、もう1回＝降順
    lsSet(LS_SORT, JSON.stringify(sort));
    refresh();
  }
  function setCols(list) {
    const s = new Set(list); s.add('name');
    cols = COLS.filter(c => s.has(c.id)).map(c => c.id);
    lsSet(LS_COLS, JSON.stringify(cols));
    head = null; ver++; widthsDirty = true;
    renderTable();
  }
  let colMenu = null;
  function openColMenu(x, y) {
    closeColMenu();
    colMenu = document.createElement('div'); colMenu.id = 'libColMenu';
    for (const c of COLS) {
      if (c.id === 'name') continue;
      const lab = document.createElement('label'); lab.className = 'lcmItem';
      const cb = document.createElement('input'); cb.type = 'checkbox'; cb.checked = cols.includes(c.id); cb.dataset.col = c.id;
      cb.addEventListener('change', () => setCols(cb.checked ? [...cols, c.id] : cols.filter(v => v !== c.id)));
      lab.append(cb, span('', c.ml ? t(c.ml[0], c.ml[1]) : c.label[1] ? t(c.label[0], c.label[1]) : t(c.tip[0], c.tip[1])));   // 記号だけの見出し（★・♥）はメニューでは言葉で
      if (c.tip) lab.title = t(c.tip[0], c.tip[1]);
      colMenu.appendChild(lab);
    }
    const rs = document.createElement('button'); rs.className = 'lcmReset'; rs.textContent = t('lib.colsReset', '初期の列に戻す');
    rs.addEventListener('click', () => { setCols(COLS.filter(c => c.def).map(c => c.id)); for (const cb of colMenu.querySelectorAll('input')) cb.checked = cols.includes(cb.dataset.col); });
    colMenu.appendChild(rs);
    document.body.appendChild(colMenu);
    const w = colMenu.offsetWidth, h = colMenu.offsetHeight;
    colMenu.style.left = Math.max(4, Math.min(innerWidth - w - 4, x)) + 'px';
    colMenu.style.top = Math.max(4, Math.min(innerHeight - h - 4, y)) + 'px';
  }
  function closeColMenu() { if (colMenu) { colMenu.remove(); colMenu = null; } }
  document.addEventListener('pointerdown', e => { if (colMenu && !colMenu.contains(e.target)) closeColMenu(); }, true);
  document.addEventListener('keydown', e => { if (colMenu && e.key === 'Escape') closeColMenu(); }, true);

  // ---- 表示の切り替え ----
  function applyMode() {
    grid.style.display = mode === 'grid' ? '' : 'none';
    tbl.style.display = mode === 'detail' ? '' : 'none';
    for (const b of document.querySelectorAll('#libViewSeg button')) b.classList.toggle('on', b.dataset.view === mode);
    syncSlider();   // 大きさのスライダーは今の表示の値（グリッド＝サムネイル・詳細＝文字）
  }
  function setView(m) {
    mode = m === 'detail' ? 'detail' : 'grid';
    lsSet(LS_VIEW, mode);
    applyMode();
    renderTable();
  }
  for (const b of document.querySelectorAll('#libViewSeg button')) b.addEventListener('click', () => setView(b.dataset.view));
  applyMode();

  // ---- まとめ ----
  function refresh() {
    compute();
    orderGrid();
    ver++; widthsDirty = true;   // 一覧が変わった＝列の幅を測り直す（詳細表示の時は renderTable で）
    if (mode === 'detail') { if (head) renderHead(); renderTable(); }
    api.filter().renderCount(view.counts);
  }
  let soonT = null;
  function refreshSoon(ms) { if (soonT) return; soonT = setTimeout(() => { soonT = null; refresh(); }, ms == null ? 80 : ms); }
  /** 中身（カバー・ネットの値）が変わった時: 並べ直さず、見えている行だけ描き直す。値が変わった時は列の幅も測り直す
   * （kind==='cover'＝カバーの画像が届いただけ＝幅は変わらないので測らない） */
  function invalidate(kind) { ver++; paintSoon(); if (kind !== 'cover') measureSoon(); }

  /** グリッドのカードをドラッグした時に入れる難易度。絞り込み中（文字の検索・モードの初期値は除く）なら、合う難易度のうち
   * 今開いている難易度と同名（Standard を優先）、無ければ合う中で一番難しい物。絞り込んでいなければ null（今までどおり） */
  function pickForCard(it, curDiff) {
    if (!api.filter().condActive()) return null;
    const rs = (it._vrows || []).filter(r => r.d);
    if (!rs.length) return null;
    const same = rs.filter(r => r.d.diff === curDiff);
    let r = same.find(x => x.d.char === 'Standard') || same[0];
    if (!r) {
      const rank = x => DIFF_ORDER.indexOf(x.d.diff);
      r = rs.reduce((a, b) => (rank(b) > rank(a) || (rank(b) === rank(a) && a.d.char !== 'Standard' && b.d.char === 'Standard')) ? b : a);
    }
    return { char: r.d.char, diff: r.d.diff, filtered: true };
  }

  function rowInfo(r) {
    const it = r.item;
    return { libId: it.lib && it.lib.id || null, native: !!it.native, rel: it.rel || '', key: r.key, char: r.d ? r.d.char : null, diff: r.d ? r.d.diff : null,
      name: (it.entry ? it.entry.name : it.name) || '' };
  }
  /** 選んだ行（並んでいる順）。次の担当の「選んだ行の★を計算」用 */
  function selectedRows() { return view.rows.filter(r => selected.has(r.id)).map(rowInfo); }
  /** 行そのもの（{item, d, key}。並んでいる順）: 'selected'＝選んだ行・'filtered'＝絞り込み（とカタログ・検索）で出ている全部の行 */
  function rowObjs(kind) { return kind === 'selected' ? view.rows.filter(r => selected.has(r.id)) : view.rows.slice(); }

  return {
    refresh, refreshSoon, invalidate, setView, pickForCard, selectedRows, rowsOf, rowObjs,
    mode: () => mode,
    clearSelection() { selected = new Set(); anchor = null; paint(true); },
    relabel() { if (head) renderHead(); ver++; syncSlider(); measureSoon(0); paint(); },
    setFont, setGridSize, font: () => fontPx,
    /** 開発用窓口（_dbgApp.lib）用の複製 */
    dbg() {
      const vis = pool.filter(el => el.style.display !== 'none' && el._row).map(el => el._i);
      return { view: mode, cols: [...cols], sort: sort ? { ...sort } : null, counts: { ...view.counts },
        rows: view.rows.map(rowInfo), sel: selectedRows(), rendered: vis.length, firstRendered: vis.length ? Math.min(...vis) : null,
        grid: [...grid.children].filter(el => el.style.display !== 'none').map(el => el._item ? (el._item.entry ? el._item.entry.name : el._item.name) : ''),
        allCols: COLS.map(c => c.id), defCols: COLS.filter(c => c.def).map(c => c.id), rowH: RH,
        // 文字の大きさ・グリッドの大きさ・測った列の幅（列 id → px）・最後の測り直し（かかった ms・行の数）・スライダー・見出しの段
        font: fontPx, gridSize: gridSz, widths: Object.fromEntries(cols.map((id, i) => [id, colW(i)])), measured: { ...lastMeasure, dirty: widthsDirty }, capped: [...capped],
        slider: slider ? { min: +slider.min, max: +slider.max, value: +slider.value, title: slider.title, shown: slider.style.display !== 'none' } : null,
        headLines: Object.fromEntries(cols.map(id => [id, headLines(byId[id])])) };
    },
    /** 開発用: 一覧の i 行目の列 id のセルを、画面と同じ描き方で作って返す（文字・ツールチップ・クラス） */
    cellOf(i, id) {
      const r = view.rows[i], c = byId[id]; if (!r || !c) return null;
      const td = document.createElement('div'); renderCell(c, r, td, ctx);
      const b = td.querySelector('.ltBtn');
      return { text: td.textContent, title: td.title || '', cls: td.className,
        btn: b ? { act: b.dataset.act || '', disabled: !!b.disabled, title: b.title || '' } : null };
    },
  };
}

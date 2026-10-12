// MEDIA ライブラリのネットの情報・★のまとめての計算・環境設定の MEDIA タブ（2026-10-12）。
//
// - 全曲データ（BeatSaberScrappedData。serve.py の /__lib/details → song_details.py）: 状態の表示と取得のきっかけ。きっかけは
//   「起動して記録したライブラリを読んだ後（初めてライブラリを足した後）に1回」と「環境設定で ON にした時」だけ。1日1回の決まりは Python が守る。
//   値を出している間は、出どころと時点を左のカタログの下（#libSrc）に出す。
// - 🔍: 全曲データに無い曲（net.src==='none'）を、利用者が押して確認した1曲だけ BeatSaver に問い合わせる（/__lib/beatsaver）。
//   毎回確認する・「今後は確認しない」は付けない・まとめて調べる口と自動で調べる口は作らない（利用者の決定: BeatSaver の負荷を最小に）。
// - ★のまとめての計算（NLM推定）: 詳細表示で選んだ行・絞り込んだ行の曲を nlm-rating で計算する（/__lib/rate。曲ごとに1回送る）。
// - 環境設定の MEDIA タブ: 全曲データを取得するか（bsnm_libNetData・キーが無い＝ON）・同時に計算する数（bsnm_rateParallel）・
//   ゲームのプレイ記録（/__lib/playdata・exe 版の pywebview.api.lib_pick_playdata）。
// 画面に入れる文字はすべて textContent（曲名・パス・エラー文はファイル・ネット由来）。
import { libPost } from './lib-native.js';
import { rowHasStars } from './lib-table.js';

const LS_NET = 'bsnm_libNetData', LS_PAR = 'bsnm_rateParallel';
export const PAR_DEF = 4;
// 同時に送る★の計算の上限。ブラウザは同じサーバーへの通信を同時に6本までしか開かない（それ以上は待たされる）ので、
// 1本は画面の読み込み（カバー・曲のドラッグ・一覧の取り直し）のために残す
export const PAR_CAP = 5;
const MANY = 30;            // これより多い曲をまとめて計算する時は、件数と時間の目安を見せて確認する
const SEC_PER_SONG = 1.5;   // 時間の目安に使う1曲の計算の秒数（2026-10-12 にこの PC の CustomLevels で測定: 1曲 0.7〜1.7秒・4曲同時で1.8秒）

const pad = n => String(n).padStart(2, '0');
const fmtFull = s => { const d = new Date(s * 1000); return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`; };
const fmtShort = s => { const d = new Date(s * 1000); return `${d.getMonth() + 1}/${d.getDate()} ${pad(d.getHours())}:${pad(d.getMinutes())}`; };
const fmtDay = s => { const d = new Date(s * 1000); return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`; };
const num = v => (typeof v === 'number' && isFinite(v)) ? v : 0;
const span = (cls, text) => { const s = document.createElement('span'); if (cls) s.className = cls; s.textContent = text; return s; };
const $ = id => document.getElementById(id);

// 🔍 の失敗（/__lib/beatsaver の error）→ 表示文
const LOOK_ERR = {
  network: '通信に失敗しました', 'not-found': 'この曲の識別子（ハッシュ）が分かりません', badHash: 'この曲の識別子（ハッシュ）が分かりません',
  tooBig: 'BeatSaver の応答が正しくありません', badResponse: 'BeatSaver の応答が正しくありません', 'unknown-lib': '記録にないライブラリです',
};
// ★の計算の失敗（/__lib/rate の error）→ その曲の行のツールチップに出す理由
const RATE_ERR = {
  run: '計算に失敗しました', timeout: '計算が時間内に終わりませんでした', badInput: '譜面の内容を読めませんでした',
  'bad-info': 'Info.dat を読めませんでした', 'no-diffs': '計算できる難易度がありません', 'not-found': '譜面のファイルが見つかりません',
  tooLarge: '譜面が大きすぎます', 'too-large': '譜面が大きすぎます', network: '通信に失敗しました', protocol: 'このプラグインの版は、今の NLM では使えません',
};

export function installLibOnline(api) {
  const { t, tf } = api;
  const lsGet = k => { try { return localStorage.getItem(k); } catch (_) { return null; } };
  const lsSet = (k, v) => { try { localStorage.setItem(k, v); } catch (_) {} };

  // ---------------------------------------------------------------- 設定の値
  const netOn = () => lsGet(LS_NET) !== '0';
  const parMax = () => Math.max(1, Math.min(PAR_CAP, (navigator.hardwareConcurrency | 0) || PAR_DEF));
  const parallel = () => { const v = parseInt(lsGet(LS_PAR), 10); return Math.max(1, Math.min(parMax(), v > 0 ? v : PAR_DEF)); };
  const isRecorded = it => !!(it && it.entry && it.native && it.lib && it.lib.native);
  const keyOf = it => it.lib.id + '|' + it.rel;
  const nameOf = it => String((it.entry && it.entry.name) || it.name || it.rel || '');

  // ---------------------------------------------------------------- 全曲データ
  let details = null;   // {state:'none'|'ok'|'error'|'unsupported', asOf, fetchedAt, error}
  let detailsBusy = false, detailsAsked = false, detailsCalls = 0, lastDid = null;
  /** 全曲データの値を使える（設定が ON で、取得済みのデータがある）。🔍 と出どころの表示はこの時だけ */
  const usable = () => netOn() && !!details && (details.state === 'ok' || (details.state === 'error' && details.asOf > 0));

  function setDetails(st) {
    if (!st || typeof st !== 'object' || typeof st.state !== 'string') return;
    details = { state: ['none', 'ok', 'error', 'unsupported'].includes(st.state) ? st.state : 'error',
      asOf: Math.max(0, num(st.asOf)), fetchedAt: Math.max(0, num(st.fetchedAt)), error: typeof st.error === 'string' ? st.error.slice(0, 200) : '' };
    renderSource(); renderPrefs(); api.invalidate();
  }
  /** 全曲データの取得を頼む（1日1回の決まりは Python が守る）。新しいデータが来た・使えるようになった時は一覧の値を取り直す。失敗は黙って前のデータを使う */
  async function updateDetails() {
    if (detailsBusy) return null;
    detailsBusy = true; detailsCalls++; renderPrefs();
    const before = usable();
    let r = null;
    try { r = await libPost('details', { act: 'update' }); } catch (_) { r = null; }
    detailsBusy = false;
    lastDid = r && typeof r.did === 'string' ? r.did : null;
    if (r && r.state) setDetails(r); else renderPrefs();
    if (r && (r.did === 'downloaded' || usable() !== before)) { try { await api.refreshExtra(); } catch (_) {} }
    return r;
  }
  /** 起動して記録したライブラリを読んだ後・初めてライブラリを足した後に1回（設定が ON で、記録したライブラリがある時だけ） */
  function ensureDetails() {
    if (detailsAsked || !netOn() || !api.hasNativeLibs()) return;
    detailsAsked = true;
    updateDetails();
  }

  /** 左のカタログの下: 全曲データの出どころと時点（全曲データの値を出している時だけ） */
  function renderSource() {
    const el = $('libSrc'); if (!el) return;
    const show = usable() && api.items().some(it => it.extra && it.extra.net && it.extra.net.src === 'dump');
    el.style.display = show ? '' : 'none';
    if (!show) return;
    const at = details.asOf || details.fetchedAt;
    el.replaceChildren(span('lsLab', t('lib.src.label', 'データ:')), span('lsName', 'BeatSaberScrappedData'),
      span('lsAt', at ? tf('lib.src.at', '{at} 時点', { at: fmtShort(at) }) : ''));
    el.title = tf('lib.src.tip', '全曲データ BeatSaberScrappedData（元は BeatSaver・BeatLeader・ScoreSaber の公開情報）を jsDelivr から取得して、アップロード日・評価・★・ランク状態などを表示しています。\n{at} 時点のデータ（最終確認 {checked}）。\n🔍 で調べた曲の値は BeatSaver から直接取得したものです。',
      { at: at ? fmtFull(at) : '–', checked: details.fetchedAt ? fmtFull(details.fetchedAt) : '–' });
  }

  // ---------------------------------------------------------------- 🔍（BeatSaver に1曲だけ問い合わせる）
  const looking = new Set();   // 問い合わせ中の曲（記録の id|相対パス）
  const lookLog = [];          // 開発用窓口: 押した結果（{rel, sent, result}）

  /** 全曲データに無い曲のセルに出す文字（{busy, text, btn}）。出さない曲は null。記録したライブラリの曲で、全曲データを使っている時だけ。
   * セルの描き方（netMissing）と、lib-table.js の列の幅の測り方（行ごとにセルを作らずに測る）が使う */
  function netMissingText(row) {
    const it = row.item;
    if (!usable() || !isRecorded(it) || !it.extra || !it.extra.net) return null;
    const busy = looking.has(keyOf(it));
    return { busy, text: busy ? t('lib.look.cellBusy', '問い合わせ中…') : t('lib.look.cell', '未照合'), btn: busy ? '⏳' : '🔍' };
  }
  /** 全曲データに無い曲のセル（lib-table.js の netMissingCell から） */
  function netMissing(row, td) {
    const p = netMissingText(row);
    if (!p) return;
    const n = row.item.extra.net, busy = p.busy;
    td.classList.add('ltMiss');
    td.appendChild(span('ltMissT', p.text));
    const b = document.createElement('button');
    b.type = 'button'; b.className = 'ltBtn ltLook'; b.dataset.act = 'look'; b.textContent = p.btn; b.disabled = busy;
    b.title = t('lib.look.btnTip', 'BeatSaver に問い合わせる（この1曲だけ。送る前に確認します）');
    td.appendChild(b);
    let tip = t('lib.look.tip', '全曲データ（BeatSaberScrappedData）にありません。🔍 で BeatSaver に問い合わせることができます');
    if (n.bsMissAt > 0) tip += '\n' + tf('lib.look.missTip', 'BeatSaver にも見つかりませんでした（{date} に確認）', { date: fmtDay(n.bsMissAt) });
    td.title = tip;
  }

  function onCellButton(row, act) { if (act === 'look') look(row); }

  async function look(row) {
    const it = row && row.item;
    if (!isRecorded(it) || !usable() || !it.extra || !it.extra.net || it.extra.net.src !== 'none') return;
    const k = keyOf(it), name = nameOf(it);
    if (looking.has(k)) return;
    const ok = await api.askYesNo(tf('lib.look.ask', '「{name}」の情報を調べるため、BeatSaver（api.beatsaver.com）へこの曲の識別子を送ります。よろしいですか？', { name }),
      t('lib.look.send', '送信する'), t('lib.look.cancel', 'やめる'));
    if (!ok) { lookLog.push({ rel: it.rel, sent: false }); return; }
    if (looking.has(k)) return;
    looking.add(k); api.invalidate();
    let r;
    try { r = await libPost('beatsaver', { id: it.lib.id, rel: it.rel, net: netOn() }); }
    catch (e) { r = { ok: false, error: (e && e.code) || 'network' }; }
    looking.delete(k);
    if (r && r.ok && r.net && typeof r.net === 'object') {
      api.setItemExtra(it.lib.id, it.rel, { net: r.net });   // 見つかれば🔍が消えて値が出る。見つからなければ🔍は残り、ツールチップに確認した日
      if (r.net.src === 'none') api.stat(tf('lib.look.notFound', 'BeatSaver にも見つかりませんでした: {name}', { name }));
      else api.showOk(tf('lib.look.found', 'BeatSaver から取得しました: {name}', { name }));
      lookLog.push({ rel: it.rel, sent: true, result: r.net.src === 'none' ? 'notFound' : 'found' });
    } else if (r && r.error === 'busy') {
      const n = Math.max(1, Math.min(3600, Math.round(num(r.retryAfter)) || 5));
      api.showErr(tf('lib.look.busy', 'BeatSaver が混んでいます。{n}秒ほど待ってからもう一度お試しください', { n }));
      lookLog.push({ rel: it.rel, sent: true, result: 'busy' });
    } else {
      const code = String((r && r.error) || 'network').slice(0, 40);
      const err = LOOK_ERR[code] ? t('lib.look.err.' + code, LOOK_ERR[code]) : /^http\d+$/.test(code) ? 'HTTP ' + code.slice(4) : code;
      api.showErr(tf('lib.look.fail', 'BeatSaver への問い合わせに失敗しました: {name}（{err}）', { name, err }));
      lookLog.push({ rel: it.rel, sent: true, result: 'error' });
    }
    api.invalidate();
  }

  // ---------------------------------------------------------------- ★のまとめての計算（NLM推定）
  const rate = { running: false, stop: false, total: 0, done: 0, failed: 0, inflight: 0, maxInflight: 0, par: 0, notInstalled: false,
    active: new Set(), queue: [], sent: [] };

  /** 行 → 計算する曲（記録したライブラリの曲で、公式の BL★ も NLM推定も無い行がある曲。同じ曲の行は1回）。
   * 選んだ行の時は、前に計算に失敗した曲もやり直す */
  function targets(kind) {
    const out = [], seen = new Set();
    for (const r of api.rows(kind)) {
      const it = r.item;
      if (!r.d || !isRecorded(it) || it.lib.state !== 'ok' || rowHasStars(r, kind === 'selected')) continue;
      const k = keyOf(it);
      if (seen.has(k) || rate.active.has(k)) continue;
      seen.add(k);
      out.push({ key: k, libId: it.lib.id, rel: it.rel, item: it });
    }
    return out;
  }
  const countTargets = kind => targets(kind).length;
  const starBusy = row => !!(row && row.item && row.item.lib && rate.active.has(keyOf(row.item)));

  /** 計算できなかった曲の印（この起動の間だけ。行のツールチップに理由）。全部の難易度に同じ理由を入れる */
  function failEst(s, r) {
    const code = String((r && r.error) || 'network').slice(0, 40);
    const why = RATE_ERR[code] ? t('lib.rate.err.' + code, RATE_ERR[code]) : code;
    // 添え書き: v4 の譜面か（nlm-rating は v4 も計算できるが、失敗した時の手がかりに）・プラグインの出した詳細
    const notes = [s.item.entry && s.item.entry.fmt === 4 ? t('lib.rate.err.v4', 'v4 形式の譜面') : '',
      r && typeof r.detail === 'string' ? r.detail.trim().slice(0, 160) : ''].filter(Boolean);
    const msg = why + (notes.length ? t('word.parenL', '（') + notes.join(t('word.listSep', '・')) + t('word.parenR', '）') : '');
    const diffs = {};
    for (const d of s.item.entry.diffs || []) diffs[d.char + '/' + d.diff] = { error: msg };
    return { version: '', failed: true, diffs };
  }

  async function rateRows(kind) {
    if (rate.running) { api.stat(t('lib.rate.already', '★の計算はすでに実行中です')); return; }
    const songs = targets(kind);
    if (!songs.length) {
      api.showErr(kind === 'selected'
        ? t('lib.rate.noneSel', '選んだ行に★を計算する曲がありません（公式の★か NLM推定がある曲と、記録したライブラリ以外の曲は計算しません）')
        : t('lib.rate.noneFilt', '表示中の行に★を計算する曲がありません（公式の★か NLM推定がある曲と、記録したライブラリ以外の曲は計算しません）'));
      return;
    }
    const par = parallel();
    if (songs.length > MANY) {
      const min = Math.max(1, Math.round(songs.length * SEC_PER_SONG / par / 60));
      const ok = await api.askYesNo(tf('lib.rate.askMany', '{n}曲の★を計算します（NLM推定）。\n1曲に1〜数秒かかるため、全部で{min}分ほどかかることがあります（同時に{p}曲ずつ。計算の間は PC が重くなります）。\n途中で［中止］できます。始めますか？',
        { n: songs.length, min, p: par }), t('lib.rate.start', '計算する'), t('lib.rate.cancel', 'やめる'));
      if (!ok || rate.running) return;
    }
    Object.assign(rate, { running: true, stop: false, total: songs.length, done: 0, failed: 0, inflight: 0, maxInflight: 0, par, notInstalled: false,
      active: new Set(), queue: songs.slice(), sent: [] });
    renderRateBar(); api.invalidate();
    const worker = async () => {
      while (rate.queue.length && !rate.stop) {
        const s = rate.queue.shift();
        rate.active.add(s.key); rate.inflight++; rate.maxInflight = Math.max(rate.maxInflight, rate.inflight); rate.sent.push(s.rel);
        api.invalidate();
        let r;
        try { r = await libPost('rate', { id: s.libId, rel: s.rel, parallel: par }); }
        catch (e) { r = { ok: false, error: (e && e.code) || 'network' }; }
        rate.inflight--; rate.active.delete(s.key);
        if (r && r.ok && r.est && typeof r.est === 'object') { rate.done++; api.setItemExtra(s.libId, s.rel, { est: r.est }); }
        else if (r && r.error === 'notInstalled') { rate.notInstalled = true; rate.stop = true; rate.queue.length = 0; }   // 残りは送らない
        else { rate.done++; rate.failed++; api.setItemExtra(s.libId, s.rel, { est: failEst(s, r) }); }
        renderRateBar(); api.invalidate();
      }
    };
    await Promise.all(Array.from({ length: Math.min(par, songs.length) }, worker));
    rate.running = false; rate.queue = [];
    renderRateBar(); api.invalidate();
    if (rate.notInstalled) { await needPlugin(); return; }
    const v = { done: rate.done, total: rate.total, n: rate.failed };
    if (rate.stop) api.stat(tf('lib.rate.stopped', '★の計算を中止しました（{done}/{total}曲）', v));
    else if (rate.failed) api.showErr(tf(rate.total === 1 ? 'lib.rate.doneFail1' : 'lib.rate.doneFail', '★を計算しました（{total}曲・計算できなかった曲 {n}。理由はその行の★の欄のツールチップ）', v));
    else api.showOk(tf(rate.total === 1 ? 'lib.rate.done1' : 'lib.rate.done', '★を計算しました（{total}曲・NLM推定）', v));   // 1曲の時は単数形の訳
  }
  function stopRate() { if (!rate.running || rate.stop) return; rate.stop = true; rate.queue.length = 0; renderRateBar(); }

  /** プラグインが取り込まれていない: 取り込み方の案内（難易度を測るのパネルを開ける） */
  async function needPlugin() {
    const ok = await api.askYesNo(t('lib.rate.needPlugin', '★の計算（NLM推定）には追加プラグイン nlm-rating（約20MB）が必要です。\n「難易度を測る」のパネル（ファイルメニュー）の［GitHub から取り込む］で取り込めます。\n\nパネルを開きますか？'),
      t('lib.rate.openPanel', 'パネルを開く'), t('lib.rate.close', '閉じる'));
    if (ok) api.openRatingPanel();
  }

  /** 計算中の帯（MEDIA の検索欄の下）: 「★を計算中 12/85」と［中止］ */
  function renderRateBar() {
    const bar = $('libRateBar'); if (!bar) return;
    bar.style.display = rate.running ? '' : 'none';
    if (!rate.running) return;
    const v = { done: rate.done, total: rate.total, n: rate.failed };
    bar.querySelector('.lrTxt').textContent = (rate.stop ? tf('lib.rate.stopping', '★の計算を中止しています… {done}/{total}', v) : tf('lib.rate.progress', '★を計算中 {done}/{total}', v))
      + (rate.failed ? tf('lib.rate.failN', '（計算できなかった曲 {n}）', v) : '');
    const st = $('libRateStop'); if (st) st.disabled = rate.stop;
  }
  { const st = $('libRateStop'); if (st) st.addEventListener('click', stopRate); }

  // ---------------------------------------------------------------- 環境設定の MEDIA タブ
  function detailsText() {
    if (detailsBusy) return t('set.libNet.busy', '取得中…');
    if (!details) return '';
    const at = details.asOf || details.fetchedAt;
    let s;
    if (details.state === 'ok') s = at ? tf('set.libNet.ok', '{at} 時点のデータ', { at: fmtFull(at) }) : t('set.libNet.okNoDate', '取得済み');
    else if (details.state === 'unsupported') s = t('set.libNet.unsupported', '形式が新しすぎて使えません（NLM の更新が必要です）');
    else if (details.state === 'error') s = details.asOf > 0 ? tf('set.libNet.errOld', '取得に失敗しました（前のデータを使用中: {at} 時点）', { at: fmtFull(details.asOf) })
      : t('set.libNet.err', '取得に失敗しました');
    else s = t('set.libNet.none', '未取得');
    if (!netOn() && details.state !== 'none') s += t('set.libNet.offNote', '（取得しない設定のため、使っていません）');
    return s;
  }
  function playText(p) {
    if (!p || !p.state) return '';
    if (p.state === 'ok') return tf('set.libPlay.ok', '読み込み済み（{date} 更新・{n}件の記録）', { date: p.mtime ? fmtFull(p.mtime) : '–', n: Math.max(0, Math.round(num(p.count))) });
    if (p.state === 'bad') return t('set.libPlay.bad', '読めませんでした（プレイ記録のファイルではないか、壊れています）');
    return exe() ? t('set.libPlay.missing', '見つかりません（ファイルを選んでください）') : t('set.libPlay.missingWeb', '見つかりません');
  }
  const exe = () => !!(window.pywebview && window.pywebview.api && typeof window.pywebview.api.lib_pick_playdata === 'function');

  function renderPrefs() {
    const cb = $('libNetOn'); if (cb) cb.checked = netOn();
    const ns = $('libNetState'); if (ns) { ns.textContent = detailsText(); ns.title = (details && details.error) || ''; }
    const sl = $('libRatePar'), sv = $('libRateParVal');
    if (sl) { sl.max = String(parMax()); if (document.activeElement !== sl) sl.value = String(parallel()); if (sv && !sv.querySelector('input')) sv.textContent = sl.value; }
    const p = api.playState() || {};
    const ps = $('libPlayState'); if (ps) ps.textContent = playText(p);
    const pm = $('libPlayMode'); if (pm) pm.textContent = !p.state ? '' : p.mode === 'custom' ? t('set.libPlay.custom', '選んだファイル:') : t('set.libPlay.auto', '自動（既定の場所）:');
    const pp = $('libPlayPath'); if (pp) { pp.textContent = String(p.path || ''); pp.title = String(p.path || ''); }
    const pk = $('libPlayPick'); if (pk) pk.style.display = exe() ? '' : 'none';
    const rs = $('libPlayReset'); if (rs) rs.disabled = p.mode !== 'custom';
    const eo = $('libPlayExeOnly'); if (eo) eo.style.display = exe() ? 'none' : '';
  }
  /** タブを開いた時: 全曲データとプレイ記録の今の状態を聞き直す */
  async function refreshPrefs() {
    renderPrefs();
    try { const r = await libPost('details', { act: 'status' }); if (r && r.state && !detailsBusy) setDetails(r); } catch (_) {}
    try { const r = await libPost('playdata', { act: 'status' }); if (r && r.state) api.setPlayState(r); } catch (_) {}
    renderPrefs();
  }
  async function setNet(on) {
    lsSet(LS_NET, on ? '1' : '0');
    renderPrefs(); renderSource(); api.invalidate();
    try { await api.refreshExtra(); } catch (_) {}   // OFF＝全曲データの値を消す（net:false）・ON＝手元のデータで出し直す
    if (on) { detailsAsked = true; await updateDetails(); }
  }
  async function pickPlay() {
    const napi = window.pywebview && window.pywebview.api;
    if (!napi || typeof napi.lib_pick_playdata !== 'function') return;
    let r = null;
    try { r = await napi.lib_pick_playdata(); } catch (e) { api.showErr(tf('set.libPlay.pickFail', 'プレイ記録のファイルを使えませんでした: {err}', { err: String(e) })); return; }
    if (!r) return;   // 選ばなかった
    if (r.error) { api.showErr(tf('set.libPlay.pickFail', 'プレイ記録のファイルを使えませんでした: {err}', { err: api.errText(r.error) })); return; }
    if (r.state) api.setPlayState(r);
    renderPrefs();
    try { await api.refreshExtra(); } catch (_) {}
    renderPrefs();
  }
  async function resetPlay() {
    let r = null;
    try { r = await libPost('playdata', { act: 'reset' }); } catch (e) { api.showErr(tf('set.libPlay.resetFail', 'プレイ記録の場所を戻せませんでした: {err}', { err: api.errText(e && e.code) })); return; }
    if (r && r.state) api.setPlayState(r);
    renderPrefs();
    try { await api.refreshExtra(); } catch (_) {}
    renderPrefs();
  }
  {   // 環境設定の部品へ一度だけ繋ぐ（editor.html の #settingsBox の MEDIA タブ）
    const cb = $('libNetOn'); if (cb) cb.addEventListener('change', () => setNet(cb.checked));
    const sl = $('libRatePar'), sv = $('libRateParVal');
    if (sl) {
      sl.max = String(parMax()); sl.value = String(parallel()); if (sv) sv.textContent = sl.value;
      sl.addEventListener('input', () => { if (sv) sv.textContent = sl.value; lsSet(LS_PAR, String(sl.value)); });
    }
    const pk = $('libPlayPick'); if (pk) pk.addEventListener('click', pickPlay);
    const rs = $('libPlayReset'); if (rs) rs.addEventListener('click', resetPlay);
    renderPrefs();
  }

  return {
    netOn, usable, parallel, parMax, setDetails, ensureDetails, updateDetails,
    netMissing, netMissingText, onCellButton, look, starBusy, countTargets, rateRows, stopRate,
    refreshPrefs, renderPrefs,
    /** /__lib/extra を取り直した後（出どころの表示） */
    afterExtra() { renderSource(); },
    relabel() { renderSource(); renderRateBar(); renderPrefs(); },
    /** 開発用窓口（_dbgApp.libOnline）用の複製 */
    dbg() {
      return { netOn: netOn(), usable: usable(), details: details ? { ...details } : null, detailsBusy, detailsAsked, detailsCalls, lastDid,
        parallel: parallel(), parMax: parMax(), source: (() => { const el = $('libSrc'); return el && el.style.display !== 'none' ? { text: el.textContent, title: el.title } : null; })(),
        looking: [...looking].map(k => k.slice(k.indexOf('|') + 1)), lookLog: lookLog.map(x => ({ ...x })),
        rate: { running: rate.running, stop: rate.stop, total: rate.total, done: rate.done, failed: rate.failed, inflight: rate.inflight,
          maxInflight: rate.maxInflight, par: rate.par, notInstalled: rate.notInstalled, queued: rate.queue.length,
          active: [...rate.active].map(k => k.slice(k.indexOf('|') + 1)), sent: [...rate.sent],
          bar: (() => { const b = $('libRateBar'); return b && b.style.display !== 'none' ? b.querySelector('.lrTxt').textContent : null; })() },
        targets: { selected: countTargets('selected'), filtered: countTargets('filtered') },
        prefs: (() => { const g = id => $(id); return { netOn: g('libNetOn') ? g('libNetOn').checked : null, netState: g('libNetState') ? g('libNetState').textContent : null,
          par: g('libRatePar') ? +g('libRatePar').value : null, parMax: g('libRatePar') ? +g('libRatePar').max : null,
          playState: g('libPlayState') ? g('libPlayState').textContent : null, playMode: g('libPlayMode') ? g('libPlayMode').textContent : null,
          playPath: g('libPlayPath') ? g('libPlayPath').textContent : null, pickShown: !!(g('libPlayPick') && g('libPlayPick').style.display !== 'none'),
          resetEnabled: !!(g('libPlayReset') && !g('libPlayReset').disabled), exeOnlyShown: !!(g('libPlayExeOnly') && g('libPlayExeOnly').style.display !== 'none') }; })() };
    },
  };
}

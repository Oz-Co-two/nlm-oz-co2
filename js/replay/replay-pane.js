// 左上の窓の3つ目「REPLAY」（2026-11-22）: Beat Saber で遊んだ自分のリプレイ（BeatLeader の .bsor）を、BL のリプレイアプリで見る。
// MEDIA → PREVIEW → REPLAY → MEDIA（Tab・見出しの「[TAB] 次」のクリック。editor-app.js の setPvMode）。元は ANP（nlm-automap）の
// js/replaypane.js・js/replays.js（同じ作者・GPLv3）。担当どうしの取り決め（API・伝言の形）は変えないこと。
//
// - 窓の中は「一覧」⇄「再生」。一覧は今の曲（書き出す Info.dat の曲名・マッパー＝D.song()）のリプレイ（serve.py の /__replay/list・新しい順）。
//   遊んだ版の譜面の控えが無い物（playable:false）は灰色で「この版の譜面が無いので再生できません」（押しても開かない）。
//   下の端に「リプレイの場所」（自動／選んだ場所）・［変更…］（exe 版だけ＝pywebview.api.replay_pick_folder）・［自動に戻す］（/__replay/resetFolder）。
// - 再生: /__replay/open の url を iframe に開く。BL のリプレイアプリは別のオリジン（http://localhost:<番号>）から出る＝NLM の画面・合言葉に触れない。
//   sandbox で上の窓を動かせない。やり取りは窓どうしの伝言だけ（相手の窓とオリジンを確かめる・送る先のオリジンも決める＝'*' にしない）:
//     NLM → 窓: {nlm:'blr', cmd:'hello'|'seek'(t)|'play'|'pause'}  窓 → NLM: {nlm:'blr', ev:'hi'|'ready'(dur)|'time'(t,playing,speed,at)|'zoom'(level)|'key'}
//   窓の中を押した後は入力が窓へ行くので、Tab・Ctrl の組み合わせだけ bridge.js が ev:'key' で渡す → D.onKey（editor-app.js の rpKeyFromViewer）
//   ズームは窓の中のホイールだけ（bridge.js）。窓の上の端の右寄り（BL の再生バー・右上の三角を避ける）に「🔍 ホイールでズーム」を重ねる（1 倍でない時は倍率）。
// - REPLAY を出した時: 前に開いた物（この起動の間・同じ曲）か一番新しい playable を自動で開く。開く時に NLM の難易度をリプレイの難易度へ
//   （Standard の時だけ・D.matchDiff）。
// - 同期（ANP の決まり）: 時計はリプレイ側の1つ。つないでいる間は editor-app.js の rpFollow が毎フレーム L.state() を読んで再生位置を合わせ、
//   NLM の側で位置を変えたら L.seek・▶/Space は L.play／L.pause（NLM の曲の音・3D の切る音は鳴らさない）。
//   時刻: リプレイの秒＝書き出した song.egg の秒＝NLM の beatToTimeTM(拍)（無音追加・Music の配置は egg に焼き込むので足し引き無し）。
//   位置を送るのは 0.12 秒に1回まで・最後の位置は必ず。送った位置に着くまで（1 秒まで）リプレイの前の時刻は使わない（hold）。
//   ▶/停止を送った後も、その状態になるまで（1 秒まで）リプレイの前の状態は使わない（holdPlay）。
//   再生中は「読んだ時刻＋（今の壁の時計−読んだ時の壁の時計）×速さ」（0.25 秒より先は読まない）＝伝言の遅れを埋める（ANP の tickFollow）。
//   途中でやめた・失敗のリプレイ（記録が曲の終わりより 1 秒以上前で終わる）は endSec で止める（同期を外していても）。
//   REPLAY から別の画面へ・一覧へ戻った時はリプレイを止めて外す。プロジェクトを開いた／新規の時は窓ごと閉じる（reset）。同期を外すと別々に動く。
// - サーバー由来の文字（リプレイの場所・修飾・難易度の名前など）は textContent だけで出す（innerHTML に入れない）。
// - 点を重ねる（見出しの［点数］・2026-11-22）: リプレイを開いた時に1回 /__replay/events を読み（replay-marks.js の cleanEvents）、
//   再生の画面を出している間だけ D.setMarks で editor-app.js へ渡す（NLE の拍番号の帯の印・3D のノーツの輪＝editor-app.js の rpMarks*）。
//   一覧へ戻した・別の画面へ・新規・開く・オフで D.setMarks(null)。凡例の行（#rpMk）は D.marksInfo() を 0.3 秒ごとに読んで、
//   段ごとの数・合わないノーツの数・難易度が違う／Standard 以外で出していないこと を出す。オン／オフは環境設定のキー bsnm_rpMarks（'0'＝オフ・無い＝オン）。

import { cleanEvents, RP_COL } from './replay-marks.js';

const DIFFS = ['Easy', 'Normal', 'Hard', 'Expert', 'ExpertPlus'];
const SYNC_KEY = 'bsnm_rpSync';     // 同期（'0'＝切る。キーが無い＝つなぐ）
const MARKS_KEY = 'bsnm_rpMarks';   // 点を重ねる（'0'＝オフ。キーが無い＝オン）
// 凡例: [段, 印の形（NLE の印・3D は輪）, 既定の文]
const MK_LEGEND = [['t115', '○', '115'], ['t113', '○', '113+'], ['t110', '○', '110+'], ['t106', '○', '106+'], ['t100', '○', '100+'], ['low', '○', '99以下'],
  ['bad', '◆', 'バッド'], ['miss', '✕', 'ミス'], ['bomb', '●', 'ボム'], ['wall', '▬', '壁']];
const SEEK_MS = 120;                // 位置を送る間隔の下限
const HOLD_MS = 1000;               // 送った位置・再生の状態になるまで待つ最長
const LOAD_WARN_MS = 25000;         // この時間たっても読み込めなければ知らせる
const MAX_ITEMS = 2000;
// 修飾の略号 → 訳のキー（ANP の js/replays.js と同じ表）
const MODS = { DA: '消える矢印', FS: '速い曲', SF: 'とても速い曲', SS: '遅い曲', GN: 'ゴーストノーツ', NA: '矢印なし', NB: 'ボムなし',
  NF: 'ノーフェイル', NO: '壁なし', PM: 'プロモード', SC: '小さいノーツ', IF: '1 ミスで終わり', BE: 'バッテリー', OD: '古いドット', SA: '厳しい角度', OP: '1 本セイバー' };
const ERR_JA = {
  'no-api': 'この版ではリプレイを見られません（リプレイの部品がありません）',
  'network': 'NLM のサーバーに接続できませんでした',
  'not-found': 'このリプレイが見つかりません（消された・場所が変わった）。↻ で一覧を読み直してください',
  'no-map': 'この版の譜面が無いので再生できません',
  'viewer-failed': 'リプレイの窓（BL のリプレイアプリ）を開けませんでした',
  'bad-replay': 'リプレイのファイルを読めませんでした（壊れているか、対応していない形式です）',
  'bad-path': 'この場所は使えません（ネットワーク上のフォルダなど）',
  'too-large': 'ファイルが大きすぎます',
};
const lsGet = k => { try { return localStorage.getItem(k); } catch (_) { return null; } };
const lsSet = (k, v) => { try { localStorage.setItem(k, v); } catch (_) {} };
const num = v => typeof v === 'number' && isFinite(v);
const wall = () => performance.timeOrigin + performance.now();   // 壁の時計（ミリ秒）＝リプレイの窓の bridge.js の at と同じ物差し
const cssZoom = el => (el && typeof el.currentCSSZoom === 'number' && el.currentCSSZoom > 0) ? el.currentCSSZoom : 1;
const p2 = n => String(n).padStart(2, '0');
const when = s => { const d = new Date(s * 1000); return `${d.getFullYear()}-${p2(d.getMonth() + 1)}-${p2(d.getDate())} ${p2(d.getHours())}:${p2(d.getMinutes())}`; };
const day = s => { const d = new Date(s * 1000); return `${d.getFullYear()}-${p2(d.getMonth() + 1)}-${p2(d.getDate())}`; };
const fmtT = s => { s = Math.max(0, s || 0); const m = Math.floor(s / 60), r = s - m * 60; return `${m}:${r.toFixed(1).padStart(4, '0')}`; };
const str = (v, max) => typeof v === 'string' ? v.slice(0, max) : '';
const int = v => num(v) && v >= 0 ? Math.floor(v) : 0;
/** 窓のオリジン（この PC の名前と番号だけ受け付ける） */
const cleanOrigin = o => typeof o === 'string' && /^http:\/\/(localhost|127\.0\.0\.1|\[::1\]):\d{1,5}$/.test(o) ? o : '';
const cleanUrl = (u, org) => typeof u === 'string' && org && u.startsWith(org + '/') && u.length < 4000 && !/[\s"'<>\\]/.test(u) ? u : '';

/** /__replay/list の item（サーバー由来）を知っている項目・形だけにする */
function cleanItem(x) {
  if (!x || typeof x !== 'object' || typeof x.id !== 'string' || !x.id || x.id.length > 300) return null;
  const diff = DIFFS.includes(x.diff) ? x.diff : str(x.diff, 24);
  return { id: x.id, playedAt: num(x.playedAt) ? x.playedAt : 0, diff, mode: str(x.mode, 32) || 'Standard',
    hash: typeof x.hash === 'string' && /^[0-9a-fA-F]{40}$/.test(x.hash) ? x.hash.toLowerCase() : '',
    fail: !!x.fail, exit: !!x.exit, practice: !!x.practice, acc: num(x.acc) && x.acc >= 0 && x.acc <= 1.5 ? x.acc : null,
    misses: int(x.misses), bad: int(x.bad), bombs: int(x.bombs), walls: int(x.walls),
    mods: str(x.mods, 80).split(',').map(s => s.trim()).filter(s => /^[A-Za-z0-9]{1,6}$/.test(s)),
    endSec: num(x.endSec) && x.endSec >= 0 ? x.endSec : null, jd: num(x.jd) ? x.jd : null, playable: !!x.playable,
    exportedAt: num(x.exportedAt) ? x.exportedAt : null, latest: !!x.latest };
}
function cleanStatus(s) {
  if (!s || typeof s !== 'object') return null;
  const src = ['env', 'chosen', 'auto', 'none'].includes(s.source) ? s.source : 'none';
  const dirs = Array.isArray(s.dirs) ? s.dirs.slice(0, 20).filter(d => d && typeof d.path === 'string').map(d => ({ path: d.path.slice(0, 400), count: int(d.count), missing: !!d.missing })) : [];
  return { source: src, dirs };
}
const songKey = s => JSON.stringify([String(s.name || '').trim().toLowerCase(), String(s.mapper || '').trim().toLowerCase()]);

export function installReplayPane(D) {
  const { t, tf } = D;
  const $ = id => document.getElementById(id);
  const body = $('bodyRp'), head = $('rpHead'), gap = $('rpHeadGap'), label = $('pvModeLabel');
  if (!body || !head) return null;
  const el = {
    listHead: $('rpListHead'), count: $('rpCount'), reloadList: $('rpReloadList'),
    playHead: $('rpPlayHead'), back: $('rpBack'), sync: $('rpSync'), reopen: $('rpReopen'),
    sum: $('rpSum'), note: $('rpNote'), listView: $('rpListView'), empty: $('rpEmpty'), list: $('rpList'),
    foot: $('rpFoot'), dirs: $('rpDirs'), pick: $('rpPick'), auto: $('rpAuto'),
    playView: $('rpPlayView'), box: $('rpFrameBox'), zoom: $('rpZoom'), marks: $('rpMarks'), mk: $('rpMk'),
  };
  // shown＝REPLAY を出している / view＝'list'|'play' / rows＝一覧（null＝まだ読んでいない）/ err＝一覧のエラーの種類 / cur＝開いているリプレイ
  // frame・origin・ready・dur＝窓 / t・playing・base＝最後に届いた時刻（先読みの元）/ hold・pend・timer＝送った位置 / holdPlay＝送った再生の状態
  const R = { shown: false, view: 'list', songKey: null, rows: null, status: null, err: '', loading: false, lseq: 0, oseq: 0, last: new Map(),
    cur: null, frame: null, origin: null, ready: false, dur: 0, sync: lsGet(SYNC_KEY) !== '0', linked: false,
    t: null, playing: false, base: null, hold: null, pend: null, timer: 0, hello: 0, wd: 0, holdPlay: null,
    stopEnd: null, stopSent: false, zoom: 1, endSec: null, diffNote: '', openErr: '', slow: false, flash: '', flashT: 0, checkAt: 0, keepRun: false,
    // 点を重ねる: marks＝オン／オフ・events＝開いているリプレイの出来事（null＝まだ・読めない）・evErr＝読めなかった種類・mkKey＝凡例の行の中身の印
    marks: lsGet(MARKS_KEY) !== '0', events: null, evErr: '', evSeq: 0, mkKey: '', mkAt: 0 };
  const errText = code => ERR_JA[code] ? t('rp.err.' + code, ERR_JA[code]) : tf('rp.err.other', 'リプレイを扱えませんでした（{code}）', { code });
  const dispDiff = d => d === 'ExpertPlus' ? 'Expert+' : d;
  const exeApi = () => (window.pywebview && window.pywebview.api && typeof window.pywebview.api.replay_pick_folder === 'function') ? window.pywebview.api : null;

  // ---- 通信（すべて POST・X-NLM-Request。合言葉は settings-mirror.js が自動で付ける） ----
  async function api(act, b) {
    let r;
    try { r = await fetch('__replay/' + act, { method: 'POST', headers: { 'X-NLM-Request': '1', 'Content-Type': 'application/json' }, body: JSON.stringify(b || {}) }); }
    catch (_) { throw { code: 'network' }; }
    let j = null;
    try { j = await r.json(); } catch (_) {}
    const code = j && typeof j.error === 'string' && /^[\w-]{1,40}$/.test(j.error) ? j.error : '';
    if (r.status === 404 && (!code || code === 'unknown' || j.error === 'unknown endpoint')) throw { code: 'no-api' };   // この版のサーバーにリプレイの API が無い
    if (!j || !j.ok) throw { code: code || (r.ok ? 'failed' : 'http-' + r.status) };
    return j;
  }

  // ---- 見出しの行の先頭の空き（REPLAY [TAB] MEDIA の帯の幅。MEDIA の #libHeadGap と同じ測り方） ----
  function fitGap() {
    if (!label || !gap || !R.shown) return;
    const lr = label.getBoundingClientRect(), hr = head.getBoundingClientRect();
    if (!lr.width || !hr.width) return;
    const w = Math.max(0, Math.ceil((lr.right - hr.left) / cssZoom(head)) + 6);
    if (gap.style.width !== w + 'px') gap.style.width = w + 'px';
  }
  try { const ro = new ResizeObserver(() => requestAnimationFrame(fitGap)); ro.observe(label); ro.observe(head); } catch (_) {}

  // ---- 窓の伝言 ----
  const post = m => { if (R.frame && R.frame.contentWindow && R.origin) R.frame.contentWindow.postMessage(Object.assign({ nlm: 'blr' }, m), R.origin); };
  /** editor-app.js の rpFollow／play／pause が使う口（つないでいる間だけ D.setLink で渡す） */
  const L = {
    play() { flushSeek(); post({ cmd: 'play' }); R.holdPlay = { want: true, until: performance.now() + HOLD_MS }; },
    pause() { post({ cmd: 'pause' }); R.holdPlay = { want: false, until: performance.now() + HOLD_MS }; },
    seek(sec) { seekReplay(sec); },
    /** 今のリプレイの時刻と再生中か。hold＝送った位置へまだ着いていない（NLM の再生位置をそのままにする） */
    state() {
      const now = performance.now();
      if (R.hold && now > R.hold.until) R.hold = null;
      if (R.holdPlay && now > R.holdPlay.until) R.holdPlay = null;
      const playing = R.holdPlay ? R.holdPlay.want : R.playing;
      if (R.hold || R.pend != null) return { t: R.hold ? R.hold.t : R.pend, playing, hold: true };
      let tt = R.t;
      if (R.playing && R.base && !(R.holdPlay && !R.holdPlay.want)) {
        const age = Math.max(0, Math.min(0.25, (wall() - R.base.at) / 1000));   // 伝言が途切れても 0.25 秒より先は読まない
        tt = R.base.t + age * R.base.sp;
        if (R.stopEnd != null) tt = Math.min(tt, R.stopEnd);
        if (R.dur) tt = Math.min(tt, R.dur);
      }
      return { t: tt, playing, hold: false };
    },
  };
  function seekReplay(sec) {
    if (!num(sec)) return;
    if (R.dur) sec = Math.min(sec, R.dur - 0.01);
    R.pend = Math.max(0, sec);
    if (!R.timer) fire();
  }
  function fire() {   // 位置を送る（0.12 秒に1回まで・最後の位置は必ず送る）
    const sec = R.pend; R.pend = null;
    post({ cmd: 'seek', t: sec });
    R.hold = { t: sec, until: performance.now() + HOLD_MS };
    R.timer = setTimeout(() => { R.timer = 0; if (R.pend != null) fire(); }, SEEK_MS);
  }
  function flushSeek() { if (R.pend != null) { clearTimeout(R.timer); R.timer = 0; fire(); } }   // ▶ の前に待たせている位置を先に送る

  function onMessage(e) {
    if (!R.frame || e.source !== R.frame.contentWindow || e.origin !== R.origin) return;
    const d = e.data;
    if (!d || typeof d !== 'object' || d.nlm !== 'blr') return;
    if (d.ev === 'hi') { stopHello(); return; }
    if (d.ev === 'ready') {
      R.ready = true; R.dur = num(d.dur) && d.dur > 0 ? d.dur : 0; stopHello(); clearTimeout(R.wd); R.slow = false;
      // 記録が曲の終わりより前で終わっている（途中でやめた・失敗して落ちた）＝そこで止める。ノーフェイルの失敗は記録が終わりまで続くので止めない
      const e2 = R.endSec;
      R.stopEnd = e2 != null && R.dur && e2 < R.dur - 1 ? e2 : null;
      renderPlay(); link(); return;
    }
    if (d.ev === 'zoom') { R.zoom = num(d.level) && d.level > 0 ? d.level : 1; renderZoom(); return; }
    if (d.ev === 'key') {   // 窓の中で押した Tab・Ctrl の組み合わせ（bridge.js が渡す）→ NLM のショートカットへ
      const k = str(d.key, 20);
      if (k && D.onKey) D.onKey({ key: k, code: str(d.code, 20), ctrl: !!d.ctrl, shift: !!d.shift, alt: !!d.alt, repeat: !!d.repeat });
      return;
    }
    if (d.ev !== 'time' || !num(d.t)) return;
    R.t = d.t; R.playing = !!d.playing;
    R.base = { t: R.t, at: num(d.at) ? d.at : wall(), sp: num(d.speed) && d.speed > 0 ? d.speed : 1 };
    body.dataset.t = R.t.toFixed(3);
    if (R.stopEnd != null && R.playing && R.t >= R.stopEnd) { if (!R.stopSent) { R.stopSent = true; L.pause(); } }   // 記録が終わった所で止める（同期を外していても）
    else if (!R.playing || R.t < R.stopEnd) R.stopSent = false;
    if (R.hold && R.pend == null && Math.abs(R.t - R.hold.t) < 0.3) {   // 送った位置に着いた
      if (!R.playing && Math.abs(R.t - R.hold.t) < 0.02) { R.t = R.hold.t; R.base.t = R.t; }   // 止めたままの小さな丸めは NLM の位置のまま（拍の目盛りからずらさない）
      R.hold = null;
    }
    if (R.holdPlay && R.playing === R.holdPlay.want) R.holdPlay = null;
  }
  window.addEventListener('message', onMessage);
  function startHello() { stopHello(); post({ cmd: 'hello' }); R.hello = setInterval(() => post({ cmd: 'hello' }), 300); }   // 伝言の受け手が動き始めるまで呼ぶ（hi まで）
  function stopHello() { clearInterval(R.hello); R.hello = 0; }

  // ---- 同期 ----
  function link() {
    if (!R.ready || !R.sync || !R.shown || R.view !== 'play' || R.linked) { mark(); return; }
    R.linked = true;
    D.setLink(L);
    seekReplay(D.nlmTime());   // つないだ時はリプレイを NLM の位置へ
    mark();
  }
  function unlink(pause) {
    if (pause && R.frame && R.ready) L.pause();   // 同期を切っていても止める（見えない所で鳴り続けない）
    if (!R.linked) { mark(); return; }
    R.linked = false;
    D.setLink(null);
    mark();
  }
  function mark() {   // 状態の印（#bodyRp の data-state＝none・loading・ready・linked）。「同期」はつないでいる間だけ緑
    body.dataset.state = R.linked ? 'linked' : R.ready ? 'ready' : R.frame ? 'loading' : 'none';
    if (el.sync) { el.sync.classList.toggle('on', R.linked); el.sync.classList.toggle('off', !R.sync); el.sync.setAttribute('aria-pressed', R.sync ? 'true' : 'false'); }
  }

  // ---- 窓 ----
  function teardown() {
    unlink(false);
    stopHello(); clearTimeout(R.timer); clearTimeout(R.wd); R.timer = 0;
    if (R.frame) { R.frame.remove(); R.frame = null; }
    Object.assign(R, { origin: null, ready: false, dur: 0, t: null, playing: false, base: null, hold: null, pend: null, holdPlay: null,
      stopEnd: null, stopSent: false, zoom: 1, endSec: null, openErr: '', slow: false, events: null, evErr: '' });
    R.evSeq++;   // 読んでいる途中の出来事は捨てる
    delete body.dataset.t;
    renderZoom(); mark(); syncMarks();
  }
  function makeFrame(url) {
    const f = document.createElement('iframe');
    f.id = 'rpFrame'; f.className = 'rpFrame'; f.title = t('rp.frameT', 'BeatLeader のリプレイ（BL のリプレイアプリ）');
    // 自動再生（NLM の ▶ でリプレイの音を始める）・全画面・画面を消さない を、窓のオリジン（src）だけに渡す
    // screen-wake-lock＝BL のアプリが再生中に画面を消さないように頼む（無いと窓の中で console.error が1回出る）
    f.allow = 'autoplay; fullscreen; screen-wake-lock'; f.allowFullscreen = true; f.referrerPolicy = 'no-referrer';
    // 上の窓（NLM の画面）を動かさない（allow-top-navigation を付けない）・BeatLeader のページへのリンクは別のタブで
    f.setAttribute('sandbox', 'allow-scripts allow-same-origin allow-popups allow-popups-to-escape-sandbox allow-pointer-lock allow-modals allow-downloads');
    f.addEventListener('load', () => { if (R.frame === f) startHello(); });
    f.src = url;
    el.box.insertBefore(f, el.zoom);
    R.frame = f; R.ready = false; R.zoom = 1;
    clearTimeout(R.wd);
    R.wd = setTimeout(() => { if (R.frame === f && !R.ready) { R.slow = true; renderPlay(); } }, LOAD_WARN_MS);   // 読み込めない時は知らせる＝↻ で開き直せる
    renderZoom(); mark();
  }
  async function openRow(r) {
    if (!r) return;
    if (!r.playable) { flash(t('rp.noMap', 'この版の譜面が無いので再生できません')); return; }
    if (R.cur && R.cur.id === r.id && R.frame) { setView('play'); link(); return; }   // 開いている物＝そのまま戻る
    const seq = ++R.oseq;
    teardown();
    R.cur = r; R.last.set(R.songKey, r.id); R.endSec = r.endSec;
    R.diffNote = diffNote(D.matchDiff(r.diff, r.mode), r);
    setView('play');
    const req = { id: r.id };
    if (R.sync) req.t = Math.round(Math.max(0, D.nlmTime()) * 1000) / 1000;   // 開く位置（止めたまま）＝NLM の今の位置
    let o;
    try { o = await api('open', req); }
    catch (e) { if (seq === R.oseq) { R.openErr = e.code || 'failed'; renderPlay(); } return; }
    if (seq !== R.oseq) return;
    const origin = cleanOrigin(o.origin), url = cleanUrl(o.url, origin);
    if (!origin || !url) { R.openErr = 'viewer-failed'; renderPlay(); return; }
    R.origin = origin;
    if (num(o.endSec)) R.endSec = o.endSec;
    makeFrame(url);
    renderPlay();
    loadEvents(r);
  }
  /** 点を重ねる: 開いたリプレイの出来事を1回読む（開き直すまで同じ物を使う）。読めなくても再生はそのまま（凡例の行に知らせるだけ） */
  async function loadEvents(r) {
    const seq = ++R.evSeq;
    R.events = null; R.evErr = ''; syncMarks();
    let j;
    try { j = await api('events', { id: r.id }); }
    catch (e) { if (seq === R.evSeq && R.cur === r) { R.evErr = e.code || 'failed'; renderMk(true); } return; }
    if (seq !== R.evSeq || R.cur !== r) return;
    R.events = cleanEvents(j);
    syncMarks();
  }
  /** editor-app.js へ渡す（REPLAY を出していて・再生の画面で・開いたリプレイの出来事があり・オンの時だけ。ほかは null＝消す） */
  function syncMarks() {
    const on = R.marks && R.shown && R.view === 'play' && !!R.cur && !!R.events && !R.openErr;
    if (D.setMarks) D.setMarks(on ? { id: R.cur.id, events: R.events, diff: R.cur.diff, mode: R.cur.mode } : null);
    renderMk(true);
  }
  function diffNote(m, r) {
    const cur = D.curDiff() || '-';
    if (!m || m.kind === 'same' || m.kind === 'switched') return '';
    if (m.kind === 'mode') return tf('rp.diffMode', 'このリプレイは {mode} のプレイです。NLM の難易度は今のまま（{cur}）です', { mode: r.mode, cur });
    return tf('rp.diffNone', 'このリプレイの難易度（{diff}）は今のプロジェクトに無いので、NLM の難易度は今のまま（{cur}）です', { diff: dispDiff(r.diff), cur });
  }

  // ---- 一覧 ----
  async function loadList(autoOpen) {
    const s = D.song(), key = songKey(s), seq = ++R.lseq;
    if (key !== R.songKey) { teardown(); R.cur = null; R.songKey = key; }
    if (!s.name) { R.rows = []; R.err = 'no-song'; R.loading = false; setView('list'); renderList(); return; }
    R.loading = true; renderList();
    let j;
    try { j = await api('list', { song: { name: s.name, mapper: s.mapper } }); }
    catch (e) { if (seq !== R.lseq) return; R.loading = false; R.err = e.code || 'failed'; R.rows = []; setView('list'); renderList(); return; }
    if (seq !== R.lseq || songKey(D.song()) !== key) return;
    R.loading = false; R.err = '';
    R.status = cleanStatus(j.status);
    R.rows = (Array.isArray(j.items) ? j.items : []).slice(0, MAX_ITEMS).map(cleanItem).filter(Boolean);
    if (R.cur && !R.rows.some(x => x.id === R.cur.id)) { teardown(); R.cur = null; }
    renderList();
    if (autoOpen && R.shown) autoPick();
    else if (R.view === 'play' && !R.cur) setView('list');
  }
  function autoPick() {   // 前に開いた物（この起動の間・同じ曲）か、一番新しい再生できる物
    const rows = R.rows || [], want = R.last.get(R.songKey);
    const r = rows.find(x => x.id === want && x.playable) || rows.find(x => x.playable);
    if (r) openRow(r); else setView('list');
  }
  function setView(v) {
    if (v === 'list' && R.view === 'play') unlink(true);   // 一覧へ戻る＝リプレイを止めて外す（窓は残す＝同じ物を押すとすぐ戻る）
    R.view = v;
    el.listView.hidden = v !== 'list'; el.playView.hidden = v !== 'play';
    el.listHead.hidden = v !== 'list'; el.playHead.hidden = v !== 'play';
    body.dataset.view = v;
    renderPlay();   // 要点は再生の時だけ
    if (v === 'list') renderList();
    syncMarks();    // 点を重ねるのは再生の画面の間だけ
    requestAnimationFrame(fitGap);
  }
  function flash(msg) { R.flash = msg; clearTimeout(R.flashT); R.flashT = setTimeout(() => { R.flash = ''; renderNote(); }, 4000); renderNote(); }

  function span(cls, text, title) { const s = document.createElement('span'); if (cls) s.className = cls; s.textContent = text; if (title) s.title = title; return s; }
  function tagsOf(r) {
    const out = [];
    if (r.exit) out.push(span('rpTag quit', t('rp.tag.exit', 'やめた'), r.endSec != null ? tf('rp.tag.exitT', '途中でやめた（ポーズからメニュー・やり直し）。{t} まで遊んだ', { t: fmtT(r.endSec) }) : ''));
    if (r.fail) out.push(span('rpTag bad', t('rp.tag.fail', '失敗'), t('rp.tag.failT', '途中で失敗した')));
    if (r.practice) out.push(span('rpTag prac', t('rp.tag.practice', '練習'), t('rp.tag.practiceT', '練習モードのプレイ')));
    return out;
  }
  function missText(r) {
    const parts = [];
    if (r.misses) parts.push(tf('rp.miss', 'ミス {n}', { n: r.misses }));
    if (r.bad) parts.push(tf('rp.bad', 'バッド {n}', { n: r.bad }));
    if (r.bombs) parts.push(tf('rp.bombs', 'ボム {n}', { n: r.bombs }));
    if (r.walls) parts.push(tf('rp.walls', '壁 {n}', { n: r.walls }));
    return parts.length ? parts.join(t('rp.sep', '・')) : t('rp.noMiss', 'ミスなし');
  }
  function verText(r) {
    if (!r.playable) return t('rp.ver.none', '譜面なし');
    if (r.latest) return t('rp.ver.latest', '最新の書き出し');
    return r.exportedAt ? tf('rp.ver.oldAt', '以前の書き出し（{d}）', { d: day(r.exportedAt) }) : t('rp.ver.old', '以前の書き出し');
  }
  const accText = r => r.acc != null ? (r.acc * 100).toFixed(2) + '%' : '—';
  function renderList() {
    if (!R.shown && R.rows === null) return;
    const rows = R.rows || [];
    el.count.textContent = R.loading ? t('rp.loading', '読んでいます…') : rows.length ? tf('rp.count', 'この曲のリプレイ {n} 件', { n: rows.length }) : '';
    let emp = '';
    if (R.loading && !rows.length) emp = t('rp.loading', '読んでいます…');
    else if (R.err === 'no-song') emp = t('rp.noSong', '曲名がありません。INFO で曲名を入れて書き出すと、この曲のリプレイが出ます');
    else if (R.err) emp = R.err === 'no-api' ? errText('no-api') : tf('rp.listFail', 'リプレイの一覧を読めませんでした: {err}', { err: errText(R.err) });
    else if (R.status && !R.status.dirs.some(d => !d.missing)) emp = t('rp.noDir', 'リプレイのフォルダが見つかりません（BeatLeader の mod が保存する Beat Saber のフォルダの UserData\\BeatLeader\\Replays）。下の［変更…］で場所を選んでください（exe 版）');
    else if (!rows.length && R.rows) emp = t('rp.empty', 'この曲のリプレイはまだありません。NLM から書き出して Beat Saber で遊ぶと、ここに出ます（遊んだ後は ↻）');
    el.empty.textContent = emp; el.empty.hidden = !emp;
    el.empty.classList.toggle('bad', !!R.err && R.err !== 'no-song');
    el.list.textContent = '';
    for (const r of rows) {
      const row = document.createElement('div');
      row.className = 'rpRow' + (r.playable ? '' : ' off') + (R.cur && R.cur.id === r.id ? ' cur' : '');
      row.dataset.id = r.id;
      row.title = r.playable ? t('rp.rowT', 'クリックでこのリプレイを開く') : t('rp.noMap', 'この版の譜面が無いので再生できません');
      const l1 = document.createElement('div'); l1.className = 'rpL1';
      const dd = span('rpDiff', dispDiff(r.diff) + (r.mode && r.mode !== 'Standard' ? ' ' + r.mode : ''));
      dd.style.setProperty('--dc', D.diffColor(r.diff));
      l1.append(span('rpWhen', r.playedAt ? when(r.playedAt) : '—'), dd, span('rpAcc', accText(r), t('rp.accT', '精度（点÷満点の目安・修飾（FS・NF など）を掛ける前の点）')), ...tagsOf(r));
      const l2 = document.createElement('div'); l2.className = 'rpL2';
      const mods = span('rpMods', '');
      for (const m of r.mods) mods.appendChild(span('rpMod', m, MODS[m] ? t('rp.mod.' + m, MODS[m]) : m));
      l2.append(span('rpMiss', missText(r)), mods, span('rpVer' + (r.playable ? (r.latest ? ' latest' : ' old') : ' none'), verText(r),
        r.playable ? (r.latest ? t('rp.ver.latestT', '今の書き出しの譜面で遊んだプレイ') : t('rp.ver.oldT', '遊んだ後に編集して書き出し直した。遊んだ時の譜面（控え）で再生します')) : t('rp.noMap', 'この版の譜面が無いので再生できません')));
      row.append(l1, l2);
      el.list.appendChild(row);
    }
    renderFoot(); renderNote();
  }
  function renderFoot() {
    const s = R.status;
    el.dirs.textContent = '';
    el.dirs.appendChild(span('rpDirLbl', t('rp.dir', 'リプレイの場所:')));
    if (!s || !s.dirs.length) el.dirs.appendChild(span('rpDirNone', s ? t('rp.dirNone', '見つかりません') : '—'));
    else for (const d of s.dirs) {
      const p = span('rpDirPath' + (d.missing ? ' missing' : ''), d.path, d.path); el.dirs.appendChild(p);
      el.dirs.appendChild(span('rpDirN', d.missing ? t('rp.dirMissing', '（フォルダがありません）') : tf('rp.dirN', '（{n} 件）', { n: d.count })));
    }
    if (s) el.dirs.appendChild(span('rpDirSrc', s.source === 'chosen' ? t('rp.src.chosen', '（選んだ場所）') : s.source === 'env' ? t('rp.src.env', '（テスト用の環境変数）')
      : s.source === 'auto' ? t('rp.src.auto', '（自動）') : ''));
    el.pick.hidden = !exeApi();
    el.auto.hidden = !(s && s.source === 'chosen');
  }
  function renderPlay() {
    const r = R.cur;
    el.sum.textContent = '';
    if (r) {
      const dd = span('rpDiff', dispDiff(r.diff) + (r.mode && r.mode !== 'Standard' ? ' ' + r.mode : '')); dd.style.setProperty('--dc', D.diffColor(r.diff));
      el.sum.append(span('rpWhen', r.playedAt ? when(r.playedAt) : '—'), dd, span('rpAcc', accText(r)), ...tagsOf(r),
        span('rpVer' + (r.latest ? ' latest' : ' old'), verText(r)));
    }
    el.sum.hidden = !r || R.view !== 'play';
    if (R.view === 'play') renderNote();
  }
  function renderNote() {
    const lines = [];
    if (R.flash) lines.push(['', R.flash]);
    if (R.view === 'play' && R.cur) {
      if (R.openErr) lines.push(['bad', tf('rp.openFail', '開けませんでした: {err}', { err: errText(R.openErr) })]);
      else if (R.slow) lines.push(['bad', t('rp.slow', 'リプレイの窓が 25 秒たっても読み込めていません。↻ で開き直してください')]);
      else if (!R.frame || !R.ready) lines.push(['', t('rp.opening', 'リプレイを開いています…')]);
      if (!R.cur.latest) lines.push(['old', t('rp.oldVer', '遊んだ後に編集した版です（今の譜面とずれることがあります）')]);
      if (R.stopEnd != null) lines.push(['', tf(R.cur.exit ? 'rp.stopExit' : R.cur.fail ? 'rp.stopFail' : 'rp.stopEnd',
        R.cur.exit ? '途中でやめたプレイ: {t} まで。そこで止めます' : R.cur.fail ? '失敗したプレイ: {t} まで。そこで止めます' : '記録が途中で終わったプレイ: {t} まで。そこで止めます',
        { t: fmtT(R.stopEnd) })]);
      if (R.diffNote) lines.push(['', R.diffNote]);
      if (!R.sync && R.ready) lines.push(['', t('rp.unsynced', '同期を切っています（NLM とリプレイは別々に動きます）')]);
    }
    el.note.textContent = '';
    for (const [cls, s] of lines) { const d = document.createElement('div'); if (cls) d.className = cls; d.textContent = s; el.note.appendChild(d); }
    el.note.hidden = !lines.length;
  }
  function renderZoom() {
    el.zoom.textContent = R.zoom !== 1 && R.frame ? tf('rp.zoomLv', '🔍 ×{z}（ホイールで戻す）', { z: R.zoom.toFixed(1) }) : t('rp.zoomHint', '🔍 ホイールでズーム');
    el.zoom.hidden = !R.frame;
  }
  /** 点を重ねる: 見出しの切り替えの見た目と、凡例の行（段ごとの数・合わない数・出していない理由）。force＝中身が同じでも作り直す（言語の切り替え） */
  function renderMk(force) {
    if (el.marks) { el.marks.classList.toggle('on', R.marks); el.marks.setAttribute('aria-pressed', R.marks ? 'true' : 'false'); }
    if (!el.mk) return;
    const show = R.view === 'play' && !!R.cur && R.marks && !R.openErr;
    let rows = null, key = '';
    if (show) {
      if (R.evErr) rows = [['bad', tf('rp.mk.fail', 'リプレイの点を読めませんでした: {err}', { err: errText(R.evErr) })]];
      else if (!R.events) rows = R.frame ? [['', t('rp.mk.loading', '点を読んでいます…')]] : null;
      else {
        const info = D.marksInfo ? D.marksInfo() : null;
        if (!info) rows = null;
        else if (info.reason === 'mode') rows = [['', t('rp.mk.mode', 'Standard 以外のプレイなので、点は重ねません')]];
        else if (info.reason === 'diff') rows = [['', tf('rp.mk.diff', '今の難易度（{cur}）がこのリプレイ（{diff}）と違うので、点は重ねていません', { cur: info.cur, diff: info.diff })]];
        else if (!info.events) rows = [['', t('rp.mk.none', 'このリプレイには重ねる点がありません')]];
        else rows = [['legend', info]];
      }
      key = JSON.stringify(rows);
    }
    if (!force && key === R.mkKey) return;
    R.mkKey = key;
    el.mk.textContent = '';
    el.mk.hidden = !rows;
    if (!rows) return;
    for (const [cls, v] of rows) {
      if (cls !== 'legend') { const d = span('rpMkMsg' + (cls ? ' ' + cls : ''), v); el.mk.appendChild(d); continue; }
      const lg = document.createElement('span'); lg.className = 'rpMkLegend';
      lg.title = t('rp.mk.legendT', '3D: ノーツの輪の色＝点数÷満点×115（BL のリプレイアプリと同じ色: 虹色 115（BL は 115 のノーツを虹色にする）・紫 113 以上・青 110 以上・緑 106 以上・黄 100 以上・ピンク 99 以下）。太い輪＝橙 バッド・赤 ミス（大きな ✕ も重ねる）・マゼンタ ボム。NLE: 拍番号の帯の印（✕ ミス・◆ バッド・● ボム・▬ 壁。押すとその位置へ・薄い印は今の譜面に合うノーツが無い所）。数はこのリプレイの全部の出来事');
      for (const [k, g, ja] of MK_LEGEND) {
        const c = span('rpMkC', ''); c.dataset.k = k;
        const gl = span('rpMkG', g); gl.style.color = RP_COL[k];
        c.append(gl, span('rpMkL', t('rp.mk.' + k, ja)), span('rpMkN', String(v.counts[k] || 0)));
        if (!v.counts[k]) c.classList.add('zero');
        lg.appendChild(c);
      }
      el.mk.appendChild(lg);
      const un = [];
      if (v.unNotes) un.push(tf('rp.mk.unNotes', '合わないノーツ {n} 個', { n: v.unNotes }));
      if (v.unBombs) un.push(tf('rp.mk.unBombs', '合わないボム {n} 個', { n: v.unBombs }));
      if (un.length) lg.appendChild(span('rpMkUn', un.join(t('rp.sep', '・')),   // 凡例の続き（折り返した2行目の空きに入る）
        t('rp.mk.unT', '今の譜面に、拍・列・段・色の同じノーツ（ボム）が無い出来事（遊んだ後に編集した所など）。3D の輪は出さず、NLE の印は薄く出します')));
    }
  }

  // ---- 部品の配線 ----
  // 押した後はボタンからフォーカスを外す（Space＝再生/停止のショートカットで、フォーカスの残ったボタンがもう一度押されないように）
  for (const b of [el.reloadList, el.back, el.sync, el.reopen, el.pick, el.auto, el.marks]) if (b) b.addEventListener('click', () => b.blur());
  if (el.marks) el.marks.addEventListener('click', () => {   // 点を重ねる（オフで NLE の印と 3D の輪を両方消す）
    R.marks = !R.marks; lsSet(MARKS_KEY, R.marks ? '1' : '0');
    syncMarks();
  });
  el.list.addEventListener('click', e => {
    const row = e.target.closest && e.target.closest('.rpRow'); if (!row) return;
    const r = (R.rows || []).find(x => x.id === row.dataset.id);
    if (r) openRow(r);
  });
  el.reloadList.addEventListener('click', () => loadList(false));
  el.back.addEventListener('click', () => setView('list'));
  el.reopen.addEventListener('click', () => { const r = R.cur; if (!r) return; teardown(); R.cur = null; openRow(r); });
  el.sync.addEventListener('click', () => {
    R.sync = !R.sync; lsSet(SYNC_KEY, R.sync ? '1' : '0');
    if (R.sync) link(); else unlink(false);
    renderNote(); mark();
  });
  el.pick.addEventListener('click', async () => {
    const a = exeApi(); if (!a) return;
    let s = null;
    try { s = await a.replay_pick_folder(); } catch (_) {}
    if (!s) return;   // 取り消し
    if (s.ok === false) { flash(errText(typeof s.error === 'string' && /^[\w-]{1,40}$/.test(s.error) ? s.error : 'failed')); return; }
    R.status = cleanStatus(s) || R.status; renderFoot();
    loadList(false);
  });
  el.auto.addEventListener('click', async () => {
    try { R.status = cleanStatus(await api('resetFolder', {})) || R.status; } catch (e) { flash(errText(e.code || 'failed')); return; }
    renderFoot(); loadList(false);
  });

  // ---- 外から呼ぶ口（editor-app.js） ----
  function show() {
    R.shown = true; body.dataset.shown = '1';
    requestAnimationFrame(fitGap);
    const key = songKey(D.song());
    if (key !== R.songKey || R.rows === null) loadList(true);
    else if (R.frame && R.cur) { setView('play'); link(); }
    else autoPick();
    // 書き出し先がつながっていて、この起動でまだ控えていなければ控える（控えを始める前に書き出した譜面のリプレイも再生できるように）
    if (!R.keepRun) {
      R.keepRun = true;
      Promise.resolve(D.keepNow()).then(r => { R.keepRun = false; if (r && r.ok && r.isNew && R.shown) loadList(false); })
        .catch(e => { R.keepRun = false; console.warn('リプレイの控え:', e); });
    }
  }
  function hide() { if (!R.shown) return; R.shown = false; delete body.dataset.shown; unlink(true); syncMarks(); }   // 別の画面へ＝リプレイを止めて外す・点も消す
  function reset() { teardown(); R.cur = null; R.rows = null; R.songKey = null; R.status = null; R.err = ''; R.lseq++; R.oseq++; R.diffNote = '';
    if (R.view === 'play') setView('list'); else renderList(); }
  function frame() {   // 毎フレーム（REPLAY を出している間）: 曲名・マッパーが変わったら（プロジェクトを開いた・INFO で書き換えた）一覧を読み直す
    if (!R.shown) return;
    const now = performance.now();
    if (now >= R.mkAt) { R.mkAt = now + 300; if (R.view === 'play' && R.cur && R.marks) renderMk(false); }   // 点の凡例（編集・難易度の切り替えに付いていく）
    if (now < R.checkAt) return;
    R.checkAt = now + 600;
    if (!R.loading && songKey(D.song()) !== R.songKey) loadList(true);
  }
  function relabel() { renderList(); renderPlay(); renderZoom(); mark(); renderMk(true); requestAnimationFrame(fitGap); }
  function dbg() {
    return JSON.parse(JSON.stringify({ shown: R.shown, view: R.view, loading: R.loading, err: R.err, status: R.status,
      rows: (R.rows || []).map(r => ({ id: r.id, playable: r.playable, latest: r.latest })), cur: R.cur ? R.cur.id : null,
      state: body.dataset.state || 'none', linked: R.linked, ready: R.ready, dur: R.dur, t: R.t, playing: R.playing, hold: !!R.hold, pend: R.pend,
      stopEnd: R.stopEnd, zoom: R.zoom, sync: R.sync, origin: R.origin, src: R.frame ? R.frame.src : null,
      count: el.count.textContent, empty: el.empty.hidden ? '' : el.empty.textContent, note: el.note.hidden ? '' : el.note.innerText,
      sum: el.sum.hidden ? '' : el.sum.textContent, dirs: el.dirs.textContent, zoomText: el.zoom.hidden ? '' : el.zoom.textContent,
      pickShown: !el.pick.hidden, autoShown: !el.auto.hidden,
      marks: R.marks, events: R.events ? R.events.notes.length + R.events.walls.length : null, evErr: R.evErr,
      mk: el.mk && !el.mk.hidden ? el.mk.textContent : '', mkMsg: el.mk && !el.mk.hidden ? [...el.mk.querySelectorAll('.rpMkMsg')].map(e => e.textContent).join(' / ') : '',
      mkUn: el.mk && !el.mk.hidden ? [...el.mk.querySelectorAll('.rpMkUn')].map(e => e.textContent).join('') : '',
      mkChips: el.mk && !el.mk.hidden ? [...el.mk.querySelectorAll('.rpMkC')].map(c => ({ k: c.dataset.k, label: c.querySelector('.rpMkL').textContent, n: +c.querySelector('.rpMkN').textContent })) : [] }));
  }
  setView('list'); mark();
  return { show, hide, reset, frame, relabel, dbg, linked: () => R.linked };
}

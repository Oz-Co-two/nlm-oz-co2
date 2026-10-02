// 難易度を測る（BeatLeader の星の近似）の結果パネル。計算は別配布のプラグイン nlm-rating（serve.py → rating_plugin.py 経由）。
// プラグインは本体に同梱しない＝未導入なら「取り込む」ボタンを出す。通信は利用者がボタンを押した時だけ。
// 譜面チェックと同じ非モーダルの浮きパネル（開いたまま譜面を直して「再測定」できる）。測るのは書き出すのと同じ中身。
const MODS = ['SS', 'FS', 'SFS'];   // 通常速度(none)の下に並べる速度違い
// サーバーの失敗コード → 表示文（rt.err.<code>）
const ERR = {
  network: 'GitHub に接続できませんでした。ネット接続を確認してください。',
  notFound: '配布元に公開中の版が見つかりませんでした。',
  badManifest: '配布元の情報（manifest.json）が読めませんでした。',
  hash: 'ダウンロードしたファイルが配布元の情報と一致しません（壊れているか改ざんの可能性）。取り込みを中止しました。',
  badZip: 'ダウンロードしたファイルの中身が正しくありません。取り込みを中止しました。',
  tooLarge: 'ファイルが大きすぎます。',
  protocol: 'このプラグインの版は、今の NLM では使えません。NLM を更新してください。',
  notInstalled: 'プラグインが取り込まれていません。',
  run: '測定に失敗しました。',
  timeout: '測定が時間内に終わりませんでした。',
  badInput: '測る譜面の内容が正しくありません。',
};

export function installRatingPanel(api) {
  const { t, escHtml, collect, dispDiff } = api;
  const post = async (act, body) => {
    const r = await fetch('__rating/' + act, { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-NLM-Request': '1' },
      body: JSON.stringify(body || {}) });
    if (!r.ok) throw new Error('HTTP ' + r.status);
    return r.json();
  };
  const errText = j => t('rt.err.' + j.error, ERR[j.error] || j.error) + (j.detail ? ` (${j.detail})` : '');
  const num = (v, d = 2) => (typeof v === 'number' && isFinite(v)) ? v.toFixed(d) : '–';
  const mb = n => (n / 1048576).toFixed(1);

  let el = null, st = null, latest = null, last = null, busy = '', msg = null;   // msg={err|ok, text}

  function build() {
    el = document.createElement('div'); el.id = 'rtPanel';
    el.innerHTML = `<div class="rtHead"><span class="rtTitle"></span><span class="rtHeadBtns">
        <button class="rtRun"></button><button class="rtClose" aria-label="close">✕</button></span></div>
      <div class="rtPlug"><span class="rtPlugTxt"></span><span class="rtPlugBtns">
        <select class="rtVer"></select><button class="rtCheck"></button><button class="rtInstall"></button></span></div>
      <div class="rtMsg"></div><div class="rtBody"></div><div class="rtFoot"></div>`;
    document.body.appendChild(el);
    el.querySelector('.rtClose').addEventListener('click', close);
    el.querySelector('.rtRun').addEventListener('click', () => measure());
    el.querySelector('.rtCheck').addEventListener('click', () => check());
    el.querySelector('.rtInstall').addEventListener('click', () => install());
    el.querySelector('.rtVer').addEventListener('change', ev => useVer(ev.target.value));
    const head = el.querySelector('.rtHead');   // 見出しをつかんで移動（譜面チェックと同じ）
    head.addEventListener('pointerdown', ev => {
      if (ev.target.closest('button')) return;
      const r0 = el.getBoundingClientRect(), dx = ev.clientX - r0.left, dy = ev.clientY - r0.top;
      head.setPointerCapture(ev.pointerId);
      const mv = e => {
        el.style.left = Math.max(0, Math.min(innerWidth - 80, e.clientX - dx)) + 'px';
        el.style.top = Math.max(0, Math.min(innerHeight - 40, e.clientY - dy)) + 'px'; el.style.right = 'auto';
      };
      const up = () => { head.removeEventListener('pointermove', mv); head.removeEventListener('pointerup', up); };
      head.addEventListener('pointermove', mv); head.addEventListener('pointerup', up);
    });
  }

  const installed = () => !!(st && st.current);

  function render() {
    if (!el) return;
    el.querySelector('.rtTitle').textContent = t('rt.title', '難易度を測る（BeatLeaderの星の近似）');
    const run = el.querySelector('.rtRun');
    run.textContent = busy === 'measure' ? t('rt.measuring', '測定中…') : (last ? t('rt.rerun', '↻ 再測定') : t('rt.run', '測る'));
    run.disabled = !!busy || !installed();
    // プラグインの状態
    const txt = el.querySelector('.rtPlugTxt'), chk = el.querySelector('.rtCheck'), ins = el.querySelector('.rtInstall'), sel = el.querySelector('.rtVer');
    if (!st) txt.textContent = t('rt.plugLoading', 'プラグインを確認中…');
    else if (!installed()) txt.textContent = t('rt.plugNone', 'プラグイン未導入');
    else txt.textContent = t('rt.plugVer', 'プラグイン v{v}').replace('{v}', st.current);
    chk.textContent = busy === 'check' ? t('rt.checking', '確認中…') : t('rt.check', '更新を確認');
    chk.disabled = !!busy; chk.style.display = installed() ? '' : 'none';
    let insLabel = null;
    if (st && !installed()) insLabel = t('rt.install', 'GitHub から取り込む');
    else if (latest && latest.compatible && !latest.installed) insLabel = t('rt.update', 'v{v} に更新（{mb}MB）').replace('{v}', latest.version).replace('{mb}', mb(latest.size));
    ins.textContent = busy === 'install' ? t('rt.installing', 'ダウンロード中…') : (insLabel || '');
    ins.style.display = insLabel || busy === 'install' ? '' : 'none'; ins.disabled = !!busy;
    const vers = st ? st.installed.filter(m => m.compatible) : [];
    sel.style.display = vers.length > 1 ? '' : 'none';   // 旧版へ戻す用（取り込み済みが2つ以上ある時だけ）
    sel.replaceChildren(...vers.map(m => { const o = document.createElement('option'); o.value = m.version; o.textContent = 'v' + m.version; o.selected = m.version === st.current; return o; }));
    sel.disabled = !!busy;
    // お知らせ（エラー・更新確認の結果）
    const me = el.querySelector('.rtMsg');
    me.className = 'rtMsg' + (msg ? (msg.err ? ' err' : ' ok') : ''); me.textContent = msg ? msg.text : '';
    el.querySelector('.rtFoot').innerHTML = escHtml(t('rt.foot', 'BeatLeader の公開ソースコードで計算した近似値です。本家の値と異なる場合があります（特に Acc は本家より低めに出ることがあります）。BeatLeader の公式ツールではありません。'))
      + `<br><span class="rtFootSub">${escHtml(t('rt.footSub', 'ノーツが20個未満の難易度は測れません。速度違い: SS=0.85倍 / FS=1.2倍 / SFS=1.5倍。'))}</span>`;
    renderBody();
  }

  function renderBody() {
    const body = el.querySelector('.rtBody');
    if (st && !installed()) {
      body.innerHTML = `<div class="rtIntro">${escHtml(t('rt.intro', 'この機能には追加プラグイン nlm-rating（約20MB）が必要です。「GitHub から取り込む」を押すと、配布元（下記）からダウンロードして、このアプリのフォルダの plugins に保存します。'))}`
        + `<div class="rtRepo">${escHtml(st.repo || '')}</div></div>`;
      return;
    }
    if (!last) { body.innerHTML = ''; return; }
    if (last.error) { body.innerHTML = `<div class="rtErr">${escHtml(last.error)}</div>`; return; }
    if (!last.results.length) { body.innerHTML = `<div class="rtErr">${escHtml(t('rt.noDiff', '測れる難易度がありません'))}</div>`; return; }
    const head = `<tr><th>${escHtml(t('rt.colDiff', '難易度'))}</th><th>★</th><th>Pass</th><th>Tech</th><th>Acc</th></tr>`;
    const rows = last.results.map(d => {
      const name = escHtml(dispDiff(d.difficulty));
      if (d.skipped) return `<tr class="rtSkip"><td>${name}</td><td colspan="4">${escHtml(t('rt.tooFew', 'ノーツが20個未満のため測れません（{n}個）').replace('{n}', d.notes))}</td></tr>`;
      const n = d.ratings.none || {};
      const tip = t('rt.predAcc', '予測精度 {p}%').replace('{p}', num((n.predictedAcc || 0) * 100, 2));
      const mods = MODS.filter(m => d.ratings[m]).map(m => `<span class="rtMod">${m} ★${escHtml(num(d.ratings[m].stars))}</span>`).join('');
      return `<tr title="${escHtml(tip)}"><td>${name}</td><td class="rtStar">${escHtml(num(n.stars))}</td><td>${escHtml(num(n.pass))}</td><td>${escHtml(num(n.tech))}</td><td>${escHtml(num(n.acc))}</td></tr>`
        + (mods ? `<tr class="rtMods"><td></td><td colspan="4">${mods}</td></tr>` : '');
    }).join('');
    body.innerHTML = `<table class="rtTable">${head}${rows}</table>`
      + `<div class="rtMeta">${escHtml(t('rt.meta', 'nlm-rating v{v}・{s}秒').replace('{v}', last.version).replace('{s}', num(last.elapsedMs / 1000, 1)))}</div>`;
  }

  async function refreshStatus() {
    try { st = await post('status'); } catch (e) { st = null; msg = { err: true, text: String(e && e.message || e) }; }
  }
  async function check() {
    if (busy) return; busy = 'check'; msg = null; render();
    try {
      const j = await post('check');
      if (!j.ok) msg = { err: true, text: errText(j) };
      else {
        st = j; latest = j.latest;
        if (!latest.compatible) msg = { err: true, text: t('rt.needNlm', '新しい版 v{v} がありますが、使うには NLM の更新が必要です。').replace('{v}', latest.version) };
        else if (latest.installed) msg = { ok: true, text: t('rt.upToDate', '最新版（v{v}）を取り込み済みです。').replace('{v}', latest.version) };
        else msg = { ok: true, text: t('rt.newer', '新しい版 v{v} があります。').replace('{v}', latest.version) };
      }
    } catch (e) { msg = { err: true, text: String(e && e.message || e) }; }
    busy = ''; render();
  }
  async function install() {
    if (busy) return; busy = 'install'; msg = null; render();
    try {
      const j = await post('install');
      if (!j.ok) msg = { err: true, text: errText(j) };
      else { st = j; latest = null; msg = { ok: true, text: t('rt.installed', 'v{v} を取り込みました。').replace('{v}', j.current) }; }
    } catch (e) { msg = { err: true, text: String(e && e.message || e) }; }
    busy = ''; render();
    if (installed() && msg && msg.ok) measure();
  }
  async function useVer(v) {
    if (busy) return; busy = 'use'; render();
    try { const j = await post('use', { version: v }); if (j.ok) { st = j; last = null; msg = null; } else msg = { err: true, text: errText(j) }; }
    catch (e) { msg = { err: true, text: String(e && e.message || e) }; }
    busy = ''; render();
  }
  async function measure() {
    if (busy || !installed()) return; busy = 'measure'; msg = null; render();
    try {
      const p = await collect();
      if (p.error) last = { error: p.error };
      else {
        const j = await post('measure', { files: p.files, modifiers: ['none', ...MODS] });
        last = j.ok ? j : { error: errText(j) };
      }
    } catch (e) { last = { error: String(e && e.message || e) }; }
    busy = ''; render();
  }

  async function open() {
    if (!el) build();
    el.style.display = 'flex'; render();
    if (!st) { await refreshStatus(); render(); }
    if (installed()) measure();   // 開くたびに測る（譜面チェックと同じ。開いたままなら「再測定」ボタン）
  }
  function close() { if (el) el.style.display = 'none'; }
  return { open, close, isOpen: () => !!el && el.style.display !== 'none' };
}

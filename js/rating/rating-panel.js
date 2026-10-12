// 難易度を測る（BeatLeader の星の近似）の結果パネル。計算は別配布のプラグイン nlm-rating（serve.py → rating_plugin.py 経由）。
// プラグインは本体に同梱しない＝未導入なら「取り込む」ボタンを出す。通信は利用者がボタンを押した時だけ。
// 譜面チェックと同じ非モーダルの浮きパネル（開いたまま譜面を直して「再測定」できる）。測るのは書き出すのと同じ中身。
// 状態・通信・測定結果は rating-client.js（譜面チェックの BL評価リストと共有）。
import { RATING_MODS as MODS } from './rating-client.js';

export function installRatingPanel(api) {
  const { t, escHtml, dispDiff, rating } = api;
  const S = rating.state;
  const num = (v, d = 2) => (typeof v === 'number' && isFinite(v)) ? v.toFixed(d) : '–';
  const mb = n => (n / 1048576).toFixed(1);

  let el = null;

  function build() {
    el = document.createElement('div'); el.id = 'rtPanel';
    el.innerHTML = `<div class="rtHead"><span class="rtTitle"></span><span class="rtHeadBtns">
        <button class="rtRun"></button><button class="rtClose" aria-label="close">✕</button></span></div>
      <div class="rtPlug"><span class="rtPlugTxt"></span><span class="rtPlugBtns">
        <select class="rtVer"></select><button class="rtCheck"></button><button class="rtInstall"></button></span></div>
      <div class="rtMsg"></div><div class="rtBody"></div><div class="rtFoot"></div>`;
    document.body.appendChild(el);
    el.querySelector('.rtClose').addEventListener('click', close);
    el.querySelector('.rtRun').addEventListener('click', () => rating.measure());
    el.querySelector('.rtCheck').addEventListener('click', () => rating.check());
    el.querySelector('.rtInstall').addEventListener('click', async () => { if (await rating.install()) rating.measure(); });
    el.querySelector('.rtVer').addEventListener('change', ev => rating.useVer(ev.target.value));
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
    rating.subscribe(() => { if (isOpen()) render(); });   // 譜面チェック側で測った・取り込んだ時も描き直す
  }

  function render() {
    if (!el) return;
    const { st, latest, last, busy, msg } = S, installed = rating.installed();
    el.querySelector('.rtTitle').textContent = t('rt.title', '難易度を測る（BeatLeaderの星の近似）');
    const run = el.querySelector('.rtRun');
    run.textContent = busy === 'measure' ? t('rt.measuring', '測定中…') : (last ? t('rt.rerun', '↻ 再測定') : t('rt.run', '測る'));
    run.disabled = !!busy || !installed;
    // プラグインの状態
    const txt = el.querySelector('.rtPlugTxt'), chk = el.querySelector('.rtCheck'), ins = el.querySelector('.rtInstall'), sel = el.querySelector('.rtVer');
    if (!st) txt.textContent = t('rt.plugLoading', 'プラグインを確認中…');
    else if (!installed) txt.textContent = t('rt.plugNone', 'プラグイン未導入');
    else txt.textContent = t('rt.plugVer', 'プラグイン v{v}').replace('{v}', st.current);
    chk.textContent = busy === 'check' ? t('rt.checking', '確認中…') : t('rt.check', '更新を確認');
    chk.disabled = !!busy; chk.style.display = installed ? '' : 'none';
    let insLabel = null;
    if (st && !installed) insLabel = t('rt.install', 'GitHub から取り込む');
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
    const body = el.querySelector('.rtBody'), { st, last } = S;
    if (st && !rating.installed()) {
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

  async function open() {
    if (!el) build();
    el.style.display = 'flex'; render();
    await rating.ensureStatus();
    // 開くたびに測る（譜面チェックと同じ。開いたままなら「再測定」ボタン）。前回から譜面が変わっていなければ、その結果をそのまま出す
    if (rating.installed()) rating.measure({ ifChanged: true });
  }
  function close() { if (el) el.style.display = 'none'; }
  function isOpen() { return !!el && el.style.display !== 'none'; }
  return { open, close, isOpen };
}

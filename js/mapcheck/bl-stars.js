// NLM版BL評価リストの★/Tech の欄（R5.A の視界ブロックの式と、R11.H.5 の★の並びに使う）。表示は R5.A の行の下。
//  - 値は「難易度を測る」プラグイン nlm-rating の近似値を自動で入れる（rating-client.js。「難易度を測る」パネルと結果を共有）
//  - 手で書き換えた欄は手入力の値を優先し、測り直しても上書きしない（BeatLeader の本当の値が分かった時用）。「自動に戻す」で消せる
//  - プラグインが無ければ取り込みの案内を出す。説明（配布元・大きさ・保存先）を見てから「取り込む」を押す2段階
//    （署名なし exe の取り込みになるため。GitHub への通信は押した時だけ）
//  - 手入力の値・測定結果は、どちらもアプリを開いている間だけ保持（プロジェクトには保存しない）
export function blStars({ t, escHtml, dispDiff, rating }) {
  const manual = {};    // 難易度 → { star?, tech? }（手で入れた値）
  let asking = false;   // 取り込みの説明を開いている
  const num2 = v => Math.round(v * 100) / 100;
  const S = rating ? rating.state : null;
  const autoOf = dn => (rating && rating.ratingOf(dn)) || null;

  // runBlCriteria に渡す p.stars（欄ごとに 手入力 → 自動 の順）
  function values(diffs) {
    const out = {};
    for (const dn of diffs) {
      const a = autoOf(dn) || {}, m = manual[dn] || {};
      const star = m.star ?? a.star, tech = m.tech ?? a.tech;
      if (star != null || tech != null) out[dn] = { star, tech };
    }
    return out;
  }

  // プラグインの状態とボタン（自動計算・再計算・取り込み）
  function controlHTML() {
    if (!rating) return '';
    const { st, last, busy, msg } = S;
    const info = s => `<span class="blRtInfo">${escHtml(s)}</span>`;
    const err = s => `<div class="blRtErr">${escHtml(s)}</div>`;
    if (!st) return `<div class="blRtCtl">${info(msg && msg.act === 'status' ? msg.text : t('rt.plugLoading', 'プラグインを確認中…'))}</div>`;
    if (!rating.installed()) {
      const ierr = msg && msg.err && msg.act === 'install' ? err(msg.text) : '';
      if (busy === 'install') return `<div class="blRtCtl">${info(t('rt.installing', 'ダウンロード中…'))}</div>`;
      if (asking) {
        return `<div class="blRtBox">${escHtml(t('rt.intro', 'この機能には追加プラグイン nlm-rating（約20MB）が必要です。「GitHub から取り込む」を押すと、配布元（下記）からダウンロードして、このアプリのフォルダの plugins に保存します。'))}`
          + ` ${escHtml(t('bl.rt.after', '取り込んだ後、★とTechを自動で計算して下の欄に入れます。'))}`
          + `<div class="blRtRepo">${escHtml(st.repo || '')}</div>`
          + `<div class="blRtBtns"><button class="blRtInstall">${escHtml(t('rt.install', 'GitHub から取り込む'))}</button>`
          + `<button class="blRtCancel">${escHtml(t('bl.rt.cancel', 'やめる'))}</button></div></div>${ierr}`;
      }
      return `<div class="blRtCtl"><button class="blRtOpen">${escHtml(t('bl.rt.install', '📥 プラグインを取り込んで自動計算…'))}</button>`
        + `${info(t('bl.rt.orManual', 'または下の欄に手で入力'))}</div>${ierr}`;
    }
    const label = busy === 'measure' ? t('bl.rt.running', '計算中…') : (last && !last.error ? t('bl.rt.rerun', '↻ 再計算') : t('bl.rt.run', '⚙ 自動計算'));
    const meta = last && last.results ? info(t('bl.rt.meta', 'nlm-rating v{v} による近似値（BeatLeader公式の値ではありません）').replace('{v}', last.version)) : '';
    return `<div class="blRtCtl"><button class="blRtRun"${busy ? ' disabled' : ''}>${escHtml(label)}</button>${meta}</div>`
      + (last && last.error ? err(last.error) : '');
  }

  function html(diffs) {
    const rows = diffs.map(dn => {
      const a = autoOf(dn), m = manual[dn] || {}, d = escHtml(dn);
      const field = k => {
        const man = m[k] != null, v = man ? m[k] : (a && a[k] != null ? num2(a[k]) : '');
        return `<input type="number" step="0.01" min="0" data-${k}="${d}" value="${v}"${man ? ' class="man"' : ''}>`;
      };
      let side = '';
      if (m.star != null || m.tech != null) {
        side = `<span class="blStarMan">${escHtml(t('bl.rt.manual', '手入力'))}</span>`
          + (a && !a.skipped ? `<button class="blStarAuto" data-dn="${d}">${escHtml(t('bl.rt.toAuto', '自動に戻す'))}</button>` : '');
      } else if (a && a.skipped) side = `<span class="blStarNa">${escHtml(t('bl.rt.tooFew', '自動計算できません（ノーツ20個未満）'))}</span>`;
      return `<span class="blStar"><b>${escHtml(dispDiff(dn))}</b> ★${field('star')} Tech${field('tech')}${side}</span>`;
    }).join('');
    return `<div class="blStarsBox">${controlHTML()}<div class="blStars">${rows}</div></div>`;
  }

  // クリック。処理したら true（呼んだ側が判定と表示をやり直す）
  function onClick(ev) {
    const b = ev.target.closest('.blRtOpen, .blRtCancel, .blRtInstall, .blRtRun, .blStarAuto');
    if (!b) return false;
    if (b.classList.contains('blRtOpen')) asking = true;
    else if (b.classList.contains('blRtCancel')) asking = false;
    else if (b.classList.contains('blRtInstall')) { asking = false; rating.install().then(ok => { if (ok) rating.measure(); }); }
    else if (b.classList.contains('blRtRun')) rating.measure();
    else delete manual[b.dataset.dn];
    return true;
  }
  // 欄の入力（確定した時）。処理したら true。空にした欄は自動の値に戻る
  function onChange(x) {
    const dn = x.dataset.star || x.dataset.tech; if (!dn) return false;
    const k = x.dataset.star ? 'star' : 'tech', v = x.value === '' ? undefined : Math.max(0, +x.value);
    const m = { ...(manual[dn] || {}), [k]: v };
    if (m.star == null && m.tech == null) delete manual[dn]; else manual[dn] = m;
    return true;
  }
  return { values, html, onClick, onChange };
}

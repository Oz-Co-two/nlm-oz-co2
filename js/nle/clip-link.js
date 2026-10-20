// リンクしたクリップ（2026-10-19）の画面の部品: 確認の画面（親を選ぶ・難易度を選ぶ・繋ぐ/切る 等）と、3D/NLE の上の小さな帯。
// 状態（クリップ・難易度・履歴）は editor-app.js が持つ。ここは DOM を作って、押された結果を返すだけ。
// クリップ名など他人のファイル由来の文字が入るので、innerHTML は使わず textContent だけで組み立てる。

const mkEl = (tag, cls, text) => { const e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; };

/**
 * 確認の画面（見た目は未保存の確認と同じ #dirtyDlg。テストの部品もそのまま使える）。
 * opts:
 *   kind     data-lk に入れる種類（テスト・画面の撮影用）
 *   title    太字の1行目
 *   lines    説明の行（文字の配列。空の要素は飛ばす）
 *   radios   [{main, sub, sub2, warn, disabled}]  1つ選ぶ一覧（radio=既定の番号）。warn=赤い注意（消える物など）
 *   checks   [{main, sub, sub2, warn, checked, disabled}]  チェックの一覧
 *   note     一覧の下の注意（黄色）
 *   buttons  [{label, value, pri}]  Enter=pri のボタン
 *   cancel   Esc の値（既定 null）
 * 戻り値 Promise<{value, radio, checks:[bool]}>
 */
export function linkDialog(opts) {
  return new Promise(res => {
    const bg = mkEl('div'); bg.id = 'dirtyDlgBg';
    const dlg = mkEl('div', 'lkDlg'); dlg.id = 'dirtyDlg'; bg.appendChild(dlg);
    if (opts.kind) dlg.dataset.lk = opts.kind;
    if (opts.title) { const h = mkEl('div', 'ddMsg lkTitle', opts.title); dlg.appendChild(h); }
    for (const ln of (opts.lines || [])) if (ln) dlg.appendChild(mkEl('div', 'ddMsg lkLine', ln));
    let radio = opts.radios ? Math.max(0, Math.min(opts.radios.length - 1, opts.radio || 0)) : null;
    const radioEls = [], checkEls = [];
    const row = (it, type, i) => {
      const lab = mkEl('label', 'lkOpt' + (it.disabled ? ' dis' : ''));
      const inp = document.createElement('input'); inp.type = type; inp.name = 'lkOpt_' + type; inp.disabled = !!it.disabled;
      if (type === 'radio') { inp.checked = i === radio; inp.addEventListener('change', () => { if (inp.checked) radio = i; }); radioEls.push(inp); }
      else { inp.checked = !!it.checked && !it.disabled; checkEls.push(inp); }
      const body = mkEl('span', 'lkOptBody');
      body.appendChild(mkEl('span', 'lkOptMain', it.main || ''));
      if (it.sub) body.appendChild(mkEl('span', 'lkOptSub', it.sub));
      if (it.sub2) body.appendChild(mkEl('span', 'lkOptSub', it.sub2));
      if (it.warn) body.appendChild(mkEl('span', 'lkOptWarn', it.warn));
      lab.append(inp, body); return lab;
    };
    if (opts.radios) { const box = mkEl('div', 'lkOpts'); opts.radios.forEach((it, i) => box.appendChild(row(it, 'radio', i))); dlg.appendChild(box); }
    if (opts.checks) { const box = mkEl('div', 'lkOpts'); opts.checks.forEach((it, i) => box.appendChild(row(it, 'checkbox', i))); dlg.appendChild(box); }
    if (opts.note) dlg.appendChild(mkEl('div', 'ddMsg lkNote', opts.note));
    const btns = mkEl('div', 'ddBtns'); dlg.appendChild(btns);
    const done = v => { removeEventListener('keydown', onKey, true); bg.remove();
      res({ value: v, radio, checks: checkEls.map(c => c.checked) }); };
    let pri = null;
    for (const b of (opts.buttons || [])) {
      const el = mkEl('button', b.pri ? 'pri' : '', b.label);
      if (b.value != null) el.dataset.v = String(b.value);
      el.addEventListener('click', () => done(b.value));
      btns.appendChild(el); if (b.pri && !pri) pri = el;
    }
    const cancel = ('cancel' in opts) ? opts.cancel : null;
    const onKey = e => {
      if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); done(cancel); }
      else if (e.key === 'Enter' && pri) { e.preventDefault(); e.stopPropagation(); pri.click(); }
      else e.stopPropagation();   // 裏のショートカットを発火させない
    };
    addEventListener('keydown', onKey, true);
    document.body.appendChild(bg);
    const f = pri || btns.firstChild; if (f) f.focus();
  });
}

/**
 * 小さな帯（画面を塞がない・少しで消える）。単独編集の帯（#eoBand）と同じ見た目。
 * opts: {msg, buttons:[{label, cls, fn}], anchor: 帯を出すペインの要素, ms: 消えるまで（0=消えない）, kind: data-lk}
 * ボタンを押すと帯は消えてから fn を呼ぶ。
 */
let _bandT = null;
export function linkBand(opts) {
  let el = document.getElementById('lkBand');
  if (!el) {
    el = mkEl('div'); el.id = 'lkBand';
    el.addEventListener('pointerenter', () => clearTimeout(_bandT));   // 帯の上にマウスがある間は消さない
    el.addEventListener('pointerleave', () => { if (el.classList.contains('on') && el._ms) _arm(2500); });
    el.addEventListener('pointerdown', e => e.stopPropagation());   // 下の3D/NLEの操作を始めない
    document.body.appendChild(el);
  }
  el.textContent = '';
  el.dataset.lk = opts.kind || '';
  el.appendChild(mkEl('span', 'lkMsg', opts.msg || ''));
  for (const b of (opts.buttons || [])) {
    const bt = mkEl('button', b.cls || '', b.label);
    bt.addEventListener('click', () => { hideLinkBand(); if (b.fn) b.fn(); });
    el.appendChild(bt);
  }
  el.classList.add('on');
  const r = opts.anchor && opts.anchor.getBoundingClientRect ? opts.anchor.getBoundingClientRect() : { left: 0, top: 0, width: innerWidth, height: innerHeight };
  el.style.maxWidth = Math.max(240, r.width - 40) + 'px';
  el.style.left = (r.left + r.width / 2) + 'px';
  el.style.top = (r.top + (opts.top != null ? opts.top : 50)) + 'px';
  el._ms = opts.ms == null ? 7000 : opts.ms;
  if (el._ms) _arm(el._ms); else clearTimeout(_bandT);
  return el;
}
function _arm(ms) { clearTimeout(_bandT); _bandT = setTimeout(hideLinkBand, ms); }
export function hideLinkBand() { clearTimeout(_bandT); _bandT = null; const el = document.getElementById('lkBand'); if (el) el.classList.remove('on'); }
export function linkBandShown() { const el = document.getElementById('lkBand'); return !!(el && el.classList.contains('on')); }

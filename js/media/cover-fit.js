// カバー画像の補正（BeatLeaderの基準: 正方形・256×256以上・png/jpg）。
// 元の画像ファイルは変えない。カバーノードの data.fit={mode,bg} を見て、書き出し・譜面チェックの時にだけ補正した画像を作る
// （元ファイルへは書き込めない＝app.pyの_NativeAccess。補正済みの画像に差し替えると開き直した時に nativePath の元画像へ戻るため）。

export const COVER_MIN = 256;
export const COVER_MODES = ['crop', 'stretch', 'pad'];   // 中央を切り抜く（既定）/ 引き伸ばす / 余白で埋める
const OK_EXT = /\.(png|jpe?g)$/i;
const JPG_EXT = /\.jpe?g$/i;
const HEX = /^#[0-9a-f]{6}$/i;
const WARN_LOSS = 0.05;   // 切り抜きで失う割合がこれ以上なら確認画面で注意を出す

/** 基準に合わない所（寸法と元のファイル名から） */
export function coverProblems(w, h, name) {
  return { ratio: w !== h, small: w < COVER_MIN || h < COVER_MIN, format: !!name && !OK_EXT.test(name) };
}
export const coverNeedsFix = (w, h, name) => { const p = coverProblems(w, h, name); return p.ratio || p.small || p.format; };

/** 補正後の一辺。切り抜き=短い辺 / 引き伸ばし・余白=長い辺（どれも256未満なら256へ拡大） */
export const coverFitSize = (w, h, mode) => Math.max(COVER_MIN, mode === 'crop' ? Math.min(w, h) : Math.max(w, h));

/** 補正後のファイル名。jpgはjpgのまま、それ以外（webp/gif/bmp等）はpngにする */
export const coverFitName = name => (String(name || 'cover').replace(/\.[^.]*$/, '') || 'cover') + (JPG_EXT.test(name || '') ? '.jpg' : '.png');

const normFit = fit => ({ mode: COVER_MODES.includes(fit && fit.mode) ? fit.mode : 'crop', bg: fit && HEX.test(fit.bg || '') ? fit.bg : '#000000' });

/** bmp(ImageBitmap)を補正した canvas を返す */
function drawFit(bmp, fit, name) {
  const { mode, bg } = normFit(fit), w = bmp.width, h = bmp.height, S = coverFitSize(w, h, mode);
  const cv = document.createElement('canvas'); cv.width = cv.height = S;
  const g = cv.getContext('2d'); g.imageSmoothingQuality = 'high';
  if (mode === 'pad' || JPG_EXT.test(name || '')) { g.fillStyle = bg; g.fillRect(0, 0, S, S); }   // jpgは透過できないので下地を塗る
  if (mode === 'crop') { const m = Math.min(w, h); g.drawImage(bmp, Math.floor((w - m) / 2), Math.floor((h - m) / 2), m, m, 0, 0, S, S); }
  else if (mode === 'stretch') g.drawImage(bmp, 0, 0, S, S);
  else { const k = S / Math.max(w, h), dw = Math.round(w * k), dh = Math.round(h * k); g.drawImage(bmp, Math.floor((S - dw) / 2), Math.floor((S - dh) / 2), dw, dh); }
  return cv;
}

/** 補正後の寸法と名前だけ求める（譜面チェック用。画像は作らない）→ {name, w, h, fixed} */
export async function measureCoverFit(file, fit) {
  const name = file.name || 'cover.png';
  const bmp = await createImageBitmap(file);
  try {
    const w = bmp.width, h = bmp.height;
    if (!fit || !coverNeedsFix(w, h, name)) return { name, w, h, fixed: false };
    const S = coverFitSize(w, h, normFit(fit).mode);
    return { name: coverFitName(name), w: S, h: S, fixed: true };
  } finally { if (bmp.close) bmp.close(); }
}

/**
 * file(File/Blob)を fit で補正する → {blob, name, w, h, fixed}
 * fit が無い・直す所が無い時は元のファイルをそのまま返す（寸法は測る）。デコードできない画像は例外
 */
export async function fitCoverImage(file, fit) {
  const name = file.name || 'cover.png';
  const bmp = await createImageBitmap(file);
  try {
    const w = bmp.width, h = bmp.height;
    if (!fit || !coverNeedsFix(w, h, name)) return { blob: file, name, w, h, fixed: false };
    const cv = drawFit(bmp, fit, name), out = coverFitName(name);
    const blob = await new Promise((res, rej) => cv.toBlob(b => b ? res(b) : rej(new Error('encode-failed')), JPG_EXT.test(out) ? 'image/jpeg' : 'image/png', 0.92));
    return { blob, name: out, w: cv.width, h: cv.height, fixed: true };
  } finally { if (bmp.close) bmp.close(); }
}

/**
 * 補正の確認ダイアログ（見た目は未保存確認 #dirtyDlg と同じ部品）。
 * bmp=元画像（閉じる時に close する）/ name=元のファイル名 / fit=今の設定 / 決定で onOk({mode,bg})
 */
export function showCoverFitDialog({ t, tf, bmp, name, fit, onOk }) {
  const w = bmp.width, h = bmp.height, pr = coverProblems(w, h, name);
  let cur = normFit(fit);
  const bg = document.createElement('div'); bg.id = 'dirtyDlgBg';
  const dlg = document.createElement('div'); dlg.id = 'dirtyDlg'; bg.appendChild(dlg);
  const div = (cls, text) => { const d = document.createElement('div'); if (cls) d.className = cls; if (text != null) d.textContent = text; return d; };
  const head = div('ddMsg', t('cf.title', 'カバー画像の補正')); head.style.fontWeight = '700';
  const probs = [pr.ratio && t('cf.pRatio', '正方形でない'), pr.small && tf('cf.pSmall', '{n}×{n}より小さい', { n: COVER_MIN }),
    pr.format && t('cf.pFormat', '形式が png/jpg でない')].filter(Boolean).join(' / ');
  const msg = div('ddMsg', tf('cf.body', '今の画像: {name}（{w}×{h}）\n合わない所: {probs}\n\n元の画像ファイルは変えません。書き出す時（と譜面チェック）だけ補正した画像を使います。INFOのカバー画像ノードでいつでも元に戻せます。',
    { name, w, h, probs }));
  dlg.append(head, msg);

  // 補正のしかた（正方形にする必要がある時だけ選べる。形式・大きさだけなら どれでも同じ）
  const modes = div('cfModes'); modes.style.cssText = 'display:flex;flex-direction:column;gap:4px;margin:-6px 0 12px;';
  const color = document.createElement('input'); color.type = 'color'; color.value = cur.bg; color.style.cssText = 'width:34px;height:20px;padding:0;border:1px solid #55555e;background:none;margin-left:6px;vertical-align:middle;';
  const labs = { crop: t('cf.mCrop', '中央を切り抜く（絵は歪まない・端が少し欠ける）'), stretch: t('cf.mStretch', '引き伸ばす（全体が残る・少し歪む）'),
    pad: t('cf.mPad', '余白で埋める（全体が残る・余白の色:）') };
  if (pr.ratio) {
    for (const m of COVER_MODES) {
      const l = document.createElement('label'); l.style.cssText = 'display:flex;align-items:center;gap:6px;cursor:pointer;font-size:12.5px;';
      const r = document.createElement('input'); r.type = 'radio'; r.name = 'cfMode'; r.value = m; r.checked = cur.mode === m;
      r.addEventListener('change', () => { if (r.checked) { cur = { ...cur, mode: m }; update(); } });
      l.append(r, document.createTextNode(labs[m])); if (m === 'pad') l.appendChild(color);
      modes.appendChild(l);
    }
    color.addEventListener('input', () => { cur = { ...cur, bg: color.value }; update(); });
    dlg.appendChild(modes);
  }
  // 補正後の見本と寸法
  const prev = div(); prev.style.cssText = 'display:flex;gap:12px;align-items:center;margin-bottom:16px;';
  const box = div(); box.style.cssText = 'width:120px;height:120px;flex:0 0 auto;background:repeating-conic-gradient(#3a3a40 0 25%,#2c2c31 0 50%) 0 0/12px 12px;border:1px solid #44444c;border-radius:4px;display:flex;align-items:center;justify-content:center;';
  const res = div(); res.style.cssText = 'font-size:12.5px;line-height:1.6;white-space:pre-line;';
  prev.append(box, res); dlg.appendChild(prev);
  function update() {
    const cv = drawFit(bmp, cur, name); cv.style.cssText = 'max-width:100%;max-height:100%;display:block;';
    box.replaceChildren(cv);
    let s = tf('cf.result', '補正後: {name}（{s}×{s}）', { name: coverFitName(name), s: cv.width });
    const loss = 1 - Math.min(w, h) / Math.max(w, h);
    if (cur.mode === 'crop' && loss >= WARN_LOSS) s += '\n' + tf('cf.lossWarn', '⚠ 長い辺の {p}% を切り落とします。絵が大きく欠ける時は「余白で埋める」を選んでください', { p: Math.round(loss * 100) });
    else if (cur.mode === 'stretch' && loss >= WARN_LOSS) s += '\n' + tf('cf.stretchWarn', '⚠ 縦横比が {p}% 変わります', { p: Math.round(loss * 100) });
    res.textContent = s;
  }
  update();

  const row = div('ddBtns'); dlg.appendChild(row);
  const done = ok => { removeEventListener('keydown', onKey, true); bg.remove(); if (bmp.close) bmp.close(); if (ok) onOk(pr.ratio ? cur : { mode: 'crop', bg: cur.bg }); };
  const mk = (label, cls, fn) => { const b = document.createElement('button'); b.textContent = label; if (cls) b.className = cls; b.addEventListener('click', fn); row.appendChild(b); return b; };
  const bOk = mk(t('cf.apply', '補正する'), 'pri', () => done(true));
  mk(t('word.cancel', 'キャンセル'), '', () => done(false));
  const onKey = e => {
    if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); done(false); }
    else if (e.key === 'Enter' && !(e.target && e.target.type === 'color')) { e.preventDefault(); e.stopPropagation(); done(true); }
    else e.stopPropagation();   // 裏のショートカットを発火させない
  };
  addEventListener('keydown', onKey, true);
  document.body.appendChild(bg); bOk.focus();
}

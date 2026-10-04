// 画面の崩れ確認（tests/visual）のうち、ページ内で動かす部品。vislib.py が読み込んで評価する。
// アプリ本体には何も足さない（window.__vis に置くだけ。ページを開き直せば消える）。
//   freeze()      アニメーション・トランジション・カーソル点滅を止める
//   hide(sels)    撮影の間だけ隠す要素（3Dビューの canvas など揺れる所）
//   rects(sels)   要素の位置（比較から除く領域を求める）
//   layout(cfg)   崩れの検出（重なり・はみ出し・文字の切れ・大きさ0・隠れ）
//   mark(items)   崩れの位置に赤枠を重ねる（撮影用・unmark で消す）
//   compare / compose / stack   画像の比較・まとめ画像の合成（canvas で行う。画像は URL で渡す）
(() => {
  const V = window.__vis = {};

  // ---- 撮影の準備 ----
  const styleEl = (id) => {
    let s = document.getElementById(id);
    if (!s) { s = document.createElement('style'); s.id = id; document.head.appendChild(s); }
    return s;
  };
  V.freeze = () => {
    styleEl('__visFreeze').textContent =
      '*,*::before,*::after{animation:none!important;transition:none!important;caret-color:transparent!important;scroll-behavior:auto!important}';
    // 下の3Dビュー（#cv）は撮影時に隠すので描画を止める。GPUの無いヘッドレスではソフトウェア描画がページを占有し、
    // 撮影・入力の1回ごとに1〜2秒かかっていた（止めると0.2秒程度）。描画ループ自体は回り続ける（2Dのキャンバスは更新される）
    try {
      const r = window._dbg && window._dbg.rt && window._dbg.rt.renderer;
      if (r && !r.__visOrigRender) { r.__visOrigRender = r.render; r.render = () => {}; }
    } catch (_) {}
    return true;
  };
  V.hide = (sels) => {
    styleEl('__visHide').textContent = sels && sels.length ? sels.join(',') + '{visibility:hidden!important}' : '';
    return true;
  };
  V.rects = (sels) => {
    const out = [];
    for (const s of sels || []) {
      for (const e of document.querySelectorAll(s)) {
        const r = e.getBoundingClientRect();
        if (r.width > 0 && r.height > 0) out.push([Math.floor(r.left), Math.floor(r.top), Math.ceil(r.width) + 1, Math.ceil(r.height) + 1]);
      }
    }
    return out;
  };

  // ---- 崩れの検出 ----
  // 操作部品（重なり・はみ出し・大きさ0・隠れの対象）
  const CTRL = 'button,input:not([type=hidden]),select,textarea,[role=button],a[href],label,[data-act],.bfField,.dfSeg,.tbi,.mbtn';
  const isVis = (e) => e.checkVisibility({ opacityProperty: true, visibilityProperty: true });
  const inter = (a, b) => {
    const x0 = Math.max(a.left, b.left), y0 = Math.max(a.top, b.top);
    const x1 = Math.min(a.right, b.right), y1 = Math.min(a.bottom, b.bottom);
    return { left: x0, top: y0, right: x1, bottom: y1, width: Math.max(0, x1 - x0), height: Math.max(0, y1 - y0) };
  };
  const R = (r) => [Math.round(r.left), Math.round(r.top), Math.round(r.width), Math.round(r.height)];
  // 要素の呼び名: 「#一番近いidの祖先 タグ#id.class[data-*]「文字」」。許可リストはこれの部分一致で書く
  const desc = (e) => {
    if (!e || e.nodeType !== 1) return '';
    let s = e.tagName.toLowerCase();
    if (e.id) s += '#' + e.id;
    const cls = [...e.classList].filter(c => !/^(on|hover|active|sel|subOpen)$/.test(c)).slice(0, 3);
    if (cls.length) s += '.' + cls.join('.');
    for (const a of ['data-act', 'data-tab', 'data-d', 'data-k', 'data-b', 'data-f', 'data-panel', 'type']) {
      const v = e.getAttribute(a);
      if (v != null && v !== '') s += `[${a}=${v}]`;
    }
    if (!e.id) {
      const anc = e.parentElement && e.parentElement.closest('[id]');
      if (anc && anc !== document.body) s = '#' + anc.id + ' ' + s;
    }
    const tx = (e.innerText || e.value || e.title || '').replace(/\s+/g, ' ').trim().slice(0, 18);
    if (tx) s += `「${tx}」`;
    return s;
  };
  // 見えている範囲（画面と、overflow で切り取る祖先との共通部分）。hard=hidden/clip の祖先だけ（スクロールする箱は除く）
  const clipOf = (e, hardOnly) => {
    let r = { left: 0, top: 0, right: innerWidth, bottom: innerHeight }, by = null;
    for (let a = e.parentElement; a && a !== document.documentElement; a = a.parentElement) {
      const cs = getComputedStyle(a);
      if (cs.position === 'fixed') {   // fixed の要素はそれより外の祖先に切り取られない（transform 等の例外は扱わない）
        if (cs.overflowX !== 'visible' || cs.overflowY !== 'visible') {
          const hard = !/(auto|scroll)/.test(cs.overflowX + cs.overflowY);
          if (!hardOnly || hard) { r = inter(r, a.getBoundingClientRect()); by = by || a; }
        }
        break;
      }
      if (cs.overflowX === 'visible' && cs.overflowY === 'visible') continue;
      const hard = !/(auto|scroll)/.test(cs.overflowX + cs.overflowY);
      if (hardOnly && !hard) continue;
      const ar = a.getBoundingClientRect();
      // 内側（padding の内側＝ボーダーを除く）で切り取られる
      const bl = parseFloat(cs.borderLeftWidth) || 0, bt = parseFloat(cs.borderTopWidth) || 0;
      const inner = { left: ar.left + bl, top: ar.top + bt, right: ar.left + bl + a.clientWidth, bottom: ar.top + bt + a.clientHeight };
      if (a.clientWidth === 0 && a.clientHeight === 0) continue;   // 大きさ0の入れ物（項目だけが見える作り）
      const ni = inter(r, cs.overflowX === 'visible' ? { ...inner, left: -1e9, right: 1e9 } : cs.overflowY === 'visible' ? { ...inner, top: -1e9, bottom: 1e9 } : inner);
      if (ni.width < r.right - r.left || ni.height < r.bottom - r.top) by = by || a;
      r = ni;
    }
    r.width = Math.max(0, r.right - r.left); r.height = Math.max(0, r.bottom - r.top);
    return { r, by };
  };
  // 浮いている層（メニュー・ダイアログ・パネル）。違う層どうしの重なりは「意図して上に出している」とみなす
  const layerOf = (e, popRoots) => {
    for (let a = e; a && a !== document.body; a = a.parentElement) {
      if (popRoots.has(a)) return a;
      if (getComputedStyle(a).position === 'fixed') return a;
    }
    return null;
  };
  V.layout = (cfg) => {
    cfg = cfg || {};
    const TOL = cfg.tol || 2;           // はみ出し・切れの許容（px）
    const OVL = cfg.overlap || 3;       // 重なりとみなす最小の幅・高さ（px）
    const popRoots = new Set((cfg.popups || []).flatMap(s => [...document.querySelectorAll(s)]));
    const ignore = (cfg.ignore || []).join(',');
    const issues = [];
    const add = (kind, a, b, rect, detail) => issues.push({ kind, a: desc(a), b: b ? desc(b) : '', rect: R(rect), detail: detail || '' });

    // 1) 操作部品
    const ctrls = [];
    for (const e of document.querySelectorAll(CTRL)) {
      if (ignore && e.closest(ignore)) continue;
      if (e.closest('#uiStash')) continue;   // 隠し置き場（display:none）
      if (!isVis(e)) continue;
      const r = e.getBoundingClientRect();
      const { r: clip, by } = clipOf(e, false);
      const vis = inter(r, clip);
      if (r.width < 2 || r.height < 2) {
        // 表示中なのに大きさ0（中身が空の飾り要素は除く）
        if ((e.innerText || e.value || '').trim() || e.matches('button,input,select,textarea')) {
          if (vis.width >= 0 && clip.width > 0) add('大きさ0', e, null, r, `${r.width.toFixed(0)}×${r.height.toFixed(0)}px`);
        }
        continue;
      }
      if (vis.width < 1 || vis.height < 1) continue;   // スクロールや折りたたみで全部隠れている＝見えていない
      ctrls.push({ e, r, vis });
      // 画面からのはみ出し
      if (r.left < -TOL || r.top < -TOL || r.right > innerWidth + TOL || r.bottom > innerHeight + TOL) {
        add('画面からはみ出し', e, null, r, `画面 ${innerWidth}×${innerHeight}`);
        continue;
      }
      // パネル（overflow:hidden の祖先）で一部が切れている
      const { r: hard, by: hb } = clipOf(e, true);
      if (r.left < hard.left - TOL || r.top < hard.top - TOL || r.right > hard.right + TOL || r.bottom > hard.bottom + TOL) {
        add('パネルからはみ出し', e, hb, r, '切り取る箱: ' + desc(hb));
      }
    }
    // 2) 操作部品どうしの重なり（同じ層の中だけ）
    for (let i = 0; i < ctrls.length; i++) {
      const A = ctrls[i];
      for (let j = i + 1; j < ctrls.length; j++) {
        const B = ctrls[j];
        if (A.e.contains(B.e) || B.e.contains(A.e)) continue;
        const ov = inter(A.vis, B.vis);
        if (ov.width < OVL || ov.height < OVL) continue;
        if (layerOf(A.e, popRoots) !== layerOf(B.e, popRoots)) continue;
        // label と、その label が指す入力欄
        if ((A.e.tagName === 'LABEL' && A.e.control === B.e) || (B.e.tagName === 'LABEL' && B.e.control === A.e)) continue;
        add('重なり', A.e, B.e, ov, `${Math.round(ov.width)}×${Math.round(ov.height)}px`);
      }
    }
    // 3) 他の要素に隠れている（中心を指した時に一番上にあるのが自分でも浮いている層でもない）
    for (const C of ctrls) {
      const x = (C.vis.left + C.vis.right) / 2, y = (C.vis.top + C.vis.bottom) / 2;
      const hit = document.elementFromPoint(x, y);
      if (!hit || C.e.contains(hit) || hit.contains(C.e)) continue;
      if (hit.closest('label') && hit.closest('label').contains(C.e)) continue;
      const lh = layerOf(hit, popRoots), lc = layerOf(C.e, popRoots);
      if (lh && lh !== lc) continue;   // メニュー・ダイアログが上に出ている
      if (C.e.tagName === 'LABEL' && C.e.control && (C.e.control === hit || C.e.control.contains(hit))) continue;
      add('隠れ', C.e, hit, C.vis, '上にあるもの: ' + desc(hit));
    }
    // 4) 文字の切れ・はみ出し（文字のある要素すべて）
    const tw = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    const range = document.createRange();
    const seen = new Set();
    for (let n = tw.nextNode(); n; n = tw.nextNode()) {
      if (!n.nodeValue.trim()) continue;
      const pe = n.parentElement;
      if (!pe || pe.closest('svg,script,style,option,textarea,#uiStash')) continue;
      if (ignore && pe.closest(ignore)) continue;
      if (!isVis(pe)) continue;
      // 文字が入っている箱（inline でない一番近い祖先）
      let box = pe;
      while (box && box !== document.body && /^(inline|contents)$/.test(getComputedStyle(box).display)) box = box.parentElement;
      if (!box || seen.has(box)) continue;
      range.selectNodeContents(n);
      const tr = range.getBoundingClientRect();
      if (tr.width < 1 || tr.height < 1) continue;
      const { r: clip, by } = clipOf(pe, false);
      const csb = getComputedStyle(box);
      const own = csb.overflowX !== 'visible' || csb.overflowY !== 'visible';
      // 自分自身の overflow も切り取りに含める
      let c2 = clip, by2 = by;
      if (own) {
        const br = box.getBoundingClientRect(), bl = parseFloat(csb.borderLeftWidth) || 0, bt = parseFloat(csb.borderTopWidth) || 0;
        const ni = inter(c2, { left: br.left + bl, top: br.top + bt, right: br.left + bl + box.clientWidth, bottom: br.top + bt + box.clientHeight });
        if (ni.width < c2.width || ni.height < c2.height) by2 = box;
        c2 = ni;
      }
      const vis = inter(tr, c2);
      if (vis.width < 1 || vis.height < 1) continue;   // 全部隠れている（スクロール外など）
      const cutX = tr.left < c2.left - TOL || tr.right > c2.right + TOL;
      const cutY = tr.top < c2.top - TOL - 1 || tr.bottom > c2.bottom + TOL + 1;   // 縦は行の高さの丸めで1px出やすい
      if (cutX || cutY) {
        seen.add(box);
        const ell = csb.textOverflow === 'ellipsis' && cutX;
        add(ell ? '文字の省略(…)' : '文字の切れ', box, by2 && by2 !== box ? by2 : null, tr,
          `文字 ${Math.round(tr.width)}×${Math.round(tr.height)} / 見える幅 ${Math.round(vis.width)}×${Math.round(vis.height)}`);
        continue;
      }
      // 操作部品・枠や背景のある箱から文字が外へはみ出している（切れてはいないが枠を越えている）
      const br = box.getBoundingClientRect();
      if (br.width < 2 || br.height < 2) continue;
      const framed = box.matches(CTRL) || (csb.borderTopStyle !== 'none' && parseFloat(csb.borderTopWidth) > 0) ||
        (csb.backgroundColor && !/rgba\(0, 0, 0, 0\)|transparent/.test(csb.backgroundColor));
      if (framed && (tr.left < br.left - TOL || tr.right > br.right + TOL || tr.top < br.top - TOL - 1 || tr.bottom > br.bottom + TOL + 1)) {
        seen.add(box);
        add('文字のはみ出し', box, null, tr, `箱 ${Math.round(br.width)}×${Math.round(br.height)} / 文字 ${Math.round(tr.width)}×${Math.round(tr.height)}`);
      }
    }
    return issues;
  };

  V.mark = (items) => {
    V.unmark();
    for (const it of items) {
      const [x, y, w, h] = it.rect;
      const b = document.createElement('div');
      b.className = '__visMark';
      Object.assign(b.style, { position: 'fixed', left: (x - 2) + 'px', top: (y - 2) + 'px', width: (w + 4) + 'px', height: (h + 4) + 'px',
        border: '2px solid #ff2050', boxShadow: '0 0 0 1px #000', pointerEvents: 'none', zIndex: 2147483647, boxSizing: 'border-box' });
      const n = document.createElement('div');
      n.className = '__visMark';
      n.textContent = it.label;
      Object.assign(n.style, { position: 'fixed', left: Math.max(0, x - 2) + 'px', top: Math.max(0, y - 18) + 'px', background: '#ff2050', color: '#fff',
        font: 'bold 11px/16px sans-serif', padding: '0 4px', pointerEvents: 'none', zIndex: 2147483647 });
      document.body.append(b, n);
    }
    return true;
  };
  V.unmark = () => { document.querySelectorAll('.__visMark').forEach(e => e.remove()); return true; };

  // ---- 画像の比較・合成 ----
  // 画像はページと同じサーバー（serve.py＝プロジェクトのフォルダ）から URL で読む。
  // CDP で画像を送り込むと cdp.py の送信（1バイトずつのマスク処理）が遅いため
  const load = async (src) => createImageBitmap(await (await fetch(src, { cache: 'no-store' })).blob());
  const pixels = (bmp) => {
    const c = new OffscreenCanvas(bmp.width, bmp.height), g = c.getContext('2d', { willReadFrequently: true });
    g.drawImage(bmp, 0, 0);
    return g.getImageData(0, 0, bmp.width, bmp.height);
  };
  const toB64 = async (canvas) => {
    const blob = await canvas.convertToBlob({ type: 'image/png' });
    const buf = new Uint8Array(await blob.arrayBuffer());
    let s = '';
    for (let i = 0; i < buf.length; i += 0x8000) s += String.fromCharCode.apply(null, buf.subarray(i, i + 0x8000));
    return btoa(s);
  };
  // 変化した画素の地図を作り、近いものをまとめて領域にする
  const diffMap = (A, B, masks, thr) => {
    const w = Math.min(A.width, B.width), h = Math.min(A.height, B.height);
    const W = Math.max(A.width, B.width), H = Math.max(A.height, B.height);
    const m = new Uint8Array(W * H);   // 1=変化 2=除外
    for (const [x, y, mw, mh] of masks) {
      for (let yy = Math.max(0, y); yy < Math.min(H, y + mh); yy++) m.fill(2, yy * W + Math.max(0, x), yy * W + Math.min(W, x + mw));
    }
    let n = 0;
    const a = A.data, b = B.data;
    for (let y = 0; y < H; y++) {
      for (let x = 0; x < W; x++) {
        const k = y * W + x;
        if (m[k] === 2) continue;
        if (x >= w || y >= h) { m[k] = 1; n++; continue; }   // 大きさが違う＝はみ出た所は全部変化
        const ia = (y * A.width + x) * 4, ib = (y * B.width + x) * 4;
        const d = Math.max(Math.abs(a[ia] - b[ib]), Math.abs(a[ia + 1] - b[ib + 1]), Math.abs(a[ia + 2] - b[ib + 2]));
        if (d > thr) { m[k] = 1; n++; }
      }
    }
    return { m, W, H, n };
  };
  const regionsOf = (m, W, H, tile, gap, maxN) => {
    const TW = Math.ceil(W / tile), TH = Math.ceil(H / tile);
    const cnt = new Int32Array(TW * TH);
    for (let y = 0; y < H; y++) for (let x = 0; x < W; x++) if (m[y * W + x] === 1) cnt[((y / tile) | 0) * TW + ((x / tile) | 0)]++;
    const lab = new Int32Array(TW * TH).fill(-1), regs = [];
    for (let i = 0; i < TW * TH; i++) {
      if (!cnt[i] || lab[i] >= 0) continue;
      const id = regs.length, st = [i];
      lab[i] = id;
      const rg = { tx0: 1e9, ty0: 1e9, tx1: -1, ty1: -1, n: 0 };
      while (st.length) {
        const k = st.pop(), tx = k % TW, ty = (k / TW) | 0;
        rg.n += cnt[k]; rg.tx0 = Math.min(rg.tx0, tx); rg.ty0 = Math.min(rg.ty0, ty); rg.tx1 = Math.max(rg.tx1, tx); rg.ty1 = Math.max(rg.ty1, ty);
        for (let dy = -gap; dy <= gap; dy++) for (let dx = -gap; dx <= gap; dx++) {
          const nx = tx + dx, ny = ty + dy;
          if (nx < 0 || ny < 0 || nx >= TW || ny >= TH) continue;
          const q = ny * TW + nx;
          if (cnt[q] && lab[q] < 0) { lab[q] = id; st.push(q); }
        }
      }
      regs.push(rg);
    }
    regs.sort((p, q) => q.n - p.n);
    const out = regs.map(rg => ({ x: rg.tx0 * tile, y: rg.ty0 * tile, w: Math.min(W, (rg.tx1 + 1) * tile) - rg.tx0 * tile,
      h: Math.min(H, (rg.ty1 + 1) * tile) - rg.ty0 * tile, n: rg.n }));
    return { regions: out.slice(0, maxN), rest: out.slice(maxN).reduce((s, r) => s + r.n, 0), total: out.length };
  };
  // opt: {thr, tile, gap, maxRegions}
  V.compare = async (srcA, srcB, masks, opt) => {
    opt = opt || {};
    const [ba, bb] = await Promise.all([load(srcA), load(srcB)]);
    const A = pixels(ba), B = pixels(bb);
    const { m, W, H, n } = diffMap(A, B, masks || [], opt.thr ?? 32);
    const rg = n ? regionsOf(m, W, H, opt.tile || 8, opt.gap ?? 4, opt.maxRegions || 6) : { regions: [], rest: 0, total: 0 };
    return { n, w: W, h: H, sizeA: [A.width, A.height], sizeB: [B.width, B.height], ...rg };
  };

  // 差分の画像: 後の画像を暗い灰色にし、変化した画素を赤、除外領域を斜線にする
  const diffImage = (A, B, m, W, H) => {
    const out = new ImageData(W, H), o = out.data, b = B.data;
    for (let y = 0; y < H; y++) for (let x = 0; x < W; x++) {
      const k = y * W + x, i = k * 4;
      if (m[k] === 1) { o[i] = 255; o[i + 1] = 30; o[i + 2] = 60; o[i + 3] = 255; continue; }
      let v = 0;
      if (x < B.width && y < B.height) { const ib = (y * B.width + x) * 4; v = (b[ib] * 0.3 + b[ib + 1] * 0.59 + b[ib + 2] * 0.11) * 0.35; }
      if (m[k] === 2 && ((x + y) & 15) < 2) v = 90;
      o[i] = o[i + 1] = o[i + 2] = v; o[i + 3] = 255;
    }
    return out;
  };
  const FONT = '"Yu Gothic UI","Meiryo",sans-serif';
  // 1画面ぶんのまとめ画像（領域ごとに 位置 | 前 | 後 | 差分 の1行）と、画面全体の差分画像を作る
  V.compose = async (srcA, srcB, masks, info, opt) => {
    opt = opt || {};
    const [ba, bb] = await Promise.all([load(srcA), load(srcB)]);
    const A = pixels(ba), B = pixels(bb);
    const { m, W, H, n } = diffMap(A, B, masks || [], opt.thr ?? 32);
    const { regions } = regionsOf(m, W, H, opt.tile || 8, opt.gap ?? 4, opt.maxRegions || 6);
    const dimg = diffImage(A, B, m, W, H);
    const dc = new OffscreenCanvas(W, H); dc.getContext('2d').putImageData(dimg, 0, 0);
    const MAXW = opt.maxWidth || 1800, GAP = 8, THUMB = 200, PAD = opt.pad || 40, MAXH = opt.maxPanelH || 420;
    const PW = Math.floor((MAXW - THUMB - GAP * 5) / 3);
    const rows = regions.map(r => {
      const x = Math.max(0, r.x - PAD), y = Math.max(0, r.y - PAD);
      const w = Math.min(W, r.x + r.w + PAD) - x, h = Math.min(H, r.y + r.h + PAD) - y;
      const s = Math.min(1, PW / w, MAXH / h);
      return { r, x, y, w, h, s, ph: Math.ceil(h * s) };
    });
    const HEAD = 30, SUB = 18;
    const thumbH = Math.ceil(H * THUMB / W);
    const totalH = HEAD + rows.reduce((t, row) => t + SUB + Math.max(row.ph, thumbH) + GAP, 0) + GAP;
    const c = new OffscreenCanvas(MAXW, totalH), g = c.getContext('2d');
    g.fillStyle = '#111'; g.fillRect(0, 0, MAXW, totalH);
    g.fillStyle = '#ffd24a'; g.font = `bold 17px ${FONT}`; g.textBaseline = 'middle';
    g.fillText(info.title, GAP, HEAD / 2);
    const tw = g.measureText(info.title).width;
    g.fillStyle = '#bbb'; g.font = `13px ${FONT}`;
    g.fillText(info.sub || '', GAP + tw + 16, HEAD / 2);
    let yy = HEAD;
    rows.forEach((row, i) => {
      g.fillStyle = '#9ad'; g.font = `12px ${FONT}`;
      g.fillText(`領域${i + 1}`, GAP, yy + SUB / 2);
      const x0 = GAP + THUMB + GAP;
      const lab = [`前（基準） x${row.r.x} y${row.r.y} ${row.r.w}×${row.r.h}`, `後（今回）  変化 ${row.r.n}px` + (row.s < 1 ? `・表示 ${Math.round(row.s * 100)}%` : ''), '差分（赤＝変化・斜線＝比較から除外）'];
      lab.forEach((t, k) => { g.fillStyle = k === 2 ? '#f88' : '#ccc'; g.fillText(t, x0 + k * (PW + GAP), yy + SUB / 2); });
      yy += SUB;
      // 位置（全体の縮小図に赤枠）
      g.drawImage(bb, GAP, yy, THUMB, thumbH);
      g.strokeStyle = '#ff2050'; g.lineWidth = 2;
      const k = THUMB / W;
      g.strokeRect(GAP + row.r.x * k - 1, yy + row.r.y * k - 1, Math.max(3, row.r.w * k) + 2, Math.max(3, row.r.h * k) + 2);
      const pw = Math.ceil(row.w * row.s);
      [ba, bb, dc].forEach((src, j) => {
        const px = x0 + j * (PW + GAP);
        g.imageSmoothingEnabled = row.s < 1;
        g.drawImage(src, row.x, row.y, row.w, row.h, px, yy, pw, row.ph);
        g.strokeStyle = '#444'; g.lineWidth = 1; g.strokeRect(px - 0.5, yy - 0.5, pw + 1, row.ph + 1);
      });
      yy += Math.max(row.ph, thumbH) + GAP;
    });
    return { review: await toB64(c), diff: await toB64(dc), regions, n };
  };
  // 複数のまとめ画像を縦に積む
  V.stack = async (list, opt) => {
    opt = opt || {};
    const bmps = await Promise.all(list.map(load));
    const W = Math.max(...bmps.map(b => b.width)), GAP = 6;
    const H = bmps.reduce((t, b) => t + b.height + GAP, 0) + (opt.header ? 34 : 0);
    const c = new OffscreenCanvas(W, H), g = c.getContext('2d');
    g.fillStyle = '#000'; g.fillRect(0, 0, W, H);
    let y = 0;
    if (opt.header) {
      g.fillStyle = '#fff'; g.font = `bold 16px ${FONT}`; g.textBaseline = 'middle'; g.fillText(opt.header, 8, 17); y = 34;
    }
    for (const b of bmps) { g.drawImage(b, 0, y); y += b.height + GAP; }
    return await toB64(c);
  };
  return true;
})();

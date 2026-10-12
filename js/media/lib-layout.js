// MEDIA ライブラリの部品の配置（2026-10-12）:
//  - 見出しの行（#libHead）: 操作部品（フォルダを追加・検索・フィルター・件数・解除・表示の切り替え・大きさ）を、MEDIA [TAB] PREVIEW の帯
//    （#pvModeLabel。position:absolute で PREVIEW と共用）の右に並べ、入りきらない分だけ2行目へ折り返す（CSS の flex-wrap）。
//    行の先頭の空き（#libHeadGap）の幅＝帯の右端まで。帯の文字は言語で幅が変わるので、帯・行の大きさが変わるたびに測り直す（ResizeObserver）。
//  - 左のカタログ（#libSide）の幅: 境目（#libSideSplit）のドラッグで変える。最小 SIDE_MIN・最大は一覧の枠（#libBody）の半分。
//    bsnm_libSideW に保存（キーが無い＝SIDE_DEF）。境目のダブルクリックで元の幅に戻す（キーを消す）。
//    MEDIA を狭めて半分を超えた時は、保存した幅は変えずに表示だけ半分に抑える。
//  - UI文字サイズ（環境設定の bsnm_uiscale）は #tabFolder と帯に CSS の zoom として掛かる。getBoundingClientRect・マウスの座標は画面の px、
//    style に入れる幅・offsetWidth・clientWidth は zoom の掛かる前の CSS の px なので、画面の px は cssZoom で割ってから入れる
//    （割らないと 80% で帯と重なり、150% で段が増えた）。
export const SIDE_DEF = 176, SIDE_MIN = 100;
/** 要素に掛かっている CSS の zoom（祖先の分も掛け合わせた値。UI文字サイズ）。分からなければ 1 */
export const cssZoom = el => (el && typeof el.currentCSSZoom === 'number' && el.currentCSSZoom > 0) ? el.currentCSSZoom : 1;
const LS_SIDE = 'bsnm_libSideW';
const lsGet = k => { try { return localStorage.getItem(k); } catch (_) { return null; } };
const lsSet = (k, v) => { try { if (v == null) localStorage.removeItem(k); else localStorage.setItem(k, v); } catch (_) {} };

export function installLibLayout() {
  const $ = id => document.getElementById(id);
  const label = $('pvModeLabel'), head = $('libHead'), gap = $('libHeadGap');
  const side = $('libSide'), split = $('libSideSplit'), libBody = $('libBody');
  const RO = typeof ResizeObserver === 'function' ? ResizeObserver : null;

  // ---- 見出しの行の先頭の空き（帯の幅）----
  let gapW = null;
  const sep = head && head.querySelector('.libSep'), sbox = $('libSearchBox'), fbtn = $('libFiltBtn'), fclr = $('libFiltClear'), fgrp = $('libFiltGrp'),
    fview = $('libViewSeg'), fsz = $('libSizeGrp');
  function fitGap() {
    if (!label || !head || !gap) return;
    const lr = label.getBoundingClientRect(), hr = head.getBoundingClientRect();
    if (!lr.width || !hr.width) return;   // PREVIEW の間（MEDIA が隠れている）は測らない。MEDIA に戻ると行の大きさが変わって測り直す
    // 帯の右端＋6px（部品の間の 6px と合わせて帯から 12px 空ける）。画面の px を行の CSS の px へ直す（UI文字サイズ）
    const w = Math.max(0, Math.ceil((lr.right - hr.left) / cssZoom(head)) + 6);
    if (w !== gapW) { gapW = w; gap.style.width = w + 'px'; }
    fitGrpSoon();
    fitSep();
  }
  /** フィルター・件数・解除・表示の切り替え・大きさの組（#libFiltGrp。折り返す時は一緒に次の段へ。表示の切り替えと大きさは組の右端）: 折り返しを決める
   * 基準の幅＝フィルター・［解除］・表示の切り替え（#libViewSeg）・大きさ（#libSizeGrp）の幅と間（--lib-fb）＋件数の一番短い形の幅（--lib-cmin。lib-filter.js）。
   * ボタンの幅は言語・条件の数の丸で変わるので測って入れる（offsetWidth＝CSS の px） */
  let fbW = null;
  function fitGrp() {
    if (!fgrp || !fbtn || !fbtn.offsetWidth) return;
    const w = fbtn.offsetWidth + (fclr ? fclr.offsetWidth : 0) + (fview ? fview.offsetWidth + 6 : 0) + (fsz ? fsz.offsetWidth + 6 : 0) + 12;   // 組の中の間 6px×（部品の数−1）
    if (w !== fbW) { fbW = w; fgrp.style.setProperty('--lib-fb', w + 'px'); }
  }
  // ResizeObserver の中で組の基準の幅を変えると、同じ回の中で見出しの行（浅い要素）の大きさが変わって「ResizeObserver loop」になる＝次の描画の前へ回す
  let grpQ = false;
  function fitGrpSoon() { if (grpQ) return; grpQ = true; requestAnimationFrame(() => { grpQ = false; fitGrp(); fitSearch(); fitSep(); }); }
  /** 検索欄の折り返し: 基準の幅は 80px（CSS）。それだと「フォルダを追加」と同じ段に 80〜140px で細く押し込まれることがある
   * （MEDIA が 520px 付近など。案内が「曲名・…」だけになる）。次の段へ送っても段の数が増えない時だけ、基準を 140px にして送る
   * （既定の約 480px・UI文字サイズ 150% 等で次の段に入らない時・全部が1段に入りきる幅（100% で 820〜860px 付近）では、細くても今の段に残す＝段を増やさない）。
   * どの幅でも同じ並びから決め直す */
  const SEARCH_WIDE = 140;
  /** 段の数（部品の縦の中心で数える。上端で数えると、同じ段でも高さの違う部品（フォルダを追加 31px・検索欄 24px・区切り線）が別の段に数えられる） */
  function rowsOf() {
    const ys = [];
    for (const e of head.children) if (e !== gap && e.offsetWidth) { const r = e.getBoundingClientRect(); ys.push(r.top + r.height / 2); }
    ys.sort((a, b) => a - b);
    let n = 0, last = -1e9;
    for (const y of ys) if (y - last > 8) { n++; last = y; }
    return n;
  }
  function fitSearch() {
    if (!sbox || !head || !head.offsetWidth) return;   // PREVIEW の間は測らない
    sbox.style.flexBasis = '';
    if (sbox.offsetWidth >= SEARCH_WIDE) return;
    const n = rowsOf();
    sbox.style.flexBasis = SEARCH_WIDE + 'px';
    if (rowsOf() > n) sbox.style.flexBasis = '';
  }
  /** 検索欄とフィルターの間の区切り線は、両方と同じ段にある時だけ見せる（折り返しで段の端に来た線は消す。場所は残す＝並びが変わらない） */
  function fitSep() {
    if (!sep || !sbox || !fbtn) return;
    const mid = e => { const r = e.getBoundingClientRect(); return r.top + r.height / 2; };
    const m = mid(sep), same = Math.abs(mid(sbox) - m) < 6 && Math.abs(mid(fbtn) - m) < 6;
    sep.style.visibility = same ? '' : 'hidden';
  }
  if (RO) { const ro = new RO(() => fitGap()); for (const e of [label, head, fbtn, fclr, fview, fsz]) if (e) ro.observe(e); }
  try { document.fonts.ready.then(fitGap); } catch (_) {}
  fitGap(); fitGrp();

  // ---- 左のカタログの幅 ----
  let sideW = (() => { const v = +lsGet(LS_SIDE); return v >= SIDE_MIN ? Math.round(v) : SIDE_DEF; })();
  const maxW = () => Math.max(SIDE_MIN, Math.floor((libBody && libBody.clientWidth || 0) / 2));
  function applySide() {
    if (!side) return;
    const w = libBody && libBody.clientWidth ? Math.min(sideW, maxW()) : sideW;
    side.style.width = w + 'px';
  }
  if (split && side) {
    split.addEventListener('pointerdown', e => {
      if (e.button !== 0) return;
      e.preventDefault();
      try { split.setPointerCapture(e.pointerId); } catch (_) {}
      split.classList.add('drag');
      // 幅は CSS の px（offsetWidth）、マウスの動きは画面の px → zoom で割って CSS の px にそろえる（UI文字サイズ）
      const x0 = e.clientX, w0 = side.offsetWidth, z = cssZoom(side);
      let moved = false;
      const mv = ev => {
        if (!moved && Math.abs(ev.clientX - x0) < 2) return;
        moved = true;
        sideW = Math.max(SIDE_MIN, Math.min(maxW(), Math.round(w0 + (ev.clientX - x0) / z)));
        applySide();
      };
      const up = () => {
        split.classList.remove('drag');
        split.removeEventListener('pointermove', mv); split.removeEventListener('pointerup', up); split.removeEventListener('pointercancel', up);
        if (moved) lsSet(LS_SIDE, String(sideW));   // 動かさずに離した時（ダブルクリックの1回目など）は保存しない
      };
      split.addEventListener('pointermove', mv); split.addEventListener('pointerup', up); split.addEventListener('pointercancel', up);
    });
    split.addEventListener('dblclick', () => { sideW = SIDE_DEF; lsSet(LS_SIDE, null); applySide(); });
  }
  if (RO && libBody) new RO(() => applySide()).observe(libBody);
  applySide();

  return {
    fitGap,
    /** 開発用窓口（_dbgApp.lib().layout）用の複製 */
    dbg() {
      const lr = label ? label.getBoundingClientRect() : null, hr = head ? head.getBoundingClientRect() : null;
      return { gap: gapW, labelRight: lr ? lr.right : null, headLeft: hr ? hr.left : null, zoom: cssZoom(head),
        sideW, sideShown: side ? side.offsetWidth : null, sideMax: maxW(), sideDef: SIDE_DEF, sideMin: SIDE_MIN };
    },
  };
}

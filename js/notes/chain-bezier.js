import { DIRV, DIR_ANGLE } from '../constants.js';

/** 実機の自動生成式: 頭方向へ距離×0.5 の二次ベジェ制御点（.dat外・描画はこの1式に固定＝WYSIWYG保証。ヘルバ様決定 2026-07-12） */
export const CHAIN_CURVE_TENSION = 0.5;

export const CHAIN_CURVE_DEFAULTS = {};   // エディタ専用の曲線調整は全廃（実機式のみ）。旧キーの除去はCHAIN_RAW_KEYSで行う

/** raw(標準外キー)→意味名。書き出し時の除去(stripChainTuning)と既定値判定に使用。
    cpm/la/s2d/fcp/csqu は旧機能の遺物＝機能としては廃止済みだが、旧データからの除去のためキー表には残す */
export const CHAIN_RAW_KEYS = {
  cpm: 'cpMul',
  la: 'linearAng',
  s2d: 's2Decay',
  fcp: 'forceCurve',
  csqu: 'clampSquish',
  td: 'tailDir',
};

/** 二次ベジェ上の1点（t: 0=頭, 1=尾）。global.dirXSign=呼び出し側座標系のX符号（エディタ世界=レーン軸反転→-1、PREVIEW=+1） */
export function chainPointAt(ch, hx, hy, tx, ty, zt, t, global = {}) {
  const sx = +(global.dirXSign) || 1;
  const hd = DIRV[ch.d ?? 0] ?? DIRV[0];
  const dist = Math.hypot(tx - hx, ty - hy) || 0.001;
  const midx = hx + hd[0] * sx * dist * CHAIN_CURVE_TENSION;
  const midy = hy + hd[1] * dist * CHAIN_CURVE_TENSION;
  const it = 1 - t;
  return {
    x: it * it * hx + 2 * it * t * midx + t * t * tx,
    y: it * it * hy + 2 * it * t * midy + t * t * ty,
    z: zt * t,
  };
}

/** チェーンのリンク配置（実機と同じ: 等間隔 t=i/(sc-1) × squish）+ 制御点メタ */
export function chainLinkLayout(ch, hx, hy, tx, ty, zt = 0, global = {}) {
  const sx = +(global.dirXSign) || 1;
  const hd = DIRV[ch.d ?? 0] ?? DIRV[0];
  const dist = Math.hypot(tx - hx, ty - hy) || 0.001;
  const midx = hx + hd[0] * sx * dist * CHAIN_CURVE_TENSION;
  const midy = hy + hd[1] * dist * CHAIN_CURVE_TENSION;
  const sc = Math.max(2, ch.sc ?? 5);
  const squish = (ch.s == null || ch.s < 0.001) ? 1 : ch.s;
  const n = Math.max(1, sc - 1);
  const links = [];
  for (let i = 1; i <= n; i++) {
    const t = i / n;
    const ts = t * squish;
    const it = 1 - ts;
    const dxT = 2 * (1 - ts) * (midx - hx) + 2 * ts * (tx - midx);   // ベジェ接線（実機のリンクの向き＝経路に沿う）
    const dyT = 2 * (1 - ts) * (midy - hy) + 2 * ts * (ty - midy);
    links.push({
      lx: it * it * hx + 2 * it * ts * midx + ts * ts * tx,
      ly: it * it * hy + 2 * it * ts * midy + ts * ts * ty,
      t, lz: zt * t,
      ang: Math.atan2(dyT, dxT) * (180 / Math.PI) - 90,
    });
  }
  return { midx, midy, links };
}

export function sampleChainCurve(ch, hx, hy, tx, ty, zt, segments = 28, global = {}) {
  const { midx, midy } = chainLinkLayout(ch, hx, hy, tx, ty, zt, global);
  const pts = [];
  for (let i = 0; i <= segments; i++) {
    pts.push(chainPointAt(ch, hx, hy, tx, ty, zt, i / segments, global));
  }
  return { pts, midx, midy };
}

/** ワールド角度(度) → 最寄り cutDirection */
export function nearestCutDirection(angleDeg) {
  let best = 0, bestDiff = 1e9;
  for (const d of [0, 1, 2, 3, 4, 5, 6, 7]) {
    let diff = Math.abs(angleDeg - (DIR_ANGLE[d] ?? 0));
    if (diff > 180) diff = 360 - diff;
    if (diff < bestDiff) { bestDiff = diff; best = d; }
  }
  return best;
}

export function angleFromWorldDelta(dx, dy) {
  return Math.atan2(dx, -dy) * (180 / Math.PI);
}

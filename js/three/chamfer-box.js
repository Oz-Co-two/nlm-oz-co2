import * as THREE from 'three';

/** 正面4隅のカット量 */
export const NOTE_CORNER_CUT = 0.03;
/** チェーン頭=ノーツ下半分カット（高さ半分・下面フラット）、リンク=細いスラブ */
export const CHAIN_HEAD_SIZE = { w: 0.46, h: 0.23, d: 0.46 };
export const CHAIN_LINK_SIZE = { w: 0.30, h: 0.12, d: 0.30 };

/** チェーン親ノーツ=下半分を切り落とした直方体。下面はフラット（角取りなし）、上面の左右2隅だけ通常ノーツと同じ面取り */
export function makeChainHeadGeometry() {
  const { w, h, d } = CHAIN_HEAD_SIZE;
  const hw = w / 2, hh = h / 2;
  const r = Math.min(NOTE_CORNER_CUT, hw * 0.45, hh * 0.45);
  const s = new THREE.Shape();
  s.moveTo(-hw, -hh);        // 左下（角そのまま＝下半分カットの断面）
  s.lineTo(hw, -hh);         // 右下（角そのまま）
  s.lineTo(hw, hh - r);
  s.lineTo(hw - r, hh);      // 右上だけ面取り
  s.lineTo(-hw + r, hh);
  s.lineTo(-hw, hh - r);     // 左上だけ面取り
  s.closePath();
  const geo = new THREE.ExtrudeGeometry(s, { depth: d, bevelEnabled: false, curveSegments: 1 });
  geo.translate(0, 0, -d / 2);
  geo.computeVertexNormals();
  return geo;
}

/** チェーン子ノーツ=フラットな直方体＋●（角取りなし） */
export function makeChainLinkGeometry() {
  const { w, h, d } = CHAIN_LINK_SIZE;
  return new THREE.BoxGeometry(w, h, d);
}

/**
 * 直方体の正面4隅だけを1段カットした軽量ジオメトリ。
 * 丸めではなく辺を1本ずつ落とすだけ（ExtrudeGeometry・bevelなし）。
 */
export function makeChamferBoxGeometry(w, h, d, cut) {
  const hw = w / 2;
  const hh = h / 2;
  const r = Math.min(cut, hw * 0.45, hh * 0.45);
  const s = new THREE.Shape();
  s.moveTo(-hw + r, -hh);
  s.lineTo(hw - r, -hh);
  s.lineTo(hw, -hh + r);
  s.lineTo(hw, hh - r);
  s.lineTo(hw - r, hh);
  s.lineTo(-hw + r, hh);
  s.lineTo(-hw, hh - r);
  s.lineTo(-hw, -hh + r);
  s.closePath();
  const geo = new THREE.ExtrudeGeometry(s, { depth: d, bevelEnabled: false, curveSegments: 1 });
  geo.translate(0, 0, -d / 2);
  geo.computeVertexNormals();
  return geo;
}

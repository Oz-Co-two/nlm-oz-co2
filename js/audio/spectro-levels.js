/**
 * スペクトログラムの段の絵（縮小用）と、時間に固定した描き方（2026-10-20）
 *
 * NLE を縮小すると、画面の1画素に解析のコマ（10ms）が何十も重なる。drawImage の縮小は数コマを拾うだけなので、再生中に表示が
 * 少しずつずれるたびに拾うコマが変わり、山がギザギザにちらついていた（時間方向の折り返し）。そこで:
 *  - 時間方向に2コマずつまとめた段（2倍・4倍…）を前もって作り（specLevelMags）、
 *  - 1コマが画面で SPEC_MIN_PX 画素以上になる、いちばん細かい段を選んで（specLevelFor）拡大して貼る（drawSpecLevel）。
 *    2段目（4コマまとめ）より粗い段は SPEC_DEEP_PX 画素以上: 1コマが1〜1.5画素の拡大は、小数の画素ずつずれるたびに補間の重みが変わって
 *    細かい模様の濃さが波打つ。縮小した時だけ1段粗くして抑える（普段の拡大率＝段0・1の見た目は変えない。絵をぼかすと拍の縞まで消えた）。
 * 段の絵のコマの境目は元の音源の秒に固定されているので、スクロールは同じ絵を小数の画素ずつずらすだけになる（ちらつかない）。
 * 画面のどこに音源のどこを貼るかは、Music の配置（開始位置・分割・トリム）・無音追加・テンポパートどおりに区間に分けて求める（specMusicSpans）。
 * 絵は横幅 SPEC_TILE コマずつのタイルに分けて持つ（1枚のキャンバスは横幅に上限があり、長い曲で描けなくなるため）。
 * まとめ方は「dB の平均」と「パワー（エネルギー）の平均を dB にした値」の真ん中。合成曲で見比べて選んだ:
 * 最大値は低域が明るい帯に潰れる・パワーの平均だけでも拡大した時より明るくなる・dB の平均だけだと短い打音（キック等）が消える。
 * どちらの平均も元のコマからの平均なので、段を重ねても（2コマずつまとめても）元の 2^L コマの平均と同じ値になる。
 * 値は buildSpectroData の正規化（-60dB=0・最大=1 の dB）のまま扱う。DOM に触るのはタイルを作る所だけ（他は純関数）。
 */

/** タイル1枚の横幅（コマ）。GPU のテクスチャの上限（4096 以上）に収め、キャンバスを加速されたまま使えるようにする */
export const SPEC_TILE = 4096;
/** 1コマが画面でこの画素数（キャンバスの実画素）以上になる、いちばん細かい段を使う */
export const SPEC_MIN_PX = 1;
/** SPEC_DEEP_FROM 段目から先は、1コマがこの画素数以上（上の説明） */
export const SPEC_DEEP_PX = 1.5;
export const SPEC_DEEP_FROM = 2;
/** 波形は1ビンがこの画素数以上になる段を使う（1〜1.5画素の段の角は、小数の画素ずつずれるたびに濃さが波打って見えるため。
 * 既定の拡大（32拍）は1ビンが約1.7画素＝段0のまま） */
export const WAVE_MIN_PX = 1.5;
/** 段を作るのをやめるコマ数（これより少なくなったら打ち切る） */
const MIN_COLS = 8;

const toPow = v => Math.pow(10, 6 * (v - 1));                                  // -60dB=0 の正規化 → パワー（最大=1）
const toVal = p => (p > 1e-6 ? Math.min(1, 1 + Math.log10(p) / 6) : 0);         // パワー → 正規化（-60dB で 0 に止める）

/** 2つのまとめ方の真ん中: dB の平均 dv と、パワーの平均 p を dB にした値の平均 */
export const specBlend = (dv, p) => (dv + toVal(p)) / 2;

/**
 * 段の一覧を作る。[0] は元の mag（同じ配列）、[L] は元の 2^L コマを1コマにまとめた物（specBlend）。
 * 最後のコマが端数（2コマ揃わない）の時は、ある分だけで平均する。
 * @param {Float32Array} mag 元の値（コマ c・周波数 b が mag[c*bins+b]・0〜1）
 * @returns {{mag:Float32Array, cols:number}[]}
 */
export function specLevelMags(mag, cols, bins, minCols = MIN_COLS) {
  const out = [{ mag, cols }];
  if (cols <= minCols) return out;
  let dv = mag, pw = new Float32Array(cols * bins);                           // 今の段の dB の平均・パワーの平均
  for (let i = 0; i < pw.length; i++) pw[i] = toPow(mag[i]);
  let n = cols;
  while (n > minCols) {
    const m = Math.ceil(n / 2), nd = new Float32Array(m * bins), np = new Float32Array(m * bins), nv = new Float32Array(m * bins);
    for (let j = 0; j < m; j++) {
      const a = 2 * j * bins, b = (2 * j + 1 < n) ? a + bins : -1, o = j * bins;
      for (let k = 0; k < bins; k++) {
        const d = b < 0 ? dv[a + k] : (dv[a + k] + dv[b + k]) / 2, p = b < 0 ? pw[a + k] : (pw[a + k] + pw[b + k]) / 2;
        nd[o + k] = d; np[o + k] = p; nv[o + k] = specBlend(d, p);
      }
    }
    out.push({ mag: nv, cols: m });
    dv = nd; pw = np; n = m;
  }
  return out;
}

/**
 * Music レーンの波形（1ビン＝その間の振幅の最大値）の段: [0] は元の配列、[L] は 2^L ビンの最大値（端数はある分だけ）。
 * 波形も同じ考え方で、1ビンが1画素以上になる段を選び、ビンの境目を時間に固定して描く（drawOverview）
 */
export function waveLevels(pk, minLen = MIN_COLS) {
  const out = [pk];
  let a = pk;
  while (a.length > minLen) {
    const m = Math.ceil(a.length / 2), b = new Float32Array(m);
    for (let j = 0; j < m; j++) b[j] = 2 * j + 1 < a.length ? Math.max(a[2 * j], a[2 * j + 1]) : a[2 * j];
    out.push(b); a = b;
  }
  return out;
}

/**
 * 使う段の番号。pxPerCol0 = 元の1コマが画面（キャンバスの実画素）で何画素か。
 * その 2^L 倍が minPx（deepFrom 段目から先は deepPx）以上になる最小の L（段が足りなければ一番粗い段）。
 * 段の切り替わりはどこでも「1コマの画素数が半分になったら次の段」＝縮小していっても2段飛ぶ所は無い
 */
export function specLevelFor(pxPerCol0, nLevels, minPx = SPEC_MIN_PX, deepPx = SPEC_DEEP_PX, deepFrom = SPEC_DEEP_FROM) {
  if (!(pxPerCol0 > 0) || !isFinite(pxPerCol0)) return 0;
  let L = 0;
  while (L < nLevels - 1 && pxPerCol0 * Math.pow(2, L) < (L >= deepFrom ? deepPx : minPx)) L++;
  return L;
}

/** 色の表: 値 v（0〜1）の色を n 段で引けるようにする（毎回 specColor を呼ぶより速い。差は1段階未満） */
export function specColorLUT(colorFn, n = 2048) {
  const lut = new Uint8ClampedArray(n * 3);
  for (let i = 0; i < n; i++) { const c = colorFn(i / (n - 1)); lut[i * 3] = c[0]; lut[i * 3 + 1] = c[1]; lut[i * 3 + 2] = c[2]; }
  return lut;
}

/**
 * 1つの段の絵をタイルの画素（RGBA・低域が下）にする。タイル i はコマ [c0, c0+n) と、前後に1コマずつのりしろ
 * （隣のタイルのコマ・曲の端では端のコマの複製）を持つ＝横幅 n+2。継ぎ目でも補間が途切れない。
 * @returns {{c0:number, n:number, w:number, h:number, data:Uint8ClampedArray}[]}
 */
export function specTilePixels(mag, cols, bins, lut, tileW = SPEC_TILE) {
  const tiles = [], nL = lut.length / 3 - 1;
  for (let c0 = 0; c0 < cols; c0 += tileW) {
    const n = Math.min(tileW, cols - c0), w = n + 2, data = new Uint8ClampedArray(w * bins * 4);
    for (let x = 0; x < w; x++) {
      const c = Math.max(0, Math.min(cols - 1, c0 + x - 1));
      for (let b = 0; b < bins; b++) {
        const li = Math.round(Math.max(0, Math.min(1, mag[c * bins + b])) * nL) * 3, idx = ((bins - 1 - b) * w + x) * 4;
        data[idx] = lut[li]; data[idx + 1] = lut[li + 1]; data[idx + 2] = lut[li + 2]; data[idx + 3] = 255;
      }
    }
    tiles.push({ c0, n, w, h: bins, data });
  }
  return tiles;
}

/** 全部の段のタイルをキャンバスに焼く（曲を読み込んだ時に1回）。返り値 [段][タイル] = {c0, n, cv} */
export function specBuildTiles(levels, bins, lut, tileW = SPEC_TILE) {
  return levels.map(({ mag, cols }) => specTilePixels(mag, cols, bins, lut, tileW).map(t => {
    const cv = document.createElement('canvas'); cv.width = t.w; cv.height = t.h;
    cv.getContext('2d').putImageData(new ImageData(t.data, t.w, t.h), 0, 0);
    return { c0: t.c0, n: t.n, cv };
  }));
}

/**
 * 段の絵の [u0,u1)（その段のコマ・小数可）を、画面の横 dx0〜dx1・縦 dy〜dy+dh へ貼る。
 * タイルごとに、のりしろへ1コマはみ出して描く（次のタイルがその上から描く＝継ぎ目の画素が半端な重ね塗りで暗くならない）。
 * 曲の頭・終わりは1コマまでのりしろ（端のコマの複製）を使う＝u0 が少し負・u1 がコマ数を少し越えても、頼まれた dx0〜dx1 のとおりに貼る
 * （specMusicSpans が区間の端を実画素に揃えた時、端が半画素ほど音源の外へ出る。切り詰めると端がまた半端な位置になる）。
 * @returns {{sx:number, sw:number, dx:number, dw:number, tile:number}[]} 描いた区間（テスト用）
 */
export function drawSpecLevel(ctx, tiles, u0, u1, dx0, dx1, dy, dh) {
  const done = [];
  if (!(u1 > u0) || !(dx1 > dx0)) return done;
  const k = (dx1 - dx0) / (u1 - u0), last = tiles.length - 1;
  for (let i = 0; i < tiles.length; i++) {
    const t = tiles[i], a = Math.max(u0, i === 0 ? t.c0 - 1 : t.c0), b = Math.min(u1, i === last ? t.c0 + t.n + 1 : t.c0 + t.n);
    if (b <= a) continue;
    const b2 = b < u1 && i < last ? Math.min(u1, b + 1) : b;   // 次のタイルへ続くなら1コマはみ出す（のりしろの中）
    const sx = 1 + (a - t.c0), sw = b2 - a, dx = dx0 + (a - u0) * k, dw = sw * k;
    if (ctx) ctx.drawImage(t.cv, sx, 0, sw, t.cv ? t.cv.height : 0, dx, dy, dw, dh);
    done.push({ sx, sw, dx, dw, tile: i });
  }
  return done;
}

/**
 * Music の配置どおりに貼る区間（2026-10-20）。画面の拍の範囲 [b0,b1)（横 X0〜X1・CSS px）のどこに元の音源のどこを貼るかを、
 * Music の区間とテンポの境目で区切って求める。区間の表は再生（play）・書き出し（eggPieces）と同じ切り貼り表（editor-app.js の musicPieces）＝
 * Music を動かす・分割・トリム・並べ替えると、スペクトログラムも Music の波形と同じように動く・切れる。音の無い所（クリップの無い所・無音追加）は区間が無い＝描かない。
 * 段の絵は元の音源の秒に固定したまま（作り直さない）で、区間ごとに「その拍の範囲に当たる音源のコマの範囲」を拡大して貼る。
 * @param {number[][]} pieces [[元の音源の開始秒 s, 終了秒 e, 鳴り始める時刻 at], …]。時刻は拍0からの秒（bt の値）。時刻 at〜at+(e-s) に元の音源の s〜e が鳴る
 * @param {(b:number)=>number} bt 拍→時刻（テンポパートを考慮）
 * @param {(t:number)=>number} tb 時刻→拍（bt の逆）
 * @param {number[]} cuts テンポの境目の拍（そこで拍→時刻の傾きが変わる＝1回の拡大では貼れないので区切る）
 * @param {number} hop 元の刻みの1コマの秒
 * @param {number} cols 元の刻みのコマ数（解析の範囲の外は描かない）
 * @param {number} dpr キャンバスの実画素 / CSS px
 * 区間の両端は実画素の境目に揃える: 隣り合う区間（分割した Music の継ぎ目・テンポの境目）がぴったり接し、継ぎ目の画素が
 * 半端な重ね塗りで暗い線にならない（中身は小数の画素の位置のまま＝スクロールでちらつかない）。
 * Music の区間が重なる所は pieces の前の物を後に描く（上に見える）＝その拍の音源の秒を1つ選ぶ audioPosAtBeat（3D の帯・曲の解析）と同じ物。
 * @returns {{b0:number, b1:number, u0:number, u1:number, dx0:number, dx1:number}[]} 描く順。u＝元の刻みのコマ（小数）・dx＝画面の横（CSS px）
 */
export function specMusicSpans(b0, b1, X0, X1, pieces, bt, tb, cuts, hop, cols, dpr = 1) {
  const out = [];
  if (!(b1 > b0) || !(X1 > X0) || !(hop > 0) || !(cols > 0) || !(dpr > 0)) return out;
  const ppb = (X1 - X0) / (b1 - b0), xOf = b => X0 + (b - b0) * ppb, snap = x => Math.round(x * dpr) / dpr;
  const cs = (cuts || []).filter(c => c > b0 && c < b1).sort((a, b) => a - b);
  for (let i = pieces.length - 1; i >= 0; i--) {
    const [s, e, at] = pieces[i];
    const pb0 = Math.max(b0, tb(at)), pb1 = Math.min(b1, tb(at + (e - s)));
    if (!(pb1 > pb0)) continue;
    const bs = [pb0, ...cs.filter(c => c > pb0 && c < pb1), pb1];
    for (let j = 0; j + 1 < bs.length; j++) {
      const ba = bs[j], bb = bs[j + 1];
      const ua = (s + bt(ba) - at) / hop, ub = (s + bt(bb) - at) / hop;   // その拍の範囲に鳴る元の音源のコマ
      if (!(ub > ua)) continue;
      const fa = xOf(ba), k = (xOf(bb) - fa) / (ub - ua);                 // 1コマの画面の幅（CSS px）
      const ca = Math.max(0, Math.min(cols, ua)), cb = Math.max(0, Math.min(cols, ub));   // 解析の範囲の外（音源の終わりの端数）は描かない
      if (!(cb > ca)) continue;
      const dx0 = snap(fa + (ca - ua) * k), dx1 = snap(fa + (cb - ua) * k);
      if (!(dx1 > dx0)) continue;
      out.push({ b0: ba, b1: bb, u0: ua + (dx0 - fa) / k, u1: ua + (dx1 - fa) / k, dx0, dx1 });
    }
  }
  return out;
}

// 曲の音量の測定と、音量補正の「自動」の値（2026-10-18）。
// 測るのは ITU-R BS.1770-4（EBU R128）の積分ラウドネス（LUFS＝耳の感じ方に合わせた平均の音量）と、
// トゥルーピーク（dBTP＝サンプルの間も含めた一番大きい瞬間。4倍に補間して近似）。ffmpeg の loudnorm / ebur128 と同じ定義なので、
// ffmpeg で測った値とほぼ一致する（K特性フィルタの係数は libebur128 と同じ式でサンプリング周波数ごとに求める）。
// 純粋関数のみ。テストは tests/unit_js/test_loudness.py。

export const AUTO_TARGET_LUFS = -9;   // 自動の目標（平均の音量）。手元のカスタム曲の相場（-13〜-5 LUFS・中央 -7 前後）を見て利用者と決めた
export const AUTO_PEAK_DB = -1;       // 自動で上げる上限＝一番大きい瞬間がこれを超えない所で止める（音割れを避ける）
export const GAIN_MIN_DB = -20, GAIN_MAX_DB = 20;   // 音量補正の範囲（手で入れる値も含む）

/** K特性フィルタ（前段の高域シェルフ＋後段のハイパス）の係数。rate=サンプリング周波数。a は a1,a2（a0=1） */
export function kWeighting(rate) {
  let f0 = 1681.974450955533, Q = 0.7071752369554196;
  const G = 3.999843853973347;
  let K = Math.tan(Math.PI * f0 / rate);
  const Vh = 10 ** (G / 20), Vb = Vh ** 0.4996667741545416, a0 = 1 + K / Q + K * K;
  const shelf = { b: [(Vh + Vb * K / Q + K * K) / a0, 2 * (K * K - Vh) / a0, (Vh - Vb * K / Q + K * K) / a0],
    a: [2 * (K * K - 1) / a0, (1 - K / Q + K * K) / a0] };
  f0 = 38.13547087602444; Q = 0.5003270373238773; K = Math.tan(Math.PI * f0 / rate);
  const d = 1 + K / Q + K * K;
  const hp = { b: [1, -2, 1], a: [2 * (K * K - 1) / d, (1 - K / Q + K * K) / d] };
  return { shelf, hp };
}

const toDb = v => v > 0 ? 20 * Math.log10(v) : -Infinity;
const blockLufs = z => -0.691 + 10 * Math.log10(z);

// トゥルーピークの補間: サンプルの間の 1/4・2/4・3/4 の位置の値を、窓付きsinc（前後12サンプル）で求める
const TP_H = 12;
const TP_PHASES = [0.25, 0.5, 0.75].map(f => {
  const w = [];
  for (let k = 1 - TP_H; k <= TP_H; k++) {
    const t = f - k, sinc = Math.sin(Math.PI * t) / (Math.PI * t);
    w.push(sinc * 0.5 * (1 + Math.cos(Math.PI * t / TP_H)));
  }
  const s = w.reduce((a, b) => a + b, 0);
  return w.map(v => v / s);   // 直流の利得を1に
});

/** サンプルの間も含めた最大の振幅。sp=サンプルのピーク。サンプルの間の山がピークを超えるのは、隣り合うサンプルが
    大きい所だけなので、両隣ともピークの半分（-6dB）未満の所は補間しない（計算を減らすため） */
function truePeak(chs, R, sp) {
  let best = sp;
  const th = sp * 0.5;
  for (const x of chs) for (const [s, e] of R) {
    for (let n = s; n < e - 1; n++) {
      const a = x[n], b = x[n + 1];
      if ((a < 0 ? -a : a) < th && (b < 0 ? -b : b) < th) continue;
      for (const w of TP_PHASES) {
        let y = 0;
        for (let k = 1 - TP_H, q = 0; k <= TP_H; k++, q++) { const i = n + k; if (i >= s && i < e) y += x[i] * w[q]; }
        if (y < 0) y = -y;
        if (y > best) best = y;
      }
    }
  }
  return best;
}

/** 音量を測る。chs=チャンネルごとの Float32Array（同じ長さ・L/R の重みはどちらも1）、rate=サンプリング周波数、
    ranges=測る区間 [[開始秒, 終了秒], …]（省略＝全体。書き出す song.egg に入る所だけを測る時に使う）。
    戻り値 {lufs, peakDb, samplePeakDb}。無音・0.4秒未満なら lufs は -Infinity */
export function measureLoudness(chs, rate, ranges = null) {
  const N = chs.length ? chs[0].length : 0;
  const R = (ranges && ranges.length ? ranges : [[0, N / rate]])
    .map(([s, e]) => [Math.max(0, Math.round(s * rate)), Math.min(N, Math.round(e * rate))]).filter(([s, e]) => e > s);
  const { shelf, hp } = kWeighting(rate);
  const [sb0, sb1, sb2] = shelf.b, [sa1, sa2] = shelf.a, [ha1, ha2] = hp.a;
  const sub = Math.round(rate * 0.1);   // 100ms。400msのブロックを100msずつずらして測る（重なり75%）
  const blocks = [];                    // 400msブロックごとの、K特性を通した平均二乗（全チャンネルの合計）
  let sp = 0;                           // サンプルのピーク
  for (const [s, e] of R) {
    const nSub = Math.floor((e - s) / sub), subSum = new Float64Array(nSub);
    for (const x of chs) {
      let x1 = 0, x2 = 0, y1 = 0, y2 = 0, z1 = 0, z2 = 0;
      for (let i = s, j = 0, k = 0; i < e; i++) {
        const v = x[i], av = v < 0 ? -v : v;
        if (av > sp) sp = av;
        const y = sb0 * v + sb1 * x1 + sb2 * x2 - sa1 * y1 - sa2 * y2;   // 高域シェルフ
        const z = y - 2 * y1 + y2 - ha1 * z1 - ha2 * z2;                // ハイパス（b=[1,-2,1]）
        x2 = x1; x1 = v; y2 = y1; y1 = y; z2 = z1; z1 = z;
        if (j < nSub) { subSum[j] += z * z; if (++k === sub) { k = 0; j++; } }
      }
    }
    for (let j = 0; j + 4 <= nSub; j++) blocks.push((subSum[j] + subSum[j + 1] + subSum[j + 2] + subSum[j + 3]) / (4 * sub));
  }
  // ゲート: -70 LUFS 以下のブロックを除き（絶対ゲート）、残りの平均より 10 LU 小さいブロックも除く（相対ゲート）
  let lufs = -Infinity;
  const abs = blocks.filter(z => z > 0 && blockLufs(z) > -70);
  if (abs.length) {
    const rel = blockLufs(abs.reduce((a, b) => a + b, 0) / abs.length) - 10;
    const g = abs.filter(z => blockLufs(z) > rel);
    if (g.length) lufs = blockLufs(g.reduce((a, b) => a + b, 0) / g.length);
  }
  return { lufs, peakDb: toDb(truePeak(chs, R, sp)), samplePeakDb: toDb(sp) };
}

/** 「自動」の補正値（dB・0.1刻みで切り捨て）。平均を目標へ近づけるが、ピークが上限を超えない所で止める。自動では下げない（利用者の決定）。
    by: 'target'=目標まで上げた / 'peak'=音が割れない所で止めた / 'max'=補正の上限で止めた /
        'loud'=もう目標以上（上げない）/ 'noRoom'=ピークに余裕が無い（上げない）/ 'silent'=測れない */
export function autoGain(m, target = AUTO_TARGET_LUFS, ceil = AUTO_PEAK_DB) {
  if (!m || !isFinite(m.lufs) || !isFinite(m.peakDb)) return { db: 0, by: 'silent' };
  const byL = target - m.lufs, byP = ceil - m.peakDb;
  if (byL <= 0) return { db: 0, by: 'loud' };
  const lim = Math.min(byL, byP, GAIN_MAX_DB);
  const db = Math.floor(lim * 10 + 1e-9) / 10;
  if (db <= 0) return { db: 0, by: 'noRoom' };
  return { db, by: lim === byL ? 'target' : lim === byP ? 'peak' : 'max' };
}

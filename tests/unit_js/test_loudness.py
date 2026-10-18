"""js/audio/loudness.js: 曲の音量（BS.1770 の積分ラウドネス・トゥルーピーク）の測定と、音量補正の「自動」の値。
ラウドネスの期待値は EBU Tech 3341 の試験信号（1kHz の正弦波・ゲートの確認）から。手元の実曲で ffmpeg の loudnorm と
0.05 LU 以内で一致することは実装時に確認済み（曲はリポジトリに入れられないのでテストには含めない）。"""
HEAD = """
const m = await import('/js/audio/loudness.js');
// 正弦波（振幅は dBFS のピーク値）を区間ごとに並べたチャンネル。parts=[[秒, dBFS], …]
const sine = (rate, parts, freq = 1000, phase = 0) => {
  const n = parts.reduce((a, p) => a + Math.round(p[0] * rate), 0), x = new Float32Array(n);
  let i = 0;
  for (const [sec, db] of parts) { const A = db == null ? 0 : 10 ** (db / 20), e = i + Math.round(sec * rate);
    for (; i < e; i++) x[i] = A * Math.sin(2 * Math.PI * freq * i / rate + phase); }
  return x;
};
const r1 = v => Math.round(v * 100) / 100;
const res = r => ({ lufs: isFinite(r.lufs) ? r1(r.lufs) : null, peak: isFinite(r.peakDb) ? r1(r.peakDb) : null,
  sp: isFinite(r.samplePeakDb) ? r1(r.samplePeakDb) : null });
"""


def _js(t, body):
    return t.ed.js("(async () => {" + HEAD + body + "})()")


def test_k_weighting_48k(t):
    '''K特性フィルタの係数: 48kHz では BS.1770-4 の表の値と一致する'''
    t.fresh()
    r = _js(t, "return m.kWeighting(48000);")
    want_shelf_b = [1.53512485958697, -2.69169618940638, 1.19839281085285]
    want_shelf_a = [-1.69065929318241, 0.73248077421585]
    want_hp_a = [-1.99004745483398, 0.99007225036621]
    for got, want, name in ((r['shelf']['b'], want_shelf_b, 'シェルフ b'), (r['shelf']['a'], want_shelf_a, 'シェルフ a'),
                            (r['hp']['a'], want_hp_a, 'ハイパス a')):
        t.ok(all(abs(g - w) < 1e-6 for g, w in zip(got, want)), f"{name}: {got}")
    t.eq(r['hp']['b'], [1, -2, 1], 'ハイパス b')


def test_ebu_sine_levels(t):
    '''EBU Tech 3341: 1kHz の正弦波を両チャンネルに -23 dBFS → -23.0 LUFS・-33 dBFS → -33.0 LUFS（48kHz・44.1kHz）。
    モノラルは片チャンネルぶん＝3 LU 小さい'''
    t.fresh()
    r = _js(t, """
const out = {};
for (const rate of [48000, 44100]) for (const db of [-23, -33]) {
  const x = sine(rate, [[20, db]]);
  out[rate + '/' + db] = res(m.measureLoudness([x, x], rate)); }
out.mono = res(m.measureLoudness([sine(48000, [[20, -23]])], 48000));
return out;""")
    for k in ('48000/-23', '44100/-23', '48000/-33', '44100/-33'):
        want = float(k.split('/')[1])
        t.ok(abs(r[k]['lufs'] - want) <= 0.1, f"{k}: {r[k]}")
        t.ok(abs(r[k]['peak'] - want) <= 0.05, f"{k} のピーク（正弦波の振幅）: {r[k]}")
    t.ok(abs(r['mono']['lufs'] - (-26.01)) <= 0.1, f"モノラル: {r['mono']}")


def test_ebu_gating(t):
    '''EBU Tech 3341 のゲートの確認: -36/-23/-36 dBFS（10/60/10秒）→ -23.0（相対ゲートで小さい所を除く）。
    -26/-20/-26 dBFS（20/20.1/20秒）→ -23.0。無音は測れない（-Infinity）'''
    t.fresh()
    r = _js(t, """
const a = sine(48000, [[10, -36], [60, -23], [10, -36]]), b = sine(48000, [[20, -26], [20.1, -20], [20, -26]]);
const z = new Float32Array(48000 * 5);
return { a: res(m.measureLoudness([a, a], 48000)), b: res(m.measureLoudness([b, b], 48000)), z: res(m.measureLoudness([z, z], 48000)),
  short: res(m.measureLoudness([new Float32Array(1000)], 48000)) };""")
    t.ok(abs(r['a']['lufs'] - (-23)) <= 0.1, f"-36/-23/-36: {r['a']}")
    t.ok(abs(r['b']['lufs'] - (-23)) <= 0.1, f"-26/-20/-26: {r['b']}")
    t.eq((r['z']['lufs'], r['z']['peak']), (None, None), '無音')
    t.eq(r['short']['lufs'], None, '0.4秒未満')


def test_ranges(t):
    '''区間を指定すると、その中だけを測る（書き出す song.egg に入る所だけを測る時に使う）'''
    t.fresh()
    r = _js(t, """
const x = sine(48000, [[10, -40], [10, -20], [10, -30]]);
return { all: res(m.measureLoudness([x, x], 48000)), mid: res(m.measureLoudness([x, x], 48000, [[10, 20]])),
  two: res(m.measureLoudness([x, x], 48000, [[0, 10], [20, 30]])) };""")
    t.ok(abs(r['mid']['lufs'] - (-20)) <= 0.1 and abs(r['mid']['peak'] - (-20)) <= 0.05, f"真ん中だけ: {r['mid']}")
    t.ok(abs(r['two']['peak'] - (-30)) <= 0.05, f"前と後ろだけ（-20 の所はピークにも入らない）: {r['two']}")
    t.ok(r['two']['lufs'] < -29, f"前と後ろだけ: {r['two']}")


def test_true_peak(t):
    '''サンプルの間の山: サンプリング周波数の1/4の正弦波を45度ずらすと、サンプルの値は振幅の0.707倍（-3dB）にしかならない。
    トゥルーピークは補間して本当の振幅（-6dBFS）を返す'''
    t.fresh()
    r = _js(t, "const x = sine(48000, [[2, -6]], 12000, Math.PI / 4); return res(m.measureLoudness([x, x], 48000));")
    t.ok(abs(r['sp'] - (-9.01)) <= 0.05, f"サンプルのピーク: {r}")
    t.ok(abs(r['peak'] - (-6.0)) <= 0.2, f"トゥルーピーク: {r}")


def test_auto_gain(t):
    '''自動の値: 平均を -9 LUFS へ近づけるが、ピークが -1 dB を超えない所で止める（0.1dB で切り捨て）。自動では下げない'''
    t.fresh()
    r = _js(t, """
const a = (lufs, peakDb) => m.autoGain({ lufs, peakDb });
return { quiet: a(-17.29, -8.51), target: a(-20, -15), loud: a(-7, 1.2), eq: a(-9, -3), noRoom: a(-12, -0.95), max: a(-40, -30),
  silent: a(-Infinity, -Infinity), consts: [m.AUTO_TARGET_LUFS, m.AUTO_PEAK_DB, m.GAIN_MIN_DB, m.GAIN_MAX_DB] };""")
    t.eq(r['quiet'], {'db': 7.5, 'by': 'peak'}, '静かな曲（平均 -17.3・ピーク -8.5）→ 音が割れない所の +7.5')
    t.eq(r['target'], {'db': 11, 'by': 'target'}, '目標まで上げる')
    t.eq(r['loud'], {'db': 0, 'by': 'loud'}, 'もう大きい曲は下げない')
    t.eq(r['eq'], {'db': 0, 'by': 'loud'}, 'ちょうど目標')
    t.eq(r['noRoom'], {'db': 0, 'by': 'noRoom'}, 'ピークに余裕が無い')
    t.eq(r['max'], {'db': 20, 'by': 'max'}, '補正の上限 +20')
    t.eq(r['silent'], {'db': 0, 'by': 'silent'}, '測れない')
    t.eq(r['consts'], [-9, -1, -20, 20], '目標・上限・範囲')

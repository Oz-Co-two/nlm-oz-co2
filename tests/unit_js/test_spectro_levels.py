"""js/audio/spectro-levels.js: スペクトログラム・Music の波形の段の絵（縮小して再生した時のちらつき対策・2026-10-20）。
段の値（まとめ方）・段の選び方・タイルののりしろ・タイルをまたいで貼る区間と、縮小してずらした時の絵の揺れ（直す前の貼り方との比較）。
Music の配置どおりに貼る区間（specMusicSpans）: 動かしていない時は以前と同じ・分割・トリム・並べ替え・重なり・継ぎ目・端を実画素に揃える。"""
HEAD = """
const m = await import('/js/audio/spectro-levels.js');
const toPow = v => Math.pow(10, 6 * (v - 1)), toVal = p => (p > 1e-6 ? Math.min(1, 1 + Math.log10(p) / 6) : 0);
let seed = 7; const rnd = () => (seed = (seed * 16807) % 2147483647) / 2147483647;
const r4 = v => Math.round(v * 1e4) / 1e4;
"""


def _js(t, body):
    return t.ed.js("(async () => {" + HEAD + body + "})()")


def test_level_values(t):
    '''段の値: L段目の1コマは元の 2^L コマの「dB の平均」と「パワーの平均を dB にした値」の真ん中。段0は元の配列のまま・端数のコマはある分だけ'''
    t.fresh()
    r = _js(t, """
const cols = 21, bins = 3, mag = new Float32Array(cols * bins);
for (let i = 0; i < mag.length; i++) mag[i] = rnd();
const lv = m.specLevelMags(mag, cols, bins, 2);
const direct = (L, j, k) => { const c0 = j << L, c1 = Math.min(cols, (j + 1) << L); let d = 0, p = 0;
  for (let c = c0; c < c1; c++) { d += mag[c * bins + k]; p += toPow(mag[c * bins + k]); } const n = c1 - c0; return (d / n + toVal(p / n)) / 2; };
let worst = 0;   // 端数を含まないコマ（元の 2^L コマが揃っている所）
lv.forEach((l, L) => { if (!L) return; for (let j = 0; ((j + 1) << L) <= cols; j++) for (let k = 0; k < bins; k++) worst = Math.max(worst, Math.abs(l.mag[j * bins + k] - direct(L, j, k))); });
const tail = Math.abs(lv[1].mag[10 * bins] - mag[20 * bins]);   // 段1の最後のコマ＝元の最後の1コマだけ
const flat = new Float32Array(16 * 2).fill(0.6), lf = m.specLevelMags(flat, 16, 2, 2);
return { same: lv[0].mag === mag, cols: lv.map(l => l.cols), worst, tail, flat: lf.map(l => r4(Math.max(...l.mag.map(v => Math.abs(v - 0.6))))) };""")
    t.ok(r['same'], '段0は元の配列（3D の帯と共用）')
    t.eq(r['cols'], [21, 11, 6, 3, 2], '段ごとのコマ数（2コマずつ・端数は切り上げ・minCols で止める）')
    t.ok(r['worst'] < 1e-5, f"2コマずつ重ねても元のコマから直接まとめた値と同じ（ずれの最大 {r['worst']}）")
    t.ok(r['tail'] < 1e-6, f"端数のコマはある分だけ（段1の最後＝元の最後のコマ。ずれ {r['tail']}）")
    t.eq(r['flat'], [0, 0, 0, 0], '同じ値ばかりならどの段も同じ値')


def test_level_keeps_hits(t):
    '''まとめ方: 短い打音（16コマに1コマだけ強い）は dB の平均より残り、最大値ほどは明るくならない'''
    t.fresh()
    r = _js(t, """
const cols = 16, bins = 1, mag = new Float32Array(cols).fill(0.2); mag[5] = 1;
const lv = m.specLevelMags(mag, cols, bins, 1);
return { v: r4(lv[4].mag[0]), dbMean: r4((0.2 * 15 + 1) / 16) };""")
    t.ok(r['dbMean'] < r['v'] < 1, f"dB の平均 {r['dbMean']} < まとめた値 {r['v']} < 最大値 1")


def test_level_for(t):
    '''段の選び方: 1コマが1画素以上（2段目から先は1.5画素以上）の一番細かい段。縮小していっても2段飛ぶ所が無い'''
    t.fresh()
    r = _js(t, """
const pick = p => m.specLevelFor(p, 12);
const cases = [4, 1, 0.99, 0.5, 0.49, 0.375, 0.374, 0.1, 1e-9, 0, NaN, -1].map(p => [p, pick(p)]);
let jump = 0, lo = Infinity, hi = 0;
for (let p = 4, prev = pick(4); p > 0.002; p *= 0.995) { const L = pick(p); jump = Math.max(jump, L - prev); prev = L;
  const px = p * 2 ** L; if (L > 0) { lo = Math.min(lo, px); hi = Math.max(hi, px); } }
return { cases, jump, lo: r4(lo), hi: r4(hi), wave: [m.specLevelFor(1.6, 8, 1.5, 1.5), m.specLevelFor(1.4, 8, 1.5, 1.5)] };""")
    t.eq([c[1] for c in r['cases']], [0, 0, 1, 1, 2, 2, 3, 4, 11, 0, 0, 0],
         f"画素数ごとの段（0.99→1・0.49→2・0.374→3・0.1→4・小さすぎ→一番粗い段・不正→0）: {r['cases']}")
    t.eq(r['jump'], 1, '縮小していった時、段は1つずつしか進まない')
    t.ok(r['lo'] >= 1 and r['hi'] < 3, f"選んだ段の1コマの画素数は 1〜3 の間: {r['lo']}〜{r['hi']}")
    t.eq(r['wave'], [0, 1], '波形は全部の段で 1.5 画素以上（1.6 は段0・1.4 は段1）')


def test_wave_levels(t):
    '''波形の段: 2ビンずつ最大値でまとめる（端数のビンはそのまま）'''
    t.fresh()
    r = _js(t, """
const pk = new Float32Array([0.1, 0.5, 0.2, 0.3, 0.9, 0.0, 0.4, 0.05, 0.7, 0.6, 0.3]);
return m.waveLevels(pk, 2).map(a => Array.from(a, r4));""")
    t.eq(r, [[0.1, 0.5, 0.2, 0.3, 0.9, 0, 0.4, 0.05, 0.7, 0.6, 0.3], [0.5, 0.3, 0.9, 0.4, 0.7, 0.3], [0.5, 0.9, 0.7], [0.9, 0.7]],
         '各段の値')


def test_tiles_padding(t):
    '''タイル: 横幅 tileW コマずつ・前後に1コマののりしろ（隣のタイルのコマ・曲の端は端のコマの複製）・低域が下・色は表どおり'''
    t.fresh()
    r = _js(t, """
const cols = 10, bins = 2, mag = new Float32Array(cols * bins);
for (let c = 0; c < cols; c++) { mag[c * bins] = c / 9; mag[c * bins + 1] = 1 - c / 9; }
const lut = m.specColorLUT(v => [Math.round(v * 255), 0, 0], 256);
const tiles = m.specTilePixels(mag, cols, bins, lut, 4);
// 下の行（低域 b=0）の赤＝コマの値。タイルの各列がどのコマか
const colOf = (tl, x) => Math.round(tl.data[((bins - 1) * tl.w + x) * 4] / 255 * 9);
const topOf = (tl, x) => Math.round(tl.data[x * 4] / 255 * 9);
return tiles.map(tl => ({ c0: tl.c0, n: tl.n, w: tl.w, low: Array.from({ length: tl.w }, (_, x) => colOf(tl, x)), high: Array.from({ length: tl.w }, (_, x) => 9 - topOf(tl, x)) }));""")
    t.eq([(x['c0'], x['n'], x['w']) for x in r], [(0, 4, 6), (4, 4, 6), (8, 2, 4)], 'タイルの区切り（のりしろ込みの横幅）')
    t.eq([x['low'] for x in r], [[0, 0, 1, 2, 3, 4], [3, 4, 5, 6, 7, 8], [7, 8, 9, 9]], '各列のコマ（のりしろ＝隣のコマ・端は複製）')
    t.eq([x['high'] for x in r], [x['low'] for x in r], '高域（b=1）は上の行')


def test_draw_ranges(t):
    '''貼る区間: タイルをまたぐ時は前のタイルを1コマはみ出して描き（継ぎ目の画素が半端に重ならない）、画面の位置はコマの位置に比例する'''
    t.fresh()
    r = _js(t, """
const tiles = [{ c0: 0, n: 4 }, { c0: 4, n: 4 }, { c0: 8, n: 2 }];
const a = m.drawSpecLevel(null, tiles, 2.5, 9.5, 100, 170, 0, 10);   // 1コマ=10px
const b = m.drawSpecLevel(null, tiles, 4.5, 7.5, 0, 30, 0, 10);       // 1枚の中だけ
return { a: a.map(s => [s.tile, r4(s.sx), r4(s.sw), r4(s.dx), r4(s.dw)]), b: b.map(s => [s.tile, r4(s.sx), r4(s.sw), r4(s.dx), r4(s.dw)]),
  none: m.drawSpecLevel(null, tiles, 5, 5, 0, 10, 0, 10).length };""")
    t.eq(r['a'], [[0, 3.5, 2.5, 100, 25], [1, 1, 5, 115, 50], [2, 1, 1.5, 155, 15]],
         '3枚にまたがる: 前の2枚は1コマはみ出す（タイルの中の位置はのりしろの1を足す）')
    t.eq(r['b'], [[1, 1.5, 3, 0, 30]], '1枚の中だけならはみ出さない')
    t.eq(r['none'], 0, '幅0の区間は描かない')


def test_scroll_steady(t):
    '''縮小して少しずつずらしても絵が揺れない: 1画素に約12コマ入る縮小で 0.3 画素ずつずらした時の「前の絵をずらした物」との差が、
    直す前の貼り方（元の刻みの絵をそのまま縮小して貼る）の 1/3 未満'''
    t.fresh()
    r = _js(t, """
const cols = 12000, bins = 24, mag = new Float32Array(cols * bins);
for (let c = 0; c < cols; c++) { const hit = c % 37 < 3 ? 0.5 : 0; for (let k = 0; k < bins; k++) mag[c * bins + k] = Math.min(1, 0.25 * rnd() + hit + 0.2 * (k % 5 === 0)); }
const lut = m.specColorLUT(v => [Math.round(v * 255), Math.round(v * v * 255), 80]);
const levels = m.specLevelMags(mag, cols, bins), tiles = m.specBuildTiles(levels, bins, lut);
const full = m.specBuildTiles([levels[0]], bins, lut, cols)[0][0].cv;   // 直す前と同じ1枚の絵（のりしろ付き）
const W = 400, H = 48, view = 4800, c = document.createElement('canvas'); c.width = W; c.height = H;
const g = c.getContext('2d', { willReadFrequently: true });
const frame = (u0, mode) => { g.fillStyle = '#000'; g.fillRect(0, 0, W, H);
  if (mode === 'old') g.drawImage(full, 1 + u0, 0, view, bins, 0, 0, W, H);
  else { const L = m.specLevelFor(W / view, tiles.length), s = 2 ** L; m.drawSpecLevel(g, tiles[L], u0 / s, (u0 + view) / s, 0, W, 0, H); }
  return g.getImageData(0, 0, W, H).data; };
const res = (A, B, d) => { let s = 0, n = 0; for (let y = 0; y < H; y++) for (let x = 2; x < W - 4; x++) { const xs = x + d, i0 = Math.floor(xs), f = xs - i0;
  for (let k = 0; k < 3; k++) { s += Math.abs(B[(y * W + x) * 4 + k] - (A[(y * W + i0) * 4 + k] * (1 - f) + A[(y * W + i0 + 1) * 4 + k] * f)); n++; } } return s / n; };
const out = {};
for (const mode of ['old', 'new']) { let sum = 0, prev = frame(1000, mode);
  for (let i = 1; i <= 8; i++) { const cur = frame(1000 + i * 0.3 * view / W, mode); sum += res(prev, cur, 0.3); prev = cur; }
  out[mode] = r4(sum / 8); }
out.level = m.specLevelFor(W / view, tiles.length);
return out;""")
    t.info(f"揺れ（0〜255）: 直す前の貼り方 {r['old']} / 段の絵 {r['new']}（段 {r['level']}）")
    t.ok(r['new'] * 3 < r['old'], f"段の絵の揺れ {r['new']} は直す前の貼り方 {r['old']} の 1/3 未満")
    t.eq(r['level'], 5, '1画素に12コマ → 段4 は1コマ約1.33画素（1.5未満）なので段5（約2.67画素）')
    t.no_errors()


def test_draw_edges_margin(t):
    '''曲の頭・終わりは1コマまでのりしろを使う: u0 が少し負・u1 がコマ数を少し越えても、頼まれた画面の位置どおりに貼る。
    最後のタイルからは次へはみ出さない（タイルの外を読まない）'''
    t.fresh()
    r = _js(t, """
const tiles = [{ c0: 0, n: 4 }, { c0: 4, n: 4 }, { c0: 8, n: 2 }];
const a = m.drawSpecLevel(null, tiles, -0.4, 2, 0, 24, 0, 10);       // 1コマ=10px・頭が0.4コマ手前から
const b = m.drawSpecLevel(null, tiles, 9, 10.5, 0, 15, 0, 10);       // 終わりを0.5コマ越える
const c = m.drawSpecLevel(null, tiles, -3, 2, 0, 50, 0, 10);         // のりしろ（1コマ）より手前は描かない
return [a, b, c].map(x => x.map(s => [s.tile, r4(s.sx), r4(s.sw), r4(s.dx), r4(s.dw)]));""")
    t.eq(r[0], [[0, 0.6, 2.4, 0, 24]], '頭: のりしろ（タイルの x=0）から読み、画面の左端 0 から貼る')
    t.eq(r[1], [[2, 2, 1.5, 0, 15]], '終わり: のりしろまで読み、画面の右端 15 まで貼る（はみ出しは足さない）')
    t.eq(r[2], [[0, 0, 3, 20, 30]], 'のりしろより手前（-3〜-1）は描かない')


SPANS_HEAD = """
const bpm = 120, bt = b => b * 60 / bpm, tb = s => s * bpm / 60;   // テンポが一定
const tp = (parts) => {   // テンポパート [[拍, BPM], …]（editor-app.js の beatToTimeTM / timeToBeatTM と同じ式）
  const bt2 = b => { let bb = 0, p = bpm, tt = 0; for (const [pb, pp] of parts) { if (pb >= b) break; tt += (pb - bb) * 60 / p; bb = pb; p = pp; } return tt + (b - bb) * 60 / p; };
  const tb2 = tm => { let bb = 0, p = bpm, tt = 0; for (const [pb, pp] of parts) { const st = (pb - bb) * 60 / p; if (tt + st > tm) break; tt += st; bb = pb; p = pp; } return bb + (tm - tt) * p / 60; };
  return [bt2, tb2]; };
const hop = 0.01, cols = 2390;   // 23.9 秒ぶんのコマ
// 区間の中の拍 b の位置に貼る元の音源の秒（u は区間の中で画面の横に比例）
const secAt = (spans, b, X0, ppb) => { const x = X0 + b * ppb; let s = null; for (const q of spans) if (x >= q.dx0 && x < q.dx1) s = q;
  return s ? (s.u0 + (x - s.dx0) / (s.dx1 - s.dx0) * (s.u1 - s.u0)) * hop : null; };
const R = sp => sp.map(s => [r4(s.b0), r4(s.b1), r4(s.u0), r4(s.u1), r4(s.dx0), r4(s.dx1)]);
"""


def _spans(t, body):
    return t.ed.js("(async () => {" + HEAD + SPANS_HEAD + body + "})()")


def test_music_spans_plain(t):
    '''Music を動かしていない（区間1つ・音源の頭が拍0）時は、以前の式（コマ＝拍の時刻÷1コマの秒）と同じ1つの区間。
    無音追加は音源の頭が後ろへずれた区間（eggPieces と同じく頭を切り詰めた表）で、その前は描かない'''
    t.fresh()
    r = _spans(t, """
const plain = m.specMusicSpans(0, 32, 128, 1012, [[0, 23.95, 0]], bt, tb, [], hop, cols, 1);
const lead = m.specMusicSpans(0, 32, 128, 1012, [[0, 23.95, 0.5]], bt, tb, [], hop, cols, 1);   // 無音追加 0.5 秒
const far = m.specMusicSpans(40, 72, 128, 1012, [[0, 23.95, 0]], bt, tb, [], hop, cols, 1);     // 拍40〜（音源の終わり 23.9 秒＝拍47.8 まで）
return { plain: R(plain), lead: R(lead), far: R(far) };""")
    t.eq(r['plain'], [[0, 32, 0, 1600, 128, 1012]], '窓全体・コマ 0〜1600（16秒）')
    t.eq(r['lead'], [[1, 32, 0.6787, 1550, 156, 1012]],
         '拍1（0.5秒）から音源の頭。左端は実画素に揃える（155.625→156・コマもその 0.375画素ぶん進める）')
    t.eq(r['far'], [[40, 47.9, 2000, 2389.1403, 128, 343]], '解析の範囲（2390コマ）の外は描かない（右端は 343.475→343・コマもその分戻す）')


def test_music_spans_arrangement(t):
    '''分割・トリム・並べ替え・同じ所を2回・ずらした開始: どの拍でも、貼る音源の秒＝再生と同じ（その拍の時刻−区間の開始の時刻＋区間の音源の開始）。
    クリップの無い所には区間が無い'''
    t.fresh()
    r = _spans(t, """
const X0 = 128, ppb = 884 / 32;
const pieces = [[1, 4, 1], [8, 12, 6], [0, 3, 9], [6, 9, 12.5]];   // [音源の開始, 終了, 鳴り始める時刻]: 拍2・12・18・25
const sp = m.specMusicSpans(0, 32, X0, X0 + 884, pieces, bt, tb, [], hop, cols, 1);
const want = b => { const s = bt(b); for (const [a, e, at] of pieces) if (s >= at && s < at + (e - a)) return a + s - at; return null; };
let bad = [], on = 0, off = 0;
for (let k = 0; k < 640; k++) { const b = (k + 0.5) / 20, x = X0 + b * ppb;
  if (sp.some(q => Math.abs(x - q.dx0) < 1 || Math.abs(x - q.dx1) < 1)) continue;
  const got = secAt(sp, b, X0, ppb), w = want(b);
  if (w == null) { if (got != null) bad.push([b, got]); else off++; }
  else if (got == null || Math.abs(got - w) > 1e-6) bad.push([b, got, w]); else on++; }
return { n: sp.length, order: sp.map(s => r4(s.b0)), bad: bad.slice(0, 5), on, off };""")
    t.eq(r['n'], 4, '区間ごとに1つ')
    t.eq(r['order'], [25, 18, 12, 2], '描く順は表の逆（重なる所は表の前の物が上＝audioPosAtBeat と同じ物が見える）')
    t.eq(r['bad'], [], f"どの拍でも再生と同じ音源の秒（一致 {r['on']}・空 {r['off']}）")
    t.ok(r['on'] > 400 and r['off'] > 100, f"音のある所・無い所の両方を確かめた（{r['on']}・{r['off']}）")


def test_music_spans_overlap_and_seams(t):
    '''重なる区間は表の前の物が上。続いている区間（Music を切っただけ・テンポの境目）は同じ実画素で接する（継ぎ目が無い）。
    Music を切っただけなら音源のコマもそのまま続く（テンポの境目は傾きが変わるので、端を実画素に揃えた分だけ半コマ未満ずれる）。
    UI の倍率 1.5・1.25 でも端は実画素に揃う'''
    t.fresh()
    r = _spans(t, """
const X0 = 128, ppb = 884 / 32;
const ov = m.specMusicSpans(0, 32, X0, X0 + 884, [[0, 4, 1], [10, 16, 3]], bt, tb, [], hop, cols, 1);
const topAt = b => { const x = X0 + b * ppb; let s = null; for (const q of ov) if (x >= q.dx0 && x < q.dx1) s = q; return s && r4(s.b0); };
const cut = m.specMusicSpans(0.137, 32.137, X0, X0 + 884, [[0, 5, 0], [5, 23.9, 5]], bt, tb, [], hop, cols, 1.5);
const [bt2, tb2] = tp([[10, 90]]);
const tempo = m.specMusicSpans(0, 32, X0, X0 + 884, [[0, 23.9, 0]], bt2, tb2, [10], hop, cols, 1.25);
const joint = sp => { const s = sp.slice().sort((a, b) => a.dx0 - b.dx0); return [r4(s[0].dx1 - s[1].dx0), r4(Math.abs(s[0].u1 - s[1].u0))]; };
const onGrid = (sp, d) => sp.every(s => Math.abs(s.dx0 * d - Math.round(s.dx0 * d)) < 1e-6 && Math.abs(s.dx1 * d - Math.round(s.dx1 * d)) < 1e-6);
return { ov: [topAt(5), topAt(7), topAt(12)], cut: [cut.length, ...joint(cut), onGrid(cut, 1.5)], tempo: [tempo.length, ...joint(tempo), onGrid(tempo, 1.25),
  r4((tempo[0].u1 - tempo[0].u0) / (tempo[0].dx1 - tempo[0].dx0)), r4((tempo[1].u1 - tempo[1].u0) / (tempo[1].dx1 - tempo[1].dx0))] };""")
    t.eq(r['ov'], [2, 2, 6], '重なる所（拍6〜10）は表の前の区間（拍2から）が上・前の区間の終わった後（拍10〜）は後ろの区間')
    t.eq(r['cut'][:4], [2, 0, 0, True], 'Music を切っただけ: 2つの区間が同じ位置で接し、音源のコマも続く（UI 1.5倍でも実画素に揃う）')
    t.eq([r['tempo'][0], r['tempo'][1], r['tempo'][3]], [2, 0, True], 'テンポの境目: 同じ位置で接する（UI 1.25倍でも実画素に揃う）')
    t.ok(r['tempo'][2] < 0.5, f"テンポの境目の音源のコマのずれは半コマ未満（端を実画素に揃えた分・{r['tempo'][2]}）")
    t.ok(r['tempo'][4] != r['tempo'][5], f"テンポの境目の前後で1画素あたりのコマが違う（{r['tempo'][4]}・{r['tempo'][5]}）")

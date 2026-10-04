"""js/media/cover-fit.js: 補正が必要かの判定・寸法/名前の計算（純粋関数）と、小さなcanvasでの補正結果。
基準はBeatLeaderのカバー画像（正方形・256以上・png/jpg）。"""
HEAD = """
const m = await import('/js/media/cover-fit.js');
// 単色の w×h のPNGファイルを作る。inner を指定すると中央に別色の正方形を描く
const mkFile = async (w, h, name, color = '#00ff00', inner = null) => {
  const cv = new OffscreenCanvas(w, h), g = cv.getContext('2d');
  g.fillStyle = color; g.fillRect(0, 0, w, h);
  if (inner) { g.fillStyle = inner; const s = Math.min(w, h) / 2; g.fillRect((w - s) / 2, (h - s) / 2, s, s); }
  const b = await cv.convertToBlob({ type: 'image/png' });
  return new File([b], name, { type: 'image/png' });
};
const px = async (blob, x, y) => {
  const bmp = await createImageBitmap(blob), cv = new OffscreenCanvas(bmp.width, bmp.height), g = cv.getContext('2d');
  g.drawImage(bmp, 0, 0); return Array.from(g.getImageData(x, y, 1, 1).data);
};
"""


def _js(t, body):
    return t.ed.js("(async () => {" + HEAD + body + "})()")


def test_problems(t):
    '''coverProblems / coverNeedsFix: 正方形でない・256未満・png/jpg以外を検出'''
    t.fresh()
    r = _js(t, """
const p = (w, h, n) => m.coverProblems(w, h, n);
return { ok: p(512, 512, 'a.png'), rect: p(512, 400, 'a.png'), small: p(200, 200, 'a.jpg'), fmt: p(512, 512, 'a.webp'), jpeg: p(512, 512, 'A.JPEG'),
  noName: p(512, 512, ''), edge: p(256, 256, 'a.png'), edge2: p(255, 255, 'a.png'),
  need: [m.coverNeedsFix(512, 512, 'a.png'), m.coverNeedsFix(512, 300, 'a.png'), m.coverNeedsFix(512, 512, 'a.gif')] };""")
    t.eq(r['ok'], dict(ratio=False, small=False, format=False), '問題なし')
    t.eq(r['rect']['ratio'], True, '長方形')
    t.eq(r['small']['small'], True, '256未満')
    t.eq(r['fmt']['format'], True, 'webp')
    t.eq(r['jpeg']['format'], False, 'JPEG大文字もOK')
    t.eq(r['noName']['format'], False, '名前が無ければ形式は判定しない')
    t.eq(r['edge']['small'], False, '256ちょうどはOK')
    t.eq(r['edge2']['small'], True, '255はNG')
    t.eq(r['need'], [False, True, True], 'coverNeedsFix')
    t.no_errors()


def test_size_and_name(t):
    '''coverFitSize: 切り抜き=短い辺・引き伸ばし/余白=長い辺・256未満は256。coverFitName: jpgは維持、他はpng'''
    r = _js(t, """
return { crop: m.coverFitSize(600, 400, 'crop'), stretch: m.coverFitSize(600, 400, 'stretch'), pad: m.coverFitSize(600, 400, 'pad'),
  small: ['crop', 'stretch', 'pad'].map(k => m.coverFitSize(100, 200, k)), minC: m.COVER_MIN, modes: m.COVER_MODES,
  names: ['a.png', 'a.jpg', 'a.JPEG', 'a.webp', 'noext', '', '.png', 'a.b.gif'].map(m.coverFitName), nul: m.coverFitName(undefined) };""")
    t.eq((r['crop'], r['stretch'], r['pad']), (400, 600, 600), '各モードの一辺')
    t.eq(r['small'], [256, 256, 256], '小さい画像は256へ拡大')
    t.eq(r['minC'], 256, 'COVER_MIN')
    t.eq(r['modes'], ['crop', 'stretch', 'pad'], 'モード一覧')
    t.eq(r['names'], ['a.png', 'a.jpg', 'a.jpg', 'a.png', 'noext.png', 'cover.png', 'cover.png', 'a.b.png'], '補正後の名前')
    t.eq(r['nul'], 'cover.png', '名前なし')
    t.no_errors()


def test_fit_images(t):
    '''fitCoverImage: モードごとの寸法・中身。fit無しや補正不要なら元のファイルをそのまま返す'''
    r = _js(t, """
const out = {};
const f = await mkFile(600, 400, 'wide.png', '#00ff00', '#ff0000');
const c = await m.fitCoverImage(f, { mode: 'crop' });
out.crop = { w: c.w, h: c.h, fixed: c.fixed, name: c.name, center: await px(c.blob, 200, 200), corner: await px(c.blob, 2, 2), sameBlob: c.blob === f };
const s = await m.fitCoverImage(f, { mode: 'stretch' });
out.stretch = { w: s.w, h: s.h, fixed: s.fixed };
const p = await m.fitCoverImage(f, { mode: 'pad', bg: '#0000ff' });
out.pad = { w: p.w, h: p.h, top: await px(p.blob, 300, 2), mid: await px(p.blob, 300, 300), bottom: await px(p.blob, 300, 597) };
const nofit = await m.fitCoverImage(f, null);
out.nofit = { fixed: nofit.fixed, same: nofit.blob === f, w: nofit.w, h: nofit.h };
const sq = await mkFile(512, 512, 'ok.png');
const ok = await m.fitCoverImage(sq, { mode: 'crop' });
out.ok = { fixed: ok.fixed, same: ok.blob === sq, w: ok.w };
const sm = await m.fitCoverImage(await mkFile(100, 100, 'small.png'), { mode: 'crop' });
out.small = { w: sm.w, h: sm.h, fixed: sm.fixed };
const wp = await m.fitCoverImage(await mkFile(300, 300, 'x.webp'), { mode: 'crop' });
out.webp = { name: wp.name, type: wp.blob.type, fixed: wp.fixed };
const jp = await m.fitCoverImage(await mkFile(300, 200, 'x.jpg'), { mode: 'crop', bg: 'bad' });
out.jpg = { name: jp.name, type: jp.blob.type };
out.measure = await m.measureCoverFit(f, { mode: 'crop' });
out.measureNoFit = await m.measureCoverFit(f, null);
let bad = null; try { await m.fitCoverImage(new File([new Uint8Array([1, 2, 3])], 'broken.png'), { mode: 'crop' }); } catch (e) { bad = 'throw'; }
out.bad = bad;
return out;""")
    c = r['crop']
    t.eq((c['w'], c['h'], c['fixed'], c['name']), (400, 400, True, 'wide.png'), '切り抜きは短い辺の正方形')
    t.eq(c['center'][:3], [255, 0, 0], '中央の物が残る')
    t.eq(c['corner'][:3], [0, 255, 0], '背景も残る')
    t.eq(c['sameBlob'], False, '新しい画像')
    t.eq((r['stretch']['w'], r['stretch']['h']), (600, 600), '引き伸ばしは長い辺')
    p = r['pad']
    t.eq((p['w'], p['h']), (600, 600), '余白埋めは長い辺')
    t.eq(p['top'][:3], [0, 0, 255], '上の余白は指定色')
    t.eq(p['bottom'][:3], [0, 0, 255], '下の余白は指定色')
    t.eq(p['mid'][:3], [255, 0, 0], '中央に元画像')
    t.eq(r['nofit'], dict(fixed=False, same=True, w=600, h=400), 'fit無しは元のまま（寸法は測る）')
    t.eq(r['ok'], dict(fixed=False, same=True, w=512), '補正不要なら元のまま')
    t.eq((r['small']['w'], r['small']['h'], r['small']['fixed']), (256, 256, True), '小さい画像は256へ')
    t.eq((r['webp']['name'], r['webp']['type'], r['webp']['fixed']), ('x.png', 'image/png', True), 'webp→png')
    t.eq((r['jpg']['name'], r['jpg']['type']), ('x.jpg', 'image/jpeg'), 'jpgはjpgのまま（不正な色は黒に）')
    t.eq(r['measure'], dict(name='wide.png', w=400, h=400, fixed=True), 'measureCoverFit は寸法と名前だけ')
    t.eq(r['measureNoFit'], dict(name='wide.png', w=600, h=400, fixed=False), 'fit無しの測定')
    t.eq(r['bad'], 'throw', 'デコードできない画像は例外')
    t.no_errors()

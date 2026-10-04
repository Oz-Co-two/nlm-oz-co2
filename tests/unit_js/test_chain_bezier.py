"""js/notes/chain-bezier.js の計算（チェーンの曲線・リンク配置・向き）。DIRV は 0:上 1:下 2:左 3:右（constants.js）。"""
HEAD = "const m = await import('/js/notes/chain-bezier.js');\n"
EPS = 1e-9


def _js(t, body):
    return t.ed.js("(async () => {" + HEAD + body + "})()")


def near(t, a, b, label, eps=1e-6):
    t.ok(abs(a - b) < eps, f"{label}: 実際 {a} / 期待 {b}")


def test_point_endpoints_and_mid(t):
    '''曲線は頭(t=0)から尾(t=1)を通り、頭の向き(右)へ距離の半分ふくらむ二次ベジェ'''
    t.fresh()
    r = _js(t, """
const ch = { d: 3 };   // 右向き
return { p0: m.chainPointAt(ch, 0, 0, 0, 2, 4, 0), p1: m.chainPointAt(ch, 0, 0, 0, 2, 4, 1), ph: m.chainPointAt(ch, 0, 0, 0, 2, 4, 0.5),
  flip: m.chainPointAt(ch, 0, 0, 0, 2, 4, 0.5, { dirXSign: -1 }), line: m.chainPointAt(ch, 0, 0, 2, 0, 0, 0.5) };""")
    near(t, r['p0']['x'], 0, 'p0.x'); near(t, r['p0']['y'], 0, 'p0.y'); near(t, r['p0']['z'], 0, 'p0.z')
    near(t, r['p1']['x'], 0, 'p1.x'); near(t, r['p1']['y'], 2, 'p1.y'); near(t, r['p1']['z'], 4, 'p1.z')
    # 制御点=(1,0)。t=.5: x=.5*1=.5, y=.25*2=.5
    near(t, r['ph']['x'], 0.5, 'ph.x'); near(t, r['ph']['y'], 0.5, 'ph.y'); near(t, r['ph']['z'], 2, 'ph.z')
    near(t, r['flip']['x'], -0.5, 'dirXSign=-1でXが反転')
    near(t, r['line']['x'], 1.0, '頭の向きと尾が一直線なら中点は直線上'); near(t, r['line']['y'], 0, 'line.y')
    t.no_errors()


def test_link_layout(t):
    '''リンク数=sc-1、最後のリンクは尾の位置、squishで尾まで届かなくなる、scが小さくても最低1個'''
    r = _js(t, """
const f = (ch, tx, ty) => m.chainLinkLayout(ch, 0, 0, tx, ty, 6);
return { a: f({ d: 3, sc: 5, s: 1 }, 2, 0), b: f({ d: 3, sc: 3, s: 0.5 }, 2, 0), c: f({ d: 3, sc: 1 }, 2, 0), d: f({ d: 3 }, 2, 0),
  zero: f({ d: 3, sc: 3, s: 0 }, 2, 0), curve: m.chainPointAt({ d: 3 }, 0, 0, 2, 0, 6, 0.5 * 0.5) };""")
    a = r['a']['links']
    t.eq(len(a), 4, 'sc=5 → リンク4個')
    near(t, a[-1]['lx'], 2, '最後のリンクx=尾'); near(t, a[-1]['lz'], 6, '最後のリンクz=尾')
    near(t, a[0]['t'], 0.25, '等間隔 t=i/(sc-1)')
    near(t, a[1]['lz'], 3, 'zは線形')
    near(t, a[0]['ang'], -90, '右へ進む経路ならリンクの向き=-90度')
    b = r['b']['links']
    t.eq(len(b), 2, 'sc=3 → 2個')
    near(t, b[-1]['lx'], 1.0, 'squish=0.5なら最後のリンクは曲線の中間(一直線なので x=1)')
    t.eq(len(r['c']['links']), 1, 'sc<2でも最低1個')
    t.eq(len(r['d']['links']), 4, 'sc未指定は5')
    near(t, r['zero']['links'][-1]['lx'], 2, 's=0(未指定扱い)はsquish=1')
    t.no_errors()


def test_sample_curve(t):
    '''sampleChainCurve は既定28分割=29点で、両端が頭と尾'''
    r = _js(t, "const s = m.sampleChainCurve({ d: 0 }, 1, 1, 3, 2, 0); const s2 = m.sampleChainCurve({ d: 0 }, 1, 1, 3, 2, 0, 4); return { n: s.pts.length, a: s.pts[0], b: s.pts[28], n2: s2.pts.length };")
    t.eq(r['n'], 29, '点の数'); t.eq(r['n2'], 5, '分割数指定')
    near(t, r['a']['x'], 1, 'start.x'); near(t, r['b']['x'], 3, 'end.x'); near(t, r['b']['y'], 2, 'end.y')
    t.no_errors()


def test_directions(t):
    '''角度→最寄りのカット方向、ワールド差分→角度'''
    r = _js(t, """
const ang = [0, 45, 90, 135, 180, 225, 270, 315, 350, 10, -90, 359, 20, 25];
return { dirs: ang.map(m.nearestCutDirection), w: [[0, -1], [1, 0], [0, 1], [-1, 0]].map(([x, y]) => m.angleFromWorldDelta(x, y)) };""")
    # DIR_ANGLE: 0:0 5:45 3:90 7:135 1:180 6:225 2:270 4:315
    t.eq(r['dirs'][:8], [0, 5, 3, 7, 1, 6, 2, 4], '8方向の角度どおり')
    t.eq([r['dirs'][8], r['dirs'][9], r['dirs'][11]], [0, 0, 0], '350/10/359度→0(上)')
    t.eq(r['dirs'][12], 0, '20度は上寄り'); t.eq(r['dirs'][13], 5, '25度は斜め寄り')
    for got, want in zip(r['w'], [0, 90, 180, -90]):
        near(t, got, want, 'angleFromWorldDelta')
    t.no_errors()


def test_raw_keys(t):
    '''標準外キー表（書き出し時の除去に使う）に旧機能のキーが残っている。張力は実機式0.5'''
    r = _js(t, "return { keys: Object.keys(m.CHAIN_RAW_KEYS).sort(), tension: m.CHAIN_CURVE_TENSION, defaults: m.CHAIN_CURVE_DEFAULTS };")
    t.eq(r['keys'], ['cpm', 'csqu', 'fcp', 'la', 's2d', 'td'], 'キー表')
    t.eq(r['tension'], 0.5, '張力')
    t.eq(r['defaults'], {}, 'エディタ専用の曲線調整は無い')
    t.no_errors()


def test_negative_angle_direction(t):
    '''負の角度（angleFromWorldDelta が返す -180..0 度）でも、等価な正の角度と同じ方向になる'''
    r = _js(t, """
const neg = [-90, -135, -180, -60, -45, -10];
return neg.map(a => [m.nearestCutDirection(a), m.nearestCutDirection(a + 360)]);""")
    bad = [(a, g, w) for a, (g, w) in zip([-90, -135, -180, -60, -45, -10], r) if g != w]
    t.eq(bad, [], '(角度, 実際, 等価な正の角度での結果) が食い違う')
    # DIR_ANGLE（constants.js）: 0=上0° 5=右上45° 3=右90° 7=右下135° 1=下180° 6=左下225° 2=左270° 4=左上315°
    got = [g for g, _ in r]
    t.eq(got, [2, 6, 1, 4, 4, 0], '負の角度 -90/-135/-180/-60/-45/-10 の方向')
    t.no_errors()

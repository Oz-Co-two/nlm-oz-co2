"""スペクトログラムを Music の配置どおりに描く（2026-10-20）。
以前は 2D の帯（#speccv）・3D の帯とも無音追加とテンポしか見ず、Music の開始位置・分割・トリムを見ていなかった＝Music を動かすと
Music の波形・実際に鳴る音とずれた。今は再生（play）・書き出し（eggPieces）と同じ切り貼り表（musicPieces）・audioPosAtBeat で描く。
ここでは (1) 帯の各位置に貼った音源の秒が audioPosAtBeat（再生と同じ計算）と一致し、音の無い所には何も貼らないこと（_dbgApp.spec() の区間）、
(2) 絵が実際にずれる・切れる・並べ替わること（画素）、(3) 3D の帯も止まったまま描き直されること、(4) 分割の継ぎ目に線が出ず、
縮小してずらしても絵が揺れないこと（ちらつきが戻っていない）を確かめる。段の絵・区間の計算そのものは unit_js/test_spectro_levels.py。
音源はページの中で作る 24 秒の合成音（120BPM＝1拍0.5秒）: 周波数が時間とともに上がり続ける音（どの時刻も帯の高さが違う＝ずれが分かる）と、
不規則な間隔の打音、10〜11秒の無音。"""
import json

from e2e_helpers import wait_until
from nle_helpers import open_nle

GEN = r"""(async()=>{
  const sr=22050, sec=24, n=sr*sec, buf=new ArrayBuffer(44+n*2), dv=new DataView(buf), s=(o,t)=>{ for(let i=0;i<t.length;i++) dv.setUint8(o+i,t.charCodeAt(i)); };
  s(0,'RIFF'); dv.setUint32(4,36+n*2,true); s(8,'WAVEfmt '); dv.setUint32(16,16,true); dv.setUint16(20,1,true); dv.setUint16(22,1,true);
  dv.setUint32(24,sr,true); dv.setUint32(28,sr*2,true); dv.setUint16(32,2,true); dv.setUint16(34,16,true); s(36,'data'); dv.setUint32(40,n*2,true);
  let seed=5; const rnd=()=>(seed=(seed*16807)%2147483647)/2147483647-0.5;
  const f0=120, r=8000/120, T=sec, K=2*Math.PI*f0*T/Math.log(r);
  for(let i=0;i<n;i++){ const t=i/sr; let v=0;
    if(t<10||t>=11){ v+=0.3*Math.sin(K*(Math.pow(r,t/T)-1));                       // 上がり続ける音
      const tc=t%0.37; if(tc<0.012) v+=rnd()*1.2; }                                   // 不規則な打音（0.37秒ごと）
    dv.setInt16(44+i*2,Math.max(-1,Math.min(1,v))*30000,true); }
  const file=new File([buf],'chirp.wav',{type:'audio/wav'});
  await window._dbg.rt.loadSongFromItem({isMusic:true,name:'chirp',songFh:{getFile:async()=>file},info:{_beatsPerMinute:120}},0);
  return true; })()"""

# 画素の読み取り・比べ方（ページの中に置く＝大きな配列を Python へ送らない）。座標はキャンバスの実画素
HELP = r"""window.__sp = {
  shots: {},
  canvas: () => document.getElementById('speccv'),
  /** 帯の絵を名前を付けて取っておく。地を塗っているので、解像度の切り替えで一時的に透明な時は null（読み直す） */
  grab(name) { const c = this.canvas(), w = c.width, h = c.height; if (!w || !h) return null;
    const d = c.getContext('2d').getImageData(0, 0, w, h).data;
    for (let i = 3; i < d.length; i += 4 * 97) if (d[i] < 255) return null;
    this.shots[name] = { w, h, d }; return true; },
  /** 拍 b の x（実画素） */
  x(b) { const tl = window._dbgApp.tl(), W = this.canvas().getBoundingClientRect().width; return (128 + (b - tl.b0) / tl.span * (W - 128)) * devicePixelRatio; },
  /** 1拍の幅（実画素） */
  ppb() { const tl = window._dbgApp.tl(), W = this.canvas().getBoundingClientRect().width; return (W - 128) / tl.span * devicePixelRatio; },
  /** B の横 x0〜x1 と、A を d 画素右へずらした物の差（RGB の平均の絶対差・0〜255。小数のずれは隣の画素と補間） */
  diff(a, b, d, x0, x1) { const A = this.shots[a], B = this.shots[b], w = B.w; let s = 0, n = 0;
    for (let y = 0; y < B.h; y++) for (let x = Math.ceil(x0); x < Math.floor(x1); x++) {
      const xs = x - d, i0 = Math.floor(xs), f = xs - i0; if (i0 < 0 || i0 + 1 >= w) continue;
      for (let k = 0; k < 3; k++) { s += Math.abs(B.d[(y * w + x) * 4 + k] - (A.d[(y * w + i0) * 4 + k] * (1 - f) + A.d[(y * w + i0 + 1) * 4 + k] * f)); n++; } }
    return n ? s / n : null; },
  /** 横 x0〜x1 のうち地の色（#0c0c0e）の画素の割合（何も描いていない所は 1） */
  empty(a, x0, x1) { const A = this.shots[a], w = A.w; let e = 0, n = 0;
    for (let y = 0; y < A.h; y++) for (let x = Math.ceil(x0); x < Math.floor(x1); x++) { const i = (y * w + x) * 4; n++;
      if (Math.abs(A.d[i] - 12) + Math.abs(A.d[i + 1] - 12) + Math.abs(A.d[i + 2] - 14) < 6) e++; }
    return n ? e / n : null; },
  /** 列ごとの差の最大（継ぎ目の線を探す）: 列の中の RGB の平均の絶対差の、x0〜x1 での最大と、その列 */
  colMax(a, b, x0, x1) { const A = this.shots[a], B = this.shots[b], w = A.w; let best = 0, at = -1;
    for (let x = Math.ceil(x0); x < Math.floor(x1); x++) { let s = 0;
      for (let y = 0; y < A.h; y++) for (let k = 0; k < 3; k++) s += Math.abs(A.d[(y * w + x) * 4 + k] - B.d[(y * w + x) * 4 + k]);
      s /= A.h * 3; if (s > best) { best = s; at = x; } }
    return [best, at]; },
  /** 2D の帯の各位置（窓を 400 等分）に貼った元の音源のコマと、audioPosAtBeat（再生と同じ計算）を比べる。
   *  区間の端から1画素以内は飛ばす（端は実画素に揃えるため）。解析の範囲の外（音源の終わりの端数）は描かないのが正しい */
  mapping() { const sp = window._dbgApp.spec(), tl = window._dbgApp.tl(), W = this.canvas().getBoundingClientRect().width, out = { bad: [], on: 0, off: 0, spans: sp.spans.length };
    for (let k = 0; k < 400; k++) { const b = tl.b0 + tl.span * (k + 0.5) / 400, x = 128 + (b - tl.b0) / tl.span * (W - 128);
      if (sp.spans.some(q => Math.abs(x - q.dx0) < 1 || Math.abs(x - q.dx1) < 1)) continue;
      let s = null; for (const q of sp.spans) if (x >= q.dx0 && x < q.dx1) s = q;   // 後に描いた物が上
      const p = window._dbgApp.audioPosAtBeat(b, true), want = p == null ? null : p / sp.hop;
      if (want == null || want >= sp.cols) { if (s) out.bad.push([+b.toFixed(3), '音が無いのに描いた']); else out.off++; continue; }
      if (!s) { out.bad.push([+b.toFixed(3), '描いていない', +want.toFixed(2)]); continue; }
      const u = s.u0 + (x - s.dx0) / (s.dx1 - s.dx0) * (s.u1 - s.u0);
      if (Math.abs(u - want) > 0.02) out.bad.push([+b.toFixed(3), +u.toFixed(3), +want.toFixed(3)]); else out.on++; }
    out.bad = out.bad.slice(0, 8); return out; },
  /** 3D の帯の行ごとのコマと audioPosAtBeat を比べる（行の中心の拍）。違う行の数と、音の無い行・ある行の数 */
  band() { const sp = window._dbgApp.spec(), bd = sp.band; if (!bd) return null; const H = bd.cols.length; let bad = 0, none = 0, some = 0, first = null;
    for (let j = 0; j < H; j++) { const beat = bd.cB - 20 + 40 * (j + 0.5) / H, p = window._dbgApp.audioPosAtBeat(beat, true);
      const want = p == null ? -1 : Math.max(0, Math.min(sp.cols - 1, Math.round(p / sp.hop)));
      if (bd.cols[j] !== want) { bad++; if (!first) first = [+beat.toFixed(3), bd.cols[j], want]; }
      if (want < 0) none++; else some++; }
    return { cB: bd.cB, bad, none, some, first }; },
};
true"""


def _frames(ed, n=3):
    ed.js("new Promise(r=>{let k=%d;const f=()=>{if(--k<=0)r(0);else requestAnimationFrame(f)};requestAnimationFrame(f)})" % n)


def _seek(ed, b0):
    """停止中に窓の左端を b0 拍へ（seekEase は窓の左端を 再生位置−幅/2 にする）。描かれるまで待つ"""
    ed.js(f"window._dbg.rt.seekEase({b0}+window._dbgApp.tl().span/2,1)")
    wait_until(ed, f"Math.abs(window._dbgApp.tl().b0-({b0}))<1e-6", label="窓の左端")
    _frames(ed)


def _grab(ed, name):
    wait_until(ed, f"window.__sp.grab({json.dumps(name)})", label=f"帯の絵 {name}")


def _open(t):
    """素材を開き、合成音を読み込んで、スペクトログラムが描かれるまで待つ。窓は拍0〜32（既定の拡大）"""
    ed = open_nle(t, "basic")
    ed.js(GEN)
    wait_until(ed, "window._dbgApp.spec().spans.length>0&&window._dbgApp.nle().music.audio", timeout=30, label="スペクトログラムの解析と描画")
    ed.js(HELP)
    _seek(ed, 0)
    t.eq(ed.js("window._dbgApp.tl().span"), 32, "既定の拡大（32拍）")
    return ed


def _place(ed, beat=0, segs=None):
    """Music の配置（開始の拍・区間 {beat, off, dur}（秒））を変える（Undo の仕組みを通す）。描き直されるまで待つ"""
    ed.js("""((mb,segs)=>{ const rt=window._dbg.rt; const st=JSON.parse(rt.dumpDomain('node'));
      st.musicBeat=mb; st.musicSegs=segs; rt.restoreDomain('node',JSON.stringify(st)); return true; })(%s,%s)""" % (beat, json.dumps(segs)))
    _frames(ed)


def _lead(ed, ms):
    """無音追加（ms）。BPM は 120 のまま（'tempo' の履歴の差し戻しと同じ経路＝Music の波形も作り直す）"""
    ed.js(f"window._dbg.rt.restoreDomain('tempo',JSON.stringify({{bpm:120,off:{-ms / 1000}}}))")
    _frames(ed)


def _mapping_ok(t, ed, what, off_min=0):
    m = ed.js("window.__sp.mapping()")
    t.ok(not m["bad"] and m["on"] > 100 and m["off"] >= off_min,
         f"{what}: 帯の各位置の音源の秒が再生と同じ（一致 {m['on']}・音の無い所 {m['off']}・区間 {m['spans']}・違う所 {m['bad']}）")
    return m


def test_plain_unchanged(t):
    '''Music を動かしていない時は今までと同じ: 窓全体が1つの区間で、拍 b に元の音源の 拍bの時刻（＝無音追加 0）の音を貼る'''
    ed = _open(t)
    _mapping_ok(t, ed, "動かしていない")
    sp = ed.js("window._dbgApp.spec()")
    s = sp["spans"]
    t.eq(len(s), 1, "1つの区間")
    W = ed.js("window.__sp.canvas().getBoundingClientRect().width")
    t.ok(abs(s[0]["dx0"] - 128) < 1e-9 and abs(s[0]["u0"]) < 1e-9 and abs(s[0]["dx1"] - W) <= 0.5,
         f"窓の左端（拍0＝音源の頭のコマ0）から右端まで1つ（{s[0]}・幅 {W}）")
    # 以前の式（コマ = (無音追加 + 拍の時刻) / 1コマの秒）と同じ傾き: 拍32＝16秒
    k = (s[0]["u1"] - s[0]["u0"]) / (s[0]["dx1"] - s[0]["dx0"]) * (W - 128)
    t.ok(abs(k - 16 / sp["hop"]) < 0.01, f"窓の幅に当たる音源のコマ数（{k:.3f} と {16 / sp['hop']:.3f}）")
    t.no_errors()


def test_moved_follows_music(t):
    '''Music の開始を拍3へずらすと、スペクトログラムも同じだけ（3拍）右へずれ、拍0〜3は空。3D の帯も止まったまま描き直される'''
    ed = _open(t)
    _grab(ed, "A")
    band0 = ed.js("window.__sp.band()")
    t.ok(band0 and band0["bad"] == 0, f"3D の帯（動かす前）: {band0}")
    _place(ed, 3)
    _mapping_ok(t, ed, "拍3へずらした", off_min=10)
    _grab(ed, "B")
    x3, ppb, W = ed.js("[window.__sp.x(3), window.__sp.ppb(), window.__sp.canvas().width]")
    moved = ed.js(f"window.__sp.diff('A','B',{3 * ppb},{x3 + 3},{W - 3})")
    still = ed.js(f"window.__sp.diff('A','B',0,{x3 + 3},{W - 3})")
    empty = ed.js(f"window.__sp.empty('B',{128 + 2},{x3 - 2})")
    t.info(f"3拍ずらした絵との差 {moved:.2f}・ずらさない絵との差 {still:.2f}（0〜255）・拍0〜3の空の割合 {empty:.3f}")
    t.ok(moved < 3, f"前の絵を3拍ずらした物と同じ（差 {moved:.2f}）")
    t.ok(still > 10 * max(moved, 0.5), f"ずらさない絵とは違う（差 {still:.2f}）")
    t.ok(empty > 0.99, f"Music の前（拍0〜3）は何も描かない（地の色の割合 {empty:.3f}）")
    # 3D の帯: 再生ヘッドを動かさなくても描き直される（以前は 1/4 拍ごとの再生位置だけで描き直しを決めていた）
    band = wait_until(ed, f"(b=>b&&b.bad===0&&b.none>{band0['none']}?b:null)(window.__sp.band())", label="3D の帯の描き直し")
    t.eq(band["cB"], band0["cB"], "再生ヘッドは動いていない")
    t.ok(band["none"] > band0["none"], f"3D の帯にも Music の前の音の無い所が増える（{band0['none']}→{band['none']} 行）")
    t.no_errors()


def test_split_trim_gap(t):
    '''分割・トリム: 区間1＝拍2から音源の1秒目（頭を1秒トリム）、区間2＝拍12から音源の8秒目を4秒。
    区間1は動かす前と同じ所（拍2＝1秒）、区間2は4拍左へ寄る。クリップの無い所（拍0〜2・8〜12・20〜）は空'''
    ed = _open(t)
    _grab(ed, "A")
    _place(ed, 0, [{"beat": 2, "off": 1, "dur": 3}, {"beat": 12, "off": 8, "dur": 4}])
    _mapping_ok(t, ed, "分割・トリム", off_min=50)
    _grab(ed, "B")
    X = ed.js("[2,8,12,20].map(b=>window.__sp.x(b))")
    ppb, W = ed.js("[window.__sp.ppb(), window.__sp.canvas().width]")
    same1 = ed.js(f"window.__sp.diff('A','B',0,{X[0] + 3},{X[1] - 3})")
    same2 = ed.js(f"window.__sp.diff('A','B',{-4 * ppb},{X[2] + 3},{X[3] - 3})")
    gaps = ed.js(f"[window.__sp.empty('B',130,{X[0] - 2}), window.__sp.empty('B',{X[1] + 2},{X[2] - 2}), window.__sp.empty('B',{X[3] + 2},{W - 2})]")
    t.info(f"区間1の差 {same1:.2f}・区間2（4拍寄せた）の差 {same2:.2f}・空の割合 {[round(g, 3) for g in gaps]}")
    t.ok(same1 < 3 and same2 < 3, f"区間ごとに元の音源の同じ所の絵（差 {same1:.2f}・{same2:.2f}）")
    t.ok(min(gaps) > 0.99, f"クリップの無い所は空（{gaps}）")
    t.no_errors()


def test_reorder_and_reuse(t):
    '''並べ替えと同じ所を2回: 拍0〜6＝音源の6〜9秒、拍6〜12＝音源の0〜3秒、拍12〜18＝また音源の6〜9秒'''
    ed = _open(t)
    _grab(ed, "A")
    _place(ed, 0, [{"beat": 0, "off": 6, "dur": 3}, {"beat": 6, "off": 0, "dur": 3}, {"beat": 12, "off": 6, "dur": 3}])
    _mapping_ok(t, ed, "並べ替え")
    _grab(ed, "B")
    X = ed.js("[0,6,12,18].map(b=>window.__sp.x(b))")
    ppb = ed.js("window.__sp.ppb()")
    first = ed.js(f"window.__sp.diff('A','B',{-12 * ppb},{X[0] + 3},{X[1] - 3})")    # 拍0〜6 ＝ 動かす前の拍12〜18
    second = ed.js(f"window.__sp.diff('A','B',{6 * ppb},{X[1] + 3},{X[2] - 3})")    # 拍6〜12 ＝ 動かす前の拍0〜6
    reuse = ed.js(f"window.__sp.diff('B','B',{12 * ppb},{X[2] + 3},{X[3] - 3})")    # 拍12〜18 ＝ 拍0〜6
    t.info(f"差: 1つ目 {first:.2f}・2つ目 {second:.2f}・2回目に使った所 {reuse:.2f}")
    t.ok(max(first, second, reuse) < 3, f"再生どおりの順に並ぶ（{first:.2f}・{second:.2f}・{reuse:.2f}）")
    t.no_errors()


def test_lead_in_with_music(t):
    '''無音追加 500ms と Music の開始 拍2 を合わせると、音源の頭は拍3（1.5秒）。拍0〜3は空・その先は動かす前の絵を3拍ずらした物'''
    ed = _open(t)
    _grab(ed, "A")
    _lead(ed, 500)
    _place(ed, 2)
    _mapping_ok(t, ed, "無音追加＋開始位置", off_min=10)
    _grab(ed, "B")
    x3, ppb, W = ed.js("[window.__sp.x(3), window.__sp.ppb(), window.__sp.canvas().width]")
    moved = ed.js(f"window.__sp.diff('A','B',{3 * ppb},{x3 + 3},{W - 3})")
    empty = ed.js(f"window.__sp.empty('B',130,{x3 - 2})")
    t.ok(moved < 3 and empty > 0.99, f"拍3から音源の頭（差 {moved:.2f}・拍0〜3の空の割合 {empty:.3f}）")
    t.ok(ed.js("window.__sp.band().bad") == 0, "3D の帯も同じ")
    t.no_errors()


def test_tempo_part_and_seam(t):
    '''テンポパート（拍10から BPM 90）でも区間ごとに再生と同じ。Music を拍10で切っただけ（音源は続いている）なら、切る前と同じ絵（継ぎ目に線が出ない）'''
    ed = _open(t)
    ed.js("""(()=>{ const rt=window._dbg.rt; const st=JSON.parse(rt.dumpDomain('node')); st.tempoParts=[{beat:10,bpm:90}]; rt.restoreDomain('node',JSON.stringify(st)); return true; })()""")
    _frames(ed)
    _mapping_ok(t, ed, "テンポパート")
    t.eq(len(ed.js("window._dbgApp.spec().spans")), 2, "テンポの境目で2つの区間")
    ed.js("""(()=>{ const rt=window._dbg.rt; const st=JSON.parse(rt.dumpDomain('node')); st.tempoParts=[]; rt.restoreDomain('node',JSON.stringify(st)); return true; })()""")
    _frames(ed)
    # 拍10（5秒）で切った形（cutMusicAt と同じ: 前の区間は 5 秒・後ろの区間は音源の5秒目から）。窓を少しずらして境目を半端な位置に
    for b0 in (0.0, 0.137):
        _seek(ed, b0)
        _place(ed, 0, None)
        _grab(ed, "A")
        _place(ed, 0, [{"beat": 0, "off": 0, "dur": 5}, {"beat": 10, "off": 5, "dur": 19}])
        _mapping_ok(t, ed, f"拍10で切った（窓の左端 {b0}）")
        _grab(ed, "C")
        x10, W = ed.js("[window.__sp.x(10), window.__sp.canvas().width]")
        whole = ed.js(f"window.__sp.diff('A','C',0,130,{W - 2})")
        col, at = ed.js(f"window.__sp.colMax('A','C',{x10 - 4},{x10 + 4})")
        t.info(f"窓の左端 {b0}: 切る前との差 {whole:.3f}・境目の列の差の最大 {col:.2f}（{at}・境目 {x10:.2f}）")
        t.ok(whole < 0.2 and col < 12, f"切る前と同じ絵・境目に線が出ない（全体の差 {whole:.3f}・境目の列 {col:.2f}）")
    t.no_errors()


def test_scroll_steady_with_music(t):
    '''Music を分割・並べ替え・無音追加した状態で縮小し、窓を約0.5画素ずつずらしても、絵はそのまま横にずれるだけ（ちらつかない）'''
    ed = _open(t)
    _lead(ed, 250)
    _place(ed, 0, [{"beat": 1, "off": 0, "dur": 7}, {"beat": 17, "off": 12, "dur": 6}, {"beat": 31, "off": 3, "dur": 12}])
    m = ed.js("window._dbgApp.musicScreen()")
    for _ in range(4):
        ed.wheel(m["left"] + 400, m["top"] + m["h"] / 2, 120, ctrl=True)
    ed.wait(0.2)
    span = ed.js("window._dbgApp.tl().span")
    t.ok(span > 50, f"縮小できた（{span}拍）")
    W = ed.js("window.__sp.canvas().width")
    step = span / (W - 128) * 0.5   # 1回で約0.5画素
    names = []
    for i in range(3):
        _seek(ed, 0.5 + i * step)
        _grab(ed, f"S{i}")
        names.append(f"S{i}")
    _mapping_ok(t, ed, "縮小・分割", off_min=10)
    d = ed.js("window.__sp.ppb()") * step
    edges = ed.js("window._dbgApp.spec().spans.flatMap(s=>[s.dx0,s.dx1]).map(x=>x*devicePixelRatio)")
    # 区間の端（実画素に揃えるため1画素ずつ動く）の近くは除いて比べる
    lo = 130
    parts = sorted([lo] + [e for e in edges if lo < e < W - 3] + [W - 3])
    moved, still = [], []
    for i in range(2):
        sm = sn = 0.0
        for a, b in zip(parts, parts[1:]):
            if b - a < 12:
                continue
            w = b - a - 8
            sm += ed.js(f"window.__sp.diff('S{i}','S{i + 1}',{-d},{a + 4},{b - 4})") * w   # 窓が右へ進む＝絵は左へずれる
            sn += w
        moved.append(sm / sn)
        still.append(ed.js(f"window.__sp.diff('S{i}','S{i + 1}',0,{lo},{W - 3})"))
    t.info(f"ずらした分を補った差 {[round(v, 2) for v in moved]}・補わない差 {[round(v, 2) for v in still]}（0〜255・1回約 {d:.2f} 画素）")
    t.ok(max(moved) < 3, f"前の絵をずらした物と次の絵がほぼ同じ（差 {moved}）")
    t.ok(min(still) > max(moved), "ずらした分を補わないと差は大きい（ちゃんと動いている）")
    t.no_errors()

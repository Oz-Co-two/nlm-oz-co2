"""スペクトログラムの帯（#speccv）と Music レーンの波形（#ovcv）の描画（2026-10-20・縮小して再生した時のちらつき対策）。
段の絵（js/audio/spectro-levels.js）の値・選び方・揺れの比較は unit_js/test_spectro_levels.py。ここでは本体に組み込んだ形で、
拡大・既定・縮小のどの段でも描かれること（タイルの継ぎ目のある長い曲）と、窓をずらすと絵がそのままずれることを確かめる。
音源はページの中で作る 60 秒の合成音（120BPM・拍ごとの低い打音と高い音）＝縮小して粗い段まで使える長さ。"""
from e2e_helpers import wait_until
from nle_helpers import open_nle

GEN = r"""(async()=>{
  const sr=22050, sec=60, n=sr*sec, buf=new ArrayBuffer(44+n*2), dv=new DataView(buf), s=(o,t)=>{ for(let i=0;i<t.length;i++) dv.setUint8(o+i,t.charCodeAt(i)); };
  s(0,'RIFF'); dv.setUint32(4,36+n*2,true); s(8,'WAVEfmt '); dv.setUint32(16,16,true); dv.setUint16(20,1,true); dv.setUint16(22,1,true);
  dv.setUint32(24,sr,true); dv.setUint32(28,sr*2,true); dv.setUint16(32,2,true); dv.setUint16(34,16,true); s(36,'data'); dv.setUint32(40,n*2,true);
  let seed=3; const rnd=()=>(seed=(seed*16807)%2147483647)/2147483647-0.5;
  for(let i=0;i<n;i++){ const t=i/sr, tb=t%0.5, bar=Math.floor(t/2);
    const kick=Math.exp(-tb*18)*Math.sin(2*Math.PI*(50+80*Math.exp(-tb*40))*tb);
    const hat=(t%0.25)<0.03?rnd()*0.3:0, tone=0.15*Math.sin(2*Math.PI*(440+110*(bar%4))*t)*((bar%8)<4?1:0.2);
    dv.setInt16(44+i*2,Math.max(-1,Math.min(1,0.6*kick+hat+tone))*30000,true); }
  const file=new File([buf],'gen.wav',{type:'audio/wav'});
  await window._dbg.rt.loadSongFromItem({isMusic:true,name:'gen',songFh:{getFile:async()=>file},info:{_beatsPerMinute:120}},0);
  return true; })()"""

# キャンバスの溝より右の画素: スペクトログラム＝明るい画素の割合／波形＝灰色の画素の割合（ヘッダーの下）。
# スペクトログラムは地を塗るので、開いた直後の解像度の切り替えで一時的に透明な時は数えない（Music レーンは元から半透明）
INK = r"""(()=>{ const out={}, d=devicePixelRatio;
  for(const id of ['speccv','ovcv']){ const c=document.getElementById(id), w=c.width, h=c.height; if(!w||!h){ out[id]=null; continue; }
    const px=c.getContext('2d').getImageData(0,0,w,h).data; let ink=0, n=0, clear=0;
    for(let y=(id==='ovcv'?Math.ceil(15*d):0);y<h-2;y++) for(let x=Math.ceil(132*d);x<w-2;x++){ const i=(y*w+x)*4; n++;
      if(id==='speccv'&&px[i+3]<255) clear++;
      else if(id==='speccv'? px[i]+px[i+1]+px[i+2]>150 : (px[i]>120&&px[i+1]>140&&px[i+2]>150&&px[i+3]>100)) ink++; }
    out[id]=clear?null:ink/n; }
  return out; })()"""


def _ink(ed):
    return wait_until(ed, f"(r=>r.speccv!=null&&r.ovcv!=null?r:null)({INK})", label="キャンバスが描かれている")


def _zoom(ed, notches):
    m = ed.js("window._dbgApp.musicScreen()")
    for _ in range(abs(notches)):
        ed.wheel(m["left"] + 400, m["top"] + m["h"] / 2, 120 if notches > 0 else -120, ctrl=True)
    ed.wait(0.2)
    return ed.js("window._dbgApp.tl().span")


def _seek(ed, b0):
    """停止中に窓の左端を b0 拍へ（seekEase は窓の左端を 再生位置−幅/2 にする）。描かれるまで待つ"""
    ed.js(f"window._dbg.rt.seekEase({b0}+window._dbgApp.tl().span/2,1)")
    wait_until(ed, f"Math.abs(window._dbgApp.tl().b0-({b0}))<1e-6", label="窓の左端")
    ed.js("new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(()=>r(0))))")


def test_drawn_at_all_zooms(t):
    '''長い曲（60秒＝タイル2枚）を読み込むと、既定・拡大・最も縮小した時のどれでもスペクトログラムと波形が描かれる'''
    ed = open_nle(t, "basic")
    ed.js(GEN)
    wait_until(ed, f"(r=>r.speccv>0.02)({INK})", timeout=30, label="スペクトログラムの解析と描画")
    base = _ink(ed)
    t.ok(base["ovcv"] > 0.05, f"既定の拡大で波形が描かれる: {base}")
    span_in = _zoom(ed, -4)
    r_in = _ink(ed)
    t.ok(span_in < 20 and r_in["speccv"] > 0.02 and r_in["ovcv"] > 0.05, f"拡大（{span_in}拍）: {r_in}")
    span_out = _zoom(ed, 14)
    _seek(ed, 0)
    r_out = _ink(ed)
    t.ok(span_out > 100 and r_out["speccv"] > 0.02 and r_out["ovcv"] > 0.05, f"最も縮小（{span_out}拍）: {r_out}")
    t.no_errors()


def test_scroll_moves_picture(t):
    '''縮小した窓を少しずつずらすと、絵はそのまま横にずれるだけ（前の絵をずらした物と次の絵がほぼ同じ）'''
    ed = open_nle(t, "basic")
    ed.js(GEN)
    wait_until(ed, f"(r=>r.speccv>0.02)({INK})", timeout=30, label="スペクトログラムの解析と描画")
    span = _zoom(ed, 8)
    t.ok(span > 80, f"縮小できた（{span}拍）")
    grab = r"""(()=>{ const c=document.getElementById('speccv'); return {w:c.width,h:c.height,css:c.getBoundingClientRect().width,
      d:Array.from(c.getContext('2d').getImageData(0,0,c.width,c.height).data)}; })()"""
    res = []
    for b0 in (6.0, 6.0 + span / 1600, 6.0 + 2 * span / 1600):   # 1回ごとに約0.5画素
        _seek(ed, b0)
        res.append(ed.js(grab))
    d = (span / 1600) / span * (res[0]["css"] - 128) * ed.js("devicePixelRatio")
    w, h = res[0]["w"], res[0]["h"]
    x0, x1 = int(132 * ed.js("devicePixelRatio")), w - 4

    def diff(A, B, shift):
        s = n = 0
        for y in range(0, h, 3):
            for x in range(x0, x1, 2):
                xs = x + shift
                i0 = int(xs)
                f = xs - i0
                for k in range(3):
                    a = A[(y * w + i0) * 4 + k] * (1 - f) + A[(y * w + i0 + 1) * 4 + k] * f
                    s += abs(B[(y * w + x) * 4 + k] - a)
                    n += 1
        return s / n
    moved = [diff(res[i]["d"], res[i + 1]["d"], d) for i in range(2)]
    still = diff(res[0]["d"], res[1]["d"], 0)
    t.info(f"ずらした分を補った差 {[round(v, 2) for v in moved]}・補わない差 {round(still, 2)}（0〜255・1回約 {round(d, 2)} 画素）")
    t.ok(max(moved) < 3, f"前の絵をずらした物と次の絵がほぼ同じ（差 {moved}）")
    t.ok(still > max(moved), "ずらした分を補わないと差は大きい（ちゃんと動いている）")
    t.no_errors()

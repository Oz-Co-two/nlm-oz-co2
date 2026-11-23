"""REPLAY の窓（js/replay/replay-pane.js）のテスト部品（e2e_misc/test_replay.py・画面テスト・英語表示の点検で使う）。

本物の裏側（serve.py の /__replay/* と viewer のサーバー・BL のリプレイアプリ）は別の作業で作る。ここでは:
- rp_mock(ed, ...): ページ内の fetch を差し替えて /__replay/* に決まった応答を返す（呼ばれた要求は rp_calls で読む）。
  open は「偽の窓」の URL を返す（要求の t＝開く位置を &time=<ミリ秒> に入れる・リプレイの長さは dur・最後の秒は item の endSec）。
- fake_viewer(): 偽のリプレイの窓のサーバー（http://localhost:<番号>）を1つ起こす。本物と同じく本体と別のオリジンで、CSP の
  frame-src（http://localhost:*）で許される形。取り決めの伝言（{nlm:'blr', cmd:'hello'|'seek'|'play'|'pause'} ⇄ ev:'hi'|'ready'|'time'|'zoom'）を話す。
  テストからは窓へ {nlm:'blr', test:'set'|'zoom'|'state'} を送って「リプレイの中で利用者が操作した」ことにする（rp_user）。
  窓が受けた命令は親へ {ev:'log'} で返し、テストの見張り（rp_watch）が window.__rpf.log に貯める（NLM の画面はこの ev を使わない）。
- 見本の一覧 ITEMS（素材 rich＝16 秒・BPM 120 に合わせた物）と、窓・状態を待つ部品。
"""
import base64
import hashlib
import http.server
import json
import socket
import threading

from e2e_helpers import wait_until

# ---- 偽のリプレイの窓 ----
FAKE_HTML = r"""<!doctype html><html><head><meta charset="utf-8"><title>fake replay viewer</title>
<style>html,body{margin:0;height:100%;background:#15151b;color:#7f8aa0;font:13px sans-serif}
body{display:flex;align-items:center;justify-content:center}</style></head>
<body><div>FAKE REPLAY VIEWER</div>
<script>
(function(){
  if (window.parent === window) return;
  const Q = new URLSearchParams(location.search);
  const S = {t: (+(Q.get('time')||0))/1000, playing:false, speed:1, dur: +(Q.get('dur')||16), ready:false, zoom:1};
  const readyAt = performance.now() + (+(Q.get('readyMs')||0));
  let PO = null, last = null, prev = performance.now();
  const wall = () => performance.timeOrigin + performance.now();
  const send = m => { if (PO) window.parent.postMessage(Object.assign({nlm:'blr'}, m), PO); };
  window.addEventListener('message', e => {
    if (e.source !== window.parent) return;
    const d = e.data; if (!d || d.nlm !== 'blr') return;
    PO = e.origin;
    if (d.cmd) send({ev:'log', cmd:d.cmd, t:(typeof d.t==='number'?d.t:null)});
    if (d.cmd === 'hello') { send({ev:'hi'}); if (S.ready) send({ev:'ready', dur:S.dur}); last = null; return; }
    if (d.cmd === 'seek' && isFinite(d.t)) S.t = Math.max(0, Math.min(S.dur - 0.01, +d.t));
    else if (d.cmd === 'play') { if (S.t >= S.dur - 0.011) S.t = 0; S.playing = true; }
    else if (d.cmd === 'pause') S.playing = false;
    // テストから（リプレイの窓の中で利用者が操作した・ホイールのズーム・今の状態）
    if (d.test === 'set') { if ('t' in d) S.t = +d.t; if ('playing' in d) S.playing = !!d.playing; if ('speed' in d) S.speed = +d.speed; }
    else if (d.test === 'zoom') { S.zoom = +d.level; send({ev:'zoom', level:S.zoom}); }
    else if (d.test === 'key') send({ev:'key', key:d.key, code:d.code||'', ctrl:!!d.ctrl, shift:!!d.shift, alt:false, repeat:false});   // 窓の中で押したキー（bridge.js が渡す形）
    else if (d.test === 'state') send({ev:'state', t:S.t, playing:S.playing, speed:S.speed, ready:S.ready});
  });
  function tick(now) {
    const dt = Math.max(0, (now - prev) / 1000); prev = now;
    if (PO && !S.ready && performance.now() >= readyAt) { S.ready = true; send({ev:'ready', dur:S.dur}); }
    if (S.ready && S.playing) { S.t += dt * S.speed; if (S.t >= S.dur) { S.t = S.dur; S.playing = false; } }
    if (S.ready) { const k = S.t.toFixed(4) + '|' + S.playing + '|' + S.speed;
      if (k !== last) { last = k; send({ev:'time', t:S.t, playing:S.playing, speed:S.speed, at:wall()}); } }
    requestAnimationFrame(tick);
  }
  requestAnimationFrame(tick);
})();
</script></body></html>"""


class _H(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.split("?", 1)[0] != "/index.html":
            self.send_error(404)
            return
        b = FAKE_HTML.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(b)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(b)

    def log_message(self, *a):
        pass


class _V6(http.server.ThreadingHTTPServer):
    address_family = socket.AF_INET6


_VIEWER = {}


def fake_viewer():
    """偽のリプレイの窓のサーバーを起こして（1つのプロセスで1回）オリジン http://localhost:<番号> を返す。
    本物の viewer と同じく 127.0.0.1 と ::1 の同じ番号で待つ（localhost が ::1 に先につながっても待たない）"""
    if "origin" in _VIEWER:
        return _VIEWER["origin"]
    s4 = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _H)
    port = s4.server_address[1]
    servers = [s4]
    try:
        servers.append(_V6(("::1", port), _H))
    except OSError:
        pass
    for s in servers:
        s.daemon_threads = True
        threading.Thread(target=s.serve_forever, daemon=True).start()
    _VIEWER["origin"] = f"http://localhost:{port}"
    _VIEWER["servers"] = servers
    return _VIEWER["origin"]


# ---- 見本の一覧（素材 rich: 曲名「リッチ テスト曲」・マッパー「NLM Tester」・16 秒・Hard と Expert） ----
NOW = 1795000000   # 2026-11 の頃の unix 秒
STATUS = {"source": "auto", "dirs": [{"path": "C:\\NLMTest\\BSManager\\BSInstances\\1.40.8\\UserData\\BeatLeader\\Replays", "count": 5}]}


def item(i, **kw):
    """一覧の1行（取り決めの item の形）。i＝新しい順の番号"""
    h = f"{i:02d}" * 20
    d = {"id": f"r{i}", "file": f"Player-リッチ テスト曲-{i}.bsor", "playedAt": NOW - i * 3600, "diff": "Expert", "mode": "Standard", "hash": h,
         "fail": False, "exit": False, "practice": False, "acc": 0.9321, "misses": 0, "bad": 0, "bombs": 0, "walls": 0, "mods": "",
         "endSec": 15.9, "jd": 17.5, "playable": True, "exportedAt": NOW - 86400, "latest": True}
    d.update(kw)
    return d


ITEMS = [
    item(1, misses=2, bad=1, mods="FS"),                                                     # 一番新しい・Expert・最新の書き出し
    item(2, diff="Hard", exit=True, endSec=6.0, acc=0.8812, latest=False, exportedAt=NOW - 3 * 86400, misses=4),   # 途中でやめた・以前の書き出し
    item(3, diff="ExpertPlus", playable=False, exportedAt=None, latest=False, acc=0.75, misses=9, bombs=1, walls=2),  # 譜面の控えが無い（灰色）
    item(4, mode="OneSaber", diff="Expert", fail=True, mods="NF,SS", practice=True),        # Standard 以外
    item(5, diff="Normal", acc=None),                                                        # この素材に無い難易度
]


# ---- 点を重ねる（/__replay/events の見本・素材 rich の Expert に合わせた物） ----
def rich_sec(beat):
    """素材 rich の拍 → 曲の秒（BPM 120・16 拍から 150）"""
    return beat * 0.5 if beat <= 16 else 8 + (beat - 16) * 0.4


def ev(beat, kind, x=0, y=0, c=0, score=None, mx=115, d=1):
    """/__replay/events の notes の1つ（取り決めの形: ボムは c・d が null・score/max は good の時だけ）"""
    e = {"t": round(rich_sec(beat), 4), "type": kind, "x": x, "y": y, "c": c, "d": d, "score": None, "max": None}
    if kind == "good":
        e["score"], e["max"] = score, mx
    if kind == "bomb":
        e["c"] = e["d"] = None
    return e


# Expert の物（beat, x, y, c）に合わせた出来事と、合う物の無い出来事（拍 7 のミス・拍 11 のボム）。
# 段（点数÷満点×115＝BL のリプレイアプリと同じ）: 115＝t115・113＝t113・112＝t110・107＝t106・104＝t100・90＝low・bad・miss・bomb。
# チェーン（拍 10・赤）は頭 85/85 と後ろ 4 つ（1 つミス）＝悪い方の miss、チェーン（拍 12・青）は頭 80/85（108.2＝t106）と後ろ 3 つ（20/20）
RICH_NOTES = [
    ev(1, "good", 1, 0, 0, 115), ev(1, "good", 2, 0, 1, 112),
    ev(2, "good", 1, 0, 0, 104), ev(2, "good", 2, 0, 1, 90),
    ev(3, "bad", 0, 1, 0), ev(3, "miss", 3, 1, 1),
    ev(4, "good", 1, 2, 0, 115), ev(4, "good", 2, 2, 1, 107),
    ev(5, "good", 0, 0, 0, 113), ev(6, "miss", 1, 1, 0),
    ev(7, "miss", 3, 2, 1),                                     # 合う物が無い（遊んだ後に消したノーツ）
    ev(8, "bomb", 0, 0),                                        # 拍 8 のボム（x0 y0）に当たった
    ev(10, "good", 1, 2, 0, 85, mx=85),
    ev(10.125, "good", 1, 1, 0, 20, mx=20), ev(10.25, "miss", 1, 1, 0), ev(10.375, "good", 1, 0, 0, 20, mx=20), ev(10.5, "good", 1, 0, 0, 20, mx=20),
    ev(11, "bomb", 2, 1),                                       # 合う物が無いボム
    ev(12, "good", 2, 2, 1, 80, mx=85),
    ev(12.17, "good", 2, 1, 1, 20, mx=20), ev(12.33, "good", 2, 1, 1, 20, mx=20), ev(12.5, "good", 2, 0, 1, 20, mx=20),
    ev(18, "good", 2, 0, 1, 115), ev(21, "bomb", 1, 2),
]
RICH_WALLS = [{"t": rich_sec(9)}, {"t": rich_sec(23)}]
RICH_EVENTS = {"ok": True, "notes": sorted(RICH_NOTES, key=lambda e: e["t"]), "walls": RICH_WALLS, "endSec": 15.9}


def rp_marks(ed):
    """点を重ねる の状態（window._dbgApp.rpMarks()）"""
    return ed.js("window._dbgApp.rpMarks()")


# ---- /__replay/* の偽物 ----
_MOCK_JS = r"""(()=>{ const A=window.__rp=window.__rp||{calls:[]};
  A.calls.length=0; A.q=%Q%; A.viewer=%V%; A.items=%ITEMS%; A.dur=%DUR%;
  const b64=u=>{ let s=''; for(let i=0;i<u.length;i+=0x8000) s+=String.fromCharCode.apply(null,u.subarray(i,i+0x8000)); return btoa(s); };
  if(!A.installed){ A.installed=true; const of=window.fetch.bind(window);
    window.fetch=async function(url,opt){ const u=String(url), m=u.match(/^(?:\.?\/)?__replay\/([A-Za-z]+)(\?.*)?$/);
      if(!m) return of(url,opt);
      const act=m[1], body=opt&&opt.body; let parsed=null, bytes=null;
      if(typeof body==='string'){ try{ parsed=JSON.parse(body); }catch(_){} }
      else if(body instanceof Blob) bytes=new Uint8Array(await body.arrayBuffer());
      else if(body instanceof ArrayBuffer) bytes=new Uint8Array(body);
      else if(body&&ArrayBuffer.isView(body)) bytes=new Uint8Array(body.buffer,body.byteOffset,body.byteLength);
      const qs=new URLSearchParams(m[2]||'');
      const rec={act,url:u,method:(opt&&opt.method)||'GET',headers:(opt&&opt.headers)||{},body:parsed,query:Object.fromEntries(qs),len:bytes?bytes.length:(typeof body==='string'?body.length:0)};
      if(bytes&&bytes.length<=4*1024*1024) rec.b64=b64(bytes);
      A.calls.push(rec);
      let r=A.q[act];
      if(Array.isArray(r)) r=r.length>1?r.shift():r[0];
      if(r==='auto'&&act==='open'){ const it=A.items.find(x=>x.id===(parsed&&parsed.id));
        if(!it) r={ok:false,error:'not-found'};
        else { const ms=parsed&&typeof parsed.t==='number'?Math.round(parsed.t*1000):0;
          r={ok:true,url:A.viewer+'/index.html?id='+encodeURIComponent(it.id)+'&dur='+A.dur+'&time='+ms+(A.readyMs?'&readyMs='+A.readyMs:''),
             origin:A.viewer,endSec:it.endSec,diff:it.diff,mode:it.mode,hash:it.hash}; } }
      if(r===undefined) r={http:404,body:{ok:false,error:'unknown endpoint'}};
      if(r&&r.waitFor){ const f=r.waitFor; while(!(A.go&&A.go[f])) await new Promise(res=>setTimeout(res,30)); r=r.then; }
      if(r&&r.netErr) throw new TypeError('Failed to fetch');
      const status=(r&&r.http)||200, b=(r&&r.http)?r.body:r;
      return new Response(JSON.stringify(b),{status,headers:{'content-type':'application/json'}}); }; }
  return true; })()"""


def rp_mock(ed, items=None, status=None, dur=16, **over):
    """/__replay/* の応答を差し替える。items＝一覧（既定 ITEMS）・status＝リプレイの場所・dur＝偽の窓のリプレイの長さ（秒）。
    over で動作ごとの応答を上書き（list / open / status / resetFolder / keep / keepEgg / events。配列は1つずつ使い最後の1つを繰り返す・
    {"http":404,...}・{"netErr":true}・{"waitFor":名前,"then":応答}）。open の既定 'auto'＝偽の窓の URL"""
    items = ITEMS if items is None else items
    status = STATUS if status is None else status
    q = {"status": {"ok": True, **status}, "resetFolder": {"ok": True, "source": "auto", "dirs": status["dirs"]},
         "list": {"ok": True, "status": status, "items": items}, "open": "auto",
         "keep": {"ok": True, "hash": "ab" * 20, "isNew": True, "needEgg": True}, "keepEgg": {"ok": True},
         "events": {"ok": True, "notes": [], "walls": [], "endSec": 15.9}}
    q.update(over)
    ed.js(_MOCK_JS.replace("%Q%", json.dumps(q, ensure_ascii=False)).replace("%V%", json.dumps(fake_viewer()))
          .replace("%ITEMS%", json.dumps(items, ensure_ascii=False)).replace("%DUR%", json.dumps(dur)))


def rp_set(ed, key, value):
    """偽物の設定を後から変える（例: readyMs＝偽の窓が ready を送るまでの ms・go＝waitFor の旗）"""
    ed.js(f"window.__rp[{json.dumps(key)}]={json.dumps(value)};true")


def rp_go(ed, flag):
    ed.js(f"(window.__rp.go=window.__rp.go||{{}})[{json.dumps(flag)}]=true;true")


def rp_calls(ed, act=None):
    return [c for c in ed.js("window.__rp.calls") if act is None or c["act"] == act]


def call_parts(c):
    """keep の要求の本体を ?m= の名前・大きさで切り分ける → [(名前, bytes)]"""
    m = json.loads(c["query"]["m"])
    raw = base64.b64decode(c["b64"])
    out, pos = [], 0
    for f in m["files"]:
        out.append((f["name"], raw[pos:pos + f["size"]]))
        pos += f["size"]
    assert pos == len(raw), f"本体の長さ {len(raw)} と ?m= の合計 {pos} が違う"
    return out


def sha1_of(c):
    return hashlib.sha1(base64.b64decode(c["b64"])).hexdigest()


# ---- 偽の窓の見張り（窓が受けた命令・窓の今の状態） ----
_WATCH_JS = r"""(()=>{ const W=window.__rpf=window.__rpf||{log:[],state:null};
  W.origin=%V%; W.log.length=0;
  if(!W.installed){ W.installed=true;
    window.addEventListener('message',e=>{ const d=e.data; if(e.origin!==W.origin||!d||d.nlm!=='blr') return;
      if(d.ev==='log') W.log.push({cmd:d.cmd,t:d.t,at:performance.now()});
      else if(d.ev==='state') W.state=d; }); }
  return true; })()"""


def rp_watch(ed):
    """偽の窓が受けた命令を window.__rpf.log に貯め始める（前の記録は消す）"""
    ed.js(_WATCH_JS.replace("%V%", json.dumps(fake_viewer())))


def rp_log(ed, cmd=None):
    """偽の窓が受けた命令 [{cmd,t}]（cmd を渡すとその命令だけ。hello は除く）"""
    return [x for x in ed.js("window.__rpf.log") if x["cmd"] != "hello" and (cmd is None or x["cmd"] == cmd)]


def rp_clear_log(ed):
    ed.js("window.__rpf.log.length=0;true")


def rp_user(ed, **kw):
    """リプレイの窓の中で利用者が操作した（t＝時刻の棒・playing＝再生ボタン・speed＝スロー）。zoom=倍率でホイールのズーム"""
    if "zoom" in kw:
        msg = {"nlm": "blr", "test": "zoom", "level": kw["zoom"]}
    else:
        msg = {"nlm": "blr", "test": "set", **kw}
    ed.js(f"(f=>{{ if(!f) return false; f.contentWindow.postMessage({json.dumps(msg)},{json.dumps(fake_viewer())}); return true; }})(document.getElementById('rpFrame'))")


def rp_frame_state(ed):
    """偽の窓の今の状態（{t, playing, speed, ready}）"""
    ed.js("window.__rpf.state=null;true")
    rp_user_raw(ed, {"nlm": "blr", "test": "state"})
    return wait_until(ed, "window.__rpf.state", label="偽の窓の状態")


def rp_user_raw(ed, msg):
    ed.js(f"(f=>{{ if(!f) return false; f.contentWindow.postMessage({json.dumps(msg)},{json.dumps(fake_viewer())}); return true; }})(document.getElementById('rpFrame'))")


# ---- 画面 ----
def rp(ed):
    """REPLAY の窓の状態（window._dbgApp.replay()）"""
    return ed.js("window._dbgApp.replay()")


def load_named(ed, fx="basic", name="Basic Test Song", mapper="NLM Tester", settle=0.3):
    """素材を曲名・マッパーを書き換えて読む（ed.load_fixture と同じ流れ。basic は曲名が空＝REPLAY の一覧を頼まない。英語の点検は日本語の曲名を避ける）"""
    wav = "basic"
    ed.js(f"""(async()=>{{ const rt=window._dbg.rt;
      const pj=await (await fetch('tools/fixtures/{fx}.nlmf',{{cache:'no-store'}})).json();
      pj.info=pj.info||{{}}; pj.info._songName={json.dumps(name)}; pj.info._levelAuthorName={json.dumps(mapper)};
      for(const n of Object.values((pj.infoGraph&&pj.infoGraph.nodes)||{{}})) if(n.t==='meta'){{ n.data.name={json.dumps(name)}; n.data.author={json.dumps(mapper)}; }}
      await rt.applyProject(pj);
      const blob=await (await fetch('tools/fixtures/{wav}.wav',{{cache:'no-store'}})).blob();
      const file=new File([blob],'{wav}.wav',{{type:'audio/wav'}});
      await rt.loadSongFromItem({{isMusic:true,name:'{fx}',songFh:{{getFile:async()=>file}},info:{{_beatsPerMinute:pj.bpm}}}},pj.musicBeat||0);
      return true; }})()""")
    ed.wait(settle)


def hover_pv(ed):
    """左上の窓の上（ボタン・リプレイの窓（iframe）の上を避ける＝窓の上のマウスの動きは親に届かない）"""
    p = ed.js("""(()=>{const r=document.getElementById('pvpane').getBoundingClientRect();
      for(const [fx,fy] of [[0.5,0.6],[0.3,0.75],[0.12,0.035],[0.5,0.035]]){ const x=r.left+r.width*fx, y=r.top+r.height*fy, e=document.elementFromPoint(x,y);
        if(e&&e.closest('#pvpane')&&!e.closest('button,input,select,iframe,.tbi,.rpRow,.mlNext,.mlItem')) return {x,y}; }
      return {x:r.left+12,y:r.top+r.height-6}; })()""")
    ed.move(p["x"], p["y"])
    ed.wait(0.15)


def to_replay(ed):
    """左上の窓を REPLAY にする（窓の上で Tab を押す・MEDIA から2回）"""
    for _ in range(3):
        if ed.js("window._dbgApp.replay().pvMode") == "replay":
            break
        hover_pv(ed)
        ed.key("Tab")
        ed.wait(0.2)
    wait_until(ed, "window._dbgApp.replay().pvMode==='replay'&&document.getElementById('bodyRp').classList.contains('on')", label="REPLAY へ")


def wait_list(ed, n=None):
    """一覧を読み終わるまで（n＝行の数）"""
    cond = "(r=>r&&r.shown&&!r.loading" + (f"&&r.rows.length==={n}" if n is not None else "") + ")(window._dbgApp.replay())"
    return wait_until(ed, cond, label="REPLAY の一覧")


def wait_state(ed, st, timeout=15.0):
    """窓の状態（none/loading/ready/linked）になるまで"""
    return wait_until(ed, f"window._dbgApp.replay().state==={json.dumps(st)}", timeout=timeout, label=f"REPLAY の窓が {st}")


def wait_nlm_sec(ed, sec, tol=0.05, label=None):
    """NLM の再生位置（秒）が sec に近づくまで"""
    return wait_until(ed, f"Math.abs(window._dbgApp.replay().nlm.sec-({sec}))<{tol}", label=label or f"NLM の位置が {sec} 秒")


def click_row(ed, rid):
    r = ed.js(f"""(()=>{{const e=document.querySelector('#rpList .rpRow[data-id="{rid}"]'); if(!e||!e.checkVisibility()) return null;
        e.scrollIntoView({{block:'nearest'}}); const r=e.getBoundingClientRect(); return {{x:r.left+r.width/2,y:r.top+r.height/2}}}})()""")
    if not r:
        raise AssertionError(f"一覧の行が見えていません: {rid}")
    ed.click(r["x"], r["y"])
    ed.wait(0.15)


def click_id(ed, sel):
    r = ed.js(f"""(()=>{{const e=document.querySelector({json.dumps(sel)}); if(!e||!e.checkVisibility()) return null;
        const r=e.getBoundingClientRect(); return {{x:r.left+r.width/2,y:r.top+r.height/2}}}})()""")
    if not r:
        raise AssertionError(f"見えていません: {sel}")
    ed.click(r["x"], r["y"])
    ed.wait(0.15)


def open_replay(ed, **mock):
    """偽物を差して REPLAY を出し、一番新しい再生できるリプレイ（r1）が自動で開いてつながるまで"""
    rp_mock(ed, **mock)
    rp_watch(ed)
    to_replay(ed)
    wait_list(ed)
    wait_state(ed, "linked")


def replay_tour(ed, scan):
    """英語表示の点検（english_ui_helpers.tour から）: REPLAY の一覧（灰色の行・札・版・場所）・再生（要点・知らせ・ズームの案内）・空の一覧・フォルダが無い。
    点を重ねる（凡例・合わない数・NLE の印のツールチップ・難易度が違う知らせ。素材 basic の Expert には合う物が無い＝全部合わない）"""
    rp_mock(ed, events=RICH_EVENTS)
    rp_watch(ed)
    to_replay(ed)
    wait_list(ed)
    wait_state(ed, "linked")
    scan(ed, "REPLAY 再生")
    wait_until(ed, "(m=>m&&m.on&&m.marks.length>0)(window._dbgApp.rpMarks())&&window._dbgApp.replay().mkChips.length>0", label="点の印と凡例")
    q = ed.js("window._dbgApp.rpMarks().marks[0]")
    ed.move(q["x"] + q["w"] / 2, q["y"] + q["h"] / 2)
    wait_until(ed, "!!document.getElementById('ndcv').title", label="点の印のツールチップ")
    scan(ed, "REPLAY 点を重ねる（凡例・合わない数・印のツールチップ）")
    g = ed.js("window._dbgApp.nleScreen(0)")
    ed.move(g["left"] + g["w"] * 0.6, g["lanes"] + 40); ed.wait(0.15)
    ed.key("3")   # 難易度を変える＝点は重ねない（知らせ）
    wait_until(ed, "window._dbgApp.replay().mkMsg.length>0", label="難易度が違う知らせ")
    scan(ed, "REPLAY 点を重ねる（難易度が違う）")
    ed.key("4")
    wait_until(ed, "window._dbgApp.rpMarks().on", label="Expert へ戻す")
    rp_user(ed, zoom=1.8)
    wait_until(ed, "window._dbgApp.replay().zoom===1.8", label="ズーム")
    scan(ed, "REPLAY 再生（ズーム）")
    click_id(ed, "#rpBack")
    wait_until(ed, "window._dbgApp.replay().view==='list'", label="一覧へ")
    ed.move(*_row_xy(ed, "r3")); ed.wait(0.3)
    scan(ed, "REPLAY 一覧")
    click_row(ed, "r4")   # Standard 以外＝難易度は今のまま（知らせ）・失敗・練習の札
    wait_state(ed, "linked")
    scan(ed, "REPLAY 再生（Standard 以外）")
    click_id(ed, "#rpBack")
    rp_mock(ed, items=[])
    click_id(ed, "#rpReloadList")
    wait_list(ed, 0)
    scan(ed, "REPLAY 空の一覧")
    rp_mock(ed, items=[], status={"source": "none", "dirs": []})
    click_id(ed, "#rpReloadList")
    wait_until(ed, "window._dbgApp.replay().empty.length>0&&window._dbgApp.replay().status.source==='none'", label="フォルダが無い")
    scan(ed, "REPLAY フォルダが無い")
    hover_pv(ed); ed.key("Tab"); ed.wait(0.4)   # MEDIA へ戻す


def _row_xy(ed, rid):
    r = ed.js(f"""(()=>{{const e=document.querySelector('#rpList .rpRow[data-id="{rid}"]'); const r=e.getBoundingClientRect(); return [r.left+r.width/2,r.top+r.height/2]}})()""")
    return r[0], r[1]

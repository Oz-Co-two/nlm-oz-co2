"""曲の構成（区切りと、同じ・似ている区間のグループ）を解析する。

使い方:
  .venv/Scripts/python tools/analyze_structure.py <音源> --nlmf <プロジェクト.nlmf>
  .venv/Scripts/python tools/analyze_structure.py <音源> --bpm 84 --lead-ms 260

--nlmf を渡すと BPM・無音追加・テンポパート・Music の配置をプロジェクトから読み、マーカーがあれば
答え合わせ（一致率）も出す。結果は音源と同じフォルダの <名前>.structure.html（再生して確かめられる報告）と
<名前>.structure.json（区間の一覧）。拍の番号は NLM の拍（無音追加を含めた曲頭＝拍0）。

計算は本体に同梱する song_analysis/structure.py にある（2026-10-19 に移した。NLM の「曲を解析」と同じ計算）。
このファイルは .nlmf の読み込み・答え合わせ・報告（HTML・JSON・表示）だけ。song_analysis/structure.py の名前は
このモジュールからもそのまま使え、このモジュールの定数を書き換えると song_analysis/structure.py にも効く
（調整用のスクリプトの A.SECTION_SAME = … 等のため。song_analysis.expose）。

仕組み（詳しくは tools/README.md の「曲の構成の解析」）:
 1. 拍の目盛りの4分の1拍ごとに、音色（MFCC）と歌の音域の音の高さ（CQT の C4〜C6）を測る。
 2. 「似ている所のつながり」で曲を分ける方法（ラプラシアン分割、McFee & Ellis 2014）をグループ数 4〜12 で
    9回行い、区切りは多数決、グループは「同じグループになった回数の割合」で決める（曲ごとに合う数が違うため）。
    比べる幅などは「1単位」（BPM 84 なら1拍、BPM 119 以上なら2拍）で決める。
 3. 似ている長い区間どうしを重ね、同じ所と違う所の境目で両方を分け直す（1番と2番で後半だけ同じ、など）。
 4. 2 の多数決で隣どうしの同じグループをまとめ、最後に「多数決」と「区間どうしを重ねた時の似ている度合い」の
    幾何平均でグループに分ける。表に出す「似ている度合い」は、重ねた時の値（1単位ぶんの流れごとに比べた平均）。
    グループの他のどの区間とも重ねた度合いが低い区間は、そのグループから外す（member_check）。
 5. 同じグループのフレーズが2〜3回続いて1本につながった区間は、回数ぶんに分ける（split_repeats）。
 6. セクションの段（build_sections）: 細かい区切りのうち、同じ並びで繰り返す組（例 B C B C）をまとめ（1つ20秒まで）、
    番号は中身（細かいグループの割合）で付ける。相手の無いセクションが続く所どうしは、まとめた全体でも比べる
    （同じパートが1番と2番で違う割れ方をした時）。1回しか出ない短いセクションが続く所は1つにまとめる。
    サビの候補は、2回以上出るセクションのうち長さ×音の大きさが一番大きいもの（中身の割合だけの緩い仲間で数える）。
 7. 名前の推測（name_sections）: セクションに仮の名前（イントロ/Aメロ/Bメロ/サビ/間奏/Cメロ/アウトロ）を並び方から付ける。
"""
import argparse
import base64
import html
import json
import os
import struct
import sys
import time
import urllib.parse
import warnings
import zlib

import numpy as np
import scipy.ndimage

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import song_analysis  # noqa: E402
from song_analysis import structure as _core  # noqa: E402
from song_analysis.structure import (SUB, Analyzer, TempoMap, build_result, build_sections, chorus_groups,  # noqa: E402,F401
                                     measure, name_sections, section_rows, unit_scale)

warnings.filterwarnings("ignore")
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
song_analysis.expose(_core, __name__)


def load_nlmf(path):
    pj = json.load(open(path, encoding="utf-8"))
    g = pj.get("graph") or {}
    song = g.get("song") or {}
    tm = TempoMap(float(pj.get("bpm") or 120),
                  [(float(p["beat"]), float(p["bpm"])) for p in pj.get("tempoParts") or []],
                  float(song.get("offset") or 0.0),
                  float(pj.get("musicBeat") or 0.0),
                  pj.get("musicSegs") or None)
    markers = [{"beat": float(m["beat"]), "name": str(m.get("name") or "")} for m in pj.get("markers") or []]
    return tm, sorted(markers, key=lambda m: m["beat"]), song.get("name") or ""


# ---- 答え合わせ（マーカーがある時） ----

def score_vs_markers(segs, lab, markers, lo, hi):
    gt = np.array([m["beat"] * SUB for m in markers])
    est = [a for a, _ in segs[1:]]

    def bound_f(tol, part=None):
        used, hit = set(), 0
        for e in est:
            d = np.abs(gt - e); j = int(np.argmin(d))
            if d[j] <= tol and j not in used:
                used.add(j); hit += 1
        p, r = hit / max(len(est), 1), hit / max(len(gt), 1)
        return {"p": p, "r": r}.get(part, 2 * p * r / max(p + r, 1e-9))

    names = sorted({m["name"] for m in markers})
    g = np.full(hi, -1); e = np.full(hi, -1)
    for i, m in enumerate(markers):
        a = int(round(m["beat"] * SUB)); b = int(round(markers[i + 1]["beat"] * SUB)) if i + 1 < len(markers) else hi
        g[a:b] = names.index(m["name"])
    for (a, b), l in zip(segs, lab):
        e[a:b] = l
    m = (g >= 0) & (np.arange(hi) >= lo)
    G = g[m][:, None] == g[m][None, :]; E = e[m][:, None] == e[m][None, :]
    iu = np.triu_indices(int(m.sum()), 1)
    tp = np.sum(G[iu] & E[iu]); p = tp / max(np.sum(E[iu]), 1); r = tp / max(np.sum(G[iu]), 1)
    return {"bound1": bound_f(SUB), "bound2": bound_f(2 * SUB), "group": 2 * p * r / max(p + r, 1e-9),
            "found2": bound_f(2 * SUB, "r"), "hit2": bound_f(2 * SUB, "p")}


# ---- 出力 ----

def score_title(markers):
    return "正解ファイルとの答え合わせ" if markers and markers[0].get("truth") else "マーカーとの答え合わせ"


def sim_word(v):
    return "ほぼ同じ" if v >= 0.7 else "よく似ている" if v >= 0.5 else "似ている"


def fmt_t(s):
    return f"{int(s // 60)}:{s % 60:05.2f}"


def png_data_uri(S, lo_v, hi_v):
    g = (np.clip((S - lo_v) / (hi_v - lo_v), 0, 1) * 255).astype(np.uint8)
    raw = b"".join(b"\x00" + g[r].tobytes() for r in range(g.shape[0]))

    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)

    data = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", g.shape[1], g.shape[0], 8, 0, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))
    return "data:image/png;base64," + base64.b64encode(data).decode()


def write_html(path, audio_path, title, tm, F, ana, rows, chorus, markers, score, meta, sections=None, sec_score=None):
    out_dir = os.path.dirname(os.path.abspath(path))
    try:
        src = urllib.parse.quote(os.path.relpath(os.path.abspath(audio_path), out_dir).replace("\\", "/"))
    except ValueError:   # 別のドライブ
        src = "file:///" + urllib.parse.quote(os.path.abspath(audio_path).replace("\\", "/"))
    # 地図は斜め方向に1拍ぶんならして（繰り返しの線を見やすくする）、半拍ごとに縮める
    S = scipy.ndimage.convolve(ana.S, np.eye(SUB) / SUB, mode="nearest")
    n2 = S.shape[0] // 2
    S2 = S[:n2 * 2, :n2 * 2].reshape(n2, 2, n2, 2).mean(axis=(1, 3))
    img = png_data_uri(S2, np.percentile(S2, 60), np.percentile(S2, 99))
    at = [None if np.isnan(x) else round(float(x), 3) for x in F["at"]]
    data = {"rows": rows, "secs": sections or [], "markers": markers, "at": at, "sub": SUB, "lo": ana.lo / SUB,
            "hi": ana.hi / SUB, "end": F["n"] / SUB, "chorus": chorus,
            "mkLabel": "正解" if markers and markers[0].get("truth") else "マーカー",
            "nlmT": [round(tm.t(i / SUB), 3) for i in range(F["n"] + 1)]}
    js_data = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    score_html = ""
    if score:
        score_html = (f'<p class="score">{html.escape(score_title(markers))}（細かい区切り）: 区切りの一致 ±1拍 <b>{score["bound1"] * 100:.0f}%</b>'
                      f' ・ ±2拍 <b>{score["bound2"] * 100:.0f}%</b> ・ グループ分けの一致 <b>{score["group"] * 100:.0f}%</b>'
                      f'（{len(markers)} 個を正解とした F 値）<br><span class="note">±2拍の内訳: 正解の区切りのうち見つけた割合'
                      f' {score["found2"] * 100:.0f}% ・ 出した区切りのうち正解に合う割合 {score["hit2"] * 100:.0f}%'
                      f'（正解より細かく区切ると後者が下がる）</span>')
        if sec_score:
            score_html += (f'<br>セクションの段: ±2拍で正解を見つけた {sec_score["found2"] * 100:.0f}% ・ '
                           f'出した区切りが正解に合う {sec_score["hit2"] * 100:.0f}% ・ グループ分けの一致 {sec_score["group"] * 100:.0f}%')
        score_html += "</p>"
    doc = TEMPLATE.replace("__TITLE__", html.escape(title)).replace("__SRC__", html.escape(src)) \
        .replace("__META__", html.escape(meta)).replace("__SCORE__", score_html) \
        .replace("__IMG__", img).replace("__DATA__", js_data)
    with open(path, "w", encoding="utf-8") as f:
        f.write(doc)


TEMPLATE = r"""<!doctype html>
<html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>曲の構成 __TITLE__</title>
<style>
:root{--bg:#f7f7f5;--fg:#1d1d1f;--mut:#6b6b70;--line:#d9d9dc;--card:#fff;--hl:#fff3c4}
@media (prefers-color-scheme:dark){:root{--bg:#18181a;--fg:#ececee;--mut:#9a9aa0;--line:#38383c;--card:#222225;--hl:#4a4020}}
*{box-sizing:border-box}
body{margin:0;padding:20px 16px 40px;background:var(--bg);color:var(--fg);font:14px/1.6 "Segoe UI","Yu Gothic UI",Meiryo,sans-serif}
main{max-width:1200px;margin:0 auto}
h1{font-size:20px;margin:0 0 4px}
h2{font-size:15px;margin:28px 0 8px}
.meta,.note{color:var(--mut);font-size:12.5px;margin:0}
.score{margin:6px 0 0}
audio{width:100%;margin:14px 0 6px}
#tl{width:100%;height:auto;display:block;cursor:pointer;background:var(--card);border:1px solid var(--line);border-radius:6px}
.groups{display:flex;flex-wrap:wrap;gap:6px}
.chip{display:inline-flex;align-items:center;gap:6px;padding:3px 10px;border-radius:999px;border:1px solid var(--line);background:var(--card);font-size:13px;color:var(--fg);font-family:inherit}
button.chip{cursor:pointer}
.sw{width:12px;height:12px;border-radius:3px;display:inline-block}
table{width:100%;border-collapse:collapse;background:var(--card);border:1px solid var(--line);border-radius:6px;overflow:hidden;font-size:13px}
th,td{padding:5px 8px;border-bottom:1px solid var(--line);text-align:left;white-space:nowrap}
th{font-weight:600;color:var(--mut);font-size:12px}
td.num{text-align:right;font-variant-numeric:tabular-nums}
tr.now td{background:var(--hl)}
tbody tr{cursor:pointer}
.wrap{overflow-x:auto}
.map{display:flex;gap:16px;flex-wrap:wrap;align-items:flex-start}
#ssm{width:min(100%,560px);height:auto;image-rendering:pixelated;cursor:crosshair;border:1px solid var(--line);border-radius:4px;background:#000}
#mapInfo{min-width:220px;flex:1}
</style></head><body><main>
<h1>曲の構成の解析: __TITLE__</h1>
<p class="meta">__META__</p>
__SCORE__
<audio id="au" controls preload="auto" src="__SRC__"></audio>
<canvas id="tl" width="1200" height="180"></canvas>
<p class="note">帯をクリックするとその区間の頭から、目盛りの段をクリックするとその位置から再生します。
<b>細かい区切り</b>: 同じ色＝同じグループ（音が同じか似ている区間）。
<b>セクション</b>: 細かい区切りのうち、同じ並びで繰り返す組をまとめた物（同じ番号＝中身が同じ。★＝サビの候補）。</p>
<h2>セクションと名前</h2>
<p class="note">名前は、並び方から決まりごとで付けた<b>仮の物</b>です（歌の有無は見ていないので、間奏と歌のパートを取り違えることがあります）。
番号を押すと、同じ番号のセクションの名前をまとめて付け直せます（このページを開き直すと元に戻ります。控えは［名前の一覧をコピー］で）。</p>
<div class="groups" id="secs"></div>
<p><button id="copyNames">名前の一覧をコピー</button> <span class="note" id="copyMsg"></span></p>
<h2>グループ</h2>
<div class="groups" id="groups"></div>
<h2>区間の一覧</h2>
<div class="wrap"><table><thead><tr><th></th><th>グループ</th><th>拍</th><th>NLMの時刻</th><th>長さ</th><th>一番似ている所（同じグループ）</th><th>マーカー</th></tr></thead><tbody id="rows"></tbody></table></div>
<h2>似ている所の地図</h2>
<div class="map"><canvas id="ssm"></canvas><div id="mapInfo"><p class="note">横も縦も曲の時間（左上が曲頭）。明るい所ほど似ています。
右下へ向かう<b>斜めの線</b>は「同じ流れの繰り返し」、<b>明るい四角</b>は「同じ雰囲気が続く所」。
クリックすると、その点の横の位置から再生します（縦の位置は下に表示）。</p><p id="mapPos" class="note"></p></div></div>
<img id="ssmImg" src="__IMG__" alt="" hidden>
<script type="application/json" id="data">__DATA__</script>
<script>
const D=JSON.parse(document.getElementById('data').textContent);
const au=document.getElementById('au');
const PAL=['#e4572e','#4c9be8','#f2b134','#3fb37f','#a66fd6','#ef7fb1','#58c4c4','#9b8b6e','#7d8cf0','#c4c94a','#d9883b','#5fa35a'];
const groups=[...new Set(D.rows.map(r=>r.group))];
const col=g=>PAL[groups.indexOf(g)%PAL.length];
const fmt=s=>s==null?'—':`${Math.floor(s/60)}:${(s%60).toFixed(1).padStart(4,'0')}`;
// 拍 → 元の音源の秒（その拍に音が無ければ、次に音のある所）
function audioAt(b){let i=Math.max(0,Math.floor(b*D.sub));const f=Math.max(0,b*D.sub-i);
  while(i<D.at.length&&D.at[i]==null)i++;if(i>=D.at.length)return null;
  const n=(i+1<D.at.length&&D.at[i+1]!=null)?D.at[i+1]:D.at[i];return D.at[i]+(n-D.at[i])*Math.min(f,1);}
function beatAt(t){let best=null,bd=1e9;for(let i=0;i<D.at.length;i++){const a=D.at[i];if(a==null)continue;const d=Math.abs(a-t);if(d<bd){bd=d;best=i;}}return best==null?0:best/D.sub;}
function playBeat(b){const t=audioAt(b);if(t==null)return;au.currentTime=t;au.play();}
const mk=(tag,txt,cls)=>{const e=document.createElement(tag);if(txt!=null)e.textContent=txt;if(cls)e.className=cls;return e;};
// グループ
const gEl=document.getElementById('groups');
for(const g of groups){const rs=D.rows.filter(r=>r.group===g);const c=mk('span',null,'chip');const sw=mk('span',null,'sw');sw.style.background=col(g);
  c.append(sw,mk('b',g),document.createTextNode(` ${rs.length}回`+(D.chorus.includes(g)?'（サビの候補）':'')+' ・ 拍 '+rs.map(r=>+r.start.toFixed(2)).join(', ')));gEl.append(c);}
// 一覧
const tb=document.getElementById('rows');const trs=[];
D.rows.forEach((r,i)=>{const tr=mk('tr');const btn=mk('td','▶');const gd=mk('td');const sw=mk('span',null,'sw');sw.style.background=col(r.group);
  gd.append(sw,document.createTextNode(' '+r.group));
  const ms=D.markers.filter(m=>m.beat>=r.start-1&&m.beat<r.end-1).map(m=>`${m.name}@${m.beat}`).join(' ');
  const best=r.best==null?'（1回だけ）':`拍 ${+r.best.toFixed(2)} と ${(r.sim*100).toFixed(0)}・${r.sim>=0.7?'ほぼ同じ':r.sim>=0.5?'よく似ている':'似ている'}`;
  tr.append(btn,gd,mk('td',`${+r.start.toFixed(2)} 〜 ${+r.end.toFixed(2)}`,'num'),mk('td',fmt(D.nlmT[Math.round(r.start*D.sub)]),'num'),
    mk('td',`${+(r.end-r.start).toFixed(2)} 拍`,'num'),mk('td',best),mk('td',ms));
  tr.addEventListener('click',()=>playBeat(r.start));tb.append(tr);trs.push(tr);});
// 帯
const cv=document.getElementById('tl'),cx=cv.getContext('2d');
const css=getComputedStyle(document.documentElement);
const PADL=86,PADR=10,ROW={ruler:[8,26],sec:[32,56],est:[62,104],mk:[112,170]};
const SPAL=['#5b6c8f','#8f6b5b','#5b8f78','#8a5b8f','#8f875b','#5b858f','#8f5b6e','#6e8f5b','#6b5b8f','#8f7a5b'];
const secIds=[...new Set(D.secs.map(s=>s.label))];
const scol=l=>SPAL[secIds.indexOf(l)%SPAL.length];
const bx=b=>PADL+(cv.width-PADL-PADR)*b/D.end, xb=x=>(x-PADL)/(cv.width-PADL-PADR)*D.end;
function draw(){const W=cv.width;cx.clearRect(0,0,W,cv.height);const fg=css.getPropertyValue('--fg'),mut=css.getPropertyValue('--mut'),line=css.getPropertyValue('--line');
  cx.font='12px "Segoe UI","Yu Gothic UI",sans-serif';cx.fillStyle=mut;cx.textBaseline='middle';
  cx.fillText('拍',8,17);if(D.secs.length)cx.fillText('セクション',8,44);cx.fillText('細かい区切り',8,83);if(D.markers.length)cx.fillText(D.mkLabel,8,141);
  for(const s of D.secs){const x0=bx(s.start),x1=bx(s.end);cx.fillStyle=scol(s.label);cx.fillRect(x0+0.5,ROW.sec[0],x1-x0-1,ROW.sec[1]-ROW.sec[0]);
    cx.font='bold 12px "Segoe UI",sans-serif';   // 収まらない幅では番号を出さない（切れて別の番号に見えるため）
    const full=(s.name?s.name+' ':'')+s.label+(s.chorus?'★':''),short=s.name||s.label;
    const sl=[full,short,s.label].find(t=>x1-x0>cx.measureText(t).width+8)||'';
    if(sl){cx.fillStyle='#fff';cx.fillText(sl,x0+4,(ROW.sec[0]+ROW.sec[1])/2);}
    cx.font='12px "Segoe UI","Yu Gothic UI",sans-serif';}
  for(let b=0;b<=D.end;b+=4){const x=bx(b);cx.strokeStyle=line;cx.globalAlpha=b%16===0?1:0.45;cx.beginPath();cx.moveTo(x,ROW.ruler[0]+(b%16===0?0:8));cx.lineTo(x,ROW.ruler[1]);cx.stroke();
    if(b%16===0){cx.globalAlpha=1;cx.fillStyle=mut;cx.fillText(String(b),x+2,ROW.ruler[0]+3);}}
  cx.globalAlpha=1;
  for(const r of D.rows){const x0=bx(r.start),x1=bx(r.end);cx.fillStyle=col(r.group);cx.fillRect(x0+0.5,ROW.est[0],x1-x0-1,ROW.est[1]-ROW.est[0]);
    cx.font='bold 13px "Segoe UI",sans-serif';
    if(x1-x0>cx.measureText(r.group).width+8){cx.fillStyle='#fff';cx.fillText(r.group,x0+4,(ROW.est[0]+ROW.est[1])/2);}
    cx.font='12px "Segoe UI","Yu Gothic UI",sans-serif';}
  D.markers.forEach((m,i)=>{const x=bx(m.beat);cx.strokeStyle=fg;cx.beginPath();cx.moveTo(x,ROW.mk[0]);cx.lineTo(x,ROW.mk[1]);cx.stroke();
    cx.fillStyle=fg;cx.fillText(m.name,x+3,ROW.mk[0]+8+(i%3)*16);});
  const pb=beatAt(au.currentTime);if(!au.paused||au.currentTime>0){const x=bx(pb);cx.strokeStyle='#e00';cx.lineWidth=2;cx.beginPath();cx.moveTo(x,2);cx.lineTo(x,cv.height-2);cx.stroke();cx.lineWidth=1;}
  const cur=D.rows.findIndex(r=>pb>=r.start&&pb<r.end);trs.forEach((t,i)=>t.classList.toggle('now',i===cur&&(!au.paused||au.currentTime>0)));}
function fit(){cv.width=Math.max(600,cv.clientWidth);cv.height=180;draw();}
cv.addEventListener('click',e=>{const r=cv.getBoundingClientRect();const x=(e.clientX-r.left)*cv.width/r.width,y=(e.clientY-r.top)*cv.height/r.height;const b=xb(x);
  if(y>=ROW.sec[0]&&y<=ROW.sec[1]){const s=D.secs.find(q=>b>=q.start&&b<q.end);if(s){playBeat(s.start);return;}}
  if(y>=ROW.est[0]&&y<=ROW.est[1]){const s=D.rows.find(q=>b>=q.start&&b<q.end);if(s){playBeat(s.start);return;}}playBeat(Math.max(0,b));});
// セクションと名前（番号ごと。押すと同じ番号の名前をまとめて付け直す）
const secEl=document.getElementById('secs');
function fillSecs(){secEl.textContent='';
  for(const l of secIds){const ss=D.secs.filter(s=>s.label===l);const c=mk('button',null,'chip');const sw=mk('span',null,'sw');sw.style.background=scol(l);
    const names=[...new Set(ss.map(s=>s.name||'—'))].join(' / ');
    c.append(sw,mk('b',l+(ss[0].chorus?'★':'')),document.createTextNode(` ${names} ・ ${ss.length}回 ・ `+ss.map(s=>fmt(D.nlmT[Math.round(s.start*D.sub)])).join(', ')));
    c.title='押すと、'+l+' の名前をまとめて付け直します';
    c.addEventListener('click',()=>{const v=prompt(l+' の名前（同じ番号のセクション全部に付けます）',ss[0].name||'');if(v==null)return;
      for(const s of ss)s.name=v.trim();fillSecs();draw();});
    secEl.append(c);}}
fillSecs();
document.getElementById('copyNames').addEventListener('click',()=>{
  const txt=D.secs.map(s=>`${fmt(D.nlmT[Math.round(s.start*D.sub)])}\t拍 ${+s.start.toFixed(2)}\t${s.label}\t${s.name||''}`).join('\n');
  navigator.clipboard.writeText(txt).then(()=>{document.getElementById('copyMsg').textContent='コピーしました（時刻・拍・番号・名前の表）';},
    ()=>{document.getElementById('copyMsg').textContent='コピーできませんでした';});});
window.addEventListener('resize',fit);au.addEventListener('timeupdate',draw);au.addEventListener('seeked',draw);
(function loop(){if(!au.paused)draw();requestAnimationFrame(loop);})();fit();
// 地図
const img=document.getElementById('ssmImg'),sc=document.getElementById('ssm'),sx=sc.getContext('2d');
img.onload=()=>{const n=img.naturalWidth,B=10;sc.width=n+B;sc.height=n+B;sx.imageSmoothingEnabled=false;sx.drawImage(img,B,B);
  for(const r of D.rows){const a=(r.start-D.lo)*2,e=(r.end-D.lo)*2;sx.fillStyle=col(r.group);sx.fillRect(B+a,0,e-a,B-2);sx.fillRect(0,B+a,B-2,e-a);}};
if(img.complete)img.onload();
sc.addEventListener('click',e=>{const r=sc.getBoundingClientRect();const k=sc.width/r.width;const x=(e.clientX-r.left)*k-10,y=(e.clientY-r.top)*k-10;
  const bxv=D.lo+x/2,byv=D.lo+y/2;document.getElementById('mapPos').textContent=`横: 拍 ${bxv.toFixed(1)} ／ 縦: 拍 ${byv.toFixed(1)}（横の位置から再生中）`;playBeat(bxv);});
</script></main></body></html>
"""


def main():
    ap = argparse.ArgumentParser(description="曲の構成（区切りと同じ・似ている区間）を解析する")
    ap.add_argument("path", help="音源ファイル（mp3/ogg/flac/wav など）")
    ap.add_argument("--nlmf", help="NLM のプロジェクト。BPM・無音追加・テンポパート・Music の配置・マーカーを読む")
    ap.add_argument("--bpm", type=float, help="BPM（--nlmf より優先）")
    ap.add_argument("--lead-ms", type=float, help="無音追加 ms（--nlmf より優先）")
    ap.add_argument("--out", help="報告の HTML の出力先（既定: 音源と同じフォルダの <名前>.structure.html）")
    ap.add_argument("--truth", help="答え合わせ用の正解 JSON（{\"sections\":[{\"beat\":拍,\"name\":名前},…]}）。"
                                    "マーカーの代わりに使う")
    ap.add_argument("--unit", type=float, help="1単位の拍数（既定: BPM から自動。BPM 119 未満=1、238 未満=2）。"
                                               "細切れなら大きく、粗すぎるなら小さくする")
    a = ap.parse_args()

    markers, title = [], os.path.splitext(os.path.basename(a.path))[0]
    if a.nlmf:
        tm, markers, _ = load_nlmf(a.nlmf)
    else:
        if a.bpm is None:
            sys.exit("--bpm（または --nlmf）が必要です")
        tm = TempoMap(a.bpm)
    if a.bpm is not None:
        tm.bpm = a.bpm
    if a.lead_ms is not None:
        tm.song_off = -a.lead_ms / 1000
    if a.truth:
        sec = json.load(open(a.truth, encoding="utf-8"))["sections"]
        markers = sorted(({"beat": float(s["beat"]), "name": str(s["name"]), "truth": True} for s in sec),
                         key=lambda m: m["beat"])
    out = a.out or os.path.join(os.path.dirname(os.path.abspath(a.path)), title + ".structure.html")

    t0 = time.time()
    F = measure(a.path, tm)
    scale = a.unit or unit_scale(tm.bpm)   # テンポパートがあっても曲頭の BPM で決める
    ana = Analyzer(F, scale, tm.bpm)
    segs, lab, K = ana.run()
    rows, _ = build_result(ana, segs, lab, K, tm, F)
    sec_segs, sec_lab, sec_chorus = build_sections(segs, lab, ana.fps, F["E"], ana.section_sim)
    sections = section_rows(sec_segs, sec_lab, sec_chorus)
    chorus = chorus_groups(segs, lab, sec_segs, sec_lab, sec_chorus)
    for sec, nm in zip(sections, name_sections(sections, rows, chorus, tm.bpm)):
        sec["name"] = nm
    took = time.time() - t0
    score = score_vs_markers(segs, lab, markers, ana.lo, F["n"]) if markers else None
    sec_score = score_vs_markers(sec_segs, sec_lab, markers, ana.lo, F["n"]) if markers else None

    lead = -tm.song_off * 1000
    meta = (f"BPM {tm.bpm:g}{'（テンポパートあり）' if tm.parts else ''} ・ 無音追加 {lead:.0f} ms ・ "
            f"1単位 {scale:g}拍 ・ セクション {len(sections)} ・ 区間 {len(rows)} ・ グループ {len(set(lab))} ・ 解析 {took:.0f} 秒")
    print(f"{title}: {meta}")
    if score:
        print(f"{score_title(markers)}: 区切り ±1拍 {score['bound1'] * 100:.0f}% / ±2拍 {score['bound2'] * 100:.0f}% / "
              f"グループ分け {score['group'] * 100:.0f}%（±2拍の内訳: 正解を見つけた {score['found2'] * 100:.0f}% ・ "
              f"出した区切りが正解に合う {score['hit2'] * 100:.0f}%）")
        print(f"  セクションの段: ±2拍で正解を見つけた {sec_score['found2'] * 100:.0f}% ・ 出した区切りが正解に合う "
              f"{sec_score['hit2'] * 100:.0f}% ・ グループ分け {sec_score['group'] * 100:.0f}%")
    print("\nセクション: " + " ".join(f"{s['label']}({s['name']})@{s['start']:g}" for s in sections))
    print(f"\n{'拍':>15}  {'NLMの時刻':>9}  {'長さ':>7}  グループ  一番似ている所")
    for r in rows:
        mk = " ".join(f"{m['name']}@{m['beat']:g}" for m in markers if r["start"] - 1 <= m["beat"] < r["end"] - 1)
        best = "（1回だけ）" if r["best"] is None else f"拍 {r['best']:g} と {r['sim'] * 100:.0f}・{sim_word(r['sim'])}"
        tag = "（サビの候補）" if r["group"] in chorus else ""
        print(f"{r['start']:7.2f}〜{r['end']:7.2f}  {fmt_t(tm.t(r['start'])):>9}  {r['end'] - r['start']:5.2f}拍  "
              f"{r['group']}{tag:<8} {best}" + (f"   [マーカー: {mk}]" if mk else ""))

    write_html(out, a.path, title, tm, F, ana, rows, chorus, markers, score, meta, sections, sec_score)
    with open(os.path.splitext(out)[0] + ".json", "w", encoding="utf-8") as f:
        json.dump({"bpm": tm.bpm, "leadMs": lead, "chorus": chorus, "sections": sections, "segments": rows,
                   "score": score, "sectionScore": sec_score}, f, ensure_ascii=False, indent=1)
    print(f"\n報告: {out}")


if __name__ == "__main__":
    main()

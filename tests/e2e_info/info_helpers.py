"""e2e_info グループの共通部品（INFO・自動ライティング・カバー補正の操作用）。
共有の tests/_lib/e2e_helpers.py は変えず、このグループだけで使う小道具をここに置く。"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "_lib"))
from e2e_helpers import hover_3d, open_fixture   # noqa: E402,F401
from e2e_helpers import wait_until as _wait_until   # noqa: E402


def wait_until(ed, expr, timeout=15.0, label=""):
    """状態の待ち合わせ（共有版と同じだが既定を15秒に。他のテストと並列に動いてPCが混む時に5秒では足りないことがある）"""
    return _wait_until(ed, expr, timeout=timeout, label=label)

# 要素の中央（表示されていなければ null）を返す JS
_CENTER_JS = """(()=>{{const e=document.querySelector({sel});if(!e)return null;
  const r=e.getBoundingClientRect();return r.width>0&&r.height>0?{{x:r.left+r.width/2,y:r.top+r.height/2}}:null}})()"""


def center(ed, selector):
    """要素の中央の画面座標（表示されていなければ None）"""
    return ed.js(_CENTER_JS.format(sel=json.dumps(selector)))


def click_sel(ed, selector, label=None):
    """要素が表示されるまで待って、本物のマウスで中央をクリック"""
    p = wait_until(ed, _CENTER_JS.format(sel=json.dumps(selector)), label=label or f"{selector} が表示される")
    ed.click(p["x"], p["y"])
    return p


def click_text(ed, selector, text):
    """selector に合う要素のうち、文字がちょうど text のものをクリック"""
    p = wait_until(ed, f"""(()=>{{const e=[...document.querySelectorAll({json.dumps(selector)})].find(b=>b.textContent.trim()==={json.dumps(text)});
      if(!e)return null;const r=e.getBoundingClientRect();return r.width>0?{{x:r.left+r.width/2,y:r.top+r.height/2}}:null}})()""",
                   label=f"{selector} 「{text}」")
    ed.click(p["x"], p["y"])


def dialog_text(ed):
    """確認画面（#dirtyDlg）の文字。出ていなければ None"""
    return ed.js("(()=>{const d=document.getElementById('dirtyDlg');return d?d.innerText:null})()")


def wait_dialog(ed, label="確認画面"):
    return wait_until(ed, "(()=>{const d=document.getElementById('dirtyDlg');return d?d.innerText:null})()", label=label)


def wait_dialog_closed(ed):
    wait_until(ed, "!document.getElementById('dirtyDlg')", label="確認画面が閉じる")


def toast(ed):
    return ed.js("(()=>{const e=document.getElementById('errToast');return e&&e.style.display!=='none'?e.textContent:''})()")


def file_menu(ed, act):
    """ファイルメニューを開いて項目（data-act）をクリック。PCが混んでいてメニューを開くクリックが効かなかった時は押し直す"""
    item = f"#mFileMenu [data-act={act}]"
    for i in range(3):
        click_sel(ed, "#mFileBtn", "ファイルメニュー")
        try:
            wait_until(ed, _CENTER_JS.format(sel=json.dumps(item)), timeout=4.0, label=f"メニュー {act}")
            break
        except AssertionError:
            if i == 2:
                raise
    click_sel(ed, item, f"メニュー {act}")


_INFO_BOTTOM_JS = "(()=>{const r=document.getElementById('inspcol').getBoundingClientRect();return {x:r.left+r.width*0.5,y:r.bottom-30}})()"


def undo(ed):
    """3Dビューの上（INFO表示中は INFO の上）にマウスを置いて Ctrl+Z"""
    if ed.js("window._dbgApp.view()") == "info":
        r = ed.js(_INFO_BOTTOM_JS)
        ed.move(r["x"], r["y"])
    else:
        hover_3d(ed)
    ed.key("z", ctrl=True)
    ed.wait(0.15)


def to_info(ed):
    """NLEの上にマウスを置いて Tab ＝ INFOへ（読込直後は配置が動いていて効かないことがある＝切り替わるまで押し直す）"""
    for _ in range(5):
        if ed.js("window._dbgApp.view()") == "info":
            break
        g = ed.js("window._dbgApp.nleScreen(0)")
        ed.move(g["left"] + g["w"] * 0.6, g["lanes"] + 40)
        ed.wait(0.2)
        ed.key("Tab")
        try:
            _wait_until(ed, "window._dbgApp.view()==='info'", timeout=3.0)
        except AssertionError:
            pass
    wait_until(ed, "window._dbgApp.view()==='info'", label="INFOへの切替")
    ed.wait(0.3)


def mapcheck_keys(ed):
    """譜面チェック（BS Map Check）の判定の項目キーを難易度ごとに返す"""
    return ed.js("""(async()=>{
      const mc=await import('./js/mapcheck/mapcheck.js');
      const p=await window._dbgApp.mapCheckInput(); const res=mc.runMapCheck(p);
      return Object.fromEntries(res.diffs.map(d=>[d.difficulty,d.results.map(x=>x.key)])); })()""")


# ---- ブラウザのピッカー（ファイル/フォルダ選択）の代わり ----
# アプリ本体は pywebview 外では showOpenFilePicker / showDirectoryPicker を使う。ページ内で差し替え、画像は canvas で作る（PIL 不要）
_PICKERS_JS = r"""(()=>{
  if(window.__fsw) return true;
  window.__fsw={};   // 'CustomLevels/<フォルダ>/<ファイル>' → Blob（アプリが書いたもの）
  window.__pickImage=null;   // 次の showOpenFilePicker が返す File
  const mkDir=path=>({kind:'directory',name:path.split('/').pop(),
    async getDirectoryHandle(n){ return mkDir(path+'/'+n); },
    async getFileHandle(n,o){ const p=path+'/'+n;
      if(!(o&&o.create)&&!window.__fsw[p]) throw new DOMException('not found','NotFoundError');
      return {kind:'file',name:n,async getFile(){ return window.__fsw[p]; },
        async createWritable(){ const ch=[]; return {async write(d){ ch.push(d); },async close(){ window.__fsw[p]=new Blob(ch); }}; }}; }});
  window.showDirectoryPicker=async()=>mkDir('CustomLevels');
  window.showOpenFilePicker=async()=>{ const f=window.__pickImage; if(!f) throw new DOMException('cancel','AbortError');
    return [{kind:'file',name:f.name,async getFile(){ return f; }}]; };
  return true; })()"""


def install_pickers(ed):
    ed.js(_PICKERS_JS)


def set_pick_image(ed, w, h, mime="image/png", name="art.png", colors=("#e03030", "#3050e0")):
    """次に「画像を選択」で選ばれる画像を canvas で作る（左半分=colors[0]・右半分=colors[1]）"""
    ed.js(f"""(async()=>{{
      const cv=document.createElement('canvas'); cv.width={w}; cv.height={h}; const g=cv.getContext('2d');
      g.fillStyle={json.dumps(colors[0])}; g.fillRect(0,0,{w}/2,{h}); g.fillStyle={json.dumps(colors[1])}; g.fillRect({w}/2,0,{w},{h});
      const b=await new Promise(r=>cv.toBlob(r,{json.dumps(mime)}));
      window.__pickImage=new File([b],{json.dumps(name)},{{type:b.type}}); return b.type; }})()""")


def written(ed):
    """アプリが（偽の出力フォルダへ）書いたファイル {パス: サイズ}"""
    return ed.js("Object.fromEntries(Object.entries(window.__fsw||{}).map(([k,b])=>[k,b.size]))")


def written_text(ed, path):
    return ed.js(f"window.__fsw[{json.dumps(path)}].text()")


def image_size(ed, path):
    """書かれた画像ファイルの寸法 [幅, 高さ] と先頭4バイト"""
    return ed.js(f"""(async()=>{{ const b=window.__fsw[{json.dumps(path)}]; const bmp=await createImageBitmap(b);
      const head=[...new Uint8Array(await b.slice(0,4).arrayBuffer())]; const r={{w:bmp.width,h:bmp.height,head}}; bmp.close(); return r; }})()""")


def node_rect(ed, node_id):
    """INFOのノード（data-node）の画面上の矩形"""
    return ed.js(f"""(()=>{{const e=document.querySelector('#infoWorld .iGrp[data-node={json.dumps(node_id)}]');if(!e)return null;
      const r=e.getBoundingClientRect();return {{x:r.left,y:r.top,w:r.width,h:r.height}}}})()""")


_MC_DONE = ("(()=>{const p=document.getElementById('mcPanel');return !!p&&p.style.display!=='none'"
            "&&!p.querySelector('.mcRerun').disabled&&p.querySelector('.mcBody').children.length>0})()")


def open_mapcheck(ed):
    """INFOの「譜面チェック」ボタンで結果パネルを開き、結果が出るまで待つ（INFO表示中であること）"""
    click_sel(ed, '#iMapCheck', '譜面チェックのボタン')
    wait_until(ed, _MC_DONE, timeout=20, label='チェック結果の表示')


def wait_mapcheck_done(ed):
    wait_until(ed, _MC_DONE, timeout=20, label='チェック結果の表示')


def type_text(ed, text):
    """入力欄にフォーカスがある状態で文字を入力（本物の入力イベント）"""
    ed.call("Input.insertText", text=text)


def pixel(ed, path, x, y):
    """書かれた画像の画素 [r,g,b,a]"""
    return ed.js(f"""(async()=>{{ const bmp=await createImageBitmap(window.__fsw[{json.dumps(path)}]);
      const cv=document.createElement('canvas'); cv.width=bmp.width; cv.height=bmp.height; const g=cv.getContext('2d'); g.drawImage(bmp,0,0);
      const d=g.getImageData({x},{y},1,1).data; bmp.close(); return [d[0],d[1],d[2],d[3]]; }})()""")


# ---- INFO のノード操作 ----
def info_graph(ed):
    return ed.js("window._dbgApp.infoGraph()")


def free_spot(ed, skip=0):
    """INFOの何も無い所（背景）の画面座標。skip 個目の候補を返す（複数欲しい時用）"""
    pts = ed.js("""(()=>{const col=document.getElementById('inspcol'), r=col.getBoundingClientRect(), out=[];
      for(let y=r.top+60;y<r.bottom-40;y+=40) for(let x=r.left+60;x<r.right-60;x+=60){
        const e=document.elementFromPoint(x,y); if(e&&(e===col||e.id==='infoWorld'||e.id==='infoEdgeSvg'||e.id==='infoPortSvg')) out.push({x,y}); }
      return out})()""")
    assert len(pts) > skip, "INFOに空きが見つかりません"
    return pts[skip]


def world_at(ed, x, y):
    """画面座標 → INFOのワールド座標（アプリの infoWorldXY と同じ式）"""
    return ed.js(f"""(()=>{{const r=document.getElementById('inspcol').getBoundingClientRect(), c=window._dbgApp.infoGraph().cam;
      return {{x:({x}-r.left-c.x)/c.s, y:({y}-r.top-c.y)/c.s}}}})()""")


def node_types(ed):
    return {k: v["t"] for k, v in info_graph(ed)["nodes"].items()}


def edges(ed):
    return sorted((e["s"], e["o"]) for e in info_graph(ed)["edges"])


def select_node(ed, key):
    """ノードの見出しをクリックして選択（out は 'out:o1'）"""
    reveal(ed, key)
    click_sel(ed, f"#infoWorld .iGrp[data-node='{key}'] h3", f"ノード {key} の見出し")


def hover_info(ed):
    """INFOの空きにマウスを置く（キー操作の効き先をINFOにする）"""
    p = free_spot(ed)
    ed.move(p["x"], p["y"])


def reveal(ed, key):
    """ノード（'m2' / 'out:o1'）がINFOの表示枠に収まるように、中ボタンのドラッグで画面をずらす（枠の外は押せないため）。
    収まっていれば何もしない。ずらした後の矩形を返す"""
    sel = f"#infoWorld .iGrp[data-node='{key}']"
    for _ in range(3):
        v = ed.js(f"""(()=>{{const e=document.querySelector("{sel}"), c=document.getElementById('inspcol').getBoundingClientRect(), r=e.getBoundingClientRect();
          return {{top:r.top-c.top, bottom:c.bottom-r.bottom, left:r.left-c.left, right:c.right-r.right, cx:(c.left+c.right)/2, cy:(c.top+c.bottom)/2,
            h:r.height, w:r.width, ch:c.height}}}})()""")
        margin = 8
        dy = 0 if v["top"] >= margin and v["bottom"] >= margin else (v["ch"] - v["h"]) / 2 - v["top"]
        dx = 0 if v["left"] >= margin and v["right"] >= margin else (v["right"] - v["left"]) / 2
        if not dx and not dy:
            break
        p = free_spot(ed)
        before = info_graph(ed)["cam"]
        ed.drag(p["x"], p["y"], p["x"] + dx, p["y"] + dy, button="middle")
        wait_until(ed, f"(c=>c.x!=={before['x']}||c.y!=={before['y']})(window._dbgApp.infoGraph().cam)", label="画面のパン")
    return node_rect(ed, key)

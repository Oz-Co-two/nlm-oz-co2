"""e2e_misc グループの共通部品（BPM自動判定・exe版のネイティブ経路・環境設定・難易度を測る）。

- install_fake_pywebview(ed, ...): exe版（pywebview）でだけ使う window.pywebview.api をページ内の偽物にする。
  アプリ本体は変えない。ページを読み込んだ「後」に差すので、開発用窓口（?dev=1 は pywebview 外だけ有効）はそのまま使える。
  偽物は app.py の Api と同じ許可範囲（書き込みは許可済みフォルダの中・拡張子は _WRITE_EXTS だけ 等）で動き、
  呼ばれた関数と引数を window.__nat.calls に残す。仮想のファイル置き場は window.__nat.files（パス→中身base64）。
- native_*: 偽物の記録の読み出し・ファイルの追加・状態の持ち越し（ページを開き直しても同じ「PC」を再現する）。
- stub_convert(ed): song.egg の変換（/__convert/toOgg＝ffmpeg）を偽物にして、呼ばれ方だけ記録する。
- prefs_*: 環境設定ダイアログの操作と localStorage(bsnm_*) の読み出し・後始末。
"""
import json
import sys
from contextlib import contextmanager
from pathlib import Path

_T = Path(__file__).resolve().parents[1]
for _p in (_T / "_lib", _T / "e2e_info", _T / "e2e_project"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from e2e_helpers import hover_3d, open_fixture, wait_until   # noqa: E402,F401
from info_helpers import (center, click_sel, click_text, file_menu, node_rect, to_info, toast, type_text,   # noqa: E402,F401
                          wait_dialog, wait_dialog_closed)
from project_helpers import install_fake_fs, queue_open   # noqa: E402,F401

def fresh_page(t):
    """t.fresh()（素材なし）の後、起動中の覆い（#bootCover）が外れるのを待つ。覆いが残っているとクリックがそこに当たる"""
    ed = t.fresh()
    wait_until(ed, "!document.getElementById('bootCover')", label="起動中の覆いが外れる")
    return ed


def open_fixture_ready(t, fx, settle=0.3):
    """素材を読み込んで開く（open_fixture）＋起動中の覆いが外れるのを待つ"""
    ed = open_fixture(t, fx, settle=settle)
    wait_until(ed, "!document.getElementById('bootCover')", label="起動中の覆いが外れる")
    return ed


# ---- 仮想のPC上のパス（Windows形式）。偽物の中ではすべて小文字・バックスラッシュに揃えて比べる ----
OUT_BASE = "C:\\NLMTest\\CustomLevels"
SONG_PATH = "C:\\NLMTest\\Music\\clicks.wav"
COVER_PATH = "C:\\NLMTest\\Art\\cover_src.png"

_FAKE_JS = r"""(()=>{
  const F=window.__nat={calls:[],files:{},dirs:{},approved:{},picked:{},queue:{folder:[],image:[],song:[]},dirty:[],quit:0};
  const norm=p=>String(p||'').replace(/\//g,'\\').replace(/\\+$/,'').toLowerCase();
  const rec=(fn,...args)=>{ F.calls.push({fn,args}); };
  const baseName=p=>String(p).split(/[\\/]/).filter(Boolean).pop()||'';
  const dirName=p=>{ const s=String(p); const i=s.lastIndexOf('\\'); return i>=0?s.slice(0,i):''; };
  const extOf=n=>{ const i=n.lastIndexOf('.'); return i>=0?n.slice(i).toLowerCase():''; };
  const IMG=['.png','.jpg','.jpeg','.webp','.gif','.bmp'];
  const AUD=['.egg','.ogg','.oga','.opus','.mp3','.m4a','.aac','.wav','.flac','.weba','.webm'];
  const WRITE=['.dat','.egg','.json',...IMG];          // app.py の _WRITE_EXTS
  const READ=[...AUD,...IMG];                           // app.py の _READ_EXTS
  const under=(d,p)=>{ const q=norm(p); return q===d||q.startsWith(d+'\\'); };
  const inOut=p=>Object.keys(F.approved).some(d=>under(d,p));
  const canRead=p=>READ.includes(extOf(String(p)))||!!F.picked[norm(p)]||inOut(p);
  const canWrite=p=>{ const n=baseName(p); return !n.includes(':')&&WRITE.includes(extOf(n))&&inOut(dirName(p)); };
  const child=(base,name)=>(!name||name==='.'||name==='..'||/[\/\\:]/.test(name))?null:(String(base).replace(/[\\\/]+$/,'')+'\\'+name);
  F.addDir=(p,approved)=>{ F.dirs[norm(p)]=String(p); if(approved) F.approved[norm(p)]=String(p); };
  F.addFile=(p,b64,mtime)=>{ F.files[norm(p)]={path:String(p),b64,mtime:mtime||1700000000}; };
  F.write=[];   // fs_write の記録（パス・サイズ・先頭4バイト・最初の書き込みか）
  window.pywebview={api:{
    async set_dirty(on){ F.dirty.push(!!on); },
    async quit_app(){ F.quit++; },
    async pick_song_file(){ rec('pick_song_file'); const p=F.queue.song.shift()||null; if(p) F.picked[norm(p)]=1; return p; },
    async pick_image_file(start){ rec('pick_image_file',start); const p=F.queue.image.shift()||null; if(p) F.picked[norm(p)]=1; return p; },
    async pick_folder(start){ rec('pick_folder',start); const p=F.queue.folder.shift()||null; if(p) F.addDir(p,true); return p; },   // 選ばれた＝許可（app.py の approve_dir）
    async read_song_file(path){ rec('read_song_file',path); const f=F.files[norm(path)];
      if(!f) return {ok:false,error:'not-found'};
      if(!canRead(path)) return {ok:false,error:'not-allowed'};
      return {ok:true,name:baseName(path),mtime:f.mtime,data:f.b64}; },
    async out_dir_ok(path){ rec('out_dir_ok',path); if(!path||!F.dirs[norm(path)]) return 'missing'; return inOut(path)?'ok':'unapproved'; },
    async fs_isfile(path){ rec('fs_isfile',path); return !!path&&!!F.files[norm(path)]&&canRead(path); },
    async fs_subdir(base,name,create){ rec('fs_subdir',base,name,!!create);
      if(!base||!inOut(base)) return {ok:false,error:'not-allowed'};
      const p=child(base,name); if(!p) return {ok:false,error:'bad-name'};
      if(create) F.addDir(p,false);
      if(!F.dirs[norm(p)]) return {ok:false,error:'not-found'};
      return {ok:true,path:p}; },
    async fs_file(base,name,create){ rec('fs_file',base,name,!!create);
      if(!base||!inOut(base)) return {ok:false,error:'not-allowed'};
      const p=child(base,name); if(!p) return {ok:false,error:'bad-name'};
      if(!create&&!F.files[norm(p)]) return {ok:false,error:'not-found'};
      return {ok:true,path:p}; },
    async fs_write(path,b64){ rec('fs_write',path,(b64||'').length);
      if(!path||!F.dirs[norm(dirName(path))]) return {ok:false,error:'no-dir'};
      if(!canWrite(path)) return {ok:false,error:'not-allowed'};
      F.files[norm(path)]={path:String(path),b64,mtime:Math.floor(Date.now()/1000)};
      const bin=atob(b64.slice(0,8)); F.write.push({path:String(path),size:Math.floor(atob(b64).length),head:[...bin].slice(0,4).map(c=>c.charCodeAt(0))});
      return {ok:true}; },
  }};
  return true; })()"""


def install_fake_pywebview(ed, approved=(), dirs=(), state=None):
    """exe版の window.pywebview.api を偽物にする。approved=許可済みの出力フォルダ（このPCで選んだことがあるもの）、
    dirs=存在するが未許可のフォルダ。state=native_state() で取っておいた状態（ページを開き直した後に同じ「PC」を再現する）"""
    ed.js(_FAKE_JS)
    if state:
        ed.js(f"""(()=>{{ const s={json.dumps(state)}, F=window.__nat;
          for(const k in s.files) F.files[k]=s.files[k];
          for(const k in s.dirs) F.dirs[k]=s.dirs[k];
          for(const k in s.approved) F.approved[k]=s.approved[k];
          for(const k in s.picked) F.picked[k]=1; return true; }})()""")
    for d in approved:
        ed.js(f"window.__nat.addDir({json.dumps(d)},true)")
    for d in dirs:
        ed.js(f"window.__nat.addDir({json.dumps(d)},false)")


def native_state(ed):
    """偽の「PC」の中身（ファイル・フォルダ・許可）。ページを開き直す前に取り、install_fake_pywebview(state=) で戻す"""
    return ed.js("(()=>{const F=window.__nat; return {files:F.files,dirs:F.dirs,approved:F.approved,picked:F.picked}})()")


def native_calls(ed, *fns):
    """偽物の関数が呼ばれた記録 [{fn,args}]。fns を渡すとその関数だけ"""
    calls = ed.js("window.__nat.calls")
    return [c for c in calls if not fns or c["fn"] in fns]


def native_reset_calls(ed):
    ed.js("window.__nat.calls.length=0; window.__nat.write.length=0; true")


def native_writes(ed):
    """fs_write で書かれたファイル（パス→{size, head}）。同じパスへ2回書けば後の方"""
    return {w["path"]: {"size": w["size"], "head": w["head"]} for w in ed.js("window.__nat.write")}


def native_write_log(ed):
    """fs_write の記録を書かれた順に [{path,size,head}]"""
    return ed.js("window.__nat.write")


def _k(path):
    """偽物の中での比較用の正規化（app.py の _npath 相当: 区切りを揃え・末尾の区切りを外し・小文字）"""
    return path.replace("/", "\\").rstrip("\\").lower()


def native_file_text(ed, path):
    """仮想のPCのファイルの中身（UTF-8の文字列）。無ければ None"""
    return ed.js(f"""(()=>{{ const f=window.__nat.files[{json.dumps(_k(path))}]; if(!f) return null;
      const bin=atob(f.b64), u=new Uint8Array(bin.length); for(let i=0;i<bin.length;i++) u[i]=bin.charCodeAt(i);
      return new TextDecoder().decode(u); }})()""")


def native_file_b64(ed, path):
    return ed.js(f"""(()=>{{ const f=window.__nat.files[{json.dumps(_k(path))}]; return f?f.b64:null; }})()""")


def native_add_file_from_url(ed, path, url):
    """ページから取れる URL（例: tools/fixtures/basic.wav）の中身を、仮想のPCの path に置く"""
    ed.js(f"""(async()=>{{ const b=await (await fetch({json.dumps(url)},{{cache:'no-store'}})).blob();
      const u=await new Promise(r=>{{const fr=new FileReader(); fr.onload=()=>r(fr.result); fr.readAsDataURL(b);}});
      window.__nat.addFile({json.dumps(path)}, u.slice(u.indexOf(',')+1)); return true; }})()""")


def native_add_png(ed, path, w=300, h=300, colors=("#e03030", "#3050e0")):
    """canvas で作った PNG（左半分=colors[0]・右半分=colors[1]）を仮想のPCの path に置く。置いた中身の base64 を返す"""
    return ed.js(f"""(async()=>{{
      const cv=document.createElement('canvas'); cv.width={w}; cv.height={h}; const g=cv.getContext('2d');
      g.fillStyle={json.dumps(colors[0])}; g.fillRect(0,0,{w}/2,{h}); g.fillStyle={json.dumps(colors[1])}; g.fillRect({w}/2,0,{w},{h});
      const b=await new Promise(r=>cv.toBlob(r,'image/png'));
      const u=await new Promise(r=>{{const fr=new FileReader(); fr.onload=()=>r(fr.result); fr.readAsDataURL(b);}});
      const b64=u.slice(u.indexOf(',')+1); window.__nat.addFile({json.dumps(path)}, b64); return b64; }})()""")


def native_queue(ed, kind, path):
    """次にネイティブのダイアログで選ばれるもの（kind=folder/image/song）。キューが空ならキャンセル扱い"""
    ed.js(f"window.__nat.queue[{json.dumps(kind)}].push({json.dumps(path)})")


# ---- song.egg の変換（ffmpeg）を偽物にする ----
_CONVERT_JS = r"""(()=>{
  if(window.__conv) { window.__conv.calls.length=0; window.__conv.mode=__MODE__; return true; }
  const C=window.__conv={calls:[],mode:__MODE__};
  const of=window.fetch.bind(window);
  window.fetch=async function(url,opt){
    if(String(url).startsWith('__convert/toOgg')){
      const body=opt&&opt.body; const head=body?[...new Uint8Array(body.slice(0,4))]:[];
      C.calls.push({url:String(url),method:(opt&&opt.method)||'GET',headers:(opt&&opt.headers)||{},len:body?body.byteLength:0,head});
      if(C.mode==='ok'){ const u=new Uint8Array(64); u.set([0x4F,0x67,0x67,0x53]); for(let i=4;i<64;i++) u[i]=i;   // "OggS"+適当な中身
        return new Response(u,{status:200,headers:{'content-type':'audio/ogg'}}); }
      return new Response(JSON.stringify({ok:false,error:C.mode}),{status:200,headers:{'content-type':'application/json'}});
    }
    return of(url,opt); };
  return true; })()"""


def stub_convert(ed, mode="ok"):
    """/__convert/toOgg を偽物にする。mode='ok'なら64バイトの偽OGG（先頭OggS）を返す。それ以外の文字列はその文言のエラーを返す"""
    ed.js(_CONVERT_JS.replace("__MODE__", json.dumps(mode)))


def convert_calls(ed):
    return ed.js("window.__conv?window.__conv.calls:[]")


# ---- INFO の出力フォルダ・カバー（書き出しノード o1・カバーノード c1） ----
OUT = "#infoWorld .iGrp[data-out=o1]"
C1 = "#infoWorld .iGrp[data-node=c1]"


def export_click(ed, folder_name=None):
    """INFOの「書き出し」ボタンを押す（folder_name があれば先に出力フォルダ名の欄へ入力）"""
    if folder_name is not None:
        click_sel(ed, f"{OUT} .oName", "フォルダ名の入力欄")
        ed.key("a", ctrl=True)
        type_text(ed, folder_name)
        wait_until(ed, f"window._dbgApp.infoGraph().outs.o1.folderName==={json.dumps(folder_name)}", label="フォルダ名")
    click_sel(ed, "#iExport", "書き出しボタン")


# ---- 環境設定 ----
def open_prefs(ed):
    """メニュー「環境設定」を本物のクリックで開く"""
    click_sel(ed, "#mbSettings", "環境設定メニュー")
    wait_until(ed, "document.getElementById('settingsBg').style.display==='flex'", label="環境設定が開く")


def close_prefs(ed):
    click_sel(ed, "#settingsClose", "環境設定の閉じる")
    wait_until(ed, "document.getElementById('settingsBg').style.display==='none'", label="環境設定が閉じる")


def prefs_tab(ed, tab):
    """タブ（app/vol/preview/cam/keys）を押して切り替え、その画面が出るまで待つ"""
    click_sel(ed, f"#settingsBox .setTab[data-tab={tab}]", f"タブ {tab}")
    wait_until(ed, f"document.querySelector('#settingsBox .setPanel.on')&&document.querySelector('#settingsBox .setPanel.on').dataset.panel==={json.dumps(tab)}",
               label=f"{tab} の画面")


def ls(ed, key):
    """localStorage の値（無ければ None）"""
    return ed.js(f"localStorage.getItem({json.dumps(key)})")


def ls_json(ed, key):
    v = ls(ed, key)
    return json.loads(v) if v else None


def prefs_set_number(ed, range_id, n):
    """スライダー(range_id)の横の数値をダブルクリック→数値を入力→Enter（本物の入力。環境設定の全スライダー共通の手入力）。
    スライダーの値が n になるまで待つ"""
    span_id = ed.js(f"document.getElementById({json.dumps(range_id)}).closest('.slRow').querySelector('.t span[id]').id")
    ed.js(f"document.getElementById({json.dumps(span_id)}).scrollIntoView({{block:'center'}})")
    p = center(ed, f"#{span_id}")
    assert p, f"#{span_id} が表示されていません"
    ed.click(p["x"], p["y"]); ed.click(p["x"], p["y"], count=2)
    wait_until(ed, f"!!document.querySelector('#{span_id} input')", label="数値の入力欄")
    ed.key("a", ctrl=True)
    type_text(ed, str(n))
    ed.key("Enter")
    wait_until(ed, f"+document.getElementById({json.dumps(range_id)}).value==={n}", label=f"{range_id}={n}")


def click_in_view(ed, selector, label=None):
    """要素が画面の外（スクロールの先）にある時はスクロールして見える所へ出してから、本物のクリックで押す"""
    ed.js(f"(()=>{{const e=document.querySelector({json.dumps(selector)}); if(e) e.scrollIntoView({{block:'center'}}); return !!e;}})()")
    return click_sel(ed, selector, label)


def prefs_toggle(ed, checkbox_id):
    """チェックボックスの項目を本物のクリックで切り替える（表示されているタブの中のもの。画面の外ならスクロールする）"""
    click_in_view(ed, f"#{checkbox_id}", f"チェック {checkbox_id}")


def mirror_json(ed):
    """config/settings.json（サーバー側の保存。localStorage のミラー）の中身。
    全グループを並列で回してPCが混むと、開き直しの直後などに通信が中断されること（Failed to fetch）がある＝少し待って読み直す"""
    for i in range(4):
        try:
            return ed.js("fetch('config/settings.json?v='+Date.now(),{cache:'no-store'}).then(r=>r.json())")
        except Exception:
            if i == 3:
                raise
            ed.wait(0.5)


def clean_prefs(ed):
    """環境設定のテスト後始末: localStorage の bsnm_* と サーバー側のミラー(config/settings.json)を「初回起動時＝settings.default.json」の状態に戻す。
    ミラーが変更のまま残ると、次のテストのページ読み込みで settings-mirror.js が localStorage へ流し込んで設定が持ち越される。
    localStorage は Storage の元のメソッドで直接書く（ミラーの予約保存を起こさない＝予約済みの保存が後で走っても同じ内容）"""
    ed.js("""(async()=>{
      const defs=await (await fetch('config/settings.default.json?v='+Date.now(),{cache:'no-store'})).json();
      for(let i=localStorage.length-1;i>=0;i--){ const k=localStorage.key(i); if(k&&k.indexOf('bsnm_')===0) Storage.prototype.removeItem.call(localStorage,k); }
      for(const k in defs) Storage.prototype.setItem.call(localStorage,k,defs[k]);
      await fetch('__settings/save',{method:'POST',headers:{'Content-Type':'application/json','X-NLM-Request':'1'},body:JSON.stringify({data:defs})});
      return true; })()""")


def wait_mirrored(ed, *keys, timeout=6.0):
    """localStorage の bsnm_* の変更が config/settings.json へミラーされる（400msのデバウンス）まで待つ（値が一致するまで）"""
    ks = json.dumps(list(keys))
    wait_until(ed, f"fetch('config/settings.json?v='+Date.now(),{{cache:'no-store'}}).then(r=>r.json()).then(o=>{ks}.every(k=>o[k]===localStorage.getItem(k)))",
               timeout=timeout, label=f"settings.json へのミラー {keys}")


def reload_keep(ed):
    """ページを開き直す（localStorage は消さない＝設定が残るか確かめる用。cdp の既定の reload は消す）"""
    from nlmtest import LIGHT_RENDER_JS
    ed.reload(clear_storage=False)
    ed.js(LIGHT_RENDER_JS)
    wait_until(ed, "!document.getElementById('bootCover')", label="起動中の覆いが外れる")


@contextmanager
def prefs_page(t):
    """環境設定のテスト用: 新しいページを開き、終わったら（失敗しても）設定を初回起動時の状態へ戻す"""
    ed = fresh_page(t)
    try:
        yield ed
    finally:
        try:
            clean_prefs(ed)
        except Exception:
            pass


# ---- 難易度を測る（/__rating/*）のページ内の偽物・記録 ----
_RATING_JS = r"""(()=>{
  const R=window.__rt={calls:[],cfg:__CFG__};
  const of=window.fetch.bind(window);
  window.fetch=async function(url,opt){
    const u=String(url);
    if(u.startsWith('__rating/')){
      const act=u.slice(9); let body=null; try{ body=JSON.parse(opt.body); }catch(_){}
      R.calls.push({act,method:(opt&&opt.method)||'GET',headers:(opt&&opt.headers)||{},body});
      if(R.cfg===null) return of(url,opt);   // 記録だけ（実サーバーへ通す）
      const q=R.cfg[act]; const r=Array.isArray(q)?(q.length>1?q.shift():q[0]):q;
      return new Response(JSON.stringify(r),{status:200,headers:{'content-type':'application/json'}}); }
    return of(url,opt); };
  return true; })()"""

RATING_INSTALLED = {"ok": True, "protocol": 1, "current": "0.1.0", "installed": [{"version": "0.1.0", "compatible": True}],
                    "repo": "https://github.com/example/nlm-rating"}
RATING_NONE = {"ok": True, "protocol": 1, "current": None, "installed": [], "repo": "https://github.com/example/nlm-rating"}


def rating_spy(ed, cfg=None):
    """/__rating/* への fetch を記録する。cfg=None なら実サーバーへ通す（プラグイン未導入の本物の応答）。
    cfg={'status':応答, 'measure':応答または[応答,…], 'install':…, 'check':…} ならサーバーへ行かずその応答を返す（キューは最後を残して消費）"""
    ed.js(_RATING_JS.replace("__CFG__", json.dumps(cfg)))


def rating_calls(ed):
    return ed.js("window.__rt.calls")


def rating_open_via_menu(ed):
    file_menu(ed, "rating")
    wait_until(ed, "(()=>{const p=document.getElementById('rtPanel');return !!p&&p.style.display==='flex'})()", label="難易度を測るパネルが開く")


def rating_text(ed, sel):
    return ed.js(f"(()=>{{const e=document.querySelector('#rtPanel {sel}'); return e?e.textContent:null}})()")

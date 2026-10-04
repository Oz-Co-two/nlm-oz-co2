"""e2e_project グループの共通部品。

- install_fake_fs(ed): showSaveFilePicker / showOpenFilePicker をページ内で偽物にする（アプリ本体は変えない）。
  書かれた中身は window.__fake.writes に溜まり、開く側は window.__fake.openQueue の先頭を返す。
- ダイアログ（未保存の3択）・ファイルメニュー・難易度ボタンのメニューを、画面上の部品を押して操作する小道具。
"""
import json

from e2e_helpers import wait_until

_FAKE_JS = r"""(()=>{
  const F=window.__fake={saveCalls:[],openCalls:[],writes:[],handles:[],saveNames:['a.nlmf','b.nlmf','c.nlmf'],cancelSave:false,cancelOpen:false,openQueue:[]};
  const mk=(name)=>{ const h={kind:'file',name,content:'',
    async getFile(){ return new File([h.content],name); },
    async createWritable(){ let buf=''; return {async write(s){ buf+=s; },async close(){ h.content=buf; F.writes.push({name,text:buf}); }}; },
    async queryPermission(){ return 'granted'; }, async requestPermission(){ return 'granted'; } };
    F.handles.push(h); return h; };
  F.mk=mk;
  window.showSaveFilePicker=async(o)=>{ F.saveCalls.push(JSON.parse(JSON.stringify(o||{})));
    if(F.cancelSave) throw new DOMException('cancel','AbortError');
    return mk(F.saveNames[F.saveCalls.length-1]||('x'+F.saveCalls.length+'.nlmf')); };
  window.showOpenFilePicker=async(o)=>{ F.openCalls.push(JSON.parse(JSON.stringify(o||{})));
    if(F.cancelOpen||!F.openQueue.length) throw new DOMException('cancel','AbortError');
    const it=F.openQueue.shift(); const h=mk(it.name); h.content=it.text; return [h]; };
  return true; })()"""


def install_fake_fs(ed):
    ed.js(_FAKE_JS)


def fake(ed):
    return ed.js("JSON.parse(JSON.stringify({saveCalls:__fake.saveCalls,openCalls:__fake.openCalls,writes:__fake.writes}))")


def queue_open(ed, name, text):
    ed.js(f"__fake.openQueue.push({{name:{json.dumps(name)},text:{json.dumps(text)}}})")


def set_flag(ed, key, val):
    ed.js(f"__fake.{key}={json.dumps(val)}")


def strip_saved_at(text):
    pj = json.loads(text)
    pj.pop("savedAt", None)
    return pj


def toast(ed):
    return ed.js("(()=>{const e=document.getElementById('errToast');return e&&e.style.display!=='none'?e.textContent:''})()")


def forget_errors(ed, needle):
    """意図してエラー表示を出させたテスト用: needle を含む console.error を、以後の t.no_errors() の対象から外す"""
    keep = []
    for e in ed._events:
        p = e.get("params", {})
        if e.get("method") == "Runtime.consoleAPICalled" and p.get("type") == "error" \
                and needle in " ".join(str(a.get("value", a.get("description", ""))) for a in p.get("args", [])):
            continue
        keep.append(e)
    ed._events[:] = keep


# ---- ファイルメニュー ----
def _click_el(ed, sel):
    """CSS セレクタの要素の中心を本物のマウスで押す"""
    p = ed.js(f"(()=>{{const e=document.querySelector({json.dumps(sel)});if(!e)return null;const r=e.getBoundingClientRect();"
              f"return {{x:r.left+r.width/2,y:r.top+r.height/2}}}})()")
    assert p, f"要素が見つかりません: {sel}"
    ed.move(p["x"], p["y"])
    ed.click(p["x"], p["y"])


def file_menu(ed, act):
    """ファイルメニューを開いて data-act=act の項目を押す（new/open/save/saveas/savecopy）"""
    _click_el(ed, "#mFileBtn")
    wait_until(ed, "document.getElementById('mFileMenu').style.display==='block'", label="ファイルメニューが開く")
    _click_el(ed, f"#mFileMenu button[data-act='{act}']")


# ---- 未保存の3択ダイアログ ----
def dialog_open(ed):
    return bool(ed.js("!!document.getElementById('dirtyDlgBg')&&document.getElementById('dirtyDlgBg').style.display!=='none'"))


def wait_dialog(ed):
    wait_until(ed, "!!document.querySelector('#dirtyDlg .ddBtns button')", label="未保存の確認ダイアログ")


def dialog_buttons(ed):
    return ed.js("[...document.querySelectorAll('#dirtyDlg .ddBtns button')].map(b=>b.textContent)")


def dialog_click(ed, idx):
    """0=保存して続行 / 1=保存せずに続行 / 2=キャンセル を本物のクリックで"""
    _click_el(ed, f"#dirtyDlg .ddBtns button:nth-child({idx + 1})")


# ---- 難易度ボタンのメニュー ----
def diff_menu_open(ed, dn):
    """現在選択中の難易度ボタン dn（Hard 等）を押してプルダウンを開く"""
    _click_el(ed, f"#diffBar .dfSeg[data-dn='{dn}']")
    wait_until(ed, "document.getElementById('ctxmenu').style.display==='block'", label="難易度メニュー")


def menu_pick(ed, *labels):
    """開いているメニュー(#ctxmenu)から、ラベルが一致（無ければ前方一致）する項目を順に押す（サブメニューも同じ方法）。
    最後の項目を押すと実行される"""
    for lab in labels:
        wait_until(ed, f"[...document.querySelectorAll('#ctxmenu button')].some(b=>b.textContent.startsWith({json.dumps(lab)}))",
                   label=f"メニュー項目 {lab}")
        # 完全一致の項目を優先（'→ Expert' が '→ Expert+' に化けない）。無ければ前方一致。サブメニューは後ろに追加されるので後ろを優先。本物のクリックで押す
        p = ed.js(f"(()=>{{const L={json.dumps(lab)};const all=[...document.querySelectorAll('#ctxmenu button')];"
                  f"const ex=all.filter(b=>b.textContent===L);const bs=ex.length?ex:all.filter(b=>b.textContent.startsWith(L));"
                  f"const r=bs[bs.length-1].getBoundingClientRect();return {{x:r.left+r.width/2,y:r.top+r.height/2}}}})()")
        ed.move(p["x"], p["y"])
        ed.click(p["x"], p["y"])
        ed.wait(0.05)


def diff_totals(ed):
    """難易度ごとの数（保存内容から）。{'Hard': {...}, 'Expert': {...}} ではなく 名前.dat をキーに"""
    from e2e_helpers import project, diff_counts_from_project
    return diff_counts_from_project(project(ed))


def diff_flat(ed, dat):
    """保存内容の難易度 dat（例 'HardStandard.dat'）の平らな配列（ノーツ等の符号化されたリスト）"""
    from e2e_helpers import project
    for st in project(ed)["difficulties"].values():
        if st["name"] == dat:
            return {k: st.get(k) for k in ("notes", "bombs", "walls", "arcs", "chains", "lightEvents")}
    return None

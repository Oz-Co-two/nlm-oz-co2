"""カバー画像の入ったプロジェクトを開いた後に、別のプロジェクトを開く・新規にする（2026-10-27・利用者の報告）。
カバー画像の控え（画像の参照 _coverHandles・同梱の画像・INFO の見本・右下の表示）はカバーノードの id（既定は c1）で持つ。
以前は開く/新規で控えを消しておらず、①カバーの無いプロジェクト・新規・画像を戻せないプロジェクトで前の画像が INFO・右下の表示・
譜面チェック・書き出しに使われ、保存するとその画像がプロジェクトに入った。②前のプロジェクトの右下の表示の画像の読み込みが後から終わり、
開いたプロジェクトの右下に前の画像が残った（exe 版で、開いてすぐ次を開いた時）。

画像は canvas で作る（A=300×300 赤・B=400×400 緑 どちらも cover.png・B2=500×500 青 b.png）。どの画像かは大きさと色で見分ける。
開く・新規・保存・書き出しは本物のクリック（ファイル・フォルダの選択だけページ内で偽物）。exe 版の経路は偽の pywebview（e2e_misc の misc_helpers）。"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "e2e_misc"))
from misc_helpers import install_fake_pywebview, native_add_png, native_queue, native_state   # noqa: E402  e2e_info も読み込み先に足す
from info_helpers import click_sel, to_info, type_text   # noqa: E402
from e2e_helpers import open_fixture, wait_until   # noqa: E402
from project_helpers import dialog_click, file_menu, install_fake_fs, queue_open   # noqa: E402

RICH_TEXT = (Path(__file__).resolve().parents[2] / "tools" / "fixtures" / "rich.nlmf").read_text(encoding="utf-8")   # カバーの無いプロジェクト（c1 は空）
C1 = "#infoWorld .iGrp[data-node=c1]"
OUT = "#infoWorld .iGrp[data-out=o1]"
PA = "C:\\NLMTest\\A\\cover.png"
PB = "C:\\NLMTest\\B\\cover.png"
PB2 = "C:\\NLMTest\\B2\\b.png"
IMGS = {"A": (300, "#ff0000", "cover.png", PA), "B": (400, "#00ff00", "cover.png", PB), "B2": (500, "#0000ff", "b.png", PB2)}
TAG = {"A": "300x300R", "B": "400x400G", "B2": "500x500B"}

# 「開く」（プロジェクト・project_helpers の偽物）と「画像を選択」「出力フォルダを選択」を1つのページで使う偽物。
# 画像の見分け（__tag）: 大きさと中央の色（R/G/B）
_PAGE_JS = r"""(()=>{
  window.__fsw={};
  const mkDir=path=>({kind:'directory',name:path.split('/').pop(),
    async getDirectoryHandle(n){ return mkDir(path+'/'+n); },
    async getFileHandle(n,o){ const p=path+'/'+n;
      if(!(o&&o.create)&&!window.__fsw[p]) throw new DOMException('not found','NotFoundError');
      return {kind:'file',name:n,async getFile(){ return window.__fsw[p]; },
        async createWritable(){ const ch=[]; return {async write(d){ ch.push(d); },async close(){ window.__fsw[p]=new Blob(ch); }}; }}; }});
  window.showDirectoryPicker=async()=>mkDir('CustomLevels');
  const openProj=window.showOpenFilePicker;
  window.showOpenFilePicker=async(o)=>{ const f=window.__pickImage; if(!f) return openProj(o);
    window.__pickImage=null; return [{kind:'file',name:f.name,async getFile(){ return f; }}]; };
  window.__mkPng=async(w,col,name)=>{ const cv=document.createElement('canvas'); cv.width=w; cv.height=w; const g=cv.getContext('2d');
    g.fillStyle=col; g.fillRect(0,0,w,w); const b=await new Promise(r=>cv.toBlob(r,'image/png')); return new File([b],name,{type:'image/png'}); };
  window.__tag=async(src)=>{ if(!src) return null;
    try{ const b=src instanceof Blob?src:await (await fetch(src)).blob(); const bmp=await createImageBitmap(b);
      const cv=document.createElement('canvas'); cv.width=bmp.width; cv.height=bmp.height; const g=cv.getContext('2d'); g.drawImage(bmp,0,0);
      const d=[...g.getImageData(bmp.width>>1,bmp.height>>1,1,1).data].slice(0,3), m=Math.max(...d), r=bmp.width+'x'+bmp.height+(m<128?'?':'RGB'[d.indexOf(m)]);
      bmp.close(); return r; }catch(e){ return 'err'; } };
  return true; })()"""

# 画面に出ている物（INFO のカードの見本・名前、右下の表示）。右下は先に読む（譜面チェックの入力を作ると applyInfoGraph で読み直すため）
_SHOWN_JS = r"""(async()=>{
  const card=document.querySelector('#infoWorld .iGrp[data-node=c1]'), th=card.querySelector('.nThumb'), si=document.getElementById('siCover');
  return {jacket:(si.style.display!=='none'&&si.getAttribute('src'))?await __tag(si.src):'none',
    card:th.style.display==='block'?await __tag(th.src):'none', name:card.querySelector('.nCovName').textContent}; })()"""


def _page(ed):
    install_fake_fs(ed)
    ed.js(_PAGE_JS)


def _shown(ed):
    return ed.js(_SHOWN_JS)


def _mapcheck(ed):
    """譜面チェックが見るカバー（書き出しと同じ計算の寸法）。無ければ None"""
    c = ed.js("(async()=>(await window._dbgApp.mapCheckInput()).cover||null)()")
    return f"{c['w']}x{c['h']}" if c else None


def _wait_shown(ed, want, label):
    """右下の表示・カードの見本が want（{'jacket':…, 'card':…}）になるのを待ち、右下の表示が決め直される間（0.5秒ごと）より長く待っても変わらないこと"""
    js = f"(async()=>{{ const s=await ({_SHOWN_JS}); const w={json.dumps(want)}; return Object.keys(w).every(k=>s[k]===w[k])?s:null; }})()"
    try:
        wait_until(ed, js, timeout=10, label=label)
    except AssertionError:
        pass   # 違ったままなら下の比較で中身を出す
    ed.wait(1.2)
    return _shown(ed)


def _pick(ed, key):
    """カバーノード（c1）の「画像を選択…」を本物のクリックで押し、key の画像を選ぶ（ブラウザ版の選択）"""
    w, col, name, _p = IMGS[key]
    ed.js(f"(async()=>{{ window.__pickImage=await __mkPng({w},{json.dumps(col)},{json.dumps(name)}); return true; }})()")
    click_sel(ed, f"{C1} .nPick", "カバーの「画像を選択」")
    wait_until(ed, f"(async()=>await __tag(await window._dbg.rt._coverHandles.c1.getFile())==={json.dumps(TAG[key])})()", label=f"カバー {key}")


def _pick_native(ed, key):
    """exe 版の「画像を選択…」（ネイティブのダイアログ＝実パス）"""
    native_queue(ed, "image", IMGS[key][3])
    click_sel(ed, f"{C1} .nPick", "カバーの「画像を選択」")
    wait_until(ed, f"window._dbgApp.infoGraph().nodes.c1.data.nativePath==={json.dumps(IMGS[key][3])}", label=f"カバー {key}（実パス）")


def _snapshot(ed):
    """今のプロジェクトの保存内容（保存と同じく、カバー画像を同梱してから）"""
    ed.js("window._dbg.rt.refreshCoverB64()")
    return ed.js("window._dbg.rt.buildProjectText()")


_CACHE = {}


def _projects(t):
    """カバー A・B・B2 の入ったプロジェクト（ブラウザ版で選んだ物と exe 版で選んだ物）と、exe 版の偽の PC の状態。1つのページで作って覚えておく"""
    if "v" not in _CACHE:
        ed = open_fixture(t, "rich")
        _page(ed)
        to_info(ed)
        out = {}
        for k in ("A", "B", "B2"):
            _pick(ed, k)
            out[k] = _snapshot(ed)
        install_fake_pywebview(ed)
        for k in ("A", "B", "B2"):
            w, col, _n, path = IMGS[k]
            native_add_png(ed, path, w, w, (col, col))
        for k in ("A", "B", "B2"):
            _pick_native(ed, k)
            out["n" + k] = _snapshot(ed)
        _CACHE["v"] = (out, native_state(ed))
    out, state = _CACHE["v"]
    return dict(out), json.loads(json.dumps(state))


def _open(ed, name, text):
    """ファイルメニューの「開く…」を本物のクリックで押してプロジェクトを開く（ファイル選択は偽物）。開き終わるまで待つ"""
    queue_open(ed, name, text)
    ed.js("document.getElementById('errToast').textContent=''")
    file_menu(ed, "open")
    if wait_until(ed, "document.getElementById('errToast').textContent.includes('プロジェクトを開きました')?'opened'"
                      ":(document.querySelector('#dirtyDlg .ddBtns button')?'ask':'')", label=f"{name} を開く") == "ask":
        dialog_click(ed, 1)   # 書き出しの設定で未保存になっている時の3択＝「保存せずに続行」
        wait_until(ed, "document.getElementById('errToast').textContent.includes('プロジェクトを開きました')", label=f"{name} を開く")


def _save(ed):
    """ファイルメニューの「保存」（開いたファイルへ上書き）。書かれた中身の同梱のカバー画像を {id: 見分け} で返す"""
    n = ed.js("__fake.writes.length")
    file_menu(ed, "save")
    wait_until(ed, f"__fake.writes.length>{n}", label="保存の書き込み")
    text = ed.js("__fake.writes[__fake.writes.length-1].text")
    pj = json.loads(text)
    return text, ed.js(f"(async()=>{{ const d={json.dumps(pj.get('coverData') or {})}, o={{}}; for(const k in d) o[k]=await __tag(d[k]); return o; }})()")


def _export(ed, folder):
    """INFO で出力フォルダ（偽物）を選び、フォルダ名を入れて書き出す。(書いた cover の見分け, Info.dat のカバー名)"""
    to_info(ed)
    click_sel(ed, f"{OUT} .oPick", "出力フォルダを選択")
    wait_until(ed, "window._dbgApp.infoGraph().outs.o1.outDirName==='CustomLevels'", label="出力フォルダ")
    click_sel(ed, f"{OUT} .oName", "フォルダ名の入力欄")
    ed.key("a", ctrl=True)
    type_text(ed, folder)
    wait_until(ed, f"window._dbgApp.infoGraph().outs.o1.folderName==={json.dumps(folder)}", label="フォルダ名")
    ed.js("window._dbg.rt.exportMap()")   # 「書き出し」ボタンは音源が要る（開いただけでは音源が無い）ので書き出しの処理を直接呼ぶ
    wait_until(ed, f"!!window.__fsw['CustomLevels/{folder}/Info.dat']", timeout=15, label="Info.dat の書き出し")
    ed.wait(0.3)
    cov = ed.js(f"""(async()=>{{ const ks=Object.keys(window.__fsw).filter(k=>k.startsWith('CustomLevels/{folder}/cover.'));
      const o={{}}; for(const k of ks) o[k.split('/').pop()]=await __tag(window.__fsw[k]); return o; }})()""")
    info = json.loads(ed.js(f"window.__fsw['CustomLevels/{folder}/Info.dat'].text()"))
    return cov, info.get("_coverImageFilename", "")


def _fresh(t, state=None):
    ed = t.fresh()
    wait_until(ed, "!document.getElementById('bootCover')", label="起動中の覆いが外れる")
    if state is not None:
        install_fake_pywebview(ed, state=state)
    _page(ed)
    return ed


def _check(t, ed, key, label):
    """開いているプロジェクトのカバーが key（None＝カバー無し）の画像になっていること: INFO・右下の表示・譜面チェック"""
    want = {"jacket": TAG[key] if key else "none", "card": TAG[key] if key else "none"}
    s = _wait_shown(ed, want, f"{label}: 表示")
    t.eq({"jacket": s["jacket"], "card": s["card"]}, want, f"{label}: 右下の表示・INFO の見本")
    t.eq(s["name"], IMGS[key][2] if key else "（未選択）", f"{label}: INFO のファイル名")
    t.eq(_mapcheck(ed), TAG[key][:-1] if key else None, f"{label}: 譜面チェックが見るカバー")


# ---------------------------------------------------------------- ブラウザ版の経路
def test_cover_reopen_other_cover(t):
    '''A を開いてから B（同じ名前 cover.png）・B2（別の名前）を開く: どれも開いたプロジェクトの画像。書き出し・保存も。B を保存して開き直しても B'''
    pj, _ = _projects(t)
    ed = _fresh(t)
    _open(ed, "a.nlmf", pj["A"])
    _check(t, ed, "A", "A を開いた")
    _open(ed, "b.nlmf", pj["B"])
    _check(t, ed, "B", "A→B（同じ名前）")
    text, saved = _save(ed)
    t.eq(saved, {"c1": TAG["B"]}, "保存した B に同梱の画像")
    t.eq(_export(ed, "cvB"), ({"cover.png": TAG["B"]}, "cover.png"), "書き出した cover・Info.dat のカバー名")
    _open(ed, "b2.nlmf", pj["B2"])
    _check(t, ed, "B2", "B→B2（別の名前）")
    ed = _fresh(t)
    _open(ed, "b.nlmf", text)
    _check(t, ed, "B", "保存した B を開き直す")
    t.no_errors()


def test_cover_reopen_no_cover(t):
    '''A を開いてからカバーの無いプロジェクト（C）を開く: 画像は無し（以前は A の画像が INFO・右下・譜面チェック・書き出しに使われ、保存すると C に A の画像が入った）'''
    pj, _ = _projects(t)
    ed = _fresh(t)
    _open(ed, "a.nlmf", pj["A"])
    _check(t, ed, "A", "A を開いた")
    _open(ed, "c.nlmf", RICH_TEXT)
    _check(t, ed, None, "A→C")
    t.eq(_save(ed)[1], {}, "保存した C に画像を入れない")
    t.eq(_export(ed, "cvC"), ({}, ""), "書き出しにカバーを書かない")
    t.no_errors()


def test_cover_new_after_cover(t):
    '''A を開いてから新規: 画像は無し（以前は A の画像が残った）。その後 B を開くと B'''
    pj, _ = _projects(t)
    ed = _fresh(t)
    _open(ed, "a.nlmf", pj["A"])
    _check(t, ed, "A", "A を開いた")
    file_menu(ed, "new")
    wait_until(ed, "document.getElementById('errToast').textContent.includes('新規プロジェクトを作成しました')", label="新規")
    want = {"jacket": "none", "card": "none"}
    s = _wait_shown(ed, want, "新規: 表示")
    t.eq({"jacket": s["jacket"], "card": s["card"]}, want, "新規: 右下の表示・INFO の見本")
    t.eq(ed.js("(async()=>{ await window._dbg.rt.refreshCoverB64(); return JSON.parse(window._dbg.rt.buildProjectText()).coverData; })()"), {},
         "新規の保存内容に画像を入れない")
    t.eq(ed.js("Object.keys(window._dbg.rt._coverHandles)"), [], "画像の参照も残らない")
    _open(ed, "b.nlmf", pj["B"])
    _check(t, ed, "B", "新規→B")
    t.no_errors()


def test_cover_reopen_unrestorable(t):
    '''A を開いてから、画像を戻せない B（同梱の画像が無い・実パスも無い＝古いファイル等）を開く: 名前だけで画像は無し・「再接続」で選び直すと B の画像。
    以前は同じ id の A の画像が使われ、保存すると B に A の画像が入った'''
    pj, _ = _projects(t)
    b = json.loads(pj["B"])
    b["coverData"] = {}
    ed = _fresh(t)
    _open(ed, "a.nlmf", pj["A"])
    _check(t, ed, "A", "A を開いた")
    _open(ed, "b.nlmf", json.dumps(b, ensure_ascii=False))
    want = {"jacket": "none", "card": "none"}
    s = _wait_shown(ed, want, "画像の無い B: 表示")
    t.eq({"jacket": s["jacket"], "card": s["card"]}, want, "画像の無い B: 右下の表示・INFO の見本")
    t.eq(s["name"], "cover.png", "名前は B の物")
    t.eq(_mapcheck(ed), None, "譜面チェックにカバーは無い")
    t.eq(_save(ed)[1], {}, "保存した B に A の画像を入れない")
    to_info(ed)
    t.eq(ed.js(f"document.querySelector('{OUT} .oReconnect').style.display"), "", "「再接続」ボタンが出る")
    w, col, name, _p = IMGS["B"]
    ed.js(f"(async()=>{{ window.__pickImage=await __mkPng({w},{json.dumps(col)},{json.dumps(name)}); return true; }})()")
    click_sel(ed, f"{OUT} .oReconnect", "再接続")   # 出力フォルダ（偽物）→ カバー画像の順に選び直す（ブラウザ版はカバーがあれば「再接続」は出たまま）
    wait_until(ed, "document.getElementById('stat').textContent.includes('書き出し設定を再接続しました')", label="再接続の完了")
    _check(t, ed, "B", "再接続した B")
    t.no_errors()


def test_cover_reopen_fit(t):
    '''カバーの補正（fit）はプロジェクトごと: 補正ありの A→補正なしの B は B の画像のまま、補正なしの B→補正ありの A は A を補正した寸法'''
    pj, _ = _projects(t)
    a = json.loads(pj["A"])
    a["infoGraph"]["nodes"]["c1"]["data"]["fit"] = {"mode": "pad", "bg": "#000000"}   # 300×300 の png は基準を満たすので、補正が効くよう A を横長にする
    ed = _fresh(t)
    a["coverData"]["c1"] = ed.js("""(async()=>{ const cv=document.createElement('canvas'); cv.width=300; cv.height=200; const g=cv.getContext('2d');
      g.fillStyle='#ff0000'; g.fillRect(0,0,300,200); return cv.toDataURL('image/png'); })()""")
    afit = json.dumps(a, ensure_ascii=False)
    _open(ed, "afit.nlmf", afit)
    t.eq(_mapcheck(ed), "300x300", "補正ありの A（300×200 を余白で 300×300 へ）")
    t.eq(ed.js("window._dbgApp.coverFit().fit"), {"mode": "pad", "bg": "#000000"}, "A の補正の設定")
    _open(ed, "b.nlmf", pj["B"])
    _check(t, ed, "B", "補正ありの A→B")
    t.eq(ed.js("window._dbgApp.coverFit().fit"), None, "B に補正の設定は無い")
    t.eq(_export(ed, "cvFit"), ({"cover.png": TAG["B"]}, "cover.png"), "B は元の画像のまま書き出す")
    _open(ed, "afit.nlmf", afit)
    t.eq(_mapcheck(ed), "300x300", "B→補正ありの A")
    t.eq(ed.js("window._dbgApp.coverFit().fit"), {"mode": "pad", "bg": "#000000"}, "A の補正の設定")
    t.no_errors()


# ---------------------------------------------------------------- exe 版の経路（実パスの自動の接続）
_SLOW_MS = 3000


def _slow_a(ed):
    """A の画像（実パス）の読み込みだけを遅くする（大きな画像を pywebview 越しに読む時の代わり）。読み始めた数を __slowStart・読み終わった数を __slowDone に数える"""
    ed.js(f"""(()=>{{ const api=window.pywebview.api, of=api.read_song_file; window.__slowStart=0; window.__slowDone=0;
      api.read_song_file=async(p)=>{{ if(String(p).toLowerCase()==={json.dumps(PA.lower())}){{ window.__slowStart++;
          await new Promise(r=>setTimeout(r,{_SLOW_MS})); const j=await of(p); window.__slowDone++; return j; }}
        return of(p); }}; return true; }})()""")


def _open_a_then(t, nxt_name, nxt_text, key):
    """exe 版: A を開き、右下の表示が A の画像を読んでいる途中（遅い）で次のプロジェクトを開く。A の読み込みが全部終わってから確かめる"""
    pj, state = _projects(t)
    ed = _fresh(t, state)
    _slow_a(ed)
    _open(ed, "a.nlmf", pj["nA"])   # 開く時の自動の接続で A を1回読む（INFO の見本）。2回目が右下の表示
    wait_until(ed, "window.__slowStart>=2", label="右下の表示が A の画像を読み始める")
    _open(ed, nxt_name, nxt_text)
    wait_until(ed, "window.__slowDone>=window.__slowStart", timeout=_SLOW_MS / 1000 + 10, label="A の読み込みが全部終わる")
    _check(t, ed, key, f"A→{nxt_name}")
    t.no_errors()


def test_cover_reopen_native_slow_same_name(t):
    '''exe 版（利用者の報告の形）: A を開いてすぐ B（同じ名前 cover.png・別の場所）を開く。右下の表示が後から終わった A の読み込みで A に戻らない'''
    pj, _ = _projects(t)
    _open_a_then(t, "b.nlmf", pj["nB"], "B")


def test_cover_reopen_native_slow_other_name(t):
    '''exe 版: A を開いてすぐ B2（別の名前 b.png）を開く。同じく B2 のまま'''
    pj, _ = _projects(t)
    _open_a_then(t, "b2.nlmf", pj["nB2"], "B2")


def test_cover_reopen_native_slow_no_cover(t):
    '''exe 版: A を開いてすぐカバーの無いプロジェクトを開く。右下の表示に A が出ない'''
    _open_a_then(t, "c.nlmf", RICH_TEXT, None)

"""書き出し先のフォルダ（出力フォルダ）を選んだプロジェクトを開いた後に、別のプロジェクトを開く・新規にする（2026-10-27）。
書き出し先の参照（outDirHandle・書き出しノードごとの控え _outHandles）はセッション中だけの物で、以前は開く/新規で消しておらず、
前のプロジェクトのフォルダが残った: カードは開いたプロジェクトの記録（空・別のフォルダ）なのに「CustomLevelsフォルダ」が準備済みのまま・
「再接続」も出ず、書き出しと審査の指摘の .txt の保存が前のプロジェクトのフォルダへ行った（exe 版で、開いたプロジェクトの実パスが
このPCで未許可・記録が無い時。新規も）。開いてすぐ次を開くと、前のプロジェクトの自動の接続（tryAutoRestoreNativeInputs）が後から終わり、
控えに前のフォルダを入れていた（カードを押すと書き出し先がそれに替わった）。
今は開く・新規で消し、開いたプロジェクトの記録がこのPCで許可済みなら自動で繋ぎ、そうでなければ「再接続」（表示と書き出し先を一致させる）。
保存しただけ・Undo・アクティブな書き出しノードの切り替えでは繋がったまま。

開く・新規・保存・書き出し・カードを押すのは本物のクリック（ファイル・フォルダの選択だけページ内で偽物）。exe 版の経路は偽の pywebview（e2e_misc の misc_helpers）。"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "e2e_misc"))
from misc_helpers import (OUT_BASE, SONG_PATH, install_fake_pywebview, native_add_file_from_url, native_queue,   # noqa: E402  e2e_info も読み込み先に足す
                          native_reset_calls, native_state, native_writes, stub_convert)
from info_helpers import click_sel, click_text, free_spot, reveal, select_node, to_info, type_text, undo   # noqa: E402
from e2e_helpers import _CAPTURE_JS, open_fixture, wait_until   # noqa: E402
from project_helpers import dialog_click, file_menu, forget_errors, install_fake_fs, queue_open, toast   # noqa: E402
from review_helpers import rv_import   # noqa: E402

OUT = "#infoWorld .iGrp[data-out=o1]"
PA = OUT_BASE                       # A の出力フォルダ（C:\NLMTest\CustomLevels）
PB = "D:\\BeatSaber\\CustomLevels"  # B の出力フォルダ（同じ名前・別の場所＝カードの名前だけでは見分けられない）
NONE_CARD = {"pick": "📁 出力フォルダを選択", "ready": False, "reconnect": True}   # 記録が無い＝未接続
RECON_CARD = {"pick": "📂 CustomLevels", "ready": False, "reconnect": True}       # 記録はあるが繋がっていない＝「再接続」
OK_CARD = {"pick": "📂 CustomLevels", "ready": True, "reconnect": False}          # 繋がっている

# 書き出しノードのカード: フォルダのボタンの文字・準備の「CustomLevelsフォルダ」が ✓ か・「再接続」が出ているか
_CARD_JS = """(oid=>{ const el=document.querySelector(`#infoWorld .iGrp[data-out="${oid}"]`); if(!el) return null;
  const row=[...el.querySelectorAll('.oChk > div')].find(d=>d.textContent.includes('CustomLevelsフォルダ'));
  return {pick:el.querySelector('.oPick').textContent, ready:!!row&&row.textContent.trim().startsWith('✓'),
    reconnect:el.querySelector('.oReconnect').style.display!=='none'}; })"""

# ブラウザ版の出力フォルダの選択（偽物）。書いた物は window.__fsw['CustomLevels/<…>']
_DIR_JS = r"""(()=>{
  window.__fsw={};
  const mkDir=path=>({kind:'directory',name:path.split('/').pop(),
    async getDirectoryHandle(n){ return mkDir(path+'/'+n); },
    async getFileHandle(n,o){ const p=path+'/'+n;
      if(!(o&&o.create)&&!window.__fsw[p]) throw new DOMException('not found','NotFoundError');
      return {kind:'file',name:n,async getFile(){ return window.__fsw[p]; },
        async createWritable(){ const ch=[]; return {async write(d){ ch.push(d); },async close(){ window.__fsw[p]=new Blob(ch); }}; }}; }});
  window.showDirectoryPicker=async()=>mkDir('CustomLevels');
  return true; })()"""


def _click_shown(ed, sel, label):
    """書き出しノード o1 のカードの中の部品を本物のマウスで押す。開き直すと INFO の表示の位置が変わり、カードが表示の枠の外
    （3Dビューの下）に出ることがある＝先にカードを枠の中へずらす（info_helpers.reveal）"""
    to_info(ed)
    reveal(ed, "out:o1")
    click_sel(ed, sel, label)


def _card(ed, oid="o1"):
    """書き出しノードのカード（表示は 0.4 秒ごとに描き直される＝待ってから読む）"""
    to_info(ed)
    ed.wait(0.5)
    return ed.js(f"({_CARD_JS})({json.dumps(oid)})")


def _press_card(ed, oid="o1"):
    """書き出しノードのカードの見出しを押す（アクティブの書き出しノードを押す＝控えの参照を書き出し先へ写し直す setActiveOut）"""
    to_info(ed)
    select_node(ed, f"out:{oid}")
    return _card(ed, oid)


def _set_folder(ed, name):
    _click_shown(ed, f"{OUT} .oName", "フォルダ名の入力欄")
    ed.key("a", ctrl=True)
    type_text(ed, name)
    wait_until(ed, f"window._dbgApp.infoGraph().outs.o1.folderName==={json.dumps(name)}", label=f"フォルダ名 {name}")


def _with_out(text, folder, path):
    """プロジェクト text の書き出しノード o1 の記録を、フォルダ名 folder・出力フォルダ path（''＝記録なし）に替えた物"""
    pj = json.loads(text)
    name = path.rsplit("\\", 1)[-1] if path else ""
    for o in (pj["infoGraph"]["outs"]["o1"], pj["graph"]["out"]):
        o.update(folderName=folder, outDirName=name, outDirPath=path)
    return json.dumps(pj, ensure_ascii=False)


def _open(ed, name, text):
    """ファイルメニューの「開く…」を本物のクリックで押してプロジェクトを開く（ファイル選択は偽物）。開き終わるまで待つ"""
    queue_open(ed, name, text)
    ed.js("document.getElementById('errToast').textContent=''")
    file_menu(ed, "open")
    done = f"document.getElementById('errToast').textContent.includes('プロジェクトを開きました: {name}')"
    if wait_until(ed, f"{done}?'opened':(document.querySelector('#dirtyDlg .ddBtns button')?'ask':'')", label=f"{name} を開く") == "ask":
        dialog_click(ed, 1)   # 未保存の3択＝「保存せずに続行」
        wait_until(ed, done, label=f"{name} を開く")


def _new(ed):
    ed.js("document.getElementById('errToast').textContent=''")
    file_menu(ed, "new")
    if wait_until(ed, "document.getElementById('errToast').textContent.includes('新規プロジェクトを作成しました')?'new'"
                      ":(document.querySelector('#dirtyDlg .ddBtns button')?'ask':'')", label="新規") == "ask":
        dialog_click(ed, 1)
        wait_until(ed, "document.getElementById('errToast').textContent.includes('新規プロジェクトを作成しました')", label="新規")


def _review_save(ed):
    """審査の指摘を読み込み、書き出しの画面の［出力フォルダへ保存］を押す（審査の指摘の .txt の保存先）。{知らせ, exe 版で書いたファイル, ブラウザ版で書いたファイル, ダウンロード}"""
    ed.js(_CAPTURE_JS)
    ed.js("window.__nlmCap.files=[]; if(window.__fsw) for(const k in window.__fsw) delete window.__fsw[k]; true")
    if ed.js("!!window.__nat"):
        native_reset_calls(ed)
    rv_import(ed, [("Mod.txt", "Expert\n4 - first")])
    ed.js("document.querySelector('#rvPanel .rvExport').click(); true")
    wait_until(ed, "!!document.querySelector('#dirtyDlg[data-rv=rvExportDlg]')", label="書き出しの画面")
    ed.js("(()=>{ const i=document.querySelector('#dirtyDlg input[name=rvXKind][value=reply]'); i.checked=true; i.dispatchEvent(new Event('change',{bubbles:true})); return 1; })()")
    wait_until(ed, "document.querySelector('#dirtyDlg .rvXPre').value.length>0", label="返事の文")
    click_text(ed, "#dirtyDlg .ddBtns button", "出力フォルダへ保存")
    wait_until(ed, "/保存しました|ダウンロードしました|保存できません/.test(document.querySelector('#dirtyDlg .rvXStatus').textContent)", label="保存")
    r = {"status": ed.js("document.querySelector('#dirtyDlg .rvXStatus').textContent"),
         "native": sorted(native_writes(ed)) if ed.js("!!window.__nat") else [],
         "fsw": ed.js("Object.keys(window.__fsw||{}).sort()"),
         "download": ed.js("window.__nlmCap.files.map(f=>f.name)")}
    click_text(ed, "#dirtyDlg .ddBtns button", "閉じる")
    wait_until(ed, "!document.querySelector('#dirtyDlg[data-rv=rvExportDlg]')", label="書き出しの画面を閉じる")
    ed.js("window._dbg.rt.reviewPanel.close&&window._dbg.rt.reviewPanel.close(); true")
    return r


# ---------------------------------------------------------------- ブラウザ版（python serve.py）
_CACHE = {}


def _browser_a(t):
    """ブラウザ版: 出力フォルダ（偽物の CustomLevels）を選び、フォルダ名 outA を入れたプロジェクト A の保存内容。1つのページで作って覚えておく"""
    if "b" not in _CACHE:
        ed = open_fixture(t, "rich")
        ed.js(_DIR_JS)
        to_info(ed)
        click_sel(ed, f"{OUT} .oPick", "出力フォルダを選択")
        wait_until(ed, "window._dbgApp.infoGraph().outs.o1.outDirName==='CustomLevels'", label="出力フォルダ")
        _set_folder(ed, "outA")
        _CACHE["b"] = ed.js("window._dbg.rt.buildProjectText()")
    return _CACHE["b"]


def _fresh_browser(t):
    ed = t.fresh()
    wait_until(ed, "!document.getElementById('bootCover')", label="起動中の覆いが外れる")
    install_fake_fs(ed)
    ed.js(_DIR_JS)
    return ed


def _export_browser(ed):
    """書き出しの処理（ブラウザ版は音源が戻らないので「書き出し」ボタンは使えない＝処理を直接呼ぶ）。{書いたフォルダ, ダウンロードした数}"""
    ed.js(_CAPTURE_JS)
    ed.js("window.__nlmCap.files=[]; for(const k in window.__fsw) delete window.__fsw[k]; true")
    ed.js("(async()=>{ await window._dbg.rt.exportMap(); return 1; })()")
    ed.wait(0.3)
    return {"wrote": sorted({k.rsplit("/", 1)[0] for k in ed.js("Object.keys(window.__fsw)")}),
            "download": len(ed.js("window.__nlmCap.files"))}


def _reconnect_browser(ed):
    _click_shown(ed, f"{OUT} .oReconnect", "再接続")
    wait_until(ed, "document.getElementById('stat').textContent.includes('書き出し設定を再接続しました')", label="再接続の完了")


def test_outdir_reopen_browser(t):
    '''ブラウザ版: A（出力フォルダを選んだ）→ B（記録なし）: B は未接続（以前は A のフォルダが準備済みのまま・「再接続」も出ず、書き出し・審査の指摘の .txt が A のフォルダへ）。
    B→A: ブラウザ版は開き直すと「再接続」（参照はセッション限定）'''
    a = _browser_a(t)
    b = _with_out(a, "outB", "")
    ed = _fresh_browser(t)
    _open(ed, "a.nlmf", a)
    t.eq(_card(ed), RECON_CARD, "A を開いた（ブラウザ版は参照を覚えていない＝再接続）")
    _reconnect_browser(ed)
    t.eq(_card(ed), OK_CARD, "再接続した A")
    t.eq(_export_browser(ed), {"wrote": ["CustomLevels/outA"], "download": 0}, "A は選んだフォルダへ書き出す")
    _open(ed, "b.nlmf", b)
    t.eq(_card(ed), NONE_CARD, "A→B（フォルダの記録なし）: 未接続・「再接続」が出る")
    t.eq(_press_card(ed), NONE_CARD, "カードを押しても未接続のまま")
    got = _export_browser(ed)
    t.eq(got["wrote"], [], "B の書き出しは A のフォルダへ行かない")
    t.ok(got["download"] > 0, f"ダウンロードで書き出す: {got}")
    rv = _review_save(ed)
    t.eq((rv["fsw"], rv["download"]), ([], ["outB_Mod_reply.txt"]), f"審査の指摘の .txt も A のフォルダへ行かない（ダウンロード）: {rv['status']}")
    _open(ed, "a.nlmf", a)
    t.eq(_card(ed), RECON_CARD, "B→A（ブラウザ版は開き直すと再接続）")
    t.no_errors()


def test_outdir_new_browser(t):
    '''ブラウザ版: A（繋がっている）→ 新規: 未接続（以前は A のフォルダが準備済みのまま・審査の指摘の .txt が A のフォルダへ）。選び直せば繋がる'''
    a = _browser_a(t)
    ed = _fresh_browser(t)
    _open(ed, "a.nlmf", a)
    _reconnect_browser(ed)
    t.eq(_card(ed), OK_CARD, "再接続した A")
    _new(ed)
    t.eq(_card(ed), NONE_CARD, "新規: 未接続・「再接続」が出る")
    rv = _review_save(ed)
    t.eq(rv["fsw"], [], f"審査の指摘の .txt は A のフォルダへ行かない: {rv['status']}")
    t.eq(len(rv["download"]), 1, "ダウンロード")
    _click_shown(ed, f"{OUT} .oPick", "出力フォルダを選択")
    wait_until(ed, "window._dbgApp.infoGraph().outs.o1.outDirName==='CustomLevels'", label="出力フォルダ")
    t.eq(_card(ed), OK_CARD, "新規で選び直すと繋がる")
    t.no_errors()


# ---------------------------------------------------------------- exe 版（実パス・許可済みの出力フォルダへの自動の接続）
def _native_a(t):
    """exe 版: 曲（実パス＝開くと音源も戻る）・出力フォルダ PA（このPCで選んだ＝許可済み）・フォルダ名 outA のプロジェクト A と、偽の PC の状態"""
    if "n" not in _CACHE:
        ed = open_fixture(t, "rich")
        wait_until(ed, "!document.getElementById('bootCover')", label="起動中の覆いが外れる")
        install_fake_pywebview(ed)
        native_add_file_from_url(ed, SONG_PATH, "tools/fixtures/basic.wav")
        native_queue(ed, "song", SONG_PATH)
        file_menu(ed, "loadsong")
        wait_until(ed, f"JSON.parse(window._dbg.rt.buildProjectText()).graph.song.nativePath==={json.dumps(SONG_PATH)}", label="曲の実パス")
        to_info(ed)
        native_queue(ed, "folder", PA)
        click_sel(ed, f"{OUT} .oPick", "出力フォルダを選択")
        wait_until(ed, f"window._dbgApp.infoGraph().outs.o1.outDirPath==={json.dumps(PA)}", label="出力フォルダ PA")
        _set_folder(ed, "outA")
        _CACHE["n"] = (ed.js("window._dbg.rt.buildProjectText()"), native_state(ed))
    text, state = _CACHE["n"]
    return text, json.loads(json.dumps(state))


def _fresh_native(t, state, approved=(), dirs=()):
    ed = t.fresh()
    wait_until(ed, "!document.getElementById('bootCover')", label="起動中の覆いが外れる")
    install_fake_pywebview(ed, approved=approved, dirs=dirs, state=state)
    install_fake_fs(ed)
    stub_convert(ed)
    return ed


def _export_native(ed):
    """「書き出し」ボタン（本物のクリック）。(書いたフォルダ, 知らせ)"""
    native_reset_calls(ed)
    to_info(ed)
    ed.js("(()=>{ const e=document.getElementById('errToast'); e.textContent=''; e.style.display='none'; return 1; })()")
    _click_shown(ed, "#iExport", "書き出しボタン")
    wait_until(ed, "document.getElementById('errToast').style.display==='block'&&/書き出しました|書き出し失敗|書き出せません/.test(document.getElementById('errToast').textContent)",
               label="書き出しの知らせ")
    ed.wait(0.2)
    return sorted({p.rsplit("\\", 1)[0] for p in native_writes(ed)}), toast(ed)


def _refused(t, ed, label):
    """書き出しボタンが出力フォルダの無いことで止まり、どこにも書かないこと"""
    wrote, msg = _export_native(ed)
    t.eq(wrote, [], f"{label}: どこにも書かない（{msg}）")
    t.ok("書き出せません" in msg and "CustomLevelsフォルダ" in msg, f"{label}: 出力フォルダが足りないと知らせる: {msg}")
    forget_errors(ed, "書き出せません")


def test_outdir_reopen_native_no_record(t):
    '''exe 版: A（許可済みの PA に自動で繋がる）→ B（フォルダの記録なし）: 未接続・「再接続」。書き出しボタンは止まり、審査の指摘の .txt はダウンロード
    （以前は A の PA が準備済みのまま、書き出し・.txt が PA へ）'''
    a, state = _native_a(t)
    ed = _fresh_native(t, state)
    _open(ed, "a.nlmf", a)
    t.eq(_card(ed), OK_CARD, "A は許可済みの PA へ自動で繋がる")
    t.eq(_export_native(ed)[0], [PA + "\\outA"], "A は PA へ書き出す")
    _open(ed, "b.nlmf", _with_out(a, "outB", ""))
    t.eq(_card(ed), NONE_CARD, "A→B（記録なし）")
    t.eq(_press_card(ed), NONE_CARD, "カードを押しても未接続のまま")
    _refused(t, ed, "B")
    rv = _review_save(ed)
    t.eq((rv["native"], rv["download"]), ([], ["outB_Mod_reply.txt"]), f"審査の指摘の .txt は PA へ行かない（ダウンロード）: {rv['status']}")
    t.no_errors()


def test_outdir_reopen_native_unapproved(t):
    '''exe 版: A（PA）→ B（記録は PB・このPCでは未許可）: 自動では繋がず「再接続」（以前は PA に繋がったままで、B の書き出しが PA へ）。再接続で PB を選ぶと PB へ'''
    a, state = _native_a(t)
    ed = _fresh_native(t, state, dirs=(PB,))
    _open(ed, "a.nlmf", a)
    t.eq(_card(ed), OK_CARD, "A は PA へ繋がる")
    _open(ed, "b.nlmf", _with_out(a, "outB", PB))
    t.ok("再接続" in ed.js("document.getElementById('stat').textContent"), "未許可のフォルダは選び直すよう案内する")
    t.eq(_card(ed), RECON_CARD, "A→B（PB・未許可）: 「再接続」")
    t.eq(_press_card(ed), RECON_CARD, "カードを押しても繋がらない")
    _refused(t, ed, "B")
    native_queue(ed, "folder", PB)
    _click_shown(ed, f"{OUT} .oReconnect", "再接続")
    wait_until(ed, f"document.querySelector('{OUT} .oReconnect').style.display==='none'", label="再接続の完了")
    t.eq(_export_native(ed)[0], [PB + "\\outB"], "再接続した B は PB へ書き出す")
    t.no_errors()


def test_outdir_reopen_native_approved(t):
    '''exe 版: 開いたプロジェクトの記録が許可済みなら今までどおり自動で繋がる: A（PA）→ B（PB・許可済み）は PB、→ A は PA、→ B'（PA・フォルダ名 outB）は PA'''
    a, state = _native_a(t)
    ed = _fresh_native(t, state, approved=(PB,))
    _open(ed, "a.nlmf", a)
    _open(ed, "b.nlmf", _with_out(a, "outB", PB))
    t.eq(_card(ed), OK_CARD, "B は PB へ自動で繋がる")
    t.eq(_export_native(ed)[0], [PB + "\\outB"], "B は PB へ書き出す")
    _open(ed, "a.nlmf", a)
    t.eq(_export_native(ed)[0], [PA + "\\outA"], "B→A は PA へ書き出す")
    _open(ed, "b2.nlmf", _with_out(a, "outB", PA))
    t.eq(_card(ed), OK_CARD, "同じ PA の記録の B' も繋がる")
    t.eq(_export_native(ed)[0], [PA + "\\outB"], "B' は PA へ書き出す")
    t.no_errors()


def test_outdir_new_native(t):
    '''exe 版: A（PA）→ 新規: 未接続（以前は PA が準備済みのまま・審査の指摘の .txt が PA へ）'''
    a, state = _native_a(t)
    ed = _fresh_native(t, state)
    _open(ed, "a.nlmf", a)
    t.eq(_card(ed), OK_CARD, "A は PA へ繋がる")
    _new(ed)
    t.eq(_card(ed), NONE_CARD, "新規")
    t.eq(_press_card(ed), NONE_CARD, "カードを押しても未接続のまま")
    rv = _review_save(ed)
    t.eq(rv["native"], [], f"審査の指摘の .txt は PA へ行かない: {rv['status']}")
    t.eq(len(rv["download"]), 1, "ダウンロード")
    t.no_errors()


def test_outdir_keep_native(t):
    '''exe 版: 同じプロジェクトでは繋がったまま: 保存・Undo（フォルダ名の入力の取り消し）・書き出しノードを足して切り替えて戻す'''
    a, state = _native_a(t)
    ed = _fresh_native(t, state)
    _open(ed, "a.nlmf", a)
    n = ed.js("__fake.writes.length")
    file_menu(ed, "save")
    wait_until(ed, f"__fake.writes.length>{n}", label="保存の書き込み")
    t.eq(_card(ed), OK_CARD, "保存しても繋がったまま")
    _set_folder(ed, "outX")
    undo(ed)
    wait_until(ed, "window._dbgApp.infoGraph().outs.o1.folderName==='outA'", label="フォルダ名の Undo")
    t.eq(_card(ed), OK_CARD, "Undo しても繋がったまま")
    p = free_spot(ed)
    ed.click(p["x"], p["y"], button="right")
    click_text(ed, "#ctxmenu button", "＋ 書き出しノード")
    wait_until(ed, "window._dbgApp.infoGraph().activeOut==='o2'", label="書き出しノード o2 を足す（アクティブ）")
    t.eq(_card(ed, "o2"), NONE_CARD, "足した o2 は未接続")
    t.eq(_press_card(ed, "o1"), OK_CARD, "o1 へ戻すと繋がったまま")
    t.eq(_export_native(ed)[0], [PA + "\\outA"], "PA へ書き出す")
    t.no_errors()


# ---- 開いてすぐ次を開く（前のプロジェクトの自動の接続が後から終わる） ----
_SLOW_MS = 3000


def _slow_pa(ed):
    """PA の確かめ（out_dir_ok）だけを遅くする。始めた数を __slowStart・終わった数を __slowDone に数える"""
    ed.js(f"""(()=>{{ const api=window.pywebview.api, of=api.out_dir_ok; window.__slowStart=0; window.__slowDone=0;
      api.out_dir_ok=async(p)=>{{ if(String(p).toLowerCase()==={json.dumps(PA.lower())}){{ window.__slowStart++;
          await new Promise(r=>setTimeout(r,{_SLOW_MS})); const j=await of(p); window.__slowDone++; return j; }}
        return of(p); }}; return true; }})()""")


def _race(t, b_path, want):
    """A を開き、PA を確かめている途中（遅い）で B（記録 b_path）を開く。A の確かめが終わってから、カードを押して書き出す"""
    a, state = _native_a(t)
    ed = _fresh_native(t, state, approved=(PB,))
    _slow_pa(ed)
    queue_open(ed, "a.nlmf", a)
    file_menu(ed, "open")
    wait_until(ed, "window.__slowStart>=1", label="A の出力フォルダを確かめ始める")
    _open(ed, "b.nlmf", _with_out(a, "outB", b_path))
    wait_until(ed, "window.__slowDone>=window.__slowStart", timeout=_SLOW_MS / 1000 + 10, label="A の確かめが終わる")
    ed.wait(0.3)
    t.eq(_card(ed), want, "A の確かめが終わった後の B")
    t.eq(_press_card(ed), want, "カードを押した後の B（控えに A のフォルダが入っていない）")
    return ed


def test_outdir_race_native_approved(t):
    '''exe 版: A（PA の確かめが遅い）を開いてすぐ B（PB・許可済み）を開く: B は PB のまま。以前は A の確かめが後から終わって控えに PA を入れ、
    カードを押すと表示は PB のまま書き出しが PA へ行った'''
    ed = _race(t, PB, OK_CARD)
    t.eq(_export_native(ed)[0], [PB + "\\outB"], "B は PB へ書き出す（PA へは書かない）")
    t.no_errors()


def test_outdir_race_native_no_record(t):
    '''exe 版: A（PA の確かめが遅い）を開いてすぐ B（記録なし）を開く: B は未接続のまま。以前はカードを押すと PA に繋がった'''
    ed = _race(t, "", NONE_CARD)
    _refused(t, ed, "B")
    t.no_errors()

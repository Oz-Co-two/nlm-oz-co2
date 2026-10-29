"""メニューバー（作業の流れで分ける・2026-10-28）: ファイル／譜面作り／確かめる／審査／環境設定／ヘルプ。
開き方（押す・開いている間は見出しへ動かすだけで切り替わる・Esc／外側のクリックで閉じる。環境設定も同じ＝2026-10-29）・項目の並び・ショートカットの表示（今の割り当て）・
新しい入口（書き出し・譜面チェックのタブ・審査の書き出し・ヘルプのページ・ショートカット・「NLM について」）。
ヘルプのページ・ライセンスの文書は、テストのサーバーでは実際には開かない（NLM_NO_OPEN・cdp.py。開く物は応答の opened）。
変更履歴（/__update/openNotes）は本当にブラウザを開くので偽物で受ける。解析の結果を使う項目は tests/e2e_nle/test_analysis.py"""
import json

from misc_helpers import (click_sel, file_menu, fresh_page, ls_json, open_fixture_ready, prefs_page, reload_keep, toast, wait_mirrored,
                          wait_until)
from project_helpers import forget_errors   # noqa: E402（misc_helpers が読み込み先を足す）

HEADS = ["ファイル", "譜面作り", "確かめる", "審査", "環境設定", "ヘルプ"]
ITEMS = {
    "mFileMenu": ["new", "open", "|", "save", "saveas", "savecopy", "|", "addfolder"],
    "mMapMenu": ["loadsong", "|", "analyze", "anaclips", "anamarkers", "|", "autolight", "|", "export"],
    "mCheckMenu": ["mapcheck", "mapcheckbl", "mapcheckam", "|", "rating"],
    "mReviewMenu": ["reviewload", "reviewpaste", "|", "reviewlist", "reviewexport"],
    "mPrefsMenu": ["settings"],
    "mHelpMenu": ["tutorial", "advanced", "keys", "changelog", "|", "update", "|", "about"],
}
OPEN = "[...document.querySelectorAll('#menubar .mbWrap.open')].map(w=>w.id)"

# ヘルプの通信を記録する（/__help/* はサーバーへ通す＝NLM_NO_OPEN で開かずに opened を返す。/__update/openNotes は偽物で返す）
_SPY_JS = r"""(()=>{ const H=window.__help={calls:[]}; if(!window.__helpOrig) window.__helpOrig=window.fetch;
  const of=window.__helpOrig.bind(window);
  window.fetch=async (url,opt)=>{ const u=String(url), m=u.match(/__(help|update)\/(open\w*)/);
    if(!m) return of(url,opt);
    let body=null; try{ body=JSON.parse((opt&&opt.body)||'null'); }catch(_){}
    if(m[1]==='update'){ H.calls.push({path:'update/'+m[2],body,res:{ok:true}}); return new Response('{"ok":true}',{headers:{'content-type':'application/json'}}); }
    const r=await of(url,opt); const j=await r.clone().json(); H.calls.push({path:'help/'+m[2],body,res:j}); return r; };
  return 1; })()"""


def _spy(ed):
    ed.js(_SPY_JS)


def _calls(ed):
    return ed.js("window.__help.calls")


def _wait_calls(ed, n):
    wait_until(ed, f"window.__help.calls.length>={n}", label=f"ヘルプの通信 {n} 回")


def _move_to(ed, sel):
    r = ed.js(f"(()=>{{const r=document.querySelector({json.dumps(sel)}).getBoundingClientRect(); return [r.left+r.width/2,r.top+r.height/2]}})()")
    ed.move(*r); ed.wait(0.3)


def test_menu_bar_layout_and_open_close(t):
    '''見出しの並び・各メニューの項目の並び。押すと開き、開いている間は見出しへ動かすだけで隣へ切り替わる。Esc・外側のクリック・同じ見出しで閉じる。
    「環境設定」も押すと下に開き（以前は押すとすぐ設定の画面で、下に何も出ず不具合に見えた）、中の「環境設定…」で設定の画面'''
    ed = fresh_page(t)
    t.eq(ed.js("[...document.querySelectorAll('#menubar > .mbWrap > .mbtn')].map(b=>b.textContent.trim())"), HEADS, "見出しの並び")
    got = ed.js("Object.fromEntries([...document.querySelectorAll('#menubar .mbMenu')].map(m=>[m.id,[...m.children].map(c=>c.tagName==='HR'?'|':c.dataset.act)]))")
    t.eq(got, ITEMS, "各メニューの項目の並び")
    click_sel(ed, "#mFileBtn", "ファイル")
    t.eq(ed.js(OPEN), ["mFileWrap"], "押すと開く")
    _move_to(ed, "#mMapBtn")
    t.eq(ed.js(OPEN), ["mMapWrap"], "開いている間は見出しへ動かすだけで切り替わる")
    _move_to(ed, "#mbSettings")
    t.eq((ed.js(OPEN), ed.js("document.getElementById('mPrefsMenu').style.display")), (["mPrefsWrap"], "block"), "環境設定も動かすだけで開く")
    _move_to(ed, "#mHelpBtn")
    t.eq((ed.js(OPEN), ed.js("document.getElementById('mHelpMenu').style.display")), (["mHelpWrap"], "block"), "ヘルプへ")
    ed.key("Escape"); ed.wait(0.3)
    t.eq(ed.js(OPEN), [], "Esc で閉じる")
    _move_to(ed, "#mCheckBtn")
    t.eq(ed.js(OPEN), [], "閉じている時は見出しへ動かしても開かない")
    click_sel(ed, "#mCheckBtn", "確かめる"); click_sel(ed, "#mCheckBtn", "確かめる")
    t.eq(ed.js(OPEN), [], "同じ見出しをもう一度押すと閉じる")
    click_sel(ed, "#mReviewBtn", "審査"); ed.click(1700, 1000); ed.wait(0.3)
    t.eq(ed.js(OPEN), [], "外側のクリックで閉じる")
    click_sel(ed, "#mbSettings", "環境設定")
    t.eq((ed.js(OPEN), ed.js("getComputedStyle(document.getElementById('settingsBg')).display")), (["mPrefsWrap"], "none"), "環境設定は押すと下に開く（設定の画面はまだ）")
    click_sel(ed, ".mbMenu button[data-act=settings]", "環境設定…")
    t.eq((ed.js(OPEN), ed.js("document.getElementById('settingsBg').style.display")), ([], "flex"), "「環境設定…」で設定の画面（メニューは閉じる）")
    click_sel(ed, "#settingsClose", "閉じる")
    t.no_errors()


def test_menu_shortcut_labels_follow_keymap(t):
    '''ファイルメニューのショートカットの表示は、環境設定で変えた今の割り当て（以前は「Ctrl O」などの決め打ちで、変えても古いキーのままだった）'''
    keys = "Object.fromEntries([...document.querySelectorAll('#mFileMenu .mkey[data-key]')].map(k=>[k.dataset.key,k.textContent]))"
    with prefs_page(t) as ed:
        click_sel(ed, "#mFileBtn", "ファイル")
        t.eq(ed.js(keys), {"open": "Ctrl+O", "save": "Ctrl+S", "saveAs": "Ctrl+Shift+S"}, "既定の割り当て")
        ed.key("Escape")
        ed.js("localStorage.setItem('bsnm_keymap',JSON.stringify({save:{k:'w',c:true,a:false,s:false}}));true")
        wait_mirrored(ed, "bsnm_keymap")
        reload_keep(ed)
        t.eq(ls_json(ed, "bsnm_keymap"), {"save": {"k": "w", "c": True, "a": False, "s": False}}, "割り当てが残る")
        click_sel(ed, "#mFileBtn", "ファイル")
        t.eq(ed.js(keys)["save"], "Ctrl+W", "変えた割り当てを出す")
        click_sel(ed, "#mHelpBtn", "ヘルプ")
        t.eq(ed.js("[...document.querySelectorAll('#mHelpMenu .mkey[data-ext]')].map(k=>[k.textContent,k.parentElement.title])"),
             [["↗", "ブラウザで開きます"]] * 3, "ブラウザで開く項目の印（チュートリアル・上級編・変更履歴）")
        ed.key("Escape")
        t.no_errors()


def test_menu_check_tabs_export_and_review(t):
    '''確かめる: 譜面チェックの3つの項目は、そのタブでパネルを開く（前回のタブに関係なく）。譜面作り「カスタム曲を書き出す…」は INFO の［カスタム曲書き出し］と
    同じ（足りない物があれば理由を出して止める）。審査「書き出す…」は一覧の［書き出す…］と同じ画面'''
    ed = open_fixture_ready(t, "rich")
    tab = "(p=>p&&p.style.display!=='none'?p.querySelector('.mcTab.on').dataset.tab:null)(document.getElementById('mcPanel'))"
    for act, want in (("mapcheckbl", "bl"), ("mapcheckam", "am"), ("mapcheck", "mc")):
        file_menu(ed, act)
        wait_until(ed, f"{tab}==={json.dumps(want)}", label=f"{act} で {want} のタブ")
        t.eq(ed.js("localStorage.getItem('bsnm_mcTab')"), want, f"{act}: 開いたタブを覚える")
    ed.js("document.querySelector('#mcPanel .mcClose').click();true")
    # 書き出し（素材 rich には出力先が無い＝INFO のボタンと同じ理由で止める）
    ed.js("document.getElementById('errToast').style.display='none';true")
    file_menu(ed, "export")
    wait_until(ed, "document.getElementById('errToast').style.display!=='none'", label="書き出せない理由")
    via_menu = toast(ed)
    t.ok("書き出せません:" in via_menu, f"理由を出して止める: {via_menu}")
    ed.js("document.getElementById('errToast').style.display='none';document.getElementById('iExport').click();true")
    wait_until(ed, "document.getElementById('errToast').style.display!=='none'", label="INFO のボタンの理由")
    t.eq(toast(ed), via_menu, "INFO の［カスタム曲書き出し］と同じ")
    forget_errors(ed, "書き出せません")   # 意図して出した知らせ（console.error にも出る）
    # 審査の書き出し
    file_menu(ed, "reviewexport")
    wait_until(ed, "!!document.querySelector('#dirtyDlg[data-rv=rvExportDlg]')", label="審査の書き出しの画面")
    ed.key("Escape")
    wait_until(ed, "!document.querySelector('#dirtyDlg[data-rv=rvExportDlg]')", label="閉じる")
    t.no_errors()


def test_menu_help_pages_and_keys(t):
    '''ヘルプ: チュートリアル・上級編は決まった名前と表示言語だけを送り、サーバーが固定の URL を開く（英語なら英語版）。変更履歴は本体の更新の
    「詳しく見る」と同じ口（版なし）。「ショートカットの一覧・変更…」は環境設定のショートカット編集のタブ'''
    with prefs_page(t) as ed:
        _spy(ed)
        file_menu(ed, "tutorial"); file_menu(ed, "advanced"); file_menu(ed, "changelog")
        _wait_calls(ed, 3)
        c = _calls(ed)
        t.eq([(x["path"], x["body"]) for x in c],
             [("help/open", {"doc": "tutorial", "lang": "ja"}), ("help/open", {"doc": "advanced", "lang": "ja"}), ("update/openNotes", {"lang": "ja"})],
             "送るのは名前と言語だけ")
        t.eq([x["res"].get("opened") for x in c[:2]],
             ["https://github.com/Oz-Co-two/nlm-oz-co2/blob/master/docs/tutorial.md", "https://github.com/Oz-Co-two/nlm-oz-co2/blob/master/docs/tutorial-advanced.md"],
             "固定の URL（日本語）")
        file_menu(ed, "keys")
        wait_until(ed, "document.getElementById('settingsBg').style.display==='flex'", label="環境設定")
        t.eq(ed.js("document.querySelector('#settingsBox .setTab.on').dataset.tab"), "keys", "ショートカット編集のタブ")
        t.ok(ed.js("!!document.querySelector('#keyEditBody kbd')"), "ショートカットの一覧が描かれている")
        click_sel(ed, "#settingsClose", "閉じる")
        ed.js("localStorage.setItem('bsnm_lang','en');true")
        wait_mirrored(ed, "bsnm_lang")
        reload_keep(ed); _spy(ed)
        file_menu(ed, "tutorial")
        _wait_calls(ed, 1)
        t.eq(_calls(ed)[0]["res"].get("opened"), "https://github.com/Oz-Co-two/nlm-oz-co2/blob/master/docs/tutorial.en.md", "英語の表示なら英語版")
        t.no_errors()


def test_menu_about(t):
    '''「NLM について」: 版（右上の版と同じ）・原作者の表記・著作権・ライセンス（GPLv3）と無保証・取り込み済みのプラグインの版。
    ページ・文書のボタンは決まった名前だけを送る（ライセンスはメモ帳で開く＝テストでは開かずに見つかった名前を返す）。Esc・［閉じる］で閉じる'''
    ed = fresh_page(t)
    _spy(ed)
    file_menu(ed, "about")
    dlg = "#dirtyDlg[data-dlg=about]"
    wait_until(ed, f"[...document.querySelectorAll('{dlg} .abPlVer')].every(e=>e.textContent!=='…')", label="プラグインの版")
    d = ed.js(f"""(()=>{{const q=s=>document.querySelector('{dlg} '+s);
      return {{ver:q('.abVer').textContent, top:document.querySelector('#menubar .mbVer').textContent, lead:q('.abLead').textContent, copy:q('.abCopy').textContent,
        text:[...document.querySelectorAll('{dlg} .abText')].map(e=>e.textContent),
        pl:[...document.querySelectorAll('{dlg} .abPl')].map(r=>[r.dataset.pl,r.querySelector('.abPlName').textContent,r.querySelector('.abPlVer').textContent]),
        btns:[...document.querySelectorAll('{dlg} button')].map(b=>b.textContent)}}; }})()""")
    t.eq(d["ver"], d["top"], "版は右上の版と同じ")
    t.ok("helba" in d["lead"] and "Oz-Co2版" in d["lead"], f"派生版の説明: {d['lead']}")
    t.eq(d["copy"], "Copyright (C) 2026 helba (original author)\nCopyright (C) 2026 Oz-Co2 (modifications and additions)", "著作権の表示（LICENSE と同じ）")
    t.ok("GNU General Public License 第3版" in d["text"][0] and "無保証" in d["text"][1], f"ライセンスと無保証: {d['text']}")
    t.eq(d["pl"], [["rating", "難易度を測る（nlm-rating）", "取り込んでいません"], ["automodder", "AutoModder の判定（nlm-automodder）", "取り込んでいません"]],
         "取り込み済みのプラグイン（テストの環境は未導入）")
    t.eq(d["btns"], ["原作のページ ↗", "Oz-Co2版のページ（GitHub） ↗", "ライセンス（GPLv3）", "第三者のライセンス", "閉じる"], "ボタン")
    for sel in (".abLink:nth-of-type(1)", ".abLink:nth-of-type(2)", "button[data-file=license]", "button[data-file=notices]"):
        click_sel(ed, f"{dlg} {sel}", sel)
    _wait_calls(ed, 4)
    t.eq([(x["path"], x["body"], x["res"]) for x in _calls(ed)], [
        ("help/open", {"doc": "original", "lang": "ja"}, {"ok": True, "opened": "https://helba.flashhub.net/nlm/"}),
        ("help/open", {"doc": "home", "lang": "ja"}, {"ok": True, "opened": "https://github.com/Oz-Co-two/nlm-oz-co2"}),
        ("help/openFile", {"name": "license", "lang": "ja"}, {"ok": True, "opened": "LICENSE"}),
        ("help/openFile", {"name": "notices", "lang": "ja"}, {"ok": True, "opened": "THIRD_PARTY_NOTICES.txt"}),
    ], "決まった名前だけを送り、決まった物を開く")
    t.ok(ed.js(f"!!document.querySelector('{dlg}')"), "ボタンを押しても画面は閉じない")
    ed.key("Escape"); ed.wait(0.3)
    t.ok(ed.js(f"!document.querySelector('{dlg}')"), "Esc で閉じる")
    file_menu(ed, "about")
    wait_until(ed, f"!!document.querySelector('{dlg}')", label="もう一度")
    click_sel(ed, f"{dlg} .ddBtns button", "閉じる")
    t.ok(ed.js(f"!document.querySelector('{dlg}')"), "［閉じる］で閉じる")
    t.no_errors()

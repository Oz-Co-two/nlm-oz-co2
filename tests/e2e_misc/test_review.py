"""審査の指摘（js/review/review-panel.js・2026-10-27）: 読み込み（.txt・貼り付け・難易度の選択）・一覧・クリックで飛ぶ（ちょうど・近い物・見つからない・範囲・ライト）・
タイムラインの印・済みの印と返事・保存して開き直す・Undo・C3（拍を付け替えた難易度の拍の直し）・書き出し（返事・NLM の確かめ）・クリップボード・出力フォルダへの保存。
見本の文は作り物（tests/_lib/review_helpers.py）。"""
import json
import re

from misc_helpers import (OUT, OUT_BASE, click_sel, install_fake_pywebview, native_file_text, native_queue, open_fixture_ready, to_info, type_text, wait_mirrored,
                          wait_until)
from nlmtest import LIGHT_RENDER_JS
from project_helpers import file_menu, install_fake_fs, queue_open
from review_helpers import (NO_HEAD, SAMPLE, bulk_info, bulk_load, rv, rv_click_row, rv_import, rv_open_import, rv_row, v3_dat)
from e2e_helpers import _CAPTURE_JS


def _items(ed):
    return rv(ed)["items"]


def _by_text(ed, s):
    return next(x for x in _items(ed) if s in x["text"])


def _sel(ed):
    """3Dの選択（種類・拍）"""
    return sorted((o["kind"], o["beat"]) for o in ed.js("window._dbgApp.selObjs().objs"))


def _cur_diff(ed):
    return ed.js("window._dbgApp.state().diff")


def _beat_is(ed, b):
    """再生位置が b に着く（飛ぶ時は短いスクロールで動く）"""
    wait_until(ed, f"Math.abs(window._dbgApp.state().cur-({b}))<1e-6", label=f"再生位置 {b}")
    return True


def _lamp(ed):
    return ed.js("window._dbgApp.dirty().lamp")


def test_review_import_and_list(t):
    '''読み込み: 見出しの難易度・見出しの無い指摘は選んだ難易度・Standard 以外・拍の無い行・読めない行・続きの行。一覧は難易度ごと・書かれた順'''
    ed = open_fixture_ready(t, "rich")
    rv_open_import(ed, [("Mod.txt", SAMPLE), (None, NO_HEAD)])
    dlg = ed.js("document.querySelector('#dirtyDlg[data-rv=rvImport]').innerText")
    t.ok("Expert 4件" in dlg and "Standard 以外 1件" in dlg and "読めなかった行 1" in dlg, f"読んだ数: {dlg}")
    t.eq(ed.js("[...document.querySelectorAll('#dirtyDlg .rvPickSel')].map(s=>s.value)"), ["Hard"], "見出しの無い指摘の難易度の既定＝今の難易度（Hard）")
    ed.js("document.querySelector('#dirtyDlg [data-v=cancel]').click(); true")
    t.eq(rv(ed)["items"], [], "キャンセルでは読み込まない")
    rv_import(ed, [("Mod.txt", SAMPLE), (None, NO_HEAD)], picks=["Normal"])
    d = rv(ed)
    t.ok(d["open"], "読み込んだら一覧を開く")
    std = [(x["difficulty"], x["mode"], x["beats"], x["ranges"], x["text"]) for x in d["items"]]
    t.eq(std, [("Expert", "Standard", [4], [], "first note looks off"), ("Expert", "Standard", [7.53], [], "slightly early?"),
               ("Expert", "Standard", [], [[13, 15]], "this part feels cramped"), ("Expert", "Standard", [100], [], "nothing here"),
               ("ExpertPlus", "OneSaber", [5], [], "other mode"),
               ("Normal", "Standard", [2], [], "a note without a heading"), ("Normal", "Standard", [3, 5], [], "two spots")], "項目（書かれた順・難易度・モード）")
    t.eq(_by_text(ed, "cramped")["cont"], ["continuation of the previous line"], "字下げした続きの行")
    t.eq(sorted((n["kind"], n["text"]) for n in d["notes"]), [("comment", "general thought without a beat"), ("mapper", "SomeMapper"),
                                                             ("unreadable", "231.g - unreadable line")], "拍の無い行・担当・読めない行")
    t.eq([s["name"] for s in d["srcs"]], ["Mod.txt", None], "読み込んだ物（ファイル名・貼り付け）")
    # 一覧の区分: Expert → Normal → Standard 以外（難しい方から）
    secs = ed.js("[...document.querySelectorAll('#rvPanel details.rvSec')].map(x=>x.dataset.key)")
    t.eq(secs, ["Expert", "Normal", "other", "notes"], "一覧の区分の順")
    t.eq(ed.js("document.querySelector('#rvPanel .rvCnt').textContent"), "7件・済み 0", "件数")
    t.ok(wait_until(ed, "window._dbgApp.dirty().lamp", label="読み込むと未保存"), "読み込むと未保存")
    t.no_errors()


def test_review_text_is_not_html(t):
    '''指摘の文・見出し・ファイル名は HTML にしない（他人の文章。textContent でだけ出す）'''
    ed = open_fixture_ready(t, "rich")
    evil = '<img src=x onerror="window.__rvX=1">'
    rv_import(ed, [('<b>x</b>.txt', f"Expert\n4 - {evil}\n  {evil}\n{evil}")])
    ed.js("document.querySelectorAll('#rvPanel details').forEach(d=>d.open=true); true")
    ed.wait(0.3)
    t.eq(ed.js("document.querySelectorAll('#rvPanel img, #rvPanel b').length"), 0, "要素として作られない")
    t.ok(ed.js("!window.__rvX"), "スクリプトは動かない")
    t.ok(evil in ed.js("document.querySelector('#rvPanel .rvText').textContent"), "文はそのままの文字で出る")
    t.no_errors()


def test_review_jump(t):
    '''行のクリック: その難易度へ切り替えて拍の物を選ぶ（ちょうど）・近い物（±1/16拍）・見つからない（古い指摘かも）・範囲・拍の数字だけ・ノーツが無ければライト'''
    ed = open_fixture_ready(t, "rich")
    rv_import(ed, [("Mod.txt", SAMPLE + "\n\nExpert\n0 - lights at the start"), (None, NO_HEAD)], picks=["Hard"])
    t.eq(_cur_diff(ed), "HardStandard.dat", "最初は Hard")
    rv_click_row(ed, "first note")
    t.eq(_cur_diff(ed), "ExpertStandard.dat", "Expert へ切り替える")
    t.eq(_sel(ed), [("note", 4), ("note", 4)], "拍4の2個を選ぶ")
    t.ok(_beat_is(ed, 4), "再生位置も拍4")
    t.ok("Expert の拍 4 へ移動しました（2個を選びました）" in rv(ed)["msg"]["text"], rv(ed)["msg"]["text"])
    rid = rv_click_row(ed, "slightly early")
    t.eq(_sel(ed), [("note", 7.5)], "7.53 ちょうどは無い → 一番近い 7.5")
    t.ok("近い物（0.03拍ずれ・1個）" in rv(ed)["msg"]["text"], rv(ed)["msg"]["text"])
    t.eq(rv(ed)["jump"][rid], "near", "近い物の印")
    rid = rv_click_row(ed, "nothing here")
    t.eq(_sel(ed), [], "拍100には物が無い")
    t.ok(_beat_is(ed, 100), "再生位置だけ動く")
    t.ok("物が見つかりません（古い指摘かもしれません）" in rv(ed)["msg"]["text"], rv(ed)["msg"]["text"])
    t.eq(rv(ed)["msg"]["kind"], "warn", "注意の色")
    t.ok(ed.js(f"!!document.querySelector('#rvPanel .rvItem[data-id={rid}] .rvRes.none')"), "行に ⚠ の印")
    rv_click_row(ed, "cramped")
    t.eq(_sel(ed), [("arc", 14), ("note", 14)], "範囲 13-15 の中の物")
    rv_click_row(ed, "lights at the start")
    t.eq(_sel(ed), [], "ノーツ類は選ばない")
    t.eq(ed.js("window._dbgApp.selObjs().lights"), 2, "拍0のライト2個")
    t.ok("ライト（2個）を選びました" in rv(ed)["msg"]["text"], rv(ed)["msg"]["text"])
    # 拍の数字だけ（「3, 5」の 5）
    r = rv_row(ed, "two spots")
    chip = ed.js(f"(()=>{{ const c=document.querySelectorAll('#rvPanel .rvItem[data-id={r['id']}] .rvBeat')[1]; const q=c.getBoundingClientRect(); return {{x:q.left+q.width/2,y:q.top+q.height/2,t:c.textContent}}; }})()")
    t.eq(chip["t"], "5", "2つ目の拍の数字")
    ed.click(chip["x"], chip["y"])
    _beat_is(ed, 5)
    t.eq(_cur_diff(ed), "HardStandard.dat", "Hard へ切り替える")
    t.eq(_sel(ed), [("note", 5)], "拍5の物だけ")
    # Standard 以外は飛べない
    rv_click_row(ed, "other mode")
    t.ok("Standard 以外の指摘は NLM では開けません" in rv(ed)["msg"]["text"], rv(ed)["msg"]["text"])
    t.no_errors()


def test_review_marks(t):
    '''タイムラインの印: 今の難易度の分だけ数字の帯に出る・印のクリックで一覧のその項目へ（シークしない）・印の無い所のクリックは今までどおりシーク'''
    ed = open_fixture_ready(t, "rich")
    rv_import(ed, [("Mod.txt", "Expert\n4 - first\n6 - second\n\nHard\n2 - hard one")])
    ed.wait(0.3)
    hard = ed.js("window._dbgApp.reviewMarks()")
    t.eq(len(hard), 1, "Hard を開いている＝Hard の印だけ")
    ed.js("document.querySelector('#rvPanel .rvClose').click(); true")
    t.ok(not rv(ed)["open"], "一覧を閉じる")
    ed.js("window._dbg.rt.switchDiffByIndex(3); true")
    wait_until(ed, "window._dbgApp.reviewMarks().length===2", label="Expert の印")
    m = ed.js("window._dbgApp.reviewMarks()")
    g = ed.js("window._dbgApp.nleScreen(6)")
    m6 = min(m, key=lambda q: abs(q["x"] + q["w"] / 2 - g["x"]))
    beat0 = ed.js("window._dbgApp.state().cur")
    ed.click(m6["x"] + m6["w"] / 2, m6["y"] + m6["h"] / 2)
    ed.wait(0.3)
    d = rv(ed)
    t.ok(d["open"], "印のクリックで一覧が開く")
    t.eq(next(x["text"] for x in d["items"] if x["id"] == d["cur"]), "second", "その項目を選ぶ")
    t.eq(ed.js("window._dbgApp.state().cur"), beat0, "印のクリックではシークしない")
    g2 = ed.js("window._dbgApp.nleScreen(10)")
    ed.click(g2["x"], g2["ruler"] + 6)
    _beat_is(ed, 10)
    t.no_errors()


def test_review_done_reply_save_reopen_undo(t):
    '''済みの印・返事: 未保存のランプが点く・Ctrl+Z で戻る・保存して開き直すと残る（済み・返事・NLM の拍）'''
    ed = open_fixture_ready(t, "rich")
    install_fake_fs(ed)
    rv_import(ed, [("Mod.txt", "Expert\n4 - first\n6 - second")])
    # 開いた直後の状態を保存済みにする（読み込みで未保存になるため）
    file_menu(ed, "save")
    wait_until(ed, "!window._dbgApp.dirty().lamp", label="保存して未保存が消える")
    rid = rv_row(ed, "first")["id"]
    box = ed.js(f"(()=>{{ const q=document.querySelector('#rvPanel .rvItem[data-id={rid}] .rvDone').getBoundingClientRect(); return {{x:q.left+q.width/2,y:q.top+q.height/2}}; }})()")
    ed.click(box["x"], box["y"])
    wait_until(ed, f"window._dbgApp.review().items.find(x=>x.id==='{rid}').done", label="済み")
    wait_until(ed, "window._dbgApp.dirty().lamp", label="済みで未保存")
    rv_click_row(ed, "second")
    inp = ed.js("(()=>{ const i=document.querySelector('#rvPanel .rvItem.cur .rvReply'); const q=i.getBoundingClientRect(); return {x:q.left+20,y:q.top+q.height/2}; })()")
    ed.click(inp["x"], inp["y"])
    type_text(ed, "moved it")
    ed.key("Enter")
    wait_until(ed, "window._dbgApp.review().items.some(x=>x.reply==='moved it')", label="返事")
    # Undo（返事→済み の順に戻る）
    ed.move(800, 300)
    ed.key("z", ctrl=True)
    wait_until(ed, "!window._dbgApp.review().items.some(x=>x.reply)", label="Undo で返事が戻る")
    ed.key("z", ctrl=True)
    wait_until(ed, "!window._dbgApp.review().items.some(x=>x.done)", label="Undo で済みが戻る")
    wait_until(ed, "!window._dbgApp.dirty().lamp", label="保存した時に戻せば未保存も消える")
    ed.key("z", ctrl=True, shift=True); ed.key("z", ctrl=True, shift=True)
    wait_until(ed, "window._dbgApp.review().items.some(x=>x.reply==='moved it')&&window._dbgApp.review().items.some(x=>x.done)", label="やり直し")
    file_menu(ed, "save")
    wait_until(ed, "!window._dbgApp.dirty().lamp", label="保存")
    text = ed.js("window._dbg.rt.buildProjectText()")   # 保存した中身（素材を開いたファイルへ上書きした物と同じ）
    pj = json.loads(text)
    t.eq(sorted((x["text"], x["done"], x["reply"]) for x in pj["review"]["items"]), [("first", True, ""), ("second", False, "moved it")], "保存した中身")
    # 開き直す
    ed = open_fixture_ready(t, None)
    install_fake_fs(ed)
    queue_open(ed, "r.nlmf", text)
    file_menu(ed, "open")
    wait_until(ed, "(d=>!!d&&d.items.length===2)(window._dbgApp.review())", label="開き直すと指摘が戻る")
    d = rv(ed)
    t.eq(sorted((x["text"], x["done"], x["reply"], x["difficulty"]) for x in d["items"]), [("first", True, "", "Expert"), ("second", False, "moved it", "Expert")], "開き直した指摘")
    t.ok(not _lamp(ed), "開いた直後は未保存ではない")
    t.no_errors()


def test_review_hide_done(t):
    '''「済みを隠す」: 済みの行が一覧から消え、別の行を選んでも隠したまま、外すと戻る（選んでいる行だけは済みでも隠さない作り＝visible()）'''
    ed = open_fixture_ready(t, "rich")
    rv_import(ed, [("Mod.txt", "Expert\n4 - first\n6 - second\n8 - third")])
    ids = {s: rv_row(ed, s)["id"] for s in ("first", "second", "third")}
    for s in ("first", "third"):
        box = ed.js(f"(()=>{{ const q=document.querySelector('#rvPanel .rvItem[data-id={ids[s]}] .rvDone').getBoundingClientRect(); return {{x:q.left+q.width/2,y:q.top+q.height/2}}; }})()")
        ed.click(box["x"], box["y"])
        wait_until(ed, f"window._dbgApp.review().items.find(x=>x.id==='{ids[s]}').done", label=f"済み: {s}")
    t.eq(rv(ed)["rows"], [ids["first"], ids["second"], ids["third"]], "隠す前は全部の行")
    hide = ed.js("(()=>{ const q=document.querySelector('#rvPanel .rvHideChk').getBoundingClientRect(); return {x:q.left+q.width/2,y:q.top+q.height/2}; })()")
    ed.click(hide["x"], hide["y"])
    wait_until(ed, "window._dbgApp.review().hideDone", label="済みを隠す")
    t.eq(rv(ed)["rows"], [ids["second"]], "済みを隠すと済みでない行だけ")
    rv_click_row(ed, "second")
    t.eq(rv(ed)["rows"], [ids["second"]], "行を選んでも隠したまま")
    ed.click(hide["x"], hide["y"])
    wait_until(ed, "!window._dbgApp.review().hideDone", label="隠すのをやめる")
    t.eq(rv(ed)["rows"], [ids["first"], ids["second"], ids["third"]], "外すと全部の行に戻る")
    t.no_errors()


def test_review_bad_project_data(t):
    '''保存した指摘はファイル由来: 形の違う物・知らない項目は捨て、正しい物だけ読む'''
    ed = open_fixture_ready(t, None)
    ed.js("""window._dbg.rt.reviewPanel.load({v:1,srcs:[{id:'s1',name:'a.txt',kind:'file',at:'2026-10-27T00:00:00Z',n:3}],
      items:[{id:'r1',src:'s1',difficulty:'Expert',mode:'Standard',beats:[4],ranges:[],text:'ok',done:true,reply:'r',evil:'<x>'},
             {id:'r2',difficulty:'Bogus',beats:['x'],ranges:[[1]],text:'no spots'},
             {id:'r3',difficulty:'Hard',mode:'<script>',beats:[1e9,2],ranges:[[5,3]],text:7,parent:'r9',nlmBeats:[1,2,3]},
             'junk', null],
      notes:[{text:'n',kind:'weird'},{text:''}]}); true""")
    d = rv(ed)
    t.eq([(x["id"], x["difficulty"], x["mode"], x["beats"], x["ranges"], x["text"], x["parent"], "nlmBeats" in x) for x in d["items"]],
         [("r1", "Expert", "Standard", [4], [], "ok", None, False), ("r3", "Hard", "Standard", [2], [[3, 5]], "", None, False)], "残る項目")
    t.ok("evil" not in d["items"][0], "知らない項目は持たない")
    t.eq([(n["text"], n["kind"]) for n in d["notes"]], [("n", "comment")], "拍の無い行")
    t.no_errors()


def test_review_c3_retimed(t):
    '''C3: 拍を付け替えた難易度（曲データを読み込む）は、指摘の拍を元の譜面の拍として NLM の拍へ直す（既定オン・一覧に両方の拍）。オフにすると書いた拍のまま。
    難易度の名前（_difficultyLabel）の見出しも読む'''
    ed = open_fixture_ready(t, None)
    files = {"HardStandard.dat": v3_dat([], [4, 8]), "ExpertStandard.dat": v3_dat([], [4, 8]),
             "ExpertPlusStandard.dat": v3_dat([{"b": 4, "m": 240}], [4, 8])}
    bulk_load(ed, bulk_info(120, [("Hard", None), ("Expert", None), ("ExpertPlus", "Demon")]), files)
    pj = json.loads(ed.js("window._dbg.rt.buildProjectText()"))
    tp = [s.get("srcTp") for s in pj["difficulties"]["expertplusstandard.dat"]["sections"]]
    t.eq(tp[0], {"b": 120, "f": [[4, 240]], "t": []}, "付け替えた難易度のクリップに元のテンポ")
    t.ok(all("srcTp" not in s for s in pj["difficulties"]["expertstandard.dat"]["sections"]), "付け替えていない難易度には無い")
    rv_open_import(ed, [("Demon.txt", "Demon\nm\n\n8 - retimed note\n4 - before the change")])
    t.ok(ed.js("!!document.querySelector('#dirtyDlg .rvC3Opt input[data-d=ExpertPlus]')"), "C3 の印が出る")
    t.ok(ed.js("document.querySelector('#dirtyDlg .rvC3Opt input[data-d=ExpertPlus]').checked"), "既定はオン")
    t.eq(ed.js("document.querySelectorAll('#dirtyDlg .rvPickSel').length"), 0, "難易度の名前「Demon」は Expert+ と読む（選ばない）")
    ed.js("document.querySelector('#dirtyDlg[data-rv=rvImport] .ddBtns button.pri').click(); true")
    wait_until(ed, "window._dbgApp.review().items.length===2", label="読み込み")
    x = _by_text(ed, "retimed")
    t.eq((x["difficulty"], x["beats"], x["nlmBeats"]), ("ExpertPlus", [8], [6]), "元の拍8＝4拍(120)+4拍(240)＝3秒 → NLM の拍6")
    t.eq(_by_text(ed, "before the change")["nlmBeats"], [4], "変化の前は同じ拍")
    t.ok("→ NLM 6" in ed.js("document.querySelector('#rvPanel .rvNlm').textContent"), "一覧に NLM の拍")
    rv_click_row(ed, "retimed")
    t.eq(_cur_diff(ed), "ExpertPlusStandard.dat", "Expert+ へ")
    t.eq(_sel(ed), [("note", 6)], "NLM の拍6のノーツ")
    # オフで読む＝書いた拍のまま
    rv_import(ed, [("Demon.txt", "Demon\n8 - as written")], c3={"ExpertPlus": False})
    y = _by_text(ed, "as written")
    t.ok("nlmBeats" not in y, "C3 オフ＝NLM の拍を持たない")
    rv_click_row(ed, "as written")
    t.eq(_sel(ed), [], "拍8（書いた拍）には物が無い")
    # 付け替えていない難易度には印を出さない
    rv_open_import(ed, [("Expert.txt", "Expert\n8 - x")])
    t.ok(ed.js("!document.querySelector('#dirtyDlg .rvC3Opt') || document.querySelector('#dirtyDlg .rvC3').style.display==='none'"), "付け替えていない難易度＝C3 の印なし")
    ed.js("document.querySelector('#dirtyDlg [data-v=cancel]').click(); true")
    t.no_errors()


def test_review_file_input(t):
    '''ファイルを選んで読む: 複数のファイル（難易度ごと・ファイル名が難易度）・UTF-16（BOM 付き）・大きすぎるファイルは読まない'''
    ed = open_fixture_ready(t, "rich")
    ed.js("""(()=>{ const u16=s=>{ const b=new Uint8Array(2+s.length*2); b[0]=0xFF; b[1]=0xFE; for(let i=0;i<s.length;i++){ b[2+i*2]=s.charCodeAt(i)&255; b[3+i*2]=s.charCodeAt(i)>>8; } return b; };
      const big=new Uint8Array(2*1024*1024+10);
      window._dbg.rt.reviewPanel.importFiles([new File(['4 - from file name'],'Expert.txt'), new File([u16('Hard\\r\\n2 - utf16')],'b.txt'), new File([big],'big.txt')]);
      return true; })()""")
    wait_until(ed, "!!document.querySelector('#dirtyDlg[data-rv=rvImport]')", label="読み込みの確認")
    dlg = ed.js("document.querySelector('#dirtyDlg[data-rv=rvImport]').innerText")
    t.ok("big.txt" in dlg and "大きすぎるため読みません" in dlg, f"大きすぎる: {dlg}")
    ed.js("document.querySelector('#dirtyDlg[data-rv=rvImport] .ddBtns button.pri').click(); true")
    wait_until(ed, "window._dbgApp.review().items.length===2", label="読み込み")
    t.eq(sorted((x["difficulty"], x["text"]) for x in _items(ed)), [("Expert", "from file name"), ("Hard", "utf16")], "ファイル名・UTF-16")
    t.no_errors()


def test_review_paste_dialog(t):
    '''貼り付けて読む: ファイルメニューの入口・貼り付けた文（``` の囲み）・読む→読み込みの確認'''
    ed = open_fixture_ready(t, "rich")
    file_menu(ed, "reviewpaste")
    wait_until(ed, "!!document.querySelector('#dirtyDlg[data-rv=rvPasteDlg] textarea')", label="貼り付けの画面")
    ed.js("(()=>{ const ta=document.querySelector('#dirtyDlg textarea'); ta.value='```\\nExpert\\n4 - pasted\\n```'; return 1; })()")
    ed.js("document.querySelector('#dirtyDlg [data-v=ok]').click(); true")
    wait_until(ed, "!!document.querySelector('#dirtyDlg[data-rv=rvImport]')", label="読み込みの確認")
    ed.js("document.querySelector('#dirtyDlg[data-rv=rvImport] .ddBtns button.pri').click(); true")
    wait_until(ed, "window._dbgApp.review().items.length===1", label="読み込み")
    t.eq((_items(ed)[0]["difficulty"], _items(ed)[0]["text"]), ("Expert", "pasted"), "貼り付けた指摘")
    t.eq(rv(ed)["srcs"][0]["kind"], "paste", "取り込みの種類")
    # 置き換え・消す（Ctrl+Z で戻る）
    rv_import(ed, [(None, "Hard\n2 - replaced")], replace=True)
    t.eq([x["text"] for x in _items(ed)], ["replaced"], "置き換え")
    ed.js("document.querySelector('#rvPanel .rvClear').click(); true")
    wait_until(ed, "!!document.querySelector('#dirtyDlg[data-rv=rvClearDlg]')", label="消すの確認")
    ed.js("document.querySelector('#dirtyDlg [data-v=ok]').click(); true")
    wait_until(ed, "window._dbgApp.review().items.length===0", label="消す")
    ed.move(800, 300); ed.key("z", ctrl=True)
    wait_until(ed, "window._dbgApp.review().items.length===1", label="Undo で戻る")
    t.no_errors()


def _export_open(ed, kind):
    ed.js("document.querySelector('#rvPanel .rvExport').click(); true")
    wait_until(ed, "!!document.querySelector('#dirtyDlg[data-rv=rvExportDlg]')", label="書き出しの画面")
    ed.js(f"(()=>{{ const i=document.querySelector('#dirtyDlg input[name=rvXKind][value={kind}]'); i.checked=true; i.dispatchEvent(new Event('change',{{bubbles:true}})); return 1; }})()")


def _pre(ed):
    return ed.js("document.querySelector('#dirtyDlg .rvXPre').value")


def test_review_export_reply(t):
    '''書き出し（返事を付けた物）: 元の行の後ろに「 - 返事」・書いた拍のまま・拍の無い行も・済みで返事の無い物に「fixed」（選んだ時だけ）・クリップボード・ダウンロード'''
    ed = open_fixture_ready(t, "rich")
    rv_import(ed, [("Mod.txt", "Expert\nOverall fine.\n4 - first\n6, 7 - second\n10-12 - third")])
    items = _items(ed)
    ids = {x["text"]: x["id"] for x in items}
    ed.js(f"""(()=>{{ const r=window._dbg.rt.reviewPanel; const s=r.save(); s.items.find(x=>x.id==='{ids["first"]}').reply='moved'; s.items.find(x=>x.id==='{ids["second"]}').done=true; r.load(s); return 1; }})()""")
    _export_open(ed, "reply")
    want = "Expert\r\nOverall fine.\r\n\r\n4 - first - moved\r\n6, 7 - second\r\n10-12 - third"
    t.eq(_pre(ed), want.replace("\r\n", "\n"), "返事を付けた .txt（欄の表示は LF）")
    ed.js("(()=>{ const i=document.querySelector('#dirtyDlg .rvXFixed'); i.checked=true; i.dispatchEvent(new Event('change',{bubbles:true})); return 1; })()")
    t.ok("6, 7 - second - fixed" in _pre(ed), "済みで返事が無い＝fixed")
    ed.js("Object.defineProperty(navigator,'clipboard',{configurable:true,value:{writeText:async s=>{ window.__clip=s; }}}); true")
    ed.js("[...document.querySelectorAll('#dirtyDlg .ddBtns button')][0].click(); true")
    wait_until(ed, "!!window.__clip", label="クリップボード")
    t.eq(ed.js("window.__clip"), want.replace("6, 7 - second", "6, 7 - second - fixed"), "クリップボードの中身（CRLF＝実物のメモ帳と同じ）")
    t.ok("コピーしました" in ed.js("document.querySelector('#dirtyDlg .rvXStatus').textContent"), "コピーの知らせ")
    ed.js(_CAPTURE_JS)
    ed.js("[...document.querySelectorAll('#dirtyDlg .ddBtns button')][1].click(); true")
    wait_until(ed, "window.__nlmCap.files.length===1", label="ダウンロード")
    f = ed.js("(async()=>{ const f=window.__nlmCap.files[0]; return {name:f.name, text:await f.blob.text()}; })()")
    t.eq(f["name"], "リッチ テスト曲_Mod_reply.txt", "ファイル名（出力フォルダ名が無い＝曲名・読み込んだ物の名前）")
    t.eq(f["text"], ed.js("window.__clip"), "中身（クリップボードと同じ）")
    t.ok("ダウンロードしました" in ed.js("document.querySelector('#dirtyDlg .rvXStatus').textContent"), "ダウンロードの知らせ")
    t.no_errors()


def test_review_export_checks(t):
    '''書き出し（NLM の確かめの結果）: 英語・難易度の見出し・「拍 - [項目] 文 (NLM)」・前書きに数を入れない・重さの印は選べる・BS Map Check は選んだ時だけ'''
    ed = open_fixture_ready(t, "rich")
    ed.js("window._dbg.rt.reviewPanel.open(); true")
    _export_open(ed, "check")
    wait_until(ed, "document.querySelector('#dirtyDlg .rvXPre').value.length>0", timeout=30, label="確かめの結果")
    text = _pre(ed)
    lines = text.split("\n")   # 欄の表示は LF（書き出す物は CRLF）
    t.ok(lines[0].startswith("NLM check results") and not re.search(r"\d", lines[0]), f"前書き（数を含まない）: {lines[0]}")
    t.ok(not re.search(r"[぀-ヿ㐀-鿿]", text), "日本語を含まない（英語で書く）")
    heads = [l for l in lines if l in ("Expert+", "Expert", "Hard", "Normal", "Easy")]
    t.ok(heads and heads == [h for h in ("Expert", "Hard") if h in heads], f"難易度の見出し（難しい方から）: {heads}")
    items = [l for l in lines if re.match(r"^\d", l)]
    t.ok(items and all(re.match(r"^[\d., -]+ - \[R\d+\.[A-Z][\w.]*\] .+ \(NLM\)$", l) for l in items), f"行の形: {items[:5]}")
    t.ok(not any("[BS Map Check]" in l for l in items), "BS Map Check は既定で入れない")
    ed.js("(()=>{ for(const c of ['rvXMc','rvXSev']){ const i=document.querySelector('#dirtyDlg .'+c); i.checked=true; i.dispatchEvent(new Event('change',{bubbles:true})); } return 1; })()")
    wait_until(ed, "document.querySelector('#dirtyDlg .rvXPre').value.includes('[BS Map Check]')", label="BS Map Check も")
    lines2 = _pre(ed).split("\n")
    sev = [l for l in lines2 if re.match(r"^\((X|\?)\) \d", l)]
    t.ok(sev and len(sev) == len([l for l in lines2 if re.search(r"\(NLM\)$", l)]), "全部の行に重さの印")
    t.no_errors()


def test_review_save_txt_native(t):
    '''exe 版: 書き出しの .txt を出力フォルダ（譜面のフォルダの1つ上）へ保存する（app.py の _WRITE_EXTS に .txt）'''
    ed = open_fixture_ready(t, "rich")
    install_fake_pywebview(ed)
    to_info(ed)
    native_queue(ed, "folder", OUT_BASE)
    click_sel(ed, f"{OUT} .oPick", "出力フォルダを選択")
    wait_until(ed, f"window._dbgApp.infoGraph().outs.o1.outDirPath==={json.dumps(OUT_BASE)}", label="出力フォルダの接続")
    rv_import(ed, [("Mod.txt", "Expert\n(S) 4 - first\n5 - second"), ("Hard.txt", "2 - h")])
    _export_open(ed, "reply")
    t.ok(ed.js("document.querySelector('#dirtyDlg .rvXSrcRow').style.display!=='none'"), "読み込んだ物が2つ＝返事を付ける物を選べる")
    t.eq(_pre(ed), "Expert\n(S) 4 - first\n5 - second\n\nHard\n2 - h", "すべて（重さの印は書いてあった行だけ）")
    ed.js("[...document.querySelectorAll('#dirtyDlg .ddBtns button')][1].click(); true")
    wait_until(ed, "/保存しました/.test(document.querySelector('#dirtyDlg .rvXStatus').textContent)", label="保存")
    t.eq(native_file_text(ed, OUT_BASE + "\\リッチ テスト曲_review_reply.txt"), "Expert\r\n(S) 4 - first\r\n5 - second\r\n\r\nHard\r\n2 - h", "出力フォルダに .txt")
    ed.js("(()=>{ const s=document.querySelector('#dirtyDlg .rvXSrc'); s.value=s.options[2].value; s.dispatchEvent(new Event('change',{bubbles:true})); return 1; })()")
    t.eq(_pre(ed), "Hard\n2 - h", "Hard.txt だけ")
    ed.js("[...document.querySelectorAll('#dirtyDlg .ddBtns button')][1].click(); true")
    wait_until(ed, "/Hard_reply/.test(document.querySelector('#dirtyDlg .rvXStatus').textContent)", label="保存（Hard.txt）")
    t.eq(native_file_text(ed, OUT_BASE + "\\リッチ テスト曲_Hard_reply.txt"), "Hard\r\n2 - h", "読み込んだ物の名前のファイル")
    t.no_errors()


# ---- 一覧の文字の大きさ（2026-10-27・利用者の要望「指摘の文字が小さくて読めない」）: 既定 14px・スライダー・Ctrl＋ホイール・bsnm_rvFont ----
_RV_GEOM = """(()=>{ const p=document.getElementById('rvPanel'), q=p.getBoundingClientRect(), s=p.querySelector('.rvFs').getBoundingClientRect(),
  fs=sel=>{ const e=p.querySelector(sel); return e?parseFloat(getComputedStyle(e).fontSize):null; };
  return {font:window._dbgApp.review().font, slider:+p.querySelector('.rvFs').value, text:fs('.rvText'), beat:fs('.rvBeat'), title:fs('.rvTitle'), panel:parseFloat(getComputedStyle(p).fontSize),
    left:q.left, right:q.right, w:q.width, vw:innerWidth, sl:s.left, sr:s.right, sy:s.top+s.height/2, active:document.activeElement===p.querySelector('.rvFs')}; })()"""


def _geom(ed):
    return ed.js(_RV_GEOM)


def _slider_x(g, v):
    """スライダーの値 v のつまみの中心（つまみの幅は約 16px）"""
    return g["sl"] + 8 + (g["sr"] - g["sl"] - 16) * (v - 11) / 9


def test_review_font_size(t):
    '''一覧の文字の大きさ: 既定 14px（指摘の文。他の部品・幅も同じ比率）・スライダーの本物のドラッグ（ドラッグ中に幅が変わってもつまみが逃げない）・
    一覧の上の Ctrl＋ホイール（ただのホイールでは変えない・細かい量はためる）・画面の右からはみ出さない・未保存の判定と履歴に関係しない・
    開き直しても残る（config/settings.json の bsnm_rvFont）'''
    ed = open_fixture_ready(t, "rich")
    install_fake_fs(ed)
    rv_import(ed, [("Mod.txt", "Expert\n" + "\n".join(f"{b} - note number {b} with a fairly long sentence to read" for b in range(1, 30)))])
    file_menu(ed, "save")
    wait_until(ed, "!window._dbgApp.dirty().lamp", label="保存して未保存が消える")
    undo0 = ed.js("window._dbgApp.state().undo")
    g = _geom(ed)
    t.eq((g["font"], g["slider"], g["text"]), (14, 14, 14), "既定は 14px（指摘の文）")
    t.ok(abs(g["beat"] - 14 * 10.5 / 12) < 0.01 and abs(g["title"] - 14 * 13 / 12) < 0.01, f"他の部品は 12px の時の比率のまま: {g}")
    t.ok(abs(g["w"] - 460 * 14 / 12) < 1, f"幅も比率で広がる: {g['w']}")
    t.eq(ed.js("localStorage.getItem('bsnm_rvFont')"), None, "触るまでは記録しない（キーが無い＝既定）")
    # スライダーをドラッグ（本物の入力）。行の左端に置いてあるので、ドラッグ中に幅が広がってもつまみの位置は動かない＝指を離した所の値になる
    ed.drag(_slider_x(g, 14), g["sy"], _slider_x(g, 17), g["sy"] + 20, steps=16)
    wait_until(ed, "window._dbgApp.review().font===17", label="ドラッグで 17")
    t.eq(_geom(ed)["text"], 17, "指を離した所の値（17px）")
    ed.drag(_slider_x(g, 17), g["sy"], g["sr"] + 40, g["sy"] + 30, steps=16)
    wait_until(ed, "window._dbgApp.review().font===20", label="ドラッグで最大")
    g2 = _geom(ed)
    t.eq((g2["slider"], g2["text"]), (20, 20), "最大 20px")
    t.ok(abs(g2["sl"] - g["sl"]) < 0.5, f"スライダーの位置は動かない: {g['sl']} → {g2['sl']}")
    t.ok(abs(g2["w"] - 460 * 20 / 12) < 1, f"幅: {g2['w']}")
    t.ok(not g2["active"], "離したらスライダーのフォーカスを外す（Space 等のショートカットが効く）")
    ed.drag(_slider_x(g2, 20), g2["sy"], g2["sl"] - 40, g2["sy"], steps=16)
    wait_until(ed, "window._dbgApp.review().font===11", label="ドラッグで最小")
    t.eq(_geom(ed)["text"], 11, "最小 11px")
    # Ctrl＋ホイール（一覧の行の上）: 奥へ＝大きく・手前へ＝小さく。ただのホイールは一覧のスクロールで、大きさは変えない
    r = rv_row(ed, "note number 3 ")
    ed.wheel(r["x"], r["y"], -100, ctrl=True); ed.wheel(r["x"], r["y"], -100, ctrl=True)
    wait_until(ed, "window._dbgApp.review().font===13", label="Ctrl＋ホイールで大きく")
    ed.wheel(r["x"], r["y"], 100, ctrl=True)
    wait_until(ed, "window._dbgApp.review().font===12", label="Ctrl＋ホイールで小さく")
    ed.wheel(r["x"], r["y"], -20, ctrl=True)
    ed.wait(0.15)
    t.eq(rv(ed)["font"], 12, "細かい量（タッチパッド）は 1 段に足りるまでためる")
    ed.wheel(r["x"], r["y"], -20, ctrl=True)
    wait_until(ed, "window._dbgApp.review().font===13", label="ためた分で 1 段")
    sc0 = ed.js("document.querySelector('#rvPanel .rvBody').scrollTop")
    ed.wheel(r["x"], r["y"], 200)
    wait_until(ed, f"document.querySelector('#rvPanel .rvBody').scrollTop>{sc0}", label="ただのホイールは一覧のスクロール")
    t.eq(rv(ed)["font"], 13, "ただのホイールでは変えない")
    t.eq(_geom(ed)["slider"], 13, "スライダーも同じ値")
    # 見出しで画面の右端へ動かしてから大きくする: はみ出さないよう左へ寄せる（ホイールはすぐ・スライダーは離した時）
    g = _geom(ed)
    hx, hy = ed.js("(r=>[r.left+60,r.top+r.height/2])(document.querySelector('#rvPanel .rvTitle').getBoundingClientRect())")
    ed.drag(hx, hy, hx + (g["vw"] - 12 - g["right"]), hy, steps=8)
    g = _geom(ed)
    t.ok(g["vw"] - 20 < g["right"] <= g["vw"], f"右端へ動かした: {g}")
    r = rv_row(ed, "note number 3 ")
    for _ in range(3):
        ed.wheel(r["x"], r["y"], -100, ctrl=True)
    wait_until(ed, "window._dbgApp.review().font===16", label="右端で大きく")
    g = _geom(ed)
    t.ok(g["right"] <= g["vw"] and g["left"] >= 0, f"Ctrl＋ホイール: 画面からはみ出さない: {g}")
    ed.drag(_slider_x(g, 16), g["sy"], g["sr"] + 40, g["sy"], steps=12)
    wait_until(ed, "window._dbgApp.review().font===20", label="右端でスライダーを最大")
    g = _geom(ed)
    t.ok(g["right"] <= g["vw"] and g["left"] >= 0, f"スライダー: 離したら画面の中へ寄せる: {g}")
    # プロジェクトには入れない＝未保存にならない・履歴に積まない
    t.ok(ed.js("window._dbgApp.dirty().same"), "保存した時と同じ（未保存の判定に関係しない）")
    t.eq(ed.js("window._dbgApp.state().undo"), undo0, "履歴に積まない")
    # 開き直しても残る: localStorage を消して開き直す＝config/settings.json から戻る
    t.eq(ed.js("localStorage.getItem('bsnm_rvFont')"), "20", "記録")
    wait_mirrored(ed, "bsnm_rvFont")
    ed.reload(clear_storage=True)
    ed.js(LIGHT_RENDER_JS)
    wait_until(ed, "!document.getElementById('bootCover')", label="起動中の覆いが外れる")
    file_menu(ed, "reviewlist")
    wait_until(ed, "window._dbgApp.review().open", label="一覧を開く")
    t.eq(rv(ed)["font"], 20, "開き直しても 20px")
    t.eq(ed.js("parseFloat(getComputedStyle(document.getElementById('rvPanel')).fontSize)"), 20, "パネルの文字")
    t.eq(ed.js("+document.querySelector('#rvPanel .rvFs').value"), 20, "スライダーの値")
    t.no_errors()

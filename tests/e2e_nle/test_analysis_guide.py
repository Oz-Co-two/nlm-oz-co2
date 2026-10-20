"""解析が終わった時の「次にやること」の案内と、溝の［🧩 クリップを作る］（2026-10-20・js/analysis/song-analysis.js の showGuide / syncClipsBtn）。
利用者の要望: 「⋯」を開かないとクリップを作る入口が分からない。ただ区切りの良し悪しは曲を聞かないと決められないので、いきなりクリップを作る画面は出さず、
確かめ方とボタンの場所（画像）を案内する。テストの環境は既定で案内を出さない（tools/cdp.py の Editor.TEST_SETTINGS＝bsnm_anaGuide '0'）ので、
ここでは localStorage の bsnm_anaGuide を消して（キーが無い＝出す）確かめる。解析の応答は偽物（tests/_lib/analysis_helpers.py）。素材 basic＝BPM 120・32拍"""
import json
import re

from analysis_helpers import (GUIDE, STRUCT, TEMPO, TEMPO_SAME, ana, ana_go, ana_mock, center_of, click_sel, clips_ok, dialog_choose, guide_dialog, guide_on,
                              run_analysis, start_from_menu, status_seq, wait_band, wait_clips_dialog, wait_guide, wait_tempo_dialog)
from e2e_helpers import project, wait_until
from nle_helpers import nle, nle_mouse, open_nle, redo, take_errors, undo

PURPLE = "rgb(129, 96, 227)"     # --accent（作る前）
MADE = "rgb(70, 60, 106)"        # 作った後（#463c6a・彩度を落として暗く沈めた紫）
MADE_HOVER = "rgb(86, 74, 132)"  # 作った後の hover（#564a84）
MADE_TIP = "この解析の結果からクリップを作成済みです。もう一度押すと、新しいレーンにもう1組作ります（帯のメニューの「クリップを作る…」と同じです）"

STEPS_JA = [
    "曲を再生して、帯の区切りが曲に合っているかを耳で確かめてください。上の段＝セクション（大きい区切り。イントロ・Aメロ・サビ…）、下の段＝細かい区切り（A・B・C…）です。",
    "どちらの区切りで打つかを決めます。帯をクリックするとその位置へ移動し、セクションの名前はダブルクリックで付け直せます。",
    "決めたら、帯の左の［🧩 クリップを作る］を押します。選んだ区切りどおりに空のクリップを新しいレーンへ作り、同じ番号のくり返しは自動でリンクします（両方を選べば両方作れます）。",
]
STALE_TOAST = "⚠ 目盛り（BPM・無音追加・テンポパート・Music の配置）が解析した時と変わったため、帯の区間が今の拍と合っていない可能性があります。解析し直してからクリップを作ってください"


def _open(t, fx="basic"):
    ed = open_nle(t, fx)
    wait_until(ed, "!document.getElementById('bootCover')&&window._dbgApp.analysis().startBtn", label="［曲を解析］が出る")
    return ed


def _guiding(ed):
    return ed.js(f"!!document.querySelector('{GUIDE}')")


def _no_guide(ed, label):
    """しばらく待っても出ない（待ちの状態にもなっていない）"""
    ed.wait(0.8)
    a = ana(ed)
    if _guiding(ed) or a["guide"] or a["guideWait"]:
        raise AssertionError(f"{label}: 解析が終わった時の案内が出た（または出す待ちになった）")


def _stat(ed):
    return ed.js("document.getElementById('stat').textContent")


def _toast(ed):
    return ed.js("(e=>e.style.display==='none'?'':e.textContent)(document.getElementById('errToast'))")


def _btn(ed):
    """溝の［クリップを作る］: 見えているか・文字・ツールチップ・色・文字が切れていないか・位置（スペクトログラムの箱からの相対）"""
    return ed.js("""(()=>{ const b=document.getElementById('anaClipsBtn'), s=document.getElementById('specPane').getBoundingClientRect(), r=b.getBoundingClientRect();
      return {vis:b.checkVisibility(), text:b.textContent, title:b.title, bg:getComputedStyle(b).backgroundColor, fit:b.scrollWidth<=b.clientWidth,
        x0:Math.round(r.left-s.left), x1:Math.round(r.right-s.left), y0:Math.round(r.top-s.top), y1:Math.round(r.bottom-s.top),
        act:(a=>({x1:Math.round(a.right-s.left), y1:Math.round(a.bottom-s.top)}))(document.getElementById('anaAct').getBoundingClientRect())}; })()""")


def _close_guide(ed, how):
    if how == "esc":
        ed.key("Escape")
    else:
        click_sel(ed, f"{GUIDE} .ddBtns button.pri")
    wait_until(ed, f"!document.querySelector('{GUIDE}')", label="案内が閉じる")


def test_clips_button_in_gutter(t):
    '''結果がある時だけ、帯の溝（「構成」「細かい区切り」の下）に［🧩 クリップを作る］（配置モードと同じ紫・白い文字・切れない）。帯の溝だけを下へ延ばす＝
    スペクトログラムの高さ・NLE のレーンの表示窓は変わらない。押すと確認の画面（帯のメニューの「クリップを作る…」と同じ）。結果を消すと隠れる'''
    ed = _open(t)
    vp0 = ed.js("window._dbgApp.nle().vp")
    t.eq((_btn(ed)["vis"], ana(ed)["clipsBtn"]["shown"]), (False, False), "結果が無い時は出ない")
    run_analysis(ed, None, tempo=TEMPO_SAME)
    t.eq(ana(ed)["guideOn"], False, "テストの環境は既定で案内を出さない（cdp.Editor.TEST_SETTINGS）")
    _no_guide(ed, "案内を出さない設定")
    b = _btn(ed)
    t.eq((b["vis"], b["text"], b["bg"], b["fit"]), (True, "🧩 クリップを作る", "rgb(129, 96, 227)", True), "溝に紫の［🧩 クリップを作る］（文字は切れない）")
    t.ok(b["x0"] >= 0 and b["x1"] <= 128 and b["y0"] >= 40 and b["act"] == {"x1": 129, "y1": 66}, f"帯の溝（幅128px）を下へ 26px 延ばした所: {b}")
    t.eq(b["title"], "帯の区切り（セクション／細かい区切り）どおりに空のクリップを新しいレーンへ作ります（同じ番号のくり返しは自動でリンク）。帯のメニューの「クリップを作る…」と同じです",
         "ツールチップ")
    a = ana(ed)
    t.eq((a["canvasH"], a["specH"]), (40, 54), "帯の高さ・スペクトログラムの高さは変わらない")
    t.eq(ed.js("window._dbgApp.nle().vp"), vp0, "NLE のレーンの表示窓は変わらない")
    click_sel(ed, "#anaClipsBtn")
    wait_clips_dialog(ed)
    t.eq(ed.js("document.querySelector('#dirtyDlg[data-ana=clips] .lkTitle').textContent"), "解析からクリップを作る", "押すと確認の画面")
    ed.key("Escape")
    wait_until(ed, "!document.querySelector('#dirtyDlg[data-ana=clips]')", label="確認の画面を閉じる")
    # 結果を消すと隠れる
    click_sel(ed, "#anaMenuBtn")
    ed.js("[...document.querySelectorAll('#ctxmenu > button')].find(b=>b.textContent==='解析の結果を消す').click();true")
    wait_until(ed, "!window._dbgApp.analysis().shown", label="結果を消す")
    t.eq((_btn(ed)["vis"], ana(ed)["clipsBtn"]["shown"]), (False, False), "結果を消すと隠れる")
    t.no_errors()


def test_clips_button_stale(t):
    '''目盛りが変わった（BPM を変えた）時は薄くなり、ツールチップに理由。押すと確認の画面は出さず、帯のメニューと同じ理由を知らせる。目盛りを戻すと元に戻る'''
    ed = _open(t)
    run_analysis(ed, None, tempo=TEMPO_SAME)
    click_sel(ed, "#bpmField .bfA[data-k=up]")
    wait_until(ed, "window._dbgApp.analysis().clipsBtn.stale", label="目盛りが変わった")
    t.eq(_btn(ed)["title"], "目盛り（BPM・無音追加・テンポパート・Music の配置）が解析した時と変わったため、今はクリップを作れません。解析し直してから押してください",
         "ツールチップに理由")
    t.ok(float(ed.js("getComputedStyle(document.getElementById('anaClipsBtn')).opacity")) < 0.6, "薄い")
    click_sel(ed, "#anaClipsBtn")
    wait_until(ed, "document.getElementById('errToast').style.display!=='none'", label="断りの知らせ")
    t.eq(_toast(ed), STALE_TOAST, "帯のメニューと同じ理由")
    t.ok(not ed.js("!!document.querySelector('#dirtyDlg[data-ana=clips]')"), "確認の画面は出ない")
    take_errors(ed, "目盛り（BPM")
    click_sel(ed, "#bpmField .bfA[data-k=dn]")
    wait_until(ed, "!window._dbgApp.analysis().clipsBtn.stale", label="目盛りを戻す")
    t.ok(float(ed.js("getComputedStyle(document.getElementById('anaClipsBtn')).opacity")) == 1, "元の濃さ")
    t.no_errors()


def _make_clips(ed):
    """溝の［クリップを作る］→ 確認の画面（既定＝セクション）→［作る］"""
    click_sel(ed, "#anaClipsBtn")
    wait_clips_dialog(ed)
    clips_ok(ed)
    wait_until(ed, "window._dbgApp.nle().editOnly===0", label="作った")


def _reopen(ed, pj):
    ed.js(f"(async()=>{{ await window._dbg.rt.applyProject({json.dumps(pj, ensure_ascii=False)}); return 1; }})()")
    wait_until(ed, "window._dbgApp.analysis().shown&&window._dbgApp.analysis().clipsBtn.shown", label="開き直す")
    ed.wait(0.2)


def test_clips_button_made(t):
    '''この解析の結果から一度クリップを作った後は、溝の［クリップを作る］を彩度を落とした暗い紫にする（2026-10-20・利用者の要望: 紫が目障り。もう一度押せることは
    分かるように枠・文字・hover は残す）。印は解析の結果と一緒に保存（analysis.made）・開き直しても暗いまま・ファイルの true 以外は受け付けない。
    作る操作の Ctrl+Z で印も戻る（やり直しで暗く）・未保存の判定（保存の中身）も作る前と同じに戻る。解析し直すと元の紫'''
    ed = _open(t)
    run_analysis(ed, None, tempo=TEMPO_SAME)
    b = _btn(ed)
    t.eq((b["bg"], ana(ed)["clipsBtn"]["made"], "made" in project(ed)["analysis"]), (PURPLE, False, False), "作る前は紫（保存の中身に印は無い）")
    ana0 = project(ed)["analysis"]
    lanes0 = nle(ed)["lanes"]["n"]
    _make_clips(ed)
    wait_until(ed, "window._dbgApp.analysis().clipsBtn.made", label="作った後の印")
    b = _btn(ed)
    t.eq((b["bg"], b["text"], b["fit"], b["title"]), (MADE, "🧩 クリップを作る", True, MADE_TIP), "作った後は暗い紫（文字は同じ・ツールチップは作成済み）")
    t.eq(ed.js("getComputedStyle(document.getElementById('anaClipsBtn')).cursor"), "pointer", "押せるボタンのまま（指のカーソル）")
    t.eq(project(ed)["analysis"].get("made"), True, "印は解析の結果と一緒に保存")
    # hover で明るくなる（押せそうに見える）
    ed.move(*center_of(ed, "#anaClipsBtn")); ed.wait(0.2)
    t.eq(_btn(ed)["bg"], MADE_HOVER, "hover で明るく")
    nle_mouse(ed); ed.wait(0.1)
    # もう一度押せる（確認の画面が出る）
    click_sel(ed, "#anaClipsBtn")
    wait_clips_dialog(ed)
    ed.key("Escape")
    wait_until(ed, "!document.querySelector('#dirtyDlg[data-ana=clips]')", label="確認の画面を閉じる")
    # 作る操作の Ctrl+Z で印も戻る・やり直しでまた暗く
    nle_mouse(ed); undo(ed)
    wait_until(ed, f"window._dbgApp.nle().lanes.n==={lanes0}", label="Ctrl+Z でクリップを作る前へ")
    wait_until(ed, "!window._dbgApp.analysis().clipsBtn.made", label="印も戻る")
    t.eq((_btn(ed)["bg"], _btn(ed)["title"].startswith("帯の区切り")), (PURPLE, True), "紫に戻る")
    t.eq(project(ed)["analysis"], ana0, "保存の中身（未保存の判定に入る解析の結果）も作る前と同じ")
    nle_mouse(ed); redo(ed)
    wait_until(ed, f"window._dbgApp.nle().lanes.n==={lanes0 + 1}&&window._dbgApp.analysis().clipsBtn.made", label="やり直しで暗く")
    pj = project(ed)
    # 解析し直すと元の紫（開き直すと音源が外れるので、先に）
    ana_mock(ed, tempo=TEMPO_SAME)
    start_from_menu(ed)
    wait_until(ed, "(a=>!a.running&&a.shown&&!a.clipsBtn.made)(window._dbgApp.analysis())", label="解析し直した")
    t.eq((_btn(ed)["bg"], "made" in project(ed)["analysis"]), (PURPLE, False), "解析し直すと紫に戻る（新しい結果に印は無い）")
    # 保存して開き直しても暗いまま
    _reopen(ed, pj)
    t.eq((ana(ed)["clipsBtn"]["made"], _btn(ed)["bg"], project(ed)["analysis"].get("made")), (True, MADE, True), "開き直しても暗いまま")
    # ファイル由来: true 以外（文字列・数）は受け付けない
    for bad in ("yes", 1):
        pj2 = json.loads(json.dumps(pj)); pj2["analysis"]["made"] = bad
        _reopen(ed, pj2)
        t.eq((ana(ed)["clipsBtn"]["made"], "made" in project(ed)["analysis"]), (False, False), f"made={bad!r} は受け付けない")
    t.no_errors()


def test_guide_after_analysis(t):
    '''「曲を解析」で構成の解析が終わって帯が出た時（テンポの確認の画面の後）に案内が出る（題・確かめ方の3つの手順・ボタンの場所の画像（赤枠）と説明・
    「次から出さない」・［わかった］）。Enter・Space では閉じない（急に出るため）。Esc で閉じると溝のボタンが少しの間光る。解析し直した時も出る'''
    ed = _open(t)
    guide_on(ed)
    ana_mock(ed)
    start_from_menu(ed)
    wait_tempo_dialog(ed)
    t.ok(not _guiding(ed), "テンポの確認の画面の間は出ない")
    dialog_choose(ed, "none")
    wait_band(ed)
    wait_guide(ed)
    wait_until(ed, f"(i=>i&&i.complete)(document.querySelector('{GUIDE} img'))", label="画像の読み込み")
    d = guide_dialog(ed)
    t.eq(d["title"], "曲の解析が終わりました ― 次にやること", "題")
    t.eq(d["steps"], STEPS_JA, "確かめ方とボタン（大きい区切り・細かい区切り・両方も作れる）")
    t.eq(d["img"], {"src": "guide/ana-clips-btn-ja.png", "ok": True, "w": 540, "alt": "解析の帯の左の溝にある［クリップを作る］のボタン（赤枠）"}, "ボタンの場所の画像（日本語版）")
    t.eq(d["cap"], "赤枠＝［🧩 クリップを作る］（帯の左の溝・「構成」の下）", "画像の説明")
    t.eq((d["never"], d["neverOn"]), ("次から出さない（環境設定で戻せます）", False), "「次から出さない」（既定は外れている）")
    t.eq([(b["v"], b["text"], b["pri"]) for b in d["btns"]], [("ok", "わかった", True)], "ボタン")
    t.eq(ana(ed)["clipsBtn"]["shown"], True, "溝のボタンはもう出ている")
    for k in ("Enter", " "):
        ed.key(k); ed.wait(0.3)
        t.ok(_guiding(ed), f"{k!r} では閉じない")
    t.ok(not ed.js("!!document.querySelector('#dirtyDlg[data-ana=clips]')"), "いきなりクリップを作る画面は出さない")
    _close_guide(ed, "esc")
    t.eq((ana(ed)["clipsBtn"]["glow"], ana(ed)["guideOn"]), (True, True), "Esc で閉じる→溝のボタンが光る（設定はそのまま）")
    wait_until(ed, "!window._dbgApp.analysis().clipsBtn.glow", timeout=5, label="少しの間で光るのをやめる")
    # 解析し直した時も出る→［わかった］
    ana_mock(ed, tempo=TEMPO_SAME)
    start_from_menu(ed)
    wait_guide(ed)
    _close_guide(ed, "ok")
    t.eq(ana(ed)["clipsBtn"]["glow"], True, "［わかった］でも光る")
    t.no_errors()


def test_guide_not_on_open_cancel_error(t):
    '''出さない: 保存した結果（プロジェクト）を開いた時・解析をやめた時・解析が失敗した時'''
    ed = _open(t)
    run_analysis(ed, None, tempo=TEMPO_SAME)   # 案内を出さない設定のまま結果を作る
    guide_on(ed)
    # やめた（構成の解析の途中）
    ana_mock(ed, tempo=TEMPO_SAME, status_s1=[{"ok": True, "state": "running", "stage": "structure", "progress": 0.3},
                                              {"waitFor": "s", "then": status_seq("structure", STRUCT)[-1]}])
    start_from_menu(ed)
    wait_until(ed, "(a=>a.running&&a.running.stage==='structure')(window._dbgApp.analysis())", label="構成の解析中")
    click_sel(ed, "#anaMsg .amBtn")
    wait_until(ed, "!window._dbgApp.analysis().running", label="やめた")
    ana_go(ed, "s")
    _no_guide(ed, "やめた時")
    # 失敗した
    ana_mock(ed, tempo=TEMPO_SAME, status_s1=[{"ok": True, "state": "error", "stage": "structure", "progress": 0.3, "result": None, "error": "failed"}])
    start_from_menu(ed)
    wait_until(ed, "!window._dbgApp.analysis().running&&document.getElementById('errToast').style.display!=='none'", label="失敗")
    take_errors(ed, "曲の解析に失敗しました")
    _no_guide(ed, "失敗した時")
    # 保存した結果（プロジェクト）を開く（開くと音源は外れるので最後に）
    pj = project(ed)
    t.ok(pj.get("analysis"), "保存する中身に解析の結果がある")
    ed.js(f"(async()=>{{ await window._dbg.rt.applyProject({json.dumps(pj, ensure_ascii=False)}); return 1; }})()")
    wait_until(ed, "window._dbgApp.analysis().shown&&window._dbgApp.analysis().clipsBtn.shown", label="保存した結果を開く")
    _no_guide(ed, "保存した結果を開いた時")
    t.no_errors()


def test_guide_waits_for_other_dialog(t):
    '''解析が終わった時に他の画面（環境設定）が出ていれば重ねずに待ち、閉じたら出す'''
    ed = _open(t)
    guide_on(ed)
    ana_mock(ed, tempo=TEMPO_SAME, status_s1=[{"waitFor": "s", "then": status_seq("structure", STRUCT)[-1]}])
    start_from_menu(ed)
    wait_until(ed, "(a=>a.running&&a.running.stage==='structure')(window._dbgApp.analysis())", label="構成の解析中")
    click_sel(ed, "#mbSettings")
    wait_until(ed, "getComputedStyle(document.getElementById('settingsBg')).display!=='none'", label="環境設定")
    ana_go(ed, "s")
    wait_until(ed, "!window._dbgApp.analysis().running&&window._dbgApp.analysis().shown", label="解析が終わる")
    ed.wait(0.6)
    t.eq((_guiding(ed), ana(ed)["guideWait"]), (False, True), "環境設定が出ている間は出さずに待つ")
    click_sel(ed, "#settingsClose")
    wait_guide(ed)
    _close_guide(ed, "ok")
    t.no_errors()


def test_guide_never_and_prefs(t):
    '''「次から出さない」で bsnm_anaGuide='0'（環境設定のチェックも外れる・下に知らせ）→ 解析し直しても出ない。環境設定の「曲の解析」の
    「解析が終わったら、次の手順を案内する」で戻すと '1' になり、また出る'''
    ed = _open(t)
    guide_on(ed)
    run_analysis(ed, None, tempo=TEMPO_SAME)
    wait_guide(ed)
    click_sel(ed, "#anaGuideNever")
    _close_guide(ed, "ok")
    t.eq(ed.js("localStorage.getItem('bsnm_anaGuide')"), "0", "出さない設定を保存")
    t.eq(_stat(ed), "解析が終わった時の案内を出さないようにしました（環境設定の「アプリケーション設定」で戻せます）", "下の知らせ")
    t.eq(ed.js("document.getElementById('anaGuideOn').checked"), False, "環境設定のチェックも外れる")
    t.eq(ana(ed)["clipsBtn"]["glow"], True, "閉じた時はボタンが光る")
    ana_mock(ed, tempo=TEMPO_SAME)
    start_from_menu(ed)
    wait_until(ed, "!window._dbgApp.analysis().running", label="解析し直す")
    _no_guide(ed, "次から出さない")
    # 環境設定で戻す（「曲の解析」のまとまりの中）
    click_sel(ed, "#mbSettings")
    wait_until(ed, "!!document.getElementById('anaGuideOn').checkVisibility()", label="環境設定のアプリケーション設定")
    t.eq(ed.js("document.getElementById('anaGuideOn').closest('.row').querySelector('[data-i18n=\"set.anaAsk\"]').textContent"), "曲の解析", "「曲の解析」のまとまり")
    t.eq(ed.js("document.querySelector('[data-i18n=\"set.anaGuideOn\"]').textContent"), "解析が終わったら、次の手順を案内する", "チェックの文")
    ed.js("document.getElementById('anaGuideOn').scrollIntoView({block:'center'});true")   # 環境設定の箱の中でスクロールの先にあることがある
    ed.wait(0.1)
    click_sel(ed, "#anaGuideOn")
    t.eq((ed.js("localStorage.getItem('bsnm_anaGuide')"), ana(ed)["guideOn"]), ("1", True), "戻した")
    click_sel(ed, "#settingsClose")
    ana_mock(ed, tempo=TEMPO_SAME)
    start_from_menu(ed)
    wait_guide(ed)
    _close_guide(ed, "ok")
    t.no_errors()


def test_guide_english(t):
    '''英語表示: 案内（題・手順・画像は英語版・説明・「次から出さない」・ボタン）・溝のボタン（切れない）・ツールチップ・環境設定の項目。日本語が残らない'''
    from nlmtest import LIGHT_RENDER_JS
    ed = t.fresh()
    ed.js("localStorage.setItem('bsnm_lang','en');true")
    ed.wait(0.6)
    ed.reload(clear_storage=False)
    ed.js(LIGHT_RENDER_JS)
    wait_until(ed, "!document.getElementById('bootCover')&&document.getElementById('mFileBtn').textContent.trim()==='File'", label="英語で起動")
    ed.load_fixture("basic", settle=0.3)
    wait_until(ed, "window._dbgApp.analysis().startBtn", label="［Analyze song］")
    guide_on(ed)
    run_analysis(ed, "none", tempo=TEMPO)
    wait_guide(ed)
    wait_until(ed, f"(i=>i&&i.complete)(document.querySelector('{GUIDE} img'))", label="画像の読み込み")
    d = guide_dialog(ed)
    t.eq(d["title"], "Analysis complete — what to do next", "題")
    t.eq(len(d["steps"]), 3, "手順は3つ")
    t.ok(d["steps"][2].startswith("Then press [🧩 Create clips] at the left of the band."), f"ボタンの手順: {d['steps'][2]}")
    t.eq((d["img"]["src"], d["img"]["ok"]), ("guide/ana-clips-btn-en.png", True), "画像は英語版")
    t.eq(d["cap"], "Red frame = [🧩 Create clips] (left gutter of the band, below \"Sections\")", "画像の説明")
    t.eq(d["never"], "Don't show this again (you can turn it back on in Preferences)", "次から出さない")
    t.eq([b["text"] for b in d["btns"]], ["Got it"], "ボタン")
    t.ok(not re.search(r"[぀-ゟ゠-ヺー-ヿ㐀-䶿一-鿿]", d["text"] + d["img"]["alt"]), f"日本語が残らない: {d['text']}")
    click_sel(ed, "#anaGuideNever")
    _close_guide(ed, "ok")
    t.eq(_stat(ed), "The guide won't be shown when an analysis finishes (turn it back on in Preferences > Application)", "下の知らせ")
    b = _btn(ed)
    t.eq((b["text"], b["fit"]), ("🧩 Create clips", True), "溝のボタン（切れない）")
    t.ok(b["title"].startswith("Creates empty clips on a new lane"), f"ツールチップ: {b['title']}")
    t.eq(ed.js("document.querySelector('[data-i18n=\"set.anaGuideOn\"]').textContent"), "Show the next steps when an analysis finishes", "環境設定の項目")
    t.no_errors()

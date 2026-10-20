"""曲を取り込んだ時の「曲を解析しますか？」（2026-10-20・js/analysis/song-analysis.js の songLoaded・editor-app.js の anaAfterLoad）。
テストの環境は既定で聞かない（tools/cdp.py の Editor.TEST_SETTINGS＝bsnm_anaAsk '0'）ので、ここでは localStorage の bsnm_anaAsk を消して
（キーが無い＝聞く）確かめる。解析の応答は偽物（tests/_lib/analysis_helpers.py）。素材 basic は BPM 120・音源 basic.wav（16秒）"""
import json
import re

from analysis_helpers import (ASK, TEMPO_SAME, ana, ana_calls, ana_go, ana_mock, ask_on, click_sel, load_song_media, run_analysis, status_seq,
                              wait_band)
from e2e_helpers import wait_until
from nle_helpers import open_nle, take_errors

# exe 版の音源の読み込み（pywebview の pick_song_file / read_song_file）だけの偽物。pick はキューの先頭を返す（空＝キャンセル）
_NATIVE_JS = r"""(async()=>{ const buf=await (await fetch('tools/fixtures/basic.wav',{cache:'no-store'})).arrayBuffer();
  let s=''; const u=new Uint8Array(buf); for(let i=0;i<u.length;i+=0x8000) s+=String.fromCharCode.apply(null,u.subarray(i,i+0x8000));
  const b64=btoa(s), N=window.__natAsk={calls:[],queue:[]};
  window.pywebview={api:{ async pick_song_file(){ N.calls.push('pick'); return N.queue.shift()||null; },
    async read_song_file(p){ N.calls.push('read:'+p); return {ok:true,name:String(p).split(/[\\/]/).pop(),data:b64}; } }};
  return true; })()"""


def _open(t, fx="basic"):
    ed = open_nle(t, fx)
    wait_until(ed, "!document.getElementById('bootCover')&&window._dbgApp.analysis().startBtn", label="［曲を解析］が出る")
    return ed


_ask_on = ask_on
_load_media = load_song_media   # MEDIA から Music へ入れるのと同じ経路（loadSongFromItem）。中身は basic.wav


def _asking(ed):
    return ed.js(f"!!document.querySelector('{ASK}')")


def _wait_ask(ed):
    wait_until(ed, f"!!document.querySelector('{ASK}')", label="「曲を解析しますか？」")


def _no_ask(ed, label):
    """しばらく待っても出ない（待ちの状態にもなっていない）"""
    ed.wait(0.8)
    a = ana(ed)
    if _asking(ed) or a["ask"] or a["askWait"]:
        raise AssertionError(f"{label}: 「曲を解析しますか？」が出た（または出す待ちになった）")


def _dialog(ed):
    return ed.js(f"""(d=>d&&({{title:d.querySelector('.aaHead').textContent, lead:d.querySelector('.aaLead').textContent,
      points:[...d.querySelectorAll('.aaList li')].map(e=>e.textContent), note:d.querySelector('.aaNote').textContent,
      never:d.querySelector('.aaChk').textContent, neverOn:d.querySelector('#anaAskNever').checked,
      btns:[...d.querySelectorAll('.ddBtns button')].map(b=>({{v:b.dataset.v,text:b.textContent,pri:b.classList.contains('pri')}})),
      text:d.innerText}}))(document.querySelector('{ASK}'))""")


def _press(ed, v):
    click_sel(ed, f"{ASK} .ddBtns button[data-v={v}]")
    wait_until(ed, f"!document.querySelector('{ASK}')", label="「曲を解析しますか？」が閉じる")


def _stat(ed):
    return ed.js("document.getElementById('stat').textContent")


def test_ask_after_media_load_and_buttons(t):
    '''MEDIA から Music へ（loadSongFromItem）新しく曲を取り込むと「曲を解析しますか？」が出る（題・解析すると何ができるかの箇条・後で解析する入口・
    「次から聞かない」・［解析する］［今はしない］）。Enter・Space では押されない（急に出るため）・Esc＝今はしない・［今はしない］＝何も送らない'''
    ed = _open(t)
    t.eq(ana(ed)["askOn"], False, "テストの環境は既定で聞かない（cdp.Editor.TEST_SETTINGS）")
    _load_media(ed)
    _no_ask(ed, "聞かない設定では出ない")
    _ask_on(ed)
    t.eq(_load_media(ed), True, "新しく取り込んだ")
    _wait_ask(ed)
    d = _dialog(ed)
    t.eq((d["title"], d["lead"]), ("曲を解析しますか？", "曲を解析すると、次のことができます。"), "題と前置き")
    t.eq(d["points"], [
        "BPM と無音追加（曲の頭のずれ）を推定して提案します（今の設定と違う時だけ確認が出ます。自動では変えません）",
        "曲の構成（イントロ・Aメロ・サビ…と細かい区切り）を NLE の帯で表示します（クリックでその位置へ・名前の付け直し・マーカーへ書き出し）",
        "構成から空のクリップをまとめて作れます（同じくり返しは自動でリンク＝1回目のサビを打てば2回目以降にも入ります）",
        "1曲 30秒〜1分。解析中も編集できます。解析は PC の中で行い、曲をネットへ送りません"], "解析すると何ができるか")
    t.eq(d["note"], "後で解析する時は、スペクトログラムの左の［🎼 曲を解析］か、ファイルメニューの「曲を解析（テンポ・構成）…」から。", "後で解析する入口")
    t.eq((d["never"], d["neverOn"]), ("次から聞かない（環境設定で戻せます）", False), "「次から聞かない」（既定は外れている）")
    t.eq([(b["v"], b["text"], b["pri"]) for b in d["btns"]], [("go", "解析する", True), ("later", "今はしない", False)], "ボタン")
    t.eq(ed.js("getComputedStyle(document.getElementById('anaStartBtn')).backgroundColor"), "rgb(129, 96, 227)", "［曲を解析］は配置モードと同じ紫（--accent）")
    ana_mock(ed, tempo=TEMPO_SAME)
    for k in ("Enter", " "):
        ed.key(k); ed.wait(0.3)
        t.ok(_asking(ed), f"{k!r} では何も押さない")
    t.eq(ana_calls(ed), [], "まだ何も送らない")
    ed.key("Escape")
    wait_until(ed, f"!document.querySelector('{ASK}')", label="Esc で閉じる")
    ed.wait(0.3)
    t.eq((ana_calls(ed), ana(ed)["running"], ana(ed)["askOn"]), ([], None, True), "Esc＝今はしない（何も送らない・設定はそのまま）")
    # もう一度（別の曲）→［今はしない］
    _load_media(ed, "song3.wav")
    _wait_ask(ed)
    _press(ed, "later")
    ed.wait(0.3)
    t.eq((ana_calls(ed), ana(ed)["running"], ana(ed)["startBtn"]), ([], None, True), "［今はしない］＝何も送らない・溝の［曲を解析］はそのまま")
    t.no_errors()


def test_ask_analyze_starts(t):
    '''［解析する］＝［曲を解析］と同じ処理（音源を送る→テンポ→構成→帯）。取り込んだ曲（song2.wav）を送る'''
    ed = _open(t)
    _ask_on(ed)
    _load_media(ed)
    _wait_ask(ed)
    ana_mock(ed, tempo=TEMPO_SAME)
    _press(ed, "go")
    wait_band(ed)
    t.eq(len(ana_calls(ed, "upload")), 1, "音源を1回送った")
    t.eq(ana(ed)["data"]["grid"]["song"], "song2.wav", "取り込んだ曲で解析した")
    t.no_errors()


def test_ask_file_paths(t):
    '''「音楽ファイルを読み込む…」（ブラウザのファイル選択・exe 版のネイティブのダイアログ）でも出る。曲データを読み込む（一括読込）は全部読み込んだ後に1回だけ出る'''
    ed = _open(t)
    _ask_on(ed)
    # ブラウザのファイル選択（showOpenFilePicker を偽物に）
    ed.js("""(async()=>{ const blob=await (await fetch('tools/fixtures/basic.wav',{cache:'no-store'})).blob();
      const f=new File([blob],'picked.wav',{type:'audio/wav'});
      window.showOpenFilePicker=async()=>[{name:f.name,kind:'file',getFile:async()=>f}]; return true; })()""")
    click_sel(ed, "#mFileBtn"); click_sel(ed, "#mFileMenu button[data-act=loadsong]")
    wait_until(ed, "JSON.parse(window._dbg.rt.buildProjectText()).graph.song.name==='picked.wav'", label="ファイル選択で読み込む")
    _wait_ask(ed)
    _press(ed, "later")
    # exe 版（pywebview のダイアログ）
    ed.js(_NATIVE_JS)
    ed.js("window.__natAsk.queue.push('C:\\\\NLMTest\\\\Music\\\\native.wav');true")
    click_sel(ed, "#mFileBtn"); click_sel(ed, "#mFileMenu button[data-act=loadsong]")
    wait_until(ed, "JSON.parse(window._dbg.rt.buildProjectText()).graph.song.name==='native.wav'", label="ネイティブのダイアログで読み込む")
    _wait_ask(ed)
    _press(ed, "later")
    t.eq(ed.js("window.__natAsk.calls"), ["pick", "read:C:\\NLMTest\\Music\\native.wav"], "ネイティブのダイアログから読んだ")
    ed.js("delete window.pywebview; true")
    # 曲データを読み込む（音源の無い新規から）: 音源・譜面・テンポパートを全部読んだ後に出る
    ed.js("(async()=>{ await window._dbg.rt.applyProject(null); return 1; })()")
    wait_until(ed, "!window._dbgApp.nle().music.audio", label="新規（音源なし）")
    import importlib.util
    from pathlib import Path
    p = Path(__file__).resolve().parents[2] / "tools" / "fixtures" / "make_fixtures.py"
    spec = importlib.util.spec_from_file_location("nlm_make_fixtures", p)
    mf = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mf)
    js = mf.bulk_load_js("tools/fixtures/rich_map/", list(mf.rich_map_files()), "tools/fixtures/basic.wav")
    ed.js(f"window.__bulkDone=false; window.__bulkAskEarly=null; ({js}).then(()=>{{ window.__bulkDone=true; }}); true", await_promise=False)
    # 一括読込の途中では出さない（loadSongFromItem の直後ではなく、最後に聞く）
    wait_until(ed, "window.__bulkDone", label="一括読込の終わり")
    _wait_ask(ed)
    t.ok(ed.js("window._dbgApp.state().counts.notes>0&&JSON.parse(window._dbg.rt.buildProjectText()).tempoParts.length>0"),
         "聞いた時には譜面とテンポパートも読み込み済み")
    _press(ed, "later")
    _no_ask(ed, "一括読込では1回だけ")
    t.no_errors()


def test_ask_not_on_project_open_or_reconnect(t):
    '''プロジェクトを開いた時の自動読込（exe 版の保存済みの実パス・keep=true）では出ない。音源が読めていないプロジェクトへ同じ名前の音源を選び直す（再接続）でも出ない。
    別の名前の音源なら出る'''
    ed = _open(t)
    _ask_on(ed)
    pj = json.loads(ed.js("window._dbg.rt.buildProjectText()"))
    pj["graph"]["song"]["nativePath"] = "C:\\NLMTest\\Music\\basic.wav"
    ed.js(_NATIVE_JS)
    ed.js(f"(async()=>{{ await window._dbg.rt.applyOpenedProject({json.dumps(pj)},{{name:'t.nlmf'}}); return 1; }})()")
    wait_until(ed, "window._dbgApp.nle().music.audio", label="開いた時の音源の自動読込")
    t.eq(ed.js("window.__natAsk.calls"), ["read:C:\\NLMTest\\Music\\basic.wav"], "保存済みの実パスから自動で読んだ")
    _no_ask(ed, "プロジェクトを開いた時")
    ed.js("delete window.pywebview; true")
    # 音源が読めないまま開いた（ブラウザ版）→ 同じ名前の音源を選び直す＝再接続
    ed.js(f"(async()=>{{ await window._dbg.rt.applyProject({json.dumps(pj)}); return 1; }})()")
    wait_until(ed, "!window._dbgApp.nle().music.audio", label="音源なしで開いた")
    t.eq(_load_media(ed, "basic.wav"), False, "同じ名前＝再接続（新しく取り込んだことにしない）")
    _no_ask(ed, "再接続")
    t.eq(_load_media(ed, "other.wav"), True, "別の名前＝新しく取り込んだ")
    _wait_ask(ed)
    _press(ed, "later")
    t.no_errors()


def test_ask_not_when_result_or_running_or_no_api(t):
    '''この曲の解析の結果がある（目盛りが同じ）時・解析中・この起動で解析を使えないと分かった（API が無い）時は出ない。
    結果があっても、別の曲を取り込めば（目盛りの曲が変わる）出る'''
    ed = _open(t)
    run_analysis(ed, None, tempo=TEMPO_SAME)
    _ask_on(ed)
    _load_media(ed, "basic.wav")
    t.eq(ana(ed)["stale"], False, "同じ曲を入れ直した＝目盛りは解析した時と同じ")
    _no_ask(ed, "結果がある")
    _load_media(ed, "song2.wav")
    _wait_ask(ed)
    _press(ed, "later")
    # 解析中
    ana_mock(ed, tempo=TEMPO_SAME, status_t1=[{"waitFor": "t", "then": status_seq("tempo", TEMPO_SAME)[-1]}])
    click_sel(ed, "#anaMsg .amBtn")   # 帯の［解析し直す］
    wait_until(ed, "!!window._dbgApp.analysis().running", label="解析中")
    _load_media(ed, "song3.wav")
    _no_ask(ed, "解析中")
    click_sel(ed, "#anaMsg .amBtn")   # やめる
    wait_until(ed, "!window._dbgApp.analysis().running", label="やめた")
    ana_go(ed, "t")
    # API が無い（404）と分かった後
    ed = _open(t)
    _ask_on(ed)
    ana_mock(ed, upload={"http": 404, "body": {"ok": False, "error": "unknown endpoint"}})
    click_sel(ed, "#anaStartBtn")
    wait_until(ed, "window._dbgApp.analysis().apiOff", label="解析を使えないと分かる")
    take_errors(ed, "この版では解析を使えません")
    _load_media(ed, "song2.wav")
    _no_ask(ed, "API が無い")
    t.no_errors()


def test_ask_waits_for_other_dialog(t):
    '''他の画面（環境設定）が出ている間は重ねずに待ち、閉じたら出す'''
    ed = _open(t)
    _ask_on(ed)
    click_sel(ed, "#mbSettings")
    wait_until(ed, "document.getElementById('settingsBg').style.display!=='none'&&document.getElementById('settingsBg').style.display!==''", label="環境設定")
    _load_media(ed)
    ed.wait(0.8)
    t.eq((_asking(ed), ana(ed)["askWait"]), (False, True), "環境設定が出ている間は出さずに待つ")
    click_sel(ed, "#settingsClose")
    _wait_ask(ed)
    _press(ed, "later")
    t.no_errors()


def test_ask_never_and_prefs(t):
    '''「次から聞かない」で bsnm_anaAsk='0'（環境設定のチェックも外れる・下に知らせ）→ 次から出ない。環境設定「曲を読み込んだ時に、解析するか聞く」で戻すと
    bsnm_anaAsk='1' になり、また出る。［解析する］と一緒に付けても効く'''
    ed = _open(t)
    _ask_on(ed)
    _load_media(ed)
    _wait_ask(ed)
    click_sel(ed, "#anaAskNever")
    t.ok(ed.js("document.getElementById('anaAskNever').checked"), "チェックが入る")
    _press(ed, "later")
    t.eq(ed.js("localStorage.getItem('bsnm_anaAsk')"), "0", "聞かない設定を保存")
    t.eq(_stat(ed), "曲を読み込んだ時に解析するかを聞かないようにしました（環境設定の「アプリケーション設定」で戻せます）", "下の知らせ")
    t.eq(ed.js("document.getElementById('anaAskOn').checked"), False, "環境設定のチェックも外れる")
    _load_media(ed, "song3.wav")
    _no_ask(ed, "次から聞かない")
    # 環境設定で戻す
    click_sel(ed, "#mbSettings")
    wait_until(ed, "!!document.getElementById('anaAskOn').checkVisibility()", label="環境設定のアプリケーション設定")
    t.eq(ed.js("document.querySelector('[data-i18n=\"set.anaAsk\"]').textContent"), "曲の解析", "項目の見出し")
    t.eq(ed.js("document.querySelector('[data-i18n=\"set.anaAskOn\"]').textContent"), "曲を読み込んだ時に、解析するか聞く", "チェックの文")
    ed.js("document.getElementById('anaAskOn').scrollIntoView({block:'center'});true")   # 環境設定の箱の中でスクロールの先にあることがある
    ed.wait(0.1)
    click_sel(ed, "#anaAskOn")
    t.eq((ed.js("localStorage.getItem('bsnm_anaAsk')"), ana(ed)["askOn"]), ("1", True), "戻した")
    click_sel(ed, "#settingsClose")
    _load_media(ed, "song4.wav")
    _wait_ask(ed)
    # ［解析する］と一緒に「次から聞かない」
    ana_mock(ed, tempo=TEMPO_SAME)
    click_sel(ed, "#anaAskNever")
    _press(ed, "go")
    wait_band(ed)
    t.eq(ed.js("localStorage.getItem('bsnm_anaAsk')"), "0", "［解析する］でも「次から聞かない」が効く")
    t.no_errors()


def test_ask_english(t):
    '''英語表示: 題・箇条・後で解析する入口（溝のボタン・ファイルメニューの名前）・「次から聞かない」・ボタン・環境設定の項目。日本語が残らない'''
    from nlmtest import LIGHT_RENDER_JS
    ed = t.fresh()
    ed.js("localStorage.setItem('bsnm_lang','en');true")
    ed.wait(0.6)
    ed.reload(clear_storage=False)
    ed.js(LIGHT_RENDER_JS)
    wait_until(ed, "!document.getElementById('bootCover')&&document.getElementById('mFileBtn').textContent.trim()==='File'", label="英語で起動")
    ed.load_fixture("basic", settle=0.3)
    _ask_on(ed)
    _load_media(ed)
    _wait_ask(ed)
    d = _dialog(ed)
    t.eq((d["title"], d["lead"]), ("Analyze this song?", "Analyzing the song lets you:"), "題と前置き")
    t.eq(len(d["points"]), 4, "箇条は4つ")
    t.ok(d["points"][1].startswith("See the song's structure (intro, verse, chorus… and segments)"), f"構成の箇条: {d['points'][1]}")
    t.eq(d["note"], "To analyze later, use [🎼 Analyze song] at the left of the spectrogram or \"Analyze song (tempo & structure)…\" in the File menu.", "後で解析する入口")
    t.eq(d["never"], "Don't ask again (you can turn it back on in Preferences)", "次から聞かない")
    t.eq([b["text"] for b in d["btns"]], ["Analyze", "Not now"], "ボタン")
    t.ok(not re.search(r"[぀-ゟ゠-ヺー-ヿ㐀-䶿一-鿿]", d["text"]), f"日本語が残らない: {d['text']}")
    click_sel(ed, "#anaAskNever")
    _press(ed, "later")
    t.eq(_stat(ed), "You won't be asked to analyze when loading a song (turn it back on in Preferences > Application)", "下の知らせ")
    t.eq(ed.js("document.querySelector('[data-i18n=\"set.anaAskOn\"]').textContent"), "Ask whether to analyze when a song is loaded", "環境設定の項目")
    t.no_errors()

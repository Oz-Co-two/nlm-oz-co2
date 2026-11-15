"""譜面チェックのパネルの3つ目のタブ「AutoModder」: 判定は別配布のプラグイン nlm-automodder（serve.py の /__automodder/* → automodder_plugin.py）。
テストではプラグインを入れない＝実サーバーは「未導入」を返す。取り込み・結果の表示・拍のクリックは、ページ内で /__automodder/* の応答を
偽物にして確かめる（tests/_lib/automodder_helpers.py。GitHub への通信・実行ファイルの取り込みは一切しない）。"""
import json

from misc_helpers import click_in_view, click_sel, open_fixture_ready, wait_until
from e2e_helpers import place_at
from automodder_helpers import (AM_DONE, AM_INSTALLED, AM_NONE, PANEL_DONE, am_acts, am_calls, am_result, am_spy, open_mapcheck, reopen_mapcheck,
                                to_am)


def _txt(ed, sel):
    return ed.js(f"(()=>{{const e=document.querySelector({json.dumps('#mcPanel ' + sel)}); return e?e.textContent:null}})()")


def _all(ed, sel):
    return ed.js(f"[...document.querySelectorAll({json.dumps('#mcPanel ' + sel)})].map(e=>e.textContent)")


def _items(ed):
    """結果の項目: [難易度の見出し, 項目名, 重さ, 拍のチップ]（並んでいる順）"""
    return ed.js("""[...document.querySelectorAll('#mcPanel details.amSec')].flatMap(s=>[...s.querySelectorAll('.amItem')].map(i=>[
      s.dataset.sec, i.querySelector('.mcLab').textContent, i.querySelector('.amSev').textContent,
      [...i.querySelectorAll('.mcBeat')].map(b=>b.textContent)]))""")


def _runs(ed):
    return len([a for a in am_acts(ed) if a == "run"])


# ---------------------------------------------------------------- 未導入（実サーバー）
def test_am_tab_not_installed(t):
    '''プラグイン未導入: BS Map Check のタブでは通信しない。AutoModder のタブを開くと状態の確認だけをして、断り書きと取り込みの案内を出す。
    「取り込む…」で説明（大きさ・配布元・保存先）→「やめる」で閉じる。説明を開いただけでは通信しない'''
    ed = open_fixture_ready(t, 'rich')
    am_spy(ed)   # 記録だけ（実サーバーへ通す）
    open_mapcheck(ed)
    ed.wait(0.3)
    t.eq(am_calls(ed), [], "BS Map Check のタブでは状態の確認もしない")
    t.eq(_all(ed, ".mcTab"), ["BS Map Check と同じ判定", "NLM版 BL評価リスト", "AutoModder"], "3つのタブ")
    to_am(ed)
    wait_until(ed, "!!document.querySelector('#mcPanel .amOpen')", label="取り込みのボタン")
    calls = am_calls(ed)
    t.eq([c["act"] for c in calls], ["status"], "開いただけでは状態の確認だけ")
    t.eq((calls[0]["method"], calls[0]["headers"].get("X-NLM-Request")), ("POST", "1"), "POSTで、CSRF対策のヘッダー付き")
    banner = _txt(ed, ".amBanner")
    t.ok(banner.startswith("AutoModder（既定の設定）の判定"), f"見出し（未導入なので版は出さない）: {banner}")
    for s in ("近似ではなく AutoModder と同じコード", "難易度ごとに既定の設定", "R5.A 視界ブロックの時間の式・壁よけの回数",
              "BeatLeader・AutoModder の公式ツールではなく"):
        t.ok(s in banner, f"断り書き「{s}」")
    t.ok("公式の基準と違う所があります" in _txt(ed, ".mcFoot"), "下の注記にも断り書き")
    t.eq(_txt(ed, ".amOpen"), "📥 プラグインを取り込む…", "取り込みのボタン")
    t.eq(ed.js("!!document.querySelector('#mcPanel .amRun')"), False, "未導入なら「確かめる」は無い")
    click_in_view(ed, "#mcPanel .amOpen", "取り込む…")
    wait_until(ed, "!!document.querySelector('#mcPanel .amBox')", label="取り込みの説明")
    box = _txt(ed, ".amBox")
    t.ok("nlm-automodder（約12MB）" in box and "https://github.com/Oz-Co-two/nlm-automodder" in box and "plugins" in box,
         f"説明（大きさ・配布元（本体に固定）・保存先）: {box}")
    t.eq(am_acts(ed), ["status"], "説明を開いただけでは通信しない")
    click_in_view(ed, "#mcPanel .amCancel", "やめる")
    wait_until(ed, "!document.querySelector('#mcPanel .amBox')&&!!document.querySelector('#mcPanel .amOpen')", label="説明を閉じる")
    # タブを覚える: 閉じて INFO のボタンで開き直すと AutoModder のタブのまま（状態は覚えているので通信を増やさない）
    click_sel(ed, "#mcPanel .mcClose", "閉じる")
    reopen_mapcheck(ed)
    t.eq(ed.js("document.getElementById('mcPanel').classList.contains('amMode')"), True, "開き直しても AutoModder のタブ")
    ed.wait(0.3)
    t.eq(am_acts(ed), ["status"], "開き直しても通信を増やさない")
    t.no_errors()


# ---------------------------------------------------------------- 取り込み → そのまま確かめる
def test_am_install_flow(t):
    '''「GitHub から取り込む」の失敗（ネット不通）はその場に赤い文→成功するとそのまま確かめて結果を出す。
    渡す物は書き出しと同じ Info.dat・各難易度の .dat と、書き出す song.egg の長さ'''
    ed = open_fixture_ready(t, 'rich')
    am_spy(ed, {"status": AM_NONE, "install": [{"ok": False, "error": "network"}, AM_INSTALLED], "run": am_result()})
    open_mapcheck(ed)
    to_am(ed)
    click_in_view(ed, "#mcPanel .amOpen", "取り込む…")
    click_in_view(ed, "#mcPanel .amInstall", "GitHub から取り込む")
    wait_until(ed, "!!document.querySelector('#mcPanel .amErrLine')", label="失敗の表示")
    t.ok("GitHub に接続できませんでした" in _txt(ed, ".amErrLine"), "失敗の文")
    t.eq(ed.js("!!document.querySelector('#mcPanel .amOpen')"), True, "取り込みのボタンは残る")
    click_in_view(ed, "#mcPanel .amOpen", "取り込む…（2回目）")
    click_in_view(ed, "#mcPanel .amInstall", "GitHub から取り込む（2回目）")
    wait_until(ed, AM_DONE, label="取り込みの後に結果")
    t.eq(am_acts(ed), ["status", "install", "install", "run"], "呼んだAPI（取り込みの後に自動で確かめる）")
    body = am_calls(ed)[-1]["body"]
    inp = ed.js("window._dbgApp.mapCheckInput()")
    names = [f["name"] for f in body["files"]]
    t.eq(names, ["Info.dat", "HardStandard.dat", "ExpertStandard.dat"], "Info.dat が先頭・書き出す難易度の .dat")
    t.eq(json.loads(body["files"][2]["text"]), inp["diffs"][1]["json"], "難易度の .dat は譜面チェックと同じ中身（書き出しと同じ）")
    info = json.loads(body["files"][0]["text"])
    t.eq([b["_beatmapFilename"] for b in info["_difficultyBeatmapSets"][0]["_difficultyBeatmaps"]], names[1:], "Info.dat の難易度の並び")
    t.ok(abs(body["songLength"] - inp["audioDuration"]) < 1e-6 and body["songLength"] > 0, f"曲の長さ＝書き出す song.egg の長さ: {body['songLength']}")
    t.ok(_txt(ed, ".amBanner").startswith("AutoModder（v1.6.6・既定の設定）の判定"), "結果の版を見出しに出す")
    t.eq(_txt(ed, ".amCtl .amInfo"), "nlm-automodder v0.1.0", "プラグインの版")
    t.eq(ed.js("!!document.querySelector('#mcPanel .amErrLine')"), False, "失敗の表示は消える")
    t.no_errors()


# ---------------------------------------------------------------- 結果の一覧・拍のクリック
def test_am_results_and_jump(t):
    '''結果は曲の情報→Info.dat の難易度の順。同じ項目・同じ文はまとめて拍を並べ、重さの順（Error→Warning→Inconclusive→Suggestion）。
    項目名は訳して元の英語の名前を添え、文は英語のまま。合格は畳んだ1行・統計は1行・ノーツ20個未満の難易度はそう出す。
    開いておくのは曲の情報と今の難易度（編集中の札）だけ。拍をクリックすると（別の難易度なら確かめてから）その難易度へ切り替えて物を選び、
    その拍へ移動する（BS Map Check のタブと同じ。確認の画面の細かい所は e2e/test_mapcheck.py の test_mapcheck_other_diff）'''
    ed = open_fixture_ready(t, 'rich')
    am_spy(ed, {"status": AM_INSTALLED, "run": am_result()})
    open_mapcheck(ed)
    to_am(ed)
    wait_until(ed, AM_DONE, label="結果")
    t.eq(am_acts(ed), ["status", "run"], "タブを開くと状態を確かめて動かす")
    t.eq(ed.js("[...document.querySelectorAll('#mcPanel details.amSec')].map(s=>s.dataset.sec)"), ["info", "Standard/Hard", "Standard/Expert"], "並び")
    heads = _all(ed, "details.amSec>summary")
    t.ok(heads[0].startswith("曲の情報（Info.dat）") and "判定できず（Questionable） 1" in heads[0] and "提案 1" in heads[0], f"曲の情報の見出し: {heads[0]}")
    t.eq(heads[1], "Hard編集中", "確かめていない難易度は数も印も出さない（今開いている Hard には編集中の札）")
    t.eq(ed.js("[...document.querySelectorAll('#mcPanel details.amSec')].map(s=>s.open)"), [True, True, False],
         "開いておくのは曲の情報と今の難易度（Hard）だけ・Expert は閉じる")
    t.ok(heads[2].startswith("Expert") and "エラー（Unrankable） 4" in heads[2] and "警告（Questionable） 2" in heads[2]
         and heads[2].endswith("✖ AutoModder: 不合格"), f"Expert の見出し（数・信号機の欄の一番重い物）: {heads[2]}")
    t.ok("ノーツが20個未満（7個）のため、AutoModder はこの難易度を確かめません。" in _txt(ed, "details[data-sec='Standard/Hard']"), "Hard はノーツ20個未満")
    t.eq(_items(ed), [
        ["info", "BPM", "判定できず（Questionable）", []],
        ["info", "試聴区間", "提案", []],
        ["Standard/Expert", "開始直後の物", "エラー（Unrankable）", ["1", "2"]],
        ["Standard/Expert", "重なった物", "エラー（Unrankable）", ["23", "24"]],
        ["Standard/Expert", "パリティ（角度の差）", "警告（Questionable）", ["10", "18"]],
    ], "項目（重さの順・同じ項目はまとめる・同じ拍は1つ）")
    hot = "[...document.querySelectorAll('#mcPanel .amItem')].find(i=>i.querySelector('.mcLab').textContent==='開始直後の物')"
    t.eq(ed.js(f"{hot}.querySelector('.mcEn').textContent"), "Hot Start", "元の英語の名前を添える")
    t.eq(ed.js(f"{hot}.querySelector('.amDesc').textContent"), "There must be at least 1.5 seconds of time before any interactable objects", "文は英語のまま")
    t.eq(ed.js(f"{hot}.querySelector('.mcN').textContent"), "2", "拍の数")
    t.eq(ed.js(f"{hot}.querySelector('.mcBeat').title"), "0:00.500 · ノーツ · CurrentBeat: 1 · MinimumBeat: 3", "チップのツールチップ（秒・種類・その結果の値）")
    prev = "[...document.querySelectorAll('#mcPanel .amItem')].find(i=>i.querySelector('.mcLab').textContent==='試聴区間')"
    t.eq(ed.js(f"{prev}.querySelector('.amData').textContent"), "PreviewStartTime: 12 · PreviewDuration: 10", "1件だけの項目は値を行で出す")
    t.eq(_all(ed, ".amPassed>summary"), ["✓ 合格 1 項目", "✓ 合格 2 項目"], "合格は畳んだ1行（曲の情報・Expert）")
    t.eq(ed.js("[...document.querySelectorAll('#mcPanel .amPassed')].map(d=>d.open)"), [False, False], "合格は畳んである")
    t.eq(_txt(ed, ".amStat"), "📊 統計（AutoModder の計算）Pass: 0.47 · Tech: 1.59 · EBPM: 43.29", "統計は1行")
    t.ok("エラー（Unrankable） 4" in _txt(ed, ".amSum") and "✓" not in _txt(ed, ".amSum"), f"全体の数: {_txt(ed, '.amSum')}")
    t.eq(_txt(ed, ".amMeta"), "nlm-automodder v0.1.0・AutoModder v1.6.6 (0c26215)・0.9秒・曲の長さ 16秒", "版・時間・曲の長さ")
    # 拍のクリック → 確かめてから Expert へ切り替えてノーツを選び、その拍へ。Expert を開き Hard を閉じる
    t.ok(ed.js("window._dbgApp.state().diff").startswith("Hard"), "最初は Hard を開いている")
    click_in_view(ed, "#mcPanel details[data-sec='Standard/Expert']>summary", "Expert の見出し（開く）")
    wait_until(ed, "document.querySelector(\"#mcPanel details[data-sec='Standard/Expert']\").open", label="Expert を開く")
    click_in_view(ed, f"#mcPanel .amItem .mcBeat[data-ref='am:3:0']", "開始直後の物の拍 1")
    wait_until(ed, "!!document.querySelector('#dirtyDlg .ddBtns button.pri')", label="切り替えの確認")
    t.eq(ed.js("document.querySelector('#dirtyDlg .ddMsg').textContent"), "この結果は Expert の物です（今開いているのは Hard）。\nExpert に切り替えて表示しますか？", "確認の文")
    click_sel(ed, "#dirtyDlg .ddBtns button.pri", "Expert に切り替える")
    wait_until(ed, "(s=>s.diff.startsWith('Expert')&&s.sel===1&&s.cur===1)(window._dbgApp.state())", label="Expert の拍 1 へ移動して選択（移動は少しずつ）")
    st = ed.js("window._dbgApp.state()")
    t.eq((st["cur"], st["sel"]), (1, 1), "拍 1 へ・ノーツを1つ選ぶ")
    t.eq(ed.js("document.querySelector('#mcPanel .mcBeat.cur').dataset.ref"), "am:3:0", "押したチップに印")
    t.eq(ed.js("[...document.querySelectorAll('#mcPanel details.amSec')].map(s=>[s.dataset.sec,s.open,!!s.querySelector(':scope>summary .mcCurTag')])"),
         [["info", True, False], ["Standard/Hard", False, False], ["Standard/Expert", True, True]], "切り替えた後: Expert を開き（編集中）、Hard を閉じる")
    # 壁のチップ（重なった物の 23）→ 壁を選ぶ
    click_in_view(ed, "#mcPanel .amItem .mcBeat[data-ref='am:8:1']", "重なった物の拍 23（壁）")
    wait_until(ed, "window._dbgApp.state().cur===23", label="拍 23 へ")
    t.eq(ed.js("window._dbgApp.state().sel"), 1, "壁を1つ選ぶ")
    t.eq(_runs(ed), 1, "移動しても確かめ直さない（難易度の切り替えだけでは中身は同じ）")
    t.no_errors()


# ---------------------------------------------------------------- 動かし直す条件
def test_am_rerun_rules(t):
    '''譜面がそのままなら、再チェック・タブの行き来では動かし直さない。「もう一度確かめる」と、譜面を直した後の再チェックでは動かし直す。
    動いている間は「確かめています…」と出してボタンを押せない'''
    ed = open_fixture_ready(t, 'rich')
    am_spy(ed, {"status": AM_INSTALLED, "run": am_result()})
    open_mapcheck(ed)
    to_am(ed)
    wait_until(ed, AM_DONE, label="結果")
    click_sel(ed, "#mcPanel .mcRerun", "↻ 再チェック")
    wait_until(ed, PANEL_DONE, label="再チェック")
    click_sel(ed, "#mcPanel .mcTab[data-tab=bl]", "BL評価リスト")
    ed.wait(0.3)
    to_am(ed)
    ed.wait(0.3)
    t.eq(_runs(ed), 1, "譜面がそのままなら動かし直さない")
    # もう一度確かめる（実行中の表示も見る）
    ed.js("window.__am.hold=true")
    click_in_view(ed, "#mcPanel .amRun", "↻ もう一度確かめる")
    wait_until(ed, "(b=>!!b&&b.disabled&&b.textContent==='AutoModder で確かめています…')(document.querySelector('#mcPanel .amRun'))", label="実行中の表示")
    t.eq(ed.js("document.querySelector('#mcPanel .mcRerun').disabled"), True, "実行中は再チェックも押せない")
    ed.js("window.__am.hold=false;window.__am.release&&window.__am.release()")
    wait_until(ed, "(b=>!!b&&!b.disabled&&b.textContent==='↻ もう一度確かめる')(document.querySelector('#mcPanel .amRun'))", label="終わる")
    t.eq(_runs(ed), 2, "もう一度確かめる")
    # 譜面を直して開き直す → 直した内容で動かす
    click_sel(ed, "#mcPanel .mcClose", "閉じる")
    place_at(ed, 1, 2)
    reopen_mapcheck(ed)   # 前回の AutoModder のタブで開く
    wait_until(ed, "window.__am.calls.filter(c=>c.act==='run').length===3", label="直した後は動かし直す")
    calls = [c for c in am_calls(ed) if c["act"] == "run"]
    hard = lambda c: json.loads(next(f for f in c["body"]["files"] if f["name"] == "HardStandard.dat")["text"])
    t.eq(len(hard(calls[2])["colorNotes"]), len(hard(calls[0])["colorNotes"]) + 1, "置いたノーツが入っている")
    t.no_errors()


# ---------------------------------------------------------------- 失敗の形
def test_am_failures(t):
    '''実行の失敗（プラグインが ok:false）は種類の文と詳しい文を赤で出す。途中で止まった難易度・読み込めなかった難易度はその難易度の所に出す。
    書き出す song.egg が無い（音源が無い）時は動かさずにそう出す'''
    ed = open_fixture_ready(t, 'rich')
    part = am_result(errors=[{"stage": "difficulty", "type": "NullReferenceException", "message": "Object reference not set",
                              "where": "BLMapCheck.Lights.Check()", "characteristic": "Standard", "difficulty": "Expert"}])
    part["criteria"]["diff"]["Standard"]["Expert"].update({"highest": None, "crit": None, "error": True})
    part["criteria"]["diff"]["Standard"]["Hard"].update({"skipped": "notLoaded", "notes": None, "highest": None})
    am_spy(ed, {"status": AM_INSTALLED, "run": [{"ok": False, "error": "run", "detail": "InvalidDataException: map could not be read"}, part]})
    open_mapcheck(ed)
    to_am(ed)
    wait_until(ed, "!!document.querySelector('#mcPanel .mcBody>.mcErr')", label="失敗の表示")
    t.eq(_txt(ed, ".mcBody>.mcErr"), "AutoModder の実行に失敗しました。 (InvalidDataException: map could not be read)", "失敗の文")
    t.eq(_txt(ed, ".amRun"), "▶ 確かめる", "うまくいっていないので「確かめる」")
    click_in_view(ed, "#mcPanel .amRun", "確かめる")
    wait_until(ed, AM_DONE, label="結果")
    ex = _txt(ed, "details[data-sec='Standard/Expert']")
    t.ok("確かめの途中で AutoModder が止まりました" in ex and "NullReferenceException: Object reference not set (BLMapCheck.Lights.Check())" in ex, f"途中で止まった難易度: {ex}")
    t.ok("AutoModder:" not in _txt(ed, "details[data-sec='Standard/Expert']>summary"), "止まった難易度には信号機の印を出さない")
    t.ok("この難易度の譜面を AutoModder が読み込めませんでした。" in _txt(ed, "details[data-sec='Standard/Hard']"), "読み込めなかった難易度")
    t.no_errors()   # 失敗は画面に出すだけ（ページの例外にしない）
    # 音源が無い → 動かさない
    ed = t.fresh()
    ed.load_fixture('rich', wav='no-such-audio', settle=0.3)
    wait_until(ed, "!document.getElementById('bootCover')", label="起動中の覆いが外れる")
    am_spy(ed, {"status": AM_INSTALLED, "run": am_result()})
    open_mapcheck(ed)
    to_am(ed)
    wait_until(ed, "!!document.querySelector('#mcPanel .mcBody>.mcErr')", label="音源が無い表示")
    t.eq(_txt(ed, ".mcBody>.mcErr"), "音源がありません。AutoModder は曲の長さを使うので、音源を読み込んでから確かめてください。", "音源が無い")
    t.eq(am_acts(ed), ["status"], "動かさない")
    t.no_errors()

"""難易度を測る（BeatLeaderの星の近似）: 計算は別配布のプラグイン nlm-rating（serve.py の /__rating/* → rating_plugin.py）。
テストではプラグインを入れない＝実サーバーは「未導入」を返す。入力（書き出しと同じ Info.dat/.dat）と結果の表示は、
ページ内で /__rating/* の応答を偽物にして確かめる（GitHub への通信・実行ファイルの取り込みは一切しない）。"""
import json

from misc_helpers import (RATING_INSTALLED, RATING_NONE, click_sel, fresh_page, open_fixture_ready, rating_calls, rating_open_via_menu,
                          rating_spy, rating_text, to_info, wait_until)
from e2e_helpers import export_files, place_at

MEASURE_OK = {"ok": True, "version": "0.1.0", "elapsedMs": 1234, "results": [
    {"difficulty": "Hard", "skipped": False, "notes": 7,
     "ratings": {"none": {"stars": 3.214, "pass": 2.1, "tech": 1.5, "acc": 5.5, "predictedAcc": 0.9512},
                 "SS": {"stars": 2.5}, "FS": {"stars": 3.9}, "SFS": {"stars": 4.8}}},
    {"difficulty": "Expert", "skipped": True, "notes": 12},
]}


def _rows(ed):
    """結果の表の各行（セルの文字）"""
    return ed.js("[...document.querySelectorAll('#rtPanel .rtTable tr')].map(r=>[...r.children].map(c=>c.textContent))")


# ---------------------------------------------------------------- 未導入（実サーバー）
def test_rating_panel_not_installed(t):
    '''プラグイン未導入: パネルに「プラグイン未導入」と取り込みの案内・配布元が出て「測る」は押せない（押しても測定は呼ばれない）。開いただけでは通信せず（状態の確認だけ）、閉じて開き直せる'''
    ed = open_fixture_ready(t, 'rich')
    rating_spy(ed)   # 記録だけ（実サーバーへ通す）
    t.eq(ed.js("document.getElementById('rtPanel')"), None, "最初はパネルが無い")
    rating_open_via_menu(ed)
    wait_until(ed, "document.querySelector('#rtPanel .rtPlugTxt').textContent==='プラグイン未導入'", label="未導入の表示")
    t.eq(rating_text(ed, ".rtTitle"), "難易度を測る（BeatLeaderの星の近似）", "見出し")
    t.eq(ed.js("document.querySelector('#rtPanel .rtRun').disabled"), True, "「測る」は押せない")
    t.eq(rating_text(ed, ".rtRun"), "測る", "ボタンの文言")
    t.eq(rating_text(ed, ".rtInstall"), "GitHub から取り込む", "取り込みのボタン")
    t.ok(ed.js("document.querySelector('#rtPanel .rtInstall').style.display") != "none", "取り込みのボタンが見える")
    t.eq(ed.js("document.querySelector('#rtPanel .rtCheck').style.display"), "none", "「更新を確認」は導入後だけ")
    t.eq(ed.js("document.querySelector('#rtPanel .rtVer').style.display"), "none", "版の選択は2つ以上ある時だけ")
    intro = rating_text(ed, ".rtIntro")
    t.ok("nlm-rating" in intro and "約20MB" in intro, f"取り込みの案内: {intro}")
    t.eq(rating_text(ed, ".rtRepo"), "https://github.com/Oz-Co-two/nlm-rating", "配布元（取得先は本体に固定）")
    foot = rating_text(ed, ".rtFoot")
    t.ok("BeatLeader の公式ツールではありません" in foot and "近似値" in foot, f"近似値・公式ではない旨の注記: {foot}")
    t.ok("20個未満" in foot, "ノーツ20個未満は測れない旨の注記")
    calls = rating_calls(ed)
    t.eq([c["act"] for c in calls], ["status"], "開いただけでは状態の確認(status)しか呼ばない（check/install は押した時だけ）")
    t.eq((calls[0]["method"], calls[0]["headers"].get("X-NLM-Request")), ("POST", "1"), "POSTで、CSRF対策のヘッダー付き")
    # 閉じる→INFOの「★ 難易度を測る」ボタンで開き直す。再度の状態確認は不要（状態を覚えている）
    click_sel(ed, "#rtPanel .rtClose", "閉じる")
    t.eq(ed.js("document.getElementById('rtPanel').style.display"), "none", "閉じた")
    to_info(ed)
    click_sel(ed, "#iRating", "INFOの「難易度を測る」ボタン")
    wait_until(ed, "document.getElementById('rtPanel').style.display==='flex'", label="開き直し")
    t.eq([c["act"] for c in rating_calls(ed)], ["status"], "開き直しても通信を増やさない")
    # 未導入のまま「測る」を押しても測定は呼ばれず、結果の表も出ない
    p = ed.js("(()=>{const r=document.querySelector('#rtPanel .rtRun').getBoundingClientRect();return {x:r.left+r.width/2,y:r.top+r.height/2}})()")
    ed.click(p["x"], p["y"])
    ed.wait(0.3)
    t.eq([c["act"] for c in rating_calls(ed)], ["status"], "「測る」を押しても測定は呼ばれない")
    t.eq(ed.js("!!document.querySelector('#rtPanel .rtTable')"), False, "結果の表は出ない")
    t.no_errors()


# ---------------------------------------------------------------- 導入済み（偽の応答）
def test_rating_measure_input_and_results(t):
    '''測定に渡す入力は書き出しと同じ（Info.dat と各難易度.dat・易しい順・速度違いSS/FS/SFSも頼む）。返ってきた結果は難易度ごとの表（★・Pass・Tech・Acc・速度違い・20個未満の注記）に出る'''
    ed = open_fixture_ready(t, 'rich')
    rating_spy(ed, {"status": RATING_INSTALLED, "measure": MEASURE_OK})
    rating_open_via_menu(ed)
    wait_until(ed, "window.__rt.calls.some(c=>c.act==='measure')", label="開くと自動で測る")
    call = next(c for c in rating_calls(ed) if c["act"] == "measure")
    body = call["body"]
    t.eq(body["modifiers"], ["none", "SS", "FS", "SFS"], "測る速度")
    t.eq([f["name"] for f in body["files"]], ["Info.dat", "HardStandard.dat", "ExpertStandard.dat"], "渡すファイル（Info.dat→難易度は易しい順）")
    exp = export_files(ed)
    t.eq(sorted(exp), ["ExpertStandard.dat", "HardStandard.dat", "Info.dat"], "準備: 書き出しの内容")
    sent = {f["name"]: f["text"] for f in body["files"]}
    t.eq(json.loads(sent["Info.dat"]), json.loads(exp["Info.dat"]), "Info.dat は書き出しと同じ内容")
    t.eq(sent["HardStandard.dat"], exp["HardStandard.dat"], "HardStandard.dat は書き出しと同じ文字列")
    t.eq(sent["ExpertStandard.dat"], exp["ExpertStandard.dat"], "ExpertStandard.dat は書き出しと同じ文字列")
    # 結果の表: 難易度ごとに ★・Pass・Tech・Acc（小数2桁）・速度違いの★・予測精度のヒント・20個未満で測れない難易度・版と所要時間
    wait_until(ed, "document.querySelectorAll('#rtPanel .rtTable tr').length>0", label="結果の表")
    t.eq(rating_text(ed, ".rtPlugTxt"), "プラグイン v0.1.0", "プラグインの版の表示")
    rows = _rows(ed)
    t.eq(rows[0], ["難易度", "★", "Pass", "Tech", "Acc"], "見出し行")
    t.eq(rows[1], ["Hard", "3.21", "2.10", "1.50", "5.50"], "Hard の行（小数2桁）")
    t.eq(rows[2], ["", "SS ★2.50FS ★3.90SFS ★4.80"], "速度違いの★")
    t.eq(rows[3], ["Expert", "ノーツが20個未満のため測れません（12個）"], "測れない難易度")
    t.eq(ed.js("document.querySelector('#rtPanel .rtTable tr:nth-child(2)').title"), "予測精度 95.12%", "予測精度のヒント")
    t.eq(rating_text(ed, ".rtMeta"), "nlm-rating v0.1.0・1.2秒", "版と所要時間")
    t.eq(rating_text(ed, ".rtRun"), "↻ 再測定", "測定後のボタンは再測定")
    t.eq(ed.js("document.querySelector('#rtPanel .rtRun').disabled"), False, "再測定は押せる")
    t.no_errors()


def test_rating_remeasure_after_edit(t):
    '''譜面を直してからパネルを開き直すと、直した後の内容（書き出しと同じ）が渡る。「↻ 再測定」ボタンでも測り直す'''
    ed = open_fixture_ready(t, 'rich')
    rating_spy(ed, {"status": RATING_INSTALLED, "measure": MEASURE_OK})
    rating_open_via_menu(ed)
    wait_until(ed, "window.__rt.calls.filter(c=>c.act==='measure').length===1", label="1回目の測定")
    first = json.loads(next(f for f in rating_calls(ed)[-1]["body"]["files"] if f["name"] == "HardStandard.dat")["text"])
    click_sel(ed, "#rtPanel .rtClose", "閉じる")   # 3Dビューの操作のため一度閉じる（パネルが3Dビューに被る）
    place_at(ed, 1, 2)
    rating_open_via_menu(ed)
    wait_until(ed, "window.__rt.calls.filter(c=>c.act==='measure').length===2", label="開き直しでもう一度測る")
    second = next(f for f in rating_calls(ed)[-1]["body"]["files"] if f["name"] == "HardStandard.dat")["text"]
    t.eq(len(json.loads(second)["colorNotes"]), len(first["colorNotes"]) + 1, "置いたノーツが入っている")
    t.eq(second, export_files(ed)["HardStandard.dat"], "書き出しと同じ文字列")
    click_sel(ed, "#rtPanel .rtRun", "再測定")
    wait_until(ed, "window.__rt.calls.filter(c=>c.act==='measure').length===3", label="再測定ボタン")
    t.no_errors()


def test_rating_measure_errors_and_no_chart(t):
    '''測定の失敗は赤い文で出る（プラグインの失敗・時間切れ）→成功すると消える／測れる譜面が無い（ノーツ・ライトが空）なら測定を呼ばずにそう出る'''
    ed = open_fixture_ready(t, 'rich')
    rating_spy(ed, {"status": RATING_INSTALLED, "measure": [
        {"ok": False, "error": "run", "detail": "exit 3"}, {"ok": False, "error": "timeout"}, MEASURE_OK]})
    rating_open_via_menu(ed)
    wait_until(ed, "!!document.querySelector('#rtPanel .rtErr')", label="失敗の表示")
    t.eq(rating_text(ed, ".rtErr"), "測定に失敗しました。 (exit 3)", "プラグインの失敗（詳細つき）")
    click_sel(ed, "#rtPanel .rtRun", "再測定")
    wait_until(ed, "document.querySelector('#rtPanel .rtErr')&&document.querySelector('#rtPanel .rtErr').textContent==='測定が時間内に終わりませんでした。'", label="時間切れの表示")
    click_sel(ed, "#rtPanel .rtRun", "再測定")
    wait_until(ed, "document.querySelectorAll('#rtPanel .rtTable tr').length>0", label="3回目は成功")
    t.eq(ed.js("!!document.querySelector('#rtPanel .rtErr')"), False, "成功すると失敗の表示は消える")
    # 空の譜面（素材なしの新規）
    ed = fresh_page(t)
    rating_spy(ed, {"status": RATING_INSTALLED, "measure": MEASURE_OK})
    rating_open_via_menu(ed)
    wait_until(ed, "!!document.querySelector('#rtPanel .rtErr')", label="空の譜面のエラー")
    t.eq(rating_text(ed, ".rtErr"), "書き出せる難易度がありません（ノーツ/ライトが空です）", "測れる難易度が無い時の文")
    t.eq([c["act"] for c in rating_calls(ed)], ["status"], "測定は呼ばない")
    t.no_errors()


def test_rating_install_flow(t):
    '''「GitHub から取り込む」（応答は偽物）: 失敗（ネット不通）は赤い文で出てボタンは残る→成功すると取り込み済みの表示になり、そのまま測定まで進む'''
    ed = open_fixture_ready(t, 'rich')
    rating_spy(ed, {"status": RATING_NONE, "install": [{"ok": False, "error": "network"}, RATING_INSTALLED], "measure": MEASURE_OK})
    rating_open_via_menu(ed)
    wait_until(ed, "document.querySelector('#rtPanel .rtPlugTxt').textContent==='プラグイン未導入'", label="未導入の表示")
    click_sel(ed, "#rtPanel .rtInstall", "取り込む")
    wait_until(ed, "document.querySelector('#rtPanel .rtMsg').classList.contains('err')", label="失敗の表示")
    t.ok("GitHub に接続できませんでした" in rating_text(ed, ".rtMsg"), f"失敗の文: {rating_text(ed, '.rtMsg')}")
    t.eq(rating_text(ed, ".rtPlugTxt"), "プラグイン未導入", "失敗しても未導入のまま")
    t.eq(rating_text(ed, ".rtInstall"), "GitHub から取り込む", "取り込みのボタンは残る")
    click_sel(ed, "#rtPanel .rtInstall", "取り込む（2回目）")
    wait_until(ed, "document.querySelectorAll('#rtPanel .rtTable tr').length>0", label="取り込み後の測定結果")
    t.eq(rating_text(ed, ".rtPlugTxt"), "プラグイン v0.1.0", "導入済みの表示")
    t.eq([c["act"] for c in rating_calls(ed)], ["status", "install", "install", "measure"], "呼んだAPI（取り込みの後に自動で測る）")
    t.no_errors()

"""MEDIA ライブラリのネットの情報・★のまとめての計算・環境設定の MEDIA タブ・音源の実際のパス（2026-10-12）。
素材は tools/fixtures/media_lib（test_media_library.py と同じ。並びは Alpha H/Ex/E+・Beta E/N/H・Gamma Ex（v4）・Delta H/E+・art・loose）。
ネット・プラグインには出ない: 全曲データ（/__lib/details）・BeatSaver（/__lib/beatsaver）・★の計算（/__lib/rate）の応答はページ内で差し替える
（e2e_helpers.media_lib_mock。テストのサーバーは NLM_NO_NET でネットへ出ない）。起動時の全曲データの取得だけは、本物の通り道
（画面→serve.py）を確かめるため serve.SONG_DETAILS を差し替えて数える。"""
import json
import sys
import time
from datetime import datetime
from pathlib import Path

from e2e_helpers import (wait_until, media_lib_load, media_lib_mock, media_lib_calls, media_lib_record, media_lib_sample_extra,
                         SAMPLE_DETAILS, SAMPLE_AS_OF)
from nle_helpers import take_errors, menu, menu_items, open_nle, clear_assets
from lib_helpers import LIB, REL, lib, lib_id, set_view, row_xy, click_sel, drag_from, wait_scanned

_MISC = str(Path(__file__).resolve().parents[1] / "e2e_misc")
if _MISC not in sys.path:
    sys.path.insert(0, _MISC)

T = lambda y, m, d: int(datetime(y, m, d, 12).timestamp())
SLEEP = "await new Promise(r=>setTimeout(r,%d));"


def _open(t, fx=None, details=SAMPLE_DETAILS, extra="sample", paths=None):
    """開き直して記録したライブラリを読む（既定は見本のネット・NLM推定の値と、取得済みの全曲データ）"""
    clear_assets(t.ed)
    ed = open_nle(t, fx)
    (Path(ed.data_dir) / "PlayerData.dat").unlink(missing_ok=True)
    media_lib_load(ed, extra=media_lib_sample_extra() if extra == "sample" else extra, paths=paths, details=details)
    return ed


def _on(ed):
    return ed.js("window._dbgApp.libOnline()")


def _cell(ed, i, col):
    return ed.js(f"window._dbgApp.libCell({i},{json.dumps(col)})")


def _btn_xy(ed, i, sel=".ltLook"):
    """詳細表示の i 行目のセルの中のボタンの画面座標。表を縦横にスクロールして見える所へ出す（行は見えている物だけ描く）"""
    row_xy(ed, i)
    ed.js("""(t=>{ const h=t.querySelector('.ltH[data-col=uploaded]'); if(h) t.scrollLeft=Math.max(0,h.offsetLeft-120); return 1; })(document.getElementById('libTable'))""")
    ed.wait(0.15)
    return wait_until(ed, f"""(()=>{{ const e=[...document.querySelectorAll('#libTable .ltRow')].find(e=>e._i==={i}&&e.style.display!=='none');
      const b=e&&e.querySelector({json.dumps(sel)}); if(!b) return null; const r=b.getBoundingClientRect(); return [r.left+r.width/2,r.top+r.height/2]; }})()""",
                      label=f"{i}行目のボタン")


def _drag_starts(ed, x, y):
    """(x,y) を押したまま動かした時にドラッグが始まるか（始まったら取り消す）"""
    ed.call("Input.setInterceptDrags", enabled=True)
    try:
        n0 = sum(1 for e in ed._events if e.get("method") == "Input.dragIntercepted")
        ed.move(x, y)
        ed.call("Input.dispatchMouseEvent", type="mousePressed", x=x, y=y, button="left", buttons=1, clickCount=1)
        for k in range(1, 8):
            ed.call("Input.dispatchMouseEvent", type="mouseMoved", x=x + 12 * k, y=y + 6 * k, button="left", buttons=1)
        evs = [e for e in ed._events if e.get("method") == "Input.dragIntercepted"][n0:]
        if evs:
            ed.call("Input.dispatchDragEvent", type="dragCancel", x=x + 84, y=y + 42, data=evs[-1]["params"]["data"])
        ed.call("Input.dispatchMouseEvent", type="mouseReleased", x=x + 84, y=y + 42, button="left", buttons=0, clickCount=1)
        ed.wait(0.3)
        return bool(evs)
    finally:
        ed.call("Input.setInterceptDrags", enabled=False)
        for e in list(ed._events):
            if e.get("method") == "Input.dragIntercepted":
                ed._events.remove(e)


def _dialog(ed, *parts):
    """確認のダイアログ（askYesNo）が出るのを待ち、文面を返す"""
    msg = wait_until(ed, "(d=>d&&d.querySelector('.ddMsg').textContent)(document.getElementById('dirtyDlg'))", label="確認のダイアログ")
    for p in parts:
        assert p in msg, f"確認の文面に「{p}」がありません: {msg}"
    return msg


def _answer(ed, yes):
    click_sel(ed, "#dirtyDlg button.pri" if yes else "#dirtyDlg button:not(.pri)")
    wait_until(ed, "!document.getElementById('dirtyDlg')", label="確認のダイアログが閉じる")


def _toast(ed):
    return ed.js("document.getElementById('errToast').textContent")


def _rate_menu(ed, i, which):
    """詳細表示の i 行目を右クリックして「選んだ行／絞り込んだ行の★を計算」を押す。押す前のメニューの文字を返す"""
    x, y = row_xy(ed, i)
    ed.click(x, y, button="right")
    wait_until(ed, "getComputedStyle(document.getElementById('ctxmenu')).display!=='none'", label="右クリックメニュー")
    items = menu_items(ed)
    label = "選んだ行の★を計算" if which == "selected" else "絞り込んだ行の★を計算"
    p = ed.js(f"""(()=>{{ const b=[...document.querySelectorAll('#ctxmenu > button')].find(b=>b.textContent.includes({json.dumps(label)}));
      if(!b) return null; const r=b.getBoundingClientRect(); return [r.left+r.width/2,r.top+r.height/2]; }})()""")
    assert p, f"メニューに「{label}」がありません: {items}"
    ed.move(*p)
    ed.click(*p)
    return items


def _wait_reloaded(ed, marker):
    """ページ自身が location.reload() した（印 window.<marker> が消え、起動が終わった）のを待つ（e2e_misc/test_prefs.py と同じ）"""
    from cdp import CdpError
    end = time.time() + 30
    while time.time() < end:
        try:
            if ed.js(f"window.{marker}===undefined&&document.readyState==='complete'&&!!window._dbgApp&&window._dbgApp.booted()&&!document.getElementById('bootCover')"):
                return
        except CdpError:
            pass
        time.sleep(0.1)
    raise AssertionError("ページが読み直されません")


def _wait_rate_done(ed, timeout=20):
    wait_until(ed, "(s=>!s.rate.running&&s.rate.total>0)(window._dbgApp.libOnline())", timeout=timeout, label="★の計算の終わり")


# ---------------------------------------------------------------- 🔍
def test_look_confirm_each_time_and_found(t):
    '''🔍（全曲データに無い曲だけ）: 押すたびに確認が出る・やめると送らない・送るとその1曲だけ・問い合わせ中は待ちの表示（押せない）・見つかれば🔍が消えて値が出る（BeatSaver から取得）。ボタンでは行の選択・ドラッグにならない'''
    ed = _open(t)
    up = T(2025, 3, 4)
    media_lib_mock(ed, beatsaver="async b=>{ %s return {ok:true,net:{src:'beatsaver',match:'hash',key:'1c03',uploaded:%d,up:3,down:1,diffs:{'Standard/Expert':{bl:6.4}}}}; }"
                   % (SLEEP % 600, up))
    set_view(ed, "detail")
    t.eq([(_cell(ed, i, "uploaded")["text"], bool(_cell(ed, i, "uploaded")["btn"])) for i in (0, 5, 6, 7, 8)],
         [("2024-05-01", False), ("2023-01-01", False), ("未照合🔍", True), ("未照合🔍", True), ("未照合🔍", True)],
         "全曲データに無い曲（Gamma・Delta）だけ「未照合 🔍」（アップロード日の列）")
    t.eq(_cell(ed, 6, "rating")["text"], "", "🔍 は1つの列にだけ（他のネットの列は空欄）")
    t.ok("全曲データ（BeatSaberScrappedData）にありません" in _cell(ed, 6, "uploaded")["title"], "ツールチップで理由")
    # ボタンを押したまま動かしてもドラッグにならない（比べるため、同じ行の曲名の所からはドラッグが始まることも確かめる）
    x, y = _btn_xy(ed, 6)
    nx = ed.js("""(()=>{ const e=[...document.querySelectorAll('#libTable .ltRow')].find(e=>e._i===6&&e.style.display!=='none');
      const r=e.querySelector('.ltMissT').getBoundingClientRect(); return [r.left+r.width/2,r.top+r.height/2]; })()""")
    t.ok(_drag_starts(ed, *nx), "同じセルの「未照合」の文字からはドラッグが始まる")
    t.ok(not _drag_starts(ed, x, y), "🔍 を押したまま動かしてもドラッグにならない")
    # 1回目: やめる → 送らない
    x, y = _btn_xy(ed, 6)
    ed.click(x, y)
    msg = _dialog(ed, "「Gamma V4」", "api.beatsaver.com", "識別子")
    t.ok("今後" not in msg, "「今後は確認しない」は無い")
    t.eq(ed.js("[...document.querySelectorAll('#dirtyDlg button')].map(b=>b.textContent)"), ["送信する", "やめる"], "ボタン")
    t.eq(lib(ed)["sel"], [], "🔍 を押しても行は選ばれない")
    _answer(ed, False)
    ed.wait(0.3)
    t.eq(media_lib_calls(ed, "beatsaver"), [], "やめると送らない")
    # 2回目: また確認が出る → 送信する
    x, y = _btn_xy(ed, 6)
    ed.click(x, y)
    _dialog(ed, "「Gamma V4」")
    _answer(ed, True)
    wait_until(ed, f"window._dbgApp.libOnline().looking.includes({json.dumps(REL['c'])})", label="問い合わせ中")
    c = _cell(ed, 6, "uploaded")
    t.eq((c["text"], c["btn"]["disabled"]), ("問い合わせ中…⏳", True), "問い合わせ中は待ちの表示（押せない）")
    wait_until(ed, f"window._dbgApp.libCell(6,'uploaded').text==='{datetime.fromtimestamp(up):%Y-%m-%d}'", label="BeatSaver の値")
    calls = media_lib_calls(ed, "beatsaver")
    t.eq([(c["body"]["id"], c["body"]["rel"], c["body"]["net"]) for c in calls], [(lib_id(ed), REL["c"], True)], "送ったのはその1曲だけ（記録の id と相対パス）")
    c = _cell(ed, 6, "uploaded")
    t.ok(c["btn"] is None and "BeatSaver から取得" in c["title"], f"🔍 が消え、値のツールチップに BeatSaver から取得: {c}")
    t.ok("BeatSaver から取得" in _cell(ed, 6, "stars")["title"] and _cell(ed, 6, "stars")["text"] == "6.40", "★も BeatSaver の値（ツールチップ）")
    t.ok("BeatSaver から取得しました" in _toast(ed), f"お知らせ: {_toast(ed)}")
    t.eq((bool(_cell(ed, 7, "uploaded")["btn"]), lib(ed)["sel"]), (True, []), "他の曲の🔍は残る・行は選ばれていない")
    t.no_errors()


def test_look_not_found_busy_and_failure(t):
    '''🔍 の結果: BeatSaver にも無い＝🔍は残りツールチップに確認した日・混んでいる＝「{n}秒ほど待って」・通信の失敗＝失敗の案内'''
    ed = _open(t)
    miss = T(2026, 10, 1)
    media_lib_mock(ed, beatsaver=("async b=>{ %s if(b.rel===%s) return {ok:true,net:{src:'none',bsMissAt:%d}};"
                                  " if(window.__bsBusy) return {ok:false,error:'busy',retryAfter:42}; return {ok:false,error:'network'}; }")
                   % (SLEEP % 100, json.dumps(REL["d"]), miss))
    set_view(ed, "detail")
    ed.click(*_btn_xy(ed, 7))
    _dialog(ed, "「Delta Noodle」")
    _answer(ed, True)
    wait_until(ed, "window._dbgApp.libOnline().lookLog.length===1", label="問い合わせの結果")
    c = _cell(ed, 7, "uploaded")
    t.ok(c["btn"] and "BeatSaver にも見つかりませんでした（2026-10-01 に確認）" in c["title"], f"見つからない＝🔍は残り、確認した日: {c}")
    t.ok("BeatSaver にも見つかりませんでした" in ed.js("document.getElementById('stat').textContent"), "下の案内")
    ed.js("window.__bsBusy=true")
    ed.click(*_btn_xy(ed, 6))
    _dialog(ed, "「Gamma V4」")
    _answer(ed, True)
    wait_until(ed, "window._dbgApp.libOnline().lookLog.length===2", label="混んでいる")
    t.ok("BeatSaver が混んでいます。42秒ほど待ってから" in _toast(ed), f"混んでいる: {_toast(ed)}")
    t.eq(take_errors(ed, "混んでいます"), 1, "エラーの表示")
    t.ok(not _cell(ed, 6, "uploaded")["btn"]["disabled"], "もう一度押せる")
    ed.js("window.__bsBusy=false")
    ed.click(*_btn_xy(ed, 6))
    _dialog(ed, "「Gamma V4」")
    _answer(ed, True)
    wait_until(ed, "window._dbgApp.libOnline().lookLog.length===3", label="通信の失敗")
    t.ok("BeatSaver への問い合わせに失敗しました: Gamma V4（通信に失敗しました）" in _toast(ed), f"失敗: {_toast(ed)}")
    t.eq(take_errors(ed, "問い合わせに失敗"), 1, "エラーの表示")
    t.eq([c["body"]["rel"] for c in media_lib_calls(ed, "beatsaver")], [REL["d"], REL["c"], REL["c"]], "押した曲だけ・押した回数だけ")
    t.no_errors()


def test_look_hidden_without_song_data(t):
    '''全曲データが無い（未取得・取得の失敗）時と、環境設定で全曲データを OFF にした時は 🔍 を出さない（出どころの表示も出さない）'''
    ed = _open(t, details=None)   # テストのサーバーの本物＝ネットへ出ない（取得の失敗か未取得）
    set_view(ed, "detail")
    s = _on(ed)
    t.ok(s["details"]["state"] in ("none", "error") and not s["usable"], f"全曲データは使えない: {s['details']}")
    t.eq((_cell(ed, 6, "uploaded")["text"], _cell(ed, 6, "uploaded")["btn"], s["source"]), ("", None, None), "🔍 も出どころも出さない")
    ed = _open(t)
    set_view(ed, "detail")
    t.ok(_on(ed)["source"] and "BeatSaberScrappedData" in _on(ed)["source"]["text"], "全曲データを使っている時は出どころ")
    ed.js("localStorage.setItem('bsnm_libNetData','0'); window._dbg.rt.libRefreshExtra().then(()=>true)")
    wait_until(ed, "!window._dbgApp.libOnline().usable", label="OFF")
    ed.wait(0.2)
    t.eq((_cell(ed, 6, "uploaded")["btn"], _on(ed)["source"]), (None, None), "OFF の時は 🔍・出どころを出さない")
    t.no_errors()


# ---------------------------------------------------------------- ★のまとめての計算
def test_rate_selected_and_filtered(t):
    '''★のまとめての計算: 選んだ行／絞り込んだ行のうち、公式の BL★ も NLM推定も無い行の曲だけ（曲単位で1回）。結果は「NLM推定」として表に出る'''
    ed = _open(t)
    media_lib_mock(ed, rate=("async b=>{ %s return {ok:true,est:{version:'0.1.0',diffs: b.rel===%s"
                             " ? {'Standard/Hard':{stars:3.21},'Standard/Expert':{stars:6.5},'Standard/ExpertPlus':{stars:8.8}}"
                             " : {'Standard/Expert':{stars:5.55}}}}; }") % (SLEEP % 200, json.dumps(REL["a"])))
    set_view(ed, "detail")
    t.eq(_on(ed)["targets"]["filtered"], 2, "表示中の行の対象は Alpha（Hard に★が無い）と Gamma だけ（Beta・Delta は NLM推定あり）")
    # BL★のある行だけを選ぶ → 対象なし
    ed.click(*row_xy(ed, 1))
    items = _rate_menu(ed, 1, "selected")
    t.ok(any("選んだ行の★を計算（NLM推定・0曲）" in s for s in items) and any("絞り込んだ行の★を計算（NLM推定・2曲）" in s for s in items),
         f"メニューに件数: {items}")
    wait_until(ed, "document.getElementById('errToast').textContent.includes('★を計算する曲がありません')", label="対象なしの案内")
    t.eq(take_errors(ed, "★を計算する曲がありません"), 1, "対象なしの案内")
    # Alpha の3行と Beta の1行を選ぶ → Alpha の1曲だけ
    ed.click(*row_xy(ed, 0))
    ed.click(*row_xy(ed, 2), shift=True)
    ed.click(*row_xy(ed, 4), ctrl=True)
    t.eq(len(lib(ed)["sel"]), 4, "4行を選んだ")
    _rate_menu(ed, 2, "selected")
    _wait_rate_done(ed)
    calls = media_lib_calls(ed, "rate")
    t.eq([(c["body"]["id"], c["body"]["rel"], c["body"]["parallel"]) for c in calls], [(lib_id(ed), REL["a"], _on(ed)["parallel"])],
         "Alpha の1曲だけ（同じ曲の行は1回・★のある Beta は除く）・同時の数を渡す")
    t.eq([_cell(ed, i, "stars")["text"] for i in (0, 1, 2)], ["NLM推定 3.21", "7.25", "9.50"], "結果は NLM推定として出る（公式の★の行はそのまま）")
    t.ok("★を計算しました（1曲・NLM推定）" in _toast(ed), f"終わりのお知らせ: {_toast(ed)}")
    # 絞り込んだ行（全部の行） → 残りは Gamma だけ
    _rate_menu(ed, 5, "filtered")
    _wait_rate_done(ed)
    t.eq([c["body"]["rel"] for c in media_lib_calls(ed, "rate")], [REL["a"], REL["c"]], "表示中の行の残り（Gamma）だけ")
    t.eq(_cell(ed, 6, "stars")["text"], "NLM推定 5.55", "Gamma の★")
    t.eq(_on(ed)["targets"]["filtered"], 0, "もう対象は無い")
    t.no_errors()


def _rate_lib(ed, n=31):
    """★の計算の同時の数・中止を確かめる、曲が n 個のライブラリ（Info.dat と Hard の譜面だけ）"""
    d = Path(ed.data_dir) / ("rate_lib_%d" % n)
    if not d.exists():
        for k in range(n):
            f = d / ("%04x (Rate %02d - M)" % (k + 0x100, k))
            f.mkdir(parents=True)
            (f / "Info.dat").write_text(json.dumps({"_version": "2.1.0", "_songName": "Rate %02d" % k, "_songAuthorName": "A", "_levelAuthorName": "M",
                                                    "_beatsPerMinute": 120, "_songFilename": "song.egg", "_difficultyBeatmapSets": [
                                                        {"_beatmapCharacteristicName": "Standard", "_difficultyBeatmaps": [
                                                            {"_difficulty": "Hard", "_beatmapFilename": "HardStandard.dat", "_noteJumpMovementSpeed": 10,
                                                             "_noteJumpStartBeatOffset": 0}]}]}), encoding="utf-8")
            (f / "HardStandard.dat").write_text(json.dumps({"_version": "2.0.0", "_notes": [{"_time": 1, "_lineIndex": 1, "_lineLayer": 0, "_type": 0, "_cutDirection": 1}],
                                                            "_obstacles": [], "_events": []}), encoding="utf-8")
    return d


def test_rate_parallel_confirm_and_stop(t):
    '''★のまとめての計算: 30曲を超える時は件数と時間の目安を見せて確認（やめると送らない）・同時に送るのは環境設定の数まで・計算中の帯「★を計算中 12/31」と行の「計算中…」・［中止］で新しく送るのをやめる'''
    clear_assets(t.ed)
    ed = open_nle(t)
    big = _rate_lib(ed)
    ed.js("localStorage.setItem('bsnm_rateParallel','2');true")
    media_lib_load(ed, paths=[big])
    media_lib_mock(ed, rate="async b=>{ %s return {ok:true,est:{version:'0.1.0',diffs:{'Standard/Hard':{stars:2.5}}}}; }" % (SLEEP % 150))
    set_view(ed, "detail")
    items = _rate_menu(ed, 0, "filtered")
    t.ok(any("31曲" in s for s in items), f"件数: {items}")
    _dialog(ed, "31曲の★を計算します", "同時に2曲ずつ", "分ほど")
    _answer(ed, False)
    ed.wait(0.3)
    t.eq((media_lib_calls(ed, "rate"), _on(ed)["rate"]["running"]), ([], False), "やめると送らない")
    _rate_menu(ed, 0, "filtered")
    _dialog(ed, "31曲")
    _answer(ed, True)
    bar = wait_until(ed, "window._dbgApp.libOnline().rate.bar", label="計算中の帯")
    t.ok(bar.startswith("★を計算中 ") and bar.endswith("/31"), f"帯: {bar}")
    busy = wait_until(ed, "(s=>s.rate.active.length?s.rate.active:null)(window._dbgApp.libOnline())", label="計算中の曲")
    i = next(k for k, r in enumerate(lib(ed)["rows"]) if r["rel"] in busy)
    st = _cell(ed, i, "stars")
    t.ok(st["text"] in ("計算中…", "NLM推定 2.50"), f"計算中の行の★の欄: {st}")
    _wait_rate_done(ed, timeout=30)
    s = _on(ed)
    t.eq((len(media_lib_calls(ed, "rate")), ed.js("window.__libMock.max.rate"), s["rate"]["maxInflight"]), (31, 2, 2), "31曲・同時に2つまで")
    t.eq({c["body"]["parallel"] for c in media_lib_calls(ed, "rate")}, {2}, "同時の数を Python 側にも渡す")
    t.eq((s["rate"]["bar"], sum(1 for i in range(31) if _cell(ed, i, "stars")["text"] == "NLM推定 2.50")), (None, 31), "帯は消え、全部の行に結果")
    # 中止: 結果を取り直して（記録には無い＝対象に戻る）もう一度始め、途中で［中止］
    ed.js("window._dbg.rt.libRefreshExtra().then(()=>true)")
    wait_until(ed, "window._dbgApp.libOnline().targets.filtered===31", label="対象に戻る")
    n0 = len(media_lib_calls(ed, "rate"))
    _rate_menu(ed, 0, "filtered")
    _dialog(ed, "31曲")
    _answer(ed, True)
    wait_until(ed, "window._dbgApp.libOnline().rate.done>=4", label="途中まで")
    click_sel(ed, "#libRateStop")
    _wait_rate_done(ed)
    sent = len(media_lib_calls(ed, "rate")) - n0
    s = _on(ed)
    t.ok(4 <= sent < 31 and sent == len(s["rate"]["sent"]) and s["rate"]["done"] == sent, f"中止の後は新しく送らない（送った分は待つ）: {sent}・{s['rate']}")
    t.ok("★の計算を中止しました" in ed.js("document.getElementById('stat').textContent"), "中止の案内")
    t.eq(s["rate"]["bar"], None, "帯は消える")
    t.no_errors()


def test_rate_not_installed_and_failures(t):
    '''★の計算: プラグインが無い＝残りを送らず、取り込み方の案内（「難易度を測る」のパネルを開ける）。計算できなかった曲は、その行の★の欄のツールチップに理由（v4 の曲はその印も）'''
    ed = _open(t)
    ed.js("localStorage.setItem('bsnm_rateParallel','1');true")
    media_lib_mock(ed, rate="async b=>{ %s return {ok:false,error:'notInstalled'}; }" % (SLEEP % 100))
    set_view(ed, "detail")
    _rate_menu(ed, 0, "filtered")
    _dialog(ed, "nlm-rating", "難易度を測る")
    t.eq(len(media_lib_calls(ed, "rate")), 1, "プラグインが無いと分かったら残りは送らない（同時の数 1）")
    _answer(ed, True)
    wait_until(ed, "(e=>e&&e.style.display!=='none')(document.getElementById('rtPanel'))", label="難易度を測るのパネル")
    wait_until(ed, "!!document.querySelector('#rtPanel .rtIntro')", label="取り込みの案内")
    ed.js("document.querySelector('#rtPanel .rtClose').click();true")
    t.eq(_on(ed)["targets"]["filtered"], 2, "プラグインが無かった曲はそのまま対象")
    media_lib_mock(ed, rate=("async b=>{ %s return b.rel===%s ? {ok:false,error:'run',detail:'unsupported map version'} : {ok:false,error:'timeout'}; }")
                   % (SLEEP % 100, json.dumps(REL["c"])))
    _rate_menu(ed, 0, "filtered")
    _wait_rate_done(ed)
    t.ok("計算できなかった曲 2" in _toast(ed), f"終わりのお知らせ: {_toast(ed)}")
    t.eq(take_errors(ed, "計算できなかった曲"), 1, "エラーの表示")
    g, a = _cell(ed, 6, "stars"), _cell(ed, 0, "stars")
    t.ok(g["text"] == "–" and "計算に失敗しました（v4 形式の譜面・unsupported map version）" in g["title"], f"v4 の曲の理由（v4 の印とプラグインの詳細を添える）: {g}")
    t.ok("計算が時間内に終わりませんでした" in a["title"], f"時間切れの理由: {a}")
    t.eq(_cell(ed, 1, "stars")["text"], "7.25", "公式の★の行はそのまま")
    s = _on(ed)["targets"]
    t.eq(s["filtered"], 0, "計算できなかった曲は、絞り込んだ行の計算では繰り返さない")
    ed.click(*row_xy(ed, 0))
    t.eq(_on(ed)["targets"]["selected"], 1, "選んだ行ならやり直せる")
    t.no_errors()


# ---------------------------------------------------------------- 環境設定の MEDIA タブ
def test_prefs_media_tab(t):
    '''環境設定の MEDIA タブ: 全曲データの状態の表示・取得する（ON/OFF＝/__lib/extra の net・ON で取得を頼む）・同時に計算する数（1〜上限）。保存して開き直しても残り、「初期設定に戻す」で初期値'''
    from misc_helpers import open_prefs, close_prefs, prefs_tab, prefs_set_number, ls, wait_mirrored, reload_keep
    ed = _open(t)
    open_prefs(ed)
    prefs_tab(ed, "media")
    p = _on(ed)["prefs"]
    hw = ed.js("navigator.hardwareConcurrency")
    t.eq((p["netOn"], p["netState"], p["parMax"], p["par"]), (True, "2026-10-12 06:30 時点のデータ", min(5, hw), min(4, hw)),
         "初期値: 取得する・状態・同時の数（上限は CPU の数と5の小さい方）")
    # 状態の表示（タブを開くたびに聞き直す）
    for resp, want in (("{state:'error',asOf:%d,fetchedAt:%d,error:'http503'}" % (SAMPLE_AS_OF, SAMPLE_AS_OF), "取得に失敗しました（前のデータを使用中: 2026-10-12 06:30 時点）"),
                       ("{state:'error',asOf:0,fetchedAt:0,error:'timed out'}", "取得に失敗しました"),
                       ("{state:'unsupported',asOf:0,fetchedAt:0}", "形式が新しすぎて使えません（NLM の更新が必要です）"),
                       ("{state:'none',asOf:0,fetchedAt:0}", "未取得")):
        media_lib_mock(ed, details=f"b=>({resp})")
        prefs_tab(ed, "app")
        prefs_tab(ed, "media")
        wait_until(ed, f"window._dbgApp.libOnline().prefs.netState==={json.dumps(want)}", label=want)
    media_lib_mock(ed, details=SAMPLE_DETAILS)
    prefs_tab(ed, "app")
    prefs_tab(ed, "media")
    # 同時に計算する数
    prefs_set_number(ed, "libRatePar", 2)
    t.eq((ls(ed, "bsnm_rateParallel"), _on(ed)["parallel"]), ("2", 2), "同時の数は bsnm_rateParallel")
    # OFF → /__lib/extra を net:false で取り直す（全曲データの値を消す）
    n0 = len(media_lib_calls(ed, "extra"))
    click_sel(ed, "#libNetOn")
    wait_until(ed, f"window.__libMock.calls.filter(c=>c.act==='extra').length>{n0}", label="OFF の取り直し")
    t.eq((ls(ed, "bsnm_libNetData"), media_lib_calls(ed, "extra")[-1]["body"]["net"]), ("0", False), "OFF＝net:false")
    t.ok("（取得しない設定のため、使っていません）" in _on(ed)["prefs"]["netState"], "状態に OFF の旨")
    # ON → 手元のデータで取り直し、取得を頼む（新しいデータが来たらもう一度取り直す）
    media_lib_mock(ed, details="b=>({state:'ok',asOf:%d,fetchedAt:%d,did:b.act==='update'?'downloaded':undefined})" % (SAMPLE_AS_OF, SAMPLE_AS_OF))
    nu, n1 = len(media_lib_calls(ed, "details")), len(media_lib_calls(ed, "extra"))
    click_sel(ed, "#libNetOn")
    wait_until(ed, f"window.__libMock.calls.filter(c=>c.act==='extra').length>={n1 + 2}", label="ON の取り直し（と新しいデータの後）")
    upd = [c for c in media_lib_calls(ed, "details")[nu:] if c["body"].get("act") == "update"]
    t.eq((ls(ed, "bsnm_libNetData"), len(upd), media_lib_calls(ed, "extra")[-1]["body"]["net"]), ("1", 1, True), "ON＝取得を頼み、net:true で取り直す")
    close_prefs(ed)
    wait_mirrored(ed, "bsnm_rateParallel", "bsnm_libNetData")
    reload_keep(ed)
    open_prefs(ed)
    prefs_tab(ed, "media")
    p = _on(ed)["prefs"]
    t.eq((p["netOn"], p["par"]), (True, 2), "開き直しても残る")
    # 初期設定に戻す（確認の後、ページを読み直す）
    ed.js("localStorage.setItem('bsnm_libNetData','0');window.__mk=1;true")
    wait_mirrored(ed, "bsnm_libNetData")
    click_sel(ed, "#settingsReset")
    _wait_reloaded(ed, "__mk")
    t.eq((ls(ed, "bsnm_libNetData"), ls(ed, "bsnm_rateParallel")), (None, None), "初期設定に戻すと消える（キーが無い＝初期値）")
    open_prefs(ed)
    prefs_tab(ed, "media")
    p = _on(ed)["prefs"]
    t.eq((p["netOn"], p["par"]), (True, min(4, hw)), "初期値（取得する・4）")
    t.no_errors()


def test_prefs_playdata(t):
    '''環境設定の MEDIA タブのプレイ記録: 状態（見つからない／読み込み済み）・自動か選んだファイルか・パス。exe 版だけ［ファイルを選ぶ…］（偽の pywebview）。［既定に戻す］で自動へ。変えたら一覧を取り直す'''
    from misc_helpers import open_prefs, prefs_tab, install_fake_pywebview, native_calls
    ed = _open(t)
    import serve   # エディタ（テストのサーバー）を用意した後に読む
    assert Path(serve.DATA_DIR).resolve() == Path(ed.data_dir).resolve(), f"serve がテストのサーバーの物ではありません: {serve.DATA_DIR}"
    h = serve.LIBRARY.get_map(lib_id(ed), REL["a"])["hash"].upper()
    rec = lambda n: {"localPlayers": [{"levelsStatsData": [
        {"levelId": "custom_level_" + h, "difficulty": d, "beatmapCharacteristicName": "Standard", "highScore": 1000, "maxCombo": 8,
         "fullCombo": False, "maxRank": 3, "validScore": True, "playCount": 2} for d in range(2, 2 + n)], "favoritesLevelIds": []}]}
    default = Path(ed.data_dir) / "PlayerData.dat"
    custom = Path(ed.data_dir) / "custom_pd" / "PlayerData.dat"
    try:
        open_prefs(ed)
        prefs_tab(ed, "media")
        p = _on(ed)["prefs"]
        t.eq((p["playState"], p["playMode"], p["pickShown"], p["exeOnlyShown"], p["resetEnabled"]),
             ("見つかりません", "自動（既定の場所）:", False, True, False), "ブラウザ版: 見つからない・選ぶボタンは無く exe 版だけの注記")
        t.eq(Path(p["playPath"]).resolve(), default.resolve(), "既定の場所")
        default.write_text(json.dumps(rec(1)), encoding="utf-8")
        prefs_tab(ed, "app")
        prefs_tab(ed, "media")
        wait_until(ed, "window._dbgApp.libOnline().prefs.playState.startsWith('読み込み済み')", label="読み込み済み")
        t.ok("1件の記録" in _on(ed)["prefs"]["playState"], f"件数: {_on(ed)['prefs']['playState']}")
        # exe 版: ファイルを選ぶ（本物は選んだファイルを Python 側で記録して状態を返す）
        install_fake_pywebview(ed)
        prefs_tab(ed, "app")
        prefs_tab(ed, "media")
        t.eq((_on(ed)["prefs"]["pickShown"], _on(ed)["prefs"]["exeOnlyShown"]), (True, False), "exe 版は［ファイルを選ぶ…］")
        custom.parent.mkdir(parents=True, exist_ok=True)
        custom.write_text(json.dumps(rec(3)), encoding="utf-8")
        st = serve.LIBRARY.set_playdata(str(custom))
        ed.js(f"window.__nat.queue.playdata.push({json.dumps(st)});true")
        n0 = len(media_lib_calls(ed, "extra"))
        click_sel(ed, "#libPlayPick")
        wait_until(ed, "window._dbgApp.libOnline().prefs.playMode==='選んだファイル:'", label="選んだファイル")
        p = _on(ed)["prefs"]
        t.eq((Path(p["playPath"]).resolve(), p["resetEnabled"]), (custom.resolve(), True), "選んだファイルのパス・［既定に戻す］が押せる")
        t.ok("3件の記録" in p["playState"], f"選んだファイルの件数: {p['playState']}")
        t.eq(len(native_calls(ed, "lib_pick_playdata")), 1, "exe 版のファイル選択（lib_pick_playdata）")
        wait_until(ed, f"window.__libMock.calls.filter(c=>c.act==='extra').length>{n0}", label="一覧の取り直し")
        wait_until(ed, "window._dbgApp.libCell(0,'plays').text==='2'", label="選んだ記録のプレイ回数")
        click_sel(ed, "#libPlayReset")
        wait_until(ed, "window._dbgApp.libOnline().prefs.playMode==='自動（既定の場所）:'", label="既定に戻す")
        t.eq((serve.LIBRARY.playdata_path()[1], _on(ed)["prefs"]["resetEnabled"]), ("auto", False), "記録も自動に戻る")
    finally:
        serve.LIBRARY.reset_playdata()
        default.unlink(missing_ok=True)
    t.no_errors()


# ---------------------------------------------------------------- 起動時の全曲データの取得
def test_details_update_once_on_boot(t):
    '''起動して記録したライブラリを読んだ後、全曲データの取得を1回だけ頼む（記録が無い時・環境設定で OFF の時は頼まない）'''
    from misc_helpers import reload_keep, wait_mirrored
    clear_assets(t.ed)
    ed = open_nle(t)
    import serve   # エディタ（テストのサーバー）を用意した後に読む
    assert Path(serve.DATA_DIR).resolve() == Path(ed.data_dir).resolve(), f"serve がテストのサーバーの物ではありません: {serve.DATA_DIR}"
    calls = []
    st = {"state": "ok", "asOf": SAMPLE_AS_OF, "fetchedAt": SAMPLE_AS_OF}
    orig_u, orig_s = serve.SONG_DETAILS.update, serve.SONG_DETAILS.status
    serve.SONG_DETAILS.update = lambda: calls.append(time.time()) or dict(st, did="throttled")
    serve.SONG_DETAILS.status = lambda: dict(st)
    try:
        reload_keep(ed)
        ed.wait(1.0)
        t.eq(len(calls), 0, "記録したライブラリが無い起動では頼まない")
        media_lib_record(ed, LIB)
        reload_keep(ed)
        wait_scanned(ed)
        wait_until(ed, "window._dbgApp.libOnline().detailsCalls===1&&!window._dbgApp.libOnline().detailsBusy", label="取得を頼む")
        ed.wait(1.0)
        t.eq(len(calls), 1, "起動ごとに1回だけ")
        set_view(ed, "detail")
        t.ok(_on(ed)["usable"] and _cell(ed, 6, "uploaded")["btn"], "全曲データを使える（全曲データに無い曲に 🔍）")
        ed.js("localStorage.setItem('bsnm_libNetData','0');true")
        wait_mirrored(ed, "bsnm_libNetData")
        reload_keep(ed)
        wait_scanned(ed)
        ed.wait(1.0)
        t.eq((len(calls), _on(ed)["detailsCalls"]), (1, 0), "OFF なら頼まない")
    finally:
        serve.SONG_DETAILS.update, serve.SONG_DETAILS.status = orig_u, orig_s
    t.no_errors()


# ---------------------------------------------------------------- 音源の実際のパス
def test_native_path_for_library_audio(t):
    '''記録したライブラリから置いた音源は実際のパスを songNode.nativePath に持つ（開き直した時に exe 版が自動で読む）。ドライブ名から始まるパスの時だけ（UNC は入れない）'''
    ed = _open(t, "basic", details=None, extra=None)
    set_view(ed, "detail")
    m = ed.js("window._dbgApp.musicScreen(4)")
    drag_from(ed, *row_xy(ed, 3), m["x"], m["top"] + m["h"] * 0.6)   # Beta（song.wav）
    wait_until(ed, "window._dbgApp.nle().music.audio&&Math.abs(window._dbgApp.nle().music.dur-2)<0.05", label="Musicレーンへのドロップ")
    want = str(LIB / REL["b"] / "song.wav")
    t.eq(ed.js("window._dbgApp.song()")["nativePath"], want, "曲の音源の実際のパス（区切りは \\）")
    pj = json.loads(ed.js("window._dbg.rt.buildProjectText()"))
    t.eq(pj["graph"]["song"].get("nativePath"), want, "プロジェクトに保存される")
    drag_from(ed, *row_xy(ed, 10), m["x"], m["top"] + m["h"] * 0.6)   # loose（譜面フォルダの外の音楽ファイル）
    wait_until(ed, f"window._dbgApp.song().nativePath==={json.dumps(str(LIB / 'Extras' / 'loose.wav'))}", label="音楽ファイルのパス")
    js = "import('./js/media/lib-native.js').then(m=>%s.map(a=>m.nativeFilePath(...a)))" % json.dumps([
        ["\\\\server\\share\\CustomLevels", "1a01 (A - B)", "song.egg"],   # UNC
        ["D:\\", "x y/z", "song.egg"],                                     # ドライブの根
        ["C:/Lib/", "a", "song.egg"],                                      # 区切りが /
        ["C:\\Lib", "a/../b", "song.egg"],                                 # 外へ出る字面
        ["C:\\Lib", "a", "x:y.egg"],                                       # ファイル名に :
        ["relative\\Lib", "a", "song.egg"],                                # 相対パス
    ])
    t.eq(ed.js(js), ["", "D:\\x y\\z\\song.egg", "C:\\Lib\\a\\song.egg", "", "", ""], "ドライブ名から始まる時だけ・1階層の名前だけ")
    t.eq(ed.js("window._dbg.rt.libSongNativePath({isMusic:true,rel:'a.wav',name:'a'}).then(v=>v)"), "", "ブラウザで選んだフォルダの音源はパスが分からない")
    t.no_errors()

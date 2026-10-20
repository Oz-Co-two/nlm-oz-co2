"""曲の解析（テンポの推定・構成の解析）の画面側。解析そのものは serve.py の /__analysis/*（Python）で、ここでは応答を偽物にする
（tests/_lib/analysis_helpers.py。送る音源は本物の basic.wav）。素材 basic は BPM 120・音源16秒（=32拍）・テンポパート無し。
帯はスペクトログラムの箱の上の段（結果がある時・解析中だけ）。結果・付け直した名前・解析した時の目盛りはプロジェクトに保存する"""
import json

from analysis_helpers import (AUDIO_ID, STRUCT, TEMPO, TEMPO_SAME, ana, ana_calls, ana_go, ana_mock, band_point, click_sel, dialog_buttons,
                              dialog_choose, dialog_lines, run_analysis, start_from_menu, status_seq, wait_band, wait_tempo_dialog)
from e2e_helpers import dirty, project, wait_until
from nle_helpers import nle, nle_mouse, open_nle, redo, take_errors, undo

WAV_SIZE = 705644   # tools/fixtures/basic.wav


def _open(t, fx="basic"):
    ed = open_nle(t, fx)
    wait_until(ed, "!document.getElementById('bootCover')&&window._dbgApp.analysis().startBtn", label="［曲を解析］が出る")
    return ed


def _bpm_lead(ed):
    return ed.js("[window._dbgApp.state().BPM, window._dbgApp.prev().leadInMs]")


def _toast(ed):
    return ed.js("(e=>e.style.display==='none'?'':e.textContent)(document.getElementById('errToast'))")


def _clear_toast(ed):
    ed.js("(e=>{e.style.display='none'; e.textContent=''; return 1})(document.getElementById('errToast'))")


def _structure_grid(ed):
    return ana_calls(ed, "structure")[-1]["body"]["grid"]


def _rename(ed, beat, text):
    """帯のセクションをダブルクリック→その場の入力欄に text を打って Enter"""
    x, y = band_point(ed, beat)
    ed.click(x, y); ed.click(x, y, count=2)
    wait_until(ed, "document.activeElement&&document.activeElement.tagName==='INPUT'&&document.activeElement.style.position==='fixed'", label="名前の入力欄")
    ed.js("(i=>{i.select(); return 1})(document.activeElement)")
    if text:
        ed.call("Input.insertText", text=text)
    else:
        ed.key("Backspace")
    ed.key("Enter")
    ed.wait(0.1)


def _menu(ed, x, y, prefix):
    """帯を右クリックして、文字が prefix で始まる項目を押す"""
    ed.click(x, y, button="right"); ed.wait(0.3)
    items = ed.js("[...document.querySelectorAll('#ctxmenu > button')].map(b=>b.textContent)")
    hit = next((i for i, s in enumerate(items) if s.startswith(prefix)), None)
    assert hit is not None, f"メニューに「{prefix}…」がありません: {items}"
    p = ed.js(f"(r=>({{x:r.left+r.width/2,y:r.top+r.height/2}}))(document.querySelectorAll('#ctxmenu > button')[{hit}].getBoundingClientRect())")
    ed.click(p["x"], p["y"]); ed.wait(0.2)
    return items


def test_analysis_flow_apply_and_undo(t):
    '''「曲を解析」の流れ: 音源（読み込んだ basic.wav のバイト列・拡張子・CSRF対策のヘッダー）を送る→テンポ→提案の画面（提案・今の値・2倍/半分・整数にした旨・
    2番目の候補（迷いあり）・段差・揺れ・裏拍と候補A/B・ノーツがある注意）→「提案を適用」で BPM 128・無音追加 265 ms→その目盛りで構成（grid と at）→
    帯が出る（名前＋番号・★）。未保存のランプが点く。Ctrl+Z で帯が消え、もう一度で BPM・無音追加が戻る。やり直しで両方戻る'''
    ed = _open(t)
    ana_mock(ed)
    start_from_menu(ed)
    wait_tempo_dialog(ed)
    up = ana_calls(ed, "upload")[0]
    t.eq((up["method"], up["headers"].get("X-NLM-Request"), up["url"], up["len"]), ("POST", "1", "__analysis/upload?ext=wav", WAV_SIZE),
         "音源を送る（POST・ヘッダー・拡張子・本体＝音源のファイルそのもの）")
    t.eq([c["body"] for c in ana_calls(ed, "tempo")], [{"audioId": AUDIO_ID}], "テンポの依頼（受け取った audioId）")
    t.ok(all(c["body"] == {"job": "t1"} for c in ana_calls(ed, "status")), "進み具合はテンポの作業（t1）を聞く")
    t.eq(ana(ed)["running"]["stage"], "decide", "テンポの確認待ち")
    lines = dialog_lines(ed)
    for want in ("テンポの推定", "提案: BPM 128 ／ 無音追加 265 ms", "今の設定: BPM 120 ／ 無音追加 0 ms",
                 "2倍の 256・半分の 64 も同じ拍の流れです（譜面の細かさで選んでかまいません）",
                 "当てはめの値は 127.982。整数の 128 でも曲全体でずれが溜まらないので整数にしました",
                 "2番目の候補: BPM 96（強さ 87%）（迷いあり。こちらも聞いて確かめてください）",
                 "0:00 128.1  0:10 126.4",
                 "どちらが拍の頭かは自動では決められないので、両方を聞いて合う方を選んでください（候補A 265 ms ／ 候補B 500 ms）",
                 "置いてあるノーツ・ライトは拍の位置のまま動きません（曲との合い方が変わります）。適用は Ctrl+Z で戻せます"):
        t.ok(want in lines, f"画面の行: {want}")
    t.ok(any(s.startswith("⚠ 0:09 あたりから、打点が目盛りより +12 ms ずれます") for s in lines), "段差の警告（時刻とずれの ms）")
    t.ok(any(s.startswith("⚠ 区間ごとのテンポの幅が 2.1% あります") for s in lines), "揺れの警告")
    t.ok(any("裏拍の疑い" in s and s.startswith("⚠ 6秒区間の 25% で") and "低い音（キック・ベース）" in s for s in lines), "裏拍の警告（両方の手がかり）")
    t.ok(not any(s.startswith("テンポパートがあります") for s in lines), "テンポパートの無い素材ではテンポパートの注意は出ない")
    t.eq([(b["v"], b["text"], b["dis"], b["pri"]) for b in dialog_buttons(ed)],
         [("a", "提案を適用", False, True), ("b", "候補B（半拍ずらし）を適用", False, False), ("none", "適用しない", False, False)], "ボタン")
    ed.key("Enter"); ed.wait(0.3)
    t.ok(ed.js("!!document.querySelector('#dirtyDlg.anaTempo')"), "Enter では何も押さない（解析の途中で急に出るため）")
    t.eq(_bpm_lead(ed), [120, 0], "まだ変わらない")
    dialog_choose(ed, "a")
    wait_band(ed)
    t.eq(_bpm_lead(ed), [128, 265], "提案を適用＝BPM 128・無音追加 265 ms（265.4 を整数に）")
    grid = _structure_grid(ed)
    t.eq((grid["bpm"], grid["leadMs"], grid["sub"]), (128, 265, 4), "構成は適用した後の目盛りで頼む")
    t.eq(grid["at"], ed.js("window._dbgApp.anaAtGrid()"), "at は今の目盛り（audioPosAtBeat）と同じ")
    t.eq(grid["at"][:4], [None, None, None, 0.087], "無音追加ぶんの頭は音が無い（null）・拍0.75＝0.3516秒−0.265秒")
    t.eq(len(grid["at"]), int((16 + 0.265) * 128 / 60 * 4) + 1, "曲末まで（拍の1/4ごと）")
    t.eq(ana_calls(ed, "structure")[0]["body"]["audioId"], AUDIO_ID, "構成も同じ audioId")
    a = ana(ed)
    t.eq(a["labels"], ["イントロ S1", "Aメロ S2", "サビ S3★", "Aメロ S2"], "帯のセクション（名前＋番号・★＝サビの候補）")
    t.eq(a["groups"], ["A", "B", "C", "D", "E", "E", "C", "D"], "細かい区切り")
    t.eq((a["shown"], a["startBtn"], a["stale"], a["canvasH"], a["specH"]), (True, False, False, 40, 54),
         "帯が出る・［曲を解析］は隠れる・スペクトログラムは帯の下へ詰める（箱の高さは同じ）")
    d = a["data"]
    t.eq((d["tempo"]["bpm"], d["tempo"]["lead_ms"], "unknown_future_field" in d["tempo"]), (128, 265.4, False), "テンポの結果を保存（知らない項目は持たない）")
    t.eq(d["grid"], {"bpm": 128, "leadMs": 265, "tp": [], "mb": 0, "ms": None, "song": "basic.wav"}, "解析した時の目盛り")
    s0 = d["structure"]["sections"][1]
    t.eq((s0["start"], s0["end"], s0["label"], s0["name"], round(s0["a0"], 3), round(s0["a1"], 3), "future" in d["structure"]["sections"][3]),
         (8, 16, "S2", "Aメロ", round(8 * 60 / 128 - 0.265, 3), round(16 * 60 / 128 - 0.265, 3), False), "セクション（解析した時の元の音源の秒つき）")
    t.eq(_toast(ed), "✅ 曲の構成を解析しました（セクション 4・細かい区切り 8）", "知らせ")
    wait_until(ed, "window._dbgApp.dirty().lamp", label="未保存のランプ")
    # Ctrl+Z: 帯 → BPM・無音追加 の順に戻る
    nle_mouse(ed)
    undo(ed)
    wait_until(ed, "!window._dbgApp.analysis().shown", label="Undo で帯が消える")
    t.eq(_bpm_lead(ed), [128, 265], "1回目の Undo では BPM はそのまま")
    undo(ed)
    wait_until(ed, "window._dbgApp.state().BPM===120", label="2回目の Undo で BPM が戻る")
    t.eq(_bpm_lead(ed), [120, 0], "無音追加も一緒に戻る")
    redo(ed); redo(ed)
    wait_until(ed, "window._dbgApp.analysis().shown", label="やり直しで帯が戻る")
    t.eq(_bpm_lead(ed), [128, 265], "やり直しで BPM・無音追加も戻る")
    t.eq(ana(ed)["stale"], False, "目盛りは解析した時と同じ")
    t.no_errors()


def test_analysis_candidate_b_and_skip(t):
    '''テンポの画面で「候補B（半拍ずらし）」＝無音追加 500 ms（499.8 を整数に）で構成を頼む／「適用しない」＝今の値のまま（at は 0.125 秒ずつ・曲末は音が無い）'''
    ed = _open(t)
    run_analysis(ed, "b")
    t.eq(_bpm_lead(ed), [128, 500], "候補B")
    t.eq((_structure_grid(ed)["bpm"], _structure_grid(ed)["leadMs"]), (128, 500), "候補Bの目盛りで構成")
    ed = _open(t)
    run_analysis(ed, "none")
    t.eq(_bpm_lead(ed), [120, 0], "適用しない＝変えない")
    g = _structure_grid(ed)
    t.eq((g["bpm"], g["leadMs"], len(g["at"])), (120, 0, 129), "今の目盛りで構成（拍0〜32）")
    t.eq((g["at"][0], g["at"][1], g["at"][4], g["at"][127], g["at"][128]), (0, 0.125, 0.5, 15.875, None), "at＝拍×0.5秒（曲末＝16秒は音が無い）")
    t.no_errors()


def test_analysis_same_tempo_no_dialog(t):
    '''テンポの推定が今の BPM・無音追加と同じ（無音追加は ±1ms まで同じとみなす）なら、適用の画面を出さずに構成へ進む'''
    ed = _open(t)
    ed.js("window.__dlgSeen=false; new MutationObserver(()=>{ if(document.querySelector('#dirtyDlg.anaTempo')) window.__dlgSeen=true; })"
          ".observe(document.body,{childList:true,subtree:true}); true")
    run_analysis(ed, None, tempo=TEMPO_SAME)
    t.eq(ed.js("window.__dlgSeen"), False, "テンポの画面は出ない")
    t.eq(ed.js("document.getElementById('stat').textContent"), "テンポの推定: 今の BPM・無音追加と同じです", "下の案内")
    t.eq(_bpm_lead(ed), [120, 0], "変えない")
    t.no_errors()


def test_analysis_progress_and_cancel(t):
    '''解析中は帯に進み具合と［やめる］（その間も編集できる＝帯の外は普通に操作できる）。［やめる］で作業の取り消しを送り、帯は消える。
    遅れて届いた結果は使わない。ファイルメニューから2回目を押しても重ねて始めない'''
    ed = _open(t)
    ana_mock(ed, status_t1=[{"ok": True, "state": "running", "stage": "tempo", "progress": 0.4},
                            {"waitFor": "late", "then": {"ok": True, "state": "done", "stage": "tempo", "progress": 1, "result": TEMPO}}])
    click_sel(ed, "#anaStartBtn")
    wait_until(ed, "(a=>a.running&&a.running.stage==='tempo'&&a.msg.includes('40%'))(window._dbgApp.analysis())", label="進み具合 40%")
    a = ana(ed)
    t.eq((a["shown"], a["startBtn"], a["msg"]), (True, False, "曲を解析中: テンポを推定 40%やめる"), "帯に進み具合と［やめる］")
    t.eq(ed.js("document.querySelector('#anaMsg .amBar i').style.width"), "17%", "全体の進み具合のバー（テンポは5〜35%の間）")
    start_from_menu(ed)
    t.eq(ed.js("document.getElementById('stat').textContent"), "曲を解析しています（やめる時は帯の［やめる］）", "2回目は重ねて始めない")
    t.eq(len(ana_calls(ed, "upload")), 1, "送ったのは1回だけ")
    # 解析中も編集できる（BPM の欄を変えられる）
    click_sel(ed, "#bpmField .bfA[data-k=up]")
    wait_until(ed, "window._dbgApp.state().BPM===121", label="解析中に BPM を変えられる")
    click_sel(ed, "#anaMsg .amBtn")
    wait_until(ed, "!window._dbgApp.analysis().shown", label="やめると帯が消える")
    t.eq([c["body"] for c in ana_calls(ed, "cancel")], [{"job": "t1"}], "作業の取り消しを送る")
    t.eq(ed.js("document.getElementById('stat').textContent"), "曲の解析をやめました", "下の案内")
    ana_go(ed, "late")
    ed.wait(1.2)
    t.eq((ana(ed)["data"], ana(ed)["dialog"], len(ana_calls(ed, "structure"))), (None, False, 0), "遅れて届いた結果は使わない（画面も出ない・構成も頼まない）")
    t.ok(ana(ed)["startBtn"], "［曲を解析］が戻る")
    t.no_errors()


def _msg_box(ed):
    """帯の上の知らせ: 種類・帯（キャンバス）の左端／右端からの位置・塗り・文字の色・動き（枠の光・バーの縞のアニメーション名）"""
    return ed.js("""(()=>{ const m=document.getElementById('anaMsg'), c=document.getElementById('anacv').getBoundingClientRect(), r=m.getBoundingClientRect(),
        cs=getComputedStyle(m), i=m.querySelector('.amBar i');
      const b=m.querySelector('.amBar'), br=b?b.getBoundingClientRect():null;
      return {mode:m.className, left:Math.round(r.left-c.left), right:Math.round(c.right-r.right), top:Math.round(r.top-c.top), h:Math.round(r.height),
        w:Math.round(r.width*10)/10, barL:br?Math.round((br.left-c.left)*10)/10:null, barLen:br?Math.round(br.width):null,
        bg:cs.backgroundColor, color:cs.color, pulse:getComputedStyle(m,'::before').animationName,
        flow:i?getComputedStyle(i,'::after').animationName:null, barW:i?i.style.width:null}; })()""")


def test_analysis_running_msg_left_and_motion(t):
    '''解析中の知らせ（2026-10-20・利用者の要望）: 帯の左寄せ（溝 128px のすぐ右＝画面の中央寄り）・濃い紫の塗りと白い文字・枠の光がゆっくり明滅し、
    進み具合のバーに縞が流れる。進み具合が届いても部品は作り直さない（縞が頭から跳ねない）・［やめる］は押せる。動きを減らす設定では止める。
    目盛りが変わった時の知らせは今までどおり右寄せ（帯の結果の上に出るので、左だと帯の頭の区切りを隠す）'''
    ed = _open(t)
    ana_mock(ed, tempo=TEMPO_SAME, status_t1=[{"ok": True, "state": "running", "stage": "tempo", "progress": 0.04},
                                             {"waitFor": "a", "then": {"ok": True, "state": "running", "stage": "tempo", "progress": 0.4}},
                                             {"waitFor": "p", "then": {"ok": True, "state": "running", "stage": "tempo", "progress": 0.7}},
                                             {"waitFor": "late", "then": status_seq("tempo", TEMPO_SAME)[-1]}])
    click_sel(ed, "#anaStartBtn")
    wait_until(ed, "window._dbgApp.analysis().msg.includes(' 4%')", label="進み具合 4%（1桁）")
    m1 = _msg_box(ed)
    t.eq(m1["barLen"], 220, f"バーは長め（220px）: {m1}")
    ana_go(ed, "a")
    wait_until(ed, "window._dbgApp.analysis().msg.includes('40%')", label="進み具合 40%")
    m = _msg_box(ed)
    # 数字の桁が変わっても箱の長さ・バーの位置は動かない（利用者の要望: 伸び縮みすると進んだり戻ったりして見えた）
    t.eq((m["w"], m["barL"]), (m1["w"], m1["barL"]), f"1桁→2桁で箱の幅・バーの位置が同じ: {m1} → {m}")
    t.eq((m["mode"], m["left"], m["top"], m["h"]), ("run", 136, 5, 30), f"帯の左寄せ（溝 128px のすぐ右）: {m}")
    t.ok(m["right"] > m["left"], f"右には寄せない（帯の左半分寄り）: {m}")
    t.eq((m["bg"], m["color"]), ("rgb(58, 42, 124)", "rgb(255, 255, 255)"), "濃い紫の塗り・白い文字")
    t.eq((m["pulse"], m["flow"], m["barW"]), ("anaRunPulse", "anaBarFlow", "17%"), "枠の光の明滅・バーに流れる縞・進み具合の幅")
    # 進み具合が届いても部品は作り直さない（縞のアニメーションが頭から跳ねない）
    ed.js("document.querySelector('#anaMsg .amBar i').__keep=1; document.querySelector('#anaMsg .amBtn').__keep=1; true")
    ana_go(ed, "p")
    wait_until(ed, "window._dbgApp.analysis().msg.includes('70%')", label="進み具合 70%")
    t.eq(ed.js("[document.querySelector('#anaMsg .amBar i').__keep, document.querySelector('#anaMsg .amBtn').__keep, document.querySelector('#anaMsg .amBar i').style.width]"),
         [1, 1, "26%"], "同じ部品のまま、文とバーの幅だけ変わる")
    t.eq(ana(ed)["msg"], "曲を解析中: テンポを推定 70%やめる", "文")
    m7 = _msg_box(ed)
    t.eq((m7["w"], m7["barL"]), (m1["w"], m1["barL"]), f"70% でも箱の幅・バーの位置が同じ: {m7}")
    # 動きを減らす設定では止める（枠の光は止めて薄く残す）
    ed.call("Emulation.setEmulatedMedia", features=[{"name": "prefers-reduced-motion", "value": "reduce"}])
    ed.wait(0.1)
    m = _msg_box(ed)
    t.eq((m["pulse"], m["flow"]), ("none", "none"), "動きを減らす設定では止める")
    ed.call("Emulation.setEmulatedMedia", features=[])
    # ［やめる］は押せる
    click_sel(ed, "#anaMsg .amBtn")
    wait_until(ed, "!window._dbgApp.analysis().shown", label="やめる")
    t.eq([c["body"] for c in ana_calls(ed, "cancel")], [{"job": "t1"}], "作業の取り消しを送る")
    ana_go(ed, "late")
    ed.wait(0.3)   # やめた作業の止まっていた応答を返し終えてから、次の偽の応答に差し替える
    # 目盛りが変わった時の知らせは右寄せのまま
    run_analysis(ed, None, tempo=TEMPO_SAME)
    click_sel(ed, "#bpmField .bfA[data-k=up]")
    wait_until(ed, "window._dbgApp.analysis().stale", label="目盛りが変わった")
    m = _msg_box(ed)
    t.eq((m["mode"], m["right"], m["top"], m["pulse"], m["flow"]), ("stale", 8, 5, "none", None), f"目盛りの知らせは右寄せ・動かない: {m}")
    t.ok(m["left"] > 400, f"帯の頭（左）は隠さない: {m}")
    t.eq(m["bg"], "rgba(18, 18, 24, 0.94)", "目盛りの知らせの塗りは今までどおり")
    t.no_errors()


def test_analysis_errors(t):
    '''失敗の種類ごとの表示（大きすぎる・読めない音源・作業が見つからない・解析の失敗・通信の失敗・知らない種類・結果の形が違う）と、この版のサーバーに API が無い（404）時の
    「この版では解析を使えません」。失敗しても帯は出ず、前の結果も消さない'''
    ed = _open(t)
    cases = [
        ("音源が大きすぎる", {"upload": {"http": 413, "body": {"ok": False, "error": "too-large"}}}, "⚠ 音源のファイルが大きすぎて解析できません"),
        ("読めない音源", {"upload": {"ok": False, "error": "bad-audio"}}, "⚠ 音源を読み込めませんでした（壊れているか、対応していない形式です）"),
        ("作業が見つからない", {"status_t1": [{"ok": False, "error": "unknown-job"}]},
         "⚠ 解析の作業が見つかりません（アプリを起動し直した等）。もう一度［曲を解析］を押してください"),
        ("解析の失敗", {"status_t1": [{"ok": True, "state": "error", "stage": "tempo", "progress": 0.3, "result": None, "error": "failed"}]}, "⚠ 曲の解析に失敗しました"),
        ("通信の失敗", {"upload": {"netErr": True}}, "⚠ 解析のサーバーに接続できませんでした"),
        ("知らない種類", {"req_structure": {"ok": False, "error": "weird-thing"}}, "⚠ 曲の解析に失敗しました（weird-thing）"),
        ("結果の形が違う", {"status_s1": status_seq("structure", {"sections": "x"})}, "⚠ 曲の解析に失敗しました"),
        ("API が無い（404・本文なし）", {"upload": {"http": 404, "body": None}}, "⚠ この版では解析を使えません"),
        ("API が無い（serve.py の unknown endpoint）", {"upload": {"http": 404, "body": {"ok": False, "error": "unknown endpoint"}}}, "⚠ この版では解析を使えません"),
    ]
    for label, over, want in cases:
        _clear_toast(ed)
        ana_mock(ed, tempo=TEMPO_SAME, **over)
        click_sel(ed, "#anaStartBtn")
        wait_until(ed, "(a=>!a.running&&!a.shown&&a.startBtn)(window._dbgApp.analysis())&&document.getElementById('errToast').style.display!=='none'", label=label)
        t.eq(_toast(ed), want, label)
        t.eq(ana(ed)["data"], None, label + ": 結果は無い")
        take_errors(ed, want[2:])
    # 前の結果があれば、失敗しても消さない
    run_analysis(ed, None, tempo=TEMPO_SAME)
    _clear_toast(ed)
    ana_mock(ed, tempo=TEMPO_SAME, upload={"ok": False, "error": "bad-audio"})
    start_from_menu(ed)
    wait_until(ed, "!window._dbgApp.analysis().running&&document.getElementById('errToast').style.display!=='none'", label="2回目の失敗")
    take_errors(ed, "音源を読み込めませんでした")
    t.eq(ana(ed)["labels"], ["イントロ S1", "Aメロ S2", "サビ S3★", "Aメロ S2"], "前の結果はそのまま")
    t.no_errors()


def test_analysis_band_click_rename_markers_clear(t):
    '''帯: クリック＝その頭へ（セクション・細かい区切り）／ダブルクリック＝番号ごとに名前を付け直す（同じ番号の全部・未保存のランプ・空にすると自動の名前）／
    右クリック「セクションの頭にマーカーを書き出す」（同じ位置の手で置いたマーカーは変えない・付け直した後の書き出しは名前を直す・Undo 1回で戻る）／
    「解析の結果を消す」→ Ctrl+Z で戻る'''
    ed = _open(t)
    run_analysis(ed, "none")
    x, y = band_point(ed, 18)
    ed.click(x, y)
    wait_until(ed, "window._dbgApp.state().cur===16", label="S3（拍16〜）の頭へ")
    x, y = band_point(ed, 22.5, "seg")
    ed.click(x, y)
    wait_until(ed, "window._dbgApp.state().cur===20", label="細かい区切り E（拍20〜）の頭へ")
    t.eq(nle(ed)["markers"], [], "マーカーはまだ無い")
    # 名前の付け直し（同じ番号 S2 の2つとも変わる）
    _rename(ed, 10, "ばーす")
    t.eq(ana(ed)["labels"], ["イントロ S1", "ばーす S2", "サビ S3★", "ばーす S2"], "S2 の2つとも名前が変わる")
    t.eq(ana(ed)["data"]["names"], {"S2": "ばーす"}, "付け直した名前は番号ごとに保存")
    wait_until(ed, "window._dbgApp.dirty().lamp", label="未保存のランプ")
    t.eq(ed.js("document.getElementById('stat').textContent"), "S2 の名前: ばーす（同じ番号のセクション全部）", "下の案内")
    # 手で置いたマーカー（拍16）→ 書き出す: 拍16は飛ばす
    ed.click(*band_point(ed, 18)); wait_until(ed, "window._dbgApp.state().cur===16", label="拍16へ")
    nle_mouse(ed); ed.key("e", ctrl=True)
    wait_until(ed, "window._dbgApp.nle().markers.length===1", label="手で置いたマーカー")
    _clear_toast(ed)
    _menu(ed, *band_point(ed, 4), "セクションの頭にマーカーを書き出す")
    mk = nle(ed)["markers"]
    t.eq([(m["beat"], m["name"]) for m in mk], [(0, "イントロ S1"), (8, "ばーす S2"), (16, "マーカー1"), (24, "ばーす S2")], "セクションの頭に名前付きのマーカー（拍16の手で置いた物は変えない）")
    t.eq(_toast(ed), "✅ セクションの頭にマーカーを 3 個足しました・1 個は同じ位置に別のマーカーがあるため飛ばしました", "知らせ")
    # 名前を直してもう一度 → 書き出したマーカーの名前を直す
    _rename(ed, 2, "前奏")
    _clear_toast(ed)
    _menu(ed, *band_point(ed, 4), "セクションの頭にマーカーを書き出す")
    t.eq([m["name"] for m in nle(ed)["markers"]], ["前奏 S1", "ばーす S2", "マーカー1", "ばーす S2"], "書き出したマーカーの名前を直す")
    t.eq(_toast(ed), "✅ 1 個のマーカーの名前を直しました・1 個は同じ位置に別のマーカーがあるため飛ばしました", "知らせ")
    nle_mouse(ed); undo(ed)
    wait_until(ed, "window._dbgApp.nle().markers[0].name==='イントロ S1'", label="Undo 1回で書き出しの前へ")
    # 空にすると自動の名前に戻る
    _rename(ed, 2, "")
    t.eq(ana(ed)["labels"][0], "イントロ S1", "空＝自動の名前")
    t.eq(ana(ed)["data"]["names"], {"S2": "ばーす"}, "S1 の付け直しは消える")
    # 結果を消す → Ctrl+Z
    items = _menu(ed, *band_point(ed, 4, "seg"), "解析の結果を消す")
    t.eq(items, ["クリップを作る…", "セクションの頭にマーカーを書き出す", "テンポの推定結果…", "解析し直す", "解析の結果を消す"], "細かい区切りの右クリックのメニュー（名前の付け直しはセクションの上だけ）")
    wait_until(ed, "!window._dbgApp.analysis().shown", label="帯が消える")
    t.eq((ana(ed)["data"], ana(ed)["startBtn"]), (None, True), "結果が無くなり［曲を解析］が戻る")
    nle_mouse(ed); undo(ed)
    wait_until(ed, "window._dbgApp.analysis().shown", label="Ctrl+Z で戻る")
    t.eq(ana(ed)["labels"][1], "ばーす S2", "付け直した名前も戻る")
    t.no_errors()


def test_analysis_tempo_result_from_menu(t):
    '''帯の「⋯」→「テンポの推定結果…」で見返せる（適用した方には「（今の設定）」・押せない）。ここから候補Bを適用すると BPM・無音追加が変わり、帯は「解析し直して」になる'''
    ed = _open(t)
    run_analysis(ed, "a")
    click_sel(ed, "#anaMenuBtn")
    items = ed.js("[...document.querySelectorAll('#ctxmenu > button')].map(b=>b.textContent)")
    t.eq(items, ["クリップを作る…", "セクションの頭にマーカーを書き出す", "テンポの推定結果…", "解析し直す", "解析の結果を消す"], "⋯ のメニュー")
    ed.js("[...document.querySelectorAll('#ctxmenu > button')].find(b=>b.textContent==='テンポの推定結果…').click(); true")
    wait_tempo_dialog(ed)
    t.eq([(b["v"], b["text"], b["dis"]) for b in dialog_buttons(ed)],
         [("a", "提案を適用（今の設定）", True), ("b", "候補B（半拍ずらし）を適用", False), ("none", "閉じる", False)], "見返す時のボタン")
    t.ok("適用しなくても、今の BPM・無音追加のまま構成を解析します" not in dialog_lines(ed), "解析の途中の注意は出ない")
    dialog_choose(ed, "b")
    wait_until(ed, "window._dbgApp.prev().leadInMs===500", label="候補Bを適用")
    wait_until(ed, "window._dbgApp.analysis().stale", label="帯は「解析し直して」")
    t.no_errors()


def test_analysis_stale_and_reanalyze_keeps_names(t):
    '''目盛り（BPM・無音追加・テンポパート・Music の配置）を変えると帯に「目盛りが変わりました。解析し直してください」→ 戻すと消える。
    ［解析し直す］で帯だけ置き換え、付け直した名前は同じ位置の番号へ引き継ぐ（番号が変わっても）'''
    ed = _open(t)
    run_analysis(ed, "none")
    t.eq(ana(ed)["msg"], "", "知らせは無い")
    click_sel(ed, "#bpmField .bfA[data-k=up]")
    wait_until(ed, "window._dbgApp.analysis().stale", label="BPM を変えた")
    t.eq(ana(ed)["msg"], "⚠ 目盛りが変わりました。解析し直してください解析し直す", "帯の知らせ")
    t.ok("Music の配置" in ed.js("document.getElementById('anaMsg').title"), "知らせのツールチップ")
    click_sel(ed, "#bpmField .bfA[data-k=dn]")
    wait_until(ed, "!window._dbgApp.analysis().stale", label="BPM を戻した")
    click_sel(ed, "#leadInField .bfA[data-k=up]")
    wait_until(ed, "window._dbgApp.analysis().stale", label="無音追加を変えた")
    click_sel(ed, "#leadInField .bfA[data-k=dn]")
    wait_until(ed, "!window._dbgApp.analysis().stale", label="無音追加を戻した")
    # テンポパート（テンポの帯の右クリック）
    s = ed.js("window._dbgApp.nleScreen(8)")
    ed.click(s["x"], s["tempo"] + 7, button="right"); ed.wait(0.3)
    ed.js("[...document.querySelectorAll('#ctxmenu > button')].find(b=>b.textContent.startsWith('＋')).click(); true")
    wait_until(ed, "window._dbgApp.analysis().stale", label="テンポパートを足した")
    nle_mouse(ed); undo(ed)
    wait_until(ed, "!window._dbgApp.analysis().stale", label="テンポパートを戻した")
    # 名前を付け直してから、番号の振り方が違う結果で解析し直す（S2→S3・S3→S2）
    _rename(ed, 10, "ばーす")
    st2 = json.loads(json.dumps(STRUCT))
    for sec in st2["sections"]:
        sec["label"] = {"S2": "S3", "S3": "S2"}.get(sec["label"], sec["label"])
    ana_mock(ed, tempo=TEMPO_SAME, structure=st2)
    click_sel(ed, "#mFileBtn"); click_sel(ed, "#mFileMenu button[data-act=analyze]")
    wait_until(ed, "(a=>!a.running&&a.labels[1]!=='ばーす S2')(window._dbgApp.analysis())", label="解析し直した帯")
    t.eq(ana(ed)["labels"], ["イントロ S1", "ばーす S3", "サビ S2★", "ばーす S3"], "名前は同じ位置の番号（S3）へ引き継ぐ")
    t.eq(ana(ed)["data"]["names"], {"S3": "ばーす"}, "保存も新しい番号で")
    nle_mouse(ed); undo(ed)
    wait_until(ed, "window._dbgApp.analysis().labels[1]==='ばーす S2'", label="Undo で前の帯へ")
    t.no_errors()


def test_analysis_save_and_reopen(t):
    '''結果（テンポ・構成・付け直した名前・解析した時の目盛り）はプロジェクトに保存され、開き直すと帯と名前が戻る（目盛りも同じ＝知らせは出ない）。
    結果が無ければプロジェクトに analysis のキーを書かない。ファイル由来のおかしな値（数でない拍・無い番号の名前）は捨てる'''
    ed = _open(t)
    t.ok("analysis" not in project(ed), "解析していなければキーごと無い")
    run_analysis(ed, "a")
    _rename(ed, 18, "サビ！")
    pj = project(ed)
    a = pj["analysis"]
    t.eq((a["v"], a["names"], a["grid"]["bpm"], a["grid"]["leadMs"], len(a["structure"]["sections"]), len(a["structure"]["segments"]), a["tempo"]["bpm"]),
         (1, {"S3": "サビ！"}, 128, 265, 4, 8, 128), "保存の中身")
    # 開き直す（音源は読み込み直さない＝帯は音源が無くても出る）
    a["names"]["S9"] = "無い番号"
    a["structure"]["sections"].append({"start": "x", "end": 4, "label": "S1"})
    a["structure"]["segments"].append({"start": 40, "end": 30, "group": "Z"})
    ed.js(f"(async()=>{{ await window._dbg.rt.applyProject({json.dumps(pj, ensure_ascii=False)}); return 1; }})()")
    wait_until(ed, "window._dbgApp.analysis().shown", label="開き直した帯")
    b = ana(ed)
    t.eq(b["labels"], ["イントロ S1", "Aメロ S2", "サビ！ S3★", "Aメロ S2"], "帯と付け直した名前が戻る")
    t.eq(b["data"]["names"], {"S3": "サビ！"}, "無い番号の名前は捨てる")
    t.eq((len(b["data"]["structure"]["sections"]), len(b["data"]["structure"]["segments"])), (4, 8), "おかしな区間は捨てる")
    t.eq((b["stale"], b["msg"]), (False, ""), "目盛りは同じ（BPM・無音追加もプロジェクトから戻る）")
    t.eq(_bpm_lead(ed), [128, 265], "BPM・無音追加")
    # 新規にすると消える
    ed.js("(async()=>{ await window._dbg.rt.applyProject(null); return 1; })()")
    wait_until(ed, "!window._dbgApp.analysis().shown", label="新規で帯が消える")
    t.no_errors()


def _ms(ed, beat):
    return ed.js(f"window._dbgApp.musicScreen({beat})")


def _my(ed):
    m = _ms(ed, 0)
    return m["top"] + m["h"] * 0.6


def test_analysis_at_follows_music_placement(t):
    '''構成に送る at（拍ごとの元の音源の秒）は Music の配置どおり: Music を拍4へ動かす→拍4が0秒・それより前は null／無音追加 10ms→0.01秒ずれる／
    拍20で分割して後ろを拍24へ動かす→拍20〜24は null・拍24が元の8秒。帯は「解析し直して」になる'''
    ed = _open(t)
    run_analysis(ed, None, tempo=TEMPO_SAME)
    ed.drag(_ms(ed, 10)["x"], _my(ed), _ms(ed, 14)["x"], _my(ed), steps=10)
    wait_until(ed, "window._dbgApp.nle().music.beat===4", label="Music を拍4へ")
    wait_until(ed, "window._dbgApp.analysis().stale", label="Music の配置で「解析し直して」")
    at = ed.js("window._dbgApp.anaAtGrid()")
    t.eq((len(at), at[15], at[16], at[17], at[143], at[144]), (145, None, 0, 0.125, 15.875, None), "Music を拍4へ（拍4〜36）")
    click_sel(ed, "#leadInField .bfA[data-k=up]")
    wait_until(ed, "window._dbgApp.prev().leadInMs===10", label="無音追加 10ms")
    at = ed.js("window._dbgApp.anaAtGrid()")
    t.eq((at[16], at[17], at[18]), (None, 0.115, 0.24), "無音追加ぶん遅れる（拍4は無音・拍4.25は0.125−0.01秒）")
    click_sel(ed, "#leadInField .bfA[data-k=dn]")
    wait_until(ed, "window._dbgApp.prev().leadInMs===0", label="無音追加を戻す")
    # 拍20で分割（Music を選んで C）→ 後ろだけ選んで拍24へ
    ed.click(_ms(ed, 6)["x"], _my(ed))
    wait_until(ed, "window._dbgApp.nle().music.sel.length===1", label="Music の選択")
    ed.move(_ms(ed, 20)["x"], _my(ed))
    wait_until(ed, "Math.abs((window._dbgApp.nle().hover??-99)-20)<1e-6", label="拍20にマウス")
    ed.key("c")
    wait_until(ed, "(window._dbgApp.nle().music.segs||[]).length===2", label="拍20で分割")
    if 0 in nle(ed)["music"]["sel"]:
        ed.click(_ms(ed, 8)["x"], _my(ed), shift=True)
        wait_until(ed, "!window._dbgApp.nle().music.sel.includes(0)", label="前の区間の選択を外す")
    ed.drag(_ms(ed, 28)["x"], _my(ed), _ms(ed, 32)["x"], _my(ed), steps=10)
    wait_until(ed, "(window._dbgApp.nle().music.segs||[])[1]&&window._dbgApp.nle().music.segs[1].beat===24", label="後ろの区間を拍24へ")
    at = ed.js("window._dbgApp.anaAtGrid()")
    t.eq((at[79], at[80], at[95], at[96], at[97], len(at)), (7.875, None, None, 8, 8.125, 161), "拍20〜24は音が無い・拍24が元の8秒（曲末は拍40）")
    t.no_errors()


def test_analysis_english_wording(t):
    '''英語表示: 帯の自動の名前（Intro/Verse/Chorus）・溝の文字・ツールチップ・テンポの画面のボタン・目盛りが変わった知らせ'''
    from nlmtest import LIGHT_RENDER_JS
    ed = t.fresh()
    ed.js("localStorage.setItem('bsnm_lang','en');true")
    ed.wait(0.6)
    ed.reload(clear_storage=False)
    ed.js(LIGHT_RENDER_JS)
    wait_until(ed, "!document.getElementById('bootCover')&&document.getElementById('mFileBtn').textContent.trim()==='File'", label="英語で起動")
    ed.load_fixture("basic", settle=0.3)
    wait_until(ed, "window._dbgApp.analysis().startBtn", label="［Analyze song］")
    t.eq(ed.js("document.getElementById('anaStartBtn').textContent"), "🎼 Analyze song", "溝のボタン")
    t.eq(ed.js("document.querySelector('#mFileMenu button[data-act=analyze]').textContent"), "Analyze song (tempo & structure)…", "ファイルメニュー")
    ana_mock(ed)
    click_sel(ed, "#anaStartBtn")
    wait_tempo_dialog(ed)
    t.eq([b["text"] for b in dialog_buttons(ed)], ["Apply suggestion", "Apply B (half-beat shift)", "Don't apply"], "テンポの画面のボタン")
    t.ok("Suggested: BPM 128 / lead-in silence 265 ms" in dialog_lines(ed), "提案の行")
    dialog_choose(ed, "none")
    wait_band(ed)
    t.eq(ana(ed)["labels"], ["Intro S1", "Verse S2", "Chorus S3★", "Verse S2"], "自動の名前は英語に訳す")
    x, y = band_point(ed, 10)
    ed.move(x, y); ed.wait(0.2)
    t.eq(ed.js("document.getElementById('anacv').title"),
         "Verse S2 · 2× this number · beats 8–16\nClick = go here / Double-click = rename (all sections with this number) / Right-click = menu", "ツールチップ")
    click_sel(ed, "#bpmField .bfA[data-k=up]")
    wait_until(ed, "window._dbgApp.analysis().stale", label="目盛りが変わった")
    t.eq(ana(ed)["msg"], "⚠ The beat grid has changed. Please analyze againAnalyze again", "知らせ")
    t.no_errors()

"""左上の窓の3つ目「REPLAY」（js/replay/replay-pane.js・2026-11-22）: 遊んだリプレイの一覧・BL のリプレイアプリの窓・再生位置の同期・書き出しの控え。

本物の裏側（serve.py の /__replay/* と viewer のサーバー）は別の作業で作る＝ここでは応答を偽物にし（tests/_lib/replay_helpers.py の rp_mock）、
リプレイの窓は偽の窓（http://localhost:<番号> の小さなページ・取り決めの伝言を話す）を本当に iframe に開く（CSP の frame-src・sandbox・
相手のオリジンの確かめも本物と同じ道を通る）。時刻はリプレイの秒＝NLM の beatToTimeTM(拍)（素材 rich は BPM 120＝1 拍 0.5 秒）。
"""
import json

from misc_helpers import (OUT_BASE, click_sel, export_click, file_menu, install_fake_pywebview, native_queue, native_writes,
                          open_fixture_ready, stub_convert, to_info, wait_until)
from replay_helpers import (ITEMS, STATUS, call_parts, click_id, click_row, fake_viewer, hover_pv, item, load_named, open_replay, rp,
                            rp_calls, rp_clear_log, rp_frame_state, rp_log, rp_mock, rp_set, rp_user, rp_user_raw, rp_watch, sha1_of, to_replay,
                            wait_list, wait_nlm_sec, wait_state)

SONG = {"name": "リッチ テスト曲", "mapper": "NLM Tester"}


def _diff(ed):
    return ed.js("(d=>d?d.replace(/Standard\\.dat$/i,''):null)(window._dbgApp.state().diff)")


def _main(ed):
    return ed.js("document.querySelector('#pvModeLabel .mlMain')&&document.querySelector('#pvModeLabel .mlMain').textContent")


def _hover_nle(ed):
    g = ed.js("window._dbgApp.nleScreen(0)")
    ed.move(g["left"] + g["w"] * 0.6, g["lanes"] + 40)
    ed.wait(0.15)


def _key_nle(ed, k, **mods):
    _hover_nle(ed)
    ed.key(k, **mods)


# ---------------------------------------------------------------- 切り替え
def test_replay_mode_cycle(t):
    '''左上の窓は MEDIA → PREVIEW → REPLAY → MEDIA（Tab・見出しの「[TAB] 次」のクリックのどちらでも）。REPLAY の間は PREVIEW の3Dの面を隠す・
    REPLAY を出すと一覧を頼み、離れると窓を止める'''
    ed = open_fixture_ready(t, "rich")
    rp_mock(ed)
    rp_watch(ed)
    t.eq(_main(ed), "MEDIA", "最初は MEDIA")
    seq = []
    for _ in range(3):
        hover_pv(ed)
        ed.key("Tab")
        wait_until(ed, f"window._dbgApp.replay().pvMode!=={json.dumps(seq[-1] if seq else 'media')}", label="Tab で次へ")
        m = ed.js("window._dbgApp.replay().pvMode")
        seq.append(m)
        wait_until(ed, f"(e=>!!e&&e.textContent==={json.dumps(m.upper())})(document.querySelector('#pvModeLabel .mlMain'))", label=f"帯が {m}")
        if m == "replay":
            on = ed.js("['bodyPv','tabFolder','bodyRp'].map(id=>document.getElementById(id).classList.contains('on'))")
            t.eq(on, [False, False, True], "REPLAY の時は PREVIEW・MEDIA の面を隠す")
            t.eq(ed.js("document.querySelector('#pvModeLabel .mlNext').title"), "クリックで MEDIA へ切り替え", "REPLAY の次は MEDIA")
            wait_list(ed, len(ITEMS))
            wait_state(ed, "linked")
    t.eq(seq, ["preview", "replay", "media"], "Tab の順")
    t.ok(rp_log(ed, "pause"), "REPLAY から離れるとリプレイを止める")
    t.eq(rp(ed)["nlm"]["linked"], False, "離れると外す")
    # 見出しのクリックでも同じ順
    seq = []
    for _ in range(3):
        prev = ed.js("window._dbgApp.replay().pvMode")
        click_sel(ed, "#pvModeLabel .mlNext", "［TAB］ 次")
        wait_until(ed, f"window._dbgApp.replay().pvMode!=={json.dumps(prev)}", label="クリックで次へ")
        seq.append(ed.js("window._dbgApp.replay().pvMode"))
    t.eq(seq, ["preview", "replay", "media"], "クリックの順")
    t.eq(len(rp_calls(ed, "list")), 1, "同じ曲なら2回目に出した時は一覧を読み直さない")
    t.no_errors()


# ---------------------------------------------------------------- 一覧
def test_replay_list_rows(t):
    '''一覧: 今の曲（曲名・マッパー）のリプレイを新しい順に。行＝日時・難易度・精度・ミス・札（やめた／失敗／練習）・版・修飾。
    遊んだ版の譜面が無い行は灰色で、押しても開かず「この版の譜面が無いので再生できません」。下の端にリプレイの場所（自動）'''
    ed = open_fixture_ready(t, "rich")
    rp_mock(ed, open={"waitFor": "never", "then": {"ok": False}})   # 自動で開くのは止めておく（一覧を見る）
    rp_watch(ed)
    to_replay(ed)
    wait_list(ed, len(ITEMS))
    click_id(ed, "#rpBack")   # 自動で開いた（開いている途中の）窓から一覧へ
    wait_until(ed, "window._dbgApp.replay().view==='list'", label="一覧へ")
    req = rp_calls(ed, "list")
    t.eq([c["body"] for c in req], [{"song": SONG}], "一覧は曲名・マッパーで頼む")
    t.eq(req[0]["headers"].get("X-NLM-Request"), "1", "POST に X-NLM-Request")
    rows = ed.js("""[...document.querySelectorAll('#rpList .rpRow')].map(r=>({id:r.dataset.id,off:r.classList.contains('off'),title:r.title,
      l1:r.querySelector('.rpL1').textContent,l2:r.querySelector('.rpL2').textContent,
      tags:[...r.querySelectorAll('.rpTag')].map(e=>e.textContent),mods:[...r.querySelectorAll('.rpMod')].map(e=>e.textContent+'='+e.title),
      ver:r.querySelector('.rpVer').textContent}))""")
    t.eq([r["id"] for r in rows], ["r1", "r2", "r3", "r4", "r5"], "サーバーの順（新しい順）")
    t.eq([r["off"] for r in rows], [False, False, True, False, False], "譜面の控えの無い行だけ灰色")
    t.eq(rows[2]["title"], "この版の譜面が無いので再生できません", "灰色の行のツールチップ")
    t.ok("Expert" in rows[0]["l1"] and "93.21%" in rows[0]["l1"], f"1行目の難易度・精度: {rows[0]['l1']}")
    t.ok("ミス 2" in rows[0]["l2"] and "バッド 1" in rows[0]["l2"], f"ミス・バッド: {rows[0]['l2']}")
    t.eq(rows[0]["mods"], ["FS=速い曲"], "修飾の札とツールチップ")
    t.eq(rows[0]["ver"], "最新の書き出し", "最新の書き出し")
    t.eq(rows[1]["tags"], ["やめた"], "途中でやめた札")
    t.ok(rows[1]["ver"].startswith("以前の書き出し（"), f"以前の書き出し＋日付: {rows[1]['ver']}")
    t.eq(rows[2]["ver"], "譜面なし", "控えの無い版")
    t.ok("Expert+" in rows[2]["l1"] and "ボム 1" in rows[2]["l2"] and "壁 2" in rows[2]["l2"], f"Expert+・ボム・壁: {rows[2]}")
    t.eq(rows[3]["tags"], ["失敗", "練習"], "失敗・練習の札")
    t.ok("OneSaber" in rows[3]["l1"], "Standard 以外は遊び方の名前も")
    t.ok("—" in rows[4]["l1"] and "ミスなし" in rows[4]["l2"], f"精度なし・ミスなし: {rows[4]}")
    st = rp(ed)
    t.ok(STATUS["dirs"][0]["path"] in st["dirs"] and "（自動）" in st["dirs"] and "（5 件）" in st["dirs"], f"リプレイの場所: {st['dirs']}")
    t.eq((st["pickShown"], st["autoShown"]), (False, False), "ブラウザ版は［変更…］なし・自動の時は［自動に戻す］なし")
    t.eq(st["count"], "この曲のリプレイ 5 件", "件数")
    # 灰色の行は押しても開かない
    click_row(ed, "r3")
    ed.wait(0.3)
    t.eq([c["body"]["id"] for c in rp_calls(ed, "open")], ["r1"], "灰色の行は開かない（自動で開いた r1 だけ）")
    t.ok("この版の譜面が無いので再生できません" in rp(ed)["note"], f"知らせ: {rp(ed)['note']}")
    t.no_errors()


def test_replay_empty_and_no_dir_and_no_song(t):
    '''一覧の文: 曲名が無い（一覧を頼まない）・この曲のリプレイが無い・リプレイのフォルダが見つからない・この版のサーバーに API が無い'''
    ed = open_fixture_ready(t, "basic")   # 曲名が空
    rp_mock(ed)
    to_replay(ed)
    wait_until(ed, "window._dbgApp.replay().empty.includes('曲名がありません')", label="曲名が無い")
    t.eq(rp_calls(ed, "list"), [], "曲名が無い時は一覧を頼まない")
    load_named(ed)   # 曲名を入れた（開き直した）＝REPLAY を出している間に変わると読み直す
    wait_until(ed, "window._dbg&&window.__rp.calls.some(c=>c.act==='list')", label="曲名が入ると一覧を頼む")
    t.eq(rp_calls(ed, "list")[0]["body"], {"song": {"name": "Basic Test Song", "mapper": "NLM Tester"}}, "新しい曲名で頼む")
    wait_state(ed, "linked")   # 一番新しい物を自動で開いた
    click_id(ed, "#rpBack")
    rp_mock(ed, items=[])
    click_id(ed, "#rpReloadList")
    wait_until(ed, "window._dbgApp.replay().empty.includes('この曲のリプレイはまだありません')", label="空の一覧")
    rp_mock(ed, items=[], status={"source": "none", "dirs": []})
    click_id(ed, "#rpReloadList")
    wait_until(ed, "window._dbgApp.replay().empty.includes('リプレイのフォルダが見つかりません')", label="フォルダが無い")
    t.ok("見つかりません" in rp(ed)["dirs"], f"場所: {rp(ed)['dirs']}")
    gone = {"source": "chosen", "dirs": [{"path": "D:/Gone/Replays", "count": 0, "missing": True}]}   # 選んだ場所のフォルダが消えた
    rp_mock(ed, items=[], status=gone)
    click_id(ed, "#rpReloadList")
    wait_until(ed, "window._dbgApp.replay().dirs.includes('D:/Gone/Replays（フォルダがありません）')", label="無いフォルダ")
    t.ok("リプレイのフォルダが見つかりません" in rp(ed)["empty"], f"無いフォルダだけ＝見つからない: {rp(ed)['empty']}")
    rp_mock(ed, list={"http": 404, "body": {"ok": False, "error": "unknown endpoint"}})
    click_id(ed, "#rpReloadList")
    wait_until(ed, "window._dbgApp.replay().empty.includes('この版ではリプレイを見られません')", label="API が無い")
    t.no_errors()


def test_replay_folder_exe(t):
    '''exe 版: ［変更…］でリプレイのフォルダを選ぶ（pywebview.api.replay_pick_folder・取り消しは何もしない）→「選んだ場所」・［自動に戻す］で /__replay/resetFolder'''
    ed = open_fixture_ready(t, "rich")
    install_fake_pywebview(ed)
    chosen = {"source": "chosen", "dirs": [{"path": "D:\\Games\\Replays", "count": 2}]}
    ed.js("window.__pick=[null];window.pywebview.api.replay_pick_folder=async()=>{ window.__picked=(window.__picked||0)+1; return window.__pick.shift(); };true")
    rp_mock(ed, open={"waitFor": "never", "then": {"ok": False}})
    to_replay(ed)
    wait_list(ed)
    click_id(ed, "#rpBack")
    t.eq(rp(ed)["pickShown"], True, "exe 版は［変更…］")
    click_id(ed, "#rpPick")
    wait_until(ed, "window.__picked===1", label="ダイアログ（取り消し）")
    ed.wait(0.2)
    t.eq(len(rp_calls(ed, "list")), 1, "取り消しは何もしない")
    ed.js("window.__pick=[{ok:false,error:'bad-path'}];true")   # 選んだ場所が使えない（app.py は {ok:false,error} を返す）
    click_id(ed, "#rpPick")
    wait_until(ed, "window._dbgApp.replay().note.includes('この場所は使えません')", label="使えない場所の知らせ")
    t.eq(len(rp_calls(ed, "list")), 1, "使えない場所では一覧を読み直さない")
    ed.js(f"window.__pick=[{json.dumps(chosen)}];true")
    rp_mock(ed, status=chosen, open={"waitFor": "never", "then": {"ok": False}})
    click_id(ed, "#rpPick")
    wait_until(ed, "window._dbgApp.replay().autoShown&&window._dbgApp.replay().dirs.includes('（選んだ場所）')", label="選んだ場所")
    t.ok("D:\\Games\\Replays" in rp(ed)["dirs"], f"選んだ場所: {rp(ed)['dirs']}")
    wait_until(ed, "window.__rp.calls.some(c=>c.act==='list')", label="一覧を読み直す")
    rp_mock(ed, open={"waitFor": "never", "then": {"ok": False}})
    click_id(ed, "#rpAuto")
    wait_until(ed, "window.__rp.calls.some(c=>c.act==='resetFolder')", label="自動に戻す")
    wait_until(ed, "!window._dbgApp.replay().autoShown&&window._dbgApp.replay().dirs.includes('（自動）')", label="自動")
    t.no_errors()


# ---------------------------------------------------------------- 開く・難易度
def test_replay_auto_open_and_diff(t):
    '''REPLAY を出すと一番新しい再生できるリプレイを開き、NLM の難易度をリプレイの難易度へ（Standard の時だけ）。開く位置は NLM の今の位置。
    別のリプレイを開くと難易度も替わる・Standard 以外／プロジェクトに無い難易度は今のまま知らせる。前に開いた物は次に REPLAY を出した時も開く'''
    ed = open_fixture_ready(t, "rich")
    _key_nle(ed, "3")   # Hard にしておく（r1 は Expert）
    wait_until(ed, "/^hard/i.test(window._dbgApp.state().diff)", label="Hard")
    rp_mock(ed)
    rp_watch(ed)
    to_replay(ed)
    wait_list(ed)
    wait_state(ed, "linked")
    st = rp(ed)
    t.eq(st["cur"], "r1", "一番新しい再生できる物（r1）")
    wait_until(ed, "/^expert/i.test(window._dbgApp.state().diff)", label="Expert へ")
    op = rp_calls(ed, "open")
    t.eq(op[0]["body"], {"id": "r1", "t": 0}, "開く要求（id と NLM の位置）")
    t.eq(st["origin"], fake_viewer(), "窓のオリジン")
    t.ok(st["src"].startswith(fake_viewer() + "/index.html?") and "time=0" in st["src"], f"窓の URL: {st['src']}")
    t.eq(ed.js("(f=>[f.getAttribute('sandbox'),f.allow,f.referrerPolicy])(document.getElementById('rpFrame'))"),
         ["allow-scripts allow-same-origin allow-popups allow-popups-to-escape-sandbox allow-pointer-lock allow-modals allow-downloads", "autoplay; fullscreen; screen-wake-lock", "no-referrer"],
         "iframe の sandbox・allow")
    t.ok("Expert" in st["sum"] and "93.21%" in st["sum"], f"見出しの要点: {st['sum']}")
    t.eq(ed.js("document.querySelector('#rpZoom').textContent"), "🔍 ホイールでズーム", "ズームの案内")
    t.eq(ed.js("getComputedStyle(document.getElementById('rpZoom')).pointerEvents"), "none", "案内は操作を通す")
    rp_user(ed, zoom=1.8)
    wait_until(ed, "window._dbgApp.replay().zoomText==='🔍 ×1.8（ホイールで戻す）'", label="ズームの倍率")
    rp_user(ed, zoom=1)
    wait_until(ed, "window._dbgApp.replay().zoomText==='🔍 ホイールでズーム'", label="1 倍へ戻る")
    # 別のリプレイ（Hard・やめた・以前の書き出し）
    click_id(ed, "#rpBack")
    wait_until(ed, "window._dbgApp.replay().view==='list'", label="一覧へ")
    click_row(ed, "r2")
    wait_state(ed, "linked")
    wait_until(ed, "/^hard/i.test(window._dbgApp.state().diff)", label="Hard へ")
    note = rp(ed)["note"]
    t.ok("遊んだ後に編集した版です（今の譜面とずれることがあります）" in note, f"以前の書き出しの知らせ: {note}")
    t.ok("途中でやめたプレイ: 0:06.0 まで" in note, f"やめたプレイの知らせ: {note}")
    # Standard 以外は今のまま知らせる
    click_id(ed, "#rpBack")
    click_row(ed, "r4")
    wait_state(ed, "linked")
    t.ok("このリプレイは OneSaber のプレイです。NLM の難易度は今のまま（Hard）です" in rp(ed)["note"], f"r4 の知らせ: {rp(ed)['note']}")
    t.eq(_diff(ed).lower(), "hard", "r4: 難易度は今のまま（Hard）")
    # 素材に中身の無い難易度（Normal）も、選べる難易度なのでそこへ（NLM は5つの難易度をいつも選べる）
    click_id(ed, "#rpBack")
    click_row(ed, "r5")
    wait_state(ed, "linked")
    wait_until(ed, "/^normal/i.test(window._dbgApp.state().diff)", label="Normal へ")
    # 前に開いた物（r5）は、次に REPLAY を出した時も
    hover_pv(ed); ed.key("Tab")
    wait_until(ed, "window._dbgApp.replay().pvMode==='media'", label="MEDIA へ")
    to_replay(ed)
    wait_state(ed, "linked")
    t.eq(rp(ed)["cur"], "r5", "前に開いた物をもう一度")
    t.eq(len(rp_calls(ed, "open")), 4, "同じ物は窓を残したまま（開き直さない）")
    t.no_errors()


# ---------------------------------------------------------------- 同期
def test_replay_keys_from_viewer(t):
    '''窓の中を押した後のキー: bridge.js が渡す Tab＝左上の窓の切り替え（REPLAY → MEDIA）・Ctrl の組み合わせ＝NLM の本物の keydown と同じ道へ。
    ほかのキーは受けない'''
    ed = open_fixture_ready(t, "rich")
    open_replay(ed)
    ed.js("window.__kd=[];addEventListener('keydown',e=>window.__kd.push(e.key+(e.ctrlKey?'+c':'')+(e.shiftKey?'+s':'')));true")
    rp_user_raw(ed, {"nlm": "blr", "test": "key", "key": "z", "code": "KeyZ", "ctrl": True})
    rp_user_raw(ed, {"nlm": "blr", "test": "key", "key": "Z", "code": "KeyZ", "ctrl": True, "shift": True})
    wait_until(ed, "window.__kd.length>=2", label="Ctrl の組み合わせが NLM の keydown へ")
    t.eq(ed.js("window.__kd"), ["z+c", "Z+c+s"], "Ctrl+Z・Ctrl+Shift+Z が NLM の keydown へ届く")
    t.eq(rp(ed)["pvMode"], "replay", "Ctrl の組み合わせでは窓を切り替えない")
    rp_user_raw(ed, {"nlm": "blr", "test": "key", "key": "Tab", "code": "Tab"})
    wait_until(ed, "window._dbgApp.replay().pvMode==='media'", label="窓の中の Tab で REPLAY → MEDIA")
    t.eq(ed.js("window.__kd.length"), 2, "Tab は keydown を作らず直接切り替える")


def test_replay_sync_nlm_to_replay(t):
    '''同期（NLM → リプレイ）: つないだ時はリプレイを NLM の位置へ。←→・ルーラーで位置を変えるとリプレイへ seek（0.12 秒に1回まで・最後の位置は必ず）。
    Space＝リプレイの再生・停止（NLM の曲の音は鳴らさない）・再生中はリプレイの時刻に NLM が付いてくる'''
    ed = open_fixture_ready(t, "rich")
    open_replay(ed)
    t.eq([round(x["t"], 3) for x in rp_log(ed, "seek")], [0.0], "つないだ時に NLM の位置（0 秒）へ")
    rp_clear_log(ed)
    _key_nle(ed, "ArrowRight")   # スナップ 1/4 拍？＝素材の既定のスナップ幅だけ進む
    wait_until(ed, "window.__rpf.log.some(x=>x.cmd==='seek')", label="→ でリプレイへ seek")
    b = rp(ed)["nlm"]
    t.ok(b["beat"] > 0, f"NLM の位置が進んだ: {b}")
    t.eq(round(rp_log(ed, "seek")[-1]["t"], 4), round(b["sec"], 4), "送る秒＝beatToTimeTM(拍)")
    wait_until(ed, f"Math.abs(window._dbgApp.replay().t-{b['sec']})<0.01", label="リプレイの時刻が付いてくる")
    # ルーラー（拍番号の帯）のクリックで 8 拍＝4 秒へ
    rp_clear_log(ed)
    g = ed.js("window._dbgApp.nleScreen(8)")
    ed.click(g["x"], g["ruler"] + 6)
    wait_until(ed, "window.__rpf.log.some(x=>x.cmd==='seek'&&Math.abs(x.t-4)<0.01)", label="ルーラーで 4 秒へ seek")
    wait_until(ed, "Math.abs(window._dbgApp.replay().t-4)<0.01&&!window._dbgApp.replay().hold", label="リプレイが 4 秒に着く")
    t.ok(abs(rp(ed)["nlm"]["beat"] - 8) < 1e-6, f"NLM は拍8のまま（丸めで動かない）: {rp(ed)['nlm']}")
    # 続けて何度も動かす（ホイール 6 回＝6 コマ）→ 送るのは 0.12 秒に1回まで・最後の位置は必ず
    rp_clear_log(ed)
    g = ed.js("window._dbgApp.nleScreen(10)")
    for _ in range(6):
        ed.wheel(g["x"], g["lanes"] + 30, -100)   # NLE の上のホイール＝再生位置をスナップ幅ずつ（1 コマに1回）
    # 最後のホイールが NLM に届く前（次のコマの前）に「送り終わった」と見えることがあるので、最後に送った位置が今の位置に
    # なるまで待つ（送らなければ時間切れ＝「最後の位置は必ず送る」が守られていない）
    wait_until(ed, "(()=>{const r=window._dbgApp.replay(), s=window.__rpf.log.filter(x=>x.cmd==='seek');"
                   "return !r.hold&&r.pend===null&&s.length&&Math.abs(s[s.length-1].t-r.nlm.sec)<1e-6;})()", label="送り終わる")
    end_sec = rp(ed)["nlm"]["sec"]
    seeks = [x for x in ed.js("window.__rpf.log") if x["cmd"] == "seek"]
    t.ok(seeks and abs(seeks[-1]["t"] - end_sec) < 1e-6, f"最後の位置は必ず送る: {seeks} / {end_sec}")
    gaps = [b2["at"] - a["at"] for a, b2 in zip(seeks, seeks[1:])]
    t.ok(all(g >= 100 for g in gaps), f"送る間隔は 0.12 秒ほど以上: {gaps}")
    # Space＝リプレイの再生
    rp_clear_log(ed)
    _key_nle(ed, " ")
    wait_until(ed, "window.__rpf.log.some(x=>x.cmd==='play')", label="Space でリプレイを再生")
    wait_until(ed, "window._dbgApp.replay().playing&&window._dbgApp.replay().nlm.playing", label="再生中")
    t.eq(ed.js("document.getElementById('play').textContent"), "⏸", "▶ の形も再生中")
    s0 = rp(ed)["nlm"]["sec"]
    ed.wait(0.8)
    st = rp(ed)
    t.ok(0.5 < st["nlm"]["sec"] - s0 < 1.3, f"NLM がリプレイの時刻に付いて進む: {s0} → {st['nlm']['sec']}")
    t.ok(abs(st["nlm"]["sec"] - st["t"]) < 0.15, f"リプレイの時刻との差: NLM {st['nlm']['sec']} / リプレイ {st['t']}")
    t.eq(st["nlm"]["srcs"], 0, "NLM の曲の音は鳴らさない")
    _key_nle(ed, " ")
    wait_until(ed, "window.__rpf.log.some(x=>x.cmd==='pause')", label="Space でリプレイを止める")
    wait_until(ed, "!window._dbgApp.replay().playing&&!window._dbgApp.replay().nlm.playing", label="止まる")
    fs = rp_frame_state(ed)
    wait_nlm_sec(ed, fs["t"], 0.02, "止めた時刻に NLM も止まる")
    t.no_errors()


def test_replay_sync_replay_to_nlm(t):
    '''同期（リプレイ → NLM）: リプレイの時刻の棒・再生・停止・速さに NLM の再生位置・▶ の形が付いてくる。ほかのオリジン・ほかの窓の伝言は使わない'''
    ed = open_fixture_ready(t, "rich")
    open_replay(ed)
    rp_user(ed, t=10)                       # 止めたまま時刻の棒を 10 秒へ
    wait_nlm_sec(ed, 10, 0.01, "NLM も 10 秒へ（素材は BPM の変化あり＝拍は beatToTimeTM の逆）")
    rp_user(ed, playing=True)               # リプレイの中で再生
    wait_until(ed, "window._dbgApp.replay().nlm.playing", label="NLM も再生中")
    t.eq(ed.js("document.getElementById('play').textContent"), "⏸", "▶ の形も再生中")
    ed.wait(0.6)
    st = rp(ed)
    t.ok(st["nlm"]["sec"] > 10.3, f"進む: {st['nlm']['sec']}")
    t.eq(st["nlm"]["srcs"], 0, "NLM の曲の音は鳴らさない")
    rp_user(ed, playing=False)
    wait_until(ed, "!window._dbgApp.replay().nlm.playing", label="NLM も止まる")
    t.eq(ed.js("document.getElementById('play').textContent"), "▶", "▶ の形")
    rp_user(ed, t=3, speed=0.5, playing=True)   # スロー（BL のミスでスロー）
    wait_until(ed, "window._dbgApp.replay().nlm.playing", label="スローで再生")
    s0 = rp(ed)["nlm"]["sec"]; ed.wait(1.0); s1 = rp(ed)["nlm"]["sec"]
    t.ok(0.3 < s1 - s0 < 0.75, f"半分の速さで付いてくる: {s1 - s0:.3f} 秒/1 秒")
    rp_user(ed, playing=False, speed=1)
    wait_until(ed, "!window._dbgApp.replay().nlm.playing", label="止める")
    # ほかの窓（この画面自身）・ほかのオリジンからの伝言は使わない
    here = rp(ed)["nlm"]["sec"]
    ed.js("window.postMessage({nlm:'blr',ev:'time',t:12,playing:false,at:performance.timeOrigin+performance.now()},'*');true")
    ed.js("""(()=>{ const f=document.createElement('iframe'); f.id='rpEvil'; document.body.appendChild(f);
      window.dispatchEvent(new MessageEvent('message',{data:{nlm:'blr',ev:'time',t:13,playing:false},origin:'http://evil.example',source:document.getElementById('rpFrame').contentWindow}));
      window.dispatchEvent(new MessageEvent('message',{data:{nlm:'blr',ev:'time',t:14,playing:false},origin:%s,source:f.contentWindow}));
      f.remove(); return true; })()""" % json.dumps(fake_viewer()))
    ed.wait(0.4)
    t.ok(abs(rp(ed)["nlm"]["sec"] - here) < 1e-6, f"使わない（{here} のまま）: {rp(ed)['nlm']['sec']}")
    t.no_errors()


def test_replay_end_sec_stop(t):
    '''途中でやめたリプレイ（記録が曲の終わりより前で終わる）は endSec で止める（その先から再生してもすぐ止まる・同期を外していても）'''
    ed = open_fixture_ready(t, "rich")
    rp_mock(ed)
    rp_watch(ed)
    to_replay(ed)
    wait_list(ed)
    wait_state(ed, "linked")
    click_id(ed, "#rpBack")
    click_row(ed, "r2")                      # やめた・endSec 6.0（偽の窓の長さは 16 秒）
    wait_state(ed, "linked")
    t.eq(rp(ed)["stopEnd"], 6.0, "止める秒")
    rp_user(ed, t=5.5)
    wait_nlm_sec(ed, 5.5, 0.01)
    rp_clear_log(ed)
    _key_nle(ed, " ")
    wait_until(ed, "window.__rpf.log.some(x=>x.cmd==='pause')", timeout=5, label="6 秒で止める")
    wait_until(ed, "!window._dbgApp.replay().nlm.playing&&!window._dbgApp.replay().playing", label="止まる")
    fs = rp_frame_state(ed)
    t.ok(5.95 <= fs["t"] < 6.25, f"リプレイは 6 秒あたりで止まる: {fs['t']}")
    wait_nlm_sec(ed, fs["t"], 0.02, "NLM も同じ所")
    rp_clear_log(ed)
    _key_nle(ed, " ")                        # その先から再生してもすぐ止まる
    wait_until(ed, "window.__rpf.log.filter(x=>x.cmd==='pause').length>=1", timeout=5, label="すぐ止める")
    # 同期を外していても止める
    click_id(ed, "#rpSync")
    wait_state(ed, "ready")
    rp_user(ed, t=5.8, playing=True)
    rp_clear_log(ed)
    wait_until(ed, "window.__rpf.log.some(x=>x.cmd==='pause')", timeout=5, label="同期を外していても 6 秒で止める")
    t.no_errors()


def test_replay_unlink(t):
    '''外す: 同期を切ると別々に動く（NLM の ▶ は NLM の曲の音）・入れ直すとリプレイを NLM の位置へ。一覧へ戻る・別の画面へ・新規の時はリプレイを止めて外す'''
    ed = open_fixture_ready(t, "rich")
    open_replay(ed)
    click_id(ed, "#rpSync")
    wait_state(ed, "ready")
    t.ok(ed.js("!document.getElementById('rpSync').classList.contains('on')"), "同期の字は緑でない")
    t.ok("同期を切っています" in rp(ed)["note"], f"知らせ: {rp(ed)['note']}")
    rp_clear_log(ed)
    _key_nle(ed, " ")
    wait_until(ed, "window._dbgApp.replay().nlm.playing&&window._dbgApp.replay().nlm.srcs>0", label="NLM の曲の音で再生")
    ed.wait(0.3)
    t.eq(rp_log(ed, "play"), [], "リプレイへ再生を送らない")
    _key_nle(ed, " ")
    wait_until(ed, "!window._dbgApp.replay().nlm.playing", label="止める")
    _key_nle(ed, "ArrowRight")
    ed.wait(0.3)
    t.eq(rp_log(ed, "seek"), [], "位置も送らない")
    sec = rp(ed)["nlm"]["sec"]
    click_id(ed, "#rpSync")
    wait_state(ed, "linked")
    t.ok(ed.js("document.getElementById('rpSync').classList.contains('on')"), "同期の字は緑")
    wait_until(ed, f"window.__rpf.log.some(x=>x.cmd==='seek'&&Math.abs(x.t-{sec})<1e-6)", label="入れ直すと NLM の位置へ")
    # 一覧へ戻る＝止めて外す（窓は残す）
    rp_user(ed, playing=True)
    wait_until(ed, "window._dbgApp.replay().nlm.playing", label="再生中")
    rp_clear_log(ed)
    click_id(ed, "#rpBack")
    wait_until(ed, "window.__rpf.log.some(x=>x.cmd==='pause')&&!window._dbgApp.replay().nlm.linked", label="一覧へ戻ると止めて外す")
    t.eq(rp(ed)["nlm"]["playing"], False, "NLM も止まっている")
    click_row(ed, "r1")
    wait_state(ed, "linked")
    t.eq(len(rp_calls(ed, "open")), 1, "同じ物は開き直さない")
    # 新規＝窓を閉じる
    file_menu(ed, "new")
    wait_until(ed, "!document.getElementById('rpFrame')&&!window._dbgApp.replay().nlm.linked", label="新規で窓を閉じる")
    wait_until(ed, "window._dbgApp.replay().empty.includes('曲名がありません')", label="新規の曲は曲名なし")
    t.no_errors()


# ---------------------------------------------------------------- 書き出しの控え
def _start_native(t):
    ed = open_fixture_ready(t, "rich")
    install_fake_pywebview(ed)
    stub_convert(ed)
    to_info(ed)
    native_queue(ed, "folder", OUT_BASE)
    click_sel(ed, "#infoWorld .iGrp[data-out=o1] .oPick", "出力フォルダを選択")
    wait_until(ed, f"window._dbgApp.infoGraph().outs.o1.outDirPath==={json.dumps(OUT_BASE)}", label="出力フォルダの接続")
    return ed


def _export(ed, folder="rpexp"):
    ed.js("document.getElementById('errToast').style.display='none'")
    export_click(ed, folder)
    wait_until(ed, "/書き出しました|書き出し失敗/.test(document.getElementById('errToast').textContent)", label="書き出しの完了")
    return ed.js("document.getElementById('errToast').textContent")


def test_replay_keep_after_export(t):
    '''書き出しの控え: 書き出した後に、書き出し先から読み直した Info.dat・難易度の .dat（Info の順）を /__replay/keep へ、song.egg を SHA-1 と一緒に
    /__replay/keepEgg へ（裏で・書き出しの結果は変えない）。同じ hash へ同じ song.egg は送り直さない。控えに失敗しても書き出しは成功のまま'''
    ed = _start_native(t)
    rp_mock(ed)
    msg = _export(ed)
    t.ok("書き出しました" in msg, f"書き出しは成功: {msg}")
    wait_until(ed, "window.__rp.calls.some(c=>c.act==='keepEgg')", label="控えの要求")
    keep = rp_calls(ed, "keep")
    t.eq(len(keep), 1, "keep は1回")
    parts = call_parts(keep[0])
    dest = OUT_BASE + "\\rpexp"
    t.eq([n for n, _ in parts], ["Info.dat", "HardStandard.dat", "ExpertStandard.dat"], "送るファイル（Info.dat が先・Info の順）")
    info_text = ed.js(f"""(()=>{{ const f=window.__nat.files[{json.dumps((dest + chr(92) + 'Info.dat').lower())}]; return atob(f.b64); }})()""")
    t.eq(parts[0][1], info_text.encode("latin-1"), "Info.dat は書いた物そのまま（書き出し先から読み直す）")
    w = native_writes(ed)
    for n, b in parts:
        t.eq(len(b), w[dest + "\\" + n]["size"], f"{n} の大きさ＝書いた物")
    t.eq(keep[0]["headers"].get("X-NLM-Request"), "1", "POST に X-NLM-Request")
    egg = rp_calls(ed, "keepEgg")
    t.eq(len(egg), 1, "keepEgg は1回")
    t.eq(egg[0]["len"], 64, "song.egg（偽の変換の 64 バイト）")
    t.eq(egg[0]["query"], {"hash": "ab" * 20, "sha1": sha1_of(egg[0])}, "hash は keep の応答・sha1 は中身から")
    # 同じ書き出し（サーバーの控えに egg がある）＝同じ song.egg は送り直さない
    rp_mock(ed, keep={"ok": True, "hash": "ab" * 20, "isNew": False, "needEgg": False})
    _export(ed)
    wait_until(ed, "window.__rp.calls.some(c=>c.act==='keep')", label="2回目の keep")
    ed.wait(0.4)
    t.eq(rp_calls(ed, "keepEgg"), [], "同じ hash へ同じ song.egg は送らない")
    # 控えに失敗しても書き出しの結果は変えない
    rp_mock(ed, keep={"ok": False, "error": "too-large"})
    msg = _export(ed, "rpexp2")
    t.ok("書き出しました" in msg, f"控えに失敗しても書き出しは成功: {msg}")
    wait_until(ed, "window.__rp.calls.some(c=>c.act==='keep')", label="3回目の keep")
    t.no_errors()


def test_replay_keep_on_show(t):
    '''REPLAY を出した時: 書き出し先がつながっていて、この起動でまだ控えていなければ1回だけ keep（needEgg の時だけ keepEgg）。控えが新しければ一覧を読み直す'''
    ed = _start_native(t)
    rp_mock(ed, keep={"ok": False, "error": "failed"})   # 書き出しの後の控えは失敗した（＝まだ控えていない）
    _export(ed)
    wait_until(ed, "window.__rp.calls.some(c=>c.act==='keep')", label="書き出しの後の keep")
    ed.wait(0.3)
    rp_mock(ed, open={"waitFor": "never", "then": {"ok": False}})
    hover_pv(ed)   # INFO を出したまま左上の窓で Tab
    to_replay(ed)
    wait_until(ed, "window.__rp.calls.some(c=>c.act==='keepEgg')", label="出した時の控え")
    t.eq(len(rp_calls(ed, "keep")), 1, "keep は1回")
    t.eq([n for n, _ in call_parts(rp_calls(ed, "keep")[0])], ["Info.dat", "HardStandard.dat", "ExpertStandard.dat"], "書き出し先の譜面")
    wait_until(ed, "window.__rp.calls.filter(c=>c.act==='list').length>=2", label="控えが新しい＝一覧を読み直す")
    # もう一度出しても控えない（この起動で1回）
    for _ in range(3):
        hover_pv(ed); ed.key("Tab"); ed.wait(0.2)
    wait_until(ed, "window._dbgApp.replay().pvMode==='replay'", label="REPLAY へ")
    ed.wait(0.4)
    t.eq(len(rp_calls(ed, "keep")), 1, "2回目は控えない")
    t.no_errors()


def test_replay_keep_on_show_need_egg_only(t):
    '''REPLAY を出した時の控えは、サーバーの控えに song.egg が無い時（needEgg）だけ keepEgg を送る'''
    ed = _start_native(t)
    rp_mock(ed, keep={"ok": False, "error": "failed"})
    _export(ed)
    wait_until(ed, "window.__rp.calls.some(c=>c.act==='keep')", label="書き出しの後の keep")
    rp_mock(ed, keep={"ok": True, "hash": "cd" * 20, "isNew": False, "needEgg": False}, open={"waitFor": "never", "then": {"ok": False}})
    hover_pv(ed)
    to_replay(ed)
    wait_until(ed, "window.__rp.calls.some(c=>c.act==='keep')", label="出した時の keep")
    ed.wait(0.5)
    t.eq(rp_calls(ed, "keepEgg"), [], "needEgg でなければ送らない")
    t.eq(len(rp_calls(ed, "list")), 1, "控えが新しくなければ一覧は読み直さない")
    t.no_errors()

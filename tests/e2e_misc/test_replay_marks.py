"""REPLAY の「点を重ねる」（2026-11-22・計算は js/replay/replay-marks.js、描画は editor-app.js の rpMarks*、切り替えと凡例は replay-pane.js）。

リプレイを開いた時に1回 /__replay/events を読み、再生の画面の間だけ NLE の拍番号の帯にミス・バッド・ボム・壁の印、下の 3D の合ったノーツに点の段の色の輪を出す。
応答は偽物（tests/_lib/replay_helpers.py の rp_mock・出来事は素材 rich の Expert に合わせた RICH_EVENTS）。時刻はリプレイの秒＝beatToTimeTM(拍)
（素材 rich は BPM 120・16 拍から 150）。
"""
import json

from misc_helpers import file_menu, open_fixture_ready, wait_until
from replay_helpers import (RICH_EVENTS, click_id, click_row, hover_pv, open_replay, rich_sec, rp, rp_calls, rp_clear_log, rp_log, rp_marks,
                            rp_mock, rp_watch, to_replay, wait_list, wait_state)
from review_helpers import rv_import

# 素材 rich の Expert の物に合わせた出来事の、期待する NLE の印（種類・拍・薄い＝合う物が無い）と 3D の輪（物の種類・拍・列・段・段）
MARKS = [("miss", 3, False), ("bad", 3, False), ("miss", 6, False), ("miss", 7, True), ("bomb", 8, False), ("wall", 9, False),
         ("miss", 10.25, False), ("bomb", 11, True), ("bomb", 21, False), ("wall", 23, False)]
RINGS = {("note", 1, 1, 0): "t115", ("note", 1, 2, 0): "t110", ("note", 2, 1, 0): "t100", ("note", 2, 2, 0): "low",
         ("note", 3, 0, 1): "bad", ("note", 3, 3, 1): "miss", ("note", 4, 1, 2): "t115", ("note", 4, 2, 2): "t106",
         ("note", 5, 0, 0): "t113", ("note", 6, 1, 1): "miss", ("bomb", 8, 0, 0): "bomb", ("chain", 10, 1, 2): "miss",
         ("chain", 12, 2, 2): "t106", ("note", 18, 2, 0): "t115", ("bomb", 21, 1, 2): "bomb"}
# 色: 切った物＝BL のリプレイアプリの点数の色（点数÷満点×115）・バッド＝橙・ミス＝赤・ボム＝マゼンタ（点の色に無い色）
COL = {"t115": "#ffffff", "t113": "#8500ff", "t110": "#00a3ff", "t106": "#00ff00", "t100": "#ffff00", "low": "#ff0038",
       "bad": "#ff8000", "miss": "#ff0000", "bomb": "#ff00d0"}
# ミスの大きな ✕（ノーツ・チェーンの頭の、段が miss の物）
CROSSES = sorted(k for k, v in RINGS.items() if v == "miss")


def _hover_nle(ed):
    g = ed.js("window._dbgApp.nleScreen(0)")
    ed.move(g["left"] + g["w"] * 0.6, g["lanes"] + 40)
    ed.wait(0.15)


def _key_nle(ed, k):
    _hover_nle(ed)
    ed.key(k)


def _wait_marks(ed, n=None):
    cond = "(m=>m&&m.on&&m.marks.length>0" + (f"&&m.marks.length==={n}" if n is not None else "") + ")(window._dbgApp.rpMarks())"
    return wait_until(ed, cond, label="点の印が出る")


def _mark(ed, kind, beat):
    return next(q for q in rp_marks(ed)["marks"] if q["kind"] == kind and abs(q["beat"] - beat) < 1e-6)


def _open(t, events=RICH_EVENTS, **mock):
    ed = open_fixture_ready(t, "rich")
    open_replay(ed, events=events, **mock)
    return ed


# ---------------------------------------------------------------- NLE の印と 3D の輪
def test_replay_marks_nle_and_3d(t):
    '''リプレイを開くと出来事を1回読み、NLE の拍番号の帯にミス・バッド・ボム・壁の印（合う物の無い出来事は薄く・拍の位置）、
    3D の合ったノーツ・ボム・チェーンの頭に点の段の色の輪（ミス・バッド・ボムは太い輪）。凡例に段ごとの数と合わないノーツ・ボムの数'''
    ed = _open(t)
    wait_until(ed, "/^expert/i.test(window._dbgApp.state().diff)", label="Expert へ")
    _wait_marks(ed)
    t.eq([c["body"] for c in rp_calls(ed, "events")], [{"id": "r1"}], "開いた時に出来事を1回頼む（id）")
    m = rp_marks(ed)
    t.eq((m["has"], m["on"], m["diff"], m["events"]), (True, True, "Expert", len(RICH_EVENTS["notes"]) + len(RICH_EVENTS["walls"])), "渡されて出している")
    t.eq([(q["kind"], q["beat"], q["dim"]) for q in m["marks"]], [(k, b, d) for k, b, d in MARKS], "NLE の印（種類・拍・合う物が無い＝薄い）")
    # 位置: 拍の位置（同じ拍に違う種類が2つ＝横に並ぶ）・拍番号の帯の中（数字の下）
    g = ed.js("window._dbgApp.nleScreen(0)")
    for q in m["marks"]:
        bx = ed.js(f"window._dbgApp.nleScreen({q['beat']}).x")
        cx, cy = q["x"] + q["w"] / 2, q["y"] + q["h"] / 2
        tol = 6 if q["beat"] == 3 else 1
        t.ok(abs(cx - bx) <= tol, f"{q['kind']} {q['beat']}: 横の位置 {cx:.1f}（拍の x {bx:.1f}）")
        t.ok(g["ruler"] + 11 <= cy <= g["tempo"], f"{q['kind']} {q['beat']}: 拍番号の帯の下の方 {cy:.1f}（帯 {g['ruler']}〜{g['tempo']}）")
    # 色（キャンバスの印の真ん中の画素・薄くない物だけ）: ミス＝赤・バッド＝橙・ボム＝マゼンタ・壁＝灰色（3D の輪・凡例と同じ）
    want = {"miss": (255, 0, 0), "bad": (255, 128, 0), "bomb": (255, 0, 208), "wall": (200, 204, 214)}
    px = ed.js("""(qs=>{ const c=document.getElementById('ndcv'), r=c.getBoundingClientRect(), sx=c.width/r.width, sy=c.height/r.height, g=c.getContext('2d');
      return qs.map(q=>Array.from(g.getImageData(Math.round((q.x+q.w/2-r.left)*sx),Math.round((q.y+q.h/2-r.top)*sy),1,1).data).slice(0,3)); })(%s)"""
               % json.dumps([q for q in m["marks"] if not q["dim"]]))
    for q, p in zip([q for q in m["marks"] if not q["dim"]], px):
        t.ok(all(abs(a - b) <= 24 for a, b in zip(p, want[q["kind"]])), f"NLE の印の色 {q['kind']} {q['beat']}: {p}（{want[q['kind']]}）")
    m3a, m3b = _mark(ed, "miss", 3), _mark(ed, "bad", 3)
    t.ok(m3a["x"] + m3a["w"] <= m3b["x"] + 1, "同じ拍のミスとバッドは横に並ぶ（重ならない）")
    # 3D の輪
    rings = {(r["kind"], r["beat"], r["x"], r["y"]): r for r in m["rings"]}
    for k, tier in RINGS.items():
        r = rings.get(k)
        t.ok(r is not None, f"輪: {k}")
        if r:
            bad = tier in ("bad", "miss", "bomb")
            t.eq((r["tier"], r["mat"], r["thick"], r["width"], r["outer"]), (tier, COL[tier], bad, 0.13 if bad else 0.03, 0.46 if bad else 0.4),
                 f"輪の段・色・太さ（切った物は細い 0.03・ミス・バッド・ボムは太い 0.13）: {k}")
            t.eq((r["rainbow"], r["bands"]), (tier == "t115", 6 if tier == "t115" else 0),
                 f"115 の輪だけ虹色（境目をはっきり切った6色の帯）: {k}")
    t.eq(len(m["rings"]), len(RINGS), "合った物だけに輪（合わない出来事・出来事の無いノーツには無い）")
    # 描く順番: 輪は半透明で奥行きを書かないので、3D のスペクトログラムの帯（半透明）より後に描く（前だと帯の重なる所だけ輪が暗くなった・2026-11-22 利用者の報告）
    t.ok(all(r["order"] > m["specOrder"] for r in m["rings"]), f"輪は帯より後に描く（輪 {sorted({r['order'] for r in m['rings']})}・帯 {m['specOrder']}）")
    # ミスの ✕: 段が miss の物だけ・赤・黒い縁＋赤をノーツの表と裏の前に（4 つの部品）・輪と同じ所
    t.eq(sorted((x["kind"], x["beat"], x["x"], x["y"]) for x in m["crosses"]), CROSSES, "ミスの物にだけ ✕")
    for x in m["crosses"]:
        t.eq((x["mat"], x["parts"], sorted(abs(z) for z in x["dz"])), ("#ff0000", 4, [0.072, 0.072, 0.082, 0.082]), f"✕ の色・部品: {x['beat']}")
    t.eq((m["unNotes"], m["unBombs"]), (1, 1), "合わないノーツ 1・ボム 1")
    st = rp(ed)
    t.eq([(c["k"], c["n"]) for c in st["mkChips"]],
         [("t115", 10), ("t113", 1), ("t110", 1), ("t106", 2), ("t100", 1), ("low", 1), ("bad", 1), ("miss", 4), ("bomb", 3), ("wall", 2)],
         "凡例の段ごとの数（全部の出来事）")
    t.eq([c["label"] for c in st["mkChips"]], ["115", "113+", "110+", "106+", "100+", "99以下", "バッド", "ミス", "ボム", "壁"], "凡例の文")
    want_col = {**COL, "wall": "#c8ccd6"}   # 壁の印は灰色（ボムのマゼンタ・どの点の色とも違う）
    t.eq(ed.js(r"[...document.querySelectorAll('#rpMk .rpMkC')].map(c=>{ const m=getComputedStyle(c.querySelector('.rpMkG')).color.match(/\d+/g); "
               r"return [c.dataset.k,'#'+m.slice(0,3).map(v=>(+v).toString(16).padStart(2,'0')).join('')]; })"),
         [[c["k"], "#000000" if c["k"] == "t115" else want_col[c["k"]]] for c in st["mkChips"]],
         "凡例の印の色（3D の輪・NLE の印と同じ。115 は字を透かして虹を見せる＝字の色は透明）")
    rb = ed.js("(g=>{ const s=getComputedStyle(g); return {img:s.backgroundImage, clip:s.backgroundClip||s.webkitBackgroundClip, a:s.color}; })"
               "(document.querySelector('#rpMk .rpMkC[data-k=\"t115\"] .rpMkG'))")
    t.ok("conic-gradient" in rb["img"] and rb["clip"] == "text" and rb["a"].replace(" ", "") == "rgba(0,0,0,0)",
         f"凡例の 115 は虹色（3D の輪と同じ）: {rb}")
    t.eq(st["mkUn"], "合わないノーツ 1 個・合わないボム 1 個", "合わない数")
    t.ok(ed.js("document.getElementById('rpMarks').classList.contains('on')"), "見出しの［点を重ねる］はオン")
    t.no_errors()


def test_replay_marks_click_and_tips(t):
    '''NLE の印: ツールチップに時刻・拍・種類（合わない物はそう書く）・押すとその位置へ（同期中はリプレイも同じ秒へ）。
    3D: 輪の付いたノーツの上にマウスを置くとツールチップに時刻と点（ミスは種類）'''
    ed = _open(t)
    _wait_marks(ed)
    # 3D のツールチップ（再生位置は拍 0 のまま＝カメラに近い拍 1〜3 の物）: 拍 2 の青（90 点）・拍 3 の青（ミス）・拍 1 の赤（115 点）
    for (kind, beat, x, y), want in [(("note", 2, 2, 0), "リプレイ 0:01.00: 90 点（満点 115）"),
                                     (("note", 3, 3, 1), "リプレイ 0:01.50: ミス（見逃し）"),
                                     (("note", 1, 1, 0), "リプレイ 0:00.50: 115 点（満点 115）")]:
        o = ed.js(f"window._dbgApp.objScreen().find(o=>o.kind==={json.dumps(kind)}&&o.beat==={beat}&&o.x==={x}&&o.y==={y}&&o.inView)")
        t.ok(o, f"3D の {kind} {beat} が見えている")
        if o:
            ed.move(o["sx"], o["sy"])
            tip3 = wait_until(ed, f"window._dbgApp.rpMarks().tip3==={json.dumps(want)}&&window._dbgApp.rpMarks().tip3", label=f"3D のツールチップ {kind} {beat}")
            t.eq(ed.js("document.getElementById('cv').title"), tip3, "3D のキャンバスの title")
    q = _mark(ed, "miss", 7)
    ed.move(q["x"] + q["w"] / 2, q["y"] + q["h"] / 2)
    tip = wait_until(ed, "document.getElementById('ndcv').title", label="印のツールチップ")
    t.ok("0:03.50（7 拍）ミス（見逃し）（今の譜面に合うノーツがありません）" in tip and "クリックでこの位置へ" in tip, f"合わないミスのツールチップ: {tip!r}")
    wait_until(ed, "document.getElementById('ndcv').style.cursor==='pointer'", label="印の上は指のカーソル")
    q = _mark(ed, "bad", 3)
    ed.move(q["x"] + q["w"] / 2, q["y"] + q["h"] / 2)
    wait_until(ed, "document.getElementById('ndcv').title.includes('バッド（悪い切り方）')", label="バッドのツールチップ")
    # 押す＝その位置へ（同期中はリプレイへ seek）
    rp_clear_log(ed)
    q = _mark(ed, "miss", 6)
    ed.click(q["x"] + q["w"] / 2, q["y"] + q["h"] / 2)
    wait_until(ed, "Math.abs(window._dbgApp.state().cur-6)<1e-6", label="拍 6 へ")
    wait_until(ed, f"window.__rpf.log.some(x=>x.cmd==='seek'&&Math.abs(x.t-{rich_sec(6)})<1e-6)", label="リプレイも 3 秒へ")
    q = _mark(ed, "miss", 10.25)   # スナップしない（出来事の拍そのもの）
    ed.click(q["x"] + q["w"] / 2, q["y"] + q["h"] / 2)
    wait_until(ed, "Math.abs(window._dbgApp.state().cur-10.25)<1e-6", label="拍 10.25 へ（スナップしない）")
    t.eq(ed.js("window._dbgApp.replay().view"), "play", "REPLAY は再生の画面のまま")
    t.no_errors()


def test_replay_marks_toggle(t):
    '''見出しの［点を重ねる］: オフで NLE の印・3D の輪・凡例を消し、環境設定のキー bsnm_rpMarks='0' に覚える（オンで '1'）。開き直すとオフのまま'''
    ed = _open(t)
    _wait_marks(ed)
    t.eq(ed.js("localStorage.getItem('bsnm_rpMarks')"), None, "キーが無い＝オン")
    click_id(ed, "#rpMarks")
    wait_until(ed, "(m=>!m.has&&!m.marks.length&&!m.rings.length)(window._dbgApp.rpMarks())", label="オフで消える")
    t.eq(ed.js("localStorage.getItem('bsnm_rpMarks')"), "0", "オフを覚える")
    t.eq(rp(ed)["mk"], "", "凡例も消える")
    t.ok(not ed.js("document.getElementById('rpMarks').classList.contains('on')"), "ボタンはオフの見た目")
    click_id(ed, "#rpMarks")
    _wait_marks(ed, len(MARKS))
    t.eq(ed.js("localStorage.getItem('bsnm_rpMarks')"), "1", "オンを覚える")
    t.eq(len(rp_calls(ed, "events")), 1, "入れ直しても出来事は読み直さない")
    # オフのまま開き直す
    click_id(ed, "#rpMarks")
    ed.wait(0.3)
    ed.reload(clear_storage=False)
    wait_until(ed, "!document.getElementById('bootCover')", label="開き直し")
    ed.load_fixture("rich")
    open_replay(ed, events=RICH_EVENTS)
    wait_until(ed, "window._dbgApp.replay().events>0", label="出来事は読む")
    ed.wait(0.4)
    m = rp_marks(ed)
    t.eq((m["has"], len(m["marks"]), len(m["rings"])), (False, 0, 0), "オフのまま（印も輪も無い）")
    t.no_errors()


def test_replay_marks_diff_and_close(t):
    '''今の難易度がリプレイの難易度と違えば出さない（凡例の行にそう書く）・戻すとまた出す。Standard 以外のプレイも出さない。
    一覧へ戻した・別の画面へ・新規で消す（同じリプレイへ戻ると出来事は読み直さずにまた出す）'''
    ed = _open(t)
    _wait_marks(ed)
    _key_nle(ed, "3")   # Hard へ
    wait_until(ed, "/^hard/i.test(window._dbgApp.state().diff)", label="Hard へ")
    wait_until(ed, "(m=>m.has&&!m.on&&!m.marks.length&&!m.rings.length)(window._dbgApp.rpMarks())", label="難易度が違うと出さない")
    wait_until(ed, "window._dbgApp.replay().mkMsg.includes('今の難易度（Hard）がこのリプレイ（Expert）と違うので、点は重ねていません')", label="凡例の行の知らせ")
    _key_nle(ed, "4")   # Expert へ戻す
    _wait_marks(ed, len(MARKS))
    # 一覧へ戻す＝消す・同じ物を押すと読み直さずに出す
    click_id(ed, "#rpBack")
    wait_until(ed, "!window._dbgApp.rpMarks().has&&!window._dbgApp.rpMarks().marks.length&&!window._dbgApp.rpMarks().rings.length", label="一覧へ戻すと消える")
    click_row(ed, "r1")
    _wait_marks(ed, len(MARKS))
    t.eq(len(rp_calls(ed, "events")), 1, "同じリプレイは読み直さない")
    # Standard 以外（r4 OneSaber）
    click_id(ed, "#rpBack")
    click_row(ed, "r4")
    wait_state(ed, "linked")
    wait_until(ed, "window._dbgApp.replay().mkMsg.includes('Standard 以外のプレイなので、点は重ねません')", label="Standard 以外の知らせ")
    t.eq(rp_calls(ed, "events")[-1]["body"], {"id": "r4"}, "別のリプレイは読む")
    t.eq((rp_marks(ed)["on"], rp_marks(ed)["marks"]), (False, []), "Standard 以外は出さない")
    # 別の画面へ＝消す・戻すとまた出す
    click_id(ed, "#rpBack")
    click_row(ed, "r1")
    _wait_marks(ed, len(MARKS))
    hover_pv(ed)
    ed.key("Tab")
    wait_until(ed, "window._dbgApp.replay().pvMode==='media'&&!window._dbgApp.rpMarks().has", label="MEDIA へ切り替えると消える")
    ed.wait(0.2)
    t.eq((rp_marks(ed)["marks"], rp_marks(ed)["rings"]), ([], []), "印も輪も消える")
    to_replay(ed)
    _wait_marks(ed, len(MARKS))
    # 新規＝消す
    file_menu(ed, "new")
    wait_until(ed, "!window._dbgApp.rpMarks().has&&!document.getElementById('rpFrame')", label="新規で消える")
    ed.wait(0.2)
    t.eq((rp_marks(ed)["marks"], rp_marks(ed)["rings"]), ([], []), "新規の後は印も輪も無い")
    t.no_errors()


def test_replay_marks_edit_and_fail(t):
    '''遊んだ後に編集した: ノーツを消すとその出来事は合わない（輪が消え、NLE の印は薄く・凡例の合わない数が増える）。Ctrl+Z で戻る。
    出来事を読めない時は凡例の行に知らせ、再生はそのまま'''
    ed = _open(t)
    _wait_marks(ed)
    o = ed.js("window._dbgApp.objScreen().find(o=>o.kind==='note'&&o.beat===3&&o.x===3&&o.y===1&&o.inView)")
    t.ok(o, "3D の拍 3 の青（ミス）のノーツが見えている")
    ed.move(o["sx"], o["sy"]); ed.wait(0.1)
    ed.click(o["sx"], o["sy"])   # 置いてある物の上のクリック＝選ぶ
    wait_until(ed, "window._dbgApp.state().sel===1", label="クリックで選ぶ")
    ed.key("Delete")
    wait_until(ed, "window._dbgApp.state().counts.notes===22&&window._dbgApp.rpMarks().unNotes===2", label="消すと合わないノーツが 2 に")
    ring3 = "window._dbgApp.rpMarks().rings.some(r=>r.kind==='note'&&r.beat===3&&r.x===3)"
    dim3 = "window._dbgApp.rpMarks().marks.find(q=>q.kind==='miss'&&q.beat===3).dim"
    wait_until(ed, f"!({ring3})&&{dim3}", label="消したノーツの輪が消え、NLE の印は薄く")
    t.ok(ed.js("window._dbgApp.rpMarks().rings.some(r=>r.kind==='note'&&r.beat===3&&r.x===0)"), "同じ拍の別のノーツ（バッド）の輪は残る")
    wait_until(ed, "window._dbgApp.replay().mkUn.includes('合わないノーツ 2 個')", label="凡例の合わない数")
    _hover_nle(ed)
    ed.key("z", ctrl=True)
    wait_until(ed, f"window._dbgApp.rpMarks().unNotes===1&&({ring3})&&!{dim3}", label="Ctrl+Z で輪も印も戻る")
    # 出来事を読めない
    rp_mock(ed, events={"ok": False, "error": "bad-replay"})
    click_id(ed, "#rpReopen")
    wait_state(ed, "linked")
    wait_until(ed, "window._dbgApp.replay().mkMsg.includes('リプレイの点を読めませんでした: リプレイのファイルを読めませんでした')", label="読めない知らせ")
    t.eq((rp_marks(ed)["has"], rp_marks(ed)["marks"]), (False, []), "読めなければ出さない")
    t.no_errors()


def test_replay_marks_with_review(t):
    '''審査の指摘の ▼ と同じ帯: 両方ある時は2段（▼ は上・点の印は下）＝同じ拍でも重ならない。点を消すと ▼ は元の位置へ'''
    ed = open_fixture_ready(t, "rich")
    _key_nle(ed, "4")
    wait_until(ed, "/^expert/i.test(window._dbgApp.state().diff)", label="Expert へ")
    rv_import(ed, [(None, "Expert\n\n3 - first\n6 - second\n")])
    wait_until(ed, "window._dbgApp.reviewMarks().length===2", label="審査の指摘の印")
    click_id(ed, "#rvPanel .rvClose")   # 一覧は閉じる（左上の REPLAY の窓に重なる）。印は残る
    before =ed.js("window._dbgApp.reviewMarks()")
    open_replay(ed, events=RICH_EVENTS)
    _wait_marks(ed, len(MARKS))
    ed.wait(0.2)
    rv = ed.js("window._dbgApp.reviewMarks()")
    q = _mark(ed, "miss", 6)
    r6 = next(r for r in rv if abs(r["x"] + r["w"] / 2 - (q["x"] + q["w"] / 2)) < 3)
    t.ok(r6["y"] + r6["h"] <= q["y"] + 0.01, f"拍 6: ▼（{r6['y']}〜{r6['y'] + r6['h']}）の下に点の印（{q['y']}〜）＝当たり判定も重ならない")
    t.ok(r6["y"] < before[1]["y"], f"▼ は上の段へ（{before[1]['y']} → {r6['y']}）")
    g = ed.js("window._dbgApp.nleScreen(0)")
    t.ok(q["y"] + q["h"] <= g["tempo"] + 0.5, "点の印は拍番号の帯の中")
    click_id(ed, "#rpMarks")
    wait_until(ed, "!window._dbgApp.rpMarks().has", label="点を消す")
    ed.wait(0.2)
    t.eq([(r["x"], r["y"], r["h"]) for r in ed.js("window._dbgApp.reviewMarks()")], [(r["x"], r["y"], r["h"]) for r in before], "▼ は元の位置")
    t.no_errors()

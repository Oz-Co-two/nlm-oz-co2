"""NLEのレーン: ロック/ソロ/ミュート（L/S/M キーと左端のボタン）・レーンの追加/削除。
仕様（docs/tutorial-advanced.md 3章）: ミュートとソロは表示を切り替えるだけで、書き出しには全部のレーンの中身が入る。
ロックは3Dビューで選んだり直したりできなくなる。レーンの状態はプロジェクトと一緒に保存される"""
import json

from e2e_helpers import wait_until, counts
from nle_helpers import (open_nle, clips, clip_xy, hover, menu, export_dat, nle, nle_mouse, scr, lane_y, show_lane, undo, take_errors, hover_canvas)


def _visible_notes(ed):
    """3Dビューに出ているノーツ系（ノーツ・ボム・壁・アーク・チェーン）の数"""
    return ed.js("window._dbgApp.objScreen().filter(o=>o.kind!=='light').length")


def _gutter_btn(ed, kind, lk, track):
    """レーン左端の L/S/M ボタンの中心（drawLayers の配置: L=溝の右端-62, S=-42, M=-22・幅16 / 上端+3・高さ14）"""
    s = scr(ed)
    off = {"l": 62, "s": 42, "m": 22}[kind]
    top = (s["notes"] if lk == "n" else s["lights"])[track]
    return s["left"] + s["gut"] - off + 8, top + 10


def test_mute_key_display_only(t):
    '''Notes 3 にマウスを置いてM→3Dのノーツが消える・書き出しは変わらない・保存内容に残る→もう一度Mで戻る'''
    ed = open_nle(t, "rich")
    before = export_dat(ed)
    nc = clips(ed, "n")[0]
    v0 = _visible_notes(ed)
    t.ok(v0 > 0, f"最初は3Dにノーツが出ている（{v0}）")
    hover(ed, 8, "n", nc["track"])
    ed.key("m")
    wait_until(ed, f"window._dbgApp.nle().mute.includes('n{nc['track']}')", label="ミュート")
    wait_until(ed, "window._dbgApp.objScreen().filter(o=>o.kind!=='light').length===0", label="3Dからノーツが消える")
    t.eq(counts(ed)["notes"], 7, "中身（ノーツの数）は減らない")
    t.eq(export_dat(ed), before, "ミュートしても書き出しには全部のレーンの中身が入る")
    pj = json.loads(ed.js("window._dbg.rt.buildProjectText()"))
    t.eq(pj["laneStates"]["mute"], [f"n{nc['track']}"], "ミュートの状態がプロジェクトに保存される")
    hover(ed, 8, "n", nc["track"])
    ed.key("m")
    wait_until(ed, "window._dbgApp.nle().mute.length===0", label="ミュート解除")
    wait_until(ed, f"window._dbgApp.objScreen().filter(o=>o.kind!=='light').length==={v0}", label="3Dにノーツが戻る")
    t.no_errors()


def test_solo_key(t):
    '''空のレーンをS（ソロ）→同じグループの他のレーンのノーツが3Dから消える・ライトのレーンには効かない・ソロとミュートは同時にONにならない'''
    ed = open_nle(t, "rich")
    before = export_dat(ed)
    nc = clips(ed, "n")[0]
    lights0 = ed.js("window._dbgApp.lights().events.length")
    hover(ed, 8, "n", 2)   # 空の Notes 1
    ed.key("s")
    wait_until(ed, "window._dbgApp.nle().solo.includes('n2')", label="Notes 1 をソロ")
    wait_until(ed, "window._dbgApp.objScreen().filter(o=>o.kind!=='light').length===0", label="ソロでないレーンのノーツが消える")
    t.eq(export_dat(ed), before, "ソロでも書き出しは変わらない")
    t.eq(ed.js("window._dbgApp.lights().events.length"), lights0, "ライトはノーツのソロの影響を受けない")
    hover(ed, 8, "n", nc["track"])
    ed.key("s")   # Notes 3 もソロ＝表示される
    wait_until(ed, "window._dbgApp.objScreen().filter(o=>o.kind!=='light').length>0", label="ソロに加えたレーンが出る")
    ed.key("m")   # 同じレーンをミュート＝ソロが外れる
    wait_until(ed, f"window._dbgApp.nle().mute.includes('n{nc['track']}')", label="ミュート")
    st = nle(ed)
    t.ok(f"n{nc['track']}" not in st["solo"], f"ミュートするとそのレーンのソロは外れる: {st['solo']}")
    t.no_errors()


def test_lock_blocks_3d_select(t):
    '''Notes 3 をL（ロック）→選んでいたノーツは外れ、3Dでクリックしても選べず中身も変わらない→もう一度Lで解除すると選べる'''
    ed = open_nle(t, "rich")
    nc = clips(ed, "n")[0]
    notes_js = "window._dbgApp.notes().notes.map(n=>[n.beat,n.x,n.y,n.c,n.d,n._tr])"

    def click_note():
        o = next(o for o in ed.js("window._dbgApp.objScreen()") if o["kind"] == "note" and o["inView"])
        ed.move(o["sx"], o["sy"]); ed.wait(0.1)
        ed.click(o["sx"], o["sy"]); ed.wait(0.15)
        return o
    hover_canvas(ed)
    ed.key("q")   # カメラ固定モード（配置済みのオブジェクトのクリック=選択）
    wait_until(ed, "window._dbgApp.state().camMode==='edit'", label="カメラ固定モード")
    ed.wait(0.15)
    click_note()
    wait_until(ed, "window._dbgApp.state().sel===1", label="ロック前はクリックで選べる")
    hover(ed, 8, "n", nc["track"])
    ed.key("l")
    wait_until(ed, f"window._dbgApp.nle().lock.includes('n{nc['track']}')", label="ロック")
    t.eq(ed.js("window._dbgApp.state().sel"), 0, "ロックしたレーンの選択は外れる")
    notes0, undo0 = ed.js(notes_js), ed.js("window._dbgApp.state().undo")
    click_note()
    t.eq(ed.js(notes_js), notes0, "ロック中のレーンのノーツはクリックしても変わらない")
    t.eq(ed.js("window._dbgApp.state().sel"), 0, "ロック中はクリックしても選べない")
    t.eq(ed.js("window._dbgApp.state().undo"), undo0, "ロック中のクリックは履歴を積まない")
    hover(ed, 8, "n", nc["track"])
    ed.key("l")
    wait_until(ed, "window._dbgApp.nle().lock.length===0", label="ロック解除")
    click_note()
    wait_until(ed, "window._dbgApp.state().sel===1", label="解除後は選べる")
    t.no_errors()


def test_lane_states_saved_and_restored(t):
    '''左端の L/S/M ボタンでも切り替わる／レーンの状態（ミュート/ソロ/ロック）は保存したプロジェクトを開き直しても戻る'''
    ed = open_nle(t, "rich")
    # 左端のボタン（Light 2）でもキーと同じように切り替わる
    for kind, field in (("l", "lock"), ("s", "solo"), ("m", "mute")):
        ed.click(*_gutter_btn(ed, kind, "l", 1))
        wait_until(ed, f"window._dbgApp.nle().{field}.includes('l1')", label=f"Light 2 の{field}ボタン")
    st = nle(ed)
    t.eq((st["lock"], st["solo"], st["mute"]), (["l1"], [], ["l1"]), "ボタン: ロックは独立・ソロはミュートで外れる")
    ed.click(*_gutter_btn(ed, "m", "l", 1))
    wait_until(ed, "window._dbgApp.nle().mute.length===0", label="もう一度押すと解除")
    hover(ed, 8, "n", 0); ed.key("m")
    hover(ed, 8, "l", 0); ed.key("l")
    show_lane(ed, "l", 2)   # 既定の画面では一番下の Light 1 は上の数pxしか見えない＝スクロールしてから
    hover(ed, 8, "l", 2); ed.key("s")
    wait_until(ed, "window._dbgApp.nle().solo.length===1", label="キーで状態を設定")
    want = {k: nle(ed)[k] for k in ("mute", "solo", "lock")}
    t.eq({k: sorted(v) for k, v in want.items()}, {"mute": ["n0"], "solo": ["l2"], "lock": ["l0", "l1"]}, "設定した状態")
    text = ed.js("window._dbg.rt.buildProjectText()")
    ed = t.fresh()
    ed.js(f"window._dbg.rt.applyProject(JSON.parse({json.dumps(text)}))")
    wait_until(ed, "window._dbgApp.nle().clips.length===2", label="開き直し")
    t.eq({k: nle(ed)[k] for k in ("mute", "solo", "lock")}, want, "開き直した後のレーンの状態")
    t.no_errors()


def test_lane_add_remove(t):
    '''一番上にクリップがあると削除できない／溝の右クリックでノーツのレーンを一番上に追加→既存のクリップは番号を保ったまま1段下がる→Undo。一番上が空なら削除できる'''
    ed = open_nle(t, "rich")
    before = export_dat(ed)
    s = scr(ed)
    gx = s["left"] + 20
    menu(ed, gx, lane_y(ed, "l", 1), "レーンを削除")   # 一番上（Light 3）にクリップがある＝削除できない
    ed.wait(0.2)
    t.eq(nle(ed)["lanes"]["l"], 3, "一番上にクリップがあるとライトのレーンは削除できない")
    t.eq(take_errors(ed, "クリップがあるため削除できません"), 1, "削除できない旨のエラー")
    menu(ed, gx, lane_y(ed, "n", 1), "レーンを追加")
    wait_until(ed, "window._dbgApp.nle().lanes.n===4", label="ノーツのレーンの追加")
    nc = clips(ed, "n")[0]
    t.eq(nc["track"], 1, "クリップは1段下がる（表示の番号 Notes 3 は同じ）")
    t.eq(nle(ed)["lanes"]["l"], 3, "ライトのレーンは変わらない")
    t.eq(export_dat(ed), before, "書き出しは変わらない")
    nle_mouse(ed)
    undo(ed)
    wait_until(ed, "window._dbgApp.nle().lanes.n===3", label="追加のUndo")
    t.eq(clips(ed, "n")[0]["track"], 0, "Undoでクリップの段も戻る")
    # 追加→一番上（空）を削除
    menu(ed, gx, lane_y(ed, "n", 1), "レーンを追加")
    wait_until(ed, "window._dbgApp.nle().lanes.n===4", label="もう一度追加")
    menu(ed, gx, lane_y(ed, "n", 1), "レーンを削除")
    wait_until(ed, "window._dbgApp.nle().lanes.n===3", label="空の一番上のレーンを削除")
    t.eq(clips(ed, "n")[0]["track"], 0, "削除でクリップは1段上がる")
    t.eq(export_dat(ed), before, "書き出しは変わらない")
    t.no_errors()


def test_hidden_clip_part_not_clickable(t):
    '''スクロールで表示窓の外に隠れたクリップの部分は押せない（2026-10-20・ノーツのレーンが 45px になり、隠れる所が増えた）:
    素材 basic のクリップは一番下の Notes 1 で、既定の画面では上の数pxしか見えない。その下（ライトのレーンの上）を押してもノーツのクリップは選ばれず、
    範囲選択でも囲めない。ノーツのグループをスクロールして見せると押せる'''
    ed = open_nle(t, "basic")
    c = clips(ed, "n")[0]
    s = scr(ed, c["beat"] + 2)
    v1 = nle(ed)["vp"]["n"][1]
    y_hidden = s["notes"][c["track"]] + s["laneH"] / 2   # クリップの縦の真ん中（窓の外＝ライトのレーンの上）
    t.ok(y_hidden > v1 + 3, f"準備: クリップの真ん中はノーツの表示窓の外（{y_hidden} > {v1}）")
    ed.click(s["x"], y_hidden); ed.wait(0.2)
    t.eq(nle(ed)["sel"], [], "隠れた所を押してもノーツのクリップは選ばれない")
    ed.drag(s["x"] - 30, y_hidden - 6, s["x"] + 30, y_hidden + 6, steps=4); ed.wait(0.2)
    t.eq(nle(ed)["sel"], [], "隠れた所だけを囲んでも選ばれない")
    show_lane(ed, "n", c["track"])
    ed.click(*clip_xy(ed, c, c["beat"] + 2))
    wait_until(ed, f"window._dbgApp.nle().sel.includes({json.dumps(c['id'])})", label="スクロールして見せると押せる")
    t.no_errors()


_SB_JS = """(id=>{ const e=document.getElementById(id); if(!e||getComputedStyle(e).display==='none') return null;
  const r=e.getBoundingClientRect(), t=e.querySelector('.sbTh').getBoundingClientRect(), tr=e.querySelector('.sbTr').getBoundingClientRect();
  return {x:r.left,y:r.top,w:r.width,h:r.height,thY:t.top,thH:t.height,thX:t.left+t.width/2,trY:tr.top,trH:tr.height,
          frac:tr.height>t.height?(t.top-tr.top)/(tr.height-t.height):0}; })"""
_SB = {"n": ("sbN", "sbNL"), "l": ("sbL", "sbLL")}   # 右端・溝の左端


def _sb(ed, sid):
    """スクロールバーの位置とつまみ（frac＝つまみが溝のどこにあるか 0〜1）。隠れていれば None"""
    return ed.js(f"{_SB_JS}({json.dumps(sid)})")


def _scroll(ed, lk):
    return nle(ed)["scroll"][lk]


def _wait_scroll(ed, lk, want, what):
    wait_until(ed, f"window._dbgApp.nle().scroll.{lk}==={want}", label=what)


def _same_place(t, ed, lk, what):
    """左右のつまみが同じ所にある（描画の次のフレームで揃うのを待つ）"""
    right, left = _SB[lk]
    js = f"(a=>b=>Math.abs(a.frac-b.frac)<0.02)({_SB_JS}({json.dumps(right)}))({_SB_JS}({json.dumps(left)}))"
    wait_until(ed, js, label=f"{what}: 左右のつまみが同じ所")


def test_lane_scrollbar_left(t):
    '''溝の左端の細いスクロールバー（2026-10-20・利用者の要望）: レーンが縦にスクロールする時だけ右と一緒に出て、範囲は右と同じ（各グループの表示窓）・
    左のつまみのドラッグで右も動く・右の▲▼で左も動く・左の溝のクリックでその位置へ・スクロールバーの上のホイールで縦にスクロール・
    スクロールできないグループは左右とも隠れる・溝の部品（レーン名・単独編集の帯）と重ならない'''
    ed = open_nle(t, "rich")
    s = scr(ed)
    for _ in range(2):   # ノーツのレーンを2本足して 5:3（ノーツの最大のスクロールを大きくする）
        menu(ed, s["left"] + 20, lane_y(ed, "n", 0), "レーンを追加")
        ed.wait(0.2)
    wait_until(ed, "window._dbgApp.nle().lanes.n===5", label="ノーツのレーンを5本に")
    ed.wait(0.2)
    s, g = scr(ed), nle(ed)
    for lk in ("n", "l"):
        right, left = (_sb(ed, i) for i in _SB[lk])
        t.ok(right and left, f"{lk}: スクロールできる時は左右とも出る")
        v0, v1 = g["vp"][lk]
        t.ok(abs(left["y"] - v0) < 0.6 and abs(left["y"] + left["h"] - v1) < 0.6 and abs(right["y"] - v0) < 0.6 and abs(right["h"] - left["h"]) < 0.6,
             f"{lk}: 左右とも範囲はグループの表示窓（{v0}〜{v1}）: 右 {right['y']}+{right['h']} / 左 {left['y']}+{left['h']}")
        t.ok(left["x"] - s["left"] >= 1 and left["x"] + left["w"] <= s["left"] + 12, f"{lk}: 左は溝の左端（{left['x'] - s['left']}〜{left['x'] + left['w'] - s['left']}px）")
    b = next(b for b in s["eo"] if b["t"] == 0)
    left = _sb(ed, "sbNL")
    t.ok(left["x"] + left["w"] <= b["x"] - 1, f"単独編集の帯と重ならない（スクロールバーの右端 {left['x'] + left['w']} / 帯の左端 {b['x']}）")
    mx = g["scroll"]["maxN"]
    t.ok(mx > 40, f"ノーツの最大のスクロール {mx}px")
    # 左のつまみのドラッグ（下へ10px）→ スクロールが進み、右のつまみも同じ所へ
    left = _sb(ed, "sbNL")
    x, y = left["thX"], left["thY"] + left["thH"] / 2
    ed.drag(x, y, x, y + 10, steps=5)
    want = round(10 * mx / (left["trH"] - left["thH"]))
    wait_until(ed, f"Math.abs(window._dbgApp.nle().scroll.n-{want})<=1", label=f"左のつまみのドラッグでスクロール（約{want}px）")
    t.eq(scr(ed)["notes"][0], g["vp"]["n"][0] - _scroll(ed, "n"), "レーンもスクロールした分だけ上へ")
    _same_place(t, ed, "n", "左のドラッグ")
    # 左のつまみを一番下まで → 右も一番下
    left = _sb(ed, "sbNL")
    ed.drag(left["thX"], left["thY"] + 5, left["thX"], left["thY"] + 200, steps=6)
    _wait_scroll(ed, "n", mx, "左のつまみを一番下まで")
    _same_place(t, ed, "n", "一番下")
    # 右の▲（1レーン分）→ 左も動く
    ed.js("document.querySelector('#sbN .sbUp').click()")
    _wait_scroll(ed, "n", mx - s["laneH"], "右の▲")
    _same_place(t, ed, "n", "右の▲")
    # 左の溝のクリック（つまみの無い所）＝その位置へ
    ed.js("document.querySelector('#sbN .sbUp').click()")
    _wait_scroll(ed, "n", max(0, mx - 2 * s["laneH"]), "右の▲をもう1回")
    left = _sb(ed, "sbNL")
    cy = left["trY"] + left["trH"] - 3
    ed.click(left["thX"], cy)
    want = min(mx, round((cy - left["trY"]) / left["trH"] * mx))
    wait_until(ed, f"Math.abs(window._dbgApp.nle().scroll.n-{want})<=1", label=f"左の溝の下の方のクリック（約{want}px）")
    _same_place(t, ed, "n", "左の溝のクリック")
    # スクロールバーの上のホイール（下へ1目盛り＝1レーン分・上へ）。左でも右でも同じ
    ed.js("document.querySelector('#sbN .sbUp').click();document.querySelector('#sbN .sbUp').click();document.querySelector('#sbN .sbUp').click();true")
    _wait_scroll(ed, "n", 0, "一番上へ")
    left = _sb(ed, "sbNL")
    ed.wheel(left["thX"], left["y"] + left["h"] / 2, 100)
    _wait_scroll(ed, "n", s["laneH"], "左の上のホイール（下へ）")
    _same_place(t, ed, "n", "左のホイール")
    right = _sb(ed, "sbN")
    ed.wheel(right["thX"], right["trY"] + right["trH"] / 2, -100)
    _wait_scroll(ed, "n", 0, "右の上のホイール（上へ）")
    ed.wheel(left["thX"], left["y"] + left["h"] / 2, 100)
    _wait_scroll(ed, "n", s["laneH"], "左の上のホイール（もう一度下へ）")
    _same_place(t, ed, "n", "ホイール")
    t.eq(_scroll(ed, "l"), 0, "ライトのグループは動かない")
    # ライトの左のつまみのドラッグ → ライトだけ
    left = _sb(ed, "sbLL")
    ed.drag(left["thX"], left["thY"] + left["thH"] / 2, left["thX"], left["thY"] + 200, steps=6)
    _wait_scroll(ed, "l", nle(ed)["scroll"]["maxL"], "ライトの左のつまみを一番下まで")
    _same_place(t, ed, "l", "ライト")
    t.eq(_scroll(ed, "n"), s["laneH"], "ノーツのグループは動かない")
    # スクロールできないグループ: 空のプロジェクトでノーツ1本（ライト5本）＝ノーツは左右とも隠れ、ライトは左右とも出る
    ed = t.fresh()   # 新規はノーツ1本・ライト3本（2026-10-20）→ ライトを2本足して 1:5
    ed.js("(()=>{const rt=window._dbg.rt; rt.laneAdd('l'); rt.laneAdd('l'); return true})()")
    wait_until(ed, "(g=>g.lanes.n===1&&g.lanes.l===5)(window._dbgApp.nle())", label="ノーツ1・ライト5")
    ed.wait(0.3)
    g = nle(ed)
    t.eq((g["scroll"]["maxN"], _sb(ed, "sbN"), _sb(ed, "sbNL")), (0, None, None), "スクロールできないノーツは左右とも隠れる")
    t.ok(g["scroll"]["maxL"] > 0 and _sb(ed, "sbL") and _sb(ed, "sbLL"), f"ライトは左右とも出る（最大 {g['scroll']['maxL']}px）")
    t.no_errors()


def test_lane_scrollbar_left_ui_scale(t):
    '''UI文字サイズ 150%・80% でも、左のスクロールバーはグループの表示窓に合い、つまみのドラッグで動かした分だけスクロールする'''
    for z in (1.5, 0.8):
        ed = open_nle(t, "rich")
        ed.js(f"localStorage.setItem('bsnm_uiscale','{z}');true")
        ed.wait(0.6)   # 環境設定のミラーへ書き戻されるのを待つ
        ed.reload(clear_storage=False)
        ed.load_fixture("rich")
        wait_until(ed, f"Math.abs(parseFloat(document.getElementById('menubar').style.zoom)-{z})<0.01", label=f"UI文字サイズ {z}")
        ed.wait(0.3)
        g = nle(ed)
        left = _sb(ed, "sbNL")
        v0, v1 = g["vp"]["n"]
        t.ok(left and abs(left["y"] - v0) < 0.6 and abs(left["y"] + left["h"] - v1) < 0.6, f"{z}: 範囲は表示窓（{v0}〜{v1}）: {left}")
        mx = g["scroll"]["maxN"]
        x, y = left["thX"], left["thY"] + left["thH"] / 2
        ed.drag(x, y, x, y + 4, steps=4)
        want = round(4 * mx / (left["trH"] - left["thH"]))
        wait_until(ed, f"Math.abs(window._dbgApp.nle().scroll.n-{want})<=1", label=f"{z}: 左のつまみのドラッグ（約{want}px）")
        _same_place(t, ed, "n", f"{z}")
        t.no_errors()


def test_lane_add_resets_solo_mute(t):
    '''レーンを追加するとソロ/ミュートは外れ（位置で覚えているため）、ロックは同じレーンに付いたまま1段ずれる'''
    ed = open_nle(t, "rich")
    hover(ed, 8, "n", 0); ed.key("l")
    hover(ed, 8, "n", 1); ed.key("m")
    wait_until(ed, "window._dbgApp.nle().mute.length===1&&window._dbgApp.nle().lock.length===1", label="ロックとミュート")
    menu(ed, scr(ed)["left"] + 20, lane_y(ed, "n", 2), "レーンを追加")
    wait_until(ed, "window._dbgApp.nle().lanes.n===4", label="レーンの追加")
    st = nle(ed)
    t.eq(st["mute"], [], "ミュートは外れる")
    t.eq(st["lock"], ["n1"], "ロックは同じレーン（1段下がった Notes 3）に付いたまま")
    t.no_errors()

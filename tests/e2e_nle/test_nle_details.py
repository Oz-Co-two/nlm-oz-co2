"""NLEの細かい操作: Musicの端のトリム・Musicとクリップの連動移動・クリップの色・クリップの左右反転・パン/ズーム・
レーンの上限（10本）・空きの無い所への貼り付け。
素材 rich は BPM120（拍16から150）・音源16秒（=拍36で曲が終わる）・Hard/Expert の2難易度。basic は BPM120・音源16秒（=32拍）"""
import copy
import json

from e2e_helpers import wait_until, counts, cell, place_at, switch_diff, hover_3d
from nle_helpers import (open_nle, clips, select, hover, menu, clip_xy, export_dat, nle, nle_mouse, scr, lane_y,
                         undo, redo, take_errors)

OBJ_KEYS = ("colorNotes", "bombNotes", "obstacles", "sliders", "burstSliders", "basicBeatmapEvents")
TLGUT = 128   # NLE・Musicの左の溝の幅（editor-app.js の TLGUT/LGUT）


# ---- 小道具 ----
def _ms(ed, beat):
    return ed.js(f"window._dbgApp.musicScreen({beat})")


def _my(ed):
    """Musicの段の本体（上端13pxのヘッダーより下）のy"""
    m = _ms(ed, 0)
    return m["top"] + m["h"] * 0.6


def _music(ed):
    return nle(ed)["music"]


def _ov_right(ed):
    """Musicの段（キャンバス）の右端のページx"""
    return ed.js("(r=>r.right)(document.getElementById('ovcv').getBoundingClientRect())")


def _pos(ed, beat):
    """拍 beat で鳴る元の音源の秒（無ければ None）"""
    return ed.js(f"window._dbgApp.audioPosAtBeat({beat})")


def _frame(ed):
    """描画を2フレーム待つ（キャンバスに描いた物・当たり判定は次の描画で更新される）"""
    ed.js("new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(()=>r(true))))")


def _timers(ed):
    """ページの待機中の setTimeout(0) を済ませる（同じ遅延のタイマーは登録順に動く＝後から登録したこれが済めば前のも済んでいる）。
    色の選択画面は「外のクリックで閉じる」処理を setTimeout(0) で登録する。ヘッドレスでは1フレームが重く（約0.2秒）、
    入力の方がタイマーより先に処理されるため、開いてすぐ外をクリックすると閉じないことがある"""
    ed.js("new Promise(r=>setTimeout(()=>r(true),0))")


def _undo_n(ed):
    return ed.js("window._dbgApp.state().undo")


def _objs(dat):
    return {k: dat.get(k, []) for k in OBJ_KEYS}


def _cut_dat(dat, cut):
    """書き出しのうち、頭の拍が cut 以下の物だけ（曲の終わりで切った時の期待値）"""
    return {k: [o for o in dat.get(k, []) if o["b"] <= cut + 1e-6] for k in OBJ_KEYS}


def _seek(ed, beat):
    """数字の目盛りをクリックして再生位置を beat へ"""
    s = scr(ed, beat)
    ed.click(s["x"], (s["ruler"] + s["tempo"]) / 2)
    wait_until(ed, f"window._dbgApp.state().cur==={beat}", label=f"再生位置を拍{beat}へ")


def _win(ed):
    """NLEの表示窓（左端の拍・表示している拍数）。拍0と拍1の画面xから求める"""
    a, b = scr(ed, 0), scr(ed, 1)
    ppb = b["x"] - a["x"]
    return {"b0": round(-(a["x"] - a["left"] - a["gut"]) / ppb, 3), "span": round((a["w"] - a["gut"]) / ppb, 3)}


def _enter(ed):
    """文字（\\r）付きのEnter。入力欄の確定（change）は文字付きのキー入力で起きる（ed.key('Enter') は文字無しで change が起きない）"""
    base = dict(key="Enter", code="Enter", windowsVirtualKeyCode=13, nativeVirtualKeyCode=13)
    ed.call("Input.dispatchKeyEvent", type="keyDown", text="\r", **base)
    ed.call("Input.dispatchKeyEvent", type="keyUp", **base)


def _sec_cols(ed, diff="hardstandard.dat"):
    """保存内容（buildProjectText）の各クリップの色 (col=既定の色番号, colHex=指定した色)"""
    pj = json.loads(ed.js("window._dbg.rt.buildProjectText()"))
    return [(s.get("lk"), s.get("col"), s.get("colHex")) for s in pj["difficulties"][diff]["sections"]]


def _swatch_xy(ed, clip):
    """クリップの名前の左の色の四角（drawLayers: クリップの左上から(4,4)・18×9）の中心"""
    s = scr(ed, clip["beat"])
    top = (s["notes"] if clip["lk"] == "n" else s["lights"])[clip["track"]]
    return s["x"] + 13, top + 12.5


def _pixel(ed, x, y):
    """NLEのキャンバスの画素（RGB）"""
    return ed.js(f"(()=>{{const c=document.getElementById('ndcv'), r=c.getBoundingClientRect(), d=devicePixelRatio;"
                 f"return [...c.getContext('2d').getImageData(Math.round(({x}-r.left)*d),Math.round(({y}-r.top)*d),1,1).data].slice(0,3)}})()")


def _rgb(hexs):
    return [int(hexs[i:i + 2], 16) for i in (1, 3, 5)]


def _show_lane(ed, lk, tr):
    """レーン tr がグループの表示窓に入るまで、中ボタンの縦ドラッグでそのグループをスクロールする（7本以上は窓に収まらない）"""
    for _ in range(12):
        s = scr(ed)
        v0, v1 = nle(ed)["vp"][lk]
        top = (s["notes"] if lk == "n" else s["lights"])[tr]
        if max(top + 5, v0 + 2) <= min(top + s["laneH"] - 5, v1 - 3):
            return
        x, y = scr(ed, 30)["x"], (v0 + v1) / 2
        dy = -s["laneH"] if top > v1 - s["laneH"] / 2 else s["laneH"]   # 上へ引く=下のレーンが出る
        ed.drag(x, y, x, y + dy, steps=4, button="middle")
    raise AssertionError(f"{lk}{tr} のレーンを表示窓に出せません")


def _lock_all(ed, lk, n):
    """グループ lk のレーン 0..n-1 を全部ロックする（Lキーはマウスのあるレーンに効く）"""
    for tr in range(n):
        if f"{lk}{tr}" in nle(ed)["lock"]:
            continue
        _show_lane(ed, lk, tr)
        hover(ed, 30, lk, tr)
        ed.key("l")
        wait_until(ed, f"window._dbgApp.nle().lock.includes('{lk}{tr}')", label=f"{lk}{tr} のロック")


def _add_lanes(ed, lk, n):
    """溝の右クリック「レーンを追加」を n 回"""
    for _ in range(n):
        k = nle(ed)["lanes"][lk]
        _show_lane(ed, lk, 0)
        menu(ed, scr(ed)["left"] + 20, lane_y(ed, lk, 0), "レーンを追加")
        wait_until(ed, f"window._dbgApp.nle().lanes.{lk}==={k + 1}", label=f"{lk}レーンの追加（{k + 1}本目）")


# ---- 1. Musicの端のトリム ----
def test_music_trim_right(t):
    '''Musicの右端を拍9までドラッグ→音源の窓が4.5秒に縮み、拍9より後のノーツ・ライト等は全難易度で書き出されない（クリップの中身は残る）→Undo/Redo'''
    ed = open_nle(t, "rich")
    before = export_dat(ed)
    clips0 = clips(ed)
    t.eq(_music(ed)["segs"], None, "最初は分割なしの1本")
    # 曲の終わり（拍36）は最初の表示窓（拍0〜32）の外＝Musicの段のCtrl+ホイールで縮小して見えるようにする
    ed.wheel(_ms(ed, 10)["x"], _my(ed), 100, ctrl=True)
    wait_until(ed, f"window._dbgApp.musicScreen(36).x<{_ov_right(ed) - 10}", label="縮小で曲の終わりが見える")
    _frame(ed)
    y = _my(ed)
    ed.drag(_ms(ed, 36)["x"] - 1, y, _ms(ed, 9)["x"], y, steps=12)
    wait_until(ed, "(window._dbgApp.nle().music.segs||[]).length===1", label="右端のトリム")
    t.eq(_music(ed)["segs"], [{"beat": 0, "off": 0, "dur": 4.5}], "拍0から音源の0〜4.5秒（拍9まで）")
    t.eq([_pos(ed, b) for b in (4, 8.5, 9, 12)], [2, 4.25, None, None], "拍9以降は音が鳴らない（手前の音の位置はそのまま）")
    t.eq(clips(ed), clips0, "ノーツ・ライトのクリップと中身は変わらない")
    after = export_dat(ed)
    t.eq(sorted(after), sorted(before), "書き出す難易度は同じ")
    for name, dat in before.items():
        t.eq(_objs(after[name]), _cut_dat(dat, 9), f"{name}: 曲の終わり（拍9）より後の物は書き出さない")
    nle_mouse(ed)
    undo(ed)
    wait_until(ed, "window._dbgApp.nle().music.segs===null", label="トリムのUndo")
    t.eq(export_dat(ed), before, "Undoで書き出しが元に戻る")
    redo(ed)
    wait_until(ed, "(window._dbgApp.nle().music.segs||[]).length===1", label="トリムのRedo")
    t.eq(_music(ed)["segs"], [{"beat": 0, "off": 0, "dur": 4.5}], "Redoで再び4.5秒")
    t.no_errors()


def test_music_trim_left(t):
    '''Musicの左端を拍4までドラッグ→拍4で音源の2秒目が鳴る（音の位置は動かない）・拍4より前は無音・書き出しは同じ→左端を拍0へ戻すと元の音が戻る（非破壊）→Undo'''
    ed = open_nle(t, "rich")
    before = export_dat(ed)
    pos0 = [_pos(ed, b) for b in (4, 10, 20)]
    y = _my(ed)
    ed.drag(_ms(ed, 0)["x"] + 2, y, _ms(ed, 4)["x"], y, steps=12)   # 左端は溝の境目（拍0）。溝の中は対象外なので2px右
    wait_until(ed, "(window._dbgApp.nle().music.segs||[]).length===1&&window._dbgApp.nle().music.segs[0].beat===4", label="左端のトリム")
    t.eq(_music(ed)["segs"], [{"beat": 4, "off": 2, "dur": 14}], "拍4から音源の2秒目以降（長さは2秒短く）")
    t.eq([_pos(ed, b) for b in (4, 10, 20)], pos0, "拍4以降の音の位置はトリムの前と同じ")
    t.eq([_pos(ed, b) for b in (0, 3.5)], [None, None], "拍4より前は無音")
    t.eq(export_dat(ed), before, "曲の終わりは同じ＝書き出しは変わらない")
    ed.drag(_ms(ed, 4)["x"] + 1, y, _ms(ed, 0)["x"] + 1, y, steps=12)
    wait_until(ed, "window._dbgApp.nle().music.segs[0].beat===0", label="左端を拍0へ戻す")
    t.eq(_music(ed)["segs"], [{"beat": 0, "off": 0, "dur": 16}], "縮めた分の音は消えておらず元の長さに戻る")
    t.eq(_pos(ed, 2), 1, "拍2で音源の1秒目が鳴る")
    nle_mouse(ed)
    undo(ed)
    wait_until(ed, "window._dbgApp.nle().music.segs[0].beat===4", label="戻したトリムのUndo")
    undo(ed)
    wait_until(ed, "window._dbgApp.nle().music.segs===null", label="最初のトリムのUndo")
    t.eq([_pos(ed, b) for b in (0, 4, 10)], [0, 2, 5], "Undoで元の音に戻る")
    t.no_errors()


def test_music_edge_click_no_change(t):
    '''Musicの端をクリックしただけ（動かさない）では、Musicの状態・履歴・未保存の判定は変わらない'''
    ed = open_nle(t, "rich")
    u0 = _undo_n(ed)
    ed.click(_ms(ed, 0)["x"] + 2, _my(ed))   # 左端のつまみ
    segs, same = _music(ed)["segs"], ed.js("window._dbgApp.dirty()")["same"]
    t.eq(_undo_n(ed), u0, "履歴は積まない")
    t.eq(segs, None, "分割なしのまま")
    t.ok(same, "未保存の判定は変わらない")
    t.no_errors()


def test_music_trim_only_real_edge(t):
    '''Musicの本当の端が表示窓の外にある時、窓の端（キャンバスの右端・溝の境目）を掴んでもトリムにならない（ノーツのクリップと同じく見えている本当の端だけがつまみ）'''
    ed = open_nle(t, "rich")
    y = _my(ed)
    right = _ov_right(ed)
    t.ok(_ms(ed, 36)["x"] > right, "曲の終わり（拍36）は表示窓の右の外")
    ed.drag(right - 2, y, _ms(ed, 24)["x"], y, steps=10)   # 本体を掴んで左へ＝拍0より左へは動かない
    right_segs = _music(ed)["segs"]
    if right_segs is not None:
        nle_mouse(ed)
        undo(ed)
        wait_until(ed, "window._dbgApp.nle().music.segs===null", label="トリムのUndo")
    # 表示窓を拍4からにする（Musicの頭は窓の左の外）。中ボタンのドラッグ＝表示の移動
    ppb = _ms(ed, 1)["x"] - _ms(ed, 0)["x"]
    x20 = _ms(ed, 20)["x"]
    ed.drag(x20, y, x20 - 4 * ppb, y, steps=8, button="middle")
    gut = _ms(ed, 0)["left"] + TLGUT
    wait_until(ed, f"Math.abs(window._dbgApp.musicScreen(4).x-{gut})<1", label="表示窓を拍4から")
    _frame(ed)
    ed.drag(gut + 2, y, _ms(ed, 8)["x"], y, steps=10)   # 溝の境目を掴んで右へ
    left_segs = _music(ed)["segs"]
    t.eq(right_segs, None, "右: キャンバスの端（窓で切れた見かけの端）を掴んでもトリムにならない")
    t.eq(left_segs, None, "左: 窓を拍4からにして溝の境目を掴んでもトリムにならない")
    t.no_errors()


# ---- 2. Musicとクリップの連動移動 ----
def test_music_and_clip_linked_move(t):
    '''Musicとクリップを同時に選びクリップを拍+4へドラッグ→Musicも+4（音とノーツの関係が保たれる）→Undo1回で両方戻る／Musicのドラッグでもクリップが連動／左へは先頭が拍0で揃って止まる'''
    ed = open_nle(t, "basic")
    c0 = clips(ed, "n")[0]
    y = _my(ed)
    nle_mouse(ed)
    ed.click(scr(ed)["left"] + 300, lane_y(ed, "n", 0))   # 空いている所のクリック＝選択を全部外す
    wait_until(ed, "window._dbgApp.nle().music.sel.length===0&&window._dbgApp.nle().sel.length===0", label="選択の解除")
    ed.click(_ms(ed, 10)["x"], y)
    wait_until(ed, "window._dbgApp.nle().music.sel.length===1", label="Musicの選択")
    select(ed, c0, shift=True)
    t.eq((nle(ed)["sel"], _music(ed)["sel"]), ([c0["id"]], [0]), "Shift+クリックでクリップとMusicを同時に選ぶ")
    pos0 = _pos(ed, 1)   # 最初のノーツ（拍1）の所で鳴る音
    u0 = _undo_n(ed)
    x0, y0 = clip_xy(ed, c0, 2)
    ed.drag(x0, y0, scr(ed, 6)["x"], y0, steps=12)
    wait_until(ed, "window._dbgApp.nle().clips[0].beat===4&&window._dbgApp.nle().music.beat===4", label="クリップの移動にMusicが連動")
    t.eq([n["beat"] for n in ed.js("window._dbgApp.notes().notes")][:2], [5, 6], "ノーツは+4拍")
    t.eq(_pos(ed, 5), pos0, "動かした後の最初のノーツ（拍5）でも同じ音が鳴る")
    t.eq([n["b"] for n in export_dat(ed)["HardStandard.dat"]["colorNotes"]][:2], [5, 6], "書き出しのノーツも+4拍")
    t.eq(_undo_n(ed) - u0, 1, "1回のドラッグで履歴は1つ")
    nle_mouse(ed)
    undo(ed)
    wait_until(ed, "window._dbgApp.nle().clips[0].beat===0&&window._dbgApp.nle().music.beat===0", label="Undo1回で両方戻る")
    redo(ed)
    wait_until(ed, "window._dbgApp.nle().clips[0].beat===4&&window._dbgApp.nle().music.beat===4", label="Redo")
    ed.drag(_ms(ed, 14)["x"], y, _ms(ed, 12)["x"], y, steps=10)   # Musicを-2拍
    wait_until(ed, "window._dbgApp.nle().clips[0].beat===2&&window._dbgApp.nle().music.beat===2", label="Musicの移動にクリップが連動")
    t.eq([n["beat"] for n in ed.js("window._dbgApp.notes().notes")][:2], [3, 4], "3Dのノーツも連動して動く")
    # 左へ大きく引く: 先頭（クリップもMusicも拍2）が拍0に着いた所で揃って止まる（相対位置は崩れない）
    c1 = clips(ed, "n")[0]
    x0, y0 = clip_xy(ed, c1, 3)
    ed.drag(x0, y0, x0 - (scr(ed, 6)["x"] - scr(ed, 0)["x"]), y0, steps=12)   # クリップを-6拍（拍0より左まで）
    wait_until(ed, "window._dbgApp.nle().clips[0].beat===0", label="クリップを左へ")
    t.eq((clips(ed, "n")[0]["beat"], _music(ed)["beat"]), (0, 0), "クリップのドラッグ: 両方とも拍0で止まる")
    nle_mouse(ed)
    undo(ed)
    wait_until(ed, "window._dbgApp.nle().clips[0].beat===2&&window._dbgApp.nle().music.beat===2", label="Undo")
    ed.drag(_ms(ed, 14)["x"], y, _ms(ed, 8)["x"], y, steps=12)   # Musicを-6拍
    ed.wait(0.1)
    got = (clips(ed, "n")[0]["beat"], _music(ed)["beat"])
    t.ok(got[0] == got[1], f"Musicのドラッグでもクリップとの相対位置は崩れない: {got}")
    t.eq(got, (0, 0), "Musicのドラッグ: 両方とも拍0で止まる")
    t.no_errors()


def test_drag_blocked_at_zero_no_history(t):
    '''拍0にあるMusic・クリップを左へドラッグしても動かない時は、履歴を積まない（Undoが空振りしない）'''
    ed = open_nle(t, "basic")
    y = _my(ed)
    t.eq(_music(ed)["sel"], [0], "読込直後はMusicが選ばれている")
    u0 = _undo_n(ed)
    ed.drag(_ms(ed, 10)["x"], y, _ms(ed, 6)["x"], y, steps=8)
    music_pushed = _undo_n(ed) - u0
    t.eq(_music(ed)["beat"], 0, "Musicは拍0より左へ動かない")
    c0 = clips(ed, "n")[0]
    select(ed, c0)   # 選択の変化は1動作として履歴に入る（ここまでは正しい）
    u1 = _undo_n(ed)
    x0, y0 = clip_xy(ed, c0, 2)
    ed.drag(x0, y0, x0 - 80, y0, steps=8)
    clip_pushed = _undo_n(ed) - u1
    t.eq(clips(ed, "n")[0]["beat"], 0, "クリップは拍0より左へ動かない")
    t.eq((music_pushed, clip_pushed), (0, 0), "動かなければ履歴は積まない（Music・クリップとも）")
    t.no_errors()


# ---- 3. クリップの色 ----
def test_clip_color_change_saved(t):
    '''クリップの右クリック「色を変更…」でHexに#3366CCを入れて確定→そのクリップだけ色が変わり（色の四角も）書き出しは同じ→Undo/Redo→保存して開き直しても残る'''
    ed = open_nle(t, "rich")
    before = export_dat(ed)
    nc, lc = clips(ed, "n")[0], clips(ed, "l")[0]
    cols0 = _sec_cols(ed)
    t.eq(cols0, [("n", 0, None), ("l", 1, None)], "最初は既定の色（色番号のみ）")
    px_n0, px_l0 = _pixel(ed, *_swatch_xy(ed, nc)), _pixel(ed, *_swatch_xy(ed, lc))
    t.eq(px_n0, _rgb("#e2605b"), "ノーツのクリップの色の四角は既定の1番目の色")
    menu(ed, *clip_xy(ed, nc, 8), "色を変更")
    wait_until(ed, "!!document.getElementById('cpanel')", label="色の選択画面")
    _timers(ed)   # 外クリックで閉じる処理の登録（setTimeout 0）を済ませる
    t.eq(ed.js("document.querySelector('#cpanel .cpHex input').value"), "#E2605BFF", "今の色が入っている")
    p = ed.js("(r=>({x:r.left+r.width/2,y:r.top+r.height/2}))(document.querySelector('#cpanel .cpHex input').getBoundingClientRect())")
    u0 = _undo_n(ed)
    ed.click(p["x"], p["y"])
    ed.key("a", ctrl=True)
    ed.call("Input.insertText", text="#3366CC")
    _enter(ed)
    wait_until(ed, "JSON.parse(window._dbg.rt.buildProjectText()).difficulties['hardstandard.dat'].sections[0].colHex==='#3366cc'", label="色の確定")
    t.eq(_sec_cols(ed), [("n", 0, "#3366cc"), ("l", 1, None)], "ノーツのクリップだけ色が変わる")
    t.eq(_undo_n(ed) - u0, 1, "履歴は1つ")
    ed.click(scr(ed, 20)["x"], (scr(ed)["tempo"] + scr(ed)["marker"]) / 2)   # 外（テンポの帯）をクリックして閉じる
    wait_until(ed, "!document.getElementById('cpanel')", label="色の選択画面を閉じる")
    _frame(ed)
    t.eq(_pixel(ed, *_swatch_xy(ed, nc)), _rgb("#3366cc"), "色の四角が新しい色で描かれる")
    t.eq(_pixel(ed, *_swatch_xy(ed, lc)), px_l0, "ライトのクリップの色は変わらない")
    t.eq(export_dat(ed), before, "色を変えても書き出しは変わらない")
    nle_mouse(ed)
    undo(ed)
    wait_until(ed, "JSON.parse(window._dbg.rt.buildProjectText()).difficulties['hardstandard.dat'].sections[0].colHex==null", label="色のUndo")
    _frame(ed)
    t.eq(_pixel(ed, *_swatch_xy(ed, nc)), px_n0, "Undoで元の色の四角に戻る")
    redo(ed)
    wait_until(ed, "JSON.parse(window._dbg.rt.buildProjectText()).difficulties['hardstandard.dat'].sections[0].colHex==='#3366cc'", label="色のRedo")
    # 保存して開き直す
    text = ed.js("window._dbg.rt.buildProjectText()")
    ed = t.fresh()
    ed.js(f"window._dbg.rt.applyProject(JSON.parse({json.dumps(text)}))")
    wait_until(ed, "window._dbgApp.nle().clips.length===2", label="開き直し")
    t.eq(_sec_cols(ed), [("n", 0, "#3366cc"), ("l", 1, None)], "開き直しても色が残る")
    _frame(ed)
    nc2 = clips(ed, "n")[0]
    t.eq(_pixel(ed, *_swatch_xy(ed, nc2)), _rgb("#3366cc"), "開き直した後も色の四角は新しい色")
    ed.click(*_swatch_xy(ed, nc2))   # 色の四角のクリックでも同じ選択画面が開く
    wait_until(ed, "!!document.getElementById('cpanel')", label="色の四角から色の選択画面")
    t.eq(ed.js("document.querySelector('#cpanel .cpHex input').value"), "#3366CCFF", "選択画面には保存した色が入っている")
    t.no_errors()


def test_clip_color_wheel_drag_one_undo(t):
    '''色の選択画面の円をドラッグして色を変える→1回のドラッグは1回のUndoで元の色に戻る'''
    ed = open_nle(t, "rich")
    nc = clips(ed, "n")[0]
    ed.click(*_swatch_xy(ed, nc))
    wait_until(ed, "!!document.getElementById('cpanel')", label="色の四角から色の選択画面")
    r = ed.js("(r=>({x:r.left,y:r.top,w:r.width,h:r.height}))(document.querySelector('#cpanel canvas.cw').getBoundingClientRect())")
    cx, cy = r["x"] + r["w"] / 2, r["y"] + r["h"] / 2
    u0 = _undo_n(ed)
    ed.drag(cx + 30, cy, cx, cy + 30, steps=8)
    hex1 = _sec_cols(ed)[0][2]
    t.ok(hex1 and hex1 != "#e2605b", f"円のドラッグで色が変わる: {hex1}")
    pushed = _undo_n(ed) - u0
    t.eq(pushed, 1, "1回のドラッグで履歴は1つ")
    nle_mouse(ed)
    undo(ed)
    wait_until(ed, "JSON.parse(window._dbg.rt.buildProjectText()).difficulties['hardstandard.dat'].sections[0].colHex==null", label="Undo1回で元の色")
    t.no_errors()


# ---- 4. クリップの左右反転 ----
MIR_D = {0: 0, 1: 1, 2: 3, 3: 2, 4: 5, 5: 4, 6: 7, 7: 6, 8: 8}   # 向き: 上下・ドットはそのまま、左右と斜めは左右を入れ替え
MIR_ET = {2: 3, 3: 2, 12: 13, 13: 12}                            # ライト: 左レーザー⇄右レーザー・左右の回転速度


def _mirror_notes_dat(dat):
    """Beat Saber の左右反転（4列）を書き出しの.datに当てた期待値。ノーツの角度 a と アークの曲がる向き m も反転する"""
    d = copy.deepcopy(_objs(dat))
    for o in d["colorNotes"]:
        o.update(x=3 - o["x"], c=1 - o["c"], d=MIR_D[o["d"]])
        if "a" in o:
            o["a"] = -o["a"]   # 角度の微調整は鏡に映すと逆回り
    for o in d["bombNotes"]:
        o["x"] = 3 - o["x"]
    for o in d["obstacles"]:
        o["x"] = 4 - o["x"] - o["w"]   # 幅のぶん左端が戻る
    for o in d["sliders"]:
        o.update(x=3 - o["x"], tx=3 - o["tx"], c=1 - o["c"], d=MIR_D[o["d"]], tc=MIR_D[o["tc"]], m={1: 2, 2: 1}.get(o["m"], o["m"]))   # 時計回り⇄反時計回り
    for o in d["burstSliders"]:
        o.update(x=3 - o["x"], tx=3 - o["tx"], c=1 - o["c"], d=MIR_D[o["d"]])
    return d


def _mirror_lights(evs):
    out = []
    for e in evs:
        e = dict(e)
        is_col = e["et"] not in (5, 8, 9, 12, 13)   # 色を持つのは color レーンだけ（BOOST・リング・回転速度の i は色ではない）
        e["et"] = MIR_ET.get(e["et"], e["et"])
        if is_col and 1 <= e["i"] <= 8:
            e["i"] = e["i"] + 4 if e["i"] <= 4 else e["i"] - 4   # 青(1〜4)⇄赤(5〜8)。0=消灯・9以上=白はそのまま
        out.append(e)
    return out


def _canon(d, drop=()):
    """並び順に依らない比較用（同じ拍の物の並びは反転で入れ替わり得る）。drop のキーは除く"""
    return {k: sorted(json.dumps({kk: vv for kk, vv in o.items() if kk not in drop}, sort_keys=True) for o in v) for k, v in d.items()}


def test_mirror_clip(t):
    '''Expertのノーツのクリップを右クリック「左右反転」→ノーツ・ボム・壁・アーク・チェーンがBeat Saberの左右反転になる→Undo／ライトのクリップは左右のレーザーと赤⇄青が入れ替わる→Undo'''
    ed = open_nle(t, "rich")
    switch_diff(ed, "Expert")
    before = export_dat(ed)["ExpertStandard.dat"]
    nc, lc = clips(ed, "n")[0], clips(ed, "l")[0]
    n0, u0 = counts(ed), _undo_n(ed)
    menu(ed, *clip_xy(ed, nc, 8), "左右反転")
    wait_until(ed, f"window._dbgApp.state().undo==={u0 + 1}", label="左右反転")
    after = _objs(export_dat(ed)["ExpertStandard.dat"])
    want = _mirror_notes_dat(before)
    t.eq(_canon(after, ("a", "m")), _canon(want, ("a", "m")), "位置（x→3−x、壁は4−x−幅）・向き・色（赤⇄青）が左右反転になる")
    t.eq(after["basicBeatmapEvents"], before["basicBeatmapEvents"], "ノーツのクリップの反転ではライトは変わらない")
    t.eq(counts(ed), n0, "数は変わらない")
    t.eq((clips(ed, "n")[0]["beat"], clips(ed, "n")[0]["len"], clips(ed, "n")[0]["n"]), (nc["beat"], nc["len"], nc["n"]), "クリップの位置・長さ・中身の数は同じ")
    a_got = sorted(o["a"] for o in after["colorNotes"] if o.get("a"))
    a_want = sorted(o["a"] for o in want["colorNotes"] if o.get("a"))
    t.ok(a_want, f"素材に角度 a のあるノーツがある: {a_want}")
    t.eq(a_got, a_want, "ノーツの角度 a が逆回りになる")
    m_got = [o["m"] for o in sorted(after["sliders"], key=lambda o: o["b"])]
    m_want = [o["m"] for o in sorted(want["sliders"], key=lambda o: o["b"])]
    t.ok(any(m in (1, 2) for m in m_want), f"素材に曲がる向き m が1か2のアークがある: {m_want}")
    t.eq(m_got, m_want, "アークの曲がる向き m（1=時計回り/2=反時計回り）が入れ替わる（0はそのまま）")
    t.eq(_canon(after), _canon(want), "角度 a・曲がる向き m も含めて、各ノーツ・アークがBeat Saberの左右反転と一致する")
    nle_mouse(ed)
    undo(ed)
    wait_until(ed, f"window._dbgApp.state().undo==={u0}", label="左右反転のUndo")
    t.eq(_objs(export_dat(ed)["ExpertStandard.dat"]), _objs(before), "Undoで書き出しが元に戻る")
    menu(ed, *clip_xy(ed, lc, 8), "左右反転")
    wait_until(ed, f"window._dbgApp.state().undo==={u0 + 1}", label="ライトのクリップの左右反転")
    t.eq(export_dat(ed)["ExpertStandard.dat"]["basicBeatmapEvents"], _mirror_lights(before["basicBeatmapEvents"]),
         "ライト: 左右のレーザー（とその回転速度）が入れ替わり、色のあるレーンは赤⇄青（消灯・白・リング・速度の値はそのまま）")
    t.eq(_objs(export_dat(ed)["ExpertStandard.dat"])["colorNotes"], before["colorNotes"], "ライトのクリップの反転ではノーツは変わらない")
    nle_mouse(ed)
    undo(ed)
    wait_until(ed, f"window._dbgApp.state().undo==={u0}", label="ライトの左右反転のUndo")
    t.eq(_objs(export_dat(ed)["ExpertStandard.dat"]), _objs(before), "Undoで書き出しが元に戻る")
    t.no_errors()


# ---- 5. パン/ズーム ----
def test_nle_zoom_pan(t):
    '''NLEのCtrl+ホイール＝マウスの拍を支点にズーム（縮小は曲の全長まで）／素のホイール＝再生位置だけ動く／Shift・Alt+ホイールは何もしない／中ボタンのドラッグ＝表示の移動（上下はレーンのスクロール）。どれも中身・書き出し・履歴は変わらない'''
    ed = open_nle(t, "rich")
    before, clips0 = export_dat(ed), clips(ed)
    w_start = _win(ed)
    t.ok(w_start["b0"] == 0 and 8 < w_start["span"] < 40, f"最初は拍0から（拍8が見えていて、全長40拍より狭い）: {w_start}")
    x8, y = scr(ed, 8)["x"], lane_y(ed, "n", 1)
    ed.wheel(x8, y, -100, ctrl=True)   # 拡大（ホイールの処理は入力を送った時点で終わっている）
    t.eq(_win(ed)["span"], round(w_start["span"] * 0.8, 3), "表示する拍数が0.8倍")
    t.ok(abs(scr(ed, 8)["x"] - x8) < 0.5, f"マウスの下の拍8はその場に留まる（{scr(ed, 8)['x']} / {x8}）")
    t.eq(ed.js("window._dbgApp.state().cur"), 0, "ズームでは再生位置は動かない")
    for _ in range(4):   # 縮小を4回（1.25倍ずつ）＝全長で頭打ち
        ed.wheel(x8, y, 100, ctrl=True)
    t.eq(_win(ed), {"b0": 0, "span": 40}, "縮小はタイムラインの全長（曲の終わり拍36＋4拍）まで")
    ed.wheel(x8, y, -100)   # 素のホイール（上）
    t.eq((ed.js("window._dbgApp.state().cur"), _win(ed)), (0.5, {"b0": 0, "span": 40}), "素のホイールは再生位置がスナップ幅（0.5拍）進むだけ")
    ed.wheel(x8, y, 100)
    t.eq(ed.js("window._dbgApp.state().cur"), 0, "逆向きで戻る")
    ed.wheel(x8, y, -100, shift=True)
    ed.wheel(x8, y, -100, alt=True)
    t.eq((ed.js("window._dbgApp.state().cur"), _win(ed)), (0, {"b0": 0, "span": 40}), "Shift・Alt+ホイールでは何も変わらない")
    for _ in range(3):
        ed.wheel(x8, y, -100, ctrl=True)
    w0 = _win(ed)
    t.eq(w0["span"], 20.48, "拡大を3回")
    ppb = scr(ed, 1)["x"] - scr(ed, 0)["x"]
    s0 = scr(ed)
    nc = clips(ed, "n")[0]
    x, yc = clip_xy(ed, nc, 8)
    ed.drag(x, yc, x - 100, yc - 40, steps=10, button="middle")   # クリップの上から中ボタンで左上へ
    w1, s1 = _win(ed), scr(ed)
    t.ok(abs(w1["b0"] - (w0["b0"] + 100 / ppb)) < 0.01, f"左へ100px引くと表示が100px分右の拍へ動く（{w1} / {w0}・{ppb:.2f}px/拍）")
    t.eq(w1["span"], w0["span"], "表示する拍数は同じ")
    dn = s0["notes"][0] - s1["notes"][0]
    t.ok(0 < dn <= 40, f"上へ引くとノーツのレーンが上へスクロールする（{dn}px）")
    t.eq(s1["lights"], s0["lights"], "ライトのレーンはスクロールしない（グループごと）")
    t.eq(nle(ed)["sel"], [], "中ボタンではクリップは選ばれない")
    my = _my(ed)
    m8 = _ms(ed, w1["b0"] + 4)["x"]
    ed.wheel(m8, my, -100, ctrl=True)   # Musicの段でも同じ表示窓がズームする
    t.eq(_win(ed)["span"], round(w1["span"] * 0.8, 3), "Musicの段のCtrl+ホイールでもNLEの表示がズームする")
    t.ok(abs(_ms(ed, w1["b0"] + 4)["x"] - m8) < 0.5, "Musicの段でもマウスの下の拍が支点")
    t.eq(clips(ed), clips0, "クリップは変わらない")
    t.eq(export_dat(ed), before, "書き出しは変わらない")
    t.eq(_undo_n(ed), 0, "履歴は積まない")
    t.ok(ed.js("window._dbgApp.dirty()")["same"], "未保存の判定も変わらない（表示の変更は未保存の判定に入らない）")
    t.no_errors()


def test_nle_follow_center(t):
    '''追従スクロール: 再生ヘッドが窓の中央を越えたら中央に留めて窓を送る＝右上のショートカット一覧の裏へ進まない
    （Ctrl+ホイールで拡大した直後＝手動の窓でも）。停止中の→でも同じで、←で戻る時は左端の余白で送る'''
    ed = open_nle(t, "basic")
    s = scr(ed, 0)
    x, y = s["x"] + 0.5, lane_y(ed, "n", 0)
    for _ in range(6):
        ed.wheel(x, y, -100, ctrl=True)   # 拍0を支点に拡大（32→約8.4拍）＝手動の窓になる
    w = ed.js("window._dbgApp.tl()")
    t.ok(w["manual"] and w["b0"] < 0.05 and 8 < w["span"] < 9, f"拡大した窓: {w}")
    span = w["span"]
    keys_left = ed.js("(r=>r.width>0?r.left:null)(document.getElementById('nodeKeys').getBoundingClientRect())")
    t.ok(keys_left is not None, "ショートカット一覧が出ている")
    head_x = lambda cur, b0: s["left"] + s["gut"] + (cur - b0) / span * (s["w"] - s["gut"])   # 再生ヘッドの画面x
    t.ok(head_x(span * 0.9, 0) > keys_left, "窓を送らなければ再生ヘッドは一覧の裏へ入る位置まで進む（この画面の大きさで試せている）")
    # 再生中の毎フレームの再生位置と窓を記録
    ed.js("""(()=>{ const L=window.__tlLog=[]; window.__tlStop=false;
      const f=()=>{ const a=window._dbgApp, st=a.state(); if(st.playing){ const w=a.tl(); L.push([st.cur,w.b0,w.manual]); }
        if(!window.__tlStop) requestAnimationFrame(f); };
      requestAnimationFrame(f); return true; })()""")
    hover_3d(ed)
    ed.key(" ")
    wait_until(ed, f"window._dbgApp.state().playing&&window._dbgApp.state().cur>{span * 1.4}", timeout=20, label="再生ヘッドが窓の幅の1.4倍まで進む")
    ed.key(" ")
    wait_until(ed, "!window._dbgApp.state().playing", label="停止")
    log = ed.js("(window.__tlStop=true, window.__tlLog)")
    t.ok(len(log) > 30, f"記録したフレーム数: {len(log)}")
    before = [b0 for cur, b0, _ in log if cur < span * 0.5 - 0.3]
    after = [(cur, b0, m) for cur, b0, m in log if cur > span * 0.5 + 0.3]
    t.ok(before and max(before) < 0.05, f"中央に来るまでは窓は動かない（左端の最大 {max(before or [0]):.3f}）")
    t.ok(after and not any(m for _, _, m in after), "中央を越えたら追従に切り替わる")
    fr = [(cur - b0) / span for cur, b0, _ in after]
    t.ok(fr and 0.45 < min(fr) and max(fr) < 0.56, f"越えた後は再生ヘッドが窓の中央に留まる（{min(fr or [0]):.3f}〜{max(fr or [0]):.3f}）")
    xs = [head_x(cur, b0) for cur, b0, _ in log]
    t.ok(max(xs) < keys_left - 2, f"再生ヘッドはショートカット一覧（x={keys_left:.0f}）より左（最大 {max(xs):.0f}）")
    # 停止中の→（tlFollow）も中央から送る／←で戻る時は左端の余白（4拍か窓の3割の小さい方）で送る
    ed.key("ArrowLeft", ctrl=True)
    wait_until(ed, "window._dbgApp.state().cur===0&&!window._dbgApp.cam().anim", label="先頭へ")
    t.eq(ed.js("window._dbgApp.tl().b0"), 0, "先頭へ飛ぶと窓も先頭")
    for _ in range(16):
        ed.key("ArrowRight")
    wait_until(ed, "window._dbgApp.state().cur===8", label="→で拍8へ")
    t.ok(abs(ed.js("window._dbgApp.tl().b0") - (8 - span * 0.5)) < 1e-9, "→で中央を越えた分だけ窓が送られる（ヘッドは中央）")
    b0, mg = ed.js("window._dbgApp.tl().b0"), min(4, span * 0.3)
    t.ok(b0 + mg < 7, f"（前提）拍7は左端の余白より右: 左端{b0:.3f}・余白{mg:.3f}")
    for _ in range(2):
        ed.key("ArrowLeft")
    wait_until(ed, "window._dbgApp.state().cur===7", label="←で拍7へ")
    t.eq(ed.js("window._dbgApp.tl().b0"), b0, "←で中央より左へ戻る間は窓は動かない")
    for _ in range(4):
        ed.key("ArrowLeft")
    wait_until(ed, "window._dbgApp.state().cur===5", label="←で拍5へ")
    t.ok(abs(ed.js("window._dbgApp.tl().b0") - (5 - mg)) < 1e-9, "左端の余白に入ると窓が戻る（ヘッドは左端から余白の位置）")
    t.no_errors()


# ---- 6. レーンの上限 ----
def test_lane_max_gutter(t):
    '''溝の右クリックでノーツ/ライトのレーンはそれぞれ10本まで足せ、11本目は「最大10本」のエラーで増えず履歴も積まない→Undoで9本に戻る'''
    ed = open_nle(t, "rich")
    before = export_dat(ed)
    _add_lanes(ed, "n", 7)
    t.eq(nle(ed)["lanes"], {"n": 10, "l": 3}, "ノーツのレーンが10本")
    u0 = _undo_n(ed)
    _show_lane(ed, "n", 0)
    menu(ed, scr(ed)["left"] + 20, lane_y(ed, "n", 0), "レーンを追加")
    ed.wait(0.1)
    t.eq(nle(ed)["lanes"]["n"], 10, "11本目は足せない")
    t.eq(take_errors(ed, "ノーツレーンは最大10本です"), 1, "最大10本のエラーが出る")
    t.eq(_undo_n(ed), u0, "足せない時は履歴を積まない")
    t.eq(clips(ed, "n")[0]["track"], 7, "既存のクリップは7段下がって一番下のまま")
    _add_lanes(ed, "l", 7)
    _show_lane(ed, "l", 0)
    menu(ed, scr(ed)["left"] + 20, lane_y(ed, "l", 0), "レーンを追加")
    ed.wait(0.1)
    t.eq(nle(ed)["lanes"], {"n": 10, "l": 10}, "ライトも10本まで")
    t.eq(take_errors(ed, "ライトレーンは最大10本です"), 1, "ライトの最大10本のエラー")
    t.eq(export_dat(ed), before, "レーンを足しても書き出しは変わらない")
    nle_mouse(ed)
    undo(ed)
    wait_until(ed, "window._dbgApp.nle().lanes.l===9", label="最後の追加のUndo")
    t.eq(nle(ed)["lanes"]["n"], 10, "ノーツのレーンはそのまま")
    t.no_errors()


def test_lane_max_auto_add(t):
    '''全レーンがロックされた拍への3D配置: 10本未満なら一番上にレーンを足してクリップを作る（Undoで戻る）／10本ある時はレーンを足さず配置しない'''
    ed = open_nle(t, "rich")
    _add_lanes(ed, "n", 6)
    _lock_all(ed, "n", 9)
    t.eq(sorted(nle(ed)["lock"]), [f"n{i}" for i in range(9)], "9本全部ロック")
    _show_lane(ed, "n", 0)
    _seek(ed, 20)   # Hardのノーツのクリップ（拍0〜16）の外
    u0 = _undo_n(ed)
    place_at(ed, 0, 0)
    wait_until(ed, "window._dbgApp.nle().clips.some(c=>c.lk==='n'&&c.beat===20&&c.n.notes===1)", label="自動で作ったクリップにノーツが入る")
    t.eq(nle(ed)["lanes"]["n"], 10, "一番上にレーンを足して10本")
    new = [c for c in clips(ed, "n") if c["beat"] == 20]
    t.eq([(c["track"], c["len"]) for c in new], [(0, 4)], "足したレーン（一番上）に拍20〜24のクリップ")
    t.eq(sorted(nle(ed)["lock"]), [f"n{i}" for i in range(1, 10)], "ロックは1段ずつ下がり、足したレーンはロックされない")
    t.eq(_undo_n(ed) - u0, 1, "配置（自動のレーン・クリップを含む）の履歴は1つ")
    # Undo: 配置と一緒に足したレーン・クリップ・ロックのずれも1回で戻る
    nle_mouse(ed)
    undo(ed)
    wait_until(ed, f"window._dbgApp.state().counts.notes===7", label="配置のUndo")
    after_undo = (nle(ed)["lanes"]["n"], len(clips(ed, "n")), sorted(nle(ed)["lock"]))
    t.eq(after_undo, (9, 1, [f"n{i}" for i in range(9)]), "Undo1回でレーン9本・ノーツのクリップ1個・ロックも元の位置に戻る")
    redo(ed)
    wait_until(ed, "window._dbgApp.state().counts.notes===8&&window._dbgApp.nle().lanes.n===10", label="配置のRedo")
    t.eq(([(c["track"], c["len"]) for c in clips(ed, "n") if c["beat"] == 20], sorted(nle(ed)["lock"])),
         ([(0, 4)], [f"n{i}" for i in range(1, 10)]), "Redoで足したレーン・クリップ・ロックのずれが再び付く")
    # 10本全部ロック→クリップの無い拍へ置いても、レーンを足さず置かない
    _lock_all(ed, "n", 10)
    _show_lane(ed, "n", 0)
    _seek(ed, 28)
    n0, u1, c0 = counts(ed)["notes"], _undo_n(ed), len(clips(ed, "n"))
    wait_until(ed, "(p=>p&&p.onScreen)(window._dbgApp.cellScreen(0,0))", timeout=5, label="マスが画面に出る")
    p = cell(ed, 0, 0)
    ed.move(p["x"], p["y"])
    ed.wait(0.15)
    ed.click(p["x"], p["y"])
    wait_until(ed, "document.getElementById('stat').textContent.includes('クリップを作れません')", label="置けない旨の表示")
    t.eq((counts(ed)["notes"], nle(ed)["lanes"]["n"], len(clips(ed, "n")), _undo_n(ed)), (n0, 10, c0, u1),
         "10本全部ロックの時はノーツもクリップもレーンも増えず、履歴も積まない")
    t.no_errors()


# ---- 7. 空きの無い所への貼り付け ----
def test_paste_no_free_lane(t):
    '''貼り付け先の拍で全レーンが埋まっている時: クリックしても貼り付けず（履歴も積まず）追従が続く→空いている拍へ動かしてクリックで貼れる→Undo／Escで取り消せる'''
    ed = open_nle(t, "rich")
    c0 = clips(ed, "n")[0]
    select(ed, c0)
    ed.key("c", ctrl=True)
    wait_until(ed, "window._dbgApp.nle().clipboard===1", label="コピー")
    for n in (2, 3):   # 拍0へ2回＝空いている Notes 2・Notes 1 へ
        ed.key("v", ctrl=True)
        wait_until(ed, "!!window._dbgApp.nle().paste", label="貼り付けの追従")
        x, y = hover(ed, 0, "n", 1)
        ed.click(x, y)
        wait_until(ed, f"window._dbgApp.nle().clips.filter(c=>c.lk==='n').length==={n}", label=f"{n - 1}回目の貼り付け")
    t.eq(sorted((c["track"], c["beat"]) for c in clips(ed, "n")), [(0, 0), (1, 0), (2, 0)], "拍0〜16は3本とも埋まる")
    before, u0 = export_dat(ed), _undo_n(ed)
    ed.key("v", ctrl=True)
    wait_until(ed, "!!window._dbgApp.nle().paste", label="3回目の貼り付けの追従")
    x, y = hover(ed, 4, "n", 1)
    ed.click(x, y)
    wait_until(ed, "document.getElementById('stat').textContent.includes('空きレーンがありません')", label="空きが無い旨の表示")
    t.eq(nle(ed)["paste"], {"at": 4, "n": 1}, "貼り付けの追従は続く")
    t.eq((len(clips(ed, "n")), _undo_n(ed)), (3, u0), "クリップは増えず履歴も積まない")
    t.eq(export_dat(ed), before, "書き出しも変わらない")
    x, y = hover(ed, 16, "n", 1)   # 拍16〜32はどのレーンも空いている
    ed.click(x, y)
    wait_until(ed, "window._dbgApp.nle().clips.filter(c=>c.lk==='n').length===4", label="空いている拍への貼り付け")
    t.eq(nle(ed)["paste"], None, "貼れたら追従は終わる")
    b = [c for c in clips(ed, "n") if c["beat"] == 16]
    t.eq([(c["track"], c["len"], c["n"]) for c in b], [(0, 16, c0["n"])], "元と同じレーン（Notes 3）の拍16に同じ中身で貼られる")
    t.eq(_undo_n(ed) - u0, 1, "貼り付けの履歴は1つ")
    nle_mouse(ed)
    undo(ed)
    wait_until(ed, "window._dbgApp.nle().clips.filter(c=>c.lk==='n').length===3", label="貼り付けのUndo")
    ed.key("v", ctrl=True)
    wait_until(ed, "!!window._dbgApp.nle().paste", label="4回目の貼り付けの追従")
    x, y = hover(ed, 8, "n", 1)
    ed.click(x, y)
    wait_until(ed, "document.getElementById('stat').textContent.includes('空きレーンがありません')", label="空きが無い旨の表示（2回目）")
    ed.key("Escape")
    wait_until(ed, "window._dbgApp.nle().paste===null", label="Escで取り消し")
    t.eq(len(clips(ed, "n")), 3, "取り消すとクリップは増えない")
    t.eq(export_dat(ed), before, "書き出しは元のまま")
    t.no_errors()

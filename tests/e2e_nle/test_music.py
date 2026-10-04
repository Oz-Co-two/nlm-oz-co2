"""NLEのMusic（曲）のクリップ: 選んでCで分割・Ctrl+Gで結合・Xで一部を削除・ドラッグで移動・右クリックで曲の長さのクリップを作る。
素材 basic は BPM120・音源16秒（=32拍）・テンポパート無し"""
from e2e_helpers import wait_until
from nle_helpers import open_nle, clips, menu, nle, nle_mouse, undo, redo


def _ms(ed, beat):
    return ed.js(f"window._dbgApp.musicScreen({beat})")


def _my(ed):
    m = _ms(ed, 0)
    return m["top"] + m["h"] * 0.6


def _music(ed):
    return nle(ed)["music"]


def _hover_music(ed, beat):
    ed.move(_ms(ed, beat)["x"], _my(ed))
    wait_until(ed, f"Math.abs((window._dbgApp.nle().hover??-99)-{beat})<1e-6", label=f"Musicの拍{beat}にマウス")


def _cut_at(ed, beat):
    ed.click(_ms(ed, 2)["x"], _my(ed))
    wait_until(ed, "window._dbgApp.nle().music.sel.length===1", label="Musicの選択")
    _hover_music(ed, beat)
    ed.key("c")
    wait_until(ed, "(window._dbgApp.nle().music.segs||[]).length===2", label="MusicのCで分割")


def test_music_cut_and_merge(t):
    '''Musicを選んで拍8でC→2つに分かれる（後ろは音源の4秒目から）→2つ選んでCtrl+Gで1本に戻る→Undo/Redo'''
    ed = open_nle(t, "basic")
    m0 = _music(ed)
    t.eq((m0["audio"], m0["segs"], m0["dur"]), (True, None, 16), "最初は分割なしの1本（16秒）")
    clips0 = clips(ed)
    _cut_at(ed, 8)
    a, b = _music(ed)["segs"]
    t.eq((a["beat"], a["off"], a["dur"]), (0, 0, 4), "前側: 拍0から音源の0〜4秒")
    t.eq((b["beat"], b["off"], b["dur"]), (8, 4, 12), "後ろ側: 拍8から音源の4秒目以降")
    t.eq(clips(ed), clips0, "ノーツ・ライトのクリップは切れない")
    t.eq(ed.js("window._dbgApp.audioPosAtBeat(10)"), 5, "拍10の音源の位置（秒）は分割前と同じ")
    ed.click(_ms(ed, 2)["x"], _my(ed))
    ed.click(_ms(ed, 12)["x"], _my(ed), shift=True)
    wait_until(ed, "window._dbgApp.nle().music.sel.length===2", label="Shift+クリックで2つ選ぶ")
    ed.key("g", ctrl=True)
    wait_until(ed, "window._dbgApp.nle().music.segs===null", label="Ctrl+Gで結合")
    t.eq(_music(ed)["beat"], 0, "1本に戻り拍0から")
    nle_mouse(ed)
    undo(ed)
    wait_until(ed, "(window._dbgApp.nle().music.segs||[]).length===2", label="結合のUndo")
    # 選択の変化（クリック・Shift+クリック）も1動作として履歴に入る＝あと3回（選択2回＋分割）で分割前に戻る
    for _ in range(3):
        undo(ed)
    wait_until(ed, "window._dbgApp.nle().music.segs===null", timeout=3, label="分割のUndo")
    redo(ed)
    wait_until(ed, "(window._dbgApp.nle().music.segs||[]).length===2", label="分割のRedo")
    t.no_errors()


def test_music_merge_needs_continuity(t):
    '''Musicの結合は時間も音源も続いている時だけ: 間を詰めずに離した2つは結合しない'''
    ed = open_nle(t, "basic")
    _cut_at(ed, 8)
    # 後ろ側を拍12へドラッグ（間が4拍空く）
    ed.click(_ms(ed, 12)["x"], _my(ed))
    wait_until(ed, "window._dbgApp.nle().music.sel.length===1", label="後ろ側の選択")
    ed.drag(_ms(ed, 12)["x"], _my(ed), _ms(ed, 16)["x"], _my(ed), steps=10)
    wait_until(ed, "window._dbgApp.nle().music.segs[1].beat===12", label="後ろ側を拍12へ")
    ed.click(_ms(ed, 2)["x"], _my(ed))
    ed.click(_ms(ed, 14)["x"], _my(ed), shift=True)
    wait_until(ed, "window._dbgApp.nle().music.sel.length===2", label="2つ選ぶ")
    ed.key("g", ctrl=True)
    ed.wait(0.2)
    t.eq(len(_music(ed)["segs"]), 2, "離れたものは結合しない")
    t.eq(ed.js("window._dbgApp.audioPosAtBeat(10)"), None, "隙間（拍8〜12）には音源が無い")
    t.eq(ed.js("window._dbgApp.audioPosAtBeat(12)"), 4, "拍12から後ろ側（音源の4秒目）が鳴る")
    t.no_errors()


def test_music_delete_segment(t):
    '''分けたMusicの後ろ側を選んでXで消す（余韻を切る）→前側だけ残る→Undoで戻る'''
    ed = open_nle(t, "basic")
    _cut_at(ed, 24)
    ed.click(_ms(ed, 28)["x"], _my(ed))
    wait_until(ed, "window._dbgApp.nle().music.sel.length===1&&window._dbgApp.nle().music.sel[0]===1", label="後ろ側の選択")
    ed.key("x")
    wait_until(ed, "(window._dbgApp.nle().music.segs||[]).length===1", label="Xで削除")
    s = _music(ed)["segs"][0]
    t.eq((s["beat"], s["off"], s["dur"]), (0, 0, 12), "前側（音源の0〜12秒）だけ残る")
    t.eq(_music(ed)["audio"], True, "音源そのものは残る")
    nle_mouse(ed)
    undo(ed)
    wait_until(ed, "(window._dbgApp.nle().music.segs||[]).length===2", label="削除のUndo")
    t.no_errors()


def test_music_drag_move(t):
    '''Musicのクリップをドラッグして拍4へ→拍4が音源の0秒になる・ノーツのクリップは動かない→Undo'''
    ed = open_nle(t, "basic")
    clips0 = clips(ed)
    ed.drag(_ms(ed, 10)["x"], _my(ed), _ms(ed, 14)["x"], _my(ed), steps=10)
    wait_until(ed, "window._dbgApp.nle().music.beat===4", label="Musicの移動")
    t.eq(ed.js("window._dbgApp.audioPosAtBeat(4)"), 0, "拍4が音源の先頭")
    t.eq(ed.js("window._dbgApp.audioPosAtBeat(2)"), None, "拍4より前には音源が無い")
    t.eq(clips(ed), clips0, "ノーツのクリップは動かない")
    nle_mouse(ed)
    undo(ed)
    wait_until(ed, "window._dbgApp.nle().music.beat===0", label="移動のUndo")
    t.no_errors()


def test_full_song_clips(t):
    '''Musicの右クリック「曲の幅のノーツ＆ライトクリップを作成」→曲の長さ（32拍）のノーツ/ライトのクリップを空いている一番下のレーンへ→Undo'''
    ed = open_nle(t, "basic")
    menu(ed, _ms(ed, 10)["x"], _my(ed), "曲の幅のノーツ＆ライトクリップを作成")
    wait_until(ed, "window._dbgApp.nle().clips.length===3", label="クリップの作成")
    new = [c for c in clips(ed) if c["label"] == "Sheet" and c["len"] == 32]
    t.eq(sorted((c["lk"], c["beat"], c["len"]) for c in new), [("l", 0, 32), ("n", 0, 32)], "曲の長さ（16秒=32拍）のクリップが2つ")
    t.eq({c["lk"]: c["track"] for c in new}, {"n": 1, "l": 2}, "空いている一番下のレーン（ノーツはNotes 1が埋まっているのでNotes 2）")
    t.eq(sorted(nle(ed)["sel"]), sorted(c["id"] for c in new), "作ったクリップが選ばれる")
    nle_mouse(ed)
    undo(ed)
    wait_until(ed, "window._dbgApp.nle().clips.length===1", label="作成のUndo")
    t.no_errors()

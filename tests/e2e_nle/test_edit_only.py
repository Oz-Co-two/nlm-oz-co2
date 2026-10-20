"""単独編集（英語 Edit only・2026-10-19）: ノーツのレーンを1つだけ編集できるようにする。
仕様（2026-10-19 に利用者と合意）: 各ノーツのレーンの左の溝の2段目にスイッチ（1つだけオン・押し直すと全部オフ）。ライトのレーンには無い。
オンの間は3Dの配置・貼り付けはそのレーンだけに入り（クリップが無ければそのレーンに新しいクリップ）、他のレーンは見えるが選択・移動・削除できない。
他のレーンのノーツを1つクリックすると3Dの上に小さな帯（［そのレーンを単独編集にする］［単独編集をオフ］［そのまま］）が出てクリック自体は何もしない。
範囲選択では帯を出さず黙って外し、数を3Dの隅に出す。重なっている時は単独編集のレーンを優先して拾う。3Dの隅に「✎ 単独編集: Notes n」。
NLEで他のレーンのクリップを選んでいても行き先は単独編集のレーン。ロック中のレーンを単独編集にするとロックが外れる。ミュート中のレーンには置かず知らせる。
E キー（NLE の上）でマウスの下のノーツのレーンを入/切。プロジェクトに保存するが、切り替えただけでは未保存にしない（view と同じ）。
レーンの増減ではロックと同じく同じレーンに付いたまま動く"""
import json

from e2e_helpers import wait_until, counts, cell, dirty, hover_3d, place_at
from nle_helpers import (open_nle, clips, hover, menu, nle, nle_mouse, scr, lane_y, select, take_errors, hover_canvas)

_CLICK = ("note", "bomb")


def _band_rect(ed, track):
    """ノーツのレーン track の溝の2段目の単独編集の帯の押せる所（画面の座標。表示窓の外に隠れていれば None）"""
    return next((b for b in scr(ed)["eo"] if b["t"] == track), None)


def _switch_xy(ed, track):
    """ノーツのレーン track の溝の2段目の帯のスイッチのあたり（帯の左端+5・幅22 のスライダー型）"""
    b = _band_rect(ed, track)
    assert b, f"段{track}の単独編集の帯が見えていません"
    return b["x"] + 14, b["y"] + b["h"] / 2


def _eo(ed):
    return nle(ed)["editOnly"]


def _set(ed, track):
    """スイッチを押して単独編集をそのレーンへ（オンのレーンを押すと全部オフ）"""
    before = _eo(ed)
    ed.click(*_switch_xy(ed, track))
    want = None if before == track else track
    wait_until(ed, f"window._dbgApp.nle().editOnly==={json.dumps(want)}", label=f"Notes の段{track}のスイッチ")


def _band(ed):
    return ed.js("""(e=>({on:e.classList.contains('on'),msg:e.querySelector('.eoMsg').textContent,
      btns:[...e.querySelectorAll('button')].map(b=>b.textContent)}))(document.getElementById('eoBand'))""")


def _ind(ed):
    """3Dの隅の表示（出ていなければ None）と、添えている短い知らせ"""
    return ed.js("""(e=>e.classList.contains('on')?{main:e.querySelector('.eoIndMain').textContent,
      note:e.querySelector('.eoIndNote').textContent}:null)(document.getElementById('eoInd'))""")


def _band_btn(ed, cls):
    p = ed.js(f"(r=>({{x:r.left+r.width/2,y:r.top+r.height/2}}))(document.querySelector('#eoBand .{cls}').getBoundingClientRect())")
    ed.move(p["x"], p["y"]); ed.wait(0.05)
    ed.click(p["x"], p["y"])


def _objs(ed):
    return ed.js("window._dbgApp.objScreen()")


def _note_on(ed, tr):
    """レーン tr のノーツのうち画面の一番下（手前＝帯に重ならない所）にあるもの"""
    os_ = [o for o in _objs(ed) if o["kind"] == "note" and o["inView"] and o["tr"] == tr]
    assert os_, f"段{tr}のノーツが画面にありません"
    return max(os_, key=lambda o: o["sy"])


def _cam_edit(ed):
    """カメラ固定モード（クリック=選択・空きのドラッグ=範囲選択）へ。切り替えるとカメラが動くので、ノーツの画面の位置が止まるまで待つ"""
    hover_canvas(ed); ed.key("q")
    wait_until(ed, "window._dbgApp.state().camMode==='edit'", label="カメラ固定モード")
    pos = "JSON.stringify(window._dbgApp.objScreen().map(o=>[Math.round(o.sx),Math.round(o.sy)]))"
    prev = None
    for _ in range(40):
        cur = ed.js(pos)
        if cur == prev:
            return
        prev = cur
        ed.wait(0.15)


def _click(ed, o):
    ed.move(o["sx"], o["sy"]); ed.wait(0.1)
    ed.click(o["sx"], o["sy"]); ed.wait(0.15)


NOTES_JS = "window._dbgApp.notes().notes.map(n=>[n.beat,n.x,n.y,n.c,n.d,n._tr])"


def _copy_clip_to_notes2(ed):
    """Notes 3 のクリップをコピーして拍0の Notes 2 へ貼る（同じ所に同じ物が重なる＝重なりの優先の確かめ用）"""
    c0 = clips(ed, "n")[0]
    select(ed, c0)
    ed.key("c", ctrl=True)
    wait_until(ed, "window._dbgApp.nle().clipboard===1", label="クリップのコピー")
    ed.key("v", ctrl=True)
    wait_until(ed, "!!window._dbgApp.nle().paste", label="貼り付けの追従")
    x, y = hover(ed, 0, "n", 1)
    ed.click(x, y)
    wait_until(ed, "window._dbgApp.nle().clips.filter(c=>c.lk==='n').length===2", label="Notes 2 へ貼り付け")
    t1 = [c for c in clips(ed, "n") if c["track"] == 1]
    assert t1 and t1[0]["beat"] == 0, f"Notes 2 の拍0に貼られていません: {clips(ed, 'n')}"
    nle_mouse(ed); ed.key("a")   # クリップの選択を外す
    wait_until(ed, "window._dbgApp.nle().sel.length===0", label="クリップの選択解除")


def test_edit_only_switch_exclusive(t):
    '''溝のスイッチ: 押すとそのレーンだけオン（別のレーンを押すと移る＝1つだけ）・オンを押し直すと全部オフ・隅に「✎ 単独編集: Notes n」・ツールチップ・ライトのレーンには無い・LIGHTINGでは隅の表示を出さない'''
    ed = open_nle(t, "rich")
    t.eq((_eo(ed), _ind(ed)), (None, None), "最初はオフ・隅の表示なし")
    _set(ed, 1)
    t.eq(_ind(ed), {"main": "✎ 単独編集: Notes 2", "note": ""}, "隅の表示")
    x, y = _switch_xy(ed, 1)
    ed.move(x + 20, y); ed.wait(0.15)
    t.eq(ed.js("document.getElementById('ndcv').title"),
         "このレーンだけを編集 — 3Dの編集はこのレーンだけに入ります。他のレーンは編集できません", "スイッチのツールチップ")
    ed.move(x + 200, y); ed.wait(0.15)
    t.eq(ed.js("document.getElementById('ndcv').title"), "", "スイッチから外れるとツールチップは消える")
    _set(ed, 0)
    t.eq((_eo(ed), _ind(ed)["main"]), (0, "✎ 単独編集: Notes 3"), "別のレーンを押すとそちらへ移る（1つだけ）")
    _set(ed, 0)
    t.eq((_eo(ed), _ind(ed)), (None, None), "オンのレーンを押し直すと全部オフ・隅の表示も消える")
    # ライトのレーンの溝の同じ位置（2段目）を押しても何も変わらない（L/S/M も押されない）
    s = scr(ed)
    st0 = {k: nle(ed)[k] for k in ("lock", "solo", "mute", "editOnly")}
    ed.click(s["left"] + 17, s["lights"][1] + 26); ed.wait(0.2)
    t.eq({k: nle(ed)[k] for k in ("lock", "solo", "mute", "editOnly")}, st0, "ライトのレーンにはスイッチが無い")
    # LIGHTING では隅の表示を出さない（ライトには効かないため）・NOTES へ戻すと出る
    _set(ed, 1)
    hover_canvas(ed); ed.key("Tab")
    wait_until(ed, "window._dbgApp.state().lightMode", label="LIGHTING")
    wait_until(ed, "!document.getElementById('eoInd').classList.contains('on')", label="LIGHTINGでは隅の表示を出さない")
    hover_canvas(ed); ed.key("Tab")
    wait_until(ed, "!window._dbgApp.state().lightMode", label="NOTES")
    wait_until(ed, "document.getElementById('eoInd').classList.contains('on')", label="NOTESへ戻すと隅の表示が出る")
    t.eq(_eo(ed), 1, "LIGHTINGを行き来しても単独編集はそのまま")
    t.no_errors()


def test_edit_only_band_hit_area(t):
    '''溝の単独編集の帯（2026-10-20・文字を大きく・帯でひとまとめ。同日「詰まって見えて字が読みづらい」で高さと余白を足した）: 帯はレーンの上端+21・高さ20
    （1段目＝L/S/M の下端+17 との間 4px・帯の下も 4px＝ノーツのレーンの最低の高さ 45px。ライトのレーンは 34px のまま）・
    帯全体が押せる（左端・文字の無い右端・上下の端）・帯のすぐ外（右・1段目との間）は押せない・
    帯の上は指のカーソルとツールチップ・スクロールで隠れた帯は押せず（その位置はライトのレーン）、半分見えている帯は見えている所だけ押せる'''
    ed = open_nle(t, "rich")
    s = scr(ed)
    b = _band_rect(ed, 1)
    off = b["y"] - s["notes"][1]   # 帯のレーンの上端からの位置
    t.eq((b["x"] - s["left"], b["w"], b["h"], off), (13, 109, 20, 21),
         "帯はレーンの上端+21・高さ20、溝の左端+13（左のスクロールバーの右）から M ボタンの右端まで（幅109）")
    t.eq((s["laneH"], s["laneHL"]), (45, 34), "既定の画面（1600×980）・ノーツ3本・ライト3本: ノーツのレーンは最低の 45px（帯の下に 4px）・ライトは 34px のまま")
    t.eq(s["notes"][2] - s["notes"][1] - off - b["h"], 4, "帯の下端から次のレーンの上端まで 4px")
    cy = b["y"] + b["h"] / 2
    for x, y, want, what in ((b["x"] + b["w"] - 2, cy, 1, "右端（文字の無い所）"), (b["x"] + 1, b["y"] + 1, None, "左上の端"),
                             (b["x"] + b["w"] / 2, b["y"] + b["h"] - 1, 1, "下の端")):
        ed.click(x, y)
        wait_until(ed, f"window._dbgApp.nle().editOnly==={json.dumps(want)}", label=f"帯の{what}を押す")
    # 帯のすぐ外: 右（溝の中）・1段目（名前）との間は何もしない（L/S/M も押されない）
    st0 = {k: nle(ed)[k] for k in ("lock", "solo", "mute", "editOnly")}
    for x, y in ((b["x"] + b["w"] + 3, cy), (b["x"] + 30, b["y"] - 2)):
        ed.click(x, y); ed.wait(0.2)
    t.eq({k: nle(ed)[k] for k in ("lock", "solo", "mute", "editOnly")}, st0, "帯の外を押しても変わらない")
    # 指のカーソルとツールチップ（帯の右端の文字の無い所でも）
    ed.move(b["x"] + b["w"] - 3, cy)
    wait_until(ed, "document.getElementById('ndcv').style.cursor==='pointer'", label="帯の上は指のカーソル")
    t.eq(ed.js("document.getElementById('ndcv').title"),
         "このレーンだけを編集 — 3Dの編集はこのレーンだけに入ります。他のレーンは編集できません", "帯の右端でもツールチップ")
    ed.move(b["x"] + 30, b["y"] - 2)
    wait_until(ed, "document.getElementById('ndcv').style.cursor===''", label="帯から外れると普通のカーソル")
    # 既定の画面では一番下の Notes 1（段2）の帯はノーツの表示窓の下に隠れている＝押せない（同じ位置はライトのレーン）
    vp = nle(ed)["vp"]["n"]
    y2 = s["notes"][2] + off   # Notes 1 の帯の上端（スクロールしていない時）
    t.eq(_band_rect(ed, 2), None, "隠れている帯は押せる所に無い")
    t.ok(y2 >= vp[1], f"Notes 1 の帯の位置は表示窓の外（{y2} ≥ {vp[1]}）")
    ed.click(b["x"] + 14, y2 + b["h"] / 2); ed.wait(0.2)
    t.eq({k: nle(ed)[k] for k in ("lock", "solo", "mute", "editOnly")}, st0, "隠れた帯の位置を押しても変わらない（Notes 2 のまま）")
    # 中ドラッグでノーツのレーンを下へ: Notes 1 の帯が半分見える（帯の真ん中が表示窓の下端）＝見えている所だけ押せる
    x0, y0 = s["x"] + 40, s["notes"][0] + 20
    ed.drag(x0, y0, x0, y0 - round(y2 + b["h"] / 2 - vp[1]), steps=4, button="middle")
    wait_until(ed, f"(e=>!!e&&e.h<{b['h']})(window._dbgApp.nleScreen(0).eo.find(b=>b.t===2))", label="Notes 1 の帯が半分見える")
    h = _band_rect(ed, 2)
    vp = nle(ed)["vp"]["n"]
    t.ok(4 <= h["h"] < b["h"] and abs(h["y"] + h["h"] - vp[1]) < 0.6, f"押せる所は表示窓の中だけ: {h} 窓の下端 {vp[1]}")
    ed.click(h["x"] + h["w"] - 4, h["y"] + h["h"] / 2)
    wait_until(ed, "window._dbgApp.nle().editOnly===2", label="半分見えている帯の見えている所を押す")
    t.no_errors()


def test_edit_only_e_key(t):
    '''E キー（NLE の上）: マウスの下のノーツのレーンの単独編集を入/切・別のレーンで押すと移る・ライトのレーンの上では何もしない・Ctrl+E はマーカー挿入のまま'''
    ed = open_nle(t, "rich")
    hover(ed, 20, "n", 1); ed.key("e")
    wait_until(ed, "window._dbgApp.nle().editOnly===1", label="Notes 2 の上で E")
    hover(ed, 20, "n", 0); ed.key("e")
    wait_until(ed, "window._dbgApp.nle().editOnly===0", label="Notes 3 の上で E＝移る")
    ed.key("e")
    wait_until(ed, "window._dbgApp.nle().editOnly===null", label="同じレーンでもう一度 E＝オフ")
    hover(ed, 20, "l", 1); ed.key("e"); ed.wait(0.2)
    t.eq(_eo(ed), None, "ライトのレーンの上の E は何もしない")
    m0 = len(nle(ed)["markers"])
    hover(ed, 20, "n", 1); ed.key("e", ctrl=True)
    wait_until(ed, f"window._dbgApp.nle().markers.length==={m0 + 1}", label="Ctrl+E はマーカー挿入")
    t.eq(_eo(ed), None, "Ctrl+E では単独編集は変わらない")
    t.no_errors()


def test_edit_only_place_goes_to_lane(t):
    '''オンの間の3Dの配置は単独編集のレーンだけに入る（クリップが無い所はそのレーンに新しいクリップ・Undo1回で戻る）・NLEで他のレーンのクリップを選んでいても単独編集のレーンへ'''
    ed = open_nle(t, "rich")
    c3 = clips(ed, "n")[0]
    t.eq((c3["track"], c3["beat"], c3["len"]), (0, 0, 16), "素材: Notes 3 の拍0〜16にクリップ（今の振り分けならここへ入る）")
    _set(ed, 1)
    u0 = ed.js("window._dbgApp.state().undo")
    place_at(ed, 0, 0)
    notes = ed.js(NOTES_JS)
    new = [n for n in notes if n[0] == 0 and n[1] == 0 and n[2] == 0]
    t.eq([n[5] for n in new], [1], "置いたノーツは Notes 2（段1）に入る")
    t.eq([(c["track"], c["beat"], c["len"], c["n"]["notes"]) for c in clips(ed, "n")], [(0, 0, 16, 7), (1, 0, 4, 1)],
         "Notes 2 に拍0〜4の新しいクリップ・Notes 3 のクリップの中身は変わらない")
    t.eq(ed.js("window._dbgApp.state().undo") - u0, 1, "履歴は1つ")
    hover_3d(ed); ed.key("z", ctrl=True)
    wait_until(ed, "window._dbgApp.state().counts.notes===7", label="配置のUndo")
    t.eq([(c["track"], c["beat"]) for c in clips(ed, "n")], [(0, 0)], "Undo1回で作ったクリップも消える")
    # NLE で他のレーン（Notes 3）のクリップを選んでいても、行き先は単独編集のレーン
    place_at(ed, 0, 0)
    select(ed, clips(ed, "n")[0])
    t.eq(nle(ed)["sel"], [c3["id"]], "Notes 3 のクリップを選んだ")
    place_at(ed, 3, 2)
    new2 = [n for n in ed.js(NOTES_JS) if n[0] == 0 and n[1] == 3 and n[2] == 2]
    t.eq([n[5] for n in new2], [1], "選んだクリップではなく Notes 2 へ入る")
    t.eq(nle(ed)["sel"], [c3["id"]], "置いた後も Notes 3 のクリップは選ばれたまま（選んだ状態で置いた）")
    wait_until(ed, "window._dbgApp.nle().clips.some(c=>c.track===1&&c.n.notes===2)", label="クリップの中身へ反映（次の描画）")
    t.eq(sorted((c["track"], c["beat"], c["len"], c["n"]["notes"]) for c in clips(ed, "n")), [(0, 0, 16, 7), (1, 0, 4, 2)],
         "Notes 2 の同じクリップに2個目が入る")
    t.no_errors()


def test_edit_only_click_other_lane_band(t):
    '''他のレーンのノーツをクリック→3Dの上に帯が出て、中身・選択・履歴は変わらない（配置モード・カメラ固定モード・右クリックの削除も）／［そのまま］で閉じる／［Notes 3 を単独編集にする］で移る／［単独編集をオフ］／少しで消える'''
    ed = open_nle(t, "rich")
    _set(ed, 1)
    notes0, u0 = ed.js(NOTES_JS), ed.js("window._dbgApp.state().undo")
    o = _note_on(ed, 0)
    _click(ed, o)
    wait_until(ed, "document.getElementById('eoBand').classList.contains('on')", label="帯が出る")
    t.eq(_band(ed), {"on": True, "msg": "このノーツは Notes 3 にあります（単独編集: Notes 2）",
                     "btns": ["Notes 3 を単独編集にする", "単独編集をオフ", "そのまま"]}, "帯の文言とボタン")
    t.eq((ed.js(NOTES_JS), ed.js("window._dbgApp.state().sel"), ed.js("window._dbgApp.state().undo")), (notes0, 0, u0),
         "クリック自体は何もしない（中身・選択・履歴）")
    _band_btn(ed, "eoKeep")
    wait_until(ed, "!document.getElementById('eoBand').classList.contains('on')", label="［そのまま］で閉じる")
    t.eq(_eo(ed), 1, "［そのまま］では単独編集は変わらない")
    # 右クリック（配置モードの削除）も消さずに帯
    ed.click(o["sx"], o["sy"], button="right"); ed.wait(0.2)
    wait_until(ed, "document.getElementById('eoBand').classList.contains('on')", label="右クリックでも帯")
    t.eq((ed.js(NOTES_JS), ed.js("window._dbgApp.state().undo")), (notes0, u0), "他のレーンのノーツは右クリックで消えない")
    # カメラ固定モード（クリック=選択）でも同じ
    _cam_edit(ed)
    o = _note_on(ed, 0)
    _click(ed, o)
    t.eq((ed.js("window._dbgApp.state().sel"), _band(ed)["on"]), (0, True), "カメラ固定モードでも選ばれず帯が出る")
    _band_btn(ed, "eoSw")
    wait_until(ed, "window._dbgApp.nle().editOnly===0", label="［Notes 3 を単独編集にする］")
    t.eq((_band(ed)["on"], _ind(ed)["main"]), (False, "✎ 単独編集: Notes 3"), "帯は閉じ、隅の表示も Notes 3 に")
    _click(ed, _note_on(ed, 0))
    wait_until(ed, "window._dbgApp.state().sel===1", label="単独編集のレーンのノーツは選べる")
    # ［単独編集をオフ］
    _set(ed, 1)
    t.eq(ed.js("window._dbgApp.state().sel"), 0, "単独編集を移すと他のレーンになった物の選択は外れる")
    _click(ed, _note_on(ed, 0))
    wait_until(ed, "document.getElementById('eoBand').classList.contains('on')", label="もう一度帯")
    _band_btn(ed, "eoOff")
    wait_until(ed, "window._dbgApp.nle().editOnly===null", label="［単独編集をオフ］")
    t.eq((_band(ed)["on"], _ind(ed)), (False, None), "帯も隅の表示も消える")
    _click(ed, _note_on(ed, 0))
    wait_until(ed, "window._dbgApp.state().sel===1", label="オフにすると今までどおり選べる")
    # 帯は少しで消える（マウスが帯の上に無ければ約6秒）
    _set(ed, 1)
    _click(ed, _note_on(ed, 0))
    wait_until(ed, "document.getElementById('eoBand').classList.contains('on')", label="帯")
    wait_until(ed, "!document.getElementById('eoBand').classList.contains('on')", timeout=10, label="帯が自然に消える")
    t.no_errors()


def test_edit_only_brush_on_other_lane_cell(t):
    '''配置のブラシで他のレーンのノーツがあるマスをクリック→書き換えずに帯（向き・色・レーンは変わらない）'''
    ed = open_nle(t, "rich")
    _set(ed, 1)
    s = scr(ed, 2)
    ed.click(s["x"], (s["ruler"] + s["tempo"]) / 2)   # 再生位置を拍2（Notes 3 のノーツ (1,0) がある拍）へ
    wait_until(ed, "window._dbgApp.state().cur===2", label="再生位置を拍2へ")
    notes0, n0 = ed.js(NOTES_JS), counts(ed)["notes"]
    wait_until(ed, "(p=>p&&p.onScreen)(window._dbgApp.cellScreen(1,0))", timeout=5, label="マスが画面に出る")
    p = cell(ed, 1, 0)
    ed.move(p["x"], p["y"]); ed.wait(0.15)
    ed.click(p["x"], p["y"]); ed.wait(0.2)
    wait_until(ed, "document.getElementById('eoBand').classList.contains('on')", label="帯が出る")
    t.eq((ed.js(NOTES_JS), counts(ed)["notes"]), (notes0, n0), "他のレーンのノーツは書き換えず、重ねても置かない")
    t.eq(_band(ed)["msg"], "このノーツは Notes 3 にあります（単独編集: Notes 2）", "帯の文言")
    t.no_errors()


def test_edit_only_overlap_and_box_select(t):
    '''重なっている時は単独編集のレーンを優先して拾う（帯は出ない）／範囲選択は帯を出さず他のレーンの物を黙って外し、隅に「他のレーンの n 個は対象外」'''
    ed = open_nle(t, "rich")
    _copy_clip_to_notes2(ed)
    _set(ed, 1)
    _cam_edit(ed)
    o = _note_on(ed, 1)
    _click(ed, o)
    wait_until(ed, "window._dbgApp.state().sel===1", label="重なっているノーツをクリック")
    sel = [x for x in _objs(ed) if x["sel"]]
    t.eq([(x["kind"], x["tr"]) for x in sel], [("note", 1)], "単独編集のレーン（Notes 2）の方が選ばれる")
    t.eq(_band(ed)["on"], False, "重なりで拾えた時は帯を出さない")
    ed.key("a")
    wait_until(ed, "window._dbgApp.state().sel===0", label="選択解除")
    # 範囲選択（Shift+ドラッグ）で3Dの見えている物を全部囲む
    vis = [x for x in _objs(ed) if x["inView"]]
    own = [x for x in vis if x["tr"] == 1]
    other = [x for x in vis if x["tr"] != 1]
    t.ok(len(own) > 0 and len(other) > 0, f"両方のレーンの物が見えている（{len(own)}・{len(other)}）")
    r = ed.js("(r=>({x:r.left,y:r.top,w:r.width,h:r.height}))(document.getElementById('cv').getBoundingClientRect())")
    x0, y0 = r["x"] + r["w"] * 0.3, r["y"] + 4
    x1 = max(x["sx"] for x in vis) + 30
    y1 = max(x["sy"] for x in vis) + 30
    ed.drag(x0, y0, x1, y1, steps=10, shift=True)
    wait_until(ed, "window._dbgApp.state().sel>0", label="範囲選択")
    sel = [x for x in _objs(ed) if x["sel"]]
    t.ok(sel and all(x["tr"] == 1 for x in sel), f"選ばれたのは単独編集のレーンの物だけ: {[(x['kind'], x['tr']) for x in sel]}")
    boxed_other = [x for x in other if x0 <= x["sx"] <= x1 and y0 <= x["sy"] <= y1]
    t.eq(_band(ed)["on"], False, "範囲選択では帯を出さない")
    t.eq(_ind(ed), {"main": "✎ 単独編集: Notes 2", "note": f"他のレーンの {len(boxed_other)} 個は対象外"}, "隅に対象外の数")
    wait_until(ed, "document.getElementById('eoInd').querySelector('.eoIndNote').textContent===''", timeout=8, label="対象外の数は少しで消える")
    t.no_errors()


def test_edit_only_muted_lane_refuses(t):
    '''単独編集のレーンがミュート中なら3Dの配置・壁・貼り付けをせず知らせる（中身・クリップ・履歴は変わらない）'''
    ed = open_nle(t, "rich")
    o = _note_on(ed, 0)
    _click(ed, o)   # 配置モード: 置いてある物のクリック＝選択
    wait_until(ed, "window._dbgApp.state().sel===1", label="ノーツを選ぶ")
    hover_3d(ed); ed.key("c", ctrl=True)   # 3D のコピー（後で貼る）
    _set(ed, 1)
    hover(ed, 20, "n", 1); ed.key("m")
    wait_until(ed, "window._dbgApp.nle().mute.includes('n1')", label="Notes 2 をミュート")
    before = (ed.js(NOTES_JS), clips(ed, "n"), ed.js("window._dbgApp.state().undo"))
    wait_until(ed, "(p=>p&&p.onScreen)(window._dbgApp.cellScreen(0,0))", timeout=5, label="マスが画面に出る")
    p = cell(ed, 0, 0)
    ed.move(p["x"], p["y"]); ed.wait(0.15)
    ed.click(p["x"], p["y"]); ed.wait(0.3)
    t.eq(take_errors(ed, "単独編集の Notes 2 はミュート中のため置けません"), 1, "置けない旨の知らせ（ノーツ）")
    hover_3d(ed); ed.key("v", ctrl=True); ed.wait(0.3)
    t.eq(take_errors(ed, "単独編集の Notes 2 はミュート中のため置けません"), 1, "置けない旨の知らせ（貼り付け）")
    t.eq((ed.js(NOTES_JS), clips(ed, "n"), ed.js("window._dbgApp.state().undo")), before, "ノーツ・クリップ・履歴は変わらない")
    t.eq(ed.js("window._dbgApp.edit().pasteFollow"), False, "貼り付けの追従も始まらない")
    # ミュートを外して他のレーン（Notes 3）をソロ＝単独編集のレーンは見えない→同じく置かない
    hover(ed, 20, "n", 1); ed.key("m")
    hover(ed, 20, "n", 0); ed.key("s")
    wait_until(ed, "window._dbgApp.nle().mute.length===0&&window._dbgApp.nle().solo.includes('n0')", label="ミュート解除・Notes 3 をソロ")
    p = cell(ed, 0, 0)
    ed.move(p["x"], p["y"]); ed.wait(0.15)
    ed.click(p["x"], p["y"]); ed.wait(0.3)
    t.eq(take_errors(ed, "単独編集の Notes 2 は他のレーンのソロで見えないため置けません"), 1, "置けない旨の知らせ（他のレーンのソロ）")
    t.eq((ed.js(NOTES_JS), clips(ed, "n")), before[:2], "ノーツ・クリップは変わらない")
    t.no_errors()


def test_edit_only_unlocks_locked_lane(t):
    '''ロック中のレーンを単独編集にするとロックが外れる（他のレーンのロックはそのまま）・その後は置ける'''
    ed = open_nle(t, "rich")
    for lk, tr in (("n", 1), ("n", 0), ("l", 0)):
        hover(ed, 20, lk, tr); ed.key("l")
    wait_until(ed, "window._dbgApp.nle().lock.length===3", label="3つロック")
    _set(ed, 1)
    t.eq(sorted(nle(ed)["lock"]), ["l0", "n0"], "単独編集にした Notes 2 のロックだけ外れる")
    place_at(ed, 0, 0)
    t.eq([n[5] for n in ed.js(NOTES_JS) if n[0] == 0 and n[1] == 0 and n[2] == 0], [1], "Notes 2 に置ける")
    # 単独編集のレーンを後からロックすると置けない（知らせる）
    hover(ed, 20, "n", 1); ed.key("l")
    wait_until(ed, "window._dbgApp.nle().lock.includes('n1')", label="Notes 2 をロック")
    t.eq(_eo(ed), 1, "ロックしても単独編集はそのまま")
    n0 = counts(ed)["notes"]
    wait_until(ed, "(p=>p&&p.onScreen)(window._dbgApp.cellScreen(3,2))", timeout=5, label="マスが画面に出る")
    p = cell(ed, 3, 2)
    ed.move(p["x"], p["y"]); ed.wait(0.15)
    ed.click(p["x"], p["y"]); ed.wait(0.3)
    t.eq(take_errors(ed, "単独編集の Notes 2 はロック中のため置けません"), 1, "ロック中の知らせ")
    t.eq(counts(ed)["notes"], n0, "置かない")
    t.no_errors()


def test_edit_only_saved_not_dirty_and_lanes(t):
    '''単独編集は保存して開き直すと戻る・切り替えただけでは未保存にならない・レーンを足すと同じレーン（Notes 2）に付いたまま動きUndoで戻る'''
    ed = open_nle(t, "rich")
    _set(ed, 1)
    ed.wait(0.3)
    d = dirty(ed)
    t.eq((d["lamp"], d["same"]), (False, True), "切り替えただけでは未保存にならない")
    pj = json.loads(ed.js("window._dbg.rt.buildProjectText()"))
    t.eq(pj["laneStates"].get("editOnly"), 1, "プロジェクトに保存される（内部の段）")
    text = ed.js("window._dbg.rt.buildProjectText()")
    ed = t.fresh()
    ed.js(f"window._dbg.rt.applyProject(JSON.parse({json.dumps(text)}))")
    wait_until(ed, "window._dbgApp.nle().clips.length===2", label="開き直し")
    t.eq(_eo(ed), 1, "開き直すと戻る")
    wait_until(ed, "document.getElementById('eoInd').classList.contains('on')", label="隅の表示")
    t.eq(_ind(ed)["main"], "✎ 単独編集: Notes 2", "開き直した後の隅の表示")
    # 範囲外の値・旧ファイル（キー無し）はオフ
    bad = json.loads(text); bad["laneStates"]["editOnly"] = 9
    ed.js(f"window._dbg.rt.applyProject({json.dumps(bad)})")
    wait_until(ed, "window._dbgApp.nle().editOnly===null", label="範囲外の値はオフ")
    ed.js(f"window._dbg.rt.applyProject(JSON.parse({json.dumps(text)}))")
    wait_until(ed, "window._dbgApp.nle().editOnly===1", label="もう一度開く")
    # レーンの追加（一番上）: 単独編集は同じレーン（Notes 2＝段1→段2）に付いたまま
    s = scr(ed)
    menu(ed, s["left"] + 20, lane_y(ed, "n", 0), "レーンを追加")
    wait_until(ed, "window._dbgApp.nle().lanes.n===4", label="ノーツのレーンを追加")
    t.eq(_eo(ed), 2, "単独編集は1段ずれて同じレーンに付いたまま")
    wait_until(ed, "document.getElementById('eoInd').textContent.includes('Notes 2')", label="隅の表示は Notes 2 のまま")
    nle_mouse(ed); ed.key("z", ctrl=True)
    wait_until(ed, "window._dbgApp.nle().lanes.n===3", label="追加のUndo")
    t.eq(_eo(ed), 1, "Undoで元の段へ戻る")
    t.no_errors()

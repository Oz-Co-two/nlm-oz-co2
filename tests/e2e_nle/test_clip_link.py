"""リンクしたクリップ（2026-10-19）: 同じ中身のクリップを繋ぎ、親だけを編集する。
仕様（利用者と合意・メモ project_edit_lane_link_spec）: 親だけ編集でき、子は打てない（子を触ると帯で［親へジャンプ］［リンクを解除］）。
子の中身＝親の中身（親の長さまで）。名前・色は同期。リンクしていない2つを選んだ時だけ親を選ぶ画面（消えるノーツの数つき）。
3つ以上は既にある親の子に加える（無ければ「2つに絞って」と断る）。別々の2つのリンクは親を選んでまとめる。親を消すと残り2つ以上なら次の親を選ぶ。
リンク中は分割・結合できない。解除した子は親の中身の写しを持つ（子の長さより後ろに隠れた分も）。保存は中身を実体で書いた上でリンク情報を足す。
古い版で子を編集したファイルは、開いた時にリンクを外して知らせる。難易度をまたぐ操作は tests/e2e_project/test_diff_link.py。
素材 rich（Hard）: ノーツのクリップ 拍0〜16（ノーツ7・ボム1・壁1・アーク1）、ライトのクリップ 拍0〜16（ライト3）"""
import json

from e2e_helpers import wait_until, counts, cell, project, state, hover_3d
from nle_helpers import (open_nle, clips, hover, menu, nle, nle_mouse, scr, select, clip_xy, undo, redo, take_errors,
                         export_dat, lane_y)


# ---- 部品 ----
def _links(ed):
    return ed.js("window._dbgApp.links()")


def _cur(ed, lk="n"):
    """今の難易度のクリップ（リンクの情報・中身の相対拍つき）を拍順に"""
    return sorted([c for c in _links(ed)["clips"] if c["cur"] and c["lk"] == lk], key=lambda c: (c["beat"], c["track"]))


def _by_id(ed, cid):
    return next(c for c in _links(ed)["clips"] if c["id"] == cid)


def _zoom_out(ed):
    """NLE を一番引いた表示に（Ctrl+ホイール。引ける上限はクリップの最後尾+4拍）"""
    s = scr(ed)
    for _ in range(4):
        ed.wheel(s["left"] + s["gut"] + 40, s["lanes"] + 10, 120, ctrl=True)
    ed.wait(0.1)


def _dup(ed, src, at, lk="n"):
    """src のクリップをコピーして拍 at へ貼り付け、貼ったクリップを返す（同じレーンが埋まっていれば空いているレーンへ入る）"""
    ids0 = {c["id"] for c in clips(ed, lk)}
    _sel(ed, [src])
    nle_mouse(ed)
    ed.key("c", ctrl=True)
    ed.key("v", ctrl=True)
    wait_until(ed, "!!window._dbgApp.nle().paste", label="貼り付けの追従")
    hover(ed, at, lk, src["track"])
    ed.click(*clip_xy(ed, {"beat": at, "len": 0, "lk": lk, "track": src["track"]}))
    wait_until(ed, f"window._dbgApp.nle().clips.filter(c=>c.lk==='{lk}').length==={len(ids0) + 1}", label=f"拍{at}への貼り付け")
    return next(c for c in clips(ed, lk) if c["id"] not in ids0)


def _sel(ed, cs):
    """cs だけを選ぶ（先に A で選択を外す＝選択中のクリップを押し直してもグループの選択が残るため）"""
    nle_mouse(ed)
    ed.key("a")
    wait_until(ed, "window._dbgApp.nle().sel.length===0", label="選択解除")
    select(ed, cs[0])
    for c in cs[1:]:
        select(ed, c, shift=True)


def _hide_toast(ed):
    """下の案内（エラーの帯）を消す＝NLE のクリップの上に重なってクリックを奪わないように"""
    ed.js("document.getElementById('errToast').style.display='none'")


def _dlg(ed, kind, timeout=5):
    """確認の画面（#dirtyDlg[data-lk=kind]）が出るのを待ち、文・一覧・ボタンを返す"""
    wait_until(ed, f"!!document.querySelector('#dirtyDlg[data-lk=\"{kind}\"] .ddBtns button')", timeout=timeout, label=f"確認の画面 {kind}")
    return ed.js("""(d=>({text:d.innerText, opts:[...d.querySelectorAll('.lkOpt')].map(o=>({text:o.innerText,
      checked:o.querySelector('input').checked, disabled:o.querySelector('input').disabled})),
      btns:[...d.querySelectorAll('.ddBtns button')].map(b=>b.textContent)}))(document.getElementById('dirtyDlg'))""")


def _xy(ed, sel):
    p = ed.js(f"(e=>{{ if(!e) return null; const r=e.getBoundingClientRect(); return {{x:r.left+r.width/2,y:r.top+r.height/2}}; }})(document.querySelector({json.dumps(sel)}))")
    assert p, f"要素がありません: {sel}"
    return p["x"], p["y"]


def _press(ed, sel):
    x, y = _xy(ed, sel)
    ed.move(x, y); ed.wait(0.05)
    ed.click(x, y)


def _dlg_pick(ed, i):
    _press(ed, f"#dirtyDlg .lkOpt:nth-of-type({i + 1}) input")


def _dlg_btn(ed, text):
    i = _dlg_btn_index(ed, text)
    _press(ed, f"#dirtyDlg .ddBtns button:nth-child({i + 1})")
    wait_until(ed, "!document.getElementById('dirtyDlgBg')", label=f"「{text}」で画面が閉じる")


def _dlg_btn_index(ed, text):
    btns = ed.js("[...document.querySelectorAll('#dirtyDlg .ddBtns button')].map(b=>b.textContent)")
    for i, b in enumerate(btns):
        if text in b:
            return i
    raise AssertionError(f"ボタン「{text}」がありません: {btns}")


def _link_two(ed, a, b, parent=0):
    """a・b（リンクしていない）を選んで K → 親を選ぶ画面で parent 番目（拍順）を選んでリンクする"""
    _sel(ed, [a, b])
    nle_mouse(ed)
    ed.key("k")
    d = _dlg(ed, "parent-link")
    if parent:
        _dlg_pick(ed, parent)
    _dlg_btn(ed, "リンクする")
    wait_until(ed, f"(c=>c.filter(x=>x.link).length>=2)(window._dbgApp.nle().clips)", label="リンク")
    return d


def _band(ed):
    return _links(ed)["band"]


def _band_btn(ed, text):
    i = ed.js(f"[...document.querySelectorAll('#lkBand button')].findIndex(b=>b.textContent.includes({json.dumps(text)}))")
    assert i >= 0, f"帯にボタン「{text}」がありません: {_band(ed)}"
    _press(ed, f"#lkBand button:nth-of-type({i + 1})")


def _seek(ed, beat):
    """NLE の数字のルーラーをクリックして再生ヘッドを beat へ（3D の表示もそこへ）"""
    s = scr(ed, beat)
    ed.click(s["x"], s["ruler"] + 6)
    wait_until(ed, f"Math.abs(window._dbgApp.state().cur-{beat})<1e-6", label=f"拍{beat}へ移動")
    ed.wait(0.3)


def _lane(ed, c):
    """クリップのレーンの表示名（Notes n＝下から数える）"""
    return f"Notes {nle(ed)['lanes']['n'] - c['track']}"


def _notes(c):
    return [tuple(n) for n in c["notes"]]


# ---- テスト ----
def test_link_two_choose_parent(t):
    '''リンクしていない2つを選んで K → 親を選ぶ画面（名前・拍・曲の時刻・レーン・難易度・ノーツ数・消えるノーツの数）→ 選んだ方が親・子は親と同じ中身 → Undo/Redo'''
    ed = open_nle(t, "rich")
    a = clips(ed, "n")[0]
    b = _dup(ed, a, 20)
    menu(ed, *clip_xy(ed, b), "左右反転")   # b の中身を変える（親を選ぶと、もう一方のノーツが消える）
    wait_until(ed, f"window._dbgApp.links().clips.find(c=>c.id==={json.dumps(b['id'])}).notes[0][1]!==1", label="左右反転")
    a0, b0 = _by_id(ed, a["id"]), _by_id(ed, b["id"])
    t.ok(_notes(a0) != _notes(b0), "左右反転で中身が違う")
    _sel(ed, [a, b])
    nle_mouse(ed)
    u0 = state(ed)["undo"]
    ed.key("k")
    d = _dlg(ed, "parent-link")
    t.eq(len(d["opts"]), 2, "候補は2つ")
    t.ok("拍 0〜16" in d["opts"][0]["text"] and "拍 20〜36" in d["opts"][1]["text"], f"拍の範囲（拍順）: {d['opts']}")
    for o in d["opts"]:
        for w in ("Hard", "Notes", "ノーツ 8", "0:"):
            t.ok(w in o["text"], f"候補に「{w}」: {o['text']}")
        t.ok("消えるノーツ" in o["text"], f"親にするともう一方で消えるノーツの数: {o['text']}")
    t.eq([o["checked"] for o in d["opts"]], [True, False], "既定は先頭（拍が早い方）")
    _dlg_pick(ed, 1)   # 後ろ（左右反転した方）を親に
    _dlg_btn(ed, "リンクする")
    wait_until(ed, f"window._dbgApp.links().clips.filter(c=>c.link).length===2", label="リンク")
    a1, b1 = _by_id(ed, a["id"]), _by_id(ed, b["id"])
    t.ok(a1["link"] and a1["link"] == b1["link"], "同じリンク")
    t.eq((a1["par"], b1["par"]), (False, True), "選んだ b が親・a が子")
    t.eq(_notes(a1), _notes(b0), "子（a）の中身は親（b）と同じ（a の元の中身は消える）")
    t.eq(a1["n"], b1["n"], "子と親の中身の数が同じ")
    t.eq(counts(ed)["notes"], 14, "3Dのノーツ（フラット）＝両方の中身")
    t.eq(state(ed)["undo"], u0 + 1, "履歴は1つ")
    dat = export_dat(ed)["HardStandard.dat"]
    xs = sorted((n["b"], n["x"], n["c"]) for n in dat["colorNotes"])
    t.eq([x for x in xs if x[0] < 16], [(b_ - 20, x_, c_) for (b_, x_, c_) in xs if b_ >= 20], "書き出しでも子（拍0〜）は親（拍20〜）と同じ並び")
    undo(ed)
    wait_until(ed, "window._dbgApp.links().clips.every(c=>!c.link)", label="リンクのUndo")
    t.eq(_notes(_by_id(ed, a["id"])), _notes(a0), "Undoで a の中身も元に戻る")
    redo(ed)
    wait_until(ed, "window._dbgApp.links().clips.filter(c=>c.link).length===2", label="リンクのRedo")
    t.eq(_by_id(ed, b["id"])["par"], True, "Redoで b が親に戻る")
    t.no_errors()


def test_link_three_and_existing(t):
    '''3つ以上: リンクしていない物だけなら「2つに絞って」と断る／既にある親と一緒なら子に加える（親は選ばない）／同じリンクなら「既に同じリンクです」／消えるノーツがある時だけ確認'''
    ed = open_nle(t, "rich")
    a = clips(ed, "n")[0]
    b, c = _dup(ed, a, 20), _dup(ed, a, 0)   # c は隣のレーンの拍0
    _sel(ed, [a, b, c])
    nle_mouse(ed)
    ed.key("k")
    wait_until(ed, "document.getElementById('errToast').textContent.includes('2つに絞って')", label="2つに絞っての案内")
    take_errors(ed, "2つに絞って")
    _hide_toast(ed)
    t.ok(all(not x["link"] for x in _links(ed)["clips"]), "リンクしない")
    _link_two(ed, a, b)   # a が親
    _sel(ed, [b, c])      # 子と、リンクしていない物（親は選んでいない）
    nle_mouse(ed)
    ed.key("k")
    wait_until(ed, f"!!window._dbgApp.links().clips.find(c=>c.id==={json.dumps(c['id'])}).link", label="子に加える")
    t.ok(not ed.js("!!document.getElementById('dirtyDlgBg')"), "中身が同じなら確認の画面は出ない")
    al = _by_id(ed, a["id"])["link"]
    t.eq([(_by_id(ed, x["id"])["link"] == al, _by_id(ed, x["id"])["par"]) for x in (a, b, c)], [(True, True), (True, False), (True, False)], "a が親・b,c が子")
    _sel(ed, [a, c])
    nle_mouse(ed)
    u0 = state(ed)["undo"]   # 選択も履歴に積まれるので、選んだ後で数える
    ed.key("k")
    wait_until(ed, "document.getElementById('stat').textContent.includes('既に同じリンクです')", label="既に同じリンク")
    t.eq(state(ed)["undo"], u0, "何もしない時は履歴を積まない")
    d = _dup(ed, a, 20)   # 隣のレーンの拍20
    menu(ed, *clip_xy(ed, d), "左右反転")
    ed.wait(0.2)
    _sel(ed, [a, d])
    nle_mouse(ed)
    ed.key("k")
    dl = _dlg(ed, "confirm")
    t.ok("消えるノーツ" in dl["text"], f"消えるノーツがあるので確認: {dl['text']}")
    _dlg_btn(ed, "続ける")
    wait_until(ed, f"window._dbgApp.links().clips.find(c=>c.id==={json.dumps(d['id'])}).link===window._dbgApp.links().clips.find(c=>c.id==={json.dumps(a['id'])}).link", label="d も子に")
    t.eq(_notes(_by_id(ed, d["id"])), _notes(_by_id(ed, a["id"])), "加えた子の中身は親と同じ")
    t.no_errors()


def test_merge_two_links(t):
    '''別々の2つのリンク（親はどちらも選ばず子を選んでも）→ 親を選ぶ画面でまとめる。選ばなかった方の親も子も全部、選んだ親の子になる → Undoで2つに戻る'''
    ed = open_nle(t, "rich")
    a = clips(ed, "n")[0]
    b = _dup(ed, a, 20)
    c = _dup(ed, a, 0)   # 隣のレーン
    menu(ed, *clip_xy(ed, c), "左右反転")
    ed.wait(0.2)
    d = _dup(ed, c, 20)
    _link_two(ed, a, b)
    _link_two(ed, c, d)
    la, lc = _by_id(ed, a["id"])["link"], _by_id(ed, c["id"])["link"]
    t.ok(la != lc, "別々のリンク")
    _sel(ed, [b, d])   # 両方とも子
    nle_mouse(ed)
    ed.key("k")
    dl = _dlg(ed, "parent-merge")
    t.eq(len(dl["opts"]), 2, "候補は2つのリンクの親")
    ic = next(i for i, o in enumerate(dl["opts"]) if _lane(ed, c) in o["text"])
    t.ok(all("Hard" in o["text"] and "消えるノーツ" in o["text"] for o in dl["opts"]), f"消えるノーツを難易度ごとに: {dl['opts']}")
    _dlg_pick(ed, ic)   # c を親に
    _dlg_btn(ed, "まとめる")
    wait_until(ed, "new Set(window._dbgApp.links().clips.filter(c=>c.link).map(c=>c.link)).size===1", label="1つのリンクに")
    cs = {x: _by_id(ed, v["id"]) for x, v in (("a", a), ("b", b), ("c", c), ("d", d))}
    t.eq({k: v["par"] for k, v in cs.items()}, {"a": False, "b": False, "c": True, "d": False}, "親は c だけ")
    t.ok(all(_notes(v) == _notes(cs["c"]) for v in cs.values()), "全部 c と同じ中身")
    undo(ed)
    wait_until(ed, "new Set(window._dbgApp.links().clips.filter(c=>c.link).map(c=>c.link)).size===2", label="まとめるのUndo")
    t.eq(_by_id(ed, a["id"])["par"], True, "Undoで a はまた親")
    t.no_errors()


def test_kid_readonly_and_band(t):
    '''子の物は3Dで打てない: 子のノーツをクリック→帯（親へジャンプ・リンクを解除）でクリック自体は何もしない／子の範囲に置こうとしても帯／親に置くと子にも入る'''
    ed = open_nle(t, "rich")
    a = clips(ed, "n")[0]
    b = _dup(ed, a, 20)
    _link_two(ed, a, b)   # a が親・b（拍20〜36）が子
    _seek(ed, 20)
    hover_3d(ed)
    kid = [o for o in ed.js("window._dbgApp.objScreen()") if o["kind"] == "note" and o["inView"] and 20 <= o["beat"] < 36]
    t.ok(kid, "子のノーツが3Dに見えている")
    o = max(kid, key=lambda o: o["sy"])
    n0, u0 = counts(ed)["notes"], state(ed)["undo"]
    ed.move(o["sx"], o["sy"]); ed.wait(0.1)
    ed.click(o["sx"], o["sy"])
    wait_until(ed, "!!(window._dbgApp.links().band||{}).kind", label="子を触った帯")
    bd = _band(ed)
    t.eq(bd["kind"], "kid", "子の帯")
    t.ok("リンクの子" in bd["text"] and "親へジャンプ" in bd["text"] and "リンクを解除" in bd["text"], f"帯の文とボタン: {bd['text']}")
    t.eq(state(ed)["sel"], 0, "子のノーツは選ばれない")
    t.eq((counts(ed)["notes"], state(ed)["undo"]), (n0, u0), "クリック自体は何もしない")
    # 子の範囲（空いているマス）へ置こうとしても帯
    ed.js("document.querySelector('#lkBand')&&document.querySelector('#lkBand').classList.remove('on')")
    _seek(ed, 21)
    hover_3d(ed)
    p = cell(ed, 0, 2)
    ed.move(p["x"], p["y"]); ed.wait(0.15)
    ed.click(p["x"], p["y"])
    wait_until(ed, "!!window._dbgApp.links().band", label="子の範囲に置こうとした帯")
    t.eq(counts(ed)["notes"], n0, "子の範囲には置けない")
    # 親へジャンプ
    _band_btn(ed, "親へジャンプ")
    wait_until(ed, f"window._dbgApp.nle().sel.includes({json.dumps(a['id'])})", label="親が選ばれる")
    wait_until(ed, "Math.abs(window._dbgApp.state().cur)<1e-6", label="再生ヘッドが親の頭へ")
    # 親に置くと子にも入る（子の中身・3Dのフラット・書き出し）
    _seek(ed, 1)
    hover_3d(ed)
    p = cell(ed, 0, 2)
    ed.move(p["x"], p["y"]); ed.wait(0.15)
    ed.click(p["x"], p["y"])
    wait_until(ed, f"window._dbgApp.state().counts.notes==={n0 + 2}", label="親に置くと子にも入る")
    t.eq(_by_id(ed, b["id"])["n"]["notes"], 8, "子の中身も8")
    t.eq(_notes(_by_id(ed, b["id"])), _notes(_by_id(ed, a["id"])), "子＝親")
    dat = export_dat(ed)["HardStandard.dat"]
    t.ok(any(abs(n["b"] - 21) < 1e-6 and n["x"] == 0 and n["y"] == 2 for n in dat["colorNotes"]), "書き出しに子の側（拍21）のノーツもある")
    hover_3d(ed)
    ed.key("z", ctrl=True)
    wait_until(ed, f"window._dbgApp.state().counts.notes==={n0}", label="親に置いたのをUndo＝子からも消える")
    wait_until(ed, f"window._dbgApp.links().clips.find(c=>c.id==={json.dumps(b['id'])}).n.notes===7", label="Undoで子も7に戻る")
    t.no_errors()


def test_unlink_keeps_copy_and_kid_trim(t):
    '''子は右端だけトリムできる（左端は帯）。解除した子は解除した時の親の中身の写しを持つ（子の長さより後ろに隠れた分も残る）'''
    ed = open_nle(t, "rich")
    a = clips(ed, "n")[0]
    b = _dup(ed, a, 20)
    _link_two(ed, a, b)
    _zoom_out(ed)
    y = lane_y(ed, "n", b["track"])
    x36, x26 = scr(ed, 36)["x"], scr(ed, 26)["x"]
    ed.drag(x36, y, x26, y)
    wait_until(ed, f"window._dbgApp.nle().clips.find(c=>c.id==={json.dumps(b['id'])}).len===6", label="子の右端のトリム")
    t.eq(_by_id(ed, b["id"])["n"]["notes"], 7, "トリムしても子の中身は7（範囲外は隠して保持）")
    t.eq(counts(ed)["notes"], 7 + 4, "3Dに出るのは子の長さまで（拍22〜25の4個）")
    x20, x24 = scr(ed, 20)["x"], scr(ed, 24)["x"]
    ed.drag(x20, y, x24, y)
    wait_until(ed, "(window._dbgApp.links().band||{}).kind==='kid'", label="左端のトリムは帯")
    t.eq((_by_id(ed, b["id"])["beat"], _by_id(ed, b["id"])["len"]), (20, 6), "左端は動かない")
    menu(ed, *clip_xy(ed, _by_id(ed, b["id"]), 22), "リンクを解除")
    wait_until(ed, "window._dbgApp.links().clips.every(c=>!c.link)", label="解除（残り1つになった親のリンクも外れる）")
    b2 = _by_id(ed, b["id"])
    t.eq(b2["n"]["notes"], 7, "解除した子は親の中身の写し（隠れた分も残す）")
    t.eq(_notes(b2), _notes(_by_id(ed, a["id"])), "写し＝解除した時の親の中身")
    t.eq(counts(ed)["notes"], 11, "3Dは変わらない")
    t.no_errors()


def test_delete_parent_choose_next_and_make_parent(t):
    '''親を消すと残り2つ以上なら次の親を選ぶ（Undoで元に戻る）／右クリック「これを親にする」／子を消して1つになったらリンクは消える'''
    ed = open_nle(t, "rich")
    a = clips(ed, "n")[0]
    b, c = _dup(ed, a, 20), _dup(ed, a, 0)
    _link_two(ed, a, b)
    _sel(ed, [b, c]); nle_mouse(ed); ed.key("k")
    wait_until(ed, "window._dbgApp.links().clips.filter(c=>c.link).length===3", label="3つのリンク")
    # これを親にする
    menu(ed, *clip_xy(ed, _by_id(ed, b["id"])), "これを親にする")
    wait_until(ed, f"window._dbgApp.links().clips.find(c=>c.id==={json.dumps(b['id'])}).par", label="b が親")
    t.eq([_by_id(ed, x["id"])["par"] for x in (a, b, c)], [False, True, False], "親は b だけ")
    undo(ed)
    wait_until(ed, f"window._dbgApp.links().clips.find(c=>c.id==={json.dumps(a['id'])}).par", label="これを親にするのUndo")
    # 親（a）を消す → 次の親を選ぶ
    _sel(ed, [_by_id(ed, a["id"])])
    nle_mouse(ed)
    ed.key("Delete")
    dl = _dlg(ed, "parent-next")
    t.eq(len(dl["opts"]), 2, "残りの2つから選ぶ")
    _dlg_pick(ed, next(i for i, o in enumerate(dl["opts"]) if _lane(ed, c) in o["text"]))
    _dlg_btn(ed, "決定")
    wait_until(ed, f"window._dbgApp.links().clips.find(c=>c.id==={json.dumps(c['id'])}).par", label="c が次の親")
    t.eq(_by_id(ed, b["id"])["par"], False, "b は子のまま")
    undo(ed)
    wait_until(ed, f"(x=>x&&x.par)(window._dbgApp.links().clips.find(c=>c.id==={json.dumps(a['id'])}))", label="削除のUndoで a が親に戻る")
    t.eq([_by_id(ed, x["id"])["par"] for x in (b, c)], [False, False], "Undoで c は子に戻る（親は1つ）")
    # 子を2つ消して1つになるとリンクは消える
    _sel(ed, [_by_id(ed, b["id"]), _by_id(ed, c["id"])]); nle_mouse(ed); ed.key("Delete")
    wait_until(ed, f"!window._dbgApp.links().clips.find(c=>c.id==={json.dumps(a['id'])}).link", label="1つだけ残ったリンクは外れる")
    t.no_errors()


def test_split_merge_blocked(t):
    '''リンク中は分割できない（C・分割モードで帯「解除してから」）・結合もできない（案内）。帯の［リンクを解除］で解除できる'''
    ed = open_nle(t, "rich")
    a = clips(ed, "n")[0]
    b = _dup(ed, a, 20)
    _link_two(ed, a, b)
    n0 = len(clips(ed, "n"))
    _sel(ed, [a])
    hover(ed, 6, "n", a["track"])
    ed.key("c")
    wait_until(ed, "(window._dbgApp.links().band||{}).kind==='split'", label="分割できない帯")
    t.eq(len(clips(ed, "n")), n0, "Cで分割されない")
    t.ok("分割できません" in _band(ed)["text"], _band(ed)["text"])
    nle_mouse(ed); ed.key("r")
    wait_until(ed, "window._dbgApp.nle().razor===true", label="分割モード")
    ed.click(*clip_xy(ed, _by_id(ed, b["id"]), 26))
    ed.wait(0.2)
    t.eq(len(clips(ed, "n")), n0, "分割モードでも分割されない")
    nle_mouse(ed); ed.key("Escape")
    _sel(ed, [_by_id(ed, a["id"]), _by_id(ed, b["id"])])
    ed.key("g", ctrl=True)
    wait_until(ed, "document.getElementById('errToast').textContent.includes('結合できません')", label="結合できない案内")
    take_errors(ed, "結合できません")
    _hide_toast(ed)
    t.eq(len(clips(ed, "n")), n0, "結合されない")
    _sel(ed, [_by_id(ed, a["id"])])
    hover(ed, 6, "n", a["track"])
    ed.key("c")
    wait_until(ed, "(window._dbgApp.links().band||{}).kind==='split'", label="分割できない帯（2回目）")
    _band_btn(ed, "リンクを解除")
    wait_until(ed, "window._dbgApp.links().clips.every(c=>!c.link)", label="帯からリンクを解除")
    t.no_errors()


def test_name_color_sync_and_badge(t):
    '''名前・色は同期（子で変えても親に揃う）。保存すると各クリップに中身を実体で書いた上でリンク情報を足し、開き直してもリンクは残る'''
    ed = open_nle(t, "rich")
    a = clips(ed, "n")[0]
    b = _dup(ed, a, 20)
    _link_two(ed, a, b)
    menu(ed, *clip_xy(ed, _by_id(ed, b["id"])), "ラベルを変更")
    wait_until(ed, "!!document.querySelector('body > input[type=text]')", timeout=3, label="名前の入力欄")
    ed.js("(i=>{ i.value='サビ'; i.dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',bubbles:true})); return 1; })([...document.querySelectorAll('body > input[type=text]')].pop())")
    wait_until(ed, f"window._dbgApp.links().clips.find(c=>c.id==={json.dumps(a['id'])}).label==='サビ'", label="名前が親にも")
    t.eq(_by_id(ed, b["id"])["label"], "サビ", "子の名前も")
    pj = project(ed)
    secs = [s for s in pj["difficulties"]["hardstandard.dat"]["sections"] if s.get("link")]
    t.eq(len(secs), 2, "保存: リンクしたクリップが2つ")
    t.eq(sorted(bool(s.get("linkParent")) for s in secs), [False, True], "保存: 親は1つ")
    t.ok(all(len(s["content"].get("notes") or []) == 7 for s in secs), "保存: 子も中身を実体で持つ（古い版で開いてもノーツは消えない）")
    ed.js(f"(async()=>{{ await window._dbg.rt.applyProject({json.dumps(pj, ensure_ascii=False)}); return 1; }})()")
    wait_until(ed, "window._dbgApp.links().clips.filter(c=>c.link).length===2", label="開き直してもリンクは残る")
    t.eq(_band(ed), None, "中身が同じならリンクを外す知らせは出ない")
    t.no_errors()


def test_old_version_edited_kid(t):
    '''古い版で子を編集したファイル（リンク情報はあるが中身が親と違う）を開くと、その子のリンクを外して「1 個のリンクを外しました」と知らせる'''
    ed = open_nle(t, "rich")
    a = clips(ed, "n")[0]
    b, c = _dup(ed, a, 20), _dup(ed, a, 0)
    _link_two(ed, a, b)
    _sel(ed, [b, c]); nle_mouse(ed); ed.key("k")
    wait_until(ed, "window._dbgApp.links().clips.filter(c=>c.link).length===3", label="3つのリンク")
    pj = project(ed)
    hard = pj["difficulties"]["hardstandard.dat"]
    kid = next(s for s in hard["sections"] if s.get("link") and not s.get("linkParent") and s.get("track") == c["track"])
    kid["content"]["notes"] = kid["content"]["notes"][1:]   # 古い版で子のノーツを1つ消した
    ed.js(f"(async()=>{{ await window._dbg.rt.applyProject({json.dumps(pj, ensure_ascii=False)}); return 1; }})()")
    wait_until(ed, "(window._dbgApp.links().band||{}).kind==='open'", label="リンクを外した知らせ")
    t.ok("1 個のリンクを外しました" in _band(ed)["text"], _band(ed)["text"])
    t.eq([(bool(_by_id(ed, x["id"])["link"]), _by_id(ed, x["id"])["n"]["notes"]) for x in (a, b, c)], [(True, 7), (True, 7), (False, 6)],
         "中身の違う子（c）だけリンクを外し、中身はそのまま")
    t.no_errors()


def test_light_link(t):
    '''ライトのクリップもリンクできる（親を左右反転すると子も変わる）。ノーツとライトは混ぜられない'''
    ed = open_nle(t, "rich")
    la = clips(ed, "l")[0]
    lb = _dup(ed, la, 20, "l")
    _link_two(ed, la, lb)
    lights0 = _by_id(ed, lb["id"])["lights"]
    menu(ed, *clip_xy(ed, _by_id(ed, la["id"])), "左右反転")
    wait_until(ed, f"JSON.stringify(window._dbgApp.links().clips.find(c=>c.id==={json.dumps(lb['id'])}).lights)!=={json.dumps(json.dumps(lights0))}", label="親の反転が子へ")
    t.eq(_by_id(ed, lb["id"])["lights"], _by_id(ed, la["id"])["lights"], "子のライト＝親")
    menu(ed, *clip_xy(ed, _by_id(ed, lb["id"])), "左右反転")   # 子は反転できない（帯）
    wait_until(ed, "(window._dbgApp.links().band||{}).kind==='kid'", label="子は編集できない帯")
    na = clips(ed, "n")[0]
    _sel(ed, [na, _by_id(ed, la["id"])]); nle_mouse(ed); ed.key("k")
    wait_until(ed, "document.getElementById('errToast').textContent.includes('ノーツとライト')", label="混ぜられない案内")
    take_errors(ed, "ノーツとライト")
    _hide_toast(ed)
    t.ok(not _by_id(ed, na["id"])["link"], "ノーツのクリップはリンクされない")
    t.no_errors()


def test_link_paste_same_diff(t):
    '''「リンクして貼り付け」（Ctrl+Shift+V）: 貼ったクリップはコピー元の子になる（コピー元が親になる）。普通の貼り付け（Ctrl+V）は繋がない'''
    ed = open_nle(t, "rich")
    a = clips(ed, "n")[0]
    _sel(ed, [a])
    nle_mouse(ed)
    ed.key("c", ctrl=True)
    ed.key("v", ctrl=True, shift=True)
    wait_until(ed, "!!window._dbgApp.nle().paste", label="リンクして貼り付けの追従")
    hover(ed, 20, "n", a["track"])
    ed.click(*clip_xy(ed, {"beat": 20, "len": 0, "lk": "n", "track": a["track"]}))
    wait_until(ed, "window._dbgApp.nle().clips.filter(c=>c.lk==='n').length===2", label="貼り付け")
    a1, b1 = _cur(ed)
    t.ok(a1["link"] and a1["link"] == b1["link"], "コピー元と同じリンク")
    t.eq((a1["par"], b1["par"]), (True, False), "コピー元が親・貼った物が子")
    nle_mouse(ed)
    ed.key("v", ctrl=True)
    wait_until(ed, "!!window._dbgApp.nle().paste", label="普通の貼り付けの追従")
    ids = {x["id"] for x in _cur(ed)}
    hover(ed, 0, "n", a["track"])
    ed.click(*clip_xy(ed, {"beat": 0, "len": 0, "lk": "n", "track": a["track"]}))
    wait_until(ed, "window._dbgApp.nle().clips.filter(c=>c.lk==='n').length===3", label="普通の貼り付け（隣のレーン）")
    t.ok(not next(x for x in _cur(ed) if x["id"] not in ids)["link"], "Ctrl+V は繋がない")
    t.no_errors()


def test_bar_offset_note_and_3d_paste_refused(t):
    '''小節の頭からの位置がずれていてもリンクできる（親を選ぶ画面に1行）。3Dで子の範囲へ貼り付けようとすると帯を出して貼らない'''
    ed = open_nle(t, "rich")
    a = clips(ed, "n")[0]
    b = _dup(ed, a, 18)   # 18 は小節の頭（4の倍数）から2拍ずれ
    _sel(ed, [a, b]); nle_mouse(ed); ed.key("k")
    d = _dlg(ed, "parent-link")
    t.ok("小節の頭からの位置が違います" in d["text"], f"位置のずれの1行: {d['text']}")
    _dlg_btn(ed, "リンクする")
    wait_until(ed, "window._dbgApp.links().clips.filter(c=>c.link).length===2", label="リンク")
    # 3D: 親のノーツを1つ選んでコピー → 子の範囲（拍21）で貼り付け → 帯・数は変わらない・履歴も積まない
    hover_3d(ed)
    o = max((o for o in ed.js("window._dbgApp.objScreen()") if o["kind"] == "note" and o["inView"] and o["beat"] < 16), key=lambda o: o["sy"])
    ed.move(o["sx"], o["sy"]); ed.wait(0.1); ed.click(o["sx"], o["sy"])
    wait_until(ed, "window._dbgApp.state().sel===1", label="親のノーツを選ぶ")
    ed.key("c", ctrl=True)
    _seek(ed, 21)
    hover_3d(ed)
    n0, u0 = counts(ed)["notes"], state(ed)["undo"]
    ed.key("v", ctrl=True)
    wait_until(ed, "(window._dbgApp.links().band||{}).kind==='kid'", label="子の範囲には貼れない帯")
    ed.wait(0.2)
    t.eq((counts(ed)["notes"], state(ed)["undo"]), (n0, u0), "貼られない・履歴も積まない")
    t.eq(_by_id(ed, b["id"])["n"]["notes"], 7, "子の中身は変わらない")
    t.no_errors()


def test_shortcut_keys_listed(t):
    '''ショートカット: リンクする=K・リンクして貼り付け=Ctrl+Shift+V（ACTIONS）。NLE の早見表に載る'''
    ed = open_nle(t, "rich")
    rows = ed.js("document.getElementById('nodeKeys').innerText")
    t.ok("リンク / リンクして貼り付け" in rows and "K" in rows and "Ctrl + Shift + V" in rows, f"早見表: {rows}")
    t.no_errors()

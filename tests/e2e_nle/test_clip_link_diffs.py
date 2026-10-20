"""リンクしたクリップ（2026-10-19）: 難易度をまたぐリンク。親は1つ（ある難易度のあるクリップ）・子はどの難易度にも置ける。
難易度間コピー（転送・受信）の「親の難易度に繋ぐ」（既定オン）・別の難易度への貼り付けの「繋ぐ／切る」・「他の難易度の同じ位置のクリップとリンク…」・
親の編集が他の難易度の子（退避データのフラット・書き出し）へ届くこと・他の難易度に子がいる親を編集し始めた時の帯（作業中1回）・
他の難易度とリンクしている時の全消去の断り・1回の操作＝1回の Undo（全難易度の履歴 'diffs'）。
素材 rich: Hard = ノーツのクリップ 拍0〜16（ノーツ7）・ライトのクリップ 拍0〜16（ライト3）／ Expert = ノーツ23・ライト12"""
import json
import sys
from pathlib import Path

_P = str(Path(__file__).resolve().parents[1] / "e2e_project")
if _P not in sys.path:
    sys.path.insert(0, _P)

from e2e_helpers import wait_until, counts, cell, state, switch_diff, hover_3d   # noqa: E402
from nle_helpers import open_nle, clips, hover, menu, nle_mouse, clip_xy, export_dat, take_errors   # noqa: E402
from project_helpers import copy_dialog, diff_menu_open, menu_pick, toast, _click_el   # noqa: E402
from test_clip_link import _links, _by_id, _dlg, _dlg_btn, _band, _band_btn, _seek, _notes, _hide_toast, _sel   # noqa: E402

HARD, EXPERT, EASY, NORMAL = "hardstandard.dat", "expertstandard.dat", "easystandard.dat", "normalstandard.dat"


def _in(ed, dk, lk="n"):
    return sorted([c for c in _links(ed)["clips"] if c["dk"] == dk and c["lk"] == lk], key=lambda c: (c["beat"], c["track"]))


def _flats(ed, dk):
    return _links(ed)["flats"].get(dk)


def _undo3d(ed):
    hover_3d(ed)
    ed.key("z", ctrl=True)


def _place(ed, beat, x=0, y=2):
    """配置モードで拍 beat・マス(x,y) にノーツを置く（再生ヘッドを beat へ動かしてから）"""
    _seek(ed, beat)
    hover_3d(ed)
    p = cell(ed, x, y)
    ed.move(p["x"], p["y"]); ed.wait(0.15)
    ed.click(p["x"], p["y"])


def _diff_menu(ed, dn):
    """難易度ボタンのメニューを開く。メニューを使った直後に同じボタンを押すと「閉じる」扱い（トグル）になって開かないので、開かなければもう一度押す"""
    for i in range(2):
        _click_el(ed, f"#diffBar .dfSeg[data-dn='{dn}']")
        try:
            wait_until(ed, "document.getElementById('ctxmenu').style.display==='block'", timeout=2 if i == 0 else 15, label="難易度メニュー")
            return
        except AssertionError:
            if i:
                raise


def _send(ed, src, payload, dst, link=True):
    _diff_menu(ed, src)
    menu_pick(ed, payload, "→ " + dst)
    text, checked = copy_dialog(ed, link=link)
    wait_until(ed, "document.getElementById('errToast').textContent.includes('コピーしました')", label="コピーの知らせ")
    return text, checked


def test_copy_link_parent_edit_reaches_other_diff(t):
    '''Hardの「ノーツを転送→Expert」（繋ぐ・既定）: Expertのクリップは Hard のクリップの子。Hardの親に置くとExpertの子（中身・フラット・書き出し）にも入り、
    帯で知らせる（作業中1回）。Undo で子も戻る。転送も1回の Undo で全部戻る'''
    ed = open_nle(t, "rich")
    exp0 = _in(ed, EXPERT)
    text, checked = _send(ed, "Hard", "ノーツを転送", "Expert")
    t.eq(checked, True, "「親の難易度に繋ぐ」は既定でオン")
    t.ok("反映" in text, f"繋いだ時の注意（親の編集は全難易度に反映）: {text}")
    t.ok("Undoできません" not in toast(ed), "繋ぐ転送は Undo できる（全難易度の履歴）")
    h, e = _in(ed, HARD), _in(ed, EXPERT)
    t.eq((h[0]["par"], bool(h[0]["link"])), (True, True), "送り元（Hard）のクリップが親")
    t.eq([(c["link"] == h[0]["link"], c["par"]) for c in e], [(True, False)], "Expertのクリップは子")
    t.eq(_notes(e[0]), _notes(h[0]), "子の中身＝親")
    # 親（Hard・今の難易度）に置くと、他の難易度の子にも入る
    n0 = counts(ed)["notes"]
    _place(ed, 1)
    wait_until(ed, f"window._dbgApp.state().counts.notes==={n0 + 1}", label="Hardの親に置く")
    wait_until(ed, f"window._dbgApp.links().clips.find(c=>c.dk==='{EXPERT}'&&c.lk==='n').n.notes===8", label="Expertの子へ届く")
    t.eq(_flats(ed, EXPERT)["notes"], 8, "Expertのフラット（退避データ）も8")
    bd = _band(ed)
    t.ok(bd and bd["kind"] == "warn" and "Expert" in bd["text"], f"他の難易度に子がいる親を編集した帯: {bd}")
    dat = export_dat(ed)["ExpertStandard.dat"]
    t.ok(any(abs(n["b"] - 1) < 1e-6 and n["x"] == 0 and n["y"] == 2 for n in dat["colorNotes"]), "Expertの書き出しにも入る")
    ed.js("document.getElementById('lkBand').classList.remove('on')")
    _place(ed, 1.5, 1, 2)
    wait_until(ed, f"window._dbgApp.links().clips.find(c=>c.dk==='{EXPERT}'&&c.lk==='n').n.notes===9", label="2個目もExpertへ")
    ed.wait(0.3)
    t.eq(_band(ed), None, "帯はそのリンクごとに作業中1回だけ")
    _undo3d(ed); _undo3d(ed)
    wait_until(ed, f"window._dbgApp.links().clips.find(c=>c.dk==='{EXPERT}'&&c.lk==='n').n.notes===7", label="Undoで子も戻る")
    t.eq(_band(ed), None, "Undoでは帯を出さない")
    _undo3d(ed)   # 転送そのもの
    wait_until(ed, f"window._dbgApp.links().clips.filter(c=>c.link).length===0", label="転送のUndo")
    t.eq([(c["beat"], c["len"], c["n"]["notes"]) for c in _in(ed, EXPERT)], [(c["beat"], c["len"], c["n"]["notes"]) for c in exp0], "Expertは転送の前に戻る")
    t.eq(_flats(ed, EXPERT)["notes"], 23, "Expertのフラットも戻る")
    t.no_errors()


def test_copy_from_kid_links_to_its_parent(t):
    '''送り元が子なら、その親に繋ぐ: Hard→Expert（繋ぐ）の後に Expert→Normal（繋ぐ）→ Normal のクリップは Hard の親の子'''
    ed = open_nle(t, "rich")
    _send(ed, "Hard", "ノーツを転送", "Expert")
    switch_diff(ed, "Expert")
    _send(ed, "Expert", "ノーツを転送", "Normal")
    h, e, n = _in(ed, HARD), _in(ed, EXPERT), _in(ed, NORMAL)
    t.ok(n and all(c["link"] == h[0]["link"] and not c["par"] for c in n), f"Normal のクリップは Hard の親の子: {n}")
    t.eq((h[0]["par"], e[0]["par"]), (True, False), "親は Hard のまま")
    t.eq(_flats(ed, NORMAL)["notes"], 7, "Normal のフラット")
    t.no_errors()


def test_receive_link_kid_readonly_and_jump(t):
    '''Hardの「ノーツを受信←Expert」（繋ぐ）: 今の難易度（Hard）のクリップが Expert の子になり打てない（帯）。帯の［親へジャンプ］で Expert へ切り替わって親を選ぶ'''
    ed = open_nle(t, "rich")
    diff_menu_open(ed, "Hard")
    menu_pick(ed, "ノーツを受信", "← Expert")
    copy_dialog(ed)
    wait_until(ed, f"window._dbgApp.state().counts.notes===23", label="受信")
    h, e = _in(ed, HARD), _in(ed, EXPERT)
    t.ok(h[0]["link"] and h[0]["link"] == e[0]["link"] and e[0]["par"] and not h[0]["par"], "Hard が Expert の子")
    n0 = counts(ed)["notes"]
    _place(ed, 0.5, 3, 2)
    wait_until(ed, "(window._dbgApp.links().band||{}).kind==='kid'", label="子には置けない帯")
    t.eq(counts(ed)["notes"], n0, "置かれない")
    t.ok("Expert" in _band(ed)["text"], f"帯に親の難易度: {_band(ed)['text']}")
    _band_btn(ed, "親へジャンプ")
    wait_until(ed, "window._dbgApp.state().diff==='ExpertStandard.dat'", label="Expertへ切り替わる")
    wait_until(ed, f"window._dbgApp.nle().sel.includes({json.dumps(e[0]['id'])})", label="親が選ばれる")
    t.no_errors()


def test_paste_to_other_diff_asks_link_or_not(t):
    '''別の難易度でコピーしたクリップの貼り付けは毎回「繋ぐ／切る」を選ぶ: 繋ぐ→コピー元（Hard）が親・貼った物（Expert）が子。1回のUndoで両方戻る／切る→普通の貼り付け'''
    ed = open_nle(t, "rich")
    a = clips(ed, "n")[0]
    _sel(ed, [a]); nle_mouse(ed)
    ed.key("c", ctrl=True)
    switch_diff(ed, "Expert")
    for choice, linked in (("繋ぐ", True), ("切る", False)):
        ids0 = {c["id"] for c in clips(ed, "n")}
        nle_mouse(ed)
        ed.key("v", ctrl=True)
        d = _dlg(ed, "paste")
        t.ok("Hard" in d["text"] and "繋ぐ" in d["text"] and "切る" in d["text"], f"繋ぐ／切るの画面: {d['text']}")
        _dlg_btn(ed, choice)
        wait_until(ed, "!!window._dbgApp.nle().paste", label="貼り付けの追従")
        hover(ed, 4, "n", 0)
        ed.click(*clip_xy(ed, {"beat": 4, "len": 0, "lk": "n", "track": 0}))
        wait_until(ed, f"window._dbgApp.nle().clips.filter(c=>c.lk==='n').length==={len(ids0) + 1}", label=f"貼り付け（{choice}）")
        new = next(c for c in clips(ed, "n") if c["id"] not in ids0)
        nb = _by_id(ed, new["id"])
        if linked:
            hp = _in(ed, HARD)[0]
            t.ok(nb["link"] and nb["link"] == hp["link"] and hp["par"] and not nb["par"], "繋ぐ: Hard のクリップが親・貼った物が子")
            nle_mouse(ed); ed.key("z", ctrl=True)
            wait_until(ed, "window._dbgApp.links().clips.every(c=>!c.link)", label="1回のUndoで Hard のリンクも戻る")
        else:
            t.ok(not nb["link"], "切る: 繋がない")
    t.no_errors()


def test_link_same_position_in_other_diffs(t):
    '''右クリック「他の難易度の同じ位置のクリップとリンク…」: 同じ拍・レーン・長さのクリップがある難易度を選んで繋ぐ（右クリックしたクリップが親）'''
    ed = open_nle(t, "rich")
    _send(ed, "Hard", "丸ごと転送（ノーツ＋ライト）", "Easy", link=False)
    t.ok(all(not c["link"] for c in _links(ed)["clips"]), "繋がない転送")
    a = clips(ed, "n")[0]
    menu(ed, *clip_xy(ed, a), "他の難易度の同じ位置")
    d = _dlg(ed, "diffs")
    t.eq(len(d["opts"]), 1, f"同じ位置のクリップがあるのは Easy だけ（Expert は長さが違う）: {d['opts']}")
    t.ok("Easy" in d["opts"][0]["text"] and d["opts"][0]["checked"], "Easy が選ばれている")
    _dlg_btn(ed, "リンクする")
    wait_until(ed, "window._dbgApp.links().clips.filter(c=>c.link).length===2", label="Easy とリンク")
    h, ez = _in(ed, HARD), _in(ed, EASY)
    t.ok(h[0]["par"] and ez[0]["link"] == h[0]["link"] and not ez[0]["par"], "Hard が親・Easy が子")
    nle_mouse(ed); ed.key("z", ctrl=True)
    wait_until(ed, "window._dbgApp.links().clips.every(c=>!c.link)", label="Undo")
    t.no_errors()


def test_clear_refused_when_linked_and_delete_parent(t):
    '''他の難易度とリンクしている難易度は「全ノーツを削除」を断る。他の難易度に子がいる親を消すと次の親を選ぶ（Undoで全難易度が戻る）'''
    ed = open_nle(t, "rich")
    _send(ed, "Hard", "ノーツを転送", "Expert")
    _send(ed, "Hard", "ノーツを転送", "Easy")
    _hide_toast(ed)
    ed.js("window._dbg.rt.diffClear('Expert','notes')")
    wait_until(ed, "document.getElementById('errToast').textContent.includes('リンクしている')", label="全消去を断る")
    take_errors(ed, "リンクしている")
    _hide_toast(ed)
    t.eq(_flats(ed, EXPERT)["notes"], 7, "消えない")
    a = clips(ed, "n")[0]
    _sel(ed, [a]); nle_mouse(ed)
    ed.key("Delete")
    d = _dlg(ed, "parent-next")
    t.eq(len(d["opts"]), 2, f"Easy と Expert の子から選ぶ: {d['opts']}")
    t.ok("Easy" in d["opts"][0]["text"] and "Expert" in d["opts"][1]["text"], "難易度の順")
    _dlg_btn(ed, "決定")
    wait_until(ed, f"window._dbgApp.links().clips.some(c=>c.dk==='{EASY}'&&c.par)", label="Easy が次の親")
    nle_mouse(ed); ed.key("z", ctrl=True)
    wait_until(ed, f"window._dbgApp.links().clips.some(c=>c.dk==='{HARD}'&&c.lk==='n'&&c.par)", label="Undoで Hard の親が戻る")
    t.eq([c["par"] for c in _links(ed)["clips"] if c["link"] and c["dk"] != HARD], [False, False], "Easy・Expert は子に戻る（親は1つ）")
    t.no_errors()


def test_light_copy_link(t):
    '''ライトも同じ形で繋げる: 「ライティングを転送→Expert」（繋ぐ）→ Hard のライトの親を左右反転すると Expert のライトも変わる'''
    ed = open_nle(t, "rich")
    _send(ed, "Hard", "ライティングを転送", "Expert")
    hl, el = _in(ed, HARD, "l"), _in(ed, EXPERT, "l")
    t.ok(hl[0]["par"] and all(c["link"] == hl[0]["link"] and not c["par"] for c in el), "Expert のライトのクリップは Hard の子")
    menu(ed, *clip_xy(ed, clips(ed, "l")[0]), "左右反転")
    wait_until(ed, f"JSON.stringify(window._dbgApp.links().clips.find(c=>c.dk==='{EXPERT}'&&c.lk==='l').lights)==="
                   f"JSON.stringify(window._dbgApp.links().clips.find(c=>c.dk==='{HARD}'&&c.lk==='l').lights)", label="子のライト＝親")
    t.ok(_in(ed, EXPERT, "l")[0]["lights"] != el[0]["lights"], "Expert のライトが反転した")
    t.no_errors()

"""リンクしたクリップ: 「次の親を選んでください」の［キャンセル］（2026-10-20・利用者の要望）。
親が無くなった時に出る画面で［キャンセル］（Esc）を押すと、画面を出すきっかけになった操作（クリップの削除・カット・リンクの解除・
難易度間コピーで送り先の親が消えた）をまるごと取り消し、操作の前とまったく同じ状態（クリップ・中身・リンク・選択・他の難易度・クリップボード）に戻す。
取り消した操作は履歴に残さない（Ctrl+Shift+Z で復活しない）。2つのリンクで続けて画面が出る時は、どこで押しても全部を取り消す。
［決定］（Enter）は今までどおり。英語表示の文言も確かめる。
素材 rich: Hard = ノーツのクリップ 拍0〜16（ノーツ7）・ライトのクリップ 拍0〜16（ライト3）／ Expert = ノーツ23・ライト12"""
import json
import re
import sys
from pathlib import Path

for _g in ("e2e_project", "e2e_misc"):
    _P = str(Path(__file__).resolve().parents[1] / _g)
    if _P not in sys.path:
        sys.path.insert(0, _P)

from e2e_helpers import wait_until, counts, state, project, dirty   # noqa: E402
from nle_helpers import open_nle, clips, menu, nle, nle_mouse, clip_xy, undo, redo   # noqa: E402
from project_helpers import copy_dialog, menu_pick, toast   # noqa: E402
from test_clip_link import _links, _by_id, _dlg, _dlg_btn, _dlg_btn_index, _dlg_pick, _dup, _press, _sel, _hide_toast   # noqa: E402
from test_clip_link_diffs import _send, _diff_menu, HARD, EXPERT, EASY, NORMAL   # noqa: E402

JP = re.compile(r"[぀-ゟ゠-ヺー-ヿ㐀-䶿一-鿿]")


# ---- 部品 ----
def _snap(ed):
    """戻ったかを比べる状態: 全難易度のクリップ（位置・リンク・親・中身）・各難易度のフラットの数・今の難易度の3Dの数・NLE の選択・
    保存内容（buildProjectText）・未保存のランプ・履歴の数"""
    lk = _links(ed)
    st = state(ed)
    return {"clips": sorted(lk["clips"], key=lambda c: (c["dk"], c["id"])), "flats": lk["flats"], "counts": counts(ed),
            "sel": sorted(nle(ed)["sel"]), "project": project(ed), "dirty": dirty(ed), "undo": st["undo"], "redo": st["redo"]}


def _same(t, ed, before, label):
    now = _snap(ed)
    for k in before:
        t.eq(now[k], before[k], f"{label}: {k}")


def _stat(ed):
    return ed.js("document.getElementById('stat').textContent")


def _wait_cancelled(ed, text="操作を取り消しました"):
    wait_until(ed, "!document.getElementById('dirtyDlgBg')", label="画面が閉じる")
    wait_until(ed, f"document.getElementById('stat').textContent==={json.dumps(text)}", label="取り消しの知らせ")


def _three(ed):
    """今の難易度に3つのリンク（a が親・b, c が子）を作り、(a, b, c) を返す"""
    a = clips(ed, "n")[0]
    b, c = _dup(ed, a, 20), _dup(ed, a, 0)   # c は隣のレーンの拍0
    _sel(ed, [a, b]); nle_mouse(ed); ed.key("k")
    _dlg(ed, "parent-link")
    ed.key("Enter")   # 既定は先頭（拍が早い a）
    wait_until(ed, "window._dbgApp.links().clips.filter(c=>c.link).length===2", label="a と b をリンク")
    _sel(ed, [b, c]); nle_mouse(ed); ed.key("k")   # c を a のリンクの子に加える（中身が同じなので確認なし）
    wait_until(ed, "window._dbgApp.links().clips.filter(c=>c.link).length===3", label="c も子に")
    return a, b, c


def _redo_noop(t, ed, before, label):
    """取り消した操作はやり直しの列に無い: Ctrl+Shift+Z は何もしない"""
    nle_mouse(ed)
    redo(ed)
    wait_until(ed, "document.getElementById('stat').textContent.includes('やり直す操作がありません')", label=f"{label}: やり直す操作が無い")
    _same(t, ed, before, f"{label}: Ctrl+Shift+Z の後")


def _undo_redo_round(t, ed, before, label):
    """Undo → Redo で操作の前に戻る（取り消した操作は Undo にも Redo にも出てこない）"""
    nle_mouse(ed)
    undo(ed)
    wait_until(ed, f"window._dbgApp.state().undo==={before['undo'] - 1}", label=f"{label}: Undo")
    redo(ed)
    wait_until(ed, f"window._dbgApp.state().undo==={before['undo']}", label=f"{label}: Redo")
    _same(t, ed, before, f"{label}: Undo→Redo の後")


# ---- テスト ----
def test_delete_parent_cancel_restores_all_diffs(t):
    '''他の難易度（Expert・Easy）に子がいる Hard の親を Delete → 次の親の画面（［決定］［キャンセル］）→［キャンセル］で、
    Hard のクリップ・全難易度のリンクと中身・フラット・選択・保存内容・履歴の数まで操作の前と同じ。Ctrl+Shift+Z で削除は復活しない。Undo→Redo も前の状態のまま'''
    ed = open_nle(t, "rich")
    _send(ed, "Hard", "ノーツを転送", "Expert")
    _send(ed, "Hard", "ノーツを転送", "Easy")
    _hide_toast(ed)
    a = clips(ed, "n")[0]
    _sel(ed, [a]); nle_mouse(ed)
    before = _snap(ed)
    t.ok(_by_id(ed, a["id"])["par"], "Hard のクリップが親")
    ed.key("Delete")
    d = _dlg(ed, "parent-next")
    t.eq(d["btns"], ["決定", "キャンセル"], "ボタン（主のボタン・キャンセルの順＝他の確認の画面と同じ）")
    t.ok("次の親を選んでください" in d["text"], f"題: {d['text']}")
    t.ok(not any(c["id"] == a["id"] for c in _links(ed)["clips"]), "画面が出ている間は消えている")
    _dlg_btn(ed, "キャンセル")
    _wait_cancelled(ed)
    _same(t, ed, before, "キャンセル")
    t.eq((_by_id(ed, a["id"])["par"], [c["par"] for c in _links(ed)["clips"] if c["link"] and c["dk"] != HARD]), (True, [False, False]),
         "Hard が親・Easy と Expert は子のまま")
    _redo_noop(t, ed, before, "削除のキャンセル")
    _undo_redo_round(t, ed, before, "削除のキャンセル")
    t.no_errors()


def test_esc_cancel_menu_delete_and_enter_decides(t):
    '''右クリック「クリップを削除」で親を消す → 次の親の画面で Esc ＝キャンセル（選択も右クリックの前へ）。
    もう一度消して Enter ＝［決定］（今までどおり先頭が次の親・Undo で元に戻る）'''
    ed = open_nle(t, "rich")
    a, b, c = _three(ed)
    _sel(ed, [_by_id(ed, b["id"])])   # 選択は b（右クリックするのは a）
    before = _snap(ed)
    menu(ed, *clip_xy(ed, _by_id(ed, a["id"])), "クリップを削除")
    _dlg(ed, "parent-next")
    t.eq(len([x for x in _links(ed)["clips"] if x["link"]]), 2, "画面が出ている間は a が消えている")
    ed.key("Escape")
    _wait_cancelled(ed)
    _same(t, ed, before, "Esc")
    t.eq([_by_id(ed, x["id"])["par"] for x in (a, b, c)], [True, False, False], "a が親に戻る")
    _redo_noop(t, ed, before, "Esc")
    # Enter＝決定（今までどおり）
    _sel(ed, [_by_id(ed, a["id"])]); nle_mouse(ed)
    u0 = state(ed)["undo"]
    ed.key("Delete")
    d = _dlg(ed, "parent-next")
    first = d["opts"][0]["text"]
    ed.key("Enter")
    wait_until(ed, "!document.getElementById('dirtyDlgBg')", label="決定で閉じる")
    wait_until(ed, "window._dbgApp.links().clips.filter(c=>c.par).length===1", label="次の親が決まる")
    par = next(x for x in _links(ed)["clips"] if x["par"])
    t.ok(par["id"] in (b["id"], c["id"]) and f"拍 {int(par['beat'])}〜" in first, f"先頭の候補が次の親: {first}")
    t.eq(state(ed)["undo"], u0 + 1, "決定した削除は履歴に1つ")
    t.ok("操作を取り消しました" not in _stat(ed), "決定では取り消さない")
    undo(ed)
    wait_until(ed, f"(x=>x&&x.par)(window._dbgApp.links().clips.find(c=>c.id==={json.dumps(a['id'])}))", label="Undo で a が親に戻る")
    t.no_errors()


def test_unlink_parent_cancel(t):
    '''親の右クリック「リンクを解除」→ 次の親の画面 →［キャンセル］で、解除の前（a が親・b, c が子）に戻る。解除は履歴に残らない'''
    ed = open_nle(t, "rich")
    a, b, c = _three(ed)
    before = _snap(ed)
    menu(ed, *clip_xy(ed, _by_id(ed, a["id"])), "リンクを解除")
    _dlg(ed, "parent-next")
    t.ok(not _by_id(ed, a["id"])["link"], "画面が出ている間は a のリンクが外れている")
    _dlg_btn(ed, "キャンセル")
    _wait_cancelled(ed)
    _same(t, ed, before, "解除のキャンセル")
    t.eq([(bool(_by_id(ed, x["id"])["link"]), _by_id(ed, x["id"])["par"]) for x in (a, b, c)], [(True, True), (True, False), (True, False)], "リンクと親が元どおり")
    _redo_noop(t, ed, before, "解除のキャンセル")
    _undo_redo_round(t, ed, before, "解除のキャンセル")
    t.no_errors()


def test_two_links_cancel_on_first_or_second(t):
    '''Hard のノーツとライトの親（どちらも Expert・Easy に子）を一緒に消す → 次の親の画面が2回続けて出る。
    1つ目でキャンセル → 全部戻る（2つ目は出ない）。1つ目を決定して2つ目でキャンセル → 1つ目の決定も含めて全部戻る'''
    ed = open_nle(t, "rich")
    _send(ed, "Hard", "丸ごと転送（ノーツ＋ライト）", "Expert")
    _send(ed, "Hard", "丸ごと転送（ノーツ＋ライト）", "Easy")
    _hide_toast(ed)
    n0, l0 = clips(ed, "n")[0], clips(ed, "l")[0]
    t.ok(_by_id(ed, n0["id"])["par"] and _by_id(ed, l0["id"])["par"], "ノーツとライトのクリップがそれぞれ親")
    _sel(ed, [n0, l0]); nle_mouse(ed)
    before = _snap(ed)
    # 1つ目でキャンセル
    ed.key("Delete")
    _dlg(ed, "parent-next")
    _dlg_btn(ed, "キャンセル")
    _wait_cancelled(ed)
    ed.wait(0.3)
    t.ok(not ed.js("!!document.getElementById('dirtyDlgBg')"), "2つ目の画面は出ない")
    _same(t, ed, before, "1つ目でキャンセル")
    # 1つ目を決定・2つ目でキャンセル
    nle_mouse(ed)   # キーの効き先を NLE に（キャンセルのボタンを押したマウスは 3D の上）
    ed.key("Delete")
    _dlg(ed, "parent-next")
    _dlg_pick(ed, 1)   # 2番目の候補（Expert）を次の親に
    ed.js("document.getElementById('dirtyDlg').dataset.seen='1';true")   # 2つ目の画面はすぐ続けて出る（閉じた瞬間を待てない）＝印の無い画面を待つ
    _press(ed, f"#dirtyDlg .ddBtns button:nth-child({_dlg_btn_index(ed, '決定') + 1})")
    wait_until(ed, "!!document.querySelector('#dirtyDlg[data-lk=\"parent-next\"]:not([data-seen]) .ddBtns button')", label="2つ目の次の親の画面")
    d2 = _dlg(ed, "parent-next")
    t.eq(len(d2["opts"]), 2, "2つ目の画面（もう1つのリンク）")
    t.eq(len([c for c in _links(ed)["clips"] if c["par"]]), 1, "2つ目の画面の間は、1つ目で決めた親だけがある")
    _dlg_btn(ed, "キャンセル")
    _wait_cancelled(ed)
    _same(t, ed, before, "2つ目でキャンセル")
    t.eq(sorted(c["dk"] for c in _links(ed)["clips"] if c["par"]), [HARD, HARD], "親はどちらも Hard に戻る（1つ目の決定も取り消す）")
    _redo_noop(t, ed, before, "2つ目でキャンセル")
    t.no_errors()


def test_receive_copy_cancel(t):
    '''Hard の親（子は Easy・Normal）がある時に「ノーツを受信←Expert」→ 送り先（Hard）の親が消えて次の親の画面 →［キャンセル］で、
    受信をまるごと取り消す（Hard の中身・Expert に付いたリンク・Easy・Normal の子まで）。「コピーしました」の知らせも置き換える'''
    ed = open_nle(t, "rich")
    _send(ed, "Hard", "ノーツを転送", "Easy")
    _send(ed, "Hard", "ノーツを転送", "Normal")
    _hide_toast(ed)
    before = _snap(ed)
    _diff_menu(ed, "Hard")
    menu_pick(ed, "ノーツを受信", "← Expert")
    copy_dialog(ed)   # 繋ぐ（既定）
    _dlg(ed, "parent-next")
    t.eq(counts(ed)["notes"], 23, "画面が出ている間は Hard が Expert の中身")
    t.ok("コピーしました" in toast(ed), f"コピーの知らせ: {toast(ed)}")
    _dlg_btn(ed, "キャンセル")
    _wait_cancelled(ed)
    _same(t, ed, before, "受信のキャンセル")
    t.ok(not any(c["link"] for c in _links(ed)["clips"] if c["dk"] == EXPERT), "Expert のクリップにリンクは付かない")
    t.eq(toast(ed), "✅ 操作を取り消しました", "知らせも置き換わる")
    _redo_noop(t, ed, before, "受信のキャンセル")
    t.no_errors()


def test_cut_parent_cancel_restores_clipboard(t):
    '''Hard の親（子は Expert・Easy）を Ctrl+X でカット → 次の親の画面 →［キャンセル］で、クリップが戻り、クリップボードもカットの前（空）に戻る'''
    ed = open_nle(t, "rich")
    _send(ed, "Hard", "ノーツを転送", "Expert")
    _send(ed, "Hard", "ノーツを転送", "Easy")
    _hide_toast(ed)
    a = clips(ed, "n")[0]
    _sel(ed, [a]); nle_mouse(ed)
    before = _snap(ed)
    ed.key("x", ctrl=True)
    _dlg(ed, "parent-next")
    _dlg_btn(ed, "キャンセル")
    _wait_cancelled(ed)
    _same(t, ed, before, "カットのキャンセル")
    nle_mouse(ed)
    ed.key("v", ctrl=True)
    wait_until(ed, "document.getElementById('stat').textContent.includes('クリップボードが空です')", label="クリップボードはカットの前（空）")
    t.ok(not nle(ed)["paste"], "貼り付けの追従は始まらない")
    t.no_errors()


def test_next_parent_cancel_english(t):
    '''英語表示: 次の親の画面の題・ボタン（OK・Cancel）と、取り消しの知らせ（Operation cancelled）。日本語が出ない'''
    from english_ui_helpers import start_english, found
    ed = start_english(t, "basic")
    wait_until(ed, "window._dbgApp.nle().clips.some(c=>c.lk==='n')", label="素材の読込")
    a = clips(ed, "n")[0]
    b, c = _dup(ed, a, a["beat"] + a["len"]), _dup(ed, a, a["beat"])   # b は a の直後・c は隣のレーン
    _sel(ed, [a, b]); nle_mouse(ed); ed.key("k")
    _dlg(ed, "parent-link")
    ed.key("Enter")
    wait_until(ed, "window._dbgApp.links().clips.filter(c=>c.link).length===2", label="リンク")
    _sel(ed, [_by_id(ed, b["id"]), c]); nle_mouse(ed); ed.key("k")
    wait_until(ed, "window._dbgApp.links().clips.filter(c=>c.link).length===3", label="3つのリンク")
    par = next(x for x in _links(ed)["clips"] if x["par"])
    _sel(ed, [par]); nle_mouse(ed)
    ed.key("Delete")
    d = _dlg(ed, "parent-next")
    t.eq(d["btns"], ["OK", "Cancel"], "ボタン")
    t.ok(d["text"].startswith("Choose the next parent"), f"題: {d['text']}")
    t.eq(JP.findall(d["text"]), [], f"画面に日本語が無い: {d['text']}")
    ed.key("Escape")
    _wait_cancelled(ed, "Operation cancelled")
    t.eq(len([x for x in _links(ed)["clips"] if x["link"]]), 3, "リンクが戻る")
    t.eq([s for s, _ in found(ed)], [], "日本語が出ない")
    t.no_errors()

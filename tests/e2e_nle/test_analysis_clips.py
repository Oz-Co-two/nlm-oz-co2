"""解析からクリップを作る（2026-10-19・確認の画面は js/analysis/ana-clips.js・作るのは editor-app.js の anaOpenClips/anaMakeClips）。
仕様（利用者と決めた物）: 解析の帯の右クリック／溝の「⋯」に「クリップを作る…」。単位＝セクション（既定）／細かい区切り／両方、作る難易度
（開いている難易度は必ず）、同じ番号の自動リンク（既定オン）を選ぶ。新しいノーツのレーンを一番上に足し（両方なら2本・上がセクション）、
帯の区間どおりの空のクリップ（名前＝「<帯の名前> S<番号>」・色＝帯の色）を作って、そのレーンを単独編集にする。親＝各番号の一番先頭
（開いている難易度）・他の難易度の分もその親に繋ぐ。Ctrl+Z 1回で全部戻る（単独編集は履歴に積まない＝オフになる）。解析し直しても作った物はそのまま。
解析の応答は偽物（tests/_lib/analysis_helpers.py）。素材 basic＝Hard だけ・BPM 120・32拍・ノーツのレーン3本（Notes 1 に Sheet）、rich＝Hard と Expert"""
import json
import re

from analysis_helpers import (STRUCT, TEMPO_SAME, ana_mock, click_sel, clips_dialog, clips_ok, clips_pick, open_clips, run_analysis,
                              start_from_menu, wait_clips_dialog)
from e2e_helpers import cell, counts, hover_3d, project, switch_diff, wait_until
from nle_helpers import nle, nle_mouse, open_nle, redo, take_errors, undo
from test_clip_link import _band, _links, _seek

HARD, EXPERT, EASY = "hardstandard.dat", "expertstandard.dat", "easystandard.dat"
SPAL = ['#5b6c8f', '#8f6b5b', '#5b8f78']                       # 帯のセクションの色（song-analysis.js の SPAL・番号の出た順）
PAL = ['#e4572e', '#4c9be8', '#f2b134', '#3fb37f', '#a66fd6']    # 細かい区切りの色（PAL・グループの出た順）
SECS = [(0, 8, "イントロ S1", SPAL[0]), (8, 8, "Aメロ S2", SPAL[1]), (16, 8, "サビ S3", SPAL[2]), (24, 8, "Aメロ S2", SPAL[1])]
SEGS = [(0, 4, "A", PAL[0]), (4, 4, "B", PAL[1]), (8, 4, "C", PAL[2]), (12, 4, "D", PAL[3]),
        (16, 4, "E", PAL[4]), (20, 4, "E", PAL[4]), (24, 4, "C", PAL[2]), (28, 4, "D", PAL[3])]


def _open(t, fx="basic"):
    ed = open_nle(t, fx)
    wait_until(ed, "!document.getElementById('bootCover')&&window._dbgApp.analysis().startBtn", label="［曲を解析］が出る")
    return ed


def _toast(ed):
    return ed.js("(e=>e.style.display==='none'?'':e.textContent)(document.getElementById('errToast'))")


def _clear_toast(ed):
    ed.js("(e=>{e.style.display='none'; e.textContent=''; return 1})(document.getElementById('errToast'))")


def _lane(ed, track, lk="n", dk=None):
    """レーン track のクリップ（拍順）。dk＝難易度（省略＝今の難易度）"""
    cs = [c for c in _links(ed)["clips"] if c["lk"] == lk and c["track"] == track and (c["cur"] if dk is None else c["dk"] == dk)]
    return sorted(cs, key=lambda c: c["beat"])


def _shape(cs):
    return [(c["beat"], c["len"], c["label"], c["colHex"]) for c in cs]


def _clip_set(ed):
    """全難易度のクリップ（リンクの id は除く。比べる用）"""
    return sorted((c["dk"], c["lk"], c["track"], c["beat"], c["len"], c["label"], bool(c["link"]), c["par"], json.dumps(c["n"], sort_keys=True))
                  for c in _links(ed)["clips"])


def _groups(cs):
    """リンクごとの [(難易度, 拍, 親か)]（拍順）"""
    g = {}
    for c in cs:
        if c["link"]:
            g.setdefault(c["link"], []).append((c["dk"], c["beat"], c["par"]))
    return sorted(sorted(v) for v in g.values())


def _place(ed, beat, x=0, y=2):
    """配置モードで拍 beat・マス(x,y) をクリックする（再生ヘッドを beat へ動かしてから）"""
    _seek(ed, beat)
    hover_3d(ed)
    p = cell(ed, x, y)
    ed.move(p["x"], p["y"]); ed.wait(0.15)
    ed.click(p["x"], p["y"])


def test_clips_sections_link_edit_only_and_undo(t):
    '''帯のセクションの右クリック「クリップを作る…」→ 確認の画面（既定＝セクション・開いている難易度は必ず・自動リンクはオン・まとめ）→［作る］:
    一番上に新しいノーツのレーン・帯の区間どおりの空のクリップ（名前＝名前＋番号・色＝帯の色）・同じ番号の S2 はリンク（親＝先頭）・今あるクリップは1段下へ
    （中身はそのまま）・そのレーンを単独編集・未保存のランプ。親に置くと子にも入り、子には置けない。Ctrl+Z 1回で全部戻る（単独編集もオフ）'''
    ed = _open(t)
    run_analysis(ed, "none")
    before = _clip_set(ed)
    lanes0 = nle(ed)["lanes"]
    undo0 = ed.js("window._dbgApp.state().undo")
    items = open_clips(ed, via="band")
    t.eq(items[:3], ["S2「Aメロ」の名前を付け直す…", "クリップを作る…", "セクションの頭にマーカーを書き出す"], "帯のセクションの右クリックのメニュー")
    wait_clips_dialog(ed)
    d = clips_dialog(ed)
    t.eq(d["title"], "解析からクリップを作る", "題")
    t.eq([(u["v"], u["checked"], u["dis"]) for u in d["units"]], [("sec", True, False), ("seg", False, False), ("both", False, False)], "単位（既定＝セクション）")
    t.eq([u["text"] for u in d["units"]],
         ["セクション（4個・番号 3種類）\nクリップ名＝名前＋番号（例「イントロ S1」）・同じ番号は同じ色",
          "細かい区切り（8個・グループ 5種類）\nクリップ名＝グループ名（例「A」）・同じグループは同じ色",
          "両方（それぞれ別の新しいレーンに）\n上のレーン＝セクション・その下＝細かい区切り"], "単位の文")
    t.eq([(e["v"], e["checked"], e["dis"]) for e in d["eo"]], [("sec", True, True), ("seg", False, True)], "単独編集にするレーンは両方の時だけ選べる")
    t.eq([(x["text"], x["checked"], x["dis"]) for x in d["diffs"]],
         [("Easy\n空", False, False), ("Normal\n空", False, False), ("Hard\n開いている難易度", True, True), ("Expert\n空", False, False), ("Expert+\n空", False, False)],
         "作る難易度（開いている難易度は必ず）")
    t.eq(d["diffs"][2]["tip"], "開いている難易度には必ず作ります", "開いている難易度のツールチップ")
    t.eq((d["link"], d["warn"]), (True, True), "自動リンクは既定でオン・親の編集の注意")
    t.eq(d["sum"], "作る物: 新しいノーツのレーン 1本・クリップ 4個 × 1難易度・リンク 1組", "まとめ（S2 が2回＝リンク1組）")
    t.eq(d["btns"], ["作る", "キャンセル"], "ボタン")
    clips_ok(ed)
    wait_until(ed, f"window._dbgApp.nle().lanes.n==={lanes0['n'] + 1}", label="レーンが1本増える")
    new = _lane(ed, 0)
    t.eq(_shape(new), SECS, "一番上のレーンに帯の区間どおりのクリップ（名前＝名前＋番号・色＝帯の色）")
    t.ok(all(not any(c["n"].values()) for c in new), "中身は空")
    t.eq([(bool(c["link"]), c["par"]) for c in new], [(False, False), (True, True), (False, False), (True, False)], "S2 の2つをリンク（親＝先頭）・1回だけの番号はリンクしない")
    t.eq(new[1]["link"], new[3]["link"], "同じリンク")
    old = sorted((dk, lk, tr, b, ln, lb, k, p, n) for dk, lk, tr, b, ln, lb, k, p, n in _clip_set(ed) if lb not in ("イントロ S1", "Aメロ S2", "サビ S3"))
    t.eq(old, sorted((dk, lk, tr + (1 if lk == "n" else 0), b, ln, lb, k, p, n) for dk, lk, tr, b, ln, lb, k, p, n in before),
         "今あるノーツのクリップは1段下へ（中身はそのまま）・ライトは変わらない")
    g = nle(ed)
    t.eq((g["editOnly"], g["lanes"]["l"]), (0, lanes0["l"]), "作ったレーンを単独編集")
    t.eq(ed.js("document.querySelector('#eoInd .eoIndMain').textContent"), "✎ 単独編集: Notes 4", "3Dの隅の表示")
    t.eq(_toast(ed), "✅ Notes 4 にクリップを 4 個作りました・リンク 1組。Notes 4 を単独編集にしました（Ctrl+Z で戻せます）", "知らせ")
    t.eq(ed.js("window._dbgApp.state().undo"), undo0 + 1, "履歴は1つ")
    wait_until(ed, "window._dbgApp.dirty().lamp", label="未保存のランプ")
    # 親（拍8〜16）に置く → 子（拍24〜32）にも入る。子には置けない
    n0 = counts(ed)["notes"]
    _place(ed, 9)
    wait_until(ed, f"window._dbgApp.state().counts.notes==={n0 + 2}", label="親に置く（子の写しも増える）")
    t.eq([c["n"]["notes"] for c in _lane(ed, 0)], [0, 1, 0, 1], "親と子に1つずつ")
    t.eq(_lane(ed, 0)[3]["notes"], _lane(ed, 0)[1]["notes"], "子の中身＝親")
    _place(ed, 27, 3, 0)
    wait_until(ed, "(window._dbgApp.links().band||{}).kind==='kid'", label="子には置けない帯")
    t.eq(counts(ed)["notes"], n0 + 2, "置かれない")
    ed.js("document.getElementById('lkBand').classList.remove('on')")
    hover_3d(ed); ed.key("z", ctrl=True)
    wait_until(ed, f"window._dbgApp.state().counts.notes==={n0}", label="置いた物の Undo")
    nle_mouse(ed); undo(ed)
    wait_until(ed, f"window._dbgApp.nle().lanes.n==={lanes0['n']}", label="Ctrl+Z 1回でレーンが戻る")
    t.eq(_clip_set(ed), before, "クリップも全部戻る")
    t.eq(nle(ed)["editOnly"], None, "単独編集はオフ（履歴に積まない）")
    t.no_errors()


def test_clips_segments_without_link(t):
    '''「⋯」→「クリップを作る…」→ 細かい区切り・自動リンクを切る: グループ名のクリップ（色＝帯の色）・リンクなし（まとめ・注意も）'''
    ed = _open(t)
    run_analysis(ed, "none")
    items = open_clips(ed)
    t.eq(items[0], "クリップを作る…", "⋯ のメニューの先頭")
    wait_clips_dialog(ed)
    clips_pick(ed, unit="seg", link=False)
    d = clips_dialog(ed)
    t.eq((d["link"], d["warn"], d["sum"]), (False, False, "作る物: 新しいノーツのレーン 1本・クリップ 8個 × 1難易度・リンクなし"), "リンクなしのまとめ（注意は隠れる）")
    clips_ok(ed)
    wait_until(ed, "window._dbgApp.nle().editOnly===0", label="作ったレーンを単独編集")
    new = _lane(ed, 0)
    t.eq(_shape(new), SEGS, "細かい区切りどおりのクリップ（名前＝グループ・色＝帯の色）")
    t.ok(not any(c["link"] for c in new), "リンクしない")
    t.eq(_toast(ed), "✅ Notes 4 にクリップを 8 個作りました。Notes 4 を単独編集にしました（Ctrl+Z で戻せます）", "知らせ")
    t.no_errors()


def test_clips_both_choose_edit_only_lane(t):
    '''両方: 2本のレーン（上＝セクション・下＝細かい区切り）・単独編集にするレーン（打つ方）を細かい区切りに・同じ番号／グループをそれぞれリンク'''
    ed = _open(t)
    run_analysis(ed, "none")
    lanes0 = nle(ed)["lanes"]["n"]
    open_clips(ed)
    wait_clips_dialog(ed)
    clips_pick(ed, unit="both")
    d = clips_dialog(ed)
    t.eq([(e["v"], e["checked"], e["dis"]) for e in d["eo"]], [("sec", True, False), ("seg", False, False)], "両方＝単独編集にするレーンを選べる（既定＝セクション）")
    t.eq(d["sum"], "作る物: 新しいノーツのレーン 2本・クリップ 12個 × 1難易度・リンク 4組", "まとめ（S2・C・D・E）")
    clips_pick(ed, eo="seg")
    clips_ok(ed)
    wait_until(ed, f"window._dbgApp.nle().lanes.n==={lanes0 + 2}", label="レーンが2本増える")
    t.eq(_shape(_lane(ed, 0)), SECS, "上のレーン＝セクション")
    t.eq(_shape(_lane(ed, 1)), SEGS, "その下＝細かい区切り")
    t.eq(_groups(_lane(ed, 0) + _lane(ed, 1)),
         [[(HARD, 8, True), (HARD, 24, False)], [(HARD, 8, True), (HARD, 24, False)], [(HARD, 12, True), (HARD, 28, False)], [(HARD, 16, True), (HARD, 20, False)]],
         "リンク4組（親＝先頭）")
    t.eq(nle(ed)["editOnly"], 1, "細かい区切りのレーンを単独編集")
    t.eq(_toast(ed), f"✅ Notes {lanes0 + 2}・Notes {lanes0 + 1} にクリップを 12 個作りました・リンク 4組。Notes {lanes0 + 1} を単独編集にしました（Ctrl+Z で戻せます）", "知らせ")
    t.no_errors()


def test_clips_other_diffs_undo_redo(t):
    '''他の難易度にも作る（rich: Hard を開いて Easy＝無い難易度・Expert＝譜面あり）: 全部の難易度に同じクリップ・親は全部開いている難易度（Hard）・
    Expert の今のクリップは2段下へ（中身・フラットはそのまま）。親に置くと他の難易度の子にも入る。Ctrl+Z 1回で全部戻り（Easy も無くなる）、やり直しで戻る'''
    ed = _open(t, "rich")
    run_analysis(ed, "none")
    before = _clip_set(ed)
    flats0 = _links(ed)["flats"]
    open_clips(ed)
    wait_clips_dialog(ed)
    d = clips_dialog(ed)
    t.eq([x["text"] for x in d["diffs"]], ["Easy\n空", "Normal\n空", "Hard\n開いている難易度", "Expert\nノーツ 25", "Expert+\n空"], "難易度（ノーツの数）")
    clips_pick(ed, unit="both", diffs=(EASY, EXPERT))
    t.eq(clips_dialog(ed)["sum"], "作る物: 新しいノーツのレーン 2本・クリップ 12個 × 3難易度・リンク 8組", "まとめ（3難易度＝1回だけの番号もリンク）")
    clips_ok(ed)
    wait_until(ed, "window._dbgApp.nle().lanes.n===5", label="レーンが2本増える")
    t.eq(_toast(ed), "✅ Notes 5・Notes 4 にクリップを 12 個ずつ作りました（Easy・Hard・Expert）・リンク 8組。Notes 5 を単独編集にしました（Ctrl+Z で戻せます）", "知らせ")
    for dk in (EASY, HARD, EXPERT):
        t.eq((_shape(_lane(ed, 0, dk=dk)), _shape(_lane(ed, 1, dk=dk))), (SECS, SEGS), f"{dk} にも同じクリップ")
    made = [c for c in _links(ed)["clips"] if c["lk"] == "n" and c["track"] in (0, 1)]
    t.ok(all(c["link"] for c in made), "1回だけの番号も他の難易度とリンク")
    t.eq(sorted({c["dk"] for c in made if c["par"]}), [HARD], "親は全部 Hard")
    t.eq(len({c["link"] for c in made}), 8, "リンク8組")
    t.eq(sorted(len(g) for g in _groups(made)), [3, 3, 3, 3, 6, 6, 6, 6], "各リンク＝各難易度の同じ番号（1回の S1・S3・A・B は3つ、2回ある S2・C・D・E は6つ）")
    ex = [c for c in _links(ed)["clips"] if c["dk"] == EXPERT and c["lk"] == "n" and c["track"] == 2]
    t.eq([(c["beat"], c["n"]["notes"]) for c in ex], [(c[3], json.loads(c[8])["notes"]) for c in before if c[0] == EXPERT and c[1] == "n"], "Expert の今のクリップは2段下へ（中身そのまま）")
    t.eq({k: v for k, v in _links(ed)["flats"].items() if k != EASY}, flats0, "フラットの数は変わらない")
    # 親（Hard・拍8〜16の S2）に置く → Expert・Easy の子にも入る
    _place(ed, 9)
    wait_until(ed, f"window._dbgApp.links().clips.filter(c=>c.track===0&&c.label==='Aメロ S2'&&c.n.notes===1).length===6", label="全難易度の S2 へ届く")
    t.eq(_links(ed)["flats"][EXPERT]["notes"], flats0[EXPERT]["notes"] + 2, "Expert のフラットにも（S2 が2つ）")
    ed.js("document.getElementById('lkBand').classList.remove('on')")
    hover_3d(ed); ed.key("z", ctrl=True)
    wait_until(ed, "window._dbgApp.links().clips.every(c=>c.label!=='Aメロ S2'||c.n.notes===0)", label="置いた物の Undo")
    nle_mouse(ed); undo(ed)
    wait_until(ed, "window._dbgApp.nle().lanes.n===3", label="Ctrl+Z 1回でレーンが戻る")
    t.eq(_clip_set(ed), before, "全難易度のクリップが戻る（作った Easy も無くなる）")
    t.eq(_links(ed)["flats"], flats0, "フラットも戻る")
    nle_mouse(ed); redo(ed)
    wait_until(ed, "window._dbgApp.nle().lanes.n===5", label="やり直し")
    t.eq((_shape(_lane(ed, 0, dk=EASY)), _shape(_lane(ed, 1, dk=EASY))), (SECS, SEGS), "やり直しで Easy のクリップも戻る")
    t.eq(len({c["link"] for c in _links(ed)["clips"] if c["link"]}), 8, "リンクも戻る")
    switch_diff(ed, "Easy")
    t.eq(_shape(_lane(ed, 0)), SECS, "Easy を開くと子のクリップ")
    t.no_errors()


def test_clips_save_reopen_and_reanalyze(t):
    '''解析し直しても（番号の振り方が変わっても）作ったクリップはそのまま。作ったクリップ・リンク・単独編集は保存され、開き直すと戻る（リンクは外れない）'''
    ed = _open(t, "rich")
    run_analysis(ed, "none")
    open_clips(ed)
    wait_clips_dialog(ed)
    clips_pick(ed, diffs=(EXPERT,))
    clips_ok(ed)
    wait_until(ed, "window._dbgApp.nle().editOnly===0", label="作った")
    made = _clip_set(ed)
    links0 = _groups(_links(ed)["clips"])
    # 解析し直す（S2 と S3 の番号を入れ替えた結果）→ 帯は変わるが作ったクリップはそのまま
    st2 = json.loads(json.dumps(STRUCT))
    for sec in st2["sections"]:
        sec["label"] = {"S2": "S3", "S3": "S2"}.get(sec["label"], sec["label"])
    ana_mock(ed, tempo=TEMPO_SAME, structure=st2)
    start_from_menu(ed)
    wait_until(ed, "(a=>!a.running&&a.labels[1]==='Aメロ S3')(window._dbgApp.analysis())", label="解析し直した帯")
    t.eq(_clip_set(ed), made, "作ったクリップはそのまま")
    # 保存して開き直す（音源は読み込み直さない）
    pj = project(ed)
    t.eq(pj["laneStates"].get("editOnly"), 0, "単独編集も保存")
    ed.js(f"(async()=>{{ await window._dbg.rt.applyProject({json.dumps(pj, ensure_ascii=False)}); return 1; }})()")
    wait_until(ed, "window._dbgApp.analysis().shown&&window._dbgApp.nle().lanes.n===4", label="開き直す")
    t.eq(_clip_set(ed), made, "クリップ・リンクが戻る")
    t.eq(_groups(_links(ed)["clips"]), links0, "リンクの組も同じ（開いた時の点検で外れない）")
    t.eq(_band(ed), None, "リンクを外した知らせは出ない")
    t.eq(nle(ed)["editOnly"], 0, "単独編集も戻る")
    t.no_errors()


def test_clips_refused_and_cancel(t):
    '''断る時: 結果が無い・目盛りが変わった（解析し直しが要る）・ノーツのレーンが上限（10本）。9本なら「両方」は選べない（理由つき）。
    Esc で閉じれば何も変わらない。画面を出している間に解析し直しが終わって結果が変わったら作らない'''
    ed = _open(t)
    ed.js("window._dbg.rt.anaOpenClips()")
    t.eq(_toast(ed), "⚠ 構成の解析の結果がありません。先に［曲を解析］を押してください", "結果が無い")
    take_errors(ed, "構成の解析の結果がありません")
    run_analysis(ed, "none")
    lanes0 = nle(ed)["lanes"]["n"]
    undo0 = ed.js("window._dbgApp.state().undo")
    # 目盛りが変わった
    click_sel(ed, "#bpmField .bfA[data-k=up]")
    wait_until(ed, "window._dbgApp.analysis().stale", label="目盛りが変わった")
    _clear_toast(ed)
    open_clips(ed)
    wait_until(ed, "document.getElementById('errToast').style.display!=='none'", label="断りの知らせ")
    t.eq(_toast(ed), "⚠ 目盛り（BPM・無音追加・テンポパート・Music の配置）が解析した時と変わったため、帯の区間が今の拍と合っていない可能性があります。解析し直してからクリップを作ってください",
         "目盛りが変わった")
    t.eq(clips_dialog(ed), None, "画面は出ない")
    take_errors(ed, "目盛り（BPM")
    click_sel(ed, "#bpmField .bfA[data-k=dn]")
    wait_until(ed, "!window._dbgApp.analysis().stale", label="目盛りを戻す")
    # Esc
    open_clips(ed)
    wait_clips_dialog(ed)
    ed.key("Escape")
    wait_until(ed, "!document.querySelector('#dirtyDlg[data-ana=clips]')", label="Esc で閉じる")
    t.eq((nle(ed)["lanes"]["n"], ed.js("window._dbgApp.state().undo")), (lanes0, undo0), "何も変わらない")
    # 画面を出している間に結果が変わった（裏で解析し直しが終わった）
    open_clips(ed)
    wait_clips_dialog(ed)
    st2 = json.loads(json.dumps(STRUCT))
    st2["sections"][0]["end"] = 4
    st2["sections"].insert(1, {"start": 4, "end": 8, "label": "S9", "count": 1, "chorus": False, "name": ""})
    ana_mock(ed, tempo=TEMPO_SAME, structure=st2)
    ed.js("document.querySelector('#mFileMenu button[data-act=analyze]').click();true")
    wait_until(ed, "(a=>!a.running&&a.labels.length===5)(window._dbgApp.analysis())", label="裏で解析し直す")
    _clear_toast(ed)
    clips_ok(ed)
    t.eq(_toast(ed), "⚠ 画面を出している間に解析の結果が変わったため、クリップを作りませんでした。もう一度［クリップを作る…］を押してください", "結果が変わった")
    take_errors(ed, "画面を出している間に")
    t.eq(nle(ed)["lanes"]["n"], lanes0, "作らない")
    # レーンが9本＝「両方」は選べない・10本＝断る
    for _ in range(9 - lanes0):
        ed.js("window._dbg.rt.laneAdd('n');true")
    open_clips(ed)
    wait_clips_dialog(ed)
    d = clips_dialog(ed)
    t.eq((d["units"][2]["dis"], d["units"][2]["text"].split("\n")[-1]), (True, "ノーツのレーンが足りません（上限 10本・あと 1本）"), "9本＝両方は選べない（理由）")
    ed.key("Escape")
    ed.js("window._dbg.rt.laneAdd('n');true")
    _clear_toast(ed)
    open_clips(ed)
    wait_until(ed, "document.getElementById('errToast').style.display!=='none'", label="断りの知らせ")
    t.eq(_toast(ed), "⚠ ノーツのレーンが上限（10本）です。空いているレーンを消してからもう一度実行してください", "10本＝断る")
    t.eq(clips_dialog(ed), None, "画面は出ない")
    take_errors(ed, "ノーツのレーンが上限")
    t.no_errors()






def test_clips_english(t):
    '''英語表示: メニューの項目・確認の画面（題・単位・難易度・リンク・まとめ・ボタン）・作ったクリップの名前（自動の名前は英語）・知らせ。日本語が出ない'''
    from nlmtest import LIGHT_RENDER_JS
    ed = t.fresh()
    ed.js("localStorage.setItem('bsnm_lang','en');true")
    ed.wait(0.6)
    ed.reload(clear_storage=False)
    ed.js(LIGHT_RENDER_JS)
    wait_until(ed, "!document.getElementById('bootCover')&&document.getElementById('mFileBtn').textContent.trim()==='File'", label="英語で起動")
    ed.load_fixture("basic", settle=0.3)
    wait_until(ed, "window._dbgApp.analysis().startBtn", label="［Analyze song］")
    run_analysis(ed, "none")
    items = open_clips(ed)
    t.eq(items, ["Create clips…", "Export section starts as markers", "Tempo estimate…", "Analyze again", "Clear analysis results"], "⋯ のメニュー")
    wait_clips_dialog(ed)
    d = clips_dialog(ed)
    t.eq(d["title"], "Create clips from the analysis", "題")
    t.eq([u["text"].split("\n")[0] for u in d["units"]], ["Sections (4 · 3 numbers)", "Segments (8 · 5 groups)", "Both (each on its own new lane)"], "単位")
    t.eq(d["diffs"][2]["text"], "Hard\nopen now", "開いている難易度")
    t.eq(d["sum"], "Will create: 1 new notes lane(s), 4 clip(s) per difficulty × 1 · 1 link group(s)", "まとめ")
    t.eq(d["btns"], ["Create", "Cancel"], "ボタン")
    jp = re.compile(r"[぀-ゟ゠-ヺー-ヿ㐀-䶿一-鿿]")
    t.eq(jp.findall(d["text"] + "".join(x["tip"] for x in d["diffs"])), [], "画面に日本語が無い")
    clips_ok(ed)
    wait_until(ed, "window._dbgApp.nle().editOnly===0", label="作った")
    t.eq([c["label"] for c in _lane(ed, 0)], ["Intro S1", "Verse S2", "Chorus S3", "Verse S2"], "クリップ名（自動の名前は英語）")
    t.eq(_toast(ed), "✅ Created 4 clips on Notes 4 · 1 link group(s). Notes 4 is now Edit only (Ctrl+Z to undo)", "知らせ")
    t.no_errors()

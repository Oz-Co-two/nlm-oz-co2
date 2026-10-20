"""難易度間コピー（難易度ボタンの ▼ の転送・受信・丸ごと転送）で、種類ごとに写る物・写らない物（2026-10-20・利用者の報告で直した）。
決まり: 「ライティングを転送／受信」はライトのクリップとライトだけ、「ノーツを転送／受信」はノーツのクリップとノーツ類（ボム・壁・アーク・チェーン）だけ、
「丸ごと転送」は両方を写す。写さない種類の送り先のクリップ・フラットはそのまま（リンクも）。「親の難易度に繋ぐ」（既定オン）なら、写したクリップは
空のクリップも含めて全部、送り元の同じクリップの子（送り元が子ならその親の子）。ノーツとライトの混ざったリンクは作らない。上書きの注意は写す種類の
物かクリップ（空のクリップも）が送り先にある時だけ。どの転送も Ctrl+Z 1回で全部戻る（まだ無かった難易度も無くなる）。
以前は、まだ開いていない難易度へ送ると今の難易度のクリップの並びを中身だけ空にして丸ごと複製していた＝ライトの転送でノーツのクリップ
（解析から作った空のクリップ・リンクの親まで）が写り、写ったクリップは元の難易度と繋がっていなかった。
素材 rich: Hard＝ノーツのクリップ 拍0〜16（ノーツ7・ボム1・壁1・アーク1）・ライトのクリップ 拍0〜16（ライト3）／Expert＝ノーツ23・ライト12／他の難易度は無い"""
import json
import sys
import time
from pathlib import Path

_P = str(Path(__file__).resolve().parents[1] / "e2e_project")
if _P not in sys.path:
    sys.path.insert(0, _P)

from analysis_helpers import clips_ok, clips_pick, open_clips, run_analysis, wait_clips_dialog   # noqa: E402
from e2e_helpers import hover_3d, project, switch_diff, wait_until   # noqa: E402
from nle_helpers import lane_y, menu, nle, open_nle, redo, scr   # noqa: E402
from project_helpers import _click_el, copy_dialog, menu_pick, toast   # noqa: E402

HARD, EXPERT, EASY, NORMAL = "hardstandard.dat", "expertstandard.dat", "easystandard.dat", "normalstandard.dat"
DK = {"Easy": EASY, "Normal": NORMAL, "Hard": HARD, "Expert": EXPERT}
NOTE_KEYS = ("notes", "bombs", "walls", "arcs", "chains")
SEND = {"notes": "ノーツを転送", "lights": "ライティングを転送", "all": "丸ごと転送（ノーツ＋ライト）"}
RECV = {"notes": "ノーツを受信", "lights": "ライティングを受信"}
KINDS = {"notes": ("n",), "lights": ("l",), "all": ("n", "l")}


# ---- 部品 ----
def _secs(pj, dk, lk):
    st = pj["difficulties"].get(dk) or {}
    return [s for s in st.get("sections", []) if s.get("kind") != "null" and (s.get("lk") == "l") == (lk == "l")]


def _shape(s, link=False):
    """クリップの比べる形（位置・長さ・名前・色・中身。link=True でリンクの id と親かも）"""
    a = (s.get("track", 0), s.get("beat", 0), s.get("len", 4), s.get("label"), s.get("col"), s.get("colHex"),
         json.dumps(s.get("content", {}), sort_keys=True))
    return a + ((s.get("link"), bool(s.get("linkParent"))) if link else ())


def _shapes(pj, dk, lk, link=False):
    return sorted(_shape(s, link) for s in _secs(pj, dk, lk))


def _flat(pj, dk, lk):
    st = pj["difficulties"].get(dk) or {}
    return {k: sorted(json.dumps(x) for x in (st.get(k) or [])) for k in (NOTE_KEYS if lk == "n" else ("lightEvents",))}


def _has(pj, dk, lk):
    """送り先に写す種類の物かクリップ（空のクリップも）があるか＝上書きの注意が出る"""
    return bool(_secs(pj, dk, lk)) or any(_flat(pj, dk, lk).values())


def _links_ok(t, pj, tag):
    """全難易度のリンク: 親は1つ・メンバーは2つ以上・ノーツとライトが混ざらない"""
    g = {}
    for dk, st in pj["difficulties"].items():
        for s in st.get("sections", []):
            if s.get("link"):
                g.setdefault(s["link"], []).append((dk, s.get("lk") == "l", bool(s.get("linkParent"))))
    for lid, ms in g.items():
        t.eq((sum(p for _, _, p in ms), len({l for _, l, _ in ms}), len(ms) >= 2), (1, 1, True), f"{tag}: リンク {lid} は親1つ・種類1つ・2つ以上 {ms}")


def _diff_menu(ed, dn):
    """難易度ボタンのメニューを開く（メニューを使った直後の1回目は「閉じる」扱いになることがあるので、開かなければもう一度押す）"""
    for i in range(2):
        _click_el(ed, f"#diffBar .dfSeg[data-dn='{dn}']")
        try:
            wait_until(ed, "document.getElementById('ctxmenu').style.display==='block'", timeout=2 if i == 0 else 15, label="難易度メニュー")
            return
        except AssertionError:
            if i:
                raise


def _hide_toast(ed):
    ed.js("(e=>{e.style.display='none'; e.textContent=''; return 1})(document.getElementById('errToast'))")


def _wait_project(ed, want, label):
    end = time.time() + 5
    while True:
        got = project(ed)
        if got == want or time.time() > end:
            return got
        ed.wait(0.15)


def _copy(t, ed, cur, payload, way, other, link):
    """今の難易度 cur のメニューから転送（way='→'）／受信（'←'）し、写った物・写らない物・リンク・確認の画面の注意を確かめ、Ctrl+Z 1回で全部戻ることも確かめる。
    戻した後の保存内容を返す（＝転送の前と同じ）"""
    src, dst = (DK[cur], DK[other]) if way == "→" else (DK[other], DK[cur])
    kinds = KINDS[payload]
    tag = f"{cur} {SEND.get(payload) if way == '→' else RECV[payload]} {way} {other}（{'繋ぐ' if link else '繋がない'}）"
    pj0 = project(ed)
    undo0 = ed.js("window._dbgApp.state().undo")
    _hide_toast(ed)
    _diff_menu(ed, cur)
    menu_pick(ed, SEND[payload] if way == "→" else RECV[payload], f"{way} {other}")
    text, checked = copy_dialog(ed, link=link)
    t.eq(checked, True, f"{tag}: 「親の難易度に繋ぐ」は既定でオン")
    t.eq("⚠" in text, any(_has(pj0, dst, lk) for lk in kinds), f"{tag}: 上書きの注意（写す種類の物・クリップが送り先にある時だけ）: {text}")
    wait_until(ed, "document.getElementById('errToast').textContent.includes('コピーしました')", label=f"{tag} の知らせ")
    t.ok("Undoできません" not in toast(ed), f"{tag}: Undo できる（知らせに「Undoできません」が無い）")
    pj1 = project(ed)
    for lk in ("n", "l"):
        word = "ノーツ" if lk == "n" else "ライト"
        if lk in kinds:
            t.eq(_shapes(pj1, dst, lk), _shapes(pj0, src, lk), f"{tag}: 送り先の{word}のクリップ＝送り元（空のクリップも）")
            t.eq(_flat(pj1, dst, lk), _flat(pj0, src, lk), f"{tag}: 送り先の{word}の中身＝送り元")
            for s in _secs(pj1, dst, lk):
                if link:
                    mate = [x for x in _secs(pj1, src, lk) if _shape(x) == _shape(s)]
                    t.ok(s.get("link") and not s.get("linkParent") and any(x.get("link") == s["link"] for x in mate),
                         f"{tag}: 写した{word}のクリップ「{s.get('label')}」（拍{s.get('beat')}）は送り元の同じクリップと同じリンクの子")
                else:
                    t.ok(not s.get("link"), f"{tag}: 繋がない＝写した{word}のクリップ「{s.get('label')}」はリンク無し")
        else:
            t.eq(_shapes(pj1, dst, lk, link=True), _shapes(pj0, dst, lk, link=True), f"{tag}: 送り先の{word}のクリップはそのまま（リンクも）")
            t.eq(_flat(pj1, dst, lk), _flat(pj0, dst, lk), f"{tag}: 送り先の{word}はそのまま")
        t.eq(_shapes(pj1, src, lk), _shapes(pj0, src, lk), f"{tag}: 送り元の{word}のクリップは変わらない（リンクが付くだけ）")
    for dk in set(pj0["difficulties"]) | set(pj1["difficulties"]):
        if dk not in (src, dst):
            t.eq(pj1["difficulties"].get(dk), pj0["difficulties"].get(dk), f"{tag}: 他の難易度 {dk} は変わらない")
    _links_ok(t, pj1, tag)
    t.eq(ed.js("window._dbgApp.state().undo"), undo0 + 1, f"{tag}: 履歴は1つ")
    hover_3d(ed)
    ed.key("z", ctrl=True)
    t.eq(_wait_project(ed, pj0, tag), pj0, f"{tag}: Ctrl+Z 1回で全部戻る（まだ無かった難易度も無くなる）")
    return pj1


def _open_ana(t, diffs=()):
    """rich を開き、Hard で「曲を解析」→「クリップを作る…」（セクション・自動リンク・diffs の難易度にも作る）"""
    ed = open_nle(t, "rich")
    wait_until(ed, "!document.getElementById('bootCover')&&window._dbgApp.analysis().startBtn", label="［曲を解析］が出る")
    run_analysis(ed, "none")
    open_clips(ed)
    wait_clips_dialog(ed)
    if diffs:
        clips_pick(ed, diffs=diffs)
    clips_ok(ed)
    wait_until(ed, "window._dbgApp.nle().editOnly===0", label="解析からクリップを作った")
    return ed


# ---- テスト ----
def test_lights_send_with_analysis_clips(t):
    '''利用者の報告の手順: Hard で解析からクリップを作り（ノーツのレーンに空のクリップ・S2 はリンク）、▼「ライティングを転送」→ Easy（まだ無い難易度）。
    Easy にはライトのクリップとライトだけが写り、ノーツのクリップ（空のクリップ・リンクの親）は写らない。写ったライトのクリップは Hard の子。Undo で Easy も無くなり、やり直しで戻る'''
    ed = _open_ana(t)
    pj0 = project(ed)
    pj1 = _copy(t, ed, "Hard", "lights", "→", "Easy", True)
    t.eq(_secs(pj1, EASY, "n"), [], "Easy にノーツのクリップは無い（解析から作った空のクリップも写らない）")
    t.eq(len(_secs(pj1, EASY, "l")), 1, "Easy にライトのクリップが1つ")
    t.ok(EASY not in project(ed)["difficulties"], "Undo で Easy は無くなる")
    hover_3d(ed)
    redo(ed)
    wait_until(ed, f"window._dbgApp.links().clips.some(c=>c.dk==='{EASY}')", label="やり直し")
    t.eq(project(ed), pj1, "やり直しで転送の後に戻る（Easy も・リンクも）")
    hover_3d(ed)
    ed.key("z", ctrl=True)
    t.eq(_wait_project(ed, pj0, "もう一度 Undo"), pj0, "もう一度 Undo で戻る")
    switch_diff(ed, "Easy")
    t.eq([(c["lk"], c["label"]) for c in nle(ed)["clips"]], [], "Easy を開くと空（転送の前の状態）")
    t.no_errors()


def test_analysis_clips_all_kinds(t):
    '''解析から作ったクリップ（空・S2 はリンク）と素材のクリップ（中身あり）がある Hard から、ノーツ／ライティング／丸ごとの転送・受信を、繋ぐ・繋がない、
    まだ無い難易度・中身のある難易度へ。毎回、写す種類だけが写り、繋ぐなら空のクリップも全部 Hard の同じクリップと同じリンクの子、Ctrl+Z 1回で戻る'''
    ed = _open_ana(t)
    for payload, way, other, link in [("lights", "→", "Easy", False), ("lights", "→", "Expert", True), ("notes", "→", "Easy", True),
                                      ("notes", "→", "Expert", False), ("all", "→", "Normal", True), ("all", "→", "Expert", True),
                                      ("notes", "←", "Expert", True), ("notes", "←", "Easy", False), ("lights", "←", "Expert", True)]:
        _copy(t, ed, "Hard", payload, way, other, link)
    t.no_errors()


def test_manual_empty_and_filled_clips(t):
    '''解析を使わず手で作った空のクリップ（ノーツ・ライト）と中身のあるクリップ: 4種類の転送・受信 × 繋ぐ・繋がない。
    写す種類だけが写り（空のクリップも）、繋ぐなら全部送り元の同じクリップの子、Ctrl+Z 1回で戻る'''
    ed = open_nle(t, "rich")
    for lk in ("n", "l"):
        menu(ed, scr(ed, 20)["x"], lane_y(ed, lk, 1), "空のクリップを作成")
        wait_until(ed, f"window._dbgApp.nle().clips.filter(c=>c.lk==='{lk}').length===2", label=f"空の{lk}のクリップ")
    for payload, way, other, link in [("lights", "→", "Easy", True), ("notes", "→", "Easy", True), ("all", "→", "Easy", False),
                                      ("notes", "→", "Expert", True), ("lights", "→", "Expert", False), ("all", "→", "Expert", True),
                                      ("notes", "←", "Expert", False), ("lights", "←", "Expert", True), ("lights", "←", "Normal", True)]:
        _copy(t, ed, "Hard", payload, way, other, link)
    t.no_errors()


def test_dst_with_linked_empty_clips(t):
    '''送り先（Easy）にも解析から作った空のクリップ（Hard の子）がある: 「ライティングを転送」は Easy の空のノーツのクリップと Hard とのリンクをそのまま残す。
    「ノーツを転送」は Easy にノーツが0個でも空のクリップが置き換わるので上書きの注意が出て、写したクリップは Hard の子。Expert からの受信・Easy 側の転送も'''
    ed = _open_ana(t, diffs=(EASY,))
    pj0 = project(ed)
    t.eq((len(_secs(pj0, EASY, "n")), _flat(pj0, EASY, "n")["notes"]), (4, []), "Easy には空のノーツのクリップが4つ（ノーツは0）")
    _copy(t, ed, "Hard", "lights", "→", "Easy", True)
    _copy(t, ed, "Hard", "notes", "→", "Easy", True)
    _copy(t, ed, "Hard", "lights", "←", "Expert", False)
    switch_diff(ed, "Easy")
    _copy(t, ed, "Easy", "lights", "→", "Expert", True)
    _copy(t, ed, "Easy", "notes", "←", "Hard", True)
    _copy(t, ed, "Easy", "all", "→", "Normal", True)
    t.no_errors()

"""空の難易度（クリップが1つも無い難易度）へ戻った時も置ける（2026-10-27）。
以前は、空の難易度を一度開いて別の難易度へ移り、もう一度その空の難易度を開くと、ノーツ・ライトを置けなかった
（「⚠ ノーツの配線が切断中です」）。loadDiff のクリップの無い難易度の分岐が配線（graphEdges）を張り直さず、前の難易度の
クリップの id を指したままだったため。同じ道を通る、クリップを全部消した難易度へ戻った時・空の難易度を退避したまま保存した
ファイルを開き直した時も確かめる。張り直した配線は未保存の判定に入らない（難易度を切り替えただけでランプが点かない）こと。
入力は本物のマウス・キー（3Dのマス・LIGHTINGのレーン・NLEのクリップ・数字キー・Ctrl+S/O）。保存・開くのファイル選択は偽物（project_helpers）"""
import sys
from pathlib import Path

_T = Path(__file__).resolve().parents[1]
for _p in (_T / "e2e_edit", _T / "e2e_nle"):   # LIGHTING の操作（edit_helpers）・NLE の操作（nle_helpers）の部品を使う
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from e2e_helpers import cell, counts, hover_3d, open_fixture, state, switch_diff, wait_until
from edit_helpers import light_lane, mv, to_edit_cam, to_light_mode
from nle_helpers import clips, nle_mouse, select
from project_helpers import install_fake_fs, queue_open
from test_dirty_switch import _clean, _save

WARN = "配線が切断中"
STAT = "document.getElementById('stat').textContent"
L_LASER = 6   # LIGHTING のレーン番号（0=左端）。種別 2


def _setup(t):
    ed = open_fixture(t, "rich")
    install_fake_fs(ed)
    ed.js("document.getElementById('errToast').style.display='none'")
    return ed


def _visit_empty_and_back(ed):
    """まだ無い難易度（rich の Easy）を開く→Hard へ→Easy へ戻る（数字キー）"""
    switch_diff(ed, "Easy")
    switch_diff(ed, "Hard")
    switch_diff(ed, "Easy")


def _place_note(t, ed, x, y, label):
    """3D のマス (x,y) をクリックして置く。置けたこと・配線の警告が出ないことを確かめる"""
    n0 = counts(ed)["notes"]
    wait_until(ed, f"(p=>p&&p.onScreen)(window._dbgApp.cellScreen({x},{y}))", timeout=5.0, label=f"マス({x},{y})が画面に出る")
    ed.wait(0.1)
    p = cell(ed, x, y)
    ed.move(p["x"], p["y"]); ed.wait(0.15)   # ホバーでゴーストが出てから押す
    ed.click(p["x"], p["y"])
    wait_until(ed, f"window._dbgApp.state().counts.notes>{n0}||{STAT}.includes('{WARN}')", label=f"{label}: 置いた結果")
    t.ok(WARN not in ed.js(STAT), f"{label}: 配線の警告が出ない（{ed.js(STAT)}）")
    t.eq(counts(ed)["notes"], n0 + 1, f"{label}: ノーツが1つ増える")


def test_place_note_revisit_empty_diff(t):
    '''空の難易度（Easy）を開いて Hard へ移り、Easy へ戻って 3D でノーツを置ける。切り替えただけでは未保存にならず、置くと未保存'''
    ed = _setup(t)
    _save(ed)
    _visit_empty_and_back(ed)
    t.eq(clips(ed), [], "前提: Easy にクリップが無い")
    _clean(t, ed, "空の Easy へ戻った後")
    _place_note(t, ed, 3, 2, "空の Easy へ戻って置く")
    wait_until(ed, "window._dbgApp.dirty().lamp===true", label="置いた後は未保存")
    t.eq(len(clips(ed, "n")), 1, "置いた所にノーツのクリップが1つできる")
    # もう一度 Hard へ行って戻っても置ける（今度はクリップのある難易度＝今までどおり）
    switch_diff(ed, "Hard")
    switch_diff(ed, "Easy")
    _place_note(t, ed, 1, 0, "クリップができた Easy へ戻って置く")
    t.no_errors()


def test_place_light_revisit_empty_diff(t):
    '''空の難易度（Easy）を開いて Hard へ移り、Easy へ戻って LIGHTING でライトを置ける（「ライティングの配線が切断中」にならない）'''
    ed = _setup(t)
    _visit_empty_and_back(ed)
    to_edit_cam(ed)
    to_light_mode(ed)
    n0 = counts(ed)["lights"]
    p = light_lane(ed, L_LASER, 1)
    mv(ed, p["x"], p["y"])
    ed.click(p["x"], p["y"])
    wait_until(ed, f"window._dbgApp.state().counts.lights>{n0}||{STAT}.includes('{WARN}')", label="ライトを置いた結果")
    t.ok(WARN not in ed.js(STAT), f"配線の警告が出ない（{ed.js(STAT)}）")
    t.eq(counts(ed)["lights"], n0 + 1, "ライトが1つ増える")
    t.eq(len(clips(ed, "l")), 1, "置いた所にライトのクリップが1つできる")
    t.no_errors()


def test_place_after_deleting_all_clips(t):
    '''Hard のクリップを NLE で全部消して Expert へ移り、Hard へ戻って 3D でノーツを置ける（クリップの無い難易度を開き直すのと同じ道）'''
    ed = _setup(t)
    cs = clips(ed)
    t.eq(sorted(c["lk"] for c in cs), ["l", "n"], "前提: rich の Hard はノーツ・ライトのクリップが1つずつ")
    select(ed, cs[0])
    for c in cs[1:]:
        select(ed, c, shift=True)
    nle_mouse(ed)
    ed.key("Delete")
    wait_until(ed, "window._dbgApp.nle().clips.length===0", label="クリップを全部消す")
    t.eq(counts(ed)["notes"], 0, "消した後の Hard のノーツ")
    switch_diff(ed, "Expert")
    switch_diff(ed, "Hard")
    t.eq(clips(ed), [], "Hard へ戻ってもクリップは無い")
    _place_note(t, ed, 3, 2, "クリップを全部消した Hard へ戻って置く")
    t.no_errors()


def test_place_empty_diff_after_reopen(t):
    '''空の Easy を開いた後に保存したファイル（Easy は空の難易度として入る）を開き直し、Easy へ切り替えて 3D でノーツを置ける'''
    ed = _setup(t)
    switch_diff(ed, "Easy")
    switch_diff(ed, "Hard")
    _save(ed)
    text = ed.js("__fake.writes[0].text")
    t.ok('"easystandard.dat"' in text, "前提: 保存したファイルに空の Easy が入る")
    queue_open(ed, "a.nlmf", text)
    hover_3d(ed)
    ed.key("o", ctrl=True)
    wait_until(ed, "__fake.openCalls.length===1&&window._dbgApp.dirty().lamp===false", label="開き直す")
    t.eq(state(ed)["diff"], "HardStandard.dat", "開いた直後は保存した時の Hard")
    switch_diff(ed, "Easy")
    _clean(t, ed, "開き直して空の Easy へ")
    _place_note(t, ed, 3, 2, "開き直した後の空の Easy に置く")
    t.no_errors()

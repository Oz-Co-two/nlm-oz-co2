"""環境設定ダイアログ（メニュー「環境設定」）: 各タブの主な設定を変えると localStorage(bsnm_*) に保存され、開き直しても残る。
config/settings.json へのミラー保存・全設定の初期化・ショートカットの割り当て変更も確かめる。
開き直しは localStorage を消さない reload_keep（cdp の既定の reload は消す）。各テストは終わりに設定を初回起動時の状態へ戻す（prefs_page）。"""
import json
from pathlib import Path

from cdp import CdpError
from misc_helpers import (center, click_in_view, close_prefs, hover_3d, ls, ls_json, mirror_json, open_prefs, prefs_page, prefs_set_number,
                          prefs_tab, prefs_toggle, reload_keep, wait_mirrored, wait_until)
from e2e_helpers import canvas_center

ROOT = Path(__file__).resolve().parents[2]
DEFAULTS = json.loads((ROOT / "config" / "settings.default.json").read_text(encoding="utf-8"))


def _val(ed, el_id):
    return ed.js(f"document.getElementById({json.dumps(el_id)}).value")


def _checked(ed, el_id):
    return ed.js(f"document.getElementById({json.dumps(el_id)}).checked")


def _near(a, b, tol=1e-3):
    return abs(a - b) <= tol


# ---------------------------------------------------------------- ダイアログ
def test_prefs_dialog_tabs(t):
    '''環境設定を開くとアプリケーション設定のタブが出る→5つのタブ（アプリ/音量/Preview/カメラ/ショートカット）を押すとその画面だけが出る→閉じる・外側のクリックで閉じる'''
    with prefs_page(t) as ed:
        t.eq(ed.js("document.getElementById('settingsBg').style.display"), "", "最初は閉じている")
        open_prefs(ed)
        tabs = ed.js("[...document.querySelectorAll('#settingsBox .setTab')].map(b=>b.dataset.tab)")
        t.eq(tabs, ["app", "vol", "preview", "cam", "keys"], "タブの並び")
        t.eq(ed.js("[...document.querySelectorAll('#settingsBox .setPanel.on')].map(p=>p.dataset.panel)"), ["app"], "最初はアプリケーション設定")
        for tab in tabs:
            prefs_tab(ed, tab)
            t.eq(ed.js("[...document.querySelectorAll('#settingsBox .setPanel.on')].map(p=>p.dataset.panel)"), [tab], f"{tab} だけが表示される")
            t.eq(ed.js("[...document.querySelectorAll('#settingsBox .setTab.on')].map(b=>b.dataset.tab)"), [tab], f"{tab} のタブが選択表示")
        t.ok(ed.js("document.querySelectorAll('#keyEditBody > div').length") > 30, "ショートカット編集の一覧が描かれる")
        close_prefs(ed)
        open_prefs(ed)
        ed.click(8, 8)   # ダイアログの外（背景）を押す
        wait_until(ed, "document.getElementById('settingsBg').style.display==='none'", label="外側のクリックで閉じる")
        t.no_errors()


def test_prefs_volume(t):
    '''音量: 4つのスライダーを手入力で変えると bsnm_vol に保存され config/settings.json にもミラーされる。反映は再起動後（開き直すと設定画面・右のフェーダー・実際の音量に出る）。右のマスターフェーダーは即座に効く'''
    with prefs_page(t) as ed:
        t.eq(ls_json(ed, "bsnm_vol"), {"m": 50, "mu": 50, "n": 50, "mt": 50}, "初期値は全て50")
        t.ok(_near(ed.js("window._dbg.rt.masterGain.gain.value"), 0.25), "初期のマスター音量 (50%)^2")
        open_prefs(ed)
        prefs_tab(ed, "vol")
        for rid, n in (("volM", 30), ("volMu", 70), ("volN", 20), ("volMt", 80)):
            prefs_set_number(ed, rid, n)
        t.eq(ls_json(ed, "bsnm_vol"), {"m": 30, "mu": 70, "n": 20, "mt": 80}, "保存された値")
        t.eq([ed.js(f"document.getElementById('{i}').textContent") for i in ("volMVal", "volMuVal", "volNVal", "volMtVal")],
             ["30", "70", "20", "80"], "スライダー横の数値表示")
        t.ok(_near(ed.js("window._dbg.rt.masterGain.gain.value"), 0.25), "スライダーの変更は保存のみ（実際の音量は再起動後に反映）")
        wait_mirrored(ed, "bsnm_vol")
        t.eq(json.loads(mirror_json(ed)["bsnm_vol"]), {"m": 30, "mu": 70, "n": 20, "mt": 80}, "config/settings.json にミラーされた")
        reload_keep(ed)
        t.eq(ls_json(ed, "bsnm_vol"), {"m": 30, "mu": 70, "n": 20, "mt": 80}, "開き直しても保存されている")
        open_prefs(ed)
        prefs_tab(ed, "vol")
        t.eq([int(_val(ed, i)) for i in ("volM", "volMu", "volN", "volMt")], [30, 70, 20, 80], "設定画面のスライダー")
        t.eq(int(_val(ed, "vol")), 30, "右のフェーダー（マスター）")
        t.ok(_near(ed.js("window._dbg.rt.masterGain.gain.value"), 0.09), "実際のマスター音量 (30%)^2")
        t.ok(_near(ed.js("window._dbg.rt.hitGain.gain.value"), 0.04), "ノーツ音 (20%)^2")
        # 右のマスターフェーダーをキーで動かすと、すぐ実際の音量に効き、設定画面のマスター音量・保存値も同じ値になる
        ed.js("document.getElementById('vol').focus()")
        ed.key("ArrowDown")
        wait_until(ed, "+document.getElementById('vol').value===29", label="フェーダーが29に")
        t.eq(ls_json(ed, "bsnm_vol")["m"], 29, "フェーダーを動かした保存値")
        t.ok(_near(ed.js("window._dbg.rt.masterGain.gain.value"), 0.29 ** 2), "フェーダーは即座に実際の音量へ反映")
        t.eq((int(_val(ed, "volM")), ed.js("document.getElementById('volMVal').textContent")), (29, "29"), "設定画面のマスター音量も追従")
        t.no_errors()


# ---------------------------------------------------------------- カメラ・スクロール
def test_prefs_camera_speed(t):
    '''カメラ速度（回転・ズーム・パン）を手入力で変えると bsnm_camspd に倍率で保存され、開き直すとスライダーと実際の速度に出る'''
    with prefs_page(t) as ed:
        open_prefs(ed)
        prefs_tab(ed, "cam")
        for rid, n in (("rotSpd", 130), ("zoomSpd", 70), ("panSpd", 120)):
            prefs_set_number(ed, rid, n)
        t.eq(ls_json(ed, "bsnm_camspd"), {"rot": 1.3, "zoom": 0.7, "pan": 1.2}, "倍率で保存される")
        t.eq([ed.js(f"document.getElementById('{i}').textContent") for i in ("rotVal", "zoomVal", "panVal")], ["130", "70", "120"], "数値表示")
        # 範囲外（50〜150）の入力は範囲内に丸められる（今は130%＝上限に丸められれば150になる）
        ed.click(*_xy(center(ed, "#rotVal"))); ed.click(*_xy(center(ed, "#rotVal")), count=2)
        wait_until(ed, "!!document.querySelector('#rotVal input')", label="数値の入力欄")
        ed.key("a", ctrl=True)
        ed.call("Input.insertText", text="999")
        ed.key("Enter")
        wait_until(ed, "+document.getElementById('rotSpd').value===150", label="上限に丸められる")
        t.eq(ls_json(ed, "bsnm_camspd")["rot"], 1.5, "上限150%に丸めて保存")
        ed.click(*_xy(center(ed, "#rotVal"))); ed.click(*_xy(center(ed, "#rotVal")), count=2)
        wait_until(ed, "!!document.querySelector('#rotVal input')", label="数値の入力欄")
        ed.key("a", ctrl=True)
        ed.call("Input.insertText", text="1")
        ed.key("Enter")
        wait_until(ed, "+document.getElementById('rotSpd').value===50", label="下限に丸められる")
        t.eq(ls_json(ed, "bsnm_camspd")["rot"], 0.5, "下限50%に丸めて保存")
        prefs_set_number(ed, "rotSpd", 130)
        wait_mirrored(ed, "bsnm_camspd")
        reload_keep(ed)
        t.eq([ed.js("window._dbg.rt.camRotSpeed"), ed.js("window._dbg.rt.camZoomSpeed"), ed.js("window._dbg.rt.camPanSpeed")],
             [1.3, 0.7, 1.2], "開き直した後の実際のカメラ速度")
        open_prefs(ed)
        prefs_tab(ed, "cam")
        t.eq([int(_val(ed, i)) for i in ("rotSpd", "zoomSpd", "panSpd")], [130, 70, 120], "設定画面のスライダー")
        t.no_errors()


def _xy(p):
    return p["x"], p["y"]


def _wheel_3d(ed, dy):
    c = canvas_center(ed)
    ed.wheel(c["x"], c["y"], dy)


def _cur(ed):
    return ed.js("window._dbgApp.state().cur")


def test_prefs_invert_scroll(t):
    '''ホイール（時間移動）の向きの反転は3D・2D（NLE）で別項目: 3Dのチェックを入れると3Dのホイールだけ逆向きになり、2Dのチェックを入れるとNLE上のホイールだけ逆向きになる。保存され、開き直しても残る'''
    with prefs_page(t) as ed:
        ed.load_fixture("basic", settle=0.3)
        hover_3d(ed)
        snap = ed.js("window._dbgApp.nle().snap")
        _wheel_3d(ed, -100)
        wait_until(ed, f"window._dbgApp.state().cur==={snap}", label="3Dで上へ回すと進む")
        _wheel_3d(ed, 100)
        wait_until(ed, "window._dbgApp.state().cur===0", label="3Dで下へ回すと戻る")
        open_prefs(ed)
        prefs_tab(ed, "cam")
        prefs_toggle(ed, "invert3DScroll")
        t.eq((ls(ed, "bsnm_invert3dscroll"), ls(ed, "bsnm_invert2dscroll")), ("1", None), "3Dだけ保存（2Dは触っていない）")
        close_prefs(ed)
        hover_3d(ed)
        _wheel_3d(ed, 100)
        wait_until(ed, f"window._dbgApp.state().cur==={snap}", label="反転後は3Dで下へ回すと進む")
        _wheel_3d(ed, -100)
        wait_until(ed, "window._dbgApp.state().cur===0", label="反転後は3Dで上へ回すと戻る")
        # 2D（NLE）は別項目: まだ反転していない
        s = ed.js("window._dbgApp.nleScreen(0)")
        x, y = s["left"] + s["w"] * 0.5, s["lanes"] + 40
        ed.move(x, y)
        ed.wheel(x, y, -100)
        wait_until(ed, f"window._dbgApp.state().cur==={snap}", label="NLEは反転していない＝上へ回すと進む")
        ed.wheel(x, y, 100)
        wait_until(ed, "window._dbgApp.state().cur===0", label="NLEで下へ回すと戻る")
        open_prefs(ed)
        prefs_tab(ed, "cam")
        prefs_toggle(ed, "invert2DScroll")
        t.eq(ls(ed, "bsnm_invert2dscroll"), "1", "2Dも保存")
        close_prefs(ed)
        ed.move(x, y)
        ed.wheel(x, y, 100)
        wait_until(ed, f"window._dbgApp.state().cur==={snap}", label="反転後はNLEで下へ回すと進む")
        wait_mirrored(ed, "bsnm_invert3dscroll", "bsnm_invert2dscroll")
        reload_keep(ed)
        open_prefs(ed)
        prefs_tab(ed, "cam")
        t.eq((_checked(ed, "invert3DScroll"), _checked(ed, "invert2DScroll")), (True, True), "開き直してもチェックが残る")
        close_prefs(ed)
        hover_3d(ed)
        _wheel_3d(ed, 100)
        wait_until(ed, f"window._dbgApp.state().cur==={snap}", label="開き直した後も3Dの反転が効く")
        t.no_errors()


# ---------------------------------------------------------------- Preview
def test_prefs_preview_sliders(t):
    '''Preview設定: 6つのスライダー（%）を手入力で変えると bsnm_pv4 に保存され、実行中の設定値(pvCfg)にもすぐ入る。開き直しても残る'''
    with prefs_page(t) as ed:
        want = {"str": 150, "rad": 60, "thr": 120, "amb": 80, "ems": 130, "refl": 170}
        t.eq(ed.js("({...window._dbg.rt.pvCfg})"), {"str": 100, "rad": 100, "thr": 100, "amb": 100, "ems": 100, "refl": 100}, "初期値は全て100%")
        open_prefs(ed)
        prefs_tab(ed, "preview")
        for rid, k in (("pvBloomStr", "str"), ("pvBloomRad", "rad"), ("pvBloomThr", "thr"), ("pvAmb", "amb"), ("pvEms", "ems"), ("pvRefl", "refl")):
            prefs_set_number(ed, rid, want[k])
        t.eq(ls_json(ed, "bsnm_pv4"), want, "保存された値")
        t.eq(ed.js("({...window._dbg.rt.pvCfg})"), want, "実行中の設定値にもすぐ反映")
        wait_mirrored(ed, "bsnm_pv4")
        reload_keep(ed)
        t.eq(ed.js("({...window._dbg.rt.pvCfg})"), want, "開き直した後の設定値")
        open_prefs(ed)
        prefs_tab(ed, "preview")
        t.eq({k: int(_val(ed, i)) for i, k in (("pvBloomStr", "str"), ("pvBloomRad", "rad"), ("pvBloomThr", "thr"), ("pvAmb", "amb"), ("pvEms", "ems"), ("pvRefl", "refl"))},
             want, "設定画面のスライダー")
        t.no_errors()


# ---------------------------------------------------------------- アプリケーション設定
def test_prefs_app_checkboxes(t):
    '''アプリケーション設定のチェック項目: ショートカット表示・直前ノーツ表示・同じ向きの警告・更新の確認・Chromaを切り替えるとそれぞれ効き、bsnm_* に保存されて開き直しても残る'''
    with prefs_page(t) as ed:
        t.eq(ed.js("document.getElementById('commonKeys').style.display"), "", "標準操作のショートカット表示は最初は出ている")
        open_prefs(ed)
        prefs_toggle(ed, "keysCommon")
        t.eq(ls(ed, "bsnm_kc"), "0", "保存（標準操作）")
        t.eq(ed.js("document.getElementById('commonKeys').style.display"), "none", "標準操作の表示が消える")
        prefs_toggle(ed, "keysNotes")
        t.eq(ls(ed, "bsnm_knt"), "0", "保存（NOTES）")
        t.eq(ed.js("document.getElementById('modeKeys').style.display"), "none", "NOTESの表示が消える（今はNOTES画面）")
        prefs_toggle(ed, "auxPrevShow")
        t.eq((ls(ed, "bsnm_auxprev"), ed.js("window._dbgApp.aux().show")), ("0", False), "直前ノーツ表示 OFF")
        prefs_toggle(ed, "swingWarnOn")
        t.eq((ls(ed, "bsnm_swingwarn"), ed.js("window._dbgApp.swing().on")), ("0", False), "同じ向きの警告 OFF")
        prefs_toggle(ed, "updateCheckOn")
        t.eq(ls(ed, "bsnm_updateCheck"), "0", "起動時の更新確認 OFF")
        t.eq(ls(ed, "bsnm_chroma"), "0", "Chroma は初期値OFF")
        prefs_toggle(ed, "chromaMode")
        t.eq(ls(ed, "bsnm_chroma"), "1", "Chroma ON")
        keys = ["bsnm_kc", "bsnm_knt", "bsnm_auxprev", "bsnm_swingwarn", "bsnm_updateCheck", "bsnm_chroma"]
        wait_mirrored(ed, *keys)
        t.eq({k: mirror_json(ed)[k] for k in keys},
             {"bsnm_kc": "0", "bsnm_knt": "0", "bsnm_auxprev": "0", "bsnm_swingwarn": "0", "bsnm_updateCheck": "0", "bsnm_chroma": "1"}, "config/settings.json にミラー")
        reload_keep(ed)
        open_prefs(ed)
        t.eq({i: _checked(ed, i) for i in ("keysCommon", "keysNotes", "keysLight", "keysNode", "keysInfo", "auxPrevShow", "swingWarnOn", "updateCheckOn", "chromaMode")},
             {"keysCommon": False, "keysNotes": False, "keysLight": True, "keysNode": True, "keysInfo": True, "auxPrevShow": False,
              "swingWarnOn": False, "updateCheckOn": False, "chromaMode": True}, "開き直した後のチェック（触っていない項目は初期値のまま）")
        t.eq(ed.js("document.getElementById('commonKeys').style.display"), "none", "開き直しても標準操作の表示は消えたまま")
        t.eq((ed.js("window._dbgApp.aux().show"), ed.js("window._dbgApp.swing().on")), (False, False), "開き直した後の動作")
        t.no_errors()

def test_prefs_app_sliders(t):
    '''アプリケーション設定のスライダー: 文字サイズ110%は bsnm_uiscale に1.1で保存され反映は再起動後（開き直すとメニューバー等のズームが1.1）。レーン構成を5:1にすると今のプロジェクトにすぐ反映され、bsnm_laneratio に保存されて次の新規プロジェクトの初期値にもなる'''
    with prefs_page(t) as ed:
        t.eq(ed.js("document.getElementById('menubar').style.zoom"), "1", "初期は等倍")
        t.eq(ed.js("window._dbgApp.nle().lanes"), {"n": 3, "l": 3}, "レーンの初期は3:3")
        open_prefs(ed)
        prefs_set_number(ed, "uiSpd", 110)
        t.eq(ls(ed, "bsnm_uiscale"), "1.1", "文字サイズの保存")
        t.eq(ed.js("document.getElementById('menubar').style.zoom"), "1", "文字サイズの変更は再起動後に反映（ドラッグ中に実サイズを変えない）")
        prefs_set_number(ed, "laneRatio", 5)
        wait_until(ed, "window._dbgApp.nle().lanes.n===5", label="今のプロジェクトのレーン数")
        t.eq(ed.js("window._dbgApp.nle().lanes"), {"n": 5, "l": 1}, "ノーツ5・ライト1")
        t.eq(ed.js("document.getElementById('laneRatioVal').textContent"), "5 : 1", "表示")
        t.eq(ls(ed, "bsnm_laneratio"), "5", "レーン構成の保存")
        wait_mirrored(ed, "bsnm_uiscale", "bsnm_laneratio")
        reload_keep(ed)
        t.eq(ed.js("document.getElementById('menubar').style.zoom"), "1.1", "開き直すと文字サイズが反映される")
        t.eq(ed.js("window._dbgApp.nle().lanes"), {"n": 5, "l": 1}, "開き直した新しいプロジェクトのレーンの初期値")
        open_prefs(ed)
        t.eq((int(_val(ed, "uiSpd")), ed.js("document.getElementById('uiVal').textContent")), (110, "110"), "設定画面の文字サイズ")
        t.eq((int(_val(ed, "laneRatio")), ed.js("document.getElementById('laneRatioVal').textContent")), (5, "5 : 1"), "設定画面のレーン構成")
        t.no_errors()


def test_prefs_language(t):
    '''言語: 日本語→English に切り替えるとメニュー・設定画面の文言が英語になり bsnm_lang='en' が保存される。開き直しても英語のまま・日本語へ戻せる'''
    with prefs_page(t) as ed:
        t.eq(ed.js("document.getElementById('mbSettings').textContent"), "環境設定", "最初は日本語")
        open_prefs(ed)
        ed.js("document.getElementById('langSel').focus()")
        ed.key("ArrowDown")   # 日本語→English（フォーカスした選択欄をキーで切り替える）
        wait_until(ed, "document.getElementById('mbSettings').textContent==='Preferences'", label="英語に切り替わる")
        t.eq(ls(ed, "bsnm_lang"), "en", "保存")
        t.eq(ed.js("document.querySelector('#settingsBox h2').textContent"), "Preferences", "設定画面の見出しも英語")
        t.eq(ed.js("document.querySelector('#settingsBox .setTab[data-tab=app]').textContent"), "Application", "タブも英語")
        wait_mirrored(ed, "bsnm_lang")
        reload_keep(ed)
        # 翻訳ファイルの読込は起動後に非同期で行われる＝PCが混んでいると開き直した直後はまだ日本語のことがある。切り替わるまで待つ
        try:
            wait_until(ed, "document.getElementById('mbSettings').textContent==='Preferences'", label="開き直しても英語")
        except AssertionError:
            pass
        t.eq(ed.js("document.getElementById('mbSettings').textContent"), "Preferences", "開き直しても英語")
        open_prefs(ed)
        t.eq(ed.js("document.getElementById('langSel').value"), "en", "選択欄も English")
        ed.js("document.getElementById('langSel').focus()")
        ed.key("ArrowUp")
        wait_until(ed, "document.getElementById('mbSettings').textContent==='環境設定'", label="日本語へ戻る")
        t.eq(ls(ed, "bsnm_lang"), "ja", "日本語へ戻した値が保存される")
        t.no_errors()


# ---------------------------------------------------------------- ショートカット編集
def _key_rows(ed):
    return ed.js("[...document.querySelectorAll('#keyEditBody > div')].map(r=>r.textContent)")


def _row_idx(ed, label):
    i = ed.js(f"[...document.querySelectorAll('#keyEditBody > div')].findIndex(r=>r.firstChild&&r.firstChild.textContent==={json.dumps(label)})")
    assert i >= 0, f"ショートカットの行が見つかりません: {label}"
    return i


def _row_btn(ed, label, n=0):
    """label の行の n 番目のボタン（0=変更/取消・1=既定）の中央。行が画面外ならスクロールしてから座標を返す"""
    i = _row_idx(ed, label)
    p = ed.js(f"""(()=>{{const b=[...document.querySelectorAll('#keyEditBody > div')][{i}].querySelectorAll('button')[{n}];
      if(!b) return null; b.scrollIntoView({{block:'center'}}); const q=b.getBoundingClientRect(); return {{x:q.left+q.width/2,y:q.top+q.height/2}}}})()""")
    assert p, f"{label} の {n} 番目のボタンがありません"
    return p


def _row_text(ed, label):
    return ed.js(f"[...document.querySelectorAll('#keyEditBody > div')][{_row_idx(ed, label)}].textContent")


def _row_kbd(ed, label):
    return ed.js(f"(()=>{{const k=[...document.querySelectorAll('#keyEditBody > div')][{_row_idx(ed, label)}].querySelector('kbd'); return {{text:k.textContent,title:k.title}}}})()")


def _remap(ed, label, key):
    """label の行の「変更」→ キーを押す"""
    p = _row_btn(ed, label)
    ed.click(p["x"], p["y"])
    wait_until(ed, "[...document.querySelectorAll('#keyEditBody kbd')].some(k=>k.textContent==='キーを押す…')", label="キー待ち")
    ed.key(key)


def test_prefs_shortcut_remap(t):
    '''ショートカット編集: 「直前ノーツ表示 切替」(H)の「変更」→Jを押すと割り当てが変わり bsnm_keymap に保存され、実際にJで切り替わりHでは切り替わらない。「既定」で戻る。開き直しても残る'''
    with prefs_page(t) as ed:
        L = "直前ノーツ表示 切替"
        open_prefs(ed)
        prefs_tab(ed, "keys")
        t.eq(_row_kbd(ed, L)["text"], "H", "初期のキー")
        t.eq(ls(ed, "bsnm_keymap"), None, "初期は割り当て変更なし")
        _remap(ed, L, "j")
        wait_until(ed, f"document.querySelector('#keyEditBody').textContent.includes({json.dumps(L + 'J')})", label="割り当ての表示")
        t.eq(ls_json(ed, "bsnm_keymap"), {"auxPrev": {"k": "j", "c": False, "a": False, "s": False}}, "保存された割り当て")
        t.ok(_row_text(ed, L).endswith("既定"), "変更した行には「既定」ボタンが出る")
        close_prefs(ed)
        hover_3d(ed)
        t.eq(ed.js("window._dbgApp.aux().show"), True, "初期は直前ノーツ表示ON")
        ed.key("h")
        ed.wait(0.2)
        t.eq(ed.js("window._dbgApp.aux().show"), True, "Hでは切り替わらない")
        ed.key("j")
        wait_until(ed, "window._dbgApp.aux().show===false", label="Jで切り替わる")
        # 開き直しても割り当ては残り、Jが効く
        wait_mirrored(ed, "bsnm_keymap")
        reload_keep(ed)
        t.eq(ed.js("window._dbgApp.aux().show"), False, "開き直しても直前ノーツ表示のOFFは残っている")
        hover_3d(ed)
        ed.key("j")
        wait_until(ed, "window._dbgApp.aux().show===true", label="開き直した後もJで切り替わる（OFF→ON）")
        # 「既定」で戻す
        open_prefs(ed)
        prefs_tab(ed, "keys")
        p = _row_btn(ed, L, 1)
        ed.click(p["x"], p["y"])
        wait_until(ed, f"document.querySelector('#keyEditBody').textContent.includes({json.dumps(L + 'H')})", label="既定へ戻る")
        t.eq(ls_json(ed, "bsnm_keymap"), {}, "割り当てが空に戻る")
        t.no_errors()


def test_prefs_shortcut_conflict_cancel_and_reset_all(t):
    '''ショートカット編集: 同じ種類の別の操作と同じキーにすると「…と重複しています」と出る／取り込み中にEscで取り消せる／「全て既定に戻す」で全部戻る'''
    with prefs_page(t) as ed:
        L = "直前ノーツ表示 切替"
        open_prefs(ed)
        prefs_tab(ed, "keys")
        # 取り込み中に Esc → 取り消し（何も変わらない）
        p = _row_btn(ed, L)
        ed.click(p["x"], p["y"])
        wait_until(ed, "[...document.querySelectorAll('#keyEditBody kbd')].some(k=>k.textContent==='キーを押す…')", label="キー待ち")
        t.ok(_row_text(ed, L).endswith("取消"), "取り込み中のボタンは「取消」")
        ed.key("Escape")
        wait_until(ed, "![...document.querySelectorAll('#keyEditBody kbd')].some(k=>k.textContent==='キーを押す…')", label="取り込みの終了")
        t.eq(ls(ed, "bsnm_keymap"), None, "Escでは割り当てを変えない")
        t.eq(_row_kbd(ed, L)["text"], "H", "表示も元のまま")
        # 色の反転(F・NOTES)と同じFにする → 重複の警告
        _remap(ed, L, "f")
        wait_until(ed, f"document.querySelector('#keyEditBody').textContent.includes({json.dumps(L + 'F')})", label="割り当ての表示")
        t.eq(_row_kbd(ed, L)["title"], "「色の反転」と重複しています", "重複の警告")
        t.eq(_row_kbd(ed, "色の反転")["title"], "「直前ノーツ表示 切替」と重複しています", "相手の行にも警告")
        # LIGHTING の「色を回転」(F) は別の種類なので、重複とは見なされない
        t.eq(_row_kbd(ed, "色を回転")["title"], "", "別の種類（LIGHTING）とは重複扱いにしない")
        # 全て既定に戻す
        _remap(ed, "再生 / 停止", "p")
        wait_until(ed, "Object.keys(JSON.parse(localStorage.getItem('bsnm_keymap')||'{}')).length===2", label="2件の割り当て")
        click_in_view(ed, "#keysResetAll", "全て既定に戻す")
        wait_until(ed, "localStorage.getItem('bsnm_keymap')==='{}'", label="全て既定へ")
        t.eq((_row_kbd(ed, L)["text"], _row_kbd(ed, "再生 / 停止")["text"]), ("H", "Space"), "表示も既定へ")
        t.no_errors()


# ---------------------------------------------------------------- 初期化
def _wait_reloaded(ed, marker):
    """ページ自身が location.reload() した（印 window.<marker> が消え、起動が終わった）のを待つ。読み込み中のJS実行エラーは無視"""
    import time
    end = time.time() + 30
    while time.time() < end:
        try:
            if ed.js(f"window.{marker}===undefined&&document.readyState==='complete'&&!!window._dbgApp&&window._dbgApp.booted()&&!document.getElementById('bootCover')"):
                return
        except CdpError:
            pass
        time.sleep(0.1)
    raise AssertionError("初期化後のリロードが終わりません")


def test_prefs_reset_all(t):
    '''「初期設定に戻す」: 確認（環境設定を初回起動時の状態に戻す）の後、変えた設定・ショートカット・カメラ速度が全て初回起動時（settings.default.json）に戻り、config/settings.json も同じ内容になる'''
    with prefs_page(t) as ed:
        open_prefs(ed)
        prefs_tab(ed, "vol")
        prefs_set_number(ed, "volM", 20)
        prefs_tab(ed, "cam")
        prefs_set_number(ed, "rotSpd", 140)
        prefs_toggle(ed, "invert3DScroll")
        prefs_tab(ed, "app")
        prefs_toggle(ed, "keysCommon")
        prefs_tab(ed, "keys")
        _remap(ed, "直前ノーツ表示 切替", "j")
        wait_until(ed, "!!localStorage.getItem('bsnm_keymap')", label="割り当ての保存")
        t.eq(ls_json(ed, "bsnm_vol")["m"], 20, "準備: 音量を変えた")
        wait_mirrored(ed, "bsnm_vol", "bsnm_camspd", "bsnm_kc", "bsnm_keymap", "bsnm_invert3dscroll")
        t.eq(json.loads(mirror_json(ed)["bsnm_vol"])["m"], 20, "準備: ミラーも変わっている")
        ed.js("window.__mk=1")
        n0 = len([e for e in ed._events if e.get("method") == "Page.javascriptDialogOpening"])
        click_in_view(ed, "#settingsReset", "初期設定に戻す")
        _wait_reloaded(ed, "__mk")
        dialogs = [e["params"]["message"] for e in ed._events if e.get("method") == "Page.javascriptDialogOpening"]
        t.ok(len(dialogs) > n0 and "初回起動時の状態に戻します" in dialogs[-1], f"確認が出た: {dialogs[-1:]}")
        store = {k: ls(ed, k) for k in ("bsnm_vol", "bsnm_camspd", "bsnm_kc", "bsnm_keymap", "bsnm_invert3dscroll", "bsnm_lang", "bsnm_laneratio")}
        t.eq(store, {"bsnm_vol": DEFAULTS["bsnm_vol"], "bsnm_camspd": None, "bsnm_kc": "1", "bsnm_keymap": None, "bsnm_invert3dscroll": None,
                     "bsnm_lang": "ja", "bsnm_laneratio": "3"}, "初回起動時の値へ戻る（初期値の無い項目は消える）")
        t.eq(mirror_json(ed), DEFAULTS, "config/settings.json も初期値と同じ内容")
        open_prefs(ed)
        t.eq((int(_val(ed, "volM")), _checked(ed, "keysCommon")), (50, True), "設定画面も初期値")
        t.ok(ed.js("window._dbg.rt.camRotSpeed") == 1, "カメラ速度も等倍")
        hover_3d(ed)
        ed.key("h")
        wait_until(ed, "window._dbgApp.aux().show===false", label="Hが既定の割り当てへ戻っている")
        t.no_errors()

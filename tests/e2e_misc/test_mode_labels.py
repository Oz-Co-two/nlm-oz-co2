"""各ペインの左上のモードの表示（例: NOTES ［TAB］ LIGHTING）: 「［TAB］ 次の画面名」の所をクリックしても、Tab キーと同じ切り替えになる
（MEDIA⇄PREVIEW・NLE⇄INFO・NOTES⇄LIGHTING）。"""
from misc_helpers import click_sel, open_fixture_ready, wait_until


def _main(ed, sel):
    return ed.js(f"document.querySelector('{sel} .mlMain').textContent")


def _wait_main(ed, sel, text):
    """表示の書き換え（アイコンの読み込みを待つ非同期）が終わるまで待つ"""
    wait_until(ed, f"(()=>{{const e=document.querySelector('{sel} .mlMain');return !!e&&e.textContent==='{text}'}})()", label=f"{sel} の表示が {text}")


def test_mode_label_click_switches(t):
    '''「［TAB］ 次の画面名」をクリックするとその画面へ切り替わり、もう一度で戻る（3か所とも）。ツールチップは「クリックで … へ切り替え」。
    クリックは下の3Dビューへ通さない（ノーツを置かない）。今の画面名の文字はクリックを下へ通す（3Dの操作を邪魔しない）'''
    ed = open_fixture_ready(t, 'rich')
    n0 = ed.js("window._dbgApp.state().counts.notes")
    # NOTES ⇄ LIGHTING（3Dビュー）
    t.eq(_main(ed, "#mainModeLabel"), "NOTES", "最初は NOTES")
    t.eq(ed.js("document.querySelector('#mainModeLabel .mlNext').title"), "クリックで LIGHTING へ切り替え", "ツールチップ")
    click_sel(ed, "#mainModeLabel .mlNext", "［TAB］ LIGHTING")
    wait_until(ed, "window._dbgApp.state().lightMode===true", label="LIGHTING へ")
    _wait_main(ed, "#mainModeLabel", "LIGHTING")
    click_sel(ed, "#mainModeLabel .mlNext", "［TAB］ NOTES")
    wait_until(ed, "window._dbgApp.state().lightMode===false", label="NOTES へ戻る")
    t.eq(ed.js("window._dbgApp.state().counts.notes"), n0, "クリックで3Dにノーツを置かない")
    # NLE ⇄ INFO
    t.eq(_main(ed, "#nodeColModeLabel"), "NLE", "最初は NLE")
    click_sel(ed, "#nodeColModeLabel .mlNext", "［TAB］ INFO")
    wait_until(ed, "window._dbgApp.view()==='info'", label="INFO へ")
    _wait_main(ed, "#nodeColModeLabel", "INFO")
    click_sel(ed, "#nodeColModeLabel .mlNext", "［TAB］ NLE")
    wait_until(ed, "window._dbgApp.view()==='nle'", label="NLE へ戻る")
    # MEDIA ⇄ PREVIEW
    t.eq(_main(ed, "#pvModeLabel"), "MEDIA", "最初は MEDIA")
    click_sel(ed, "#pvModeLabel .mlNext", "［TAB］ PREVIEW")
    wait_until(ed, "document.getElementById('bodyPv').classList.contains('on')", label="PREVIEW へ")
    _wait_main(ed, "#pvModeLabel", "PREVIEW")
    click_sel(ed, "#pvModeLabel .mlNext", "［TAB］ MEDIA")
    wait_until(ed, "document.getElementById('tabFolder').classList.contains('on')", label="MEDIA へ戻る")
    # 今の画面名の文字・アイコンはクリックを下へ通す（従来どおり）
    t.eq(ed.js("getComputedStyle(document.querySelector('#mainModeLabel .mlMain')).pointerEvents"), "none", "画面名の文字はクリックを通す")
    t.no_errors()

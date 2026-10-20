"""英語表示の訳し漏れ: 英語で起動して主な画面・メニュー・パネルを開き、画面の文字・ツールチップ・キャンバスに描いた文字・
画面下部のメッセージに日本語が残っていないか（english_ui_helpers の見張り）。日本語で使った後に英語へ切り替えた時に
作り済みの画面（INFOのノード・ショートカット一覧など）が日本語のまま残らないかも確かめる"""
from pathlib import Path

from english_ui_helpers import SCAN_JS, found, nle, scan, start_english, tab_over, tour
from misc_helpers import close_prefs, open_prefs, wait_until

OUT = Path(__file__).resolve().parents[2] / "test-out" / "english_ui.txt"


def _report(t, items, label):
    """見つかった日本語を test-out/english_ui.txt にも書く（失敗の要約では長い文が切れるため）"""
    lines = [f"{s}  ← {where}" for s, where in items]
    if lines:
        OUT.parent.mkdir(exist_ok=True)
        with OUT.open("a", encoding="utf-8") as f:
            f.write(f"## {label}（{len(lines)}件）\n" + "\n".join(lines) + "\n")
    t.eq(lines, [], label + "（全文は test-out/english_ui.txt）")


def test_english_ui_no_japanese(t):
    '''英語で起動→主な画面（MEDIA/PREVIEW/NLE/INFO/NOTES/LIGHTING・パイ・パレット・ファイルメニュー・環境設定の全タブ・右クリックメニュー・
    難易度のメニュー・譜面チェックの2タブ・自動ライティング・難易度を測る・書き出しの不足の知らせ）に日本語が出ない'''
    ed = start_english(t)
    tour(ed)
    _report(t, found(ed), "英語表示で見えた日本語")
    t.no_errors()


def test_edit_only_english_wording(t):
    '''単独編集（Edit only）の英語の文言: スイッチのツールチップ・3Dの隅の表示・他のレーンのノーツをクリックした時の帯・早見表の行（利用者に提示して了承済みの文言）'''
    from english_ui_helpers import edit_only_switch_xy
    ed = start_english(t, "rich")
    wait_until(ed, "window._dbgApp.nle().clips.length===2", label="素材の読込")
    x, y = edit_only_switch_xy(ed, 1)
    ed.click(x, y)
    wait_until(ed, "window._dbgApp.nle().editOnly===1", label="Notes 2 を単独編集")
    ed.move(x + 20, y); ed.wait(0.2)
    t.eq(ed.js("document.getElementById('ndcv').title"),
         "Edit only this lane — 3D editing goes to this lane only. Other lanes can't be edited.", "スイッチのツールチップ")
    t.eq(ed.js("document.querySelector('#eoInd .eoIndMain').textContent"), "✎ Edit only: Notes 2", "3Dの隅の表示")
    o = max((o for o in ed.js("window._dbgApp.objScreen()") if o["kind"] == "note" and o["inView"] and o["tr"] == 0), key=lambda o: o["sy"])
    ed.move(o["sx"], o["sy"]); ed.wait(0.15); ed.click(o["sx"], o["sy"])
    wait_until(ed, "document.getElementById('eoBand').classList.contains('on')", label="帯")
    t.eq(ed.js("[document.querySelector('#eoBand .eoMsg').textContent,...[...document.querySelectorAll('#eoBand button')].map(b=>b.textContent)]"),
         ["This note is in Notes 3 (Edit only: Notes 2)", "Edit only Notes 3", "Turn off Edit only", "Keep"], "帯の文言とボタン")
    rows = ed.js("[...document.querySelectorAll('#nodeKeys .mkrow')].map(r=>r.textContent)")
    t.ok("Edit only (note lane)E" in rows, f"NLE の早見表に E の行: {rows}")
    t.no_errors()   # 画面全体の日本語の点検は test_english_ui_no_japanese（rich の曲名・クリップ名は素材の日本語なのでここでは見ない）


def test_link_english_wording(t):
    '''リンクしたクリップの英語の文言: 親を選ぶ画面・リンクしたクリップの右クリック・分割できない帯・早見表の行'''
    from english_ui_helpers import link_tour
    ed = start_english(t, "basic")
    link_tour(ed)   # 親を選ぶ画面→リンク→右クリック→分割できない帯→難易度間コピーの確認（キャンセル）
    t.eq(len([c for c in ed.js("window._dbgApp.nle().clips") if c["link"]]), 2, "リンクできた")
    texts = [s for s, _ in found(ed)]
    t.eq(texts, [], "日本語が出ない")
    kid = next(c for c in ed.js("window._dbgApp.nle().clips") if c["link"] and not c["par"])
    g = nle(ed, kid["beat"] + 1)
    v1 = ed.js("window._dbgApp.nle().vp.n[1]")
    ed.click(g["x"], min(g["notes"][kid["track"]] + g["laneH"] * 0.7, v1 - 3), button="right"); ed.wait(0.4)
    items = ed.js("[...document.querySelectorAll('#ctxmenu > button')].map(b=>b.textContent)")
    for w in ("Jump to parent", "Make this the parent", "Unlink", "🔗 Link with clips at the same position in other difficulties…"):
        t.ok(w in items, f"子の右クリックに「{w}」: {items}")
    ed.key("Escape")
    rows = ed.js("[...document.querySelectorAll('#nodeKeys .mkrow')].map(r=>r.textContent)")
    t.ok("Link / Paste linkedK ／ Ctrl + Shift + V" in rows, f"NLE の早見表の行: {rows}")
    t.no_errors()


def test_switch_to_english_later(t):
    '''日本語でINFO・NLEを開いて作り済みにしてから、環境設定で English に切り替える→作り済みの画面にも日本語が残らない'''
    ed = t.fresh("basic")
    wait_until(ed, "!document.getElementById('bootCover')", label="起動中の覆いが外れる")
    g = nle(ed)
    tab_over(ed, g["left"] + g["w"] * 0.6, g["lanes"] + 40)   # INFO（カードを作らせる）
    tab_over(ed, g["left"] + g["w"] * 0.6, g["lanes"] + 40)   # NLE へ戻す
    open_prefs(ed)
    ed.js("(()=>{const s=document.getElementById('langSel'); s.value='en'; s.onchange(); return 1})()")
    wait_until(ed, "document.getElementById('mFileBtn').textContent.trim()==='File'", label="英語に切り替わる")
    close_prefs(ed)
    ed.js("(()=>{const e=document.getElementById('errToast'); if(e) e.textContent=''; return 1})()")   # 切り替える前（日本語の時）に出た通知は対象外
    ed.js(SCAN_JS)
    scan(ed, "切替後 NLE")
    tab_over(ed, g["left"] + g["w"] * 0.6, g["lanes"] + 40); scan(ed, "切替後 INFO")
    tab_over(ed, g["left"] + g["w"] * 0.6, g["lanes"] + 40); scan(ed, "切替後 NLE（INFOから戻った後）")
    tab_over(ed, 280, 300); scan(ed, "切替後 PREVIEW"); tab_over(ed, 280, 300); scan(ed, "切替後 MEDIA")
    _report(t, found(ed), "切り替えた後に残っていた日本語")
    t.no_errors()

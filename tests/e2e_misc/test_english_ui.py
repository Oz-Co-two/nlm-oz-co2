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

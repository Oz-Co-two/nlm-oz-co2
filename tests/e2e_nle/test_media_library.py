"""MEDIA の「記録したライブラリ」・詳細表示・並べ替え・絞り込み・ドラッグの決まり（2026-10-12）。
素材は tools/fixtures/media_lib（作り直しは tools/fixtures/make_media_lib.py。中身の説明もそこ）:
  Alpha（v2・Standard H/Ex/E+ と OneSaber Ex・音源3秒・カバー）/ Beta（v3 の譜面・Standard E/N/H・音源2秒）/
  Gamma（v4・Standard Ex・長さ61.5秒）/ Delta（キー無し・音源無し・Standard H(Chroma推奨)/E+(Noodle必須) と Lawless Ex）/ Extras の音楽・画像
記録は config/library.json に書いて loadNativeLibs（起動時と同じ処理）を呼ぶ（lib_helpers）。ネット・NLM推定の値は /__lib/extra の応答を
ページ内で差し替え、プレイ記録は <データフォルダ>/PlayerData.dat に置く"""
import json
import shutil
import time
from datetime import datetime
from pathlib import Path

from e2e_helpers import wait_until, counts
from nle_helpers import clips, scr, lane_y, take_errors, menu, nle, nle_mouse, undo
from lib_helpers import (LIB, REL, open_lib, lib, lib_id, map_hash, record_libs, wait_scanned, set_view, head_xy, row_xy, row_names,
                         drag_from, click_sel, center, open_filter, close_filter, filt_range, filt_diff, filt_mode, filt_check, install_extra)

T = lambda y, m, d: int(datetime(y, m, d, 12).timestamp())
EXTRA = {
    REL["a"]: {"net": {"src": "dump", "match": "hash", "key": "1a01", "uploaded": T(2024, 5, 1), "up": 90, "down": 10,
                       "ranked": {"bl": True, "blq": False, "ss": True, "ssq": False}, "tags": ["tech", "anime"],
                       "diffs": {"Standard/Expert": {"bl": 7.25}, "Standard/ExpertPlus": {"bl": 9.5, "ss": 8.1}}}},
    REL["b"]: {"net": {"src": "dump", "match": "key", "key": "1b02", "uploaded": T(2023, 1, 1), "up": 5, "down": 5, "tags": [], "diffs": {}},
               "est": {"version": "0.1.0", "diffs": {"Standard/Hard": {"stars": 4.56}, "Standard/Easy": {"skipped": "tooFewNotes"}}}},
    REL["c"]: {"net": {"src": "none"}},
    REL["d"]: {"net": {"src": "none"}, "est": {"version": "0.1.0", "diffs": {"Standard/ExpertPlus": {"stars": 11.11}}}},
}
# 初期の並び（モードの初期値＝Standard だけ）: 曲は記録の走査の順、その後に譜面フォルダの外のファイル
NATURAL = [("Alpha Song", "Standard/Hard"), ("Alpha Song", "Standard/Expert"), ("Alpha Song", "Standard/ExpertPlus"),
           ("Beta Song", "Standard/Easy"), ("Beta Song", "Standard/Normal"), ("Beta Song", "Standard/Hard"),
           ("Gamma V4", "Standard/Expert"), ("Delta Noodle", "Standard/Hard"), ("Delta Noodle", "Standard/ExpertPlus"),
           ("art", ""), ("loose", "")]


def _count(ed):
    return lib(ed)["count"]


def _nle_target(ed, beat, lk="n", track=0):
    return scr(ed, beat)["x"], lane_y(ed, lk, track)


def _clip_at(ed, beat, lk="n"):
    cs = [c for c in clips(ed, lk) if c["beat"] == beat]
    return cs[0] if cs else None


def _drop_notes(ed, x0, y0, beat=8):
    """(x0,y0) の項目を Notes のレーンの拍 beat へドロップし、できたクリップを返してから Undo で消す（次のドロップのためにレーンを空ける）"""
    n0 = len(clips(ed))
    drag_from(ed, x0, y0, *_nle_target(ed, beat))
    try:
        wait_until(ed, f"window._dbgApp.nle().clips.length==={n0 + 1}", label="ドロップ")
    except AssertionError as e:   # 何が起きたかの手がかり（下のメッセージ・ページ内のエラー・ドラッグした物）
        toast = ed.js("document.getElementById('errToast').textContent")
        under = ed.js("(e=>e&&(e.closest('.libItem,.ltRow')||e).textContent)(document.elementFromPoint(%s,%s))" % (x0, y0))
        raise AssertionError(f"{e}\n  メッセージ: {toast}\n  エラー: {ed.errors()}\n  始点: {(x0, y0)} {under}")
    c = _clip_at(ed, beat)
    nle_mouse(ed)
    undo(ed)
    wait_until(ed, f"window._dbgApp.nle().clips.length==={n0}", label="ドロップの Undo")
    return c


def test_recorded_library_scan(t):
    '''記録したライブラリがカタログに出て走査され、曲・音楽・画像がグリッドに並ぶ（v4 の曲も一覧には出る）。件数は「4曲・9譜面（全4曲）」'''
    ed = open_lib(t)
    s = lib(ed)
    nat = [l for l in s["libs"] if l["native"]]
    t.eq([(l["name"], l["state"], l["songs"], l["items"]) for l in nat], [("media_lib", "ok", 4, 6)], "カタログ・状態・曲の数（＋音楽1・画像1）")
    t.eq(s["view"], "grid", "初めはグリッド")
    t.eq(s["grid"], ["Alpha Song", "Beta Song", "Gamma V4", "Delta Noodle", "art", "loose"], "グリッドの並び（走査の順）")
    t.eq(s["count"], "4曲・9譜面（全4曲）", "件数（曲以外は数えない・モードの初期値は Standard だけ）")
    t.eq(row_names(ed), NATURAL, "一覧の行（1行＝1難易度）")
    cats = ed.js("[...document.querySelectorAll('#libList .libCat')].map(e=>e.textContent)")
    t.ok(any("media_lib" in c for c in cats), f"左の一覧に記録したフォルダ: {cats}")
    t.ok(not s["active"] and ed.js("document.getElementById('libFiltClear').disabled"), "モードの初期値だけでは絞り込み中にしない（［解除］は押せない）")
    wait_until(ed, "window._dbgApp.lib().libs.find(l=>l.native).covers>=2", label="カバー・画像の読み込み（見えている物から）")
    t.no_errors()


def test_detail_view_columns_persist(t):
    '''詳細表示に切り替える（大きさのスライダーは文字の大きさになる）・見出しの右クリックで列の表示/非表示・開き直しても表示・列・並べ替え・絞り込みが残る（起動時に記録を読む）'''
    ed = open_lib(t, extra=EXTRA)
    set_view(ed, "detail")
    sl = lib(ed)["slider"]
    t.eq((sl["shown"], sl["min"], sl["max"], sl["value"]), (True, 11, 18, 13), "詳細表示では大きさのスライダーは一覧の文字の大きさ（11〜18px・初期値13）")
    s = lib(ed)
    t.eq(s["cols"], s["defCols"], "初期の列")
    t.eq(s["defCols"], ["cover", "name", "artist", "mapper", "diff", "stars", "njs", "nps", "len", "bpm", "uploaded", "dl", "plays"], "初期の列（取り決めどおり）")
    t.ok(s["rendered"] == 11, f"行が描かれる: {s['rendered']}")
    x, y = head_xy(ed, "artist")
    ed.click(x, y, button="right")
    wait_until(ed, "!!document.getElementById('libColMenu')", label="列のメニュー")
    click_sel(ed, "#libColMenu input[data-col=notes]")
    click_sel(ed, "#libColMenu input[data-col=artist]")
    s = lib(ed)
    t.ok("notes" in s["cols"] and "artist" not in s["cols"], f"ノーツの列を出し、アーティストの列を隠す: {s['cols']}")
    t.eq(json.loads(ed.js("localStorage.getItem('bsnm_libCols')")), s["cols"], "列は bsnm_libCols に保存")
    ed.key("Escape")
    x, y = head_xy(ed, "stars")
    ed.click(x, y)
    wait_until(ed, "(s=>s.sort&&s.sort.col==='stars')(window._dbgApp.lib())", label="並べ替え")
    filt_diff(ed, "Expert")
    close_filter(ed)
    t.eq(_count(ed), "2曲・2譜面（全4曲）", "Expert だけ")
    ed.wait(0.6)   # 環境設定のミラー（config/settings.json）へ書き戻されるのを待つ
    ed.reload(clear_storage=False)   # 記録（library.json）は残る＝起動時に読む
    wait_scanned(ed)
    ed.wait(0.2)
    s = lib(ed)
    t.eq((s["view"], s["sort"], s["filter"]["diffs"]), ("detail", {"col": "stars", "dir": 1}, ["Expert"]), "開き直しても表示・並べ替え・絞り込みが残る")
    t.ok("notes" in s["cols"] and "artist" not in s["cols"], "列も残る")
    t.eq(s["count"], "2曲・2譜面（全4曲）", "件数")
    t.no_errors()


def test_cells_values(t):
    '''詳細表示のセル: 難易度の印（Standard 以外はモード名）・★（BL／NLM推定は言葉と色・ツールチップ／ノーツ不足）・長さ・BPM・NJS・日付・反応時間/JD・必要な Mod'''
    ed = open_lib(t, extra=EXTRA)
    set_view(ed, "detail")
    cell = lambda i, c: ed.js(f"window._dbgApp.libCell({i},{json.dumps(c)})")
    t.eq([cell(i, "diff")["text"] for i in range(9)], ["H", "Ex", "E+", "E", "N", "H", "Ex", "H", "E+"], "難易度の印")
    a = cell(2, "stars")
    t.eq((a["text"], "ltEst" in a["cls"]), ("9.50", False), "公式の BL★")
    b = cell(5, "stars")
    t.eq((b["text"], "ltEst" in b["cls"]), ("NLM推定 4.56", True), "NLM推定は言葉を付けて色を変える")
    t.ok("公式の★ではありません" in b["title"], f"NLM推定のツールチップ: {b['title']}")
    e = cell(3, "stars")
    t.ok("20個未満" in e["title"], f"ノーツが少なくて計算していない理由: {e}")
    t.eq((cell(0, "len")["text"], cell(6, "len")["text"], cell(7, "len")["text"]), ("0:03", "1:02", ""), "長さ（音源の長さ・分:秒。v4 は Info の長さ）")
    t.eq((cell(0, "bpm")["text"], cell(0, "njs")["text"], cell(1, "nps")["text"]), ("120", "14", "4.27"), "BPM・NJS・NPS")
    t.eq((cell(0, "uploaded")["text"], cell(0, "dl")["text"], cell(6, "uploaded")["text"]), ("2024-05-01", "2025-01-10", ""), "アップロード日・ダウンロード日（全曲データに無い曲は空欄）")
    # 隠れている列も同じ描き方で値を確かめる
    # 反応時間・JD（ゲームの式）: BPM120＝1拍0.5秒。hjd は 4 から NJS×0.5×hjd≦17.999 まで半分にする
    #   Alpha Hard（NJS14・オフセット0）: 14×0.5×4=28>18 → hjd=2 → RT=1.0秒・JD=14×0.5×2×2=28m
    #   Alpha Expert（NJS16・オフセット-0.5）: hjd=2-0.5=1.5 → RT=0.75秒・JD=16×0.5×1.5×2=24m
    t.eq((cell(0, "rt")["text"], cell(0, "jd")["text"], cell(1, "rt")["text"], cell(1, "jd")["text"]), ("1000ms", "28.0m", "750ms", "24.0m"),
         "反応時間・ジャンプ距離（NJS・オフセット・BPM から）")
    t.eq((cell(7, "mods")["text"], cell(8, "mods")["text"]), ("", "Noodle"), "必要な Mod（推奨の Chroma は出さない）")
    t.ok("Chroma" in cell(7, "mods")["title"], "推奨の Mod はツールチップ")
    t.eq((cell(0, "rating")["text"], cell(0, "ranked")["text"], cell(2, "ranked")["text"]), ("90.0%", "未ランク", "BL / SS"), "高評価率・ランク状態（その難易度に★がある時だけ BL）")
    t.eq((cell(4, "ranked")["text"], cell(0, "key")["text"], cell(7, "key")["text"]), ("", "1a01", ""), "キーだけで当たった曲はランク状態を出さない・キー")
    t.eq((cell(0, "tags")["text"], cell(9, "name")["text"]), ("tech, anime", "art画像"), "タグ・曲以外の項目は名前と種類だけ")
    t.no_errors()


def test_sort_and_nulls_bottom(t):
    '''見出しのクリックで並べ替え（1回目＝昇順、もう1回＝降順）。値の無い行はどちら向きでも一番下。グリッドの並びにも効く'''
    ed = open_lib(t, extra=EXTRA)
    set_view(ed, "detail")
    nulls = [("Alpha Song", "Standard/Hard"), ("Beta Song", "Standard/Easy"), ("Beta Song", "Standard/Normal"), ("Gamma V4", "Standard/Expert"),
             ("Delta Noodle", "Standard/Hard"), ("art", ""), ("loose", "")]
    ed.click(*head_xy(ed, "stars"))
    wait_until(ed, "(s=>s.sort&&s.sort.dir===1)(window._dbgApp.lib())", label="昇順")
    t.eq(row_names(ed), [("Beta Song", "Standard/Hard"), ("Alpha Song", "Standard/Expert"), ("Alpha Song", "Standard/ExpertPlus"),
                         ("Delta Noodle", "Standard/ExpertPlus")] + nulls, "★の昇順（NLM推定も★として並べる）・値の無い行は下")
    t.eq(lib(ed)["grid"], ["Beta Song", "Alpha Song", "Delta Noodle", "Gamma V4", "art", "loose"], "グリッドは各曲の最初の行の順")
    t.eq(ed.js("document.querySelector('#libTable .ltH[data-col=stars] .ltArrow').textContent"), "▲", "昇順の印")
    ed.click(*head_xy(ed, "stars"))
    wait_until(ed, "(s=>s.sort&&s.sort.dir===-1)(window._dbgApp.lib())", label="降順")
    t.eq(row_names(ed), [("Delta Noodle", "Standard/ExpertPlus"), ("Alpha Song", "Standard/ExpertPlus"), ("Alpha Song", "Standard/Expert"),
                         ("Beta Song", "Standard/Hard")] + nulls, "★の降順・値の無い行はやはり下")
    ed.click(*head_xy(ed, "len"))
    wait_until(ed, "(s=>s.sort&&s.sort.col==='len'&&s.sort.dir===1)(window._dbgApp.lib())", label="長さで並べる")
    t.eq([n for n, _ in row_names(ed)], ["Beta Song"] * 3 + ["Alpha Song"] * 3 + ["Gamma V4", "Delta Noodle", "Delta Noodle", "art", "loose"],
         "長さの昇順（音源の無い曲・曲以外は下）")
    ed.click(*head_xy(ed, "name"))
    wait_until(ed, "(s=>s.sort&&s.sort.col==='name')(window._dbgApp.lib())", label="曲名で並べる")
    t.eq([n for n, _ in row_names(ed)], ["Alpha Song"] * 3 + ["art"] + ["Beta Song"] * 3 + ["Delta Noodle"] * 2 + ["Gamma V4", "loose"],
         "曲名の昇順（大文字小文字を区別しない）")
    t.eq(json.loads(ed.js("localStorage.getItem('bsnm_libSort')")), {"col": "name", "dir": 1}, "並べ替えは bsnm_libSort に保存")
    t.no_errors()


def test_filter_panel(t):
    '''絞り込み: 範囲（★・長さ・NJS・NPS・BPM）・難易度・モード（初期値は Standard だけ）・ランク・必要な Mod・件数・［解除］。曲の条件で絞っている間は曲以外を隠す'''
    ed = open_lib(t, extra=EXTRA)
    filt_range(ed, "stars", "5", "")
    t.eq(_count(ed), "2曲・3譜面（全4曲）", "★5以上（NLM推定の11.11も入る）")
    s = lib(ed)
    t.eq(s["grid"], ["Alpha Song", "Delta Noodle"], "グリッドは合う難易度が1つでもある曲だけ（曲以外は隠す）")
    t.ok(s["active"] and not ed.js("document.getElementById('libFiltClear').disabled"), "絞り込み中は［解除］を押せる")
    filt_diff(ed, "ExpertPlus")
    t.eq(_count(ed), "2曲・2譜面（全4曲）", "＋難易度 E+ だけ")
    click_sel(ed, "#libFiltPanel .lfReset")
    wait_until(ed, "!window._dbgApp.lib().active", label="解除")
    t.eq((_count(ed), lib(ed)["filter"]["modes"]), ("4曲・9譜面（全4曲）", ["Standard"]), "解除でモードは初期値（Standard だけ）に戻る")
    filt_mode(ed, "OneSaber")
    filt_mode(ed, "Lawless")
    t.eq(_count(ed), "4曲・11譜面（全4曲）", "モードを足す（OneSaber・Lawless）")
    t.ok(lib(ed)["condActive"], "モードを初期値から変えたら絞り込み中")
    filt_mode(ed, "Standard")
    t.eq((_count(ed), row_names(ed)), ("2曲・2譜面（全4曲）", [("Alpha Song", "OneSaber/Expert"), ("Delta Noodle", "Lawless/Expert")]), "Standard を外す")
    click_sel(ed, "#libFiltPanel .lfReset")
    wait_until(ed, "!window._dbgApp.lib().active", label="解除")
    filt_check(ed, "noMods")
    t.eq((_count(ed), ("Delta Noodle", "Standard/Hard") in row_names(ed)), ("4曲・8譜面（全4曲）", True), "Noodle が必要な難易度だけ除く（Chroma の推奨は除かない）")
    filt_check(ed, "noMods")
    filt_range(ed, "len", "0:03", "")
    t.eq(_count(ed), "2曲・4譜面（全4曲）", "長さ 3秒以上（分:秒。音源の無い曲は入らない）")
    filt_range(ed, "len", "", "")
    filt_range(ed, "njs", "15", "17")
    t.eq(_count(ed), "3曲・3譜面（全4曲）", "NJS 15〜17")
    filt_range(ed, "njs", "", "")
    filt_range(ed, "bpm", "", "130")
    t.eq(_count(ed), "2曲・4譜面（全4曲）", "BPM 130 以下（Alpha 120・Gamma 100）")
    filt_range(ed, "bpm", "", "")
    filt_range(ed, "nps", "4", "")
    t.eq(_count(ed), "3曲・4譜面（全4曲）", "NPS 4 以上")
    filt_range(ed, "nps", "", "")
    open_filter(ed)
    ed.js("(s=>{ s.value='bl'; s.dispatchEvent(new Event('change')); return 1; })(document.querySelector('#libFiltPanel .lfRanked'))")
    ed.wait(0.15)
    t.eq((_count(ed), row_names(ed)), ("1曲・2譜面（全4曲）", [("Alpha Song", "Standard/Expert"), ("Alpha Song", "Standard/ExpertPlus")]), "BL ランク（その難易度に BL★がある）")
    ed.js("(s=>{ s.value='unranked'; s.dispatchEvent(new Event('change')); return 1; })(document.querySelector('#libFiltPanel .lfRanked'))")
    ed.wait(0.15)
    t.eq(_count(ed), "4曲・7譜面（全4曲）", "未ランク")
    ed.js("(s=>{ s.value='all'; s.dispatchEvent(new Event('change')); return 1; })(document.querySelector('#libFiltPanel .lfRanked'))")
    # アップロード日（日付の入力欄は文字を打ち込めないので、値を入れて input を送る）
    ed.js("(i=>{ i.value='2024-01-01'; i.dispatchEvent(new Event('input')); return 1; })(document.querySelector('#libFiltPanel .lfRow[data-k=up] .lfLo'))")
    ed.wait(0.15)
    t.eq(_count(ed), "1曲・3譜面（全4曲）", "アップロード日 2024-01-01 以降（全曲データに無い曲は入らない）")
    t.eq(json.loads(ed.js("localStorage.getItem('bsnm_libFilter')"))["up"], ["2024-01-01", ""], "条件は bsnm_libFilter に保存")
    close_filter(ed)
    click_sel(ed, "#libFiltClear")
    wait_until(ed, "!window._dbgApp.lib().active", label="上の［解除］")
    t.eq(_count(ed), "4曲・9譜面（全4曲）", "上の［解除］でも全部外れる")
    t.no_errors()


def test_search_and_catalog_scope(t):
    '''検索欄（曲名・アーティスト・マッパーの部分一致・大文字小文字を区別しない）と、左のカタログで選んだ範囲の中の件数'''
    ed = open_lib(t)
    click_sel(ed, "#libSearch")
    ed.call("Input.insertText", text="beta")
    wait_until(ed, "window._dbgApp.lib().count.startsWith('1曲')", label="検索")
    s = lib(ed)
    t.eq((s["count"], s["grid"]), ("1曲・3譜面（全4曲）", ["Beta Song"]), "曲名で探す（曲以外は名前が合わないので隠れる）")
    ed.key("a", ctrl=True)
    ed.call("Input.insertText", text="ARTIST ALPHA")
    wait_until(ed, "window._dbgApp.lib().grid.join()==='Alpha Song'", label="アーティストで探す")
    ed.key("a", ctrl=True)
    ed.call("Input.insertText", text="mapperd")
    wait_until(ed, "window._dbgApp.lib().grid.join()==='Delta Noodle'", label="マッパーで探す")
    ed.key("a", ctrl=True)
    ed.call("Input.insertText", text="loose")
    wait_until(ed, "window._dbgApp.lib().grid.join()==='loose'", label="音楽ファイルの名前")
    t.eq(_count(ed), "0曲・0譜面（全4曲）", "曲は0")
    ed.key("Escape")
    wait_until(ed, "window._dbgApp.lib().filter.q===''", label="Esc で検索を消す")
    click_sel(ed, "#libList .libCat:nth-child(2)")   # アセット
    wait_until(ed, "window._dbgApp.lib().cat==='アセット'", label="アセットを選ぶ")
    t.eq((_count(ed), lib(ed)["grid"]), ("", []), "曲の無い範囲は件数を出さない")
    t.no_errors()


def test_row_selection(t):
    '''詳細表示の選択: クリックで1行・Ctrl+クリックで追加/解除・Shift+クリックで範囲（Ctrl+Shift で範囲を足す）'''
    ed = open_lib(t)
    set_view(ed, "detail")
    sel = lambda: [(r["name"], r["key"]) for r in lib(ed)["sel"]]
    ed.click(*row_xy(ed, 1))
    t.eq(sel(), [NATURAL[1]], "クリック＝1行")
    ed.click(*row_xy(ed, 3), ctrl=True)
    t.eq(sel(), [NATURAL[1], NATURAL[3]], "Ctrl＋クリック＝追加")
    ed.click(*row_xy(ed, 5), shift=True)
    t.eq(sel(), NATURAL[3:6], "Shift＋クリック＝最後にクリックした行からの範囲")
    ed.click(*row_xy(ed, 7), shift=True, ctrl=True)
    t.eq(sel(), NATURAL[3:8], "Ctrl＋Shift＝範囲を足す")
    ed.click(*row_xy(ed, 4), ctrl=True)
    t.eq(sel(), [NATURAL[3]] + NATURAL[5:8], "Ctrl＋クリック＝解除")
    t.eq(ed.js("document.querySelectorAll('#libTable .ltRow.sel').length"), 4, "選んだ行は色が付く")
    sr = ed.js("window._dbg.rt.libSelectedRows()")
    t.eq((sr[0]["rel"], sr[0]["char"], sr[0]["diff"], sr[0]["native"]), (REL["b"], "Standard", "Easy", True), "選んだ行の取得（次の担当用）")
    t.no_errors()


def test_row_drag_takes_that_difficulty(t):
    '''詳細表示の行のドラッグ＝その行の難易度（別の難易度・別のモードも）を今開いている難易度（Hard）へ入れる。NJS もその難易度の物'''
    ed = open_lib(t, "basic")
    set_view(ed, "detail")
    drag_from(ed, *row_xy(ed, 2), *_nle_target(ed, 8))
    wait_until(ed, "window._dbgApp.nle().clips.length===2", label="E+ の行のドロップ")
    c = _clip_at(ed, 8)
    t.eq((c["label"], c["n"]["notes"]), ("Alpha Song", 24), "Alpha の Expert+（24ノーツ）が入る")
    pj = json.loads(ed.js("window._dbg.rt.buildProjectText()"))
    t.eq(pj["njsCfg"].get("hardstandard.dat"), {"njs": 18, "offset": 0}, "今の難易度（Hard）の NJS は入れた譜面（E+）の物")
    t.ok("Expert+" in ed.js("document.getElementById('errToast').textContent"), "どの難易度を入れたかを出す")
    filt_mode(ed, "OneSaber")
    close_filter(ed)
    i = row_names(ed).index(("Alpha Song", "OneSaber/Expert"))
    t.eq(_drop_notes(ed, *row_xy(ed, i), beat=24)["n"]["notes"], 10, "別のモード（OneSaber の Expert・10ノーツ）も入る")
    t.ok("1本" in ed.js("document.getElementById('errToast').textContent"), "モード名もメッセージに出す")
    t.no_errors()


def test_grid_drag_rule_while_filtering(t):
    '''グリッドのカードのドラッグ: 絞り込んでいなければ今開いている難易度と同名（Hard）。絞り込み中は合う難易度に同名があればそれ、無ければ合う中で一番難しい物'''
    from nle_helpers import lib_item_xy
    ed = open_lib(t, "basic", extra=EXTRA)
    t.eq(_drop_notes(ed, *lib_item_xy(ed, "Alpha Song"))["n"]["notes"], 8, "絞り込みなし＝Hard（8ノーツ）")
    filt_diff(ed, "ExpertPlus")
    close_filter(ed)
    c = _drop_notes(ed, *lib_item_xy(ed, "Alpha Song"))
    t.eq(c["n"]["notes"], 24, "合う難易度（E+）に Hard が無い＝合う中で一番難しい E+")
    t.ok("フィルターに合う" in ed.js("document.getElementById('errToast').textContent"), "フィルターから選んだことをメッセージに出す")
    filt_diff(ed, "ExpertPlus")
    filt_diff(ed, "Hard")
    filt_diff(ed, "Expert")
    close_filter(ed)
    t.eq(_drop_notes(ed, *lib_item_xy(ed, "Alpha Song"))["n"]["notes"], 8, "合う難易度に Hard がある＝Hard")
    t.eq(_drop_notes(ed, *lib_item_xy(ed, "Beta Song"))["n"]["notes"], 12, "Beta も Hard（12ノーツ）")
    click_sel(ed, "#libFiltClear")
    filt_range(ed, "stars", "7", "")
    close_filter(ed)
    t.eq(_drop_notes(ed, *lib_item_xy(ed, "Alpha Song"))["n"]["notes"], 24, "★7以上（Expert・E+）＝一番難しい E+")
    t.no_errors()


def test_v4_song_refused_and_music_lane(t):
    '''v4 の曲は NLE のレーンへのドラッグ・曲データを読み込むを断る（一覧には出る）。Musicレーンへは記録したライブラリの音源を /__lib/file から置ける'''
    ed = open_lib(t, "basic")
    set_view(ed, "detail")
    n0 = len(clips(ed))
    drag_from(ed, *row_xy(ed, 6), *_nle_target(ed, 8))
    ed.wait(0.4)
    t.eq(len(clips(ed)), n0, "v4 の曲はクリップにならない")
    t.eq(take_errors(ed, "v4 形式"), 1, "v4 は未対応の案内")
    x, y = row_xy(ed, 6)
    menu(ed, x, y, "曲データを読み込む")
    ed.wait(0.3)
    t.eq(take_errors(ed, "v4 形式"), 1, "曲データを読み込むも断る")
    m = ed.js("window._dbgApp.musicScreen(4)")
    drag_from(ed, *row_xy(ed, 3), m["x"], m["top"] + m["h"] * 0.6)   # Beta（音源2秒）
    wait_until(ed, "window._dbgApp.nle().music.beat===4&&Math.abs(window._dbgApp.nle().music.dur-2)<0.05", label="Musicレーンへのドロップ")
    t.eq(ed.js("window._dbgApp.state().BPM"), 150, "BPM も曲から")
    t.no_errors()


def test_bulk_load_reads_real_info(t):
    '''記録したライブラリの曲の「曲データを読み込む」: 音源・各難易度・曲情報のノードに加え、試聴区間（走査の結果には無い）を本物の Info.dat から読む'''
    ed = open_lib(t)
    set_view(ed, "detail")
    x, y = row_xy(ed, 0)
    menu(ed, x, y, "曲データを読み込む")
    wait_until(ed, "window._dbgApp.nle().music.audio&&Math.abs(window._dbgApp.nle().music.dur-3)<0.05", label="音源の読み込み")
    wait_until(ed, "document.getElementById('errToast').textContent.includes('一括読み込みしました')", label="一括読み込みの終わり")
    g = ed.js("window._dbgApp.infoGraph()")
    meta = [n for n in g["nodes"].values() if n["t"] == "meta"]
    prev = [n for n in g["nodes"].values() if n["t"] == "prev"]
    t.ok(any(n["data"].get("name") == "Alpha Song" for n in meta), "曲情報のノード")
    t.ok(any(n["data"].get("start") == 1 and n["data"].get("dur") == 2 for n in prev), f"試聴区間は Info.dat の値: {[n['data'] for n in prev]}")
    pj = json.loads(ed.js("window._dbg.rt.buildProjectText()"))
    for k in ("hardstandard.dat", "expertstandard.dat", "expertplusstandard.dat"):
        t.ok(pj["difficulties"].get(k, {}).get("sections") or k == pj.get("currentDiff", "").lower(), f"{k} にクリップ")
    t.eq(pj["njsCfg"].get("expertplusstandard.dat"), {"njs": 18, "offset": 0}, "E+ の NJS")
    t.no_errors()


def test_open_folder(t):
    '''「フォルダの場所を開く」: 記録したライブラリの曲＝その譜面フォルダ、音楽ファイル＝そのファイルのあるフォルダ（serve.py がエクスプローラーで開く。テストでは開く関数を差し替え）'''
    ed = open_lib(t)
    import serve   # エディタ（テストのサーバー）を用意した後に読む（前に読むと、サーバーが使っていない古い serve を差し替えてしまう＝本物のエクスプローラーが開く）
    assert Path(serve.DATA_DIR).resolve() == Path(ed.data_dir).resolve(), f"serve がテストのサーバーの物ではありません: {serve.DATA_DIR}"
    set_view(ed, "detail")
    opened = []
    orig = serve.LIBRARY.opener
    serve.LIBRARY.opener = opened.append
    try:
        x, y = row_xy(ed, 1)
        menu(ed, x, y, "フォルダの場所を開く")
        wait_until(ed, "document.getElementById('stat').textContent.includes('フォルダを開きました')", label="曲のフォルダ")
        x, y = row_xy(ed, 10)
        menu(ed, x, y, "フォルダの場所を開く")
        for _ in range(50):
            if len(opened) >= 2:
                break
            ed.wait(0.05)
    finally:
        serve.LIBRARY.opener = orig
    norm = lambda p: str(Path(p).resolve()).lower()
    t.eq([norm(p) for p in opened], [norm(LIB / REL["a"]), norm(LIB / "Extras")], "曲は譜面フォルダ・音楽ファイルはそのフォルダ")
    t.no_errors()


def test_open_folder_browser_folder_is_exe_only(t):
    '''ブラウザ版の一時的なフォルダの曲では「フォルダの場所を開く」はデスクトップ版だけの案内を出す（前の「対応予定」の文言ではない）'''
    from test_media import _add_fake_library, SONG
    from nle_helpers import lib_item_xy
    ed = open_lib(t)
    _add_fake_library(ed)
    menu(ed, *lib_item_xy(ed, SONG), "フォルダの場所を開く")
    t.eq(take_errors(ed, "デスクトップ版（exe）"), 1, "exe 版だけの案内")
    s = lib(ed)
    t.eq(s["count"], "5曲・11譜面（全5曲）", "ブラウザ版のフォルダの曲も一覧・件数に入る（記録したライブラリと一緒に）")
    t.no_errors()


def test_rescan_and_remove(t):
    '''カタログの右クリック「読み直す」で走査し直す／「−」で記録から外す（library.json から消え、フォルダの中身は消さない）'''
    ed = open_lib(t)
    x, y = center(ed, "#libList .libCat:nth-child(3)")
    menu(ed, x, y, "読み直す")
    wait_until(ed, "window._dbgApp.lib().libs.find(l=>l.native).scanning===false&&window._dbgApp.lib().libs.find(l=>l.native).items===6", label="読み直し")
    wait_scanned(ed)
    t.eq(lib(ed)["count"], "4曲・9譜面（全4曲）", "読み直しても同じ曲")
    click_sel(ed, "#libList .libCat:nth-child(3) .libDel")
    wait_until(ed, "!window._dbgApp.lib().libs.some(l=>l.native)", label="外す")
    rec = json.loads((Path(ed.data_dir) / "config" / "library.json").read_text(encoding="utf-8"))
    t.eq(rec["libs"], [], "記録から消える")
    t.eq(lib(ed)["grid"], [], "曲も消える")
    t.ok((LIB / REL["a"] / "Info.dat").is_file(), "フォルダの中身は消さない")
    t.no_errors()


def test_missing_library(t):
    '''記録したフォルダが無い時は薄く表示し、ツールチップで「見つかりません」。クリックで探し直し、見つかれば読み込む'''
    from nle_helpers import open_nle, clear_assets
    clear_assets(t.ed)
    ed = open_nle(t)
    gone = Path(ed.data_dir) / "gone_lib"
    shutil.rmtree(gone, ignore_errors=True)
    record_libs(ed, gone)
    ed.js("window._dbg.rt.loadNativeLibs().then(()=>true)")
    wait_until(ed, "window._dbgApp.lib().libs.some(l=>l.native&&l.state==='missing')", label="見つからない")
    c = ed.js("(c=>({cls:c.className,title:c.title}))([...document.querySelectorAll('#libList .libCat')].find(c=>c.textContent.includes('gone_lib')))")
    t.ok("missing" in c["cls"] and "見つかりません" in c["title"], f"薄く表示・ツールチップ: {c}")
    click_sel(ed, "#libList .libCat.missing")
    wait_until(ed, "!window._dbgApp.lib().libs.find(l=>l.native).scanning", label="探し直し")
    # 無いフォルダは走査を始める前（rescan の応答）で知らせる＝scanning は最初から false のまま。知らせが届くまで待つ
    #（以前は 0.3 秒だけ待っていて、他のテストと同時に回して PC が混んでいると応答が間に合わず落ちた・2026-10-20）
    n = 0
    for _ in range(50):
        n = take_errors(ed, "読み込めませんでした")
        if n:
            break
        ed.wait(0.1)
    ed.wait(0.3)
    n += take_errors(ed, "読み込めませんでした")
    t.eq(n, 1, "まだ無い")
    t.eq(lib(ed)["libs"][-1]["state"], "missing", "見つからないまま")
    shutil.copytree(LIB / REL["b"], gone / REL["b"])
    click_sel(ed, "#libList .libCat.missing")
    wait_scanned(ed)
    t.eq((lib(ed)["libs"][-1]["state"], lib(ed)["libs"][-1]["songs"]), ("ok", 1), "見つかれば読み込む")
    shutil.rmtree(gone, ignore_errors=True)
    t.no_errors()


def test_play_data_columns(t):
    '''プレイ記録（PlayerData.dat）: その難易度のプレイ回数・自己ベスト・フルコンボ・お気に入り。「お気に入りだけ」「未プレイだけ」の絞り込み'''
    ed = open_lib(t)
    h = map_hash(ed, REL["a"]).upper()
    pd = {"localPlayers": [{"levelsStatsData": [
        {"levelId": "custom_level_" + h, "difficulty": 2, "beatmapCharacteristicName": "Standard", "highScore": 123456, "maxCombo": 8,
         "fullCombo": True, "maxRank": 5, "validScore": True, "playCount": 3}],
        "favoritesLevelIds": ["custom_level_" + h]}]}
    (Path(ed.data_dir) / "PlayerData.dat").write_text(json.dumps(pd), encoding="utf-8")
    try:
        ed.js("window._dbg.rt.libRefreshExtra().then(()=>true)")
        wait_until(ed, "window._dbgApp.libCell(0,'plays').text==='3'", label="プレイ記録の読み込み")
        cell = lambda i, c: ed.js(f"window._dbgApp.libCell({i},{json.dumps(c)})")["text"]
        t.eq((cell(0, "plays"), cell(1, "plays"), cell(0, "best"), cell(0, "fc"), cell(0, "fav"), cell(3, "fav")),
             ("3", "", "123,456 (S)", "✓", "♥", ""), "プレイ回数・自己ベスト・FC・お気に入り")
        filt_check(ed, "fav")
        t.eq(_count(ed), "1曲・3譜面（全4曲）", "お気に入りだけ")
        filt_check(ed, "fav")
        filt_check(ed, "unplayed")
        t.eq((_count(ed), ("Alpha Song", "Standard/Hard") in row_names(ed)), ("4曲・8譜面（全4曲）", False), "未プレイだけ（遊んだ Hard を除く）")
    finally:
        (Path(ed.data_dir) / "PlayerData.dat").unlink(missing_ok=True)
    t.no_errors()


def test_exe_add_folder(t):
    '''exe 版の「フォルダを追加」: pywebview の lib_pick_folder（ネイティブのフォルダ選択→記録）で選んだフォルダを走査して並べる。同じフォルダをもう一度選んでも増えない'''
    import sys
    misc = str(Path(__file__).resolve().parents[1] / "e2e_misc")
    if misc not in sys.path:
        sys.path.insert(0, misc)
    from misc_helpers import install_fake_pywebview, native_calls
    from nle_helpers import open_nle, clear_assets
    clear_assets(t.ed)
    ed = open_nle(t)
    import serve   # エディタ（テストのサーバー）を用意した後に読む（前に読むと、サーバーの使っていない古い serve＝手元の config/ に記録してしまう）
    assert Path(serve.DATA_DIR).resolve() == Path(ed.data_dir).resolve(), f"serve がテストのサーバーの物ではありません: {serve.DATA_DIR}"
    ed.js("window._dbg.rt.loadNativeLibs().then(()=>true)")   # 起動時の記録の読み込み（順番に動く）が終わってから「選ぶ」
    install_fake_pywebview(ed)
    picked = serve.LIBRARY.approve_dir(str(LIB))   # 本物の lib_pick_folder はダイアログで選んだフォルダをここで記録して {id,name} を返す
    ed.js(f"window.__nat.queue.lib.push({json.dumps(picked)});true")
    click_sel(ed, "#libAddBtn")
    try:
        wait_scanned(ed)
    except AssertionError as e:   # 何が起きたかの手がかり
        st = json.dumps({k: v for k, v in lib(ed).items() if k in ("libs", "count")}, ensure_ascii=False)
        msg = ed.js("document.getElementById('stat').textContent+' / '+document.getElementById('errToast').textContent")
        raise AssertionError(f"{e}\n  状態: {st}\n  呼び出し: {native_calls(ed)}\n  メッセージ: {msg}\n  エラー: {ed.errors()}")
    t.eq(len(native_calls(ed, "lib_pick_folder")), 1, "ネイティブのフォルダ選択を使う（showDirectoryPicker ではない）")
    t.eq((lib(ed)["count"], [l["name"] for l in lib(ed)["libs"] if l["native"]]), ("4曲・9譜面（全4曲）", ["media_lib"]), "走査して並べる")
    ed.js(f"window.__nat.queue.lib.push({json.dumps(picked)});true")
    click_sel(ed, "#libAddBtn")
    wait_until(ed, "document.getElementById('stat').textContent.includes('すでにライブラリにあります')", label="同じフォルダ")
    t.eq(len([l for l in lib(ed)["libs"] if l["native"]]), 1, "増えない")
    t.no_errors()


def test_virtual_scroll_many_rows(t):
    '''行が多くても見えている行だけを描く（1500行）。一番下までスクロールでき、並べ替え・絞り込みも全部の行に効く'''
    from nle_helpers import open_nle, clear_assets
    clear_assets(t.ed)
    ed = open_nle(t)
    big = Path(ed.data_dir) / "big_lib"
    if not big.exists():
        diffs = [{"_difficulty": d, "_beatmapFilename": d + ".dat", "_noteJumpMovementSpeed": 10 + i, "_noteJumpStartBeatOffset": 0}
                 for i, d in enumerate(["Easy", "Normal", "Hard", "Expert", "ExpertPlus"])]
        for k in range(300):
            f = big / ("%04x (Song %03d - M)" % (k + 1, k))
            f.mkdir(parents=True)
            (f / "Info.dat").write_text(json.dumps({"_version": "2.1.0", "_songName": "Song %03d" % k, "_songAuthorName": "A", "_levelAuthorName": "M",
                                                    "_beatsPerMinute": 100 + k, "_difficultyBeatmapSets": [
                                                        {"_beatmapCharacteristicName": "Standard", "_difficultyBeatmaps": diffs}]}), encoding="utf-8")
    record_libs(ed, big)
    t0 = time.time()
    ed.js("window._dbg.rt.loadNativeLibs().then(()=>true)")
    wait_scanned(ed, timeout=60)
    set_view(ed, "detail")
    s = lib(ed)
    t.eq((len(s["rows"]), s["count"]), (1500, "300曲・1500譜面（全300曲）"), "1500行")
    n_dom = ed.js("document.querySelectorAll('#libTable .ltRow').length")
    t.ok(n_dom < 80, f"描くのは見えている行だけ: {n_dom}行の要素")
    ed.js("(t=>{ t.scrollTop=t.scrollHeight; return 1; })(document.getElementById('libTable'))")
    wait_until(ed, "window._dbgApp.lib().firstRendered>1400", label="一番下までスクロール")
    last = ed.js("[...document.querySelectorAll('#libTable .ltRow')].filter(e=>e.style.display!=='none').map(e=>e._i).sort((a,b)=>b-a)[0]")
    t.eq(last, 1499, "最後の行が描かれる")
    ed.click(*head_xy(ed, "bpm"))
    ed.click(*head_xy(ed, "bpm"))
    wait_until(ed, "(s=>s.sort&&s.sort.col==='bpm'&&s.sort.dir===-1)(window._dbgApp.lib())", label="BPM の降順")
    t.eq(lib(ed)["rows"][0]["name"], "Song 299", "全部の行を並べ替える")
    filt_range(ed, "bpm", "390", "")
    t.eq(_count(ed), "10曲・50譜面（全300曲）", "絞り込み")
    t.no_errors()


def test_drop_to_info(t):
    '''記録したライブラリの曲・画像を INFO へドロップ: 曲＝曲情報・カバー（cover.png）・試聴（本物の Info.dat の値）のノード、画像＝その画像のカバーのノード'''
    import sys
    info = str(Path(__file__).resolve().parents[1] / "e2e_info")
    if info not in sys.path:
        sys.path.insert(0, info)
    from info_helpers import to_info
    from nle_helpers import lib_item_xy
    ed = open_lib(t)
    to_info(ed)
    r = ed.js("(r=>({x:r.left+r.width*0.5,y:r.top+r.height*0.4}))(document.getElementById('inspcol').getBoundingClientRect())")
    nodes = lambda: list(ed.js("window._dbgApp.infoGraph()")["nodes"].values())
    n0 = len(nodes())
    drag_from(ed, *lib_item_xy(ed, "Alpha Song"), r["x"], r["y"])
    wait_until(ed, f"Object.keys(window._dbgApp.infoGraph().nodes).length>={n0 + 3}", label="曲のドロップ")
    new = nodes()[n0:]
    t.eq(sorted(n["t"] for n in new), ["cover", "meta", "prev"], "曲情報・カバー・試聴のノード")
    by = {n["t"]: n["data"] for n in new}
    t.eq((by["meta"].get("name"), by["meta"].get("artist"), by["cover"].get("name")), ("Alpha Song", "Artist Alpha", "cover.png"), "曲情報とカバーの名前")
    t.eq((by["prev"].get("start"), by["prev"].get("dur")), (1, 2), "試聴区間は本物の Info.dat から（走査の結果には無い）")
    n1 = len(nodes())
    drag_from(ed, *lib_item_xy(ed, "art"), r["x"] + 300, r["y"])
    wait_until(ed, f"Object.keys(window._dbgApp.infoGraph().nodes).length>={n1 + 1}", label="画像のドロップ")
    c = nodes()[n1]
    t.eq((c["t"], c["data"].get("name")), ("cover", "art.png"), "画像はその画像のカバーのノード（見えていなくても読んでから置く）")
    wait_until(ed, "document.getElementById('errToast').textContent.includes('カバー画像として配置')", label="配置のメッセージ")
    t.no_errors()


def test_rename_catalog_by_id(t):
    '''カタログの記録したフォルダの表示名をダブルクリックで変える（記録の id で覚える＝開き直しても残る）'''
    ed = open_lib(t)
    x, y = center(ed, "#libList .libCat:nth-child(3) .libCatName")
    ed.click(x, y, count=2)
    wait_until(ed, "document.activeElement&&document.activeElement.closest&&!!document.activeElement.closest('#libList')", label="名前の入力欄")
    ed.key("a", ctrl=True)
    ed.call("Input.insertText", text="マイ譜面")
    ed.key("Enter")
    wait_until(ed, "[...document.querySelectorAll('#libList .libCatName')].some(e=>e.textContent==='マイ譜面')", label="表示名の変更")
    labels = json.loads(ed.js("localStorage.getItem('bsnm_libLabels')"))
    t.eq(labels, {"lib:" + lib_id(ed, "マイ譜面"): "マイ譜面"}, "記録の id で覚える")
    ed.wait(0.6)   # 環境設定のミラーへ書き戻されるのを待つ
    ed.reload(clear_storage=False)
    wait_scanned(ed)
    t.ok(any(l["name"] == "マイ譜面" and l["native"] for l in lib(ed)["libs"]), "開き直しても残る")
    t.no_errors()

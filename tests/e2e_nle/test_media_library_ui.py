"""MEDIA ライブラリの画面の調整（2026-10-12）: 操作部品を見出しの行（MEDIA [TAB] PREVIEW の帯の右）へ寄せて折り返す・「フィルター」のボタンと
効いている条件の数・検索欄の 🔍 と ×・左のカタログの幅のドラッグ・詳細表示の2段の見出し・列の幅を値に合わせる・文字の大きさ（スライダー兼用・Ctrl＋ホイール）。
UI文字サイズ（環境設定の bsnm_uiscale＝#tabFolder の CSS の zoom）が 100% 以外の時も確かめる。
素材は tools/fixtures/media_lib（test_media_library.py と同じ）"""
import json
import re
from pathlib import Path

from e2e_helpers import wait_until, media_lib_record, media_lib_extra, media_lib_mock, media_lib_wait, SAMPLE_DETAILS
from lib_helpers import (open_lib, lib, lib_id, set_view, click_sel, center, row_xy, open_filter, close_filter, filt_range, filt_diff, filt_mode,
                         filt_check, record_libs, install_extra, wait_scanned)
from test_media_library import EXTRA

# 見出しの行の部品（行の段を数える・帯との重なりを見る）
HEAD_ITEMS = ["libAddBtn", "libSearchBox", "libFiltBtn", "libCount", "libFiltClear", "libViewSeg", "libSize"]
# 中身が…で切れてよい列: 測らない列（カバー・曲名）と、幅の上限に届いた長い名前の列（_dbgApp.lib().capped）
ALWAYS_CUT_OK = ["cover", "name"]
# JD（ジャンプ距離）は1段のまま（元から切れていない短い見出し。2段にすると値より広くなる）。英語は RT も1段
TWO_LINE = ["uploaded", "dl", "plays", "rating", "ranked", "notes", "mods", "best", "rt"]

HEAD_JS = """(()=>{ const r=e=>{ const b=e.getBoundingClientRect(); return {l:b.left,t:b.top,r:b.right,b:b.bottom,cy:b.top+b.height/2,w:b.width,h:b.height,vis:e.checkVisibility()}; };
  const ids=%s, out={}; for(const id of ids) out[id]=r(document.getElementById(id));
  const lab=document.getElementById('pvModeLabel'), main=lab.querySelector('.mlMain');
  out.label=r(lab); out.labelMain=r(main); out.pane=r(document.getElementById('pvpane')); out.body=r(document.getElementById('libBody'));
  out.sep=document.querySelector('#libHead .libSep').style.visibility; return out; })()""" % json.dumps(HEAD_ITEMS)

# 表の見出しの各段・各セルの中身が切れていないか（文字の幅は Range で小数まで測る。どちらも画面の px）。返すのは切れている物の一覧
CUT_JS = """((always)=>{ const bad=[], s=window._dbgApp.lib(), cols=s.cols, fixed=[...always, ...s.capped];
  const tw=e=>{ const g=document.createRange(); g.selectNodeContents(e); return g.getBoundingClientRect().width; };
  for(const h of document.querySelectorAll('#libTable .ltH')) for(const s of h.querySelectorAll('.ltHL span')){
    const w=tw(s), box=s.getBoundingClientRect().width; if(w>box+0.5) bad.push(['見出し',h.dataset.col,s.textContent,Math.round(w*10)/10,Math.round(box*10)/10]); }
  for(const row of document.querySelectorAll('#libTable .ltRow')){ if(row.style.display==='none') continue;
    [...row.children].forEach((td,k)=>{ const id=cols[k]; if(fixed.includes(id)||!td.textContent) return;
      const cs=getComputedStyle(td), z=td.currentCSSZoom||1, inner=td.getBoundingClientRect().width-(parseFloat(cs.paddingLeft)+parseFloat(cs.paddingRight))*z;   // 余白は CSS の px＝画面の px へ直す（UI文字サイズ）
      const w=tw(td); if(w>inner+0.5) bad.push(['セル',id,td.textContent,Math.round(w*10)/10,Math.round(inner*10)/10]); }); }
  return bad; })(%s)""" % json.dumps(ALWAYS_CUT_OK)


def _head(ed):
    return ed.js(HEAD_JS)


def _lines(h):
    """見出しの行の部品が何段に並んでいるか（部品の縦の中心で数える）。帯の段（1段目）も数える"""
    ys = sorted(h[i]["cy"] for i in HEAD_ITEMS if h[i]["vis"])
    rows = []
    for y in ys:
        if not rows or y - rows[-1] > 8:
            rows.append(y)
    return len(rows)


def _set_pane(ed, w):
    """MEDIA の幅を変える（境目のドラッグと同じく #pvpane の幅を変えて、画面の配置を合わせる）"""
    ed.js(f"document.getElementById('pvpane').style.width='{w}px'; window.dispatchEvent(new Event('resize')); true")
    ed.wait(0.35)


def _all_cols(ed):
    """見出しの右クリックの列のメニューで、全部の列を出す"""
    x, y = center(ed, "#libTable .ltH[data-col=name]")
    ed.click(x, y, button="right")
    wait_until(ed, "!!document.getElementById('libColMenu')", label="列のメニュー")
    ed.js("[...document.querySelectorAll('#libColMenu input')].forEach(c=>{ if(!c.checked) c.click(); }); true")
    ed.key("Escape")
    wait_until(ed, "!document.getElementById('libColMenu')", label="列のメニューを閉じる")
    ed.wait(0.2)


def _reopen(ed, **ls):
    """localStorage に ls を書いて開き直す（環境設定のミラーへ書き戻されるのを待ってから。記録したライブラリは起動時に読む）"""
    ed.js("".join(f"localStorage.setItem({json.dumps(k)},{json.dumps(str(v))});" for k, v in ls.items()) + "true")
    ed.wait(0.6)
    ed.reload(clear_storage=False)
    wait_scanned(ed)
    ed.wait(0.3)


def _with_extra(ed, extra=EXTRA):
    """開き直した後に /__lib/extra の差し替えを入れ直して読み直す（NLM推定の★が出るまで待つ）"""
    install_extra(ed, extra)
    ed.js("window._dbg.rt.libRefreshExtra().then(()=>true)")
    wait_until(ed, "window._dbgApp.lib().libs.some(l=>l.native&&l.extra>0)&&(()=>{ const n=window._dbgApp.lib().rows.length; for(let i=0;i<n;i++){ const c=window._dbgApp.libCell(i,'stars'); if(c&&c.text.includes('11.11')) return true; } return false; })()",
               label="差し替えた値")
    ed.wait(0.2)


# MEDIA の幅を順に変えて、見出しの行の段と大きさのスライダーの位置を測る（幅ごとに描画を3回待つ＝検索欄の送り（fitSearch）は次の描画の前に動く。1回の呼び出しで全部の幅を回す）
SWEEP_JS = """(async ws=>{ const pane=document.getElementById('pvpane'), old=pane.style.width, out=[];
  const r=id=>document.getElementById(id).getBoundingClientRect(), cy=b=>b.top+b.height/2, frame=()=>new Promise(f=>requestAnimationFrame(()=>f()));
  for(const w of ws){ pane.style.width=w+'px'; window.dispatchEvent(new Event('resize')); await frame(); await frame(); await frame();
    const p=r('pvpane'), s=r('libSize'), g=r('libSizeGrp'), v=r('libViewSeg'), f=r('libFiltBtn'), c=r('libFiltClear'), sb=r('libSearchBox'), a=r('libAddBtn');
    const ys=%s.map(id=>cy(r(id))).sort((x,y)=>x-y); let lines=0, last=-1e9; for(const y of ys){ if(y-last>8){ lines++; last=y; } }
    out.push({w, lines, sizeCy:cy(s), viewCy:cy(v), filtCy:cy(f), clearCy:cy(c), addCy:cy(a), sizeL:g.left, sizeR:s.right, viewL:v.left, viewR:v.right,
      clearR:c.right, paneR:p.right, searchW:sb.width, searchCy:cy(sb)}); }
  pane.style.width=old; window.dispatchEvent(new Event('resize')); await frame(); return out; })(%s)"""


def _sweep(ed, widths):
    return ed.js(SWEEP_JS % (json.dumps(HEAD_ITEMS), json.dumps(list(widths))))


def _check_size_slider(t, rows, tag):
    """表示の切り替えと大きさのスライダーは、どの幅でもフィルター・件数・解除と同じ段の右端（スライダーだけが次の段へ1つで折り返さない）。
    表示の切り替えはスライダーのすぐ左"""
    bad = [r["w"] for r in rows if any(abs(r[k] - r["filtCy"]) > 4 for k in ("sizeCy", "viewCy", "clearCy"))]
    t.eq(bad, [], f"{tag}: 表示の切り替え・大きさのスライダーはフィルター・件数・解除と同じ段（違った幅）")
    bad = [(r["w"], round(r["paneR"] - r["sizeR"])) for r in rows if not (8 <= r["paneR"] - r["sizeR"] <= 30)]
    t.eq(bad, [], f"{tag}: 大きさのスライダーは行の右端（違った幅・右の余白）")
    bad = [(r["w"], round(r["sizeL"] - r["viewR"], 1)) for r in rows if not (5 <= r["sizeL"] - r["viewR"] <= 7)]
    t.eq(bad, [], f"{tag}: 表示の切り替えは大きさのすぐ左（違った幅・間）")
    bad = [r["w"] for r in rows if r["viewL"] < r["clearR"] + 6]
    t.eq(bad, [], f"{tag}: 表示の切り替えは［解除］と重ならない（違った幅）")
    bad = [(r["w"], r["lines"]) for r in rows if r["lines"] > 2]
    t.eq(bad, [], f"{tag}: どの幅でも2段以内（違った幅・段の数）")


def _body_top(h):
    return h["body"]["t"] - h["pane"]["t"]


def _placeholder_fits(ed):
    """検索欄の案内の文字が全部見えているか（文字の幅を canvas で測り、欄の中の幅と比べる）"""
    return ed.js("""(()=>{ const si=document.getElementById('libSearch'), cs=getComputedStyle(si), g=document.createElement('canvas').getContext('2d');
      g.font=cs.fontSize+' '+cs.fontFamily; return g.measureText(si.placeholder).width <= si.clientWidth-parseFloat(cs.paddingLeft)-parseFloat(cs.paddingRight)+0.5; })()""")


def _slider_end(ed, right):
    """大きさのスライダーの右端（または左端）を本物のクリックで押す＝最大（最小）の値"""
    r = ed.js("(r=>({l:r.left,r:r.right,y:r.top+r.height/2}))(document.getElementById('libSize').getBoundingClientRect())")
    ed.click(r["r"] - 1 if right else r["l"] + 1, r["y"])
    ed.wait(0.2)


def test_head_row_layout(t):
    '''操作部品は MEDIA の見出しの行（帯の右）に並び、帯の文字と重ならない。既定の幅（約480px）では2段（今までの3段より1段少ない）、
    広げると1段。PREVIEW の時は出さない。検索欄とフィルターの区切り線は、折り返しで段の端に来たら消す'''
    ed = open_lib(t)
    h = _head(ed)
    t.ok(h["libAddBtn"]["l"] >= h["label"]["r"] + 6, f"フォルダを追加は帯の右（帯の右端 {h['label']['r']:.0f}・ボタンの左 {h['libAddBtn']['l']:.0f}）")
    t.ok(abs(h["libAddBtn"]["cy"] - h["labelMain"]["cy"]) <= 4, f"フォルダを追加は帯の文字と同じ高さ（{h['libAddBtn']['cy']:.1f} / {h['labelMain']['cy']:.1f}）")
    t.ok(0 < h["libSize"]["l"] - h["libViewSeg"]["r"] <= 30 and abs(h["libViewSeg"]["cy"] - h["libSize"]["cy"]) <= 4,
         "表示の切り替えは大きさのスライダーのすぐ左（前はフォルダを追加の右）")
    pw = round(h["pane"]["w"])
    t.ok(470 <= pw <= 490, f"既定の MEDIA の幅: {pw}")
    t.eq(_lines(h), 2, "既定の幅では2段（帯の段＋1段）")
    t.ok(h["body"]["t"] - h["pane"]["t"] <= 80, f"一覧は MEDIA の上端から 80px 以内で始まる（{h['body']['t'] - h['pane']['t']:.0f}px。前は約117px）")
    for i in HEAD_ITEMS[1:]:
        t.ok(h[i]["vis"] and h[i]["r"] <= h["pane"]["r"] - 8, f"{i} は MEDIA の中に見えている")
    t.eq(lib(ed)["count"], "4曲・9譜面（全4曲）", "件数（全文はツールチップにも）")
    t.eq(ed.js("document.getElementById('libCount').title"), "4曲・9譜面（全4曲）", "件数の全文のツールチップ")
    # 既定の幅では検索欄はフォルダを追加と同じ段の残り（約83px。2段目へ送ると3段になるので送らない）
    t.ok(abs(h["libSearchBox"]["cy"] - h["libAddBtn"]["cy"]) <= 4, "既定の幅では検索欄はフォルダを追加と同じ段")
    _set_pane(ed, 600)
    h = _head(ed)
    t.ok(h["libSearchBox"]["w"] >= 150, f"段に余った幅は検索欄が先に取る（600px で {h['libSearchBox']['w']:.0f}px）")
    # 広げると1段に収まる。余った幅は検索欄が先に取り（案内が全部見える 200px まで）、その先は件数へ
    _set_pane(ed, 960)
    h = _head(ed)
    t.eq(_lines(h), 1, "広げると1段")
    t.ok(h["libAddBtn"]["l"] >= h["label"]["r"] + 6, "広げても帯と重ならない")
    t.ok(_placeholder_fits(ed), "960px では検索欄の案内「曲名・アーティスト・マッパー」が全部見える")
    _set_pane(ed, 1100)
    h = _head(ed)
    t.eq(_lines(h), 1, "1100px でも1段")
    t.eq(ed.js("document.getElementById('libCount').textContent"), "4曲・9譜面（全4曲）", "もっと広げると件数は全文")
    t.ok(h["libSize"]["r"] <= h["pane"]["r"] - 8 and h["libSize"]["r"] >= h["pane"]["r"] - 30, "大きさのスライダーは行の右端")
    t.ok(h["libFiltClear"]["l"] - h["libCount"]["r"] <= 8, "［解除］は件数の文字のすぐ右")
    # 中くらいの幅: 検索欄が1段目の端・フィルターが2段目の頭 → 区切り線は消す。フィルター・件数・解除は1つの組で一緒に2段目へ
    _set_pane(ed, 700)
    h = _head(ed)
    t.ok(abs(h["libSearchBox"]["cy"] - h["libFiltBtn"]["cy"]) > 8, "700px では検索欄とフィルターが別の段")
    t.eq(h["sep"], "hidden", "段の端に来た区切り線は消す")
    t.ok(abs(h["libFiltBtn"]["cy"] - h["libCount"]["cy"]) <= 4 and abs(h["libFiltBtn"]["cy"] - h["libFiltClear"]["cy"]) <= 4,
         "フィルター・件数・解除は同じ段")
    _set_pane(ed, 960)
    t.eq(_head(ed)["sep"], "", "同じ段に戻ると区切り線を出す")
    # 幅を 20px ずつ変えても、大きさのスライダーはフィルター・件数・解除と同じ段の右端（前は 740〜800px でスライダーだけが2段目の左端へ1つで折り返した）
    rows = _sweep(ed, range(480, 1121, 20))
    _check_size_slider(t, rows, "日本語")
    mid = [r for r in rows if 740 <= r["w"] <= 800]
    t.ok(all(abs(r["searchCy"] - r["addCy"]) <= 4 and r["searchW"] >= 150 for r in mid),
         f"740〜800px: 検索欄は1段目で広い（{[(r['w'], round(r['searchW'])) for r in mid]}）")
    # 2段の時、検索欄は 140px 以上（1段目に細く押し込まれる幅＝520px 付近では2段目へ送る）。ただし一番狭い所（〜500px）と全部が1段に入る幅
    # （820〜860px 付近）は、送ると段が増えるので細いまま1段目に残す（段を増やさないことを優先＝縦の場所を使わないため）
    bad = [(r["w"], round(r["searchW"])) for r in rows
           if r["lines"] == 2 and r["searchW"] < 139.5 and not (r["w"] <= 500 and abs(r["searchCy"] - r["addCy"]) <= 4)]
    t.eq(bad, [], "2段の時は検索欄が 140px より細くならない（〜500px で1段目に残す時を除く。違った幅・検索欄の幅）")
    t.ok(all(r["lines"] == 1 for r in rows if r["w"] >= 820), "820px 以上は1段（検索欄を送って段を増やさない）")
    _set_pane(ed, 480)
    # PREVIEW の時は出さない（Tab で切り替え）
    ed.move(240, 300); ed.wait(0.2); ed.key("Tab")
    wait_until(ed, "!document.getElementById('libHead').checkVisibility()", label="PREVIEW では見出しの行を出さない")
    ed.move(240, 300); ed.wait(0.2); ed.key("Tab")
    wait_until(ed, "document.getElementById('libHead').checkVisibility()", label="MEDIA に戻す")
    ed.wait(0.3)
    h = _head(ed)
    t.ok(h["libAddBtn"]["l"] >= h["label"]["r"] + 6, "MEDIA に戻っても帯と重ならない")
    t.no_errors()


def test_head_row_english(t):
    '''英語表示でも帯（言語で文字が変わる）と重ならず、既定の幅で2段'''
    ed = open_lib(t)
    ed.js("localStorage.setItem('bsnm_lang','en');true")
    ed.wait(0.6)   # 環境設定のミラーへ書き戻されるのを待つ
    ed.reload(clear_storage=False)
    wait_scanned(ed)
    wait_until(ed, "document.getElementById('mFileBtn').textContent.trim()==='File'", label="英語表示")
    ed.wait(0.3)
    h = _head(ed)
    t.ok(h["libAddBtn"]["l"] >= h["label"]["r"] + 6, f"Add folder は帯の右（{h['label']['r']:.0f} / {h['libAddBtn']['l']:.0f}）")
    t.eq(_lines(h), 2, "既定の幅で2段")
    t.eq(ed.js("document.querySelector('#libFiltBtn [data-i18n=\"lib.filterBtn\"]').textContent"), "Filter", "ボタンは Filter")
    t.eq(ed.js("document.getElementById('libSearch').placeholder"), "Song, artist, mapper", "検索欄の案内")
    t.ok(ed.js("document.getElementById('libSize').title").startswith("Thumbnail size"), "スライダーのツールチップ（グリッド）")
    for w in (700, 960):   # 言語で部品の幅が変わっても、フィルター・件数・解除は同じ段（前は英語の 700px で件数・解除だけ次の段へ分かれた）
        _set_pane(ed, w)
        h = _head(ed)
        t.ok(abs(h["libFiltBtn"]["cy"] - h["libCount"]["cy"]) <= 4 and abs(h["libFiltBtn"]["cy"] - h["libFiltClear"]["cy"]) <= 4,
             f"{w}px: Filter・件数・Clear は同じ段")
    _check_size_slider(t, _sweep(ed, range(480, 1121, 20)), "英語")   # 前は 720〜780px でスライダーだけが2段目へ
    _set_pane(ed, 480)
    set_view(ed, "detail")
    t.ok(ed.js("document.getElementById('libSize').title").startswith("Text size"), "スライダーのツールチップ（詳細）")
    _check_size_slider(t, _sweep(ed, range(480, 1121, 40)), "英語・詳細表示")   # 印が Aa に変わっても同じ
    t.no_errors()


def test_search_box_and_filter_badge(t):
    '''検索欄の中の 🔍 と ×（文字がある時だけ・押すと消える）。「フィルター ▾」のボタンは効いている条件の数を丸で出す（文字の検索・モードの初期値は数えない）'''
    ed = open_lib(t, extra=EXTRA)
    t.eq(ed.js("document.getElementById('libSearch').placeholder"), "曲名・アーティスト・マッパー", "検索欄の案内")
    t.ok(ed.js("document.querySelector('#libSearchBox .lsIco').checkVisibility()"), "検索欄の中に 🔍 の印")
    t.ok(not ed.js("document.getElementById('libSearchX').checkVisibility()"), "文字が無い時は × を出さない")
    t.eq(ed.js("document.getElementById('libFiltBtn').textContent"), "フィルター▾", "ボタンは「フィルター ▾」（条件が無い時は数を出さない）")
    t.ok(ed.js("!!document.querySelector('#libFiltBtn .lfIco')"), "漏斗の印")
    t.ok(not ed.js("document.getElementById('libFiltN').checkVisibility()"), "条件の数の丸は出さない")
    click_sel(ed, "#libSearch")
    ed.call("Input.insertText", text="beta")
    wait_until(ed, "window._dbgApp.lib().count.startsWith('1曲')", label="打つとすぐ絞り込む")
    t.ok(ed.js("document.getElementById('libSearchX').checkVisibility()"), "文字があると × を出す")
    t.eq(lib(ed)["condCount"], 0, "文字の検索は条件の数に入れない")
    t.ok(not ed.js("document.getElementById('libFiltN').checkVisibility()"), "文字の検索だけでは丸を出さない")
    click_sel(ed, "#libSearchX")
    wait_until(ed, "window._dbgApp.lib().filter.q===''&&window._dbgApp.lib().count.startsWith('4曲')", label="× で消す")
    t.eq(ed.js("document.getElementById('libSearch').value"), "", "欄も空")
    t.ok(ed.js("document.activeElement===document.getElementById('libSearch')"), "× の後も欄に打てる（フォーカスが残る）")
    t.ok(not ed.js("document.getElementById('libSearchX').checkVisibility()"), "× は隠れる")
    badge = lambda: ed.js("(e=>e.checkVisibility()?e.textContent:'')(document.getElementById('libFiltN'))")
    filt_range(ed, "stars", "5", "")
    t.eq((badge(), lib(ed)["condCount"]), ("1", 1), "★の範囲＝1")
    filt_range(ed, "stars", "5", "10")
    t.eq(badge(), "1", "同じ条件の上限を足しても1")
    filt_diff(ed, "ExpertPlus")
    t.eq(badge(), "2", "＋難易度")
    filt_mode(ed, "OneSaber")
    t.eq(badge(), "3", "＋モード（初期値の Standard だけから変えた）")
    filt_check(ed, "noMods")
    filt_check(ed, "fav")
    t.eq(badge(), "5", "＋Mod・お気に入り")
    t.ok("5個の条件" in ed.js("document.getElementById('libFiltN').title"), "丸のツールチップ")
    t.ok(ed.js("document.getElementById('libFiltBtn').classList.contains('on')"), "条件がある時はボタンの色を変える")
    # 残りの項目も1つずつ増える（値は一覧が空になってもよい。数だけを見る）
    n = 5
    for k, lo in (("len", "1"), ("njs", "5"), ("nps", "0.1"), ("bpm", "60")):
        filt_range(ed, k, "", lo) if k == "len" else filt_range(ed, k, lo, "")
        n += 1
        t.eq(badge(), str(n), f"＋{k}")
    ed.js("(i=>{ i.value='2020-01-01'; i.dispatchEvent(new Event('input')); return 1; })(document.querySelector('#libFiltPanel .lfRow[data-k=up] .lfLo'))")
    n += 1
    wait_until(ed, f"window._dbgApp.lib().condCount==={n}", label="アップロード日")
    t.eq(badge(), str(n), "＋アップロード日")
    ed.js("(s=>{ s.value='bl'; s.dispatchEvent(new Event('change')); return 1; })(document.querySelector('#libFiltPanel .lfRanked'))")
    n += 1
    wait_until(ed, f"window._dbgApp.lib().condCount==={n}", label="ランク")
    t.eq(badge(), str(n), "＋ランク")
    filt_check(ed, "unplayed")
    n += 1
    t.eq(badge(), str(n), "＋未プレイ")
    # 初期値に戻すと減る（モードは Standard だけに戻すと数えない）
    filt_mode(ed, "OneSaber")
    n -= 1
    t.eq((badge(), lib(ed)["filter"]["modes"]), (str(n), ["Standard"]), "モードを初期値（Standard だけ）に戻すと1つ減る")
    filt_check(ed, "unplayed")
    n -= 1
    t.eq(badge(), str(n), "未プレイを外すと1つ減る")
    filt_range(ed, "stars", "", "")
    n -= 1
    t.eq(badge(), str(n), "★の範囲を空にすると1つ減る")
    close_filter(ed)
    click_sel(ed, "#libFiltClear")
    wait_until(ed, "!window._dbgApp.lib().active", label="解除")
    t.eq((badge(), lib(ed)["condCount"]), ("", 0), "解除で丸も消える")
    open_filter(ed)
    t.eq(ed.js("document.querySelector('#libFiltPanel .lfHead span').textContent"), "フィルター", "パネルの名前もフィルター")
    close_filter(ed)
    t.no_errors()


def test_catalog_width_drag(t):
    '''左のカタログの幅を境目のドラッグで変える（最小100px・最大は一覧の枠の半分）・開き直しても残る（bsnm_libSideW）・ダブルクリックで元の幅（176px）'''
    ed = open_lib(t)
    side = lambda: round(ed.js("document.getElementById('libSide').getBoundingClientRect().width"))
    t.eq(side(), 176, "初めは176px")
    t.eq(ed.js("localStorage.getItem('bsnm_libSideW')"), None, "保存はまだ無い")
    x, y = center(ed, "#libSideSplit")
    t.eq(ed.js("getComputedStyle(document.getElementById('libSideSplit')).cursor"), "col-resize", "境目は左右の矢印のカーソル")
    t.ok(ed.js("document.getElementById('libSideSplit').getBoundingClientRect().left>=document.getElementById('libSide').getBoundingClientRect().right-1.01"),
         "つかむ所はカタログの側（縦のスクロールバー）へはみ出さない（境目の線の 1px まで）")
    ed.drag(x, y, x - 50, y)
    ed.wait(0.2)
    t.eq((side(), ed.js("localStorage.getItem('bsnm_libSideW')")), (126, "126"), "左へ50px＝126px・保存")
    x, y = center(ed, "#libSideSplit")
    ed.drag(x, y, x - 200, y)
    ed.wait(0.2)
    t.eq(side(), 100, "最小は100px")
    half = ed.js("Math.floor(document.getElementById('libBody').clientWidth/2)")
    x, y = center(ed, "#libSideSplit")
    ed.drag(x, y, x + 400, y)
    ed.wait(0.2)
    t.eq(side(), half, f"最大は一覧の枠の半分（{half}px）")
    x, y = center(ed, "#libSideSplit")
    ed.drag(x, y, x - 30, y)
    ed.wait(0.2)
    w = side()
    t.eq(ed.js("localStorage.getItem('bsnm_libSideW')"), str(w), "動かした幅を保存")
    t.ok(ed.js("(r=>{ const m=document.getElementById('libMain').getBoundingClientRect(); return Math.abs(m.left-r.right)<=4; })(document.getElementById('libSide').getBoundingClientRect())"),
         "一覧はカタログのすぐ右から")
    ed.wait(0.6)   # 環境設定のミラーへ書き戻されるのを待つ
    ed.reload(clear_storage=False)
    wait_scanned(ed)
    ed.wait(0.2)
    t.eq(side(), w, "開き直しても残る")
    # MEDIA を狭めると表示だけ半分に抑え、保存した幅は変えない
    ed.js("document.getElementById('pvpane').style.width='300px'; true")
    ed.wait(0.3)
    half = ed.js("Math.floor(document.getElementById('libBody').clientWidth/2)")
    t.eq(side(), max(100, min(w, half)), "狭めた時は半分まで")
    t.eq(ed.js("localStorage.getItem('bsnm_libSideW')"), str(w), "保存した幅は変えない")
    ed.js("document.getElementById('pvpane').style.width='480px'; true")
    ed.wait(0.3)
    t.eq(side(), w, "戻すと保存した幅")
    x, y = center(ed, "#libSideSplit")
    ed.click(x, y, count=2)
    ed.wait(0.2)
    t.eq((side(), ed.js("localStorage.getItem('bsnm_libSideW')")), (176, None), "ダブルクリックで元の幅（保存も消す）")
    t.no_errors()


def test_two_line_headers_not_cut(t):
    '''詳細表示の見出しは決めた位置で2段に折り、見出しの各段も中身も切れない（全部の列を出して確かめる。日本語・英語）'''
    ed = open_lib(t, extra=EXTRA)
    set_view(ed, "detail")
    _all_cols(ed)
    s = lib(ed)
    t.eq(len(s["cols"]), len(s["allCols"]), "全部の列を出した")
    hl = s["headLines"]
    t.eq({c: hl[c] for c in ("uploaded", "dl", "plays", "rt", "jd")},
         {"uploaded": ["アップロード", "日"], "dl": ["ダウンロード", "日"], "plays": ["プレイ", "回数"], "rt": ["反応", "時間"], "jd": ["JD"]}, "2段の見出し（JD は1段）")
    t.ok(all(len(hl[c]) == 2 for c in TWO_LINE), f"2段にする列: {[c for c in TWO_LINE if len(hl[c]) != 2]}")
    t.eq(ed.js("[...document.querySelectorAll('#libTable .ltH[data-col=uploaded] .ltHL span')].map(e=>e.textContent)"), ["アップロード", "日"], "画面でも2段")
    t.eq(ed.js(CUT_JS), [], "見出しの各段・セルの中身が切れていない")
    # 並べ替えの印が付いても切れない（印のぶん幅を足す）
    x, y = center(ed, "#libTable .ltH[data-col=uploaded]")
    ed.click(x, y)
    wait_until(ed, "(s=>s.sort&&s.sort.col==='uploaded')(window._dbgApp.lib())", label="並べ替え")
    ed.wait(0.2)
    t.eq(ed.js(CUT_JS), [], "並べ替えの印が付いても切れない")
    # 英語
    ed.js("localStorage.setItem('bsnm_lang','en');true")
    ed.wait(0.6)
    ed.reload(clear_storage=False)
    wait_scanned(ed)
    install_extra(ed, EXTRA)
    ed.js("window._dbg.rt.libRefreshExtra().then(()=>true)")
    wait_until(ed, "(()=>{ const n=window._dbgApp.lib().rows.length; for(let i=0;i<n;i++) if(window._dbgApp.libCell(i,'stars').text.startsWith('NLM est.')) return true; return false; })()",
               label="英語の NLM推定")
    ed.wait(0.3)
    hl = lib(ed)["headLines"]
    t.eq((hl["uploaded"], hl["rt"], hl["jd"]), (["Upload", "date"], ["RT"], ["JD"]), "英語の2段の見出し（RT・JD は1段）")
    t.eq(ed.js(CUT_JS), [], "英語でも切れない")
    t.no_errors()


def test_column_widths_fit_values(t):
    '''列の幅は一覧の全部の行（見えていない行も）の値に合わせる: 値の無い★の列は狭く、一番下の行にだけ NLM推定がある時も切れない。
    値が変わった・絞り込みで一覧が変わった時は測り直す。1500行でも測り直しは速い'''
    from nle_helpers import open_nle, clear_assets
    clear_assets(t.ed)
    ed = open_nle(t)
    big = Path(ed.data_dir) / "big_lib"
    if not big.exists():   # test_media_library.py の test_virtual_scroll_many_rows と同じ素材（同じプロセスなら作り直さない）
        diffs = [{"_difficulty": d, "_beatmapFilename": d + ".dat", "_noteJumpMovementSpeed": 10 + i, "_noteJumpStartBeatOffset": 0}
                 for i, d in enumerate(["Easy", "Normal", "Hard", "Expert", "ExpertPlus"])]
        for k in range(300):
            f = big / ("%04x (Song %03d - M)" % (k + 1, k))
            f.mkdir(parents=True)
            (f / "Info.dat").write_text(json.dumps({"_version": "2.1.0", "_songName": "Song %03d" % k, "_songAuthorName": "A", "_levelAuthorName": "M",
                                                    "_beatsPerMinute": 100 + k, "_difficultyBeatmapSets": [
                                                        {"_beatmapCharacteristicName": "Standard", "_difficultyBeatmaps": diffs}]}), encoding="utf-8")
    record_libs(ed, big)
    ed.js("window._dbg.rt.loadNativeLibs().then(()=>true)")
    wait_scanned(ed, timeout=60)
    set_view(ed, "detail")
    s = lib(ed)
    t.eq(len(s["rows"]), 1500, "1500行")
    w0 = s["widths"]["stars"]
    t.ok(w0 <= 40, f"★の値が1つも無い時は見出しの幅だけ（{w0}px）")
    t.ok(s["widths"]["diff"] <= 60, f"Standard だけの一覧の難易度の列は印と見出しの幅だけ（{s['widths']['diff']}px）")
    t.ok(s["widths"]["artist"] <= 95 and s["widths"]["mapper"] <= 70 and not s["capped"],
         f"短い名前しか無い列は見出しの幅まで詰める（アーティスト {s['widths']['artist']}px・マッパー {s['widths']['mapper']}px。上限はそれぞれ約147px・136px）")
    t.eq(s["measured"]["rows"], 1500, "全部の行を測る")
    # 一番下の曲（見えていない行）にだけ NLM推定の★を入れる → ★の列が広がる
    lid = lib_id(ed, "big_lib")
    ed.js(f"window._dbg.rt.libSetItemExtra({json.dumps(lid)}, '012c (Song 299 - M)', {{est:{{version:'0.1.0',diffs:{{'Standard/ExpertPlus':{{stars:12.34}}}}}}}});true")
    wait_until(ed, f"window._dbgApp.lib().widths.stars>{w0 + 40}", label="値が変わったら測り直す")
    s = lib(ed)
    t.ok(s["firstRendered"] < 100, "一番下の行は描いていない（見えていない）")
    w1 = s["widths"]["stars"]
    t.ok(80 <= w1 <= 130, f"「NLM推定 12.34」が入る幅（{w1}px）")
    ed.js("(t=>{ t.scrollTop=t.scrollHeight; return 1; })(document.getElementById('libTable'))")
    wait_until(ed, "window._dbgApp.lib().firstRendered>1400", label="一番下までスクロール")
    ed.wait(0.2)
    t.eq(ed.js("window._dbgApp.libCell(1499,'stars').text"), "NLM推定 12.34", "一番下の行")
    t.eq(ed.js(CUT_JS), [], "一番下の行の★も切れていない")
    # 絞り込みで NLM推定のある行が一覧から外れたら狭める
    click_sel(ed, "#libSearch")
    ed.call("Input.insertText", text="Song 001")
    wait_until(ed, "window._dbgApp.lib().count.startsWith('1曲')", label="検索")
    wait_until(ed, f"window._dbgApp.lib().widths.stars==={w0}", label="一覧に★が無くなったら狭める")
    ed.key("Escape")
    wait_until(ed, f"window._dbgApp.lib().widths.stars==={w1}", label="戻すと広げる")
    # BPM の列（100〜399）: 一番広い値に合わせる
    t.eq(ed.js(CUT_JS), [], "BPM 等も切れていない")
    # 深い位置で文字の大きさを変えても、一番上に見えていた行はそのまま。行の高さが変わっても行のクリックは合う
    ed.js("(t=>{ t.scrollTop=1000*window._dbgApp.lib().rowH; return 1; })(document.getElementById('libTable'))")
    wait_until(ed, "window._dbgApp.lib().firstRendered>=990", label="1000行目付近へスクロール")
    ed.wait(0.2)
    top = lambda: ed.js("(t=>Math.floor(t.scrollTop/window._dbgApp.lib().rowH))(document.getElementById('libTable'))")
    t0 = top()
    x, y = center(ed, "#libTable")
    ed.wheel(x, y, -100, ctrl=True); ed.wait(0.15)
    ed.wheel(x, y, -100, ctrl=True); ed.wait(0.15)
    s = lib(ed)
    t.eq((s["font"], s["rowH"]), (15, 30), "Ctrl＋ホイールで15px")
    t.eq(top(), t0, f"一番上の行（{t0}行目）はそのまま")
    t.ok(s["firstRendered"] <= t0 <= s["firstRendered"] + 10, "その位置の行を描いている")
    ed.click(*row_xy(ed, 1200))
    t.eq([(r["name"], r["key"]) for r in lib(ed)["sel"]], [(lib(ed)["rows"][1200]["name"], lib(ed)["rows"][1200]["key"])], "1200行目のクリックで1200行目を選ぶ")
    ed.js("(t=>{ t.scrollTop=t.scrollHeight; return 1; })(document.getElementById('libTable'))")
    _slider_end(ed, False)
    wait_until(ed, "window._dbgApp.lib().font===11", label="11px")
    ed.js("(t=>{ t.scrollTop=t.scrollHeight; return 1; })(document.getElementById('libTable'))")
    ed.wait(0.2)
    last = ed.js("[...document.querySelectorAll('#libTable .ltRow')].filter(e=>e.style.display!=='none').map(e=>e._i).sort((a,b)=>b-a)[0]")
    t.eq(last, 1499, "小さくしても最後の行まで描く")
    t.no_errors()


def test_font_size_slider_and_wheel(t):
    '''大きさのスライダーは兼用: グリッド＝サムネイルの大きさ（bsnm_libsz）・詳細＝一覧の文字の大きさ（bsnm_libFont・11〜18px・初期値13）。
    行の高さ・カバーの小さい画像・難易度の印・見出し・列の幅も文字に合わせる。詳細表示の上の Ctrl＋ホイールでも変える（ページの拡大にしない）'''
    ed = open_lib(t, extra=EXTRA)
    s = lib(ed)
    t.eq((s["slider"]["min"], s["slider"]["max"], s["slider"]["value"], s["gridSize"]), (4, 8, 5, 5), "グリッドではサムネイルの大きさ（4〜8・初期値5）")
    t.eq(s["slider"]["title"], "サムネイルの大きさ", "ツールチップ（グリッド）")
    ico = lambda: ed.js("[...document.querySelectorAll('#libSizeIco > *')].filter(e=>e.checkVisibility()).map(e=>e.getAttribute('class'))")
    t.eq(ico(), ["lszImg"], "スライダーの左の印はグリッドでは画像")
    t.eq(ed.js("document.getElementById('libSizeGrp').title"), "サムネイルの大きさ", "印の上でも同じツールチップ")
    _slider_end(ed, True)
    t.eq((lib(ed)["gridSize"], ed.js("localStorage.getItem('bsnm_libsz')")), (8, "8"), "右端＝8（大）・保存")
    t.eq(ed.js("getComputedStyle(document.getElementById('libGrid')).gridTemplateColumns.split(' ').length"), 2, "グリッドは2列")
    set_view(ed, "detail")
    s = lib(ed)
    t.eq((s["slider"]["min"], s["slider"]["max"], s["slider"]["value"], s["font"], s["rowH"]), (11, 18, 13, 13, 26), "詳細では文字の大きさ（初期値13px・行26px）")
    t.ok(s["slider"]["title"].startswith("文字の大きさ"), f"ツールチップ（詳細）: {s['slider']['title']}")
    t.eq(ico(), ["lszAa"], "詳細では Aa")
    t.eq(ed.js("getComputedStyle(document.querySelector('#libTable .ltRow .ltC:nth-child(2)')).fontSize"), "13px", "一覧の文字は13px")
    name0 = s["widths"]["name"]
    wait_until(ed, "!!document.querySelector('#libTable .ltRow .ltCov img')", label="カバーの小さい画像")
    _slider_end(ed, True)
    s = lib(ed)
    t.eq((s["font"], s["rowH"], ed.js("localStorage.getItem('bsnm_libFont')")), (18, 35, "18"), "右端＝18px・行35px・保存")
    t.eq(s["gridSize"], 8, "サムネイルの大きさは変わらない")
    geo = ed.js("""(()=>{ const rows=[...document.querySelectorAll('#libTable .ltRow')].filter(e=>e.style.display!=='none').sort((a,b)=>a._i-b._i);
      const im=document.querySelector('#libTable .ltRow .ltCov img'), df=document.querySelector('#libTable .ltDiff');
      return {h:rows[0].getBoundingClientRect().height, step:rows[1].getBoundingClientRect().top-rows[0].getBoundingClientRect().top,
        img:im?im.getBoundingClientRect().height:null, diffFs:getComputedStyle(df).fontSize, fs:getComputedStyle(rows[0].children[1]).fontSize,
        head:document.querySelector('#libTable .ltHead').getBoundingClientRect().height}; })()""")
    t.eq((geo["h"], geo["step"], geo["img"], geo["diffFs"], geo["fs"]), (35, 35, 31, "17px", "18px"), "行の高さ・行の間隔・カバーの画像・難易度の印・文字")
    t.ok(geo["head"] >= 35, f"見出しの高さも文字に合わせる: {geo['head']}")
    t.ok(s["widths"]["name"] > name0, "列の幅も文字に合わせる")
    t.eq(ed.js(CUT_JS), [], "大きい文字でも見出し・中身が切れない")
    # Ctrl＋ホイール（詳細表示の上）: 下へ＝小さく。ページの拡大にはしない（preventDefault）
    ed.js("window.__wp=[]; window.addEventListener('wheel',e=>{ if(e.ctrlKey) window.__wp.push(e.defaultPrevented); },{passive:false}); true")
    x, y = center(ed, "#libTable")
    ed.wheel(x, y, 100, ctrl=True); ed.wait(0.1)
    ed.wheel(x, y, 100, ctrl=True); ed.wait(0.1)
    s = lib(ed)
    t.eq((s["font"], s["slider"]["value"], s["rowH"]), (16, 16, 31), "Ctrl＋ホイール2段＝16px（スライダーも合わせる）")
    ed.wheel(x, y, -100, ctrl=True); ed.wait(0.1)
    t.eq(lib(ed)["font"], 17, "上へ＝大きく")
    t.eq(ed.js("window.__wp"), [True, True, True], "ページの拡大にはしない")
    ed.wheel(x, y, 100); ed.wait(0.1)
    t.eq(lib(ed)["font"], 17, "Ctrl なしのホイールはスクロールだけ")
    # 行の選択は新しい行の高さでも合う
    ed.click(*row_xy(ed, 3))
    t.eq([(r["name"], r["key"]) for r in lib(ed)["sel"]], [("Beta Song", "Standard/Easy")], "行のクリック")
    _slider_end(ed, False)
    t.eq((lib(ed)["font"], lib(ed)["rowH"]), (11, 23), "左端＝11px・行23px")
    # グリッドの上の Ctrl＋ホイールは今のまま（文字の大きさを変えない）
    set_view(ed, "grid")
    gx, gy = center(ed, "#libGrid")
    # テストの Edge がページを拡大して座標がずれないよう、この確かめの間だけグリッドの上の Ctrl＋ホイールの既定の動きを止める（アプリの処理は変えない）
    ed.js("window.__gz=e=>{ if(e.ctrlKey) e.preventDefault(); }; document.getElementById('libGrid').addEventListener('wheel',window.__gz,{passive:false}); true")
    ed.wheel(gx, gy, -100, ctrl=True); ed.wait(0.1)
    ed.js("document.getElementById('libGrid').removeEventListener('wheel',window.__gz); true")
    t.eq((lib(ed)["font"], lib(ed)["gridSize"]), (11, 8), "グリッドの上では変えない")
    ed.wait(0.6)
    ed.reload(clear_storage=False)
    wait_scanned(ed)
    t.eq((lib(ed)["gridSize"], lib(ed)["slider"]["value"]), (8, 8), "開き直してもサムネイルの大きさが残る")
    set_view(ed, "detail")
    t.eq((lib(ed)["font"], lib(ed)["slider"]["value"], lib(ed)["rowH"]), (11, 11, 23), "開き直しても文字の大きさが残る")
    t.no_errors()


def test_ui_scale_head_catalog_columns(t):
    '''UI文字サイズ（環境設定・bsnm_uiscale。#tabFolder と帯に CSS の zoom が掛かる）が 80%・150% でも: フォルダを追加は帯の文字と重ならない・
    段が増えない（150% でも一覧は前の3段の作りの約175px より上から始まる）・カタログの境目のドラッグは画面の動きと同じだけ幅が変わる・
    詳細表示の見出しと中身が切れない（字形の幅は画面に実際に描く大きさで測る）'''
    for z, top_max, wide_lines in ((0.8, 64, 1), (1.5, 170, 2)):
        ed = open_lib(t)
        _reopen(ed, bsnm_uiscale=z)
        _with_extra(ed)
        s = lib(ed)
        t.ok(abs(s["layout"]["zoom"] - z) < 0.01, f"{z}: 拡大率 {s['layout']['zoom']}")
        h = _head(ed)
        same_row = abs(h["libAddBtn"]["cy"] - h["labelMain"]["cy"]) <= 4 * z
        t.ok(h["libAddBtn"]["l"] >= h["label"]["r"] + 5 * z if same_row else h["libAddBtn"]["t"] >= h["label"]["b"] - 1,
             f"{z}: フォルダを追加は帯の文字と重ならない（帯の右端 {h['label']['r']:.0f}・ボタンの左 {h['libAddBtn']['l']:.0f}・同じ段 {same_row}）")
        if same_row:
            t.ok(h["libAddBtn"]["l"] - h["label"]["r"] <= 16 * z, f"{z}: 帯のすぐ右（空きを拡大率で割り戻す）")
        t.ok(_body_top(h) <= top_max, f"{z}: 一覧は MEDIA の上端から {top_max}px 以内（{_body_top(h):.0f}px）")
        for i in HEAD_ITEMS[2:]:
            t.ok(h[i]["vis"] and h[i]["r"] <= h["pane"]["r"] - 4, f"{z}: {i} は MEDIA の中に見えている")
        _set_pane(ed, 1100)
        h = _head(ed)
        t.ok(_lines(h) <= wide_lines, f"{z}: 広げると {wide_lines} 段以内（{_lines(h)}）")
        _set_pane(ed, 800)   # 480px の 150% はカタログが一覧の枠の半分に抑えられている＝広げてから
        # カタログの境目: 画面の上で 20px 動かすと、画面の上で 20px 広がる
        sw = lambda: ed.js("document.getElementById('libSide').getBoundingClientRect().width")
        w0 = sw()
        x, y = center(ed, "#libSideSplit")
        ed.drag(x, y, x + 20, y)
        ed.wait(0.2)
        t.ok(abs(sw() - w0 - 20) <= 1.01, f"{z}: 境目を右へ 20px＝画面の上でも 20px 広がる（{w0:.1f} → {sw():.1f}）")
        t.eq(ed.js("localStorage.getItem('bsnm_libSideW')"), str(lib(ed)["layout"]["sideW"]), f"{z}: 保存は CSS の px")
        t.ok(abs(lib(ed)["layout"]["sideW"] - (176 + 20 / z)) <= 1.01, f"{z}: 保存した幅 {lib(ed)['layout']['sideW']}（176＋20÷{z}）")
        x, y = center(ed, "#libSideSplit")
        ed.drag(x, y, x - 20, y)
        ed.wait(0.2)
        t.ok(abs(sw() - w0) <= 1.01, f"{z}: 左へ 20px で元に戻る")
        _set_pane(ed, 480)
        # 詳細表示・全部の列・文字の大きさの両端と既定: 見出しと中身が切れない
        set_view(ed, "detail")
        _all_cols(ed)
        for fs in (11, 13, 18):
            ed.js(f"(s=>{{ s.value={fs}; s.dispatchEvent(new Event('input')); return 1; }})(document.getElementById('libSize'))")
            wait_until(ed, f"window._dbgApp.lib().font==={fs}&&!window._dbgApp.lib().measured.dirty", label=f"{fs}px")
            ed.wait(0.15)
            t.eq(ed.js(CUT_JS), [], f"{z}: {fs}px で見出し・中身が切れない")
        t.no_errors()


def _make_big4k(big, n=800):
    """800曲×5難易度＝4000行（この PC の実データと同じくらい）。難易度ファイルにノーツ・ボム・壁を入れる（3桁区切りの数の列も値を持つ）"""
    if big.exists():
        return
    names = ["Easy", "Normal", "Hard", "Expert", "ExpertPlus"]
    for k in range(n):
        f = big / ("%04x (Song %03d - M%d)" % (k + 1, k, k % 37))
        f.mkdir(parents=True)
        diffs = []
        for i, d in enumerate(names):
            diffs.append({"_difficulty": d, "_beatmapFilename": d + ".dat", "_noteJumpMovementSpeed": 10 + i, "_noteJumpStartBeatOffset": 0})
            nn = (k * 7 + i * 13) % 40 + 1
            notes = [{"_time": j, "_lineIndex": 0, "_lineLayer": 0, "_type": j % 2, "_cutDirection": 1} for j in range(nn)]
            notes.append({"_time": 1, "_lineIndex": 1, "_lineLayer": 0, "_type": 3, "_cutDirection": 0})
            (f / (d + ".dat")).write_text(json.dumps({"_version": "2.2.0", "_notes": notes, "_events": [],
                                                      "_obstacles": [{"_time": 2, "_lineIndex": 0, "_type": 0, "_duration": 1, "_width": 1}]}), encoding="utf-8")
        (f / "Info.dat").write_text(json.dumps({"_version": "2.1.0", "_songName": "Song %03d" % k, "_songAuthorName": "Artist %d" % (k % 53),
                                                "_levelAuthorName": "M%d" % (k % 37), "_beatsPerMinute": 100 + k % 300, "_difficultyBeatmapSets": [
                                                    {"_beatmapCharacteristicName": "Standard", "_difficultyBeatmaps": diffs}]}), encoding="utf-8")


# 走査中の件数の表示を 30ms ごとに記録する（文字・…で切れずに入っているか・ツールチップ）
_COUNT_SAMPLER = """(()=>{ window.__cs=[]; clearInterval(window.__csT); window.__csT=setInterval(()=>{ const el=document.getElementById('libCount');
  const g=document.createRange(); g.selectNodeContents(el); window.__cs.push([el.textContent, g.getBoundingClientRect().width<=el.getBoundingClientRect().width+0.5, el.title]); },30); return true; })()"""


def test_measure_4000_rows_all_columns(t):
    '''4000行（800曲×5難易度）・全部の列・全部の曲が「未照合 🔍」でも、列の幅の測り直しは 50ms 以内（数回測って一番短い値）。
    走査中の件数は狭くても進み具合の数字が残る。MEDIA が隠れている間（PREVIEW）は測らず、戻った時に測る'''
    from nle_helpers import open_nle, clear_assets
    clear_assets(t.ed)
    ed = open_nle(t)
    big = Path(ed.data_dir) / "big4k"
    _make_big4k(big)
    rels = ["%04x (Song %03d - M%d)" % (k + 1, k, k % 37) for k in range(800)]
    media_lib_record(ed, big)
    media_lib_extra(ed, {r: {"net": {"src": "none"}} for r in rels})
    media_lib_mock(ed, details=SAMPLE_DETAILS)
    ed.js(_COUNT_SAMPLER)
    ed.js("window._dbg.rt.loadNativeLibs().then(()=>{ window._dbg.rt.libOnline.ensureDetails(); return true; })")
    media_lib_wait(ed, timeout=90)
    wait_until(ed, "(s=>s.details&&s.details.state==='ok'&&!s.detailsBusy)(window._dbgApp.libOnline())", label="全曲データの状態")
    smp = ed.js("(()=>{ clearInterval(window.__csT); return window.__cs; })()")
    scan = [x for x in smp if "/" in x[2]]
    t.ok(len(scan) >= 3, f"走査中の件数を記録できた（{len(scan)}回）")
    bad = [x for x in scan if not x[1] or not re.search(r"\d+/\d+", x[0])]
    t.eq(bad[:3], [], "走査中は狭くても進み具合の数字（○/○）が切れずに見える")
    set_view(ed, "detail")
    _all_cols(ed)
    s = lib(ed)
    t.eq((len(s["rows"]), len(s["cols"])), (4000, len(s["allCols"])), "4000行・全部の列")
    t.eq(ed.js("window._dbgApp.libCell(0,'uploaded').text"), "未照合🔍", "全部の曲が未照合")

    def best(action, n=5):
        ms = []
        for i in range(n):
            c0 = lib(ed)["measured"]["count"]
            action(i)
            wait_until(ed, f"window._dbgApp.lib().measured.count>{c0}&&!window._dbgApp.lib().measured.dirty", label="測り直し")
            m = lib(ed)["measured"]
            t.eq(m["rows"], 4000, "全部の行を測る")
            ms.append(m["ms"])
        return min(ms), ms
    b, ms = best(lambda i: ed.js(f"(s=>{{ s.value={14 if i % 2 == 0 else 13}; s.dispatchEvent(new Event('input')); return 1; }})(document.getElementById('libSize'))"))
    t.ok(b < 50, f"文字の大きさを変えた時の測り直し: 一番短い {b}ms（{ms}）")
    b, ms = best(lambda i: ed.click(*center(ed, "#libTable .ltH[data-col=notes]")))
    t.ok(b < 50, f"並べ替えた時の測り直し: 一番短い {b}ms（{ms}）")
    t.eq(ed.js(CUT_JS), [], "切れていない")
    # MEDIA が隠れている間（PREVIEW）は測らない。戻った時に測る（描く前＝古い幅の画面は出ない）
    ed.move(240, 300); ed.wait(0.2); ed.key("Tab")
    wait_until(ed, "!document.getElementById('libTable').checkVisibility()", label="PREVIEW")
    c0 = lib(ed)["measured"]["count"]
    w0 = lib(ed)["widths"]["stars"]
    lid = lib_id(ed, "big4k")
    ed.js(f"window._dbg.rt.libSetItemExtra({json.dumps(lid)}, {json.dumps(rels[799])}, {{net:{{src:'none'}},est:{{version:'0.1.0',diffs:{{'Standard/ExpertPlus':{{stars:12.34}}}}}}}});true")
    ed.wait(0.8)
    s = lib(ed)
    t.eq((s["measured"]["count"], s["measured"]["dirty"]), (c0, True), "隠れている間は測らない（測り直しは後へ）")
    ed.move(240, 300); ed.wait(0.2); ed.key("Tab")
    wait_until(ed, "document.getElementById('libTable').checkVisibility()", label="MEDIA に戻す")
    wait_until(ed, f"!window._dbgApp.lib().measured.dirty&&window._dbgApp.lib().measured.count>{c0}", label="戻ると測る")
    t.ok(lib(ed)["widths"]["stars"] > w0 + 30, f"★の列が「NLM推定 12.34」の幅に広がる（{w0} → {lib(ed)['widths']['stars']}px）")
    t.no_errors()

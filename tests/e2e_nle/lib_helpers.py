"""MEDIA の「記録したライブラリ」（2026-10-12）のテスト部品（test_media_library.py 用）。

記録（config/library.json）は JS から増やせない（exe 版のフォルダ選択ダイアログだけ）ので、テストはテストのサーバーのデータフォルダ
（tools/cdp.py の ed.data_dir）の config/library.json に素材の絶対パスを書き、ページの loadNativeLibs（起動時と同じ処理）を呼ぶ。
t.fresh() はこのファイルを消す＝テストごとに記録の無い所から始まる（tests/_lib/nlmtest.py）。

- open_lib(t, fx, paths, extra): 開き直して素材を読み、ライブラリを記録して走査とネット等の値（/__lib/extra）の読み込みが終わるまで待つ
- extra: /__lib/extra の応答をページ内で差し替える（{rel: {net, play, est}} を重ねる。ネット・NLM推定の表示の確認用）
- lib(ed): window._dbgApp.lib()（表示・列・並べ替え・絞り込み・件数・行・選択・グリッド・カタログ）
- set_view / head_xy / row_xy / drag_from: 詳細表示の操作（本物の入力）
- open_filter / filt_*: 絞り込みのパネルの操作（本物の入力）
"""
import json
from pathlib import Path

from e2e_helpers import wait_until, media_lib_record, media_lib_extra, media_lib_wait, media_lib_load, MEDIA_LIB
from nle_helpers import open_nle, clear_assets

ROOT = Path(__file__).resolve().parents[2]
LIB = MEDIA_LIB
REL = {"a": "1a01 (Alpha Song - MapperA)", "b": "1b02 (Beta Song - MapperB)", "c": "1c03 (Gamma V4 - MapperC)", "d": "Delta Noodle"}


def record_libs(ed, *paths):
    """config/library.json に記録を書く（exe 版のダイアログで選んだのと同じ状態）"""
    media_lib_record(ed, *paths)


def install_extra(ed, extra):
    """/__lib/extra の応答に extra（{rel: {net?, play?, est?}}）を重ねる（ページ内の fetch を包む。開き直すと消える）"""
    media_lib_extra(ed, extra)


def lib(ed):
    return ed.js("window._dbgApp.lib()")


def wait_scanned(ed, timeout=20):
    """記録したライブラリの走査（見つからない物を除く）と、その後の extra の読み込みが終わるまで待つ"""
    return media_lib_wait(ed, timeout)


def open_lib(t, fx=None, paths=None, extra=None, playdata=None):
    """ページを開き直して（素材 fx）、ライブラリ（既定は tools/fixtures/media_lib）を記録して読み込む。
    playdata: <データフォルダ>/PlayerData.dat に書く中身（None なら消す＝プレイ記録なし）"""
    clear_assets(t.ed)   # 前のテスト（test_media.py）がアセットへ保存したクリップを消す（一覧・件数に混ざらないように。開き直す前に）
    ed = open_nle(t, fx)
    pd = Path(ed.data_dir) / "PlayerData.dat"
    if playdata is None:
        pd.unlink(missing_ok=True)
    else:
        pd.write_text(json.dumps(playdata), encoding="utf-8")
    media_lib_load(ed, extra=extra, paths=paths)
    return ed


def lib_id(ed, name="media_lib"):
    return next(l["id"] for l in lib(ed)["libs"] if l["native"] and l["name"] == name)


def map_hash(ed, rel, name="media_lib"):
    """走査の結果のハッシュ（テストのサーバー＝同じプロセスの serve.LIBRARY から）"""
    import serve
    return serve.LIBRARY.get_map(lib_id(ed, name), rel)["hash"]


def center(ed, sel):
    p = ed.js(f"""(()=>{{ const e=[...document.querySelectorAll({json.dumps(sel)})].find(e=>e.checkVisibility());
      if(!e) return null; e.scrollIntoView({{block:'nearest',inline:'nearest'}}); const r=e.getBoundingClientRect(); return {{x:r.left+r.width/2,y:r.top+r.height/2}}; }})()""")
    assert p, f"見つからないか見えていません: {sel}"
    return p["x"], p["y"]


def click_sel(ed, sel, **mods):
    x, y = center(ed, sel)
    ed.click(x, y, **mods)
    ed.wait(0.1)


def set_view(ed, mode):
    """グリッド⇔詳細の切り替え（本物のクリック）"""
    click_sel(ed, f"#libViewSeg button[data-view={mode}]")
    wait_until(ed, f"window._dbgApp.lib().view==={json.dumps(mode)}", label="表示の切り替え")
    ed.wait(0.1)


def head_xy(ed, col):
    return center(ed, f"#libTable .ltH[data-col={col}]")


def row_xy(ed, i, col=None):
    """詳細表示の i 行目（一覧の並び）の画面座標。見えるところまでスクロールしてから測る（行は見えている物だけ描く）。
    col を渡すとその列のセルの中央（無ければ曲名の列）"""
    ed.js(f"""(()=>{{ const t=document.getElementById('libTable'), hh=t.querySelector('.ltHead').offsetHeight, rh=window._dbgApp.lib().rowH, y={i}*rh;
      if(y<t.scrollTop||y+rh>t.scrollTop+t.clientHeight-hh) t.scrollTop=Math.max(0,y-rh*3); return true; }})()""")   # 行の高さは文字の大きさで変わる（rowH）
    ed.wait(0.1)
    p = wait_until(ed, f"""(()=>{{ const e=[...document.querySelectorAll('#libTable .ltRow')].find(e=>e._i==={i}&&e.style.display!=='none');
      if(!e) return null; const cols=window._dbgApp.lib().cols, k=cols.indexOf({json.dumps(col or 'name')});
      const c=e.children[Math.max(0,k)], r=c.getBoundingClientRect(), tr=document.getElementById('libTable').getBoundingClientRect();
      return {{x:Math.min(r.left+r.width/2,tr.right-30),y:r.top+r.height/2}}; }})()""", label=f"{i}行目の表示")
    return p["x"], p["y"]


def row_names(ed):
    return [(r["name"], r["key"]) for r in lib(ed)["rows"]]


def drag_from(ed, x0, y0, x1, y1, steps=10):
    """(x0,y0) から (x1,y1) へ本物のドラッグ＆ドロップ（nle_helpers.drag_media と同じ仕組み）"""
    ed.call("Input.setInterceptDrags", enabled=True)
    try:
        n0 = sum(1 for e in ed._events if e.get("method") == "Input.dragIntercepted")
        ed.move(x0, y0)
        ed.call("Input.dispatchMouseEvent", type="mousePressed", x=x0, y=y0, button="left", buttons=1, clickCount=1)
        for i in range(1, steps + 1):
            ed.call("Input.dispatchMouseEvent", type="mouseMoved", x=x0 + (x1 - x0) * i / steps, y=y0 + (y1 - y0) * i / steps,
                    button="left", buttons=1)
        evs = [e for e in ed._events if e.get("method") == "Input.dragIntercepted"]
        assert len(evs) > n0, "ドラッグが始まりません"
        data = evs[-1]["params"]["data"]
        for typ in ("dragEnter", "dragOver", "drop"):
            ed.call("Input.dispatchDragEvent", type=typ, x=x1, y=y1, data=data)
        ed.call("Input.dispatchMouseEvent", type="mouseReleased", x=x1, y=y1, button="left", buttons=0, clickCount=1)
    finally:
        ed.call("Input.setInterceptDrags", enabled=False)
        for e in list(ed._events):
            if e.get("method") == "Input.dragIntercepted":
                ed._events.remove(e)


# ---- 絞り込みのパネル ----
def open_filter(ed):
    if not ed.js("window._dbgApp.lib().panel"):
        click_sel(ed, "#libFiltBtn")
    wait_until(ed, "window._dbgApp.lib().panel", label="絞り込みのパネル")


def close_filter(ed):
    if ed.js("window._dbgApp.lib().panel"):
        click_sel(ed, "#libFiltPanel .lfClose")
    wait_until(ed, "!window._dbgApp.lib().panel", label="絞り込みのパネルを閉じる")


def _type_into(ed, sel, text):
    click_sel(ed, sel)
    ed.key("a", ctrl=True)
    if text:
        ed.call("Input.insertText", text=text)
    else:
        ed.key("Delete")
    ed.wait(0.1)


def filt_range(ed, k, lo="", hi=""):
    """範囲（k=stars/len/njs/nps/bpm）の下限・上限を入力欄に打ち込む"""
    open_filter(ed)
    _type_into(ed, f"#libFiltPanel .lfRow[data-k={k}] .lfLo", lo)
    _type_into(ed, f"#libFiltPanel .lfRow[data-k={k}] .lfHi", hi)
    want = json.dumps([lo, hi], separators=(",", ":"), ensure_ascii=False)   # JSON.stringify と同じ書き方
    wait_until(ed, f"JSON.stringify(window._dbgApp.lib().filter.{k})==={json.dumps(want)}", label=f"{k} の範囲")
    ed.wait(0.15)


def filt_diff(ed, d):
    open_filter(ed)
    click_sel(ed, f"#libFiltPanel .lfDf[data-d={d}]")
    ed.wait(0.15)


def filt_mode(ed, m):
    open_filter(ed)
    click_sel(ed, f"#libFiltPanel .lfMode input[data-m='{m}']")
    ed.wait(0.15)


def filt_check(ed, c):
    open_filter(ed)
    click_sel(ed, f"#libFiltPanel .lfChk input[data-c={c}]")
    ed.wait(0.15)

"""e2e_nle グループの共通部品（NLEのクリップ操作・MEDIA/アセットの通しテスト用）。

状態は開発用窓口 window._dbgApp の nle()（クリップ・選択・マーカー・レーン状態・Music）と nleScreen()/musicScreen()
（画面座標）から読む。操作は本物のマウス/キー入力（tools/cdp.py の click / key / drag）で行う。

- open_nle(t, 素材名): ページを開き直して素材を読み、起動時の非同期の初期化が終わるまで待つ（各テストの最初に使う）
- clips(ed, lk) / clip_xy(ed, clip, beat) / lane_y(ed, lk, track): クリップ一覧とクリック位置
- hover(ed, beat, lk, track): NLEの上にマウスを置く（C・L/S/M・Ctrl+E はマウスの位置で効く）
- menu(ed, x, y, text): 右クリックしてメニューの項目を押す
- export_dat(ed): 書き出しの各難易度.dat を辞書で（e2e_helpers.export_files を JSON にしたもの）
- take_errors(ed, 部分文字列): 想定どおりのエラー表示（showErr は console.error も出す）を回収して消す
- lib_items / drag_media(ed, 名前, x, y): MEDIAの一覧と、項目のドラッグ＆ドロップ（本物の入力）
- asset_dir / clear_assets: アセットの保存先（一時フォルダであることを確かめる）と、その掃除
"""
import json

from e2e_helpers import export_files, wait_until

KINDS = ("notes", "bombs", "walls", "arcs", "chains", "lights")


def nle(ed):
    return ed.js("window._dbgApp.nle()")


def scr(ed, beat=0):
    return ed.js(f"window._dbgApp.nleScreen({beat})")


def clips(ed, lk=None):
    """今の難易度のクリップ（拍順）。lk='n'/'l' で絞り込み"""
    cs = [c for c in nle(ed)["clips"] if lk is None or c["lk"] == lk]
    return sorted(cs, key=lambda c: (c["lk"], c["beat"], c["track"]))


def total(cs):
    """クリップの中身の数の合計（種類ごと）"""
    return {k: sum(c["n"][k] for c in cs) for k in KINDS}


def lane_y(ed, lk, track, frac=0.7):
    """レーンの中のy。frac=0.7 はクリップの本体（上端16pxのヘッダー・色の四角を避ける）。
    グループ（ノーツ/ライト）の表示窓より下に隠れている部分は使えないので、窓の中に収める
    （既定の画面サイズでは各3本のうち一番下のレーンが半分ほど隠れる）"""
    s = scr(ed)
    top = (s["notes"] if lk == "n" else s["lights"])[track]
    v0, v1 = nle(ed)["vp"][lk]
    y = top + s["laneH"] * frac
    lo, hi = max(top + 5, v0 + 2), min(top + s["laneH"] - 5, v1 - 3)
    assert lo <= hi, f"{lk}{track} のレーンが表示窓の外です"
    return min(max(y, lo), hi)


def clip_xy(ed, clip, beat=None, frac=0.7):
    """クリップの本体の画面座標。beat=クリップ内の絶対拍（省略時はクリップの中央）"""
    b = clip["beat"] + clip["len"] / 2 if beat is None else beat
    return scr(ed, b)["x"], lane_y(ed, clip["lk"], clip["track"], frac)


def open_nle(t, fx=None):
    """ページを開き直して素材を読み、起動時の非同期の初期化（ツールバーのアイコン読込の後に配置モードへ切り替える）が
    終わるまで待つ。遅いPCだと読込の後にカメラのモードや下の案内文が切り替わり、Q等のキーや案内の確認とぶつかるため"""
    from e2e_helpers import open_fixture
    ed = open_fixture(t, fx)
    wait_until(ed, "document.getElementById('pvVisAmbient').innerHTML!==''&&window._dbgApp.state().camMode==='place'",
               timeout=15, label="起動時の初期化の完了")
    return ed


def hover(ed, beat, lk="n", track=0, timeout=5.0):
    """NLEの拍 beat・レーンの上にマウスを置く。表示の窓が動いている途中でも合うまで置き直す"""
    import time
    end = time.time() + timeout
    while True:
        x = scr(ed, beat)["x"]
        y = lane_y(ed, lk, track)
        ed.move(x, y)
        if ed.js(f"Math.abs((window._dbgApp.nle().hover??-99)-{beat})<1e-6"):
            return x, y
        if time.time() > end:
            raise AssertionError(f"NLEの拍{beat}にマウスを置けません（{nle(ed)['hover']}）")
        ed.wait(0.05)


def select(ed, clip, shift=False):
    """クリップをクリックして選ぶ（Shift=追加）"""
    x, y = clip_xy(ed, clip)
    ed.click(x, y, shift=shift)
    wait_until(ed, f"window._dbgApp.nle().sel.includes({json.dumps(clip['id'])})", label=f"クリップ {clip['label']} の選択")


def menu_items(ed):
    return ed.js("[...document.querySelectorAll('#ctxmenu > button')].map(b=>b.textContent)")


def menu(ed, x, y, text):
    """右クリックしてメニューの項目（text を含むもの）を押す"""
    ed.click(x, y, button="right")
    wait_until(ed, "getComputedStyle(document.getElementById('ctxmenu')).display!=='none'", label="右クリックメニュー")
    p = ed.js(f"""(()=>{{ const b=[...document.querySelectorAll('#ctxmenu > button')].find(b=>b.textContent.includes({json.dumps(text)}));
      if(!b) return null; const r=b.getBoundingClientRect(); return {{x:r.left+r.width/2,y:r.top+r.height/2}}; }})()""")
    assert p, f"メニューに「{text}」がありません: {menu_items(ed)}"
    ed.move(p["x"], p["y"])
    ed.click(p["x"], p["y"])
    wait_until(ed, "getComputedStyle(document.getElementById('ctxmenu')).display==='none'", label="メニューが閉じる")


def export_dat(ed):
    """書き出し（ダウンロード）を横取りし、{ファイル名: JSON} を返す"""
    return {k: json.loads(v) for k, v in export_files(ed).items() if k.endswith(".dat")}




def undo(ed):
    ed.key("z", ctrl=True)


def redo(ed):
    ed.key("z", ctrl=True, shift=True)


def nle_mouse(ed):
    """キーの効き先をNLEにする（キー操作はマウスのあるペインで効く）。NLEの空いている所（ルーラーの下・溝の右）にマウスを置く"""
    s = scr(ed)
    ed.move(s["left"] + s["gut"] + 4, s["marker"] - 4)


def hover_canvas(ed):
    """3Dビューの左下寄り（マス・ノーツから離れた所）にマウスを置く＝キー操作の効き先を3Dビューにする"""
    r = ed.js("(()=>{const r=document.getElementById('cv').getBoundingClientRect();return {x:r.left,y:r.top,w:r.width,h:r.height}})()")
    ed.move(r["x"] + r["w"] * 0.1, r["y"] + r["h"] * 0.85)
    ed.wait(0.05)






def take_errors(ed, part):
    """console.error のうち part を含むもの（想定どおりのエラー表示）を数えて取り除く。t.no_errors() で誤検知しないため"""
    ed.wait(0.05)
    keep, n = [], 0
    for e in ed._events:
        p = e.get("params", {})
        if e.get("method") == "Runtime.consoleAPICalled" and p.get("type") == "error" and \
                any(part in str(a.get("value", "")) for a in p.get("args", [])):
            n += 1
            continue
        keep.append(e)
    ed._events[:] = keep
    return n


# ---- MEDIA（ライブラリ）とアセット ----
def lib_items(ed):
    """MEDIAの一覧に出ている項目の名前（表示中のもの）"""
    return ed.js("[...document.querySelectorAll('#libGrid .libItem')].filter(e=>e.style.display!=='none').map(e=>e.querySelector('.libName').textContent)")


def lib_item_xy(ed, name):
    p = ed.js(f"""(()=>{{ const e=[...document.querySelectorAll('#libGrid .libItem')].find(e=>e.querySelector('.libName').textContent==={json.dumps(name)});
      if(!e) return null; e.scrollIntoView({{block:'nearest'}}); const r=e.getBoundingClientRect(); return {{x:r.left+r.width/2,y:r.top+r.height/2}}; }})()""")
    assert p, f"MEDIAに「{name}」がありません: {lib_items(ed)}"
    return p["x"], p["y"]


def drag_media(ed, name, x1, y1, steps=10):
    """MEDIAの項目を (x1,y1) へドラッグ＆ドロップする（本物の入力）。
    CDP の Input.setInterceptDrags でブラウザのドラッグを横取りし、得たドラッグデータで dragEnter/dragOver/drop を送る
    （ページの dragstart → ドロップ先の dragover/drop の各ハンドラがそのまま動く）"""
    x0, y0 = lib_item_xy(ed, name)
    ed.call("Input.setInterceptDrags", enabled=True)
    try:
        n0 = sum(1 for e in ed._events if e.get("method") == "Input.dragIntercepted")
        ed.move(x0, y0)
        ed.call("Input.dispatchMouseEvent", type="mousePressed", x=x0, y=y0, button="left", buttons=1, clickCount=1)
        for i in range(1, steps + 1):
            ed.call("Input.dispatchMouseEvent", type="mouseMoved", x=x0 + (x1 - x0) * i / steps, y=y0 + (y1 - y0) * i / steps,
                    button="left", buttons=1)
        evs = [e for e in ed._events if e.get("method") == "Input.dragIntercepted"]
        assert len(evs) > n0, f"「{name}」のドラッグが始まりません"
        data = evs[-1]["params"]["data"]
        for typ in ("dragEnter", "dragOver", "drop"):
            ed.call("Input.dispatchDragEvent", type=typ, x=x1, y=y1, data=data)
        ed.call("Input.dispatchMouseEvent", type="mouseReleased", x=x1, y=y1, button="left", buttons=0, clickCount=1)
    finally:
        ed.call("Input.setInterceptDrags", enabled=False)
        for e in list(ed._events):   # 横取りの通知はページ内エラーではないが、溜めない
            if e.get("method") == "Input.dragIntercepted":
                ed._events.remove(e)


def asset_dir(ed):
    """アセットの保存先（serve.py の ASSET_DIR）。tools/cdp.py が NLM_DATA_DIR を一時フォルダにしているので、
    手元の asset/ でないことを確かめてから返す（手元の asset/・config/ を書き換えないため）"""
    import os
    import serve
    from pathlib import Path
    a, d = Path(serve.ASSET_DIR).resolve(), Path(ed.data_dir).resolve()
    assert d in a.parents, f"アセットの保存先が一時フォルダではありません: {a}"
    repo = (Path(__file__).resolve().parents[2] / "asset").resolve()
    assert a != repo, "アセットの保存先が手元の asset/ です"
    os.makedirs(a, exist_ok=True)
    return a


def clear_assets(ed):
    """一時フォルダのアセット（前のテストで作ったもの）を消す。ページを開き直す前に呼ぶ（起動時に asset/ を読むため）"""
    for p in asset_dir(ed).glob("*.nlmclip"):
        p.unlink()

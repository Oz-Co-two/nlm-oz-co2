"""上級編チュートリアル(docs/tutorial-advanced.md)用のスクリーンショットを撮り直すスクリプト。

tools/fixtures/basic.wav（120BPMのクリック音）を読み込み、実際にクリック・キー入力で赤青のノーツ・ライト・
マーカー・テンポパートを置きながら、各章の画面を docs/images/tutorial-advanced/ へ保存する。
ファイル名は「<章>-<連番>-<内容>.png」。撮影の部品（赤枠と番号・ノーツ配置・ダイアログの差し替え）は
make_tutorial_shots.py のものを使う。NLE の帯の位置は _dbgApp.nleScreen で取る（キャンバスに直接描くため）。

3章の「単独編集」(03-2b・03-2c)・「リンクしたクリップ」(03-2d〜03-2h)と4章の難易度間コピーの確認(04-2)・6章の「曲を解析」は、
他の画像と別の起動で撮る（クリップの色・名前・マーカーの番号の続きを他の画像へ持ち込まないため）。リンクは最後に撮るので元へは戻さない。
新規作成はノーツのレーン1本・ライト3本なので、単独編集は溝の右クリックで一番上にレーンを1本足してから撮る（撮った後に Ctrl+Z で戻す）。

「曲を解析しますか？」(06-1b)と、解析が終わった時の「次にやること」の案内(06-3b)は、テストの環境（tools/cdp.py の Editor.TEST_SETTINGS）では
出ない設定なので、撮る時だけ localStorage の bsnm_anaAsk / bsnm_anaGuide を消して出し（基本編と同じ analysis_helpers の ask_on・guide_on）、
撮った後に '0' へ戻す。
環境設定(10-1)の「曲の解析」の2つのチェックも、初めて使う人と同じ（オン）に見せて撮る。

「曲を解析」(6章)は、解析の応答を自動テストと同じ偽物（tests/_lib/analysis_helpers.py の ana_mock）にして、見本の結果
（TEMPO_SHOT・STRUCT_SHOT。曲名の無い、イントロ・Aメロ・Bメロ・サビが繰り返す形）で撮る。合成音を本当に解析しても中身が乏しいため。
解析からクリップを作る（06-7・06-8）は帯がある間に撮り、Ctrl+Z 1回で戻す。
撮った後は Ctrl+Z で帯・マーカーを戻し、後の画像を前と同じ状態で撮る。

「難易度を測る」(9章)は追加プラグイン nlm-rating が要る。撮影用の一時データフォルダへコピーして使うので、
取り込み済みのプラグインフォルダ（plugins/rating。中に current.json と版のフォルダがある）を
環境変数 NLM_RATING_DIR で指定する。省略時は配布フォルダ NLM-app/plugins/rating を探し、
無ければ「プラグイン未導入」の画面を撮る。

MEDIA ライブラリ（3章・10章の MEDIA タブ）は、自動テストと同じ素材 tools/fixtures/media_lib（架空の曲）を一時フォルダの
「CustomLevels」へ写し、撮影用のデータフォルダの config/library.json に記録してから読み直させる（exe 版のフォルダ選択で
選んだのと同じ状態。JS から記録を増やす口は無い）。部品は tests/_lib/e2e_helpers.py の media_lib_*（tests/ 側は変えない）。
ネットへは出ない（tools/cdp.py が NLM_NO_NET=1）。全曲データ・NLM推定の★は見本の値（SAMPLE_DETAILS・media_lib_sample_extra）、
プレイ記録は見本の PlayerData.dat を書いて使う。

使い方: .venv-build/Scripts/python.exe tools/make_advanced_shots.py [--en] [章番号...]
        例: make_advanced_shots.py 03 09 で3章と9章の画像だけ保存（操作は最初から全部行う）
        --en: 英語表示で撮って docs/images/tutorial-advanced-en/ へ保存する（英語版 docs/tutorial-advanced.en.md 用）
"""
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "tests" / "_lib"))   # MEDIA ライブラリの用意（e2e_helpers の media_lib_*。serve を import しない）
sys.path.insert(0, str(HERE.parent / "tests" / "e2e_nle"))   # NLE のクリップの位置・選択（nle_helpers。serve を import しない）
import make_tutorial_shots as mts  # noqa: E402
from cdp import Editor  # noqa: E402
import e2e_helpers as lib_h  # noqa: E402
import analysis_helpers as ana_h  # noqa: E402
import nle_helpers as nh  # noqa: E402

mts.OUT = HERE.parent / "docs" / "images" / ("tutorial-advanced-en" if mts.LANG == "en" else "tutorial-advanced")
# 上級編だけで文言から要素を探す所の、英語表示での文言（lang/en.json と同じ。基本編の表 mts.TEXT_EN に足す）
mts.TEXT_EN.update({
    "ラベルを変更": "Edit label",
    "親へジャンプ": "Jump to parent",
    "これを親にする": "Make this the parent",
    "リンクを解除": "Unlink",
    "他の難易度の同じ位置のクリップとリンク": "Link with clips at the same position in other difficulties",
    "ノーツを転送": "Send notes",
    "クリップを作る": "Create clips",
    "ノーツレーンを追加": "Add Notes lane",
})
W, H = mts.W, mts.H
RIGHT = mts.RIGHT
PLUGIN_DIR = Path(os.environ.get("NLM_RATING_DIR") or HERE.parent / "NLM-app" / "plugins" / "rating")
VIEW3D = (400, 560, 1120, 520)   # 3Dビューの中央下（基本編と同じ切り取り）


def move_panel(ed, sel, left=1100):
    """パネルは画面右端に出る＝撮影範囲（右端の音量メーターの手前まで）からはみ出すので、左へ寄せる（見出しドラッグと同じ移動）"""
    ed.js(f"(()=>{{const p=document.querySelector({sel!r}); p.style.left='{left}px'; p.style.right='auto'; return 1}})()")
    ed.wait(0.3)


def box(ed, sels, pad=14, deep=False):
    """セレクタ（または [x,y,w,h]）の外接矩形＋余白を、撮影範囲 (x, y, w, h) にして返す。
    deep=True は中身の要素も含めて囲む（大きさ0の入れ物＝パイメニューは項目だけが見えている）"""
    rs = []
    for s in sels:
        if isinstance(s, (list, tuple)):
            rs.append({"x": s[0], "y": s[1], "w": s[2], "h": s[3]})
        else:
            q = f"[...document.querySelectorAll({s!r}), ...document.querySelectorAll({(s + ' *')!r})]" if deep else f"[...document.querySelectorAll({s!r})]"
            rs += ed.js(q + """
                .map(e=>e.getBoundingClientRect()).filter(r=>r.width>0&&r.height>0)
                .map(r=>({x:r.left,y:r.top,w:r.width,h:r.height}))""") or []
    if not rs:
        raise SystemExit(f"撮影範囲の要素が見つかりません: {sels}")
    x0 = max(0, min(r["x"] for r in rs) - pad); y0 = max(0, min(r["y"] for r in rs) - pad)
    x1 = min(RIGHT, max(r["x"] + r["w"] for r in rs) + pad); y1 = min(H, max(r["y"] + r["h"] for r in rs) + pad)
    return round(x0), round(y0), round(x1 - x0), round(y1 - y0)


def wait_until(ed, js, err, timeout=20):
    """js が真になるまで待つ（errは失敗時の文言。関数なら呼んで作る）"""
    for _ in range(int(timeout / 0.25)):
        if ed.js(js):
            ed.wait(0.3); return
        ed.wait(0.25)
    raise SystemExit(err() if callable(err) else err)


def hide_menu(ed):
    ed.js("(()=>{const m=document.getElementById('ctxmenu'); m.style.display='none'; return 1})()")
    ed.wait(0.2)


def menu_click(ed, text):
    """右クリックメニュー(#ctxmenu)の、textを含む項目をクリックする"""
    ok = ed.js(f"""(()=>{{const it=[...document.querySelectorAll('#ctxmenu *')].reverse()
        .find(e=>e.textContent.includes({text!r})&&e.getBoundingClientRect().height>0&&e.getBoundingClientRect().height<40); if(!it) return false; it.click(); return true}})()""")
    if not ok:
        menu = ed.js("document.getElementById('ctxmenu').innerText")
        raise SystemExit(f"メニュー項目が見つかりません: {text}（メニュー: {menu!r}）")
    ed.wait(0.4)


def menu_mark(ed, text, tid):
    """メニュー項目に撮影用のidを付ける（赤枠の対象にするため）"""
    return ed.js(f"""(()=>{{const it=[...document.querySelectorAll('#ctxmenu *')].reverse()
        .find(e=>e.textContent.includes({text!r})&&e.getBoundingClientRect().height>0&&e.getBoundingClientRect().height<40); if(it) it.id={tid!r}; return !!it}})()""")


def nle(ed, beat=None):
    return ed.js(f"window._dbgApp.nleScreen({'null' if beat is None else beat})")


def key_hold(ed, key, code, vk):
    ed.call("Input.dispatchKeyEvent", type="keyDown", key=key, code=code, text=key, windowsVirtualKeyCode=vk, nativeVirtualKeyCode=vk)


def key_release(ed, key, code, vk):
    ed.call("Input.dispatchKeyEvent", type="keyUp", key=key, code=code, windowsVirtualKeyCode=vk, nativeVirtualKeyCode=vk)


MEDIA_W = 1150     # 詳細表示を撮る時の MEDIA の幅（既定の列が全部入る幅。上限は画面の幅の6割）
LIB_SIDE_W = 120   # 詳細表示を撮る時の左のカタログの幅
# 環境設定のプレイ記録の欄の場所。撮影では一時のデータフォルダ（PC のユーザー名を含む）になるので、既定の場所の例に置き換えて撮る
PLAY_PATH_SHOWN = r"C:\Users\YourName\AppData\LocalLow\Hyperbolic Magnetism\Beat Saber\PlayerData.dat"


def lib_col_rect(ed, col):
    """詳細表示の列（見出し〜最後の行）の画面上の矩形 [x, y, w, h]"""
    return ed.js(f"""(()=>{{ const h=document.querySelector('#libTable .ltH[data-col={col}]').getBoundingClientRect();
      const rows=[...document.querySelectorAll('#libTable .ltRow')].filter(e=>e.style.display!=='none').map(e=>e.getBoundingClientRect().bottom);
      return [h.left, h.top, h.width, Math.max(...rows)-h.top]; }})()""")


def lib_row_xy(ed, name, diff):
    """詳細表示の、曲名 name・難易度 diff の行の曲名のあたりの画面座標"""
    p = ed.js(f"""(()=>{{ const el=[...document.querySelectorAll('#libTable .ltRow')].find(e=>e._row&&e._row.d&&e._row.item.entry
        &&e._row.item.entry.name==={name!r}&&e._row.d.diff==={diff!r}&&e.style.display!=='none'); if(!el) return null;
      const r=el.getBoundingClientRect(), n=document.querySelector('#libTable .ltH[data-col=name]').getBoundingClientRect();
      return {{x:n.left+60,y:r.top+r.height/2}}; }})()""")
    if not p:
        raise SystemExit(f"詳細表示に {name} / {diff} の行がありません")
    return p["x"], p["y"]


def media_pane_clip(ed, top=22):
    """MEDIA のペインの範囲（上は番号の丸が入るようにメニューバーの下端まで広げる）"""
    r = t_rect(ed, "#pvpane")
    return 0, top, round(r["x"] + r["w"] + 4), round(r["y"] + r["h"] + 4 - top)


def eo_band(g, track):
    """nleScreen の結果 g から、ノーツのレーン track（内部の段）の溝の単独編集の帯の画面の矩形（{x,y,w,h}・表示窓に見えている所）"""
    b = next((b for b in g["eo"] if b["t"] == track), None)
    if not b:
        raise RuntimeError(f"段{track}の単独編集の帯が見えていません")
    return b


def t_rect(ed, sel):
    return ed.js(f"(()=>{{const r=document.querySelector({sel!r}).getBoundingClientRect();return {{x:r.left,y:r.top,w:r.width,h:r.height}}}})()")


def hide_toast(ed):
    """画面の下の知らせ（✅/⚠）を消す（撮る画像に写さない）"""
    ed.js("(e=>{e.style.display='none'; return 1})(document.getElementById('errToast'))")


def edit_only(ed, t):
    """3章「単独編集」（03-2b・03-2c）。新規作成のノーツのレーンは1本なので、溝の右クリックで一番上にレーンを足し（Notes 2＝内部の段0。
    今までのノーツは Notes 1＝段1へ下がる）、Notes 2 を単独編集にして3Dにノーツを置き、Notes 1 のノーツをクリックして帯を出す。撮った後は元へ戻す"""
    n0 = ed.js("window._dbgApp.state().counts.notes")
    lanes0 = ed.js("window._dbgApp.nle().lanes.n")
    g = nle(ed)
    ed.click(g["left"] + 60, g["notes"][0] + g["laneH"] - 6, button="right"); ed.wait(0.4)   # 溝の何もない所（名前・L/S/M・単独編集の帯の下）
    menu_click(ed, mts.L("ノーツレーンを追加"))
    wait_until(ed, f"window._dbgApp.nle().lanes.n==={lanes0 + 1}", "ノーツのレーンを足せません")
    hide_toast(ed); ed.wait(0.4)
    g = nle(ed)
    b = eo_band(g, 0)
    sw = (b["x"] + 14, b["y"] + b["h"] / 2)   # Notes 2（内部の段0＝一番上）の溝の2段目の単独編集の帯のスイッチ
    ed.click(*sw)
    wait_until(ed, "window._dbgApp.nle().editOnly===0", "単独編集のスイッチが入りません")
    mts.seek_to(ed, 4.5)
    mts.place_note(t, 0, 2, 0, 8)   # 赤と青のドット（向きの警告を出さない）。上の段の両端＝奥の Notes 1 のノーツと画面で重ならない所
    mts.place_note(t, 3, 2, 1, 8)
    wait_until(ed, f"window._dbgApp.state().counts.notes==={n0 + 2}&&window._dbgApp.nle().clips.some(c=>c.lk==='n'&&c.track===0)",
               lambda: f"単独編集のレーンに置けません: {n0} → {ed.js('window._dbgApp.state()')} {ed.js('window._dbgApp.nle().clips')} {ed.errors()}")
    # ---- 03-2b: NLE（①スイッチ ②単独編集のレーン） ----
    ed.move(1700, 1060); ed.wait(0.4)
    g = nle(ed)
    x17 = nle(ed, 17)["x"]
    lane = [g["left"] + g["gut"], g["notes"][0], x17 - g["left"] - g["gut"], g["laneH"]]
    b = eo_band(g, 0)
    t.shot("03-2b-edit-only-lane", marks=json.dumps([
        {"t": [b["x"], b["y"], b["w"], b["h"]], "n": 1, "at": "l", "pad": 2},
        {"t": lane, "n": 2, "at": "r", "pad": -1}]),
        clip=(round(g["left"]) - 46, round(g["ruler"]) - 6, round(x17 - g["left"]) + 92, round(g["lights"][0] - g["ruler"]) + 12))
    # ---- 03-2c: 3D（他のレーンのノーツをクリック→①帯 ②隅の表示） ----
    objs = [o for o in ed.js("window._dbgApp.objScreen()") if o["kind"] == "note" and o["inView"] and o["tr"] != 0]
    o = next((o for o in objs if abs(o["beat"] - 6) < 1e-6 and o["c"] == 0), None)   # Notes 1 の拍6の赤
    if o is None:
        raise SystemExit(f"Notes 1 の拍6のノーツが画面にありません: {[(x['beat'], x['tr']) for x in objs]}")
    ed.move(o["sx"], o["sy"]); ed.wait(0.2); ed.click(o["sx"], o["sy"]); ed.wait(0.3)
    wait_until(ed, "document.getElementById('eoBand').classList.contains('on')", "単独編集の帯が出ません")
    m = t.rect("#eoBand .eoMsg"); ed.move(m["x"] + m["w"] / 2, m["y"] + m["h"] / 2); ed.wait(0.4)   # 帯の上にマウス＝自然に消えない
    t.shot("03-2c-edit-only-band", marks="[{t:'#eoBand',n:1,at:'l'},{t:'#eoInd',n:2,at:'r'}]",
           clip=box(ed, ["#eoBand", "#eoInd", [o["sx"] - 150, o["sy"] - 60, 300, 120]], pad=46))
    # 元へ戻す（置いた2つを取り消し、単独編集をオフにして、足したレーンも Ctrl+Z で戻す）
    ed.move(960, 800); ed.wait(0.2)
    for _ in range(2):
        ed.key("z", ctrl=True); ed.wait(0.4)
    wait_until(ed, f"window._dbgApp.state().counts.notes==={n0}&&!window._dbgApp.nle().clips.some(c=>c.lk==='n'&&c.track===0)",
               "単独編集で置いたノーツを取り消せません")
    ed.click(*sw)
    wait_until(ed, "window._dbgApp.nle().editOnly===null", "単独編集をオフにできません")
    ed.move(960, 800); ed.wait(0.2); ed.key("z", ctrl=True)
    wait_until(ed, f"window._dbgApp.nle().lanes.n==={lanes0}", "足したノーツのレーンを Ctrl+Z で戻せません")
    hide_toast(ed)
    mts.seek_to(ed, 16)


# 曲を解析（6章）の見本。テンポ: 今の設定（BPM 120・無音追加 0）と無音追加が違い、知らせ（整数・2番目の候補・段差・揺れ・裏拍）を全部含む
TEMPO_SHOT = dict(ana_h.TEMPO, bpm=120.0, raw_bpm=119.982, lead_ms=265.4, alt_lead_ms=515.4, family=120.0,
                  drift=[[0.0, 121.0], [8.0, 119.4]], alt={"bpm": 90.0, "ratio": 0.87})
TEMPO_SHOT.pop("unknown_future_field", None)


def _sections():
    """構成の見本（32拍＝basic.wav の長さ）: イントロ・Aメロ・Bメロ・サビ（★）を2回・アウトロ。細かい区切りは2拍ずつ"""
    sec = [(0, "S1", "イントロ"), (4, "S2", "Aメロ"), (8, "S3", "Bメロ"), (12, "S4", "サビ"),
           (16, "S2", "Aメロ"), (20, "S3", "Bメロ"), (24, "S4", "サビ"), (28, "S5", "アウトロ")]
    cnt = {lab: sum(1 for s in sec if s[1] == lab) for _, lab, _ in sec}
    sections = [{"start": b, "end": b + 4, "label": lab, "count": cnt[lab], "chorus": lab == "S4", "name": nm} for b, lab, nm in sec]
    groups = "A B C D E F G H C D E F G H I J".split()
    sims = {"C": 0.84, "D": 0.79, "E": 0.81, "F": 0.62, "G": 0.9, "H": 0.88}
    segments = []
    for i, gname in enumerate(groups):
        others = [j * 2 for j, x in enumerate(groups) if x == gname and j != i]
        segments.append({"start": i * 2, "end": i * 2 + 2, "group": gname, "count": groups.count(gname),
                         "best": others[0] if others else None, "sim": sims.get(gname) if others else None})
    return {"version": 1, "sub": 4, "chorus": ["G", "H"], "sections": sections, "segments": segments}


STRUCT_SHOT = _sections()
RENAMED = "Guitar solo" if mts.LANG == "en" else "ギターソロ"   # 6章で S3 に付け直す名前


def sec_rect(ed, b0, b1, row="sec"):
    """帯の拍 b0〜b1 の、セクションの段（row='sec'）か細かい区切りの段（'seg'）の矩形 [x, y, w, h]"""
    a, b = ed.js(f"window._dbgApp.anaScreen({b0})"), ed.js(f"window._dbgApp.anaScreen({b1})")
    y0, h = (a["top"] + 3, 18) if row == "sec" else (a["top"] + 24, 13)
    return [a["x"], y0, b["x"] - a["x"], h]


def song_analysis(ed, t):
    """6章「曲を解析（テンポと構成）」（06-1〜06-8。06-7・06-8 は解析からクリップを作る）。撮った後は Ctrl+Z でクリップ・帯・名前・マーカーを戻す"""
    n0 = ed.js("window._dbgApp.state().counts.notes")
    if ed.js("window._dbgApp.nle().markers.length") or ed.js("window._dbgApp.analysis().data"):
        raise SystemExit("曲を解析の前にマーカーか解析の結果があります")
    running = lambda p: {"ok": True, "state": "running", "stage": "tempo", "progress": p}
    ana_h.ana_mock(ed, tempo=TEMPO_SHOT, structure=STRUCT_SHOT,
                   status_t1=[running(0.4), {"waitFor": "t", "then": running(0.7)}] + ana_h.status_seq("tempo", TEMPO_SHOT))
    ana_h.guide_on(ed)   # 解析が終わった時の「次にやること」の案内を出す（テストの環境は既定で出さない）。06-3b を撮ったら戻す
    # ---- 06-1: 解析中（スペクトログラムの溝の［🎼 曲を解析］から）。①進み具合（文とバー） ②やめる ----
    t.click_el("#anaStartBtn")
    wait_until(ed, "(a=>a.running&&a.running.stage==='tempo'&&a.running.progress>=0.4)(window._dbgApp.analysis())", "解析中になりません")
    ed.move(1700, 1060); ed.wait(0.6)
    prog = ed.js("""(()=>{ const rs=['#anaMsg .amTxt','#anaMsg .amBar'].map(s=>document.querySelector(s).getBoundingClientRect());
      const x0=Math.min(...rs.map(r=>r.left)), y0=Math.min(...rs.map(r=>r.top));
      return [x0, y0, Math.max(...rs.map(r=>r.right))-x0, Math.max(...rs.map(r=>r.bottom))-y0]; })()""")
    t.shot("06-1-analyze-running", marks=json.dumps([{"t": prog, "n": 1, "at": "b"}, {"t": "#anaMsg .amBtn", "n": 2, "at": "b"}]),
           clip=box(ed, ["#overview", "#specPane"], pad=40))
    # ---- 06-2: テンポの確認の画面 ----
    ana_h.ana_go(ed, "t")
    wait_until(ed, "!!document.querySelector('#dirtyDlg.anaTempo')", "テンポの確認の画面が出ません")
    ed.move(1700, 1060); ed.wait(0.3)
    # 行に撮影用の印を付ける（①提案 ②今の設定 ③補足 ④段差 ⑤揺れ ⑥裏拍 ⑦ボタン）
    ed.js("""(()=>{ const L=[...document.querySelectorAll('#dirtyDlg.anaTempo .atLine')];
      const warn=L.filter(e=>e.classList.contains('atWarn')), notes=L.filter(e=>e.classList.contains('atNote'));
      const uni=(es)=>{ const rs=es.map(e=>e.getBoundingClientRect()); const x0=Math.min(...rs.map(r=>r.left)), y0=Math.min(...rs.map(r=>r.top));
        return [x0, y0, Math.max(...rs.map(r=>r.right))-x0, Math.max(...rs.map(r=>r.bottom))-y0]; };
      const i=L.indexOf(warn[0]);
      window.__tutAt={prop:uni([L[1]]), cur:uni([L[2]]), note:uni(L.slice(3,i)), step:uni([warn[0]]),
        drift:uni([warn[1], L[L.indexOf(warn[1])+1]]), off:uni([warn[2], L[L.indexOf(warn[2])+1]]),
        btns:uni([...document.querySelectorAll('#dirtyDlg.anaTempo .ddBtns button')])};
      return 1; })()""")
    at = ed.js("window.__tutAt")
    if not all(at.values()):
        raise SystemExit("テンポの確認の画面の行が見本と合いません: " + str(ana_h.dialog_lines(ed)))
    marks = [{"t": at[k], "n": i + 1, "at": "l", "pad": 3} for i, k in enumerate(("prop", "cur", "note", "step", "drift", "off", "btns"))]
    t.shot("06-2-tempo-dialog", marks=json.dumps(marks), clip=box(ed, ["#dirtyDlg"], pad=50))
    t.click_el("#dirtyDlg button[data-v=none]")   # 適用しない（BPM 120 のまま構成を解析）
    ana_h.wait_band(ed, len(STRUCT_SHOT["sections"]))
    hide_toast(ed)
    # ---- 06-3b: 解析が終わった時の「次にやること」の案内（①手順 ②ボタンの場所の画像 ③次から出さない ④わかった） ----
    wait_until(ed, f"(i=>!!i&&i.complete&&i.naturalWidth>0)(document.querySelector('{ana_h.GUIDE} .agFig img'))", "解析が終わった時の案内が出ません")
    ed.move(1700, 1060); ed.wait(0.4)
    t.shot("06-3b-analysis-guide", marks=json.dumps([
        {"t": f"{ana_h.GUIDE} .agList", "n": 1, "at": "l"}, {"t": f"{ana_h.GUIDE} .agFig", "n": 2, "at": "l"},
        {"t": f"{ana_h.GUIDE} .agChk", "n": 3, "at": "l"}, {"t": f"{ana_h.GUIDE} .ddBtns button.pri", "n": 4, "at": "l"}]),
        clip=box(ed, ["#dirtyDlg"], pad=50))
    t.click_el(f"{ana_h.GUIDE} .ddBtns button.pri")   # わかった（閉じると溝のボタンが少しの間光る）
    wait_until(ed, f"!document.querySelector('{ana_h.GUIDE}')", "案内を閉じられません")
    wait_until(ed, "!document.getElementById('anaClipsBtn').classList.contains('glow')", "溝のボタンの光が消えません", timeout=10)
    ed.js("localStorage.setItem('bsnm_anaGuide','0');true")   # テストの環境と同じ（案内を出さない）へ戻す
    # ---- 06-3: 構成の帯（①同じ番号 ②★サビの候補 ③細かい区切り ④⋯ ⑤クリップを作る） ----
    ed.move(1700, 1060); ed.wait(0.4)
    t.shot("06-3-structure-band", marks=json.dumps([
        {"t": sec_rect(ed, 4, 8), "n": 1, "at": "tr", "pad": 1, "dy": -17}, {"t": sec_rect(ed, 16, 20), "n": 1, "at": "tr", "pad": 1, "dy": -17},
        {"t": sec_rect(ed, 12, 16), "n": 2, "at": "tr", "pad": 1, "dy": -17}, {"t": sec_rect(ed, 24, 28), "n": 2, "at": "tr", "pad": 1, "dy": -17},
        {"t": sec_rect(ed, 0, 32, "seg"), "n": 3, "at": "b", "pad": 1}, {"t": "#anaMenuBtn", "n": 4, "at": "l", "pad": 2},
        {"t": "#anaClipsBtn", "n": 5, "at": "b", "pad": 2}]),
        clip=box(ed, ["#overview", "#specPane"], pad=40))
    # ---- 06-4: 帯の右クリックのメニュー ----
    x, y = ana_h.band_point(ed, 6)
    ed.click(x, y, button="right"); ed.wait(0.4)
    n = ed.js("(()=>{ const bs=[...document.querySelectorAll('#ctxmenu > button')]; bs.forEach((b,i)=>b.id='tutAm'+i); return bs.length; })()")
    if n != 6:
        raise SystemExit(f"帯の右クリックのメニューの項目が見本と違います（{n}）: {ed.js('document.getElementById(`ctxmenu`).innerText')!r}")
    t.shot("06-4-band-menu", marks=json.dumps([{"t": f"#tutAm{i}", "n": i + 1, "at": "r", "pad": 1} for i in range(n)]),
           clip=box(ed, ["#ctxmenu", [x - 160, y - 30, 320, 50]], pad=40))
    hide_menu(ed)
    # ---- 06-5: S3 の名前を付け直してから、マーカーへ書き出す ----
    x, y = ana_h.band_point(ed, 10)
    ed.click(x, y); ed.click(x, y, count=2)
    wait_until(ed, "document.activeElement&&document.activeElement.tagName==='INPUT'&&document.activeElement.style.position==='fixed'", "名前の入力欄が出ません")
    ed.js("(i=>{i.select(); return 1})(document.activeElement)")
    ed.call("Input.insertText", text=RENAMED)
    ed.key("Enter"); ed.wait(0.3)
    wait_until(ed, f"window._dbgApp.analysis().labels.filter(s=>s.startsWith({json.dumps(RENAMED + ' S3')})).length===2", "名前を付け直せません")
    x, y = ana_h.band_point(ed, 30)
    ed.click(x, y, button="right"); ed.wait(0.4)
    menu_click(ed, mts.L("セクションの頭にマーカーを書き出す"))
    wait_until(ed, "window._dbgApp.nle().markers.length===8", "マーカーへ書き出せません")
    hide_toast(ed)
    ed.move(1700, 1060); ed.wait(0.4)
    g = nle(ed)
    t.shot("06-5-markers", marks=json.dumps([
        {"t": [g["left"] + g["gut"], g["marker"], g["w"] - g["gut"], g["lanes"] - g["marker"]], "n": 1, "at": "l", "pad": 0},
        {"t": sec_rect(ed, 8, 12), "n": 2, "at": "tr", "pad": 1, "dy": -17}, {"t": sec_rect(ed, 20, 24), "n": 2, "at": "tr", "pad": 1, "dy": -17}]),
        clip=box(ed, ["#ndcv", "#overview", "#specPane"], pad=40))
    # ---- 06-6: 目盛りが変わった（BPM を1つ上げる。BPM の欄は履歴に積まないので、撮った後に1つ下げて戻す） ----
    t.click_el("#bpmField .bfA[data-k=up]")
    wait_until(ed, "window._dbgApp.analysis().stale&&window._dbgApp.analysis().msg!==''", "目盛りが変わった知らせが出ません")
    ed.move(1700, 1060); ed.wait(0.5)
    t.shot("06-6-stale", marks="[{t:'#anaMsg',n:1,at:'l'}]", clip=box(ed, ["#overview", "#specPane"], pad=40))
    t.click_el("#bpmField .bfA[data-k=dn]")
    wait_until(ed, "window._dbgApp.state().BPM===120&&!window._dbgApp.analysis().stale", "BPM を 120 に戻せません")
    # ---- 06-7: 解析からクリップを作る（帯の右クリック「クリップを作る…」の確認の画面。①単位 ②難易度 ③リンク ④まとめ） ----
    lanes0 = ed.js("window._dbgApp.nle().lanes.n")
    x, y = ana_h.band_point(ed, 6)
    ed.click(x, y, button="right"); ed.wait(0.4)
    menu_click(ed, mts.L("クリップを作る"))
    wait_until(ed, "!!document.querySelector('#dirtyDlg[data-ana=clips] .ddBtns button')", "解析からクリップを作る画面が出ません")
    ed.move(1700, 1060); ed.wait(0.3)
    ed.js("""(d=>{ const o=d.querySelectorAll(':scope > .lkOpts'); o[0].id='tutAcUnit'; o[1].id='tutAcLink'; return o.length; })
      (document.querySelector('#dirtyDlg[data-ana=clips]'))""")
    t.shot("06-7-clips-dialog", marks=json.dumps([{"t": "#tutAcUnit", "n": 1, "at": "l"}, {"t": "#dirtyDlg .acDiffs", "n": 2, "at": "l"},
                                                  {"t": "#tutAcLink", "n": 3, "at": "l"}, {"t": "#dirtyDlg .acSum", "n": 4, "at": "l"}]),
           clip=box(ed, ["#dirtyDlg"], pad=50))
    # ---- 06-8: 作った後の NLE（①新しいレーンと作ったクリップ ②単独編集）。撮ったら Ctrl+Z 1回で戻す ----
    t.click_el("#dirtyDlg[data-ana=clips] .ddBtns button.pri")
    wait_until(ed, f"window._dbgApp.nle().lanes.n==={lanes0 + 1}&&window._dbgApp.nle().editOnly===0", "解析からクリップを作れません")
    hide_toast(ed)
    ed.move(1700, 1060); ed.wait(0.4)
    g = nle(ed)
    b = eo_band(g, 0)
    t.shot("06-8-clips-made", marks=json.dumps([
        {"t": [g["left"] + g["gut"], g["notes"][0], g["w"] - g["gut"], g["laneH"]], "n": 1, "at": "tr", "pad": 1},
        {"t": [b["x"], b["y"], b["w"], b["h"]], "n": 2, "at": "l", "pad": 2}]),
        clip=(round(g["left"]) - 46, round(g["ruler"]) - 6, round(min(RIGHT, g["left"] + g["w"] + 10) - g["left"]) + 46,
              round(g["lights"][0] - g["ruler"]) + 12))
    nh.nle_mouse(ed); ed.key("z", ctrl=True)
    wait_until(ed, f"window._dbgApp.nle().lanes.n==={lanes0}&&window._dbgApp.nle().editOnly===null", "作ったクリップを Ctrl+Z で戻せません")
    hide_toast(ed)
    # 元へ戻す（マーカーの書き出し・名前の付け直し・帯の到着を1つずつ Ctrl+Z）
    ed.move(960, 800); ed.wait(0.2)
    for cond in ("window._dbgApp.nle().markers.length===0", "!window._dbgApp.analysis().labels.some(s=>s.startsWith(" + json.dumps(RENAMED) + "))",
                 "!window._dbgApp.analysis().data&&!window._dbgApp.analysis().shown"):
        ed.key("z", ctrl=True)
        wait_until(ed, cond, f"Ctrl+Z で戻せません: {cond}")
    if ed.js("window._dbgApp.state().counts.notes") != n0 or ed.js("window._dbgApp.prev().leadInMs") != 0:
        raise SystemExit("曲を解析の後に、ノーツか無音追加が変わっています")
    hide_toast(ed)


LINK_NAME = "Chorus" if mts.LANG == "en" else "サビ"   # 3章でリンクするクリップの名前


def clip_rect(ed, c):
    """NLE のクリップの画面上の矩形 [x, y, w, h]（描き方と同じ: レーンの上端+4・高さはレーン-8）"""
    g = nle(ed)
    x0, x1 = nle(ed, c["beat"])["x"], nle(ed, c["beat"] + c["len"])["x"]
    return [x0, g["notes" if c["lk"] == "n" else "lights"][c["track"]] + 4, x1 - x0, g["laneH" if c["lk"] == "n" else "laneHL"] - 8]


def nle_deselect(ed):
    nh.nle_mouse(ed); ed.key("a")
    wait_until(ed, "window._dbgApp.nle().sel.length===0", "クリップの選択を外せません")


def nle_paste_at(ed, beat, track, link=False):
    """選んでいるクリップをコピーして拍 beat へ貼り付け（link=True はリンクして貼り付け）、貼ったクリップを返す"""
    ids0 = {c["id"] for c in nh.clips(ed, "n")}
    nh.nle_mouse(ed); ed.key("c", ctrl=True)
    ed.key("v", ctrl=True, shift=link)
    wait_until(ed, "!!window._dbgApp.nle().paste", "貼り付けの追従が始まりません")
    nh.hover(ed, beat, "n", track)
    ed.click(*nh.clip_xy(ed, {"beat": beat, "len": 0, "lk": "n", "track": track}))
    wait_until(ed, f"window._dbgApp.nle().clips.filter(c=>c.lk==='n').length==={len(ids0) + 1}", f"拍{beat}へ貼り付けられません")
    return next(c for c in nh.clips(ed, "n") if c["id"] not in ids0)


def clip_link(ed, t):
    """3章「リンクしたクリップ」（03-2d〜03-2g）と4章の難易度間コピーの確認（04-2）。
    Notes 1 の拍8〜12のクリップに名前を付け、コピーして拍20へ貼り付け → 2つを選んで K（親を選ぶ画面）→ 拍8を親にリンク →
    親を拍28へリンクして貼り付け（Ctrl+Shift+V）。この起動の最後に撮るので、元へは戻さない"""
    src = next((c for c in nh.clips(ed, "n") if c["beat"] == 8 and c["len"] == 4), None)
    if src is None:
        raise SystemExit(f"拍8〜12のクリップがありません: {nh.clips(ed, 'n')}")
    tr = src["track"]
    # 名前を付ける（右クリック「ラベルを変更…」→ その場の入力欄）
    ed.click(*nh.clip_xy(ed, src), button="right"); ed.wait(0.4)
    menu_click(ed, mts.L("ラベルを変更"))
    wait_until(ed, "!!document.querySelector('body > input[type=text]')", "クリップの名前の入力欄が出ません")
    ed.js(f"""(i=>{{ i.value={json.dumps(LINK_NAME)}; i.dispatchEvent(new KeyboardEvent('keydown',{{key:'Enter',bubbles:true}})); return 1; }})
      ([...document.querySelectorAll('body > input[type=text]')].pop())""")
    wait_until(ed, f"window._dbgApp.nle().clips.some(c=>c.label==={json.dumps(LINK_NAME)})", "クリップに名前を付けられません")
    # コピーして拍20へ（普通の貼り付け）→ 2つを選んで K
    nle_deselect(ed); nh.select(ed, src)
    b = nle_paste_at(ed, 20, tr)
    nle_deselect(ed); nh.select(ed, src); nh.select(ed, b, shift=True)
    nh.nle_mouse(ed); ed.key("k")
    wait_until(ed, "!!document.querySelector('#dirtyDlg[data-lk=\"parent-link\"] .ddBtns button')", "親を選ぶ画面が出ません")
    ed.move(1700, 1060); ed.wait(0.3)
    ed.js("(e=>{e.id='tutLkOpts'; return 1})(document.querySelector('#dirtyDlg .lkOpts'))")
    # ---- 03-2d: 親を選ぶ画面（①候補・②リンクする） ----
    t.shot("03-2d-link-dialog", marks="[{t:'#tutLkOpts',n:1,at:'l'},{t:'#dirtyDlg .ddBtns button.pri',n:2,at:'l'}]",
           clip=box(ed, ["#dirtyDlg"], pad=50))
    t.click_el("#dirtyDlg .ddBtns button.pri")   # 既定（拍の早い方＝拍8）を親に
    wait_until(ed, "window._dbgApp.nle().clips.filter(c=>c.link).length===2", "リンクできません")
    # 親を拍28へリンクして貼り付け（Ctrl+Shift+V）＝3つのリンク
    nle_deselect(ed); nh.select(ed, src)
    c3 = nle_paste_at(ed, 28, tr, link=True)
    wait_until(ed, "window._dbgApp.nle().clips.filter(c=>c.link).length===3", "リンクして貼り付けられません")
    nle_deselect(ed)
    hide_toast(ed)
    mts.seek_to(ed, 16)   # 再生ヘッド（赤い線）をリンクしたクリップに重ねない
    # ---- 03-2e: NLE（①親 ②子） ----
    ed.move(1700, 1060); ed.wait(0.4)
    cs = {c["id"]: c for c in nh.clips(ed, "n")}
    par, kids = cs[src["id"]], [cs[b["id"]], cs[c3["id"]]]
    if not par["par"] or any(k["par"] or k["link"] != par["link"] for k in kids):
        raise SystemExit(f"リンクの親子が見本と違います: {list(cs.values())}")
    g = nle(ed)
    # 枠は子の点線の外側に・番号はクリップの上（空いている Notes 2）に置く
    marks = [{"t": clip_rect(ed, par), "n": 1, "at": "tr", "pad": 5, "dy": -16}] + \
            [{"t": clip_rect(ed, k), "n": 2, "at": "tr", "pad": 5, "dy": -16} for k in kids]
    x_end = min(RIGHT, g["left"] + g["w"] + 24)
    t.shot("03-2e-link-clips", marks=json.dumps(marks),
           clip=(round(g["left"]) - 10, round(g["ruler"]) - 6, round(x_end - g["left"]) + 10, round(g["lights"][0] - g["ruler"]) + 12))
    # ---- 03-2g: 子の右クリックメニュー（①親へジャンプ ②これを親にする ③リンクを解除 ④他の難易度とリンク） ----
    x, y = nh.clip_xy(ed, kids[0], kids[0]["beat"] + 0.3)   # クリップの左寄り（メニューが画面の右端の撮影範囲からはみ出さない）
    ed.click(x, y, button="right"); ed.wait(0.4)
    for i, text in enumerate(("親へジャンプ", "これを親にする", "リンクを解除", "他の難易度の同じ位置のクリップとリンク")):
        if not menu_mark(ed, mts.L(text), f"tutLkM{i}"):
            raise SystemExit(f"子の右クリックに「{text}」がありません: {ed.js('document.getElementById(`ctxmenu`).innerText')!r}")
    ed.move(1700, 1060); ed.wait(0.3)
    t.shot("03-2g-link-menu", marks=json.dumps([{"t": f"#tutLkM{i}", "n": i + 1, "at": "r", "pad": 1} for i in range(4)]),
           clip=box(ed, ["#ctxmenu", clip_rect(ed, kids[0])], pad=56))
    hide_menu(ed)
    # ---- 03-2f: 3D で子のノーツをクリック → 帯 ----
    mts.seek_to(ed, 20)
    objs = [o for o in ed.js("window._dbgApp.objScreen()") if o["kind"] == "note" and o["inView"] and 20 <= o["beat"] < 24]
    if not objs:
        raise SystemExit("子のノーツが3Dに見えません")
    o = max(objs, key=lambda o: o["sy"])   # 一番手前（下）のノーツ
    ed.move(o["sx"], o["sy"]); ed.wait(0.2); ed.click(o["sx"], o["sy"])
    wait_until(ed, "(b=>!!b&&b.classList.contains('on'))(document.getElementById('lkBand'))", "子のノーツを触った帯が出ません")
    hide_toast(ed)
    m = t.rect("#lkBand .lkMsg"); ed.move(m["x"] + m["w"] / 2, m["y"] + m["h"] / 2); ed.wait(0.4)   # 帯の上にマウス＝自然に消えない
    t.shot("03-2f-link-kid-band", marks="[{t:'#lkBand',n:1,at:'l'}]",
           clip=box(ed, ["#lkBand", [o["sx"] - 150, o["sy"] - 60, 300, 120]], pad=46))
    ed.js("(b=>{b.classList.remove('on'); return 1})(document.getElementById('lkBand'))")
    # ---- 03-2h: 親を消す → 次の親を選ぶ画面（①候補 ②決定 ③キャンセル）。［キャンセル］で削除ごと取り消す ----
    mts.seek_to(ed, 16)
    nle_deselect(ed); nh.select(ed, cs[src["id"]])
    nh.nle_mouse(ed); ed.key("Delete")
    wait_until(ed, "!!document.querySelector('#dirtyDlg[data-lk=\"parent-next\"] .ddBtns button')", "次の親を選ぶ画面が出ません")
    ed.move(1700, 1060); ed.wait(0.3)
    if ed.js("document.querySelectorAll('#dirtyDlg .ddBtns button').length") != 2:
        raise SystemExit("次の親を選ぶ画面に［キャンセル］がありません: " + str(ed.js("document.getElementById('dirtyDlg').innerText")))
    ed.js("""(d=>{ d.querySelector('.lkOpts').id='tutLkNext'; d.querySelector('.ddBtns button:not(.pri)').id='tutLkCancel'; return 1; })
      (document.getElementById('dirtyDlg'))""")
    t.shot("03-2h-link-next-parent", marks="""[{t:'#tutLkNext',n:1,at:'l'},{t:'#dirtyDlg .ddBtns button.pri',n:2,at:'b'},
      {t:'#tutLkCancel',n:3,at:'b'}]""", clip=box(ed, ["#dirtyDlg"], pad=50))
    t.click_el("#tutLkCancel")
    wait_until(ed, f"!document.getElementById('dirtyDlgBg')&&window._dbgApp.nle().clips.some(c=>c.id==={json.dumps(src['id'])}&&c.par)",
               "［キャンセル］で親の削除を取り消せません")
    nle_deselect(ed)
    hide_toast(ed)
    # ---- 04-2: 難易度のメニュー「ノーツを転送 → Expert」の確認（①親の難易度に繋ぐ）。撮ったら取り消す ----
    ed.move(960, 800); ed.wait(0.2)
    t.click_el("#diffBar .dfSeg.on"); ed.wait(0.5)
    if not menu_mark(ed, mts.L("ノーツを転送"), "tutSend"):
        raise SystemExit("難易度のメニューが出ません")
    r = t.rect("#tutSend"); ed.move(r["x"] + 20, r["y"] + r["h"] / 2); ed.wait(0.5)
    ok = ed.js("""(()=>{ const b=[...document.querySelectorAll('#ctxmenu .ctxsub button')].find(b=>b.textContent.trim()==='→ Expert');
      if(!b) return false; b.click(); return true; })()""")
    if not ok:
        raise SystemExit("ノーツを転送の → Expert がありません")
    wait_until(ed, "!!document.querySelector('#dirtyDlg[data-lk=\"copy\"] .ddBtns button')", "難易度間コピーの確認が出ません")
    ed.move(1700, 1060); ed.wait(0.3)
    t.shot("04-2-diff-copy-link", marks="[{t:'#dirtyDlg .lkOpt',n:1,at:'l'}]", clip=box(ed, ["#dirtyDlg"], pad=50))
    ed.key("Escape")
    wait_until(ed, "!document.getElementById('dirtyDlgBg')", "難易度間コピーの確認を閉じられません")


def media_library(ed, t):
    """3章「MEDIA ライブラリ」と10章の環境設定の MEDIA タブ（03-3〜03-8・10-2）"""
    # 素材（架空の曲）を一時フォルダの CustomLevels へ写して記録する（カタログに「CustomLevels」と出る）。
    # Extras の画像・音楽は名前だけ分かりやすくする（見本の値は曲のフォルダ名で引くので影響しない）
    tmp = Path(tempfile.mkdtemp(prefix="nlm_shots_lib_"))
    try:
        lib = tmp / "CustomLevels"
        shutil.copytree(lib_h.MEDIA_LIB, lib)
        (lib / "Extras" / "art.png").rename(lib / "Extras" / "artwork.png")
        (lib / "Extras" / "loose.wav").rename(lib / "Extras" / "my-song.wav")
        lib_h.media_lib_load(ed, extra=lib_h.media_lib_sample_extra(), covers=2, details=lib_h.SAMPLE_DETAILS, paths=[lib])
        # 見本のプレイ記録（Alpha Song の Hard・Expert と Beta Song の Normal を遊んだ・Alpha Song はお気に入り）。
        # ハッシュはテストのサーバー（同じプロセスの serve.LIBRARY）の走査の結果から取る（Editor の起動後なので手元の config/ は触らない）
        import serve
        lid = next(x["id"] for x in ed.js("window._dbgApp.lib()")["libs"] if x["native"])
        hs = {k: serve.LIBRARY.get_map(lid, rel)["hash"].upper() for k, rel in (("a", "1a01 (Alpha Song - MapperA)"), ("b", "1b02 (Beta Song - MapperB)"))}
        rec = lambda k, df, plays, best, rank, fc: {"levelId": "custom_level_" + hs[k], "difficulty": df, "beatmapCharacteristicName": "Standard",
                                                   "highScore": best, "maxCombo": 50, "fullCombo": fc, "maxRank": rank, "validScore": True, "playCount": plays}
        pd = {"localPlayers": [{"levelsStatsData": [rec("a", 2, 12, 412345, 5, True), rec("a", 3, 5, 301234, 4, False), rec("b", 1, 3, 150000, 6, True)],
                                "favoritesLevelIds": ["custom_level_" + hs["a"]]}]}
        (Path(ed.data_dir) / "PlayerData.dat").write_text(json.dumps(pd), encoding="utf-8")
        ed.js("window._dbg.rt.libRefreshExtra().then(()=>true)")
        wait_until(ed, "[...Array(12).keys()].some(i=>!!((window._dbgApp.libCell(i,'plays')||{}).text))", "見本のプレイ記録が一覧に入りません")
        ed.move(1700, 1060); ed.wait(0.3)

        # ---- 03-3: グリッド（既定の幅）。フォルダを追加・カタログ・表示の切り替え・大きさ ----
        ed.js("""(()=>{ const c=[...document.querySelectorAll('#libList .libCat')].find(e=>e._lib&&e._lib.native); if(c) c.id='tutLibCat'; return !!c; })()""")
        t.shot("03-3-media-grid", marks="""[{t:'#libAddBtn',n:1,at:'tr'},{t:'#tutLibCat',n:2,at:'b'},
          {t:'#libViewSeg',n:3,at:'b'},{t:'#libSizeGrp',n:4,at:'b'}]""", clip=media_pane_clip(ed))

        # ---- 03-4: 詳細表示（MEDIA を広げ、カタログを少し狭め、★の降順に並べる） ----
        sv = t.center("#splitV"); ed.drag(sv[0], sv[1], MEDIA_W, sv[1]); ed.wait(0.8)
        t.click_el("#libViewSeg button[data-view=detail]"); ed.wait(0.6)
        ss = t.rect("#libSideSplit"); sx = ss["x"] + ss["w"] / 2
        ed.drag(sx, ss["y"] + 120, sx + (LIB_SIDE_W - t.rect("#libSide")["w"]), ss["y"] + 120); ed.wait(0.5)
        for _ in range(2):   # 1回目＝昇順 ▲・2回目＝降順 ▼
            t.click_el("#libTable .ltH[data-col=stars]"); ed.wait(0.4)
        # 既定の列が全部入るまで一覧の文字を小さくする（既定 13px。英語は見出しが長く、13px では右端のプレイ回数が切れる）
        for fs in (13, 12, 11):
            ed.js(f"(s=>{{ s.value={fs}; s.dispatchEvent(new Event('input')); return 1; }})(document.getElementById('libSize'))"); ed.wait(0.5)
            if ed.js("(e=>e.scrollWidth<=e.clientWidth+1)(document.getElementById('libTable'))"):
                break
        ed.move(1700, 1060); ed.wait(0.4)
        marks = [{"t": lib_col_rect(ed, "stars"), "n": 1, "at": "b", "pad": 1},
                 {"t": lib_col_rect(ed, "uploaded"), "n": 2, "at": "b", "pad": 1},
                 {"t": lib_col_rect(ed, "plays"), "n": 3, "at": "b", "pad": 1},
                 {"t": "#libSrc", "n": 4, "at": "r"}]
        t.shot("03-4-media-detail", marks=json.dumps(marks), clip=media_pane_clip(ed))

        # ---- 03-5: 列のメニュー（見出しの右クリック） ----
        x, y = t.center("#libTable .ltH[data-col=stars]")
        ed.click(x, y, button="right"); ed.wait(0.5)
        if not ed.js("!!document.getElementById('libColMenu')"):
            raise SystemExit("列のメニューが出ません")
        m, hn, hd = t.rect("#libColMenu"), t.rect("#libTable .ltH[data-col=name]"), t.rect("#libTable .ltHead")
        x0, y0 = hn["x"] - 4, hd["y"] - 6   # 表の左端（曲名の列）から、メニューの右下まで
        t.shot("03-5-media-columns", marks="[{t:'#libColMenu',pad:3}]",
               clip=(round(x0), round(y0), round(m["x"] + m["w"] + 24 - x0), round(m["y"] + m["h"] + 16 - y0)))
        ed.key("Escape"); ed.wait(0.3)

        # ---- 03-6: 検索とフィルター（★5以上） ----
        t.click_el("#libFiltBtn"); ed.wait(0.5)
        ed.js("(i=>{ i.value='5'; i.dispatchEvent(new Event('input')); return 1; })(document.querySelector('#libFiltPanel .lfRow[data-k=stars] .lfLo'))")
        ed.wait(0.6)
        ed.move(1700, 1060); ed.wait(0.3)
        t.shot("03-6-media-filter", marks="""[{t:'#libSearchBox',n:1,at:'tl'},{t:'#libFiltBtn',n:2,at:'tl'},
          {t:'#libCount',n:3,at:'b'},{t:'#libFiltClear',n:4,at:'b'}]""", clip=media_pane_clip(ed))
        t.click_el("#libFiltPanel .lfClose"); ed.wait(0.3)
        t.click_el("#libFiltClear"); ed.wait(0.5)

        # ---- 03-7: 🔍 の確認（全曲データに無い曲。送る前に出る） ----
        t.click_el("#libTable .ltLook"); ed.wait(0.6)
        if not ed.js("!!document.getElementById('dirtyDlg')"):
            raise SystemExit("🔍 の確認が出ません")
        t.shot("03-7-media-lookup", clip=box(ed, ["#dirtyDlg"], pad=30))
        t.click_el("#dirtyDlg button:not(.pri)"); ed.wait(0.4)

        # ---- 03-8: 行の右クリック（★を計算・NLM推定）。★の無い2曲の行（Alpha Song の Hard・Gamma V4）を Ctrl＋クリックで選んで開く ----
        x, y = lib_row_xy(ed, "Alpha Song", "Hard")
        ed.click(x, y); ed.wait(0.3)
        x2, y2 = lib_row_xy(ed, "Gamma V4", "Expert")
        ed.click(x2, y2, ctrl=True); ed.wait(0.3)
        ed.click(x, y, button="right"); ed.wait(0.5)
        n = ed.js("""(()=>{ const bs=[...document.querySelectorAll('#ctxmenu button')].filter(b=>b.textContent.trim().startsWith('★'));
          bs.forEach((b,i)=>b.id='tutRate'+i); return bs.length; })()""")
        if n != 2:
            raise SystemExit(f"行の右クリックに★を計算の項目がありません（{n}）")
        t.shot("03-8-media-row-menu", marks="[{t:'#tutRate0',n:1,at:'r'},{t:'#tutRate1',n:2,at:'r'}]",
               clip=box(ed, ["#ctxmenu", [x - 60, y - 40, 120, 80], [x2 - 60, y2 - 14, 120, 28]], pad=50))
        hide_menu(ed)

        # ---- 10-2: 環境設定の MEDIA タブ ----
        # exe 版の画面（［ファイルを選ぶ…］がある）で撮るため、exe 版の窓口（pywebview）のプレイ記録の選択だけを置く。撮った後に外す
        ed.js("window.pywebview={api:{lib_pick_playdata:async()=>null}};true")
        t.click_el("#mbSettings"); ed.wait(0.6)
        t.click_el("#settingsBox .setTab[data-tab=media]")
        wait_until(ed, "!!document.getElementById('libPlayState').textContent&&!!document.getElementById('libNetState').textContent",
                   "環境設定の MEDIA タブの状態が出ません")
        ed.js(f"(e=>{{ e.textContent={PLAY_PATH_SHOWN!r}; e.title=e.textContent; return 1; }})(document.getElementById('libPlayPath'))")
        # ②は「★の計算を同時に何曲まで」の行と、その下の説明の行をまとめて囲む
        rate = ed.js("""(()=>{ document.getElementById('libNetOn').closest('.row').id='tutSetNet';
          document.getElementById('libPlayState').closest('.row').id='tutSetPlay';
          const a=document.getElementById('libRatePar').closest('.slRow'), b=a.nextElementSibling;
          const r1=a.getBoundingClientRect(), r2=b.getBoundingClientRect();
          return [r1.left, r1.top, Math.max(r1.right,r2.right)-r1.left, r2.bottom-r1.top]; })()""")
        t.shot("10-2-settings-media", marks=json.dumps([{"t": "#tutSetNet", "n": 1, "at": "l"}, {"t": rate, "n": 2, "at": "l"},
                                                         {"t": "#tutSetPlay", "n": 3, "at": "l"}]),
               clip=box(ed, ["#settingsBox"], pad=40))
        t.click_el("#settingsBox .setTab[data-tab=app]"); ed.wait(0.3)
        t.click_el("#settingsClose"); ed.wait(0.4)
        ed.js("delete window.pywebview;true")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def ask_dialog(ed, t):
    """6章「曲を解析しますか？」（06-1b。①できること ②次から聞かない ③解析する ④今はしない）。曲を読み込んだ時に出る。
    撮ったら［今はしない］で閉じ、テストの環境と同じ（聞かない）へ戻す"""
    ask = ana_h.ASK
    wait_until(ed, f"!!document.querySelector('{ask} .ddBtns button')", "「曲を解析しますか？」が出ません")
    ed.move(1700, 1060); ed.wait(0.4)
    t.shot("06-1b-ask-dialog", marks=json.dumps([
        {"t": f"{ask} .aaList", "n": 1, "at": "l"}, {"t": f"{ask} .aaChk", "n": 2, "at": "l"},
        {"t": f"{ask} .ddBtns button[data-v=go]", "n": 3, "at": "b"}, {"t": f"{ask} .ddBtns button[data-v=later]", "n": 4, "at": "b"}]),
        clip=box(ed, ["#dirtyDlg"], pad=50))
    t.click_el(f"{ask} .ddBtns button[data-v=later]")
    wait_until(ed, f"!document.querySelector('{ask}')", "「曲を解析しますか？」を閉じられません")
    ed.js("localStorage.setItem('bsnm_anaAsk','0');true")


def setup(ed, ask=False):
    """曲（basic.wav）を読み込み、ノーツを置く: 2〜15拍目に赤青1個ずつ、振り下ろし/振り上げを交互に（★の測定は20個以上が必要）。
    ask=True は曲を読み込んだ時の「曲を解析しますか？」を出して撮る（06-1b）"""
    mts.use_lang(ed)
    t = mts.Tut(ed)
    mts.stub_pickers(ed)
    ed.wait(0.5)
    if ask:
        ana_h.ask_on(ed)   # テストの環境は既定で聞かない＝キーを消す（初めて使う人と同じ）
    t.click_el("#mFileBtn"); ed.wait(0.5)
    t.click_el("#mFileMenu button[data-act=loadsong]"); ed.wait(2.5)
    if ask:
        ask_dialog(ed, t)
    beat = 0.0
    for i, b in enumerate(range(2, 16)):
        while beat < b - 1e-6:
            ed.move(960, 800); ed.key("ArrowRight"); beat += 0.5   # 既定スナップ1/2拍
        d = 1 if i % 2 == 0 else 0
        mts.place_note(t, 1, 0, 0, d)
        mts.place_note(t, 2, 0, 1, d)
    n = ed.js("window._dbgApp.state().counts.notes")
    if n < 20:
        raise SystemExit(f"ノーツ配置に失敗しました（{n}個）\n{ed.errors()}")
    return t


def main():
    mts.OUT.mkdir(parents=True, exist_ok=True)
    # 3章の単独編集・リンク、4章の難易度間コピーの確認、6章の曲を解析は、別の起動で撮る
    # （クリップの色・名前・マーカーの番号の続きなど、他の画像の状態を変えないため）
    if not mts.ONLY or {"03", "04", "06"} & mts.ONLY:
        with Editor(width=W, height=H) as ed:
            t = setup(ed, ask=True)
            ed.move(960, 800); ed.key("ArrowRight"); ed.key("ArrowRight"); ed.wait(1.0)   # 本編と同じ拍16へ
            edit_only(ed, t)
            song_analysis(ed, t)
            clip_link(ed, t)   # リンクは元へ戻さないので最後
            print(ed.errors())
    if mts.ONLY and not mts.ONLY - {"06"}:
        return
    with Editor(width=W, height=H) as ed:
        t = setup(ed)

        # ---- 2章: 同じ向きの警告（15拍目の赤は振り上げ → 16拍目にも振り上げを置く）・直前ノーツ・JD/RT ----
        ed.move(960, 800); ed.key("ArrowRight"); ed.key("ArrowRight"); ed.wait(1.0)
        mts.place_note(t, 1, 0, 0, 0)
        ed.move(300, 800); ed.wait(0.8)
        t.shot("02-1-aux-swing", clip=VIEW3D)
        t.shot("02-2-header", marks="[{t:'#jdInfo',n:1,at:'l'},{t:'#swingLamp',n:2,at:'b'}]",
               clip=box(ed, ["#jdInfo", "#swingLamp", "#diffBar"], pad=30))
        ed.move(960, 800); ed.key("z", ctrl=True); ed.wait(0.5)   # 警告用のノーツを取り消す
        t.shot("02-3-spectrogram", marks="[{t:'#overview',n:1,at:'l',pad:-2},{t:'#specPane',n:2,at:'l',pad:-2}]",
               clip=box(ed, ["#overview", "#specPane"], pad=40))

        # ---- 1章: スナップのパイメニュー（, を押している間だけ出る） ----
        ed.move(960, 760); ed.wait(0.3)
        key_hold(ed, ",", "Comma", 188); ed.wait(0.6)
        t.shot("01-1-snap-pie", clip=box(ed, ["#pie"], pad=110, deep=True))
        key_release(ed, ",", "Comma", 188); ed.wait(0.3)

        # ---- 3章: NLE（マーカー・テンポパート） ----
        for b in (4, 8):   # マーカーはマウスの位置に置かれる
            g = nle(ed, b); ed.move(g["x"], g["notes"][0] + 5); ed.wait(0.3); ed.key("e", ctrl=True); ed.wait(0.3)
        g = nle(ed, 12); ed.click(g["x"], g["tempo"] + 7, button="right"); ed.wait(0.4)
        menu_click(ed, mts.L("テンポパートを追加"))
        g = nle(ed)
        x4, x12 = nle(ed, 4)["x"], nle(ed, 12)["x"]
        ed.move(g["left"] + g["w"] - 40, g["notes"][0] + 5); ed.wait(0.5)
        light_top = g["lights"][0] if g["lights"] else g["lanes"]
        t.shot("03-1-nle-parts", marks=json.dumps([
            {"t": [g["left"] + g["gut"], g["ruler"], g["w"] - g["gut"], g["tempo"] - g["ruler"]], "n": 1, "at": "l", "pad": 0},
            {"t": [x12 - 6, g["tempo"], 52, g["marker"] - g["tempo"]], "n": 2, "at": "r", "pad": 1},   # テンポパートの◆
            {"t": [x4 - 6, g["marker"], 70, g["lanes"] - g["marker"]], "n": 3, "at": "r", "pad": 1},   # マーカー
            # ④⑤の番号は右上（溝の左に置くと、レーンの名前・L/S/M・単独編集の帯に重なる）
            {"t": [g["left"] + g["gut"], g["lanes"], g["w"] - g["gut"], light_top - g["lanes"]], "n": 4, "at": "tr", "pad": -2},
            {"t": [g["left"] + g["gut"], light_top, g["w"] - g["gut"], g["top"] + g["h"] - light_top], "n": 5, "at": "tr", "pad": -2},
            {"t": "#overview", "n": 6, "at": "l", "pad": -2}]),
            clip=box(ed, ["#ndcv", "#overview"], pad=40))
        # クリップの右クリックメニュー（ノーツのクリップがあるレーンを探す）
        found = False
        for y in nle(ed, 3)["notes"]:
            g = nle(ed, 3); ed.click(g["x"], y + g["laneH"] / 2, button="right"); ed.wait(0.4)
            if ed.js(f"document.getElementById('ctxmenu').textContent.includes({mts.L('左右反転')!r})"):
                found = True; break
            hide_menu(ed)
        if not found:
            raise SystemExit("ノーツのクリップが見つかりません")
        t.shot("03-2-clip-menu", marks="[{t:'#ctxmenu',pad:3}]", clip=box(ed, ["#ctxmenu", [g["x"] - 160, g["lanes"], 320, 60]], pad=24))
        hide_menu(ed)

        # ---- 1章: マーカーの右クリックメニュー ----
        g = nle(ed, 4); ed.click(g["x"], g["marker"] + 8, button="right"); ed.wait(0.4)
        menu_mark(ed, mts.L("試聴の開始に転送"), "tutMkPrev")
        t.shot("01-2-marker-menu", marks="[{t:'#tutMkPrev',n:1,at:'r'}]",
               clip=box(ed, ["#ctxmenu", [g["x"] - 200, g["ruler"], 400, 80]], pad=24))
        hide_menu(ed)

        # ---- 5章: テンポパートの右クリックメニュー ----
        g = nle(ed, 12); ed.click(g["x"] + 1, g["tempo"] + 7, button="right"); ed.wait(0.4)
        if not ed.js(f"document.getElementById('ctxmenu').textContent.includes({mts.L('自動判定')!r})"):
            raise SystemExit("テンポパートのメニューが出ません")
        t.shot("05-1-tempo-menu", marks="[{t:'#ctxmenu',pad:3},{t:'#tempoDetectAllBtn',n:1,at:'b'}]",
               clip=box(ed, ["#ctxmenu", [g["x"] - 200, g["ruler"], 400, 60], "#tempoDetectAllBtn"], pad=24))
        hide_menu(ed)

        # ---- 5章: 曲の音量補正（Music の段の左溝）。自動調整を押し、結果のメッセージと一緒に撮る ----
        t.click_el("#gainAutoBtn")
        wait_until(ed, "(e=>e.style.display==='block'&&e.textContent.startsWith('✅'))(document.getElementById('errToast'))",
                   lambda: "自動調整の結果が出ません: " + str(ed.js("document.getElementById('errToast').textContent")))
        if not ed.js("window._dbgApp.songGain().db>0"):
            raise SystemExit("自動調整で音量補正が上がりません: " + str(ed.js("document.getElementById('errToast').textContent")))
        # 結果のメッセージは画面の下に4秒だけ出る。写しを作り、Music の段のすぐ下（スペクトログラムの上）に2行で置く
        ov, mg = t.rect("#overview"), t.rect("#musicGain")
        ed.js(f"""(()=>{{ const c=document.getElementById('errToast').cloneNode(true); c.id='tutToast';
          Object.assign(c.style,{{left:'{round(mg["x"] + mg["w"] + 8)}px',top:'{round(ov["y"] + ov["h"] + 14)}px',bottom:'auto',
            transform:'none',maxWidth:'620px'}});
          document.body.appendChild(c); return 1; }})()""")
        ed.move(960, 800); ed.wait(0.4)   # 自動調整のボタンからマウスを離す（ホバーの色を写さない）
        tr = t_rect(ed, "#tutToast")
        t.shot("05-2-song-gain", marks="[{t:'#gainAutoBtn',n:1,at:'r'},{t:'#gainField',n:2,at:'b'},{t:'#tutToast',n:3,at:'r'}]",
               clip=box(ed, ["#musicGain", "#tutToast", [tr["x"] + tr["w"], tr["y"], 50, tr["h"]]], pad=24))
        ed.js("document.getElementById('tutToast').remove();true")
        ed.move(960, 800); ed.key("z", ctrl=True); ed.wait(0.5)   # 音量補正を取り消す（後の画像を前と同じ状態で撮る）
        if ed.js("window._dbgApp.songGain().db") != 0:
            raise SystemExit("音量補正を取り消せません")

        # ---- 4章: 難易度のメニュー（選択中のボタンをもう一度クリック → 受信のサブメニュー） ----
        t.click_el("#diffBar .dfSeg.on"); ed.wait(0.5)
        if not menu_mark(ed, mts.L("ノーツを受信"), "tutRecv"):
            raise SystemExit("難易度のメニューが出ません")
        r = t.rect("#tutRecv"); ed.move(r["x"] + 20, r["y"] + r["h"] / 2); ed.wait(0.6)
        t.shot("04-1-diff-menu", marks="[{t:'#diffBar .dfSeg.on',n:1,at:'l'},{t:'#tutRecv',n:2,at:'l'}]",
               clip=box(ed, ["#ctxmenu", "#diffBar"] + [f"#ctxmenu ~ .ctxsub"], pad=40))
        ed.key("Escape"); hide_menu(ed)

        # ---- 7章: ライトを置いてパイメニュー（W=動き / C=色） ----
        ed.move(960, 800); ed.key("Tab"); ed.wait(1.5)
        for b, lanes in ((1, (2, 4, 6)), (2, (4, 6)), (3, (2,))):
            mts.seek_to(ed, b)
            for li in lanes:
                q = ed.js(f"window._dbgApp.lightLaneScreen({li},{b})")
                ed.move(q["x"], q["y"]); ed.wait(0.2); ed.click(q["x"], q["y"]); ed.wait(0.2)
        ed.move(960, 760); ed.wait(0.3)
        key_hold(ed, "w", "KeyW", 87); ed.wait(0.6)
        t.shot("07-1-light-pie", clip=box(ed, ["#pie"], pad=110, deep=True))
        key_release(ed, "w", "KeyW", 87); ed.wait(0.3)
        ed.move(960, 760); ed.wait(0.3)
        key_hold(ed, "c", "KeyC", 67); ed.wait(0.6)
        t.shot("07-2-color-pie", clip=box(ed, ["#pie"], pad=110, deep=True))
        key_release(ed, "c", "KeyC", 67); ed.wait(0.3)
        # 自動ライティング: ツールバーのボタン → 確認 → 新しいレーンのクリップ。
        # 9章は「ライトが足りない」状態を撮るので、撮り終えたら取り消す
        ed.move(960, 760); ed.wait(0.3)
        t.shot("07-3-auto-light-button", marks="[{t:'#tbAutoLight',n:1,at:'b'}]", clip=box(ed, ["#maintb"], pad=36))
        t.click_el("#tbAutoLight"); ed.wait(0.6)
        if not ed.js("!!document.getElementById('dirtyDlg')"):
            raise SystemExit("自動ライティングの確認が出ません")
        t.shot("07-4-auto-light-dialog", clip=box(ed, ["#dirtyDlg"], pad=30))
        t.click_el("#dirtyDlg button.pri"); ed.wait(1.0)
        g = nle(ed)
        t.shot("07-5-auto-light-lane", marks=json.dumps([
            {"t": [g["left"] + g["gut"], g["lights"][0], g["w"] - g["gut"], g["laneHL"]], "n": 1, "at": "b", "pad": -2}]),   # 番号は下（左は L/S/M に重なる）
            clip=box(ed, ["#ndcv"], pad=40))
        ed.move(960, 800); ed.key("z", ctrl=True); ed.wait(0.8)
        if ed.js("window._dbgApp.lights().clips.some(c=>c.n>20)"):
            raise SystemExit("自動ライトを取り消せません")
        ed.move(960, 800); ed.key("Tab"); ed.wait(1.0)   # NOTESへ戻す

        # ---- 8章・11章: INFO（曲情報を入れ、書き出しノードをもう1つ作る） ----
        ed.move(1200, 300); ed.wait(0.3); ed.key("Tab"); ed.wait(1.5)
        for f, text in (("name", "My First Map"), ("artist", "NLM Tutorial"), ("author", "YourName")):
            t.click_el(f"#infoWorld input[data-f={f}]"); ed.wait(0.2); t.type(text); ed.wait(0.2)
        t.click_el("#infoWorld input[data-d=Hard]"); ed.wait(0.3)
        ir = t.rect("#inspcol")
        cx, cy = ir["x"] + ir["w"] / 2, ir["y"] + ir["h"] / 2
        nr = t.rect("#nodecol")
        for _ in range(6):   # 書き出しノードの右隣に、もう1つ置ける空きができるまで少しずつ縮小する
            o = t.rect("#infoWorld .iGrp[data-out]")
            if o["x"] + o["w"] * 2 + 60 < nr["x"] + nr["w"]:
                break
            ed.wheel(cx, cy, 120); ed.wait(0.3)
        ed.click(o["x"] + o["w"] + 30, o["y"] + 10, button="right"); ed.wait(0.4)
        menu_click(ed, mts.L("書き出しノード"))
        ed.js("""(()=>{document.querySelectorAll('#infoWorld .iGrp[data-t]').forEach(e=>{ if(!document.getElementById('tutN_'+e.dataset.t)) e.id='tutN_'+e.dataset.t; });
          const outs=[...document.querySelectorAll('#infoWorld .iGrp[data-out]')]; outs.forEach((e,i)=>e.id='tutOut'+i); return outs.length})()""")
        ed.move(ir["x"] + 10, ir["y"] + ir["h"] - 10); ed.wait(0.4)
        t.shot("08-1-info-nodes", marks="""[
          {t:'#tutN_meta',n:1,at:'tr'},{t:'#tutN_cover',n:2,at:'tr'},{t:'#tutN_set',n:3,at:'tr'},{t:'#tutN_prev',n:4,at:'tr'},
          {t:'#tutOut0',n:5,at:'tr'},{t:'#tutOut1',n:5,at:'tl'}]""", clip=box(ed, ["#nodecol"], pad=0))
        # 11章: 新しい書き出しノード（アクティブ）は出力フォルダ未設定＝必須項目に ✕。拡大して枠の中だけを撮る
        c = t.rect("#tutOut1 .oChk")
        for _ in range(2):
            ed.wheel(c["x"] + c["w"] / 2, c["y"] + c["h"] / 2, -120); ed.wait(0.3)
        x, y, w, h = box(ed, ["#tutOut1"], pad=40)
        x1, y1 = min(x + w, nr["x"] + nr["w"]), min(y + h, nr["y"] + nr["h"])
        x, y = max(x, nr["x"]), max(y, nr["y"])
        t.shot("11-1-export-blocked", marks="[{t:'#tutOut1 .oChk',n:1,at:'l'}]", clip=(round(x), round(y), round(x1 - x), round(y1 - y)))
        ed.move(1200, 300); ed.key("Tab"); ed.wait(1.0)   # NLEへ戻す

        # ---- 10章・1章: 環境設定 ----
        t.click_el("#mbSettings"); ed.wait(0.6)
        # 「曲の解析」の2つのチェックは、テストの環境（聞かない・案内しない）でなく初めて使う人と同じ（オン）に見せる（表示だけ・撮った後に戻す）
        # アプリケーション設定の欄は箱の中でスクロールする＝「ノーツのレーンの本数」が欄の上端に来るまでスクロールして、新しい項目（③④）を見せる
        ed.js("""(()=>{ for(const id of ['anaAskOn','anaGuideOn']) document.getElementById(id).checked=true;
          const lanes=document.getElementById('laneRatio').closest('.slRow'); lanes.id='tutSetLanes';
          document.getElementById('anaAskOn').closest('.row').id='tutSetAna';
          const p=document.querySelector('#settingsBox .setPanel.on');
          p.scrollTop+=lanes.getBoundingClientRect().top-p.getBoundingClientRect().top-6; return 1; })()""")
        ed.wait(0.3)
        t.shot("10-1-settings", marks="""[{t:'#settingsBox .setTabs',n:1,at:'l'},{t:'#settingsReset',n:2,at:'l'},
          {t:'#tutSetLanes',n:3,at:'l'},{t:'#tutSetAna',n:4,at:'l'}]""",
               clip=box(ed, ["#settingsBox"], pad=40))
        ed.js("""(()=>{ for(const id of ['anaAskOn','anaGuideOn']) document.getElementById(id).checked=false;
          document.querySelector('#settingsBox .setPanel.on').scrollTop=0; return 1; })()""")
        t.click_el("#settingsBox .setTab[data-tab=keys]"); ed.wait(0.6)
        t.shot("01-3-shortcut-edit", marks="[{t:'#keyEditBody button',n:1,at:'r'}]",
               clip=box(ed, ["#settingsBox"], pad=40))
        t.click_el("#settingsBox .setTab[data-tab=app]"); ed.wait(0.3)
        t.click_el("#settingsClose"); ed.wait(0.4)

        # ---- 9章: 譜面チェック・BL評価リスト・難易度を測る ----
        # プラグインは BL評価リストの★/Tech（09-3）でも使うので、譜面チェックを開く前に取り込んでおく
        has_plugin = (PLUGIN_DIR / "current.json").exists()
        if has_plugin:
            shutil.copytree(PLUGIN_DIR, Path(ed.data_dir) / "plugins" / "rating")
        else:
            print("プラグインが見つからないので、未導入の画面を撮ります:", PLUGIN_DIR)
        t.click_el("#mFileBtn"); ed.wait(0.5)
        t.click_el("#mFileMenu button[data-act=mapcheck]"); ed.wait(3.0)
        move_panel(ed, "#mcPanel")
        beat_chip = ed.js("(()=>{const b=document.querySelector('#mcPanel .mcBeat'); if(b) b.id='tutBeat'; return !!b})()")
        marks = "{t:'#mcPanel .mcTabs',n:1,at:'l'},{t:'#mcPanel .mcSum',n:2,at:'l'},{t:'#mcPanel .mcRerun',n:3,at:'b'}"
        if ed.js("!!document.querySelector('#mcPanel .mcFix')"):   # ライトが足りない項目の「💡 自動ライティング…」
            marks += ",{t:'#mcPanel .mcFix',n:4,at:'l'}"
        if beat_chip:
            marks += ",{t:'#tutBeat',n:5,at:'l'}"
        t.shot("09-1-mapcheck", marks="[" + marks + "]", clip=box(ed, ["#mcPanel"], pad=44))
        t.click_el("#mcPanel .mcTab[data-tab=bl]"); ed.wait(1.0)
        t.shot("09-2-bl-criteria", marks="""[
          {t:'#mcPanel .blBanner',n:1,at:'l'},{t:'#mcPanel .blOnly',n:2,at:'l'},
          {t:'#mcPanel .blKind',n:3,at:'r'}]""", clip=box(ed, ["#mcPanel"], pad=44))
        if has_plugin:   # BL評価リストを開くと自動で測る（別プロセス）。★の欄に入るまで待つ
            wait_until(ed, "(()=>{const i=document.querySelector('#mcPanel .blStars input[data-star]');return !!i&&i.value!==''})()",
                       "BL評価リストの★/Techが自動で入りません", timeout=60)
        ed.js("(()=>{const s=document.querySelector('#mcPanel .blStarsBox'); if(s) s.scrollIntoView({block:'center'}); return 1})()")
        ed.wait(0.5)
        t.shot("09-3-bl-stars", marks="[{t:'#mcPanel .blRtCtl',n:1,at:'l'},{t:'#mcPanel .blStars',n:2,at:'l'}]",
               clip=box(ed, ["#mcPanel"], pad=44))
        t.click_el("#mcPanel .mcTab[data-tab=mc]"); ed.wait(0.3)   # 次回開いた時のタブを元へ戻す
        t.click_el("#mcPanel .mcClose"); ed.wait(0.5)

        # ---- 9章: カバー画像の補正（少しだけ正方形でない画像を選ぶ → チェックの「🖼 カバー画像を補正…」→ 確認 → INFOのカード） ----
        ed.js("""(()=>{ const prev=window.showOpenFilePicker;
          window.showOpenFilePicker=async(opt)=>{
            if(!JSON.stringify((opt&&opt.types)||[]).includes('image/')) return prev(opt);
            const W=512,H=496, c=document.createElement('canvas'); c.width=W; c.height=H; const g=c.getContext('2d');
            const gr=g.createLinearGradient(0,0,W,H); gr.addColorStop(0,'#ff3355'); gr.addColorStop(1,'#2d7dff');
            g.fillStyle=gr; g.fillRect(0,0,W,H); g.fillStyle='#fff'; g.font='bold 92px sans-serif'; g.textAlign='center';
            g.fillText('NLM',W/2,232); g.font='bold 48px sans-serif'; g.fillText('Tutorial',W/2,312);
            const blob=await new Promise(r=>c.toBlob(r,'image/png'));
            const f=new File([blob],'my-cover.png',{type:'image/png'});
            return [{kind:'file',name:'my-cover.png',getFile:async()=>f}]; };
          return 1; })()""")
        ed.move(1200, 300); ed.key("Tab"); ed.wait(1.5)   # INFOへ（8章で拡大したままなので、.で全体が見える位置へ戻す）
        ed.move(1200, 300); ed.key("."); ed.wait(0.8)
        t.click_el("#tutOut0 h3"); ed.wait(0.5)   # 8章で足した書き出しノード（何もつながっていない）から、元の書き出しノードへ
        t.click_el("#tutN_cover .nPick")
        COVER = "(async()=>JSON.stringify((await window._dbgApp.mapCheckInput()).cover))()"
        wait_until(ed, COVER + ".then(c=>c!=='null')", "選んだカバー画像が書き出しに入りません")   # 画像の作成（toBlob）はヘッドレスだと遅い
        ed.move(1200, 300); ed.key("Tab"); ed.wait(1.0)   # NLEへ戻す
        t.click_el("#mFileBtn"); ed.wait(0.5)
        t.click_el("#mFileMenu button[data-act=mapcheck]")
        wait_until(ed, "!!document.querySelector('#mcPanel .mcFix[data-fix=cover]')",
                   lambda: "カバー画像を補正のボタンが出ません: " + str(ed.js(COVER)))
        t.click_el("#mcPanel .mcFix[data-fix=cover]")
        wait_until(ed, "!!document.querySelector('#dirtyDlg canvas')", "カバー画像の補正の確認が出ません")
        ed.js("(()=>{const d=document.getElementById('dirtyDlg'); d.querySelector('.cfModes').id='tutCfModes'; d.querySelector('canvas').parentElement.parentElement.id='tutCfPrev'; return 1})()")
        t.shot("09-5-cover-fit-dialog", marks="[{t:'#tutCfModes',n:1,at:'l'},{t:'#tutCfPrev',n:2,at:'l'}]",
               clip=box(ed, ["#dirtyDlg"], pad=44))
        t.click_el("#dirtyDlg button.pri")
        wait_until(ed, "!document.querySelector('#mcPanel .mcFix[data-fix=cover]')", "補正した後もカバー画像の項目が残っています")
        t.click_el("#mcPanel .mcClose"); ed.wait(0.5)
        ed.move(1200, 300); ed.key("Tab"); ed.wait(1.5)   # INFOのカバー画像ノード
        ed.move(1200, 300); ed.key("."); ed.wait(0.8)
        nr = t.rect("#nodecol")
        for _ in range(8):   # カバー画像ノード全体（下端の補正の表示まで）が INFO 画面の高さに入るまで縮小する
            c = t.rect("#tutN_cover")
            if c["h"] + 40 < nr["h"]:   # 下の移動で上端を INFO 画面の上から 30px に置く＝下に 10px 残る
                break
            ed.wheel(nr["x"] + nr["w"] / 2, nr["y"] + nr["h"] / 2, 120); ed.wait(0.3)
        for _ in range(4):   # 入る範囲でできるだけ大きく（全体を見せる「.」の位置は小さすぎて補正の文字が読みにくい）
            ed.wheel(nr["x"] + nr["w"] / 2, nr["y"] + nr["h"] / 2, -120); ed.wait(0.3)
            if t.rect("#tutN_cover")["h"] + 40 >= nr["h"]:
                ed.wheel(nr["x"] + nr["w"] / 2, nr["y"] + nr["h"] / 2, 120); ed.wait(0.3)
                break
        # 左下の曲の情報（basic.wav・BPM など）に重ならないよう、ノードを曲の情報の右・画面の上寄りへ動かす（中ボタンのドラッグ）
        c = t.rect("#tutN_cover")
        sx, sy = nr["x"] + nr["w"] / 2, nr["y"] + nr["h"] / 2
        ed.drag(sx, sy, sx + (nr["x"] + 360 - c["x"]), sy + (nr["y"] + 30 - c["y"]), button="middle"); ed.wait(0.5)
        x, y, w, h = box(ed, ["#tutN_cover"], pad=50)
        x1, y1 = min(x + w, nr["x"] + nr["w"]), min(y + h, nr["y"] + nr["h"])
        x, y = max(x, nr["x"]), max(y, nr["y"])
        t.shot("09-6-cover-fit-card", marks="[{t:'#tutN_cover .nCovFit span',n:1,at:'l'},{t:'#tutN_cover .nCovFitOff',n:2,at:'r'}]",
               clip=(round(x), round(y), round(x1 - x), round(y1 - y)))
        t.click_el("#tutOut1 h3"); ed.wait(0.5)   # アクティブな書き出しノードを元に戻す（難易度を測るの画像を前と同じ状態で撮る）
        ed.move(1200, 300); ed.key("Tab"); ed.wait(1.0)   # NLEへ戻す

        t.click_el("#mFileBtn"); ed.wait(0.5)
        t.click_el("#mFileMenu button[data-act=rating]")
        move_panel(ed, "#rtPanel")
        for _ in range(120):   # 測定（別プロセス）の完了を待つ
            ed.wait(0.5)
            if ed.js("!!document.querySelector('#rtPanel .rtTable, #rtPanel .rtIntro, #rtPanel .rtErr')"):
                break
        ed.wait(0.5)
        has_table = ed.js("!!document.querySelector('#rtPanel .rtTable')")
        marks = ("[{t:'#rtPanel .rtTable',n:1,at:'l'},{t:'#rtPanel .rtRun',n:2,at:'l'},{t:'#rtPanel .rtPlug',n:3,at:'l'}]"
                 if has_table else "[{t:'#rtPanel .rtInstall',n:1,at:'b'}]")
        t.shot("09-4-rating", marks=marks, clip=box(ed, ["#rtPanel"], pad=44))
        print("測定結果あり" if has_table else "未導入の画面")
        t.click_el("#rtPanel .rtClose"); ed.wait(0.4)

        # ---- 3章・10章: MEDIA ライブラリ（MEDIA の幅を変えるので最後に撮る） ----
        media_library(ed, t)
        print(ed.errors())


if __name__ == "__main__":
    main()

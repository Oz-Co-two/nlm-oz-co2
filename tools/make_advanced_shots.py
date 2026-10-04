"""上級編チュートリアル(docs/tutorial-advanced.md)用のスクリーンショットを撮り直すスクリプト。

tools/fixtures/basic.wav（120BPMのクリック音）を読み込み、実際にクリック・キー入力で赤青のノーツ・ライト・
マーカー・テンポパートを置きながら、各章の画面を docs/images/tutorial-advanced/ へ保存する。
ファイル名は「<章>-<連番>-<内容>.png」。撮影の部品（赤枠と番号・ノーツ配置・ダイアログの差し替え）は
make_tutorial_shots.py のものを使う。NLE の帯の位置は _dbgApp.nleScreen で取る（キャンバスに直接描くため）。

「難易度を測る」(8章)は追加プラグイン nlm-rating が要る。撮影用の一時データフォルダへコピーして使うので、
取り込み済みのプラグインフォルダ（plugins/rating。中に current.json と版のフォルダがある）を
環境変数 NLM_RATING_DIR で指定する。省略時は配布フォルダ NLM-app/plugins/rating を探し、
無ければ「プラグイン未導入」の画面を撮る。

使い方: .venv-build/Scripts/python.exe tools/make_advanced_shots.py [--en] [章番号...]
        例: make_advanced_shots.py 03 08 で3章と8章の画像だけ保存（操作は最初から全部行う）
        --en: 英語表示で撮って docs/images/tutorial-advanced-en/ へ保存する（英語版 docs/tutorial-advanced.en.md 用）
"""
import json
import os
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import make_tutorial_shots as mts  # noqa: E402
from cdp import Editor  # noqa: E402

mts.OUT = HERE.parent / "docs" / "images" / ("tutorial-advanced-en" if mts.LANG == "en" else "tutorial-advanced")
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


def main():
    mts.OUT.mkdir(parents=True, exist_ok=True)
    with Editor(width=W, height=H) as ed:
        mts.use_lang(ed)
        t = mts.Tut(ed)
        mts.stub_pickers(ed)
        ed.wait(0.5)
        t.click_el("#mFileBtn"); ed.wait(0.5)
        t.click_el("#mFileMenu button[data-act=loadsong]"); ed.wait(2.5)

        # ノーツを置く: 2〜15拍目に赤青1個ずつ、振り下ろし/振り上げを交互に（★の測定は20個以上が必要）
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
            {"t": [g["left"] + g["gut"], g["lanes"], g["w"] - g["gut"], light_top - g["lanes"]], "n": 4, "at": "l", "pad": -2},
            {"t": [g["left"] + g["gut"], light_top, g["w"] - g["gut"], g["top"] + g["h"] - light_top], "n": 5, "at": "l", "pad": -2},
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

        # ---- 4章: 難易度のメニュー（選択中のボタンをもう一度クリック → 受信のサブメニュー） ----
        t.click_el("#diffBar .dfSeg.on"); ed.wait(0.5)
        if not menu_mark(ed, mts.L("ノーツを受信"), "tutRecv"):
            raise SystemExit("難易度のメニューが出ません")
        r = t.rect("#tutRecv"); ed.move(r["x"] + 20, r["y"] + r["h"] / 2); ed.wait(0.6)
        t.shot("04-1-diff-menu", marks="[{t:'#diffBar .dfSeg.on',n:1,at:'l'},{t:'#tutRecv',n:2,at:'l'}]",
               clip=box(ed, ["#ctxmenu", "#diffBar"] + [f"#ctxmenu ~ .ctxsub"], pad=40))
        ed.key("Escape"); hide_menu(ed)

        # ---- 6章: ライトを置いてパイメニュー（W=動き / C=色） ----
        ed.move(960, 800); ed.key("Tab"); ed.wait(1.5)
        for b, lanes in ((1, (2, 4, 6)), (2, (4, 6)), (3, (2,))):
            mts.seek_to(ed, b)
            for li in lanes:
                q = ed.js(f"window._dbgApp.lightLaneScreen({li},{b})")
                ed.move(q["x"], q["y"]); ed.wait(0.2); ed.click(q["x"], q["y"]); ed.wait(0.2)
        ed.move(960, 760); ed.wait(0.3)
        key_hold(ed, "w", "KeyW", 87); ed.wait(0.6)
        t.shot("06-1-light-pie", clip=box(ed, ["#pie"], pad=110, deep=True))
        key_release(ed, "w", "KeyW", 87); ed.wait(0.3)
        ed.move(960, 760); ed.wait(0.3)
        key_hold(ed, "c", "KeyC", 67); ed.wait(0.6)
        t.shot("06-2-color-pie", clip=box(ed, ["#pie"], pad=110, deep=True))
        key_release(ed, "c", "KeyC", 67); ed.wait(0.3)
        # 自動ライティング: ツールバーのボタン → 確認 → 新しいレーンのクリップ。
        # 8章は「ライトが足りない」状態を撮るので、撮り終えたら取り消す
        ed.move(960, 760); ed.wait(0.3)
        t.shot("06-3-auto-light-button", marks="[{t:'#tbAutoLight',n:1,at:'b'}]", clip=box(ed, ["#maintb"], pad=36))
        t.click_el("#tbAutoLight"); ed.wait(0.6)
        if not ed.js("!!document.getElementById('dirtyDlg')"):
            raise SystemExit("自動ライティングの確認が出ません")
        t.shot("06-4-auto-light-dialog", clip=box(ed, ["#dirtyDlg"], pad=30))
        t.click_el("#dirtyDlg button.pri"); ed.wait(1.0)
        g = nle(ed)
        t.shot("06-5-auto-light-lane", marks=json.dumps([
            {"t": [g["left"] + g["gut"], g["lights"][0], g["w"] - g["gut"], g["laneH"]], "n": 1, "at": "l", "pad": -2}]),
            clip=box(ed, ["#ndcv"], pad=40))
        ed.move(960, 800); ed.key("z", ctrl=True); ed.wait(0.8)
        if ed.js("window._dbgApp.lights().clips.some(c=>c.n>20)"):
            raise SystemExit("自動ライトを取り消せません")
        ed.move(960, 800); ed.key("Tab"); ed.wait(1.0)   # NOTESへ戻す

        # ---- 7章・10章: INFO（曲情報を入れ、書き出しノードをもう1つ作る） ----
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
        t.shot("07-1-info-nodes", marks="""[
          {t:'#tutN_meta',n:1,at:'tr'},{t:'#tutN_cover',n:2,at:'tr'},{t:'#tutN_set',n:3,at:'tr'},{t:'#tutN_prev',n:4,at:'tr'},
          {t:'#tutOut0',n:5,at:'tr'},{t:'#tutOut1',n:5,at:'tl'}]""", clip=box(ed, ["#nodecol"], pad=0))
        # 10章: 新しい書き出しノード（アクティブ）は出力フォルダ未設定＝必須項目に ✕。拡大して枠の中だけを撮る
        c = t.rect("#tutOut1 .oChk")
        for _ in range(2):
            ed.wheel(c["x"] + c["w"] / 2, c["y"] + c["h"] / 2, -120); ed.wait(0.3)
        x, y, w, h = box(ed, ["#tutOut1"], pad=40)
        x1, y1 = min(x + w, nr["x"] + nr["w"]), min(y + h, nr["y"] + nr["h"])
        x, y = max(x, nr["x"]), max(y, nr["y"])
        t.shot("10-1-export-blocked", marks="[{t:'#tutOut1 .oChk',n:1,at:'l'}]", clip=(round(x), round(y), round(x1 - x), round(y1 - y)))
        ed.move(1200, 300); ed.key("Tab"); ed.wait(1.0)   # NLEへ戻す

        # ---- 9章・1章: 環境設定 ----
        t.click_el("#mbSettings"); ed.wait(0.6)
        t.shot("09-1-settings", marks="[{t:'#settingsBox .setTabs',n:1,at:'l'},{t:'#settingsReset',n:2,at:'l'}]",
               clip=box(ed, ["#settingsBox"], pad=40))
        t.click_el("#settingsBox .setTab[data-tab=keys]"); ed.wait(0.6)
        t.shot("01-3-shortcut-edit", marks="[{t:'#keyEditBody button',n:1,at:'r'}]",
               clip=box(ed, ["#settingsBox"], pad=40))
        t.click_el("#settingsBox .setTab[data-tab=app]"); ed.wait(0.3)
        t.click_el("#settingsClose"); ed.wait(0.4)

        # ---- 8章: 譜面チェック・BL評価リスト・難易度を測る ----
        t.click_el("#mFileBtn"); ed.wait(0.5)
        t.click_el("#mFileMenu button[data-act=mapcheck]"); ed.wait(3.0)
        move_panel(ed, "#mcPanel")
        beat_chip = ed.js("(()=>{const b=document.querySelector('#mcPanel .mcBeat'); if(b) b.id='tutBeat'; return !!b})()")
        marks = "{t:'#mcPanel .mcTabs',n:1,at:'l'},{t:'#mcPanel .mcSum',n:2,at:'l'},{t:'#mcPanel .mcRerun',n:3,at:'b'}"
        if ed.js("!!document.querySelector('#mcPanel .mcFix')"):   # ライトが足りない項目の「💡 自動ライティング…」
            marks += ",{t:'#mcPanel .mcFix',n:4,at:'l'}"
        if beat_chip:
            marks += ",{t:'#tutBeat',n:5,at:'l'}"
        t.shot("08-1-mapcheck", marks="[" + marks + "]", clip=box(ed, ["#mcPanel"], pad=44))
        t.click_el("#mcPanel .mcTab[data-tab=bl]"); ed.wait(1.0)
        t.shot("08-2-bl-criteria", marks="""[
          {t:'#mcPanel .blBanner',n:1,at:'l'},{t:'#mcPanel .blOnly',n:2,at:'l'},
          {t:'#mcPanel .blKind',n:3,at:'r'}]""", clip=box(ed, ["#mcPanel"], pad=44))
        ed.js("(()=>{const s=document.querySelector('#mcPanel .blStars'); if(s) s.scrollIntoView({block:'center'}); return 1})()")
        ed.wait(0.5)
        t.shot("08-3-bl-stars", marks="[{t:'#mcPanel .blStars',n:1,at:'l'}]", clip=box(ed, ["#mcPanel"], pad=44))
        t.click_el("#mcPanel .mcTab[data-tab=mc]"); ed.wait(0.3)   # 次回開いた時のタブを元へ戻す
        t.click_el("#mcPanel .mcClose"); ed.wait(0.5)

        # ---- 8章: カバー画像の補正（少しだけ正方形でない画像を選ぶ → チェックの「🖼 カバー画像を補正…」→ 確認 → INFOのカード） ----
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
        ed.move(1200, 300); ed.key("Tab"); ed.wait(1.5)   # INFOへ（7章で拡大したままなので、.で全体が見える位置へ戻す）
        ed.move(1200, 300); ed.key("."); ed.wait(0.8)
        t.click_el("#tutOut0 h3"); ed.wait(0.5)   # 7章で足した書き出しノード（何もつながっていない）から、元の書き出しノードへ
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
        t.shot("08-5-cover-fit-dialog", marks="[{t:'#tutCfModes',n:1,at:'l'},{t:'#tutCfPrev',n:2,at:'l'}]",
               clip=box(ed, ["#dirtyDlg"], pad=44))
        t.click_el("#dirtyDlg button.pri")
        wait_until(ed, "!document.querySelector('#mcPanel .mcFix[data-fix=cover]')", "補正した後もカバー画像の項目が残っています")
        t.click_el("#mcPanel .mcClose"); ed.wait(0.5)
        ed.move(1200, 300); ed.key("Tab"); ed.wait(1.5)   # INFOのカバー画像ノード
        ed.move(1200, 300); ed.key("."); ed.wait(0.8)
        nr = t.rect("#nodecol")
        for _ in range(8):   # カバー画像ノード全体（下端の補正の表示まで）が INFO 画面の高さに入るまで縮小する
            c = t.rect("#tutN_cover")
            if c["h"] + 70 < nr["h"]:
                break
            ed.wheel(nr["x"] + nr["w"] / 2, nr["y"] + nr["h"] / 2, 120); ed.wait(0.3)
        # 左下の曲の情報（basic.wav・BPM など）に重ならないよう、ノードを曲の情報の右・画面の上寄りへ動かす（中ボタンのドラッグ）
        c = t.rect("#tutN_cover")
        sx, sy = nr["x"] + nr["w"] / 2, nr["y"] + nr["h"] / 2
        ed.drag(sx, sy, sx + (nr["x"] + 360 - c["x"]), sy + (nr["y"] + 30 - c["y"]), button="middle"); ed.wait(0.5)
        x, y, w, h = box(ed, ["#tutN_cover"], pad=50)
        x1, y1 = min(x + w, nr["x"] + nr["w"]), min(y + h, nr["y"] + nr["h"])
        x, y = max(x, nr["x"]), max(y, nr["y"])
        t.shot("08-6-cover-fit-card", marks="[{t:'#tutN_cover .nCovFit span',n:1,at:'l'},{t:'#tutN_cover .nCovFitOff',n:2,at:'r'}]",
               clip=(round(x), round(y), round(x1 - x), round(y1 - y)))
        t.click_el("#tutOut1 h3"); ed.wait(0.5)   # アクティブな書き出しノードを元に戻す（難易度を測るの画像を前と同じ状態で撮る）
        ed.move(1200, 300); ed.key("Tab"); ed.wait(1.0)   # NLEへ戻す

        if (PLUGIN_DIR / "current.json").exists():
            shutil.copytree(PLUGIN_DIR, Path(ed.data_dir) / "plugins" / "rating")
        else:
            print("プラグインが見つからないので、未導入の画面を撮ります:", PLUGIN_DIR)
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
        t.shot("08-4-rating", marks=marks, clip=box(ed, ["#rtPanel"], pad=44))
        print("測定結果あり" if has_table else "未導入の画面", ed.errors())


if __name__ == "__main__":
    main()

"""チュートリアル(docs/tutorial.md)用のスクリーンショットを撮り直すスクリプト。

空の状態から tools/fixtures/basic.wav（120BPMのクリック音）を読み込み、実際にクリック・キー入力で
ノーツ等を置きながら、各段階の画面を docs/images/tutorial/ へ保存する。
画面の赤枠と番号は撮影の直前にページへ一時的に重ねた印（アプリの機能ではない）。

UIが変わったらこれを実行し直せば画像が追従する（座標は要素の位置から計算しているので、多少の配置変更には強い）。
ファイル選択ダイアログは撮れない（ブラウザの showOpenFilePicker をテスト素材を返す関数に差し替えている）。
「曲を解析」(04b〜04d) は、解析の応答を自動テストと同じ偽物（tests/_lib/analysis_helpers.py の ana_mock）にして、見本の結果で撮る
（合成音を本当に解析しても今の設定と同じ結果になり、確認の画面が出ないため）。
曲を取り込んだ時の「曲を解析しますか？」(02b) と解析が終わった時の「次にやること」の案内 (04d) は、撮影の環境
（cdp.Editor.TEST_SETTINGS）では出ない設定なので、撮る直前に localStorage のキー（bsnm_anaAsk / bsnm_anaGuide）を消して出す。

使い方: .venv-build/Scripts/python.exe tools/make_tutorial_shots.py [--en] [撮る番号...]
        番号を省略すると全部撮る（例: make_tutorial_shots.py 05 06 で05と06だけ）
        --en: 英語表示で撮って docs/images/tutorial-en/ へ保存する（英語版チュートリアル docs/tutorial.en.md 用）
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "tests" / "_lib"))   # 曲の解析の偽の応答（analysis_helpers。serve を import しない）
from cdp import Editor  # noqa: E402
import analysis_helpers as ana_h  # noqa: E402

LANG = "en" if "--en" in sys.argv else "ja"
OUT = HERE.parent / "docs" / "images" / ("tutorial-en" if LANG == "en" else "tutorial")
W, H = 1920, 1080
# 右端のレベルメーター目盛りの位置に、ヘッドレスEdgeが時々ページ外の丸いアイコンを重ねて描く
# （DOMに無くページ側から消せない）。メーターは説明に不要なので、その手前で切って撮る
RIGHT = 1838
ONLY = set(a for a in sys.argv[1:] if not a.startswith("--"))

# 画面の文言で要素を探す所の、英語表示での文言（lang/en.json と同じ）
TEXT_EN = {
    "カスタム曲書き出し": "Export custom song",
    "テンポパートを追加": "Add tempo part here",
    "左右反転": "Flip horizontally",
    "試聴の開始に転送": "Set as song preview start",
    "自動判定": "Auto-detect",
    "ノーツを受信": "Receive notes",
    "書き出しノード": "Export node",
    "セクションの頭にマーカーを書き出す": "Export section starts as markers",
}


def L(ja):
    """画面の文言（日本語）を、撮影する言語の文言にする"""
    return TEXT_EN[ja] if LANG == "en" else ja


# 「曲を解析」のテンポの見本（基本編 04b 用）: 今の設定（BPM 120・無音追加 0）と BPM は同じで無音追加だけ違う、知らせの無い結果
TEMPO_BASIC = {"version": 1, "bpm": 120.0, "raw_bpm": 120.0, "lead_ms": 132.6, "alt_lead_ms": 382.6, "low_offbeat": False, "offbeat_ratio": 0.0,
               "steps": [], "drift_pct": 0.4, "drift": [], "alt": None, "block_mad_ms": 6.0, "n_beats": 30, "family": 120.0,
               "slope_sig": False, "slope": 0.0, "resid_mad_ms": 7.0}


def wait_js(ed, js, err, timeout=20):
    """js が真になるまで待つ"""
    for _ in range(int(timeout / 0.25)):
        if ed.js(js):
            ed.wait(0.3); return
        ed.wait(0.25)
    raise SystemExit(err)


def use_lang(ed):
    """英語で撮る時は、環境設定の言語を English にしてページを開き直す（起動時から英語＝作り済みの画面に日本語が残らない）"""
    if LANG != "en":
        return
    ed.js("localStorage.setItem('bsnm_lang','en');true")
    ed.wait(0.8)   # 環境設定のミラー（config/settings.json）へ書き戻されるのを待つ
    ed.reload(clear_storage=False)
    ed.wait(2.0)
    if ed.js("document.getElementById('mFileBtn').textContent.trim()") != "File":
        raise SystemExit("英語表示に切り替わりません")

# 撮影用の印（赤枠＋番号）と、ショートカット表示の非表示
MARK_JS = r"""
window.__tut = {
  style(){ if(document.getElementById('tutStyle')) return;
    const s=document.createElement('style'); s.id='tutStyle';
    s.textContent=`#nodeKeys,#modeKeys,#commonKeys{display:none!important}
      .tutBox{position:fixed;border:3px solid #ff3355;border-radius:6px;box-shadow:0 0 0 2px rgba(0,0,0,.55);pointer-events:none;z-index:99998}
      .tutNum{position:fixed;min-width:30px;height:30px;padding:0 6px;box-sizing:border-box;border-radius:15px;background:#ff3355;color:#fff;
        font:bold 17px/30px sans-serif;text-align:center;box-shadow:0 1px 4px rgba(0,0,0,.6);pointer-events:none;z-index:99999}`;
    document.head.appendChild(s); },
  rectOf(t){ if(Array.isArray(t)) return {x:t[0],y:t[1],w:t[2],h:t[3]};
    const e=typeof t==='string'?document.querySelector(t):t; if(!e) return null;
    const r=e.getBoundingClientRect(); return {x:r.left,y:r.top,w:r.width,h:r.height}; },
  mark(items){ this.clear();
    for(const it of items){ const r=this.rectOf(it.t); if(!r) continue; const p=it.pad??3;
      const b=document.createElement('div'); b.className='tutBox';
      Object.assign(b.style,{left:(r.x-p)+'px',top:(r.y-p)+'px',width:(r.w+2*p)+'px',height:(r.h+2*p)+'px'});
      document.body.appendChild(b);
      if(it.n!=null){ const n=document.createElement('div'); n.className='tutNum'; n.textContent=it.n;
        const pos=it.at||'tl'; let x=r.x-p-12, y=r.y-p-12;
        if(pos==='tr'){ x=r.x+r.w+p-18; } if(pos==='l'){ x=r.x-p-38; y=r.y+r.h/2-15; } if(pos==='r'){ x=r.x+r.w+p+8; y=r.y+r.h/2-15; }
        if(pos==='in'){ x=r.x+6; y=r.y+6; } if(pos==='b'){ x=r.x+r.w/2-15; y=r.y+r.h+p+6; }
        x+=it.dx||0; y+=it.dy||0;   // 番号だけをずらす（下の文字に重なる時）
        Object.assign(n.style,{left:Math.max(2,x)+'px',top:Math.max(2,y)+'px'}); document.body.appendChild(n); } } },
  clear(){ document.querySelectorAll('.tutBox,.tutNum').forEach(e=>e.remove()); },
};
true
"""


class Tut:
    def __init__(self, ed):
        self.ed = ed
        ed.js(MARK_JS)
        ed.js("__tut.style()")

    def shot(self, name, marks=None, clip=None):
        if ONLY and name.split("-")[0] not in ONLY:
            return
        if marks:
            self.ed.js(f"__tut.mark({marks})")
            self.ed.wait(0.2)
        path = OUT / f"{name}.png"
        x, y, w, h = clip or (0, 0, W, H)
        self.ed.shot(path, clip=(x, y, min(w, RIGHT - x), h))
        self.ed.js("__tut.clear()")
        print("撮影:", path.name)

    def rect(self, sel):
        return self.ed.js(f"(()=>{{const r=document.querySelector({sel!r}).getBoundingClientRect();return {{x:r.left,y:r.top,w:r.width,h:r.height}}}})()")

    def center(self, sel):
        r = self.rect(sel)
        return r["x"] + r["w"] / 2, r["y"] + r["h"] / 2

    def click_el(self, sel, **kw):
        x, y = self.center(sel)
        self.ed.click(x, y, **kw)

    def cell(self, x, y):
        return self.ed.js(f"window._dbgApp.cellScreen({x},{y})")

    def type(self, text):
        self.ed.call("Input.insertText", text=text)


def _union(t, a, b):
    ra, rb = t.rect(a), t.rect(b)
    x0, y0 = min(ra["x"], rb["x"]), min(ra["y"], rb["y"])
    x1, y1 = max(ra["x"] + ra["w"], rb["x"] + rb["w"]), max(ra["y"] + ra["h"], rb["y"] + rb["h"])
    return round(x0), round(y0), round(x1 - x0), round(y1 - y0)


def set_brush(t, c, d):
    """ブラシの色(F=反転)と向き（ノーツボタン▾の一覧から選ぶ）を合わせる"""
    ed = t.ed
    st = ed.js("window._dbgApp.state().brush")
    if st["c"] != c:
        ed.move(960, 800); ed.key("f"); ed.wait(0.1)
    if st["d"] != d or st["type"] != "note":
        t.click_el("#tbModeNote"); ed.wait(0.3)
        t.click_el(f"#tbDirPanel .dirRow[data-d='{d}']"); ed.wait(0.2)


def place_note(t, x, y, c, d):
    set_brush(t, c, d)
    p = t.cell(x, y)
    t.ed.move(p["x"], p["y"]); t.ed.wait(0.25)
    t.ed.click(p["x"], p["y"]); t.ed.wait(0.25)


def seek_to(ed, b):
    """再生ヘッドを拍bへ（←/→で1コマ=スナップ1/2拍ずつ）"""
    cur = ed.js("window._dbgApp.state().cur")
    ed.move(960, 800)
    n = round((b - cur) / 0.5)
    for _ in range(abs(n)):
        ed.key("ArrowRight" if n > 0 else "ArrowLeft")
    ed.wait(1.5)


def stub_pickers(ed):
    # ファイル/フォルダ選択ダイアログを差し替える（ヘッドレスでは操作できないため）。
    #   音源 → テスト素材 basic.wav / 画像 → その場で描いたカバー画像 /
    #   出力フォルダ・保存先 → ブラウザ内の仮想フォルダ(OPFS)。書き出し・保存は実際にそこへ書かれる
    ed.js("""(()=>{
      window.showOpenFilePicker=async(opt)=>{
        const acc=JSON.stringify((opt&&opt.types)||[]);
        if(acc.includes('image/')){
          const c=document.createElement('canvas'); c.width=c.height=512; const g=c.getContext('2d');
          const gr=g.createLinearGradient(0,0,512,512); gr.addColorStop(0,'#ff3355'); gr.addColorStop(1,'#2d7dff');
          g.fillStyle=gr; g.fillRect(0,0,512,512); g.fillStyle='#fff'; g.font='bold 92px sans-serif'; g.textAlign='center';
          g.fillText('NLM',256,240); g.font='bold 48px sans-serif'; g.fillText('Tutorial',256,320);
          const blob=await new Promise(r=>c.toBlob(r,'image/png'));
          const f=new File([blob],'cover.png',{type:'image/png'});
          return [{kind:'file',name:'cover.png',getFile:async()=>f}]; }
        const blob=await (await fetch('tools/fixtures/basic.wav',{cache:'no-store'})).blob();
        const f=new File([blob],'basic.wav',{type:'audio/wav'});
        return [{kind:'file',name:'basic.wav',getFile:async()=>f}]; };
      window.showDirectoryPicker=async()=>(await navigator.storage.getDirectory()).getDirectoryHandle('CustomLevels',{create:true});
      window.showSaveFilePicker=async(opt)=>(await navigator.storage.getDirectory()).getFileHandle('my-first-map.nlmf',{create:true});
      return true; })()""")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    with Editor(width=W, height=H) as ed:
        use_lang(ed)
        t = Tut(ed)
        stub_pickers(ed)
        ed.wait(0.5)

        # 01 起動直後の画面構成
        t.shot("01-overview", marks="""[
          {t:'#pvpane',n:1,at:'in',pad:-4},{t:'#nodecol',n:2,at:'in',pad:-4},{t:'#main',n:3,at:'in',pad:-4},
          {t:'#maintb',n:4,at:'l'},{t:'#transportBar',n:5,at:'l'}]""")

        # 02 ファイルメニュー
        t.click_el("#mFileBtn"); ed.wait(0.5)
        t.shot("02-file-menu", marks="[{t:'#mFileMenu button[data-act=loadsong]',n:1,at:'r'}]", clip=(0, 0, 900, 420))
        # 02b 曲を取り込んだ時の「曲を解析しますか？」。撮影の環境（cdp.Editor.TEST_SETTINGS）は聞かない設定なので、
        # 読み込む直前にキーを消して初めて使う人と同じにする（tests/_lib/analysis_helpers.py の ask_on）。撮った後は［今はしない］
        ana_h.ask_on(ed)
        t.click_el("#mFileMenu button[data-act=loadsong]")
        wait_js(ed, "!!document.querySelector('#dirtyDlg[data-ana=ask]')", "「曲を解析しますか？」が出ません")
        ed.move(1700, 1060); ed.wait(0.4)
        d = t.rect("#dirtyDlg")
        t.shot("02b-analyze-ask", marks="""[{t:'#dirtyDlg button[data-v=go]',n:1,at:'b'},{t:'#dirtyDlg button[data-v=later]',n:2,at:'b'},
          {t:'#dirtyDlg .aaChk',n:3,at:'l'}]""",
               clip=(round(d["x"]) - 50, round(d["y"]) - 30, round(d["w"]) + 100, round(d["h"]) + 75))
        t.click_el("#dirtyDlg button[data-v=later]")
        wait_js(ed, "!document.querySelector('#dirtyDlg[data-ana=ask]')", "「曲を解析しますか？」が閉じません")
        ed.wait(1.5)

        # 03 曲を読み込んだ直後のNLE。①は波形だけを囲み、左の溝（「Music」の文字・自動調整・音量）は⑦の音量補正として別に囲む。
        # ⑧はスペクトログラムの溝の［🎼 曲を解析］（音源があって解析の結果が無い時だけ出る）。⑦の下に⑧のボタンがあるので、⑦の番号は左上に付け、
        # その番号が入るように左を少し広く撮る
        wait_js(ed, "window._dbgApp.analysis().startBtn", "［曲を解析］のボタンが出ません")
        ov, mg = t.rect("#overview"), t.rect("#musicGain")
        wave = [round(mg["x"] + mg["w"]), round(ov["y"]), round(ov["x"] + ov["w"] - mg["x"] - mg["w"]), round(ov["h"])]
        t.shot("03-song-loaded", marks="""[
          {t:%s,n:1,at:'b',pad:-2},
          {t:'#bpmField',n:2,at:'l'},{t:'#vmBpmBtn',n:3,at:'tr'},{t:'#leadInField',n:4,at:'b'},
          {t:'#diffBar',n:5,at:'b'},{t:'#njsField',n:6,at:'b'},{t:'#musicGain',n:7,at:'tl',pad:-2},{t:'#anaStartBtn',n:8,at:'r'}]""" % wave,
               clip=(round(mg["x"]) - 18, 28, 1354, 532))

        # 04 BPM測定
        t.click_el("#vmBpmBtn"); ed.wait(2.0)
        # 候補メニューはクリック位置（画面右端寄り）に出るので、撮影用に左へ寄せる
        ed.js("(()=>{const m=document.getElementById('ctxmenu'),b=document.getElementById('vmBpmBtn').getBoundingClientRect();m.style.left=(b.right-m.offsetWidth)+'px';return 1})()")
        t.shot("04-bpm-detect", marks="[{t:'#ctxmenu',pad:4}]", clip=(900, 30, 940, 330))
        ed.js("document.getElementById('ctxmenu').style.display='none'")
        ed.click(1200, 300); ed.wait(0.3)

        # 04b〜04d 曲を解析（見本の結果）: 04b テンポの確認の画面 →「適用しない」→ 04c 構成の解析中の知らせ（帯の左・進み具合のバー）→
        # 解析が終わって 04d「次にやること」の案内（撮影の環境は出さない設定なので、guide_on でキーを消して出す）→［わかった］→
        # 出た帯を Ctrl+Z で消す（後の画像を前と同じ状態で撮る）
        running_s = {"ok": True, "state": "running", "stage": "structure", "progress": 0.5}
        ana_h.ana_mock(ed, tempo=TEMPO_BASIC, structure=ana_h.STRUCT,
                       status_s1=[running_s, {"waitFor": "s", "then": running_s}] + ana_h.status_seq("structure", ana_h.STRUCT, steps=()))
        ana_h.guide_on(ed)
        t.click_el("#mFileBtn"); ed.wait(0.5)
        t.click_el("#mFileMenu button[data-act=analyze]")
        wait_js(ed, "!!document.querySelector('#dirtyDlg.anaTempo')", "テンポの確認の画面が出ません")
        ed.move(1700, 1060); ed.wait(0.3)
        d = t.rect("#dirtyDlg")
        # ①の「提案」の行は文字の周りに余白が無いので、枠の余白を広めにとる（既定の3pxだと枠が文字に接して見える）
        t.shot("04b-analyze-tempo", marks="""[{t:'#dirtyDlg .atProp',n:1,at:'l',pad:7},{t:'#dirtyDlg button[data-v=a]',n:2,at:'b'},
          {t:'#dirtyDlg button[data-v=b]',n:3,at:'b'}]""",
               clip=(round(d["x"]) - 50, round(d["y"]) - 30, round(d["w"]) + 100, round(d["h"]) + 70))
        t.click_el("#dirtyDlg button[data-v=none]")
        wait_js(ed, "(a=>a.running&&a.running.stage==='structure'&&a.running.progress>=0.5)(window._dbgApp.analysis())", "構成の解析が始まりません")
        ed.move(1700, 1060); ed.wait(1.2)
        sp, ms = t.rect("#specPane"), t.rect("#anaMsg")
        t.shot("04c-analyze-running", marks="[{t:'#anaMsg',pad:4}]",
               clip=(round(sp["x"]), round(ms["y"]) - 40, 1000, round(sp["y"] + sp["h"] - ms["y"]) + 44))
        ana_h.ana_go(ed, "s")   # 止めておいた応答を返す → 構成の解析が終わる
        wait_js(ed, "!!document.querySelector('#dirtyDlg[data-ana=guide]')", "解析が終わった時の案内が出ません")
        wait_js(ed, "(i=>!i||(i.complete&&i.naturalWidth>0))(document.querySelector('#dirtyDlg[data-ana=guide] img'))", "案内の画像が読めません")
        ed.move(1700, 1060); ed.wait(0.4)
        d = t.rect("#dirtyDlg")
        t.shot("04d-analyze-guide", clip=(round(d["x"]) - 40, round(d["y"]) - 30, round(d["w"]) + 80, round(d["h"]) + 60))
        t.click_el("#dirtyDlg[data-ana=guide] button[data-v=ok]")
        wait_js(ed, "!document.querySelector('#dirtyDlg[data-ana=guide]')", "案内が閉じません")
        ed.wait(3.0)   # 溝の［クリップを作る］が光り終わるまで
        ed.move(1200, 300); ed.key("z", ctrl=True)   # 帯を消す（解析の結果が届いた所を戻す）
        wait_js(ed, "(a=>!a.running&&!a.shown&&!a.data&&a.startBtn)(window._dbgApp.analysis())", "解析の帯を消せません")
        if ed.js("window._dbgApp.state().BPM") != 120 or ed.js("window._dbgApp.prev().leadInMs") != 0:
            raise SystemExit("曲の解析で BPM・無音追加が変わりました")

        # 05〜07 配置モードでノーツを置く
        seq = [  # (拍, 列x, 段y, 色c, 向きd)  色0=赤(左手) 1=青(右手) / 向き0=上 1=下
            (1, 1, 0, 0, 1), (1, 2, 0, 1, 1),
            (2, 0, 1, 0, 0), (2, 3, 1, 1, 0),
            (3, 1, 0, 0, 1), (3, 2, 0, 1, 1),
            (4, 0, 2, 0, 0), (4, 3, 2, 1, 0),
            (5, 1, 0, 0, 1), (5.5, 2, 0, 1, 1),
            (6, 1, 1, 0, 0), (6.5, 2, 1, 1, 0),
        ]
        beat = 0.0
        for i, (b, x, y, c, d) in enumerate(seq):
            while beat < b - 1e-6:
                ed.move(960, 800); ed.key("ArrowRight"); beat += 0.5   # 既定スナップ1/2拍
            place_note(t, x, y, c, d)
            if i == 5:
                # ゴースト（半透明の配置予定）が見える状態でツールバーを説明
                set_brush(t, 0, 0)
                p = t.cell(0, 2); ed.move(p["x"], p["y"]); ed.wait(0.6)
                t.shot("05-place-mode", marks="""[
                  {t:'#camModeInd',n:1,at:'b'},{t:'#tbSnapBtn',n:2,at:'b'},{t:'#tbModeNote',n:3,at:'b'},
                  {t:'#tbModeBomb',n:4,at:'b'},{t:'#tbModeWall',n:5,at:'b'},{t:'#tbColSw',n:6,at:'b'},
                  {t:[%d,%d,%d,%d],n:7,at:'tr'}]""" % tuple(_union(t, "#tbArcBtn", "#tbChainBtn")),
                       clip=(400, 560, 1120, 520))
        # 06 向きの選択（ノーツボタンの▾）
        t.click_el("#tbModeNote"); ed.wait(0.5)
        t.shot("06-direction", marks="[{t:'#tbDirPanel',pad:3}]", clip=(560, 560, 700, 440))
        t.click_el("#tbModeNote"); ed.wait(0.3)
        # 07 置き終わった状態（NLEに自動でクリップができている）
        seek_to(ed, 0)   # 1コマずつ戻す（v1.4.0-oz より前は Ctrl+← で配置モードの定位置カメラがずれたための回避策。今は Ctrl+← でもよい）
        t.shot("07-notes-placed")

        # 08〜09 アークとチェーン: 素材のノーツを置いてからカメラ固定モードで選ぶ
        seek_to(ed, 8);  place_note(t, 1, 0, 0, 1)
        seek_to(ed, 10); place_note(t, 0, 2, 0, 0)
        seek_to(ed, 12); place_note(t, 2, 2, 1, 1)
        # チェーンの尾はドットにする（尾の向きはチェーンに使われない。12拍と同じ「下」にすると
        # 「同じ向きの連続の警告」の赤枠が08に写り、基本編では説明していないので紛らわしい）
        seek_to(ed, 13); place_note(t, 3, 0, 1, 8)
        seek_to(ed, 7)
        ed.move(960, 800); ed.key("q"); ed.wait(2.5)
        objs = [o for o in ed.js("window._dbgApp.objScreen()") if o["kind"] == "note"]
        def obj_at(b, x, y):
            return next(o for o in objs if abs(o["beat"] - b) < 1e-6 and o["x"] == x and o["y"] == y)
        a, b2 = obj_at(8, 1, 0), obj_at(10, 0, 2)
        ed.click(a["sx"], a["sy"]); ed.wait(0.3)
        ed.click(b2["sx"], b2["sy"], shift=True); ed.wait(0.5)
        t.shot("08-select", marks="[{t:'#camModeInd',n:1,at:'b'}]", clip=(400, 560, 1120, 520))
        ed.key("r", ctrl=True); ed.wait(0.8)
        objs = [o for o in ed.js("window._dbgApp.objScreen()") if o["kind"] == "note"]
        c1, c2 = obj_at(12, 2, 2), obj_at(13, 3, 0)
        ed.click(c1["sx"], c1["sy"]); ed.wait(0.3)
        ed.click(c2["sx"], c2["sy"], shift=True); ed.wait(0.3)
        ed.key("c"); ed.wait(0.8)
        ed.move(960, 1000); ed.key("a"); ed.wait(0.5)   # A=選択解除
        ed.move(300, 800); ed.wait(0.5)
        t.shot("09-arc-chain", clip=(400, 560, 1120, 520))

        # 10 ボムと壁（配置モードへ戻る）
        ed.move(960, 800); ed.key("q"); ed.wait(2.0)
        seek_to(ed, 14)
        t.click_el("#tbModeBomb"); ed.wait(0.3)
        for x, y in ((1, 1), (2, 1)):
            p = t.cell(x, y); ed.move(p["x"], p["y"]); ed.wait(0.2); ed.click(p["x"], p["y"]); ed.wait(0.3)
        seek_to(ed, 15)
        t.click_el("#tbModeWall"); ed.wait(0.3)
        p0, p1 = t.cell(0, 0), t.cell(0, 2)
        for i, (x, y) in enumerate(((p0["x"], p0["y"]), (p0["x"], p0["y"]), (p1["x"], p1["y"]), (p0["x"] + 220, p0["y"] + 20))):
            ed.move(x - 5, y); ed.wait(0.15); ed.move(x, y); ed.wait(0.3); ed.click(x, y); ed.wait(0.4)
        t.click_el("#tbModeNote"); ed.wait(0.3); t.click_el("#tbModeNote"); ed.wait(0.3)
        ed.move(960, 800); ed.key("a")
        seek_to(ed, 13)
        ed.move(300, 800); ed.wait(0.5)
        t.shot("10-bomb-wall", marks="[{t:'#tbModeBomb',n:1,at:'b'},{t:'#tbModeWall',n:2,at:'b'}]", clip=(400, 560, 1120, 520))

        # 11 ライティング
        seek_to(ed, 0)
        ed.move(960, 800); ed.key("Tab"); ed.wait(1.5)   # 3Dビュー上でTab = NOTES⇄LIGHTING
        seek_to(ed, 1)
        for beat, lanes in ((1, (2, 4, 6)), (2, (4, 6)), (3, (2,)), (4, (7, 8))):
            seek_to(ed, beat)
            for li in lanes:
                q = ed.js(f"window._dbgApp.lightLaneScreen({li},{beat})")
                ed.move(q["x"], q["y"]); ed.wait(0.2); ed.click(q["x"], q["y"]); ed.wait(0.2)
        seek_to(ed, 0)
        ed.move(300, 800); ed.wait(0.5)
        # 左上のモード表示は「［TAB］ 次の画面名」(.mlNext) まで含め、余白を広めにとる（既定の3pxだと枠が文字に接して見える）
        t.shot("11-lighting", marks="[{t:[%d,%d,%d,%d],n:1,at:'r',pad:7},{t:'#tbgLBehav',n:2,at:'b'},{t:'#tbgLColor',n:3,at:'b'}]"
               % tuple(_union(t, "#mainModeLabel", "#mainModeLabel .mlNext")),
               clip=(0, 560, 1500, 520))
        ed.move(960, 800); ed.key("Tab"); ed.wait(1.0)   # NOTESへ戻す

        # 12 PREVIEW（実機に近い3Dプレビュー）
        ed.move(300, 300); ed.wait(0.3); ed.key("Tab"); ed.wait(1.0)   # 左上の枠でTab = MEDIA⇄PREVIEW
        seek_to(ed, 1)
        ed.move(300, 300); ed.wait(1.5)
        t.shot("12-preview", marks="[{t:[%d,%d,%d,%d],n:1,at:'r',pad:7},{t:'#transportBar',n:2,at:'l'}]"
               % tuple(_union(t, "#pvModeLabel", "#pvModeLabel .mlNext")))
        ed.move(300, 300); ed.key("Tab"); ed.wait(0.5)

        # 13〜14 INFO画面: 曲情報・難易度・カバー・書き出し
        ed.move(1200, 300); ed.wait(0.3); ed.key("Tab"); ed.wait(1.5)   # NLEの上でTab = NLE⇄INFO
        for f, text in (("name", "My First Map"), ("artist", "NLM Tutorial"), ("author", "YourName")):
            t.click_el(f"#infoWorld input[data-f={f}]"); ed.wait(0.2); t.type(text); ed.wait(0.2)
        t.click_el("#infoWorld input[data-d=Hard]"); ed.wait(0.3)
        t.click_el("#infoWorld button.nPick"); ed.wait(1.5)
        t.click_el("#infoWorld button.oPick"); ed.wait(1.0)
        t.click_el("#infoWorld input.oName"); ed.wait(0.2); t.type("MyFirstMap"); ed.wait(0.2)
        ed.move(1000, 520); ed.wait(1.0)
        t.shot("13-info", marks="""[
          {t:'#infoWorld input[data-f=name]',n:1,at:'r'},{t:'#infoWorld input[data-d=Hard]',n:2,at:'l'},
          {t:'#infoWorld button.nPick',n:3,at:'l'},{t:'#infoWorld button.oPick',n:4,at:'tr'},
          {t:'#infoWorld input.oName',n:5,at:'r'}]""", clip=(580, 30, 1340, 530))
        # 書き出しボタンを撮ってから押し、実際に仮想フォルダへ書き出されたことを確かめる
        ed.js("(()=>{const b=[...document.querySelectorAll('#infoWorld button')].find(x=>x.textContent.includes(" + repr(L('カスタム曲書き出し')) + "));b.id='tutExportBtn';return 1})()")
        r = t.rect("#tutExportBtn"); o = t.rect("#infoWorld button.oPick")
        t.shot("14-export", marks="[{t:'#tutExportBtn',n:1,at:'l'}]",
               clip=(round(o["x"]) - 60, round(o["y"]) - 60, round(o["w"]) + 120, round(r["y"] + r["h"] - o["y"]) + 90))
        t.click_el("#tutExportBtn")
        files = []
        for _ in range(40):   # 書き出し（ffmpegでのsong.egg変換を含む）の完了を待つ
            ed.wait(0.5)
            files = ed.js("""(async()=>{ try{ const d=await (await (await navigator.storage.getDirectory()).getDirectoryHandle('CustomLevels')).getDirectoryHandle('MyFirstMap');
                const o=[]; for await (const [n,h] of d.entries()) o.push(n); return o.sort(); }catch(_){ return []; } })()""")
            if "Info.dat" in files and "song.egg" in files:
                break
        print("書き出されたファイル:", files)
        if "Info.dat" not in files or "song.egg" not in files:
            raise SystemExit("書き出しに失敗しました")
        ed.move(1200, 300); ed.key("Tab"); ed.wait(1.0)   # NLEへ戻す

        # 15 保存（未保存ランプ）
        t.shot("15-dirty-lamp", marks="[{t:'#dirtyLamp',n:1,at:'b'}]", clip=(1280, 30, 640, 90))
        ed.move(960, 800); ed.key("s", ctrl=True); ed.wait(2.0)
        print("保存後:", ed.js("window._dbgApp.dirty()"))
        t.shot("15b-saved", clip=(1280, 30, 640, 90))
        print(ed.js("window._dbgApp.state()"), ed.errors())


if __name__ == "__main__":
    main()

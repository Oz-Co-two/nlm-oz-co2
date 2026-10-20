"""画面の中の案内に使う画像（guide/）を撮り直すスクリプト。

今は「曲の解析が終わりました ― 次にやること」の案内（js/analysis/song-analysis.js の showGuide）に入れる、
解析の帯と溝の［🧩 クリップを作る］のボタン（赤枠）の画像だけ:
  guide/ana-clips-btn-ja.png（日本語表示）・guide/ana-clips-btn-en.png（英語表示）
どちらの言語の画像を出すかは訳の ana.guide.img（lang/*.json）が決める。

解析の応答は自動テストと同じ偽物（tests/_lib/analysis_helpers.py。素材 basic・BPM 120・見本の構成）。赤枠は撮影の直前にページへ
一時的に重ねた印（アプリの機能ではない）。tools/cdp.py の Editor は案内を出さない設定（Editor.TEST_SETTINGS）で開くので、撮影中に案内は出ない。
ボタンの見た目・帯の配置を変えたら撮り直す（画面の中の案内なので、配布物＝exe にも入る。nlm.spec の datas）。

使い方: .venv-build/Scripts/python.exe tools/make_guide_shots.py [ja|en]   （省略＝両方）
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "tests" / "_lib"))   # 曲の解析の偽の応答（analysis_helpers。serve を import しない）
from cdp import Editor  # noqa: E402
import analysis_helpers as ana_h  # noqa: E402
from e2e_helpers import wait_until  # noqa: E402

OUT = HERE.parent / "guide"
LANGS = [a for a in sys.argv[1:] if a in ("ja", "en")] or ["ja", "en"]

# 撮影用の印（赤枠）。ショートカットの早見表は写さない
MARK_JS = r"""(()=>{
  if(!document.getElementById('guideShotStyle')){ const s=document.createElement('style'); s.id='guideShotStyle';
    s.textContent=`#nodeKeys,#modeKeys,#commonKeys{display:none!important}
      .guideShotBox{position:fixed;border:3px solid #ff3355;border-radius:7px;box-shadow:0 0 0 2px rgba(0,0,0,.55);pointer-events:none;z-index:99998}`;
    document.head.appendChild(s); }
  document.querySelectorAll('.guideShotBox').forEach(e=>e.remove());
  const r=document.getElementById('anaClipsBtn').getBoundingClientRect(), p=3, b=document.createElement('div'); b.className='guideShotBox';
  Object.assign(b.style,{left:(r.left-p)+'px',top:(r.top-p)+'px',width:(r.width+2*p)+'px',height:(r.height+2*p)+'px'});
  document.body.appendChild(b); return 1; })()"""


def shoot(lang):
    with Editor(ready=True) as ed:
        if lang == "en":
            ed.js("localStorage.setItem('bsnm_lang','en');true")
            ed.wait(0.8)   # 環境設定のミラー（config/settings.json）へ書き戻されるのを待つ
            ed.reload(clear_storage=False)
            if ed.js("document.getElementById('mFileBtn').textContent.trim()") != "File":
                raise SystemExit("英語表示に切り替わりません")
        ed.load_fixture("basic", settle=0.5)
        wait_until(ed, "window._dbgApp.analysis().startBtn", label="［曲を解析］が出る")
        # テンポは今の設定と同じ（確認の画面が出ない）・構成は見本
        ana_h.run_analysis(ed, None, tempo=ana_h.TEMPO_SAME)
        wait_until(ed, "window._dbgApp.analysis().clipsBtn.shown", label="溝の［クリップを作る］")
        ed.js("(e=>{e.style.display='none'; return 1})(document.getElementById('errToast'))")   # 下の知らせは写さない
        ed.move(1590, 975); ed.wait(0.5)   # マウスは帯の外（帯の区間の白い枠・ツールチップを出さない）
        ed.js(MARK_JS); ed.wait(0.3)
        r = ed.js("(()=>{const s=document.getElementById('specPane').getBoundingClientRect(), o=document.getElementById('overview').getBoundingClientRect();"
                  "return {x:s.left, y:o.bottom-26, b:s.bottom}})()")
        x, y = r["x"] - 6, r["y"]
        OUT.mkdir(exist_ok=True)
        path = OUT / f"ana-clips-btn-{lang}.png"
        ed.shot(path, clip=(x, y, 540, r["b"] + 6 - y))   # Music の波形の下の端・解析の帯・溝のボタン・スペクトログラムの左の部分
        errs = ed.errors()
        if errs:
            raise SystemExit("ページのエラー:\n" + "\n".join(errs))
        print("撮影:", path)


if __name__ == "__main__":
    for lg in LANGS:
        shoot(lg)

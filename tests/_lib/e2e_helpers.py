"""e2e グループの共通部品（操作の通しテスト用）。

- 素材ごとの期待値（RICH / BASIC）: tools/fixtures/make_fixtures.py の rich_map_files() と揃える
- export_files(ed): exportMap のダウンロード（<a download> の click）を横取りしてファイル名→中身を返す
- pretty_json(text): 正解ファイル用に整形（キーの順はアプリの出力のまま）
- open_fixture(t, 素材名): ページを開き直して素材を読む（t.fresh の短い待ち版）
- wait_until(ed, js式): 状態の待ち合わせ（固定の sleep を避ける）
- 入力の小道具: hover_3d / switch_diff / place_cell など
"""
import json
import time

# 素材ごとの中身（数）。rich の Expert のノーツはチェーンの頭2個を含まない（読み込みでチェーンへ吸収される）
BASIC = {"HardStandard.dat": dict(notes=8, bombs=0, walls=0, arcs=0, chains=0, lights=0)}
RICH = {
    "HardStandard.dat": dict(notes=7, bombs=1, walls=1, arcs=1, chains=0, lights=3),
    "ExpertStandard.dat": dict(notes=23, bombs=3, walls=2, arcs=2, chains=2, lights=12),
}
FIXTURE_DIFFS = {"basic": BASIC, "rich": RICH}
KINDS = ("notes", "bombs", "walls", "arcs", "chains", "lights")
# 難易度の切替キー（1〜5 = Easy〜Expert+）
DIFF_KEY = {"Easy": "1", "Normal": "2", "Hard": "3", "Expert": "4", "ExpertPlus": "5"}


def open_fixture(t, fx=None, settle=0.3):
    """t.fresh(fx) と同じ（ページを開き直して素材を読む）だが、読込後の固定待ちを短くする（このグループは状態を待ち合わせるため）"""
    ed = t.fresh()
    if fx:
        ed.load_fixture(fx, settle=settle)
    return ed


def wait_until(ed, expr, timeout=15.0, label=""):   # 既定15秒: 全グループを並列で回すとPCが混み、5秒では足りないことがある
    """JS式 expr が真になるまで待つ（ページのイベントも取り込みながら）。値を返す"""
    end = time.time() + timeout
    v = None
    while time.time() < end:
        v = ed.js(expr)
        if v:
            return v
        ed.wait(0.05)
    raise AssertionError(f"待ち合わせが {timeout} 秒で終わりません: {label or expr}（最後の値 {v!r}）")


def state(ed):
    return ed.js("window._dbgApp.state()")


def counts(ed):
    return state(ed)["counts"]


def dirty(ed):
    return ed.js("window._dbgApp.dirty()")


def project(ed):
    """アプリ自身の保存内容（buildProjectText）を辞書で。揺れる savedAt は除く"""
    pj = json.loads(ed.js("window._dbg.rt.buildProjectText()"))
    pj.pop("savedAt", None)
    return pj


def project_text(ed):
    return json.dumps(project(ed), ensure_ascii=False, sort_keys=True)


def diff_counts_from_project(pj):
    """保存内容から難易度ごとの数を数える。クリップがあればクリップの中身（content）が正、無ければフラット配列"""
    out = {}
    for st in pj.get("difficulties", {}).values():
        secs = [s for s in st.get("sections") or [] if s.get("kind") != "null" and s.get("content")]
        c = {k: 0 for k in KINDS}
        if any(any(s["content"].get(k) for k in KINDS) for s in secs):
            for s in secs:
                for k in KINDS:
                    c[k] += len(s["content"].get(k) or [])
        else:
            for k in KINDS:
                c[k] = len(st.get("lightEvents" if k == "lights" else k) or [])
        if any(c.values()):
            out[st["name"]] = c
    return out


def pretty_json(text):
    return json.dumps(json.loads(text), ensure_ascii=False, indent=1) + "\n"


# ---- 書き出しの横取り ----
_CAPTURE_JS = r"""(()=>{
  if(window.__nlmCap) { window.__nlmCap.files=[]; return true; }
  const cap=window.__nlmCap={files:[],blobs:new Map()};
  const oc=URL.createObjectURL.bind(URL);
  URL.createObjectURL=function(b){ const u=oc(b); cap.blobs.set(u,b); return u; };
  const click=HTMLAnchorElement.prototype.click;
  HTMLAnchorElement.prototype.click=function(){
    if(this.download&&cap.blobs.has(this.href)){ cap.files.push({name:this.download,blob:cap.blobs.get(this.href)}); return; }  // 実際のダウンロードはしない
    return click.call(this); };
  return true; })()"""


def export_files(ed):
    """出力フォルダ未選択の exportMap（ダウンロードで書き出す）を実行し、{ファイル名: 中身の文字列} を返す。
    アプリ本体は変えず、ページ内で URL.createObjectURL と <a>.click を横取りする"""
    ed.js(_CAPTURE_JS)
    ed.js("window._dbg.rt.exportMap()")
    files = ed.js("""(async()=>{ const out={};
      for(const f of window.__nlmCap.files) out[f.name]=await f.blob.text();
      return out; })()""")
    return files


# ---- 入力の小道具 ----
def canvas_center(ed):
    """3Dビュー（キャンバス）の中央付近の画面座標"""
    return ed.js("(()=>{const c=document.querySelector('#cv')||document.querySelector('canvas');const r=c.getBoundingClientRect();"
                 "return {x:r.left+r.width/2,y:r.top+r.height*0.25}})()")


def hover_3d(ed):
    """3Dビューの上にマウスを置く（キー操作の効き先＝ペインはマウスの位置で決まる）"""
    p = cell(ed, 0, 2) or canvas_center(ed)
    ed.move(p["x"], p["y"] - 60)


def cell(ed, x, y):
    return ed.js(f"window._dbgApp.cellScreen({x},{y})")


def place_at(ed, x, y):
    """配置モードでマス(x,y)をクリックしてノーツを置く（今の拍・今のブラシ）。置く前の数を返す"""
    before = counts(ed)["notes"]
    # 難易度の切替・素材の読込の直後はカメラが動いている途中のことがある（並列実行でPCが混むと長引く）＝画面に入るまで待つ
    try:
        wait_until(ed, f"(p=>p&&p.onScreen)(window._dbgApp.cellScreen({x},{y}))", timeout=5.0)
    except AssertionError:
        pass
    ed.wait(0.1)
    p = cell(ed, x, y)
    assert p and p["onScreen"], f"マス({x},{y})が画面に出ていません: {p}"
    ed.move(p["x"], p["y"]); ed.wait(0.15)   # ホバーでゴーストが出てから押す
    ed.click(p["x"], p["y"])
    wait_until(ed, f"window._dbgApp.state().counts.notes==={before + 1}", label=f"マス({x},{y})へのノーツ配置")
    return before


def notes_at(ed, beat):
    """拍 beat にあるノーツ（x,y,c,d）"""
    return ed.js(f"window._dbgApp.notes().notes.filter(n=>Math.abs(n.beat-{beat})<1e-6).map(n=>({{x:n.x,y:n.y,c:n.c,d:n.d}}))")


def bulk_load_rich_map(ed):
    """tools/fixtures/rich_map を「曲データを読み込む」（bulkLoadSongData）で読ませる（make_fixtures.py と同じ手順）"""
    import importlib.util
    from pathlib import Path
    p = Path(__file__).resolve().parents[2] / "tools" / "fixtures" / "make_fixtures.py"
    spec = importlib.util.spec_from_file_location("nlm_make_fixtures", p)
    mf = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mf)
    ed.js(mf.bulk_load_js("tools/fixtures/rich_map/", list(mf.rich_map_files()), "tools/fixtures/basic.wav"))
    wait_until(ed, "window._dbgApp.state().counts.notes>0", label="一括読込")
    ed.wait(0.3)
    return mf


def switch_diff(ed, name):
    """数字キーで難易度を切り替え、切り替わるまで待つ"""
    hover_3d(ed)
    ed.key(DIFF_KEY[name])
    wait_until(ed, f"window._dbgApp.state().diff==='{name}Standard.dat'", label=f"難易度 {name} への切替")
    ed.wait(0.1)

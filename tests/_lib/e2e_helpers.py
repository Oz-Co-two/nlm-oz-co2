"""e2e グループの共通部品（操作の通しテスト用）。

- 素材ごとの期待値（RICH / BASIC）: tools/fixtures/make_fixtures.py の rich_map_files() と揃える
- export_files(ed): exportMap のダウンロード（<a download> の click）を横取りしてファイル名→中身を返す
- pretty_json(text): 正解ファイル用に整形（キーの順はアプリの出力のまま）
- open_fixture(t, 素材名): ページを開き直して素材を読む（t.fresh の短い待ち版）
- wait_until(ed, js式): 状態の待ち合わせ（固定の sleep を避ける）
- 入力の小道具: hover_3d / switch_diff / place_cell など
- media_lib_load(ed, extra): MEDIA の記録したライブラリにテスト素材 tools/fixtures/media_lib を出す（画面テスト・英語表示の点検でも使う）
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


# ---- MEDIA の記録したライブラリ（2026-10-12）----
from pathlib import Path as _Path
MEDIA_LIB = _Path(__file__).resolve().parents[2] / "tools" / "fixtures" / "media_lib"
_EXTRA_JS = r"""(()=>{ window.__libExtra=%s;
  if(window.__libExtraHooked) return true; window.__libExtraHooked=true;
  const of=window.fetch;
  window.fetch=async function(u,init){ const r=await of.apply(this,arguments);
    if(String(u&&u.url||u).endsWith('__lib/extra')){ const j=await r.clone().json(), X=window.__libExtra||{};
      if(j&&j.extra) for(const k in X) j.extra[k]=Object.assign({},j.extra[k]||{},X[k]);
      return new Response(JSON.stringify(j),{status:200,headers:{'Content-Type':'application/json; charset=utf-8'}}); }
    return r; };
  return true; })()"""


def media_lib_record(ed, *paths):
    """config/library.json に記録を書く（exe 版のフォルダ選択ダイアログで選んだのと同じ状態。JS から記録を増やす口は無い）"""
    cfg = _Path(ed.data_dir) / "config"
    cfg.mkdir(parents=True, exist_ok=True)
    (cfg / "library.json").write_text(json.dumps({"libs": [{"path": str(p)} for p in paths]}, ensure_ascii=False), encoding="utf-8")


def media_lib_extra(ed, extra):
    """/__lib/extra の応答に extra（{rel: {net?, play?, est?}}）を重ねる（ページ内の fetch を包む。開き直すと消える）"""
    ed.js(_EXTRA_JS % json.dumps(extra, ensure_ascii=False))


def media_lib_wait(ed, timeout=20):
    """記録したライブラリの走査（見つからない物を除く）と、その後の extra の読み込みが終わるまで待つ"""
    return wait_until(ed, """(s=>{ const n=s.libs.filter(l=>l.native); return n.length>0&&n.every(l=>l.state!=='ok'||(!l.scanning&&l.extra===l.songs&&l.songs>0)); })(window._dbgApp.lib())""",
                      timeout=timeout, label="ライブラリの走査")


# ネット・プラグインの窓口（/__lib/details・beatsaver・rate・playdata）の応答をページ内で差し替える。ネットとプラグインには出ない
# （テストのサーバーは NLM_NO_NET でネットへ出ないが、差し替えれば「取得できた」「見つかった」「混んでいる」等の応答を作れる）。
# 差し替えた窓口への要求は __libMock.calls に残り、同時に処理中だった数の最大を __libMock.max に数える（★の計算の同時の数の確認）。
# /__lib/extra は差し替えずに要求だけを残す（全曲データの ON/OFF で net:false を送るかの確認）
_MOCK_JS = r"""(()=>{ const M=window.__libMock=window.__libMock||{calls:[],h:{},inflight:{},max:{}};
  if(window.__libMockHooked) return true; window.__libMockHooked=true;
  const of=window.fetch;
  window.fetch=async function(u,init){
    const m=/__lib\/(details|beatsaver|rate|playdata|extra)$/.exec(String(u&&u.url||u)), h=m&&M.h[m[1]];
    let body={}; if(m){ try{ body=JSON.parse((init&&init.body)||'{}'); }catch(_){} }
    if(m&&m[1]==='extra') M.calls.push({act:'extra',body});
    if(!h) return of.apply(this,arguments);
    const act=m[1];
    M.calls.push({act,body});
    M.inflight[act]=(M.inflight[act]||0)+1; M.max[act]=Math.max(M.max[act]||0,M.inflight[act]);
    try{ const r=await h(body); return new Response(JSON.stringify(r),{status:200,headers:{'Content-Type':'application/json; charset=utf-8'}}); }
    finally{ M.inflight[act]--; } };
  return true; })()"""
# 全曲データの見本の状態（2026-10-12 06:30 時点のデータ・取得済み）。画面テスト・英語表示の点検でも使う
SAMPLE_AS_OF = 1791754200   # 2026-10-12 06:30（日本時間）
SAMPLE_DETAILS = "b=>({state:'ok',asOf:%d,fetchedAt:%d,did:b.act==='update'?'throttled':undefined})" % (SAMPLE_AS_OF, SAMPLE_AS_OF + 3600)


def media_lib_mock(ed, **handlers):
    """/__lib/<窓口> の応答をページ内で差し替える。値は JS の関数の式（要求の本体 b を受けて応答を返す。async 可）。None で差し替えをやめる。
    例: media_lib_mock(ed, rate="async b=>{ await new Promise(r=>setTimeout(r,200)); return {ok:false,error:'notInstalled'}; }")"""
    ed.js(_MOCK_JS)
    for act, fn in handlers.items():
        ed.js(f"window.__libMock.h[{json.dumps(act)}]={fn or 'undefined'};true")


def media_lib_calls(ed, act=None):
    """差し替えた窓口へ来た要求 [{act, body}]（act を渡すとその窓口だけ）"""
    cs = ed.js("window.__libMock?window.__libMock.calls:[]")
    return [c for c in cs if act is None or c["act"] == act]


def media_lib_load(ed, extra=None, paths=None, covers=0, details=None):
    """ライブラリ（既定は tools/fixtures/media_lib）を記録してページに読ませ（起動時と同じ loadNativeLibs）、走査が終わるまで待つ。
    covers: 読み込みを待つカバー・画像の数（見えている物から読む）。details: 全曲データの状態の応答の差し替え（JS の関数の式。
    SAMPLE_DETAILS＝取得済み。渡さなければテストのサーバーの本物＝未取得か取得の失敗）"""
    media_lib_record(ed, *(paths or [MEDIA_LIB]))
    if extra:
        media_lib_extra(ed, extra)
    if details:
        media_lib_mock(ed, details=details)
    ed.js("window._dbg.rt.loadNativeLibs().then(()=>{ window._dbg.rt.libOnline.ensureDetails(); return true; })")   # 起動時と同じ（全曲データの取得を頼む）
    media_lib_wait(ed)
    if details:
        wait_until(ed, "(s=>s.details&&s.details.state==='ok'&&!s.detailsBusy)(window._dbgApp.libOnline())", label="全曲データの状態")
    if covers:
        wait_until(ed, f"window._dbgApp.lib().libs.filter(l=>l.native).reduce((a,l)=>a+l.covers,0)>={covers}", label="カバーの読み込み")
    ed.wait(0.15)   # 一覧の描き直し（refreshSoon）


def media_lib_sample_extra():
    """画面テスト・英語表示の点検用の、ネット・NLM推定の値（BL★・NLM推定・全曲データに無い曲）"""
    import datetime
    t = lambda y, m, d: int(datetime.datetime(y, m, d, 12).timestamp())
    return {
        "1a01 (Alpha Song - MapperA)": {"net": {"src": "dump", "match": "hash", "key": "1a01", "uploaded": t(2024, 5, 1), "up": 90, "down": 10,
                                                "ranked": {"bl": True, "blq": False, "ss": True, "ssq": False}, "tags": ["tech", "anime"],
                                                "diffs": {"Standard/Expert": {"bl": 7.25}, "Standard/ExpertPlus": {"bl": 9.5, "ss": 8.1}}}},
        "1b02 (Beta Song - MapperB)": {"net": {"src": "dump", "match": "key", "key": "1b02", "uploaded": t(2023, 1, 1), "up": 5, "down": 5, "tags": [], "diffs": {}},
                                       "est": {"version": "0.1.0", "diffs": {"Standard/Hard": {"stars": 4.56}, "Standard/Easy": {"skipped": "tooFewNotes"}}}},
        "1c03 (Gamma V4 - MapperC)": {"net": {"src": "none"}},
        "Delta Noodle": {"net": {"src": "none"}, "est": {"version": "0.1.0", "diffs": {"Standard/ExpertPlus": {"stars": 11.11}}}},
    }

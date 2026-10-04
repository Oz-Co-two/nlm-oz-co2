"""MEDIA（ライブラリ）とアセットのクリップ。
- フォルダの登録: 「フォルダを追加」のフォルダ選択（showDirectoryPicker）をページ内で偽物に差し替え、tools/fixtures/rich_map を
  Beat Saber の譜面フォルダとして・basic.wav を音楽ファイルとして見せる
- 曲をNLEのレーンへドラッグ（addSongLine）: 今の難易度の譜面だけを、落とした拍に置く
- クリップをアセットへ保存・名前変更・削除（serve.py の /__asset/*）。保存先は一時フォルダ（tools/cdp.py の NLM_DATA_DIR）
- アセットのクリップをNLEへドラッグして配置
ドラッグは本物の入力（CDP のドラッグの横取り＋dragEnter/dragOver/drop。nle_helpers.drag_media）"""
import json

from e2e_helpers import wait_until, counts, switch_diff, RICH
from nle_helpers import (open_nle, clips, total, menu, clip_xy, nle, nle_mouse, scr, lane_y, undo, take_errors,
                         lib_items, lib_item_xy, drag_media, asset_dir, clear_assets)

_FAKE_LIB_JS = r"""(async()=>{
  const base='tools/fixtures/rich_map/', names=['Info.dat','HardStandard.dat','ExpertStandard.dat'];
  const info=await (await fetch(base+'Info.dat',{cache:'no-store'})).json();
  const wav=await (await fetch('tools/fixtures/basic.wav',{cache:'no-store'})).blob();
  const fh=(nm,blob)=>({kind:'file',name:nm,getFile:async()=>new File([blob],nm)});
  const notFound=()=>{ throw new DOMException('not found','NotFoundError'); };
  const mapDir={kind:'directory',name:'rich_map',values:async function*(){},
    getFileHandle:async nm=>{ if(nm===info._songFilename) return fh(nm,wav); if(!names.includes(nm)) notFound();
      return fh(nm,new Blob([await (await fetch(base+nm,{cache:'no-store'})).text()])); }};
  const root={kind:'directory',name:'FakeLevels',getFileHandle:async()=>notFound(),
    values:async function*(){ yield mapDir; yield fh('basic.wav',wav); }};
  window.showDirectoryPicker=async()=>root;   // 「フォルダを追加」のフォルダ選択ダイアログの代わり
  return true; })()"""
SONG = "リッチ テスト曲"


def _add_fake_library(ed):
    ed.js(_FAKE_LIB_JS)
    p = ed.js("(()=>{const r=document.getElementById('libAddBtn').getBoundingClientRect();return {x:r.left+r.width/2,y:r.top+r.height/2}})()")
    ed.click(p["x"], p["y"])
    wait_until(ed, f"(n=>n.includes({json.dumps(SONG)})&&n.includes('basic'))([...document.querySelectorAll('#libGrid .libName')].map(e=>e.textContent))",
               label="ライブラリの走査")


def _wait_files(ed, adir, want, timeout=5.0):
    """アセットの保存先のファイル一覧が want になるまで待つ（サーバーへの書き込みは非同期）"""
    import time
    end = time.time() + timeout
    while time.time() < end and sorted(p.name for p in adir.glob("*.nlmclip")) != sorted(want):
        ed.wait(0.05)


def _lane_target(ed, beat, lk, track):
    return scr(ed, beat)["x"], lane_y(ed, lk, track)


def test_drag_song_to_notes_lane(t):
    '''「フォルダを追加」でフォルダを走査しMEDIAに並ぶ／MEDIAの曲をNotesのレーンの拍8へドラッグ→今の難易度（Hard）の譜面だけが拍8のクリップになる・NJSも取り込む・他の難易度は空のまま→Undo'''
    ed = open_nle(t, "basic")
    _add_fake_library(ed)
    items = lib_items(ed)
    t.ok(SONG in items and "basic" in items, f"譜面フォルダはInfo.datの曲名・音楽ファイルは拡張子を除いた名前でMEDIAに出る: {items}")
    cats = ed.js("[...document.querySelectorAll('#libList .libCat')].map(e=>e.textContent)")
    t.ok(any("FakeLevels" in c for c in cats), f"左の一覧に登録したフォルダの名前が出る: {cats}")
    n0 = counts(ed)["notes"]
    drag_media(ed, SONG, *_lane_target(ed, 8, "n", 0))
    wait_until(ed, "window._dbgApp.nle().clips.length===2", label="曲のドロップ")
    c = next(c for c in clips(ed, "n") if c["label"] == SONG)
    h = RICH["HardStandard.dat"]
    t.eq(c["beat"], 8, "落とした拍に置く")
    t.eq(c["track"], 2, "空いている一番下のレーン（Notes 1）から詰める")
    t.eq({k: c["n"][k] for k in ("notes", "bombs", "walls", "arcs", "chains")},
         {k: h[k] for k in ("notes", "bombs", "walls", "arcs", "chains")}, "Hardのノーツ系だけが入る")
    t.eq(c["n"]["lights"], 0, "ノーツのレーンへ落とした時はライトは入らない")
    t.eq(counts(ed)["notes"], n0 + h["notes"], "3Dのノーツが増える")
    beats = sorted(n["beat"] for n in ed.js("window._dbgApp.notes().notes") if n["beat"] >= 8)
    t.eq(beats, [10, 11, 12, 13, 14, 16, 18], "元の譜面の拍＋8に置かれる")
    pj = json.loads(ed.js("window._dbg.rt.buildProjectText()"))
    t.eq(pj["njsCfg"].get("hardstandard.dat"), {"njs": 14, "offset": 0}, "Hardの飛来速度/オフセットを元の曲から取り込む")
    ex = pj["difficulties"].get("expertstandard.dat")
    t.ok(not ex or not ex.get("sections"), f"今の難易度以外にはクリップを足さない: {ex and ex.get('sections')}")
    nle_mouse(ed)
    undo(ed)
    wait_until(ed, "window._dbgApp.nle().clips.length===1", label="ドロップのUndo")
    t.eq(counts(ed)["notes"], n0, "Undoで元のノーツ数")
    t.no_errors()


def test_drag_song_to_light_lane_expert(t):
    '''Expertに切り替えて曲をLightのレーンへドラッグ→Expertのライトだけが落とした拍のクリップになる'''
    ed = open_nle(t, "basic")
    _add_fake_library(ed)
    switch_diff(ed, "Expert")
    drag_media(ed, SONG, *_lane_target(ed, 4, "l", 1))
    wait_until(ed, "window._dbgApp.nle().clips.length===1", label="曲のドロップ")
    c = clips(ed, "l")[0]
    t.eq((c["beat"], c["track"], c["label"]), (4, 2, SONG), "落とした拍・一番下のLightレーン・曲名")
    t.eq(total([c]), {"notes": 0, "bombs": 0, "walls": 0, "arcs": 0, "chains": 0, "lights": RICH["ExpertStandard.dat"]["lights"]},
         "Expertのライトだけが入る")
    t.eq(len(clips(ed, "n")), 0, "ノーツのクリップは作らない")
    pj = json.loads(ed.js("window._dbg.rt.buildProjectText()"))
    t.ok("expertstandard.dat" not in pj["njsCfg"], f"ライトの配置では飛来速度を取り込まない: {pj['njsCfg']}")
    t.no_errors()


def test_drag_music_file(t):
    '''音楽ファイルをNLEのレーンへ落とすと案内が出て何も置かない／Musicレーンの拍4へ落とすと音源が拍4から鳴る'''
    ed = open_nle(t, "basic")
    _add_fake_library(ed)
    drag_media(ed, "basic", *_lane_target(ed, 8, "n", 1))
    ed.wait(0.3)
    t.eq(len(clips(ed)), 1, "譜面の無い音楽ファイルはクリップにならない")
    t.eq(take_errors(ed, "音楽ファイルには譜面がありません"), 1, "案内のエラー")
    m = ed.js("window._dbgApp.musicScreen(4)")
    drag_media(ed, "basic", m["x"], m["top"] + m["h"] * 0.6)
    wait_until(ed, "window._dbgApp.nle().music.beat===4", label="Musicレーンへのドロップ")
    t.eq(ed.js("window._dbgApp.audioPosAtBeat(4)"), 0, "拍4が音源の先頭")
    t.no_errors()


def test_asset_save_from_clip(t):
    '''クリップの右クリック「アセットへ保存」→一時フォルダの asset/ に .nlmclip（種類・名前・長さ・中身）ができMEDIAに出る。同じ名前は上書きせず連番'''
    ed = t.ed
    clear_assets(ed)
    ed = open_nle(t, "rich")
    adir = asset_dir(ed)
    nc, lc = clips(ed, "n")[0], clips(ed, "l")[0]
    menu(ed, *clip_xy(ed, nc), "アセットへ保存")
    wait_until(ed, f"[...document.querySelectorAll('#libGrid .libName')].some(e=>e.textContent==={json.dumps(nc['label'])})", label="MEDIAに出る")
    files = sorted(p.name for p in adir.glob("*.nlmclip"))
    t.eq(files, [nc["label"] + ".nlmclip"], "クリップ名のファイルができる")
    data = json.loads((adir / files[0]).read_text(encoding="utf-8"))
    t.eq((data["nlmClip"], data["type"], data["name"], data["len"]), (1, "notes", nc["label"], 16), "種類・名前・長さ")
    t.eq({k: len(v) for k, v in data["content"].items()}, nc["n"], "中身の数")
    menu(ed, *clip_xy(ed, lc), "アセットへ保存")   # 同じ名前のライトのクリップ
    wait_until(ed, "document.querySelectorAll('#libGrid .libItem').length===2", label="2つ目の保存")
    files = sorted(p.name for p in adir.glob("*.nlmclip"))
    t.eq(files, sorted([nc["label"] + ".nlmclip", nc["label"] + " (2).nlmclip"]), "同じ名前は連番を付けて別のファイルにする")
    data2 = json.loads((adir / (nc["label"] + " (2).nlmclip")).read_text(encoding="utf-8"))
    t.eq((data2["type"], len(data2["content"]["lights"])), ("light", 3), "ライトのクリップは light として保存")
    t.no_errors()


def test_asset_place_by_drag(t):
    '''アセットのクリップをNotesのレーンの拍20へドラッグ→同じ中身のクリップが置かれる→Undo。種類の違うレーン・Musicレーンへは置かない'''
    ed = t.ed
    clear_assets(ed)
    ed = open_nle(t, "rich")
    nc = clips(ed, "n")[0]
    menu(ed, *clip_xy(ed, nc), "アセットへ保存")
    wait_until(ed, "document.querySelectorAll('#libGrid .libItem').length===1", label="アセットへ保存")
    name = lib_items(ed)[0]
    drag_media(ed, name, *_lane_target(ed, 20, "l", 1))   # ライトのレーン＝置かない
    ed.wait(0.3)
    t.eq(len(clips(ed)), 2, "NOTESのクリップはライトのレーンへは置かない")
    t.eq(take_errors(ed, "NOTES"), 1, "NOTESレーンへの案内")
    m = ed.js("window._dbgApp.musicScreen(20)")
    drag_media(ed, name, m["x"], m["top"] + m["h"] * 0.6)   # Musicレーン＝置かない
    ed.wait(0.3)
    t.eq((len(clips(ed)), nle(ed)["music"]["beat"]), (2, 0), "Musicレーンにも置かない（音源も変わらない）")
    t.eq(take_errors(ed, "NOTES"), 1, "NOTESレーンへの案内（Music）")
    drag_media(ed, name, *_lane_target(ed, 20, "n", 1))
    wait_until(ed, "window._dbgApp.nle().clips.filter(c=>c.lk==='n').length===2", label="アセットのドロップ")
    c = clips(ed, "n")[1]
    t.eq((c["beat"], c["len"], c["label"]), (20, 16, name), "落とした拍・元の長さ・アセット名")
    t.eq(c["n"], nc["n"], "中身は保存したクリップと同じ")
    t.eq(counts(ed)["notes"], 14, "3Dのノーツが増える")
    nle_mouse(ed)
    undo(ed)
    wait_until(ed, "window._dbgApp.nle().clips.filter(c=>c.lk==='n').length===1", label="ドロップのUndo")
    t.no_errors()


def test_asset_rename_and_delete(t):
    '''MEDIAのアセットを右クリック「名前を変更」→ファイル名と中の名前が変わる／「クリップを削除」→ファイルが消えMEDIAからも消える'''
    ed = t.ed
    clear_assets(ed)
    ed = open_nle(t, "rich")
    adir = asset_dir(ed)
    menu(ed, *clip_xy(ed, clips(ed, "l")[0]), "アセットへ保存")
    wait_until(ed, "document.querySelectorAll('#libGrid .libItem').length===1", label="アセットへ保存")
    old = lib_items(ed)[0]
    ed.js("document.querySelector('#libGrid .libItem').dataset.before='1'")   # 改名後に読み直した新しい項目と見分ける印
    menu(ed, *lib_item_xy(ed, old), "名前を変更")
    wait_until(ed, "document.activeElement&&document.activeElement.closest&&!!document.activeElement.closest('#libGrid')", label="名前の入力欄")
    ed.key("a", ctrl=True)
    ed.call("Input.insertText", text="サビの光")
    ed.key("Enter")
    wait_until(ed, "[...document.querySelectorAll('#libGrid .libName')].some(e=>e.textContent==='サビの光')", label="名前の変更")
    _wait_files(ed, adir, ["サビの光.nlmclip"])   # 表示は先に変わり、ファイルの改名はサーバーの応答の後
    t.eq(sorted(p.name for p in adir.glob("*.nlmclip")), ["サビの光.nlmclip"], "ファイル名が変わる（元のファイルは残らない）")
    t.eq(json.loads((adir / "サビの光.nlmclip").read_text(encoding="utf-8"))["name"], "サビの光", "ファイルの中の名前も変わる")
    wait_until(ed, "(e=>e.length===1&&!e[0].dataset.before&&e[0].querySelector('.libName').textContent==='サビの光')([...document.querySelectorAll('#libGrid .libItem')])",
               label="改名後の読み直し")   # 改名後にアセットの一覧を読み直す（表示の名前は応答の前に先に変わる）
    t.eq(lib_items(ed), ["サビの光"], "MEDIAの表示")
    menu(ed, *lib_item_xy(ed, "サビの光"), "クリップを削除")
    wait_until(ed, "document.querySelectorAll('#libGrid .libItem').length===0", label="削除")
    t.eq(list(adir.glob("*.nlmclip")), [], "ファイルが消える")
    t.eq(len(clips(ed)), 2, "NLEのクリップはそのまま")
    t.no_errors()


def test_drop_when_lanes_full(t):
    '''Notesのレーンが全部埋まっている拍へアセットを落とすと置かず、履歴も積まない（空振りのUndoを作らない）'''
    ed = t.ed
    clear_assets(ed)
    ed = open_nle(t, "rich")
    nc = clips(ed, "n")[0]
    menu(ed, *clip_xy(ed, nc), "アセットへ保存")
    wait_until(ed, "document.querySelectorAll('#libGrid .libItem').length===1", label="アセットへ保存")
    for tr in (1, 2):   # Notes 2・Notes 1 の拍0にも空のクリップ（16拍）＝拍0〜16は3本とも埋まる
        menu(ed, scr(ed, 0)["x"] + 30, lane_y(ed, "n", tr), "空のクリップを作成")
        wait_until(ed, f"window._dbgApp.nle().clips.filter(c=>c.lk==='n').length==={tr + 1}", label=f"Notes {3 - tr} に空のクリップ")
    undo0 = ed.js("window._dbgApp.state().undo")
    drag_media(ed, lib_items(ed)[0], *_lane_target(ed, 0, "n", 0))
    ed.wait(0.3)
    t.eq(len(clips(ed, "n")), 3, "置かない")
    t.eq(take_errors(ed, "埋まっています"), 1, "全部埋まっている旨のエラー")
    t.eq(ed.js("window._dbgApp.state().undo"), undo0, "置けなかった時は履歴を積まない（次のCtrl+Zが空振りしない）")
    t.no_errors()

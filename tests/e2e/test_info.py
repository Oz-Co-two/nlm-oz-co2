"""INFO（ノードエディタ）と、曲フォルダの読込まわりの確認"""
import json
from pathlib import Path

from e2e_helpers import bulk_load_rich_map, wait_until

ROOT = Path(__file__).resolve().parents[2]

# INFOのノード（書き出しノード含む）の画面上の四角形
_RECTS_JS = """[...document.querySelectorAll('#infoWorld .iGrp[data-node]')].filter(e=>e.offsetWidth>0)
  .map(e=>{const r=e.getBoundingClientRect();return {id:e.dataset.node,x:r.left,y:r.top,w:r.width,h:r.height}})"""


def _to_info(ed):
    """NLEの上にマウスを置いてTab＝INFOへ"""
    g = ed.js("window._dbgApp.nleScreen(0)")
    ed.move(g["left"] + g["w"] * 0.6, g["lanes"] + 40)
    ed.key("Tab")
    wait_until(ed, "window._dbgApp.view()==='info'", label="INFOへの切替")
    ed.wait(0.3)


def test_info_top_node_visible(t):
    '''INFOを開いた直後、一番上のノードの見出しが見出しバーの下に隠れない（ノード群が枠より高い時は上端に合わせる）'''
    ed = t.fresh('basic')
    _to_info(ed)
    rects = ed.js(_RECTS_JS)
    bar = ed.js("(()=>{const r=document.getElementById('nodeColBar').getBoundingClientRect();return r.bottom})()")
    top = min(r["y"] for r in rects)
    t.ok(top >= bar - 1, f'一番上のノードの上端 {top:.0f} が見出しバーの下端 {bar:.0f} より上（隠れている）')
    t.no_errors()


def test_bulk_import_nodes_do_not_overlap(t):
    '''曲データの一括読込で足される曲情報・カバー・試聴ノードが、既存のノードと重ならない'''
    ed = t.fresh()
    bulk_load_rich_map(ed)
    ig = ed.js("window._dbgApp.infoGraph()")
    t.eq(sorted(n["t"] for n in ig["nodes"].values()), ["cover", "cover", "meta", "meta", "prev", "prev", "set"],
         '既定の4つ＋読み込んだ3つ（既定のノードは消さない仕様）')
    _to_info(ed)
    rects = ed.js(_RECTS_JS)
    over = []
    for i, a in enumerate(rects):
        for b in rects[i + 1:]:
            w = min(a["x"] + a["w"], b["x"] + b["w"]) - max(a["x"], b["x"])
            h = min(a["y"] + a["h"], b["y"] + b["h"]) - max(a["y"], b["y"])
            if w > 2 and h > 2:
                over.append((a["id"], b["id"], round(w), round(h)))
    t.eq(over, [], '重なっているノード（id, id, 幅, 高さ）')
    t.no_errors()


def test_open_folder_keeps_tempo_changes(t):
    '''「フォルダを開く」（.dat から新規）でも、譜面のテンポ変化がテンポパートとして取り込まれる'''
    ed = t.fresh()
    files = [str((ROOT / "tools" / "fixtures" / "rich_map").resolve())]   # フォルダ選択の欄（webkitdirectory）なのでフォルダのパスを渡す
    doc = ed.call("DOM.getDocument")["root"]["nodeId"]
    node = ed.call("DOM.querySelector", nodeId=doc, selector="#folder")["nodeId"]
    ed.call("DOM.setFileInputFiles", files=files, nodeId=node)   # フォルダ選択ダイアログの代わり（change が起きて afterFolder が動く）
    wait_until(ed, "window._dbgApp.state().counts.notes>0", label="フォルダの読込")
    # テンポ変化は譜面を表示した後に取り込む＝入るまで待つ（入らなければ下の確認で失敗する）
    try:
        wait_until(ed, "JSON.parse(window._dbg.rt.buildProjectText()).tempoParts.length>0", label="テンポパートの取り込み")
    except AssertionError:
        pass
    pj = json.loads(ed.js("window._dbg.rt.buildProjectText()"))
    t.eq(pj.get("tempoParts"), [{"beat": 16, "bpm": 150}], '読込後のテンポパート')
    t.eq(ed.js("window._dbgApp.state().BPM"), 120, '基準BPM（Info.dat）')
    t.no_errors()


def _bulk_load_with_audio_first(t):
    """先に音源（basic.wav・BPM120）だけを置いてから、rich_map の「曲データを読み込む」を始める（終わりは待たない＝確認が出るため）"""
    import importlib.util
    ed = t.fresh()
    ed.js("""(async()=>{ const blob=await (await fetch('tools/fixtures/basic.wav',{cache:'no-store'})).blob();
      const file=new File([blob],'basic.wav',{type:'audio/wav'});
      await window._dbg.rt.loadSongFromItem({isMusic:true,name:'basic',songFh:{getFile:async()=>file},info:{_beatsPerMinute:120}},0);
      return true; })()""")
    spec = importlib.util.spec_from_file_location("nlm_make_fixtures", ROOT / "tools" / "fixtures" / "make_fixtures.py")
    mf = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mf)
    js = mf.bulk_load_js("tools/fixtures/rich_map/", list(mf.rich_map_files()), "tools/fixtures/basic.wav")
    ed.js(f"window.__bulkP={js};true", await_promise=False)
    wait_until(ed, "!!document.getElementById('dirtyDlg')", label="BPM変化の取り込みの確認")
    return ed


def _click_dlg(ed, label):
    p = ed.js(f"""(()=>{{const b=[...document.querySelectorAll('#dirtyDlg button')].find(b=>b.textContent==={json.dumps(label)});
      const r=b.getBoundingClientRect();return {{x:r.left+r.width/2,y:r.top+r.height/2}}}})()""")
    ed.click(p["x"], p["y"])
    ed.js("window.__bulkP")   # 読込の完了を待つ
    wait_until(ed, "!document.getElementById('dirtyDlg')", label="確認が閉じる")


def test_bulk_import_with_audio_asks_tempo_yes(t):
    '''音源が既にある所へ「曲データを読み込む」と、BPM変化を取り込むか尋ねる。「取り込む」でテンポパートになる'''
    ed = _bulk_load_with_audio_first(t)
    msg = ed.js("document.querySelector('#dirtyDlg .ddMsg').textContent")
    t.ok('拍16でBPM150' in msg, f'確認の文に変化の地点が無い: {msg}')
    _click_dlg(ed, '取り込む')
    t.eq(ed.js("JSON.parse(window._dbg.rt.buildProjectText()).tempoParts"), [{'beat': 16, 'bpm': 150}], 'テンポパート')
    t.no_errors()


def test_bulk_import_with_audio_asks_tempo_no(t):
    '''同じ確認で「取り込まない」なら、テンポは今のまま（テンポパート無し）で、読込のお知らせに変化の地点が出る'''
    ed = _bulk_load_with_audio_first(t)
    _click_dlg(ed, '取り込まない')
    t.eq(ed.js("JSON.parse(window._dbg.rt.buildProjectText()).tempoParts"), [], 'テンポパート')
    toast = ed.js("(document.getElementById('errToast')||{}).textContent||''")
    t.ok('拍16でBPM150' in toast and '取り込んでいません' in toast, f'お知らせに変化の地点が無い: {toast}')
    t.no_errors()

"""3Dビューの貼り付けで自動に作ったクリップの Undo・取消と、素早く続いた Undo（2026-10-04）。
- 貼り先にクリップが無いと、貼り付けはクリップを自動で作る。以前は先に 'note'/'light' の履歴を取っていたため、
  Undo で貼った物だけが消えて空のクリップが残った。取消（Esc）でもクリップが残り、空振りの履歴も残った
- ノーツの Undo の直後（同じ描画フレーム内）にレーン数の変わる Undo が続くと、今のノーツがレーン番号の違う戻したクリップへ
  書き戻され、ノーツが別のクリップへ移る（消える）ことがあった"""
import json

from e2e_helpers import place_at, state, wait_until
from edit_helpers import open_ed, click_obj, hover_off_grid, undo, redo


def _clips(ed, lk="n"):
    return ed.js(f"window._dbgApp.nle().clips.filter(c=>c.lk==='{lk}').map(c=>[c.beat,c.len,c.track])")


def _project(ed):
    pj = json.loads(ed.js("window._dbg.rt.buildProjectText()"))
    pj.pop("savedAt", None)
    return pj


def _copy_pair_and_go_to(ed, beat):
    """拍3の赤青2個をコピーし、再生ヘッドを beat へ（3Dの上で → を押す。スナップ1/2＝1回で半拍）"""
    click_obj(ed, beat=3, x=1, y=0)
    click_obj(ed, shift=True, beat=3, x=2, y=0)
    wait_until(ed, "window._dbgApp.state().sel===2", label="2個選択")
    hover_off_grid(ed)
    ed.key("c", ctrl=True)
    for _ in range(int(beat * 2)):
        ed.key("ArrowRight")
    wait_until(ed, f"Math.abs(window._dbgApp.state().cur-{beat})<1e-6", label=f"再生ヘッドを拍{beat}へ")


def test_paste_into_empty_region_undo_redo(t):
    '''クリップの無い拍20へ貼り付け→クリップが自動でできる→Enterで確定→Undo1回で貼った物もクリップも消え、Redoで両方戻る'''
    ed = open_ed(t)
    clips0 = _clips(ed)
    _copy_pair_and_go_to(ed, 20)
    u0 = state(ed)["undo"]
    ed.key("v", ctrl=True)
    wait_until(ed, "window._dbgApp.state().counts.notes===10", label="貼り付け")
    clips1 = _clips(ed)
    t.ok(len(clips1) == len(clips0) + 1 and any(c[0] == 20 for c in clips1), f"拍20にクリップが自動でできる: {clips1}")
    ed.key("Enter")
    wait_until(ed, "window._dbgApp.edit().pasteFollow===false", label="確定")
    t.eq(state(ed)["undo"], u0 + 1, "貼り付けの履歴は1つ")
    hover_off_grid(ed)
    undo(ed)
    wait_until(ed, "window._dbgApp.state().counts.notes===8", label="Undo")
    t.eq(_clips(ed), clips0, "Undoで自動のクリップも消える")
    redo(ed)
    wait_until(ed, "window._dbgApp.state().counts.notes===10", label="Redo")
    t.eq(_clips(ed), clips1, "Redoでクリップも戻る")
    t.no_errors()


def test_paste_into_empty_region_cancel(t):
    '''クリップの無い拍20へ貼り付け→Escで取消＝貼った物も自動のクリップも消え、履歴も残らない（取消後の Ctrl+Z が空振りしない）'''
    ed = open_ed(t)
    clips0 = _clips(ed)
    _copy_pair_and_go_to(ed, 20)
    u0 = state(ed)["undo"]
    ed.key("v", ctrl=True)
    wait_until(ed, "window._dbgApp.state().counts.notes===10", label="貼り付け")
    ed.key("Escape")
    wait_until(ed, "window._dbgApp.state().counts.notes===8", label="Escで取消")
    t.eq(_clips(ed), clips0, "取消で自動のクリップも消える")
    t.eq(state(ed)["undo"], u0, "取消した貼り付けの履歴は残らない")
    t.no_errors()


def test_paste_into_existing_clip_cancel_no_history(t):
    '''クリップのある所への貼り付けを Esc で取消しても、空振りの履歴は残らない（以前はノーツ側だけ残っていた）'''
    ed = open_ed(t)
    clips0 = _clips(ed)
    _copy_pair_and_go_to(ed, 0)
    u0 = state(ed)["undo"]
    ed.key("v", ctrl=True)
    wait_until(ed, "window._dbgApp.state().counts.notes===10", label="貼り付け")
    ed.key("Escape")
    wait_until(ed, "window._dbgApp.state().counts.notes===8", label="Escで取消")
    t.eq((_clips(ed), state(ed)["undo"]), (clips0, u0), "クリップも履歴も貼り付け前のまま")
    t.no_errors()


def test_quick_undo_note_then_lane(t):
    '''レーンを足してからノーツを置き、Undo2回を同じ処理の中で続ける＝ノーツもクリップも元どおり（以前はノーツが別のクリップへ移り消えた）'''
    ed = open_ed(t)
    before = _project(ed)
    ed.js("(()=>{ const rt=window._dbg.rt; rt.snapshot('node'); rt.laneAdd('n'); return true; })()")   # NLEの溝の右クリック「レーンを追加」と同じ
    wait_until(ed, "window._dbgApp.nle().lanes.n===4", label="レーンの追加")
    place_at(ed, 3, 2)   # 拍0のクリップ（1段下がった）へノーツを置く＝'note' の履歴
    t.eq(state(ed)["counts"]["notes"], 9, "置いたノーツ")
    ed.js("(()=>{ const rt=window._dbg.rt; rt.undo(); rt.undo(); return true; })()")   # 同じ描画フレームの中で2回
    wait_until(ed, "window._dbgApp.nle().lanes.n===3", label="2回のUndo")
    ed.wait(0.3)   # 描画ごとの書き戻しが走っても崩れないこと
    t.eq(state(ed)["counts"]["notes"], 8, "ノーツの数は元どおり")
    t.eq(_project(ed), before, "プロジェクト内容（ノーツの所属クリップ・レーン）も元どおり")
    t.no_errors()

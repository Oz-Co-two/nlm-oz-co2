"""NLE（レイヤービュー）の操作: テンポパート・クリップ"""
import json

from e2e_helpers import open_fixture, counts, export_files, wait_until


def _tempo(ed):
    return ed.js("JSON.parse(window._dbg.rt.buildProjectText()).tempoParts")


def test_tempo_part_add_edit_undo(t):
    '''テンポ帯をダブルクリックでテンポパートを追加→BPMを手入力→書き出しの bpmEvents に出る→Undoで消える'''
    ed = open_fixture(t, 'basic')
    s = ed.js("window._dbgApp.nleScreen(8)")
    ty = (s['tempo'] + s['marker']) / 2
    ed.click(s['x'], ty); ed.click(s['x'], ty, count=2)
    wait_until(ed, "JSON.parse(window._dbg.rt.buildProjectText()).tempoParts.length===1", label='テンポパートの追加')
    t.eq(_tempo(ed), [{'beat': 8, 'bpm': 120}], '追加直後は今のテンポを引き継ぐ')
    s = ed.js("window._dbgApp.nleScreen(8)")
    ed.click(s['x'] + 3, ty); ed.click(s['x'] + 3, ty, count=2)   # 既存の◆をダブルクリック＝BPMの手入力
    wait_until(ed, "document.activeElement&&document.activeElement.tagName==='INPUT'", label='BPMの入力欄')
    ed.key('a', ctrl=True)
    ed.call('Input.insertText', text='90')
    ed.key('Enter')
    wait_until(ed, "JSON.parse(window._dbg.rt.buildProjectText()).tempoParts[0].bpm===90", label='BPMの変更')
    hard = json.loads(export_files(ed)['HardStandard.dat'])
    t.eq(hard['bpmEvents'], [{'b': 8, 'm': 90}], '書き出しの bpmEvents')
    t.eq(json.loads(export_files(ed)['Info.dat'])['_beatsPerMinute'], 120, 'Info.datの基準BPMは変わらない')
    # Undo: BPM変更→追加 の順に戻る（キーはNLEの上で）
    ed.move(s['x'], s['lanes'] + 40)
    ed.key('z', ctrl=True)
    wait_until(ed, "JSON.parse(window._dbg.rt.buildProjectText()).tempoParts[0]?.bpm===120", label='BPM変更のUndo')
    ed.key('z', ctrl=True)
    wait_until(ed, "JSON.parse(window._dbg.rt.buildProjectText()).tempoParts.length===0", label='追加のUndo')
    t.no_errors()


def test_clip_delete_undo(t):
    '''NLEでクリップをクリックして選びDeleteで消すと中身のノーツも消え、Ctrl+Zで戻る'''
    ed = open_fixture(t, 'basic')
    n = ed.js("window._dbgApp.nleScreen(2)")
    for y in n['notes']:   # クリップのある段（Notes1）を探す: 空の段のクリック＋Deleteは何もしない
        ed.click(n['x'], y + n['laneH'] / 2)
        ed.key('Delete'); ed.wait(0.2)
        if counts(ed)['notes'] == 0:
            break
    t.eq(counts(ed)['notes'], 0, 'クリップ削除後のノーツ数')
    ed.key('z', ctrl=True)
    wait_until(ed, "window._dbgApp.state().counts.notes===8", label='クリップ削除のUndo')
    ed.key('z', ctrl=True, shift=True)
    wait_until(ed, "window._dbgApp.state().counts.notes===0", label='クリップ削除のRedo')
    t.no_errors()

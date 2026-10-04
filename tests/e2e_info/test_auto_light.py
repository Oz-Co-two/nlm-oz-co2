"""自動ライティングの適用（3つの入口 → 確認画面 → 実行 → Undo）"""
import json
import re
from collections import Counter

from e2e_helpers import export_files
from info_helpers import (click_sel, click_text, dialog_text, file_menu, hover_3d, mapcheck_keys, open_fixture, to_info,
                          toast, undo, wait_dialog, wait_dialog_closed, wait_until)


def _lights(ed):
    return ed.js("window._dbgApp.lights()")


def _ev_key(e):
    return (e["beat"], e["et"], e["i"], e.get("f"))


def _lock_lane0(ed):
    """NLEのライトのレーン0の上でLキー（レーンのロック）。本物のキー入力"""
    g = ed.js("window._dbgApp.nleScreen(0)")
    ed.move(g["left"] + g["w"] * 0.6, g["lights"][0] + g["laneH"] / 2)
    ed.key("l")
    wait_until(ed, "window._dbgApp.lights().locks.length===1", label="レーンのロック")


def _check_applied(t, ed, before, n_added):
    """適用後の共通確認: レーンが1本増え、全難易度に自動ライトのクリップが入り、既存のライトはそのまま残る"""
    after = _lights(ed)
    t.eq(after["lanes"], before["lanes"] + 1, 'ライトのレーン数')
    cur_clips = sorted(after["clips"], key=lambda c: c["track"])
    t.eq(cur_clips[0]["track"], 0, '自動ライトのクリップは一番上のレーン')
    t.eq(cur_clips[0]["n"], n_added, '自動ライトのクリップのライト数（確認画面の数）')
    t.eq([(c["label"], c["track"], c["n"]) for c in cur_clips[1:]],
         [(c["label"], c["track"] + 1, c["n"]) for c in sorted(before["clips"], key=lambda c: c["track"])],
         '既存のクリップは1段下がるだけ')
    for k, b in before["diffs"].items():   # 中身のある全難易度に同じクリップが入る
        a = after["diffs"][k]
        t.eq(a["notes"], b["notes"], f'{k} のノーツは変わらない')
        t.eq(a["lights"], b["lights"] + n_added, f'{k} のライト数 = 元 + 追加')
        t.eq(sum(1 for c in a["clips"] if c["track"] == 0 and c["n"] == n_added), 1, f'{k} に自動ライトのクリップが1つ（一番上）')
        t.eq(sorted((c["track"] + 1, c["n"]) for c in b["clips"]),
             sorted((c["track"], c["n"]) for c in a["clips"] if c["track"] != 0), f'{k} の既存クリップは1段下がる')
    old, new = Counter(map(_ev_key, before["events"])), Counter(map(_ev_key, after["events"]))
    t.ok(not (old - new), f'既存のライトが消えた/変わった: {old - new}')
    t.eq(sum(new.values()), sum(old.values()) + n_added, '今の難易度のライト総数')
    return after


def _undo_restores(t, ed, before):
    undo(ed)
    after = _lights(ed)
    t.eq(after["lanes"], before["lanes"], 'Undo後のレーン数')
    t.eq(after["locks"], before["locks"], 'Undo後のロック')
    t.eq(after["clips"], before["clips"], 'Undo後のクリップ')
    cur = ed.js("window._dbgApp.state().diff").lower()   # 今の難易度の projDiffs は次に退避されるまで古い＝画面外の難易度だけ比べる（今の分は上のクリップ・ライトで確認済み）
    t.eq({k: v for k, v in after["diffs"].items() if k != cur}, {k: v for k, v in before["diffs"].items() if k != cur}, 'Undo後の画面外の難易度')
    t.eq(Counter(map(_ev_key, after["events"])), Counter(map(_ev_key, before["events"])), 'Undo後のライト')


def _n_from_dialog(txt):
    m = re.search(r'ライト (\d+)個', txt)
    assert m, f'確認画面にライト数が無い: {txt}'
    return int(m.group(1))


def test_auto_light_file_menu(t):
    '''rich: ファイルメニュー→確認画面→作成。レーン+1・全難易度に同じクリップ・既存ライトは残り・ロックは1段下がり、1回のUndoで全部戻る'''
    ed = open_fixture(t, 'rich')
    _lock_lane0(ed)
    before = _lights(ed)
    t.eq(before["locks"], ['l0'], '準備: 既存のクリップのレーンをロック')
    u0 = ed.js("window._dbgApp.state().undo")
    file_menu(ed, 'autolight')
    txt = wait_dialog(ed)
    t.ok('元にする難易度: Expert' in txt and '追加する難易度: Hard / Expert' in txt, f'確認画面の中身: {txt}')
    n = _n_from_dialog(txt)
    t.eq(_lights(ed), before, '確認画面を出しただけでは何も変わらない')
    click_text(ed, '#dirtyDlg button', '作成')
    wait_dialog_closed(ed)
    after = _check_applied(t, ed, before, n)
    t.eq(after["locks"], ['l1'], 'ロックは既存のクリップのレーンについて1段下がる（自動ライトのレーンはロックされない）')
    t.ok('自動ライトを追加しました' in toast(ed), f'完了のお知らせ: {toast(ed)}')
    t.eq(ed.js("window._dbgApp.state().undo"), u0 + 1, '履歴は1つだけ増える')
    t.ok(all('insufficientLight' not in v for v in mapcheck_keys(ed).values()), '譜面チェックのライト不足が消える')
    _undo_restores(t, ed, before)
    t.ok(all('insufficientLight' in v for v in mapcheck_keys(ed).values()), 'Undo後はライト不足に戻る')
    files = export_files(ed)   # 書き出しにも元の数で出る（画面外の難易度も含めて戻っている）
    t.eq({k: len(json.loads(v)['basicBeatmapEvents']) for k, v in files.items() if k.endswith('Standard.dat')},
         {'HardStandard.dat': 3, 'ExpertStandard.dat': 12}, 'Undo後の書き出しのライト数')
    t.no_errors()


def test_auto_light_cancel(t):
    '''確認画面で「キャンセル」と Esc では何も変わらない（履歴も増えない）'''
    ed = open_fixture(t, 'rich')
    before, u0 = _lights(ed), ed.js("window._dbgApp.state().undo")
    file_menu(ed, 'autolight')
    wait_dialog(ed)
    click_text(ed, '#dirtyDlg button', 'キャンセル')
    wait_dialog_closed(ed)
    file_menu(ed, 'autolight')
    wait_dialog(ed)
    ed.key('Escape')
    wait_dialog_closed(ed)
    t.eq(_lights(ed), before, 'ライトの状況')
    t.eq(ed.js("window._dbgApp.state().undo"), u0, '履歴')
    t.no_errors()


def test_auto_light_toolbar(t):
    '''LIGHTINGのツールバー「自動ライト」から確認画面→Enterで作成。全難易度に入りUndoで戻る'''
    ed = open_fixture(t, 'rich')
    before = _lights(ed)
    hover_3d(ed)
    ed.key('Tab')   # NOTES→LIGHTING
    wait_until(ed, "window._dbgApp.state().lightMode", label='LIGHTING表示')
    for _ in range(3):   # モード切替の直後はツールバーの配置が動いていることがある＝出なければ押し直す
        ed.wait(0.3)
        click_sel(ed, '#tbAutoLight', '自動ライトのボタン')
        ed.wait(0.3)
        if dialog_text(ed):
            break
    n = _n_from_dialog(wait_dialog(ed))
    ed.key('Enter')
    wait_dialog_closed(ed)
    _check_applied(t, ed, before, n)
    _undo_restores(t, ed, before)
    t.no_errors()


def test_auto_light_from_mapcheck(t):
    '''譜面チェックのライト不足の項目の「💡 自動ライティング…」から作成すると、チェックがやり直されてボタンが消える'''
    ed = open_fixture(t, 'rich')
    before = _lights(ed)
    to_info(ed)
    click_sel(ed, '#iMapCheck', '譜面チェックのボタン')
    done = ("(()=>{const p=document.getElementById('mcPanel');return !!p&&p.style.display!=='none'"
            "&&!p.querySelector('.mcRerun').disabled&&p.querySelector('.mcBody').children.length>0})()")
    wait_until(ed, done, timeout=20, label='チェック結果')
    t.eq(ed.js("document.querySelectorAll('#mcPanel .mcFix[data-fix=autolight]').length"), 2,
         '各難易度（Hard・Expert）のライト不足の項目に自動ライティングのボタン')
    click_sel(ed, '#mcPanel .mcFix[data-fix=autolight]', '💡 自動ライティング…')
    n = _n_from_dialog(wait_dialog(ed))
    click_text(ed, '#dirtyDlg button', '作成')
    wait_dialog_closed(ed)
    _check_applied(t, ed, before, n)
    wait_until(ed, done, timeout=20, label='チェックのやり直し')
    wait_until(ed, "document.querySelectorAll('#mcPanel .mcFix[data-fix=autolight]').length===0", timeout=20,
               label='ライト不足の項目（とボタン）が消える')
    t.no_errors()


def test_auto_light_basic_no_lights(t):
    '''basic（ライト無し・Hardだけ）: 作成でHardにだけライトが入り、ノーツは変わらず、Undoで空に戻る'''
    ed = open_fixture(t, 'basic')
    before = _lights(ed)
    t.eq(before["events"], [], '準備: ライトは無い')
    file_menu(ed, 'autolight')
    txt = wait_dialog(ed)
    t.ok('追加する難易度: Hard' in txt and 'Expert' not in txt, f'対象はHardだけ: {txt}')
    n = _n_from_dialog(txt)
    click_text(ed, '#dirtyDlg button', '作成')
    wait_dialog_closed(ed)
    a = _lights(ed)
    t.eq(len(a["events"]), n, 'ライトの数')
    t.eq(ed.js("window._dbgApp.state().counts.notes"), 8, 'ノーツは変わらない')
    t.eq(a["lanes"], before["lanes"] + 1, 'レーン数')
    _undo_restores(t, ed, before)
    t.no_errors()


def test_auto_light_no_chart(t):
    '''譜面が無い（新規の空の状態）で実行すると、確認画面は出ずにお知らせだけ出る'''
    ed = open_fixture(t)
    file_menu(ed, 'autolight')
    wait_until(ed, "(()=>{const e=document.getElementById('errToast');return !!e&&e.style.display!=='none'&&e.textContent.length>0})()",
               label='お知らせ')
    t.ok(dialog_text(ed) is None, '確認画面は出ない')
    msg = toast(ed)
    t.ok('ライトを作る譜面がありません' in msg or 'ノーツのある難易度がありません' in msg, f'お知らせ: {msg}')
    errs = ed.errors()   # 利用者へのお知らせは console.error にも出る＝それ以外のエラーが無いこと
    t.ok(all(('ライトを作る譜面がありません' in e or 'ノーツのある難易度がありません' in e) for e in errs), f'想定外のエラー: {errs}')

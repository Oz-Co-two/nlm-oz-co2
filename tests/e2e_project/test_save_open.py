"""保存（Ctrl+S・メニュー・別名・コピー）・開く・新規・未保存の3択。
保存/開くのファイル選択はページ内で偽物に差し替え（project_helpers.install_fake_fs）、アプリ本来の保存・読込の処理を通す。"""
import json

from e2e_helpers import counts, diff_counts_from_project, dirty, hover_3d, open_fixture, place_at, project, wait_until, state, RICH
from project_helpers import (dialog_buttons, dialog_click, dialog_open, fake, file_menu, forget_errors, install_fake_fs, queue_open,
                             set_flag, strip_saved_at, toast, wait_dialog)

IDB_GET = """new Promise(res=>{const r=indexedDB.open('nodemapper',1);r.onerror=()=>res(null);
  r.onsuccess=()=>{const q=r.result.transaction('kv').objectStore('kv').get(%s);q.onsuccess=()=>res(q.result||null);q.onerror=()=>res(null);};})"""


def _setup(t, fx='basic'):
    ed = open_fixture(t, fx)
    install_fake_fs(ed)
    ed.js("document.getElementById('errToast').style.display='none'")   # 読込時の「音源を配置しました」を消す
    return ed


def _ctrl_s(ed):
    hover_3d(ed)
    ed.key('s', ctrl=True)


def _wait_writes(ed, n):
    wait_until(ed, f"__fake.writes.length>={n}", label=f'{n}回目の書き込み')
    wait_until(ed, "window._dbgApp.dirty().lamp===false", label='保存後に未保存ランプが消える')


def _dirty_edit(ed, x=1, y=1):
    place_at(ed, x, y)
    wait_until(ed, "window._dbgApp.dirty().lamp===true", label='編集後に未保存')


def test_save_ctrl_s_first(t):
    '''Ctrl+S（初回）: 保存先ピッカーが project.nlmf で開き、アプリの保存内容が書かれ、未保存ランプが消える'''
    ed = _setup(t)
    _dirty_edit(ed)
    _ctrl_s(ed)
    _wait_writes(ed, 1)
    f = fake(ed)
    t.eq(len(f['saveCalls']), 1, '保存先ピッカーの呼び出し回数')
    t.eq(f['saveCalls'][0]['suggestedName'], 'project.nlmf', '既定のファイル名')
    t.eq(f['writes'][0]['name'], 'a.nlmf', '書き込み先')
    saved = strip_saved_at(f['writes'][0]['text'])
    t.eq(saved['format'], 'nlmf', '形式')
    t.eq(saved, project(ed), '書かれた中身 = 今のプロジェクト内容')
    t.eq(diff_counts_from_project(saved)['HardStandard.dat']['notes'], 9, '書かれたノーツ数（8+編集の1）')
    t.eq(dirty(ed)['same'], True, '保存時点と同じ内容')
    t.no_errors()


def test_save_second_overwrites_and_backup(t):
    '''2回目のCtrl+Sはピッカーを出さず同じ保存先へ上書きし、上書き前の内容がバックアップ(IndexedDB bak1)に残る'''
    ed = _setup(t)
    _dirty_edit(ed, 1, 1)
    _ctrl_s(ed)
    _wait_writes(ed, 1)
    first = fake(ed)['writes'][0]['text']
    _dirty_edit(ed, 2, 1)
    _ctrl_s(ed)
    _wait_writes(ed, 2)
    f = fake(ed)
    t.eq(len(f['saveCalls']), 1, 'ピッカーは初回だけ')
    t.eq([w['name'] for w in f['writes']], ['a.nlmf', 'a.nlmf'], '同じ保存先へ2回書く')
    second = f['writes'][1]['text']
    t.eq(diff_counts_from_project(strip_saved_at(second))['HardStandard.dat']['notes'], 10, '2回目の中身は編集が足されている')
    bak = ed.js(IDB_GET % json.dumps('projBak1:a.nlmf'))
    t.ok(bak is not None, 'バックアップ(bak1)が作られている')
    t.eq(bak['text'], first, 'bak1 = 上書き前（1回目）の内容')
    t.no_errors()


def test_save_as_changes_destination(t):
    '''別名保存（メニュー）は毎回ピッカーを開き、以後のCtrl+Sは新しい保存先へ書く。※Ctrl+Shift+SはヘッドレスEdgeがブラウザ側で奪うためキーでは試せない'''
    ed = _setup(t)
    _dirty_edit(ed)
    _ctrl_s(ed)
    _wait_writes(ed, 1)
    file_menu(ed, 'saveas')
    wait_until(ed, "__fake.saveCalls.length===2", label='別名保存でピッカーが開く')
    wait_until(ed, "__fake.writes.length===2", label='別名保存の書き込み')
    _dirty_edit(ed, 2, 1)
    _ctrl_s(ed)
    _wait_writes(ed, 3)
    f = fake(ed)
    t.eq([w['name'] for w in f['writes']], ['a.nlmf', 'b.nlmf', 'b.nlmf'], '書き込み先の遷移')
    t.eq(len(f['saveCalls']), 2, 'ピッカー回数')
    t.no_errors()


def test_save_menu_items(t):
    '''ファイルメニューの「保存」「名前を付けて保存」がショートカットと同じ動き（保存→上書き→別名）'''
    ed = _setup(t)
    _dirty_edit(ed)
    file_menu(ed, 'save')
    _wait_writes(ed, 1)
    _dirty_edit(ed, 2, 1)
    file_menu(ed, 'save')
    _wait_writes(ed, 2)
    t.eq(len(fake(ed)['saveCalls']), 1, '「保存」は2回目からピッカー無し')
    file_menu(ed, 'saveas')
    wait_until(ed, "__fake.writes.length===3", label='別名保存')
    f = fake(ed)
    t.eq([w['name'] for w in f['writes']], ['a.nlmf', 'a.nlmf', 'b.nlmf'], '書き込み先')
    t.no_errors()


def test_save_cancel_keeps_dirty(t):
    '''保存先ピッカーをキャンセルすると何も書かれず、未保存のまま（エラー表示も出ない）'''
    ed = _setup(t)
    _dirty_edit(ed)
    set_flag(ed, 'cancelSave', True)
    _ctrl_s(ed)
    wait_until(ed, "__fake.saveCalls.length===1", label='ピッカーが呼ばれる')
    ed.wait(0.3)
    t.eq(fake(ed)['writes'], [], '書き込み無し')
    t.eq(dirty(ed)['lamp'], True, '未保存のまま')
    t.eq(toast(ed), '', 'トースト（エラー）なし')
    t.no_errors()


def test_save_copy_does_not_change_state(t):
    '''「コピーを保存」はproject_copy.nlmfへ書くが、未保存状態や保存先を変えない（次のCtrl+Sは通常どおりピッカー）'''
    ed = _setup(t)
    _dirty_edit(ed)
    file_menu(ed, 'savecopy')
    wait_until(ed, "__fake.writes.length===1", label='コピーの書き込み')
    f = fake(ed)
    t.eq(f['saveCalls'][0]['suggestedName'], 'project_copy.nlmf', 'コピーの既定名')
    t.eq(strip_saved_at(f['writes'][0]['text']), project(ed), 'コピーの中身 = 今の内容')
    t.eq(dirty(ed)['lamp'], True, 'コピー保存では未保存のまま')
    _ctrl_s(ed)
    wait_until(ed, "__fake.saveCalls.length===2", label='Ctrl+Sは保存先未設定としてピッカーを開く')
    _wait_writes(ed, 2)
    t.no_errors()


def test_save_open_roundtrip(t):
    '''richを保存→開き直したページで「開く」を通すと、保存した状態（2難易度・テンポ・曲情報）に戻る。ランプは消えている'''
    ed = _setup(t, 'rich')
    _ctrl_s(ed)
    wait_until(ed, "__fake.writes.length>=1", label='保存')
    text = fake(ed)['writes'][0]['text']
    want = strip_saved_at(text)
    ed = t.fresh('basic')
    install_fake_fs(ed)
    t.eq(counts(ed)['notes'], 8, '開く前はbasic')
    queue_open(ed, 'rich.nlmf', text)
    hover_3d(ed)
    ed.key('o', ctrl=True)
    wait_until(ed, "window._dbgApp.state().counts.notes===7", label='開いた中身が反映される')
    ed.wait(0.3)
    t.eq(len(fake(ed)['openCalls']), 1, '開くピッカー')
    t.ok(fake(ed)['openCalls'][0]['types'][0]['accept']['application/octet-stream'].count('.nlmf') == 1, '.nlmf を受け付ける')
    t.eq(counts(ed), RICH['HardStandard.dat'], '現在の難易度の数')
    t.eq(project(ed), want, '開いた後の保存内容 = 保存した内容')
    t.eq(diff_counts_from_project(project(ed)), RICH, '難易度ごとの数')
    wait_until(ed, "window._dbgApp.dirty().lamp===false", timeout=5, label='開き終えたら未保存でない')   # 中身が反映された直後〜基準を取り直すまでは点いていることがある
    t.no_errors()


TL = "(()=>{const a=window._dbgApp,w=a.tl();return {beat:a.state().cur,span:w.span,b0:w.b0}})()"


def test_save_restores_view(t):
    '''保存すると再生位置とNLEのズーム・表示位置も記録し、開くとその状態に戻る。再生位置・ズームを動かしただけでは未保存にならない。
    記録の無い旧ファイルは先頭から（ズームはそのまま）'''
    ed = _setup(t)
    s = ed.js("window._dbgApp.nleScreen(0)")
    x, y = s['x'] + 0.5, s['notes'][0] + s['laneH'] * 0.5
    for _ in range(3):
        ed.wheel(x, y, -100, ctrl=True)   # 拍0を支点に拡大（32→16.384拍）
    hover_3d(ed)
    for _ in range(24):
        ed.key('ArrowRight')   # 1/2拍ずつ12拍目へ（中央を越えたので窓も送られる）
    wait_until(ed, "window._dbgApp.state().cur===12", label='再生位置を拍12へ')
    view = ed.js(TL)
    t.ok(abs(view['span'] - 16.384) < 1e-9 and view['b0'] > 0, f'拡大して送られた窓: {view}')
    ed.wait(0.7)   # 判定は操作が落ち着いて0.5秒後
    t.eq(dirty(ed)['lamp'], False, '再生位置・ズームを動かしただけでは未保存にならない')
    _ctrl_s(ed)
    wait_until(ed, "__fake.writes.length>=1", label='保存')
    text = fake(ed)['writes'][0]['text']
    t.eq(json.loads(text)['view'], view, '保存した中身に再生位置・ズーム・表示位置')
    # 別の位置・ズームにしてから開く
    ed.key('ArrowLeft', ctrl=True)
    wait_until(ed, "window._dbgApp.state().cur===0", label='先頭へ')
    for _ in range(2):
        ed.wheel(x, y, 100, ctrl=True)
    t.ok(ed.js(TL) != view, '開く前は別の状態')
    queue_open(ed, 'a.nlmf', text)
    ed.key('o', ctrl=True)
    wait_until(ed, "__fake.openCalls.length===1&&window._dbgApp.state().cur===12", label='開くと保存時の再生位置')
    t.eq(ed.js(TL), view, '開いた後の再生位置・ズーム・表示位置')
    wait_until(ed, "window._dbgApp.dirty().lamp===false", timeout=5, label='開き終えたら未保存でない')
    # 記録の無い旧ファイル（この機能より前に保存したもの）
    old = json.loads(text)
    old.pop('view')
    queue_open(ed, 'old.nlmf', json.dumps(old))
    ed.key('o', ctrl=True)
    wait_until(ed, "__fake.openCalls.length===2&&window._dbgApp.state().cur===0", label='旧ファイルは先頭から')
    t.eq(ed.js(TL), {'beat': 0, 'span': view['span'], 'b0': 0}, '旧ファイル: 先頭を表示・ズームはそのまま')
    # 壊れた値は使わない（ファイル由来の値）
    bad = dict(json.loads(text), view={'beat': -5, 'span': 'x', 'b0': None})
    queue_open(ed, 'bad.nlmf', json.dumps(bad))
    ed.key('o', ctrl=True)
    wait_until(ed, "__fake.openCalls.length===3", label='壊れた値のファイルを開く')
    wait_until(ed, "window._dbgApp.dirty().lamp===false", timeout=5, label='開き終える')
    t.eq(ed.js(TL), {'beat': 0, 'span': view['span'], 'b0': 0}, '壊れた値: 再生位置は0へ・ズームはそのまま')
    # 新規作成は、開いていたファイルの表示位置を残さない
    queue_open(ed, 'a.nlmf', text)
    ed.key('o', ctrl=True)
    wait_until(ed, "__fake.openCalls.length===4&&window._dbgApp.state().cur===12", label='もう一度開く')
    wait_until(ed, "window._dbgApp.dirty().lamp===false", timeout=5, label='開き終える')
    file_menu(ed, 'new')
    wait_until(ed, "window._dbgApp.state().cur===0", label='新規作成')
    t.eq(ed.js(TL), {'beat': 0, 'span': view['span'], 'b0': 0}, '新規作成: 先頭を表示・ズームはそのまま')
    t.no_errors()


def test_open_far_view_keeps_3d_camera(t):
    '''保存時の再生位置が曲末の暫定値（音源の読込前＝128拍）より後ろのファイルを開いても、3Dのカメラは再生ヘッドの所に留まる。
    以前はカメラの可動範囲（曲頭−8拍〜曲末＋8拍）の外として押し出され、位置と注視点が同じ奥行き（真横向き）になって何も映らなかった（2026-10-09）'''
    ed = _setup(t)
    c0 = ed.js("window._dbgApp.cam()")
    pj = json.loads(ed.js("window._dbg.rt.buildProjectText()"))
    pj['view'] = {'beat': 200, 'span': 32, 'b0': 184}
    queue_open(ed, 'far.nlmf', json.dumps(pj))
    hover_3d(ed)
    ed.key('o', ctrl=True)
    wait_until(ed, "__fake.openCalls.length===1&&window._dbgApp.state().cur===200", label='拍200の位置で開く')
    wait_until(ed, "window._dbgApp.dirty().lamp===false", timeout=5, label='開き終える')
    ed.wait(0.2)   # 描画のたびに可動範囲へ寄せる＝数フレーム回してから見る
    c1 = ed.js("window._dbgApp.cam()")
    t.eq(state(ed)['camMode'], 'place', '配置モードのまま')
    t.ok(all(abs(a - b) < 1e-6 for a, b in zip(c1['pos'] + c1['tgt'], c0['pos'] + c0['tgt'])),
         f'カメラは再生ヘッドに対して開く前と同じ位置・向き（前 {c0} / 後 {c1}）')
    t.no_errors()


def test_open_then_save_overwrites_opened_file(t):
    '''開いたファイルへのCtrl+Sはピッカー無しでそのファイルへ書く'''
    ed = _setup(t, 'basic')
    _ctrl_s(ed)
    wait_until(ed, "__fake.writes.length>=1", label='保存')
    text = fake(ed)['writes'][0]['text']
    ed = t.fresh('basic')
    install_fake_fs(ed)
    queue_open(ed, 'opened.nlmf', text)
    hover_3d(ed)
    ed.key('o', ctrl=True)
    wait_until(ed, "__fake.openCalls.length===1&&__fake.handles.length>=1", label='開く')
    ed.wait(0.4)
    _dirty_edit(ed, 3, 1)
    _ctrl_s(ed)
    _wait_writes(ed, 1)
    f = fake(ed)
    t.eq(len(f['saveCalls']), 0, '保存ピッカーは出ない')
    t.eq(f['writes'][0]['name'], 'opened.nlmf', '開いたファイルへ書く')
    t.no_errors()


def test_open_invalid_files(t):
    '''nlmf形式でないファイル・壊れたJSONを開くと、エラー表示を出して今の内容は変わらない'''
    ed = _setup(t)
    before = project(ed)
    queue_open(ed, 'bad.nlmf', json.dumps({'format': 'other'}))
    hover_3d(ed)
    ed.key('o', ctrl=True)
    wait_until(ed, "document.getElementById('errToast').style.display==='block'", label='形式エラーの表示')
    t.ok('nlmf形式ではありません' in toast(ed), f'形式エラーの文言: {toast(ed)}')
    queue_open(ed, 'broken.nlmf', '{ここは壊れたJSON')
    ed.key('o', ctrl=True)
    wait_until(ed, "document.getElementById('errToast').textContent.includes('読込失敗')", label='壊れたJSONのエラー表示')
    t.eq(project(ed), before, '内容は変わらない')
    t.eq(dirty(ed)['lamp'], False, '未保存にもならない')
    forget_errors(ed, '形式ではありません')
    forget_errors(ed, '読込失敗')
    t.no_errors()


def test_open_cancel_picker(t):
    '''開くのピッカーをキャンセルしても何も起きない'''
    ed = _setup(t)
    before = project(ed)
    set_flag(ed, 'cancelOpen', True)
    hover_3d(ed)
    ed.key('o', ctrl=True)
    wait_until(ed, "__fake.openCalls.length===1", label='ピッカー呼び出し')
    ed.wait(0.2)
    t.eq(project(ed), before, '内容は変わらない')
    t.eq(toast(ed), '', 'エラー表示なし')
    t.no_errors()


# ---- 未保存の3択 ----
def _saved_text(ed):
    return fake(ed)['writes'][0]['text']


def test_open_clean_has_no_dialog(t):
    '''未保存でなければ「開く」で確認ダイアログは出ず、そのままピッカーが開く'''
    ed = _setup(t)
    set_flag(ed, 'cancelOpen', True)
    file_menu(ed, 'open')
    wait_until(ed, "__fake.openCalls.length===1", label='ピッカーが直接開く')
    t.eq(dialog_open(ed), False, 'ダイアログは出ない')
    t.no_errors()


def test_dialog_three_choices_shown(t):
    '''未保存で「開く」を選ぶと3択（保存して続行／保存せずに続行／キャンセル）が出て、ピッカーはまだ開かない'''
    ed = _setup(t)
    _dirty_edit(ed)
    file_menu(ed, 'open')
    wait_dialog(ed)
    t.eq(dialog_buttons(ed), ['保存して続行', '保存せずに続行', 'キャンセル'], '3つのボタン')
    t.eq(len(fake(ed)['openCalls']), 0, 'ピッカーは未呼び出し')
    t.no_errors()


def test_dialog_cancel_button_and_esc(t):
    '''3択のキャンセル／Escは何も変えずに閉じる（編集は残り、ピッカーも保存も起きない）'''
    ed = _setup(t)
    _dirty_edit(ed)
    n = counts(ed)['notes']
    file_menu(ed, 'open')
    wait_dialog(ed)
    dialog_click(ed, 2)
    wait_until(ed, "!document.getElementById('dirtyDlgBg')", label='キャンセルで閉じる')
    # Esc
    file_menu(ed, 'new')
    wait_dialog(ed)
    ed.key('Escape')
    wait_until(ed, "!document.getElementById('dirtyDlgBg')", label='Escで閉じる')
    f = fake(ed)
    t.eq((len(f['openCalls']), len(f['saveCalls']), f['writes']), (0, 0, []), 'ピッカー・保存なし')
    t.eq(counts(ed)['notes'], n, '編集は残っている')
    t.eq(dirty(ed)['lamp'], True, '未保存のまま')
    t.no_errors()


def test_open_dirty_discard(t):
    '''未保存で「開く」→「保存せずに続行」: 保存はせずピッカーが開き、開いた中身で置き換わる（編集は捨てられる）'''
    ed = _setup(t, 'rich')
    _ctrl_s(ed)
    wait_until(ed, "__fake.writes.length>=1", label='保存')
    text = _saved_text(ed)
    _dirty_edit(ed, 3, 1)
    t.eq(counts(ed)['notes'], 8, '編集後（rich Hard 7+1）')
    queue_open(ed, 'rich.nlmf', text)
    file_menu(ed, 'open')
    wait_dialog(ed)
    dialog_click(ed, 1)
    wait_until(ed, "__fake.openCalls.length===1", label='ピッカーが開く')
    wait_until(ed, "window._dbgApp.state().counts.notes===7", label='開いた中身へ置き換わる')
    ed.wait(0.3)
    f = fake(ed)
    t.eq(len(f['writes']), 1, '保存は追加で起きていない（最初の1回のみ）')
    wait_until(ed, "window._dbgApp.dirty().lamp===false", timeout=3, label='開いた後は未保存でない')
    t.no_errors()


def test_open_dirty_save_and_continue(t):
    '''未保存で「開く」→「保存して続行」: 先に今の内容を保存してから、ピッカーが開く'''
    ed = _setup(t, 'rich')
    _ctrl_s(ed)
    wait_until(ed, "__fake.writes.length>=1", label='最初の保存')
    text = _saved_text(ed)
    _dirty_edit(ed, 3, 1)
    queue_open(ed, 'rich.nlmf', text)
    file_menu(ed, 'open')
    wait_dialog(ed)
    dialog_click(ed, 0)
    wait_until(ed, "__fake.openCalls.length===1", label='保存後にピッカーが開く')
    f = fake(ed)
    t.eq(len(f['writes']), 2, '続行前に保存された')
    t.eq(diff_counts_from_project(strip_saved_at(f['writes'][1]['text']))['HardStandard.dat']['notes'], 8, '保存された中身は編集後のもの')
    t.eq(len(f['saveCalls']), 1, '保存先は最初のものを使う（ピッカーは増えない）')
    t.no_errors()


def test_dialog_save_cancelled_stays(t):
    '''3択で「保存して続行」を選んで保存先ピッカーをキャンセルすると、ダイアログに戻り続行されない（新規にならない）'''
    ed = _setup(t)
    _dirty_edit(ed)
    n = counts(ed)['notes']
    set_flag(ed, 'cancelSave', True)
    file_menu(ed, 'new')
    wait_dialog(ed)
    dialog_click(ed, 0)
    wait_until(ed, "__fake.saveCalls.length===1", label='保存ピッカーが呼ばれる')
    wait_until(ed, "document.getElementById('dirtyDlgBg')&&document.getElementById('dirtyDlgBg').style.display!=='none'", label='ダイアログへ戻る')
    t.eq(counts(ed)['notes'], n, '新規にはなっていない')
    t.eq(dirty(ed)['lamp'], True, '未保存のまま')
    dialog_click(ed, 2)   # 後始末
    wait_until(ed, "!document.getElementById('dirtyDlgBg')", label='閉じる')
    t.no_errors()


def test_new_clean(t):
    '''未保存でなければ「新規」は確認なしで空のプロジェクトにする（ノーツ0・未保存でない）'''
    ed = _setup(t)
    file_menu(ed, 'new')
    wait_until(ed, "window._dbgApp.state().counts.notes===0", label='新規で空になる')
    t.eq(dialog_open(ed), False, 'ダイアログなし')
    t.eq(dirty(ed)['lamp'], False, '新規直後は未保存でない')
    t.eq(project(ed)['format'], 'nlmf', '新規でも保存内容は組み立てられる')
    t.no_errors()


def test_new_dirty_discard(t):
    '''未保存で「新規」→「保存せずに続行」: 保存せずに空になる'''
    ed = _setup(t)
    _dirty_edit(ed)
    file_menu(ed, 'new')
    wait_dialog(ed)
    dialog_click(ed, 1)
    wait_until(ed, "window._dbgApp.state().counts.notes===0", label='空になる')
    f = fake(ed)
    t.eq((f['writes'], len(f['saveCalls'])), ([], 0), '保存は起きない')
    t.eq(dirty(ed)['lamp'], False, '新規直後は未保存でない')
    t.no_errors()


def test_new_dirty_save_first(t):
    '''未保存で「新規」→「保存して続行」: 編集を保存してから空になる。保存内容に編集が入っている'''
    ed = _setup(t)
    _dirty_edit(ed)
    file_menu(ed, 'new')
    wait_dialog(ed)
    dialog_click(ed, 0)
    wait_until(ed, "window._dbgApp.state().counts.notes===0", label='保存後に空になる')
    f = fake(ed)
    t.eq(len(f['writes']), 1, '保存された')
    t.eq(diff_counts_from_project(strip_saved_at(f['writes'][0]['text']))['HardStandard.dat']['notes'], 9, '保存内容は編集後（8+1）')
    t.eq(dirty(ed)['lamp'], False, '未保存でない')
    t.no_errors()


def test_new_forgets_save_destination(t):
    '''新規にした後のCtrl+Sは、前のファイルへ上書きせず保存先ピッカーを開く（元ファイルを上書きする事故の防止）'''
    ed = _setup(t)
    _dirty_edit(ed)
    _ctrl_s(ed)
    _wait_writes(ed, 1)
    file_menu(ed, 'new')
    wait_until(ed, "window._dbgApp.state().counts.notes===0", label='新規')
    place_at(ed, 1, 0)
    wait_until(ed, "window._dbgApp.dirty().lamp===true", label='新規後に編集')
    _ctrl_s(ed)
    wait_until(ed, "__fake.saveCalls.length===2", label='ピッカーが開く')
    _wait_writes(ed, 2)
    f = fake(ed)
    t.eq([w['name'] for w in f['writes']], ['a.nlmf', 'b.nlmf'], '別のファイルへ書く')
    t.eq(diff_counts_from_project(strip_saved_at(f['writes'][1]['text']))['HardStandard.dat']['notes'], 1, '新規後の内容（1個）')
    t.no_errors()


def test_new_resets_history(t):
    '''新規の直後は履歴が空で、Ctrl+Zを押しても例外が出ず空のまま'''
    ed = _setup(t)
    _dirty_edit(ed)
    file_menu(ed, 'new')
    wait_dialog(ed)
    dialog_click(ed, 1)
    wait_until(ed, "window._dbgApp.state().counts.notes===0", label='新規')
    t.eq(state(ed)['undo'], 0, '履歴は空')
    hover_3d(ed)
    ed.key('z', ctrl=True)
    ed.wait(0.3)
    t.eq(counts(ed)['notes'], 0, 'Undoしても空のまま')
    t.no_errors()

"""3Dビュー・ライト・再生まわりの細かい所:
壁の高さ・奥行きのつまみ（S）／ライトのカラーパイ（C）／直前ノーツ表示（H）と同じ向きの警告（ランプ）／
譜面チェックの拍からのジャンプ／再生・停止・1コマ送り・先頭/末尾・マーカー・メトロノーム／PREVIEWの表示切替。

素材 basic: BPM120・音源16秒（＝32拍）・ノーツは全部↓（赤: 拍1(1,0)・拍3(0,1)(1,0)(1,2) / 青: 拍2(2,0)・拍3(3,1)(2,0)(2,2)）。
スナップの既定は1/2拍。ブラシの既定は赤の↓。"""
import math

from e2e_helpers import counts, state, wait_until, cell, place_at, dirty
from edit_helpers import (open_ed, mv, edit, undo, redo, wheel, pie_pick, hover_off_grid, to_edit_cam, to_light_mode,
                          light_lane, place_light, click_obj, hover_obj, objs_on_screen, frames)
from edit_details_helpers import (place_wall, wall, handle_press_drag, hex01, light_row, click_el, set_setting_checkbox,
                                  restore_settings, hover_pv, hover_nle, osc_log)

BACK = 8          # ライトのレーン番号（0=左端）。BACK の種別(et)は 0
ROT_NODOT = [1, 6, 2, 4, 0, 5, 3, 7]   # Alt+ホイールの回転順 ↓↙←↖↑↗→↘（手前へ回す＝この順に進む）
W0 = {'beat': 0, 'x': 1, 'y': 0, 'w': 2, 'h': 2, 'dur': 2}   # place_wall で置く壁
CUR = "window._dbgApp.state().cur"


# ---- 小道具 ----
def _cur_is(ed, b, label=''):
    wait_until(ed, f"Math.abs({CUR}-({b}))<1e-6&&!window._dbgApp.state().playing", label=label or f'再生位置が拍{b}')
    frames(ed)   # 3Dビューのオブジェクトの位置は次の描画で再生位置に合わせ直される＝画面座標を読むのはその後


def _step(ed, key, n=1, **mods):
    for _ in range(n):
        ed.key(key, **mods)


def _size_mode(ed):
    hover_off_grid(ed)
    ed.key('s')
    wait_until(ed, "window._dbgApp.edit().gizmo==='size'&&window._dbgApp.gizmoScreen().handles.some(h=>h.size)", label='Sでサイズモード')


def _wall_is(ed, w, label):
    js = '&&'.join(f"w.{k}==={v}" for k, v in w.items())
    wait_until(ed, f"(w=>!!w&&{js})(window._dbgApp.objs().walls[0])", label=label)


def _select_light(ed, li, beat):
    p = light_lane(ed, li, beat)
    mv(ed, p['x'], p['y'])
    ed.click(p['x'], p['y'])
    wait_until(ed, "window._dbgApp.edit().lightSel.length===1", label=f'ライト選択 レーン{li} 拍{beat}')
    return p


def _swing(ed):
    return ed.js("window._dbgApp.swing()")


def _place(ed, x, y, kind='notes'):
    """今の拍・今のブラシでマス(x,y)をクリックして置く（kind の数が1つ増えるまで待つ）"""
    n0 = counts(ed)[kind]
    wait_until(ed, f"(p=>p&&p.onScreen)(window._dbgApp.cellScreen({x},{y}))", label=f'マス({x},{y})が画面に入る')
    p = cell(ed, x, y)
    mv(ed, p['x'], p['y'])
    ed.wait(0.1)   # ホバーでゴーストが出てから押す
    ed.click(p['x'], p['y'])
    wait_until(ed, f"window._dbgApp.state().counts.{kind}==={n0 + 1}", label=f'マス({x},{y})に{kind}を配置')


def _aux_items(key):
    """直前ノーツ表示の内容（_dbgApp.aux().key＝「色|赤|青」）を [赤, 青] の (拍, {(x,y,向き)}) に。無い色は None"""
    out = []
    for part in key.split('|')[1:]:
        if part == '-':
            out.append(None)
            continue
        b, items = part.split(':', 1)
        out.append((float(b), {tuple(int(v) for v in it.split(',')) for it in items.split(';')}))
    return out


# ---- 1. 壁の高さ・奥行きのつまみ ----
def test_wall_size_height(t):
    '''壁を選んでS→上のつまみを上へ引くと高さが盤の上端（3段）まで伸びてそれ以上は伸びない・下のつまみは床より下へ出ず（履歴も積まない）、上へ引くと下端が上がって最小1段で止まる・Undo/Redo'''
    ed = open_ed(t)
    place_wall(ed)
    _size_mode(ed)
    u0 = state(ed)['undo']
    ok, seen = handle_press_drag(ed, 'y', 1, until="window._dbgApp.objs().walls[0].h===3", extra_px=100,
                                 watch="window._dbgApp.objs().walls[0].h")
    t.ok(ok, f'上のつまみで3段まで伸びる（途中の高さ: {seen}）')
    t.eq(wall(ed), {**W0, 'h': 3}, '上端（3段）で止まる（さらに100px引いても）・他の寸法は変わらない')
    t.ok(set(seen) <= {2, 3}, f'高さは段単位でしか変わらない: {seen}')
    t.eq(state(ed)['undo'], u0 + 1, '1回のドラッグ＝履歴1つ')
    undo(ed)
    _wall_is(ed, W0, '高さのUndo')
    u1 = state(ed)['undo']
    handle_press_drag(ed, 'y', -1, max_px=150)   # 段0の壁の下のつまみを下（外）へ
    t.eq(wall(ed), W0, '床（段0）より下へは伸びない')
    t.eq(state(ed)['undo'], u1, '変化の無いドラッグは履歴を積まない')
    ok, seen = handle_press_drag(ed, 'y', -1, inward=True, until="window._dbgApp.objs().walls[0].y===1", extra_px=100,
                                 watch="[window._dbgApp.objs().walls[0].y,window._dbgApp.objs().walls[0].h]")
    t.ok(ok, f'下のつまみを上へ引くと下端が上がる（途中の[段,高さ]: {seen}）')
    t.eq(wall(ed), {**W0, 'y': 1, 'h': 1}, '下端が段1へ・上端（段1）は動かない＝最小1段で止まる')
    undo(ed)
    _wall_is(ed, W0, '下端のUndo')
    redo(ed)
    _wall_is(ed, {**W0, 'y': 1, 'h': 1}, '下端のRedo')
    t.no_errors()


def test_wall_size_depth(t):
    '''壁のSサイズモード: 奥のつまみを奥へ引くとスナップ（1/2拍）単位で奥行きが伸び、手前へ引き切っても1スナップ残る・手前のつまみは拍0より前へ出ず（履歴も積まない）、奥へ引くと始まりが遅れて終わりは動かない・Undo/Redo'''
    ed = open_ed(t)
    place_wall(ed)
    _size_mode(ed)
    ok, seen = handle_press_drag(ed, 'z', 1, until="window._dbgApp.objs().walls[0].dur===3",
                                 watch="window._dbgApp.objs().walls[0].dur")
    t.ok(ok, f'奥のつまみで3拍まで伸びる（途中の奥行き: {seen}）')
    t.eq(wall(ed), {**W0, 'dur': 3}, '奥行き3拍（始まりの拍は変わらない）')
    t.ok(set(seen) <= {2, 2.5, 3} and 2.5 in seen, f'奥行きは1/2拍ずつ変わる: {seen}')
    undo(ed)
    _wall_is(ed, W0, '奥行きのUndo')
    handle_press_drag(ed, 'z', 1, inward=True, max_px=420)
    t.eq(wall(ed), {**W0, 'dur': 0.5}, '手前へ引き切っても奥行きは1スナップ（1/2拍）残る')
    undo(ed)
    _wall_is(ed, W0, '縮めたのをUndo')
    u0 = state(ed)['undo']
    handle_press_drag(ed, 'z', -1, max_px=200)   # 拍0から始まる壁の手前のつまみを手前（外）へ
    t.eq(wall(ed), W0, '拍0より前へは伸びない')
    t.eq(state(ed)['undo'], u0, '変化の無いドラッグは履歴を積まない')
    ok, seen = handle_press_drag(ed, 'z', -1, inward=True, until="window._dbgApp.objs().walls[0].beat===1",
                                 watch="window._dbgApp.objs().walls[0].beat")
    t.ok(ok, f'手前のつまみを奥へ引くと始まりが遅れる（途中の拍: {seen}）')
    t.eq(wall(ed), {**W0, 'beat': 1, 'dur': 1}, '始まりが拍1へ・終わり（拍2）は動かない')
    undo(ed)
    _wall_is(ed, W0, '始まりのUndo')
    redo(ed)
    _wall_is(ed, {**W0, 'beat': 1, 'dur': 1}, '始まりのRedo')
    t.no_errors()


# ---- 2. ライトのカラーパイ ----
RED, BLUE, WHITE = hex01('#ff274d'), hex01('#3092ff'), hex01('#e8f0ff')   # 左ノーツ・右ノーツの色（既定）・ライトの白
PIE_RIGHT, PIE_WHITE = 120, 240   # カラーパイの並び: 左ノーツ(0°・上)→右ノーツ(120°)→白(240°)（登録色が無い時）


def test_light_color_pie_chroma(t):
    '''Chroma配色: LIGHTINGでCを押したまま向けて離す＝カラーパイ。右（青）を選ぶと以後置くライトが青になり（選択が無ければ既存は変えない）、選択中のライトは白を選ぶと白に変わる・Undo/Redo'''
    ed = open_ed(t)
    try:
        _color_pie_chroma(t, ed)
    finally:
        restore_settings(ed, 'bsnm_chroma')


def _color_pie_chroma(t, ed):
    set_setting_checkbox(ed, 'chromaMode', True)   # 環境設定「ライト配色モード」＝Chroma
    to_edit_cam(ed)
    to_light_mode(ed)
    place_light(ed, BACK, 1)
    t.eq(light_row(ed, 1, 0)['color'], RED, '既定のブラシ＝左ノーツの色')
    u0 = state(ed)['undo']
    hover_off_grid(ed)
    pie_pick(ed, 'c', PIE_RIGHT)
    wait_until(ed, "window._dbgApp.edit().lightBrush.chroma==='#3092ff'", label='カラーパイで右（青）')
    t.eq(light_row(ed, 1, 0)['color'], RED, '選択もマウス下のライトも無い時はブラシだけが変わる')
    t.eq(state(ed)['undo'], u0, 'ブラシだけの変更は履歴を積まない')
    place_light(ed, BACK, 2)
    t.eq(light_row(ed, 2, 0)['color'], BLUE, '置いたライトは右ノーツの色（青）')
    _select_light(ed, BACK, 1)
    u1 = state(ed)['undo']
    pie_pick(ed, 'c', PIE_WHITE)
    wait_until(ed, f"window._dbgApp.edit().lightBrush.chroma==='#e8f0ff'&&window._dbgApp.state().undo==={u1 + 1}", label='カラーパイで白')
    t.eq(light_row(ed, 1, 0)['color'], WHITE, '選択中のライトが白に変わる')
    t.eq(light_row(ed, 2, 0)['color'], BLUE, '選んでいないライトは変わらない')
    t.eq((light_row(ed, 1, 0)['i'], light_row(ed, 1, 0)['f']), (5, 1), '色を変えても動作（ライト）と強さは変わらない')
    undo(ed)
    wait_until(ed, f"window._dbgApp.state().undo==={u1}", label='色の変更のUndo')
    t.eq(light_row(ed, 1, 0)['color'], RED, 'Undoで元の色（左ノーツの色）')
    redo(ed)
    wait_until(ed, f"window._dbgApp.state().undo==={u1 + 1}", label='色の変更のRedo')
    t.eq(light_row(ed, 1, 0)['color'], WHITE, 'Redoで白')
    t.no_errors()


def test_light_color_pie_vanilla(t):
    '''バニラ配色（既定）: カラーパイで右（青）を選ぶと、選択中のライトも以後置くライトも青（値1＝青のライト）になり、見えないクロマ色（customData.color）は書かない'''
    ed = open_ed(t)
    t.eq(ed.js("document.getElementById('chromaMode').checked"), False, '前提: 既定の設定はバニラ配色')
    to_edit_cam(ed)
    to_light_mode(ed)
    place_light(ed, BACK, 1)
    t.eq({k: light_row(ed, 1, 0)[k] for k in ('i', 'color')}, {'i': 5, 'color': None}, '既定のブラシ＝赤のライト（4+1）・クロマ色なし')
    _select_light(ed, BACK, 1)
    pie_pick(ed, 'c', PIE_RIGHT)
    wait_until(ed, "window._dbgApp.edit().pie===false", label='パイが閉じる')
    ed.wait(0.2)
    sel = {k: light_row(ed, 1, 0)[k] for k in ('i', 'color')}
    hover_off_grid(ed)
    ed.key('a')   # 選択を外してから新しく置く
    place_light(ed, BACK, 2)
    new = {k: light_row(ed, 2, 0)[k] for k in ('i', 'color')}
    t.no_errors()
    want = {'i': 1, 'color': None}
    t.eq(sel, want, '選択中のライトが青（値1）になり、クロマ色は書かない')
    t.eq(new, want, '以後置くライトも青（値1）・クロマ色なし')


# ---- 3. 直前ノーツ表示（H）・同じ向きの警告 ----
def test_aux_prev_toggle(t):
    '''直前ノーツ表示（補助グリッド）: 再生ヘッドより前の赤・青それぞれ最後の拍のノーツ（位置・向き）を映す・Hで表示/非表示（環境設定と連動・保存される）・LIGHTINGと再生中は出さない'''
    ed = open_ed(t)
    try:
        _aux_prev(t, ed)
    finally:
        restore_settings(ed, 'bsnm_auxprev')


def _aux_prev(t, ed):
    a = ed.js("window._dbgApp.aux()")
    t.eq((a['show'], a['visible']), (True, True), '既定は表示')
    t.eq(_aux_items(a['key']), [None, None], '拍0より前にノーツは無い')
    hover_off_grid(ed)
    _step(ed, 'ArrowRight', 5)
    _cur_is(ed, 2.5)
    want = [(1.0, {(1, 0, 1)}), (2.0, {(2, 0, 1)})]
    wait_until(ed, f"window._dbgApp.aux().key.endsWith('|1:1,0,1|2:2,0,1')", label='拍2.5の直前ノーツ')
    t.eq(_aux_items(ed.js("window._dbgApp.aux().key")), want, '拍2.5: 赤は拍1・青は拍2')
    ed.key('ArrowRight')
    _cur_is(ed, 3)
    ed.wait(0.15)
    t.eq(_aux_items(ed.js("window._dbgApp.aux().key")), want, '拍3: 同じ拍（拍3）のノーツは「直前」に入らない')
    ed.key('ArrowRight')
    _cur_is(ed, 3.5)
    wait_until(ed, "window._dbgApp.aux().key.includes('|3:')", label='拍3.5の直前ノーツ')
    t.eq(_aux_items(ed.js("window._dbgApp.aux().key")), [(3.0, {(0, 1, 1), (1, 0, 1), (1, 2, 1)}), (3.0, {(3, 1, 1), (2, 0, 1), (2, 2, 1)})],
         '拍3.5: 拍3の赤3個・青3個（同じ拍は全部）')
    ed.key('h')
    wait_until(ed, "!window._dbgApp.aux().show&&!window._dbgApp.aux().visible", label='Hで非表示')
    t.eq(ed.js("[localStorage.getItem('bsnm_auxprev'), document.getElementById('auxPrevShow').checked]"), ['0', False],
         '設定（保存値・環境設定のチェック）も切り替わる')
    ed.key('h')
    wait_until(ed, "window._dbgApp.aux().show&&window._dbgApp.aux().visible", label='もう一度Hで表示')
    to_light_mode(ed)
    wait_until(ed, "!window._dbgApp.aux().visible", label='LIGHTINGでは出さない')
    ed.key('h')
    ed.wait(0.15)
    t.eq(ed.js("window._dbgApp.aux().show"), True, 'LIGHTINGのHは直前ノーツ表示を切り替えない')
    hover_off_grid(ed)
    ed.key('Tab')
    wait_until(ed, "!window._dbgApp.state().lightMode&&window._dbgApp.aux().visible", label='NOTESへ戻ると表示')
    ed.key(' ')
    wait_until(ed, "window._dbgApp.state().playing&&!window._dbgApp.aux().visible", label='再生中は出さない')
    ed.key(' ')
    wait_until(ed, "!window._dbgApp.state().playing&&window._dbgApp.aux().visible", label='止めるとまた表示')
    t.no_errors()


def test_swing_warn_prev_lamp(t):
    '''同じ向きの警告: 前の同じ色と同じ向き（↓）で置くと置いたノーツに赤枠とランプ→Undoで消える／もう一度置く→ランプのクリックでその拍へ→向きを↑に回すと消える'''
    ed = open_ed(t)
    t.eq({k: _swing(ed)[k] for k in ('on', 'warned', 'lamp')}, {'on': True, 'warned': [], 'lamp': False}, '既定はON・読み込んだだけでは警告しない')
    hover_off_grid(ed)
    _step(ed, 'ArrowRight', 10)
    _cur_is(ed, 5)
    bad = {'beat': 5, 'x': 0, 'y': 0, 'c': 0, 'd': 1}
    place_at(ed, 0, 0)   # 赤↓（前の赤は拍3の↓）
    wait_until(ed, "window._dbgApp.swing().lamp&&window._dbgApp.swing().frames===1", label='ランプが点き、赤枠が描かれる')
    t.eq(_swing(ed)['warned'], [bad], '赤枠は置いたノーツ（1個）')
    hover_off_grid(ed)
    undo(ed)
    wait_until(ed, "window._dbgApp.state().counts.notes===8&&!window._dbgApp.swing().lamp&&window._dbgApp.swing().warned.length===0",
               label='置いたのをUndoすると赤枠とランプが消える')
    place_at(ed, 0, 0)
    wait_until(ed, "window._dbgApp.swing().lamp", label='もう一度置くとランプが点く')
    hover_off_grid(ed)
    ed.key('ArrowLeft', ctrl=True)
    _cur_is(ed, 0, '先頭へ')
    click_el(ed, '#swingLamp')
    _cur_is(ed, 5, 'ランプのクリックで赤枠のノーツの拍へ')
    click_obj(ed, beat=5, x=0, y=0)
    wait_until(ed, "window._dbgApp.state().sel===1", label='赤枠のノーツを選ぶ')
    o = hover_obj(ed, beat=5, x=0, y=0)
    for d in ROT_NODOT[1:5]:   # ↓→↙→←→↖→↑
        wheel(ed, o['sx'], o['sy'], 100, alt=True)
        wait_until(ed, f"window._dbgApp.notes().notes.some(n=>n.beat===5&&n.x===0&&n.y===0&&n.d==={d})", label=f'向き {d} へ回転')
    hover_off_grid(ed)
    ed.key('a')
    wait_until(ed, "!window._dbgApp.swing().lamp&&window._dbgApp.swing().warned.length===0&&window._dbgApp.swing().frames===0",
               label='向きを直すと赤枠とランプが消える')
    t.no_errors()


def test_swing_warn_next_and_exempt(t):
    '''同じ向きの警告: 後ろの同じ向きの前に置くと後ろのノーツに赤枠（置いた方ではない）・1/5拍未満（スライダー）／直前がドット／間にボムがある時は警告しない'''
    ed = open_ed(t)
    p = hover_off_grid(ed)
    for _ in range(4):   # 空き地のAlt+ホイール＝ブラシの向きだけ回る（↓→↙→←→↖→↑）
        wheel(ed, p['x'], p['y'], 100, alt=True)
    wait_until(ed, "window._dbgApp.state().brush.d===0", label='ブラシを↑に')
    _step(ed, 'ArrowRight', 12)
    _cur_is(ed, 6)
    place_at(ed, 0, 0)   # A: 拍6 赤↑（前の赤は拍3の↓＝問題なし）
    ed.wait(0.15)
    t.eq(_swing(ed)['warned'], [], '向きが逆（↓の後の↑）なら警告しない')
    hover_off_grid(ed)
    _step(ed, 'ArrowLeft', 2)
    _cur_is(ed, 5)
    place_at(ed, 1, 0)   # B: 拍5 赤↑ → 後ろの A（拍6↑）が同じ向き
    wait_until(ed, "window._dbgApp.swing().lamp", label='ランプが点く')
    t.eq(_swing(ed)['warned'], [{'beat': 6, 'x': 0, 'y': 0, 'c': 0, 'd': 0}], '赤枠は後ろのノーツ（拍6）に付く')
    hover_off_grid(ed)
    undo(ed)
    wait_until(ed, "window._dbgApp.state().counts.notes===9&&!window._dbgApp.swing().lamp", label='Undoで赤枠が消える')
    # スライダー: 1/8拍後に同じ向き（間隔が1/5拍未満＝同じ振り）
    pie_pick(ed, ',', 216)   # スナップパイ: 1/1(上)→1/2→1/4→1/8(216°)→1/16
    wait_until(ed, "window._dbgApp.nle().snap===0.125", label='スナップ1/8')
    hover_off_grid(ed)
    _step(ed, 'ArrowRight', 9)   # 5 → 6.125
    _cur_is(ed, 6.125)
    place_at(ed, 1, 1)   # C: 拍6.125 赤↑（前は拍6の↑）
    ed.wait(0.15)
    t.eq(_swing(ed)['warned'], [], '1/8拍後の同じ向き（スライダー）は警告しない')
    # ドット: ドットは判定しない・直前がドットなら次の矢印も判定しない
    hover_off_grid(ed)
    ed.key('d')
    wait_until(ed, "window._dbgApp.state().brush.d===8", label='Dでブラシをドットに')
    _step(ed, 'ArrowRight', 3)
    _cur_is(ed, 6.5)
    place_at(ed, 0, 0)   # D: 拍6.5 赤ドット
    hover_off_grid(ed)
    ed.key('d')
    wait_until(ed, "window._dbgApp.state().brush.d===0", label='もう一度Dで↑に戻る')
    _step(ed, 'ArrowRight', 4)
    _cur_is(ed, 7)
    place_at(ed, 1, 0)   # E: 拍7 赤↑（直前の赤はドット）
    ed.wait(0.15)
    t.eq(_swing(ed)['warned'], [], 'ドットと、ドットの後の矢印は警告しない')
    # ボム: 間にボムがあれば意図的なリセット
    hover_off_grid(ed)
    _step(ed, 'ArrowRight', 4)
    _cur_is(ed, 7.5)
    pie_pick(ed, 'w', 120)   # 配置パイ: 右下＝ボム
    wait_until(ed, "window._dbgApp.state().brush.type==='bomb'", label='Wパイでボム')
    _place(ed, 3, 2, 'bombs')
    hover_off_grid(ed)
    pie_pick(ed, 'w', 0)
    wait_until(ed, "window._dbgApp.state().brush.type==='note'&&window._dbgApp.state().brush.d===0", label='Wパイでノーツ（↑のまま）')
    _step(ed, 'ArrowRight', 4)
    _cur_is(ed, 8)
    place_at(ed, 0, 0)   # F: 拍8 赤↑（前は拍7の↑だが、間の拍7.5にボム）
    ed.wait(0.15)
    t.eq(_swing(ed)['warned'], [], '間にボムがあれば同じ向きでも警告しない')
    t.eq(_swing(ed)['lamp'], False, 'ランプは消えたまま')
    t.no_errors()


def test_swing_warn_setting_off(t):
    '''環境設定で「同じ向きの連続の警告」をOFFにすると出ていた赤枠とランプが消え（ランプ自体も隠れる）、同じ向きで置いても警告しない・ONに戻すとまた警告する'''
    ed = open_ed(t)
    try:
        _swing_setting_off(t, ed)
    finally:
        restore_settings(ed, 'bsnm_swingwarn')


def _swing_setting_off(t, ed):
    hover_off_grid(ed)
    _step(ed, 'ArrowRight', 10)
    _cur_is(ed, 5)
    place_at(ed, 0, 0)   # 赤↓（前の赤は拍3の↓）
    wait_until(ed, "window._dbgApp.swing().lamp", label='警告が出る')
    set_setting_checkbox(ed, 'swingWarnOn', False)
    sw = _swing(ed)
    t.eq({k: sw[k] for k in ('on', 'warned', 'lamp')}, {'on': False, 'warned': [], 'lamp': False}, 'OFFで出ていた警告が消える')
    wait_until(ed, "window._dbgApp.swing().frames===0", label='赤枠が消える')
    t.eq(ed.js("[document.getElementById('swingLamp').style.display, localStorage.getItem('bsnm_swingwarn')]"), ['none', '0'],
         'ランプは隠れ、設定は保存される')
    hover_off_grid(ed)
    ed.key('ArrowRight')
    _cur_is(ed, 5.5)
    place_at(ed, 1, 0)   # 赤↓（前は拍5の↓）
    ed.wait(0.2)
    t.eq(_swing(ed)['warned'], [], 'OFFの間は同じ向きで置いても警告しない')
    set_setting_checkbox(ed, 'swingWarnOn', True)
    t.eq(ed.js("document.getElementById('swingLamp').style.display"), '', 'ONに戻すとランプが見える（消灯）')
    hover_off_grid(ed)
    ed.key('ArrowRight')
    _cur_is(ed, 6)
    place_at(ed, 0, 1)   # 赤↓（前は拍5.5の↓）
    wait_until(ed, "window._dbgApp.swing().lamp", label='ONに戻すとまた警告する')
    t.eq(_swing(ed)['warned'], [{'beat': 6, 'x': 0, 'y': 1, 'c': 0, 'd': 1}], '置いたノーツに赤枠')
    t.no_errors()


# ---- 4. 譜面チェックの拍からのジャンプ ----
def _open_mapcheck(ed):
    n = ed.js("window._dbgApp.nleScreen(0)")
    mv(ed, n['left'] + n['w'] * 0.6, n['lanes'] + 40)
    ed.key('Tab')   # NLEの上でTab=INFOへ
    wait_until(ed, "window._dbgApp.view()==='info'", label='INFO画面へ')
    click_el(ed, '#iMapCheck')
    wait_until(ed, "(()=>{const p=document.getElementById('mcPanel');return !!p&&p.style.display!=='none'"
                   "&&!p.querySelector('.mcRerun').disabled&&p.querySelectorAll('.mcBeat').length>0})()", timeout=10, label='チェック結果の表示')


def _chip_click(ed, ref):
    sel = f'#mcPanel .mcBeat[data-ref="{ref}"]'
    ed.js(f"document.querySelector({sel!r}).scrollIntoView({{block:'center'}})")
    click_el(ed, sel)


def _selected(ed):
    return sorted((o['kind'], o['beat'], o['x'], o['y']) for o in objs_on_screen(ed) if o['sel'])


def test_mapcheck_jump(t):
    '''譜面チェックの拍をクリックすると、その難易度へ切り替わり、その拍へ移動して対象のオブジェクトが選ばれる（ノーツ＝移動のつまみ付き・チェーン＝つまみ無し）'''
    ed = open_ed(t, 'rich')
    t.eq(state(ed)['diff'], 'HardStandard.dat', '前提: Hard を開いている')
    # パネルと同じ判定を直接呼び、拍のチップ（data-ref＝難易度:項目:対象）が指すオブジェクトを調べる
    objs = ed.js("""(async()=>{ const mc=await import('./js/mapcheck/mapcheck.js'); const res=mc.runMapCheck(await window._dbgApp.mapCheckInput());
      const out=[]; res.diffs.forEach((d,di)=>d.results.forEach((r,ri)=>(r.objs||[]).forEach((o,oi)=>out.push(
        {ref:di+':'+ri+':'+oi, dn:d.difficulty, kind:o.kind, beat:o.beat, x:o.x, y:o.y}))));
      return out; })()""")
    _open_mapcheck(ed)
    shown = set(ed.js("[...document.querySelectorAll('#mcPanel .mcBeat')].map(e=>e.dataset.ref)"))

    def pick(dn, kind):
        hs = [o for o in objs if o['dn'] == dn and o['kind'] == kind and o['ref'] in shown]
        t.ok(hs, f'前提: rich の譜面チェックに {dn} の {kind} の拍チップがある（判定が変わったら素材を見直す）: {objs}')
        return hs[0]

    for o, gizmo in ((pick('Expert', 'note'), 'move'), (pick('Hard', 'note'), 'move'), (pick('Expert', 'chain'), None)):
        _chip_click(ed, o['ref'])
        wait_until(ed, f"window._dbgApp.state().diff==='{o['dn']}Standard.dat'", label=f"{o['dn']} へ切替")
        _cur_is(ed, o['beat'], f"拍{o['beat']}へ移動")
        wait_until(ed, "window._dbgApp.state().sel===1", label='対象を選択')
        t.eq(_selected(ed), [(o['kind'], o['beat'], o['x'], o['y'])], f"選ばれたのはチップの対象 {o}")
        t.eq(edit(ed)['gizmo'], gizmo, f"{o['kind']} のつまみ")
        t.eq(ed.js("[...document.querySelectorAll('#mcPanel .mcBeat.cur')].map(e=>e.dataset.ref)"), [o['ref']], '押したチップだけが強調される')
    t.no_errors()


# ---- 5. 再生・位置の移動・マーカー・メトロノーム ----
SONG_END = 32   # basic.wav 16秒 × 120BPM


def test_playback_keys(t):
    '''Spaceで再生（位置が進む）→もう一度Spaceで止まる（位置はそのまま）・→/←＝スナップ（1/2拍）ずつ・Shift+Ctrl+→/←＝4拍ずつ・Ctrl+→＝曲末（音源の終わり＝32拍）・Ctrl+←＝先頭・曲末から再生すると先頭から繰り返す・再生中の→は止めてから動かす'''
    ed = open_ed(t)
    hover_off_grid(ed)
    u0 = state(ed)['undo']
    ed.key(' ')
    wait_until(ed, f"window._dbgApp.state().playing&&{CUR}>0.6", label='再生で位置が進む')
    ed.key(' ')
    wait_until(ed, "!window._dbgApp.state().playing", label='Spaceで止まる')
    c1 = ed.js(CUR)
    ed.wait(0.3)
    t.eq(ed.js(CUR), c1, '止めた後は位置が動かない')
    ed.key('ArrowRight')
    _cur_is(ed, round((c1 + 0.5) / 0.5) * 0.5, '→＝1コマ先（スナップの格子へ）')
    ed.key('ArrowLeft', ctrl=True)
    _cur_is(ed, 0, 'Ctrl+←＝先頭')
    ed.key('ArrowLeft')
    ed.wait(0.15)
    t.eq(ed.js(CUR), 0, '先頭より前へは戻らない')
    _step(ed, 'ArrowRight', 3)
    _cur_is(ed, 1.5, '→3回＝1.5拍')
    ed.key('ArrowLeft')
    _cur_is(ed, 1, '←＝1コマ前')
    ed.key('ArrowRight', ctrl=True, shift=True)
    _cur_is(ed, 5, 'Shift+Ctrl+→＝4拍先')
    ed.key('ArrowLeft', ctrl=True, shift=True)
    _cur_is(ed, 1, 'Shift+Ctrl+←＝4拍前')
    ed.key('ArrowRight', ctrl=True)
    _cur_is(ed, SONG_END, 'Ctrl+→＝曲末（音源の終わり）')
    ed.key(' ')
    wait_until(ed, f"window._dbgApp.state().playing&&{CUR}<4", label='曲末から再生すると先頭から繰り返す')
    wait_until(ed, f"{CUR}>0.3", label='繰り返しの再生が進む')
    ed.key('ArrowRight')
    wait_until(ed, "!window._dbgApp.state().playing", label='再生中の→は再生を止める')
    c2 = ed.js(CUR)
    t.ok(abs(c2 * 2 - round(c2 * 2)) < 1e-9 and 0 < c2 < 5, f'止めた位置から1コマ先（スナップの格子の上）: {c2}')
    t.eq(state(ed)['undo'], u0, '再生・移動は編集の履歴に積まない')
    t.no_errors()


def test_transport_and_markers(t):
    '''再生バーのボタン（先頭・前のマーカー・再生/停止・次のマーカー・曲末）と、3Dビューの上での Ctrl+] / Ctrl+[（マーカーへのジャンプ）'''
    ed = open_ed(t)
    for b in (12, 4):
        hover_nle(ed, b)
        ed.key('e', ctrl=True)   # NLEの上の Ctrl+E＝マウスの拍にマーカー
        wait_until(ed, f"window._dbgApp.nle().markers.some(m=>m.beat==={b})", label=f'拍{b}にマーカー')
    hover_off_grid(ed)   # 以降のキーは3Dビューの上で
    ed.key(']', ctrl=True)
    _cur_is(ed, 4, 'Ctrl+]＝次のマーカー（拍4）')
    # 曲の読み込み完了の通知（4秒）が再生バーに重なって押せない間は待つ（test_transport_ui で別に確かめる）
    wait_until(ed, "document.getElementById('errToast').style.display==='none'", timeout=8, label='読み込みの通知が消える')
    click_el(ed, '#tbi_tp_nextkey')
    _cur_is(ed, 12, '「次のマーカー」ボタン＝拍12')
    click_el(ed, '#tbi_tp_nextkey')
    ed.wait(0.3)
    t.eq(ed.js(CUR), 12, '最後のマーカーより先へは動かない')
    hover_off_grid(ed)
    ed.key('[', ctrl=True)
    _cur_is(ed, 4, 'Ctrl+[＝前のマーカー（拍4）')
    click_el(ed, '#tbi_tp_prevkey')
    _cur_is(ed, 0, '「前のマーカー」ボタン: 最初のマーカーより前は先頭（拍0）')
    click_el(ed, '#tbi_tp_end')
    _cur_is(ed, SONG_END, '「曲末へ」ボタン')
    click_el(ed, '#tbi_tp_start')
    _cur_is(ed, 0, '「スタートに戻る」ボタン')
    click_el(ed, '#tbi_tp_play')
    wait_until(ed, f"window._dbgApp.state().playing&&{CUR}>0.3", label='「再生」ボタンで再生')
    click_el(ed, '#tbi_tp_play')
    wait_until(ed, "!window._dbgApp.state().playing", label='もう一度押すと止まる')
    t.eq([m['beat'] for m in ed.js("window._dbgApp.nle().markers")], [4, 12], 'ジャンプでマーカーは変わらない')
    t.no_errors()


def test_transport_ui(t):
    '''再生バーのボタン: 曲の読み込み直後の通知に隠れず押せる・「スタートに戻る」「曲末へ」の説明（ツールチップ）のキーが実際の割り当て（Ctrl+← / Ctrl+→）と合っている（Shift+Ctrl+←/→ は4拍ずつの移動）'''
    ed = open_ed(t)
    # 素材の読み込み（音源の配置）で「音源を配置しました」の通知が4秒出る。その間も再生バーのボタンは押せるべき
    cover = ed.js("""(()=>{ const toast=document.getElementById('errToast').style.display!=='none';
      return {toast, covered:['start','prevkey','play','nextkey','end'].filter(k=>{ const e=document.getElementById('tbi_tp_'+k), r=e.getBoundingClientRect();
        const h=document.elementFromPoint(r.left+r.width/2,r.top+r.height/2); return !(h===e||e.contains(h)); })}; })()""")
    titles = ed.js("['start','end'].map(k=>document.getElementById('tbi_tp_'+k).title.replace(/ /g,''))")
    hover_off_grid(ed)
    _step(ed, 'ArrowRight', 12)
    _cur_is(ed, 6)
    ed.key('ArrowLeft', ctrl=True, shift=True)
    _cur_is(ed, 2, 'Shift+Ctrl+←は4拍前（先頭へは行かない）')
    ed.key('ArrowLeft', ctrl=True)
    _cur_is(ed, 0, 'Ctrl+←が先頭へ')
    t.no_errors()
    bad = [tt for tt, k in zip(titles, '←→') if f'Ctrl+{k}' not in tt or 'Shift' in tt]
    t.eq(bad, [], 'ツールチップのキーが実際の割り当て（Ctrl+←/→）と合っている（lang/ja.json・en.json の tb.start / tb.end）')
    t.eq(cover['covered'], [], '曲の読み込み直後のお知らせ（4秒）が再生バーのボタンに重ならない（お知らせは再生バーより上に出す）')


def test_metronome(t):
    '''メトロノーム（音量の下のボタン）: ONで再生すると拍頭ごとにクリック音（1760Hz）が1回鳴り、OFFでは鳴らない。ノーツの通過音（880Hz）はノーツのある拍ごとに鳴る'''
    ed = open_ed(t)
    btn_on = "document.getElementById('vmMetroBtn').classList.contains('on')"
    t.eq(ed.js(btn_on), False, '既定はOFF')
    click_el(ed, '#vmMetroBtn')
    wait_until(ed, btn_on, label='ボタンでON')
    note_beats = sorted({n['beat'] for n in ed.js("window._dbgApp.notes().notes")})

    def play_count():
        osc_log(ed, reset=True)
        hover_off_grid(ed)
        ed.key(' ')
        wait_until(ed, f"window._dbgApp.state().playing&&{CUR}>2.3", label='再生で拍2を越える')
        ed.key(' ')
        wait_until(ed, "!window._dbgApp.state().playing", label='停止')
        c = ed.js(CUR)
        return c, osc_log(ed)

    c, log = play_count()
    t.eq(log.count(1760), math.floor(c), f'拍頭（1, 2, …）ごとにクリック音（{c:.2f}拍まで再生）')
    t.eq(log.count(880), len([b for b in note_beats if 0 < b <= c]), f'ノーツのある拍ごとに通過音（{c:.2f}拍まで再生）')
    click_el(ed, '#vmMetroBtn')
    wait_until(ed, f"!{btn_on}", label='もう一度押すとOFF')
    hover_off_grid(ed)
    ed.key('ArrowLeft', ctrl=True)
    _cur_is(ed, 0, '先頭へ')
    c, log = play_count()
    t.eq(log.count(1760), 0, 'OFFの時はクリック音が鳴らない')
    t.eq(log.count(880), len([b for b in note_beats if 0 < b <= c]), '通過音はメトロノームと関係なく鳴る')
    t.no_errors()


# ---- 6. PREVIEW の表示切替 ----
PV_BTNS = ('Notes', 'Lights', 'Struct', 'Ambient')
PV_VIS = "Object.fromEntries(['Notes','Lights','Struct','Ambient'].map(k=>[k,document.getElementById('pvVis'+k).classList.contains('on')]))"
PV_MODE = "[document.getElementById('bodyPv').classList.contains('on'), document.getElementById('tabFolder').classList.contains('on')]"


def test_preview_toggles(t):
    '''左上のペインでTab＝MEDIA⇄PREVIEW。PREVIEWの表示切替（ノーツ・ライト・構造物・環境ライト）は押すたびに入/切が替わり（既定は環境ライトだけ切）、互いに独立・MEDIAへ切り替えて戻っても保たれる・編集の履歴にも未保存にも関係しない'''
    ed = open_ed(t)
    t.eq(ed.js(PV_MODE), [False, True], '起動時は MEDIA')
    u0 = state(ed)['undo']
    hover_pv(ed)
    ed.key('Tab')
    wait_until(ed, f"({PV_MODE})[0]", label='左上でTab＝PREVIEW')
    t.eq(ed.js(PV_MODE), [True, False], 'PREVIEW の時は MEDIA の一覧を隠す')
    vis = {'Notes': True, 'Lights': True, 'Struct': True, 'Ambient': False}
    t.eq(ed.js(PV_VIS), vis, '既定: 環境ライトだけ切')
    for k in PV_BTNS:
        click_el(ed, f'#pvVis{k}')
        vis[k] = not vis[k]
        wait_until(ed, f"document.getElementById('pvVis{k}').classList.contains('on')==={str(vis[k]).lower()}", label=f'{k} の切替')
        t.eq(ed.js(PV_VIS), vis, f'{k} を押した後（押したものだけが変わる）')
    hover_pv(ed)
    ed.key('Tab')
    wait_until(ed, f"!({PV_MODE})[0]&&({PV_MODE})[1]", label='もう一度Tab＝MEDIA')
    hover_pv(ed)
    ed.key('Tab')
    wait_until(ed, f"({PV_MODE})[0]", label='PREVIEW へ戻る')
    t.eq(ed.js(PV_VIS), vis, 'MEDIA を挟んでも表示切替は保たれる')
    for k in PV_BTNS:
        click_el(ed, f'#pvVis{k}')
    wait_until(ed, f"JSON.stringify({PV_VIS})==='{{\"Notes\":true,\"Lights\":true,\"Struct\":true,\"Ambient\":false}}'", label='もう一度押すと既定へ戻る')
    t.eq(state(ed)['undo'], u0, '表示切替は編集の履歴に積まない')
    t.eq(dirty(ed)['lamp'], False, '表示切替で未保存にならない')
    t.no_errors()

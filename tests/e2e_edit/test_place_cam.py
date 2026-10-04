"""配置モードの定位置カメラが、先頭・曲末などへの移動でずれないこと（2026-10-04）。
以前は先頭・曲末・マーカーへの移動（seekEase）と「.」キーが、モードによらず注視点のZを0（再生ヘッド）へ寄せていた。
配置モードの定位置ビューは注視点がヘッドより先（Z=4.08）にあるため、移動のたびにカメラが約4ずれていた。
配置モードでは定位置ビューの注視点のZへ戻す（向き・高さ・横位置は変えない）。カメラ固定モードは従来どおりZ=0へ寄せる。"""
from e2e_helpers import state, wait_until
from edit_helpers import open_ed, hover_off_grid, mv, to_edit_cam


def _cam(ed):
    return ed.js("window._dbgApp.cam()")


def _wait_seek(ed, beat=None, label=""):
    """移動（イージング）が終わるまで待つ。beat を渡したら、その拍に着いたことも待つ"""
    cond = "!window._dbgApp.cam().anim"
    if beat is not None:
        cond += f"&&Math.abs(window._dbgApp.state().cur-({beat}))<1e-9"
    wait_until(ed, cond, label=label or f"拍{beat}への移動")


def _same_cam(t, got, want, what):
    for k in ("pos", "tgt"):
        d = max(abs(a - b) for a, b in zip(got[k], want[k]))
        t.ok(d < 1e-6, f"{what}: カメラの{'位置' if k == 'pos' else '注視点'}が変わらない（差 {d:.4f}）")


def _offset(c):
    return [p - q for p, q in zip(c["pos"], c["tgt"])]


def _click_btn(ed, el_id):
    r = ed.js(f"(()=>{{const r=document.getElementById('{el_id}').getBoundingClientRect();return {{x:r.left+r.width/2,y:r.top+r.height/2}}}})()")
    mv(ed, r["x"], r["y"])
    ed.click(r["x"], r["y"])


def test_place_cam_seek_keys(t):
    '''配置モード: Ctrl+→（曲末）・Ctrl+←（先頭）・Shift+Ctrl+→（4拍）で定位置カメラが動かない'''
    ed = open_ed(t)
    c0 = _cam(ed)
    t.ok(abs(c0["tgt"][2] - 4.08) < 1e-6, f"前提: 定位置ビューの注視点のZ=4.08（{c0['tgt'][2]}）")
    hover_off_grid(ed)
    ed.key("ArrowRight", ctrl=True)
    wait_until(ed, "window._dbgApp.state().cur>0&&!window._dbgApp.cam().anim", label="曲末への移動")
    _same_cam(t, _cam(ed), c0, "Ctrl+→（曲末へ）")
    ed.key("ArrowLeft", ctrl=True)
    _wait_seek(ed, 0)
    _same_cam(t, _cam(ed), c0, "Ctrl+←（先頭へ）")
    ed.key("ArrowRight", ctrl=True, shift=True)
    _wait_seek(ed, 4)
    _same_cam(t, _cam(ed), c0, "Shift+Ctrl+→（4拍先へ）")
    t.eq(state(ed)["camMode"], "place", "配置モードのまま")
    t.no_errors()


def test_place_cam_toolbar_and_head(t):
    '''配置モード: 再生バーの「曲末へ」「前のマーカーへ」「スタートに戻る」と「.」キー（再生ヘッドへ）でも定位置カメラが動かない'''
    ed = open_ed(t)
    c0 = _cam(ed)
    _click_btn(ed, "tbi_tp_end")
    wait_until(ed, "window._dbgApp.state().cur>0&&!window._dbgApp.cam().anim", label="曲末への移動")
    _same_cam(t, _cam(ed), c0, "再生バーの「曲末へ」")
    _click_btn(ed, "tbi_tp_prevkey")
    _wait_seek(ed, label="前のマーカーへの移動")
    _same_cam(t, _cam(ed), c0, "再生バーの「前のマーカーへ」")
    _click_btn(ed, "tbi_tp_start")
    _wait_seek(ed, 0)
    _same_cam(t, _cam(ed), c0, "再生バーの「スタートに戻る」")
    hover_off_grid(ed)
    ed.key(".")
    ed.wait(0.1)
    _same_cam(t, _cam(ed), c0, "「.」キー（再生ヘッドへ）")
    t.no_errors()


def test_place_cam_after_orbit(t):
    '''配置モード: 視点を回した後に先頭へ戻ると、向きを保ったままタイムライン方向だけ定位置（注視点のZ=4.08）へ寄る'''
    ed = open_ed(t)
    c0 = _cam(ed)
    p = hover_off_grid(ed)
    ed.drag(p["x"], p["y"], p["x"] + 80, p["y"] - 30, button="middle")   # 中ドラッグ＝マウス直下の床を支点に回転
    ed.wait(0.1)
    c1 = _cam(ed)
    t.ok(abs(c1["tgt"][2] - c0["tgt"][2]) > 0.05, f"前提: 回転で注視点のZが動いた（{c0['tgt'][2]:.3f}→{c1['tgt'][2]:.3f}）")
    ed.key("ArrowRight", ctrl=True)
    wait_until(ed, "window._dbgApp.state().cur>0&&!window._dbgApp.cam().anim", label="曲末への移動")
    ed.key("ArrowLeft", ctrl=True)
    _wait_seek(ed, 0)
    c2 = _cam(ed)
    t.ok(abs(c2["tgt"][2] - 4.08) < 1e-6, f"注視点のZが定位置の4.08へ戻る（{c2['tgt'][2]:.4f}）")
    t.ok(max(abs(a - b) for a, b in zip(c2["tgt"][:2], c1["tgt"][:2])) < 1e-6, "注視点の横位置・高さは回した後のまま")
    t.ok(max(abs(a - b) for a, b in zip(_offset(c2), _offset(c1))) < 1e-6, "カメラの向き・距離は回した後のまま")
    t.no_errors()


def test_edit_cam_seek_to_head(t):
    '''カメラ固定モード: 先頭・曲末への移動では従来どおり、向きを保ったまま注視点のZが再生ヘッド（0）へ寄る'''
    ed = open_ed(t)
    to_edit_cam(ed)
    c1 = _cam(ed)
    t.ok(abs(c1["tgt"][2]) > 1, f"前提: 俯瞰ビューの注視点はヘッドから離れている（Z={c1['tgt'][2]:.3f}）")
    ed.key("ArrowRight", ctrl=True)
    wait_until(ed, "window._dbgApp.state().cur>0&&!window._dbgApp.cam().anim", label="曲末への移動")
    c2 = _cam(ed)
    t.ok(abs(c2["tgt"][2]) < 1e-6, f"注視点のZが再生ヘッド（0）へ寄る（{c2['tgt'][2]:.4f}）")
    t.ok(max(abs(a - b) for a, b in zip(_offset(c2), _offset(c1))) < 1e-6, "カメラの向き・距離は変わらない")
    t.eq(c2["vwB"], None, "ビューの固定が外れてヘッド追従になる")
    t.eq(state(ed)["camMode"], "edit", "カメラ固定モードのまま")
    t.no_errors()

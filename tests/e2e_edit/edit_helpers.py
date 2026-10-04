"""e2e_edit グループ（3Dビューの編集）の共通部品。

状態は開発用窓口 window._dbgApp（読み取り専用）から読み、操作は本物のマウス/キー入力で行う。
- open_ed: 開き直して素材を読み、起動処理の完了まで待つ（各テストの最初に使う）
- mv: マウスを動かし、ページがその移動を受け取るまで待つ（キーの効き先＝マウスの下のペイン、が確定する）
- objs_on_screen / find_obj / click_obj / hover_obj: 3Dビューに見えているオブジェクトの画面座標とクリック
- off_grid / hover_off_grid: キャンバスのうち、マス・オブジェクトから離れた空き地（キー操作の前にマウスを置く）
- to_edit_cam: Q でカメラ固定モードへ（俯瞰。範囲選択・ライトの拍を選んだ配置に使う）
- drag_box: 左ドラッグでの範囲選択 / wheel: ホイール1刻み / pie_pick: パイメニュー（押したまま向けて離す）
- drag_handle: ギズモのつまみを画面上の向きにドラッグ（_dbgApp.gizmoScreen の座標）
- to_light_mode / light_lane / place_light / light_at: LIGHTING の切替・レーン上の画面座標・配置・検索
"""
import math

from e2e_helpers import wait_until, state, counts, cell

# ページが最後に受け取ったマウス位置（テスト側で足すリスナー。アプリ本体は変えない）。
# Chromium は mousemove をフレーム単位でまとめて遅れて届け、キーはすぐ届ける。キーの効き先（hoverPane）は
# マウスの移動で決まるため、PCが混んでいると「移動が届く前にキーが届いて別のペイン扱い」になることがある
_PTR_JS = """(()=>{ if(!window.__e2ePtr){ const p=window.__e2ePtr={x:-1e9,y:-1e9};
  addEventListener('pointermove',e=>{ p.x=e.clientX; p.y=e.clientY; },{passive:true}); } return true; })()"""


def mv(ed, x, y, **mods):
    """マウスを (x,y) へ動かし、ページがその移動を受け取ったのを待つ（同じ位置への移動は届かないことがあるので一度ずらす）"""
    ed.js(_PTR_JS)
    ed.move(x + 3, y + 3, **mods)
    ed.move(x, y, **mods)
    wait_until(ed, f"(p=>Math.abs(p.x-({x}))<1.5&&Math.abs(p.y-({y}))<1.5)(window.__e2ePtr)", timeout=5.0,
               label=f"マウスの移動 ({x:.0f},{y:.0f}) がページに届く")


def open_ed(t, fx="basic"):
    """ページを開き直して素材を読み、起動処理の終わり（配置モードで始まる）と配置グリッドの表示を待つ。
    起動時の setCamMode('place') は非同期の初期化（アイコン読込の await の後）で走るため、cdp の wait_ready の後でも
    まだ終わっていないことがある。その間に Q を押すと初期値 'edit' からの切替になり、配置モードへ入ってしまう"""
    from e2e_helpers import open_fixture
    ed = open_fixture(t, fx)
    wait_until(ed, "window._dbgApp.state().camMode==='place'&&!!document.getElementById('pvVisStruct')?.innerHTML", timeout=10.0,
               label="起動処理の完了（配置モード）")
    wait_cells_on_screen(ed)
    return ed


def notes(ed):
    return ed.js("window._dbgApp.notes().notes")


def chains(ed):
    return ed.js("window._dbgApp.notes().chains")


def objs(ed):
    """ボム・壁・アーク"""
    return ed.js("window._dbgApp.objs()")


def edit(ed):
    return ed.js("window._dbgApp.edit()")


def lights(ed):
    return ed.js("window._dbgApp.lights().events")


def key_of(o):
    return (o["beat"], o["x"], o["y"], o["c"], o["d"])


def note_keys(ed):
    """ノーツを (拍, x, y, 色, 向き) の並べ替えた一覧で（順序に依らず比べる用）"""
    return sorted(key_of(n) for n in notes(ed))


def objs_on_screen(ed):
    return ed.js("window._dbgApp.objScreen()")


def find_obj(ed, kind="note", **kw):
    """種類と属性（beat/x/y/c）が一致する、画面に見えているオブジェクト（1個）。画面座標 sx,sy を含む"""
    hits = [o for o in objs_on_screen(ed) if o["kind"] == kind and all(abs(o[k] - v) < 1e-6 for k, v in kw.items())]
    assert len(hits) == 1, f"{kind} {kw} が1個に決まりません: {hits}"
    o = hits[0]
    assert o["inView"], f"{kind} {kw} が画面に出ていません: {o}"
    return o


def click_obj(ed, kind="note", shift=False, **kw):
    """オブジェクトをクリック（Shift付き=追加/解除）。押す前にホバーして判定を落ち着かせる"""
    o = find_obj(ed, kind, **kw)
    mv(ed, o["sx"], o["sy"], shift=shift)
    ed.click(o["sx"], o["sy"], shift=shift)
    ed.wait(0.1)
    return o


def hover_obj(ed, kind="note", **kw):
    """オブジェクトの上にマウスを置く（F/D/Alt+ホイールは「カーソル直下が選択中なら選択全体へ」）"""
    o = find_obj(ed, kind, **kw)
    mv(ed, o["sx"], o["sy"])
    return o


def sel_keys(ed):
    """選択中のノーツの (拍, x, y)"""
    return sorted((o["beat"], o["x"], o["y"]) for o in objs_on_screen(ed) if o["sel"])


def canvas_rect(ed):
    return ed.js("(()=>{const r=document.getElementById('cv').getBoundingClientRect();return {x:r.left,y:r.top,w:r.width,h:r.height}})()")


def off_grid(ed):
    """キャンバスの左下寄り＝配置モードのマス・ノーツ・ライトレーンから離れた所（カメラの向きによらず空きであることを確かめて返す）"""
    r = canvas_rect(ed)
    for fx, fy in ((0.12, 0.85), (0.08, 0.6), (0.95, 0.9), (0.5, 0.95)):
        x, y = r["x"] + r["w"] * fx, r["y"] + r["h"] * fy
        ok = ed.js(f"""(()=>{{const e=document.elementFromPoint({x},{y}); if(!e||e.id!=='cv') return false;
          return !window._dbgApp.objScreen().some(o=>Math.hypot(o.sx-{x},o.sy-{y})<60); }})()""")
        if ok:
            return {"x": x, "y": y}
    raise AssertionError("キャンバスに空いた場所が見つかりません")


def hover_off_grid(ed):
    p = off_grid(ed)
    mv(ed, p["x"], p["y"])
    return p


def wait_cells_on_screen(ed):
    """配置モードの定位置カメラが落ち着き、マスが画面に入るまで待つ（e2e_helpers.place_at と同じ方式）"""
    wait_until(ed, "[[0,0],[3,0],[0,2],[3,2]].every(([x,y])=>(p=>p&&p.onScreen)(window._dbgApp.cellScreen(x,y)))", timeout=5.0,
               label="配置グリッドが画面に入る")


def to_edit_cam(ed):
    """Q でカメラ固定モード（俯瞰）へ。カメラの移動は即時。
    キーの効き先はマウスの下のペインで決まるので、必ずキャンバスの空き地にマウスを置いてから押す
    （e2e_helpers.hover_3d の位置は、カメラが動いている途中だとツールバーやNLEに掛かることがある）"""
    hover_off_grid(ed)
    assert state(ed)["camMode"] == "place", "前提: 配置モード（open_ed で起動処理の完了を待つこと）"
    ed.key("q")
    wait_until(ed, "window._dbgApp.state().camMode==='edit'", label="カメラ固定モードへ")
    ed.wait(0.15)


def drag_box(ed, x0, y0, x1, y1, shift=False):
    """左ドラッグで範囲選択（押す位置は空き地であること）"""
    mv(ed, x0, y0, shift=shift)
    ed.drag(x0, y0, x1, y1, steps=8, shift=shift)
    ed.wait(0.1)


def bbox_of(points, pad=14):
    xs = [p["sx"] for p in points]; ys = [p["sy"] for p in points]
    return min(xs) - pad, min(ys) - pad, max(xs) + pad, max(ys) + pad


def undo(ed):
    ed.key("z", ctrl=True)


def redo(ed):
    ed.key("z", ctrl=True, shift=True)


def wheel(ed, x, y, dy, **mods):
    """ホイール1刻み（dy>0=手前へ回す＝下スクロール）"""
    if not ed.js(f"(p=>!!p&&Math.abs(p.x-({x}))<1.5&&Math.abs(p.y-({y}))<1.5)(window.__e2ePtr)"):
        mv(ed, x, y, **mods)
    ed.wheel(x, y, dy, **mods)
    ed.js("new Promise(r=>requestAnimationFrame(()=>r(0)))")   # ホイールの処理が終わるのを1フレーム待つ


def frames(ed, n=2):
    """描画のフレームを n 回待つ"""
    ed.js("new Promise(r=>{let k=%d;const f=()=>(--k>0?requestAnimationFrame(f):r(0));requestAnimationFrame(f);})" % n)


def drag_handle(ed, axis, sign, dist_px=None, to=None, steps=10):
    """ギズモのつまみ（axis/sign）を、中心→つまみの画面上の向きへ dist_px だけ（または to の座標へ）ドラッグする"""
    wait_until(ed, f"window._dbgApp.gizmoScreen().handles.some(h=>h.axis==='{axis}'&&h.sign==={sign})", label=f"つまみ {axis}{sign:+d} の表示")
    frames(ed)   # つまみの位置は描画のたびに選択物へ寄せ直す＝Undo直後などは次のフレームまで古い位置のまま
    g = ed.js("window._dbgApp.gizmoScreen()")
    hs = [h for h in g["handles"] if h["axis"] == axis and h["sign"] == sign]
    assert g["visible"] and hs, f"ギズモのつまみ {axis}{sign:+d} が出ていません: {g}"
    h, c = hs[0], g["center"]
    assert h["onScreen"], f"つまみが画面外: {h}"
    if to is None:
        vx, vy = h["x"] - c["x"], h["y"] - c["y"]
        n = math.hypot(vx, vy) or 1.0
        to = {"x": h["x"] + vx / n * dist_px, "y": h["y"] + vy / n * dist_px}
    mv(ed, h["x"], h["y"])
    ed.drag(h["x"], h["y"], to["x"], to["y"], steps=steps)
    ed.wait(0.15)
    return h


def _key_event(ed, typ, key):
    """1文字キーの keyDown / keyUp だけを送る（cdp.Editor.key は押して離すまで一度に送るため、押したまま動かす操作に使う）"""
    base = dict(key=key, code="Key" + key.upper(), windowsVirtualKeyCode=ord(key.upper()), nativeVirtualKeyCode=ord(key.upper()), modifiers=0)
    if typ == "down":
        ed.call("Input.dispatchKeyEvent", type="keyDown", text=key, **base)
    else:
        ed.call("Input.dispatchKeyEvent", type="keyUp", **base)


def pie_pick(ed, key, angle, r=70):
    """パイメニュー（W/C等）: キーを押したまま、パイの中心から angle 度（0=上・時計回り）の向きへマウスを動かし、
    キーを離して確定する（画面の説明どおり「離して確定」）"""
    _key_event(ed, "down", key)
    wait_until(ed, "window._dbgApp.edit().pie===true", label=f"{key} のパイが開く")
    c = ed.js("(()=>{const e=document.getElementById('pie');return {x:parseFloat(e.style.left),y:parseFloat(e.style.top)}})()")
    a = math.radians(angle - 90)
    x, y = c["x"] + math.cos(a) * r, c["y"] + math.sin(a) * r
    mv(ed, x, y)
    _key_event(ed, "up", key)
    wait_until(ed, "window._dbgApp.edit().pie===false", label="パイが閉じる")
    ed.wait(0.05)


# ---- LIGHTING ----
LIGHT_ET = [9, 8, 4, 13, 3, 12, 2, 1, 0, 5]   # レーン番号(0=左端)→イベント種別（editor-app.js の LIGHT_LANES の並び）


def to_light_mode(ed):
    hover_off_grid(ed)
    ed.key("Tab")
    wait_until(ed, "window._dbgApp.state().lightMode===true", label="LIGHTING へ切替")
    ed.wait(0.1)


def light_lane(ed, li, beat):
    p = ed.js(f"window._dbgApp.lightLaneScreen({li},{beat})")
    assert p and p["inView"], f"ライトレーン {li} 拍{beat} が画面に出ていません: {p}"
    hit = ed.js(f"(e=>e&&e.id)(document.elementFromPoint({p['x']},{p['y']}))")
    assert hit == "cv", f"ライトレーン {li} 拍{beat} の上に別の要素があります: {hit}"
    return p


def light_at(ed, li, beat):
    """レーン li・拍 beat のライト（無ければ None）"""
    et = LIGHT_ET[li]
    hs = [e for e in lights(ed) if e["et"] == et and abs(e["beat"] - beat) < 1e-6]
    return hs[0] if hs else None


def place_light(ed, li, beat):
    """カメラ固定モードのライトレーン（li, beat）をクリックしてライトを置く"""
    n0 = counts(ed)["lights"]
    p = light_lane(ed, li, beat)
    mv(ed, p["x"], p["y"])
    ed.click(p["x"], p["y"])
    wait_until(ed, f"window._dbgApp.state().counts.lights==={n0 + 1}", label=f"ライト配置 レーン{li} 拍{beat}")
    return p

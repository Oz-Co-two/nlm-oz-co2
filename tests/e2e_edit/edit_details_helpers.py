"""test_edit_details.py（3Dビュー・ライト・再生まわりの細かい所）の部品。

edit_helpers.py（同じグループの共通部品）を土台に、次を足す:
- place_wall: 段階式で壁を1つ置く（拍0・列1〜2・段0〜1・奥行き2拍。確定した壁は選択中）
- handle_press_drag: ギズモのつまみを押したまま少しずつ動かし、条件を満たした所で（さらに少し動かして）離す
- light_rows: 今の難易度のライト（拍・種別・値・強さ・クロマ色）。色は _dbgApp.lights() に無いので保存内容から読む
- hex01: '#rrggbb' → クロマ色の [r,g,b]（アプリと同じく 0〜1・小数3桁）
- click_el / set_setting_checkbox: 画面の要素のクリックと、環境設定のチェックボックスの切替（本物のクリック）
- hover_3d_empty / hover_pv / hover_nle: キーの効き先（マウスの下のペイン）を決めるためのマウスの置き場所
- osc_log: ページ内の OscillatorNode.start を記録する（メトロノームのクリック音＝1760Hz・通過音＝880Hz を数える）
"""
import json
import math

from e2e_helpers import wait_until, cell, project, state
from edit_helpers import mv, pie_pick, hover_off_grid, frames, canvas_rect


# ---- 壁 ----
def _click_cell(ed, x, y):
    p = cell(ed, x, y)
    mv(ed, p['x'], p['y'])
    ed.click(p['x'], p['y'])


def place_wall(ed):
    """Wパイで壁→マス(1,0)をクリック→横幅(2,0)=2列→高さ(2,1)=2段→奥行き=床の拍2 で確定（test_wall.py と同じ手順）"""
    hover_off_grid(ed)
    pie_pick(ed, 'w', 240)   # 配置パイ: 上=ノーツ・右下=ボム・左下(240°)=壁
    wait_until(ed, "window._dbgApp.state().brush.type==='wall'", label='Wパイで壁')
    _click_cell(ed, 1, 0)
    wait_until(ed, "window._dbgApp.edit().wallStage==='width'", label='仮配置→横幅の調整')
    p = cell(ed, 2, 0); mv(ed, p['x'], p['y'])
    wait_until(ed, "window._dbgApp.objs().walls[0]?.w===2", label='横幅が2列に')
    _click_cell(ed, 2, 0)
    wait_until(ed, "window._dbgApp.edit().wallStage==='height'", label='高さの調整へ')
    p = cell(ed, 2, 1); mv(ed, p['x'], p['y'])
    wait_until(ed, "window._dbgApp.objs().walls[0]?.h===2", label='高さが2段に')
    _click_cell(ed, 2, 1)
    wait_until(ed, "window._dbgApp.edit().wallStage==='depth'", label='奥行きの調整へ')
    p = ed.js("window._dbgApp.lightLaneScreen(0,2)")   # 床の上の拍2（奥行きは床の拍で決まる）
    mv(ed, p['x'], p['y'])
    wait_until(ed, "window._dbgApp.objs().walls[0]?.dur===2", label='奥行きが2拍に')
    ed.click(p['x'], p['y'])
    wait_until(ed, "window._dbgApp.edit().wallStage===null", label='壁の確定')


def wall(ed):
    ws = ed.js("window._dbgApp.objs().walls")
    assert len(ws) == 1, ws
    return {k: ws[0][k] for k in ('beat', 'x', 'y', 'w', 'h', 'dur')}


# ---- ギズモのつまみを押したまま動かす ----
def handle_press_drag(ed, axis, sign, inward=False, until=None, extra_px=0, watch=None, step_px=5, max_px=420):
    """つまみ（axis/sign）を押し、中心→つまみの画面上の向き（inward=True なら逆向き＝箱の内側へ）に step_px ずつ動かす。
    until（JS式）が真になったら、さらに extra_px だけ動かしてから離す（until=None なら max_px まで動かす）。
    戻り値: (until が真になったか, 動かすたびの watch（JS式）の値の一覧)。キャンバスの外へは出さない"""
    wait_until(ed, f"window._dbgApp.gizmoScreen().handles.some(h=>h.axis==='{axis}'&&h.sign==={sign})", label=f"つまみ {axis}{sign:+d} の表示")
    frames(ed)   # つまみの位置は描画のたびに選択物へ寄せ直す＝直前の変更・Undoの後は次のフレームまで古い位置のまま
    g = ed.js("window._dbgApp.gizmoScreen()")
    h = [h for h in g['handles'] if h['axis'] == axis and h['sign'] == sign][0]
    c = g['center']
    assert h['onScreen'], f"つまみが画面外: {h}"
    vx, vy = h['x'] - c['x'], h['y'] - c['y']
    n = math.hypot(vx, vy) or 1.0
    vx, vy = vx / n, vy / n
    if inward:
        vx, vy = -vx, -vy
    if until is None and watch is None:
        step_px = max(step_px, 20)   # 途中を見ないなら大きく動かす（速さのため）
    r = canvas_rect(ed)
    mv(ed, h['x'], h['y'])
    ed.call("Input.dispatchMouseEvent", type="mousePressed", x=h['x'], y=h['y'], button="left", buttons=1, clickCount=1, modifiers=0)
    seen, reached, stop_at, d = [], False, max_px, 0
    x, y = h['x'], h['y']
    while d < stop_at:
        d += step_px
        nx, ny = h['x'] + vx * d, h['y'] + vy * d
        if not (r['x'] + 4 < nx < r['x'] + r['w'] - 4 and r['y'] + 4 < ny < r['y'] + r['h'] - 4):
            break
        x, y = nx, ny
        ed.call("Input.dispatchMouseEvent", type="mouseMoved", x=x, y=y, button="left", buttons=1, modifiers=0)
        # mousemove はフレーム単位でまとめて届くことがある＝ページが受け取ったのを確かめてから状態を見る（1往復で済ませる）
        probe = (f"(p=>!!p&&Math.abs(p.x-({x}))<1.5&&Math.abs(p.y-({y}))<1.5)(window.__e2ePtr)?"
                 f"[{watch or 'null'},{until or 'false'}]:null")
        v = None
        for _ in range(50):
            v = ed.js(probe)
            if v is not None:
                break
            ed.wait(0.01)
        assert v is not None, f"マウスの移動 ({x:.0f},{y:.0f}) がページに届きません"
        if watch:
            seen.append(v[0])
        if until and not reached and v[1]:
            reached, stop_at = True, d + extra_px
    ed.call("Input.dispatchMouseEvent", type="mouseReleased", x=x, y=y, button="left", buttons=0, clickCount=1, modifiers=0)
    ed.wait(0.1)
    return reached, seen


# ---- ライト ----
def hex01(h):
    """'#rrggbb' → アプリが customData.color に書く 0〜1 の RGB（小数3桁に丸める）"""
    n = int(h.lstrip('#'), 16)
    return [round(((n >> s) & 255) / 255, 3) for s in (16, 8, 0)]


def light_rows(ed):
    """今の難易度のライトを [{beat, et, i, f, color}] で。color はクロマ色の [r,g,b]（無ければ None）。
    _dbgApp.lights() は raw（customData）を省くので、アプリ自身の保存内容（buildProjectText）から読む
    （lightEvents は [拍, 種別, 値, 強さ, レーン, 標準外の項目] の配列）"""
    pj = project(ed)
    d = pj['difficulties'][state(ed)['diff'].lower()]
    out = []
    for a in d.get('lightEvents') or []:
        raw = a[5] if len(a) > 5 else None
        col = ((raw or {}).get('customData') or {}).get('color')
        out.append({'beat': a[0], 'et': a[1], 'i': a[2], 'f': a[3], 'color': [round(v, 3) for v in col[:3]] if col else None})
    return sorted(out, key=lambda e: (e['beat'], e['et']))


def light_row(ed, beat, et):
    hs = [e for e in light_rows(ed) if abs(e['beat'] - beat) < 1e-6 and e['et'] == et]
    return hs[0] if hs else None


# ---- 画面の要素 ----
def el_center(ed, sel):
    return ed.js(f"""(()=>{{const e=document.querySelector({sel!r}); if(!e) return null; const r=e.getBoundingClientRect();
      if(!(r.width>0&&r.height>0)) return null; const x=r.left+r.width/2, y=r.top+r.height/2, h=document.elementFromPoint(x,y);
      return {{x,y,hit:!!h&&(h===e||e.contains(h))}}; }})()""")


def click_el(ed, sel, label=None):
    """要素の中央を本物のクリックで押す（表示されていて、手前に別の要素が無いことを確かめてから）"""
    p = wait_until(ed, f"""(()=>{{const e=document.querySelector({sel!r}); const r=e&&e.getBoundingClientRect(); return !!r&&r.width>0&&r.height>0; }})()""",
                   label=label or f'{sel} の表示')
    p = el_center(ed, sel)
    assert p and p['hit'], f"{sel} の上に別の要素があります: {p}"
    mv(ed, p['x'], p['y'])
    ed.click(p['x'], p['y'])
    return p


DEFAULT_SETTINGS = {'bsnm_chroma': '0', 'bsnm_swingwarn': '1', 'bsnm_auxprev': '1'}   # config/settings.default.json と各設定の既定値


def restore_settings(ed, *keys):
    """このテストで変えた環境設定を既定へ戻し、設定ファイル（一時フォルダの config/settings.json）に書かれるまで待つ。
    環境設定（bsnm_*）は localStorage から settings.json へ0.4秒遅れでミラーされ、開き直すと読み戻される
    （t.fresh の localStorage の消去だけでは戻らない）＝戻して書かれるのを待たないと、同じグループの後のテストに漏れる"""
    vals = json.dumps({k: DEFAULT_SETTINGS[k] for k in keys})
    ed.js(f"(v=>{{ for(const k in v) localStorage.setItem(k,v[k]); return true; }})({vals})")
    wait_until(ed, f"""(async v=>{{ const o=await (await fetch('config/settings.json?v='+Date.now(),{{cache:'no-store'}})).json();
      return Object.keys(v).every(k=>o[k]===v[k]); }})({vals})""", label=f'設定ファイルが既定へ戻る {keys}')


def set_setting_checkbox(ed, cid, on):
    """環境設定（メニューバーの歯車）を開き、チェックボックス cid を on/off にして閉じる"""
    click_el(ed, '#mbSettings')
    wait_until(ed, "document.getElementById('settingsBg').style.display==='flex'", label='環境設定が開く')
    ed.js(f"document.getElementById({cid!r}).scrollIntoView({{block:'center'}})")   # 利用者がスクロールして見える所へ出すのと同じ
    if ed.js(f"document.getElementById({cid!r}).checked") != on:
        click_el(ed, '#' + cid)
        wait_until(ed, f"document.getElementById({cid!r}).checked==={str(on).lower()}", label=f'{cid} を {on} に')
    click_el(ed, '#settingsClose')
    wait_until(ed, "document.getElementById('settingsBg').style.display==='none'", label='環境設定が閉じる')


# ---- マウスの置き場所（キーの効き先） ----
def hover_3d_empty(ed):
    """3Dビューのうちマス・オブジェクトから離れた空き地（edit_helpers.hover_off_grid と同じ）"""
    return hover_off_grid(ed)


def hover_pv(ed):
    """左上のペイン（MEDIA / PREVIEW）の上。ボタン類の無い所を選ぶ"""
    p = ed.js("""(()=>{const r=document.getElementById('pvpane').getBoundingClientRect();
      for(const [fx,fy] of [[0.5,0.6],[0.3,0.7],[0.7,0.5],[0.5,0.85]]){ const x=r.left+r.width*fx, y=r.top+r.height*fy, e=document.elementFromPoint(x,y);
        if(e&&e.closest('#pvpane')&&!e.closest('button,input,select,.tbi')) return {x,y}; }
      return null; })()""")
    assert p, '左上のペインに空いた場所がありません'
    mv(ed, p['x'], p['y'])
    return p


def hover_nle(ed, beat, track=0):
    """NLE（レイヤービュー）のノーツのレーン track の、拍 beat の上"""
    s = ed.js(f"window._dbgApp.nleScreen({beat})")
    x, y = s['x'], s['notes'][track] + s['laneH'] * 0.5
    mv(ed, x, y)
    wait_until(ed, f"Math.abs((window._dbgApp.nle().hover??-99)-{beat})<0.3", label=f'NLEの拍{beat}にマウス')
    return {'x': x, 'y': y}


# ---- 音（ヘッドレスでも AudioContext の時間は進む＝鳴らした音の数を数える） ----
OSC_LOG_JS = """(()=>{ if(window.__oscLog){ window.__oscLog.length=0; return true; }
  const log=window.__oscLog=[], P=OscillatorNode.prototype, st=P.start;
  P.start=function(...a){ try{ log.push(Math.round(this.frequency.value)); }catch(_){} return st.apply(this,a); };
  return true; })()"""


def osc_log(ed, reset=False):
    """ページ内で鳴らした発振音の周波数の一覧（reset=True で記録を始め直す）"""
    if reset:
        ed.js(OSC_LOG_JS)
        return []
    return ed.js("window.__oscLog?[...window.__oscLog]:[]")

"""曲の音量補正（NLE の Music レーンの左溝の「音量」と「自動調整」・2026-10-18）。
値は songNode.gainDb（プロジェクトに保存・Undo の対象）で、再生は songGain（Web Audio の音量部品）に効く。
書き出し（song.egg への焼き込み）は e2e_misc/test_music_egg.py、ffmpeg の処理は unit_py/test_egg_segments.py、
測り方と「自動」の値の決め方は unit_js/test_loudness.py。素材 basic は 120BPM・16秒のクリック音（振幅0.6）"""
import json
import re

from e2e_helpers import project, wait_until
from nle_helpers import nle_mouse, open_nle, take_errors, undo

F = "#gainField"


def _gain(ed):
    return ed.js("window._dbgApp.songGain()")


def _center(ed, sel):
    return wait_until(ed, f"""(()=>{{ const e=document.querySelector({json.dumps(sel)}); if(!e) return null;
      const r=e.getBoundingClientRect(); return r.width>0?{{x:r.left+r.width/2,y:r.top+r.height/2}}:null; }})()""", label=f"{sel} が表示される")


def _click(ed, sel, **mods):
    p = _center(ed, sel)
    ed.click(p["x"], p["y"], **mods)


def _text(ed):
    return ed.js(f"document.querySelector('{F} .bfV').textContent")


def _type_value(ed, text):
    _click(ed, F + " .bfV")
    wait_until(ed, f"!!document.querySelector('{F} .bfV input')", label="手入力の欄")
    ed.key("a", ctrl=True)
    ed.call("Input.insertText", text=text)
    ed.key("Enter")


def _toast(ed):
    return ed.js("(()=>{const e=document.getElementById('errToast');return e&&e.style.display!=='none'?e.textContent:''})()")


def _wait_applied(ed, db):
    """再生の音量部品が db（dB）の倍率になるまで待つ（30ms かけて変える）"""
    wait_until(ed, f"(g=>g.applied==={db}&&Math.abs(g.param-{10 ** (db / 20)})<1e-3)(window._dbgApp.songGain())",
               label=f"再生の音量が {db} dB")


def test_gain_stepper(t):
    '''‹›で±0.5dB・Shift+‹›で±0.1dB・数値クリックで手入力（±20dB に収める）。値は保存内容に入り、再生の音量部品に効く。
    Undo で戻り、0 に戻すと保存内容からも消える（未保存の印も消える）'''
    ed = open_nle(t, "basic")
    t.eq(_gain(ed)["db"], 0, "最初は 0")
    _wait_applied(ed, 0)
    t.eq(_text(ed), "0.0 dB", "表示")
    _click(ed, F + " .bfA[data-k='up']")
    t.eq(_gain(ed)["db"], 0.5, "› で +0.5")
    _click(ed, F + " .bfA[data-k='up']", shift=True)
    wait_until(ed, "window._dbgApp.songGain().db===0.6", label="Shift+› で +0.1")
    _click(ed, F + " .bfA[data-k='dn']")
    wait_until(ed, "window._dbgApp.songGain().db===0.1", label="‹ で -0.5")
    wait_until(ed, f"document.querySelector('{F} .bfV').textContent==='+0.1 dB'", label="表示 +0.1 dB")
    _type_value(ed, "-3.26")
    wait_until(ed, "window._dbgApp.songGain().db===-3.3", label="手入力（0.1dB に丸める）")
    t.eq(_text(ed), "-3.3 dB", "表示（マイナス）")
    _wait_applied(ed, -3.3)
    _type_value(ed, "50")
    wait_until(ed, "window._dbgApp.songGain().db===20", label="上限 +20")
    _wait_applied(ed, 20)
    t.eq(project(ed)["graph"]["song"].get("gainDb"), 20, "保存内容（graph.song.gainDb）")
    wait_until(ed, "window._dbgApp.dirty().same===false", label="未保存の印")
    nle_mouse(ed)
    undo(ed)
    wait_until(ed, "window._dbgApp.songGain().db===-3.3", label="Undo で前の値")
    _wait_applied(ed, -3.3)
    _type_value(ed, "0")
    wait_until(ed, "window._dbgApp.songGain().db===0", label="0 に戻す")
    t.ok("gainDb" not in project(ed)["graph"]["song"], "0 なら保存内容に持たない")
    wait_until(ed, "window._dbgApp.dirty().same===true", label="元に戻せば未保存の印も消える")
    t.no_errors()


def test_gain_auto(t):
    '''「自動調整」: 曲を測って、平均 -9 LUFS を目標に、ピークが -1 dB を超えない所まで上げる。素材はまばらなクリック音で
    平均がとても小さい＝ピークで止まる。もう一度押しても同じ値（元の音源を測るので、補正後の音を測り直して上げ続けない）。Undo で戻る'''
    ed = open_nle(t, "basic")
    _click(ed, "#gainAutoBtn")
    wait_until(ed, "/音量補正を/.test(document.getElementById('errToast').textContent)", label="自動の結果のメッセージ")
    msg = _toast(ed)
    db = _gain(ed)["db"]
    m = re.search(r"平均 (-?[\d.]+) → (-?[\d.]+) LUFS・ピーク (-?[\d.]+) → (-?[\d.]+) dB", msg)
    t.ok(m, f"メッセージ: {msg}")
    l0, l1, p0, p1 = (float(v) for v in m.groups())
    t.ok(db > 0, f"上がる: {db}")
    t.ok(-1.1 <= p1 <= -1.0, f"ピークが -1 dB の手前で止まる: {msg}")
    t.ok(l1 < -9, f"目標の手前: {msg}")
    t.ok("音が割れます" in msg, f"ピークで止めた旨: {msg}")
    t.eq(_text(ed), f"+{db:.1f} dB", "帯の表示")
    _wait_applied(ed, db)
    _click(ed, "#gainAutoBtn")
    ed.wait(0.3)
    t.eq(_gain(ed)["db"], db, "もう一度押しても同じ値")
    nle_mouse(ed)
    undo(ed)
    wait_until(ed, "window._dbgApp.songGain().db===0", label="Undo で 0 に戻る")
    t.no_errors()


def test_gain_auto_without_audio(t):
    '''音源が無い時の「自動調整」は、測れない旨を出して何も変えない'''
    ed = open_nle(t)
    _click(ed, "#gainAutoBtn")
    wait_until(ed, "/音量を測れません/.test(document.getElementById('errToast').textContent)", label="音源が無い旨")
    t.eq(_gain(ed)["db"], 0, "変わらない")
    t.eq(take_errors(ed, "音量を測れません"), 1, "エラー表示")
    t.no_errors()

"""譜面チェックの NLM版 BL評価リスト: R5.A（視界ブロック）の★/Tech を「難易度を測る」プラグインで自動で入れる。
★は R11.H.5（難易度が★の低い順・0.5★まで許容）の判定にも使う。プラグインの状態・測定結果は「難易度を測る」パネルと共有。
/__rating/* の応答はページ内の偽物（test_rating.py と同じ。GitHub への通信・実行ファイルの取り込みは一切しない）。"""
import json

from misc_helpers import (RATING_INSTALLED, RATING_NONE, click_in_view, click_sel, file_menu, open_fixture_ready, rating_calls,
                          rating_open_via_menu, rating_spy, type_text, wait_until)
from e2e_helpers import place_at


def _res(hard, expert):
    """測定結果（偽物）。hard/expert=(★, Tech) か None（ノーツ20個未満で測れない）"""
    def one(dn, v):
        if v is None:
            return {"characteristic": "Standard", "difficulty": dn, "skipped": "tooFewNotes", "notes": 12, "ratings": {}}
        return {"characteristic": "Standard", "difficulty": dn, "skipped": None, "notes": 40,
                "ratings": {"none": {"stars": v[0], "pass": 2.0, "tech": v[1], "acc": 5.0, "predictedAcc": 0.95}}}
    return {"ok": True, "version": "0.1.0", "elapsedMs": 900, "results": [one("Hard", hard), one("Expert", expert)]}


M1 = _res((3.214, 1.5), (4.567, 2.25))
M2 = _res((3.5, 1.8), (5.1, 2.6))
_MC_DONE = ("(()=>{const p=document.getElementById('mcPanel');return !!p&&p.style.display!=='none'"
            "&&!p.querySelector('.mcRerun').disabled&&p.querySelector('.mcBody').children.length>0})()")


def _open_mapcheck(ed):
    file_menu(ed, "mapcheck")
    wait_until(ed, _MC_DONE, timeout=20, label="チェック結果の表示")


def _to_bl(ed):
    click_sel(ed, "#mcPanel .mcTab[data-tab=bl]", "BL評価リストのタブ")
    wait_until(ed, "document.getElementById('mcPanel').classList.contains('blMode')&&!!document.querySelector('#mcPanel .blStarsBox')",
               label="BL評価リストの★/Techの欄")


def _rule(ed, rid):
    """評価リストの1項目: 状態（st-…）と所見の文字"""
    return ed.js(f"""(()=>{{const r=[...document.querySelectorAll('#mcPanel .blRule')].find(x=>x.querySelector('.blId').textContent==={json.dumps(rid)});
      return r?{{st:[...r.classList].find(c=>c.startsWith('st-')),fs:[...r.querySelectorAll('.blF')].map(f=>f.textContent)}}:null}})()""")


def _val(ed, k, dn):
    return ed.js(f"(()=>{{const i=document.querySelector('#mcPanel input[data-{k}=\"{dn}\"]');return i?i.value:null}})()")


def _box(ed):
    return ed.js("document.querySelector('#mcPanel .blStarsBox').textContent")


def _measures(ed):
    return len([c for c in rating_calls(ed) if c["act"] == "measure"])


def _min_ms(ed, star, tech):
    return ed.js(f"(async()=>{{const m=await import('./js/mapcheck/blcriteria.js');return Math.round(m.visionMinMs({star},{tech}))}})()")


# ---------------------------------------------------------------- 導入済み: 自動で入る・測り直す条件
def test_bl_stars_auto(t):
    '''プラグイン導入済み: BS Map Check のタブでは通信しない→BL評価リストを開くと自動で測り、★/Techの欄に入って R5.A・R11.H.5 が判定される。
    譜面がそのままの再チェックでは測り直さず、「↻ 再計算」と、譜面を直した後の再チェックでは測り直す'''
    ed = open_fixture_ready(t, 'rich')
    ed.js("localStorage.setItem('bsnm_mcTab','mc')")
    rating_spy(ed, {"status": RATING_INSTALLED, "measure": M1})
    _open_mapcheck(ed)
    ed.wait(0.3)
    t.eq(rating_calls(ed), [], "BS Map Check のタブでは状態の確認も測定もしない")
    _to_bl(ed)
    wait_until(ed, "(()=>{const i=document.querySelector('#mcPanel input[data-star=\"Hard\"]');return !!i&&i.value!==''})()", label="自動で入る")
    t.eq([c["act"] for c in rating_calls(ed)], ["status", "measure"], "BL評価リストを開くと状態を確かめて測る")
    t.eq([_val(ed, "star", "Hard"), _val(ed, "tech", "Hard"), _val(ed, "star", "Expert"), _val(ed, "tech", "Expert")],
         ["3.21", "1.5", "4.57", "2.25"], "★/Tech の欄（小数2桁）")
    t.ok("nlm-rating v0.1.0 による近似値" in _box(ed) and "公式の値ではありません" in _box(ed), f"近似値・公式ではない旨: {_box(ed)}")
    t.eq(ed.js("document.querySelector('#mcPanel .blRtRun').textContent"), "↻ 再計算", "ボタンは再計算")
    r5 = _rule(ed, "R5.A")
    t.ok(not any("入ると判定します" in f for f in r5["fs"]), f"R5.A は★/Techが入って判定される: {r5['fs']}")
    ms = _min_ms(ed, 3.214, 1.5)
    t.ok(any(f.startswith("Hard") and f"{ms}ms" in f for f in r5["fs"]), f"Hard は最小時間 {ms}ms で判定: {r5['fs']}")
    r11 = _rule(ed, "R11.H.5")
    t.eq(r11, {"st": "st-pass", "fs": ["★の並び: Hard ★3.21 → Expert ★4.57"]}, "R11.H.5（★の並び）")
    # 譜面がそのままの再チェック → 測り直さない
    click_sel(ed, "#mcPanel .mcRerun", "再チェック")
    wait_until(ed, _MC_DONE, label="再チェック")
    ed.wait(0.3)
    t.eq(_measures(ed), 1, "譜面がそのままなら再チェックしても測り直さない")
    # ↻ 再計算 → 測り直す
    click_in_view(ed, "#mcPanel .blRtRun", "↻ 再計算")
    wait_until(ed, "window.__rt.calls.filter(c=>c.act==='measure').length===2", label="再計算")
    # 譜面を直して開き直す（タブは BL評価リストのまま）→ 直した内容を測る
    click_sel(ed, "#mcPanel .mcClose", "閉じる")
    place_at(ed, 1, 2)
    _open_mapcheck(ed)
    wait_until(ed, "window.__rt.calls.filter(c=>c.act==='measure').length===3", label="直した後は測り直す")
    hard = json.loads(next(f for f in rating_calls(ed)[-1]["body"]["files"] if f["name"] == "HardStandard.dat")["text"])
    first = json.loads(next(f for f in rating_calls(ed)[1]["body"]["files"] if f["name"] == "HardStandard.dat")["text"])
    t.eq(len(hard["colorNotes"]), len(first["colorNotes"]) + 1, "置いたノーツが入っている")
    t.no_errors()


def test_bl_stars_manual_override(t):
    '''手で書き換えた欄は「手入力」になり、判定に使われ、測り直しても上書きされない（手入力でない欄は新しい値になる）。「自動に戻す」で自動の値へ戻る。
    ★の並びが0.5★を超えて逆転すると R11.H.5 が要確認になる'''
    ed = open_fixture_ready(t, 'rich')
    rating_spy(ed, {"status": RATING_INSTALLED, "measure": [M1, M2]})
    _open_mapcheck(ed)
    _to_bl(ed)
    wait_until(ed, "document.querySelector('#mcPanel input[data-star=\"Hard\"]').value==='3.21'", label="自動で入る")
    # Hard の★を 6 に書き換える（本物の入力。欄を離れた時に確定）
    click_in_view(ed, '#mcPanel input[data-star="Hard"]', "Hard の★の欄")
    ed.js("document.activeElement.select()")
    type_text(ed, "6")
    click_sel(ed, "#mcPanel .mcTitle", "欄を離れる")
    wait_until(ed, "!!document.querySelector('#mcPanel .blStarMan')", label="手入力の表示")
    t.eq(ed.js("document.querySelector('#mcPanel input[data-star=\"Hard\"]').classList.contains('man')"), True, "手入力の欄は印が付く")
    t.eq(ed.js("document.querySelector('#mcPanel input[data-tech=\"Hard\"]').classList.contains('man')"), False, "書き換えていない欄は自動のまま")
    ms = _min_ms(ed, 6, 1.5)
    t.ok(any(f.startswith("Hard") and f"{ms}ms" in f for f in _rule(ed, "R5.A")["fs"]), f"R5.A は手入力の★で判定（{ms}ms）")
    r11 = _rule(ed, "R11.H.5")
    t.eq(r11["st"], "st-check", f"Expert（★4.57）が Hard（★6）より0.5★を超えて低い→要確認: {r11}")
    t.ok(r11["fs"][0].startswith("Expert") and "Hard" in r11["fs"][0] and "★6.00" in r11["fs"][0], f"所見: {r11['fs']}")
    # 測り直す（新しい値）→ 手入力の★は残り、他の欄は新しい値
    click_in_view(ed, "#mcPanel .blRtRun", "↻ 再計算")
    wait_until(ed, "document.querySelector('#mcPanel input[data-star=\"Expert\"]').value==='5.1'", label="新しい値")
    t.eq([_val(ed, "star", "Hard"), _val(ed, "tech", "Hard"), _val(ed, "tech", "Expert")], ["6", "1.8", "2.6"], "手入力の欄だけ残る")
    # 自動に戻す
    click_in_view(ed, '#mcPanel .blStarAuto[data-dn="Hard"]', "自動に戻す")
    wait_until(ed, "!document.querySelector('#mcPanel .blStarMan')", label="手入力の表示が消える")
    t.eq(_val(ed, "star", "Hard"), "3.5", "自動の値に戻る")
    t.eq(_rule(ed, "R11.H.5")["st"], "st-pass", "★の並びも戻る")
    t.eq(_measures(ed), 2, "自動に戻すだけでは測らない")
    t.no_errors()


# ---------------------------------------------------------------- 未導入: 説明を見てから取り込む
def test_bl_stars_install_flow(t):
    '''プラグイン未導入: 開いただけでは通信しない。「取り込んで自動計算…」で説明（大きさ・配布元）→「やめる」で閉じる。
    「GitHub から取り込む」の失敗（ネット不通）はその場に赤い文→成功するとそのまま測って欄に入る。未導入の間も手入力で判定できる'''
    ed = open_fixture_ready(t, 'rich')
    rating_spy(ed, {"status": RATING_NONE, "install": [{"ok": False, "error": "network"}, RATING_INSTALLED], "measure": M1})
    _open_mapcheck(ed)
    _to_bl(ed)
    wait_until(ed, "!!document.querySelector('#mcPanel .blRtOpen')", label="取り込みのボタン")
    t.eq(ed.js("document.querySelector('#mcPanel .blRtOpen').textContent"), "📥 プラグインを取り込んで自動計算…", "取り込みのボタンの文言")
    t.eq([_val(ed, "star", "Hard"), _val(ed, "tech", "Hard")], ["", ""], "欄は空")
    t.ok(any("入ると判定します" in f for f in _rule(ed, "R5.A")["fs"]), "R5.A は未判定")
    t.eq(_rule(ed, "R11.H.5")["st"], "st-manual", "R11.H.5 は★が無いので手動確認")
    t.eq([c["act"] for c in rating_calls(ed)], ["status"], "開いただけでは状態の確認だけ")
    # 説明を開く→やめる
    click_in_view(ed, "#mcPanel .blRtOpen", "取り込んで自動計算…")
    wait_until(ed, "!!document.querySelector('#mcPanel .blRtBox')", label="取り込みの説明")
    box = ed.js("document.querySelector('#mcPanel .blRtBox').textContent")
    t.ok("約20MB" in box and "https://github.com/example/nlm-rating" in box and "plugins" in box, f"説明（大きさ・配布元・保存先）: {box}")
    t.eq([c["act"] for c in rating_calls(ed)], ["status"], "説明を開いただけでは通信しない")
    click_in_view(ed, "#mcPanel .blRtCancel", "やめる")
    wait_until(ed, "!document.querySelector('#mcPanel .blRtBox')&&!!document.querySelector('#mcPanel .blRtOpen')", label="説明を閉じる")
    # 未導入でも手入力で判定できる
    click_in_view(ed, '#mcPanel input[data-star="Hard"]', "Hard の★の欄")
    type_text(ed, "4")
    click_in_view(ed, '#mcPanel input[data-tech="Hard"]', "Hard のTechの欄")
    type_text(ed, "2")
    click_sel(ed, "#mcPanel .mcTitle", "欄を離れる")
    ms = _min_ms(ed, 4, 2)
    wait_until(ed, f"(()=>{{const r=[...document.querySelectorAll('#mcPanel .blRule')].find(x=>x.querySelector('.blId').textContent==='R5.A');"
                   f"return [...r.querySelectorAll('.blF')].some(f=>f.textContent.startsWith('Hard')&&f.textContent.includes('{ms}ms'))}})()",
               label="手入力で R5.A を判定")
    t.eq(ed.js("!!document.querySelector('#mcPanel .blStarAuto')"), False, "自動の値が無い時は「自動に戻す」を出さない")
    # 取り込み: 1回目は失敗
    click_in_view(ed, "#mcPanel .blRtOpen", "取り込んで自動計算…")
    click_in_view(ed, "#mcPanel .blRtInstall", "GitHub から取り込む")
    wait_until(ed, "!!document.querySelector('#mcPanel .blRtErr')", label="失敗の表示")
    t.ok("GitHub に接続できませんでした" in ed.js("document.querySelector('#mcPanel .blRtErr').textContent"), "失敗の文")
    t.eq(ed.js("!!document.querySelector('#mcPanel .blRtOpen')"), True, "取り込みのボタンは残る")
    # 2回目は成功 → そのまま測って欄に入る（手入力の Hard は残る）
    click_in_view(ed, "#mcPanel .blRtOpen", "取り込んで自動計算…")
    click_in_view(ed, "#mcPanel .blRtInstall", "GitHub から取り込む（2回目）")
    wait_until(ed, "document.querySelector('#mcPanel input[data-star=\"Expert\"]').value==='4.57'", label="取り込み後に自動で入る")
    t.eq([c["act"] for c in rating_calls(ed)], ["status", "install", "install", "measure"], "呼んだAPI（取り込みの後に自動で測る）")
    t.eq([_val(ed, "star", "Hard"), _val(ed, "tech", "Hard")], ["4", "2"], "手入力の値は残る")
    t.eq(ed.js("!!document.querySelector('#mcPanel .blStarAuto[data-dn=\"Hard\"]')"), True, "自動の値ができたので「自動に戻す」が出る")
    t.eq(ed.js("!!document.querySelector('#mcPanel .blRtErr')"), False, "失敗の表示は消える")
    t.no_errors()


# ---------------------------------------------------------------- 「難易度を測る」パネルとの共有・測れない難易度
def test_bl_stars_shared_with_rating_panel(t):
    '''BL評価リストで測った結果は「難易度を測る」パネルにそのまま出る（測り直さない）。逆も同じ。
    ノーツ20個未満で測れない難易度は欄にそう出て空のまま（R5.A は未判定・R11.H.5 は手動確認）'''
    ed = open_fixture_ready(t, 'rich')
    rating_spy(ed, {"status": RATING_INSTALLED, "measure": _res((3.214, 1.5), None)})
    _open_mapcheck(ed)
    _to_bl(ed)
    wait_until(ed, "document.querySelector('#mcPanel input[data-star=\"Hard\"]').value==='3.21'", label="自動で入る")
    t.ok("自動計算できません（ノーツ20個未満）" in _box(ed), f"測れない難易度の表示: {_box(ed)}")
    t.eq([_val(ed, "star", "Expert"), _val(ed, "tech", "Expert")], ["", ""], "測れない難易度の欄は空")
    t.ok(any(f.startswith("Expert") and "入ると判定します" in f for f in _rule(ed, "R5.A")["fs"]), "Expert の R5.A は未判定")
    t.eq(_rule(ed, "R11.H.5")["st"], "st-manual", "★が1つしか無いので R11.H.5 は手動確認")
    click_sel(ed, "#mcPanel .mcClose", "譜面チェックを閉じる")
    rating_open_via_menu(ed)
    wait_until(ed, "document.querySelectorAll('#rtPanel .rtTable tr').length>0", label="パネルに結果")
    t.eq(ed.js("[...document.querySelector('#rtPanel .rtTable tr:nth-child(2)').children].map(c=>c.textContent)")[:2], ["Hard", "3.21"], "同じ結果が出る")
    t.eq(_measures(ed), 1, "パネルを開いても測り直さない（譜面がそのまま）")
    # 逆: パネルで測ってから BL評価リストを開く
    ed = open_fixture_ready(t, 'rich')
    rating_spy(ed, {"status": RATING_INSTALLED, "measure": M2})
    rating_open_via_menu(ed)
    wait_until(ed, "document.querySelectorAll('#rtPanel .rtTable tr').length>0", label="パネルで測る")
    click_sel(ed, "#rtPanel .rtClose", "閉じる")
    _open_mapcheck(ed)
    _to_bl(ed)
    wait_until(ed, "document.querySelector('#mcPanel input[data-star=\"Hard\"]').value==='3.5'", label="パネルの結果が入る")
    ed.wait(0.3)
    t.eq([c["act"] for c in rating_calls(ed)], ["status", "measure"], "BL評価リストを開いても測り直さない")
    t.no_errors()

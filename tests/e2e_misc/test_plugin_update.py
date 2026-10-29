"""取り込み済みのプラグインの更新の知らせ（js/update/update-dialog.js・2026-10-28）。本体の確認（exe 版・環境設定 ON）に続けて、
取り込み済みのプラグイン（難易度を測る・AutoModder）を1つずつ確かめ、新しい版があれば本体と同じ形の画面を出す。
応答は偽物（tests/_lib/plugin_update_helpers.py）＝GitHub・ブラウザ・取り込みには触らない。起動時の確認は読み込みの3秒後に動くので、
偽物は読み込みの前に差す（pu_on_load。終わったら pu_off で外す）"""
import json

from misc_helpers import file_menu, fresh_page, ls, rating_open_via_menu, rating_text, reload_keep, toast, wait_until
from plugin_update_helpers import (AM_NONE, DLG, NO_DLG, NOTES, RT_NEW, RT_OLD, UPDATE_NONE, cfg_rating_newer, click_btn, dlg, pu_acts,
                                   pu_calls, pu_off, pu_on_load, pu_spy, rt_latest)

RT_NAME = "「難易度を測る」のプラグイン（nlm-rating）"
AM_NAME = "AutoModder のプラグイン（nlm-automodder）"


def _boot(ed, cfg):
    """偽物を読み込みの前に差して開き直す（localStorage は残す）。外す時の id を返す"""
    ident = pu_on_load(ed, cfg)
    reload_keep(ed)
    return ident


def _wait_act(ed, act, label=None):
    wait_until(ed, f"(window.__pu&&window.__pu.calls.some(c=>c.act==={json.dumps(act)}))", timeout=12, label=label or act)


def _click_more(ed, i=0):
    r = ed.js(f"(()=>{{const a=document.querySelectorAll('#updDlg .udMore')[{i}]; if(!a) return null; const r=a.getBoundingClientRect(); return [r.left+r.width/2,r.top+r.height/2]}})()")
    ed.click(*r)


def test_plugin_update_startup_and_skip(t):
    '''起動時: 本体が最新なら、取り込み済みの「難易度を測る」の新しい版を知らせる（題・今の版・更新内容＝プラグインの CHANGELOG の見出し・大きさ・
    版を戻せる場所・あとから更新できる案内）。Esc では閉じない。取り込んでいない AutoModder は GitHub へ問い合わせない。「詳しく見る」はその版の
    リリースのページ。「更新しない」で閉じると、開き直してもその版は出さない（それより新しい版が出たらまた出す）'''
    ed = fresh_page(t)
    ident = _boot(ed, cfg_rating_newer())
    try:
        wait_until(ed, DLG, timeout=12, label="起動時の知らせ")
        d = dlg(ed)
        t.eq(d["title"], f"{RT_NAME}の新しい版 v0.2.0 があります", "題")
        t.eq(d["cur"], "今の版: v0.1.0", "今の版")
        t.eq((d["vers"], d["items"]), (["v0.2.0"], NOTES[0]["ja"]), "更新内容（版ごとの見出し・日本語）")
        t.ok("ダウンロード（17.8MB）" in d["hints"][0] and "「難易度を測る」のパネルの版の選択で戻せます" in d["hints"][0], f"説明: {d['hints']}")
        t.ok("ヘルプのメニューの「更新を確認…」か、「難易度を測る」のパネルの［更新を確認］" in d["hints"][1], f"あとから更新できる案内: {d['hints']}")
        t.eq(d["btns"], ["更新しない", "更新する"], "ボタン（本体と同じ）")
        acts = pu_acts(ed)
        t.ok(acts.index("update:check") < acts.index("rating:check"), f"本体の確認が先: {acts}")
        t.ok("rating:install" not in acts, "知らせただけでは取り込まない")
        ed.key("Escape"); ed.wait(0.3)
        t.ok(ed.js(DLG), "Esc では閉じない（選んでもらう）")
        _click_more(ed)
        _wait_act(ed, "rating:openNotes", "詳しく見る")
        t.eq([c["body"] for c in pu_calls(ed) if c["act"] == "rating:openNotes"], [{"version": "0.2.0"}], "その版のページを開く")
        click_btn(ed, "更新しない")
        wait_until(ed, NO_DLG, label="閉じる")
        t.eq(ls(ed, "bsnm_rtUpdSkip"), "0.2.0", "「更新しない」にした版を記録")
        _wait_act(ed, "automodder:status", "次のプラグインの状態を見る")
        ed.wait(0.5)
        t.ok("automodder:check" not in pu_acts(ed), f"取り込んでいない AutoModder は GitHub へ問い合わせない: {pu_acts(ed)}")
        # 開き直す: 「更新しない」にした版は出さない
        reload_keep(ed)
        _wait_act(ed, "automodder:status", "開き直した後の確認が最後まで進む")
        ed.wait(0.5)
        t.ok(ed.js(NO_DLG), "「更新しない」にした版は起動時に出さない")
        t.ok("rating:check" in pu_acts(ed), "確認自体はする")
    finally:
        pu_off(ed, ident)
    # それより新しい版が出たら、また出す
    ident = _boot(ed, cfg_rating_newer(rating={"status": RT_OLD, "check": rt_latest("0.3.0", notes=[])}))
    try:
        wait_until(ed, DLG, timeout=12, label="新しい版の知らせ")
        d = dlg(ed)
        t.eq(d["title"], f"{RT_NAME}の新しい版 v0.3.0 があります", "記録した版より新しい版は出す")
        t.eq((d["vers"], d["items"], d["msg"]), (["v0.3.0"], [], "更新内容の情報がありません。"), "更新内容の無い manifest（古い作り）でも版と「詳しく見る」は出す")
        click_btn(ed, "更新しない")
        wait_until(ed, NO_DLG, label="閉じる")
        t.eq(ls(ed, "bsnm_rtUpdSkip"), "0.3.0", "記録を新しい版にする")
    finally:
        pu_off(ed, ident)
        ed.js("localStorage.removeItem('bsnm_rtUpdSkip');true")
    t.no_errors()


def test_plugin_update_after_main_prompt(t):
    '''本体にも新しい版がある時は本体の知らせが先。本体を「更新しない」にした後で、プラグインの知らせを出す（同時には出さない）'''
    ed = fresh_page(t)
    upd = {"status": UPDATE_NONE["status"],
           "check": {"ok": True, "current": "v2.1.1-oz", "latest": "v2.2.0-oz", "newer": True, "size": 120000000, "auto": "ok",
                     "notes": [{"version": "v2.2.0-oz", "ja": ["本体の変更"], "en": ["App change"]}]}}
    ident = _boot(ed, cfg_rating_newer(update=upd))
    try:
        wait_until(ed, DLG, timeout=12, label="本体の知らせ")
        t.eq(dlg(ed)["title"], "新しいバージョン v2.2.0-oz があります", "本体が先")
        ed.wait(1.0)
        t.eq(ed.js("document.querySelectorAll('#updDlgBg').length"), 1, "画面は1つだけ")
        click_btn(ed, "更新しない")
        wait_until(ed, f"{DLG}&&document.querySelector('#updDlg .udTitle').textContent.includes('nlm-rating')", timeout=12, label="続けてプラグインの知らせ")
        t.eq(ls(ed, "bsnm_updateSkip"), "v2.2.0-oz", "本体の「更新しない」も記録")
        click_btn(ed, "更新しない")
        wait_until(ed, NO_DLG, label="閉じる")
    finally:
        pu_off(ed, ident)
        ed.js("localStorage.removeItem('bsnm_rtUpdSkip');localStorage.removeItem('bsnm_updateSkip');true")
    t.no_errors()


def test_plugin_update_not_checked_when_off(t):
    '''起動時の確認をしない時（開発用の起動＝exe 版でない・環境設定 OFF）は、プラグインも GitHub へ問い合わせない'''
    ed = fresh_page(t)
    cfg = cfg_rating_newer(update={"status": {**UPDATE_NONE["status"], "frozen": False}, "check": UPDATE_NONE["check"]})
    ident = _boot(ed, cfg)
    try:
        _wait_act(ed, "update:status")
        ed.wait(1.5)
        acts = pu_acts(ed)
        t.ok(not any(a in acts for a in ("update:check", "rating:check", "automodder:check")), f"exe 版でなければ確認しない: {acts}")
    finally:
        pu_off(ed, ident)
    ed.js("localStorage.setItem('bsnm_updateCheck','0');true")
    ident = _boot(ed, cfg_rating_newer())
    try:
        _wait_act(ed, "update:status")
        ed.wait(1.5)
        acts = pu_acts(ed)
        t.ok(not any(a in acts for a in ("update:check", "rating:check", "automodder:check")), f"環境設定 OFF なら確認しない: {acts}")
        t.ok(ed.js(NO_DLG), "何も出さない")
    finally:
        pu_off(ed, ident)
        ed.js("localStorage.removeItem('bsnm_updateCheck');true")
    t.no_errors()


def test_plugin_update_install_from_menu(t):
    '''メニューの「更新を確認…」: 起動時に「更新しない」にした版でも出す。「更新する」でパネルと共有の部品から取り込み（再起動なし）、
    通知を出して閉じる。パネルも新しい版の表示になる'''
    ed = fresh_page(t)
    ed.js("localStorage.setItem('bsnm_rtUpdSkip','0.2.0');true")
    pu_spy(ed, cfg_rating_newer())
    file_menu(ed, "update")
    wait_until(ed, f"{DLG}&&document.querySelector('#updDlg .udTitle').textContent.includes('nlm-rating')", label="メニューからの知らせ")
    click_btn(ed, "更新する")
    wait_until(ed, NO_DLG, label="取り込んで閉じる")
    t.ok(f"{RT_NAME}を v0.2.0 に更新しました" in toast(ed), f"通知: {toast(ed)}")
    acts = pu_acts(ed)
    t.ok("rating:install" in acts, f"取り込んだ: {acts}")
    t.ok("automodder:check" not in acts, "取り込んでいない AutoModder は確かめない")
    rating_open_via_menu(ed)
    wait_until(ed, "(()=>{const e=document.querySelector('#rtPanel .rtPlugTxt');return !!e&&e.textContent.includes('v0.2.0')})()", label="パネルの版")
    t.eq(rating_text(ed, ".rtPlugTxt"), "プラグイン v0.2.0", "パネルも新しい版（共有の部品）")
    ed.js("localStorage.removeItem('bsnm_rtUpdSkip');true")


def test_plugin_update_manual_summary(t):
    '''メニューの「更新を確認…」で、どれも新しくなければ結果をまとめて出す（本体・取り込み済みのプラグインごと・確認できなかった物・
    NLM の更新が要る新しい版）。取り込んでいない物は書かない'''
    ed = fresh_page(t)
    am_old = {**AM_NONE, "current": "0.1.0", "automodder": "1.6.6", "installed": [{"version": "0.1.0", "protocol": 1, "compatible": True, "automodder": "1.6.6"}]}
    am_check = {**am_old, "latest": {"version": "0.2.0", "protocol": 2, "size": 12000000, "compatible": False, "installed": False, "newer": True, "notes": []}}
    pu_spy(ed, cfg_rating_newer(rating={"status": RT_NEW, "check": {**rt_latest(newer=False), **{"current": "0.2.0"}}},
                                automodder={"status": am_old, "check": am_check}))
    file_menu(ed, "update")
    wait_until(ed, f"{DLG}&&document.querySelector('#updDlg .udTitle').textContent==='更新の確認'&&!document.querySelector('#updDlg .udMsg').textContent.includes('確認しています')",
               label="結果のまとめ")
    t.eq(dlg(ed)["msg"].split("\n"), ["最新のバージョンです（v2.1.1-oz）。", f"{RT_NAME}: 最新の版（v0.2.0）を取り込み済みです。",
                                      f"{AM_NAME}: 新しい版 v0.2.0 がありますが、使うには NLM の更新が必要です。"], "まとめ")
    ed.key("Escape")
    wait_until(ed, NO_DLG, label="Esc で閉じる")
    # 確認できなかった物
    pu_spy(ed, cfg_rating_newer(rating={"status": RT_OLD, "check": {"ok": False, "error": "network"}}))
    file_menu(ed, "update")
    wait_until(ed, f"{DLG}&&document.querySelector('#updDlg .udMsg').textContent.includes('nlm-rating')", label="確認できなかった物")
    t.eq(dlg(ed)["msg"].split("\n")[1], f"{RT_NAME}: 確認できませんでした（GitHub に接続できませんでした。ネット接続を確認してください。）", "失敗の理由")
    click_btn(ed, "閉じる")
    wait_until(ed, NO_DLG, label="閉じる")
    t.no_errors()

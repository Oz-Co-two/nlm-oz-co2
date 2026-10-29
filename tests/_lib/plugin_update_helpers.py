"""本体とプラグインの更新の知らせ（js/update/update-dialog.js）のテストの共通部品（e2e_misc・visual で使う）。

/__update/*・/__rating/*・/__automodder/* への fetch をページ内で偽物にして、呼ばれ方を window.__pu.calls（'rating:check' 等）に残す。
GitHub への通信・ブラウザを開く・取り込みは一切しない（応答は cfg のとおり。キューは最後を残して消費）。
- pu_spy(ed, cfg): 今のページに差す（メニューの「更新を確認…」用）
- pu_on_load(ed, cfg): 次からの読み込みの前に差す（起動時の確認＝読み込みの3秒後に動く物用）。戻り値を pu_off に渡して外す
  （Edge はテストの間で使い回すので、外さないと次のテストにも残る）
"""
import json

_PU_JS = r"""(()=>{
  if(!window.__puOrig) window.__puOrig=window.fetch;   // pu_unspy で戻す元（重ねて差しても一番最初の物）
  const P=window.__pu={calls:[],cfg:__CFG__};
  const of=window.fetch.bind(window);
  const kinds=[['__update/','update'],['__rating/','rating'],['__automodder/','automodder']];
  window.fetch=async function(url,opt){
    const u=String(url), k=kinds.find(x=>u.startsWith(x[0]));
    if(k&&P.cfg[k[1]]){
      const act=u.slice(k[0].length); let body=null; try{ body=JSON.parse(opt.body); }catch(_){}
      P.calls.push({act:k[1]+':'+act,body,headers:(opt&&opt.headers)||{}});
      const q=P.cfg[k[1]][act]; const r=Array.isArray(q)?(q.length>1?q.shift():q[0]):q;
      if(r===undefined) return new Response('{}',{status:404});
      return new Response(JSON.stringify(r),{status:200,headers:{'content-type':'application/json'}}); }
    return of(url,opt); };
  return true; })()"""

CUR = "v2.1.1-oz"
UPDATE_NONE = {"status": {"ok": True, "current": CUR, "frozen": True, "justUpdated": None},
               "check": {"ok": True, "current": CUR, "latest": CUR, "newer": False, "notes": [], "size": 0, "auto": "ok"}}
NOTES = [{"version": "0.2.0", "ja": ["BeatLeader の 2026 年 10 月のリウェイトに合わせて、計算を新しくしました", "Acc は、本家がスコアから付ける補正の前の値です"],
          "en": ["Updated to BeatLeader's October 2026 reweight", "Acc is the value before BeatLeader's score-based correction"]}]
RT_OLD = {"ok": True, "protocol": 1, "current": "0.1.0", "installed": [{"version": "0.1.0", "protocol": 1, "compatible": True}],
          "repo": "https://github.com/Oz-Co-two/nlm-rating"}
RT_NEW = {**RT_OLD, "current": "0.2.0", "installed": [{"version": "0.2.0", "protocol": 1, "compatible": True}, RT_OLD["installed"][0]]}
AM_NONE = {"ok": True, "protocol": 1, "current": None, "automodder": None, "installed": [], "repo": "https://github.com/Oz-Co-two/nlm-automodder"}


def rt_latest(ver="0.2.0", newer=True, compatible=True, notes=None, size=18681090):
    return {**RT_OLD, "latest": {"version": ver, "protocol": 1 if compatible else 2, "size": size, "compatible": compatible,
                                 "installed": not newer, "newer": newer, "notes": NOTES if notes is None else notes}}


def cfg_rating_newer(**over):
    """本体は最新・難易度を測る（0.1.0 を取り込み済み）に 0.2.0 がある・AutoModder は未導入"""
    c = {"update": dict(UPDATE_NONE),
         "rating": {"status": RT_OLD, "check": rt_latest(), "install": RT_NEW, "openNotes": {"ok": True}},
         "automodder": {"status": AM_NONE}}
    c.update(over)
    return c


def pu_spy(ed, cfg):
    ed.js(_PU_JS.replace("__CFG__", json.dumps(cfg)))


def pu_unspy(ed):
    """pu_spy で差した偽物を全部外す（後の手順の /__rating/* 等を本物へ戻す）"""
    ed.js("(()=>{if(window.__puOrig){window.fetch=window.__puOrig;delete window.__puOrig;} return true})()")


def pu_on_load(ed, cfg):
    return ed.call("Page.addScriptToEvaluateOnNewDocument", source=_PU_JS.replace("__CFG__", json.dumps(cfg)))["identifier"]


def pu_off(ed, ident):
    ed.call("Page.removeScriptToEvaluateOnNewDocument", identifier=ident)


def pu_acts(ed):
    return ed.js("window.__pu?window.__pu.calls.map(c=>c.act):null")


def pu_calls(ed):
    return ed.js("window.__pu.calls")


DLG = "!!document.getElementById('updDlg')"
NO_DLG = "!document.getElementById('updDlgBg')"


def dlg(ed):
    """出ている更新の画面: {title, cur, vers, items, hints, msg, btns}（無ければ None）"""
    return ed.js("""(()=>{const d=document.getElementById('updDlg'); if(!d) return null; const q=s=>[...d.querySelectorAll(s)].map(e=>e.textContent);
      return {title:q('.udTitle')[0], cur:q('.udCur')[0]||null, vers:q('.udVerName'), items:q('.udNotes li'), hints:q('.udHint'),
              msg:q('.udMsg').join('\\n'), btns:q('.udBtns button'), busy:!!d.querySelector('.udBar.busy')}})()""")


def click_btn(ed, label):
    """更新の画面のボタンを文字で押す（本物のクリック）"""
    r = ed.js(f"""(()=>{{const b=[...document.querySelectorAll('#updDlg .udBtns button')].find(b=>b.textContent==={json.dumps(label)});
        if(!b) return null; const r=b.getBoundingClientRect(); return [r.left+r.width/2,r.top+r.height/2]}})()""")
    if not r:
        raise AssertionError(f"更新の画面にボタン「{label}」がありません: {dlg(ed)}")
    ed.click(*r)


def mock_manual_rating_newer(ed):
    """画面テスト用: メニューの「更新を確認…」で、難易度を測るの 0.2.0 の知らせが出るようにする（本体は最新・AutoModder は未導入）"""
    pu_spy(ed, cfg_rating_newer())


AM_OLD = {**AM_NONE, "current": "0.1.0", "automodder": "1.6.6",
          "installed": [{"version": "0.1.0", "protocol": 1, "compatible": True, "automodder": "1.6.6"}]}


def cfg_summary():
    """メニューの「更新を確認…」のまとめ: 本体は最新・難易度を測るは最新を取り込み済み・AutoModder は NLM の更新が要る新しい版"""
    am_check = {**AM_OLD, "latest": {"version": "0.2.0", "protocol": 2, "size": 12000000, "compatible": False, "installed": False,
                                     "newer": True, "notes": []}}
    return cfg_rating_newer(rating={"status": RT_NEW, "check": {**rt_latest(newer=False), "current": "0.2.0"}},
                            automodder={"status": AM_OLD, "check": am_check})


def plugin_update_tour(ed, scan):
    """英語の画面の点検（english_ui_helpers.tour から）: メニューの「更新を確認…」→プラグインの知らせ→「更新する」の通知→結果のまとめ。
    応答は偽物（終わったら外す）"""
    from misc_helpers import click_sel, wait_until
    pu_spy(ed, cfg_rating_newer())
    click_sel(ed, "#mHelpBtn", "ヘルプ"); ed.wait(0.3); click_sel(ed, ".mbMenu button[data-act=update]", "更新を確認")
    wait_until(ed, DLG + "&&document.querySelector('#updDlg .udTitle').textContent.includes('nlm-rating')", label="プラグインの更新の知らせ")
    scan(ed, "プラグインの更新の知らせ")
    click_btn(ed, "Update")
    wait_until(ed, NO_DLG, label="取り込んで閉じる")
    scan(ed, "プラグインを更新した通知")
    pu_spy(ed, cfg_summary())
    click_sel(ed, "#mHelpBtn", "ヘルプ"); ed.wait(0.3); click_sel(ed, ".mbMenu button[data-act=update]", "更新を確認")
    wait_until(ed, DLG + "&&document.querySelector('#updDlg .udMsg').textContent.includes('nlm-automodder')", label="更新の確認のまとめ")
    scan(ed, "更新の確認のまとめ")
    click_btn(ed, "Close")
    wait_until(ed, NO_DLG, label="閉じる")
    pu_unspy(ed)

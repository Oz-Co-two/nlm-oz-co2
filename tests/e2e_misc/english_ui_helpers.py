"""英語表示の訳し漏れ検出（test_english_ui.py 用）。

ページに見張りを仕込み、画面に出た日本語を集める:
- 見えている要素の文字・ツールチップ（title）・入力欄の薄い説明（placeholder）
- キャンバスに描いた文字（fillText / strokeText。NLE のクリップの「〇小節」など）
- 画面下部のメッセージや一時的な通知（追加・書き換えられた文字を MutationObserver で拾う）
- confirm / prompt / alert の文面
「日本語」は ひらがな・カタカナ（中黒「・」は除く）・漢字。全角の記号（①（）／＋など）は数えない。
"""
import json

from misc_helpers import click_sel, close_prefs, open_prefs, prefs_tab, wait_until
from e2e_helpers import media_lib_load, media_lib_sample_extra, media_lib_mock, SAMPLE_DETAILS

# 英語表示でも日本語のまま出してよいもの（言語の選択肢そのもの）
ALLOW = ("日本語", "言語 / Language")

SCAN_JS = r"""
(()=>{ if(window.__jp) return true;
  const JP=/[぀-ゟ゠-ヺー-ヿ㐀-䶿一-鿿]/;
  const ALLOW=new Set(%ALLOW%);
  const found=new Map();   // 文字 → どこで見たか
  const add=(s,where)=>{ s=String(s||'').trim(); if(!s||!JP.test(s)||ALLOW.has(s)) return; if(!found.has(s)) found.set(s,where); };
  const vis=el=>{ if(!el||!el.getClientRects) return false; if(!el.getClientRects().length) return false;
    const cs=getComputedStyle(el); return cs.visibility!=='hidden'&&cs.display!=='none'&&+cs.opacity>0; };
  const pathOf=el=>{ const p=[]; for(let e=el;e&&e.nodeType===1&&p.length<4;e=e.parentElement) p.unshift(e.id?'#'+e.id:(e.tagName.toLowerCase()+(e.classList[0]?'.'+e.classList[0]:''))); return p.join('>'); };
  const skip=el=>!!(el&&el.closest&&el.closest('script,style,#langSel,noscript'));
  function scan(step){
    const w=document.createTreeWalker(document.body,NodeFilter.SHOW_TEXT);
    for(let n=w.nextNode();n;n=w.nextNode()){ const el=n.parentElement; if(!el||skip(el)||!vis(el)) continue; add(n.nodeValue,step+' 文字 '+pathOf(el)); }
    for(const el of document.body.querySelectorAll('[title],[placeholder],[aria-label]')){ if(skip(el)||!vis(el)) continue;
      for(const a of ['title','placeholder','aria-label']) if(el.hasAttribute(a)) add(el.getAttribute(a),step+' '+a+' '+pathOf(el)); }
    for(const el of document.body.querySelectorAll('option')){ const s=el.closest('select'); if(s&&!skip(s)&&vis(s)) add(el.textContent,step+' option '+pathOf(s)); }
  }
  for(const fn of ['fillText','strokeText']){ const o=CanvasRenderingContext2D.prototype[fn];
    CanvasRenderingContext2D.prototype[fn]=function(txt,...a){ try{ add(txt,'キャンバス '+(this.canvas&&(this.canvas.id||this.canvas.className)||'')); }catch(_){} return o.call(this,txt,...a); }; }
  new MutationObserver(ms=>{ for(const m of ms){
      if(m.type==='characterData'){ const el=m.target.parentElement; if(el&&!skip(el)) add(m.target.nodeValue,'変化 '+pathOf(el)); continue; }
      for(const nd of m.addedNodes){ if(nd.nodeType===3){ const el=nd.parentElement; if(el&&!skip(el)) add(nd.nodeValue,'変化 '+pathOf(el)); }
        else if(nd.nodeType===1&&!skip(nd)) add(nd.innerText||'','追加 '+pathOf(nd)); } } })
    .observe(document.body,{subtree:true,childList:true,characterData:true});
  for(const fn of ['confirm','prompt','alert']){ const o=window[fn]; window[fn]=function(msg,...a){ add(msg,fn); return fn==='confirm'?false:(fn==='prompt'?null:undefined); }; }
  window.__jp={ scan, found:()=>[...found.entries()], clear:()=>found.clear() };
  return true; })()
""".replace("%ALLOW%", json.dumps(list(ALLOW), ensure_ascii=False))


def start_english(t, fixture="basic"):
    """英語表示（環境設定の言語＝English）で開き直し、素材を読み込んで見張りを仕込む"""
    from nlmtest import LIGHT_RENDER_JS
    ed = t.fresh()
    ed.js("localStorage.setItem('bsnm_lang','en');true")
    ed.wait(0.6)   # 環境設定のミラー（config/settings.json）へ書き戻されるのを待つ
    ed.reload(clear_storage=False)
    ed.js(LIGHT_RENDER_JS)
    wait_until(ed, "!document.getElementById('bootCover')", label="起動中の覆いが外れる")
    wait_until(ed, "document.getElementById('mFileBtn').textContent.trim()==='File'", label="英語表示で起動")
    if fixture:
        ed.load_fixture(fixture)
    ed.js(SCAN_JS)
    return ed


def take_errors(ed, part):
    """console.error のうち part を含むもの（想定どおりのエラー表示）を取り除く。t.no_errors() で誤検知しないため"""
    ed.wait(0.05)
    keep = []
    for e in ed._events:
        p = e.get("params", {})
        if e.get("method") == "Runtime.consoleAPICalled" and p.get("type") == "error" and \
                any(part in str(a.get("value", "")) for a in p.get("args", [])):
            continue
        keep.append(e)
    ed._events[:] = keep


def scan(ed, step):
    ed.wait(0.25)
    ed.js(f"window.__jp.scan({json.dumps(step, ensure_ascii=False)})")


def found(ed):
    return ed.js("window.__jp.found()")


def nle(ed, beat=None):
    return ed.js(f"window._dbgApp.nleScreen({'null' if beat is None else beat})")


def tab_over(ed, x, y):
    ed.move(x, y); ed.wait(0.2); ed.key("Tab"); ed.wait(0.6)


def hide_menu(ed):
    ed.key("Escape"); ed.wait(0.2)
    ed.js("(()=>{const m=document.getElementById('ctxmenu'); if(m) m.style.display='none'; return 1})()")


def right_click(ed, x, y, step):
    ed.click(x, y, button="right"); ed.wait(0.4)
    scan(ed, step)
    hide_menu(ed)


def edit_only_switch_xy(ed, track):
    """NLE のノーツのレーン track の溝の2段目にある単独編集の帯（帯全体が押せる）のスイッチのあたり"""
    b = next(b for b in nle(ed)["eo"] if b["t"] == track)
    return b["x"] + 14, b["y"] + b["h"] / 2


def edit_only_tour(ed):
    """単独編集（2026-10-19）: 溝のスイッチ（文字はキャンバス・ツールチップ）・3Dの隅の表示・他のレーンのノーツをクリックした時の帯。最後にオフへ戻す"""
    objs = [o for o in ed.js("window._dbgApp.objScreen()") if o["kind"] == "note" and o["inView"]]
    if not objs:
        return
    o = max(objs, key=lambda o: o["sy"])   # 手前のノーツ（帯に重ならない所）
    x, y = edit_only_switch_xy(ed, 1 if o["tr"] != 1 else 0)
    ed.click(x, y)
    wait_until(ed, "document.getElementById('eoInd').classList.contains('on')", label="単独編集の隅の表示")
    ed.move(x + 20, y); ed.wait(0.3); scan(ed, "単独編集のスイッチ（ツールチップ）・隅の表示")
    ed.move(o["sx"], o["sy"]); ed.wait(0.15); ed.click(o["sx"], o["sy"])
    wait_until(ed, "document.getElementById('eoBand').classList.contains('on')", label="単独編集の帯")
    scan(ed, "単独編集の帯（他のレーンのノーツをクリック）")
    ed.js("(()=>{const b=document.querySelector('#eoBand .eoOff'); if(b) b.click(); return 1})()"); ed.wait(0.3)


def link_tour(ed):
    """リンクしたクリップ（2026-10-19）: 親を選ぶ画面・🔗の数（キャンバス）・リンクしたクリップの右クリック・分割できない帯・難易度間コピーの確認の画面"""
    cs = ed.js("window._dbgApp.nle().clips.filter(c=>c.lk==='n')")
    if not cs:
        return
    c0 = cs[0]
    def at(beat, tr):   # レーンの本体（表示窓の下に半分隠れたレーンでも見えている所）
        g = nle(ed, beat)
        v1 = ed.js("window._dbgApp.nle().vp.n[1]")
        return g["x"], min(g["notes"][tr] + g["laneH"] * 0.7, v1 - 3)
    g0 = nle(ed)
    ed.move(g0["left"] + g0["gut"] + 4, g0["marker"] - 4); ed.key("a"); ed.wait(0.2)
    ed.click(*at(c0["beat"] + c0["len"] / 2, c0["track"])); ed.wait(0.2)
    ed.key("c", ctrl=True); ed.key("v", ctrl=True); ed.wait(0.3)
    to = c0["beat"] + c0["len"]
    x, y = at(to, c0["track"]); ed.move(x, y); ed.wait(0.3); ed.click(x, y); ed.wait(0.4)   # 貼った直後は貼った物だけが選ばれている
    ed.click(*at(c0["beat"] + c0["len"] / 2, c0["track"]), shift=True); ed.wait(0.2)   # 元も足す
    ed.move(g0["left"] + g0["gut"] + 4, g0["marker"] - 4); ed.wait(0.1)
    ed.key("k")
    wait_until(ed, "!!document.querySelector('#dirtyDlg[data-lk]')", label="リンクの親を選ぶ画面")
    scan(ed, "リンクの親を選ぶ画面")
    click_sel(ed, "#dirtyDlg .ddBtns button.pri", "リンクする")
    wait_until(ed, "window._dbgApp.nle().clips.filter(c=>c.link).length===2", label="リンク")
    scan(ed, "リンクした NLE（🔗の数）")
    right_click(ed, *at(to + 1, c0["track"]), "リンクした子のクリップの右クリック")
    ed.click(*at(to + 1, c0["track"])); ed.wait(0.2)
    ed.move(*at(to + 2, c0["track"])); ed.wait(0.2); ed.key("c"); ed.wait(0.3)
    scan(ed, "リンク中は分割できない帯")
    ed.js("(e=>{ if(e) e.classList.remove('on'); return 1; })(document.getElementById('lkBand'))")
    for _ in range(2):   # 直前にメニューを使っていると、同じボタンの1回目は「閉じる」扱い（トグル）になる
        click_sel(ed, "#diffBar .dfSeg.on", "選択中の難易度"); ed.wait(0.4)
        if ed.js("document.getElementById('ctxmenu').style.display==='block'"):
            break
    ed.js("(b=>{ b.click(); return 1; })(document.querySelector('#ctxmenu > button'))"); ed.wait(0.3)
    ed.js("(b=>{ if(b) b.click(); return 1; })(document.querySelector('#ctxmenu .ctxsub button'))"); ed.wait(0.4)
    if ed.js("!!document.querySelector('#dirtyDlg[data-lk=copy]')"):
        scan(ed, "難易度間コピーの確認の画面")
        click_sel(ed, "#dirtyDlg .ddBtns button:not(.pri)", "キャンセル"); ed.wait(0.3)
    hide_menu(ed)


def tour(ed):
    """主な画面・メニュー・パネルを順に開いて scan する"""
    g = nle(ed)
    scan(ed, "起動直後")
    # 左上: MEDIA ⇄ PREVIEW、右上: NLE ⇄ INFO、下: NOTES ⇄ LIGHTING
    tab_over(ed, 280, 300); scan(ed, "PREVIEW"); tab_over(ed, 280, 300); scan(ed, "MEDIA")
    # MEDIA の記録したライブラリ（2026-10-12）: グリッド・詳細表示（全部の列）・列のメニュー・絞り込みのパネル
    media_lib_load(ed, extra=media_lib_sample_extra(), covers=1, details=SAMPLE_DETAILS); scan(ed, "MEDIA ライブラリ")   # 全曲データは取得済み（出どころの表示・🔍）
    click_sel(ed, "#libViewSeg button[data-view=detail]", "詳細表示"); ed.wait(0.4); scan(ed, "MEDIA 詳細表示")
    # 🔍（全曲データに無い曲）の確認・★のまとめての計算（右クリックのメニュー・計算中の帯）。応答は差し替え（ネット・プラグインへ出ない）
    media_lib_mock(ed, rate="async b=>{ while(!window.__rateGo) await new Promise(r=>setTimeout(r,50)); return {ok:false,error:'run'}; }")
    ed.js("(t=>{ t.scrollLeft=t.querySelector('.ltH[data-col=uploaded]').offsetLeft-120; return 1; })(document.getElementById('libTable'))"); ed.wait(0.3)
    scan(ed, "MEDIA 詳細表示（🔍）")
    click_sel(ed, "#libTable .ltLook", "🔍"); wait_until(ed, "!!document.getElementById('dirtyDlg')", label="🔍 の確認"); scan(ed, "MEDIA 🔍 の確認")
    click_sel(ed, "#dirtyDlg button:not(.pri)", "やめる"); ed.wait(0.3)
    r0 = ed.js("(()=>{ const e=[...document.querySelectorAll('#libTable .ltRow')].find(e=>e._i===0), r=e.getBoundingClientRect(), t=document.getElementById('libTable').getBoundingClientRect();"
               " return {x:t.left+60,y:r.top+r.height/2}; })()")
    ed.click(r0["x"], r0["y"], button="right"); ed.wait(0.4); scan(ed, "MEDIA 行の右クリック")
    ed.js("[...document.querySelectorAll('#ctxmenu > button')].find(b=>b.textContent.includes('filtered rows')||b.textContent.includes('絞り込んだ行')).click();true")
    wait_until(ed, "!!window._dbgApp.libOnline().rate.bar", label="★の計算中の帯"); scan(ed, "MEDIA ★の計算中")
    click_sel(ed, "#libRateStop", "中止"); ed.wait(0.2); scan(ed, "MEDIA ★の計算を中止中")
    ed.js("window.__rateGo=true"); wait_until(ed, "!window._dbgApp.libOnline().rate.running", label="★の計算の終わり"); scan(ed, "MEDIA ★の計算の終わり")
    ed.js("(t=>{ t.scrollLeft=0; return 1; })(document.getElementById('libTable'))")
    hx = ed.js("(r=>({x:r.left+r.width/2,y:r.top+r.height/2}))(document.querySelector('#libTable .ltH[data-col=name]').getBoundingClientRect())")
    ed.click(hx["x"], hx["y"], button="right"); ed.wait(0.3); scan(ed, "MEDIA 列のメニュー")
    ed.js("[...document.querySelectorAll('#libColMenu input')].forEach(c=>{ if(!c.checked) c.click(); }); true"); ed.wait(0.3)   # 隠れている列も出してセル・ツールチップを点検
    scan(ed, "MEDIA 詳細表示（全部の列）")
    ed.js("document.querySelector('#libColMenu .lcmReset').click(); true"); ed.key("Escape"); ed.wait(0.2)
    # 詳細表示の文字の大きさ（スライダーのツールチップ）・フィルター（条件の数の丸）・検索欄の ×（2026-10-12）
    ed.js("document.getElementById('libSize').value=16; document.getElementById('libSize').dispatchEvent(new Event('input')); true"); ed.wait(0.3)
    scan(ed, "MEDIA 詳細表示（文字の大きさ）")
    click_sel(ed, "#libFiltBtn", "フィルター"); ed.wait(0.4); scan(ed, "MEDIA フィルター")
    ed.js("(i=>{ i.value='5'; i.dispatchEvent(new Event('input')); return 1; })(document.querySelector('#libFiltPanel .lfRow[data-k=stars] .lfLo'))"); ed.wait(0.3)
    scan(ed, "MEDIA フィルター（条件の数の丸）")
    click_sel(ed, "#libFiltPanel .lfClose", "フィルターを閉じる"); ed.wait(0.2)
    click_sel(ed, "#libSearch", "検索欄"); ed.call("Input.insertText", text="a"); ed.wait(0.4); scan(ed, "MEDIA 検索欄（×）")
    click_sel(ed, "#libSearchX", "検索を消す"); click_sel(ed, "#libFiltClear", "解除"); ed.wait(0.3)
    click_sel(ed, "#libViewSeg button[data-view=grid]", "グリッド表示"); ed.wait(0.3)
    tab_over(ed, g["left"] + g["w"] * 0.6, g["lanes"] + 40); scan(ed, "INFO")
    tab_over(ed, g["left"] + g["w"] * 0.6, g["lanes"] + 40); scan(ed, "NLE")
    ed.move(960, 820); ed.wait(0.2); ed.key("Tab"); ed.wait(0.8); scan(ed, "LIGHTING")
    for k, code, vk in (("w", "KeyW", 87), ("c", "KeyC", 67)):
        ed.move(960, 820); ed.wait(0.2)
        ed.call("Input.dispatchKeyEvent", type="keyDown", key=k, code=code, text=k, windowsVirtualKeyCode=vk, nativeVirtualKeyCode=vk)
        ed.wait(0.5); scan(ed, f"LIGHTING {k}パイ")
        ed.call("Input.dispatchKeyEvent", type="keyUp", key=k, code=code, windowsVirtualKeyCode=vk, nativeVirtualKeyCode=vk); ed.wait(0.3)
    ed.move(960, 820); ed.key("Tab"); ed.wait(0.8)
    for k, code, vk in (("w", "KeyW", 87), (",", "Comma", 188)):
        ed.move(960, 820); ed.wait(0.2)
        ed.call("Input.dispatchKeyEvent", type="keyDown", key=k, code=code, text=k, windowsVirtualKeyCode=vk, nativeVirtualKeyCode=vk)
        ed.wait(0.5); scan(ed, f"NOTES {k}パイ")
        ed.call("Input.dispatchKeyEvent", type="keyUp", key=k, code=code, windowsVirtualKeyCode=vk, nativeVirtualKeyCode=vk); ed.wait(0.3)
    # 配置色のパレット
    click_sel(ed, "#tbColSw", "配置色"); ed.wait(0.5); scan(ed, "カラーパレット"); ed.key("Escape"); ed.click(1700, 1000); ed.wait(0.3)
    # ファイルメニュー
    click_sel(ed, "#mFileBtn", "ファイル"); ed.wait(0.4); scan(ed, "ファイルメニュー"); ed.key("Escape"); ed.click(1700, 1000); ed.wait(0.3)
    # 環境設定の全タブ
    open_prefs(ed)
    for tab in ("app", "vol", "preview", "cam", "keys", "media"):
        prefs_tab(ed, tab); scan(ed, f"環境設定 {tab}")
    close_prefs(ed)
    # NLE の右クリック: クリップ・空き・レーンの左端・Music・テンポの帯・マーカーの帯（Ctrl+E で1つ置く）
    g = nle(ed, 4)
    ed.move(g["x"], g["notes"][0] + g["laneH"] * 0.7); ed.wait(0.2); ed.key("e", ctrl=True); ed.wait(0.4)
    clips = ed.js("window._dbgApp.nle().clips.filter(c=>c.lk==='n')")
    if clips:
        c0 = clips[0]; gc = nle(ed, c0["beat"] + 0.5)
        right_click(ed, gc["x"], gc["notes"][c0["track"]] + gc["laneH"] * 0.7, "クリップの右クリック")
    g = nle(ed, 40)
    right_click(ed, g["x"], g["notes"][-1] + g["laneH"] * 0.5, "空きの右クリック")
    right_click(ed, g["left"] + 20, g["notes"][0] + 6, "レーン左端の右クリック")   # 溝のレーン名の所（溝の 2〜11px は左のスクロールバー）
    right_click(ed, g["x"], g["tempo"] + 7, "テンポの帯の右クリック")
    g4 = nle(ed, 4)
    right_click(ed, g4["x"] + 2, g4["marker"] + 6, "マーカーの右クリック")
    mus = ed.js("window._dbgApp.musicScreen?window._dbgApp.musicScreen(2):null")
    if mus:
        right_click(ed, mus["x"], mus["top"] + mus["h"] / 2, "Musicの右クリック")
    edit_only_tour(ed)
    # 難易度のメニュー（選択中のボタンをもう一度）
    click_sel(ed, "#diffBar .dfSeg.on", "選択中の難易度"); ed.wait(0.4); scan(ed, "難易度のメニュー"); hide_menu(ed)
    link_tour(ed)   # 難易度のメニューを使うので、上の点検の後に
    # 譜面チェック（2つのタブ）・自動ライティング・難易度を測る
    click_sel(ed, "#mFileBtn", "ファイル"); ed.wait(0.3); click_sel(ed, "#mFileMenu button[data-act=mapcheck]", "譜面チェック")
    wait_until(ed, "!!document.querySelector('#mcPanel .mcSum, #mcPanel .mcOk')", label="譜面チェックの結果")
    scan(ed, "譜面チェック")
    click_sel(ed, "#mcPanel .mcTab[data-tab=bl]", "BL評価リスト"); ed.wait(0.6); scan(ed, "BL評価リスト")
    click_sel(ed, "#mcPanel .mcTab[data-tab=mc]", "BS Map Check"); click_sel(ed, "#mcPanel .mcClose", "閉じる"); ed.wait(0.3)
    click_sel(ed, "#mFileBtn", "ファイル"); ed.wait(0.3); click_sel(ed, "#mFileMenu button[data-act=autolight]", "自動ライティング")
    wait_until(ed, "!!document.getElementById('dirtyDlg')", label="自動ライティングの確認"); scan(ed, "自動ライティングの確認")
    ed.key("Escape"); ed.wait(0.3)
    ed.js("(()=>{const b=document.querySelector('#dirtyDlg button:not(.pri)'); if(b) b.click(); return 1})()"); ed.wait(0.3)
    click_sel(ed, "#mFileBtn", "ファイル"); ed.wait(0.3); click_sel(ed, "#mFileMenu button[data-act=rating]", "難易度を測る")
    wait_until(ed, "!!document.querySelector('#rtPanel .rtTable, #rtPanel .rtIntro, #rtPanel .rtErr')", label="難易度を測る")
    scan(ed, "難易度を測る")
    ed.js("(()=>{const b=document.querySelector('#rtPanel .rtClose, #rtPanel .mcClose'); if(b) b.click(); return 1})()"); ed.wait(0.3)
    # INFO: 書き出し（出力フォルダ未設定＝足りない物の一覧が出る）
    g = nle(ed)
    tab_over(ed, g["left"] + g["w"] * 0.6, g["lanes"] + 40)
    ed.js("(()=>{const b=document.getElementById('iExport'); if(b) b.click(); return 1})()"); ed.wait(0.8)
    scan(ed, "INFO 書き出し")
    take_errors(ed, "Cannot export: missing")   # 想定どおりのエラー表示（showErr は console.error も出す）
    ed.move(1200, 300); ed.key("Tab"); ed.wait(0.6)
    # 曲の解析（2026-10-19）: 解析中の帯・テンポの画面・帯・右クリック・⋯・ツールチップ・目盛りが変わった知らせ（応答は偽物）
    from analysis_helpers import analysis_tour
    analysis_tour(ed, scan)

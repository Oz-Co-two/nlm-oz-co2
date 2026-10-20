"""曲の解析（テンポの推定・構成の解析）のテスト部品（e2e_nle/test_analysis.py・test_analysis_clips.py・画面テスト・英語表示の点検で使う）。

解析そのものは serve.py の /__analysis/*（Python・別の作業で作る）。ここではページ内の fetch を差し替えて、決まった応答を返す
（音源は本物の basic.wav を送る＝送る中身の確認もできる）。
- ana_mock(ed, ...): /__analysis/* の応答を差し替える。応答は動作（upload/tempo/structure/cancel）ごと、進み具合は 'status:<job>' ごとに
  並べる（1つずつ使い、最後の1つは何度でも返す）。{"http":404,"body":…} で HTTP の状態、{"netErr":true} で通信の失敗、
  {"waitFor":"名前","then":応答} で ana_go(ed, "名前") まで応答を止める（解析中の画面・やめるの確認用）。
- ana_calls(ed, act): 送られた要求（動作・URL・ヘッダー・JSON の本体・本体の長さ）
- 見本の結果 TEMPO / STRUCT（素材 basic・rich の 16 秒・BPM 120＝32 拍に合わせた物）
- open_clips / clips_dialog / clips_pick / clips_ok: 解析からクリップを作る（帯のメニュー→確認の画面→［作る］）
"""
import json

from e2e_helpers import wait_until

AUDIO_ID = "ab" * 32

# テンポの推定の見本（tools/tempo_leadin.py の estimate() と同じ形）。提案 BPM 128・無音追加 265 ms・候補B 499.8 ms。
# 整数にした（raw_bpm が違う）・2番目の候補は迷いあり（0.87）・段差1つ・揺れ（drift_pct>1.5）・裏拍の疑い（offbeat_ratio>=0.2）をすべて含む
TEMPO = {"version": 1, "bpm": 128.0, "raw_bpm": 127.982, "lead_ms": 265.4, "alt_lead_ms": 499.8, "low_offbeat": True, "offbeat_ratio": 0.25,
         "steps": [{"sec": 9.6, "ms": 12}], "drift_pct": 2.1, "drift": [[0.0, 128.1], [10.0, 126.4]],
         "alt": {"bpm": 96.0, "ratio": 0.87}, "block_mad_ms": 8.2, "n_beats": 30, "family": 128.0, "slope_sig": False, "slope": 0.0,
         "resid_mad_ms": 11.0, "unknown_future_field": {"x": 1}}
# 何も警告の無いテンポ（今の設定 BPM 120・無音追加 0 と同じ）
TEMPO_SAME = {"version": 1, "bpm": 120.0, "raw_bpm": 120.0, "lead_ms": 0.4, "alt_lead_ms": 250.4, "low_offbeat": False, "offbeat_ratio": 0.0,
              "steps": [], "drift_pct": 0.3, "drift": [], "alt": None, "block_mad_ms": 5.0, "n_beats": 30, "family": 120.0,
              "slope_sig": False, "slope": 0.0, "resid_mad_ms": 6.0}
# 構成の解析の見本（拍は NLM の拍）。S2 は2回（Aメロ）・S3 はサビの候補
STRUCT = {"version": 1, "sub": 4, "chorus": ["E"],
          "sections": [{"start": 0, "end": 8, "label": "S1", "count": 1, "chorus": False, "name": "イントロ"},
                       {"start": 8, "end": 16, "label": "S2", "count": 2, "chorus": False, "name": "Aメロ"},
                       {"start": 16, "end": 24, "label": "S3", "count": 1, "chorus": True, "name": "サビ"},
                       {"start": 24, "end": 32, "label": "S2", "count": 2, "chorus": False, "name": "Aメロ", "future": "ok"}],
          "segments": [{"start": 0, "end": 4, "group": "A", "count": 1, "best": None, "sim": None},
                       {"start": 4, "end": 8, "group": "B", "count": 1, "best": None, "sim": None},
                       {"start": 8, "end": 12, "group": "C", "count": 2, "best": 24, "sim": 0.81},
                       {"start": 12, "end": 16, "group": "D", "count": 2, "best": 28, "sim": 0.66},
                       {"start": 16, "end": 20, "group": "E", "count": 2, "best": 20, "sim": 0.9},
                       {"start": 20, "end": 24, "group": "E", "count": 2, "best": 16, "sim": 0.9},
                       {"start": 24, "end": 28, "group": "C", "count": 2, "best": 8, "sim": 0.81},
                       {"start": 28, "end": 32, "group": "D", "count": 2, "best": 12, "sim": 0.66}]}


def status_seq(stage, result, steps=(0.5,)):
    """進み具合の応答の並び（running を steps の数だけ → done）"""
    return [{"ok": True, "state": "running", "stage": stage, "progress": p, "result": None, "error": None} for p in steps] + \
           [{"ok": True, "state": "done", "stage": stage, "progress": 1, "result": result, "error": None}]


_MOCK_JS = r"""(()=>{ const A=window.__ana=window.__ana||{calls:[],q:{},go:{}};
  A.calls.length=0; A.q=%Q%; A.go={};
  if(!A.installed){ A.installed=true; const of=window.fetch.bind(window);
    window.fetch=async function(url,opt){ const u=String(url), m=u.match(/^(?:\.?\/)?__analysis\/([a-z]+)/);
      if(!m) return of(url,opt);
      const act=m[1], body=opt&&opt.body; let parsed=null, len=0;
      if(typeof body==='string'){ len=body.length; try{ parsed=JSON.parse(body); }catch(_){} }
      else if(body&&body.byteLength!=null) len=body.byteLength;
      A.calls.push({act,url:u,method:(opt&&opt.method)||'GET',headers:(opt&&opt.headers)||{},body:parsed,len});
      const key=(act==='status'&&parsed&&parsed.job)?'status:'+parsed.job:act;
      const q=(key in A.q)?A.q[key]:A.q[act];
      let r=Array.isArray(q)?(q.length>1?q.shift():q[0]):q;
      if(r===undefined) r={http:404,body:{ok:false,error:'unknown endpoint'}};
      if(r&&r.waitFor){ const f=r.waitFor; while(!A.go[f]) await new Promise(res=>setTimeout(res,30)); r=r.then; }
      if(r&&r.netErr) throw new TypeError('Failed to fetch');
      const status=(r&&r.http)||200, b=(r&&r.http)?r.body:r;
      return new Response(JSON.stringify(b),{status,headers:{'content-type':'application/json'}}); }; }
  return true; })()"""


def ana_mock(ed, tempo=TEMPO, structure=STRUCT, **over):
    """/__analysis/* の応答を差し替える。tempo/structure は解析の結果。over で動作ごとの応答を上書き
    （キー: upload / req_tempo / req_structure / cancel / status_t1 / status_s1。tempo・structure は結果の引数と名前が重なるので req_ を付ける）"""
    q = {"upload": {"ok": True, "audioId": AUDIO_ID}, "tempo": {"ok": True, "job": "t1"}, "structure": {"ok": True, "job": "s1"},
         "cancel": {"ok": True}, "status:t1": status_seq("tempo", tempo), "status:s1": status_seq("structure", structure)}
    for k, v in over.items():
        q[k.replace("status_", "status:").replace("req_", "")] = v
    ed.js(_MOCK_JS.replace("%Q%", json.dumps(q, ensure_ascii=False)))


def ana_calls(ed, act=None):
    return [c for c in ed.js("window.__ana.calls") if act is None or c["act"] == act]


def ana_go(ed, flag):
    ed.js(f"window.__ana.go[{json.dumps(flag)}]=true;true")


def ana(ed):
    """帯・解析の状態（window._dbgApp.analysis()）"""
    return ed.js("window._dbgApp.analysis()")


def center_of(ed, sel):
    r = ed.js(f"""(()=>{{const e=document.querySelector({json.dumps(sel)}); if(!e||!e.checkVisibility()) return null;
        const r=e.getBoundingClientRect(); return {{x:r.left+r.width/2,y:r.top+r.height/2}}}})()""")
    if not r:
        raise AssertionError(f"要素が見つからないか見えていません: {sel}")
    return r["x"], r["y"]


def click_sel(ed, sel):
    x, y = center_of(ed, sel)
    ed.click(x, y)
    ed.wait(0.15)


def start_from_menu(ed):
    """ファイルメニューの「曲を解析（テンポ・構成）…」"""
    click_sel(ed, "#mFileBtn")
    click_sel(ed, "#mFileMenu button[data-act=analyze]")


def wait_tempo_dialog(ed):
    wait_until(ed, "!!document.querySelector('#dirtyDlg.anaTempo')", label="テンポの推定の画面")


def dialog_lines(ed):
    return ed.js("[...document.querySelectorAll('#dirtyDlg.anaTempo .atLine')].map(e=>e.textContent)")


def dialog_buttons(ed):
    return ed.js("[...document.querySelectorAll('#dirtyDlg.anaTempo .ddBtns button')].map(b=>({v:b.dataset.v,text:b.textContent,dis:b.disabled,pri:b.classList.contains('pri')}))")


def dialog_choose(ed, v):
    click_sel(ed, f"#dirtyDlg.anaTempo button[data-v={v}]")


def wait_band(ed, n_sections=4):
    """解析が終わって帯が出て、帯の上の知らせ（進み具合）が消えるまで（画面は次の描画で追いつく）"""
    wait_until(ed, f"(a=>a&&a.shown&&!a.running&&a.labels.length==={n_sections}&&(a.stale||a.msg===''))(window._dbgApp.analysis())", label="解析の帯が出る")


def run_analysis(ed, choice="a", tempo=TEMPO, structure=STRUCT):
    """偽の応答で「曲を解析」を最後まで（テンポの画面では choice を押す。None＝画面が出ない時）"""
    ana_mock(ed, tempo=tempo, structure=structure)
    start_from_menu(ed)
    if choice:
        wait_tempo_dialog(ed)
        dialog_choose(ed, choice)
    wait_band(ed, len(structure["sections"]))


def band_point(ed, beat, row="sec"):
    """帯の拍 beat の位置（ページ座標）。row='sec'＝セクションの段／'seg'＝細かい区切りの段"""
    g = ed.js(f"window._dbgApp.anaScreen({beat})")
    return g["x"], g[row]


# ---- 解析からクリップを作る（js/analysis/ana-clips.js・editor-app.js の anaOpenClips/anaMakeClips） ----
CLIPS_ITEM = ("クリップを作る…", "Create clips…")   # 帯のメニューの項目（日本語・英語）


def hide_menus(ed):
    ed.js("[...document.querySelectorAll('#ctxmenu')].forEach(m=>m.style.display='none');true")


def menu_texts(ed):
    return ed.js("[...document.querySelectorAll('#ctxmenu > button')].map(b=>b.textContent)")


def menu_press(ed, texts):
    """開いているメニューの、文字が texts のどれかの項目を本物のクリックで押す"""
    p = ed.js(f"""(()=>{{ const b=[...document.querySelectorAll('#ctxmenu > button')].find(b=>{json.dumps(list(texts), ensure_ascii=False)}.includes(b.textContent));
      if(!b) return null; const r=b.getBoundingClientRect(); return {{x:r.left+r.width/2,y:r.top+r.height/2}}; }})()""")
    assert p, f"メニューに {texts} がありません: {menu_texts(ed)}"
    ed.move(p["x"], p["y"]); ed.wait(0.05)
    ed.click(p["x"], p["y"]); ed.wait(0.2)


def open_clips(ed, via="dots", beat=10):
    """帯の「⋯」（via='dots'）か、帯のセクションの右クリック（via='band'・拍 beat）→「クリップを作る…」。押す前のメニューの項目を返す"""
    hide_menus(ed)
    if via == "band":
        x, y = band_point(ed, beat)
        ed.click(x, y, button="right")
    else:
        click_sel(ed, "#anaMenuBtn")
    wait_until(ed, "getComputedStyle(document.getElementById('ctxmenu')).display!=='none'", label="解析のメニュー")
    items = menu_texts(ed)
    menu_press(ed, CLIPS_ITEM)
    return items


def wait_clips_dialog(ed):
    wait_until(ed, "!!document.querySelector('#dirtyDlg[data-ana=clips] .ddBtns button')", label="解析からクリップを作る画面")


def clips_dialog(ed):
    """解析からクリップを作る画面の中身（無ければ None）: 題・単位・単独編集にするレーン・難易度・リンク・注意・まとめ・ボタン"""
    return ed.js("""(d=>d&&({title:d.querySelector('.lkTitle').textContent, text:d.innerText,
      units:[...d.querySelectorAll('input[name=acUnit]')].map(i=>({v:i.value,checked:i.checked,dis:i.disabled,text:i.closest('label').innerText})),
      eo:[...d.querySelectorAll('input[name=acEo]')].map(i=>({v:i.value,checked:i.checked,dis:i.disabled})),
      diffs:[...d.querySelectorAll('.acDiffChk')].map(i=>({dk:i.dataset.dk,checked:i.checked,dis:i.disabled,text:i.closest('label').innerText,tip:i.closest('label').title})),
      link:d.querySelector('#acLink').checked, warn:d.querySelector('.acWarn').style.display!=='none',
      sum:d.querySelector('.acSum').textContent, btns:[...d.querySelectorAll('.ddBtns button')].map(b=>b.textContent)}))(document.querySelector('#dirtyDlg[data-ana=clips]'))""")


def clips_pick(ed, unit=None, eo=None, diffs=(), link=None):
    """画面の選択を本物のクリックで変える: unit='sec'|'seg'|'both'・eo='sec'|'seg'・diffs＝チェックを切り替える難易度のキー・link＝自動リンクの入/切"""
    D = "#dirtyDlg[data-ana=clips] "
    if unit:
        click_sel(ed, D + f"input[name=acUnit][value={unit}]")
    if eo:
        click_sel(ed, D + f"input[name=acEo][value={eo}]")
    for dk in diffs:
        click_sel(ed, D + f".acDiffChk[data-dk='{dk}']")
    if link is not None and ed.js(f"document.querySelector('{D}#acLink').checked") != link:
        click_sel(ed, D + "#acLink")


def clips_ok(ed):
    """［作る］を押して画面が閉じるまで待つ"""
    click_sel(ed, "#dirtyDlg[data-ana=clips] .ddBtns button.pri")
    wait_until(ed, "!document.querySelector('#dirtyDlg[data-ana=clips]')", label="解析からクリップを作る画面が閉じる")


# ---- 曲を取り込んだ時の「曲を解析しますか？」（2026-10-20・song-analysis.js の songLoaded） ----
# テストの環境は既定で聞かない（tools/cdp.py の Editor.TEST_SETTINGS＝bsnm_anaAsk '0'）。確かめる時は ask_on で聞く設定にする
ASK = "#dirtyDlg[data-ana=ask]"
# MEDIA から Music へ入れるのと同じ経路（loadSongFromItem）で、中身が basic.wav の音源を name の名前で取り込む（BPM は今のまま）。新しく取り込んだか（再接続・失敗は false）を返す
_LOAD_SONG_JS = """(async()=>{ const blob=await (await fetch('tools/fixtures/basic.wav',{cache:'no-store'})).blob();
  const file=new File([blob],%NAME%,{type:'audio/wav'});
  return await window._dbg.rt.loadSongFromItem({isMusic:true,name:'x',songFh:{getFile:async()=>file},info:{_beatsPerMinute:window._dbgApp.state().BPM}},0); })()"""


def ask_on(ed):
    """曲を取り込んだ時に解析するか聞く設定にする（キーを消す＝初めて使う人と同じ）"""
    ed.js("localStorage.removeItem('bsnm_anaAsk');true")


def load_song_media(ed, name="song2.wav"):
    return ed.js(_LOAD_SONG_JS.replace("%NAME%", json.dumps(name)))


# ---- 解析が終わった時の「次にやること」の案内と、溝の［🧩 クリップを作る］（2026-10-20・song-analysis.js の showGuide / syncClipsBtn） ----
# テストの環境は既定で出さない（tools/cdp.py の Editor.TEST_SETTINGS＝bsnm_anaGuide '0'）。確かめる時は guide_on で出す設定にする
GUIDE = "#dirtyDlg[data-ana=guide]"


def guide_on(ed):
    """解析が終わった時に案内を出す設定にする（キーを消す＝初めて使う人と同じ）"""
    ed.js("localStorage.removeItem('bsnm_anaGuide');true")


def wait_guide(ed):
    wait_until(ed, f"!!document.querySelector('{GUIDE}')", label="解析が終わった時の案内")


def guide_dialog(ed):
    """案内の中身（無ければ None）: 題・手順・画像（読めたか・幅）・説明・「次から出さない」・ボタン・全文"""
    return ed.js(f"""(d=>d&&({{title:d.querySelector('.agHead').textContent, steps:[...d.querySelectorAll('.agList li')].map(e=>e.textContent),
      img:(i=>i&&{{src:i.getAttribute('src'), ok:i.complete&&i.naturalWidth>0, w:i.naturalWidth, alt:i.alt}})(d.querySelector('.agFig img')),
      cap:(c=>c&&c.textContent)(d.querySelector('.agFig figcaption')), never:d.querySelector('.agChk').textContent, neverOn:d.querySelector('#anaGuideNever').checked,
      btns:[...d.querySelectorAll('.ddBtns button')].map(b=>({{v:b.dataset.v,text:b.textContent,pri:b.classList.contains('pri')}})),
      text:d.innerText}}))(document.querySelector('{GUIDE}'))""")


def analysis_tour(ed, scan):
    """英語表示の点検（english_ui_helpers.tour）用: 曲を取り込んだ時の確認・解析中の帯・テンポの画面・解析が終わった時の案内・帯・溝の［クリップを作る］・
    右クリックのメニュー・ツールチップ・目盛りが変わった知らせ・
    テンポの推定結果・解析からクリップを作る（断りの知らせ・確認の画面・作った後のクリップ名と知らせ）"""
    if ed.js("window._dbgApp.view()") != "nle":   # 帯は NLE の画面（INFO では隠れる）
        ed.move(1200, 300); ed.wait(0.2); ed.key("Tab"); ed.wait(0.6)
    # 曲を取り込んだ時の「曲を解析しますか？」: 聞く設定にして別の名前の曲を取り込む →「次から聞かない」→［今はしない］（下の知らせ）
    ask_on(ed)
    load_song_media(ed, "song2.wav")
    wait_until(ed, f"!!document.querySelector('{ASK}')", label="曲を解析しますか")
    scan(ed, "曲の解析 曲を取り込んだ時の確認")
    click_sel(ed, f"{ASK} #anaAskNever")
    click_sel(ed, f"{ASK} .ddBtns button[data-v=later]")
    wait_until(ed, f"!document.querySelector('{ASK}')", label="曲を解析しますかが閉じる")
    scan(ed, "曲の解析 次から聞かない（下の知らせ）")
    ana_mock(ed, status_t1=[{"waitFor": "t", "then": {"ok": True, "state": "running", "stage": "tempo", "progress": 0.4}}] + status_seq("tempo", TEMPO))
    guide_on(ed)   # 解析が終わった時の案内も出す
    click_sel(ed, "#anaStartBtn")
    wait_until(ed, "(a=>a&&a.running&&a.running.stage==='tempo')(window._dbgApp.analysis())", label="解析中")
    scan(ed, "曲の解析 解析中")
    ana_go(ed, "t")
    wait_tempo_dialog(ed); scan(ed, "曲の解析 テンポの画面")
    dialog_choose(ed, "none")
    wait_band(ed)
    # 解析が終わった時の「次にやること」の案内 →「次から出さない」→［Got it］（下の知らせ・溝の［Create clips］が光る）
    wait_guide(ed)
    wait_until(ed, f"(i=>!i||i.complete)(document.querySelector('{GUIDE} img'))", label="案内の画像")
    scan(ed, "曲の解析 解析が終わった時の案内")
    click_sel(ed, f"{GUIDE} #anaGuideNever")
    click_sel(ed, f"{GUIDE} .ddBtns button.pri")
    wait_until(ed, f"!document.querySelector('{GUIDE}')", label="案内が閉じる")
    scan(ed, "曲の解析 案内を次から出さない（下の知らせ）・溝の［クリップを作る］")
    x, y = band_point(ed, 10)
    ed.move(x, y); ed.wait(0.3); scan(ed, "曲の解析 帯（セクションのツールチップ）")
    x2, y2 = band_point(ed, 18, "seg")
    ed.move(x2, y2); ed.wait(0.3); scan(ed, "曲の解析 帯（細かい区切りのツールチップ）")
    ed.click(x, y, button="right"); ed.wait(0.4); scan(ed, "曲の解析 帯の右クリック")
    ed.key("Escape"); ed.js("(()=>{const m=document.getElementById('ctxmenu'); if(m) m.style.display='none'; return 1})()")
    ed.js("[...document.querySelectorAll('#ctxmenu')].forEach(m=>m.style.display='none');true")
    click_sel(ed, "#anaMenuBtn"); ed.wait(0.3); scan(ed, "曲の解析 ⋯ のメニュー")
    ed.js("[...document.querySelectorAll('#ctxmenu > button')].find(b=>b.textContent.startsWith('Tempo')).click();true")
    wait_tempo_dialog(ed); scan(ed, "曲の解析 テンポの推定結果")
    click_sel(ed, "#dirtyDlg.anaTempo button[data-v=none]")
    # 目盛りが変わった（BPM を +1）
    click_sel(ed, "#bpmField .bfA[data-k=up]")
    wait_until(ed, "window._dbgApp.analysis().stale", label="目盛りが変わった知らせ"); scan(ed, "曲の解析 目盛りが変わった")
    ed.move(*center_of(ed, "#anaMsg")); ed.wait(0.2); scan(ed, "曲の解析 目盛りの知らせのツールチップ")
    # 名前の付け直し・マーカーへ書き出す（知らせの文）
    ed.js("[...document.querySelectorAll('#ctxmenu')].forEach(m=>m.style.display='none');true")
    click_sel(ed, "#anaMenuBtn"); ed.wait(0.2)
    ed.js("[...document.querySelectorAll('#ctxmenu > button')].find(b=>b.textContent.startsWith('Export')).click();true"); ed.wait(0.3)
    scan(ed, "曲の解析 マーカーへ書き出す")
    # 解析からクリップを作る: 目盛りが変わった時の断り → 目盛りを戻して確認の画面（既定・両方）→ 作る（知らせ・クリップ名・単独編集）
    open_clips(ed)
    wait_until(ed, "document.getElementById('errToast').style.display!=='none'&&document.getElementById('errToast').textContent.includes('beat grid')",
               label="目盛りが変わった時の断り")
    scan(ed, "曲の解析 クリップを作る（目盛りが変わった時の断り）")
    _drop_errors(ed, "The beat grid")
    click_sel(ed, "#bpmField .bfA[data-k=dn]")
    wait_until(ed, "!window._dbgApp.analysis().stale", label="目盛りを戻す")
    open_clips(ed, via="band")
    wait_clips_dialog(ed); scan(ed, "曲の解析 クリップを作る画面")
    clips_pick(ed, unit="both"); scan(ed, "曲の解析 クリップを作る画面（両方）")
    clips_ok(ed)
    wait_until(ed, "window._dbgApp.nle().editOnly===0", label="作ったレーンを単独編集")
    scan(ed, "曲の解析 クリップを作った後")


def _drop_errors(ed, part):
    """想定どおりのエラー表示（showErr は console.error も出す）を回収して消す（t.no_errors() で誤検知しないため）"""
    ed.wait(0.05)
    ed._events[:] = [e for e in ed._events if not (e.get("method") == "Runtime.consoleAPICalled" and e.get("params", {}).get("type") == "error"
                     and any(part in str(a.get("value", "")) for a in e.get("params", {}).get("args", [])))]

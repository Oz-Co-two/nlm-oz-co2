"""審査の指摘（js/review/review-panel.js・2026-10-27）のテストの共通部品。
見本の文は実物の「形」をまねて作った物（中身は作り物。実物の他人の文章はリポジトリに入れない）。
- rv_import(ed, texts): 文を渡して読み込みの確認の画面を出し（rt.reviewPanel.importTexts）、難易度を選び・C3 の印を変え・［読み込む］を押す
- rv(ed): 開発用窓口の状態（_dbgApp.review()）
- review_tour(ed, scan): 英語表示の総点検（english_ui_helpers.tour）用に、読み込み・一覧・飛ぶ・書き出し・貼り付け・消すの画面を回る
"""
import json
import time

# 素材 rich の Expert: ノーツ 1〜6（2個ずつ）・7.5・10・12…／ボム 8・21／壁 9・23／アーク 14・18／チェーン 10・12／ライト 0・2・4…
SAMPLE = """Expert
SomeMapper

4 - first note looks off
7.53 - slightly early?
13-15 - this part feels cramped
    continuation of the previous line
100 - nothing here
general thought without a beat
231.g - unreadable line

One Saber Ex+
5 - other mode"""

NO_HEAD = """2 - a note without a heading
3, 5 - two spots"""


def rv(ed):
    return ed.js("window._dbgApp.review()")


def wait_until(ed, expr, timeout=15.0, label=""):
    end = time.time() + timeout
    v = None
    while time.time() < end:
        v = ed.js(expr)
        if v:
            return v
        ed.wait(0.05)
    raise AssertionError(f"待ち合わせが {timeout} 秒で終わりません: {label or expr}（最後の値 {v!r}）")


def rv_open_import(ed, texts):
    """読み込みの確認の画面を出す。texts: [(ファイル名 or None, 文)]"""
    arr = [{"name": n, "text": s} for n, s in texts]
    ed.js(f"window._dbg.rt.reviewPanel.importTexts({json.dumps(arr, ensure_ascii=False)}); true")
    wait_until(ed, "!!document.querySelector('#dirtyDlg[data-rv=rvImport]')", label="読み込みの確認の画面")


def rv_import(ed, texts, picks=None, c3=None, replace=False, ok=True):
    """picks: 難易度の選択（画面の上から順に値）、c3: {難易度: bool}（C3 の印）。ok=False なら画面を出したまま返す"""
    rv_open_import(ed, texts)
    if picks:
        ed.js(f"""(()=>{{ const v={json.dumps(picks)}; [...document.querySelectorAll('#dirtyDlg .rvPickSel')].forEach((s,i)=>{{ if(v[i]){{ s.value=v[i]; s.dispatchEvent(new Event('change',{{bubbles:true}})); }} }}); return true; }})()""")
    if c3:
        ed.js(f"""(()=>{{ const v={json.dumps(c3)}; for(const [d,on] of Object.entries(v)){{ const i=document.querySelector(`#dirtyDlg .rvC3Opt input[data-d="${{d}}"]`); if(i){{ i.checked=on; i.dispatchEvent(new Event('change',{{bubbles:true}})); }} }} return true; }})()""")
    if replace:
        ed.js("(()=>{ const i=document.querySelector('#dirtyDlg input[name=rvExisting][value=replace]'); i.checked=true; i.dispatchEvent(new Event('change',{bubbles:true})); return true; })()")
    if ok:
        ed.js("document.querySelector('#dirtyDlg[data-rv=rvImport] .ddBtns button.pri').click(); true")
        wait_until(ed, "!document.querySelector('#dirtyDlg[data-rv=rvImport]')", label="読み込みの確認の画面が閉じる")
        ed.wait(0.1)


def rv_row(ed, text):
    """一覧の行（文に text を含む）の画面の中央（ページ座標）"""
    r = ed.js(f"""(()=>{{ const row=[...document.querySelectorAll('#rvPanel .rvItem')].find(r=>(r.querySelector('.rvText')||{{textContent:''}}).textContent.includes({json.dumps(text)}));
      if(!row) return null; const det=row.closest('details'); if(det) det.open=true; row.scrollIntoView({{block:'center'}}); const q=(row.querySelector('.rvText')||row).getBoundingClientRect(); return {{x:q.left+Math.min(40,q.width/2), y:q.top+q.height/2, id:row.dataset.id}}; }})()""")
    if not r:
        raise AssertionError(f"一覧に行がありません: {text}")
    return r


def rv_click_row(ed, text):
    r = rv_row(ed, text)
    ed.click(r["x"], r["y"])
    wait_until(ed, f"(d=>d.cur==={json.dumps(r['id'])}&&!!d.msg.text)(window._dbgApp.review())", label=f"行のクリックで移動: {text}")
    ed.wait(0.15)
    return r["id"]


def review_tour(ed, scan):
    """英語表示の総点検: 読み込みの確認（難易度の選択・注意）・一覧・飛んだ知らせ・拍の無い行・書き出し（2種類）・貼り付け・消すの確認"""
    rv_open_import(ed, [("Mod.txt", SAMPLE), (None, NO_HEAD)])
    ed.js("(()=>{ const d=document.querySelector('#dirtyDlg .rvWarns'); if(d) d.open=true; return 1; })()")
    scan(ed, "審査の指摘の読み込み")
    ed.js("document.querySelector('#dirtyDlg[data-rv=rvImport] .ddBtns button.pri').click(); true")
    wait_until(ed, "window._dbgApp.review().open", label="審査の指摘の一覧")
    ed.js("(()=>{ document.querySelectorAll('#rvPanel details').forEach(d=>d.open=true); return 1; })()")
    scan(ed, "審査の指摘の一覧")
    rv_click_row(ed, "first note"); scan(ed, "審査の指摘: 飛ぶ")
    rv_click_row(ed, "nothing here"); scan(ed, "審査の指摘: 見つからない")
    rv_click_row(ed, "slightly early"); scan(ed, "審査の指摘: 近い物")
    ed.js("document.querySelector('#rvPanel .rvExport').click(); true")
    wait_until(ed, "!!document.querySelector('#dirtyDlg[data-rv=rvExportDlg]')", label="書き出しの画面")
    scan(ed, "審査の指摘: 書き出し（返事）")
    ed.js("(()=>{ const i=document.querySelector('#dirtyDlg input[name=rvXKind][value=check]'); i.checked=true; i.dispatchEvent(new Event('change',{bubbles:true})); return 1; })()")
    wait_until(ed, "(p=>!!p&&p.value.length>0)(document.querySelector('#dirtyDlg .rvXPre'))||/no findings|There are/.test(document.querySelector('#dirtyDlg .rvXNote').textContent)",
               timeout=30, label="NLM の確かめの結果")
    scan(ed, "審査の指摘: 書き出し（NLM の確かめ）")
    ed.js("document.querySelector('#dirtyDlg .ddBtns button[data-v=cancel]').click(); true"); ed.wait(0.2)
    ed.js("document.querySelector('#rvPanel .rvPaste').click(); true")
    wait_until(ed, "!!document.querySelector('#dirtyDlg[data-rv=rvPasteDlg]')", label="貼り付けの画面")
    scan(ed, "審査の指摘: 貼り付け")
    ed.js("document.querySelector('#dirtyDlg .ddBtns button[data-v=cancel]').click(); true"); ed.wait(0.2)
    ed.js("document.querySelector('#rvPanel .rvClear').click(); true")
    wait_until(ed, "!!document.querySelector('#dirtyDlg[data-rv=rvClearDlg]')", label="消すの確認")
    scan(ed, "審査の指摘: 消すの確認")
    ed.js("document.querySelector('#dirtyDlg .ddBtns button[data-v=cancel]').click(); true"); ed.wait(0.2)
    ed.js("document.querySelector('#rvPanel .rvClose').click(); true"); ed.wait(0.2)


# ---- C3: 曲データを読み込む（bulkLoadSongData）で難易度ごとに違う BPM 変化の譜面を読む（tests/e2e/test_bulk_import.py と同じ偽のフォルダ） ----
_LOAD_JS = """(async()=>{
  const info=%s, files=%s;
  const wav=await (await fetch('tools/fixtures/basic.wav',{cache:'no-store'})).blob();
  const dir={name:'tempo_map', getFileHandle:async nm=>{
    if(nm===info._songFilename) return {name:nm,getFile:async()=>new File([wav],'basic.wav',{type:'audio/wav'})};
    if(!(nm in files)) throw new DOMException('not found','NotFoundError');
    return {name:nm,getFile:async()=>new File([JSON.stringify(files[nm])],nm,{type:'application/json'})}; }};
  await window._dbg.rt.bulkLoadSongData({name:'tempo_map',info,dir});
  return true; })()"""


def bulk_info(bpm, diffs):
    """diffs: [(難易度, 難易度の名前 or None)]"""
    rank = {"Easy": 1, "Normal": 3, "Hard": 5, "Expert": 7, "ExpertPlus": 9}
    return {"_version": "2.1.0", "_songName": "Review Tempo", "_songSubName": "", "_songAuthorName": "a", "_levelAuthorName": "m",
            "_beatsPerMinute": bpm, "_songTimeOffset": 0, "_shuffle": 0, "_shufflePeriod": 0, "_previewStartTime": 1, "_previewDuration": 2,
            "_songFilename": "song.egg", "_coverImageFilename": "", "_environmentName": "DefaultEnvironment",
            "_difficultyBeatmapSets": [{"_beatmapCharacteristicName": "Standard", "_difficultyBeatmaps": [
                {"_difficulty": d, "_difficultyRank": rank[d], "_beatmapFilename": d + "Standard.dat", "_noteJumpMovementSpeed": 16, "_noteJumpStartBeatOffset": 0,
                 **({"_customData": {"_difficultyLabel": lab}} if lab else {})}
                for d, lab in diffs]}]}


def v3_dat(bpm_events, beats):
    return {"version": "3.3.0", "bpmEvents": bpm_events,
            "colorNotes": [{"b": b, "x": 1, "y": 0, "c": 0, "d": 1, "a": 0} for b in beats],
            "bombNotes": [], "obstacles": [], "sliders": [], "burstSliders": [], "basicBeatmapEvents": []}


def bulk_load(ed, info, files):
    ed.js(_LOAD_JS % (json.dumps(info), json.dumps(files)))
    wait_until(ed, "document.getElementById('errToast').textContent.includes('一括読み込みしました')", label="一括読み込みの終わり")

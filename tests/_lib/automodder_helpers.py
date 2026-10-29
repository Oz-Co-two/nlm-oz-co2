"""譜面チェックの AutoModder のタブ（js/automodder/・serve.py の /__automodder/*）のテストの共通部品（e2e_misc・visual・英語の画面の点検で使う）。

- am_spy(ed, cfg): /__automodder/* への fetch をページ内で記録する。cfg=None なら実サーバーへ通す（プラグイン未導入の本物の応答）。
  cfg={'status':応答, 'run':応答または[応答,…], 'install':…, 'check':…} ならサーバーへ行かずその応答を返す（キューは最後を残して消費）。
  GitHub への通信・実行ファイルの取り込みは一切しない（test_rating.py の rating_spy と同じ作り）。
- am_result(): 素材 rich（Hard＝ノーツ7個・Expert）に合わせた偽の結果（AutoModder v1.6.6 の出力の形・automodder_plugin.py で整えた後の形）。
  物の拍・位置は素材の実物の物（本物のプラグインで rich を確かめた時の結果から選んだ）。
"""
import json

_AM_JS = r"""(()=>{
  const A=window.__am={calls:[],cfg:__CFG__};
  const of=window.fetch.bind(window);
  window.fetch=async function(url,opt){
    const u=String(url);
    if(u.startsWith('__automodder/')){
      const act=u.slice(13); let body=null; try{ body=JSON.parse(opt.body); }catch(_){}
      A.calls.push({act,method:(opt&&opt.method)||'GET',headers:(opt&&opt.headers)||{},body});
      if(A.cfg===null) return of(url,opt);   // 記録だけ（実サーバーへ通す）
      const q=A.cfg[act]; const r=Array.isArray(q)?(q.length>1?q.shift():q[0]):q;
      if(A.hold&&act==='run') await new Promise(res=>{ A.release=res; });   // hold=true の間は run の応答を止める（実行中の表示を見る）
      return new Response(JSON.stringify(r),{status:200,headers:{'content-type':'application/json'}}); }
    return of(url,opt); };
  return true; })()"""

REPO = "https://github.com/example/nlm-automodder"
AM_INSTALLED = {"ok": True, "protocol": 1, "current": "0.1.0", "automodder": "1.6.6",
                "installed": [{"version": "0.1.0", "protocol": 1, "compatible": True, "automodder": "1.6.6"}], "repo": REPO}
AM_NONE = {"ok": True, "protocol": 1, "current": None, "automodder": None, "installed": [], "repo": REPO}

PANEL_DONE = ("(()=>{const p=document.getElementById('mcPanel');return !!p&&p.style.display!=='none'"
              "&&!p.querySelector('.mcRerun').disabled&&p.querySelector('.mcBody').children.length>0})()")
AM_DONE = "!!document.querySelector('#mcPanel .amMeta')"   # 結果の一覧の最後の行（版・秒）が出た


def am_spy(ed, cfg=None):
    ed.js(_AM_JS.replace("__CFG__", json.dumps(cfg)))


def am_calls(ed):
    return ed.js("window.__am.calls")


def am_acts(ed):
    return [c["act"] for c in am_calls(ed)]


def _note(b, x, y, c, sec):
    return {"type": "note", "beat": b, "x": x, "y": y, "color": c, "seconds": sec}


def _r(name, sev, diff, desc, objs=(), data=None, ct="X"):
    return {"name": name, "characteristic": "Standard" if diff else None, "difficulty": diff, "difficultyRank": {"Hard": 5, "Expert": 7}.get(diff),
            "severity": sev, "checkType": ct, "description": desc, "objects": list(objs), "data": data or {}}


HOT = "There must be at least 1.5 seconds of time before any interactable objects"


def am_result(**over):
    res = [
        _r("Song Name", "Passed", None, "The song name field is not empty", ct="SongInfo"),
        _r("BPM", "Inconclusive", None, "The maps BPM must be set to the song BPM or a multiple of it. This cannot be automatically detected currently",
           data={"BPM": "Could not be found"}, ct="SongInfo"),
        _r("Song Preview", "Suggestion", None, "The song preview is using default values. Consider changing it",
           data={"PreviewStartTime": "12", "PreviewDuration": "10"}, ct="SongInfo"),
        _r("Hot Start", "Error", "Expert", HOT, [_note(1.0, 1, 0, 0, 0.5)], {"CurrentBeat": "1", "MinimumBeat": "3"}),
        _r("Hot Start", "Error", "Expert", HOT, [_note(1.0, 2, 0, 1, 0.5)], {"CurrentBeat": "1", "MinimumBeat": "3"}),
        _r("Hot Start", "Error", "Expert", HOT, [_note(2.0, 1, 0, 0, 1.0)], {"CurrentBeat": "2", "MinimumBeat": "3"}),
        _r("Parity Warning", "Warning", "Expert", "Parity degree difference", [_note(18.0, 2, 0, 1, 8.8)], {"WarningType": "180 degree difference"}),
        _r("Parity Warning", "Warning", "Expert", "Parity degree difference", [_note(10.0, 1, 2, 0, 5.0)], {"WarningType": "180 degree difference"}),
        _r("Fused Object", "Error", "Expert", "Objects cannot collide within 0.074 in the same line",
           [_note(24.0, 1, 1, 0, 11.2), {"type": "wall", "beat": 23.0, "x": 0, "y": 2, "color": None, "seconds": 10.8}]),
        _r("Wall", "Passed", "Expert", "No issue with hidden objects, movement, wall size and duration detected"),
        _r("Vision Block", "Passed", "Expert", "No issue with vision from notes and bombs detected"),
        _r("Statistical Data", "Data", "Expert", "Statistical data of the difficulty", data={"Pass": "0.47", "Tech": "1.59", "EBPM": "43.29"}),
    ]
    out = {"ok": True, "version": "0.1.0", "automodder": {"version": "1.6.6", "commit": "0c2621507170c427506297457c8abdef7765dad1"},
           "config": "default", "elapsedMs": 900, "songLength": 16.0, "results": res,
           "criteria": {"info": {"SongName": "Success", "BPM": "Warning", "Preview": "Warning"},
                        "diff": {"Standard": {"Hard": {"difficultyRank": 5, "notes": 7, "skipped": "tooFewNotes", "highest": "Fail", "error": False, "crit": None},
                                              "Expert": {"difficultyRank": 7, "notes": 40, "skipped": None, "highest": "Fail", "error": False,
                                                         "crit": {"HotStart": "Fail", "VisionBlock": "Success"}}}}},
           "errors": [], "truncated": False}
    out.update(over)
    return out


def open_mapcheck(ed):
    from info_helpers import file_menu   # tests/e2e_info（呼ぶ側が読み込み先に足している）
    from e2e_helpers import wait_until
    file_menu(ed, "mapcheck")
    wait_until(ed, PANEL_DONE, timeout=20, label="チェック結果の表示")


def reopen_mapcheck(ed):
    """INFO の［🔍 譜面チェック］で開き直す＝前回のタブのまま開く口（メニューの「譜面チェック」は 2026-10-28 から決まったタブで開く）"""
    from info_helpers import click_sel, to_info
    from e2e_helpers import wait_until
    to_info(ed)
    click_sel(ed, "#iMapCheck", "譜面チェックのボタン")
    wait_until(ed, PANEL_DONE, timeout=20, label="チェック結果の表示")


def to_am(ed):
    from info_helpers import click_sel
    from e2e_helpers import wait_until
    click_sel(ed, "#mcPanel .mcTab[data-tab=am]", "AutoModder のタブ")
    wait_until(ed, "document.getElementById('mcPanel').classList.contains('amMode')&&!!document.querySelector('#mcPanel .amBanner')",
               label="AutoModder のタブの中身")


def am_tour(ed, scan):
    """英語の画面の点検（english_ui_helpers.tour）: 譜面チェックの AutoModder のタブの、未導入・取り込みの説明・結果（応答は偽物）"""
    from info_helpers import click_sel
    from e2e_helpers import wait_until
    am_spy(ed, {"status": AM_NONE, "install": AM_INSTALLED, "run": am_result()})
    open_mapcheck(ed)
    to_am(ed)
    wait_until(ed, "!!document.querySelector('#mcPanel .amOpen')", label="取り込みのボタン")
    scan(ed, "AutoModder（未導入）")
    click_sel(ed, "#mcPanel .amOpen", "取り込む…")
    wait_until(ed, "!!document.querySelector('#mcPanel .amBox')", label="取り込みの説明")
    scan(ed, "AutoModder（取り込みの説明）")
    click_sel(ed, "#mcPanel .amInstall", "GitHub から取り込む")
    wait_until(ed, AM_DONE, label="AutoModder の結果")
    ed.js("(()=>{document.querySelectorAll('#mcPanel details').forEach(d=>d.open=true);return 1})()")
    scan(ed, "AutoModder（結果）")
    click_sel(ed, "#mcPanel .mcTab[data-tab=mc]", "BS Map Check")
    click_sel(ed, "#mcPanel .mcClose", "閉じる")
    ed.wait(0.3)

"""NLEのレーンの既定の数（2026-10-20・利用者の要望「新規作成した時のレーンの数を減らしたい」）。
仕様: 新規作成・プロジェクト無しで始める時はノーツ1本・ライト3本（ノーツの本数は環境設定「ノーツのレーンの本数」＝bsnm_noteLanes で変えられる）。
新規作成は前のプロジェクトのレーンの数・ロック／ソロ／ミュート／単独編集を持ち越さない。保存したプロジェクトは保存した数で開く
（古い版で作った3本のプロジェクトも3本。レーン数の記録が無いさらに古いファイルは当時の既定 3:3。どちらも使っている段が見えない数にはしない）。
ノーツが1本でも、3Dで置く・貼り付け・曲データを読み込む・解析からクリップを作る は、空きが無ければ一番上にレーンを足して動く（1回の Undo でレーンも戻る）。
素材 rich＝ノーツ3本・ライト3本で保存（Hard と Expert・ノーツのクリップは一番上の Notes 3）"""
import json

from analysis_helpers import clips_ok, clips_pick, load_song_media, open_clips, run_analysis, wait_clips_dialog
from e2e_helpers import bulk_load_rich_map, counts, dirty, hover_3d, place_at, wait_until
from nle_helpers import clips, hover, lane_y, menu, nle, nle_mouse, open_nle, scr, select, undo

HARD, EXPERT = "hardstandard.dat", "expertstandard.dat"


def _click_el(ed, sel):
    p = ed.js(f"(()=>{{const e=document.querySelector({json.dumps(sel)});if(!e)return null;const r=e.getBoundingClientRect();"
              f"return {{x:r.left+r.width/2,y:r.top+r.height/2}}}})()")
    assert p, f"要素が見つかりません: {sel}"
    ed.move(p["x"], p["y"])
    ed.click(p["x"], p["y"])


def _file_new(ed):
    """ファイルメニューの「新規」（未保存なら3択で「保存せずに続行」）"""
    _click_el(ed, "#mFileBtn")
    wait_until(ed, "document.getElementById('mFileMenu').style.display==='block'", label="ファイルメニューが開く")
    _click_el(ed, "#mFileMenu button[data-act='new']")
    wait_until(ed, "!!document.querySelector('#dirtyDlg .ddBtns button')||window._dbgApp.nle().clips.length===0", label="新規（または未保存の確認）")
    if ed.js("!!document.querySelector('#dirtyDlg .ddBtns button')"):
        _click_el(ed, "#dirtyDlg .ddBtns button:nth-child(2)")   # 保存せずに続行
    wait_until(ed, "window._dbgApp.nle().clips.length===0&&window._dbgApp.state().counts.notes===0", label="新規で空になる")


def _all_shown(ed):
    """ノーツ・ライトの全部のレーンが、スクロールしなくても表示窓に収まっている（既定の画面 1600×980）"""
    g, s = nle(ed), ed.js("window._dbgApp.nleScreen(0)")
    ok = all(g["vp"]["n"][0] - 1 <= y and y + s["laneH"] <= g["vp"]["n"][1] + 1 for y in s["notes"])
    return ok and all(g["vp"]["l"][0] - 1 <= y and y + s["laneHL"] <= g["vp"]["l"][1] + 1 for y in s["lights"])


def _tracks(ed, lk="n"):
    """全難易度のクリップの (難易度, 段, 拍)"""
    return sorted((c["dk"], c["track"], c["beat"]) for c in ed.js("window._dbgApp.links().clips") if c["lk"] == lk)


def test_blank_and_new_project_reset_lanes(t):
    '''起動直後（プロジェクト無し）はノーツ1本・ライト3本で全部見える。レーンを増やし（ノーツ5・ライト4）ロック・ミュート・ソロ・単独編集を付けてから
    ファイル→新規（未保存の確認で「保存せずに続行」）→ ノーツ1本・ライト3本に戻り、レーンの状態も持ち越さない・未保存でない・履歴も空'''
    ed = open_nle(t)
    t.eq(nle(ed)["lanes"], {"n": 1, "l": 3}, "起動直後はノーツ1本・ライト3本")
    t.ok(_all_shown(ed), "全部のレーンが見えている")
    s, g = ed.js("window._dbgApp.nleScreen(0)"), nle(ed)
    t.ok(s["laneH"] >= 45 and s["laneHL"] >= 34, f"ノーツのレーンは単独編集の帯が入る 45px 以上・ライトは 34px 以上（{s['laneH']}・{s['laneHL']}）")
    t.ok(abs(s["lights"][-1] + s["laneHL"] - g["vp"]["l"][1]) < 0.6, f"レーンは表示窓を隙間なく埋める（スクロールは出ない）: {s['lights']} / {g['vp']}")
    t.eq((g["scroll"]["maxN"], g["scroll"]["maxL"]), (0, 0), "スクロールは出ない")
    t.eq(dirty(ed)["lamp"], False, "起動直後は未保存でない")
    ed = open_nle(t, "rich")
    t.eq(nle(ed)["lanes"], {"n": 3, "l": 3}, "保存したプロジェクトは保存した数（古い版で作った3本）")
    gx = scr(ed)["left"] + 20
    for n in (4, 5):
        menu(ed, gx, lane_y(ed, "n", 0), "レーンを追加")
        wait_until(ed, f"window._dbgApp.nle().lanes.n==={n}", label=f"ノーツのレーンを {n} 本に")
    menu(ed, gx, lane_y(ed, "l", 0), "レーンを追加")
    wait_until(ed, "window._dbgApp.nle().lanes.l===4", label="ライトのレーンを4本に")
    hover(ed, 8, "n", 0); ed.key("l")   # 9本＝表示窓に入りきらないので、上の方のレーン（スクロールしなくても見える所）で
    hover(ed, 8, "l", 0); ed.key("m")
    hover(ed, 8, "l", 1); ed.key("s")
    hover(ed, 8, "n", 1); ed.key("e")
    wait_until(ed, "(g=>g.lock.length===1&&g.mute.length===1&&g.solo.length===1&&g.editOnly===1)(window._dbgApp.nle())", label="レーンの状態を付ける")
    _file_new(ed)
    g = nle(ed)
    t.eq(g["lanes"], {"n": 1, "l": 3}, "新規はノーツ1本・ライト3本に戻る（前の数を持ち越さない）")
    t.eq((g["lock"], g["mute"], g["solo"], g["editOnly"]), ([], [], [], None), "ロック・ミュート・ソロ・単独編集も持ち越さない")
    t.ok(_all_shown(ed), "スクロールしなくても全部のレーンが見える")
    t.eq(dirty(ed)["lamp"], False, "新規の直後は未保存でない")
    t.eq(ed.js("window._dbgApp.state().undo"), 0, "履歴も空")
    nle_mouse(ed)
    undo(ed)
    ed.wait(0.2)
    t.eq(nle(ed)["lanes"], {"n": 1, "l": 3}, "Ctrl+Z を押しても前のプロジェクトのレーンに戻らない")
    t.no_errors()


def test_open_uses_saved_lane_counts(t):
    '''保存したプロジェクトは保存したレーンの数で開く（今のレーンの数・既定には関係しない）。レーン数の記録が無い古いファイルは 3:3、
    記録より下の段にクリップがある（壊れた）ファイルはそのクリップが見える数。プロジェクト無し（applyProject(null)）は既定の 1:3'''
    ed = open_nle(t, "rich")
    rich = ed.js("window._dbg.rt.buildProjectText()")
    gx = scr(ed)["left"] + 20
    menu(ed, gx, lane_y(ed, "n", 0), "レーンを追加")
    wait_until(ed, "window._dbgApp.nle().lanes.n===4", label="ノーツのレーンを4本に")
    four = ed.js("window._dbg.rt.buildProjectText()")
    for _ in range(2):
        ed.js("window._dbg.rt.laneAdd('n')")   # 開く前の今のプロジェクトはノーツ6本

    def opened(text, label):
        ed.js(f"window._dbg.rt.applyOpenedProject(JSON.parse({json.dumps(text)}),{{name:'t.nlmf'}})")
        wait_until(ed, "window._dbgApp.nle().clips.length>0", label=label)
        return nle(ed)["lanes"]
    t.eq(opened(four, "4本のプロジェクトを開く"), {"n": 4, "l": 3}, "保存した4本で開く")
    t.eq(dirty(ed)["lamp"], False, "開いた直後は未保存でない")
    t.eq(opened(rich, "3本のプロジェクトを開く"), {"n": 3, "l": 3}, "古い版で作った3本のプロジェクトは3本（前の4本を持ち越さない）")
    old = json.loads(rich)
    old.pop("notesLanes"); old.pop("lightLanes")
    t.eq(opened(json.dumps(old), "記録の無いファイル"), {"n": 3, "l": 3}, "レーン数の記録が無い古いファイルは 3:3")
    for s in old["difficulties"][EXPERT]["sections"]:
        if s.get("lk", "n") == "n":
            s["track"] = 4                                      # 記録が無く、Expert のクリップが Notes の5段目にある
    t.eq(opened(json.dumps(old), "記録が無く下の段にクリップ"), {"n": 5, "l": 3}, "使っている段（Expert の5段目）が見える数")
    bad = json.loads(rich)
    bad["notesLanes"] = 1                                       # 記録は1本だが Hard のクリップは3段目（壊れた・手で書き換えた）
    for s in bad["difficulties"][HARD]["sections"]:
        if s.get("lk", "n") == "n":
            s["track"] = 2
    t.eq(opened(json.dumps(bad), "記録より下の段にクリップ"), {"n": 3, "l": 3}, "記録より下の段のクリップも隠さない")
    ed.js("(async()=>{ await window._dbg.rt.applyProject(null); return 1; })()")   # プロジェクト無し
    wait_until(ed, "window._dbgApp.nle().lanes.n===1", label="プロジェクト無し")
    t.eq(nle(ed)["lanes"], {"n": 1, "l": 3}, "プロジェクト無しは既定の 1:3")
    t.no_errors()


def test_one_lane_place_lock_and_paste(t):
    '''ノーツ1本の新規: 3Dで置くと Notes 1 にクリップができる（レーンは増えない）。Notes 1 をロックして置くと一番上にレーンを足してそこへ置き、
    1回の Undo でレーンも戻る。NLEでクリップを同じ拍へ貼ると、空きが無いので一番上にレーンを足して貼る'''
    ed = open_nle(t)
    hover_3d(ed)
    place_at(ed, 1, 0)
    t.eq([(c["track"], c["beat"]) for c in clips(ed, "n")], [(0, 0)], "Notes 1 の拍0にクリップができる")
    t.eq(nle(ed)["lanes"]["n"], 1, "レーンは増えない")
    hover(ed, 2, "n", 0); ed.key("l")
    wait_until(ed, "window._dbgApp.nle().lock.includes('n0')", label="Notes 1 をロック")
    u0 = ed.js("window._dbgApp.state().undo")
    hover_3d(ed)
    place_at(ed, 2, 0)
    wait_until(ed, "window._dbgApp.nle().lanes.n===2", label="ロック中は一番上にレーンを足す")
    t.eq(sorted((c["track"], c["beat"]) for c in clips(ed, "n")), [(0, 0), (1, 0)], "足したレーンにクリップ・元のクリップは1段下（Notes 1 のまま）")
    t.eq(nle(ed)["lock"], ["n1"], "ロックは元のレーン（Notes 1）に付いたまま")
    t.eq(ed.js("window._dbgApp.state().undo") - u0, 1, "履歴は1つ")
    hover_3d(ed)
    ed.key("z", ctrl=True)
    wait_until(ed, "window._dbgApp.nle().lanes.n===1", label="Undo でレーンも戻る")
    t.eq((counts(ed)["notes"], nle(ed)["lock"]), (1, ["n0"]), "置いた物も消え、ロックも元のレーンに")
    hover(ed, 2, "n", 0); ed.key("l")
    wait_until(ed, "window._dbgApp.nle().lock.length===0", label="ロックを外す")
    c0 = clips(ed, "n")[0]
    select(ed, c0)
    ed.key("c", ctrl=True)
    wait_until(ed, "window._dbgApp.nle().clipboard===1", label="コピー")
    ed.key("v", ctrl=True)
    wait_until(ed, "!!window._dbgApp.nle().paste", label="貼り付けの追従")
    x, y = hover(ed, 0, "n", 0)
    ed.click(x, y)
    wait_until(ed, "window._dbgApp.nle().lanes.n===2&&window._dbgApp.nle().clips.length===2", label="一番上にレーンを足して貼る")
    t.eq(sorted((c["track"], c["beat"], c["n"]["notes"]) for c in clips(ed, "n")), [(0, 0, 1), (1, 0, 1)], "貼った物は足したレーン・元は1段下")
    t.eq(counts(ed)["notes"], 2, "中身も増える")
    nle_mouse(ed)
    undo(ed)
    wait_until(ed, "window._dbgApp.nle().lanes.n===1&&window._dbgApp.nle().clips.length===1", label="貼り付けの Undo でレーンも戻る")
    t.no_errors()


def test_one_lane_bulk_load_adds_lane(t):
    '''ノーツ1本で Notes 1 の拍0にクリップがある時に「曲データを読み込む」: 重なるので一番上にレーンを足して入れる（以前は10段目まで探し、
    レーンの外＝見えない段へ入ることがあった）。他の難易度（Expert）は今あるレーンの空いている段へ。Undo で全部戻る'''
    ed = open_nle(t)
    hover_3d(ed)
    place_at(ed, 1, 0)
    u0, before = ed.js("window._dbgApp.state().undo"), _tracks(ed)
    t.eq(before, [(HARD, 0, 0)], "準備: Hard の Notes 1 にクリップ")
    bulk_load_rich_map(ed)
    wait_until(ed, "window._dbgApp.nle().lanes.n===2", label="一番上にレーンを足す")
    g = nle(ed)
    t.eq(_tracks(ed), [(EXPERT, 0, 0), (HARD, 0, 0), (HARD, 1, 0)], "Hard は足したレーン（Notes 2）へ・前のクリップは Notes 1 のまま・Expert は空いている上の段")
    t.ok(all(c["track"] < g["lanes"]["n"] for c in ed.js("window._dbgApp.links().clips") if c["lk"] == "n"), "全部のクリップがレーンの中（見える）")
    t.ok(all(c["track"] < g["lanes"]["l"] for c in ed.js("window._dbgApp.links().clips") if c["lk"] == "l"), "ライトのクリップもレーンの中")
    hover_3d(ed)
    for _ in range(ed.js("window._dbgApp.state().undo") - u0):
        ed.key("z", ctrl=True)
        ed.wait(0.15)
    wait_until(ed, "window._dbgApp.nle().lanes.n===1", label="Undo でレーンも戻る")
    t.eq(_tracks(ed), before, "Undo で読み込んだクリップは全難易度から消える")
    t.no_errors()


def test_one_lane_analysis_clips_fit(t):
    '''ノーツ1本の新規に曲を読み込んで解析→「クリップを作る」（両方）: 一番上にノーツのレーンが2本増えて3本（ライト3本と合わせて6本）＝
    以前の既定（3:3）と同じ本数で、作ったレーンはスクロールしなくても見える（利用者の要望の元: 3本から作ると5本になり初期の高さでは見えなかった。
    テストの画面 1600×980 では 6本は最低の高さ（ノーツ 45px・ライト 34px）で入りきらず、表示窓は全部の高さに比例＝ノーツは上の2本が見える）。Ctrl+Z 1回で1本に戻る'''
    ed = open_nle(t)
    t.ok(load_song_media(ed, "basic.wav"), "曲を読み込む")
    wait_until(ed, "window._dbgApp.nle().music.audio", label="音源")
    run_analysis(ed, "none")   # テンポの画面（120 と提案 128）は「適用しない」
    u0 = ed.js("window._dbgApp.state().undo")
    open_clips(ed)
    wait_clips_dialog(ed)
    clips_pick(ed, unit="both")
    clips_ok(ed)
    wait_until(ed, "window._dbgApp.nle().lanes.n===3", label="ノーツのレーンが2本増える")
    g = nle(ed)
    t.eq((g["lanes"], g["editOnly"]), ({"n": 3, "l": 3}, 0), "ノーツ3本・ライト3本・作ったレーン（セクション）を単独編集")
    t.eq(sorted({c["track"] for c in clips(ed, "n")}), [0, 1], "作ったクリップは上の2本（Notes 1 は空のまま）")
    s = ed.js("window._dbgApp.nleScreen(0)")
    t.ok(all(y + s["laneH"] <= g["vp"]["n"][1] + 1 for y in s["notes"][:2]), f"作ったレーン（上の2本）はスクロールしなくても見える {s['notes']} / {g['vp']['n']}")
    t.eq(ed.js("window._dbgApp.state().undo") - u0, 1, "履歴は1つ")
    nle_mouse(ed)
    undo(ed)
    wait_until(ed, "window._dbgApp.nle().lanes.n===1", label="Undo で1本に戻る")
    t.eq(clips(ed, "n"), [], "作ったクリップも消える")
    t.no_errors()

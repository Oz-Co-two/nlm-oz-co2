"""js/replay/replay-marks.js: REPLAY の「点を重ねる」（2026-11-22）の計算。DOM を使わない部品をページ内で直接呼ぶ。
出来事の掃除（サーバー由来＝信用しない）・点の段・拍への並べ直し・NLE の印の範囲・物との合わせ方（拍 ±0.01・列・段・色・チェーンの頭と後ろ・
合わない数）と、物ごとに全部の出来事をなめない速さ。"""
import json
import re
from pathlib import Path

HEAD = "const M = await import('/js/replay/replay-marks.js');\n"


def _js(t, body):
    return t.ed.js("(async () => {" + HEAD + body + "})()")


def jq(v):
    return json.dumps(v, ensure_ascii=False)


def test_clean_events(t):
    '''cleanEvents: 知っている項目・形だけ（数でない・負の秒・知らない種類・列や段が数でない・色の無いノーツは捨てる）。
    ボムの色・向きは null、score/max は good の時だけ（点は 0〜満点へ）。壁は秒だけ・endSec'''
    t.fresh()
    raw = {"notes": [
        {"t": 1.0, "type": "good", "x": 1, "y": 0, "c": 0, "d": 1, "score": 112, "max": 115},
        {"t": 2.0, "type": "good", "x": 1, "y": 0, "c": 1, "d": 1, "score": 999, "max": 115},   # 点は満点まで
        {"t": "3", "type": "miss", "x": 1, "y": 0, "c": 0},                                       # 秒が文字
        {"t": -1, "type": "miss", "x": 1, "y": 0, "c": 0},                                        # 負の秒
        {"t": 4.0, "type": "hit", "x": 1, "y": 0, "c": 0},                                        # 知らない種類
        {"t": 5.0, "type": "miss", "x": 1.5, "y": 0, "c": 0},                                     # 列が整数でない
        {"t": 6.0, "type": "bad", "x": 2, "y": 1, "c": 2},                                        # 色が 0/1 でない
        {"t": 7.0, "type": "bomb", "x": 2, "y": 1, "c": 0, "d": 3, "score": 5, "max": 5},         # ボム＝色・向き・点は null
        {"t": 8.0, "type": "miss", "x": 3, "y": 2, "c": 1, "d": 0, "score": 50, "max": 115},      # ミスに点は付けない
        "junk", None,
    ], "walls": [{"t": 9.5}, {"t": "x"}, {"t": -2}, 7], "endSec": 15.25, "extra": "<b>"}
    r = _js(t, f"return M.cleanEvents({jq(raw)});")
    t.eq([(e["t"], e["type"]) for e in r["notes"]], [(1.0, "good"), (2.0, "good"), (7.0, "bomb"), (8.0, "miss")], "残る出来事")
    t.eq((r["notes"][0]["score"], r["notes"][0]["max"]), (112, 115), "good の点と満点")
    t.eq(r["notes"][1]["score"], 115, "点は満点まで")
    t.eq((r["notes"][2]["c"], r["notes"][2]["d"], r["notes"][2]["score"], r["notes"][2]["max"]), (None, None, None, None), "ボムの色・向き・点は null")
    t.eq((r["notes"][3]["score"], r["notes"][3]["max"]), (None, None), "ミスに点は無い")
    t.eq(r["walls"], [{"t": 9.5}], "壁は秒だけ・形の違う物は捨てる")
    t.eq(r["endSec"], 15.25, "endSec")
    t.eq(_js(t, "return [M.cleanEvents(null), M.cleanEvents({notes:'x', walls:{}})];"),
         [{"notes": [], "walls": [], "endSec": None}] * 2, "形の違う応答は空")
    t.no_errors()


def test_tiers(t):
    '''点の段: BL のリプレイアプリ（beat.js の colorAndScaleForScore・HSVConfig.judgments）と同じ＝「点数÷満点×115」が 115 以上・113 以上・110 以上・
    106 以上・100 以上・それ未満の6段と同じ色。チェーンの頭（満点 85）・後ろ（20）も同じ物差し。悪い切り方・見逃し・ボムは点の色に無い色の別の段。
    悪い方の段（worseTier）'''
    t.fresh()
    cases = [(115, 115), (114, 115), (113, 115), (112, 115), (110, 115), (109, 115), (106, 115), (105, 115), (100, 115), (99, 115), (0, 115),
             (85, 85), (84, 85), (83, 85), (80, 85), (74, 85), (73, 85), (20, 20), (19, 20)]
    r = _js(t, f"""return {{ g: {jq(cases)}.map(([s, m]) => M.tierOf({{type:'good', score:s, max:m}})),
      o: ['bad','miss','bomb'].map(k => M.tierOf({{type:k}})), nomax: M.tierOf({{type:'good', score:null, max:null}}),
      w: [M.worseTier('t115','t113'), M.worseTier('t106','t110'), M.worseTier('miss','bad'), M.worseTier(null,'low'), M.worseTier('t100', null), M.worseTier('low','bad')],
      tiers: M.TIERS, cut: M.CUT_TIERS, col: M.RP_COL }};""")
    t.eq(r["g"], ["t115", "t113", "t113", "t110", "t110", "t106", "t106", "t100", "t100", "low", "low",
                  "t115", "t113", "t110", "t106", "t100", "low", "t115", "t106"], "切った点の段（点数÷満点×115）")
    t.eq(r["o"], ["bad", "miss", "bomb"], "悪い切り方・見逃し・ボム")
    t.eq(r["nomax"], "t115", "点の無い good（点の付かない種類）は満点の段")
    t.eq(r["w"], ["t113", "t106", "miss", "low", "t100", "bad"], "悪い方の段")
    t.eq(r["tiers"], ["t115", "t113", "t110", "t106", "t100", "low", "bad", "miss", "bomb"], "段の並び（良い順）")
    t.eq(r["cut"], [[115, "t115"], [113, "t113"], [110, "t110"], [106, "t106"], [100, "t100"]], "段の下限＝BL の judgments の threshold")
    t.eq({k: r["col"][k].upper() for k in r["col"]},
         {"t115": "#FFFFFF", "t113": "#8500FF", "t110": "#00A3FF", "t106": "#00FF00", "t100": "#FFFF00", "low": "#FF0038",
          "bad": "#FF8000", "miss": "#FF0000", "bomb": "#FF00D0", "wall": "#C8CCD6"},
         "色: 切った物＝BL の点数の色（judgments の color）・バッド橙・ミス赤・ボムのマゼンタ・壁は灰色（どれとも違う）")
    t.no_errors()


def test_tiers_match_bl_viewer(t):
    '''段の下限と色が、リポジトリに写した BL のリプレイアプリ（replay-viewer/blreplay/build/build.*.js の judgments）と同じ（写しの版を上げた時に気づく）'''
    t.fresh()
    root = Path(__file__).resolve().parents[2]
    builds = sorted((root / "replay-viewer" / "blreplay" / "build").glob("build.*.js"))
    t.ok(builds, "BL のアプリの写しがある")
    if not builds:
        return
    src = builds[-1].read_text(encoding="utf-8", errors="replace")
    m = re.search(r"judgments:\[(.*?)\}\]", src)   # 配列の終わり（最後の要素の「}」と「]」）まで
    t.ok(m, "judgments の表が見つかる")
    if not m:
        return
    rows = re.findall(r"threshold:(-?[\d.]+),text:\"[^\"]*\",color:\[([\d.,]+)\]", m.group(1))
    bl = [(float(th), "#" + "".join("%02X" % round(float(v) * 255) for v in col.split(",")[:3])) for th, col in rows]
    r = _js(t, "return { cut: M.CUT_TIERS, col: M.RP_COL };")
    ours = [(float(th), r["col"][k].upper()) for th, k in r["cut"]] + [(-1.0, r["col"]["low"].upper())]
    t.eq(ours, bl, "段の下限と色（最後の -1 は「それ未満」）")
    t.ok("score/t.maxScore*115" in src, "点数÷満点×115 の式")
    t.no_errors()


def test_prep_and_range(t):
    '''prepEvents: 秒を拍へ（呼ぶ側の toBeat）・拍の順に並べる。NLE の印はミス・バッド・ボム・壁だけ（ni＝ノーツの出来事の番号・壁は -1）。
    同じ拍の印は ミス→バッド→ボム→壁 の順。marksRange は二分探索で見えている範囲だけ'''
    t.fresh()
    ev = {"notes": [
        {"t": 2.0, "type": "good", "x": 1, "y": 0, "c": 0, "score": 115, "max": 115},
        {"t": 1.0, "type": "bomb", "x": 1, "y": 0, "c": None},
        {"t": 1.0, "type": "miss", "x": 2, "y": 0, "c": 1},
        {"t": 3.0, "type": "bad", "x": 0, "y": 0, "c": 0},
    ], "walls": [{"t": 1.0}, {"t": 2.5}]}
    r = _js(t, f"""const p = M.prepEvents({jq(ev)}, s => s * 2);   // 1 秒＝2 拍
      return {{ n: p.n.map(e => [e.beat, e.type, e.tier]), nb: Array.from(p.nb), m: p.m.map(e => [e.beat, e.kind, e.ni]), mb: Array.from(p.mb), walls: p.walls,
        r1: M.marksRange(p, 1.5, 4.5), r2: M.marksRange(p, 6.5, 9), r3: M.marksRange(p, 0, 100), lb: [M.lowerBound([1,2,2,3], 2), M.lowerBound([1,2,3], 9), M.lowerBound([], 1)] }};""")
    t.eq(r["n"], [[2, "bomb", "bomb"], [2, "miss", "miss"], [4, "good", "t115"], [6, "bad", "bad"]], "ノーツ・ボムの出来事（拍の順）")
    t.eq(r["nb"], [2, 2, 4, 6], "拍の列")
    t.eq(r["m"], [[2, "miss", 1], [2, "bomb", 0], [2, "wall", -1], [5, "wall", -1], [6, "bad", 3]], "NLE の印（同じ拍は ミス→ボム→壁）")
    t.eq(r["walls"], 2, "壁の数")
    t.eq(r["r1"], [0, 3], "拍 1.5〜4.5 の印")
    t.eq(r["r2"], [5, 5], "印の無い範囲")
    t.eq(r["r3"], [0, 5], "全部")
    t.eq(r["lb"], [1, 3, 0], "lowerBound")
    t.no_errors()


def test_match_objects(t):
    '''matchObjects: 拍 ±0.01・列・段・色が同じ物に（ボムは列・段）。候補が複数なら拍の近い方・1つの出来事は1つの物にだけ。
    チェーンは頭と、頭の後ろから尾までの同じ色の出来事をまとめて悪い方の段に（ノーツを先に合わせる＝範囲の中のノーツの出来事を取らない）。
    合わない数（ノーツ・ボム）。貼り付けの追従中の物（_ghost）は合わせない'''
    t.fresh()
    ev = {"notes": [
        {"t": 1.0, "type": "good", "x": 1, "y": 0, "c": 0, "score": 115, "max": 115},     # n1
        {"t": 1.004, "type": "good", "x": 1, "y": 0, "c": 0, "score": 100, "max": 115},   # n1 の近く（二重のノーツの 2 つ目）
        {"t": 2.0, "type": "miss", "x": 2, "y": 0, "c": 1},                                # n2
        {"t": 3.0, "type": "bad", "x": 0, "y": 1, "c": 0},                                 # 色が違う＝合わない
        {"t": 4.003, "type": "good", "x": 3, "y": 0, "c": 1, "score": 111, "max": 115},   # n4（±0.01 の中）
        {"t": 5.02, "type": "good", "x": 0, "y": 0, "c": 0, "score": 115, "max": 115},    # n5 から 0.02 ずれ＝合わない
        {"t": 6.0, "type": "bomb", "x": 1, "y": 2, "c": None},                             # b6
        {"t": 7.0, "type": "bomb", "x": 2, "y": 2, "c": None},                             # 合わないボム
        {"t": 8.0, "type": "good", "x": 1, "y": 2, "c": 0, "score": 85, "max": 85},       # チェーンの頭
        {"t": 8.1, "type": "good", "x": 1, "y": 1, "c": 0, "score": 20, "max": 20},
        {"t": 8.2, "type": "miss", "x": 1, "y": 1, "c": 0},
        {"t": 8.3, "type": "good", "x": 2, "y": 2, "c": 1, "score": 104, "max": 115},     # チェーンの間の別の色のノーツ（n83）
        {"t": 8.4, "type": "good", "x": 1, "y": 0, "c": 0, "score": 20, "max": 20},
        {"t": 9.0, "type": "good", "x": 1, "y": 0, "c": 0, "score": 115, "max": 115},     # _ghost の物と同じ所＝合わない
    ], "walls": [{"t": 2.5}]}
    objs = """{ notes: [n1, n1b, n2, n3, n4, n5, n83, g9], bombs: [b6], chains: [ch] }"""
    r = _js(t, f"""const p = M.prepEvents({jq(ev)}, s => s);
      const n1={{beat:1,x:1,y:0,c:0}}, n1b={{beat:1,x:1,y:0,c:0}}, n2={{beat:2,x:2,y:0,c:1}}, n3={{beat:3,x:0,y:1,c:1}}, n4={{beat:4,x:3,y:0,c:1}},
        n5={{beat:5,x:0,y:0,c:0}}, n83={{beat:8.3,x:2,y:2,c:1}}, g9={{beat:9,x:1,y:0,c:0,_ghost:true}}, b6={{beat:6,x:1,y:2}}, ch={{b:8,x:1,y:2,c:0,tb:8.4}};
      const R = M.matchObjects(p, {objs});
      const g = o => {{ const v = R.map.get(o); return v ? [v.tier, v.ev.score, v.links] : null; }};
      const cnt = M.tierCounts(R);
      return {{ n1: g(n1), n1b: g(n1b), n2: g(n2), n3: g(n3), n4: g(n4), n5: g(n5), n83: g(n83), g9: g(g9), b6: g(b6), ch: g(ch),
        un: [R.unNotes, R.unBombs], used: Array.from(R.used), cnt }};""")
    t.eq(r["n1"], ["t115", 115, 0], "一番近い出来事（同じ所の二重のノーツは近い順に 1 つずつ）")
    t.eq(r["n1b"], ["t100", 100, 0], "2 つ目の同じ所のノーツは残りの出来事")
    t.eq(r["n2"], ["miss", None, 0], "ミス")
    t.eq(r["n3"], None, "色が違えば合わない")
    t.eq(r["n4"], ["t110", 111, 0], "±0.01 拍の中")
    t.eq(r["n5"], None, "0.02 拍ずれると合わない")
    t.eq(r["n83"], ["t100", 104, 0], "チェーンの間の別の色のノーツ（ノーツが先）")
    t.eq(r["g9"], None, "貼り付けの追従中の物は合わせない")
    t.eq(r["b6"], ["bomb", None, 0], "ボム（列・段）")
    t.eq(r["ch"], ["miss", 85, 3], "チェーン＝頭と後ろ 3 つの悪い方（ミス）")
    t.eq(r["un"], [3, 1], "合わないノーツ（色違い・0.02 ずれ・_ghost の所）3 個・ボム 1 個")
    t.eq(r["cnt"]["miss"], 2, "段ごとの数（合った物ごと・チェーンは 1 つ）")
    t.no_errors()


def test_match_speed(t):
    '''速さ: 出来事 4 万・ノーツ 1 万でも合わせは 1 回 100ms 未満（物ごとに二分探索で ±tol だけ見る）。見えている範囲の印も二分探索'''
    t.fresh()
    r = _js(t, """
const notes = [], ev = { notes: [], walls: [] };
for (let i = 0; i < 10000; i++) { const b = i * 0.25, x = i % 4, c = i % 2; notes.push({ beat: b, x, y: 0, c });
  ev.notes.push({ t: b / 2, type: i % 50 ? 'good' : 'miss', x, y: 0, c, score: i % 50 ? 110 : null, max: i % 50 ? 115 : null }); }
for (let i = 0; i < 30000; i++) ev.notes.push({ t: 5000 + i * 0.01, type: 'good', x: 0, y: 0, c: 0, score: 115, max: 115 });   // 合わない出来事
const p = M.prepEvents(ev, s => s * 2);
const t0 = performance.now(); const R = M.matchObjects(p, { notes, bombs: [], chains: [] }); const ms = performance.now() - t0;
const t1 = performance.now(); let k = 0; for (let i = 0; i < 1000; i++) { const [a, b] = M.marksRange(p, i, i + 32); k += b - a; } const ms2 = performance.now() - t1;
return { ms, ms2, matched: R.map.size, un: R.unNotes, k };""")
    t.eq(r["matched"], 10000, "全部のノーツに合う")
    t.eq(r["un"], 30000, "合わない出来事の数")
    t.ok(r["ms"] < 100, f"合わせ 1 回 {r['ms']:.1f}ms（100ms 未満）")
    t.ok(r["ms2"] < 20, f"範囲 1000 回 {r['ms2']:.1f}ms")
    t.no_errors()

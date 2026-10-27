"""js/review/review-data.js: 審査の指摘を画面で扱う部品（保存の形へ移す・確かめる・飛ぶ先を探す・書き出しの形へ戻す・NLM の確かめの結果・C3 の拍の直し）。
見本は作り物（実物の他人の文章はリポジトリに入れない）。"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_review_txt import automodder_import   # noqa: E402  AutoModder v1.6.6 の取り込みの移植

HEAD = "const R = await import('/js/review/review-txt.js'); const D = await import('/js/review/review-data.js');\n"


def _js(t, body):
    return t.ed.js("(async () => {" + HEAD + body + "})()")


def jq(v):
    return json.dumps(v, ensure_ascii=False)


def _imp(t, text, parse=None, **o):
    """parseReviewText → importParsed（id は r1, r2 …）"""
    return _js(t, f"""let n=0; const p=R.parseReviewText({jq(text)}, {jq(parse or {})});
      return D.importParsed(p, {{src:'s1', nextId:()=>'r'+(++n), ...{jq(o)}}});""")


def test_import_pick_and_ids(t):
    '''読み込み: 難易度の分からない項目は見出しの名前ごとに選んだ難易度・字下げした細かい指摘の親と「^」の指す項目は id・まとめ（]）は取り込みごとの名前'''
    # 1行目が知らない難易度の名前（AT）・2行目が担当の名前の形
    r = _imp(t, "AT\nSomeone\n\n8 - custom\n\nHard\n4 - top\n      4.5 - sub\n5 - ^\n\nOne Saber Ex+\n9 - other", pick={"AT": "Expert"})
    got = [(x["id"], x["difficulty"], x["mode"], x["label"], x["beats"], x["text"], x["parent"], x["prev"]) for x in r["items"]]
    t.eq(got, [("r1", "Expert", "Standard", "AT", [8], "custom", None, None), ("r2", "Hard", "Standard", None, [4], "top", None, None),
               ("r3", "Hard", "Standard", None, [4.5], "sub", "r2", None), ("r4", "Hard", "Standard", None, [5], "^", None, "r3"),
               ("r5", "ExpertPlus", "OneSaber", None, [9], "other", None, None)], "難易度・親・前の項目")
    t.ok(all(x["src"] == "s1" and x["done"] is False and x["reply"] == "" for x in r["items"]), "取り込み・済み・返事の初め")
    t.eq([x["difficulty"] for x in _imp(t, "4 - top", pick={"": "Normal"})["items"]], ["Normal"], "見出しの無い項目")
    t.eq([x["difficulty"] for x in _imp(t, "4 - top")["items"]], [None], "選ばなければ分からないまま")
    g = _imp(t, "Expert\n1 - a  ]\n2 - b  ] both")
    t.eq([(x["group"], x["groupText"]) for x in g["items"]], [("s1:1", "both"), ("s1:1", "both")], "まとめ")
    u = _js(t, "return [D.unknownGroups(R.parseReviewText('AT\\nSomeone\\n\\n5 - b\\n6 - c')), D.unknownGroups(R.parseReviewText('4 - a\\n\\nHard\\n5 - b'))];")
    t.eq(u, [[{"key": "AT", "label": "AT", "n": 2}], [{"key": "", "label": None, "n": 1}]], "難易度の分からない組")


def test_import_reply_from_file(t):
    '''マッパーの返事の入ったファイル（行の後ろに「 - fixed」）は返事の欄に入る'''
    r = _imp(t, "Expert\n4 - a - fixed\n5 - b - no change\n6 - c - changed to 7\n7 - d")
    t.eq([(x["text"], x["reply"]) for x in r["items"]], [("a", "fixed"), ("b", "no change"), ("c", "changed to 7"), ("d", "")], "返事")


def test_c3_orig_to_nlm(t):
    '''C3: 元の譜面のテンポ（f）の拍→秒→読み込んだ時の NLM のテンポ（t）の拍。読み込みで「元の拍として読む」難易度だけ直す'''
    tp = {"b": 120, "f": [[4, 240]], "t": []}
    v = _js(t, f"const tp={jq(tp)}; return [0,4,6,8,12].map(b=>D.origToNlm(tp,b));")
    t.eq(v, [0, 4, 5, 6, 8], "元の拍 0,4,6,8,12 → NLM（4拍目から倍の速さ）")
    v2 = _js(t, "return D.origToNlm({b:100,f:[],t:[[8,200]]}, 12);")
    t.eq(v2, 16, "逆向き（NLM の方に BPM 変化）: 元の拍12＝7.2秒 → 8拍(4.8秒)+2.4秒(200)＝16")
    t.eq(_js(t, "return [D.srcTpOk({b:120,f:[],t:[]}), D.srcTpOk({b:0,f:[],t:[]}), D.srcTpOk({b:120,f:[[1]],t:[]}), D.srcTpOk({b:120,f:[[1,-5]],t:[]}), D.srcTpOk(null), D.srcTpOk([1])]"),
         [True, False, False, False, False, False], "形の確かめ")
    r = _imp(t, "Expert+\n8 - x\n10-12 - y\n\nExpert\n8 - z", retime={"ExpertPlus": tp, "Expert": tp}, asOrig={"ExpertPlus": True, "Expert": False})
    t.eq([(x["difficulty"], x.get("nlmBeats"), x.get("nlmRanges")) for x in r["items"]],
         [("ExpertPlus", [6], []), ("ExpertPlus", [], [[7, 8]]), ("Expert", None, None)], "元の拍として読む難易度だけ NLM の拍を持つ")


def test_sanitize(t):
    '''保存した物（ファイル由来）を確かめる: 知らない項目・形の違う値・重なった id・拍の無い項目・指す物の無い親を捨てる'''
    v = {"v": 1, "srcs": [{"id": "s1", "name": "a.txt", "kind": "file", "at": "2026-10-27T01:02:03.004Z", "n": 1}, {"id": "bad id"}],
         "items": [{"id": "r1", "src": "s1", "line": 3, "difficulty": "Expert", "mode": "Standard", "label": "AT", "beats": [4], "ranges": [[6, 5]],
                    "nlmBeats": [5], "nlmRanges": [[7, 6]], "severity": "X", "text": "a\u202Eb", "cont": ["c", 5], "reply": "r", "done": True,
                    "repeats": True, "parent": "r9", "prev": "r1", "group": "s1:1", "x": 1},
                   {"id": "r1", "beats": [1]}, {"id": "r2", "beats": []}, {"id": "r3", "beats": [2], "nlmBeats": [1, 2], "severity": "Z", "mode": "a b"}],
         "notes": [{"text": "n", "kind": "divider", "difficulty": "Hard", "src": "s9"}]}
    s = _js(t, f"return D.sanitizeReview({jq(v)});")
    it = s["items"][0]
    t.eq((it["id"], it["ranges"], it["nlmRanges"], it["severity"], it["text"], it["cont"], it["parent"], it["prev"], "x" in it),
         ("r1", [[5, 6]], [[6, 7]], "X", "ab", ["c"], None, "r1", False), "1つ目（範囲の向き・制御文字・指す物の無い親）")
    t.eq([(x["id"], x["severity"], x["mode"], "nlmBeats" in x) for x in s["items"]], [("r1", "X", "Standard", True), ("r3", None, "Standard", False)],
         "重なった id・拍の無い項目は捨て、数の合わない NLM の拍は持たない")
    t.eq([x["id"] for x in s["srcs"]], ["s1"], "取り込み")
    t.eq(s["notes"], [{"src": None, "line": 0, "text": "n", "kind": "divider", "difficulty": "Hard", "mode": "Standard", "label": None}], "拍の無い行")
    t.eq(_js(t, "return [D.sanitizeReview(null), D.sanitizeReview([]), D.sanitizeReview({items:[],notes:[]})]"), [None, None, None], "中身が無い")


def test_pick_targets(t):
    '''飛ぶ先: ±0.01拍の物・無ければ ±1/16拍で一番近い拍の物（同じ拍は全部）・範囲の中・見つからなければ再生位置だけ'''
    pool = [{"beat": b, "ref": i} for i, b in enumerate([4, 4, 7.5, 8, 14, 14.0001, 20])]
    r = _js(t, f"const P={jq(pool)}; return [D.pickTargets(P,[{{a:4.003,b:null}}]), D.pickTargets(P,[{{a:7.53,b:null}}]), D.pickTargets(P,[{{a:100,b:null}}]),"
               f" D.pickTargets(P,[{{a:13,b:15}}]), D.pickTargets(P,[{{a:7.8,b:null}}]), D.pickTargets(P,[{{a:100,b:null}},{{a:20,b:null}}])];")
    t.eq((r[0]["kind"], r[0]["refs"], r[0]["seek"]), ("exact", [0, 1], 4.003), "ちょうど（.003 のずれは同じ拍）")
    t.eq((r[1]["kind"], r[1]["refs"], r[1]["seek"], round(r[1]["delta"], 4)), ("near", [2], 7.5, -0.03), "近い物（その物の拍へ）")
    t.eq((r[2]["kind"], r[2]["refs"], r[2]["seek"]), ("none", [], 100), "見つからない")
    t.eq((r[3]["kind"], r[3]["refs"], r[3]["seek"]), ("exact", [4, 5], 13), "範囲の中")
    t.eq(r[4]["kind"], "none", "1/16拍より遠い（7.8 と 8 は 0.2）")
    t.eq((r[5]["kinds"], r[5]["refs"], r[5]["seek"]), (["none", "exact"], [6], 100), "2か所の片方だけ")


def test_format_reply_roundtrip(t):
    '''返事を付けた .txt: 書いた拍（元の拍）のまま・行の後ろに「 - 返事」・済みで返事の無い物は選んだ時だけ fixed。読み直すと同じ指摘と返事'''
    text = "Expert\nOverall: fine.\n4 - a\n6, 7 - b\n10-12 - c\n    more\n\nHard\n2 - d"
    out = _js(t, f"""let n=0; const p=R.parseReviewText({jq(text)});
      const r=D.importParsed(p,{{src:'s1',nextId:()=>'r'+(++n),retime:{{Expert:{{b:120,f:[[0,240]],t:[]}}}},asOrig:{{Expert:true}}}});
      r.items[0].reply='moved'; r.items[1].done=true;
      const o={{responses:true, notes:D.toFormatNotes(r.notes)}};
      return [R.formatReviewText(D.toFormatItems(r.items),o), R.formatReviewText(D.toFormatItems(r.items,{{fixedForDone:true}}),o)];""")
    t.eq(out[0], "Expert\r\nOverall: fine.\r\n\r\n4 - a - moved\r\n6, 7 - b\r\n10-12 - c\r\n    more\r\n\r\nHard\r\n2 - d", "返事を付けた形（拍は書いたまま）")
    t.ok("6, 7 - b - fixed" in out[1], "済み＝fixed")
    keep = _js(t, """let n=0; const r=D.importParsed(R.parseReviewText('Expert+\\n(S) 4 - a\\n5 - b\\n(X) 6 - c'),{src:'s1',nextId:()=>'r'+(++n)});
      return R.formatReviewText(D.toFormatItems(r.items),{responses:true,severity:'keep',eol:'\\n'});""")
    t.eq(keep, "Expert+\n(S) 4 - a\n5 - b\n(X) 6 - c", "重さの印は書いてあった行だけ（severity:'keep'）")
    back = _js(t, f"return R.parseReviewText({jq(out[1])}, {{responses:true}});")
    t.eq([(x["difficulty"], x["beats"], x["ranges"], x["text"], x["response"]) for x in back["items"]],
         [("Expert", [4], [], "a", "moved"), ("Expert", [6, 7], [], "b", "fixed"), ("Expert", [], [[10, 12]], "c", None), ("Hard", [2], [], "d", None)], "読み直す")


def _fake_results():
    mc = {"general": [{"status": "warn", "key": "noCover"}],
          "diffs": [{"difficulty": "Hard", "results": [{"status": "rank", "key": "hotStart", "label": "Hot start", "objs": [{"beat": 0.5}]},
                                                       {"status": "info", "key": "x", "label": "Info only", "objs": [{"beat": 1}]}]},
                    {"difficulty": "ExpertPlus", "results": [{"status": "warn", "key": "parallelNotes", "label": "Parallel", "objs": [{"beat": 3}, {"beat": 3}]}]}]}
    bl = {"rules": [{"id": "R3.B", "findings": [{"d": "Hard", "status": "check", "key": "k1", "objs": [{"beat": b} for b in range(1, 11)]},
                                                 {"d": None, "status": "fail", "key": "k2", "objs": None}]},
                    {"id": "R5.A", "findings": [{"d": "ExpertPlus", "status": "fail", "key": "k3", "objs": [{"beat": 12.3333333}, {"beat": 4}]},
                                                 {"d": "Hard", "status": "pass", "key": "k4", "objs": [{"beat": 9}]}]}]}
    return mc, bl


def test_checks_to_items(t):
    '''NLM の確かめの結果 → 指摘の形: 違反＝(X)・要確認＝(?)・拍のある所見だけ（無い物は数）・難しい方から・1行に8拍まで・BS Map Check は選んだ時だけ'''
    mc, bl = _fake_results()
    r = _js(t, f"""const mc={jq(mc)}, bl={jq(bl)};
      const o={{fail:true, check:true, blText:(r,f)=>'msg '+f.key, mcText:r=>r.label}};
      return [D.checksToItems(mc,bl,o), D.checksToItems(mc,bl,{{...o,mc:true}}), D.checksToItems(mc,bl,{{...o,check:false}})];""")
    a = r[0]
    t.eq([(x["difficulty"], x["beats"], x["text"], x["severity"], x["origin"]) for x in a["items"]],
         [("ExpertPlus", [4, 12.333333], "[R5.A] msg k3 (NLM)", "X", "bl"),
          ("Hard", [1, 2, 3, 4, 5, 6, 7, 8], "[R3.B] msg k1 (NLM)", "?", "bl"), ("Hard", [9, 10], "[R3.B] msg k1 (NLM)", "?", "bl")], "BL評価リスト")
    t.eq(a["noBeat"], 1, "拍の無い所見の数")
    t.eq([(x["difficulty"], x["text"], x["severity"]) for x in r[1]["items"] if x["origin"] == "mc"],
         [("ExpertPlus", "[BS Map Check] Parallel (NLM)", "?"), ("Hard", "[BS Map Check] Hot start (NLM)", "X")], "BS Map Check（情報は入れない）")
    t.eq(r[1]["noBeat"], 2, "BS Map Check の全体の項目（拍なし）も数える")
    t.eq([x["severity"] for x in r[2]["items"]], ["X"], "要確認を入れない")


def test_checks_text_automodder(t):
    '''NLM の確かめの結果の .txt は AutoModder v1.6.6 の取り込みで読める: 前書きの行は数を含まない＝指摘にならない・拍と重さ・文'''
    mc, bl = _fake_results()
    header = "NLM check results (BeatLeader ranking criteria as read by NLM). Not an official BeatLeader or BS Map Check result."
    out = _js(t, f"""const r=D.checksToItems({jq(mc)},{jq(bl)},{{fail:true,check:true,blText:(r,f)=>'msg '+f.key,mcText:r=>r.label}});
      return [R.formatReviewText(r.items,{{header:[{jq(header)}]}}), R.formatReviewText(r.items,{{severity:true, header:[{jq(header)}]}})];""")
    plain, sev = out
    t.ok(plain.startswith(header + "\r\n\r\nExpert+\r\n4, 12.333 - [R5.A] msg k3 (NLM)\r\n"), plain[:200])
    am = automodder_import(sev.split("\r\n"))
    t.eq(am, [("Error", [4, 12.333], "R5.A] msg k3 (NLM)"), ("Inconclusive", [1, 2, 3, 4, 5, 6, 7, 8], "R3.B] msg k1 (NLM)"),
              ("Inconclusive", [9, 10], "R3.B] msg k1 (NLM)")], "AutoModder の取り込み（前書き・見出しは指摘にならない）")

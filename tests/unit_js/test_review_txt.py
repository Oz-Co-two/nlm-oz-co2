"""js/review/review-txt.js: 審査の指摘（「拍 - 文」の .txt・Discord の貼り付け）を読む／書き出す。
見本は実物の「形」をまねて作った短い文（中身は作り物。実物の他人の文章はリポジトリに入れない＝tools/review_txt_check.py で手元の実物を流す）。"""
import json
import re

HEAD = "const R = await import('/js/review/review-txt.js');\n"


def _js(t, body):
    return t.ed.js("(async () => {" + HEAD + body + "})()")


def jq(v):
    return json.dumps(v, ensure_ascii=False)


def P(t, text, **opts):
    """parseReviewText の結果"""
    return _js(t, f"return R.parseReviewText({jq(text)}, {jq(opts)});")


def F(t, items, **opts):
    """formatReviewText の結果"""
    return _js(t, f"return R.formatReviewText({jq(items)}, {jq(opts)});")


def spots(r):
    """項目ごとの (拍, 範囲, 文) の一覧"""
    return [(it['beats'], it['ranges'], it['text']) for it in r['items']]


def codes(r):
    return [w['code'] for w in r['warnings']]


# ---------------------------------------------------------------- AutoModder v1.6.6 の取り込み（BLMapCheck/Classes/Helper/GenericMod.cs）の移植
# 書き出した行を AutoModder がどう読むかを確かめるためだけのもの（重さ・拍・文）
_AM_NUM = r'^\d+([.,])?(\d+)?'
_AM_NUM2 = r'\d+([.,])?(\d+)?'


def _am_float(s):
    try:
        return float(s.replace(',', '.'))
    except ValueError:
        return -1.0


def automodder_import(lines):
    out, sev = [], 'Info'
    for line in lines:
        s = line.strip()
        low = line.lower()
        keyword = False
        if low.startswith('(x)'):
            sev, s = 'Error', s[3:].strip()
        elif line.startswith('(?)'):
            sev, s = 'Inconclusive', s[3:].strip()
        elif low.startswith('(s)'):
            sev, s = 'Suggestion', s[3:].strip()
        elif low.startswith('(i)') or low.startswith('(n)'):
            sev, s = 'Info', s[3:].strip()
        sub = s
        m = re.search(_AM_NUM2, s)
        if not m:
            continue
        beat = _am_float(m.group(0))
        if beat < 0:
            continue
        beats = []
        while True:
            loop = False
            beats.append(beat)
            sub = sub[m.start() + len(m.group(0)):].lstrip(',.').strip()
            if sub.startswith('and'):
                sub = sub[3:].strip()
                m = re.match(_AM_NUM, sub)
                if m:
                    keyword = True
                    beats.append(_am_float(m.group(0)))
                    sub = sub[m.end():].lstrip(',.').strip()
            else:
                m = re.match(_AM_NUM, sub)
                if m:
                    beat = _am_float(m.group(0))
                    if beat >= 0 and m.start() <= 2:
                        loop = True
            if not loop:
                break
        if not keyword and sub.startswith('to'):
            m2 = re.match(_AM_NUM, sub[2:].strip())
            if m2:
                beats.append(_am_float(m2.group(0)))
                comment = s
            else:
                comment = sub.strip()
        elif not keyword and sub.startswith('-'):
            m2 = re.match(_AM_NUM, sub[1:].strip())
            if m2 and _am_float(m2.group(0)) > beats[-1]:
                beats.append(_am_float(m2.group(0)))
                comment = s
            else:
                comment = sub.strip()
        else:
            comment = sub.strip()
        out.append((sev, beats, re.sub(r'^[^\w]+', '', comment)))
    return out


# ---------------------------------------------------------------- 拍の書き方

def test_separators(t):
    '''区切りの3種（「拍 - 文」「拍 文」「拍: 文」）と行頭の beat・箇条書きの「- 」を読む'''
    r = P(t, "12 - first thing\n13.5 second thing\n14: third thing\nbeat 27.5 - fourth\n- 30 (and repeats) fifth\n31.25  - sixth\n32- seventh")
    t.eq(spots(r), [([12], [], 'first thing'), ([13.5], [], 'second thing'), ([14], [], 'third thing'), ([27.5], [], 'fourth'),
                    ([30], [], 'fifth'), ([31.25], [], 'sixth'), ([32], [], 'seventh')], '拍と文')
    t.eq(r['items'][4]['repeats'], True, '(and repeats)')
    t.eq([it['line'] for it in r['items']], [1, 2, 3, 4, 5, 6, 7], '行番号')
    t.eq(r['notes'], [], '拍の無い行は無い')
    t.no_errors()


def test_dash_range_or_separator(t):
    '''` - ` は「数・-・数で後ろが大きければ範囲」。区切りが続けば確かな範囲、文が続けば ambiguous'''
    r = P(t, "\n".join([
        "66 - 68 maybe use one hand here",               # 範囲（文が続く＝区切りかもしれない）
        "34.5 - 35: try the layout in the picture",     # 範囲（: が続く）
        "47 - 48 - the mapping stops here",             # 範囲（- が続く）
        "25.5 - the angle is too sharp",                # 区切り
        "20 - 10 notes is too many",                    # 後ろが小さい＝区切り
        "44.75 - 1/16 late",                            # 分数は拍ではない＝区切り
        "63.5-64 - lower this part",                    # 空白なしの範囲
        "50-49 typo here",                              # 空白なしでも後ろが小さければ区切り
    ]))
    t.eq(spots(r), [([], [[66, 68]], 'maybe use one hand here'), ([], [[34.5, 35]], 'try the layout in the picture'),
                    ([], [[47, 48]], 'the mapping stops here'), ([25.5], [], 'the angle is too sharp'),
                    ([20], [], '10 notes is too many'), ([44.75], [], '1/16 late'), ([], [[63.5, 64]], 'lower this part'),
                    ([50], [], '49 typo here')], '範囲と区切り')
    t.eq([it['ambiguous'] for it in r['items']], [True, False, False, False, False, False, False, False], 'ambiguous')
    t.no_errors()


def test_ranges_and_lists(t):
    '''範囲 > to thru、複数 , & and「, and」、範囲と範囲を & でつなぐ形'''
    r = P(t, "\n".join([
        "19>24 - slightly off time",
        "52 to 54 - a few tweaks",
        "58 thru 59 - wall is too short",
        "80.234>81 - burst",
        "17, 22.733 - no double here",
        "70.25 & 70.75 - why chains",
        "83.25&91.25 - inline",
        "36.5 and 37 - smoother lead-in",
        "170, 186, and 202 - make these doubles",
        "23>24 & 166>167 - same sound",
        "46 to 61- same as hard",
    ]))
    t.eq(spots(r), [([], [[19, 24]], 'slightly off time'), ([], [[52, 54]], 'a few tweaks'), ([], [[58, 59]], 'wall is too short'),
                    ([], [[80.234, 81]], 'burst'), ([17, 22.733], [], 'no double here'), ([70.25, 70.75], [], 'why chains'),
                    ([83.25, 91.25], [], 'inline'), ([36.5, 37], [], 'smoother lead-in'), ([170, 186, 202], [], 'make these doubles'),
                    ([], [[23, 24], [166, 167]], 'same sound'), ([], [[46, 61]], 'same as hard')], '範囲と複数')
    t.eq([it['at'] for it in r['items']][:5], [19, 52, 58, 80.234, 17], '最初に書かれた位置')
    t.no_errors()


def test_repeats_and_paren(t):
    '''「…など」（30...・(etc.)・(& repeats)・, repeats・repeats）と括弧で同じ所（119.5 (343.5)）。小数は丸めない'''
    r = P(t, "\n".join([
        "21.75, 40... - lots of these",
        "29.33, 61.33, 157.33, ... - 29.299 (1/10 precision)",
        "14.5, 16.5 (etc.) lots of repeats",
        "199.5 (& repeats) - red feels late",
        "603.25, 607.25, repeats",
        "88, 96, 104 repeats",
        "19.5 (243.5) - to .562 (1/16)",
        "100 (0:23) the note spawns inside the wall",
        "117.333 - a",
        "153.66 - b",
        "233.583 - c",
        "122.417 - d",
        "20.5 - to .666",
    ]))
    t.eq([it['repeats'] for it in r['items']], [True, True, True, True, True, True, False, False, False, False, False, False, False], 'repeats')
    t.eq(spots(r)[:8], [([21.75, 40], [], 'lots of these'), ([29.33, 61.33, 157.33], [], '29.299 (1/10 precision)'),
                        ([14.5, 16.5], [], 'lots of repeats'), ([199.5], [], 'red feels late'), ([603.25, 607.25], [], 'repeats'),
                        ([88, 96, 104], [], 'repeats'), ([19.5, 243.5], [], 'to .562 (1/16)'),
                        ([100], [], '(0:23) the note spawns inside the wall')], '拍と文')
    t.eq([it['beats'][0] for it in r['items'][8:12]], [117.333, 153.66, 233.583, 122.417], '1/3 拍などの小数はそのまま')
    t.eq(r['items'][12]['text'], 'to .666', '「to .666」は文')
    t.no_errors()


def test_order_kept(t):
    '''拍の順に並べ替えない（書かれた順のまま）'''
    r = P(t, "50 - b\n10 - a\n30 - c")
    t.eq([it['at'] for it in r['items']], [50, 10, 30], '書かれた順')
    t.no_errors()


# ---------------------------------------------------------------- 難易度

def test_headings(t):
    '''見出しの行の各形（大文字小文字・コロン・Ex/EX/Expert・注記の括弧・太字・## ・[ ]）'''
    forms = [
        ("Expert+", 'ExpertPlus', 'Standard'), ("Expert+:", 'ExpertPlus', 'Standard'), ("ex+", 'ExpertPlus', 'Standard'),
        ("EX+:", 'ExpertPlus', 'Standard'), ("Ex+", 'ExpertPlus', 'Standard'), ("E+", 'ExpertPlus', 'Standard'),
        ("ExpertPlus", 'ExpertPlus', 'Standard'), ("***expert+***", 'ExpertPlus', 'Standard'), ("**Expert:**", 'Expert', 'Standard'),
        ("ex:", 'Expert', 'Standard'), ("expert", 'Expert', 'Standard'), ("Expert (repeats skipped)", 'Expert', 'Standard'),
        ("hard:", 'Hard', 'Standard'), ("Hard (would raise JD to 17-18)", 'Hard', 'Standard'), ("## Hard", 'Hard', 'Standard'),
        ("HD", 'Hard', 'Standard'), ("[Normal]", 'Normal', 'Standard'), ("normal", 'Normal', 'Standard'), ("EZ", 'Easy', 'Standard'),
        ("Easy:", 'Easy', 'Standard'), ("Standard Ex+", 'ExpertPlus', 'Standard'), ("Standard ex+", 'ExpertPlus', 'Standard'),
        ("One Saber Ex+", 'ExpertPlus', 'OneSaber'), ("OneSaber E+:", 'ExpertPlus', 'OneSaber'), ("OneSaber H:", 'Hard', 'OneSaber'),
        ("Lawless Expert", 'Expert', 'Lawless'), ("360Degree Hard", 'Hard', '360Degree'),
    ]
    for line, d, mode in forms:
        r = P(t, line + "\n10 - x")
        t.eq((r['items'][0]['difficulty'], r['items'][0]['mode']), (d, mode), f'見出し「{line}」')
        t.eq(len(r['sections']), 1, f'見出し「{line}」の数')
    r = P(t, "Hard (would raise JD to 17-18)\n10 - x")
    t.eq([(n['kind'], n['text']) for n in r['notes']], [('comment', 'would raise JD to 17-18')], '見出しの括弧は全体への意見')
    r = P(t, "and a couple more notes for ex+:\n10 - x")
    t.eq(r['items'][0]['difficulty'], 'ExpertPlus', 'コロンで終わる短い行の中の難易度')
    t.ok('heading-guess' in codes(r), '推測の見出しは warnings に出る')
    r = P(t, "One Saber Ex+\n10 - x")
    t.eq(r['items'][0]['otherMode'], True, 'Standard 以外は対象外の印')
    t.ok('other-mode' in codes(r), 'Standard 以外は warnings')
    t.no_errors()


def test_multi_sections(t):
    '''1つのファイルに見出しの行と ----- で難易度を分ける形（項目は見出しの難易度）'''
    r = P(t, "Ex+\n-----\n5 - a\n16.5 and 17 - b\n\nExpert\n-----\n20.25 - c\n\nHard\n-----\n28 to 40 - d\n\nStandard Normal\n------\n16.5 - e\n\nOne Saber Ex+\n-----------------\n22.5 - f")
    t.eq([(it['difficulty'], it['mode'], it['text']) for it in r['items']],
         [('ExpertPlus', 'Standard', 'a'), ('ExpertPlus', 'Standard', 'b'), ('Expert', 'Standard', 'c'), ('Hard', 'Standard', 'd'),
          ('Normal', 'Standard', 'e'), ('ExpertPlus', 'OneSaber', 'f')], '難易度とモード')
    t.eq([s['line'] for s in r['sections']], [1, 6, 10, 14, 18], '見出しの行')
    t.eq(r['notes'], [], '----- は notes に入れない')
    t.no_errors()


def test_first_line_and_mapper(t):
    '''1行目が難易度名・2行目が担当マッパー名（次が空行）。名前は sections と notes(mapper) に入る'''
    r = P(t, "Expert+\nSampleMapper\n\nNJS feels a bit slow, maybe try 17\n\n25.5 the red tower is behind a wall\n26 the arc looks busy")
    t.eq(r['sections'][0]['mapper'], 'SampleMapper', '担当マッパー')
    t.eq([(n['kind'], n['text']) for n in r['notes']], [('mapper', 'SampleMapper'), ('comment', 'NJS feels a bit slow, maybe try 17')], 'notes')
    t.eq(r['notes'][1]['hints'], [17], '文の中の数は候補だけ')
    t.eq([it['difficulty'] for it in r['items']], ['ExpertPlus', 'ExpertPlus'], '難易度')
    r = P(t, "Hard\n\n48.75 kept it for the new sound")
    t.eq(r['sections'][0]['mapper'], None, '見出しの次が空行なら名前は無い')
    r = P(t, "hard\nfine\n\n10 - x")
    t.eq(r['sections'][0]['mapper'], None, '「fine」は名前にしない')
    t.no_errors()


def test_custom_labels(t):
    '''独自の難易度名（AT・IN・「名前 (Ex+)」）。呼ぶ側の名前の表（_difficultyLabel→難易度）で難易度にする'''
    text = "AT\nSampleMapper\n\n25.5 red tower is behind a wall\n26 same as expert+"
    r = P(t, text)
    t.eq((r['items'][0]['difficulty'], r['items'][0]['label']), (None, 'AT'), '表が無ければ難易度は分からない（名前だけ）')
    t.ok('unknown-label' in codes(r), '分からない名前は warnings')
    t.eq(r['sections'][0]['mapper'], 'SampleMapper', '担当マッパー')
    r = P(t, text, labels={'AT': 'ExpertPlus', 'IN': 'Expert'})
    t.eq((r['items'][0]['difficulty'], r['items'][0]['label']), ('ExpertPlus', 'AT'), '名前の表')
    t.eq(codes(r), [], '表にあれば warnings なし')
    r = P(t, "IN\n\n12 - x", fileName='IN.txt', labels=[{'label': 'IN', 'difficulty': 'Expert'}])
    t.eq(r['items'][0]['difficulty'], 'Expert', 'ファイル名と同じ1行目・表は配列でもよい')
    r = P(t, "Sample's Extreme Demon (Ex+)\nSampleMapper\n\n28 starts with an arrow")
    t.eq((r['items'][0]['difficulty'], r['items'][0]['label']), ('ExpertPlus', "Sample's Extreme Demon"), '名前 (Ex+)')
    r = P(t, "Sample's Hard Demon (Ex)\n\n18 x", labels={"Sample's Hard Demon": 'Hard'})
    t.eq(r['items'][0]['difficulty'], 'Hard', '名前の表は括弧の中より優先')
    r = P(t, "Expert\n10 - x", labels={'Expert': 'ExpertPlus'})
    t.eq(r['items'][0]['difficulty'], 'ExpertPlus', '表は普通の名前より優先')
    t.ok('label-override' in codes(r), '普通の名前と違う意味になる時は warnings')
    t.no_errors()


def test_file_name(t):
    '''ファイル名の難易度（Expert.txt・Hard_1.txt・ExpertPlusStandard.txt）。中の見出しが優先。どちらも無ければ defaultDifficulty'''
    t.eq(P(t, "10 - x", fileName='Hard_1.txt')['items'][0]['difficulty'], 'Hard', 'Hard_1.txt')
    t.eq(P(t, "10 - x", fileName='C:/x/y/ExpertPlusStandard.txt')['items'][0]['difficulty'], 'ExpertPlus', 'ExpertPlusStandard.txt')
    t.eq(P(t, "10 - x", fileName='Mod.txt')['items'][0]['difficulty'], None, 'Mod.txt は難易度なし')
    t.eq(P(t, "10 - x", fileName='Mod.txt', defaultDifficulty='Expert')['items'][0]['difficulty'], 'Expert', 'defaultDifficulty')
    r = P(t, "Expert+\nSampleMapper\n\n10 x", fileName='Expert.txt')
    t.eq(r['items'][0]['difficulty'], 'ExpertPlus', '中の見出しが優先')
    t.eq(r['fileDifficulty'], 'Expert', 'ファイル名の難易度')
    t.ok('file-name-differs' in codes(r), 'ファイル名と違えば warnings')
    t.eq(P(t, "10 - x", fileName='1.txt')['items'][0]['difficulty'], None, '1.txt')
    t.no_errors()


# ---------------------------------------------------------------- 拍の無い行・続きの行

def test_continuation_and_subitems(t):
    '''字下げした行＝前の項目の続き。字下げした拍の行＝前の項目の細かい指摘（parent）。空行の後は続きにしない'''
    r = P(t, "\n".join([
        "40-48 the jumps could follow the kick",
        "        right now the rhythm feels flat",
        "52.5 this double is cramped",
        "81-84 the stream reads poorly",
        "        a few ideas:",
        "        81.5 make this horizontal",
        "            it plays better",
        "        82.25 move left one",
        "90 could be a dot",
        "",
        "    an indented line after a blank",
    ]))
    t.eq([(it['text'], it['cont'], it['parent']) for it in r['items']], [
        ('the jumps could follow the kick', ['right now the rhythm feels flat'], None),
        ('this double is cramped', [], None),
        ('the stream reads poorly', ['a few ideas:'], None),
        ('make this horizontal', ['it plays better'], 2),
        ('move left one', [], 2),
        ('could be a dot', [], None)], '続きと細かい指摘')
    t.eq([n['text'] for n in r['notes']], ['an indented line after a blank'], '空行の後は notes')
    t.no_errors()


def test_notes_and_dividers(t):
    '''全体への意見・方針の断り・区切りの線は notes に（kind）。文の中の数は hints'''
    r = P(t, "\n".join([
        "The intro feels off beat, please check the offset",
        "",
        "repeats are mostly skipped",
        "10 - x",
        "-- repeated section skipped --",
        "--------------- second chorus repeats ---------------",
        "-----",
        "20 - y",
        "same as ex+ except 40 and 96",
        "== Hard ==",
        "30 - z",
    ]))
    t.eq([(n['kind'], n['text'], n['line']) for n in r['notes']], [
        ('comment', 'The intro feels off beat, please check the offset', 1), ('comment', 'repeats are mostly skipped', 3),
        ('divider', 'repeated section skipped', 5), ('divider', 'second chorus repeats', 6),
        ('comment', 'same as ex+ except 40 and 96', 9)], 'notes')
    t.eq(r['notes'][4]['hints'], [40, 96], 'hints')
    t.eq(r['notes'][4]['after'], 1, '直前の項目の添字')
    t.eq(r['items'][2]['difficulty'], 'Hard', '「== Hard ==」は見出し')
    t.no_errors()


def test_same_as_prev(t):
    '''「^」「^^」「same ^」「same」「same as previous」＝前の項目と同じ指摘（prev）'''
    r = P(t, "Expert+\n10 - would move down\n11 - ^\n12 - ^^\n13: same ^\n14 - same\n15 same as previous\n16 - same as 10\n\nHard\n20 - same")
    t.eq([(it['sameAsPrev'], it['prev']) for it in r['items']],
         [(False, None), (True, 0), (True, 1), (True, 2), (True, 3), (True, 4), (False, None), (True, None)], '前の項目')
    t.eq(r['items'][6]['hints'], [10], '「same as 10」は hints')
    t.no_errors()


def test_bracket_group(t):
    '''行末の「]」で2行をまとめる書き方（groupText は「]」の後ろの共通の文）'''
    r = P(t, "37 - make this a tower?   ]\n37.5 - drop this tower?     ] both clash with the intro\n40 - other\n41 - a ]\n42 - b ] c")
    t.eq([(it['text'], it['group'], it['groupText']) for it in r['items']], [
        ('make this a tower?', 1, 'both clash with the intro'), ('drop this tower?', 1, 'both clash with the intro'), ('other', None, None),
        ('a', 2, 'c'), ('b', 2, 'c')], 'まとめ')
    t.no_errors()


def test_unreadable(t):
    '''書き誤り（231.g）は捨てずに notes(unreadable)＋warnings。時刻・2nd 等は拍として読まない'''
    r = P(t, "131.g - tower?\n1:23 - time is not a beat\n2nd drop feels better\n134 .5 is a typo in the middle")
    t.eq([(n['kind'], n['text']) for n in r['notes']],
         [('unreadable', '131.g - tower?'), ('comment', '1:23 - time is not a beat'), ('comment', '2nd drop feels better')], 'notes')
    t.eq([w['code'] for w in r['warnings']], ['unreadable'], 'warnings')
    t.eq(spots(r), [([134], [], '.5 is a typo in the middle')], '行の途中の書き誤りは文のまま')
    t.no_errors()


def test_severity(t):
    '''重さの印 (X)(?)(S)(N)(I)(Q)・「(suggestion)」。印の無い項目は null（前の行を引き継がない）'''
    r = P(t, "\n".join([
        "(S) [49.25 - 51, ...] streams alternate oddly",
        "(I) [109] unmapped sound",
        "(Q) [133.25 - 139] undermapped",
        "(Q) [289 - 291 & 293.25 - 295] half time",
        "(X) 200 - vision block",
        "(?) 210 - maybe a vision block",
        "(N) 220 - just a note",
        "230 - no mark",
        "77 (suggestion) - an arc would fit",
        "216 - 224 (suggestion): smoother",
        "324.5: (suggestion): cleaner",
        "96.75 - suggestion, shift these right",
    ]))
    t.eq([(it['severity'], it['mark']) for it in r['items']], [
        ('S', '(S)'), ('N', '(I)'), ('?', '(Q)'), ('?', '(Q)'), ('X', '(X)'), ('?', '(?)'), ('N', '(N)'), (None, None),
        ('S', '(suggestion)'), ('S', '(suggestion)'), ('S', '(suggestion)'), ('S', 'suggestion')], '重さ')
    t.eq(spots(r)[:4], [([], [[49.25, 51]], 'streams alternate oddly'), ([109], [], 'unmapped sound'), ([], [[133.25, 139]], 'undermapped'),
                        ([], [[289, 291], [293.25, 295]], 'half time')], '[ ] の中の拍')
    t.eq(r['items'][0]['repeats'], True, '[ … , ...]')
    t.eq([it['text'] for it in r['items'][8:12]], ['an arc would fit', 'smoother', 'cleaner', 'suggestion, shift these right'], '文')
    t.no_errors()


def test_discord_paste(t):
    '''Discord の本文: ``` の囲み（直後の拍）・メンション・自作の絵文字・太字/斜体・引用への返事・日本語の訳の行'''
    text = "\n".join([
        "<@123456789012345678>",
        "ex+",
        "```54 - the blue note feels late :someEmoji:",
        "199.5 (& repeats) - walls clip <a:dance:123456789012345678>",
        "**230.5 & 234.5** — I like *this* part",
        "```",
        "```",
        "IN GENERAL: the walls feel too dense",
        "4.5-5.25 - too many walls```",
        "> 84, 85.5 why towers here?",
        "they follow the snare",
        "271 would try a diagonal here",
        "ここは斜めを試してみてください",
    ])
    r = P(t, text)
    t.eq([(it['beats'], it['ranges'], it['text'], it['difficulty']) for it in r['items']], [
        ([54], [], 'the blue note feels late :someEmoji:', 'ExpertPlus'),
        ([199.5], [], 'walls clip :dance:', 'ExpertPlus'),
        ([230.5, 234.5], [], 'I like this part', 'ExpertPlus'),
        ([], [[4.5, 5.25]], 'too many walls', 'ExpertPlus'),
        ([84, 85.5], [], 'why towers here?', 'ExpertPlus'),
        ([271], [], 'would try a diagonal here', 'ExpertPlus')], '項目')
    t.eq(r['items'][1]['repeats'], True, '(& repeats)')
    t.eq((r['items'][4]['quoted'], r['items'][4]['response']), (True, 'they follow the snare'), '引用への返事')
    t.eq(r['items'][5]['cont'], ['ここは斜めを試してみてください'], '日本語の訳は続き')
    t.eq([n['text'] for n in r['notes']], ['IN GENERAL: the walls feel too dense'], 'notes')
    t.ok(all('<' not in it['text'] for it in r['items']), 'メンション・絵文字の記号は残らない')
    t.no_errors()


def test_automodder_forms(t):
    '''AutoModder の BeatLeader 用の形（「拍 | Unrankable - 文 -- Response: …」）と Discord 用の形（太字の拍の次の行に文）も読む'''
    r = P(t, "12.5, 13 | Unrankable - vision block -- Response: moved it\n**Beats: 20 | Suggestion**\nlead-in could be smoother")
    t.eq([(it['beats'], it['severity'], it['text'], it['response']) for it in r['items']],
         [([12.5, 13], 'X', 'vision block', 'moved it'), ([20], 'S', 'lead-in could be smoother', None)], '項目')
    t.no_errors()


def test_responses(t):
    '''マッパーが行の後ろに足した返事（ - fixed・ - No change・ - changed to …・ -fixed・… fixed）。3件以上で自動で分ける'''
    text = "\n".join([
        "21.5 - feels too strong - kept it to balance the hands",
        "24.75 - try an angle here - fixed",
        "27.333 - straighten this - fixed",
        "63 - why is this unmapped - No change",
        "67.5 - the setup is weak",
        "210 to 213 - same -fixed",
        "138 - same as 122 but for red fixed",
        "128 - would rework this double - changed to 126-127",
    ])
    r = P(t, text)
    t.eq(r['responses'], True, '自動で返事の形と見る')
    t.eq([(it['text'], it['response']) for it in r['items']], [
        ('feels too strong', 'kept it to balance the hands'), ('try an angle here', 'fixed'), ('straighten this', 'fixed'),
        ('why is this unmapped', 'No change'), ('the setup is weak', None), ('same', 'fixed'), ('same as 122 but for red', 'fixed'),
        ('would rework this double', 'changed to 126-127')], '返事')
    t.eq(r['items'][5]['sameAsPrev'], True, '返事を外した後の「same」')
    r = P(t, text, responses=False)
    t.eq((r['responses'], r['items'][1]['text'], r['items'][1]['response']), (False, 'try an angle here - fixed', None), 'responses=false')
    r = P(t, "10 - a - b\n11 - c")
    t.eq((r['responses'], r['items'][0]['text']), (False, 'a - b'), '返事の言葉が少なければ分けない')
    t.no_errors()


# ---------------------------------------------------------------- 文字コード・上限

def _dec(t, raw, **opts):
    return _js(t, f"try {{ return R.decodeReviewBytes(Uint8Array.from({list(raw)}), {jq(opts)}); }} catch (e) {{ return 'ERR:' + (e.code || e.message); }}")


def test_decode_bytes(t):
    '''BOM（UTF-8・UTF-16LE/BE）・BOM の無い UTF-16・Shift_JIS・Windows-1252・大きすぎる物'''
    s = "Expert+\r\n12 - café 直した"
    t.eq(_dec(t, s.encode('utf-8')), s, 'UTF-8（BOM なし）')
    t.eq(_dec(t, b'\xef\xbb\xbf' + s.encode('utf-8')), s, 'UTF-8（BOM あり）')
    t.eq(_dec(t, b'\xff\xfe' + s.encode('utf-16-le')), s, 'UTF-16LE（BOM）')
    t.eq(_dec(t, b'\xfe\xff' + s.encode('utf-16-be')), s, 'UTF-16BE（BOM）')
    t.eq(_dec(t, "Hard\r\n12 - x".encode('utf-16-le')), "Hard\r\n12 - x", 'UTF-16LE（BOM なし）')
    t.eq(_dec(t, "12 - 直しました".encode('cp932')), "12 - 直しました", 'Shift_JIS')
    t.eq(_dec(t, "12 - caf\xe9".encode('latin-1')), "12 - caf\xe9", 'Windows-1252')
    t.eq(_dec(t, b'1234567890', maxBytes=5), 'ERR:too-large', '大きすぎる物は読まない')
    r = _js(t, "const b = new TextEncoder().encode('Hard\\r\\n12 - a\\r\\n13 - b'); const r = R.parseReviewText(R.decodeReviewBytes(b.buffer)); return r.items.map(x => x.text);")
    t.eq(r, ['a', 'b'], 'ArrayBuffer・CRLF・最後の改行なし')
    t.no_errors()


def test_text_forms(t):
    '''LF・CR だけ・最後の改行あり・文字列の頭の BOM・タブの字下げ・見えない制御文字'''
    for nl in ("\n", "\r\n", "\r"):
        r = P(t, nl.join(["Hard", "10 - a", "\tcontinued", "11 - b"]) + nl)
        t.eq([(it['text'], it['cont']) for it in r['items']], [('a', ['continued']), ('b', [])], f'改行 {nl!r}')
    zw = chr(0x200b) + chr(0x202e)
    r = P(t, chr(0xfeff) + "Hard\n10 - a" + zw + "b")
    t.eq((r['items'][0]['difficulty'], r['items'][0]['text']), ('Hard', 'ab'), 'BOM と見えない文字を消す')
    t.no_errors()


def test_limits(t):
    '''長すぎる行は切る・行数の上限・項目の数の上限（warnings に出す）'''
    r = _js(t, "const r = R.parseReviewText('10 - ' + 'a'.repeat(R.REVIEW_LIMITS.maxLineChars + 50)); return [r.items[0].text.length, r.warnings.map(w => w.code)];")
    t.eq(r, [3995, ['line-too-long']], '長い行')
    r = _js(t, "const n = R.REVIEW_LIMITS.maxLines + 10; const r = R.parseReviewText(Array.from({length: n}, (_, i) => (i + 1) + ' - x').join('\\n')); return [r.items.length, r.warnings.map(w => w.code)];")
    t.eq(r, [10000, ['too-many-lines', 'too-many-items']], '行数・項目の数')
    t.eq(P(t, None)['items'], [], '文字列でない物は空')
    t.no_errors()


# ---------------------------------------------------------------- 書き出す

ITEMS = [
    {'difficulty': 'ExpertPlus', 'mode': 'Standard', 'beats': [12.5, 13], 'ranges': [], 'text': 'Vision block (NLM)', 'severity': 'X'},
    {'difficulty': 'ExpertPlus', 'mode': 'Standard', 'beats': [], 'ranges': [[20, 22]], 'text': 'Bombs are too close', 'severity': '?'},
    {'difficulty': 'Hard', 'mode': 'Standard', 'beats': [109.33333333], 'ranges': [], 'text': 'Maybe a dot', 'severity': None, 'repeats': True},
    {'difficulty': 'ExpertPlus', 'mode': 'Standard', 'beats': [30, 31.5], 'ranges': [[40, 41]], 'text': 'Mixed', 'severity': 'S'},
    {'difficulty': 'Hard', 'mode': 'Standard', 'beats': [0.4375], 'ranges': [[50, 50]], 'text': '3 notes are stacked', 'severity': 'N'},
]


def test_format_plain(t):
    '''実物と同じ手書きの形（見出し＋「拍, 拍 - 文」・CRLF・最後の改行なし）。難易度ごとに最初に出た順でまとめる'''
    s = F(t, ITEMS)
    t.eq(s, "\r\n".join([
        "Expert+", "12.5, 13 - Vision block (NLM)", "20-22 - Bombs are too close", "30, 31.5, 40-41 - Mixed", "",
        "Hard", "109.333... - Maybe a dot", "0.4375, 50: 3 notes are stacked"]), '書き出し')
    t.eq(F(t, ITEMS[:1], eol="\n", finalNewline=True), "Expert+\n12.5, 13 - Vision block (NLM)\n", 'LF・最後の改行')
    t.eq(F(t, [{'beats': [5], 'text': 'no difficulty'}, ITEMS[0]]), "5 - no difficulty\r\n\r\nExpert+\r\n12.5, 13 - Vision block (NLM)", '難易度の無い項目は先頭')
    t.eq(F(t, [{'difficulty': 'Expert', 'mode': 'OneSaber', 'beats': [5], 'text': 'x'}, {'difficulty': 'Expert', 'label': 'IN', 'beats': [6], 'text': 'y'}], useLabels=True),
         "OneSaber Expert\r\n5 - x\r\n\r\nIN (Expert)\r\n6 - y", 'モード・名前の見出し')
    t.eq(F(t, [{'beats': [-1, 'x', None], 'text': 'bad'}, {'beats': [], 'text': 'none'}]), "", '読めない拍の項目は書かない')
    t.no_errors()


def test_format_severity_and_responses(t):
    '''重さの印（印の無い項目は (N)）・返事を「 - 返事」で足す・先頭の行・全体への意見'''
    s = F(t, ITEMS[:3], severity=True)
    t.eq(s.split("\r\n"), ["Expert+", "(X) 12.5, 13 - Vision block (NLM)", "(?) 20-22 - Bombs are too close", "", "Hard", "(N) 109.333... - Maybe a dot"], '重さの印')
    items = [dict(ITEMS[0], response='moved the wall'), dict(ITEMS[1], response=None)]
    t.eq(F(t, items, responses=True).split("\r\n"), ["Expert+", "12.5, 13 - Vision block (NLM) - moved the wall", "20-22 - Bombs are too close"], '返事')
    s = F(t, ITEMS[:1], header=["Checked with NLM (approximate)", "2 problems found"],
          notes=[{'difficulty': 'ExpertPlus', 'text': 'JD looks fine'}, {'difficulty': 'ExpertPlus', 'kind': 'divider', 'text': 'repeats not listed'}])
    t.eq(s.split("\r\n"), ["Checked with NLM (approximate)", "Note: 2 problems found", "", "Expert+", "JD looks fine", "--- repeats not listed ---", "",
                           "12.5, 13 - Vision block (NLM)"], '先頭の行・全体への意見（数で始まる行は Note: を付ける）')
    t.no_errors()


def test_format_automodder_import(t):
    '''書き出した行を AutoModder v1.6.6 の取り込み（GenericMod.cs の移植）で読むと、拍・重さ・文がそのまま取れる'''
    s = F(t, ITEMS, severity=True)
    got = automodder_import(s.split("\r\n"))
    t.eq(got, [
        ('Error', [12.5, 13.0], 'Vision block (NLM)'),
        ('Inconclusive', [20.0, 22.0], '20-22 - Bombs are too close'),   # 範囲は行全体を文にする（AutoModder の作り）
        ('Suggestion', [30.0, 31.5, 40.0, 41.0], '30, 31.5, 40-41 - Mixed'),
        ('Info', [109.333], 'Maybe a dot'),
        ('Info', [0.4375, 50.0], '3 notes are stacked')], 'AutoModder の取り込み')
    got = automodder_import(F(t, ITEMS).split("\r\n"))
    t.eq([g[1] for g in got], [[12.5, 13.0], [20.0, 22.0], [30.0, 31.5, 40.0, 41.0], [109.333], [0.4375, 50.0]], '印なしでも拍は同じ')
    t.no_errors()


ROUNDTRIP = "\n".join([
    "Overall: fun map, a few readability issues",
    "",
    "Expert+",
    "SampleMapper",
    "",
    "40-48 the jumps could follow the kick",
    "        right now the rhythm feels flat",
    "52.5 - this double is cramped",
    "54 - same as previous",
    "60.333 - arc start is off",
    "70, 71.5, 73 (etc.) many repeats",
    "81-84 - the stream reads poorly",
    "        81.5 make this horizontal",
    "        82.25 move left one",
    "(S) [99.25 - 101, ...] alternate jumps",
    "157 - make this a tower?   ]",
    "157.5 - drop this tower?   ] both clash with the intro",
    "170 - 12 notes in a row",
    "",
    "Hard",
    "-----",
    "97 - move to the outer lane?",
    "88, 96, 104 - repeats",
    "",
    "One Saber Ex+",
    "42.5 - straighten this",
])


def test_roundtrip(t):
    '''読む→書き出す→読み直すと、項目（難易度・拍・範囲・文・続き・細かい指摘・まとめ・重さ・繰り返し）が同じになる'''
    r = _js(t, f"""
      const a = R.parseReviewText({jq(ROUNDTRIP)});
      const notes = a.notes.filter(n => n.kind === 'comment');
      const s = R.formatReviewText(a.items, {{ severity: false, notes }});
      const b = R.parseReviewText(s);
      const pick = it => [it.difficulty, it.mode, it.beats, it.ranges, it.text, it.cont, it.parent, it.group, it.groupText, it.repeats, it.sameAsPrev, it.prev];
      return {{ a: a.items.map(pick), b: b.items.map(pick), s, an: notes.map(n => n.text), bn: b.notes.filter(n => n.kind === 'comment').map(n => n.text) }};""")
    t.eq(len(r['a']), 15, '読んだ項目の数')
    t.eq(r['b'], r['a'], '読み直した項目')
    t.eq(r['bn'], r['an'], '全体への意見')
    # 重さの印を付けても同じ（印の無い項目は (N) になる）
    r2 = _js(t, f"""
      const a = R.parseReviewText({jq(ROUNDTRIP)});
      const b = R.parseReviewText(R.formatReviewText(a.items, {{ severity: true }}));
      return [a.items.map(it => it.severity || 'N'), b.items.map(it => it.severity), b.items.map(it => it.text)];""")
    t.eq(r2[1], r2[0], '重さ')
    t.no_errors()


def test_format_beat(t):
    '''拍の書き方: 小数3桁まで（4桁でちょうどなら4桁）・余計な0を付けない・読めない値は空'''
    r = _js(t, "return [109.33333333, 12, 12.5, 0.4375, 0.1 + 0.2, 1e-7, -1, NaN, 'x', 99999.5, 433.583].map(R.formatBeat);")
    t.eq(r, ['109.333', '12', '12.5', '0.4375', '0.3', '0', '', '', '', '', '433.583'], '拍')
    t.no_errors()

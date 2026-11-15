"""決まりの確かめ（ブラウザを使わない・1秒ほど。tools/run_tests.py --changed ではいつも回る）。
CLAUDE.md の「〜を足したら〜も足す」のうち機械で数えられる物と、2つの表が今のソースと合っているかを見る:
  tests/coverage_map.json  確かめる対象（ダイアログ・API・ショートカット・訳）→ それを確かめるテスト。理由があって足さない物の理由
  tests/select_map.json    変えたファイル → 回すテスト（tools/run_tests.py --changed）
落ちたら、メッセージの「直し方」のとおりに足りないテスト・表の行を足す。数えるのは「載っているか」だけで、
載っているテストが本当にその事を確かめているかは見ない（表を書く時に中身を読んで決める）。"""
import re

import rules_scan as R
import test_select as TS


EXCUSES = {"todo": "後回し（テストを足すとよい）", "manual": "自動では確かめられない（手で確かめる）", "noNeed": "要らない"}


def _check(t, title, problems, how, excused=()):
    """excused＝表に理由を書いて外している物 [(種類, 名前)]。数と名前を結果の補足に出す（todo は残りの不足として目に入るように）"""
    for kind, label in EXCUSES.items():
        names = [n for k, n in excused if k == kind]
        if names:
            t.info(f"{title}: {label} {len(names)}件（tests/coverage_map.json の {kind}）: " + "、".join(names))
    if problems:
        raise AssertionError(f"{title}: {len(problems)}件\n" + "\n".join(f"  - {p}" for p in problems) + f"\n直し方: {how}")


def _excuse(e, kind):
    """表の行 e が、kind（visual・english・test・hit・sheet）を理由付きで外していれば (todo/manual/noNeed, 理由)"""
    for k in EXCUSES:
        why = (e.get(k) or {}).get(kind)
        if why:
            return k, why
    return None


def test_shortcuts(t):
    '''ショートカット（ACTIONS）: キーの処理・早見表かメニューのキーの表示・ショートカット編集の訳がそろっている'''
    ids = R.actions()
    t.ok(len(ids) >= 30, f"ACTIONS を拾えた数が少なすぎます（{len(ids)}）。書き方が変わったら tests/rules/rules_scan.py を直す")
    cm = R.coverage_map()["shortcuts"]
    handled, sheet, mkeys = R.handled_action_ids(), R.cheat_sheet_ids(), R.menu_key_ids()
    ja, en = R.lang("ja"), R.lang("en")
    probs, excused = [], []
    for i in ids:
        e = cm.get(i, {})
        for kind, ok, msg in (("hit", i in handled, f"{i}: キーの処理（hit(e,'{i}')）が js/ のどこにも無い"),
                              ("sheet", i in sheet or i in mkeys, f"{i}: 早見表（editor-app.js の KEYS_*）にもメニューの data-key にも無い")):
            ex = _excuse(e, kind)
            if ok and ex:
                probs.append(f"tests/coverage_map.json の shortcuts の {i} の {kind} の理由は、もう要らない（表から消す）")
            elif not ok:
                if ex:
                    excused.append((ex[0], f"{i}（{kind}）"))
                else:
                    probs.append(msg)
        for name, d in (("ja", ja), ("en", en)):
            if f"act.{i}" not in d:
                probs.append(f"{i}: lang/{name}.json に act.{i}（ショートカット編集に出す操作名）が無い")
    probs += [f"早見表の {{{s}}} が ACTIONS に無い（打ち間違い？ 早見表にキーが出ない）" for s in sorted(sheet - set(ids))]
    probs += [f"tests/coverage_map.json の shortcuts の {k} は、もう ACTIONS に無い" for k in cm if k not in ids]
    _check(t, "ショートカット", probs,
           "ショートカットを足したら、キーの処理（hit）・早見表の行（{id}）・lang/ja.json と en.json の act.<id> を足す。"
           "早見表に出さない理由がある物は tests/coverage_map.json の shortcuts に noNeed で理由を書く", excused)


def test_dialogs(t):
    '''ダイアログ・パネル: 作る所ごとに、画面テストの一覧（visual）と英語の点検（english_ui）の対応が表にある'''
    sites = R.dialog_sites()
    t.ok(len(sites) >= 15, f"ダイアログを作る所を拾えた数が少なすぎます（{len(sites)}）。書き方が変わったら tests/rules/rules_scan.py を直す")
    cm = R.coverage_map()["dialogs"]
    screens, labels = R.screen_names(), R.english_labels()
    t.ok(len(screens) >= 30 and len(labels) >= 30, f"画面テストの名前（{len(screens)}）・英語の点検の名前（{len(labels)}）を拾えていません")
    probs, excused = [], []
    for k, where in sites.items():
        e = cm.get(k)
        if e is None:
            probs.append(f"表に無いダイアログ: {k}（{where}）")
            continue
        for kind, have, known, where_ in (("visual", e.get("visual", []), screens, "tests/visual/screens.py の Screen の名前"),
                                          ("english", e.get("english", []), labels, "英語の点検の scan(ed, \"…\") の名前")):
            for v in have:
                if v not in known:
                    probs.append(f"{k}: {kind} の「{v}」が {where_} に無い")
            ex = _excuse(e, kind)
            if have and ex:
                probs.append(f"{k}: {kind} があるのに理由（{ex[0]}）も書いてある（理由を消す）")
            elif not have:
                if ex:
                    excused.append((ex[0], f"{k.split('::', 1)[-1]}（{kind}）"))
                else:
                    probs.append(f"{k}: {'画面テスト' if kind == 'visual' else '英語の点検'}が無い")
    probs += [f"tests/coverage_map.json の dialogs の {k} は、もう無い（関数の名前・id を変えた？）" for k in cm if k not in sites]
    _check(t, "ダイアログ・パネル", probs,
           "新しいダイアログ・パネルを足したら、tests/visual/screens.py に Screen を、tests/e2e_misc/english_ui_helpers.py の tour に scan を足し、"
           "tests/coverage_map.json の dialogs に「作る所のキー: {visual:[画面の名前], english:[scan の名前]}」を書く。"
           "関数の名前を変えただけなら、表のキーを直す。要らない物は noNeed、後回しは todo に理由を書く", excused)


def test_api(t):
    '''serve.py の API: どれもテストがある（テストの中に名前が書いてあるか、表に確かめるテストがある）'''
    eps = R.api_endpoints()
    t.ok(len(eps) >= 30, f"API を拾えた数が少なすぎます（{len(eps)}）。書き方が変わったら tests/rules/rules_scan.py を直す")
    cm = R.coverage_map()["api"]
    text = R.tests_text()
    probs, excused = [], []
    for p, where in eps.items():
        named = p in text or f"'{p[1:]}" in text or f'"{p[1:]}' in text
        e = cm.get(p)
        if named:
            if e is not None:
                probs.append(f"tests/coverage_map.json の api の {p} は、もうテストに名前が書いてある（表から消す）")
            continue
        if e is None:
            probs.append(f"テストの無い API: {p}（{where}）")
        elif e.get("tests"):
            for s in e["tests"]:
                try:
                    TS.resolve(s)
                except ValueError as err:
                    probs.append(f"{p}: 表のテスト「{s}」が無い（{err}）")
        elif _excuse(e, "test"):
            excused.append((_excuse(e, "test")[0], p))
        else:
            probs.append(f"{p}: 表に tests も理由も無い")
    probs += [f"tests/coverage_map.json の api の {k} は、もう serve.py に無い" for k in cm if k not in eps]
    _check(t, "serve.py の API", probs,
           "API を足したら、tests/unit_py/ にテストを足す（名前を文字で書けば自動で見つかる）。画面越しにしか通らない物は、"
           "tests/coverage_map.json の api に {tests:[確かめるテスト]} を書く", excused)


def test_exe_bundle(t):
    '''exe の同梱（nlm.spec）: app.py から import でたどれるリポジトリの .py が、datas と hiddenimports の両方にある'''
    datas, hidden = R.spec_lists()
    mods = R.local_imports()
    t.ok(len(mods) >= 5 and datas and hidden, f"nlm.spec・import を拾えていません（部品 {len(mods)}）")
    probs = []
    for mod, path in sorted(mods.items()):
        rel = path.relative_to(R.ROOT).as_posix()
        if mod not in hidden:
            probs.append(f"{mod}（{rel}）が hiddenimports に無い")
        if not any(TS.path_match(d, rel) for d in datas):
            probs.append(f"{rel} が datas に無い")
    _check(t, "exe の同梱", probs, "新しい .py を足したら nlm.spec の datas と hiddenimports に足す（足さないと exe だけ起動に失敗する。CLAUDE.md「MEDIA ライブラリ」）")


def test_menu_acts(t):
    '''メニューバー: editor.html の項目（data-act）と runMenuAct の処理が1対1'''
    html, run = R.menu_acts_html(), R.menu_acts_run()
    t.ok(len(html) >= 15 and run, f"メニューの項目を拾えていません（{len(html)}）")
    probs = [f"メニューの項目 {a} が2つある" for a in sorted({a for a in html if html.count(a) > 1})]
    probs += [f"メニューの項目 {a} の処理が runMenuAct に無い（押しても何も起きない）" for a in sorted(set(html) - run)]
    probs += [f"runMenuAct の {a} がメニューに無い" for a in sorted(run - set(html))]
    _check(t, "メニューバー", probs, "メニューに項目を足したら runMenuAct に処理を足し、tests/e2e_misc/test_menus.py の ITEMS も直す")


def test_lang_keys(t):
    '''訳: JS・HTML に文字で書いたキーが ja.json と en.json の両方にあり、2つのファイルのキーがそろっている'''
    ja, en = R.lang("ja"), R.lang("en")
    used = R.i18n_keys()
    t.ok(len(used) >= 500, f"訳のキーを拾えた数が少なすぎます（{len(used)}）")
    cm = R.coverage_map()["lang"]
    probs = []
    for k, f in sorted(used.items()):
        for name, d in (("ja", ja), ("en", en)):
            if k not in d and k not in cm.get(f"{name}Missing", {}):
                probs.append(f"{k}（{f}）が lang/{name}.json に無い")
    probs += [f"{k} が ja.json にだけある" for k in sorted(set(ja) - set(en)) if k not in cm.get("jaOnly", {})]
    probs += [f"{k} が en.json にだけある" for k in sorted(set(en) - set(ja)) if k not in cm.get("enOnly", {})]
    for kind in ("jaOnly", "enOnly", "jaMissing", "enMissing"):
        d = {"jaOnly": set(ja) - set(en), "enOnly": set(en) - set(ja),
             "jaMissing": set(used) - set(ja), "enMissing": set(used) - set(en)}[kind]
        probs += [f"tests/coverage_map.json の lang.{kind} の {k} は、もう当てはまらない（表から消す）" for k in cm.get(kind, {}) if k not in d]
    _check(t, "訳のキー", probs, "新しい文言は日本語を直書きせず、lang/ja.json と lang/en.json の両方にキーを足す（CLAUDE.md「表示言語」）")


def test_runtime_methods(t):
    '''委譲の一覧（editor-runtime.js・save-system.js の methodNames）が、本体の rt に今もある'''
    rt = R.rt_assigned()
    probs = []
    for rel in ("js/runtime/editor-runtime.js", "js/project/save-system.js"):
        names = R.method_names(rel)
        t.ok(len(names) >= 10, f"{rel} の methodNames を拾えていません")
        probs += [f"{rel} の {n} が editor-app.js の rt に無い（消した関数が一覧に残っている）" for n in names if n not in rt]
    _check(t, "委譲の一覧", probs, "関数を消したら methodNames からも消す（CLAUDE.md「全体構成」）")


def _k_hits(group, word):
    if group == "visual":
        return any(word in f"test_layout_{n} test_image_{n}" for n in R.screen_names())
    return any(word in f"{f.name}::{n} {title}" for f in (R.TESTS / group).glob("test_*.py") for n, title in TS._test_defs(f))


def _spec_problems(spec, where):
    try:
        res = TS.resolve(spec)
    except ValueError as e:
        return [f"{where} の「{spec}」: {e}"]
    return [f"{where} の「{spec}」: -k の「{what[1]}」に当たるテストが無い"
            for g, what in res if what != "all" and what[0] == "k" and not _k_hits(g, what[1])]


def test_select_map(t):
    '''回すテストの選び方の表（tests/select_map.json）: 全部のファイルがどれかの決まりに当たり、決まりが今のファイル・テストを指している'''
    m = TS.load_map()
    files = TS.repo_files()
    probs = []
    for p in files:
        if TS.rules_for(p, m):
            continue
        parts = p.split("/")
        if parts[0] == "tests" and p.endswith(".py") and (
                (len(parts) == 3 and parts[2].startswith("test_")) or TS.tests_using(p)):
            continue   # テストのファイルと、テストが import する部品は表に書かなくても選ばれる
        probs.append(f"どの決まりにも当たらないファイル: {p}")
    for r in m["files"]:
        for pat in r["paths"]:
            if not any(TS.path_match(pat, f) for f in files):
                probs.append(f"files の paths「{pat}」に当たるファイルが無い（消した・名前を変えた？）")
        for s in r.get("run", []):
            probs += _spec_problems(s, f"files（{r['paths'][0]}）")
    app = R.read(TS.APP_JS)
    tops = TS.top_functions(app)
    for fr in m["functions"]:
        try:
            rx = re.compile(fr["match"])
        except re.error as e:
            probs.append(f"functions の「{fr['match']}」が正規表現として読めない: {e}")
            continue
        if not any(rx.search(n) for n in tops):
            probs.append(f"functions の「{fr['match']}」に当たる関数が {TS.APP_JS} に無い")
        for s in fr["run"]:
            probs += _spec_problems(s, f"functions（{fr['match']}）")
    hit = sum(any(re.search(fr["match"], n) for fr in m["functions"]) for n in tops)
    t.info(f"{TS.APP_JS} の関数・定数 {len(tops)} のうち、名前で選べる物 {hit}（残りは --changed が「表に無い関数」として名前を出す）")
    _check(t, "回すテストの選び方の表", probs,
           "新しいファイルを足したら、tests/select_map.json の files に、そのファイルを変えた時に回すテストを足す"
           "（テストの無い文書・道具は run を空にして note に理由）。決まりの指す物を消した・名前を変えたら表も直す")

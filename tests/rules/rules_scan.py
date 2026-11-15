"""決まりの確かめ（tests/rules/test_rules.py）が、ソースから確かめる対象を拾う部品。
JS・HTML は解析せず、今の書き方の決まり（正規表現）で拾う。書き方を変えて拾えなくなったら、ここを直す
（拾えない時は 0 件になり、test_rules.py の「拾えた数」の確かめで落ちる＝黙って通らない）。"""
import ast
import json
import re
import sys
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TESTS = ROOT / "tests"
sys.path.insert(0, str(ROOT / "tools"))
import test_select as TS   # noqa: E402

COVERAGE_MAP = TESTS / "coverage_map.json"
APP_JS = ROOT / "js" / "runtime" / "editor-app.js"


@lru_cache(None)
def read(rel):
    return (ROOT / rel).read_text(encoding="utf-8")


def coverage_map():
    return json.loads(COVERAGE_MAP.read_text(encoding="utf-8"))


def js_files():
    return sorted(p for p in (ROOT / "js").rglob("*.js") if "vendor" not in p.parts)


def _between(text, start, end):
    i = text.index(start)
    return text[i:text.index(end, i)]


def line_of(text, pos):
    return text.count("\n", 0, pos) + 1


# ---- ショートカット ----
def actions():
    """ACTIONS（再割当できるショートカット）の id"""
    return re.findall(r"\{id:'(\w+)'", _between(read("js/runtime/editor-app.js"), "const ACTIONS=[", "const ACT_BY_ID"))


def cheat_sheet_ids():
    """早見表（KEYS_COMMON〜KEYS_NODE）の操作に書いた {id}"""
    return set(re.findall(r"\{(\w+)\}", _between(read("js/runtime/editor-app.js"), "const KEYS_COMMON=[", "const ACTIONS=[")))


def handled_action_ids():
    """キーの処理で判定している id（hit(e,'id')・effBind('id')・ピの閉じ方の eq('id')）"""
    s = "".join(p.read_text(encoding="utf-8") for p in js_files())
    return set(re.findall(r"\b(?:hit|effBind|eq)\(\s*(?:\w+\s*,\s*)?'(\w+)'\s*\)", s))


def menu_key_ids():
    """メニューの項目の右に今のキーを出す data-key（syncMenu）"""
    return set(re.findall(r'data-key="(\w+)"', read("editor.html")))


# ---- メニュー ----
def menu_acts_html():
    return re.findall(r'data-act="(\w+)"', read("editor.html"))


def menu_acts_run():
    return set(re.findall(r"act==='(\w+)'", _between(read("js/runtime/editor-app.js"), "function runMenuAct", "\n}\n")))


# ---- 訳 ----
def lang(name):
    return json.loads(read(f"lang/{name}.json"))


def i18n_keys():
    """JS の t('キー', …)・tf('キー', …) と HTML の data-i18n* に、文字で書いたキー → 最初に見つけたファイル"""
    out = {}
    for p in js_files() + [ROOT / "editor.html"]:
        s = p.read_text(encoding="utf-8")
        rel = p.relative_to(ROOT).as_posix()
        for m in re.finditer(r"\btf?\(\s*'([^'\\{}$`]+)'\s*,", s):
            out.setdefault(m.group(1), rel)
        for m in re.finditer(r'data-i18n(?:-t|-ph)?="([^"${}]+)"', s):
            out.setdefault(m.group(1), rel)
    return out


# ---- ダイアログ・パネル ----
_SITE = re.compile(r"""\.id\s*=\s*['"](\w*(?:Dlg|Panel|Dialog))['"]|\bid=\\?["'](\w*(?:Dlg|Panel|Dialog))\\?["']""")
_SITE_QUAL = re.compile(r"""dataset\.(?:dlg|rv|ana)\s*=\s*['"](\w+)['"]""")
_SITE_CALL = re.compile(r"""\bdialog\(\s*'(\w+)'""")


def dialog_sites():
    """ダイアログ・パネルを作る所 {キー: 'ファイル:行'}。キーは「ファイル::関数::id[data-dlg 等]」（同じ部品で作る
    審査の指摘の画面は「ファイル::dialog('名前')」）。editor.html に初めからある物は「editor.html::#id」"""
    out = {}
    for p in js_files():
        rel = p.relative_to(ROOT).as_posix()
        text = p.read_text(encoding="utf-8")
        names = TS.enclosing_names(text)
        for i, ln in enumerate(text.splitlines()):
            for m in _SITE.finditer(ln):
                q = _SITE_QUAL.search(ln)
                out.setdefault(f"{rel}::{names[i]}::{m.group(1) or m.group(2)}" + (f"[{q.group(1)}]" if q else ""), f"{rel}:{i + 1}")
            for m in _SITE_CALL.finditer(ln):
                out.setdefault(f"{rel}::dialog('{m.group(1)}')", f"{rel}:{i + 1}")
    html = read("editor.html")
    for m in re.finditer(r'id="(\w*(?:Dlg|DlgBg|Panel|Dialog|Bg))"', html):
        out.setdefault(f"editor.html::#{m.group(1)}", f"editor.html:{line_of(html, m.start())}")
    return out


def screen_names():
    """画面テストの一覧（tests/visual/screens.py）の画面の名前"""
    return set(re.findall(r"\bScreen\(\s*'(\w+)'", read("tests/visual/screens.py")))


def english_labels():
    """英語の点検（tests/e2e_misc/english_ui_helpers.py の tour と、そこから呼ぶ部品）の区切りの名前 scan(ed, "…")。
    名前は文字で書いた物だけ拾う（変数で渡すと拾えない。f"…{x}" は {x} のまま）"""
    out = set()
    for p in TESTS.rglob("*.py"):
        if "__pycache__" in p.parts or p.parent.name == "rules":
            continue
        for m in re.finditer(r"""\bscan\(\s*ed\s*,\s*f?(["'])(.+?)\1""", p.read_text(encoding="utf-8")):
            out.add(m.group(2))
    return out


# ---- serve.py の API ----
def api_endpoints():
    """serve.py が受け付ける /__… の名前 {名前: 'serve.py:行'}（act == '…' で分ける窓口は、窓口の頭＋act）"""
    text = read("serve.py")
    out, prefix = {}, None
    for i, ln in enumerate(text.splitlines(), 1):
        if re.match(r"\s{4}def \w+\(self", ln):
            prefix = None
        m = re.search(r"len\('(/__[\w/]+/)'\)", ln)
        if m:
            prefix = m.group(1)
        if prefix:
            for a in re.findall(r"\bact == '(\w+)'", ln):
                out.setdefault(prefix + a, f"serve.py:{i}")
        for p in re.findall(r"self\.path(?:\.split\('\?', 1\)\[0\])? == '(/__[\w/]+)'", ln):
            out.setdefault(p, f"serve.py:{i}")
    return out


def tests_text():
    """テストのソース（rules 自身は除く）。API の名前を文字で書いているテストを探すのに使う"""
    return "\n".join(p.read_text(encoding="utf-8") for p in sorted(TESTS.rglob("*.py"))
                     if "__pycache__" not in p.parts and p.parent.name != "rules")


# ---- exe の同梱（nlm.spec） ----
def spec_lists():
    """nlm.spec の datas の1つ目（写す物）と hiddenimports（文字で書いた物だけ）"""
    tree = ast.parse(read("nlm.spec"))
    datas, hidden = [], []
    for node in ast.walk(tree):
        if isinstance(node, (ast.Assign, ast.AugAssign)) and isinstance(node.value, ast.List):
            tgt = node.targets[0] if isinstance(node, ast.Assign) else node.target
            if not isinstance(tgt, ast.Name):
                continue
            if tgt.id == "datas":
                datas += [e.elts[0].value for e in node.value.elts
                          if isinstance(e, ast.Tuple) and isinstance(e.elts[0], ast.Constant)]
            elif tgt.id == "hiddenimports":
                hidden += [e.value for e in node.value.elts if isinstance(e, ast.Constant)]
    return datas, hidden


def _local_module(name):
    """import の名前 → リポジトリの .py（無ければ None）"""
    parts = name.split(".")
    for cand in (ROOT.joinpath(*parts).with_suffix(".py"), ROOT.joinpath(*parts) / "__init__.py"):
        if cand.is_file():
            return cand
    return None


def local_imports(entry="app.py"):
    """exe の入口（app.py）から import をたどって届く、リポジトリの部品 {モジュール名: ファイル}（関数の中の import も数える）"""
    seen, todo = {}, [(entry[:-3], ROOT / entry)]
    while todo:
        mod, path = todo.pop()
        if mod in seen:
            continue
        seen[mod] = path
        pkg = mod.rsplit(".", 1)[0] if path.name == "__init__.py" or "." in mod else ""
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                base = node.module or ""
                if node.level:
                    base = ".".join(filter(None, [pkg, base]))
                names = [base] + [f"{base}.{a.name}" for a in node.names]
            for n in names:
                p = _local_module(n) if n else None
                if p:
                    todo.append((n, p))
    seen.pop(entry[:-3], None)
    return seen


# ---- 委譲の一覧（methodNames） ----
def method_names(rel):
    body = _between(read(rel), "static get methodNames()", "];")
    return re.findall(r"'([^']+)'", body)


def rt_assigned():
    return set(re.findall(r"\brt\.([A-Za-z_$][\w$]*)\s*=(?!=)", read("js/runtime/editor-app.js")))

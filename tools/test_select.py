"""変えたファイルから回すテストを選ぶ（tools/run_tests.py --changed）。選び方の表は tests/select_map.json（書き方は tests/README.md「回すテストの選び方」）。

選び方:
  - tests/<グループ>/test_*.py を変えた → そのファイル
  - tests/ の部品（*_helpers.py・_lib/*.py 等）を変えた → それを import しているテストのファイル（部品が部品を import していればたどる）
  - それ以外 → 表の files の paths に当たる決まりの run（当たる決まりが全部）
  - js/runtime/editor-app.js（1万行を超える本体）は、変えた行を含む関数の名前を表の functions の match（正規表現）と比べて選ぶ。
    どれにも当たらない関数は「表に無い関数」として名前を出す＝担当が中身を読んで選ぶ（表に足してもよい）
  - rules（決まりの確かめ・1秒ほど）はいつも回す

run の書き方（表の run と、run_tests.py に直接渡す名前で同じ）:
  "e2e_nle"                         グループ全部
  "e2e_nle/test_clip_link*.py"      グループの中のファイル（* が使える）
  "e2e/test_export.py::test_export_rich"   1つのテスト
  "visual -k analysis_ link_"       グループの中で、名前・題名にどれかの語を含むテスト（画面テストは画面の名前で選べる）
  "*"                               全部のグループ
"""
import ast
import fnmatch
import json
import re
import subprocess
from functools import lru_cache
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parent.parent
TESTS = ROOT / "tests"
SELECT_MAP = TESTS / "select_map.json"
APP_JS = "js/runtime/editor-app.js"
ALWAYS = ["rules"]   # いつも回すグループ（ソースを読むだけで速い）
NOT_GROUPS = {"golden", "fixtures"}


def git(*args):
    p = subprocess.run(["git", "-c", "core.quotepath=false", *args], cwd=ROOT, capture_output=True,
                       text=True, encoding="utf-8", errors="replace")
    if p.returncode:
        raise RuntimeError(f"git {' '.join(args)}: {p.stderr.strip()}")
    return p.stdout


def repo_files():
    """git で管理しているファイルと、まだ足していない（.gitignore に無い）ファイル。消したファイルは入れない"""
    out = git("ls-files", "-z", "--cached", "--others", "--exclude-standard")
    return sorted({p for p in out.split("\0") if p and (ROOT / p).is_file()})


def path_match(pat, path):
    return PurePosixPath(path).full_match(pat)


def load_map(path=SELECT_MAP):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def groups_all():
    return sorted(p.name for p in TESTS.iterdir()
                  if p.is_dir() and not p.name.startswith(("_", ".")) and p.name not in NOT_GROUPS and any(p.glob("test_*.py")))


# ---- 関数の名前（変えた行がどの関数の中か） ----
_DECL_ANY = re.compile(r"^\s*(?:export\s+)?(?:async\s+)?function\*?\s+([A-Za-z_$][\w$]*)")
_DECL_TOP = re.compile(r"^(?:export\s+)?(?:const|let|var|class)\s+([A-Za-z_$][\w$]*)")
_DECL_METHOD = re.compile(r"^ {2}(?:static\s+)?(?:async\s+)?(?!(?:if|for|while|switch|catch|return|function|else|do|try)\b)"
                          r"([A-Za-z_$][\w$]*)\s*\([^)]*\)\s*\{")


def enclosing_names(text):
    """行ごと（0番目＝1行目）に、その行を含む関数の名前。字下げで入れ子を見る（JS を解析しない近似。
    関数の宣言はどの深さでも・const/let/class は字下げ無しだけ・クラスのメソッドは字下げ2つ）。どれの中でもない行は '(top)'"""
    out, stack = [], []
    for line in text.splitlines():
        s = line.strip()
        if not s:
            out.append(stack[-1][1] if stack else "(top)")
            continue
        ind = len(line) - len(line.lstrip())
        closing = s.startswith(("}", ")", "]"))
        while stack and (ind < stack[-1][0] or (ind == stack[-1][0] and not closing)):
            stack.pop()
        m = _DECL_ANY.match(line) or _DECL_TOP.match(line) or _DECL_METHOD.match(line)
        if m:
            stack.append((ind, m.group(1)))
        out.append(stack[-1][1] if stack else "(top)")
        if closing and not m and stack and ind == stack[-1][0]:
            stack.pop()
    return out


def top_functions(text):
    """字下げ無しで宣言された関数・定数の名前（表の functions が古くなっていないかの確かめに使う）"""
    names = []
    for line in text.splitlines():
        m = re.match(r"^(?:async\s+)?function\*?\s+([A-Za-z_$][\w$]*)", line) or _DECL_TOP.match(line)
        if m:
            names.append(m.group(1))
    return names


# ---- run の名前 ----
def _test_defs(f):
    """ファイルに書いてある test_ の関数 [(名前, docstring の1行目)]"""
    try:
        tree = ast.parse(f.read_text(encoding="utf-8"))
    except Exception:
        return []
    out = []
    for n in tree.body:
        if isinstance(n, ast.FunctionDef) and n.name.startswith("test_"):
            doc = (ast.get_docstring(n) or "").strip().splitlines()
            out.append((n.name, doc[0] if doc else n.name))
    return out


def resolve(spec):
    """run の名前1つ → [(グループ, 'all' / ('only', 'file' か 'file::name') / ('k', 語))]。名前が今のテストに無ければ ValueError"""
    spec = spec.strip()
    if spec == "*":
        return [(g, "all") for g in groups_all()]
    if " -k " in spec:
        g, words = spec.split(" -k ", 1)
        g = g.strip()
        if not (TESTS / g).is_dir():
            raise ValueError(f"グループが無い: {spec}")
        ws = words.split()
        if not ws:
            raise ValueError(f"-k の後に語が無い: {spec}")
        return [(g, ("k", w)) for w in ws]
    if "/" not in spec:
        if not (TESTS / spec).is_dir() or not any((TESTS / spec).glob("test_*.py")):
            raise ValueError(f"グループが無い: {spec}")
        return [(spec, "all")]
    g, rest = spec.split("/", 1)
    pat, _, name = rest.partition("::")
    files = sorted(f for f in (TESTS / g).glob("test_*.py") if fnmatch.fnmatch(f.name, pat)) if (TESTS / g).is_dir() else []
    if not files:
        raise ValueError(f"テストのファイルが無い: {spec}")
    if name:
        if len(files) != 1 or name not in [n for n, _ in _test_defs(files[0])]:
            raise ValueError(f"テストが無い: {spec}")
        return [(g, ("only", f"{files[0].name}::{name}"))]
    return [(g, ("only", f.name)) for f in files]


def selection(specs):
    """run の名前の並び → {グループ: {'all': bool, 'only': set, 'k': set}}（全部の和）"""
    sel = {}
    for spec in specs:
        for g, what in resolve(spec):
            s = sel.setdefault(g, {"all": False, "only": set(), "k": set()})
            if what == "all":
                s["all"] = True
            else:
                s[what[0]].add(what[1])
    for s in sel.values():
        if s["all"]:
            s["only"], s["k"] = set(), set()
    return sel


def k_to_only(group, words):
    """-k の語を、そのグループのテスト（ファイル名::関数名と題名に語を含む物）の名前に直す。
    まとめ役（test_zz_）のあるグループ（visual。読み込んだ時にテストを作る）は直せないので None＝-k のまま渡す"""
    out = set()
    for f in sorted((TESTS / group).glob("test_*.py")):
        defs = _test_defs(f)
        if any(n.startswith("test_zz_") for n, _ in defs):
            return None
        for n, title in defs:
            if any(w in f"{f.name}::{n} {title}" for w in words):
                out.add(f"{f.name}::{n}")
    return out


# ---- 変えたファイル ----
def merge_base(base):
    return "HEAD" if base in (None, "HEAD") else git("merge-base", base, "HEAD").strip()


def changed_files(base=None):
    """base（既定 HEAD）から今の作業フォルダまでに変わったファイル（追加・変更・削除・まだ足していないファイル）"""
    mb = merge_base(base)
    out = set(p for p in git("diff", "--name-only", "--no-renames", "-z", mb).split("\0") if p)
    out |= set(p for p in git("ls-files", "--others", "--exclude-standard", "-z").split("\0") if p)
    return sorted(out)


def changed_lines(path, base=None):
    """そのファイルの今の版で変わった行の番号（1始まり）。消しただけの所は、その前後の行。新しいファイルは全部"""
    if git("ls-files", "--", path).strip() == "":
        n = len((ROOT / path).read_text(encoding="utf-8").splitlines()) if (ROOT / path).is_file() else 0
        return set(range(1, n + 1))
    lines = set()
    for m in re.finditer(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@", git("diff", "-U0", "--no-renames", merge_base(base), "--", path), re.M):
        c, d = int(m.group(1)), int(m.group(2) or 1)
        lines |= {c, c + 1} if d == 0 else set(range(c, c + d))
    return lines


def changed_functions(path=APP_JS, base=None):
    p = ROOT / path
    if not p.is_file():
        return []
    names = enclosing_names(p.read_text(encoding="utf-8"))
    return sorted({names[i - 1] for i in changed_lines(path, base) if 0 < i <= len(names)})


# ---- tests/ の部品を使うテスト ----
@lru_cache(None)
def _tests_py():
    return tuple((f, f.read_text(encoding="utf-8")) for f in sorted(TESTS.rglob("*.py")) if "__pycache__" not in f.parts)


def _importers(mod):
    pat = re.compile(rf"^\s*(?:from\s+{re.escape(mod)}\s+import\b|import\s+(?:[\w.]+\s*,\s*)*{re.escape(mod)}\b)", re.M)
    return [f for f, text in _tests_py() if pat.search(text)]


def tests_using(helper):
    """tests/ の部品（.py）を import しているテストのファイル（部品の部品もたどる）→ run の名前"""
    seen, todo, out = set(), [Path(helper).stem], set()
    while todo:
        mod = todo.pop()
        if mod in seen:
            continue
        seen.add(mod)
        for f in _importers(mod):
            rel = f.relative_to(TESTS).as_posix()
            if f.name.startswith("test_") and "/" in rel:
                out.add(rel)
            else:
                todo.append(f.stem)
    return sorted(out)


# ---- 選ぶ ----
def rules_for(path, m):
    return [r for r in m["files"] if any(path_match(p, path) for p in r["paths"])]


def select(changed, base=None, m=None):
    """変えたファイル → (選んだ [(run の名前, 理由)], 表に無いファイル, 表に無い関数)"""
    m = m or load_map()
    picks, unknown_files, unknown_funcs = [], [], []

    def add(specs, why):
        for s in specs:
            picks.append((s, why))

    for path in changed:
        parts = path.split("/")
        if parts[0] == "tests" and len(parts) == 3 and parts[2].startswith("test_") and parts[2].endswith(".py"):
            if (ROOT / path).is_file():
                add([f"{parts[1]}/{parts[2]}"], path)
            continue
        if parts[0] == "tests" and path.endswith(".py") and not rules_for(path, m):
            users = tests_using(path)
            if users:
                add(users, f"{path} を使うテスト")
                continue
        rules = rules_for(path, m)
        if not rules:
            unknown_files.append(path)
            continue
        for r in rules:
            add(r.get("run", []), f"{path}（{r.get('note', '')}）" if r.get("note") else path)
            if r.get("byFunction"):
                for fn in changed_functions(path, base):
                    hits = [fr for fr in m["functions"] if re.search(fr["match"], fn)]
                    if not hits:
                        unknown_funcs.append(fn)
                    for fr in hits:
                        add(fr["run"], f"{path} の {fn}（{fr.get('note', '')}）")
    add(ALWAYS, "いつも")
    return picks, unknown_files, sorted(set(unknown_funcs))

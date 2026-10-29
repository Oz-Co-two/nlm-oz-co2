"""公開した版の訳のうち、今の同梱の文と違う物の表（lang/history/released.json）を作る・確かめる（2026-10-28）。

exe 版は初回の起動で lang/*.json を exe の隣へ写し（app.py の _seed）、serve.py はその後ずっと、同梱の訳の上に exe の隣の訳を
キー単位で重ねて返す。自動更新は lang/ を入れ替えないので、そのままでは「同じキーのまま直した文」が今の利用者に届かない。
そこで、公開した版（git のタグ v*-oz と、原作 0.8 beta）の訳のうち今の文と違う物をこの表に入れて同梱し、exe の隣の文が
表の文（＝昔の同梱の文そのまま）なら serve.py は使わない。利用者が自分で書き換えた文は表に無いので、今までどおり優先する。

使い方:  python tools/lang_history.py           表を作り直す（訳の文を直したら、公開の前に実行してコミットする）
         python tools/lang_history.py --check   表が公開した版の文を全部含むか確かめる（足りなければ一覧を出して 1 で終わる）
make_release.py はビルド結果の表（_internal/lang/history/released.json）を同じ方法で確かめ、足りなければ止まる。
"""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FILES = ("ja.json", "en.json")
TABLE = Path("history") / "released.json"   # lang/ の中（_seed は lang/ の直下の .json だけを写す＝exe の隣へは写らない）
# 原作（helba さんの Non-Linear Mapper 0.8 beta）の訳。原作の配布フォルダへ Oz-Co2版を上書きした人の exe の隣にある
ORIGINAL = ("b4a4c2e18fdda6b71fec5b6e02a6d8fbcf4e4d99", "NLM-source (1)/Non-Linear Mapper 0.8 beta (source)/lang/")


def _git(root, *args):
    r = subprocess.run(["git", *args], cwd=root, capture_output=True)
    if r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)}: {r.stderr.decode('utf-8', 'replace').strip()}")
    return r.stdout


def released_refs(root=ROOT):
    """[(名前, git の参照, lang/ のパス)]: 原作と、公開した版のタグ（古い順）"""
    tags = _git(root, "tag", "--list", "v*-oz", "--sort=creatordate").decode().split()
    return [("0.8 beta", ORIGINAL[0], ORIGINAL[1])] + [(t, t, "lang/") for t in tags]


def _load_ref(root, ref, path):
    try:
        d = json.loads(_git(root, "show", f"{ref}:{path}").decode("utf-8-sig"))
    except (RuntimeError, ValueError):
        return {}
    return {k: v for k, v in d.items() if isinstance(k, str) and isinstance(v, str)} if isinstance(d, dict) else {}


def _load_cur(lang_dir):
    return {f: json.loads((Path(lang_dir) / f).read_text(encoding="utf-8-sig")) for f in FILES}


def collect(root=ROOT, lang_dir=None):
    """表の中身: {ファイル: {キー: [公開した版にあった、今と違う文…]}}（今の同梱に無いキーは入れない＝使われないため）"""
    cur = _load_cur(lang_dir or Path(root) / "lang")
    out = {f: {} for f in FILES}
    for _, ref, path in released_refs(root):
        for f in FILES:
            for k, v in _load_ref(root, ref, path + f).items():
                if k in cur[f] and v != cur[f][k] and v not in out[f].setdefault(k, []):
                    out[f][k].append(v)
    return {f: {k: vs for k, vs in sorted(m.items()) if vs} for f, m in out.items()}


def missing(root=ROOT, lang_dir=None):
    """表（lang_dir/history/released.json）に無い「公開した版の、今と違う文」の一覧 [(版, ファイル, キー)]"""
    lang_dir = Path(lang_dir or Path(root) / "lang")
    try:
        table = json.loads((lang_dir / TABLE).read_text(encoding="utf-8")).get("files", {})
    except (OSError, ValueError):
        table = {}
    cur = _load_cur(lang_dir)
    out = []
    for name, ref, path in released_refs(root):
        for f in FILES:
            for k, v in _load_ref(root, ref, path + f).items():
                if k in cur[f] and v != cur[f][k] and v not in table.get(f, {}).get(k, []):
                    out.append((name, f, k))
    return out


def write(root=ROOT):
    files = collect(root)
    data = {"v": 1, "note": "公開した版の訳のうち、今の同梱の文と違う物。exe の隣の訳がこの文なら serve.py は使わない（tools/lang_history.py が作る）",
            "files": files}
    p = Path(root) / "lang" / TABLE
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return p, sum(len(m) for m in files.values())


def main():
    if "--check" in sys.argv[1:]:
        miss = missing()
        if miss:
            print("lang/history/released.json に無い、公開した版の文があります（python tools/lang_history.py で作り直す）:")
            for name, f, k in miss[:30]:
                print(f"  {name} {f} {k}")
            if len(miss) > 30:
                print(f"  …ほか {len(miss) - 30} 件")
            sys.exit(1)
        print("OK: 公開した版の文は全部、表に入っています")
        return
    p, n = write()
    print(f"作りました: {p.relative_to(ROOT)}（{n} キー）")


if __name__ == "__main__":
    main()

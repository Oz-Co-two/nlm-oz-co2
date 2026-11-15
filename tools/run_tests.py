"""NLMのテストを全部まとめて回す入口（詳しくは tests/README.md）。

  .venv-build/Scripts/python.exe tools/run_tests.py              全グループ
  .venv-build/Scripts/python.exe tools/run_tests.py e2e unit_js  グループを指定
  .venv-build/Scripts/python.exe tools/run_tests.py e2e_nle/test_clip_link*.py e2e/test_export.py::test_export_rich
                                                                 ファイル・1つのテストを指定（グループと混ぜてよい）
  .venv-build/Scripts/python.exe tools/run_tests.py --changed    変えたファイルから回すテストを選んで回す（表は tests/select_map.json）
  オプション: -k 名前の一部（絞り込み・複数可）/ --update-golden（書き出しの正解を今の結果で更新）
              --coverage（JSのうちテストで実際に動いた割合を測る。test-out/coverage/report.txt）
              --accept（画面の基準画像を今の画面で更新）/ -v（1件ずつ表示）/ -j 同時に動かすプロセスの数（既定10）
              --no-split（グループを分けずに流す。テスト同士の影響を疑う時の切り分け用）
              --changed [基準]（既定 HEAD＝まだコミットしていない変更。ブランチの作業は --changed master＝分かれた所から）
              --dry-run（--changed で選んだテストと理由を見せるだけで回さない）

グループ（tests/ 直下のフォルダ）は別プロセス・別のEdgeで並列に動く。大きいグループは、前回の各テストの所要時間
（test-out/test_secs.json）を元に、ファイル単位（長いファイルはテスト単位）で同じくらいの長さに分けて同時に流し、
長いものから先に始める（全体の時間は一番最後に終わるプロセスで決まるため）。-k で絞った時は分けない。画面には要約だけを出し、
失敗の詳細は test-out/last.txt、全結果は test-out/summary.json に書く。
失敗・エラーがあった回は、その記録を test-out/history/<日時>/ にも残す（last.txt は次の実行で上書きされるため。新しい順に30回分）。
終了コード: 0=失敗なし（要確認はあってもよい）/ 1=失敗あり
"""
import argparse
import ast
import concurrent.futures as cf
import math
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

if sys.platform == "win32":
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8")
        except Exception:
            pass

ROOT = Path(__file__).resolve().parent.parent
TESTS = ROOT / "tests"
OUT = ROOT / "test-out"
VENV_PY = ROOT / ".venv-build" / "Scripts" / "python.exe"
MARK = {"pass": "OK", "fail": "失敗", "error": "エラー", "skip": "飛ばし", "review": "要確認"}
HIST = OUT / "history"
KEEP_HISTORY = 30
TEST_SECS = OUT / "test_secs.json"   # テストごとの前回の所要時間（「グループ/ファイル::関数名」→秒）。分け方と流す順に使う
DEFAULT_SECS = 3.0   # 記録の無いテストの見込み（秒）
BOOT_SECS = 3.0      # 1つのプロセスで Edge を起動して最初のページを開くまでの見込み（秒）


def _reexec_with_venv_py():
    if VENV_PY.exists() and Path(sys.executable).resolve() != VENV_PY.resolve():
        os.execv(str(VENV_PY), [str(VENV_PY), __file__, *sys.argv[1:]])


sys.path.insert(0, str(ROOT / "tools"))
import test_select as TS   # noqa: E402  回すテストの名前の読み方・変えたファイルからの選び方

groups_all = TS.groups_all


def _load_secs():
    try:
        return json.loads(TEST_SECS.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_test_secs(allres, full):
    """各テストの所要時間を覚える。全部を回した回（full）は作り直す＝消したテストの記録が残らない"""
    secs = {} if full else _load_secs()
    secs.update({f"{r['group']}/{r['file']}::{r['name']}": r["secs"] for r in allres if r["name"].startswith("test_")})
    TEST_SECS.write_text(json.dumps(secs, ensure_ascii=False, indent=0, sort_keys=True), encoding="utf-8")


def _test_names(f):
    """ファイルに書いてある test_ の関数名（書いた順）。visual のように読み込んだ時に作るテストは入らない"""
    try:
        tree = ast.parse(f.read_text(encoding="utf-8"))
    except Exception:
        return []
    return [n.name for n in tree.body if isinstance(n, ast.FunctionDef) and n.name.startswith("test_")]


def _files(group, secs, only=None):
    """グループのファイルごとの [(見込み秒, ファイル名, テスト単位に分けられるなら [(見込み秒, 関数名)…] / 分けられないなら None, 一部だけか)]。
    まとめ役（test_zz_）のあるファイルと、読み込んだ時にテストを作るファイルは、1つのプロセスで全部を回す必要があるので分けない。
    only＝回すテスト（「ファイル名」か「ファイル名::関数名」の集まり。None＝全部）"""
    out = []
    for f in sorted((TESTS / group).glob("test_*.py")):
        names = _test_names(f)
        pick = None   # このファイルの一部のテストだけを回す時の関数名
        if only is not None and f.name not in only:
            pick = [n for n in names if f"{f.name}::{n}" in only]
            if not pick:
                continue
        rec = {k.split("::", 1)[1]: v for k, v in secs.items() if k.startswith(f"{group}/{f.name}::")}
        tests = [(rec.get(n, DEFAULT_SECS), n) for n in (pick or names)]
        if pick:
            out.append((sum(s for s, _ in tests), f.name, tests, True))
            continue
        dynamic = any(n not in names for n in rec)
        est = sum(rec.values()) if dynamic else sum(s for s, _ in tests)
        out.append((est or DEFAULT_SECS, f.name, None if dynamic or any(n.startswith("test_zz_") for n in names) else tests, False))
    return out


def _units(fs, target):
    """1プロセスに入れる単位 [(見込み秒, --only に渡す名前)]（目安 target より長いファイルと、一部だけ回すファイルはテスト単位）"""
    units = []
    for e, name, tests, part in fs:
        if tests and (part or e > target):
            units += [(s, f"{name}::{n}") for s, n in tests]
        else:
            units.append((e, name))
    return units


def _split(files, target, restricted=()):
    """1プロセスの長さの目安 target より長いグループを分ける（目安より長いファイルはテスト単位に分ける）。
    restricted＝一部のテストだけを回すグループ（分けない時も --only で回す物を渡す）"""
    jobs = []
    for g, fs in files.items():
        units = _units(fs, target)
        est = sum(e for e, _ in units)
        k = max(1, min(len(units), math.ceil(est / target)))
        if k == 1:
            jobs.append((g, None, [u for _, u in units] if g in restricted else None, est))
            continue
        bins = [[0.0, []] for _ in range(k)]
        for e, u in sorted(units, key=lambda x: -x[0]):   # 長いものから、今いちばん短い組へ入れる
            b = min(bins, key=lambda b: b[0])
            b[0] += e
            b[1].append(u)
        jobs += [(g, i, b[1], b[0]) for i, b in enumerate(bins)]
    return jobs


def _makespan(jobs, j):
    """j 個の枠へ長い順に流した時に全部が終わるまでの見込み（秒）"""
    ends = [0.0] * max(1, j)
    for e in sorted((x[3] + BOOT_SECS for x in jobs), reverse=True):
        i = ends.index(min(ends))
        ends[i] += e
    return max(ends)


def plan(groups, j, split, only=None):
    """流すプロセスの一覧 [(グループ, 番号 / 分けない時は None, --only に渡す名前 / 全部の時は None, 見込み秒)] を、見込みの長い順に返す。
    1プロセスの長さの目安を、分けられない一番長い所から1秒ずつ変えて分け方を作り、j 個の枠で一番早く終わるもの
    （同じならプロセスの少ないもの＝起動する Edge が少なくCPUが楽）を選ぶ。only＝{グループ: 回すテストの名前の集まり}（無いグループは全部）"""
    only = only or {}
    secs = _load_secs()
    files = {g: _files(g, secs, only.get(g)) for g in groups}
    files = {g: fs for g, fs in files.items() if fs}
    restricted = set(only)
    whole = [(g, None, [u for _, u in _units(fs, math.inf)] if g in restricted else None, sum(e for e, *_ in fs))
             for g, fs in files.items()]
    best = (_makespan(whole, j) // 1, len(whole)), whole
    if split and whole:
        floor = max([e for fs in files.values() for e, _, t, _ in fs if t is None]
                    + [s for fs in files.values() for _, _, t, _ in fs if t for s, _ in t] + [1])
        for target in range(math.ceil(floor), math.ceil(max(e for *_, e in whole)) + 1):
            jobs = _split(files, target, restricted)
            key = (_makespan(jobs, j) // 1, len(jobs))
            if key < best[0]:
                best = key, jobs
    return sorted(best[1], key=lambda x: -x[3])


def run_one(job, a):
    group, part, only, _ = job
    tag = group if part is None else f"{group}.{part}"
    js = OUT / f"_{tag}.json"
    js.unlink(missing_ok=True)
    cmd = [sys.executable, str(TESTS / "_lib" / "nlmtest.py"), "--group", group, "--json", str(js)]
    if part is not None:
        cmd += ["--part", str(part)]
    if only:
        cmd += ["--only", *only]
    for ks in (a.k or []) + ([sorted(a.k_by_group[group])] if a.k_by_group.get(group) else []):
        cmd += ["-k", *ks]
    if a.update_golden:
        cmd.append("--update-golden")
    if a.accept:
        cmd.append("--accept")
    if a.coverage:
        cmd.append("--coverage")
    t0 = time.time()
    p = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace")
    secs = time.time() - t0
    try:
        res = json.loads(js.read_text(encoding="utf-8"))
    except Exception:
        res = [dict(group=group, file="-", name="(実行)", title=f"グループの実行に失敗（{tag}）", status="error",
                    msg=(p.stderr or p.stdout or "")[-2500:], secs=secs)]
    if a.verbose and p.stdout.strip():
        print(p.stdout.rstrip())
    return group, res, secs


def save_history(groups):
    """失敗・エラーのあった回の記録を test-out/history/<日時>/ に写す。まれにしか起きない失敗は、
    次の実行で last.txt が上書きされると手がかりが消えるため（tests/README.md「たまに出るエラーの記録」）。新しい順に KEEP_HISTORY 回分"""
    d = HIST / time.strftime("%Y%m%d_%H%M%S")
    d.mkdir(parents=True, exist_ok=True)
    for f in ("last.txt", "summary.json"):
        shutil.copyfile(OUT / f, d / f)
    (d / "command.txt").write_text(" ".join(["tools/run_tests.py", *sys.argv[1:]]) + "\n", encoding="utf-8")
    err = OUT / "visual" / "errors"   # 画面テストの準備・撮影で例外が出た時の状況（tests/visual/vislib.py）。今回 visual を回した時だけ
    if "visual" in groups and err.is_dir() and any(err.iterdir()):
        shutil.copytree(err, d / "visual_errors")
    for old in sorted(p for p in HIST.iterdir() if p.is_dir())[:-KEEP_HISTORY]:
        shutil.rmtree(old, ignore_errors=True)
    return d


def changed_report(base):
    """--changed: 変えたファイルから回すテストを選び、選んだ理由と、表に無いファイル・関数を見せる。回す名前の並びを返す"""
    changed = TS.changed_files(base)
    picks, unknown_files, unknown_funcs = TS.select(changed, base)
    print(f"変えたファイル（{'まだコミットしていない変更' if base == 'HEAD' else base + ' から分かれた所から'}）: {len(changed)}")
    for p in changed:
        print(f"  {p}")
    why = {}
    for spec, reason in picks:
        why.setdefault(spec, []).append(reason)
    print(f"回すテスト: {len(why)}（表は tests/select_map.json）")
    for spec, rs in why.items():
        rs = list(dict.fromkeys(rs))
        print(f"  {spec}  ← " + "・".join(rs[:3]) + (f" ほか{len(rs) - 3}" if len(rs) > 3 else ""))
    if unknown_files:
        print("表に無いファイル（tests/select_map.json の files に足してください。足すまで、このファイルのテストは選ばれません）:")
        for p in unknown_files:
            print(f"  {p}")
    if unknown_funcs:
        print(f"表に無い {TS.APP_JS} の関数（中身を読んで回すテストを足す。よく使う物は表の functions に足す）:")
        print("  " + ", ".join(unknown_funcs))
    return list(why)


def main():
    _reexec_with_venv_py()
    ap = argparse.ArgumentParser()
    ap.add_argument("groups", nargs="*")
    ap.add_argument("-k", action="append", nargs="+")
    ap.add_argument("--update-golden", action="store_true")
    ap.add_argument("--accept", action="store_true")
    ap.add_argument("-v", "--verbose", action="store_true")
    # 10: 全部で約1分半・CPUは平均7割ほど。8なら約1分45秒・平均5割台。描画を抑えない（NLM_TEST_FPS=0）まま増やすとCPUが張り付いて逆に遅くなる（2026-10-11に測定）
    ap.add_argument("-j", type=int, default=10)
    ap.add_argument("--coverage", action="store_true", help="JSのうちテストで実際に動いた割合も測る")
    ap.add_argument("--no-split", action="store_true", help="グループを分けずに流す")
    ap.add_argument("--changed", nargs="?", const="HEAD", metavar="基準",
                    help="変えたファイルから回すテストを選ぶ（既定 HEAD。ブランチの作業は master 等＝分かれた所から）")
    ap.add_argument("--dry-run", action="store_true", help="--changed で選んだテストを見せるだけで回さない")
    a = ap.parse_args()
    if a.changed:
        if a.groups:
            print("--changed とグループ・テストの名前は一緒に使えません")
            return 2
        specs = changed_report(a.changed)
        if a.dry_run:
            return 0
    else:
        specs = a.groups or groups_all()
    try:
        sel = TS.selection(specs)
    except ValueError as e:
        print("知らないテストの名前:", e, "／グループ:", ", ".join(groups_all()))
        return 2
    groups = [g for g in groups_all() if g in sel] + sorted(g for g in sel if g not in groups_all())
    only, a.k_by_group = {}, {}
    for g in groups:   # 一部だけ回すグループ: 回すテストの名前の集まり（-k の語はテストの名前に直す。直せない visual は -k のまま渡す）
        s = sel[g]
        if s["all"]:
            continue
        names = set(s["only"])
        if s["k"]:
            hit = TS.k_to_only(g, s["k"])
            if hit is None:
                a.k_by_group[g] = s["k"]
                if names:   # ファイル指定と -k が両方ある visual は全部（1つのファイルしか無い）
                    del a.k_by_group[g]
                continue
            names |= hit
        only[g] = names
    OUT.mkdir(exist_ok=True)
    if a.coverage:
        import shutil
        shutil.rmtree(OUT / "coverage", ignore_errors=True)
    for p in OUT.glob("_*.json"):   # 前回の各プロセスの結果（分け方が変わると名前が変わるので残さない）
        p.unlink(missing_ok=True)
    jobs = plan(groups, a.j, split=not a.k and not a.no_split, only=only)
    groups = [g for g in groups if any(job[0] == g for job in jobs)]   # 選んだテストが1件も無いグループ（-k が当たらない等）は出さない
    t0 = time.time()
    done = {g: ([], 0.0, 0) for g in groups}   # グループ → (結果, 一番長かったプロセスの秒, プロセスの数)
    with cf.ThreadPoolExecutor(max_workers=max(1, a.j)) as ex:
        for g, res, secs in ex.map(lambda job: run_one(job, a), jobs):
            r0, s0, n0 = done[g]
            done[g] = (r0 + res, max(s0, secs), n0 + 1)
    order = {(g, f.name, n): i for g in groups for f in (TESTS / g).glob("test_*.py") for i, n in enumerate(_test_names(f))}
    for g in groups:   # 分けて流したグループの結果を、ファイル・書いた順に並べ直す
        res, secs, n = done[g]
        if n > 1:
            done[g] = (sorted(res, key=lambda r: (r["file"], order.get((g, r["file"], r["name"]), math.inf))), secs, n)
    if not a.coverage:   # カバレッジの計測をした回の時間は普段より長いので覚えない
        save_test_secs([r for res, _, _ in done.values() for r in res], full=not a.k and not a.groups and not a.changed)

    allres, lines, detail = [], [], []
    for g in groups:
        res, secs, nproc = done[g]
        allres += res
        n = len(res)
        c = {s: sum(r["status"] == s for r in res) for s in MARK}
        tail = "・".join(f"{MARK[s]}{c[s]}" for s in ("fail", "error", "review", "skip") if c[s])
        lines.append(f"{g:<10} {c['pass']}/{n - c['skip']} OK" + (f"  {tail}" if tail else "")
                     + f"  ({secs:.0f}秒" + (f"・{nproc}つに分けて同時に" if nproc > 1 else "") + ")")
        for r in res:
            if r["status"] in ("fail", "error", "review"):
                head = f"  {'✗' if r['status'] in ('fail', 'error') else '?'} {g}/{r['file']}::{r['name']}  {r['title']}"
                first = (r["msg"] or "").strip().splitlines()[:1]
                lines.append(head + (f"\n      {first[0][:160]}" if first else "") + (f"\n      → {r['path']}" if r.get("path") else ""))
            if r["status"] != "pass" or r.get("info"):
                detail.append(f"[{MARK[r['status']]}] {g}/{r['file']}::{r['name']}  {r['title']}  ({r['secs']}秒)\n"
                              + "".join(f"    {ln}\n" for ln in (r["msg"] or "").splitlines())
                              + "".join(f"    ※{i}\n" for i in r.get("info") or [])
                              + (f"    → {r['path']}\n" if r.get("path") else ""))
    nf = sum(r["status"] in ("fail", "error") for r in allres)
    nr = sum(r["status"] == "review" for r in allres)
    lines.append(f"合計 {len(allres)}件: " + (f"失敗{nf}" if nf else "失敗なし") + (f"・要確認{nr}" if nr else "")
                 + f"  ({time.time() - t0:.0f}秒)" + ("  詳細: test-out/last.txt" if detail else ""))
    if a.coverage:
        sys.path.insert(0, str(TESTS / "_lib"))
        import jscov
        lines.append(jscov.merge_report(sorted((OUT / "coverage").glob("*.json")), OUT / "coverage" / "report.txt")
                     + "  詳細: test-out/coverage/report.txt")
    print("\n".join(lines))
    (OUT / "last.txt").write_text("\n".join(lines) + "\n\n" + "\n".join(detail), encoding="utf-8")
    (OUT / "summary.json").write_text(json.dumps(allres, ensure_ascii=False, indent=1), encoding="utf-8")
    if nf:
        print(f"失敗の記録を残しました: {save_history(groups).relative_to(ROOT).as_posix()}/")
    return 1 if nf else 0


if __name__ == "__main__":
    sys.exit(main())

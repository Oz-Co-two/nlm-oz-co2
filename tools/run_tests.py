"""NLMのテストを全部まとめて回す入口（詳しくは tests/README.md）。

  .venv-build/Scripts/python.exe tools/run_tests.py              全グループ
  .venv-build/Scripts/python.exe tools/run_tests.py e2e unit_js  グループを指定
  オプション: -k 名前の一部（絞り込み・複数可）/ --update-golden（書き出しの正解を今の結果で更新）
              --coverage（JSのうちテストで実際に動いた割合を測る。test-out/coverage/report.txt）
              --accept（画面の基準画像を今の画面で更新）/ -v（1件ずつ表示）/ -j 同時に動かすグループ数（既定4）

グループ（tests/ 直下のフォルダ）は別プロセスで並列に動く。画面には要約だけを出し、
失敗の詳細は test-out/last.txt、全結果は test-out/summary.json に書く。
終了コード: 0=失敗なし（要確認はあってもよい）/ 1=失敗あり
"""
import argparse
import concurrent.futures as cf
import json
import os
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
NOT_GROUPS = {"golden", "fixtures"}
MARK = {"pass": "OK", "fail": "失敗", "error": "エラー", "skip": "飛ばし", "review": "要確認"}


def _reexec_with_venv_py():
    if VENV_PY.exists() and Path(sys.executable).resolve() != VENV_PY.resolve():
        os.execv(str(VENV_PY), [str(VENV_PY), __file__, *sys.argv[1:]])


def groups_all():
    return sorted(p.name for p in TESTS.iterdir()
                  if p.is_dir() and not p.name.startswith(("_", ".")) and p.name not in NOT_GROUPS and any(p.glob("test_*.py")))


def run_one(group, a):
    js = OUT / f"_{group}.json"
    js.unlink(missing_ok=True)
    cmd = [sys.executable, str(TESTS / "_lib" / "nlmtest.py"), "--group", group, "--json", str(js)]
    for ks in a.k or []:
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
        res = [dict(group=group, file="-", name="(実行)", title="グループの実行に失敗", status="error",
                    msg=(p.stderr or p.stdout or "")[-2500:], secs=secs)]
    if a.verbose and p.stdout.strip():
        print(p.stdout.rstrip())
    return group, res, secs


def main():
    _reexec_with_venv_py()
    ap = argparse.ArgumentParser()
    ap.add_argument("groups", nargs="*")
    ap.add_argument("-k", action="append", nargs="+")
    ap.add_argument("--update-golden", action="store_true")
    ap.add_argument("--accept", action="store_true")
    ap.add_argument("-v", "--verbose", action="store_true")
    ap.add_argument("-j", type=int, default=4)
    ap.add_argument("--coverage", action="store_true", help="JSのうちテストで実際に動いた割合も測る")
    a = ap.parse_args()
    groups = a.groups or groups_all()
    unknown = [g for g in groups if not (TESTS / g).is_dir()]
    if unknown:
        print("知らないグループ:", ", ".join(unknown), "／ある:", ", ".join(groups_all()))
        return 2
    OUT.mkdir(exist_ok=True)
    if a.coverage:
        import shutil
        shutil.rmtree(OUT / "coverage", ignore_errors=True)
    t0 = time.time()
    done = {}
    with cf.ThreadPoolExecutor(max_workers=max(1, a.j)) as ex:
        for g, res, secs in ex.map(lambda g: run_one(g, a), groups):
            done[g] = (res, secs)

    allres, lines, detail = [], [], []
    for g in groups:
        res, secs = done[g]
        allres += res
        n = len(res)
        c = {s: sum(r["status"] == s for r in res) for s in MARK}
        tail = "・".join(f"{MARK[s]}{c[s]}" for s in ("fail", "error", "review", "skip") if c[s])
        lines.append(f"{g:<10} {c['pass']}/{n - c['skip']} OK" + (f"  {tail}" if tail else "") + f"  ({secs:.0f}秒)")
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
    return 1 if nf else 0


if __name__ == "__main__":
    sys.exit(main())

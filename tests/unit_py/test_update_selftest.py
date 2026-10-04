"""app_update.py の自己テスト（tools/update_test.py）を実行して結果を確かめるラッパー"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_update_selftest(t):
    '''tools/update_test.py（偽の配布元で通しの更新テスト）が終了コード0で終わる'''
    r = subprocess.run([sys.executable, str(ROOT / "tools" / "update_test.py")], cwd=ROOT, capture_output=True,
                       timeout=300, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    out = (r.stdout or b"").decode("utf-8", "replace")
    ng = [ln for ln in out.splitlines() if ln.startswith("  NG")]
    t.info(f"チェック {out.count('  ok   ')}件OK / NG {len(ng)}件")
    t.ok(r.returncode == 0, "終了コード%d。NG: %s\n%s" % (r.returncode, ng[:5], (r.stderr or b"").decode("utf-8", "replace")[-800:]))

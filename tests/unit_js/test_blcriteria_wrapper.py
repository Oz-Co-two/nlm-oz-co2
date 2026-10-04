"""NLM版BL評価リスト（js/mapcheck/blcriteria.js）は tools/blcriteria_test.py が自己テストを持つので、それを実行して結果だけ確認する。"""
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_blcriteria_selftest(t):
    '''tools/blcriteria_test.py（基準の違反を1つずつ仕込む自己テスト）が終了コード0で終わる'''
    t0 = time.time()
    p = subprocess.run([sys.executable, str(ROOT / "tools" / "blcriteria_test.py")], cwd=ROOT,
                       capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=240)
    secs = time.time() - t0
    t.info(f"blcriteria_test.py の所要時間: {secs:.1f}秒")
    out = (p.stdout + p.stderr).strip()
    t.eq(p.returncode, 0, "blcriteria_test.py の終了コード\n" + out[-1500:])
    t.ok("OK" in out, "OK の表示が出ている: " + out[-300:])

"""テストがまれに落ちる時の、原因の切り分け用の実験（経緯と結果は tests/README.md「たまに出るエラーの記録」）。

  .venv-build/Scripts/python.exe tools/test_diag.py reload [回数]   開き直した直後に、まだ古いページのまま次へ進むことがあるか
  .venv-build/Scripts/python.exe tools/test_diag.py files [組数]    書いた直後の画像の読み書きで、ファイルのロック（ウイルス対策ソフト等）が起きるか
  .venv-build/Scripts/python.exe tools/test_diag.py burst           ローカルサーバーへ同時にたくさん接続した時に、拒否されるか

どれもアプリの設定・テストの基準画像には触れない（files は test-out/_diag_files を作って最後に消す）。
2026-10-04 の結果: reload 0/50・files 0/12000・burst はブラウザから 0/400
（Python から一斉に60〜120本つなぐと、回によって14〜37本が拒否・切断された＝列があふれること自体は起きる）。
"""
import shutil
import sys
import threading
import time
import urllib.request
from pathlib import Path

if sys.platform == "win32":
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8")
        except Exception:
            pass

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tests" / "visual"))


def _until(ed, expr, n=60):
    for _ in range(n):
        if ed.js(expr):
            return True
        ed.wait(0.25)
    return False


def reload_race(n):
    """古いページに目印 window.__old を置いて開き直し、直後に目印が見えたら「古いページのまま戻った」。
    続けて0.4秒かかる JS を実行し、途中でページが入れ替わって CDP のエラーになるかも数える。
    未保存の変更なし／あり（画面テスト「曲データの読込」と同じ手順で確認画面まで進める）の2通り"""
    from cdp import Editor, CdpError
    import screens as S
    with Editor(ready=True) as ed:
        ed.reload()
        for mode in ("未保存なし", "未保存あり"):
            stale = errs = 0
            msgs = []
            for i in range(n):
                ed.reload()
                if mode == "未保存あり":
                    ed.js(S.AUDIO_ONLY_JS)
                    ed.js(S.bulk_load_start_js())
                    _until(ed, "!!document.getElementById('dirtyDlg')")
                ed.js("window.__old=1;true")
                ed.reload()
                try:
                    if ed.js("window.__old===1"):
                        stale += 1
                    ed.js("new Promise(r=>setTimeout(()=>r(1),400))")
                except CdpError as e:
                    errs += 1
                    msgs.append(f"#{i}: {e}"[:200])
            print(f"{mode}: 古いページのまま戻った {stale}/{n}・CDPのエラー {errs}/{n}", flush=True)
            for m in msgs[:5]:
                print("   ", m, flush=True)


def file_locks(n):
    """画面テストと同じ書き方（PNGを書く→すぐ読む・コピー・上書き）を n 組。例外の種類ごとに数える"""
    src = next((ROOT / "tests" / "visual" / "baseline").glob("*.png"), None) or next((ROOT / "docs").rglob("*.png"))
    data = src.read_bytes()
    d = ROOT / "test-out" / "_diag_files"
    errs = {}
    t0 = time.time()
    try:
        for _ in range(max(1, n // 100)):
            shutil.rmtree(d, ignore_errors=True)
            d.mkdir(parents=True, exist_ok=True)
            for i in range(100):
                a, b = d / f"shot_{i}.png", d / f"cur_{i}.png"
                for what, fn in (("書く", lambda: a.write_bytes(data)), ("読む", a.read_bytes),
                                 ("コピー", lambda: shutil.copyfile(a, b)), ("上書き", lambda: a.write_bytes(data))):
                    try:
                        fn()
                    except Exception as e:
                        k = f"{what}: {type(e).__name__}: {e}"[:160]
                        errs[k] = errs.get(k, 0) + 1
    finally:
        shutil.rmtree(d, ignore_errors=True)
    print(f"{max(1, n // 100) * 100}組（{len(data) // 1024}KB の PNG）を {time.time() - t0:.1f}秒で処理: エラー {sum(errs.values())}件", flush=True)
    for k, v in errs.items():
        print(f"  {v}回  {k}", flush=True)


def burst():
    """serve.py（ThreadingHTTPServer・受付待ちの列 request_queue_size=5）へ同時に要求する。
    ブラウザは1つの相手へ同時6接続までに抑えるので、列があふれるのは Python 等から一斉に接続した時だけのはず"""
    from cdp import Editor
    with Editor(ready=True) as ed:
        ed.reload()
        for n in (50, 200, 400):
            r = ed.js(f"""(async()=>{{ const rs=await Promise.allSettled(Array.from({{length:{n}}},(_, i)=>
                fetch('tools/fixtures/basic.wav?b='+i+'_'+Math.random(),{{cache:'no-store'}}).then(r=>{{ if(!r.ok) throw new Error('HTTP '+r.status); return r.arrayBuffer(); }})));
              const bad=rs.filter(x=>x.status==='rejected'); return {{bad:bad.length,why:[...new Set(bad.map(x=>String(x.reason)))].slice(0,3)}}; }})()""")
            print(f"ブラウザから同時 {n} 件: 失敗 {r['bad']} 件 {r['why']}", flush=True)
        for m in (20, 60, 120):
            res = {"ok": 0, "ng": {}}
            lock, go = threading.Lock(), threading.Event()

            def worker():
                go.wait()
                try:
                    urllib.request.urlopen(f"http://127.0.0.1:{ed.port}/tools/fixtures/basic.wav", timeout=20).read()
                    with lock:
                        res["ok"] += 1
                except Exception as e:
                    k = f"{type(e).__name__}: {e}"[:120]
                    with lock:
                        res["ng"][k] = res["ng"].get(k, 0) + 1
            th = [threading.Thread(target=worker) for _ in range(m)]
            for x in th:
                x.start()
            go.set()
            for x in th:
                x.join()
            print(f"Python から同時 {m} 接続: 成功 {res['ok']}・失敗 {sum(res['ng'].values())} {res['ng']}", flush=True)


def main(argv):
    if not argv or argv[0] not in ("reload", "files", "burst"):
        print(__doc__)
        return 2
    n = int(argv[1]) if len(argv) > 1 else None
    {"reload": lambda: reload_race(n or 25), "files": lambda: file_locks(n or 12000), "burst": burst}[argv[0]]()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

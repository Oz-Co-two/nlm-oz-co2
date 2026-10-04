"""NLMのテストの共通部品（標準ライブラリだけ。pytest等は使わない）。

テストの書き方（tests/<グループ>/test_*.py）:
    def test_place_undo(t):
        '''ノーツを置いてUndoすると消える'''          # 1行目が結果一覧に出る名前
        ed = t.fresh('basic')                          # ページを開き直してテスト素材を読む
        t.eq(ed.js("window._dbgApp.state().counts.notes"), 8, 'ノーツ数')
        t.no_errors()                                  # ページ内で例外が出ていない

t（Ctx）でできること:
    t.ed / t.fresh(fixture)   共有のヘッドレスEdge（グループ内で1つ。fresh で初期状態に戻す。settle=読込後の待ち秒）
    t.eq(実際, 期待, 説明) / t.ok(条件, 説明) / t.no_errors()   確認（外れたら失敗）
    t.golden(名前, 文字列)    tests/golden/<名前> と比べる（--update-golden で書き換え）
    t.review(説明, パス)      失敗ではないが人の確認が要る（画面の変化など）
    t.skip(理由) / t.info(文)  飛ばす / 結果に補足を出す
    t.out                     このグループの出力フォルダ（test-out/<グループ>/）
    t.update_golden / t.accept  実行時のオプション

名前が test_zz_ で始まるテストは「まとめ役」: -k で絞り込んでも、同じファイルのテストが1件でも動いたら最後に動く
（画面の比較のまとめ画像づくりなど。行番号で並ぶので、ファイルの最後に置く）。

グループごとに別プロセスで動く（tools/run_tests.py が並列に起動する）。単体で動かす時:
    .venv-build/Scripts/python.exe tests/_lib/nlmtest.py --group e2e [-k 名前の一部]
"""
import argparse
import difflib
import importlib.util
import json
import sys
import time
import traceback
from pathlib import Path

if sys.platform == "win32":
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8")
        except Exception:
            pass

ROOT = Path(__file__).resolve().parents[2]
TESTS = ROOT / "tests"
GOLDEN = TESTS / "golden"
OUT = ROOT / "test-out"
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))


class Skip(Exception):
    pass


class Review(Exception):
    def __init__(self, msg, path=None):
        super().__init__(msg)
        self.path = path


# 3Dビューの描画を省き、位置の計算に要る行列の更新だけ行う（t.fresh() のたびに入れる）。
# GPUの無いヘッドレスでは描画がソフトウェアでCPUを使い切り、グループを並列に回すと全体が数倍遅くなっていた。
# テストは絵ではなく状態と画面座標（cellScreen 等＝カメラの行列）を見るので、行列さえ更新すれば足りる。画面の比較（visual）は撮影時に3Dビューを隠している
LIGHT_RENDER_JS = """(()=>{ const r=window._dbg&&window._dbg.rt&&window._dbg.rt.renderer;
  if(r&&!r.__testLight){ r.__testLight=true; r.render=(s,c)=>{ if(s&&s.matrixWorldAutoUpdate!==false) s.updateMatrixWorld();
    if(c&&!c.parent) c.updateMatrixWorld(); }; }
  return true; })()"""

# ページ内エラーのうち、テスト環境（ヘッドレス・音声デバイス無し等）特有で無視してよいもの。足す時は理由を書く
BENIGN_ERRORS = [
]


class Ctx:
    def __init__(self, group, opts):
        self.group = group
        self.opts = opts
        self.update_golden = opts.update_golden
        self.accept = opts.accept
        self.out = OUT / group
        self.out.mkdir(parents=True, exist_ok=True)
        self._ed = None
        self._infos = []
        self.cov = None
        if getattr(opts, "coverage", False):   # tools/run_tests.py --coverage
            import jscov
            self.cov = jscov.Collector()

    # ---- エディタ ----
    @property
    def ed(self):
        if self._ed is None:
            from cdp import Editor
            self._ed = Editor(ready=True)
            self._ed.start()
            if self.cov:   # 記録を始めてから開き直す（読み込み時に動くコードも数える）
                self.cov.start(self._ed)
                self._ed.reload()
        return self._ed

    def fresh(self, fixture=None, settle=0.3):
        """ページを開き直し（未保存の確認は自動承諾・localStorageも消す）、fixture があれば読み込む"""
        ed = self.ed
        if self.cov:
            self.cov.take(ed)   # 開き直すと記録が消えるので先に取り出す
        # 環境設定(bsnm_*)は一時のデータフォルダの config/settings.json にミラーされ、開き直すと読み戻される＝
        # localStorage を消すだけでは前のテストの設定が漏れる。消して初期値（settings.default.json）から始める
        try:
            (Path(ed.data_dir) / "config" / "settings.json").unlink(missing_ok=True)
        except Exception:
            pass
        try:
            ed.reload()
        except Exception:
            self.restart()   # ブラウザが固まった/落ちた時は起動し直す
            ed = self.ed
            ed.reload()
        ed.js(LIGHT_RENDER_JS)
        if fixture:
            ed.load_fixture(fixture, settle=settle)   # 読込の処理は完了を待ってから戻る＝固定の待ちは短くてよい（画面の比較は長めに渡す）
        return ed

    def restart(self):
        if self._ed and self.cov:
            self.cov.take(self._ed)
        if self._ed:
            try:
                self._ed.close()
            except Exception:
                pass
        self._ed = None

    def close(self):
        self.restart()
        if self.cov:
            self.cov.save(OUT / "coverage" / f"{self.group}.json")

    # ---- 確認 ----
    def eq(self, actual, expected, label=""):
        if actual != expected:
            a = json.dumps(actual, ensure_ascii=False, sort_keys=True, default=str)
            e = json.dumps(expected, ensure_ascii=False, sort_keys=True, default=str)
            if len(a) + len(e) > 300:
                diff = "\n".join(difflib.unified_diff(
                    json.dumps(expected, ensure_ascii=False, sort_keys=True, indent=1, default=str).splitlines(),
                    json.dumps(actual, ensure_ascii=False, sort_keys=True, indent=1, default=str).splitlines(),
                    "期待", "実際", lineterm="", n=1))
                raise AssertionError(f"{label}: 期待と違います\n" + _clip(diff))
            raise AssertionError(f"{label}: 実際 {a} / 期待 {e}")

    def ok(self, cond, label=""):
        if not cond:
            raise AssertionError(label or "条件を満たしません")

    def no_errors(self, ed=None):
        """ページ内の例外・console.error が無いこと（BENIGN_ERRORS は除く）"""
        ed = ed or self._ed
        if ed is None:
            return
        errs = [e for e in ed.errors() if not any(p in e for p in BENIGN_ERRORS)]
        if errs:
            raise AssertionError("ページ内エラー:\n  " + "\n  ".join(_clip(e, 400) for e in errs[:5]))

    def golden(self, name, text):
        """tests/golden/<name> と一字一句比べる。--update-golden の時は書き換えて成功扱い"""
        p = GOLDEN / name
        if self.update_golden or not p.exists():
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(text, encoding="utf-8", newline="\n")
            self.info(f"正解ファイルを{'更新' if self.update_golden else '新規作成'}: tests/golden/{name}")
            return
        want = p.read_text(encoding="utf-8")
        if want != text:
            (self.out / ("actual_" + name.replace("/", "_"))).write_text(text, encoding="utf-8", newline="\n")
            diff = "\n".join(difflib.unified_diff(want.splitlines(), text.splitlines(), "正解", "今回", lineterm="", n=1))
            raise AssertionError(f"tests/golden/{name} と違います（意図した変更なら --update-golden）\n" + _clip(diff))

    def review(self, msg, path=None):
        raise Review(msg, path)

    def skip(self, msg):
        raise Skip(msg)

    def info(self, msg):
        self._infos.append(str(msg))


def _clip(s, n=2500):
    s = str(s)
    return s if len(s) <= n else s[:n] + f"\n…（以下 {len(s) - n} 文字省略）"


def _load(path):
    spec = importlib.util.spec_from_file_location(f"nlmtest_{path.parent.name}_{path.stem}", path)
    mod = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(path.parent))
    spec.loader.exec_module(mod)
    return mod


def run_group(group, opts):
    files = sorted((TESTS / group).glob("test_*.py"))
    ctx = Ctx(group, opts)
    results = []
    try:
        for f in files:
            try:
                mod = _load(f)
            except Exception:
                results.append(dict(group=group, file=f.name, name="(読み込み)", title=f.name, status="error",
                                    msg=_clip(traceback.format_exc(limit=3)), secs=0))
                continue
            tests = [(n, fn) for n, fn in vars(mod).items() if n.startswith("test_") and callable(fn)]
            tests.sort(key=lambda x: x[1].__code__.co_firstlineno)
            ran = 0
            for name, fn in tests:
                title = ((fn.__doc__ or "").strip().splitlines() or [name])[0]
                summary = name.startswith("test_zz_")   # まとめ役: -k で絞っても、同じファイルで1件でも動いたら最後に動く
                if opts.k and not any(k in f"{f.name}::{name} {title}" for k in opts.k):
                    if not (summary and ran):
                        continue
                ran += 1
                ctx._infos = []
                t0 = time.time()
                status, msg, path = "pass", "", None
                try:
                    fn(ctx)
                except Skip as e:
                    status, msg = "skip", str(e)
                except Review as e:
                    status, msg, path = "review", str(e), e.path
                except AssertionError as e:
                    status, msg = "fail", _clip(str(e) or traceback.format_exc(limit=2))
                except Exception:
                    status, msg = "error", _clip(traceback.format_exc(limit=4))
                r = dict(group=group, file=f.name, name=name, title=title, status=status, msg=msg,
                         secs=round(time.time() - t0, 2), info=list(ctx._infos))
                if path:
                    r["path"] = str(path)
                results.append(r)
                if opts.verbose:
                    print(f"[{status}] {group}/{f.name}::{name} {title} {msg[:200]}", flush=True)
    finally:
        ctx.close()
    return results


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--group", required=True)
    ap.add_argument("-k", action="append", nargs="+", help="名前の一部で絞り込み（複数可）")
    ap.add_argument("--update-golden", action="store_true")
    ap.add_argument("--accept", action="store_true")
    ap.add_argument("--json", help="結果をJSONで書き出す先")
    ap.add_argument("-v", "--verbose", action="store_true")
    ap.add_argument("--coverage", action="store_true", help="JSのカバレッジを test-out/coverage/ に記録")
    opts = ap.parse_args(argv)
    opts.k = [k for ks in opts.k for k in ks] if opts.k else None
    res = run_group(opts.group, opts)
    if opts.json:
        Path(opts.json).write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    else:
        for r in res:
            print(f"[{r['status']}] {r['file']}::{r['name']} {r['title']}" + (f"\n    {r['msg']}" if r["msg"] else ""))
    return 1 if any(r["status"] in ("fail", "error") for r in res) else 0


if __name__ == "__main__":
    sys.exit(main())

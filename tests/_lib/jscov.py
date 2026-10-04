"""JSのカバレッジ（テスト中に実際に動いたコードの割合）を集める。tools/run_tests.py --coverage の時だけ使う。

Edge（V8）の precise coverage（ブロック単位）を CDP で取る。ページを開き直すとそれまでの記録が消えるので、
開き直す直前・終了時に取り出して合算する。位置は V8 の数え方（UTF-16 の単位）のまま扱う。

結果は2つの数字で見る:
  関数: 1回でも呼ばれた関数の割合
  ブロック: 実行された範囲の文字数の割合（if の片側だけ通った、なども数える。空白・コメントも含むので目安）
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TARGET = ("/js/", "/preview-v4/")   # 集計する（プロジェクトの）スクリプト


def _local(url):
    """http://127.0.0.1:port/js/a.js → プロジェクト内の相対パス（対象外なら None）"""
    if "://" not in url:
        return None
    path = "/" + url.split("://", 1)[1].split("/", 1)[-1].split("?", 1)[0]
    if not any(path.startswith(t) for t in TARGET) or path.startswith("/js/vendor/"):
        return None   # 外部のライブラリ（three.js 等）は数えない
    return path.lstrip("/")


class Collector:
    def __init__(self):
        self.cov = {}     # パス → bytearray（UTF-16の1単位ごとに 1=実行された）
        self.funcs = {}   # パス → {(開始, 終了): [名前, 実行された]}

    def start(self, ed):
        ed.call("Profiler.enable")
        ed.call("Profiler.startPreciseCoverage", callCount=True, detailed=True)

    def take(self, ed):
        try:
            res = ed.call("Profiler.takePreciseCoverage")["result"]
        except Exception:
            return
        for s in res:
            rel = _local(s.get("url", ""))
            if not rel:
                continue
            ranges = [r for f in s["functions"] for r in f["ranges"]]
            if not ranges:
                continue
            n = max(r["endOffset"] for r in ranges)
            arr = self.cov.get(rel)
            if arr is None or len(arr) < n:
                arr = (arr or bytearray()) + bytearray(n - len(arr or b""))
                self.cov[rel] = arr
            # 外側→内側の順に塗る（内側の範囲が外側の回数を上書きする＝V8のブロックカバレッジの読み方）
            tmp = bytearray(n)
            for r in sorted(ranges, key=lambda r: (r["startOffset"], -r["endOffset"])):
                a, b = r["startOffset"], r["endOffset"]
                tmp[a:b] = (b"\x01" if r["count"] > 0 else b"\x00") * (b - a)
            tmp += bytearray(len(arr) - n)
            arr[:] = (int.from_bytes(arr, "big") | int.from_bytes(tmp, "big")).to_bytes(len(arr), "big")   # 合算（OR）を一度に
            fs = self.funcs.setdefault(rel, {})
            for f in s["functions"]:
                r0 = f["ranges"][0]
                key = (r0["startOffset"], r0["endOffset"])
                if not f.get("functionName") and r0["startOffset"] == 0:
                    continue   # スクリプト全体（モジュールの最上位）は関数に数えない
                e = fs.setdefault(key, [f.get("functionName") or "(無名)", False])
                e[1] = e[1] or r0["count"] > 0

    def save(self, path):
        out = {}
        for rel, arr in self.cov.items():
            iv, i, n = [], 0, len(arr)
            while i < n:   # 実行された範囲を [開始, 終了) の並びに縮める
                if arr[i]:
                    j = i
                    while j < n and arr[j]:
                        j += 1
                    iv.append([i, j])
                    i = j
                else:
                    i += 1
            out[rel] = {"covered": iv, "funcs": [[a, b, nm, ok] for (a, b), (nm, ok) in self.funcs.get(rel, {}).items()]}
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(json.dumps(out), encoding="utf-8")


def merge_report(paths, out_txt, top=25):
    """グループごとの結果を合算して、ファイルごとの割合と「動いていない大きい関数」を書く。要約の行を返す"""
    cov, funcs = {}, {}
    for p in paths:
        try:
            d = json.loads(Path(p).read_text(encoding="utf-8"))
        except Exception:
            continue
        for rel, v in d.items():
            cov.setdefault(rel, []).extend(v["covered"])
            fs = funcs.setdefault(rel, {})
            for a, b, nm, ok in v["funcs"]:
                e = fs.setdefault((a, b), [nm, False])
                e[1] = e[1] or ok
    rows, detail = [], []
    tot_u = tot_c = tot_f = tot_fc = 0
    for rel in sorted(cov):
        # 改行を変換せずに読む（V8 の位置は CRLF の CR も1単位として数える。変換すると位置がずれる）
        src = (ROOT / rel).read_text(encoding="utf-8", errors="replace", newline="") if (ROOT / rel).exists() else ""
        units = len(src.encode("utf-16-le")) // 2
        if not units:
            continue
        mark = bytearray(units)
        for a, b in cov[rel]:
            mark[a:min(b, units)] = b"\x01" * max(0, min(b, units) - a)
        c = sum(mark)
        fs = funcs.get(rel, {})
        nf, nfc = len(fs), sum(1 for v in fs.values() if v[1])
        tot_u += units; tot_c += c; tot_f += nf; tot_fc += nfc
        rows.append((rel, nfc, nf, c / units * 100))
        # 動いていない関数（大きい順。入れ子の内側は外側に含まれるので、外側が動いていない時は外側だけ出す）
        dead = sorted(((a, b, v[0]) for (a, b), v in fs.items() if not v[1]), key=lambda x: (x[0], -x[1]))
        tops, last_end = [], -1
        for a, b, nm in dead:
            if a >= last_end:
                tops.append((b - a, a, nm)); last_end = b
        if tops:
            u16 = src.encode("utf-16-le")
            line_of = lambda off: u16[:off * 2].decode("utf-16-le", errors="replace").count("\n") + 1
            detail.append(f"■ {rel}（動いていない関数 {nf - nfc}個のうち大きいもの）")
            for size, a, nm in sorted(tops, reverse=True)[:top]:
                detail.append(f"   {size:7d}文字  {line_of(a):5d}行目  {nm}")
    lines = [f"{'ファイル':<38} {'関数':>13} {'ブロック':>7}"]
    for rel, nfc, nf, pct in sorted(rows, key=lambda r: -r[2]):
        lines.append(f"{rel:<38} {nfc:5d}/{nf:<5d}{(nfc / nf * 100 if nf else 100):4.0f}% {pct:6.1f}%")
    summary = (f"JS全体: 関数 {tot_fc}/{tot_f}（{tot_fc / max(1, tot_f) * 100:.0f}%）・"
               f"ブロック {tot_c / max(1, tot_u) * 100:.1f}%")
    Path(out_txt).write_text(summary + "\n\n" + "\n".join(lines) + "\n\n" + "\n".join(detail) + "\n", encoding="utf-8")
    return summary

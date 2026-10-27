"""審査の指摘の .txt（js/review/review-txt.js の decodeReviewBytes・parseReviewText）を、手元の実物でまとめて読んで確かめる。

  .venv-build/Scripts/python.exe tools/review_txt_check.py <フォルダか .txt> [...] [--names <tsv>] [--labels AT=ExpertPlus,IN=Expert]
                                                          [--default Expert] [--items] [--out <ファイル>]

- 1件ずつ「行・項目・拍の無い行の数・難易度ごとの数・見出し・警告」と、拍の無い行の一覧、読み落としの疑い（数で始まるのに
  拍の無い行になった・範囲か区切りか決めきれない・文が数で始まる・文が空 等）を出す。--items で項目の一覧も出す。
- --names: 保存名と元のファイル名の対応（TSV。見出しの行に「元のファイル名」か original の列があればその列、無ければ2列目）。
  実物を別の名前で保存している時に、ファイル名から難易度を読む所も確かめるため。
- 実物は他人の文章なので、結果はリポジトリの外へ出す（標準出力か --out。--out がリポジトリの中なら止める）。
  実物そのものもリポジトリに入れない（テストの見本は tests/unit_js/test_review_txt.py に作り物で置く）。
"""
import argparse
import base64
import csv
import sys
from collections import Counter
from pathlib import Path

if sys.platform == "win32":
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8")
        except Exception:
            pass

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

JS = r"""
(async () => {
  const R = await import('/js/review/review-txt.js');
  const bin = atob(%(b64)s), u8 = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) u8[i] = bin.charCodeAt(i);
  let text;
  try { text = R.decodeReviewBytes(u8); } catch (e) { return { error: e.code || e.message }; }
  const r = R.parseReviewText(text, %(opts)s);
  r.lineCount = text.split(/\r\n|\r|\n/).length;
  return r;
})()
"""


def load_names(path):
    """保存名 → 元のファイル名"""
    out = {}
    rows = [r for r in csv.reader(Path(path).read_text(encoding="utf-8-sig").splitlines(), delimiter="\t") if r and not r[0].startswith("#")]
    col = 1
    if rows:
        head = [c.strip().lower() for c in rows[0]]
        for k, name in enumerate(head):
            if name in ("元のファイル名", "original", "original name"):
                col = k
                rows = rows[1:]
                break
    for r in rows:
        if len(r) > col and r[0].strip() and r[col].strip():
            out[r[0].strip()] = r[col].strip()
    return out


def parse_labels(s):
    out = {}
    for part in (s or "").split(","):
        if "=" in part:
            k, v = part.split("=", 1)
            out[k.strip()] = v.strip()
    return out


def suspects(r):
    """読み落としの疑い（目で確かめる所）"""
    out = []
    for n in r["notes"]:
        t = n["text"]
        if n["kind"] in ("comment", "unreadable") and t[:1].isdigit():
            out.append((n["line"], "数で始まるのに拍の無い行", t))
        elif n["kind"] == "comment" and n["hints"] and len(t) < 60:
            out.append((n["line"], "拍の無い行に数（候補）", t))
    for it in r["items"]:
        if it["ambiguous"]:
            out.append((it["line"], "範囲と読んだ（区切りかも）", it["raw"].strip()))
        low = it["text"].lower()
        if (it["text"][:1].isdigit() or low.startswith(("to ", "thru ", "and ", "& "))) and not low.startswith("to ."):   # 「to .562」はタイミングの直し
            out.append((it["line"], "文が数・範囲の言葉で始まる", it["raw"].strip()))
        if not it["text"] and not it["cont"]:
            out.append((it["line"], "文が空", it["raw"].strip()))
        if it["difficulty"] is None and r["sections"]:
            out.append((it["line"], "難易度が分からない", (it["label"] or "") + " | " + it["raw"].strip()))
    return sorted(out)


def spot_text(it):
    parts = [f"{b:g}" for b in it["beats"]] + [f"{a:g}-{b:g}" for a, b in it["ranges"]]
    return ", ".join(parts) + ("..." if it["repeats"] else "")


def report(name, orig, r, show_items):
    w = []
    title = name + (f"（{orig}）" if orig and orig != name else "")
    w.append(f"=== {title}")
    if "error" in r:
        w.append(f"  読めない: {r['error']}")
        return w, None
    kinds = Counter(n["kind"] for n in r["notes"])
    conts = sum(len(it["cont"]) for it in r["items"])
    subs = sum(1 for it in r["items"] if it["parent"] is not None)
    w.append(f"  行 {r['lineCount']}・項目 {len(r['items'])}・拍の無い行 {len(r['notes'])}（" +
             "・".join(f"{k} {kinds.get(k, 0)}" for k in ("comment", "mapper", "divider", "unreadable")) +
             f"）・続きの行 {conts}・細かい指摘 {subs}・返事 {sum(1 for it in r['items'] if it['response'])}")
    by = Counter(f"{it['difficulty']}" + ("" if it["mode"] == "Standard" else f"/{it['mode']}") for it in r["items"])
    w.append("  難易度: " + ("・".join(f"{k} {v}" for k, v in by.items()) or "なし") + f"（ファイル名から: {r['fileDifficulty']}）")
    for s in r["sections"]:
        w.append(f"  見出し: {s['line']}行目 {s['difficulty']}（{s['mode']}）" + (f" 名前 {s['label']}" if s["label"] else "") +
                 (f" 担当 {s['mapper']}" if s["mapper"] else "") + (" 推測" if s["guess"] else ""))
    sev = Counter(it["severity"] for it in r["items"] if it["severity"])
    if sev:
        w.append("  重さ: " + "・".join(f"{k} {v}" for k, v in sev.items()))
    if r["responses"]:
        w.append("  返事を分けた（行の後ろの - fixed 等）")
    for x in r["warnings"]:
        w.append(f"  警告: {x['line']}行目 {x['code']} {x['text']}")
    if r["notes"]:
        w.append("  拍の無い行:")
        for n in r["notes"]:
            w.append(f"    {n['line']}: [{n['kind']}] {n['text']}")
    sus = suspects(r)
    if sus:
        w.append("  要確認:")
        for line, why, t in sus:
            w.append(f"    {line}: {why}: {t}")
    if show_items:
        w.append("  項目:")
        for it in r["items"]:
            extra = []
            if it["severity"]:
                extra.append(f"重さ {it['severity']}")
            if it["parent"] is not None:
                extra.append(f"親 {it['parent']}")
            if it["group"] is not None:
                extra.append(f"まとめ {it['group']}")
            if it["sameAsPrev"]:
                extra.append(f"前と同じ {it['prev']}")
            if it["response"]:
                extra.append(f"返事「{it['response']}」")
            if it["quoted"]:
                extra.append("引用")
            w.append(f"    {it['line']}: [{it['difficulty']}] {spot_text(it)} | {it['text']}" + (f"  ({'・'.join(extra)})" if extra else ""))
            for c in it["cont"]:
                w.append(f"        続き: {c}")
    return w, sus


def main():
    ap = argparse.ArgumentParser(description="審査の指摘の .txt をまとめて読んで確かめる（結果はリポジトリの外へ）")
    ap.add_argument("paths", nargs="+", help="フォルダ（中の .txt を全部）か .txt")
    ap.add_argument("--names", help="保存名と元のファイル名の対応（TSV）")
    ap.add_argument("--labels", help="難易度の名前の表（例 AT=ExpertPlus,IN=Expert）")
    ap.add_argument("--default", dest="default_diff", help="見出し・ファイル名が無い時の難易度")
    ap.add_argument("--items", action="store_true", help="項目の一覧も出す")
    ap.add_argument("--out", help="結果を書くファイル（リポジトリの外）")
    a = ap.parse_args()

    if a.out:
        out = Path(a.out).resolve()
        try:
            out.relative_to(ROOT)
            print("--out がリポジトリの中です（他人の文章が入るので、リポジトリの外を指定してください）", file=sys.stderr)
            return 2
        except ValueError:
            pass
    files = []
    for p in a.paths:
        q = Path(p)
        if q.is_dir():
            files += sorted(x for x in q.iterdir() if x.is_file() and x.suffix.lower() == ".txt")
        elif q.is_file():
            files.append(q)
        else:
            print(f"見つかりません: {p}", file=sys.stderr)
            return 2
    if not files:
        print("読む .txt がありません", file=sys.stderr)
        return 2
    names = load_names(a.names) if a.names else {}
    labels = parse_labels(a.labels)

    import json
    from cdp import Editor
    lines, total = [], Counter()
    with Editor(ready=True) as ed:
        for f in files:
            orig = names.get(f.name)
            opts = {"fileName": orig or f.name, "labels": labels}
            if a.default_diff:
                opts["defaultDifficulty"] = a.default_diff
            r = ed.js(JS % {"b64": json.dumps(base64.b64encode(f.read_bytes()).decode("ascii")), "opts": json.dumps(opts, ensure_ascii=False)})
            w, sus = report(f.name, orig, r, a.items)
            lines += w + [""]
            if "error" not in r:
                total["files"] += 1
                total["items"] += len(r["items"])
                total["notes"] += len(r["notes"])
                total["suspects"] += len(sus)
                total["warnings"] += len(r["warnings"])
        errs = ed.errors()
    lines.append(f"合計: {total['files']}件・項目 {total['items']}・拍の無い行 {total['notes']}・警告 {total['warnings']}・要確認 {total['suspects']}")
    if errs:
        lines.append("ページ内のエラー: " + " / ".join(errs[:5]))
    text = "\n".join(lines) + "\n"
    if a.out:
        Path(a.out).write_text(text, encoding="utf-8")
        print(lines[-1])
    else:
        sys.stdout.write(text)
    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(main())

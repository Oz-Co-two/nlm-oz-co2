"""コード譜（行ごとのコードの並び）を音源の拍ごとの和音に当てはめ、セクションの開始拍を出す。
analyze_structure.py の答え合わせ用の正解ファイル（--truth）を作るためのもの。

使い方:
  .venv/Scripts/python tools/chords_to_truth.py <音源> <コード譜.txt> --bpm 129 --lead-ms 240 [--out <正解.json>]
  （--nlmf <プロジェクト> でも BPM・無音追加などを読める）

コード譜.txt の書き方（1行＝コード譜の1行。[ ] の行はセクションの見出し。# で始まる行はコメント）:
  [イントロ]
  C F A# D# G# C#
  [Aメロ]
  F#m Bm E A C#
コードは C, C#m, F#7, G#m7-5, Fdim, Cmaj7 などの書き方。同じ見出しは何度書いてもよい（グループ分けの正解にも使う）。

仕組み: 拍ごとのクロマ（調波成分の CQT を音名ごとに足したもの）と各コードの形（構成音）の近さを点数にし、
「コードの順番は変えない・各コードは1拍以上・コードが変わるたびに少し罰点」で全体の点数が最大になる当てはめ方を
動的計画法で探す。各行の頭の拍と、コードごとの拍数を表示するので、おかしな所（コード譜の省略で1つのコードが
長すぎる、など）は目で確かめて、出力の JSON を手で直す。
"""
import argparse
import json
import os
import re
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import analyze_structure as AS  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

NAMES = {"C": 0, "C#": 1, "Db": 1, "D": 2, "D#": 3, "Eb": 3, "E": 4, "F": 5, "F#": 6, "Gb": 6, "G": 7,
         "G#": 8, "Ab": 8, "A": 9, "A#": 10, "Bb": 10, "B": 11}
PENALTY = 0.3      # コードが変わるたびの罰点（小さいとコードが細かく揺れ、大きいと長いコードに寄る）
LONG_BEATS = 12    # これより長く続くコードは「コード譜の省略かも」と知らせる


def intervals(q):
    """コードの種類の文字列 → 構成音（根音からの半音数）。テンション（9・11・13・add）は無視して基本の形で見る。"""
    q = q.replace("(", "").replace(")", "").replace("♭", "b").replace("♯", "#")
    if re.match(r"(m7-5|m7b5|mb5|ø)", q):
        return (0, 3, 6, 10)
    if q.startswith("dim"):
        return (0, 3, 6, 9) if "7" in q else (0, 3, 6)
    if q.startswith("aug") or q.startswith("+"):
        return (0, 4, 8)
    minor = q.startswith("m") and not q.lower().startswith("maj")
    base = (0, 5, 7) if "sus4" in q else (0, 2, 7) if "sus2" in q else (0, 3, 7) if minor else (0, 4, 7)
    if re.search(r"(maj7|M7|△7)", q):
        return base + (11,)
    if re.search(r"(?<![0-9])(7|9|11|13)", q.replace("maj", "")) and "add" not in q:
        return base + (10,)
    if re.search(r"(?<![0-9])6", q):
        return base + (9,)
    return base


def template(ch):
    """コード名 → 12音名の重み。コードなし（N.C. など）は None。"""
    ch = ch.replace("♭", "b").replace("♯", "#").split("/")[0].strip()   # 分数コードはベース音を無視
    m = re.match(r"([A-G][#b]?)(.*)", ch)
    if not m:
        return None
    v = np.zeros(12)
    for i, iv in enumerate(intervals(m.group(2))):
        v[(NAMES[m.group(1)] + iv) % 12] = 1.0 if i < 3 else 0.6
    v[NAMES[m.group(1)]] += 0.5   # 根音を少し強める
    return v / np.linalg.norm(v)


def read_sheet(path):
    """[(行番号, 見出し or None, [コード…])] を返す。見出しはその後の最初の行に付ける。"""
    out, head = [], None
    for ln, raw in enumerate(open(path, encoding="utf-8"), 1):
        s = raw.strip()
        if not s or s.startswith("#"):   # # で始まる行はコメント（コード名の # とぶつかるので行の途中からは無理）
            continue
        m = re.fullmatch(r"\[(.+)\]", s)
        if m:
            head = m.group(1).strip()
            continue
        out.append((ln, head, s.split()))
        head = None
    return out


def beat_chroma(F):
    amp = 10 ** (F["CQ"] / 20)
    nb = amp.shape[1] // AS.SUB
    ch = np.zeros((12, nb))
    for k in range(amp.shape[0]):
        ch[k % 12] += amp[k, :nb * AS.SUB].reshape(nb, AS.SUB).sum(1)
    ch /= np.linalg.norm(ch, axis=0, keepdims=True) + 1e-9
    db = 20 * np.log10(F["E"][:nb * AS.SUB].reshape(nb, AS.SUB).mean(1) + 1e-6)
    return ch, db


def align(S, b0, b1):
    """S[コード, 拍] の点数で、コードを順番どおり拍 b0〜b1 に並べる。各コードの開始拍を返す。"""
    N, B = S.shape
    NEG = -1e18
    D = np.full((N, B), NEG); P = np.zeros((N, B), np.int8)   # P: 1=この拍で前のコードから移った
    D[0, b0] = S[0, b0]; P[0, b0] = 1
    for t in range(b0 + 1, b1):
        stay = D[:, t - 1]
        move = np.r_[NEG, D[:-1, t - 1] - PENALTY]
        P[:, t] = move > stay
        D[:, t] = np.maximum(stay, move) + S[:, t]
    if D[N - 1, b1 - 1] <= NEG / 2:
        sys.exit("拍の数よりコードが多すぎて当てはめられません")
    starts = np.zeros(N, int)
    j = N - 1
    for t in range(b1 - 1, b0 - 1, -1):
        if P[j, t]:
            starts[j] = t
            j -= 1
            if j < 0:
                break
    return starts


def main():
    ap = argparse.ArgumentParser(description="コード譜からセクションの開始拍（正解ファイル）を作る")
    ap.add_argument("path", help="音源")
    ap.add_argument("sheet", help="コード譜のテキスト")
    ap.add_argument("--nlmf"); ap.add_argument("--bpm", type=float); ap.add_argument("--lead-ms", type=float)
    ap.add_argument("--out", help="出力の JSON（既定: コード譜と同じ名前の .truth.json）")
    ap.add_argument("--transpose", default="auto",
                    help="コード譜を何半音上げて音源に合わせるか。auto=12通り試して一番合うもの（カポ付きのコード譜のため）")
    a = ap.parse_args()
    if a.nlmf:
        tm = AS.load_nlmf(a.nlmf)[0]
    elif a.bpm:
        tm = AS.TempoMap(a.bpm)
    else:
        sys.exit("--bpm（または --nlmf）が必要です")
    if a.bpm:
        tm.bpm = a.bpm
    if a.lead_ms is not None:
        tm.song_off = -a.lead_ms / 1000

    rows = read_sheet(a.sheet)
    seq = [(ri, ch) for ri, (_, _, chs) in enumerate(rows) for ch in chs]
    T = np.array([t if t is not None else np.zeros(12) for t in (template(ch) for _, ch in seq)])   # コードなし=点数0
    chroma, db = beat_chroma(AS.measure(a.path, tm))
    live = db > db.max() - 30
    b0 = int(np.argmax(live)); b1 = len(live) - int(np.argmax(live[::-1]))
    best = None
    for sh in (range(12) if a.transpose == "auto" else [int(a.transpose) % 12]):
        S = np.roll(T, sh, axis=1) @ chroma
        st = align(S, b0, b1)
        du = np.diff(np.r_[st, b1])
        ft = np.mean([S[j, st[j]:st[j] + du[j]].mean() for j in range(len(seq))])
        if best is None or ft > best[0]:
            best = (ft, sh, S, st, du)
    fit, shift, S, starts, dur = best
    print(f"音のある拍 {b0}〜{b1} ・ コード {len(seq)} 個 ・ 移調 +{shift} 半音 ・ 当てはまり（平均）{fit:.2f}\n")
    sections = []
    for ri, (ln, head, _) in enumerate(rows):
        js = [j for j, (r, _) in enumerate(seq) if r == ri]
        st = int(starts[js[0]])
        if head:
            sections.append({"beat": st, "name": head})
        cs = " ".join(f"{seq[j][1]}({dur[j]})" for j in js)
        warn = "  ← 長すぎるコード（コード譜の省略かも）" if max(dur[j] for j in js) > LONG_BEATS else ""
        print(f"{ln:4d}行目 拍{st:4d} {('[' + head + ']') if head else '':12s} {cs}{warn}")
    out = a.out or os.path.splitext(a.sheet)[0] + ".truth.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump({"note": f"chords_to_truth.py で {os.path.basename(a.sheet)} から作成（移調 +{shift}・当てはまり {fit:.2f}）。"
                           "目で確かめて直すこと。", "fit": round(float(fit), 3), "transpose": shift,
                   "sections": sections}, f, ensure_ascii=False, indent=1)
    print(f"\nセクション: " + " / ".join(f"{s['name']}@{s['beat']}" for s in sections))
    print(f"正解ファイル: {out}")


if __name__ == "__main__":
    main()

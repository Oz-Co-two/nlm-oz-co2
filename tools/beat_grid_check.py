"""設定したBPM・無音追加(ms)のグリッドと、実際の音の打点のズレを1拍ごとに測る。

使い方:
  .venv/Scripts/python tools/beat_grid_check.py <音源ファイル> --bpm 83.94 --lead-ms 250

グリッドの拍kは、元音源上で t = k * 60/BPM - lead の位置にある(無音追加でlead分だけ後ろにずれる)。
各グリッド拍の前後 ±WINDOW 秒でパーカッシブ成分のオンセット強度が最大の点を打点とみなし、
ズレ(打点 - グリッド)をms単位で出す。正なら音がグリッドより遅い、負なら音が先。

ズレを拍番号に対して直線で当てはめ(Theil-Sen、外れ値に強い)、傾きからBPM補正、
切片から無音追加の補正を提案する。傾きが有意でなく、途中で段差状に跳ぶ場合は
テンポ変化なので、tempo_drift.py / analyze_tempo.py も併用してテンポパートで対処する。
"""
import argparse
import sys
import warnings

import librosa
import numpy as np
from scipy.stats import theilslopes

warnings.filterwarnings("ignore")
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

HOP = 128
WINDOW = 0.2        # 打点を探す範囲(グリッド拍の前後, 秒)。半拍より十分小さくする
STRONG_PCT = 70     # オンセット強度がこのパーセンタイル以上の打点だけ使う
BLOCK = 6           # 表示の集計幅(秒)


def measure(y, sr, bpm, lead_ms):
    yp = librosa.effects.percussive(y)
    env = librosa.onset.onset_strength(y=yp, sr=sr, hop_length=HOP)
    tm = librosa.times_like(env, sr=sr, hop_length=HOP)
    thr = np.percentile(env, STRONG_PCT)
    period = 60.0 / bpm
    rows = []  # (拍番号, グリッド時刻, ズレms)
    for k in range(int((tm[-1] + lead_ms / 1000) / period) + 1):
        g = k * period - lead_ms / 1000
        if g < WINDOW or g > tm[-1] - WINDOW:
            continue
        m = (tm > g - WINDOW) & (tm < g + WINDOW)
        i = int(np.argmax(np.where(m, env, -1)))
        if env[i] >= thr:
            rows.append((k, g, (tm[i] - g) * 1000))
    return np.array(rows), period


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("path")
    ap.add_argument("--bpm", type=float, required=True, help="NLMに設定しているBPM")
    ap.add_argument("--lead-ms", type=float, default=0.0, help="NLMの無音追加(ms)")
    a = ap.parse_args()

    y, sr = librosa.load(a.path, sr=22050, mono=True)
    rows, period = measure(y, sr, a.bpm, a.lead_ms)
    if len(rows) < 20:
        print("強い打点が少なすぎて判定できません")
        return

    print(f"BPM {a.bpm} / 無音追加 {a.lead_ms:g} ms / 使用した打点 {len(rows)} 個")
    print(f"\n{BLOCK}秒ごとのズレ中央値 (正=音が遅い, 負=音が先)")
    for s in np.arange(0, rows[-1, 1] + BLOCK, BLOCK):
        b = rows[(rows[:, 1] >= s) & (rows[:, 1] < s + BLOCK)]
        if len(b) >= 3:
            print(f"{int(s // 60)}:{int(s % 60):02d}-  {np.median(b[:, 2]):+6.0f} ms  n={len(b)}")

    # dev = a*k + b。a[ms/拍]は真の周期との差、bは無音追加の過不足
    slope, icpt, lo, hi = theilslopes(rows[:, 2], rows[:, 0])
    true_period = period + slope / 1000
    true_bpm = 60.0 / true_period
    true_lead = a.lead_ms - icpt
    span = rows[-1, 1] - rows[0, 1]
    total_drift = slope * (rows[-1, 0] - rows[0, 0])
    print(f"\n直線当てはめ: 傾き {slope:+.3f} ms/拍 (95%範囲 {lo:+.3f}〜{hi:+.3f}), 切片 {icpt:+.0f} ms")
    print(f"曲全体({span:.0f}秒)で溜まるズレ: {total_drift:+.0f} ms")
    print(f"提案: BPM {true_bpm:.3f} (95%範囲 {60/(period+hi/1000):.3f}〜{60/(period+lo/1000):.3f}), "
          f"無音追加 {true_lead:.0f} ms")
    if lo <= 0 <= hi:
        print("→ 傾きは有意ではない: BPMは今のままでよい")
    resid = rows[:, 2] - (slope * rows[:, 0] + icpt)
    print(f"当てはめ後の残差 中央絶対偏差 {np.median(np.abs(resid)):.0f} ms "
          f"(大きい区間は上の表で段差・突出として現れる)")


if __name__ == "__main__":
    main()

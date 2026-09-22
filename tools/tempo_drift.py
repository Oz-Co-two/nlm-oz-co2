"""一定テンポを仮定した拍グリッドからのズレを調べ、テンポ変化の有無を判定する。

使い方: .venv/Scripts/python tools/tempo_drift.py <音源ファイル> [--lo <BPM>] [--hi <BPM>]

全体の最適BPMを細かく探索し、20秒窓ごとの最適BPMと、全体グリッドに対する位相ズレを表示する。
位相ズレが時間とともに一方向に溜まる、または窓ごとのBPMが継続的に変わるなら、テンポ変化がある。
"""
import sys
import warnings
import argparse

import librosa
import numpy as np

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

warnings.filterwarnings("ignore")
HOP = 512
WIN, STEP = 20.0, 10.0
# デフォルト探索範囲。2倍・1.5倍などの誤認を避けるため、想定テンポ付近に絞る
DEFAULT_LO, DEFAULT_HI = 75.0, 92.0


def best_bpm(env, times, lo, hi, step):
    bpms = np.arange(lo, hi, step)
    z = np.array([np.abs(np.sum(env * np.exp(-2j * np.pi * (b / 60.0) * times))) for b in bpms])
    return bpms[int(np.argmax(z))], z.max() / (env.sum() + 1e-9)


def phase_at(env, times, bpm):
    z = np.sum(env * np.exp(-2j * np.pi * (bpm / 60.0) * times))
    return np.angle(z) / (2 * np.pi)  # 拍単位(-0.5〜0.5)


def main(path, lo, hi):
    y, sr = librosa.load(path, sr=22050, mono=True)
    env = librosa.onset.onset_strength(y=y, sr=sr, hop_length=HOP)
    env = np.maximum(env - np.median(env), 0)
    times = librosa.times_like(env, sr=sr, hop_length=HOP)

    g, gs = best_bpm(env, times, lo, hi, 0.05)
    print(f"全体の最適BPM: {g:.2f} (強度 {gs:.3f})\n")
    print("窓(秒)      窓内最適BPM  強度   全体グリッドとの位相差(拍)")
    for s in np.arange(0, times[-1] - WIN + 1, STEP):
        m = (times >= s) & (times < s + WIN)
        b, st = best_bpm(env[m], times[m], g - 6, g + 6, 0.05)
        ph = phase_at(env[m], times[m], g)
        print(f"{s:>5.0f}-{s+WIN:<5.0f}  {b:8.2f}   {st:.3f}   {ph:+.2f}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="テンポ変化を調べるツール")
    parser.add_argument("path", help="音源ファイルのパス")
    parser.add_argument("--lo", type=float, default=DEFAULT_LO, help=f"探索BPM下限（デフォルト: {DEFAULT_LO}）")
    parser.add_argument("--hi", type=float, default=DEFAULT_HI, help=f"探索BPM上限（デフォルト: {DEFAULT_HI}）")
    args = parser.parse_args()
    main(args.path, args.lo, args.hi)

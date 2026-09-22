"""MP3のテンポ変化を検出する解析スクリプト。

使い方: .venv/Scripts/python tools/analyze_tempo.py <音源ファイル>

ビート位置を検出し、拍間隔から局所BPMを求め、BPMが変わる位置を区間として出力する。
2倍/半分の誤認は、80〜160の範囲に折り返して吸収する。
"""
import sys

import librosa
import numpy as np

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# 折り返し範囲。2倍/半分は譜面側で吸収できるためオクターブ誤差は無視する
BPM_LO, BPM_HI = 80.0, 160.0
# 区間として分けるBPM差の閾値
SPLIT_BPM_DIFF = 3.0
# 短すぎる区間(ノイズ)を前後にマージする拍数
MIN_SEG_BEATS = 8


def fold_bpm(bpm):
    while bpm < BPM_LO:
        bpm *= 2
    while bpm >= BPM_HI:
        bpm /= 2
    return bpm


def main(path):
    y, sr = librosa.load(path, sr=22050, mono=True)
    dur = len(y) / sr
    print(f"長さ: {dur:.1f}s")

    # 全体テンポを初期値にしつつ、ビートトラッカーが変化に追従できるよう tightness を緩める
    tempo, beats = librosa.beat.beat_track(y=y, sr=sr, tightness=50, units="time")
    print(f"全体推定テンポ: {float(np.atleast_1d(tempo)[0]):.1f} BPM / 検出拍数: {len(beats)}")
    if len(beats) < MIN_SEG_BEATS:
        print("拍が少なすぎて解析できません")
        return

    ibi = np.diff(beats)
    # 移動中央値で外れ値(拍の取りこぼし)をならす
    k = 5
    pad = np.pad(ibi, k // 2, mode="edge")
    smooth = np.array([np.median(pad[i:i + k]) for i in range(len(ibi))])
    bpms = np.array([fold_bpm(60.0 / v) for v in smooth])

    # BPMが基準から閾値以上ずれたら新区間
    segs = []  # [start_idx, end_idx(含まない)]
    start = 0
    for i in range(1, len(bpms)):
        base = np.median(bpms[start:i])
        if abs(bpms[i] - base) > SPLIT_BPM_DIFF:
            segs.append([start, i])
            start = i
    segs.append([start, len(bpms)])

    # 短い区間を直前にマージ
    merged = []
    for s in segs:
        if merged and (s[1] - s[0]) < MIN_SEG_BEATS:
            merged[-1][1] = s[1]
        else:
            merged.append(s)

    print("\n区間      開始(秒)  終了(秒)  拍数  BPM")
    for n, (a, b) in enumerate(merged, 1):
        bpm = float(np.median(bpms[a:b]))
        print(f"{n:>2}  {beats[a]:>9.2f} {beats[b]:>9.2f} {b - a:>5}  {bpm:6.1f}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("使い方: python tools/analyze_tempo.py <音源ファイル>")
    main(sys.argv[1])

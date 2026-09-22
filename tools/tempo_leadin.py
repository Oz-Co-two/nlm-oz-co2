"""曲頭は無音/弱起でビート検出の精度が落ちやすい問題を避けるため、
まず曲の中央付近だけでBPMを確定し(テンポは曲の大半で一定という前提)、
そのBPMで曲全体のグリッドと実際の打点のズレを測って無音追加量を直接計算する。

analyze_tempo.py / tempo_drift.py / beat_grid_check.py を手作業で繰り返す代わりに、
「BPM確定」と「無音追加量の逆算」を1回の実行で済ませるのが狙い。

使い方:
  .venv/Scripts/python tools/tempo_leadin.py <音源ファイル> [--lo 75] [--hi 180] [--segments 4] [--center 0.6]

進め方:
  1. 曲の中央 --center 割合(既定60%)を --segments 分割(既定4)し、区間ごとに最適BPMをFourier探索。
     区間間のばらつきが小さければ「テンポは一定」とみなし、中央値をBPMとして確定する。
     ばらつきが大きい場合はテンポ変化の疑いを警告するので、tempo_drift.pyで詳細確認する。
  2. 確定したBPMで無音追加0msのグリッドを仮定し、曲全体(先頭含む)で1拍ごとのズレを測る。
     ズレの切片(Theil-Sen、外れ値に強い)がそのまま「追加すべき無音の量」になる。
  3. 出力される提案値で beat_grid_check.py を実行し、傾きが有意でなくなることを確認する。
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
WINDOW = 0.2        # beat_grid_check.pyと同じ: 打点を探す範囲(グリッド拍の前後, 秒)
STRONG_PCT = 70      # オンセット強度がこのパーセンタイル以上の打点だけ使う


def segment_bpm(y, sr, t0, t1, lo, hi):
    """[t0,t1)区間だけでFourier法により最適BPMを求める(tempo_drift.pyのbest_bpmと同じ発想)"""
    i0, i1 = int(t0 * sr), int(t1 * sr)
    yp = librosa.effects.percussive(y[i0:i1])
    env = librosa.onset.onset_strength(y=yp, sr=sr, hop_length=HOP)
    env = np.maximum(env - np.median(env), 0)
    times = librosa.times_like(env, sr=sr, hop_length=HOP)
    bpms = np.arange(lo, hi, 0.02)
    z = np.array([np.abs(np.sum(env * np.exp(-2j * np.pi * (b / 60.0) * times))) for b in bpms])
    return float(bpms[int(np.argmax(z))])


def measure(y, sr, bpm, lead_ms=0.0):
    """beat_grid_check.pyのmeasure()と同じ: グリッドと実際の打点のズレ(拍番号,グリッド時刻,ズレms)を返す"""
    yp = librosa.effects.percussive(y)
    env = librosa.onset.onset_strength(y=yp, sr=sr, hop_length=HOP)
    tm = librosa.times_like(env, sr=sr, hop_length=HOP)
    thr = np.percentile(env, STRONG_PCT)
    period = 60.0 / bpm
    rows = []
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
    ap.add_argument("--lo", type=float, default=75.0, help="探索BPM下限(既定75)")
    ap.add_argument("--hi", type=float, default=180.0, help="探索BPM上限(既定180)")
    ap.add_argument("--segments", type=int, default=4, help="中央部を何分割してBPM検出するか(既定4)")
    ap.add_argument("--center", type=float, default=0.6, help="曲全体の中央何割を使うか(既定0.6=中央60%)")
    a = ap.parse_args()

    y, sr = librosa.load(a.path, sr=22050, mono=True)
    dur = len(y) / sr

    # Phase 1: 曲の中央部をsegments分割してBPMを検出し、区間間の一致を確認する
    margin = (1 - a.center) / 2
    t0, t1 = dur * margin, dur * (1 - margin)
    seg_len = (t1 - t0) / a.segments
    print(f"曲の長さ: {dur:.1f}s / 中央 {t0:.1f}s〜{t1:.1f}s を{a.segments}分割してBPM検出\n")
    bpms = []
    for i in range(a.segments):
        s0, s1 = t0 + i * seg_len, t0 + (i + 1) * seg_len
        b = segment_bpm(y, sr, s0, s1, a.lo, a.hi)
        bpms.append(b)
        print(f"  区間{i + 1} {s0:6.1f}-{s1:6.1f}s: {b:7.2f} BPM")
    bpms = np.array(bpms)

    # 中央絶対偏差(MAD)基準で倍音・半音誤認などの外れ値を除外してから中央値を取る
    # (単純なmax-minだと1区間の誤検出だけで「ばらつき大」と誤判定してしまう)
    med0 = np.median(bpms)
    mad = np.median(np.abs(bpms - med0))
    keep = np.abs(bpms - med0) <= max(1.5 * mad, 0.3)
    if keep.sum() < len(bpms):
        dropped = ", ".join(f"{b:.2f}" for b in bpms[~keep])
        print(f"\n  外れ値として除外: {dropped} BPM (倍音/半音の誤検出の疑い)")
    bpms_kept = bpms[keep] if keep.sum() >= max(2, len(bpms) // 2) else bpms

    spread = bpms_kept.max() - bpms_kept.min()
    bpm = float(np.median(bpms_kept))
    print(f"\n中央値BPM: {bpm:.2f} (採用 {len(bpms_kept)}/{len(bpms)} 区間, 幅: {spread:.2f})")
    if spread > 1.0:
        print("⚠ 採用区間内でもBPMのばらつきが大きい → テンポ変化がある可能性。tempo_drift.py で詳細確認を推奨")
    else:
        print("→ 区間ごとのBPMはほぼ一致。テンポは一定とみなして進めます")

    # Phase 2: 確定したBPM付近から無音追加0msで解析し、傾きが有意でなくなるまでBPMを追い込む
    # (区間分割のFourier探索は刻み0.02と粗いため、ここでBPMの小数第3位まで精密化する)
    significant = True
    for it in range(4):
        rows, period = measure(y, sr, bpm, lead_ms=0.0)
        if len(rows) < 20:
            print("\n強い打点が少なすぎて無音追加量を判定できません")
            return
        slope, icpt, lo_s, hi_s = theilslopes(rows[:, 2], rows[:, 0])
        significant = not (lo_s <= 0 <= hi_s)
        print(f"\n[反復{it + 1}] BPM {bpm:.3f} / 無音追加0msで解析: "
              f"傾き {slope:+.3f} ms/拍 (95%範囲 {lo_s:+.3f}〜{hi_s:+.3f})")
        if not significant or abs(slope) < 0.005:
            break
        bpm = 60.0 / (period + slope / 1000)   # 傾き分をBPMへ反映して再測定

    lead_ms = max(0.0, icpt)
    print(f"\n提案: BPM {bpm:.3f} / 無音追加 {lead_ms:.0f} ms")
    if icpt < 0:
        print("  (切片が負 → 曲頭に既に十分な余白があり、無音追加は不要な可能性)")
    if significant:
        print("⚠ 傾きが有意なまま収束しませんでした → 曲中でテンポが変化している可能性が高い")
    resid = rows[:, 2] - (slope * rows[:, 0] + icpt)
    mad = np.median(np.abs(resid))
    print(f"残差 中央絶対偏差 {mad:.0f} ms (大きい場合は下の裏拍疑いか、beat_grid_check.pyの区間表で詳細確認)")

    # 裏拍(半周期ズレ)の疑い: テンポは合っていても、曲中で「強拍/裏拍のどちらがオンセットとして
    # 強く出るか」が入れ替わる曲だと、6秒ブロックの中央値が基準値と±半周期の2群に割れる。
    # BPMや傾きの検定だけでは検出できないため、ブロックごとの分布から別途チェックする。
    half_ms = period * 500  # 半拍(period秒の半分)をmsで
    block_meds = []
    for s in np.arange(0, rows[-1, 1] + 6, 6):
        blk = rows[(rows[:, 1] >= s) & (rows[:, 1] < s + 6)]
        if len(blk) >= 3:
            block_meds.append(np.median(blk[:, 2]))
    block_meds = np.array(block_meds)
    if len(block_meds):
        near_half = np.abs(np.abs(block_meds - icpt) - half_ms) < half_ms * 0.3
        offbeat_ratio = near_half.mean()
        if offbeat_ratio >= 0.2:
            alt_lead = lead_ms + half_ms   # lead_ms,half_msとも0以上なので常に正
            print(f"\n⚠ 6秒区間の {offbeat_ratio * 100:.0f}% が基準値から半拍(約{half_ms:.0f}ms)ズレた位置に"
                  f"集まっています。")
            print("  曲中で強拍/裏拍どちらがオンセットとして強く出るかが入れ替わっている疑いがあります。")
            print("  どちらが正しいかは自動判定できないため、両方を実際に聞いて確認してください:")
            print(f"    候補A: 無音追加 {lead_ms:.0f} ms")
            print(f"    候補B: 無音追加 {alt_lead:.0f} ms (候補Aの半拍ぶんずらした裏拍側)")

    print(f"\n次の一手:\n  .venv/Scripts/python tools/beat_grid_check.py \"{a.path}\" --bpm {bpm:.3f} --lead-ms {lead_ms:.0f}")


if __name__ == "__main__":
    main()

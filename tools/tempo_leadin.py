"""音源から NLM に入れる BPM と無音追加(ms)を出す（まずこれを実行する）。

使い方:
  .venv/Scripts/python tools/tempo_leadin.py <音源ファイル> [--lo 75] [--hi 180]

計算は本体に同梱する song_analysis/tempo.py にある（2026-10-19 に移した。NLM の「曲を解析」と同じ計算）。
このファイルは表示だけ。song_analysis/tempo.py の名前（onset_env・estimate・定数）はこのモジュールからもそのまま使え、
このモジュールの定数を書き換えると song_analysis/tempo.py にも効く（調整用のスクリプトのため。song_analysis.expose）。

進め方（2026-10-19 に作り直し。前の方式と、それが外れた理由は README の「テンポの推定」）:
  1. 系統を決める: 打楽器成分の打点の強さの流れ（オンセット）を16秒ずつ区切って周期の強さを測り、曲全体で平均する。
     BPM の候補ごとに「その1倍・2倍（8分）・4倍か3倍の強い方（16分か3連符）」の強さを足して一番大きい物を選ぶ。
     1つの周期の強さだけで選ぶと、本当のテンポの 3/2・4/3・5/4 倍（倍音）を拾う曲が多かった。
  2. 2倍・半分のどちらにするか: --lo〜--hi に入る物のうち、その周期そのものが強い方。
     （2倍・半分の違いは譜面でノーツを置く細かさで吸収できるので、どちらでもよい）
  3. 精密にする: 拍の目盛りと実際の打点のずれ（1拍ごと）に直線を当てはめ（Theil-Sen）、傾きが無くなるまで BPM を直す。
     打点を探す幅は拍の 0.4 倍まで（速い曲で隣の拍を拾わないため）。直線の切片から無音追加を出す。
  4. 確かめ: 区間ごとのテンポの揺れ（ライブ録音など）・裏拍（半拍ずれ）の疑い・2番目の系統の強さを出す。
"""
import argparse
import os
import sys
import warnings

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import song_analysis  # noqa: E402
from song_analysis import tempo as _core  # noqa: E402
from song_analysis.tempo import DRIFT_WARN, estimate, onset_env  # noqa: E402,F401

warnings.filterwarnings("ignore")
song_analysis.expose(_core, __name__)


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="NLM に入れる BPM と無音追加(ms)を出す")
    ap.add_argument("path")
    ap.add_argument("--lo", type=float, default=75.0, help="出す BPM の下限（既定75。2倍・半分をこの範囲に折り返す）")
    ap.add_argument("--hi", type=float, default=180.0, help="出す BPM の上限（既定180）")
    a = ap.parse_args()

    env, fps, dur, low = onset_env(a.path)
    r = estimate(env, fps, a.lo, a.hi, low)
    print(f"曲の長さ: {dur:.1f}s")
    if r.get("error"):
        print(f"⚠ {r['error']}（BPM {r['bpm']} は目安）")
        return
    print(f"\n提案: BPM {r['bpm']:g} / 無音追加 {r['lead_ms']:.0f} ms")
    print(f"  （2倍の {round(r['bpm'] * 2, 3):g}・半分の {round(r['bpm'] / 2, 3):g} も同じ拍の流れ。譜面の細かさで選んでよい）")
    if r["raw_bpm"] != r["bpm"]:
        print(f"  当てはめの値は {r['raw_bpm']:.3f}。整数の {r['bpm']:g} でも曲全体でずれが溜まらないので整数にした")
    print(f"  8秒ごとの、目盛りとのずれの中央値のばらつき {r['block_mad_ms']:.0f} ms（20ms 前後までなら耳では区別できない）"
          f"・使った拍 {r['n_beats']}")
    if r["alt"]:
        word = "（迷いあり。こちらも聞いて確かめる）" if r["alt"]["ratio"] >= 0.85 else ""
        print(f"  2番目の候補: BPM {r['alt']['bpm']}（強さ {r['alt']['ratio'] * 100:.0f}%）{word}")
    for s in r["steps"]:
        t = s["sec"]
        print(f"\n⚠ {int(t // 60)}:{int(t % 60):02d} あたりから、打点が目盛りより {s['ms']:+d} ms ずれます（それまでとそれ以降は"
              "それぞれ平ら）。\n  拍の長さの違う所があるか、曲がそこで少しずれています。耳で確かめ、必要ならテンポパートで直す")
    if r["drift_pct"] > DRIFT_WARN:
        print(f"\n⚠ 区間ごとのテンポの幅が {r['drift_pct']:.1f}% あります（ライブ録音・テンポの変わる曲の疑い）。"
              "1つの BPM では途中から合わなくなります:")
        print("  " + "  ".join(f"{int(t // 60)}:{int(t % 60):02d} {b:.1f}" for t, b in r["drift"]))
    if r["offbeat_ratio"] >= 0.2 or r["low_offbeat"]:
        if r["offbeat_ratio"] >= 0.2:
            print(f"\n⚠ 6秒区間の {r['offbeat_ratio'] * 100:.0f}% で、強い打点が半拍ずれた位置にあります（裏拍の疑い）。")
        if r["low_offbeat"]:
            print("\n⚠ 低い音（キック・ベース）は、半拍ずれた位置の方に強く出ています（裏拍の疑い）。")
        print("  どちらが拍の頭かは自動では決められないので、両方を NLM で聞いて合う方を選ぶ:")
        print(f"    候補A: 無音追加 {r['lead_ms']:.0f} ms")
        print(f"    候補B: 無音追加 {r['alt_lead_ms']:.0f} ms（半拍ずらし）")
    print(f"\n次の一手（1拍ごとのずれの確認）:\n  .venv/Scripts/python tools/beat_grid_check.py \"{a.path}\" "
          f"--bpm {r['bpm']:g} --lead-ms {r['lead_ms']:.0f}")


if __name__ == "__main__":
    main()

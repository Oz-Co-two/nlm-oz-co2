"""音源から NLM に入れる BPM と無音追加(ms)を出す（テンポの推定）。

本体（serve.py の /__analysis/tempo）と、開発用のコマンド tools/tempo_leadin.py の両方が使う。
（2026-10-19 に tools/tempo_leadin.py から移した。計算は変えていない）

進め方（2026-10-19 に作り直し。前の方式と、それが外れた理由は tools/README.md の「テンポの推定の作り直し」）:
  1. 系統を決める: 打楽器成分の打点の強さの流れ（オンセット）を16秒ずつ区切って周期の強さを測り、曲全体で平均する。
     BPM の候補ごとに「その1倍・2倍（8分）・4倍か3倍の強い方（16分か3連符）」の強さを足して一番大きい物を選ぶ。
     1つの周期の強さだけで選ぶと、本当のテンポの 3/2・4/3・5/4 倍（倍音）を拾う曲が多かった。
  2. 2倍・半分のどちらにするか: --lo〜--hi に入る物のうち、その周期そのものが強い方。
     （2倍・半分の違いは譜面でノーツを置く細かさで吸収できるので、どちらでもよい）
  3. 精密にする: 拍の目盛りと実際の打点のずれ（1拍ごと）に直線を当てはめ（Theil-Sen）、傾きが無くなるまで BPM を直す。
     打点を探す幅は拍の 0.4 倍まで（速い曲で隣の拍を拾わないため）。直線の切片から無音追加を出す。
  4. 確かめ: 区間ごとのテンポの揺れ（ライブ録音など）・裏拍（半拍ずれ）の疑い・2番目の系統の強さを出す。
"""
import numpy as np
from scipy.stats import theilslopes

SR = 22050
HOP = 128
WIN_SEC = 16.0        # 周期の強さを測る区間の長さ
NFFT = 1 << 16        # 区間の周波数の細かさ（0.16 BPM ほど）
COMB_LO, COMB_HI = 60.0, 240.0
SAME_FAMILY = 0.015   # 2倍・半分を除いてこの割合以内なら同じ系統
STRONG_PCT = 70       # 打点の強さがこのパーセンタイル以上の拍だけ使う
DRIFT_WIN = 20.0      # テンポの揺れを測る区間の長さ
DRIFT_WARN = 1.5      # 区間ごとのテンポの幅（%）がこれを超えたら揺れの警告
BLOCK_SEC = 8.0       # 整数の BPM の確かめ・段差の検出で、目盛りとのずれの中央値を取る区間の長さ
SNAP_MAX = 0.1        # これ以内の整数の BPM を試す
SNAP_DRIFT_MS = 20.0  # 整数にした時、曲全体で溜まるずれがこれ未満なら整数にする
STEP_MIN_BLOCKS = 3   # 段差の前後に最低限いる区間の数
LEAD_BIAS_MS = 30.0   # 無音追加に足す量。耳で合わせた値（利用者が譜面を作った2曲、手元の Beat Saber 譜面の2曲ぶん5つ）と
                      # 比べると、打点の強さの山は 17〜60ms（中央値 31ms）遅かった（7件とも同じ向き。2026-10-19）


def onset_env(path, y=None, progress=None):
    """打楽器成分（HPSS）の打点の強さ。戻り値: (強さ, 1秒あたりの数, 曲の秒, 低い音の打点の強さ3本)
    低い音の3本は 打楽器成分のメル0〜8帯・8〜16帯、元の音のメル0〜8帯（拍の頭か裏拍かの手がかり）
    y: 読み込み済みの音（librosa.load(path, sr=SR, mono=True) の結果。渡せば path は読まない）
    progress: 進み具合（0〜1）を受け取る関数（serve.py の解析の仕事が、取り消しの確認にも使う）"""
    import librosa
    tick = progress or (lambda f: None)
    if y is None:
        y, _ = librosa.load(path, sr=SR, mono=True)
    sr = SR
    tick(0.15)
    yp = librosa.effects.percussive(y)
    tick(0.6)
    env = librosa.onset.onset_strength(y=yp, sr=sr, hop_length=HOP)
    lp = librosa.onset.onset_strength_multi(y=yp, sr=sr, hop_length=HOP, channels=[0, 8, 16])
    lf = librosa.onset.onset_strength_multi(y=y, sr=sr, hop_length=HOP, channels=[0, 8])
    tick(1.0)
    return env, sr / HOP, len(y) / sr, [lp[0], lp[1], lf[0]]


def _flatten(env, fps):
    """1秒ほどのゆっくりした変化を引き、正の部分だけ残す"""
    k = max(3, int(fps) | 1)
    return np.maximum(env - np.convolve(env, np.ones(k) / k, mode="same"), 0)


def tempogram(env, fps):
    """16秒ずつの周期の強さ（区間の大きさで割る）の平均。戻り値: (BPM の目盛り, 強さ)"""
    L = int(WIN_SEC * fps)
    w = np.hanning(L)
    acc, n = None, 0
    for s in range(0, max(1, len(env) - L + 1), L // 2):
        seg = env[s:s + L]
        if len(seg) < L:   # 16秒より短い曲（前は長さを確かめる前に窓を掛けて落ちていた。2026-10-19）
            continue
        x = seg * w
        if x.sum() <= 1e-9:
            continue
        X = np.abs(np.fft.rfft(x, NFFT)) / x.sum()
        acc = X if acc is None else acc + X
        n += 1
    if acc is None:   # 16秒より短い
        x = env * np.hanning(len(env))
        acc, n = np.abs(np.fft.rfft(x, NFFT)) / max(x.sum(), 1e-9), 1
    return np.fft.rfftfreq(NFFT, 1 / fps) * 60, acc / n


def comb(bx, A, cands):
    """候補ごとの点数: 1倍＋2倍＋（4倍と3倍の強い方）"""
    a = lambda h: np.interp(cands * h, bx, A)  # noqa: E731
    return a(1) + a(2) + np.maximum(a(4), a(3))


def same_family(a, b):
    r = np.log2(a / b)
    return abs(r - round(r)) < np.log2(1 + SAME_FAMILY)


def fold(b, lo, hi):
    while b >= hi:
        b /= 2
    while b < lo:
        b *= 2
    return b


def _coherent(env, fps, bpms, hs=(1, 2, 4)):
    """曲全体で位相のそろった周期の強さ（テンポが一定なら細かく決まる）"""
    t = np.arange(len(env)) / fps
    out = np.zeros(len(bpms))
    for h in hs:
        for i, b in enumerate(bpms):
            out[i] += abs(np.sum(env * np.exp(-2j * np.pi * (b * h / 60.0) * t)))
    return out


def grid_rows(env, fps, bpm, lead_ms, thr):
    """NLM の目盛り（元の音源で k*周期 − 無音追加）ごとに、前後 0.4 拍（最大0.2秒）で一番強い打点とのずれ(ms)。
    正＝音が目盛りより遅い。戻り値の列: 拍番号, 目盛りの秒, ずれms"""
    period = 60.0 / bpm
    win = min(0.2, 0.4 * period)
    n = len(env)
    dur = n / fps
    lead = lead_ms / 1000
    rows = []
    for k in range(int((dur + lead) / period) + 1):
        g = k * period - lead
        if g < win or g > dur - win:
            continue
        i0, i1 = int(np.ceil((g - win) * fps)), int(np.floor((g + win) * fps)) + 1
        i = i0 + int(np.argmax(env[i0:i1]))
        if env[i] >= thr:
            rows.append((k, g, (i / fps - g) * 1000))
    return np.array(rows)


def best_lead(env, fps, bpm):
    """目盛りに打点が一番よく乗る無音追加(ms)。5ms 刻みで1拍ぶん調べる"""
    period = 60.0 / bpm
    n = len(env)
    ks = np.arange(1, int(n / fps / period) + 1)
    best = (-1.0, 0.0)
    for L in np.arange(0, period * 1000, 5.0):
        idx = np.round((ks * period - L / 1000) * fps).astype(int)
        idx = idx[(idx > 1) & (idx < n - 2)]
        v = (env[idx - 1] + env[idx] + env[idx + 1]).mean()
        if v > best[0]:
            best = (v, float(L))
    return best[1]


def block_medians(rows, sec=BLOCK_SEC):
    """sec 秒ごとの、目盛りとのずれの中央値。列: 区間の頭の秒, 区間の拍番号の中央, ずれの中央値ms（打点が3個以上の区間だけ）"""
    out = []
    if len(rows) == 0:
        return np.zeros((0, 3))
    for s in np.arange(0, rows[-1, 1] + sec, sec):
        m = (rows[:, 1] >= s) & (rows[:, 1] < s + sec)
        if m.sum() >= 3:
            out.append((s, np.median(rows[m, 0]), np.median(rows[m, 2])))
    return np.array(out) if out else np.zeros((0, 3))


def find_steps(bk, period_ms, depth=0):
    """ずれの中央値が途中で段差状に跳ぶ所（その前後はそれぞれ平ら）。戻り値: [{"sec": 秒, "ms": 跳んだ量}]
    跳び方が 拍の 8% か 25ms の大きい方を超え、前後の中のばらつきが跳びの半分未満の時だけ。3段まで"""
    n = len(bk)
    if n < 2 * STEP_MIN_BLOCKS or depth >= 3:
        return []
    v = bk[:, 2]
    best = None
    for i in range(STEP_MIN_BLOCKS, n - STEP_MIN_BLOCKS + 1):
        a, b = np.median(v[:i]), np.median(v[i:])
        d = b - a
        spread = max(np.median(np.abs(v[:i] - a)), np.median(np.abs(v[i:] - b)))
        if abs(d) > max(25.0, 0.08 * period_ms) and spread < abs(d) / 2 and (best is None or abs(d) > abs(best[1])):
            best = (i, d)
    if best is None:
        return []
    i, d = best
    return (find_steps(bk[:i], period_ms, depth + 1) + [{"sec": round(float(bk[i, 0]), 1), "ms": round(float(d))}]
            + find_steps(bk[i:], period_ms, depth + 1))


def flat_slope(bk, period_ms):
    """区間ごとの中央値の傾き(ms/拍)。段差で区切った中の組だけで測る（段差をまたぐ組は数えない）"""
    edges = [s["sec"] for s in find_steps(bk, period_ms)]
    seg = np.searchsorted(edges, bk[:, 0], side="right")
    sl = [(bk[j, 2] - bk[i, 2]) / (bk[j, 1] - bk[i, 1])
          for i in range(len(bk)) for j in range(i + 1, len(bk)) if seg[i] == seg[j] and bk[j, 1] > bk[i, 1]]
    return float(np.median(sl)) if sl else 0.0


def local_tempi(env, fps, bpm):
    """20秒ずつ（半分重ねる）、bpm の ±4% で一番強い周期。テンポの揺れを見る用。戻り値: [(区間の頭の秒, BPM)]"""
    L = int(DRIFT_WIN * fps)
    cands = bpm * np.linspace(0.96, 1.04, 161)
    out = []
    for s in range(0, len(env) - L + 1, L // 2):
        x = env[s:s + L]
        if x.sum() <= 1e-9:
            continue
        sc = _coherent(x * np.hanning(L), fps, cands)
        out.append((s / fps, float(cands[int(np.argmax(sc))])))
    return out


def estimate(env, fps, lo=75.0, hi=180.0, low=None):
    """打点の強さ（打楽器成分）から BPM・無音追加などを出す。low は onset_env の低い音の3本（無ければ裏拍の手がかりを省く）。
    戻り値は dict（説明は main の表示を参照）"""
    e = _flatten(env, fps)
    bx, A = tempogram(e, fps)
    cands = np.arange(COMB_LO, COMB_HI, 0.05)
    sc = comb(bx, A, cands)
    fam = float(cands[int(np.argmax(sc))])
    # 2番目の系統（同じ系統を除いた一番大きい山）
    peaks = [i for i in range(1, len(sc) - 1) if sc[i] >= sc[i - 1] and sc[i] >= sc[i + 1]]
    others = sorted((sc[i], float(cands[i])) for i in peaks if not same_family(cands[i], fam))
    alt = None
    if others:
        alt = {"bpm": round(fold(others[-1][1], lo, hi), 2), "ratio": round(float(others[-1][0] / sc.max()), 2)}
    # 2倍・半分: 範囲に入る物のうち周期そのものが強い方
    octs = [fam * 2.0 ** k for k in range(-3, 4) if lo <= fam * 2.0 ** k < hi] or [fold(fam, lo, hi)]
    bpm = max(octs, key=lambda b: np.interp(b, bx, A))
    # 曲全体の位相のそろい方で細かくする（テンポが一定の曲向け。揺れる曲でも下の当てはめで直る）
    fine = bpm + np.arange(-0.3, 0.3001, 0.005)
    bpm = float(fine[int(np.argmax(_coherent(e, fps, fine)))])
    drift = local_tempi(e, fps, bpm)
    dv = np.array([b for _, b in drift]) if drift else np.array([bpm])
    drift_pct = float((np.percentile(dv, 90) - np.percentile(dv, 10)) / bpm * 100)

    thr = np.percentile(env, STRONG_PCT)
    lead = best_lead(e, fps, bpm)
    significant, slope, rows = True, 0.0, None
    for _ in range(6):
        rows = grid_rows(env, fps, bpm, lead, thr)
        if len(rows) < 20:
            return {"bpm": round(bpm, 3), "lead_ms": round(lead, 1), "error": "強い打点が少なすぎる",
                    "family": round(fam, 2), "alt": alt, "drift_pct": round(drift_pct, 2), "drift": drift}
        slope, icpt, lo_s, hi_s = theilslopes(rows[:, 2], rows[:, 0])
        significant = not (lo_s <= 0 <= hi_s)
        period = 60.0 / bpm
        lead = (lead - icpt) % (period * 1000)        # 打点が遅い（切片が正）なら無音追加を減らす
        if not significant or abs(slope) < 0.005:
            break
        bpm = 60.0 / (period + slope / 1000)
    raw_bpm = bpm
    # 整数の BPM でも曲全体でずれが溜まらなければ整数にする（曲は普通 整数の BPM で作られている）。
    # 1拍ごとの当てはめは、途中で拍が一度ずれる曲（段差）で傾きを付けてしまうので、8秒ごとの中央値で見る
    near = float(round(bpm))
    if near != bpm and abs(near - bpm) <= SNAP_MAX:
        bk = block_medians(grid_rows(env, fps, near, lead, thr))
        if len(bk) >= 6 and abs(flat_slope(bk, 60000.0 / near) * (bk[-1, 1] - bk[0, 1])) < SNAP_DRIFT_MS:
            bpm = near
    period_ms = 60000.0 / bpm
    # 無音追加は 8秒ごとの中央値の中央値で合わせる（1拍ごとの中央値は、16分ずれた打点の多い曲で定まらない）。
    # 段差がある曲では、曲の長い方の部分に合う
    for _ in range(2):
        rows = grid_rows(env, fps, bpm, lead, thr)
        bk = block_medians(rows)
        lead = (lead - float(np.median(bk[:, 2] if len(bk) else rows[:, 2]))) % period_ms
    rows = grid_rows(env, fps, bpm, lead, thr)
    resid = rows[:, 2] - np.median(rows[:, 2])
    bk = block_medians(rows)
    steps = find_steps(bk, period_ms)
    seg = np.searchsorted([s["sec"] for s in steps], bk[:, 0], side="right") if len(bk) else []
    bdev = np.concatenate([bk[seg == g, 2] - np.median(bk[seg == g, 2]) for g in np.unique(seg)]) if len(bk) else [0]
    block_mad = float(np.median(np.abs(bdev)))
    # 裏拍の疑い: 6秒ごとのずれの中央値が、半拍離れた所に集まる区間の割合
    half = period_ms / 2
    blk = []
    for s in np.arange(0, rows[-1, 1] + 6, 6):
        m = (rows[:, 1] >= s) & (rows[:, 1] < s + 6)
        if m.sum() >= 3:
            blk.append(np.median(rows[m, 2]))
    blk = np.array(blk)
    offbeat = float((np.abs(np.abs(blk - np.median(rows[:, 2])) - half) < half * 0.3).mean()) if len(blk) else 0.0
    # 低い音（キック・ベース）が一番よく乗る位置が、半拍ずれた方を指す数（3本中）
    low_votes = 0
    for le in (low or []):
        d = (best_lead(_flatten(np.asarray(le, float), fps), fps, bpm) - lead + half) % period_ms - half
        low_votes += abs(abs(d) - half) < period_ms * 0.15
    # 打点の強さの山は、耳で合わせた拍より少し遅く出る（立ち上がりの緩やかな楽器のため）ので、その分 目盛りを早める
    lead = (lead + LEAD_BIAS_MS) % period_ms
    return {"bpm": round(bpm, 3), "raw_bpm": round(raw_bpm, 3), "lead_ms": round(lead, 1),
            "alt_lead_ms": round((lead + half) % period_ms, 1), "low_offbeat": bool(low_votes >= 2), "steps": steps,
            "family": round(fam, 2), "alt": alt, "slope_sig": bool(significant), "slope": round(float(slope), 4),
            "resid_mad_ms": round(float(np.median(np.abs(resid))), 1), "block_mad_ms": round(block_mad, 1),
            "offbeat_ratio": round(offbeat, 2),
            "drift_pct": round(drift_pct, 2), "drift": [(round(t, 1), round(b, 2)) for t, b in drift],
            "n_beats": int(len(rows))}


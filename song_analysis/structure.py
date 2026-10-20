"""曲の構成（区切りと、同じ・似ている区間のグループ・セクション・名前）を解析する。

本体（serve.py の /__analysis/structure）と、開発用のコマンド tools/analyze_structure.py の両方が使う。
（2026-10-19 に tools/analyze_structure.py から移した。計算は変えていない。報告の HTML・答え合わせ・.nlmf の読み込みは tools 側）

仕組み（詳しくは tools/README.md の「曲の構成の解析」）:
 1. 拍の目盛りの4分の1拍ごとに、音色（MFCC）と歌の音域の音の高さ（CQT の C4〜C6）を測る。
    目盛りは TempoMap（BPM・無音追加・テンポパート・Music の配置）か、NLM が渡す「1/4拍ごとの元の音源の秒」（measure_at）。
 2. 「似ている所のつながり」で曲を分ける方法（ラプラシアン分割、McFee & Ellis 2014）をグループ数 4〜12 で
    9回行い、区切りは多数決、グループは「同じグループになった回数の割合」で決める（曲ごとに合う数が違うため）。
    比べる幅などは「1単位」（BPM 84 なら1拍、BPM 119 以上なら2拍）で決める。
 3. 似ている長い区間どうしを重ね、同じ所と違う所の境目で両方を分け直す（1番と2番で後半だけ同じ、など）。
 4. 2 の多数決で隣どうしの同じグループをまとめ、最後に「多数決」と「区間どうしを重ねた時の似ている度合い」の
    幾何平均でグループに分ける。表に出す「似ている度合い」は、重ねた時の値（1単位ぶんの流れごとに比べた平均）。
    グループの他のどの区間とも重ねた度合いが低い区間は、そのグループから外す（member_check）。
 5. 同じグループのフレーズが2〜3回続いて1本につながった区間は、回数ぶんに分ける（split_repeats）。
 6. セクションの段（build_sections）: 細かい区切りのうち、同じ並びで繰り返す組（例 B C B C）をまとめ（1つ20秒まで）、
    番号は中身（細かいグループの割合）で付ける。相手の無いセクションが続く所どうしは、まとめた全体でも比べる
    （同じパートが1番と2番で違う割れ方をした時）。1回しか出ない短いセクションが続く所は1つにまとめる。
    サビの候補は、2回以上出るセクションのうち長さ×音の大きさが一番大きいもの（中身の割合だけの緩い仲間で数える）。
 7. 名前の推測（name_sections）: セクションに仮の名前（イントロ/Aメロ/Bメロ/サビ/間奏/Cメロ/アウトロ）を並び方から付ける。
"""
import collections

import numpy as np
import scipy.linalg
import scipy.ndimage
import scipy.sparse.csgraph
from sklearn.cluster import KMeans


SR = 22050
HOP = 256
SUB = 4                  # 1拍を何コマに分けて測るか
VOCAL = (24, 48)         # CQT（C2 から半音72本）のうち C4〜C6 ＝歌の音域
K_RANGE = range(4, 13)   # ラプラシアン分割のグループ数（多数決に使う）
BOUND_VOTE = 0.4         # 区切りにする多数決の割合
SAME = 0.5               # 隣どうしをまとめる時: 同じグループにする多数決の割合（9回のうち半分以上）
MIX_SAME = 0.4           # 最後のグループ分け: 多数決と重ねた度合いの幾何平均のしきい値（2曲で 0.35〜0.5 は結果がほぼ同じ）
MEMBER_MIN = 0.40        # グループの確認: 他のどの区間ともこれに届かない区間はそのグループから外す
SECTION_MAX_SEC = 20     # セクションの段: 1つにまとめる長さの上限（秒）。24秒だと Aメロ＋Bメロ・イントロ＋次 までつながった
SECTION_SAME = 0.6       # セクションの段: 中の細かいグループの割合（長さで重みづけ）がこれ以上同じで、
SECTION_SIM = 0.45       # かつ並び順どおりに重ねた似ている度合いがこれ以上で、
SECTION_LEN_RATIO = 0.75 # かつ長さの比がこれ以上なら同じ番号（同じ部品の別の Aメロ＝長さ0.6倍、が同じ番号になっていた）
REPEAT_MIN_SEC = 8       # 繰り返しを分ける時、元にするフレーズの最短の長さ（秒）。これより短い動機の繰り返しは分けない
PREFIX_SIM = 0.5         # 長い区間の頭の1回分だけがこれ以上似ていれば、頭とそれ以外に分ける
UNIQUE_PIECE_SEC = 12    # 1回しか出ない短いセクション（これ未満の秒）が続く所は1つにまとめる。10秒だとある曲の
                         # Dメロ（1つのパート）の最後の10.4秒の区間が残った。1番の頭だけの Aメロ（21秒）等はつなげない
UNIQUE_MAX_SEC = 30      # ただし、まとめた長さはこの秒まで（45秒だと、間奏から2番の Aメロ・次の間奏までまとまった曲があった）
NAME_OUTRO_SEC = 30      # 名前の推測: 最後のサビより後で アウトロ にするのは曲末からこの秒まで
NAME_INTRO_SEC = 25      # 名前の推測: イントロにする頭のセクションの長さの上限（秒）
NAME_A_PART = 0.6        # 名前の推測: サビの前の歌のかたまりの、前からこの割合を Aメロ、残りを Bメロ
RUN_MAX_SEC = 20         # 1回しか出ないセクションが続く所どうしを、まとめた全体で比べる時の長さの上限（秒）
LONG = 20                # 重ねて分け直す対象の長さ（単位）
UNIT_SEC = 60 / 84       # 1単位の目安の秒（BPM 84 の1拍）。1単位はこれに一番近い 1・2・4 拍にする


def unit_scale(bpm):
    """1単位の拍数。BPM 84 の曲は1拍、BPM 119〜238 の曲は2拍（速い曲で拍のまま比べると、和音が変わるたびに
    区切って細切れになった。曲B＝BPM 129 で区間63個→30個）。"""
    return 2.0 ** max(0, round(np.log2(bpm * UNIT_SEC / 60)))


# ---- 拍と秒の対応（editor-app.js の beatToTimeTM / audioPosAtBeat と同じ計算） ----

class TempoMap:
    def __init__(self, bpm, parts=(), song_off=0.0, music_beat=0.0, music_segs=None):
        self.bpm = bpm
        self.parts = sorted(parts)          # [(拍, BPM)]
        self.song_off = song_off            # songNode.offset（0以下の秒。無音追加 = -song_off）
        self.music_beat = music_beat
        self.music_segs = music_segs        # [{beat, off, dur}]（Musicを分割・トリムした時だけ）

    def t(self, b):
        """拍 → 曲頭（拍0）からの秒。"""
        bb, bpm, tt = 0.0, self.bpm, 0.0
        for pb, pbpm in self.parts:
            if pb >= b:
                break
            tt += (pb - bb) * 60 / bpm
            bb, bpm = pb, pbpm
        return tt + (b - bb) * 60 / bpm

    def b(self, tm):
        """秒 → 拍（t の逆）。"""
        bb, bpm, tt = 0.0, self.bpm, 0.0
        for pb, pbpm in self.parts:
            seg = (pb - bb) * 60 / bpm
            if tt + seg > tm:
                break
            tt += seg
            bb, bpm = pb, pbpm
        return bb + (tm - tt) * bpm / 60

    def segs(self, dur):
        return self.music_segs or [{"beat": self.music_beat, "off": 0.0, "dur": max(0.0, dur - self.song_off)}]

    def audio_at(self, b, dur):
        """拍 → 元の音源の秒。その拍に音が無ければ None。"""
        tt = self.t(b)
        for sg in self.segs(dur):
            rel = tt - self.t(sg["beat"])
            if 0 <= rel < sg["dur"]:
                p = self.song_off + sg["off"] + rel
                return p if 0 <= p < dur else None
        return None

    def end_beat(self, dur):
        return max(self.b(self.t(sg["beat"]) + sg["dur"]) for sg in self.segs(dur))


# ---- 特徴 ----

def z(X):
    return (X - X.mean(1, keepdims=True)) / (X.std(1, keepdims=True) + 1e-9)


def unit(X):
    return X / (np.linalg.norm(X, axis=0, keepdims=True) + 1e-9)


def stack(X, n):
    """コマ t に t-n/2 .. t+n/2-1 を積む（前後の流れを含めて比べるため）。"""
    if n <= 1:
        return X
    h = n // 2
    Xp = np.concatenate([np.repeat(X[:, :1], h, 1), X, np.repeat(X[:, -1:], h, 1)], 1)
    return np.concatenate([Xp[:, k:k + X.shape[1]] for k in range(n)], 0)


def load_audio(path):
    """音源を読む（解析の音の形: SR・モノラル）。戻り値は (音, SR)"""
    import librosa
    return librosa.load(path, sr=SR, mono=True)


def features(y, sr, at, ends, progress=None):
    """1/4拍のコマごとの特徴。at[i]＝コマ i の頭の元の音源の秒（NaN＝音が無い）、ends[i]＝終わりの秒。
    progress: 進み具合（0〜1）を受け取る関数（serve.py の解析の仕事が、取り消しの確認にも使う）"""
    import librosa
    tick = progress or (lambda f: None)
    n = len(at)
    yh = librosa.effects.harmonic(y)
    tick(0.45)
    cq = librosa.amplitude_to_db(np.abs(librosa.cqt(yh, sr=sr, hop_length=HOP, fmin=librosa.note_to_hz("C2"),
                                                    n_bins=72, bins_per_octave=12)), ref=np.max)
    tick(0.8)
    mf = librosa.feature.mfcc(y=y, sr=sr, hop_length=HOP, n_mfcc=20)
    rms = librosa.feature.rms(y=y, hop_length=HOP)[0]
    nf = cq.shape[1]
    CQ = np.full((72, n), cq.min()); M = np.zeros((20, n)); E = np.zeros(n)
    for i in range(n):
        a = at[i]
        if np.isnan(a):
            continue
        e = ends[i]
        f0 = min(int(a * sr / HOP), nf - 1); f1 = min(max(int(e * sr / HOP), f0 + 1), nf)
        CQ[:, i] = cq[:, f0:f1].mean(1); M[:, i] = mf[:, f0:f1].mean(1); E[i] = rms[f0:f1].mean()
    tick(1.0)
    return {"CQ": CQ, "M": M, "E": E, "at": np.asarray(at, float), "dur": len(y) / sr, "n": n}


def measure(path, tm, y=None, progress=None):
    """TempoMap の目盛りで特徴を測る（tools/analyze_structure.py・調整用のスクリプト）。y は読み込み済みの音（無ければ path を読む）"""
    if y is None:
        y, _ = load_audio(path)
    sr = SR
    dur = len(y) / sr
    n = int(tm.end_beat(dur) * SUB)
    grid = np.arange(n + 1) / SUB
    at = np.full(n, np.nan); ends = np.full(n, np.nan)
    for i in range(n):
        a = tm.audio_at(grid[i], dur)
        if a is None:
            continue
        at[i] = a
        ends[i] = a + tm.t(grid[i + 1]) - tm.t(grid[i])
    return features(y, sr, at, ends, progress)


SNAP_TOL = 0.006   # NLM の目盛りを TempoMap の式で作り直す時に、同じ目盛りとみなすずれ（画面の秒は 10ms に丸めることがある）


def grid_ends(at, bpm, sub=SUB):
    """コマの終わりの秒（nlm_grid で作り直せない目盛り用）。次のコマへの間隔が、その前に使った間隔の 0.4〜2.5 倍なら
    次のコマの頭まで。そうでない所（音の無い所の手前・Music の切り貼りの継ぎ目など）は前に使った間隔（最初は BPM の 1/sub 拍）"""
    at = np.asarray(at, float)
    n = len(at)
    ends = np.full(n, np.nan)
    ref = 60.0 / bpm / sub
    for i in range(n):
        a = at[i]
        if np.isnan(a):
            continue
        d = at[i + 1] - a if i + 1 < n else np.nan
        if np.isfinite(d) and 0.4 * ref <= d <= 2.5 * ref:
            ref = d
        ends[i] = a + ref
    return ends


def nlm_grid(at, bpm, lead_ms=None, dur=None):
    """NLM が渡す目盛り（拍 0, 1/SUB, 2/SUB, … ごとの元の音源の秒。None＝音が無い）→ (コマの頭の秒, 終わりの秒)。
    コマの境目がフレームの境目にちょうど乗る曲が多く（BPM 84 の 1/4 拍は 15.38… フレームで、無音追加しだいで整数になる）、
    秒の最後の桁の違い1つでフレームが1つずれ、区切りが変わることがある（試した曲で拍 160.25 → 160.0）。そこで、
    テンポが一定で Music を切っていない目盛り（全部の秒が「BPM の目盛り＋一定のずれ」に SNAP_TOL 以内で乗る）は、
    tools/analyze_structure.py（TempoMap）と同じ式で秒を作り直す＝コマンドと同じ結果になる。ずれは無音追加
    （-lead_ms/1000）に合えばそれを使う。そうでない目盛り（テンポパート・Music の切り貼り）は渡された秒のまま（grid_ends）。
    音源の外（負・曲の長さ dur 以上）の秒は音が無い扱い（TempoMap.audio_at と同じ）"""
    a = np.array([np.nan if v is None else float(v) for v in at], float)
    n = len(a)
    ok = np.isfinite(a)
    T = (np.arange(n + 1) / SUB) * 60 / bpm   # TempoMap.t（テンポパートなし）と同じ式・同じ順の計算
    if ok.sum() >= 2:
        c = a[ok] - T[:n][ok]
        mid = float(np.median(c))
        if float(np.max(np.abs(c - mid))) <= SNAP_TOL:
            so = mid
            if lead_ms is not None and np.isfinite(lead_ms) and abs(-lead_ms / 1000 - mid) <= SNAP_TOL:
                so = -lead_ms / 1000            # TempoMap.song_off（--lead-ms・プロジェクトの offset と同じ値）
            a[ok] = so + T[:n][ok]              # TempoMap.audio_at: (song_off + 0.0) + (t(b) - t(0))
            if dur is not None:
                ok &= (a >= 0) & (a < dur)
            a[~ok] = np.nan
            ends = np.where(ok, a + T[1:] - T[:n], np.nan)   # measure と同じ: a + t(次のコマ) - t(このコマ)
            return a, ends
    if dur is not None:
        ok &= (a >= 0) & (a < dur)
    a[~ok] = np.nan
    return a, grid_ends(a, bpm)


def measure_at(path, at, bpm, lead_ms=None, y=None, progress=None):
    """NLM が渡す目盛りで特徴を測る（serve.py の /__analysis/structure）。at は NLM の拍 0, 1/SUB, 2/SUB, … ごとの
    元の音源の秒（None・NaN＝その拍に音が無い）。テンポパート・Music の配置・無音追加は NLM 側で反映済み（nlm_grid）"""
    if y is None:
        y, _ = load_audio(path)
    a, ends = nlm_grid(at, bpm, lead_ms, len(y) / SR)
    return features(y, SR, a, ends, progress)


# ---- 区切りとグループ ----

def laplacian(Frec, Fpath, k, kappa=0.03, med=4 * SUB + 1):
    """McFee & Ellis (2014) のラプラシアン分割。各コマのグループ番号を返す。"""
    n = Frec.shape[1]
    S = Frec.T @ Frec
    kk = max(2, int(kappa * n))
    th = np.sort(S, axis=1)[:, -kk - 1][:, None]
    R = np.where((S >= th) & (S >= th.T), S, 0.0)
    np.fill_diagonal(R, 0)
    dp = np.sum(np.diff(Fpath, axis=1) ** 2, axis=0)
    ps = np.exp(-dp / (np.median(dp) + 1e-9))
    Rp = np.diag(ps, 1) + np.diag(ps, -1)
    dpth, drec = Rp.sum(1), R.sum(1)
    mu = dpth.dot(dpth + drec) / np.sum((dpth + drec) ** 2)
    L = scipy.sparse.csgraph.laplacian(mu * R + (1 - mu) * Rp, normed=True)
    _, V = scipy.linalg.eigh(L)
    V = scipy.ndimage.median_filter(V, size=(med, 1))
    Y = V[:, :k] / (np.cumsum(V ** 2, axis=1)[:, k - 1:k] ** 0.5 + 1e-9)
    return KMeans(n_clusters=k, n_init=10, random_state=0).fit_predict(Y)


class Analyzer:
    def __init__(self, F, scale=1.0, bpm=120.0, progress=None):
        """scale: 「1単位」が何拍か。比べる幅・ならす幅・区間の最短の長さはこの単位で決める
        （速い曲で拍のままだと、和音が変わるたびに区切って細切れになるため。main の unit_scale）。
        bpm: 秒で決める所（繰り返しを分ける時のフレーズの長さ）に使う。
        progress: 多数決の各回の後に、終わった割合（0〜1）で呼ぶ関数（serve.py の解析の仕事の進み具合）。"""
        self.U = SUB * scale                                # 1単位のコマ数
        self.fps = SUB * bpm / 60                           # 1秒のコマ数
        self.CQ, self.M, self.E = F["CQ"], F["M"], F["E"]
        db = 20 * np.log10(self.E + 1e-6)
        live = db > db.max() - 30
        self.lo = int(np.argmax(live)); self.hi = len(live) - int(np.argmax(live[::-1]))
        sl = slice(self.lo, self.hi)
        Fm = unit(z(self.M[1:, sl])); Fv = unit(z(self.CQ[VOCAL[0]:VOCAL[1], sl]))
        X = np.vstack([Fm, Fv])
        self.n = X.shape[1]
        Fs = unit(stack(X, self.f(1)))
        self.S = Fs.T @ Fs                                  # 1単位ぶんの流れで比べた、コマどうしの似ている度合い
        Frec = unit(stack(X, self.f(4)))
        votes = np.zeros(self.n); self.CO = np.zeros((self.n, self.n))
        for j, k in enumerate(K_RANGE):
            lab = laplacian(Frec, Fm, k, med=self.f(4) | 1)
            v = np.zeros(self.n); v[1:][lab[1:] != lab[:-1]] = 1
            votes += scipy.ndimage.gaussian_filter1d(v, self.U / 2) * np.sqrt(2 * np.pi) * (self.U / 2)
            self.CO += lab[:, None] == lab[None, :]
            if progress:
                progress((j + 1) / len(K_RANGE))
        self.votes = votes / len(K_RANGE); self.CO /= len(K_RANGE)

    def f(self, units):
        """単位の数 → コマ数。"""
        return max(1, int(round(units * self.U)))

    def boundaries(self):
        out = []
        for i in np.argsort(-self.votes):
            if self.votes[i] < BOUND_VOTE:
                break
            if i < self.f(2) or i > self.n - self.f(2):
                continue
            if all(abs(i - j) >= self.f(2) for j in out):
                out.append(int(i))
        return sorted(out)

    def align(self, a, b, lag=None):
        """区間 a と b を、b の先頭を ±lag コマずらして重ねる。(平均, ずらし, 1コマごとの値) の平均最大のもの。"""
        lag = self.f(1) if lag is None else lag
        best = (-9.0, 0, None)
        for dl in range(-lag, lag + 1):
            b0 = b[0] + dl
            m = min(a[1] - a[0], b[1] - b[0], self.n - b0)
            if b0 < 0 or m <= 0:
                continue
            p = self.S[np.arange(a[0], a[0] + m), np.arange(b0, b0 + m)]
            if p.mean() > best[0]:
                best = (float(p.mean()), dl, p)
        return best

    def refine(self, segs):
        """同じグループらしい長い区間の組を重ね、「同じ所」と「違う所」の境目で両方を分ける。"""
        side, W = self.f(6), self.f(2)
        for _ in range(50):
            hit = None
            for i in range(len(segs)):
                for j in range(i + 1, len(segs)):
                    a, b = segs[i], segs[j]
                    if max(a[1] - a[0], b[1] - b[0]) < self.f(LONG) or self.CO[a[0]:a[1], b[0]:b[1]].mean() < 0.4:
                        continue
                    _, dl, p = self.align(a, b, self.f(2))
                    if p is None or len(p) < 2 * side:
                        continue
                    cs = np.r_[0, np.cumsum(p)]
                    gaps = [((cs[-1] - cs[c]) / (len(p) - c) - cs[c] / c, c) for c in range(side, len(p) - side + 1)]
                    g, c = max(gaps, key=lambda x: abs(x[0]))
                    l, r = cs[c] / c, (cs[-1] - cs[c]) / (len(p) - c)
                    if abs(g) < 0.25 or min(l, r) >= 0.3:
                        continue
                    # 全体で一番差の大きい所の近くで、前後2単位の差が一番急な所を境目にする
                    sg = 1 if g > 0 else -1
                    cands = range(max(side, c - self.f(6)), min(len(p) - side, c + self.f(6)) + 1)
                    c = max(cands, key=lambda q: sg * (p[q:q + W].mean() - p[q - W:q].mean()))
                    if not (a[0] < a[0] + c < a[1] and b[0] < b[0] + dl + c < b[1]):
                        continue
                    hit = (i, j, [(a[0], a[0] + c), (a[0] + c, a[1]), (b[0], b[0] + dl + c), (b[0] + dl + c, b[1])])
                    break
                if hit:
                    break
            if not hit:
                return segs
            segs = sorted([s for k, s in enumerate(segs) if k not in hit[:2]] + hit[2])
        return segs

    def group(self, segs, thr=SAME, mix=False):
        """平均連結の階層クラスタリング。グループ番号は最初に出た順。K は「重ねた時の似ている度合い」（表示にも使う）。
        mix=False: グループ数 4〜12 の各回で同じグループになった割合（多数決）だけでまとめる。
        mix=True : 多数決と重ねた度合いの幾何平均でまとめる（多数決だけだと、楽器の雰囲気が近い別のパート
                   ＝曲Bの Bメロとサビの後半、を同じグループにしてしまったため）。
        （重ねた度合いだけでまとめると、しきい値で結果が大きく揺れた）"""
        n = len(segs)
        C = np.array([[self.CO[a:e, a2:e2].mean() for (a2, e2) in segs] for (a, e) in segs])
        K = np.eye(n)
        for i in range(n):
            for j in range(i + 1, n):
                K[i, j] = K[j, i] = (self.align(segs[i], segs[j])[0] + self.align(segs[j], segs[i])[0]) / 2
        M = np.sqrt(np.clip(C, 0, 1) * np.clip(K, 0, 1)) if mix else C
        cl = [[i] for i in range(n)]
        while len(cl) > 1:
            v, i, j = max((np.mean([M[x, y] for x in cl[i] for y in cl[j]]), i, j)
                          for i in range(len(cl)) for j in range(i + 1, len(cl)))
            if v < thr:
                break
            cl[i] += cl[j]; del cl[j]
        lab = np.zeros(n, int)
        for g, c in enumerate(sorted(cl, key=min)):
            lab[c] = g
        return lab, K

    def run(self):
        b = self.boundaries()
        segs = self.refine(list(zip([0] + b, b + [self.n])))
        lab, _ = self.group(segs)
        # 隣り合う同じグループの区間は1つにまとめる（同じフレーズの中の小さな繰り返しで細切れになるため）
        merged = [segs[0]]
        for s, p, q in zip(segs[1:], lab[:-1], lab[1:]):
            if p == q:
                merged[-1] = (merged[-1][0], s[1])
            else:
                merged.append(s)
        lab, K = self.group(merged, MIX_SAME, mix=True)
        lab = member_check(lab, K)
        merged, lab = self.split_repeats(merged, lab)
        if len(merged) != len(K):
            _, K = self.group(merged, MIX_SAME, mix=True)   # 分けた区間の分の「似ている度合い」を出し直す（グループはそのまま）
        return [(a + self.lo, e + self.lo) for a, e in merged], lab, K

    def section_sim(self, s1, s2):
        """2つの区間（run() が返すのと同じ絶対のコマ）を並び順どおりに重ねた似ている度合い（両方向の大きい方）。"""
        l1 = (max(0, s1[0] - self.lo), min(self.n, s1[1] - self.lo))
        l2 = (max(0, s2[0] - self.lo), min(self.n, s2[1] - self.lo))
        if l1[1] <= l1[0] or l2[1] <= l2[0]:
            return 0.0
        return max(self.align(l1, l2)[0], self.align(l2, l1)[0])

    def split_repeats(self, segs, lab):
        """同じグループのフレーズが2〜3回続いて1本につながった区間を、回数ぶんに分ける。
        隣り合う同じグループをつなげる処理のため、例えばサビが2回続く所が1本の長い区間になり、1回分のサビと形が変わって
        セクションの段で別の番号になっていた（利用者が耳で確かめた: その所は「同じサビが2回」が正しい）。
        分けるのは、同じグループの他の区間（REPEAT_MIN_SEC 秒以上＝フレーズの長さ）のちょうど 2〜3 倍の長さで、
        分けた各部分をその区間と重ねてもよく似ている時だけ。短い動機が何回も続く区間（間奏のメロディー等）は分けない
        （利用者の判断: そういう区間は1つのパートとして正しい）。"""
        out_s, out_l = [], []
        lab = list(lab)
        nxt = max(lab) + 1
        for i, (a, b) in enumerate(segs):
            L = b - a
            best = None
            prefix = None    # 全部は繰り返しでなくても、頭の1回分だけが他の区間とよく似ている時の切り方
            for j, (a2, b2) in enumerate(segs):
                Lr = b2 - a2
                if j == i or lab[j] != lab[i] or Lr < REPEAT_MIN_SEC * self.fps:
                    continue
                ratio = L / Lr                       # 相手（1回分）が何回入るか
                n = 2 if 1.6 <= ratio < 2.6 else 3 if 2.6 <= ratio <= 3.4 else 0
                if not n:
                    continue
                # 2回目以降の頭は、前の頭から相手の長さの 0.75〜1.35 倍の範囲で、相手と一番よく重なる所にする
                # （等分に切ると2回目の頭がずれた。ある曲の2回続くサビは1回目が1番のサビより7拍長く、±数拍では見つからなかった）
                cuts, sims = [a], [self.align((a, a + Lr), (a2, b2))[0]]
                for k in range(1, n):
                    cands = [c for c in range(cuts[-1] + int(0.75 * Lr), cuts[-1] + int(1.35 * Lr) + 1)
                             if c + int(0.75 * Lr) <= b]
                    if not cands:
                        break
                    c = max(cands, key=lambda c: self.align((c, min(c + Lr, b)), (a2, b2))[0])
                    cuts.append(c); sims.append(self.align((c, min(c + Lr, b)), (a2, b2))[0])
                if len(cuts) == n and min(sims) >= MEMBER_MIN and (best is None or np.mean(sims) > best[0]):
                    best = (float(np.mean(sims)), cuts)
                # 頭だけ: 頭の1回分が PREFIX_SIM 以上似ていれば、相手と同じ長さの所で頭とそれ以外に分ける。それ以外は
                # 新しいグループ。ある曲で、1番の「Aメロ＋別の Aメロ」が1本につながり、2番の Aメロ1回分と長さが合わず
                # 別物になっていた（全部が繰り返しではないので、上の分け方では分けられない）
                if sims[0] >= PREFIX_SIM and (prefix is None or sims[0] > prefix[0]):
                    prefix = (sims[0], a + Lr)
            if best:
                cuts = best[1] + [b]
                for k in range(len(cuts) - 1):
                    out_s.append((cuts[k], cuts[k + 1])); out_l.append(lab[i])
            elif prefix:
                out_s += [(a, prefix[1]), (prefix[1], b)]; out_l += [lab[i], nxt]; nxt += 1
            else:
                out_s.append((a, b)); out_l.append(lab[i])
        order = {}
        return out_s, np.array([order.setdefault(x, len(order)) for x in out_l])


def member_check(lab, K, tau=MEMBER_MIN, min_size=3):
    """グループの他のどの区間とも、重ねた度合いが tau に届かない区間をそのグループから外す（1回だけの区間にする）。
    多数決は楽器の雰囲気が近いだけの区間も強く同じグループにするため（ある曲で、サビの後半のグループに Bメロ・Cメロの
    一部が混ざっていた。利用者が耳で確かめて「本当の D と違う」とした3つの区間が、ちょうどこの確認で外れる）。
    2個だけのグループは確かめない（長さの違う区間どうしだと重ねた度合いが低く出やすく、正しい組まで外れた）。"""
    lab = list(lab)
    nxt = max(lab) + 1
    changed = True
    while changed:
        changed = False
        for g in sorted(set(lab)):
            idx = [i for i in range(len(lab)) if lab[i] == g]
            if len(idx) < min_size:
                continue
            worst = min(idx, key=lambda i: max(K[i, j] for j in idx if j != i))
            if max(K[worst, j] for j in idx if j != worst) < tau:
                lab[worst] = nxt; nxt += 1; changed = True
    order = {}
    return np.array([order.setdefault(x, len(order)) for x in lab])


def sections_from(segs, lab, max_frames):
    """セクションの段: 細かい区間の、隣り合う2つのグループの組のうち、重ならずに2回以上出てくる物を1つにまとめる、を
    くり返す（同じ並びで繰り返す区間の組＝1つのフレーズ・セクション）。まとめた長さが max_frames を超える組はまとめない。
    最後に同じ物が続く所もまとめる。返り値は (区間, セクションの番号)。番号が同じ＝同じ並びのセクション。"""
    syms = [(int(x),) for x in lab]
    spans = list(segs)
    while True:
        cnt = {}
        for i in range(len(syms) - 1):
            key = (syms[i], syms[i + 1])
            if key[0] != key[1] and spans[i + 1][1] - spans[i][0] <= max_frames:
                cnt.setdefault(key, []).append(i)
        best = None
        for key, pos in cnt.items():
            nonov = []
            for p in pos:
                if not nonov or p > nonov[-1] + 1:
                    nonov.append(p)
            if len(nonov) >= 2 and (best is None or len(nonov) > len(best[1])):
                best = (key, nonov)
        if not best:
            break
        key, pos = best
        for p in reversed(pos):
            syms[p:p + 2] = [key[0] + key[1]]
            spans[p:p + 2] = [(spans[p][0], spans[p + 1][1])]
    out_s, out_l = [], []
    for s, sp in zip(syms, spans):
        if out_l and out_l[-1] == s:
            out_s[-1] = (out_s[-1][0], sp[1])
        else:
            out_s.append(sp); out_l.append(s)
    names = {}
    return out_s, [names.setdefault(x, len(names)) for x in out_l]


def build_sections(segs, lab, fps, E=None, sim=None):
    """セクションの段を作る。返り値は (区間, 番号, サビの候補の番号の集まり)。sim(区間1, 区間2) は並び順どおりに
    重ねた時の似ている度合い（Analyzer.section_sim）。
    1. sections_from で、同じ並びで繰り返す組をまとめる（1つ SECTION_MAX_SEC 秒まで）。
    2. 番号は、まとめ方（どの組がまとまったか）ではなく中身で決める: 中の細かいグループの割合（長さで重みづけ）が
       SECTION_SAME 以上同じ、並び順どおりに重ねて SECTION_SIM 以上似ていて、長さの比が SECTION_LEN_RATIO 以上なら
       同じ番号（「A」と「A＋短いB」が別の番号になっていた。割合だけだと、同じ部品を違う順に並べた別の Aメロまで
       同じ番号になった）。似ている組でつながった仲間は全部同じ番号。
       相手の無いセクションが続く所どうしは、まとめた全体でも比べる（join_runs。同じパートの割れ方が違う時）。
    3. 1回しか出ない短い（UNIQUE_PIECE_SEC 秒未満）セクションが続く所は1つにまとめる（UNIQUE_MAX_SEC 秒まで）。
       繰り返しの無い部分は細かく割れたままだった（利用者の判断: 1回しか出ない所は1つのパートとしてよい）。
    4. サビの候補: 2回以上出る番号のうち、合計の長さ×（1＋0.15×音の大きさ[曲の中央値からの dB]）が一番大きいもの
       （細かいグループの合計の長さで選ぶと、Aメロ2回分がつながった長い区間などが選ばれ、ある歌手のアルバム38曲で15曲しか
       当たらなかった。セクションで数えて音の大きさを加えると22曲）。"""
    secs, _ = sections_from(segs, lab, int(SECTION_MAX_SEC * fps))

    def content(a, b):
        c = {}
        for (s0, s1), l in zip(segs, lab):
            o = min(b, s1) - max(a, s0)
            if o > 0:
                c[int(l)] = c.get(int(l), 0) + o
        return c

    def same(c1, c2):
        keys = set(c1) | set(c2)
        mx = sum(max(c1.get(k, 0), c2.get(k, 0)) for k in keys)
        return sum(min(c1.get(k, 0), c2.get(k, 0)) for k in keys) / max(mx, 1) >= SECTION_SAME

    def number(secs):
        """似ている組（中身の割合・並び順どおり・長さの3つとも満たす）を全部調べ、つながった仲間に同じ番号を付ける。
        （前から順に決めると、後ろに出る仲間を介してしかつながらない区間が別の番号になった）"""
        cs = [content(*sp) for sp in secs]
        par = list(range(len(secs)))

        def root(x):
            while par[x] != x:
                par[x] = par[par[x]]; x = par[x]
            return x
        for i in range(len(secs)):
            for j in range(i + 1, len(secs)):
                li, lj = secs[i][1] - secs[i][0], secs[j][1] - secs[j][0]
                if (min(li, lj) >= SECTION_LEN_RATIO * max(li, lj) and same(cs[i], cs[j])
                        and (sim is None or sim(secs[i], secs[j]) >= SECTION_SIM)):
                    par[root(j)] = root(i)
        return [root(i) for i in range(len(secs))]

    def join_runs(secs, num):
        """1回しか出ない番号のセクションが続く所どうしを比べ、まとめた全体が number と同じ3つの条件で似ていれば、
        それぞれを1つのセクションにまとめる（その後の number で同じ番号になる）。細かい区切りの割れ方が1番と2番で
        少し違うと、繰り返す組のまとめ方（sections_from）も変わり、同じパートが別々の小さいセクションに分かれて、
        どれも相手が無くなっていた（ある曲の Bメロ: 1番が2つ・2番が3つ。1番の前半の後ろ6拍だけが、サビの終わりと
        同じ細かいグループになっていた）。比べるのは、少なくとも片方が2つ以上のセクションの組（1つどうしは number で
        比べ済み）で、長さは RUN_MAX_SEC 秒まで。長い組から決め、3回目以降も同じ組となら仲間にする。"""
        cnt = {t: num.count(t) for t in set(num)}
        lim = RUN_MAX_SEC * fps
        subs = []
        for i in range(len(secs)):
            for j in range(i, len(secs)):
                if cnt[num[j]] != 1 or secs[j][1] - secs[i][0] > lim:
                    break
                subs.append((i, j))
        cont = {r: content(secs[r[0]][0], secs[r[1]][1]) for r in subs}
        cands = []
        for r1 in subs:
            for r2 in subs:
                if r2[0] <= r1[1] or (r1[0] == r1[1] and r2[0] == r2[1]):
                    continue
                sp1, sp2 = (secs[r1[0]][0], secs[r1[1]][1]), (secs[r2[0]][0], secs[r2[1]][1])
                l1, l2 = sp1[1] - sp1[0], sp2[1] - sp2[0]
                if min(l1, l2) < SECTION_LEN_RATIO * max(l1, l2) or not same(cont[r1], cont[r2]):
                    continue
                v = 1.0 if sim is None else sim(sp1, sp2)
                if v >= SECTION_SIM:
                    cands.append((l1 + l2, v, r1, r2))
        owner = {}    # セクションの位置 → まとめた組
        for _, _, r1, r2 in sorted(cands, reverse=True):
            if all(owner.get(x, r) == r for r in (r1, r2) for x in range(r[0], r[1] + 1)):
                for r in (r1, r2):
                    owner.update({x: r for x in range(r[0], r[1] + 1)})
        out, i = [], 0
        while i < len(secs):
            r = owner.get(i, (i, i))
            out.append((secs[r[0]][0], secs[r[1]][1])); i = r[1] + 1
        return out

    num = number(secs)
    joined = join_runs(secs, num)
    if len(joined) != len(secs):
        secs, num = joined, number(joined)
    # 1回しか出ない短いセクションが続く所をまとめる。「1回しか出ない」は、番号が1回だけで、かつ中の細かいグループの
    # 半分以上（長さ）が、このセクションの外にはほとんど出てこない（外の長さが中の半分未満）こと。番号は長さの違いで
    # 別になることがあり、それだけで判断すると、ある曲で2番の Aメロ（1番は Aメロ2回分で長さが違う）が間奏とまとめられた。
    # 外に少しでも出たら除く、だと、別の曲の Dメロ（中の1つのグループが後半に5拍だけ出る）がまとまらなかった
    fine_dur = {}
    for (s0, s1), l in zip(segs, lab):
        fine_dur[int(l)] = fine_dur.get(int(l), 0) + s1 - s0

    def only_here(a, b):
        inside = {}
        for (s0, s1), l in zip(segs, lab):
            o = min(b, s1) - max(a, s0)
            if o > 0:
                inside[int(l)] = inside.get(int(l), 0) + o
        tot = sum(inside.values())
        return sum(v for l, v in inside.items() if fine_dur[l] - v < 0.5 * v) >= 0.5 * max(tot, 1)

    cnt = {t: num.count(t) for t in set(num)}
    merged = []
    for (a, b), t in zip(secs, num):
        uniq = cnt[t] == 1 and (b - a) < UNIQUE_PIECE_SEC * fps and only_here(a, b)
        if uniq and merged and merged[-1][2] and b - merged[-1][0] <= UNIQUE_MAX_SEC * fps:
            merged[-1] = (merged[-1][0], b, True)
        else:
            merged.append((a, b, uniq))
    secs = [(a, b) for a, b, _ in merged]
    num = number(secs)
    order = {}
    num = [order.setdefault(t, len(order)) for t in num]
    chorus = set()
    if E is not None:
        # サビの候補は、表示の番号より緩い仲間（中身の割合だけ・前から順に）で選ぶ。表示の番号は並び順・長さも見て
        # 厳しく分けるので、落ちサビ・最後のサビ等の少し違うサビが別の番号になり、サビの番号の合計が減って別の物が
        # 選ばれた（38曲で 22→16 曲）。選ばれた仲間に入るセクションは、表示の番号が違っても全部サビの候補にする
        loose, mem = [], []
        for sp in secs:
            c = content(*sp)
            t = next((ti for ti, ms in enumerate(mem) if any(same(c, m) for m in ms)), None)
            if t is None:
                mem.append([c]); t = len(mem) - 1
            else:
                mem[t].append(c)
            loose.append(t)
        db = 20 * np.log10(np.asarray(E) + 1e-6)
        live = db > db.max() - 30
        ref = np.median(db[live]) if live.any() else 0.0
        stat = {}
        for (a, b), t in zip(secs, loose):
            v = stat.setdefault(t, [0, 0.0, 0])
            v[0] += b - a; v[1] += float(np.sum(db[a:b] - ref)); v[2] += 1
        rep = [t for t, v in stat.items() if v[2] >= 2]
        if rep:
            best = max(rep, key=lambda t: stat[t][0] * (1 + 0.15 * stat[t][1] / max(stat[t][0], 1)))
            chorus = {n for n, t in zip(num, loose) if t == best}
    return secs, num, chorus


# ---- 一覧にする ----

def label_name(g):
    return chr(ord("A") + g) if g < 26 else f"Z{g - 25}"


def build_result(ana, segs, lab, K, tm, F):
    rows = []
    for i, ((a, e), g) in enumerate(zip(segs, lab)):
        same = [j for j in range(len(segs)) if lab[j] == g and j != i]
        best = max(same, key=lambda j: K[i, j]) if same else None
        rows.append({"start": a / SUB, "end": e / SUB, "group": label_name(g), "count": len(same) + 1,
                     "best": None if best is None else segs[best][0] / SUB,
                     "sim": None if best is None else round(float(K[i, best]), 3)})
    # サビの候補: 2回以上出るグループのうち、合計の長さが一番長いもの（同じなら音が大きい方）
    db = 20 * np.log10(F["E"] + 1e-6)
    tot = {}
    for (a, e), g in zip(segs, lab):
        t_ = tot.setdefault(g, [0, 0.0, 0])
        t_[0] += e - a; t_[1] += db[a:e].sum(); t_[2] += 1
    rep = [g for g, v in tot.items() if v[2] >= 2]
    if not rep:
        return rows, []
    main_g = max(rep, key=lambda g: (tot[g][0], tot[g][1] / tot[g][0]))
    # サビのグループと交互に出るグループもサビの一部とみなす（曲A の「あ」と「あ2」など）。
    # 「交互」= 隣がサビのグループである回数（前後で数える）が出てくる回数の1.5倍以上。
    # 前か後ろの片側だけ（サビの直前に毎回来るパート・サビの後の間奏）は含めない。
    chorus = [main_g]
    for g in sorted(set(lab)):
        idx = [i for i in range(len(lab)) if lab[i] == g]
        adj = sum(int(i > 0 and lab[i - 1] == main_g) + int(i + 1 < len(lab) and lab[i + 1] == main_g) for i in idx)
        if g != main_g and adj >= 1.5 * len(idx):
            chorus.append(g)
    return rows, [label_name(g) for g in sorted(chorus)]


def section_rows(sec_segs, sec_lab, chorus=()):
    """セクションの段の一覧（S1, S2 …。番号が同じ＝同じ中身のセクション）。chorus はサビの候補の番号の集まり。"""
    cnt = {l: list(sec_lab).count(l) for l in set(sec_lab)}
    return [{"start": a / SUB, "end": e / SUB, "label": f"S{l + 1}", "count": cnt[l], "chorus": l in chorus}
            for (a, e), l in zip(sec_segs, sec_lab)]


def name_sections(rows, seg_rows=(), chorus_fine=(), bpm=120.0):
    """セクションの段（section_rows の一覧）に、仮の名前（イントロ/Aメロ/Bメロ/サビ/間奏/Cメロ/アウトロ）を決まりごとで付ける。
    作る人と遊ぶ人が同じ言葉で話すための目安で、利用者が番号（グループ）ごとに直す前提。歌の有無は見ていない。
    seg_rows・chorus_fine は細かい区切りの段の一覧（build_result）とサビの候補の細かいグループ（chorus_groups）。
    - サビ: サビの候補のセクションと、サビの細かいグループが半分以上を占めるセクション（★が1つの番号だけだと後半のサビを落とす）。
    - アウトロ: 最後のサビより後の、曲末の NAME_OUTRO_SEC 秒までの部分（それより前はまだ歌の区間とみなす）。
    - イントロ: 最初のサビより前の頭の部分（頭の1つと、続く1回だけの物。合わせて NAME_INTRO_SEC 秒まで・かたまりの最後は除く）。
      同じ番号が後で出たら 間奏。
    - サビの後のかたまり: 頭の1つが最初のかたまりの歌に出てこない番号なら 間奏（続けて付けると2番の歌まで 間奏 になった）。2回目のサビより後の1回だけの物は Cメロ。
      残りの歌の区間は、かたまりの中の時間の位置で Aメロ（前の NAME_A_PART）・Bメロ。
    - 同じ番号の物は多数決で同じ名前にそろえる（イントロ・アウトロ・サビは位置や中身で決まるのでそろえない）。"""
    n = len(rows)
    if not n:
        return []
    spb = 60.0 / bpm
    lab = [r["label"] for r in rows]
    cnt = collections.Counter(lab)
    dur = [(r["end"] - r["start"]) * spb for r in rows]
    names = [None] * n
    cf = set(chorus_fine)
    for i, r in enumerate(rows):
        cov = sum(max(0.0, min(r["end"], g["end"]) - max(r["start"], g["start"])) for g in seg_rows if g["group"] in cf)
        if r["chorus"] or cov >= 0.5 * (r["end"] - r["start"]):
            names[i] = "サビ"
    ch = [i for i in range(n) if names[i] == "サビ"]
    # アウトロ: 曲末から NAME_OUTRO_SEC 秒まで（最後のサビより後だけ）
    last = ch[-1] if ch else -1
    t = 0.0
    for i in range(n - 1, last, -1):
        if t + dur[i] > NAME_OUTRO_SEC and t > 0:
            break
        names[i] = "アウトロ"
        t += dur[i]
    # サビ・アウトロで区切ったかたまりごとに決める
    stops = [i for i in range(n) if names[i] in ("サビ", "アウトロ")]
    blocks, cur = [], []
    for i in range(n):
        if names[i] is None:
            cur.append(i)
        elif cur:
            blocks.append(cur)
            cur = []
    if cur:
        blocks.append(cur)
    intro_lab = set()        # イントロの番号（後で出たら 間奏）
    first_verse = set()
    for k, blk in enumerate(blocks):
        after_chorus = blk[0] > 0 and names[blk[0] - 1] == "サビ"
        nth = sum(1 for i in ch if i < blk[0])    # このかたまりより前のサビの数
        verse = []
        head = True            # かたまりの頭（イントロ・間奏の続く所）にいる間
        t_intro = 0.0
        intro_labs = set()
        for j, i in enumerate(blk):
            if (head and nth == 0 and j < len(blk) - 1 and t_intro + dur[i] <= NAME_INTRO_SEC
                    and (j == 0 or cnt[lab[i]] == 1)):
                names[i] = "イントロ"
                intro_labs.add(lab[i])
                t_intro += dur[i]
            elif lab[i] in intro_lab:
                names[i] = "間奏"
            elif j == 0 and after_chorus and lab[i] not in first_verse:
                names[i] = "間奏"
            elif nth >= 2 and cnt[lab[i]] == 1:
                names[i] = "Cメロ"
            else:
                verse.append(i)
                head = False
        intro_lab |= intro_labs
        if verse:
            t0 = rows[verse[0]]["start"]
            t1 = rows[verse[-1]]["end"]
            for i in verse:
                mid = (rows[i]["start"] + rows[i]["end"]) / 2
                names[i] = "Aメロ" if (mid - t0) < NAME_A_PART * (t1 - t0) or len(verse) == 1 else "Bメロ"
                if nth == 0:
                    first_verse.add(lab[i])
    # 同じ番号は多数決でそろえる
    keep = ("イントロ", "アウトロ", "サビ")
    votes = collections.defaultdict(collections.Counter)
    for i in range(n):
        if names[i] not in keep:
            votes[lab[i]][names[i]] += dur[i]
    for i in range(n):
        if names[i] not in keep and votes[lab[i]]:
            names[i] = votes[lab[i]].most_common(1)[0][0]
    return names


def chorus_groups(segs, lab, sec_segs, sec_lab, chorus):
    """サビの候補のセクションの中で、合計の長さの3割以上を占める細かいグループ（細かい段の表示用）。"""
    if not chorus:
        return []
    span = [(a, b) for (a, b), l in zip(sec_segs, sec_lab) if l in chorus]
    tot = sum(b - a for a, b in span)
    c = {}
    for (s0, s1), l in zip(segs, lab):
        for a, b in span:
            o = min(b, s1) - max(a, s0)
            if o > 0:
                c[int(l)] = c.get(int(l), 0) + o
    return [label_name(g) for g, v in sorted(c.items()) if v >= 0.3 * tot]


# ---- まとめて解析する（serve.py の /__analysis/structure。tools/analyze_structure.py の main と同じ順） ----

NAME_KEYS = {"イントロ": "intro", "Aメロ": "a", "Bメロ": "b", "サビ": "chorus", "間奏": "interlude", "Cメロ": "c",
             "アウトロ": "outro"}   # 名前の推測（name_sections）の種類。画面はこのキーで訳す


def analyze(F, bpm, unit=None, progress=None):
    """特徴（measure・measure_at の戻り値）から、細かい区切り・セクション・名前まで出す。
    戻り値: dict（rows＝細かい区切りの一覧・sections＝セクションの段の一覧（name 付き）・chorus＝サビの候補の細かいグループ・
    ana・segs・lab・K・sec_segs・sec_lab・scale）。progress は 0〜1"""
    tick = progress or (lambda f: None)
    scale = unit or unit_scale(bpm)   # テンポパートがあっても曲頭の BPM で決める
    ana = Analyzer(F, scale, bpm, progress=lambda f: tick(0.7 * f))
    segs, lab, K = ana.run()
    tick(0.85)
    rows, _ = build_result(ana, segs, lab, K, None, F)
    sec_segs, sec_lab, sec_chorus = build_sections(segs, lab, ana.fps, F["E"], ana.section_sim)
    sections = section_rows(sec_segs, sec_lab, sec_chorus)
    chorus = chorus_groups(segs, lab, sec_segs, sec_lab, sec_chorus)
    for sec, nm in zip(sections, name_sections(sections, rows, chorus, bpm)):
        sec["name"] = nm
    tick(1.0)
    return {"rows": rows, "sections": sections, "chorus": chorus, "ana": ana, "segs": segs, "lab": lab, "K": K,
            "sec_segs": sec_segs, "sec_lab": sec_lab, "scale": scale}


def result_json(res, version=1):
    """analyze の戻り値 → 画面へ返す形（拍は NLM の拍。tools の structure.json と同じ形＋名前の種類 nameKey）"""
    def num(v):
        return None if v is None else float(v)
    sections = [{"start": num(s["start"]), "end": num(s["end"]), "label": s["label"], "count": int(s["count"]),
                 "chorus": bool(s["chorus"]), "name": s.get("name") or "", "nameKey": NAME_KEYS.get(s.get("name"), "")}
                for s in res["sections"]]
    segments = [{"start": num(r["start"]), "end": num(r["end"]), "group": r["group"], "count": int(r["count"]),
                 "best": num(r["best"]), "sim": num(r["sim"])} for r in res["rows"]]
    return {"version": version, "sub": SUB, "sections": sections, "segments": segments, "chorus": list(res["chorus"])}

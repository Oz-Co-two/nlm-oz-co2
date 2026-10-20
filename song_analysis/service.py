"""曲の解析の窓口（serve.py の /__analysis/*）: 音源の一時保存と、解析を1件ずつ別スレッドで回す仕事の列。

- 音源は OS の一時フォルダの下の専用フォルダ（ROOT_NAME）に、中身の SHA-256 の名前で置く（同じ中身なら同じ id・保存し直さない）。
  最後に使ってから KEEP_SEC を過ぎた物と、合計が KEEP_BYTES を超えた分（古い順）は片付ける（解析中・待ちの物は残す）。
  exe の隣の config/ には置かない（大きい・使い捨てのため）。
- 解析は同時に1件（2件目からは待ち行列）。進み具合の区切りごとに取り消しを確かめる（重い計算の途中では止まらない）。
- 同じ音源・同じ条件の結果は覚えておき、次は計算せずに返す（画面で解析し直しを押しても待たない。計算は毎回同じ結果になる）。
- エラーは文言ではなく種類（AnalysisError.code）で返す。画面（JS）が訳す（CLAUDE.md「表示言語」）。
- numpy・librosa 等は解析を始めた時に読み込む（このファイルは標準ライブラリだけで読み込める＝serve.py の起動を遅くしない）。
"""
import collections
import glob
import hashlib
import json
import math
import os
import re
import secrets
import shutil
import subprocess
import tempfile
import threading
import time
import traceback

from . import RESULT_VERSION

ROOT_NAME = 'NLM-analysis'          # 一時フォルダの下の専用フォルダの名前
MAX_UPLOAD = 300 * 1024 * 1024      # 音源の大きさの上限（WAV の 5分は約50MB・FLAC は約30MB）
KEEP_SEC = 24 * 3600                # 音源を残す時間（最後に使ってから）
KEEP_BYTES = 2 * 1024 ** 3          # 音源の合計の上限（超えたら古い順に消す）
PART_SEC = 3600                     # 書きかけ（.part）を残す時間（落ちた等で残った物）
CLEAN_EVERY = 600                   # 片付けを試す間隔（秒）
JOB_KEEP_SEC = 3600                 # 終わった仕事の状態を覚えておく時間
MAX_DONE_JOBS = 200                 # 終わった仕事を覚えておく数
MAX_QUEUE = 20                      # 待ち行列の上限
RESULT_CACHE = 16                   # 覚えておく解析結果の数
MIN_SEC = 5.0                       # これより短い音源は解析しない
MIN_CELLS = 24                      # 構成解析: 音のあるコマ（1/4拍）がこれより少ない目盛りは解析しない（6拍。グループ数12の分割ができない）
SR = 22050                          # 解析の音の形（song_analysis.tempo / structure の SR と同じ）
MAX_GRID = 200000                   # 構成解析の目盛りの数の上限（1/4拍ごと。BPM 300 で 2時間45分）
# 拡張子（そのまま保存する物。他は .bin）。SF_EXTS は ffmpeg が無くても読める（libsndfile）
AUDIO_EXTS = {'mp3', 'ogg', 'egg', 'oga', 'opus', 'flac', 'wav', 'wave', 'aif', 'aiff', 'aifc', 'caf',
              'm4a', 'aac', 'mp4', 'wma', 'webm', 'mka'}
SF_EXTS = {'mp3', 'ogg', 'egg', 'oga', 'opus', 'flac', 'wav', 'wave', 'aif', 'aiff', 'aifc', 'caf'}
_ID = re.compile(r'[0-9a-f]{64}')


class AnalysisError(Exception):
    """code: 画面へ返すエラーの種類（too-large・bad-audio・too-short・ffmpeg-not-found・unknown-audio・unknown-job・
    bad-grid・bad-request・busy・cancelled・unavailable・failed）"""

    def __init__(self, code, detail=''):
        super().__init__(code)
        self.code = code
        self.detail = detail


class _Cancelled(Exception):
    pass


class _Job:
    def __init__(self, kind, audio_id, params, key):
        self.id = secrets.token_hex(8)
        self.kind, self.audio_id, self.params, self.key = kind, audio_id, params, key
        self.state, self.progress = 'queued', 0.0
        self.result = self.error = None
        self.detail = ''
        self.cancel = threading.Event()
        self.done_at = None

    def view(self):
        out = {'ok': True, 'state': self.state, 'stage': self.kind, 'progress': round(self.progress, 3),
               'result': self.result, 'error': self.error}
        if self.detail:
            out['detail'] = self.detail
        return out


def _plain(o):
    """結果を JSON にできる形にする（numpy の数→Python の数、NaN・無限大→None、タプル→リスト）"""
    if isinstance(o, dict):
        return {str(k): _plain(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_plain(v) for v in o]
    if o is None or isinstance(o, (str, bool)):
        return o
    if isinstance(o, int):
        return int(o)
    if hasattr(o, 'dtype') and getattr(o, 'shape', None) == ():   # numpy の数
        o = o.item()
        if isinstance(o, (bool, int, str)):
            return o
    if isinstance(o, float):
        return o if math.isfinite(o) else None
    raise TypeError(type(o).__name__)


def _num(v, lo, hi):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) and lo <= v <= hi


class AnalysisService:
    def __init__(self, root=None):
        self.root = root or os.path.join(tempfile.gettempdir(), ROOT_NAME)
        self.lock = threading.Lock()
        self.cv = threading.Condition(self.lock)
        self.queue = collections.deque()
        self.jobs = {}
        self.results = collections.OrderedDict()
        self.thread = None
        self.last_clean = 0.0

    # ---- 音源 ----

    def store(self, read, length, ext):
        """本体（length バイト・read(n) で読む）を保存して音源の id を返す。本体は失敗しても最後まで読む
        （読み残すと Windows では応答が届かないことがある。serve.py の _drain の説明）"""
        ext = re.sub(r'[^a-z0-9]', '', str(ext or '').lower())[:8]
        ext = ext if ext in AUDIO_EXTS else 'bin'
        if length <= 0:
            raise AnalysisError('bad-audio', 'empty')
        if length > MAX_UPLOAD:
            raise AnalysisError('too-large')
        h = hashlib.sha256()
        f = tmp = None
        err = None
        try:
            os.makedirs(self.root, exist_ok=True)
            tmp = os.path.join(self.root, 'up-%s.part' % secrets.token_hex(6))
            f = open(tmp, 'wb')
        except OSError as e:
            err = AnalysisError('failed', 'store: %s' % e)
        left = length
        try:
            while left > 0:
                d = read(min(left, 1 << 20))
                if not d:
                    break
                left -= len(d)
                h.update(d)
                if f and not err:
                    try:
                        f.write(d)
                    except OSError as e:
                        err = AnalysisError('failed', 'store: %s' % e)
        finally:
            if f:
                f.close()
        try:
            if left > 0 and not err:
                err = AnalysisError('bad-request', 'body ended early')
            if err:
                raise err
            aid = h.hexdigest()
            with self.lock:
                old = self._find(aid)
                if old:
                    self._touch(old)
                else:
                    try:
                        os.replace(tmp, os.path.join(self.root, '%s.%s' % (aid, ext)))
                        tmp = None
                    except OSError:
                        if not self._find(aid):   # 同じ中身を同時に保存した側が先に置いた時は、それを使う
                            raise
            self._maybe_clean()
            return aid
        finally:
            if tmp:
                try:
                    os.remove(tmp)
                except OSError:
                    pass

    def _find(self, aid):
        """音源の id → 保存したファイル（無ければ None）"""
        if not isinstance(aid, str) or not _ID.fullmatch(aid):
            return None
        for p in glob.glob(os.path.join(glob.escape(self.root), aid + '.*')):
            if not p.endswith(('.part', '.dec.wav')):
                return p
        return None

    @staticmethod
    def _touch(p):
        try:
            os.utime(p, None)
        except OSError:
            pass

    def _maybe_clean(self, force=False):
        now = time.time()
        if not force and now - self.last_clean < CLEAN_EVERY:
            return
        self.last_clean = now
        try:
            self.clean()
        except OSError:
            pass

    def clean(self, now=None):
        """古い音源を片付ける（解析中・待ちの仕事が使う物は残す）。消した数を返す"""
        now = time.time() if now is None else now
        with self.lock:
            busy = {j.audio_id for j in self.jobs.values() if j.state in ('queued', 'running')}
        files = []
        for p in glob.glob(os.path.join(glob.escape(self.root), '*')):
            try:
                st = os.stat(p)
            except OSError:
                continue
            if not os.path.isfile(p):
                continue
            files.append((st.st_mtime, st.st_size, p))
        removed = 0
        total = sum(s for _, s, _ in files)
        for mt, size, p in sorted(files):   # 古い順
            name = os.path.basename(p)
            aid = name.split('.', 1)[0]
            if aid in busy:
                continue
            old = now - mt > (PART_SEC if name.endswith('.part') else KEEP_SEC)
            if old or total > KEEP_BYTES:
                try:
                    os.remove(p)
                    removed += 1
                    total -= size
                except OSError:
                    pass
        return removed

    # ---- 仕事 ----

    def start_tempo(self, audio_id):
        if not self._find(audio_id):
            raise AnalysisError('unknown-audio')
        return self._submit('tempo', audio_id, {}, ('tempo', audio_id))

    def start_structure(self, audio_id, grid):
        if not self._find(audio_id):
            raise AnalysisError('unknown-audio')
        g = self.check_grid(grid)
        key = ('structure', audio_id, hashlib.sha256(json.dumps(g, sort_keys=True).encode()).hexdigest())
        return self._submit('structure', audio_id, g, key)

    @staticmethod
    def check_grid(grid):
        """構成解析の目盛り {bpm, leadMs, sub, at} を確かめる（だめなら bad-grid）"""
        if not isinstance(grid, dict):
            raise AnalysisError('bad-grid')
        bpm, lead, sub, at = grid.get('bpm'), grid.get('leadMs', 0), grid.get('sub'), grid.get('at')
        if not _num(bpm, 10, 1000) or not _num(sub, 4, 4) or (lead is not None and not _num(lead, -1e7, 1e7)):
            raise AnalysisError('bad-grid')
        if not isinstance(at, list) or not 0 < len(at) <= MAX_GRID:
            raise AnalysisError('bad-grid')
        if any(v is not None and not _num(v, -1e7, 1e7) for v in at) or all(v is None for v in at):
            raise AnalysisError('bad-grid')
        return {'bpm': float(bpm), 'leadMs': None if lead is None else float(lead), 'sub': 4,
                'at': [None if v is None else float(v) for v in at]}

    def _submit(self, kind, audio_id, params, key):
        with self.cv:
            self._prune()
            for j in self.jobs.values():   # 同じ条件で待ち・解析中の物があればそれを返す
                if j.key == key and j.state in ('queued', 'running'):
                    return j.id
            job = _Job(kind, audio_id, params, key)
            hit = self.results.get(key)
            if hit is not None:   # 前に同じ条件で解析した結果
                self.results.move_to_end(key)
                job.state, job.progress, job.result, job.done_at = 'done', 1.0, hit, time.time()
                self.jobs[job.id] = job
                return job.id
            if sum(1 for j in self.jobs.values() if j.state == 'queued') >= MAX_QUEUE:
                raise AnalysisError('busy')
            self.jobs[job.id] = job
            self.queue.append(job)
            if self.thread is None or not self.thread.is_alive():
                self.thread = threading.Thread(target=self._worker, name='nlm-analysis', daemon=True)
                self.thread.start()
            self.cv.notify()
            return job.id

    def status(self, job_id):
        with self.lock:
            j = self.jobs.get(job_id) if isinstance(job_id, str) else None
            if not j:
                raise AnalysisError('unknown-job')
            return j.view()

    def cancel(self, job_id):
        with self.lock:
            j = self.jobs.get(job_id) if isinstance(job_id, str) else None
            if not j:
                raise AnalysisError('unknown-job')
            if j.state == 'queued':
                try:
                    self.queue.remove(j)
                except ValueError:
                    pass
                j.state, j.error, j.done_at = 'error', 'cancelled', time.time()
            elif j.state == 'running':
                j.cancel.set()   # 次の区切りで止まる（状態は止まった時に error/cancelled になる）
            return {'ok': True}

    def _prune(self):
        """終わった仕事を覚えておく数・時間を超えた物を忘れる（lock の中で呼ぶ）"""
        now = time.time()
        done = sorted((j.done_at, k) for k, j in self.jobs.items() if j.done_at is not None)
        for i, (t, k) in enumerate(done):
            if now - t > JOB_KEEP_SEC or len(done) - i > MAX_DONE_JOBS:
                del self.jobs[k]

    def _worker(self):
        import warnings
        warnings.filterwarnings('ignore', module=r'(librosa|numpy|scipy|sklearn|numba|soundfile|song_analysis)')
        self._maybe_clean(force=True)
        while True:
            with self.cv:
                while not self.queue:
                    self.cv.wait()
                job = self.queue.popleft()
                job.state = 'running'
            try:
                res = _plain(self._run(job))
                with self.lock:
                    job.state, job.result, job.progress = 'done', res, 1.0
                    self.results[job.key] = res
                    while len(self.results) > RESULT_CACHE:
                        self.results.popitem(last=False)
            except _Cancelled:
                with self.lock:
                    job.state, job.error = 'error', 'cancelled'
            except AnalysisError as e:
                with self.lock:
                    job.state, job.error, job.detail = 'error', e.code, e.detail[:500]
            except MemoryError:
                with self.lock:
                    job.state, job.error = 'error', 'failed'
                    job.detail = 'MemoryError'
            except Exception as e:
                with self.lock:
                    job.state, job.error = 'error', 'failed'
                    job.detail = ('%s: %s' % (type(e).__name__, e))[:300] + ' | ' + traceback.format_exc()[-1200:]
            finally:
                with self.lock:
                    job.done_at = time.time()

    def _tick(self, job, lo, hi):
        """進み具合 lo〜hi の区間を受け持つ関数（呼ばれるたびに取り消しを確かめる）"""
        def f(frac):
            if job.cancel.is_set():
                raise _Cancelled()
            job.progress = max(job.progress, lo + (hi - lo) * min(max(float(frac), 0.0), 1.0))
        return f

    def _run(self, job):
        tick = self._tick(job, 0.0, 0.02)
        tick(0)
        path = self._find(job.audio_id)
        if not path:
            raise AnalysisError('unknown-audio')
        self._touch(path)
        try:
            from . import structure, tempo   # numpy・scipy・scikit-learn もここで読み込まれる
        except ImportError as e:
            raise AnalysisError('unavailable', str(e))
        try:   # 計算に使うスレッドは CPU の半分まで（解析の間も編集できるように）。数値計算の部品を読み込んだ後で設定する
            from threadpoolctl import threadpool_limits
            limit = threadpool_limits(max(1, (os.cpu_count() or 2) // 2))
        except Exception:
            limit = None
        try:
            tick(1)
            y = self._load(path)
            if job.kind == 'tempo':
                self._tick(job, 0.1, 0.1)(1)
                env, fps, dur, low = tempo.onset_env(path, y=y, progress=self._tick(job, 0.1, 0.85))
                r = tempo.estimate(env, fps, low=low)
                if r.get('error'):
                    r['error'] = 'few-onsets'   # 強い打点が少なすぎる（BPM・無音追加は目安）
                r['drift'] = [list(x) for x in r.get('drift') or []]
                r['version'] = RESULT_VERSION
                return r
            g = job.params
            self._tick(job, 0.08, 0.08)(1)
            F = structure.measure_at(path, g['at'], g['bpm'], g['leadMs'], y=y,
                                     progress=self._tick(job, 0.08, 0.4))
            if int((F['at'] == F['at']).sum()) < MIN_CELLS:   # 音のあるコマ（NaN でない）が少なすぎると区切れない
                raise AnalysisError('too-short')
            res = structure.analyze(F, g['bpm'], progress=self._tick(job, 0.4, 1.0))
            out = structure.result_json(res, RESULT_VERSION)
            out['bpm'], out['leadMs'] = g['bpm'], g['leadMs']
            return out
        finally:
            if limit is not None:
                try:
                    limit.restore_original_limits()
                except Exception:
                    pass

    def _load(self, path):
        """音源を解析の形（SR・モノラル）で読む。libsndfile で読めない形式（m4a 等）は ffmpeg で WAV にしてから読む"""
        import librosa
        try:
            y, _ = librosa.load(path, sr=SR, mono=True)
        except Exception as e:
            ext = path.rsplit('.', 1)[-1].lower()
            ffmpeg = shutil.which('ffmpeg')
            if not ffmpeg:
                raise AnalysisError('bad-audio' if ext in SF_EXTS else 'ffmpeg-not-found', str(e)[:300])
            wav = self._decode(ffmpeg, path)
            try:
                y, _ = librosa.load(wav, sr=SR, mono=True)
            except Exception as e2:
                raise AnalysisError('bad-audio', str(e2)[:300])
        if y.ndim != 1 or len(y) < MIN_SEC * SR:
            raise AnalysisError('too-short')
        return y

    def _decode(self, ffmpeg, path):
        """ffmpeg で 32bit 浮動小数の WAV にする（チャンネル数・サンプリング周波数はそのまま＝後は librosa の読み込みと同じ）"""
        aid = os.path.basename(path).split('.', 1)[0]
        dst = os.path.join(self.root, aid + '.dec.wav')
        if os.path.isfile(dst):
            self._touch(dst)
            return dst
        tmp = os.path.join(self.root, 'dec-%s.part' % secrets.token_hex(6))
        try:
            r = subprocess.run([ffmpeg, '-nostdin', '-y', '-v', 'error', '-i', path, '-vn', '-f', 'wav', '-acodec', 'pcm_f32le', tmp],
                               capture_output=True, timeout=600, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            if r.returncode != 0 or not os.path.isfile(tmp):
                raise AnalysisError('bad-audio', (r.stderr or b'').decode('utf-8', 'ignore')[-300:])
            os.replace(tmp, dst)
            return dst
        except subprocess.TimeoutExpired:
            raise AnalysisError('bad-audio', 'ffmpeg timeout')
        finally:
            if os.path.exists(tmp):
                try:
                    os.remove(tmp)
                except OSError:
                    pass

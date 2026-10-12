# BeatSaver への「1曲だけ」の問い合わせ（MEDIAライブラリ・2026-10-12）
#
# 利用者が🔍を押して確認した曲だけを、公式 API（GET https://api.beatsaver.com/maps/hash/<ハッシュ>）に問い合わせる。
# 全曲データ（song_details.py）に無い曲の補いで、まとめて問い合わせる使い方はしない。
# 約束:
#  - 取得先はここに固定。受け取るのは40桁の小文字16進のハッシュだけ（URL・ホスト名は渡せない）
#  - 同時に1つだけ・前の問い合わせから1秒以上あける・時間切れ15秒・応答の上限2MB
#  - 429 は待ち時間まで問い合わせを止める（Retry-After ヘッダー（秒）→本文の resetAfter（ミリ秒）→10分。上限1時間）
#  - 結果は <DATA_DIR>/config/beatsaver_cache.json に記録（ハッシュごと）。見つからなかった（404）ことも記録する
#  - ネットから来た値は信用しない（数値は範囲を確かめ、文字列は長さを切り、形の違う物は捨てる）
import datetime
import json
import os
import re
import threading
import time
import urllib.error
import urllib.request

import song_details

API = 'https://api.beatsaver.com/maps/hash/'
MIN_GAP = 1.0                 # 問い合わせの最小間隔（秒）
TIMEOUT = 15
MAX_BODY = 2 * 1024 * 1024
DEFAULT_WAIT = 600            # 429 で待ち時間が分からない時
MAX_WAIT = 3600
_HASH_RE = re.compile(r'[0-9a-f]{40}')
_KEY_RE = re.compile(r'[0-9a-f]{1,8}')
_CHARS = {'Standard', 'OneSaber', 'NoArrows', '90Degree', '360Degree', 'Lightshow', 'Lawless', 'Legacy', 'Custom'}
_DIFFS = {'Easy', 'Normal', 'Hard', 'Expert', 'ExpertPlus'}


def _num(v, lo, hi):
    """範囲内の数だけ通す（bool・文字列・NaN は 0）"""
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return 0
    return v if lo <= v <= hi else 0


def _time(s):
    # ISO 8601（"2020-05-01T12:34:56.789Z"）→ UNIX 秒。読めなければ 0
    if not isinstance(s, str) or len(s) > 40:
        return 0
    try:
        d = datetime.datetime.fromisoformat(s.replace('Z', '+00:00'))
        if d.tzinfo is None:
            d = d.replace(tzinfo=datetime.timezone.utc)
        t = int(d.timestamp())
        return t if 0 <= t <= 0xffffffff else 0
    except Exception:
        return 0


def _stars(v):
    v = _num(v, 0, 1000)
    return round(float(v), 2) if v > 0 else 0


def convert(data, hash):
    """BeatSaver の応答（辞書）を net の形（src:'beatsaver'）にする。形が違えば None。
    返ってきた版のハッシュが hash と違う（手元が古い版）なら match:'key' ＝★とランク状態は入れない"""
    if not isinstance(data, dict):
        return None
    key = data.get('id')
    if not isinstance(key, str) or not _KEY_RE.fullmatch(key.lower()):
        return None
    stats = data.get('stats') if isinstance(data.get('stats'), dict) else {}
    versions = data.get('versions') if isinstance(data.get('versions'), list) else []
    mine = None
    for v in versions:
        if isinstance(v, dict) and isinstance(v.get('hash'), str) and v['hash'].lower() == hash:
            mine = v
            break
    tags = []
    if isinstance(data.get('tags'), list):
        tags = [t[:60] for t in data['tags'] if isinstance(t, str)][:64]
    out = {'src': 'beatsaver', 'match': 'hash' if mine else 'key', 'key': key.lower(),
           'uploaded': _time(data.get('uploaded')),
           'up': int(_num(stats.get('upvotes'), 0, 0xffffffff)), 'down': int(_num(stats.get('downvotes'), 0, 0xffffffff)),
           'tags': tags, 'diffs': {}}
    if mine:
        out['ranked'] = {'bl': data.get('blRanked') is True, 'blq': data.get('blQualified') is True,
                         'ss': data.get('ranked') is True, 'ssq': data.get('qualified') is True}
        for d in mine.get('diffs') if isinstance(mine.get('diffs'), list) else []:
            if not isinstance(d, dict) or d.get('characteristic') not in _CHARS or d.get('difficulty') not in _DIFFS:
                continue
            e = {}
            if _stars(d.get('blStars')):
                e['bl'] = _stars(d['blStars'])
            if _stars(d.get('stars')):
                e['ss'] = _stars(d['stars'])
            if e:
                out['diffs'][d['characteristic'] + '/' + d['difficulty']] = e
    return out


def _wait_seconds(headers, body):
    """429 の待ち時間（秒）。Retry-After（秒）→本文 resetAfter（ミリ秒）→10分。1〜3600 に丸める。負や数値でない値は無視"""
    ra = headers.get('Retry-After') if headers else None
    if isinstance(ra, str) and re.fullmatch(r'\s*\d{1,9}(\.\d+)?\s*', ra):
        return max(1, min(MAX_WAIT, int(float(ra))))
    try:
        ms = json.loads(body.decode('utf-8', 'replace')).get('resetAfter')
        if not isinstance(ms, bool) and isinstance(ms, (int, float)) and 0 < ms < 1e12:
            return max(1, min(MAX_WAIT, int(ms / 1000 + 0.999)))
    except Exception:
        pass
    return DEFAULT_WAIT


class BeatSaverLookup:
    def __init__(self, data_dir, opener=None, clock=None, sleep=None, app_root=None):
        """opener / clock / sleep はテスト用の差し替え口（既定は urlopen・time.time・time.sleep）。取得先は差し替えられない"""
        self.path = os.path.join(data_dir, 'config', 'beatsaver_cache.json')
        self._open = opener or urllib.request.urlopen
        self._now = clock or time.time
        self._sleep = sleep or time.sleep
        self._ua = song_details.user_agent(app_root)
        self._busy = threading.Lock()       # 通信は同時に1つだけ
        self._io = threading.Lock()         # 記録ファイルの読み書き
        self._last = 0.0                    # 前の問い合わせの時刻
        self._blocked_until = None

    # ---- 記録 ----
    def _load(self):
        try:
            with open(self.path, encoding='utf-8') as f:
                d = json.load(f)
            if isinstance(d, dict) and isinstance(d.get('maps'), dict):
                return d
        except Exception:
            pass
        return {'v': 1, 'maps': {}}

    def _save(self, d):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        tmp = self.path + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(d, f, ensure_ascii=False)
        os.replace(tmp, self.path)

    def cached(self, hash):
        """記録だけを返す（通信しない）。無ければ None"""
        if not isinstance(hash, str) or not _HASH_RE.fullmatch(hash):
            return None
        with self._io:
            e = self._load()['maps'].get(hash)
        return e if isinstance(e, dict) and e.get('src') in ('beatsaver', 'none') else None

    def _remember(self, hash, net):
        with self._io:
            d = self._load()
            d['maps'][hash] = net
            self._save(d)

    def _block_state(self, d=None):
        # 429 の止め期間（再起動しても守る）
        if self._blocked_until is None:
            with self._io:
                b = self._load().get('blockedUntil')
            self._blocked_until = b if isinstance(b, (int, float)) else 0
        return self._blocked_until

    # ---- 問い合わせ ----
    def lookup(self, hash):
        """BeatSaver にこの1曲だけ問い合わせて記録し、net の形で返す。
        見つからなければ {'src':'none','bsMissAt':時刻}。失敗は {'error': 'badHash'|'busy'|'network'|'tooBig'|'badResponse'|'http<番号>', 'retryAfter'?: 秒}"""
        if not isinstance(hash, str) or not _HASH_RE.fullmatch(hash):
            return {'error': 'badHash'}
        if not self._busy.acquire(blocking=False):
            return {'error': 'busy', 'retryAfter': 1}
        try:
            now = self._now()
            until = self._block_state()
            if now < until:
                return {'error': 'busy', 'retryAfter': int(until - now + 0.999)}
            gap = MIN_GAP - (now - self._last)
            if gap > 0:
                self._sleep(gap)
            self._last = self._now()
            return self._ask(hash)
        except Exception:
            return {'error': 'network'}
        finally:
            self._busy.release()

    def _ask(self, hash):
        req = urllib.request.Request(API + hash, headers={'User-Agent': self._ua, 'Accept': 'application/json',
                                                           'Accept-Encoding': 'identity'})
        try:
            r = self._open(req, timeout=TIMEOUT)
        except urllib.error.HTTPError as e:
            if e.code == 404:
                net = {'src': 'none', 'bsMissAt': int(self._now())}
                self._remember(hash, net)
                return net
            if e.code == 429:
                try:
                    body = e.read(65536)
                except Exception:
                    body = b''
                wait = _wait_seconds(e.headers, body)
                self._blocked_until = self._now() + wait
                with self._io:
                    d = self._load()
                    d['blockedUntil'] = self._blocked_until
                    self._save(d)
                return {'error': 'busy', 'retryAfter': wait}
            return {'error': 'http%d' % e.code}
        except Exception:
            return {'error': 'network'}
        with r:
            try:
                ln = int(r.headers.get('Content-Length') or 0)
            except Exception:
                ln = 0
            if ln > MAX_BODY:
                return {'error': 'tooBig'}
            body = r.read(MAX_BODY + 1)
        if len(body) > MAX_BODY:
            return {'error': 'tooBig'}
        try:
            net = convert(json.loads(body.decode('utf-8')), hash)
        except Exception:
            net = None
        if net is None:
            return {'error': 'badResponse'}
        self._remember(hash, net)
        return net

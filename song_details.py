# 全曲データ（BeatSaver 上の全譜面の要約）の取得と読み取り（MEDIAライブラリ・2026-10-12）
#
# 出典: kinsi55 さんの BeatSaberScrappedData の songDetails2_v3.gz（gzip した protobuf・約10MB・ほぼ毎日更新）。
# Beat Saber の Mod（BetterSongList 等）が使っている物。形式は kinsi55/BeatSaber_SongDetails（MIT）の
# Structs/SongProtoContainer.cs・SongProto.cs・SongDifficultyProto.cs と SongDetails.cs（Process）に従う（列挙型の値もそこ）。
#   container: 1 formatVersion(=3) 2 scrapeEndedTimeUnix 3 songHashes(20バイト×曲数・songs と同じ順) 4 songs(繰り返し) 5 tagList
#   tags(ulong) の第 i ビット ＝ tagList[i]。songs は mapId の昇順（ただしここでは並びを信用せず辞書で引く）
# 安全のための約束:
#  - 取得先 URL はここに固定（jsDelivr だけ。GitHub の raw は予備にも使わない＝利用者の決定）。引数では受け取らない
#  - サイズの上限・時間切れ・一時ファイル→置き換え。失敗しても前のデータは消さない。通信は1日1回まで（ETag）
#  - ネットから来たデータは信用しない（読み取りは範囲を確かめ、壊れていても例外を外へ出さない。文字列は長さを切る）
import gzip
import json
import os
import re
import struct
import threading
import time
import urllib.error
import urllib.request
import zlib

URL = 'https://cdn.jsdelivr.net/gh/kinsi55/BeatSaberScrappedData/songDetails2_v3.gz'
FORMAT_VERSION = 3
MAX_DOWNLOAD = 50 * 1024 * 1024      # 取得する gz の上限（実物は約10MB）
MAX_UNZIP = 400 * 1024 * 1024        # 展開後の上限（実物は数十MB）
TIMEOUT = 20                          # 通信の時間切れ（秒）
INTERVAL = 24 * 3600                  # 前回の確認からこれ未満なら通信しない
ERROR_BACKOFF = 10 * 60               # 失敗した後に再び試すまで
MAX_STR = 200

# 列挙型（SongDifficultyProto.cs / SongProto.cs）。名前は Beat Saber の Info.dat の名前
CHARACTERISTICS = {0: 'Custom', 1: 'Standard', 2: 'OneSaber', 3: 'NoArrows', 4: '90Degree', 5: '360Degree', 6: 'Lightshow', 7: 'Lawless'}
DIFFICULTIES = {0: 'Easy', 1: 'Normal', 2: 'Hard', 3: 'Expert', 4: 'ExpertPlus'}
RS_SS, RS_BL, RS_SSQ, RS_BLQ = 1, 2, 4, 8   # RankedStates のビット

_KEY_RE = re.compile(r'[0-9a-fA-F]{1,8}')
_HASH_RE = re.compile(r'[0-9a-fA-F]{40}')


def _app_version(app_root):
    # app.py の _app_version と同じ。読めなければ空（User-Agent は版なしになる）
    try:
        with open(os.path.join(app_root, 'js', 'constants.js'), encoding='utf-8') as f:
            m = re.search(r"APP_VERSION\s*=\s*'([^']+)'", f.read())
        return m.group(1) if m else ''
    except Exception:
        return ''


def user_agent(app_root=None):
    root = app_root or os.path.dirname(os.path.abspath(__file__))
    v = _app_version(root)
    return 'NonLinearMapper/%s (+https://github.com/Oz-Co-two/nlm-oz-co2)' % v if v else 'NonLinearMapper (+https://github.com/Oz-Co-two/nlm-oz-co2)'


# ---- protobuf の読み取り（必要な分だけ・自前） ----
def _varint(b, i, end):
    r = 0
    s = 0
    while True:
        if i >= end or s > 63:
            raise ValueError('varint')
        c = b[i]
        i += 1
        r |= (c & 0x7f) << s
        if c < 0x80:
            return r, i
        s += 7


def _fields(b, i, end):
    """(番号, 値) を順に返す。長さ付き(2)の値は (開始, 終了) の組、固定長(1,5)は生のバイト列、可変長(0)は整数。壊れていれば ValueError"""
    while i < end:
        tag, i = _varint(b, i, end)
        fn, wt = tag >> 3, tag & 7
        if fn == 0:
            raise ValueError('field0')
        if wt == 0:
            v, i = _varint(b, i, end)
        elif wt == 2:
            n, i = _varint(b, i, end)
            if n > end - i:
                raise ValueError('len')
            v = (i, i + n)
            i += n
        elif wt == 5:
            if i + 4 > end:
                raise ValueError('f32')
            v = bytes(b[i:i + 4])
            i += 4
        elif wt == 1:
            if i + 8 > end:
                raise ValueError('f64')
            v = bytes(b[i:i + 8])
            i += 8
        else:
            raise ValueError('wire')
        yield fn, v


def _str(b, se):
    return bytes(b[se[0]:se[1]]).decode('utf-8', 'replace')[:MAX_STR]


def _unzip(path):
    """gz を展開して bytes で返す（上限を超えたら ValueError）"""
    d = zlib.decompressobj(31)
    out = []
    total = 0
    with open(path, 'rb') as f:
        while True:
            c = f.read(1 << 20)
            if not c:
                break
            while c:
                part = d.decompress(c, MAX_UNZIP + 1 - total)
                total += len(part)
                out.append(part)
                if total > MAX_UNZIP:
                    raise ValueError('too big')
                c = d.unconsumed_tail
    out.append(d.flush())
    return b''.join(out)


class _Index:
    """展開済みのバイト列から、ハッシュ→曲・キー→曲の索引を作った物。曲の中身は引かれた時に初めて読む"""

    def __init__(self, buf):
        self.buf = buf
        self.version = None
        self.scrape = 0
        self.tags = []
        self.songs = []        # (開始, 終了)
        hashes = (0, 0)
        for fn, v in _fields(buf, 0, len(buf)):
            if fn == 1 and isinstance(v, int):
                self.version = v
            elif fn == 2 and isinstance(v, int):
                self.scrape = v
            elif fn == 3 and isinstance(v, tuple):
                hashes = v
            elif fn == 4 and isinstance(v, tuple):
                self.songs.append(v)
            elif fn == 5 and isinstance(v, tuple):
                if len(self.tags) < 64:
                    self.tags.append(_str(buf, v))
        self.hash_idx = {}
        self.key_idx = {}
        if self.version != FORMAT_VERSION:
            return
        n = len(self.songs)
        hn = (hashes[1] - hashes[0]) // 20
        for i, (s, e) in enumerate(self.songs):
            try:
                for fn, v in _fields(buf, s, e):
                    if fn == 5:                       # mapId（番号の昇順に並ぶので5が見つかれば十分）
                        if isinstance(v, int) and v <= 0xffffffff:
                            self.key_idx.setdefault(v, i)
                        break
                    if fn > 5:
                        break
            except ValueError:
                pass
        if hn >= n:
            hb = bytes(buf[hashes[0]:hashes[0] + 20 * n])
            for i in range(n):
                self.hash_idx.setdefault(hb[20 * i:20 * i + 20], i)

    def song(self, i):
        """曲 i の中身（辞書）。壊れていれば None"""
        s, e = self.songs[i]
        buf = self.buf
        o = {'up': 0, 'down': 0, 'uploaded': 0, 'key': None, 'states': 0, 'tagbits': 0, 'diffs': []}
        try:
            for fn, v in _fields(buf, s, e):
                if fn == 2 and isinstance(v, int):
                    o['up'] = min(v, 0xffffffff)
                elif fn == 3 and isinstance(v, int):
                    o['down'] = min(v, 0xffffffff)
                elif fn == 4 and isinstance(v, int):
                    o['uploaded'] = v if v <= 0xffffffff else 0
                elif fn == 5 and isinstance(v, int) and v <= 0xffffffff:
                    o['key'] = '%x' % v
                elif fn == 13 and isinstance(v, int):
                    o['states'] = v & 0xffffffff
                elif fn == 14 and isinstance(v, int):
                    o['tagbits'] = v & 0xffffffffffffffff
                elif fn == 11 and isinstance(v, tuple):
                    d = self._diff(v)
                    if d:
                        o['diffs'].append(d)
        except ValueError:
            return None
        return o

    def _diff(self, se):
        # 無い項目は protobuf の既定値（0）ではなく SongDifficultyProto のコンストラクターの既定（Standard / ExpertPlus）になる
        ch, df, ss, bl = 1, 4, 0, 0
        try:
            for fn, v in _fields(self.buf, se[0], se[1]):
                if not isinstance(v, int):
                    continue
                if fn == 1:
                    ch = v
                elif fn == 2:
                    df = v
                elif fn == 4:
                    ss = v
                elif fn == 5:
                    bl = v
        except ValueError:
            return None
        if ch not in CHARACTERISTICS or df not in DIFFICULTIES:
            return None
        return CHARACTERISTICS[ch] + '/' + DIFFICULTIES[df], ss, bl

    def tag_names(self, bits):
        return [t for i, t in enumerate(self.tags) if bits >> i & 1]


def _stars(t100):
    # 100倍の整数。0＝無し。ありえない大きさは無しにする
    return round(t100 / 100, 2) if 0 < t100 <= 100000 else 0


class SongDetails:
    def __init__(self, data_dir, opener=None, clock=None, app_root=None):
        """opener / clock はテスト用の差し替え口（既定は urllib.request.urlopen と time.time）。URL は差し替えられない"""
        self.dir = os.path.join(data_dir, 'config', 'songdetails')
        self.gz = os.path.join(self.dir, 'songDetails2_v3.gz')
        self.meta_path = os.path.join(self.dir, 'meta.json')
        self._open = opener or urllib.request.urlopen
        self._now = clock or time.time
        self._ua = user_agent(app_root)
        self._lock = threading.RLock()
        self._idx = None
        self._idx_sig = None

    # ---- 状態 ----
    def _meta(self):
        try:
            with open(self.meta_path, encoding='utf-8') as f:
                m = json.load(f)
            return m if isinstance(m, dict) else {}
        except Exception:
            return {}

    def _save_meta(self, m):
        os.makedirs(self.dir, exist_ok=True)
        tmp = self.meta_path + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(m, f, ensure_ascii=False)
        os.replace(tmp, self.meta_path)

    def status(self):
        """{state: 'none'|'ok'|'error'|'unsupported', asOf: 全曲データの作成時刻(UNIX秒), fetchedAt: 最後に確認した時刻, error?}
        error は直近の取得の失敗（前に取れたデータがあれば照合には使える）。unsupported は形式の版が違う（照合には使わない）"""
        with self._lock:
            m = self._meta()
            have = os.path.isfile(self.gz)
            st = {'state': 'none', 'asOf': 0, 'fetchedAt': 0}
            if have:
                st['state'] = 'ok'
                st['asOf'] = m['asOf'] if isinstance(m.get('asOf'), int) else 0
            if isinstance(m.get('checkedAt'), (int, float)):
                st['fetchedAt'] = int(m['checkedAt'])
            if m.get('unsupported'):
                st['state'] = 'unsupported'
            elif isinstance(m.get('error'), str) and m['error']:
                st['state'] = 'error'
                st['error'] = m['error']
            return st

    # ---- 取得 ----
    def update(self):
        """前回の確認から24時間たっていなければ何もしない。たっていれば If-None-Match 付きで取得（304 なら確認時刻だけ更新）。
        status() の辞書に、結果 did（'throttled'|'notModified'|'downloaded'|'failed'）を足して返す。例外は外へ出さない"""
        with self._lock:
            now = self._now()
            m = self._meta()
            chk = m.get('checkedAt')
            have = os.path.isfile(self.gz)
            if have and isinstance(chk, (int, float)) and 0 <= now - chk < INTERVAL and not m.get('error'):
                return dict(self.status(), did='throttled')
            err = m.get('errorAt')
            if isinstance(err, (int, float)) and 0 <= now - err < ERROR_BACKOFF:
                return dict(self.status(), did='throttled')
            try:
                did = self._fetch(m, now)
                m.pop('error', None)
                m.pop('errorAt', None)
            except Exception as e:
                m['error'] = (str(e) or e.__class__.__name__)[:200]
                m['errorAt'] = now
                did = 'failed'
            try:
                self._save_meta(m)
            except Exception:
                pass
            return dict(self.status(), did=did)

    def _fetch(self, m, now):
        os.makedirs(self.dir, exist_ok=True)
        req = urllib.request.Request(URL, headers={'User-Agent': self._ua, 'Accept-Encoding': 'identity'})
        et = m.get('etag')
        if isinstance(et, str) and et and os.path.isfile(self.gz):
            req.add_header('If-None-Match', et)
        tmp = self.gz + '.tmp'
        try:
            try:
                r = self._open(req, timeout=TIMEOUT)
            except urllib.error.HTTPError as e:
                if e.code == 304:
                    m['checkedAt'] = now
                    return 'notModified'
                raise RuntimeError('http%d' % e.code)
            with r:
                code = getattr(r, 'status', 200)
                if code == 304:
                    m['checkedAt'] = now
                    return 'notModified'
                if code != 200:
                    raise RuntimeError('http%s' % code)
                try:
                    ln = int(r.headers.get('Content-Length') or 0)
                except Exception:
                    ln = 0
                if ln > MAX_DOWNLOAD:
                    raise RuntimeError('tooBig')
                total = 0
                with open(tmp, 'wb') as f:
                    while True:
                        c = r.read(1 << 16)
                        if not c:
                            break
                        total += len(c)
                        if total > MAX_DOWNLOAD:
                            raise RuntimeError('tooBig')
                        f.write(c)
                new_etag = r.headers.get('ETag')
            if total == 0:
                raise RuntimeError('empty')
            # 置き換える前に、読めること・形式の版を確かめる（壊れた物で前のデータを潰さない）
            try:
                ix = _Index(_unzip(tmp))
            except Exception:
                raise RuntimeError('broken')
            if ix.version != FORMAT_VERSION:
                m['unsupported'] = True
                m['checkedAt'] = now
                raise RuntimeError('unsupported')
            if not ix.songs:
                raise RuntimeError('broken')
            os.replace(tmp, self.gz)
            m.pop('unsupported', None)
            m['checkedAt'] = now
            m['asOf'] = ix.scrape
            m['etag'] = new_etag if isinstance(new_etag, str) and len(new_etag) < 300 else None
            self._idx = ix
            self._idx_sig = self._sig()
            return 'downloaded'
        finally:
            try:
                if os.path.exists(tmp):
                    os.remove(tmp)
            except OSError:
                pass

    # ---- 照合 ----
    def _sig(self):
        try:
            s = os.stat(self.gz)
            return (s.st_mtime_ns, s.st_size)
        except OSError:
            return None

    def _index(self):
        sig = self._sig()
        if sig is None:
            self._idx = self._idx_sig = None
            return None
        if self._idx is None or sig != self._idx_sig:
            try:
                ix = _Index(_unzip(self.gz))
            except Exception:
                ix = None
            self._idx, self._idx_sig = ix, sig
        return self._idx

    def lookup(self, hash=None, key=None):
        """ハッシュ（40桁の16進）またはキー（16進）で曲を引く。net の形（src:'dump'）を返す。無ければ None。
        ハッシュで当たれば match:'hash'（★とランク状態あり）、キーでだけ当たれば match:'key'（★とランク状態は入れない＝版が違うかもしれないため）。
        形式の版が違う・壊れている時も None（例外は出さない）"""
        try:
            with self._lock:
                m = self._meta()
                if m.get('unsupported'):
                    return None
                ix = self._index()
                if ix is None or ix.version != FORMAT_VERSION:
                    return None
                i, match = None, None
                if isinstance(hash, str) and _HASH_RE.fullmatch(hash):
                    i = ix.hash_idx.get(bytes.fromhex(hash))
                    match = 'hash'
                if i is None and isinstance(key, str) and _KEY_RE.fullmatch(key):
                    i = ix.key_idx.get(int(key, 16))
                    match = 'key'
                if i is None:
                    return None
                s = ix.song(i)
                if not s or s['key'] is None:
                    return None
                out = {'src': 'dump', 'match': match, 'key': s['key'], 'uploaded': s['uploaded'],
                       'up': s['up'], 'down': s['down'], 'tags': ix.tag_names(s['tagbits']), 'diffs': {}}
                if match == 'hash':
                    st = s['states']
                    out['ranked'] = {'bl': bool(st & RS_BL), 'blq': bool(st & RS_BLQ), 'ss': bool(st & RS_SS), 'ssq': bool(st & RS_SSQ)}
                    for k, ss, bl in s['diffs']:
                        e = {}
                        if _stars(bl):
                            e['bl'] = _stars(bl)
                        if _stars(ss):
                            e['ss'] = _stars(ss)
                        if e:
                            out['diffs'][k] = e
                return out
        except Exception:
            return None

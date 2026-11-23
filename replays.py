"""REPLAY の窓（BeatLeader のリプレイを BL のリプレイアプリで見る・2026-11-22）の裏側。元は Auto Note Plotter（同じ作者・GPLv3）の
app/replays.py・app/server.py の viewer の所。決まり（利用者の決定）は「今開いている曲の、NLM から書き出した版のリプレイだけ」を一覧にし、
遊んだ版の譜面が手元に無い物は灰色で出すだけ（BeatSaver から取らない・リプレイの記録から組み立てない）。

置き場（DATA_DIR＝exe の隣・開発ではリポジトリの直下）:
- config/replays.json … 利用者がダイアログで選んだリプレイのフォルダ {"dir": "<path>"}（無い＝自動）。JS から場所を渡す口は作らない
  （MEDIA のライブラリと同じ約束。choose_dir を呼ぶのは app.py の replay_pick_folder＝ネイティブのダイアログだけ）
- config/replays_cache.json … .bsor の頭と数（精度・ミス…）の控え（場所・大きさ・更新時刻ごと。消しても読み直すだけ）
- replays/maps/<hash>/ … 書き出しの控え（Info.dat・難易度の .dat・カバー・nlm.json＝{songName, levelAuthor, exportedAt, egg, files}）
- replays/eggs/<sha1>.egg … song.egg（中身の SHA-1 ごとに 1 つ＝同じ音は 1 つ）

リプレイのフォルダの決め方（folders）: ① 環境変数 NLM_REPLAYS（os.pathsep 区切り・テスト用。あれば自動の検出をしない＝利用者の本物を読まない）
② config/replays.json の dir ③ 自動: MEDIA のライブラリに記録したフォルダから推定（BSManager の SharedMaps/CustomLevels → BSInstances/*/UserData/
BeatLeader/Replays の全部、<X>/Beat Saber_Data/CustomLevels → <X>/UserData/BeatLeader/Replays）＋ Steam の既定の場所。見つかった全部を合わせる。読むだけ。

一覧の「この曲」: 書き出しの控えの nlm.json の songName・levelAuthor が、送られた name・mapper と同じ（前後の空白を除き大文字小文字を区別しない）
控えの hash の集まり H。hash が H に入り音（egg）も控えてあるリプレイ＝playable。.bsor の頭の曲名・マッパーが同じで遊べない物＝playable:false。
id はこの起動の間だけ使える不透明な文字列（場所の SHA-256 に起動ごとの塩）＝JS からパスは受けない。

BL のリプレイアプリ（replay-viewer/blreplay/）は本体と別のオリジン（http://localhost:<本体の番号＋20>）で出す（ViewerHandler）。同じオリジンの
iframe は本体の画面（DOM・合言葉）に触れるため。出すのは GET の /blreplay/…・/bridge.js・/blr/<鍵>/<名前>（使い捨ての鍵＝その 1 件の .bsor と
map.zip）だけ。名前は localhost（::1 と 127.0.0.1 の両方で同じ番号で待つ＝どちらへつないでも待たない）。本体（127.0.0.1）と名前が違う＝別のサイト＝
ブラウザが別の流れ（プロセス）で描く（ANP で 127.0.0.1 の別の番号だと本体の描画にリプレイが待たされた）。
"""
import errno
import hashlib
import json
import math
import os
import posixpath
import re
import secrets
import shutil
import socket
import struct
import sys
import threading
import time
import zipfile
import http.server
from urllib.parse import quote, unquote, urlsplit

import bsor
import map_hash
from native_paths import _npath, _lpath, _path_kind, _is_under

DIFFS = ('Easy', 'Normal', 'Hard', 'Expert', 'ExpertPlus')
STEAM_REPLAYS = r'C:\Program Files (x86)\Steam\steamapps\common\Beat Saber\UserData\BeatLeader\Replays'
KEEP_MAX = 64 * 1024 * 1024     # /__replay/keep の本体（Info.dat・難易度の .dat・カバー）の上限
EGG_MAX = 300 * 1024 * 1024     # /__replay/keepEgg の本体（song.egg）の上限
KEEP_FILES_MAX = 64             # keep で受けるファイルの数の上限
NAME_MAX = 128                  # keep で受けるファイル名の長さの上限
STR_MAX = 256                   # ファイルから読んだ文字列の長さの上限
BSOR_MAX = 256 * 1024 * 1024    # 読む .bsor の大きさの上限（普通は数 MB）
DIR_FILES_MAX = 100000          # 1 つのフォルダで見る .bsor の数の上限（暴走防止）
TOKENS_MAX = 8                  # 覚えておく使い捨ての鍵（開くたびに 1 つ）
VIEWER_DELTA = 20               # viewer の番号＝本体の番号＋これ（使われていれば OS が選ぶ）
CACHE_VER = 1                   # replays_cache.json の形（bsor の数え方を変えたら上げる）
IMAGE_EXTS = ('.png', '.jpg', '.jpeg', '.webp', '.gif', '.bmp')
HASH_RE = re.compile(r'[0-9a-f]{40}')
TOKEN_RE = re.compile(r'[A-Za-z0-9_-]{24,64}')
# BeatLeader のリプレイのファイル名: <プレイヤー>-[practice-][fail-][exit-]<曲名>-<難易度>-<モード>-<HASH>-<時刻>.bsor
# exit＝途中でやめた（ポーズからメニューへ・やり直し）プレイ（.bsor の中には印が無い）
FLAGS_RE = re.compile(r'^[^-]+((?:-(?:practice|fail|exit))*)-')


class ReplayError(Exception):
    """利用者に見せる失敗。code は JS 側で訳す（not-found・no-map・viewer-failed・bad-request・too-large・bad-name・bad-map・bad-sha1・
    bad-replay・bad-path・failed＝書けなかった）"""
    def __init__(self, code):
        super().__init__(code)
        self.code = code


# ---------------------------------------------------------------- 小さな部品

def _str(v, n=STR_MAX):
    return v[:n] if isinstance(v, str) else ''


def _norm(v):
    """曲名・マッパー名の比べ方（前後の空白を除き大文字小文字を区別しない）"""
    return v.strip().casefold() if isinstance(v, str) else ''


_RESERVED = re.compile(r'(con|prn|aux|nul|com[0-9]|lpt[0-9])(\..*)?', re.I)   # Windows の装置の名前（CON.dat 等）


def _plain(name):
    """フォルダ直下の 1 つの名前か（.. や区切り文字・ドライブ名・装置の名前で外の物を指させない）"""
    return (isinstance(name, str) and 0 < len(name) <= NAME_MAX and name not in ('.', '..') and name == name.strip()
            and not any(c in name for c in '/\\:*?"<>|') and all(ord(c) >= 32 for c in name)
            and not name.endswith('.') and not _RESERVED.fullmatch(name))


def _write_atomic(path, data):
    """一時ファイルに書き終えてから置き換える（読み手が書きかけを見ない・途中で落ちても前の中身が残る）。
    Windows では置き換え先を他が開いていると失敗する（ウイルス対策ソフト等）ので少し待ってやり直す"""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = '%s.%s.tmp' % (path, secrets.token_hex(4))
    with open(tmp, 'wb') as f:
        f.write(data)
    for i in range(20):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            if i == 19:
                try:
                    os.remove(tmp)
                except OSError:
                    pass
                raise
            time.sleep(0.05)


def _decode_json(b):
    try:
        try:
            s = b.decode('utf-8-sig')
        except UnicodeDecodeError:
            return None
        return json.loads(s)
    except (ValueError, RecursionError):
        return None


def _discard(rfile, n):
    try:
        while n > 0:
            d = rfile.read(min(n, 1 << 20))
            if not d:
                break
            n -= len(d)
    except OSError:
        pass


def name_flags(name):
    m = FLAGS_RE.match(name)
    return set(m.group(1).split('-')[1:]) if m else set()


def replays_for_levels(levels):
    """Beat Saber の曲のフォルダ（CustomLevels）→ そのゲームのリプレイの置き場の候補（新しい版から）"""
    p = os.path.normpath(levels)
    name, parent = os.path.basename(p).lower(), os.path.dirname(p)
    if name != 'customlevels':
        return []
    if os.path.basename(parent).lower() == 'sharedmaps':   # BSManager の共有: <BSManager>/SharedContent/SharedMaps/CustomLevels
        root = os.path.dirname(os.path.dirname(parent))
        inst = os.path.join(root, 'BSInstances')
        try:
            vs = sorted((e.name for e in os.scandir(inst) if e.is_dir()), reverse=True)
        except OSError:
            return []
        return [os.path.join(inst, v, 'UserData', 'BeatLeader', 'Replays') for v in vs]
    if os.path.basename(parent).lower() == 'beat saber_data':   # ゲームのフォルダ: <X>/Beat Saber_Data/CustomLevels
        return [os.path.join(os.path.dirname(parent), 'UserData', 'BeatLeader', 'Replays')]
    return []


def _info_text(info, *keys):
    for k in keys:
        cur = info
        for part in k.split('.'):
            cur = cur.get(part) if isinstance(cur, dict) else None
        if isinstance(cur, str):
            return cur
    return ''


def _level_author(info):
    v = _info_text(info, '_levelAuthorName')
    if v:
        return v
    ms = ((info.get('beatmapAuthors') or {}).get('mappers') if isinstance(info.get('beatmapAuthors'), dict) else None) or []
    return ', '.join(m for m in ms if isinstance(m, str))


def _song_file(info):
    n = _info_text(info, '_songFilename', 'audio.songFilename')
    return n if _plain(n) else 'song.egg'


def _cover_file(info):
    n = _info_text(info, '_coverImageFilename', 'coverImageFilename')
    return n if _plain(n) and n.lower().endswith(IMAGE_EXTS) else ''


def _info_bpm(info):
    """Info.dat の基準の BPM（v2 の _beatsPerMinute・v4 の audio.bpm）。正の有限の数でなければ None"""
    for k in ('_beatsPerMinute', 'audio.bpm'):
        cur = info
        for part in k.split('.'):
            cur = cur.get(part) if isinstance(cur, dict) else None
        if isinstance(cur, (int, float)) and not isinstance(cur, bool) and math.isfinite(cur) and 0 < cur < 100000:
            return cur
    return None


def _viewer_dat(b, bpm):
    """viewer へ渡す難易度の .dat: v3 の bpmEvents に拍 0 の物が無ければ、拍 0 に基準の BPM（bpm）を足したバイト列。直す要が無ければ b のまま。
    BL のリプレイアプリ（build の timeConvertor）は、最初の BPM の変化が拍 0 に無いと、その前の拍まで変化の後の BPM で秒にする
    （ゲームは最初の変化までを Info.dat の BPM で数える）＝テンポパートのある NLM の書き出し（拍 0 を書かない）でノーツの時刻がずれて出なかった。
    写した物（replay-viewer/blreplay/）には手を入れず、渡す譜面の方を直す。hash は控えの元のファイルで数えるので、ここで変えても関係ない"""
    if bpm is None:
        return b
    d = _decode_json(b)
    ev = d.get('bpmEvents') if isinstance(d, dict) else None
    if not isinstance(ev, list) or not ev:
        return b
    beats = [e.get('b', 0) for e in ev if isinstance(e, dict)]
    if not beats or not all(isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x) for x in beats):
        return b
    if min(beats) <= 0:
        return b
    d['bpmEvents'] = [{'b': 0, 'm': bpm}] + sorted((e for e in ev if isinstance(e, dict)), key=lambda e: e.get('b', 0))
    return json.dumps(d, ensure_ascii=False, separators=(',', ':')).encode('utf-8')


def _map_files(info):
    """Info.dat が指す（hash に足す）ファイル名の並び。どれか 1 つでも 1 つの名前の .dat でなければ None"""
    ns = map_hash.files_for_hash(info)
    if not all(_plain(n) and n.lower().endswith('.dat') and n.lower() != 'info.dat' for n in ns):
        return None
    return ns


def _head_of(info):
    """.bsor の頭 → 一覧に使う物だけ（ファイル由来＝形を確かめ、文字は切り詰める）"""
    h = _str(info.get('hash'), 64).strip().lower()
    try:
        ts = int(str(info.get('timestamp') or '').strip())
        ts = ts if 0 < ts < 10 ** 11 else None
    except ValueError:
        ts = None
    jd = info.get('jump_distance')
    ft = info.get('fail_time')
    d = info.get('difficulty')
    return {'song': _str(info.get('song_name')), 'mapper': _str(info.get('mapper')), 'hash': h if HASH_RE.fullmatch(h) else '',
            'diff': d if d in DIFFS else None, 'mode': _str(info.get('mode'), 32), 'ts': ts, 'mods': _str(info.get('modifiers'), 64),
            'jd': round(jd, 3) if isinstance(jd, float) and math.isfinite(jd) and 0 < jd < 1000 else None,
            'fail': isinstance(ft, float) and math.isfinite(ft) and ft > 0}


_HEAD_KEYS = {'song', 'mapper', 'hash', 'diff', 'mode', 'ts', 'mods', 'jd', 'fail'}
_SUM_KEYS = {'misses', 'bad', 'bombs', 'walls', 'acc', 'end'}


def _sum_of(s):
    """bsor.summary → 控えに書く物（数の形を確かめる）"""
    out = {}
    for k in ('misses', 'bad', 'bombs', 'walls'):
        v = s.get(k)
        out[k] = v if isinstance(v, int) and not isinstance(v, bool) and v >= 0 else None
    a = s.get('acc')
    out['acc'] = a if isinstance(a, float) and 0 <= a <= 1 else None
    e = s.get('end')
    out['end'] = e if isinstance(e, float) and math.isfinite(e) and e >= 0 else None
    return out


# ---------------------------------------------------------------- 置き場・一覧・控え

class ReplayStore:
    def __init__(self, data_dir, base_dir, library=None, env_dirs=None):
        """data_dir＝serve.py の DATA_DIR（書く所）・base_dir＝BASE_DIR（replay-viewer/ の置き場）。library＝serve.LIBRARY（記録したフォルダから
        リプレイの置き場を推定する）。env_dirs＝環境変数 NLM_REPLAYS の値（None＝無い）"""
        self.config_dir = os.path.join(data_dir, 'config')
        self.choice_file = os.path.join(self.config_dir, 'replays.json')
        self.cache_file = os.path.join(self.config_dir, 'replays_cache.json')
        self.maps_root = os.path.join(data_dir, 'replays', 'maps')
        self.eggs_root = os.path.join(data_dir, 'replays', 'eggs')
        self.viewer_root = os.path.join(base_dir, 'replay-viewer')   # 中身は blreplay/（BL のリプレイアプリの写し）と bridge.js
        self.library = library
        self.env_dirs = None if env_dirs is None else [p for p in env_dirs.split(os.pathsep) if p.strip()]
        self.steam_default = STEAM_REPLAYS   # テストで差し替える
        self._salt = secrets.token_bytes(16)
        self._ids = {}                       # id → .bsor の場所（一覧に出した物）
        self._lock = threading.RLock()       # 控え（replays_cache.json）・id の表
        self._keep_lock = threading.Lock()   # 書き出しの控え（maps/・eggs/）
        self._cache, self._cache_dirty = None, False
        self._kept = {}                      # 控えのフォルダ → (nlm.json の更新時刻, 中身)
        self._tok_lock = threading.Lock()
        self._tokens = {}                    # 鍵 → {bsor, name, hash, at}

    # ---- リプレイのフォルダ ----
    def _chosen(self):
        try:
            with open(self.choice_file, 'r', encoding='utf-8') as f:
                d = json.load(f)
        except (OSError, ValueError):
            return None
        p = d.get('dir') if isinstance(d, dict) else None
        return p if _path_kind(p) else None   # ドライブ名から始まる絶対パスか UNC だけ（壊れた・書き換えられた記録は使わない）

    def folders(self):
        """→ (source: 'env'|'chosen'|'auto'|'none', [フォルダ…])"""
        if self.env_dirs is not None:
            return 'env', list(self.env_dirs)
        c = self._chosen()
        if c:
            return 'chosen', [c]
        cands = []
        if self.library is not None:
            try:
                libs = self.library.list()
            except Exception:
                libs = []
            for l in libs:
                p = l.get('path') if isinstance(l, dict) else None
                if _path_kind(p) == 'local':   # ネットワークの場所（UNC）からは推定しない＝選んだフォルダの外の場所に触れない
                    cands += replays_for_levels(p)
        if self.steam_default:
            cands.append(self.steam_default)
        out, seen = [], set()
        for p in cands:
            k = _lpath(p)
            if k not in seen and os.path.isdir(p):
                seen.add(k)
                out.append(p)
        return ('auto' if out else 'none'), out

    def _bsor_files(self, d):
        """フォルダの .bsor → [(場所, 名前, stat)]（読めないフォルダは空）"""
        out = []
        try:
            with os.scandir(d) as it:
                for e in it:
                    if len(out) >= DIR_FILES_MAX:
                        break
                    if e.name.lower().endswith('.bsor'):
                        try:
                            if e.is_file():
                                out.append((e.path, e.name, e.stat()))
                        except OSError:
                            pass
        except OSError:
            pass
        return out

    def status(self):
        src, dirs = self.folders()
        rows = []
        for d in dirs:
            row = {'path': d, 'count': len(self._bsor_files(d))}
            if not os.path.isdir(d):
                row['missing'] = True
            rows.append(row)
        return {'ok': True, 'source': src, 'dirs': rows}

    def choose_dir(self, path):
        """ダイアログで選ばれたフォルダを記録する（app.py の replay_pick_folder からだけ呼ぶ）→ status と同じ形"""
        if not _path_kind(path):
            raise ReplayError('bad-path')
        if not os.path.isdir(path):
            raise ReplayError('not-found')
        _write_atomic(self.choice_file, json.dumps({'dir': path}, ensure_ascii=False).encode('utf-8'))
        return self.status()

    def reset_folder(self):
        """選んだフォルダを忘れて自動へ戻す → status と同じ形"""
        try:
            os.remove(self.choice_file)
        except FileNotFoundError:
            pass
        except OSError:
            raise ReplayError('failed')
        return self.status()

    # ---- .bsor の頭と数の控え（config/replays_cache.json） ----
    def _cache_open(self):
        if self._cache is None:
            items = {}
            try:
                with open(self.cache_file, 'r', encoding='utf-8') as f:
                    d = json.load(f)
                if isinstance(d, dict) and d.get('v') == CACHE_VER and isinstance(d.get('items'), dict):
                    for k, v in d['items'].items():   # 形の違う物（手で直した・壊れた）は読み直す
                        if (isinstance(v, list) and len(v) == 4 and isinstance(v[0], int) and isinstance(v[1], int)
                                and (v[2] is None or (isinstance(v[2], dict) and _HEAD_KEYS <= set(v[2])))
                                and (v[3] is None or (isinstance(v[3], dict) and _SUM_KEYS <= set(v[3])))):
                            items[k] = v
            except (OSError, ValueError):
                pass
            self._cache = items
        return self._cache

    def _cache_save(self, keep_keys=None):
        if keep_keys is not None:   # 今のフォルダに無くなったファイルの分は消す
            for k in [k for k in self._cache if k not in keep_keys]:
                del self._cache[k]
                self._cache_dirty = True
        if not self._cache_dirty:
            return
        try:
            _write_atomic(self.cache_file, json.dumps({'v': CACHE_VER, 'items': self._cache}, ensure_ascii=False,
                                                      separators=(',', ':')).encode('utf-8'))
            self._cache_dirty = False
        except OSError:
            pass   # 書けなくても次に読み直すだけ

    def _entry(self, path, st):
        """→ [更新時刻, 大きさ, 頭（読めなければ None）, 数（まだなら None）]"""
        key = _lpath(path)
        ent = self._cache.get(key)
        if ent and ent[0] == st.st_mtime_ns and ent[1] == st.st_size:
            return ent
        head = None
        if st.st_size <= BSOR_MAX:
            try:
                head = _head_of(bsor.read_info(path))
            except (OSError, bsor.BsorError, ValueError, struct.error):
                head = None
        ent = [st.st_mtime_ns, st.st_size, head, None]
        self._cache[key] = ent
        self._cache_dirty = True
        return ent

    def _summary(self, path, ent):
        if ent[3] is None:
            try:
                ent[3] = _sum_of(bsor.summary(bsor.read(path)))
            except (OSError, bsor.BsorError, ValueError, MemoryError, struct.error):
                ent[3] = {'bad': None, 'misses': None, 'bombs': None, 'walls': None, 'acc': None, 'end': None, 'err': True}
            self._cache_dirty = True
        return ent[3]

    def _id(self, path):
        i = hashlib.sha256(self._salt + _lpath(path).encode('utf-8')).hexdigest()[:24]
        self._ids[i] = path
        return i

    def _path_of(self, rid):
        """id → .bsor の場所（今のフォルダの中にある物だけ）。無ければ ReplayError('not-found')"""
        if not isinstance(rid, str) or not re.fullmatch(r'[0-9a-f]{24}', rid):
            raise ReplayError('not-found')
        _, dirs = self.folders()
        with self._lock:
            p = self._ids.get(rid)
            if p is None:   # まだ一覧に出していない（一覧より先に頼まれた）→ 今のフォルダから探す
                for d in dirs:
                    for path, _, _ in self._bsor_files(d):
                        if self._id(path) == rid:
                            p = path
                            break
                    if p:
                        break
        if not p or not any(_lpath(os.path.dirname(p)) == _lpath(d) for d in dirs) or not os.path.isfile(p):
            raise ReplayError('not-found')
        return p

    # ---- 書き出しの控え（replays/maps/・replays/eggs/） ----
    def _kept_meta(self, h):
        """控えの nlm.json の中身（形を確かめた物）か None"""
        d = os.path.join(self.maps_root, h)
        f = os.path.join(d, 'nlm.json')
        try:
            fs = os.stat(f)
            mt = (fs.st_mtime_ns, fs.st_size)
        except OSError:
            self._kept.pop(d, None)
            return None
        hit = self._kept.get(d)
        if hit and hit[0] == mt:
            return hit[1]
        try:
            with open(f, 'rb') as fp:
                raw = _decode_json(fp.read(1024 * 1024))
        except OSError:
            raw = None
        if not isinstance(raw, dict):
            return None
        egg = raw.get('egg')
        ex = raw.get('exportedAt')
        meta = {'songName': _str(raw.get('songName')), 'levelAuthor': _str(raw.get('levelAuthor')),
                'exportedAt': round(float(ex), 3) if isinstance(ex, (int, float)) and not isinstance(ex, bool) and math.isfinite(ex) else None,
                'egg': egg if isinstance(egg, str) and HASH_RE.fullmatch(egg) else None,
                'files': [n for n in (raw.get('files') or []) if _plain(n)][:KEEP_FILES_MAX] if isinstance(raw.get('files'), list) else []}
        self._kept[d] = (mt, meta)
        return meta

    def _egg_ok(self, meta):
        return bool(meta and meta['egg'] and os.path.isfile(os.path.join(self.eggs_root, meta['egg'] + '.egg')))

    def _sweep_tmp(self, age=3600):
        """途中で止まった書き出し（maps/・eggs/ の *.tmp）のうち古い物を片付ける"""
        now = time.time()
        for root in (self.maps_root, self.eggs_root):
            try:
                with os.scandir(root) as it:
                    old = [e.path for e in it if e.name.endswith('.tmp') and now - e.stat().st_mtime > age]
            except OSError:
                continue
            for p in old:
                if os.path.isdir(p):
                    shutil.rmtree(p, ignore_errors=True)
                else:
                    try:
                        os.remove(p)
                    except OSError:
                        pass

    def _kept_all(self):
        out = {}
        try:
            with os.scandir(self.maps_root) as it:
                names = [e.name for e in it if HASH_RE.fullmatch(e.name)]
        except OSError:
            names = []
        for h in names:
            m = self._kept_meta(h)
            if m:
                out[h] = m
        return out

    def keep(self, m, body):
        """/__replay/keep: 書き出した譜面を hash ごとに控える。m＝JSON {files:[{name,size}]}（文字列）・body＝その順に繋げたバイト列。
        → {ok, hash, isNew, needEgg}"""
        try:
            meta = json.loads(m) if isinstance(m, str) and len(m) <= 65536 else None
        except ValueError:
            meta = None
        files = meta.get('files') if isinstance(meta, dict) else None
        if not isinstance(files, list) or not 0 < len(files) <= KEEP_FILES_MAX:
            raise ReplayError('bad-request')
        got, seen, pos = {}, set(), 0
        for it in files:
            name = it.get('name') if isinstance(it, dict) else None
            size = it.get('size') if isinstance(it, dict) else None
            if not isinstance(size, int) or isinstance(size, bool) or size < 0:
                raise ReplayError('bad-request')
            if not _plain(name) or not name.lower().endswith(('.dat',) + IMAGE_EXTS) or name.casefold() in seen:
                raise ReplayError('bad-name')
            seen.add(name.casefold())
            got[name] = body[pos:pos + size]
            pos += size
        if pos != len(body):
            raise ReplayError('bad-request')
        info_name = next((n for n in got if n.casefold() == 'info.dat'), None)
        info = _decode_json(got[info_name]) if info_name else None
        if not isinstance(info, dict):
            raise ReplayError('bad-map')
        need = _map_files(info)
        by_fold = {n.casefold(): n for n in got}
        if need is None or any(n.casefold() not in by_fold for n in need):
            raise ReplayError('bad-map')
        h = map_hash.compute(got[info_name], [got[by_fold[n.casefold()]] for n in need])
        cover = _cover_file(info)
        cover = by_fold.get(cover.casefold()) if cover else None
        store = {'Info.dat': got[info_name]}
        for n in need:
            store.setdefault(n, got[by_fold[n.casefold()]])
        if cover:
            store.setdefault(cover, got[cover])
        now = round(time.time(), 3)   # unix 秒（小数 3 桁＝同じ秒に 2 回書き出しても順が分かる）
        with self._keep_lock:
            d = os.path.join(self.maps_root, h)
            old = self._kept_meta(h)
            if old is None:
                self._sweep_tmp()
                tmp = os.path.join(self.maps_root, '%s.%s.tmp' % (h, secrets.token_hex(4)))
                try:
                    os.makedirs(tmp)
                    for n, b in store.items():
                        with open(os.path.join(tmp, n), 'wb') as f:
                            f.write(b)
                    rec = {'songName': _str(_info_text(info, '_songName', 'song.title')), 'levelAuthor': _str(_level_author(info)),
                           'exportedAt': now, 'egg': None, 'files': list(store)}
                    with open(os.path.join(tmp, 'nlm.json'), 'w', encoding='utf-8') as f:
                        json.dump(rec, f, ensure_ascii=False)
                    if os.path.isdir(d):   # nlm.json の無い（途中で止まった）古い控え
                        shutil.rmtree(d, ignore_errors=True)
                    os.rename(tmp, d)
                    self._kept.pop(d, None)
                except OSError:
                    shutil.rmtree(tmp, ignore_errors=True)
                    raise ReplayError('failed')
                return {'ok': True, 'hash': h, 'isNew': True, 'needEgg': True}
            # もう控えてある（同じ hash＝Info.dat と難易度は同じ）: 書き出した時刻とカバーだけ新しくする
            try:
                if cover:
                    _write_atomic(os.path.join(d, cover), store[cover])
                rec = dict(old, exportedAt=now)
                if cover and cover not in rec['files']:
                    rec['files'] = rec['files'] + [cover]
                _write_atomic(os.path.join(d, 'nlm.json'), json.dumps(rec, ensure_ascii=False).encode('utf-8'))
                self._kept.pop(d, None)
            except OSError:
                raise ReplayError('failed')
            return {'ok': True, 'hash': h, 'isNew': False, 'needEgg': not self._egg_ok(self._kept_meta(h))}

    def keep_egg(self, h, sha1, rfile, n):
        """/__replay/keepEgg: 本体（song.egg・n バイト）の SHA-1 を確かめて eggs/ に置き（あれば置かない）、控え h の音をこれにする
        （後から書いた方が勝つ＝無音追加だけ変えた書き出しは hash が同じで音だけ違う）。本体はどの場合も n バイト読み切る"""
        h = h.lower() if isinstance(h, str) else ''
        sha1 = sha1.lower() if isinstance(sha1, str) else ''
        err = None
        if not HASH_RE.fullmatch(h) or not HASH_RE.fullmatch(sha1):
            err = 'bad-request'
        elif n <= 0:
            err = 'bad-request'
        elif self._kept_meta(h) is None:
            err = 'no-map'
        if err:
            _discard(rfile, n)
            raise ReplayError(err)
        try:
            os.makedirs(self.eggs_root, exist_ok=True)
        except OSError:
            _discard(rfile, n)
            raise ReplayError('failed')
        final = os.path.join(self.eggs_root, sha1 + '.egg')
        tmp = '%s.%s.tmp' % (final, secrets.token_hex(4))
        dig, left = hashlib.sha1(), n
        try:
            with open(tmp, 'wb') as f:
                while left > 0:
                    b = rfile.read(min(left, 1 << 20))
                    if not b:
                        break
                    dig.update(b)
                    f.write(b)
                    left -= len(b)
        except OSError:
            _discard(rfile, left)
            left = -1
        if left != 0 or dig.hexdigest() != sha1:
            try:
                os.remove(tmp)
            except OSError:
                pass
            raise ReplayError('bad-request' if left else 'bad-sha1')
        with self._keep_lock:
            try:
                if os.path.isfile(final):
                    os.remove(tmp)   # 同じ音はもうある
                else:
                    os.replace(tmp, final)
                old = self._kept_meta(h)
                if old is None:
                    raise ReplayError('no-map')
                if old['egg'] != sha1:
                    _write_atomic(os.path.join(self.maps_root, h, 'nlm.json'),
                                  json.dumps(dict(old, egg=sha1), ensure_ascii=False).encode('utf-8'))
                    self._kept.pop(os.path.join(self.maps_root, h), None)
            except OSError:
                raise ReplayError('failed')
        return {'ok': True}

    # ---- 一覧 ----
    def list(self, song):
        """/__replay/list {song:{name, mapper}} → {ok, status, items:[…新しい順]}"""
        if not isinstance(song, dict) or not isinstance(song.get('name'), str) or not isinstance(song.get('mapper', ''), str):
            raise ReplayError('bad-request')
        name, mapper = _norm(song.get('name')), _norm(song.get('mapper') or '')
        st = self.status()
        kept = {h: m for h, m in self._kept_all().items() if name and _norm(m['songName']) == name and _norm(m['levelAuthor']) == mapper}
        latest = max(kept, key=lambda h: (kept[h]['exportedAt'] or 0, h)) if kept else None
        items = []
        if name:
            _, dirs = self.folders()
            with self._lock:
                self._cache_open()
                keys = set()
                for d in dirs:
                    for path, fname, fst in self._bsor_files(d):
                        keys.add(_lpath(path))
                        ent = self._entry(path, fst)
                        head = ent[2]
                        if not head:
                            continue
                        h = head['hash']
                        if h in kept:
                            playable = self._egg_ok(kept[h])
                        elif _norm(head['song']) == name and _norm(head['mapper']) == mapper:
                            playable = False
                        else:
                            continue
                        s = self._summary(path, ent)
                        flags = name_flags(fname)
                        items.append({
                            'id': self._id(path), 'file': _str(fname, 255), 'playedAt': head['ts'] or int(fst.st_mtime),
                            'diff': head['diff'], 'mode': head['mode'], 'hash': h, 'fail': bool(head['fail'] or 'fail' in flags),
                            'exit': 'exit' in flags, 'practice': 'practice' in flags, 'acc': s.get('acc'),
                            'misses': s.get('misses'), 'bad': s.get('bad'), 'bombs': s.get('bombs'), 'walls': s.get('walls'),
                            'mods': head['mods'], 'endSec': s.get('end'), 'jd': head['jd'], 'playable': playable,
                            'exportedAt': kept[h]['exportedAt'] if h in kept else None, 'latest': h == latest})
                self._cache_save(keys)
        items.sort(key=lambda r: (-r['playedAt'], r['file']))
        return {'ok': True, 'status': st, 'items': items}

    def _read(self, rid):
        p = self._path_of(rid)
        try:
            if os.path.getsize(p) > BSOR_MAX:
                raise ReplayError('bad-replay')
            return p, bsor.read(p)
        except (OSError, bsor.BsorError, ValueError, MemoryError, struct.error):
            raise ReplayError('bad-replay')

    def events(self, rid):
        """/__replay/events {id} → {ok, notes, walls, endSec}（bsor.events）"""
        _, rep = self._read(rid)
        ev = bsor.events(rep)
        return {'ok': True, 'notes': ev['notes'], 'walls': ev['walls'], 'endSec': ev['endSec']}

    # ---- 開く（使い捨ての鍵と viewer） ----
    def open(self, rid, t, main_port):
        """/__replay/open {id, t?} → {ok, url, origin, endSec, diff, mode, hash}。t＝開く位置（song.egg の秒）"""
        if t is not None and (isinstance(t, bool) or not isinstance(t, (int, float)) or not math.isfinite(t)):
            raise ReplayError('bad-request')
        p, rep = self._read(rid)
        head = _head_of(rep['info'])
        h = head['hash']
        meta = self._kept_meta(h) if h else None
        if not self._egg_ok(meta):
            raise ReplayError('no-map')
        if not os.path.isfile(os.path.join(self.viewer_root, 'blreplay', 'index.html')):
            raise ReplayError('viewer-failed')
        try:
            origin = viewer_origin(main_port, self)
        except OSError:
            raise ReplayError('viewer-failed')
        tok = secrets.token_urlsafe(24)
        name = os.path.basename(p)
        with self._tok_lock:
            self._tokens[tok] = {'bsor': p, 'name': name, 'hash': h, 'at': time.time()}
            for old in sorted(self._tokens, key=lambda k: self._tokens[k]['at'])[:-TOKENS_MAX]:
                self._tokens.pop(old, None)
        base = '%s/blr/%s/' % (origin, tok)
        url = '%s/blreplay/index.html?link=%s&mapLink=%s' % (origin, quote(base + quote(name, safe=''), safe=''),
                                                            quote(base + 'map.zip', safe=''))
        if t is not None:
            url += '&time=%d' % max(0, round(t * 1000))
        return {'ok': True, 'url': url, 'origin': origin, 'endSec': bsor.summary_end(rep), 'diff': head['diff'],
                'mode': head['mode'], 'hash': h}

    def _map_zip(self, h):
        """控え h → map.zip のバイト列（Info.dat・難易度・カバー・song.egg＝名前は Info.dat の _songFilename・STORED）か None"""
        meta = self._kept_meta(h)
        if not self._egg_ok(meta):
            return None
        d = os.path.join(self.maps_root, h)
        try:
            with open(os.path.join(d, 'Info.dat'), 'rb') as f:
                info_b = f.read()
        except OSError:
            return None
        info = _decode_json(info_b)
        need = _map_files(info) if isinstance(info, dict) else None
        if need is None:
            return None
        import io
        buf = io.BytesIO()
        try:
            with zipfile.ZipFile(buf, 'w', zipfile.ZIP_STORED) as z:
                done = {'info.dat'}
                z.writestr('Info.dat', info_b)
                bpm = _info_bpm(info)
                for n in need:
                    if n.casefold() in done:
                        continue
                    done.add(n.casefold())
                    with open(os.path.join(d, n), 'rb') as f:
                        z.writestr(n, _viewer_dat(f.read(), bpm))
                cover = _cover_file(info)
                if cover and cover.casefold() not in done and os.path.isfile(os.path.join(d, cover)):
                    done.add(cover.casefold())
                    z.write(os.path.join(d, cover), cover)
                song = _song_file(info)
                if song.casefold() not in done:
                    z.write(os.path.join(self.eggs_root, meta['egg'] + '.egg'), song)
        except OSError:
            return None
        return buf.getvalue()

    def token_file(self, tok, name):
        """/blr/<鍵>/<名前> → (バイト列, 種類) か None（鍵が違う・知らない名前）"""
        if not TOKEN_RE.fullmatch(tok or ''):
            return None
        with self._tok_lock:
            t = self._tokens.get(tok)
        if not t:
            return None
        if name == 'map.zip':
            z = self._map_zip(t['hash'])
            return (z, 'application/zip') if z is not None else None
        if name == t['name']:
            try:
                with open(t['bsor'], 'rb') as f:
                    return f.read(BSOR_MAX), 'application/octet-stream'
            except OSError:
                return None
        return None


# ---------------------------------------------------------------- viewer（BL のリプレイアプリを別のオリジンで出す）

VIEWER_NAMES = ('localhost', '127.0.0.1', '::1')
_VIEWERS, _VLOCK = {}, threading.Lock()   # 本体の番号 → [viewer のサーバー（127.0.0.1・あれば ::1）]
_IN_USE = {errno.EADDRINUSE, errno.EACCES, 10048, 10013}   # 番号が使われている（Windows の WSAEADDRINUSE・排他で断られた WSAEACCES も）
_CTYPES = {
    '.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.mjs': 'text/javascript; charset=utf-8',
    '.css': 'text/css; charset=utf-8', '.json': 'application/json', '.map': 'application/json', '.wasm': 'application/wasm',
    '.svg': 'image/svg+xml', '.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.gif': 'image/gif',
    '.webp': 'image/webp', '.ico': 'image/x-icon', '.woff': 'font/woff', '.woff2': 'font/woff2', '.ttf': 'font/ttf',
    '.otf': 'font/otf', '.eot': 'application/vnd.ms-fontobject', '.ogg': 'audio/ogg', '.mp3': 'audio/mpeg', '.wav': 'audio/wav',
    '.glb': 'model/gltf-binary', '.gltf': 'model/gltf+json', '.txt': 'text/plain; charset=utf-8', '.md': 'text/plain; charset=utf-8',
}


class _ViewerHTTP(http.server.ThreadingHTTPServer):
    """viewer の番号（同じ番号をほかと分け合わない＝Windows は SO_REUSEADDR だと使われている番号でも待ててしまい、要求がどちらに
    届くか決まらない。ANP の 2026-11-15 のスキャン F1）"""
    allow_reuse_address = False
    daemon_threads = True
    main_port = 0
    store = None

    def handle_error(self, request, client_address):
        """BL のリプレイアプリは .bsor・音を少しずつ読み、途中で読むのをやめて接続を切る（つなぎっぱなしの接続も閉じる）＝その時の
        「接続を切られた」は異常ではないので黙る（既定は例外の全文を標準エラーへ出し、python serve.py の画面がそれで埋まった）。ほかの例外は今までどおり"""
        e = sys.exc_info()[1]
        if isinstance(e, (ConnectionResetError, ConnectionAbortedError, BrokenPipeError, socket.timeout, TimeoutError)):
            return
        super().handle_error(request, client_address)

    def server_bind(self):
        if hasattr(socket, 'SO_EXCLUSIVEADDRUSE'):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


class _ViewerHTTP6(_ViewerHTTP):
    address_family = socket.AF_INET6


def _host_port(hostport):
    """'localhost:8158' / '[::1]:8158' → ('localhost', '8158')（小文字）"""
    hp = (hostport or '').strip().lower()
    if hp.startswith('['):
        i = hp.find(']')
        if i < 0:
            return hp, ''
        rest = hp[i + 1:]
        return hp[1:i], rest[1:] if rest.startswith(':') else ''
    if hp.count(':') == 1:
        a, b = hp.split(':')
        return a, b
    return hp, ''


class ViewerHandler(http.server.BaseHTTPRequestHandler):
    """viewer の番号の受け答え（GET・HEAD の /blreplay/…・/bridge.js・/blr/<鍵>/<名前> だけ）"""
    protocol_version = 'HTTP/1.1'   # つなぎっぱなし（ファイルごとにつなぎ直さない）
    timeout = 15                    # 使われていない接続を閉じるまでの秒
    server_version = 'NLM-replay-viewer'

    def version_string(self):
        return self.server_version

    def log_message(self, *a):   # 静かに
        pass

    def _parent(self):
        return 'http://127.0.0.1:%d' % self.server.main_port

    def end_headers(self):
        self.send_header('Content-Security-Policy', 'frame-ancestors ' + self._parent())   # 埋め込めるのは本体の画面からだけ
        self.send_header('X-Content-Type-Options', 'nosniff')
        super().end_headers()

    def _deny(self, code=403):
        self.close_connection = True
        self.send_error(code)

    def _ok(self):
        """Host がこの PC の名前＋この番号・Origin が付いていればこの番号のページ"""
        port = str(self.server.server_address[1])
        name, p = _host_port(self.headers.get('Host'))
        if name not in VIEWER_NAMES or p != port:
            return False
        org = self.headers.get('Origin')
        if org and org != 'null':
            try:
                u = urlsplit(org)
                return u.scheme == 'http' and (u.hostname or '') in VIEWER_NAMES and str(u.port) == port
            except ValueError:
                return False
        return True

    def do_POST(self):
        try:   # 小さい本体は読み捨ててから断る（読まずに閉じると Windows では接続がリセットされ、断った答えが届かないことがある）
            n = int(self.headers.get('Content-Length') or 0)
        except ValueError:
            n = 0
        if 0 < n <= 65536:
            _discard(self.rfile, n)
        self._deny()

    do_PUT = do_DELETE = do_PATCH = do_OPTIONS = do_POST

    def do_HEAD(self):
        self._get(head=True)

    def do_GET(self):
        self._get(head=False)

    def _range(self, total):
        """Range: bytes=a-b（1 つだけ）→ (a, b)・無い／使えない形＝None・範囲の外＝False。BL のリプレイアプリは .bsor の頭
        （bytes=0-8191）から少しずつ読む（200 で答えると「流して読めない」と知らせて全部を読み直す）"""
        r = (self.headers.get('Range') or '').strip()
        m = re.fullmatch(r'bytes=(\d*)-(\d*)', r)
        if not m or not (m.group(1) or m.group(2)):
            return None
        if m.group(1):
            a = int(m.group(1))
            b = min(int(m.group(2)), total - 1) if m.group(2) else total - 1
        else:   # 後ろから n バイト
            a, b = max(0, total - int(m.group(2))), total - 1
        return (a, b) if a <= b and a < total else False

    def _send(self, body, ctype, cache='no-store', etag=None, head=False):
        if etag and self.headers.get('If-None-Match') == etag:
            self.send_response(304)
            self.send_header('ETag', etag)
            self.send_header('Content-Length', '0')
            self.end_headers()
            return
        rg = self._range(len(body))
        if rg is False:
            self.send_response(416)
            self.send_header('Content-Range', 'bytes */%d' % len(body))
            self.send_header('Content-Length', '0')
            self.end_headers()
            return
        total = len(body)
        if rg:
            body = body[rg[0]:rg[1] + 1]
            self.send_response(206)
            self.send_header('Content-Range', 'bytes %d-%d/%d' % (rg[0], rg[1], total))
        else:
            self.send_response(200)
        self.send_header('Accept-Ranges', 'bytes')
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', cache)
        if etag:
            self.send_header('ETag', etag)
        self.end_headers()
        if not head:
            self.wfile.write(body)

    def _send_file(self, path, ctype, head):
        try:
            st = os.stat(path)
            etag = '"%x-%x"' % (st.st_mtime_ns, st.st_size)
            if self.headers.get('If-None-Match') == etag:
                return self._send(b'', ctype, etag=etag)
            f = open(path, 'rb')
        except OSError:
            return self._deny(404)
        with f:
            self.send_response(200)
            self.send_header('Content-Type', ctype)
            self.send_header('Content-Length', str(st.st_size))
            self.send_header('Cache-Control', 'no-cache')
            self.send_header('ETag', etag)
            self.end_headers()
            if not head:
                shutil.copyfileobj(f, self.wfile, 1 << 20)

    def _get(self, head):
        if not self._ok():
            return self._deny()
        raw = self.path.split('?', 1)[0].split('#', 1)[0]
        path = unquote(raw)
        store = self.server.store
        if store is None:
            return self._deny(404)
        if path.startswith('/blr/'):
            parts = path.split('/')
            got = store.token_file(parts[2], parts[3]) if len(parts) == 4 else None
            if got is None:
                return self._deny(404)
            return self._send(got[0], got[1], head=head)
        if path == '/bridge.js':
            return self._send_file(os.path.join(store.viewer_root, 'bridge.js'), _CTYPES['.js'], head)
        if path == '/blreplay':
            self.send_response(301)
            self.send_header('Location', '/blreplay/' + (('?' + self.path.split('?', 1)[1]) if '?' in self.path else ''))
            self.send_header('Content-Length', '0')
            self.end_headers()
            return
        if not path.startswith('/blreplay/'):
            return self._deny()
        rel = posixpath.normpath(path[len('/blreplay/'):]) if path != '/blreplay/' else ''
        parts = [p for p in rel.split('/') if p and p != '.']
        if any(p == '..' or '\\' in p or ':' in p or '\0' in p or os.path.splitdrive(p)[0] for p in parts):
            return self._deny(404)
        root = os.path.join(store.viewer_root, 'blreplay')
        if not parts or parts == ['index.html']:
            return self._index(root, head)
        f = os.path.join(root, *parts)
        try:   # 実体を解決した結果が写しの中であること（ジャンクションで外へ出ない）
            if not _is_under(_npath(root), _npath(f)) or not os.path.isfile(f):
                return self._deny(404)
        except (OSError, ValueError):
            return self._deny(404)
        ext = os.path.splitext(f)[1].lower()
        return self._send_file(f, _CTYPES.get(ext, 'application/octet-stream'), head)

    def _index(self, root, head):
        """BL のリプレイアプリの index.html に、伝言の受け手（/bridge.js）の <script> を </body> の前に足して出す（写した物は変えない）"""
        try:
            with open(os.path.join(root, 'index.html'), 'r', encoding='utf-8') as f:
                html = f.read()
        except (OSError, UnicodeDecodeError):
            return self._deny(404)
        tag = '<script src="/bridge.js" data-parent="%s"></script>\n' % self._parent()
        i = html.lower().rfind('</body>')
        html = html[:i] + tag + html[i:] if i >= 0 else html + tag
        self._send(html.encode('utf-8'), _CTYPES['.html'], cache='no-store', head=head)


def viewer_origin(main_port, store):
    """本体の番号 → viewer のオリジン（http://localhost:<番号>）。まだ待っていなければ待ち始める（最初の open の時）"""
    with _VLOCK:
        srvs = _VIEWERS.get(main_port)
        if srvs is None:
            srvs = []
            tries = [main_port + VIEWER_DELTA] if main_port + VIEWER_DELTA <= 65535 else []
            tries += [0, 0, 0]
            for p in tries:
                try:
                    v4 = _ViewerHTTP(('127.0.0.1', p), ViewerHandler)
                except OSError:
                    continue
                srvs = [v4]
                try:
                    srvs.append(_ViewerHTTP6(('::1', v4.server_address[1]), ViewerHandler))
                except OSError as e:
                    if e.errno in _IN_USE or getattr(e, 'winerror', None) in _IN_USE:   # ::1 の同じ番号がほかに使われていた → 別の番号で両方を試す
                        v4.server_close()
                        srvs = []
                        continue
                    # ::1 で待てない（IPv6 を切った等）→ 127.0.0.1 だけ（URL は localhost のまま）
                break
            if not srvs:
                raise OSError('viewer の番号を開けなかった')
            for srv in srvs:
                srv.main_port = main_port
                srv.store = store
                threading.Thread(target=srv.serve_forever, kwargs={'poll_interval': 0.2}, daemon=True, name='nlm-replay-viewer').start()
            _VIEWERS[main_port] = srvs
        for srv in srvs:
            srv.store = store
        return 'http://localhost:%d' % srvs[0].server_address[1]


def stop_viewers(main_port=None):
    """viewer を止める（本体のサーバーを止める時。main_port＝None は全部）"""
    with _VLOCK:
        ports = list(_VIEWERS) if main_port is None else [main_port]
        srvs = [s for p in ports for s in _VIEWERS.pop(p, [])]
    for srv in srvs:
        try:
            srv.shutdown()
            srv.server_close()
        except Exception:
            pass

# MEDIAライブラリ（譜面フォルダの記録・走査・キャッシュ・ファイル読み出し・エクスプローラーで開く・プレイ記録・2026-10-12）
#
# 追加したライブラリフォルダ（CustomLevels 等）を config/library.json に記録し、次回の起動でも自動で読む（exe版）。
# 以前は画面（JS）が File System Access API でフォルダを走査していたが、ハンドルはセッション限定で保存もできない
# （CLAUDE.md「WebView2 / File System Access API の重大な制約」）ため、Python 側でネイティブのパスを使って走査する。
#
# 安全のための約束（CLAUDE.md「セキュリティの約束事」）:
#  - 記録するフォルダは**ダイアログで選ばれた物だけ**（approve_dir は pywebview のフォルダ選択からだけ呼ぶ。JS から足す口は作らない）
#  - JS から受け取るのは id（記録の識別子）と相対パス・ファイル名だけ。相対パスは .. ・ドライブ名・\・:・NUL を拒否し、
#    実体を解決(realpath)した結果がライブラリの根の中であることを確かめる（ジャンクションで外へ出ない）
#  - UNC（\\server\share）は記録した字面の中だけ触る（native_paths.py の説明。app.py の _NativeAccess.may_touch と同じ考え方）
#  - ファイルから読んだ文字列・数値は信用しない（文字列は長さを切り、数値は範囲を確かめる）。CustomLevels は読むだけで何も書かない
#
# 呼び出し側（後で配線する）: serve.py の /__lib/*（scan・rescan・list・file・remove・open・extra・rate・playdata）と、
# app.py の pywebview Api（lib_pick_folder → approve_dir、lib_pick_playdata → set_playdata）。
# 失敗は LibError（code を JS 側で翻訳キーにする。rating_plugin.py の PluginError と同じ形）で返す。
import datetime
import hashlib
import json
import math
import os
import re
import struct
import threading
import time

import map_hash
from native_paths import _npath, _lpath, _path_kind, _is_under

AUDIO_EXTS = {'.egg', '.ogg', '.mp3', '.wav', '.flac', '.m4a', '.aac', '.opus'}   # 譜面フォルダの外の音源（JS の AUDIO_EXTS と同じ）
IMAGE_EXTS = {'.png', '.jpg', '.jpeg', '.webp', '.gif', '.bmp'}                     # 同じく画像（JS の IMAGE_EXTS と同じ）
READ_EXTS = {'.dat', '.json'} | AUDIO_EXTS | IMAGE_EXTS                            # read_file で返してよい種類
CONTENT_TYPES = {
    '.dat': 'application/json', '.json': 'application/json',
    '.egg': 'audio/ogg', '.ogg': 'audio/ogg', '.opus': 'audio/ogg', '.mp3': 'audio/mpeg', '.wav': 'audio/wav',
    '.flac': 'audio/flac', '.m4a': 'audio/mp4', '.aac': 'audio/aac',
    '.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.webp': 'image/webp', '.gif': 'image/gif',
    '.bmp': 'image/bmp',
}
MAX_DEPTH = 8                    # 何階層まで降りるか（JS の scanLibrary と同じ。アーティスト/アルバム/曲… の深い階層・暴走防止）
MAX_READ = 200 * 1024 * 1024     # read_file で返す1ファイルの上限
MAX_INFO = 16 * 1024 * 1024      # Info.dat の上限（普通は数KB）
MAX_PARSE = 64 * 1024 * 1024     # 難易度の .dat を解析する上限（超えたらハッシュだけ計算し、数は不明＝null。MAX_READ を超えたらハッシュも不明）
MAX_PLAYDATA = 64 * 1024 * 1024  # PlayerData.dat の上限（実物は数百KB）
MAX_ITEMS = 100000               # 1つのライブラリで返す譜面・ファイルの上限（暴走防止）
MAX_STR = 256                    # ファイルから読んだ文字列の長さの上限
CACHE_SAVE_SEC = 15              # 初回の走査の途中でもこの間隔でキャッシュを保存する（途中で閉じても次回はそこから速い）
# キャッシュの形式。MapEntry の項目・数え方を変えたら上げる（古いキャッシュを使わずに作り直す）。
# map_hash の規則（どのファイルをどの順に足すか）が変わった時は自動で作り直す（_hash_rule_tag をキャッシュの鍵に入れてある）
CACHE_VERSION = 2   # 2: 難易度に req（必要な Mod だけ）を足した（2026-10-12）
RATING_MAX_INPUT = 64 * 1024 * 1024   # rating_plugin.MAX_INPUT と同じ
_DAT_RE = re.compile(r'[A-Za-z0-9_\- ]{1,64}\.dat')   # rating_plugin._DAT_RE と同じ（プラグインへ渡せる名前）
# フォルダ名の先頭の BeatSaver のキー（ダウンロードした時の名前「103fb (Song - Mapper)」）。キーは小文字の16進。
# 後ろが「 (」「 - 」か名前の終わりの時だけ＝「Bad Apple」の Bad 等を拾わない
_KEY_RE = re.compile(r'([0-9a-f]{1,6})(?=$| \(| - )')

# 難易度の名前（PlayerData の difficulty は 0〜4 の数値＝ゲームの BeatmapDifficulty の並び）
DIFF_NAMES = ('Easy', 'Normal', 'Hard', 'Expert', 'ExpertPlus')
# PlayerData の maxRank（数値）→ 文字。ゲームの RankModel.Rank の並び（E,D,C,B,A,S,SS,SSS）。
# 確かめ方: この PC の PlayerData.dat（levelsStatsData 1934件）で、validScore=false の記録は全部 0、validScore=true の記録は 2〜6 で、
# 6 が最多・5・4 と続く（普通のプレイヤーは SS/S/A が多い）。スコアから精度（得点÷その譜面の最高点）を計算して 6=SS(90%以上)・
# 5=S(80%以上)・4=A(65%以上) の範囲に入ることも確かめた（2026-10-12・scratchpad の実データ確認）。7(SSS) はほぼ出ない
RANK_NAMES = ('E', 'D', 'C', 'B', 'A', 'S', 'SS', 'SSS')
MOD_ORDER = ('chroma', 'noodle', 'me', 'cinema', 'vivify')


class LibError(Exception):
    """利用者に見せる失敗。code は JS 側で翻訳キーにする（例: unknown-lib, missing, bad-path, not-allowed, not-found, too-large）"""
    def __init__(self, code, detail=''):
        super().__init__(code)
        self.code, self.detail = code, str(detail)[:500]


# ---------------------------------------------------------------- 小さな部品

def _write_text_atomic(path, text):
    """一時ファイルに書き終えてから置き換える（serve.py の _write_text_atomic と同じ考え方）。
    読み手が書きかけを見ない・途中で落ちても前の中身が残る。置き換え先を他が開いていると失敗するので少し待ってやり直す"""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        f.write(text)
    for i in range(20):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            if i == 19:
                raise
            time.sleep(0.05)


def _lib_id(path):
    """記録の識別子: 選んだパスの字面（大文字小文字・区切りをそろえた物）から作る短い安定した文字列"""
    return hashlib.sha1(_lpath(path).encode('utf-8')).hexdigest()[:12]


def _str(v, n=MAX_STR):
    return v[:n] if isinstance(v, str) else ''


def _num(v, lo, hi):
    """数値として使える値なら float、そうでなければ None（真偽値・範囲外・NaN は捨てる）"""
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    v = float(v)
    return v if math.isfinite(v) and lo <= v <= hi else None


def _r(v, nd=3):
    return None if v is None else round(v, nd)


def _plain_name(n):
    """Info.dat に書かれたファイル名が「フォルダ直下の1つの名前」か（.. や区切り文字で外のファイルを読ませない）"""
    return (isinstance(n, str) and 0 < len(n) <= 255 and n not in ('.', '..')
            and not any(c in n for c in '/\\:\0'))


def _rel_parts(rel):
    """JS から来た相対パス（区切りは '/'）を要素に分ける。危ない物は LibError('bad-path')。空文字＝根"""
    if not isinstance(rel, str) or len(rel) > 1024:
        raise LibError('bad-path')
    if rel == '':
        return []
    parts = rel.split('/')
    if len(parts) > 32:
        raise LibError('bad-path')
    for p in parts:
        if not p or p in ('.', '..') or any(c in p for c in '\\:\0') or os.path.splitdrive(p)[0]:
            raise LibError('bad-path')
    return parts


def _decode_json(b):
    """バイト列を JSON として読む（UTF-8 の BOM 付きも可）。読めなければ None"""
    try:
        try:
            s = b.decode('utf-8-sig')
        except UnicodeDecodeError:
            s = b.decode('utf-8', 'replace')
        return json.loads(s)
    except (ValueError, RecursionError):
        return None


def _birthtime(st):
    """作成日（UNIX秒）。Windows の Python 3.12 以降は st_birthtime、無ければ Windows の st_ctime（＝作成日）"""
    v = getattr(st, 'st_birthtime', None)
    if v is None and os.name == 'nt':
        v = st.st_ctime
    return v


def _added_date(folder, files):
    """曲フォルダの metadata.json の addedDate（UNIX秒）。Mod が曲を入れた時に書く物で、ファイルの日付からの推定より正確
    （フォルダごとコピーすると作成日はコピーした日になり、zip の日付を残す取り込み方だと Info.dat の更新日がアップロードの頃になる）。
    この PC では全曲にあった（2026-10-12）。時差の無い書き方はこの PC の時刻として読む。無い・読めない・ありえない日付なら None"""
    f = files.get('metadata.json')
    if not f or f[1] > 64 * 1024:
        return None
    try:
        with open(os.path.join(folder, f[0]), 'rb') as fp:
            v = json.loads(fp.read().decode('utf-8-sig')).get('addedDate')
        t = datetime.datetime.fromisoformat(v).timestamp()
    except Exception:
        return None
    return int(t) if 1514764800 <= t <= time.time() + 86400 else None   # 2018年〜明日


# ---------------------------------------------------------------- 音源の長さ

def _ogg_duration(path, size):
    """OGG（.egg も中身は OGG Vorbis）の長さ（秒）。全体は読まない: 最初のページの識別ヘッダーのサンプルレートと、
    ファイル末尾から探した最後のページの granule position（その時点までのサンプル数）で計算する。Opus は 48kHz 固定・pre-skip を引く"""
    try:
        with open(path, 'rb') as f:
            head = f.read(4096)
            if len(head) < 28 or head[:4] != b'OggS' or head[4] != 0:
                return None
            nseg = head[26]
            data = 27 + nseg
            pkt = head[data:data + sum(head[27:27 + nseg])]
            serial = head[14:18]
            if pkt[:7] == b'\x01vorbis' and len(pkt) >= 16:
                rate, preskip = struct.unpack('<I', pkt[12:16])[0], 0
            elif pkt[:8] == b'OpusHead' and len(pkt) >= 12:
                rate, preskip = 48000, struct.unpack('<H', pkt[10:12])[0]
            else:
                return None
            if not 1000 <= rate <= 400000:
                return None
            for span in (65536, 1024 * 1024):   # 普通は最後の数KBに見つかる。長い末尾のページがある時だけ広げる
                n = min(size, span)
                f.seek(size - n)
                tail = f.read(n)
                i = len(tail)
                while True:
                    i = tail.rfind(b'OggS', 0, i)
                    if i < 0:
                        break
                    if i + 27 <= len(tail) and tail[i + 4] == 0 and tail[i + 14:i + 18] == serial:
                        g = struct.unpack('<q', tail[i + 6:i + 14])[0]
                        if g > 0:   # -1 は「このページで終わるパケットが無い」
                            sec = (g - preskip) / rate
                            return sec if 0 < sec < 86400 else None
                if n >= size:
                    break
    except OSError:
        pass
    return None


def _wav_duration(path, size):
    """WAV の長さ（秒）＝ data チャンクの大きさ ÷ fmt チャンクの1秒あたりのバイト数"""
    try:
        with open(path, 'rb') as f:
            head = f.read(65536)
    except OSError:
        return None
    if len(head) < 12 or head[:4] != b'RIFF' or head[8:12] != b'WAVE':
        return None
    pos, byte_rate = 12, None
    while pos + 8 <= len(head):
        cid, csz = head[pos:pos + 4], struct.unpack('<I', head[pos + 4:pos + 8])[0]
        if cid == b'fmt ' and pos + 16 <= len(head):
            if pos + 20 <= len(head):
                byte_rate = struct.unpack('<I', head[pos + 16:pos + 20])[0]
        elif cid == b'data':
            n = csz if csz != 0xFFFFFFFF and pos + 8 + csz <= size else size - (pos + 8)
            if byte_rate:
                sec = n / byte_rate
                return sec if 0 < sec < 86400 else None
            return None
        pos += 8 + csz + (csz & 1)
    return None


def audio_duration(path, size):
    ext = os.path.splitext(path)[1].lower()
    if ext in ('.egg', '.ogg', '.opus'):
        return _ogg_duration(path, size)
    if ext == '.wav':
        return _wav_duration(path, size)
    return None


# ---------------------------------------------------------------- 譜面の解析

def _mods(cd, req_only=False):
    """難易度の customData の _requirements/_suggestions（v4 は requirements/suggestions）を短い名前へ。
    req_only=True は必要な Mod（_requirements）だけ＝「Noodle/Chroma が必要な曲を除く」の絞り込みと「必要な Mod」の列に使う
    （Chroma は推奨（ライトだけ）で付いている譜面が多く、推奨まで含めると普通の譜面まで除いてしまう）"""
    out = set()
    if not isinstance(cd, dict):
        return []
    for k in (('_requirements', 'requirements') if req_only else ('_requirements', '_suggestions', 'requirements', 'suggestions')):
        v = cd.get(k)
        if not isinstance(v, list):
            continue
        for s in v[:64]:
            if not isinstance(s, str):
                continue
            s = s.lower()
            if 'noodle' in s:
                out.add('noodle')
            elif 'chroma' in s:
                out.add('chroma')
            elif 'mapping extensions' in s:
                out.add('me')
            elif 'cinema' in s:
                out.add('cinema')
            elif 'vivify' in s:
                out.add('vivify')
    return [m for m in MOD_ORDER if m in out]


def _beat(v):
    """拍として使える数か（真偽値・NaN・極端な値は捨てる。1曲に数千回呼ぶので _num より軽く書いてある）"""
    return type(v) in (int, float) and -1e7 <= v <= 1e7


def _round_half_up(x, nd=3):
    """四捨五入（Python の round は偶数への丸めで、122.0625 が 122.062 になり BeatSaver の 122.063 と合わない）"""
    k = 10 ** nd
    return math.floor(x * k + 0.5) / k


def count_diff(d, bpm):
    """難易度の .dat（json.loads した物）から {notes, bombs, walls, lengthSec, nps} を数える。形が分からなければ全部 None。
    形の見分け: ゲームと同じく "version" の項目があれば v3・v4、無くて _notes/_obstacles があれば v2。
      v2 の中身を残したまま v3 で保存し直した .dat（_notes と colorNotes の両方がある）は v3 として数える
      （ゲームも BeatSaver もそう読む。全曲データと数が合わなかった譜面がこれだった）。
    数え方（BeatSaver と同じ考え方）:
      - notes＝色ノーツ（v2: _notes の _type 0/1 ／ v3・v4: colorNotes。チェーンのリンク burstSliders/chains は数えない）、
        bombs（v2: _type 3 ／ v3・v4: bombNotes）、walls（v2: _obstacles ／ v3・v4: obstacles）。v2 で Noodle の偽物
        （_customData._fake=true）は数えない（v3 以降の偽物は customData.fake… の別の配列にあるので自然に数えない）。
        v4 の colorNotes 等の中身は *Data 配列への添字の物の配列＝数は配列の長さ。
        この PC の CustomLevels（全曲データと照合できた 1114曲・3875難易度）で、BeatSaver の notes・bombs は全部、obstacles は
        1件を除いて一致した（その1件はファイルの _obstacles が空なのに全曲データは 860＝向こうの値がおかしい。2026-10-12）。
      - lengthSec＝「最初のノーツから最後のノーツまで」の拍を、Info.dat の基本の BPM で秒にした物（BPM の変化は見ない）。
        ノーツは v2 が _notes 全部（ボムも含む）、v3・v4 が colorNotes。nps＝notes ÷ lengthSec。どちらも小数3桁に四捨五入。
        この PC の CustomLevels の 100e7（Easy 226.875秒・ExpertPlus 226.914秒）・103fb（ExpertPlus 122.063秒・Normal 121.313秒）で、
        BeatSaver の seconds・nps と4つとも一致した（最後の物の拍・壁の終わり・最後のライトは、どれも合わない。2026-10-12）。
        ボムを含めるか（v2）・含めないか（v3・v4）は BeatSaver の作りの記憶に合わせた物で、実データでは確かめられていない
        （確かめた4つは最初と最後がどちらも色ノーツだった。ボムが色ノーツより外にある難易度は v2 の約6%・v3 の約5%）"""
    nul = {'notes': None, 'bombs': None, 'walls': None, 'lengthSec': None, 'nps': None}
    if not isinstance(d, dict):
        return nul
    v2 = isinstance(d.get('_notes'), list) or isinstance(d.get('_obstacles'), list)
    v3 = any(isinstance(d.get(k), list) for k in ('colorNotes', 'bombNotes', 'obstacles'))
    times = []
    if isinstance(d.get('version'), str) or (v3 and not v2):   # v3・v4
        cn = d.get('colorNotes') if isinstance(d.get('colorNotes'), list) else []
        notes = len(cn)
        bombs = len(d['bombNotes']) if isinstance(d.get('bombNotes'), list) else 0
        walls = len(d['obstacles']) if isinstance(d.get('obstacles'), list) else 0
        for n in cn:
            if type(n) is dict:
                b = n.get('b', 0)   # b が無いのは 0 拍（既定値を省いて書くエディタがある）
                if _beat(b):
                    times.append(b)
    elif v2:
        notes = bombs = 0
        for n in d.get('_notes') or []:
            if type(n) is not dict:
                continue
            cd = n.get('_customData')
            if cd and type(cd) is dict and cd.get('_fake') is True:
                continue
            t = n.get('_type')
            if t == 0 or t == 1:
                notes += 1
            elif t == 3:
                bombs += 1
            else:
                continue
            b = n.get('_time')
            if _beat(b):
                times.append(b)
        walls = 0
        for o in d.get('_obstacles') or []:
            if type(o) is dict:
                cd = o.get('_customData')
                if not (cd and type(cd) is dict and cd.get('_fake') is True):
                    walls += 1
    else:
        return nul
    if not bpm:   # BPM が分からなければ秒にできない
        return {'notes': notes, 'bombs': bombs, 'walls': walls, 'lengthSec': None, 'nps': None}
    length = (max(times) - min(times)) * 60.0 / bpm if times else 0.0
    nps = notes / length if length > 0 else 0.0
    return {'notes': notes, 'bombs': bombs, 'walls': walls,
            'lengthSec': _round_half_up(length), 'nps': _round_half_up(nps)}


def _diff_list(info):
    """Info.dat の難易度の一覧 [(char, diff, file, njs, offset, customData)]（v2/v3 と v4 の両方の形）"""
    out = []
    if isinstance(info.get('difficultyBeatmaps'), list):   # v4
        for d in info['difficultyBeatmaps'][:256]:
            if isinstance(d, dict):
                out.append((_str(d.get('characteristic'), 64), _str(d.get('difficulty'), 64), d.get('beatmapDataFilename'),
                            d.get('noteJumpMovementSpeed'), d.get('noteJumpStartBeatOffset'), d.get('customData')))
        return out
    for s in (info.get('_difficultyBeatmapSets') or [])[:64]:
        if not isinstance(s, dict):
            continue
        ch = _str(s.get('_beatmapCharacteristicName'), 64)
        for d in (s.get('_difficultyBeatmaps') or [])[:64]:
            if isinstance(d, dict):
                out.append((ch, _str(d.get('_difficulty'), 64), d.get('_beatmapFilename'),
                            d.get('_noteJumpMovementSpeed'), d.get('_noteJumpStartBeatOffset'), d.get('_customData')))
    return out


def _listing_name(files, name):
    """フォルダの一覧（小文字の名前 → (実際の名前, 大きさ, 更新日)）から名前を大文字小文字を無視して探し、実際の名前を返す"""
    if not _plain_name(name):
        return None
    hit = files.get(name.lower())
    return hit[0] if hit else None


def parse_map(folder, files, info_name):
    """譜面フォルダ1つを解析して MapEntry の中身（rel・key・dlTime 以外）を返す。Info.dat が読めなければ None。
    files はフォルダ直下の一覧（小文字の名前 → (実際の名前, 大きさ, 更新日ns)）。各 .dat は1回だけ読み、解析とハッシュに使う"""
    try:
        with open(os.path.join(folder, info_name), 'rb') as f:
            info_bytes = f.read(MAX_INFO + 1)
    except OSError:
        return None
    if len(info_bytes) > MAX_INFO:
        return None
    info = _decode_json(info_bytes)
    if not isinstance(info, dict):
        return None
    v4 = isinstance(info.get('difficultyBeatmaps'), list)
    if v4:
        song = info.get('song') if isinstance(info.get('song'), dict) else {}
        audio = info.get('audio') if isinstance(info.get('audio'), dict) else {}
        envs = info.get('environmentNames') if isinstance(info.get('environmentNames'), list) else []
        mappers = []
        for d in info['difficultyBeatmaps'][:256]:
            ba = d.get('beatmapAuthors') if isinstance(d, dict) else None
            for m in (ba.get('mappers') if isinstance(ba, dict) and isinstance(ba.get('mappers'), list) else [])[:32]:
                if isinstance(m, str) and m and m not in mappers:
                    mappers.append(m)
        e = {'fmt': 4, 'name': _str(song.get('title')), 'subName': _str(song.get('subTitle')),
             'artist': _str(song.get('author')), 'mapper': _str(', '.join(mappers)),
             'bpm': _num(audio.get('bpm'), 0.001, 100000), 'env': _str(envs[0] if envs else '', 64) or None,
             'songFile': _listing_name(files, audio.get('songFilename')),
             'coverFile': _listing_name(files, info.get('coverImageFilename'))}
        v4dur = _num(audio.get('songDuration'), 0.001, 86400)
    else:
        e = {'fmt': 2, 'name': _str(info.get('_songName')), 'subName': _str(info.get('_songSubName')),
             'artist': _str(info.get('_songAuthorName')), 'mapper': _str(info.get('_levelAuthorName')),
             'bpm': _num(info.get('_beatsPerMinute'), 0.001, 100000), 'env': _str(info.get('_environmentName'), 64) or None,
             'songFile': _listing_name(files, info.get('_songFilename')),
             'coverFile': _listing_name(files, info.get('_coverImageFilename'))}
        v4dur = None
    bpm = e['bpm']
    e['bpm'] = _r(bpm, 4)
    # 音源の長さ: OGG/egg・WAV は実物から。読めなければ v4 の audio.songDuration
    dur = None
    if e['songFile']:
        _, size, _ = files[e['songFile'].lower()]
        dur = audio_duration(os.path.join(folder, e['songFile']), size)
    e['durationSec'] = _r(dur if dur is not None else v4dur)
    # .dat はハッシュの順（map_hash.files_for_hash）に1回ずつ読み、同じバイト列をハッシュと解析の両方に使う
    blobs = {}   # 小文字の名前 → bytes（読めない・大きすぎる物は None）

    def blob(name):
        real = _listing_name(files, name)
        if not real:
            return None
        k = real.lower()
        if k not in blobs:
            blobs[k] = None
            if files[k][1] <= MAX_READ:
                try:
                    with open(os.path.join(folder, real), 'rb') as f:
                        blobs[k] = f.read()
                except OSError:
                    pass
        return blobs[k]
    names = map_hash.files_for_hash(info)
    parts = [blob(n) for n in names]
    # 無いファイルは飛ばす（ゲームと同じ・map_hash.compute の約束）。有るのに読めなかった物があれば、ハッシュは不明
    unreadable = any(p is None and _listing_name(files, n) for n, p in zip(names, parts))
    e['hash'] = None if unreadable else map_hash.compute(info_bytes, parts)
    parsed = {}  # 小文字の名前 → count_diff の結果（同じファイルを指す難易度は1回だけ数える）
    diffs = []
    for ch, df, fn, njs, off, cd in _diff_list(info):
        b = blob(fn)
        key = fn.lower() if isinstance(fn, str) else None
        if key not in parsed:
            parsed[key] = count_diff(_decode_json(b) if b is not None and len(b) <= MAX_PARSE else None, bpm)
        cnt = parsed[key]
        cd = cd if isinstance(cd, dict) else {}
        label = cd.get('_difficultyLabel', cd.get('difficultyLabel'))
        diffs.append({'char': ch, 'diff': df, 'label': _str(label, 128),
                      'file': _str(fn, 255) if isinstance(fn, str) else None,
                      'njs': _r(_num(njs, -1000, 1000)), 'offset': _r(_num(off, -1000, 1000)),
                      **cnt, 'mods': _mods(cd), 'req': _mods(cd, req_only=True)})
    e['diffs'] = diffs
    return e


# ---------------------------------------------------------------- 走査の状態（1回の走査＝1つ）

class _Scan:
    def __init__(self, lib_id, root):
        self.lib_id, self.root = lib_id, root
        self.lock = threading.Lock()
        self.maps, self.files = [], []
        self.total = 0          # 見つけた譜面フォルダの数（フォルダをたどっている間は増える）
        self.parsed = 0         # 処理し終えた譜面フォルダの数
        self.skipped = 0        # Info.dat が読めなかった譜面フォルダの数
        self.reparsed = 0       # キャッシュが使えず解析し直した数（テスト・確認用）
        self.phase = 'walk'     # walk（フォルダをたどる）→ parse（譜面を読む）→ done
        self.error = self.detail = None
        self.cancel = threading.Event()
        self.thread = None


# ---------------------------------------------------------------- 本体

class MediaLibrary:
    def __init__(self, data_dir, opener=None, default_playdata=None):
        """data_dir＝exe の隣（serve.py の DATA_DIR）。opener＝フォルダを開く関数（テストで差し替える。既定は os.startfile）。
        default_playdata＝プレイ記録の既定の場所（テストで差し替える）"""
        self.config_dir = os.path.join(data_dir, 'config')
        self.record_file = os.path.join(self.config_dir, 'library.json')
        self.cache_file = os.path.join(self.config_dir, 'library_cache.json')
        self.opener = opener or _default_open
        self.default_playdata = default_playdata or os.path.join(
            os.environ.get('USERPROFILE') or os.path.expanduser('~'),
            'AppData', 'LocalLow', 'Hyperbolic Magnetism', 'Beat Saber', 'PlayerData.dat')
        self._lock = threading.RLock()        # 記録（library.json）・走査の一覧
        self._cache_lock = threading.Lock()   # キャッシュ（library_cache.json）
        self._libs, self._playdata = [], None
        self._scans = {}
        self._cache = None
        self._pd = {'key': None, 'checked': 0, 'state': 'missing', 'data': None, 'count': 0, 'mtime': None}
        self._pd_lock = threading.Lock()
        self._record_seen = None
        self._load_record()

    # ---- 記録（config/library.json）----
    def _record_sig(self):
        try:
            st = os.stat(self.record_file)
            return (st.st_mtime_ns, st.st_size)
        except OSError:
            return None

    def _load_record(self):
        self._record_seen = self._record_sig()
        libs, playdata = [], None
        try:
            with open(self.record_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except (OSError, ValueError):
            data = None
        if isinstance(data, dict):
            seen = set()
            for it in data.get('libs') or []:
                p = it.get('path') if isinstance(it, dict) else None
                if _path_kind(p) is None:   # ドライブ名から始まる絶対パスか UNC だけ（壊れた・書き換えられた記録は読み飛ばす）
                    continue
                i = _lib_id(p)
                if i not in seen:
                    seen.add(i)
                    libs.append({'id': i, 'path': p, 'name': _lib_name(p)})
            pd = data.get('playdata')
            playdata = pd if _path_kind(pd) else None
        self._libs, self._playdata = libs, playdata

    def _reload_if_changed(self):
        """記録ファイルが外で書き換わっていたら読み直す（自動テストが記録を用意する時・利用者が手で直した時）。
        JS から記録を書き換える口は無いので、ここに来るのはこの PC の利用者・テストが書いた物だけ。外れたライブラリの走査は止める"""
        with self._lock:
            if self._record_sig() == self._record_seen:
                return
            self._load_record()
            ids = {l['id'] for l in self._libs}
            for i in [i for i in self._scans if i not in ids]:
                self._scans.pop(i).cancel.set()

    def _save_record(self):
        _write_text_atomic(self.record_file, json.dumps(
            {'libs': [{'path': l['path']} for l in self._libs], 'playdata': self._playdata}, ensure_ascii=False, indent=1))
        self._record_seen = self._record_sig()

    def _lib(self, lib_id):
        with self._lock:
            for l in self._libs:
                if l['id'] == lib_id:
                    return l
        raise LibError('unknown-lib')

    def may_touch(self, path):
        """そのパスにファイルシステムで触れてよいか（字面だけで判定）。ドライブ名から始まる絶対パスは可。
        UNC は記録したライブラリの中・記録したプレイ記録のファイルだけ（どちらもダイアログで選ばれた字面）"""
        k = _path_kind(path)
        if k == 'local':
            return True
        if k != 'unc':
            return False
        p = _lpath(path)
        with self._lock:
            if self._playdata and _path_kind(self._playdata) == 'unc' and p == _lpath(self._playdata):
                return True
            return any(_path_kind(l['path']) == 'unc' and _is_under(_lpath(l['path']), p) for l in self._libs)

    def approve_dir(self, path):
        """ダイアログで選ばれたフォルダを記録する（pywebview のフォルダ選択からだけ呼ぶ）。→ {id, name}。
        同じフォルダを2回選んだら前の記録をそのまま返す"""
        if _path_kind(path) is None:
            raise LibError('bad-path')
        if not os.path.isdir(path):   # 選ばれた物なので UNC でも触ってよい
            raise LibError('not-found')
        i = _lib_id(path)
        self._reload_if_changed()   # 記録ファイルが外で変わっていたら先に読み直す（古い記録を見て「記録済み」と判断し、保存しないことがあった）
        with self._lock:
            for l in self._libs:
                if l['id'] == i:
                    return {'id': i, 'name': l['name']}
            self._libs.append({'id': i, 'path': path, 'name': _lib_name(path)})
            self._save_record()
        return {'id': i, 'name': _lib_name(path)}

    def remove(self, lib_id):
        """記録から外す（走査を止め、そのライブラリのキャッシュも消す）。フォルダの中身には触れない"""
        self._reload_if_changed()
        with self._lock:
            lib = self._lib(lib_id)
            self._libs.remove(lib)
            sc = self._scans.pop(lib_id, None)
            self._save_record()
        if sc:
            sc.cancel.set()
        with self._cache_lock:
            cache = self._load_cache()
            if cache['libs'].pop(lib_id, None) is not None:
                self._save_cache()
        return {'ok': True}

    def list(self):
        """記録したライブラリ [{id, name, path, state:'ok'|'missing'}]（記録した順）"""
        self._reload_if_changed()
        with self._lock:
            libs = [dict(l) for l in self._libs]
        out = []
        for l in libs:
            ok = self.may_touch(l['path']) and os.path.isdir(l['path'])
            out.append({'id': l['id'], 'name': l['name'], 'path': l['path'], 'state': 'ok' if ok else 'missing'})
        return out

    # ---- キャッシュ（config/library_cache.json）----
    def _cache_key(self):
        return '%d/%s' % (CACHE_VERSION, _hash_rule_tag())

    def _load_cache(self):
        """_cache_lock の中で呼ぶ"""
        if self._cache is None:
            data = None
            try:
                with open(self.cache_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
            except (OSError, ValueError):
                pass
            if not (isinstance(data, dict) and data.get('v') == self._cache_key() and isinstance(data.get('libs'), dict)):
                data = {'v': self._cache_key(), 'libs': {}}
            self._cache = data
        return self._cache

    def _save_cache(self):
        """_cache_lock の中で呼ぶ"""
        try:
            _write_text_atomic(self.cache_file, json.dumps(self._cache, ensure_ascii=False, separators=(',', ':')))
        except OSError:
            pass   # 保存できなくても今回の走査は使える（次回が遅くなるだけ）

    # ---- 走査 ----
    def scan(self, lib_id, from_index=0):
        """走査の途中経過・結果。初回の呼び出しで裏のスレッドで走査を始め、すぐ返す（JS は done まで繰り返し呼ぶ）。
        → {ok, done, progress:{done,total}, maps:[from_index 番目以降の MapEntry], files:[…], next, skipped}
        files（譜面フォルダの外の音源・画像）は done の時だけ全部を返す（途中では空）。走査し終えた後は、rescan するまで同じ結果を返す"""
        lib = self._lib(lib_id)
        with self._lock:
            sc = self._scans.get(lib_id)
            if sc is None:
                sc = self._start(lib)
        return self._result(sc, from_index)

    def rescan(self, lib_id):
        """走査をやり直す（「読み直す」）。キャッシュは更新日・大きさで確かめ直す。走っている走査は止めてから始める
        （同じライブラリを同時に2回走査しない）。→ scan(lib_id, 0) と同じ形"""
        lib = self._lib(lib_id)
        with self._lock:
            old = self._scans.get(lib_id)
            if old:
                old.cancel.set()
            sc = self._start(lib, wait_for=old)
        return self._result(sc, 0)

    def _start(self, lib, wait_for=None):
        """self._lock の中で呼ぶ"""
        sc = _Scan(lib['id'], lib['path'])
        self._scans[lib['id']] = sc
        sc.thread = threading.Thread(target=self._run, args=(sc, wait_for), daemon=True, name='nlm-lib-scan')
        sc.thread.start()
        return sc

    def _result(self, sc, from_index):
        try:
            fi = max(0, int(from_index or 0))
        except (TypeError, ValueError):
            fi = 0
        with sc.lock:
            done = sc.phase == 'done'
            maps = sc.maps[fi:]
            r = {'ok': sc.error is None, 'done': done, 'progress': {'done': sc.parsed, 'total': sc.total},
                 'maps': maps, 'files': list(sc.files) if done else [], 'next': fi + len(maps), 'skipped': sc.skipped}
            if sc.error:
                r['error'] = sc.error
        return r

    def _run(self, sc, wait_for):
        if wait_for and wait_for.thread and wait_for.thread is not threading.current_thread():
            wait_for.thread.join()   # 前の走査が止まるのを待つ（止める合図は出してある。1曲の解析が終わるまで）
        try:
            if sc.cancel.is_set():   # 待っている間に、さらに読み直し・記録から外す操作があった
                return
            if not self.may_touch(sc.root) or not os.path.isdir(sc.root):
                sc.error = 'missing'
                return
            cands = self._walk(sc)
            if sc.cancel.is_set():
                return
            with sc.lock:
                sc.phase = 'parse'
            self._parse_all(sc, cands)
        except Exception as e:   # 予想外の失敗でも「走査中」のまま止まらないようにする
            sc.error = 'scan-failed'
            sc.detail = str(e)[:500]
        finally:
            with sc.lock:
                sc.phase = 'done'

    def _walk(self, sc):
        """フォルダをたどって譜面フォルダの候補と、譜面フォルダの外の音源・画像を集める（JS の scanLibrary と同じ規則）:
        深さ8まで・Info.dat（大文字小文字は問わない）があるフォルダが譜面で、その中へは降りない。
        ジャンクション・シンボリックリンクはたどらない（根の外へ出る・ループする）"""
        cands = []
        root_list = _scandir(sc.root)
        stack = [('', root_list, 0)]
        while stack:
            if sc.cancel.is_set():
                break
            rel, listing, depth = stack.pop()
            subdirs, files = listing
            for name, st in files:
                ext = os.path.splitext(name)[1].lower()
                kind = 'music' if ext in AUDIO_EXTS else 'image' if ext in IMAGE_EXTS else None
                if kind and len(sc.files) < MAX_ITEMS:
                    with sc.lock:
                        sc.files.append({'kind': kind, 'rel': (rel + '/' if rel else '') + name,
                                         'name': os.path.splitext(name)[0]})
            nxt = []
            for name, st in subdirs:
                crel = (rel + '/' if rel else '') + name
                child = _scandir(os.path.join(sc.root, *crel.split('/')))
                info = next((n for n, _ in child[1] if n.lower() == 'info.dat'), None)
                if info:
                    if len(cands) < MAX_ITEMS:
                        cands.append((crel, st, child[1], info))
                        with sc.lock:
                            sc.total = len(cands)
                elif depth < MAX_DEPTH:
                    nxt.append((crel, child, depth + 1))
            stack.extend(reversed(nxt))   # 名前の順にたどる（深さ優先）
        return cands

    def _parse_all(self, sc, cands):
        with self._cache_lock:
            cache = self._load_cache()
            lc = dict(cache['libs'].get(sc.lib_id) or {})
        fresh, last_save, dirty = {}, time.monotonic(), False
        for crel, dst, flist, info_name in cands:
            if sc.cancel.is_set():
                return
            time.sleep(0)   # 1曲ごとに他のスレッドへ順番を譲る（初回は JSON の解析で CPU を使い切り、同時の通信・画面からの要求が待たされるため）
            files = {n.lower(): (n, s.st_size, s.st_mtime_ns) for n, s in flist}
            sig = hashlib.sha1('\n'.join('%s|%d|%d' % (n, sz, mt) for n, sz, mt in sorted(files.values())).encode('utf-8')).hexdigest()
            hit = lc.get(crel)
            if isinstance(hit, dict) and hit.get('sig') == sig and isinstance(hit.get('e'), dict):
                e = dict(hit['e'])
            else:
                e = None
                try:
                    e = parse_map(os.path.join(sc.root, *crel.split('/')), files, info_name)
                except Exception:
                    e = None
                with sc.lock:
                    sc.reparsed += 1
                if e is None:
                    with sc.lock:
                        sc.parsed += 1
                        sc.skipped += 1
                    continue
                dirty = True
            fresh[crel] = {'sig': sig, 'e': e}
            # ダウンロード日: metadata.json の addedDate があればそれ（_added_date）。無ければ推定＝フォルダの作成日と
            # Info.dat の更新日の早い方（毎回、一覧の値から作る＝キャッシュに頼らない。metadata.json の変更は sig に入る）
            added = _added_date(os.path.join(sc.root, *crel.split('/')), files)
            times = [t for t in (_birthtime(dst), files[info_name.lower()][2] / 1e9) if t]
            m = _key_of(crel.rsplit('/', 1)[-1])
            entry = {'rel': crel, 'key': m, **e, 'dlTime': added or (int(min(times)) if times else None)}
            if not entry.get('name'):
                entry['name'] = crel.rsplit('/', 1)[-1][:MAX_STR]
            with sc.lock:
                sc.maps.append(entry)
                sc.parsed += 1
            if dirty and time.monotonic() - last_save > CACHE_SAVE_SEC:
                self._store_cache(sc.lib_id, fresh, lc, partial=True)
                last_save, dirty = time.monotonic(), False
        self._store_cache(sc.lib_id, fresh, lc, partial=False)

    def _store_cache(self, lib_id, fresh, old, partial):
        """partial=True（途中）は前のキャッシュに今回の分を重ねる。最後は今回見つかった物だけにする（消えた曲を残さない）。
        記録の鍵を持ったまま書く＝書いている間に remove されてキャッシュに残る、が起きない（鍵の順は _lock → _cache_lock）"""
        with self._lock:
            if not any(l['id'] == lib_id for l in self._libs):
                return   # 走査の途中で記録から外された
            with self._cache_lock:
                cache = self._load_cache()
                cache['libs'][lib_id] = {**old, **fresh} if partial else dict(fresh)
                self._save_cache()

    def get_map(self, lib_id, rel):
        """走査の結果から1曲の MapEntry を返す（無ければ None）。BeatSaver への問い合わせ・★の計算の前に hash/key を引くため"""
        self._lib(lib_id)
        with self._lock:
            sc = self._scans.get(lib_id)
        if not sc:
            return None
        with sc.lock:
            for m in sc.maps:
                if m['rel'] == rel:
                    return m
        return None

    # ---- ファイル読み出し・フォルダを開く ----
    def _resolve(self, lib_id, rel, name=''):
        """id・相対パス・名前から、根の中の実在するパスを作る（字面の検査 → UNC の確認 → 実体が根の中か）"""
        lib = self._lib(lib_id)
        parts = _rel_parts(rel)
        if name:
            if not _plain_name(name):
                raise LibError('bad-path')
            parts = parts + [name]
        root = lib['path']
        path = os.path.join(root, *parts) if parts else root
        if not self.may_touch(path):
            raise LibError('not-allowed')
        rr, rp = _npath(root), _npath(path)
        if not _is_under(rr, rp):   # ジャンクション・シンボリックリンクで根の外へ出ていないか（実体で比べる）
            raise LibError('not-allowed')
        return path, rp == rr

    def read_file(self, lib_id, rel, name=''):
        """ライブラリの中のファイルを読む → (bytes, content_type)。許可は .dat/.json/音源/画像だけ・根の中だけ・200MBまで。
        rel は譜面フォルダ（または files の rel のフォルダ部分）、name はファイル名。name を空にして rel にファイルまで書いてもよい"""
        path, is_root = self._resolve(lib_id, rel, name)
        ext = os.path.splitext(path)[1].lower()
        if is_root or ext not in READ_EXTS:
            raise LibError('not-allowed')
        try:
            if not os.path.isfile(path):
                raise LibError('not-found')
            size = os.path.getsize(path)
        except OSError:
            raise LibError('not-found')
        if size > MAX_READ:
            raise LibError('too-large')
        try:
            with open(path, 'rb') as f:
                data = f.read(MAX_READ + 1)
        except OSError:
            raise LibError('not-found')
        if len(data) > MAX_READ:
            raise LibError('too-large')
        return data, CONTENT_TYPES[ext]

    def open_folder(self, lib_id, rel):
        """ライブラリの中のフォルダをエクスプローラーで開く（根の中の実在するフォルダだけ）"""
        path, _ = self._resolve(lib_id, rel)
        if not os.path.isdir(path):
            raise LibError('not-found')
        self.opener(path)
        return {'ok': True}

    # ---- nlm-rating（★の計算）に渡す入力 ----
    def rating_input(self, lib_id, rel):
        """rating_plugin.RatingPlugin.measure の files（[{name:'Info.dat', text}, {name:'<難易度>.dat', text}, …]）を作る。
        渡せる名前（rating_plugin._DAT_RE）の物だけ・最大32個・合計64MBまで。v4 は音の情報（audioDataFilename）も足す"""
        path, is_root = self._resolve(lib_id, rel)
        if is_root or not os.path.isdir(path):
            raise LibError('not-found')
        listing = {n.lower(): n for n, _ in _scandir(path)[1]}
        info_name = listing.get('info.dat')
        if not info_name:
            raise LibError('not-found')
        info_text = _read_text(os.path.join(path, info_name), MAX_INFO)
        try:
            info = json.loads(info_text) if info_text is not None else None
        except (ValueError, RecursionError):
            info = None
        if not isinstance(info, dict):
            raise LibError('bad-info')
        names = list(map_hash.files_for_hash(info))
        if isinstance(info.get('audio'), dict):
            names.append(info['audio'].get('audioDataFilename'))
        out, total, seen = [{'name': 'Info.dat', 'text': info_text}], len(info_text), {'info.dat'}
        for fn in names:
            if not isinstance(fn, str) or not _DAT_RE.fullmatch(fn) or fn.lower() in seen or len(out) >= 32:
                continue
            real = listing.get(fn.lower())
            if not real:
                continue
            seen.add(fn.lower())
            text = _read_text(os.path.join(path, real), RATING_MAX_INPUT)
            if text is None:
                continue
            total += len(text)
            if total > RATING_MAX_INPUT:
                raise LibError('too-large')
            out.append({'name': fn, 'text': text})
        if len(out) < 2:
            raise LibError('no-diffs')
        return out

    # ---- プレイ記録（PlayerData.dat。読むだけ）----
    def playdata_path(self):
        with self._lock:
            return (self._playdata, 'custom') if self._playdata else (self.default_playdata, 'auto')

    def set_playdata(self, path):
        """ダイアログで選ばれたプレイ記録のファイルを記録する（pywebview のファイル選択からだけ呼ぶ）→ playdata_status()"""
        if _path_kind(path) is None:
            raise LibError('bad-path')
        with self._lock:
            self._playdata = path
            self._save_record()
        return self.playdata_status()

    def reset_playdata(self):
        """既定の場所に戻す → playdata_status()"""
        with self._lock:
            self._playdata = None
            self._save_record()
        return self.playdata_status()

    def playdata_status(self):
        """{mode:'auto'|'custom', path, state:'ok'|'missing'|'bad', mtime, count}。count＝1回以上遊んだ記録（難易度ごと）の数"""
        path, mode = self.playdata_path()
        pd = self._load_playdata(force=True)
        return {'mode': mode, 'path': path, 'state': pd['state'], 'mtime': pd['mtime'], 'count': pd['count']}

    def _load_playdata(self, force=False):
        """プレイ記録を読み、{hash（小文字）: play} を作って覚えておく。更新日・大きさが変わった時だけ読み直す
        （force=False の時は確かめるのも1秒に1回まで＝1曲ずつ呼ばれても重くならない）"""
        path, _ = self.playdata_path()
        with self._pd_lock:
            now = time.monotonic()
            if not force and self._pd['key'] and self._pd['key'][0] == path and now - self._pd['checked'] < 1:
                return self._pd
            self._pd['checked'] = now
            try:
                if not self.may_touch(path):
                    raise FileNotFoundError
                st = os.stat(path)
            except OSError:
                self._pd.update(key=(path, None), state='missing', data=None, count=0, mtime=None)
                return self._pd
            key = (path, st.st_mtime_ns, st.st_size)
            if self._pd['key'] == key:
                return self._pd
            self._pd.update(key=key, mtime=int(st.st_mtime), data=None, count=0, state='bad')
            if st.st_size > MAX_PLAYDATA:
                return self._pd
            try:
                with open(path, 'rb') as f:
                    raw = f.read(MAX_PLAYDATA + 1)
            except OSError:
                self._pd['state'] = 'missing'
                return self._pd
            data = _parse_playdata(_decode_json(raw)) if len(raw) <= MAX_PLAYDATA else None
            if data is None:
                return self._pd
            plays, count = data
            self._pd.update(data=plays, count=count, state='ok')
            return self._pd

    def play_for(self, h):
        """そのハッシュの譜面のプレイ記録 → {fav, diffs:{"Standard/ExpertPlus":{plays,best,rank,fc}}}。記録が無ければ None。
        プレイヤー名・ID は返さない（そもそも読み取った物に入れていない）"""
        if not isinstance(h, str):
            return None
        pd = self._load_playdata()
        if not pd['data']:
            return None
        p = pd['data'].get(h.lower())
        return {'fav': p['fav'], 'diffs': {k: dict(v) for k, v in p['diffs'].items()}} if p else None

    def play_all(self, lib_id):
        """走査の結果の全曲のプレイ記録 → {rel: play}（記録のある曲だけ）。/__lib/extra の play に使う"""
        self._lib(lib_id)
        with self._lock:
            sc = self._scans.get(lib_id)
        if not sc:
            return {}
        with sc.lock:
            pairs = [(m['rel'], m.get('hash')) for m in sc.maps]
        out = {}
        for rel, h in pairs:
            p = self.play_for(h) if h else None
            if p:
                out[rel] = p
        return out


# ---------------------------------------------------------------- モジュール内の部品

_RULE_TAG = []


def _hash_rule_tag():
    """map_hash.files_for_hash の規則の指紋（決まった見本の Info で返す並びのハッシュ）。規則が変われば変わる＝キャッシュを作り直す"""
    if not _RULE_TAG:
        v4 = {'version': '4.0.0', 'audio': {'audioDataFilename': 'A.dat'}, 'difficultyBeatmaps': [
            {'beatmapDataFilename': 'B.dat', 'lightshowDataFilename': 'L.dat'},
            {'beatmapDataFilename': 'C.dat', 'lightshowDataFilename': 'L.dat'}]}
        v2 = {'_version': '2.0.0', '_difficultyBeatmapSets': [{'_difficultyBeatmaps': [
            {'_beatmapFilename': 'X.dat'}, {'_beatmapFilename': 'Y.dat'}]}]}
        s = json.dumps([map_hash.files_for_hash(v4), map_hash.files_for_hash(v2)])
        _RULE_TAG.append(hashlib.sha1(s.encode('utf-8')).hexdigest()[:8])
    return _RULE_TAG[0]


def _lib_name(path):
    s = path.replace('/', '\\').rstrip('\\')
    return (s.rsplit('\\', 1)[-1] or path)[:MAX_STR]


def _key_of(folder_name):
    m = _KEY_RE.match(folder_name)
    return m.group(1).lower() if m else None


def _scandir(path):
    """フォルダ直下の一覧 → ([(フォルダ名, stat)], [(ファイル名, stat)])。名前の順。リンク・ジャンクションは入れない。
    Windows では DirEntry.stat() が一覧の情報から作られる（ファイルごとに開かない）ので速い"""
    dirs, files = [], []
    try:
        with os.scandir(path) as it:
            for ent in it:
                try:
                    if ent.is_symlink() or (hasattr(ent, 'is_junction') and ent.is_junction()):
                        continue
                    if ent.is_dir(follow_symlinks=False):
                        dirs.append((ent.name, ent.stat(follow_symlinks=False)))
                    elif ent.is_file(follow_symlinks=False):
                        files.append((ent.name, ent.stat(follow_symlinks=False)))
                except OSError:
                    continue
    except OSError:
        pass
    key = lambda x: x[0].casefold()
    return sorted(dirs, key=key), sorted(files, key=key)


def _read_text(path, limit):
    try:
        with open(path, 'rb') as f:
            b = f.read(limit + 1)
    except OSError:
        return None
    if len(b) > limit:
        raise LibError('too-large')
    try:
        return b.decode('utf-8-sig')
    except UnicodeDecodeError:
        return b.decode('utf-8', 'replace')


def _parse_playdata(d):
    """PlayerData.dat（json.loads した物）→ ({hash: {fav, diffs}}, 遊んだ記録の数)。形が違えば None。
    使うのは localPlayers[0] の levelsStatsData と favoritesLevelIds だけ（名前・ID・設定は読まない）。
    levelId は「custom_level_<大文字のハッシュ>」（公式曲は別の形なので読み飛ばす）。difficulty は 0〜4（DIFF_NAMES）"""
    if not isinstance(d, dict) or not isinstance(d.get('localPlayers'), list) or not d['localPlayers']:
        return None
    pl = d['localPlayers'][0]
    if not isinstance(pl, dict):
        return None
    out, count = {}, 0

    def slot(level_id):
        if not isinstance(level_id, str) or not level_id.startswith('custom_level_'):
            return None
        h = level_id[len('custom_level_'):].lower()
        if not re.fullmatch(r'[0-9a-f]{40}', h):
            return None
        return out.setdefault(h, {'fav': False, 'diffs': {}})

    for s in (pl.get('levelsStatsData') or [])[:200000]:
        if not isinstance(s, dict):
            continue
        plays = s.get('playCount')
        if isinstance(plays, bool) or not isinstance(plays, int) or plays <= 0:
            continue   # 選んだだけで遊んでいない記録（playCount 0）は数えない
        df = s.get('difficulty')
        ch = s.get('beatmapCharacteristicName')
        if isinstance(df, bool) or not isinstance(df, int) or not 0 <= df < len(DIFF_NAMES) or not isinstance(ch, str):
            continue
        p = slot(s.get('levelId'))
        if p is None:
            continue
        valid = s.get('validScore') is True   # 一度もクリアしていない（失敗だけ）の記録は得点・ランクが 0
        best = s.get('highScore')
        rank = s.get('maxRank')
        p['diffs']['%s/%s' % (ch[:64], DIFF_NAMES[df])] = {
            'plays': min(plays, 10 ** 7),
            'best': best if valid and isinstance(best, int) and not isinstance(best, bool) and 0 <= best < 10 ** 9 else None,
            'rank': RANK_NAMES[rank] if valid and isinstance(rank, int) and not isinstance(rank, bool) and 0 <= rank < len(RANK_NAMES) else None,
            'fc': s.get('fullCombo') is True}
        count += 1
    for lid in (pl.get('favoritesLevelIds') or [])[:200000]:
        p = slot(lid)
        if p is not None:
            p['fav'] = True
    return out, count


def _default_open(path):
    """フォルダをエクスプローラーで開く（ShellExecute。explorer.exe の引数にするとフォルダ名の , で切れてしまう）"""
    os.startfile(path)   # noqa: S606（根の中の実在するフォルダだと確かめてから呼ぶ）


# ---------------------------------------------------------------- NLM推定の★の記録（config/rating_cache.json）

class RatingCache:
    """nlm-rating で計算した★（NLM推定）を、譜面のハッシュ＋プラグインの版ごとに記録する。
    版が変われば計算し直す（古い版の値は使わない）。中身は {"<版>": {"<ハッシュ>": {"Standard/ExpertPlus": {"stars": 7.12} | {"skipped": "tooFewNotes"}}}}"""

    def __init__(self, data_dir):
        self.file = os.path.join(data_dir, 'config', 'rating_cache.json')
        self._lock = threading.Lock()
        self._data = None

    def _load(self):
        if self._data is None:
            try:
                with open(self.file, 'r', encoding='utf-8') as f:
                    d = json.load(f)
                self._data = d if isinstance(d, dict) else {}
            except (OSError, ValueError):
                self._data = {}
        return self._data

    def get(self, h, version):
        if not isinstance(h, str) or not version:
            return None
        with self._lock:
            v = self._load().get(version, {}).get(h.lower())
            return {k: dict(x) for k, x in v.items()} if isinstance(v, dict) else None

    def put(self, h, version, diffs):
        if not isinstance(h, str) or not version:
            return
        with self._lock:
            d = self._load()
            for old in [k for k in d if k != version]:   # 古い版の値は捨てる（使わないので溜めない）
                d.pop(old, None)
            d.setdefault(version, {})[h.lower()] = diffs
            try:
                _write_text_atomic(self.file, json.dumps(d, ensure_ascii=False, separators=(',', ':')))
            except OSError:
                pass

    @staticmethod
    def from_plugin(results):
        """rating_plugin.measure の results → {"Standard/ExpertPlus": {"stars": …} | {"skipped": …}}（数値は rating_plugin で検査済み）"""
        out = {}
        for r in results or []:
            ch, df = r.get('characteristic') or 'Standard', r.get('difficulty')
            if not df:
                continue
            k = '%s/%s' % (ch, df)
            if r.get('skipped'):
                out[k] = {'skipped': r['skipped']}
                continue
            st = ((r.get('ratings') or {}).get('none') or {}).get('stars')
            if isinstance(st, (int, float)) and math.isfinite(st) and 0 <= st < 1000:
                out[k] = {'stars': round(float(st), 2)}
        return out

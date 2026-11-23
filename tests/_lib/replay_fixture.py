"""REPLAY の窓のテスト用の合成リプレイ（.bsor）と書き出しの控えを作る部品（標準ライブラリだけ・書くだけ）。
unit_py（tests/unit_py/test_replays.py）と e2e（担当 C の tests/_lib/replay_helpers.py 等）の両方から使う。他人の譜面・曲・リプレイは使わない。

よく使う流れ（e2e）:
    import replay_fixture as RF
    ed = t.fresh('basic')
    # 1. 書き出しの控え: 画面から書き出す（NLM が /__replay/keep・keepEgg を呼ぶ）か、RF.keep_map(ed.data_dir, files, egg) で直接置く
    files = RF.make_map(song='Test Song', mapper='Tester', diffs=('Expert',))     # {ファイル名: バイト列}（Info.dat v2・難易度の .dat・カバー）
    h = RF.keep_map(ed.data_dir, files, egg=b'OggS-test')                          # → 控えの hash（小文字 40 字）
    #    書き出したフォルダから hash を出すなら RF.folder_hash(<書き出したフォルダ>)
    # 2. その版で遊んだリプレイを、テストのリプレイのフォルダ（tools/cdp.py の ed.replays_dir＝NLM_REPLAYS）に置く
    RF.write_replay(ed.replays_dir, song='Test Song', mapper='Tester', h=h, diff='Expert', notes=RF.NOTES, end=4.0)
    # 3. 画面から /__replay/list {song:{name:'Test Song', mapper:'Tester'}} を呼ぶと 1 件（playable:true）
    #    hash を変えた物（h='CD' * 20）は控えに無い版＝playable:false（灰色）

.bsor の形は BeatLeader の Open Replay Format（https://github.com/BeatLeader/BS-Open-Replay ）。フレームは中身が 0 の物を frames 個
（最後のフレームの時刻＝end・記録が終わった秒）。ノーツは NOTES の形の (番号, 出来事の秒, ノーツの秒, 種類, before, after, 中心からの距離)。
"""
import hashlib
import json
import os
import struct
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

MAGIC = 0x442D3D69
FRAME_SIZE = 4 + 4 + 3 * 7 * 4
GOOD, BAD, MISS, BOMB = 0, 1, 2, 3
PLAYER = '76561190000000000'
DIFF_RANK = {'Easy': 1, 'Normal': 3, 'Hard': 5, 'Expert': 7, 'ExpertPlus': 9}


def nid(st, x, y, c, d):
    """ノーツの番号（点の種類 st＝3 が通常・6 がチェーンの頭・7 がチェーンの後ろ／列 x／段 y／色 c／向き d）"""
    return st * 10000 + x * 1000 + y * 100 + c * 10 + d


# 見本のノーツ: 良い 2 つ（115 点・70+15+8＝93 点）・悪い切り方・見逃し・古い形のボム・チェーンの頭（85 点満点）・チェーンの後ろ（20 点）
NOTES = [(nid(3, 1, 0, 0, 1), 1.0, 1.0, GOOD, 1.0, 1.0, 0.0),
         (nid(3, 2, 0, 1, 1), 1.5, 1.5, GOOD, 1.0, 0.5, 0.15),
         (nid(3, 0, 2, 0, 0), 2.1, 2.0, BAD, 0.2, 0.0, 0.0),
         (nid(3, 3, 1, 1, 8), 2.5, 2.5, MISS, 0, 0, 0),
         (-1, 3.0, 3.0, GOOD, 0, 0, 0),
         (nid(6, 1, 1, 0, 1), 3.5, 3.5, GOOD, 1.0, 0.0, 0.0),
         (nid(7, 1, 0, 0, 8), 3.6, 3.55, GOOD, 0, 0, 0)]


def _s(t, broken=False):
    b = t.encode('utf-8')
    return (b'\x00' if broken else b'') + struct.pack('<i', len(b)) + b


def bsor_bytes(song='Test Song', mapper='Tester', h='AB' * 20, diff='Expert', mode='Standard', score=1000, notes=(), walls=(),
               frames=3, end=None, broken=False, mods='', ts=1794394711, player='プレイヤー', jd=17.0, fail_time=0.0):
    """合成の .bsor のバイト列。walls＝[(番号, 体力, 入った秒, 出る秒)]。broken＝プレイヤー名の長さの前に 1 バイト余計な物（古い mod の癖）"""
    head = struct.pack('<iBB', MAGIC, 1, 0)
    strs = ['0.9.0', '1.40.8', str(ts), PLAYER, player, 'steam', 'Oculus', 'Quest3', 'Touch', h, song, mapper, diff]
    info = b''.join(_s(x, broken and i == 4) for i, x in enumerate(strs)) + struct.pack('<i', score)
    info += _s(mode) + _s('DefaultEnvironment') + _s(mods) + struct.pack('<f?ffff', jd, False, 1.75, 0.0, fail_time, 1.0)
    fr = struct.pack('<Bi', 1, frames) + b''.join(struct.pack('<f', (end or 0) * (i + 1) / frames) + bytes(FRAME_SIZE - 4)
                                                  for i in range(frames))
    ns = struct.pack('<Bi', 2, len(notes))
    for n, t, sp, kind, before, after, dist in notes:
        ns += struct.pack('<iffi', n, t, sp, kind)
        if kind in (GOOD, BAD):
            ns += struct.pack('<????f3fiff3f3f4f', True, kind == GOOD, True, False, 3.0, 0, 0, 1, 1, 0.0, 0.0,
                              0, 1, 0, 0, 0, 1, dist, 0.0, before, after)
    ws = struct.pack('<Bi', 3, len(walls)) + b''.join(struct.pack('<ifff', *w) for w in walls)
    rest = struct.pack('<Bi', 4, 0) + struct.pack('<Bi', 5, 1) + struct.pack('<qf', 3, 12.5)
    return head + info + fr + ns + ws + rest


def replay_name(song='Test Song', diff='Expert', mode='Standard', h='AB' * 20, ts=1794394711, flags=()):
    """BeatLeader と同じ形のファイル名 <プレイヤー>-[practice-][fail-][exit-]<曲名>-<難易度>-<モード>-<HASH>-<時刻>.bsor"""
    fl = ''.join('-' + f for f in ('practice', 'fail', 'exit') if f in flags)
    return f'{PLAYER}{fl}-{song}-{diff}-{mode}-{h.upper()}-{ts}.bsor'


def write_replay(folder, name=None, flags=(), **kw):
    """合成の .bsor を folder に書いて場所を返す（name を省くと BeatLeader と同じ形の名前。kw は bsor_bytes と同じ）。
    flags＝('fail', 'exit', 'practice') のどれか＝ファイル名の印（fail は .bsor の中の失敗の時刻も 1 秒にする）"""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    if 'fail' in flags:
        kw.setdefault('fail_time', 1.0)
    args = {k: kw[k] for k in ('song', 'diff', 'mode', 'h', 'ts') if k in kw}
    p = folder / (name or replay_name(flags=flags, **args))
    p.write_bytes(bsor_bytes(**kw))
    return p


def make_map(song='Test Song', mapper='Tester', diffs=('Expert',), bpm=120.0, cover=True, notes=1):
    """書き出しと同じ形の小さな譜面 → {ファイル名: バイト列}（Info.dat v2・<難易度>Standard.dat v3・cover.jpg）"""
    info = {'_version': '2.1.0', '_songName': song, '_songSubName': '', '_songAuthorName': 'Artist', '_levelAuthorName': mapper,
            '_beatsPerMinute': bpm, '_songFilename': 'song.egg', '_coverImageFilename': 'cover.jpg' if cover else '',
            '_environmentName': 'DefaultEnvironment',
            '_difficultyBeatmapSets': [{'_beatmapCharacteristicName': 'Standard', '_difficultyBeatmaps': [
                {'_difficulty': d, '_difficultyRank': DIFF_RANK[d], '_beatmapFilename': f'{d}Standard.dat',
                 '_noteJumpMovementSpeed': 16, '_noteJumpStartBeatOffset': 0} for d in diffs]}]}
    files = {'Info.dat': json.dumps(info, ensure_ascii=False).encode('utf-8')}
    for d in diffs:
        # NLM の書き出しと同じ項目をそろえる（BL のリプレイアプリは basicBeatmapEvents などが無い .dat を読むと途中で止まり、曲を読み込まない
        # ＝本物どうしのテスト test_replay_real.py が「読み込み中」のままになった。2026-11-22）
        dat = {'version': '3.2.0', 'bpmEvents': [], 'rotationEvents': [],
               'colorNotes': [{'b': 2 + i, 'x': 1, 'y': 0, 'c': 0, 'd': 1, 'a': 0} for i in range(notes)],
               'bombNotes': [], 'obstacles': [], 'sliders': [], 'burstSliders': [], 'waypoints': [],
               'basicBeatmapEvents': [], 'colorBoostBeatmapEvents': [], 'lightColorEventBoxGroups': [], 'lightRotationEventBoxGroups': [],
               'lightTranslationEventBoxGroups': [], 'basicEventTypesWithKeywords': {}, 'useNormalEventsAsCompatibleEvents': True}
        files[f'{d}Standard.dat'] = json.dumps(dat).encode('utf-8')
    if cover:
        files['cover.jpg'] = b'\xff\xd8\xff\xe0cover'
    return files


def map_hash_of(files):
    """{ファイル名: バイト列} → BeatSaver・BeatLeader と同じ hash（map_hash.py と同じ規則・小文字 40 字）"""
    import map_hash
    info = json.loads(files['Info.dat'].decode('utf-8-sig'))
    return map_hash.compute(files['Info.dat'], [files.get(n) for n in map_hash.files_for_hash(info)])


def folder_hash(folder):
    """書き出したフォルダ（Info.dat と難易度の .dat）→ hash"""
    folder = Path(folder)
    files = {p.name: p.read_bytes() for p in folder.iterdir() if p.is_file()}
    return map_hash_of(files)


def keep_body(files):
    """/__replay/keep に送る (m の JSON 文字列, 本体)。files＝{ファイル名: バイト列}（送る順）"""
    names = list(files)
    return json.dumps({'files': [{'name': n, 'size': len(files[n])} for n in names]}), b''.join(files[n] for n in names)


def reset(data_dir, replays_dir=None):
    """前のテストのリプレイと控えを消す（t.fresh() は消さない）: replays_dir（ed.replays_dir）の中身・data_dir の replays/・
    config/replays.json（選んだフォルダ）・config/replays_cache.json。e2e なら RF.reset(ed.data_dir, ed.replays_dir)"""
    import shutil
    if replays_dir:
        for p in Path(replays_dir).iterdir() if Path(replays_dir).is_dir() else ():
            shutil.rmtree(p) if p.is_dir() else p.unlink()
    shutil.rmtree(Path(data_dir) / 'replays', ignore_errors=True)
    for n in ('replays.json', 'replays_cache.json'):
        (Path(data_dir) / 'config' / n).unlink(missing_ok=True)


def keep_map(data_dir, files, egg=b'OggS-test-egg', exported_at=None):
    """書き出しの控えを data_dir（serve の DATA_DIR）の replays/ に直接置く（/__replay/keep・keepEgg を通さない）→ hash。
    egg=None なら音は控えない（playable にならない）"""
    h = map_hash_of(files)
    d = Path(data_dir) / 'replays' / 'maps' / h
    d.mkdir(parents=True, exist_ok=True)
    for n, b in files.items():
        (d / n).write_bytes(b)
    sha = None
    if egg is not None:
        sha = hashlib.sha1(egg).hexdigest()
        e = Path(data_dir) / 'replays' / 'eggs' / (sha + '.egg')
        e.parent.mkdir(parents=True, exist_ok=True)
        e.write_bytes(egg)
    info = json.loads(files['Info.dat'].decode('utf-8-sig'))
    (d / 'nlm.json').write_text(json.dumps({'songName': info.get('_songName', ''), 'levelAuthor': info.get('_levelAuthorName', ''),
                                           'exportedAt': int(exported_at or time.time()), 'egg': sha, 'files': list(files)},
                                          ensure_ascii=False), encoding='utf-8')
    return h

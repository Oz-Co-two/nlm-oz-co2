"""map_hash.py（譜面ハッシュに足すファイルの並び: v2/v3 と v4（SongCore の Hashing.cs と同じ）・SHA-1 の計算）"""
import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import unitpy_helpers as H

sys.path.insert(0, str(H.ROOT))
import map_hash as mh  # noqa: E402


def test_files_v2(t):
    '''v2/v3 は _difficultyBeatmapSets の順に各 _beatmapFilename'''
    info = {'_difficultyBeatmapSets': [
        {'_difficultyBeatmaps': [{'_beatmapFilename': 'A.dat'}, {'_beatmapFilename': 'B.dat'}]},
        {'_difficultyBeatmaps': [{'_beatmapFilename': 'C.dat'}, {'_beatmapFilename': 5}]},
        'x',
    ]}
    t.eq(mh.files_for_hash(info), ['A.dat', 'B.dat', 'C.dat'], '並び')


def test_files_v4(t):
    '''v4 は audioDataFilename が先頭、続けて難易度ごとに（beatmapData, lightshowData）。重複は除かない'''
    info = {'audio': {'audioDataFilename': 'AudioData.dat'},
            'difficultyBeatmaps': [
                {'beatmapDataFilename': 'E.dat', 'lightshowDataFilename': 'L.dat'},
                {'beatmapDataFilename': 'H.dat', 'lightshowDataFilename': 'L.dat'},
                {'beatmapDataFilename': 'X.dat'},
                'x']}
    t.eq(mh.files_for_hash(info), ['AudioData.dat', 'E.dat', 'L.dat', 'H.dat', 'L.dat', 'X.dat'], '並び')
    t.eq(mh.files_for_hash({'difficultyBeatmaps': []}), [], '空')
    t.eq(mh.files_for_hash(None), [], 'dictでない')


def test_compute(t):
    '''Info.dat のバイト列のあとに各ファイルを順に足した SHA-1（小文字）。無いファイル(None)は飛ばす'''
    exp = hashlib.sha1(b'INFO' + b'aa' + b'cc').hexdigest()
    t.eq(mh.compute(b'INFO', [b'aa', None, b'cc']), exp, 'hash')
    t.eq(mh.compute(b'INFO', []), hashlib.sha1(b'INFO').hexdigest(), 'Info のみ')

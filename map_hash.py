# 譜面フォルダの識別子（ハッシュ）の計算（MEDIAライブラリ・2026-10-12）
#
# Beat Saber（SongCore）・BeatSaver・BeatLeader・ゲームのプレイ記録（PlayerData.dat の levelId「custom_level_<ハッシュ>」）は、
# 同じ版の譜面を同じハッシュで指す。中身は「Info.dat のバイト列のあとに、Info.dat が指す譜面ファイルのバイト列を順に足した物」の SHA-1。
# どのファイルをどの順に足すかは Info.dat の形式で違う（files_for_hash）。
# 走査（media_library.py）は譜面ファイルを解析のために1回だけ読むので、その同じバイト列をここへ渡して計算する（2回読まない）。
import hashlib


def files_for_hash(info):
    """ハッシュに足すファイル名を、足す順に返す（Info.dat 自体は含めない）。info は Info.dat を json.loads した物。
    v2/v3: _difficultyBeatmapSets の順に、各 _difficultyBeatmaps の _beatmapFilename。
    v4: 先頭に audio.audioDataFilename、続けて difficultyBeatmaps の順に（beatmapDataFilename, lightshowDataFilename）の組。
        SongCore の Hashing.ComputeCustomLevelHash（BeatmapLevelSaveData 版）と同じ。同じファイル名が何度出ても重複は除かず、そのつど足す
        （例: 全難易度が同じ lightshow を指していれば、その数だけ足される）。ファイルが無い物は compute 側で飛ばす"""
    out = []
    if not isinstance(info, dict):
        return out
    if isinstance(info.get('difficultyBeatmaps'), list):   # v4
        au = info.get('audio')
        if isinstance(au, dict) and isinstance(au.get('audioDataFilename'), str):
            out.append(au['audioDataFilename'])
        for d in info['difficultyBeatmaps']:
            if not isinstance(d, dict):
                continue
            for k in ('beatmapDataFilename', 'lightshowDataFilename'):
                if isinstance(d.get(k), str):
                    out.append(d[k])
        return out
    for s in info.get('_difficultyBeatmapSets') or []:
        if not isinstance(s, dict):
            continue
        for d in s.get('_difficultyBeatmaps') or []:
            if isinstance(d, dict) and isinstance(d.get('_beatmapFilename'), str):
                out.append(d['_beatmapFilename'])
    return out


def compute(info_bytes, file_bytes):
    """info_bytes = Info.dat のバイト列、file_bytes = files_for_hash の順に読んだバイト列のリスト（無いファイルは None＝飛ばす）。
    小文字の16進40文字を返す（PlayerData の levelId は大文字なので照合の時に小文字へそろえる）"""
    h = hashlib.sha1()
    h.update(info_bytes)
    for b in file_bytes:
        if b is not None:
            h.update(b)
    return h.hexdigest()

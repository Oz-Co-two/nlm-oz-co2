"""BeatLeader のリプレイ（.bsor）を読む（2026-11-22・REPLAY の窓＝replays.py が一覧・再生・ミスの位置を作るために使う）。
標準ライブラリだけ（サーバーの頭で読んでも軽い）。元は Auto Note Plotter（同じ作者・GPLv3）の automap/bsor.py。

形式は BeatLeader の Open Replay Format（https://github.com/BeatLeader/BS-Open-Replay ・MIT）。公式の読み込み
（https://github.com/BeatLeader/ReplayDecoder ・MIT）と同じ癖に合わせる:
- 文字列の長さがおかしい（負・1000 超）時は 1 バイトずらして読み直す（古い mod の不具合）。
- ノーツの番号が -1、または 100000 未満で下 1 桁が 9 の時はボム（番号に 4 を足す）。
フレーム（頭と両手の位置・向き）は数と最後の時刻だけ読む（見るのは BL のリプレイアプリ）。

1 つのノーツの点（cut_score）は BL のリプレイアプリ（BeatSaber-Web-Replays の組み立て済みの物・2026-11 に写した版）と同じ式:
振り始め 70（beforeCutRating×70・アークの尾は 70 のまま）・振り終わり 30（afterCutRating×30・アークの頭は 30 のまま・チェーンの頭は 0）・
真ん中 15（中心からの距離 0.3 で 0）。チェーンの後ろの部分は 20 のまま。満点（MAX_CUT）は種類ごと（公式の ScoreDefinitions の合計）。
.bsor は信用しない（他人から受け取ることもある）: 途中で終わる・数がおかしい物は BsorError（読み足りないだけの時は BsorShort）。
"""
import math
import struct

MAGIC = 0x442D3D69
GOOD, BAD, MISS, BOMB = 0, 1, 2, 3
FRAME_SIZE = 4 + 4 + 3 * 7 * 4   # 時刻・fps・頭／左手／右手（位置 3＋回転 4）
_CUT = struct.Struct('<????f3fiff3f3f4f')   # 切った時の情報（GOOD・BAD の時だけ付く・72 バイト）
INFO_KEYS = ('version', 'game_version', 'timestamp', 'player_id', 'player_name', 'platform', 'tracking_system', 'hmd',
             'controller', 'hash', 'song_name', 'mapper', 'difficulty')
# 点の種類（番号の頭＝ゲームの ScoringType＋2）。1 Ignore・2 NoScore・3 Normal・4 ArcHead・5 ArcTail・6 ChainHead・7 ChainLink・
# 8 ArcHeadArcTail・9 ChainHeadArcTail・10 ChainLinkArcHead・11 ChainHeadArcHead・12 ChainHeadArcHeadArcTail（0 は古い形＝通常）
ST_ARC_HEAD, ST_ARC_TAIL, ST_CHAIN_HEAD, ST_CHAIN_LINK = 4, 5, 6, 7
ST_ARC_BOTH, ST_CHAIN_HEAD_ARC_TAIL, ST_CHAIN_LINK_ARC_HEAD = 8, 9, 10
# 種類 → 1 つの満点（公式の NoteParams.ScoreDefinitions の合計）。無い・古い（0・1）は通常
MAX_CUT = {2: 0, 3: 115, 4: 115, 5: 115, 6: 85, 7: 20, 8: 115, 9: 115, 10: 20, 11: 115, 12: 115}
CHAIN_LINKS = (ST_CHAIN_LINK, ST_CHAIN_LINK_ARC_HEAD)   # チェーンの後ろの部分（点は 20 のまま）
MAX_HEAD = 1024 * 1024   # 頭（情報の部分）を探す上限（普通は数百バイト）


class BsorError(ValueError):
    pass


class BsorShort(BsorError):
    """途中で終わっている（もっと読めば読めるかもしれない）"""


class _R:
    def __init__(self, data):
        self.d, self.p = data, 0

    def take(self, n):
        if n < 0 or self.p + n > len(self.d):
            raise BsorShort(f'.bsor が途中で終わっている（{self.p} バイト目で {n} バイト足りない）')
        b = self.d[self.p:self.p + n]
        self.p += n
        return b

    def i32(self):
        return struct.unpack('<i', self.take(4))[0]

    def i64(self):
        return struct.unpack('<q', self.take(8))[0]

    def f32(self):
        return struct.unpack('<f', self.take(4))[0]

    def u8(self):
        return self.take(1)[0]

    def text(self):
        n = self.i32()
        while n > 1000 or n < 0:   # 公式の DecodeString と同じ: 1 バイトずらして読み直す
            self.take(1)
            n = struct.unpack('<i', self.d[self.p - 4:self.p])[0]
        return self.take(n).decode('utf-8', errors='replace')


def _info(r):
    if r.i32() != MAGIC:
        raise BsorError('.bsor ではない（頭の印が違う）')
    if r.u8() != 1:
        raise BsorError('知らない版の .bsor')
    if r.u8() != 0:
        raise BsorError('情報の部分が無い')
    info = {k: r.text() for k in INFO_KEYS}
    info['score'] = r.i32()
    info['mode'], info['environment'], info['modifiers'] = r.text(), r.text(), r.text()
    info['jump_distance'] = r.f32()
    info['left_handed'] = r.u8() != 0
    info['height'], info['start_time'], info['fail_time'], info['speed'] = r.f32(), r.f32(), r.f32(), r.f32()
    return info


def read_info(path, head=16384):
    """リプレイの頭（曲・難易度・hash・点・修飾…）だけを読む（ファイルの頭の数 KB）。足りなければ MAX_HEAD まで読み足す"""
    with open(path, 'rb') as f:
        data = f.read(head)
        while True:
            try:
                return _info(_R(data))
            except BsorShort:
                more = f.read(head) if len(data) < MAX_HEAD else b''
                if not more:
                    raise
                data += more


def note_params(note_id):
    """ノーツの番号 → (点の種類, 列, 段, 色, 向き)。公式の NoteParams と同じ分け方（100000 以上は列・段の大きい譜面の形）"""
    i = note_id
    if i < 100000:
        st, i = divmod(i, 10000)
        x, i = divmod(i, 1000)
        y, i = divmod(i, 100)
    else:
        st, i = divmod(i, 10000000)
        x, i = divmod(i, 1000000)
        y, i = divmod(i, 100000)
    c, d = divmod(i, 10)
    return st, x, y, c, d


def _note(r):
    nid, t, spawn, kind = r.i32(), r.f32(), r.f32(), r.i32()
    n = {'id': nid, 'time': t, 'spawn': spawn, 'type': kind}
    if kind in (GOOD, BAD):
        v = _CUT.unpack(r.take(_CUT.size))
        n['cut'] = {'speed_ok': v[0], 'direction_ok': v[1], 'saber_type_ok': v[2], 'too_soon': v[3], 'saber_type': v[8],
                    'distance': v[17], 'before': v[19], 'after': v[20]}
    if nid == -1 or (0 < nid < 100000 and nid % 10 == 9):
        n['id'] = nid + 4
        n['type'] = BOMB
    return n


def _new(info):
    return {'info': info, 'frames': 0, 'end': None, 'notes': [], 'walls': [], 'heights': [], 'pauses': []}


def parse(data):
    """→ {info, frames（数だけ）, end（最後のフレームの時刻＝記録が終わった所・フレームが無ければ None）, notes: [{id, time, spawn, type, cut?}],
    walls, heights, pauses}"""
    r = _R(data)
    return _sections(r, _new(_info(r)))


def _sections(r, out):
    data = r.d
    while r.p < len(data):
        kind = r.u8()
        if kind == 1:
            n = r.i32()
            fr = r.take(n * FRAME_SIZE)
            out['frames'] = n
            if n > 0:
                out['end'] = struct.unpack_from('<f', fr, (n - 1) * FRAME_SIZE)[0]
        elif kind == 2:
            out['notes'] = [_note(r) for _ in range(max(0, r.i32()))]
        elif kind == 3:
            out['walls'] = [{'id': r.i32(), 'energy': r.f32(), 'time': r.f32(), 'spawn': r.f32()} for _ in range(max(0, r.i32()))]
        elif kind == 4:
            out['heights'] = [(r.f32(), r.f32()) for _ in range(max(0, r.i32()))]
        elif kind == 5:
            out['pauses'] = [(r.i64(), r.f32()) for _ in range(max(0, r.i32()))]
        else:
            break   # 6（セイバーのずれ）・7（任意のデータ）は使わない
    return out


def read(path):
    """ファイルを読む（フレームは読み飛ばす＝ファイルの 9 割を読まない・一覧で数百個を読むため）"""
    with open(path, 'rb') as f:
        head = f.read(65536)
        try:
            r = _R(head)
            info = _info(r)
        except BsorShort:   # 頭が 64KB を超える（無いはず）・途中で終わっている → 全部読む
            f.seek(0)
            return parse(f.read())
        out = _new(info)
        f.seek(r.p)
        if f.read(1) == b'\x01':
            b = f.read(4)
            if len(b) < 4:
                raise BsorShort('.bsor が途中で終わっている（フレームの数）')
            n = struct.unpack('<i', b)[0]
            end = f.seek(0, 2)
            if n < 0 or r.p + 5 + n * FRAME_SIZE > end:
                raise BsorShort('.bsor が途中で終わっている（フレーム）')
            out['frames'] = n
            if n > 0:   # 最後のフレームの時刻だけ読む（記録が終わった所＝途中でやめた・失敗したプレイはそこまで）
                f.seek(r.p + 5 + (n - 1) * FRAME_SIZE)
                out['end'] = struct.unpack('<f', f.read(4))[0]
            f.seek(r.p + 5 + n * FRAME_SIZE)
        else:
            f.seek(r.p)
        return _sections(_R(f.read()), out)


def note_max(note_id):
    """1 つのノーツの満点（種類ごと）"""
    return MAX_CUT.get(note_params(note_id)[0], 115)


def _clamp(v, lo, hi):
    return lo if not math.isfinite(v) or v < lo else hi if v > hi else v


def _round(v):
    """JS の Math.round と同じ（.5 は上へ。Python の round は偶数へ寄せるので使わない）"""
    return math.floor(v + 0.5)


def cut_score(note):
    """切ったノーツ（GOOD）の点（振り始め＋振り終わり＋真ん中）。BL のリプレイアプリと同じ式（このファイルの頭の説明）"""
    cut = note.get('cut') or {}
    st = note_params(note['id'])[0]
    if st in CHAIN_LINKS:
        return 20
    if st in (ST_ARC_TAIL, ST_ARC_BOTH, ST_CHAIN_HEAD_ARC_TAIL):
        before = 70
    else:
        before = _clamp(_round(70 * _clamp(cut.get('before', 0.0), -10, 10)), 0, 70)
    if st == ST_CHAIN_HEAD:
        after = 0
    elif st in (ST_ARC_HEAD, ST_ARC_BOTH, ST_CHAIN_HEAD_ARC_TAIL):
        after = 30
    else:
        after = _clamp(_round(30 * _clamp(cut.get('after', 0.0), -10, 10)), 0, 30)
    acc = _round(15 * (1 - _clamp(cut.get('distance', 1.0) / 0.3, 0, 1)))
    return min(int(before + after + acc), note_max(note['id']))


def _mult_up(mult, prog):
    if mult < 8:
        prog += 1
        if prog >= mult * 2:
            mult, prog = mult * 2, 0
    return mult, prog


def max_score(notes):
    """切るノーツ（ボムを除く）の満点（コンボの倍率 1→2→4→8 を、出てくる順に掛ける）"""
    total, mult, prog = 0, 1, 0
    for n in sorted((n for n in notes if n['type'] != BOMB), key=lambda n: n['spawn']):
        mult, prog = _mult_up(mult, prog)
        total += note_max(n['id']) * mult
    return total


def base_score(rep):
    """修飾を掛ける前の点（ゲームの倍率の数え方: 良く切る→上がる、悪い切り方・見逃し・ボム・壁→1 つ下がる・出来事の時刻順）"""
    evs = [(n['time'], 0, n) for n in rep['notes']] + [(w['time'], 1, None) for w in rep['walls']]
    evs.sort(key=lambda e: (e[0] if math.isfinite(e[0]) else 0, e[1]))
    total, mult, prog = 0, 1, 0
    for _, is_wall, n in evs:
        if not is_wall and n['type'] == GOOD:
            mult, prog = _mult_up(mult, prog)
            total += cut_score(n) * mult
        else:
            prog = 0
            if mult > 1:
                mult //= 2
    return total


def summary(rep):
    """一覧に出す数: {notes, misses（見逃し）, bad（悪い切り方）, bombs, walls, acc（修飾の前の点÷満点・0〜1・切るノーツが無ければ None）,
    end（記録が終わった秒）}"""
    ns = rep['notes']
    mx = max_score(ns)
    acc = None
    if mx:
        acc = round(_clamp(base_score(rep) / mx, 0, 1), 5)
    return {'notes': sum(1 for n in ns if n['type'] != BOMB), 'misses': sum(1 for n in ns if n['type'] == MISS),
            'bad': sum(1 for n in ns if n['type'] == BAD), 'bombs': sum(1 for n in ns if n['type'] == BOMB),
            'walls': len(rep['walls']), 'acc': acc,
            'end': summary_end(rep)}


_KIND = {GOOD: 'good', BAD: 'bad', MISS: 'miss', BOMB: 'bomb'}


def _sec(v):
    return round(v, 4) if isinstance(v, float) and math.isfinite(v) else None


def events(rep, limit=200000):
    """ミスの印などに使う出来事: notes＝[{t（そのノーツの曲の秒）, type, x, y, c, d, score, max}]（t の順）・walls＝[{t（壁に入った秒）}]。
    score・max は good の時だけ（ほかは None）。ボムの色・向きは None"""
    notes = []
    for n in rep['notes'][:limit]:
        t = _sec(n.get('spawn'))
        k = _KIND.get(n['type'])
        if t is None or k is None:
            continue
        st, x, y, c, d = note_params(n['id'])
        e = {'t': t, 'type': k, 'x': x, 'y': y, 'c': c, 'd': d, 'score': None, 'max': None}
        if k == 'good':
            e['score'], e['max'] = cut_score(n), note_max(n['id'])
        elif k == 'bomb':
            e['c'] = e['d'] = None
        notes.append(e)
    notes.sort(key=lambda e: e['t'])
    walls = sorted(({'t': t} for t in (_sec(w.get('time')) for w in rep['walls'][:limit]) if t is not None), key=lambda e: e['t'])
    return {'notes': notes, 'walls': walls, 'endSec': summary_end(rep)}


def summary_end(rep):
    end = rep.get('end')
    return round(end, 3) if isinstance(end, float) and math.isfinite(end) else None

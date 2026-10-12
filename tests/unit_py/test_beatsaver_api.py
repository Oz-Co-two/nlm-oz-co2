"""beatsaver_api.py（BeatSaver への1曲の問い合わせ: 形の変換・版の不一致・404の記録・429と待ち時間・1秒の間隔・同時1つ。本物のネットには出ない）"""
import io
import json
import sys
import tempfile
import threading
import urllib.error
from email.message import Message
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import unitpy_helpers as H

sys.path.insert(0, str(H.ROOT))
import beatsaver_api as bs  # noqa: E402

HASH = 'a' * 40
OLD = 'b' * 40

BODY = {
    'id': '103FB', 'name': 'x',
    'uploaded': '2020-09-13T12:26:40.000Z',
    'stats': {'upvotes': 1551, 'downvotes': 264},
    'ranked': True, 'qualified': False, 'blRanked': True, 'blQualified': False,
    'tags': ['anime', 'tech'],
    'versions': [
        {'hash': OLD, 'diffs': [{'characteristic': 'Standard', 'difficulty': 'Expert', 'stars': 1.5}]},
        {'hash': HASH, 'diffs': [
            {'characteristic': 'Standard', 'difficulty': 'ExpertPlus', 'stars': 8.724, 'blStars': 9.86},
            {'characteristic': 'Standard', 'difficulty': 'Hard', 'stars': 0},
            {'characteristic': 'Evil', 'difficulty': 'Hard', 'stars': 3},
            {'characteristic': 'OneSaber', 'difficulty': 'Easy', 'blStars': 2},
        ]},
    ],
}


class _Resp:
    def __init__(self, body, headers=None):
        self._b = io.BytesIO(body)
        self.headers = headers or {}
        self.status = 200

    def read(self, n=-1):
        return self._b.read(n)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _http_error(code, body=b'', headers=None):
    m = Message()
    for k, v in (headers or {}).items():
        m[k] = v
    return urllib.error.HTTPError(bs.API + HASH, code, 'x', m, io.BytesIO(body))


class _Env:
    """偽の opener・時計・sleep。replies は順に返す（例外ならそれを投げる）"""
    def __init__(self, replies):
        self.replies = list(replies)
        self.reqs = []
        self.now = 1_800_000_000.0
        self.sleeps = []

    def opener(self, req, timeout=None):
        self.reqs.append((req, timeout))
        r = self.replies.pop(0)
        if isinstance(r, Exception):
            raise r
        return r

    def clock(self):
        return self.now

    def sleep(self, s):
        self.sleeps.append(s)
        self.now += s


def _mk(replies):
    env = _Env(replies)
    d = tempfile.mkdtemp(prefix='nlm_unitpy_bs_')
    return bs.BeatSaverLookup(d, opener=env.opener, clock=env.clock, sleep=env.sleep), env, Path(d)


def _ok(body=BODY):
    return _Resp(json.dumps(body).encode())


def test_lookup_matching_version(t):
    '''自分のハッシュの版が返れば match:hash。★(2桁)・ランク状態・タグ・日付・投票が入り、記録される'''
    b, env, d = _mk([_ok()])
    r = b.lookup(HASH)
    t.eq(r['src'], 'beatsaver', 'src')
    t.eq(r['match'], 'hash', 'match')
    t.eq(r['key'], '103fb', 'key は小文字')
    t.eq(r['uploaded'], 1600000000, '日付')
    t.eq((r['up'], r['down']), (1551, 264), '投票')
    t.eq(r['ranked'], {'bl': True, 'blq': False, 'ss': True, 'ssq': False}, 'ランク状態')
    t.eq(r['tags'], ['anime', 'tech'], 'タグ')
    t.eq(r['diffs'], {'Standard/ExpertPlus': {'bl': 9.86, 'ss': 8.72}, 'OneSaber/Easy': {'bl': 2.0}}, '★（0・不明な特性は無し）')
    req, to = env.reqs[0]
    t.eq(req.full_url, bs.API + HASH, 'URL はコードの固定＋ハッシュ')
    t.ok(req.full_url.startswith('https://api.beatsaver.com/maps/hash/'), 'api.beatsaver.com')
    t.eq(to, bs.TIMEOUT, '時間切れ')
    t.ok(req.get_header('User-agent', '').startswith('NonLinearMapper'), 'User-Agent')
    t.eq(b.cached(HASH), r, '記録される')
    t.eq(json.loads((d / 'config' / 'beatsaver_cache.json').read_text(encoding='utf-8'))['maps'][HASH]['key'], '103fb', 'ファイル')


def test_lookup_old_version_is_key_match(t):
    '''返ってきた版のハッシュが問い合わせたものと違う（手元が古い）なら match:key ＝★とランク状態は入れない'''
    b, env, d = _mk([_ok()])
    r = b.lookup('c' * 40)
    t.eq(r['match'], 'key', 'match')
    t.ok('ranked' not in r, 'ランク状態なし')
    t.eq(r['diffs'], {}, '★なし')
    t.eq(r['key'], '103fb', 'キーは入る')


def test_404_recorded(t):
    '''404 は {src:none, bsMissAt} を記録して返す'''
    b, env, d = _mk([_http_error(404)])
    r = b.lookup(HASH)
    t.eq(r, {'src': 'none', 'bsMissAt': int(env.now)}, '返り値')
    t.eq(b.cached(HASH), r, '記録')
    t.eq(b.cached(OLD), None, '別のハッシュは無し')


def test_bad_hash_rejected(t):
    '''40桁の小文字16進以外は通信せずに拒否（URL・大文字・パス・長さ違い）'''
    b, env, d = _mk([])
    for h in ('A' * 40, 'a' * 39, 'a' * 41, '../x', 'http://evil/', 'a' * 39 + '/', '', None, 5, 'g' * 40, ('a' * 40) + '\n'):
        t.eq(b.lookup(h), {'error': 'badHash'}, repr(h))
    t.eq(env.reqs, [], '通信していない')
    t.eq(b.cached('A' * 40), None, 'cached も同じ')


def test_429_retry_after_header(t):
    '''429 は Retry-After（秒）まで止める。止めている間は通信せず busy を返す。過ぎたら再開'''
    b, env, d = _mk([_http_error(429, b'', {'Retry-After': '120'}), _ok()])
    r = b.lookup(HASH)
    t.eq(r, {'error': 'busy', 'retryAfter': 120}, '429')
    env.now += 30
    r = b.lookup(HASH)
    t.eq(r['error'], 'busy', '止め期間中')
    t.eq(r['retryAfter'], 90, '残り')
    t.eq(len(env.reqs), 1, '通信していない')
    env.now += 100
    t.eq(b.lookup(HASH)['src'], 'beatsaver', '期間が過ぎたら再開')
    # 再起動しても止め期間を守る
    b2, env2, d2 = _mk([_http_error(429, b'', {'Retry-After': '300'})])
    b2.lookup(HASH)
    b3 = bs.BeatSaverLookup(str(d2), opener=env2.opener, clock=env2.clock, sleep=env2.sleep)
    t.eq(b3.lookup(HASH)['error'], 'busy', '別インスタンスでも')
    t.eq(len(env2.reqs), 1, '通信していない（再起動後）')


def test_429_wait_sources(t):
    '''待ち時間は Retry-After → 本文の resetAfter(ミリ秒) → 10分。1時間で切る。負・数値でない値は無視'''
    cases = [
        ({'Retry-After': '45'}, b'{"resetAfter": 9000}', 45, 'ヘッダー優先'),
        ({}, b'{"resetAfter": 90000}', 90, '本文 resetAfter（ミリ秒→秒）'),
        ({}, b'{"resetAfter": 1500}', 2, '端数は切り上げ'),
        ({}, b'', 600, '何も無ければ10分'),
        ({'Retry-After': 'soon'}, b'{"resetAfter": "x"}', 600, '数値でない'),
        ({'Retry-After': '-5'}, b'{"resetAfter": -1}', 600, '負'),
        ({'Retry-After': '999999'}, b'', 3600, 'ヘッダーは1時間で切る'),
        ({}, b'{"resetAfter": 99999999999999}', 600, 'ありえない大きさは無視'),
        ({}, b'{"resetAfter": 7200000}', 3600, '本文も1時間で切る'),
        ({}, b'[1,2]', 600, 'JSONの形違い'),
        ({}, b'\xff\xfe', 600, '壊れた本文'),
        ({'Retry-After': 'Wed, 21 Oct 2015 07:28:00 GMT'}, b'{"resetAfter": 20000}', 20, '日付形式はヘッダーとして読まない'),
    ]
    for hd, body, want, label in cases:
        b, env, d = _mk([_http_error(429, body, hd)])
        r = b.lookup(HASH)
        t.eq(r, {'error': 'busy', 'retryAfter': want}, label)


def test_min_gap_one_second(t):
    '''前の問い合わせから1秒未満なら、足りない分だけ待ってから問い合わせる'''
    b, env, d = _mk([_ok(), _ok()])
    b.lookup(HASH)
    t.eq(env.sleeps, [], '最初は待たない')
    env.now += 0.4
    b.lookup(HASH)
    t.eq(len(env.sleeps), 1, '2回目は待つ')
    t.ok(abs(env.sleeps[0] - 0.6) < 1e-6, f'残りの0.6秒: {env.sleeps}')
    env.now += 5
    b2, env2, d2 = _mk([_ok(), _ok()])
    b2.lookup(HASH)
    env2.now += 1.5
    b2.lookup(HASH)
    t.eq(env2.sleeps, [], '1秒以上あいていれば待たない')


def test_one_at_a_time(t):
    '''通信中に別の問い合わせが来たら、待たずに busy を返す（同時に1つだけ）'''
    gate = threading.Event()
    entered = threading.Event()
    env = _Env([])

    def opener(req, timeout=None):
        entered.set()
        gate.wait(5)
        return _ok()

    d = tempfile.mkdtemp(prefix='nlm_unitpy_bs_')
    b = bs.BeatSaverLookup(d, opener=opener, clock=env.clock, sleep=env.sleep)
    res = {}
    th = threading.Thread(target=lambda: res.update(r=b.lookup(HASH)))
    th.start()
    t.ok(entered.wait(5), '1つ目が通信中')
    t.eq(b.lookup(OLD), {'error': 'busy', 'retryAfter': 1}, '2つ目は busy')
    gate.set()
    th.join(5)
    t.eq(res['r']['src'], 'beatsaver', '1つ目は終わる')


def test_errors_are_returned_not_raised(t):
    '''通信エラー・時間切れ・HTTP エラー・巨大な応答・壊れた応答は例外にならず error で返り、記録しない'''
    big = _Resp(b'x', {'Content-Length': str(bs.MAX_BODY + 1)})
    big_no_len = _Resp(b'x' * (bs.MAX_BODY + 10))
    cases = [
        (urllib.error.URLError('down'), 'network'),
        (TimeoutError('t'), 'network'),
        (_http_error(500), 'http500'),
        (_http_error(403), 'http403'),
        (big, 'tooBig'),
        (big_no_len, 'tooBig'),
        (_Resp(b'<html>'), 'badResponse'),
        (_Resp(b'[]'), 'badResponse'),
        (_Resp(b'{"id": "zzz"}'), 'badResponse'),
        (_Resp(b'{"name": 1}'), 'badResponse'),
    ]
    for rep, want in cases:
        b, env, d = _mk([rep])
        r = b.lookup(HASH)
        t.eq(r, {'error': want}, want)
        t.eq(b.cached(HASH), None, f'{want} は記録しない')


def test_untrusted_values_clamped(t):
    '''ありえない値・形の違う値は捨てる（日付・投票・★・タグ・ランク状態は True の時だけ真）'''
    body = dict(BODY, uploaded='not a date', stats={'upvotes': 2 ** 50, 'downvotes': 'x'}, tags=['ok', 5, 'x' * 500],
                ranked='yes', blRanked=1)
    body['versions'] = [{'hash': HASH.upper(), 'diffs': [{'characteristic': 'Standard', 'difficulty': 'Expert', 'stars': 10 ** 9, 'blStars': True}]}]
    b, env, d = _mk([_ok(body)])
    r = b.lookup(HASH)
    t.eq(r['match'], 'hash', '大文字のハッシュも同じ版')
    t.eq((r['uploaded'], r['up'], r['down']), (0, 0, 0), '日付・投票')
    t.eq(r['tags'], ['ok', 'x' * 60], 'タグ')
    t.eq(r['ranked'], {'bl': False, 'blq': False, 'ss': False, 'ssq': False}, 'True 以外は偽')
    t.eq(r['diffs'], {}, '★')

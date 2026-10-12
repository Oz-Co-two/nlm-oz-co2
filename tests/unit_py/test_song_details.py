"""song_details.py（全曲データ: protobuf の読み取り・照合・ETag/24時間/サイズ上限/壊れたデータ。本物のネットには出ない）"""
import gzip
import http.server
import struct
import sys
import tempfile
import threading
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import unitpy_helpers as H

sys.path.insert(0, str(H.ROOT))
import song_details as sd  # noqa: E402


# ---- 小さな protobuf を組み立てる ----
def _vi(n):
    out = bytearray()
    while True:
        b = n & 0x7f
        n >>= 7
        if n:
            out.append(b | 0x80)
        else:
            out.append(b)
            return bytes(out)


def _f_int(fn, v):
    return _vi(fn << 3) + _vi(v)


def _f_len(fn, b):
    return _vi(fn << 3 | 2) + _vi(len(b)) + b


def _f_float(fn, v):
    return _vi(fn << 3 | 5) + struct.pack('<f', v)


def _diff(ch=None, df=None, ss=0, bl=0):
    b = b''
    if ch is not None:
        b += _f_int(1, ch)
    if df is not None:
        b += _f_int(2, df)
    if ss:
        b += _f_int(4, ss)
    if bl:
        b += _f_int(5, bl)
    return b


def _song(mapid, up=0, down=0, uploaded=0, states=0, tags=0, diffs=(), name='n'):
    b = _f_float(1, 120.0) + _f_int(2, up) + _f_int(3, down) + _f_int(4, uploaded) + _f_int(5, mapid)
    b += _f_len(7, name.encode())
    for d in diffs:
        b += _f_len(11, d)
    if states:
        b += _f_int(13, states)
    if tags:
        b += _f_int(14, tags)
    return b


H1, H2, H3 = bytes([1] * 20), bytes([2] * 20), bytes([3] * 20)


def _container(version=3, songs=None, hashes=None, tags=('tech', 'anime'), scrape=1700000000):
    if songs is None:
        songs = [
            # 0x103fb: 両方のランク・★あり。特性/難易度の無い難易度は Standard/ExpertPlus
            _song(0x103fb, up=1551, down=264, uploaded=1600000000, states=sd.RS_SS | sd.RS_BL, tags=0b10,
                  diffs=[_diff(None, None, ss=872, bl=986), _diff(1, 3, ss=0, bl=0), _diff(1, 0, ss=100), _diff(6, 4)]),
            _song(0x2a, up=5, diffs=[_diff(1, 4, ss=0, bl=0)]),
            _song(0xffffffff, tags=0b11, states=sd.RS_SSQ | sd.RS_BLQ, diffs=[_diff(5, 3, bl=1234)]),
        ]
        hashes = H1 + H2 + H3
    b = _f_int(1, version) + _f_int(2, scrape)
    if hashes is not None:
        b += _f_len(3, hashes)
    for s in songs:
        b += _f_len(4, s)
    for t in tags:
        b += _f_len(5, t.encode())
    return b


def _write_gz(path, raw):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_bytes(gzip.compress(raw))


def _sd(clock=None, opener=None):
    d = tempfile.mkdtemp(prefix='nlm_unitpy_sd_')
    return sd.SongDetails(d, opener=opener, clock=clock), Path(d)


def _hx(b):
    return b.hex()


def test_lookup_by_hash(t):
    '''ハッシュで当たれば match:hash。★(100で割る・0は無し)・ランク状態・タグ名・投票・日付が入る'''
    s, d = _sd()
    _write_gz(s.gz, _container())
    r = s.lookup(hash=_hx(H1))
    t.eq(r['src'], 'dump', 'src')
    t.eq(r['match'], 'hash', 'match')
    t.eq(r['key'], '103fb', 'key')
    t.eq((r['up'], r['down'], r['uploaded']), (1551, 264, 1600000000), '投票・日付')
    t.eq(r['ranked'], {'bl': True, 'blq': False, 'ss': True, 'ssq': False}, 'ランク状態')
    t.eq(r['tags'], ['anime'], 'タグ（第1ビット=2番目）')
    t.eq(r['diffs'], {'Standard/ExpertPlus': {'bl': 9.86, 'ss': 8.72}, 'Standard/Easy': {'ss': 1.0}}, '★')
    r3 = s.lookup(hash=_hx(H3))
    t.eq(r3['key'], 'ffffffff', '32ビットのキー')
    t.eq(r3['ranked'], {'bl': False, 'blq': True, 'ss': False, 'ssq': True}, 'qualified')
    t.eq(r3['tags'], ['tech', 'anime'], '複数タグ')
    t.eq(r3['diffs'], {'360Degree/Expert': {'bl': 12.34}}, '特性名')
    t.eq(s.lookup(hash=_hx(bytes([9] * 20))), None, '無い')


def test_lookup_by_key_only(t):
    '''キーでだけ当たれば match:key で★とランク状態を入れない。ハッシュが当たればキーより優先'''
    s, d = _sd()
    _write_gz(s.gz, _container())
    r = s.lookup(hash='f' * 40, key='103FB')
    t.eq(r['match'], 'key', 'match')
    t.ok('ranked' not in r, 'ランク状態なし')
    t.eq(r['diffs'], {}, '★なし')
    t.eq((r['up'], r['down']), (1551, 264), '投票は入る')
    r = s.lookup(hash=_hx(H2), key='103fb')
    t.eq((r['match'], r['key']), ('hash', '2a'), 'ハッシュ優先')
    t.eq(s.lookup(key='zzz'), None, '不正なキー')
    t.eq(s.lookup(key='99999'), None, '無いキー')
    t.eq(s.lookup(), None, '引数なし')
    t.eq(s.lookup(hash='abc'), None, '短いハッシュ')


def test_diff_enum_defaults(t):
    '''特性・難易度の無い難易度は Standard/ExpertPlus。範囲外の列挙値は捨てる'''
    s, d = _sd()
    raw = _container(songs=[_song(1, diffs=[_diff(None, None, ss=500), _diff(1, 9, ss=100), _diff(99, 1, ss=100), _diff(4, 2, ss=700)])],
                     hashes=H1)
    _write_gz(s.gz, raw)
    r = s.lookup(hash=_hx(H1))
    t.eq(r['diffs'], {'Standard/ExpertPlus': {'ss': 5.0}, '90Degree/Hard': {'ss': 7.0}}, '既定値と範囲外')


def test_broken_data_never_raises(t):
    '''壊れた・途中で切れた・でたらめなデータでも lookup は例外を出さず None（または読めた分だけ）'''
    good = _container()
    cases = {
        '途中で切れる': good[:len(good) // 2],
        '末尾が切れる': good[:-3],
        'でたらめ': bytes(range(256)) * 4,
        '空': b'',
        'フィールド0': b'\x00\x01',
        '長さが範囲外': _f_int(1, 3) + _vi(4 << 3 | 2) + _vi(10 ** 9),
        '曲数よりハッシュが短い': _container(hashes=H1),
        'varintが終わらない': _f_int(1, 3) + b'\xff' * 20,
    }
    for label, raw in cases.items():
        s, d = _sd()
        _write_gz(s.gz, raw)
        for kw in ({'hash': _hx(H1)}, {'key': '103fb'}):
            try:
                s.lookup(**kw)
            except Exception as e:  # noqa: BLE001
                t.ok(False, f'{label}: 例外 {e!r}')
    s, d = _sd()
    Path(s.gz).parent.mkdir(parents=True, exist_ok=True)
    Path(s.gz).write_bytes(b'not a gzip')
    t.eq(s.lookup(hash=_hx(H1)), None, 'gzipでない')
    # 壊れた曲があっても他の曲は引ける
    bad_song = _vi(5 << 3) + b'\x80'   # mapId の varint が途中で終わる
    raw = _container(songs=[_song(0x10, up=1), bad_song], hashes=H1 + H2)
    _write_gz(s.gz, raw)
    t.eq(s.lookup(hash=_hx(H1))['key'], '10', '壊れた曲の手前は引ける')
    t.eq(s.lookup(hash=_hx(H2)), None, '壊れた曲は無し')


def test_huge_numbers_are_clamped(t):
    '''ありえない大きさの数値は 0（無し）または上限に丸める'''
    s, d = _sd()
    raw = _container(songs=[_song(1, up=2 ** 40, uploaded=2 ** 40, diffs=[_diff(1, 4, ss=10 ** 9, bl=10 ** 9)])], hashes=H1)
    _write_gz(s.gz, raw)
    r = s.lookup(hash=_hx(H1))
    t.eq(r['up'], 0xffffffff, '投票は上限')
    t.eq(r['uploaded'], 0, '日付は無し')
    t.eq(r['diffs'], {}, '★は無し')


def test_unsupported_format(t):
    '''formatVersion が 3 でなければ使わない（lookup は None）'''
    s, d = _sd()
    _write_gz(s.gz, _container(version=4))
    t.eq(s.lookup(hash=_hx(H1)), None, 'v4は使わない')


def test_reload_when_file_changes(t):
    '''ファイルが差し替わったら読み直す'''
    s, d = _sd()
    _write_gz(s.gz, _container())
    t.eq(s.lookup(hash=_hx(H2))['key'], '2a', '1回目')
    raw = _container(songs=[_song(0x777, up=9)], hashes=H2)
    _write_gz(s.gz, raw)
    t.eq(s.lookup(hash=_hx(H2))['key'], '777', '差し替え後')
    t.eq(s.lookup(hash=_hx(H1)), None, '前の曲は消える')


# ---- 取得（偽の HTTP サーバー。取得先 URL はコードに固定なので、opener で偽サーバーへ向け直す） ----
class _Fake:
    def __init__(self):
        self.body = gzip.compress(_container())
        self.etag = 'W/"abc"'
        self.hits = []
        self.status = None      # 固定で返す状態（500 等）
        self.chunked_big = 0    # >0: Content-Length なしでこの量を流す
        fake = self

        class Hd(http.server.BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                fake.hits.append(dict(self.headers))
                if fake.status:
                    self.send_response(fake.status)
                    self.send_header('Content-Length', '0')
                    self.end_headers()
                    return
                if self.headers.get('If-None-Match') == fake.etag:
                    self.send_response(304)
                    self.send_header('Content-Length', '0')
                    self.end_headers()
                    return
                self.send_response(200)
                self.send_header('ETag', fake.etag)
                if fake.chunked_big:
                    self.send_header('Connection', 'close')
                    self.end_headers()
                    try:
                        for _ in range(fake.chunked_big // 65536):
                            self.wfile.write(b'x' * 65536)
                    except OSError:
                        pass
                    return
                self.send_header('Content-Length', str(len(fake.body)))
                self.end_headers()
                self.wfile.write(fake.body)

        self.httpd = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Hd)
        self.url = f'http://127.0.0.1:{self.httpd.server_address[1]}/x.gz'
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.urls = []

    def opener(self, req, timeout=None):
        self.urls.append(req.full_url)
        r2 = urllib.request.Request(self.url, headers=dict(req.header_items()))
        return urllib.request.urlopen(r2, timeout=timeout)

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()


class _Clock:
    def __init__(self, t=1_800_000_000):
        self.t = t

    def __call__(self):
        return self.t


def test_update_etag_and_24h(t):
    '''初回は取得して保存。24時間未満は通信しない。24時間後は If-None-Match 付きで確認し、304 なら確認時刻だけ更新'''
    f = _Fake()
    try:
        clk = _Clock()
        s, d = _sd(clock=clk, opener=f.opener)
        t.eq(s.status()['state'], 'none', '最初は none')
        r = s.update()
        t.eq((r['did'], r['state']), ('downloaded', 'ok'), '初回')
        t.eq(r['asOf'], 1700000000, 'asOf')
        t.eq(r['fetchedAt'], clk.t, 'fetchedAt')
        t.eq(f.urls, [sd.URL], '取得先はコードの固定URL（jsDelivr）')
        t.ok(sd.URL.startswith('https://cdn.jsdelivr.net/gh/kinsi55/BeatSaberScrappedData/'), 'jsDelivrだけ')
        ua = f.hits[0].get('User-Agent', '')
        t.ok(ua.startswith('NonLinearMapper') and 'github.com/Oz-Co-two/nlm-oz-co2' in ua, 'User-Agent: ' + ua)
        t.ok('If-None-Match' not in f.hits[0], '初回は If-None-Match なし')
        t.eq(s.lookup(hash=_hx(H1))['key'], '103fb', '取得したデータで照合できる')
        clk.t += 23 * 3600
        r = s.update()
        t.eq(r['did'], 'throttled', '24時間未満')
        t.eq(len(f.hits), 1, '通信していない')
        clk.t += 2 * 3600
        r = s.update()
        t.eq(r['did'], 'notModified', '304')
        t.eq(f.hits[1].get('If-None-Match'), f.etag, 'ETag を送る')
        t.eq(r['fetchedAt'], clk.t, '確認時刻は更新')
        clk.t += 30 * 3600
        f.etag = 'W/"new"'
        f.body = gzip.compress(_container(songs=[_song(0x55, up=1)], hashes=H2, scrape=1700001234))
        r = s.update()
        t.eq((r['did'], r['asOf']), ('downloaded', 1700001234), '更新')
        t.eq(s.lookup(hash=_hx(H2))['key'], '55', '新しいデータに読み直す')
        # 状態は再起動（別インスタンス）でも残る
        s2 = sd.SongDetails(str(d), opener=f.opener, clock=clk)
        t.eq(s2.status()['asOf'], 1700001234, 'meta が残る')
    finally:
        f.close()


def test_update_failure_keeps_old_data(t):
    '''取得に失敗・壊れたデータ・形式違い・サイズ超過でも前のデータは消えない。失敗の直後はすぐに再試行しない'''
    f = _Fake()
    try:
        clk = _Clock()
        s, d = _sd(clock=clk, opener=f.opener)
        s.update()
        old = Path(s.gz).read_bytes()
        clk.t += 25 * 3600
        f.etag = 'W/"n1"'
        f.status = 500
        r = s.update()
        t.eq((r['did'], r['state']), ('failed', 'error'), 'HTTP 500')
        t.eq(r['error'], 'http500', 'error')
        t.eq(Path(s.gz).read_bytes(), old, '前のデータは残る')
        t.eq(s.lookup(hash=_hx(H1))['key'], '103fb', '照合にも使える')
        n = len(f.hits)
        clk.t += 60
        t.eq(s.update()['did'], 'throttled', '失敗の直後は待つ')
        t.eq(len(f.hits), n, '通信していない')
        f.status = None
        clk.t += 20 * 60
        f.body = b'garbage'
        r = s.update()
        t.eq((r['did'], r['error']), ('failed', 'broken'), '壊れたデータ')
        t.eq(Path(s.gz).read_bytes(), old, '壊れた物で置き換えない')
        clk.t += 20 * 60
        f.body = gzip.compress(_container(version=4))
        r = s.update()
        t.eq(r['state'], 'unsupported', '形式違い')
        t.eq(Path(s.gz).read_bytes(), old, '形式違いで置き換えない')
        t.eq(s.lookup(hash=_hx(H1)), None, 'unsupported の間は使わない')
        clk.t += 20 * 60
        f.body = gzip.compress(_container())
        r = s.update()
        t.eq((r['did'], r['state']), ('downloaded', 'ok'), '直れば ok に戻る')
        t.ok(not list(Path(s.dir).glob('*.tmp')), '一時ファイルが残らない')
    finally:
        f.close()


def test_update_size_limit(t):
    '''Content-Length が上限超過・長さ不明のまま上限を超えて流れる、どちらも途中で打ち切って保存しない'''
    f = _Fake()
    old_max = sd.MAX_DOWNLOAD
    try:
        sd.MAX_DOWNLOAD = 100000
        clk = _Clock()
        s, d = _sd(clock=clk, opener=f.opener)
        f.body = b'x' * 200000
        r = s.update()
        t.eq((r['did'], r['error']), ('failed', 'tooBig'), 'Content-Length 超過')
        t.ok(not Path(s.gz).exists(), '保存しない')
        clk.t += 20 * 60
        f.chunked_big = 1024 * 1024
        r = s.update()
        t.eq((r['did'], r['error']), ('failed', 'tooBig'), '長さ不明で超過')
        t.ok(not Path(s.gz).exists() and not list(Path(s.dir).glob('*.tmp')), '保存しない・一時ファイルなし')
    finally:
        sd.MAX_DOWNLOAD = old_max
        f.close()


def test_update_timeout_and_network_error(t):
    '''通信の失敗（時間切れ等）は例外にならず error になる。時間切れは固定値で渡す'''
    seen = {}

    def opener(req, timeout=None):
        seen['timeout'] = timeout
        raise TimeoutError('timed out')

    s, d = _sd(clock=_Clock(), opener=opener)
    r = s.update()
    t.eq((r['did'], r['state']), ('failed', 'error'), '失敗')
    t.eq(seen['timeout'], sd.TIMEOUT, '時間切れを渡す')
    t.ok(sd.TIMEOUT <= 20, '20秒以内')
    t.eq(s.lookup(hash=_hx(H1)), None, 'データなし')


def test_user_agent_reads_app_version(t):
    '''User-Agent の版は js/constants.js の APP_VERSION から（読めなければ版なし）'''
    ua = sd.user_agent(str(H.ROOT))
    t.ok(ua.startswith('NonLinearMapper/v') and ua.endswith('(+https://github.com/Oz-Co-two/nlm-oz-co2)'), ua)
    t.eq(sd.user_agent(tempfile.mkdtemp()), 'NonLinearMapper (+https://github.com/Oz-Co-two/nlm-oz-co2)', '読めない時')

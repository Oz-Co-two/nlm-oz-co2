# NLM開発サーバー: キャッシュ無効ヘッダ付き（Chromeの古いファイル使い回しを根絶）
# ＋ アセット(asset/)クリップの保存/改名/削除API（ローカル専用。Tauri化時はネイティブ書込みへ置換）
import hmac, http.server, json, math, os, posixpath, re, secrets, shutil, subprocess, sys, tempfile, threading, time
from urllib.parse import unquote, urlsplit, parse_qs
from rating_plugin import RatingPlugin, PluginError
from app_update import Updater, UpdateError
from media_library import MediaLibrary, LibError, RatingCache
from song_details import SongDetails
from beatsaver_api import BeatSaverLookup

# BASE_DIR = Webコンテンツの置き場（読み取り専用でよい）。exe化(PyInstaller)ではバンドル展開先を渡す。
# DATA_DIR = 書き込み対象（config/settings.json と asset/*.nlmclip）。exe化では exe と同居のユーザー書込み可フォルダを渡す。
# 環境変数が無ければ両方 NLM/ を指す＝dev の従来動作と完全に同じ。
BASE_DIR = os.environ.get('NLM_BASE_DIR') or os.path.dirname(os.path.abspath(__file__))          # NLM/
DATA_DIR = os.environ.get('NLM_DATA_DIR') or BASE_DIR
ASSET_DIR = os.path.join(DATA_DIR, 'asset')                     # 素材は NLM/asset（ヘルバ様指定 2026-07-14: ルート直下→NLM内へ移動）
ASSET_SEED_DIR = os.path.join(BASE_DIR, 'asset')               # バンドル同梱の見本クリップ（DATA_DIR に無い時のフォールバック）
CONFIG_DIR = os.path.join(DATA_DIR, 'config')
SETTINGS_FILE = os.path.join(CONFIG_DIR, 'settings.json')        # 個人の環境設定(bsnm_*)をファイル保存（localStorageの喪失対策）
LANG_DIR = os.path.join(DATA_DIR, 'lang')                       # 翻訳(lang/*.json)は exe隣を優先＝ユーザーが編集/言語追加できる
LANG_SEED_DIR = os.path.join(BASE_DIR, 'lang')                  # バンドル同梱の翻訳（exe隣に無い時のフォールバック）
OPEN_FILE = os.environ.get('NLM_OPEN_FILE') or ''              # ダブルクリックで開くファイル（app.pyが%1から設定）。ネイティブパスなので保存もここへ書き戻せる

# 本体の自動更新（app_update.py）。exe 版では DATA_DIR＝exe の隣＝差し替える配布フォルダ
UPDATER = Updater(BASE_DIR, DATA_DIR, bool(getattr(sys, 'frozen', False)))

# MEDIA ライブラリ（2026-10-12）。記録したフォルダ（config/library.json）は exe 版のフォルダ選択ダイアログ（app.py の
# Api.lib_pick_folder）からだけ増える。JS から受け取るのは記録の id と、その中の相対パス・ファイル名だけ（media_library.py）。
# 全曲データ（song_details.py・jsDelivr）と BeatSaver（beatsaver_api.py）の取得先 URL はそれぞれのファイルに固定。
# NLM_PLAYDATA はプレイ記録の既定の場所の差し替え（テスト用。利用者の本物の記録を読まないように）
# NLM_NO_NET=1 はネットへ出ない（自動テスト用。画面は記録したライブラリを読むと全曲データの取得を頼むため、テストのサーバーが
# 毎回 jsDelivr から約10MB を取りに行かないように。全曲データ・BeatSaver の取得は「通信の失敗」として扱われる）
def _no_net(*a, **k):
    import urllib.error
    raise urllib.error.URLError('NLM_NO_NET')
_NET = None if os.environ.get('NLM_NO_NET') != '1' else _no_net
LIBRARY = MediaLibrary(DATA_DIR, default_playdata=os.environ.get('NLM_PLAYDATA') or None)
SONG_DETAILS = SongDetails(DATA_DIR, app_root=BASE_DIR, opener=_NET)
BEATSAVER = BeatSaverLookup(DATA_DIR, app_root=BASE_DIR, opener=_NET)
RATING_CACHE = RatingCache(DATA_DIR)

def _safe(name):
    # ファイル名を安全化（パストラバーサル・不正文字の除去）。ディレクトリ部は捨てる
    name = os.path.basename(str(name or ''))
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', name).strip().strip('.')
    return name or 'clip'

# ---- アクセス制御（2026-09-28） ----
# 待ち受けは127.0.0.1のみだが、それだけでは「普段のブラウザで開いた悪意あるサイトが127.0.0.1へ要求を送る」
# 攻撃（CSRF）と、DNSリバインディング（攻撃者のドメイン名を127.0.0.1へ向け直して読み書きする）を防げない。
#  ① Hostヘッダーがローカルの名前でなければ拒否（DNSリバインディング対策）
#  ② 書き込み系(POST)は独自ヘッダー X-NLM-Request 必須。他サイトからこのヘッダー付きで送るにはブラウザの
#     事前確認(CORSプリフライト)が必要で、ここはそれを許可しないため送れない（アプリ自身の通信は同一オリジンなので影響なし）
#  ③ Originヘッダーが付いていて他サイトのものなら拒否（念のための二重化）
# Docker/WSLのポート転送やリバースプロキシで別名アクセスする場合は、環境変数 NLM_ALLOWED_HOSTS に
# カンマ区切りでホスト名を追加する（例: NLM_ALLOWED_HOSTS=nlm.local,192.168.0.10）。
ALLOWED_HOSTS = {'127.0.0.1', 'localhost', '::1'} | {
    h.strip().lower() for h in (os.environ.get('NLM_ALLOWED_HOSTS') or '').split(',') if h.strip()}

# ---- 合言葉（2026-10-11・セキュリティ点検 2026-10-10 の F8） ----
# 上の①〜③はブラウザ経由の攻撃への対策で、ブラウザ以外のプログラムから直接送られると全部通る（固定の値なので誰でも付けられる）。
# 同じPCの別アカウントや、ポート転送で届く LAN の他の機器から API を使われないよう、起動ごとの合言葉を X-NLM-Token ヘッダーで求める。
#  - 画面へは URL の #k=… で渡す（access_url。# 以降はサーバーへも Referer にも送られない）。JS は settings-mirror.js が
#    同じオリジンへの fetch/XHR に自動で付ける。
#  - Cookie では渡さない: 127.0.0.1 の Cookie はポートを区別しないため、別ポートに立てられたページへも送られて盗まれる。
#  - 合言葉なしで返すのは PUBLIC_* の静的ファイル（<script src>・<link>・<img>・import() はヘッダーを付けられない）だけ。
#    守る場所を列挙すると取りこぼす（asset/ 内のジャンクションで抜けられた）ので、返してよい物だけを列挙する。
SESSION_TOKEN = secrets.token_urlsafe(32)
PUBLIC_FILES = {'editor.html'}
PUBLIC_DIRS = {'js', 'css', 'icons', 'fonts', 'preview-v4'}


def access_url(port, host='127.0.0.1'):
    """合言葉付きの、エディタを開く URL"""
    return 'http://%s:%d/editor.html#k=%s' % (host, port, SESSION_TOKEN)


def _url_parts(path):
    """URL のパスを translate_path と同じ手順で要素に分ける（? # を落とし、%xx を戻して .. を畳む）"""
    rel = posixpath.normpath(unquote(path.split('?', 1)[0].split('#', 1)[0]))
    return [p for p in rel.split('/') if p and p != '.']


def _is_public(path):
    """合言葉なしで返してよい静的ファイルか。名前の完全一致だけで判定する（大文字小文字のみ同一視）。
    8.3 形式の短い名前・末尾の点などの別名は一致しない＝合言葉が要る側に倒れる"""
    parts = [p.lower() for p in _url_parts(path)]
    if not parts:
        return False
    if len(parts) == 1:
        return parts[0] in PUBLIC_FILES
    return parts[0] in PUBLIC_DIRS

def _hostname(hostport):
    """'127.0.0.1:8138' / '[::1]:8138' / 'localhost' → ホスト名部分（小文字）"""
    hp = (hostport or '').strip().lower()
    if hp.startswith('['):
        return hp[1:hp.find(']')] if ']' in hp else hp[1:]
    return hp.rsplit(':', 1)[0] if hp.count(':') == 1 else hp

_settings_lock = threading.Lock()   # config/settings.json の保存と配信を交互にする（書きかけを読ませない）


def _write_text_atomic(path, text):
    """一時ファイルに書き終えてから置き換える＝読み手が書きかけ（空・途中まで）を見ない・途中で落ちても前の中身が残る（2026-10-09）。
    以前は空にしてから書いていたため、保存と同時の読み込みが空のファイルを受け取ることがあった。
    Windows では置き換え先を他が開いていると失敗する（ウイルス対策ソフト・起動時に言語を読む app.py 等）ので少し待ってやり直す"""
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


class NoCacheHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=BASE_DIR, **kwargs)

    def _access_ok(self, write=False):
        if _hostname(self.headers.get('Host')) not in ALLOWED_HOSTS:
            return False
        origin = self.headers.get('Origin')
        if origin and origin != 'null' and _hostname(urlsplit(origin).netloc) not in ALLOWED_HOSTS:
            return False
        if write and self.headers.get('X-NLM-Request') != '1':
            return False
        if write or not _is_public(self.path):   # 合言葉（SESSION_TOKEN の説明）
            given = (self.headers.get('X-NLM-Token') or '').encode('utf-8', 'replace')
            return hmac.compare_digest(given, SESSION_TOKEN.encode('ascii'))
        return True

    def _deny(self):
        self._drain()   # 拒否する時も本体を読み捨ててから応答する（_drain の説明）
        self.send_error(403, 'Forbidden (NLM local server: this host/origin is not allowed, or the access key is missing.'
                             ' Open the URL shown when the server started.)')

    def translate_path(self, path):
        parts = _url_parts(path)
        # Windowsでは '\' やドライブ名('C:')もパス区切りとして効くため、1要素でもそれを含めば配信しない。
        # （例: /C:%5CWindows%5Cwin.ini がフォルダ外の実ファイルを返していた。元のSimpleHTTPRequestHandlerが
        #   持っていたこの検査を独自実装で落としていた。セキュリティ点検 2026-09-28）
        if any(p == '..' or '\\' in p or ':' in p or os.path.splitdrive(p)[0] for p in parts):
            return os.path.join(BASE_DIR, '__forbidden__')   # 存在しないパス＝404
        # /asset/* は DATA_DIR/asset/ へ。無ければバンドル同梱の見本(ASSET_SEED_DIR)へフォールバック。
        if parts and parts[0] == 'asset':
            sub = os.path.join(ASSET_DIR, *parts[1:]) if len(parts) > 1 else ASSET_DIR
            sub = os.path.normpath(sub)
            if len(parts) > 1 and not os.path.exists(sub):
                seed = os.path.normpath(os.path.join(ASSET_SEED_DIR, *parts[1:]))
                if os.path.exists(seed):
                    return seed
            return sub
        # config/settings.json は書込み先(DATA_DIR)を優先。無ければ「初期値(settings.default.json)」へ
        # フォールバックする＝配布版に個人設定を持ち込まない（新規環境は必ず初期状態で始まる）。
        # （個人設定 settings.json はバンドルしない。dev では DATA_DIR に実ファイルがあるので live が使われる）
        if len(parts) == 2 and parts[0] == 'config' and parts[1] == 'settings.json':
            live = os.path.join(CONFIG_DIR, 'settings.json')
            if os.path.exists(live):
                return live
            return os.path.join(BASE_DIR, 'config', 'settings.default.json')
        # /lang/* は exe隣(DATA_DIR/lang)を優先し、無ければ同梱(BASE_DIR/lang)へフォールバック。
        if parts and parts[0] == 'lang':
            sub = os.path.normpath(os.path.join(LANG_DIR, *parts[1:])) if len(parts) > 1 else LANG_DIR
            if len(parts) > 1 and not os.path.exists(sub):
                seed = os.path.normpath(os.path.join(LANG_SEED_DIR, *parts[1:]))
                if os.path.exists(seed):
                    return seed
            return sub
        return os.path.join(self.directory, *parts) if parts else self.directory

    def do_HEAD(self):
        if not self._access_ok():
            return self._deny()
        return super().do_HEAD()

    def do_GET(self):
        if not self._access_ok():
            return self._deny()
        # ダブルクリックで開くファイルの取得（起動時にフロントが読み、そのプロジェクトを開く）
        if self.path.split('?', 1)[0] == '/__openarg':
            ok = bool(OPEN_FILE) and os.path.isfile(OPEN_FILE)
            obj = {'ok': ok}
            if ok:
                try:
                    with open(OPEN_FILE, 'r', encoding='utf-8') as f:
                        obj['text'] = f.read()
                    obj['name'] = os.path.basename(OPEN_FILE)
                    obj['path'] = OPEN_FILE
                except Exception as e:
                    obj = {'ok': False, 'error': str(e)}
            return self._reply(200, obj)
        # 翻訳は「同梱版を土台に exe隣の版で上書き」してキー単位で合成して返す。
        # exe隣の lang/ は初回にシードされた後は更新されない（ユーザー編集を守るため）ので、
        # 丸ごと差し替えだと旧版の lang/ を持つ利用者には新機能の訳が欠ける（アップデート時の互換対策 2026-09-27）。
        lp = unquote(self.path.split('?', 1)[0])
        m = re.fullmatch(r'/lang/([A-Za-z0-9_-]+\.json)', lp)
        if m:
            merged, found = {}, False
            for d in (LANG_SEED_DIR, LANG_DIR):   # 後勝ち＝ユーザー側の訳が優先
                p = os.path.join(d, m.group(1))
                if os.path.isfile(p):
                    try:
                        with open(p, 'r', encoding='utf-8') as f:
                            merged.update(json.load(f)); found = True
                    except Exception:
                        pass   # 壊れたファイルは無視して他方を使う
            if found:
                return self._reply(200, merged)
        if lp == '/config/settings.json':   # 保存（__settings/save）と同じ鍵の中で読む＝保存の途中を返さない
            with _settings_lock:
                return super().do_GET()
        return super().do_GET()

    def list_directory(self, path):
        # フォルダ一覧はアセット(asset/)の走査にだけ使う。それ以外（アプリ本体のフォルダ等）は見せない
        p = os.path.normcase(os.path.abspath(path))
        for root in (ASSET_DIR, ASSET_SEED_DIR):
            r = os.path.normcase(os.path.abspath(root))
            if p == r or p.startswith(r + os.sep):
                return super().list_directory(path)
        self.send_error(404, 'File not found')
        return None

    def end_headers(self):
        self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
        self.send_header('Pragma', 'no-cache')
        self.send_header('Expires', '0')
        super().end_headers()

    def log_message(self, *a):   # 静かに
        pass

    _DRAIN_MAX = 16 * 1024 * 1024   # 使わない本体を読み捨てる上限（これより大きい本体は読まない＝接続がリセットされても構わない不正な要求）

    def _content_length(self):
        if self.command != 'POST':
            return 0
        try:
            return max(0, int(self.headers.get('Content-Length', 0) or 0))
        except ValueError:
            return 0   # 数値でない Content-Length は本体なしとして扱う（例外にすると応答が返らない）

    def _raw_body(self):
        # POSTの本体は1回だけ読む（_body も同じものを使う）
        if getattr(self, '_raw', None) is None:
            n = self._content_length()
            self._raw = self.rfile.read(n) if n > 0 else b''
        return self._raw

    def _drain(self):
        # 応答する前に、まだ読んでいない本体を読み捨てる（_reply・_deny から呼ぶ）。読まずに応答して閉じると、Windows では残った
        # データのせいで接続がリセットされ、応答が届かずに通信エラーになることがある（本体が大きいほど起きやすい。小さい本体でも
        # まれに起き、全テストで __update/status がたまに ConnectionAbortedError になっていた）。拒否する要求（他サイトから送られた物）
        # に大きなメモリを使わせないよう、保存せずに少しずつ読み、上限を超える本体・届かない本体は諦める
        if getattr(self, '_raw', None) is not None:
            return
        n, self._raw = self._content_length(), b''
        if not 0 < n <= self._DRAIN_MAX:
            return
        try:
            self.connection.settimeout(2)
            while n > 0:
                d = self.rfile.read(min(n, 65536))
                if not d:
                    break
                n -= len(d)
        except OSError:
            pass

    def _body(self):
        return json.loads(self._raw_body() or b'{}')

    def _reply(self, code, obj):
        self._drain()
        body = json.dumps(obj, ensure_ascii=False).encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _convert_to_ogg(self):
        # 本体（音源）はエラーを返す時も先に読み切る（_drain の説明。数MBの音源を送るため特に起きやすかった）
        raw = self._raw_body()
        ffmpeg = shutil.which('ffmpeg')
        if not ffmpeg:
            return self._reply(200, {'ok': False, 'error': 'ffmpeg-not-found'})
        qs = parse_qs(urlsplit(self.path).query)
        ext = re.sub(r'[^a-z0-9]', '', (qs.get('ext', ['bin'])[0] or 'bin').lower()) or 'bin'
        try:
            lead_in_ms = max(0, int(float(qs.get('leadInMs', ['0'])[0] or '0')))
        except (TypeError, ValueError):
            lead_in_ms = 0
        # segs: Musicの配置（分割・トリム）の切り貼り表 [[元の音源の開始秒, 終了秒, 書き出し先の開始秒], …]（editor-app.js の eggPieces）
        segs = None
        if 'segs' in qs:
            try:
                v = json.loads(qs['segs'][0])
                if not isinstance(v, list) or not (0 < len(v) <= 1000):
                    raise ValueError
                segs = []
                for it in v:
                    a, b, at = (float(x) for x in it)
                    if not all(math.isfinite(x) and 0 <= x < 86400 for x in (a, b, at)) or b <= a:
                        raise ValueError
                    segs.append((a, b, at))
            except (TypeError, ValueError):
                return self._reply(200, {'ok': False, 'error': 'bad-segs'})
        # gainDb: 曲の音量補正（dB・editor-app.js の setSongGainDb。画面の範囲は ±20）。0 なら何もしない
        gain_db = 0.0
        if 'gainDb' in qs:
            try:
                gain_db = float(qs['gainDb'][0])
                if not (math.isfinite(gain_db) and -40 <= gain_db <= 40):
                    raise ValueError
            except (TypeError, ValueError):
                return self._reply(200, {'ok': False, 'error': 'bad-gain'})
        vol = 'volume=%.2fdB' % gain_db if abs(gain_db) >= 0.005 else ''
        try:
            with tempfile.TemporaryDirectory() as td:
                src = os.path.join(td, 'in.' + ext)
                dst = os.path.join(td, 'out.ogg')
                with open(src, 'wb') as f:
                    f.write(raw)
                cmd = [ffmpeg, '-y', '-i', src, '-vn']
                if segs:   # 区間ごとに切り出し（atrim）→書き出し先の位置へずらし（adelay）→重ねる（amix・音量はそのまま）
                    parts = ['[0:a]atrim=start=%.6f:end=%.6f,asetpts=PTS-STARTPTS,adelay=%d:all=1[p%d]' % (a, b, round(at * 1000), i)
                             for i, (a, b, at) in enumerate(segs)]
                    if len(segs) == 1:
                        out = '[p0]'
                    else:
                        parts.append(''.join('[p%d]' % i for i in range(len(segs)))
                                     + 'amix=inputs=%d:normalize=0:dropout_transition=0[out]' % len(segs))
                        out = '[out]'
                    if vol:   # 並べ終えた後で音量を変える
                        parts.append(out + vol + '[vol]')
                        out = '[vol]'
                    cmd += ['-filter_complex', ';'.join(parts), '-map', out]
                else:
                    # 曲頭に無音を追加(ms)＝実際の音声データを前にずらす（Info.dat側の指定に頼らず確実に効かせる）
                    af = (['adelay=%d:all=true' % lead_in_ms] if lead_in_ms > 0 else []) + ([vol] if vol else [])
                    if af:
                        cmd += ['-af', ','.join(af)]
                cmd += ['-c:a', 'libvorbis', '-q:a', '5', dst]
                # creationflags=CREATE_NO_WINDOW: 親(exe)にコンソールが無くてもffmpeg単体がコンソール窓を
                # 一瞬出してしまう(Windowsの既定動作)のを防ぐ
                r = subprocess.run(cmd, capture_output=True, timeout=300,
                                    creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
                if r.returncode != 0 or not os.path.isfile(dst):
                    err = (r.stderr or b'').decode('utf-8', 'ignore')[-800:]
                    return self._reply(200, {'ok': False, 'error': 'ffmpeg-failed: ' + err})
                with open(dst, 'rb') as f:
                    ogg = f.read()
        except Exception as e:
            return self._reply(200, {'ok': False, 'error': str(e)})
        self.send_response(200)
        self.send_header('Content-Type', 'audio/ogg')
        self.send_header('Content-Length', str(len(ogg)))
        self.end_headers()
        self.wfile.write(ogg)

    def _rating(self):
        # 取得先URL・置き場所は rating_plugin.py に固定。JSから受け取るのは「使う版」と譜面の中身だけ
        rp = RatingPlugin(DATA_DIR)
        act = self.path[len('/__rating/'):]
        try:
            if act == 'status':
                return self._reply(200, rp.status())
            if act == 'check':
                return self._reply(200, rp.check())
            if act == 'install':
                return self._reply(200, rp.install())
            if act == 'use':
                return self._reply(200, rp.use(self._body().get('version')))
            if act == 'measure':
                return self._reply(200, rp.measure(self._body()))
        except PluginError as e:
            return self._reply(200, {'ok': False, 'error': e.code, 'detail': e.detail})
        return self._reply(404, {'ok': False, 'error': 'unknown endpoint'})

    def _update(self):
        # 取得先URL・差し替える物は app_update.py に固定。JSから受け取るのは言語（と更新内容を開く版番号）だけ
        act = self.path[len('/__update/'):]
        try:
            if act == 'status':
                return self._reply(200, UPDATER.status())
            if act == 'check':
                return self._reply(200, UPDATER.check())
            if act == 'download':
                return self._reply(200, UPDATER.start_download())
            if act == 'progress':
                return self._reply(200, UPDATER.progress())
            if act == 'cancel':
                return self._reply(200, UPDATER.cancel())
            if act == 'apply':
                return self._reply(200, UPDATER.apply(self._body().get('lang')))
            if act == 'openNotes':
                b = self._body()
                return self._reply(200, UPDATER.open_notes(b.get('lang'), b.get('version')))
            if act == 'openReleases':
                return self._reply(200, UPDATER.open_releases())
        except UpdateError as e:
            return self._reply(200, {'ok': False, 'error': e.code, 'detail': e.detail})
        return self._reply(404, {'ok': False, 'error': 'unknown endpoint'})

    def _reply_bytes(self, data, ctype):
        self._drain()
        self.send_response(200)
        self.send_header('Content-Type', ctype)
        self.send_header('X-NLM-File', '1')   # ファイルの中身（失敗の {ok:false} と見分ける。.dat も application/json のため）
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    @staticmethod
    def _lib_net(m, use_dump):
        """1曲の「ネットの情報」（取り決めの Extra の net）。版が一致する（ハッシュで当たった）物を優先し、全曲データ＞BeatSaver の記録の順。
        どちらにも無ければ {'src':'none'}（画面に🔍を出す）。BeatSaver にも無かった曲は bsMissAt 付き"""
        h, k = m.get('hash'), m.get('key')
        dump = SONG_DETAILS.lookup(hash=h, key=k) if use_dump else None
        bs = BEATSAVER.cached(h) if h else None
        cands = [x for x in (dump, bs) if isinstance(x, dict) and x.get('src') in ('dump', 'beatsaver')]
        for x in cands:
            if x.get('match') == 'hash':
                return x
        if cands:
            return cands[0]
        if isinstance(bs, dict) and bs.get('bsMissAt'):
            return {'src': 'none', 'bsMissAt': bs['bsMissAt']}
        return {'src': 'none'}

    def _lib(self):
        # MEDIA ライブラリ（media_library.py・song_details.py・beatsaver_api.py）。JS から受け取るのは記録の id・相対パス・ファイル名・
        # 同時に計算する数・全曲データを使うか、だけ。フォルダを増やす口は無い（exe 版のダイアログ＝app.py の Api.lib_pick_folder だけ）
        act = self.path[len('/__lib/'):]
        b = self._body()
        b = b if isinstance(b, dict) else {}
        sv = lambda k: b.get(k) if isinstance(b.get(k), str) else ''
        lid, rel = sv('id'), sv('rel')
        use_dump = b.get('net') is not False
        try:
            if act == 'list':
                return self._reply(200, {'ok': True, 'libs': LIBRARY.list(), 'details': SONG_DETAILS.status(),
                                         'playdata': LIBRARY.playdata_status()})
            if act == 'scan':
                return self._reply(200, LIBRARY.scan(lid, b.get('from') or 0))
            if act == 'rescan':
                return self._reply(200, LIBRARY.rescan(lid))
            if act == 'remove':
                return self._reply(200, LIBRARY.remove(lid))
            if act == 'open':
                return self._reply(200, LIBRARY.open_folder(lid, rel))
            if act == 'file':
                data, ctype = LIBRARY.read_file(lid, rel, sv('name'))
                return self._reply_bytes(data, ctype)
            if act == 'extra':
                maps = LIBRARY.scan(lid, 0)['maps']
                plays = LIBRARY.play_all(lid)
                cur = RatingPlugin(DATA_DIR).current()
                ver = cur['version'] if cur else None
                out = {}
                for m in maps:
                    e = {'net': self._lib_net(m, use_dump)}
                    if m['rel'] in plays:
                        e['play'] = plays[m['rel']]
                    est = RATING_CACHE.get(m.get('hash'), ver) if ver else None
                    if est:
                        e['est'] = {'version': ver, 'diffs': est}
                    out[m['rel']] = e
                return self._reply(200, {'ok': True, 'extra': out})
            if act == 'details':   # 全曲データ。update は JS が環境設定 ON の時だけ呼ぶ（1日1回の決まりは song_details.py が守る）
                return self._reply(200, SONG_DETAILS.update() if sv('act') == 'update' else SONG_DETAILS.status())
            if act == 'beatsaver':   # 利用者が🔍を押して確認した1曲だけ（確認は JS が取る）
                m = LIBRARY.get_map(lid, rel)
                if not m or not m.get('hash'):
                    return self._reply(200, {'ok': False, 'error': 'not-found'})
                r = BEATSAVER.lookup(m['hash'])
                if 'error' in r:
                    return self._reply(200, {'ok': False, **r})
                return self._reply(200, {'ok': True, 'net': self._lib_net(m, use_dump)})
            if act == 'rate':   # NLM推定の★（nlm-rating）。同時に動かす数は rating_plugin が 1〜CPU数に丸める
                m = LIBRARY.get_map(lid, rel)
                if not m or not m.get('hash'):
                    return self._reply(200, {'ok': False, 'error': 'not-found'})
                rp = RatingPlugin(DATA_DIR)
                cur = rp.current()
                if not cur:
                    return self._reply(200, {'ok': False, 'error': 'notInstalled'})
                hit = RATING_CACHE.get(m['hash'], cur['version'])
                if hit is None:
                    try:
                        par = int(b.get('parallel') or 1)
                    except (TypeError, ValueError):
                        par = 1
                    res = rp.measure({'files': LIBRARY.rating_input(lid, rel), 'modifiers': ['none']}, par)
                    hit = RatingCache.from_plugin(res.get('results'))
                    RATING_CACHE.put(m['hash'], cur['version'], hit)
                return self._reply(200, {'ok': True, 'est': {'version': cur['version'], 'diffs': hit}})
            if act == 'playdata':
                return self._reply(200, LIBRARY.reset_playdata() if sv('act') == 'reset' else LIBRARY.playdata_status())
        except LibError as e:
            return self._reply(200, {'ok': False, 'error': e.code})
        except PluginError as e:
            return self._reply(200, {'ok': False, 'error': e.code, 'detail': e.detail})
        return self._reply(404, {'ok': False, 'error': 'unknown endpoint'})

    def do_POST(self):
        self._raw = None   # 本体の読み込みは要求ごと（_raw_body）
        if not self._access_ok(write=True):
            return self._deny()
        try:
            if self.path == '/__settings/save':   # 環境設定(bsnm_*)を config/settings.json へ保存
                b = self._body()
                os.makedirs(CONFIG_DIR, exist_ok=True)
                with _settings_lock:
                    _write_text_atomic(SETTINGS_FILE, json.dumps(b.get('data', {}), ensure_ascii=False, indent=1))
                return self._reply(200, {'ok': True})
            if self.path == '/__openarg/save':   # ダブルクリックで開いたファイルへ保存を書き戻す（同じ.nlmfへ上書き）
                if not OPEN_FILE:
                    return self._reply(400, {'ok': False, 'error': 'no open file'})
                b = self._body()
                # 上書き前に1世代バックアップ（事故保険）
                try:
                    if os.path.isfile(OPEN_FILE):
                        with open(OPEN_FILE, 'r', encoding='utf-8') as f:
                            old = f.read()
                        with open(OPEN_FILE + '.bak', 'w', encoding='utf-8') as f:
                            f.write(old)
                except Exception:
                    pass
                with open(OPEN_FILE, 'w', encoding='utf-8') as f:
                    f.write(b.get('text', ''))
                return self._reply(200, {'ok': True, 'name': os.path.basename(OPEN_FILE)})
            if self.path.split('?', 1)[0] == '/__convert/toOgg':   # 書き出し時: OGG以外の音源をsong.egg用にOGG Vorbisへ変換（ffmpeg利用・無ければエラー返却）
                return self._convert_to_ogg()
            if self.path.startswith('/__update/'):   # 本体の自動更新。詳細は app_update.py
                return self._update()
            if self.path.startswith('/__rating/'):   # 難易度を測る（BeatLeaderの星の近似）プラグイン。詳細は rating_plugin.py
                return self._rating()
            if self.path.startswith('/__lib/'):   # MEDIA ライブラリ。詳細は _lib
                return self._lib()
            os.makedirs(ASSET_DIR, exist_ok=True)
            if self.path == '/__asset/save':
                b = self._body()
                name = _safe(b.get('name', 'clip'))
                if not name.lower().endswith('.nlmclip'):
                    name += '.nlmclip'
                # 同名が既存なら連番付与＝既存クリップを黙って上書きしない（監査 2026-07-14）
                if os.path.exists(os.path.join(ASSET_DIR, name)):
                    base = re.sub(r'\.nlmclip$', '', name, flags=re.I)
                    i = 2
                    while os.path.exists(os.path.join(ASSET_DIR, '%s (%d).nlmclip' % (base, i))):
                        i += 1
                    name = '%s (%d).nlmclip' % (base, i)
                with open(os.path.join(ASSET_DIR, name), 'w', encoding='utf-8') as f:
                    json.dump(b.get('data', {}), f, ensure_ascii=False)
                return self._reply(200, {'ok': True, 'name': name})
            if self.path == '/__asset/rename':
                b = self._body()
                src = _safe(b.get('from', ''))
                newlabel = str(b.get('to', '')).strip()
                dst = _safe(newlabel)
                if not dst.lower().endswith('.nlmclip'):
                    dst += '.nlmclip'
                sp = os.path.join(ASSET_DIR, src)
                dp = os.path.join(ASSET_DIR, dst)
                # 別クリップと同名になる改名は拒否＝黙って潰さない（監査 2026-07-14）
                if os.path.abspath(sp) != os.path.abspath(dp) and os.path.exists(dp):
                    return self._reply(200, {'ok': False, 'error': 'exists'})   # 文言はJS側で訳す（msg.assetNameExists）
                if os.path.isfile(sp):
                    try:
                        with open(sp, 'r', encoding='utf-8') as f:
                            data = json.load(f)
                        data['name'] = re.sub(r'\.nlmclip$', '', newlabel, flags=re.I)
                        with open(dp, 'w', encoding='utf-8') as f:
                            json.dump(data, f, ensure_ascii=False)
                        if os.path.abspath(sp) != os.path.abspath(dp):
                            os.remove(sp)
                    except Exception:
                        os.replace(sp, dp)
                return self._reply(200, {'ok': True, 'name': dst})
            if self.path == '/__asset/delete':
                b = self._body()
                p = os.path.join(ASSET_DIR, _safe(b.get('name', '')))
                if os.path.isfile(p):
                    os.remove(p)
                return self._reply(200, {'ok': True})
            return self._reply(404, {'ok': False, 'error': 'unknown endpoint'})
        except Exception as e:
            return self._reply(500, {'ok': False, 'error': str(e)})

def make_server(port=8138, bind='127.0.0.1'):
    # ランチャー(app.py)から呼ぶ用。BASE_DIR/DATA_DIR は環境変数で差し替え済み。
    # NoCacheHandler は __init__ 内で directory=BASE_DIR を自前指定するため、ここでは渡さない。
    os.makedirs(CONFIG_DIR, exist_ok=True)
    os.makedirs(ASSET_DIR, exist_ok=True)
    return http.server.ThreadingHTTPServer((bind, port), NoCacheHandler)

if __name__ == '__main__':
    os.chdir(BASE_DIR)
    port = next((int(a.split('=', 1)[1]) for a in sys.argv[1:] if a.startswith('--port=')), 8138)
    httpd = make_server(port=port)
    url = access_url(port)
    # 表示は英語(ASCII)だけ: 日本語は、日本語を表せない文字コードの環境で出力をファイルへ回すと変換に失敗して起動前に落ちる
    print('NLM local server is running. Open this URL in Chrome / Edge'
          ' (it contains an access key that changes every time the server starts):', flush=True)
    print('  ' + url, flush=True)
    print('Press Ctrl+C to stop.', flush=True)
    if '--no-browser' not in sys.argv:   # 合言葉付きの URL を既定のブラウザで開く（開けなくても上の URL を開けばよい）
        try:
            import webbrowser
            webbrowser.open(url)
        except Exception:
            pass
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()

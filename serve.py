# NLM開発サーバー: キャッシュ無効ヘッダ付き（Chromeの古いファイル使い回しを根絶）
# ＋ アセット(asset/)クリップの保存/改名/削除API（ローカル専用。Tauri化時はネイティブ書込みへ置換）
import http.server, json, math, os, posixpath, re, shutil, subprocess, sys, tempfile, threading, time
from urllib.parse import unquote, urlsplit, parse_qs
from rating_plugin import RatingPlugin, PluginError
from app_update import Updater, UpdateError

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
        return True

    def _deny(self):
        self._drain()   # 拒否する時も本体を読み捨ててから応答する（_drain の説明）
        self.send_error(403, 'Forbidden (NLM local server: access from this host/origin is not allowed)')

    def translate_path(self, path):
        path = path.split('?', 1)[0].split('#', 1)[0]
        rel = posixpath.normpath(unquote(path))
        parts = [p for p in rel.split('/') if p and p != '.']
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
                    cmd += ['-filter_complex', ';'.join(parts), '-map', out]
                elif lead_in_ms > 0:   # 曲頭に無音を追加(ms)＝実際の音声データを前にずらす（Info.dat側の指定に頼らず確実に効かせる）
                    cmd += ['-af', 'adelay=%d:all=true' % lead_in_ms]
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
    http.server.test(HandlerClass=NoCacheHandler, port=8138, bind='127.0.0.1')

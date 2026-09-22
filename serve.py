# NLM開発サーバー: キャッシュ無効ヘッダ付き（Chromeの古いファイル使い回しを根絶）
# ＋ アセット(asset/)クリップの保存/改名/削除API（ローカル専用。Tauri化時はネイティブ書込みへ置換）
import http.server, json, os, posixpath, re, base64, shutil, subprocess, tempfile
from urllib.parse import unquote, urlsplit, parse_qs

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
SHOTS_DIR = os.path.join(os.path.dirname(BASE_DIR), 'WEB', 'assets', 'shots')   # マニュアル用スクショ保存先（ローカル開発専用）

def _safe(name):
    # ファイル名を安全化（パストラバーサル・不正文字の除去）。ディレクトリ部は捨てる
    name = os.path.basename(str(name or ''))
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', name).strip().strip('.')
    return name or 'clip'

class NoCacheHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=BASE_DIR, **kwargs)

    def translate_path(self, path):
        path = path.split('?', 1)[0].split('#', 1)[0]
        rel = posixpath.normpath(unquote(path))
        parts = [p for p in rel.split('/') if p and p != '.']
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

    def do_GET(self):
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
        return super().do_GET()

    def end_headers(self):
        self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
        self.send_header('Pragma', 'no-cache')
        self.send_header('Expires', '0')
        super().end_headers()

    def log_message(self, *a):   # 静かに
        pass

    def _body(self):
        n = int(self.headers.get('Content-Length', 0) or 0)
        return json.loads(self.rfile.read(n) or b'{}')

    def _reply(self, code, obj):
        body = json.dumps(obj, ensure_ascii=False).encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _convert_to_ogg(self):
        ffmpeg = shutil.which('ffmpeg')
        if not ffmpeg:
            return self._reply(200, {'ok': False, 'error': 'ffmpeg-not-found'})
        qs = parse_qs(urlsplit(self.path).query)
        ext = re.sub(r'[^a-z0-9]', '', (qs.get('ext', ['bin'])[0] or 'bin').lower()) or 'bin'
        try:
            lead_in_ms = max(0, int(float(qs.get('leadInMs', ['0'])[0] or '0')))
        except (TypeError, ValueError):
            lead_in_ms = 0
        n = int(self.headers.get('Content-Length', 0) or 0)
        raw = self.rfile.read(n)
        try:
            with tempfile.TemporaryDirectory() as td:
                src = os.path.join(td, 'in.' + ext)
                dst = os.path.join(td, 'out.ogg')
                with open(src, 'wb') as f:
                    f.write(raw)
                cmd = [ffmpeg, '-y', '-i', src, '-vn']
                if lead_in_ms > 0:   # 曲頭に無音を追加(ms)＝実際の音声データを前にずらす（Info.dat側の指定に頼らず確実に効かせる）
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

    def do_POST(self):
        try:
            if self.path == '/__settings/save':   # 環境設定(bsnm_*)を config/settings.json へ保存
                b = self._body()
                os.makedirs(CONFIG_DIR, exist_ok=True)
                with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
                    json.dump(b.get('data', {}), f, ensure_ascii=False, indent=1)
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
            if self.path == '/__shot/save':   # マニュアル用スクショを WEB/assets/shots/ へ保存（ローカル開発専用）
                b = self._body()
                name = _safe(b.get('name', 'shot'))
                if not name.lower().endswith('.png'):
                    name += '.png'
                m = re.match(r'^data:image/\w+;base64,(.+)$', b.get('data', ''), re.S)
                if not m:
                    return self._reply(400, {'ok': False, 'error': 'bad data url'})
                os.makedirs(SHOTS_DIR, exist_ok=True)
                with open(os.path.join(SHOTS_DIR, name), 'wb') as f:
                    f.write(base64.b64decode(m.group(1)))
                return self._reply(200, {'ok': True, 'name': name})
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
                    return self._reply(200, {'ok': False, 'error': '同名のクリップが既にあります'})
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

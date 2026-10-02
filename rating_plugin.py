# 難易度を測る（BeatLeader の星の近似）プラグイン nlm-rating の取り込み・更新・実行（2026-10-02）
#
# プラグインは NLM 本体に同梱しない別配布（https://github.com/Oz-Co-two/nlm-rating ・ MIT）。
# 必要な人だけが画面の「取り込む」ボタンで GitHub Releases から取得する。中身は .NET の自己完結 exe で、
# 1 回の測定ごとに起動し、標準入力に譜面の JSON を渡して標準出力の JSON を受け取る（常駐・ポートなし）。
#
# 置き場所: <DATA_DIR>/plugins/rating/<版>/（exe 隣＝asset/・config/ と同じユーザーデータ扱い。旧版は残す）
#           <DATA_DIR>/plugins/rating/current.json に使う版を記録（旧版へ戻せる）
# 安全のための約束:
#  - 取得先 URL はここに固定。JS から URL・パス・版以外の値を受け取らない（版も「取り込み済みの一覧」と照合する）
#  - zip は manifest.json の SHA-256・サイズと照合してから展開し、展開時にフォルダ外へ出る名前を拒否する
#  - 通信は利用者がボタンを押した時だけ（自動確認はしない）
#  - 署名なし exe の実行になるので、取得先固定＋ハッシュ照合は外さないこと
import hashlib, json, os, re, shutil, subprocess, threading, urllib.error, urllib.request, zipfile

REPO = 'Oz-Co-two/nlm-rating'
MANIFEST_URL = f'https://github.com/{REPO}/releases/latest/download/manifest.json'
ZIP_URL = f'https://github.com/{REPO}/releases/download/v{{ver}}/{{name}}'
PROTOCOL = 1                 # NLM が話せるプラグインとの通信仕様の版（plugin 側 Program.Protocol と同じ値）
PLATFORM = 'win-x64'
MAX_ZIP = 200 * 1024 * 1024  # 取得する zip の上限（実物は約 19MB）
MAX_UNZIP = 400 * 1024 * 1024
MAX_INPUT = 64 * 1024 * 1024 # 測定に渡す譜面 JSON の合計の上限
RUN_TIMEOUT = 300            # 測定 1 回の上限秒（重い譜面・全難易度・速度違い 4 種でも数秒）
_VER_RE = re.compile(r'\d{1,4}\.\d{1,4}\.\d{1,4}')
_DAT_RE = re.compile(r'[A-Za-z0-9_\- ]{1,64}\.dat')
_MODS = ('none', 'SS', 'FS', 'SFS')
_lock = threading.Lock()     # 取り込みと測定を同時に走らせない


class PluginError(Exception):
    """利用者に見せる失敗。code は JS 側で翻訳キーにする（rt.err.<code>）"""
    def __init__(self, code, detail=''):
        super().__init__(code)
        self.code, self.detail = code, str(detail)[:500]


def _vtuple(v):
    return tuple(int(x) for x in v.split('.'))


class RatingPlugin:
    def __init__(self, data_dir):
        self.root = os.path.join(data_dir, 'plugins', 'rating')

    # ---- 状態 ----
    def installed(self):
        """取り込み済みの版（新しい順）。plugin.json があり protocol が読めるものだけ"""
        out = []
        if os.path.isdir(self.root):
            for n in os.listdir(self.root):
                if not _VER_RE.fullmatch(n):
                    continue
                meta = self._meta(n)
                if meta:
                    out.append({'version': n, 'protocol': meta.get('protocol'), 'compatible': meta.get('protocol') == PROTOCOL})
        return sorted(out, key=lambda m: _vtuple(m['version']), reverse=True)

    def _meta(self, ver):
        p = os.path.join(self.root, ver, 'plugin.json')
        try:
            with open(p, 'r', encoding='utf-8') as f:
                m = json.load(f)
            return m if m.get('version') == ver and os.path.isfile(os.path.join(self.root, ver, 'nlm-rating.exe')) else None
        except Exception:
            return None

    def current(self):
        """使う版。current.json の版が使えなければ、使える中で最新の版"""
        inst = [m for m in self.installed() if m['compatible']]
        try:
            with open(os.path.join(self.root, 'current.json'), 'r', encoding='utf-8') as f:
                want = json.load(f).get('version')
            for m in inst:
                if m['version'] == want:
                    return m
        except Exception:
            pass
        return inst[0] if inst else None

    def status(self):
        cur = self.current()
        return {'ok': True, 'protocol': PROTOCOL, 'current': cur['version'] if cur else None, 'installed': self.installed(),
                'repo': f'https://github.com/{REPO}'}

    def use(self, ver):
        ver = str(ver or '')
        m = next((m for m in self.installed() if m['version'] == ver), None)
        if not m:
            raise PluginError('notInstalled')
        if not m['compatible']:
            raise PluginError('protocol')
        self._write_current(ver)
        return self.status()

    def _write_current(self, ver):
        os.makedirs(self.root, exist_ok=True)
        with open(os.path.join(self.root, 'current.json'), 'w', encoding='utf-8') as f:
            json.dump({'version': ver}, f)

    # ---- 取得 ----
    @staticmethod
    def _get(url, limit):
        req = urllib.request.Request(url, headers={'User-Agent': 'NonLinearMapper'})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                data = r.read(limit + 1)
        except urllib.error.HTTPError as e:
            raise PluginError('notFound' if e.code == 404 else 'network', e)   # 404＝配布元にまだ公開中の版が無い
        except Exception as e:
            raise PluginError('network', e)
        if len(data) > limit:
            raise PluginError('tooLarge')
        return data

    @staticmethod
    def _check_manifest(raw):
        try:
            m = json.loads(raw)
            ver, z = str(m['version']), m['zip']
            ok = (m.get('name') == 'nlm-rating' and _VER_RE.fullmatch(ver) and m.get('platform') == PLATFORM
                  and isinstance(m.get('protocol'), int) and z.get('name') == f'nlm-rating-{ver}-{PLATFORM}.zip'
                  and re.fullmatch(r'[0-9a-f]{64}', str(z.get('sha256'))) and 0 < int(z.get('size')) <= MAX_ZIP)
        except Exception:
            ok = False
        if not ok:
            raise PluginError('badManifest')
        return m

    def check(self):
        """GitHub の最新版を調べる（取り込みはしない）"""
        m = self._check_manifest(self._get(MANIFEST_URL, 64 * 1024))
        st = self.status()
        st['latest'] = {'version': m['version'], 'protocol': m['protocol'], 'size': m['zip']['size'],
                        'compatible': m['protocol'] == PROTOCOL,
                        'installed': any(i['version'] == m['version'] for i in st['installed'])}
        return st

    def install(self):
        """最新版を取得し、SHA-256 を照合して plugins/rating/<版>/ へ展開する。成功したらその版を使う版にする"""
        with _lock:
            m = self._check_manifest(self._get(MANIFEST_URL, 64 * 1024))
            if m['protocol'] != PROTOCOL:
                raise PluginError('protocol')   # 古い NLM に新しすぎるプラグインを入れない（NLM の更新が必要）
            ver, z = m['version'], m['zip']
            data = self._get(ZIP_URL.format(ver=ver, name=z['name']), MAX_ZIP)
            if len(data) != int(z['size']) or hashlib.sha256(data).hexdigest() != z['sha256']:
                raise PluginError('hash')
            self.install_zip(data, ver)
            self._write_current(ver)
        return self.status()

    def install_zip(self, data, ver):
        """照合済みの zip を展開する（テストからも呼ぶ）。いったん一時フォルダへ展開してから入れ替える"""
        import io
        dst = os.path.join(self.root, ver)
        tmp = os.path.join(self.root, '.tmp-' + ver)
        shutil.rmtree(tmp, ignore_errors=True)
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as zf:
                total = 0
                for info in zf.infolist():
                    name = info.filename
                    parts = name.split('/')
                    # フォルダ外へ出る名前・絶対パス・ドライブ名・'\' を含む名前は拒否（zip slip）
                    if (not name or name.startswith('/') or '\\' in name or ':' in name
                            or any(p in ('..', '.') for p in parts)):
                        raise PluginError('badZip', name)
                    total += info.file_size
                    if total > MAX_UNZIP:
                        raise PluginError('tooLarge')
                os.makedirs(tmp)
                zf.extractall(tmp)
            meta_p = os.path.join(tmp, 'plugin.json')
            with open(meta_p, 'r', encoding='utf-8') as f:
                meta = json.load(f)
            if meta.get('version') != ver or meta.get('protocol') != PROTOCOL or not os.path.isfile(os.path.join(tmp, 'nlm-rating.exe')):
                raise PluginError('badZip', 'plugin.json')
            shutil.rmtree(dst, ignore_errors=True)
            os.replace(tmp, dst)
        except PluginError:
            raise
        except Exception as e:
            raise PluginError('badZip', e)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    # ---- 測定 ----
    def measure(self, body):
        """body = {files:[{name,text}], modifiers:[...]}。Info.dat と書き出す難易度の .dat（NLM の書き出しと同じ中身）"""
        files = body.get('files')
        if not isinstance(files, list) or not (2 <= len(files) <= 32):
            raise PluginError('badInput')
        clean, total = [], 0
        for f in files:
            name, text = (f or {}).get('name'), (f or {}).get('text')
            if not isinstance(name, str) or not isinstance(text, str) or not _DAT_RE.fullmatch(name):
                raise PluginError('badInput')
            total += len(text)
            clean.append({'name': name, 'text': text})
        if total > MAX_INPUT:
            raise PluginError('tooLarge')
        mods = [m for m in _MODS if m in (body.get('modifiers') or ['none'])]
        cur = self.current()
        if not cur:
            raise PluginError('notInstalled')
        exe = os.path.join(self.root, cur['version'], 'nlm-rating.exe')
        req = json.dumps({'protocol': PROTOCOL, 'files': clean, 'modifiers': mods}, ensure_ascii=False).encode('utf-8')
        with _lock:
            try:
                r = subprocess.run([exe], input=req, capture_output=True, timeout=RUN_TIMEOUT, cwd=os.path.dirname(exe),
                                   creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            except subprocess.TimeoutExpired:
                raise PluginError('timeout')
            except OSError as e:
                raise PluginError('run', e)
        try:
            out = json.loads(r.stdout.decode('utf-8'))
        except Exception:
            raise PluginError('run', (r.stderr or b'').decode('utf-8', 'replace')[-500:] or 'exit %s' % r.returncode)
        if not out.get('ok'):
            raise PluginError('run', out.get('error', ''))
        # プラグインの出力は数値・既知の文字列だけを通す（画面に出す値なので）
        res = []
        for d in out.get('results') or []:
            ratings = {}
            for m in mods:
                v = (d.get('ratings') or {}).get(m)
                ratings[m] = {k: float(v[k]) for k in ('stars', 'pass', 'tech', 'acc', 'predictedAcc') if isinstance(v.get(k), (int, float))} if isinstance(v, dict) else None
            res.append({'characteristic': str(d.get('characteristic', ''))[:32], 'difficulty': str(d.get('difficulty', ''))[:32],
                        'notes': int(d.get('notes') or 0), 'skipped': d.get('skipped') if d.get('skipped') in ('tooFewNotes',) else None,
                        'ratings': ratings})
        return {'ok': True, 'version': cur['version'], 'elapsedMs': int(out.get('elapsedMs') or 0), 'results': res}

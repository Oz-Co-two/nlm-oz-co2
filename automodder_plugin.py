# AutoModder の判定を動かすプラグイン nlm-automodder の取り込み・更新・実行（2026-10-27）
#
# プラグインは NLM 本体に同梱しない別配布（https://github.com/Oz-Co-two/nlm-automodder ・ MIT）。中身は AutoModder
# （LightAi39/ChroMapper-AutoModder・MIT）の自動の確かめ（BLMapCheck）を改変せずに組み立てた .NET の自己完結 exe で、
# 1 回ごとに起動し、標準入力に譜面の JSON を渡して標準出力の JSON を受け取る（常駐・ポートなし）。入出力はプラグインの README。
# 作りは「難易度を測る」の rating_plugin.py と同じ（取り込み・照合・置き場所・版の選択）。違いは入出力と、同時に動かすのは 1 つだけな所。
#
# 置き場所: <DATA_DIR>/plugins/automodder/<版>/（exe 隣＝asset/・config/ と同じユーザーデータ扱い。旧版は残す）
#           <DATA_DIR>/plugins/automodder/current.json に使う版を記録（旧版へ戻せる）
#           ネットに繋がらない PC では、配布の zip を展開した中身をこの <版>/ に置けば使える（plugin.json の版・protocol が合う物だけ）
# 安全のための約束:
#  - 取得先 URL はここに固定。JS から URL・パス・版以外の値を受け取らない（版も「取り込み済みの一覧」と照合する）
#  - zip は manifest.json の SHA-256・サイズと照合してから展開し、展開時にフォルダ外へ出る名前を拒否する
#  - GitHub への通信は、利用者がボタンを押した時と、起動時の更新の確認（取り込み済みの時だけ・環境設定で OFF にできる・
#    js/update/update-dialog.js。2026-10-28 から）だけ
#  - 署名なし exe の実行になるので、取得先固定＋ハッシュ照合は外さないこと
#  - プラグインの出力は画面に出すので、知っている項目・形だけを通す（文字は長さを切る。画面では textContent／escHtml で出す）
import hashlib, json, math, os, re, shutil, subprocess, threading, urllib.error, urllib.request, zipfile

NAME = 'nlm-automodder'
EXE = 'nlm-automodder.exe'
REPO = 'Oz-Co-two/nlm-automodder'
MANIFEST_URL = f'https://github.com/{REPO}/releases/latest/download/manifest.json'
ZIP_URL = f'https://github.com/{REPO}/releases/download/v{{ver}}/{{name}}'
RELEASE_URL = f'https://github.com/{REPO}/releases/tag/v{{ver}}'   # 更新のお知らせの「詳しく見る」（リリースの説明＝日英）
PROTOCOL = 1                # NLM が話せるプラグインとの通信仕様の版（プラグイン側 Program.Protocol と同じ値）
PLATFORM = 'win-x64'
MAX_ZIP = 100 * 1024 * 1024  # 取得する zip の上限（実物は約 12MB）
MAX_UNZIP = 300 * 1024 * 1024  # 展開後の合計の上限（実物は約 29MB）
MAX_INPUT = 64 * 1024 * 1024   # 渡す譜面 JSON の合計の上限
MAX_OUTPUT = 64 * 1024 * 1024  # 受け取る結果の JSON の上限
RUN_TIMEOUT = 300            # 1 回の上限秒（1 譜面 0.5〜1 秒ほど。ほとんどは起動）
MAX_RESULTS = 20000          # 画面へ渡す結果の数の上限（それを超えた分と、1 件の物の数の上限を超えた分は truncated で知らせる）
MAX_OBJS = 5000
_VER_RE = re.compile(r'\d{1,4}\.\d{1,4}\.\d{1,4}')
_DAT_RE = re.compile(r'[A-Za-z0-9_\- ]{1,64}\.dat')
_WORD_RE = re.compile(r'[A-Za-z0-9_]{1,40}')
_HEX_RE = re.compile(r'[0-9a-f]{7,40}')
SEVERITIES = ('Passed', 'Info', 'Suggestion', 'Warning', 'Error', 'Inconclusive', 'Data')   # AutoModder の Severity
CRITS = ('Success', 'Warning', 'Fail')   # AutoModder の信号機の欄（CritResult）
OBJ_TYPES = ('note', 'bomb', 'chain', 'arc', 'wall', 'light')
SKIPPED = ('tooFewNotes', 'notLoaded')

# 取り込みと実行を同時に走らせない。実行も 1 つずつ（画面は譜面チェックのパネルの 1 か所だけ）
_cv = threading.Condition()
_runs = {'n': 0, 'installing': False}


class _Install:
    def __enter__(self):
        with _cv:
            _cv.wait_for(lambda: not _runs['installing'] and _runs['n'] == 0)
            _runs['installing'] = True

    def __exit__(self, *a):
        with _cv:
            _runs['installing'] = False
            _cv.notify_all()


class _Run:
    def __enter__(self):
        with _cv:
            _cv.wait_for(lambda: not _runs['installing'] and _runs['n'] == 0)
            _runs['n'] += 1

    def __exit__(self, *a):
        with _cv:
            _runs['n'] -= 1
            _cv.notify_all()


class PluginError(Exception):
    """利用者に見せる失敗。code は JS 側で翻訳キーにする（am.err.<code>）"""
    def __init__(self, code, detail=''):
        super().__init__(code)
        self.code, self.detail = code, str(detail)[:500]


def _vtuple(v):
    return tuple(int(x) for x in v.split('.'))


def _clean_notes(notes):
    """manifest.json の更新内容（版ごとの見出し・プラグインの build.py が CHANGELOG から作る）。画面に出す文字なので形と長さだけ整える
    （表示は textContent。rating_plugin.py と同じ）"""
    out = []
    for n in (notes if isinstance(notes, list) else [])[:200]:
        if not isinstance(n, dict) or not isinstance(n.get('version'), str) or not _VER_RE.fullmatch(n['version']):
            continue
        item = {'version': n['version']}
        for lang in ('ja', 'en'):
            xs = n.get(lang)
            item[lang] = [str(x)[:300] for x in xs[:60] if isinstance(x, str)] if isinstance(xs, list) else []
        out.append(item)
    return out


def _child_env():
    """プラグインを起動する時の環境変数。プラグインは PyInstaller 製ではない（.NET の自己完結 exe）ので、app_update.py の
    _env_for_child（別の PyInstaller 製 exe を正しく起動するための物）は要らない。念のため、このアプリの PyInstaller の設定と
    NLM の設定（データフォルダ等）だけは渡さない（.NET はどれも読まないので、結果は変わらない）"""
    return {k: v for k, v in os.environ.items() if not k.startswith(('_PYI_', 'NLM_')) and k not in ('_MEIPASS2',)}


def _s(v, n):
    """文字だけ・長さを切る（数は文字にする）。それ以外は None"""
    if isinstance(v, bool) or v is None:
        return None
    if isinstance(v, (int, float)):
        v = str(v)
    return v[:n] if isinstance(v, str) else None


def _num(v):
    """有限の数だけ（真偽値は除く）。それ以外は None"""
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    v = float(v)
    return v if math.isfinite(v) else None


class AutoModderPlugin:
    def __init__(self, data_dir):
        self.root = os.path.join(data_dir, 'plugins', 'automodder')

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
                    am = meta.get('automodder')
                    out.append({'version': n, 'protocol': meta.get('protocol'), 'compatible': meta.get('protocol') == PROTOCOL,
                                'automodder': am if isinstance(am, str) and _VER_RE.fullmatch(am) else None})
        return sorted(out, key=lambda m: _vtuple(m['version']), reverse=True)

    def _meta(self, ver):
        p = os.path.join(self.root, ver, 'plugin.json')
        try:
            with open(p, 'r', encoding='utf-8') as f:
                m = json.load(f)
            return m if (isinstance(m, dict) and m.get('version') == ver and m.get('name', NAME) == NAME
                         and os.path.isfile(os.path.join(self.root, ver, EXE))) else None
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
        return {'ok': True, 'protocol': PROTOCOL, 'current': cur['version'] if cur else None,
                'automodder': cur['automodder'] if cur else None, 'installed': self.installed(),
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
            ok = (m.get('name') == NAME and _VER_RE.fullmatch(ver) and m.get('platform') == PLATFORM
                  and isinstance(m.get('protocol'), int) and not isinstance(m.get('protocol'), bool)
                  and m.get('exe', EXE) == EXE
                  and z.get('name') == f'{NAME}-{ver}-{PLATFORM}.zip'
                  and re.fullmatch(r'[0-9a-f]{64}', str(z.get('sha256'))) and 0 < int(z.get('size')) <= MAX_ZIP)
        except Exception:
            ok = False
        if not ok:
            raise PluginError('badManifest')
        return m

    def check(self):
        """GitHub の最新版を調べる（取り込みはしない）。newer＝取り込み済みのどの版より新しい、notes＝それより新しい版の更新内容（新しい順）"""
        m = self._check_manifest(self._get(MANIFEST_URL, 64 * 1024))
        st = self.status()
        am = m.get('automodder')
        lv = _vtuple(m['version'])
        top = max((_vtuple(i['version']) for i in st['installed']), default=(0, 0, 0))
        notes = sorted((n for n in _clean_notes(m.get('notes')) if top < _vtuple(n['version']) <= lv),
                       key=lambda n: _vtuple(n['version']), reverse=True)
        st['latest'] = {'version': m['version'], 'protocol': m['protocol'], 'size': m['zip']['size'],
                        'compatible': m['protocol'] == PROTOCOL,
                        'automodder': am if isinstance(am, str) and _VER_RE.fullmatch(am) else None,
                        'installed': any(i['version'] == m['version'] for i in st['installed']),
                        'newer': lv > top, 'notes': notes}
        return st

    def open_notes(self, ver):
        """その版のリリースのページを既定のブラウザで開く（版の形でなければリリースの一覧）。取得先は REPO に固定"""
        import webbrowser
        ver = ver if isinstance(ver, str) and _VER_RE.fullmatch(ver) else None
        webbrowser.open(RELEASE_URL.format(ver=ver) if ver else f'https://github.com/{REPO}/releases')
        return {'ok': True}

    def install(self):
        """最新版を取得し、SHA-256 を照合して plugins/automodder/<版>/ へ展開する。成功したらその版を使う版にする"""
        with _Install():
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
            with open(os.path.join(tmp, 'plugin.json'), 'r', encoding='utf-8') as f:
                meta = json.load(f)
            if (not isinstance(meta, dict) or meta.get('name') != NAME or meta.get('version') != ver
                    or meta.get('protocol') != PROTOCOL or not os.path.isfile(os.path.join(tmp, EXE))):
                raise PluginError('badZip', 'plugin.json')
            shutil.rmtree(dst, ignore_errors=True)
            os.replace(tmp, dst)
        except PluginError:
            raise
        except Exception as e:
            raise PluginError('badZip', e)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    # ---- 実行 ----
    def run(self, body):
        """body = {files:[{name,text}], songLength}。files の先頭が Info.dat、続きが書き出す難易度の .dat（NLM の書き出しと同じ中身）。
        songLength は曲の長さ（秒・書き出す song.egg の長さ）。AutoModder は Cold End・Outside・Light に使う"""
        files = body.get('files') if isinstance(body, dict) else None
        if not isinstance(files, list) or not (2 <= len(files) <= 32):
            raise PluginError('badInput')
        clean, total = [], 0
        for i, f in enumerate(files):
            f = f if isinstance(f, dict) else {}
            name, text = f.get('name'), f.get('text')
            if not isinstance(name, str) or not isinstance(text, str) or not _DAT_RE.fullmatch(name):
                raise PluginError('badInput')
            if (name.lower() == 'info.dat') != (i == 0):   # Info.dat は先頭に 1 つだけ
                raise PluginError('badInput')
            total += len(text)
            clean.append({'filename': name, 'json': text})
        if total > MAX_INPUT:
            raise PluginError('tooLarge')
        sl = _num(body.get('songLength'))
        if sl is None or not (0 < sl <= 86400):
            raise PluginError('badInput')
        cur = self.current()
        if not cur:
            raise PluginError('notInstalled')
        exe = os.path.join(self.root, cur['version'], EXE)
        req = json.dumps({'protocol': PROTOCOL, 'info': {'filename': 'Info.dat', 'json': clean[0]['json']},
                          'difficulties': clean[1:], 'songLength': sl}, ensure_ascii=False).encode('utf-8')
        with _Run():
            try:
                r = subprocess.run([exe], input=req, capture_output=True, timeout=RUN_TIMEOUT, cwd=os.path.dirname(exe),
                                   env=_child_env(), creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            except subprocess.TimeoutExpired:
                raise PluginError('timeout')
            except OSError as e:
                raise PluginError('run', e)
        if len(r.stdout or b'') > MAX_OUTPUT:
            raise PluginError('tooLarge')
        try:
            out = json.loads((r.stdout or b'').decode('utf-8'))
            if not isinstance(out, dict):
                raise ValueError
        except Exception:
            raise PluginError('run', (r.stderr or b'').decode('utf-8', 'replace')[-500:] or 'exit %s' % r.returncode)
        if out.get('ok') is not True:
            e = out.get('error') if isinstance(out.get('error'), dict) else {}
            raise PluginError('run', ': '.join(x for x in (_s(e.get('type'), 80), _s(e.get('message'), 300)) if x)
                              + (' (%s)' % _s(e.get('where'), 150) if _s(e.get('where'), 150) else ''))
        if out.get('protocol') != PROTOCOL:
            raise PluginError('run', 'protocol %s' % _s(out.get('protocol'), 10))
        return self._clean_output(out, cur['version'])

    @staticmethod
    def _clean_output(out, ver):
        """プラグインの出力のうち、知っている項目・形だけを通す（画面に出す値なので）"""
        trunc = False
        res = []
        raw = out.get('results') if isinstance(out.get('results'), list) else []
        if len(raw) > MAX_RESULTS:
            raw, trunc = raw[:MAX_RESULTS], True
        for d in raw:
            if not isinstance(d, dict) or d.get('severity') not in SEVERITIES:
                continue
            objs = []
            ro = d.get('objects') if isinstance(d.get('objects'), list) else []
            if len(ro) > MAX_OBJS:
                ro, trunc = ro[:MAX_OBJS], True
            for o in ro:
                if not isinstance(o, dict) or o.get('type') not in OBJ_TYPES or _num(o.get('beat')) is None:
                    continue
                c = o.get('color')
                objs.append({'type': o['type'], 'beat': _num(o['beat']), 'x': _num(o.get('x')), 'y': _num(o.get('y')),
                             'color': c if isinstance(c, int) and not isinstance(c, bool) and 0 <= c <= 3 else None,
                             'seconds': _num(o.get('seconds'))})
            data = {}
            rd = d.get('data') if isinstance(d.get('data'), dict) else {}
            for k, v in list(rd.items())[:40]:
                k = _s(k, 60)
                if not k:
                    continue
                if isinstance(v, list):
                    vs = [x for x in (_s(x, 200) for x in v[:50]) if x is not None]
                    if vs:
                        data[k] = vs
                elif _s(v, 200) is not None:
                    data[k] = _s(v, 200)
            rank = d.get('difficultyRank')
            res.append({'name': _s(d.get('name'), 80) or '', 'characteristic': _s(d.get('characteristic'), 32),
                        'difficulty': _s(d.get('difficulty'), 32),
                        'difficultyRank': rank if isinstance(rank, int) and not isinstance(rank, bool) else None,
                        'severity': d['severity'], 'checkType': _s(d.get('checkType'), 40) or '',
                        'description': _s(d.get('description'), 2000) or '', 'objects': objs, 'data': data})
        crit = out.get('criteria') if isinstance(out.get('criteria'), dict) else {}

        def crit_of(c):
            if not isinstance(c, dict):
                return None
            return {k: v for k, v in list(c.items())[:60] if isinstance(k, str) and _WORD_RE.fullmatch(k) and v in CRITS}
        info = crit_of(crit.get('info'))
        diff = {}
        cd = crit.get('diff') if isinstance(crit.get('diff'), dict) else {}
        for ch, dd in list(cd.items())[:16]:
            if not (isinstance(ch, str) and _WORD_RE.fullmatch(ch) and isinstance(dd, dict)):
                continue
            diff[ch] = {}
            for dn, e in list(dd.items())[:16]:
                if not (isinstance(dn, str) and _WORD_RE.fullmatch(dn) and isinstance(e, dict)):
                    continue
                n, rank = e.get('notes'), e.get('difficultyRank')
                diff[ch][dn] = {'difficultyRank': rank if isinstance(rank, int) and not isinstance(rank, bool) else None,
                                'notes': n if isinstance(n, int) and not isinstance(n, bool) else None,
                                'skipped': e.get('skipped') if e.get('skipped') in SKIPPED else None,
                                'highest': e.get('highest') if e.get('highest') in CRITS else None,
                                'error': e.get('error') is True, 'crit': crit_of(e.get('crit'))}
        errs = []
        for e in (out.get('errors') if isinstance(out.get('errors'), list) else [])[:50]:
            if isinstance(e, dict):
                errs.append({'stage': e.get('stage') if e.get('stage') in ('info', 'difficulty') else None,
                             'type': _s(e.get('type'), 80), 'message': _s(e.get('message'), 500), 'where': _s(e.get('where'), 200),
                             'characteristic': _s(e.get('characteristic'), 32), 'difficulty': _s(e.get('difficulty'), 32)})
        am = out.get('automodder') if isinstance(out.get('automodder'), dict) else {}
        amv, amc = am.get('version'), am.get('commit')
        el, sl = _num(out.get('elapsedMs')), _num(out.get('songLength'))
        return {'ok': True, 'version': ver,
                'automodder': {'version': amv if isinstance(amv, str) and _VER_RE.fullmatch(amv) else None,
                               'commit': amc if isinstance(amc, str) and _HEX_RE.fullmatch(amc) else None},
                'config': 'default' if out.get('config') == 'default' else None,
                'elapsedMs': int(el) if el is not None and el >= 0 else 0, 'songLength': sl,
                'results': res, 'criteria': {'info': info, 'diff': diff}, 'errors': errs, 'truncated': trunc}

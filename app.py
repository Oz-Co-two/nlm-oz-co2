# Non-Linear Mapper — デスクトップ版ランチャー（pywebview + 既存 serve.py）
#   - Webコンテンツ（editor.html / js / css / fonts / …）はバンドル(読み取り専用)から配信
#   - 書き込み（環境設定 config/settings.json・アセット asset/*.nlmclip）は
#     %LOCALAPPDATA%\NonLinearMapper\data 配下（ユーザー書込み可・アプリ更新で消えない）
#   - ローカルの空きポートで serve.py を起動し、WebView2 のネイティブウィンドウで表示する。
#     serve.py をそのまま使うので、フォルダ走査・保存・書き出し等のフロント実装は一切変更不要。
import os, sys, socket, threading

# ★pywebview(WinForms) が使う pythonnet のランタイムを .NET Framework(netfx) に固定する。
#   pythonnet 3.x は既定で coreclr(.NET 6+) を優先するが、素の Windows 11 は .NET ランタイム
#   未導入のことがあり、その場合 "Failed to resolve Python.Runtime.Loader.Initialize from
#   ...\Python.Runtime.dll" で起動に失敗する（配布ユーザー報告 2026-07-21）。
#   .NET Framework 4.x は Win10/11 に標準搭載なので netfx を使えば追加インストール不要で確実。
#   ※必ず webview/clr のインポート前に設定すること。
os.environ.setdefault('PYTHONNET_RUNTIME', 'netfx')

def _app_root():
    # PyInstaller onedir/onefile では _MEIPASS にバンドル展開。開発時はこのファイルの隣。
    if getattr(sys, 'frozen', False):
        return sys._MEIPASS
    return os.path.dirname(os.path.abspath(__file__))

def _unblock_dist_folder():
    # 配布zipをダウンロードすると、Windowsが「インターネットからのファイル」の印
    # (Mark of the Web、NTFSの代替データストリーム "Zone.Identifier") を付与し、
    # エクスプローラーでの展開後もDLL等に引き継がれることがある。この状態だと.NET
    # ランタイムがDLLロードを拒否し、pythonnetのCLR初期化が
    # "Failed to resolve Python.Runtime.Loader.Initialize from ...\Python.Runtime.dll"
    # で失敗する（配布ユーザー報告 2026-09-23。手動なら「zipのプロパティ→許可する」で回避可）。
    # ここでは exe と同じフォルダ配下の全ファイルから Zone.Identifier を自動除去し、
    # ユーザーの手動操作を不要にする。frozen時のみ（devはそもそも付かない）。
    # ※必ず webview/clr のインポート前に呼ぶこと。失敗しても起動は妨げない。
    if not getattr(sys, 'frozen', False):
        return
    base = os.path.dirname(sys.executable)
    try:
        for root, _dirs, files in os.walk(base):
            for f in files:
                try:
                    os.remove(os.path.join(root, f) + ':Zone.Identifier')
                except OSError:
                    pass   # ストリームが無い(未ブロック)場合も含め、失敗は無視
    except OSError:
        pass

def _data_root(app_root):
    # 書き込み先（config/settings.json と asset/*.nlmclip）。
    # frozen時は exe と同じフォルダ直下（＝_internal の外）に置く＝ポータブル。
    #   ユーザーが config/asset を直接見られる／フォルダごと持ち運べる。
    #   ※Program Files 等の書込み不可な場所に置くと保存できないが、beta は zip 配布の
    #     ポータブル運用（Downloads/Desktop 等の書ける場所で使う）想定。
    # dev（非frozen）は NLM/ 直下＝純粋な serve.py と同じ。
    if getattr(sys, 'frozen', False):
        d = os.path.dirname(sys.executable)
    else:
        d = app_root
    cfg = os.path.join(d, 'config')
    ast = os.path.join(d, 'asset')
    lng = os.path.join(d, 'lang')
    os.makedirs(cfg, exist_ok=True)
    os.makedirs(ast, exist_ok=True)
    os.makedirs(lng, exist_ok=True)
    # 同梱のシード（見本クリップ／翻訳）を exe隣へ複製＝ユーザーが見える・編集できる形にする。
    # 対象フォルダに該当ファイルが無いときだけコピー（ユーザーの編集を上書きしない）。
    def _seed(seed_dir, dst_dir, exts):
        try:
            import shutil
            if not os.path.isdir(seed_dir) or os.path.abspath(seed_dir) == os.path.abspath(dst_dir):
                return
            have = any(f.lower().endswith(exts) for f in os.listdir(dst_dir))
            if have:
                return
            for f in os.listdir(seed_dir):
                if f.lower().endswith(exts):
                    try: shutil.copyfile(os.path.join(seed_dir, f), os.path.join(dst_dir, f))
                    except OSError: pass
        except Exception:
            pass
    _seed(os.path.join(app_root, 'asset'), ast, ('.nlmclip',))
    _seed(os.path.join(app_root, 'lang'),  lng, ('.json',))
    return d

def _free_port():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(('127.0.0.1', 0))
    port = s.getsockname()[1]
    s.close()
    return port

# ---- ファイル種別アイコンの登録（配布先でも .nlmf/.nlmclip にアイコンが出るようにする） ----
# ファイルのアイコンは「このPCの HKCU に .nlmf→ローカルの.ico を登録」して初めて表示される。
# .nlmf ファイル自体にアイコンは埋め込めない＝配布先で何もしないと真っ白な書類になる。
# そこで初回起動時に、同梱の .ico をユーザー領域へコピーし HKCU に関連付けを登録する。
# 管理者不要（HKCU のみ）・アイコンだけ（ダブルクリックの動作は変えない）・登録済みなら何もしない。
_ASSOC = [
    ('.nlmf',    'NonLinearMapper.Project', 'Non-Linear Mapper プロジェクト',    'nlmfile.ico'),
    ('.nlmclip', 'NonLinearMapper.Clip',    'Non-Linear Mapper アセットクリップ', 'nlmclip.ico'),
]

def _register_file_icons(app_root):
    if sys.platform != 'win32':
        return
    try:
        import winreg, shutil, hashlib
        icon_dst = os.path.join(os.environ.get('LOCALAPPDATA') or os.path.expanduser('~'),
                                'NonLinearMapper', 'icons')
        os.makedirs(icon_dst, exist_ok=True)
        changed = False
        for ext, progid, friendly, icofile in _ASSOC:
            src = os.path.join(app_root, 'icons', icofile)
            if not os.path.isfile(src):
                continue
            base = os.path.splitext(icofile)[0]   # 'nlmfile'
            # ★アイコンキャッシュ対策: 中身のハッシュをファイル名に入れる。
            #   Windows は「パス+索引」でアイコンを描画キャッシュするので、同名で中身だけ
            #   差し替えても古い絵が出続ける。中身が変わればファイル名が変わる＝別アイコン扱いで
            #   必ず描き直される。アプリ更新でデザインを変えたときも配布先で自動的に反映される。
            h = hashlib.md5(open(src, 'rb').read()).hexdigest()[:8]
            dst = os.path.join(icon_dst, '%s.%s.ico' % (base, h))
            # 旧バージョンの同系ファイルを掃除（base.*.ico のうち今回以外）
            try:
                for f in os.listdir(icon_dst):
                    if (f.startswith(base + '.') and f.endswith('.ico')
                            and f != os.path.basename(dst)):
                        try: os.remove(os.path.join(icon_dst, f))
                        except OSError: pass
            except OSError:
                pass
            if not os.path.isfile(dst):
                try: shutil.copyfile(src, dst)
                except OSError: pass
            exe = sys.executable  # frozen時=NonLinearMapper.exe の絶対パス
            open_cmd = '"%s" "%%1"' % exe
            # 既に完全一致で登録済み（アイコン一致＋拡張子リンク有＋開くコマンドが「今のexe」を指す）なら触らない。
            # ＝毎回書かない（無駄なシェル通知を避ける）。exeを移動した場合は開くコマンドが古いパスのままなので
            #   ここが一致せず、下で新パスへ登録し直される（移動後の初回起動で自動修正）。
            try:
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                                    r'Software\Classes\%s\DefaultIcon' % progid) as k:
                    cur = winreg.QueryValueEx(k, '')[0]
                if cur == dst and _ext_points_to(ext, progid) and _open_cmd_is(progid, open_cmd):
                    continue
            except FileNotFoundError:
                pass
            # 登録: 拡張子→ProgID、ProgID→フレンドリ名＋DefaultIcon(ハッシュ版パス)
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, r'Software\Classes\%s' % ext) as k:
                winreg.SetValueEx(k, '', 0, winreg.REG_SZ, progid)
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, r'Software\Classes\%s' % progid) as k:
                winreg.SetValueEx(k, '', 0, winreg.REG_SZ, friendly)
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER,
                                  r'Software\Classes\%s\DefaultIcon' % progid) as k:
                winreg.SetValueEx(k, '', 0, winreg.REG_SZ, dst)
            # ★開くコマンドは必須。これが無いと Windows が「不完全な関連付け」として
            #   拡張子キー(.nlmf)を後で勝手に削除し、アイコンが消える（アイコンだけの登録は維持されない）。
            #   ダブルクリック=NLM起動（%1=ファイルパス。将来そのファイルを開く実装に使える）。
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER,
                                  r'Software\Classes\%s\shell\open\command' % progid) as k:
                winreg.SetValueEx(k, '', 0, winreg.REG_SZ, open_cmd)
            changed = True
        if changed:
            _notify_shell()
    except Exception:
        pass  # アイコン登録失敗でアプリ起動を妨げない

def _ext_points_to(ext, progid):
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Software\Classes\%s' % ext) as k:
            return winreg.QueryValueEx(k, '')[0] == progid
    except OSError:
        return False

def _open_cmd_is(progid, expected):
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r'Software\Classes\%s\shell\open\command' % progid) as k:
            return winreg.QueryValueEx(k, '')[0] == expected
    except OSError:
        return False

def _notify_shell():
    try:
        import ctypes
        ctypes.windll.shell32.SHChangeNotify(0x08000000, 0, None, None)  # SHCNE_ASSOCCHANGED
    except Exception:
        pass

def _open_file_arg():
    # Windowsがダブルクリックで渡すファイルパス（shell\open\command の %1）。
    # .nlmf/.bslm/.bsnm のみ受け付ける。無ければ ''（通常起動）。
    for a in sys.argv[1:]:
        if a.lower().endswith(('.nlmf', '.bslm', '.bsnm')) and os.path.isfile(a):
            return os.path.abspath(a)
    return ''

def main():
    _unblock_dist_folder()   # webview(→pythonnet/clr)のインポート前に済ませる
    app_root = _app_root()
    data_root = _data_root(app_root)
    # serve.py がインポート時に読む環境変数を先に設定する
    os.environ['NLM_BASE_DIR'] = app_root
    os.environ['NLM_DATA_DIR'] = data_root
    os.environ['NLM_OPEN_FILE'] = _open_file_arg()   # ダブルクリックで開くファイル（serve.py が /__openarg で提供）

    _register_file_icons(app_root)   # 配布先でも .nlmf/.nlmclip にアイコンが出るよう初回登録

    sys.path.insert(0, app_root)
    import serve  # 既存の開発サーバをそのままライブラリとして使う

    port = _free_port()
    httpd = serve.make_server(port=port, bind='127.0.0.1')
    threading.Thread(target=httpd.serve_forever, daemon=True).start()

    import webview

    class Api:
        # ブラウザのFile System Access APIは絶対パスを一切JSへ渡さないため、再オープン時の
        # 自動読込ができない（handleをIndexedDBに保存する手も別問題でWebView2をクラッシュさせる）。
        # pywebviewのネイティブダイアログは実パスを返すので、音源だけこちら経由にして
        # そのパスをプロジェクトJSONへ保存 → 次回はダイアログ無しでPythonが直接読み込む。
        def pick_song_file(self):
            paths = webview.windows[0].create_file_dialog(
                webview.FileDialog.OPEN,
                file_types=('音源ファイル (*.egg;*.ogg;*.oga;*.opus;*.mp3;*.m4a;*.aac;*.wav;*.flac;*.weba;*.webm)',
                            'すべてのファイル (*.*)'))
            return paths[0] if paths else None

        def read_song_file(self, path):
            import base64
            try:
                if not path or not os.path.isfile(path):
                    return {'ok': False, 'error': 'not-found'}
                with open(path, 'rb') as f:
                    data = f.read()
                return {'ok': True, 'name': os.path.basename(path), 'mtime': os.path.getmtime(path),
                        'data': base64.b64encode(data).decode('ascii')}
            except Exception as e:
                return {'ok': False, 'error': str(e)}

        # ---- 出力フォルダ / カバー画像もネイティブ方式（曲と同じ理由）----
        # 出力フォルダ・カバー画像もブラウザのFile System Access APIだと絶対パスが取れず、再オープンのたびに
        # 選び直しになり、しかも id指定で覚える「前回の場所」が現在のパスとズレて古い場所で開いてしまう。
        # ネイティブダイアログの実パスをプロジェクトへ保存し、JS側の疑似ハンドル(mkNativeDir/mkNativeFile)が
        # 下のfs_*を呼ぶ＝書き出し処理はFileSystemHandleと同じ呼び方のまま動く。
        def pick_folder(self, start=''):
            kw = {'directory': start} if start and os.path.isdir(start) else {}
            paths = webview.windows[0].create_file_dialog(webview.FileDialog.FOLDER, **kw)
            return paths[0] if paths else None

        def pick_image_file(self, start=''):
            d = os.path.dirname(start) if start else ''
            kw = {'directory': d} if d and os.path.isdir(d) else {}
            paths = webview.windows[0].create_file_dialog(
                webview.FileDialog.OPEN,
                file_types=('画像ファイル (*.png;*.jpg;*.jpeg;*.webp;*.gif;*.bmp)', 'すべてのファイル (*.*)'), **kw)
            return paths[0] if paths else None

        @staticmethod
        def _child(base, name):   # 名前は1階層分のみ許可（'..'や区切り文字で外へ出さない）
            if not name or name in ('.', '..') or any(c in name for c in '/\\:'):
                return None
            return os.path.join(base, name)

        def fs_isdir(self, path):
            return bool(path) and os.path.isdir(path)

        def fs_isfile(self, path):
            return bool(path) and os.path.isfile(path)

        def fs_subdir(self, base, name, create):
            try:
                p = self._child(base, name)
                if not p:
                    return {'ok': False, 'error': 'bad-name'}
                if create:
                    os.makedirs(p, exist_ok=True)
                if not os.path.isdir(p):
                    return {'ok': False, 'error': 'not-found'}
                return {'ok': True, 'path': p}
            except Exception as e:
                return {'ok': False, 'error': str(e)}

        def fs_file(self, base, name, create):
            try:
                p = self._child(base, name)
                if not p:
                    return {'ok': False, 'error': 'bad-name'}
                if not create and not os.path.isfile(p):
                    return {'ok': False, 'error': 'not-found'}
                return {'ok': True, 'path': p}   # create時の実体作成はfs_writeが行う
            except Exception as e:
                return {'ok': False, 'error': str(e)}

        def fs_write(self, path, b64):
            import base64
            try:
                if not path or not os.path.isdir(os.path.dirname(path)):
                    return {'ok': False, 'error': 'no-dir'}
                with open(path, 'wb') as f:
                    f.write(base64.b64decode(b64))
                return {'ok': True}
            except Exception as e:
                return {'ok': False, 'error': str(e)}

    api = Api()

    url = 'http://127.0.0.1:%d/editor.html' % port
    win = webview.create_window(
        'Non-Linear Mapper',
        url,
        width=1600, height=980, min_size=(1100, 720),
        confirm_close=True,
        js_api=api,
    )
    try:
        webview.start()   # WebView2 (Edge Chromium) を使用。既定でメインスレッドをブロック。
    finally:
        try:
            httpd.shutdown()
        except Exception:
            pass

if __name__ == '__main__':
    main()

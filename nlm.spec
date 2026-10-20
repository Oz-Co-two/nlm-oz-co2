# PyInstaller spec — Non-Linear Mapper デスクトップ版（pywebview + serve.py）
# ビルド: cd NLM && python -m PyInstaller nlm.spec
# 出力:   NLM/dist/NonLinearMapper/NonLinearMapper.exe （onedir）
import os
from PyInstaller.utils.hooks import collect_all, copy_metadata

block_cipher = None
HERE = os.path.abspath('.')

# Webコンテンツ一式を読み取り専用データとして同梱（editor.html から参照されるもの全部）。
# 書き込み対象（config/settings.json・asset の実データ）は実行時に %LOCALAPPDATA% 側へ作るので
# ここに入る config/ は settings.default.json と初期 settings.json（見本）、asset/ は見本クリップのみ。
datas = [
    ('editor.html', '.'),
    ('serve.py', '.'),
    ('rating_plugin.py', '.'),   # 難易度を測る（BL星の近似）プラグインの取り込み・実行。serve.py が import する
    ('app_update.py', '.'),      # 本体の自動更新。serve.py・app.py が import する
    ('media_library.py', '.'),   # MEDIA ライブラリ（記録・走査・プレイ記録）。serve.py が import する
    ('map_hash.py', '.'),        # 譜面のハッシュ。media_library.py が import する
    ('native_paths.py', '.'),    # パスの字面の判定。app.py・media_library.py が import する
    ('song_details.py', '.'),    # 全曲データ（jsDelivr）。serve.py が import する
    ('beatsaver_api.py', '.'),   # BeatSaver への1曲の問い合わせ。serve.py が import する
    ('song_analysis/*.py', 'song_analysis'),   # 曲の解析（テンポ・構成）。serve.py が import する（librosa 等は解析を始めた時）
    ('js', 'js'),
    ('css', 'css'),
    ('fonts', 'fonts'),
    ('icons', 'icons'),
    ('guide', 'guide'),          # 画面の中の案内の画像（解析が終わった時の案内。tools/make_guide_shots.py が撮る）
    ('lang', 'lang'),
    ('preview-v4', 'preview-v4'),
    ('config/settings.default.json', 'config'),   # 初期値のみ同梱。個人設定 settings.json はバンドルしない（配布版は初期状態で始まる）
    ('asset', 'asset'),
]

# pywebview の Windows(WebView2) バックエンドと pythonnet を確実に取り込む
hiddenimports = ['serve', 'rating_plugin', 'app_update', 'media_library', 'map_hash', 'native_paths', 'song_details', 'beatsaver_api',
                 'song_analysis', 'song_analysis.service', 'song_analysis.tempo', 'song_analysis.structure']
# 曲の解析が使う librosa・numpy・scipy・scikit-learn・numba・llvmlite・soundfile・soxr は、song_analysis から見つかり、
# pyinstaller-hooks-contrib のフック（librosa は lazy_loader が読む .pyi も・numba・llvmlite・sklearn・soundfile）で取り込まれる。
# 関数の中で import している物（librosa・threadpoolctl）も PyInstaller は見つける。念のため名前でも足す
hiddenimports += ['librosa', 'threadpoolctl', 'soxr', 'soundfile', 'sklearn.cluster']
# 曲の解析の部品のライセンス文（各部品の dist-info の LICENSE・licenses/）を exe に入れる（THIRD_PARTY_NOTICES.txt の 9.）
for _pkg in ('librosa', 'numpy', 'scipy', 'scikit-learn', 'numba', 'llvmlite', 'soundfile', 'soxr', 'joblib', 'threadpoolctl',
             'lazy_loader', 'pooch', 'requests', 'certifi', 'urllib3', 'idna', 'charset-normalizer', 'platformdirs', 'decorator',
             'msgpack', 'narwhals', 'cloudpickle', 'typing_extensions', 'cffi', 'pycparser', 'packaging'):
    try:
        datas += copy_metadata(_pkg)
    except Exception:
        pass
binaries = []
for pkg in ('webview', 'clr_loader', 'pythonnet'):
    try:
        b, d, h = collect_all(pkg)
        binaries += b; datas += d; hiddenimports += h
    except Exception:
        pass

a = Analysis(
    ['app.py'],
    pathex=[HERE],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=['tkinter'],
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name='NonLinearMapper',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,          # GUIアプリ（コンソール窓を出さない）
    disable_windowed_traceback=False,
    icon=os.path.join(HERE, 'icons', 'nlmapp.ico'),   # exe本体＝NLMロゴ（どのPCでも表示される）
)
coll = COLLECT(
    exe, a.binaries, a.zipfiles, a.datas,
    strip=False, upx=False, upx_exclude=[],
    name='NonLinearMapper',
)

# 案内文とライセンス（LICENSE・THIRD_PARTY_NOTICES.txt）はexeと同じ階層（_internalの外）に置きたいが、
# COLLECT()へのTOC追加はPyInstaller(6.x系)ではonedirでも_internal配下にまとめられてしまうため、
# ビルド後に直接コピーする（COLLECT完了後のこの位置なら毎回確実に反映される）。
# ここに足した物は app_update.py の REPLACE_ITEMS にも足す（自動更新でも入れ替わるように）。
import shutil
for _name in ('はじめにお読みください.txt', 'LICENSE', 'THIRD_PARTY_NOTICES.txt'):
    _src = os.path.join(HERE, _name)
    if os.path.isfile(_src):
        shutil.copy2(_src, os.path.join(DISTPATH, 'NonLinearMapper', _name))

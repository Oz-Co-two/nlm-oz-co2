# PyInstaller spec — Non-Linear Mapper デスクトップ版（pywebview + serve.py）
# ビルド: cd NLM && python -m PyInstaller nlm.spec
# 出力:   NLM/dist/NonLinearMapper/NonLinearMapper.exe （onedir）
import os
from PyInstaller.utils.hooks import collect_all

block_cipher = None
HERE = os.path.abspath('.')

# Webコンテンツ一式を読み取り専用データとして同梱（editor.html から参照されるもの全部）。
# 書き込み対象（config/settings.json・asset の実データ）は実行時に %LOCALAPPDATA% 側へ作るので
# ここに入る config/ は settings.default.json と初期 settings.json（見本）、asset/ は見本クリップのみ。
datas = [
    ('editor.html', '.'),
    ('serve.py', '.'),
    ('js', 'js'),
    ('css', 'css'),
    ('fonts', 'fonts'),
    ('icons', 'icons'),
    ('lang', 'lang'),
    ('preview-v4', 'preview-v4'),
    ('config/settings.default.json', 'config'),   # 初期値のみ同梱。個人設定 settings.json はバンドルしない（配布版は初期状態で始まる）
    ('asset', 'asset'),
]

# pywebview の Windows(WebView2) バックエンドと pythonnet を確実に取り込む
hiddenimports = ['serve']
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

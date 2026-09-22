"""PyInstallerでビルドして、配布フォルダの exe と _internal だけを差し替える。

使い方:  python tools/build_and_deploy.py [--no-backup] [--skip-build]
  --skip-build : ビルドは省略し、既存の dist/ をそのまま配布フォルダへ反映する
  --no-backup  : 差し替え前の退避(_backup_before_update_日時/)を作らない

アプリが起動中なら警告して終了する（閉じてから再実行）。
退避フォルダは新しい順に KEEP_BACKUPS 個だけ残し、古いものは自動削除する。

配布フォルダの asset/ config/ は上書きしない（ユーザーデータのため。CLAUDE.md参照）。
lang/ はアプリが exe隣を優先して読むため、ソースのlang/*.jsonで上書きする（旧版は退避に含める。ユーザーが追加した言語ファイルは残す）。
"""
import argparse
import datetime
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT
DIST = SRC / "dist" / "NonLinearMapper"
DEPLOY = ROOT / "NLM-app"   # 普段使う配布フォルダ（.gitignore済み。バージョンを含めない）
VENV_PY = SRC / ".venv-build" / "Scripts" / "python.exe"   # ビルド用venv（.venv は tools/ の解析用）
TARGETS = ["NonLinearMapper.exe", "_internal"]   # 差し替える対象はこの2つだけ
EXE_NAME = "NonLinearMapper.exe"
BACKUP_PREFIX = "_backup_before_update_"          # このスクリプトが作る退避だけを整理対象にする（手動の _backup_日付 等は触らない）
KEEP_BACKUPS = 5


def _reexec_with_venv_py():
    """`python tools/build_and_deploy.py`のpythonが.venv-build以外(Microsoft Storeスタブ・システムPython等)
    だった場合、.venv-buildのpythonで自分自身を再実行する。PyInstallerはVENV_PYでしか呼べないため、
    ビルド用venvが無いだけの場合はここでは何もせず、build()側の案内メッセージに任せる。"""
    try:
        cur = Path(sys.executable).resolve()
    except OSError:
        return
    if not VENV_PY.exists() or cur == VENV_PY.resolve():
        return
    r = subprocess.run([str(VENV_PY), str(Path(__file__).resolve()), *sys.argv[1:]])
    sys.exit(r.returncode)


def fail(msg):
    print(f"エラー: {msg}", file=sys.stderr)
    sys.exit(1)


def ensure_not_running():
    """アプリ起動中は差し替えられない（ビルドの数分を無駄にしないよう、最初に検査する）"""
    out = subprocess.run(["tasklist", "/FI", f"IMAGENAME eq {EXE_NAME}", "/FO", "CSV", "/NH"],
                         capture_output=True, text=True, errors="replace").stdout
    n = sum(1 for line in out.splitlines() if line.strip().lower().startswith(f'"{EXE_NAME.lower()}"'))
    if n:
        fail(f"{EXE_NAME} が起動中です（{n}プロセス）。\n"
             "  アプリの画面を閉じてから、もう一度実行してください。何も変更していません。")


def prune_backups():
    old = sorted((p for p in DEPLOY.iterdir() if p.is_dir() and p.name.startswith(BACKUP_PREFIX)),
                 key=lambda p: p.name, reverse=True)[KEEP_BACKUPS:]   # 名前=日時なので名前順=新しい順
    for p in old:
        shutil.rmtree(p)
        print(f"== 古い退避を削除: {p.name} ==")


def build():
    if not VENV_PY.exists():
        fail(f"venvが見つかりません: {VENV_PY}\n"
             "  python -m venv .venv-build && .venv-build/Scripts/python -m pip install pywebview pythonnet pyinstaller")
    print("== ビルド中（数分かかります）==")
    r = subprocess.run([str(VENV_PY), "-m", "PyInstaller", "--noconfirm", "--clean", "nlm.spec"], cwd=SRC)
    if r.returncode != 0:
        fail("PyInstallerが失敗しました。配布フォルダは変更していません。")


def deploy(backup):
    for name in TARGETS:
        if not (DIST / name).exists():
            fail(f"ビルド成果物がありません: {DIST / name}")
    if not DEPLOY.is_dir():
        fail(f"配布フォルダがありません: {DEPLOY}")
    if backup:
        bdir = DEPLOY / (BACKUP_PREFIX + datetime.datetime.now().strftime("%Y%m%d_%H%M%S"))
        bdir.mkdir()
        for name in TARGETS:
            if (DEPLOY / name).exists():
                shutil.move(str(DEPLOY / name), str(bdir / name))
        if (DEPLOY / "lang").is_dir():
            shutil.copytree(DEPLOY / "lang", bdir / "lang")
        print(f"== 旧版を退避: {bdir.name} ==")
        prune_backups()
    else:
        for name in TARGETS:
            p = DEPLOY / name
            if p.is_dir():
                shutil.rmtree(p)
            elif p.exists():
                p.unlink()

    for name in TARGETS:
        s, d = DIST / name, DEPLOY / name
        if s.is_dir():
            shutil.copytree(s, d)
        else:
            shutil.copy2(s, d)
    # lang/ はアプリが exe隣を優先して読む（serve.py）ため、ここが古いと新しい翻訳が反映されない。
    # ソースにあるファイルだけ上書きし、ユーザーが追加した言語ファイルは消さない。
    (DEPLOY / "lang").mkdir(exist_ok=True)
    for f in sorted((SRC / "lang").glob("*.json")):
        shutil.copy2(f, DEPLOY / "lang" / f.name)
    print(f"== 配布フォルダへ反映しました: {DEPLOY} ==")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-backup", action="store_true")
    ap.add_argument("--skip-build", action="store_true")
    a = ap.parse_args()
    ensure_not_running()
    if not a.skip_build:
        build()
    deploy(backup=not a.no_backup)


if __name__ == "__main__":
    _reexec_with_venv_py()
    main()

"""JSの構文/初期ロードエラーを自動チェックする（Node.js不使用）。

このプロジェクトはNode/npmを使わない方針（CLAUDE.md参照）なので `node --check` は使えない・使わない。
代わりに、このアプリが元々前提にしているMicrosoft Edgeをヘッドレスで起動し、serve.py経由で
editor.htmlを実際に読み込ませて、コンソールに出るUncaught例外（構文エラー含む）を拾う。
本物のブラウザで実際に最後まで実行させるので、node --checkと違いWebGL/File System Access等
このアプリが前提にしているブラウザ専用APIも込みで検証できる（＝node --checkより実情に合う）。

使い方: .venv-build/Scripts/python.exe tools/check_js.py [対象html（省略時editor.html）]
終了コード: 0=問題なし / 1=コンソールにエラーらしき出力あり / 2=環境側の問題（Edge不在など）
"""
import os
import re
import socket
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

if sys.platform == "win32":
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8")
        except Exception:
            pass

ROOT = Path(__file__).resolve().parent.parent
VENV_PY = ROOT / ".venv-build" / "Scripts" / "python.exe"

EDGE_CANDIDATES = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
]

CONSOLE_LINE_RE = re.compile(r'CONSOLE:\d+\]\s*"(?P<msg>.*)",\s*source:\s*(?P<src>\S+)\s*\((?P<line>\d+)\)')
ERROR_HINT_RE = re.compile(r'Uncaught|SyntaxError|ReferenceError|TypeError|RangeError')


def _reexec_with_venv_py():
    """`python tools/check_js.py`のpythonがMicrosoft Storeスタブ等(.venv-build以外)だった場合、
    .venv-buildのpythonで自分自身を再実行する（build_and_deploy.pyと同じ流儀）。"""
    if not VENV_PY.exists():
        return
    try:
        cur = Path(sys.executable).resolve()
    except OSError:
        cur = None
    if cur != VENV_PY.resolve():
        os.execv(str(VENV_PY), [str(VENV_PY), __file__, *sys.argv[1:]])


def find_edge():
    for p in EDGE_CANDIDATES:
        if Path(p).exists():
            return p
    return None


def free_port():
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


def main():
    _reexec_with_venv_py()

    edge = find_edge()
    if not edge:
        print("✗ Microsoft Edgeが見つかりません（" + " / ".join(EDGE_CANDIDATES) + "）。\n"
              "  このチェックは通常のブラウザ動作確認と同じEdgeを使うので、Edgeがインストールされていれば自動検出できるはずです。",
              file=sys.stderr)
        sys.exit(2)

    target = sys.argv[1] if len(sys.argv) > 1 else "editor.html"

    sys.path.insert(0, str(ROOT))
    import serve
    port = free_port()
    httpd = serve.make_server(port=port)
    th = threading.Thread(target=httpd.serve_forever, daemon=True)
    th.start()

    try:
        url = f"http://127.0.0.1:{port}/{target}"
        with tempfile.TemporaryDirectory(prefix="nlm_check_edge_") as profile:
            log_fd, log_path = tempfile.mkstemp(prefix="nlm_check_log_", suffix=".txt")
            os.close(log_fd)
            try:
                with open(log_path, "w", encoding="utf-8", errors="replace") as logf:
                    subprocess.run([
                        edge, "--headless=new", "--disable-gpu",
                        f"--user-data-dir={profile}",
                        "--enable-logging=stderr", "--v=1",
                        "--virtual-time-budget=8000",
                        "--dump-dom", url,
                    ], stdout=subprocess.DEVNULL, stderr=logf, timeout=40)
                log_text = Path(log_path).read_text(encoding="utf-8", errors="replace")
            finally:
                # Edgeのヘッドレス終了直後は子プロセスがログハンドルをまだ掴んでいることがある＝
                # 後始末の失敗（一時ファイルの消し忘れ）で本処理の結果を握りつぶさないようベストエフォートにする
                try:
                    os.unlink(log_path)
                except OSError:
                    pass
    finally:
        httpd.shutdown()

    problems = []
    for line in log_text.splitlines():
        m = CONSOLE_LINE_RE.search(line)
        if m and ERROR_HINT_RE.search(m.group("msg")):
            problems.append(f'  {m.group("src")}:{m.group("line")}  {m.group("msg")}')

    if problems:
        print(f"✗ {target} の読み込み中にコンソールエラーが出ました:")
        for p in problems:
            print(p)
        sys.exit(1)

    print(f"OK: {target} はエラー無く読み込めました（Edgeヘッドレス・{port}番ポート）")
    sys.exit(0)


if __name__ == "__main__":
    main()

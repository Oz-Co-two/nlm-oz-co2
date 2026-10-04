"""unit_py グループ共通の部品（一時のデータフォルダでserve.pyを起動する・生のHTTP要求を送る）。

serve.py は import 時に環境変数を読むので、ここで先に NLM_DATA_DIR 等を設定してから import する。
グループは1プロセスで動くので、サーバーは最初に使った時に1度だけ起動して使い回す（プロセス終了で止まる）。
"""
import http.client
import json
import os
import socket
import sys
import tempfile
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EXTRA_HOST = "nlm-extra.test"   # NLM_ALLOWED_HOSTS で追加するテスト用ホスト名

_srv = None


def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


class Server:
    pass


def server():
    """起動済みの Server（.port .data_dir .serve モジュール）を返す"""
    global _srv
    if _srv:
        return _srv
    s = Server()
    s.data_dir = tempfile.mkdtemp(prefix="nlm_unitpy_data_")
    os.environ["NLM_DATA_DIR"] = s.data_dir
    os.environ["NLM_ALLOWED_HOSTS"] = EXTRA_HOST
    os.environ.pop("NLM_OPEN_FILE", None)
    sys.path.insert(0, str(ROOT))
    if "serve" in sys.modules:
        del sys.modules["serve"]
    import serve
    s.serve = serve
    s.port = _free_port()
    s.httpd = serve.make_server(port=s.port)
    threading.Thread(target=s.httpd.serve_forever, daemon=True).start()
    _srv = s
    return s


def req(method, path, host=None, headers=None, body=None, origin=None):
    """生のHTTP要求を送って (status, headers, body bytes) を返す。path は加工せずそのまま送る"""
    s = server()
    h = {"Host": s_host(s) if host is None else host}
    if origin:
        h["Origin"] = origin
    h.update(headers or {})
    c = http.client.HTTPConnection("127.0.0.1", s.port, timeout=10)
    try:
        c.request(method, path, body=body, headers=h)
        r = c.getresponse()
        return r.status, dict(r.getheaders()), r.read()
    finally:
        c.close()


def s_host(s):
    return f"127.0.0.1:{s.port}"


def post_json(path, obj, **kw):
    h = {"Content-Type": "application/json", "X-NLM-Request": "1"}
    h.update(kw.pop("headers", {}) or {})
    st, hd, b = req("POST", path, headers=h, body=json.dumps(obj).encode("utf-8"), **kw)
    try:
        return st, json.loads(b.decode("utf-8"))
    except Exception:
        return st, None

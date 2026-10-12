# ネイティブのパスの比較・分類（app.py の _NativeAccess と media_library.py の共用・2026-10-12に app.py から移した）
#
# ネットワーク上のパス(UNC: \\server\share\...)は、存在確認・実体の解決(realpath)をするだけで Windows がそのサーバーへ接続し、
# 利用者のNTLM認証を送る。細工したファイルに \\攻撃者\... を書かれると開いただけで送ってしまうため、UNC は
# 「このPCでダイアログから選んだ物」に**字面で**一致する時だけ触る。その判定にはファイルシステムに触れない
# _path_kind（分類）と _lpath（字面の正規化）を使い、触ってよいと分かった後で _npath（実体へ解決）を使う。
import os


def _npath(p):
    """比較用の正規化パス（ジャンクション/シンボリックリンクも実体へ解決・大文字小文字を無視）。"""
    return os.path.normcase(os.path.realpath(os.path.abspath(str(p))))


def _lpath(p):
    """比較用の正規化パス（字面だけ＝ファイルシステムに触れない。大文字小文字を無視）。"""
    return os.path.normcase(os.path.normpath(p))


def _path_kind(p):
    """JSから来たパスを字面だけで分類する（ファイルシステムには触れない）。
    'local'=ドライブ名から始まる絶対パス(C:\\...) / 'unc'=ネットワーク上のパス(\\\\server\\share\\...) / None=それ以外。
    \\\\?\\・\\\\.\\（デバイスパス）、\\??\\（NTパス）、\\から始まるパス、相対パス、C:foo は None。"""
    if not isinstance(p, str) or not p or '\0' in p:
        return None
    s = p.replace('/', '\\')
    if len(s) >= 3 and s[0].isascii() and s[0].isalpha() and s[1] == ':' and s[2] == '\\':
        return 'local'
    if s.startswith('\\\\') and len(s) > 2 and s[2] not in '?.\\':
        host, _, rest = s[2:].partition('\\')
        if host and rest.split('\\')[0]:
            return 'unc'
    return None


def _is_under(root, p):
    try:
        return os.path.commonpath([root, p]) == root
    except ValueError:   # ドライブが違う等
        return False

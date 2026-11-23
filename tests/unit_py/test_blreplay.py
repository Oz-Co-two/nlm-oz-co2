"""REPLAY の窓の中身（replay-viewer/）: BL のリプレイアプリの写しが MANIFEST.json の指紋どおりか・写しの道具（tools/blreplay_fetch.py）・
伝言の受け手（replay-viewer/bridge.js）の名前。ブラウザは使わない（ズームの動きはスクラッチの確かめ・REPLAY の窓の e2e で見る）"""
import contextlib
import hashlib
import io
import json
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import unitpy_helpers as H

sys.path.insert(0, str(H.ROOT / 'tools'))
import blreplay_fetch as bf  # noqa: E402

VIEW = H.ROOT / 'replay-viewer'


def _check(dest=None):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        rc = bf.check(dest)
    return rc, out.getvalue()


def test_copy_matches_manifest(t):
    '''写した BL のリプレイアプリが MANIFEST.json の指紋（SHA-256）どおりで、一覧に無いファイルも無い（git が行の終わりを変えていない）'''
    t.eq(bf.DEST, VIEW / 'blreplay', '写す先')
    rc, msg = _check()
    t.eq(rc, 0, '--check: ' + msg.strip())
    man = json.loads((bf.DEST / 'MANIFEST.json').read_text(encoding='utf-8'))
    t.ok(len(man['files']) > 300, f'ファイルの数 {len(man["files"])}')
    t.eq(man['patches'], [list(p) for p in bf.PATCHES], '写した時の直しが道具の PATCHES と同じ')
    t.ok((bf.DEST / 'SOURCE.md').is_file() and (bf.DEST / 'LICENSE.txt').is_file(), 'SOURCE.md・LICENSE.txt がある')
    t.ok((bf.DEST / 'fontawesome' / 'LICENSE.txt').is_file(), 'Font Awesome の LICENSE.txt がある')
    t.ok('replay-viewer/blreplay/** -text' in (H.ROOT / '.gitattributes').read_text(encoding='utf-8').splitlines(),
         '.gitattributes で行の終わりを変えない')


def test_patches_applied(t):
    '''直し（PATCHES）が写した物に当たっている＝CDN・サーバーの頭からの場所を読まない'''
    for pat, old, new in bf.PATCHES:
        files = sorted(bf.DEST.glob(pat))
        t.ok(files, f'{pat} がある')
        body = ''.join(f.read_text(encoding='utf-8') for f in files)
        t.ok(old not in body and body.count(new) >= 1, f'{pat}: {old} → {new}')
    html = (bf.DEST / 'index.html').read_text(encoding='utf-8')
    t.ok('use.fontawesome.com' not in html, 'index.html が Font Awesome の CDN を読まない')
    t.eq(html.count('</body>'), 1, 'viewer が bridge.js を足す </body> が 1 つ')


def test_check_detects_changes(t):
    '''--check は中身の違い・無いファイル・一覧に無いファイルを見つける'''
    tmp = Path(tempfile.mkdtemp(prefix='nlm_blr_'))
    try:
        (tmp / 'a').mkdir()
        files = {'index.html': b'<html></html>\n', 'a/b.js': b'x\r\n'}
        for p, b in files.items():
            (tmp / p).write_bytes(b)
        (tmp / 'SOURCE.md').write_text('手で書いた物', encoding='utf-8')
        man = {'files': {p: hashlib.sha256(b).hexdigest() for p, b in files.items()}}
        (tmp / 'MANIFEST.json').write_text(json.dumps(man), encoding='utf-8')
        t.eq(_check(tmp)[0], 0, '同じ（SOURCE.md・MANIFEST.json は数えない）')
        (tmp / 'a/b.js').write_bytes(b'x\n')
        t.eq(_check(tmp)[0], 1, '行の終わりが変わった')
        (tmp / 'a/b.js').write_bytes(b'x\r\n')
        (tmp / 'extra.js').write_bytes(b'1')
        rc, msg = _check(tmp)
        t.ok(rc == 1 and 'extra.js' in msg, '一覧に無いファイル: ' + msg.strip())
        (tmp / 'extra.js').unlink()
        (tmp / 'index.html').unlink()
        t.eq(_check(tmp)[0], 1, '無いファイル')
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_safe_rel(t):
    '''外から来た名前（公開ページ・GitHub の一覧）のうち、写しのフォルダの外へ出る形・使えない文字は書かない'''
    for p in ('index.html', 'build/build.1.js', 'assets/flags/not set.png', 'fontawesome/webfonts/fa-solid-900.woff2'):
        t.ok(bf.safe_rel(p), f'書いてよい: {p}')
    for p in ('..', '../x', 'a/../b', 'a/./b', '/abs', 'C:/x', 'a\\b', ' x', 'x.', 'a//b', '.hidden', ''):
        t.ok(not bf.safe_rel(p), f'書かない: {p!r}')


def test_bridge_messages(t):
    '''bridge.js は NLM の伝言の名前（nlm:'blr'）だけを使い、送る先のオリジンを決めて送る（'*' にしない）'''
    js = (VIEW / 'bridge.js').read_text(encoding='utf-8')
    t.ok("Object.assign({nlm: 'blr'}, m), PO)" in js, "送る伝言は nlm:'blr'・送る先は PO")
    t.ok("d.nlm !== 'blr'" in js, "受ける伝言は nlm:'blr' だけ")
    t.ok('anp' not in js.replace('ANP', ''), "ANP の名前（anp:'blr'）を使わない")
    t.ok("postMessage(" in js and ", '*')" not in js, "postMessage の送る先に '*' を使わない")
    t.ok('e.source !== window.parent || !ALLOW.includes(e.origin)' in js, '相手の窓とオリジンを確かめる')
    for ev in ("ev: 'hi'", "ev: 'ready'", "ev: 'time'", "ev: 'zoom'"):
        t.ok(ev in js, f'知らせ {ev}')

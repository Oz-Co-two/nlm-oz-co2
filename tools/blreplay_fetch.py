"""BL のリプレイアプリ（BeatLeader の Web のリプレイの見え方・https://github.com/BeatLeader/BeatSaber-Web-Replays ・MIT）を
NLM の中（replay-viewer/blreplay/）へ写す道具（2026-11-22・REPLAY の窓）。

元は同じ作者の Auto Note Plotter（nlm-automap・GPLv3）の tools/blreplay_fetch.py。写す先を NLM の場所にしただけで、取り方・直し方
（PATCHES）は同じ＝ANP の写しと NLM の写しはバイトまで同じになる（今の写しは ANP の app/static/blreplay/ を写した物・SOURCE.md）。

BL のリプレイアプリは BeatSaver に無い譜面を開けない（譜面を BeatSaver から取る）。NLM の viewer のサーバー（serve.py）に置いて、
リプレイ（?link=）と遊んだ時の譜面の zip（?mapLink=・zip-loader が BeatSaver に問い合わせずに読む）を渡して開く。

作るには npm（webpack）が要る＝NLM では使わない。そこで BL が公開している組み立て済みの物（https://replay.beatleader.com/ の
index.html・build/・vendor/）をそのまま写し、素材（assets/）は GitHub の一覧（決めた版のコミット）の物を公開ページから取る（無ければ
GitHub の同じ版から）。アイコンの字（Font Awesome Free 6.4.0・ページは CDN から読む）も写して、開く時にネットへ出ないようにする
（出るのは BL の公開プロフィールの問い合わせだけ）。写した物に当てる直しは PATCHES だけ（当たらなければ止まる）。

使い方: .venv-build/Scripts/python.exe -I tools/blreplay_fetch.py [--commit <sha>] [--dry]   … 写す（前の物は丸ごと置き換える。SOURCE.md は残す）
        .venv-build/Scripts/python.exe -I tools/blreplay_fetch.py --check                     … 写した物が MANIFEST.json の指紋どおりか
標準ライブラリだけ。証明書は Windows の置き場（ssl.create_default_context）。
写した後は git の行の終わりを変えない（.gitattributes の replay-viewer/blreplay/** -text）＝--check がそのまま通る。
"""
import argparse
import hashlib
import json
import re
import shutil
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEST = ROOT / 'replay-viewer' / 'blreplay'
SITE = 'https://replay.beatleader.com/'
REPO = 'BeatLeader/BeatSaber-Web-Replays'
FA = 'https://use.fontawesome.com/releases/v6.4.0/'
# 書いてよい場所の形（取ってきたページ・CSS・GitHub の一覧から読んだ名前＝外から来た名前。区切りごとに英数字か _ で始まる名前だけ＝
# ..・.・\・:・ドライブ名・絶対の場所を通さない）。今の写しの 381 ファイルは全部この形（空白を含む物が 1 つ）
SAFE_PART = re.compile(r'[A-Za-z0-9_][A-Za-z0-9 ._+@()-]*')
KEEP = ('SOURCE.md',)   # 写し直しても残す（手で書いた物）
# 素材のうち写さない物（使わない・大きい）: 試しの zip・元の .blend・Font Awesome 5 の字（ページは 6.4.0 を使う）
SKIP = (re.compile(r'^assets/test\.zip$'), re.compile(r'^assets/raw/'), re.compile(r'^assets/webfonts/'))
# 写した物に当てる直し（ファイル, 前, 後）: どれも 1 回だけ当たること（ANP と同じ）
PATCHES = [
    # サーバーの頭からの場所（/assets/…）を、ページからの場所に（NLM の viewer では /blreplay/ の下に置く）
    ('index.html', '"/assets/img/firefoxautoplay.jpg"', '"assets/img/firefoxautoplay.jpg"'),
    ('build/*.js', '"/assets/sounds/silence.mp3"', '"assets/sounds/silence.mp3"'),
    # アイコンの字は写した物を読む（CDN へ出ない）
    ('index.html', 'https://use.fontawesome.com/releases/v6.4.0/css/all.css', 'fontawesome/css/all.css'),
]
UA = 'NLM-blreplay-fetch'
_CTX = ssl.create_default_context()


def get(url, ok404=False):
    url = urllib.parse.quote(url, safe=':/?=&%')   # 素材の名前に空白がある（assets/flags/not set.png）
    req = urllib.request.Request(url, headers={'User-Agent': UA})
    for i in range(3):
        try:
            with urllib.request.urlopen(req, timeout=60, context=_CTX) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code == 404 and ok404:
                return None
            if e.code < 500 or i == 2:
                raise
        except urllib.error.URLError:
            if i == 2:
                raise
        time.sleep(1 + i)


def gh(path):
    return json.loads(get('https://api.github.com/repos/' + REPO + '/' + path))


def page_files(html):
    """index.html が読む組み立て済みの物（build/・vendor/ の相対の場所）"""
    refs = re.findall(r'(?:src|href)="((?:build|vendor)/[A-Za-z0-9._/@+-]+)(?:[?#][^"]*)?"', html)   # 名前の文字は safe_rel と同じ側に絞る
    if not any(r.startswith('build/') and r.endswith('.js') for r in refs):
        raise SystemExit('index.html に build/…js が見つからない（ページの形が変わった）')
    return sorted(set(refs))


def collect(commit=None):
    """→ (files {場所: バイト列}, info)"""
    html_b = get(SITE)
    html = html_b.decode('utf-8')
    files = {'index.html': html_b}
    for p in page_files(html):
        files[p] = get(SITE + p)
        print(f'  {p} {len(files[p]):,} バイト', flush=True)
    if commit is None:
        commit = gh('commits/master')['sha']
    tree = gh(f'git/trees/{commit}?recursive=1')
    if tree.get('truncated'):
        raise SystemExit('GitHub の一覧が途中で切れた')
    blobs = [t['path'] for t in tree['tree'] if t['type'] == 'blob']
    # vendor/ の小さな部品（本体が場所で読むかもしれない物）。aframe の元の形と .map は要らない
    for p in blobs:
        if p.startswith('vendor/') and p.endswith('.js') and p not in files and 'aframe-master' not in p:
            files[p] = get(f'https://raw.githubusercontent.com/{REPO}/{commit}/{p}')
    assets = [p for p in blobs if p.startswith('assets/') and not any(s.search(p) for s in SKIP)]
    from_gh = []
    for i, p in enumerate(assets):
        b = get(SITE + p, ok404=True)
        if b is None or b[:15].lower().startswith(b'<!doctype html'):   # 公開ページに無い（ページの代わりに index が返る時も）
            b = get(f'https://raw.githubusercontent.com/{REPO}/{commit}/{p}')
            from_gh.append(p)
        files[p] = b
        if i % 50 == 0:
            print(f'  素材 {i + 1}/{len(assets)}', flush=True)
    files['LICENSE.txt'] = get(f'https://raw.githubusercontent.com/{REPO}/{commit}/LICENSE')
    css = get(FA + 'css/all.css')
    files['fontawesome/css/all.css'] = css
    for u in sorted(set(re.findall(r'url\(\.\./(webfonts/[A-Za-z0-9._/@+-]+)\)', css.decode('utf-8')))):
        files['fontawesome/' + u] = get(FA + u)
    files['fontawesome/LICENSE.txt'] = get(FA + 'LICENSE.txt', ok404=True) or (
        b'Font Awesome Free 6.4.0 by @fontawesome - https://fontawesome.com\n'
        b'License - https://fontawesome.com/license/free (Icons: CC BY 4.0, Fonts: SIL OFL 1.1, Code: MIT License)\n')
    return files, {'commit': commit, 'from_github': from_gh}


def patch(files):
    for pat, old, new in PATCHES:
        names = [p for p in files if re.fullmatch(pat.replace('.', r'\.').replace('*', '[^/]*'), p)]
        hit = 0
        for p in names:
            s = files[p].decode('utf-8')
            n = s.count(old)
            if n:
                files[p] = s.replace(old, new).encode('utf-8')
                hit += n
        if hit != 1:
            raise SystemExit(f'直しが {hit} 回当たった（1 回のはず）: {pat} {old!r}（写す元が変わった＝PATCHES を見直す）')


def sha(b):
    return hashlib.sha256(b).hexdigest()


def safe_rel(p):
    """写しの中の相対の場所（/ 区切り）として書いてよい形か（SAFE_PART）"""
    parts = str(p).split('/')
    return all(SAFE_PART.fullmatch(x) and x.strip(' .') == x for x in parts)


def write(files, info):
    bad = sorted(p for p in files if not safe_rel(p))
    if bad:   # 外から来た名前に区切りの外へ出る形がある＝何も書かずに止める（人が見てから）
        raise SystemExit('書けない名前がある（写しのフォルダの外へ出る形・使えない文字）: ' + ', '.join(map(repr, bad[:10])))
    tmp = DEST.with_name(DEST.name + '.new')
    if tmp.exists():
        shutil.rmtree(tmp)
    root = tmp.resolve()
    for p, b in files.items():
        f = tmp.joinpath(*p.split('/'))
        if not f.resolve().is_relative_to(root):   # 念のため（safe_rel を通った名前は外へ出ない）
            raise SystemExit(f'写しのフォルダの外を指す名前: {p!r}')
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_bytes(b)
    for k in KEEP:
        if (DEST / k).exists():
            shutil.copy2(DEST / k, tmp / k)
    man = {'site': SITE, 'repo': REPO, 'commit': info['commit'], 'fetched': time.strftime('%Y-%m-%d'),
           'from_github': info['from_github'], 'patches': [list(x) for x in PATCHES],
           'files': {p: sha(b) for p, b in sorted(files.items())}}
    (tmp / 'MANIFEST.json').write_text(json.dumps(man, ensure_ascii=False, indent=1) + '\n', encoding='utf-8', newline='\n')
    if DEST.exists():
        shutil.rmtree(DEST)
    tmp.rename(DEST)


def check(dest=None):
    """写した物が MANIFEST.json の指紋どおりか（違う物・無い物・一覧に無い物を数える）→ 0＝同じ・1＝違う"""
    dest = Path(dest) if dest else DEST
    man = json.loads((dest / 'MANIFEST.json').read_text(encoding='utf-8'))
    bad = [p for p, h in man['files'].items() if not (dest / p).is_file() or sha((dest / p).read_bytes()) != h]
    known = set(man['files']) | {'MANIFEST.json'} | set(KEEP)
    extra = sorted(p.relative_to(dest).as_posix() for p in dest.rglob('*') if p.is_file()
                   and p.relative_to(dest).as_posix() not in known)
    print(f'{len(man["files"])} ファイル・違う物 {len(bad)}' + (': ' + ', '.join(bad[:10]) if bad else '')
          + (f'・一覧に無い物 {len(extra)}: ' + ', '.join(extra[:10]) if extra else ''))
    return 1 if bad or extra else 0


def main(argv=None):
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    ap = argparse.ArgumentParser(description='BL のリプレイアプリを replay-viewer/blreplay/ へ写す')
    ap.add_argument('--commit', help='素材の一覧を取る GitHub の版（既定は master の今の版）')
    ap.add_argument('--dry', action='store_true', help='取って直すだけで書かない（大きさを出す）')
    ap.add_argument('--check', action='store_true', help='写した物が MANIFEST.json の指紋どおりか')
    a = ap.parse_args(argv)
    if a.check:
        return check()
    files, info = collect(a.commit)
    patch(files)
    total = sum(len(b) for b in files.values())
    print(f'{len(files)} ファイル・{total / 1e6:.1f}MB・版 {info["commit"][:10]}・GitHub から取った素材 {len(info["from_github"])}')
    if not a.dry:
        write(files, info)
        print(f'書いた: {DEST}')
    return 0


if __name__ == '__main__':
    sys.exit(main())

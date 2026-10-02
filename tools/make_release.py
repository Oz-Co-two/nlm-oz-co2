"""GitHub リリースに添付する 2 つのファイルを作る: 配布 zip と update.json（アプリ内の自動更新が読む）。

使い方:  python tools/make_release.py        （先に tools/build_and_deploy.py でビルドしておく）
出力:    dist/release/NonLinearMapper-<版>.zip と dist/release/update.json

- 版は js/constants.js の APP_VERSION。ビルド結果（dist/NonLinearMapper）の版・CHANGELOG の先頭の版と一致しないと止まる。
- update.json の更新内容は CHANGELOG.md / CHANGELOG.en.md の「## v〇.〇.〇-oz」ごとの、行頭の太字（- **〜**）。
  日英で版の並びと見出しの数が違うと止まる（英語表示で抜けが出ないように）。
- できた zip を app_update.py と同じ検査（照合・展開・版の確認）に通してから終わる。
- 公開はこの後に手で行う（gh release create <タグ> <zip> <update.json> ...）。update.json を添付し忘れると、
  旧版のアプリは「最新リリースに update.json が無い」ので更新を知らせられない。
"""
import hashlib, json, re, sys, tempfile, zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import app_update  # noqa: E402

DIST = ROOT / "dist" / "NonLinearMapper"
OUT = ROOT / "dist" / "release"


def fail(msg):
    print(f"エラー: {msg}", file=sys.stderr)
    sys.exit(1)


def headline(line):
    """'- **見出し**（補足）' → '見出し'。リンク・コードの記号は外す"""
    m = re.match(r"- \*\*(.+?)\*\*", line)
    if not m:
        return None
    s = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", m.group(1))
    return s.replace("`", "").strip()


def parse_changelog(path):
    """[(版, [見出し…]), …]（書かれた順＝新しい順）"""
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        m = re.fullmatch(r"## (v\d+\.\d+\.\d+-oz)\s*", line)
        if m:
            out.append((m.group(1), []))
        elif out and (h := headline(line)):
            out[-1][1].append(h)
    if not out:
        fail(f"{path.name} に「## v〇.〇.〇-oz」の見出しがありません")
    return out


def build_notes(ver):
    ja, en = parse_changelog(ROOT / "CHANGELOG.md"), parse_changelog(ROOT / "CHANGELOG.en.md")
    if [v for v, _ in ja] != [v for v, _ in en]:
        fail(f"CHANGELOG.md と CHANGELOG.en.md の版の並びが違います\n  ja: {[v for v, _ in ja]}\n  en: {[v for v, _ in en]}")
    if ja[0][0] != ver:
        fail(f"CHANGELOG の先頭の版（{ja[0][0]}）が APP_VERSION（{ver}）と違います")
    notes = []
    for (v, hj), (_, he) in zip(ja, en):
        if len(hj) != len(he) or not hj:
            fail(f"{v}: 太字の見出しの数が日英で違うか、ありません（ja {len(hj)} / en {len(he)}）")
        notes.append({"version": v, "ja": hj, "en": he})
    return notes


def make_zip(ver):
    zpath = OUT / f"{app_update.ZIP_TOP}-{ver}.zip"
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for p in sorted(DIST.rglob("*")):
            if p.is_file():
                zf.write(p, f"{app_update.ZIP_TOP}/" + p.relative_to(DIST).as_posix())
    return zpath


def main():
    ver = app_update.read_app_version(str(ROOT))
    if not app_update.vtuple(ver):
        fail(f"APP_VERSION（{ver!r}）が v〇.〇.〇-oz の形ではありません")
    if not (DIST / app_update.EXE_NAME).is_file():
        fail(f"{DIST} にビルド結果がありません（先に python tools/build_and_deploy.py）")
    built = app_update.read_app_version(str(DIST / "_internal"))
    if built != ver:
        fail(f"ビルド結果の版（{built}）が APP_VERSION（{ver}）と違います。ビルドし直してください")
    notes = build_notes(ver)
    OUT.mkdir(parents=True, exist_ok=True)
    for p in [*OUT.glob("*.zip"), OUT / "update.json"]:   # 前回の分だけ消す（同じフォルダに置いたリリースノートは残す）
        p.unlink(missing_ok=True)
    zpath = make_zip(ver)
    data = zpath.read_bytes()
    manifest = {"name": "NonLinearMapper", "format": app_update.FORMAT, "version": ver,
                "zip": {"name": zpath.name, "sha256": hashlib.sha256(data).hexdigest(), "size": len(data)},
                "notes": notes}
    upath = OUT / "update.json"
    upath.write_text(json.dumps(manifest, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    # アプリと同じ検査に通す
    m = app_update.check_manifest(upath.read_bytes())
    assert not m["manual"] and m["zip"]["size"] == len(data)
    with tempfile.TemporaryDirectory() as td:
        app_update.extract_release(str(zpath), str(Path(td) / "new"), ver)
    print(f"作成しました（{ver}）:")
    print(f"  {zpath.relative_to(ROOT)}  {len(data) / 1048576:.1f}MB  sha256={manifest['zip']['sha256']}")
    print(f"  {upath.relative_to(ROOT)}  更新内容 {len(notes)} 版分")
    print("公開する時は、zip と update.json の両方をリリースに添付する:")
    print(f"  gh release create {ver} \"{zpath.relative_to(ROOT).as_posix()}\" \"{upath.relative_to(ROOT).as_posix()}\" --verify-tag --latest --notes-file <ノート>")


if __name__ == "__main__":
    main()

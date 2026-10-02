"""本体の自動更新（app_update.py）の自己テスト。ネットには繋がず、ローカルの偽の配布元で通しで確かめる。

使い方:  python tools/update_test.py
確かめること: 更新内容の絞り込み（今の版より新しい分だけ）/ ダウンロードと SHA-256 照合 / 改ざん・zip slip の拒否 /
  差し替え（利用者のデータに触らない・1 世代の退避）/ 失敗時に元へ戻す / 想定外の場所からの差し替えの拒否 /
  更新後の片付け / CHANGELOG の日英の見出しの読み取り（tools/make_release.py）
"""
import hashlib, http.server, io, json, os, shutil, sys, tempfile, threading, time, zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
import app_update as au  # noqa: E402
import make_release  # noqa: E402

FAILS = []
BOXES = []
au._msgbox = BOXES.append   # テスト中にメッセージボックスを出さない


def check(cond, what):
    print(("  ok   " if cond else "  NG   ") + what)
    if not cond:
        FAILS.append(what)


def write(p, text):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def make_app(d, ver, exe=b"EXE"):
    """配布フォルダの形（exe・_internal・案内文）を作る"""
    d.mkdir(parents=True, exist_ok=True)
    (d / au.EXE_NAME).write_bytes(exe + ver.encode())
    write(d / "_internal" / "js" / "constants.js", f"export const APP_VERSION = '{ver}';\n")
    write(d / "_internal" / "lib" / "x.dll", ver)
    write(d / "はじめにお読みください.txt", ver)


def make_zip(ver, extra=None):
    buf = io.BytesIO()
    with tempfile.TemporaryDirectory() as td:
        src = Path(td) / "app"
        make_app(src, ver, b"NEW")
        with zipfile.ZipFile(buf, "w") as zf:
            for p in sorted(src.rglob("*")):
                if p.is_file():
                    zf.write(p, "NonLinearMapper/" + p.relative_to(src).as_posix())
            if extra:
                zf.writestr(extra, "evil")
    return buf.getvalue()


class Site:
    """偽の配布元（update.json と zip を返す）"""
    def __init__(self):
        self.files = {}
        site = self

        class H(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                body = site.files.get(self.path)
                if body is None:
                    self.send_response(404); self.end_headers(); return
                self.send_response(200); self.send_header("Content-Length", str(len(body))); self.end_headers()
                self.wfile.write(body)

            def log_message(self, *a):
                pass
        self.httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{self.httpd.server_address[1]}"
        au.UPDATE_URL = base + "/latest/update.json"
        au.ZIP_URL = base + "/download/{tag}/{name}"

    def publish(self, ver, zdata, notes, sha=None, size=None):
        name = f"NonLinearMapper-{ver}.zip"
        self.files[f"/download/{ver}/{name}"] = zdata
        self.files["/latest/update.json"] = json.dumps({
            "name": "NonLinearMapper", "format": 1, "version": ver,
            "zip": {"name": name, "sha256": sha or hashlib.sha256(zdata).hexdigest(), "size": size or len(zdata)},
            "notes": notes}).encode()


NOTES = [{"version": "v1.4.0-oz", "ja": ["新機能A"], "en": ["Feature A"]},
         {"version": "v1.3.1-oz", "ja": ["修正B"], "en": ["Fix B"]},
         {"version": "v1.3.0-oz", "ja": ["今の版"], "en": ["current"]},
         {"version": "v1.2.0-oz", "ja": ["古い版"], "en": ["old"]}]


def wait_job(up, timeout=20):
    t0 = time.time()
    while up.job["state"] in ("download", "extract") and time.time() - t0 < timeout:
        time.sleep(0.05)
    return up.job


def main():
    site = Site()
    with tempfile.TemporaryDirectory() as td:
        target = Path(td) / "NLM"
        make_app(target, "v1.3.0-oz")
        write(target / "config" / "settings.json", "{\"mine\":1}")
        write(target / "asset" / "clip.nlmclip", "mine")
        write(target / "plugins" / "rating" / "current.json", "mine")
        (target / "_previous_v0.9.0-oz").mkdir()   # 古い退避（1 世代だけ残すので消える）
        up = au.Updater(str(target / "_internal"), str(target), frozen=True)

        print("確認（check）")
        zdata = make_zip("v1.4.0-oz")
        site.publish("v1.4.0-oz", zdata, NOTES)
        j = up.check()
        check(j["newer"] and j["latest"] == "v1.4.0-oz" and j["current"] == "v1.3.0-oz", "新しい版があると分かる")
        check([n["version"] for n in j["notes"]] == ["v1.4.0-oz", "v1.3.1-oz"], "更新内容は今の版より新しい分だけ（新しい順）")
        check(j["auto"] == "ok" and j["size"] == len(zdata), "自動更新できる・サイズ")
        check(au.Updater(str(target / "_internal"), str(target), frozen=False).check()["auto"] == "notExe", "exe 版でなければ自動更新しない")

        print("ダウンロード（改ざん・zip slip）")
        site.publish("v1.4.0-oz", zdata, NOTES, sha="0" * 64)
        up.start_download(); job = wait_job(up)
        check(job["state"] == "error" and job["error"] == "hash", "SHA-256 が違えば中止")
        check(not (target / "_update" / "new").exists(), "中止したら展開物を残さない")
        bad = make_zip("v1.4.0-oz", extra="NonLinearMapper/../../evil.txt")
        site.publish("v1.4.0-oz", bad, NOTES)
        up.start_download(); job = wait_job(up)
        check(job["state"] == "error" and job["error"] == "badZip" and not (Path(td) / "evil.txt").exists(), "フォルダ外へ出る名前の zip は拒否")
        site.publish("v1.4.0-oz", make_zip("v1.5.0-oz"), NOTES)
        up.start_download(); job = wait_job(up)
        check(job["state"] == "error" and job["error"] == "badZip", "zip の中身の版が update.json と違えば拒否")

        print("ダウンロード（正常）")
        site.publish("v1.4.0-oz", zdata, NOTES)
        up.start_download(); job = wait_job(up)
        new_dir = target / "_update" / "new" / "NonLinearMapper"
        check(job["state"] == "ready" and (new_dir / au.EXE_NAME).is_file(), "照合して _update/new へ展開")
        check(not list((target / "_update").glob("*.part")), "ダウンロード途中のファイルを残さない")

        print("差し替え（想定外の場所からは拒否）")
        other = Path(td) / "other" / "NonLinearMapper"
        make_app(other, "v1.4.0-oz")
        args = ["x", "--apply-update", "--target", str(target), "--pid", "0", "--lang", "ja"]
        check(au.apply_main(args, src=str(other), launch=False) is False, "_update/new 以外からの差し替えは拒否")
        check(au.read_app_version(str(target / "_internal")) == "v1.3.0-oz", "拒否した時は何も変えない")

        print("差し替え（失敗したら元へ戻す）")
        write(new_dir / "_internal" / "js" / "constants.js", "broken")   # 版が読めない展開物は使わない
        check(au.apply_main(args, src=str(new_dir), launch=False) is False, "版が読めない展開物は拒否")
        write(new_dir / "_internal" / "js" / "constants.js", "export const APP_VERSION = 'v1.4.0-oz';\n")
        real_copy2 = shutil.copy2

        def bad_copy2(s, d, *a, **k):   # 最後の案内文のコピーで失敗させる（exe・_internal は入れた後）
            if str(s).endswith(".txt"):
                raise OSError("disk full")
            return real_copy2(s, d, *a, **k)
        au.shutil.copy2 = bad_copy2
        try:
            BOXES.clear()
            check(au.apply_main(args, src=str(new_dir), launch=False) is False and BOXES, "コピーの途中で失敗")
        finally:
            au.shutil.copy2 = real_copy2
        check(au.read_app_version(str(target / "_internal")) == "v1.3.0-oz"
              and (target / au.EXE_NAME).read_bytes() == b"EXEv1.3.0-oz"
              and (target / "はじめにお読みください.txt").read_text(encoding="utf-8") == "v1.3.0-oz", "元の版に戻っている")
        (target / "_previous_v0.9.0-oz").mkdir(exist_ok=True)   # 「退避は 1 世代だけ」の確認用に置き直す

        print("差し替え（正常）")
        BOXES.clear()
        ok = au.apply_main(args, src=str(new_dir), launch=False)
        check(ok and not BOXES, "成功・メッセージなし")
        check(au.read_app_version(str(target / "_internal")) == "v1.4.0-oz"
              and (target / au.EXE_NAME).read_bytes() == b"NEWv1.4.0-oz"
              and (target / "はじめにお読みください.txt").read_text(encoding="utf-8") == "v1.4.0-oz", "exe・_internal・案内文が新しい版")
        check((target / "config" / "settings.json").read_text() == "{\"mine\":1}"
              and (target / "asset" / "clip.nlmclip").read_text() == "mine"
              and (target / "plugins" / "rating" / "current.json").read_text() == "mine", "利用者のデータはそのまま")
        bk = target / "_previous_v1.3.0-oz"
        check(au.read_app_version(str(bk / "_internal")) == "v1.3.0-oz" and (bk / au.EXE_NAME).is_file(), "前の版を _previous_v1.3.0-oz に退避")
        check(not (target / "_previous_v0.9.0-oz").exists(), "退避は 1 世代だけ")

        print("更新後の起動（片付け）")
        up2 = au.Updater(str(target / "_internal"), str(target), frozen=True)
        au.startup(up2)
        check(up2.just_updated == {"from": "v1.3.0-oz", "to": "v1.4.0-oz"}, "「更新しました」用の版")
        for _ in range(50):
            if not (target / "_update").exists():
                break
            time.sleep(0.1)
        check(not (target / "_update").exists(), "_update/ を消す")
        check(up2.check()["newer"] is False, "更新後は最新")

    print("CHANGELOG（tools/make_release.py）")
    ja, en = make_release.parse_changelog(ROOT / "CHANGELOG.md"), make_release.parse_changelog(ROOT / "CHANGELOG.en.md")
    check([v for v, _ in ja] == [v for v, _ in en], "日英で版の並びが同じ")
    check(all(len(a) == len(b) and a for (_, a), (_, b) in zip(ja, en)), "各版の見出しの数が日英で同じ")
    check(make_release.headline("- **画像付き`x`を追加**（[a](b)）") == "画像付きxを追加", "見出しから記号を外す")
    site.httpd.shutdown()
    print("\n" + ("すべて OK" if not FAILS else f"NG {len(FAILS)} 件"))
    sys.exit(1 if FAILS else 0)


if __name__ == "__main__":
    main()

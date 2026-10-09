"""serve.py のAPI（設定保存・翻訳の合成・アセット操作・開くファイル・プラグイン/更新の入口）"""
import json
import os
import sys
from pathlib import Path
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parent))
import unitpy_helpers as H


def test_settings_save_goes_to_data_dir(t):
    '''__settings/save はデータフォルダの config/settings.json に書く（本体フォルダには書かない）'''
    s = H.server()
    st, obj = H.post_json("/__settings/save", {"data": {"bsnm_x": "日本語", "n": 3}})
    t.eq((st, obj), (200, {"ok": True}), "応答")
    p = Path(s.data_dir) / "config" / "settings.json"
    t.ok(p.is_file(), "データフォルダに作られる")
    t.eq(json.loads(p.read_text(encoding="utf-8")), {"bsnm_x": "日本語", "n": 3}, "中身")
    t.eq(os.path.normcase(s.serve.SETTINGS_FILE), os.path.normcase(str(p)), "SETTINGS_FILE")
    t.ok(os.path.normcase(s.serve.DATA_DIR) != os.path.normcase(str(H.ROOT)), "DATA_DIRは本体と別")


def test_settings_save_never_half_written(t):
    '''保存の最中に読んでも、書きかけ（空・途中まで）の settings.json は返らない。保存は書き終えてから置き換える（一時ファイルは残らない）。
    以前は空にしてから書いていたため、保存と同時の読み込みが空のファイルを受け取ることがあった（全テストで1回・2026-10-09）'''
    import threading
    s = H.server()
    data = {f"bsnm_k{i}": "値" * 40 for i in range(400)}   # 数十KB＝書いている途中を読みやすくする
    bad, stop = [], threading.Event()

    def reader():
        while not stop.is_set():
            st, _, body = H.req("GET", "/config/settings.json")
            try:
                json.loads(body)
            except Exception:
                bad.append((st, body[:30]))

    th = [threading.Thread(target=reader) for _ in range(3)]
    for x in th:
        x.start()
    try:
        for i in range(60):
            data["n"] = i
            st, obj = H.post_json("/__settings/save", {"data": data})
            if st != 200:
                bad.append(("save", st, obj))
    finally:
        stop.set()
        for x in th:
            x.join()
    t.eq(bad[:3], [], f"書きかけを読んだ・保存に失敗した回数 {len(bad)}")
    p = Path(s.data_dir) / "config" / "settings.json"
    t.eq(json.loads(p.read_text(encoding="utf-8"))["n"], 59, "最後に保存した中身")
    t.eq(sorted(x.name for x in p.parent.iterdir()), ["settings.json"], "一時ファイルは残らない")


def test_settings_save_bad_json(t):
    '''壊れたJSON本体は500のエラー応答（サーバーは落ちない）'''
    st, _, _ = H.req("POST", "/__settings/save", headers={"X-NLM-Request": "1"}, body=b"{not json")
    t.eq(st, 500, "status")
    st, _, _ = H.req("GET", "/editor.html")
    t.eq(st, 200, "その後も動く")


def _lang_seed(name="ja.json"):
    return json.loads((H.ROOT / "lang" / name).read_text(encoding="utf-8"))


def test_lang_merge_overrides_by_key(t):
    '''/lang/*.json は同梱版を土台に、データフォルダ側の版をキー単位で上書きして返す'''
    s = H.server()
    seed = _lang_seed()
    keys = list(seed)
    k1, k2 = keys[0], keys[1]
    d = Path(s.data_dir) / "lang"
    d.mkdir(exist_ok=True)
    (d / "ja.json").write_text(json.dumps({k1: "上書き訳", "user.only": "利用者の独自キー"}, ensure_ascii=False), encoding="utf-8")
    st, _, body = H.req("GET", "/lang/ja.json")
    t.eq(st, 200, "status")
    got = json.loads(body)
    t.eq(got[k1], "上書き訳", "上書きされる")
    t.eq(got[k2], seed[k2], "上書きしていないキーは同梱版のまま（旧版の翻訳でも欠けない）")
    t.eq(got["user.only"], "利用者の独自キー", "利用者のキーも残る")
    t.eq(len(got), len(seed) + 1, "キー数")


def test_lang_only_seed_and_only_user(t):
    '''データフォルダ側に無い言語は同梱版のみ、同梱に無い言語はデータフォルダ側のみ、どちらも無ければ404'''
    s = H.server()
    d = Path(s.data_dir) / "lang"
    d.mkdir(exist_ok=True)
    (d / "en.json").unlink(missing_ok=True)
    st, _, body = H.req("GET", "/lang/en.json")
    t.eq(json.loads(body), _lang_seed("en.json"), "同梱のみ")
    (d / "xx-user.json").write_text('{"a":"b"}', encoding="utf-8")
    st, _, body = H.req("GET", "/lang/xx-user.json")
    t.eq((st, json.loads(body)), (200, {"a": "b"}), "利用者のみ")
    st, _, _ = H.req("GET", "/lang/nonexistent-zz.json")
    t.eq(st, 404, "どちらも無い")


def test_lang_broken_user_file_ignored(t):
    '''データフォルダ側の翻訳が壊れていても同梱版を返す'''
    s = H.server()
    d = Path(s.data_dir) / "lang"
    d.mkdir(exist_ok=True)
    (d / "ja.json").write_text("{壊れた", encoding="utf-8")
    st, _, body = H.req("GET", "/lang/ja.json")
    t.eq(st, 200, "status")
    t.eq(json.loads(body), _lang_seed(), "同梱版")


def test_lang_name_restricted(t):
    '''/lang/ の合成は英数字・_-の名前の .json だけ。..で抜けた先はルート内の実ファイルをそのまま返す（合成されない）'''
    st, _, body = H.req("GET", "/lang/..%2fconfig%2fsettings.default.json")
    t.eq(st, 200, "ルート内に正規化される")
    t.eq(body, (H.ROOT / "config" / "settings.default.json").read_bytes(), "合成されず実ファイルそのまま")
    st, _, _ = H.req("GET", "/lang/..%5Cconfig%5Csettings.default.json")
    t.eq(st, 404, "バックスラッシュ")


def test_asset_save_rename_delete(t):
    '''アセットの保存・同名の連番付与・改名・削除。ファイルはデータフォルダのasset/に出来る'''
    s = H.server()
    ad = Path(s.data_dir) / "asset"
    st, obj = H.post_json("/__asset/save", {"name": "テスト", "data": {"name": "テスト", "v": 1}})
    t.eq((st, obj), (200, {"ok": True, "name": "テスト.nlmclip"}), "保存")
    t.ok((ad / "テスト.nlmclip").is_file(), "ファイルが出来る")
    st, obj = H.post_json("/__asset/save", {"name": "テスト", "data": {"v": 2}})
    t.eq(obj["name"], "テスト (2).nlmclip", "同名は連番（黙って上書きしない）")
    t.eq(json.loads((ad / "テスト.nlmclip").read_text(encoding="utf-8"))["v"], 1, "元は無事")
    st, obj = H.post_json("/__asset/rename", {"from": "テスト (2).nlmclip", "to": "改名後"})
    t.eq(obj, {"ok": True, "name": "改名後.nlmclip"}, "改名")
    t.ok((ad / "改名後.nlmclip").is_file() and not (ad / "テスト (2).nlmclip").exists(), "改名の結果")
    t.eq(json.loads((ad / "改名後.nlmclip").read_text(encoding="utf-8"))["name"], "改名後", "nameも更新")
    st, obj = H.post_json("/__asset/rename", {"from": "改名後.nlmclip", "to": "テスト"})
    t.eq((obj.get("ok"), obj.get("error")), (False, "exists"), "別クリップと同名への改名は拒否（文言ではなく種類を返し、JSが表示言語で訳す）")
    st, obj = H.post_json("/__asset/delete", {"name": "改名後.nlmclip"})
    t.eq(obj, {"ok": True}, "削除")
    t.ok(not (ad / "改名後.nlmclip").exists(), "消えた")
    st, _, body = H.req("GET", "/asset/" + quote("テスト.nlmclip"))
    t.eq((st, json.loads(body)["v"]), (200, 1), "GETで取れる")
    H.post_json("/__asset/delete", {"name": "テスト.nlmclip"})


def test_asset_name_sanitized(t):
    '''アセット名の ..・区切り・ドライブ名はファイル名だけに潰され、asset/の外へ出ない'''
    s = H.server()
    ad = Path(s.data_dir) / "asset"
    outside = Path(s.data_dir)
    before = set(os.listdir(outside))
    for nm in ("..\\..\\evil", "../../evil", "C:\\evil", "..", "a/b/c"):
        st, obj = H.post_json("/__asset/save", {"name": nm, "data": {}})
        t.eq(st, 200, nm)
        got = obj["name"]
        t.ok(("/" not in got) and ("\\" not in got) and ":" not in got, f"名前に区切り: {got}")
        t.ok((ad / got).is_file(), f"asset/内に作られる: {nm} -> {got}")
    t.eq(set(os.listdir(outside)) - before, set(), "データフォルダ直下に何も増えていない")
    victim = Path(s.data_dir) / "victim.txt"
    victim.write_text("x")
    H.post_json("/__asset/delete", {"name": "..\\victim.txt"})
    H.post_json("/__asset/delete", {"name": "../victim.txt"})
    t.ok(victim.exists(), "asset/の外のファイルは消せない")


def test_openarg(t):
    '''__openarg: NLM_OPEN_FILE が無ければ ok:false、あれば中身を返す。保存は.bak付きで書き戻す'''
    s = H.server()
    st, _, body = H.req("GET", "/__openarg")
    t.eq(json.loads(body), {"ok": False}, "未指定")
    st, obj = H.post_json("/__openarg/save", {"text": "x"})
    t.eq(st, 400, "未指定の保存は400")
    p = Path(s.data_dir) / "open.nlmf"
    p.write_text('{"v":1}', encoding="utf-8")
    old = s.serve.OPEN_FILE
    s.serve.OPEN_FILE = str(p)
    try:
        st, _, body = H.req("GET", "/__openarg")
        o = json.loads(body)
        t.eq((o["ok"], o["text"], o["name"]), (True, '{"v":1}', "open.nlmf"), "読み込み")
        st, obj = H.post_json("/__openarg/save", {"text": '{"v":2}'})
        t.eq(obj, {"ok": True, "name": "open.nlmf"}, "保存")
        t.eq(p.read_text(encoding="utf-8"), '{"v":2}', "書き戻し")
        t.eq(Path(str(p) + ".bak").read_text(encoding="utf-8"), '{"v":1}', "1世代バックアップ")
    finally:
        s.serve.OPEN_FILE = old


def test_rating_and_update_endpoints_guarded(t):
    '''__rating/__update のPOSTもヘッダー必須。知らない操作は404。status は200で形が合う'''
    st, _, _ = H.req("POST", "/__rating/status", body=b"{}")
    t.eq(st, 403, "rating ヘッダー無し")
    st, _, _ = H.req("POST", "/__update/status", body=b"{}")
    t.eq(st, 403, "update ヘッダー無し")
    st, obj = H.post_json("/__rating/status", {})
    t.eq(st, 200, "rating status")
    t.eq(obj["current"], None, "未導入")
    t.eq(obj["installed"], [], "未導入の一覧")
    st, obj = H.post_json("/__rating/bogus", {})
    t.eq(st, 404, "rating 不明")
    st, obj = H.post_json("/__update/bogus", {})
    t.eq(st, 404, "update 不明")
    st, obj = H.post_json("/__update/status", {})
    t.eq(st, 200, "update status")
    t.ok(isinstance(obj, dict), "辞書")


def test_rating_use_unknown_version(t):
    '''__rating/use は取り込み済みでない版を拒否する（パスのような値も）'''
    for v in ("9.9.9", "../../x", "", None):
        st, obj = H.post_json("/__rating/use", {"version": v})
        t.eq((st, obj.get("ok"), obj.get("error")), (200, False, "notInstalled"), f"version={v!r}")


def test_rating_measure_validation(t):
    '''__rating/measure は不正な入力（ファイル数・名前・型）を badInput で拒否し、未導入なら notInstalled'''
    ok2 = [{"name": "Info.dat", "text": "{}"}, {"name": "ExpertStandard.dat", "text": "{}"}]
    cases = [
        ({"files": []}, "badInput"),
        ({"files": "x"}, "badInput"),
        ({"files": ok2[:1]}, "badInput"),
        ({"files": [{"name": "../x.dat", "text": "{}"}, ok2[1]]}, "badInput"),
        ({"files": [{"name": "x.exe", "text": "{}"}, ok2[1]]}, "badInput"),
        ({"files": [{"name": "a.dat", "text": 5}, ok2[1]]}, "badInput"),
        ({"files": ok2}, "notInstalled"),
    ]
    for body, code in cases:
        st, obj = H.post_json("/__rating/measure", body)
        t.eq(obj.get("error"), code, json.dumps(body, ensure_ascii=False)[:80])


def test_convert_ogg_endpoint(t):
    '''__convert/toOgg: ffmpegが無ければ ffmpeg-not-found のJSON。あれば壊れた入力で ok:false（変換失敗）'''
    import shutil
    st, hd, body = H.req("POST", "/__convert/toOgg?ext=mp3", headers={"X-NLM-Request": "1"}, body=b"not audio")
    if shutil.which("ffmpeg"):
        t.eq(st, 200, "status")
        t.eq(json.loads(body).get("ok"), False, "壊れた音声は失敗")
    else:
        t.eq(json.loads(body), {"ok": False, "error": "ffmpeg-not-found"}, "ffmpeg無し")


def test_convert_ogg_error_with_large_body(t):
    '''__convert/toOgg: 数MBの音源を送っても、変換しない時のエラー（ffmpeg無し・切り貼り表がおかしい）の応答が届く'''
    # 以前は音源を読まずに応答して閉じていたため、Windows では残ったデータのせいで接続がリセットされ、
    # 応答が届かずに通信エラーになっていた（小さい音源だとタイミング次第で通る）。ffmpeg の有無は serve 側の which を差し替えて作る
    import types
    s = H.server()
    big = b"\0" * (8 * 1024 * 1024)
    real = s.serve.shutil
    try:
        for which, query, want in ((None, "ext=mp3", "ffmpeg-not-found"),
                                   ("ffmpeg", "ext=wav&segs=" + quote(json.dumps([[3, 2, 0]])), "bad-segs")):
            s.serve.shutil = types.SimpleNamespace(which=lambda name, w=which: w)
            st, hd, body = H.req("POST", "/__convert/toOgg?" + query, headers={"X-NLM-Request": "1"}, body=big)
            t.eq((st, json.loads(body)), (200, {"ok": False, "error": want}), want)
    finally:
        s.serve.shutil = real


def test_post_reply_with_unread_body(t):
    '''本体を使わない応答（拒否・不明な操作・本体の要らない操作）でも、数MBの本体を送った時に応答が届く'''
    # 本体を読まずに応答して閉じると、Windows では残ったデータのせいで接続がリセットされ応答が届かないことがある
    # （小さい本体だとタイミング次第で、全テストでたまに __update/status が ConnectionAbortedError になっていた）
    big = b"\0" * (8 * 1024 * 1024)
    for path, hdr, want in (("/__update/status", {"X-NLM-Request": "1"}, 200),
                            ("/__update/bogus", {"X-NLM-Request": "1"}, 404),
                            ("/__rating/status", {"X-NLM-Request": "1"}, 200),
                            ("/__rating/bogus", {"X-NLM-Request": "1"}, 404),
                            ("/__nothing", {"X-NLM-Request": "1"}, 404),
                            ("/__update/status", {}, 403)):
        st, _, _ = H.req("POST", path, headers=hdr, body=big)
        t.eq(st, want, path + (" ヘッダー無し" if not hdr else ""))


def test_post_broken_content_length(t):
    '''Content-Length が数値でない・本体より長い・とても大きい要求にも応答が返る（拒否する要求の本体は上限を超えたら読まない）'''
    import time
    ok = {"X-NLM-Request": "1"}
    for hdr, want, label in (({**ok, "Content-Length": "abc"}, 200, "数値でない"),
                             ({"Content-Length": "abc"}, 403, "数値でない・ヘッダー無し"),
                             ({**ok, "Content-Length": "100"}, 200, "本体より長い（届かない分は待ち切りで諦める）"),
                             ({"Content-Length": str(512 * 1024 * 1024)}, 403, "とても大きい・ヘッダー無し（読まずに拒否）")):
        t0 = time.time()
        st, _, _ = H.req("POST", "/__update/status", headers=hdr, body=None)
        t.eq(st, want, label)
        t.ok(time.time() - t0 < 5, label + ": すぐ返る")

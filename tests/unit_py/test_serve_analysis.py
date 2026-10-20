"""曲の解析（serve.py の /__analysis/*・song_analysis/）: 音源の保存・テンポ・構成・状態・取り消し・エラー・アクセス制御と、
NLM が渡す目盛り（at）で tools/analyze_structure.py と同じ特徴になること。
音源はテスト用のクリック音（tools/fixtures/basic.wav・120BPM・16秒）と、その場で作る合成音（著作物でない）。"""
import hashlib
import io
import json
import os
import sys
import tempfile
import time
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import unitpy_helpers as H

WAV = H.ROOT / "tools" / "fixtures" / "basic.wav"
SPEC_TEMPO_KEYS = {"bpm", "raw_bpm", "lead_ms", "alt_lead_ms", "low_offbeat", "offbeat_ratio", "steps", "drift_pct", "drift",
                   "alt", "block_mad_ms", "n_beats", "family", "slope_sig", "slope", "resid_mad_ms", "version"}
NAME_KEYS = {"intro", "a", "b", "chorus", "interlude", "c", "outro", ""}


def _libs():
    """解析の部品（.venv-build に足した librosa・scipy・scikit-learn）。無ければ失敗にする（exe のビルドにも要るため）"""
    try:
        import librosa  # noqa: F401
        import numpy as np
        import sklearn  # noqa: F401
        return np
    except ImportError as e:
        raise AssertionError(f"解析の部品が入っていません（.venv-build に librosa・scipy・scikit-learn を入れる）: {e}")


def upload(data, ext="wav", **kw):
    st, _, b = H.req("POST", "/__analysis/upload?ext=" + ext, body=data,
                     headers={"X-NLM-Request": "1", "Content-Type": "application/octet-stream"}, **kw)
    try:
        return st, json.loads(b.decode("utf-8"))
    except Exception:
        return st, None


def start(kind, obj):
    st, r = H.post_json("/__analysis/" + kind, obj)
    assert st == 200 and r and r.get("ok"), f"{kind} を始められません: {st} {r}"
    return r["job"]


def wait(job, timeout=180):
    end = time.time() + timeout
    while time.time() < end:
        st, r = H.post_json("/__analysis/status", {"job": job})
        assert st == 200 and r and r.get("ok"), f"状態を取れません: {st} {r}"
        if r["state"] in ("done", "error"):
            return r
        time.sleep(0.1)
    raise AssertionError(f"解析が {timeout} 秒で終わりません（最後の状態 {r}）")


def grid_for(bpm, lead_ms, dur, extra=4):
    """画面が渡す形の目盛り（拍 0, 0.25, … ごとの元の音源の秒。音の無い所は null）"""
    n = int((dur + lead_ms / 1000) * bpm / 60 * 4) + extra
    at = []
    for i in range(n):
        a = (i / 4) * 60 / bpm - lead_ms / 1000
        at.append(a if 0 <= a < dur else None)
    return {"bpm": bpm, "leadMs": lead_ms, "sub": 4, "at": at}


def synth_wav(seconds, seed=0, bpm=120.0, sr=22050):
    """合成音の WAV のバイト列: 拍ごとのクリックと、8拍ごとに入れ替わる和音（A B A B C A …）。seed で中身を変える"""
    np = _libs()
    rng = np.random.default_rng(seed)
    t = np.arange(int(seconds * sr)) / sr
    beat = 60 / bpm
    chords = [(261.6, 329.6, 392.0), (220.0, 277.2, 329.6), (174.6, 220.0, 261.6)]
    order = [0, 1, 0, 1, 2, 0, 1, 0]
    y = np.zeros_like(t)
    sec = (t // (8 * beat)).astype(int)
    for k, ch in enumerate(chords):
        m = np.array([order[s % len(order)] == k for s in sec])
        for f in ch:
            y += m * 0.12 * np.sin(2 * np.pi * f * (1 + 0.001 * seed) * t)
    ph = (t % beat) / beat
    y += 0.6 * np.exp(-ph * beat * 60) * rng.standard_normal(len(t)) * 0.5
    y = np.clip(y, -1, 1)
    bio = io.BytesIO()
    with wave.open(bio, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes((y * 32000).astype("<i2").tobytes())
    return bio.getvalue()


def test_upload_same_content_same_id(t):
    '''音源の id は中身の SHA-256。同じ中身なら拡張子が違っても同じ id で、保存し直さない（ファイルは1つ）。
    拡張子は英数字だけにし、知らない物は .bin（一時フォルダの外には書かない）'''
    s = H.server()
    data = WAV.read_bytes()
    st, r = upload(data, "wav")
    t.eq((st, r), (200, {"ok": True, "audioId": hashlib.sha256(data).hexdigest()}), "1回目")
    aid = r["audioId"]
    adir = Path(s.serve.ANALYSIS.root)
    p = next(adir.glob(aid + ".*"))
    mt = p.stat().st_mtime_ns
    st, r = upload(data, "WAV")
    t.eq(r, {"ok": True, "audioId": aid}, "2回目（拡張子の大文字小文字が違う）")
    t.eq([x.name for x in adir.glob(aid + ".*")], [aid + ".wav"], "ファイルは1つ")
    t.eq(p.stat().st_mtime_ns >= mt, True, "使った時刻は新しくなる（片付けの目安）")
    other = data + b"\0"
    st, r = upload(other, "..%2F..%2Fevil")
    oid = hashlib.sha256(other).hexdigest()
    t.eq(r, {"ok": True, "audioId": oid}, "おかしな拡張子")
    t.eq([x.name for x in adir.glob(oid + ".*")], [oid + ".bin"], "知らない拡張子は .bin")
    t.eq(sorted(x.name for x in adir.iterdir() if x.name.endswith(".part")), [], "書きかけは残らない")


def test_upload_errors(t):
    '''空の本体は bad-audio、上限を超える本体は too-large（本体を読み捨ててから答える＝応答が届く）。その後もサーバーは動く'''
    s = H.server()
    st, r = upload(b"")
    t.eq((st, r), (200, {"ok": False, "error": "bad-audio"}), "空")
    old = s.serve.ANALYSIS_MAX_UPLOAD
    s.serve.ANALYSIS_MAX_UPLOAD = 1000
    try:
        st, r = upload(b"x" * 200000)
    finally:
        s.serve.ANALYSIS_MAX_UPLOAD = old
    t.eq((st, r), (200, {"ok": False, "error": "too-large"}), "上限超え")
    st, r = H.post_json("/__analysis/status", {"job": "nope"})
    t.eq((st, r), (200, {"ok": False, "error": "unknown-job"}), "その後も答える")


def test_needs_header_and_token(t):
    '''解析の API も POST の約束どおり: X-NLM-Request が無い・合言葉が無い／違う要求は 403（音源は保存しない）'''
    s = H.server()
    data = b"RIFF-not-really-audio-" + os.urandom(64)
    st, _, _ = H.req("POST", "/__analysis/upload?ext=wav", body=data)
    t.eq(st, 403, "X-NLM-Request なし")
    st, _ = upload(data, token=False)
    t.eq(st, 403, "合言葉なし")
    st, _ = upload(data, token="wrong")
    t.eq(st, 403, "合言葉が違う")
    adir = Path(s.serve.ANALYSIS.root)
    t.eq(list(adir.glob(hashlib.sha256(data).hexdigest() + ".*")) if adir.exists() else [], [], "保存されない")
    for path in ("/__analysis/status", "/__analysis/tempo", "/__analysis/structure", "/__analysis/cancel"):
        st, _ = H.post_json(path, {"job": "x"}, token=False)
        t.eq(st, 403, path + " 合言葉なし")
    st, r = H.post_json("/__analysis/unknown", {})
    t.eq((st, r), (404, {"ok": False, "error": "unknown endpoint"}), "知らない口")


def test_bad_requests(t):
    '''知らない音源・仕事・壊れた JSON・おかしな目盛りは、それぞれの種類のエラー（文言ではなく種類）'''
    st, r = H.post_json("/__analysis/tempo", {"audioId": "0" * 64})
    t.eq(r, {"ok": False, "error": "unknown-audio"}, "知らない音源")
    st, r = H.post_json("/__analysis/tempo", {"audioId": "../../config/settings"})
    t.eq(r, {"ok": False, "error": "unknown-audio"}, "id でない文字列")
    st, r = H.post_json("/__analysis/cancel", {"job": "0123"})
    t.eq(r, {"ok": False, "error": "unknown-job"}, "知らない仕事の取り消し")
    st, _, b = H.req("POST", "/__analysis/status", headers={"X-NLM-Request": "1"}, body=b"{not json")
    t.eq((st, json.loads(b)), (200, {"ok": False, "error": "bad-request"}), "壊れた JSON")
    st, _, b = H.req("POST", "/__analysis/status", headers={"X-NLM-Request": "1"}, body=b"[1,2]")
    t.eq(json.loads(b), {"ok": False, "error": "bad-request"}, "JSON がオブジェクトでない")
    st, r = upload(WAV.read_bytes())
    aid = r["audioId"]
    good = grid_for(120.0, 0.0, 16.0)
    bad = {
        "目盛りが無い": None,
        "BPM が0": {**good, "bpm": 0},
        "BPM が文字": {**good, "bpm": "120"},
        "sub が4でない": {**good, "sub": 2},
        "at が空": {**good, "at": []},
        "at が全部 null": {**good, "at": [None] * 10},
        "at に文字": {**good, "at": [0.0, "1"]},
        "at に真偽値": {**good, "at": [0.0, True]},
        "無音追加が文字": {**good, "leadMs": "x"},
    }
    for label, g in bad.items():
        st, r = H.post_json("/__analysis/structure", {"audioId": aid, "grid": g})
        t.eq(r, {"ok": False, "error": "bad-grid"}, label)


def test_tempo_click_track(t):
    '''テンポ: 120BPM のクリック音から BPM 120。結果は tempo_leadin.estimate() と同じ項目＋version。
    同じ音源をもう一度頼むと、覚えた結果をすぐ返す'''
    _libs()
    st, r = upload(WAV.read_bytes())
    aid = r["audioId"]
    r = wait(start("tempo", {"audioId": aid}))
    t.eq((r["state"], r["stage"], r["progress"], r["error"]), ("done", "tempo", 1.0, None), "状態")
    res = r["result"]
    t.eq(sorted(SPEC_TEMPO_KEYS - set(res)), [], "項目が揃う")
    t.eq((res["bpm"], res["version"], "error" in res), (120.0, 1, False), "BPM・版")
    t.ok(0 <= res["lead_ms"] < 500 and 0 <= res["alt_lead_ms"] < 500, f"無音追加 {res['lead_ms']}・候補B {res['alt_lead_ms']}")
    t.ok(isinstance(res["drift"], list) and isinstance(res["steps"], list), "揺れ・段差はリスト")
    job2 = start("tempo", {"audioId": aid})
    st, r2 = H.post_json("/__analysis/status", {"job": job2})
    t.eq((r2["state"], r2["result"]), ("done", res), "2回目は覚えた結果")


def test_structure_result_shape(t):
    '''構成: 画面が渡す目盛りで解析し、取り決めの形（sections・segments・chorus・version・sub）で返す。拍は NLM の拍'''
    _libs()
    st, r = upload(WAV.read_bytes())
    aid = r["audioId"]
    g = grid_for(120.0, 0.0, 16.0)
    r = wait(start("structure", {"audioId": aid, "grid": g}))
    t.eq((r["state"], r["stage"], r["error"]), ("done", "structure", None), "状態")
    res = r["result"]
    t.eq((res["version"], res["sub"], res["bpm"], res["leadMs"]), (1, 4, 120.0, 0.0), "版・目盛り")
    secs, segs = res["sections"], res["segments"]
    t.ok(secs and segs, "セクション・区間がある")
    for s in secs:
        t.eq(sorted(s), ["chorus", "count", "end", "label", "name", "nameKey", "start"], "セクションの項目")
        t.ok(s["start"] < s["end"] and s["label"].startswith("S") and s["count"] >= 1, f"セクション {s}")
        t.ok(s["nameKey"] in NAME_KEYS and isinstance(s["chorus"], bool), f"名前の種類 {s}")
    for a, b in zip(secs, secs[1:]):
        t.eq(a["end"], b["start"], "セクションは隙間なく続く")
    for s in segs:
        t.eq(sorted(s), ["best", "count", "end", "group", "sim", "start"], "区間の項目")
    t.ok(segs[0]["start"] >= 0 and segs[-1]["end"] <= len(g["at"]) / 4, "拍の範囲")
    t.ok(isinstance(res["chorus"], list), "サビの候補はリスト")


def test_bad_audio_and_too_short(t):
    '''音源として読めない物は bad-audio、5秒より短い物は too-short（仕事の状態の error。種類だけを返す）'''
    _libs()
    st, r = upload(os.urandom(5000), "mp3")
    r = wait(start("tempo", {"audioId": r["audioId"]}))
    t.eq((r["state"], r["error"], r["result"]), ("error", "bad-audio", None), "読めない")
    short = synth_wav(2.0, seed=11)
    st, r = upload(short)
    r = wait(start("tempo", {"audioId": r["audioId"]}))
    t.eq((r["state"], r["error"]), ("error", "too-short"), "短すぎる")
    st, r = upload(WAV.read_bytes())
    g = grid_for(120.0, 0.0, 16.0)
    g["at"] = [a if i < 10 else None for i, a in enumerate(g["at"])]
    r = wait(start("structure", {"audioId": r["audioId"], "grid": g}))
    t.eq((r["state"], r["error"]), ("error", "too-short"), "音のあるコマが少なすぎる目盛り")
    st, r = upload(synth_wav(6.0, seed=12))
    r = wait(start("tempo", {"audioId": r["audioId"]}))
    t.eq((r["state"], r["result"]["error"], r["result"]["version"]), ("done", "few-onsets", 1),
         "16秒より短い曲も落ちない（打点が少なければ結果の error に種類）")


def test_m4a_via_ffmpeg(t):
    '''libsndfile で読めない形式（m4a）は ffmpeg で WAV にしてから読む。ffmpeg が無ければ ffmpeg-not-found（画面が入れ方を案内する）'''
    _libs()
    import shutil
    import subprocess
    sys.path.insert(0, str(H.ROOT))
    from song_analysis import service as SV
    ff = shutil.which("ffmpeg")
    if not ff:
        t.skip("ffmpeg が無い（winget install Gyan.FFmpeg）")
    with tempfile.TemporaryDirectory() as td:
        datas = []
        for i, br in enumerate(("128k", "96k")):
            dst = os.path.join(td, f"a{i}.m4a")
            subprocess.run([ff, "-nostdin", "-y", "-v", "error", "-i", str(WAV), "-c:a", "aac", "-b:a", br, dst], check=True,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            datas.append(Path(dst).read_bytes())
    st, r = upload(datas[0], "m4a")
    r = wait(start("tempo", {"audioId": r["audioId"]}))
    t.eq((r["state"], r["result"]["bpm"]), ("done", 120.0), "m4a（ffmpeg あり）")

    class NoFF:
        @staticmethod
        def which(name):
            return None
    real = SV.shutil
    SV.shutil = NoFF
    try:
        st, r = upload(datas[1], "m4a")
        r = wait(start("tempo", {"audioId": r["audioId"]}))
    finally:
        SV.shutil = real
    t.eq((r["state"], r["error"]), ("error", "ffmpeg-not-found"), "m4a（ffmpeg なし）")


def test_spec_includes_analysis(t):
    '''nlm.spec に song_analysis が入っている（serve.py が import するので、足し忘れると exe だけ起動に失敗する）'''
    spec = (H.ROOT / "nlm.spec").read_text(encoding="utf-8")
    t.ok("('song_analysis/*.py', 'song_analysis')" in spec, "datas")
    for m in ("song_analysis", "song_analysis.service", "song_analysis.tempo", "song_analysis.structure"):
        t.ok(f"'{m}'" in spec, f"hiddenimports に {m}")


def test_queue_and_cancel(t):
    '''解析は1件ずつ（2件目は待ち行列）。待っている仕事の取り消しはすぐ、解析中の物は次の区切りで止まる（error/cancelled）。
    取り消した後も次の仕事は動く'''
    _libs()
    st, ra = upload(synth_wav(40.0, seed=int(time.time()) % 1000 + 21))
    st, rb = upload(synth_wav(8.0, seed=int(time.time()) % 1000 + 22))
    ja = start("structure", {"audioId": ra["audioId"], "grid": grid_for(120.0, 0.0, 40.0)})
    jb = start("tempo", {"audioId": rb["audioId"]})
    st, sb = H.post_json("/__analysis/status", {"job": jb})
    t.eq(sb["state"], "queued", "2件目は待ち")
    t.eq(H.post_json("/__analysis/cancel", {"job": jb})[1], {"ok": True}, "待ちの取り消し")
    st, sb = H.post_json("/__analysis/status", {"job": jb})
    t.eq((sb["state"], sb["error"]), ("error", "cancelled"), "すぐ取り消される")
    t.eq(H.post_json("/__analysis/cancel", {"job": ja})[1], {"ok": True}, "解析中の取り消し")
    r = wait(ja)
    t.eq((r["state"], r["error"]), ("error", "cancelled"), "次の区切りで止まる")
    r = wait(start("tempo", {"audioId": rb["audioId"]}))
    t.eq(r["state"], "done", "その後の仕事は動く")


def test_measure_at_matches_tools(t):
    '''画面が渡す目盛り（at・10ms に丸めた物も）で測った特徴が、tools/analyze_structure.py（TempoMap）と同じになる。
    コマの境目がフレームの境目にちょうど乗る曲が多く、秒の最後の桁の違いで区切りが変わるため（nlm_grid の説明）。
    テンポパートのある目盛りは渡された秒のまま使う'''
    np = _libs()
    sys.path.insert(0, str(H.ROOT))
    from song_analysis import structure as S
    with tempfile.TemporaryDirectory() as td:
        p = os.path.join(td, "a.wav")
        Path(p).write_bytes(synth_wav(30.0, seed=5, bpm=84.0))
        y, _ = S.load_audio(p)
        dur = len(y) / S.SR
        tm = S.TempoMap(84.0, song_off=-0.26)
        F1 = S.measure(p, tm, y=y)
        n = F1["n"]
        at = [tm.audio_at(i / S.SUB, dur) for i in range(n + 6)]
        for label, a in (("そのまま", at), ("10ms に丸め", [None if v is None else round(v, 2) for v in at])):
            F2 = S.measure_at(p, json.loads(json.dumps(a)), 84.0, 260.0, y=y)
            for k in ("CQ", "M", "E"):
                t.ok(np.array_equal(F1[k], F2[k][..., :n]), f"{label}: {k} が同じ")
        tm2 = S.TempoMap(84.0, parts=[(40.0, 120.0)], song_off=-0.26)
        at2 = [tm2.audio_at(i / S.SUB, dur) for i in range(int(tm2.end_beat(dur) * S.SUB))]
        a2, e2 = S.nlm_grid(at2, 84.0, 260.0, dur)
        want = np.array([np.nan if v is None else v for v in at2])
        t.ok(np.array_equal(a2, want, equal_nan=True), "テンポパートのある目盛りはそのまま")
        ok = ~np.isnan(a2)
        t.ok(bool(np.all(e2[ok] > a2[ok])), "コマの終わりは頭より後")


def test_tools_modules_share_constants(t):
    '''tools/analyze_structure.py・tempo_leadin.py は song_analysis の計算をそのまま使い、定数の書き換えも song_analysis に効く
    （調整用のスクリプトが A.SECTION_SAME = … で試すため）'''
    _libs()
    sys.path.insert(0, str(H.ROOT))
    sys.path.insert(0, str(H.ROOT / "tools"))
    import analyze_structure as A
    import tempo_leadin as TL
    from song_analysis import structure as S
    from song_analysis import tempo as T
    t.ok(A.Analyzer is S.Analyzer and A.measure is S.measure and TL.estimate is T.estimate, "同じ関数")
    old, old2 = S.SECTION_SAME, T.LEAD_BIAS_MS
    try:
        A.SECTION_SAME = 0.123
        TL.LEAD_BIAS_MS = 7.0
        t.eq((S.SECTION_SAME, A.SECTION_SAME, T.LEAD_BIAS_MS), (0.123, 0.123, 7.0), "書き換えが効く")
    finally:
        A.SECTION_SAME = old
        TL.LEAD_BIAS_MS = old2
    t.eq((S.SECTION_SAME, T.LEAD_BIAS_MS), (old, old2), "元に戻る")


def test_clean_old_audio(t):
    '''一時フォルダの片付け: 最後に使ってから1日を過ぎた音源・1時間を過ぎた書きかけは消し、待ち・解析中の仕事の音源は残す。
    合計が上限を超えたら古い順に消す'''
    sys.path.insert(0, str(H.ROOT))
    from song_analysis import service as SV
    with tempfile.TemporaryDirectory() as td:
        svc = SV.AnalysisService(td)
        now = time.time()

        def mk(name, age, size=10):
            p = Path(td) / name
            p.write_bytes(b"x" * size)
            os.utime(p, (now - age, now - age))
            return p
        old = mk("a" * 64 + ".mp3", 2 * 86400)
        dec = mk("a" * 64 + ".dec.wav", 2 * 86400)
        new = mk("b" * 64 + ".wav", 60)
        busy = mk("c" * 64 + ".ogg", 3 * 86400)
        part = mk("up-0123.part", 2 * 3600)
        job = SV._Job("tempo", "c" * 64, {}, ("tempo", "c" * 64))
        svc.jobs[job.id] = job   # 待ちの仕事（実行はしない）
        t.eq(svc.clean(now), 3, "消した数")
        t.eq([p.exists() for p in (old, dec, new, busy, part)], [False, False, True, True, False], "残る物")
        mk("d" * 64 + ".wav", 120, size=600)
        keep = SV.KEEP_BYTES
        SV.KEEP_BYTES = 500
        try:
            svc.clean(now)
        finally:
            SV.KEEP_BYTES = keep
        t.eq(sorted(p.name[:1] for p in Path(td).iterdir()), ["b", "c"], "上限を超えた分は古い順に消す（使用中は残す）")

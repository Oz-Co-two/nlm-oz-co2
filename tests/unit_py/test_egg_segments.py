"""song.egg の変換（serve.py の /__convert/toOgg）: 無音追加と、Musicの配置（分割・トリム）の切り貼り。
ffmpeg が無い環境では飛ばす。出来た OGG を ffmpeg で WAV に戻し、「ピッ」の位置で切り貼りの結果を確かめる"""
import io
import json
import math
import shutil
import struct
import subprocess
import sys
import tempfile
import wave
from pathlib import Path
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parent))
import unitpy_helpers as H

RATE = 22050


def _beep_wav(beeps, seconds=14):
    """beeps（秒）の位置にだけ 0.1秒の「ピッ」がある WAV（モノラル16bit）"""
    n = int(seconds * RATE)
    smp = [0.0] * n
    for b in beeps:
        st = int(b * RATE)
        for k in range(int(0.1 * RATE)):
            if st + k < n:
                smp[st + k] = 0.7 * math.sin(2 * math.pi * 1000 * k / RATE)
    bio = io.BytesIO()
    with wave.open(bio, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(RATE)
        w.writeframes(b"".join(struct.pack("<h", int(v * 32767)) for v in smp))
    return bio.getvalue()


def _convert(t, query, body):
    st, hd, out = H.req("POST", "/__convert/toOgg?" + query, headers={"X-NLM-Request": "1"}, body=body)
    t.eq(st, 200, "status")
    t.ok(out[:4] == b"OggS", f"OGGが返る: {out[:120]!r}")
    return out


def _beeps_in(ogg):
    """OGG を WAV に戻し、0.1秒より長く続く音のかたまりの開始秒と、全体の長さ（秒）"""
    with tempfile.TemporaryDirectory() as td:
        src, dst = Path(td, "a.ogg"), Path(td, "a.wav")
        src.write_bytes(ogg)
        subprocess.run([shutil.which("ffmpeg"), "-y", "-i", str(src), "-ac", "1", "-ar", str(RATE), str(dst)],
                       capture_output=True, timeout=60, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        with wave.open(str(dst), "rb") as w:
            raw = w.readframes(w.getnframes())
    vals = struct.unpack("<%dh" % (len(raw) // 2), raw)
    win = int(0.01 * RATE)   # 10msごとの最大振幅
    starts, on = [], False
    for i in range(0, len(vals) - win, win):
        loud = max(abs(v) for v in vals[i:i + win]) > 6000
        if loud and not on:
            starts.append(round(i / RATE, 2))
        on = loud
    return starts, len(vals) / RATE


def _need_ffmpeg(t):
    if not shutil.which("ffmpeg"):
        t.skip("ffmpeg が無い環境")


def test_egg_lead_in(t):
    '''無音追加（leadInMs）: 先頭に無音を足すだけ＝「ピッ」が足した分だけ遅れる（これまでの動き）'''
    _need_ffmpeg(t)
    starts, dur = _beeps_in(_convert(t, "ext=wav&leadInMs=500", _beep_wav([1, 9])))
    t.eq([round(s, 1) for s in starts], [1.5, 9.5], "「ピッ」の位置（秒）")
    t.ok(abs(dur - 14.5) < 0.1, f"長さ 14.5秒: {dur:.2f}")


def test_egg_segments_cut_and_move(t):
    '''Musicの切り貼り: 0〜4秒を先頭に、8〜12秒を4秒目に並べる＝元の1秒・9秒の「ピッ」が1秒・5秒に来て、長さは8秒'''
    _need_ffmpeg(t)
    segs = quote(json.dumps([[0, 4, 0], [8, 12, 4]]))
    starts, dur = _beeps_in(_convert(t, "ext=wav&segs=" + segs, _beep_wav([1, 6, 9])))
    t.eq([round(s, 1) for s in starts], [1.0, 5.0], "「ピッ」の位置（元の6秒は切り取った区間なので鳴らない）")
    t.ok(abs(dur - 8.0) < 0.1, f"長さ 8秒: {dur:.2f}")


def test_egg_segments_gap_and_order(t):
    '''区間の間は無音・並べる順は書き出し先の位置どおり（元の9秒を先、元の1秒を後に並べ替えられる）'''
    _need_ffmpeg(t)
    segs = quote(json.dumps([[8, 10, 2], [0, 2, 6]]))   # 元の8〜10秒→2秒目、元の0〜2秒→6秒目（間の4〜6秒は無音）
    starts, dur = _beeps_in(_convert(t, "ext=wav&segs=" + segs, _beep_wav([1, 9])))
    t.eq([round(s, 1) for s in starts], [3.0, 7.0], "「ピッ」の位置（元の9秒→3秒、元の1秒→7秒）")
    t.ok(abs(dur - 8.0) < 0.1, f"長さ 8秒: {dur:.2f}")


def test_egg_segments_rejects_bad_input(t):
    '''切り貼り表がおかしい（負の秒・終わりが開始より前・数でない・多すぎる）時は変換せず bad-segs'''
    for bad in ([[-1, 2, 0]], [[3, 2, 0]], [["a", 2, 0]], [[0, 1, float("nan")]], [[0, 1, 0]] * 1001, [], "x"):
        st, hd, body = H.req("POST", "/__convert/toOgg?ext=wav&segs=" + quote(json.dumps(bad)),
                             headers={"X-NLM-Request": "1"}, body=_beep_wav([1], seconds=2))
        if not shutil.which("ffmpeg"):
            t.eq(json.loads(body).get("error"), "ffmpeg-not-found", "ffmpeg無し")
            continue
        t.eq(json.loads(body), {"ok": False, "error": "bad-segs"}, f"切り貼り表 {str(bad)[:40]}")

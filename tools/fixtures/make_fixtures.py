"""テスト素材(tools/fixtures/)を作り直すスクリプト。

  basic.wav   … 120BPM・16秒のクリック音（4拍目ごとに高い音）。プログラム生成なので著作物の問題なし
  basic.nlmf  … basic.wav 用のプロジェクト。tools/cdp.py で実際にクリックして赤青ノーツを8個置いたもの
                （＝アプリ自身が保存した正規の形式。形式が変わったら作り直す）

使い方: .venv-build/Scripts/python.exe tools/fixtures/make_fixtures.py
"""
import json
import math
import struct
import sys
import wave
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from cdp import Editor  # noqa: E402

BPM, SECONDS, RATE = 120, 16, 22050


def make_wav(path):
    n = SECONDS * RATE
    samples = [0.0] * n
    beat_len = 60 / BPM
    for i in range(int(SECONDS / beat_len)):
        start = int(i * beat_len * RATE)
        freq = 1760 if i % 4 == 0 else 880   # 小節頭は高い音
        for k in range(int(0.05 * RATE)):     # 50msの減衰クリック
            if start + k < n:
                samples[start + k] += 0.6 * math.exp(-k / (0.008 * RATE)) * math.sin(2 * math.pi * freq * k / RATE)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(b"".join(struct.pack("<h", int(max(-1, min(1, s)) * 32767)) for s in samples))


def make_project(path):
    # 空の状態から音源だけ読み、配置モードの赤枠にクリックでノーツを置く（1拍ずつ進めながら赤青交互）
    with Editor() as ed:
        ed.js("""(async()=>{ const blob=await (await fetch('tools/fixtures/basic.wav',{cache:'no-store'})).blob();
          const file=new File([blob],'basic.wav',{type:'audio/wav'});
          await window._dbg.rt.loadSongFromItem({isMusic:true,name:'basic',songFh:{getFile:async()=>file},info:{_beatsPerMinute:120}},0);
          return true; })()""")
        ed.wait(1.0)
        cells = [(1, 0), (2, 0), (0, 1), (3, 1), (1, 0), (2, 0), (1, 2), (2, 2)]
        for i, (x, y) in enumerate(cells):
            want = 0 if x < 2 else 1          # 左2列=赤 / 右2列=青
            if ed.js("window._dbgApp.state().brush.c") != want:
                ed.key("f")                   # F=ブラシ色反転
            ed.key("ArrowRight"); ed.key("ArrowRight")   # 1拍進める（スナップ1/2×2）
            ed.wait(0.3)
            p = ed.js(f"window._dbgApp.cellScreen({x},{y})")
            ed.move(p["x"], p["y"]); ed.wait(0.3)
            ed.click(p["x"], p["y"]); ed.wait(0.3)
        st = ed.js("window._dbgApp.state()")
        if st["counts"]["notes"] != len(cells):
            raise SystemExit(f"ノーツ配置に失敗: {st['counts']}（期待 {len(cells)}個）\n{ed.errors()}")
        text = ed.js("window._dbg.rt.buildProjectText()")
        pj = json.loads(text)
        pj["savedAt"] = "2026-01-01T00:00:00.000Z"   # 作り直しても差分が出にくいよう固定
        path.write_text(json.dumps(pj, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        print("ノーツ", st["counts"]["notes"], "個・エラー", ed.errors() or "なし")


if __name__ == "__main__":
    make_wav(HERE / "basic.wav")
    print("作成:", HERE / "basic.wav")
    make_project(HERE / "basic.nlmf")
    print("作成:", HERE / "basic.nlmf")

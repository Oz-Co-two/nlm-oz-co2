"""unit_js グループ共通の部品（ページ内でJSモジュールを直接呼ぶためのもの）。"""
import json

# ページ内で使う、問題の無い譜面（blcriteria_test.py と同じ作り）と runMapCheck の入力を作る関数
MAP_JS = r"""
const base = () => {
  const cn = [], ev = [];
  for (let b = 8; b <= 200; b++) { const d = b % 2 ? 0 : 1; cn.push({ b, x: 1, y: 0, c: 0, d, a: 0 }, { b, x: 2, y: 0, c: 1, d, a: 0 }); }
  for (let b = 0; b <= 240; b++) ev.push({ b, et: 0, i: 1, f: 1 });
  return { version: '3.2.0', bpmEvents: [], colorNotes: cn, bombNotes: [], obstacles: [], sliders: [], burstSliders: [], basicBeatmapEvents: ev };
};
const P = (json, extra = {}) => ({ info: { bpm: 120, environment: 'DefaultEnvironment', previewStart: 12, previewDuration: 10 },
  diffs: [{ difficulty: 'Expert', json, njs: 16, njsOffset: 0 }], audioDuration: 120, cover: { w: 512, h: 512, name: 'cover.png' },
  meta: { songName: 'Test Song', subName: '', author: 'Artist', mapper: 'me' },
  infoRaw: { songTimeOffset: 0, shuffle: 0, shufflePeriod: 0, colorSchemes: [], requirements: [] }, ...extra });
const keysOf = r => ({ general: r.general.map(x => x.key), diff: r.diffs[0].results.map(x => x.key), err: r.diffs[0].error || null });
"""


def run_js(ed, body):
    """MAP_JS の部品が使える状態で body（async関数の中身。return で値を返す）を実行し、結果を返す"""
    return ed.js("(async () => {" + MAP_JS + body + "})()")


def jq(v):
    return json.dumps(v, ensure_ascii=False)

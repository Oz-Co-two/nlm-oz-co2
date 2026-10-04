"""js/lighting/auto-light.js（generateAutoLights / envTypes）の単体テスト。
期待値は CLAUDE.md「自動ライティング」節の約束（R10.Aの数に入る種別だけで1拍あたり1.2個以上・BACKは消さない・色はバニラのみ）から決める。"""
import json

HEAD = """
const { generateAutoLights, envTypes } = await import('/js/lighting/auto-light.js');
const { BASIC_TRACKS } = await import('/js/mapcheck/env-tables.js');
// 4拍ごとに赤青の同時ノーツ、32拍まで
const mk = (over = {}) => ({ notes: Array.from({ length: 8 }, (_, i) => [{ beat: 4 + i * 4, c: 0 }, { beat: 4 + i * 4, c: 1 }]).flat(),
  chains: [], others: [], endBeat: 60, bpm: 120, env: 'DefaultEnvironment', markers: [], ...over });
"""


def _js(t, body):
    return t.ed.js("(async () => {" + HEAD + body + "})()")


def test_density_and_back(t):
    '''数える種別だけで1拍あたり1.2個以上・BACKが曲頭から最後の物の2拍後まで消えない・色はバニラ（赤/青）だけ'''
    t.fresh()
    r = _js(t, """
const res = generateAutoLights(mk());
const l = envTypes('DefaultEnvironment').l;
return { events: res.events, counted: res.events.filter(e => l.includes(e.et)).length, perBeat: res.perBeat, end: res.endBeat, l };""")
    ev = r['events']
    t.ok(len(ev) > 0, 'イベントが作られる')
    t.eq(r['end'], 60, 'endBeat')
    t.ok(r['counted'] / 60 >= 1.2, f"数に入るライトが1.2/拍以上: {r['counted']}個/60拍")
    t.ok(r['perBeat'] >= 1.2, 'perBeat の自己申告も1.2以上')
    # BACK(et=0): 0拍に点灯、2拍後(最後のノーツ=32拍→34拍)より前に消灯(値0)が無い
    back = [e for e in ev if e['et'] == 0]
    t.ok(any(e['beat'] == 0 and e['i'] != 0 for e in back), 'BACKが曲の頭から点いている')
    t.ok(not any(e['i'] == 0 and e['beat'] < 34 for e in back), 'BACKは最後の物の2拍後まで消えない')
    t.ok(max(e['beat'] for e in back) >= 34, 'BACKの終端は最後の物の2拍後以降')
    # 色: ライト種別の値は 1..3(青) か 5..7(赤)。スクリプト色(f=1以外/customData)は無い
    for e in ev:
        if e['et'] in r['l']:
            t.ok(e['i'] in (1, 2, 3, 5, 6, 7), f"バニラの値のみ: {e}")
        t.ok(set(e) == {'beat', 'et', 'i', 'f'}, f"customData等を持たない: {e}")
    t.no_errors()


def test_events_valid(t):
    '''イベントは [0, endBeat) の範囲・拍順・同じ拍と種別の重複なし・環境で使える種別だけ'''
    r = _js(t, """
const out = {};
for (const env of ['DefaultEnvironment', 'KaleidoscopeEnvironment', 'WeaveEnvironment', 'GagaEnvironment', 'NoSuchEnvironment']) {
  const res = generateAutoLights(mk({ env }));
  out[env] = res && { events: res.events, k: envTypes(env).k };
}
return out;""")
    for env, v in r.items():
        t.ok(v, f'{env}: 結果がある')
        ev = v['events']
        t.ok(all(0 <= e['beat'] < 60 for e in ev), f'{env}: 範囲内')
        t.eq([e['beat'] for e in ev], sorted(e['beat'] for e in ev), f'{env}: 拍順')
        keys = [(e['beat'], e['et']) for e in ev]
        t.eq(len(keys), len(set(keys)), f'{env}: 重複なし')
        t.ok(all(e['et'] in v['k'] for e in ev), f"{env}: 使える種別だけ {sorted({e['et'] for e in ev} - set(v['k']))}")
    t.no_errors()


def test_unknown_env_is_default(t):
    '''表に無い環境は Default 扱い'''
    r = _js(t, "return { a: envTypes('NoSuchEnvironment'), d: envTypes('DefaultEnvironment'), w: envTypes('WeaveEnvironment') };")
    t.eq(r['a'], r['d'], '不明な環境=Default')
    t.eq(r['w']['k'], [4], 'Weave は種別4のみ')
    t.no_errors()


def test_empty_input(t):
    '''置く物が無ければ null。ボムや壁だけでも置く物として扱う'''
    r = _js(t, """
return { none: generateAutoLights(mk({ notes: [] })),
  bombs: !!generateAutoLights(mk({ notes: [], others: [{ beat: 8 }] })),
  wall: !!generateAutoLights(mk({ notes: [], others: [{ b: 8, dur: 4 }] })),
  chain: !!generateAutoLights(mk({ notes: [], chains: [{ b: 8, c: 0 }] })) };""")
    t.eq(r['none'], None, '何も無ければnull')
    t.ok(r['bombs'] and r['wall'] and r['chain'], 'ボム/壁/チェーンだけでも作る')
    t.no_errors()


def test_end_beat_fallback(t):
    '''endBeat が最後の物より前（音源が無い等）の時は最後の物から1小節先までで切る'''
    r = _js(t, "const res = generateAutoLights(mk({ endBeat: 0 })); return { end: res.endBeat, max: Math.max(...res.events.map(e => e.beat)), perBeat: res.perBeat };")
    t.ok(r['end'] > 32, f"最後の物(32拍)より後ろまで: {r['end']}")
    t.ok(r['max'] < r['end'], 'イベントはendBeat未満')
    t.ok(r['perBeat'] >= 1.2, '密度は保たれる')
    t.no_errors()


def test_deterministic(t):
    '''同じ入力なら同じ結果（乱数を使わない）'''
    r = _js(t, "return JSON.stringify(generateAutoLights(mk())) === JSON.stringify(generateAutoLights(mk()));")
    t.eq(r, True, '再現性')
    t.no_errors()


def test_lasers_follow_notes(t):
    '''赤ノーツ=左レーザー(2・赤)、青ノーツ=右レーザー(3・青)。近すぎる連打でレーザーをチカチカさせない'''
    r = _js(t, """
const one = generateAutoLights(mk({ notes: [{ beat: 8, c: 0 }, { beat: 16, c: 1 }], endBeat: 40 }));
const dense = generateAutoLights(mk({ notes: Array.from({ length: 64 }, (_, i) => ({ beat: 8 + i / 16, c: 0 })), endBeat: 40, bpm: 180 }));
return { one: one.events.filter(e => e.et === 2 || e.et === 3), dense: [2, 3].map(et => dense.events.filter(e => e.et === et).map(e => e.beat)) };""")
    t.ok(any(e['et'] == 2 and e['beat'] == 8 and e['i'] >= 5 for e in r['one']), '8拍の赤ノーツ→左レーザー赤')
    t.ok(any(e['et'] == 3 and e['beat'] == 16 and 1 <= e['i'] <= 3 for e in r['one']), '16拍の青ノーツ→右レーザー青')
    t.ok(sum(len(x) for x in r['dense']) < 64, f"連打では光らせない拍がある: {sum(len(x) for x in r['dense'])}/64")
    for et, d in zip((2, 3), r['dense']):
        d = sorted(d)
        t.ok(all(b - a >= 0.25 - 1e-6 for a, b in zip(d, d[1:])), f'レーザー{et}は最短間隔(0.25拍)を割らない')
    t.no_errors()

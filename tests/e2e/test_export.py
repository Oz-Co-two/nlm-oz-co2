"""書き出し結果の照合（exportMap のダウンロードを横取りして Info.dat と各難易度 .dat を正解ファイルと比べる）

正解ファイル: tests/golden/export/<素材名>/<ファイル名>（JSONは整形済み）。意図して書き出しを変えた時は
`tools/run_tests.py e2e --update-golden` で作り直し、差分を目で確かめてから確定する。
"""
import json

from e2e_helpers import RICH, bulk_load_rich_map, export_files, open_fixture, place_at, pretty_json, switch_diff

V3_KEYS = {'notes': 'colorNotes', 'bombs': 'bombNotes', 'walls': 'obstacles', 'arcs': 'sliders', 'chains': 'burstSliders',
           'lights': 'basicBeatmapEvents'}


def _golden_all(t, fx, files):
    for name in sorted(files):
        t.golden(f'export/{fx}/{name}', pretty_json(files[name]))


def _dat_counts(j):
    return {k: len(j.get(v) or []) for k, v in V3_KEYS.items()}


def test_export_basic(t):
    '''basic: 書き出した Info.dat と HardStandard.dat が正解と一致する'''
    ed = open_fixture(t, 'basic')
    files = export_files(ed)
    t.eq(sorted(files), ['HardStandard.dat', 'Info.dat'], '書き出したファイル')
    info = json.loads(files['Info.dat'])
    t.eq(info['_beatsPerMinute'], 120, 'BPM')
    t.eq([d['_beatmapFilename'] for d in info['_difficultyBeatmapSets'][0]['_difficultyBeatmaps']], ['HardStandard.dat'], 'Info.datの難易度')
    hard = json.loads(files['HardStandard.dat'])
    t.eq(_dat_counts(hard), dict(notes=8, bombs=0, walls=0, arcs=0, chains=0, lights=0), 'Hardの数')
    bs = [n['b'] for n in hard['colorNotes']]
    t.eq(bs, sorted(bs), 'ノーツが時刻順')
    t.eq(hard['bpmEvents'], [], 'テンポ変化なし')
    _golden_all(t, 'basic', files)
    t.no_errors()


def test_export_rich(t):
    '''rich: 書き出した Info.dat と Hard/Expert の .dat が正解と一致する（曲情報・NJS・テンポ・チェーンの頭の合成）'''
    ed = open_fixture(t, 'rich')
    files = export_files(ed)
    t.eq(sorted(files), ['ExpertStandard.dat', 'HardStandard.dat', 'Info.dat'], '書き出したファイル')
    info = json.loads(files['Info.dat'])
    t.eq({k: info[k] for k in ('_songName', '_songSubName', '_songAuthorName', '_levelAuthorName', '_beatsPerMinute',
                               '_previewStartTime', '_previewDuration', '_shuffle', '_shufflePeriod', '_songFilename')},
         {'_songName': 'リッチ テスト曲', '_songSubName': 'fixture', '_songAuthorName': 'NLM Test Artist', '_levelAuthorName': 'NLM Tester',
          '_beatsPerMinute': 120, '_previewStartTime': 4, '_previewDuration': 6, '_shuffle': 0, '_shufflePeriod': 0,
          '_songFilename': 'song.egg'}, 'Info.datの曲情報')
    bms = info['_difficultyBeatmapSets'][0]['_difficultyBeatmaps']
    t.eq([(d['_difficulty'], d['_difficultyRank'], d['_beatmapFilename'], d['_noteJumpMovementSpeed'], d['_noteJumpStartBeatOffset']) for d in bms],
         [('Hard', 5, 'HardStandard.dat', 14, 0), ('Expert', 7, 'ExpertStandard.dat', 17, -0.25)], 'Info.datの難易度（易しい順・NJS/オフセット）')
    for name, want in RICH.items():
        j = json.loads(files[name])
        # V3の .dat の要素に V2 の項目名（_time 等。_ で始まる）が混ざらない
        mixed = sorted({k for arr in j.values() if isinstance(arr, list) for o in arr if isinstance(o, dict) for k in o if k.startswith('_')})
        t.eq(mixed, [], f'{name}: V3の要素に混ざった _ で始まる項目')
        exp = dict(want)
        exp['notes'] += want['chains']   # チェーンの頭ノーツは書き出し時に合成される（実機の仕様）
        t.eq(_dat_counts(j), exp, f'{name} の数')
        t.eq(j['bpmEvents'], [{'b': 16, 'm': 150}], f'{name} のテンポ変化（テンポパート）')
        t.eq(j['version'], '3.2.0', f'{name} の形式')
        for k in V3_KEYS.values():
            bs = [o['b'] for o in j[k]]
            t.eq(bs, sorted(bs), f'{name} の {k} が時刻順')
    ex = json.loads(files['ExpertStandard.dat'])
    heads = {(c['b'], c['x'], c['y'], c['c']) for c in ex['burstSliders']}
    t.eq(len([n for n in ex['colorNotes'] if (n['b'], n['x'], n['y'], n['c']) in heads]), 2, 'チェーンの頭のノーツ')
    t.eq(sorted({n['d'] for n in ex['colorNotes']}), list(range(9)), 'Expertのノーツの向き（9方向すべて）')
    _golden_all(t, 'rich', files)
    t.no_errors()


def test_export_after_edit(t):
    '''編集が書き出しに反映される（Expertにノーツを足すと Expert の .dat だけが1個増える）'''
    ed = open_fixture(t, 'rich')
    switch_diff(ed, 'Expert')
    place_at(ed, 3, 2)
    files = export_files(ed)
    ex, hd = json.loads(files['ExpertStandard.dat']), json.loads(files['HardStandard.dat'])
    t.eq(len(ex['colorNotes']), RICH['ExpertStandard.dat']['notes'] + 2 + 1, 'Expertのノーツ（頭2＋追加1）')
    t.eq([(n['x'], n['y']) for n in ex['colorNotes'] if n['b'] == 0], [(3, 2)], '追加したノーツ（拍0）')
    t.eq(len(hd['colorNotes']), RICH['HardStandard.dat']['notes'], 'Hardは変わらない')
    t.no_errors()


def test_export_after_bulk_import(t):
    '''曲データの一括読込の直後に書き出すと、読み込んだ全難易度（Hard/Expert）が書き出される'''
    ed = t.fresh()
    bulk_load_rich_map(ed)
    files = export_files(ed)
    t.ok('HardStandard.dat' in files, f'今の難易度（Hard）が書き出されない: {sorted(files)}')
    # 以前は開いていない難易度のクリップがフラット配列へ展開されず、書き出し・譜面チェックから漏れていた
    t.ok('ExpertStandard.dat' in files, f'開いていない難易度（Expert）が書き出されない: {sorted(files)}')
    ex = json.loads(files['ExpertStandard.dat'])
    exp = dict(RICH['ExpertStandard.dat'])
    exp['notes'] += exp['chains']
    t.eq(_dat_counts(ex), exp, 'Expertの数')
    t.no_errors()


def test_bulk_import_keeps_tempo_changes(t):
    '''曲データの一括読込で、元の譜面のテンポ変化（bpmEvents: 拍16で150）がテンポパートとして取り込まれる'''
    ed = t.fresh()
    bulk_load_rich_map(ed)
    tp = ed.js("JSON.parse(window._dbg.rt.buildProjectText()).tempoParts")
    t.eq(ed.js("window._dbgApp.state().BPM"), 120, '基準BPM（Info.dat）')
    t.eq(tp, [{'beat': 16, 'bpm': 150}], '読込後のテンポパート（拍0の120は基準BPMなので入らない）')
    t.no_errors()


def test_bulk_import_keeps_extra_fields(t):
    '''曲データの一括読込で、ノーツの標準外の値（v3 の角度オフセット a=45）が書き出しまで残る'''
    ed = t.fresh()
    bulk_load_rich_map(ed)
    ex = json.loads(export_files(ed)['ExpertStandard.dat'])   # Expert は開いていない（開かなくても残ること）
    a = [n.get('a') for n in ex['colorNotes'] if n['b'] == 7.5]
    t.eq(a, [45], '拍7.5のノーツの角度オフセット a')
    t.no_errors()

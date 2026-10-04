"""INFO（ノードエディタ）のノード操作: 追加・削除・複製・移動・配線・書き出しノード・試聴ノード・曲情報ノード。
操作は本物のマウス/キー入力。結果は infoGraph（読み取り窓口）と、書き出した Info.dat で確かめる。"""
import json

from e2e_helpers import export_files
from info_helpers import (center, click_sel, click_text, edges, free_spot, hover_info, info_graph, node_rect, node_types,
                          open_fixture, reveal, select_node, to_info, toast, type_text, undo, wait_until, world_at)

OUT = "#infoWorld .iGrp[data-node='out:o1']"


def _rich_info(t):
    ed = open_fixture(t, 'rich')
    to_info(ed)
    return ed


def _add_via_menu(ed, label):
    """INFOの空きを右クリック → メニューの項目をクリック。クリックしたワールド座標を返す"""
    p = free_spot(ed)
    w = world_at(ed, p["x"], p["y"])
    ed.click(p["x"], p["y"], button="right")
    click_text(ed, '#ctxmenu button', label)
    return w


def _port(ed, node_id):
    reveal(ed, node_id)
    return center(ed, f"#infoWorld .iGrp[data-node='{node_id}'] .nPort i")


def _out_port(ed, oid, kind):
    reveal(ed, f'out:{oid}')
    return center(ed, f"#infoWorld .iGrp[data-out='{oid}'] .oPort[data-oport='{oid}|{kind}'] i")


def _wire(ed, node_id, oid, kind=None):
    """ノードの出力ポートから書き出しノードへドラッグ。kind を渡せばその入力ポートへ、無ければカードの上へ落とす"""
    for _ in range(2):   # 両方が枠に収まるまで（片方をずらすともう片方が出ることがある）
        reveal(ed, node_id)
        reveal(ed, f'out:{oid}')
    a = _port(ed, node_id)
    if kind:
        b = _out_port(ed, oid, kind)
    else:
        c = node_rect(ed, f'out:{oid}')
        b = {"x": c["x"] + c["w"] / 2, "y": c["y"] + 40}
    ed.drag(a["x"], a["y"], b["x"], b["y"])


def _info_dat(ed):
    return json.loads(export_files(ed)['Info.dat'])


def _type_into(ed, node_id, field, text):
    """曲情報ノードの入力欄をクリックして全選択 → 入力（本物のキー入力）"""
    reveal(ed, node_id)
    selector = f"#infoWorld .iGrp[data-node='{node_id}'] input[data-f='{field}']"
    click_sel(ed, selector, f'入力欄 {selector}')
    ed.key('a', ctrl=True)
    type_text(ed, text)


def test_info_add_nodes(t):
    '''右クリック→「＋ ○○ ノード」で4種のノードが足せる。クリックした位置に出て選択状態になり、未接続。Undoで消える'''
    ed = _rich_info(t)
    base = node_types(ed)
    labels = {'meta': '＋ 曲情報 ノード', 'set': '＋ 設定 ノード', 'cover': '＋ カバー画像 ノード', 'prev': '＋ 試聴 ノード'}
    added = []
    for kind, label in labels.items():
        before = set(node_types(ed))
        w = _add_via_menu(ed, label)
        wait_until(ed, f"Object.keys(window._dbgApp.infoGraph().nodes).length==={len(before) + 1}", label=f'{kind} の追加')
        new = [k for k in node_types(ed) if k not in before]
        t.eq(len(new), 1, f'{kind}: 増えたノード')
        nid = new[0]
        g = info_graph(ed)["nodes"][nid]
        t.eq(g["t"], kind, f'{kind}: 種類')
        t.ok(abs(g["x"] - w["x"]) < 1.5 and abs(g["y"] - w["y"]) < 1.5, f'{kind}: クリックした位置（{w}）に出る: ({g["x"]}, {g["y"]})')
        t.ok(all(nid not in e for e in edges(ed)), f'{kind}: 新しいノードは未接続')
        t.ok(ed.js(f"document.querySelector('#infoWorld .iGrp[data-node=\"{nid}\"]').classList.contains('sel')"), f'{kind}: 選択状態')
        added.append(nid)
    t.eq(len(node_types(ed)), len(base) + 4, 'ノード数')
    undo(ed)
    t.eq(sorted(node_types(ed)), sorted(list(base) + added[:3]), 'Undo1回で最後に足したノードだけ消える')
    t.no_errors()


def test_info_delete_node_and_undo(t):
    '''ノードを選んで Delete で消すと、そのノードの配線も消える。Undoでノードも配線も中身も戻る'''
    ed = _rich_info(t)
    before = info_graph(ed)
    t.ok(('p1', 'o1') in edges(ed), '準備: 試聴ノード p1 が接続されている')
    select_node(ed, 'p1')
    hover_info(ed)
    ed.key('Delete')
    wait_until(ed, "!window._dbgApp.infoGraph().nodes.p1", label='p1 の削除')
    t.ok(all('p1' not in e for e in edges(ed)), '配線も消える')
    t.eq(sorted(node_types(ed)), sorted(k for k in before["nodes"] if k != 'p1'), '他のノードは残る')
    undo(ed)
    after = info_graph(ed)
    t.eq(after["nodes"]["p1"], before["nodes"]["p1"], 'Undoでノードが元の位置・中身で戻る')
    t.eq(edges(ed), sorted((e["s"], e["o"]) for e in before["edges"]), 'Undoで配線も戻る')
    t.no_errors()


def test_info_duplicate_copy_paste(t):
    '''曲情報ノードを Ctrl+C → Ctrl+V で複製。中身は同じで、右下に50ずれ、未接続で選択状態。Undoで消える'''
    ed = _rich_info(t)
    before = info_graph(ed)
    src = before["nodes"]["m2"]
    select_node(ed, 'm2')
    hover_info(ed)
    ed.key('c', ctrl=True)
    ed.key('v', ctrl=True)
    wait_until(ed, f"Object.keys(window._dbgApp.infoGraph().nodes).length==={len(before['nodes']) + 1}", label='貼り付け')
    g = info_graph(ed)
    new = [k for k in g["nodes"] if k not in before["nodes"]]
    n = g["nodes"][new[0]]
    t.eq((n["t"], n["data"]), ('meta', src["data"]), '種類と中身（曲名など）が同じ')
    t.eq((n["x"], n["y"]), (src["x"] + 50, src["y"] + 50), '位置は右下に50ずれる')
    t.ok(all(new[0] not in e for e in edges(ed)), '複製は未接続')
    t.eq(ed.js(f"[...document.querySelectorAll('#infoWorld .iGrp.sel')].map(e=>e.dataset.node)"), new, '貼り付けたものが選択状態')
    undo(ed)
    t.eq(sorted(node_types(ed)), sorted(before["nodes"]), 'Undoで複製が消える')
    t.no_errors()


def test_info_drag_move(t):
    '''ノードの見出しをドラッグすると、その分だけ動く（ズーム倍率ぶん補正）。Undoで元の位置へ'''
    ed = _rich_info(t)
    g0 = info_graph(ed)
    n0 = g0["nodes"]["c3"]
    s = g0["cam"]["s"]
    reveal(ed, 'c3')
    h = center(ed, "#infoWorld .iGrp[data-node='c3'] h3")
    dx, dy = 90, -40
    ed.drag(h["x"], h["y"], h["x"] + dx, h["y"] + dy)
    n1 = info_graph(ed)["nodes"]["c3"]
    t.ok(abs((n1["x"] - n0["x"]) - dx / s) < 1.5 and abs((n1["y"] - n0["y"]) - dy / s) < 1.5,
         f'移動量: 期待({dx / s:.1f}, {dy / s:.1f}) 実際({n1["x"] - n0["x"]:.1f}, {n1["y"] - n0["y"]:.1f})')
    t.eq(info_graph(ed)["nodes"]["m1"], g0["nodes"]["m1"], '他のノードは動かない')
    undo(ed)
    n2 = info_graph(ed)["nodes"]["c3"]
    t.eq((n2["x"], n2["y"]), (n0["x"], n0["y"]), 'Undoで元の位置')
    t.no_errors()


def test_info_wire_replace_and_unplug(t):
    '''ポートのドラッグ: 曲情報ノードのポートを書き出しノードへ落とすと同じ種類の線が差し替わる。出力側の線を空きへ引き抜くと切れる。Undoで戻る'''
    ed = _rich_info(t)
    base = edges(ed)
    t.eq(base, [('c1', 'o1'), ('m2', 'o1'), ('p1', 'o1'), ('s1', 'o1')], '準備: 配線')
    # 1) m1（空の曲情報）のポート → 書き出しの曲情報ポート ＝ m2 から差し替わる
    _wire(ed, 'm1', 'o1', 'meta')
    wait_until(ed, "window._dbgApp.infoGraph().edges.some(e=>e.s==='m1')", label='m1 の接続')
    t.eq(edges(ed), [('c1', 'o1'), ('m1', 'o1'), ('p1', 'o1'), ('s1', 'o1')], '同じ種類は差し替え（1本のまま）')
    t.eq(ed.js("window._dbgApp.mapCheckInput().then(p=>p.meta.songName)"), '', '曲名は空のノードの値になる')
    undo(ed)
    t.eq(edges(ed), base, 'Undoで元の配線')
    # 2) 書き出し側の曲情報ポートを掴んで空きへ → はがれる
    b = _out_port(ed, 'o1', 'meta')
    sp = free_spot(ed)
    ed.drag(b["x"], b["y"], sp["x"], sp["y"])
    wait_until(ed, "!window._dbgApp.infoGraph().edges.some(e=>e.s==='m2')", label='m2 の切断')
    t.eq(edges(ed), [('c1', 'o1'), ('p1', 'o1'), ('s1', 'o1')], '曲情報の線だけ切れる')
    t.eq(ed.js("window._dbgApp.mapCheckInput().then(p=>p.meta.songName)"), '', '切れたので曲名は空')
    # 3) 切れた m2 を書き出しの上へ落として繋ぎ直す
    _wire(ed, 'm2', 'o1')   # 書き出しカードの上ならどこでも、種類が合うポートへ繋がる
    wait_until(ed, "window._dbgApp.infoGraph().edges.some(e=>e.s==='m2')", label='m2 の再接続')
    t.eq(edges(ed), base, '繋ぎ直して元の配線')
    t.eq(ed.js("window._dbgApp.mapCheckInput().then(p=>p.meta.songName)"), 'リッチ テスト曲', '曲名が戻る')
    # 4) ソース側のポートを空きへ落とす → その口の線が全部はがれる
    a = _port(ed, 'c1')
    sp = free_spot(ed)
    ed.drag(a["x"], a["y"], sp["x"], sp["y"])
    wait_until(ed, "!window._dbgApp.infoGraph().edges.some(e=>e.s==='c1')", label='c1 の切断')
    t.eq(edges(ed), [('m2', 'o1'), ('p1', 'o1'), ('s1', 'o1')], 'カバーの線だけ切れる')
    t.no_errors()


def test_info_wire_by_type(t):
    '''別の試聴ノード(p4)を書き出しカードへ落とすと、種類が合う「試聴」ポートに繋がり p1 と入れ替わる。書き出しの試聴区間は p4 の値になる'''
    ed = _rich_info(t)
    # p4 の値を変えて区別できるようにする（‹›で開始を+1）
    reveal(ed, 'p4')
    click_sel(ed, "#infoWorld .iGrp[data-node='p4'] .pvF[data-f2='start'] .bfA[data-k='up']", 'p4 の開始 ›')
    wait_until(ed, "window._dbgApp.infoGraph().nodes.p4.data.start===5", label='p4 の開始')
    _wire(ed, 'p4', 'o1')
    wait_until(ed, "window._dbgApp.infoGraph().edges.some(e=>e.s==='p4')", label='p4 の接続')
    t.eq(edges(ed), [('c1', 'o1'), ('m2', 'o1'), ('p4', 'o1'), ('s1', 'o1')], 'p1 から p4 へ差し替わる')
    t.eq(_info_dat(ed)['_previewStartTime'], 5, '書き出しの試聴開始は p4 の値')
    t.no_errors()


def test_info_out_nodes_switch(t):
    '''書き出しノードを足すと新しい方がアクティブ。それぞれ別の曲情報を繋ぐと、アクティブを切り替えるたびに書き出す曲名が変わる'''
    ed = _rich_info(t)
    # m1 に曲名を入れる（本物のキー入力）
    _type_into(ed, 'm1', 'name', 'B曲')
    wait_until(ed, "window._dbgApp.infoGraph().nodes.m1.data.name==='B曲'", label='m1 の曲名')
    # 書き出しノードを足す
    w = _add_via_menu(ed, '＋ 書き出しノード')
    wait_until(ed, "Object.keys(window._dbgApp.infoGraph().outs).length===2", label='書き出しノードの追加')
    g = info_graph(ed)
    t.eq(g["activeOut"], 'o2', '足した書き出しノードがアクティブ')
    t.ok(abs(g["outs"]["o2"]["x"] - w["x"]) < 1.5 and abs(g["outs"]["o2"]["y"] - w["y"]) < 1.5, '右クリックした位置に出る')
    t.eq(_info_dat(ed)['_songName'], '', '何も繋がっていない書き出し（o2）の曲名は空')
    # m1 を o2 の曲情報ポートへ
    _wire(ed, 'm1', 'o2', 'meta')
    wait_until(ed, "window._dbgApp.infoGraph().edges.some(e=>e.s==='m1'&&e.o==='o2')", label='m1→o2')
    t.eq(sorted(edges(ed)), sorted([('c1', 'o1'), ('m2', 'o1'), ('p1', 'o1'), ('s1', 'o1'), ('m1', 'o2')]), '両方の書き出しに繋がっている')
    t.eq(_info_dat(ed)['_songName'], 'B曲', 'アクティブ(o2)の曲名')
    # o1 をクリックしてアクティブにする
    select_node(ed, 'out:o1')
    wait_until(ed, "window._dbgApp.infoGraph().activeOut==='o1'", label='o1 がアクティブ')
    t.eq(_info_dat(ed)['_songName'], 'リッチ テスト曲', 'アクティブ(o1)の曲名')
    t.ok(ed.js("document.querySelector(\"#infoWorld .iGrp[data-out='o2']\").classList.contains('outInactive')"), 'o2 は休止の見た目')
    # Undo: アクティブの切替も1動作
    undo(ed)
    t.eq(info_graph(ed)["activeOut"], 'o2', 'Undoでアクティブが o2 に戻る')
    # o2 を消す → o1 がアクティブに
    select_node(ed, 'out:o2')
    hover_info(ed)
    ed.key('Delete')
    wait_until(ed, "Object.keys(window._dbgApp.infoGraph().outs).length===1", label='o2 の削除')
    g = info_graph(ed)
    t.eq((g["activeOut"], list(g["outs"])), ('o1', ['o1']), '残るのは o1 でアクティブ')
    t.ok(all(e["o"] != 'o2' for e in g["edges"]), 'o2 への配線も消える')
    t.no_errors()


def test_info_last_out_cannot_delete(t):
    '''最後の書き出しノードは消せない（お知らせが出て、ノードも配線も残る）'''
    ed = _rich_info(t)
    before = info_graph(ed)
    select_node(ed, 'out:o1')
    hover_info(ed)
    ed.key('Delete')
    wait_until(ed, "(()=>{const e=document.getElementById('errToast');return !!e&&e.style.display!=='none'&&e.textContent.includes('最後')})()",
               label='お知らせ')
    t.ok('最後の書き出しノードは消せません' in toast(ed), f'お知らせ: {toast(ed)}')
    t.eq(info_graph(ed)["outs"], before["outs"], '書き出しノードは残る')
    t.eq(edges(ed), sorted((e["s"], e["o"]) for e in before["edges"]), '配線も残る')
    errs = ed.errors()   # お知らせは console.error にも出る＝それ以外のエラーが無いこと
    t.ok(all('最後の書き出しノードは消せません' in e for e in errs), f'想定外のエラー: {errs}')


def test_info_prev_stepper_and_export(t):
    '''試聴ノード: ‹›で±1秒・Shift+‹›で±0.1秒・数値クリックで手入力。値は書き出しの Info.dat に出て、Undoで戻る'''
    ed = _rich_info(t)
    P = "#infoWorld .iGrp[data-node='p1']"
    st = lambda: ed.js("window._dbgApp.infoGraph().nodes.p1.data")   # noqa: E731
    t.eq(st(), {'start': 4, 'dur': 6}, '準備: 試聴の初期値')
    click_sel(ed, f"{P} .pvF[data-f2='start'] .bfA[data-k='up']")
    t.eq(st()['start'], 5, '開始 › で +1')
    p = center(ed, f"{P} .pvF[data-f2='start'] .bfA[data-k='up']")
    ed.click(p["x"], p["y"], shift=True)
    wait_until(ed, "window._dbgApp.infoGraph().nodes.p1.data.start===5.1", label='開始 Shift+› で +0.1')
    click_sel(ed, f"{P} .pvF[data-f2='dur'] .bfA[data-k='dn']")
    t.eq(st()['dur'], 5, '長さ ‹ で -1')
    # 数値クリック → 手入力
    click_sel(ed, f"{P} .pvF[data-f2='dur'] .bfV")
    wait_until(ed, f"!!document.querySelector(\"{P} .pvF[data-f2='dur'] .bfV input\")", label='手入力の欄')
    ed.key('a', ctrl=True)
    type_text(ed, '7.5')
    ed.key('Enter')
    wait_until(ed, "window._dbgApp.infoGraph().nodes.p1.data.dur===7.5", label='長さの手入力')
    t.eq(ed.js("window._dbgApp.prev()['infoStart']"), 5.1, '曲情報へ反映（開始）')
    d = _info_dat(ed)
    t.eq((d['_previewStartTime'], d['_previewDuration']), (5.1, 7.5), 'Info.dat の試聴区間')
    # 下限: 長さは0.5秒未満にならない
    p = center(ed, f"{P} .pvF[data-f2='dur'] .bfA[data-k='dn']")
    for _ in range(10):
        ed.click(p["x"], p["y"])
    wait_until(ed, "window._dbgApp.infoGraph().nodes.p1.data.dur===0.5", label='長さの下限')
    # Undo
    ed.wait(0.7)   # 連続編集のまとまり（600ms）を切る
    undo(ed)
    t.ok(st()['dur'] > 0.5, f"Undoで長さが戻る: {st()}")
    t.no_errors()


def test_info_prev_play_toggle(t):
    '''試聴ノードの「▶ 試聴」で再生が始まり、「■ 停止」で止まる。再生中にノードを消すと止まる'''
    ed = _rich_info(t)
    btn = "#infoWorld .iGrp[data-node='p1'] .pvPlay"
    q = json.dumps(btn)
    t.eq(ed.js(f"document.querySelector({q}).textContent.trim()"), '▶ 試聴', '準備: ボタンの表示')
    click_sel(ed, btn)
    wait_until(ed, "window._dbgApp.prev().playing", label='試聴の再生')
    t.eq(ed.js("window._dbgApp.prev().id"), 'p1', '再生しているノード')
    wait_until(ed, f"document.querySelector({q}).textContent.includes('停止')", label='ボタンが「停止」に')
    click_sel(ed, btn)
    wait_until(ed, "!window._dbgApp.prev().playing", label='停止')
    t.ok('試聴' in ed.js(f"document.querySelector({q}).textContent"), 'ボタンが「試聴」に戻る')
    # 再生中に消す
    click_sel(ed, btn)
    wait_until(ed, "window._dbgApp.prev().playing", label='再び再生')
    select_node(ed, 'p1')
    hover_info(ed)
    ed.key('Delete')
    wait_until(ed, "!window._dbgApp.infoGraph().nodes.p1", label='p1 の削除')
    wait_until(ed, "!window._dbgApp.prev().playing", label='削除で再生が止まる')
    t.no_errors()


def test_info_meta_inputs_to_info_dat(t):
    '''曲情報ノードの4欄（曲名・サブ・アーティスト・制作者）の入力が、繋がっていれば書き出しの Info.dat に出る。繋がっていないノードは影響しない'''
    ed = _rich_info(t)
    vals = {'name': '新しい曲名', 'sub': 'サブ題', 'artist': '歌い手X', 'author': '作り手Y'}
    for f, v in vals.items():
        _type_into(ed, 'm2', f, v)
        wait_until(ed, f"window._dbgApp.infoGraph().nodes.m2.data.{f}==={json.dumps(v)}", label=f'{f} の入力')
        ed.wait(0.7)   # 欄ごとに Undo の区切りを分ける（連続編集は600msでまとまる）
    d = _info_dat(ed)
    t.eq((d['_songName'], d['_songSubName'], d['_songAuthorName'], d['_levelAuthorName']),
         (vals['name'], vals['sub'], vals['artist'], vals['author']), 'Info.dat の曲情報')
    # 繋がっていない m1 に入力しても Info.dat は変わらない
    _type_into(ed, 'm1', 'name', '無関係')
    wait_until(ed, "window._dbgApp.infoGraph().nodes.m1.data.name==='無関係'", label='m1 の入力')
    t.eq(_info_dat(ed)['_songName'], vals['name'], '未接続ノードの入力は書き出しに出ない')
    # Undo（m1 → m2 の author の順）
    ed.wait(0.7)
    undo(ed)
    t.eq(info_graph(ed)["nodes"]["m1"]["data"]["name"], '', 'Undoで m1 の入力が戻る')
    undo(ed)
    t.eq(info_graph(ed)["nodes"]["m2"]["data"]["author"], 'NLM Tester', 'Undoで m2 の制作者が元に戻る')
    t.eq(_info_dat(ed)['_levelAuthorName'], 'NLM Tester', 'Info.dat も戻る')
    t.no_errors()

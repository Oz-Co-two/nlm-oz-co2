"""js/core/history.js: 履歴ドメインの委譲層（実装は editor-app.js のクロージャ側）。メソッド一覧と委譲・登録を確認する。"""
HEAD = "const m = await import('/js/core/history.js');\n"


def _js(t, body):
    return t.ed.js("(async () => {" + HEAD + body + "})()")


def test_method_names(t):
    '''methodNames は8個で、クラスに同名メソッドがある（CLAUDE.md: 追加削除時に両方更新する約束）'''
    t.fresh()
    r = _js(t, "const H = m.HistorySystem; return { names: [...H.methodNames], has: H.methodNames.map(n => typeof H.prototype[n]) };")
    t.eq(sorted(r['names']), ['dumpDomain', 'pushHist', 'redo', 'resetHistory', 'restoreDomain', 'selWatch', 'snapshot', 'undo'], 'メソッド一覧')
    t.eq(set(r['has']), {'function'}, '全メソッドがクラスにある')
    t.no_errors()


def test_forwarding(t):
    '''メソッド呼び出しは引数ごと rt の同名関数へ委譲され、戻り値が返る'''
    r = _js(t, """
const calls = [], rt = {};
for (const n of m.HistorySystem.methodNames) rt[n] = (...a) => { calls.push([n, a]); return n + ':' + a.join(','); };
const h = new m.HistorySystem(rt);
return { r1: h.undo(), r2: h.pushHist('x', 2), r3: h.restoreDomain('notes', 'z'), calls: calls.map(c => c[0] + '/' + c[1].length) };""")
    t.eq(r['r1'], 'undo:', 'undo')
    t.eq(r['r2'], 'pushHist:x,2', '引数を渡す')
    t.eq(r['r3'], 'restoreDomain:notes,z', 'restoreDomain')
    t.eq(r['calls'], ['undo/0', 'pushHist/2', 'restoreDomain/2'], '呼び出し回数と引数の数')
    t.no_errors()


def test_install(t):
    '''installHistorySystem は rt.modules.history に登録し、rt にある関数だけ実体へ直接束ねる'''
    r = _js(t, """
const rt = { undo: () => 'U', redo: () => 'R' };
const inst = m.installHistorySystem(rt);
return { same: rt.modules.history === inst, undo: inst.undo(), redo: inst.redo(), own: Object.keys(inst).filter(k => k !== 'rt').sort(),
  missing: (() => { try { return inst.snapshot(); } catch (e) { return 'throws'; } })(),
  keep: (() => { const rt2 = { modules: { other: 1 } }; m.installHistorySystem(rt2); return rt2.modules.other; })() };""")
    t.eq(r['same'], True, '登録')
    t.eq((r['undo'], r['redo']), ('U', 'R'), '束ねた関数が動く')
    t.eq(r['own'], ['redo', 'undo'], 'rtに無い関数は束ねない')
    t.eq(r['missing'], 'throws', 'rtに無い関数の呼び出しは例外（委譲先が無い）')
    t.eq(r['keep'], 1, '既存の rt.modules は壊さない')
    t.no_errors()

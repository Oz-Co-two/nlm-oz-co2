"""BPMの自動判定（音量フェーダー下の「BPM測定」ボタン・テンポパートの「全パート自動判定」/右クリック「自動判定」）。
素材 basic.wav は 120BPM（拍ごとのクリック音・16秒）。判定は estimateBPM（オンセット包絡の自己相関＋コムフィルタ）。"""
import json

from misc_helpers import center, fresh_page, hover_3d, open_fixture_ready as open_fixture, toast, wait_until
from project_helpers import forget_errors, menu_pick

# 判定の精度: 区間12秒・フレーム11.6msの分解能なので 0.5BPM（約0.4%）までを「合っている」とする
TOL = 0.5


def _estimate(ed, t0=None, t1=None):
    """estimateBPM を直接呼ぶ（区間の秒を省くと曲全体）。{cands:[{bpm,conf}], drift}。例外は {'error': 文言}"""
    args = "" if t0 is None else f"{t0},{t1}"
    return ed.js(f"(()=>{{ try{{ return window._dbg.rt.estimateBPM({args}); }}catch(e){{ return {{error:e.message}}; }} }})()")


def _near(bpm, want, tol=TOL):
    return abs(bpm - want) <= tol


def _tempo(ed):
    return ed.js("JSON.parse(window._dbg.rt.buildProjectText()).tempoParts")


def _add_tempo_part(ed, beat):
    """テンポ帯をダブルクリックして拍 beat にテンポパートを追加する（追加直後は今のテンポを引き継ぐ）。追加した後のテンポパートの数を返す"""
    n0 = len(_tempo(ed))
    s = ed.js(f"window._dbgApp.nleScreen({beat})")
    ty = (s["tempo"] + s["marker"]) / 2
    ed.click(s["x"], ty); ed.click(s["x"], ty, count=2)
    wait_until(ed, f"JSON.parse(window._dbg.rt.buildProjectText()).tempoParts.length==={n0 + 1}", label=f"拍{beat}のテンポパート追加")
    return n0 + 1


def _set_part_bpm(ed, beat, bpm):
    """既存の◆をダブルクリック＝BPMの手入力（インライン入力欄）"""
    s = ed.js(f"window._dbgApp.nleScreen({beat})")
    ty = (s["tempo"] + s["marker"]) / 2
    ed.click(s["x"] + 3, ty); ed.click(s["x"] + 3, ty, count=2)
    wait_until(ed, "document.activeElement&&document.activeElement.tagName==='INPUT'", label="BPMの入力欄")
    ed.key("a", ctrl=True)
    ed.call("Input.insertText", text=str(bpm))
    ed.key("Enter")
    wait_until(ed, f"JSON.parse(window._dbg.rt.buildProjectText()).tempoParts.some(p=>p.beat==={beat}&&p.bpm==={bpm})", label=f"拍{beat}のBPM={bpm}")


def _click_detect_all(ed):
    p = center(ed, "#tempoDetectAllBtn")
    assert p, "「全パート自動判定」ボタンが表示されていません"
    ed.click(p["x"], p["y"])


def _stat(ed):
    return ed.js("document.getElementById('stat').textContent")


def _click_bpm_button(ed):
    p = center(ed, "#vmBpmBtn")
    assert p, "BPM測定のボタンが表示されていません"
    ed.click(p["x"], p["y"])


def test_estimate_candidates_for_120_click(t):
    '''estimateBPM: 120BPMのクリック音は、候補（最大3つ）のどれかが120±0.5。候補は55〜220の範囲で一致度は5〜99%・テンポ揺れ無し。6秒未満の区間は「区間が短すぎます」で止まる'''
    ed = open_fixture(t, 'basic')
    r = _estimate(ed)
    t.ok('error' not in r, f'判定が例外で止まった: {r}')
    cands = r['cands']
    t.ok(1 <= len(cands) <= 3, f'候補は1〜3個: {cands}')
    t.ok(any(_near(c['bpm'], 120) for c in cands), f'候補に120（±{TOL}）が入る: {cands}')
    for c in cands:
        t.ok(55 <= c['bpm'] <= 220, f'候補は55〜220BPMの範囲: {c}')
        t.ok(5 <= c['conf'] <= 99, f'一致度は5〜99%: {c}')
    t.eq(len({round(c['bpm']) for c in cands}), len(cands), '同じテンポの重複候補は出さない')
    t.eq(r['drift'], False, '一定テンポの曲はテンポ揺れ無し')
    # 区間指定（先頭8秒・後半8秒）でも120が候補に入る
    for a, b in ((0, 8), (8, 16)):
        rr = _estimate(ed, a, b)
        t.ok('error' not in rr and any(_near(c['bpm'], 120) for c in rr['cands']), f'{a}〜{b}秒の候補に120: {rr}')
    # 区間が短い（6秒未満）と止まる
    t.eq(_estimate(ed, 3, 8), {'error': '区間が短すぎます（6秒以上必要）'}, '5秒の区間は判定できない')
    r7 = _estimate(ed, 0, 7)
    t.ok('error' not in r7, f'7秒なら判定できる: {r7}')
    t.no_errors()


def test_bpm_button_without_audio(t):
    '''曲を読み込んでいない時にBPM測定ボタン・「全パート自動判定」を押すと、どちらも「先に曲を読み込んでください」と出る（候補メニューは出ない）'''
    ed = fresh_page(t)
    wait_until(ed, "!!document.getElementById('vmBpmBtn').onclick", label='BPM測定ボタンの準備（アイコン読込の後に配線される）')
    _click_bpm_button(ed)
    wait_until(ed, "document.getElementById('errToast').style.display==='block'", label='エラーの表示')
    t.ok('先に曲を読み込んでください' in toast(ed), f'エラー文: {toast(ed)}')
    t.eq(ed.js("document.getElementById('ctxmenu').style.display"), 'none', '候補メニューは出ない')
    ed.js("document.getElementById('errToast').style.display='none'")
    wait_until(ed, "document.getElementById('tempoDetectAllBtn').offsetParent!==null", label='全パート自動判定ボタン')
    _click_detect_all(ed)
    wait_until(ed, "document.getElementById('errToast').style.display==='block'", label='エラーの表示')
    t.ok('先に曲を読み込んでください' in toast(ed), f'全パート判定（曲が無い時）: {toast(ed)}')
    forget_errors(ed, '先に曲を読み込んでください')
    t.no_errors()


def test_bpm_button_menu_apply(t):
    '''BPM測定ボタン→候補メニュー（BPM xx に設定（一致度 n%））→120を選ぶとBPMが120.00になる。ヘッダー表示・未保存ランプ・メッセージも追従'''
    ed = open_fixture(t, 'basic')
    ed.js("window._dbg.rt.setBPMv(100)")   # 判定結果の反映が分かるよう、先に別の値にしておく
    t.eq(ed.js("window._dbgApp.state().BPM"), 100, '準備: BPMを100に')
    hover_3d(ed)
    _click_bpm_button(ed)
    wait_until(ed, "document.getElementById('ctxmenu').style.display==='block'", label='候補メニュー')
    items = ed.js("[...document.querySelectorAll('#ctxmenu button')].map(b=>b.textContent)")
    t.ok(1 <= len(items) <= 4, f'メニュー項目（候補3つ＋揺れの注意）: {items}')
    t.ok(all(i.startswith('BPM ') and '一致度' in i for i in items), f'項目の書式「BPM xx に設定（一致度 n%）」: {items}')
    t.ok(any(i.startswith('BPM 120.00 に設定') or i.startswith('BPM 119.9') or i.startswith('BPM 120.0') for i in items), f'120が候補に: {items}')
    t.eq(ed.js("window._dbgApp.state().BPM"), 100, '選ぶまでBPMは変わらない')
    menu_pick(ed, 'BPM 120.00 に設定')
    wait_until(ed, "window._dbgApp.state().BPM===120", label='BPMの反映')
    t.eq(ed.js("document.querySelector('#bpmField .bfV').textContent"), '120.00', 'ヘッダーのBPM表示')
    t.eq(ed.js("JSON.parse(window._dbg.rt.buildProjectText()).bpm"), 120, '保存内容のBPM')
    wait_until(ed, "window._dbgApp.dirty().lamp===true", label='BPMを変えると未保存になる')
    t.eq(ed.js("document.getElementById('ctxmenu').style.display"), 'none', '選ぶとメニューが閉じる')
    t.ok('BPM = 120' in _stat(ed), f'ステータス: {_stat(ed)}')
    t.no_errors()


def _octave_pick(cands, prev):
    """自動判定が採る候補（editor-app.js の pickTempoOctave と同じ考え方）: 先頭とその倍・半分のうち、直前のテンポに一番近いもの"""
    import math
    top = cands[0]

    def rel(f):
        return next((c for c in cands if abs(c['bpm'] / (top['bpm'] * f) - 1) < 0.04), {'bpm': round(top['bpm'] * f * 100) / 100, 'conf': top['conf']})
    opts = [top] + ([rel(2)] if top['bpm'] * 2 <= 220 else []) + ([rel(0.5)] if top['bpm'] / 2 >= 55 else [])
    best = top
    for o in opts:
        if abs(math.log(o['bpm'] / prev)) < abs(math.log(best['bpm'] / prev)):
            best = o
    return best


def test_tempo_part_detect_all_and_undo(t):
    '''テンポパート（拍8）を90BPMにしてから「全パート自動判定」→判定の候補（倍・半分は直前のテンポ＝120に近い方）が入りメッセージが出る→Undoで90へ戻る→Redoで判定結果へ'''
    ed = open_fixture(t, 'basic')
    _add_tempo_part(ed, 8)
    _set_part_bpm(ed, 8, 90)
    t.eq(_tempo(ed), [{'beat': 8, 'bpm': 90}], '準備: テンポパートを90BPMに')
    expect = _octave_pick(_estimate(ed, 4, 16)['cands'], 120)['bpm']   # 拍8=4秒から曲末(16秒)までが、このパートの範囲。直前のテンポ＝基準の120
    _click_detect_all(ed)
    wait_until(ed, "JSON.parse(window._dbg.rt.buildProjectText()).tempoParts[0].bpm!==90", label='自動判定の反映')
    got = _tempo(ed)[0]['bpm']
    t.eq(got, expect, 'パートの範囲（4〜16秒）の判定の候補（倍・半分は直前のテンポに近い方）が入る')
    t.ok('全パートを自動判定しました（1/1件）' in _stat(ed), f'メッセージ: {_stat(ed)}')
    wait_until(ed, "window._dbgApp.dirty().lamp===true", label='判定すると未保存になる')
    # Undo/Redo（キーはNLEの上で）
    s = ed.js("window._dbgApp.nleScreen(8)")
    ed.move(s["x"], s["lanes"] + 40)
    ed.key('z', ctrl=True)
    wait_until(ed, "JSON.parse(window._dbg.rt.buildProjectText()).tempoParts[0].bpm===90", label='判定のUndo')
    ed.key('z', ctrl=True, shift=True)
    wait_until(ed, f"JSON.parse(window._dbg.rt.buildProjectText()).tempoParts[0].bpm==={json.dumps(got)}", label='判定のRedo')
    t.no_errors()
    # 判定の質: 120BPMのクリック音なので120付近（以前は半分の60を採ることがあった＝estimateBPM に倍テンポの確認を追加）
    t.ok(_near(got, 120), f'120BPMのクリック音の判定が120付近: {got}')


def test_tempo_part_detect_context_menu(t):
    '''テンポパートの◆を右クリック→「🎯 自動判定」: そのパートだけ判定の先頭候補になり、「（拍8）を自動判定: BPM xx（一致度 n%）」と出る'''
    ed = open_fixture(t, 'basic')
    _add_tempo_part(ed, 8)
    _set_part_bpm(ed, 8, 90)
    est = _octave_pick(_estimate(ed, 4, 16)['cands'], 120)   # 倍・半分は直前のテンポ（基準の120）に近い方
    s = ed.js("window._dbgApp.nleScreen(8)")
    ty = (s["tempo"] + s["marker"]) / 2
    ed.click(s["x"] + 3, ty, button='right')
    wait_until(ed, "document.getElementById('ctxmenu').style.display==='block'", label='右クリックメニュー')
    items = ed.js("[...document.querySelectorAll('#ctxmenu button')].map(b=>b.textContent)")
    t.eq(items, ['🎯 自動判定', 'BPMを手入力…', 'テンポパートを削除'], '右クリックメニューの項目')
    menu_pick(ed, '🎯 自動判定')
    wait_until(ed, "JSON.parse(window._dbg.rt.buildProjectText()).tempoParts[0].bpm!==90", label='自動判定の反映')
    t.eq(_tempo(ed), [{'beat': 8, 'bpm': est['bpm']}], '判定の候補（倍・半分は直前のテンポに近い方）が入る')
    t.eq(_stat(ed), f"テンポパート（拍8）を自動判定: BPM {est['bpm']:.2f}（一致度 {est['conf']}%）", 'メッセージ')
    t.no_errors()


def test_tempo_part_detect_too_short(t):
    '''（パートが無い時は「テンポパートがありません」）区間が短すぎる（6秒未満）パートは判定されず値が変わらない／全パートの判定は「0/1件」／右クリックの個別判定は「区間が短すぎます」のエラー'''
    ed = open_fixture(t, 'basic')
    # 曲はあるがテンポパートが無い: 「テンポパートがありません」で何もしない（履歴も積まない）
    undo_a = ed.js("window._dbgApp.state().undo")
    _click_detect_all(ed)
    wait_until(ed, "document.getElementById('stat').textContent.includes('テンポパートがありません')", label='パートが無い時のメッセージ')
    t.eq(ed.js("window._dbgApp.state().undo"), undo_a, '何もしなければ履歴は積まない')
    t.eq(_tempo(ed), [], 'テンポパートは増えない')
    _add_tempo_part(ed, 21)   # 拍21=10.5秒〜曲末16秒＝5.5秒の区間（右端の拍は画面右上のキー一覧に隠れるので避ける）
    _set_part_bpm(ed, 21, 90)
    undo0 = ed.js("window._dbgApp.state().undo")
    _click_detect_all(ed)
    wait_until(ed, "document.getElementById('stat').textContent.includes('全パートを自動判定しました')", label='全パート判定の終了')
    t.ok('（0/1件）' in _stat(ed), f'判定できたパートは0件: {_stat(ed)}')
    t.eq(_tempo(ed), [{'beat': 21, 'bpm': 90}], '短すぎるパートのBPMは変わらない')
    t.eq(ed.js("window._dbgApp.state().undo") - undo0, 1, '全パート判定は1操作として履歴に積む（判定できなくても）')
    s = ed.js("window._dbgApp.nleScreen(21)")
    ty = (s["tempo"] + s["marker"]) / 2
    ed.click(s["x"] + 3, ty, button='right')
    wait_until(ed, "document.getElementById('ctxmenu').style.display==='block'", label='右クリックメニュー')
    menu_pick(ed, '🎯 自動判定')
    wait_until(ed, "document.getElementById('errToast').style.display==='block'", label='エラーの表示')
    t.ok('区間が短すぎます（6秒以上必要）' in toast(ed), f'エラー文: {toast(ed)}')
    t.eq(_tempo(ed), [{'beat': 21, 'bpm': 90}], '個別判定でも値は変わらない')
    forget_errors(ed, '区間が短すぎます')
    t.no_errors()

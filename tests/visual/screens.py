"""画面の崩れ確認で撮る画面の一覧（tests/visual）。

■ 画面の足し方
  SCENES のどれかの screens に Screen(...) を1つ足すだけ。名前(name)は基準画像のファイル名になる（英数字と_）。
  場面(Scene)は「ページを開き直して素材を読む」単位で、その中の画面は上から順に steps を実行しながら撮る
  （前の画面の leave → 次の画面の steps）。開き直しは場面ごとに1回なので、同じ準備から行ける画面は同じ場面にまとめると速い。
  1つの画面だけ -k で選んでも、同じ場面の前の画面の steps/leave は実行される（状態は全部流しと同じになる）。
  足したら一度 `tools/run_tests.py visual -k <題名>` で基準画像を作り（自動で作られる）、test-out/visual/current/<名前>.png を見て
  目的の画面が写っているか確かめる。

■ 手順の部品（steps / leave に並べる）
  click(sel) / rclick(sel or (x,y)) / key(k, at=sel or (x,y), ctrl=, shift=) / tab(pane) / wait(秒) / js(式) / until(式)
  pane は 'nle'（右上: NLE⇄INFO）/ 'main'（下: NOTES⇄LIGHTING）/ 'pv'（左上: MEDIA⇄PREVIEW）。

■ 比較から除く所
  hide: 撮影の間だけ visibility:hidden にする（上に重なる操作部品は写る）。3Dビューの canvas のように中身が揺れる所。
  mask: 位置だけを比較から除く（写りはする）。時刻表示など、変わってよい小さな所。
  どちらも COMMON_* に共通分、Scene / Screen に個別分を書く。
"""

# テスト素材（tools/fixtures/<名前>.nlmf）。rich＝2難易度・ノーツ・ボム・壁・アーク・チェーン・ライト・BPM変化を含む。変えたら --accept で基準画像を作り直す
FIXTURE = 'rich'

SIZE = (1600, 980)          # 既定の画面の大きさ（Scene.size で場面ごとに変えられる）
MOUSE = (2, 978)            # 撮影時のマウス位置（どの操作部品にも乗らない左下の隅）

# 全画面で撮影の間だけ隠すもの
COMMON_HIDE = [
    '#cv',          # 下の3Dビュー（WebGL）。描画が毎回わずかに揺れる。上に重なるツールバー等は写る
    '#pv4host',     # 左上の PREVIEW の3D（WebGL）
    '#perf',        # 描画速度の表示
    '#errToast',    # 「音源を配置しました」等の通知（数秒で消える＝撮る時刻で写ったり写らなかったりする）
]
# 全画面で比較から除く所（写るが比較しない）
COMMON_MASK = [
    '#vmcol',            # 右端の音量メーター。ヘッドレスEdgeが目盛りの所に時々ページ外の丸いアイコンを描く（make_tutorial_shots.py 参照）
    (-20, 0, 20, 4000),  # そのアイコンは右端20pxにはみ出して描かれることもある（x が負＝右端から）
]
# 浮いている層（メニュー・パネル）。この中の部品と外の部品の重なりは「上に出している」とみなす。position:fixed の要素は自動で入る
COMMON_POPUPS = ['#mFileMenu', '#ctxmenu', '.tbpanel', '.ctxsub', '#pie']
# 崩れ検出の対象にしない所
COMMON_IGNORE = ['.__visMark']


class Screen:
    def __init__(self, name, title, steps=(), leave=(), hide=(), mask=(), popups=(), ignore=(), mouse=None, settle=0.3):
        self.name, self.title = name, title
        self.steps, self.leave = list(steps), list(leave)
        self.hide, self.mask, self.popups, self.ignore = list(hide), list(mask), list(popups), list(ignore)
        self.mouse, self.settle = mouse, settle


class Scene:
    def __init__(self, title, fixture, screens, setup=(), size=None, hide=(), mask=()):
        self.title, self.fixture, self.screens = title, fixture, screens
        self.setup, self.size = list(setup), size or SIZE
        self.hide, self.mask = list(hide), list(mask)


# ---- 手順の部品 ----
def _center(ed, sel):
    r = ed.js(f"""(()=>{{const e=[...document.querySelectorAll({sel!r})].find(e=>e.checkVisibility());
        if(!e) return null; const r=e.getBoundingClientRect(); return {{x:r.left+r.width/2,y:r.top+r.height/2}}}})()""")
    if not r:
        raise AssertionError(f"準備の手順: 要素が見つからないか見えていません: {sel}")
    return r['x'], r['y']


def _pos(ed, at):
    return at if isinstance(at, (tuple, list)) else _center(ed, at)


def click(sel, wait_s=0.3):
    def f(ed):
        x, y = _pos(ed, sel)
        ed.click(x, y)
        ed.wait(wait_s)
    f.__name__ = f'click({sel})'
    return f


def rclick(at, wait_s=0.4):
    def f(ed):
        x, y = _pos(ed, at(ed) if callable(at) else at)
        ed.click(x, y, button='right')
        ed.wait(wait_s)
    f.__name__ = f'rclick({getattr(at, "__name__", at)})'
    return f


def key(k, at=None, wait_s=0.25, **mods):
    def f(ed):
        if at is not None:
            x, y = _pos(ed, at)
            ed.move(x, y)
            ed.wait(0.15)
        ed.key(k, **mods)
        ed.wait(wait_s)
    f.__name__ = f'key({k!r}' + (f', at={at}' if at is not None else '') + ''.join(f', {m}' for m, v in mods.items() if v) + ')'
    return f


_PANE = {'nle': '#nodeColBar', 'main': '#mainModeLabel', 'pv': '#pvModeLabel'}


def tab(pane, wait_s=1.0):
    """そのペインの上にマウスを置いて Tab（モード切替）"""
    def f(ed):
        x, y = _center(ed, _PANE[pane]) if pane != 'pv' else _pos(ed, '#pvpane')
        ed.move(x, y)
        ed.wait(0.2)
        ed.key('Tab')
        ed.wait(wait_s)
    f.__name__ = f'tab({pane})'
    return f


def wait(s):
    def f(ed):
        ed.wait(s)
    f.__name__ = f'wait({s})'
    return f


def js(expr, wait_s=0.2, name=None):
    def f(ed):
        ed.js(expr)
        ed.wait(wait_s)
    f.__name__ = name or f'js({" ".join(expr.split())[:70]})'
    return f


def until(expr, timeout=15, what=None):
    def f(ed):
        for _ in range(int(timeout / 0.25)):
            if ed.js(expr):
                ed.wait(0.2)
                return
            ed.wait(0.25)
        raise AssertionError(f"準備の手順: {what or expr} が {timeout} 秒以内に満たされません")
    f.__name__ = f'until({what or expr})'
    return f


def nle_clip_point(ed):
    """NLEのノーツのクリップ（拍1付近・クリップのあるレーン）の位置。レーンがノーツの表示窓の下に隠れていれば見えている所
    （既定の画面では素材 basic のクリップのある一番下の Notes 1 は上の数pxしか見えない）"""
    g = ed.js("window._dbgApp.nleScreen(1)")
    n = ed.js("window._dbgApp.nle()")
    tr = next((c['track'] for c in n['clips'] if c['lk'] == 'n'), len(g['notes']) - 1)
    top, (v0, v1) = g['notes'][tr], n['vp']['n']
    return g['x'], min(max(top + g['laneH'] / 2, max(top + 5, v0 + 2)), min(top + g['laneH'] - 5, v1 - 3))


def bulk_load_start_js():
    """rich_map の「曲データを読み込む」を始める式（終わりを待たない＝途中で確認が出る場面を撮るため）"""
    import importlib.util
    from pathlib import Path
    f = Path(__file__).resolve().parents[2] / "tools" / "fixtures" / "make_fixtures.py"
    spec = importlib.util.spec_from_file_location("nlm_make_fixtures", f)
    mf = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mf)
    js = mf.bulk_load_js("tools/fixtures/rich_map/", list(mf.rich_map_files()), "tools/fixtures/basic.wav")
    return f"window.__bulkP={js};true"


def start_bulk_load(ed):
    """「曲データを読み込む」を始める（終わりを待たない）"""
    ed.js(bulk_load_start_js())


AUDIO_ONLY_JS = """(async()=>{ const blob=await (await fetch('tools/fixtures/basic.wav',{cache:'no-store'})).blob();
  const file=new File([blob],'basic.wav',{type:'audio/wav'});
  await window._dbg.rt.loadSongFromItem({isMusic:true,name:'basic',songFh:{getFile:async()=>file},info:{_beatsPerMinute:120}},0);
  return true; })()"""


def _e2e_helpers():
    import sys
    from pathlib import Path
    lib = str(Path(__file__).resolve().parents[1] / "_lib")
    if lib not in sys.path:
        sys.path.insert(0, lib)
    import e2e_helpers
    return e2e_helpers


def media_lib_setup(ed):
    """MEDIA の記録したライブラリにテスト素材（tools/fixtures/media_lib）を出し、ネット・NLM推定の値（見本）と取得済みの全曲データ（見本の時点）も入れる。
    カバー2枚の読み込みまで待つ"""
    h = _e2e_helpers()
    h.media_lib_load(ed, extra=h.media_lib_sample_extra(), covers=2, details=h.SAMPLE_DETAILS)


def mock_song_details(ed):
    """全曲データの状態の応答を見本（2026-10-12 06:30 時点のデータ）に差し替える（環境設定の MEDIA タブの状態の表示を毎回同じにする）"""
    h = _e2e_helpers()
    h.media_lib_mock(ed, details=h.SAMPLE_DETAILS)


def lib_scroll_to_uploaded(ed):
    """詳細表示の表を横にスクロールして、アップロード日（全曲データに無い曲の「未照合 🔍」）の列を見せる"""
    ed.js("(t=>{ t.scrollLeft=t.querySelector('.ltH[data-col=uploaded]').offsetLeft-150; return 1; })(document.getElementById('libTable'))")
    ed.wait(0.3)


def lib_rate_start(ed):
    """★のまとめての計算を始める（応答は差し替え・window.__rateGo を立てるまで終わらない）: 1行目の右クリック→「絞り込んだ行の★を計算」"""
    h = _e2e_helpers()
    h.media_lib_mock(ed, rate="async b=>{ while(!window.__rateGo) await new Promise(r=>setTimeout(r,50)); return {ok:false,error:'run'}; }")
    r = ed.js("(()=>{ const e=[...document.querySelectorAll('#libTable .ltRow')].find(e=>e._i===0), r=e.getBoundingClientRect(), t=document.getElementById('libTable').getBoundingClientRect();"
              " return {x:t.left+60,y:r.top+r.height/2}; })()")
    ed.click(r['x'], r['y'], button='right')
    ed.wait(0.3)
    p = ed.js("(b=>{ if(!b) return null; const r=b.getBoundingClientRect(); return {x:r.left+r.width/2,y:r.top+r.height/2}; })"
              "([...document.querySelectorAll('#ctxmenu > button')].find(b=>b.textContent.includes('絞り込んだ行の★を計算')))")
    if not p:
        raise AssertionError("準備の手順: 右クリックのメニューに「絞り込んだ行の★を計算」がありません")
    ed.click(p['x'], p['y'])
    ed.wait(0.3)


def lib_head_rclick(ed):
    """詳細表示の見出し（★の列）の位置（右クリックで列のメニュー）"""
    return _center(ed, '#libTable .ltH[data-col=stars]')


def edit_only_on(ed):
    """単独編集: NLE の Notes 2（ノーツの段1）の溝の2段目の帯のスイッチを押す（素材 rich の中身は Notes 3 にある）"""
    b = next(b for b in ed.js("window._dbgApp.nleScreen(0)")['eo'] if b['t'] == 1)
    ed.click(b['x'] + 14, b['y'] + b['h'] / 2)
    ed.wait(0.3)
    if ed.js("window._dbgApp.nle().editOnly") != 1:
        raise AssertionError("準備の手順: 単独編集のスイッチ（Notes 2）が入りません")


def edit_only_click_other(ed):
    """単独編集: 他のレーン（Notes 3）のノーツのうち手前のものをクリックして帯を出す"""
    os_ = [o for o in ed.js("window._dbgApp.objScreen()") if o['kind'] == 'note' and o['inView'] and o['tr'] == 0]
    if not os_:
        raise AssertionError("準備の手順: Notes 3 のノーツが3Dビューに見えていません")
    o = max(os_, key=lambda o: o['sy'])
    ed.move(o['sx'], o['sy'])
    ed.wait(0.15)
    ed.click(o['sx'], o['sy'])
    ed.wait(0.3)


def _link_clip_xy(ed, beat, track=0):
    g = ed.js(f"window._dbgApp.nleScreen({beat})")
    return g['x'], g['notes'][track] + g['laneH'] * 0.7


def link_dup(ed):
    """リンクしたクリップ: Hard のノーツのクリップ（拍0〜16）をコピーして拍20（同じレーン）へ貼り付け、2つを選ぶ"""
    ed.click(*_link_clip_xy(ed, 8)); ed.wait(0.2)
    ed.key('c', ctrl=True); ed.key('v', ctrl=True); ed.wait(0.2)
    x, y = _link_clip_xy(ed, 20)
    ed.move(x, y); ed.wait(0.3); ed.click(x, y); ed.wait(0.4)
    if len([c for c in ed.js("window._dbgApp.nle().clips") if c['lk'] == 'n']) != 2:
        raise AssertionError("準備の手順: クリップの貼り付けができません")
    ed.click(*_link_clip_xy(ed, 8)); ed.wait(0.1)
    ed.click(*_link_clip_xy(ed, 28), shift=True); ed.wait(0.2)


def link_press_k(ed):
    """NLE の上で K（リンクする）"""
    g = ed.js("window._dbgApp.nleScreen(0)")
    ed.move(g['left'] + g['gut'] + 4, g['marker'] - 4); ed.wait(0.15)
    ed.key('k'); ed.wait(0.4)


def link_trim_parent(ed):
    """親（拍0〜16）の右端を拍8へ縮める＝子（拍20〜36）の後ろ8拍が「親より長い空白」（斜線・拍28〜）になる"""
    x0, y = _link_clip_xy(ed, 16)
    x1, _ = _link_clip_xy(ed, 8)
    ed.drag(x0, y, x1, y); ed.wait(0.3)
    ed.click(*_link_clip_xy(ed, 30, 2)); ed.wait(0.2)   # 選択を外す（空いているレーン）


def link_click_kid(ed):
    """3D で子（拍20〜）のノーツをクリックして帯を出す（再生ヘッドを拍20へ）。
    撮影の間は3Dの描画を止めている（vis_page.js の freeze）＝ノーツの位置の行列が古いままでクリックが別の物に当たるので、その間だけ描画を戻す"""
    ed.js("(r=>{ if(r&&r.__visOrigRender&&!r.__visTmp){ r.__visTmp=r.render; r.render=r.__visOrigRender; } return 1; })(window._dbg.rt.renderer)")
    try:
        g = ed.js("window._dbgApp.nleScreen(20)")
        ed.click(g['x'], g['ruler'] + 6); ed.wait(0.8)
        os_ = [o for o in ed.js("window._dbgApp.objScreen()") if o['kind'] == 'note' and o['inView'] and 20 <= o['beat'] < 32]
        if not os_:
            raise AssertionError("準備の手順: 子のノーツが3Dビューに見えていません")
        o = max(os_, key=lambda o: o['sy'])
        ed.move(o['sx'], o['sy']); ed.wait(0.15)
        ed.click(o['sx'], o['sy']); ed.wait(0.3)
    finally:
        ed.js("(r=>{ if(r&&r.__visTmp){ r.render=r.__visTmp; delete r.__visTmp; } return 1; })(window._dbg.rt.renderer)")


def lib_scroll_to_stars(ed):
    """詳細表示の表を横にスクロールして、難易度・★・NJS の列を見せる（MEDIA は既定の幅では曲名とアーティストまでしか見えない。
    MEDIA を広げると NLE の上の帯が狭くなって崩れるので、広げずに表のほうを動かす）"""
    ed.js("(t=>{ t.scrollLeft=t.querySelector('.ltH[data-col=diff]').offsetLeft-60; return 1; })(document.getElementById('libTable'))")
    ed.wait(0.3)


# ---- 画面の一覧 ----
SCENES = [
    Scene('起動直後', None, [
        Screen('boot', '起動直後の画面（素材なし）'),
        Screen('boot_file_menu', 'ファイルメニュー（素材なし）', steps=[click('#mFileBtn')]),
    ]),
    Scene('通常画面', FIXTURE, [
        Screen('main', '素材を読み込んだ通常画面（MEDIA・NLE・NOTES）'),
        Screen('file_menu', 'ファイルメニュー', steps=[click('#mFileBtn')], leave=[click('#mFileBtn')]),
        Screen('diff_menu', '難易度のメニュー（選択中の難易度をもう一度クリック）',
               steps=[click('#diffBar .dfSeg.on')], leave=[key('Escape'), js("document.getElementById('ctxmenu').style.display='none'")]),
        Screen('snap_panel', 'スナップの一覧（ツールバー）', steps=[click('#tbSnapBtn')], leave=[click('#tbSnapBtn')]),
        Screen('dir_panel', 'ノーツの向きの一覧（ツールバー）', steps=[click('#tbModeNote')], leave=[click('#tbModeNote')]),
        Screen('env_panel', '環境（ステージ）の一覧', steps=[click('#sqEnvBtn')], leave=[click('#sqEnvBtn')]),
        Screen('color_panel', 'ノーツ色のカラーパレット', steps=[click('#tbColSw')], leave=[key('Escape'), js("document.getElementById('cpanel')?.remove()")]),
        Screen('clip_menu', 'NLEのクリップの右クリックメニュー', steps=[rclick(nle_clip_point)],
               leave=[js("document.getElementById('ctxmenu').style.display='none'")]),
    ]),
    Scene('LIGHTING', FIXTURE, [
        Screen('lighting', 'LIGHTING（下の3DビューでTab）', steps=[tab('main')]),
        Screen('auto_light_dialog', '自動ライティングの確認画面', steps=[click('#tbAutoLight'), until("!!document.getElementById('dirtyDlg')")]),
    ]),
    Scene('INFO', FIXTURE, [
        Screen('info', 'INFO（曲情報・難易度・カバー・試聴・書き出しノード）', steps=[tab('nle', 1.5)]),
    ]),
    Scene('PREVIEW', FIXTURE, [
        Screen('preview', 'PREVIEW（左上でTab）', steps=[tab('pv', 1.5)]),
    ]),
    Scene('環境設定', FIXTURE, [
        Screen('settings_app', '環境設定: アプリケーション設定', steps=[click('#mbSettings', 0.6)]),
        Screen('settings_vol', '環境設定: 音量設定', steps=[click('#settingsBox .setTab[data-tab=vol]')]),
        Screen('settings_preview', '環境設定: Preview設定', steps=[click('#settingsBox .setTab[data-tab=preview]')]),
        Screen('settings_cam', '環境設定: カメラ設定', steps=[click('#settingsBox .setTab[data-tab=cam]')]),
        Screen('settings_keys', '環境設定: ショートカット編集', steps=[click('#settingsBox .setTab[data-tab=keys]')]),
        Screen('settings_media', '環境設定: MEDIA（全曲データ・★の計算の同時の数・ゲームのプレイ記録）',
               steps=[mock_song_details, click('#settingsBox .setTab[data-tab=media]', 0.6),
                      until("window._dbgApp.libOnline().prefs.netState.includes('時点')", what='全曲データの状態')],
               mask=['#libPlayPath']),   # プレイ記録の既定の場所＝テストの一時のデータフォルダ（毎回違う）
    ]),
    Scene('譜面チェック', FIXTURE, [
        Screen('mapcheck', '譜面チェックのパネル（BS Map Check）',
               steps=[click('#mFileBtn'), click('#mFileMenu button[data-act=mapcheck]'), until("!!document.querySelector('#mcPanel .mcSum')")]),
        Screen('mapcheck_bl', '譜面チェックのパネル（NLM版 BL評価リスト）', steps=[click('#mcPanel .mcTab[data-tab=bl]', 1.0)]),
        Screen('mapcheck_bl_stars', 'BL評価リスト: R5.A の★/Tech の欄（プラグイン未導入・取り込みの説明）',
               steps=[until("!!document.querySelector('#mcPanel .blRtOpen')"),
                      js("(()=>{document.querySelector('#mcPanel .blStarsBox').scrollIntoView({block:'center'});return 1})()", 0.3, name='R5.A の欄までスクロール'),
                      click('#mcPanel .blRtOpen'),
                      js("(()=>{document.querySelector('#mcPanel .blStarsBox').scrollIntoView({block:'center'});return 1})()", 0.3, name='説明が見える位置へ')]),
    ]),
    Scene('曲データの読込', None, [
        Screen('tempo_import_dialog', '曲データを読み込む: BPM変化の取り込みの確認（音源が既にある時）',
               steps=[js(AUDIO_ONLY_JS, 0.5, name='音源だけを読む(AUDIO_ONLY_JS)'), start_bulk_load, until("!!document.getElementById('dirtyDlg')")]),
    ]),
    Scene('MEDIAライブラリ', None, [
        Screen('media_lib_grid', 'MEDIA: 記録したライブラリ（グリッド・件数）'),
        Screen('media_lib_detail', 'MEDIA: 詳細表示（1行＝1難易度・★の BL／NLM推定。表を横にスクロール）',
               steps=[click('#libViewSeg button[data-view=detail]', 0.5), lib_scroll_to_stars]),
        Screen('media_lib_cols', 'MEDIA: 詳細表示の列のメニュー（見出しの右クリック）', steps=[rclick(lib_head_rclick)],
               leave=[key('Escape'), js("document.getElementById('libColMenu')?.remove();true")]),
        Screen('media_lib_net', 'MEDIA: 全曲データに無い曲の「未照合 🔍」・全曲データの出どころ（左下）', steps=[lib_scroll_to_uploaded]),
        Screen('media_lib_look', 'MEDIA: 🔍 の確認（BeatSaver へ送る前）',
               steps=[click('#libTable .ltLook', 0.4), until("!!document.getElementById('dirtyDlg')", what='🔍 の確認')],
               leave=[click('#dirtyDlg button:not(.pri)')]),
        Screen('media_lib_rate', 'MEDIA: ★のまとめての計算の途中（「★を計算中」の帯と［中止］・行の「計算中…」）',
               steps=[lib_scroll_to_stars, lib_rate_start, until("!!window._dbgApp.libOnline().rate.bar", what='★の計算中の帯')],
               leave=[js("window.__rateGo=true;true"), until("!window._dbgApp.libOnline().rate.running", what='★の計算の終わり')]),
        Screen('media_lib_filter', 'MEDIA: 絞り込みのパネル（★5以上・Standard）',
               steps=[click('#libFiltBtn', 0.4),
                      js("(i=>{ i.value='5'; i.dispatchEvent(new Event('input')); return 1; })(document.querySelector('#libFiltPanel .lfRow[data-k=stars] .lfLo'))", 0.4,
                         name='★の下限に5')]),
        Screen('media_lib_font', 'MEDIA: 詳細表示の文字を大きく（大きさのスライダー＝16px）・フィルターの条件の数の丸（★5以上＝1）',
               steps=[click('#libFiltPanel .lfClose', 0.2),
                      js("(s=>{ s.value=16; s.dispatchEvent(new Event('input')); return 1; })(document.getElementById('libSize'))", 0.4, name='文字の大きさを16px'),
                      lib_scroll_to_stars]),
    ], setup=[media_lib_setup]),
    Scene('単独編集', FIXTURE, [
        Screen('edit_only', '単独編集: Notes 2 をオン（溝の2段目の帯＝オンは深緑・オフは灰色・レーンのうっすらした色・3Dの左下の「✎ 単独編集: Notes 2」）',
               steps=[edit_only_on]),
        Screen('edit_only_band', '単独編集: 他のレーンのノーツをクリックした時の帯（3Dの上・ツールバーの下）',
               steps=[edit_only_click_other, until("document.getElementById('eoBand').classList.contains('on')", what='単独編集の帯')],
               popups=['#eoBand']),   # 帯は3Dの上に浮かぶ層（早見表の上に重なってよい・少しで消える）
    ]),
    Scene('リンクしたクリップ', FIXTURE, [
        Screen('link_parent_dialog', 'リンク: 2つを選んで K → 親を選ぶ画面（名前・拍・曲の時刻・レーン・難易度・ノーツ数・消えるノーツの数）',
               steps=[link_dup, link_press_k, until("!!document.querySelector('#dirtyDlg[data-lk=parent-link]')", what='親を選ぶ画面')],
               leave=[click('#dirtyDlg .ddBtns button.pri', 0.5), until("window._dbgApp.nle().clips.filter(c=>c.link).length===2", what='リンク')]),
        Screen('link_nle', 'リンク: NLE の 🔗 と数・子の点線の枠・親より長い所の斜線（親の右端を縮めた。NLE の早見表はたたむ＝子が隠れないように）',
               steps=[link_trim_parent, click('#nodeKeys .mkFold')]),
        Screen('link_band', 'リンク: 3Dで子のノーツをクリックした時の帯（［親へジャンプ］［リンクを解除］［そのまま］）',
               steps=[link_click_kid, until("(e=>!!e&&e.classList.contains('on'))(document.getElementById('lkBand'))", what='子の帯')],
               popups=['#lkBand']),   # 帯は3Dの上に浮かぶ層（少しで消える）
        Screen('link_copy_dialog', 'リンク: 難易度間コピーの確認の画面（上書きの注意・「親の難易度に繋ぐ」・繋いだ時の注意）',
               steps=[js("(e=>{ if(e) e.classList.remove('on'); return true; })(document.getElementById('lkBand'))", 0.1, name='帯を消す'),
                      click('#diffBar .dfSeg.on'), click("#ctxmenu button:nth-child(1)", 0.4),
                      js("(b=>{ b.dispatchEvent(new MouseEvent('click',{bubbles:true})); return 1; })([...document.querySelectorAll('#ctxmenu .ctxsub button')].find(b=>b.textContent.includes('Expert')))", 0.4, name='→ Expert'),
                      until("!!document.querySelector('#dirtyDlg[data-lk=copy]')", what='コピーの確認の画面')]),
    ]),
    Scene('難易度を測る', FIXTURE, [
        Screen('rating', '難易度を測るのパネル（プラグイン未導入）',
               steps=[click('#mFileBtn'), click('#mFileMenu button[data-act=rating]'),
                      until("!!document.querySelector('#rtPanel .rtTable, #rtPanel .rtIntro, #rtPanel .rtErr')")]),
    ]),
]


# ---- 曲の解析（2026-10-19・js/analysis/song-analysis.js）: 応答は偽物（tests/_lib/analysis_helpers.py）。帯はスペクトログラムの箱の上の段 ----
def _ana():
    import analysis_helpers   # tests/_lib（nlmtest が読み込み先に足している）
    return analysis_helpers


def analysis_mock_hold(ed):
    """解析の応答を偽物にする。テンポの進み具合は 40% の所で止める（window.__ana.go.t で続き）"""
    A = _ana()
    A.ana_mock(ed, status_t1=[{"ok": True, "state": "running", "stage": "tempo", "progress": 0.4},
                              {"waitFor": "t", "then": A.status_seq("tempo", A.TEMPO)[-1]}])


def analysis_band_rclick(ed):
    """帯のセクション S2（拍10）の位置（右クリックでメニュー）"""
    g = ed.js("window._dbgApp.anaScreen(10)")
    return g['x'], g['sec']


def analysis_open_clips(ed):
    """帯のセクションの右クリック→「クリップを作る…」"""
    _ana().open_clips(ed, via='band')


SCENES.append(Scene('曲の解析', FIXTURE, [
    Screen('analysis_running', '曲の解析: 解析中（帯に進み具合と［やめる］・スペクトログラムは帯の下へ詰める）',
           steps=[analysis_mock_hold, click('#anaStartBtn'),
                  until("window._dbgApp.analysis().msg.includes('40%')", what='解析中の帯')]),
    Screen('analysis_tempo', '曲の解析: テンポの推定の画面（提案・今の設定・2倍/半分・2番目の候補・段差・揺れ・裏拍と候補B・注意書き）',
           steps=[js("window.__ana.go.t=true;true", name='テンポの続き'), until("!!document.querySelector('#dirtyDlg.anaTempo')", what='テンポの画面')]),
    Screen('analysis_band', '曲の解析: 解析の帯（上＝セクション「名前＋番号」・★＝サビの候補／下＝細かい区切り）',
           steps=[click('#dirtyDlg.anaTempo button[data-v=none]'),
                  until("(a=>a.shown&&!a.running&&a.msg==='')(window._dbgApp.analysis())", what='解析の帯')]),
    Screen('analysis_menu', '曲の解析: 帯の右クリックのメニュー（名前の付け直し・クリップを作る・マーカーへ書き出す・テンポの推定結果・解析し直す・結果を消す）',
           steps=[rclick(analysis_band_rclick)], leave=[js("document.getElementById('ctxmenu').style.display='none'")]),
    Screen('analysis_stale', '曲の解析: 目盛りが変わった時の知らせ（BPM を変えた・帯は薄く）',
           steps=[click('#bpmField .bfA[data-k=up]'), until("window._dbgApp.analysis().stale", what='目盛りが変わった知らせ')]),
    # 解析からクリップを作る（2026-10-19・js/analysis/ana-clips.js）: 目盛りを戻してから
    Screen('analysis_clips_dialog', '曲の解析: 解析からクリップを作る画面（単位＝両方・単独編集にするレーン・作る難易度に Expert・自動リンク・親の編集の注意・まとめ）',
           steps=[click('#bpmField .bfA[data-k=dn]'), until("!window._dbgApp.analysis().stale", what='目盛りを戻す'),
                  analysis_open_clips, until("!!document.querySelector('#dirtyDlg[data-ana=clips]')", what='クリップを作る画面'),
                  click('#dirtyDlg input[name=acUnit][value=both]', 0.2), click("#dirtyDlg .acDiffChk[data-dk='expertstandard.dat']", 0.2)]),
    Screen('analysis_clips_nle', '曲の解析: 作った後の NLE（一番上の2本＝セクション・細かい区切りのクリップ・🔗の数・Notes 5 の単独編集のスイッチ。NLE の早見表はたたむ）',
           steps=[click('#dirtyDlg .ddBtns button.pri', 0.6), until("window._dbgApp.nle().editOnly===0", what='作った'), click('#nodeKeys .mkFold')]),
]))


def analysis_ask_load(ed):
    """曲を取り込んだ時の「曲を解析しますか？」を出す: テストの環境は既定で聞かない（cdp.Editor.TEST_SETTINGS）ので聞く設定にして、別の名前の曲を MEDIA の経路で取り込む"""
    A = _ana()
    A.ask_on(ed)
    A.load_song_media(ed, 'song2.wav')


def analysis_guide_run(ed):
    """解析が終わった時の「次にやること」の案内を出す: テストの環境は既定で出さない（cdp.Editor.TEST_SETTINGS）ので出す設定にして、偽の応答で解析する
    （テンポの確認の画面が出たら「適用しない」）"""
    A = _ana()
    A.guide_on(ed)
    A.ana_mock(ed, tempo=A.TEMPO_SAME)
    A.start_from_menu(ed)
    for _ in range(80):
        if ed.js("!!document.querySelector('#dirtyDlg.anaTempo')"):
            A.dialog_choose(ed, 'none')
        if ed.js("!!document.querySelector('#dirtyDlg[data-ana=guide]')"):
            return
        ed.wait(0.25)
    raise AssertionError("準備の手順: 解析が終わった時の案内が出ません")


# 解析が終わった時の「次にやること」の案内と、溝の［🧩 クリップを作る］（2026-10-20）
SCENES.append(Scene('曲の解析の案内', FIXTURE, [
    Screen('analysis_guide', '曲の解析: 解析が終わった時の「次にやること」の案内（確かめ方の3つの手順・ボタンの場所の画像（赤枠）・次から出さない・［わかった］）',
           steps=[analysis_guide_run, until("(i=>!i||i.complete)(document.querySelector('#dirtyDlg[data-ana=guide] img'))", what='案内の画像')]),
    Screen('analysis_band_clips_btn', '曲の解析: 帯の溝の［🧩 クリップを作る］（案内を閉じた後・光り終わってから。帯の溝だけが下へ延び、スペクトログラムは詰めない）',
           steps=[click('#dirtyDlg[data-ana=guide] .ddBtns button.pri', 0.3), until("!window._dbgApp.analysis().clipsBtn.glow", what='光り終わる')]),
    # 2026-10-20: 一度クリップを作った後は彩度を落とした暗い紫（もう一度押せる）
    Screen('analysis_band_clips_btn_made', '曲の解析: クリップを作った後の溝の［🧩 クリップを作る］（彩度を落とした暗い紫・枠と文字は残す。一番上に作ったレーン）',
           steps=[click('#anaClipsBtn', 0.4), until("!!document.querySelector('#dirtyDlg[data-ana=clips] .ddBtns button')", what='クリップを作る画面'),
                  click('#dirtyDlg .ddBtns button.pri', 0.6), until("window._dbgApp.analysis().clipsBtn.made", what='作った後の印')]),
]))


# 曲を取り込んだ時の「曲を解析しますか？」（2026-10-20）。溝の［🎼 曲を解析］（紫の塗り）は 'main' 等の画面にも写る
SCENES.append(Scene('曲の解析の確認', FIXTURE, [
    Screen('analysis_ask', '曲の解析: 曲を取り込んだ時の「曲を解析しますか？」（解析すると何ができるか・後で解析する入口・次から聞かない・［解析する］［今はしない］）',
           steps=[analysis_ask_load, until("!!document.querySelector('#dirtyDlg[data-ana=ask]')", what='曲を解析しますか')]),
]))

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
    """NLEのノーツのクリップ（拍1付近・クリップのあるレーン）の位置"""
    g = ed.js("window._dbgApp.nleScreen(1)")
    return g['x'], g['notes'][-1] + g['laneH'] / 2


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
    ]),
    Scene('譜面チェック', FIXTURE, [
        Screen('mapcheck', '譜面チェックのパネル（BS Map Check）',
               steps=[click('#mFileBtn'), click('#mFileMenu button[data-act=mapcheck]'), until("!!document.querySelector('#mcPanel .mcSum')")]),
        Screen('mapcheck_bl', '譜面チェックのパネル（NLM版 BL評価リスト）', steps=[click('#mcPanel .mcTab[data-tab=bl]', 1.0)]),
    ]),
    Scene('曲データの読込', None, [
        Screen('tempo_import_dialog', '曲データを読み込む: BPM変化の取り込みの確認（音源が既にある時）',
               steps=[js(AUDIO_ONLY_JS, 0.5, name='音源だけを読む(AUDIO_ONLY_JS)'), start_bulk_load, until("!!document.getElementById('dirtyDlg')")]),
    ]),
    Scene('難易度を測る', FIXTURE, [
        Screen('rating', '難易度を測るのパネル（プラグイン未導入）',
               steps=[click('#mFileBtn'), click('#mFileMenu button[data-act=rating]'),
                      until("!!document.querySelector('#rtPanel .rtTable, #rtPanel .rtIntro, #rtPanel .rtErr')")]),
    ]),
]

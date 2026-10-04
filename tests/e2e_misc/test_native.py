"""exe版（pywebview）だけのネイティブ経路を、ページ内の偽の window.pywebview.api で通すテスト。
実際の絶対パスで出力フォルダ・カバー画像・音源を扱い、プロジェクトに保存したパスから次回はダイアログ無しで自動接続する
（CLAUDE.md「WebView2 / File System Access API の重大な制約」4番）。偽物は app.py の Api と同じ許可範囲で動き、
呼ばれた関数と引数を記録する（misc_helpers.install_fake_pywebview）。song.egg の変換（ffmpeg）は偽物にして呼ばれ方だけ確かめる
（実際の変換は ffmpeg がある環境だけ別テストで通す）。"""
import copy
import json
import shutil
from pathlib import Path

from misc_helpers import (C1, COVER_PATH, OUT, OUT_BASE, SONG_PATH, click_sel, convert_calls, export_click, file_menu,
                          fresh_page, install_fake_fs, install_fake_pywebview, native_add_file_from_url, native_add_png,
                          native_calls, native_file_b64, native_file_text, native_queue, native_state,
                          native_writes, open_fixture_ready, queue_open, stub_convert, to_info, toast,
                          type_text, wait_dialog, wait_until)
from e2e_helpers import export_files, place_at
from info_helpers import hover_info, select_node, undo
from project_helpers import dialog_buttons, dialog_click, forget_errors

GOLDEN = Path(__file__).resolve().parents[1] / "golden" / "export" / "rich"
WAV_SIZE = (Path(__file__).resolve().parents[2] / "tools" / "fixtures" / "basic.wav").stat().st_size
OTHER = "D:\\Other\\CustomLevels"


def _golden(name):
    return json.loads((GOLDEN / name).read_text(encoding="utf-8"))


def _start(t, fx="rich", view="info"):
    """素材を読み、偽の pywebview を差す。view='info' なら INFO を開く"""
    ed = open_fixture_ready(t, fx)
    install_fake_pywebview(ed)
    if view == "info":
        to_info(ed)
    return ed


def _set_lead_in(ed, ms):
    """ヘッダーの「無音追加」の値をクリック→数値を入力→Enter（NLE表示の時）"""
    click_sel(ed, "#leadInField .bfV", "無音追加の値")
    wait_until(ed, "!!document.querySelector('#leadInField .bfV input')", label="無音追加の入力欄")
    ed.key("a", ctrl=True)
    type_text(ed, str(ms))
    ed.key("Enter")
    wait_until(ed, f"JSON.parse(window._dbg.rt.buildProjectText()).graph.song.offset===-{ms / 1000}", label=f"無音追加 {ms}ms")


def _to_nle(ed):
    """INFO→NLE（INFOの上にマウスを置いて Tab）"""
    hover_info(ed)
    ed.key("Tab")
    wait_until(ed, "window._dbgApp.view()==='nle'", label="NLEへの切替")


def _pick_out(ed, path=OUT_BASE):
    """出力ノード(o1)の「出力フォルダを選択」を押し、path が選ばれて接続するまで待つ"""
    native_queue(ed, "folder", path)
    click_sel(ed, f"{OUT} .oPick", "出力フォルダを選択")
    wait_until(ed, f"window._dbgApp.infoGraph().outs.o1.outDirPath==={json.dumps(path)}", label="出力フォルダの接続")


def _pick_cover(ed, path=COVER_PATH):
    native_queue(ed, "image", path)
    click_sel(ed, f"{C1} .nPick", "カバーの「画像を選択」")
    wait_until(ed, f"window._dbgApp.infoGraph().nodes.c1.data.nativePath==={json.dumps(path)}", label="カバー画像の接続")


def _export_and_wait(ed, folder="natexp"):
    """出力フォルダ名を入れて書き出し、完了のメッセージが出るまで待つ"""
    ed.js("document.getElementById('errToast').style.display='none'")
    export_click(ed, folder)
    wait_until(ed, "document.getElementById('errToast').style.display==='block'&&/書き出しました|書き出し失敗|書き出せません/.test(document.getElementById('errToast').textContent)",
               label="書き出しの完了メッセージ")
    return toast(ed)


def _names(ed, dest):
    """fs_write で書かれたファイル名（dest の直下のものだけ）"""
    pre = dest.lower() + "\\"
    return sorted(p[len(dest) + 1:] for p in native_writes(ed) if p.lower().startswith(pre))


def _calls(ed, *fns):
    return [(c["fn"], *c["args"]) for c in native_calls(ed, *fns)]


def _text(ed, path):
    return native_file_text(ed, path)


def _wait_calls(ed, n, fn):
    wait_until(ed, f"window.__nat.calls.filter(c=>c.fn==={json.dumps(fn)}).length>={n}", label=f"{fn} が呼ばれる")


# ---------------------------------------------------------------- 出力フォルダ
def test_native_pick_out_folder(t):
    '''出力フォルダの選択（ネイティブ）: キャンセルは何も変えず履歴も積まない／選ぶと実パスが保存される／2回目は保存済みパスを開始位置に渡す／同名の別の場所へ選び直してUndoしても書き出し先が画面と一致する'''
    ed = _start(t)
    select_node(ed, "out:o1")   # 押すとカードが選択される（INFOの選択も履歴に積まれる）ので、先に選んでから数える
    undo0 = ed.js("window._dbgApp.state().undo")
    click_sel(ed, f"{OUT} .oPick", "出力フォルダを選択")   # 偽物のキューが空＝キャンセル
    _wait_calls(ed, 1, "pick_folder")
    ed.wait(0.2)
    o1 = ed.js("window._dbgApp.infoGraph().outs.o1")
    t.eq({k: o1[k] for k in ("folderName", "outDirName", "outDirPath")}, {"folderName": "", "outDirName": "", "outDirPath": ""}, "キャンセルでは変わらない")
    t.eq(ed.js("window._dbgApp.state().undo"), undo0, "キャンセルでは履歴を積まない")
    _pick_out(ed)
    t.eq(_calls(ed, "pick_folder"), [("pick_folder", ""), ("pick_folder", "")], "最初は開始位置なし（保存済みパスが無い）")
    o1 = ed.js("window._dbgApp.infoGraph().outs.o1")
    t.eq((o1["outDirName"], o1["outDirPath"]), ("CustomLevels", OUT_BASE), "出力フォルダの名前と実パス")
    t.ok(ed.js(f"document.querySelector('{OUT} .oPick').textContent").endswith("CustomLevels"), "ボタンに選んだフォルダ名")
    t.eq(ed.js("window._dbgApp.state().undo"), undo0 + 1, "選ぶと1操作として履歴に積む")
    pj = json.loads(ed.js("window._dbg.rt.buildProjectText()"))
    t.eq(pj["infoGraph"]["outs"]["o1"]["outDirPath"], OUT_BASE, "プロジェクトに実パスが保存される")
    # 2回目: 保存済みのパスを開始位置にしてダイアログを開く（旧: ブラウザが覚えた古い場所で開いていた）
    _pick_out(ed, OTHER)   # フォルダ名は同じ（CustomLevels）で場所が違う
    t.eq(_calls(ed, "pick_folder")[-1], ("pick_folder", OUT_BASE), "2回目は今の出力先を開始位置に渡す")
    o1 = ed.js("window._dbgApp.infoGraph().outs.o1")
    t.eq((o1["outDirName"], o1["outDirPath"]), ("CustomLevels", OTHER), "選び直した出力先")
    # Undo: 画面の出力先が前のパスへ戻る。書き出しは画面の出力先（または未接続）と一致しなければならない
    stub_convert(ed)
    undo(ed)
    wait_until(ed, f"window._dbgApp.infoGraph().outs.o1.outDirPath==={json.dumps(OUT_BASE)}", label="Undoで前のパスへ戻る")
    _export_and_wait(ed, "undotest")
    wrote = sorted(native_writes(ed))
    shown = ed.js("window._dbgApp.infoGraph().outs.o1.outDirPath")
    bad = [p for p in wrote if not p.lower().startswith(shown.lower() + "\\")]
    forget_errors(ed, "書き出せません")   # Undoで未接続になると「書き出せません」の案内が出る（それも正しい動き）
    t.ok(not bad, f"書き出し先が画面の出力先（{shown}）と一致し、選び直した方（{OTHER}）へは書かない: {bad[:3]}")
    t.no_errors()


# ---------------------------------------------------------------- 書き出し
def test_native_export_files(t):
    '''ネイティブの出力フォルダへ書き出す: fs_* 経由で Info.dat・各難易度.dat・song.egg・変換のマーカーが実パスに書かれ、中身はダウンロード書き出しの正解と同じ。変換に失敗（ffmpeg無し）しても譜面は書き、案内を出す'''
    ed = _start(t)
    stub_convert(ed)
    _pick_out(ed)
    msg = _export_and_wait(ed, "natexp")
    dest = OUT_BASE + "\\natexp"
    t.eq(_names(ed, dest), ['.nlm-egg.json', 'ExpertStandard.dat', 'HardStandard.dat', 'Info.dat', 'song.egg'], "書かれたファイル")
    t.ok(all(p.lower().startswith(OUT_BASE.lower() + "\\natexp\\") for p in native_writes(ed)), "すべて出力フォルダ名のサブフォルダの中")
    t.eq(_calls(ed, "fs_subdir"), [("fs_subdir", OUT_BASE, "natexp", True)], "サブフォルダは出力先の下に1回だけ作る")
    for name in ("Info.dat", "HardStandard.dat", "ExpertStandard.dat"):
        t.eq(json.loads(_text(ed, dest + "\\" + name)), _golden(name), f"{name} の中身はダウンロード書き出しの正解と同じ")
    egg = native_writes(ed)[dest + "\\song.egg"]
    t.eq((egg["size"], egg["head"]), (64, [0x4F, 0x67, 0x67, 0x53]), "song.egg は変換結果（OggS）")
    conv = convert_calls(ed)
    t.eq(len(conv), 1, "変換は1回")
    t.eq((conv[0]["url"], conv[0]["method"], conv[0]["headers"], conv[0]["head"]),
         ("__convert/toOgg?ext=wav", "POST", {"X-NLM-Request": "1"}, [0x52, 0x49, 0x46, 0x46]), "変換の呼び方（POST・拡張子・CSRF対策ヘッダー・wavのバイト列）")
    mark = json.loads(_text(ed, dest + "\\.nlm-egg.json"))
    t.eq((mark["name"], mark["size"], mark["leadInMs"]), ("basic.wav", WAV_SIZE, 0), "変換のマーカー（音源の名前・大きさ・無音追加）")
    t.ok("「natexp」に Info.dat / HardStandard.dat / ExpertStandard.dat / song.egg" in msg, f"完了メッセージ: {msg}")
    # 変換に失敗（ffmpegが無い）: 譜面は書き、song.egg とマーカーは書かず、インストールの案内を出す
    stub_convert(ed, "ffmpeg-not-found")
    msg = _export_and_wait(ed, "noffmpeg")
    t.eq(_names(ed, OUT_BASE + "\\noffmpeg"), ['ExpertStandard.dat', 'HardStandard.dat', 'Info.dat'], "変換に失敗しても譜面は書かれ、song.egg とマーカーは無い")
    t.ok("ffmpegが見つかりません" in msg and "winget install Gyan.FFmpeg" in msg, f"インストールの案内: {msg}")
    t.ok("song.egg" not in msg.split("に", 1)[-1].split("※")[0], f"書いたファイルの一覧に song.egg は出ない: {msg}")
    t.no_errors()


def test_native_export_egg_cache_lead_in_force(t):
    '''song.egg の再変換: 2回目の書き出しは変換しない（マーカーが同じ）。無音追加250msにすると変換し直し（クエリに leadInMs・Info.datの試聴開始に0.25秒を足す）。「強制再変換」で変換し直す'''
    ed = _start(t)
    stub_convert(ed)
    _pick_out(ed)
    _export_and_wait(ed, "cache")
    t.eq(len(convert_calls(ed)), 1, "1回目は変換する")
    _export_and_wait(ed, "cache")
    t.eq(len(convert_calls(ed)), 1, "2回目は変換しない（音源も無音追加も前回と同じ）")
    t.ok(any(p.endswith("\\song.egg") for p in native_writes(ed)), "song.egg は残っている")
    # 無音追加（ms）: マーカーと違う＝変換し直し。OGGでなくても必ずffmpegで焼き込む
    _to_nle(ed)
    _set_lead_in(ed, 250)
    to_info(ed)
    _export_and_wait(ed, "cache")
    t.eq([c["url"] for c in convert_calls(ed)], ["__convert/toOgg?ext=wav", "__convert/toOgg?ext=wav&leadInMs=250"], "無音追加を変えたら変換し直す（クエリに leadInMs）")
    dest = OUT_BASE + "\\cache"
    t.eq(json.loads(_text(ed, dest + "\\.nlm-egg.json"))["leadInMs"], 250, "マーカーの無音追加")
    t.eq(json.loads(_text(ed, dest + "\\Info.dat"))["_previewStartTime"], 4.25, "試聴開始（元の音源の4秒＋無音追加0.25秒）")
    _export_and_wait(ed, "cache")
    t.eq(len(convert_calls(ed)), 2, "同じ無音追加ならまた変換しない")
    # 強制再変換のチェック（カード生成時の固定要素）
    click_sel(ed, f"{OUT} .oForceEgg", "強制再変換のチェック")
    _export_and_wait(ed, "cache")
    t.eq(len(convert_calls(ed)), 3, "強制再変換にチェックすると変換し直す")
    t.no_errors()


def test_native_export_real_ffmpeg(t):
    '''実際のffmpegで変換（ffmpegがある環境だけ）: song.egg が本物のOGG（先頭 OggS）として書かれる'''
    if not shutil.which("ffmpeg"):
        t.skip("ffmpeg がこのPCのPATHに無い（winget install Gyan.FFmpeg）")
    ed = _start(t)
    _pick_out(ed)
    msg = _export_and_wait(ed, "realegg")
    egg = native_writes(ed).get(OUT_BASE + "\\realegg\\song.egg")
    t.ok(egg is not None, f"song.egg が書かれた: {msg}")
    t.eq(egg["head"], [0x4F, 0x67, 0x67, 0x53], "先頭が OggS")
    t.ok(egg["size"] > 1000, f"中身がある: {egg['size']}")
    t.no_errors()


# ---------------------------------------------------------------- カバー画像
def test_native_cover_pick_and_export(t):
    '''カバー画像（ネイティブ）: 選ぶと実パスと名前がノードに入り表示される→書き出すと cover.png としてバイト単位でそのまま書かれ Info.dat に載る。2回目の選択は保存済みパスを渡す。キャンセルでは変わらず履歴も積まない'''
    ed = _start(t)
    stub_convert(ed)
    b64 = native_add_png(ed, COVER_PATH, 300, 300)
    _pick_cover(ed)
    t.eq(_calls(ed, "pick_image_file"), [("pick_image_file", "")], "最初の選択は開始位置なし")
    c1 = ed.js("window._dbgApp.infoGraph().nodes.c1.data")
    t.eq((c1["name"], c1["nativePath"]), ("cover_src.png", COVER_PATH), "カバーノードの名前と実パス")
    wait_until(ed, f"document.querySelector('{C1} .nThumb').style.display==='block'", label="カバーの見本")
    t.eq(ed.js(f"document.querySelector('{C1} .nCovName').textContent"), "cover_src.png", "ファイル名の表示")
    _pick_out(ed)
    _export_and_wait(ed, "withcover")
    dest = OUT_BASE + "\\withcover"
    t.eq(native_file_b64(ed, dest + "\\cover.png"), b64, "cover.png は元の画像と同じバイト列（補正なし）")
    t.eq(json.loads(_text(ed, dest + "\\Info.dat"))["_coverImageFilename"], "cover.png", "Info.dat のカバー名")
    t.ok("cover.png" in _names(ed, dest), "書かれたファイルに cover.png")
    # 選び直す時は、保存済みのパスを開始位置に渡す
    native_add_png(ed, "C:\\NLMTest\\Art\\other.png", 256, 256)
    _pick_cover(ed, "C:\\NLMTest\\Art\\other.png")
    t.eq(_calls(ed, "pick_image_file")[-1], ("pick_image_file", COVER_PATH), "2回目は今のカバーのパスを開始位置に渡す")
    t.eq(ed.js("window._dbgApp.infoGraph().nodes.c1.data.name"), "other.png", "選び直した名前")
    # キャンセル（ダイアログを閉じる）: 今のカバーは変わらず、履歴も積まれない
    undo0 = ed.js("window._dbgApp.state().undo")
    click_sel(ed, f"{C1} .nPick", "カバーの「画像を選択」")   # 偽物のキューが空＝キャンセル
    _wait_calls(ed, 3, "pick_image_file")
    ed.wait(0.2)
    t.eq(ed.js("window._dbgApp.infoGraph().nodes.c1.data.name"), "other.png", "キャンセルでは変わらない")
    t.eq(ed.js("window._dbgApp.state().undo"), undo0, "キャンセルでは履歴を積まない")
    t.no_errors()


# ---------------------------------------------------------------- 曲
def test_native_song_open(t):
    '''音楽ファイルを読み込む（ネイティブ）: ネイティブのダイアログで選ぶと実パスで読み込まれ、実パスがプロジェクトに保存される。キャンセル・読めないパスでも壊れない'''
    ed = _start(t, view=None)
    native_add_file_from_url(ed, SONG_PATH, "tools/fixtures/basic.wav")
    # キャンセル（キューが空）
    file_menu(ed, "loadsong")
    _wait_calls(ed, 1, "pick_song_file")
    ed.wait(0.2)
    t.eq(_calls(ed, "read_song_file"), [], "キャンセルでは読み込まない")
    # 選ぶ
    native_queue(ed, "song", SONG_PATH)
    file_menu(ed, "loadsong")
    wait_until(ed, f"JSON.parse(window._dbg.rt.buildProjectText()).graph.song.nativePath==={json.dumps(SONG_PATH)}", label="曲の実パスの保存")
    t.eq(_calls(ed, "read_song_file"), [("read_song_file", SONG_PATH)], "実パスで読み込む")
    song = ed.js("JSON.parse(window._dbg.rt.buildProjectText()).graph.song")
    t.eq((song["name"], song["nativePath"]), ("clicks.wav", SONG_PATH), "曲の名前と実パス")
    t.eq(ed.js("window._dbgApp.nle().music.audio"), True, "音源が読み込まれた")
    t.eq(round(ed.js("window._dbgApp.nle().music.dur"), 1), 16.0, "音源の長さ（秒）")
    t.ok("音源を読み込みました: clicks.wav（16.0秒）" in toast(ed), f"メッセージ: {toast(ed)}")
    # 読めないパス（ファイルが無い）→ エラーを出し、今の曲は残る
    native_queue(ed, "song", "C:\\NLMTest\\Music\\missing.wav")
    file_menu(ed, "loadsong")
    wait_until(ed, "document.getElementById('errToast').textContent.includes('音源の読込に失敗')", label="読み込み失敗の表示")
    t.eq(ed.js("window._dbgApp.nle().music.audio"), True, "失敗しても今の音源は残る")
    t.eq(ed.js("JSON.parse(window._dbg.rt.buildProjectText()).graph.song.nativePath"), SONG_PATH, "失敗しても今の曲のパスは残る")
    forget_errors(ed, "音源の読込に失敗")
    t.no_errors()


# ---------------------------------------------------------------- 開いた直後の自動接続
_CACHE = {}


def _native_project(t):
    """曲（ネイティブ）・出力フォルダ・カバー（ネイティブ）を設定したプロジェクトを作り、(保存内容の文字列, 偽のPCの状態, カバーのbase64) を返す。
    開き直しの4つのテストで同じものを使うので、最初に作ったものを覚えておく（作り直さない）"""
    if "v" not in _CACHE:
        ed = _start(t, view=None)
        native_add_file_from_url(ed, SONG_PATH, "tools/fixtures/basic.wav")
        b64 = native_add_png(ed, COVER_PATH, 300, 300)
        native_queue(ed, "song", SONG_PATH)
        file_menu(ed, "loadsong")
        wait_until(ed, f"JSON.parse(window._dbg.rt.buildProjectText()).graph.song.nativePath==={json.dumps(SONG_PATH)}", label="曲の実パス")
        to_info(ed)
        _pick_out(ed)
        _pick_cover(ed)
        click_sel(ed, f"{OUT} .oName", "フォルダ名")
        type_text(ed, "natmap")
        wait_until(ed, "window._dbgApp.infoGraph().outs.o1.folderName==='natmap'", label="フォルダ名")
        _CACHE["v"] = (ed.js("window._dbg.rt.buildProjectText()"), native_state(ed), b64)
    pj, state, b64 = _CACHE["v"]
    return pj, copy.deepcopy(state), b64


def _reopen(t, pj, state):
    """ページを開き直し、同じ「PC」（偽のファイル置き場）を差して、保存したプロジェクトを「開く」（ブラウザのファイル選択は偽物）で開く"""
    ed = fresh_page(t)
    install_fake_pywebview(ed, state=state)
    install_fake_fs(ed)
    queue_open(ed, "natmap.nlmf", pj)
    file_menu(ed, "open")
    wait_until(ed, "document.getElementById('errToast').textContent.includes('プロジェクトを開きました')", label="プロジェクトを開く")
    return ed


def test_native_reopen_auto_connect(t):
    '''保存したプロジェクトを開くと、曲・出力フォルダ・カバーがダイアログ無しで自動接続され、そのまま書き出せる（選び直しのボタンも出ない）'''
    pj, state, b64 = _native_project(t)
    t.eq(json.loads(pj)["graph"]["song"]["nativePath"], SONG_PATH, "保存内容に曲の実パス")
    t.eq(json.loads(pj)["infoGraph"]["nodes"]["c1"]["data"]["nativePath"], COVER_PATH, "保存内容にカバーの実パス")
    ed = _reopen(t, pj, state)
    wait_until(ed, "window._dbgApp.nle().music.audio", label="音源の自動読み込み")
    t.eq(_calls(ed, "pick_song_file", "pick_folder", "pick_image_file"), [], "ダイアログは一度も開かない")
    t.eq(_calls(ed, "read_song_file")[0], ("read_song_file", SONG_PATH), "曲は保存済みの実パスから読む")
    t.eq(_calls(ed, "out_dir_ok"), [("out_dir_ok", OUT_BASE)], "出力フォルダは許可済みかを確かめて接続")
    t.ok(("fs_isfile", COVER_PATH) in _calls(ed, "fs_isfile"), "カバー画像は存在を確かめて接続")
    t.eq(round(ed.js("window._dbgApp.nle().music.dur"), 1), 16.0, "音源の長さ")
    t.eq(ed.js("window._dbgApp.dirty().lamp"), False, "開いた直後は未保存でない")
    to_info(ed)
    wait_until(ed, f"document.querySelector('{C1} .nThumb').style.display==='block'", label="カバーの見本")
    t.eq(ed.js(f"document.querySelector('{OUT} .oReconnect').style.display"), "none", "「再接続」ボタンは出ない")
    stub_convert(ed)
    _export_and_wait(ed, "natmap")   # 保存済みのフォルダ名・出力先でそのまま書き出す
    dest = OUT_BASE + "\\natmap"
    t.eq(_names(ed, dest), ['.nlm-egg.json', 'ExpertStandard.dat', 'HardStandard.dat', 'Info.dat', 'cover.png', 'song.egg'], "ダイアログ無しで書き出せた")
    t.eq(native_file_b64(ed, dest + "\\cover.png"), b64, "カバーも元の画像のまま")
    t.eq(_calls(ed, "pick_song_file", "pick_folder", "pick_image_file"), [], "書き出しでもダイアログは開かない")
    t.no_errors()


def test_native_reopen_unapproved_out_dir(t):
    '''このPCでまだ選ばれていないフォルダ（他人の.nlmfに仕込まれた書き出し先など）には自動接続しない: 案内を出し、許可の無いフォルダへは書かれない。「再接続」で選び直すと書き出せる'''
    pj, state, b64 = _native_project(t)
    state["approved"] = {}   # このPCで選んだことがある、の記録が無い（フォルダは存在する）
    ed = _reopen(t, pj, state)
    wait_until(ed, "window._dbgApp.nle().music.audio", label="音源の自動読み込み")
    t.eq(_calls(ed, "out_dir_ok"), [("out_dir_ok", OUT_BASE)], "許可済みかを確かめた")
    stat = ed.js("document.getElementById('stat').textContent")
    t.ok("再接続" in stat, f"案内: {stat}")
    to_info(ed)
    t.eq(ed.js(f"document.querySelector('{OUT} .oReconnect').style.display"), "", "「再接続」ボタンが出る")
    files = export_files(ed)   # 出力先が未接続＝ダウンロードの書き出しになる（ダウンロードは横取りして実際には保存しない）
    t.eq(sorted(files), ['ExpertStandard.dat', 'HardStandard.dat', 'Info.dat'], "出力先が未接続なので、ダウンロードでの書き出しになる（song.egg は不可）")
    t.eq(_calls(ed, "fs_subdir", "fs_file", "fs_write"), [], "許可の無いフォルダには何も書こうとしない")
    # 再接続: ネイティブのフォルダ選択（保存済みパスが開始位置）で選び直す＝許可される
    native_queue(ed, "folder", OUT_BASE)
    click_sel(ed, f"{OUT} .oReconnect", "再接続")
    wait_until(ed, f"document.querySelector('{OUT} .oReconnect').style.display==='none'", label="再接続の完了")
    t.eq(_calls(ed, "pick_folder"), [("pick_folder", OUT_BASE)], "保存済みのパスを開始位置にして選ばせる")
    stub_convert(ed)
    _export_and_wait(ed, "natmap")
    t.ok(OUT_BASE + "\\natmap\\Info.dat" in native_writes(ed), "再接続後は書き出せる")
    t.no_errors()


def test_native_reopen_missing_out_dir(t):
    '''保存した出力フォルダが今は無い（移動・削除）: 自動接続せず（無言で作らず）、「再接続」ボタンが出る。保存したパスは残す'''
    pj, state, b64 = _native_project(t)
    state["dirs"] = {}
    state["approved"] = {}
    ed = _reopen(t, pj, state)
    wait_until(ed, "window._dbgApp.nle().music.audio", label="音源の自動読み込み")
    t.eq(_calls(ed, "out_dir_ok"), [("out_dir_ok", OUT_BASE)], "存在を確かめた")
    t.eq(_calls(ed, "fs_subdir", "fs_write"), [], "フォルダを作ったり書いたりしない")
    to_info(ed)
    t.eq(ed.js(f"document.querySelector('{OUT} .oReconnect').style.display"), "", "「再接続」ボタンが出る")
    t.eq(ed.js("window._dbgApp.infoGraph().outs.o1.outDirPath"), OUT_BASE, "保存したパスは消さない（選び直すまで残す）")
    t.no_errors()


def test_native_reopen_missing_files(t):
    '''保存した曲・カバーのファイルが今は無い: 開く処理は止まらず、曲は未読込のまま「音源が未読込です」と案内する（無言で失敗しない）'''
    pj, state, b64 = _native_project(t)
    for k in list(state["files"]):
        if k.endswith("clicks.wav") or k.endswith("cover_src.png"):
            del state["files"][k]
    ed = _reopen(t, pj, state)
    t.eq(ed.js("window._dbgApp.nle().music.audio"), False, "曲のファイルが無いので音源は未読込")
    t.ok("音源が未読込です" in toast(ed), f"案内: {toast(ed)}")
    t.eq(ed.js("JSON.parse(window._dbg.rt.buildProjectText()).graph.song.nativePath"), SONG_PATH, "曲の実パスは残す（ファイルが戻れば次回読める）")
    t.eq(_calls(ed, "pick_song_file"), [], "ダイアログは開かない")
    t.no_errors()


# ---------------------------------------------------------------- 閉じる時の確認・未保存の通知
def test_native_dirty_notify_and_quit_dialog(t):
    '''未保存の通知と×ボタンの確認（exe版）: 編集するとPython側へ set_dirty(true)・保存すると false。×を押す（__nlmAskQuit）と3択が出て、キャンセル=閉じない／保存せずに終了=終了／保存して終了=保存してから終了'''
    ed = _start(t, "basic", view=None)
    install_fake_fs(ed)
    t.eq(ed.js("window.__nat.dirty"), [], "開いた直後は通知なし")
    place_at(ed, 1, 1)
    wait_until(ed, "window.__nat.dirty.length>0", label="未保存の通知")
    t.eq(ed.js("window.__nat.dirty"), [True], "編集すると set_dirty(true)")
    # × → 3択（キャンセル）
    t.eq(ed.js("window.__nlmAskQuit()"), "ok", "×の処理はすぐ 'ok' を返す（結果は quit_app で伝える）")
    wait_dialog(ed)
    t.eq(dialog_buttons(ed), ["保存して終了", "保存せずに終了", "キャンセル"], "3択の文言")
    dialog_click(ed, 2)
    wait_until(ed, "!document.getElementById('dirtyDlgBg')", label="ダイアログが閉じる")
    ed.wait(0.1)
    t.eq(ed.js("window.__nat.quit"), 0, "キャンセルでは閉じない")
    # × → 保存せずに終了
    ed.js("window.__nlmAskQuit()")
    wait_dialog(ed)
    dialog_click(ed, 1)
    wait_until(ed, "window.__nat.quit===1", label="保存せずに終了")
    # × → 保存して終了（保存先を選ぶ→書く→閉じる）
    ed.js("window.__nlmAskQuit()")
    wait_dialog(ed)
    dialog_click(ed, 0)
    wait_until(ed, "window.__nat.quit===2", label="保存して終了")
    t.eq(len(ed.js("__fake.writes")), 1, "保存して終了では先に保存する")
    t.eq(ed.js("window.__nat.dirty"), [True, False], "保存すると set_dirty(false)")
    t.no_errors()

"""書き出す song.egg への Musicの配置（開始位置・分割・トリム）の反映（2026-10-04）。
以前は無音追加だけを焼き込み、NLEでMusicを動かす/切ると、エディタでは合っているのにゲームではずれた。
ここでは書き出しが変換（/__convert/toOgg・偽物）へ渡す内容と、Info.dat の試聴開始・譜面チェックの音源の長さを確かめる。
切り貼りそのもの（ffmpeg）は tests/unit_py/test_egg_segments.py。
素材 rich: 120BPM（拍16から150）・音源は basic.wav（16秒）・試聴開始は元の音源の4秒"""
import json
from urllib.parse import quote

from e2e_helpers import wait_until
from info_helpers import to_info
from misc_helpers import stub_convert, convert_calls
from test_native import OUT_BASE, _native_project, _reopen, _export_and_wait, _text


def _open_with_music(t, music_beat=0, segs=None):
    """exe版で保存した rich のプロジェクトに Musicの配置（開始の拍・区間）を書き込み、開き直す（曲・出力フォルダは自動で接続）。
    開き直しで配置が残ること（以前は曲の自動読込で分割・トリムが消えていた）もここで確かめる"""
    pj, state, _b64 = _native_project(t)
    d = json.loads(pj)
    d["musicBeat"], d["musicSegs"] = music_beat, segs
    ed = _reopen(t, json.dumps(d, ensure_ascii=False), state)
    wait_until(ed, "window._dbgApp.nle().music.audio", label="音源の自動読み込み")
    m = ed.js("window._dbgApp.nle().music")
    t.eq((m["beat"], m["segs"]), (music_beat, segs), "開き直してもMusicの配置が残る")
    to_info(ed)
    stub_convert(ed)
    return ed


def _mapcheck_audio(ed):
    return ed.js("window._dbgApp.mapCheckInput().then(x=>x.audioDuration)")


def test_music_moved_adds_silence(t):
    '''Musicを拍2（1秒）から始めると、song.egg の先頭に1秒の無音（leadInMs=1000）。試聴開始・音源の長さも1秒ずれる'''
    ed = _open_with_music(t, music_beat=2)
    _export_and_wait(ed, "moved")
    t.eq([c["url"] for c in convert_calls(ed)], ["__convert/toOgg?ext=wav&leadInMs=1000"], "変換の呼び方（無音1秒・切り貼り無し）")
    dest = OUT_BASE + "\\moved"
    t.eq(json.loads(_text(ed, dest + "\\Info.dat"))["_previewStartTime"], 5.0, "試聴開始（元の音源の4秒が鳴るのは5秒目）")
    mark = json.loads(_text(ed, dest + "\\.nlm-egg.json"))
    t.eq((mark["leadInMs"], mark["segs"]), (1000, None), "変換のマーカー")
    t.eq(_mapcheck_audio(ed), 17, "譜面チェックの音源の長さ（1秒＋16秒）")
    t.no_errors()


def test_music_split_sends_segments(t):
    '''Musicを分け、後ろの区間を元の音源の8秒目から拍8（4秒）に置く＝元の4〜8秒を切り取った形。切り貼り表を変換へ渡す'''
    segs = [{"beat": 0, "off": 0, "dur": 4}, {"beat": 8, "off": 8, "dur": 4}]
    ed = _open_with_music(t, segs=segs)
    _export_and_wait(ed, "split")
    want = [[0, 4, 0], [8, 12, 4]]   # [元の音源の開始秒, 終了秒, 書き出し先の開始秒]
    t.eq([c["url"] for c in convert_calls(ed)], ["__convert/toOgg?ext=wav&segs=" + quote(json.dumps(want, separators=(",", ":")))],
         "変換の呼び方（切り貼り表）")
    dest = OUT_BASE + "\\split"
    t.eq(json.loads(_text(ed, dest + "\\.nlm-egg.json"))["segs"], want, "変換のマーカーに切り貼り表")
    t.eq(json.loads(_text(ed, dest + "\\Info.dat"))["_previewStartTime"], 4.0,
         "試聴開始（元の音源の4秒は切り取られている＝その後で最初に鳴る区間の頭＝4秒目）")
    t.eq(_mapcheck_audio(ed), 8, "譜面チェックの音源の長さ（4秒＋4秒）")
    t.no_errors()


def test_music_arrangement_cache(t):
    '''同じ配置なら2回目の書き出しは変換しない。配置を変えれば（後ろの区間の位置）変換し直す'''
    segs = [{"beat": 0, "off": 0, "dur": 4}, {"beat": 8, "off": 8, "dur": 4}]
    ed = _open_with_music(t, segs=segs)
    _export_and_wait(ed, "cache")
    _export_and_wait(ed, "cache")
    t.eq(len(convert_calls(ed)), 1, "同じ配置なら変換し直さない")
    # 後ろの区間を拍10（5秒）へ（保存内容を書き換えて開き直すのではなく、ページ内で配置だけ変える＝Undoの仕組みを通す）
    ed.js("""(()=>{ const rt=window._dbg.rt; const st=JSON.parse(rt.dumpDomain('node'));
      st.musicSegs=[{beat:0,off:0,dur:4},{beat:10,off:8,dur:4}]; rt.restoreDomain('node',JSON.stringify(st)); return true; })()""")
    wait_until(ed, "window._dbgApp.nle().music.segs[1].beat===10", label="配置の変更")
    _export_and_wait(ed, "cache")
    urls = [c["url"] for c in convert_calls(ed)]
    t.eq(len(urls), 2, "配置を変えたら変換し直す")
    t.ok(quote(json.dumps([[0, 4, 0], [8, 12, 5]], separators=(",", ":"))) in urls[1], f"新しい切り貼り表: {urls[1]}")
    t.no_errors()

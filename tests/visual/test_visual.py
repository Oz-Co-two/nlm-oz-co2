"""画面の崩れ確認。screens.py の画面ごとに2つのテストを作る:
  崩れ: <題名>   重なり・はみ出し・文字の切れ・大きさ0・隠れ を機械的に探す（新しいものが出たら失敗）
  見た目: <題名> 基準画像とピクセル比較（変化したら「要確認」。意図した変化なら --accept）
最後の「まとめ」が、変化した画面だけのまとめ画像 test-out/visual/review.png とレポート report.html を指す。
"""
import screens
import vislib


def _make(kind, scr):
    if kind == "layout":
        def fn(t):
            vislib.runner(t).check_layout(scr.name)
        fn.__doc__ = f"崩れ: {scr.title}"
    else:
        def fn(t):
            vislib.runner(t).check_image(scr.name)
        fn.__doc__ = f"見た目: {scr.title}"
    fn.__name__ = f"test_{kind}_{scr.name}"
    return fn


# 実行順は関数の行番号で決まる（nlmtest.py）。作った関数は行番号が同じになるので、画面の順・崩れ→見た目の順になるよう振り直す
_order = 10000
for _sc in screens.SCENES:
    for _s in _sc.screens:
        for _k in ("layout", "image"):
            _f = _make(_k, _s)
            _f.__code__ = _f.__code__.replace(co_firstlineno=_order)
            _order += 1
            globals()[_f.__name__] = _f


def test_zz_summary(t):
    '''まとめ: 見た目が変化した画面（まとめ画像とレポート）'''
    r = vislib.runner(t)
    if not r.results:
        t.skip("画面を1つも撮っていません")
    changed, lay = r.write_final()
    if changed:
        t.info(f"レポート（人の確認用）: {vislib.OUT / 'report.html'}")
        t.review(f"見た目が変化した画面 {len(changed)}件: {', '.join(changed)}（まとめ画像を確認。意図した変化なら --accept）",
                 vislib.OUT / "review.png")
    t.info(f"撮った画面 {len(r.results)}件・変化なし" + (f"・崩れあり {len(lay)}件" if lay else ""))


test_zz_summary.__code__ = test_zz_summary.__code__.replace(co_firstlineno=99999)   # 一番最後に

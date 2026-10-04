# テスト

機能を足したり直したりした後に、**基本の機能が壊れていないか**を自動で確かめるためのもの。
追加ライブラリは不要（Python 3.14 の標準ライブラリ＋手元の Microsoft Edge をヘッドレスで使う）。

```
.venv-build/Scripts/python.exe tools/run_tests.py              全部（グループごとに並列）
.venv-build/Scripts/python.exe tools/run_tests.py e2e unit_js  グループを指定
.venv-build/Scripts/python.exe tools/run_tests.py -k export    名前の一部で絞り込み
```

画面には要約だけを出す。失敗の詳細は `test-out/last.txt`、全部の結果は `test-out/summary.json`。

`--coverage` を付けると、JSのうちテスト中に実際に動いたコードの割合も測る（外部ライブラリは除く）。
ファイルごとの割合と「一度も動いていない大きい関数」の一覧が `test-out/coverage/report.txt` に出る＝次にテストを足す所の目安。
「動いた」は「確かめた」とは限らない（画面を撮るために開いただけの処理も数える）ので、実際に確かめている範囲はこれより狭い。
終了コードは 0=失敗なし（要確認はあってもよい）/ 1=失敗あり。

## グループ

| フォルダ | 中身 | ブラウザ |
|---|---|---|
| `unit_py/` | Python側（serve.py のアクセス制御・ファイル読み書きの許可範囲・自動更新 等） | 使わない |
| `unit_js/` | JSの計算部分（譜面チェック・自動ライティング・カバー補正 等）をページ内で直接呼ぶ | 使う |
| `e2e/` | エディタを実際に操作して結果を数値で確かめる（配置・Undo・保存→開き直し・書き出しの照合・曲データの読込 等） | 使う |
| `e2e_project/` | 保存・開く・新規・未保存時の3択・バックアップ、難易度の転送/受信/全消去 | 使う |
| `e2e_edit/` | 3Dビューの編集（選択・コピー/貼り付け・回転・壁・アーク/チェーン・つまみ）とライティングの編集 | 使う |
| `e2e_nle/` | NLEのクリップ操作（分割・結合・移動・長さ・レーン・L/S/M・マーカー・Music）、MEDIAとアセットクリップ | 使う |
| `e2e_info/` | 自動ライティング・カバー補正の適用、INFOのノード操作（追加・削除・複製・配線・書き出しノード・試聴） | 使う |
| `e2e_misc/` | BPMの自動判定、exe版だけの処理（pywebview を偽物にして通す）、環境設定、難易度を測る（応答は偽物） | 使う |
| `visual/` | 画面の崩れ検出（画像なし）と、基準画像とのピクセル比較 | 使う |

`t.fresh()` は localStorage と、一時のデータフォルダの `config/settings.json`（環境設定のミラー）を消してから開き直す＝
テストごとに環境設定は初期値から始まる。設定が残ることを確かめる時は `ed.reload(clear_storage=False)` を直接使う。

全部で約4分（同時に4グループ。このPCでは4が一番速く、増やすとCPUの取り合いで逆に遅くなる）。
普段は直した所に関係するグループ・テストだけを回す（例: `run_tests.py e2e_nle`、`-k` で絞り込み）。全部はリリースの直前に1回。
操作テストのグループ内の部品は `tests/<グループ>/*_helpers.py`、グループをまたぐ共通部品は `tests/_lib/e2e_helpers.py`。

各グループは別プロセス・別のEdgeで同時に動く。グループ内ではEdgeを1つ使い回し、テストごとに
`t.fresh()` でページを開き直して初期状態に戻す。

## 結果の種類

- **OK / 失敗 / エラー**: 失敗＝確認が外れた、エラー＝テスト自体が例外で止まった。
- **要確認**: 失敗ではないが人の目が要るもの（画面に変化があった等）。下の「画面の比較」参照。
- **飛ばし**: `t.skip()`。既知の不具合で、直すまで止めているものは理由に「既知の不具合: …」と書いてある。

## 書き出しの正解ファイル（tests/golden/）

決まったテスト素材を書き出した Info.dat・各難易度.dat を、`tests/golden/` の正解と一字一句比べる。
書き出しの中身を**意図して**変えた時は、差分が意図どおりかを確かめてから正解を更新する:

```
.venv-build/Scripts/python.exe tools/run_tests.py e2e --update-golden
git diff tests/golden/      ← 変わった所が意図どおりか必ず見る
```

正解ファイルは git に入れる（小さい文字ファイル）。

## 画面の比較（visual/）

- 崩れ検出: 表示中のボタン等の位置を調べ、重なり・はみ出し・文字の切れを見つける。画像を使わない。
  見つかったら**失敗**。意図的な重なりは `tests/visual/layout_allow.json` に理由付きで入れる。
- 画像比較: 決まった画面を撮り、基準画像（`tests/visual/baseline/`・git管理外＝PCごと）と比べる。
  変化した画面だけを `test-out/visual/review.png`（1枚のまとめ）と `test-out/visual/report.html`
  （前後を並べて見るページ）にまとめ、**要確認**にする。意図どおりなら基準を更新する:

```
.venv-build/Scripts/python.exe tools/run_tests.py visual --accept
```

基準画像が無いPC（初回）では、今の画面を基準として作るだけで比較はしない。
Edgeの更新で文字の描画が変わると全画面に差が出ることがある。その時は内容を確かめて一度 `--accept` する。

- 撮る画面の一覧は `tests/visual/screens.py`（足し方は冒頭の説明）。画面ごとに「崩れ」と「見た目」の2件のテストになる。
  新しい画面・ダイアログを足したら、ここに `Screen(...)` を1つ足して `-k <題名>` で一度回し、
  `test-out/visual/current/<名前>.png` を見て目的の画面が写っているか確かめる。
- 崩れの仕分け: 意図的なもの＝`layout_allow.json`（無視）、直すまで保留＝`layout_known.json`（「飛ばし」になる）。
  どちらにも理由（note）を書く。
- 判定の許容値（`tests/visual/vislib.py` の冒頭）: R・G・B のどれかの差が 32/255 を超えた画素を「変化」とし、
  25画素以上で「画面が変化した」とみなす。3Dビュー等の揺れる所は隠すか比較から除く（`screens.py` の hide / mask）。
- 撮影中は隠している3Dビューの描画を止め、画像の比較・合成は別のタブで行う（エディタのページは重いため）。

## テスト素材（tools/fixtures/）

- `basic`: ノーツ8個だけの小さい素材。
- `rich`: 2難易度（Hard・Expert）・赤青ノーツ（ドット含む）・ボム・壁・アーク・チェーン・ライト・BPM変化・曲情報を含む。
  `tools/fixtures/rich_map/`（Beat Saber の譜面フォルダ）をアプリの「曲データを読み込む」で読ませ、アプリ自身に保存させたもの。
  音源は basic.wav を使い回す。作り直しは `tools/fixtures/make_fixtures.py`。

## テストの書き方

`tests/<グループ>/test_*.py` に `def test_名前(t):` を書く。docstring の1行目が結果の一覧に出る名前。
使える道具は `tests/_lib/nlmtest.py` の冒頭に書いてある。

```python
def test_place_undo(t):
    '''ノーツを置いてUndoすると消える'''
    ed = t.fresh('basic')                       # 開き直してテスト素材を読む
    ...
    t.eq(ed.js("window._dbgApp.state().counts.notes"), 8, 'ノーツ数')
    t.no_errors()                               # ページ内で例外が出ていない
```

- 状態は開発用窓口 `window._dbgApp`（読み取り専用）と `window._dbg.rt`（ランタイム全体）から読む。
  足りなければ `_dbgApp` に**値の複製を返すだけ**の窓口を足す（書き換え機能は持たせない）。
- 期待値は仕様・コードの意図から決める。今の出力をそのまま写して期待値にしない。
- テスト素材は `tools/fixtures/`（作り直しは `tools/fixtures/make_fixtures.py`）。
- 固定の秒数で待つより、状態が変わるのを待つ方が速くて安定する。

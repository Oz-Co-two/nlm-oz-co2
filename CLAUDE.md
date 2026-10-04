# Non-Linear Mapper (NLM) — 開発メモ

Beat Saber譜面エディタ。原作者は helba さん（https://helba.flashhub.net/nlm/ ）で、
このリポジトリはその派生版。原作者からは note のコメント欄で公開・改変の許可を得ている
（2026-09-22、Oz-Co2名義での配布・修正版の配布も快諾）。
ライセンスは GPLv3。`preview-v4/preview-v4.js`（3Dプレビュー）がGPLv3の
ArcViewer（https://github.com/AllPoland/ArcViewer/ ）の移植であるため、
プロジェクト全体をGPLv3としている（詳細は `LICENSE.draft` と `THIRD_PARTY_NOTICES.txt`）。
移植はコードだけでなく `preview-v4/env/*.json` も対象＝ArcViewer実行中シーンから
helbaさん自作のUnityスクリプト`NLMEnvExport.cs`で抽出した実メッシュ・階層データ。
（他に `js/runtime/editor-app.js` のアーク/チェーン作成がChroMapper(GPL-2.0)の
仕様に「準拠」との記述あり。ただしコードは独自実装でコピーではない）。
公開準備が整い次第 `LICENSE.draft` → `LICENSE` に改名する。
このファイルは他人の書いたコードを後から保守する際に、**コードを読むだけでは分からない・再発見に時間がかかる知識**
をまとめたもの。仕様の全文書き起こしはしていない（コード自体が正でありコピーは陳腐化するだけ）。

## 全体構成

- Node/npm は使わない。ビルドツールなし、素のES Modules。
- `app.py` — デスクトップ版ランチャー。`pywebview`でWebView2(Edge Chromium)ネイティブウィンドウを開く。
  内部で`serve.py`をローカルの空きポートでスレッド起動し、`http://127.0.0.1:<port>/editor.html`を表示。
- `serve.py` — 静的ファイル配信＋ローカル専用API（`__settings/save`, `__openarg`, `__asset/*`,
  `__convert/toOgg`等）。`python serve.py`単体でも起動でき、その場合は普通のブラウザ（Edge/Chrome）
  で`http://127.0.0.1:8138/editor.html`を開いて動作確認できる（DevToolsが自由に使える最速の検証手段）。
- `editor.html` → `js/main.js` → `js/runtime/editor-app.js`（実質1万行超のモノリシック本体）。
  UI・保存・書き出し・3D描画・音声処理が全部ここに入っている。
- `js/runtime/editor-runtime.js` / `js/project/save-system.js` は「メソッド一覧を持つラッパークラス」。
  実装は全部`editor-app.js`のクロージャ内にあり、これらはただの委譲層（`rt.foo`を呼ぶだけ）。
  新しい関数を追加/削除したら、ここの`methodNames`配列と対応メソッドも忘れず更新すること
  （忘れても動くが、参照が浮いた状態になる）。

## テスト（2026-10-04）

- **普段の修正・機能追加では、全テストは回さない**（全部で約6〜7分かかるため）。直した所のテストと、影響しそうな周辺の
  グループ・テストだけを回す（例: `run_tests.py e2e_nle`、`run_tests.py e2e_edit -k paste`）。どれを回したかは報告に書く。
- **全テスト（`.venv-build/Scripts/python.exe tools/run_tests.py`）はリリースの直前に1回だけ**: 版を上げた後、GitHubへ
  プッシュする前。そこで見つかった不具合は、その公開予定の版で直して一緒に出す。
- 画面には要約だけが出る。失敗の詳細は`test-out/last.txt`を読む（画像を何枚も見て確かめる代わり）。使い方は`tests/README.md`。
- 失敗したら直してから報告する。自分の変更と無関係に見える失敗も、黙って飛ばさず報告に書く。
- 失敗・エラーのあった回は`test-out/history/<日時>/`に記録が残る（last.txtは次の実行で上書きされるため）。再現しない・
  まれな失敗は、`tests/README.md`の「たまに出るエラーの記録」に調べた結果を書き足す（同じものが出た時の絞り込みに使う）。
- 書き出しの中身を意図して変えた時だけ`--update-golden`。`git diff tests/golden/`で差分が意図どおりかを確かめ、報告に書く。
- 画面の「要確認」は、まず`test-out/visual/review.png`（変化した画面だけのまとめ1枚）を見る。意図どおりと言い切れない時は
  ユーザーに`test-out/visual/report.html`を見てもらう。意図どおりなら`--accept`で基準画像を更新する。
- 新しい機能を足したら、その機能のテストも足す（`tests/<グループ>/test_*.py`）。新しい画面・ダイアログは`tests/visual/`の画面一覧にも足す。

## ビルド・実行

- 開発用venv: `.venv-build/`（`.gitignore`済み）。`pip install pywebview pythonnet pyinstaller`。
  **Python 3.14**で作る（`py -3.14 -m venv .venv-build`。2026-09-28に3.9から移行・3.14はセキュリティ修正が2030-10まで）。
  上限はpythonnet（3.1.0は`<3.15`）で決まるので、3.15以降へ上げる時はpythonnetの対応を先に確認すること。
  `.venv/` は `tools/` のテンポ解析用（librosa）で、ビルドには使わない。
- ビルド: `.venv-build/Scripts/python.exe -m PyInstaller --noconfirm --clean nlm.spec` →
  `dist/NonLinearMapper/` にonedir出力（`NonLinearMapper.exe` + `_internal/`）。
- **配布用exeへの反映方法**: 配布フォルダ（例: `NLM-app/`）の`NonLinearMapper.exe`と
  `_internal/`だけを新ビルドで上書きする。**`asset/`・`config/`・`lang/`は上書きしない**
  （exeの隣に生成されるユーザーデータ。設定・クリップが入っている。`app.py`の`_data_root()`参照）。
  上書き前に古い`exe`+`_internal`をバックアップしておくと安全（このリポジトリはgit管理外）。
- **版番号**: 利用者向けの版番号は`js/constants.js`の`APP_VERSION`（例`v1.1.0-oz`）が唯一の定義元。
  メニューバー右端（`main.js`）とexeのウィンドウタイトル（`app.py`の`_app_version()`がこの行を正規表現で読む）に出る。
  リリース時はここを書き換え、GitHubのタグ/リリース名・配布zip名（`NonLinearMapper-<版>.zip`）と揃える。
  配布zipは`dist/NonLinearMapper/`から作る（`NLM-app/`には自分の`config/`・`asset/`が入っているので使わない）。
- **翻訳の互換**: exe隣の`lang/`は初回シード後は更新されないため、`serve.py`の`do_GET`が`/lang/*.json`を
  「同梱版(`_internal/lang`)を土台にexe隣の版をキー単位で上書き」して返す。旧版の`lang/`を持つ利用者でも
  新機能の訳が欠けない（2026-09-27）。新しい設定項目(`bsnm_*`)は「キーが無い＝初期値」で動くように書くこと
  （旧`settings.json`は存在するキーだけlocalStorageへ流し込む方式＝`js/settings-mirror.js`。CSP導入でeditor.htmlから分離）。
- `nlm.spec`の`console=True`と`app.py`の`webview.start(debug=True)`は診断用フラグ。
  普段は両方無効(`console=False`・`debug`無し)でビルドすること。デバッグしたい時だけ一時的に有効化。
- **ffmpeg依存**: song.egg変換(後述)にはPATH上の`ffmpeg`が必要。`winget install Gyan.FFmpeg`で導入可能。
  無い場合はエラーメッセージでインストール手順を案内する仕様（無言で失敗はしない）。
- **配布zipのMark of the Web対策**: `app.py`の`_unblock_dist_folder()`（`main()`の先頭、
  `import webview`より前で呼ぶ）が、同梱物（`_internal`＝`sys._MEIPASS`）配下のファイルからZone.Identifier
  (NTFSの代替データストリーム)を除去する。配布zipをダウンロードして展開すると、この印が
  DLLに引き継がれたままになり、.NETランタイムがDLLロードを拒否して
  "Failed to resolve Python.Runtime.Loader.Initialize from ...\Python.Runtime.dll" で
  起動失敗することがある（helbaさんのnoteコメント経由でユーザー報告、2026-09-23）。
  手動なら「zipのプロパティ→許可する」でも回避可（README.mdのトラブルシューティング参照）。

## WebView2 / File System Access API の重大な制約（はまりどころ）

このアプリはブラウザの`File System Access API`（`showOpenFilePicker`/`showDirectoryPicker`等）に
大きく依存しているが、**pywebviewのWebView2埋め込み環境ではこのAPIに固有の制約がある**。

1. **ハンドルはセッション限定**。`FileSystemFileHandle`/`FileSystemDirectoryHandle`はJSON化できず、
   アプリを再起動する（あるいはプロジェクトを開き直す）と全て失効する。`outDirHandle`・カバー画像の
   `_coverHandles`・曲の`songNode.handle`は全て「セッション中のみ」（コード内のコメントにもその旨あり）。
2. **絶対パスは一切取得できない**。`File.name`はファイル名のみでフォルダパスを含まない。これは
   WebView2固有の制限ではなくChromiumの仕様なので、ホスト側の設定では回避できない。
3. **ハンドルをIndexedDBに保存して自動復元する手法は、このWebView2環境でネイティブクラッシュする**。
   `addRecent()`（最近使ったファイル）・`persistSongHandle()`（曲の自動復元）・`saveLibDirs()`
   （ライブラリフォルダの自動復元）が実際にこれをやっていて、**保存直後にアプリ全体が無言で
   クラッシュする不具合の直接原因だった**（2026-09-20の調査で特定・修正済み）。
   → **今後もこの手法（`FileSystemHandle`をIndexedDBや`localStorage`に保存する）は絶対に再導入しないこと。**
   通常のChrome/Edgeでは問題なく動くため、テストがブラウザ経由（`python serve.py`）だけだと再現しない。
4. **上記の代替**: 曲の自動読込だけは`pywebview`のネイティブファイルダイアログ経由に置き換えた
   （`app.py`の`Api.pick_song_file`/`read_song_file`、JSの`openSongFileNative`/`tryAutoLoadSongNative`）。
   pywebviewの`create_file_dialog`は実際の絶対パスを返すので、それを`songNode.nativePath`（文字列）
   としてプロジェクトJSONへ保存すれば、次回はダイアログ無し・IndexedDB不要で自動読込できる。
   **出力フォルダ・カバー画像も同じ方式に移行済み**（2026-09-21）。`Api.pick_folder`/`pick_image_file`/`fs_*`
   （app.py）と、JSの疑似ハンドル`mkNativeDir`/`mkNativeFile`（`getDirectoryHandle`/`getFileHandle`/`createWritable`/
   `getFile`だけを実装したFileSystemHandle互換）で包むので、`exportMap`は無改修で動く。実パスは
   `infoGraph.outs[oid].outDirPath`と`cover.data.nativePath`に保存し、プロジェクトを開いた直後に
   `tryAutoRestoreNativeInputs()`が存在確認のうえダイアログ無しで自動接続する（パスが無ければ従来どおり「再接続」）。
   ただし出力フォルダは**このPCでダイアログから選んだことがあるもの**だけ（下の「ファイル読み書きの許可範囲」参照）。
   ダイアログは保存済みパスを開始位置にして開く。旧方式の`showDirectoryPicker({id})`は前回の場所を勝手に覚え、
   出力先を変えた後も古い場所で開いてしまっていた。pywebview外（`python serve.py`+ブラウザ）では従来のブラウザピッカーへ戻る。
5. **フォルダ選択ダイアログが毎回「一つ上の階層」を表示する**のはWindows標準のフォルダ選択ダイアログの
   仕様（選んだフォルダの親フォルダを一覧表示し、目的のフォルダをクリックさせる）。
   `showDirectoryPicker({id:'...'})`のid指定で「前回の場所を覚える」までは改善できるが、
   この一手間自体はブラウザ/OS側の挙動でこちらからは変更できない。
6. **`.oChk`のような「クリックのたびに`innerHTML`で再生成される領域」にボタンを置くと、
   クリックした瞬間に自分自身が再生成されてclickイベントの発火先を失う**（`refreshOutCards()`が
   `setActiveOut()`経由でpointerdownのたびに同期的に呼ばれるため）。恒久的なボタン/inputは
   カード生成時に一度だけ作る固定要素側に置き、直接`addEventListener`すること。デリゲーション
   （祖先要素でのイベント委譲）で解決しようとしても、対象要素が既に detached なら意味がない。

## 「オフセット」という名前が3つある（要注意）

紛らわしいので明記する。

1. **NJS飛来オフセット**（`_noteJumpStartBeatOffset`）— 難易度別。ヘッダーの`offField`。
   単位は**拍**。ノーツがBeat Saber内で画面に出現し始めるタイミングの微調整。
   曲の同期やタイミングそのものには一切関係しない。`njsCfg`に保存。
2. **`_songTimeOffset`**（Info.dat由来）— `exportMap()`で`b._songTimeOffset`をそのまま素通り
   させているだけの値。読み込んだ元のInfo.datの値がそのまま出力されるだけで、このアプリの
   UIには編集箇所がなく、内部の再生ロジックにも一切関与しない（死んでいる/使われていない値）。
3. **`songNode.offset`＋`getSongOff()`＋ヘッダーの`leadInField`（無音追加, ms）**— 2026-09-20に
   UIを新設。**曲の先頭に無音を追加する**ための唯一の実装。`songNode.offset`は常に0以下（秒）で
   保持し、UIには「追加するms」として符号反転して見せている（`getLeadInMs`/`setLeadInMs`）。
   - エディタ内プレビュー: `play()`が`getSongOff()`を使って再生スケジューリングに直接反映（既存の
     仕組みに乗せただけで`play()`自体は変更していない）。
   - 書き出し: `exportMap()`が`leadInMs>0`ならffmpegの`adelay`フィルタで**song.eggの音声データ自体に
     無音を物理的に焼き込む**。Info.datの`_songTimeOffset`メタデータには依存しない（実際のBeat Saber
     本体がこのフィールドをどこまで確実に解釈するか不明なため、確実性を優先した設計判断）。
   - **Musicの配置（NLEのMusicクリップの開始位置・分割・トリム）も song.egg に焼き込む**（2026-10-04）。切り貼り表は
     `eggPieces()`＝`play()`と同じ計算。切っていなければ「無音追加＋Musicの開始位置」ぶんの`adelay`だけ、分割・トリムが
     あれば`?segs=`で切り貼り表を渡し serve.py が`atrim`→`adelay`→`amix`で並べ直す。以前は無音追加だけで、Musicを動かすと
     エディタでは合っているのにゲームではずれた。**Musicの再生の仕方（`play()`）を変えたら`eggPieces()`も合わせること。**

## 試聴ノード（選曲画面のプレビュー区間・2026-09-28）

- Info.datの`_previewStartTime`/`_previewDuration`はINFO画面の**試聴ノード**（`t:'prev'`）が持つ。旧ヘッダーの
  「プレビュー開始/プレビュー長」欄は廃止。アクティブ書き出しに繋がった試聴ノードの値を`applyInfoGraph()`が
  `infoBase`へ写し、未接続なら12秒/10秒（`PREV_DEF`）。
- ノードの秒は**元の音源の秒**。書き出しは`eggOutSecOf()`で書き出す song.egg の秒へ直す（無音追加・Musicの配置ぶんずれるため）。
  以前は足しておらず、無音追加を使うと試聴位置がずれていた。拍→音源秒の変換は`audioPosAtBeat()`（Musicの配置・カット・無音追加を考慮）。
- 旧プロジェクト（`infoGraph.prevMig`なし）とプロジェクト無しのInfo.dat読込は`migratePrevNode()`で`infoBase`の値から試聴ノードを作り、
  全書き出しに繋ぐ。`prevMig`を見て1回だけ行う（ユーザーが消した試聴ノードを復活させないため）。

## 譜面チェック（BeatLeader基準・2026-09-28）

- `js/mapcheck/mapcheck.js` は BS Map Check（KivalEvan・MIT）の**BeatLeaderプリセット**と、それが使う bsmap の計算の移植。
  ランク審査で実際に使われるのが BS Map Check なので、**「原作と同じ結果」を最優先**にしている。そのため原作の計算のクセも
  わざと再現している（直すと審査で見られる結果とずれる）:
  - 各配列を並べ替えない（原作は読み込み時に並べ替えず、.datに書かれた順で判定する。NLMの書き出しは時刻順）
  - チェーンのリンクの秒(`sec`)に拍の値が入る／bsmapの`vectorMul`は0を掛けると元の値のまま（`mulQ`）
  - 「照らされていないボム」は原作が例外で何も出さない条件では何も出さない
- 原作と違うのは「原作が例外で項目ごと消える」ケースだけ（分割数1のチェーン、不正IDのイベントボックス）。移植は判定できた分を出す。
- 検査対象は書き出しと同じ `collectExportDiffs()`/`buildExportInfo()` の結果（`exportMap`から切り出して共有）。
  書き出しの中身を変えればチェックにも自動で反映される。音源の長さは書き出す song.egg の長さ（`eggLength()`）。
- 原作の更新に追従する時・移植を直した時は `tools/mapcheck_difftest.py`（原作サイトと自動で突き合わせ。tools/README.md）。
- `js/mapcheck/env-tables.js` は bsmap の `src/beatmap/misc/environment.ts` から自動抽出した表（環境の追加時は作り直す）。
- 結果パネルは `mapcheck-panel.js`。項目名は `mc.k.<key>`（日本語の既定値はパネル内の`JA`表）。
- パネルの2つ目のタブ「NLM版 BL評価リスト」（`blcriteria.js`＋表示`blcriteria-view.js`・2026-09-29）は、BeatLeader公式の**文章の基準**
  （beatleader.wiki の Ranking Criteria）を項目番号（R1.A.1…）どおりに並べたNLM独自の判定表。BS Map Check とは別物なので、
  **公式の結果と見間違えないよう枠と背景を青緑にしている**（ユーザーの要望。`#mcPanel.blMode`）。判定の種類は
  自動（文面の数値どおり）/候補（図や審査員の判断に頼る項目。一部は BS Map Check の結果を流用）/手動/対象外。
  文面に定義が無くNLMが解釈した所（チェーン密度＝squish、振り始め・スイング軌道のマス、ボムの照明の近似など）は
  コメントと画面の注記（`BL_NOTE_JA`）に書いてある。基準の改訂に追従したら `CRITERIA_DATE` を更新し `tools/blcriteria_test.py`。
  - スイングのまとまりは BS Map Check のもの（90度ちょうどで分ける）を使わず独自に作る（45度ルールが判定できなくなるため）。
  - 視界ブロック（R5.A）は★とTechレーティングを使う公式の式。値は利用者がパネルで入れる（アプリを開いている間だけ保持）。
  - R1.B.2（Shuffle/Shuffle Periodは未使用か0）に合わせ、`buildExportInfo`はShuffleが0なら周期も0で書く（他のエディタや公式譜面は0.5を書くため、
    読み込んだ値をそのまま出すと常に違反になっていた。ゲームはこの2項目を使っていないので遊び心地は変わらない）。

## 自動ライティング（2026-10-03）

- 入口は3つ: ファイルメニュー「自動ライティング…」・LIGHTINGのツールバー「自動ライト」・譜面チェックのライト不足の項目の
  「💡 自動ライティング…」（対象の項目は`mapcheck-panel.js`の`LIGHT_FIX_MC`/`LIGHT_FIX_BL`。作成後にチェックをやり直す）。生成は`js/lighting/auto-light.js`（`generateAutoLights`）、配置は`editor-app.js`の`autoLightPlan`/`applyAutoLight`。
- 狙いは譜面チェックのライト項目（BS Map Check の`insufficientLight`、BL評価リストの R10.A・R7.B）を満たすこと。**R10.Aの数に入るのは
  環境の表(`BASIC_TRACKS[env].l`)の種別だけ**（Defaultなら0〜4。リング回転/ズーム・レーザー速度は数えない）で、分母は曲の長さ（拍）。
  ノーツだけでは足りないので、最後に足りない拍をRINGSのフェードで埋めて1拍あたり1.2個にしている。BACKは曲の頭から最後の物の2拍後まで
  消さない（ボムが常に照らされる＝R7.B）。色はバニラ（赤/青）のみ。
- 一番ノーツの多い難易度から作り、中身のある全難易度へ同じものを配る。ライトのレーンを一番上に1本足し、曲全体の長さの1クリップに入れる
  （既存のライトには触れない。重なりは利用者がレーンを消す/ミュートして選ぶ）。
- 画面外の難易度も変えるため、履歴に専用の領域`'diffs'`（`dumpDomain`/`restoreDomain`）を足した＝1回のUndoで全難易度とロックが戻る。

## カバー画像の補正（2026-10-03）

- 譜面チェックのカバー画像の項目（`mapcheck-panel.js`の`COVER_FIX_MC`/`COVER_FIX_BL`）に「🖼 カバー画像を補正…」。処理と確認画面は`js/media/cover-fit.js`、
  入口は`editor-app.js`の`openCoverFit`。正方形にする（中央を切り抜く＝既定／引き伸ばす／余白で埋める）・256未満は256へ拡大・png/jpg以外はpngへ。
- **元の画像ファイルは変えない**。設定はカバーノードの`data.fit={mode,bg}`だけで、書き出し（`exportMap`）は`fitCoverImage()`で補正した画像を、
  譜面チェック（`collectMapCheckInput`）は`measureCoverFit()`で補正後の寸法・名前だけを使う（どちらも`connectedCoverFit()`。PNGのエンコードは重いのでチェックではしない）。元ファイルへは書けない（`_NativeAccess`）し、補正済みの画像に差し替えると
  開き直した時に`nativePath`の元画像へ自動で繋ぎ直されて補正が消えるため。`infoGraph`の中なので保存・Undo・未保存ランプは自動で付く。
- 画像を選び直したら`fit`を消す（前の画像向けの設定のため）。同じ画像の「再接続」では残す。補正が効く時だけカードに「書き出し時に…へ補正」と「補正をやめる」。

## 難易度を測る（BeatLeaderの星の近似・2026-10-02）

- 計算は**本体に同梱しない別配布のプラグイン** nlm-rating（https://github.com/Oz-Co-two/nlm-rating ・MIT・.NETの自己完結exe・zip約19MB）。
  BeatLeaderの公開コード（RatingAPI＋beatleader-analyzer server-dev）を使う。本家と同じ星は保証できない（Accが本家より2〜9%低い譜面がある）
  ので、画面には「近似値・公式ツールではない」と必ず出す。比較テスト・上流の追従手順はプラグイン側のREADME。
- NLM側: `rating_plugin.py`（取り込み・更新・実行）＋`serve.py`の`/__rating/*`（POST）＋`js/rating/rating-panel.js`。
  入力は譜面チェックと同じ`collectExportDiffs()`/`buildExportInfo()`（`collectRatingInput`）。
- 置き場所は exe隣の`plugins/rating/<版>/`（`current.json`で使う版を選ぶ・旧版は残す）。取得先URLは`rating_plugin.py`に固定し、
  zipは`manifest.json`のSHA-256・サイズと照合してから展開する。JSからURL・パスを渡せるようにしないこと（署名なしexeを実行するため）。
- 通信仕様の版`PROTOCOL`（rating_plugin.py）はプラグイン側`Program.Protocol`と同じ値。入出力の形を変えたら両方を上げる
  （NLMは知らないprotocolの版を取り込まない＝古いNLMに新しすぎるプラグインが入らない）。
- 上流はノーツ20個未満の難易度を計算しない（`skipped:"tooFewNotes"`）。
- プラグイン側の保守はそのリポジトリで行う: `python build.py`（zipとmanifest.json）→ `python tests/compare_bl.py <exe>`（本家の値との比較。
  Pass/Techが1つでもずれたら失敗）。上流の追従手順はプラグインのREADME。公開は**プラグインのリリースが先、それを使うNLMの版が後**。

## 本体の自動更新（2026-10-02）

- `app_update.py`（確認・ダウンロード・照合・展開・差し替え）＋`serve.py`の`/__update/*`（POST）＋`js/update/update-dialog.js`。
  起動時の確認はexe版だけ・環境設定`bsnm_updateCheck`で OFF 可・通信の失敗は黙って無視。「更新しない」の版は`bsnm_updateSkip`
  （それより新しい版が出るまで起動時に出さない。ファイルメニューの「更新を確認…」からは常に出す）。
- 最新リリースに添付した`update.json`（`tools/make_release.py`が作る）を読む。中身は zip の SHA-256・サイズと、
  `CHANGELOG.md`/`CHANGELOG.en.md`の各版の行頭の太字（`- **〜**`）＝更新のお知らせに出す見出し。
  **変更点は README ではなく CHANGELOG に日英両方で書く**（版の並び・見出しの数が日英で違うと make_release が止まる）。
  README も日英2つ（`README.md`/`README.en.md`）あるので、片方を直したらもう片方も直す。GitHub のリリースノートも日英併記
  （日本語の後ろに`## English`。v1.4.0-oz から）。表示言語の初期値は日本語なので、英語の案内では「環境設定」の位置で説明している。
- 差し替えは**新しい版の exe**が行う: 旧版が zip を exe 隣の`_update/new/`へ展開 → その exe を
  `--apply-update --target <配布フォルダ> --pid <旧版のpid> --lang <ja|en>`で起動して自分は終了 → 新しい版が旧版の終了を待って
  `NonLinearMapper.exe`・`_internal`・案内文だけを入れ替え（前の版は`_previous_<版>/`に1世代）→ 起動し直し → `_update/`を片付け。
  **この引数・update.json の形式（`FORMAT`）・zip の中身の形は版をまたぐ約束**（旧版が新しい版の exe を呼ぶため）。
  形式を変える時は`FORMAT`を上げる（旧版は自動更新せずリリースページを開く案内になる）。
- 別の PyInstaller 製 exe を起動する時は`_env_for_child()`（`PYINSTALLER_RESET_ENVIRONMENT=1`・`_PYI_*`を消す）を通すこと。
  親の設定を引き継ぐと子の exe が正しく起動しない。
- 差し替え役として起動された時は`app.py`の`main()`の先頭で抜ける（画面・サーバー・関連付けの登録をしない。登録すると
  .nlmf が消える予定の`_update/`の exe を指してしまう）。
- 取得先URLは`app_update.py`に固定。JS から受け取るのは言語（と更新内容を開く版番号）だけ。

## song.egg 書き出し（変換・キャッシュ）

- 元の音源がOGGならバイトコピー、それ以外（mp3/wav/flac等）はffmpegで`libvorbis`へ変換。
- 変換は`serve.py`の`/__convert/toOgg`（POST、生バイナリボディ、`?ext=xxx&leadInMs=xxx`、Musicを分割・トリムしていれば`&segs=`）。
  ffmpeg呼び出しには`creationflags=CREATE_NO_WINDOW`必須（無いと一瞬コンソール窓が出る）。
  エラーを返す時も**送られた音源（本体）を先に読み切ってから応答する**。読まずに応答して閉じると、Windowsでは残ったデータのせいで
  接続がリセットされ、ffmpeg無し等の応答がJSに届かず通信エラーになる（2026-10-04に修正。大きい本体のPOSTを足す時も同じ）。
- 出力先フォルダに`.nlm-egg.json`という小さなマーカーファイルを置いて、音源のsize/mtime/leadInMs/segsが
  前回と同一なら再変換をスキップする（ffmpeg起動・大きい音声ファイルの再書き込みを避ける）。
- 書き出しパネルの「song.eggを強制再変換」チェックボックスでキャッシュを無視して強制再生成できる
  （初期化・やり直し用）。

## 未保存検知（ランプ・終了時の確認）

- 判定は`projSig()`（`buildProjectText`と同じ項目を副作用なしで直列化）と保存時点の値の**比較**。
  `metaDirty`は履歴に積まれる編集で立たない・Undoで戻らない等の穴があり判定には使っていない。
  **プロジェクトに保存する項目を`buildProjectText`へ足したら`projSig`にも足すこと**（足さないとその変更でランプが点かない）。
  逆に、自動で書き足される派生値（例: `infoBase._beatsPerMinute`）は除外しないと「元に戻してもランプが消えない」誤検知になる。
- 閉じる確認は`app.py`の`events.closing`（未保存時だけ中止→JSの`__nlmAskQuit`で3択）。pywebview標準の
  `confirm_close`は英語固定なので使わない。closingはUIスレッドで同期実行＝中で`evaluate_js`を待つとデッドロックする。
- `editor-app.js`内の`window._dbg`は`js/main.js`が起動時に上書きするため、そちらに診断を足しても外から見えない。

## 開発用窓口とローカルサーバーのアクセス制御（2026-09-28）

- `window._dbg`（main.js・ランタイム全体）/`window._dbgApp`（editor-app.js・読み取り専用）/`_cam`/`_ctl`は
  **pywebview外かつURLに`?dev=1`の時だけ**作る（`isDevMode()`/`NLM_DEV`）。配布版に開発用の入口を残さないため。
  診断を足すなら`_dbgApp`へ（値の複製を返すだけにし、書き換え機能は持たせない）。
- 検証は`tools/cdp.py`（ヘッドレスEdge＋CDP。撮影・本物の入力・JS実行）と`tools/fixtures/`を使う。詳細は`tools/README.md`。
  決まった確認は`tests/`のテストにして`tools/run_tests.py`で回す（上の「テスト」節）。
- `serve.py`はHostヘッダーがローカル名でない要求を403にし（DNSリバインディング対策・追加は`NLM_ALLOWED_HOSTS`）、
  **POSTは`X-NLM-Request: 1`ヘッダー必須**（他サイトからのCSRF対策）。**新しいPOST APIを足したら、JS側のfetchにも
  このヘッダーを付けること**（付け忘れると403で無言に失敗する）。
- `serve.py`の`translate_path`は`\`・ドライブ名・`..`を含むパスを404にする（Windowsではこれらでフォルダ外を読めてしまう）。
  フォルダ一覧（`list_directory`）はアセット走査用に`asset/`配下だけ許可。

## セキュリティの約束事（2026-09-28の点検で導入）

他人から受け取るファイル（.nlmf・.nlmclip・Info.dat・翻訳ファイル）の中身は信用しない、が前提。
- **innerHTMLへ差し込む値のうちファイル由来の文字列は必ず`escHtml()`を通す**（editor-app.js冒頭）。色をSVG属性へ
  差し込む時は`safeHex()`。点検時、.nlmfの曲名(`graph.song.name`)がそのままinnerHTMLに入りスクリプトが実行できた。
  テキストだけなら`textContent`を使うのが一番安全。
- **CSP**（editor.htmlの`<meta http-equiv="Content-Security-Policy">`）: インライン`<script>`と`onclick="..."`等の
  HTML属性ハンドラは禁止（二重の守り。1つ目の約束を破っても仕込まれたスクリプトは動かない）。イベントはJSで
  `addEventListener`する。importmapだけはsha256で許可しているので、**importmapを変えたらハッシュを計算し直す**
  （改行コードで値が変わらないよう1行のまま。`base64(sha256(<script>と</script>の間の文字列))`）。
  外部サイトの読み込み・`eval`も不可（今は使っていない）。
- 翻訳ファイルの訳文に`<`が含まれていたら`loadLang()`が捨てて既定文にする（訳文もinnerHTMLに入るため）。
- **ファイル読み書きの許可範囲**（app.pyの`_NativeAccess`）: JSへ渡す`fs_*`/`read_song_file`は任意パスを受けない。
  - 書き込み: 許可済み出力フォルダの中だけ、拡張子は`_WRITE_EXTS`（.dat/.egg/.json/画像）だけ。
    **書き出しで新しい種類のファイルを作るようにしたら`_WRITE_EXTS`に足すこと**（足さないと`not-allowed`で失敗する）。
  - 許可済み出力フォルダ＝`pick_folder`（ネイティブのフォルダ選択ダイアログ）で選ばれたフォルダ。exe隣の
    `config/native_out_dirs.json`に保存され次回も自動接続できる。JS側から許可を足す口は作らないこと。
  - 読み込み: 音源/画像の拡張子、そのセッションでダイアログから選んだファイル、許可済み出力フォルダの中だけ。

## 表示言語（日本語・英語・2026-10-04）

- 訳の仕組みは5つ: JSの文言は`t('キー','日本語')`/`tf()`、HTMLは`data-i18n`（文字）/`data-i18n-t`（title）/`data-i18n-ph`（placeholder）、
  画面下部のメッセージ（`stat()`/`showErr()`）は**日本語の文面そのものを`m:`キーにして**引く、画面に浮かぶショートカット一覧は
  `sk:`（説明）/`skk:`（操作）、パネルの日本語の表は接頭辞＋キー（`mc.k.`・`bl.r.`・`act.`=ショートカット編集の操作名など）。
  **新しい文言は日本語を直書きせず、`lang/ja.json`と`lang/en.json`の両方にキーを足す。**
- `m:`キーは文面が変わると当たらなくなる（黙って日本語に戻る）。メッセージの日本語を直したら`en.json`の`m:`キーも直す。
- 言語を切り替えた時に訳し直されるのは、`data-i18n`系の付いた要素と`loadLang()`が呼び直す描画だけ。
  **一度だけ組み立てる画面（INFOのノードのカードなど）に文言を入れる時は`data-i18n`を付ける**（付けないと前の言語のまま残る）。
- 訳し漏れは`tests/e2e_misc/test_english_ui.py`で見つける（英語で起動して主な画面を回り、画面の文字・ツールチップ・キャンバスに描いた文字・
  メッセージから日本語を探す。見つけた全文は`test-out/english_ui.txt`）。画面・ダイアログを足したら`english_ui_helpers.tour()`にも足す。
- exe版（app.py）は`config/settings.json`の`bsnm_lang`を`_ui_lang()`で読み、ファイル選択ダイアログの種類名・エクスプローラーの種類名を合わせる。
  serve.py はエラーを文言ではなく種類（例: `exists`）で返し、JSが訳す。
- 表示言語の初期値は日本語（`bsnm_lang`が無い時）。英語の案内では「左上の2つ目のメニュー『環境設定』→『言語 / Language』」と位置で説明する。
- 英語版のチュートリアルの画像は`tools/make_tutorial_shots.py --en`・`make_advanced_shots.py --en`で`docs/images/tutorial-en/`・`tutorial-advanced-en/`へ撮る。

## 削除済み機能（意図的）

- 「最近使ったファイル」機能（`addRecent`/`fillRecentMenu`/`openRecentHandle`）— 上記のIndexedDB
  クラッシュの直接原因だったため、メニュー・JS・CSS・翻訳ファイルから完全に削除した。
  同じ発想の機能を作る場合は、必ずネイティブパス方式（上記4番）を使うこと。

## 触らなくていい・生きていないコード

- 「song/in/outノードをキャンバスに描画する古いグラフエディタ」は**到達できないことを確認済み**（2026-10-04・カバレッジ調査）。
  `ndView`は常に`'layers'`（代入は宣言だけ）で、ノード用の処理は`ndView!=='layers'`の時だけ動く。全テストでも一度も動かない。
  該当: `activateLine`/`deleteSelNode`/`removeNodeMerge`/`pasteNode`/`copySelNode`/`compileGraphToFlat`/`nodeGeomOf`/`nodeRowsFor`/
  `portHit`/`editExtraNode`/`nodeExtraH`/`edgeHit`/`resizeAt`/`altAt`/`allNodeIds`/`loadLineDiff`/`_ndWidgets`等と、それを呼ぶ
  右クリックメニュー・キー処理の分岐（`js/chart/graph-legacy.js`も）。`songNode`/`graphEdges`/`extraNodes`自体は
  `applyInfoGraph()`経由で今も現役（INFOノードエディタのミラー先）なので消さない。
- どこからも呼ばれていない関数: `addMarker`（今は`addMarkerAt`）・`srcNjsOf`・`setLightBehavSmart`・`flipLightColors`・`pvFillEnvSel`。
- 上の2つは削除の候補（当面は残す）。消す時は methodNames からも外し、全テストで確かめる。

## その他

- gitはこのプロジェクトに元々入っていなかった（2026-09-20にこちらで`git init`した）。
  配布用exeフォルダ（`NLM-app/`、ビルド成果物の`dist/`・`build/`・`.venv/`・`.venv-build/`）は
  `.gitignore`済み＝ソース以外はバージョン管理していない。

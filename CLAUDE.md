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
  窓の位置・大きさ・最大化は、実際に閉じる時に`config/window.json`へ残し、次に開く時に使う（2026-10-18・play-list と同じ作り。
  値は pywebview の論理の値・最大化中は`RestoreBounds`・タイトルバーが今の画面に見えない位置は使わない。未保存の3択でキャンセルした時は残さない）。
- `serve.py` — 静的ファイル配信＋ローカル専用API（`__settings/save`, `__openarg`, `__asset/*`,
  `__convert/toOgg`等）。`python serve.py`単体でも起動でき、その場合は起動時に表示される合言葉付きの URL
  （`http://127.0.0.1:8138/editor.html#k=…`。既定のブラウザで自動で開く）を普通のブラウザ（Edge/Chrome）で開いて動作確認できる
  （DevToolsが自由に使える最速の検証手段。開発用窓口は `editor.html?dev=1#k=…`）。合言葉は下の「開発用窓口と…」節。
- `song_analysis/` — 曲の解析（テンポの推定・構成の解析。librosa 等）。serve.py の `/__analysis/*` から使う（下の「曲の解析」節）。
- `editor.html` → `js/main.js` → `js/runtime/editor-app.js`（実質1万行超のモノリシック本体）。
  UI・保存・書き出し・3D描画・音声処理が全部ここに入っている。
- `js/runtime/editor-runtime.js` / `js/project/save-system.js` は「メソッド一覧を持つラッパークラス」。
  実装は全部`editor-app.js`のクロージャ内にあり、これらはただの委譲層（`rt.foo`を呼ぶだけ）。
  新しい関数を追加/削除したら、ここの`methodNames`配列と対応メソッドも忘れず更新すること
  （忘れても動くが、参照が浮いた状態になる）。

## テスト（2026-10-04）

- **普段の修正・機能追加では、全テストは回さない**（2026-10-04の取り決め。当時は全部で約6〜7分かかった。2026-10-11にテストのEdgeを
  GPU描画・描画は毎秒30回まで・大きいグループを分けて同時に流す形にして約1分半になった。仕組みは`tests/README.md`）。直した所のテストと、影響しそうな周辺の
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

- 開発用venv: `.venv-build/`（`.gitignore`済み）。`pip install pywebview pythonnet pyinstaller librosa scipy scikit-learn`
  （後ろの3つは曲の解析＝下の「曲の解析」節。exe に同梱する）。
  **Python 3.14**で作る（`py -3.14 -m venv .venv-build`。2026-09-28に3.9から移行・3.14はセキュリティ修正が2030-10まで）。
  上限はpythonnet（3.1.0は`<3.15`）で決まるので、3.15以降へ上げる時はpythonnetの対応を先に確認すること。
  `.venv/` は `tools/` のテンポ解析用（Python 3.9・librosa 0.11）で、ビルドには使わない（tools は `.venv-build` でも動く）。
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
- **第三者のライセンス表示**（2026-10-19）: `LICENSE` と `THIRD_PARTY_NOTICES.txt` は `nlm.spec` が exe の隣へ写し、`app_update.py` の
  `REPLACE_ITEMS` にも入っている（自動更新でも入れ替わる。`make_release.py` は無ければ止まる）。**部品を足した・版を上げた時は、ビルドした
  `_internal` の実際の中身（DLL・dist-info・埋め込みモジュール）で THIRD_PARTY_NOTICES.txt を直す**（pip の一覧だけで決めない）。
  LGPL の部品（libsndfile・mpg123・LAME・libsoxr）のソースの入手先は THIRD_PARTY_NOTICES.txt の付録C。`build_and_deploy.py` は
  手元の NLM-app へは exe と `_internal` だけを写す（ライセンスの2ファイルは利用者向けの zip と自動更新で届く）。
- **LGPL の部品のソースはリリースに添付する**（2026-10-20・v2.0.0-oz から）。同梱の版のソースと組み立ての設定（libsndfile・mpg123・LAME・
  python-soxr と libsoxr・DLL を作った libsndfile-binaries と vcpkg の port）を `release-assets/lgpl-src/`（git の管理外）に置き、zip・update.json と
  一緒に添付する（`make_release.py` はこのフォルダと `SOURCES.txt` が無ければ止まり、表示する `gh release create` に全部並べる）。
  中身・照合・版の根拠は `SOURCES.txt`（英語）、ファイル名は付録C。**soundfile・soxr の版を上げたら取り直し、SOURCES.txt と付録Cを書き直す**:
  libsndfile の DLL は soundfile のタグのサブモジュール `_soundfile_data`＝bastibe/libsndfile-binaries のコミットで、その GitHub Actions が vcpkg で組み立てる。
  DLL に版の文字列が無い部品（mpg123）は、DLL に残る `buildtrees\<port>\src\<ref>-<hash>.clean` の hash（元のソースと各パッチの SHA-512 から作る）を
  vcpkg の port の履歴で計算し直して版とパッチを決める。libsoxr は `soxr_ext.pyd` の版の文字列（git describe の形）と python-soxr のタグのサブモジュール。
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
   **MEDIA のライブラリフォルダも同じ考え方で記録する**（2026-10-12。ダイアログの実パスを `config/library.json` へ。下の「MEDIA ライブラリ」節）。
   `saveLibDirs()` は空のまま残してある（ブラウザ版の一時的なフォルダの経路から呼ばれるため）。
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
     エディタでは合っているのにゲームではずれた。**Musicの再生の仕方（`play()`）を変えたら`eggPieces()`（＝`musicPieces()`。スペクトログラムも同じ表で描く）も合わせること。**

## 曲の音量補正（2026-10-18）

- 置き場所は NLE の Music レーンの左溝（HTML の`#musicGain`を canvas の溝の上に重ねる）。難易度ボタンの右の帯`#musicBar`は既定の幅で
  ほぼ満杯で、部品を足すと飛来速度の欄が EXPERT のボタンに重なり、画面テストで「崩れ」になる（利用者と決めて溝へ移した）。
- 値は`songNode.gainDb`（dB・±20・0 の時はキーを持たない＝0 に戻せば未保存のランプも消える）。プロジェクトに保存され、'node' の履歴で戻せる。
  再生は`songGain`（Web Audio の音量部品）。**Musicの音を鳴らす経路を足したら`songGain`へ繋ぐこと**（本編の`play()`と試聴ノードは繋いである）。
  書き出しは`/__convert/toOgg`の`gainDb`→ffmpeg の`volume`（無音追加・切り貼りの後）。補正があれば元が OGG でも変換する。
- 環境設定の「ミュージック音量」（`volCfg.mu`）は作業中の聞こえ方だけで、書き出しには入らない。別物なのでツールチップに書いてある。
- 「自動調整」は`js/audio/loudness.js`（BS.1770 の LUFS とトゥルーピーク。実曲で ffmpeg の loudnorm と 0.05 LU 以内で一致）。
  目標 -9 LUFS・ピーク -1 dB で止める・**自動では下げない**（利用者の決定。手元のカスタム曲の相場が -13〜-5 LUFS だったため）。
  測るのは`eggPieces()`の区間（書き出す song.egg に入る所）の元の音源＝何度押しても同じ値になる。

## 曲の解析の画面側（テンポの推定・構成の帯・2026-10-19）

- 画面・通信・保存の形は `js/analysis/song-analysis.js`（見た目は `css/analysis.css`）。editor-app.js は本体の状態との橋渡しだけ（`anaGrid`・`anaAtGrid`・
  `anaApplyTempo`・`anaExportMarkers`・`anaSeek`）。解析は serve.py の `/__analysis/*`（upload→tempo→status→structure→status、cancel。すべて POST）。
- 入口はファイルメニューと、スペクトログラムの溝の［🎼 曲を解析］（音源がある・結果が無い時だけ）。ボタン1つで テンポ→（今の BPM・無音追加と違えば
  確認の画面: 提案／候補B＝半拍ずらし／適用しない。**自動では変えない**。急に出るので Enter では押さない）→今の目盛りで構成→帯、まで進む。
  BPM・無音追加の欄は履歴に積まないので、適用は専用の履歴の領域 `'tempo'`（BPM・`songNode.offset`）で1回の Ctrl+Z で戻す。
  溝のボタンは目立たせるため配置モードと同じ紫（`--accent`）の塗り（2026-10-20・利用者の要望。英語でも溝の 128px に収まる）。
- **曲を取り込んだ時の「曲を解析しますか？」**（2026-10-20・利用者の要望）: editor-app.js の `anaAfterLoad()` → `songAna.songLoaded()`。呼ぶのは利用者の操作で
  新しく曲を取り込んだ時だけ（音楽ファイルを読み込む・MEDIA から Music へ・曲データを読み込む＝全部読んだ後に1回）。
  プロジェクトを開いた時の自動読込（keep=true）・再接続（`restoreLineAssets`、音源の無いプロジェクトへ同じ名前の音源を選び直す＝`songReconnect`）・
  ドラッグ中の波形の先読みでは呼ばない。**音源を新しく取り込む経路を足したら `anaAfterLoad()` も呼ぶこと。**
  出さない条件（song-analysis.js）: 環境設定 `bsnm_anaAsk='0'`（キーが無い＝聞く・環境設定のアプリケーション設定に切り替え）・この起動で解析の API が無い／使えない
  （no-api・unavailable）・解析中・この曲の結果があり目盛りが今と同じ。他の画面（`#dirtyDlgBg`・`#updDlgBg`・環境設定）が出ていれば閉じるまで待つ。
  急に出るので Enter では押さない・Esc＝今はしない。履歴・`projSig` には関係しない。
  **テストの環境は既定で出さない**（`tools/cdp.py` の `Editor.TEST_SETTINGS` を一時のデータフォルダの settings.json に書く・`t.fresh()` も書き直す＝
  多くのテスト・撮影が曲を読み込むため）。確かめるテストは localStorage の `bsnm_anaAsk` を消して出す（`tests/e2e_nle/test_analysis_ask.py`）。
- 帯はスペクトログラムの箱（`#specPane`）の上の段 `#anaPane`。**結果がある時・解析中だけ出し、その間スペクトログラムを下へ詰める**
  （NLE のレーンの高さを変えない＝1600×980 でレーンにスクロールが出ない。帯を常に出すとレーンが最低の高さを割る）。上＝セクション（名前＋番号・同じ番号は同じ色・★サビの候補）、
  下＝細かい区切り。クリック＝その頭へ（窓は動かさない）・ダブルクリック＝番号ごとに名前を付け直す・右クリック／溝の「⋯」＝クリップを作る・マーカーへ書き出す・テンポの推定結果・解析し直す・結果を消す。
- 帯の上の知らせ `#anaMsg`（2026-10-20・利用者の要望: 右端では気づきにくい・処理が続いていると分かるように）: **解析中は帯の左寄せ**（溝 128px のすぐ右＝`left:136px`。
  NLE は画面の右側なので画面の中央寄り）で、`--accent` を濃くした紫の塗り（`#3a2a7c`・枠 `#9a80f5`・白い太字）。動きは控えめに2つ＝進み具合のバーに斜めの縞が流れる・
  枠の外の光がゆっくり明滅（どちらも opacity・transform だけ＝再生中の描画を重くしない。`prefers-reduced-motion` では止める）。部品は種類と言語が変わった時だけ作り直し、
  進み具合は文とバーの幅だけ書き換える（`syncMsg`。作り直すと縞が頭から跳ねる）。**目盛りが変わった時の知らせは右寄せのまま**（帯の結果の上に出るので、左だと帯の頭の区切りを隠す）。
  解析中の文の欄は、作った時にその言語で一番長い文（全段階・100%）の幅を測って固定し（`fixRunTextWidth`）、数字は等幅・バーは 220px
  ＝数字の桁や段階が変わっても箱の長さ・バーの位置が動かない（利用者の要望: 1桁→2桁で伸び縮みし、進んだり戻ったりして見えた）。段階の文を足したら `runText` に足すこと。
  画面テストは撮る時にアニメーションを止める（`__vis.freeze()`）＝明滅の光は写らない。
- **溝の［🧩 クリップを作る］と「次にやること」の案内**（2026-10-20・利用者の要望: 「⋯」を開かないと次が分からない。ただ区切りの良し悪しは曲を聞かないと決められないので、
  いきなりクリップを作る画面は出さない）。処理は song-analysis.js の `syncClipsBtn`・`showGuide`（見た目は analysis.css）。
  - ボタンは結果がある時だけ、帯（40px のまま）の**溝だけを 26px 下へ延ばした所**（`#anaAct`・溝の下端は箱の上から 66px）に置く。スペクトログラムの溝は何も描いていないので
    重ねるだけ＝スペクトログラム（54px）・NLE のレーンの高さは変わらない。**スペクトログラムの溝に何か描くようにしたら、この 26px と重ならないようにすること。**
    色は［🎼 曲を解析］と同じ（`--accent` の塗り＋白い太字）。押す＝帯のメニューの「クリップを作る…」（`anaOpenClips`）。目盛りが変わった（stale）時は薄くし、押すと同じ理由で断る。
  - **その解析の結果から一度クリップを作った後は、彩度を落とした暗い紫**（`.made`・塗り `#463c6a`・枠 `#6c5e9f`・文字 `#dcd6ef`、hover で `#564a84`。2026-10-20・利用者の要望:
    紫が目障り。押せることは分かるように枠・文字・指のカーソルは残す）。ツールチップも「作成済み・もう一度押すと新しいレーンにもう1組」。印は解析の結果の `made:true`
    （`anaMakeClips` が作った後に `songAna.setMade(true)`）＝保存され開き直しても暗いまま・解析し直すと新しい結果には無い＝元の紫。作る操作の Ctrl+Z で印も戻る
    （全難易度の履歴 `'diffs'` の控えに `anaMade` を入れている。解析の結果そのものの変化は全部 `'ana'` の履歴に積まれるので、'diffs' では印だけ戻せばよい）。
  - 案内を出すのは「曲を解析」で構成の解析が終わって帯が出た時だけ（テンポの確認の後・解析し直した時も）。保存した結果を開いた時・やめた時・失敗した時は出さない。
    環境設定 `bsnm_anaGuide='0'`＝出さない（キーが無い＝出す・アプリケーション設定の「曲の解析」に切り替え）。他の画面が出ていれば閉じるまで待つ（「曲を解析しますか？」と同じ）。
    急に出るので Enter では閉じない・Esc＝閉じる。閉じると本物のボタンを約2.6秒光らせる。いきなりクリップを作る画面は出さない。
  - 案内の中の画像は `guide/ana-clips-btn-<ja|en>.png`（`tools/make_guide_shots.py` が撮る・`guide/` は serve.py の `PUBLIC_DIRS` と nlm.spec の datas に入れてある）。
    どれを出すかは訳の `ana.guide.img`（`guide/` の .png の名前だけ受け付ける）。読めない時は図を外して文だけ。**ボタン・帯の見た目を変えたら撮り直す。**
  - テストの環境は既定で出さない（`Editor.TEST_SETTINGS` の `bsnm_anaGuide='0'`）。確かめるテストはキーを消して出す（`tests/e2e_nle/test_analysis_guide.py`）。
- 保存はプロジェクトの `analysis`（`{v:1,tempo,structure,names,grid}`＋クリップを作った後だけ `made:true`・無ければキーごと無し）。`projSig` にも入れる＝名前の付け直しで未保存のランプが点く。
  帯の変化（結果の到着・名前・消す）は履歴の領域 `'ana'`。ファイル由来なので `load` は知っている項目・正しい形だけを残す（名前はキャンバスと textContent にだけ使う）。
- **目盛りが変わったかの判定**: `grid`＝解析した時の `anaGrid()`（BPM・無音追加 ms・テンポパート・Musicの配置 `musicBeat`/`musicSegs`・音源の名前）と今の値を比べ、違えば帯を薄くして
  「解析し直してください」。目盛りに効く状態を足したら `anaGrid` にも足すこと。構成に送る `at`（拍の1/4ごとの元の音源の秒・音の無い所は null）は `audioPosAtBeat(b,true)`。
- 解析し直した時は帯だけ置き換え、付け直した名前は同じ位置（解析した時の元の音源の秒 `a0/a1`。無ければ拍）で一番重なる新しい番号へ引き継ぐ。
- Python が付ける仮の名前（イントロ/Aメロ…）は日本語で届くので、知っている名前は `ana.nm.*` で訳して出す。テンポの結果の `error`（日本語の文）は出さず、種類としてだけ扱う。
- マーカーへの書き出しは、書き出したマーカーに `ana`＝書き出した時の名前を持たせ、手で名前を変えていなければ次の書き出しで直す（同じ位置の他のマーカーは変えない）。
- **解析からクリップを作る**（帯のメニューの「クリップを作る…」・2026-10-20）: 確認の画面は `js/analysis/ana-clips.js`、作るのは editor-app.js の `anaOpenClips`/`anaMakeClips`、
  材料は `songAna.clipSource()`（表示中の名前＋番号・帯の色・負の拍や重なる区間は飛ばす）。利用者と決めた形: 新しいノーツのレーンを一番上に足し（両方なら2本・上がセクション）、
  空のクリップ（名前＝「<表示中の名前> S<番号>」・細かい区切りはグループ名、色＝帯の色 `colHex`）を作り、そのレーンを単独編集にする。同じ番号は自動でリンク（既定オン・
  親＝開いている難易度の一番先頭・他の難易度に作った分もその親へ）。開いている難易度には必ず作る。番号が1回だけで他の難易度にも作らない時はリンクしない。
  作ったクリップは解析と繋がっていない普通のクリップ（解析し直しても・結果を消してもそのまま。名前は作った時の表示言語）。
  - 断る: 結果なし・目盛りが変わった（stale）・ノーツのレーンが上限。画面を出している間に結果が変わった（裏で解析し直しが終わった）時も作らない（開いた時の `clipSource()` と比べる）。
  - 履歴は全難易度の `'diffs'` 1回（レーンの追加で全難易度のクリップがずれる）。単独編集は履歴に積まない＝Undo でオフになる。レーンを足すとソロ・ミュートは外れる（`laneShiftAll`）。
    `'diffs'` のやり直しは、戻す時に消した難易度（その操作で作った難易度）を空の土台から作り直す（以前は作り直さず、他の難易度に作った子がやり直しで消えていた）。
- テストは応答を偽物にする（`tests/_lib/analysis_helpers.py`・`tests/e2e_nle/test_analysis.py`・`test_analysis_clips.py`）。

## スペクトログラムと Music の波形の描き方（縮小した時のちらつき・2026-10-20）

- NLE を縮小すると画面の1画素に解析のコマ（10ms）・波形のビン（1/16拍）が何十も重なる。以前は drawImage の縮小・1画素ごとに1ビン拾う描き方で、
  再生中のスクロールで拾う物が変わり山がギザギザにちらついていた（利用者の報告）。今は `js/audio/spectro-levels.js` の**段の絵**（時間方向に2コマずつまとめた
  2倍・4倍…）から、1コマが画面で1画素以上（スペクトログラムの段2から先は1.5画素以上・波形は全段1.5画素以上）になる段を選び、**拡大して**貼る。
  段の境目は音源の秒に固定＝スクロールは同じ絵を小数の画素ずつずらすだけ。波形はビンの境目で段になる形を1つの図形で塗る（1画素ずつの fillRect ではない）。
- 段の絵は生の音源の秒で持つので、BPM・無音追加・テンポパート・Musicの配置・窓の大きさ・UI文字サイズでは作り直さない（拍→秒は描く時に計算）。作り直すのは音源が変わった時だけ
  （スペクトログラム＝`buildSpectroData`・`specForBuf`、波形＝`ovWave` が作り直されたら次の描画で `_ovWaveLv`）。**縮小した帯・レーンに音の絵を描く経路を足したら段の絵を使うこと**（1つ拾うとちらつく）。
- まとめ方は合成曲で見比べて決めた: スペクトログラム＝「dB の平均」と「パワーの平均を dB にした値」の真ん中（最大値は低域が明るい帯に潰れ、dB の平均だけだと短い打音が消える）、
  波形＝最大値。しきい値を全段で上げると既定の拡大（32拍）の見た目がぼけ、段の絵を [1,2,1] でぼかすと拍の縞まで消えた（どちらも不採用）。既定の拡大の見た目は以前とほぼ同じ。
- 絵は横幅4096コマのタイル（前後に1コマののりしろ・継ぎ目は1コマはみ出して描く＝半端な重ね塗りの線が出ない）。以前の1枚のキャンバス（横＝コマ数）は長い曲で描けなかった（Edge で横 40000 は描け 70000 は描けない＝7〜11分の間に上限）。
- **スペクトログラムは実際に鳴る音の並びで描く**（2026-10-20。以前は 2D・3D とも無音追加とテンポだけを見て、Music の配置を見ていなかった＝Music を動かすと波形とずれた）。
  2D の帯（`drawSpecPane`）は再生・書き出しと同じ切り貼り表 `musicPieces()`（`eggPieces()` は同じ表を時刻順に並べた物）から、画面の拍の範囲を Music の区間と
  テンポの境目で区切り（`specMusicSpans`・spectro-levels.js）、区間ごとに「その拍の範囲に鳴る音源のコマ」を段の絵から貼る＝Music を動かす・分割・トリム・並べ替え・
  同じ所を2回使う、のどれも波形と同じように動く・切れる。音の無い所（クリップの無い所・無音追加）は区間が無い＝何も描かない。区間の両端は実画素に揃える
  （分割の継ぎ目・テンポの境目で隣とぴったり接する。曲の頭・終わりで半画素はみ出す分は `drawSpecLevel` がのりしろで描く）。区間の数は見えている Music の区間×テンポの数程度。
  3D の帯（`updateSpecBand`）は行ごとに `audioPosAtBeat(b,true)`。描き直しの判定に拍→音源の秒の対応の印 `specMapSig()`（BPM・テンポパート・`musicPieces`）を含める
  ＝止まったまま Music・無音追加・BPM を変えても描き直す（以前は再生位置が 1/4拍動くまで古い絵のままだった）。Music の区間が重なる所は `musicPieces` の前の物が見える（`audioPosAtBeat` と同じ）。
  **Music の鳴らし方（`play()`）を変えたら `musicPieces()` も合わせる**（再生・書き出し・スペクトログラムが同じ表を使う）。解析の帯（`#anaPane`）は拍で持ち、
  `anaGrid` に Music の配置が入っている＝Music を動かすと「解析し直してください」になるだけで、ここでは変えない。
- テスト: `tests/unit_js/test_spectro_levels.py`（段の値・選び方・タイル・揺れを直す前の貼り方と比べる・区間の計算）、`tests/e2e_nle/test_spectro_draw.py`（本体で描かれる・窓をずらすと絵がずれるだけ）、
  `tests/e2e_nle/test_spectro_music.py`（Music の配置どおり: 帯の各位置の音源の秒＝`audioPosAtBeat`・ずらす・切る・並べ替え・無音追加・継ぎ目・3D の帯・縮小してずらした揺れ。
  位置は開発用窓口 `_dbgApp.spec()`）。キャンバスを `getImageData` で何度も読むと Edge がそのキャンバスを CPU 描画に切り替え、描く重さの計測が狂う（重さを測る時は読まずに待つ）。

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
  - 視界ブロック（R5.A）は★とTechレーティングを使う公式の式。値の欄は`js/mapcheck/bl-stars.js`（2026-10-12）: 「難易度を測る」プラグインが
    あれば BL評価リストを表示した時に自動で測って入れ（BS Map Check のタブでは測らない）、無ければ取り込みの案内（説明を見てから押す2段階）。
    手で書き換えた欄は手入力が優先で、測り直しても上書きしない（BeatLeaderの本当の値用）。値はアプリを開いている間だけ保持（保存しない）。
    R11.H.5（★の低い順・0.5★まで許容）も同じ★で判定する。近似値なので違反ではなく要確認止まり。★が足りない時は所見を`BL.MANUAL`にして手動確認にする。
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

## MEDIA ライブラリ（記録・詳細表示・絞り込み・2026-10-12）

- 構成: Python は `media_library.py`（フォルダの記録 `config/library.json`・走査・キャッシュ `config/library_cache.json`・ファイル読み出し・
  フォルダを開く・プレイ記録 PlayerData.dat・NLM推定の★の記録 `RatingCache`）、`map_hash.py`（譜面のハッシュ）、`song_details.py`（全曲データ）、
  `beatsaver_api.py`（BeatSaver へ1曲）、`native_paths.py`（パスの字面の判定。app.py と共有）、serve.py の `/__lib/*`、app.py の `lib_pick_folder`/`lib_pick_playdata`。
  JS は `js/media/lib-native.js`（`/__lib/*`・疑似ハンドル）・`lib-table.js`（詳細表示・1行＝1難易度・仮想スクロール・並べ替え・列）・
  `lib-filter.js`（検索・絞り込み・件数）・`lib-online.js`（全曲データ・🔍・★のまとめ計算・環境設定の MEDIA タブ）。editor-app.js は配線だけ。
- **ライブラリのフォルダとプレイ記録の場所は、exe 版のダイアログで選んだ物だけが記録される**（JS から増やす口を作らないこと）。JS から受け取るのは
  記録の id・その中の相対パス・ファイル名だけ。ライブラリは読むだけ（書き出し先の許可 `_NativeAccess` とは別）。
- **BeatSaver への問い合わせは、全曲データに無い曲で利用者が🔍を押して確認した1曲だけ**（利用者の決定: サーバーの負荷を最小に。まとめて調べる・
  自動の問い合わせ・「今後は確認しない」は作らない）。全曲データ（kinsi55/BeatSaberScrappedData の songDetails2_v3.gz）は **jsDelivr からだけ**・
  1日1回まで・ETag。取得は環境設定 ON の時だけ JS が頼む（Python から勝手に取りに行かない）。形式（protobuf・formatVersion 3）は
  SongDetails（MIT）の Structs が出典。formatVersion が上がったら `song_details.py` を追従する。
- ハッシュは SongCore と同じ（v2/v3＝Info.dat＋各難易度の .dat、v4＝Info.dat＋audioDataFilename＋難易度ごとに譜面・ライトの組。重複もそのつど足す）。
  BeatSaver・BeatLeader・PlayerData の levelId（custom_level_<大文字>）と一致する。規則を変えるとキャッシュは自動で作り直される。
- NPS は BeatSaver と同じ: 色ノーツ数 ÷（最初〜最後の色ノーツの拍を基本の BPM で秒に）。ダウンロード日は曲フォルダの metadata.json の addedDate を優先
  （Mod が書く。無ければフォルダの作成日と Info.dat の更新日の早い方。フォルダごとコピーすると作成日はコピーした日になるため）。
- v4 の譜面ファイルは NLM の読み込み（`parseDiffFragment`）が未対応なので、NLE へのドラッグ・曲データを読み込むは断る（一覧・絞り込みはできる）。
- 画面の配置（2026-10-12・利用者と決めた調整）: 操作部品は見出しの行 `#libHead`（MEDIA [TAB] PREVIEW の帯の右・入りきらない分だけ折り返す）。
  帯は PREVIEW と共用の `position:absolute` なので、行の先頭の空き `#libHeadGap` の幅を `lib-layout.js` が帯の幅から測って入れる（言語で帯の幅が変わる）。
  部品を足したら、既定の MEDIA の幅（約480px）で2段に収まるかを `tests/e2e_nle/test_media_library_ui.py` で確かめる。左のカタログの幅は `bsnm_libSideW`。
  フィルター・件数・解除・表示の切り替え・大きさのスライダーは1つの組 `#libFiltGrp`（一緒に折り返す。表示の切り替えとスライダーは組の右端＝行の右端。
  折り返しの基準の幅は中身の最小＝ボタン・切り替え・スライダーの幅 `--lib-fb`＋件数の一番短い形 `--lib-cmin`。組の外に置くとスライダーだけが次の段へ1つで折り返す）。
  検索欄を次の段へ送るか（`fitSearch`）は段の数で決める。段は部品の縦の中心で数える（上端で数えると高さの違う部品が別の段に数えられる）。
  **UI文字サイズ（`bsnm_uiscale`）は `#tabFolder` と帯に CSS の zoom で掛かる**: `getBoundingClientRect`・マウスの座標は画面の px、style の幅・`offsetWidth` は
  zoom の前の px なので、画面の px を幅へ入れる時は `cssZoom()`（lib-layout.js）で割る（割らないと 80% で帯と重なり、150% で段が増えた）。
  ResizeObserver の中では、見ている要素より浅い要素の大きさが変わる変更をしない（「ResizeObserver loop」のエラーになる＝次の描画の前へ回す）。
- 詳細表示の列の幅は一覧の全部の行の中身と見出しから測る（`lib-table.js` の `measureWidths`・列の定義の `mw`）。**セルの描き方（`cell`）を変えたら `mw` も合わせる**
  （合わないと文字が…で切れる）。長い名前の列（アーティスト・マッパー・環境・Mod・フォルダ名・タグ）は列の定義の `max` で止める（…で省略・全文はツールチップ）。
  4000行・全部の列でも 50ms 以内が目安（行ごとに `toLocaleString` や DOM を作ると超える。MEDIA が隠れている間は測らない）。見出しの2段は訳の `lib.h.*` の改行。文字の大きさは `bsnm_libFont`（大きさのスライダーを詳細表示の時だけ兼用・Ctrl＋ホイール）、
  行の高さは `rowHeightOf`（CSS の `--lt-rh` と仮想スクロールの両方）。
- NLM推定の★: 曲ごとに nlm-rating を実行（`rating_plugin.measure(body, parallel)`。測定どうしは同時に parallel 個まで・取り込み中は待つ）。
  同時の数は環境設定 `bsnm_rateParallel`（上限は CPU 数と5の小さい方＝ブラウザの同じサーバーへの同時接続は6本まで）。結果はハッシュ＋プラグインの版で記録。
  表示は★の列に `NLM推定 7.12` と言葉と色を付ける（公式の★と見間違えないように。利用者の要望）。
- **新しい .py を足したら `nlm.spec` の datas と hiddenimports に足す**（serve.py が実行時に import するため。足さないと exe だけ起動に失敗する）。
- テスト: サーバーは `NLM_NO_NET=1`（全曲データ・BeatSaver でネットへ出ない）・`NLM_PLAYDATA`（プレイ記録の既定の場所の差し替え。利用者の本物を読まない）。
  記録したライブラリは、テストのデータフォルダの `config/library.json` を書けば次の `/__lib/list` で読み直される。素材は `tools/fixtures/media_lib/`。
  テストの中でエディタを用意する前に `import serve` すると手元の `config/` を触るので注意（`tests/README.md`）。

## 難易度を測る（BeatLeaderの星の近似・2026-10-02）

- 計算は**本体に同梱しない別配布のプラグイン** nlm-rating（https://github.com/Oz-Co-two/nlm-rating ・MIT・.NETの自己完結exe・zip約19MB）。
  BeatLeaderの公開コード（RatingAPI＋beatleader-analyzer server-dev）を使う。本家と同じ星は保証できない（Accが本家より2〜9%低い譜面がある）
  ので、画面には「近似値・公式ツールではない」と必ず出す。比較テスト・上流の追従手順はプラグイン側のREADME。
- NLM側: `rating_plugin.py`（取り込み・更新・実行）＋`serve.py`の`/__rating/*`（POST）＋`js/rating/rating-client.js`（状態・通信・測定結果）
  ＋`js/rating/rating-panel.js`（表示）。入力は譜面チェックと同じ`collectExportDiffs()`/`buildExportInfo()`（`collectRatingInput`）。
- `rating-client.js`は「難易度を測る」パネルと譜面チェックのBL評価リスト（R5.A・R11.H.5の★/Tech）で**1つを共有**する（どちらで測っても両方に出る）。
  `measure({ifChanged:true})`は測る中身（送る .dat の文字列）が前回うまく測れた時と同じなら測り直さない＝開くたびに測っても無駄に exe を起動しない。
  測定中に頼まれた分は、終わってからもう1回だけ測る。
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

## 曲の解析（テンポ・構成・本体に同梱・2026-10-19）

- 計算は `song_analysis/`（`tempo.py`＝BPM・無音追加の提案、`structure.py`＝区切り・グループ・セクション・名前の推測、
  `service.py`＝音源の一時保存と解析の仕事の列）。開発用のコマンド `tools/tempo_leadin.py`・`tools/analyze_structure.py` は表示
  （報告の HTML・答え合わせ）だけで計算は song_analysis を呼ぶ（出力は移す前と同じ）。**計算を直す時は song_analysis を直す**（NLM と tools の両方に効く）。
  tools のモジュールの定数を書き換えると song_analysis にも効く（`song_analysis.expose`。調整用のスクリプトが `A.SECTION_SAME = …` で試すため）。
- API は serve.py の `/__analysis/*`（POST・JSON・エラーは種類）: `upload?ext=`（本体＝音源・上限300MB→`audioId`＝SHA-256）／`tempo`{audioId}／
  `structure`{audioId, grid:{bpm, leadMs, sub:4, at}}／`status`{job}（state・stage・progress・result・error）／`cancel`{job}。
  種類: too-large・bad-audio・too-short・ffmpeg-not-found・unknown-audio・unknown-job・bad-grid・bad-request・busy・cancelled・unavailable・failed。
  テンポの結果の `error`（打点が少なすぎる）は `few-onsets`、セクションの名前は `nameKey`（intro・a・b・chorus・interlude・c・outro）でも返す（画面が訳す）。
  upload は本体を `store` が最後まで読む（失敗しても）。上限を超える本体も読み捨ててから答える（`_discard`・合言葉を確かめた後だけ）。
- 解析は別スレッドで1件ずつ（2件目からは待ち行列）。取り消しは進み具合の区切りごと（重い計算の途中では止まらない）。計算のスレッドは CPU の半分まで
  （threadpoolctl・解析中も編集できるように）。同じ音源・同じ条件の結果は覚えて返す。librosa 等は解析を始めた時に読み込む（service.py は標準ライブラリだけ
  ＝serve.py の起動を遅くしない。exe では最初の解析だけ読み込みに約5秒）。
- 構成の目盛り `at` は NLM の拍 0, 0.25, … ごとの元の音源の秒（null＝音が無い）。**コマの境目がフレームの境目にちょうど乗る曲が多く、秒の最後の桁の違い
  1つで区切りが変わる**ので、テンポが一定で Music を切っていない目盛りは `nlm_grid` が TempoMap と同じ式で秒を作り直す（画面の秒を 10ms に丸めても
  tools と同じ結果）。テンポパート・切り貼りがある時は渡された秒のまま。`grid.bpm` は曲頭の BPM（1単位の拍数を決める）。
- 音源の置き場は OS の一時フォルダの下の `NLM-analysis/`（exe 隣の config/ ではない）。中身のハッシュの名前で、最後に使ってから1日・合計2GBを超えた分を
  古い順に片付ける（解析中・待ちの物は残す）。libsndfile で読めない形式（m4a 等）は ffmpeg で WAV（`<id>.dec.wav`）にしてから読む。
  テストは `NLM_ANALYSIS_DIR` で置き場を差し替える（unit_py の `H.server()` が設定する）。
- librosa は 1.0（Python 3.14 用。解析を作った時は 0.11）。テンポ63曲・構成39曲の採点が 0.11 と同じ結果だった（特徴の差は MFCC の 1.5e-5 だけ）。
  librosa 1.0 は audioread を使わない（読めない形式はエラー＝NLM は ffmpeg へ回す）。**librosa・numpy・scipy・scikit-learn の版を上げたら同じ比べをする**
  （tools/README.md「librosa の版を上げる時」）。
- exe: `nlm.spec` の datas（`song_analysis/*.py`）と hiddenimports。librosa・numba・llvmlite・sklearn・soundfile は pyinstaller-hooks-contrib のフックで入る
  （librosa は lazy_loader が読む .pyi も）。各部品のライセンス文は `copy_metadata` で dist-info ごと入れる（THIRD_PARTY_NOTICES.txt の 9.・部品を足したらそこにも足す）。
  これで exe のフォルダは約46MB→約287MB、配布の zip は約22MB→約118MB（一番大きいのは llvmlite の約115MB）。
  自動更新の上限（app_update.py の MAX_ZIP 600MB・MAX_UNZIP 1500MB）には収まる。numba の JIT の結果は exe では利用者の `%LOCALAPPDATA%\numba\Cache` に残る
  （数百KB。numba が凍結した exe ではそこしか使わない）。

## song.egg 書き出し（変換・キャッシュ）

- 元の音源がOGGならバイトコピー、それ以外（mp3/wav/flac等）はffmpegで`libvorbis`へ変換。
- 変換は`serve.py`の`/__convert/toOgg`（POST、生バイナリボディ、`?ext=xxx&leadInMs=xxx`、Musicを分割・トリムしていれば`&segs=`）。
  ffmpeg呼び出しには`creationflags=CREATE_NO_WINDOW`必須（無いと一瞬コンソール窓が出る）。
  エラーを返す時も**送られた音源（本体）を先に読み切ってから応答する**。読まずに応答して閉じると、Windowsでは残ったデータのせいで
  接続がリセットされ、ffmpeg無し等の応答がJSに届かず通信エラーになる（2026-10-04に修正）。2026-10-05からは全POST共通で、
  `_reply()`/`_deny()`が応答の前に`_drain()`でまだ読んでいない本体を読み捨てる（使う本体は`_raw_body()`/`_body()`で1回だけ読む。
  拒否する要求の本体は保存せず、16MBを超えたら読まない）。**`_reply()`を通さずに応答するPOST APIを足す時は、先に`_raw_body()`か`_drain()`を呼ぶこと**。
- 出力先フォルダに`.nlm-egg.json`という小さなマーカーファイルを置いて、音源のsize/mtime/leadInMs/segs/gainDbが
  前回と同一なら再変換をスキップする（ffmpeg起動・大きい音声ファイルの再書き込みを避ける）。
- 書き出しパネルの「song.eggを強制再変換」チェックボックスでキャッシュを無視して強制再生成できる
  （初期化・やり直し用）。

## 未保存検知（ランプ・終了時の確認）

- 判定は`projSig()`（`buildProjectText`と同じ項目を副作用なしで直列化）と保存時点の値の**比較**。
  `metaDirty`は履歴に積まれる編集で立たない・Undoで戻らない等の穴があり判定には使っていない。
  **プロジェクトに保存する項目を`buildProjectText`へ足したら`projSig`にも足すこと**（足さないとその変更でランプが点かない）。
  逆に、自動で書き足される派生値（例: `infoBase._beatsPerMinute`）は除外しないと「元に戻してもランプが消えない」誤検知になる。
- `buildProjectText`の`view`（再生位置・NLEのズーム・表示の左端。開いた時に`restoreView()`で戻す・2026-10-06）は**わざと`projSig`に入れていない**
  （利用者の要望: カーソルを動かしただけで未保存にしない）。保存した時の値が残るだけで、動かしただけなら閉じる時に確認は出ない。
  開いた直後は音源の読込が終わる前で、曲末が暫定の128拍（`camSongEndBeat`）。3Dカメラの可動範囲（`clampCamera`）は再生ヘッドを必ず含めること
  （含めないと、戻した再生位置が128拍より後ろの時にカメラが押し出されて3Dに何も映らなくなる。2026-10-09に修正）。
- 閉じる確認は`app.py`の`events.closing`（未保存時だけ中止→JSの`__nlmAskQuit`で3択）。pywebview標準の
  `confirm_close`は英語固定なので使わない。closingはUIスレッドで同期実行＝中で`evaluate_js`を待つとデッドロックする。
- `window._dbg`は`js/main.js`が作る（editor-app.js側にあった古い`window._dbg`は、main.jsが起動時に上書きして外から見えなかったため
  2026-10-05に削除）。editor-app.jsの中の状態を見る診断は`window._dbgApp`へ足す（下の節）。

## 開発用窓口とローカルサーバーのアクセス制御（2026-09-28）

- `window._dbg`（main.js・ランタイム全体）/`window._dbgApp`（editor-app.js・読み取り専用）/`_cam`/`_ctl`は
  **pywebview外かつURLに`?dev=1`の時だけ**作る（`isDevMode()`/`NLM_DEV`）。配布版に開発用の入口を残さないため。
  診断を足すなら`_dbgApp`へ（値の複製を返すだけにし、書き換え機能は持たせない）。
- 検証は`tools/cdp.py`（ヘッドレスEdge＋CDP。撮影・本物の入力・JS実行）と`tools/fixtures/`を使う。詳細は`tools/README.md`。
  決まった確認は`tests/`のテストにして`tools/run_tests.py`で回す（上の「テスト」節）。
- `serve.py`はHostヘッダーがローカル名でない要求を403にし（DNSリバインディング対策・追加は`NLM_ALLOWED_HOSTS`）、
  **POSTは`X-NLM-Request: 1`ヘッダー必須**（他サイトからのCSRF対策）。**新しいPOST APIを足したら、JS側のfetchにも
  このヘッダーを付けること**（付け忘れると403で無言に失敗する）。
- **合言葉**（2026-10-11）: 上の守りはブラウザ経由の攻撃だけを防ぎ、ブラウザ以外から直接送られると通る。そこで起動ごとの
  `SESSION_TOKEN` を `X-NLM-Token` ヘッダーで求める（POST 全部と、`PUBLIC_FILES`/`PUBLIC_DIRS` 以外の GET）。
  - 画面へは URL の `#k=…`（`access_url()`）で渡し、`settings-mirror.js` の先頭が同じオリジンへの fetch/XHR に自動で付ける
    ＝JS の通信で個別に付ける必要は無い。Cookie では渡さない（127.0.0.1 の Cookie はポートを区別せず別ポートのページへ漏れる）。
  - 合言葉なしで返すのは許可リストの静的ファイル（`<script src>`・`<link>`・`<img>`・`import()` はヘッダーを付けられない）だけ。
    **画面がヘッダー無しで読み込む物を新しいフォルダに置いたら `PUBLIC_DIRS` に足す**（足さないと403）。守る場所を列挙する形に
    してはいけない（asset/ 内のジャンクション等の別名で抜けられる）。
  - Python から直接要求するツール・テストは `X-NLM-Token` を付ける（`tools/cdp.py` の `ed.token`、unit_py の `H.req` は既定で付ける）。
    `cdp.Editor.url()` は呼ぶたびに `?n=` を変える（`#` 付きの同じ URL へ移ると読み込み直さない＝テストの開き直しが効かない）。
  - `python serve.py` は起動時に合言葉付きの URL を英語で表示しブラウザで開く（`--no-browser`・`--port=`）。表示に日本語を
    入れない（日本語を表せない文字コードで出力をファイルへ回すと起動前に落ちる。test_standalone_start_message）。
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
  - ネットワーク上のパス（`\\server\share\...`）は存在確認・実体の解決だけで接続と認証（NTLM）が起きるので、`may_touch()`が字面だけで
    「このPCでダイアログから選んだファイル・許可済み出力フォルダの中」と確かめてから触る（選んだUNCは`native_out_dirs.json`の
    `unc_files`/`unc_out_dirs`に保存）。`\\?\`・`\??\`・相対パス等は受けない。**JSから来たパスに触る処理を足したら、先に`may_touch()`を通すこと。**
- **ブラウザのファイル選択で選んだファイルへの書き込みの許可**（2026-10-11・app.pyの`_auto_allow_file_rw`）: 「開く…」等で選んだファイルは読み込みの
  許可しか付かず、保存の`requestPermission({mode:'readwrite'})`で WebView2 が画面の上の端に枠の無い確認を出していた（見落としやすく、見た目・位置は変えられない）。
  exe版では`CoreWebView2.PermissionRequested`で、種類が`FileReadWrite`かつこの起動の`http://127.0.0.1:<port>`からの要求だけを、確認なしで許可する
  （`SavesInProfile=False`。他の種類・別の画面は既定の確認のまま）。対象は利用者が選んだかドラッグした物だけ＝書き出し先フォルダと同じ考え方（利用者と合意）。
  「操作から始まった要求だけ」も条件にしたかったが、WebView2 はこの種類の`IsUserInitiated`を常に False と報告する（実機で確認）ため使っていない。
  自動テスト（ブラウザ）では通らない。実機での確かめ方: exe を CDP 付きで起動し、`Input.dispatchDragEvent`でファイルをドロップして
  `getAsFileSystemHandle()`でハンドルを作り（ファイル選択画面は自動で押せないため）、`requestPermission`が確認なしで`granted`になるかを見る。

## アークと端のノーツのつながり（2026-10-06）

- アークは Beat Saber の形式どおり独立した物（頭・尾の座標を自分で持つ）で、ノーツとのつながりは保存しない。
  「拍・列・段が一致」（`arcEndIs`）で、その都度判定する。チェーンは作る時にノーツを消費するので、この話は無い。
- 連動させている操作: 色（`recolorLinkedSliders`）・向き（`redirLinkedSliders`。頭=`d`・尾=`tc`）・ギズモでの移動（`arcLinkPlan`）。
  移動は、ノーツを動かすとつながったアークの端がついてくる（片端=変形・両端=平行移動・頭は尾の拍を越えない）。アークを全体移動すると端のノーツを連れていく。
  アークの頭・尾のミニギズモと、ノーツの無い筒の端のドラッグはアークの端だけを動かす（つながりを外す手段として残している）。
  **ノーツを動かす・向きを変える操作を新しく足したら、これらを通すこと**（通さないとアークが置き去りになる）。貼り付けの追従中は連動しない。
- クリックはノーツ優先: `objUnder`は筒と端のノーツが重なる所（筒の端の近く・レイが端のノーツも通る）でノーツを返し、
  `pickArcEndpoint`は端のノーツを拾わない。以前は端のノーツの上のクリックがアークの端を掴み、ノーツを動かせなかった。
  `pickArcPart`（既定で端のノーツも拾う）は、選択中アークの端点の上の Alt+ホイール（向き）用。
- アークを1本選ぶと頭・尾にミニギズモが出るので、その間だけ全体移動の矢印を大きくする（`GIZMO_SCALE_BIG`）。普段の矢印は小さいまま（原作者の指定）。

## 単独編集（英語 Edit only・2026-10-19）

- ノーツのレーンを1つだけ編集できるようにする（ライトには無い）。入/切は溝の2段目のスイッチ・NLE の上の E（`nleEditOnly`）・3Dの帯のボタン。1つだけオン。
  状態は `editOnlyTr`（ノーツのレーンの内部の段 gi・null=オフ）。レーンの並びは全難易度で共通＝難易度を切り替えても同じレーン。
- 「他のレーンは触れない」は、ロックの判定 `objLockedN` に `objOffEditN` を足して効かせている（ロックの状態 `layerLockS` は書き換えない）。
  選択・ギズモ・範囲選択・アークの連動・減光はこれで自動的に効く（つながったアークが他のレーンにあると、ロックと同じく動かした時につながりが外れる）。
  **3Dでノーツ系を拾う・動かす処理を足したら `objLockedN`（`objUnder`）を通すこと。**
- 行き先: `clipTrackPlan` の先頭で `editOnlyPlan`（必ず単独編集のレーン。クリップが無ければそのレーンの1小節の空きに新しいクリップ）。貼り付け（`pasteTrackFor`・選んだNLEのクリップ）も同じ。
  **3Dで物を置く経路を足したら、先に `editOnlyRefuse()` を呼ぶ**（単独編集のレーンがロック・ミュート・他のレーンのソロで見えない時は、置かずに showErr で知らせる）。
- 他のレーンの物のクリック（左・Shift・右クリックの削除・配置のブラシのマス）は `editOnlyClickOther`→`showEditOnlyBand`（帯だけ・クリック自体は何もしない）。重なっていれば `objUnder` が単独編集のレーンを先に拾う。
  範囲選択は帯を出さずに外し、数を3Dの隅の表示に少しの間だけ添える（`noteEditOnly`）。隅の表示は毎フレームの `syncEditOnlyUI`（変わった時だけDOMを書く・LIGHTINGでは出さない）。
- ロックとの関係: ロック中のレーンを単独編集にするとロックを外す（`setEditOnly`）。単独編集中にそのレーンをロックするのはでき、その間は置けない（知らせる）。
- 保存は `buildProjectText` の `laneStates.editOnly`（オフならキー無し）。**`projSig` には入れない**＝切り替えただけでは未保存にしない（view と同じ・利用者の決定）。履歴にも積まない。
  レーンの増減では `shiftLocks` がロックと一緒にずらす（Undo の `restoreDomain` も同じ経路）。
- 溝の2段目の見た目（2026-10-20・利用者の要望「文字が小さくて見づらい」）: スイッチと文字を角の丸い帯でひとまとめにし、**帯全体が押せる**
  （`_eoBtns`＝帯の矩形。表示窓に半分隠れていれば見えている所だけ・4px 未満は無し。上は指のカーソルとツールチップ）。大きさ・色は `EO_GUT`。
  同日、利用者の「詰まって見えて字が読みづらい・枠の高さを」で余白を足した: 帯はレーンの上端+21・高さ20・角の丸み6（1段目の L/S/M＝上端+3〜17 との間 4px・帯の下も 4px）、
  中は左の余白5・スイッチ 22×12・文字との間7、文字は 12px・**太字をやめ中くらいの太さ（500）**・字間 0.5px・オフの文字は少し明るい灰色（#b4b4b4）。
  長い訳は 8px まで縮めて帯に収める（今の訳は日英とも 12px のまま入る。`measureText` は字間込み）。色は既存の物だけ: オフ＝L/S/M のオフの灰色の帯、オン＝3Dの帯の
  ［…を単独編集にする］と同じ深緑＋緑の枠。そのため**ノーツのレーンだけ最低の高さを 45px に上げた**（ライトは 34px のまま・下の「NLE のレーンの数」）。
  NLE のキャンバスは UI文字サイズ（zoom）が掛からないので、帯の文字は 80〜150% でも 12px のまま。テストは `nleScreen().eo` の矩形を使う（位置を数字で書かない）。

## NLE のレーンの数（既定・新規作成・開く時・2026-10-20）

- 既定はノーツ1本・ライト3本（`laneDefN()`・`LANE_DEF_L`。利用者の要望: 解析からクリップを作る等で一番上に増えるので少なく始める）。ノーツの本数だけ
  環境設定「ノーツのレーンの本数」（`#laneRatio`・`bsnm_noteLanes`・1〜5・今のプロジェクトにも反映＝`setNoteLanes`）で変えられる。旧設定 `bsnm_laneratio`
  （計6の比率・settings.default.json の初期値が3）は読まない＝初期値の3が残っている利用者も1本から始まる（そのため新しいキーにした）。
- レーンの数（`notesLanes`/`lightLanes`）は全難易度で共通の状態。以前は新規作成（`newProject`→`resetAllState`）で戻しておらず、前のプロジェクトの数を
  持ち越していた。今は `resetAllState` の `resetLanes()` で既定へ戻す。開く時は `applyProject` が `laneCountsOpen(pj)`＝保存した数を **`loadDiff` の前に**入れる
  （記録の無い古いファイルは当時の既定 3:3＝`LANE_OLD_*`。どちらも使っている段＝クリップの track が見える数より少なくはしない。pj=null＝プロジェクト無しは既定）。
- 空きが無ければ一番上にレーンを足して入れる: 3Dで置く（`clipSlotAt`）・MEDIA のドロップ（`mediaDropTrack`）・NLE の貼り付け（`layerPasteFit` の `add`・ゴーストに「＋」）・
  曲データを読み込む（今あるレーンの中だけ探す。以前は上限の10段目まで探し、レーンの外＝見えない段へ入ることがあった）・解析からクリップを作る・自動ライティング。上限 `LANE_MAX` で断る。
  **レーンを足す・消す操作の履歴は全難易度の `'diffs'`**（全難易度のクリップの段がずれる。'node' だと Undo で他の難易度のクリップが1段ずれたまま残る。溝の右クリックの追加/削除・
  環境設定のスライダーも 'diffs' に直した）。
- テストの素材（basic/rich.nlmf）はノーツ3本で保存してあり、多くのテストがその並び（Notes 3 等）を前提にする。`make_fixtures.py` は作り直しても3本になるよう
  `keep_three_note_lanes` で足してから作る。素材無しで始めるテスト（`t.fresh()`）は 1:3。
- **レーンの高さ**（2026-10-20〜ノーツとライトで別・`laneGeom()`・`laneHt(lk)`/`laneVP(lk)` は必ずグループを渡す）: 最低の高さはノーツ 45px（溝の2段目の単独編集の帯が入る
  ＝`EO_GUT` の y+h+pb・`laneMinOf`）・ライト 34px（`LANE_MIN_L`・溝は1段）。合計6本以下は隙間なく埋め、ノーツが最低に届かない時はライトを 34px まで縮めた分をノーツへ回す
  （既定の画面 1600×980・1:3 ＝ノーツ 45・ライト 42.7 でスクロール無し）。それでも入りきらない・7本以上は最低の高さでスクロールし、表示窓は各グループの全部の高さ（本数×高さ）に比例
  （高さが同じなら以前と同じ＝本数に比例）。1600×980・3:3 はノーツの窓 98.5px（上の2本が見え、一番下の Notes 1 は上の約8px）・ライトの窓 74.5px（一番下は約6px）。
  以前（全部 34px・窓は本数に比例）は各グループの一番下が約18px 見えていた。`nleScreen()` は `laneH`＝ノーツ・`laneHL`＝ライトの高さ。テストで一番下のレーンを使う時は
  `nle_helpers.show_lane` でスクロールしてから。クリップの当たり判定・範囲選択は表示窓に見えている所だけ（`clipVisY`。以前は窓の外に隠れた所が隣のグループの上でも当たった）。

## 古い形式のプロジェクトを開く（2026-10-20）

- 受け付ける形: `format` が `nlmf` と旧名の `bslm`・`bsnm`（拡張子 .bslm/.bsnm も開ける）。保存形式 `version:2`（物はタプル・クリップは難易度ごと。原作 0.8 beta
  から今まで）と、`version` の無い v1（物はオブジェクトの形・今の難易度のクリップはトップレベルの `sections`。0.8 beta より前の版。実物は無く、コードのコメントと
  読み込みの処理からの推定）。レーンの数・`laneStates`・`tempoParts`・`view` 等の無いファイルは、それぞれ初期値で開く。
- 今の形はクリップの中身が正で、開く・難易度の切り替え・NLE の操作のたびにクリップから作り直す（`compileLayersToFlat`）。古いファイルにはクリップの外の物
  （フラットにだけある物・クリップの無い難易度）・長さの無いクリップ（v1。音源を読む前の `ensureLens` が4拍にした）・ノーツのクリップの中のライト（ノードの画面の頃）があり、
  そのままでは消えていた（以前はチェーン・アークだけ `loadDiff` で拾い直していた）。v1 は、レーンを詰め直すとフラットの `_tr` がずれ、合わせ直さないライトが保存で消えていた。
- 開く時に `applyProject` がクリップの中へ入れる: `oldAdoptDiffs`（`loadDiff` の前・全難易度・どの版でも）と `oldFixCur`（v1 の今の難易度・トップレベルの
  sections を組んだ後）。その拍を含む同じ種類のクリップへ入れ、無ければ一番下のレーンの空いている所に小節の区切りで新しいクリップを作る。同じ物は二重にしない
  （物ごとに「フラットの数」と「クリップの数」の多い方まで）。v1 は長さの無いクリップを次のクリップの頭まで（最後は中身の最後の小節まで）にし、ノーツのクリップの中の
  ライトをライトのクリップへ移し、フラットをクリップから作り直す。負の拍の物は入れない（今までどおり）。
- 入れる範囲: v1（フラットが正だった頃）はクリップに入っていない物を全部。v2 は**どのクリップの範囲にも無い物だけ**（クリップの無い難易度は全部）。範囲の中なのに
  中身に無い物は、消した物がフラットに残った物として今までどおり戻さない（リンクの子の中身を消した古いファイルで親へ戻ってしまった・`test_old_version_edited_kid`）。
  チェーン・アークだけは以前から `loadDiff` が範囲の中でも拾い直す。
- 今の形で保存したファイルはフラット＝クリップの中身なので何もしない（開き方・保存の中身・書き出しは同じ）。開いた後は未保存にしない（直したのは置き場所だけ）。
- テストは `tests/e2e_project/test_old_formats.py`（見本は rich.nlmf を古い形へ書き換えて作る＝`old_format_helpers.py`）。**保存の形を変えたら、古い形の見本も足すこと。**

## レーンの縦のスクロールバー（左右・2026-10-20）

- 右端の `#sbN`/`#sbL`（▲▼付き）に加え、溝の左端に細い `#sbNL`/`#sbLL`（幅9px・溝の 2〜11px・▲▼無し）。利用者の要望「右にしか無いので縦にスクロール
  できること自体が分かりにくい」。どちらも同じ `laneScrN`/`laneScrL` を `syncLaneSb` が毎フレーム写す＝常に同じ位置。働きも同じ（`LANE_SBS` の4つに同じ
  処理: つまみのドラッグ・溝のクリック＝その位置へ・スクロールバーの上のホイール＝縦に1目盛り≒1レーン）。スクロールできないグループは左右とも隠す。
- そのため溝の部品は左を空けて描く（単独編集の帯 `EO_GUT.x`=13・レーン名 `LANE_LBL_X`=15）。溝の左端（2〜11px）を押すテストはスクロールバーに当たる。
- 縦の位置はキャンバスの上端 `ndcv.offsetTop`＋`laneTopOf`。以前は 50 の決め打ちで、`#nodepane` の padding-top が 78 になった後は右のスクロールバーが
  28px 上（拍番号の帯の所）にずれていた。つまみのドラッグは画面の px を CSS の px へ直してから使う（祖先に zoom が掛かってもずれないように。今は掛かっていない）。

## リンクしたクリップ（2026-10-19）

- データ: クリップに `link`（リンクのid・全難易度で共通）と、親だけ `linkParent:true`。親は1つ（ある難易度のあるクリップ）・子はどの難易度にも置ける。
  **子も中身を実体で持つ**（親の中身のうち親の長さまで＝`linkDerived`）＝保存・書き出し・譜面チェックは無改修で、古い版で開いてもノーツは消えない。
  `encSec` がクリップの項目を丸ごと書くので保存と `projSig` には自動で乗る。処理は editor-app.js の「リンクしたクリップ」の塊、画面の部品（確認の画面・帯）は `js/nle/clip-link.js`。
- 子の作り直し: `syncFlatToSections` は子を飛ばし（3Dから子へは書き戻さない）、最後に `linkSync` が親の中身・名前・色を全難易度の子へ写す。
  中身が変わった子は、今の難易度ならフラットの子の範囲（`_tr`＋拍）を作り直し（3Dのメッシュも）、他の難易度は退避データ（`projDiffs[k]` の sections とフラット）を直す。
  `compileLayersToFlat` も先に `linkSync` を呼ぶ＝NLE の操作・Undo・難易度の切り替えの後も子は親に揃う。子＝親から決まる物なので、親を戻す Undo だけで子も戻る。
  比べるのは `linkSig`（並び順を問わない・`_ENC` の項目と raw の標準外）。子の範囲に紛れ込んだ物（親の中身でない物）は `linkSync` が取り除いて知らせる（下の経路で入れないのが前提）。
- 子は打てない: `objLockedN`/`objLockedL` に `linkRoN`/`linkRoL` を足している（選択・範囲選択・ギズモ・減光が自動で効く）。子を触る・置く・貼る・左端をトリムする・左右反転は
  `linkBandKid`（帯［親へジャンプ］［リンクを解除］）。置き場所は `linkPlaceBlock`（`clipTrackPlan` は子より他のクリップを優先し、子しか無ければ子を返す＝呼ぶ側が帯）。
  ギズモ・貼り付けの追従は `linkMoveBlocked` で子の中へ入れず飛び越えさせない。`extendClipToFit` はリンクしたクリップを削らない（手前まで）。
  **3Dで物を置く・動かす経路を足したら、`linkPlaceBlock`／`linkMoveBlocked` も通すこと**（通さないと子の範囲に入った物が `linkSync` で消える）。
- リンク中は分割（C・分割モード・マーカーでカット）・結合ができない。難易度の全消去は、他の難易度とリンクしているクリップがあれば断る（`linkBlocksClear`）。
  親を消す・解除して2つ以上残れば次の親を選ぶ（`linkTidy`→`linkAskNextParents`。1つしか残らなければリンクは消える）。
- 次の親の画面の［キャンセル］／Esc（2026-10-20・利用者の要望）は、きっかけの操作（クリップの削除・カット・リンクの解除・難易度間コピーで送り先の親が消えた）を
  まるごと取り消す: その操作が積んだ履歴の項目で操作の前へ戻し、項目を履歴から外す（やり直しの列にも積まない＝Ctrl+Shift+Z で復活しない）。やり直しの列・クリップボード（カット）も
  操作の前の物へ戻す。続けて2つ目以降の画面が出ても、どこで押しても全部を取り消す。控えは `linkTxBegin`（履歴を積む直前）→`linkTxMark`（積んだ直後）→`linkAskNextParents(orphans,tx)`。
  **親が消え得る経路を足したら tx を渡すこと**（渡さないとキャンセルが出ず、Esc＝決定の古い形になる）。
- 履歴: リンクの付け外し・名前や色の変更で他の難易度も変わる時は全難易度 `'diffs'`（`linkHist`/`clipHist`）。`'diffs'` は他の難易度のノーツ類のフラットと、
  まだ無かった難易度（`absent`＝戻す時に消す）も持つ。難易度間コピーは常に `'diffs'`（繋がない画面外への転送も Undo 1回で戻る・2026-10-20〜）。
- 開く時: `applyProject` は `_lkHold` で子の作り直しを止め、`loadDiff` の後の `linkSanitize` で、親と中身の違う子（古い版で子を編集した等）・親の無いリンクを外して帯で知らせる。
- 難易度間コピー（`diffCopyAsk`→`diffCopy(…,{link})`）は「親の難易度に繋ぐ」が既定オン（送り元が子ならその親に繋ぐ）。写すのは種類の物だけ: ライティング＝ライトのクリップ
  とライト、ノーツ＝ノーツのクリップとノーツ類、丸ごと＝両方。写さない種類の送り先のクリップ・フラット・リンクには触らない。繋ぐ時は空のクリップも同じく子になる。
  まだ無い難易度は空のタイムライン（`diffBlankStore`・クリップ無し）として扱う（2026-10-20 まで `diffStoreOf` が今の難易度のクリップの並びを中身だけ空にして複製しており、
  まだ開いていない難易度へライトを送るとノーツのクリップ＝解析から作った空のクリップ・リンクの親まで写り、繋がっていなかった。v1.6.0 以前からの作り）。送り元がまだ無い時は退避データを作らない。
  上書きの注意は写す種類の物かクリップ（空も）が送り先にある時。
  クリップのコピーは元の id と難易度を覚え、
  別の難易度で貼る時は毎回「繋ぐ／切る」（`startLayerPaste`）、同じ難易度の中は Ctrl+V＝普通・`nleLinkPaste`（Ctrl+Shift+V）＝リンクして貼り付け。リンクする＝`nleLink`（K）。

## ショートカットと早見表（2026-10-11）

- キーのショートカットは editor-app.js の`ACTIONS`に定義し、keydown では`hit(e,id)`で判定する＝環境設定の「ショートカット編集」で割り当てを変えられる。
- 画面に浮かぶ早見表（`KEYS_COMMON`/`KEYS_NOTE`/`KEYS_LIGHT`/`KEYS_NLE`/`KEYS_NODE`）は、操作の`{id}`を ACTIONS の今のキーに置き換えて出す（`keyText`。割り当てを変えるとすぐ描き直す）。
  **ショートカットを足したら早見表にも足す**（以前は固定の文字で、W・Esc 等が載っておらず、割り当てを変えても古いキーのままだった）。
  訳のキーは`{…}`を含んだままの文字列（例`skk:2個以上 {noteArc} ／ …`）。キー名は設定ファイル（`bsnm_keymap`）由来なので`escHtml`を通す。
- 右下の共通の早見表は3Dビューの高さぎりぎり。行を足すと画面テスト（1600×980）で最後の行が下にはみ出して`崩れ`になる（Escの行を足した時は区切り線を2本減らして収めた）。
- 早見表の上の帯（持ち手）には題名（環境設定「ショートカット表示」の項目名`set.k.*`）を`renderModeKeys`が書く（2026-10-12）。「—」でたたむと本文を消して
  題名とボタンだけの幅の1行に縮む（以前は幅を保ったまま空の帯が残り、何の一覧か分からなかった）。動かした早見表をひらく時は、左端で幅を測ってからペインの中へ押し戻す。
- 各ペインの左上のモード表示（`setModeLabel`）の「［TAB］ 次の画面名」（`.mlNext`）は、クリックでも Tab キーと同じ切り替えをする（2026-10-12）。
  ラベルの他の部分は`pointer-events:none`のまま＝クリックを下の3D/NLEへ通す。`.mlNext`の押下は伝播を止める（下で配置・範囲選択を始めない）。
  NLE/INFO の表示（`updateNodeColLabel`）も言語の読込のたびに作り直す（ツールチップの訳のため）。
- LIGHTINGで3Dの上にマウスがある時の数字キー: 1/2/3＝色を選ぶ（`lightCol1〜3`・①/②/白、クロマ時は左/右/白＝Cパイの先頭3つ）。ここでは数字で難易度を変えない
  （4/5も何もしない・利用者と決めた仕様）。NLE・INFO等の上では今までどおり数字＝難易度切替。

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
- 古いノード画面（song/in/outノードをキャンバスに並べて配線するグラフエディタ）の処理一式（2026-10-05）。`ndView`が常に`'layers'`で
  到達できなかった。同時に、どこからも呼ばれていなかった関数（`addMarker`・`srcNjsOf`・`setLightBehavSmart`・`flipLightColors`等）と、
  常に隠れていたステージ選択（`#pvEnvSel`・`pvFillEnvSel`。原作者の指示で「当面削除」とされていた物）も削除。戻す時は git の履歴から。
  調べ方は、全テストのカバレッジ（`run_tests.py --coverage`）→ 名前の参照をたどって消せる物の範囲を出す → 複数の観点での反証。
- 「曲フォルダ読込」（2026-10-20・利用者の決定＝保守の手間を減らす）。`#loadBtn`（最初の公開から常に `display:none`＝利用者が使えた版は無い）・
  隠れたファイル選択 `#folder`・`afterFolder`、この機能だけが値を入れていた `files`/`handles`/`dirHandle`（と `infoText`/`infoFileName`）と、それを読む所すべて:
  カバーを曲フォルダのファイルから探す（`loadCoverPreview`/`updateCoverThumb`/`buildDefaultGraph`）・`loadDiff` が曲フォルダの .dat を読む分岐・
  保存の「曲フォルダ直下の project.nlmf」と `rotateBakDisk`・書き出し先が無い時の曲フォルダ・旧 `bsnm.meta.json`・まだ読んでいない .dat の難易度の扱い
  （解析からクリップを作るの「未読込」、難易度間の転送の `diffUnloaded`/`diffCopyRefuse`）。どれも `files` は常に空・`dirHandle` は常に null で、
  今の操作では通らなかった（開く・保存・書き出し・難易度の切り替えは別の道＝`projFileHandle`・`outDirHandle`/ダウンロード・空の新しい難易度）。
  古い版で曲フォルダに保存された project.nlmf は「開く…」で今までどおり開ける。`applyProject(null)`（プロジェクト無し）と `buildDefaultGraph` は、
  テストが新規の代わりに使うので残した。戻す時は git の履歴から。

## 古いノード画面の名残り（消さないもの）

- `songNode`/`graphEdges`/`extraNodes`/`graphIO`/`altIns`/`altOuts`/`altSongs`/`activeUids`/`cutSet`は現役のデータ（保存ファイル・
  履歴に入る。`applyInfoGraph()`がINFOノードエディタからここへ写す）。`js/chart/graph-legacy.js`も、レイヤー画面・保存・読込が使う
  `ensureEdges`/`newDefaultGraph`/`sigConnected`/`sigPath`を持つので消さない。
- `loadLineDiff`/`fillDiffSelectFromInfo`は、`restoreLineAssets()`が古い版の残したIndexedDBの`lineDirs`を読む経路から呼ばれ得るので残した
  （今の版は`lineDirs`を書かない）。`ndFromScreen`/`ndCam`はMEDIAのドロップが使う（今は常に恒等変換）。

## その他

- gitはこのプロジェクトに元々入っていなかった（2026-09-20にこちらで`git init`した）。
  配布用exeフォルダ（`NLM-app/`、ビルド成果物の`dist/`・`build/`・`.venv/`・`.venv-build/`）は
  `.gitignore`済み＝ソース以外はバージョン管理していない。

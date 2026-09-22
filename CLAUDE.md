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

## ビルド・実行

- 開発用venv: `.venv-build/`（`.gitignore`済み）。`pip install pywebview pythonnet pyinstaller`。
  `.venv/` は `tools/` のテンポ解析用（librosa）で、ビルドには使わない。
- ビルド: `.venv-build/Scripts/python.exe -m PyInstaller --noconfirm --clean nlm.spec` →
  `dist/NonLinearMapper/` にonedir出力（`NonLinearMapper.exe` + `_internal/`）。
- **配布用exeへの反映方法**: 配布フォルダ（例: `NLM-app/`）の`NonLinearMapper.exe`と
  `_internal/`だけを新ビルドで上書きする。**`asset/`・`config/`・`lang/`は上書きしない**
  （exeの隣に生成されるユーザーデータ。設定・クリップが入っている。`app.py`の`_data_root()`参照）。
  上書き前に古い`exe`+`_internal`をバックアップしておくと安全（このリポジトリはgit管理外）。
- `nlm.spec`の`console=True`と`app.py`の`webview.start(debug=True)`は診断用フラグ。
  普段は両方無効(`console=False`・`debug`無し)でビルドすること。デバッグしたい時だけ一時的に有効化。
- **ffmpeg依存**: song.egg変換(後述)にはPATH上の`ffmpeg`が必要。`winget install Gyan.FFmpeg`で導入可能。
  無い場合はエラーメッセージでインストール手順を案内する仕様（無言で失敗はしない）。
- **配布zipのMark of the Web対策**: `app.py`の`_unblock_dist_folder()`（`main()`の先頭、
  `import webview`より前で呼ぶ）が、exeと同じフォルダ配下の全ファイルからZone.Identifier
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

## song.egg 書き出し（変換・キャッシュ）

- 元の音源がOGGならバイトコピー、それ以外（mp3/wav/flac等）はffmpegで`libvorbis`へ変換。
- 変換は`serve.py`の`/__convert/toOgg`（POST、生バイナリボディ、`?ext=xxx&leadInMs=xxx`）。
  ffmpeg呼び出しには`creationflags=CREATE_NO_WINDOW`必須（無いと一瞬コンソール窓が出る）。
- 出力先フォルダに`.nlm-egg.json`という小さなマーカーファイルを置いて、音源のsize/mtime/leadInMsが
  前回と同一なら再変換をスキップする（ffmpeg起動・大きい音声ファイルの再書き込みを避ける）。
- 書き出しパネルの「song.eggを強制再変換」チェックボックスでキャッシュを無視して強制再生成できる
  （初期化・やり直し用）。

## 削除済み機能（意図的）

- 「最近使ったファイル」機能（`addRecent`/`fillRecentMenu`/`openRecentHandle`）— 上記のIndexedDB
  クラッシュの直接原因だったため、メニュー・JS・CSS・翻訳ファイルから完全に削除した。
  同じ発想の機能を作る場合は、必ずネイティブパス方式（上記4番）を使うこと。

## 触らなくていい・生きていないコード

- `_ndWidgets`（1684行目付近で宣言、以降どこからも`.push`されていない）や、`nodeGeomOf('song')`等が
  想定しているらしい「song/in/outノードをキャンバスに描画する古いグラフエディタ」は、現在の
  `nodeColMode`（`'nle'`と`'info'`の2値のみ）からは到達できないように見える。`songNode`/`graphEdges`/
  `extraNodes`自体は`applyInfoGraph()`経由で今も現役（INFOノードエディタのミラー先）だが、
  この古い方のキャンバス描画UIは死んでいる可能性が高い。触る前に本当に呼ばれているか要確認。

## その他

- gitはこのプロジェクトに元々入っていなかった（2026-09-20にこちらで`git init`した）。
  配布用exeフォルダ（`NLM-app/`、ビルド成果物の`dist/`・`build/`・`.venv/`・`.venv-build/`）は
  `.gitignore`済み＝ソース以外はバージョン管理していない。

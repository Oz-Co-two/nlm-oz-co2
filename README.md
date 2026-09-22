# Non-Linear Mapper (NLM) — Oz-Co2版

Beat Saber の譜面エディタです。デスクトップアプリ（Windows / pywebview + WebView2）として動作します。

## これは何か

このリポジトリは、[helba](https://helba.flashhub.net/nlm/) さんが開発された **Non-Linear Mapper 0.8 beta**
の派生版（フォーク）です。操作方法・パネル構成などのドキュメントは原作サイトが詳しいので、
そちらを参照してください。

- **原作 / 公式ドキュメント**: https://helba.flashhub.net/nlm/
- **リファレンスマニュアル**: https://helba.flashhub.net/nlm/manual/
- **原作の修正履歴**: https://helba.flashhub.net/nlm/changelog.html

note のコメント欄にて helba さんご本人から、本フォークとしての公開・改変・再配布について
快諾をいただいています。

## このフォークでの変更点

原作からの主な差分です。基本操作は上記の原作マニュアルを参照してください。

### 新機能

- **スペクトログラム（周波数）表示を追加**
  曲読込時に音声全体を解析し、2D エディタの波形の下、および 3D ビューのノーツ配置空間の
  外側に、周波数の強弱を色（黒→紫→赤→橙→白）で表した帯を表示します。曲のサビや静かな
  部分がひと目で分かります。
- **テンポパート機能（曲中のテンポ変化に対応）**
  一定テンポ前提だった譜面に、拍単位でBPMが変わる「テンポパート」を追加できるようになり
  ました。Beat Saber 本体側でも実際にテンポが変わるよう、V3 譜面形式の bpmEvents として
  書き出します。既存BPM測定機能を使った「全パート自動判定」ボタンもあります。
- **無音追加（ms）機能**
  曲の先頭に無音を追加できるUIを追加。エディタ内プレビューに反映されるほか、書き出し時は
  ffmpeg で song.egg の音声データ自体に無音を物理的に焼き込みます。
- **song.egg 変換のキャッシュ**
  音源が前回書き出しと同一なら変換をスキップするようになり、繰り返しの書き出しが速くなり
  ました。強制的に再変換するチェックボックスもあります。
- **出力フォルダ／カバー画像のネイティブ接続化**
  ブラウザの File System Access API はハンドルがアプリ再起動で失効する制約があるため、
  実際の絶対パスをプロジェクトファイルに保存し、次回開いた際にダイアログなしで自動的に
  再接続するようにしました（「再接続」ボタンでの一括やり直しも可能）。
- 「編集モード」を「カメラ固定モード」に改名し、ビューを少し引いて見やすく調整
- 3D ビューのホイール操作（時間移動）を反転させる設定を追加
- 実装済みだったのにショートカット一覧に載っていなかった操作（分割モード R、4拍イージング
  Shift+Ctrl+矢印、チェーン作成 C）を一覧に追加表示
- **配置モード中でも、選択したノーツを Alt+ホイール／F キーで編集可能に**
  これまでは配置モード中、Alt+ホイール（向き変更）と F キー（色反転）は常にブラシ側にしか
  効きませんでした。カーソル直下が選択中のノーツであれば、その選択全体へまとめて適用される
  ようにしました（それ以外の場合は従来通りブラシのみ変更します）。

### 不具合修正

- **保存直後に画面が白くフリーズ／アプリがクラッシュする不具合を修正**
  ファイルの参照情報（FileSystemHandle）をブラウザの IndexedDB に直接保存する処理が、
  WebView2 埋め込み環境でネイティブクラッシュを引き起こしていたのが原因でした。
  該当処理（「最近使ったファイル」機能など）を廃止し、代わりに pywebview のネイティブ
  ファイルダイアログ経由で絶対パスを扱う方式に置き換えています。
- Alt キーでノーツの向きを変えた後、移動操作が反応しなくなる不具合を修正（Windows が Alt を
  特殊キー扱いすることによる誤認識が原因）

### 開発用ツール（`tools/`）

一般利用者向けではありませんが、開発時に使うスクリプトを同梱しています。

- テンポ・拍グリッド解析ツール一式（MP3 のテンポ変化検出、NLM に設定する BPM／無音追加の
  逆算）。詳細は [tools/README.md](tools/README.md) を参照
- ビルド＆配布フォルダ反映スクリプト（`build_and_deploy.py`）
- JS 構文・初期ロードチェックツール（`check_js.py`、Node.js 不使用のためヘッドレス Edge で検証）

## ライセンス

**GNU General Public License v3.0 (GPLv3)** で公開しています。詳細は [LICENSE](LICENSE) を
参照してください。

MIT ではなく GPLv3 を選んだ理由は、3D プレビュー描画エンジン（`preview-v4/`）が、GPLv3 で
公開されている Beat Saber 譜面ビューア [ArcViewer](https://github.com/AllPoland/ArcViewer/)
（AllPoland 作）の移植（コードおよび環境シーンデータ）を含むためです。GPLv3 はコピーレフト
ライセンスのため、この部分を含むプロジェクト全体を GPLv3 としています。

同梱する第三者コンポーネント（three.js、pywebview 等）のライセンス全文は
[THIRD_PARTY_NOTICES.txt](THIRD_PARTY_NOTICES.txt) を参照してください。

- 原作者: [helba](https://helba.flashhub.net/nlm/)
- 本フォークでの改良: Oz-Co2

## ビルド・実行

開発メモ（[CLAUDE.md](CLAUDE.md)）にビルド手順や内部実装の詳細をまとめています。要点のみ:

```bash
# 開発用venv
python -m venv .venv-build
.venv-build/Scripts/python -m pip install pywebview pythonnet pyinstaller

# ビルド
.venv-build/Scripts/python -m PyInstaller --noconfirm --clean nlm.spec
# → dist/NonLinearMapper/ に NonLinearMapper.exe + _internal/ が出力されます
```

開発中の動作確認は `python serve.py` でローカルサーバーを起動し、ブラウザで
`http://127.0.0.1:8138/editor.html` を開く方法が手早く確認できます（DevTools が使えます）。

### ffmpeg（song.egg 変換に必要）

song.egg への書き出し（OGG 以外の音源の変換、無音追加の焼き込み）には、PATH 上に
`ffmpeg` が必要です。**自動ではインストールされない**ため、事前に導入しておいてください。

```bash
winget install Gyan.FFmpeg
```

未インストールのまま書き出すと、エラーメッセージでインストール方法が案内されます。

## トラブルシューティング

### 起動時に "Failed to resolve Python.Runtime.Loader.Initialize from ...\Python.Runtime.dll" と出る

配布 ZIP を Web ブラウザでダウンロードすると、Windows が「インターネットから来たファイル」の
印（Mark of the Web）を付けます。これがエクスプローラーで展開した後の DLL にも引き継がれ、
.NET ランタイムが DLL のロードを拒否してしまうことがあります。

**起動時に自動でこの印を取り除く処理を入れているため、通常は発生しません。** それでも直らない
場合は、以下の手順で手動解除してください。

1. ダウンロードした ZIP を右クリックし「プロパティ」を開く
2. 「全般」タブの一番下、「許可する（ブロック解除）」にチェックを入れて OK
3. 解除した ZIP を再度展開し直してから起動する

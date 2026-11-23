# BL のリプレイアプリの出典（写した物の記録）

このフォルダは BeatLeader の Web のリプレイの見え方（BeatSaber-Web-Replays・https://github.com/BeatLeader/BeatSaber-Web-Replays ・MIT・
Copyright © 2018 Supermedium）の組み立て済みの物の写し。NLM の左上の窓の「REPLAY」が、遊んだリプレイと遊んだ時の譜面の zip を
NLM の viewer のサーバー（serve.py・本体と別のオリジン＝`http://localhost:<本体の番号＋20>`）から渡して開く
（`/blreplay/index.html?link=<.bsor の場所>&mapLink=<譜面の zip の場所>`）。こちらで書いたのはこのファイルだけ。
窓どうしの伝言の受け手とホイールのズームは写した物の外（`replay-viewer/bridge.js`）にあり、viewer のサーバーが index.html を出す時だけ
`</body>` の前に script を足す＝写した物には手を入れない。

## どこから写したか

- 同じ作者の Auto Note Plotter（nlm-automap・GPLv3）が写した物（その `app/static/blreplay/`）を、そのまま写した（2026-11-22）。
  ANP の写しは下の「写し方」で BL の公開ページと GitHub から取った物で、`MANIFEST.json` もそのまま（ファイルごとの SHA-256 が ANP の写しと同じ）。
- 元の版: GitHub のコミット `cb3e9b81776d41cfdc25fa410ce4fdd9811662ed`（2026-11-09「Fixed song resume offset on Safari」）・公開ページの本体
  `build/build.1794234981.js`（ANP が 2026-11-12 に写した）。

## 写し方

- `tools/blreplay_fetch.py` が写す（標準ライブラリだけ・npm を使わない。ANP の同じ名前の道具の写す先を NLM の場所にした物）。
  index.html・`build/`・`vendor/aframe-master.min.js` は BL の公開ページ https://replay.beatleader.com/ から（作るには npm が要る＝NLM では使わない）、
  素材（`assets/`）は GitHub の決めた版のコミットの一覧の物を公開ページから、無ければ GitHub の同じ版から。`vendor/` の小さな部品と LICENSE は GitHub の同じ版から。
- Font Awesome Free 6.4.0（ページは CDN から読む）も `fontawesome/` に写した＝開く時にネットへ出るのは BeatLeader の API（プレイヤーの公開
  プロフィール）だけ。
- 写さない物: `assets/test.zip`・`assets/raw/`（元の .blend）・`assets/webfonts/`（Font Awesome 5・使わない）・`vendor/aframe-master.js`（.min を使う）と .map。
- `MANIFEST.json` に写した日・版・ファイルごとの SHA-256。`tools/blreplay_fetch.py --check` で写した物が変わっていないか（と一覧に無い物が無いか）を確かめる。
  git は行の終わりを変えない（`.gitattributes` の `replay-viewer/blreplay/** -text`）。

## こちらで変えた所（PATCHES・ANP と同じ・写し直す時に道具が当て直す。当たらなければ止まる）

1. `index.html` の `"/assets/img/firefoxautoplay.jpg"` → `"assets/img/firefoxautoplay.jpg"`（viewer では /blreplay/ の下に置く）
2. `build/build.*.js` の `"/assets/sounds/silence.mp3"` → `"assets/sounds/silence.mp3"`（同じ）
3. `index.html` の Font Awesome の CSS を CDN から写した物（`fontawesome/css/all.css`）に

## 動き方で知っておくこと

- `mapLink` があると、zip-loader は BeatSaver に問い合わせずに zip を読む。遊んだ譜面の hash と zip の中身が違っても止まらない。
- `link` の .bsor はリプレイアプリが XHR で読む（同じ viewer のサーバー・使い捨ての鍵の場所 /blr/<鍵>/…）。プレイヤーの名前とアイコンは
  リプレイの頭のプレイヤーの番号で BeatLeader の API から読む（ネットが無ければ出ないだけ）。
- 設定（視点・音量など）はリプレイアプリがブラウザの覚え（viewer のオリジンごと）に持つ。
- `replay-viewer/bridge.js` はリプレイアプリの中の部品（a-scene の song-controls・song・再生のボタン・`#mainCamera`・`#povCamera` と
  A-Frame の look-controls・camera）に頼る。**写し直したら bridge.js の冒頭に書いた「版が変わった時に見直す所」を確かめる。**

## 写し直す手順

1. `.venv-build/Scripts/python.exe -I tools/blreplay_fetch.py`（前の物は丸ごと置き換える・このファイルは残す）
2. 写した日・版をこのファイルに書き直す（`MANIFEST.json` の commit・fetched）。ANP の写しと揃えるなら、ANP でも写し直して `--check` を比べる。
3. `THIRD_PARTY_NOTICES.txt` の BL のリプレイアプリの節（版・中の部品）を見直す。
4. REPLAY の窓で開けるか・伝言（hello・seek・play・pause・time）とホイールのズームが動くかを確かめる。

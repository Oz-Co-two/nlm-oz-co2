// REPLAY の窓の中の、伝言の受け手とホイールのズーム（BL のリプレイアプリの中で動く・2026-11-22）。
// 元は同じ作者の Auto Note Plotter（nlm-automap・GPLv3）の static/blrembed/bridge.js（伝言の受け手）。伝言の名前を nlm:'blr' にし、ズームを足した。
// NLM の viewer のサーバー（serve.py・本体と別のオリジン＝http://localhost:<番号>）は BL のリプレイアプリ（replay-viewer/blreplay/）を出し、
// index.html を出す時だけ </body> の前にこの <script> を足す（写した物には手を入れない）。data-parent＝埋め込んでよい NLM の画面のオリジン（空白で区切る）。
//
// 伝言（窓どうしの postMessage だけ・相手の窓とオリジンを確かめる・送る先のオリジンも決める＝'*' にしない）:
//   NLM → ここ: {nlm:'blr', cmd:'hello'}（つながったか）・{cmd:'seek', t}（曲の秒＝song.egg の秒）・{cmd:'play'}・{cmd:'pause'}
//   ここ → NLM: {nlm:'blr', ev:'key', key, code, ctrl, shift, alt, repeat}（窓の中で押した Tab・Ctrl の組み合わせ＝NLM のショートカットへ）・{nlm:'blr', ev:'hi'}・{ev:'ready', dur}（曲を読めた）・{ev:'time', t, playing, speed, at}（時刻か再生中かが変わるたび＝毎コマ・
//   at＝時刻を読んだ時の壁の時計（performance.timeOrigin＋now・ミリ秒）＝NLM が届くまでの遅れの分を先読みする）・{ev:'zoom', level}（倍率が変わった時・1＝標準）
// BL のリプレイアプリの中の部品（a-scene の song-controls・song）を使う: 時刻＝song.getCurrentTime()・動かす＝song-controls の seek
// （アプリの帯の上の時刻の棒と同じ）・再生中＝再生のボタン（#controlsPause）に play の印が無い・再生と停止＝そのボタンを押す（終わった後は頭から）。
// 開く位置（URL の time）の動かし直しを止める（ANP で 2026-11-15 に見つけた「スローを有効化して再生したら画面がずれた」）: BL のリプレイアプリは time を
// 受けると、最初に音が鳴り始めた（songstartaudio）0.1 秒後に一度だけ song-controls の seek(time, false) でその位置へ戻す。埋め込みでは
// 開いた後に NLM の位置へ動かすので、最初の ▶ で開いた時の位置へ引き戻された。その 1 回だけを飛ばす
// （ノーツを作り直さない seek＝第 2 引数 false を呼ぶのは BL のリプレイアプリの中でここだけ・2026-11-12 に写した版で確かめた）。
//
// ホイールのズーム（2026-11-22 利用者「ズームはホイールだけ・マウスの指す所へ寄る・離れる」）: BL のリプレイアプリはホイールを時刻の棒・
// 音量や速さのつまみでだけ使い、3D の絵の上では何もしない。そこで 3D の絵（a-scene の canvas）の上のホイールだけを受ける（時刻の棒・設定の画面
// などの上のホイールは canvas に届かない＝今までどおり）。1 目盛りで 1.15 倍・倍率は 1〜8 倍・ページを開いたら 1 倍（覚えない）。
// 「ホイールでズーム」の重ねた表示は NLM の画面が出す（ここは何も描かない）。
//   - 標準の視点（#mainCamera・初めは 0, 1.75, 2.0・look-controls のドラッグで向きが変わる・wasd-controls で動く）: カメラをマウスの画素を
//     通る光線に沿って動かす（向きは変えない）＝その光線の上の物は画面の同じ画素に残る（地図のズームと同じ）。寄る距離は、その光線と
//     プレイヤーの面（頭＝#head を通る縦の面・カメラの向きに向かい合う＝標準の視点では z=0 付近の面）との交点までの距離 D から決める:
//     倍率 L→L2 で D×(1−L/L2) 進む（交点までの距離が D×L/L2 になる＝そこにある物が L2/L 倍の大きさに見える）。交点が無い（真上から見る・
//     面を通り過ぎた・面とほぼ平行）時は「1 倍の時に 2m 先」とみなす（D＝2m÷L）。1 倍まで戻したら、寄り始める前の位置へぴったり戻す。
//     BL の左・中・右の視点のボタン・WASD・カメラの戻す（Restore）など、ほかから位置が変わったら倍率を 1 として数え直す
//     （最後にここで置いた位置と今の位置を毎コマ比べる）。向き（ドラッグ）が変わっても倍率は数え直さない。
//   - 目線（FPV・#povCamera・頭の動きに付いて毎コマ動く）: 位置は動かせないので視野を狭めて寄る。three.js のカメラの view（setViewOffset と同じ形・
//     全体を 1×1 とした窓）で、全体の視野の中の 1/L の大きさの窓を描く＝視野角が 1/L に狭まった絵。窓の位置はマウスの指す所が同じ画素に
//     残るように決める（全体の視野の外へは出さない）。1 倍で元の視野（view を止める）。BL の設定の視野角（fov）は変えない＝設定のつまみは
//     そのまま効き、倍率もそのまま。FPV に入った・やめた時（povchanged）は 1 倍に戻す。
//   - ほかのカメラ（正射影の後ろ・右・上）を全画面にしている時は、標準の視点・目線が隅の小さな枠に描かれる＝ホイールを受けない（今までどおり）。
//     正射影の小さな枠を出している時に、その枠の上でホイールを回すと、枠の下に隠れた標準の視点が寄る（枠の形は見ていない）。
//
// BL のリプレイアプリの版が変わった時（tools/blreplay_fetch.py で写し直した時）に見直す所:
//   ① a-scene の song-controls の seek(t, clearBeats)・song.getCurrentTime()/getDuration()/speed/source・#controlsPause の play の印
//   ② 開く位置への動かし直し（seek(time, false) を呼ぶのが songstartaudio の後の 1 回だけか）
//   ③ #mainCamera（.mainCamera）・#povCamera（.povCamera）・#head（.headset）の id と、look-controls が毎コマ向きだけを決める（位置は触らない）こと、
//      camera-mover の左・中・右・Restore が位置を直接書くこと（＝ほかから動いたと分かる）、povchanged の知らせ
//   ④ 3D の canvas（#main-canvas・A-Frame がそこに描く）の上でホイールを使う部品が足されていないか（今は時刻の棒・つまみの wheel だけ・
//      OrbitControls は組み込まれているが使っていない・look-controls はつまむ操作（タッチ）でだけ前後に動く）
//   ⑤ A-Frame の camera の data.fullscreen（正射影のカメラを全画面にした時に false）と、three.js の PerspectiveCamera の view（r95）
(function () {
  'use strict';
  if (window.parent === window) return;   // 別のタブで開いた時は何もしない
  const me = document.currentScript;
  const ALLOW = String((me && me.dataset.parent) || '').split(/\s+/).filter(Boolean);
  const PT = (() => { const v = new URLSearchParams(location.search).get('time'); return v && isFinite(v) ? parseFloat(v) / 1e3 : null; })();
  let PO = null;          // つながった NLM の画面のオリジン（最初の正しい伝言で決める）
  let ready = false, lastT = null, lastP = null, lastSp = null, want = null;   // want＝読めるまで待たせた seek
  let skipPT = PT != null;   // 開く位置への動かし直し（1 回だけ）をまだ飛ばしていない
  const send = m => { if (PO) window.parent.postMessage(Object.assign({nlm: 'blr'}, m), PO); };

  // 窓の中を押した後のキー（2026-11-22）: 押した後は入力がこの窓へ来るので、NLM の Tab（左上の窓の切り替え）と Ctrl の組み合わせ（保存・
  // 取り消し…）が効かなくなる。この2種類だけ NLM へ渡す＝{ev:'key', key, code, ctrl, shift, alt}（BL のリプレイアプリには渡さない）。
  // Space・矢印などは BL のリプレイアプリが受ける（再生・位置の変化は同期で NLM にも付いてくる）
  window.addEventListener('keydown', e => {
    if (!PO || e.isComposing) return;
    const tab = e.key === 'Tab' && !e.ctrlKey && !e.altKey && !e.metaKey;
    const ctrl = (e.ctrlKey || e.metaKey) && !['Control', 'Shift', 'Alt', 'Meta'].includes(e.key);
    if (!tab && !ctrl) return;
    e.preventDefault(); e.stopImmediatePropagation();
    send({ev: 'key', key: String(e.key).slice(0, 20), code: String(e.code).slice(0, 20), ctrl: !!(e.ctrlKey || e.metaKey), shift: !!e.shiftKey, alt: !!e.altKey, repeat: !!e.repeat});
  }, true);
  const scene = () => document.querySelector('a-scene');
  const ctl = () => { const s = scene(); return s && s.components ? s.components['song-controls'] : null; };
  const loaded = c => !!(c && c.song && c.song.source && c.song.getDuration() > 0);
  const btn = () => document.getElementById('controlsPause');
  const playing = () => { const b = btn(); return !!b && !b.classList.contains('play'); };
  const wall = () => performance.timeOrigin + performance.now();

  function guard(c) {   // song-controls の seek を包む（開く位置への動かし直しだけ飛ばす・ほかはそのまま）
    if (!c || c.__nlmGuard) return;
    c.__nlmGuard = true;
    const orig = c.seek;
    c.seek = function (t, clearBeats) {
      if (skipPT && clearBeats === false && Math.abs(t - PT) < 1e-6) { skipPT = false; return; }
      return orig.apply(this, arguments);
    };
  }
  function seek(t) {
    const c = ctl();
    if (!loaded(c)) { want = t; return; }
    want = null;
    const d = c.song.getDuration();
    c.seek(Math.max(0, Math.min(d - 0.01, t)));
  }
  function setPlay(on) {
    const b = btn();
    if (b && loaded(ctl()) && on !== playing()) b.click();
  }

  // ---- ホイールのズーム ----
  const STEP = 1.15, MAX = 8, FALLBACK = 2;   // 1 目盛りの倍率・上限・交点が無い時の 1 倍での距離（m）
  const zm = {level: 1, start: null, last: null};   // 標準の視点: start＝寄り始める前の位置・last＝最後にここで置いた位置（どちらも親の座標）
  const zp = {level: 1, ox: 0, oy: 0, w: 1};         // 目線: 全体の視野を 1×1 とした窓の左上（ox, oy）と大きさ（w＝1/level）
  let zSent = 1, wheelOn = null, povHooked = null;
  const T3 = () => (window.AFRAME && window.AFRAME.THREE) || window.THREE;
  const camEl = id => document.getElementById(id);
  const camOf = id => { const el = camEl(id); return el && el.getObject3D ? el.getObject3D('camera') : null; };

  function active() {   // 今描いているカメラ → 'main'・'pov'・null（まだ無い・正射影のカメラを全画面にしている）
    const s = scene();
    if (!s || !s.camera) return null;
    for (const [k, id] of [['main', 'mainCamera'], ['pov', 'povCamera']]) {
      if (camOf(id) !== s.camera) continue;
      const c = camEl(id).components && camEl(id).components.camera;
      return c && c.data && c.data.fullscreen === false ? null : k;
    }
    return null;
  }
  function mainSync() {   // 標準の視点がほかから動いた（左・中・右・WASD・Restore）→ 1 倍として数え直す
    const el = camEl('mainCamera');
    if (zm.last && el && el.object3D && !el.object3D.position.equals(zm.last)) { zm.level = 1; zm.start = zm.last = null; }
  }
  function povSync() {   // 目線の窓がほかから変わった・止められた → 1 倍として数え直す
    if (zp.level === 1) return;
    const cam = camOf('povCamera'), v = cam && cam.view;
    if (!v || !v.enabled || v.width !== zp.w || v.offsetX !== zp.ox || v.offsetY !== zp.oy) { zp.level = 1; zp.ox = zp.oy = 0; zp.w = 1; }
  }
  function povReset() {
    const cam = camOf('povCamera');
    if (zp.level !== 1 && cam && cam.view && cam.view.enabled) { cam.view.enabled = false; cam.updateProjectionMatrix(); }
    zp.level = 1; zp.ox = zp.oy = 0; zp.w = 1;
  }
  function nextLevel(L, n) {   // n 目盛り（正＝離れる）回した後の倍率。1 に近ければ 1 へ（戻した時にぴったり 1 倍にする）
    let v = L * Math.pow(STEP, -n);
    if (v < 1 + 1e-3) v = 1;
    return Math.min(MAX, v);
  }
  function planeDist(T, cam, p0, d) {   // 光線（p0 から d の向き）とプレイヤーの面との交点までの距離（無ければ 0）
    const f = new T.Vector3(0, 0, 0.5).unproject(cam).sub(p0);   // カメラの向き（画面の真ん中を通る光線）
    const all = f.length();
    f.y = 0;   // 縦の面（向きの水平の成分を面の向きにする）
    if (!(all > 0) || f.length() < 0.2 * all) return 0;   // ほぼ真上・真下を向いている＝縦の面と向かい合わない
    f.normalize();
    const den = d.dot(f);
    if (den < 0.05) return 0;   // 面とほぼ平行・面から離れる向き
    const hp = new T.Vector3();
    const h = camEl('head');
    if (h && h.object3D) h.object3D.getWorldPosition(hp);
    const t = hp.sub(p0).dot(f) / den;
    return t > 0.02 && t < 60 ? t : 0;
  }
  function zoomMain(n, u, v) {
    const T = T3(), el = camEl('mainCamera'), cam = camOf('mainCamera');
    if (!T || !el || !cam) return;
    const o = el.object3D;
    mainSync();
    const L = zm.level, L2 = nextLevel(L, n);
    if (L2 === L) return;
    if (L2 === 1) { o.position.copy(zm.start); o.updateMatrixWorld(true); zm.level = 1; zm.start = zm.last = null; return; }
    if (L === 1) zm.start = o.position.clone();
    o.updateMatrixWorld(true);   // 同じコマの中で続けて回した時も今の位置から測る
    const p0 = new T.Vector3().setFromMatrixPosition(cam.matrixWorld);
    const d = new T.Vector3(u * 2 - 1, 1 - v * 2, 0.5).unproject(cam).sub(p0).normalize();   // マウスの画素を通る光線
    const D = planeDist(T, cam, p0, d) || FALLBACK / L;
    const ew = new T.Vector3().setFromMatrixPosition(o.matrixWorld).addScaledVector(d, D * (1 - L / L2));
    o.position.copy(o.parent ? o.parent.worldToLocal(ew) : ew);
    o.updateMatrixWorld(true);
    zm.level = L2; zm.last = o.position.clone();
  }
  function zoomPov(n, u, v) {
    const cam = camOf('povCamera');
    if (!cam) return;
    povSync();
    const L = zp.level, L2 = nextLevel(L, n);
    if (L2 === L) return;
    if (L2 === 1) { povReset(); return; }
    const s = 1 / L, s2 = 1 / L2, cl = x => Math.max(0, Math.min(1 - s2, x));
    const fx = zp.ox + u * s, fy = zp.oy + v * s;   // 全体の視野の中でマウスの指す所
    zp.ox = cl(fx - u * s2); zp.oy = cl(fy - v * s2); zp.w = s2; zp.level = L2;
    cam.view = Object.assign(cam.view || {}, {enabled: true, fullWidth: 1, fullHeight: 1, offsetX: zp.ox, offsetY: zp.oy, width: s2, height: s2});
    cam.updateProjectionMatrix();
  }
  function zoomNow() { const k = active(); return k === 'pov' ? zp.level : zm.level; }
  function report() {   // 今描いているカメラの倍率が NLM に知らせた物と違えば知らせる
    const lv = Math.round(zoomNow() * 1e4) / 1e4;
    if (PO && lv !== zSent) { zSent = lv; send({ev: 'zoom', level: lv}); }
  }
  function onWheel(e) {
    const k = active();
    if (!k) return;
    e.preventDefault();
    const n = Math.max(-5, Math.min(5, e.deltaY * (e.deltaMode === 1 ? 1 / 3 : e.deltaMode === 2 ? 1 : 1 / 100)));   // 目盛りの数（1 目盛り＝100px・3 行）
    if (!n) return;
    const r = e.currentTarget.getBoundingClientRect();
    if (!r.width || !r.height) return;
    const u = (e.clientX - r.left) / r.width, v = (e.clientY - r.top) / r.height;
    if (k === 'main') zoomMain(n, u, v); else zoomPov(n, u, v);
    report();
  }
  function hookZoom() {   // 3D の canvas ができたらホイールを受ける・FPV の切り替えを聞く
    const s = scene(), cv = (s && s.canvas) || document.getElementById('main-canvas');   // BL の A-Frame は #main-canvas に描く
    if (cv && wheelOn !== cv) { cv.addEventListener('wheel', onWheel, {passive: false}); wheelOn = cv; }
    if (s && povHooked !== s && s.addEventListener) { s.addEventListener('povchanged', povReset); povHooked = s; }
  }

  window.addEventListener('message', e => {
    if (e.source !== window.parent || !ALLOW.includes(e.origin)) return;
    const d = e.data;
    if (!d || d.nlm !== 'blr') return;
    PO = e.origin;
    if (d.cmd === 'hello') {
      send({ev: 'hi'});
      if (ready) send({ev: 'ready', dur: ctl().song.getDuration()});
      lastT = null; zSent = 1; report();   // つないだ時は NLM は 1 倍とみなす＝違えば知らせ直す
      return;
    }
    if (d.cmd === 'seek' && isFinite(d.t)) seek(+d.t);
    else if (d.cmd === 'play') setPlay(true);
    else if (d.cmd === 'pause') setPlay(false);
  });

  function tick() {
    const c = ctl();
    guard(c);
    hookZoom();
    mainSync(); povSync(); report();
    if (PO && loaded(c)) {
      if (!ready) { ready = true; send({ev: 'ready', dur: c.song.getDuration()}); }
      if (want != null) seek(want);
      const t = c.song.getCurrentTime(), p = playing(), sp = c.song.speed;
      if (lastT == null || Math.abs(t - lastT) > 1e-4 || p !== lastP || sp !== lastSp) {
        send({ev: 'time', t, playing: p, speed: sp, at: wall()});
        lastT = t; lastP = p; lastSp = sp;
      }
    }
    requestAnimationFrame(tick);
  }
  requestAnimationFrame(tick);
})();

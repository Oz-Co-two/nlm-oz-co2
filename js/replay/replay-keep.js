// 書き出しの控え（REPLAY の窓・2026-11-22）: 書き出した譜面（Info.dat・難易度の .dat・カバー）と song.egg を、ローカルのサーバーに控えてもらう
// （serve.py の /__replay/keep・/__replay/keepEgg）。Beat Saber で遊んだリプレイの譜面の hash がこの控えと同じなら、REPLAY の窓で
// 遊んだ時の譜面のまま再生できる（BeatSaver に無い譜面でも・遊んだ後に編集し直しても）。
//
// - 読むのは書き出し先のフォルダのハンドル（ブラウザの FileSystemDirectoryHandle か、exe 版の疑似ハンドル mkNativeDir）から＝
//   ディスクに書いた物そのまま（hash はサーバーが map_hash.py と同じ規則でこのバイト列から出す）。
// - 送る物: Info.dat（必須）・Info.dat が指す難易度の .dat（Info の順）・カバー（あれば）。本体はこの順にバイト列を繋げた物、
//   名前と大きさは ?m=（JSON {files:[{name,size}]}）。ファイル名は Info.dat 由来なので、区切り文字・..・知らない拡張子の名前は送らない
//   （サーバーも確かめる）。
// - song.egg は中身の SHA-1（crypto.subtle）と一緒に keepEgg へ。同じ hash でも無音追加だけ変えた書き出しは音だけが違う＝後から書いた方が勝つ。
//   この起動の間に同じ hash へ同じ SHA-1 を送っていれば送り直さない（sentEgg）。
// - 失敗しても書き出しの結果は変えない（呼ぶ側は console に残すだけ）。DOM を使わない。

const DAT_RE = /\.dat$/i;
const IMG_RE = /\.(png|jpe?g|webp|gif|bmp)$/i;
const MAX_MAP = 60 * 1024 * 1024;     // 譜面・カバーの合計の上限（サーバーの上限 64MB 程度より少し下）
const MAX_EGG = 300 * 1024 * 1024;    // song.egg の上限（サーバーと同じ）
const sentEgg = new Map();            // hash → この起動で送った song.egg の SHA-1

/** Info.dat 由来のファイル名を確かめる（ファイル名だけ・区切り文字や .. は不可・拡張子の決まり re） */
export function safeName(n, re) {
  n = typeof n === 'string' ? n.trim() : '';
  if (!n || n.length > 200 || n === '.' || n === '..' || /[\\/:*?"<>|\x00-\x1f]/.test(n)) return '';
  return re && !re.test(n) ? '' : n;
}

/** Info.dat（v2・v4）が指す難易度の .dat・カバー・song.egg の名前 */
export function infoFiles(info) {
  const diffs = [], seen = new Set();
  const add = n => { const s = safeName(n, DAT_RE); if (s && !seen.has(s.toLowerCase())) { seen.add(s.toLowerCase()); diffs.push(s); } };
  if (info && Array.isArray(info._difficultyBeatmapSets)) {
    for (const set of info._difficultyBeatmapSets) for (const b of (set && Array.isArray(set._difficultyBeatmaps)) ? set._difficultyBeatmaps : []) add(b && b._beatmapFilename);
  } else if (info && Array.isArray(info.difficultyBeatmaps)) {   // v4（NLM は書き出さないが、手で置いた物も読めるように）
    for (const b of info.difficultyBeatmaps) { add(b && b.beatmapDataFilename); add(b && b.lightshowDataFilename); }
  }
  const cover = safeName(info && (info._coverImageFilename ?? info.coverImageFilename), IMG_RE);
  const egg = safeName(info && (info._songFilename ?? (info.audio && info.audio.songFilename)), /\.(egg|ogg)$/i) || 'song.egg';
  return { diffs, cover, egg };
}

async function sha1Hex(buf) {
  const d = new Uint8Array(await crypto.subtle.digest('SHA-1', buf));
  return Array.from(d, b => b.toString(16).padStart(2, '0')).join('');
}

async function post(path, body) {
  let r;
  try { r = await fetch('__replay/' + path, { method: 'POST', headers: { 'X-NLM-Request': '1', 'Content-Type': 'application/octet-stream' }, body }); }
  catch (_) { return { ok: false, error: 'network' }; }
  let j = null;
  try { j = await r.json(); } catch (_) {}
  if (r.status === 404 && (!j || !j.error || j.error === 'unknown endpoint' || j.error === 'unknown')) return { ok: false, error: 'no-api' };   // この版のサーバーに控えの API が無い
  if (!j || typeof j !== 'object') return { ok: false, error: 'http-' + r.status };
  return j;
}

async function readBuf(dir, name) {
  const fh = await dir.getFileHandle(name);
  const f = await fh.getFile();
  return await f.arrayBuffer();
}

/**
 * 書き出し先の譜面のフォルダ dir を控える。egg: 'always'（書き出した直後＝送る。同じ SHA-1 を送ってあれば送らない）／
 * 'need'（サーバーの控えにまだ egg が無い時だけ）／'none'（送らない＝今回の書き出しで song.egg を書けなかった）。
 * → {ok, hash, isNew, needEgg, egg:'sent'|'same'|'skip'|'none'|'too-large'|<エラー>} / {ok:false, error}
 */
export async function keepFromDir(dir, opt = {}) {
  const egg = opt.egg || 'need';
  let infoBuf;
  try { infoBuf = await readBuf(dir, 'Info.dat'); } catch (_) { return { ok: false, error: 'no-info' }; }
  let info;
  try { info = JSON.parse(new TextDecoder().decode(infoBuf)); } catch (_) { return { ok: false, error: 'bad-info' }; }
  const names = infoFiles(info);
  if (!names.diffs.length) return { ok: false, error: 'no-diffs' };
  const files = [{ name: 'Info.dat', buf: infoBuf }];
  for (const n of names.diffs) {
    try { files.push({ name: n, buf: await readBuf(dir, n) }); }
    catch (_) { return { ok: false, error: 'missing-dat' }; }   // Info.dat が指す難易度が欠けている＝hash が遊んだ譜面と合わないので控えない
  }
  if (names.cover) { try { files.push({ name: names.cover, buf: await readBuf(dir, names.cover) }); } catch (_) {} }   // カバーは任意
  const total = files.reduce((s, f) => s + f.buf.byteLength, 0);
  if (total > MAX_MAP) return { ok: false, error: 'too-large' };
  const m = { files: files.map(f => ({ name: f.name, size: f.buf.byteLength })) };
  const r = await post('keep?m=' + encodeURIComponent(JSON.stringify(m)), new Blob(files.map(f => f.buf)));
  if (!r.ok) return { ok: false, error: typeof r.error === 'string' ? r.error : 'failed' };
  const hash = typeof r.hash === 'string' && /^[0-9a-f]{40}$/i.test(r.hash) ? r.hash.toLowerCase() : '';
  const out = { ok: true, hash, isNew: !!r.isNew, needEgg: !!r.needEgg, egg: 'none' };
  if (!hash || egg === 'none' || (egg === 'need' && !r.needEgg)) { out.egg = 'skip'; return out; }
  let eb;
  try { eb = await readBuf(dir, names.egg); } catch (_) { out.egg = 'none'; return out; }
  if (eb.byteLength > MAX_EGG) { out.egg = 'too-large'; return out; }
  const sha1 = await sha1Hex(eb);
  if (!r.needEgg && sentEgg.get(hash) === sha1) { out.egg = 'same'; return out; }
  const e = await post('keepEgg?hash=' + encodeURIComponent(hash) + '&sha1=' + sha1, eb);
  if (e.ok) { sentEgg.set(hash, sha1); out.egg = 'sent'; } else out.egg = typeof e.error === 'string' ? e.error : 'failed';
  return out;
}

// MEDIA ライブラリの「記録したフォルダ」（2026-10-12）: serve.py の /__lib/*（media_library.py）との通信・疑似ハンドル・走査の進め方・
// カバーの読み込みの順番待ち。
//
// 以前の MEDIA は File System Access API でフォルダを走査していたが、ハンドルはセッション限定で保存もできない（CLAUDE.md「WebView2 /
// File System Access API の重大な制約」）。記録したフォルダは Python 側がネイティブのパスで走査・読み出しし、ここから渡すのは
// 記録の id・相対パス・ファイル名だけ（絶対パス・URL は渡さない・受け取らない＝取り決め「守ること」）。
// 曲の項目は疑似ハンドル（getFileHandle/getFile だけの FileSystemHandle 互換）で包むので、今の MEDIA のコード（ドラッグ・曲データを読み込む・
// INFO へのドロップ・音源の配置）はブラウザのフォルダと同じ呼び方のまま動く。

const HDR = { 'Content-Type': 'application/json', 'X-NLM-Request': '1' };   // 合言葉（X-NLM-Token）は settings-mirror.js が自動で付ける

export class LibError extends Error {
  constructor(code) { super(code); this.code = code; }
}

/** /__lib/<act> を呼んで JSON を返す（通信の失敗は LibError('network')） */
export async function libPost(act, body) {
  let r;
  try {
    r = await fetch('__lib/' + act, { method: 'POST', headers: HDR, body: JSON.stringify(body || {}) });
  } catch (e) { throw new LibError('network'); }
  if (!r.ok) throw new LibError('http' + r.status);
  return r.json();
}

/** ライブラリの中の1ファイルを Blob で読む。失敗は LibError(code)。成功の応答には X-NLM-File: 1 が付く
 *（失敗は {ok:false,error} の JSON。.dat も application/json で返るので、種類では見分けない） */
export async function libReadFile(id, rel, name) {
  let r;
  try {
    r = await fetch('__lib/file', { method: 'POST', headers: HDR, body: JSON.stringify({ id, rel, name: name || '' }) });
  } catch (e) { throw new LibError('network'); }
  if (!r.ok) throw new LibError('http' + r.status);
  if (r.headers.get('X-NLM-File') !== '1') {
    let j = null;
    try { j = await r.json(); } catch (_) {}
    throw new LibError((j && j.error) || 'unknown');
  }
  return r.blob();
}

/** 記録したライブラリの中のファイルの実際のパス（Windows の形・区切りは '\'）。音源の songNode.nativePath 用＝開き直した時に exe 版が
 * ダイアログ無しで読む（CLAUDE.md「WebView2…の制約」4番の仕組み）。ライブラリの場所（/__lib/list の path）がドライブ名から始まる時だけ作る
 * （ネットワーク上のパス（UNC）は app.py の許可（may_touch）で読めないため）。rel＝ライブラリの根からの相対パス（区切り '/'）、file＝その中の
 * ファイル名（無ければ rel がファイルまでのパス）。作れなければ '' */
export function nativeFilePath(libPath, rel, file) {
  const base = String(libPath || '').replace(/\//g, '\\');
  if (!/^[A-Za-z]:\\/.test(base)) return '';
  const parts = [base.replace(/\\+$/, '')];
  for (const p of [...String(rel || '').split('/'), ...(file ? [String(file)] : [])]) {
    if (!p) continue;
    if (p === '.' || p === '..' || /[\\/:\0]/.test(p)) return '';   // 1階層の名前だけ（外へ出る・別のドライブを指す字面は作らない）
    parts.push(p);
  }
  return parts.length > 1 ? parts.join('\\') : '';
}

const baseName = p => String(p || '').split('/').filter(Boolean).pop() || '';
export const dirOf = p => { const s = String(p || ''); const i = s.lastIndexOf('/'); return i >= 0 ? s.slice(0, i) : ''; };

/** ファイルの疑似ハンドル {kind,name,getFile()}。rel＝譜面フォルダ（name を空にすればファイルまでの相対パス） */
export function libFileHandle(id, rel, name) {
  const shown = name || baseName(rel);
  return {
    kind: 'file', name: shown,
    getFile: async () => {
      const b = await libReadFile(id, rel, name);
      return new File([b], shown, { type: b.type || '' });
    },
  };
}

/** フォルダの疑似ハンドル（getFileHandle だけ）。曲の項目の item.dir に入れる＝ prepareMediaFrag 等の dir.getFileHandle がそのまま動く */
export function libDirHandle(id, rel) {
  return { kind: 'directory', name: baseName(rel), getFileHandle: async n => libFileHandle(id, rel, n) };
}

// ---------------------------------------------------------------- Info.dat の形をそろえる

/** v4 の Info.dat を、NLM の MEDIA が読む v2 の形（曲名・BPM・音源・カバー・試聴区間・難易度の一覧）に写す。v2/v3 はそのまま。
 * v4 の譜面ファイルそのものは NLM の読み込み（parseDiffFragment）が未対応＝ここでは一覧と音源・曲情報のためだけに使う */
export function infoToV2(info) {
  if (!info || typeof info !== 'object' || !Array.isArray(info.difficultyBeatmaps)) return info || {};
  const song = info.song || {}, audio = info.audio || {}, sets = new Map();
  for (const d of info.difficultyBeatmaps) {
    if (!d || typeof d !== 'object') continue;
    const ch = String(d.characteristic || 'Standard');
    if (!sets.has(ch)) sets.set(ch, []);
    sets.get(ch).push({ _difficulty: d.difficulty, _beatmapFilename: d.beatmapDataFilename,
      _noteJumpMovementSpeed: d.noteJumpMovementSpeed, _noteJumpStartBeatOffset: d.noteJumpStartBeatOffset });
  }
  const mappers = [];
  for (const d of info.difficultyBeatmaps) for (const m of ((d && d.beatmapAuthors && d.beatmapAuthors.mappers) || [])) if (typeof m === 'string' && !mappers.includes(m)) mappers.push(m);
  return {
    _version: '2.1.0', _fromV4: true,
    _songName: song.title || '', _songSubName: song.subTitle || '', _songAuthorName: song.author || '', _levelAuthorName: mappers.join(', '),
    _beatsPerMinute: audio.bpm, _songFilename: audio.songFilename || 'song.egg', _coverImageFilename: info.coverImageFilename || '',
    _previewStartTime: audio.previewStartTime, _previewDuration: audio.previewDuration,
    _environmentName: (info.environmentNames || [])[0] || '',
    _difficultyBeatmapSets: [...sets].map(([ch, list]) => ({ _beatmapCharacteristicName: ch, _difficultyBeatmaps: list })),
  };
}

/** 走査の結果（MapEntry）から、すぐ使える v2 の形の Info（試聴区間・customData は無い）。本物は必要な時に読む（ensureItemInfo） */
export function quickInfo(m) {
  const sets = new Map();
  for (const d of m.diffs || []) {
    if (!sets.has(d.char)) sets.set(d.char, []);
    sets.get(d.char).push({ _difficulty: d.diff, _beatmapFilename: d.file, _noteJumpMovementSpeed: d.njs, _noteJumpStartBeatOffset: d.offset });
  }
  return {
    _songName: m.name || '', _songSubName: m.subName || '', _songAuthorName: m.artist || '', _levelAuthorName: m.mapper || '',
    _beatsPerMinute: m.bpm, _songFilename: m.songFile || 'song.egg', _coverImageFilename: m.coverFile || '', _environmentName: m.env || '',
    _difficultyBeatmapSets: [...sets].map(([ch, list]) => ({ _beatmapCharacteristicName: ch, _difficultyBeatmaps: list })),
  };
}

const KEY_RE = /^([0-9a-f]{1,6})(?=$| \(| - )/;   // media_library.py の _KEY_RE と同じ（フォルダ名の先頭の BeatSaver のキー）

/** ブラウザで選んだフォルダ（その時限り）の曲に、詳細表示・絞り込み用の MapEntry 相当を作る（ノーツ数・長さ等は分からない＝null） */
export function entryFromInfo(info, folderName, fmt) {
  const diffs = [];
  for (const s of info._difficultyBeatmapSets || []) for (const d of (s && s._difficultyBeatmaps) || []) {
    const num = v => (typeof v === 'number' && isFinite(v)) ? v : null;
    diffs.push({ char: String(s._beatmapCharacteristicName || 'Standard'), diff: String(d._difficulty || ''), label: '', file: d._beatmapFilename || null,
      njs: num(d._noteJumpMovementSpeed), offset: num(d._noteJumpStartBeatOffset), notes: null, bombs: null, walls: null, lengthSec: null, nps: null, mods: [], req: [] });
  }
  const km = KEY_RE.exec(folderName || '');
  const bpm = +info._beatsPerMinute;
  return { rel: folderName || '', key: km ? km[1] : null, hash: null, fmt: fmt || 2, name: info._songName || folderName || '', subName: info._songSubName || '',
    artist: info._songAuthorName || '', mapper: info._levelAuthorName || '', bpm: bpm > 0 ? bpm : null, env: info._environmentName || null,
    songFile: info._songFilename || null, coverFile: info._coverImageFilename || null, durationSec: null, dlTime: null, diffs };
}

// ---------------------------------------------------------------- 走査

const sleep = ms => new Promise(r => setTimeout(r, ms));

/** 1つのライブラリの走査を done まで進める（サーバーは裏のスレッドで走査し、途中経過を返す）。
 * cb.maps(新しい MapEntry の配列)・cb.progress({done,total})・cb.alive()（false で中断）。first＝rescan の応答（あればそこから）。
 * → 最後の応答（{done, ok, error?, files, skipped}）。中断・失敗は null か {ok:false,error} */
export async function runScan(id, cb, first) {
  let next = 0, r = first || null;
  for (;;) {
    if (!r) {
      try { r = await libPost('scan', { id, from: next }); } catch (e) { return { ok: false, error: e.code || 'network', done: true }; }
    }
    if (!cb.alive()) return null;
    if (!r || !('done' in r)) return { ok: false, error: (r && r.error) || 'unknown', done: true };   // unknown-lib 等
    if (r.maps && r.maps.length) cb.maps(r.maps);
    next = r.next != null ? r.next : next;
    if (r.progress) cb.progress(r.progress);
    if (r.done) return r;
    const got = r.maps && r.maps.length;
    r = null;
    await sleep(got ? 150 : 350);   // 新しい曲が来ている間は早めに、フォルダをたどっている間はゆっくり聞く
  }
}

// ---------------------------------------------------------------- カバー・アートワークの読み込み（順番待ち）

/** 記録したフォルダの曲・画像・音楽のサムネイルを、見えている物から1件ずつ読む（全部を先読みしない＝1000曲でも通信とメモリを使い切らない）。
 * load(item) は Blob か null を返す関数（曲＝カバー画像、画像＝その画像、音楽＝埋め込みアートワーク）、apply(item, blob) は画面へ反映する関数 */
export function makeCoverLoader(load, apply) {
  const queue = [], queued = new Set();
  let busy = false;
  const io = (typeof IntersectionObserver === 'function') ? new IntersectionObserver(ents => {
    for (const e of ents) if (e.isIntersecting && e.target._item) want(e.target._item, true);
  }, { rootMargin: '300px 0px' }) : null;
  /** 1件を読む（同じ項目を2回読まない。読み途中なら同じ Promise を返す＝now() が待てる） */
  function loadOne(it) {
    if (!it._coverP) {
      it._coverTried = true;
      it._coverP = (async () => {
        let blob = null;
        try { blob = await load(it); } catch (_) { blob = null; }
        if (blob && !it._libGone) { try { apply(it, blob); } catch (_) {} }
      })();
    }
    return it._coverP;
  }
  async function pump() {
    if (busy) return;
    busy = true;
    try {
      while (queue.length) {
        const it = queue.shift();
        queued.delete(it);
        if (it.coverURL || it._coverTried || it._libGone) continue;
        await loadOne(it);
        await sleep(0);   // 描画・入力へ明け渡す
      }
    } finally { busy = false; }
  }
  function want(it, urgent) {
    if (!it || it.coverURL || it._coverTried || it._libGone) return;
    if (queued.has(it)) {
      if (urgent) { const i = queue.indexOf(it); if (i > 0) { queue.splice(i, 1); queue.unshift(it); } }
    } else {
      queued.add(it);
      if (urgent) queue.unshift(it); else queue.push(it);
    }
    pump();
  }
  return {
    want,
    observe(el, it) { el._item = it; if (io) io.observe(el); else want(it); },
    unobserve(el) { if (io) io.unobserve(el); },
    /** 今すぐ欲しい（ドラッグを始めた時など）。読み終わるまで待つ */
    async now(it) {
      if (!it || it.coverURL || it._libGone) return;
      queued.delete(it); const i = queue.indexOf(it); if (i >= 0) queue.splice(i, 1);
      await loadOne(it);   // 裏で読み途中なら、その終わりを待つ
    },
  };
}

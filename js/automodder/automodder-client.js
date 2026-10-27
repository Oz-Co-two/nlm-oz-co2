// AutoModder の判定のプラグイン nlm-automodder の状態と通信（serve.py の /__automodder/* → automodder_plugin.py）。
// 作りは「難易度を測る」の rating-client.js と同じ。run({ifChanged:true}) は、渡す中身（書き出しと同じ Info.dat/.dat と曲の長さ）が
// 前回うまく確かめられた時と同じなら動かし直さない（譜面チェックのタブを開くたびに exe を起動しない）。
// GitHub への通信（install / check）は利用者がボタンを押した時だけ。status / run は PC の中だけで終わる。
// サーバーの失敗コード → 表示文（am.err.<code>）
const ERR = {
  network: 'GitHub に接続できませんでした。ネット接続を確認してください。',
  notFound: '配布元に公開中の版が見つかりませんでした。',
  badManifest: '配布元の情報（manifest.json）が読めませんでした。',
  hash: 'ダウンロードしたファイルが配布元の情報と一致しません（壊れているか改ざんの可能性）。取り込みを中止しました。',
  badZip: 'ダウンロードしたファイルの中身が正しくありません。取り込みを中止しました。',
  tooLarge: 'ファイルが大きすぎます。',
  protocol: 'このプラグインの版は、今の NLM では使えません。NLM を更新してください。',
  notInstalled: 'プラグインが取り込まれていません。',
  run: 'AutoModder の実行に失敗しました。',
  timeout: 'AutoModder が時間内に終わりませんでした。',
  badInput: '確かめる譜面の内容が正しくありません。',
};

export function createAutoModderClient({ t, collect }) {
  // st=status の応答 / latest=更新確認で見つけた版 / last=最後の結果（{error} もある） / busy=''|'check'|'install'|'use'|'run'
  // msg={err|ok, text, act}＝取り込み・更新確認などの結果のお知らせ（act はどの操作の結果か）
  const S = { st: null, latest: null, last: null, busy: '', msg: null };
  const subs = new Set();
  const emit = () => { for (const f of subs) { try { f(); } catch (e) { console.error(e); } } };
  const post = async (act, body) => {
    const r = await fetch('__automodder/' + act, { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-NLM-Request': '1' },
      body: JSON.stringify(body || {}) });
    if (!r.ok) throw new Error('HTTP ' + r.status);
    return r.json();
  };
  const errText = j => t('am.err.' + j.error, ERR[j.error] || String(j.error)) + (j.detail ? ` (${j.detail})` : '');
  const exText = e => String(e && e.message || e);
  const installed = () => !!(S.st && S.st.current);
  let sig = null;          // 最後にうまく確かめられた時の中身（同じなら動かし直さない）
  let statusP = null, running = null, again = null;

  async function refreshStatus() {
    try { S.st = await post('status'); } catch (e) { S.st = null; S.msg = { err: true, text: exText(e), act: 'status' }; }
    emit();
  }
  // 状態がまだ分からなければ確かめる（同時に呼ばれても1回だけ）
  function ensureStatus() {
    if (S.st) return Promise.resolve();
    if (!statusP) statusP = refreshStatus().finally(() => { statusP = null; });
    return statusP;
  }
  async function check() {
    if (S.busy) return; S.busy = 'check'; S.msg = null; emit();
    try {
      const j = await post('check');
      if (!j.ok) S.msg = { err: true, text: errText(j), act: 'check' };
      else {
        S.st = j; S.latest = j.latest;
        const L = S.latest;
        if (!L.compatible) S.msg = { err: true, text: t('am.needNlm', '新しい版 v{v} がありますが、使うには NLM の更新が必要です。').replace('{v}', L.version), act: 'check' };
        else if (L.installed) S.msg = { ok: true, text: t('am.upToDate', '最新版（v{v}）を取り込み済みです。').replace('{v}', L.version), act: 'check' };
        else S.msg = { ok: true, text: t('am.newer', '新しい版 v{v} があります。').replace('{v}', L.version), act: 'check' };
      }
    } catch (e) { S.msg = { err: true, text: exText(e), act: 'check' }; }
    S.busy = ''; emit();
  }
  // 取り込み（GitHub から）。うまくいったら true（動かすかどうかは呼んだ側が決める）
  async function install() {
    if (S.busy) return false; S.busy = 'install'; S.msg = null; emit();
    let ok = false;
    try {
      const j = await post('install');
      if (!j.ok) S.msg = { err: true, text: errText(j), act: 'install' };
      else { S.st = j; S.latest = null; S.last = null; sig = null; ok = true; S.msg = { ok: true, text: t('am.installed', 'v{v} を取り込みました。').replace('{v}', j.current), act: 'install' }; }
    } catch (e) { S.msg = { err: true, text: exText(e), act: 'install' }; }
    S.busy = ''; emit();
    return ok && installed();
  }
  async function useVer(v) {
    if (S.busy) return; S.busy = 'use'; emit();
    try { const j = await post('use', { version: v }); if (j.ok) { S.st = j; S.last = null; sig = null; S.msg = null; } else S.msg = { err: true, text: errText(j), act: 'use' }; }
    catch (e) { S.msg = { err: true, text: exText(e), act: 'use' }; }
    S.busy = ''; emit();
  }
  // 確かめる。動いている最中に頼まれたら、終わった後にもう1回（ifChanged はどちらかが無条件なら無条件）
  function run(opt = {}) {
    if (!installed()) return Promise.resolve();
    if (running) { again = { ifChanged: (again ? again.ifChanged : true) && !!opt.ifChanged }; return running; }
    if (S.busy) return Promise.resolve();   // 取り込み・版の切り替え中
    running = runOnce(!!opt.ifChanged).finally(() => {
      running = null; const a = again; again = null;
      if (a) run(a);
    });
    return running;
  }
  async function runOnce(ifChanged) {
    let p;
    try { p = await collect(); } catch (e) { p = { error: exText(e) }; }
    if (p.error) { S.last = { error: p.error }; sig = null; emit(); return; }
    const key = p.files.map(f => f.name + '\n' + f.text).join('\0') + '\0' + p.songLength;
    if (ifChanged && key === sig && S.last && !S.last.error) return;
    S.busy = 'run'; S.msg = null; emit();
    try {
      const j = await post('run', { files: p.files, songLength: p.songLength });
      S.last = j.ok ? j : { error: errText(j) }; sig = j.ok ? key : null;
    } catch (e) { S.last = { error: exText(e) }; sig = null; }
    S.busy = ''; emit();
  }
  return {
    state: S, installed, ensureStatus, refreshStatus, check, install, useVer, run,
    subscribe: f => { subs.add(f); return () => subs.delete(f); },
  };
}

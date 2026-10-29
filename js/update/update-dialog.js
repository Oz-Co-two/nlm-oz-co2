// 本体の自動更新のダイアログ（2026-10-02）。確認・ダウンロード・差し替えは serve.py → app_update.py。
// 起動時の確認（環境設定 bsnm_updateCheck='0' で OFF）は exe 版だけ・通信の失敗は何も出さない。
// 「更新しない」を選んだ版は bsnm_updateSkip に記録し、それより新しい版が出るまで起動時には出さない
// （メニューの「更新を確認…」からはいつでも更新できる）。文字はすべて textContent で入れる（更新内容も外から来る文字のため）。
// 取り込み済みのプラグイン（難易度を測る＝nlm-rating・AutoModder＝nlm-automodder）も、本体の確認に続けて同じ形で知らせる（2026-10-28）:
//  - 取り込んでいないプラグインは GitHub へ問い合わせない。起動時は本体と同じ条件（exe 版・環境設定 ON）
//  - 「更新しない」はプラグインごとの skipKey（bsnm_rtUpdSkip 等）に版を記録。後からはメニューの「更新を確認…」かパネルの［更新を確認］で更新できる
//  - 「更新する」はパネルと共有の部品（client.install）で取り込む＝パネルの表示も新しい版になる。アプリの再起動は要らない
//  - 画面は1つずつ（前の画面が閉じてから次を出す）。更新内容はプラグインの manifest.json の notes（プラグインの CHANGELOG の見出し）
const ERR = {
  network: 'GitHub に接続できませんでした。ネット接続を確認してください。',
  notFound: '配布元に更新情報（update.json）が見つかりませんでした。',
  badManifest: '配布元の更新情報（update.json）が読めませんでした。',
  tooLarge: 'ファイルが大きすぎます。',
  hash: 'ダウンロードしたファイルが配布元の情報と一致しません（壊れているか改ざんの可能性）。更新を中止しました。',
  badZip: 'ダウンロードしたファイルの中身が正しくありません。更新を中止しました。',
  extract: 'ダウンロードしたファイルを展開できませんでした。',
  notAuto: 'この環境では自動更新できません。',
  noUpdate: '新しい版はありません。',
  notReady: '更新の準備ができていません。',
};
const SKIP_KEY = 'bsnm_updateSkip', CHECK_KEY = 'bsnm_updateCheck';
const vt = v => { const m = /^v(\d+)\.(\d+)\.(\d+)-oz$/.exec(v || ''); return m ? m.slice(1).map(Number) : null; };
const vtp = v => { const m = /^(\d+)\.(\d+)\.(\d+)$/.exec(v || ''); return m ? m.slice(1).map(Number) : null; };   // プラグインの版（0.2.0）
const gtBy = parse => (a, b) => { const x = parse(a), y = parse(b); if (!x) return false; if (!y) return true;
  for (let i = 0; i < 3; i++) if (x[i] !== y[i]) return x[i] > y[i]; return false; };
const vgt = gtBy(vt), vgtp = gtBy(vtp);
const lsGet = k => { try { return localStorage.getItem(k); } catch (_) { return null; } };
const lsSet = (k, v) => { try { localStorage.setItem(k, v); } catch (_) {} };
const sleep = ms => new Promise(r => setTimeout(r, ms));

/** plugins: [{ base:'__rating/', skipKey, errKey:'rt.err.', client, name:()=>表示名, where:()=>版を戻せる場所 }] */
export function installUpdater(api) {
  const { t, tf, lang, confirmDiscard, showOk, plugins = [] } = api;
  const send = async (url, body) => {
    const r = await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-NLM-Request': '1' },
      body: JSON.stringify(body || {}) });
    if (!r.ok) throw new Error('HTTP ' + r.status);
    return r.json();
  };
  const post = (act, body) => send('__update/' + act, body);
  const ppost = (p, act, body) => send(p.base + act, body);
  const errText = j => t('upd.err.' + j.error, ERR[j.error] || j.error) + (j.detail ? ` (${j.detail})` : '');
  const mb = n => (n / 1048576).toFixed(1);

  // ---- ダイアログの部品（未保存確認と同じ見た目）----
  // 流れ（更新するかの選択→ダウンロード→結果）の終わりを ended で知らせる（次のプラグインの知らせを、前の画面が閉じてから出すため）。
  // 流れの中で次の画面へ移る時は openDlg が前の画面を消すだけ（ended は呼ばない）、閉じる時は closeDlg。
  // gen＝確認の回。起動時の確認の途中でメニューから確認し直したら、古い回の続き（次のプラグインの知らせ）は出さない
  let bg = null, onKey = null, ended = null, gen = 0;
  function dropDlg() { if (onKey) removeEventListener('keydown', onKey, true); onKey = null; if (bg) bg.remove(); bg = null; }
  function endFlow() { const f = ended; ended = null; if (f) f(); }
  function closeDlg() { dropDlg(); endFlow(); }
  function el(tag, cls, text) { const e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; }
  /** escClose=Esc で閉じてよいか（更新するかの選択と、ダウンロード中は閉じさせない） */
  function openDlg(title, escClose) {
    dropDlg();
    bg = el('div'); bg.id = 'updDlgBg';
    const dlg = el('div'); dlg.id = 'updDlg'; bg.appendChild(dlg);
    dlg.appendChild(el('div', 'udTitle', title));
    const body = el('div', 'udBody'); dlg.appendChild(body);
    const btns = el('div', 'udBtns'); dlg.appendChild(btns);
    onKey = e => { if (e.key === 'Escape' && escClose) { e.preventDefault(); closeDlg(); } e.stopPropagation(); };   // 裏のショートカットを発火させない
    addEventListener('keydown', onKey, true);
    document.body.appendChild(bg);
    return { body, btns };
  }
  /** fn の中で開いた画面が最後に閉じた時（何も出さなければ fn の後）に解決する */
  function flow(fn) {
    return new Promise(res => {
      endFlow();
      ended = res;
      Promise.resolve().then(fn).catch(e => console.error(e)).finally(() => { if (!bg && ended === res) endFlow(); });
    });
  }
  /** 他の画面（未保存の確認・読み込み中・環境設定など）が出ていれば閉じるまで待つ（曲の解析の問い合わせと同じ見方） */
  async function whenFree(my) {
    const busy = () => {
      if (document.querySelector('#updDlgBg, #dirtyDlgBg, #busyDlgBg')) return true;
      const s = document.getElementById('settingsBg');
      return !!s && getComputedStyle(s).display !== 'none';
    };
    while (my === gen && busy()) await sleep(500);
  }
  function btn(row, label, cls, fn) { const b = el('button', cls, label); b.addEventListener('click', fn); row.appendChild(b); return b; }
  function info(title, text, isErr) {
    const d = openDlg(title, true);
    d.body.appendChild(el('div', 'udMsg' + (isErr ? ' err' : ''), text));
    btn(d.btns, t('ui.close', '閉じる'), 'pri', closeDlg).focus();
  }
  /** 版ごとの見出しの一覧。label=版の見出しの文字、open=「詳しく見る」で開く物 */
  function notesBox(body, notes, label, open) {
    const list = el('div', 'udNotes'); body.appendChild(list);
    const en = lang() === 'en';
    for (const n of notes) {
      const head = el('div', 'udVer'); head.appendChild(el('span', 'udVerName', label(n.version)));
      const more = el('a', 'udMore', t('upd.more', '詳しく見る')); more.href = '#';
      more.addEventListener('click', e => { e.preventDefault(); open(n.version); });
      head.appendChild(more); list.appendChild(head);
      const items = (en && n.en && n.en.length ? n.en : n.ja) || [];
      if (items.length) { const ul = el('ul'); for (const s of items) ul.appendChild(el('li', '', s)); list.appendChild(ul); }
    }
    return list;
  }

  // ---- 更新内容（版ごとの見出し）＋「更新する／更新しない」----
  function prompt(j) {
    const d = openDlg(tf('upd.newTitle', '新しいバージョン {v} があります', { v: j.latest }), false);
    d.body.appendChild(el('div', 'udCur', tf('upd.current', '今のバージョン: {v}', { v: j.current })));
    const list = notesBox(d.body, j.notes || [], v => v, v => post('openNotes', { lang: lang(), version: v }).catch(() => {}));
    if (!(j.notes || []).length) list.appendChild(el('div', 'udMsg', t('upd.noNotes', '更新内容の情報がありません。')));
    const skip = () => { lsSet(SKIP_KEY, j.latest); closeDlg(); };
    if (j.auto === 'ok') {
      d.body.appendChild(el('div', 'udHint', tf('upd.hint', '「更新する」を押すと、ダウンロード（{mb}MB）してからアプリを再起動して更新します。環境設定・アセット・翻訳はそのまま残ります。', { mb: mb(j.size) })));
      btn(d.btns, t('upd.skip', '更新しない'), '', skip);
      btn(d.btns, t('upd.update', '更新する'), 'pri', () => run(j)).focus();
    } else {
      const why = { readonly: t('upd.whyReadonly', 'アプリのフォルダに書き込めないため、自動では更新できません。'),
        manual: t('upd.whyManual', 'この版は自動では更新できません。'),
        notExe: t('upd.whyNotExe', '開発用の起動方法（python serve.py）では自動更新しません。') }[j.auto] || '';
      d.body.appendChild(el('div', 'udHint', why + t('upd.manualHint', 'リリースページから zip をダウンロードして更新してください。')));
      btn(d.btns, t('upd.skip', '更新しない'), '', skip);
      btn(d.btns, t('upd.openReleases', 'リリースページを開く'), 'pri', () => { post('openReleases').catch(() => {}); closeDlg(); }).focus();
    }
  }

  // ---- ダウンロード → 差し替え役の起動 → 終了 ----
  async function run(j) {
    dropDlg();
    if (!await confirmDiscard('quit')) return endFlow();   // 未保存なら先に保存するか聞く（更新のためにアプリを終了するので）
    const d = openDlg(tf('upd.dlTitle', '{v} に更新しています', { v: j.latest }), false);
    const msg = el('div', 'udMsg', t('upd.downloading', 'ダウンロード中…')); d.body.appendChild(msg);
    const bar = el('div', 'udBar'), fill = el('div', 'udFill'); bar.appendChild(fill); d.body.appendChild(bar);
    let cancelled = false;
    const cancel = btn(d.btns, t('word.cancel', 'キャンセル'), '', () => { cancelled = true; cancel.disabled = true; post('cancel').catch(() => {}); });
    const fail = text => info(t('upd.failTitle', '更新できませんでした'), text, true);
    let p;
    try {
      p = await post('download');
      while (p.ok && (p.state === 'download' || p.state === 'extract')) {
        if (p.state === 'download' && p.total) {
          fill.style.width = (100 * p.done / p.total).toFixed(1) + '%';
          msg.textContent = tf('upd.dlProgress', 'ダウンロード中… {d} / {t}MB', { d: mb(p.done), t: mb(p.total) });
        } else if (p.state === 'extract') { fill.style.width = '100%'; msg.textContent = t('upd.extracting', '展開しています…'); cancel.disabled = true; }
        await sleep(300);
        p = await post('progress');
      }
    } catch (e) { return fail(String(e && e.message || e)); }
    if (p.state === 'cancel' || cancelled && p.state !== 'ready') { closeDlg(); return; }
    if (!p.ok || p.state !== 'ready') return fail(errText(p));
    msg.textContent = t('upd.restarting', '更新を適用するため、アプリを再起動します…'); cancel.disabled = true;
    try {
      const r = await post('apply', { lang: lang() });
      if (!r.ok) return fail(errText(r));
    } catch (e) { return fail(String(e && e.message || e)); }
    await sleep(300);
    try { window.pywebview.api.quit_app(); } catch (_) {}
  }

  // ---- 取り込み済みのプラグイン ----
  /** 最新版を調べる。取り込んでいなければ null（GitHub へは行かない）。{j, newer, needNlm} か {err} */
  async function pluginCheck(p) {
    let st;
    try { st = await ppost(p, 'status'); } catch (_) { return null; }
    if (!st || !st.ok || !st.current) return null;
    let j;
    try { j = await ppost(p, 'check'); } catch (e) { return { err: String(e && e.message || e) }; }
    if (!j || !j.ok || !j.latest) return { err: t(p.errKey + (j && j.error), String(j && j.error || '')) };
    const L = j.latest;
    return { j, newer: !!(L.newer && L.compatible), needNlm: !!(L.newer && !L.compatible) };
  }
  function pluginPrompt(p, j) {
    const L = j.latest, where = p.where();
    const d = openDlg(tf('upd.pl.newTitle', '{name}の新しい版 v{v} があります', { name: p.name(), v: L.version }), false);
    d.body.appendChild(el('div', 'udCur', tf('upd.pl.current', '今の版: v{v}', { v: j.current })));
    const has = (L.notes || []).length > 0;
    const list = notesBox(d.body, has ? L.notes : [{ version: L.version, ja: [], en: [] }], v => 'v' + v,
      v => ppost(p, 'openNotes', { version: v }).catch(() => {}));
    if (!has) list.appendChild(el('div', 'udMsg', t('upd.noNotes', '更新内容の情報がありません。')));
    d.body.appendChild(el('div', 'udHint', tf('upd.pl.hint', '「更新する」を押すと、ダウンロード（{mb}MB）して取り込みます。アプリの再起動は要りません。前の版も残るので、{where}の版の選択で戻せます。', { mb: mb(L.size), where })));
    d.body.appendChild(el('div', 'udHint', tf('upd.pl.later', '「更新しない」にしても、あとからヘルプのメニューの「更新を確認…」か、{where}の［更新を確認］で更新できます。', { where })));
    btn(d.btns, t('upd.skip', '更新しない'), '', () => { lsSet(p.skipKey, L.version); closeDlg(); });
    btn(d.btns, t('upd.update', '更新する'), 'pri', () => pluginRun(p, L)).focus();
  }
  async function pluginRun(p, L) {
    const d = openDlg(tf('upd.pl.dlTitle', '{name}を v{v} に更新しています', { name: p.name(), v: L.version }), false);
    d.body.appendChild(el('div', 'udMsg', t('upd.pl.installing', 'ダウンロードして取り込んでいます…')));
    const bar = el('div', 'udBar busy'); bar.appendChild(el('div', 'udFill')); d.body.appendChild(bar);
    for (let i = 0; i < 300 && p.client.state.busy; i++) await sleep(200);   // 測定・確かめの途中なら終わるのを待つ（取り込みと同時には動かせない）
    let ok = false;
    try { ok = await p.client.install(); } catch (_) {}
    const S = p.client.state, cur = S.st && S.st.current;
    if (ok && cur) { closeDlg(); showOk(tf('upd.pl.done', '{name}を v{v} に更新しました', { name: p.name(), v: cur })); }
    else info(t('upd.failTitle', '更新できませんでした'), (S.msg && S.msg.err && S.msg.text) || t('upd.pl.failed', '取り込めませんでした。'), true);
  }

  // ---- 起動時（exe 版・環境設定で ON の時だけ。失敗は何も出さない）----
  async function autoCheck() {
    const my = ++gen;
    let st;
    try { st = await post('status'); } catch (_) { return; }
    if (st.justUpdated) showOk(tf('upd.done', '{v} に更新しました', { v: st.justUpdated.to }));
    if (!st.frozen || lsGet(CHECK_KEY) === '0') return;
    let j = null;
    try { j = await post('check'); } catch (_) {}
    if (my !== gen) return;
    if (j && j.ok && j.newer) {
      const skipped = lsGet(SKIP_KEY);
      if (!(skipped && !vgt(j.latest, skipped)) && !document.getElementById('updDlgBg')) await flow(() => prompt(j));   // 「更新しない」にした版（とそれ以前）は出さない
    }
    // 取り込み済みのプラグイン（本体を更新した時はアプリが再起動するので、ここへは来ない）
    for (const p of plugins) {
      if (my !== gen) return;
      const r = await pluginCheck(p);
      if (!r || !r.newer) continue;
      const skipped = lsGet(p.skipKey);
      if (skipped && !vgtp(r.j.latest.version, skipped)) continue;
      await whenFree(my);
      if (my !== gen) return;
      await flow(() => pluginPrompt(p, r.j));
    }
  }

  // ---- メニューの「更新を確認…」（記録した版も出す。結果は必ず表示）----
  // 本体に新しい版があればその画面、続けて取り込み済みのプラグインを1つずつ。どれも新しくなければ結果をまとめて出す
  // （知らせを1つでも出した時は、まとめには確認できなかった物・NLM の更新が要る物だけを出す＝「最新です」を後から重ねない）
  async function manualCheck() {
    const my = ++gen;
    const title = t('upd.checkTitle', '更新の確認');
    const checking = () => { const d = openDlg(title, true); d.body.appendChild(el('div', 'udMsg', t('upd.checking', '確認しています…'))); };
    endFlow();
    checking();
    let j;
    try { j = await post('check'); } catch (e) { return info(title, String(e && e.message || e), true); }
    if (my !== gen) return;
    if (!j.ok) return info(title, errText(j), true);
    const lines = [];   // [文, 知らせを出した後でも出すか]
    let shown = false;
    if (j.newer) { shown = true; await flow(() => prompt(j)); if (my !== gen) return; if (plugins.length) checking(); }
    else lines.push([tf('upd.upToDate', '最新のバージョンです（{v}）。', { v: j.current }), false]);
    for (let i = 0; i < plugins.length; i++) {
      const p = plugins[i], r = await pluginCheck(p);
      if (my !== gen) return;
      if (!r) continue;
      if (r.err) lines.push([tf('upd.pl.checkFail', '{name}: 確認できませんでした（{err}）', { name: p.name(), err: r.err }), true]);
      else if (r.newer) {
        shown = true;
        await flow(() => pluginPrompt(p, r.j));
        if (my !== gen) return;
        if (i < plugins.length - 1) checking();
      }
      else if (r.needNlm) lines.push([tf('upd.pl.needNlm', '{name}: 新しい版 v{v} がありますが、使うには NLM の更新が必要です。', { name: p.name(), v: r.j.latest.version }), true]);
      else lines.push([tf('upd.pl.upToDate', '{name}: 最新の版（v{v}）を取り込み済みです。', { name: p.name(), v: r.j.latest.version }), false]);
    }
    if (my !== gen) return;
    const out = lines.filter(l => !shown || l[1]).map(l => l[0]);
    if (out.length) info(title, out.join('\n')); else closeDlg();
  }

  return { autoCheck, manualCheck, isOn: () => lsGet(CHECK_KEY) !== '0', setOn: on => lsSet(CHECK_KEY, on ? '1' : '0') };
}

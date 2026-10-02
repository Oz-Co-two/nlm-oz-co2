// 本体の自動更新のダイアログ（2026-10-02）。確認・ダウンロード・差し替えは serve.py → app_update.py。
// 起動時の確認（環境設定 bsnm_updateCheck='0' で OFF）は exe 版だけ・通信の失敗は何も出さない。
// 「更新しない」を選んだ版は bsnm_updateSkip に記録し、それより新しい版が出るまで起動時には出さない
// （メニューの「更新を確認…」からはいつでも更新できる）。文字はすべて textContent で入れる（更新内容も外から来る文字のため）。
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
const vgt = (a, b) => { const x = vt(a), y = vt(b); if (!x) return false; if (!y) return true;
  for (let i = 0; i < 3; i++) if (x[i] !== y[i]) return x[i] > y[i]; return false; };
const lsGet = k => { try { return localStorage.getItem(k); } catch (_) { return null; } };
const lsSet = (k, v) => { try { localStorage.setItem(k, v); } catch (_) {} };
const sleep = ms => new Promise(r => setTimeout(r, ms));

export function installUpdater(api) {
  const { t, tf, lang, confirmDiscard, showOk } = api;
  const post = async (act, body) => {
    const r = await fetch('__update/' + act, { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-NLM-Request': '1' },
      body: JSON.stringify(body || {}) });
    if (!r.ok) throw new Error('HTTP ' + r.status);
    return r.json();
  };
  const errText = j => t('upd.err.' + j.error, ERR[j.error] || j.error) + (j.detail ? ` (${j.detail})` : '');
  const mb = n => (n / 1048576).toFixed(1);

  // ---- ダイアログの部品（未保存確認と同じ見た目）----
  let bg = null, onKey = null;
  function closeDlg() { if (onKey) removeEventListener('keydown', onKey, true); onKey = null; if (bg) bg.remove(); bg = null; }
  function el(tag, cls, text) { const e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; }
  /** escClose=Esc で閉じてよいか（更新するかの選択と、ダウンロード中は閉じさせない） */
  function openDlg(title, escClose) {
    closeDlg();
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
  function btn(row, label, cls, fn) { const b = el('button', cls, label); b.addEventListener('click', fn); row.appendChild(b); return b; }
  function info(title, text, isErr) {
    const d = openDlg(title, true);
    d.body.appendChild(el('div', 'udMsg' + (isErr ? ' err' : ''), text));
    btn(d.btns, t('ui.close', '閉じる'), 'pri', closeDlg).focus();
  }

  // ---- 更新内容（版ごとの見出し）＋「更新する／更新しない」----
  function prompt(j) {
    const d = openDlg(tf('upd.newTitle', '新しいバージョン {v} があります', { v: j.latest }), false);
    d.body.appendChild(el('div', 'udCur', tf('upd.current', '今のバージョン: {v}', { v: j.current })));
    const list = el('div', 'udNotes'); d.body.appendChild(list);
    const en = lang() === 'en';
    for (const n of j.notes || []) {
      const head = el('div', 'udVer'); head.appendChild(el('span', 'udVerName', n.version));
      const more = el('a', 'udMore', t('upd.more', '詳しく見る')); more.href = '#';
      more.addEventListener('click', e => { e.preventDefault(); post('openNotes', { lang: lang(), version: n.version }).catch(() => {}); });
      head.appendChild(more); list.appendChild(head);
      const ul = el('ul'); for (const s of (en && n.en && n.en.length ? n.en : n.ja) || []) ul.appendChild(el('li', '', s));
      list.appendChild(ul);
    }
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
    closeDlg();
    if (!await confirmDiscard('quit')) return;   // 未保存なら先に保存するか聞く（更新のためにアプリを終了するので）
    const d = openDlg(tf('upd.dlTitle', '{v} に更新しています', { v: j.latest }), false);
    const msg = el('div', 'udMsg', t('upd.downloading', 'ダウンロード中…')); d.body.appendChild(msg);
    const bar = el('div', 'udBar'), fill = el('div', 'udFill'); bar.appendChild(fill); d.body.appendChild(bar);
    let cancelled = false;
    const cancel = btn(d.btns, t('word.cancel', 'キャンセル'), '', () => { cancelled = true; cancel.disabled = true; post('cancel').catch(() => {}); });
    const fail = text => { closeDlg(); info(t('upd.failTitle', '更新できませんでした'), text, true); };
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

  // ---- 起動時（exe 版・環境設定で ON の時だけ。失敗は何も出さない）----
  async function autoCheck() {
    let st;
    try { st = await post('status'); } catch (_) { return; }
    if (st.justUpdated) showOk(tf('upd.done', '{v} に更新しました', { v: st.justUpdated.to }));
    if (!st.frozen || lsGet(CHECK_KEY) === '0') return;
    let j;
    try { j = await post('check'); } catch (_) { return; }
    if (!j || !j.ok || !j.newer) return;
    const skipped = lsGet(SKIP_KEY);
    if (skipped && !vgt(j.latest, skipped)) return;   // 「更新しない」にした版（とそれ以前）は出さない
    if (document.getElementById('updDlgBg')) return;
    prompt(j);
  }

  // ---- メニューの「更新を確認…」（記録した版も出す。結果は必ず表示）----
  async function manualCheck() {
    const d = openDlg(t('upd.checkTitle', '更新の確認'), true);
    d.body.appendChild(el('div', 'udMsg', t('upd.checking', '確認しています…')));
    let j;
    try { j = await post('check'); } catch (e) { return info(t('upd.checkTitle', '更新の確認'), String(e && e.message || e), true); }
    if (!j.ok) return info(t('upd.checkTitle', '更新の確認'), errText(j), true);
    if (!j.newer) return info(t('upd.checkTitle', '更新の確認'), tf('upd.upToDate', '最新のバージョンです（{v}）。', { v: j.current }));
    prompt(j);
  }

  return { autoCheck, manualCheck, isOn: () => lsGet(CHECK_KEY) !== '0', setOn: on => lsSet(CHECK_KEY, on ? '1' : '0') };
}

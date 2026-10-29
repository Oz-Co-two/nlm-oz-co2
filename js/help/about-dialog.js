// 「NLM について」の画面（ヘルプのメニュー・2026-10-28）。#dirtyDlg の様式（見た目は css/help.css）。
// 版・原作者の表記・ライセンス（GPLv3 の適切な法的告知＝著作権の表示・無保証・ライセンスの案内）・取り込み済みのプラグインの版を出す。
// ページ・ライセンスの文書を開くのは serve.py の /__help/*（JS が渡すのは決まった名前だけ。URL・パスは Python 側に固定）。
// 文字はすべて textContent で入れる（プラグインの版はファイル由来）。
export function openAbout({ t, version, lang, post, plugins, showErr }) {
  if (document.querySelector('#dirtyDlg[data-dlg=about]')) return;   // 2重に出さない
  const mk = (tag, cls, text) => { const e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; };
  const bg = mk('div'); bg.id = 'dirtyDlgBg';
  const dlg = mk('div', 'about'); dlg.id = 'dirtyDlg'; dlg.dataset.dlg = 'about'; bg.appendChild(dlg);

  const head = mk('div', 'abHead');
  head.append(mk('span', 'abName', 'Non-Linear Mapper'), mk('span', 'abVer', version));
  dlg.append(head, mk('div', 'abLead', t('about.lead', 'Beat Saber の譜面エディタです。\nhelba さんの Non-Linear Mapper を元にした Oz-Co2版（派生版）です。')));

  // 開く物は名前だけを送る（serve.py の HELP_DOCS・HELP_FILES）。失敗は種類で返る
  const open = async (path, body) => {
    try { const j = await post(path, { ...body, lang: lang() }); if (!j || !j.ok) throw new Error(j && j.error || 'failed'); }
    catch (e) { showErr(t('about.openFail', '開けませんでした') + (e && e.message === 'missing' ? t('about.missing', '（ファイルが見つかりません）') : '')); }
  };
  const linkBtn = (label, path, body) => {
    const b = mk('button', 'abLink', label + ' ↗'); b.type = 'button'; b.title = t('menu.extTip', 'ブラウザで開きます');
    b.addEventListener('click', () => open(path, body)); return b;
  };
  const links = mk('div', 'abRow');
  links.append(linkBtn(t('about.original', '原作のページ'), '__help/open', { doc: 'original' }),
    linkBtn(t('about.home', 'Oz-Co2版のページ（GitHub）'), '__help/open', { doc: 'home' }));
  dlg.append(links);

  const lic = mk('div', 'abSec');
  lic.append(mk('div', 'abCopy', 'Copyright (C) 2026 helba (original author)\nCopyright (C) 2026 Oz-Co2 (modifications and additions)'),
    mk('div', 'abText', t('about.license', 'このプログラムはフリーソフトウェアです。GNU General Public License 第3版（またはそれ以降の版）の条件のもとで、再配布・改変できます。')),
    mk('div', 'abText', t('about.warranty', 'このプログラムは無保証です。商品性や特定の目的への適合性についての保証もありません。詳しくはライセンスの本文を見てください。')));
  const files = mk('div', 'abRow');
  for (const [name, label] of [['license', t('about.licBtn', 'ライセンス（GPLv3）')], ['notices', t('about.noticeBtn', '第三者のライセンス')]]) {
    const b = mk('button', 'abFile', label); b.type = 'button'; b.dataset.file = name;
    b.title = t('about.fileTip', 'メモ帳で開きます');
    b.addEventListener('click', () => open('__help/openFile', { name }));
    files.appendChild(b);
  }
  lic.appendChild(files);
  dlg.appendChild(lic);

  // 取り込み済みのプラグイン（PC の中の確認だけ＝GitHub へは通信しない）
  const pl = mk('div', 'abSec');
  pl.appendChild(mk('div', 'abSub', t('about.plugins', '追加プラグイン')));
  for (const p of plugins) {
    const row = mk('div', 'abPl'); row.dataset.pl = p.id;
    const val = mk('span', 'abPlVer', '…');
    row.append(mk('span', 'abPlName', p.name()), val);
    pl.appendChild(row);
    p.client.ensureStatus().then(() => {
      const cur = p.client.state.st && p.client.state.st.current;
      val.textContent = cur ? 'v' + String(cur).slice(0, 20) : t('about.notInstalled', '取り込んでいません');
      val.classList.toggle('none', !cur);
    }).catch(() => { val.textContent = '—'; });
  }
  dlg.appendChild(pl);

  const btns = mk('div', 'ddBtns');
  const close = mk('button', 'pri', t('about.close', '閉じる')); close.type = 'button';
  btns.appendChild(close); dlg.appendChild(btns);
  const done = () => { removeEventListener('keydown', onKey, true); bg.remove(); };
  close.addEventListener('click', done);
  const onKey = e => { if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); done(); return; } e.stopPropagation(); };   // 裏のショートカットを発火させない
  addEventListener('keydown', onKey, true);
  document.body.appendChild(bg);
  close.focus();
}

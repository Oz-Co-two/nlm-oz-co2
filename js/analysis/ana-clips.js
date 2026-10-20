// 解析からクリップを作る（2026-10-19）の確認の画面。状態（クリップ・レーン・難易度・リンク・履歴）は editor-app.js（anaOpenClips/anaMakeClips）が持ち、
// ここは DOM を作って選んだ結果を返すだけ。見た目は他の確認の画面と同じ #dirtyDlg（一覧の様式はリンクの画面の .lkOpt を使う）。
// 選ぶ物: 単位（セクション＝既定／細かい区切り／両方。両方の時は単独編集にするレーン＝既定はセクション）・作る難易度（開いている難易度は必ず）・
// 同じ番号のクリップを自動でリンク（既定オン）。クリップ名（帯で付け直した名前）は他人のファイル由来なので textContent だけで組み立てる。

const mkEl = (tag, cls, text) => { const e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; };

/** 区間の一覧の数: n=区間の数・kinds=番号（グループ）の数・multi=2回以上ある番号の数・ex=1つ目の名前 */
function statOf(list) {
  const by = new Map();
  for (const it of list) by.set(it.key, (by.get(it.key) || 0) + 1);
  return { n: list.length, kinds: by.size, multi: [...by.values()].filter(c => c >= 2).length, ex: list.length ? list[0].name : '' };
}

/**
 * opts: {t, tf, src:{sections, segments}（song-analysis.js の clipSource）, diffs:[{dk, label, cur, empty, n}], free:足せるノーツのレーンの数}
 * 戻り値 Promise<null | {unit:'sec'|'seg'|'both', eo:'sec'|'seg', diffs:[dk…]（開いている難易度を含む）, link:bool}>
 */
export function anaClipsDialog(opts) {
  const { t, tf, src, diffs, free } = opts;
  const st = { sec: statOf(src.sections || []), seg: statOf(src.segments || []) };
  return new Promise(res => {
    const bg = mkEl('div'); bg.id = 'dirtyDlgBg';
    const dlg = mkEl('div', 'anaClips'); dlg.id = 'dirtyDlg'; dlg.dataset.ana = 'clips'; bg.appendChild(dlg);
    dlg.appendChild(mkEl('div', 'ddMsg lkTitle', t('ana.c.title', '解析からクリップを作る')));
    dlg.appendChild(mkEl('div', 'ddMsg lkLine', t('ana.c.body', '新しいノーツのレーンを一番上に足し、帯の区間どおりに空のクリップを作ります。今あるノーツ・レーンには触りません。作った後、そのレーンを単独編集にします。')));
    const opt = (type, name, value, main, sub, warn, dis) => {
      const lab = mkEl('label', 'lkOpt' + (dis ? ' dis' : ''));
      const inp = document.createElement('input'); inp.type = type; inp.name = name; inp.value = value; inp.disabled = !!dis;
      const body = mkEl('span', 'lkOptBody');
      body.appendChild(mkEl('span', 'lkOptMain', main));
      if (sub) body.appendChild(mkEl('span', 'lkOptSub', sub));
      if (warn) body.appendChild(mkEl('span', 'lkOptWarn', warn));
      lab.append(inp, body); return { lab, inp };
    };
    // ---- 単位 ----
    dlg.appendChild(mkEl('div', 'acHead', t('ana.c.unit', '作る単位')));
    const ub = mkEl('div', 'lkOpts'); dlg.appendChild(ub);
    const hasSec = st.sec.n > 0, hasSeg = st.seg.n > 0, bothOk = hasSec && hasSeg && free >= 2;
    const units = {
      sec: opt('radio', 'acUnit', 'sec', tf('ana.c.uSec', 'セクション（{n}個・番号 {k}種類）', { n: st.sec.n, k: st.sec.kinds }),
        hasSec ? tf('ana.c.uSecSub', 'クリップ名＝名前＋番号（例「{ex}」）・同じ番号は同じ色', { ex: st.sec.ex }) : '', hasSec ? '' : t('ana.c.none', '結果にありません'), !hasSec),
      seg: opt('radio', 'acUnit', 'seg', tf('ana.c.uSeg', '細かい区切り（{n}個・グループ {k}種類）', { n: st.seg.n, k: st.seg.kinds }),
        hasSeg ? tf('ana.c.uSegSub', 'クリップ名＝グループ名（例「{ex}」）・同じグループは同じ色', { ex: st.seg.ex }) : '', hasSeg ? '' : t('ana.c.none', '結果にありません'), !hasSeg),
      both: opt('radio', 'acUnit', 'both', t('ana.c.uBoth', '両方（それぞれ別の新しいレーンに）'),
        t('ana.c.uBothSub', '上のレーン＝セクション・その下＝細かい区切り'),
        hasSec && hasSeg && free < 2 ? tf('ana.c.laneShort', 'ノーツのレーンが足りません（上限 {max}本・あと {n}本）', { max: opts.max || 10, n: free }) : '', !bothOk),
    };
    for (const k of ['sec', 'seg', 'both']) ub.appendChild(units[k].lab);
    (hasSec ? units.sec : units.seg).inp.checked = true;
    // 両方の時: 単独編集にするレーン（打つ方）
    const eoRow = mkEl('div', 'acEo');
    eoRow.appendChild(mkEl('span', 'acEoLbl', t('ana.c.eo', '単独編集にするレーン（打つ方）:')));
    const eo = {};
    for (const [k, label] of [['sec', t('ana.c.eoSec', 'セクション')], ['seg', t('ana.c.eoSeg', '細かい区切り')]]) {
      const lab = mkEl('label', 'acEoOpt'); const inp = document.createElement('input'); inp.type = 'radio'; inp.name = 'acEo'; inp.value = k;
      inp.checked = k === 'sec'; lab.append(inp, mkEl('span', '', label)); eoRow.appendChild(lab); eo[k] = inp;
    }
    ub.appendChild(eoRow);
    // ---- 難易度 ----
    dlg.appendChild(mkEl('div', 'acHead', t('ana.c.diffs', '作る難易度')));
    const db = mkEl('div', 'acDiffs'); dlg.appendChild(db);
    const dchk = [];
    for (const d of diffs) {
      const lab = mkEl('label', 'acDiff' + (d.cur ? ' cur' : ''));
      const inp = document.createElement('input'); inp.type = 'checkbox'; inp.className = 'acDiffChk'; inp.dataset.dk = d.dk;
      inp.checked = !!d.cur; inp.disabled = !!d.cur;
      const sub = d.cur ? t('ana.c.dCur', '開いている難易度') : d.empty || !d.n ? t('ana.c.dEmpty', '空') : tf('ana.c.dNotes', 'ノーツ {n}', { n: d.n });
      lab.title = d.cur ? t('ana.c.dCurTip', '開いている難易度には必ず作ります') : '';
      lab.append(inp, mkEl('span', 'acDiffName', d.label), mkEl('span', 'acDiffSub', sub));
      db.appendChild(lab); dchk.push({ d, inp });
    }
    // ---- リンク ----
    dlg.appendChild(mkEl('div', 'acHead', t('ana.c.link', 'リンク')));
    const lb = mkEl('div', 'lkOpts'); dlg.appendChild(lb);
    const lk = opt('checkbox', 'acLink', 'link', t('ana.c.linkMain', '同じ番号のクリップを自動でリンクする'),
      t('ana.c.linkSub', '親＝各番号の一番先頭のクリップ（開いている難易度）。子は親と同じ中身になり、打てません（編集は親で行います）。他の難易度に作った分も、この親に繋ぎます。'));
    lk.inp.id = 'acLink'; lk.inp.checked = true; lb.appendChild(lk.lab);
    const warn = mkEl('div', 'ddMsg lkNote acWarn', t('lk.parentHint', '親を編集すると、繋いだ全部（他の難易度も）に反映されます。'));
    dlg.appendChild(warn);
    const sum = mkEl('div', 'ddMsg acSum'); dlg.appendChild(sum);
    // ---- 選んだ物に合わせて表示を直す ----
    const unitNow = () => (units.both.inp.checked ? 'both' : units.seg.inp.checked ? 'seg' : 'sec');
    const pickedDiffs = () => dchk.filter(x => x.inp.checked).map(x => x.d.dk);
    function sync() {
      const u = unitNow(), both = u === 'both';
      eoRow.classList.toggle('dis', !both);
      for (const k in eo) eo[k].disabled = !both;
      const kinds = both ? ['sec', 'seg'] : [u], nd = Math.max(1, pickedDiffs().length);
      const per = kinds.reduce((a, k) => a + st[k].n, 0);
      const links = lk.inp.checked ? kinds.reduce((a, k) => a + (nd >= 2 ? st[k].kinds : st[k].multi), 0) : 0;
      warn.style.display = links > 0 ? '' : 'none';
      sum.textContent = tf('ana.c.sum', '作る物: 新しいノーツのレーン {lanes}本・クリップ {n}個 × {d}難易度・{links}',
        { lanes: kinds.length, n: per, d: nd, links: links > 0 ? tf('ana.c.sumLinks', 'リンク {k}組', { k: links }) : t('ana.c.sumNoLink', 'リンクなし') });
    }
    dlg.addEventListener('change', sync);
    sync();
    // ---- ボタン ----
    const btns = mkEl('div', 'ddBtns'); dlg.appendChild(btns);
    const done = v => { removeEventListener('keydown', onKey, true); bg.remove(); res(v); };
    const ok = mkEl('button', 'pri', t('ana.c.ok', '作る')); ok.dataset.v = 'ok';
    const cancel = mkEl('button', '', t('word.cancel', 'キャンセル')); cancel.dataset.v = 'cancel';
    ok.addEventListener('click', () => {
      const u = unitNow();
      done({ unit: u, eo: u === 'both' ? (eo.seg.checked ? 'seg' : 'sec') : u, diffs: pickedDiffs(), link: lk.inp.checked });
    });
    cancel.addEventListener('click', () => done(null));
    btns.append(ok, cancel);
    const onKey = e => {
      if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); done(null); }
      else if (e.key === 'Enter') { e.preventDefault(); e.stopPropagation(); ok.click(); }
      else e.stopPropagation();   // 裏のショートカットを発火させない
    };
    addEventListener('keydown', onKey, true);
    document.body.appendChild(bg);
    ok.focus();
  });
}

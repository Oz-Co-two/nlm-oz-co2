// 審査の指摘の画面（2026-10-27）: 浮きパネルの一覧（#rvPanel）・読み込みの確認・貼り付け・書き出しの画面。
// 状態（読み込んだ指摘・済みの印・返事）はここが持ち、プロジェクトの保存・未保存の判定・履歴（'review'）・タイムラインの印・飛ぶ処理は
// editor-app.js が api で繋ぐ（CLAUDE.md「審査の指摘の .txt を読む・書き出す」）。読む・書く形は review-txt.js、保存の形は review-data.js。
// 指摘の文・見出しの名前・ファイル名は他人のファイル由来なので、DOM は createElement＋textContent だけで組み立てる（innerHTML を使わない）。
import { decodeReviewBytes, parseReviewText, formatReviewText, formatBeat, REVIEW_DIFFS, REVIEW_LIMITS } from './review-txt.js';
import { RV_VERSION, RV_LIMITS, importParsed, sanitizeReview, unknownGroups, parsedStats, spotsOf, writtenSpotsOf, jumpable,
  toFormatItems, toFormatNotes, checksToItems } from './review-data.js';
import { runMapCheck } from '../mapcheck/mapcheck.js';
import { runBlCriteria } from '../mapcheck/blcriteria.js';
import { blView } from '../mapcheck/blcriteria-view.js';

const mkEl = (tag, cls, text) => { const e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; };
const DIFF_ORDER = ['ExpertPlus', 'Expert', 'Hard', 'Normal', 'Easy'];
const MAX_FILES = 20;
// NLM の確かめの結果の書き出しの1行目（英語・審査の人向け。数を入れない＝AutoModder の取り込みは数を含む行を指摘として読む）
const CHECK_HEADER = 'NLM check results (BeatLeader ranking criteria as read by NLM). Not an official BeatLeader or BS Map Check result.';
// 読み方の注意（parseReviewText の warnings の code）
const WARN_JA = {
  'too-large': '大きすぎるため、途中までだけ読みました', 'too-many-lines': '行が多すぎるため、途中までだけ読みました',
  'line-too-long': '長すぎる行を途中で切りました', 'too-many-items': '指摘が多すぎるため、途中までだけ読みました',
  'heading-guess': 'コロンで終わる行を難易度の見出しと推測しました', 'heading-e': '「E」だけの見出しを Expert と読みました',
  'label-override': '譜面の難易度の名前の表で読みました（標準の名前とは違う難易度です）', 'unknown-label': '知らない難易度の名前の見出しです',
  'other-mode': 'Standard 以外のモードの見出しです（NLM の対象外）', 'unreadable': '拍として読めない行です（拍の無い行に入れました）',
  'file-name-differs': 'ファイル名と中の見出しで難易度が違います（中の見出しで読みました）',
};
const SEV_JA = { X: 'ランク不可（Unrankable）', '?': '要確認（Questionable）', S: '提案（Suggestion）', N: 'メモ（Note）' };
// 一覧の文字の大きさ（指摘の文の px。2026-10-27・利用者の要望）: 件数の行の左端のスライダーと、一覧の上の Ctrl＋ホイール（MEDIA の詳細表示と同じ使い方）。
// 他の部品・パネルの幅は CSS の --rv-fs からの比率（css/review.css）。保存は環境設定と同じ bsnm_rvFont（無ければ RV_FONT_DEF。config/settings.json へ自動でミラー）。
// プロジェクトには入れない＝未保存の判定・履歴とは関係しない
export const RV_FONT_MIN = 11, RV_FONT_MAX = 20, RV_FONT_DEF = 14;
const LS_FONT = 'bsnm_rvFont';
const lsGet = k => { try { return localStorage.getItem(k); } catch (_) { return null; } };
const lsSet = (k, v) => { try { localStorage.setItem(k, v); } catch (_) {} };

export function installReviewPanel(api) {
  const { t, tf, dispDiff } = api;
  let data = { items: [], notes: [], srcs: [] };
  let seq = 0;                 // 項目・取り込みの id の番号（r1・s2 …）
  let el = null, curId = null, filt = 'all', hideDone = false, lastMsg = { text: '', kind: '' };
  const jumpRes = new Map();   // 項目 → 最後に飛んだ結果（'exact'|'near'|'none'|'light'）。保存しない
  let fileInp = null, enDict = null;
  let fontPx = (() => { const v = +lsGet(LS_FONT); return v >= RV_FONT_MIN && v <= RV_FONT_MAX ? Math.round(v) : RV_FONT_DEF; })();

  // ---------------------------------------------------------------- 状態
  const byId = id => data.items.find(x => x.id === id) || null;
  const isEmpty = () => !data.items.length && !data.notes.length;
  function bumpSeq() {
    let m = 0;
    for (const x of [...data.items, ...data.srcs]) { const n = parseInt(String(x.id).slice(1), 10); if (n > m) m = n; }
    seq = Math.max(seq, m);
  }
  /** 保存する中身（無ければ undefined＝キーごと書かない）。projSig と履歴も同じ物 */
  function save() { return isEmpty() ? undefined : { v: RV_VERSION, items: data.items, notes: data.notes, srcs: data.srcs }; }
  /** 開いた時・Undo（'review'）: 中身はファイル由来なので review-data.js の sanitizeReview で確かめる */
  function load(v) {
    const s = sanitizeReview(v);
    data = s || { items: [], notes: [], srcs: [] };
    bumpSeq();
    if (curId && !byId(curId)) curId = null;
    for (const id of [...jumpRes.keys()]) if (!byId(id)) jumpRes.delete(id);
    render();
  }
  function reset() { data = { items: [], notes: [], srcs: [] }; curId = null; jumpRes.clear(); lastMsg = { text: '', kind: '' }; render(); }
  const changed = () => { api.dirty(); };

  // ---------------------------------------------------------------- 表示の文
  const diffName = d => (d ? dispDiff(d) : t('rv.diffUnknown', '難易度が分からない'));
  const spotText = s => (s.b == null ? formatBeat(s.a) : `${formatBeat(s.a)}-${formatBeat(s.b)}`);
  const beatsText = x => writtenSpotsOf(x).map(spotText).join(', ');
  const nlmText = x => (x.nlmBeats ? spotsOf(x).map(spotText).join(', ') : '');
  const srcName = id => { const s = data.srcs.find(q => q.id === id); return s ? (s.name || t('rv.pasted', '貼り付けた文')) : ''; };
  function tipOf(id) {
    const x = byId(id); if (!x) return '';
    const head = beatsText(x) + (x.nlmBeats ? ` (NLM ${nlmText(x)})` : '');
    const tx = x.text.length > 120 ? x.text.slice(0, 119) + '…' : x.text;
    return `${t('rv.markTip', '審査の指摘')} ${head}: ${tx}`;
  }
  function setMsg(text, kind = '') {
    lastMsg = { text, kind };
    if (el) { const m = el.querySelector('.rvMsg'); m.textContent = text; m.className = 'rvMsg' + (kind ? ' ' + kind : ''); }
  }

  // ---------------------------------------------------------------- パネル
  function build() {
    el = mkEl('div'); el.id = 'rvPanel';
    const head = mkEl('div', 'rvHead');
    head.append(mkEl('span', 'rvTitle'));
    const btns = mkEl('span', 'rvHeadBtns');
    const bLoad = mkEl('button', 'rvLoad'), bPaste = mkEl('button', 'rvPaste'), bExp = mkEl('button', 'rvExport'), bClose = mkEl('button', 'rvClose', '✕');
    bClose.setAttribute('aria-label', 'close');
    btns.append(bLoad, bPaste, bExp, bClose); head.append(btns);
    const sum = mkEl('div', 'rvSum');
    const cnt = mkEl('span', 'rvCnt');
    const fsel = document.createElement('select'); fsel.className = 'rvFilt';
    const hd = mkEl('label', 'rvHideDone'); const hdc = document.createElement('input'); hdc.type = 'checkbox'; hdc.className = 'rvHideChk';
    hd.append(hdc, mkEl('span', 'rvHideTxt'));
    const fg = mkEl('span', 'rvFsGrp'), fi = mkEl('span', 'rvFsIco', 'Aa'); fi.setAttribute('aria-hidden', 'true');
    const fr = document.createElement('input'); fr.type = 'range'; fr.className = 'rvFs';
    fr.min = String(RV_FONT_MIN); fr.max = String(RV_FONT_MAX); fr.step = '1'; fr.value = String(fontPx);
    fg.append(fi, fr);
    sum.append(fg, cnt, fsel, hd);
    el.append(head, sum, mkEl('div', 'rvMsg'), mkEl('div', 'rvBody'), mkEl('div', 'rvFoot'));
    document.body.appendChild(el);
    applyFont();
    // 文字の大きさ: ドラッグ中（input）は画面の右へはみ出しても寄せない（寄せるとつまみが指から逃げて値が行き来する）。離した時（change）に寄せる。
    // マウスで動かした後はフォーカスを外す（入力欄にフォーカスがあると Space 等のショートカットが効かない）
    fr.addEventListener('input', () => setFont(fr.value));
    fr.addEventListener('change', keepInView);
    fr.addEventListener('pointerup', () => fr.blur());
    let wheelAcc = 0;   // タッチパッドの細かい量はためて 1 段ずつ（lib-table.js と同じ）
    el.addEventListener('wheel', ev => {
      if (!ev.ctrlKey) return;
      ev.preventDefault();   // ページの拡大にしない
      wheelAcc += ev.deltaMode === 0 ? ev.deltaY : ev.deltaY * 40;
      if (Math.abs(wheelAcc) < 40) return;
      const step = wheelAcc < 0 ? 1 : -1; wheelAcc = 0;
      setFont(fontPx + step); keepInView();
    }, { passive: false });
    bClose.addEventListener('click', close);
    bLoad.addEventListener('click', () => openFile());
    bPaste.addEventListener('click', () => openPaste());
    bExp.addEventListener('click', () => exportDialog());
    fsel.addEventListener('change', () => { filt = fsel.value; render(); });
    hdc.addEventListener('change', () => { hideDone = hdc.checked; render(); });
    const body = el.querySelector('.rvBody');
    body.addEventListener('click', ev => {
      if (ev.target.closest('input,textarea,select,.rvDoneLab')) return;
      const row = ev.target.closest('.rvItem'); if (!row) return;
      const x = byId(row.dataset.id); if (!x) return;
      const chip = ev.target.closest('.rvBeat');
      jumpTo(x, chip ? +chip.dataset.k : null);
    });
    body.addEventListener('change', ev => {
      const row = ev.target.closest('.rvItem'); const x = row && byId(row.dataset.id); if (!x) return;
      if (ev.target.classList.contains('rvDone')) {
        api.snapshot(); x.done = ev.target.checked; changed(); render(); return;
      }
      if (ev.target.classList.contains('rvReply')) {
        const v = ev.target.value.replace(/[\r\n]+/g, ' ').slice(0, RV_LIMITS.reply);
        if (v !== x.reply) { api.snapshot(); x.reply = v; changed(); }
      }
    });
    body.addEventListener('keydown', ev => {
      if (!ev.target.classList.contains('rvReply')) return;
      if (ev.key === 'Enter') { ev.preventDefault(); ev.target.blur(); }
      else if (ev.key === 'Escape') { const row = ev.target.closest('.rvItem'), x = row && byId(row.dataset.id); if (x) ev.target.value = x.reply; ev.target.blur(); }
    });
    el.querySelector('.rvFoot').addEventListener('click', ev => { if (ev.target.closest('.rvClear')) clearAsk(); });
    // 見出しをつかんで移動（画面外へは出さない・譜面チェックのパネルと同じ）
    head.addEventListener('pointerdown', ev => {
      if (ev.target.closest('button')) return;
      const r0 = el.getBoundingClientRect(), dx = ev.clientX - r0.left, dy = ev.clientY - r0.top;
      head.setPointerCapture(ev.pointerId);
      const mv = e => {
        el.style.left = Math.max(0, Math.min(innerWidth - 80, e.clientX - dx)) + 'px';
        el.style.top = Math.max(0, Math.min(innerHeight - 40, e.clientY - dy)) + 'px'; el.style.right = 'auto';
      };
      const up = () => { head.removeEventListener('pointermove', mv); head.removeEventListener('pointerup', up); };
      head.addEventListener('pointermove', mv); head.addEventListener('pointerup', up);
    });
  }

  // ---------------------------------------------------------------- 文字の大きさ
  function setFont(v) {
    v = Math.max(RV_FONT_MIN, Math.min(RV_FONT_MAX, Math.round(+v || RV_FONT_DEF)));
    if (v === fontPx) return;
    fontPx = v; lsSet(LS_FONT, String(v));
    applyFont();
  }
  /** --rv-fs を入れる。一番上に見えていた行は同じ高さに残す（大きくすると下の行が押し下げられ、読んでいた所を見失うため） */
  function applyFont() {
    if (!el) return;
    const body = el.querySelector('.rvBody'), top = () => body.getBoundingClientRect().top;
    const anchor = body.scrollTop > 0 ? [...body.querySelectorAll('summary,.rvItem,.rvNote')].find(r => r.getBoundingClientRect().bottom > top() + 1) : null;
    const off = anchor ? anchor.getBoundingClientRect().top - top() : 0;
    el.style.setProperty('--rv-fs', fontPx + 'px');
    if (anchor) body.scrollTop += anchor.getBoundingClientRect().top - top() - off;
    const fr = el.querySelector('.rvFs');
    if (fr && +fr.value !== fontPx) fr.value = String(fontPx);
  }
  /** 幅が広がって画面の右からはみ出すなら左へ寄せる（見出しで右へ動かした後）。#rvPanel は body の直下で UI文字サイズの zoom が掛からない＝
   *  getBoundingClientRect の px をそのまま style.left に入れてよい */
  function keepInView() {
    if (!isOpen()) return;
    const r = el.getBoundingClientRect();
    if (r.right > innerWidth - 8) el.style.left = Math.max(0, innerWidth - 8 - r.width) + 'px';
  }

  /** 一覧に出す項目（絞り込み・済みを隠す） */
  function visible(x) {
    if (hideDone && x.done && x.id !== curId) return false;
    if (filt === 'all') return true;
    if (filt === 'cur') return x.difficulty && x.difficulty === api.curDiff();
    return x.difficulty === filt && x.mode === 'Standard';
  }
  /** 一覧の区分: 難易度ごと（難しい方から）→難易度が分からない→Standard 以外 */
  function sectionsOf() {
    const secs = [];
    for (const d of DIFF_ORDER) { const its = data.items.filter(x => x.difficulty === d && x.mode === 'Standard'); if (its.length) secs.push({ key: d, d, items: its }); }
    const unk = data.items.filter(x => !x.difficulty && x.mode === 'Standard'); if (unk.length) secs.push({ key: 'unknown', d: null, items: unk });
    const oth = data.items.filter(x => x.mode !== 'Standard'); if (oth.length) secs.push({ key: 'other', d: null, other: true, items: oth });
    return secs;
  }

  function rowEl(x) {
    const row = mkEl('div', 'rvItem' + (x.done ? ' done' : '') + (x.id === curId ? ' cur' : '') + (x.parent ? ' child' : '') + (jumpable(x) ? '' : ' nojump'));
    row.dataset.id = x.id;
    if (x.severity) row.classList.add('sev-' + (x.severity === '?' ? 'q' : x.severity));
    row.title = `${srcName(x.src)}${x.line ? ' L' + x.line : ''}`;
    const line = mkEl('div', 'rvLine');
    const dl = mkEl('label', 'rvDoneLab'); dl.title = t('rv.doneTip', '済み（直した・確かめた）の印。書き出しの「fixed」にも使えます');
    const dc = document.createElement('input'); dc.type = 'checkbox'; dc.className = 'rvDone'; dc.checked = x.done;
    dl.append(dc); line.append(dl);
    if (x.severity) { const s = mkEl('span', 'rvSev', x.severity); s.title = t('rv.sev.' + (x.severity === '?' ? 'q' : x.severity), SEV_JA[x.severity]); line.append(s); }
    const bs = mkEl('span', 'rvBeats');
    const ws = writtenSpotsOf(x), ns = spotsOf(x);
    ws.forEach((s, k) => {
      const c = mkEl('span', 'rvBeat', spotText(s)); c.dataset.k = String(k);
      if (x.nlmBeats) c.title = tf('rv.c3Tip', '元の譜面の拍 {o} ＝ NLM の拍 {n}', { o: spotText(s), n: spotText(ns[k]) });
      bs.append(c);
    });
    if (x.repeats) { const r = mkEl('span', 'rvFlag', '…'); r.title = t('rv.fRepeats', '「など」「繰り返し」と書かれています（全部の位置は書かれていません）'); bs.append(r); }
    line.append(bs);
    if (x.nlmBeats) { const n = mkEl('span', 'rvNlm', tf('rv.nlmAt', '→ NLM {beats}', { beats: nlmText(x) })); n.title = t('rv.nlmTip', 'この難易度は「曲データを読み込む」で拍を付け替えたため、元の譜面の拍を NLM の拍に直しました'); line.append(n); }
    if (x.ambiguous) { const a = mkEl('span', 'rvFlag amb', t('rv.fAmbShort', '範囲?')); a.title = t('rv.fAmb', '「a - b 文」を範囲と読みました（区切りの「-」かもしれません）'); line.append(a); }
    if (x.sameAsPrev) { const s = mkEl('span', 'rvFlag', '↑'); s.title = t('rv.fSame', '前の指摘と同じ（^・same）'); line.append(s); }
    const res = jumpRes.get(x.id);
    if (res === 'near' || res === 'none') {
      const r = mkEl('span', 'rvRes ' + res, res === 'near' ? '≈' : '⚠');
      r.title = res === 'near' ? t('rv.resNear', 'ちょうどの拍には物が無く、近い物を選びました') : t('rv.resNone', '物が見つかりませんでした（古い指摘かもしれません）');
      line.append(r);
    }
    row.append(line);
    if (x.text) row.append(mkEl('div', 'rvText', x.text));
    for (const c of x.cont) row.append(mkEl('div', 'rvCont', c));
    if (x.groupText) row.append(mkEl('div', 'rvCont rvGrp', tf('rv.groupText', '（まとめて）{text}', { text: x.groupText })));
    // 返事の欄: 選んでいる行と、返事のある行だけ（全部の行に欄を出すと一覧が長くなる）
    if (x.id === curId || x.reply) {
      const rp = document.createElement('input'); rp.type = 'text'; rp.className = 'rvReply'; rp.value = x.reply; rp.maxLength = RV_LIMITS.reply;
      rp.placeholder = t('rv.replyPh', '返事（書き出しで「 - 返事」として行の後ろに足します）');
      row.append(rp);
    }
    return row;
  }

  function render() {
    if (!el) return;
    el.querySelector('.rvTitle').textContent = t('rv.title', '📝 審査の指摘');
    el.querySelector('.rvLoad').textContent = t('rv.load', '読み込む…');
    el.querySelector('.rvLoad').title = t('rv.loadTip', '審査の人の .txt（「拍 - 文」）を読み込みます（難易度ごとのファイルを一度に選べます）');
    el.querySelector('.rvPaste').textContent = t('rv.paste', '貼り付け…');
    el.querySelector('.rvPaste').title = t('rv.pasteTip', 'Discord の本文（指摘）を貼り付けて読みます');
    el.querySelector('.rvExport').textContent = t('rv.export', '書き出す…');
    el.querySelector('.rvExport').title = t('rv.exportTip', '返事を付けた指摘・NLM の確かめの結果を、指摘と同じ形の .txt にします');
    const done = data.items.filter(x => x.done).length;
    el.querySelector('.rvCnt').textContent = data.items.length ? tf('rv.total', '{n}件・済み {d}', { n: data.items.length, d: done }) : '';
    const fsel = el.querySelector('.rvFilt');
    const opts = [['all', t('rv.fAll', 'すべての難易度')], ['cur', t('rv.fCur', '今の難易度')],
      ...DIFF_ORDER.filter(d => data.items.some(x => x.difficulty === d && x.mode === 'Standard')).map(d => [d, dispDiff(d)])];
    if (!opts.some(o => o[0] === filt)) filt = 'all';
    fsel.replaceChildren(...opts.map(([v, l]) => { const o = mkEl('option', '', l); o.value = v; return o; }));
    fsel.value = filt;
    el.querySelector('.rvHideChk').checked = hideDone;
    el.querySelector('.rvHideTxt').textContent = t('rv.hideDone', '済みを隠す');
    const fsTip = t('rv.fontSize', '指摘の文字の大きさ（一覧の上で Ctrl＋ホイールでも変えられます）');
    el.querySelector('.rvFsGrp').title = fsTip; el.querySelector('.rvFs').setAttribute('aria-label', fsTip);
    el.querySelector('.rvSum').style.display = data.items.length ? '' : 'none';
    setMsg(lastMsg.text, lastMsg.kind);
    // 本体
    const body = el.querySelector('.rvBody'), sc = body.scrollTop;
    const opened = new Map([...body.querySelectorAll('details.rvSec')].map(x => [x.dataset.key, x.open]));
    const parts = [];
    if (isEmpty()) {
      const e = mkEl('div', 'rvEmpty');
      e.append(mkEl('div', '', t('rv.empty', 'まだ指摘を読み込んでいません。')),
        mkEl('div', 'rvEmptySub', t('rv.emptySub', '［読み込む…］で審査の人の .txt を、［貼り付け…］で Discord の本文を読み込みます。読み込んだ指摘はタイムラインの拍の帯に印が付き、行をクリックするとその位置へ移動します。')));
      parts.push(e);
    }
    for (const s of sectionsOf()) {
      const vis = s.items.filter(visible); if (!vis.length) continue;
      const det = mkEl('details', 'rvSec' + (s.other ? ' other' : s.d ? '' : ' unknown')); det.dataset.key = s.key; det.open = opened.has(s.key) ? opened.get(s.key) : !s.other;
      const su = mkEl('summary');
      su.append(mkEl('span', 'rvSecName', s.other ? t('rv.secOther', 'Standard 以外（NLM の対象外・飛べません）') : s.d ? dispDiff(s.d) : t('rv.secUnknown', '難易度が分からない（飛べません）')));
      const nd = s.items.filter(x => x.done).length;
      su.append(mkEl('span', 'rvSecCnt', tf('rv.secCnt', '{n}件・済み {d}', { n: s.items.length, d: nd })));
      if (s.items.some(x => x.nlmBeats)) { const b = mkEl('span', 'rvSecC3', t('rv.secC3', '元の拍→NLM の拍')); b.title = t('rv.nlmTip', 'この難易度は「曲データを読み込む」で拍を付け替えたため、元の譜面の拍を NLM の拍に直しました'); su.append(b); }
      det.append(su);
      for (const x of vis) {
        const r = rowEl(x);
        if (s.other) { const m = mkEl('span', 'rvMode', `${x.mode} ${diffName(x.difficulty)}`); r.querySelector('.rvLine').append(m); }
        det.append(r);
      }
      parts.push(det);
    }
    if (data.notes.length) {
      const det = mkEl('details', 'rvSec rvNotes'); det.dataset.key = 'notes'; det.open = opened.has('notes') ? opened.get('notes') : false;
      const su = mkEl('summary');
      su.append(mkEl('span', 'rvSecName', tf('rv.secNotes', '拍の無い行・読めなかった行（{n}）', { n: data.notes.length })));
      det.append(su);
      for (const n of data.notes) {
        const r = mkEl('div', 'rvNote' + (n.kind === 'unreadable' ? ' unreadable' : ''));
        const where = [n.difficulty ? diffName(n.difficulty) : '', n.mode !== 'Standard' ? n.mode : '', `${srcName(n.src)}${n.line ? ' L' + n.line : ''}`].filter(Boolean).join(' · ');
        r.append(mkEl('span', 'rvNoteWhere', where));
        const kind = { divider: t('rv.nDivider', '区切り'), unreadable: t('rv.nUnreadable', '⚠ 読めない'), mapper: t('rv.nMapper', '担当') }[n.kind];
        if (kind) r.append(mkEl('span', 'rvNoteKind', kind));
        r.append(mkEl('span', 'rvNoteText', n.text));
        det.append(r);
      }
      parts.push(det);
    }
    body.replaceChildren(...parts);
    body.scrollTop = sc;
    // 下の段
    const foot = el.querySelector('.rvFoot');
    const fparts = [mkEl('div', '', t('rv.foot', '行をクリックするとその難易度・拍へ移動して物を選びます（±0.01拍。無ければ ±1/16拍の近い物）。拍の数字のクリックはその位置だけ。文は読み込んだまま出しています。'))];
    if (data.srcs.length) {
      const fr = mkEl('div', 'rvFootSrc');
      fr.append(mkEl('span', '', tf('rv.srcs', '読み込んだ物: {list}', { list: data.srcs.map(s => (s.name || t('rv.pasted', '貼り付けた文'))).join(t('rv.sep', '、')) })));
      const cb = mkEl('button', 'rvClear', t('rv.clear', '指摘を消す')); cb.title = t('rv.clearTip', '読み込んだ指摘・済みの印・返事を全部消します（Ctrl+Z で戻せます）');
      fr.append(cb);
      fparts.push(fr);
    }
    foot.replaceChildren(...fparts);
  }
  /** 前に選んでいた行と今の行だけ描き直す（選んだ印・返事の欄・飛んだ結果。入力中の返事の欄は作り直さない） */
  function refreshRows(prev) {
    if (!el) return;
    for (const id of new Set([prev, curId])) {
      const row = id && el.querySelector(`.rvItem[data-id="${id}"]`), x = id && byId(id);
      if (!row || !x) continue;
      const rp = row.querySelector('.rvReply');
      if (rp && document.activeElement === rp) { row.classList.toggle('cur', id === curId); continue; }
      const nr = rowEl(x);
      if (row.querySelector('.rvMode')) nr.querySelector('.rvLine').append(row.querySelector('.rvMode'));
      row.replaceWith(nr);
    }
  }

  function open() { if (!el) build(); el.style.display = 'flex'; render(); keepInView(); }
  function close() { if (el) el.style.display = 'none'; }
  function isOpen() { return !!el && el.style.display !== 'none'; }
  /** タイムラインの印のクリック: 一覧を開いてその項目を見せる（絞り込み・済みを隠すで見えなければ外す） */
  function focus(id) {
    const x = byId(id); if (!x) return;
    open(); curId = id;
    if (!visible(x)) { filt = 'all'; }
    render();
    const row = el.querySelector(`.rvItem[data-id="${id}"]`);
    if (row) { const det = row.closest('details'); if (det) det.open = true; row.scrollIntoView({ block: 'nearest' }); }
  }

  // ---------------------------------------------------------------- 飛ぶ
  async function jumpTo(x, k) {
    const prev = curId; curId = x.id;
    if (!jumpable(x)) { refreshRows(prev); setMsg(x.mode !== 'Standard' ? t('rv.jOther', 'Standard 以外の指摘は NLM では開けません') : t('rv.jUnknown', '難易度が分からない指摘です'), 'warn'); return; }
    let spots = spotsOf(x), ws = writtenSpotsOf(x);
    if (k != null && spots[k]) { spots = [spots[k]]; ws = [ws[k]]; }
    const r = await api.jump(x.difficulty, spots);
    const beat = ws.map(spotText).join(', ') + (x.nlmBeats ? ` (NLM ${spots.map(spotText).join(', ')})` : '');
    const v = { diff: dispDiff(x.difficulty), beat, n: r.n || 0, d: formatBeat(Math.abs(r.delta || 0)) };
    let text, kind = '';
    if (r.kind === 'nodiff') { text = tf('rv.jNoDiff', '{diff} はこのプロジェクトにありません', v); kind = 'warn'; }
    else if (r.kind === 'fail') { text = t('rv.jFail', '難易度を切り替えられませんでした'); kind = 'warn'; }
    else {
      jumpRes.set(x.id, r.light ? 'light' : r.kind);
      if (r.kind === 'none') { text = tf('rv.jNone', '{diff} の拍 {beat} に物が見つかりません（古い指摘かもしれません）。再生位置だけ動かしました', v); kind = 'warn'; }
      else if (r.light) text = tf('rv.jLight', '{diff} の拍 {beat} のライト（{n}個）を選びました（ノーツ類はありません）', v);
      else if (r.kind === 'near') { text = tf('rv.jNear', '{diff} の拍 {beat} ちょうどには物が無いため、近い物（{d}拍ずれ・{n}個）を選びました', v); kind = 'warn'; }
      else text = tf('rv.jExact', '{diff} の拍 {beat} へ移動しました（{n}個を選びました）', v);
      if (r.locked) text += tf('rv.jLocked', '（ロック・単独編集・リンクの子で選べない物 {n}個）', { n: r.locked });
    }
    setMsg(text, kind);
    if (api.stat) api.stat(text);
    refreshRows(prev);
  }

  // ---------------------------------------------------------------- 読み込み
  function openFile() {
    if (!fileInp) {
      fileInp = document.createElement('input'); fileInp.type = 'file'; fileInp.multiple = true; fileInp.accept = '.txt,.text,.md,.log,text/plain';
      fileInp.style.display = 'none'; document.body.appendChild(fileInp);
      fileInp.addEventListener('change', async () => {
        const fs = [...(fileInp.files || [])].slice(0, MAX_FILES); fileInp.value = '';
        if (!fs.length) return;
        importFiles(fs);
      });
    }
    fileInp.click();
  }
  /** 選んだファイル（File）を読んで読み込みの確認を出す（ファイル選択・テスト） */
  async function importFiles(fs) {
    const list = [];
    for (const f of [...fs].slice(0, MAX_FILES)) list.push(await readFile(f));
    if (list.length) return importDialog(list);
    return false;
  }
  async function readFile(f) {
    const name = String(f.name || '').replace(/[\u0000-\u001F\u007F]/g, '').slice(0, 200);
    if (f.size > REVIEW_LIMITS.maxBytes) return { name, kind: 'file', err: t('rv.errLarge', '大きすぎるため読みません（2MB まで）') };
    try {
      const text = decodeReviewBytes(new Uint8Array(await f.arrayBuffer()));
      return { name, kind: 'file', parsed: parseReviewText(text, { fileName: name, labels: api.labels() }) };
    } catch (e) { return { name, kind: 'file', err: t('rv.errRead', '読み込めませんでした') }; }
  }
  /** 外から文を渡して読み込みの確認を出す（テスト・貼り付け） */
  function importTexts(list) {
    return importDialog(list.map(x => ({ name: x.name || null, kind: x.name ? 'file' : 'paste',
      parsed: parseReviewText(String(x.text || ''), { fileName: x.name || undefined, labels: api.labels() }) })));
  }
  function openPaste() {
    const { bg, dlg, done } = dialog('rvPasteDlg');
    dlg.append(mkEl('div', 'ddMsg lkTitle', t('rv.pTitle', '審査の指摘を貼り付けて読む')));
    dlg.append(mkEl('div', 'ddMsg lkLine', t('rv.pBody', 'Discord の本文（``` で囲んだ物・見出しの行もそのまま）を貼り付けてください。拍で始まる行を指摘として読みます。')));
    const ta = document.createElement('textarea'); ta.className = 'rvPasteText'; ta.spellcheck = false; ta.maxLength = REVIEW_LIMITS.maxChars;
    ta.placeholder = t('rv.pPh', '例:\nExpert+\n12.5 - 文\n24, 25 - 文');
    dlg.append(ta);
    const btns = mkEl('div', 'ddBtns'); dlg.append(btns);
    const ok = mkEl('button', 'pri', t('rv.pOk', '読む')); ok.dataset.v = 'ok';
    const cancel = mkEl('button', '', t('word.cancel', 'キャンセル')); cancel.dataset.v = 'cancel';
    btns.append(ok, cancel);
    ok.addEventListener('click', () => {
      const text = ta.value;
      if (!text.trim()) { ta.focus(); return; }
      done(); importTexts([{ text }]);
    });
    cancel.addEventListener('click', () => done());
    dlg._onKey = e => { if (e.key === 'Enter' && e.ctrlKey) { e.preventDefault(); ok.click(); return true; } return false; };
    document.body.appendChild(bg); ta.focus();
  }

  /** 確認の画面の土台（#dirtyDlg の様式）。Esc＝閉じる。入力欄の上のキーはそのまま通す（裏のショートカットは入力欄では動かない） */
  function dialog(cls) {
    const bg = mkEl('div'); bg.id = 'dirtyDlgBg';
    const dlg = mkEl('div', 'rvDlg ' + cls); dlg.id = 'dirtyDlg'; dlg.dataset.rv = cls; bg.appendChild(dlg);
    const done = () => { removeEventListener('keydown', onKey, true); bg.remove(); };
    const onKey = e => {
      if (dlg._onKey && dlg._onKey(e)) { e.stopPropagation(); return; }
      if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); (dlg.querySelector('button[data-v="cancel"]') || { click: done }).click(); return; }
      if (/^(INPUT|TEXTAREA|SELECT)$/.test((e.target && e.target.tagName) || '')) return;
      e.stopPropagation();   // 裏のショートカットを発火させない
    };
    addEventListener('keydown', onKey, true);
    return { bg, dlg, done };
  }

  const diffOpt = (sel, d, has) => { const o = mkEl('option', '', has ? dispDiff(d) : tf('rv.iNoDiff', '{diff}（プロジェクトに無い）', { diff: dispDiff(d) })); o.value = d; sel.append(o); };

  /** 読み込みの確認: 読んだ数・難易度の分からない項目の難易度・C3（元の拍として読む）・今の指摘に足すか置き換えるか */
  function importDialog(list) {
    return new Promise(res => {
      const { bg, dlg, done } = dialog('rvImport');
      dlg.append(mkEl('div', 'ddMsg lkTitle', t('rv.iTitle', '審査の指摘を読み込む')));
      const has = new Set((api.diffs() || []).filter(d => d.has).map(d => d.dn));
      const cur = api.curDiff();
      const picks = [];   // {li, key, sel}
      list.forEach((e, li) => {
        const box = mkEl('div', 'rvSrc');
        box.append(mkEl('div', 'rvSrcName', e.name ? '📄 ' + e.name : t('rv.pasted', '貼り付けた文')));
        if (e.err) { box.append(mkEl('div', 'rvSrcErr', e.err)); dlg.append(box); return; }
        const st = parsedStats(e.parsed), bits = [];
        for (const d of DIFF_ORDER) if (st.by[d]) bits.push(tf('rv.iDiffN', '{diff} {n}件', { diff: dispDiff(d), n: st.by[d] }));
        if (st.unknown) bits.push(tf('rv.iUnknownN', '難易度の分からない指摘 {n}件', { n: st.unknown }));
        if (st.other) bits.push(tf('rv.iOtherN', 'Standard 以外 {n}件', { n: st.other }));
        if (st.notes) bits.push(tf('rv.iNotesN', '拍の無い行 {n}', { n: st.notes }));
        if (st.unreadable) bits.push(tf('rv.iUnreadN', '読めなかった行 {n}', { n: st.unreadable }));
        if (st.responses) bits.push(tf('rv.iRespN', '返事 {n}件', { n: st.responses }));
        box.append(mkEl('div', 'rvSrcStat', bits.length ? bits.join(t('rv.sep', '、')) : t('rv.iNone', '指摘（拍で始まる行）が見つかりませんでした')));
        for (const g of unknownGroups(e.parsed)) {
          const row = mkEl('label', 'rvPick');
          row.append(mkEl('span', '', g.label ? tf('rv.iPickLabel', '見出し「{label}」の指摘（{n}件）の難易度:', { label: g.label, n: g.n })
            : tf('rv.iPick', '見出しの無い指摘（{n}件）の難易度:', { n: g.n })));
          const sel = document.createElement('select'); sel.className = 'rvPickSel';
          for (const d of DIFF_ORDER) diffOpt(sel, d, has.has(d));
          sel.value = cur && REVIEW_DIFFS.includes(cur) ? cur : (DIFF_ORDER.find(d => has.has(d)) || 'ExpertPlus');
          row.append(sel); box.append(row);
          picks.push({ li, key: g.key, sel });
        }
        const ws = (e.parsed.warnings || []).filter(w => WARN_JA[w.code]);
        if (ws.length) {
          const det = mkEl('details', 'rvWarns');
          det.append(mkEl('summary', '', tf('rv.iWarns', '読み方の注意（{n}）', { n: ws.length })));
          for (const w of ws.slice(0, 50)) {
            const r = mkEl('div', 'rvWarn');
            r.append(mkEl('span', 'rvWarnLine', w.line ? 'L' + w.line : ''), mkEl('span', '', t('rv.w.' + w.code, WARN_JA[w.code])));
            if (w.text) r.append(mkEl('span', 'rvWarnText', w.text));
            det.append(r);
          }
          box.append(det);
        }
        dlg.append(box);
      });
      // C3: 拍を付け替えた難易度（その難易度へ入る指摘がある時だけ）
      const c3Box = mkEl('div', 'rvC3'); dlg.append(c3Box);
      const c3 = new Map();   // 難易度 → checkbox
      const pickOf = li => { const o = {}; for (const p of picks) if (p.li === li) o[p.key] = p.sel.value; return o; };
      const targets = () => {
        const s = new Set();
        list.forEach((e, li) => { if (!e.parsed) return; const pk = pickOf(li);
          for (const it of e.parsed.items) { if (it.otherMode) continue; const d = it.difficulty || pk[it.label || '']; if (d) s.add(d); } });
        return s;
      };
      // 今ある指摘
      let rep = null;
      if (data.items.length || data.notes.length) {
        const box = mkEl('div', 'rvExisting');
        for (const [v, l] of [['add', tf('rv.iAdd', '今ある指摘（{n}件）に足す', { n: data.items.length })], ['replace', t('rv.iReplace', '今ある指摘・済みの印・返事を消して置き換える')]]) {
          const lab = mkEl('label', 'rvExistingOpt'); const inp = document.createElement('input'); inp.type = 'radio'; inp.name = 'rvExisting'; inp.value = v; inp.checked = v === 'add';
          lab.append(inp, mkEl('span', '', l)); box.append(lab);
          if (v === 'replace') rep = inp;
        }
        dlg.append(box);
      }
      const sum = mkEl('div', 'ddMsg rvISum'); dlg.append(sum);
      const total = list.reduce((a, e) => a + (e.parsed ? e.parsed.items.length : 0), 0);
      function sync() {
        const tg = targets();
        for (const d of DIFF_ORDER) {
          const tp = tg.has(d) && api.retime(d);
          if (tp && !c3.has(d)) {
            const lab = mkEl('label', 'rvC3Opt'); const inp = document.createElement('input'); inp.type = 'checkbox'; inp.checked = true; inp.dataset.d = d;
            lab.append(inp, mkEl('span', '', tf('rv.iC3', '{diff} は「曲データを読み込む」で拍を付け替えています。指摘の拍を元の譜面の拍として読み、NLM の拍に直す', { diff: dispDiff(d) })));
            c3.set(d, { lab, inp });
          }
          if (c3.has(d)) c3.get(d).lab.style.display = tp ? '' : 'none';
        }
        c3Box.replaceChildren(...DIFF_ORDER.filter(d => c3.has(d)).map(d => c3.get(d).lab));
        c3Box.style.display = [...c3.values()].some(x => x.lab.style.display !== 'none') ? '' : 'none';
        sum.textContent = tf('rv.iSum', '読み込む指摘: {n}件', { n: total });
      }
      dlg.addEventListener('change', sync);
      sync();
      const btns = mkEl('div', 'ddBtns'); dlg.append(btns);
      const ok = mkEl('button', 'pri', t('rv.iOk', '読み込む')); ok.dataset.v = 'ok';
      const cancel = mkEl('button', '', t('word.cancel', 'キャンセル')); cancel.dataset.v = 'cancel';
      ok.disabled = !list.some(e => e.parsed && (e.parsed.items.length || e.parsed.notes.length));
      btns.append(ok, cancel);
      cancel.addEventListener('click', () => { done(); res(false); });
      ok.addEventListener('click', () => {
        const tg = targets(), retime = {}, asOrig = {};
        for (const d of tg) { const tp = api.retime(d); if (tp) { retime[d] = tp; asOrig[d] = !!(c3.has(d) && c3.get(d).inp.checked); } }
        const replace = !!(rep && rep.checked);
        done();
        commitImport(list, pickOf, retime, asOrig, replace);
        res(true);
      });
      dlg._onKey = e => { if (e.key === 'Enter' && !/^(SELECT|TEXTAREA)$/.test((e.target && e.target.tagName) || '') && !ok.disabled) { e.preventDefault(); ok.click(); return true; } return false; };
      document.body.appendChild(bg);
      ok.focus();
    });
  }
  function commitImport(list, pickOf, retime, asOrig, replace) {
    api.snapshot();
    if (replace) { data = { items: [], notes: [], srcs: [] }; curId = null; jumpRes.clear(); }
    let n = 0, m = 0;
    list.forEach((e, li) => {
      if (!e.parsed) return;
      if (data.srcs.length >= RV_LIMITS.srcs) return;
      const src = { id: 's' + (++seq), name: e.name || null, kind: e.kind === 'file' ? 'file' : 'paste', at: new Date().toISOString(), n: 0 };
      const r = importParsed(e.parsed, { src: src.id, nextId: () => 'r' + (++seq), pick: pickOf(li), retime, asOrig });
      const room = RV_LIMITS.items - data.items.length, nroom = RV_LIMITS.notes - data.notes.length;
      const its = r.items.slice(0, Math.max(0, room)), nts = r.notes.slice(0, Math.max(0, nroom));
      src.n = its.length;
      data.srcs.push(src); data.items.push(...its); data.notes.push(...nts);
      n += its.length; m += nts.length;
    });
    changed();
    open();
    setMsg(tf('rv.loaded', '審査の指摘を {n}件読み込みました（拍の無い行 {m}）。行をクリックするとその位置へ移動します', { n, m }), 'ok');
    render();
  }

  // ---------------------------------------------------------------- 消す
  function clearAsk() {
    const { bg, dlg, done } = dialog('rvClearDlg');
    dlg.append(mkEl('div', 'ddMsg', tf('rv.clearAsk', '読み込んだ審査の指摘（{n}件）・済みの印・返事を全部消しますか？（Ctrl+Z で戻せます）', { n: data.items.length })));
    const btns = mkEl('div', 'ddBtns'); dlg.append(btns);
    const ok = mkEl('button', 'pri', t('rv.clearOk', '消す')); ok.dataset.v = 'ok';
    const cancel = mkEl('button', '', t('word.cancel', 'キャンセル')); cancel.dataset.v = 'cancel';
    btns.append(ok, cancel);
    ok.addEventListener('click', () => { done(); clearAll(); });
    cancel.addEventListener('click', () => done());
    document.body.appendChild(bg); cancel.focus();
  }
  function clearAll() {
    if (isEmpty()) return;
    api.snapshot();
    data = { items: [], notes: [], srcs: [] }; curId = null; jumpRes.clear();
    changed(); setMsg(t('rv.cleared', '審査の指摘を消しました（Ctrl+Z で戻せます）'), 'ok'); render();
  }

  // ---------------------------------------------------------------- 書き出し
  async function english() {
    if (enDict) return enDict;
    try { const j = await (await fetch('lang/en.json', { cache: 'no-cache' })).json(); enDict = j && typeof j === 'object' ? j : {}; } catch (_) { enDict = {}; }
    return enDict;
  }
  /** NLM の確かめ（書き出すのと同じ .dat）を英語の指摘の形にする */
  async function checkItems(o) {
    const p = await api.collect();
    if (!p || p.error) return { error: (p && p.error) || t('rv.xNoChart', '確かめる譜面がありません') };
    const mc = runMapCheck(p);
    const rc = api.rating && api.rating(), stars = {};
    for (const d of p.diffs) { const a = rc && rc.ratingOf && rc.ratingOf(d.difficulty); if (a && (a.star != null || a.tech != null)) stars[d.difficulty] = { star: a.star, tech: a.tech }; }
    let bl = null; try { bl = runBlCriteria({ ...p, stars }, mc); } catch (_) { bl = null; }
    const EN = await english();
    const tEn = (k, def) => (Object.prototype.hasOwnProperty.call(EN, k) && typeof EN[k] === 'string' ? EN[k] : def);
    const fill = (s, vars) => { if (vars) for (const k in vars) s = s.split('{' + k + '}').join(String(vars[k])); return s; };
    const bv = blView({ t: tEn, escHtml: s => s, dispDiff, mcLabel: key => tEn('mc.k.' + key, key) });
    const mcText = r => { const v = { ...(r.vars || {}) }; if (v.what) v.what = tEn('mc.what.' + v.what, v.what); if (v.above) v.above = dispDiff(v.above); return fill(tEn('mc.k.' + r.key, r.label || r.key), v); };
    return checksToItems(mc, bl, { ...o, blText: (r, f) => bv.msg(f), mcText });
  }
  function exportDialog() {
    const { bg, dlg, done } = dialog('rvExportDlg');
    dlg.append(mkEl('div', 'ddMsg lkTitle', t('rv.xTitle', '指摘の形で書き出す')));
    const kinds = mkEl('div', 'lkOpts');
    const opt = (type, name, value, main, sub, dis) => {
      const lab = mkEl('label', 'lkOpt' + (dis ? ' dis' : ''));
      const inp = document.createElement('input'); inp.type = type; inp.name = name; inp.value = value; inp.disabled = !!dis;
      const body = mkEl('span', 'lkOptBody'); body.append(mkEl('span', 'lkOptMain', main)); if (sub) body.append(mkEl('span', 'lkOptSub', sub));
      lab.append(inp, body); return { lab, inp };
    };
    const kReply = opt('radio', 'rvXKind', 'reply', t('rv.xReply', '審査の指摘に返事を付けた物'),
      t('rv.xReplySub', '元の行の後ろに「 - 返事」を足します（拍は審査の人が書いた拍のまま）。マッパーが返事を送る形'), !data.items.length);
    const kCheck = opt('radio', 'rvXKind', 'check', t('rv.xCheck', 'NLM の確かめの結果'),
      t('rv.xCheckSub', 'BL評価リスト（と BS Map Check）の拍のある所見を、指摘と同じ形（英語・難易度の見出し＋「拍, 拍 - [項目] 文 (NLM)」）にします。AutoModder の「Import Mod」でも読めます'));
    (data.items.length ? kReply : kCheck).inp.checked = true;
    kinds.append(kReply.lab, kCheck.lab); dlg.append(kinds);
    const chk = (cls, label, on) => { const lab = mkEl('label', 'rvXOpt'); const inp = document.createElement('input'); inp.type = 'checkbox'; inp.className = cls; inp.checked = on; lab.append(inp, mkEl('span', '', label)); return { lab, inp }; };
    const oReply = mkEl('div', 'rvXOpts');
    const oFixed = chk('rvXFixed', t('rv.xFixed', '済みで返事の無い指摘に「fixed」と書く'), false);
    // 読み込んだ物が2つ以上: どれに返事を付けるか（審査の人ごとに返す。既定は全部）
    const srcSel = document.createElement('select'); srcSel.className = 'rvXSrc';
    { const o = mkEl('option', '', t('rv.xSrcAll', '読み込んだ物すべて')); o.value = ''; srcSel.append(o); }
    for (const s of data.srcs) { const o = mkEl('option', '', s.name || t('rv.pasted', '貼り付けた文')); o.value = s.id; srcSel.append(o); }
    const srcRow = mkEl('label', 'rvXOpt rvXSrcRow'); srcRow.append(mkEl('span', '', t('rv.xSrc', '返事を付ける物:')), srcSel);
    if (data.srcs.length < 2) srcRow.style.display = 'none';
    oReply.append(srcRow, oFixed.lab);
    const oCheck = mkEl('div', 'rvXOpts');
    const oFail = chk('rvXFail', t('rv.xFail', 'BL評価リストの違反'), true), oChk = chk('rvXChk', t('rv.xChk', 'BL評価リストの要確認'), true);
    const oMc = chk('rvXMc', t('rv.xMc', 'BS Map Check（ランク不可・エラー・警告）'), false), oSev = chk('rvXSev', t('rv.xSev', '行の頭に重さの印（(X) 違反／(?) 要確認）'), false);
    oCheck.append(oFail.lab, oChk.lab, oMc.lab, oSev.lab);
    dlg.append(oReply, oCheck);
    const note = mkEl('div', 'ddMsg rvXNote'); dlg.append(note);
    const pre = document.createElement('textarea'); pre.className = 'rvXPre'; pre.readOnly = true; pre.spellcheck = false; dlg.append(pre);
    const status = mkEl('div', 'rvXStatus'); dlg.append(status);
    const btns = mkEl('div', 'ddBtns'); dlg.append(btns);
    const bCopy = mkEl('button', 'pri', t('rv.xCopy', 'クリップボードへコピー')), bSave = mkEl('button', '', t('rv.xSave', '出力フォルダへ保存'));
    const bClose = mkEl('button', '', t('ui.close', '閉じる')); bClose.dataset.v = 'cancel';
    bSave.title = t('rv.xSaveTip', '書き出しの出力フォルダ（INFO の書き出しノードで選んだフォルダ）へ .txt で保存します。出力フォルダが無ければダウンロードします');
    btns.append(bCopy, bSave, bClose);
    let checks = null, text = '', ver = 0;
    async function sync() {
      const my = ++ver, kind = kCheck.inp.checked ? 'check' : 'reply';
      oReply.style.display = kind === 'reply' ? '' : 'none'; oCheck.style.display = kind === 'check' ? '' : 'none';
      status.textContent = ''; status.className = 'rvXStatus';
      if (kind === 'reply') {
        const sid = srcSel.value, xs = sid ? data.items.filter(x => x.src === sid) : data.items, ns = sid ? data.notes.filter(n => n.src === sid) : data.notes;
        const its = toFormatItems(xs, { fixedForDone: oFixed.inp.checked });
        // 重さの印は審査の人が書いた項目にだけ（'keep'。印の無い行に (N) を足さない）
        text = formatReviewText(its, { responses: true, severity: 'keep', notes: toFormatNotes(ns), useLabels: xs.some(x => x.label) });
        note.textContent = tf('rv.xReplyNote', '返事のある指摘 {r}／{n}件。拍の無い行（全体への意見など）もその難易度の見出しの下に入れます。', { r: its.filter(x => x.response).length, n: its.length });
      } else {
        note.textContent = t('rv.xRunning', '確かめています…'); pre.value = '';
        if (!checks) {
          try { checks = await checkItems({ fail: true, check: true, mc: true }); } catch (e) { checks = { error: String(e && e.message || e) }; }
        }
        if (my !== ver) return;
        if (checks.error) { text = ''; note.textContent = checks.error; pre.value = ''; return; }
        const want = x => (x.origin === 'mc' ? oMc.inp.checked : x.severity === 'X' ? oFail.inp.checked : oChk.inp.checked);
        const its = checks.items.filter(want);
        text = its.length ? formatReviewText(its, { severity: oSev.inp.checked, header: [CHECK_HEADER] }) : '';
        note.textContent = (its.length ? tf('rv.xCheckNote', '{n}行（英語で書き出します・審査の人向け）。', { n: its.length }) : t('rv.xCheckNone', '書き出す所見がありません。'))
          + (checks.noBeat ? tf('rv.xNoBeat', '拍の無い所見 {n}件は入れていません。', { n: checks.noBeat }) : '')
          + t('rv.xStars', '★・Tech は「難易度を測る」の結果を使います（無ければ R5.A は判定しません）。');
      }
      pre.value = text;
    }
    dlg.addEventListener('change', () => sync());
    bCopy.addEventListener('click', async () => {
      if (!text) return;
      let ok = false;
      try { if (api.copyText) ok = await api.copyText(text); else { await navigator.clipboard.writeText(text); ok = true; } } catch (_) { ok = false; }
      if (!ok) { try { pre.focus(); pre.select(); ok = document.execCommand('copy'); } catch (_) { ok = false; } }
      status.textContent = ok ? t('rv.xCopied', 'クリップボードへコピーしました') : t('rv.xCopyFail', 'コピーできませんでした（上の欄を選んでコピーしてください）');
      status.className = 'rvXStatus ' + (ok ? 'ok' : 'err');
    });
    bSave.addEventListener('click', async () => {
      if (!text) return;
      const kind = kCheck.inp.checked ? 'check' : 'reply';
      const clean = (s, n) => String(s || '').replace(/[\u0000-\u001F\u007F\\/:*?"<>|]/g, '').trim().slice(0, n);
      const base = clean(api.outBase(), 60) || 'NLM';
      // 返事: 1つの読み込んだ物に返す時はその名前を入れる（例「曲_Mod_reply.txt」）。名前はファイル由来なので使えない文字を消す
      const src = kind === 'reply' && (srcSel.value || data.srcs.length === 1) ? data.srcs.find(s => s.id === (srcSel.value || data.srcs[0].id)) : null;
      const stem = src && src.name ? clean(src.name.replace(/\.(?:txt|text|md|log)$/i, ''), 40) : '';
      const name = kind === 'check' ? `${base}_nlm_check.txt` : stem ? `${base}_${stem}_reply.txt` : `${base}_review_reply.txt`;
      const r = await api.saveTxt(name, text);
      status.textContent = r && r.ok ? (r.download ? tf('rv.xDownloaded', '出力フォルダが無いため、ダウンロードしました: {name}', { name }) : tf('rv.xSaved', '保存しました: {where}', { where: r.where || name }))
        : tf('rv.xSaveFail', '保存できませんでした: {err}', { err: (r && r.err) || '?' });
      status.className = 'rvXStatus ' + (r && r.ok ? 'ok' : 'err');
    });
    bClose.addEventListener('click', () => done());
    document.body.appendChild(bg);
    sync();
    bClose.focus();
  }

  // ---------------------------------------------------------------- タイムラインの印・言語
  /** 今の難易度の印: [{id, spots:[{a,b}]（NLM の拍）, sev, done, cur}] */
  function marks(dn) {
    if (!dn) return [];
    return data.items.filter(x => jumpable(x) && x.difficulty === dn).map(x => ({ id: x.id, spots: spotsOf(x), sev: x.severity, done: x.done, cur: x.id === curId }));
  }
  function relabel() { render(); }
  function dbg() {
    const rows = el ? [...el.querySelectorAll('.rvItem')].map(r => r.dataset.id) : [];
    return structuredClone({ open: isOpen(), items: data.items, notes: data.notes, srcs: data.srcs, cur: curId, filt, hideDone, msg: lastMsg, rows, jump: Object.fromEntries(jumpRes),
      font: fontPx });
  }
  return { open, close, isOpen, focus, openFile, openPaste, importTexts, importFiles, exportDialog, save, load, reset, marks, tipOf, relabel, dbg };
}

// MEDIA ライブラリの絞り込み（2026-10-12）: 文字の検索欄・条件のパネル（ボタンは「フィルター」）・件数の表示。
// 条件は行（＝1難易度）ごとに判定する（rowMatches）。グリッドは「合う難易度が1つでもある曲」を出す（lib-table.js の refresh）。
// 条件は bsnm_libFilter に保存して次回も残す。モードの初期値（Standard だけ）は「絞り込み中」に数えない（件数の表示・［解除］の点灯）。
import { rowVal, DIFF_ORDER, DIFF_SHORT, CHAR_NAMES, charName } from './lib-table.js';

const KEY = 'bsnm_libFilter';
const RANGES = ['stars', 'len', 'njs', 'nps', 'bpm', 'up'];   // 範囲（下限・上限。空欄＝制限なし）
const MODES = ['Standard', 'OneSaber', 'NoArrows', '360Degree', '90Degree', 'Lawless', 'Lightshow', 'Legacy'];
const DEFAULT_MODES = ['Standard'];

export function defaultFilter() {
  return { q: '', stars: ['', ''], len: ['', ''], njs: ['', ''], nps: ['', ''], bpm: ['', ''], up: ['', ''],
    diffs: [], modes: [...DEFAULT_MODES], ranked: 'all', noMods: false, fav: false, unplayed: false };
}

function load() {
  const f = defaultFilter();
  let s = null;
  try { s = JSON.parse(localStorage.getItem(KEY) || 'null'); } catch (_) { s = null; }
  if (!s || typeof s !== 'object') return f;
  const str = v => (typeof v === 'string' ? v.slice(0, 40) : '');
  if (typeof s.q === 'string') f.q = s.q.slice(0, 200);
  for (const k of RANGES) if (Array.isArray(s[k])) f[k] = [str(s[k][0]), str(s[k][1])];
  if (Array.isArray(s.diffs)) f.diffs = s.diffs.filter(d => DIFF_ORDER.includes(d));
  if (Array.isArray(s.modes)) f.modes = s.modes.filter(m => typeof m === 'string').slice(0, 32);
  if (['all', 'bl', 'unranked'].includes(s.ranked)) f.ranked = s.ranked;
  for (const k of ['noMods', 'fav', 'unplayed']) f[k] = s[k] === true;
  return f;
}

/** 長さの入力: 「2:30」＝2分30秒、数だけ＝分（小数可） → 秒。読めなければ null */
export function parseLen(s) {
  s = String(s || '').trim();
  if (!s) return null;
  const m = /^(\d+):(\d{1,2})$/.exec(s);
  if (m) return +m[1] * 60 + +m[2];
  const v = parseFloat(s);
  return isFinite(v) ? v * 60 : null;
}
function parseNum(s) { s = String(s || '').trim(); if (!s) return null; const v = parseFloat(s); return isFinite(v) ? v : null; }
/** 日付の入力（YYYY-MM-DD）→ UNIX秒。上限はその日の終わりまで含める */
function parseDay(s, end) {
  s = String(s || '').trim();
  if (!/^\d{4}-\d{2}-\d{2}$/.test(s)) return null;
  const t = new Date(s + 'T00:00:00').getTime() / 1000;
  return isFinite(t) ? t + (end ? 86400 - 1 : 0) : null;
}

// innerHTML へ入れる訳文（属性の中も）を無害にする。訳文は loadLang が '<' を含む物を捨てているが、'"' は残るため属性からは抜け出せる
const esc = v => String(v == null ? '' : v).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');

export function installLibFilter(api) {
  const { onChange } = api;
  const t = (k, d) => esc(api.t(k, d)), tf = api.tf;   // このファイルの t は innerHTML 用（無害化済み）。textContent へは api.t を使う
  let f = load();
  let parsed = null;          // 範囲の数値（変わるたびに作り直す）
  const sameModes = (a, b) => a.length === b.length && a.every(x => b.includes(x));

  function reparse() {
    const p = {};
    for (const k of RANGES) {
      const [a, b] = f[k];
      p[k] = k === 'len' ? [parseLen(a), parseLen(b)] : k === 'up' ? [parseDay(a, false), parseDay(b, true)] : [parseNum(a), parseNum(b)];
    }
    p.q = f.q.trim().toLowerCase();
    p.diffs = new Set(f.diffs);
    p.modes = new Set(f.modes);
    parsed = p;
  }
  reparse();

  /** 行（難易度）の条件のうち、初期値と違う物があるか（文字の検索は含めない） */
  function condActive() {
    return RANGES.some(k => parsed[k][0] != null || parsed[k][1] != null) || f.diffs.length > 0 || !sameModes(f.modes, DEFAULT_MODES)
      || f.ranked !== 'all' || f.noMods || f.fav || f.unplayed;
  }
  /** 絞り込み中か（件数の表示の強調・［解除］の点灯）。モードの初期値は数えない */
  function active() { return condActive() || !!parsed.q; }
  /** 効いている条件の数（フィルターのボタンの丸の数字）: ★・長さ・NJS・NPS・BPM・アップロード日・難易度・モード（初期値の Standard だけは数えない）・
   * ランク・Mod・お気に入り・未プレイで、それぞれ1つ。文字の検索は数えない */
  function condCount() {
    return RANGES.filter(k => parsed[k][0] != null || parsed[k][1] != null).length + (f.diffs.length > 0 ? 1 : 0) + (!sameModes(f.modes, DEFAULT_MODES) ? 1 : 0)
      + (f.ranked !== 'all' ? 1 : 0) + (f.noMods ? 1 : 0) + (f.fav ? 1 : 0) + (f.unplayed ? 1 : 0);
  }

  /** 曲（またはその他の項目）が文字の検索に合うか。曲は曲名・サブタイトル・アーティスト・マッパー、その他は名前 */
  function matchText(item) {
    const q = parsed.q;
    if (!q) return true;
    const e = item.entry;
    const hay = e ? [e.name, e.subName, e.artist, e.mapper, item.name] : [item.name];
    return hay.some(s => s && String(s).toLowerCase().includes(q));
  }

  const inRange = (v, r) => (r[0] == null && r[1] == null) || (v != null && (r[0] == null || v >= r[0]) && (r[1] == null || v <= r[1]));

  /** 1行（1難易度）が条件に合うか。値の無い行は、その範囲が指定されていれば合わない */
  function rowMatches(row) {
    const d = row.d;
    if (!d) return false;
    if (parsed.modes.size && !parsed.modes.has(d.char)) return false;
    if (parsed.diffs.size && !parsed.diffs.has(d.diff)) return false;
    if (!inRange(rowVal.stars(row), parsed.stars)) return false;
    if (!inRange(rowVal.len(row), parsed.len)) return false;
    if (!inRange(rowVal.njs(row), parsed.njs)) return false;
    if (!inRange(rowVal.nps(row), parsed.nps)) return false;
    if (!inRange(rowVal.bpm(row), parsed.bpm)) return false;
    if (!inRange(rowVal.uploaded(row), parsed.up)) return false;
    if (f.ranked !== 'all') { const bl = rowVal.blRanked(row); if (f.ranked === 'bl' ? !bl : bl) return false; }
    if (f.noMods && (d.req || []).some(m => m === 'noodle' || m === 'chroma')) return false;
    if (f.fav && !rowVal.fav(row)) return false;
    if (f.unplayed && (rowVal.plays(row) || 0) > 0) return false;
    return true;
  }

  // ---------------------------------------------------------------- 画面
  const $ = id => document.getElementById(id);
  let panel = null, lastCount = '';

  function save() { try { localStorage.setItem(KEY, JSON.stringify(f)); } catch (_) {} }
  function changed(soon) { reparse(); save(); refreshUi(); onChange(soon); }

  function refreshUi() {
    const on = active(), n = condCount();
    const fb = $('libFiltBtn'); if (fb) fb.classList.toggle('on', n > 0);
    const fn = $('libFiltN');
    if (fn) { fn.textContent = n > 0 ? String(n) : ''; fn.classList.toggle('on', n > 0); fn.title = n > 0 ? tf('lib.filterN', '{n}個の条件で絞り込んでいます', { n }) : ''; }
    const cl = $('libFiltClear'); if (cl) { cl.disabled = !on; cl.classList.toggle('on', on); }
    const sb = $('libSearchBox'), si = $('libSearch'); if (sb && si) sb.classList.toggle('has', !!si.value);   // 検索欄の × は文字がある時だけ
    if (panel) syncPanel();
  }

  function rangeRow(k, labelKey, labelDef, unitKey, unitDef, ph, type, tipKey, tipDef) {
    const tp = type || 'text';
    const tip = tipKey ? ` data-i18n-t="${tipKey}" title="${t(tipKey, tipDef)}"` : '';
    return `<div class="lfRow" data-k="${k}"><span class="lfLab" data-i18n="${labelKey}"${tip}>${labelDef}</span>`
      + `<input class="lfLo" type="${tp}" ${tp === 'text' ? 'inputmode="decimal"' : ''} placeholder="${ph || ''}" spellcheck="false">`
      + `<span class="lfTil">–</span><input class="lfHi" type="${tp}" ${tp === 'text' ? 'inputmode="decimal"' : ''} placeholder="${ph || ''}" spellcheck="false">`
      + (unitKey ? `<span class="lfUnit" data-i18n="${unitKey}">${unitDef}</span>` : '') + '</div>';
  }

  function build() {
    panel = document.createElement('div');
    panel.id = 'libFiltPanel';
    panel.innerHTML = `<div class="lfHead"><span data-i18n="lib.f.title">${t('lib.f.title', 'フィルター')}</span>`
      + `<button class="lfClose" data-i18n-t="ui.close" title="${t('ui.close', '閉じる')}">✕</button></div>`
      + rangeRow('stars', 'lib.f.stars', '★', null, null, '', 'text', 'lib.f.starsTip', 'BeatLeader の★（無ければ NLM推定の★）で判定します')
      + rangeRow('len', 'lib.f.len', '長さ', 'lib.f.lenUnit', '分', '2:30')
      + rangeRow('njs', 'lib.f.njs', 'NJS')
      + rangeRow('nps', 'lib.f.nps', 'NPS')
      + rangeRow('bpm', 'lib.f.bpm', 'BPM')
      + rangeRow('up', 'lib.f.up', 'アップロード日', null, null, '', 'date')
      + `<div class="lfRow"><span class="lfLab" data-i18n="lib.f.diff">難易度</span><span class="lfDiffs">`
      + DIFF_ORDER.map(d => `<button class="lfDf lfDf_${d}" data-d="${d}">${DIFF_SHORT[d]}</button>`).join('') + '</span></div>'
      + `<div class="lfRow lfModeRow"><span class="lfLab" data-i18n="lib.f.mode">モード</span><span class="lfModes">`
      + MODES.map(m => `<label class="lfMode"><input type="checkbox" data-m="${m}"><span data-i18n="${CHAR_NAMES[m] ? 'lib.char.' + m : ''}">${charName(m, t)}</span></label>`).join('') + '</span></div>'
      + `<div class="lfRow"><span class="lfLab" data-i18n="lib.f.ranked">ランク</span><select class="lfRanked">`
      + `<option value="all" data-i18n="lib.f.rankAll">${t('lib.f.rankAll', 'すべて')}</option>`
      + `<option value="bl" data-i18n="lib.f.rankBl">${t('lib.f.rankBl', 'BL ランク')}</option>`
      + `<option value="unranked" data-i18n="lib.f.rankNone">${t('lib.f.rankNone', '未ランク')}</option></select></div>`
      + `<label class="lfChk"><input type="checkbox" data-c="noMods"><span data-i18n="lib.f.noMods">Noodle/Chroma が必要な曲を除く</span></label>`
      + `<label class="lfChk"><input type="checkbox" data-c="fav"><span data-i18n="lib.f.fav">お気に入りだけ</span></label>`
      + `<label class="lfChk"><input type="checkbox" data-c="unplayed"><span data-i18n="lib.f.unplayed">未プレイだけ（その難易度を遊んだことがない）</span></label>`
      + `<div class="lfFoot"><button class="lfReset" data-i18n="lib.f.clear">解除</button></div>`;
    // data-i18n の既定文を今の言語で（以後の言語切替は loadLang が data-i18n 系を訳し直す）
    panel.querySelectorAll('[data-i18n]').forEach(el => { if (el.dataset.i18n) el.textContent = api.t(el.dataset.i18n, el.textContent); });
    document.body.appendChild(panel);
    panel.addEventListener('keydown', e => { if (e.key === 'Escape') { e.stopPropagation(); close(); } });
    panel.querySelector('.lfClose').addEventListener('click', close);
    panel.querySelector('.lfReset').addEventListener('click', () => clear());
    for (const row of panel.querySelectorAll('.lfRow[data-k]')) {
      const k = row.dataset.k;
      const upd = () => { f[k] = [row.querySelector('.lfLo').value.trim(), row.querySelector('.lfHi').value.trim()]; changed(true); };
      row.querySelector('.lfLo').addEventListener('input', upd);
      row.querySelector('.lfHi').addEventListener('input', upd);
    }
    for (const b of panel.querySelectorAll('.lfDf')) b.addEventListener('click', () => {
      const d = b.dataset.d, s = new Set(f.diffs);
      if (s.has(d)) s.delete(d); else s.add(d);
      f.diffs = DIFF_ORDER.filter(x => s.has(x)); changed();
    });
    for (const c of panel.querySelectorAll('.lfMode input')) c.addEventListener('change', () => {
      f.modes = [...panel.querySelectorAll('.lfMode input')].filter(x => x.checked).map(x => x.dataset.m); changed();
    });
    panel.querySelector('.lfRanked').addEventListener('change', e => { f.ranked = e.target.value; changed(); });
    for (const c of panel.querySelectorAll('.lfChk input')) c.addEventListener('change', () => { f[c.dataset.c] = c.checked; changed(); });
    document.addEventListener('pointerdown', e => {
      if (!panel || panel.style.display === 'none') return;
      if (panel.contains(e.target) || (e.target.closest && e.target.closest('#libFiltBtn'))) return;
      close();
    }, true);
  }

  function syncPanel() {
    for (const row of panel.querySelectorAll('.lfRow[data-k]')) {
      const k = row.dataset.k, lo = row.querySelector('.lfLo'), hi = row.querySelector('.lfHi');
      if (document.activeElement !== lo) lo.value = f[k][0];
      if (document.activeElement !== hi) hi.value = f[k][1];
      const bad = (v, x) => v !== '' && x == null;
      lo.classList.toggle('bad', bad(f[k][0], parsed[k][0]));
      hi.classList.toggle('bad', bad(f[k][1], parsed[k][1]));
    }
    for (const b of panel.querySelectorAll('.lfDf')) b.classList.toggle('on', f.diffs.includes(b.dataset.d));
    for (const c of panel.querySelectorAll('.lfMode input')) c.checked = f.modes.includes(c.dataset.m);
    panel.querySelector('.lfRanked').value = f.ranked;
    for (const c of panel.querySelectorAll('.lfChk input')) c.checked = !!f[c.dataset.c];
  }

  function place() {
    const b = $('libFiltBtn'); if (!b || !panel) return;
    const r = b.getBoundingClientRect(), w = panel.offsetWidth, h = panel.offsetHeight;
    panel.style.left = Math.max(4, Math.min(innerWidth - w - 4, r.left)) + 'px';
    panel.style.top = Math.max(4, Math.min(innerHeight - h - 4, r.bottom + 4)) + 'px';
  }
  function open() { if (!panel) build(); panel.style.display = 'block'; syncPanel(); place(); }
  function close() { if (panel) panel.style.display = 'none'; }
  function toggle() { if (panel && panel.style.display !== 'none') close(); else open(); }
  function isOpen() { return !!panel && panel.style.display !== 'none'; }

  function clear() {
    f = defaultFilter();
    const si = $('libSearch'); if (si) si.value = '';
    changed();
  }

  // 検索欄・ボタン（editor.html にある物へ一度だけ繋ぐ）
  {
    const si = $('libSearch');
    if (si) {
      si.value = f.q;
      let tm = null;
      const sb = $('libSearchBox');
      si.addEventListener('input', () => { f.q = si.value.slice(0, 200); if (sb) sb.classList.toggle('has', !!si.value); clearTimeout(tm); tm = setTimeout(() => changed(), 120); });
      si.addEventListener('keydown', e => { if (e.key === 'Escape' && si.value) { e.stopPropagation(); clearTimeout(tm); si.value = ''; f.q = ''; changed(); } });
      // 欄の中の ×: 検索の文字を消す（打った文字のぶんの絞り込みも外れる）。押した後も欄に入力できるようにする
      const sx = $('libSearchX');
      if (sx) {
        sx.addEventListener('pointerdown', e => e.preventDefault());   // 欄のフォーカスを外さない
        sx.addEventListener('click', () => { clearTimeout(tm); si.value = ''; f.q = ''; changed(); si.focus(); });
      }
    }
    const fb = $('libFiltBtn'); if (fb) fb.addEventListener('click', toggle);
    const cl = $('libFiltClear'); if (cl) cl.addEventListener('click', () => clear());
    refreshUi();
  }

  /** 件数の表示: 「85曲・120譜面（全1131曲）」。曲が1つも無ければ空。走査中は「読み込み中 340/1131」を足す（c.scan） */
  // 件数は見出しの行の残りの幅に入れる（lib-layout.js）。入りきらない時は短い形（「85曲・120譜面」→「85曲」）にし、それでも入らなければ…で省略。
  // 走査中の短い形は進み具合の数字を残す（「85曲　340/1131」→「340/1131」）。全文はツールチップ
  let countForms = [];
  function renderCount(c) {
    const el = $('libCount'); if (!el) return;
    // 曲・譜面の数は単数と複数で訳を分ける（英語の「1 songs」を避ける。日本語は同じ）
    const songs = tf(c.songs === 1 ? 'lib.songs1' : 'lib.songsN', '{n}曲', { n: c.songs }),
      rows = tf(c.rows === 1 ? 'lib.charts1' : 'lib.chartsN', '{n}譜面', { n: c.rows });
    lastCount = c.total ? tf('lib.count', '{songs}・{rows}（全{total}曲）', { songs, rows, total: c.total }) : '';
    countForms = c.total ? [lastCount, tf('lib.countShort', '{songs}・{rows}', { songs, rows }), songs] : [''];
    if (c.scan) {
      const sc = tf('lib.countScan', '読み込み中 {done}/{total}', c.scan), prog = `${c.scan.done}/${c.scan.total}`;
      lastCount += (lastCount ? '　' : '') + sc;
      const songs = c.total ? countForms[2] : '';
      countForms = countForms.map(s => s + (s ? '　' : '') + sc);
      if (songs) countForms.push(songs + '　' + prog);
      countForms.push(prog);
    }
    el.title = lastCount;
    el.classList.toggle('on', active());
    fitCmin(el);
    fitCount();
  }
  /** 件数の一番短い形の幅を、組（フィルター・件数・解除）の折り返しを決める基準の幅に入れる（CSS の --lib-cmin。CSS の px で測る）。
   * 件数が変わった時だけ（ResizeObserver の中で組の幅を変えると「ResizeObserver loop」になるため、fitCount からは呼ばない） */
  let cminW = null, measCtx = null;
  function fitCmin(el) {
    const grp = $('libFiltGrp'), last = countForms[countForms.length - 1] || '';
    if (!grp) return;
    let w = 0;
    if (last) { try { measCtx = measCtx || document.createElement('canvas').getContext('2d'); measCtx.font = getComputedStyle(el).font; w = Math.ceil(measCtx.measureText(last).width) + 2; } catch (_) { w = 44; } }
    if (w !== cminW) { cminW = w; grp.style.setProperty('--lib-cmin', w + 'px'); }
  }
  function fitCount() {
    const el = $('libCount'); if (!el) return;
    el.textContent = countForms[0] || '';
    if (countForms.length < 2 || !el.clientWidth) return;
    // 文字の幅は小数まで比べる（scrollWidth は整数に丸めるため、1px 未満のはみ出しで…が出ても気付けない）
    const rg = document.createRange();
    for (let i = 1; i < countForms.length; i++) {
      rg.selectNodeContents(el);
      if (rg.getBoundingClientRect().width <= el.getBoundingClientRect().width + 0.05) return;
      el.textContent = countForms[i];
    }
  }
  { const g = $('libFiltGrp') || $('libCount'); if (g && typeof ResizeObserver === 'function') new ResizeObserver(() => fitCount()).observe(g); }   // 組の幅は中身で変わらない（flex の基準の幅＋残り）＝描き直しが続かない

  return {
    rowMatches, matchText, condActive, condCount, active, renderCount, clear, open, close, isOpen,
    state: () => JSON.parse(JSON.stringify(f)),
    countText: () => lastCount,
    relabel() { refreshUi(); },
  };
}

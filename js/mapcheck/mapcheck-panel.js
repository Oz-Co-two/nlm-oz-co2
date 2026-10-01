// 譜面チェック（BeatLeader基準）の結果パネル。判定そのものは mapcheck.js。
// 非モーダルの浮きパネル＝開いたまま譜面を直して「再チェック」できる。拍をクリックするとその位置へ移動・選択する
import { runMapCheck, STATUS, CHECK_NAMES } from './mapcheck.js';
import { runBlCriteria } from './blcriteria.js';
import { blView } from './blcriteria-view.js';

// 項目の日本語名（{}はチェックが返す数値）。英語版は lang/en.json の mc.k.* で上書きされる
const JA = {
  timingDifference: '1つ上の難易度（{above}）に無いタイミング',
  invalidNote: '不正なノーツ（位置・向きが範囲外）', invalidBomb: '不正なボム（位置が範囲外）', invalidArc: '不正なアーク',
  invalidChain: '不正なチェーン', invalidObstacle: '不正な壁（長さ・幅・高さが0以下）', invalidRotation: '不正な回転イベント',
  invalidWaypoint: '不正なウェイポイント', invalidEvent: '不正なライトイベント（種別が範囲外）',
  invalidLightColor: '不正なライトカラーのイベントボックス', invalidLightRotation: '不正なライト回転のイベントボックス',
  invalidLightTranslation: '不正なライト移動のイベントボックス', invalidFx: '不正なFXのイベントボックス',
  beforeStart: '曲の開始前にある{what}', afterEnd: '曲の終わりより後ろにある{what}',
  hotStart: '開始直後にノーツ（{sec}秒・1.5秒未満）',
  njsUnset: 'NJSが未設定', njsHigh: 'NJSが高すぎる（{v}・23超）', njsLow: 'NJSが低すぎる（{v}・3未満）',
  jdVeryHigh: '飛来距離（JD）がとても長い（{v}・36超）', jdVeryLow: '飛来距離（JD）がとても短い（{v}・18未満）',
  jdHigh: '飛来距離（JD）が長め（{v}超・NJSとオフセットが遊びにくい可能性）',
  rtQuick: '反応時間がとても短い（{ms}ms・420ms未満）', negOffset: '意味の無いマイナスのオフセット（{v}拍より短くはならない）',
  diffLabel: '難易度ラベルが長すぎる（{n}文字・30文字まで）',
  insufficientLight: 'ライトイベントが足りない（点灯が11個以上必要）', unknownLight: 'v3環境のライトは目視での確認が必要',
  invalidEbgId: 'イベントボックスのグループIDがこの環境に無い', invalidEbgFilter: 'イベントボックスのフィルタが範囲外',
  unlitBomb: '照らされていないボム',
  oneSaber: '片方の色のノーツしか無い（One Saber以外）', excessiveDouble: '両手同時が多すぎる（{perc}%）',
  ebpm: '実効BPMが高い（{thres}超）', ebpmSwing: '実効BPMが高い・スイング単位（{thres}超）',
  acceptablePrec: '1/8・1/6 の拍に乗っていない', varySwing: 'スライダーの速さが一定でない',
  slowSlider: '遅いスライダー（{ms}msより遅い）', inlineAngle: '同じ位置での急な角度変化', shradoAngle: 'シュラド角（負の曲率になる角度）',
  improperArc: '不適切なアーク', improperChain: '不適切なチェーン（頭のノーツと合っていない）',
  unrankableChain: 'ランク不可のチェーン（開始直後・枠外のリンク・詰めすぎ）', improperWindow: '斜めウィンドウの不適切なスナップ',
  hitboxStair: 'ヒットボックスの階段', hitboxReverseStair: 'ヒットボックスの逆階段', hitboxInline: 'ヒットボックスの重なり（同じ列）',
  hitboxPath: 'スイング経路のヒットボックスの重なり', parallelNotes: '平行ノーツ', handclap: '手拍子になる配置',
  hammerHit: 'ハンマーヒット（ボムに向かって振る）', stackedNote: '重なったノーツ', stackedBomb: '重なったボム',
  doubleDirectional: '同じ向きへの連続スイング', visionBlock: '視界妨害（中央のノーツの後ろ）',
  shortObstacle: '短すぎる壁（15ms未満）', centerObstacle: '中央の2マス幅の壁（回復{ms}ms未満）', zeroObstacle: '値が0の壁',
  audioShort: '音源が短すぎる（{sec}秒・20秒未満はランク不可）', noAudio: '音源がありません',
  coverNotSquare: 'カバー画像が正方形でない（{w}×{h}）', coverSmall: 'カバー画像が小さい（{w}×{h}・256×256以上が必要）',
  noCover: 'カバー画像がありません', previewDefault: '試聴区間が初期値のまま（12秒から10秒間）',
  checkFailed: '判定中にエラー（{name}: {err}）',
};
// 「曲の開始前/終わりより後ろにある◯◯」の◯◯
const WHAT = {
  'Note': 'ノーツ', 'Bomb': 'ボム', 'Obstacle': '壁', 'Arc': 'アーク', 'Chain': 'チェーン', 'Rotation Event': '回転イベント',
  'Basic Event': 'ライトイベント', 'Color Boost Event': 'カラーブースト', 'Waypoint': 'ウェイポイント',
  'Light Color Event Box Group': 'ライトカラーのイベントボックス', 'Light Rotation Event Box Group': 'ライト回転のイベントボックス',
  'Light Translation Event Box Group': 'ライト移動のイベントボックス', 'FX Event Box Group': 'FXのイベントボックス',
  'Light Color Event': 'ライトカラーのイベント', 'Light Rotation Event': 'ライト回転のイベント',
  'Light Translation Event': 'ライト移動のイベント', 'FX Event': 'FXのイベント',
};
const ST = {
  [STATUS.RANK]: { ic: '🚧', ja: 'ランク不可', k: 'mc.st.rank', tip: 'mc.st.rankTip', tipJa: 'ランク基準を満たさない（直さないとランク申請が通らない）' },
  [STATUS.ERROR]: { ic: '❌', ja: 'エラー', k: 'mc.st.error', tip: 'mc.st.errorTip', tipJa: '大きな問題。理由が無ければ直す' },
  [STATUS.WARN]: { ic: '❗', ja: '警告', k: 'mc.st.warn', tip: 'mc.st.warnTip', tipJa: '問題の可能性。確認して必要なら直す' },
  [STATUS.INFO]: { ic: '⚠️', ja: '情報', k: 'mc.st.info', tip: 'mc.st.infoTip', tipJa: '軽微または問題ではない。参考' },
};
const ORDER = [STATUS.RANK, STATUS.ERROR, STATUS.WARN, STATUS.INFO];
const CHIP_MAX = 80;   // 1項目に最初に並べる拍の数（残りは「他N件」で展開）

export function installMapCheckPanel(api) {
  const { t, escHtml, collect, jump, dispDiff } = api;
  const fill = (s, vars) => { if (vars) for (const k in vars) s = s.split('{' + k + '}').join(String(vars[k])); return s; };
  const labelOf = r => {
    const vars = { ...(r.vars || {}) };
    if (vars.what) vars.what = t('mc.what.' + vars.what, WHAT[vars.what] || vars.what);
    if (vars.above) vars.above = dispDiff(vars.above);
    return fill(t('mc.k.' + r.key, JA[r.key] || r.label), vars);
  };
  const fmtBeat = b => String(Math.round(b * 1000) / 1000);
  const fmtSec = s => { if (!isFinite(s)) return ''; const m = Math.floor(s / 60), r = s - m * 60; return m + ':' + r.toFixed(3).padStart(6, '0'); };

  let el = null, last = null, busy = false, input = null, blRes = null;
  const expanded = new Set();   // 「他N件」を開いた項目（再描画しても開いたまま）
  // タブ: 'mc'＝BS Map Check と同じ判定 / 'bl'＝NLM版 BeatLeader評価リスト（開いているタブだけは覚えておく）
  let tab = 'mc'; try { if (localStorage.getItem('bsnm_mcTab') === 'bl') tab = 'bl'; } catch (_) {}
  const blSt = { onlyIssues: false, stars: {}, expanded };   // ★/Techはアプリを開いている間だけ保持
  const blv = blView({ t, escHtml, dispDiff, mcLabel: key => t('mc.k.' + key, JA[key] || key) });
  const runBl = () => {
    blRes = null;
    if (!input || !last || last.error) return;
    try { blRes = runBlCriteria({ ...input, stars: blSt.stars }, last); } catch (e) { blRes = { error: String(e && e.message || e) }; }
  };

  function build() {
    el = document.createElement('div'); el.id = 'mcPanel';
    el.innerHTML = `<div class="mcHead"><span class="mcTitle"></span><span class="mcHeadBtns">
        <button class="mcRerun"></button><button class="mcClose" aria-label="close">✕</button></span></div>
      <div class="mcTabs"><button class="mcTab" data-tab="mc"></button><button class="mcTab" data-tab="bl"></button></div>
      <div class="mcSum"></div><div class="mcBody"></div><div class="mcFoot"></div>`;
    document.body.appendChild(el);
    el.querySelector('.mcClose').addEventListener('click', close);
    el.querySelector('.mcRerun').addEventListener('click', () => run());
    el.querySelectorAll('.mcTab').forEach(b => b.addEventListener('click', () => {
      tab = b.dataset.tab; try { localStorage.setItem('bsnm_mcTab', tab); } catch (_) {}
      el.querySelector('.mcBody').scrollTop = 0; render();
    }));
    const body = el.querySelector('.mcBody');
    body.addEventListener('click', ev => {   // 拍チップと「他N件」は描画し直すので委譲で受ける（パネル本体は固定要素）
      const more = ev.target.closest('.mcMore');
      if (more) { expanded.add(more.dataset.id); render(); return; }
      const chip = ev.target.closest('.mcBeat'); if (!chip || !last) return;
      const ref = chip.dataset.ref.split(':');
      let dn = null, o = null;
      if (ref[0] === 'bl') {   // bl:項目:所見:対象
        const r = blRes && blRes.rules && blRes.rules[+ref[1]], f = r && r.findings[+ref[2]];
        if (f && f.objs) { dn = f.d; o = f.objs[+ref[3]]; }
      } else {
        const [di, ri, oi] = ref.map(Number), d = last.diffs[di], r = d && d.results[ri];
        if (d && r && r.objs) { dn = d.difficulty; o = r.objs[oi]; }
      }
      if (!o || !dn) return;
      el.querySelectorAll('.mcBeat.cur').forEach(x => x.classList.remove('cur')); chip.classList.add('cur');
      jump(dn, o);
    });
    body.addEventListener('change', ev => {   // BL評価リストの「違反・要確認だけ」と★/Tech（入力を確定した時だけ描き直す）
      const x = ev.target;
      if (x.classList.contains('blOnlyChk')) { blSt.onlyIssues = x.checked; render(); return; }
      const dn = x.dataset.star || x.dataset.tech; if (!dn) return;
      const v = x.value === '' ? undefined : Math.max(0, +x.value);
      blSt.stars[dn] = { ...(blSt.stars[dn] || {}), [x.dataset.star ? 'star' : 'tech']: v };
      runBl(); render();
    });
    // 見出しをつかんで移動（画面外へは出さない）
    const head = el.querySelector('.mcHead');
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

  function statusCounts(results) {
    const c = {}; for (const s of ORDER) c[s] = 0;
    for (const r of results) c[r.status] = (c[r.status] || 0) + 1;
    return c;
  }
  const countsHTML = c => ORDER.filter(s => c[s]).map(s =>
    `<span class="mcCnt st-${s}" title="${escHtml(t(ST[s].tip, ST[s].tipJa))}">${ST[s].ic} ${escHtml(t(ST[s].k, ST[s].ja))} ${c[s]}</span>`).join('');

  function itemHTML(r, di, ri) {
    const lab = labelOf(r), en = r.label && r.label !== lab ? `<span class="mcEn">${escHtml(r.label)}</span>` : '';
    let beats = '';
    if (r.objs && r.objs.length) {
      const id = di + ':' + ri, all = expanded.has(id), n = all ? r.objs.length : Math.min(CHIP_MAX, r.objs.length);
      const chips = [];
      for (let oi = 0; oi < n; oi++) {
        const o = r.objs[oi];
        if (oi > 0 && Math.abs(o.beat - r.objs[oi - 1].beat) < 1e-6) continue;   // 同じ拍は1つにまとめる（原作と同じ）
        chips.push(`<span class="mcBeat" data-ref="${di}:${ri}:${oi}" title="${escHtml(fmtSec(o.sec))}">${escHtml(fmtBeat(o.beat))}</span>`);
      }
      beats = `<div class="mcBeats">${chips.join('')}${n < r.objs.length
        ? `<span class="mcMore" data-id="${id}">${escHtml(t('mc.more', '他{n}件').replace('{n}', r.objs.length - n))}</span>` : ''}</div>`;
    }
    const cnt = r.objs ? `<span class="mcN">${new Set(r.objs.map(o => o.beat)).size}</span>` : '';
    return `<div class="mcItem st-${r.status}"><div class="mcLine"><span class="mcIc" title="${escHtml(t(ST[r.status].tip, ST[r.status].tipJa))}">${ST[r.status].ic}</span>`
      + `<span class="mcLab">${escHtml(lab)}</span>${cnt}${en}</div>${beats}</div>`;
  }
  const sortByStatus = list => list.map((r, i) => [r, i]).sort((a, b) => ORDER.indexOf(a[0].status) - ORDER.indexOf(b[0].status) || a[1] - b[1]);

  function render() {
    if (!el) return;
    el.classList.toggle('blMode', tab === 'bl');
    el.querySelectorAll('.mcTab').forEach(b => b.classList.toggle('on', b.dataset.tab === tab));
    el.querySelector('.mcTab[data-tab="mc"]').textContent = t('mc.tabMc', 'BS Map Check と同じ判定');
    el.querySelector('.mcTab[data-tab="bl"]').textContent = t('mc.tabBl', 'NLM版 BL評価リスト');
    if (tab === 'bl') return renderBl();
    el.querySelector('.mcTitle').textContent = t('mc.title', '譜面チェック（BeatLeader基準）');
    el.querySelector('.mcRerun').textContent = busy ? t('mc.running', 'チェック中…') : t('mc.rerun', '↻ 再チェック');
    el.querySelector('.mcRerun').disabled = busy;
    el.querySelector('.mcFoot').innerHTML = escHtml(t('mc.foot', '判定は BS Map Check（KivalEvan・MIT）の BeatLeader プリセットと同じです。拍をクリックするとその位置へ移動します。'))
      + `<br><span class="mcFootSub">${escHtml(t('mc.checked', '{n}項目をチェック').replace('{n}', CHECK_NAMES.length))}</span>`;
    const body = el.querySelector('.mcBody'), sum = el.querySelector('.mcSum');
    if (!last) { body.innerHTML = ''; sum.textContent = ''; return; }
    if (last.error) { sum.textContent = ''; body.innerHTML = `<div class="mcErr">${escHtml(last.error)}</div>`; return; }
    const all = [...last.general, ...last.diffs.flatMap(d => d.results)];
    const tot = statusCounts(all);
    sum.innerHTML = (tot[STATUS.RANK] || tot[STATUS.ERROR]) ? countsHTML(tot)
      : `<span class="mcOk">✓ ${escHtml(t('mc.noBlocking', 'ランク不可・エラーはありません'))}</span>${countsHTML(tot)}`;
    const parts = [];
    const gen = sortByStatus(last.general).map(([r]) => itemHTML(r, -1, 0)).join('');
    parts.push(`<details class="mcSec" open><summary>${escHtml(t('mc.general', '全体（音源・カバー・試聴）'))}${countsHTML(statusCounts(last.general))}</summary>${gen || `<div class="mcNone">${escHtml(t('mc.none', '問題は見つかりませんでした'))}</div>`}</details>`);
    last.diffs.forEach((d, di) => {
      const items = d.error ? `<div class="mcErr">${escHtml(d.error)}</div>`
        : (sortByStatus(d.results).map(([r, ri]) => itemHTML(r, di, ri)).join('') || `<div class="mcNone">${escHtml(t('mc.none', '問題は見つかりませんでした'))}</div>`);
      parts.push(`<details class="mcSec" open><summary>${escHtml(dispDiff(d.difficulty))}${countsHTML(statusCounts(d.results))}</summary>${items}</details>`);
    });
    const opened = [...body.querySelectorAll('details.mcSec:not(.blSec)')].map(x => x.open), sc = body.scrollTop;
    body.innerHTML = parts.join('');
    body.querySelectorAll('details.mcSec').forEach((x, i) => { if (i < opened.length) x.open = opened[i]; });   // 再チェックしても開閉とスクロール位置は保つ
    body.scrollTop = sc;
  }

  function renderBl() {
    el.querySelector('.mcTitle').textContent = t('mc.title', '譜面チェック（BeatLeader基準）');
    el.querySelector('.mcRerun').textContent = busy ? t('mc.running', 'チェック中…') : t('mc.rerun', '↻ 再チェック');
    el.querySelector('.mcRerun').disabled = busy;
    el.querySelector('.mcFoot').innerHTML = escHtml(t('bl.foot', '✖違反＝基準の数値に反する　⚠要確認＝違反の候補・正当化が必要な所　☐手動確認＝自動では判定できない項目。拍をクリックするとその位置へ移動します。'))
      + `<br><span class="mcFootSub">${escHtml(t('bl.footSub', '出典: beatleader.wiki の Ranking Criteria（{date}取得）。基準は予告なく変わることがあります。').replace('{date}', (blRes && blRes.date) || ''))}</span>`;
    const body = el.querySelector('.mcBody'), sum = el.querySelector('.mcSum');
    sum.textContent = '';
    if (!last) { body.innerHTML = ''; return; }
    const err = last.error || (blRes && blRes.error);
    if (err || !blRes) { body.innerHTML = err ? `<div class="mcErr">${escHtml(err)}</div>` : ''; return; }
    const opened = new Map([...body.querySelectorAll('details.blSec')].map(x => [x.dataset.sec, x.open])), sc = body.scrollTop;
    body.innerHTML = blv.render(blRes, blSt, CHIP_MAX);
    body.querySelectorAll('details.blSec').forEach(x => { if (opened.has(x.dataset.sec)) x.open = opened.get(x.dataset.sec); });
    body.scrollTop = sc;
  }

  async function run() {
    if (busy) return; busy = true; render();
    try {
      const p = await collect();
      if (p.error) { last = { error: p.error }; input = null; }
      else { input = p; last = runMapCheck(p); expanded.clear(); }
    } catch (e) { last = { error: String(e && e.message || e) }; input = null; }
    runBl();
    busy = false; render();
  }
  function open() { if (!el) build(); el.style.display = 'flex'; render(); run(); }
  function close() { if (el) el.style.display = 'none'; }
  return { open, close, run, isOpen: () => !!el && el.style.display !== 'none' };
}

// 譜面チェック（BeatLeader基準）の結果パネル。判定そのものは mapcheck.js。
// 非モーダルの浮きパネル＝開いたまま譜面を直して「再チェック」できる。拍をクリックするとその位置へ移動・選択する
// 結果は全難易度の分を出すが、開いておくのは今の難易度（と全体）だけ（2026-11-03・利用者の要望: 別の難易度の拍を今の難易度の物と取り違える）。
//  - 別の難易度は閉じた見出し（数は見える）。BL評価リストは所見の行を残し拍だけ隠す（行を押すと出す）。難易度を切り替えたら開き直す（diffChanged）
//  - 別の難易度の拍を押したら「切り替えますか？」と確かめてから切り替える（ask）。同じ難易度の拍はそのまま移動
//  - 開閉の既定に戻すのは今の難易度が変わった時だけ（再チェック・タブの行き来では利用者が開け閉めした状態を保つ）
import { runMapCheck, STATUS, CHECK_NAMES } from './mapcheck.js';
import { runBlCriteria, BL } from './blcriteria.js';
import { blView } from './blcriteria-view.js';
import { blStars } from './bl-stars.js';
import { amView } from '../automodder/automodder-view.js';

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
// ライトが足りない項目（自動ライティングで直せるもの）: BS Map Check の項目キー / BL評価リストの所見キー
const LIGHT_FIX_MC = new Set(['insufficientLight', 'unlitBomb']);
const LIGHT_FIX_BL = new Set(['lightFew', 'noLightAtAll', 'bombDark']);
// カバー画像の寸法・形式の項目（カバー画像の補正で直せるもの）
const COVER_FIX_MC = new Set(['coverNotSquare', 'coverSmall']);
const COVER_FIX_BL = new Set(['coverRatio', 'coverSize', 'coverFormat']);

export function installMapCheckPanel(api) {
  // autoLight / coverFix (終わったら呼ぶ関数)＝自動ライティング / カバー画像の補正の確認を開く（無ければボタンを出さない）
  // rating＝難易度を測るプラグインの窓口（rating-client.js）。BL評価リストの★/Techを自動で入れる（無ければ手入力だけ）
  // automodder＝AutoModder の判定のプラグインの窓口（automodder-client.js）。3つ目のタブ（無ければタブを出さない）
  // curDiff()＝今開いている難易度の名前（Easy〜ExpertPlus・無ければ null） / ask(文, はい, いいえ)＝確認の画面（はい＝true の Promise）
  const { t, escHtml, collect, jump, dispDiff, autoLight, coverFix, rating, automodder, curDiff, ask } = api;
  const FIX = { autolight: [autoLight, 'mc.fixAutoLight', '💡 自動ライティング…'], cover: [coverFix, 'mc.fixCover', '🖼 カバー画像を補正…'] };
  const fixBtn = (kind = 'autolight') => FIX[kind][0] ? `<button class="mcFix" data-fix="${kind}">${escHtml(t(FIX[kind][1], FIX[kind][2]))}</button>` : '';
  const fixKindMc = key => LIGHT_FIX_MC.has(key) ? 'autolight' : COVER_FIX_MC.has(key) ? 'cover' : null;
  const fixKindBl = key => LIGHT_FIX_BL.has(key) ? 'autolight' : COVER_FIX_BL.has(key) ? 'cover' : null;
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
  // タブ: 'mc'＝BS Map Check と同じ判定 / 'bl'＝NLM版 BeatLeader評価リスト / 'am'＝AutoModder の判定（開いているタブだけは覚えておく）
  let tab = 'mc'; try { const v = localStorage.getItem('bsnm_mcTab'); if (v === 'bl' || (v === 'am' && automodder)) tab = v; } catch (_) {}
  const otherOpen = new Set();   // BL評価リストで拍を出した、別の難易度の所見（bl:項目:所見）。今の難易度が変わったら閉じる
  const blSt = { onlyIssues: false, expanded, cur: null, otherOpen };
  const cdNow = () => (curDiff ? curDiff() : null);
  let shownDiff;   // 開閉の既定を決めた時の今の難易度（違えば次の描画で既定に戻す）
  // タブごとの開閉（data-sec → open）。描き直す前に、今パネルに描いてあるタブ（bodyTab）の開閉をここへ控える。以前は描き直す前の中身から読んでいて、
  // 別のタブから戻ると、そのタブの中身しか無く既定に戻っていた（タブの行き来で開け閉めが消えた・2026-11-15）
  const openMem = { mc: new Map(), bl: new Map(), am: new Map() };
  let bodyTab = null;
  let curChip = null, reveal = false, asking = false;   // 押した拍のチップ [タブ, data-ref]（描き直しても印を残す）・切り替えた後に見える所へ出す・確認の画面を出している
  const stars = blStars({ t, escHtml, dispDiff, rating });   // ★/Tech の欄（自動計算・手入力。アプリを開いている間だけ保持）
  const blv = blView({ t, escHtml, dispDiff, mcLabel: key => t('mc.k.' + key, JA[key] || key),
    fixHTML: f => fixKindBl(f.key) && (f.status === BL.FAIL || f.status === BL.CHECK) ? fixBtn(fixKindBl(f.key)) : '',
    starsHTML: diffs => stars.html(diffs) });
  const runBl = () => {
    blRes = null;
    if (!input || !last || last.error) return;
    try { blRes = runBlCriteria({ ...input, stars: stars.values(input.diffs.map(d => d.difficulty)) }, last); } catch (e) { blRes = { error: String(e && e.message || e) }; }
  };
  // BL評価リストを見ている時だけ、★/Tech を自動で測る（プラグインがあれば。譜面が前回測った時のままなら測り直さない）
  const autoRate = async () => {
    if (!rating || tab !== 'bl' || !isOpen() || !last || last.error) return;
    await rating.ensureStatus();   // PCの中の確認だけ（GitHubへは通信しない）
    if (rating.installed() && tab === 'bl' && isOpen()) rating.measure({ ifChanged: true });
  };
  // 測り終わった・取り込んだ等 → 判定をやり直して描き直す。★/Techの欄に入力中なら、欄を離れるまで描き直さない（打っている途中の値が消えるため）
  let renderLater = false;
  const typingStars = () => { const a = document.activeElement; return !!(a && a.tagName === 'INPUT' && a.closest('#mcPanel .blStars')); };
  const amv = automodder ? amView({ t, escHtml, dispDiff, am: automodder }) : null;
  // AutoModder のタブを見ている時だけ動かす（プラグインがあれば。譜面が前回確かめた時のままなら動かし直さない）
  const autoAm = async () => {
    if (!automodder || tab !== 'am' || !isOpen()) return;
    await automodder.ensureStatus();   // PCの中の確認だけ（GitHubへは通信しない）
    if (automodder.installed() && tab === 'am' && isOpen()) automodder.run({ ifChanged: true });
  };
  if (automodder) automodder.subscribe(() => { if (isOpen() && tab === 'am') render(); });
  if (rating) rating.subscribe(() => {
    if (!isOpen()) return;
    runBl();
    if (tab !== 'bl') return;
    if (typingStars()) renderLater = true; else render();
  });

  function build() {
    el = document.createElement('div'); el.id = 'mcPanel';
    el.innerHTML = `<div class="mcHead"><span class="mcTitle"></span><span class="mcHeadBtns">
        <button class="mcRerun"></button><button class="mcClose" aria-label="close">✕</button></span></div>
      <div class="mcTabs"><button class="mcTab" data-tab="mc"></button><button class="mcTab" data-tab="bl"></button>${automodder ? '<button class="mcTab" data-tab="am"></button>' : ''}</div>
      <div class="mcSum"></div><div class="mcBody"></div><div class="mcFoot"></div>`;
    document.body.appendChild(el);
    el.querySelector('.mcClose').addEventListener('click', close);
    el.querySelector('.mcRerun').addEventListener('click', () => run());
    el.querySelectorAll('.mcTab').forEach(b => b.addEventListener('click', () => {
      tab = b.dataset.tab; try { localStorage.setItem('bsnm_mcTab', tab); } catch (_) {}
      el.querySelector('.mcBody').scrollTop = 0; render(); autoRate(); autoAm();
    }));
    const body = el.querySelector('.mcBody');
    body.addEventListener('click', ev => {   // 拍チップと「他N件」は描画し直すので委譲で受ける（パネル本体は固定要素）
      if (stars.onClick(ev)) { runBl(); render(); return; }   // ★/Tech の欄のボタン（自動計算・取り込み・自動に戻す）
      if (amv && amv.onClick(ev)) { render(); return; }   // AutoModder のタブのボタン（取り込み・もう一度・更新の確認）
      const fx = ev.target.closest('.mcFix');
      if (fx) { const fn = FIX[fx.dataset.fix] && FIX[fx.dataset.fix][0]; if (fn) fn(() => run()); return; }   // 直したらチェックし直す
      const more = ev.target.closest('.mcMore');
      if (more) { expanded.add(more.dataset.id); render(); return; }
      const chip = ev.target.closest('.mcBeat');
      if (chip) { if (last) onChip(chip); return; }
      const oth = ev.target.closest('.blOther');   // BL評価リストの別の難易度の所見の行＝拍を出す・隠す
      if (oth) { const k = oth.dataset.oref; if (otherOpen.has(k)) otherOpen.delete(k); else otherOpen.add(k); render(); }
    });
    body.addEventListener('change', ev => {   // BL評価リストの「違反・要確認だけ」と★/Tech（入力を確定した時だけ描き直す）
      const x = ev.target;
      if (x.classList.contains('blOnlyChk')) { blSt.onlyIssues = x.checked; render(); return; }
      if (amv && amv.onChange(ev)) return;   // AutoModder のタブの版の選択
      // 描き直しは、クリックした次の欄にフォーカスが移ってから（同期で描き直すと、移る先の欄が消えてフォーカスが外れる）
      if (stars.onChange(x)) { runBl(); setTimeout(render, 0); }
    });
    body.addEventListener('focusout', () => {   // 入力中に測り終わっていたら、欄を離れた時に描き直す
      if (renderLater) setTimeout(() => { if (renderLater && !typingStars()) render(); }, 0);
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

  // 拍のチップ → 飛ぶ先 {dn, o}（無ければ null）
  function chipTarget(ref) {
    let dn = null, o = null;
    if (ref[0] === 'am') {   // am:結果:物（AutoModder のタブ）
      const r = amv && amv.ref(ref); if (r) { dn = r.dn; o = r.o; }
    } else if (ref[0] === 'bl') {   // bl:項目:所見:対象
      const r = blRes && blRes.rules && blRes.rules[+ref[1]], f = r && r.findings[+ref[2]];
      if (f && f.objs) { dn = f.d; o = f.objs[+ref[3]]; }
    } else {
      const [di, ri, oi] = ref.map(Number), d = last.diffs[di], r = d && d.results[ri];
      if (d && r && r.objs) { dn = d.difficulty; o = r.objs[oi]; }
    }
    return o && dn ? { dn, o } : null;
  }
  // 拍のチップを押した: 今の難易度ならそのまま移動。別の難易度なら切り替えてよいかを確かめてから（切り替えた後の描画でチップを見える所へ出す）
  async function onChip(chip) {
    const ref = chip.dataset.ref, g = chipTarget(ref.split(':'));
    if (!g || asking) return;
    const cd = cdNow();
    if (g.dn !== cd && ask) {
      asking = true;
      let ok = false;
      try {
        ok = await ask(fill(t('mc.switchAsk', 'この結果は {diff} の物です（今開いているのは {cur}）。\n{diff} に切り替えて表示しますか？'),
          { diff: dispDiff(g.dn), cur: cd ? dispDiff(cd) : '—' }),
        fill(t('mc.switchYes', '{diff} に切り替える'), { diff: dispDiff(g.dn) }), t('word.cancel', 'キャンセル'));
      } finally { asking = false; }
      if (!ok) return;
      reveal = true;
    }
    curChip = [tab, ref];
    markCur();
    jump(g.dn, g.o);
  }
  // 押したチップに印（描き直した後も）。切り替えた直後なら見える所へ出す（閉じた見出しの中にある間は出さずに待つ）
  function markCur() {
    if (!el) return;
    el.querySelectorAll('.mcBeat.cur').forEach(x => x.classList.remove('cur'));
    if (!curChip || curChip[0] !== tab) return;
    const c = el.querySelector(`.mcBody .mcBeat[data-ref="${CSS.escape(curChip[1])}"]`);
    if (!c) return;
    c.classList.add('cur');
    if (reveal && c.getClientRects().length) { reveal = false; c.scrollIntoView({ block: 'nearest' }); }
  }
  // 見出しの「編集中」の札（今開いている難易度）
  const curTag = () => `<span class="mcCurTag" title="${escHtml(t('mc.curTip', '今開いている難易度です。他の難易度の結果は閉じてあります（見出しを押すと開きます）'))}">${escHtml(t('mc.curDiff', '編集中'))}</span>`;
  // 今パネルに描いてあるタブの開閉（data-sec ごと）を控える（render の頭で呼ぶ）
  function saveOpen() {
    const m = bodyTab && openMem[bodyTab];
    if (m) el.querySelectorAll('.mcBody details[data-sec]').forEach(x => m.set(x.dataset.sec, x.open));
  }
  // 描いた後に、控えた開閉を戻す（控えの無い節は既定のまま）
  const applyOpen = (body, k) => { bodyTab = k; const m = openMem[k]; body.querySelectorAll('details[data-sec]').forEach(x => { if (m.has(x.dataset.sec)) x.open = m.get(x.dataset.sec); }); };

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
      + `<span class="mcLab">${escHtml(lab)}</span>${cnt}${en}${fixKindMc(r.key) ? fixBtn(fixKindMc(r.key)) : ''}</div>${beats}</div>`;
  }
  const sortByStatus = list => list.map((r, i) => [r, i]).sort((a, b) => ORDER.indexOf(a[0].status) - ORDER.indexOf(b[0].status) || a[1] - b[1]);

  function render() {
    if (!el) return;
    const cd = cdNow(), fresh = cd !== shownDiff;   // 今の難易度が変わった＝開閉を既定（今の難易度だけ開く）に戻す
    saveOpen();
    // BL評価リストの節（R1〜）は難易度の区切りではない＝難易度を切り替えても開閉を保つ（別の難易度の所見の拍は otherOpen）
    if (fresh) { shownDiff = cd; otherOpen.clear(); openMem.mc.clear(); openMem.am.clear(); }
    el.classList.toggle('blMode', tab === 'bl');
    el.classList.toggle('amMode', tab === 'am');
    el.querySelectorAll('.mcTab').forEach(b => b.classList.toggle('on', b.dataset.tab === tab));
    el.querySelector('.mcTab[data-tab="mc"]').textContent = t('mc.tabMc', 'BS Map Check と同じ判定');
    el.querySelector('.mcTab[data-tab="bl"]').textContent = t('mc.tabBl', 'NLM版 BL評価リスト');
    const amTab = el.querySelector('.mcTab[data-tab="am"]');
    if (amTab) { amTab.textContent = t('mc.tabAm', 'AutoModder'); amTab.title = t('mc.tabAmTip', 'AutoModder（既定の設定）の判定を、別配布のプラグインで動かした結果'); }
    if (tab === 'bl') renderBl(cd, fresh); else if (tab === 'am') renderAm(cd, fresh); else renderMc(cd, fresh);
    markCur();
  }

  function renderMc(cd, fresh) {
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
    parts.push(`<details class="mcSec" data-sec="mc:gen" open><summary>${escHtml(t('mc.general', '全体（音源・カバー・試聴）'))}${countsHTML(statusCounts(last.general))}</summary>${gen || `<div class="mcNone">${escHtml(t('mc.none', '問題は見つかりませんでした'))}</div>`}</details>`);
    last.diffs.forEach((d, di) => {
      const items = d.error ? `<div class="mcErr">${escHtml(d.error)}</div>`
        : (sortByStatus(d.results).map(([r, ri]) => itemHTML(r, di, ri)).join('') || `<div class="mcNone">${escHtml(t('mc.none', '問題は見つかりませんでした'))}</div>`);
      const isCur = d.difficulty === cd;   // 開いておくのは今の難易度だけ（判定の途中で止まった難易度も、気付けるよう開く）
      parts.push(`<details class="mcSec${isCur ? ' mcCurSec' : ''}" data-sec="mc:${escHtml(d.difficulty)}"${isCur || d.error ? ' open' : ''}><summary>${escHtml(dispDiff(d.difficulty))}${isCur ? curTag() : ''}${countsHTML(statusCounts(d.results))}</summary>${items}</details>`);
    });
    const sc = body.scrollTop;
    body.innerHTML = parts.join('');
    applyOpen(body, 'mc');   // 再チェック・タブの行き来でも開閉とスクロール位置は保つ
    body.scrollTop = sc;
  }

  function renderBl(cd, fresh) {
    renderLater = false;
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
    const sc = body.scrollTop;
    const a = typingStars() ? document.activeElement : null, fk = a && (a.dataset.star != null ? ['star', a.dataset.star] : ['tech', a.dataset.tech]);
    blSt.cur = cd;
    body.innerHTML = blv.render(blRes, blSt, CHIP_MAX);
    applyOpen(body, 'bl');
    body.scrollTop = sc;
    if (fk) { const n = body.querySelector(`.blStars input[data-${fk[0]}="${CSS.escape(fk[1])}"]`); if (n) n.focus(); }   // 入力中の★/Techの欄はフォーカスを戻す
  }

  function renderAm(cd, fresh) {
    el.querySelector('.mcTitle').textContent = t('mc.title', '譜面チェック（BeatLeader基準）');
    const ab = automodder.state.busy === 'run';
    el.querySelector('.mcRerun').textContent = busy || ab ? t('mc.running', 'チェック中…') : t('mc.rerun', '↻ 再チェック');
    el.querySelector('.mcRerun').disabled = busy || ab;
    el.querySelector('.mcFoot').innerHTML = amv.foot();
    el.querySelector('.mcSum').textContent = '';
    const body = el.querySelector('.mcBody');
    const sc = body.scrollTop;
    body.innerHTML = amv.render({ expanded, cur: cd, curTag: curTag() }, CHIP_MAX);
    applyOpen(body, 'am');   // 開閉とスクロール位置は保つ
    body.scrollTop = sc;
  }

  async function run() {
    if (busy) return; busy = true; render();
    try {
      const p = await collect();
      if (p.error) { last = { error: p.error }; input = null; }
      else { input = p; last = runMapCheck(p); expanded.clear(); otherOpen.clear(); curChip = null; }   // 結果の番号（data-ref）が変わるので、押した印・出した拍も外す
    } catch (e) { last = { error: String(e && e.message || e) }; input = null; }
    runBl();
    busy = false; render();
    autoRate(); autoAm();
  }
  /** 開いて確かめ直す。want＝そのタブで開く（メニューの3つの項目。'mc'/'bl'/'am'・無ければ前回のタブ） */
  function open(want) {
    if (want === 'mc' || want === 'bl' || (want === 'am' && automodder)) {
      if (want !== tab && el) el.querySelector('.mcBody').scrollTop = 0;
      tab = want; try { localStorage.setItem('bsnm_mcTab', tab); } catch (_) {}
    }
    if (!el) build(); el.style.display = 'flex'; render(); run();
  }
  function close() { if (el) el.style.display = 'none'; }
  function isOpen() { return !!el && el.style.display !== 'none'; }
  /** 本体が難易度を切り替えた後に呼ぶ（loadDiff の終わり）: 開いていれば、今の難易度の結果を開き他を閉じて描き直す */
  function diffChanged() { if (isOpen() && cdNow() !== shownDiff) render(); }
  return { open, close, run, isOpen, diffChanged };
}

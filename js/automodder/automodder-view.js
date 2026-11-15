// 譜面チェックのパネルの3つ目のタブ「AutoModder」の中身（タブの切り替え・拍のクリックは mapcheck-panel.js）。
// 判定は別配布のプラグイン nlm-automodder（AutoModder v1.6.6 の自動の確かめを改変せずに動かす .NET の exe）。状態・通信は automodder-client.js。
//  - プラグインが無ければ取り込みの案内。説明（配布元・大きさ・保存先）を見てから「取り込む」を押す2段階（bl-stars.js と同じ。署名なし exe の取り込みになるため）
//  - 結果は難易度ごと（曲の情報が先頭）・重さごと（Error → Warning → Inconclusive → Suggestion → Info → 参考）に、同じ項目・同じ文をまとめて拍を並べる。
//    開いておくのは曲の情報と今の難易度だけ（render の st.cur。別の難易度の拍の確認・切り替えは mapcheck-panel.js）
//    合格（Passed）は畳んだ1行、統計（Statistical Data）は1行。英語の文はそのまま出し、項目名だけ訳す（am.k.<項目名>）
//  - 「AutoModder の判定を NLM の中で動かした結果・公式の基準と違う所がある・難易度ごとに既定の設定」の断り書きを必ず出す（先頭の帯と下の注記）
//  - プラグインの出力の文字（曲名・難易度名を含む）はファイル由来なので、すべて escHtml を通す
// 項目名の日本語（AutoModder の CheckResult.Name。知らない名前は英語のまま）。英語版は lang/en.json の am.k.* で元の名前に戻る
const JA = {
  'Song Name': '曲名', 'Song SubName': 'サブタイトル', 'Song Author': '曲の作者', 'Creator': '作者（マッパー）',
  'Song Time Offset': '曲のオフセット', 'BPM': 'BPM', 'Difficulty Ordering': '難易度の並び', 'Song Preview': '試聴区間',
  'Hot Start': '開始直後の物', 'Cold End': '曲の終わりの余白', 'Mapped Duration': '譜面の長さ', 'Outside': '曲の外にある物',
  'Note Jump Speed': 'ノーツの速さ（NJS）', 'Requirements': '必須の Mod', 'Difficulty Label Name': '難易度名（不適切な語）',
  'Difficulty Label Size': '難易度名の長さ', 'Vision Block': '視界ブロック', 'Parity': 'パリティ', 'Parity Warning': 'パリティ（角度の差）',
  'Parity Inverted': 'パリティ（逆手）', 'Parity Mismatch': 'パリティの食い違い', 'Parity Debug': 'パリティ（調べ用）',
  'Fused Object': '重なった物', 'Hand Clap': '手拍子', 'Loloppe': '同じ色の平行ノーツ（Loloppe）', 'Swing Path': 'スイングの通り道',
  'Staircase': 'ヒットボックスの階段', 'Reverse Staircase': 'ヒットボックスの逆階段', 'Inline': 'インライン（低い NJS）',
  'Slider Precision': 'スライダーの刻み', 'Dot Spam': 'スイングの長さ（点の連打）', 'Chain': 'チェーン', 'Chain Duration': 'チェーンの長さ',
  'Chain Head': 'チェーンの頭', 'Chain Slice': 'チェーンのリンクの数', 'Chain Squish': 'チェーンの詰め', 'Chain Lead': 'チェーンのはみ出し',
  'Chain Rotation': 'チェーンの曲がり', 'Chain Flick': 'チェーンの後の間', 'Chain Consistency': 'チェーンの長さの揃い',
  'Early Chain': '最初の方のチェーン', 'Reversed Chain': '逆向きのチェーン', 'Wall': '壁', 'Wall Dodge': '壁よけ', 'Wall Length': '短すぎる壁',
  'Wall Size': '壁の大きさ', 'Forced Movement': '外の列へ動かす壁', 'Hidden': '壁に隠れた物', 'Visibility': '壁で見えにくい所',
  'Light': 'ライトの量', 'Average Light': 'ライトの量（平均）', 'Bomb Lit': 'ボムの明るさ', 'Timing': 'タイミングの違い',
  'Unexpected Speed': '急な速さ（EBPM）', 'Offbeat Note': '珍しい刻み', 'Inline Note': 'インライン', 'Flick Note': 'はじき',
  'Shrado Angle': 'シュラド角', 'AngleOffset Note': '角度のずらし', 'Statistical Data': '統計', 'Mod': '指摘',
};
// 重さ（AutoModder の Severity）。並べる順・印・名前。Warning と Inconclusive は AutoModder の画面の Questionable、Error は Unrankable
const SEV = {
  Error: { ic: '❌', ja: 'エラー（Unrankable）', tip: 'AutoModder の Unrankable（ランク不可）' },
  Warning: { ic: '❗', ja: '警告（Questionable）', tip: 'AutoModder の Questionable（要確認）' },
  Inconclusive: { ic: '❔', ja: '判定できず（Questionable）', tip: 'AutoModder の Questionable（自動では判定できない）' },
  Suggestion: { ic: '💡', ja: '提案', tip: 'AutoModder の提案' },
  Info: { ic: 'ℹ️', ja: '情報', tip: 'AutoModder の情報' },
  Data: { ic: '📊', ja: '参考', tip: 'AutoModder の参考の値（基準の判定ではない）' },
  Passed: { ic: '✓', ja: '合格', tip: '合格' },
};
const SEV_ORDER = ['Error', 'Warning', 'Inconclusive', 'Suggestion', 'Info', 'Data', 'Passed'];
const COUNTED = ['Error', 'Warning', 'Inconclusive', 'Suggestion', 'Info'];   // 見出しに数を出す重さ
const OBJ = { note: 'ノーツ', bomb: 'ボム', chain: 'チェーン', arc: 'アーク', wall: '壁', light: 'ライト' };
const MARK = { Success: ['✓', '問題なし'], Warning: ['⚠', '要確認'], Fail: ['✖', '不合格'] };   // 信号機の欄（CritResult）
const DIFFS = ['Easy', 'Normal', 'Hard', 'Expert', 'ExpertPlus'];   // 拍のクリックで飛べる難易度（NLM が書き出す Standard の難易度）

export function amView({ t, escHtml, dispDiff, am }) {
  const S = am.state;
  let asking = false;   // 取り込みの説明を開いている
  const fill = (s, vars) => { for (const k in vars) s = s.split('{' + k + '}').join(String(vars[k])); return s; };
  const tf = (k, def, vars) => fill(t(k, def), vars || {});
  const nameOf = n => t('am.k.' + n, JA[n] || n);
  const sevOf = s => SEV[s] || SEV.Info;
  const sevKey = s => SEV[s] ? s : 'Info';   // class 名に入れる重さ（知らない値は Info）
  const sevLab = s => t('am.sv.' + s, sevOf(s).ja);
  const sevTip = s => t('am.svTip.' + s, sevOf(s).tip);
  const fmtBeat = b => String(Math.round(b * 1000) / 1000);
  const fmtSec = s => { if (s == null || !isFinite(s)) return ''; const m = Math.floor(s / 60), r = s - m * 60; return m + ':' + r.toFixed(3).padStart(6, '0'); };
  const mb = n => (n / 1048576).toFixed(1);
  const dataText = d => Object.entries(d || {}).map(([k, v]) => k + ': ' + (Array.isArray(v) ? v.join(', ') : v)).join(' · ');
  const amVersion = () => (S.last && S.last.automodder && S.last.automodder.version) || (S.st && S.st.automodder) || null;

  function banner() {
    const v = amVersion();
    const title = v ? tf('am.bannerTitleV', 'AutoModder（v{v}・既定の設定）の判定', { v }) : t('am.bannerTitle', 'AutoModder（既定の設定）の判定');
    return `<div class="amBanner"><b>${escHtml(title)}</b><span>${escHtml(t('am.banner',
      'AutoModder の自動の確かめを NLM の中でそのまま動かした結果です（近似ではなく AutoModder と同じコード）。難易度ごとに既定の設定で確かめます。'
      + 'AutoModder の判定は BeatLeader の今の基準と違う所があります（R5.A 視界ブロックの時間の式・壁よけの回数など）。'
      + 'BeatLeader・AutoModder の公式ツールではなく、ランクの審査の結果でもありません。'))}</span></div>`;
  }

  // プラグインの状態とボタン（取り込み・もう一度・更新の確認）
  function control() {
    const { st, latest, last, busy, msg } = S;
    const info = s => `<span class="amInfo">${escHtml(s)}</span>`;
    const err = s => `<div class="amErrLine">${escHtml(s)}</div>`;
    if (!st) return `<div class="amCtl">${info(msg && msg.act === 'status' ? msg.text : t('am.plugLoading', 'プラグインを確認中…'))}</div>`;
    if (!am.installed()) {
      const ierr = msg && msg.err && msg.act === 'install' ? err(msg.text) : '';
      if (busy === 'install') return `<div class="amCtl">${info(t('am.installing', 'ダウンロード中…'))}</div>`;
      if (asking) {
        return `<div class="amBox">${escHtml(t('am.intro', 'この機能には追加プラグイン nlm-automodder（約12MB）が必要です。「GitHub から取り込む」を押すと、配布元（下記）からダウンロードして、このアプリのフォルダの plugins に保存します。'))}`
          + ` ${escHtml(t('am.after', '取り込んだ後、AutoModder の確かめを自動で動かして、結果をここに出します。'))}`
          + `<div class="amRepo">${escHtml(st.repo || '')}</div>`
          + `<div class="amBtns"><button class="amInstall">${escHtml(t('am.install', 'GitHub から取り込む'))}</button>`
          + `<button class="amCancel">${escHtml(t('am.cancel', 'やめる'))}</button></div></div>${ierr}`;
      }
      return `<div class="amCtl"><button class="amOpen">${escHtml(t('am.open', '📥 プラグインを取り込む…'))}</button>`
        + `${info(t('am.need', 'AutoModder の判定には追加プラグイン nlm-automodder が必要です。'))}</div>${ierr}`;
    }
    const runLab = busy === 'run' ? t('am.running', 'AutoModder で確かめています…') : (last && !last.error ? t('am.rerun', '↻ もう一度確かめる') : t('am.run', '▶ 確かめる'));
    const vers = st.installed.filter(m => m.compatible);
    const sel = vers.length > 1 ? `<select class="amVer"${busy ? ' disabled' : ''}>${vers.map(m =>
      `<option value="${escHtml(m.version)}"${m.version === st.current ? ' selected' : ''}>v${escHtml(m.version)}</option>`).join('')}</select>` : '';
    const upd = latest && latest.compatible && !latest.installed
      ? `<button class="amUpdate"${busy ? ' disabled' : ''}>${escHtml(tf('am.update', 'v{v} に更新（{mb}MB）', { v: latest.version, mb: mb(latest.size) }))}</button>` : '';
    const chk = `<button class="amCheck"${busy ? ' disabled' : ''}>${escHtml(busy === 'check' ? t('am.checking', '確認中…') : busy === 'install' ? t('am.installing', 'ダウンロード中…') : t('am.check', '更新を確認'))}</button>`;
    const m = msg && ['check', 'install', 'use'].includes(msg.act) ? `<div class="${msg.err ? 'amErrLine' : 'amOkLine'}">${escHtml(msg.text)}</div>` : '';
    return `<div class="amCtl">${info(tf('am.plugVer', 'nlm-automodder v{v}', { v: st.current }))}${sel}`
      + `<button class="amRun"${busy ? ' disabled' : ''}>${escHtml(runLab)}</button>${chk}${upd}</div>${m}`;
  }

  // 1つの難易度（または曲の情報）の中身
  function section(sec, st, chipMax) {
    const L = S.last, out = [];
    const e = sec.entry;
    if (e && e.skipped === 'tooFewNotes') out.push(`<div class="amNote">${escHtml(tf('am.tooFew', 'ノーツが20個未満（{n}個）のため、AutoModder はこの難易度を確かめません。', { n: e.notes ?? '?' }))}</div>`);
    if (e && e.skipped === 'notLoaded') out.push(`<div class="amNote">${escHtml(t('am.notLoaded', 'この難易度の譜面を AutoModder が読み込めませんでした。'))}</div>`);
    for (const er of sec.errors) {
      out.push(`<div class="mcErr">${escHtml(t('am.stopped', '確かめの途中で AutoModder が止まりました（この部分の結果はありません）'))}`
        + `<div class="amErrDetail">${escHtml([er.type, er.message].filter(Boolean).join(': ') + (er.where ? ` (${er.where})` : ''))}</div></div>`);
    }
    // 同じ重さ・同じ項目・同じ文をまとめる
    const groups = new Map(), passed = [], stats = [];
    for (const ri of sec.ris) {
      const r = L.results[ri];
      if (r.severity === 'Passed') { passed.push(r); continue; }
      if (r.severity === 'Data' && !r.objects.length) { stats.push(r); continue; }
      const k = r.severity + '\0' + r.name + '\0' + r.description;
      if (!groups.has(k)) groups.set(k, { sev: r.severity, name: r.name, desc: r.description, ris: [] });
      groups.get(k).ris.push(ri);
    }
    const list = [...groups.values()].map((g, i) => [g, i]).sort((a, b) => SEV_ORDER.indexOf(a[0].sev) - SEV_ORDER.indexOf(b[0].sev) || a[1] - b[1]).map(x => x[0]);
    list.forEach((g, gi) => out.push(itemHTML(g, sec.key + ':' + gi, st, chipMax)));
    for (const r of stats) {
      out.push(`<div class="amStat"><span class="amStatLab">${escHtml(SEV.Data.ic + ' ' + tf('am.stat', '{name}（AutoModder の計算）', { name: nameOf(r.name) }))}</span>`
        + `<span class="amStatVal">${escHtml(dataText(r.data))}</span></div>`);
    }
    if (passed.length) {
      const names = [...new Set(passed.map(r => nameOf(r.name)))];
      out.push(`<details class="amPassed" data-sec="pass:${escHtml(sec.key)}"><summary>${escHtml(tf('am.passed', '✓ 合格 {n} 項目', { n: passed.length }))}</summary>`
        + `<div class="amPassList">${escHtml(names.join(t('am.sep', '・')))}</div></details>`);
    }
    if (!out.length) out.push(`<div class="mcNone">${escHtml(t('am.none', '結果がありません'))}</div>`);
    return out.join('');
  }

  function itemHTML(g, id, st, chipMax) {
    const L = S.last, lab = nameOf(g.name), en = g.name !== lab ? `<span class="mcEn">${escHtml(g.name)}</span>` : '';
    const objs = [];
    for (const ri of g.ris) L.results[ri].objects.forEach((o, oi) => objs.push({ ri, oi, o }));
    objs.sort((a, b) => a.o.beat - b.o.beat);
    let beats = '', cnt = '';
    if (objs.length) {
      const all = st.expanded.has(id), n = all ? objs.length : Math.min(chipMax, objs.length);
      const chips = [];
      for (let i = 0; i < n; i++) {
        const { ri, oi, o } = objs[i];
        if (i > 0 && Math.abs(o.beat - objs[i - 1].o.beat) < 1e-6) continue;   // 同じ拍は1つにまとめる（BS Map Check のタブと同じ）
        const tip = [fmtSec(o.seconds), t('am.obj.' + o.type, OBJ[o.type] || o.type), g.ris.length > 1 ? dataText(L.results[ri].data) : ''].filter(Boolean).join(' · ');
        chips.push(`<span class="mcBeat" data-ref="am:${ri}:${oi}" title="${escHtml(tip)}">${escHtml(fmtBeat(o.beat))}</span>`);
      }
      beats = `<div class="mcBeats">${chips.join('')}${n < objs.length
        ? `<span class="mcMore" data-id="${escHtml(id)}">${escHtml(tf('mc.more', '他{n}件', { n: objs.length - n }))}</span>` : ''}</div>`;
      cnt = `<span class="mcN">${new Set(objs.map(x => x.o.beat)).size}</span>`;
    }
    const data = g.ris.length === 1 && Object.keys(L.results[g.ris[0]].data || {}).length
      ? `<div class="amData">${escHtml(dataText(L.results[g.ris[0]].data))}</div>` : '';
    return `<div class="mcItem amItem sv-${sevKey(g.sev)}"><div class="mcLine"><span class="mcIc" title="${escHtml(sevTip(g.sev))}">${sevOf(g.sev).ic}</span>`
      + `<span class="mcLab">${escHtml(lab)}</span>${cnt}${en}<span class="amSev">${escHtml(sevLab(g.sev))}</span></div>`
      + (g.desc ? `<div class="amDesc">${escHtml(g.desc)}</div>` : '') + data + beats + '</div>';
  }

  const countsHTML = (ris) => {
    const c = {};
    for (const ri of ris) { const s = S.last.results[ri].severity; c[s] = (c[s] || 0) + 1; }
    return COUNTED.filter(s => c[s]).map(s => `<span class="mcCnt sv-${s}" title="${escHtml(sevTip(s))}">${sevOf(s).ic} ${escHtml(sevLab(s))} ${c[s]}</span>`).join('');
  };

  // 難易度ごとの並び（曲の情報 → Info.dat の順。結果にだけある難易度は後ろ）
  function sections() {
    const L = S.last, secs = [], byKey = new Map();
    const add = (key, title, entry) => { const s = { key, title, entry, ris: [], errors: [] }; secs.push(s); byKey.set(key, s); return s; };
    add('info', t('am.secInfo', '曲の情報（Info.dat）'), null);
    const dk = (ch, dn) => (ch || 'Standard') + '/' + dn;
    const dTitle = (ch, dn) => dispDiff(dn) + (ch && ch !== 'Standard' ? ` (${ch})` : '');
    for (const [ch, dd] of Object.entries((L.criteria && L.criteria.diff) || {})) for (const [dn, e] of Object.entries(dd)) add(dk(ch, dn), dTitle(ch, dn), e);
    L.results.forEach((r, ri) => {
      const key = r.difficulty == null ? 'info' : dk(r.characteristic, r.difficulty);
      (byKey.get(key) || add(key, dTitle(r.characteristic, r.difficulty), null)).ris.push(ri);
    });
    for (const er of L.errors || []) {
      const key = er.stage === 'difficulty' && er.difficulty ? dk(er.characteristic, er.difficulty) : 'info';
      (byKey.get(key) || add(key, dTitle(er.characteristic, er.difficulty), null)).errors.push(er);
    }
    return secs;
  }

  function results(st, chipMax) {
    const L = S.last;
    if (!am.installed()) return '';
    if (!L) return S.busy === 'run' ? `<div class="amRunning">${escHtml(t('am.running', 'AutoModder で確かめています…'))}</div>` : '';
    if (L.error) return `<div class="mcErr">${escHtml(L.error)}</div>`;
    const all = L.results.map((_, i) => i);
    const nErr = L.results.filter(r => r.severity === 'Error').length;
    const sum = `<div class="amSum">${nErr ? '' : `<span class="mcOk">✓ ${escHtml(t('am.noError', 'エラー（Unrankable）はありません'))}</span>`}${countsHTML(all)}</div>`;
    // 開いておくのは曲の情報と今開いている難易度だけ（別の難易度は見出しの数・印だけ見せて閉じる。止まった所がある難易度は気付けるよう開く）
    const curKey = st.cur ? 'Standard/' + st.cur : null;
    const secs = sections().map(sec => {
      const e = sec.entry, h = e && !e.skipped && e.highest && MARK[e.highest];
      const mark = h ? `<span class="amMark m-${e.highest}" title="${escHtml(t('am.markTip', 'AutoModder の信号機の欄（項目ごとの合否）で一番重い物'))}">`
        + `${escHtml(h[0] + ' ' + tf('am.mark', 'AutoModder: {m}', { m: t('am.m.' + e.highest, h[1]) }))}</span>` : '';
      const isCur = sec.key === curKey, open = sec.key === 'info' || isCur || sec.errors.length > 0;
      return `<details class="mcSec amSec${isCur ? ' mcCurSec' : ''}"${open ? ' open' : ''} data-sec="${escHtml(sec.key)}"><summary>${escHtml(sec.title)}${isCur && st.curTag ? st.curTag : ''}${countsHTML(sec.ris)}${mark}</summary>${section(sec, st, chipMax)}</details>`;
    }).join('');
    const a = L.automodder || {};
    const meta = [tf('am.metaPlug', 'nlm-automodder v{v}', { v: L.version }),
      a.version ? 'AutoModder v' + a.version + (a.commit ? ` (${a.commit.slice(0, 7)})` : '') : '',
      tf('am.metaSec', '{s}秒', { s: (L.elapsedMs / 1000).toFixed(1) }),
      L.songLength ? tf('am.metaLen', '曲の長さ {s}秒', { s: Math.round(L.songLength * 10) / 10 }) : ''].filter(Boolean).join(t('am.sep', '・'));
    return sum + (L.truncated ? `<div class="amNote">${escHtml(t('am.truncated', '結果が多すぎるため、一部だけを表示しています。'))}</div>` : '')
      + secs + `<div class="amMeta">${escHtml(meta)}</div>`;
  }

  function render(st, chipMax) { return banner() + control() + results(st, chipMax); }

  function foot() {
    return escHtml(t('am.foot', '❌＝AutoModder の Unrankable　❗❔＝Questionable。公式の基準と違う所があります。拍をクリックするとその位置へ移動します。'))
      + `<br><span class="mcFootSub">${escHtml(t('am.footSub', '出典: AutoModder（LightAi39・MIT）を別配布のプラグイン nlm-automodder で動かした物。BeatLeader・AutoModder の公式ツールではありません。'))}</span>`;
  }

  // ボタンのクリック。処理したら true（呼んだ側が描き直す）
  function onClick(ev) {
    const b = ev.target.closest('.amOpen, .amCancel, .amInstall, .amRun, .amCheck, .amUpdate');
    if (!b || b.disabled) return !!b;
    if (b.classList.contains('amOpen')) asking = true;
    else if (b.classList.contains('amCancel')) asking = false;
    else if (b.classList.contains('amInstall') || b.classList.contains('amUpdate')) { asking = false; am.install().then(ok => { if (ok) am.run(); }); }
    else if (b.classList.contains('amRun')) am.run();
    else am.check();
    return true;
  }
  function onChange(ev) {
    const x = ev.target;
    if (!x.classList || !x.classList.contains('amVer')) return false;
    am.useVer(x.value).then(() => am.run());
    return true;
  }
  // 拍のチップ（am:結果:物）→ 飛ぶ先 {dn, o}（mapCheckJump に渡す形）
  function ref(parts) {
    const L = S.last, r = L && L.results && L.results[+parts[1]], o = r && r.objects[+parts[2]];
    if (!o || !DIFFS.includes(r.difficulty) || (r.characteristic && r.characteristic !== 'Standard')) return null;
    return { dn: r.difficulty, o: { kind: o.type, beat: o.beat, x: o.x, y: o.y, c: o.type === 'note' ? o.color : null } };
  }
  return { render, foot, onClick, onChange, ref };
}

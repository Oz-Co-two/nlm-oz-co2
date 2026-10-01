// NLM版 BeatLeader評価リストの表示（判定は blcriteria.js）。譜面チェックのパネル（mapcheck-panel.js）の2つ目のタブ。
// BS Map Check の結果と見間違えないよう、枠と背景の色を変えて「NLMが作った表」だと分かるようにしている（css/mapcheck.css の .bl*）
import { RULES, SECTIONS, BL, CRITERIA_DATE } from './blcriteria.js';

// 基準の要約（日本語の既定値。英語は lang/en.json の bl.r.*）。公式の文面の和訳ではなくNLMによる要約
export const BL_RULE_JA = {
  'R1.A.1': '譜面のBPMが曲のBPM（またはその倍数）になっている',
  'R1.A.2': '曲の拍とグリッドが（音源の調整やBPMイベントで）できるだけ合っている',
  'R1.A.3': '音源が十分な品質で .ogg 形式（.egg 可）',
  'R1.A.4': 'カバー画像が 256×256px 以上・1:1・png/jpg/jpeg',
  'R1.B.1': 'Song Time Offset が未使用または 0',
  'R1.B.2': 'Shuffle と Shuffle Period が未使用または 0',
  'R1.B.3': '定義した（公式の）カラースキームは全色を指定している',
  'R1.B.4': '壁の幅・長さが0より大きく、高さが0でない（マイナスの高さは枠内に入らなければ可）',
  'R1.B.5': 'チェーンの詰め具合（squish）が0より大きい',
  'R1.B.6': 'オブジェクトの拍がマイナスでなく、曲の最終拍を超えない',
  'R1.B.7': '壁が曲の終わりをはみ出さない（拍＋長さ ≤ 最終拍）',
  'R1.B.8': 'NJSイベントに使えないイージング（Sine/Cubic/Quart/Quint/Expo）が無い',
  'R1.C': '遊ぶのにMODや外部プログラムを必要としない',
  'R1.D.1': '最初の当たる物まで1.5秒以上（2秒推奨）',
  'R1.D.2': '最後の当たる物のあと2秒以上',
  'R1.E': 'ミス配置・間違い・意図しない配置が無い',
  'R1.F': '最初のノーツから最後のノーツ/チェーンのリンクまで45秒以上',
  'R1.G': '他の難易度・他の譜面と十分に違う（40%以上同じなら古い方のみ）',
  'R2.A': '各ノーツが音のタイミングポイントから12ms以内（意図したリズムの扱いを含む）',
  'R2.B': '繰り返す音は、タイミングポイントの取り方が一貫している',
  'R2.C': 'リズムの取り方が区間の中で一貫している',
  'R3.A.1': 'オブジェクト同士が奥行き方向で重ならない（同じマスで0.5m以内）',
  'R3.A.2': '壁以外のオブジェクトが壁と重ならない',
  'R3.B': 'ノーツの振り始めを反対色のノーツ/チェーンがふさがない',
  'R3.C': 'ヒットボックスを悪用する配置が無い（重なり20%超）',
  'R4.A.1': 'スイングを引き延ばすための過剰なノーツ（ポール・ドット連打など）が無い',
  'R4.A.2': '複数ノーツのスイングは速さが一定',
  'R4.A.3': 'スライダーの実効精度が区間の精度に対して1/16以上に細かい（2ノーツの窓は1/8）',
  'R4.A.4': 'スライダーの速さが区間ごとに一定',
  'R4.A.5': 'スライダーと窓スライダーの実効精度が区間の中で同じ',
  'R4.A.6': 'チェーンの長さがスライダーの平均の実効長の200%以下',
  'R4.B.1': '複数ノーツのスイングを、最初の角度から45度以内の軌道で切れる',
  'R4.B.2': 'スイングの軌道が曲がる向きは片側だけ',
  'R4.B.3': 'スイングの軌道の曲がりの半径が妥当',
  'R4.C': '手拍子（両手が同じ場所に来る）を誘う配置が無い',
  'R5.A': '当たる物が、反応に十分な時間見えている（視界ブロックの式）',
  'R5.B.1': 'ノーツ・チェーン・ボムが、壁やボムの壁の向こう側に隠れない',
  'R5.B.3': '下からの壁が、その列の物の出現を（壁の終わり＋0.25拍まで）隠していない',
  'R5.C': 'リセットが曖昧・読みにくくない',
  'R6.A': '最初の16ノーツにチェーン（リンクを含む）が無い',
  'R6.B.1': 'チェーンが逆向きでない（頭が先）',
  'R6.B.2': 'チェーンが頭の向きから45度を超えて曲がらない（点の頭は下向き扱い）',
  'R6.C.1': 'チェーンの頭が4×3の枠の中',
  'R6.C.2': 'リンクは左右に1レーンまでならはみ出してよいが、上下にははみ出さない',
  'R6.D': 'チェーンのリンクが、すき間に対して12.5%以上',
  'R6.E': 'チェーンの最後のリンクから次のノーツまで、チェーンの長さ以上空ける（手ごと）',
  'R6.F': 'アークがボムにつながっていない',
  'R6.G.1': 'チェーンに頭のノーツがある',
  'R6.G.2': 'チェーンの分割数が2以上（見えるリンクが1つ以上）',
  'R7.A': 'ボムがノーツ/チェーンのスイング軌道の上に無い',
  'R7.B': 'ボムの250ms前から通り過ぎるまで、明るさ50以上のライトが点いている',
  'R7.C': 'ボムがセイバーを4×3の枠の外へ追い出さない',
  'R8.A.1': '壁の間に、楽に避けられる空間がある',
  'R8.A.2': '壁の境界を避ける時間が250ms以上（例外で235ms）',
  'R8.A.3': '頭を1秒に2回を超えて動かす回避壁は正当化が必要',
  'R8.B': '壁が外側のレーンへ追い出さない（真ん中のどちらかが常に空いている）',
  'R8.C': '13.8ms以下の壁は、同じレーンの正規の壁の後ろ250ms以内（どの壁でも100ms以内）',
  'R8.D.1': 'しゃがむ壁の最中と0.5拍後まで、真ん中2列の下段の物は視界ブロック扱い',
  'R8.D.2': 'しゃがむ壁の最中は、中段より上に置かない',
  'R9': '可変NJS（NJSの下限1・基本NJSの範囲・当たる範囲への侵入）',
  'R10.A': '平均で1拍に1個以上のライトイベント',
  'R10.B': 'ライトの演出が譜面の視認を大きく妨げない',
  'R11.A': '曲が公式に入手でき、1つの公式リリースをメタデータの出典にしている',
  'R11.B': 'メタデータが検索できる（日本語などは公式の翻訳/ローマ字）',
  'R11.C': 'ゲーム内で打てない特殊文字は置き換える',
  'R11.D.1': '曲名が公式どおり（大文字小文字も）',
  'R11.D.2': '曲名に feat./Remix などのタグを入れない（サブ名へ）',
  'R11.E': 'サブ名のタグの書き方・順番',
  'R11.F.1': '作者名が公式どおり（大文字小文字も）',
  'R11.F.2': '作者名に feat./カバーなどのタグを入れない',
  'R11.G': 'マッパー欄に全マッパー・ライター（またはグループ名）',
  'R11.H.1': '難易度名が重ならない・行数（1難易度は1行、2つなら2行、3つ以上で3行まで）',
  'R11.H.5': '難易度が★の昇順（0.5★まで許容）',
  'R11.I': '不適切な内容が無い',
  'R11.J': 'AI生成の曲でない',
};
export const BL_SEC_JA = { R1: '全般・譜面の設定', R2: 'タイミング', R3: '配置', R4: 'スイング', R5: '視認性', R6: 'チェーンとアーク',
  R7: 'ボム', R8: '壁', R9: '可変NJS', R10: 'ライト', R11: 'メタデータ' };
export const BL_MSG_JA = {
  noAudio: '音源がありません', oggOk: '形式はOK（NLMが .ogg に変換し song.egg で書き出す）。音質は聞いて確認',
  noCover: 'カバー画像がありません（必須）', coverRatio: '正方形でない（{w}×{h}）', coverSize: '小さすぎる（{w}×{h}）',
  coverFormat: '形式が png/jpg/jpeg でない（{name}）',
  songTimeOffset: 'Song Time Offset が {v}（読み込んだInfo.datの値を引き継いでいます）',
  shuffle: 'Shuffle={s}・Shuffle Period={sp}（Shuffleが0ならNLMは周期も0で書き出す）',
  noSchemes: 'カラースキームなし（NLMは書き出さない）', schemeMissing: '色が欠けたカラースキームが{n}個',
  requirements: '必須MODの指定: {list}',
  wallZero: '幅・長さが0以下、または高さが0の壁', wallNegIn: '高さがマイナスで枠の中に入り込む壁', squish: '詰め具合が0以下のチェーン',
  beatNeg: '拍がマイナスのオブジェクト', noAudioEnd: '音源が無いので、曲の終わりに関わる判定はできません',
  beatOver: '最終拍（{end}）より後ろのオブジェクト', wallEnd: '最終拍（{end}）をはみ出す壁',
  noNjsEvents: 'NJSイベントなし（NLMのv3書き出しには無い）', njsEasing: '使えないイージングのNJSイベントが{n}個',
  leadShort: '最初の当たる物が{sec}秒（1.5秒未満）', leadRec: '{sec}秒（1.5秒以上だが推奨の2秒未満）',
  tailShort: '最後の当たる物のあとが{sec}秒（2秒未満）', mapShort: '最初から最後のノーツまで{sec}秒（45秒未満）',
  zIntersect: '同じマスで奥行き0.5m以内に重なる物', inWall: '壁の中にある物',
  preSwing: '振り始めのマス（切る向きの反対側の隣）に反対色の物がある',
  mc: 'BS Map Check「{key}」の該当箇所', slowSlider: '実効精度が1/16拍より粗いスライダー（1/4刻みの区間を想定）',
  precList: '使われている実効精度（拍）: {list}', noSliders: 'スライダーが無いので、チェーンの長さを比べられません',
  chainLong: 'スライダーの平均の2倍（{ms}ms）より長いチェーン',
  swing45: '最初の角度から45度を超えて曲がるスイング', swingBothWays: '左右両方へ曲がるスイング',
  needStars: '下の欄にこの難易度の★とTechを入れると判定します', vision: '最小時間{ms}ms未満で隠れる物（ゲーム内かArcViewerで確認）',
  visionOk: '最小時間{ms}msで判定・該当なし', wallHide: '下からの壁で出現が隠れる物（正当化が必要）',
  first16: '最初の16ノーツに入っているチェーン', chainReverse: '逆向き（尾が頭より前か同時）のチェーン',
  chainTurn: '45度を超えて曲がるチェーン', chainHeadOut: '頭が枠の外のチェーン', chainLinkOut: 'リンクが許される範囲の外に出るチェーン',
  chainSparse: '詰め具合が12.5%未満のチェーン', chainDense: '詰め具合33%以上のチェーンが{n}個（視界ブロックを厳しめに見られる）',
  chainGap: '次のノーツまでの間がチェーンの長さより短い', arcBomb: 'ボムにつながったアーク', noHead: '頭のノーツが無いチェーン',
  fewSlices: '分割数が2未満のチェーン', bombPath: 'スイングの手前/先のマスにあるボム',
  boxLights: 'v3のイベントボックスのライトは再現できないので目視で確認', noLightAtAll: 'ライトが1つも点かない（全ボムが暗い）',
  bombDark: '250ms前から暗い時間があるボム（フェードは1秒点灯とみなした近似）',
  dodgeFast: '0.5秒未満で頭を左右に動かす回避壁', outerLane: '真ん中の2レーンを同時に塞ぐ壁', illegalWall: '後ろに付いていない13.8ms以下の壁',
  crouchLow: 'しゃがむ壁の最中/直後の、真ん中下段の物（視界ブロック扱い）', crouchHigh: 'しゃがむ壁の最中に上段にある物',
  njsEventsUsed: 'NJSイベントが{n}個あります（この項目は目視）',
  lightFew: 'ライト{n}個／{beats}拍＝1拍あたり{per}個（1個未満）', lightOk: 'ライト{n}個／{beats}拍＝1拍あたり{per}個',
  unsearchable: '{field}に打てない文字「{chars}」（公式の翻訳/ローマ字にする）', specialChar: '{field}に打てない記号「{chars}」（似た文字か記号名に置き換え）',
  nameTag: '曲名にタグらしい語: 「{v}」', authorTag: '作者名にタグらしい語: 「{v}」', noMapper: 'マッパー欄が空です',
  customLabels: '独自の難易度名: {list}（ゲーム内で重なり・行数を確認）', defaultNames: 'NLMは標準の難易度名で書き出す（重なり・行数の問題なし）',
  failed: '判定中にエラー（{err}）', fSong: '曲名', fSub: 'サブ名', fAuthor: '作者名', fMapper: 'マッパー名',
};
// 文面に定義が無くNLMが解釈した・近似した項目の注記
export const BL_NOTE_JA = {
  'R3.B': '図だけで示された項目。「振る直前」を同じ手の前のノーツとの間の後半（最大0.5秒）とみなした候補',
  'R3.C': 'BS Map Check のヒットボックス系の判定を候補として表示',
  'R4.A.2': 'BS Map Check の「スライダーの速さが一定でない」を候補として表示',
  'R4.A.3': '区間の精度は自動で決められないため、1/4刻みの区間を想定した候補（1/8刻みの区間なら下限は1/32）',
  'R4.A.6': '「実効長」は最初から最後のノーツまでの時間で近似',
  'R4.C': 'BS Map Check の「手拍子になる配置」を候補として表示',
  'R5.A': '式はBeatLeader公式（750-325)·e^(-★/7.6-Tech·0.06)+325ms。★とTechはBeatLeaderの値（申請前は見込み）を入れる。下段の例外は流れに沿うかを目視',
  'R6.D': '文面に計算方法が無いため、チェーンの詰め具合（squish）をリンクの割合とみなした',
  'R7.A': '「軌道の上」を切る向きの手前/先の隣のマスとみなした候補',
  'R7.B': '明るさ50を0.5とみなし、基本ライトイベントを再現して判定',
  'R8.A.2': 'BS Map Check の「中央の2マス幅の壁（回復250ms未満）」を候補として表示',
  'R8.A.3': '真ん中の片側だけを塞ぐ壁で、塞ぐ側が0.5秒未満で入れ替わる所を候補にした',
};
const ST = {
  [BL.FAIL]: { ic: '✖', ja: '違反' }, [BL.CHECK]: { ic: '⚠', ja: '要確認' }, [BL.PASS]: { ic: '✔', ja: '合格' },
  [BL.PARTIAL]: { ic: '✔', ja: '自動分は合格' }, [BL.MANUAL]: { ic: '☐', ja: '手動確認' }, [BL.NA]: { ic: '－', ja: '対象外' },
};
const ST_ORDER = [BL.FAIL, BL.CHECK, BL.PASS, BL.PARTIAL, BL.MANUAL, BL.NA];
const KIND_JA = { auto: '自動', partial: '一部自動', cand: '候補', manual: '手動', na: '対象外' };

export function blView({ t, escHtml, dispDiff, mcLabel }) {
  const fill = (s, vars) => { if (vars) for (const k in vars) s = s.split('{' + k + '}').join(String(vars[k])); return s; };
  const stLab = s => t('bl.st.' + s, ST[s].ja);
  const fmtBeat = b => String(Math.round(b * 1000) / 1000);
  const fmtSec = s => { if (!isFinite(s)) return ''; const m = Math.floor(s / 60), r = s - m * 60; return m + ':' + r.toFixed(3).padStart(6, '0'); };
  const msg = f => {
    const v = { ...(f.vars || {}) };
    if (v.field) v.field = t('bl.m.' + v.field, BL_MSG_JA[v.field]);
    if (v.key) v.key = mcLabel(v.key);
    return fill(t('bl.m.' + f.key, BL_MSG_JA[f.key] || f.key), v);
  };
  const counts = rules => { const c = {}; for (const r of rules) c[r.status] = (c[r.status] || 0) + 1; return c; };
  const countsHTML = c => ST_ORDER.filter(s => c[s]).map(s => `<span class="blCnt st-${s}">${ST[s].ic} ${escHtml(stLab(s))} ${c[s]}</span>`).join('');

  function chips(f, ref, expanded, CHIP_MAX) {
    if (!f.objs) return '';
    const all = expanded.has(ref), n = all ? f.objs.length : Math.min(CHIP_MAX, f.objs.length), out = [];
    for (let oi = 0; oi < n; oi++) {
      const o = f.objs[oi];
      if (oi > 0 && Math.abs(o.beat - f.objs[oi - 1].beat) < 1e-6) continue;
      out.push(`<span class="mcBeat" data-ref="${ref}:${oi}" title="${escHtml(fmtSec(o.sec))}">${escHtml(fmtBeat(o.beat))}</span>`);
    }
    return `<div class="mcBeats">${out.join('')}${n < f.objs.length
      ? `<span class="mcMore" data-id="${ref}">${escHtml(t('mc.more', '他{n}件').replace('{n}', f.objs.length - n))}</span>` : ''}</div>`;
  }

  // res: runBlCriteria の結果 / st: {onlyIssues, stars, expanded}
  function render(res, st, CHIP_MAX) {
    const tot = counts(res.rules);
    let h = `<div class="blBanner"><b>${escHtml(t('bl.banner', 'NLM版 BeatLeader評価リスト'))}</b>`
      + `<span>${escHtml(t('bl.bannerSub', 'BeatLeader公式の文章の基準（{date}時点）を、NLMが項目ごとに判定表にしたものです。BeatLeader や BS Map Check の公式な結果ではありません。').replace('{date}', res.date))}</span></div>`;
    h += `<div class="blSum">${countsHTML(tot)}<label class="blOnly"><input type="checkbox" class="blOnlyChk"${st.onlyIssues ? ' checked' : ''}> ${escHtml(t('bl.onlyIssues', '違反・要確認だけ表示'))}</label></div>`;
    for (const sec of SECTIONS) {
      const rs = res.rules.map((r, i) => [r, i]).filter(([r]) => r.id.split('.')[0] === sec);
      const vis = rs.filter(([r]) => !st.onlyIssues || r.status === BL.FAIL || r.status === BL.CHECK);
      if (!vis.length) continue;
      const rows = vis.map(([r, ri]) => ruleHTML(r, ri, res, st, CHIP_MAX)).join('');
      h += `<details class="mcSec blSec" data-sec="${sec}" open><summary><span class="blSecId">${sec}</span>${escHtml(t('bl.sec.' + sec, BL_SEC_JA[sec]))}${countsHTML(counts(rs.map(x => x[0])))}</summary>${rows}</details>`;
    }
    return h;
  }
  function ruleHTML(r, ri, res, st, CHIP_MAX) {
    const txt = t('bl.r.' + r.id, BL_RULE_JA[r.id] || r.id);
    const note = BL_NOTE_JA[r.id] ? `<div class="blNote">＊${escHtml(t('bl.n.' + r.id, BL_NOTE_JA[r.id]))}</div>` : '';
    const fs = r.findings.map((f, fi) => {
      const d = f.d ? `<span class="blDiff">${escHtml(dispDiff(f.d))}</span>` : '';
      const cls = f.status === BL.FAIL || f.status === BL.CHECK ? ' st-' + f.status : '';
      return `<div class="blF${cls}">${d}<span>${escHtml(msg(f))}</span>${f.objs ? `<span class="mcN">${new Set(f.objs.map(o => o.beat)).size}</span>` : ''}${chips(f, 'bl:' + ri + ':' + fi, st.expanded, CHIP_MAX)}</div>`;
    }).join('');
    let inp = '';
    if (r.input === 'stars') {
      inp = `<div class="blStars">` + res.diffs.map(dn => {
        const v = st.stars[dn] || {};
        return `<span class="blStar"><b>${escHtml(dispDiff(dn))}</b> ★<input type="number" step="0.01" min="0" data-star="${escHtml(dn)}" value="${v.star ?? ''}">`
          + ` Tech<input type="number" step="0.01" min="0" data-tech="${escHtml(dn)}" value="${v.tech ?? ''}"></span>`;
      }).join('') + `</div>`;
    }
    return `<div class="blRule st-${r.status}"><div class="blLine"><span class="blId">${escHtml(r.id)}</span>`
      + `<span class="blSt" title="${escHtml(stLab(r.status))}">${ST[r.status].ic}</span><span class="blTxt">${escHtml(txt)}</span>`
      + `<span class="blKind">${escHtml(t('bl.kind.' + r.kind, KIND_JA[r.kind]))}</span></div>${fs}${inp}${note}</div>`;
  }
  return { render, RULES, CRITERIA_DATE };
}

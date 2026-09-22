import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { makeChamferBoxGeometry, NOTE_CORNER_CUT, CHAIN_HEAD_SIZE, CHAIN_LINK_SIZE, makeChainHeadGeometry, makeChainLinkGeometry } from '../three/chamfer-box.js';
import { chainLinkLayout, CHAIN_CURVE_DEFAULTS, CHAIN_RAW_KEYS, sampleChainCurve, nearestCutDirection, angleFromWorldDelta } from '../notes/chain-bezier.js';
import { _sniffMime, _rd32be, _parseFlacPic, _id3Pic, _flacPic, _oggPic, _mp4FindAtom, _mp4Pic } from '../media/cover-parse.js';   // 埋め込みアートワーク解析（純関数・監査で切出し 2026-07-14）
import { EffectComposer } from 'three/addons/postprocessing/EffectComposer.js';
import { RenderPass } from 'three/addons/postprocessing/RenderPass.js';
import { UnrealBloomPass } from 'three/addons/postprocessing/UnrealBloomPass.js';
import { mergeGeometries } from 'three/addons/utils/BufferGeometryUtils.js';   // ボムのトゲトゲ合成用


import { installLightingEditor } from '../lighting/lighting-editor.js';
import { installNotesEditor } from '../notes/notes-editor.js';
import { installNlePanel } from '../nle/nle-panel.js';
import { installMediaPanel } from '../media/media-panel.js';
import { installInfoPanel } from '../info/info-panel.js';
import { installSaveSystem } from '../project/save-system.js';
import { installExportSystem } from '../project/export-system.js';
import { installHistorySystem } from '../core/history.js';
import { installEditorScene } from '../three/editor-scene.js';
import { installAudioEngine } from '../audio/audio-engine.js';
import { installPv4Bridge } from '../preview/pv4-bridge.js';
import { installPaneModes } from '../modes/pane-modes.js';
import { installChartSync } from '../chart/sync.js';
import { installGraphLegacy } from '../chart/graph-legacy.js';
import { installUiChrome } from '../ui/chrome.js';
import { installTickLoop } from '../loop/tick-loop.js';
import { installEditorRuntimeHelpers } from '../runtime/editor-runtime.js';

/**
 * Editor runtime — original closure (behavior-preserving).
 * Domain class modules hold the split object API + method implementations.
 */
export function createEditorApp() {
const LANE=0.62, LAYER=0.62, BASE_Y=0.7, ZPB=2.52;   // Z/拍=拍間隔。1.8→2.52(1.4倍)：低BPM曲で詰まりすぎないよう横に伸長（ヘルバ様指定）
let RED=0xff274d, BLUE=0x3092ff, cRED='#ff274d', cBLUE='#3092ff';   // ノーツ色（左=赤/右=青。ユーザー変更可）
let LRED=0xff274d, LBLUE=0x3092ff, LRED_B=0xff6f9f, LBLUE_B=0x6fdcff;   // レーザー色（赤系/青系ライト。白は固定）。_B=BOOST色（独立編集・ヘルバ様指定 2026-07-13。未設定の旧ファイルはlaserBoostColsの派生で埋める）
const WHITE_HEX='#e8f0ff';   // ライトの白（i>=9・固定色）。パレット表示/Fサイクルで使う（ヘルバ様指定 2026-07-13）
function boostStateAt(beat){   // 指定拍でのBoost状態: その拍以前の最新Boostイベント(et=5)がON(i>0)ならtrue（無ければOFF）
  let on=false, best=-Infinity;
  for(const e of lightEvents){ if(e.et!==5) continue; if(e.beat<=beat+1e-6 && e.beat>=best){ best=e.beat; on=(e.i>0); } }
  return on; }
function _briB(c){ const f=(v)=>Math.min(255,v+((255-v)*0.4)|0); return f(c>>16&255)<<16|f(c>>8&255)<<8|f(c&255); }   // ブースト既定＝基本色を明るくした派生
function laserBoostCols(){ LRED_B=_briB(LRED); LBLUE_B=_briB(LBLUE); }
const hexOf=n=>'#'+(n>>>0).toString(16).padStart(6,'0');
function setNoteColStr(){ cRED=hexOf(RED); cBLUE=hexOf(BLUE); try{ updateColorBtn(); }catch(_){} }   // カスタム色変更をツールバー色ボタンへも反映（初期化中はTB_ICONS未定義でTDZ→try/catchで無視）
// カラーピッカーのスウォッチから各色をライブ変更（ノーツ/ライト/ブースト）。値はライブ変数＋セットアップノードの両方へ直接反映＝applyInfoGraphで戻らず、undo連打も出ない（保存はinfoGraph経由・ヘルバ様指定 2026-07-13）
function _hexToInt(hex){ const m=/^#?([0-9a-fA-F]{6})/.exec(hex||''); return m?parseInt(m[1],16)>>>0:null; }
function setNoteColorHex(which,hex){ const v=_hexToInt(hex); if(v==null) return;
  if(which===0) RED=v; else BLUE=v;
  const nd=quickSetNode(); if(nd) nd.data[which===0?'red':'blue']=v;
  setNoteColStr(); try{ refreshInfoCards(); }catch(_){} try{ applyModeDim(); }catch(_){} metaDirty=true; }
function setLightColorHex(which,hex){ const v=_hexToInt(hex); if(v==null) return;
  if(which===0) LRED=v; else LBLUE=v;
  const nd=quickSetNode(); if(nd) nd.data[which===0?'lred':'lblue']=v;
  try{ refreshInfoCards(); }catch(_){} try{ applyModeDim(); }catch(_){} metaDirty=true; }
function setLightBoostHex(which,hex){ const v=_hexToInt(hex); if(v==null) return;
  if(which===0) LRED_B=v; else LBLUE_B=v;
  const nd=quickSetNode(); if(nd) nd.data[which===0?'lredB':'lblueB']=v;
  metaDirty=true; }
// ライト用クロマ色（RGB自由指定）のhex⇄rgb01(0-1)変換。.datのcustomData.colorは0-1 float配列
function hexToRgb01(hex){ const n=parseInt((hex||'#ffffff').replace('#',''),16)>>>0;
  return [(n>>16&255)/255,(n>>8&255)/255,(n&255)/255]; }
function rgb01ToHex(rgb){ const h=v=>Math.max(0,Math.min(255,Math.round((v??1)*255))).toString(16).padStart(2,'0');
  return '#'+h(rgb[0])+h(rgb[1])+h(rgb[2]); }
function rgb01ToHexInt(rgb){ const h=v=>Math.max(0,Math.min(255,Math.round((v??1)*255)));
  return (h(rgb[0])<<16)|(h(rgb[1])<<8)|h(rgb[2]); }
const FONT='"M PLUS Rounded 1c",sans-serif';   // Canvas描画共通フォント
let MAXANISO=8;   // テキストテクスチャの異方性フィルタ（レンダラ初期化後に実値へ更新）
const DIRICON={0:'↑',1:'↓',2:'←',3:'→',4:'↖',5:'↗',6:'↙',7:'↘',8:'•'};
const DIRV={0:[0,1],1:[0,-1],2:[-1,0],3:[1,0],4:[-1,1],5:[1,1],6:[-1,-1],7:[1,-1],8:[0,0]};
const ROT=[1,6,2,4,0,5,3,7,8];   // 回転順 ↓↙←↖↑↗→↘[・]（ヘルバ様指定・プルダウンと一致）
const ROT_NODOT=[1,6,2,4,0,5,3,7];   // ドット(8)を除く8方向のみ。チェーン尾の回転用（子ノーツは常にドット表示のためドット枠は不要＝ヘルバ様指摘）
const DIR_ANGLE={0:0,5:45,3:90,7:135,1:180,6:225,2:270,4:315};
function rotStep(d,step){ const i=(ROT.indexOf(d)+step+ROT.length*9)%ROT.length; return ROT[i]; }
function rotStepNoDot(d,step){ let i=ROT_NODOT.indexOf(d); if(i<0) i=(step>0?-1:0); i=(i+step+ROT_NODOT.length*9)%ROT_NODOT.length; return ROT_NODOT[i]; }

const cv=document.getElementById('cv');
const renderer=new THREE.WebGLRenderer({canvas:cv,antialias:true,powerPreference:'high-performance'});
let dprScale=1;
function applyDpr(){ renderer.setPixelRatio(Math.min(devicePixelRatio,2)*dprScale); }
applyDpr();
// 実際に使われているGPUを特定（SwiftShader=ソフトウェア描画なら重さの原因）
let gpuName='GPU不明';
MAXANISO=renderer.capabilities.getMaxAnisotropy();
{ const gl=renderer.getContext(); const ext=gl.getExtension('WEBGL_debug_renderer_info');
  if(ext) gpuName=gl.getParameter(ext.UNMASKED_RENDERER_WEBGL); console.log('WebGL renderer:',gpuName); }
const scene=new THREE.Scene(); scene.fog=new THREE.Fog(0x17171e,22,70);
{ // Blenderテーマと同じ縦グラデーション背景（上#141414→下#191a2a）
  const c=document.createElement('canvas'); c.width=1; c.height=256;
  const g=c.getContext('2d'); const gr=g.createLinearGradient(0,0,0,256);
  gr.addColorStop(0,'#141414'); gr.addColorStop(1,'#191a2a');
  g.fillStyle=gr; g.fillRect(0,0,1,256);
  const t=new THREE.CanvasTexture(c); t.colorSpace=THREE.SRGBColorSpace;
  scene.background=t;
}
const camera=new THREE.PerspectiveCamera(37.85,1,0.1,180);   // 垂直画角37.85°=フルサイズ換算35mm（端の歪み対策で24mm→35mmへ）。farを絞って深度精度を確保（Zファイト対策）
camera.position.set(-16.33,8.67,18.5);                   // 起動直後の暫定値。初期化末尾の setCamMode('place') → flyPlaceCam() が PLACE_CAM_DEF で必ず上書きするため、実際にはこの値では描かれない
const controls=new OrbitControls(camera,cv);
controls.mouseButtons={ LEFT:null, MIDDLE:THREE.MOUSE.ROTATE, RIGHT:null };
controls.enableZoom=false; controls.target.set(-3.48,-3,18.5); controls.update();   // x=0 は2026-07-18のレイアウト改修で「何も無い場所」になったためレーン帯の中央へ（実描画前に上書きされるが、初期化順を変えた時に空画面にならないように）
// 3Dカメラの可動範囲制限（ヘルバ様指示: 譜面を見失うほど遠く/高くへ行けないように。地面以下も禁止）
// 初期視点(-16.33, 8.67, 18.5)/初期注視点(-3.48,-3,18.5)は範囲内に収まる値に設定
const CAM_LIMIT={ px:20, pyMin:0.3, pyMax:18,     // カメラ位置: 高さ=地面の少し上〜18・Xは譜面周辺のみ
                  tx:14, tyMin:-4, tyMax:10 };    // 注視点: 視線が譜面から大きく外れない範囲
const CAM_MARGIN_ZB=8;   // Z制限の余白（拍）: 曲のはじまり−8拍 〜 曲の終わり＋8拍（ヘルバ様指定=曲に合わせて動的）
function camSongEndBeat(){   // 曲末の拍（セグメント末尾の最大）。曲未読込時は暫定128拍
  let e=0; try{ for(const sg of msegs()) e=Math.max(e,segEndBeat(sg)); }catch(_){}
  return e>0?e:128;
}
function clampCamera(){
  const p=camera.position, t=controls.target;
  // Z: ワールドzは表示アンカー(viewBeat)相対なので、毎フレーム「拍→z」で絶対範囲に換算してクランプ
  let zLo=-1e9, zHi=1e9;
  try{ const vb=viewBeat();
    zLo=(0-vb-CAM_MARGIN_ZB)*ZPB;                     // 曲頭−8拍
    zHi=(camSongEndBeat()-vb+CAM_MARGIN_ZB)*ZPB;      // 曲末＋8拍
    if(zHi<zLo+ZPB) zHi=zLo+ZPB;                       // 退化ガード
  }catch(_){}
  p.x=Math.max(-CAM_LIMIT.px,Math.min(CAM_LIMIT.px,p.x));
  p.y=Math.max(CAM_LIMIT.pyMin,Math.min(CAM_LIMIT.pyMax,p.y));
  p.z=Math.max(zLo,Math.min(zHi,p.z));
  t.x=Math.max(-CAM_LIMIT.tx,Math.min(CAM_LIMIT.tx,t.x));
  t.y=Math.max(CAM_LIMIT.tyMin,Math.min(CAM_LIMIT.tyMax,t.y));
  t.z=Math.max(zLo,Math.min(zHi,t.z));
}
controls.addEventListener('change',clampCamera);   // 操作時にも即時クランプ（毎フレームのtick側と二重で確実）
window._cam=camera; window._ctl=controls;   // 開発用: コンソールから視点を確認・調整できるように公開
window._dbg={ get state(){ return {musicBeat,musicSegs:structuredClone(musicSegs),markers:structuredClone(markers),notesLanes,lightLanes,cur,BPM,audio:!!audioBuf,songDur,sections:sections.length}; },
  set musicBeat(v){ musicBeat=v; }, save(){ return buildProjectText(); }, apply(pj){ return applyProject(pj); },
  exportJson(k){ return buildDiffJsonFor(projDiffs[k]); },
  dropInfo(item,x,y){ return dropInfoNodesFromItem(item,x,y); }, setDragMedia(it){ _dragMedia=it; },   // 診断用（MEDIA→INFOドロップの機械検証）
  extractArtwork(fh){ return extractArtwork(fh); },   // 診断用（埋め込みアートワーク抽出の検証）
  scanLibrary(dh){ return scanLibrary(dh); },
  nodeColMode(m){ return setNodeColMode(m); },   // 診断用（NLE/INFO表示切替）
  dropInfoMusic(item,x,y){ return dropInfoNodesFromItem(item,x,y); },
  saveClipToAsset(sec){ return saveClipToAsset(sec); }, scanAsset(){ return scanAssetLibrary(); },   // 診断用（アセット保存/再スキャン）
  setPvMode(m){ return setPvMode(m); },   // 診断用（MEDIA/PREVIEW切替）
  pv4Stats(){ return _PV4&&_PV4._dbgStats&&_PV4._dbgStats(); },   // 診断用（停止中スキップの検証）
  pvTick(n2){ const raf=window.requestAnimationFrame; window.requestAnimationFrame=()=>0;   // 手動駆動中はRAF多重登録を防ぐ
    try{ for(let i2=0;i2<(n2||1);i2++) _tick(); } finally{ window.requestAnimationFrame=raf; }
    return {ticked:n2||1}; },   // 診断用: RAF停止環境でフレーム手動駆動
  get pvDbg(){ return {playing,cur,BPM,meshes:meshes.filter(m=>m.obj.kind==='note'||m.obj.kind==='wall').slice(0,30).map(m=>({k:m.obj.kind,
    beat:m.obj.beat??m.obj.b, gone:m.group.userData._pvGone,
    mask:(m.group.children[0]||m.group).layers.mask}))}; },
  get inSel(){ return [..._inSel]; },
  get infoDbg(){ applyInfoChain(); return {base:structuredClone(infoBase),json:structuredClone(infoJson),
    chain:infoChain().map(n=>({id:n.id,kind:n.kind,data:n.data})),extra:extraNodes.map(n=>({id:n.id,kind:n.kind,data:n.data}))}; },
  counts(){ const o={}; for(const k in projDiffs){ const st=projDiffs[k];
    o[k]={n:(st.notes||[]).length,b:(st.bombs||[]).length,w:(st.walls||[]).length,a:(st.arcs||[]).length,c:(st.chains||[]).length,l:(st.lightEvents||[]).length,
      sec:(st.sections||[]).length,secItems:(st.sections||[]).reduce((m,s)=>m+Object.values(s.content||{}).reduce((m2,ar)=>m2+(ar||[]).length,0),0)}; } return o; } };   // 開発用: 保存/復元の診断
scene.add(new THREE.AmbientLight(0x5a5a5a,1.4));
const dl=new THREE.DirectionalLight(0xe8e8e8,0.7); dl.position.set(4,8,-3); scene.add(dl);

// ---- 正面プレビュー（第2レンダラ・レイヤー1=編集ヘルパは非表示） ----
camera.layers.enable(1);
camera.layers.enable(3);         // 譜面オブジェクト（プレビュー側は表示トグル対象）
function tagHelper(o){ o.traverse(c=>c.layers.set(1)); }
// ---- エラー可視化（無言で失敗しない） ----
function showErr(msg){
  if(typeof msg==='string') msg=t('m:'+msg,msg);   // 静的メッセージは辞書(m:)で翻訳。動的文字列はキー不一致でそのまま
  console.error(msg);
  const el=document.getElementById('errToast');
  el.textContent='⚠ '+msg; el.style.display='block';
  clearTimeout(showErr._t); showErr._t=setTimeout(()=>el.style.display='none',12000);
}
function showOk(msg){
  if(typeof msg==='string') msg=t('m:'+msg,msg);   // 静的メッセージは辞書(m:)で翻訳
  const el=document.getElementById('errToast');
  el.textContent='✅ '+msg;
  el.style.background='#12321e'; el.style.borderColor='#56ffc1'; el.style.color='#aef0cd';
  el.style.display='block';
  clearTimeout(showErr._t); showErr._t=setTimeout(()=>{ el.style.display='none';
    el.style.background='#3a1216'; el.style.borderColor='#ff4d5e'; el.style.color='#ffb3bb'; },4000);
}
addEventListener('error',e=>showErr(`${e.message} (${(e.filename||'').split('/').pop()}:${e.lineno})`));
addEventListener('unhandledrejection',e=>showErr('Promise: '+(e.reason&&e.reason.stack||e.reason)));

// ---- 多言語（lang/*.json、localStorageに選択を保存） ----
let LANG={}, langCode=localStorage.getItem('bsnm_lang')||'ja';
function t(k,def){ return (LANG&&Object.prototype.hasOwnProperty.call(LANG,k))?LANG[k]:def; }
const TL=(k,def)=>t(k,def);   // t()の安全な別名（引数名tでシャドウされる関数=srcCardHTML等の内部からも翻訳できるように）
function tf(key,def,vars){ let s=t(key,def); if(vars) for(const k in vars) s=s.split('{'+k+'}').join(String(vars[k])); return s; }   // 差し込み穴つき翻訳（動的値を含むトースト用。{name}等を置換）
async function loadLang(){
  try{ LANG=await (await fetch('lang/'+langCode+'.json?v='+(typeof ICON_V!=='undefined'?ICON_V:1),{cache:'no-cache'})).json(); }catch(e){ LANG={}; console.warn('lang読込失敗',e); }
  document.querySelectorAll('[data-i18n]').forEach(el=>{ el.textContent=t(el.dataset.i18n,el.textContent); });
  document.querySelectorAll('[data-i18n-t]').forEach(el=>{ el.title=t(el.dataset.i18nT,el.title); });
  document.querySelectorAll('[data-i18n-ph]').forEach(el=>{ el.placeholder=t(el.dataset.i18nPh,el.placeholder); });
  document.documentElement.style.setProperty('--srcon', JSON.stringify('● '+t('ui.srcActive','出力中')));   // CSS ::after（出力中バッジ）の翻訳
  setPvMode(pvMode); setNodeMode(nodeMode); updateMainModeLabel();
  if(typeof refreshInspector==='function') refreshInspector();   // INFOノードカード/曲情報など動的生成テキストを再翻訳（言語切替時）
  if(document.getElementById('tbDirPanel')) buildDirPanel();
  if(typeof updateModeIndicator==='function') updateModeIndicator();   // 配置/編集モード表示は動的管理（data-i18n非依存）＝言語切替でも現在モードの訳語を出す
}
// ---- ペインモード（Tabで切替。マウスの乗っているペインが対象） ----
let curTab='tabFolder', pvMode='media', nodeMode='edit', nodeColMode='nle', hoverPane='main';   // 起動時はMEDIAを先に表示（ヘルバ様指示）
async function setModeLabel(id,icon,txt,nextTxt){ const el=document.getElementById(id);
  el.innerHTML=(await tbIcon(icon))+`<span class="mlMain">${txt.toUpperCase()}</span>`
    +`<span class="mlNext">${await tbIcon('cycle_tab')}<span>${nextTxt.toUpperCase()}</span></span>`;
}
function setPvMode(m){ pvMode=m; curTab=(m==='preview')?'bodyPv':'tabFolder';
  document.getElementById('bodyPv').classList.toggle('on',m==='preview');
  document.getElementById('tabFolder').classList.toggle('on',m!=='preview');
  const pv=t('mode.preview','Preview'), md=t('mode.media','Media');
  setModeLabel('pvModeLabel',(m==='preview')?'eye':'folder',(m==='preview')?pv:md,(m==='preview')?md:pv);
  if(m!=='preview') renderMetaList();
}
function setNodeMode(m){ nodeMode='edit';   // INFOモードは廃止（ノード側で編集）
  document.getElementById('infoPanel').style.display='none';
}
// ノード列: NLE（レイヤー/Musicタイムライン＋ボリューム）⇄ INFO（曲情報バー）をTab/クリックで切替
function setNodeColMode(m){ nodeColMode=m; const info=(m==='info'), gid=id=>document.getElementById(id);
  const ins=gid('inspcol'); if(ins) ins.style.display=info?'block':'none';
  { const nk=gid('nodeKeys'), bd=nk&&(nk.querySelector('.mkbody')||nk); if(bd&&typeof KEYSHTML_NLE!=='undefined') bd.innerHTML=info?KEYSHTML_NODE:KEYSHTML_NLE; }   // INFO=旧NODE流儀のショートカット表示（ヘッダーは温存しボディだけ差し替え）
  if(typeof applyShowKeys==='function') applyShowKeys();   // NLE/INFOで表示トグルが別（設定5分割）
  const np=gid('nodepane'), ov=gid('overview'), sp=gid('specPane'), vm=gid('vmcol');
  if(np) np.style.display=info?'none':''; if(ov) ov.style.display=info?'none':''; if(sp) sp.style.display=info?'none':''; if(vm) vm.style.display=info?'none':'flex';
  { const dt=gid('diffTools'); if(dt) dt.style.display=info?'none':'flex'; }   // 難易度バーはNLE専用（INFOでは隠す）
  { const mb=gid('musicBar'); if(mb) mb.style.display=info?'none':'flex'; }   // BPM/メトロ/プレビュー秒の帯もNLE専用
  if(info&&typeof layoutInfoNodes==='function'){ layoutInfoNodes(); if(typeof infoAutoCenter==='function') infoAutoCenter(); }   // センタリングは他パネルを隠してinspcolが最終サイズになった後（先に呼ぶと縮んだ矩形で計算され上に寄る）
  setModeLabel('nodeColModeLabel', info?'info':'nle', info?'INFO':'NLE', info?'NLE':'INFO');   // 他モードラベルと同一様式（アイコン＋TABピル）
  if(!info) resize();
}
const KEYS_COMMON=[
  ['回転','🖱️ 中ドラッグ'],
  ['パン','Shift + 🖱️ 中ドラッグ'],
  ['ズーム','Shift + 🖱️ ホイール'],
  ['範囲選択','🖱️ 左ドラッグ'],
  ['追加選択','Shift + 🖱️ 左クリック/ドラッグ'],
  ['選択解除','A'],
  ['---'],
  ['削除','X / Del'],
  ['取り消し','Ctrl + Z'],
  ['やり直し','Shift + Ctrl + Z'],
  ['コピー / 貼り付け / カット','Ctrl + C ／ Ctrl + V ／ Ctrl + X'],
  ['---'],
  ['再生 / 停止','Space'],
  ['タイムライン操作','🖱️ ホイール'],
  ['1コマ進む / 戻る','→ ／ ←'],
  ['スタート / 曲末へ','Ctrl + ← ／ →'],
  ['4拍イージング','Shift + Ctrl + ← ／ →'],
  ['---'],
  ['スナップパイ','，'],
  ['再生ヘッドにジャンプ','.'],
  ['---'],
  ['マーカー挿入','Ctrl + E'],
  ['前/次のマーカーへ','Ctrl + [ ／ Ctrl + ]'],
  ['---'],
  ['難易度切替','1〜5（Easy〜Expert+）'],
];
const KEYS_NOTE=[
  ['配置モード / カメラ固定モード切替','Q'],
  ['追加','🖱️ 左クリック'],
  ['削除','🖱️ 右クリック'],
  ['向き回転','Alt + 🖱️ ホイール'],
  ['色の反転','F'],
  ['アーク / チェーン','2個以上 Ctrl+R ／ Ctrl+T・C（同色連続ペア）'],
  ['アーク','Alt + 🖱️ ホイール = mu（頭曲率）／ Ctrl + Alt + 🖱️ ホイール = tmu（尾曲率）'],
  ['チェーン','Ctrl + 🖱️ ホイール = 分割数 ／ Ctrl + Alt + 🖱️ ホイール = squish（詰め）'],
  ['壁のサイズ','S'],
];
const KEYS_LIGHT=[
  ['配置モード / カメラ固定モード切替','Q'],
  ['追加','🖱️ 左クリック'],
  ['削除(ライト)','🖱️ 右クリック'],
  ['数値の増減','Alt + 🖱️ ホイール'],
  ['色を回転','F'],
  ['カラーパイ','C'],
  ['数値を±1刻みで増減','Ctrl + Alt + 🖱️ ホイール'],
];
// ================= ショートカット リマップ基盤（データ駆動・ヘルバ様指定 2026-07-15）=================
// ACTIONS = 再割当できるキー系ショートカットの一元定義。def=既定バインド {k:キー, c:Ctrl, a:Alt, s:Shift}。
// マウス/ホイール操作は再割当対象外（ショートカット表に参考表示）。
// ※Phase2 実施済み(2026-07-15)：keydown/keyup各ハンドラの直書きキー判定を hit(e,id) / effBind へ置換＝ショートカット編集の再割当が実際に反映される。既定バインドのままなら挙動は不変。
const ACTIONS=[
  // 共通
  {id:'play',        cat:'common', label:'再生 / 停止',            def:{k:' '}},
  {id:'frameNext',   cat:'common', label:'1コマ進む',             def:{k:'ArrowRight'}},
  {id:'framePrev',   cat:'common', label:'1コマ戻る',             def:{k:'ArrowLeft'}},
  {id:'jumpStart',   cat:'common', label:'スタートへ',            def:{k:'ArrowLeft', c:true}},
  {id:'jumpEnd',     cat:'common', label:'曲末へ',                def:{k:'ArrowRight',c:true}},
  {id:'snapPie',     cat:'common', label:'スナップパイ',          def:{k:','}},
  {id:'jumpHead',    cat:'common', label:'再生ヘッドにジャンプ',  def:{k:'.'}},
  {id:'markerAdd',   cat:'common', label:'マーカー挿入',          def:{k:'e', c:true}},
  {id:'markerPrev',  cat:'common', label:'前のマーカーへ',        def:{k:'[', c:true}},
  {id:'markerNext',  cat:'common', label:'次のマーカーへ',        def:{k:']', c:true}},
  {id:'undo',        cat:'common', label:'取り消し',              def:{k:'z', c:true}},
  {id:'redo',        cat:'common', label:'やり直し',              def:{k:'z', c:true, s:true}},
  {id:'copy',        cat:'common', label:'コピー',                def:{k:'c', c:true}},
  {id:'paste',       cat:'common', label:'貼り付け',              def:{k:'v', c:true}},
  {id:'cut',         cat:'common', label:'カット',                def:{k:'x', c:true}},
  {id:'save',        cat:'common', label:'保存',                  def:{k:'s', c:true}},
  {id:'saveAs',      cat:'common', label:'名前を付けて保存',      def:{k:'s', c:true, s:true}},
  {id:'open',        cat:'common', label:'開く',                  def:{k:'o', c:true}},
  {id:'del',         cat:'common', label:'削除',                  def:{k:'x'}},
  {id:'deselect',    cat:'common', label:'選択解除',              def:{k:'a'}},   // 全ペイン共通（3D/NLE/INFO/ノード）＝そのペインの選択だけを解除（ヘルバ様指定）
  {id:'lightMode',   cat:'common', label:'NOTES / LIGHTING 切替', def:{k:'Tab'}},   // Tabに一本化（3Dビュー上）。旧L切替は廃止（Lはレーンロック専用・ヘルバ様指定 2026-07-15）
  {id:'camMode',     cat:'common', label:'配置 / カメラ固定モード切替',  def:{k:'q'}},
  // NOTES
  {id:'noteFlip',    cat:'notes',  label:'色の反転',              def:{k:'f'}},
  {id:'noteArc',     cat:'notes',  label:'アーク作成',            def:{k:'r', c:true}},
  {id:'noteChain',   cat:'notes',  label:'チェーン作成',          def:{k:'t', c:true}},
  {id:'noteWall',    cat:'notes',  label:'壁のサイズ',            def:{k:'s'}},
  {id:'notePie',     cat:'notes',  label:'配置パイ',              def:{k:'w'}},
  // LIGHTING
  {id:'lightCycle',  cat:'light',  label:'色を回転',              def:{k:'f'}},
  {id:'lightPie',    cat:'light',  label:'ライト動作パイ',        def:{k:'w'}},
  {id:'lightColorPie',cat:'light', label:'カラーパイ',            def:{k:'c'}},
  // NLE
  {id:'nleCut',      cat:'nle',    label:'カット',                def:{k:'c'}},
  {id:'nleMerge',    cat:'nle',    label:'マージ',                def:{k:'g', c:true}},
  {id:'nleLock',     cat:'nle',    label:'レーン ロック',         def:{k:'l'}},
  {id:'nleSolo',     cat:'nle',    label:'レーン ソロ',           def:{k:'s'}},
  {id:'nleMute',     cat:'nle',    label:'レーン ミュート',       def:{k:'m'}},
];
const ACT_BY_ID={}; for(const a of ACTIONS) ACT_BY_ID[a.id]=a;
const ACT_CATS=[['common','共通'],['notes','NOTES'],['light','LIGHTING'],['nle','NLE']];
let _keymap={};   // ユーザー上書き {id:{k,c,a,s}}。既定と異なるものだけ保持
try{ _keymap=JSON.parse(localStorage.getItem('bsnm_keymap')||'{}')||{}; }catch(_){ _keymap={}; }
function saveKeymap(){ try{ localStorage.setItem('bsnm_keymap',JSON.stringify(_keymap)); }catch(_){} }   // bsnm_* なので config/settings.json へ自動ミラー
function effBind(id){ const a=ACT_BY_ID[id]; if(!a) return null; return _keymap[id]||a.def; }   // 実効バインド（上書き優先）
function _normKey(k){ return (k&&k.length===1)?k.toLowerCase():k; }   // 1文字キーは小文字化（大小無視）
function comboFromEvent(e){ return {k:_normKey(e.key), c:!!e.ctrlKey||!!e.metaKey, a:!!e.altKey, s:!!e.shiftKey}; }
function sameBind(x,y){ return !!x&&!!y&&_normKey(x.k)===_normKey(y.k)&&!!x.c===!!y.c&&!!x.a===!!y.a&&!!x.s===!!y.s; }
// hit(e,id): 押されたキーが action id の実効バインドと一致するか（Phase2でハンドラの直書き判定を置換）
function hit(e,id){ const b=effBind(id); if(!b) return false; return sameBind(comboFromEvent(e),b); }
function comboStr(b){ if(!b) return '—';
  let s=''; if(b.c) s+='Ctrl + '; if(b.a) s+='Alt + '; if(b.s) s+='Shift + ';
  const k=b.k===' '?'Space':b.k==='ArrowLeft'?'←':b.k==='ArrowRight'?'→':b.k==='ArrowUp'?'↑':b.k==='ArrowDown'?'↓':(b.k&&b.k.length===1?b.k.toUpperCase():b.k);
  return s+k; }
function renderModeKeys(){
  const rows=arr=>arr.map(([d,k])=>d==='---'?'<div class="mksep"></div>':`<div class="mkrow"><span class="mkd">${t('sk:'+d,d)}</span><span class="mk">${t('skk:'+k,k)}</span></div>`).join('');   // '---'=区切り線／ラベル・操作列はt()で翻訳（英語=skk:キーは日本語を含む操作のみ辞書化・純キーはそのまま）
  const el=document.getElementById('modeKeys'); if(el) (el.querySelector('.mkbody')||el).innerHTML=rows(lightMode?KEYS_LIGHT:KEYS_NOTE);
  const ck=document.getElementById('commonKeys'); if(ck) (ck.querySelector('.mkbody')||ck).innerHTML=rows(KEYS_COMMON);
}
function updateMainModeLabel(){
  renderModeKeys();
  if(typeof applyShowKeys==='function') applyShowKeys();   // NOTES/LIGHTで左上の表示切替が変わる
  const nt=t('mode.note','Notes'), lt=t('mode.light','Lighting');
  setModeLabel('mainModeLabel',lightMode?'light_on':'note',lightMode?lt:nt,lightMode?nt:lt);
  document.querySelectorAll('.tbgNoteGrp').forEach(el=>el.style.display=lightMode?'none':'');   // ノーツ系3ボックス（配置/色/アーク・チェイン）をまとめて切替
  document.querySelectorAll('.tbgLightGrp').forEach(el=>el.style.display=lightMode?'':'none');   // ライト系ボックス（動作/色/レーザー色/明るさ）をまとめて切替
  try{ updateLightColorTB(); }catch(_){}   // ライト色ツールバー(Chroma1個/バニラ5個)を現在の状態へ
}
function renderMetaList(){
  const el=document.getElementById('metaList');
  const ordered=[...sections].sort((a,b)=>a.beat-b.beat);
  el.innerHTML=ordered.length?'':'<div style="color:#5d7596">セクション未作成（下部タイムラインをダブルクリック）</div>';
  ordered.forEach((s,i)=>{ const d=document.createElement('div');
    const col=SEC_COLORS[sections.indexOf(s)%SEC_COLORS.length];
    d.innerHTML=`<span style="color:${col}">■ ${s.label}</span><span style="color:#6f88ad">拍 ${s.beat}</span>`;
    d.onclick=()=>{ cur=s.beat; offset=beatToTimeTM(cur); };
    el.appendChild(d); });
}

addEventListener('keydown', e=>{ if(e.key==='Control') controls.enabled=false; });
// AltはWindowsではCtrl/Shiftと違い「メニューアクセスキー」としてOS/ブラウザ側で特別扱いされ、
// ホイール操作等と絡むとkeyupが届かず「押されたまま」に見える不具合が起きうる（Alt+ホイールで方向を
// 変えた後、ノーツの移動ギズモが反応しなくなり、Altをもう一度押すと直る症状の原因・ヘルバ様報告 2026-09-20）。
// keydown側でこの経路に入らせない（既定動作を止める）ことで発生を防ぐ。
addEventListener('keydown', e=>{ if(e.key==='Alt') e.preventDefault(); });
addEventListener('keyup',   e=>{ if(e.key==='Control') controls.enabled=true;
  // パイは「押して開き・離して確定」。離したキーが該当アクションの実効バインドと一致したら確定（再割当対応・Phase2）
  if(pieOpen){ const rk=_normKey(e.key), eq=id=>{ const b=effBind(id); return !!b&&_normKey(b.k)===rk; };
    if((pieKey===','&&eq('snapPie'))||(pieKey==='w'&&(eq('notePie')||eq('lightPie')))||(pieKey==='c'&&eq('lightColorPie'))) closePie(true); } });

// ---- 中ドラッグ回転（自前実装）: 軸はマウスのある拍のグリッド中央線 ----
let orbitDrag=null, panDrag=null;
function rotAround(pivot,axis,angle){
  const q=new THREE.Quaternion().setFromAxisAngle(axis.clone().normalize(),angle);
  camera.position.sub(pivot).applyQuaternion(q).add(pivot);
  controls.target.sub(pivot).applyQuaternion(q).add(pivot);
}
document.getElementById('main').addEventListener('pointerdown', e=>{
  if(e.button===1){
    if(e.ctrlKey||e.altKey||e.metaKey) return;   // 未設定: Ctrl/Alt/Meta+中ドラッグは無効（素=回転・Shift=パンのみ）
    if(e.shiftKey){ controls.mouseButtons.MIDDLE=null; e.preventDefault();
      panDrag={x:e.clientX,y:e.clientY}; }   // 自前パン: 速度を床までの距離基準で安定させる
    else { controls.mouseButtons.MIDDLE=null; e.preventDefault();
      // 支点=マウスポインタ直下の床位置（両モード共通。突然の180度反転を防ぐ）
      setPtr(e);
      let pv=null;
      // 床に当たっても、±12/±36を超える遠方(地平線すれすれ)はクランプでマウス直下から外れるので支点に使わない
      if(raycaster.ray.intersectPlane(floorPlane,_fv)&&Math.abs(_fv.x)<=12&&Math.abs(_fv.z)<=36)
        pv=new THREE.Vector3(_fv.x,0.4,_fv.z);
      // 床に当たらない(地平線より上)/遠すぎる時は、マウスの向きに現在の注視距離だけ進んだ点。
      // 以前はここで再生ヘッド(z=0)固定だったため「ヘッド中心に回る」感覚になっていた
      if(!pv) pv=camera.position.clone().addScaledVector(raycaster.ray.direction,camera.position.distanceTo(controls.target));
      orbitDrag={x:e.clientX,y:e.clientY,pivot:pv}; }
  }
}, true);
addEventListener('pointermove', e=>{
  if(panDrag){
    const dx=e.clientX-panDrag.x, dy=e.clientY-panDrag.y;
    panDrag.x=e.clientX; panDrag.y=e.clientY;
    // 画面中央の視線が床と交わる距離を基準に1pxあたりの移動量を決める（2〜28にクランプ）
    const fwd=new THREE.Vector3(); camera.getWorldDirection(fwd);
    let dist=camera.position.distanceTo(controls.target);
    if(Math.abs(fwd.y)>1e-3){ const t=-camera.position.y/fwd.y; if(t>0) dist=t; }
    dist=Math.max(2,Math.min(28,dist));
    const r=cv.getBoundingClientRect();
    const f=2*Math.tan(THREE.MathUtils.degToRad(camera.fov/2))*dist/r.height*camPanSpeed;
    const right=new THREE.Vector3().setFromMatrixColumn(camera.matrixWorld,0);
    const up=new THREE.Vector3().setFromMatrixColumn(camera.matrixWorld,1);
    const mv=right.multiplyScalar(-dx*f).addScaledVector(up,dy*f);
    camera.position.add(mv); controls.target.add(mv); controls.update();
    return;
  }
  if(!orbitDrag) return;
  const dx=e.clientX-orbitDrag.x, dy=e.clientY-orbitDrag.y;
  orbitDrag.x=e.clientX; orbitDrag.y=e.clientY;
  rotAround(orbitDrag.pivot,new THREE.Vector3(0,1,0),-dx*0.006*camRotSpeed);       // 中央線(縦軸)まわり
  const right=new THREE.Vector3().setFromMatrixColumn(camera.matrixWorld,0);
  rotAround(orbitDrag.pivot,right,-dy*0.006*camRotSpeed);                           // 上下の見込み角
  controls.update();
});
addEventListener('pointerup', e=>{ if(e.button===1){ orbitDrag=null; panDrag=null; } });

// 背景の薄いグリッド（空間の基準。プレビューには映さない）
const bgGrid=new THREE.GridHelper(400,200,0x2c2c2c,0x1d1d1d);
bgGrid.position.y=-0.02; scene.add(bgGrid);
// ---- レーン帯のX配置（ヘルバ様指定 2026-07-18の大改修）----
// 旧: 拍番号帯を挟んで「ライト=左 / ノーツ=右」に分かれ、非編集側は減光して残していた。
// 新: モードごとに片方だけを表示し、ノーツ列は「ライトレーンと同じ場所」へ寄せる＝どちらのモードでも
//     画面上の見え方（拍番号帯との距離・レーンの位置）が揃う。拍番号帯(-NUMX)は動かさない。
// ノーツとライトはワールド座標上で重なるが、同時に表示されることが無いので問題にならない。
const NUMX=1.79;                                      // 拍番号帯の中心X（帯は動かさない＝両モード共通の基準）
const NUM_HALF=0.3;                                   // 拍番号帯の半幅（numStripGeo=PlaneGeometry(0.6,…)）
const NOTE_EDGE=1.25;                                 // ノーツ床の半幅（floor=PlaneGeometry(2.5,…)）
const NUM_GAP=(NUMX-NUM_HALF)-NOTE_EDGE;              // 帯 ↔ レーン群 の隙間（旧レイアウトのノーツ側の隙間を踏襲）
const LANE_NEAR=-(NUMX+NUM_HALF+NUM_GAP);             // レーン群の手前端＝帯の外側＋同じ隙間（ライト/ノーツ共通）
// ノーツ側は全体をこのオフセットで移動する。ワールドX計算は必ず NOTE_DX 込みで行い、
// 逆変換（マウスのワールドX → 列番号）では必ず NOTE_DX を引くこと。
const NOTE_DX=LANE_NEAR-NOTE_EDGE;
// noteRoot = ノーツ側の表示ON/OFFをまとめて切り替えるための入れ物。
// 変換は常に恒等（position/rotation/scaleを触らない）＝ローカル座標＝ワールド座標のまま。
// これにより当たり判定・ギズモ・ゴーストのX計算に一切影響を与えずに visible だけを一括制御できる。
const noteRoot=new THREE.Group(); scene.add(noteRoot);
// floor + lanes
const floor=new THREE.Mesh(new THREE.PlaneGeometry(2.5,160),new THREE.MeshStandardMaterial({color:0x141414,roughness:.9,polygonOffset:true,polygonOffsetFactor:1,polygonOffsetUnits:2}));
floor.rotation.x=-Math.PI/2; floor.position.set(NOTE_DX,0,20); noteRoot.add(floor);
for(let i=0;i<=4;i++){ const l=new THREE.Mesh(new THREE.BoxGeometry(0.02,0.003,160),new THREE.MeshBasicMaterial({color:0x232323}));
  l.position.set((i-2)*LANE+NOTE_DX,0.01,20); noteRoot.add(l); }

// edit plane (4x3)
const editGroup=new THREE.Group(); noteRoot.add(editGroup);   // position.x は触らない（ローカル=ワールドを維持・NOTE_DXは各要素側で加算）
const cellPlanes=[];
const editGridVis=[];   // 黄色の12マス枠＋薄い塗り（配置モードでは非表示にする＝ヘルバ様指定。cellPlanes/ghostは別扱いで残す）
for(let x=0;x<4;x++)for(let y=0;y<3;y++){
  const ed=new THREE.LineSegments(new THREE.EdgesGeometry(new THREE.PlaneGeometry(LANE*0.96,LAYER*0.96)),
    new THREE.LineBasicMaterial({color:0xffd82d,transparent:true,opacity:0.8}));
  ed.position.set((1.5-x)*LANE+NOTE_DX,BASE_Y+y*LAYER,0); editGroup.add(ed); editGridVis.push(ed);   // レーン軸反転（NLEの並びと一致させる）
  const p=new THREE.Mesh(new THREE.PlaneGeometry(LANE*0.96,LAYER*0.96),
    new THREE.MeshBasicMaterial({visible:false,side:THREE.DoubleSide}));
  p.position.copy(ed.position); p.userData={x,y}; editGroup.add(p); cellPlanes.push(p);
}
const editFill=new THREE.Mesh(new THREE.PlaneGeometry(4*LANE,3*LAYER),
  new THREE.MeshBasicMaterial({color:0xffd82d,transparent:true,opacity:0.06,side:THREE.DoubleSide}));
editFill.position.set(NOTE_DX,BASE_Y+LAYER,0.001); editGroup.add(editFill); editGridVis.push(editFill);

// マウス拍ライン（常時・黄）
const mouseLine=new THREE.Mesh(new THREE.BoxGeometry(10.8,0.004,0.011),
  new THREE.MeshBasicMaterial({color:0xffd82d}));
mouseLine.position.set(-3.5,0.03,0); mouseLine.visible=false; scene.add(mouseLine);   // 再生ラインと同じくライティングレーンの端まで

// 再生ヘッド（赤枠+半透明赤盤、常に z=0）
const playFrame=new THREE.Group(); scene.add(playFrame);
// 再生ヘッドはノーツ側・ライト側・共通（床ライン/◆）が同居するため、モード別にvisibleを切れるよう
// 恒等変換のサブグループへ分ける（位置は一切変わらない）。共通部分は playFrame 直下に残す。
const pfNotes=new THREE.Group(); playFrame.add(pfNotes);
const pfLight=new THREE.Group(); playFrame.add(pfLight);
pfNotes.add(new THREE.LineSegments(
  new THREE.EdgesGeometry(new THREE.PlaneGeometry(4*LANE+0.1,3*LAYER+0.1)),
  new THREE.LineBasicMaterial({color:0xff3344})));
pfNotes.children[0].position.set(NOTE_DX,BASE_Y+LAYER,0);
const playFill=new THREE.Mesh(new THREE.PlaneGeometry(4*LANE+0.1,3*LAYER+0.1),
  new THREE.MeshBasicMaterial({color:0xff3344,transparent:true,opacity:0.10,side:THREE.DoubleSide,depthWrite:false}));
playFill.position.set(NOTE_DX,BASE_Y+LAYER,0); pfNotes.add(playFill);
// 赤フレーム内部を4列×3行=12マスに分割（ノーツが入る部分の目安。内部線=縦3本+横2本、外枠は既存）
{ const gy0=BASE_Y-0.5*LAYER, gy1=BASE_Y+2.5*LAYER, gp=[];
  for(const gx of [-LANE,0,LANE]) gp.push(gx+NOTE_DX,gy0,0, gx+NOTE_DX,gy1,0);                       // 縦の仕切り3本（4列）
  for(const gy of [BASE_Y+0.5*LAYER,BASE_Y+1.5*LAYER]) gp.push(-2*LANE+NOTE_DX,gy,0, 2*LANE+NOTE_DX,gy,0);   // 横の仕切り2本（3行）
  const gg=new THREE.BufferGeometry(); gg.setAttribute('position',new THREE.Float32BufferAttribute(gp,3));
  pfNotes.add(new THREE.LineSegments(gg,new THREE.LineBasicMaterial({color:0xff3344,transparent:true,opacity:0.30}))); }
const playFloorLine=new THREE.Mesh(new THREE.BoxGeometry(10.8,0.005,0.026),
  new THREE.MeshBasicMaterial({color:0xff3344,depthTest:false,depthWrite:false}));
playFloorLine.position.set(-3.5,0.014,0); playFloorLine.renderOrder=8; playFrame.add(playFloorLine);   // ライティングレーンの端まで届く長さ。地面に接地（浮きを解消＝ヘルバ様指定 2026-07-14）。depthTest:false+renderOrderでマーカーバナーに埋もれず常に最前面
// 拍番号レーン上の現在拍マーカー（NLEルーラーの▼に相当する赤いひし形）
const playDiamond=new THREE.Mesh(new THREE.BoxGeometry(0.17,0.012,0.17),
  new THREE.MeshBasicMaterial({color:0xff3344,depthTest:false,depthWrite:false}));
playDiamond.rotation.y=Math.PI/4; playDiamond.position.set(-NUMX,0.014,0); playDiamond.renderOrder=9; playFrame.add(playDiamond);   // 地面に接地（浮きを解消・ヘルバ様指定 2026-07-14）。最前面描画でマーカー等に埋もれない
let scrubDrag=false;   // シークの入口は拍番号レーンのみ（赤ライン掴みの旧ハンドルは廃止済み）

// スナップ分割線
const subPool=[]; for(let i=0;i<560;i++){ const m=new THREE.Mesh(new THREE.BoxGeometry(2.5,0.003,0.012),
  new THREE.MeshBasicMaterial({color:0x1f1f1f})); m.visible=false; noteRoot.add(m); subPool.push(m); }

// beat lines + 拍番号
const beatPool=[]; for(let i=0;i<96;i++){ const b=new THREE.Mesh(new THREE.BoxGeometry(2.5,0.003,0.02),
  new THREE.MeshBasicMaterial({color:0x2a2a2a})); b.visible=false; noteRoot.add(b); beatPool.push(b); }
const numTexCache={};
function numTex(n){ if(numTexCache[n]) return numTexCache[n];
  const c=document.createElement('canvas'); c.width=128; c.height=64; const g=c.getContext('2d');
  g.font='bold 38px '+FONT; g.textAlign='center'; g.textBaseline='middle';
  g.fillStyle=(n%4===0)?'#e7e7e7':'#8a8a8a'; g.fillText(String(n),64,33);
  const t=new THREE.CanvasTexture(c); t.anisotropy=MAXANISO; numTexCache[n]=t; return t; }
// 拍番号は床に張り付いた平面（スプライト=立て看板だと画面端/浅い角度でクリック判定の帯とパララックスでズレるため）
const numGeo=new THREE.PlaneGeometry(0.72,0.36); numGeo.rotateX(-Math.PI/2); numGeo.rotateY(Math.PI/2);   // マーカーラベルと同じ向き（タイムライン方向に読む）
const numPool=[]; for(let i=0;i<96;i++){ const s=new THREE.Mesh(numGeo,new THREE.MeshBasicMaterial({transparent:true,depthWrite:false}));
  s.renderOrder=6;   // 常にバーより後=数字が沈まない
  s.visible=false; scene.add(s); numPool.push(s); }
// 拍番号の帯: クリックでその拍へジャンプ（透明な当たり判定）
const numStripGeo=new THREE.PlaneGeometry(0.6,40*ZPB); numStripGeo.rotateX(-Math.PI/2);
const numStrip=new THREE.Mesh(numStripGeo,
  new THREE.MeshBasicMaterial({color:0x2a2a32,transparent:true,opacity:0.8,depthWrite:false}));   // 灰色バー=クリックで飛べる範囲の明示（当たり判定と同一面）
numStrip.renderOrder=5;   // 半透明の距離ソートに任せず「バー→数字」の順を固定（角度で数字が沈む問題の防止）
numStrip.position.set(-NUMX,0.018,0); scene.add(numStrip);
numStrip.raycast=()=>{};   // クリックでの拍ジャンプ/ドラッグスクラブは廃止（表示のみ）。奥の帯が手前のノーツ/ギズモへの
                            // クリックを奪ってしまう不具合の原因だった（ヘルバ様報告 2026-09-20）。見た目はそのまま残す。
// スペクトログラム表示帯: 拍番号帯(-NUMX)とは反対側＝ノーツ床の外側に、ノーツ配置空間(2*NOTE_EDGE)の
// 約70%の幅で表示する（拍番号帯は奥で見づらい・帯自体も細すぎるとのヘルバ様指摘 2026-09-21）。
// 帯とレーン床の隙間は拍番号帯と同じNUM_GAPを踏襲して見た目を揃える。
let specForBuf=null, specMag=null, specBins=56, specHop=0, specCols=0, specSrcCanvas=null;   // 解析結果本体はbuildSpectroData（波形データ節）で埋める
const SPEC_W=0.7*(2*NOTE_EDGE);
const SPEC_X=NOTE_DX-NOTE_EDGE-NUM_GAP-SPEC_W/2;
const specGeo=new THREE.PlaneGeometry(SPEC_W,40*ZPB); specGeo.rotateX(-Math.PI/2);
const specBand=new THREE.Mesh(specGeo,new THREE.MeshBasicMaterial({color:0x2a2a32,transparent:true,opacity:0.9,depthWrite:false}));
specBand.renderOrder=5; specBand.position.set(SPEC_X,0.018,0); scene.add(specBand);
specBand.raycast=()=>{};   // 表示専用（拍ジャンプ等の当たり判定は持たせない。numStripと同じ流儀）
// ウィンドウ切り出し用の小さなcanvas。specMag(生の解析結果)から直接、周波数=横軸(u)・時間=縦軸(v)で書き込む
// （specSrcCanvasは2D側の横長表示用に周波数=縦・時間=横で持っているため、そのままdrawImageすると軸が入れ替わってしまう＝
//   曲頭の解析時点で気付けなかった不具合。ここではspecMagから直接、正しい軸でピクセルを書く）
const _specWinCanvas=document.createElement('canvas'); _specWinCanvas.width=specBins; _specWinCanvas.height=2400;   // 2D側に見劣りしないよう表示解像度を確保（解析自体の細かさはspecHopのまま変えない＝表示だけを上げる）
const _specWinCtx=_specWinCanvas.getContext('2d');
const _specWinTex=new THREE.CanvasTexture(_specWinCanvas); _specWinTex.anisotropy=MAXANISO;
_specWinTex.generateMipmaps=false; _specWinTex.minFilter=THREE.LinearFilter;   // ミップマップ(縮小時に複数解像度を混ぜる)が帯を斜めに見た時の色をぼかして薄く見せていた原因。
                                                                                // 生成をやめて等倍サンプリングにする＝2Dタイムラインと同じ鮮やかさで見えるように（ヘルバ様指摘 2026-09-21）
let _specWinKey=null;
// centerB=テクスチャの中心にする拍（再生ヘッド）/ viewB=3Dワールドの座標基準（拍番号・ノーツのzと同じ）。
// テクスチャは「量子化した中心拍(cB)±20拍」を焼き、帯自体は (cB-viewB)*ZPB に置く＝画像は拍と同じワールド座標に固定され、
// 再生中は拍番号・ノーツと一緒に流れる（旧: 帯を再生ヘッドのzへ動かしていたため画像が赤ラインと共に動き、実際の音の位置とズレた）。
function updateSpecBand(centerB,viewB){
  if(!specMag){
    if(specBand.material.map){ specBand.material.map=null; specBand.material.color.setHex(0x2a2a32); specBand.material.opacity=0.9; specBand.material.needsUpdate=true; }
    specBand.position.z=(centerB-viewB)*ZPB;
    return;
  }
  const key=Math.round(centerB*4);   // 1/4拍単位で変化した時だけ書き直す（毎フレームのputImageData/テクスチャアップロードを間引く）
  const cB=key/4;
  specBand.position.z=(cB-viewB)*ZPB;
  if(key!==_specWinKey){
    _specWinKey=key;
    const off=getSongOff();
    const winW=_specWinCanvas.width, winH=_specWinCanvas.height;
    const imgd=_specWinCtx.createImageData(winW,winH);
    for(let j=0;j<winH;j++){   // j=拍位置を等間隔に割ったサンプル（0=cB-20側…winH-1=cB+20側）。v軸(canvas縦)→world Z(帯の長さ方向)
      const beat=(cB-20)+40*(j+0.5)/winH,   // 画素の中心が指す拍（端の画素を端の拍そのものにすると全体が半画素ずれる）
 tt=off+beatToTimeTM(beat);   // 拍→時間は区分的（テンポパート境界を跨ぐと非線形）なので、
                                                                          // 窓の両端だけで時間を線形補間すると境界付近でズレる＝1行ごとに正しく変換する
      const inRange=(tt>=0&&tt<=songDur);
      const col=Math.max(0,Math.min(specCols-1,Math.round(tt/specHop)));
      for(let f=0;f<winW;f++){   // f=周波数ビン。u軸(canvas横)→world X(帯の幅方向)
        const v=inRange?specMag[col*specBins+f]:0;   // 無音追加などで曲の範囲外になった部分は真っ黒（無音）にする
        const [r,g,b]=specColor(v);
        const fx=winW-1-f;   // 左右反転（ノーツ側の端と外側の端を入れ替え。ヘルバ様指定 2026-09-21）
        const idx=(j*winW+fx)*4; imgd.data[idx]=r; imgd.data[idx+1]=g; imgd.data[idx+2]=b; imgd.data[idx+3]=255;
      }
    }
    _specWinCtx.putImageData(imgd,0,0);
    _specWinTex.needsUpdate=true;
  }
  if(specBand.material.map!==_specWinTex){ specBand.material.map=_specWinTex; specBand.material.color.setHex(0xffffff); specBand.material.opacity=1; specBand.material.needsUpdate=true; }
}
// 3Dビューのマーカー（縦ライン+半透明帯+名前ラベル）
const markerPool=[];
// マーカーバナーのX。旧=+2.05（レーン群が帯の右側にあった頃の空き地）。
// レーン群を帯の外側へ集約したので、帯を挟んだ反対側＝今は何も無い側へ寄せる（2026-07-18）。
// 段数(laneCount)が増えると外へ広がるので、基準を段数から逆算して「一番内側の段が帯に触れない」位置に固定する。
// 固定値にすると段数が増えたとき帯と拍番号の上へ乗り上げる（監査で検出）。
const MK_EDGE=0.17;   // ラベル半幅0.132＋余白。これ以上は帯(内端 -1.49)へ食い込む
function mkBaseX(){ return -(NUMX-NUM_HALF)+MK_EDGE+((laneCount()-1)/2)*0.20; }
// マーカー名はバーの上面に直接印字（チップは出さない）
const markNameGeo=new THREE.PlaneGeometry(2.4,0.44);
markNameGeo.rotateX(-Math.PI/2); markNameGeo.rotateY(Math.PI/2);
const markNameTexCache={};
function markNameTex(label){ if(markNameTexCache[label]) return markNameTexCache[label];
  const c=document.createElement('canvas'); c.width=512; c.height=96; const g=c.getContext('2d');
  g.font='bold 52px '+FONT; g.textAlign='center'; g.textBaseline='middle';
  g.fillStyle='#141414'; g.fillText(label,256,50,480);   // 中立ダーク（バナー色がパレット任意色になったため）
  const t=new THREE.CanvasTexture(c); t.anisotropy=MAXANISO; markNameTexCache[label]=t; return t; }   // ラベルレーンのX位置（拍番号の反対側=譜面の上側、床に平置き）
for(let i=0;i<32;i++){
  const g=new THREE.Group();
  const mat=new THREE.MeshBasicMaterial({color:0xffffff});
  // NLEのレイヤークリップと同期する薄板バー（4サブレーン・ペラペラ。端のキャップ/仕切り板は廃止）
  const bar=new THREE.Mesh(new THREE.BoxGeometry(0.17,0.012,1),mat);
  bar.position.y=0.02; g.add(bar);
  const label=new THREE.Mesh(markNameGeo,new THREE.MeshBasicMaterial({transparent:true,depthWrite:false}));
  label.position.set(0,0.035,0); label.scale.set(0.6,1,0.6); g.add(label);   // バー上面に名前（バー方向に沿って印字）
  g.userData={bar,label,mat};
  g.visible=false; scene.add(g); markerPool.push(g);
}
// ---- タイムラインマーカーの3D表現（NLEマーカー帯と同期・白固定）: 床ライン+拍番号帯の白◆+名前 ----
const tmPool=[];
const tmNameTexCache={};
function tmNameTex(label){ if(tmNameTexCache[label]) return tmNameTexCache[label];
  const c=document.createElement('canvas'); c.width=512; c.height=96; const g=c.getContext('2d');
  g.font='bold 46px '+FONT; g.textAlign='left'; g.textBaseline='middle';
  const txt='◆ '+label, tw=Math.min(504,g.measureText(txt).width+30);
  g.fillStyle='rgba(14,14,14,.68)'; g.beginPath(); g.roundRect(2,6,tw,84,16); g.fill();   // 半透明の板（視認性）
  g.fillStyle='#e8e8e8'; g.fillText(txt,17,51,474);                                        // ◆は名前の左
  const t=new THREE.CanvasTexture(c); t.anisotropy=MAXANISO; tmNameTexCache[label]=t; return t; }
{ const tmLineGeo=new THREE.BoxGeometry(10.8,0.004,0.016);   // 再生ヘッドの床ラインと同じ長さ（ライトレーン端まで）
  for(let i=0;i<16;i++){
    const g=new THREE.Group();
    const ln=new THREE.Mesh(tmLineGeo,new THREE.MeshBasicMaterial({color:0xffffff,transparent:true,opacity:0.4}));
    ln.position.set(-3.5,0.048,0); g.add(ln);
    const lb=new THREE.Mesh(markNameGeo,new THREE.MeshBasicMaterial({transparent:true,depthWrite:false}));
    lb.rotation.y=Math.PI; lb.scale.set(0.55,1,0.55); lb.position.set(-(NUMX+NUM_HALF+NUM_GAP/2),0.02,0.75); lb.renderOrder=6;   // 帯とレーン群の隙間に「◆ 名前」バナー（ノーツ/ライトどちらのモードでも同じ位置）
    g.add(lb);
    g.userData={lb,ln}; g.visible=false; scene.add(g); tmPool.push(g);   // ln=床ライン。applyLaneVisがレーン端に合わせて伸縮する
  } }
// ---- ライティングレーン（トラック左側・ChroMapper式のイベント表示） ----
const LIGHT_LANES=[   // 並び順=ヘルバ様指定 2026-07-13（t=Beat Saber実イベント種別ID。並びは表示のみ・データ/PREVIEW/書き出しはet=tで動作）
  {t:9, n:'RING ZOOM'},
  {t:8, n:'RING ROT'},
  {t:4, n:'CENTER'},
  {t:13,n:'R SPEED'},
  {t:3, n:'R LASER'},
  {t:12,n:'L SPEED'},
  {t:2, n:'L LASER'},
  {t:1, n:'RINGS'},
  {t:0, n:'BACK'},
  {t:5, n:'BOOST'},
];
const laneIdxByType={}; LIGHT_LANES.forEach((l,i)=>laneIdxByType[l.t]=i);
// 罫線色はノーツトラックと同じ。拍番号エリアの外側に配置
// LLANE=ライトのレーン幅。ノーツ列幅(LANE)の半分＝広すぎたため（ヘルバ様指定 2026-07-17）。
// 幅に関わる寸法（罫線/床/赤パネル/チップ/ホバー判定）は全てここから導出する＝1箇所で調整できる
const LLANE=LANE/2;
const LCHIP_K=LLANE/LANE;   // 旧レーン幅(LANE)前提で書かれた寸法 → 現レーン幅(LLANE)への倍率。チップ形状と重複枠が共有＝幅を変えても比率が崩れない
// ライト床の手前端は「拍番号帯の外側＋ノーツ側と同じ隙間」に置く＝拍番号を挟んで左右対称（ヘルバ様指定 2026-07-17）。
// 手前端 = LANE_X0 + LLANE/2 + 0.02（0.02 = laneAreaW の余白0.04の半分）なので、そこから LANE_X0 を逆算する。
// LLANE直書きの座標にすると幅を変えるたびに隙間が崩れるため、必ずここから導出すること。
// NUMX / NUM_HALF / NOTE_EDGE / NUM_GAP / LANE_NEAR は floor 生成の直前へ集約済み（NOTE_DX がそれらから導出されるため）
const LANE_DX=-LLANE, LANE_X0=LANE_NEAR-LLANE/2-0.02;
let lightEvents=[];
const lightGroup=new THREE.Group(); scene.add(lightGroup);
const laneTexCache={};
function laneTex(name){ if(laneTexCache[name]) return laneTexCache[name];
  const c=document.createElement('canvas'); c.width=512; c.height=64; const g=c.getContext('2d');
  g.font='bold 38px '+FONT; g.textBaseline='middle'; g.textAlign='center';
  g.fillStyle='#9a9a9a'; g.fillText(name,256,33);
  const t=new THREE.CanvasTexture(c); t.anisotropy=MAXANISO; laneTexCache[name]=t; return t; }
const laneAreaW=Math.abs(LANE_DX)*LIGHT_LANES.length+0.04;
const laneAreaCX=LANE_X0+(LIGHT_LANES.length-1)/2*LANE_DX;
// フロア（ノーツ側と同じ見た目）
const laneFloor=new THREE.Mesh(new THREE.PlaneGeometry(laneAreaW,160),
  new THREE.MeshStandardMaterial({color:0x141414,roughness:.9,polygonOffset:true,polygonOffsetFactor:1,polygonOffsetUnits:2}));
laneFloor.rotation.x=-Math.PI/2; laneFloor.position.set(laneAreaCX,0,20); lightGroup.add(laneFloor);
// レーン罫線（境界線11本・トラックのレーン線と同色）
const laneEdgeLines=[];
for(let i=0;i<=LIGHT_LANES.length;i++){
  const x=LANE_X0+(i-0.5)*LANE_DX;
  const l=new THREE.Mesh(new THREE.BoxGeometry(0.02,0.003,160),new THREE.MeshBasicMaterial({color:0x232323}));
  l.position.set(x,0.01,20); lightGroup.add(l); laneEdgeLines.push(l);
}
// ---- ライティングレーン側の赤パネル（再生ヘッド位置・縦一段分＝ノーツ側の赤枠に相当。ヘルバ様指定） ----
// playFrame の子＝毎フレーム z=(curV-viewB)*ZPB に追従（ノーツ側の赤枠/床線と同じ挙動）。床から1段(LAYER)だけ立てる
let _lRedFrame=null, _lRedFill=null, _lRedDiv=null;   // 赤パネル（枠/塗り/縦仕切り）＝レーン本数の増減で作り直す
{ const lw=laneAreaW, lh=LAYER, lx=laneAreaCX;
  _lRedFrame=new THREE.LineSegments(
    new THREE.EdgesGeometry(new THREE.PlaneGeometry(lw+0.1,lh)),
    new THREE.LineBasicMaterial({color:0xff3344}));
  _lRedFrame.position.set(lx,lh/2,0); pfLight.add(_lRedFrame);
  _lRedFill=new THREE.Mesh(new THREE.PlaneGeometry(lw+0.1,lh),
    new THREE.MeshBasicMaterial({color:0xff3344,transparent:true,opacity:0.10,side:THREE.DoubleSide,depthWrite:false}));
  _lRedFill.position.set(lx,lh/2,0); pfLight.add(_lRedFill);
  // 各レーン境界の縦仕切り（ライト10レーン＝内部9本。ノーツ側の12マス分割と同じ流儀）
  const gp=[]; for(let i=1;i<LIGHT_LANES.length;i++){ const gx=LANE_X0+(i-0.5)*LANE_DX; gp.push(gx,0,0, gx,lh,0); }
  const gg=new THREE.BufferGeometry(); gg.setAttribute('position',new THREE.Float32BufferAttribute(gp,3));
  _lRedDiv=new THREE.LineSegments(gg,new THREE.LineBasicMaterial({color:0xff3344,transparent:true,opacity:0.30}));
  pfLight.add(_lRedDiv); }
const laneNameSprites=[];
LIGHT_LANES.forEach((l,i)=>{
  const x=LANE_X0+i*LANE_DX;
  const sp=new THREE.Sprite(new THREE.SpriteMaterial({map:laneTex(l.n),transparent:true,depthWrite:false}));   // 深度を書かない=背後のチップに穴を開けない
  sp.scale.set(1.15,0.16,1); sp.position.set(x,0.07,-0.7); lightGroup.add(sp); laneNameSprites.push(sp);
});
// レーン用の拍ライン（ノーツ側の拍線と同期して流れる）
const laneBeatPool=[]; for(let i=0;i<96;i++){ const b=new THREE.Mesh(
  new THREE.BoxGeometry(laneAreaW,0.003,0.02),
  new THREE.MeshBasicMaterial({color:0x2a2a2a}));
  b.position.x=laneAreaCX; b.visible=false; lightGroup.add(b); laneBeatPool.push(b); }
// スナップ分割の細線（ノーツ側subPoolと同期して表示）
const laneSubPool=[]; for(let i=0;i<560;i++){ const m=new THREE.Mesh(
  new THREE.BoxGeometry(laneAreaW,0.003,0.012),
  new THREE.MeshBasicMaterial({color:0x1f1f1f}));
  m.position.x=laneAreaCX; m.visible=false; lightGroup.add(m); laneSubPool.push(m); }
// ---- Chromaモード中はBOOSTレーンを隠す（各ライトが自由色を持つのでブースト配色が効かない・ヘルバ様指定 2026-07-17） ----
// BOOSTは LIGHT_LANES の末尾なので「表示本数を1本減らす」だけで済む（途中のレーンを隠す想定は無い）
const BOOST_T=5, BOOST_LANE_IDX=laneIdxByType[BOOST_T];
function visLaneN(){ return (chromaMode&&BOOST_LANE_IDX===LIGHT_LANES.length-1)?LIGHT_LANES.length-1:LIGHT_LANES.length; }
function laneHiddenT(t){ return chromaMode&&t===BOOST_T; }        // そのライト種別が今隠れているか
function lightHiddenEv(ev){ return laneHiddenT(ev&&ev.et); }      // 隠れているライトは選択/範囲選択/ギズモの対象外
// 床の3本ライン（赤=再生ヘッド / 黄=マウス拍 / 白=マーカー）は素の長さ10.8・中心x=-3.5 で作ってある。
// レーン幅やBOOSTの表示切替で端が動くため、毎回ここで伸縮させる（固定値のままだとレーン外へはみ出して余る＝ヘルバ様報告 2026-07-17）
const LINE_GEO_LEN=10.8;                    // 3本の素のジオメトリ長
// ノーツとライトを同じ場所へ重ねた（NOTE_DX）ため、3本ラインの両端も「今表示している側」で決める。
// 手前端=拍番号帯の外側（マーカーバナーの少し先）／外端=表示中のレーン群の外端。
const LINE_X_NEAR=-(NUMX-NUM_HALF)+0.12;    // 帯のノーツ側の端をわずかに越えた位置（帯の下に線が消えない）
function laneFarX(){ const n=visLaneN(); return LANE_X0-LLANE*(2*n-1)/2-0.02; }   // 表示中のライトレーンの外端（0.02=laneAreaWの余白の半分）
function laneAreaFarX(){ return lightMode?laneFarX():(NOTE_DX-NOTE_EDGE); }        // 今表示しているレーン群の外端
function applyLaneVis(){   // 表示レーン数に合わせて床/罫線/赤パネル/拍線/ラベル/3本ラインを作り直さずに寄せる
  const n=visLaneN();
  const w=Math.abs(LANE_DX)*n+0.04, cx=LANE_X0+(n-1)/2*LANE_DX;
  { const x0=laneAreaFarX(), len=LINE_X_NEAR-x0, mid=(x0+LINE_X_NEAR)/2;   // 表示中レーンの外端 → 拍番号帯の手前 まで
    const fit=o=>{ if(!o) return; o.scale.x=len/LINE_GEO_LEN; o.position.x=mid; };
    fit(playFloorLine); fit(mouseLine);
    for(const g of tmPool) fit(g.userData&&g.userData.ln); }
  laneFloor.scale.x=w/laneAreaW; laneFloor.position.x=cx;
  laneEdgeLines.forEach((l,i)=>{ l.visible=(i<=n); });            // 境界線は n+1 本だけ
  if(_lRedFrame){ _lRedFrame.scale.x=(w+0.1)/(laneAreaW+0.1); _lRedFrame.position.x=cx; }
  if(_lRedFill){ _lRedFill.scale.x=(w+0.1)/(laneAreaW+0.1); _lRedFill.position.x=cx; }
  if(_lRedDiv) _lRedDiv.geometry.setDrawRange(0,Math.max(0,(n-1)*2));   // 内部仕切りは n-1 本（頂点2個/本・昇順に並んでいる）
  laneNameSprites.forEach((sp,i)=>{ sp.visible=(i<n); });
  for(const b of laneBeatPool){ b.scale.x=w/laneAreaW; b.position.x=cx; }
  for(const m of laneSubPool){ m.scale.x=w/laneAreaW; m.position.x=cx; }
}
// ---- イベントチップ: ペラペラ板 + Canvasテクスチャ（動作別の見た目 + 強さ数字） ----
function chipKindOf(t,i){ const k=laneKind(t);
  if(k==='trigger') return 'trigger';
  if(k==='speed') return i>0?'speed':'off';
  if(k==='boost') return i?'on':'off';
  if(i===0) return 'off';
  return ['','on','flash','fade','trans'][(i-1)%4+1];
}
function chipColorOf(t,i,chroma,boost){ const k=laneKind(t);
  const CTRL=0xb4b4be, OFF=0x484850;                 // コントロール系(BOOST/SPEED/ZOOM/ROT)=明るめ灰（橙/黄はライト色と紛らわしい）／消灯=暗め灰
  if(k==='trigger') return CTRL;
  if(k==='speed') return i>0?CTRL:OFF;
  if(k==='boost') return i?CTRL:OFF;
  if(i>0&&chroma) return rgb01ToHexInt(chroma);        // クロマ色（カスタムRGB）は通常の赤/青/白より優先（クロマはブースト影響を受けない）
  if(i>=9) return 0xe8f0ff;                            // 白は固定（ブーストでも変わらない）
  if(i>=5) return boost?LRED_B:LRED;                   // その拍がブースト中なら①②をブースト色へ差替（各ライトは自分の位置で判定・ヘルバ様指定 2026-07-13）
  if(i>=1) return boost?LBLUE_B:LBLUE;
  return OFF;                                         // OFF=暗め灰
}
function chipNumOf(t,ev){ const k=laneKind(t);
  if(k==='speed'&&ev.i>0) return ev.i;
  if(k==='color'&&ev.i>0) return Math.round((ev.f??1)*100);
  return null;
}
// 上から見た形（フットプリント）で判別: ON=一枚板 / FLASH=縞 / FADE=三角 / TRANS=ペナント / OFF=低い薄板
// 形はレーン幅方向(x)に描き、奥行き0.10を維持 = 1/16スナップでも重ならない
function chipFootGeo(shapes,h){
  const g=new THREE.ExtrudeGeometry(shapes,{depth:h,bevelEnabled:false});
  g.rotateX(-Math.PI/2); g.rotateY(-Math.PI/2);   // (時間,レーン幅)の形を床に寝かせる
  return g;
}
function chipRect(u0,v0,u1,v1){ const sh=new THREE.Shape();
  sh.moveTo(u0,v0); sh.lineTo(u1,v0); sh.lineTo(u1,v1); sh.lineTo(u0,v1); sh.closePath(); return sh; }
const _flashBars=[];
for(let i=0;i<4;i++){ const v0=-0.25+i*0.138; _flashBars.push(chipRect(-0.05,v0,0.05,v0+0.086)); }
// FADE=直角三角形（片辺が直線・斜辺で先細り） / TRANS=中央で尖る砂時計（▶◀）
const _fadeTri=(()=>{ const sh=new THREE.Shape();
  sh.moveTo(-0.05,-0.25); sh.lineTo(0.05,-0.25); sh.lineTo(-0.05,0.25); sh.closePath(); return sh; })();
const _transBow=(()=>{ const sh=new THREE.Shape();   // 中央が繋がった砂時計（首幅0.02）
  sh.moveTo(-0.05,-0.25); sh.lineTo(0.05,-0.25); sh.lineTo(0.024,0);
  sh.lineTo(0.05,0.25); sh.lineTo(-0.05,0.25); sh.lineTo(-0.024,0);
  sh.closePath(); return sh; })();
const CHIP_GEOS={
  on:   new THREE.BoxGeometry(0.5,0.08,0.10).translate(0,0.04,0),
  off:  new THREE.BoxGeometry(0.5,0.035,0.10).translate(0,0.0175,0),
  flash:chipFootGeo(_flashBars,0.08),
  fade: chipFootGeo([_fadeTri],0.08),
  trans:chipFootGeo([_transBow],0.08),
};
// 形状は「レーン幅0.5」を前提に定義してあるので、実レーン幅(LLANE)に合わせて幅方向(x)だけ縮める。
// レーン内の占有率は従来どおり＝レーン幅を変えてもチップが隣へはみ出さない（aliasを貼る前に1回だけ適用）
for(const n of ['on','off','flash','fade','trans']) CHIP_GEOS[n].scale(LCHIP_K,1,1);
CHIP_GEOS.trigger=CHIP_GEOS.on; CHIP_GEOS.speed=CHIP_GEOS.on;
const CHIP_EDGES={};
function chipEdges(kind){ return CHIP_EDGES[kind]||(CHIP_EDGES[kind]=new THREE.EdgesGeometry(CHIP_GEOS[kind]||CHIP_GEOS.on)); }
// 強さ数字（ビルボード = どの角度からでも読める）
const numSprTexCache={};
function numSprTex(n){
  if(numSprTexCache[n]) return numSprTexCache[n];
  const c=document.createElement('canvas'); c.width=256; c.height=128;   // POTサイズ=ミップマップ有効
  const g=c.getContext('2d');
  g.font='bold 72px '+FONT; g.textAlign='center'; g.textBaseline='middle';
  g.fillStyle='#ffffff';
  g.fillText(String(n),128,66);
  const tx=new THREE.CanvasTexture(c); tx.anisotropy=MAXANISO;
  numSprTexCache[n]=tx; return tx;
}
const chipPool=[];
function ensureChips(n){ while(chipPool.length<n&&chipPool.length<1200){
  const mat=new THREE.MeshStandardMaterial({flatShading:true,metalness:0.1,roughness:0.65,transparent:true});
  const body=new THREE.Mesh(CHIP_GEOS.on,mat);
  const num=new THREE.Sprite(new THREE.SpriteMaterial({transparent:true,depthWrite:false}));
  // 数字はチップの真上に載せる（下端=チップ上面0.08）。高く浮かせると浅い角度で隣レーンの上に見えてどのライトの数字か分からない（ヘルバ様報告 2026-07-17。旧 y=0.34）
  num.scale.set(0.25,0.126,1); num.position.y=0.08+0.126/2;   // 0.36×0.18の0.7倍（大きすぎた・ヘルバ様指定 2026-07-18）。下端=チップ上面0.08に載せる計算は維持
  num.renderOrder=6;   // 拍番号帯(numStrip=5)より後に描く＝灰色バーに数字が沈まない（拍番号numPoolと同じ流儀）
  // 数字のレイキャストは有効なまま＝「クリックの盾」に使う。掴めるのは箱(body)だけで、
  // 数字の上では選択も配置も削除も起こさない（overLightNumRay で完全に不活性化・ヘルバ様指定 2026-07-17）
  const edge=new THREE.LineSegments(chipEdges('on'),
    new THREE.LineBasicMaterial({color:0x56ffc1}));
  edge.visible=false; edge.raycast=()=>{};   // 選択枠も表示専用
  const grp=new THREE.Group(); grp.add(body,num,edge);
  grp.userData={body,num,mat,edge};
  grp.visible=false; lightGroup.add(grp); grp.traverse(c=>c.layers.set(1));
  chipPool.push(grp); } }

// 編集ヘルパ類は正面プレビューに映さない（レイヤー1）
// ---- ライティング編集 ----
let lightMode=false, lightHover=null, lastLightFTime=0;   // lightHover={lane,beat}
let _lastHeadBeat=0;   // 直近フレームの再生ヘッド拍（tickで更新）＝配置色ボックスのブースト判定用（ヘルバ様指定 2026-07-14）
// 選択ツール(lightSelectMode)は廃止（ヘルバ様指定）。常に動作ツール武装＝空きクリック=配置／配置済みライトのクリック=選択／Shift=範囲選択
let _notePlaceSaved=false;   // ライトモード中に退避するノーツ側placeMode（ライト⇄ノーツ切替で配置ツールが選択に戻らないよう復元・ヘルバ様指定 2026-07-13）
let lightMove=null;                                        // G移動 {b0,l0,orig:[{ev,beat,lane}]}
let pvShowNotes=true, pvShowLights=true, pvShowStruct=true, pvShowAmbient=false;   // プレビューの表示トグル（環境ライトは既定OFF）
let lightSelection=new Set();                             // ライトイベントの選択（Shift+ドラッグ）
const lightBrush={behav:1, base:4, f:1, speed:12, chroma:null, _lastChromaHex:null};   // base: 0=青 4=赤 8=白／speed=レーザー回転速度の既定(L/R SPEED共通・ヘルバ様指定 2026-07-14:12)／chroma: '#rrggbb'=クロマ色を重ねる・null=既定（左ノーツ色）
function brushChromaHex(){ return lightBrush.chroma||lightBrush._lastChromaHex||cRED; }   // ライトのクロマ既定=左ノーツ色(cRED)。未ピック時はオレンジではなく左ノーツ色（ヘルバ様指定 2026-07-13）
let _lightPalIdx=-1;   // ライト中Fで保存パレットのクロマ色を巡回する現在位置（ヘルバ様指定 2026-07-13）
let chromaMode=localStorage.getItem('bsnm_chroma')!=='0';   // Chromaモード（既定ON）。ON=各ライト自由色(Mod必要) / OFF=バニラ配色（環境設定で切替・ヘルバ様指定 2026-07-13）
// クロマ色は raw.customData.color（実機Chroma仕様・0-1 float RGB配列）に持たせる＝既存のraw往復(save/.dat import・export)に無改造で乗る
function getLightChroma(ev){ const c=ev&&ev.raw&&ev.raw.customData&&ev.raw.customData.color; return c?c.slice(0,3):null; }
function evChroma(ev){ return chromaMode?getLightChroma(ev):null; }   // 表示用: バニラモード(OFF)では保存クロマを無視してベース色（赤/青/白）で見せる
function setLightChroma(ev,rgbOrNull){
  if(rgbOrNull){ if(!ev.raw) ev.raw={};
    ev.raw.customData={...(ev.raw.customData||{}), color:[...rgbOrNull.map(v=>Math.round(v*1000)/1000),1]}; }
  else if(ev.raw&&ev.raw.customData){ const {color,...rest}=ev.raw.customData;
    if(Object.keys(rest).length) ev.raw.customData=rest; else delete ev.raw.customData;
    if(ev.raw&&!Object.keys(ev.raw).length) ev.raw=null; }
}
function laneKind(t){ return (t===5)?'boost':(t===8||t===9)?'trigger':(t===12||t===13)?'speed':'color'; }
function lightValue(kind){
  if(kind==='color') return lightBrush.behav===0?0:lightBrush.base+lightBrush.behav;
  if(kind==='boost') return lightBrush.behav===0?0:1;
  if(kind==='speed') return lightBrush.speed;
  return 0;
}
const L_BEHAV_N=['オフ','ライト','フラッシュ','フェード','トランジション'];   // 旧 OFF/ON（ヘルバ様指定 2026-07-18）
function lightDesc(kind,i,f,chroma){
  if(kind==='speed') return `速度 ${i}`;
  if(kind==='trigger') return 'トリガー';
  if(kind==='boost') return i?'ブーストON':'ブーストOFF';
  if(i===0) return L_BEHAV_N[0];   // 'オフ'（ボタン/パイの表記と揃える）
  const c=i<=4?'青':i<=8?'赤':'白';
  const chr=chroma?` ★${rgb01ToHex(chroma)}`:'';
  return `${c} ${L_BEHAV_N[(i-1)%4+1]} f=${(f??1).toFixed(2)}${chr}`;
}
const _lgMat=new THREE.MeshStandardMaterial({flatShading:true,metalness:0.1,roughness:0.65,transparent:true,opacity:0.45});   // 配置前ゴースト=フィル＋ワイヤーフレーム（薄すぎ修正 2026-07-14: 0.2→0.45）
const _lgBody=new THREE.Mesh(CHIP_GEOS.on,_lgMat);
const _lgWire=new THREE.LineSegments(chipEdges('on'),new THREE.LineBasicMaterial({color:0x9fe8ff,transparent:true,opacity:0.95}));   // 未配置とわかるワイヤーフレーム
const _lgNum=new THREE.Sprite(new THREE.SpriteMaterial({transparent:true,opacity:0.75,depthWrite:false}));
_lgNum.scale.set(0.25,0.126,1); _lgNum.position.y=0.08+0.126/2; _lgNum.renderOrder=6;   // 配置済みチップの数字と同じ寸法/高さ/描画順＝配置の前後で数字が飛ばない
const lightGhost=new THREE.Group(); lightGhost.add(_lgBody,_lgWire,_lgNum);
lightGhost.visible=false; lightGroup.add(lightGhost);
function setLightMode(on){
  if(lightMode===on) return;
  lightMode=on;
  if(on){ _notePlaceSaved=placeMode; setPlaceMode(false); gizmoMode=null; selection.clear(); }   // ノーツ側の配置ツール状態を退避（ライト中はノーツ配置を消す）
  else { lightHover=null; lightGhost.visible=false; if(_notePlaceSaved) setPlaceMode(true,true); }     // ノーツ復帰時に配置ツールを復元＝切替のたびに選択へ落ちない（ヘルバ様指定 2026-07-13）。keepCam=視点を触らない
  lightSelection.clear(); lightMove=null;
  const row=document.getElementById('lightRow');
  if(row) row.style.outline=on?'2px solid var(--accent)':'none';
  updateMainModeLabel(); applyModeDim(); applyModeVis();   // 非編集側を丸ごと非表示（2026-07-18）
  stat(on?'ライト編集 ON（選択ツール=左で選択 / 動作ツール=左で配置・右で削除 / Alt+ホイール=強さ±10 / 1・2・3=色）':'ライト編集 OFF');
}
function refreshLightHover(){
  lightHover=null;
  if(!lightMode){ lightGhost.visible=false; return; }
  if(overLightNumRay()&&!lightUnder(null)){ lightGhost.visible=false; return; }   // 数字だけの上=不活性（ゴーストも出さない＝置けないことが見て分かる）。箱が有れば盾にしない
  if(raycaster.ray.intersectPlane(floorPlane,_fv)){
    const li=Math.round((LANE_X0-_fv.x)/LLANE);   // レーン幅はLLANE（LANE直書きだと罫線とクリック判定がズレる）
    if(li>=0&&li<visLaneN()&&Math.abs(_fv.x-(LANE_X0-li*LLANE))<=LLANE/2){   // 隠れているレーン(Chroma中のBOOST)には置けない
      const atHead=(camMode==='place');   // 配置モード＝赤パネル(再生ヘッド)の拍に固定・レーンのみマウス追従（ヘルバ様指定 2026-07-13）
      const rawB=atHead?lockBeat:Math.max(0,viewBeat()+_fv.z/ZPB);
      lightHover={lane:li,beat:Math.max(0,snapV(rawB)),raw:rawB};   // beat=配置用（スナップ済）/ raw=選択・削除のヒット判定用（スナップ非依存）
    }
  }
  lightGhost.visible=!!lightHover&&!lightMove&&!hoverLightEvent();   // 既存イベントの上では消す（選択と数字を邪魔しない）
  if(lightGhost.visible){
    const t=LIGHT_LANES[lightHover.lane].t, kind=laneKind(t), iv=lightValue(kind);
    const num=kind==='speed'?(iv>0?iv:null):(kind==='color'&&iv>0?Math.round(lightBrush.f*100):null);
    const gCol=chipColorOf(t,iv,(chromaMode&&kind==='color'&&iv>0)?hexToRgb01(brushChromaHex()):null,boostStateAt(lightHover.beat));   // ゴーストは配置位置のブースト状態で色を出す（バニラモードOFF時はベース色）
    _lgBody.geometry=CHIP_GEOS[chipKindOf(t,iv)]||CHIP_GEOS.on;
    _lgWire.geometry=chipEdges(chipKindOf(t,iv));   // ワイヤーフレームも挙動別ジオメトリに追従
    _lgMat.color.setHex(gCol); _lgMat.emissive.setHex(gCol).multiplyScalar(0.4);
    _lgNum.visible=num!==null;
    if(num!==null) _lgNum.material.map=numSprTex(num);
    lightGhost.position.set(LANE_X0-lightHover.lane*LLANE,0.026,(lightHover.beat-viewBeat())*ZPB);   // レーン幅はLLANE（LANEだとゴーストだけ別レーンに出る）
  }
}
function placeLight(){
  if(!sigConnected('lights')){ stat('⚠ ライティングの配線が切断中です（ノードエディタで再接続してから）'); return; }
  if(inNullRange(lightHover.beat)){ stat('⚠ NULLノードの範囲には配置できません'); return; }
  const ln=LIGHT_LANES[lightHover.lane], b=lightHover.beat, kind=laneKind(ln.t);
  snapshot();
  const i=lightValue(kind), f=kind==='color'?lightBrush.f:1;
  const chroma=(chromaMode&&kind==='color'&&i>0)?hexToRgb01(brushChromaHex()):null;   // クロマ色を付与（バニラモードOFF時はnull＝customData.colorを書かない＝バニラ配色・ヘルバ様指定 2026-07-13）
  const ex=lightEvents.find(ev=>ev.et===ln.t&&Math.abs(ev.beat-b)<1e-4);
  if(ex){ ex.i=i; ex.f=f; setLightChroma(ex,chroma); }
  else { const tr=clipTrackForBeat(b,'l');   // EDIT配置ルールでライトクリップを決定（無→作成／選択優先／一番下／全ロック→上）
    if(tr<0){ stat('⚠ ライトを置けません（ライトレーンが全てロック/最大です）'); return; }
    const nev={beat:b,et:ln.t,i,f,_tr:tr,raw:null};
    if(chroma) setLightChroma(nev,chroma);
    lightEvents.push(nev); lightEvents.sort((a,b2)=>a.beat-b2.beat); }
  gizmoMode=null;   // 置いた直後はギズモを出さない＝連続配置中にハンドルが次のクリックを奪わない（ノーツのplaceAtと同じ流儀）
  stat(tf('msg.lightPlaced','{lane} 拍{beat}: {desc}',{lane:ln.n,beat:b,desc:lightDesc(kind,i,f)}));
}
// マウス直下の実チップを拾う。配置モードでは lightHover が再生ヘッドの拍に固定されるため hoverLightEvent では
// 「見えているチップ」を選べない＝ノーツの objUnder と同じくメッシュを直接レイキャストする（ヘルバ様報告）
function lightUnder(e){
  if(!lightMode) return null;
  // ノーツとライトはワールド座標上で重なっているため、モードで拾う対象を必ず分ける（2026-07-18の表示改修）。
  if(e) setPtr(e); else raycaster.setFromCamera(pointer,camera);
  for(const h of raycaster.intersectObjects(chipPool.filter(c=>c.visible),true)){
    if(h.object.isSprite) continue;   // 数字は掴まない＝選択できるのは箱(body)だけ
    let o=h.object; while(o&&!o.userData.ev) o=o.parent;
    const ev=o&&o.userData.ev; if(!ev) continue;
    if(!lightHiddenEv(ev)&&layerVisible('l',ev._tr||0)&&!objLockedL(ev)) return ev; }
  return null;
}
// 現在のraycasterが、表示中の数字スプライトに当たっているか。当たっていれば選択/配置/削除を一切させない＝
// 数字を踏んで意図しない操作が起きるのを防ぐ（数字が出るのはライトチップだけなので、ここだけの判定で足りる・ヘルバ様指定 2026-07-17）
const _numHit=[];
function overLightNumRay(){
  for(const c of chipPool){ if(!c.visible) continue;
    const n=c.userData&&c.userData.num; if(!n||!n.visible) continue;
    _numHit.length=0; n.raycast(raycaster,_numHit);   // intersectObject経由より軽い（表示中のチップだけを走査）
    if(_numHit.length) return true; }
  return false;
}
function hoverLightEvent(){
  if(!lightHover) return null;
  // 許容誤差はスナップ幅の半分まで＝隣のライトの領域に食い込まない。
  // 旧: tol=0.15 固定だったため 1/8(0.125拍) や 1/16 で並べると隣まで拾い、「間に置けない」「Alt+ホイールで隣の数字まで変わる」
  //     が起きていた（ヘルバ様報告 2026-07-18）。上限0.15は据え置き＝粗いスナップでの掴みやすさは従来どおり
  const t=LIGHT_LANES[lightHover.lane].t, tol=Math.min(0.15,(snap||0.5)/2), hb=lightHover.raw??lightHover.beat;
  let best=null,bd=1e9;
  for(const ev of lightEvents){ if(ev.et!==t||objLockedL(ev)) continue;   // ロック中レーンのライトは触れない
    const d=Math.abs(ev.beat-hb); if(d<bd){ bd=d; best=ev; } }
  return (best&&bd<=tol)?best:null;
}
// ※startLightMove(G=ライトを掴んでマウス追従)は撤去（2026-07-17）。Gの割当は以前に廃止済みで呼び出し元ゼロだった。
//   lightMove 自体はペースト追従（貼り付け直後の位置決め）で現役なので applyLightMove/cancelLightMove は残す
function applyLightMove(){
  if(!lightMove||!lightHover) return;
  const dl=lightHover.lane-lightMove.l0;
  let db=lightHover.beat-lightMove.b0;
  const fits=k=>lightMove.orig.every(o=>{ const nb=o.beat+k;   // 全員が元のボックス範囲内に収まる移動量までクランプ（相対間隔は維持）
    return nb>=-1e-9&&(!o.rng||(nb>=o.rng.b0-1e-6&&nb<o.rng.b1-1e-6)); });
  while(db!==0&&!fits(db)){ db-=Math.sign(db)*Math.min(Math.abs(db),Math.max(snap,1e-3)); if(Math.abs(db)<1e-9) db=0; }
  for(const o of lightMove.orig){
    o.ev.beat=Math.max(0,o.beat+db);
    const nl=Math.min(LIGHT_LANES.length-1,Math.max(0,o.lane+dl));
    o.ev.et=LIGHT_LANES[nl].t;
  }
  lightEvents.sort((a,b)=>a.beat-b.beat);
}
function cancelLightMove(){
  if(!lightMove) return;
  if(lightMove.pasted){   // 貼り付け由来の追従＝位置を戻すのではなく貼り付けた実体ごと消す（ノーツ側 cancelPasteFollow と同じ流儀）
    const gone=new Set(lightMove.pasted);
    lightEvents=lightEvents.filter(ev=>!gone.has(ev));
    for(const ev of gone) lightSelection.delete(ev);
    lightMove=null; _flatDirty=true; metaDirty=true; undoStack.pop();
    stat('貼り付けを取り消しました'); return;
  }
  for(const o of lightMove.orig){ o.ev.beat=o.beat; o.ev.et=LIGHT_LANES[o.lane].t; }
  lightEvents.sort((a,b)=>a.beat-b.beat);
  lightMove=null; undoStack.pop(); stat('ライト移動を取消');   // 直前に積んだ自分のスナップショットを破棄
}
// F: 選択ライトの色フリップ（赤⇄青、白はそのまま）。選択なしはブラシを反転
// 動作キー: 選択中のライトがあれば書き換え、無ければブラシに設定
function setLightBehavSmart(b){
  const sel=[...lightSelection].filter(ev=>laneKind(ev.et)==='color');
  if(sel.length){ snapshot();
    sel.forEach(ev=>{
      if(b===0){ ev.i=0; }
      else{ const base=ev.i>=9?8:ev.i>=5?4:ev.i>=1?0:lightBrush.base; ev.i=base+b; } });
    stat(tf('msg.lightBehavSel','選択ライトを{behav}に変更 ×{n}',{behav:L_BEHAV_N[b],n:sel.length})); }
  else { setLightBehav(b); stat(tf('msg.lightBehav','ライト動作: {behav}',{behav:L_BEHAV_N[b]})); }
}
function flipLightColors(){
  const sel=[...lightSelection].filter(ev=>ev.i>=1&&ev.i<=8);
  if(sel.length){ snapshot();
    sel.forEach(ev=>{ ev.i=ev.i<=4?ev.i+4:ev.i-4; });
    stat(tf('msg.lightColorFlip','ライト色フリップ ×{n}',{n:sel.length})); }
  else { setLightColor(lightBrush.base===4?0:4); stat('ブラシ色フリップ'); }
}
// クロマ（カスタムRGB色）: 選択中のライトがあれば書き換え、無ければブラシへ設定（F=色フリップ等と同じ「選択優先」流儀）
function applyLightChroma(hexOrNull){
  const sel=[...lightSelection].filter(ev=>laneKind(ev.et)==='color');
  const rgb=hexOrNull?hexToRgb01(hexOrNull):null;
  if(sel.length){ snapshot();
    sel.forEach(ev=>setLightChroma(ev,rgb));
    stat(hexOrNull?tf('msg.chromaApplied','クロマ色を適用 ×{n}',{n:sel.length}):tf('msg.chromaCleared','クロマ色を解除 ×{n}',{n:sel.length})); }
  else { lightBrush.chroma=hexOrNull; updateChromaUI();
    stat(hexOrNull?tf('msg.chromaOn','ブラシ: クロマ色 ON（スウォッチで色選択）'):tf('msg.chromaOff','ブラシ: クロマ色 OFF')); }
}
function setBrushChroma(hex){   // ブラシのクロマ色を設定＋色ライトへ即適用（F巡回・Cパイ共通）。適用先=選択中→無ければマウス下のライト（ヘルバ様指定 2026-07-13）
  lightBrush._lastChromaHex=hex; lightBrush.chroma=hex; updateChromaUI();
  let targets=[...lightSelection].filter(ev=>laneKind(ev.et)==='color');
  if(!targets.length){ const hv=hoverLightEvent(); if(hv&&laneKind(hv.et)==='color') targets=[hv]; }   // 選択が無ければマウス下のライトへ
  if(targets.length){ snapshot(); const rgb=hexToRgb01(hex); targets.forEach(ev=>setLightChroma(ev,rgb)); metaDirty=true; }
  stat('クロマ: '+hex+(targets.length?` ×${targets.length}`:''));
}
function lightChromaSeq(){ return [cRED, cBLUE, WHITE_HEX, ...cpSaved()]; }   // 左ノーツ→右ノーツ→白→クロマ登録色（ヘルバ様指定 2026-07-13）
function cycleLightChroma(){   // F(Chroma時)=左ノーツ→右ノーツ→白→クロマ登録色 を巡回
  const seq=lightChromaSeq(); _lightPalIdx=(_lightPalIdx+1)%seq.length; setBrushChroma(seq[_lightPalIdx]);
}
function cycleLightBase(){   // F(バニラ時)=配置色①(赤/base4)→②(青/base0)→白(base8) を巡回＋選択/マウス下の色ライトのiベースも変更（ヘルバ様指定 2026-07-13）
  const order=[4,0,8], nb=order[(order.indexOf(lightBrush.base)+1)%3]; setLightColor(nb);
  let targets=[...lightSelection].filter(ev=>laneKind(ev.et)==='color'&&ev.i>0);
  if(!targets.length){ const hv=hoverLightEvent(); if(hv&&laneKind(hv.et)==='color'&&hv.i>0) targets=[hv]; }
  if(targets.length){ snapshot(); targets.forEach(ev=>{ const behav=((ev.i-1)%4)+1; ev.i=nb+behav; setLightChroma(ev,null); }); metaDirty=true; }   // バニラはクロマ解除してベース色に
  stat('ライト色: '+(nb===4?'①(赤)':nb===0?'②(青)':'白')+(targets.length?` ×${targets.length}`:''));
}
// ライトモードのCパイ（色選択）: 左ノーツ→右ノーツ→クロマ登録色（ヘルバ様指定 2026-07-13）
function lightColorPieDefs(){ const cols=lightChromaSeq(), n=cols.length;
  return cols.map((hex,i)=>({ val:hex, color:hex, angle:i*(360/n), label:(i===0?'左':i===1?'右':'') })); }
function commitLightColorPie(hex){ setBrushChroma(hex); }
function openLightColorPie(){ if(!pieOpen) openPie(lightColorPieDefs(), brushChromaHex(), commitLightColorPie, 'c'); }
// 現在ライティングで配置する色。ツールバーの1個の箱に表示（ヘルバ様指定 2026-07-14）
function lightBaseHex(){   // 素の配置色（ブースト無視・パレットの起点色に使う）
  return lightBrush.base===0?hexOf(LBLUE):lightBrush.base===8?WHITE_HEX:hexOf(LRED);
}
function lightBoostedHex(boost){   // boost=trueなら①②をブースト色へ差替（白・Chromaはブースト非対象＝chipColorOfと同じ規則）
  if(lightBrush.base===8) return WHITE_HEX;
  if(lightBrush.base===0) return boost?hexOf(LBLUE_B):hexOf(LBLUE);
  return boost?hexOf(LRED_B):hexOf(LRED);
}
function currentLightPlaceHex(){   // Chroma=クロマ色 / バニラ=配置位置(ホバー優先・無ければ再生ヘッド)のブースト状態を反映（ヘルバ様指定 2026-07-14）
  if(chromaMode) return brushChromaHex();
  const beat=(lightHover&&isFinite(lightHover.beat))?lightHover.beat:_lastHeadBeat;
  return lightBoostedHex(boostStateAt(beat));
}
function updateChromaUI(){
  const sw=document.getElementById('lcChromaSw');
  if(sw) sw.innerHTML=chromaSwSvg(currentLightPlaceHex());   // 現在の配置色を常に表示
  updateLightColorTB();
}
// ライト色ツールバー（ヘルバ様指定 2026-07-14）: 色の箱は1個だけ＝現在の配置色を表示・クリックでカラーパレット（色の選択/編集はパレット内で行う）
function updateLightColorTB(){
  const sw=document.getElementById('lcChromaSw'), host=document.getElementById('lcColsHost');
  if(sw){ sw.style.display=''; sw.innerHTML=chromaSwSvg(currentLightPlaceHex());
    sw.title=chromaMode?'現在の配置色（クリックでカラーパレット）':'現在の配置色 ①②白（クリックでカラーパレット）'; }
  if(host){ host.innerHTML=''; host.style.display='none'; }   // 5個の箱は廃止＝パレット内で選択（ヘルバ様指定 2026-07-14）
}
function chromaSwSvg(col){ return `<svg viewBox="0 0 64 64"><rect x="3" y="3" width="58" height="58" rx="13" fill="${col}"/></svg>`; }   // 色矩形を大きく＝ノーツ色スウォッチと同等の見た目（ヘルバ様指定 2026-07-13）
let _cpTrigger=null, _cpSuppress=0, _cpSuppressTrig=null;   // カラーピッカーのトグル用（同じスウォッチを再度押したら閉じる・全開き口共通・ヘルバ様指定 2026-07-13）
function pickHexAt(btn,initHex,onCommit){
  const sr=btn.getBoundingClientRect(), nr=ndcv.getBoundingClientRect();
  ndColorEdit(initHex,onCommit,{x:sr.left-nr.left,y:sr.bottom-nr.top,h:0},btn);   // トグル判定はndColorEdit側（第4引数=trigger）
}
function deleteLightAt(){
  const best=hoverLightEvent();
  if(best){ snapshot(); lightEvents=lightEvents.filter(v=>v!==best);
    stat(tf('msg.lightDel','ライト削除: {lane} 拍{beat}',{lane:LIGHT_LANES[lightHover.lane].n,beat:best.beat})); return true; }
  return false;
}
[bgGrid,editGroup,mouseLine,playFrame,lightGroup,...subPool,...beatPool,...numPool,numStrip,specBand,...markerPool,...tmPool].forEach(tagHelper);

// ---- 正面プレビュー用の様式化ライト器具（レイヤー2 = プレビューのみ表示） ----
// モードごとに「編集していない側」を丸ごと隠す（ヘルバ様指定 2026-07-18）。
// 旧仕様は非編集側を減光して残していたが、ノーツとライトは同じ場所に重ねて置くようになったため
// 減光では重なって判別できない＝完全に非表示にする。
// noteRoot / lightGroup / pfNotes / pfLight はいずれも恒等変換のグループなので、
// visible を落としても座標・当たり判定・ギズモの計算には一切影響しない。
// PREVIEW は preview-v4 の別シーンで描いているので、ここで隠してもプレビューには波及しない。
function applyModeVis(){
  noteRoot.visible=!lightMode;
  lightGroup.visible=!!lightMode;
  pfNotes.visible=!lightMode;
  pfLight.visible=!!lightMode;
  applyLaneVis();   // 3本の床ライン（赤/黄/白）を、表示中のレーン群の外端まで伸縮させ直す
}
function applyModeDim(){
  // LIGHTモードでもノーツは減光しない（2026-07-05ヘルバ様指定「previewは基本的にずっと通常。白枠を通過したときだけ光る」）。
  // マテリアルは編集ビューとプレビューで共有のため、減光するとプレビューまで暗くなっていた。
  // 編集中サイドの背景マスを少し明るく（非編集側は従来の暗さ）— これは3D編集の目印なので維持
  // 2026-07-18: 非編集側は丸ごと非表示になったため、モードによる床の明暗切替は不要（見えない側を暗くしていただけ）。
  floor.material.color.setHex(0x2c2c36);
  laneFloor.material.color.setHex(0x2c2c36);
  NOTE_MATS[0].color.setHex(RED);
  NOTE_MATS[1].color.setHex(BLUE);
  NOTE_MATS[0].emissive.setHex(RED);    // 純色に寄せる（従来は暗い0x3a0010で沈んでいた）
  NOTE_MATS[1].emissive.setHex(BLUE);
  NOTE_MATS_HOT[0].color.setHex(RED);   NOTE_MATS_HOT[0].emissive.setHex(RED);   // 白枠（判定面）通過時の発光は従来どおり
  NOTE_MATS_HOT[1].color.setHex(BLUE);  NOTE_MATS_HOT[1].emissive.setHex(BLUE);
  { const DF=0.45;   // LIGHT編集中の編集ビュー用（RED/BLUEを45%に減光＝少し暗く。プレビューには不使用）
    NOTE_MATS_DIM[0].color.setHex(RED).multiplyScalar(DF);   NOTE_MATS_DIM[1].color.setHex(BLUE).multiplyScalar(DF);
    NOTE_MATS_DIM[0].emissive.setHex(RED).multiplyScalar(DF); NOTE_MATS_DIM[1].emissive.setHex(BLUE).multiplyScalar(DF); }
  try{ ghostNoteMats[0].color.setHex(RED); ghostNoteMats[1].color.setHex(BLUE); ghostKey=''; }catch(_){}   // 配置ゴーストのマテリアル(起動時clone)もカスタム色へ追従＝「ゴーストが赤のまま」修正（ヘルバ様報告・初期化中はTDZ→try/catch）
  arrowMatS.opacity=1;
  dotMatS.opacity=1;
  bombMat.color.setHex(0x0c0c0e);
  wallMat.opacity=0.30;
  wallEdgeMat.color.setHex(0xd03060);
  arcMats[0].color.setHex(RED);  arcMats[0].opacity=0.7;   // アークもノーツ色に追従（従来は起動時の既定色で固定＝色バグTODO#8の原因）
  arcMats[1].color.setHex(BLUE); arcMats[1].opacity=0.7;
  laneNameSprites.forEach(sp=>sp.material.opacity=1);   // NOTES中は lightGroup ごと非表示なので減光の出番が無い（2026-07-18）
}
// ---- プレビュー限定の表示トグル（レイヤー切替なので編集ビューには影響しない） ----
function setPvShowNotes(v){ pvShowNotes=v;
  if(pv4On&&_PV4) _PV4.setVisible(pvShowNotes,pvShowLights);   // V2へ反映
  const b=document.getElementById('pvVisNotes'); if(b) b.classList.toggle('on',v); }
function setPvShowLights(v){ pvShowLights=v;
  if(pv4On&&_PV4) _PV4.setVisible(pvShowNotes,pvShowLights);   // V2へ反映
  const b=document.getElementById('pvVisLights'); if(b) b.classList.toggle('on',v); }
function setPvShowStruct(v){ pvShowStruct=v; if(pv4On&&_PV4&&_PV4.setStructVisible) _PV4.setStructVisible(v);   // 構造物トグル(V2)
  const b=document.getElementById('pvVisStruct'); if(b) b.classList.toggle('on',v); }
function setPvShowAmbient(v){ pvShowAmbient=v; if(pv4On&&_PV4&&_PV4.setAmbient) _PV4.setAmbient(v);   // 環境ライト=構造物を明るく（動きを見やすく）
  const b=document.getElementById('pvVisAmbient'); if(b) b.classList.toggle('on',v); }

// ---- 波形データ（下部タイムライン用。1拍=16ビンの高解像度ピーク） ----
function buildWaveData(){
  if(!audioBuf) return;
  const off=getSongOff(), effDur=Math.max(0.5,songDur-off);
  const totalBeats=timeToBeatTM(effDur);
  const bins=Math.max(1024,Math.ceil(totalBeats*16));
  const ch=audioBuf.getChannelData(0), N=ch.length;
  const pk=new Float32Array(bins);
  for(let i=0;i<N;i++){
    const tEff=i/N*songDur-off; if(tEff<0||tEff>=effDur) continue;
    const a=Math.abs(ch[i]), col=Math.min(bins-1,(tEff/effDur*bins)|0);
    if(a>pk[col])pk[col]=a; }
  let maxPk=1e-9; for(let i=0;i<bins;i++){ if(pk[i]>maxPk)maxPk=pk[i]; }
  for(let i=0;i<bins;i++) pk[i]/=maxPk;
  ovWave=pk; ovWaveLen=bins; ovBeats=totalBeats;
  if(specForBuf!==audioBuf){ specForBuf=audioBuf; stat(t('m:スペクトログラム解析中…','スペクトログラム解析中…')); setTimeout(buildSpectroData,0); }   // 音源そのものが変わった時だけ解析（オフセット/無音追加の変更では再解析しない＝生の音声時間軸で持つため無関係）。setTimeoutでstat()の描画を1フレーム挟んでから重い処理へ
}

// ---- スペクトログラム（拍番号帯に重ねる周波数解析。BPMグリッドと実際の音のズレ確認・オンセット視認用） ----
// 生波形の絶対時間軸で1回だけ解析し、オフスクリーンcanvasへ焼き込む（specSrcCanvas）。
// 表示側（3D specBand / 2D specPane）は、現在のウィンドウ分だけこの画像を切り出すだけ＝毎フレームのコストは軽い。
// ※ specBins等の状態変数は3D初期化ブロック（specBandの定義）より前で参照されるため、そちらの直前で宣言する
//   （このモジュールはconst/letのTDZに引っかかると起動直後に画面が真っ暗になる＝2026-09-21に実際に踏んだ不具合）。
function fftInPlace(re,im){   // 反復版Cooley-Tukey（n=2^k専用、in-place）
  const n=re.length;
  for(let i=1,j=0;i<n;i++){
    let bit=n>>1;
    for(;j&bit;bit>>=1) j^=bit;
    j^=bit;
    if(i<j){ let tmp=re[i];re[i]=re[j];re[j]=tmp; tmp=im[i];im[i]=im[j];im[j]=tmp; }
  }
  for(let len=2;len<=n;len<<=1){
    const ang=-2*Math.PI/len, wr=Math.cos(ang), wi=Math.sin(ang);
    for(let i=0;i<n;i+=len){
      let curWr=1, curWi=0;
      for(let k=0;k<len/2;k++){
        const ur=re[i+k], ui=im[i+k];
        const vr=re[i+k+len/2]*curWr-im[i+k+len/2]*curWi;
        const vi=re[i+k+len/2]*curWi+im[i+k+len/2]*curWr;
        re[i+k]=ur+vr; im[i+k]=ui+vi;
        re[i+k+len/2]=ur-vr; im[i+k+len/2]=ui-vi;
        const nWr=curWr*wr-curWi*wi, nWi=curWr*wi+curWi*wr;
        curWr=nWr; curWi=nWi;
      }
    }
  }
}
// 多色相の知覚均等な連続ランプ（黒→紫→赤→橙→白。いわゆるinferno系）。単色ランプだと強弱の差が
// 分かりにくいとのヘルバ様指摘（2026-09-21）で変更。「明るさが単調増加する」性質は保っているので
// dataviz原則のsequential（虹色=非単調とは違い、境界の錯覚が出ない）を満たす。
const SPEC_STOPS=[
  [0.00,  0,  0,  4],
  [0.25, 87, 16,110],
  [0.50,188, 55, 84],
  [0.75,249,142,  8],
  [1.00,252,255,164],
];
const SPEC_GAMMA=1.8;   // 色の割り付けに傾斜を付ける（線形=均等割り付けだと明るい色が広く出過ぎるとのヘルバ様指摘。
                         // 1より大きくすると中間〜弱い成分が暗色側に寄り、強い成分だけが明るい色になる）
function specColor(v){
  v=Math.pow(Math.max(0,Math.min(1,v)),SPEC_GAMMA);
  let i=0; while(i<SPEC_STOPS.length-2&&v>SPEC_STOPS[i+1][0]) i++;
  const s0=SPEC_STOPS[i], s1=SPEC_STOPS[i+1], f=(v-s0[0])/((s1[0]-s0[0])||1);
  return [Math.round(s0[1]+(s1[1]-s0[1])*f), Math.round(s0[2]+(s1[2]-s0[2])*f), Math.round(s0[3]+(s1[3]-s0[3])*f)];
}
function buildSpectroData(){
  specMag=null; specSrcCanvas=null;
  if(!audioBuf) return;
  try{
    const sr=audioBuf.sampleRate, ch=audioBuf.getChannelData(0);
    const fftSize=2048, hop=Math.max(256,Math.round(sr*0.010));   // 10ms刻み・2048点FFT（時間軸の解像度をさらに優先。曲全体を一括解析するため一度だけの重さは許容）
    specHop=hop/sr;
    const cols=Math.max(1,Math.floor((ch.length-fftSize)/hop)+1);
    specCols=cols;
    const win=new Float32Array(fftSize);
    for(let i=0;i<fftSize;i++) win[i]=0.5-0.5*Math.cos(2*Math.PI*i/(fftSize-1));   // Hann窓
    const re=new Float32Array(fftSize), im=new Float32Array(fftSize);
    const mag=new Float32Array(cols*specBins);
    const fLo=40, fHi=Math.min(12000,sr/2), nyq=sr/2, halfN=fftSize/2;
    const binEdge=new Float64Array(specBins+1);
    for(let i=0;i<=specBins;i++) binEdge[i]=fLo*Math.pow(fHi/fLo,i/specBins);   // 対数周波数ビン（低音〜高音を人の聴感に近い間隔で分割）
    for(let c=0;c<cols;c++){
      const start=c*hop;
      for(let i=0;i<fftSize;i++){ re[i]=(ch[start+i]||0)*win[i]; im[i]=0; }
      fftInPlace(re,im);
      for(let b=0;b<specBins;b++){
        const k0=Math.max(1,Math.floor(binEdge[b]/nyq*halfN)), k1=Math.min(halfN-1,Math.ceil(binEdge[b+1]/nyq*halfN));
        let sum=0,n=0;
        for(let k=k0;k<=k1;k++){ sum+=Math.hypot(re[k],im[k]); n++; }
        mag[c*specBins+b]=n?sum/n:0;
      }
    }
    let maxV=1e-6; for(let i=0;i<mag.length;i++) if(mag[i]>maxV) maxV=mag[i];
    for(let i=0;i<mag.length;i++){   // -60dBフロアで0〜1に正規化（生の振幅のまま持つとspecColorのclampでほぼ白黒二値になる）
      const db=20*Math.log10((mag[i]/maxV)+1e-6);
      mag[i]=Math.max(0,Math.min(1,(db+60)/60));
    }
    const cv=document.createElement('canvas'); cv.width=cols; cv.height=specBins;
    const cg=cv.getContext('2d'); const imgd=cg.createImageData(cols,specBins);
    for(let c=0;c<cols;c++){
      for(let b=0;b<specBins;b++){
        const [r,g,bch]=specColor(mag[c*specBins+b]);
        const py=specBins-1-b, idx=(py*cols+c)*4;   // b=0(低域)を画像の下端に=スペクトログラムの慣習通り
        imgd.data[idx]=r; imgd.data[idx+1]=g; imgd.data[idx+2]=bch; imgd.data[idx+3]=255;
      }
    }
    cg.putImageData(imgd,0,0);
    specMag=mag; specSrcCanvas=cv;   // specMagは正規化済み(0〜1)。3D側(updateSpecBand)はこれを直接specColorに渡せる
  }catch(e){ console.warn('スペクトログラム解析に失敗',e); specMag=null; specSrcCanvas=null; }
}
function specTimeRange(b0,b1){   // 拍区間[b0,b1)→生音声の時間軸での列範囲（オフセット/無音追加を含めた実時間）
  const off=getSongOff();
  return [off+beatToTimeTM(b0), off+beatToTimeTM(b1)];
}

// ---- 全体タイムライン + セクションタグ ----
let ovWave=null, ovWaveLen=0, ovBeats=0;
let sections=[];            // {beat,label} 昇順管理
const SEC_COLORS=['#56ffc1','#ffd82d','#ff2d55','#6cf06c','#8160e3','#ff9d3d','#4dc8ff','#ff6da8'];
const ovcv=document.getElementById('ovcv'), ovg=ovcv.getContext('2d');
let ovW=0, ovH=0;
let tlSpan=32;                               // 下段共通の時間窓（拍）: ホイールで拡大縮小
let tlFrozen=null;                           // ドラッグ中は窓を凍結（座標系が動かないように）
let ovWin={b0:0,span:tlSpan};
function ovResize(){ const r=ovcv.getBoundingClientRect();   // 親(#overview)ではなくキャンバス自身の内容幅を測る＝ndcvと同一座標系(幅W-16)。拍→xがndcvと完全一致し再生ヘッド/黄ライン/クリック判定が揃う
  ovW=r.width; ovH=r.height; ovcv.width=ovW*devicePixelRatio; ovcv.height=ovH*devicePixelRatio;
  ovg.setTransform(devicePixelRatio,0,0,devicePixelRatio,0,0); }
// ---- スペクトログラム帯（Musicの波形の下、独立パネル）----
const speccv=document.getElementById('speccv'), specg=speccv.getContext('2d');
let specPaneW=0, specPaneH=0;
function specResize(){ const r=speccv.getBoundingClientRect();
  specPaneW=r.width; specPaneH=r.height; speccv.width=specPaneW*devicePixelRatio; speccv.height=specPaneH*devicePixelRatio;
  specg.setTransform(devicePixelRatio,0,0,devicePixelRatio,0,0); }
function drawSpecPane(curV){   // ovcvと同じ窓(TLGUT基準)で、切り出したスペクトログラムを表示する
  if(!specPaneW) return;
  specg.clearRect(0,0,specPaneW,specPaneH);
  specg.fillStyle='#0c0c0e'; specg.fillRect(0,0,specPaneW,specPaneH);
  const win=tlWindow(curV);
  const x=b=>TLGUT+(b-win.b0)/win.span*(specPaneW-TLGUT);
  if(specSrcCanvas){
    // drawImageは1回につき直線的な拡縮しかできないため、窓内にテンポパートの境界があるとその区間だけ実際の
    // 時間とズレて描画されてしまう（拍→時間が区分的にしか変換できないため）。境界ごとに区切って個別に描く。
    const bEnd=win.b0+win.span;
    const bps=[win.b0,...tempoParts.map(p=>p.beat).filter(b=>b>win.b0+1e-6&&b<bEnd-1e-6).sort((a,b)=>a-b),bEnd];
    for(let i=0;i<bps.length-1;i++){
      const [t0,t1]=specTimeRange(bps[i],bps[i+1]);
      const u0=t0/specHop, u1=t1/specHop;   // クランプ前の列位置（音源の範囲外を含む）
      const cc0=Math.max(0,Math.min(specCols,u0)), cc1=Math.max(0,Math.min(specCols,u1));
      if(cc1<=cc0||u1<=u0) continue;
      const fx0=x(bps[i]), fx1=x(bps[i+1]);
      if(fx1<=fx0) continue;
      // 音源の端を越えた分は描かない。切り詰めた列範囲に比例して描画先も切り詰める（しないと残りが窓幅いっぱいに引き伸ばされる）
      const k=(fx1-fx0)/(u1-u0);
      const dx0=fx0+(cc0-u0)*k, dx1=fx0+(cc1-u0)*k;
      specg.drawImage(specSrcCanvas,cc0,0,cc1-cc0,specBins,dx0,0,dx1-dx0,specPaneH);
    }
  }
  drawMetroLines(specg,speccv,win,x);   // メトロノームON時の拍頭ライン
}
function phRect(ctx,cv,xCss){   // 再生ヘッド本体を必ずデバイスピクセルに乗せてクッキリ2px相当で描く（dpr=1.5等でAA潰れ＝細く見えるのを防止・ndcv/ovcvで同一）
  const dpr=devicePixelRatio, w=Math.max(2,Math.round(2*dpr)), x0=Math.round(xCss*dpr)-(w>>1);
  ctx.save(); ctx.setTransform(1,0,0,1,0,0); ctx.fillStyle='#ff3344'; ctx.fillRect(x0,0,w,cv.height); ctx.restore(); }
function crispVLine(ctx,cv,xCss,col){   // 縦線をデバイスピクセルに乗せてクッキリ全高で描く（黄=マウス拍ライン。赤phRectより細く＝約1px・上端まで・AA潰れ防止）
  const dpr=devicePixelRatio, w=Math.max(1,Math.round(dpr)), x0=Math.round(xCss*dpr)-(w>>1);
  ctx.save(); ctx.setTransform(1,0,0,1,0,0); ctx.fillStyle=col; ctx.fillRect(x0,0,w,cv.height); ctx.restore(); }
function drawMetroLines(ctx,cv,win,xFn){   // メトロノームON時、拍頭(整数拍)に薄い線を重ねて表示（波形/スペクトログラムのレーン共通・ヘルバ様指定 2026-09-21）
  const mn=metroNode(); if(!mn||!mn.data||!mn.data.on) return;
  const b0=Math.ceil(win.b0-1e-6), b1=Math.floor(win.b0+win.span+1e-6);
  for(let b=b0;b<=b1;b++){ const x=xFn(b); if(x>=TLGUT) crispVLine(ctx,cv,x,'rgba(120,220,255,.6)'); }
}
// タイムライン全長 = 最後尾のボックス（Musicセグメント/クリップの遅い方の終端）+4拍
function tlEnd(){
  let e=0;
  for(const sg of msegs()) e=Math.max(e,segEndBeat(sg));
  for(const s of sections) e=Math.max(e,(s.beat||0)+(s.len||4));
  return e+4;
}
let tlViewB0=null;   // Shift+中ドラッグによる手動スクロール位置（beats）。nullなら再生ヘッド追従
let tlB0=0;          // 追従スクロールの左端。ページ送り（右端→左端へ折り返し）は廃止し、連続スクロールで追う
function tlWindow(b){ if(tlFrozen) return tlFrozen;
  if(tlViewB0!=null){
    if(playing&&(b<tlViewB0||b>=tlViewB0+tlSpan)){ tlB0=tlViewB0; tlViewB0=null; }   // 窓外へ出たら現在窓から連続で追従へ
    else return {b0:tlViewB0,span:tlSpan};
  }
  if(playing){ const mg=Math.min(4,tlSpan*0.3);   // 追従スクロールは再生中のみ（クリック/シークで窓は動かさない＝動かすのは使用者）
    if(b>tlB0+tlSpan-mg) tlB0=Math.max(0,b-(tlSpan-mg));
    else if(b<tlB0+mg) tlB0=Math.max(0,b-mg); }
  return {b0:tlB0,span:tlSpan}; }
function tlZoom(e){ e.preventDefault();
  if(e.shiftKey&&!e.ctrlKey&&!e.altKey&&!e.metaKey){ tlScrub(e); return; }   // Shift+ホイール=スクラブ / 素のホイール=タイムラインズーム
  if(e.ctrlKey||e.altKey||e.metaKey||e.shiftKey) return;   // 未設定の修飾+ホイールは無効（ズームは素のホイールのみ）
  const maxSpan=Math.max(32,Math.ceil(tlEnd()));   // タイムライン全長（最後尾ボックス+4拍、最低8小節）より広くは縮小できない
  const cv=e.currentTarget, rect=cv.getBoundingClientRect();   // ndcv/ovcv どちらでもマウス支点で拡大縮小（支点の拍がその場に留まる＝編集箇所が逃げない）
  const GUT=128, W=rect.width||1, mx=e.clientX-rect.left, frac=(mx-GUT)/Math.max(1,W-GUT);
  const w0=tlWindow(cur), pivotBeat=w0.b0+Math.max(0,Math.min(1,frac))*w0.span;   // マウス下の拍（支点）
  tlSpan=Math.max(4,Math.min(maxSpan,tlSpan*(e.deltaY>0?1.25:0.8)));
  if(mx>=GUT&&frac<=1) tlViewB0=Math.max(0,pivotBeat-frac*tlSpan);   // 支点の拍がマウス位置に留まるよう窓をスクロール
  if(tlFrozen) tlFrozen=null; }
ovcv.addEventListener('wheel',tlZoom,{passive:false});
const TLGUT=128;   // 左溝幅（S/MボタンとBPMステッパーが入る幅）。レイヤービューのLGUTと同値にして支点の縦線を一直線に揃える
const beatToX=b=>TLGUT+(b-ovWin.b0)/ovWin.span*(ovW-TLGUT);
const xToBeat=x=>ovWin.b0+(x-TLGUT)/(ovW-TLGUT)*ovWin.span;
function drawOverview(curV){
  if(!ovW) return;
  ovg.clearRect(0,0,ovW,ovH);
  const w=tlWindow(curV); ovWin=w;
  // 拍グリッド（4拍ごと。未読込でもNLEと揃った縦線を出す）
  ovg.strokeStyle='rgba(255,255,255,.08)';
  for(let b=Math.ceil(ovWin.b0/4)*4;b<ovWin.b0+ovWin.span;b+=4){ const x=beatToX(b); if(x<TLGUT) continue;
    ovg.beginPath(); ovg.moveTo(x,0); ovg.lineTo(x,ovH); ovg.stroke(); }
  // 左溝: Musicラベル（Layerと同じ上付き）＋BPMステッパー（−/値/＋。値ダブルクリックで直接入力）
  const drawOvGutter=()=>{
    ovg.fillStyle='#212121'; ovg.fillRect(0,0,TLGUT,ovH);
    ovg.strokeStyle='#161616'; ovg.lineWidth=1; ovg.beginPath(); ovg.moveTo(TLGUT,0); ovg.lineTo(TLGUT,ovH); ovg.stroke();
    ovg.fillStyle='#9a9a9a'; ovg.font='bold 10px '+FONT; ovg.textAlign='left'; ovg.textBaseline='middle';
    ovg.fillText('Music',8,13);
    // BPM・メトロ・プレビュー秒は難易度バーとルーラーの間の帯 #musicBar（HTML）へ集約（2026-07-08ヘルバ様指示）
  };
  // MEDIAドラッグ中のゴースト（音源のドロップ位置プレビュー）
  const drawOvGhost=()=>{ if(!_dragMedia||_mediaGhostOv==null) return;
    const gb=Math.max(0,snapV(xToBeat(_mediaGhostOv)));
    if(_dragMedia.isClip||_dragMedia.isImage){   // クリップ/画像はMusicレーンに置けない→赤い不可ゴースト（画像1と同じ様式・ヘルバ様指定 2026-07-14）
      const x0=beatToX(gb), gw2=Math.max(160,Math.min(ovW-x0-4,300));
      const msg=_dragMedia.isImage?t('msg.imgToCoverShort','画像はカバー画像へ')
        :(_dragMedia.clipType==='light'?t('msg.clipToLight','LIGHTクリップは LIGHT レーンへ'):t('msg.clipToNotes','NOTESクリップは NOTES レーンへ'));
      ovg.save(); ovg.beginPath(); ovg.roundRect(x0,1,gw2,ovH-2,6); ovg.clip();
      ovg.fillStyle='rgba(226,96,91,.10)'; ovg.fillRect(x0,1,gw2,ovH-2);
      ovg.fillStyle='#e2605b'; ovg.textBaseline='middle'; ovg.textAlign='left';
      ovg.font='bold 13px '+FONT; const qw=ovg.measureText('？').width;
      ovg.font='bold 10px '+FONT; const mw=ovg.measureText(msg).width;
      const tx=x0+Math.max(8,(gw2-(qw+5+mw))/2), cy=ovH/2;
      ovg.font='bold 13px '+FONT; ovg.fillText('？',tx,cy);
      ovg.font='bold 10px '+FONT; ovg.fillText(msg,tx+qw+5,cy);
      ovg.restore();
      ovg.setLineDash([5,4]); ovg.strokeStyle='#e2605b'; ovg.lineWidth=1.5;
      ovg.beginPath(); ovg.roundRect(x0,1,gw2,ovH-2,6); ovg.stroke(); ovg.setLineDash([]);
      return; }
    const gBpm=+((_dragMedia.info||{})._beatsPerMinute)||BPM;   // ドロップでBPMも曲側に切り替わるため、ゴーストは曲のBPMで実長を計算（120のままズレる問題の修正）
    const durB=_dragMedia._durSec?(_dragMedia._durSec*gBpm/60):32;   // デコード済みなら実長・未了はプレースホルダー
    const x0=beatToX(gb), x1=beatToX(gb+durB), gw2=Math.max(26,x1-x0);
    ovg.save(); ovg.beginPath(); ovg.roundRect(x0,1,gw2,ovH-2,6); ovg.clip();
    ovg.fillStyle='rgba(46,143,143,.16)'; ovg.fillRect(x0,1,gw2,ovH-2);
    if(_dragMedia._peaks){                                           // 実波形（先読みピーク）
      const pk=_dragMedia._peaks, hdr=13, mid=(ovH+hdr)/2, amp=(ovH-hdr)/2*0.82;
      ovg.fillStyle='rgba(150,160,175,.45)';
      const xe=Math.min(ovW,x0+gw2);
      for(let px2=Math.max(TLGUT,Math.ceil(x0));px2<xe;px2++){ const p=(px2-x0)/(x1-x0);
        if(p<0||p>=1) continue;
        const v=pk[Math.min(pk.length-1,(p*pk.length)|0)];
        const h2=Math.max(1,Math.pow(v,0.8)*amp); ovg.fillRect(px2,mid-h2,1,h2*2); } }
    ovg.fillStyle='#d8f0f0'; ovg.font='bold 10px '+FONT; ovg.textAlign='left'; ovg.textBaseline='middle';
    ovg.fillText('♪ '+(_dragMedia.name||''),x0+7,9);
    ovg.restore();
    ovg.setLineDash([5,4]); ovg.strokeStyle='#2e8f8f'; ovg.lineWidth=1.5;
    ovg.beginPath(); ovg.roundRect(x0,1,gw2,ovH-2,6); ovg.stroke(); ovg.setLineDash([]); };
  if(!ovBeats){ ovcv.style.cursor='';   // 空状態: ボタン表示・クリック読み込みとも廃止（ヘルバ様指示）
    drawOvGhost();
    for(const m of markers){ const mx2=beatToX(m.beat);   // マーカーの白ライン（空状態でも表示）
      if(mx2>=TLGUT){ ovg.strokeStyle='rgba(255,255,255,.4)'; ovg.lineWidth=1;
        ovg.beginPath(); ovg.moveTo(mx2+0.5,0); ovg.lineTo(mx2+0.5,ovH); ovg.stroke(); } }
    drawOvGutter();
    // 黄(マウス拍)→赤(再生ヘッド)の順で最後に描く＝赤が最前面（ndcvと重なり順を統一。同位置で下だけ黄が上に来る不整合を解消）
    { const thb=(camMode==='place')?null:(tlHoverBeat??hoverBeat); if(thb!=null){ const hx2=beatToX(thb); if(hx2>=TLGUT) crispVLine(ovg,ovcv,hx2,'rgba(255,216,45,.85)'); } }   // 配置モードは黄ライン非表示（ヘルバ様指定）
    { const px=beatToX(curV); if(px>=TLGUT) phRect(ovg,ovcv,px); }
    return; }
  ovcv.style.cursor=musicDrag?'grabbing':_ovEdgeHover?'ew-resize':_ovClipHover?'grab':'';   // 端=ew-resize／クリップ本体=掌／ドラッグ中=グー（ノーツ/ライトと同じ）
  // （旧セクション帯は削除: クリップ範囲はNLEレイヤービュー側で表示。Musicレーンは音源クリップ専用）
  // Music クリップ（セグメント対応: Cカットの各区間を個別ボックス表示。ヘッダー掴みで移動・本体クリックで選択）
  _musicBoxes.length=0;
  if(ovWave&&sigConnected('audio')){
    const effD=Math.max(0.001,songDur-getSongOff());
    msegs().forEach((sg,i)=>{
      const segBeats=segBeatsOf(sg);
      const bx0=beatToX(sg.beat), bx1=beatToX(sg.beat+segBeats);
      const cx0=Math.max(TLGUT,bx0), cx1=Math.min(ovW,bx1), hdr=13;
      if(cx1<=cx0) return;
      _musicBoxes.push({i,cx0,cx1,hdr});
      const seld=musicSelSet.has(i);
      // 角丸は実位置（px0/px1）で描き、溝より左は後から描く左溝が覆う＝NLEのボックスと同じ「下に潜り込む」見え方
      const px0=Math.max(TLGUT-24,bx0), px1=Math.min(ovW+24,bx1);
      const mbPath=()=>{ ovg.beginPath(); ovg.roundRect(px0+0.5,0.5,px1-px0-1,ovH-1,6); };   // レイヤークリップと同じ角丸6px
      ovg.save(); mbPath(); ovg.clip();                                                  // 地・波形・ヘッダーを角丸内に収める
      ovg.fillStyle='rgba(46,143,143,.08)'; ovg.fillRect(px0,0,px1-px0,ovH);            // 透明ティールの地（テーマaudio_strip #2e8f8f）
      const mid=(ovH+hdr)/2, amp=(ovH-hdr)/2*0.82;                                        // 波形（グレー・ヘッダー下、音源内オフセット対応）
      ovg.fillStyle='rgba(150,160,175,.55)';
      for(let x=Math.max(TLGUT,Math.ceil(bx0));x<cx1;x++){ const rb=xToBeat(x)-sg.beat;
        if(rb<0||rb>=segBeats) continue;
        const p=(sg.off+(beatToTimeTM(sg.beat+rb)-beatToTimeTM(sg.beat)))/effD;
        if(p<0||p>=1) continue;   // 音源の範囲外=無音（トリムで伸ばした部分は波形なし）
        const v=ovWave[Math.min(ovWaveLen-1,(p*ovWaveLen)|0)];
        const h=Math.max(1,Math.pow(v,0.8)*amp); ovg.fillRect(x,mid-h,1,h*2); }
      ovg.fillStyle=seld?'rgba(46,143,143,.60)':'rgba(46,143,143,.32)'; ovg.fillRect(px0,0,px1-px0,hdr);   // ラベルヘッダー
      ovg.fillStyle='#d8f0f0'; ovg.font='bold 10px '+FONT; ovg.textAlign='left'; ovg.textBaseline='middle';
      ovg.fillText('♪ '+((songNode&&songNode.name)||'Music'),bx0+7,hdr/2+0.5);
      ovg.restore();
      ovg.lineWidth=seld?2.4:1; ovg.strokeStyle=seld?'#ff8f0d':'rgba(46,143,143,.7)';   // 枠（選択=テーマselected_strip）
      mbPath(); ovg.stroke();
    });
  }
  drawOvGhost();
  // マーカーの白ライン（NLE側からMusicの下端まで連続して見えるように）
  for(const m of markers){ const mx2=beatToX(m.beat);
    if(mx2>=TLGUT){ ovg.strokeStyle='rgba(255,255,255,.4)'; ovg.lineWidth=1;
      ovg.beginPath(); ovg.moveTo(mx2+0.5,0); ovg.lineTo(mx2+0.5,ovH); ovg.stroke(); } }
  drawMetroLines(ovg,ovcv,ovWin,beatToX);   // メトロノームON時の拍頭ライン
  // 左溝（支点をレイヤービューのLGUTと揃える）→ 先に描く
  drawOvGutter();
  // 黄(マウス拍)→赤(再生ヘッド)の順で最後に描く＝赤が最前面（ndcvと重なり順を統一）
  { const thb=tlHoverBeat??hoverBeat; if(thb!=null){ const hx2=beatToX(thb); if(hx2>=TLGUT) crispVLine(ovg,ovcv,hx2,'rgba(255,216,45,.85)'); } }
  { const px=beatToX(curV); if(px>=TLGUT) phRect(ovg,ovcv,px); }
}
// 音レーン: ドラッグ=シーク
let markers=[], _mkSeq=0;   // タイムラインマーカー {beat,name}（全難易度共通・白固定）。Mで挿入・ダブルクリックで改名（空=削除）
const _mkRects=[];          // マーカー帯のラベル当たり判定（drawLayersで毎フレーム更新）
const _tpRects=[];          // テンポパート帯の当たり判定（drawLayersで毎フレーム更新）
// ---- テンポパート境界の追加/削除/自動判定 ----
function addTempoPartAt(b,{snap:doSnap=true}={}){ b=Math.max(0.25,doSnap?snapV(b??cur):(b??cur));
  if(tempoParts.some(p=>Math.abs(p.beat-b)<1e-6)){ stat('この位置には既にテンポパートがあります'); return; }
  snapshot('node');
  tempoParts.push({beat:b,bpm:bpmAtBeat(b)}); sortTempoParts();   // 追加直後は現在地のテンポを引き継ぐ＝作成時に音が飛ばない
  metaDirty=true; stat(tf('msg.tempoPartAdd','テンポパートを追加: 拍 {beat}（右クリックで自動判定/手入力/削除）',{beat:b}));
}
function addTempoPartAtSec(sec){   // 秒指定はグリッドスナップを介さず正確な拍位置へ変換する（目的が「正確な時刻指定」のため）
  if(isNaN(sec)||sec<0){ stat('秒数を正しく入力してください'); return; }
  const b=timeToBeatTM(sec); addTempoPartAt(b,{snap:false});
}
function setTempoPartBpm(idx,bpm){ if(!tempoParts[idx]||!(bpm>0)) return;
  snapshot('node'); tempoParts[idx].bpm=Math.round(bpm*100)/100; metaDirty=true;
  stat(tf('msg.tempoPartBpm','テンポパート（拍{beat}）のBPM: {bpm}',{beat:tempoParts[idx].beat,bpm:tempoParts[idx].bpm}));
}
function delTempoPart(idx){ if(!tempoParts[idx]) return;
  snapshot('node'); tempoParts.splice(idx,1); metaDirty=true; stat(tf('msg.tempoPartDel','テンポパートを削除しました'));
}
function tempoPartRangeSec(idx){   // idx番目のテンポパートが対象とする生音声上の時間範囲[t0,t1)
  const off=getSongOff();
  const b0=tempoParts[idx].beat, b1=(idx+1<tempoParts.length)?tempoParts[idx+1].beat:timeToBeatTM(songDur-off);
  return [off+beatToTimeTM(b0), off+beatToTimeTM(Math.max(b0+0.01,b1))];
}
function autoDetectTempoPart(idx){
  if(!audioBuf||!tempoParts[idx]) return;
  const [t0,t1]=tempoPartRangeSec(idx);
  try{
    const r=estimateBPM(t0,t1);
    tempoParts[idx].bpm=r.cands[0].bpm; metaDirty=true;
    stat(tf('msg.tempoPartDetect','テンポパート（拍{beat}）を自動判定: BPM {bpm}（一致度 {conf}%）',{beat:tempoParts[idx].beat,bpm:r.cands[0].bpm.toFixed(2),conf:r.cands[0].conf}));
  }catch(err){ showErr(tf('msg.bpmAnalyzeFail','BPM解析に失敗: {err}',{err:err.message})); }
}
function autoDetectAllTempoParts(){
  if(!audioBuf){ showErr('先に曲を読み込んでください'); return; }
  if(!tempoParts.length){ stat('テンポパートがありません（テンポ帯を右クリックで追加）'); return; }
  snapshot('node');
  let ok=0;
  for(let i=0;i<tempoParts.length;i++){
    const [t0,t1]=tempoPartRangeSec(i);
    try{ const r=estimateBPM(t0,t1); tempoParts[i].bpm=r.cands[0].bpm; ok++; }catch(_){}
  }
  metaDirty=true; stat(tf('msg.tempoPartDetectAll','全パートを自動判定しました（{n}/{total}件）',{n:ok,total:tempoParts.length}));
}
function addMarkerAt(b){ b=Math.max(0,snapV(b??cur));
  if(markers.some(m=>Math.abs(m.beat-b)<1e-6)){ stat('この位置には既にマーカーがあります'); return; }
  snapshot('node');   // マーカー作成をUndo可能に
  markers.push({beat:b,name:'マーカー'+(++_mkSeq)}); markers.sort((a,b2)=>a.beat-b2.beat);
  metaDirty=true; stat(tf('msg.markerAdd','マーカー追加: 拍 {beat}（名前はダブルクリックで変更・空にすると削除）',{beat:b})); }
function markerMenuTop(){   // どのトラックの右クリックメニューでも先頭に置く「現在ポジション(再生ヘッド)にマーカー作成」＋区切り線
  return [[t('ctx.addMarkerHere','マーカーを作成'),()=>addMarkerAt(cur)],['---']]; }
let ovPan=null;    // Musicレーンの中ドラッグ=表示窓の移動
let musicBeat=0, musicDrag=null, musicSegs=null, musicSelSet=new Set();   // Musicクリップ。musicSegs=Cカットの分割区間{beat,off,dur}[]（null=未分割）。選択はクリップと同じ複数選択
let musicResize=null;   // Music端トリム {i,side,origBeat,origOff,origDur}。off/durは音源への窓=縮小は非破壊・範囲外は無音
let _ovEdgeHover=false, _ovClipHover=false; // Musicセグメント端ホバー（ew-resize）／クリップ本体ホバー（grab）
const _musicBoxes=[];   // 画面上のセグメント箱（drawOverviewで毎フレーム更新）
const _EMPTY_SEGS=[]; let _msegCache=null, _msegKey='';
function msegs(){ if(musicSegs) return musicSegs;
  if(!audioBuf) return _EMPTY_SEGS;
  const k=musicBeat+':'+songDur+':'+getSongOff();   // 毎フレーム呼ばれるためキャッシュ（GC負荷の予防）
  if(k!==_msegKey){ _msegKey=k; _msegCache=[{beat:musicBeat, off:0, dur:Math.max(0,songDur-getSongOff())}]; }
  return _msegCache; }   // 未分割=全体1セグメント（off=有効音声内の開始秒）
function cutMusicAt(b){   // 選択中のMusicセグメントを拍bでカット（NLEのCと同じ流儀）
  const A=msegs().map(s=>({...s})); if(!A.length) return false;
  const inSeg=j=>{ const sg=A[j]; return sg&&b>sg.beat+1e-4&&b<segEndBeat(sg)-1e-4; };
  const i=[...musicSelSet].find(inSeg);   // Cは「選択したボックスのみ」対象（未選択のMusicは絶対に切らない）
  if(i===undefined) return false;
  snapshot('node');
  const sg=A[i], cutSec=beatToTimeTM(b)-beatToTimeTM(sg.beat);
  A.splice(i,1,{...sg,dur:cutSec},{beat:b,off:sg.off+cutSec,dur:sg.dur-cutSec});
  musicSegs=A; musicSelSet=new Set(); layerSel=new Set();   // カット後は全選択解除
  metaDirty=true; stat('Musicをカットしました'); return true;
}
function mergeMusicSel(){   // 選択中のMusicセグメントを結合（M。タイムライン隣接かつ音源内も連続のみ=無劣化で1本に戻せる場合）
  if(!musicSegs||musicSelSet.size<2){ stat('結合するにはMusicセグメントを2つ以上選択してください'); return; }
  const selIdx=new Set(musicSelSet);
  const sel=[...selIdx].map(j=>musicSegs[j]).filter(Boolean).sort((a,b)=>a.beat-b.beat);
  const mergedSegs=[]; let runBase=null, did=false;
  for(const sg of sel){
    if(runBase&&Math.abs(segEndBeat(runBase)-sg.beat)<1e-3&&Math.abs((runBase.off+runBase.dur)-sg.off)<1e-3){
      runBase.dur+=sg.dur; did=true; }
    else { runBase={...sg}; mergedSegs.push(runBase); }
  }
  if(!did){ stat('E: タイムラインと音源の両方で連続しているセグメントだけ結合できます'); return; }
  snapshot('node');
  const rest=musicSegs.filter((s,j)=>!selIdx.has(j));
  musicSegs=[...rest,...mergedSegs].sort((a,b)=>a.beat-b.beat);
  if(musicSegs.length===1&&Math.abs(musicSegs[0].off)<1e-6){ musicBeat=musicSegs[0].beat; musicSegs=null; }   // 完全に1本へ戻ったら未分割状態に
  musicSelSet=new Set(); metaDirty=true; stat('Musicセグメントを結合しました');
}
function musicHit(sx,sy){ for(const b of _musicBoxes){ if(sx>=b.cx0&&sx<=b.cx1) return {i:b.i,part:sy<=b.hdr?'header':'body'}; } return null; }
ovcv.addEventListener('pointerdown', e=>{
  selWatch('node');   // Musicセグメント選択の変化も1動作として履歴へ
  const r=ovcv.getBoundingClientRect(), sx=e.clientX-r.left, sy=e.clientY-r.top;
  if(e.button===1&&!e.ctrlKey&&!e.altKey&&!e.metaKey){ e.preventDefault();   // パン=中ドラッグ（素/Shift併用可・Ctrl/Alt/Metaは無効。2D画面は素の中ボタンでスクロール）
    ovPan={sx,startB0:tlWindow(cur).b0};
    try{ovcv.setPointerCapture(e.pointerId);}catch(_){} return; }
  if(e.button!==0) return;
  if(sx<TLGUT) return;                       // 左溝（BPMフィールドはNLEヘッダー右端へ移設済み）
  if(!ovBeats) return;   // 空タイムライン=クリックしても何もしない（ファイル→音楽ファイルを読み込む…／MEDIAから。ヘルバ様指示）
  { let eh=null;                             // セグメント端±4px=トリムハンドル
    for(const b of _musicBoxes){ if(Math.abs(sx-b.cx0)<=4){ eh={i:b.i,side:'l'}; break; } if(Math.abs(sx-b.cx1)<=4){ eh={i:b.i,side:'r'}; break; } }
    if(eh){ const pre=dumpDomain('node');   // 履歴は確定時に「実際に変化した場合だけ」積む
      if(!musicSegs) musicSegs=msegs().map(s=>({...s}));   // 未分割ならセグメント化してから
      const sg=musicSegs[eh.i];
      musicResize={i:eh.i,side:eh.side,origBeat:sg.beat,origOff:sg.off,origDur:sg.dur,pre};
      tlFrozen=tlWindow(cur);
      try{ovcv.setPointerCapture(e.pointerId);}catch(_){} return; } }
  const hit=musicHit(sx,sy);
  if(hit){                                   // 選択はクリップと同じ流儀（Shift=追加/解除・複数選択可）
    if(e.shiftKey){ musicSelSet.has(hit.i)?musicSelSet.delete(hit.i):musicSelSet.add(hit.i); }   // Shift=追加（レイヤー選択は維持＝同時選択）
    else if(!musicSelSet.has(hit.i)){ musicSelSet=new Set([hit.i]); layerSel=new Set(); }   // 単独クリック=このsongのみ（レイヤー選択も解除）。既選択の掴み直しはグループ維持
    tlFrozen=tlWindow(cur);                  // 本体/ヘッダーどちらを掴んでもドラッグ開始（ノーツ/ライトのクリップと同じ）
    musicDrag={i:hit.i,sx,starts:msegs().map(s=>s.beat)};
    try{ovcv.setPointerCapture(e.pointerId);}catch(_){}
    return; }
  if(!e.shiftKey){ musicSelSet=new Set(); layerSel=new Set(); }     // 空クリック=全選択解除（song/レイヤー両方。シークはNLE上部のルーラーのみ）
});
addEventListener('pointermove', e=>{
  if(ovPan){ const r=ovcv.getBoundingClientRect(), sx=e.clientX-r.left, ppb=(ovW-TLGUT)/tlWindow(cur).span;
    tlViewB0=Math.max(0,ovPan.startB0-(sx-ovPan.sx)/ppb); return; }
  if(musicResize){ const r=ovcv.getBoundingClientRect(), sx=e.clientX-r.left;
    const sg=musicSegs&&musicSegs[musicResize.i]; if(!sg) return;
    const mn=Math.max(snap,0.25);
    let tb=Math.max(0,snapV(xToBeat(sx)));
    if(musicResize.side==='r'){
      const lenBeats=Math.max(mn,tb-sg.beat);
      sg.dur=beatToTimeTM(sg.beat+lenBeats)-beatToTimeTM(sg.beat);   // 右へ伸ばす=音源末尾を越えたぶんは無音／縮める=窓が狭まるだけで内容保持
    } else {
      tb=Math.min(tb,segEndBeat({beat:musicResize.origBeat,dur:musicResize.origDur})-mn);
      const d=tb-musicResize.origBeat, dSec=beatToTimeTM(musicResize.origBeat+d)-beatToTimeTM(musicResize.origBeat);
      sg.beat=tb; sg.off=musicResize.origOff+dSec; sg.dur=musicResize.origDur-dSec;   // offは負も可=先頭無音
    }
    metaDirty=true; return; }
  if(musicDrag){ const r=ovcv.getBoundingClientRect(), sx=e.clientX-r.left, w=tlWindow(cur), ppb=(ovW-TLGUT)/w.span;
    if(!musicDrag.moved){ snapshot('node'); musicDrag.moved=true; }   // Music移動もUndo対象に（未記録だとCtrl+Zで位置が巻き戻ったまま保存される事故が起きる）
    let nb=snapV(musicDrag.starts[musicDrag.i]+(sx-musicDrag.sx)/ppb);   // 移動は常にスナップ幅（Shiftスムーズ移動は廃止）。0クランプはグループ単位で下記
    let d=nb-musicDrag.starts[musicDrag.i];                         // 掴んだセグメント基準の移動量を選択全体へ
    // 0拍より左はグループ全体で停止＝先頭が0に達したら止める（旧: 個別クランプで2個目以降が0に重なる不具合）
    { let minB=Infinity;
      if(musicSegs){ for(const j of musicSelSet) if(musicSegs[j]) minB=Math.min(minB,musicDrag.starts[j]??0); }
      else minB=musicDrag.starts[0]??0;
      if(layerSel.size) for(const x of sections) if(layerSel.has(x.id)) minB=Math.min(minB,x.beat||0);   // 同時選択のクリップも含めて止める
      if(minB!==Infinity&&minB+d<0) d=-minB; }
    if(layerSel.size){                                             // songと同時選択したレイヤークリップも同じ拍だけ連動
      const grabPrev=musicSegs?((musicSegs[musicDrag.i]||{}).beat||0):musicBeat;
      const dInc=(musicDrag.starts[musicDrag.i]+d)-grabPrev;
      if(dInc&&!shiftSelLayersBeat(dInc)) return;                  // 重なるならこのステップは不適用（音楽も動かさず同期維持）
    }
    if(musicSegs){ for(const j of musicSelSet) if(musicSegs[j]) musicSegs[j].beat=musicDrag.starts[j]+d; }
    else musicBeat=musicDrag.starts[0]+d;
    metaDirty=true; return; }
});
addEventListener('pointerup', ()=>{ const _mDragged=musicDrag&&musicDrag.moved; ovPan=null; musicDrag=null;
  if(_mDragged&&layerSel.size) compileLayersToFlat();   // songと連動して動かしたレイヤークリップを確定（3D/出力へ反映）
  if(musicResize){ const sg=musicSegs&&musicSegs[musicResize.i];
    const changed=sg&&(Math.abs(sg.beat-musicResize.origBeat)>1e-9||Math.abs(sg.dur-musicResize.origDur)>1e-9||Math.abs(sg.off-musicResize.origOff)>1e-9);
    if(changed){ pushHist('node',musicResize.pre);
      stat('Musicをトリムしました'); }
    musicResize=null; }
  if(!prSeek) tlFrozen=null; });
// Music（音源）はノート/ライト群と独立して削除可能: Musicレーンを右クリック
function deleteMusic(){
  if(!audioBuf&&!songNode){ stat('削除するMusic（音源）がありません'); return; }
  if(playing) pause();
  graphEdges=graphEdges.filter(e2=>e2.sig!=='audio');   // 音源配線も掃除（あれば）
  songNode=null; songDeleted=true;                       // ensureGraphIOの自動復活を止める
  audioBuf=null; ovWave=null; ovWaveLen=0; ovBeats=0; cur=0; offset=0; musicSegs=null; musicSelSet=new Set(); musicBeat=0;
  specMag=null; specSrcCanvas=null; specForBuf=null;
  metaDirty=true; stat('Music（音源）を削除しました（Musicレーンをクリックで再読み込み）');
}
function createFullSongClip(lk){   // 曲の全幅クリップを lk レーンの「一番下(Layer1)の空きトラック」に作成→section。空き無しならnull
  const segs=msegs(); if(!segs.length) return null;
  const start=Math.max(0,Math.min(...segs.map(s=>s.beat||0)));
  const end=Math.max(...segs.map(s=>segEndBeat({beat:s.beat||0,dur:s.dur||0})));
  const len=Math.max(0.25, end-start);
  const N=laneCountOf(lk);
  for(let tr=N-1;tr>=0;tr--){ if(laneOverlaps(start,len,lk,tr)) continue;   // Layer1(一番下)→上へ・最初の空き段に挿入
    const sec={id:'n'+(++_nid)+Math.random().toString(36).slice(2,6),beat:start,track:tr,lk,col:pickStripCol(),label:'Sheet',len,kind:'sheet',content:{}};
    sections.push(sec); relinkDiffEdges(); return sec; }
  return null;
}
ovcv.addEventListener('contextmenu', e=>{ e.preventDefault();   // Musicクリップ右クリック=メニュー（NLEボックスと同じ様式）
  const r=ovcv.getBoundingClientRect(), sx=e.clientX-r.left, sy=e.clientY-r.top;
  if(!audioBuf){   // 空のMusicトラック: PC内から曲を読み込む
    showMenu(e.clientX,e.clientY,[
      ...markerMenuTop(),
      [t('ctx.loadSong','曲を読み込む…'),()=>openSongFile()],
    ]);
    return; }
  const hit=musicHit(sx,sy); if(!hit) return;
  showMenu(e.clientX,e.clientY,[
    [t('ctx.fullClipNL','曲の幅のノーツ＆ライトクリップを作成'),()=>{
      snapshot('node');
      const a=createFullSongClip('n'), b=createFullSongClip('l');
      if(!a&&!b){ undoStack.pop(); showErr('ノーツ/ライトとも空きトラックがありません'); return; }
      layerSel=new Set([...(a?[a.id]:[]),...(b?[b.id]:[])]);
      compileLayersToFlat(); metaDirty=true; stat('曲の幅のノーツ＆ライトクリップを作成しました'); }],
    ['---'],
    [t('ctx.fullClipN','曲の幅のノーツクリップを作成'),()=>{
      snapshot('node'); const s=createFullSongClip('n');
      if(!s){ undoStack.pop(); showErr('ノーツレーンに空きトラックがありません'); return; }
      layerSel=new Set([s.id]); compileLayersToFlat(); metaDirty=true; stat('曲の幅のノーツクリップを作成しました'); }],
    [t('ctx.fullClipL','曲の幅のライトクリップを作成'),()=>{
      snapshot('node'); const s=createFullSongClip('l');
      if(!s){ undoStack.pop(); showErr('ライトレーンに空きトラックがありません'); return; }
      layerSel=new Set([s.id]); compileLayersToFlat(); metaDirty=true; stat('曲の幅のライトクリップを作成しました'); }],
    ['---'],
    [t('ctx.delClip','クリップを削除'),()=>{
      if(musicSegs){ snapshot('node');
        musicSegs=musicSegs.filter((_,j)=>j!==hit.i);
        if(!musicSegs.length){ musicSegs=null; deleteMusic(); }
        else { metaDirty=true; stat('Musicセグメントを削除しました'); }
        musicSelSet=new Set(); }
      else deleteMusic(); }],
  ]);
});

// ---- セクション旗の操作: ピアノロール上部のラベル帯で行う ----
const PR_TAG_H=14;   // ピアノロール上部のラベル帯の高さ
let tgDrag=null;
function secAtPr(x){
  const w=tlWindow(cur), bx=b=>TLGUT+(b-w.b0)/w.span*(prW-TLGUT);
  for(const t of timelineSections()){ if(Math.abs(bx(t.b0)-x)<7) return t.sec; } return null;
}
addEventListener('pointermove', e=>{
  if(!tgDrag) return;
  const r=prcv.getBoundingClientRect(), x=e.clientX-r.left;
  const w=tlWindow(cur);
  tgDrag.sec.beat=Math.max(0,snapV(w.b0+(x-TLGUT)/(prW-TLGUT)*w.span));
  sections.sort((a,b)=>a.beat-b.beat); metaDirty=true;
});
addEventListener('pointerup', ()=>{ if(tgDrag){ tgDrag=null; if(!prSeek) tlFrozen=null; } });
// M = 再生ヘッド位置にマーカーを打って分割
function addMarker(){
  if(!ovBeats){ stat('M: 曲を読み込んでから'); return; }
  const b=snapV(cur);
  ensureEdges();
  const pn=sigPath('notes'), pl=sigPath('lights');
  const seg=pn.segs.find(g=>b>g.start+1e-6&&b<g.end-1e-6)
        ||pl.segs.find(g=>b>g.start+1e-6&&b<g.end-1e-6);
  if(!seg){ stat('M: この拍を含む接続済みノードがありません'); return; }
  graphOp(()=>{
    const owner=seg.sec, rel=b-seg.start;
    const nu={ id:'n'+(++_nid)+Math.random().toString(36).slice(2,6),
      beat:b, label:'マーカー'+(sections.length+1),
      nx:owner.nx+ND_W+56, ny:owner.ny, len:owner.len-rel, content:{} };
    const oc=owner.content||{}, nc=nu.content;
    const split=(key,bk)=>{ const keep=[], move=[];
      (oc[key]||[]).forEach(o=>{ const t=bk?o.b:o.beat;
        if(t>=rel-1e-6){ const o2={...o}; if(bk){ o2.b-=rel; o2.tb-=rel; } else o2.beat-=rel; move.push(o2); }
        else keep.push(o); });
      oc[key]=keep; nc[key]=move; };
    split('notes');split('bombs');split('walls');split('lights');split('arcs',true);split('chains',true);
    owner.len=rel;
    sections.push(nu);
    for(const sig of ['notes','lights']){                 // owner→X を owner→nu→X に
      const outE=graphEdges.find(e=>e.sig===sig&&e.fromId===owner.id);
      if(outE){ outE.fromId=nu.id; graphEdges.push({fromId:owner.id,toId:nu.id,sig}); }
    }
  });
  stat(tf('msg.markerSplit','マーカー追加: 拍 {beat} でノードを分割（名前はピアノロール上部の旗をダブルクリックで変更）',{beat:b}));
}
ovcv.addEventListener('contextmenu',e=>e.preventDefault());
// ---- ノード編集ペイン（セクションタグ → 自動ノード化。骨格版） ----
const ndcv=document.getElementById('ndcv'), ndg=ndcv.getContext('2d');
let ndW=0, ndH=0;
let ndCam={x:0,y:0,scale:1};                 // パン/ズーム
let ndView='layers';                         // 既定=レイヤー表示（ノードは引退。設定移設が済むまで一時的にトグルで到達可）
let ndDrag=null;                             // {sec} | 'pan'
const ND_W=170, ND_H=96;
function ndResize(){ const r=ndcv.getBoundingClientRect();   // 上端インセットぶんを含めず実キャンバスサイズを計測
  ndW=r.width; ndH=r.height; ndcv.width=ndW*devicePixelRatio; ndcv.height=ndH*devicePixelRatio;
  ndg.setTransform(devicePixelRatio,0,0,devicePixelRatio,0,0); }
function ndToScreen(x,y){ return [(x-ndCam.x)*ndCam.scale,(y-ndCam.y)*ndCam.scale]; }
function ndFromScreen(sx,sy){ return [sx/ndCam.scale+ndCam.x, sy/ndCam.scale+ndCam.y]; }
// ---- ノードグラフ M1: Input/Output + 直列チェーン ----
const SIGNALS=[['notes','#4dc8ff',0.42],['lights','#ffd82d',0.62],['audio','#ff9d3d',0.82]];
const IOW=150, IOH=84;
let graphIO=null;   // {in:{nx,ny}, out:{nx,ny}} プロジェクトに保存
let cutSet=new Set();   // はがした配線。キー="下流ノードid|信号"（'out'=OUTPUTノード）
let _nid=0;
function ensureNodeIds(){ for(const s of sections){ if(!s.id) s.id='n'+(++_nid)+Math.random().toString(36).slice(2,6); } }
// ==== 自由配線（エッジ明示・経路走査） ====
let graphEdges=[];        // {fromId,toId,sig}  fromId:'in'|ノードid  toId:ノードid|'out'
let wireDrag=null;        // 配線ドラッグ中 {sig,side,nodeId}
let _ndMouse=[0,0];       // ノード画面上のマウス（ワールド座標）
function ensureLens(){
  const ordered=[...sections].sort((a,b)=>a.beat-b.beat);
  ordered.forEach((s2,i)=>{ if(!(s2.len>0)){
    const end=i+1<ordered.length?ordered[i+1].beat:Math.max(ovBeats||s2.beat+4,s2.beat+4);
    s2.len=Math.max(0.25,end-s2.beat); } });
}
let edgesInited=false;   // 初期配線はプロジェクト読込時の一度だけ（外した線が勝手に蘇生しないように）
function ensureEdges(){
  ensureNodeIds(); ensureLens();
  if(!sections.length||edgesInited) return;
  edgesInited=true;
  const ordered=[...sections].sort((a,b)=>a.beat-b.beat);
  for(const sig of ['notes','lights']){
    let prev='in';
    for(const s2 of ordered){
      if(!cutSet.has(s2.id+'|'+sig)) graphEdges.push({fromId:prev,toId:s2.id,sig});
      prev=s2.id;
    }
    if(!cutSet.has('out|'+sig)) graphEdges.push({fromId:prev,toId:'out',sig});
  }
  cutSet.clear();
  if(!graphEdges.some(e=>e.sig==='audio'))
    graphEdges.push({fromId:'in',toId:'song',sig:'audio'},{fromId:'song',toId:'out',sig:'audio'});
}
// 信号の経路（INPUTから配線を辿る）。segs=[{sec,start,end}], reachOut=OUTPUT到達
function sigPath(sig){
  const eOut={}; for(const e of graphEdges){ if(e.sig===sig){ (eOut[e.fromId]||(eOut[e.fromId]=[])).push(e.toId); } }
  const byId={}; for(const s2 of sections) byId[s2.id]=s2;
  const pick=from=>{ const outs=eOut[from]; if(!outs) return undefined;
    const sec=outs.find(t=>byId[t]); if(sec!==undefined) return sec;   // 直列(Sheet)を優先
    if(outs.includes('out')) return 'out';                             // 末端: アクティブOUTPUT
    return outs[0]; };
  const segs=[], seen=new Set(); let cur='in', off=0, reach=false;
  for(let guard=0;guard<999;guard++){
    const nxt=pick(cur);
    if(nxt===undefined) break;
    if(nxt==='out'){ reach=true; break; }
    if(seen.has(nxt)) break;                    // 循環ガード
    seen.add(nxt);
    const sec=byId[nxt]; if(!sec) break;
    segs.push({sec,start:off,end:off+(sec.len||1)});
    off+=(sec.len||1); cur=nxt;
  }
  return {segs,reachOut:reach};
}
function sigConnected(sig){
  if(sig==='audio'){
    return !!audioBuf && !songDeleted;   // Musicはノート/ライト群と完全独立。音源が読込済みなら接続扱い（グラフ配線に依存しない）
  }
  ensureEdges(); return sigPath(sig).reachOut;
}
// フラット配列 → 経路上の各ノードへスライス（OUTPUT未到達の信号は凍結）
function syncGraphFromFlat(){
  if(ndView==='layers') return;   // レイヤーモードでは section.content が真実（チェーン順の再スライスで壊さない）
  ensureEdges();
  const inR=(b,b0,b1)=>b>=b0-1e-6&&b<b1-1e-6;
  for(const s2 of sections) s2.content=s2.content||{};
  { const p=sigPath('notes');
    if(p.reachOut) for(const g of p.segs){ if(g.sec.kind==='null') continue;
      const c=g.sec.content, b0=g.start, b1=g.end;
      c.notes =notes .filter(n=>inR(n.beat,b0,b1)).map(n=>({...n,beat:n.beat-b0}));
      c.bombs =bombs .filter(n=>inR(n.beat,b0,b1)).map(n=>({...n,beat:n.beat-b0}));
      c.walls =walls .filter(o=>inR(o.beat,b0,b1)).map(o=>({...o,beat:o.beat-b0}));
      c.arcs  =arcs  .filter(a=>inR(a.b,b0,b1)).map(a=>({...a,b:a.b-b0,tb:a.tb-b0}));
      c.chains=chains.filter(cc=>inR(cc.b,b0,b1)).map(cc=>({...cc,b:cc.b-b0,tb:cc.tb-b0})); } }
  { const p=sigPath('lights');
    if(p.reachOut) for(const g of p.segs){ if(g.sec.kind==='null') continue;
      const b0=g.start, b1=g.end;
      g.sec.content.lights=lightEvents.filter(ev=>inR(ev.beat,b0,b1)).map(ev=>({...ev,beat:ev.beat-b0})); } }
}
// ノード所有コンテンツ → フラット配列（接続順に連結。到達しない信号は空）
function compileGraphToFlat(){
  ensureEdges();
  notes=[];bombs=[];walls=[];arcs=[];chains=[]; lightEvents=[];
  const pn=sigPath('notes'), pl=sigPath('lights');
  if(pn.reachOut) for(const g of pn.segs){ const c=g.sec.content||{}, L=g.sec.len;
    (c.notes ||[]).forEach(n=>{ if(n.beat<L) notes .push({...n,beat:n.beat+g.start}); });
    (c.bombs ||[]).forEach(n=>{ if(n.beat<L) bombs .push({...n,beat:n.beat+g.start}); });
    (c.walls ||[]).forEach(o=>{ if(o.beat<L) walls .push({...o,beat:o.beat+g.start}); });
    (c.arcs  ||[]).forEach(a=>{ if(a.b<L) arcs  .push({...a,b:a.b+g.start,tb:a.tb+g.start}); });
    (c.chains||[]).forEach(cc=>{ if(cc.b<L) chains.push({...cc,b:cc.b+g.start,tb:cc.tb+g.start}); });
  }
  if(pl.reachOut) for(const g of pl.segs){ const L=g.sec.len;
    ((g.sec.content||{}).lights||[]).forEach(ev=>{ if(ev.beat<L) lightEvents.push({...ev,beat:ev.beat+g.start}); }); }
  lightEvents.sort((a,b)=>a.beat-b.beat);
  // 表示上のノード拍位置: ノーツ経路優先、次にライト経路
  const placed=new Set();
  for(const g of pn.segs){ g.sec.beat=g.start; placed.add(g.sec.id); }
  for(const g of pl.segs){ if(!placed.has(g.sec.id)) g.sec.beat=g.start; }
  applyInfoChain();
  selection.clear(); lightSelection.clear(); gizmoMode=null;
  rebuild();
}
function graphOp(fn){ snapshot('node'); syncGraphFromFlat(); fn();
  // レイヤーモードは位置(section.beat)が真実。旧compileGraphToFlatはチェーン順でbeatを上書きし、
  // 手動移動したクリップの隙間を詰めてしまう（load/undoでは既に廃止済み）。layers時は位置基準で再合成する。
  (ndView==='layers'?compileLayersToFlat:compileGraphToFlat)();
  metaDirty=true; }
const SIG_NAME={notes:'ノーツ',lights:'ライティング',audio:'音源',info:'Info',cover:'カバー'};
const SIGC={notes:'#4dc8ff',lights:'#ffd82d',audio:'#ff9d3d',info:'#9a9a9a',cover:'#c07dff'};
// ---- 追加ノード（info/infoplus/cover/env） ----
const ENW=200, ENH=66;
let extraNodes=[];   // {id,kind,nx,ny,data:{},name?,handle?}
const EN_DEF={
  info:    {title:'INFO',      col:'#9a9a9a', sig:'info'},
  infoplus:{title:'INFO PLUS', col:'#8a8a8a', sig:'info'},
  env:     {title:'ENVIRONMENT',col:'#9a9a9a', sig:'info'},
  cover:   {title:'COVER',     col:'#c07dff', sig:'cover'},
  metro:   {title:'METRONOME', col:'#ffd24d', sig:'lights'},   // エディタ専用ユーティリティ（書き出しには影響しない・配線なし）
};
function createExtra(kind,wx,wy){
  const d={};
  if(kind==='info'&&infoBase){ for(const k of ['_songName','_songSubName','_songAuthorName','_levelAuthorName']) d[k]=infoBase[k]??''; }
  if(kind==='infoplus'&&infoBase){ for(const k of ['_shuffle','_shufflePeriod','_previewStartTime','_previewDuration']) d[k]=infoBase[k]??''; }
  if(kind==='env') d._environmentName=(infoBase&&infoBase._environmentName)||'DefaultEnvironment';
  if(kind==='metro') d.on=1;
  const n={id:'x'+(++_nid)+Math.random().toString(36).slice(2,6),kind,nx:wx,ny:wy,data:d,name:''};
  extraNodes.push(n);
  metaDirty=true;
  return n;
}
// info系チェーン（OUTPUTから灰配線を遡る。遠い方から順に上書き）
function infoChain(){
  const eIn={}; for(const e of graphEdges){ if(e.sig==='info') eIn[e.toId]=e.fromId; }
  const chain=[]; let cur='out'; const seen=new Set();
  while(eIn[cur]&&!seen.has(eIn[cur])){
    cur=eIn[cur]; seen.add(cur);
    const n=extraNodes.find(x=>x.id===cur); if(!n) break;
    chain.unshift(n);
  }
  return chain;
}
function applyInfoChain(){
  if(!infoBase) return;
  infoJson={...infoBase};
  if(typeof refreshMusicHdr==='function') refreshMusicHdr();   // プレビュー秒の表示を最新infoBaseへ同期
  // 旧INFOノードチェーンの合成は廃止（INFOノードエディタ=applyInfoGraphがinfoBaseへ確定情報を書く方式。
  // 旧チェーンの自動生成ノードが空文字でinfoBaseを上書きし、曲名が消えるバグの根絶）
}
// NULLレンジ判定（中身を持てないスペーサー）
function inNullRange(b){
  return timelineSections().some(t=>t.sec.kind==='null'&&b>=t.b0-1e-6&&b<t.b1-1e-6);
}
// タイムライン表示用: 接続経路上のノードだけを {sec,b0,b1} で返す（切断ノードは帯を出さない）
function timelineSections(){
  if(!sections.length) return [];
  ensureEdges();
  const out=[], seen=new Set();
  const pn=sigPath('notes');
  if(pn.reachOut) for(const g of pn.segs){ out.push({sec:g.sec,b0:g.start,b1:g.end}); seen.add(g.sec.id); }
  const pl=sigPath('lights');
  if(pl.reachOut) for(const g of pl.segs){ if(!seen.has(g.sec.id)) out.push({sec:g.sec,b0:g.start,b1:g.end}); }
  out.sort((a,b)=>a.b0-b.b0);
  return out;
}
// ---- 統一ノードレイアウト（ComfyUI風: ヘッダー + ラベル付きポート行 + コンテンツ） ----
const NHEAD=20, NROWH=17, NPADT=5;
function nodeRowsFor(id){
  if(id==='in'||id.startsWith('in@'))
    return [{sig:'notes',out:1,label:'notes'},{sig:'lights',out:1,label:'lights'},{sig:'audio',out:1,label:'music'}];
  if(id==='out'||id.startsWith('out@'))
    return [{sig:'info',inp:1,label:'info'},{sig:'notes',inp:1,label:'notes'},{sig:'lights',inp:1,label:'lights'},
                         {sig:'audio',inp:1,label:'music'},{sig:'cover',inp:1,label:'cover'}];
  if(id==='song'||id.startsWith('song@'))
    return [{sig:'audio',inp:1,out:1,label:'music'}];
  const ex=extraNodes.find(x=>x.id===id);
  if(ex){ if(ex.kind==='metro') return [];     // メトロノームは配線なし（存在するだけで機能）
    const sig=EN_DEF[ex.kind].sig;
    return [{sig,out:1,label:sig}]; }          // INFO系は出力のみ（INFO同士のチェーンは不可）
  return [{sig:'notes',inp:1,out:1,label:'notes'},{sig:'lights',inp:1,out:1,label:'lights'}];
}
function nodeExtraH(id){
  if(id.startsWith('in@')||id.startsWith('out@')||id.startsWith('song@')) return 34;
  if(id==='in') return 106;
  if(id==='out') return 134;
  if(id==='song') return 156;   // ラベル+欄34 / オフセット・プレビュー3行(26×3) / BPM推定20 / 余白
  const ex=extraNodes.find(x=>x.id===id);
  if(ex){
    if(ex.kind==='cover'){ const c=_coverImgs.get(ex.id);
      return 34+(c&&c.bmp?Math.round(((ex.w||ENW)-16)*c.bmp.height/c.bmp.width)+20:0); }
    if(ex.kind==='metro') return 44;
    return (EN_FIELDS[ex.kind]||[]).length*22+10; }
  { const sec=sections.find(x=>x.id===id);
    if(sec&&sec._diffCounts){ return 22+5*13+6; } }   // 5難易度を常に表示
  return 36;   // sheet
}
function nodeGeomOf(id){
  let w=ENW, base;   // デフォルト幅は全ノードINFOと同じ(ENW)。右下ドラッグでnode.wが入れば個別に上書き
  if(id==='in'||id==='out'){ if(!graphIO) return null; base=graphIO[id]; }
  else if(id==='song'){ if(!songNode) return null; base=songNode; }
  else if(id.startsWith('in@')){ base=altIns.find(n=>'in@'+n.uid===id); if(!base) return null; }
  else if(id.startsWith('out@')){ base=altOuts.find(n=>'out@'+n.uid===id); if(!base) return null; }
  else if(id.startsWith('song@')){ base=altSongs.find(n=>'song@'+n.uid===id); if(!base) return null; }
  else { const ex=extraNodes.find(x=>x.id===id);
    if(ex){ base=ex; }
    else { const sec=sections.find(x=>x.id===id); if(!sec) return null; base=sec; } }
  if(base.w) w=base.w;                                  // 右下ドラッグで変更した幅
  const rows=nodeRowsFor(id);
  return {nx:base.nx,ny:base.ny,w,h:NHEAD+NPADT+rows.length*NROWH+nodeExtraH(id),rows,base};
}
function portPosW(id,sig,side){
  const g=nodeGeomOf(id); if(!g) return null;
  const i=g.rows.findIndex(r=>r.sig===sig&&(side==='out'?r.out:r.inp));
  if(i<0) return null;
  return [side==='out'?g.nx+g.w:g.nx, g.ny+NHEAD+NPADT+i*NROWH+NROWH*0.5];
}
function getSongOff(){ return (songNode&&isFinite(songNode.offset))?songNode.offset:0; }
let _ndWidgets=[];   // ノード上のクリック可能ウィジェット（描画のたびに再構築）
let _pickOpen=null;  // ダイアログを開いている📁のキー（描画で📂に変わる）
let ndSel=null;      // 選択中ノードのid（左クリックで選択・ハイライト、X/Delで削除）
let ndMultiSel=new Set();  // 範囲選択されたノードid（Shift+左ドラッグ。掴んで一括移動・X/Delで一括削除）
let ndBoxSel=null;         // 範囲選択ドラッグ中の矩形 {x0,y0,x1,y1}（スクリーン座標）
function allNodeIds(){
  const ids=['in','out']; if(songNode) ids.push('song');
  for(const sec of sections) ids.push(sec.id);
  for(const ex of extraNodes) ids.push(ex.id);
  for(const n of altIns) ids.push('in@'+n.uid);
  for(const n of altOuts) ids.push('out@'+n.uid);
  for(const n of altSongs) ids.push('song@'+n.uid);
  return ids;
}
// ---- Blender式カラーピッカー ----
function hsv2rgb(h,s2,v){ const f=(n2)=>{ const k=(n2+h/60)%6;
  return v-v*s2*Math.max(0,Math.min(k,4-k,1)); };
  return [f(5),f(3),f(1)]; }
function rgb2hsv(r2,g2,b2){ const mx=Math.max(r2,g2,b2), mn=Math.min(r2,g2,b2), d=mx-mn;
  let h=0; if(d>0){ h=mx===r2?((g2-b2)/d)%6:mx===g2?(b2-r2)/d+2:(r2-g2)/d+4; h=(h*60+360)%360; }
  return [h, mx?d/mx:0, mx]; }
const hx2=n2=>Math.round(Math.max(0,Math.min(1,n2))*255).toString(16).padStart(2,'0');
// ※色履歴(cpHistory/pushCpHistory・bsnm_cphist)は履歴パレット廃止に伴い撤去（監査 2026-07-14）
let _cpal=[];   // ライトのクロマ保存パレット＝プロジェクト(.nlmf)ごとに保存。localStorageには残さない＝新規ファイルは空（ヘルバ様指定 2026-07-13）
function cpSaved(){ return _cpal.slice(); }
function setCpSaved(a){ _cpal=(a||[]).slice(0,48); metaDirty=true; }   // 保存パレット変更＝プロジェクトをdirty化
function ndColorEdit(val,onCommit,wd,trigger){
  if(trigger&&trigger===_cpSuppressTrig&&performance.now()-_cpSuppress<400){ _cpSuppress=0; _cpSuppressTrig=null; return; }   // 同じスウォッチ再クリックで閉じた直後の再オープンを抑止＝トグルで閉じる（ヘルバ様指定）
  const old=document.getElementById('cpanel'); if(old) old.remove();
  _cpTrigger=trigger||null;
  const st={h:0,s:0,v:0.9,a:1,
    wheel:'linear',   // リニア固定（知覚的トグルは廃止）
    tab:localStorage.getItem('bsnm_cpt')||'hsv'};
  if(/^#[0-9a-fA-F]{6}/.test(val)){ const r2=parseInt(val.slice(1,3),16)/255,
      g2=parseInt(val.slice(3,5),16)/255, b2=parseInt(val.slice(5,7),16)/255;
    [st.h,st.s,st.v]=rgb2hsv(r2,g2,b2); }
  const TGT={   // 編集ターゲット（スウォッチ選択→円/数値で直接ライブ編集）。キー→現在色get と 反映set（ヘルバ様指定 2026-07-13）
    note0:{get:()=>cRED, set:h=>setNoteColorHex(0,h)}, note1:{get:()=>cBLUE, set:h=>setNoteColorHex(1,h)},
    light0:{get:()=>hexOf(LRED), set:h=>setLightColorHex(0,h)}, light1:{get:()=>hexOf(LBLUE), set:h=>setLightColorHex(1,h)},
    boost0:{get:()=>hexOf(LRED_B), set:h=>setLightBoostHex(0,h)}, boost1:{get:()=>hexOf(LBLUE_B), set:h=>setLightBoostHex(1,h)} };
  let activeTgt=null;   // null=元(onCommit) / それ以外=TGTのキー
  const commit=()=>{ const [r2,g2,b2]=hsv2rgb(st.h,st.s,st.v); const hex='#'+hx2(r2)+hx2(g2)+hx2(b2);
    if(activeTgt&&TGT[activeTgt]){ TGT[activeTgt].set(hex);
      const sw=pn.querySelector('.cpNoteBar[data-tgt="'+activeTgt+'"]'); if(sw) sw.style.background=hex; }   // 選択中の色を直接変更＋スウォッチ即更新
    else onCommit(hex); };
  // ---- パネル ----
  const pn=document.createElement('div'); pn.id='cpanel';
  const WS=148, BW=16;   // 一回り小さく（ヘルバ様指定 2026-07-13）
  const _nIco=(typeof TB_ICONS!=='undefined'&&TB_ICONS.note)||'♪', _lIco=(typeof TB_ICONS!=='undefined'&&TB_ICONS.light_on)||'💡', _bIco=(typeof TB_ICONS!=='undefined'&&TB_ICONS.light_boost)||'💡';
  const _row=(ico,tip,cols)=>`<div class="cpColRow"><span class="cpRowIco" title="${tip}">${ico}</span><div class="cpCols" data-cols="${cols}"></div></div>`;
  const _notesRow=_row(_nIco,'ノーツの色（左=赤 / 右=青・クリックで選択→円で編集）','note');
  // Chroma版=ノーツ色＋Chromaパレット / バニラ版=ノーツ色＋ライト色＋ライトブースト色（ヘルバ様指定 2026-07-13）
  const _bottom = chromaMode
    ? _notesRow+`<div class="cpLightHdr" title="${t('cp.lightPal','ノーツ①②・白＋登録クロマ色（ライト中Fで巡回）')}">${_lIco}<span>${t('cp.lightPalL','Chroma パレット')}</span><span class="cpHint">${t('cp.palHint','右クリックで削除')}</span></div><div class="cpSaved" title="${t('cp.savedPal','ノーツ①②・白は固定 / 登録色はクリック=適用・右クリック=削除・Fで巡回')}"></div>`
    : _notesRow
      +_row(_lIco,'ライト色 ①②（クリック=配置色に選択→円で編集 / 現在色をドロップで色変更）','lightvan')
      +_row(_bIco,'ブースト色 ①②（クリック=選択→円で編集 / 現在色をドロップで色変更）','lightboost');
  pn.innerHTML=`<div class="cpMain"><div class="cpTop"><canvas class="cw" width="${WS}" height="${WS}"></canvas>
      <canvas class="cv" width="${BW}" height="${WS}"></canvas></div>
    <div class="cpCur" draggable="true" title="${t('cp.dragCur','現在色（クリック=元の対象へ戻す / Chromaパレットへドラッグ=保存）')}"></div>
    <div class="cpSeg cpt"><div data-v="rgb">${t('cp.rgb','RGB')}</div><div data-v="hsv">${t('cp.hsv','HSV')}</div></div>
    <div class="cpRows"></div>
    <div class="cpHex"><span style="color:#9a9aa2">${t('cp.hex','Hex')}</span><input spellcheck="false">
      <button title="${t('cp.pick','Eyedropper')}">💉</button></div></div>
    ${_bottom}`;
  document.body.appendChild(pn);
  // 位置: スウォッチ付近（画面内にクランプ）
  { const r=ndcv.getBoundingClientRect();
    const px=r.left+(wd?wd.x:60), py=r.top+(wd?wd.y+wd.h+8:60);
    pn.style.left=Math.max(8,Math.min(innerWidth-pn.offsetWidth-8,px))+'px';
    pn.style.top=Math.max(8,Math.min(innerHeight-pn.offsetHeight-8,py))+'px'; }
  const cw=pn.querySelector('.cw'), cv2=pn.querySelector('.cv');
  const wg=cw.getContext('2d'), vg=cv2.getContext('2d');
  const R=WS/2-2, CX=WS/2, CY=WS/2;
  function drawWheel(){
    const img=wg.createImageData(WS,WS);
    for(let y=0;y<WS;y++) for(let x=0;x<WS;x++){
      const dx=x-CX, dy=y-CY, r2=Math.hypot(dx,dy), i=(y*WS+x)*4;
      if(r2>R+1) continue;
      const hue=(Math.atan2(dy,dx)*180/Math.PI-90+360)%360;
      let sat=Math.min(1,r2/R);
      if(st.wheel==='perceptual') sat=sat*sat;
      const [r3,g3,b3]=hsv2rgb(hue,sat,1);
      img.data[i]=r3*255; img.data[i+1]=g3*255; img.data[i+2]=b3*255;
      img.data[i+3]=r2>R-1?(R+1-r2)*127:255;
    }
    wg.putImageData(img,0,0);
    // インジケータ
    const rr=(st.wheel==='perceptual'?Math.sqrt(st.s):st.s)*R;
    const an=(st.h+90)*Math.PI/180;
    const ix=CX+Math.cos(an)*rr, iy=CY+Math.sin(an)*rr;
    wg.beginPath(); wg.arc(ix,iy,7,0,7); wg.strokeStyle='#fff'; wg.lineWidth=1.6; wg.stroke();
    wg.beginPath(); wg.arc(ix,iy,8.5,0,7); wg.strokeStyle='rgba(0,0,0,.55)'; wg.lineWidth=1.2; wg.stroke();
  }
  function drawVBar(){
    const gr=vg.createLinearGradient(0,0,0,WS);
    gr.addColorStop(0,'#fff'); gr.addColorStop(1,'#000');
    vg.fillStyle=gr; vg.fillRect(0,0,BW,WS);
    const y=(1-st.v)*WS;
    vg.fillStyle='#e8e8ec'; vg.fillRect(0,Math.max(0,Math.min(WS-3,y-1.5)),BW,3);
    vg.strokeStyle='rgba(0,0,0,.6)'; vg.strokeRect(0.5,Math.max(0,Math.min(WS-3,y-1.5))+0.5,BW-1,2);
  }
  const rowsEl=pn.querySelector('.cpRows'), hexEl=pn.querySelector('.cpHex input');
  function rowDefs(){
    const A=t('cp.alpha','Alpha');
    if(st.tab==='rgb'){ const [r2,g2,b2]=hsv2rgb(st.h,st.s,st.v);
      return [['R',r2,v2=>{ const c=hsv2rgb(st.h,st.s,st.v); [st.h,st.s,st.v]=rgb2hsv(v2,c[1],c[2]); }],
              ['G',g2,v2=>{ const c=hsv2rgb(st.h,st.s,st.v); [st.h,st.s,st.v]=rgb2hsv(c[0],v2,c[2]); }],
              ['B',b2,v2=>{ const c=hsv2rgb(st.h,st.s,st.v); [st.h,st.s,st.v]=rgb2hsv(c[0],c[1],v2); }],
              [A,st.a,v2=>{ st.a=v2; }]];
    }
    return [[t('cp.hue','Hue'),st.h/360,v2=>{ st.h=v2*360; }],
            [t('cp.saturation','Saturation'),st.s,v2=>{ st.s=v2; }],
            [t('cp.value','Value'),st.v,v2=>{ st.v=v2; }],
            [A,st.a,v2=>{ st.a=v2; }]];
  }
  function refresh(){
    drawWheel(); drawVBar();
    pn.querySelectorAll('.cpt div').forEach(d=>d.classList.toggle('on',d.dataset.v===st.tab));
    rowsEl.innerHTML='';
    for(const [lb,v2,setr] of rowDefs()){
      const row=document.createElement('div'); row.className='cpSl';
      row.innerHTML=`<div class="fill" style="width:${Math.max(0,Math.min(1,v2))*100}%"></div>
        <span class="lb">${lb}</span><span class="vl">${v2.toFixed(3)}</span>`;
      row.addEventListener('pointerdown',e2=>{
        e2.preventDefault(); row.setPointerCapture(e2.pointerId);
        const rc=row.getBoundingClientRect();
        const mv=e3=>{ const f=Math.max(0,Math.min(1,(e3.clientX-rc.left)/rc.width));
          setr(f); commit(); refresh(); };
        mv(e2);
        row.onpointermove=e3=>{ if(e3.buttons&1) mv(e3); };
        row.onpointerup=()=>{ row.onpointermove=null; };
      });
      rowsEl.appendChild(row);
    }
    if(document.activeElement!==hexEl){
      const [r2,g2,b2]=hsv2rgb(st.h,st.s,st.v);
      hexEl.value=('#'+hx2(r2)+hx2(g2)+hx2(b2)+hx2(st.a)).toUpperCase();
    }
    { const ce=pn.querySelector('.cpCur'); if(ce){ const [r3,g3,b3]=hsv2rgb(st.h,st.s,st.v); ce.style.background='#'+hx2(r3)+hx2(g3)+hx2(b3); } }   // ドラッグ元チップに現在色を反映
  }
  // ホイール/Vバーのドラッグ
  function wheelPick(e2){
    const rc=cw.getBoundingClientRect();
    const dx=e2.clientX-rc.left-CX, dy=e2.clientY-rc.top-CY;
    st.h=(Math.atan2(dy,dx)*180/Math.PI-90+360)%360;
    let sat=Math.min(1,Math.hypot(dx,dy)/R);
    st.s=st.wheel==='perceptual'?sat*sat:sat;
    commit(); refresh();
  }
  cw.addEventListener('pointerdown',e2=>{ e2.preventDefault(); cw.setPointerCapture(e2.pointerId);
    wheelPick(e2); cw.onpointermove=e3=>{ if(e3.buttons&1) wheelPick(e3); };
    cw.onpointerup=()=>{ cw.onpointermove=null; }; });
  function vPick(e2){ const rc=cv2.getBoundingClientRect();
    st.v=Math.max(0,Math.min(1,1-(e2.clientY-rc.top)/WS)); commit(); refresh(); }
  cv2.addEventListener('pointerdown',e2=>{ e2.preventDefault(); cv2.setPointerCapture(e2.pointerId);
    vPick(e2); cv2.onpointermove=e3=>{ if(e3.buttons&1) vPick(e3); };
    cv2.onpointerup=()=>{ cv2.onpointermove=null; }; });
  // タブ（RGB/HSV。リニア/知覚的トグルは廃止＝リニア固定）
  pn.querySelector('.cpt').addEventListener('pointerdown',e2=>{ const d=e2.target.dataset.v;
    if(d){ st.tab=d; localStorage.setItem('bsnm_cpt',d); refresh(); } });
  // Hex入力
  hexEl.addEventListener('change',()=>{
    const m=hexEl.value.trim().match(/^#?([0-9a-fA-F]{6})([0-9a-fA-F]{2})?$/);
    if(!m){ refresh(); return; }
    const r2=parseInt(m[1].slice(0,2),16)/255, g2=parseInt(m[1].slice(2,4),16)/255, b2=parseInt(m[1].slice(4,6),16)/255;
    [st.h,st.s,st.v]=rgb2hsv(r2,g2,b2);
    if(m[2]) st.a=parseInt(m[2],16)/255;
    commit(); refresh();
  });
  hexEl.addEventListener('keydown',e2=>e2.stopPropagation());
  // スポイト
  pn.querySelector('.cpHex button').addEventListener('click',async()=>{
    if(!window.EyeDropper){ showErr('このブラウザはスポイトに未対応です'); return; }
    try{ const res=await new EyeDropper().open();
      const m=res.sRGBHex.match(/^#([0-9a-fA-F]{6})$/);
      if(m){ const r2=parseInt(m[1].slice(0,2),16)/255, g2=parseInt(m[1].slice(2,4),16)/255, b2=parseInt(m[1].slice(4,6),16)/255;
        [st.h,st.s,st.v]=rgb2hsv(r2,g2,b2); commit(); refresh(); }
    }catch(e3){}
  });
  // 現在色チップ等のドラッグ色（hex）を受けて、その対象の色を変更（ヘルバ様指定 2026-07-14）
  function attachSwatchDrop(bar,key){
    bar.addEventListener('dragover',e2=>{ e2.preventDefault(); e2.dataTransfer.dropEffect='copy'; bar.classList.add('drop'); });
    bar.addEventListener('dragleave',()=>bar.classList.remove('drop'));
    bar.addEventListener('drop',e2=>{ e2.preventDefault(); bar.classList.remove('drop');
      const hex=((e2.dataTransfer.getData('text/plain')||'').trim().slice(0,7)).toUpperCase();
      if(!/^#[0-9A-F]{6}$/.test(hex)||!TGT[key]) return;
      TGT[key].set(hex);
      if(activeTgt===key){ const r2=parseInt(hex.slice(1,3),16)/255, g2=parseInt(hex.slice(3,5),16)/255, b2=parseInt(hex.slice(5,7),16)/255; [st.h,st.s,st.v]=rgb2hsv(r2,g2,b2); refresh(); }
      renderAllCols(); try{ updateColorBtn(); }catch(_){} try{ updateLightColorTB(); }catch(_){} });   // ツールバーの色箱も同期
  }
  // ノーツ色行: クリック=配置色(赤/青)に選択＋円で編集 / ドラッグ元・ドロップ先両対応（ヘルバ様指定 2026-07-14）
  function renderColorPair(cols){ const el=pn.querySelector('.cpCols[data-cols="'+cols+'"]'); if(!el) return;
    el.innerHTML='';
    [cols+'0',cols+'1'].forEach((key,idx)=>{ if(!TGT[key]) return; const hxc=TGT[key].get();
      const bar=document.createElement('div'); bar.className='cpNoteBar'; bar.style.background=hxc; bar.dataset.tgt=key;
      bar.setAttribute('draggable','true');
      if(cols==='note'&&brush.c===idx){ bar.style.boxShadow='0 0 0 2px #e8f0ff'; }   // 現在の配置色(赤/青)を白リングで強調
      if(activeTgt===key) bar.classList.add('sel');
      bar.title=hxc+(cols==='note'?'（クリック=配置色に選択＋円で編集 / 現在色をドロップで色変更）':'（クリック=選択して円で編集）');
      bar.addEventListener('click',()=>{ if(cols==='note') setColor(idx,false); selectTarget(key); renderColorPair(cols); });
      bar.addEventListener('dragstart',e2=>{ e2.dataTransfer.setData('text/plain',TGT[key].get()); e2.dataTransfer.effectAllowed='copy'; });
      attachSwatchDrop(bar,key);
      el.appendChild(bar); }); }
  // バニラ版: ライト行=①②（配置色に選択可）／ブースト行=①②（編集のみ）＝白は廃止・ブーストは一段下げ（ヘルバ様指定 2026-07-14）
  function renderVanillaLights(){
    const elL=pn.querySelector('.cpCols[data-cols="lightvan"]');
    const elB=pn.querySelector('.cpCols[data-cols="lightboost"]');
    const baseOf={light0:4, light1:0};   // ①②のみ配置色に選択（白は廃止）
    const mk=key=>{ const isBase=(key in baseOf); const hxc=TGT[key].get();
      const bar=document.createElement('div'); bar.className='cpNoteBar'; bar.style.background=hxc; bar.dataset.tgt=key;
      if(isBase&&lightBrush.base===baseOf[key]){ bar.style.boxShadow='0 0 0 2px #e8f0ff'; }   // 現在の配置色を白リングで強調
      if(activeTgt===key) bar.classList.add('sel');
      bar.setAttribute('draggable','true');
      bar.title=hxc+(isBase?'（クリック=配置色に選択＋円で編集 / 現在色をドロップで色変更）':'（クリック=選択して円で編集 / 現在色をドロップで色変更）');
      bar.addEventListener('click',()=>{ if(isBase) setLightColor(baseOf[key]); selectTarget(key); renderVanillaLights(); });
      bar.addEventListener('dragstart',e2=>{ e2.dataTransfer.setData('text/plain',TGT[key].get()); e2.dataTransfer.effectAllowed='copy'; });
      attachSwatchDrop(bar,key); return bar; };
    if(elL){ elL.innerHTML=''; elL.appendChild(mk('light0')); elL.appendChild(mk('light1')); }
    if(elB){ elB.innerHTML=''; elB.appendChild(mk('boost0')); elB.appendChild(mk('boost1')); } }
  function renderAllCols(){ renderColorPair('note'); renderVanillaLights(); }
  function updateTargetSel(){ pn.querySelectorAll('.cpNoteBar[data-tgt]').forEach(b=>b.classList.toggle('sel',b.dataset.tgt===activeTgt));
    const ce=pn.querySelector('.cpCur'); if(ce) ce.classList.toggle('sel',activeTgt==null); }
  function selectTarget(key){ activeTgt=key||null;   // null=元ターゲット(現在色チップ) / TGTキー=その色を編集
    const src=(key&&TGT[key])?TGT[key].get():val;
    if(/^#[0-9a-fA-F]{6}/.test(src||'')){ const r2=parseInt(src.slice(1,3),16)/255, g2=parseInt(src.slice(3,5),16)/255, b2=parseInt(src.slice(5,7),16)/255; [st.h,st.s,st.v]=rgb2hsv(r2,g2,b2); }
    updateTargetSel(); refresh(); }
  // ※履歴カラーパレット(renderHist)は廃止済み＝死にコード削除（監査 2026-07-14。cpHistory/pushCpHistoryも撤去）
  // 保存パレット（右側・現在色チップをドラッグして保存 / クリック=適用 / 右クリック=削除）＝ヘルバ様指定 2026-07-13
  const curEl=pn.querySelector('.cpCur'), savedEl=pn.querySelector('.cpSaved');
  const curHex=()=>{ const [r2,g2,b2]=hsv2rgb(st.h,st.s,st.v); return ('#'+hx2(r2)+hx2(g2)+hx2(b2)).toUpperCase(); };
  function applyHex(hxc){ const r2=parseInt(hxc.slice(1,3),16)/255, g2=parseInt(hxc.slice(3,5),16)/255, b2=parseInt(hxc.slice(5,7),16)/255;
    [st.h,st.s,st.v]=rgb2hsv(r2,g2,b2); commit(); refresh(); }
  function addSaved(hxc){ const H=(hxc||'').slice(0,7).toUpperCase(); if(!/^#[0-9A-F]{6}$/.test(H)) return;
    const a=cpSaved(); if(!a.includes(H)){ a.push(H); setCpSaved(a); renderSaved(); } }
  function renderSaved(){ if(!savedEl) return; savedEl.innerHTML='';
    const mk=(hxc,removable,label)=>{ const sw=document.createElement('div'); sw.className='cpSavedSw'; sw.style.background=hxc; sw.title=(label?label+' ':'')+hxc;
      sw.dataset.hex=hxc; if(removable) sw.dataset.rm='1';   // 右クリックはコンテナ側で一括処理（下）＝固定色や余白でもブラウザメニューを出さない
      sw.addEventListener('pointerdown',e2=>{ if(e2.button!==0) return; e2.preventDefault(); applyHex(hxc); });   // クリック=この色を適用（ライトのクロマへ）
      savedEl.appendChild(sw); };
    mk(cRED,false,'ノーツ①'); mk(cBLUE,false,'ノーツ②'); mk(WHITE_HEX,false,'白');   // 先頭固定=ノーツ①②・白（削除不可・ヘルバ様指定 2026-07-13）
    for(const hxc of cpSaved()) mk(hxc,true,'登録色'); }
  // 右クリックはパレット全体で受ける（以前は登録色にしか付いておらず、固定色・余白でブラウザメニューが出ていた＝ヘルバ様報告）
  if(savedEl) savedEl.addEventListener('contextmenu',e2=>{
    e2.preventDefault();                                        // パレット内ではブラウザメニューを出さない
    const sw=e2.target&&e2.target.closest?e2.target.closest('.cpSavedSw'):null;
    if(!sw) return;                                             // 余白＝抑止だけ
    if(!sw.dataset.rm){ stat(t('msg.palFixed','ノーツ①②・白は削除できません（登録した色のみ削除できます）')); return; }
    const hxc=sw.dataset.hex;
    // 確認はアプリ内メニューで出す。ネイティブconfirm()はページ全体をブロックし、環境によっては
    // ダイアログを閉じるまで一切操作を受け付けなくなる（＝「消せない」状態に見える。ヘルバ様報告 2026-07-18）
    ctxEl.classList.add('overPanel');   // カラーピッカー(z-index:120)より手前に出す＝背面に潜らない
    showMenu(e2.clientX, e2.clientY, [
      [tf('cf.delPalColor','{hex} を削除しますか？',{hex:hxc}), ()=>{ setCpSaved(cpSaved().filter(c=>c!==hxc)); renderSaved();
        stat(tf('msg.palRemoved','{hex} をChromaパレットから削除しました',{hex:hxc})); }],
      ['---'],
      [t('word.cancel','キャンセル'), ()=>{}],
    ]); });
  if(curEl) curEl.addEventListener('click',()=>selectTarget(null));   // 現在色チップをクリック=元ターゲット（onCommit先）へ戻す
  if(curEl) curEl.addEventListener('dragstart',e2=>{ e2.dataTransfer.setData('text/plain',curHex()); e2.dataTransfer.effectAllowed='copy'; });   // 現在色を各スウォッチ/パレットへドラッグ（バニラでも有効・ヘルバ様指定 2026-07-14）
  if(curEl&&savedEl){
    savedEl.addEventListener('dragover',e2=>{ e2.preventDefault(); e2.dataTransfer.dropEffect='copy'; savedEl.classList.add('drop'); });
    savedEl.addEventListener('dragleave',()=>savedEl.classList.remove('drop'));
    savedEl.addEventListener('drop',e2=>{ e2.preventDefault(); savedEl.classList.remove('drop'); addSaved(e2.dataTransfer.getData('text/plain')||curHex()); }); }
  // 外クリック / Esc で閉じる（閉じる時に現在色を履歴へ積む）
  const closePanel=()=>{ pn.remove(); removeEventListener('pointerdown',closer,true); _cpTrigger=null; };
  const closer=e2=>{
    if(ctxEl.contains(e2.target)) return;   // パレットから開いた確認メニュー(#ctxmenuはパレット外のDOM)のクリックで閉じない（ヘルバ様報告 2026-07-18）
    if(!pn.contains(e2.target)){
    if(_cpTrigger&&_cpTrigger.contains&&_cpTrigger.contains(e2.target)){ _cpSuppress=performance.now(); _cpSuppressTrig=_cpTrigger; }   // トリガー(スウォッチ)自身のクリックで閉じた＝直後の同トリガー再オープンを抑止
    closePanel(); } };
  setTimeout(()=>addEventListener('pointerdown',closer,true),0);
  pn.addEventListener('keydown',e2=>{ if(e2.key==='Escape') closePanel(); });
  renderAllCols(); renderSaved(); refresh(); updateTargetSel();
}
// ---- マルチライン: 非アクティブの INPUT/OUTPUT/MUSIC（濃灰・選択するまでラインが通らない） ----
let altIns=[], altOuts=[], altSongs=[];          // {uid,nx,ny,w?,...} id='in@uid'/'out@uid'/'song@uid'
let activeUids={in:null,out:null,song:null};     // アクティブラインの由来uid（null=初期ライン）
function activateLine(uid){
  if(playing) pause();
  snapshot('node'); syncGraphFromFlat();
  const ren=(a,b)=>{ for(const e of graphEdges){
    if(e.fromId===a) e.fromId=b;
    if(e.toId===a) e.toId=b; } };
  // ---- INPUT ----
  const ii=altIns.findIndex(n=>n.uid===uid);
  if(ii>=0){
    const nu=altIns.splice(ii,1)[0];
    const old=activeUids.in||('L'+(++_nid));
    ren('in','@TMPIN'); ren('in@'+uid,'in'); ren('@TMPIN','in@'+old);
    altIns.push({uid:old,nx:graphIO.in.nx,ny:graphIO.in.ny,w:graphIO.in.w,bpm:BPM,
      colors:graphIO.in.colors,env:graphIO.in.env});
    graphIO.in={nx:nu.nx,ny:nu.ny,w:nu.w,colors:nu.colors,env:nu.env};
    if(+nu.bpm>0){ BPM=+nu.bpm; }
    activeUids.in=uid;
  }
  // ---- OUTPUT ----
  const oi=altOuts.findIndex(n=>n.uid===uid);
  if(oi>=0){
    const nu=altOuts.splice(oi,1)[0];
    const old=activeUids.out||('L'+(++_nid));
    ren('out','@TMPOUT'); ren('out@'+uid,'out'); ren('@TMPOUT','out@'+old);
    const oldOut={...graphIO.out,uid:old};
    altOuts.push(oldOut);
    graphIO.out={...nu}; delete graphIO.out.uid;
    activeUids.out=uid;
  }
  // ---- MUSIC ----
  const si=altSongs.findIndex(n=>n.uid===uid);
  if(si>=0){
    const nu=altSongs.splice(si,1)[0];
    const old=activeUids.song||('L'+(++_nid));
    ren('song','@TMPSG'); ren('song@'+uid,'song'); ren('@TMPSG','song@'+old);
    if(songNode) altSongs.push({...songNode,uid:old});
    songNode={nx:nu.nx,ny:nu.ny,w:nu.w,name:nu.name||'',offset:nu.offset||0,handle:nu.handle||null};
    songDeleted=false; activeUids.song=uid;
    audioBuf=null; ovWave=null; specMag=null; specSrcCanvas=null; specForBuf=null;
    if(nu.handle){ (async()=>{ try{
        const f=await nu.handle.getFile();
        audioBuf=await actx.decodeAudioData(await f.arrayBuffer());
        songDur=audioBuf.duration; buildWaveData();
      }catch(err){ showErr('音源の読込に失敗しました — MUSICノードの📁から選び直してください'); } })(); }
    else showErr('このラインの音源が未読込です — MUSICノードの📁から選んでください');
  }
  cur=0; offset=0; prevPlayBeat=-1;
  { const src=(typeof lineSrc!=='undefined')&&lineSrc.get(uid);
    if(src) fillDiffSelectFromInfo(src.info,src.cur); }
  compileGraphToFlat(); metaDirty=true; ndSel='in';
  stat('ラインを切り替えました');
}
// 空の基本構成（新規時のデフォルト盤面）
function newDefaultGraph(){
  const wx=60, wy=230;
  sections=[]; extraNodes=[]; graphEdges=[]; cutSet.clear();
  altIns=[]; altOuts=[]; altSongs=[];
  activeUids={in:null,out:null,song:null};
  ndSel=null;
  // 既定のシートは作らない（シートはNLEの右クリックで作成）。notes/lightsはin→out直結で配置ガードを通す
  graphIO={in:{nx:wx,ny:wy},out:{nx:wx+1020,ny:wy-80,diffs:{}}};
  songNode={nx:wx+250,ny:wy+130,name:'',offset:0}; songDeleted=false;
  const inf=createExtra('info',wx+560,wy-170);
  const cov=createExtra('cover',wx+560,wy+120);
  graphEdges.push(
    {fromId:'in',toId:'out',sig:'notes'},
    {fromId:'in',toId:'out',sig:'lights'},
    {fromId:'in',toId:'song',sig:'audio'},{fromId:'song',toId:'out',sig:'audio'},
    {fromId:inf.id,toId:'out',sig:'info'},{fromId:cov.id,toId:'out',sig:'cover'});
  edgesInited=true;
  metaDirty=false;
}
// デフォルト盤面が手つかずのままか（最初のドロップはこれを置き換えてアクティブになる）
function defaultFresh(){
  return sections.length===0&&notes.length===0&&lightEvents.length===0
    &&!audioBuf&&!(songNode&&songNode.name)&&extraNodes.length===2
    &&altIns.length===0&&altOuts.length===0&&altSongs.length===0;
}
function altAt(sx,sy){
  const [wx,wy]=ndFromScreen(sx,sy);
  const chk=(arr,side,pre)=>{ for(let i=arr.length-1;i>=0;i--){
    const g=nodeGeomOf(pre+arr[i].uid); if(!g) continue;
    if(wx>=g.nx&&wx<=g.nx+g.w&&wy>=g.ny&&wy<=g.ny+g.h) return {uid:arr[i].uid,side}; } return null; };
  return chk(altIns,'in','in@')||chk(altOuts,'out','out@')||chk(altSongs,'song','song@');
}
let songDeleted=false;   // MUSICノードを意図的に消した（ensureGraphIOの自動復活を止める）
let ndClip=null;   // NODEのコピー内容 {type:'sheet'|'extra', data, handleRef}
function copySelNode(){
  const id=ndSel;
  if(!id){ stat('コピー: ノードを選択してください'); return; }
  if(id.includes('@')){ stat('休止ラインのノードはコピーできません（クリックで選択してから）'); return; }
  if(id==='in'){ ndClip={type:'in',data:{bpm:BPM,colors:JSON.parse(JSON.stringify(graphIO.in.colors||null)),
      env:graphIO.in.env,w:graphIO.in.w},handleRef:null};
    stat('コピー: INPUTノード'); return; }
  if(id==='out'){ const {nx,ny,uid,...rest}=graphIO.out;
    ndClip={type:'out',data:JSON.parse(JSON.stringify(rest)),handleRef:null};
    stat('コピー: OUTPUTノード'); return; }
  if(id==='song'){ ndClip={type:'song',data:{name:songNode.name||'',offset:songNode.offset||0,w:songNode.w},
      handleRef:songNode.handle||null};
    stat('コピー: MUSICノード'); return; }
  const ex=extraNodes.find(x=>x.id===id);
  if(ex){ const {handle,...rest}=ex;
    ndClip={type:'extra',data:JSON.parse(JSON.stringify(rest)),handleRef:ex.handle||null};
    stat(tf('msg.copyNode','コピー: {title}ノード',{title:EN_DEF[ex.kind].title})); return; }
  const s2=sections.find(x=>x.id===id);
  if(s2){ ndClip={type:'sheet',data:JSON.parse(JSON.stringify(s2)),handleRef:null};
    stat(tf('msg.copyLabel','コピー: 「{label}」',{label:s2.label})); return; }
}
function pasteNode(){
  if(!ndClip){ stat('貼り付けるノードがありません（Ctrl+Cでコピー）'); return; }
  const [mx,my]=(_ndMouse&&_ndMouse.length)?_ndMouse:[120,120];
  if(ndClip.type==='in'){
    altIns.push({uid:'L'+(++_nid),nx:mx,ny:my,bpm:ndClip.data.bpm,
      colors:ndClip.data.colors||undefined,env:ndClip.data.env,w:ndClip.data.w});
    metaDirty=true; stat('INPUTノードを貼り付けました（クリックでライン選択）'); return; }
  if(ndClip.type==='out'){
    altOuts.push({uid:'L'+(++_nid),nx:mx,ny:my,...JSON.parse(JSON.stringify(ndClip.data))});
    metaDirty=true; stat('OUTPUTノードを貼り付けました（クリックでライン選択）'); return; }
  if(ndClip.type==='song'){
    altSongs.push({uid:'L'+(++_nid),nx:mx,ny:my,name:ndClip.data.name,offset:ndClip.data.offset,
      w:ndClip.data.w,handle:ndClip.handleRef||null});
    metaDirty=true; stat('MUSICノードを貼り付けました（クリックでライン選択）'); return; }
  if(ndClip.type==='sheet'){
    graphOp(()=>{
      const nu=JSON.parse(JSON.stringify(ndClip.data));
      nu.id='n'+(++_nid)+Math.random().toString(36).slice(2,6);
      nu.beat=99999+sections.length; nu.nx=mx; nu.ny=my;
      sections.push(nu);
      ndSel=nu.id;
    });
    stat('Sheetノードを貼り付けました（未配線）');
  } else {
    const nu=JSON.parse(JSON.stringify(ndClip.data));
    nu.id='x'+(++_nid)+Math.random().toString(36).slice(2,6);
    nu.nx=mx; nu.ny=my;
    if(ndClip.handleRef) nu.handle=ndClip.handleRef;
    extraNodes.push(nu); metaDirty=true; ndSel=nu.id;
    stat(tf('msg.pasteNode','{title}ノードを貼り付けました',{title:EN_DEF[nu.kind].title}));
  }
}
function deleteSelNode(){
  const id=ndSel; if(!id) return;
  if(id==='in'||id==='out'){
    const side=id, arr=side==='in'?altIns:altOuts;
    if(!arr.length){ showErr(side==='in'?'最後のINPUTは削除できません':'最後のOUTPUTは削除できません'); return; }
    snapshot('node'); syncGraphFromFlat();
    graphEdges=graphEdges.filter(e2=>e2.fromId!==side&&e2.toId!==side);   // このノードの配線を除去
    const nu=arr.shift();                                                 // 先頭の休止ノードを昇格
    const ren=(a,b)=>{ for(const e of graphEdges){ if(e.fromId===a)e.fromId=b; if(e.toId===a)e.toId=b; } };
    ren(side+'@'+nu.uid,side);
    if(side==='in'){
      graphIO.in={nx:nu.nx,ny:nu.ny,w:nu.w,colors:nu.colors,env:nu.env};
      if(+nu.bpm>0) BPM=+nu.bpm;
      activeUids.in=nu.uid;
    } else {
      graphIO.out={...nu}; delete graphIO.out.uid;
      activeUids.out=nu.uid;
    }
    compileGraphToFlat(); metaDirty=true; ndSel=null;
    stat(tf('msg.ioDeletedActivated','{io}を削除し、休止ノードをアクティブにしました',{io:side==='in'?'INPUT':'OUTPUT'})); return;
  }
  if(id==='song'){ graphOp(()=>{ graphEdges=graphEdges.filter(e2=>e2.sig!=='audio');
      songNode=null; songDeleted=true; }); ndSel=null; stat('MUSICノードを削除しました'); return; }
  const ex=extraNodes.find(x=>x.id===id);
  if(ex){ graphOp(()=>{ graphEdges=graphEdges.filter(e2=>e2.fromId!==id&&e2.toId!==id);
      extraNodes=extraNodes.filter(x=>x!==ex); }); ndSel=null;
    stat(tf('msg.delNode','{title}ノードを削除しました',{title:EN_DEF[ex.kind].title})); return; }
  const s2=sections.find(x=>x.id===id);
  if(s2){ if(sections.length<=1){ showErr('最後のSheetノードは削除できません'); return; }
    graphOp(()=>removeNodeMerge(s2)); ndSel=null; stat(tf('msg.mergedLabel','「{label}」を統合しました',{label:s2.label})); return; }
}
function deleteMultiSel(){   // 範囲選択したノードをまとめて削除（各ノードの削除規則はそのまま適用）
  const ids=[...ndMultiSel]; ndMultiSel.clear();
  for(const id of ids){ ndSel=id; deleteSelNode(); }
  ndSel=null;
}
const OUT_DIFFS=['Easy','Normal','Hard','Expert','ExpertPlus'];
const _coverImgs=new Map();   // coverノードid → {key,bmp} プレビュー用ImageBitmap
async function loadCoverPreview(n){
  const key=n.handle?('h:'+n.name):('f:'+(n.name||'').toLowerCase());
  const c=_coverImgs.get(n.id);
  if(c&&c.key===key) return;
  _coverImgs.set(n.id,{key,bmp:(c&&c.bmp)||null});   // 先にkeyを立てて多重ロード防止
  let file=null;
  try{
    if(n.handle) file=await n.handle.getFile();
    else if(n.name&&files[(n.name||'').toLowerCase()]) file=files[n.name.toLowerCase()];
  }catch(e){}
  let bmp=null;
  if(file){ try{ bmp=await createImageBitmap(file); }catch(e){} }
  _coverImgs.set(n.id,{key,bmp});
}
let outDirHandle=null;   // 書き出し先（セッション中のみ。名前はgraphIO.outに保存）
// ---- ネイティブ(pywebview)のフォルダ/ファイルを FileSystemHandle 互換の薄い代役で包む ----
// 書き出しが使うのは getDirectoryHandle / getFileHandle / createWritable / getFile だけなので、
// 同じ形で実装すれば書き出し側は無改修。実体はapp.pyのApi.fs_*（絶対パスで直接読み書き）。
// ブラウザのハンドルと違いセッションをまたいで失効しないので、パスをプロジェクトに保存して自動接続できる。
const nativeApi=()=>(window.pywebview&&window.pywebview.api&&window.pywebview.api.fs_write&&window.pywebview.api.pick_folder)?window.pywebview.api:null;
const _pathBase=p=>String(p).split(/[\\/]/).filter(Boolean).pop()||String(p);
function mkNativeFile(path){
  return { kind:'file', name:_pathBase(path), nativePath:path,
    async getFile(){ const j=await nativeApi().read_song_file(path);   // 汎用の読み出し（名前は曲用だが中身はただのファイル読込）
      if(!j||!j.ok) throw new Error((j&&j.error)||'read-failed');
      return new File([b64ToBuf(j.data)],j.name,{lastModified:(j.mtime||0)*1000}); },
    async createWritable(){ const parts=[];
      return { async write(d){ parts.push(d); },
        async close(){ const u=await blobToDataURL(new Blob(parts));
          const j=await nativeApi().fs_write(path,u.slice(u.indexOf(',')+1));
          if(!j||!j.ok) throw new Error((j&&j.error)||'write-failed'); } }; } };
}
function mkNativeDir(path){
  return { kind:'directory', name:_pathBase(path), nativePath:path,
    async getDirectoryHandle(n,o){ const j=await nativeApi().fs_subdir(path,n,!!(o&&o.create));
      if(!j||!j.ok) throw new Error((j&&j.error)||'not-found'); return mkNativeDir(j.path); },
    async getFileHandle(n,o){ const j=await nativeApi().fs_file(path,n,!!(o&&o.create));
      if(!j||!j.ok) throw new Error((j&&j.error)||'not-found'); return mkNativeFile(j.path); } };
}
async function pickCoverImage(startPath){   // →{fh,path}|null。ネイティブがあれば実パス付き、無ければ従来のブラウザピッカー
  const api=nativeApi();
  if(api){ let p=null; try{ p=await api.pick_image_file(startPath||''); }catch(e){} return p?{fh:mkNativeFile(p),path:p}:null; }
  let fh=null;
  try{ [fh]=await showOpenFilePicker({id:'nlm-cover',types:[{description:'カバー画像',accept:{'image/*':['.png','.jpg','.jpeg','.webp','.gif','.bmp']}}]}); }catch(e){}
  return fh?{fh,path:''}:null;
}
async function pickOutFolder(){
  const api=nativeApi();
  if(api){   // 保存済みパスを開始位置に渡す＝ダイアログは「今の出力先」で開く（旧: ブラウザが覚えた古い場所で開いていた）
    _pickOpen='outdir'; let path=null;
    try{ path=await api.pick_folder((graphIO&&graphIO.out&&graphIO.out.outDirPath)||''); }catch(e){}
    _pickOpen=null; if(!path) return;
    outDirHandle=mkNativeDir(path);
    if(graphIO&&graphIO.out){ graphIO.out.outDirName=outDirHandle.name; graphIO.out.outDirPath=path; }
    metaDirty=true; stat(tf('msg.exportDest','書き出し先: {name}',{name:outDirHandle.name})); return;
  }
  let h;
  _pickOpen='outdir';
  try{ h=await showDirectoryPicker({mode:'readwrite',id:'nlm-outdir'}); }catch(e){ _pickOpen=null; return; }   // id指定でブラウザに前回の場所を覚えさせる（階層ズレ対策）
  _pickOpen=null;
  outDirHandle=h;
  if(graphIO&&graphIO.out){ graphIO.out.outDirName=h.name; graphIO.out.outDirPath=''; }
  metaDirty=true; stat(tf('msg.exportDest','書き出し先: {name}',{name:h.name}));
}
// ノード上のその場テキスト入力（prompt()の代わり。Enter=確定 / Esc=取消 / 外クリック=確定）
function ndInlineEdit(rect,val,onCommit,numeric,anchor){
  const r=(anchor||ndcv).getBoundingClientRect();
  const inp=document.createElement('input');
  inp.type='text'; inp.value=val??'';
  Object.assign(inp.style,{position:'fixed',left:(r.left+rect.x)+'px',top:(r.top+rect.y)+'px',
    width:Math.max(60,rect.w)+'px',height:Math.max(16,rect.h)+'px',zIndex:'99',
    background:'#1f1f1f',color:'#eee',border:'1px solid #8160e3',borderRadius:'5px',   // INFO入力欄と同じ様式（フォーカス紫）
    font:`${Math.max(11,Math.round(rect.h*0.55))}px ${FONT}`,padding:'0 6px',boxSizing:'border-box',outline:'none'});
  let done=false;
  // pointerdownの処理中にfocusすると直後のデフォルト動作でblurされて一瞬で消えるため、イベント完了後に出す
  setTimeout(()=>{ if(!done){ document.body.appendChild(inp); inp.focus(); inp.select(); } },0);
  const fin=commit=>{ if(done) return; done=true; const v=inp.value; inp.remove();
    if(!commit) return;
    if(numeric){ const n2=parseFloat(v); if(isFinite(n2)) onCommit(n2); }
    else onCommit(v); };
  inp.addEventListener('keydown',ev=>{ ev.stopPropagation();
    if(ev.key==='Enter') fin(true); else if(ev.key==='Escape') fin(false); });
  inp.addEventListener('blur',()=>fin(true));
}
function setBPMv(v){
  if(!isFinite(v)||v<=0) return;
  BPM=Math.round(v*100)/100;
  if(infoBase){ infoBase._beatsPerMinute=BPM; infoDirty=true; applyInfoChain(); }
  offset=beatToTimeTM(cur);
  if(playing) pause();
  if(audioBuf) buildWaveData();
  metaDirty=true; stat(tf('msg.bpmSet','BPM = {bpm}',{bpm:BPM}));
}
// ---- BPM推定（オンセット包絡の自己相関 + コムフィルタ追い込み） ----
// t0/t1（生音声の秒。省略時は曲全体）を指定すると、その区間だけを対象にテンポを推定する（テンポパート機能の自動判定用）。
function estimateBPM(t0,t1){
  const sr=audioBuf.sampleRate, hop=256, chFull=audioBuf.getChannelData(0);
  const i0=Math.max(0,Math.floor((t0||0)*sr)), i1=Math.min(chFull.length,(t1!=null)?Math.ceil(t1*sr):chFull.length);
  const ch=chFull.subarray(i0,Math.max(i0+1,i1));
  const N=Math.floor(ch.length/hop), fps=sr/hop;
  const minSec=(t0||t1!=null)?6:10;   // 区間指定時（テンポパート）は短めの部分でも判定できるよう下限を緩める
  if(N<fps*minSec) throw new Error(tf('msg.bpmTooShort','区間が短すぎます（{sec}秒以上必要）',{sec:String(minSec)}));
  // フレームエネルギー: 低域（キック強調・160Hzローパス）+ 全帯域
  const eLP=new Float32Array(N), eF=new Float32Array(N);
  let lp=0; const a=1-Math.exp(-2*Math.PI*160/sr);
  for(let i=0;i<N;i++){ let sL=0,sF=0; const o=i*hop;
    for(let j=0;j<hop;j++){ const x=ch[o+j]||0; lp+=a*(x-lp); sL+=lp*lp; sF+=x*x; }
    eLP[i]=sL; eF[i]=sF; }
  // オンセット強度 = エネルギー増分の半波整流（低域を2倍重み）
  const env=new Float32Array(N);
  for(let i=1;i<N;i++) env[i]=Math.max(0,eLP[i]-eLP[i-1])*2+Math.max(0,eF[i]-eF[i-1]);
  let mean=0; for(let i=0;i<N;i++) mean+=env[i]; mean/=N;
  // コムスコア: 周期P間隔でパルスを立て、乗った位置の平均オンセット強度（位相8通りの最大）
  const comb=(bpm,i0,i1)=>{ const P=fps*60/bpm; let best=0;
    for(let ph=0;ph<8;ph++){ let s2=0,c=0;
      for(let t=i0+P*ph/8;t<i1;t+=P){ s2+=env[t|0]; c++; }
      if(c>4){ const v=s2/c; if(v>best)best=v; } }
    return best; };
  // 粗探索: 自己相関（55〜220BPM・項数正規化）
  const minL=Math.floor(fps*60/220), maxL=Math.min(N-1,Math.ceil(fps*60/55));
  let bestL=minL, bestA=-1;
  for(let L=minL;L<=maxL;L++){ let s2=0;
    for(let i=L;i<N;i++) s2+=env[i]*env[i-L];
    s2/=(N-L); if(s2>bestA){ bestA=s2; bestL=L; } }
  const coarse=60*fps/bestL;
  // 候補（半分/倍/付点系も含む）を±1.2の範囲で0.01刻みに追い込み
  const seen=new Set(), cands=[];
  for(const b0 of [coarse,coarse*2,coarse/2,coarse*4/3,coarse*3/2]){
    if(b0<55||b0>220) continue;
    let bb=b0, bv=-1;
    for(let b=b0-1.2;b<=b0+1.201;b+=0.01){
      const v=comb(b,0,N)*(b>=90&&b<=180?1.06:1);   // 同点なら常識的レンジを優先
      if(v>bv){ bv=v; bb=b; } }
    bb=Math.abs(bb-Math.round(bb))<=0.03?Math.round(bb):Math.round(bb*100)/100;
    const key=Math.round(bb*10);
    if(seen.has(key)) continue; seen.add(key);
    cands.push({bpm:bb,score:bv});
  }
  cands.sort((p2,q)=>q.score-p2.score);
  // 一致度: 拍位置の平均強度が全体平均の何倍か → %化
  const top=cands.slice(0,3).map(c=>({bpm:c.bpm,
    conf:Math.max(5,Math.min(99,Math.round(100*(1-mean/Math.max(c.score,1e-12)))))}));
  // テンポ揺れ検出: 前半と後半で最良BPMが割れるか
  const half=(i0,i1)=>{ let bb=top[0].bpm, bv=-1;
    for(let b=top[0].bpm-0.6;b<=top[0].bpm+0.601;b+=0.02){
      const v=comb(b,i0,i1); if(v>bv){ bv=v; bb=b; } }
    return bb; };
  const drift=Math.abs(half(0,N>>1)-half(N>>1,N))>0.25;
  return {cands:top,drift};
}
function runBpmEstimate(e){
  if(!audioBuf){ showErr('先に曲を読み込んでください'); return; }
  stat('BPMを解析しています…');
  setTimeout(()=>{
    let r; try{ r=estimateBPM(); }catch(err){ showErr(tf('msg.bpmAnalyzeFail','BPM解析に失敗: {err}',{err:err.message})); return; }
    const items=r.cands.map(c=>[tf('ctx.bpmSetCand','BPM {bpm} に設定（一致度 {conf}%）',{bpm:c.bpm.toFixed(2),conf:c.conf}),()=>setBPMv(c.bpm)]);
    if(r.drift) items.unshift([t('ctx.bpmDrift','⚠ テンポが一定でない曲の可能性があります'),()=>{}]);
    showMenu(e.clientX,e.clientY,items);
    stat('BPM候補を表示しました（採用するものを選んでください）');
  },30);
}
function portPosOf(id,side,sig){
  const w=portPosW(id,sig,side); if(!w) return null;
  return ndToScreen(w[0],w[1]);
}
// ポートのヒットテスト
function resizeAt(sx,sy){
  const [wx,wy]=ndFromScreen(sx,sy);
  const ids=['in','out']; if(songNode) ids.push('song');
  for(const sec of sections) ids.push(sec.id);
  for(const ex of extraNodes) ids.push(ex.id);
  for(const n of altIns) ids.push('in@'+n.uid);
  for(const n of altOuts) ids.push('out@'+n.uid);
  for(const n of altSongs) ids.push('song@'+n.uid);
  for(const id of ids){ const g=nodeGeomOf(id); if(!g) continue;
    if(Math.abs(wx-(g.nx+g.w))<=9&&Math.abs(wy-(g.ny+g.h))<=9) return g.base; }
  return null;
}
function portHit(sx,sy){
  if(!graphIO) return null;
  const sc=ndCam.scale, R2=(6*sc+2.5)**2;
  const ids=['in','out']; if(songNode) ids.push('song');
  for(const sec of sections) ids.push(sec.id);
  for(const ex of extraNodes) ids.push(ex.id);
  for(const n of altIns) ids.push('in@'+n.uid);
  for(const n of altOuts) ids.push('out@'+n.uid);
  for(const n of altSongs) ids.push('song@'+n.uid);
  for(const id of ids){
    for(const r of nodeRowsFor(id)){
      if(r.inp){ const p=portPosOf(id,'in',r.sig);
        if(p&&(sx-p[0])**2+(sy-p[1])**2<R2) return {nodeId:id,side:'in',sig:r.sig}; }
      if(r.out){ const p=portPosOf(id,'out',r.sig);
        if(p&&(sx-p[0])**2+(sy-p[1])**2<R2) return {nodeId:id,side:'out',sig:r.sig}; }
    }
  }
  return null;
}
// 配線本体のヒットテスト（クリック=切断）
function edgeHit(sx,sy){
  if(!graphIO) return null;
  const sc=ndCam.scale;
  for(const e of graphEdges){
    const p1=portPosOf(e.fromId,'out',e.sig), p2=portPosOf(e.toId,'in',e.sig);
    if(!p1||!p2) continue;
    const [x1,y1]=p1,[x2,y2]=p2, cx1=x1+46*sc, cx2=x2-46*sc;
    for(let t=0.14;t<0.87;t+=0.045){ const u=1-t;   // 端はポート/ノード操作を優先
      const px=u*u*u*x1+3*u*u*t*cx1+3*u*t*t*cx2+t*t*t*x2;
      const py=u*u*u*y1+3*u*u*t*y1+3*u*t*t*y2+t*t*t*y2;
      if((sx-px)**2+(sy-py)**2<49) return e;
    } }
  return null;
}
let songNode=null;        // {nx,ny,name} 音源はこのノードが所有（オレンジ専用ルート）
function ensureGraphIO(){
  if(!(graphIO&&graphIO.in&&graphIO.out)){
    const ordered=[...sections].sort((a,b)=>a.beat-b.beat);
    const f=ordered[0]||{nx:60,ny:80}, l=ordered[ordered.length-1]||f;
    graphIO={in:{nx:f.nx-IOW-70,ny:f.ny-10}, out:{nx:l.nx+ND_W+70,ny:l.ny-10}};
  }
  if(!songNode&&!songDeleted){
    songNode={nx:(graphIO.in.nx+graphIO.out.nx)/2, ny:Math.max(graphIO.in.ny,graphIO.out.ny)+170, name:''};
  }
}
// 曲フォルダからの新規読込時の基本構成（INPUT / Song / MUSIC / INFO / COVER / OUTPUT）
function buildDefaultGraph(){
  const ordered=[...sections].sort((a,b)=>a.beat-b.beat);
  ordered.forEach((s2,i)=>{ s2.nx=300+i*(ND_W+60); s2.ny=90; });
  const outX=Math.max(700,300+ordered.length*(ND_W+60)+140);
  graphIO={in:{nx:40,ny:200},out:{nx:outX,ny:170}};
  songNode={nx:300,ny:330,name:''};
  extraNodes=[]; graphEdges=[]; edgesInited=false;
  const inf=createExtra('info',outX-ENW-120,10);       // info.datの内容はcreateExtraが取り込む
  const cov=createExtra('cover',outX-ENW-120,350);
  if(infoBase&&infoBase._coverImageFilename){
    cov.name=infoBase._coverImageFilename;
    const h=handles[(cov.name||'').toLowerCase()];
    if(h&&h.getFile) cov.handle=h;
  }
  graphEdges.push({fromId:inf.id,toId:'out',sig:'info'},{fromId:cov.id,toId:'out',sig:'cover'});
}
// 音源ファイルを開く（主要な音楽形式に対応）
function b64ToBuf(b64){ const bin=atob(b64); const a=new Uint8Array(bin.length); for(let i=0;i<bin.length;i++) a[i]=bin.charCodeAt(i); return a.buffer; }
// デコード後の共通後処理（ネイティブパス経由/ブラウザピッカー経由どちらからも呼ぶ）
async function applyLoadedSong(buf,name){
  if(playing) pause();
  audioBuf=await actx.decodeAudioData(buf);
  songDur=audioBuf.duration; buildWaveData();
  document.getElementById('tbgTime').style.display='';
  cur=0; offset=0; musicSegs=null; musicSelSet=new Set();
  songDeleted=false; ensureGraphIO(); if(songNode) songNode.name=name; metaDirty=true;
}
// pywebviewのネイティブダイアログ経由: 実パスをsongNode.nativePathへ保存＝次回はダイアログ無しで自動読込できる
async function openSongFileNative(){
  let path; try{ path=await window.pywebview.api.pick_song_file(); }catch(e){ path=null; }
  if(!path) return;
  try{
    const j=await window.pywebview.api.read_song_file(path);
    if(!j||!j.ok) throw new Error((j&&j.error)||'read failed');
    await applyLoadedSong(b64ToBuf(j.data),j.name);
    if(songNode){ songNode.nativePath=path; songNode.handle=null; }
    showOk(tf('msg.loadedAudio','音源を読み込みました: {name}（{dur}秒）',{name:j.name,dur:songDur.toFixed(1)}));
  }catch(err){ showErr(tf('msg.loadAudioFail','音源の読込に失敗: {err}',{err})); }
}
async function openSongFile(){
  if(window.pywebview&&window.pywebview.api&&window.pywebview.api.pick_song_file) return openSongFileNative();
  let fh;
  _pickOpen='song';
  try{ [fh]=await showOpenFilePicker({types:[{description:'音源ファイル',
    accept:{'audio/*':['.egg','.ogg','.oga','.opus','.mp3','.m4a','.aac','.wav','.flac','.weba','.webm']}}]}); }
  catch(e){ _pickOpen=null; return; }
  _pickOpen=null;
  try{
    const f=await fh.getFile();
    await applyLoadedSong(await f.arrayBuffer(),f.name);
    if(songNode){ songNode.handle=fh; songNode.nativePath=''; }
    showOk(tf('msg.loadedAudio','音源を読み込みました: {name}（{dur}秒）',{name:f.name,dur:songDur.toFixed(1)}));
  }catch(err){ showErr(tf('msg.loadAudioFail','音源の読込に失敗: {err}',{err})); }
}
// 右下表示用のジャケット（COVERノードのhandle優先、無ければ曲フォルダ内のカバーファイル）
let _coverURL=null, _coverKey='';
async function updateCoverThumb(){
  const img=document.getElementById('siCover');
  const covN=extraNodes.find(x=>x.kind==='cover'
    &&graphEdges.some(e2=>e2.sig==='cover'&&e2.fromId===x.id&&e2.toId==='out'));   // OUTPUTへ配線中のみ有効
  const fname=covN?(covN.name||''):'';
  const key=covN?(covN.handle?'h:'+covN.name:'f:'+fname):'';
  if(key===_coverKey) return;
  _coverKey=key;
  let file=null;
  try{
    if(covN&&covN.handle) file=await covN.handle.getFile();
    else if(fname&&files[fname.toLowerCase()]) file=files[fname.toLowerCase()];
  }catch(e){}
  if(_coverURL){ URL.revokeObjectURL(_coverURL); _coverURL=null; }
  if(file){ _coverURL=URL.createObjectURL(file); img.src=_coverURL; img.style.display=''; }
  else { img.removeAttribute('src'); img.style.display='none'; }
}
async function openCoverFile(n){
  let fh;
  _pickOpen='cover:'+n.id;
  try{ [fh]=await showOpenFilePicker({id:'nlm-cover',types:[{description:'カバー画像',accept:{'image/*':['.png','.jpg','.jpeg','.webp','.gif','.bmp']}}]}); }
  catch(e){ _pickOpen=null; return; }
  _pickOpen=null;
  n.handle=fh; n.name=fh.name; metaDirty=true;
  _coverKey=''; updateCoverThumb();
  showOk(tf('msg.coverSet','カバー画像を設定: {name}（書き出し時に曲フォルダへコピーされます）',{name:fh.name}));
}
const EN_FIELDS={
  info:[['_songName','曲名（songName）'],['_songSubName','サブタイトル（songSubName）'],
        ['_songAuthorName','アーティスト（songAuthorName）'],['_levelAuthorName','譜面制作者（levelAuthorName）']],
  infoplus:[['_shuffle','shuffle'],['_shufflePeriod','shufflePeriod'],
        ['_previewStartTime','プレビュー開始秒（previewStartTime）'],['_previewDuration','プレビュー長さ秒（previewDuration）']],
  env:[['_environmentName','環境名（environmentName）']],
};
const EN_NUM=new Set(['_shuffle','_shufflePeriod','_previewStartTime','_previewDuration']);
function editExtraNode(n){
  const bg=document.getElementById('neBg'), box=document.getElementById('neFields');
  document.getElementById('neTitle').textContent=EN_DEF[n.kind].title;
  box.innerHTML='';
  for(const [key,label] of (EN_FIELDS[n.kind]||[])){
    const row=document.createElement('div'); row.className='irow';
    const lb=document.createElement('label'); lb.textContent=label;
    const inp=document.createElement('input'); inp.type='text'; inp.value=n.data[key]??'';
    inp.addEventListener('input',()=>{ let v=inp.value;
      if(EN_NUM.has(key)){ const num=parseFloat(v); if(!isFinite(num)) return; v=num; }
      n.data[key]=v; metaDirty=true; applyInfoChain(); });
    row.append(lb,inp); box.appendChild(row);
  }
  bg.style.display='flex';
}
// 拍数変更（ノードのlenを変更。経路上の後続は自動で前後にスライド）
function rippleSection(sec,newLen){
  if(!isFinite(newLen)||newLen<=0) return;
  graphOp(()=>{ sec.len=newLen; });
  stat(tf('msg.beatLenChange','「{label}」の拍数を {len} に変更（後続ノードは自動スライド）',{label:sec.label,len:newLen}));
}
// ノード削除（中身は経路上の前ノードへ統合。前が無ければ次ノードの先頭へ）
function removeNodeMerge(dead){
  const pn=sigPath('notes'), idx=pn.segs.findIndex(g=>g.sec===dead);
  const merge=(host,off)=>{
    const dc=dead.content||{}, hc=host.content=host.content||{};
    const mv=(key,bk)=>{ (dc[key]||[]).forEach(o=>{
      const o2={...o}; if(bk){ o2.b+=off; o2.tb+=off; } else o2.beat+=off;
      (hc[key]=hc[key]||[]).push(o2); }); };
    mv('notes');mv('bombs');mv('walls');mv('lights');mv('arcs',true);mv('chains',true);
  };
  if(idx>0){ const prev=pn.segs[idx-1].sec; merge(prev,prev.len); prev.len+=dead.len; }
  else { const pl=sigPath('lights'), li=pl.segs.findIndex(g=>g.sec===dead);
    if(li>0){ const prev=pl.segs[li-1].sec; merge(prev,prev.len); prev.len+=dead.len; }
    else { // 先頭ノード: 次ノードの先頭へ
      const nxtSeg=(idx>=0?pn.segs[idx+1]:null)||(li>=0?pl.segs[li+1]:null);
      if(nxtSeg){ const nxt=nxtSeg.sec, nc=nxt.content=nxt.content||{};
        for(const k of ['notes','bombs','walls','lights'])
          (nc[k]||[]).forEach(o=>o.beat+=dead.len);
        for(const k of ['arcs','chains'])
          (nc[k]||[]).forEach(o=>{ o.b+=dead.len; o.tb+=dead.len; });
        merge(nxt,0); nxt.len+=dead.len; } }
  }
  // 配線をブリッジして本体を除去
  for(const sig of ['notes','lights']){
    const inE=graphEdges.find(e=>e.sig===sig&&e.toId===dead.id);
    const outE=graphEdges.find(e=>e.sig===sig&&e.fromId===dead.id);
    graphEdges=graphEdges.filter(e=>e.fromId!==dead.id&&e.toId!==dead.id);
    if(inE&&outE) graphEdges.push({fromId:inE.fromId,toId:outE.toId,sig});
  }
  sections=sections.filter(x=>x!==dead);
}
function nodeAt(sx,sy){ const [wx,wy]=ndFromScreen(sx,sy);
  for(let i=sections.length-1;i>=0;i--){ const s2=sections[i]; const g=nodeGeomOf(s2.id); if(!g) continue;
    if(wx>=g.nx&&wx<=g.nx+g.w&&wy>=g.ny&&wy<=g.ny+g.h) return s2; } return null; }
function ioAt(sx,sy){ if(!graphIO) return null;
  const [wx,wy]=ndFromScreen(sx,sy);
  for(const k of ['in','out']){ const g=nodeGeomOf(k); if(!g) continue;
    if(wx>=g.nx&&wx<=g.nx+g.w&&wy>=g.ny&&wy<=g.ny+g.h) return k; } return null; }
function songAt(sx,sy){ if(!songNode) return null;
  const g=nodeGeomOf('song'); const [wx,wy]=ndFromScreen(sx,sy);
  return (wx>=g.nx&&wx<=g.nx+g.w&&wy>=g.ny&&wy<=g.ny+g.h)?songNode:null; }
ndcv.addEventListener('pointerdown', e=>{
  if(ndView!=='node') return;                 // レイヤービュー時はNODE操作を遮断
  const r=ndcv.getBoundingClientRect(), sx=e.clientX-r.left, sy=e.clientY-r.top;
  if(e.button===1&&!e.ctrlKey&&!e.altKey&&!e.metaKey){ e.preventDefault(); ndDrag={pan:{sx,sy,cx:ndCam.x,cy:ndCam.y}}; return; }
  if(e.button===2){
    { const alt=altAt(sx,sy);
      if(alt){ showMenu(e.clientX,e.clientY,[
          [t('ctx.selectLine','このラインを選択'),()=>activateLine(alt.uid)],
          [t('ctx.delNode','ノードを削除'),()=>{ graphOp(()=>{
            const id2=alt.side+'@'+alt.uid;
            graphEdges=graphEdges.filter(e2=>e2.fromId!==id2&&e2.toId!==id2);
            if(alt.side==='in') altIns=altIns.filter(n=>n.uid!==alt.uid);
            else if(alt.side==='out') altOuts=altOuts.filter(n=>n.uid!==alt.uid);
            else altSongs=altSongs.filter(n=>n.uid!==alt.uid); }); }],
        ]); return; } }
    const exN=extraAt(sx,sy);
    if(exN){ showMenu(e.clientX,e.clientY,[
        [exN.kind==='metro'?t('ctx.metroToggle','ON / OFF 切替'):exN.kind==='cover'?t('ctx.selImage','画像を選択…'):t('ctx.edit','編集…'),
          ()=>{ exN.kind==='metro'?(exN.data.on=exN.data.on?0:1,metaDirty=true)
            :exN.kind==='cover'?openCoverFile(exN):editExtraNode(exN); }],
        [t('ctx.delNode','ノードを削除'),()=>{ graphOp(()=>{
          graphEdges=graphEdges.filter(e2=>e2.fromId!==exN.id&&e2.toId!==exN.id);
          extraNodes=extraNodes.filter(x=>x!==exN); }); }],
      ]); return; }
    const s=nodeAt(sx,sy);
    if(!s){ // 空きスペース: 新規ノード
      const [wx,wy]=ndFromScreen(sx,sy);
      showMenu(e.clientX,e.clientY,[
        [t('ctx.addSheet','＋ Sheet ノード（譜面・8小節）'),()=>graphOp(()=>{
          sections.push({id:'n'+(++_nid)+Math.random().toString(36).slice(2,6),
            beat:99999+sections.length,label:'Sheet',len:32,content:{},nx:wx,ny:wy}); })],
        [t('ctx.addNull','＋ Null ノード（空白スペーサー・8小節）'),()=>graphOp(()=>{
          sections.push({id:'n'+(++_nid)+Math.random().toString(36).slice(2,6),
            beat:99999+sections.length,label:'NULL',kind:'null',len:32,content:{},nx:wx,ny:wy}); })],
        [t('ctx.addMusic','＋ Music ノード'),()=>{ if(songNode){ showErr('Musicノードは既にあります'); return; }
          songNode={nx:wx,ny:wy,name:''}; songDeleted=false; metaDirty=true; }],
        [t('ctx.addInfo','＋ Info ノード'),()=>{ createExtra('info',wx,wy); }],
        [t('ctx.addCover','＋ Cover ノード'),()=>{ createExtra('cover',wx,wy); }],
        [t('ctx.addMetro','＋ Metronome ノード（拍打ち確認用）'),()=>{ createExtra('metro',wx,wy); }],
        [t('ctx.addInput','＋ Input ノード'),()=>{ altIns.push({uid:'L'+(++_nid),nx:wx,ny:wy,bpm:BPM}); metaDirty=true; }],
        [t('ctx.addOutput','＋ Output ノード'),()=>{ altOuts.push({uid:'L'+(++_nid),nx:wx,ny:wy,diffs:{}}); metaDirty=true; }],
      ]); return; }
    { const [b0,b1]=sectionRange(s);
      showMenu(e.clientX,e.clientY,[
        [tf('ctx.dupToPlayhead','複製 → 再生ヘッド(拍{beat})へ',{beat:snapV(cur)}),()=>{
          const frag=extractRegion(b0,b1); const at=snapV(cur);
          pasteFragment(frag,at); metaDirty=true; }],
        [tf('ctx.changeBeatLen','拍数を変更（現在 {len} 拍・以降をリップル）',{len:b1-b0}),()=>{
          const v=parseFloat(prompt('このノードの拍数',b1-b0));
          if(isFinite(v)&&v>0) rippleSection(s,v); }],
        [t('ctx.mirror','ミラー（左右+色反転）'),()=>mirrorRegion(b0,b1)],
        [t('ctx.delContents','中身を削除'),()=>deleteRegionContents(b0,b1)],
        [t('ctx.delNodeMerge','ノードを削除（中身は前に統合）'),()=>{ graphOp(()=>removeNodeMerge(s)); stat(tf('msg.mergedLabel','「{label}」を統合しました',{label:s.label})); }],
      ]); }
    return; }
  if(e.button===0&&e.shiftKey){ ndBoxSel={x0:sx,y0:sy,x1:sx,y1:sy}; return; }   // Shift+左ドラッグ=範囲選択
  if(e.button===0){
    for(const wd of _ndWidgets){
      if(sx>=wd.x&&sx<=wd.x+wd.w&&sy>=wd.y&&sy<=wd.y+wd.h){
        { const io0=ioAt(sx,sy), s0=nodeAt(sx,sy), sn0=songAt(sx,sy), ex0=extraAt(sx,sy);   // ウィジェット操作でも選択は立てる
          ndSel=io0||(s0&&s0.id)||(sn0?'song':null)||(ex0&&ex0.id)||ndSel; }
        wd.act(e,wd); return; } }
    { const rz=resizeAt(sx,sy);              // 右下の端 = 幅リサイズ
      if(rz){ ndDrag={rz}; return; } }
    const ph=portHit(sx,sy);                 // ポート: クリック=切断 / ドラッグ=付け替え
    if(ph){
      wireDrag={...ph, sx, sy, armed:true};  // まだ何も変更しない（動いたらドラッグ、動かなければクリック）
      return;
    }
    if(e.ctrlKey){                           // 配線の切断は Ctrl+左クリック（誤クリック防止）
      const eh=edgeHit(sx,sy);
      if(eh){ graphOp(()=>{ graphEdges=graphEdges.filter(e2=>e2!==eh); });
        stat(tf('msg.wireUnplug','{sig}の配線をはがしました',{sig:SIG_NAME[eh.sig]})); return; } }
    if(ndMultiSel.size){                     // 複数選択中: 選択ノードを掴んだら一括移動
      const s0=nodeAt(sx,sy), io0=ioAt(sx,sy), sn0=songAt(sx,sy), ex0=extraAt(sx,sy), alt0=altAt(sx,sy);
      const hitId=(s0&&s0.id)||io0||(sn0?'song':null)||(ex0&&ex0.id)||(alt0?alt0.side+'@'+alt0.uid:null);
      if(hitId&&ndMultiSel.has(hitId)){
        const [wx,wy]=ndFromScreen(sx,sy), multi=[];
        for(const id of ndMultiSel){ const g=nodeGeomOf(id); if(g) multi.push({base:g.base,ox:wx-g.nx,oy:wy-g.ny}); }
        ndDrag={multi}; return; }
      ndMultiSel.clear();                    // 選択外をクリック = 複数選択を解除
    }
    const s=nodeAt(sx,sy);
    if(s){ const [wx,wy]=ndFromScreen(sx,sy); ndSel=s.id; ndDrag={sec:s,ox:wx-s.nx,oy:wy-s.ny}; return; }
    const io=ioAt(sx,sy);
    if(io){ const [wx,wy]=ndFromScreen(sx,sy); ndSel=io;
      ndDrag={io,ox:wx-graphIO[io].nx,oy:wy-graphIO[io].ny}; return; }
    const sn=songAt(sx,sy);
    if(sn){ const [wx,wy]=ndFromScreen(sx,sy); ndSel='song';
      ndDrag={song:true,ox:wx-songNode.nx,oy:wy-songNode.ny}; return; }
    const ex=extraAt(sx,sy);
    if(ex){ const [wx,wy]=ndFromScreen(sx,sy); ndSel=ex.id;
      ndDrag={ex,ox:wx-ex.nx,oy:wy-ex.ny}; return; }
    { const alt=altAt(sx,sy);                    // 濃灰ノード = クリックでこのラインを選択
      if(alt){ const side=alt.side; activateLine(alt.uid);
        const [wx,wy]=ndFromScreen(sx,sy);
        if(side==='in'||side==='out'){ ndSel=side;
          ndDrag={io:side,ox:wx-graphIO[side].nx,oy:wy-graphIO[side].ny}; }
        else if(songNode){ ndSel='song'; ndDrag={song:true,ox:wx-songNode.nx,oy:wy-songNode.ny}; }
        return; } }
    ndSel=null;                                  // 空きスペース = 選択解除
  }
});
function extraAt(sx,sy){ const [wx,wy]=ndFromScreen(sx,sy);
  for(let i=extraNodes.length-1;i>=0;i--){ const n=extraNodes[i]; const g=nodeGeomOf(n.id); if(!g) continue;
    if(wx>=g.nx&&wx<=g.nx+g.w&&wy>=g.ny&&wy<=g.ny+g.h) return n; } return null; }
ndcv.addEventListener('pointermove', e=>{
  if(ndView!=='node') return;                 // レイヤービュー時はNODE操作を遮断
  const r0=ndcv.getBoundingClientRect(), msx=e.clientX-r0.left, msy=e.clientY-r0.top;
  _ndMouse=ndFromScreen(msx,msy);
  if(ndBoxSel){ ndBoxSel.x1=msx; ndBoxSel.y1=msy; return; }
  if(!ndDrag&&!wireDrag) ndcv.style.cursor=resizeAt(msx,msy)?'nwse-resize':'';
  if(wireDrag){
    if(wireDrag.armed&&((msx-wireDrag.sx)**2+(msy-wireDrag.sy)**2>36)){
      // ドラッグ開始が確定 → トランザクション開始
      wireDrag.armed=false; wireDrag.live=true;
      snapshot('node'); syncGraphFromFlat();
      // 既存線が刺さっているポートを掴んだ場合は、その線を外して反対側の端を持つ
      if(wireDrag.side==='in'){                 // 入力ポート: 既存1本を掴んで付け替え
        const ex=graphEdges.find(e2=>e2.sig===wireDrag.sig&&e2.toId===wireDrag.nodeId);
        if(ex){ graphEdges=graphEdges.filter(e2=>e2!==ex); wireDrag.side='out'; wireDrag.nodeId=ex.fromId; }
      }                                          // 出力ポート: 既存は掴まず新規線（fan-out）
    }
    return;                                  // ラバーバンドは描画側が追従
  }
  if(!ndDrag) return;
  const r=ndcv.getBoundingClientRect(), sx=e.clientX-r.left, sy=e.clientY-r.top;
  if(ndDrag.pan){ ndCam.x=ndDrag.pan.cx-(sx-ndDrag.pan.sx)/ndCam.scale;
    ndCam.y=ndDrag.pan.cy-(sy-ndDrag.pan.sy)/ndCam.scale; }
  else if(ndDrag.multi){ const [wx,wy]=ndFromScreen(sx,sy);
    for(const m of ndDrag.multi){ m.base.nx=wx-m.ox; m.base.ny=wy-m.oy; } metaDirty=true; }
  else if(ndDrag.sec){ const [wx,wy]=ndFromScreen(sx,sy);
    ndDrag.sec.nx=wx-ndDrag.ox; ndDrag.sec.ny=wy-ndDrag.oy; metaDirty=true; }
  else if(ndDrag.io){ const [wx,wy]=ndFromScreen(sx,sy);
    graphIO[ndDrag.io].nx=wx-ndDrag.ox; graphIO[ndDrag.io].ny=wy-ndDrag.oy; metaDirty=true; }
  else if(ndDrag.song){ const [wx,wy]=ndFromScreen(sx,sy);
    songNode.nx=wx-ndDrag.ox; songNode.ny=wy-ndDrag.oy; metaDirty=true; }
  else if(ndDrag.ex){ const [wx,wy]=ndFromScreen(sx,sy);
    ndDrag.ex.nx=wx-ndDrag.ox; ndDrag.ex.ny=wy-ndDrag.oy; metaDirty=true; }
  else if(ndDrag.rz){ const [wx]=ndFromScreen(sx,sy);
    ndDrag.rz.w=Math.max(120,Math.min(560,Math.round(wx-ndDrag.rz.nx))); metaDirty=true; }
});
addEventListener('pointerup', e=>{
  if(ndBoxSel){                                  // 範囲選択を確定
    const r=ndcv.getBoundingClientRect();
    ndBoxSel.x1=e.clientX-r.left; ndBoxSel.y1=e.clientY-r.top;
    const [ax,ay]=ndFromScreen(Math.min(ndBoxSel.x0,ndBoxSel.x1),Math.min(ndBoxSel.y0,ndBoxSel.y1));
    const [bx,by]=ndFromScreen(Math.max(ndBoxSel.x0,ndBoxSel.x1),Math.max(ndBoxSel.y0,ndBoxSel.y1));
    ndMultiSel.clear();
    for(const id of allNodeIds()){ const g=nodeGeomOf(id); if(!g) continue;
      if(g.nx<bx&&g.nx+g.w>ax&&g.ny<by&&g.ny+g.h>ay) ndMultiSel.add(id); }   // 矩形と重なったノードを選択
    ndSel=ndMultiSel.size===1?[...ndMultiSel][0]:null;
    ndBoxSel=null;
    if(ndMultiSel.size>1) stat(tf('msg.multiNodeSel','{n}個のノードを選択しました（ドラッグで一括移動 / X・Delで一括削除）',{n:ndMultiSel.size}));
    return;
  }
  if(wireDrag){
    if(wireDrag.armed){                      // 動かさず離した = クリック → その口の線を切断
      const wd=wireDrag; wireDrag=null;
      const kill=wd.side==='in'
        ? graphEdges.filter(e2=>e2.sig===wd.sig&&e2.toId===wd.nodeId)
        : graphEdges.filter(e2=>e2.sig===wd.sig&&e2.fromId===wd.nodeId);   // 出力は全fan-out線
      if(kill.length){ graphOp(()=>{ graphEdges=graphEdges.filter(e2=>!kill.includes(e2)); });
        stat(tf('msg.wireUnplugN','{sig}の配線を{cnt}はがしました',{sig:SIG_NAME[wd.sig],cnt:kill.length>1?kill.length+'本':''})); }
      return;
    }
    // ドラッグ確定分（トランザクション中）: 有効ポートに落ちれば接続、外せばそのまま切断
    const r=ndcv.getBoundingClientRect(), sx=e.clientX-r.left, sy=e.clientY-r.top;
    const ph=portHit(sx,sy);
    if(ph&&ph.sig===wireDrag.sig&&ph.side!==wireDrag.side){
      const fromId=wireDrag.side==='out'?wireDrag.nodeId:ph.nodeId;
      const toId  =wireDrag.side==='out'?ph.nodeId:wireDrag.nodeId;
      const audioOK=wireDrag.sig!=='audio'
        ||(fromId.startsWith('in')&&toId.startsWith('song'))||(fromId.startsWith('song')&&toId.startsWith('out'));
      if(!fromId.startsWith('out')&&!toId.startsWith('in')&&fromId!==toId&&audioOK){
        graphEdges=graphEdges.filter(e2=>!(e2.sig===wireDrag.sig&&e2.toId===toId));   // 入力ポートは1本のみ・出力はfan-out可
        graphEdges.push({fromId,toId,sig:wireDrag.sig});
        stat(tf('msg.wireConnect','{sig}を接続しました',{sig:SIG_NAME[wireDrag.sig]}));
      } else if(!audioOK) showErr('音源はINPUT→SONG→OUTPUTの順にのみ接続できます');
    } else stat(tf('msg.wireUnplug','{sig}の配線をはがしました',{sig:SIG_NAME[wireDrag.sig]}));
    wireDrag=null;
    compileGraphToFlat(); metaDirty=true;
    return;
  }
  ndDrag=null;
});
ndcv.addEventListener('wheel', e=>{ e.preventDefault();
  if(ndView!=='node') return;                 // レイヤービュー時はNODEズームを遮断（レイヤー用wheelが処理）
  if(e.shiftKey&&!e.ctrlKey&&!e.altKey&&!e.metaKey){ tlScrub(e); return; }   // Shift+ホイール=タイムラインスクラブ（ズームではなく）
  if(e.ctrlKey||e.altKey||e.metaKey||e.shiftKey) return;   // 未設定の修飾+ホイールは無効
  const r=ndcv.getBoundingClientRect(), sx=e.clientX-r.left, sy=e.clientY-r.top;
  const [wx,wy]=ndFromScreen(sx,sy);
  ndCam.scale=Math.max(0.35,Math.min(2.5,ndCam.scale*(e.deltaY>0?0.9:1.11)));
  ndCam.x=wx-sx/ndCam.scale; ndCam.y=wy-sy/ndCam.scale;
},{passive:false});
ndcv.addEventListener('dblclick', e=>{
  if(ndView!=='node') return;                 // レイヤービュー時はNODE操作を遮断
  const r=ndcv.getBoundingClientRect(), sx=e.clientX-r.left, sy=e.clientY-r.top;
  const s=nodeAt(sx,sy);
  if(s){ const g=nodeGeomOf(s.id), wy=ndFromScreen(sx,sy)[1];
    if(wy<=g.ny+NHEAD+2){
      const [hx,hy]=ndToScreen(g.nx,g.ny), sc2=ndCam.scale;
      ndInlineEdit({x:hx+4,y:hy+2,w:g.w*sc2-8,h:NHEAD*sc2-4},s.label,nm=>{
        if(nm.trim()){ s.label=nm.trim(); metaDirty=true; } });
      return; }
    cur=s.beat; offset=beatToTimeTM(cur); stat(tf('msg.jumpToLabel','「{label}」へジャンプ',{label:s.label})); }
});
ndcv.addEventListener('contextmenu',e=>{ e.preventDefault();
  if(ndView!=='layers') return;
  if(layerPaste){ cancelLayerPaste(); return; }   // ゴースト追従中の右クリック=取消（メニューは出さない）
  const r=ndcv.getBoundingClientRect(), sx=e.clientX-r.left, sy=e.clientY-r.top;
  if(sy>=LRULER-MKRH-TPRH&&sy<LRULER-MKRH){              // テンポパート帯: 右クリック=追加/自動判定/手入力/削除
    const hit=_tpRects.find(r2=>sx>=r2.x&&sx<=r2.x+r2.w&&sy>=r2.y&&sy<=r2.y+r2.h);
    if(hit){ const p=tempoParts[hit.i];
      showMenu(e.clientX,e.clientY,[
        [t('ctx.tempoPartDetect','🎯 自動判定'),()=>autoDetectTempoPart(hit.i)],
        [t('ctx.tempoPartManual','BPMを手入力…'),()=>{ const v=prompt('BPM',String(p.bpm)); const n=parseFloat(v);
          if(isFinite(n)&&n>0) setTempoPartBpm(hit.i,n); }],
        [t('ctx.tempoPartDel','テンポパートを削除'),()=>delTempoPart(hit.i)],
      ]); }
    else showMenu(e.clientX,e.clientY,[
      [t('ctx.tempoPartAddHere','＋ 拍で指定'),()=>addTempoPartAt(lXToBeat(sx))],
      [t('ctx.tempoPartAddSec','＋ 秒で指定…'),()=>{ const sec=parseFloat(prompt('秒数')); if(isFinite(sec)&&sec>=0) addTempoPartAtSec(sec); }],
    ]);
    return; }
  if(sy>=LRULER-MKRH&&sy<LRULER){                        // マーカー帯: 右クリック=名前変更/削除
    const hit=_mkRects.find(r2=>sx>=r2.x&&sx<=r2.x+r2.w&&sy>=r2.y&&sy<=r2.y+r2.h)
      ||(()=>{ let best=null,bd=8;                       // ラベル外でも◆/ライン付近8pxなら拾う
        for(let i2=0;i2<markers.length;i2++){ const d=Math.abs(lBeatToX(markers[i2].beat)-sx); if(d<bd){ bd=d; best={i:i2}; } } return best; })();
    if(hit){ const mk=markers[hit.i];
      showMenu(e.clientX,e.clientY,[
        [t('ctx.rename','名前を変更…'),()=>{ const r2=_mkRects.find(q=>q.i===hit.i)||{x:sx,y:LRULER-MKRH+1,w:60};
          ndInlineEdit({x:r2.x-2,y:r2.y,w:Math.max(90,(r2.w||60)+24),h:MKRH-2},mk.name,v=>{ v=(v||'').trim();
            if(v){ mk.name=v; metaDirty=true; stat(tf('msg.markerName','マーカー名: {name}',{name:v})); } },false,ndcv); }],
        [t('ctx.mkToPreview','▶ プレビュー開始に転送'),()=>{ const sec=Math.max(0,Math.round(beatToTimeTM(mk.beat)*100)/100);   // マーカー拍→秒（audio時間）をプレビュー開始へ
          infoBase=infoBase||{}; infoBase._previewStartTime=sec; applyInfoChain(); metaDirty=true; if(typeof refreshMusicHdr==='function') refreshMusicHdr();
          stat(tf('msg.mkToPreview','プレビュー開始を {sec}秒 に設定（マーカー「{name}」）',{sec,name:mk.name})); }],
        [t('ctx.delMarker','マーカーを削除'),()=>{ snapshot('node'); markers.splice(hit.i,1); metaDirty=true; stat('マーカーを削除しました'); }],
      ]); }
    return; }
  if(sx<LGUT&&sy>=LRULER){   // 溝: レーンの追加/削除（下=1固定・増減は一番上のレーン。各グループ最大LANE_MAX本）
    const la=laneAtY(sy), grpName=la.lk==='n'?t('word.notes','ノーツ'):t('word.light','ライト');
    showMenu(e.clientX,e.clientY,[
      ...markerMenuTop(),
      [tf('ctx.laneAdd','＋ {grp}レーンを追加（一番上に）',{grp:grpName}),()=>{
        if(laneCountOf(la.lk)>=LANE_MAX){ showErr(tf('msg.laneMax','{grp}レーンは最大{max}本です',{grp:grpName,max:LANE_MAX})); return; }
        snapshot('node'); if(la.lk==='n') notesLanes++; else lightLanes++;
        laneShiftAll(la.lk,1);   // 既存クリップは番号維持のまま1段下がる（=下1固定・上に空きレーン）
        metaDirty=true; stat(tf('msg.laneAdded','{grp}レーンを追加しました（{n}本）',{grp:grpName,n:laneCountOf(la.lk)})); }],
      [tf('ctx.laneDel','－ {grp}レーンを削除（一番上・空のみ）',{grp:grpName}),()=>{
        const N=laneCountOf(la.lk); if(N<=1){ showErr('レーンは最低1本必要です'); return; }
        if(sections.some(s2=>secLk(s2)===la.lk&&(s2.track||0)===0)){ showErr('一番上のレーンにクリップがあるため削除できません'); return; }
        { const curK=(currentDiffName||'').toLowerCase(); let hit=null;   // レーン数は全難易度共通なので他難易度の一番上も確認
          for(const k in projDiffs){ if(k===curK) continue; const st=projDiffs[k];
            if(st&&(st.sections||[]).some(s2=>secLk(s2)===la.lk&&(s2.track||0)===0)){ hit=st.name||k; break; } }
          if(hit){ showErr(tf('msg.laneTopOtherDiff','一番上のレーンに他の難易度（{diff}）のクリップがあるため削除できません',{diff:dispDiff(String(hit).replace(/Standard\.dat$/i,''))})); return; } }
        snapshot('node'); if(la.lk==='n') notesLanes--; else lightLanes--;
        laneShiftAll(la.lk,-1);
        setScr(la.lk,scrOf(la.lk)); metaDirty=true;
        stat(tf('msg.laneDeleted','{grp}レーンを削除しました（{n}本）',{grp:grpName,n:laneCountOf(la.lk)})); }],
    ]); return; }
  if(sx<LGUT||sy<LRULER) return;
  const s=clipAtLayer(sx,sy);
  if(s){                                                   // クリップ上: ラベル変更 / 色変更 / 削除
    showMenu(e.clientX,e.clientY,[
      [t('ctx.editLabel','ラベルを変更…'),()=>{ const lh=laneHt(), t=s.track||0, x=lBeatToX(s.beat||0), w=(s.len||4)*lPPB(), y=LRULER+t*lh+4;
        const gx=Math.max(LGUT,x);
        ndInlineEdit({x:gx+2,y,w:Math.min(x+w,ndW)-gx-4,h:16},s.label||'',nm=>{
          if(nm.trim()){ snapshot('node'); if(!s.gid) s.gid='g'+(++_nid); const r0=clipRef(s);
            s.label=nm.trim(); metaDirty=true; } }); }],
      [t('ctx.editColor','色を変更…'),()=>{ ndColorEdit(stripColOf(s),hex=>{ snapshot('node'); if(!s.gid) s.gid='g'+(++_nid);
          s.colHex=hex; metaDirty=true; },{x:sx,y:sy,h:0}); }],   // ヘッダーの色スウォッチと同じピッカー
      ['---'],
      [t('ctx.mirrorClip','左右反転'),()=>mirrorClip(s)],   // クリップの中身を左右ミラー＋色反転
      ['---'],
      [t('ctx.cutByMarkers','マーカーでカット'),()=>cutClipAtMarkers(s)],   // クリップ内の全マーカー拍で分割
      ['---'],
      [tf('ctx.saveAsset','📦 アセットへ保存（{type}）',{type:secLk(s)==='l'?'LIGHT':'NOTES'}),()=>saveClipToAsset(s)],   // クリップを .nlmclip 部品として保存
      [t('ctx.delClip','クリップを削除'),()=>{ layerSel=new Set([s.id]); deleteLayerSel(); }],
    ]);
  } else {                                                 // 空き: その位置に空のシートを作成（レーン種のクリップになる）
    const beat=Math.max(0,snapV(lXToBeat(sx))), la=laneAtY(sy);
    showMenu(e.clientX,e.clientY,[
      ...markerMenuTop(),
      [tf('ctx.newEmptyClip','＋ 空のクリップを作成（{lane}・拍 {beat}）',{lane:laneLabel(la.lk,la.gi),beat}),()=>{
        if(laneOverlaps(beat,16,la.lk,la.gi)){ showErr('この位置は既存クリップと重なります（同じレーン内では重ねられません）'); return; }
        snapshot('node');
        const sec={id:'n'+(++_nid)+Math.random().toString(36).slice(2,6),beat,track:la.gi,lk:la.lk,col:pickStripCol(),label:'Sheet',len:16,kind:'sheet',content:{}};
        sections.push(sec);
        relinkDiffEdges(); layerSel=new Set([sec.id]);
        compileLayersToFlat(); metaDirty=true; stat('空のクリップを作成しました'); }],
    ]);
  }
});

// ============ フェーズ1: レイヤービュー（NLEタイムライン・表示/ナビのみ・非破壊） ============
const LGUT=TLGUT, MKRH=16, TPRH=14, LRULER=22+MKRH+TPRH, LANE_MAX=10, LDIV=3;   // MKRH=マーカー帯・TPRH=テンポパート帯。LDIV=グループ間の継ぎ目(Notes/Light・Light/Music共通)
function laneDefN(){ try{ const n=parseInt(localStorage.getItem('bsnm_laneratio')); if(n>=1&&n<=5) return n; }catch(e){} return 4; }   // 個人の初期設定（ノーツ本数1〜5・計6）。無ければ4（＝4:2。ライトは縦軸が無くトラック少なめで足りる・ヘルバ様指定）
let notesLanes=laneDefN(), lightLanes=6-notesLanes;   // 上=NOTESグループ／下=LIGHTグループ（各1〜LANE_MAX本・プロジェクト保存）。既定=個人設定(bsnm_laneratio)、無ければ3:3
let laneScrN=0, laneScrL=0;       // グループごとの縦スクロール（Notes/Lightは別もの・Musicはスクロールなし）
function laneCount(){ return notesLanes+lightLanes; }
function secLk(s){ return s&&s.lk==='l'?'l':'n'; }
function laneCountOf(lk){ return lk==='l'?lightLanes:notesLanes; }
function rowOf(lk,gi){ return (lk==='l'?notesLanes:0)+gi; }   // 全レーン通しの行番号（3Dのボックス帯の並び等に使用）
function laneShiftAll(lk,d){   // レーン増減時: 全難易度のクリップ/フラットのレーン位置をずらす（下=1固定・増減は一番上）
  const apply=(secs,flats)=>{ for(const s2 of (secs||[])) if(secLk(s2)===lk) s2.track=Math.max(0,(s2.track||0)+d);
    for(const g of flats) if(g[1]===lk) for(const it of (g[0]||[])) it._tr=Math.max(0,(it._tr||0)+d); };
  apply(sections,[[notes,'n'],[bombs,'n'],[walls,'n'],[arcs,'n'],[chains,'n'],[lightEvents,'l']]);
  const curK=(currentDiffName||'').toLowerCase();
  for(const k in projDiffs){ if(k===curK) continue; const st=projDiffs[k]; if(!st) continue;
    apply(st.sections,[[st.notes,'n'],[st.bombs,'n'],[st.walls,'n'],[st.arcs,'n'],[st.chains,'n'],[st.lightEvents,'l']]); }
  layerSoloS.clear(); layerMuteS.clear();   // S/Mはレーン位置キーのため増減でリセット（誤ミュートの防止）
}
function laneHt(){ const total=Math.max(1,notesLanes+lightLanes);   // 合計6本以下: 隙間なくぴったり埋める（レーンを太く）／7本以上: 6本ぶんの固定厚でスクロール
  return Math.max(34,(ndH-LRULER-2*LDIV)/Math.min(6,total)); }   // 継ぎ目はNotes/Light間と最下部(Light/Music間)の2本ぶん確保
function laneVP(lk){ const avail=ndH-LRULER-2*LDIV, total=Math.max(1,notesLanes+lightLanes);
  return Math.max(34, avail*laneCountOf(lk)/total); }   // 各グループの表示窓=レーン数に比例（合計avail）→区切り線が比率で動く。計6ならぴったり埋まる
function laneTopOf(lk){ return LRULER+(lk==='l'?laneVP('n')+LDIV:0); }
function scrOf(lk){ return lk==='l'?laneScrL:laneScrN; }
function setScr(lk,v){ v=Math.max(0,Math.min(laneMaxScroll(lk),Math.round(v)));
  if(lk==='l') laneScrL=v; else laneScrN=v; }
function laneMaxScroll(lk){ return Math.max(0,Math.ceil(laneCountOf(lk)*laneHt()-laneVP(lk))); }
// レーン増減ヘルパー（溝右クリックメニューと設定スライダーで共用）。一番上に追加/一番上の空を削除。
function laneAdd(lk){ if(laneCountOf(lk)>=LANE_MAX) return false;
  if(lk==='n') notesLanes++; else lightLanes++; laneShiftAll(lk,1); return true; }
function laneRemove(lk){ if(laneCountOf(lk)<=1) return false;   // 一番上=空のみ（全難易度で確認）
  if(sections.some(s2=>secLk(s2)===lk&&(s2.track||0)===0)) return false;
  const curK=(currentDiffName||'').toLowerCase();
  for(const k in projDiffs){ if(k===curK) continue; const st=projDiffs[k];
    if(st&&(st.sections||[]).some(s2=>secLk(s2)===lk&&(s2.track||0)===0)) return false; }
  if(lk==='n') notesLanes--; else lightLanes--; laneShiftAll(lk,-1); setScr(lk,scrOf(lk)); return true; }
function setLaneRatio(n){   // 設定スライダー: ノーツn本 : ライト(6-n)本（計6固定）
  n=Math.max(1,Math.min(5,n)); const l=6-n;
  if(notesLanes===n&&lightLanes===l) return;
  snapshot('node'); let ok=true;
  while(ok&&notesLanes<n) ok=laneAdd('n');
  while(ok&&notesLanes>n) ok=laneRemove('n');
  while(ok&&lightLanes<l) ok=laneAdd('l');
  while(ok&&lightLanes>l) ok=laneRemove('l');
  metaDirty=true;
  { const el=document.getElementById('laneRatio'), lv=document.getElementById('laneRatioVal');
    if(el) el.value=notesLanes; if(lv) lv.textContent=notesLanes+' : '+lightLanes; }
  if(!ok) showErr('一番上のレーンにクリップがあるため、その比率にできません（空にしてから再度）');
  else showOk(tf('msg.laneLayout','レーン構成: ノーツ{notes} : ライト{lights}',{notes:notesLanes,lights:lightLanes})); }
function laneY(lk,gi){ return laneTopOf(lk)-scrOf(lk)+gi*laneHt(); }
function laneAtY(y){ const H=laneHt();
  if(y<laneTopOf('l')-LDIV/2){ const yy=y-laneTopOf('n')+laneScrN;
    return {lk:'n',gi:Math.max(0,Math.min(notesLanes-1,Math.floor(yy/H)))}; }
  const yy=y-laneTopOf('l')+laneScrL;
  return {lk:'l',gi:Math.max(0,Math.min(lightLanes-1,Math.floor(yy/H)))}; }
function laneLabel(lk,gi){ return (lk==='l'?'Light ':'Notes ')+(laneCountOf(lk)-gi); }   // 番号は下が1（旧Layer表記と同じ・ヘルバ様指定）
function hueOf(id){ let h=0; const s=String(id); for(let i=0;i<s.length;i++) h=(h*31+s.charCodeAt(i))>>>0; return h%360; }
// クリップ色はBlenderテーマ(DarkPurpleGreen)のstrip_colorパレット。作成時に「最も使われていない色」を割当（s.colに保存）
const STRIP_COLS=['#e2605b','#f1a355','#f1dc55','#7bcc7b','#5db6ea','#8d59da','#c673b8','#7a5441'];
function stripColOf(s){ if(s&&typeof s==='object'){
    if(s.colHex) return s.colHex;   // スウォッチで指定した任意色が最優先
    return STRIP_COLS[((s.col!=null)?s.col:hueOf(s.id)%STRIP_COLS.length)%STRIP_COLS.length]; }   // 旧データ(col無し)はハッシュにフォールバック
  return STRIP_COLS[hueOf(s)%STRIP_COLS.length]; }
function pickStripCol(){   // 現在のタイムラインで使用数が最少の色（連続ドロップで同色が続かない）
  const cnt=new Array(STRIP_COLS.length).fill(0);
  for(const s of sections){ const c=((s.col!=null)?s.col:hueOf(s.id)%STRIP_COLS.length)%STRIP_COLS.length; cnt[c]++; }
  let best=0; for(let i=1;i<cnt.length;i++) if(cnt[i]<cnt[best]) best=i;
  return best; }
function hexA(hex,a){ const n=parseInt(hex.slice(1),16); return `rgba(${(n>>16)&255},${(n>>8)&255},${n&255},${a})`; }
// レイヤービューは下段Musicと同じ時間窓(tlWindow)を共有＝再生で全部連動。pxb/原点は窓から導出
function lPPB(){ return (ndW-LGUT)/tlWindow(cur).span; }
function lBeatToX(b){ const w=tlWindow(cur); return LGUT+(b-w.b0)/w.span*(ndW-LGUT); }
function lXToBeat(x){ const w=tlWindow(cur); return w.b0+(x-LGUT)/(ndW-LGUT)*w.span; }
function layerFit(){ tlSpan=Math.max(32,Math.ceil(tlEnd())); }   // 全長（最後尾ボックス+4拍）にフィット。最低8小節=32拍
// キャンバス用 notes/light アイコン（MEDIAサムネのLIB_CLIP_*_ICOと同じ意匠を縮小描画）
function drawNoteIco(g,x,y,s){ const q=(s-1)/2;   // 赤青4ブロック
  g.fillStyle='#e0355a'; g.fillRect(x,y,q,q); g.fillRect(x+q+1,y+q+1,q,q);
  g.fillStyle='#2f6fe0'; g.fillRect(x+q+1,y,q,q); g.fillRect(x,y+q+1,q,q); }
function drawLightIco(g,x,y,s){ g.fillStyle='#ffd82d';   // 黄の横バー3本
  const h=Math.max(1,Math.round(s*0.2)), gap=(s-3*h)/2;
  g.fillRect(x,y,s,h); g.fillRect(x,y+h+gap,Math.round(s*0.82),h); g.fillRect(x,y+2*(h+gap),Math.round(s*0.6),h); }
function roundRectND(x,y,w,h,r){ if(typeof r==='number') r=[r,r,r,r];
  ndg.beginPath(); ndg.moveTo(x+r[0],y); ndg.lineTo(x+w-r[1],y); ndg.arcTo(x+w,y,x+w,y+r[1],r[1]);
  ndg.lineTo(x+w,y+h-r[2]); ndg.arcTo(x+w,y+h,x+w-r[2],y+h,r[2]); ndg.lineTo(x+r[3],y+h);
  ndg.arcTo(x,y+h,x,y+h-r[3],r[3]); ndg.lineTo(x,y+r[0]); ndg.arcTo(x,y,x+r[0],y,r[0]); ndg.closePath(); }
function drawLayers(curV){
  if(curV===undefined) curV=cur;   // 再生中はtickから音声遅延補正済みの拍(curV)が渡る＝下段Music/Notesと完全一致
  if(!ndW) return;
  flushFlatEdits();   // 3D(NOTES/LIGHT)の編集をクリップcontentへ確定してから描画＝ミニロールが即追従・他操作でrevertしない
  ndg.clearRect(0,0,ndW,ndH);
  const laneH=laneHt();
  for(const g of ['n','l']){ ndg.save(); ndg.beginPath(); ndg.rect(0,laneTopOf(g),ndW,laneVP(g)); ndg.clip();
    for(let i=0;i<laneCountOf(g);i++){ ndg.fillStyle=i%2?'#191919':'#1d1d1d'; ndg.fillRect(0,laneY(g,i),ndW,laneH); }
    ndg.restore(); }
  ndg.fillStyle='#1d1d1d'; ndg.fillRect(0,0,ndW,LRULER);   // ルーラー帯（テーマscrubbing back相当。レーンはスクロールでこの下に潜る）
  const _W=tlWindow(curV), PPB=(ndW-LGUT)/_W.span; const b0=Math.floor(_W.b0), b1=Math.ceil(_W.b0+_W.span);
  ndg.fillStyle='#191919'; ndg.fillRect(0,LRULER-MKRH,ndW,MKRH);     // マーカー帯（数字の下＝拍番号に被らない）
  ndg.strokeStyle='#161616'; ndg.lineWidth=1; ndg.beginPath(); ndg.moveTo(0,LRULER-MKRH+0.5); ndg.lineTo(ndW,LRULER-MKRH+0.5); ndg.stroke();
  const bx=b=>LGUT+(b-_W.b0)/_W.span*(ndW-LGUT);   // 描画は全てこの窓基準（curV）で統一
  // テンポパート帯（拍番号の下・マーカー帯の上）: 曲中のBPM変更ポイント。紫系でマーカー(白)と区別
  { const tpT=LRULER-MKRH-TPRH; ndg.fillStyle='#3a2c4a'; ndg.fillRect(0,tpT,ndW,TPRH);
    ndg.strokeStyle='#161616'; ndg.beginPath(); ndg.moveTo(0,tpT+0.5); ndg.lineTo(ndW,tpT+0.5); ndg.stroke();
    _tpRects.length=0;
    for(let pi=0;pi<tempoParts.length;pi++){ const p=tempoParts[pi], x=bx(p.beat); if(x<LGUT-2) continue;
      ndg.fillStyle='#e0b8ff'; ndg.beginPath(); ndg.moveTo(x,tpT); ndg.lineTo(x+4,tpT+TPRH/2); ndg.lineTo(x,tpT+TPRH); ndg.lineTo(x-4,tpT+TPRH/2); ndg.closePath(); ndg.fill();
      const lbl='♩'+Math.round(p.bpm), tw=ndg.measureText(lbl).width;
      ndg.font='9px '+FONT; ndg.textAlign='left'; ndg.textBaseline='middle'; ndg.fillStyle='#faf0ff';
      ndg.fillText(lbl,x+6,tpT+TPRH/2);
      _tpRects.push({i:pi,x:x-4,y:tpT,w:10+ndg.measureText(lbl).width,h:TPRH}); } }
  const numStep=PPB>=22?1:PPB>=11?2:4;   // 3D編集と同じ全拍番号。ズームアウト時のみ重ならないよう間引き
  if(snap<1&&snap*PPB>=4){   // スナップ分割の細線（3DのsubPool相当。間隔4px未満は省略）
    ndg.strokeStyle='#1e1e1e'; ndg.lineWidth=1;
    const i0=Math.ceil(_W.b0/snap);
    for(let i2=i0;i2*snap<_W.b0+_W.span;i2++){ const b=i2*snap;
      if(Math.abs(b-Math.round(b))<1e-6) continue;   // 整数拍は既存のラインが描く
      const x=bx(b); if(x<LGUT) continue;
      ndg.beginPath(); ndg.moveTo(x,LRULER); ndg.lineTo(x,ndH); ndg.stroke(); } }
  for(let b=b0;b<=b1;b++){ const x=bx(b); if(x<LGUT) continue;
    const bar=(b%4===0); ndg.strokeStyle=bar?'#2e2e2e':'#232323'; ndg.lineWidth=1;
    ndg.beginPath(); ndg.moveTo(x,LRULER); ndg.lineTo(x,ndH); ndg.stroke();
    if(b%numStep===0){ ndg.fillStyle=bar?'#8a8a8a':'#6f6f6f'; ndg.font='10px '+FONT; ndg.textAlign='center'; ndg.textBaseline='top'; ndg.fillText(String(b),x,2); } }
  _clipSw.length=0;
  for(const s of sections){ const lk=secLk(s), t=s.track||0; if(t>=laneCountOf(lk)) continue;   // 同レーンは重ならない設計＝描画順ソート不要（毎フレームの確保+sortを撤廃）
    ndg.save(); ndg.beginPath(); ndg.rect(LGUT,laneTopOf(lk),ndW-LGUT,laneVP(lk)); ndg.clip();   // 自グループの窓の外（スクロールで隠れた分）＋溝(トラックヘッド)には描かない
    ndg.globalAlpha=layerVisible(lk,t)?1:0.22;   // ミュート/ソロ非対象は薄く表示（3D側は非表示のまま）
    const x=bx(s.beat||0), w=(s.len||4)*PPB, y=laneY(lk,t)+4, h=laneH-8;
    if(x+w<LGUT||x>ndW){ ndg.restore(); continue; }
    const isNull=s.kind==='null', scol=stripColOf(s), sel=layerSel.has(s.id);
    // Musicボックスと同じインセット描画（+0.5/幅-1）: 枠線が箱の外へはみ出さない=隣接クリップと1pxも重ならない
    ndg.fillStyle=isNull?'#242424':hexA(scol,.14); roundRectND(x+0.5,y+0.5,w-1,h-1,6); ndg.fill();
    ndg.lineWidth=sel?2.4:1.2; ndg.strokeStyle=sel?'#ff8f0d':(isNull?'#4a4a4a':hexA(scol,.8)); ndg.stroke();
    ndg.fillStyle=isNull?'#333338':hexA(scol,.5); roundRectND(x+0.5,y+0.5,w-1,16,[6,6,0,0]); ndg.fill();
    ndg.save(); roundRectND(x+0.5,y+0.5,w-1,h-1,6); ndg.clip();   // 角丸パスでクリップ（四隅から中身がはみ出さない）
    if(!isNull){                                       // ラベル左の色スウォッチ（クリックでカラーピッカー）
      ndg.fillStyle=scol; ndg.beginPath(); ndg.roundRect(x+4,y+4,18,9,2); ndg.fill();
      ndg.strokeStyle='rgba(0,0,0,.5)'; ndg.lineWidth=1; ndg.stroke();
      _clipSw.push({id:s.id,x:x+3,y:y+3,w:20,h:11}); }
    ndg.fillStyle='#eafff5'; ndg.font='bold 10.5px '+FONT; ndg.textAlign='left'; ndg.textBaseline='middle';
    ndg.fillText(s.label||'Sheet',x+26,y+8);
    const cc=s.content||{}, nN=(cc.notes||[]).length+(cc.chains||[]).length+(cc.arcs||[]).length, nL=(cc.lights||[]).length, L=(s.len||4);   // カウントにチェーン/アークも含める
    // ヘッダー右: そのクリップ種別のカウントのみ（NOTESクリップ=ノーツ数／LIGHTクリップ=ライト数）＋種別アイコン
    if(!isNull&&w>96){ const isL=lk==='l', cnt=isL?nL:nN;
      ndg.fillStyle='#c8d8e2'; ndg.font='9px '+FONT; ndg.textAlign='right'; ndg.textBaseline='middle';
      ndg.fillText(String(cnt),x+w-6,y+8);
      const tw=ndg.measureText(String(cnt)).width, icoX=x+w-6-tw-4-8, icoY=y+8-4;   // 数字の左に8pxアイコン
      if(isL) drawLightIco(ndg,icoX,icoY,8); else drawNoteIco(ndg,icoX,icoY,8);
      ndg.textAlign='left'; }
    // 本体: 真上視点のミニロール（ノーツクリップ=4列フル高さ／ライトクリップ=10レーンフル高さ）
    const byTop=y+18, byH=h-21;
    if(!isNull&&byH>=10){
      if(lk==='n'){
        const laneNH=byH/4;
        for(let i=0;i<4;i++){ ndg.fillStyle=i%2?'rgba(255,255,255,.020)':'rgba(255,255,255,.045)';   // ノーツ4列の帯
          ndg.fillRect(x+2,byTop+i*laneNH,w-4,laneNH); }
        for(const o of (cc.walls||[])){ if((o.beat||0)>=L||(o.beat||0)<0) continue;        // 壁=列×長さ（真上視点そのもの）
          const wx0=Math.max(x+2,x+(o.beat||0)*PPB), wx1=Math.min(x+w-2,x+((o.beat||0)+(o.dur||0))*PPB);
          const c0=Math.max(0,Math.min(3,o.x||0)), cols=Math.max(1,Math.min(o.w||1,4-c0));
          ndg.fillStyle='rgba(208,48,96,.22)'; ndg.fillRect(wx0,byTop+c0*laneNH,Math.max(1.5,wx1-wx0),cols*laneNH); }
        for(const c3 of (cc.chains||[])){ const b0=c3.b||0; if(b0>=L||b0<0) continue;      // チェーン=頭チック＋尾チック＋頭→尾の斜線（真上視点。従来は未描画＝ヘルバ様指摘）
          const hx2=x+b0*PPB, tx2=x+Math.min(L,c3.tb??b0)*PPB;
          if(hx2<x-3||hx2>x+w) continue;
          const l0=Math.max(0,Math.min(3,c3.x||0)), l1=Math.max(0,Math.min(3,c3.tx||0));
          const col2=c3.c===0?cRED:cBLUE, ga=ndg.globalAlpha;
          ndg.save(); ndg.globalAlpha=ga*0.55; ndg.strokeStyle=col2; ndg.lineWidth=2;
          ndg.beginPath();
          ndg.moveTo(hx2+1.5, byTop+l0*laneNH+laneNH/2);
          ndg.lineTo(Math.min(x+w-2,tx2)+1, byTop+l1*laneNH+laneNH/2);
          ndg.stroke(); ndg.restore();
          ndg.fillStyle=col2;
          ndg.fillRect(hx2,byTop+l0*laneNH+0.8,3,Math.max(1.5,laneNH-1.6));                 // 頭（ノーツと同じ太さ）
          ndg.fillRect(Math.max(x+2,Math.min(x+w-3,tx2)),byTop+l1*laneNH+2,2,Math.max(1,laneNH-4)); }   // 尾（細め）
        for(const a3 of (cc.arcs||[])){ const ab0=a3.b||0; if(ab0>=L||ab0<0) continue;      // アーク=頭/尾を丸マーカー＋破線斜線（チェーンの実線+角チックと区別・ヘルバ様指定）
          const hx3=x+ab0*PPB, tx3=x+Math.min(L,a3.tb??ab0)*PPB;
          if(hx3<x-3||hx3>x+w) continue;
          const al0=Math.max(0,Math.min(3,a3.x||0)), al1=Math.max(0,Math.min(3,a3.tx||0));
          const col3=a3.c===0?cRED:cBLUE, ga3=ndg.globalAlpha;
          ndg.save(); ndg.globalAlpha=ga3*0.55; ndg.strokeStyle=col3; ndg.lineWidth=1.6; ndg.setLineDash([3,2]);
          ndg.beginPath();
          ndg.moveTo(hx3+1.5, byTop+al0*laneNH+laneNH/2);
          ndg.lineTo(Math.min(x+w-2,tx3)+1, byTop+al1*laneNH+laneNH/2);
          ndg.stroke(); ndg.setLineDash([]); ndg.restore();
          const rH=Math.max(1.5,laneNH-1.6)/2;
          ndg.fillStyle=col3;
          ndg.beginPath(); ndg.arc(hx3+1.5, byTop+al0*laneNH+laneNH/2, rH, 0, Math.PI*2); ndg.fill();               // 頭=丸（ノーツ/チェーンの角チックと区別）
          ndg.beginPath(); ndg.arc(Math.max(x+3,Math.min(x+w-3,tx3)), byTop+al1*laneNH+laneNH/2, rH*0.65, 0, Math.PI*2); ndg.fill(); }   // 尾=小さめの丸
        for(const n of (cc.notes||[])){ if((n.beat||0)>=L||(n.beat||0)<0) continue;        // ノーツ=列のみ（拍線=頭）
          const nx=x+(n.beat||0)*PPB, lane=Math.max(0,Math.min(3,n.x||0));
          if(nx<x-3||nx>x+w) continue;
          ndg.fillStyle=n.c===0?cRED:cBLUE;
          ndg.fillRect(nx,byTop+lane*laneNH+0.8,3,Math.max(1.5,laneNH-1.6)); }
        for(const n of (cc.bombs||[])){ if((n.beat||0)>=L||(n.beat||0)<0) continue;
          const nx=x+(n.beat||0)*PPB, lane=Math.max(0,Math.min(3,n.x||0));
          if(nx<x-3||nx>x+w) continue;
          ndg.fillStyle='#888899'; ndg.fillRect(nx,byTop+lane*laneNH+1.6,2,Math.max(1,laneNH-3.2)); }
      } else {
        const laneLH=byH/10, ltTop=byTop;
        for(const ev of (cc.lights||[])){ if((ev.beat||0)>=L||(ev.beat||0)<0) continue;    // ライト=3Dと同レーン順・チップ同色
          const li=laneIdxByType[ev.et]; if(li===undefined) continue;
          const nx=x+(ev.beat||0)*PPB; if(nx<x-3||nx>x+w) continue;
          ndg.fillStyle='#'+chipColorOf(ev.et,ev.i,evChroma(ev),boostStateAt(ev.beat)).toString(16).padStart(6,'0');
          ndg.fillRect(nx,ltTop+li*laneLH+0.3,2,Math.max(1,laneLH-0.6)); }
      }
    } else if(!isNull){
      const bars=(L/4), isL=lk==='l';
      ndg.fillStyle='#9fb8c8'; ndg.font='9px '+FONT; ndg.textAlign='left';
      const pre=`${(Math.round(bars*10)/10).toString().replace(/\.0$/,'')}小節 ・ `;   // クリップ種別のカウントのみ＋種別アイコン
      ndg.fillText(pre,x+6,y+24);
      const ix=x+6+ndg.measureText(pre).width, iy=y+24-7;
      if(isL) drawLightIco(ndg,ix,iy,8); else drawNoteIco(ndg,ix,iy,8);
      ndg.fillText(String(isL?nL:nN),ix+10,y+24);
    }
    ndg.restore(); ndg.restore(); }
  ndg.globalAlpha=1;
  // マーカー（白・全難易度共通）: 帯に◆+名前、細い白ラインをペイン下端まで（Musicレーン側はdrawOverviewが続きを描く）
  _mkRects.length=0;
  ndg.font='9.5px '+FONT; ndg.textBaseline='middle';
  const mkT=LRULER-MKRH;   // マーカー帯の上端（数字の下）
  for(let mi2=0;mi2<markers.length;mi2++){ const m=markers[mi2]; const x=bx(m.beat);
    if(x<LGUT-2||x>ndW+2) continue;
    ndg.strokeStyle='rgba(255,255,255,.4)'; ndg.lineWidth=1;
    ndg.beginPath(); ndg.moveTo(x+0.5,mkT); ndg.lineTo(x+0.5,ndH); ndg.stroke();
    ndg.fillStyle='#e8e8e8';
    ndg.beginPath(); ndg.moveTo(x,mkT+3.5); ndg.lineTo(x+4,mkT+MKRH/2); ndg.lineTo(x,mkT+MKRH-3.5); ndg.lineTo(x-4,mkT+MKRH/2); ndg.closePath(); ndg.fill();   // ◆
    const nm=m.name||('マーカー'+(mi2+1));
    ndg.textAlign='left'; const tw=ndg.measureText(nm).width;
    ndg.fillStyle='#c9c9c9'; ndg.fillText(nm,x+8,mkT+MKRH/2+0.5);
    _mkRects.push({i:mi2,x:x+6,y:mkT+1,w:tw+6,h:MKRH-2});
  }
  // MEDIAドラッグ中のゴーストクリップ（ホバー中のレーン種で中身が変わる。曲に現在の難易度が無ければ「？」）
  if(_dragMedia&&_mediaGhostNd){
    const gla=laneAtY(_mediaGhostNd.sy), glk=gla.lk;
    const clipLk=_dragMedia.isClip?(_dragMedia.clipType==='light'?'l':'n'):null;   // アセットクリップは種別レーンにしか置けない
    const laneBad=!!clipLk&&clipLk!==glk;                                          // 種別≠ドロップ先レーン＝不一致（NOTESクリップ→Light等）
    const invalid=_dragMedia._noDiff||laneBad;                                     // 不一致/難易度なし/音楽/画像＝画像1の赤ゴースト（ヘルバ様指定 2026-07-14）
    ndg.save(); ndg.beginPath(); ndg.rect(0,laneTopOf(glk),ndW,laneVP(glk)); ndg.clip();
    const gb=Math.max(0,snapV(lXToBeat(_mediaGhostNd.sx)));
    const gl=invalid?16:(_dragMedia._len||32), gx=bx(gb), gw=gl*PPB, gy=laneY(glk,gla.gi)+4, gh=laneH-8;
    // 枠色: 不可=赤／ライトレーン=黄／ノーツレーン=紫（ヘルバ様指示: Lightは黄色フレーム）
    const ghostAccent=invalid?'#e2605b':(glk==='l'?'#ffd82d':'#8160e3');
    const ghostFill=invalid?'rgba(226,96,91,.10)':(glk==='l'?'rgba(255,216,45,.12)':'rgba(129,96,227,.13)');
    ndg.fillStyle=ghostFill; roundRectND(gx,gy,gw,gh,6); ndg.fill();
    ndg.setLineDash([5,4]); ndg.strokeStyle=ghostAccent; ndg.lineWidth=1.5; ndg.stroke(); ndg.setLineDash([]);
    ndg.save(); roundRectND(gx,gy,gw,gh,6); ndg.clip();
    const fr=_dragMedia._frag;
    if(invalid){   // ドロップ不可（種別不一致 or 音楽ファイル or 現在の難易度が無い）→ 中央1行で案内（短いレーンでも縦に潰れない）
      const msg=_dragMedia.isImage?t('msg.imgToCoverShort','画像はカバー画像へ')
        :_dragMedia.isMusic?t('msg.dragMusicLane','音楽ファイルは Music レーンへ')
        :laneBad?(clipLk==='n'?t('msg.clipToNotes','NOTESクリップは NOTES レーンへ'):t('msg.clipToLight','LIGHTクリップは LIGHT レーンへ'))   // 種別不一致（ヘルバ様指定）
        :(glk==='l'?t('msg.noDiffLights','この難易度のライティングは含まれていません')
                   :t('msg.noDiffNotes','この難易度のノーツは含まれていません'));   // ドラッグ先レーン種でノーツ/ライティングを出し分け
      ndg.fillStyle='#e2605b'; ndg.textBaseline='middle'; ndg.textAlign='left';
      const qf=Math.min(15,Math.max(11,gh*0.5));
      ndg.font='bold '+qf+'px '+FONT; const qw=ndg.measureText('？').width;
      ndg.font='bold 10px '+FONT; const mw=ndg.measureText(msg).width;
      const total=qw+5+mw, x0=gx+Math.max(6,(gw-total)/2), cy=gy+gh/2;
      ndg.font='bold '+qf+'px '+FONT; ndg.fillText('？',x0,cy);
      ndg.font='bold 10px '+FONT; ndg.fillText(msg,x0+qw+5,cy);
    } else if(fr){ const bTop=gy+14, bH=gh-16;   // ノーツレーン=ノーツ4列／ライトレーン=ライト10レーン
      if(bH>=10&&glk==='n'){
        const laneNH=bH/4;
        for(const o of (fr.walls||[])){ if((o.beat||0)>=gl||(o.beat||0)<0) continue;
          const wx0=Math.max(gx+2,gx+(o.beat||0)*PPB), wx1=Math.min(gx+gw-2,gx+((o.beat||0)+(o.dur||0))*PPB);
          const c0=Math.max(0,Math.min(3,o.x||0)), cols=Math.max(1,Math.min(o.w||1,4-c0));
          ndg.fillStyle='rgba(208,48,96,.22)'; ndg.fillRect(wx0,bTop+c0*laneNH,Math.max(1.5,wx1-wx0),cols*laneNH); }
        for(const n2 of (fr.notes||[])){ if((n2.beat||0)>=gl||(n2.beat||0)<0) continue;
          const nx=gx+(n2.beat||0)*PPB, lane=Math.max(0,Math.min(3,n2.x||0));
          if(nx<gx-3||nx>gx+gw) continue;
          ndg.fillStyle=n2.c===0?cRED:cBLUE; ndg.fillRect(nx,bTop+lane*laneNH+0.8,3,Math.max(1.5,laneNH-1.6)); }
        for(const n2 of (fr.bombs||[])){ if((n2.beat||0)>=gl||(n2.beat||0)<0) continue;
          const nx=gx+(n2.beat||0)*PPB, lane=Math.max(0,Math.min(3,n2.x||0));
          if(nx<gx-3||nx>gx+gw) continue;
          ndg.fillStyle='#888899'; ndg.fillRect(nx,bTop+lane*laneNH+1.6,2,Math.max(1,laneNH-3.2)); }
      } else if(bH>=10){
        const laneLH=bH/10;
        for(const ev of (fr.lights||[])){ if((ev.beat||0)>=gl||(ev.beat||0)<0) continue;
          const li=laneIdxByType[ev.et]; if(li===undefined) continue;
          const nx=gx+(ev.beat||0)*PPB; if(nx<gx-3||nx>gx+gw) continue;
          ndg.fillStyle='#'+chipColorOf(ev.et,ev.i,evChroma(ev),boostStateAt(ev.beat)).toString(16).padStart(6,'0');
          ndg.fillRect(nx,bTop+li*laneLH+0.3,2,Math.max(1,laneLH-0.6)); }
      } }
    if(!invalid){   // 不可時は中央1行の案内のみ（上部ラベルと重ねない）
      ndg.fillStyle='#eafff5'; ndg.font='bold 10.5px '+FONT; ndg.textAlign='left'; ndg.textBaseline='middle';
      ndg.fillText((_dragMedia.name||'')+(glk==='n'?'（ノーツ）':'（ライト）'),gx+6,gy+8); }
    ndg.restore(); ndg.restore();
  }
  ndg.fillStyle='#212121'; ndg.fillRect(0,0,LGUT,ndH);
  _lgBtns.length=0;
  for(const row of [['n',notesLanes],['l',lightLanes]]){ const lk=row[0];
    ndg.save(); ndg.beginPath(); ndg.rect(0,laneTopOf(lk),LGUT,laneVP(lk)); ndg.clip();
    for(let t=0;t<row[1];t++){
      const vy=laneY(lk,t);
      ndg.fillStyle=t%2?'#1f1f1f':'#242424'; ndg.fillRect(0,vy,LGUT,laneH);   // レーンと同じ交互の色分け
      const vis=layerVisible(lk,t);
      ndg.fillStyle=vis?'#9a9a9a':'#5f5f5f'; ndg.font='bold 10px '+FONT; ndg.textAlign='left'; ndg.textBaseline='middle';
      ndg.fillText(laneLabel(lk,t),8,vy+12);
      const bw2=16, bh2=14, by2=vy+5;   // L(ロック)/S(ソロ)/M(ミュート)ボタン
      const lb={lk,t,kind:'l',x:LGUT-3*bw2-14,y:by2,w:bw2,h:bh2}, sb={lk,t,kind:'s',x:LGUT-2*bw2-10,y:by2,w:bw2,h:bh2}, mb={lk,t,kind:'m',x:LGUT-bw2-6,y:by2,w:bw2,h:bh2};
      for(const b of [lb,sb,mb]){
        const on=b.kind==='s'?layerSoloS.has(lk+t):b.kind==='m'?layerMuteS.has(lk+t):layerLockS.has(lk+t);
        ndg.fillStyle=on?(b.kind==='s'?'#f1dc55':b.kind==='m'?'#e2605b':'#5b8fdb'):'#2d2d2d';   // L=青系
        ndg.beginPath(); ndg.roundRect(b.x,b.y,b.w,b.h,3); ndg.fill();
        ndg.strokeStyle=on?'rgba(0,0,0,.4)':'#1d1d1d'; ndg.lineWidth=1; ndg.stroke();
        ndg.fillStyle=on?'#141414':'#9a9a9a'; ndg.font='bold 9px '+FONT; ndg.textAlign='center';
        ndg.fillText(b.kind.toUpperCase(),b.x+b.w/2,b.y+b.h/2+0.5);
        _lgBtns.push(b);
      }
      ndg.textAlign='left';
    }
    ndg.restore(); }
  { const dy=laneTopOf('l')-LDIV;   // ノーツ/ライトグループの継ぎ目（Music/Layerの区切りと同じ様式・固定位置）
    ndg.fillStyle='#0e0e0e'; ndg.fillRect(0,dy,ndW,LDIV);
    ndg.fillRect(0,ndH-LDIV,ndW,LDIV); }   // Light/Music の継ぎ目もndcv内に描く＝全高の再生ヘッドが跨いで連続（ovcvはCSS border撤去で密着）
  ndg.strokeStyle='#161616'; ndg.beginPath(); ndg.moveTo(0,LRULER); ndg.lineTo(ndW,LRULER); ndg.stroke();
  ndg.beginPath(); ndg.moveTo(LGUT,0); ndg.lineTo(LGUT,ndH); ndg.stroke();
  syncLaneSb();   // 右のNotes/Light独立スクロールバー（レーンが入り切らない時だけ表示）
  // マウス拍の黄ライン（3D⇄NLEで双方向共有・Musicまで貫通）
  { const thb=(camMode==='place')?null:(tlHoverBeat??hoverBeat);   // 配置モードは黄ライン非表示（ヘルバ様指定）
    if(thb!=null){ const hx=bx(thb);
      if(hx>=LGUT) crispVLine(ndg,ndcv,hx,'rgba(255,216,45,.85)'); } }   // 赤と同じく上端(ルーラー)まで全高・クッキリ
  // 範囲選択マーキー
  if(layerBand&&layerBand.moved){
    const bx=Math.min(layerBand.x0,layerBand.x1), by=Math.min(layerBand.y0,layerBand.y1),
      bw=Math.abs(layerBand.x1-layerBand.x0), bh=Math.abs(layerBand.y1-layerBand.y0);
    ndg.fillStyle='rgba(129,96,227,.10)'; ndg.fillRect(bx,by,bw,bh);
    ndg.strokeStyle='#8160e3'; ndg.lineWidth=1; ndg.setLineDash([4,3]);
    ndg.strokeRect(bx+0.5,by+0.5,bw,bh); ndg.setLineDash([]); }
  if(layerPaste){   // ペーストのゴースト（マウス追従・クリックで確定 / Esc取消）。空きが無いレーンは赤で警告
    const {items,at,dtBy}=layerPaste;
    for(const it of items){ const kind=it.lk||'n', sh=dtBy[kind], fits=(sh!=null);
      const gtr=fits?it.track+sh:it.track;
      if(gtr>=laneCountOf(kind)) continue;
      const gx=bx(at+it.rel), gw=(it.len||4)*PPB, gy=laneY(kind,gtr)+4, gh=laneH-8;
      if(gx+gw<LGUT||gx>ndW) continue;
      ndg.save(); ndg.beginPath(); ndg.rect(LGUT,laneTopOf(kind),ndW-LGUT,laneVP(kind)); ndg.clip();
      ndg.globalAlpha=0.6;
      ndg.fillStyle=fits?'rgba(129,96,227,.18)':'rgba(208,48,96,.20)';
      roundRectND(gx+0.5,gy+0.5,gw-1,gh-1,6); ndg.fill();
      ndg.lineWidth=1.6; ndg.setLineDash([5,3]); ndg.strokeStyle=fits?'#8160e3':'#d03060'; ndg.stroke(); ndg.setLineDash([]);
      ndg.globalAlpha=0.9; ndg.fillStyle='#eafff5'; ndg.font='bold 10.5px '+FONT; ndg.textAlign='left'; ndg.textBaseline='middle';
      ndg.fillText(it.label||'Sheet', Math.max(LGUT+4,gx+6), gy+9);
      // ゴースト内にもミニロール（ピアノロール）を薄く表示＝何を貼るか見える
      const cc=it.content||{}, L=it.len||4, byTop=gy+18, byH=gh-21;
      if(byH>=10){
        ndg.save(); roundRectND(gx+0.5,gy+0.5,gw-1,gh-1,6); ndg.clip(); ndg.globalAlpha=0.5;
        if(kind==='n'){
          const laneNH=byH/4;
          for(const o of (cc.walls||[])){ if((o.beat||0)>=L||(o.beat||0)<0) continue;
            const wx0=Math.max(gx+2,gx+(o.beat||0)*PPB), wx1=Math.min(gx+gw-2,gx+((o.beat||0)+(o.dur||0))*PPB);
            const c0=Math.max(0,Math.min(3,o.x||0)), cols=Math.max(1,Math.min(o.w||1,4-c0));
            ndg.fillStyle='rgba(208,48,96,.22)'; ndg.fillRect(wx0,byTop+c0*laneNH,Math.max(1.5,wx1-wx0),cols*laneNH); }
          for(const n of (cc.notes||[])){ if((n.beat||0)>=L||(n.beat||0)<0) continue;
            const nx=gx+(n.beat||0)*PPB, lane=Math.max(0,Math.min(3,n.x||0)); if(nx<gx-3||nx>gx+gw) continue;
            ndg.fillStyle=n.c===0?cRED:cBLUE; ndg.fillRect(nx,byTop+lane*laneNH+0.8,3,Math.max(1.5,laneNH-1.6)); }
          for(const n of (cc.bombs||[])){ if((n.beat||0)>=L||(n.beat||0)<0) continue;
            const nx=gx+(n.beat||0)*PPB, lane=Math.max(0,Math.min(3,n.x||0)); if(nx<gx-3||nx>gx+gw) continue;
            ndg.fillStyle='#888899'; ndg.fillRect(nx,byTop+lane*laneNH+1.6,2,Math.max(1,laneNH-3.2)); }
        } else {
          const laneLH=byH/10;
          for(const ev of (cc.lights||[])){ if((ev.beat||0)>=L||(ev.beat||0)<0) continue;
            const li=laneIdxByType[ev.et]; if(li===undefined) continue;
            const nx=gx+(ev.beat||0)*PPB; if(nx<gx-3||nx>gx+gw) continue;
            ndg.fillStyle='#'+chipColorOf(ev.et,ev.i,evChroma(ev),boostStateAt(ev.beat)).toString(16).padStart(6,'0');
            ndg.fillRect(nx,byTop+li*laneLH+0.3,2,Math.max(1,laneLH-0.6)); }
        }
        ndg.restore();
      }
      ndg.restore(); }
    ndg.globalAlpha=1;
  }
  // 再生ヘッド（最前面・Musicと同一X・上部まで貫通。音声遅延補正済みcurV基準）
  const _phx=bx(curV);
  if(_phx>=LGUT){ phRect(ndg,ndcv,_phx);   // 本体=デバイスピクセルスナップでクッキリ
    ndg.fillStyle='#ff3344'; ndg.beginPath(); ndg.moveTo(_phx-5,0); ndg.lineTo(_phx+5,0); ndg.lineTo(_phx,7); ndg.closePath(); ndg.fill(); }
  ndcv.style.cursor=layerRazor?'crosshair':_ndEdgeHover?'ew-resize':layerDrag?'grabbing':_ndClipHover?'grab':'';   // クリップ=掌／ドラッグ中=グー
}
// フェーズ2: レイヤービューの編集（選択・移動・分割・結合・削除）。位置=真実で合成
let layerPan=null, layerDrag=null, layerRazor=false, layerSeek=false, layerBand=null, layerSel=new Set();
let markerDrag=null;   // マーカー帯のドラッグ移動 {m,moved}
let layerResize=null;   // クリップ端トリム {s,side,origBeat,origLen,ref}
let layerClipboard=null; // クリップのコピー内容 {items:[{rel,track,len,label,col,colHex,content,byDiff}]}（全難易度の中身ごと保持）
let _ndEdgeHover=false; // クリップ端ホバー（ew-resizeカーソル用）
let _ndClipHover=false; // クリップ本体ホバー（掌カーソル用。ドラッグ中はグー）
let tlHoverBeat=null;   // NLE/Musicのマウス拍（3Dの黄ラインと同じ・スナップ済み。両パネルを貫く一本線で描画）
// レイヤーのソロ/ミュート（表示のみのフィルタ。保存・書き出しデータは削らない）
let layerMuteS=new Set(), layerSoloS=new Set(), layerLockS=new Set();   // L=ロック（暗く＋触れない）
const objLockedN=o=>layerLockS.has('n'+(o._tr||0));   // ノーツ系（'n'グループ）のロック判定
const objLockedL=o=>layerLockS.has('l'+(o._tr||0));   // ライト（'l'グループ）のロック判定
const _lgBtns=[];   // 溝内S/Mボタンの当たり判定（drawLayersで毎フレーム更新）
const _clipSw=[];   // クリップヘッダー左の色スウォッチの当たり判定（drawLayersで毎フレーム更新）
// ソロはグループ（ノーツ/ライト）内で完結＝ライトのソロでノーツが消えない（逆も同様・ヘルバ様指定）。
// 自グループにソロが1つも無ければ、そのグループは従来どおりミュート判定のみで表示。
const soloInGrp=lk=>{ for(const k of layerSoloS) if(k[0]===lk) return true; return false; };   // 空Setなら即抜け＝ソロ未使用時のコストは実質ゼロ
const layerVisible=(lk,t)=>{ const k=lk+(t||0); return soloInGrp(lk)?layerSoloS.has(k):!layerMuteS.has(k); };   // キー='n0'/'l2'等
function laneOverlaps(beat,len,lk,tr,excludeIds){   // 同一レーン内の重なり判定（同グループ・同レーンのみ比較）
  return sections.some(s=>secLk(s)===lk&&(s.track||0)===tr&&s.kind!=='null'
    &&!(excludeIds&&excludeIds.has(s.id))
    &&(s.beat||0)<beat+len-1e-6&&(s.beat||0)+(s.len||4)>beat+1e-6);
}
function packLanes(){   // 接続に関係なく各グループ(notes/light)のクリップを「一番数字の低いトラック(Notes1/Light1=一番下)」へ詰める（時間が重なる分だけ上へ・隙間はそのまま空き）
  for(const lk of ['n','l']){ const N=laneCountOf(lk);
    const grp=sections.filter(s=>secLk(s)===lk&&s.kind!=='null').sort((a,b)=>(a.beat||0)-(b.beat||0)||(a.track||0)-(b.track||0));
    const lanes=[];   // lanes[d] = 詰め深さd（d=0=Notes1/一番下）に確定済みの[b0,b1]配列
    for(const s of grp){ const b0=s.beat||0, b1=b0+(s.len||4);
      let d=0; while((lanes[d]||[]).some(o=>b0<o.b1-1e-6&&b1>o.b0+1e-6)) d++;   // 時間が重ならない一番下の段を探す
      (lanes[d]=lanes[d]||[]).push({b0,b1});
      s.track=Math.max(0,N-1-d); }   // 詰め深さd（0=Notes1）→ 内部track(gi)。表示番号は下が1
  }
}
function clipAtLayer(mx,my){ if(mx<LGUT) return null; const lh=laneHt();   // 溝(トラックヘッド/S・M・Lボタン)はクリップ対象外
  for(let i=sections.length-1;i>=0;i--){ const s=sections[i];
    const x=lBeatToX(s.beat||0), w=(s.len||4)*lPPB(), y=laneY(secLk(s),s.track||0)+4, h=lh-8;
    if(mx>=x&&mx<=x+w&&my>=y&&my<=y+h) return s; } return null; }
function clipEdgeAt(mx,my){ if(mx<LGUT) return null; const lh=laneHt();   // クリップの左右端±4px=トリムハンドル（溝は除外）
  for(let i=sections.length-1;i>=0;i--){ const s=sections[i];
    const x=lBeatToX(s.beat||0), w=(s.len||4)*lPPB(), y=laneY(secLk(s),s.track||0)+4, h=lh-8;
    if(my<y||my>y+h) continue;
    if(x>=LGUT&&Math.abs(mx-x)<=4) return {s,side:'l'};   // 左端は溝より右に見えている時だけ（溝下に隠れた左端はトリム不可）
    if(Math.abs(mx-(x+w))<=4) return {s,side:'r'}; }
  return null; }
const _LCT={notes:['beat'],bombs:['beat'],walls:['beat'],arcs:['b','tb'],chains:['b','tb'],lights:['beat']};
// 実体のあるクリップが1つでもあるか（空配列 [] は truthy だが compile でフラットが消えるので区別）
function hasActiveClips(arr){ return (arr||[]).some(s=>s.kind!=='null'); }
// ノーツ系フラットの _tr を、その拍を含むクリップのトラックへ合わせる（チェイン/アーク生成時の _tr 未設定や packLanes 後のズレを修復）
function alignNoteGroupTracks(arr){
  for(const o of arr||[]){ const bf=o.beat??o.b; if(bf==null) continue;
    const cov=sections.filter(s=>secLk(s)==='n'&&s.kind!=='null'&&(s.beat||0)<=bf+1e-6&&(s.beat||0)+(s.len||4)>bf+1e-6);
    if(!cov.length) continue;
    // 現在の所属トラックに自分の拍を覆うクリップがあれば動かさない。
    // （以前は無条件で「最大トラックのクリップ」へ強制移動→拍範囲が重なる別レーンのクリップに中身が吸われるバグ＝ヘルバ様報告の
    //   「保存したら上のクリップから下のクリップへ移動する」の原因。所属先を失った迷子だけを拾う本来の役目に限定）
    if(cov.some(s=>(s.track||0)===(o._tr||0))) continue;
    o._tr=cov.reduce((a,c)=>((c.track||0)>(a.track||0)?c:a)).track||0; }
}
function compileLayersToFlat(){   // 各セクションの内容を、そのセクションのbeat位置に合成（チェーン順でなく位置が真実）
  if(_flatDirty) flushFlatEdits();   // 未同期の3D編集を消さない（compile前にcontentへ確定）
  notes=[];bombs=[];walls=[];arcs=[];chains=[];lightEvents=[];
  for(const s of sections){ if(s.kind==='null') continue; const c=s.content||{}, L=s.len||4, off=s.beat||0, tr=s.track||0;
    (c.notes||[]).forEach(n=>{ if(n.beat>=0&&n.beat<L) notes.push({...n,beat:n.beat+off,_tr:tr}); });   // 負の拍=左トリムで隠れた分（保持・非出力）
    (c.bombs||[]).forEach(n=>{ if(n.beat>=0&&n.beat<L) bombs.push({...n,beat:n.beat+off,_tr:tr}); });
    (c.walls||[]).forEach(o=>{ if(o.beat>=0&&o.beat<L) walls.push({...o,beat:o.beat+off,_tr:tr}); });
    (c.arcs||[]).forEach(a=>{ if(a.b>=0&&a.b<L) arcs.push({...a,b:a.b+off,tb:a.tb+off,_tr:tr}); });
    (c.chains||[]).forEach(cc=>{ if(cc.b>=0&&cc.b<L) chains.push({...cc,b:cc.b+off,tb:cc.tb+off,_tr:tr}); });
    (c.lights||[]).forEach(ev=>{ if(ev.beat>=0&&ev.beat<L) lightEvents.push({...ev,beat:ev.beat+off,_tr:tr}); }); }
  lightEvents.sort((a,b)=>a.beat-b.beat);
  applyInfoChain(); selection.clear(); lightSelection.clear(); gizmoMode=null; rebuild(); }
// 逆同期: 3D編集で変わったフラット(notes[]等)を各クリップのcontentへ書き戻す。範囲外(トリムで隠れた分=負の拍/はみ出し)は保持
let _flatDirty=false;   // 3D(NOTES/LIGHT)でフラットを編集した→contentへ未反映
function syncFlatToSections(){
  const FA={notes,bombs,walls,arcs,chains,lights:lightEvents};   // content-key → フラット配列
  const GK={notes:'n',bombs:'n',walls:'n',arcs:'n',chains:'n',lights:'l'};
  for(const s of sections){ if(s.kind==='null') continue;
    const off=s.beat||0, L=s.len||4, tr=s.track||0, slk=secLk(s);
    if(!s.content) s.content={};
    for(const key in _LCT){ if(GK[key]!==slk) continue;   // そのクリップのグループ種別のみ処理
      const bf=_LCT[key][0];   // 主拍フィールド(notes='beat'/arcs='b'等)
      const old=s.content[key]||[];
      const kept=old.filter(it=>{ const rb=it[bf]??0; return !(rb>=0&&rb<L); });   // 表示範囲[0,L)外=トリム分は保持
      const inside=(FA[key]||[]).filter(o=>(o._tr||0)===tr&&(o[bf]??0)>=off-1e-6&&(o[bf]??0)<off+L-1e-6)
        .map(o=>{ const c={...o}; delete c._tr; for(const f of _LCT[key]) c[f]=(c[f]??0)-off; return c; });   // 絶対拍→クリップ相対拍
      s.content[key]=[...kept,...inside]; } }
}
function flushFlatEdits(){ if(_flatDirty){ _flatDirty=false; syncFlatToSections(); } }   // 未反映の3D編集をcontentへ確定（ミニロール更新＋revert防止）
// ============ ボックス構造の全難易度同期（構造=一体、中身=難易度ごと） ============
// クリップは共通ID(gid)で全難易度の対応物と結ばれる。gid無しの旧データは（名前+拍+レーン+長さ）で照合
function clipRef(s){ return {gid:s.gid,label:s.label,beat:s.beat||0,track:s.track||0,len:s.len||4}; }
// 伝播ヘルパ群(eachOtherDiff/propagateLights/propSplit〜propCreate)は撤去（2026-07-05ヘルバ様確定「箱ごと難易度別」）
function splitSectionAt(s,atAbsBeat,quiet){ if(s.kind==='null') return;   // quiet=履歴/通知を抑止（一括分割で外側が1回だけ積む）
  const local=atAbsBeat-(s.beat||0), L=s.len||4; if(local<=1e-6||local>=L-1e-6) return;
  if(!quiet) snapshot('node');
  if(!s.gid) s.gid='g'+(++_nid);
  const ref0=clipRef(s);
  const right={...s,id:'n'+(++_nid)+Math.random().toString(36).slice(2,6),gid:'g'+(++_nid),beat:(s.beat||0)+local,len:L-local,label:(s.label||'')+"'",col:pickStripCol(),colHex:null,content:{}};   // 後ろ半分は別の色（任意色指定も引き継がない）
  const nc={};
  for(const k in _LCT){ const arr=(s.content&&s.content[k])||[];
    nc[k]=arr.filter(it=>(it[_LCT[k][0]]??0)<local-1e-6).map(it=>({...it}));
    right.content[k]=arr.filter(it=>(it[_LCT[k][0]]??0)>=local-1e-6).map(it=>{ const o={...it}; for(const f of _LCT[k]) o[f]=(o[f]??0)-local; return o; }); }
  s.content=nc; s.len=local;
  const i=sections.indexOf(s); sections.splice(i+1,0,right);
  layerSel=new Set(); musicSelSet=new Set();   // カット後は全選択解除
  compileLayersToFlat(); metaDirty=true; if(!quiet) stat('クリップを分割しました'); }
function cutClipAtMarkers(s){   // クリップ範囲内の全マーカー拍で一括分割（マーカーが何個あっても全部）
  if(!s||s.kind==='null') return;
  const b0=s.beat||0, b1=b0+(s.len||4);
  const ms=[...new Set(markers.map(m=>m.beat).filter(b=>b>b0+1e-6&&b<b1-1e-6))].sort((a,b)=>a-b);
  if(!ms.length){ stat('このクリップ内にマーカーがありません'); return; }
  snapshot('node');
  for(let i=ms.length-1;i>=0;i--) splitSectionAt(s,ms[i],true);   // 大きい拍から分割＝左側sは常にb0始点のまま有効に切れる
  layerSel=new Set(); musicSelSet=new Set();
  compileLayersToFlat(); metaDirty=true; stat(tf('msg.cutByMarkers','{n}個のマーカーで分割しました',{n:ms.length})); }
function mergeLayerSel(){ const sel=sections.filter(x=>layerSel.has(x.id)&&x.kind!=='null');
  if(sel.length<2){ stat('結合するにはクリップを2つ以上選択してください'); return; }
  // 同じ種別(notes同士/light同士)なら、別トラック・離れていても・時間が重なっていても1つに結合（重なった拍のノーツはそのまま重なる＝重複チェックで検知）
  const byGrp=new Map();
  for(const c of sel){ const k=secLk(c); if(!byGrp.has(k)) byGrp.set(k,[]); byGrp.get(k).push(c); }
  const merges=[];
  for(const arr of byGrp.values()){ if(arr.length<2) continue;
    arr.sort((a,b)=>(a.beat||0)-(b.beat||0));
    merges.push(arr); }
  if(!merges.length){ stat('結合できるクリップがありません（同じ種別を2つ以上選択）'); return; }
  snapshot('node');
  const newSel=new Set([...layerSel]);
  for(const run of merges){
    for(const c of run) if(!c.gid) c.gid='g'+(++_nid);
    const start=run[0].beat||0, end=Math.max(...run.map(c=>(c.beat||0)+(c.len||4)));   // 最遠端（重なり時は最後尾でなく全クリップの最大終端）
    const lk=secLk(run[0]), len=end-start;
    const content={}; for(const k in _LCT) content[k]=[];
    for(const c of run){ const off=(c.beat||0)-start; for(const k in _LCT){ for(const it of ((c.content&&c.content[k])||[])){ const o={...it}; for(const f of _LCT[k]) o[f]=(o[f]??0)+off; content[k].push(o); } } }
    const ids=new Set(run.map(c=>c.id));
    sections=sections.filter(x=>!ids.has(x.id));   // 先に構成クリップを除去＝重なり判定の対象外にする（他クリップは一切触らない）
    let tr=Math.min(...run.map(c=>c.track||0)), N=laneCountOf(lk);   // 他トラックを動かさず、マージ結果だけ空いている一番下の段へ
    for(let t=N-1;t>=0;t--){ if(!laneOverlaps(start,len,lk,t)){ tr=t; break; } }
    const merged={id:'n'+(++_nid)+Math.random().toString(36).slice(2,6),gid:'g'+(++_nid),beat:start,len,track:tr,lk,
      col:run[0].col,colHex:run[0].colHex||null,label:run[0].label,kind:'sheet',content};
    sections.push(merged);
    for(const id of ids) newSel.delete(id);
    newSel.add(merged.id); }
  layerSel=newSel; relinkDiffEdges(); compileLayersToFlat(); metaDirty=true; stat('クリップを結合しました'); }
function deleteLayerSel(){ if(!layerSel.size) return; snapshot('node');
  const _refs=sections.filter(x=>layerSel.has(x.id)).map(s=>{ if(!s.gid) s.gid='g'+(++_nid); return clipRef(s); });
  sections=sections.filter(x=>!layerSel.has(x.id)); layerSel=new Set();
  relinkDiffEdges();   // 消えたIDへの配線を残さない（配置ガードの誤爆防止）
  compileLayersToFlat(); metaDirty=true; stat('クリップを削除しました'); }
// ---- song(Music)とレイヤークリップの同時移動（同じ拍だけ連動） ----
function shiftMusicSelBeat(d){   // 選択中のMusicセグメント（分割/未分割）を拍dだけ相対移動
  if(!musicSelSet.size||!d) return;
  // 0拍より左はグループ全体で停止＝先頭が0に達したら止める（旧: 個別クランプで2個目以降が0に重なる不具合）
  if(musicSegs){
    let minB=Infinity; for(const j of musicSelSet) if(musicSegs[j]) minB=Math.min(minB,musicSegs[j].beat||0);
    if(minB!==Infinity&&minB+d<0) d=-minB;
    if(!d) return;
    for(const j of musicSelSet) if(musicSegs[j]) musicSegs[j].beat=(musicSegs[j].beat||0)+d;
  }
  else if(musicSelSet.has(0)) musicBeat=Math.max(0,musicBeat+d);
  metaDirty=true;
}
function shiftSelLayersBeat(d){   // 選択中のレイヤークリップを拍dだけ相対移動（レーン不変）。他クリップと重なるならfalseで一切不適用
  const grp=sections.filter(x=>layerSel.has(x.id)); if(!grp.length||!d) return true;
  // 0拍より左はグループ全体で停止＝先頭が0に達したら止める（旧: 個別クランプで2個目以降が0に重なる不具合）
  { let minB=Infinity; for(const x of grp) minB=Math.min(minB,x.beat||0);
    if(minB!==Infinity&&minB+d<0) d=-minB;
    if(!d) return true; }
  const gids=new Set(grp.map(x=>x.id));
  for(const x of grp){ const tb=(x.beat||0)+d;   // dはグループでクランプ済み＝個別クランプ不要
    if(laneOverlaps(tb,x.len||4,secLk(x),x.track||0,gids)) return false; }
  const moves=grp.map(x=>({x,ob:x.beat||0,ot:x.track||0,L:x.len||4,nb:(x.beat||0)+d}));
  const shift=(arr,f,f2)=>{ for(const it of arr){ const t=it[f]??0;   // ドラッグ中の3D/プレビュー追従（layerDragと同じ流儀）
    for(const m2 of moves){ if((it._tr||0)===m2.ot&&t>=m2.ob-1e-6&&t<m2.ob+m2.L-1e-6){
      it[f]=t+(m2.nb-m2.ob); if(f2&&it[f2]!=null) it[f2]+=(m2.nb-m2.ob); break; } } } };
  shift(notes,'beat'); shift(bombs,'beat'); shift(walls,'beat'); shift(lightEvents,'beat'); shift(arcs,'b','tb'); shift(chains,'b','tb');
  lightEvents.sort((a,b)=>a.beat-b.beat);
  for(const m2 of moves){ m2.x.beat=m2.nb; }
  return true;
}
let _ndMouseY=-1;   // NLE上のマウスy（レーン特定用。-1=NLE外）
function toggleLaneState(kind, lk, tr){   // レーンのロック(l)/ミュート(m)/ソロ(s)を切替（ボタンとキーで共用）
  const set=kind==='s'?layerSoloS:kind==='m'?layerMuteS:layerLockS, key=lk+tr;
  set.has(key)?set.delete(key):set.add(key);
  if(kind==='s'&&set.has(key)) layerMuteS.delete(key);   // ソロとミュートは同レーンで同時ONにしない（排他）
  if(kind==='m'&&set.has(key)) layerSoloS.delete(key);
  if(kind==='l'&&set.has(key)){ for(const o of [...selection]) if(objLockedN(o)) selection.delete(o);   // ロックしたレーンの選択は解除
    for(const ev of [...lightSelection]) if(objLockedL(ev)) lightSelection.delete(ev); }
  rebuild();
  stat(tf('msg.laneState','{lane} を{state}',{lane:laneLabel(lk,tr),state:kind==='s'?(layerSoloS.has(key)?t('word.solo','ソロ'):t('word.unsolo','ソロ解除')):kind==='m'?(layerMuteS.has(key)?t('word.mute','ミュート'):t('word.unmute','ミュート解除')):(layerLockS.has(key)?t('word.lock','ロック'):t('word.unlock','ロック解除'))}));
}
let layerPaste=null;   // NLEクリップのペースト・ゴースト（マウス追従→クリックで確定 / Esc・右クリックで取消）
function layerPasteFit(items, at){   // グループごとに重ならない空きレーンシフトを求める（見つからなければnull）
  const dtBy={};
  for(const kind of ['n','l']){ const its=items.filter(i2=>(i2.lk||'n')===kind);
    if(!its.length){ dtBy[kind]=0; continue; }
    const N=laneCountOf(kind), minT=Math.min(...its.map(i2=>i2.track)), maxT=Math.max(...its.map(i2=>i2.track));
    const cand=[0]; for(let a=1;a<N;a++){ cand.push(a,-a); }
    dtBy[kind]=null;
    for(const sh of cand){ if(minT+sh<0||maxT+sh>N-1) continue;
      let ok2=true; for(const it of its){ if(laneOverlaps(at+it.rel,it.len,kind,it.track+sh)){ ok2=false; break; } }
      if(ok2){ dtBy[kind]=sh; break; } } }
  return dtBy;
}
function startLayerPaste(){ if(!layerClipboard||!layerClipboard.items.length){ stat('クリップボードが空です'); return; }
  const at=Math.max(0,snapV(tlHoverBeat??cur));
  layerPaste={items:layerClipboard.items, at, dtBy:layerPasteFit(layerClipboard.items, at)};
  metaDirty=true; stat('クリップを貼り付け — マウスで位置決め → クリックで確定 / Esc取消'); }
function updateLayerPaste(beat){ if(!layerPaste) return; layerPaste.at=Math.max(0,snapV(beat)); layerPaste.dtBy=layerPasteFit(layerPaste.items, layerPaste.at); metaDirty=true; }
function commitLayerPaste(){ if(!layerPaste) return;
  const {items,at,dtBy}=layerPaste;
  if(dtBy.n==null||dtBy.l==null){ stat('⚠ ここは空きレーンがありません（別の位置へ / Escで取消）'); return; }   // 置けない位置ではゴーストを残す
  snapshot('node');
  const newSel=new Set();
  for(const it of items){ const kind=it.lk||'n';
    const sec={id:'n'+(++_nid)+Math.random().toString(36).slice(2,6),beat:at+it.rel,track:it.track+dtBy[kind],lk:kind,len:it.len,
      label:it.label,col:pickStripCol(),colHex:null,kind:'sheet',content:structuredClone(it.content)};
    sections.push(sec); newSel.add(sec.id); }
  layerSel=newSel; layerPaste=null; relinkDiffEdges(); compileLayersToFlat(); metaDirty=true;
  stat(tf('msg.clipPaste','クリップを貼り付け ×{n}（拍 {at}）',{n:items.length,at})); }
function cancelLayerPaste(){ if(!layerPaste) return; layerPaste=null; metaDirty=true; stat('貼り付けを取り消しました'); }
ndcv.addEventListener('pointerdown', e=>{ if(ndView!=='layers') return;
  if(layerPaste){ if(e.button===0){ e.preventDefault(); commitLayerPaste(); } return; }   // ゴースト追従中: 左クリックで確定（他ボタンは無視＝右クリックはcontextmenuで取消）
  selWatch('node');   // 選択の変化を1動作として履歴へ
  const r=ndcv.getBoundingClientRect(), sx=e.clientX-r.left, sy=e.clientY-r.top;   // songとの同時選択を保つため、ここでは音楽選択を一律解除しない（単独クリック時のみ下で解除）
  if(e.button===1&&!e.ctrlKey&&!e.altKey&&!e.metaKey){ e.preventDefault();   // パン=中ドラッグ（素/Shift併用可・Ctrl/Alt/Metaは無効）。上下はカーソルのあるグループ（Notes/Light別・Musicはなし）
    const la0=(sy>=LRULER)?laneAtY(sy):null;
    layerPan={sx,sy,startB0:tlWindow(cur).b0,lk:la0?la0.lk:null,sc0:la0?scrOf(la0.lk):0};
    try{ndcv.setPointerCapture(e.pointerId);}catch(_){} return; }
  if(sx<LGUT){                                   // 溝内: L(ロック)/S(ソロ)/M(ミュート)ボタン
    if(e.button===0){ const b=_lgBtns.find(r2=>sx>=r2.x&&sx<=r2.x+r2.w&&sy>=r2.y&&sy<=r2.y+r2.h);
      if(b) toggleLaneState(b.kind, b.lk, b.t); }
    return; }
  if(sy>=LRULER-MKRH&&sy<LRULER){   // マーカー帯: マーカーのドラッグのみ。ここでは再生ヘッドをジャンプさせない（シークは上の数字ルーラーだけ）
    if(e.button===0){ const hit=_mkRects.find(r2=>sx>=r2.x&&sx<=r2.x+r2.w&&sy>=r2.y&&sy<=r2.y+r2.h)
        ||(()=>{ let best=null,bd=8; for(let i2=0;i2<markers.length;i2++){ const d=Math.abs(lBeatToX(markers[i2].beat)-sx); if(d<bd){ bd=d; best={i:i2}; } } return best; })();
      if(hit){ markerDrag={m:markers[hit.i],moved:false}; try{ndcv.setPointerCapture(e.pointerId);}catch(_){} } }
    return; }
  if(sy>=LRULER-MKRH-TPRH&&sy<LRULER-MKRH){      // テンポパート帯: 追加/編集は右クリックかダブルクリックのみ（左クリック単発では何もしない・シークもさせない）
    return; }
  if(sy<LRULER-MKRH){                            // 数字ルーラー（マーカー帯より上）=シーク（Premiere/DaVinciと同じ。ドラッグでスクラブ）
    if(e.button!==0) return;
    if(playing) pause();
    tlFrozen=tlWindow(cur); layerSeek=true;
    cur=Math.max(0,snapV(lXToBeat(sx))); offset=beatToTimeTM(cur);
    try{ndcv.setPointerCapture(e.pointerId);}catch(_){} return; }
  const s=clipAtLayer(sx,sy);
  if(layerRazor){ if(s) splitSectionAt(s,lXToBeat(sx)); return; }
  if(e.button!==0) return;
  { const sw=_clipSw.find(r2=>sx>=r2.x&&sx<=r2.x+r2.w&&sy>=r2.y&&sy<=r2.y+r2.h);   // 色スウォッチ=既存ピッカーで色変更
    if(sw){ const sec=sections.find(x2=>x2.id===sw.id);
      if(sec) ndColorEdit(stripColOf(sec),hex=>{ snapshot('node'); if(!sec.gid) sec.gid='g'+(++_nid);
        sec.colHex=hex; metaDirty=true; },{x:sw.x,y:sw.y+14,h:0});
      return; } }
  { const eh=clipEdgeAt(sx,sy);                            // 端ドラッグ=トリム（左右端±4px）
    if(eh&&eh.s.kind!=='null'){ if(!eh.s.gid) eh.s.gid='g'+(++_nid);
      const origC={}; for(const k2 in _LCT) origC[k2]=((eh.s.content&&eh.s.content[k2])||[]).map(it=>_LCT[k2].map(f=>it[f]??0));   // 中身の元拍（左トリム中の絶対位置固定用）
      layerResize={s:eh.s,side:eh.side,origBeat:eh.s.beat||0,origLen:eh.s.len||4,ref:clipRef(eh.s),origC,
        pre:dumpDomain('node')};   // 履歴は確定時に「実際に変化した場合だけ」積む（クリックだけでRedoが消える汚染の防止）
      try{ndcv.setPointerCapture(e.pointerId);}catch(_){} return; } }
  if(!s){ layerBand={x0:sx,y0:sy,x1:sx,y1:sy,add:e.shiftKey,moved:false};   // 空き左ドラッグ=範囲選択（クリックのみ=解除）
    try{ndcv.setPointerCapture(e.pointerId);}catch(_){} return; }
  if(e.shiftKey){ layerSel.has(s.id)?layerSel.delete(s.id):layerSel.add(s.id); }   // Shift=追加（song選択は維持＝同時選択）
  else if(!layerSel.has(s.id)){ layerSel=new Set([s.id]); musicSelSet=new Set(); }   // 単独クリック=このクリップのみ（song選択も解除）。既選択の掴み直しはグループ維持
  layerDrag={grabBeat:lXToBeat(sx)-(s.beat||0), s, moved:false,
    orig:sections.filter(x=>layerSel.has(x.id)||x===s).map(x=>{ if(!x.gid) x.gid='g'+(++_nid); return {id:x.id,ref:clipRef(x)}; })};   // 移動前の位置（全難易度伝播用）
  try{ndcv.setPointerCapture(e.pointerId);}catch(_){} });
ndcv.addEventListener('pointermove', e=>{ if(ndView!=='layers') return;
  const r=ndcv.getBoundingClientRect(), sx=e.clientX-r.left, sy=e.clientY-r.top;
  _ndMouseY=sy;   // L/M/Sショートカット用にマウスyを記録
  if(layerPaste){ tlHoverBeat=(sx>=LGUT&&sy>=LRULER)?Math.max(0,snapV(lXToBeat(sx))):null; if(tlHoverBeat!=null) updateLayerPaste(tlHoverBeat); return; }   // ゴースト追従
  if(markerDrag){ markerDrag.m.beat=Math.max(0,snapV(lXToBeat(sx))); markerDrag.moved=true; metaDirty=true; return; }   // マーカードラッグ中は拍だけ更新
  tlHoverBeat=(sx>=LGUT&&sy>=LRULER)?Math.max(0,snapV(lXToBeat(sx))):null;   // 黄ライン（マウス拍）
  _ndEdgeHover=!layerDrag&&!layerBand&&!layerSeek&&(layerResize!=null||!!clipEdgeAt(sx,sy));   // 端ホバー=ew-resize
  _ndClipHover=!layerBand&&!layerSeek&&!_ndEdgeHover&&!!clipAtLayer(sx,sy);   // 本体ホバー=掌
  if(layerResize){ const s=layerResize.s, mn=Math.max(snap,0.25);
    const others=sections.filter(x2=>x2!==s&&secLk(x2)===secLk(s)&&(x2.track||0)===(s.track||0)&&x2.kind!=='null');
    if(layerResize.side==='r'){
      let nl=snapV(lXToBeat(sx))-(s.beat||0);
      let lim=Infinity; for(const o2 of others){ const ob=o2.beat||0; if(ob>=(s.beat||0)+mn-1e-6&&ob<lim) lim=ob; }   // 右隣を越えない
      s.len=Math.max(mn,Math.min(nl,lim-(s.beat||0)));
    } else {
      let nb=Math.max(0,snapV(lXToBeat(sx)));
      let lim=0; for(const o2 of others){ const oe=(o2.beat||0)+(o2.len||4); if(oe<=layerResize.origBeat+1e-6&&oe>lim) lim=oe; }   // 左隣を越えない
      nb=Math.max(lim,Math.min(nb,layerResize.origBeat+layerResize.origLen-mn));
      s.len=layerResize.origLen-(nb-layerResize.origBeat); s.beat=nb;
      const dT=nb-layerResize.origBeat;                        // 中身は絶対位置に固定表示（端だけが動く）
      for(const k2 in _LCT){ const arr=(s.content&&s.content[k2])||[], ov=layerResize.origC[k2], fs=_LCT[k2];
        for(let i2=0;i2<arr.length;i2++){ for(let j2=0;j2<fs.length;j2++) arr[i2][fs[j2]]=ov[i2][j2]-dT; } }
    }
    return; }
  if(layerSeek){ cur=Math.max(0,snapV(lXToBeat(sx))); offset=beatToTimeTM(cur); return; }
  if(layerBand){ layerBand.x1=sx; layerBand.y1=sy;
    if(Math.abs(sx-layerBand.x0)+Math.abs(sy-layerBand.y0)>3) layerBand.moved=true; return; }
  if(layerDrag){ if(!layerDrag.moved) snapshot('node');
    let nb=snapV(lXToBeat(sx)-layerDrag.grabBeat);   // 移動は常にスナップ幅（Shiftスムーズ移動は廃止=1/60拍等の事故防止）。0クランプはグループ単位で下記
    const la=laneAtY(sy), lk0=secLk(layerDrag.s);
    let d=nb-(layerDrag.s.beat||0);
    const dt=(la.lk===lk0?la.gi-(layerDrag.s.track||0):0);   // レーン移動は同グループ内のみ（継ぎ目は跨げない）
    const grp=sections.filter(x=>layerSel.has(x.id)); if(!grp.includes(layerDrag.s)) grp.push(layerDrag.s);
    // 0拍より左は「グループ全体」で停止＝先頭クリップが0に達したらそれ以上動かさない（相対間隔を保つ）。
    // 旧: 各クリップを個別に Math.max(0,..) → 負になる分が全部0へ集まり2個目以降が重なる不具合（ヘルバ様報告 2026-07-15）
    { let minB=Infinity;
      for(const x of grp) minB=Math.min(minB,x.beat||0);
      if(musicSelSet.size){ if(musicSegs){ for(const j of musicSelSet) if(musicSegs[j]) minB=Math.min(minB,musicSegs[j].beat||0); }
        else if(musicSelSet.has(0)) minB=Math.min(minB,musicBeat); }   // 同時選択のMusicも含めて止める＝ズレ防止
      if(minB!==Infinity&&minB+d<0) d=-minB; }
    const gids=new Set(grp.map(x=>x.id));
    const clampT=x2=>Math.max(0,Math.min(laneCountOf(secLk(x2))-1,(x2.track||0)+dt));
    let ok=true;                                             // 移動先が重なるならこのステップは適用しない（ドラッグ中も重ねて表示しない）
    for(const x of grp){ const tb=(x.beat||0)+d;             // dはグループでクランプ済み＝個別クランプ不要
      if(laneOverlaps(tb,x.len||4,secLk(x),clampT(x),gids)){ ok=false; break; } }
    if(ok){
      // 移動対象クリップ範囲のフラットも同時に平行移動 → 3Dビューがドラッグ中リアルタイム追従（全再構築なしで軽量）
      const moves=grp.map(x=>({x,ob:x.beat||0,ot:x.track||0,L:x.len||4,
        nb:(x.beat||0)+d,nt:clampT(x)}));
      const shift=(arr,f,f2)=>{ for(const it of arr){ const t=it[f]??0;
        for(const m2 of moves){ if((it._tr||0)===m2.ot&&t>=m2.ob-1e-6&&t<m2.ob+m2.L-1e-6){
          it[f]=t+(m2.nb-m2.ob); if(f2&&it[f2]!=null) it[f2]+=(m2.nb-m2.ob); it._tr=m2.nt; break; } } } };
      shift(notes,'beat'); shift(bombs,'beat'); shift(walls,'beat'); shift(lightEvents,'beat'); shift(arcs,'b','tb'); shift(chains,'b','tb');
      lightEvents.sort((a,b)=>a.beat-b.beat);
      for(const m2 of moves){ m2.x.beat=m2.nb; m2.x.track=m2.nt; }
      if(musicSelSet.size) shiftMusicSelBeat(d);   // songを同時選択している場合は同じ拍だけ連動（レーン移動時も拍dのみ適用）
    }
    layerDrag.moved=true; return; }
  if(layerPan){ tlViewB0=Math.max(0,layerPan.startB0-(sx-layerPan.sx)/lPPB());   // 掴んだ方向へ表示窓を移動
    if(layerPan.lk) setScr(layerPan.lk,layerPan.sc0-(sy-layerPan.sy)); } });      // 上下パン=そのグループのスクロール
ndcv.addEventListener('pointerup', e=>{ if(ndView!=='layers') return;
  selWatch('node');   // マーキー範囲選択の確定も1動作として履歴へ
  if(markerDrag){ if(markerDrag.moved){ markers.sort((a,b)=>a.beat-b.beat); metaDirty=true; stat(tf('msg.markerMoved','マーカー「{name}」を拍 {beat} へ移動',{name:markerDrag.m.name,beat:markerDrag.m.beat})); }
    markerDrag=null; return; }   // 動かさずクリックしても再生ヘッドはジャンプさせない（マーカー帯ではシーク無効）
  if(layerResize){ const s=layerResize.s, d=(s.beat||0)-layerResize.origBeat;
    const changed=Math.abs(d)>1e-9||Math.abs((s.len||4)-layerResize.origLen)>1e-9;
    if(changed){   // 変化があった時だけ履歴に積む（端をクリックしただけではUndo/Redoを汚さない）
      pushHist('node',layerResize.pre);
      // 左トリム分の内部シフトはドラッグ中に適用済み（譜面は絶対位置固定・負の拍=保持・非出力）
      relinkDiffEdges(); compileLayersToFlat(); metaDirty=true; stat('クリップをトリムしました'); }
    layerResize=null; return; }
  if(layerSeek){ layerSeek=false; if(!prSeek) tlFrozen=null; }
  if(layerBand){
    if(layerBand.moved){
      const bx0=Math.min(layerBand.x0,layerBand.x1), bx1=Math.max(layerBand.x0,layerBand.x1),
        by0=Math.min(layerBand.y0,layerBand.y1), by1=Math.max(layerBand.y0,layerBand.y1), lh=laneHt();
      const hit=new Set(layerBand.add?[...layerSel]:[]);
      for(const s of sections){
        const x=lBeatToX(s.beat||0), w=(s.len||4)*lPPB(), y=laneY(secLk(s),s.track||0)+4, h=lh-8;
        if(x<=bx1&&x+w>=bx0&&y<=by1&&y+h>=by0) hit.add(s.id); }
      layerSel=hit; }
    else if(!layerBand.add){ layerSel=new Set(); musicSelSet=new Set(); }   // 空クリック=全選択解除（song選択も）
    layerBand=null; }
  if(layerDrag&&layerDrag.moved){
    const movedIds=new Set((layerDrag.orig||[]).map(o=>o.id));
    let bad=false;
    for(const o of (layerDrag.orig||[])){ const live=sections.find(x=>x.id===o.id);
      if(live&&laneOverlaps(live.beat||0,live.len||4,secLk(live),live.track||0,movedIds)){ bad=true; break; } }
    if(bad){                                                   // 同じレイヤー内では重ねられない → 元の位置へ戻す
      for(const o of (layerDrag.orig||[])){ const live=sections.find(x=>x.id===o.id);
        if(live){ live.beat=o.ref.beat; live.track=o.ref.track; } }
      stat('⚠ 同じレーン内で重なるため元の位置に戻しました');
    } else {
      // 箱は難易度ごとに独立（2026-07-05確定）＝他難易度への伝播はしない
    }
    compileLayersToFlat(); metaDirty=true; }
  layerDrag=null; layerPan=null; });
ndcv.addEventListener('wheel', e=>{ if(ndView!=='layers') return; tlZoom(e); },{passive:false});   // ズーム/スクラブは下段Musicと共有
ndcv.addEventListener('mouseleave',()=>{ tlHoverBeat=null; _ndMouseY=-1; });
function syncLaneSb(){   // drawLayersから毎フレーム（変化時のみstyle書込）。拍数ルーラーには被らない=LRULERから下
  const padTop=50;   // 50=#nodepaneのpadding-top（canvas上端）
  for(const g of [['n','sbN'],['l','sbL']]){ const lk=g[0], el=document.getElementById(g[1]); if(el){
    const VP=laneVP(lk);
    const mx=laneMaxScroll(lk);
    if(mx<=0){ if(el.style.display!=='none'){ el.style.display='none'; } setScr(lk,0); continue; }
    const top=padTop+laneTopOf(lk);
    if(el.style.display!=='flex') el.style.display='flex';
    if(el._top!==top){ el._top=top; el.style.top=top+'px'; }
    if(el._h!==VP){ el._h=VP; el.style.height=VP+'px'; }
    const tr=el.querySelector('.sbTr'), th=el.querySelector('.sbTh');
    const trH=tr.clientHeight, thH=Math.max(22,trH*VP/Math.max(1,laneCountOf(lk)*laneHt()));
    const tY=mx>0?(scrOf(lk)/mx)*(trH-thH):0;
    if(th._h!==thH){ th._h=thH; th.style.height=thH+'px'; }
    if(Math.abs((th._y||0)-tY)>0.5){ th._y=tY; th.style.top=tY+'px'; }
  } } }
for(const g of [['n','sbN'],['l','sbL']]){ const lk=g[0], el=document.getElementById(g[1]);
  if(el){ const tr=el.querySelector('.sbTr'), th=el.querySelector('.sbTh');
    el.querySelector('.sbUp').addEventListener('click',()=>setScr(lk,scrOf(lk)-laneHt()));
    el.querySelector('.sbDn').addEventListener('click',()=>setScr(lk,scrOf(lk)+laneHt()));
    let dg=null;
    th.addEventListener('pointerdown',e2=>{ e2.preventDefault(); dg={y:e2.clientY,s0:scrOf(lk)};
      try{th.setPointerCapture(e2.pointerId);}catch(_){} });
    th.addEventListener('pointermove',e2=>{ if(!dg) return;
      const trH=tr.clientHeight, thH=th.clientHeight, mx=laneMaxScroll(lk);
      if(trH>thH) setScr(lk,dg.s0+(e2.clientY-dg.y)*mx/(trH-thH)); });
    th.addEventListener('pointerup',()=>{ dg=null; });
    tr.addEventListener('pointerdown',e2=>{ if(e2.target===th) return;   // 溝クリック=その位置へジャンプ
      const r2=tr.getBoundingClientRect(); setScr(lk,((e2.clientY-r2.top)/Math.max(1,r2.height))*laneMaxScroll(lk)); });
  } }
ovcv.addEventListener('pointermove',e=>{ const r=ovcv.getBoundingClientRect(), sx=e.clientX-r.left, sy=e.clientY-r.top;
  tlHoverBeat=(sx>=TLGUT)?Math.max(0,snapV(xToBeat(sx))):null;   // Musicレーン上でも黄ライン追従
  _ovEdgeHover=musicResize!=null||_musicBoxes.some(b=>Math.abs(sx-b.cx0)<=4||Math.abs(sx-b.cx1)<=4);   // 端=ew-resize
  _ovClipHover=_musicBoxes.some(b=>sx>=b.cx0&&sx<=b.cx1);   // クリップ本体上=grab
});
ovcv.addEventListener('mouseleave',()=>{ tlHoverBeat=null; });
ndcv.addEventListener('dblclick', e=>{ if(ndView!=='layers') return;   // クリップのヘッダー（ラベル帯）ダブルクリック=その場リネーム
  const r=ndcv.getBoundingClientRect(), sx=e.clientX-r.left, sy=e.clientY-r.top;
  if(sy>=LRULER-MKRH-TPRH&&sy<LRULER-MKRH){             // テンポパート帯: 既存の◆ダブルクリック=BPM手入力・空欄ダブルクリック=新規追加
    const hit=_tpRects.find(r2=>sx>=r2.x&&sx<=r2.x+r2.w&&sy>=r2.y&&sy<=r2.y+r2.h);
    if(hit){ const p=tempoParts[hit.i];
      ndInlineEdit({x:hit.x-2,y:hit.y,w:Math.max(70,hit.w+24),h:TPRH-2},String(p.bpm),v=>{
        const n=parseFloat(v); if(isFinite(n)&&n>0) setTempoPartBpm(hit.i,n); },false,ndcv); }
    else addTempoPartAt(lXToBeat(sx));
    return; }
  if(sy>=LRULER-MKRH&&sy<LRULER){                       // マーカー帯（数字の下）: ラベルのダブルクリック=改名（空にすると削除）
    const hit=_mkRects.find(r2=>sx>=r2.x&&sx<=r2.x+r2.w&&sy>=r2.y&&sy<=r2.y+r2.h);
    if(hit){ const mk=markers[hit.i];
      ndInlineEdit({x:hit.x-2,y:hit.y,w:Math.max(90,hit.w+24),h:MKRH-2},mk.name,v=>{ v=(v||'').trim();
        if(!v){ markers.splice(hit.i,1); stat('マーカーを削除しました'); }
        else { mk.name=v; stat(tf('msg.markerName','マーカー名: {name}',{name:v})); }
        metaDirty=true; },false,ndcv); }
    return; }
  if(sx<LGUT||sy<LRULER) return;
  const s=clipAtLayer(sx,sy); if(!s) return;
  const x=lBeatToX(s.beat||0), w=(s.len||4)*lPPB(), y=laneY(secLk(s),s.track||0)+4;
  if(sy>y+16) return;                                  // ヘッダー帯のみ対象（本体Wクリックは誤爆させない）
  const gx=Math.max(LGUT,x);
  ndInlineEdit({x:gx+2,y:y,w:Math.min(x+w,ndW)-gx-4,h:16},s.label||'',nm=>{
    if(nm.trim()){ snapshot('node');
      s.label=nm.trim(); metaDirty=true; stat(tf('msg.clipRename','クリップ名を変更: {label}',{label:s.label})); } });
});
function setNdView(v){ ndView=v; if(v==='layers') layerFit(); }   // ビューはlayers固定（NODEトグルはDOMごと廃止済み）
// NODEビューは廃止（トグル削除）。ndView は 'layers' 固定。

// ============ M1: 区間操作 + パターンライブラリ ============
const MIR_D={0:0,1:1,2:3,3:2,4:5,5:4,6:7,7:6,8:8};   // 左右ミラーの向き変換
function sectionRange(s){
  const ordered=[...sections].sort((a,b)=>a.beat-b.beat);
  const i=ordered.indexOf(s);
  return [s.beat, ordered[i+1]?ordered[i+1].beat:Math.max(s.beat+4,Math.ceil(ovBeats||s.beat+16))];
}
function headBeat(o){ return o.kind==='arc'||o.kind==='chain'?o.b:o.beat; }
function inRegion(o,b0,b1){ const b=headBeat(o); return b>=b0-1e-4&&b<b1-1e-4; }
function regionObjs(b0,b1){ return [...notes,...bombs,...walls,...arcs,...chains].filter(o=>inRegion(o,b0,b1)); }
function extractRegion(b0,b1){
  const frag={len:b1-b0,notes:[],bombs:[],walls:[],arcs:[],chains:[]};
  for(const o of regionObjs(b0,b1)){
    const c={...o,raw:null};
    if(o.kind==='arc'||o.kind==='chain'){ c.b=o.b-b0; c.tb=o.tb-b0; }
    else c.beat=o.beat-b0;
    frag[o.kind==='note'?'notes':o.kind==='bomb'?'bombs':o.kind==='wall'?'walls':o.kind==='arc'?'arcs':'chains'].push(c);
  }
  return frag;
}
function pasteFragment(frag,at){
  snapshot();
  const made=[];
  const mk=(c)=>{ const o={...c,raw:null};
    if(o.kind==='arc'||o.kind==='chain'){ o.b=c.b+at; o.tb=c.tb+at; }
    else o.beat=c.beat+at;
    arrOf(o.kind).push(o); addObj(o); made.push(o); return o; };
  [...frag.notes,...frag.bombs,...frag.walls,...frag.arcs,...frag.chains].forEach(mk);
  selection=new Set(made);
  stat(tf('msg.pasteN','貼り付け: {n}個 → 拍 {at}',{n:made.length,at}));
}
function mirrorRegion(b0,b1){
  snapshot(); let n=0;
  for(const o of regionObjs(b0,b1)){ n++;
    if(o.kind==='note'){ o.x=3-o.x; o.d=MIR_D[o.d]??o.d; o.c=o.c===0?1:0; }
    else if(o.kind==='bomb'){ o.x=3-o.x; }
    else if(o.kind==='wall'){ o.x=3-o.x-(o.w-1); }
    else { o.x=3-o.x; o.tx=3-o.tx; o.d=MIR_D[o.d]??o.d; o.c=o.c===0?1:0;
      if(o.kind==='arc') o.tc=MIR_D[o.tc]??o.tc; }
    refreshMesh(o); }
  stat(tf('msg.mirrorApply','ミラー適用 ×{n}（左右+色反転）',{n}));
}
const MIR_ET={2:3,3:2,12:13,13:12};   // ライトの左右ペア（L LASER⇄R LASER・L SPEED⇄R SPEED）。RING/CENTER/BACK/BOOSTは左右の対が無いのでそのまま
function mirrorClip(s){   // クリップ単位の左右反転（位置=左右ミラー・色=赤⇄青）。真実はcontent側なのでflatではなくcontentを直接反転する
  if(!s||s.kind==='null') return;
  if(_flatDirty) flushFlatEdits();   // 未同期の3D編集を先にcontentへ確定（後のflushで反転結果が巻き戻るのを防ぐ）
  snapshot('node');                  // contentはnodeドメイン（sections）に含まれる＝Undoで戻る
  if(!s.gid) s.gid='g'+(++_nid);
  const c=s.content||{}; let n=0;
  for(const o of (c.notes||[])){ o.x=3-o.x; o.d=MIR_D[o.d]??o.d; o.c=o.c===0?1:0; n++; }
  for(const o of (c.bombs||[])){ o.x=3-o.x; n++; }
  for(const o of (c.walls||[])){ o.x=3-o.x-((o.w||1)-1); n++; }   // 壁は幅のぶん左端を戻す（mirrorRegionと同一式）
  for(const o of (c.arcs||[])){ o.x=3-o.x; o.tx=3-o.tx; o.d=MIR_D[o.d]??o.d; o.tc=MIR_D[o.tc]??o.tc; o.c=o.c===0?1:0; n++; }
  for(const o of (c.chains||[])){ o.x=3-o.x; o.tx=3-o.tx; o.d=MIR_D[o.d]??o.d; o.c=o.c===0?1:0; n++; }
  for(const ev of (c.lights||[])){
    const isCol=laneKind(ev.et)==='color';   // iが色なのはcolorレーンだけ。SPEED=回転速度・BOOST=ON/OFF・RINGトリガーのiは色ではないので絶対に触らない
    ev.et=MIR_ET[ev.et]??ev.et;              // （左右ペアは種別が同じなので判定は反転前後どちらでも同値）
    if(isCol&&ev.i>=1&&ev.i<=8) ev.i=ev.i<=4?ev.i+4:ev.i-4;   // 赤系⇄青系（i=0のOFF・i>=9の白は対象外＝flipLightColorsと同じ流儀）
    n++; }
  compileLayersToFlat(); metaDirty=true;
  stat(tf('msg.mirrorClip','左右反転 ×{n}（位置＋色）',{n}));
}
function deleteRegionContents(b0,b1){
  snapshot(); const objs=regionObjs(b0,b1);
  objs.forEach(o=>removeObj(o));
  stat(tf('msg.regionClear','区間の中身を削除 ×{n}',{n:objs.length}));
}
// ---- 右クリックメニュー ----
const ctxEl=document.getElementById('ctxmenu');
function showMenu(x,y,items){   // 項目=[ラベル, 関数] または [ラベル, サブ項目配列]（配列=ホバーで右横にカスケード展開）
  ctxEl.innerHTML='';
  let sub=null, subFor=null;
  const closeSub=()=>{ if(sub){ sub.remove(); sub=null; } if(subFor){ subFor.classList.remove('subOpen'); subFor=null; } };
  items.forEach(([label,fn])=>{
    if(label==='---'){ const dv=document.createElement('div'); dv.className='ctxdiv'; ctxEl.appendChild(dv); return; }   // '---'=区切り線
    const b=document.createElement('button'); b.textContent=label;
    if(Array.isArray(fn)){
      b.classList.add('hasSub');
      const open=()=>{ if(subFor===b) return; closeSub();
        sub=document.createElement('div'); sub.className='ctxsub'; subFor=b; b.classList.add('subOpen');
        fn.forEach(([l2,f2])=>{ const b2=document.createElement('button'); b2.textContent=l2;
          b2.onclick=()=>{ hideMenu(); f2(); }; sub.appendChild(b2); });
        sub.style.top=b.offsetTop+'px'; ctxEl.appendChild(sub);
        const r=sub.getBoundingClientRect();   // 右にはみ出すなら左側へ・下は画面内へ
        if(r.right>innerWidth-4) sub.style.left=(-r.width+3)+'px';
        if(r.bottom>innerHeight-4) sub.style.top=(b.offsetTop-(r.bottom-innerHeight)-4)+'px'; };
      b.addEventListener('mouseenter',open);
      b.onclick=open;   // クリックでも開ける（タッチ/ペン用）
    } else {
      b.addEventListener('mouseenter',closeSub);   // 通常項目に乗ったらサブを閉じる
      b.onclick=()=>{ hideMenu(); fn(); };
    }
    ctxEl.appendChild(b); });
  ctxEl.style.display='block';
  ctxEl.style.left=Math.min(x,innerWidth-200)+'px'; ctxEl.style.top=Math.min(y,innerHeight-items.length*34-10)+'px';
}
var _menuHidAt=0;   // メニューが閉じた時刻（同じクリックでの即再オープン=トグル判定用）
function hideMenu(){ ctxEl.style.display='none'; ctxEl.classList.remove('overPanel'); _menuHidAt=performance.now(); }
function closeFloatUI(){ hideMenu(); const cp=document.getElementById('cpanel'); if(cp) cp.remove(); }   // 浮いているメニュー/カラーピッカーを閉じる
// 書き出しの充足チェック（配線＋内容から自動判定。必須=音源・難易度）
function exportReadiness(){
  const okAudio=sigConnected('audio')&&!!audioBuf;
  const okDiff=!!(graphIO&&graphIO.out&&graphIO.out.diffs&&Object.values(graphIO.out.diffs).some(v=>v));   // 1つ以上の難易度が選択されていればOK（ノーツ有無は不問＝壁だけの譜面も許可）
  const ib=infoBase||{};   // 曲情報=infoBaseが真実（INFOノードエディタの確定情報。旧チェーン参照は廃止）
  const nm=ib._songName||'', ar=ib._songAuthorName||'', la=ib._levelAuthorName||'';
  const covOn=extraNodes.some(x=>x.kind==='cover'
    &&graphEdges.some(e=>e.sig==='cover'&&e.fromId===x.id&&e.toId==='out')&&(x.handle||x.name));
  const okLights=sigConnected('lights')&&lightEvents.length>0;
  const okFolderName=!!(graphIO&&graphIO.out&&graphIO.out.folderName);
  const okOutDir=!!outDirHandle;
  return [
    {label:TL('rd.outdir','CustomLevelsフォルダ'), ok:okOutDir, req:true},
    {label:TL('rd.folderName','フォルダー名'), ok:okFolderName, req:true},
    {label:TL('rd.audio','音源（song.egg）'), ok:okAudio, req:true},
    {label:TL('rd.diff','難易度（1つ以上選択）'), ok:okDiff, req:true},
    {label:TL('rd.songName','曲名'), ok:!!nm, req:false},
    {label:TL('rd.artist','アーティスト名'), ok:!!ar, req:false},
    {label:TL('rd.mapper','譜面制作者名'), ok:!!la, req:false},
    {label:TL('rd.cover','カバー画像'), ok:covOn, req:false},
    {label:TL('rd.lights','ライト'), ok:okLights, req:false},
  ];
}
addEventListener('pointerdown', e=>{ if(!ctxEl.contains(e.target)) hideMenu(); }, true);





// ---- ピアノロール式タイムライン（下段・12レーン簡易表示） ----
const prcv=document.getElementById('prcv'), prg=prcv.getContext('2d');
let prW=0, prH=0;
function prResize(){ const r=prcv.parentElement.getBoundingClientRect();
  prW=r.width; prH=r.height; prcv.width=prW*devicePixelRatio; prcv.height=prH*devicePixelRatio;
  prg.setTransform(devicePixelRatio,0,0,devicePixelRatio,0,0); }
function drawPRoll(curV){
  if(!prW) return;
  prg.clearRect(0,0,prW,prH);
  // 音タイムラインと同じ時間窓（完全連動・赤線が2段を貫く）
  const w=tlWindow(curV);
  const frac=w.frac, b0=w.b0, pxb=(prW-TLGUT)/w.span, PR_SPAN=w.span;
  const laneH=prH/12;
  // レーン帯（列ごとに濃淡）
  for(let i=0;i<12;i++){ const col=(i/3)|0;
    prg.fillStyle=col%2?'rgba(255,255,255,.015)':'rgba(255,255,255,.035)';
    prg.fillRect(TLGUT,i*laneH,prW-TLGUT,laneH); }
  // セクション帯 + 上部ラベル帯（接続されているノードのレンジだけ）
  if(ovBeats){
    for(const t of timelineSections()){
      const e0=t.b0, e1=t.b1, sec=t.sec;
      if(e1<b0||e0>b0+PR_SPAN) continue;
      const x0=Math.max(TLGUT,TLGUT+(e0-b0)*pxb), x1=Math.min(prW,TLGUT+(e1-b0)*pxb);
      const col=SEC_COLORS[sections.indexOf(sec)%SEC_COLORS.length];
      prg.fillStyle=col+'14'; prg.fillRect(x0,0,x1-x0,prH);
      prg.save(); prg.beginPath(); prg.rect(x0,0,x1-x0,PR_TAG_H); prg.clip();
      prg.fillStyle=col+'3a'; prg.fillRect(x0,0,x1-x0,PR_TAG_H);
      prg.fillStyle='#e8f4ff'; prg.font='bold 10px '+FONT; prg.textBaseline='middle';
      prg.fillText(sec.label,x0+5,PR_TAG_H/2+0.5); prg.restore();
      const fx=TLGUT+(e0-b0)*pxb;
      if(fx>=TLGUT-2&&fx<=prW+2){ prg.fillStyle=col; prg.fillRect(fx-1,0,2,prH); }
    }
  }
  // 拍線
  for(let b=Math.ceil(b0);b<b0+PR_SPAN;b++){ const x=TLGUT+(b-b0)*pxb; if(x<TLGUT) continue;
    prg.strokeStyle=(b%4===0)?'rgba(130,130,130,.5)':'rgba(70,70,70,.55)';
    prg.lineWidth=(b%4===0)?1.6:1;
    prg.beginPath(); prg.moveTo(x,0); prg.lineTo(x,prH); prg.stroke(); }
  // ノーツ（レーン= 列*3 + (2-段)）
  for(const n of notes){ if(n.beat<b0||n.beat>b0+PR_SPAN) continue;
    const lane=n.x*3+(2-n.y), x=TLGUT+(n.beat-b0)*pxb;
    prg.fillStyle=n.c===0?cRED:cBLUE;
    prg.fillRect(x-2,lane*laneH+1.5,4,laneH-3); }
  for(const n of bombs){ if(n.beat<b0||n.beat>b0+PR_SPAN) continue;
    const lane=n.x*3+(2-n.y), x=TLGUT+(n.beat-b0)*pxb;
    prg.fillStyle='#888899'; prg.fillRect(x-1.5,lane*laneH+3,3,laneH-6); }
  // 壁（帯）
  for(const o of walls){ if(o.beat+o.dur<b0||o.beat>b0+PR_SPAN) continue;
    const x0=TLGUT+(o.beat-b0)*pxb, x1=TLGUT+(o.beat+o.dur-b0)*pxb;
    const l0=o.x*3, rows=Math.max(1,Math.min(o.h,3-o.y));
    const yTop=(o.x*3+(2-(o.y+rows-1)))*laneH;
    prg.fillStyle='rgba(208,48,96,.30)';
    prg.fillRect(x0,yTop,Math.max(2,x1-x0),rows*laneH*(o.w));   // 簡易: 幅方向は概略
  }
  // 再生ヘッド（全体タイムラインとX一致・▼付き）
  const px=TLGUT+(curV-b0)*pxb;
  prg.fillStyle='#ff3344'; prg.fillRect(px-1,0,2,prH);
  prg.beginPath(); prg.moveTo(px-5,0); prg.lineTo(px+5,0); prg.lineTo(px,7); prg.closePath(); prg.fill();
  // 赤バーの上に現在の小節数（4/4想定: 拍/4+1）
  if(px>=-30&&px<=prW+30){
    const meas=String(Math.floor(Math.max(0,curV)/4)+1);
    prg.font='bold 10px '+FONT; prg.textAlign='center'; prg.textBaseline='middle';
    const tw=prg.measureText(meas).width+12;
    prg.fillStyle='rgba(18,18,18,.92)';
    prg.beginPath(); prg.roundRect(px-tw/2,1.5,tw,13,4); prg.fill();
    prg.strokeStyle='#ff3344'; prg.lineWidth=1;
    prg.beginPath(); prg.roundRect(px-tw/2,1.5,tw,13,4); prg.stroke();
    prg.fillStyle='#ff6a7a'; prg.fillText(meas,px,8.5);
    prg.textAlign='left';
  }
  // 左溝（支点をレイヤービューのLGUTと揃える）
  prg.fillStyle='#212121'; prg.fillRect(0,0,TLGUT,prH);
  prg.strokeStyle='#161616'; prg.lineWidth=1; prg.beginPath(); prg.moveTo(TLGUT,0); prg.lineTo(TLGUT,prH); prg.stroke();
  prg.fillStyle='#8a8a8a'; prg.font='bold 10px '+FONT; prg.textAlign='left'; prg.textBaseline='middle'; prg.fillText('Notes',8,prH/2);
}
let prSeek=false;
function prSeekTo(clientX){
  const r=prcv.getBoundingClientRect(), x=clientX-r.left;
  const w=tlWindow(cur);
  cur=Math.max(0,snapV(w.b0+(x-TLGUT)/(prW-TLGUT)*w.span)); offset=beatToTimeTM(cur);
}
prcv.addEventListener('pointerdown', e=>{
  const r=prcv.getBoundingClientRect(), x=e.clientX-r.left, y=e.clientY-r.top;
  if(ovBeats&&y<PR_TAG_H){                   // 上部ラベル帯: 旗の操作
    const sc=secAtPr(x);
    if(e.button===2){ if(sc){ sections=sections.filter(v=>v!==sc); metaDirty=true; } return; }
    if(e.button===0&&sc){ tlFrozen=tlWindow(cur); tgDrag={sec:sc}; return; }
  }
  if(e.button!==0) return;
  if(playing) pause();
  tlFrozen=tlWindow(cur);                    // ドラッグ中は窓を固定
  prSeek=true; prSeekTo(e.clientX);
});
prcv.addEventListener('dblclick', e=>{
  if(!ovBeats) return;
  const r=prcv.getBoundingClientRect();
  if(e.clientY-r.top>=PR_TAG_H) return;
  const sc=secAtPr(e.clientX-r.left);
  if(sc){ const nm=prompt('セクション名',sc.label); if(nm){ sc.label=nm; metaDirty=true; } }
});
prcv.addEventListener('contextmenu',e=>e.preventDefault());
addEventListener('pointermove', e=>{ if(prSeek) prSeekTo(e.clientX); });
addEventListener('pointerup', ()=>{ if(prSeek){ prSeek=false; tlFrozen=null; } });
prcv.addEventListener('wheel',tlZoom,{passive:false});

let metaDirty=false;

// textures / geometry
function makeTex(draw){ const c=document.createElement('canvas'); c.width=c.height=128; const g=c.getContext('2d');
  draw(g); const t=new THREE.CanvasTexture(c); t.anisotropy=4; return t; }
const arrowTex=makeTex(g=>{ g.lineJoin='round'; g.lineCap='round'; g.lineWidth=8;
  g.strokeStyle='#fff'; g.fillStyle='#fff';
  // 実物準拠: 矢印は切る方向と逆側の縁に付く（↑ノーツは下端に▲、↓ノーツは上端に▼）
  g.beginPath(); g.moveTo(64,78); g.lineTo(112,112); g.lineTo(16,112); g.closePath(); g.stroke(); g.fill(); });
const dotTex=makeTex(g=>{ g.fillStyle='#fff'; g.beginPath(); g.arc(64,64,23,0,7); g.fill(); });
/** チェーン親用: 中央▲（縁寄せだと半分高さの箱で角に潰れて見える） */
const chainHeadArrowTex=makeTex(g=>{ g.lineJoin='round'; g.lineCap='round'; g.lineWidth=8;
  g.strokeStyle='#fff'; g.fillStyle='#fff';
  g.beginPath(); g.moveTo(64,32); g.lineTo(108,96); g.lineTo(20,96); g.closePath(); g.stroke(); g.fill(); });
const markGeo=new THREE.PlaneGeometry(0.4,0.4);
/** 親ノーツ正面に収まるマーク面（幅は通常と同じ・高さは半分箱に合わせる） */
const chainHeadMarkGeo=new THREE.PlaneGeometry(0.4,0.18);
const noteGeo=makeChamferBoxGeometry(0.46,0.46,0.46,NOTE_CORNER_CUT);
const NOTE_THIN=0.25;   // NOTES編集ビューでのノーツ奥行き=1/4（1/8連打でも読める板状）。プレビューは実寸のまま
const arrowMatS=new THREE.MeshBasicMaterial({map:arrowTex,transparent:true});
const dotMatS=new THREE.MeshBasicMaterial({map:dotTex,transparent:true});
const chainHeadArrowMatS=new THREE.MeshBasicMaterial({map:chainHeadArrowTex,transparent:true});
function makeSpikyBomb(R,sl,sr){   // 黒トゲトゲのボム: icosphere＋20本の四角錐トゲを1ジオメトリに合成（起動時1回）
  const parts=[new THREE.IcosahedronGeometry(R,1)];
  const dirs=new THREE.DodecahedronGeometry(1,0), pos=dirs.attributes.position, seen=new Set(), up=new THREE.Vector3(0,1,0);
  for(let i=0;i<pos.count;i++){ const v=new THREE.Vector3().fromBufferAttribute(pos,i).normalize();
    const key=v.toArray().map(x=>x.toFixed(2)).join(','); if(seen.has(key)) continue; seen.add(key);
    const cone=new THREE.ConeGeometry(sr,sl,4).toNonIndexed();   // 四角錐トゲ（非index化＝icosphereと揃えて合成可能に）
    cone.applyMatrix4(new THREE.Matrix4().compose(v.clone().multiplyScalar(R*0.92+sl*0.5), new THREE.Quaternion().setFromUnitVectors(up,v), new THREE.Vector3(1,1,1)));
    parts.push(cone); }
  return mergeGeometries(parts);
}
const bombGeo=makeSpikyBomb(0.17,0.1,0.06);
const chainHeadGeo=makeChainHeadGeometry();
const chainLinkGeo=makeChainLinkGeometry();
// 共有マテリアル/ジオメトリ（再構築のたびに生成しない: リーク対策）
const bombMat=new THREE.MeshStandardMaterial({color:0x0c0c0e,emissive:0x000000,metalness:.55,roughness:.4});   // 黒（赤発光なし）
const bombRingGeo=new THREE.TorusGeometry(0.23,0.02,6,20);
const bombRingMat=new THREE.MeshBasicMaterial({color:0x666677});
const wallMat=new THREE.MeshBasicMaterial({color:0xa0103a,transparent:true,opacity:0.30,depthWrite:false});
const wallEdgeMat=new THREE.LineBasicMaterial({color:0xd03060});
const arcMats=[new THREE.MeshBasicMaterial({color:RED, transparent:true,opacity:0.7}),
               new THREE.MeshBasicMaterial({color:BLUE,transparent:true,opacity:0.7})];

// 選択インジケータ
const selGeom=new THREE.BoxGeometry(0.465,0.465,0.465);   // ノーツ(0.46)にピッタリ密着（隙間なし）
const selEdge=new THREE.EdgesGeometry(selGeom);
// 箱(0.465立方)を対象オブジェクトへ密着させる。選択枠(selPool)とホバー枠(hoverBox)で共用＝二重管理でズレない
function fitBoxTo(sb,o,m){
  if(o.kind==='note'||o.kind==='bomb'){ sb.scale.set(1,1,o.kind==='note'?NOTE_THIN:1); sb.position.copy(m.group.position);
    sb.rotation.z=(o.kind==='note'&&o.d>=4&&o.d<=7)?Math.PI/4:0; }   // 斜めノーツは箱ごと回して密着・厚みもノーツに追従
  else if(o.kind==='wall'){ const {hh,cx,cy,len}=wallDims(o);   // 壁は全体を包む（選択箱の実寸=0.465で割る＝壁にぴったり）
    sb.rotation.z=0;
    sb.position.set(cx,cy,m.group.position.z+len/2);
    sb.scale.set((o.w*LANE+0.04)/0.465,(hh*LAYER+0.04)/0.465,(len+0.08)/0.465); }
  else if(o.kind==='chain'){ const b=chainBounds(o);
    sb.rotation.z=0;
    sb.position.set(b.cx,b.cy,m.group.position.z+b.cz);
    sb.scale.set(b.sx/0.465,b.sy/0.465,b.sz/0.465); }
  else { const b=arcBounds(o);   // アーク=曲線全体を包む（旧: 頭マスに小箱だけで分かりづらい＝ヘルバ様指摘）
    sb.rotation.z=0;
    sb.position.set(b.cx,b.cy,m.group.position.z+b.cz);
    sb.scale.set(b.sx/0.465,b.sy/0.465,b.sz/0.465); }
}
// マウス直下のノーツ/ライトを黄色枠で囲う（どれの上にいるのか分かりづらい＝ヘルバ様指定 2026-07-17）。
// 黄色=このアプリでは「マウス位置」の色（マウス拍ラインと同色）
const hoverBox=new THREE.LineSegments(selEdge,new THREE.LineBasicMaterial({color:0xffd82d,transparent:true,opacity:0.95}));
hoverBox.visible=false; hoverBox.raycast=()=>{}; hoverBox.renderOrder=7; scene.add(hoverBox); tagHelper(hoverBox);
const selPool=[];
let chainSelPart='head';   // チェーンをどの部位で選択したか: 'head'=緑枠+全体移動ギズモ / 'child'=青枠+分割・曲率スライダー（ヘルバ様指定）
function ensureSelPool(n){ while(selPool.length<n){ const g=new THREE.Group();
  g.add(new THREE.Mesh(selGeom,new THREE.MeshBasicMaterial({color:0x50ffb8,transparent:true,opacity:0.18,depthWrite:false})));
  g.add(new THREE.LineSegments(selEdge,new THREE.LineBasicMaterial({color:0x50ffb8})));
  g.visible=false; scene.add(g); tagHelper(g); selPool.push(g); } }
// 重複インジケータ: 選択ボックスより一回り大きい黄色枠（本体の色替えだと黄色ノーツ/レーザーと紛れるため）
const dupPool=[];
function ensureDupPool(n){ while(dupPool.length<n){ const g=new THREE.Group();
  g.add(new THREE.Mesh(selGeom,new THREE.MeshBasicMaterial({color:0xffd82d,transparent:true,opacity:0.13,depthWrite:false})));
  g.add(new THREE.LineSegments(selEdge,new THREE.LineBasicMaterial({color:0xffd82d})));
  g.traverse(c=>{ c.raycast=()=>{}; });   // 表示専用: レイキャストに当たらない（枠が中のノーツへのクリックを遮るバグの防止）
  g.visible=false; scene.add(g); tagHelper(g); dupPool.push(g); } }
// 複数選択時に全体を囲む大きい枠（個別の小さい枠はそのまま残す）
const groupSelBox=new THREE.LineSegments(new THREE.EdgesGeometry(new THREE.BoxGeometry(1,1,1)),new THREE.LineBasicMaterial({color:0x50ffb8,transparent:true,opacity:0.55}));
groupSelBox.visible=false; groupSelBox.raycast=()=>{}; scene.add(groupSelBox); tagHelper(groupSelBox);

// マテリアルは赤/青の2個を全ノーツで共有（ドローコール/メモリ削減）
const NOTE_MATS=[
  new THREE.MeshStandardMaterial({color:RED, emissive:RED, emissiveIntensity:0.2,metalness:.05,roughness:.5,flatShading:true}),   // 純色に寄せる: 半金属(暗背景の反射)をやめ弱く自己発光
  new THREE.MeshStandardMaterial({color:BLUE,emissive:BLUE,emissiveIntensity:0.2,metalness:.05,roughness:.5,flatShading:true}),
];
// 白枠（判定面）通過直後の発光用（共有マテリアル差し替え方式）
const NOTE_MATS_HOT=[
  new THREE.MeshStandardMaterial({color:RED, emissive:RED, emissiveIntensity:0.85,metalness:.05,roughness:.5,flatShading:true}),
  new THREE.MeshStandardMaterial({color:BLUE,emissive:BLUE,emissiveIntensity:0.85,metalness:.05,roughness:.5,flatShading:true}),
];
// LIGHT編集モード時、編集ビューのノーツだけ少し暗くする専用マテリアル（プレビューはNOTE_MATSのまま＝通常）。色はapplyModeDimでRED/BLUEを減光して同期
const NOTE_MATS_DIM=[
  new THREE.MeshStandardMaterial({color:RED, emissive:RED, emissiveIntensity:0.2,metalness:.05,roughness:.5,flatShading:true}),
  new THREE.MeshStandardMaterial({color:BLUE,emissive:BLUE,emissiveIntensity:0.2,metalness:.05,roughness:.5,flatShading:true}),
];
const NOTE_MATS_GHOST=[NOTE_MATS[0].clone(),NOTE_MATS[1].clone()];   // 3Dペースト追従中（配置前）のノーツ本体＝半透明ゴースト
NOTE_MATS_GHOST.forEach(m=>{ m.transparent=true; m.opacity=0.3; m.depthWrite=false; });
function mat(c){ return NOTE_MATS[c===0?0:1]; }
// ---- 重複チェック（TODO10）: 同拍・同位置のノーツ/ボム、同拍・同レーンのライトを検出（黄色枠＋件数チップ＋‹›ジャンプ） ----
let dupNoteSet=new Set(), dupLightSet=new Set(), dupNoteBeats=[], dupLightBeats=[], dupNoteCount=0, dupLightCount=0;
let dupNoteList=[], dupLightList=[], _dupNoteIdx=-1, _dupLightIdx=-1;   // 重複アイテムを1個ずつ選択移動する用（拍順の配列＋現在位置）
let dupChainCells=new Map();   // 重複チェーン → 衝突マス[{beat,x,y}] （黄色枠を衝突している頭/尾のマスに描くため）
function scanDups(){
  const m=new Map();
  const put=(o,beat,x,y)=>{ const k=Math.round((beat||0)*960)+'|'+(x||0)+'|'+(y||0);
    const a=m.get(k)||[]; a.push({o,beat:beat||0,x:x||0,y:y||0}); m.set(k,a); };
  for(const o of notes) put(o,o.beat,o.x,o.y);
  for(const o of bombs) put(o,o.beat,o.x,o.y);
  // チェーンの頭・尾のマスも重複判定に参加（通常ノーツを重ねたら警告＝ヘルバ様指示）。頭=尾の退化形は1回だけ登録
  for(const c of chains){ put(c,c.b,c.x,c.y);
    if(!(Math.abs((c.b||0)-(c.tb||0))<1e-4&&c.x===c.tx&&c.y===c.ty)) put(c,c.tb,c.tx,c.ty); }
  dupNoteSet=new Set(); dupChainCells=new Map(); const nb=new Set(); dupNoteCount=0;
  for(const a of m.values()){ const uniq=new Set(a.map(e=>e.o));
    if(uniq.size>1){ dupNoteCount++; nb.add(a[0].beat);   // 箇所=グループ数（同拍の別マスは別カウント）
      for(const e of a){ dupNoteSet.add(e.o);
        if(e.o.kind==='chain'){ const arr=dupChainCells.get(e.o)||[]; arr.push({beat:e.beat,x:e.x,y:e.y}); dupChainCells.set(e.o,arr); } } } }
  const ml=new Map();
  for(const ev of lightEvents){ const k=Math.round((ev.beat||0)*960)+'|'+ev.et;
    const a=ml.get(k)||[]; a.push(ev); ml.set(k,a); }
  dupLightSet=new Set(); const lb=new Set(); dupLightCount=0;
  for(const a of ml.values()) if(a.length>1){ dupLightCount++; a.forEach(o=>dupLightSet.add(o)); lb.add(a[0].beat||0); }
  dupNoteBeats=[...nb].sort((a,b)=>a-b); dupLightBeats=[...lb].sort((a,b)=>a-b);
  dupNoteList=[...dupNoteSet].sort((a,b)=>((((a.beat??a.b))||0)-(((b.beat??b.b))||0))||((a.x||0)-(b.x||0))||((a.y||0)-(b.y||0)));   // 個々の重複アイテム（拍→列→段順。チェーンは頭拍b）
  dupLightList=[...dupLightSet].sort((a,b)=>((a.beat||0)-(b.beat||0))||((a.et||0)-(b.et||0))||((a.i||0)-(b.i||0)));
  if(_dupNoteIdx>=dupNoteList.length) _dupNoteIdx=-1; if(_dupLightIdx>=dupLightList.length) _dupLightIdx=-1;
}
// ‹›=重複アイテムを1個ずつ選択して移動（kind: 'n'=ノーツ/ボム, 'l'=ライト）
function dupJumpItem(kind,dir){
  const list=kind==='n'?dupNoteList:dupLightList;
  if(!list.length) return; if(playing) pause();
  let idx=kind==='n'?_dupNoteIdx:_dupLightIdx;
  const selSet=kind==='n'?selection:lightSelection;   // 現在の単一選択が重複アイテムなら、その位置から移動
  if(selSet.size===1){ const p=list.indexOf([...selSet][0]); if(p>=0) idx=p; }
  idx=(idx<0)?(dir>0?0:list.length-1):(((idx+dir)%list.length)+list.length)%list.length;   // 端でループ
  if(kind==='n') _dupNoteIdx=idx; else _dupLightIdx=idx;
  const it=list[idx];
  if(kind==='n'){ selection=new Set([it]); lightSelection.clear(); gizmoMode=it.kind==='chain'?null:'move'; }
  else { lightSelection=new Set([it]); selection.clear(); }
  seekEase(((it.beat??it.b))||0);
  const dz=0-controls.target.z; camera.position.z+=dz; controls.target.z+=dz; controls.update();   // 着地点を画面中央へ（.キーと同流儀）
  stat(tf('msg.dupNav','重複{kind} {n}/{total} を選択',{kind:kind==='n'?t('word.notes','ノーツ'):t('word.light','ライト'),n:idx+1,total:list.length}));
}

// ============ data & meshes ============
// note:{kind:'note',beat,x,y,c,d,raw} bomb:{kind:'bomb',beat,x,y,raw}
// wall:{kind:'wall',beat,x,y,dur,w,h,raw} arc:{kind:'arc',b,c,x,y,d,mu,tb,tx,ty,tc,tmu,m,raw}
// chain:{kind:'chain',b,c,x,y,d,tb,tx,ty,sc,s,raw}  raw.cpm/la/s2d/fcp=曲線調整（標準外）
let notes=[], bombs=[], walls=[], arcs=[], chains=[];
/** チェーン曲線のグローバル既定（新規チェイン・raw未指定時） */
let chainCurveGlobal={...CHAIN_CURVE_DEFAULTS};
let meshes=[]; // {obj,group}
function cellPos(x,y){ return [(1.5-x)*LANE+NOTE_DX, BASE_Y+y*LAYER]; }   // レーン軸反転（NLE基準）＋ノーツ帯のXオフセット。ノーツ側のワールドXは必ずここを通す

function buildNote(n){
  const g=new THREE.Group();
  const box=new THREE.Mesh(noteGeo,mat(n.c)); box.userData.obj=n;
  if(n.d>=4&&n.d<=7) box.rotation.z=-Math.PI/4;   // レーン軸反転に伴う鏡映
  g.add(box); g.userData.body=box;   // 通過発光でマテリアルを差し替えるためのボディ参照
  g.scale.z=NOTE_THIN;               // 編集ビューは1/4厚（プレビュー描画の直前だけ実寸に戻す）
  attachNoteArrowMarks(g, n.d, n, 0);
  const [px,py]=cellPos(n.x,n.y); g.userData.obj=n; g.position.set(px,py,(n.beat-cur)*ZPB); return g;
}
// 通常ノーツと同一の矢印/ドット貼り付け
const NOTE_MARK_Z=0.235;
/** 下半分カット後の箱中心（下面=セル中心 y=0） */
const CHAIN_HEAD_LIFT=CHAIN_HEAD_SIZE.h/2;
function attachNoteArrowMarks(grp, d, obj, markY=0){
  if(d===8){
    const m=new THREE.Mesh(markGeo,dotMatS);
    m.position.set(0,markY,-NOTE_MARK_Z); m.rotation.set(0,Math.PI,0); m.userData.obj=obj; grp.add(m);
    const mb=new THREE.Mesh(markGeo,dotMatS);
    mb.position.set(0,markY,NOTE_MARK_Z); mb.rotation.set(0,0,0); mb.userData.obj=obj; grp.add(mb);
    return;
  }
  const deg=DIR_ANGLE[d]??0;
  const m=new THREE.Mesh(markGeo,arrowMatS);
  m.position.set(0,markY,-NOTE_MARK_Z);
  m.rotation.set(0,Math.PI,-THREE.MathUtils.degToRad(deg));
  m.userData.obj=obj; grp.add(m);
  const mb=new THREE.Mesh(markGeo,arrowMatS);
  mb.position.set(0,markY,NOTE_MARK_Z);
  mb.rotation.set(0,0,THREE.MathUtils.degToRad(deg));
  mb.userData.obj=obj; grp.add(mb);
}
/** チェーン親専用: 中央▲を箱中心に置く（通常ノーツの縁寄せ▲は半分箱で角に潰れる）。
    箱が向きに完全回転する（リファレンス図準拠）ため、マーク位置も回転後の箱中心へ追従させる */
function attachChainHeadMarks(grp, d, obj){
  const [mx,my]=chainHeadBoxOffset(chainBoxRotZ(d));   // 回転後の箱中心
  if(d===8){
    const m=new THREE.Mesh(markGeo,dotMatS);
    m.position.set(mx,my,-NOTE_MARK_Z); m.rotation.set(0,Math.PI,0); m.userData.obj=obj; grp.add(m);
    const mb=new THREE.Mesh(markGeo,dotMatS);
    mb.position.set(mx,my,NOTE_MARK_Z); mb.rotation.set(0,0,0); mb.userData.obj=obj; grp.add(mb);
    return;
  }
  const deg=DIR_ANGLE[d]??0;
  const m=new THREE.Mesh(chainHeadMarkGeo,chainHeadArrowMatS);
  m.position.set(mx,my,-NOTE_MARK_Z);
  m.rotation.set(0,Math.PI,-THREE.MathUtils.degToRad(deg));
  m.userData.obj=obj; grp.add(m);
  const mb=new THREE.Mesh(chainHeadMarkGeo,chainHeadArrowMatS);
  mb.position.set(mx,my,NOTE_MARK_Z);
  mb.rotation.set(0,0,THREE.MathUtils.degToRad(deg));
  mb.userData.obj=obj; grp.add(mb);
}
function buildBomb(n){
  const g=new THREE.Group();
  const s=new THREE.Mesh(bombGeo,bombMat); s.userData.obj=n; g.add(s);
  const [px,py]=cellPos(n.x,n.y); g.userData.obj=n; g.position.set(px,py,(n.beat-cur)*ZPB); return g;
}
function wallDims(w0){
  const hh=Math.max(1,Math.min(w0.h,3-w0.y));
  const cx=(1.5-(w0.x+(w0.w-1)/2))*LANE+NOTE_DX;   // レーン軸反転＋ノーツ帯のXオフセット
  const cy=BASE_Y+w0.y*LAYER+(hh-1)*LAYER/2;
  return {hh,cx,cy,len:Math.max(0.12,w0.dur*ZPB)};
}
function buildWall(w0){
  const g=new THREE.Group();
  const {hh,cx,cy,len}=wallDims(w0);
  const geo=new THREE.BoxGeometry(w0.w*LANE-0.04,hh*LAYER-0.04,len);  // 縁は固定幅（端がサイズで動かないように）
  const m=new THREE.Mesh(geo,wallMat);
  m.position.set(cx,cy,len/2); m.userData.obj=w0; m.userData.ownGeo=true; g.add(m);
  const eg=new THREE.EdgesGeometry(geo);
  const e=new THREE.LineSegments(eg,wallEdgeMat);
  e.position.copy(m.position); e.userData.obj=w0; e.userData.ownGeo=true; g.add(e);
  g.userData.obj=w0; g.position.set(0,0,(w0.beat-cur)*ZPB); return g;
}
function buildArc(a){
  const g=new THREE.Group();
  const [hx,hy]=cellPos(a.x,a.y), [tx,ty]=cellPos(a.tx,a.ty);
  const zt=(a.tb-a.b)*ZPB;
  const hv=DIRV[a.d]||[0,0], tv=DIRV[a.tc]||[0,0];
  const p0=new THREE.Vector3(hx,hy,0);
  const p1=new THREE.Vector3(hx-hv[0]*0.55*(a.mu??1),hy+hv[1]*0.55*(a.mu??1),zt*0.25);
  const p3=new THREE.Vector3(tx,ty,zt);
  const p2=new THREE.Vector3(tx+tv[0]*0.55*(a.tmu??1),ty-tv[1]*0.55*(a.tmu??1),zt*0.75);
  const curve=new THREE.CubicBezierCurve3(p0,p1,p2,p3);
  const tube=new THREE.Mesh(new THREE.TubeGeometry(curve,24,0.045,6,false),arcMats[a.c===0?0:1]);
  tube.userData.obj=a; tube.userData.ownGeo=true; g.add(tube);
  g.userData.obj=a; g.position.set(0,0,(a.b-cur)*ZPB); return g;
}
// アーク全体のAABB（buildArcと同じベジェをサンプル。選択ボックス/ギズモ用＝ヘルバ様指定「選択枠はアーク全体」）
function arcBounds(a){
  const [hx,hy]=cellPos(a.x,a.y), [tx,ty]=cellPos(a.tx,a.ty);
  const zt=(a.tb-a.b)*ZPB;
  const hv=DIRV[a.d]||[0,0], tv=DIRV[a.tc]||[0,0];
  const p0=new THREE.Vector3(hx,hy,0);
  const p1=new THREE.Vector3(hx-hv[0]*0.55*(a.mu??1),hy+hv[1]*0.55*(a.mu??1),zt*0.25);
  const p3=new THREE.Vector3(tx,ty,zt);
  const p2=new THREE.Vector3(tx+tv[0]*0.55*(a.tmu??1),ty-tv[1]*0.55*(a.tmu??1),zt*0.75);
  const curve=new THREE.CubicBezierCurve3(p0,p1,p2,p3);
  const mn=new THREE.Vector3(1e9,1e9,1e9), mx=new THREE.Vector3(-1e9,-1e9,-1e9);
  for(let i=0;i<=16;i++){ const pt=curve.getPoint(i/16); mn.min(pt); mx.max(pt); }
  const pad=0.12; mn.subScalar(pad); mx.addScalar(pad);
  return { mn, mx, cx:(mn.x+mx.x)/2, cy:(mn.y+mx.y)/2, cz:(mn.z+mx.z)/2,
           sx:Math.max(0.12,mx.x-mn.x), sy:Math.max(0.12,mx.y-mn.y), sz:Math.max(0.12,mx.z-mn.z) };
}
// 幽霊ノーツ制度は廃止（ヘルバ様指示）: チェーン頭/尾に対応する隠しノーツは作らない・探さない。
// 旧データ/実機.datの「チェーンと重なる頭/尾ノーツ」は読み込み境界で absorbChainCompanionNotes が吸収変換する。
function absorbChainCompanionNotes(notesArr, chainsArr){
  if(!chainsArr||!chainsArr.length||!notesArr||!notesArr.length) return 0;
  const isCompanion=n=>n.kind!=='bomb'&&chainsArr.some(ch=>
    (Math.abs((ch.b||0)-n.beat)<1e-4&&ch.x===n.x&&ch.y===n.y&&ch.c===n.c)||
    (Math.abs((ch.tb||0)-n.beat)<1e-4&&ch.tx===n.x&&ch.ty===n.y&&ch.c===n.c));
  let removed=0;
  for(let i=notesArr.length-1;i>=0;i--){ if(isCompanion(notesArr[i])){ notesArr.splice(i,1); removed++; } }
  return removed;
}
// チェーン全体のAABB（頭〜尾リンク・拍方向Zは圧縮しないローカル座標）
function chainBounds(ch){
  const [hx,hy]=cellPos(ch.x,ch.y), [tx,ty]=cellPos(ch.tx,ch.ty);
  const zt=(ch.tb-ch.b)*ZPB;
  const { links }=chainLinkLayout(ch, hx, hy, tx, ty, zt, {...chainCurveGlobal, dirXSign:-1});
  const zR=Math.max(0.05,0.46*NOTE_THIN*0.5);
  const headRx=CHAIN_HEAD_SIZE.w/2, headRy=CHAIN_HEAD_SIZE.h/2;
  const tailR=Math.max(CHAIN_LINK_SIZE.w,CHAIN_LINK_SIZE.h)/2;
  let mn=new THREE.Vector3(hx-headRx,hy+CHAIN_HEAD_LIFT-headRy,-zR), mx=new THREE.Vector3(hx+headRx,hy+CHAIN_HEAD_LIFT+headRy,zR);
  for(const lk of links){
    const lz=lk.lz??zt*lk.t;
    const lr=Math.max(CHAIN_LINK_SIZE.w,CHAIN_LINK_SIZE.h)/2;
    mn.min(new THREE.Vector3(lk.lx-lr,lk.ly-lr,lz-zR));
    mx.max(new THREE.Vector3(lk.lx+lr,lk.ly+lr,lz+zR));
  }
  mn.min(new THREE.Vector3(tx-tailR,ty-tailR,zt-zR));
  mx.max(new THREE.Vector3(tx+tailR,ty+tailR,zt+zR));
  return { mn,mx, cx:(mn.x+mx.x)/2, cy:(mn.y+mx.y)/2, cz:(mn.z+mx.z)/2,
    sx:mx.x-mn.x, sy:mx.y-mn.y, sz:Math.max(mx.z-mn.z,0.12) };
}
// ノーツ面マーク: 0.4 平面 / 0.46 箱幅 ≒ 87%
const NOTE_MARK_RATIO = 0.4 / 0.46;
/** チェーン各パーツのマーク寸法（箱サイズに比例。リンクは実機同様の均一サイズ＝s2縮小は廃止） */
function chainMarkParams(size) {
  const { w, h, d } = size;
  const face = Math.min(w, h) * NOTE_MARK_RATIO;
  return {
    faceScale: face / 0.4,
    markZ: d * 0.5 * 1.02,
    aspect: h / w,
  };
}
// チェーン各パーツの前後マーク（buildNote と同様: box と兄弟・box のみ斜め回転）
function addThinFaceMarks(grp, markMat, arrowDeg, obj, params = {}) {
  const { faceScale = 1, markZ = 0.235, aspect = 1, markY = 0 } = params;
  const m = new THREE.Mesh(markGeo, markMat);
  m.position.set(0, markY, -markZ);
  m.scale.set(faceScale, arrowDeg != null ? faceScale * aspect : faceScale, 1);
  m.userData.obj = obj;
  if (arrowDeg != null) m.rotation.set(0, Math.PI, -THREE.MathUtils.degToRad(arrowDeg));
  else m.rotation.set(0, Math.PI, 0);
  grp.add(m);
  const mb = new THREE.Mesh(markGeo, markMat);
  mb.position.set(0, markY, markZ);
  mb.scale.set(faceScale, arrowDeg != null ? faceScale * aspect : faceScale, 1);
  mb.userData.obj = obj;
  if (arrowDeg != null) mb.rotation.set(0, 0, THREE.MathUtils.degToRad(arrowDeg));
  else mb.rotation.set(0, 0, 0);   // ●背面: buildNote と同じ（Y=π だと面が内側を向き非表示）
  grp.add(mb);
}
// チェーン親=下半分カット。中央▲を箱中心へ（縁寄せ通常矢印は使わない）
/** 向き d → チェーン頭の箱の rotation.z。基準=ヘルバ様の8方向リファレンス図（2026-07-12決定版）:
    箱は向きに完全回転（左右向きは縦長）。平らな切り口が進行方向(リンク側)を向き、面取りは反対側。
    式: DIR_ANGLE[d]+180（全方向共通）。ドット(8)は無回転。
    ※箱のオフセット（切り口=セル中心に置くための持ち上げ）も回転に追従させること（chainHeadBoxOffset）。 */
function chainBoxRotZ(d){
  if(d>=0&&d<=7) return THREE.MathUtils.degToRad((DIR_ANGLE[d]??0)+180);
  return 0;
}
/** 回転φに追従した頭箱の中心オフセット（元は(0,+LIFT)＝切り口がセル中心を通る位置） */
function chainHeadBoxOffset(phi){
  return [-Math.sin(phi)*CHAIN_HEAD_LIFT, Math.cos(phi)*CHAIN_HEAD_LIFT];
}
function addChainHeadVisual(parent, wx, wy, wz, col, d, ch){
  const grp=new THREE.Group();
  grp.position.set(wx,wy,wz);
  grp.scale.z=NOTE_THIN;
  const box=new THREE.Mesh(chainHeadGeo,col);
  const phi=chainBoxRotZ(d);
  const [ox,oy]=chainHeadBoxOffset(phi);
  box.position.set(ox,oy,0);   // 切り口=セル中心（箱は進行方向の後ろ側に座る）
  box.rotation.z=phi;
  box.userData.obj=ch;
  box.userData.partRole='head';
  grp.userData.obj=ch; grp.userData.partRole='head';   // マーク面クリックでも部位が拾えるように
  grp.userData.body=box;   // 通過発光でマテリアルを差し替えるためのボディ参照（ノーツと同じ仕組み）
  grp.add(box);
  attachChainHeadMarks(grp, d, ch);
  parent.add(grp);
  return grp;
}
function buildChain(ch){
  const g=new THREE.Group();
  const [hx,hy]=cellPos(ch.x,ch.y), [tx,ty]=cellPos(ch.tx,ch.ty);
  const zt=(ch.tb-ch.b)*ZPB;
  const col=mat(ch.c);
  const thin=NOTE_THIN;
  const { links }=chainLinkLayout(ch, hx, hy, tx, ty, zt, {...chainCurveGlobal, dirXSign:-1});
  const headGrp=addChainHeadVisual(g, hx, hy, 0, col, ch.d, ch);
  g.userData.body=headGrp.userData.body;   // 通過発光の対象＝頭ボックス（ノーツのjudgment-planeフラッシュと同じ仕組み）
  // リンクの向き=ベジェ接線（実機式）。頭→尾の角度補間・尾の向き上書き(td)は実機非反映のため廃止（ヘルバ様決定 2026-07-12）
  for(let li=0; li<links.length; li++){
    const lk=links[li];
    const isTail=li===links.length-1;
    const lz=lk.lz??zt*lk.t;
    const linkMark=chainMarkParams(CHAIN_LINK_SIZE);
    const linkGrp=new THREE.Group();
    linkGrp.position.set(lk.lx,lk.ly,lz);
    linkGrp.rotation.z=THREE.MathUtils.degToRad(lk.ang);   // 接線角（実機のリンクの向き）
    linkGrp.scale.z=thin;
    const linkBox=new THREE.Mesh(chainLinkGeo,col);
    linkBox.userData.obj=ch;
    linkBox.userData.partRole=isTail?'tail':'link';
    linkGrp.userData.obj=ch; linkGrp.userData.partRole=isTail?'tail':'link';   // ●マーク面クリックでも部位が拾えるように
    linkGrp.add(linkBox);
    addThinFaceMarks(linkGrp, dotMatS, null, ch, linkMark);   // 子ノーツ(テール含む)は回転しても常に●（ヘルバ様指摘）
    g.add(linkGrp);
  }
  { const { pts }=sampleChainCurve(ch, hx, hy, tx, ty, zt, 24, {...chainCurveGlobal, dirXSign:-1});
    const curvePts=pts.map(p=>new THREE.Vector3(p.x,p.y,p.z));
    const cgeom=new THREE.BufferGeometry().setFromPoints(curvePts);
    const cmat=new THREE.LineBasicMaterial({color:ch.c===0?0xff6688:0x55aaff,transparent:true,opacity:0.42});
    const cl=new THREE.Line(cgeom,cmat); cl.userData.ownGeo=true; g.add(cl); }
  g.userData.obj=ch; g.position.set(0,0,(ch.b-cur)*ZPB); return g;
}
function extendClipForChain(ch){
  const sec=clipSectionAt('n',ch._tr,ch.b);
  if(sec) extendClipToFit(sec,ch.b,ch.tb);
}
// ワールドZ→拍。メッシュは毎フレーム viewBeat() 基準で配置されるため、変換も必ず同じアンカーを使う。
// （旧: cur基準。他画面操作後などで vwB(ビュー固定)や補正により viewBeat≠cur になると、ドラッグした瞬間に
//   b/tb が (cur−viewB) ぶん飛んでチェインが崩壊して見えるバグの原因＝ヘルバ様報告）

// ---- チェーン視覚編集（曲線表示 + 尾/頭/向きハンドル + 尾・向きミニギズモ） ----
const chainOverlay=new THREE.Group(); noteRoot.add(chainOverlay); tagHelper(chainOverlay);
let chainHandles=[], chainDrag=null, chainGizmoHandles=[], chainGizmoDrag=null;
const CHAIN_GIZMO_DEFS=[
  {dir:[-1,0,0], axis:'x', sign:1,  color:0xff5566},
  {dir:[1,0,0],  axis:'x', sign:-1, color:0xff5566},
  {dir:[0,1,0],  axis:'y', sign:1,  color:0x55dd66},
  {dir:[0,-1,0], axis:'y', sign:-1, color:0x55dd66},
  {dir:[0,0,1],  axis:'z', sign:1,  color:0x4499ff},
  {dir:[0,0,-1], axis:'z', sign:-1, color:0x4499ff},
];
/** チェーン/アークのミニギズモを箱面に密着させる半サイズ */
function chainHeadGizmoHalf(){
  const {w,h,d}=CHAIN_HEAD_SIZE;
  return { x:w/2, y:h/2, z:d*NOTE_THIN/2 };
}
function chainLinkGizmoHalf(){
  const {w,h,d}=CHAIN_LINK_SIZE;
  return { x:w/2, y:h/2, z:d*NOTE_THIN/2 };
}
function makeChainGizmoArrow(def){
  const grp=new THREE.Group();
  const m=new THREE.MeshBasicMaterial({color:def.color});
  const shaft=new THREE.Mesh(new THREE.CylinderGeometry(0.014,0.014,0.18,8),m);
  shaft.position.y=0.09; grp.add(shaft);
  const cone=new THREE.Mesh(new THREE.ConeGeometry(0.058,0.15,10),m);
  cone.position.y=0.24; grp.add(cone);
  grp.quaternion.setFromUnitVectors(new THREE.Vector3(0,1,0),new THREE.Vector3(...def.dir));
  grp.scale.setScalar(0.6);   // 頭/尾のミニギズモは一回り小さく（ヘルバ様指定）
  grp.userData.chainGizmoArrow=def;
  grp.children.forEach(c=>c.userData.chainGizmoArrow=def);
  tagHelper(grp);
  return grp;
}
// その方向へ1ステップでも動けるか（動けない矢印は出さない＝ヘルバ様指定。def.signはグリッド系の増分）
function chainGizmoUsable(role, ch, def){
  const s=def.sign;
  if(role==='head'){
    if(def.axis==='x'){ const nx=(ch.x||0)+s; return nx>=0&&nx<=3; }
    if(def.axis==='y'){ const ny=(ch.y||0)+s; return ny>=0&&ny<=2; }
    return s>0 || (ch.b||0)-snap>=-1e-6;                   // 拍: 前へは常に可・後ろは拍0まで
  }
  if(role==='tail'){
    if(def.axis==='x'){ const nx=(ch.tx||0)+s; return nx>=0&&nx<=3; }
    if(def.axis==='y'){ const ny=(ch.ty||0)+s; return ny>=0&&ny<=2; }
    return s>0 || (ch.tb||0)-snap>=(ch.b||0)-1e-6;         // 拍: 前へは常に可・後ろは頭と同拍まで
  }
  return true;   // dir等は常に表示
}
function attachChainGizmoAt(pos, role, chain, axes, half){
  const anchor=new THREE.Group();
  anchor.position.copy(pos);
  const off=0.05;
  for(const def of CHAIN_GIZMO_DEFS){
    if(!axes.includes(def.axis)) continue;
    if(!chainGizmoUsable(role,chain,def)) continue;   // 盤端・拍下限で動けない方向の矢印は非表示
    const g=makeChainGizmoArrow(def);
    g.position.set(def.dir[0]*(half.x+off),def.dir[1]*(half.y+off),def.dir[2]*(half.z+off));
    g.userData.chainGizmo={role,chain,arrow:def,center:pos.clone()};
    anchor.add(g); chainGizmoHandles.push(g);
  }
  chainOverlay.add(anchor);
}
function clearChainOverlay(){
  chainOverlay.children.forEach(ch=>{ if(ch.userData.ownGeo) ch.geometry.dispose(); });
  while(chainOverlay.children.length) chainOverlay.remove(chainOverlay.children[0]);
  chainHandles=[]; chainGizmoHandles=[];
}
let _chainOvIdSeq=0, _chainOverlayKey=null;
// 毎フレーム(_tick)から呼ばれるため、選択/チェーン内容/再生ヘッド位置に変化が無ければ
// ジオメトリを丸ごと作り直さない（毎フレーム全破棄・再生成していたのが重さの原因＝ヘルバ様報告のラグ対策）
function updateChainOverlay(){
  const cs=selChains().filter(c=>layerVisible('n',c._tr||0));
  const as=selArcs().filter(a=>layerVisible('n',a._tr||0));   // アークもチェーンと同じオーバーレイ機構に乗せる（ヘルバ様指定「チェインの操作にできるだけ合わせる」）
  const visible=(cs.length||as.length)&&!lightMode&&!box&&!pasteFollow;   // placeMode条件は撤去＝常時武装でオーバーレイが永久に消える問題の解消（選択中のチェーン/アークが有る時だけ出る）
  // キーには実際に描画で使うZ(本体メッシュのgroup.position.z)も含める＝cur以外(viewB/vwB)の変化でも
  // 確実にオーバーレイが追従する（キャッシュ導入で新たな取り残しを作らないため）
  const key=visible?(JSON.stringify(chainCurveGlobal)+'|'+chainSelPart+'|'+cs.map(c=>{
    const id=c._ovid??(c._ovid=++_chainOvIdSeq);
    const mEntry0=meshes.find(m=>m.obj===c);
    const gz0=mEntry0?mEntry0.group.position.z:(c.b-cur)*ZPB;
    return id+':'+gz0.toFixed(4)+':'+[c.b,c.x,c.y,c.d,c.tb,c.tx,c.ty,c.sc,c.s,JSON.stringify(c.raw||null)].join(',');
  }).join(';')+'|'+as.map(a=>{
    const id=a._ovid??(a._ovid=++_chainOvIdSeq);
    const mEntry0=meshes.find(m=>m.obj===a);
    const gz0=mEntry0?mEntry0.group.position.z:(a.b-cur)*ZPB;
    return id+':'+gz0.toFixed(4)+':'+[a.b,a.x,a.y,a.d,a.tb,a.tx,a.ty,a.tc,a.mu,a.tmu,a.m].join(',');
  }).join(';')):'';
  if(key===_chainOverlayKey) return;
  _chainOverlayKey=key;
  clearChainOverlay();
  if(!visible) return;
  const showGizmo=cs.length===1&&chainSelPart==='child';   // ミニギズモは子ノーツ選択時のみ（頭選択=全体移動ギズモだけ＝ヘルバ様指定）
  for(const ch of cs){
    // 本体メッシュは viewB 基準(m.group.position.z)で毎フレーム位置決めされる（updateGizmoと同じ方式）。
    // ここを独自に (ch.b-cur)*ZPB で再計算すると、ビュー固定(vwB)中や再生中のレイテンシ補正でcur≠viewBとなり、
    // 選択枠/矢印/曲線オーバーレイだけ本体からズレる（他画面へ切替→戻ってチェーンに触ると崩れて見えるバグの原因）
    const mEntry=meshes.find(m=>m.obj===ch);
    const gz=mEntry?mEntry.group.position.z:(ch.b-cur)*ZPB;
    const [hx,hy]=cellPos(ch.x,ch.y), [tx,ty]=cellPos(ch.tx,ch.ty);
    const zt=(ch.tb-ch.b)*ZPB;
    const col=ch.c===0?0xff6688:0x55aaff;
    const { pts,midx,midy }=sampleChainCurve(ch, hx, hy, tx, ty, zt, 36, {...chainCurveGlobal, dirXSign:-1});
    const vecs=pts.map(p=>new THREE.Vector3(p.x,p.y,gz+p.z));
    const hg=new THREE.BufferGeometry().setFromPoints(vecs);
    const hl=new THREE.Line(hg,new THREE.LineBasicMaterial({color:col,transparent:true,opacity:0.95}));
    hl.userData.ownGeo=true; chainOverlay.add(hl);
    { const armMat=new THREE.LineBasicMaterial({color:0x7dffc8,transparent:true,opacity:0.45});
      for(const seg of [[hx,hy,gz,midx,midy,gz],[midx,midy,gz,tx,ty,gz+zt]]){
        const ag=new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(seg[0],seg[1],seg[2]),new THREE.Vector3(seg[3],seg[4],seg[5])]);
        const al=new THREE.Line(ag,armMat); al.userData.ownGeo=true; chainOverlay.add(al); }
    }
    // 向き(dir)の黄色球ハンドルは廃止＝回転はAlt+ホイールで行う（ヘルバ様指定・ドラッグ用ハンドルは不要）
    const headPos=new THREE.Vector3(hx,hy+CHAIN_HEAD_LIFT,gz);
    const tailPos=new THREE.Vector3(tx,ty,gz+zt);
    const headHalf=chainHeadGizmoHalf();
    const tailHalf=chainLinkGizmoHalf();
    if(showGizmo){
      attachChainGizmoAt(headPos,'head',ch,['x','y','z'],headHalf);
      attachChainGizmoAt(tailPos,'tail',ch,['x','y','z'],tailHalf);
    }
  }
  const showArcGizmo=as.length===1;   // アークは頭/尾どちらも常にミニギズモ表示（チェーンの「子」相当・部位選択の概念は無い）
  for(const a of as){
    const mEntry=meshes.find(m=>m.obj===a);
    const gz=mEntry?mEntry.group.position.z:(a.b-cur)*ZPB;
    const [hx,hy]=cellPos(a.x,a.y), [tx,ty]=cellPos(a.tx,a.ty);
    const zt=(a.tb-a.b)*ZPB;
    const headPos=new THREE.Vector3(hx,hy,gz);
    const tailPos=new THREE.Vector3(tx,ty,gz+zt);
    const ptHalf={x:0.16,y:0.16,z:0.16};   // アーク端点は箱を持たないため固定の小半径
    if(showArcGizmo){
      attachChainGizmoAt(headPos,'head',a,['x','y','z'],ptHalf);
      attachChainGizmoAt(tailPos,'tail',a,['x','y','z'],ptHalf);
    }
  }
}
function pickChainGizmo(e){
  if(!chainGizmoHandles.length) return null;
  setPtr(e);
  const hit=raycaster.intersectObjects(chainGizmoHandles,true)[0];
  if(!hit) return null;
  let o=hit.object;
  while(o&&!o.userData.chainGizmo) o=o.parent;
  return o?o.userData.chainGizmo:null;
}
function pickChainHandle(e){
  if(!chainHandles.length) return null;
  setPtr(e);
  const hit=raycaster.intersectObjects(chainHandles,false)[0];
  return hit?hit.object.userData.chainHandle:null;
}
function startChainGizmoDrag(cg){
  snapshot();
  const ch=cg.chain, d=cg.arrow;
  const ld=new THREE.Vector3(...d.dir);
  const center=cg.center.clone();
  const t0=axisParam(center,ld);
  if(cg.role==='tail'){
    chainGizmoDrag={role:'tail',chain:ch,d,ld,t0,center,orig:{tx:ch.tx,ty:ch.ty,tb:ch.tb}};
  } else if(cg.role==='head'){
    chainGizmoDrag={role:'head',chain:ch,d,ld,t0,center,orig:{b:ch.b,x:ch.x,y:ch.y,tb:ch.tb}};
  } else {
    const [hx,hy]=cellPos(ch.x,ch.y);
    chainGizmoDrag={role:'dir',chain:ch,d,ld,t0,center,orig:{d:ch.d,hx,hy,hxH:center.x,hyH:center.y}};
  }
}
function applyChainGizmoDrag(){
  if(!chainGizmoDrag) return;
  const {role,chain:ch,d,ld,t0,center,orig}=chainGizmoDrag;
  const t=axisParam(center,ld);
  const unit=d.axis==='x'?LANE:d.axis==='y'?LAYER:snap*ZPB;
  const steps=Math.round((t-t0)/unit);
  if(steps===0){
    if(role==='tail'){ ch.tx=orig.tx; ch.ty=orig.ty; ch.tb=orig.tb; }
    else if(role==='head'){ ch.b=orig.b; ch.x=orig.x; ch.y=orig.y; ch.tb=orig.tb; }
    else { ch.d=orig.d; }
    refreshMesh(ch); updateChainOverlay(); return;
  }
  if(role==='tail'){
    let tx=orig.tx, ty=orig.ty, tb=orig.tb;
    if(d.axis==='x') tx=Math.max(0,Math.min(3,orig.tx+steps*d.sign));
    else if(d.axis==='y') ty=Math.max(0,Math.min(2,orig.ty+steps*d.sign));
    else tb=Math.max(ch.b,orig.tb+steps*d.sign*snap);   // 下限=頭と同拍（縦積み形へ戻せる。旧: b+snap強制で戻れなかった＝ヘルバ様報告）
    ch.tx=tx; ch.ty=ty; ch.tb=tb;
    stat(tf('msg.chainTail','尾: 列{tx} 段{ty} 拍{tb}',{tx,ty,tb:tb.toFixed(2)}));
  } else if(role==='head'){
    let b=orig.b, x=orig.x, y=orig.y, tb=orig.tb;
    if(d.axis==='x') x=Math.max(0,Math.min(3,orig.x+steps*d.sign));
    else if(d.axis==='y') y=Math.max(0,Math.min(2,orig.y+steps*d.sign));
    else b=Math.max(0,orig.b+steps*d.sign*snap);
    ch.b=b; ch.x=x; ch.y=y;
    if(ch.tb<ch.b) ch.tb=ch.b;   // 尾は頭より過去に置けない（同拍=縦積みはOK）
    stat(tf('msg.chainHead','頭: 列{x} 段{y} 拍{b}',{x,y,b:b.toFixed(2)}));
  } else {
    const hxH=orig.hxH+(d.axis==='x'?steps*d.sign*LANE:0);
    const hyH=orig.hyH+(d.axis==='y'?steps*d.sign*LAYER:0);
    ch.d=nearestCutDirection(angleFromWorldDelta(hxH-orig.hx,hyH-orig.hy));
    stat(tf('msg.chainDir','向き: {dir}',{dir:DIRICON[ch.d]}));
  }
  _flatDirty=true;
  (ch.kind==='arc'?extendClipForArc:extendClipForChain)(ch);
  refreshMesh(ch);
  updateChainOverlay();
  refreshChainPanel();
  refreshArcPanel();
}
function endChainGizmoDrag(){
  if(!chainGizmoDrag) return;
  flushFlatEdits();
  chainGizmoDrag=null;
  metaDirty=true;
}
function startChainDrag(h,e){
  // 掴んだ時点では何も変更しない（選択クリックで位置が飛ぶバグの修正＝ヘルバ様報告）。
  // 4px以上動いたら初めてドラッグ扱い。適用は「掴んだ床点からの相対移動量」方式＝
  // レイがノーツを突き抜けて奥の床に当たる絶対投影のワープを原理的に排除。
  const ch=h.chain;
  setPtr(e);
  const f0=new THREE.Vector3();
  if(!raycaster.ray.intersectPlane(floorPlane,f0)) f0.set(0,0,0);
  chainDrag={...h, sx:e.clientX, sy:e.clientY, f0:{x:f0.x,y:f0.y,z:f0.z},
    orig:{b:ch.b,x:ch.x,y:ch.y,tb:ch.tb,tx:ch.tx,ty:ch.ty,d:ch.d}, moved:false};
}
function applyChainDrag(e){
  if(!chainDrag) return;
  if(!chainDrag.moved){
    if(Math.hypot(e.clientX-chainDrag.sx, e.clientY-chainDrag.sy)<4) return;   // クリック（選択）では動かさない
    chainDrag.moved=true; snapshot();   // 実際に動かし始めた時だけ履歴
  }
  setPtr(e);
  if(!raycaster.ray.intersectPlane(floorPlane,_fv)) return;
  const ch=chainDrag.chain, o=chainDrag.orig, f0=chainDrag.f0;
  const dgx=Math.round(-(_fv.x-f0.x)/LANE), dgy=Math.round((_fv.y-f0.y)/LAYER), dbz=(_fv.z-f0.z)/ZPB;   // 相対移動量（レーン軸はワールド反転）
  if(chainDrag.role==='tail'){
    ch.tx=Math.max(0,Math.min(3,o.tx+dgx)); ch.ty=Math.max(0,Math.min(2,o.ty+dgy));
    ch.tb=Math.max(ch.b,snapV(o.tb+dbz));   // 下限=頭と同拍（縦積み形へ戻せる）
  } else if(chainDrag.role==='head'){
    ch.x=Math.max(0,Math.min(3,o.x+dgx)); ch.y=Math.max(0,Math.min(2,o.y+dgy));
    ch.b=Math.max(0,snapV(o.b+dbz));
    if(ch.tb<ch.b) ch.tb=ch.b;   // 尾は頭より過去に置けない（同拍=縦積みはOK）
  } else if(chainDrag.role==='dir'){
    const [hx,hy]=cellPos(ch.x,ch.y);
    ch.d=nearestCutDirection(angleFromWorldDelta(_fv.x-hx,_fv.y-hy));
  }
  _flatDirty=true;
  (ch.kind==='arc'?extendClipForArc:extendClipForChain)(ch);
  refreshMesh(ch);
  updateChainOverlay();
  refreshChainPanel();
  refreshArcPanel();
}
function endChainDrag(){
  if(!chainDrag) return;
  if(chainDrag.moved){ flushFlatEdits(); metaDirty=true; }
  chainDrag=null;
}

// チェーンの頭・尾・子リンクをレイキャスト（ホイール操作・ドラッグの当たり判定）
function pickChainPart(e){
  if(lightMode) return null;
  // ノーツとライトはワールド座標上で重なっているため、モードで拾う対象を必ず分ける（2026-07-18の表示改修）。
  setPtr(e);
  const groups=meshes.filter(m=>{
    const o=m.obj;
    return o.kind==='chain'&&layerVisible('n',o._tr||0)&&!objLockedN(o)&&m.group.visible;   // ロック中レーンのチェーンは触れない（ヘルバ様指摘）
  }).map(m=>m.group);
  const hits=raycaster.intersectObjects(groups,true);
  for(const h of hits){
    let o=h.object;
    while(o){
      const role=o.userData?.partRole;
      if((role==='head'||role==='tail'||role==='link')&&o.userData.obj?.kind==='chain'){
        return {role,obj:o.userData.obj};
      }
      o=o.parent;
    }
  }
  return null;
}
function pickChainArcEndpoint(e){
  const p=pickChainPart(e);
  return p&&(p.role==='head'||p.role==='tail')?p:null;
}
function extendClipForArc(a){
  const sec=clipSectionAt('n',a._tr,a.b);
  if(sec) extendClipToFit(sec,a.b,a.tb);
}
// アークの頭/尾/本体をレイキャスト（チェーンと違いアークは1本のチューブのみ＝実メッシュにpartRoleタグが無いため、
// ヒット点と端点ワールド座標の近接度で判定。ヘルバ様指定「チェインの操作にできるだけ合わせる」の受け皿）
// アーク頭/尾は実ノーツがそのまま残る仕様のため、細いチューブの数学的端点ちょうどを狙うレイは筒の開口部を素通りして外れる
// （TubeGeometryはclosed=falseで両端キャップ無し）。実際にユーザーが自然にクリックする「頭/尾のノーツそのもの」も
// 判定対象に含める＝チェーンの頭/尾箱と同じ感覚でクリックできるようにする。
const ARC_ENDPOINT_NEAR=0.5;
function pickArcPart(e){
  setPtr(e);
  const arcObjs=arcs.filter(o=>layerVisible('n',o._tr||0)&&!objLockedN(o));
  if(!arcObjs.length) return null;
  const targets=[];   // {group, isNote, arc, role}
  for(const m of meshes){
    if(!m.group.visible) continue;
    const o=m.obj;
    if(o.kind==='arc'&&arcObjs.includes(o)){ targets.push({group:m.group, isNote:false, arc:o}); continue; }
    if(o.kind==='note'){
      for(const a of arcObjs){
        if(o.beat===a.b&&o.x===a.x&&o.y===a.y&&o.c===a.c){ targets.push({group:m.group, isNote:true, arc:a, role:'head'}); }
        else if(o.beat===a.tb&&o.x===a.tx&&o.y===a.ty&&o.c===a.c){ targets.push({group:m.group, isNote:true, arc:a, role:'tail'}); }
      }
    }
  }
  const hits=raycaster.intersectObjects(targets.map(t=>t.group),true);
  for(const h of hits){
    let root=h.object; while(root&&!targets.some(t=>t.group===root)) root=root.parent;
    const t=root&&targets.find(x=>x.group===root); if(!t) continue;
    if(t.isNote) return {role:t.role, obj:t.arc};
    const a=t.arc;
    const mEntry=meshes.find(m=>m.obj===a); const gz=mEntry?mEntry.group.position.z:(a.b-cur)*ZPB;
    const [hx,hy]=cellPos(a.x,a.y), [tx,ty]=cellPos(a.tx,a.ty);
    const zt=(a.tb-a.b)*ZPB;
    const hp=new THREE.Vector3(hx,hy,gz), tp=new THREE.Vector3(tx,ty,gz+zt);
    const dh=h.point.distanceTo(hp), dt=h.point.distanceTo(tp);
    if(dh<=ARC_ENDPOINT_NEAR&&dh<=dt) return {role:'head',obj:a};
    if(dt<=ARC_ENDPOINT_NEAR&&dt<dh) return {role:'tail',obj:a};
    return {role:'body',obj:a};
  }
  return null;
}
function pickArcEndpoint(e){
  if(lightMode) return null;   // ノーツとライトはワールド座標上で重なっているため（2026-07-18の表示改修）
  const p=pickArcPart(e);
  return p&&(p.role==='head'||p.role==='tail')?p:null;
}
// チェーン/アーク共通: 頭/尾の掴み判定（掴みドラッグの入口。チェーンは実メッシュタグ・アークは近接判定＝優先度はチェーン→アーク）
function pickCurveEndpoint(e){
  return pickChainArcEndpoint(e)||pickArcEndpoint(e);
}

const BUILDERS={note:buildNote,bomb:buildBomb,wall:buildWall,arc:buildArc,chain:buildChain};
function addObj(o){ const grp=BUILDERS[o.kind](o); grp.traverse(c=>{ c.layers.set(3); c.layers.enable(5); }); noteRoot.add(grp); meshes.push({obj:o,group:grp}); }   // 3=編集ビュー・5=プレビュー（通過で外す）
function removeObjMesh(o){ const i=meshes.findIndex(m=>m.obj===o); if(i>=0){
  meshes[i].group.traverse(ch=>{ if(ch.userData.ownGeo) ch.geometry.dispose(); }); // 固有ジオメトリを破棄（リーク対策）
  noteRoot.remove(meshes[i].group); meshes.splice(i,1); } }
function refreshMesh(o){ removeObjMesh(o); addObj(o); }
// 位置だけ変わった時の軽量更新（ノーツ/ボム用。再構築せずグループを動かす）
// ---- 実機プレビュー ミラープール（ArcViewer移植）: 編集メッシュとは別に、プレビュー専用レイヤー6へ実機挙動で描く ----
function syncPos(o){ const m=meshes.find(m=>m.obj===o); if(!m) return;
  const [px,py]=cellPos(o.x,o.y); m.group.position.x=px; m.group.position.y=py; }
function arrOf(kind){ return kind==='note'?notes:kind==='bomb'?bombs:kind==='wall'?walls:kind==='arc'?arcs:chains; }
// 幽霊ノーツ制度は廃止（ヘルバ様指示）: チェーンは頭/尾の座標を自分で持ち、notes側に隠しノーツを一切残さない。
// 作成時=選択2ノーツを削除して変換、削除時=チェーン本体のみ、書き出し時=頭colorNoteをチェーンから合成。
function removeObj(o){ const a=arrOf(o.kind); const i=a.indexOf(o); if(i>=0)a.splice(i,1); removeObjMesh(o); selection.delete(o); }
function rebuild(){
  meshes.forEach(m=>{ m.group.traverse(ch=>{ if(ch.userData.ownGeo) ch.geometry.dispose(); }); noteRoot.remove(m.group); });
  meshes=[];
  [...notes,...bombs,...walls,...arcs,...chains].filter(o=>layerVisible('n',o._tr||0)).forEach(addObj);   // 幽霊廃止: notesは常に全表示
  refreshChainPanel();
  refreshArcPanel();
}

// state
let BPM=120, songDur=0, cur=0, snap=0.5, brush={c:0,d:1,type:'note'};
// ---- テンポパート（曲中のBPM変更。V3譜面のbpmEventsとして書き出す＝Beat Saber本体でも実際に速度が変わる） ----
// tempoParts: [{beat, bpm}] を必ずbeat昇順で保持。BPM(上の変数)は「拍0〜最初のパートまで」の基準テンポ。
// 拍番号は据え置きで、テンポを変えると後ろの絶対時刻が自動でズレる（bpmEventsそのままの標準挙動）。
let tempoParts=[];
function sortTempoParts(){ tempoParts.sort((a,b)=>a.beat-b.beat); }
function bpmAtBeat(b){ let bpm=BPM; for(const p of tempoParts){ if(p.beat>b+1e-9) break; bpm=p.bpm; } return bpm; }
function beatToTimeTM(b){   // 区分的な拍→秒（曲頭=拍0からの経過秒。offset/leadInは呼び出し側で別途加減する）
  let bb=0, bpm=BPM, tt=0;
  for(const p of tempoParts){ if(p.beat>=b) break; tt+=(p.beat-bb)*60/bpm; bb=p.beat; bpm=p.bpm; }
  return tt+(b-bb)*60/bpm;
}
function timeToBeatTM(tm){   // 区分的な秒→拍（beatToTimeTMの逆関数）
  let bb=0, bpm=BPM, tt=0;
  for(const p of tempoParts){ const segT=(p.beat-bb)*60/bpm; if(tt+segT>tm) break; tt+=segT; bb=p.beat; bpm=p.bpm; }
  return bb+(tm-tt)*bpm/60;
}
// Musicクリップの長さは秒(sg.dur)で保持しているため、拍換算は開始拍(sg.beat)からの区分的な変換が必要
// （テンポパートを跨ぐセグメントで単純な sg.dur*BPM/60 だと長さがズレる）。
function segEndBeat(sg){ return timeToBeatTM(beatToTimeTM(sg.beat)+sg.dur); }
function segBeatsOf(sg){ return segEndBeat(sg)-sg.beat; }
// ジャンプのイージング: 瞬間移動だと視線が追えず「どこへ行ったか分からない」ため、短いスクロールで飛ぶ
let curAnim=null;   // {from,to,start,dur,last} tickが進める。他の操作がcurを触ったら自動中断
// 3Dビューのアンカー拍: 拍番号クリックでビューを固定し、ヘッド（赤ライン）だけが画面内を飛ぶ（NLEと同じ）
let vwB=null;       // null=ヘッド追従（従来どおり世界がスクロール）
let vwPlayD=null;   // 再生中のヘッド画面位置（cur-vwB、再生開始時に確定）。再生中のみビューがヘッドと等速スクロール（±20拍キープ）
// 原則: 停止中にシステムがビュー/カメラを動かすことは絶対にない（動かすのは使用者のみ）。旧・描画窓スライド＋カメラ補償は構造欠陥のため全廃
function viewBeat(){ if(vwB!=null) return vwB;   // レイテンシ補正はミリ秒オーダーの微小量なので、現在地点のBPM(bpmAtBeat)で近似して十分（テンポパートを跨いでも実用上ズレない）
  return playing? cur-(((actx.outputLatency||actx.baseLatency||0)+avOffset/1000)*bpmAtBeat(cur)/60) : cur; }
function seekEase(target,dur){ target=Math.max(0,target); if(playing) pause();
  vwB=null;   // 3Dは世界スクロールでヘッド追従へ
  tlViewB0=null; tlB0=Math.max(0,target-tlSpan*0.5);   // NLE窓を常にヘッド中心へ飛ばす（手動パンも解除＝再生バー/ショートカットで必ず再生ヘッドへ飛ぶ。ヘルバ様指定）
  try{ const dz=0-controls.target.z; camera.position.z+=dz; controls.target.z+=dz; controls.update(); }catch(_){}   // 3Dカメラもヘッド(z=0)へ寄せる（「.」キーと同じ＝3D EDITでも再生ヘッドへ飛ぶ）
  curAnim={from:cur,to:target,start:performance.now(),dur:dur||240,last:cur}; }
// ==== 配置モード / 編集モード（Qで切替・ヘルバ様指定）====
// 'place'=配置: カメラ=定位置ビュー＋タイムライン追従（再生しながらちょっとづつ置く）／ 'edit'=編集: カメラ自由・再生に非追従（カメラと再生は完全独立）
let camMode='edit';
// 2026-07-18: ヘルバ様がスクリーンショットで指定した構図に合わせて再設定（旧 pos:[-5.2,4.4,-5.0] tgt:[0.2,0.3,3.0]）。
// 赤い再生ヘッド枠の四隅の画素位置から逆算したもので、注視点までの距離は旧設定とほぼ同じ（10.4 対 10.3）＝
// 中ドラッグの回転量やホイールのズーム感は従来どおり。
const PLACE_CAM_DEF={pos:[-6.57,3.07,-3.74],tgt:[-0.97,-1.16,4.08]};   // 配置モードの定位置ビュー（3/4アングル・Ctrl+.プリセットとは別枠。localStorageで上書き可）
// v=2 でないプリセットは無視して既定へ落とす。2026-07-18のレイアウト改修でノーツ帯が動いたため、
// 旧レイアウト時代に手で保存された値（注視点が x≒0＝今は何も無い場所）を読むと、起動直後に何も映らない画面になる。
// 書き込み側はUIに無くコンソール専用なので、版を上げても失うものは無い。
function placeCamPreset(){ try{ const j=JSON.parse(localStorage.getItem('bsnm_placecam')); if(j&&j.v===2&&j.pos&&j.tgt) return j; }catch(_){} return PLACE_CAM_DEF; }
function flyPlaceCam(){ vwB=null;   // ヘッド追従へ（ヘッド=z0基準の定位置ビュー）
  const p=placeCamPreset();
  try{ camera.position.set(p.pos[0],p.pos[1],p.pos[2]); controls.target.set(p.tgt[0],p.tgt[1],p.tgt[2]); controls.update(); }catch(_){} }
// 編集モードの俯瞰ビュー（タイムライン横向き・再生ヘッド=左端の定点。zは再生ヘッド相対＝入った時点のヘッド位置に合わせて配置し、以後カメラは追従しない・ヘルバ様指定 2026-07-14）
// pos/tgt の z は「再生ヘッドからの相対Z」（flyEditCamで headZ を加算）
// 2026-07-17: 遠すぎたため注視点からのオフセットを 1/1.77 に縮めて寄せた（旧 pos:[-15,9,8]・ヘルバ様指定）。角度は据え置き＝見え方の向きは変わらない
// 2026-07-18: ノーツとライトを同じ場所へ集約した改修に合わせ、レーン帯を画面いっぱいに収める画角へ変更
// （ヘルバ様がスクリーンショットで指定。旧 pos:[-9.56,5.08,8] tgt:[-2.5,0,8] は帯が左右に分かれていた頃の構図）。
// 注視点をレーン帯の中央へ寄せ、距離を詰めて俯角を約66°に。拍の間隔と10レーンの収まりを実測で合わせてある。
// 2026-09-21: スペクトログラム帯が加わり見る範囲が広がったため、注視点はそのまま距離を2.2倍に引いた（旧 pos:[-6.11,5.89,8]・距離6.45→14.2）。
// 配置モードの定位置ビュー（注視点までの距離≒10.4）より明確に遠くして、切り替えた時に画角の違いが分かるようにしてある。
const EDIT_CAM_DEF={pos:[-9.27,12.96,8],tgt:[-3.48,0,8]};
function editCamPreset(){ try{ const j=JSON.parse(localStorage.getItem('bsnm_editcam')); if(j&&j.v===2&&j.pos&&j.tgt) return j; }catch(_){} return EDIT_CAM_DEF; }   // v=2判定の理由は placeCamPreset を参照
// ノーツとライトは同じ場所に重ねてあるので、編集カメラもモードで分けない＝TABで切り替えても視点は動かない
// （モード別の画角にすると、切り替えのたびにカメラを飛ばすか、片方が変な角度のまま残るかの二択になる）。
function flyEditCam(){ const headZ=(cur-viewBeat())*ZPB;   // 再生ヘッドのワールドZ（この瞬間で固定＝カメラは以後ヘッドに連動しない）
  const p=editCamPreset();
  try{ camera.position.set(p.pos[0],p.pos[1],p.pos[2]+headZ); controls.target.set(p.tgt[0],p.tgt[1],p.tgt[2]+headZ); controls.update(); }catch(_){} }
// ※savePlaceCam(配置モードの定位置ビュー保存)はUIから呼ばれず死んでいたため撤去（監査 2026-07-14。placeCamPreset/EDIT/PLACE_CAM_DEFは生存）
function setCamMode(mode){ if(mode===camMode) return;
  camMode=mode;
  if(mode==='place'){ if(!lightMode) setPlaceMode(true); flyPlaceCam(); stat(tf('msg.camModePlace','配置モード：カメラ追従・再生しながら配置（Qでカメラ固定へ）')); }   // ライト中はノーツ配置(placeMode)を触らない＝ライトはcamModeで赤パネル固定/自由が切替（ヘルバ様指定 2026-07-13）
  else { if(vwB==null) vwB=viewBeat(); flyEditCam(); stat(tf('msg.camModeEdit','カメラ固定モード：再生してもビューは動きません（Qで配置へ）')); }   // 編集モードは俯瞰ビューへ移動（ヘルバ様指定 2026-07-14）。配置ツールは維持＝セレクト廃止に伴い勝手に武装解除しない（配置済みのクリック=選択で両立）
  if(typeof updateModeIndicator==='function') updateModeIndicator(); }
function toggleCamMode(){ setCamMode(camMode==='place'?'edit':'place'); }
function updateModeIndicator(){ const lbl=document.getElementById('camModeLbl'); if(!lbl) return;
  lbl.textContent=camMode==='place'?t('ui.modePlace','配置モード'):t('ui.modeEdit','カメラ固定モード');
  const box=document.getElementById('camModeInd'); if(box) box.classList.toggle('placeon',camMode==='place'); }
let selection=new Set();
const snapV=b=>Math.round(b/snap)*snap;

// ---- undo / redo ----
const HIST_MAX=512;                                         // 統一履歴の深さ（ヘルバ様指定）
// 一本化: {d:対象ドメイン, s:差し戻しダンプ, diff:その編集をした難易度} を発生順に積む（NLE/NOTES/LIGHT混在）。
// diff を持たせることで難易度をまたいでも1本の履歴で辿れる＝切替そのものは履歴に積まない（空振りのUndoを作らないため・ヘルバ様指定 2026-07-17）
const undoStack=[], redoStack=[];
function pushHist(d,s2){ if(d==='note'||d==='light') _flatDirty=true;   // 3D編集(note/light)=フラットが変わった→contentへ要反映
  undoStack.push({d,s:s2,diff:currentDiffName}); if(undoStack.length>HIST_MAX) undoStack.shift(); redoStack.length=0; }
function dumpDomain(d){
  if(d==='node') return JSON.stringify({sections,graphIO,edges:graphEdges,extra:extraNodes.map(({handle,...r})=>r),
    cuts:[...cutSet],altIns,altOuts,altSongs:altSongs.map(({handle,...r})=>r),activeUids,
    song:songNode?(({handle,...r})=>r)(songNode):null,songDeleted,musicBeat,musicSegs,markers,tempoParts,noteRed:RED,noteBlue:BLUE,laserRed:LRED,laserBlue:LBLUE,
    laySel:[...layerSel],musSel:[...musicSelSet],lanesN:notesLanes,lanesL:lightLanes});   // 選択・マーカーも履歴の一部（マーカー作成/削除もUndo可）
  if(d==='info') return JSON.stringify({g:{...infoGraph,cam:undefined},sel:[..._inSel]});   // ビュー(cam)は履歴対象外
  if(d==='light') return JSON.stringify({lightEvents,sel:[...lightSelection].map(ev=>lightEvents.indexOf(ev)).filter(i2=>i2>=0)});
  return JSON.stringify({notes,bombs,walls,arcs,chains,
    sel:[...selection].map(o=>[o.kind,arrOf(o.kind).indexOf(o)]).filter(p=>p[1]>=0)});
}
function restoreDomain(d,s2){
  const v=JSON.parse(s2);
  if(d==='node'){
    // handleはJSON不可なので現物から引き継ぐ
    const covH=new Map(extraNodes.filter(x=>x.handle).map(x=>[x.id,x.handle]));
    const sgH=new Map(altSongs.filter(x=>x.handle).map(x=>[x.uid,x.handle]));
    const kh=songNode&&songNode.handle;
    sections=v.sections; graphIO=v.graphIO; graphEdges=v.edges;
    extraNodes=v.extra||[]; extraNodes.forEach(x=>{ if(covH.has(x.id)) x.handle=covH.get(x.id); });
    cutSet=new Set(v.cuts||[]);
    altIns=v.altIns||[]; altOuts=v.altOuts||[];
    altSongs=v.altSongs||[]; altSongs.forEach(x=>{ if(sgH.has(x.uid)) x.handle=sgH.get(x.uid); });
    activeUids=v.activeUids||{in:null,out:null,song:null};
    songNode=v.song||null; if(songNode&&kh) songNode.handle=kh;
    songDeleted=!!v.songDeleted; musicBeat=+v.musicBeat||0;
    musicSegs=v.musicSegs||null;
    if(Array.isArray(v.markers)){ markers=v.markers; _mkSeq=Math.max(_mkSeq,markers.length); }   // マーカーもUndo/Redoで往復
    if(Array.isArray(v.tempoParts)) tempoParts=v.tempoParts;   // テンポパートもUndo/Redoで往復
    metaDirty=true;
    layerSel=new Set(v.laySel||[]); musicSelSet=new Set(v.musSel||[]);   // 選択も復元
    if(v.lanesN) notesLanes=v.lanesN; if(v.lanesL) lightLanes=v.lanesL;
    if(v.noteRed!=null){ RED=v.noteRed>>>0; BLUE=v.noteBlue>>>0; setNoteColStr(); refreshInfoCards(); applyModeDim(); }
    if(v.laserRed!=null){ LRED=v.laserRed>>>0; LBLUE=v.laserBlue>>>0; laserBoostCols(); refreshInfoCards(); }
    ndSel=null;
    relinkDiffEdges();
    compileLayersToFlat();                                  // フラットへ再展開（位置=真実。旧compileGraphToFlatはチェーン順でbeatを上書きしUndo/Redoを破壊していた）
  } else if(d==='info'){
    const cam=infoGraph.cam;                       // 現在のビューは維持
    infoGraph=v.g; infoGraph.cam=cam;
    _inSel=new Set(v.sel||[]);
    sanitizeInfoGraph();
    { const ao=infoGraph.activeOut, o=infoGraph.outs[ao];   // 書き出し先ミラーを復元後の姿へ再同期（表示と実書き出し先の乖離防止）
      outDirHandle=(o&&_outHandles[ao]&&_outHandles[ao].name===o.outDirName)?_outHandles[ao]:null;   // handleは名前が一致する時だけ引き継ぐ
      if(o&&graphIO&&graphIO.out){ graphIO.out.folderName=o.folderName||''; graphIO.out.outDirName=o.outDirName||''; graphIO.out.outDirPath=o.outDirPath||''; } }
    _infoSnapT=0;   // Undo直後の再入力が600ms窓に飲まれて履歴が取れなくなるのを防ぐ
    layoutInfoNodes(); applyInfoGraph(); infoSelApply();
  } else if(d==='light'){
    lightEvents=v.lightEvents;
    lightSelection=new Set((v.sel||[]).map(i2=>lightEvents[i2]).filter(Boolean));   // 選択も復元
  } else {
    notes=v.notes; bombs=v.bombs; walls=v.walls; arcs=v.arcs; chains=v.chains;
    rebuild();
    selection=new Set((v.sel||[]).map(([k2,i2])=>arrOf(k2)[i2]).filter(Boolean));   // 選択も復元（rebuild後に張り直し）
  }
  metaDirty=true;
}
const DOM_LABEL={note:'NOTES',light:'LIGHT',node:'NODE',info:'INFO'};
function snapshot(dom){
  const d=dom||(lightMode?'light':'note');
  pushHist(d,dumpDomain(d));
}
// 履歴の項目が別の難易度のものなら、そこへ戻してから差し戻す。
// projDiffs に居る＝loadDiffの同期パス（awaitを通らない）なので、その場で切替が完了する。
// 履歴がある＝必ず訪問済み＝projDiffsに居る、ので.dat再パースの非同期パスには入らない。
function gotoHistDiff(e){
  if(!e.diff||e.diff===currentDiffName) return '';
  if(!projDiffs[e.diff.toLowerCase()]) return '';   // 未訪問（通常あり得ない）＝切替えずその場で差し戻す
  loadDiff(e.diff);                                  // 入口で stashCurrentDiff() が走る＝今の難易度の編集内容は保たれる
  const sel=document.getElementById('diff'); if(sel) sel.value=e.diff;   // プルダウンの表示も追従
  return e.diff.replace(/Standard\.dat$/i,'');
}
// ライト/ノーツの差し戻しは、何が戻ったか見えるように表示モードも寄せる（履歴には積まない＝表示だけ）
function syncHistView(d){
  if(d==='light'&&!lightMode) setLightMode(true);
  else if(d==='note'&&lightMode) setLightMode(false);
}
function undo(){ const e=undoStack.pop();
  if(!e){ stat('取り消す操作がありません'); return; }
  const moved=gotoHistDiff(e); syncHistView(e.d);
  redoStack.push({d:e.d,s:dumpDomain(e.d),diff:currentDiffName}); restoreDomain(e.d,e.s);
  if(e.d==='note'||e.d==='light') _flatDirty=true;   // フラット復元→contentへ再同期（NLEミニロールと整合）
  stat(tf('msg.undo','取り消し {dom}（残り{n}）',{dom:DOM_LABEL[e.d]+(moved?' @'+moved:''),n:undoStack.length})); }
function redo(){ const e=redoStack.pop();
  if(!e){ stat('やり直す操作がありません'); return; }
  const moved=gotoHistDiff(e); syncHistView(e.d);
  undoStack.push({d:e.d,s:dumpDomain(e.d),diff:currentDiffName}); restoreDomain(e.d,e.s);
  if(e.d==='note'||e.d==='light') _flatDirty=true;   // フラット復元→contentへ再同期
  stat(tf('msg.redo','やり直し {dom}（残り{n}）',{dom:DOM_LABEL[e.d]+(moved?' @'+moved:''),n:redoStack.length})); }
function resetHistory(){ undoStack.length=0; redoStack.length=0; }
// 選択も1動作として履歴に積む: ハンドラ冒頭でselWatch→処理後（マイクロタスク）に選択が実際に変わっていた時だけpush
function selKey(d){ if(d==='node') return [...layerSel].sort().join()+'|'+[...musicSelSet].sort().join();
  if(d==='light') return [...lightSelection].map(ev=>lightEvents.indexOf(ev)).sort((a,b)=>a-b).join();
  return [...selection].map(o=>o.kind+arrOf(o.kind).indexOf(o)).sort().join(); }
function selWatch(d){ const pre=dumpDomain(d), k=selKey(d);
  queueMicrotask(()=>{ if(selKey(d)!==k) pushHist(d,pre); }); }

// ---- sidebar ----
const pal=document.getElementById('pal');
[4,0,5,2,8,3,6,1,7].forEach(d=>{ const el=document.createElement('div'); el.textContent=DIRICON[d]; el.dataset.d=d;
  if(d===brush.d)el.classList.add('on');
  el.onclick=()=>{ brush.d=d; refreshPal();
    if(placeMode) refreshGhost();
    const sel=[...selection].filter(o=>o.kind==='note');
    if(sel.length){ snapshot(); sel.forEach(n=>{n.d=d; refreshMesh(n);}); } }; pal.appendChild(el); });
function refreshPal(){ [...pal.children].forEach(c=>c.classList.toggle('on',+c.dataset.d===brush.d));
  updateDirBtn(); updateColorBtn(); }
const cRed=document.getElementById('cRed'),cBlue=document.getElementById('cBlue');
function recolorLinkedSliders(n){   // ノーツの色変更を、端点(頭/尾)が一致するアークへ連動させる
  if(!n||n.kind!=='note') return;
  for(const a of arcs){
    if((Math.abs((a.b||0)-n.beat)<1e-4&&a.x===n.x&&a.y===n.y)||(Math.abs((a.tb||0)-n.beat)<1e-4&&a.tx===n.x&&a.ty===n.y)){
      if(a.c!==n.c){ a.c=n.c; refreshMesh(a); } } }
}
function setColor(c,applySel=true){ brush.c=c; cRed.classList.toggle('on',c===0); cBlue.classList.toggle('on',c===1);
  updateColorBtn();
  if(placeMode) refreshGhost();                       // 編集モード中はゴーストを即更新
  if(applySel){ const sel=[...selection].filter(o=>o.kind==='note'||o.kind==='arc'||o.kind==='chain');
    if(sel.length){ snapshot(); sel.forEach(n=>{n.c=c; refreshMesh(n); if(n.kind==='note') recolorLinkedSliders(n);}); } } }
cRed.onclick=()=>setColor(0); cBlue.onclick=()=>setColor(1);
const typeBtns={note:document.getElementById('tNote'),bomb:document.getElementById('tBomb'),wall:document.getElementById('tWall')};
// ---- ライトブラシUI ----
const lbBehavEl=document.getElementById('lbBehav');
// ※ON/OFFのプルダウン（lbOnOffBtn/lbOnOffPanel・updateOnOffBtn/toggleOnOffPanel/_lastOnOff）は撤去（2026-07-18）。
//   オフ/ライトを独立ボタンに分割したため不要（ヘルバ様指定）
function setLightBehav(b){ lightBrush.behav=b;
  document.querySelectorAll('.lbBehavItem').forEach(x=>x.classList.toggle('modeon',+x.dataset.b===b)); }
document.querySelectorAll('.lbBehavItem').forEach(btn=>btn.onclick=()=>setLightBehav(+btn.dataset.b));
function setLightColor(base){ lightBrush.base=base;
  [0,4,8].forEach(v=>{ const b=document.getElementById('lc'+v); if(b) b.classList.toggle('on',v===base); });
  try{ updateLightColorTB(); }catch(_){} }   // バニラ配置色の選択をツールバーへ反映
[0,4,8].forEach(v=>{ const b=document.getElementById('lc'+v); if(b) b.onclick=()=>setLightColor(v); });
// ---- クロマ色（カスタムRGB）UI ----
{ const tgl=document.getElementById('lcChroma'), sw=document.getElementById('lcChromaSw');
  if(tgl){ tgl.onclick=()=>{
    const sel=[...lightSelection].filter(ev=>laneKind(ev.et)==='color');
    if(sel.length){ applyLightChroma(null); return; }   // 選択中はクロマ解除（色を選び直す時はスウォッチをクリック）
    lightBrush.chroma=lightBrush.chroma?null:brushChromaHex();
    updateChromaUI();
    stat(lightBrush.chroma?tf('msg.chromaOn','ブラシ: クロマ色 ON（スウォッチで色選択）'):tf('msg.chromaOff','ブラシ: クロマ色 OFF'));
  }; }
  if(sw){ sw.addEventListener('click',e=>{
    if(chromaMode) pickHexAt(e.currentTarget,brushChromaHex(),hex=>{ lightBrush._lastChromaHex=hex; applyLightChroma(hex); });
    else pickHexAt(e.currentTarget,lightBaseHex(),()=>{}); }); }   // バニラは配置色の選択/色編集をパレット内で（起点は素の①②白＝ブースト非適用）
  updateChromaUI();
}
function updateLightUI(){ const el=document.getElementById('lsVal'); if(el) el.textContent=lightBrush.speed; }   // 明るさ/速度スライダーは撤去（Alt+ホイールで調整＝ヘルバ様指定）＝要素が無くても安全
{ const rg=document.getElementById('lfRange'); if(rg) rg.addEventListener('input',e=>{
  lightBrush.f=e.target.value/100; const lv=document.getElementById('lfVal'); if(lv) lv.textContent=lightBrush.f.toFixed(2); }); }

function setBrushType(t){ brush.type=t; for(const k in typeBtns) typeBtns[k].classList.toggle('on',k===t);
  ghostKey=''; refreshHoverVisuals(); if(typeof updateModeButtons==='function') updateModeButtons();
  stat(tf('msg.brush','ブラシ: {kind}',{kind:t==='note'?tf('word.note','ノーツ'):t==='bomb'?tf('word.bomb','ボム'):tf('word.wall','壁')})); }
typeBtns.note.onclick=()=>setBrushType('note'); typeBtns.bomb.onclick=()=>setBrushType('bomb'); typeBtns.wall.onclick=()=>setBrushType('wall');
const snapVals=[[1,'1/1'],[0.5,'1/2'],[0.25,'1/4'],[0.125,'1/8'],[1/16,'1/16']];
const snapsEl=document.getElementById('snaps');
snapVals.forEach(([v,l])=>{ const b=document.createElement('div'); b.className='dirRow';
  b.innerHTML=`<span style="min-width:34px;text-align:center">${l}</span>`; b.dataset.v=v;
  if(v===snap)b.classList.add('on');
  b.onclick=()=>{ setSnap(v); document.querySelectorAll('.tbpanel').forEach(x=>x.style.display='none');
    document.querySelectorAll('#maintb .tbi.on').forEach(x=>x.classList.remove('on')); };
  snapsEl.appendChild(b); });
function setSnap(v){ snap=v; [...snapsEl.children].forEach(c=>c.classList.toggle('on',+c.dataset.v===v));
  const lb=document.getElementById('tbSnapLabel'); if(lb) lb.textContent=snapVals.find(s=>s[0]===v)[1];
  stat(tf('msg.snap','スナップ {val}',{val:snapVals.find(s=>s[0]===v)[1]})); }

// ---- audio ----
const actx=new (window.AudioContext||window.webkitAudioContext)();
const masterGain=actx.createGain(); masterGain.gain.value=1; masterGain.connect(actx.destination);
const gain=actx.createGain(); gain.gain.value=0.12; gain.connect(masterGain);
const analyser=actx.createAnalyser(); analyser.fftSize=1024; masterGain.connect(analyser);
const vmData=new Float32Array(analyser.fftSize);
let audioBuf=null,srcNs=[],playing=false,startedAt=0,offset=0,playStartB=0;
function aTime(){ return playing? offset+(actx.currentTime-startedAt): offset; }
function play(){ if(!audioBuf)return;
  if(curAnim){ cur=curAnim.to; curAnim=null; }   // イージング中に再生したら着地点から
  if(camMode==='edit'&&vwB==null) vwB=viewBeat();   // 編集モードは再生開始時にビューアンカーを固定＝以後ヘッドだけが動きカメラ/ビューは非連動（2026-07-14改）
  // 再生中はvwBがヘッドに等速追走（両モード共通）: 画面上のヘッド位置は保ったまま世界がスクロールし、常に±24拍を描画キープ
  if(vwB!=null){ let d0=cur-vwB;
    if(d0>16){ vwB=cur-16; d0=16; }                            // ヘッドが窓端の外なら必要最小限だけ窓を寄せる（リピート直後等）
    else if(d0<-16){ vwB=Math.max(0,cur+16); d0=cur-vwB; }
    vwPlayD=d0; } else vwPlayD=null;
  if(!sigConnected('audio')){ showErr('音源の配線が切断されています（ノードエディタで接続してください）'); return; }
  stopS(); startedAt=actx.currentTime;
  offset=beatToTimeTM(cur); prevPlayBeat=cur; playStartB=cur;   // 遅延補正のクランプ基準（開始拍より後ろへは描画しない）
  const t0=actx.currentTime, off0=getSongOff();
  for(const sg of msegs()){                                // セグメントごとにスケジュール（Cカット済み音源・無音トリム対応）
    const bs=beatToTimeTM(sg.beat), rel=offset-bs;
    if(rel>=sg.dur-0.001) continue;
    let when=rel>=0?t0:t0-rel;
    let bo=off0+sg.off+(rel>=0?rel:0);                     // バッファ内の開始位置
    let du=rel>=0?sg.dur-rel:sg.dur;
    if(bo<0){ when+=-bo; du+=bo; bo=0; }                   // off負=先頭無音（その分あとから鳴らす）
    if(du<=0.001||bo>=audioBuf.duration-0.001) continue;   // 全部無音区間なら鳴らさない
    const s=actx.createBufferSource(); s.buffer=audioBuf; s.connect(gain);
    s.start(when,bo,du);                                   // 末尾はバッファ終端で自然に無音
    srcNs.push(s);
  }
  playing=true; document.getElementById('play').textContent='⏸'; }
function stopS(){ for(const s of srcNs){ try{s.stop()}catch(e){} try{s.disconnect()}catch(e){} } srcNs=[]; }
function pause(){ offset=aTime(); stopS(); playing=false; vwPlayD=null; document.getElementById('play').textContent='▶'; }
document.getElementById('vol').addEventListener('input',e=>{   // 右のフェーダー=マスター
  volCfg.m=+e.target.value; localStorage.setItem('bsnm_vol',JSON.stringify(volCfg));
  const el=document.getElementById('volM'), lv=document.getElementById('volMVal');
  if(el) el.value=volCfg.m; if(lv) lv.textContent=volCfg.m;
  applyVolumes();
});
{ const vol=document.getElementById('vol'), tip=document.getElementById('volTip'); let _tipT=null;   // 調整中はつまみの左に今何%か表示
  const showTip=()=>{ if(!tip) return;
    const fr=vol.getBoundingClientRect(); if(fr.height<10) return;   // フェーダー非表示中（INFO画面等）は出さない
    const v=+vol.value, pad=9;   // つまみの移動域（端の余白ぶんを差し引き）。value=100が上端
    tip.textContent=v+'%'; tip.style.display='block';
    tip.style.top=(fr.top+pad+(1-v/100)*(fr.height-pad*2))+'px';   // ビューポート座標（fixed）
    tip.style.left=(fr.left-tip.offsetWidth-6)+'px';
    clearTimeout(_tipT); _tipT=setTimeout(()=>{ tip.style.display='none'; },700); };
  vol.addEventListener('input',showTip);
  vol.addEventListener('pointerdown',showTip);
}
const avOffset=0;   // AVオフセットUIは廃止。音声出力レイテンシ補正のみ内部で使用
// ショートカット表示のON/OFF（5分割: 標準操作/NOTES/LIGHTING/NLE/INFO・localStorage保存）
const keyShow={common:localStorage.getItem('bsnm_kc')!=='0', node:localStorage.getItem('bsnm_kn')!=='0',
  notes:localStorage.getItem('bsnm_knt')!=='0', light:localStorage.getItem('bsnm_kl')!=='0',
  info:localStorage.getItem('bsnm_ki')!=='0'};
function applyShowKeys(){
  const ck=document.getElementById('commonKeys'); if(ck) ck.style.display=keyShow.common?'':'none';
  const nk=document.getElementById('nodeKeys'); if(nk) nk.style.display=((nodeColMode==='info')?keyShow.info:keyShow.node)?'':'none';   // 右列はNLE/INFOで別トグル
  const mk=document.getElementById('modeKeys'); if(mk) mk.style.display=(lightMode?keyShow.light:keyShow.notes)?'':'none';   // 左上はモードに応じて別トグル
}
{ const wire=(id,key,ls)=>{ const el=document.getElementById(id); if(!el) return;
    el.checked=keyShow[key];
    el.addEventListener('change',()=>{ keyShow[key]=el.checked; localStorage.setItem(ls,el.checked?'1':'0'); applyShowKeys(); }); };
  wire('keysCommon','common','bsnm_kc'); wire('keysNode','node','bsnm_kn');
  wire('keysNotes','notes','bsnm_knt'); wire('keysLight','light','bsnm_kl');
  wire('keysInfo','info','bsnm_ki'); }
applyShowKeys();
{ const cm=document.getElementById('chromaMode');   // Chromaモード On/OFF（ON=各ライト自由色 / OFF=バニラ配色。ヘルバ様指定 2026-07-13）
  if(cm){ cm.checked=chromaMode;
    cm.addEventListener('change',()=>{ chromaMode=cm.checked; localStorage.setItem('bsnm_chroma',cm.checked?'1':'0');
      try{ applyLaneVis();   // BOOSTレーンの表示/非表示を即反映（ON=隠す）。隠す時はBOOSTの選択も解除＝見えない物が選択されたまま残らない
        if(chromaMode){ for(const ev of [...lightSelection]) if(lightHiddenEv(ev)) lightSelection.delete(ev); } }catch(_){}
      // 400msデバウンスを待たず settings.json へ即確定＝トグル直後にリロードしても保存が消えない（ヘルバ様報告の修正 2026-07-13）
      try{ const data={}; for(let i=0;i<localStorage.length;i++){ const k=localStorage.key(i); if(k&&k.indexOf('bsnm_')===0) data[k]=localStorage.getItem(k); }
        fetch('__settings/save',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({data})}); }catch(_){}
      try{ updateChromaUI(); }catch(_){} stat(cm.checked?'Chromaモード ON（各ライト自由色・要Mod）':'バニラ配色モード（Mod無しでも全員に見える）'); }); } }
// ---- ショートカット表示のフローティング化: 上部ドラッグで移動（親ペインの外へは出ない）・▾たたむ・✕閉じる=設定のチェックOFF（再表示は設定から） ----
{ const posSaved=JSON.parse(localStorage.getItem('bsnm_keypos')||'{}');
  const foldSaved=JSON.parse(localStorage.getItem('bsnm_keyfold')||'{}');
  const clampXY=(el,x,y)=>{ const p=el.offsetParent||document.body;
    return [Math.max(0,Math.min(x,p.clientWidth-el.offsetWidth)), Math.max(0,Math.min(y,p.clientHeight-el.offsetHeight))]; };
  const mkFloat=(id,closeInfo)=>{ const el=document.getElementById(id); if(!el) return;
    const bd=document.createElement('div'); bd.className='mkbody';
    while(el.firstChild) bd.appendChild(el.firstChild);   // 既存の中身はボディへ（レンダラはボディだけ書き換える）
    const hd=document.createElement('div'); hd.className='mkhead';
    hd.innerHTML='<span style="flex:1"></span><button class="mkbtn mkFold" title="たたむ / ひらく">—</button><button class="mkbtn mkClose" title="閉じる（設定のショートカット表示で再表示）">✕</button>';
    el.append(hd,bd);
    if(foldSaved[id]) el.classList.add('keysFolded');
    if(posSaved[id]&&isFinite(posSaved[id].x)){ const [x,y]=clampXY(el,posSaved[id].x,posSaved[id].y);
      el.style.left=x+'px'; el.style.top=y+'px'; el.style.right='auto'; }
    hd.querySelector('.mkFold').addEventListener('click',ev=>{ ev.stopPropagation();
      const on=el.classList.toggle('keysFolded');
      foldSaved[id]=on?1:0; localStorage.setItem('bsnm_keyfold',JSON.stringify(foldSaved)); });
    hd.querySelector('.mkClose').addEventListener('click',ev=>{ ev.stopPropagation();
      const [key,ls,chk]=closeInfo();
      keyShow[key]=false; localStorage.setItem(ls,'0');
      const cb=document.getElementById(chk); if(cb) cb.checked=false;   // 設定画面のチェックも外す（再チェックで復活）
      applyShowKeys(); stat('ショートカット表示を閉じました（⚙設定の「ショートカット表示」で再表示できます）'); });
    let dg=null;
    hd.addEventListener('pointerdown',e=>{ if(e.button!==0||e.target.closest('.mkbtn')) return;
      e.preventDefault();
      const p=el.offsetParent||document.body, pr=p.getBoundingClientRect(), r=el.getBoundingClientRect();
      el.style.left=(r.left-pr.left)+'px'; el.style.top=(r.top-pr.top)+'px'; el.style.right='auto';   // right基準→left基準へ切替
      dg={sx:e.clientX,sy:e.clientY,ox:parseFloat(el.style.left),oy:parseFloat(el.style.top)};
      try{hd.setPointerCapture(e.pointerId);}catch(_){} });
    hd.addEventListener('pointermove',e=>{ if(!dg) return;
      const [x,y]=clampXY(el,dg.ox+e.clientX-dg.sx,dg.oy+e.clientY-dg.sy);
      el.style.left=x+'px'; el.style.top=y+'px'; });
    hd.addEventListener('pointerup',()=>{ if(!dg) return; dg=null;
      posSaved[id]={x:parseFloat(el.style.left)||0,y:parseFloat(el.style.top)||0};
      localStorage.setItem('bsnm_keypos',JSON.stringify(posSaved)); });
  };
  mkFloat('commonKeys',()=>['common','bsnm_kc','keysCommon']);
  mkFloat('nodeKeys',()=>nodeColMode==='info'?['info','bsnm_ki','keysInfo']:['node','bsnm_kn','keysNode']);   // 右列は今見えているNLE/INFOのチェックを外す
  mkFloat('modeKeys',()=>lightMode?['light','bsnm_kl','keysLight']:['notes','bsnm_knt','keysNotes']);   // 左上は今見えているモードのチェックを外す
}
document.getElementById('play').addEventListener('click',()=>{ playing?pause():play(); });

// 通過音（単音）
const hitGain=actx.createGain(); hitGain.gain.value=0.5; hitGain.connect(masterGain);
function blip(){ const t=actx.currentTime;
  const o=actx.createOscillator(); o.type='square'; o.frequency.value=880;
  const g=actx.createGain(); g.gain.setValueAtTime(0.22,t); g.gain.exponentialRampToValueAtTime(0.001,t+0.05);
  o.connect(g); g.connect(hitGain); o.start(t); o.stop(t+0.06); }
// メトロノーム（METRONOMEノードがONの間、拍頭でクリック音+CENTER点滅）
const metroGain=actx.createGain(); metroGain.gain.value=0.6; metroGain.connect(masterGain);
let metroFlashMs=0;
function metroNode(){ return extraNodes.find(n=>n.kind==='metro'); }
function metroTick(){ const t=actx.currentTime;
  const o=actx.createOscillator(); o.type='square'; o.frequency.value=1760;   // 通過音(880Hz)より1オクターブ上の短いクリック
  const g=actx.createGain(); g.gain.setValueAtTime(0.3,t); g.gain.exponentialRampToValueAtTime(0.001,t+0.03);
  o.connect(g); g.connect(metroGain); o.start(t); o.stop(t+0.04); }
let prevPlayBeat=0;

// ---- load / save ----
let files={}, handles={}, dirHandle=null, rawDiff=null, diffV3=false, currentDiffName='';
// 同一ハンドルへのqueryPermission/requestPermission再問い合わせを避ける（WebView2埋め込み環境で
// 2回目以降の呼び出しがレンダラをクラッシュさせる不具合の回避策。一度許可が取れたハンドルは
// セッション中に許可が失効しないので、以後は問い合わせ自体をスキップする）
const _fsPermOk=new WeakSet();
async function ensureRW(handle){
  if(_fsPermOk.has(handle)) return;
  if(await handle.queryPermission({mode:'readwrite'})!=='granted')
    await handle.requestPermission({mode:'readwrite'});
  _fsPermOk.add(handle);
}
// ---- プロジェクト(.nlmf): 元の .dat はいじらず、編集状態を project.nlmf に丸ごと保存 ----
let projDiffs={}, infoText='', infoFileName='Info.dat';
let projFileHandle=null;   // 「名前を付けて保存」で選んだ保存先（未指定なら曲フォルダ直下）
let infoJson=null, infoBase=null, infoDirty=false;
function stashCurrentDiff(){ if(!currentDiffName||!rawDiff) return;
  flushFlatEdits();   // 退避前に3D編集をcontentへ確定（難易度切替でクリップに反映されるように）
  alignNoteGroupTracks([...notes,...bombs,...walls,...arcs,...chains]);
  syncFlatToSections();   // _tr不一致でも常にフラット→contentを確定（チェイン/アークの保存漏れ防止）
  projDiffs[currentDiffName.toLowerCase()]={name:currentDiffName,v3:diffV3,base:rawDiff,
    notes,bombs,walls,arcs,chains,lightEvents,
    sections:structuredClone(sections)}; }   // クリップ構成（レイヤー配置）も難易度ごとに退避
// 空の難易度ベース（v3）。ゼロから作る難易度の切替・書き出しの土台
const EMPTY_V3=()=>({version:'3.2.0',bpmEvents:[],rotationEvents:[],colorNotes:[],bombNotes:[],obstacles:[],
  sliders:[],burstSliders:[],waypoints:[],basicBeatmapEvents:[],colorBoostBeatmapEvents:[],
  lightColorEventBoxGroups:[],lightRotationEventBoxGroups:[],
  basicEventTypesWithKeywords:{d:[]},useNormalEventsAsCompatibleEvents:true});
// notes/lights配線を現在のsectionsへ張り直す（audio/info/coverは維持）。難易度切替でIDが変わっても配置ガードが誤爆しない
function relinkDiffEdges(){
  graphEdges=graphEdges.filter(e=>e.sig!=='notes'&&e.sig!=='lights');
  const ordered=[...sections].sort((a,b)=>(a.beat||0)-(b.beat||0));
  for(const sig of ['notes','lights']){ let prev='in';
    for(const s2 of ordered){ graphEdges.push({fromId:prev,toId:s2.id,sig}); prev=s2.id; }
    graphEdges.push({fromId:prev,toId:'out',sig}); }
  edgesInited=true;
}
function resetDiffSections(){   // 新しい難易度は空のタイムラインから（シートは右クリックで作成）
  sections=[]; relinkDiffEdges();
}
// 難易度プルダウン: 標準5難易度を常時提供（空Sheetから難易度別に作るのが大前提）
function ensureDiffSelect(){
  const sel=document.getElementById('diff');
  if(sel.options.length) return;
  OUT_DIFFS.forEach(d=>{ const o=document.createElement('option');
    o.value=d+'Standard.dat'; o.textContent=d; sel.appendChild(o); });
  sel.onchange=()=>loadDiff(sel.value);
}
function initScratchDiff(){
  ensureDiffSelect();
  const sel=document.getElementById('diff');
  sel.value='HardStandard.dat';   // 既定=Hard
  currentDiffName='HardStandard.dat'; rawDiff=EMPTY_V3(); diffV3=true;
  stashCurrentDiff(); updateDiffLabel();
}
// ============ MEDIAライブラリ（CustomLevels一覧 → ドラッグでライン追加） ============
let libDirs=[], _dragMedia=null, _mediaGhostNd=null, _mediaGhostOv=null;   // ゴースト=ドラッグ中のドロップ位置プレビュー
let _restoringLibs=false;   // 起動時のライブラリ復元中は saveLibDirs の途中保存を抑止（未処理フォルダの取りこぼし＝SCANDAL消失バグ対策）
const lineSrc=new Map();   // uid → {dir,info,sheetId,cur} ドロップしたラインの元フォルダ（難易度切替用・セッション限り）
function fillDiffSelectFromInfo(info,selName){
  const sel=document.getElementById('diff'); sel.innerHTML='';
  const sets=info._difficultyBeatmapSets||[];
  const std=sets.find(s2=>s2._beatmapCharacteristicName==='Standard')||sets[0];
  ((std&&std._difficultyBeatmaps)||[]).forEach(d=>{ const o=document.createElement('option');
    o.value=d._beatmapFilename; o.textContent=d._difficulty; sel.appendChild(o); });
  if(selName) sel.value=selName;
  sel.onchange=()=>loadLineDiff(sel.value);
}
async function loadLineDiff(fname){
  // プルダウンは常にプロジェクト難易度の切替（クリップの元譜面差し替えではない）
  const src=lineSrc.get(activeUids.in);   // 旧MEDIAライン経路（現在は未使用）
  if(!src){ loadDiff(fname); return; }
  try{
    const df=await (await src.dir.getFileHandle(fname)).getFile();
    const frag=parseDiffFragment(JSON.parse(await df.text()));
    const sec=sections.find(x=>x.id===src.sheetId);
    if(!sec){ showErr('このクリップの元データが見つかりません'); return; }
    snapshot('node');
    const cp=a=>(a||[]).map(o=>({...o}));
    sec.content={notes:cp(frag.notes),bombs:cp(frag.bombs),walls:cp(frag.walls),arcs:cp(frag.arcs),chains:cp(frag.chains),lights:cp(frag.lights)};
    sec.len=Math.max(4,Math.ceil((frag._max+1)/4)*4);
    src.cur=fname;
    { const o=document.getElementById('diff').selectedOptions[0];
      sec._diffName=o?o.textContent:''; }
    compileLayersToFlat(); metaDirty=true;   // 位置=真実（レイヤー流儀）で再合成
    stat(tf('msg.diffSwitched','難易度を切り替えました: {name}',{name:sec._diffName||fname}));
  }catch(err){ showErr(tf('msg.diffLoadFail','難易度の読込に失敗: {err}',{err})); }
}
{ const sl=document.getElementById('libSize'), lg=document.getElementById('libGrid');
  const apply=v=>{ lg.style.gridTemplateColumns=`repeat(${10-v},1fr)`; };   // 左=6列(小) 右=2列(大) : v4→6列, v8→2列
  const sv=+localStorage.getItem('bsnm_libsz');
  sl.value=(sv>=4&&sv<=8)?sv:5;
  apply(+sl.value);
  sl.addEventListener('input',()=>{ apply(+sl.value); localStorage.setItem('bsnm_libsz',sl.value); }); }
document.getElementById('libAddBtn').addEventListener('click', async ()=>{
  let dh;
  try{ dh=await showDirectoryPicker(); }catch(e){ return; }
  stat('ライブラリをスキャンしています…');
  await scanLibrary(dh);
});
const AUDIO_EXTS=new Set(['egg','ogg','mp3','wav','flac','m4a','aac','opus']);
const IMAGE_EXTS=new Set(['png','jpg','jpeg','webp','gif','bmp']);   // MEDIAフォルダ内の画像=カバー画像アイテム（INFOのカバーノードへドラッグ可）
// 音楽アイテム/カスタム曲どちらでも音源FileHandleを返す（isMusic=直下ファイル、それ以外=曲フォルダ内の_songFilename）
async function getSongFile(item){
  if(item.isMusic) return item.songFh;
  return await item.dir.getFileHandle((item.info&&item.info._songFilename)||'song.egg');
}
// 埋め込みアートワーク抽出の純関数(_sniffMime/_id3Pic/_flacPic/_oggPic/_mp4Pic 等)は ../media/cover-parse.js へ切り出し（監査 2026-07-14）
async function extractArtwork(fh){
  try{
    const file=await fh.getFile();
    const buf=await file.slice(0,Math.min(file.size,4*1024*1024)).arrayBuffer();
    const u=new Uint8Array(buf); let pic=null;
    if(u[0]===0x49&&u[1]===0x44&&u[2]===0x33) pic=_id3Pic(u);                        // "ID3"
    else if(u[0]===0x66&&u[1]===0x4C&&u[2]===0x61&&u[3]===0x43) pic=_flacPic(u.subarray(4)); // "fLaC"
    else if(u[0]===0x4F&&u[1]===0x67&&u[2]===0x67&&u[3]===0x53) pic=_oggPic(u);      // "OggS"
    else if(u[4]===0x66&&u[5]===0x74&&u[6]===0x79&&u[7]===0x70) pic=_mp4Pic(u);      // "....ftyp"
    if(!pic||!pic.data||!pic.data.length) return null;
    return new Blob([pic.data],{type:pic.mime||'image/jpeg'});
  }catch(e){ return null; }
}
// 抽出したアートワークをアイテムのサムネイル（波形→画像）に反映
function applyArtwork(item,blob,lib){
  const url=URL.createObjectURL(blob); item.coverURL=url; item._coverBlob=blob; lib.urls.push(url);
  const th=item._el&&item._el.querySelector('.libThumb'); if(!th) return;
  th.classList.remove('libWave'); th.innerHTML='';
  const im=document.createElement('img'); im.src=url; th.appendChild(im);
  th.appendChild(Object.assign(document.createElement('div'),{className:'libMark'}));
  renderLibMark(item);   // 画像データ=青チップを追加
}
// setTimeout(0)で1回イベントループへ明け渡す＝タイトなawaitループが描画/入力を飢餓状態にするのを防ぐ
// （awaitだけでは足りない: File System Access APIの解決がマイクロタスクとして連続すると、
//  requestAnimationFrame等のマクロタスクが後回しにされ続け、体感「フリーズ」になる＝ヘルバ様報告の直接原因）
function _idleYield(){ return new Promise(r=>setTimeout(r,0)); }
// 埋め込みアートワークを背景で1件ずつ抽出（alive()がfalseになったら中断）。scanLibrary/scanAssetLibrary 共用
function extractArtworkBatch(musicItems,lib,alive){
  if(!musicItems.length) return;
  (async()=>{ for(const it of musicItems){ if(!alive()) break;
    try{ const blob=await extractArtwork(it.songFh); if(blob) applyArtwork(it,blob,lib); }catch(e){}
    await _idleYield(); } })();
}
// Beat Saber譜面フォルダのカバー画像も同じく背景で1件ずつ（大量フォルダ登録時の起動フリーズ対策・ヘルバ様報告）
function extractCoverBatch(mapItems,lib,alive){
  if(!mapItems.length) return;
  (async()=>{ for(const {item,dirH,coverName} of mapItems){ if(!alive()) break;
    try{ const cf=await dirH.getFileHandle(coverName); const blob=await cf.getFile(); applyArtwork(item,blob,lib); }catch(e){}
    await _idleYield(); } })();
}
async function scanLibrary(dh){
  const lib={dh,els:[],urls:[]};
  libDirs.push(lib);
  // libTitle（「ライブラリ（ジャケットをNODEへ…）」の案内文）は廃止（ヘルバ様指示）
  let count=0, mcount=0, icount=0; const musicItems=[], mapCoverItems=[];
  const MAXDEPTH=8;   // アーティスト/アルバム/曲… の深い階層も辿る（暴走防止の上限）
  let _walkN=0;
  async function walk(dir,depth){
    for await (const h of dir.values()){
      if((++_walkN)%6===0){ await _idleYield(); renderLibList(); }   // 数件ごとに描画へ明け渡す＝大量フォルダでもフリーズせず徐々に表示される
      if(h.kind==='directory'){
        // info.dat があれば Beat Saber カスタム曲。中の.eggは列挙せず＝重複回避（ヘルバ様指示）。中へは降りない
        let infoFh=null;
        for(const nm of ['info.dat','Info.dat','INFO.DAT']){
          try{ infoFh=await h.getFileHandle(nm); break; }catch(e){} }
        if(infoFh){
          try{
            const info=JSON.parse(await (await infoFh.getFile()).text());
            // カバー画像はここで同期抽出しない＝音楽ファイルの埋め込みアートワークと同じく背景で1件ずつ（大量の譜面フォルダ登録時にUIが固まるバグの対策）
            const mit={name:info._songName||h.name, info, dir:h, coverURL:null};
            addLibItem(mit,lib);
            if(info._coverImageFilename) mapCoverItems.push({item:mit, dirH:h, coverName:info._coverImageFilename});
            count++;
          }catch(e){}
          continue;
        }
        // 通常フォルダ（アーティスト/アルバム等）→ 下の階層も再帰検索して曲ファイルを抽出
        if(depth<MAXDEPTH){ try{ await walk(h,depth+1); }catch(e){} }
      }else if(h.kind==='file'){
        const ext=(h.name.match(/\.([^.]+)$/)||[])[1]?.toLowerCase();
        if(ext&&AUDIO_EXTS.has(ext)){   // 任意階層の音声ファイル＝音楽アイテム（譜面なし。埋め込みアートワークは背景で抽出）
          const mit={name:h.name.replace(/\.[^.]+$/,''), songFh:h, isMusic:true};
          addLibItem(mit,lib); musicItems.push(mit); mcount++;
        }else if(ext&&IMAGE_EXTS.has(ext)){   // 画像ファイル＝カバー画像アイテム（INFOのカバーノードへドラッグ）
          try{ const iurl=URL.createObjectURL(await h.getFile());
            addLibItem({name:h.name.replace(/\.[^.]+$/,''), fileName:h.name, imgFh:h, isImage:true, coverURL:iurl},lib); icount++; }catch(e){}
        }
      }
    }
  }
  await walk(dh,0);
  renderLibList(); if(!_restoringLibs) saveLibDirs();   // 復元中は保存しない（復元完了後に一括保存＝全フォルダ揃ってから）
  const parts=[]; if(count) parts.push(`${count}曲`); if(mcount) parts.push(`音楽${mcount}件`); if(icount) parts.push(`画像${icount}件`);
  stat(tf('msg.libLoaded','ライブラリ: {name} から {parts} 読み込みました',{name:dh.name,parts:parts.join('・')||t('word.zeroItems','0件')}));
  if(!count&&!mcount&&!icount) showErr(tf('msg.libNotFound','{name} に譜面フォルダ・音楽ファイルが見つかりませんでした',{name:dh.name}));
  // 埋め込みアートワークを背景で抽出（1件ずつ＝UIをブロックしない。無ければ波形アイコンのまま）
  extractArtworkBatch(musicItems, lib, ()=>lib.els.length>0);   // 背景でアートワーク抽出（フォルダが外れたら中断）
  extractCoverBatch(mapCoverItems, lib, ()=>lib.els.length>0);   // 譜面フォルダのカバーも同様に背景抽出
}
// アセット=アプリ配下の asset/ フォルダをHTTP経由で常時接続（起動時に自動読込・CustomLevelsの上に固定）
async function scanAssetLibrary(){
  let lib=libDirs.find(l=>l.asset);
  if(lib){ for(const el of lib.els) el.remove(); lib.els.length=0; for(const u of lib.urls) URL.revokeObjectURL(u); lib.urls.length=0; }
  else { lib={asset:true,name:'アセット',els:[],urls:[]}; libDirs.unshift(lib); }   // 先頭=Allの直下
  let ccount=0, mcount=0; const musicItems=[]; const MAXDEPTH=8;
  const httpFh=(url,name)=>({name,getFile:async()=>new File([await (await fetch(url)).blob()],name)});
  async function walk(path,depth){
    let links;
    try{ const res=await fetch(path); if(!res.ok) return;
      const html=await res.text(); const doc=new DOMParser().parseFromString(html,'text/html');
      links=[...doc.querySelectorAll('a[href]')].map(a=>a.getAttribute('href'))
        .filter(h=>h&&h!=='../'&&!h.startsWith('/')&&!h.startsWith('?')&&!h.startsWith('..'));
    }catch(e){ return; }
    for(const href of links){
      if(href.endsWith('/')){ if(depth<MAXDEPTH) await walk(path+href,depth+1); continue; }   // サブフォルダ=再帰
      const fname=decodeURIComponent(href);
      const ext=(fname.match(/\.([^.]+)$/)||[])[1]?.toLowerCase();
      if(ext==='nlmclip'){   // NLEクリップ（NOTES/LIGHT部品）＝アセットの主用途
        try{
          const clip=JSON.parse(await (await fetch(path+href)).text());
          if(clip&&clip.nlmClip){
            const it={name:clip.name||fname.replace(/\.nlmclip$/i,''), isClip:true, _asset:true,
              clipType:(clip.type==='light'?'light':'notes'), _fileName:fname,
              content:clip.content||{}, _len:Math.max(1,clip.len||8)};
            it._frag=fragFromContent(it.content); it._bmDiff='*';   // ドラッグ用フラグメント（即用意）
            addLibItem(it,lib); ccount++;
          }
        }catch(e){}
        continue;
      }
      if(ext&&AUDIO_EXTS.has(ext)){   // 音楽も入れられる（今は主用途ではない）
        const mit={name:fname.replace(/\.[^.]+$/,''), isMusic:true, _asset:true, songFh:httpFh(path+href,fname)};
        addLibItem(mit,lib); musicItems.push(mit); mcount++;
      }
    }
  }
  await walk('asset/',0);
  renderLibList();
  extractArtworkBatch(musicItems, lib, ()=>libDirs.includes(lib));   // 背景でアートワーク抽出（libが外れたら中断）
}
// NLEクリップ(section)を .nlmclip としてアセットへ保存（serve.py の書き込みAPI経由）
async function saveClipToAsset(sec){
  if(!sec||!sec.content){ showErr('保存できるクリップがありません'); return; }
  const type=secLk(sec)==='l'?'light':'notes';
  const c=sec.content||{};
  const data={nlmClip:1,type,name:sec.label||'clip',len:sec.len||8,
    content:{notes:c.notes||[],bombs:c.bombs||[],walls:c.walls||[],arcs:c.arcs||[],chains:c.chains||[],lights:c.lights||[]}};
  try{
    const res=await fetch('__asset/save',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({name:data.name,data})});
    const j=await res.json();
    if(j&&j.ok){ await scanAssetLibrary(); showOk(tf('msg.assetSaved','アセットへ保存しました: {name}（{type}）',{name:(j.name||data.name+'.nlmclip').replace(/\.nlmclip$/i,''),type:type==='light'?'LIGHT':'NOTES'})); }
    else showErr(tf('msg.assetSaveFail','アセット保存に失敗: {err}',{err:(j&&j.error)||t('word.unknown','不明')}));
  }catch(e){ showErr(tf('msg.assetSaveFailSrv','アセット保存に失敗（サーバー未対応?）: {err}',{err:e})); }
}
// MEDIAのアセットクリップを右クリックで改名（.nlmclip をリネーム＋name更新）
function renameAssetClip(item){
  const el=item._el; if(!el) return;
  const nm=el.querySelector('.libName'); if(!nm) return;
  const inp=document.createElement('input'); inp.type='text'; inp.value=item.name;
  inp.style.cssText='width:100%;box-sizing:border-box;background:#1d1d20;border:1px solid #8160e3;border-radius:3px;color:#fff;font:inherit;font-size:10.5px;text-align:center;padding:1px 3px;';
  let done=false;
  const restore=()=>{ if(done) return; done=true; const d=Object.assign(document.createElement('div'),{className:'libName'}); d.textContent=item.name; d.title=item.name; inp.replaceWith(d); };
  const commit=async()=>{ if(done) return; const val=inp.value.trim(); done=true;
    const d=Object.assign(document.createElement('div'),{className:'libName'}); d.textContent=val||item.name; d.title=val||item.name; inp.replaceWith(d);
    if(val&&val!==item.name){
      try{ const res=await fetch('__asset/rename',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({from:item._fileName,to:val})});
        const j=await res.json(); if(j&&j.ok){ await scanAssetLibrary(); showOk(tf('msg.clipRenamed','クリップ名を変更しました: {name}',{name:val})); } else showErr(tf('msg.renameFail','改名に失敗: {err}',{err:(j&&j.error)||''})); }catch(e){ showErr(tf('msg.renameFail','改名に失敗: {err}',{err:e})); } } };
  nm.replaceWith(inp); inp.focus(); inp.select();
  inp.addEventListener('keydown',e=>{ e.stopPropagation(); if(e.key==='Enter') commit(); else if(e.key==='Escape') restore(); });
  inp.addEventListener('blur',commit);
}
async function deleteAssetClip(item){
  try{ const res=await fetch('__asset/delete',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:item._fileName})});
    const j=await res.json(); if(j&&j.ok){ await scanAssetLibrary(); showOk(tf('msg.clipDeleted','クリップを削除しました: {name}',{name:item.name})); } else showErr('削除に失敗'); }catch(e){ showErr(tf('msg.deleteFail','削除に失敗: {err}',{err:e})); }
}
function saveLibDirs(){ /* 無効化: FileSystemHandleのIndexedDB保存がWebView2でクラッシュするため */ }   // アセット(常時接続)は保存対象外
// 起動時: 保存済みライブラリを復元（権限が残っていれば即スキャン、無ければクリックで再接続）
// ※クリックするまでスキャンを遅延する方式を試したが、フリーズの原因はMEDIAではなかった（ヘルバ様確認）ため元に戻す。
// カバー抽出の背景バッチ化・walk()の定期yieldは害が無いのでそのまま残す。
(async()=>{
  await new Promise(r2=>setTimeout(r2,0));   // モジュール評価完了後に実行（idbの初期化前アクセスを回避）
  try{ await scanAssetLibrary(); }catch(e){}   // アセット=常時接続（asset/ フォルダをHTTPで自動読込・先頭固定）
  _restoringLibs=true;   // 復元中は途中保存を止める（全フォルダが揃う前にscanLibrary→saveLibDirsが走ると、まだ処理していないフォルダをidbから消す＝SCANDAL消失の原因）
  try{
    const saved=(await idbGet('libDirs'))||[];
    for(const dh of saved){
      try{
        if((await dh.queryPermission({mode:'read'}))==='granted') await scanLibrary(dh);
        else { libDirs.push({dh,els:[],urls:[],pending:true}); renderLibList(); }   // 権限が外れていても pending として保持（薄く表示・クリックで再接続）
      }catch(e){}
    }
  }catch(e){}
  _restoringLibs=false; saveLibDirs();   // 復元完了後に一括保存: 許可済み/pending の両方を漏れなく保存＝CustomLevelsもSCANDALも同じ仕組みで永続化
  renderLibList();   // ライブラリ0件でも左カタログに「All」を表示
})();
let _libActiveCat=null;   // 選択中カタログ（null=All、それ以外=libオブジェクト）
function applyLibFilter(){ const g=document.getElementById('libGrid'); if(!g) return;
  for(const el of g.children){ el.style.display=(!_libActiveCat||el._lib===_libActiveCat)?'':'none'; } }
function updateLibCatSel(){ const box=document.getElementById('libList'); if(!box) return;   // 選択ハイライトだけ更新（リスト再構築なし＝要素が消えずダブルクリックが効く）
  for(const c of box.children){ c.classList.toggle('on',(c._lib||null)===(_libActiveCat||null)); } }
// アセットクリップのサムネアイコン: NOTES=赤青ブロック / LIGHT=横バー
const LIB_CLIP_NOTES_ICO='<svg viewBox="0 0 48 48" width="100%" height="100%" preserveAspectRatio="xMidYMid meet" style="display:block"><rect x="7" y="7" width="15" height="15" rx="2.5" fill="#e0355a"/><rect x="26" y="7" width="15" height="15" rx="2.5" fill="#2f6fe0"/><rect x="7" y="26" width="15" height="15" rx="2.5" fill="#2f6fe0"/><rect x="26" y="26" width="15" height="15" rx="2.5" fill="#e0355a"/></svg>';
const LIB_CLIP_LIGHT_ICO='<svg viewBox="0 0 48 48" width="100%" height="100%" preserveAspectRatio="xMidYMid meet" style="display:block"><g fill="#ffd82d"><rect x="8" y="11" width="26" height="5" rx="2.5"/><rect x="8" y="21.5" width="32" height="5" rx="2.5" opacity="0.85"/><rect x="8" y="32" width="19" height="5" rx="2.5" opacity="0.7"/></g></svg>';
// インラインHTML用ミニアイコン（難易度カウント表示など。♪/☀の置き換え）
const ICO_N_MINI='<svg viewBox="0 0 48 48" width="11" height="11" style="vertical-align:-2px"><rect x="7" y="7" width="15" height="15" rx="2.5" fill="#e0355a"/><rect x="26" y="7" width="15" height="15" rx="2.5" fill="#2f6fe0"/><rect x="7" y="26" width="15" height="15" rx="2.5" fill="#2f6fe0"/><rect x="26" y="26" width="15" height="15" rx="2.5" fill="#e0355a"/></svg>';
const ICO_L_MINI='<svg viewBox="0 0 48 48" width="11" height="11" style="vertical-align:-2px"><g fill="#ffd82d"><rect x="8" y="11" width="26" height="5" rx="2.5"/><rect x="8" y="21.5" width="32" height="5" rx="2.5" opacity="0.85"/><rect x="8" y="32" width="19" height="5" rx="2.5" opacity="0.7"/></g></svg>';
// 左下チップの色: 保有データ種別（左から 音楽=緑 / NOTES=紫 / ライト=黄 / 画像=青）
function libMarkColors(item){
  if(item.isClip) return [item.clipType==='light'?'#ffd82d':'#8160e3'];   // クリップ=種別色1つ（NOTES紫/LIGHT黄）
  if(item.isImage) return ['#4dc8ff'];    // 画像=カバー(青)のみ
  const cols=['#56ffc1'];                 // 音源は常に有る＝音楽(緑)
  if(!item.isMusic){ cols.push('#e36ea8','#8160e3','#ffd82d'); }   // カスタム曲=曲情報(ピンク)＋譜面(NOTES紫＋ライト黄)
  if(item.coverURL) cols.push('#4dc8ff'); // アートワーク/カバー=画像(青)
  return cols;
}
function renderLibMark(item){
  const mk=item._el&&item._el.querySelector('.libMark'); if(!mk) return;
  mk.innerHTML='';
  for(const c of libMarkColors(item)){ const s=document.createElement('i'); s.className='libMarkSeg'; s.style.background=c; mk.appendChild(s); }
}
function addLibItem(item,lib){
  const grid=document.getElementById('libGrid');
  const el=document.createElement('div'); el.className='libItem'; el.draggable=true; el._lib=lib; item._el=el;   // アートワーク後追い反映用
  const th=document.createElement('div'); th.className='libThumb';
  if(item.coverURL){ const im=document.createElement('img'); im.src=item.coverURL; th.appendChild(im); }
  else if(item.isClip){ th.classList.add('libClip', item.clipType==='light'?'libClipL':'libClipN'); th.innerHTML=item.clipType==='light'?LIB_CLIP_LIGHT_ICO:LIB_CLIP_NOTES_ICO; }   // クリップ=種別アイコン
  else if(item.isMusic){ th.classList.add('libWave'); th.innerHTML=LIB_WAVE_ICO; }   // アートワーク無しの音楽ファイル=緑枠に波形
  else th.textContent='♪';
  th.appendChild(Object.assign(document.createElement('div'),{className:'libMark'}));   // 保有データの色チップ
  const nm=document.createElement('div'); nm.className='libName'; nm.textContent=item.name; nm.title=item.name;
  el.append(th,nm);
  renderLibMark(item);   // el に th を append した後（querySelectorが効くように）
  el.addEventListener('click',()=>{ for(const s of grid.querySelectorAll('.libItem.sel')) s.classList.remove('sel'); el.classList.add('sel'); });   // 選択ハイライト
  if(_libActiveCat&&lib!==_libActiveCat) el.style.display='none';   // 現在のカタログ絞り込みを反映
  el.addEventListener('dragstart',ev=>{ _dragMedia=item; prepareMediaFrag(item); prepareMediaWave(item);   // 先読み: ピアノロール+波形ゴースト
    ev.dataTransfer.setData('text/plain',item.name); ev.dataTransfer.effectAllowed='copy';
    try{ ev.dataTransfer.setDragImage(_emptyDragImg,0,0); }catch(_){}   // ネイティブのドラッグ画像を消す＝独自の追従アイコンで制御（NLE上では隠せる・ヘルバ様指定 2026-07-14）
    startMediaDragIcon(el,ev.clientX,ev.clientY); });
  el.addEventListener('dragend',()=>{ removeMediaDragIcon(); setTimeout(()=>{ _dragMedia=null; _mediaGhostNd=null; _mediaGhostOv=null; },200); });
  el.addEventListener('contextmenu',ev=>{ ev.preventDefault();
    const menu=(item._asset&&item.isClip)
      ? [ [t('ctx.rename2','✏️ 名前を変更'),()=>renameAssetClip(item)],
          [t('ctx.delClip2','🗑 クリップを削除'),()=>deleteAssetClip(item)] ]
      : [ [t('ctx.openFolder','📁 フォルダの場所を開く'),()=>showOk(tf('msg.openFolder','📂 フォルダを開く…（デスクトップ版で実動作に対応予定: {name}）',{name:item.name}))],   // 統一様式: 通常📁・押したら📂（実処理はTauri化時）
          ...((item.isClip||item.isImage||item.isMusic)?[]:[ ['---'], [t('ctx.loadSongData','📥 曲データを読み込む'),()=>bulkLoadSongData(item)] ]) ];
    showMenu(ev.clientX,ev.clientY,menu); });
  lib.els.push(el);
  if(item.coverURL) lib.urls.push(item.coverURL);
  grid.appendChild(el);
}
const LIB_FOLDER_ICO='<svg viewBox="0 0 24 24" width="15" height="15" style="display:block"><path d="M2.5 6.6 a1.8 1.8 0 0 1 1.8-1.8 h4.3 a1 1 0 0 1 .8.4 l1 1.35 a1 1 0 0 0 .8.4 h8.5 a1.8 1.8 0 0 1 1.8 1.8 v8.2 a1.8 1.8 0 0 1 -1.8 1.8 H4.3 a1.8 1.8 0 0 1 -1.8-1.8 z" fill="#e3b34e"/></svg>';   // Blender風の黄色フォルダ
const LIB_ALL_ICO='<svg viewBox="0 0 24 24" width="14" height="14" style="display:block"><rect x="4.5" y="4.5" width="15" height="15" rx="2.5" fill="none" stroke="currentColor" stroke-width="2"/><rect x="9.5" y="9.5" width="5" height="5" rx="1" fill="currentColor"/></svg>';   // 画像1の「All」＝四角＋中点
// アートワーク無しの音楽ファイル用: 緑枠＋波形（テーマ緑 #56ffc1）
const LIB_WAVE_ICO='<svg viewBox="0 0 48 48" width="100%" height="100%" preserveAspectRatio="xMidYMid meet" style="display:block"><g fill="none" stroke="#56ffc1" stroke-width="2.4" stroke-linecap="round"><line x1="9" y1="21" x2="9" y2="27"/><line x1="14" y1="16" x2="14" y2="32"/><line x1="19" y1="12" x2="19" y2="36"/><line x1="24" y1="9" x2="24" y2="39"/><line x1="29" y1="14" x2="29" y2="34"/><line x1="34" y1="17" x2="34" y2="31"/><line x1="39" y1="20" x2="39" y2="28"/></g></svg>';
function libLabels(){ try{ return JSON.parse(localStorage.getItem('bsnm_libLabels')||'{}'); }catch(_){ return {}; } }   // フォルダの表示名（実フォルダ名→カスタム名）
function libDisp(lib){ if(lib.asset) return lib.name||'アセット'; return libLabels()[lib.dh.name]||lib.dh.name; }
function setLibLabel(key,label){ const m=libLabels(); if(label&&label!==key) m[key]=label; else delete m[key]; localStorage.setItem('bsnm_libLabels',JSON.stringify(m)); }
function renderLibList(){   // 左カタログ列（Blender風）: All＋各フォルダ。クリックでグリッドを絞り込み
  const box=document.getElementById('libList'); if(!box) return; box.innerHTML='';
  if(_libActiveCat&&!libDirs.includes(_libActiveCat)) _libActiveCat=null;
  const mkCat=(ico,name,lib)=>{ const c=document.createElement('div'); c.className='libCat'; c._lib=lib||null;
    c.innerHTML=`<span class="libCatIco">${ico}</span><span class="libCatName"></span>`;
    c.querySelector('.libCatName').textContent=name; c.title=name;
    if((_libActiveCat||null)===(lib||null)) c.classList.add('on');
    box.appendChild(c); return c; };
  const catAll=mkCat(LIB_ALL_ICO,'All',null);
  catAll.onclick=()=>{ _libActiveCat=null; updateLibCatSel(); applyLibFilter(); };   // 選択更新のみ（再構築しない＝ダブルクリック改名を壊さない）
  libDirs.forEach(lib=>{
    if(lib.asset){   // アセット=常時接続の固定カテゴリ（CustomLevelsの上・削除/改名なし）
      const c=mkCat('<span style="display:inline-block;width:14px;text-align:center;font-size:13px;color:#9a9aa2">›</span>', libDisp(lib), lib);   // 他フォルダと同じ「›」（緑キューブは分かりづらい・ヘルバ様指示）
      c.title='アセット（常時接続: assetフォルダ）';
      c.onclick=(e)=>{ _libActiveCat=lib; updateLibCatSel(); applyLibFilter(); };
      return;
    }
    const c=mkCat('<span style="display:inline-block;width:14px;text-align:center;font-size:13px;color:#9a9aa2">›</span>', libDisp(lib), lib);   // フォルダ項目の左に「›」（ヘルバ様指示）
    if(lib.pending){ c.querySelector('.libCatIco').style.opacity=.4; c.title=libDisp(lib)+'（クリックで再接続）'; }   // 未接続=フォルダを薄く
    c.querySelector('.libCatName').addEventListener('dblclick',ev=>{ ev.stopPropagation();   // ダブルクリックで表示名を変更
      const span=ev.currentTarget;
      const inp=document.createElement('input'); inp.type='text'; inp.value=libDisp(lib);
      inp.style.cssText='flex:1;min-width:0;background:#1d1d20;border:1px solid #8160e3;border-radius:3px;color:#fff;font:inherit;font-size:12px;padding:1px 5px;';
      span.replaceWith(inp); inp.focus(); inp.select();
      inp.addEventListener('click',e2=>e2.stopPropagation());
      inp.addEventListener('keydown',e2=>{ e2.stopPropagation();
        if(e2.key==='Enter'){ setLibLabel(lib.dh.name,inp.value.trim()); renderLibList(); }
        else if(e2.key==='Escape'){ renderLibList(); } });
      inp.addEventListener('blur',()=>{ setLibLabel(lib.dh.name,inp.value.trim()); renderLibList(); }); });
    const del=document.createElement('button'); del.className='libDel'; del.textContent='−';
    del.title='このフォルダをライブラリから外す';
    del.onclick=(e)=>{ e.stopPropagation();
      for(const el of lib.els) el.remove();
      for(const u of lib.urls) URL.revokeObjectURL(u);
      libDirs=libDirs.filter(l=>l!==lib);
      if(_libActiveCat===lib) _libActiveCat=null;
      renderLibList(); applyLibFilter(); saveLibDirs();
      stat(tf('msg.libRemoved','ライブラリから外しました: {name}',{name:lib.dh.name})); };
    c.appendChild(del);
    if(lib.pending){ c.onclick=async(e)=>{ if(e.target.closest('.libDel')) return;   // 未接続=クリックで再接続
        try{ if((await lib.dh.requestPermission({mode:'read'}))!=='granted') return; }catch(_){ return; }
        libDirs=libDirs.filter(l=>l!==lib); await scanLibrary(lib.dh); }; }
    else c.onclick=(e)=>{ if(e.target.closest('.libDel')) return; _libActiveCat=lib; updateLibCatSel(); applyLibFilter(); };   // 選択更新のみ（再構築しない）
  });
}
// ---- MEDIAドラッグの独自追従アイコン: ネイティブ画像は透明化し、これで表示。NLE(タイムライン)上に来たら隠してゴーストだけにする（ヘルバ様指定 2026-07-14） ----
const _emptyDragImg=Object.assign(new Image(),{src:'data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7'});   // 1x1透明GIF（起動時に先読み）
let _mediaDragIcon=null;
function _overNLE(x,y){ for(const cv of [ndcv,ovcv,document.getElementById('prcv')]){ if(!cv) continue;
  const r=cv.getBoundingClientRect(); if(x>=r.left&&x<=r.right&&y>=r.top&&y<=r.bottom) return true; } return false; }
function startMediaDragIcon(el,x,y){ removeMediaDragIcon();
  const ic=el.cloneNode(true); ic.classList.add('libDragIcon');   // サムネイル(img/SVG/文字)ごと複製＝ネイティブ画像と同じ見た目
  ic.style.cssText='position:fixed;margin:0;pointer-events:none;z-index:99999;opacity:.9;width:'+el.offsetWidth+'px;transform:translate(-50%,-50%);';
  document.body.appendChild(ic); _mediaDragIcon=ic; moveMediaDragIcon(x,y); }
function moveMediaDragIcon(x,y){ if(!_mediaDragIcon) return;
  _mediaDragIcon.style.display=_overNLE(x,y)?'none':'';   // NLE上ではアイコンを隠す＝ゴーストだけ
  _mediaDragIcon.style.left=x+'px'; _mediaDragIcon.style.top=y+'px'; }
function removeMediaDragIcon(){ if(_mediaDragIcon){ _mediaDragIcon.remove(); _mediaDragIcon=null; } }
document.addEventListener('dragover',e=>{ if(_dragMedia&&_mediaDragIcon) moveMediaDragIcon(e.clientX,e.clientY); });   // ネイティブは座標を渡さない環境対策＝追従は自前で
ndcv.addEventListener('dragover',e=>{ if(_dragMedia){ e.preventDefault(); e.dataTransfer.dropEffect='copy';
  const r=ndcv.getBoundingClientRect(); _mediaGhostNd={sx:e.clientX-r.left,sy:e.clientY-r.top}; } });   // ゴーストクリップ追従
ndcv.addEventListener('dragleave',()=>{ _mediaGhostNd=null; });
ndcv.addEventListener('drop',e=>{
  if(!_dragMedia) return;
  e.preventDefault();
  const r=ndcv.getBoundingClientRect(), sx=e.clientX-r.left, sy=e.clientY-r.top;
  const [wx,wy]=ndFromScreen(sx,sy);
  const item=_dragMedia; _dragMedia=null; _mediaGhostNd=null;
  if(item.isImage){ showErr(t('msg.imgToCover','画像はINFOのカバー画像ノードへドラッグしてください')); return; }   // 画像はカバー専用
  { const la=laneAtY(sy);
    addSongLine(item,wx,wy,{beat:Math.max(0,snapV(lXToBeat(sx))),lk:la.lk,track:la.gi}); }   // ドロップ位置（拍・レーン種・レーン）に配置
});
// Musicレーンへのドロップ = 音源をその位置に配置（譜面・曲情報は変更しない）
ovcv.addEventListener('dragover',e=>{ if(_dragMedia){ e.preventDefault(); e.dataTransfer.dropEffect='copy';
  const r=ovcv.getBoundingClientRect(); _mediaGhostOv=e.clientX-r.left; } });
ovcv.addEventListener('dragleave',()=>{ _mediaGhostOv=null; });
ovcv.addEventListener('drop',e=>{
  if(!_dragMedia) return;
  e.preventDefault();
  const r=ovcv.getBoundingClientRect(), sx=e.clientX-r.left;
  const item=_dragMedia; _dragMedia=null; _mediaGhostOv=null;
  if(item.isImage){ showErr(t('msg.imgToCover','画像はINFOのカバー画像ノードへドラッグしてください')); return; }   // 画像はカバー専用
  if(item.isClip){ showErr(item.clipType==='light'?t('msg.clipToLight','LIGHTクリップは LIGHT レーンへ'):t('msg.clipToNotes','NOTESクリップは NOTES レーンへ')); return; }   // クリップはMusicレーン不可（ヘルバ様指定 2026-07-14）
  const w=tlWindow(cur), b=Math.max(0,snapV(w.b0+(sx-TLGUT)/(ovW-TLGUT)*w.span));
  loadSongFromItem(item,b);
});
// ライブラリの曲の音源だけをMusicレーンへ読み込む（配置拍=beat）
async function loadSongFromItem(item,beat){
  try{
    const fh=await getSongFile(item);
    const f=await fh.getFile();
    if(playing) pause();
    audioBuf=await actx.decodeAudioData(await f.arrayBuffer());
    songDur=audioBuf.duration;
    const inf=item.info||{};
    const bpm=+inf._beatsPerMinute;
    if(bpm>0){ infoBase=infoBase||{}; setBPMv(bpm); }   // カスタム曲=BPMを読み込み（infoBaseを用意して_beatsPerMinuteも保存）
    if(inf._previewStartTime!=null&&inf._previewStartTime!==''){ infoBase=infoBase||{}; infoBase._previewStartTime=+inf._previewStartTime; }   // 試聴プレビュー区間も自動取り込み
    if(inf._previewDuration!=null&&inf._previewDuration!==''){ infoBase=infoBase||{}; infoBase._previewDuration=+inf._previewDuration; }
    if(infoBase) applyInfoChain();
    buildWaveData();
    document.getElementById('tbgTime').style.display='';
    songDeleted=false; ensureGraphIO();
    if(songNode){ songNode.name=f.name; songNode.handle=fh; songNode.nativePath=''; }
    musicBeat=Math.max(0,beat); musicSegs=null; musicSelSet=new Set([0]); metaDirty=true;
    showOk(tf('msg.audioPlaced','音源を配置しました: {name}（拍 {beat}{bpm}）',{name:f.name,beat:musicBeat,bpm:bpm>0?`・BPM ${BPM}`:''}));
  }catch(err){ showErr(tf('msg.loadAudioFail','音源の読込に失敗: {err}',{err})); }
}
// INFO画面へのドロップ = 曲情報を「未接続のノード3枚」として配置（書き出しへは自分で繋ぐ=ヘルバ様指定）
async function dropInfoNodesFromItem(item,wx,wy){
  const info=item.info||{};
  if(item.isMusic||item.isImage){   // 音楽ファイル/画像ファイル=カバー画像ノードのみ（曲情報/設定は作らない・ヘルバ様指示）
    infoSnapshot(); _infoSnapSup=true;
    const cid=addSrcNode('cover',wx,wy);
    const hasArt=!!(item._coverBlob||item.coverURL);
    if(hasArt) infoGraph.nodes[cid].data.name=item.isImage?(item.fileName||item.name):(item.name||'artwork')+'.jpg';
    _infoSnapSup=false;
    _inSel=new Set([cid]); infoSelApply(); layoutInfoNodes(); metaDirty=true;
    if(hasArt){ try{
      if(item.isImage&&item.imgFh) _coverHandles[cid]=item.imgFh;   // 画像=実ファイルハンドルをそのまま（書き出し時に曲フォルダへコピー）
      else { const blob=item._coverBlob||await fetch(item.coverURL).then(r=>r.blob());
        _coverHandles[cid]={name:infoGraph.nodes[cid].data.name,getFile:async()=>blob}; }
      try{ await loadCoverPreview({id:'ig:'+cid,handle:_coverHandles[cid],name:infoGraph.nodes[cid].data.name}); }catch(_){}   // 先にデコードしてからカード更新＝サムネが即表示される
      refreshInfoCards(); }catch(e){} }
    showOk(item.isImage?tf('msg.coverPlaced','「{name}」をカバー画像として配置しました',{name:item.name})
      :hasArt?tf('msg.artworkPlaced','「{name}」のアートワークをカバー画像ノードとして配置しました',{name:item.name})
             :tf('msg.noArtwork','「{name}」にはアートワークがありません（空のカバー画像ノードを配置）',{name:item.name}));
    return;
  }
  infoSnapshot(); _infoSnapSup=true;   // ドロップ=曲情報＋カバー画像の2ノード生成（設定は廃止・ヘルバ様指示）
  const mid=addSrcNode('meta',wx,wy);
  Object.assign(infoGraph.nodes[mid].data,{name:info._songName||item.name||'',sub:info._songSubName||'',
    artist:info._songAuthorName||'',author:info._levelAuthorName||''});
  const cid=addSrcNode('cover',wx,wy+230);
  const hasArt=!!(item._coverBlob||item.coverURL);   // music アイテムの埋め込みアートワーク等（dirハンドル無し）
  if(info._coverImageFilename) infoGraph.nodes[cid].data.name=info._coverImageFilename;
  else if(hasArt) infoGraph.nodes[cid].data.name=(item.name||'artwork')+'.jpg';
  _infoSnapSup=false;   // 抑制はawaitを跨がない（handle取得中のユーザー操作の履歴を飲み込まないため）
  _inSel=new Set([mid,cid]); infoSelApply(); layoutInfoNodes(); metaDirty=true;   // 配置した2枚は選択済み=そのままドラッグでまとめて動かせる
  if(info._coverImageFilename){
    try{ _coverHandles[cid]=await item.dir.getFileHandle(info._coverImageFilename); refreshInfoCards(); }catch(e){} }
  else if(hasArt){   // blob を疑似ハンドル({name,getFile})でカバーノードへ（_coverHandlesはランタイム専用なので安全）
    try{ const blob=item._coverBlob||await fetch(item.coverURL).then(r=>r.blob());
      _coverHandles[cid]={name:infoGraph.nodes[cid].data.name,getFile:async()=>blob}; refreshInfoCards(); }catch(e){} }
  showOk(tf('msg.infoPlaced','「{name}」の情報をノードとして配置しました（書き出しへは未接続）',{name:info._songName||item.name}));
}
{ const insp=document.getElementById('inspcol');
  let ghost=null;
  const worldXY=e=>infoWorldXY(e);   // 座標変換は本家に一本化
  const showGhost=(e)=>{   // ドロップ後のノード3枚配置を中身（曲情報・設定・カバー画像）ごとゴーストで見せる
    if(!ghost){ ghost=document.createElement('div');
      ghost.style.cssText='position:absolute;pointer-events:none;opacity:.62;z-index:60;';
      const info=(_dragMedia&&_dragMedia.info)||{};
      const esc=v=>String(v??'').replace(/&/g,'&amp;').replace(/</g,'&lt;');
      const row=(lb,v)=>v?`<div style="display:flex;gap:8px;color:#c8ccd4;font-size:10px;padding:2px 11px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">
        <span style="color:#8a8a92;flex:0 0 52px;">${lb}</span><span style="overflow:hidden;text-overflow:ellipsis;">${esc(v)}</span></div>`:'';
      const mk=(x,y,w,col,title,body)=>`<div style="position:absolute;left:${x}px;top:${y}px;width:${w}px;
        background:rgba(34,34,36,.92);border:1.6px dashed ${col};border-radius:8px;overflow:hidden;padding-bottom:8px;">
        <div style="background:${col}3c;color:#eee;font-size:10.5px;font-weight:700;padding:7px 11px;margin-bottom:5px;">${title}</div>${body}</div>`;
      const cover=(_dragMedia&&_dragMedia.coverURL)
        ?`<img src="${_dragMedia.coverURL}" style="width:calc(100% - 22px);height:auto;border-radius:6px;margin:0 11px;object-fit:contain;">`:'';
      const coverBody=cover+(info._coverImageFilename?row(TL('gh.file','ファイル'),info._coverImageFilename)
        :(_dragMedia&&_dragMedia.coverURL?row('　',TL('gh.artwork','（アートワーク）')):row('　',TL('gh.noImage','（画像なし）'))));
      ghost.innerHTML=(_dragMedia&&(_dragMedia.isMusic||_dragMedia.isImage))   // 音楽ファイル/画像=カバー画像のみ
        ? mk(0,0,280,INFO_NODE_DEFS.cover[1],TL('node.cover','カバー画像'),coverBody)
        : ( mk(0,0,280,INFO_NODE_DEFS.meta[1],TL('node.meta','曲情報'),   // カスタム曲=曲情報＋カバー画像（設定は廃止・ヘルバ様指示）
             row(TL('f.name','曲名'),info._songName||_dragMedia.name)+row(TL('f.sub','サブ'),info._songSubName)
             +row(TL('f.artist','アーティスト'),info._songAuthorName)+row(TL('f.author','制作者'),info._levelAuthorName))
          +mk(0,230,280,INFO_NODE_DEFS.cover[1],TL('node.cover','カバー画像'),coverBody) );
      document.getElementById('infoWorld').appendChild(ghost); }
    const w=worldXY(e); ghost.style.left=w.x+'px'; ghost.style.top=w.y+'px'; };
  const hideGhost=()=>{ if(ghost){ ghost.remove(); ghost=null; } };
  insp.addEventListener('dragover',e=>{ if(_dragMedia){ e.preventDefault(); e.dataTransfer.dropEffect='copy'; showGhost(e); } });
  insp.addEventListener('dragleave',hideGhost);
  insp.addEventListener('drop',e=>{ if(!_dragMedia) return; e.preventDefault(); hideGhost();
    const item=_dragMedia; _dragMedia=null; const w=worldXY(e);
    dropInfoNodesFromItem(item,w.x,w.y); });
}
// ドラッグ開始時の先読み: 音源をデコードして波形ピークだけ抽出（Musicレーンのゴースト用。バッファは即破棄でメモリ節約）
async function prepareMediaWave(item){
  if(item.isClip||item.isImage) return;   // クリップ/画像は音源なし
  if(item._peaks||item._waveLoading) return; item._waveLoading=1;
  try{
    const fh=await getSongFile(item);
    const buf=await actx.decodeAudioData(await (await fh.getFile()).arrayBuffer());
    item._durSec=buf.duration;
    const ch=buf.getChannelData(0), N=ch.length, BINS=2048, pk=new Float32Array(BINS);
    const step=Math.max(1,(N/BINS)|0);
    for(let i=0;i<BINS;i++){ let m=0; const o=i*step, e2=Math.min(N,o+step);
      for(let j=o;j<e2;j+=4){ const a=Math.abs(ch[j]); if(a>m)m=a; }   // 4サンプル間引きで十分
      pk[i]=m; }
    item._peaks=pk;   // バッファ本体はここでスコープアウト→GC（保持しない）
  }catch(e){ console.warn('MEDIA波形の先読みに失敗',e); }
  item._waveLoading=0;
}
// ドラッグ開始時の先読み: 譜面（Hard優先）をフラグメント化してゴースト表示・ドロップの即配置に使う
async function prepareMediaFrag(item){   // 現在の難易度の譜面だけを先読み（無い曲は_noDiff=？ゴースト）
  if(item.isClip) return;   // クリップは読込済み(_fragは配列生成時にセット済み)
  if(item.isImage){ item._noDiff=1; return; }   // 画像=NLE/Musicレーンには置けない（カバー専用）→ _noDiffゴースト
  const selOpt=document.getElementById('diff').selectedOptions[0];
  const curDn=selOpt?selOpt.textContent:'Hard';
  if(item._fragLoading) return;
  if(item._bmDiff===curDn&&(item._frag||item._noDiff)) return;   // 同じ難易度で読み込み済み
  item._fragLoading=1; item._noDiff=0; item._frag=null;
  try{
    const sets=(item.info&&item.info._difficultyBeatmapSets)||[];
    const std=sets.find(s2=>s2._beatmapCharacteristicName==='Standard')||sets[0];
    const bms=(std&&std._difficultyBeatmaps)||[];
    const bm=bms.find(b2=>b2._difficulty===curDn);
    item._bmDiff=curDn;
    if(!bm){ item._noDiff=1; }
    else { const df=await (await item.dir.getFileHandle(bm._beatmapFilename)).getFile();
      item._frag=parseDiffFragment(JSON.parse(await df.text()));
      item._len=Math.max(4,Math.ceil((item._frag._max+1)/4)*4); }
  }catch(e){ console.warn('MEDIA先読みに失敗',e); }
  item._fragLoading=0;
}
// .dat を編集用フラグメント（Sheetのcontent形式）へ変換
function parseDiffFragment(d){
  const v3='colorNotes' in d||!!String(d.version||'').match(/^[34]/);
  const out={notes:[],bombs:[],walls:[],arcs:[],chains:[],lights:[]}; let mx=0;
  const M=b=>{ b=+b||0; if(b>mx)mx=b; return b; };
  if(v3){
    for(const n of d.colorNotes||[]) out.notes.push({kind:'note',beat:M(n.b),x:n.x,y:n.y,c:n.c,d:n.d,raw:null});
    for(const n of d.bombNotes||[]) out.bombs.push({kind:'bomb',beat:M(n.b),x:n.x,y:n.y,raw:null});
    for(const o of d.obstacles||[]) out.walls.push({kind:'wall',beat:M(o.b),x:o.x,y:o.y,dur:o.d,w:o.w,h:o.h,raw:null});
    for(const a of d.sliders||[]) out.arcs.push({kind:'arc',b:M(a.b),c:a.c,x:a.x,y:a.y,d:a.d,mu:a.mu,tb:M(a.tb),tx:a.tx,ty:a.ty,tc:a.tc,tmu:a.tmu,m:a.m,raw:null});
    for(const c of d.burstSliders||[]) out.chains.push({kind:'chain',b:M(c.b),c:c.c,x:c.x,y:c.y,d:c.d,tb:M(c.tb),tx:c.tx,ty:c.ty,sc:c.sc,s:c.s,raw:null});
    absorbChainCompanionNotes(out.notes, out.chains);   // 実機.datのチェーン頭colorNoteはチェーンへ吸収（幽霊廃止・書き出し時に再合成）
    for(const e of d.basicBeatmapEvents||[]) out.lights.push({beat:M(e.b),et:e.et,i:e.i??0,f:e.f??1,raw:null});
  } else {
    for(const n of d._notes||[]){
      if(n._type===3) out.bombs.push({kind:'bomb',beat:M(n._time),x:n._lineIndex,y:n._lineLayer,raw:null});
      else if(n._type===0||n._type===1) out.notes.push({kind:'note',beat:M(n._time),x:n._lineIndex,y:n._lineLayer,c:n._type,d:n._cutDirection,raw:null}); }
    for(const o of d._obstacles||[]) out.walls.push({kind:'wall',beat:M(o._time),x:o._lineIndex,y:o._type===1?2:0,dur:o._duration,w:o._width,h:o._type===1?3:5,raw:null});
    for(const e of d._events||[]) out.lights.push({beat:M(e._time),et:e._type,i:e._value??0,f:1,raw:null});
  }
  out._max=mx; return out;
}
// MEDIA→NLE: 譜面（ノーツ/ライト）をクリップとして配置。プルダウンにある全難易度ぶんを一括読込
// （現在の難易度=ライブ配置、他の難易度=退避データ(projDiffs)へ同じ位置・同じ色で配置。音源=Musicレーン、曲情報=INFO画面）
// アセットクリップ内容 → 先読みフラグメント（ゴースト/配置用）。_max も算出
function fragFromContent(c){
  c=c||{}; const arrs=['notes','bombs','walls','arcs','chains','lights'];
  const out={}; let mx=0;
  for(const k of arrs){ out[k]=(c[k]||[]).map(o=>({...o}));
    for(const o of out[k]){ const b=(o.beat??o.b??0); if(b>mx)mx=b; const tb=(o.tb??0); if(tb>mx)mx=tb; } }
  out._max=mx; return out;
}
// アセットクリップをNLEへ配置（全レベル共通＝難易度に依存しない。種別レーンへ）
function placeClipLine(item,place){
  const lk=item.clipType==='light'?'l':'n';
  if(place&&place.lk&&place.lk!==lk){ showErr(tf('msg.clipToLane','{tok}クリップは{tok}レーンへドラッグしてください',{tok:lk==='n'?'NOTES':'LIGHT'})); return; }
  const cp=a=>(a||[]).map(o=>({...o})); const c=item.content||{};
  const content=lk==='n'
    ?{notes:cp(c.notes),bombs:cp(c.bombs),walls:cp(c.walls),arcs:cp(c.arcs),chains:cp(c.chains),lights:[]}
    :{notes:[],bombs:[],walls:[],arcs:[],chains:[],lights:cp(c.lights)};
  const cnt=lk==='n'?(content.notes.length+content.bombs.length+content.walls.length+content.arcs.length+content.chains.length):content.lights.length;
  if(!cnt){ showErr('このクリップは空です'); return; }
  snapshot('node'); edgesInited=true;
  const len=Math.max(4,Math.ceil((item._len||8)/4)*4);
  const beat=Math.max(0,place?place.beat:snapV(cur));
  let tr=laneCountOf(lk)-1;   // 一番数字の低いトラック(Notes1/Light1=一番下)から詰める（重なる分だけ上へ・ドロップしたレーンには縛られない）
  while(tr>=0&&laneOverlaps(beat,len,lk,tr)) tr--;
  if(tr<0){ showErr(tf('msg.laneFull','この位置は{grp}レーンが全て埋まっています',{grp:lk==='n'?t('word.notes','ノーツ'):t('word.light','ライト')})); return; }
  const sec={id:'n'+(++_nid)+Math.random().toString(36).slice(2,6),beat,track:tr,lk,col:pickStripCol(),
    label:item.name,len,kind:'sheet',content};
  sections.push(sec); relinkDiffEdges(); layerSel=new Set([sec.id]);
  compileLayersToFlat(); metaDirty=true;
  showOk(tf('msg.assetClipPlaced','アセットクリップ「{name}」を配置しました（{lane}・拍 {beat}）',{name:item.name,lane:laneLabel(lk,tr),beat}));
}
async function addSongLine(item,wx,wy,place){   // place={beat,lk,track}: ドロップ位置。現在の難易度のノーツ/ライトだけ読み込む（他難易度には一切入れない）
  if(item.isClip){ placeClipLine(item,place); return; }
  if(item.isMusic){ showErr('音楽ファイルには譜面がありません（Musicレーンへドラッグすると音源を配置できます）'); return; }
  const info=item.info||{};
  const selOpt=document.getElementById('diff').selectedOptions[0];
  const curDn=selOpt?selOpt.textContent:'';
  const sets=info._difficultyBeatmapSets||[];
  const std=sets.find(s2=>s2._beatmapCharacteristicName==='Standard')||sets[0];
  const bm=((std&&std._difficultyBeatmaps)||[]).find(b2=>b2._difficulty===curDn);
  if(!bm){ showErr(tf('msg.noDiffChart','この曲に {diff} の譜面は含まれていません',{diff:dispDiff(curDn)})); return; }
  let frag;
  try{
    frag=(item._bmDiff===curDn&&item._frag)?item._frag   // dragstart/dragoverの先読みを再利用
      :parseDiffFragment(JSON.parse(await (await item.dir.getFileHandle(bm._beatmapFilename)).getFile().then(f=>f.text())));
  }catch(err){ showErr(tf('msg.chartLoadFail','譜面の読込に失敗: {err}',{err})); return; }
  const lk=(place&&place.lk)==='l'?'l':'n';
  if(lk==='n'){ const k=(curDn+'Standard.dat').toLowerCase();   // ★ノーツ譜面を持ってきた時だけ、その難易度のNJS/オフセットを取得（ライト配置では一切変更しない）
    njsCfg[k]={ njs:(+bm._noteJumpMovementSpeed>0)?+bm._noteJumpMovementSpeed:(_DIFF_NJS[curDn]||16), offset:+bm._noteJumpStartBeatOffset||0 };
    metaDirty=true; if(typeof refreshMusicHdr==='function') refreshMusicHdr(); }
  const cp=a=>(a||[]).map(o=>({...o}));
  const content=lk==='n'
    ?{notes:cp(frag.notes),bombs:cp(frag.bombs),walls:cp(frag.walls),arcs:cp(frag.arcs),chains:cp(frag.chains),lights:[]}
    :{notes:[],bombs:[],walls:[],arcs:[],chains:[],lights:cp(frag.lights)};
  const cnt=lk==='n'?(content.notes.length+content.bombs.length+content.walls.length+content.arcs.length+content.chains.length):content.lights.length;
  if(!cnt){ showErr(tf('msg.chartNoContent','この譜面（{diff}）に{kind}がありません',{diff:dispDiff(curDn),kind:lk==='n'?t('word.notes','ノーツ'):t('word.lighting','ライティング')})); return; }
  snapshot('node');
  edgesInited=true;                                        // 自動直列配線をここからの追加に走らせない
  const len=Math.max(4,Math.ceil((frag._max+1)/4)*4);
  const beat=Math.max(0,place?place.beat:snapV(cur));
  let tr=laneCountOf(lk)-1;   // 一番数字の低いトラック(Notes1/Light1=一番下)から詰める（重なる分だけ上へ・ドロップしたレーンには縛られない）
  while(tr>=0&&laneOverlaps(beat,len,lk,tr)) tr--;
  if(tr<0){ showErr(tf('msg.laneFullNoStack','この位置は{grp}レーンが全て埋まっています（重ねて配置はできません）',{grp:lk==='n'?t('word.notes','ノーツ'):t('word.light','ライト')})); return; }
  const sec={id:'n'+(++_nid)+Math.random().toString(36).slice(2,6),beat,track:tr,lk,col:pickStripCol(),
    label:info._songName||item.name,len,kind:'sheet',content};
  sections.push(sec); relinkDiffEdges(); layerSel=new Set([sec.id]);
  lineSrc.set(sec.id,{dir:item.dir,info,sheetId:sec.id,cur:''});
  compileLayersToFlat(); metaDirty=true;
  showOk(tf('msg.chartPlaced','「{name}」の{kind}を配置しました: {diff}（{lane}・拍 {beat}）',{name:info._songName||item.name,kind:lk==='n'?t('word.notes','ノーツ'):t('word.lighting','ライティング'),diff:dispDiff(curDn),lane:laneLabel(lk,tr),beat}));
}
// 任意のsections配列に対する空きトラック探索（projDiffsの非アクティブ難易度はlaneCountOf/laneOverlapsが使えないため専用実装）
function firstFreeTrackIn(secArr,lk,beat,len,maxTracks){
  for(let tr=0;tr<maxTracks;tr++){
    let ok=true;
    for(const s of secArr){ if(s.lk!==lk||s.track!==tr||s.kind==='null') continue;
      const sb=s.beat||0, se=sb+(s.len||4);
      if(beat<se&&sb<beat+len){ ok=false; break; } }
    if(ok) return tr;
  }
  return -1;
}
// MEDIA右クリック「曲データを読み込む」: 音源/BPM/プレビュー/曲情報&カバー/全難易度のNJS・オフセット・譜面を一括取得。
// 既存の個別取得（addSongLine=現難易度のみ／loadSongFromItem=BPM・プレビューのみ）を統合し「曲を1回持ってくれば全部揃う」を実現（ヘルバ様指定）。
// 曲情報/カバーノードは既存仕様通り書き出しへは未接続のまま生成（手動配線・ヘルバ様指示は維持）。
async function bulkLoadSongData(item){
  if(item.isClip||item.isImage||item.isMusic){ showErr(t('msg.bulkSongBadItem','曲データの読込対象はCustomLevelsの曲のみです')); return; }
  const info=item.info||{};
  try{
    const hasMusic=!!audioBuf&&!songDeleted;    // 既に音源が入っている＝Music(音源・BPM・プレビュー)は上書きせず読み込まない（ヘルバ様指定）
    if(!hasMusic) await loadSongFromItem(item,0);            // 音源・BPM・プレビュー区間（既に音源がある時はスキップ）
    await dropInfoNodesFromItem(item,60,60);    // 曲情報＋カバー画像ノード（未接続）
    const sets=info._difficultyBeatmapSets||[];
    const std=sets.find(s2=>s2._beatmapCharacteristicName==='Standard')||sets[0];
    const bms=(std&&std._difficultyBeatmaps)||[];
    if(!bms.length){ showOk(tf('msg.bulkSongNoChart','「{name}」に譜面が含まれていないため、曲情報のみ取り込みました',{name:info._songName||item.name})); return; }
    snapshot('node');
    let placedDiffs=0, placedClips=0, curTouched=false;
    for(const bm of bms){
      const dnm=bm._difficulty; if(!dnm) continue;
      const key=(dnm+'Standard.dat').toLowerCase();
      njsCfg[key]={ njs:(+bm._noteJumpMovementSpeed>0)?+bm._noteJumpMovementSpeed:(_DIFF_NJS[dnm]||16), offset:+bm._noteJumpStartBeatOffset||0 };
      let frag;
      try{ frag=parseDiffFragment(JSON.parse(await (await item.dir.getFileHandle(bm._beatmapFilename)).getFile().then(f2=>f2.text()))); }
      catch(_){ continue; }   // 譜面ファイル自体が読めなくてもNJS/オフセットは取得済みのまま次の難易度へ
      const cp=a=>(a||[]).map(o=>({...o}));
      const contentN={notes:cp(frag.notes),bombs:cp(frag.bombs),walls:cp(frag.walls),arcs:cp(frag.arcs),chains:cp(frag.chains),lights:[]};
      const contentL={notes:[],bombs:[],walls:[],arcs:[],chains:[],lights:cp(frag.lights)};
      const cntN=contentN.notes.length+contentN.bombs.length+contentN.walls.length+contentN.arcs.length+contentN.chains.length;
      const cntL=contentL.lights.length;
      placedDiffs++;
      if(!cntN&&!cntL) continue;   // 中身が空の譜面はNJS/オフセットのみ取得
      const len=Math.max(4,Math.ceil((frag._max+1)/4)*4);
      const isCur=key===(currentDiffName||'').toLowerCase();
      const target=isCur?sections:(projDiffs[key]=projDiffs[key]||{name:dnm+'Standard.dat',v3:true,base:EMPTY_V3(),notes:[],bombs:[],walls:[],arcs:[],chains:[],lightEvents:[],sections:[]}).sections;
      const mk=(lk,content,cnt)=>{ if(!cnt) return;
        const tr=firstFreeTrackIn(target,lk,0,len,LANE_MAX); if(tr<0) return;
        target.push({id:'n'+(++_nid)+Math.random().toString(36).slice(2,6),beat:0,track:tr,lk,col:pickStripCol(),
          label:info._songName||item.name,len,kind:'sheet',content});
        placedClips++; if(isCur) curTouched=true; };
      mk('n',contentN,cntN); mk('l',contentL,cntL);
    }
    if(curTouched){ relinkDiffEdges(); compileLayersToFlat(); }
    metaDirty=true; if(typeof refreshMusicHdr==='function') refreshMusicHdr();
    showOk(tf('msg.bulkSongLoaded','「{name}」のデータを一括読み込みしました（{n}難易度分・{c}クリップ配置）{skip}',{name:info._songName||item.name,n:placedDiffs,c:placedClips,skip:hasMusic?t('msg.bulkSongMusicKept','　※音源は既存のものを維持'):''}));
  }catch(err){ showErr(tf('msg.bulkSongLoadFail','曲データの一括読込に失敗: {err}',{err})); }
}
document.getElementById('loadBtn').addEventListener('click', async ()=>{
  if(window.showDirectoryPicker){
    try{ dirHandle=await showDirectoryPicker({mode:'readwrite'}); }catch{ return; }
    files={}; handles={};
    for await (const [name,h] of dirHandle.entries()){
      if(h.kind==='file'){ handles[name.toLowerCase()]=h; files[name.toLowerCase()]=await h.getFile(); } }
    await afterFolder();
  } else document.getElementById('folder').click();
});
document.getElementById('folder').addEventListener('change', async e=>{
  files={}; handles={}; dirHandle=null;
  for(const f of e.target.files) files[f.name.toLowerCase()]=f;
  await afterFolder();
});
async function afterFolder(){
  const info=files['info.dat']; if(!info){stat('Info.dat が無い');return;}
  infoText=await info.text();
  infoFileName=(handles['info.dat']&&handles['info.dat'].name)||info.name||'Info.dat';
  const ij=JSON.parse(infoText); BPM=ij._beatsPerMinute||120;
  infoBase=ij; infoJson={...ij}; infoDirty=false; const ipEl=document.getElementById('infoPanel'); ipEl.dataset.built='';
  const sel=document.getElementById('diff'); sel.innerHTML='';
  const sets=ij._difficultyBeatmapSets||[]; const std=sets.find(s=>s._beatmapCharacteristicName==='Standard')||sets[0];
  (std?._difficultyBeatmaps||[]).forEach(d=>{const o=document.createElement('option');o.value=d._beatmapFilename;o.textContent=d._difficulty;sel.appendChild(o);});
  sel.onchange=()=>loadDiff(sel.value);
  const sf=files[(ij._songFilename||'song.egg').toLowerCase()];
  if(sf){ stat('音源読込中'); audioBuf=await actx.decodeAudioData(await sf.arrayBuffer()); songDur=audioBuf.duration;
    buildWaveData(); document.getElementById('tbgTime').style.display=''; }
  // プロジェクト(.nlmf、旧.bslm/.bsnmも可)があれば優先して読込（元の .dat は以後読むだけ）
  let pj=null;
  const projFile=files['project.nlmf']||files['project.bslm']||files['project.bsnm'];   // 新拡張子を優先、旧形式もそのまま読める
  if(projFile){
    try{ const pp=JSON.parse(await projFile.text());
      if(pp&&(pp.format==='nlmf'||pp.format==='bslm'||pp.format==='bsnm')) pj=pp; }
    catch(e){ console.warn('プロジェクト読込失敗',e); } }
  try{ await applyProject(pj); }
  catch(err){ showErr(tf('msg.projApplyErr','プロジェクト適用エラー: {err}',{err:err&&err.stack||err})); }
  document.getElementById('saveBtn').style.display='';
  document.getElementById('saveAsBtn').style.display='';
  document.getElementById('openProjBtn').style.display='';
  document.getElementById('exportBtn').style.display='';
  if(pj) stat('プロジェクトを読み込みました（Ctrl+S=保存 / 書き出し=.dat生成）');
}
// プロジェクトデータの適用（pj=null なら .dat からの新規プロジェクト扱い）
function resetAllState(){   // 新規/開く/最近使った の直前に全状態を初期化＝前ファイルの残留（特にフラット配列と_flatDirty）が新ファイルのクリップへ混入するのを防止（ヘルバ様報告のデータ混在バグ対策）
  if(playing) pause();
  notes=[]; bombs=[]; walls=[]; arcs=[]; chains=[]; lightEvents=[];   // フラット（譜面データ）を必ずクリア
  sections=[];                                                         // クリップ構成もクリア
  projDiffs={}; currentDiffName=''; rawDiff=null;
  markers=[]; _mkSeq=0;
  _flatDirty=false;                                                    // ★未反映の3D編集フラグを消す＝旧フラットが新クリップへ同期されない
  chainCurveGlobal={...CHAIN_CURVE_DEFAULTS};
  // ★音源も必ずクリア＝新規で読み込んだ曲が、その後に開いた別プロジェクトへ残留するバグの対策（ヘルバ様報告）
  graphEdges=graphEdges.filter(e2=>e2.sig!=='audio');
  songNode=null; songDeleted=false; audioBuf=null; ovWave=null; ovWaveLen=0; ovBeats=0; songDur=0; cur=0; offset=0; prevPlayBeat=-1;   // songDeletedも必ずクリア＝前プロジェクトの「MUSIC削除」状態が持ち越されないように（監査 2026-07-14）
  specMag=null; specSrcCanvas=null; specForBuf=null;
  musicSegs=null; musicBeat=0; musicSelSet=new Set();
  selection.clear(); lightSelection.clear(); layerSel=new Set(); gizmoMode=null;
  layerLockS.clear(); layerMuteS.clear(); layerSoloS.clear();          // レーンのロック/ミュート/ソロも持ち越さない
  _cpal=[]; lightBrush.chroma=null; lightBrush._lastChromaHex=null; _lightPalIdx=-1;   // クロマパレット/ブラシは持ち越さない＝新規は空・既定(左ノーツ色)。開くファイルはapplyProjectで上書き（ヘルバ様指定 2026-07-13）
  try{ updateChromaUI(); }catch(_){}
  resetHistory(); _pv4Hist=-1;
}
async function applyProject(pj){
  resetAllState();   // 読み込み前に一旦リセット（残留の混入防止）
  const sel=document.getElementById('diff');
  projDiffs={}; currentDiffName=''; rawDiff=null;
  sections=[]; layerSel=new Set();   // 開く前のボックスを残さない
  if(pj){ const src=pj.difficulties||{}; for(const k2 in src) projDiffs[k2]=decDiff(src[k2]); }   // v2タプル形式をデコード（v1はそのまま通る）
  if(pj&&sel.options.length===0){                      // フォルダ未読込でも.bsnm単体で開ける
    const sets=(pj.info&&pj.info._difficultyBeatmapSets)||[];
    const std=sets.find(x=>x._beatmapCharacteristicName==='Standard')||sets[0];
    (std&&std._difficultyBeatmaps||[]).forEach(d=>{
      const o=document.createElement('option'); o.value=d._beatmapFilename; o.textContent=d._difficulty; sel.appendChild(o); });
    if(!sel.options.length) for(const k in projDiffs){
      const o=document.createElement('option'); o.value=projDiffs[k].name||k; o.textContent=o.value; sel.appendChild(o); }
    sel.style.display='none'; sel.onchange=()=>loadDiff(sel.value);
    if(infoJson==null&&pj.info) infoJson=pj.info;
  }
  if(pj&&pj.current){ const o=[...sel.options].find(o=>o.value.toLowerCase()===pj.current.toLowerCase());
    if(o) sel.value=o.value; }
  if(pj&&pj.info){ infoBase=pj.info; infoJson={...pj.info}; if(+infoBase._beatsPerMinute>0) BPM=+infoBase._beatsPerMinute; }
  if(pj&&+pj.bpm>0) BPM=+pj.bpm;   // 保存時の作業BPMが最優先（INFO未読込のプロジェクトで120に戻るバグの修正）
  tempoParts=(pj&&Array.isArray(pj.tempoParts))?pj.tempoParts.filter(p=>p&&isFinite(p.beat)&&+p.bpm>0).map(p=>({beat:+p.beat,bpm:+p.bpm})):[];
  sortTempoParts();
  graphIO=(pj&&pj.graph&&pj.graph.in&&pj.graph.out)?{in:pj.graph.in,out:pj.graph.out}:null;
  songNode=(pj&&pj.graph&&pj.graph.song)?pj.graph.song:null;
  songDeleted=!!(pj&&pj.songDeleted);   // 「MUSIC削除」状態を復元＝削除済みプロジェクトを再オープンしても空のMUSICノードが自動復活しない（監査 2026-07-14）
  extraNodes=(pj&&pj.graph&&Array.isArray(pj.graph.extra))?pj.graph.extra:[];
  if(songNode&&songNode.handle&&typeof songNode.handle.getFile!=='function') songNode.handle=null;   // JSON化で抜け殻になった参照を無効化
  for(const ex of extraNodes) if(ex.handle&&typeof ex.handle.getFile!=='function') ex.handle=null;
  graphEdges=graphEdges.filter(e2=>!(e2.sig==='info'&&extraNodes.some(x=>x.id===e2.toId)));   // INFO→INFOの残骸を除去
  graphEdges=(pj&&pj.graph&&Array.isArray(pj.graph.edges))?pj.graph.edges:[];
  edgesInited=graphEdges.length>0;                     // 保存済みedgesがあれば初期化不要
  cutSet=new Set((pj&&pj.graph&&pj.graph.cuts)||[]);   // 旧形式はensureEdgesで変換
  altIns=(pj&&pj.graph&&pj.graph.altIns)||[];
  altOuts=(pj&&pj.graph&&pj.graph.altOuts)||[];
  altSongs=(pj&&pj.graph&&pj.graph.altSongs)||[];
  activeUids=(pj&&pj.graph&&pj.graph.activeUids)||{in:null,out:null,song:null};
  musicBeat=(pj&&+pj.musicBeat)||0;
  musicSegs=(pj&&pj.musicSegs)||null; musicSelSet=new Set();   // Cカットのセグメントも復元
  if(pj&&pj.noteRed!=null){ RED=pj.noteRed>>>0; BLUE=pj.noteBlue>>>0; } else { RED=0xff274d; BLUE=0x3092ff; }
  if(pj&&pj.laserRed!=null){ LRED=pj.laserRed>>>0; LBLUE=pj.laserBlue>>>0; } else { LRED=0xff274d; LBLUE=0x3092ff; }
  _cpal=(pj&&Array.isArray(pj.chromaPalette))?pj.chromaPalette.slice(0,48):[];   // クロマパレットはプロジェクトから復元（無ければ空＝新規/旧ファイル）
  try{ lightBrush.chroma=null; lightBrush._lastChromaHex=null; _lightPalIdx=-1; }catch(_){}   // ブラシのクロマ状態もリセット（既定=左ノーツ色へ戻る）
  laserBoostCols(); setNoteColStr(); refreshInfoCards(); applyModeDim();
  await loadDiff(sel.value);
  // セクションタグ: .bsnm > 旧bsnm.meta.json > 既定
  markers=(pj&&Array.isArray(pj.markers))?structuredClone(pj.markers):[]; _mkSeq=markers.length;   // マーカー復元
  njsCfg=(pj&&pj.njsCfg&&typeof pj.njsCfg==='object')?structuredClone(pj.njsCfg):{};   // 難易度別NJS/オフセットの編集値を復元
  if(pj&&pj.chainCurveGlobal&&typeof pj.chainCurveGlobal==='object')
    chainCurveGlobal={...CHAIN_CURVE_DEFAULTS,...pj.chainCurveGlobal};
  else chainCurveGlobal={...CHAIN_CURVE_DEFAULTS};
  notesLanes=Math.max(1,Math.min(LANE_MAX,(pj&&pj.notesLanes)||laneDefN())); lightLanes=Math.max(1,Math.min(LANE_MAX,(pj&&pj.lightLanes)||(6-laneDefN()))); laneScrN=0; laneScrL=0;   // レーン数復元（プロジェクト優先・無ければ個人設定）
  { const ls=(pj&&pj.laneStates)||{};   // レーンのミュート/ソロ/ロック状態を復元（未保存の旧ファイルは全解除のまま）
    layerMuteS=new Set(ls.mute||[]); layerSoloS=new Set(ls.solo||[]); layerLockS=new Set(ls.lock||[]); }
  infoGraph=(pj&&pj.infoGraph)?Object.assign(defaultInfoGraph(),structuredClone(pj.infoGraph)):defaultInfoGraph();
  infoGraph.cam={x:0,y:0,s:1,auto:1};   // 保存済みカメラは使わない（起動時は常に全ノード中央=「.」と同じ状態から）
  sanitizeInfoGraph(); layoutInfoNodes(); applyInfoGraph();   // INFOノード復元（旧形式は移行）→接続ノードを確定情報として反映
  await restoreCoversFromB64(pj);   // 同梱base64からカバー画像を復元（再取得より優先＝確実）。全読込経路(_dbg.apply/recent含む)で有効
  if(!(pj&&+pj.version>=2)){   // v2はsectionsをloadDiffがdifficulties[current]から復元済み（トップレベル重複は廃止）。v1/旧形式のみここでsectionsを組む
    sections=[];
    if(pj&&Array.isArray(pj.sections)) sections=pj.sections.map(s2=>decSec(s2)).sort((a,b)=>a.beat-b.beat);
    else if(files['bsnm.meta.json']){ try{ const meta=JSON.parse(await files['bsnm.meta.json'].text());
      sections=(meta.sections||[]).sort((a,b)=>a.beat-b.beat); }catch(e){} }
    // マーカーが無ければ曲全体をひとつの大きなノードに（1ノードのまま作る派向け）
    if(!sections.length) sections.push({beat:0,label:(infoBase&&infoBase._songName)||'Song'});
    packLanes();   // 旧形式でも一番低いトラックへ詰める
  }
  if(!pj) buildDefaultGraph();                          // 新規（.datフォルダ）は基本構成で配置
  ensureNodeIds(); ensureLens(); ensureEdges();
  // .bsnm再オープン時は sections.content が真実（この時点のフラットは空）。
  // 空フラットのまま sync すると保存内容を消すため、フラット側だけに実データがある場合のみ吸い上げる
  { const hasContent=sections.some(s2=>s2.content&&
      ['notes','bombs','walls','arcs','chains','lights'].some(k=>(s2.content[k]||[]).length));
    if(!hasContent&&(notes.length||bombs.length||walls.length||arcs.length||chains.length||lightEvents.length)) syncGraphFromFlat(); }
  relinkDiffEdges();
  const flatEmpty=!notes.length&&!bombs.length&&!walls.length&&!arcs.length&&!chains.length&&!lightEvents.length;
  if(flatEmpty&&hasActiveClips(sections))
    compileLayersToFlat();
  else { applyInfoChain(); selection.clear(); lightSelection.clear(); gizmoMode=null; rebuild(); }
}
// 音源handleの永続化と自動復元（handleはJSONへ書けない → IndexedDBに退避。これが無いと再オープンで音源が消える）
// window.pywebview はページ読込後に非同期で注入されるため、起動直後の自動読込では
// 注入前に判定してしまう恐れがある→pywebviewready を少し待つ（最大3秒・通常は即解決）
function waitPywebview(ms=3000){
  return new Promise(res=>{
    if(window.pywebview&&window.pywebview.api) return res(true);
    let done=false;
    const on=()=>{ if(done) return; done=true; window.removeEventListener('pywebviewready',on); res(true); };
    window.addEventListener('pywebviewready',on);
    setTimeout(()=>{ if(done) return; done=true; window.removeEventListener('pywebviewready',on); res(!!(window.pywebview&&window.pywebview.api)); },ms);
  });
}
// プロジェクトを開いた直後、songNode.nativePathがあればダイアログ無しでPython経由で自動読込する
// (pywebviewのネイティブダイアログで得た実パスなので、ブラウザの権限確認は一切不要)
async function tryAutoLoadSongNative(){
  if(audioBuf||!songNode||!songNode.nativePath) return;
  await waitPywebview();
  if(!(window.pywebview&&window.pywebview.api&&window.pywebview.api.read_song_file)) return;
  try{
    const j=await window.pywebview.api.read_song_file(songNode.nativePath);
    if(!j||!j.ok) return;
    await applyLoadedSong(b64ToBuf(j.data),j.name);
    showOk(tf('msg.audioRestored','音源を復元しました: {name}',{name:j.name}));
  }catch(e){ console.warn('音源の自動復元に失敗',e); }
}
// プロジェクトを開いた直後、保存済みのネイティブパス（出力フォルダ・カバー画像）へダイアログ無しで自動接続する。
// パスが今は存在しない（移動・削除）場合は何もしない＝従来どおり「再接続」で選び直してもらう。
async function tryAutoRestoreNativeInputs(){
  await waitPywebview(); const api=nativeApi(); if(!api||!infoGraph) return;
  let changed=false;
  for(const oid in (infoGraph.outs||{})){ const o=infoGraph.outs[oid]; if(!o.outDirPath) continue;
    try{ if(await api.fs_isdir(o.outDirPath)){ _outHandles[oid]=mkNativeDir(o.outDirPath); changed=true; } }catch(e){} }
  const act=infoGraph.activeOut, ao=act&&infoGraph.outs[act];
  if(ao&&ao.outDirPath&&_outHandles[act]&&_outHandles[act].nativePath===ao.outDirPath){
    outDirHandle=_outHandles[act];
    if(graphIO&&graphIO.out){ graphIO.out.outDirName=ao.outDirName||outDirHandle.name; graphIO.out.outDirPath=ao.outDirPath; } }
  for(const cid in (infoGraph.nodes||{})){ const n=infoGraph.nodes[cid]; if(n.t!=='cover'||!n.data.nativePath) continue;
    try{ if(await api.fs_isfile(n.data.nativePath)){ const h=mkNativeFile(n.data.nativePath); _coverHandles[cid]=h; changed=true;
        try{ await loadCoverPreview({id:'ig:'+cid,handle:h,name:n.data.name}); }catch(_){} } }catch(e){} }
  if(changed){ applyInfoGraph(); refreshInfoCards(); refreshOutCards(); }
}
// .bsnm を直接開く（曲フォルダ不要。音源だけはSONGノードの📁から）
// .bsnm再オープン時: IndexedDBの元フォルダ参照から 音源・カバー・難易度切替 を復元
async function restoreLineAssets(){
  let m={}; try{ m=(await idbGet('lineDirs'))||{}; }catch(e){}
  const perm=async dh=>{ if(!dh) return false;
    try{ if((await dh.queryPermission({mode:'read'}))==='granted') return true;
      return (await dh.requestPermission({mode:'read'}))==='granted';
    }catch(e){ return false; } };
  const sheetOf=inId=>{ const e2=graphEdges.find(e3=>e3.fromId===inId&&e3.sig==='notes'); return e2?e2.toId:null; };
  // アクティブラインの音源
  const auid=activeUids.song||activeUids.in;
  if(auid&&m[auid]&&songNode&&songNode.name&&!audioBuf&&await perm(m[auid])){
    try{ const fh2=await m[auid].getFileHandle(songNode.name); songNode.handle=fh2;
      const f=await fh2.getFile(); audioBuf=await actx.decodeAudioData(await f.arrayBuffer());
      songDur=audioBuf.duration; buildWaveData();
      document.getElementById('tbgTime').style.display='';
      showOk(tf('msg.audioReconnected','音源を再接続しました: {name}',{name:songNode.name}));
    }catch(e){} }
  // 休止ラインの音源handle
  for(const n of altSongs){ if(n.handle||!n.name||!m[n.uid]) continue;
    if(await perm(m[n.uid])){ try{ n.handle=await m[n.uid].getFileHandle(n.name); }catch(e){} } }
  // カバー画像（名前一致するフォルダを総当たりで再接続）
  for(const ex of extraNodes){ if(ex.kind!=='cover'||ex.handle||!ex.name) continue;
    for(const dh2 of Object.values(m)){
      if(!(await perm(dh2))) continue;
      try{ ex.handle=await dh2.getFileHandle(ex.name); break; }catch(e){}
    } }
  // 難易度切替（lineSrc）の復元
  for(const uid of Object.keys(m)){
    if(lineSrc.has(uid)) continue;
    if(!(await perm(m[uid]))) continue;
    try{
      let ifh=null;
      for(const nm of ['info.dat','Info.dat','INFO.DAT']){ try{ ifh=await m[uid].getFileHandle(nm); break; }catch(e){} }
      if(!ifh) continue;
      const info=JSON.parse(await (await ifh.getFile()).text());
      lineSrc.set(uid,{dir:m[uid],info,
        sheetId:sheetOf(uid===activeUids.in?'in':'in@'+uid),cur:''});
    }catch(e){}
  }
  const src=lineSrc.get(activeUids.in);
  if(src){
    const sec=sections.find(x=>x.id===src.sheetId);
    const dn=sec&&sec._diffName;
    const sets=src.info._difficultyBeatmapSets||[];
    const std=sets.find(s2=>s2._beatmapCharacteristicName==='Standard')||sets[0];
    const bms=(std&&std._difficultyBeatmaps)||[];
    const bm=bms.find(b2=>b2._difficulty===dn)
      ||bms.find(b2=>b2._difficulty==='Hard')||bms[bms.length-1];   // 記録が無い旧保存はHard→最高難度の順
    src.cur=bm?bm._beatmapFilename:'';
    fillDiffSelectFromInfo(src.info,src.cur);
  }
}
async function applyOpenedProject(pj,fh){
  projFileHandle=fh;
  await applyProject(pj);
  await restoreLineAssets();
  await tryAutoLoadSongNative();   // nativePath保存済みならダイアログ無しで音源を自動復元
  try{ await tryAutoRestoreNativeInputs(); }catch(e){ console.warn('出力先/カバーの自動接続に失敗',e); }
  document.getElementById('saveBtn').style.display='';
  document.getElementById('saveAsBtn').style.display='';
  document.getElementById('exportBtn').style.display='';
  if(audioBuf) showOk(tf('msg.projOpened','プロジェクトを開きました: {name}',{name:fh.name}));
  else showOk(tf('msg.projOpenedNoAudio','プロジェクトを開きました: {name}　※音源が未読込です — ファイル→音楽ファイルを読み込む…から開いてください',{name:fh.name}));
}
async function openProjectFile(){
  let fh;
  try{ [fh]=await showOpenFilePicker({types:[{description:'Non-Linear Mapperプロジェクト',accept:{'application/octet-stream':['.nlmf','.bslm','.bsnm']}}]}); }
  catch(e){ return; }
  try{
    const pj=JSON.parse(await (await fh.getFile()).text());
    if(!pj||(pj.format!=='nlmf'&&pj.format!=='bslm'&&pj.format!=='bsnm')){ showErr('⚠ nlmf形式ではありません'); return; }
    _nativeSavePath='';   // ピッカーで開き直したらネイティブ保存先は解除（以後は選んだハンドルへ）
    await applyOpenedProject(pj,fh);
  }catch(err){ showErr(tf('msg.projLoadFail','プロジェクト読込失敗: {err}',{err})); }
}
// exe版: ダブルクリックで渡されたファイル(.nlmf)を起動時に開く。serve.py の /__openarg が中身を返す。
// FileSystemFileHandle は無いので、保存はネイティブパスへ serve.py 経由で書き戻す（_nativeSavePath）。
let _nativeSavePath='', _nativeSaveName='';
let _nativeOpenTried=false;
async function openFromNativeArg(){
  if(_nativeOpenTried) return; _nativeOpenTried=true;   // 二重実行防止（bootReady/loadの両方から呼ばれても1回だけ）
  let info;
  try{ info=await (await fetch('__openarg',{cache:'no-store'})).json(); }catch(e){ return; }
  if(!info||!info.ok||!info.text) return;
  let pj;
  try{ pj=JSON.parse(info.text); }catch(e){ showErr('プロジェクト読込失敗: ファイルが壊れています'); return; }
  if(!pj||(pj.format!=='nlmf'&&pj.format!=='bslm'&&pj.format!=='bsnm')){ showErr('⚠ nlmf形式ではありません'); return; }
  _nativeSavePath=info.path||''; _nativeSaveName=info.name||'project.nlmf'; projFileHandle=null;
  try{ await applyProject(pj); }catch(e){ showErr(tf('msg.projLoadFail','プロジェクト読込失敗: {err}',{err:e})); return; }
  try{ await restoreLineAssets(); }catch(e){}
  try{ await tryAutoLoadSongNative(); }catch(e){}   // nativePath保存済みならダイアログ無しで音源を自動復元
  try{ await tryAutoRestoreNativeInputs(); }catch(e){ console.warn('出力先/カバーの自動接続に失敗',e); }
  document.getElementById('saveBtn').style.display='';
  document.getElementById('saveAsBtn').style.display='';
  document.getElementById('exportBtn').style.display='';
  if(audioBuf) showOk(tf('msg.projOpened','プロジェクトを開きました: {name}',{name:_nativeSaveName}));
  else showOk(tf('msg.projOpenedNoAudio','プロジェクトを開きました: {name}　※音源が未読込です — ファイル→音楽ファイルを読み込む…から開いてください',{name:_nativeSaveName}));
}
// inheritMissingClipsは撤去（箱ごと難易度別・2026-07-05確定）
async function loadDiff(f){ if(!f) return;
  _pv4Hist=-1;                               // 難易度切替後にプレビューを必ず再プッシュ（resetHistoryで履歴0に戻り再プッシュ検知漏れ→消える不具合の対策）
  stashCurrentDiff();                        // 切替前の編集内容をプロジェクトへ退避
  layerSel=new Set(); musicSelSet=new Set();
  const st=projDiffs[f.toLowerCase()];
  if(st){                                    // 編集データがあればそちらを採用
    currentDiffName=st.name||f; rawDiff=st.base; diffV3=!!st.v3;
    notes=st.notes||[]; bombs=st.bombs||[]; walls=st.walls||[]; arcs=st.arcs||[]; chains=st.chains||[]; lightEvents=st.lightEvents||[];
    if(st.sections){
      // 自己修復: 完全重複クリップ（旧ドロップ蓄積バグ）を検出したら除去し、フラットもクリップから作り直す
      const seen=new Set(), uniq=[];
      for(const s2 of st.sections){ const k2=[s2.label,s2.beat||0,s2.track||0,s2.len||4,s2._diffName||'',s2.lk||'n'].join('|');
        if(seen.has(k2)) continue; seen.add(k2); uniq.push(s2); }
      if(uniq.length!==st.sections.length){
        st.sections=uniq;
        const rb={notes:[],bombs:[],walls:[],arcs:[],chains:[],lightEvents:[]};
        for(const s2 of uniq){ if(s2.kind==='null') continue; const c=s2.content||{}, L2=s2.len||4, off=s2.beat||0, trr=s2.track||0;
          (c.notes||[]).forEach(n=>{ if(n.beat<L2) rb.notes.push({...n,beat:n.beat+off,_tr:trr}); });
          (c.bombs||[]).forEach(n=>{ if(n.beat<L2) rb.bombs.push({...n,beat:n.beat+off,_tr:trr}); });
          (c.walls||[]).forEach(o=>{ if(o.beat<L2) rb.walls.push({...o,beat:o.beat+off,_tr:trr}); });
          (c.arcs||[]).forEach(a=>{ if(a.b<L2) rb.arcs.push({...a,b:a.b+off,tb:a.tb+off,_tr:trr}); });
          (c.chains||[]).forEach(c3=>{ if(c3.b<L2) rb.chains.push({...c3,b:c3.b+off,tb:c3.tb+off,_tr:trr}); });
          (c.lights||[]).forEach(ev=>{ if(ev.beat<L2) rb.lightEvents.push({...ev,beat:ev.beat+off,_tr:trr}); }); }
        rb.lightEvents.sort((a,b)=>a.beat-b.beat);
        Object.assign(st,rb);
        notes=st.notes; bombs=st.bombs; walls=st.walls; arcs=st.arcs; chains=st.chains; lightEvents=st.lightEvents;
        console.warn('重複クリップを自己修復:',f);
      }
      if(hasActiveClips(st.sections)){
        // 読み込みは保存時の完全再現（ヘルバ様指示）: packLanes（レーン詰め直し）は行わない＝クリップの配置(track/beat)は保存のまま
        sections=structuredClone(st.sections); relinkDiffEdges();
        // クリップのcontentが正: 先にcontent→フラット合成＝中身は必ず自分のクリップに追従。
        // 旧実装は「packで配置を詰め直し→古い_trのフラットをcontentへ強制flush」の順だったため、
        // 拍範囲の重なる別クリップへ中身が丸ごと移動した（＝ヘルバ様報告「保存したらクリップ間で中身が移動する」の原因）
        const preChains=st.chains||[], preArcs=st.arcs||[];
        compileLayersToFlat();
        // 旧保存形式サルベージ: contentに無くフラットにだけ存在するチェイン/アークを拾ってクリップへ（従来の全量flushの本来の目的）
        const okey=o=>[+(o.b||0).toFixed(4),o.x,o.y,o.c,+(o.tb||0).toFixed(4),o.tx,o.ty].join(',');
        const haveC=new Set(chains.map(okey)), haveA=new Set(arcs.map(okey));
        const orphC=preChains.filter(c=>!haveC.has(okey(c))), orphA=preArcs.filter(a=>!haveA.has(okey(a)));
        if(orphC.length||orphA.length){
          chains.push(...structuredClone(orphC)); arcs.push(...structuredClone(orphA));
          alignNoteGroupTracks([...chains,...arcs]);
          _flatDirty=true; flushFlatEdits(); compileLayersToFlat();
          console.warn('旧形式のフラット残チェイン/アークをクリップへ回収:',orphC.length+orphA.length,'件',f);
        }
      } else if(st.sections) sections=structuredClone(st.sections);   // クリップ無し: フラット直保持（compileで消さない）
    }
    { // 幽霊制度廃止に伴う旧データ変換: チェーンの頭/尾と重なる隠しノーツ（旧仕様が notes に保持していた分）をチェーンへ吸収
      const g=absorbChainCompanionNotes(notes, chains);
      if(g){ if(st.sections&&hasActiveClips(st.sections)){ _flatDirty=true; flushFlatEdits(); }   // クリップにも書き戻し
        console.warn('旧仕様のチェーン随伴ノーツを吸収:',g,'件',f); }
    }
    selection.clear(); rebuild();   // 履歴は消さない＝難易度をまたいで1本で辿れる（各項目のdiffタグで戻り先が分かる・ヘルバ様指定 2026-07-17）
    stat(tf('msg.projStats','[project] BPM {bpm} ・ ノーツ{notes} ボム{bombs} 壁{walls} アーク{arcs} チェーン{chains}',{bpm:BPM,notes:notes.length,bombs:bombs.length,walls:walls.length,arcs:arcs.length,chains:chains.length}));
    return; }
  const fl=files[f.toLowerCase()];
  if(!fl){                                   // 元ファイルも無い＝ゼロから作る新しい難易度（箱は難易度ごとに独立=空のタイムラインから）
    currentDiffName=f; rawDiff=EMPTY_V3(); diffV3=true;
    notes=[];bombs=[];walls=[];arcs=[];chains=[];lightEvents=[];
    resetDiffSections();
    selection.clear(); rebuild(); stashCurrentDiff();   // 履歴は消さない（上と同じ理由）
    stat(tf('msg.newDiffStart','新しい難易度を開始: {name}',{name:f.replace(/Standard\.dat$/,'')}));
    return; }
  const d=JSON.parse(await fl.text());
  currentDiffName=f; rawDiff=d;
  diffV3='colorNotes' in d||!!String(d.version||'').match(/^[34]/);
  notes=[];bombs=[];walls=[];arcs=[];chains=[];lightEvents=[];
  // ライトイベント（レーン表示用）
  if(diffV3){ for(const e of d.basicBeatmapEvents||[]) lightEvents.push({beat:e.b??0,et:e.et,i:e.i??0,f:e.f??1,raw:e}); }
  else { for(const e of d._events||[]) lightEvents.push({beat:e._time,et:e._type,i:e._value??0,f:1,raw:e}); }
  lightEvents.sort((a,b)=>a.beat-b.beat);
  if(diffV3){
    for(const n of d.colorNotes||[]) notes.push({kind:'note',beat:n.b,x:n.x,y:n.y,c:n.c,d:n.d,raw:n});
    for(const n of d.bombNotes||[]) bombs.push({kind:'bomb',beat:n.b,x:n.x,y:n.y,raw:n});
    for(const o of d.obstacles||[]) walls.push({kind:'wall',beat:o.b,x:o.x,y:o.y,dur:o.d,w:o.w,h:o.h,raw:o});
    for(const a of d.sliders||[]) arcs.push({kind:'arc',b:a.b,c:a.c,x:a.x,y:a.y,d:a.d,mu:a.mu,tb:a.tb,tx:a.tx,ty:a.ty,tc:a.tc,tmu:a.tmu,m:a.m,raw:a});
    for(const c of d.burstSliders||[]) chains.push({kind:'chain',b:c.b,c:c.c,x:c.x,y:c.y,d:c.d,tb:c.tb,tx:c.tx,ty:c.ty,sc:c.sc,s:c.s,raw:c});
    absorbChainCompanionNotes(notes, chains);   // 実機.datはチェーン頭のcolorNoteを併記する仕様→エディタではチェーンへ吸収（書き出し時に再合成）
  } else {
    for(const n of d._notes||[]){
      if(n._type===0||n._type===1) notes.push({kind:'note',beat:n._time,x:n._lineIndex,y:n._lineLayer,c:n._type,d:n._cutDirection,raw:n});
      else if(n._type===3) bombs.push({kind:'bomb',beat:n._time,x:n._lineIndex,y:n._lineLayer,raw:n});
    }
    for(const o of d._obstacles||[]) walls.push({kind:'wall',beat:o._time,x:o._lineIndex,
      y:o._type===1?2:0,dur:o._duration,w:o._width,h:o._type===1?1:3,raw:o});
  }
  selection.clear(); rebuild();   // 履歴は消さない（上と同じ理由）。初回の.dat読込＝この難易度の履歴はまだ無い
  stashCurrentDiff();
  stat(tf('msg.chartStats','BPM {bpm} ・ ノーツ{notes} ボム{bombs} 壁{walls} アーク{arcs} チェーン{chains}{v2}',{bpm:BPM,notes:notes.length,bombs:bombs.length,walls:walls.length,arcs:arcs.length,chains:chains.length,v2:diffV3?'':t('word.v2NoArcChain','（v2: アーク/チェーン非対応）')})); }
function stat(s){ document.getElementById('stat').textContent=(typeof s==='string')?t('m:'+s,s):s; }

function buildDiffJsonFor(st){
  const d=structuredClone(st.base);
  const sortB=(p,q)=>(p.b??p._time)-(q.b??q._time);
  const mC=st.chains||[];
  // 幽霊廃止: エディタはチェーン随伴ノーツを保持しない。実機仕様（チェーン頭にはcolorNoteが必要）は
  // 書き出し時にチェーンのデータから頭colorNoteを合成して満たす（尾はBS仕様上ノーツ無し）
  const mN=st.notes||[], mB=st.bombs||[], mW=st.walls||[], mA=st.arcs||[], mL=st.lightEvents||[];
  const chainHeadOut=mC.map(c=>({a:0,b:c.b,x:c.x,y:c.y,c:c.c,d:c.d===8?0:c.d}));
  const stripChainTuning=r=>{ if(!r) return r; const o={...r}; for(const k in CHAIN_RAW_KEYS) delete o[k]; return o; };   // cpm/la/s2d/fcp/csqu/td はエディタ専用値・.dat未出力
  if(st.v3){
    d.colorNotes=[...mN.map(n=>({...(n.raw||{a:0}),b:n.beat,x:n.x,y:n.y,c:n.c,d:n.d})),...chainHeadOut].sort(sortB);
    d.bombNotes=mB.map(n=>({...(n.raw||{}),b:n.beat,x:n.x,y:n.y})).sort(sortB);
    d.obstacles=mW.map(o=>({...(o.raw||{}),b:o.beat,x:o.x,y:o.y,d:o.dur,w:o.w,h:o.h})).sort(sortB);
    d.sliders=mA.map(a=>({...(a.raw||{}),b:a.b,c:a.c,x:a.x,y:a.y,d:a.d,mu:a.mu??1,tb:a.tb,tx:a.tx,ty:a.ty,tc:a.tc??a.d,tmu:a.tmu??1,m:a.m??0})).sort(sortB);
    d.burstSliders=mC.map(c=>({...(stripChainTuning(c.raw)||{}),b:c.b,c:c.c,x:c.x,y:c.y,d:c.d,tb:c.tb,tx:c.tx,ty:c.ty,sc:c.sc??4,s:c.s??1})).sort(sortB);
    d.basicBeatmapEvents=mL.map(e=>({...(e.raw||{}),b:e.beat,et:e.et,i:e.i??0,f:e.f??1})).sort(sortB);
    d.bpmEvents=tempoParts.map(p=>({b:p.beat,m:p.bpm}));   // 曲中のテンポ変更（パート機能）。拍番号はそのまま・以降の絶対時刻だけ変わるBS標準の仕組み
    d.version=d.version||'3.2.0'; delete d._version;              // v3構造 → v3のversionを自動
  } else {
    const ns=mN.map(n=>({...(n.raw||{}),_time:n.beat,_lineIndex:n.x,_lineLayer:n.y,_type:n.c,_cutDirection:n.d}));
    const bs=mB.map(n=>({...(n.raw||{_cutDirection:0}),_time:n.beat,_lineIndex:n.x,_lineLayer:n.y,_type:3}));
    d._notes=[...ns,...bs].sort((p,q)=>p._time-q._time);
    d._obstacles=mW.map(o=>({...(o.raw||{}),_time:o.beat,_lineIndex:o.x,_type:(o.y===2?1:0),_duration:o.dur,_width:o.w})).sort((p,q)=>p._time-q._time);
    d._events=mL.map(e=>({...(e.raw||{}),_time:e.beat,_type:e.et,_value:e.i??0})).sort((p,q)=>p._time-q._time);
    d._version=d._version||'2.0.0'; delete d.version;            // v2構造 → v2のversionを自動
  }
  return d;
}
// ---- 保存フォーマットv2 ----
// アイテムをタプル配列で保存（キー名の反復と raw:null を排除 → v1比で約1/4サイズ）。
// raw は書き出しスプレッドで必要な「標準外フィールド」だけ抽出して保持。v1（オブジェクト形式）もそのまま読める。
const _ENC={
  notes:{k:'note',f:['beat','x','y','c','d']},
  bombs:{k:'bomb',f:['beat','x','y']},
  walls:{k:'wall',f:['beat','x','y','dur','w','h']},
  arcs:{k:'arc',f:['b','c','x','y','d','mu','tb','tx','ty','tc','tmu','m']},
  chains:{k:'chain',f:['b','c','x','y','d','tb','tx','ty','sc','s']},
  lights:{f:['beat','et','i','f']},
};
const _RAWSKIP={
  notes:['b','x','y','c','d','_time','_lineIndex','_lineLayer','_type','_cutDirection'],
  walls:['b','x','y','d','w','h','_time','_lineIndex','_type','_duration','_width'],
  arcs:['b','c','x','y','d','mu','tb','tx','ty','tc','tmu','m'],
  chains:['b','c','x','y','d','tb','tx','ty','sc','s'],
  lights:['b','et','i','f','_time','_type','_value'],
};
_RAWSKIP.bombs=_RAWSKIP.notes;
function _rawX(raw,t){ if(!raw) return null; let o=null;   // rawから標準外フィールド（v3のangle等）だけ抽出
  for(const k2 in raw){ if(_RAWSKIP[t].includes(k2)) continue; o=o||{}; o[k2]=raw[k2]; }
  return o; }
function encArr(arr,t){ const d=_ENC[t];
  return (arr||[]).map(o=>{ const a=d.f.map(k2=>o[k2]??null); a.push(o._tr??null);
    const x=_rawX(o.raw,t); if(x) a.push(x); return a; }); }
function decArr(arr,t){ const d=_ENC[t];
  return (arr||[]).map(o=>{ if(!Array.isArray(o)) return o;   // v1（オブジェクト形式）はそのまま
    const it={}; if(d.k) it.kind=d.k;
    d.f.forEach((k2,i2)=>{ if(o[i2]!=null) it[k2]=o[i2]; });
    if(o[d.f.length]!=null) it._tr=o[d.f.length];
    it.raw=o[d.f.length+1]||null; return it; }); }
const _CKEYS=['notes','bombs','walls','arcs','chains','lights'];
function encSec(s){ const c=s.content||{}, o={};
  for(const k2 of _CKEYS){ if((c[k2]||[]).length) o[k2]=encArr(c[k2],k2); }   // 空配列はキーごと省略
  return {...s,content:o}; }
function decSec(s){ const c=s.content||{}, o={};
  for(const k2 of _CKEYS) o[k2]=decArr(c[k2],k2);
  s.content=o; return s; }
function _slimBase(st){ const b=structuredClone(st.base||{});
  for(const k2 of (st.v3?['colorNotes','bombNotes','obstacles','sliders','burstSliders','basicBeatmapEvents']:['_notes','_obstacles','_events']))
    if(Array.isArray(b[k2])) b[k2]=[];   // 書き出しで全置換される配列は保存不要（MEDIA由来のbase肥大対策）
  return b; }
function encDiff(st){ return {name:st.name,v3:!!st.v3,base:_slimBase(st),
  notes:encArr(st.notes,'notes'),bombs:encArr(st.bombs,'bombs'),walls:encArr(st.walls,'walls'),
  arcs:encArr(st.arcs,'arcs'),chains:encArr(st.chains,'chains'),lightEvents:encArr(st.lightEvents,'lights'),
  sections:(st.sections||[]).map(encSec)}; }
function decDiff(st){ if(!st) return st;
  st.notes=decArr(st.notes,'notes'); st.bombs=decArr(st.bombs,'bombs'); st.walls=decArr(st.walls,'walls');
  st.arcs=decArr(st.arcs,'arcs'); st.chains=decArr(st.chains,'chains'); st.lightEvents=decArr(st.lightEvents,'lights');
  st.sections=(st.sections||[]).map(decSec); return st; }
function buildProjectText(){
  try{ syncGraphFromFlat(); }catch(e){}
  stashCurrentDiff();   // 現難易度のsectionsはdifficulties側に入る（v2はトップレベルsectionsの重複を廃止）
  const diffsOut={}; for(const k2 in projDiffs) diffsOut[k2]=encDiff(projDiffs[k2]);
  const coverData={}; for(const id in _coverB64) if(infoGraph.nodes&&infoGraph.nodes[id]) coverData[id]=_coverB64[id];   // カバー画像をbase64で同梱（存在ノードのみ）
  return JSON.stringify({format:'nlmf',version:2,savedAt:new Date().toISOString(),
    bpm:BPM,tempoParts,current:currentDiffName,musicBeat,musicSegs,songDeleted,noteRed:RED,noteBlue:BLUE,laserRed:LRED,laserBlue:LBLUE,markers,notesLanes,lightLanes,info:infoBase,infoGraph,njsCfg,coverData,chainCurveGlobal,chromaPalette:_cpal,
    laneStates:{mute:[...layerMuteS],solo:[...layerSoloS],lock:[...layerLockS]},   // レーンのミュート/ソロ/ロック状態も保存（ヘルバ様指摘）
    graph:{...(graphIO||{}),edges:graphEdges,
      song:songNode?(({handle,...r})=>r)(songNode):null,
      extra:extraNodes.map(({handle,...r})=>r),
      altIns,altOuts,altSongs:altSongs.map(({handle,...r})=>r),activeUids},difficulties:diffsOut});
}
// バックアップ: 保存直前の内容を3世代ローテーション（bak1=最新〜bak3=最古）。事故時の復旧用
async function rotateBakIdb(name, oldText){ try{
  const g2=await idbGet('projBak2:'+name); if(g2) await idbSet('projBak3:'+name,g2);
  const g1=await idbGet('projBak1:'+name); if(g1) await idbSet('projBak2:'+name,g1);
  await idbSet('projBak1:'+name,{t:Date.now(),text:oldText}); }catch(e){} }
async function rotateBakDisk(dir, baseName, oldText){ try{   // ディレクトリ保存時はファイルと同場所にも3世代（*.bak1/2/3.nlmf）
  const bn=i=>baseName.replace(/\.nlmf$/i,'')+'.bak'+i+'.nlmf';
  for(let i=2;i>=1;i--){ try{ const src=await dir.getFileHandle(bn(i)); const t=await (await src.getFile()).text();
    const w=await (await dir.getFileHandle(bn(i+1),{create:true})).createWritable(); await w.write(t); await w.close(); }catch(_){} }
  const w=await (await dir.getFileHandle(bn(1),{create:true})).createWritable(); await w.write(oldText); await w.close(); }catch(e){} }
// 保存 = project.nlmf（元の .dat は変更しない）。saveAs=true で保存先を選択
async function saveProject(saveAs=false){
  if(!sections.length){ showErr('保存対象がありません'); return; }
  await refreshCoverB64();   // カバー画像をbase64化してから同梱（保存で画像が消えない）
  const text=buildProjectText();
  // exe版でダブルクリック起動したファイルは、同じネイティブパスへ serve.py 経由で書き戻す（上書き保存）。
  // 「名前を付けて保存」時は下のピッカー経路へ（新しい保存先を選ぶ＝ネイティブ解除）。
  if(_nativeSavePath && !saveAs){
    try{
      const r=await fetch('__openarg/save',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text})});
      const j=await r.json();
      if(j&&j.ok){ metaDirty=false; showOk(tf('msg.projSaved','プロジェクト保存: {name}',{name:_nativeSaveName})); }
      else showErr(tf('msg.saveFail','保存失敗: {err}',{err:(j&&j.error)||'?'}));
    }catch(err){ showErr(tf('msg.saveFail','保存失敗: {err}',{err})); }
    return;
  }
  if(saveAs) _nativeSavePath='';   // 名前を付けて保存＝以後は選んだ保存先へ
  if(saveAs||(!projFileHandle&&!dirHandle)){
    try{ projFileHandle=await showSaveFilePicker({suggestedName:'project.nlmf',
      types:[{description:'Non-Linear Mapperプロジェクト',accept:{'application/octet-stream':['.nlmf']}}]}); }
    catch(e){ return; }                       // キャンセル
  }
  try{
    if(projFileHandle){                       // 指定した保存先へ
      await ensureRW(projFileHandle);
      try{ const old=await (await projFileHandle.getFile()).text();   // 上書き前の内容を3世代バックアップ（事故保険）
        if(old) await rotateBakIdb(projFileHandle.name, old); }catch(e){}
      const w=await projFileHandle.createWritable(); await w.write(text); await w.close();
      metaDirty=false;
      showOk(tf('msg.projSaved','プロジェクト保存: {name}',{name:projFileHandle.name}));
    } else {                                  // 既定: 曲フォルダ直下
      await ensureRW(dirHandle);
      const fh=await dirHandle.getFileHandle('project.nlmf',{create:true});
      try{ const old=await (await fh.getFile()).text();   // 同場所に3世代（project.bak1/2/3.nlmf）＋IndexedDBにも3世代
        if(old){ await rotateBakDisk(dirHandle,'project.nlmf',old); await rotateBakIdb(fh.name,old); } }catch(e){}
      const w=await fh.createWritable(); await w.write(text); await w.close();
      metaDirty=false; projFileHandle=projFileHandle||fh;
      showOk('プロジェクト保存: 曲フォルダ/project.nlmf');
    }
  }catch(err){ showErr(tf('msg.saveFail','保存失敗: {err}',{err})); }
}
// 書き出し = Info.dat + 各難易度 .dat を実ファイルとして生成（初回のみ .bsnm.bak バックアップ）
let njsCfg={};   // 難易度キー(小文字 例:hardstandard.dat) → {njs, offset} ユーザー編集値。未設定は元曲(srcNjsOf)→ランク既定へフォールバック
const _DIFF_RANK={Easy:1,Normal:3,Hard:5,Expert:7,ExpertPlus:9};
const _DIFF_NJS={Easy:10,Normal:10,Hard:10,Expert:12,ExpertPlus:16};
function srcInfo(){ for(const [,v] of lineSrc){ if(v&&v.info) return v.info; } return null; }   // 読み込んだ元曲のInfo.dat（セッション保持）
function srcNjsOf(dnm){   // 元曲(info.dat)の該当難易度のNJS/オフセットを保持（読み込んだ曲のlineSrcから）。無ければランク既定
  for(const [,v] of lineSrc){ const info=v&&v.info; if(!info) continue;
    const sets=info._difficultyBeatmapSets||[]; const std=sets.find(x=>x._beatmapCharacteristicName==='Standard')||sets[0];
    const bm=((std&&std._difficultyBeatmaps)||[]).find(b=>b._difficulty===dnm);
    if(bm&&+bm._noteJumpMovementSpeed>0) return {njs:+bm._noteJumpMovementSpeed, offset:+bm._noteJumpStartBeatOffset||0}; }
  return {njs:_DIFF_NJS[dnm]||16, offset:0};
}
// ユーザー編集(njsCfg)があればそれを、無ければ元曲/既定を返す
function njsOffExport(dnm){ const c=njsCfg[(dnm+'Standard.dat').toLowerCase()]||{}; return {njs:c.njs!=null?c.njs:(_DIFF_NJS[dnm]||16), offset:c.offset!=null?c.offset:0}; }   // njsCfg(取得/編集済み)のみ→無ければ既定。lineSrcフォールバックは廃止（全難易度が元曲に化ける問題の解消）
function njsOffCur(){ const dnm=(currentDiffName||'').replace(/Standard\.dat$/i,'').replace(/\.dat$/i,'')||'Hard';
  const c=njsCfg[(currentDiffName||'').toLowerCase()]||{}; return {njs:c.njs!=null?c.njs:(_DIFF_NJS[dnm]||16), offset:c.offset!=null?c.offset:0}; }
function setNjsCur(field,v){ const k=(currentDiffName||'').toLowerCase(); if(!k) return; (njsCfg[k]=njsCfg[k]||{})[field]=v; metaDirty=true;
  if(pv4On&&typeof pv4Push==='function') pv4Push(); }   // 飛来速度/オフセットの変更をプレビューへ即反映
// song.egg変換キャッシュ: 出力先フォルダに小さなマーカーを置き、音源が前回書き出しと同一なら
// 変換/コピーをスキップする（毎回ffmpegを起動しない・毎回でかいファイルを書き直さない）
async function readEggMark(dest){ try{ const fh=await dest.getFileHandle('.nlm-egg.json'); return JSON.parse(await (await fh.getFile()).text()); }catch(e){ return null; } }
async function writeEggMark(dest,mark){ try{ const fh=await dest.getFileHandle('.nlm-egg.json',{create:true}); const w=await fh.createWritable(); await w.write(JSON.stringify(mark)); await w.close(); }catch(e){} }
// 音源をFile相当({name,size,lastModified,arrayBuffer()})で返す。ネイティブ読込(handleなし)の場合は
// pywebview経由でバイトを取得してポリフィルする（ブラウザhandle経由/ネイティブpath経由の両方をexportMapへ透過）
async function getSongFileLike(){
  const songH=songNode&&songNode.handle;
  if(songH&&typeof songH.getFile==='function'){ try{ return await songH.getFile(); }catch(e){ return null; } }
  if(songNode&&songNode.nativePath&&window.pywebview&&window.pywebview.api&&window.pywebview.api.read_song_file){
    try{
      const j=await window.pywebview.api.read_song_file(songNode.nativePath);
      if(!j||!j.ok) return null;
      const buf=b64ToBuf(j.data);
      return {name:j.name,size:buf.byteLength,lastModified:(j.mtime||0)*1000,arrayBuffer:async()=>buf};
    }catch(e){ return null; }
  }
  return null;
}
async function exportMap(forceEgg=false){
  if(!currentDiffName){ stat('書き出し対象がありません'); return; }
  stashCurrentDiff();
  applyInfoGraph();   // 接続ノード(曲情報/設定/カバー)の確定情報をinfoBaseへ＋カバーhandleをextraNodesへミラー＋applyInfoChainでinfoJson更新
  // --- 書き出す難易度を確定（中身のある Standard 難易度・OUT_DIFFS順） ---
  const cutB=msegs().reduce((m,sg)=>Math.max(m,segEndBeat(sg)),0);   // Music終端で長さ固定
  const clip=arr=>cutB>0?(arr||[]).filter(o=>o.beat<=cutB+1e-6):(arr||[]);
  const diffFiles=[];
  for(const dnm of OUT_DIFFS){
    const st=projDiffs[(dnm+'Standard.dat').toLowerCase()]; if(!st) continue;
    if(!(st.notes||[]).length&&!(st.lightEvents||[]).length&&!(st.bombs||[]).length&&!(st.walls||[]).length
      &&!(st.arcs||[]).length&&!(st.chains||[]).length) continue;   // 空は出さない
    const stX=cutB>0?{...st, notes:clip(st.notes),bombs:clip(st.bombs),walls:clip(st.walls),
      arcs:(st.arcs||[]).filter(a=>a.b<=cutB+1e-6),chains:(st.chains||[]).filter(c2=>c2.b<=cutB+1e-6),lightEvents:clip(st.lightEvents)}:st;
    diffFiles.push({dnm, name:dnm+'Standard.dat', text:JSON.stringify(buildDiffJsonFor(stX))});
  }
  if(!diffFiles.length){ showErr(t('m:書き出せる難易度がありません（ノーツ/ライトが空です）','書き出せる難易度がありません（ノーツ/ライトが空です）')); return; }
  // --- 出力先: outDirHandle(選んだCustomLevels) 内に「出力フォルダ名」サブフォルダを作成。無ければ従来のdirHandle/ダウンロード ---
  const folderName=((graphIO&&graphIO.out&&graphIO.out.folderName)||'').trim();
  let dest=null, destLabel='';
  if(outDirHandle&&folderName){
    try{ dest=await outDirHandle.getDirectoryHandle(folderName,{create:true}); destLabel=folderName; }
    catch(err){ showErr(tf('msg.exportFail','書き出し失敗: {err}',{err})); return; }
  } else if(dirHandle){ dest=dirHandle; destLabel=dirHandle.name||''; }
  // --- カバー画像 → cover.<ext> ---
  let coverName='';
  const covN=extraNodes.find(n=>n.kind==='cover'&&graphEdges.some(e=>e.sig==='cover'&&e.fromId===n.id&&e.toId==='out'));
  if(covN&&covN.handle&&dest){
    try{ const f=await covN.handle.getFile();
      coverName='cover.'+((f.name.match(/\.([^.]+)$/)||[,'png'])[1].toLowerCase());
      const ch=await dest.getFileHandle(coverName,{create:true}); const cw=await ch.createWritable();
      await cw.write(await f.arrayBuffer()); await cw.close();
    }catch(err){ showErr(tf('msg.coverCopyFail','カバー画像のコピーに失敗: {err}',{err})); coverName=''; }
  }
  // --- song.egg（元がOGGならバイトコピー。それ以外はffmpeg経由でOGG Vorbisへ変換） ---
  // 未変更ならスキップ（forceEggで強制再変換=初期化）。
  // 音源はFileSystemFileHandle(ブラウザピッカー経由)かnativePath(pywebviewネイティブ読込経由)のどちらか。
  let eggWritten=false, eggWarn='';
  const songF=await getSongFileLike();
  if(dest){
    if(songF){
      try{
        const f=songF;
        const leadInMs=getLeadInMs();
        const mark={name:f.name,size:f.size,mtime:f.lastModified,leadInMs};
        let eggExists=true; try{ await dest.getFileHandle('song.egg'); }catch(_){ eggExists=false; }
        const prev=(!forceEgg&&eggExists)?await readEggMark(dest):null;
        if(prev&&prev.name===mark.name&&prev.size===mark.size&&prev.mtime===mark.mtime&&(prev.leadInMs||0)===leadInMs){
          eggWritten=true;   // 音源・無音追加設定が前回と同一＝再変換不要
        } else {
          const buf=await f.arrayBuffer();
          const u=new Uint8Array(buf.slice(0,4)), isOgg=(u[0]===0x4F&&u[1]===0x67&&u[2]===0x67&&u[3]===0x53);   // "OggS"
          let outBuf=buf;
          if(!isOgg||leadInMs>0){   // 無音追加が設定されていれば、元がOGGでも必ずffmpegで焼き込む
            stat(t('m:song.eggへ変換中…（ffmpeg）','song.eggへ変換中…（ffmpeg）'));
            const ext=(f.name.match(/\.([^.]+)$/)||[,'bin'])[1].toLowerCase();
            let qs='ext='+encodeURIComponent(ext); if(leadInMs>0) qs+='&leadInMs='+leadInMs;
            let r; try{ r=await fetch('__convert/toOgg?'+qs,{method:'POST',body:buf}); }catch(e){ r=null; }
            if(r&&r.ok&&(r.headers.get('content-type')||'').includes('audio')){
              outBuf=await r.arrayBuffer();
            } else {
              let em='conv-failed'; try{ const j=await r.json(); if(j&&j.error) em=j.error; }catch(_){}
              outBuf=null;
              eggWarn=' '+(em==='ffmpeg-not-found'
                ? t('m:※ffmpegが見つかりません。"winget install ffmpeg" でインストール後に再度書き出してください','※ffmpegが見つかりません。"winget install ffmpeg" でインストール後に再度書き出してください')
                : tf('msg.eggConvFail','※song.egg変換に失敗: {err}',{err:em}));
            }
          }
          if(outBuf){
            const eh=await dest.getFileHandle('song.egg',{create:true}); const ew=await eh.createWritable();
            await ew.write(outBuf); await ew.close(); eggWritten=true;
            await writeEggMark(dest,mark);
          }
        }
      }catch(err){ eggWarn=' '+tf('msg.eggFail','※song.egg書き込み失敗: {err}',{err}); }
    } else eggWarn=' '+t('m:※音源のファイル参照が無くsong.eggを書けません（曲を読み込み直してください）','※音源のファイル参照が無くsong.eggを書けません（曲を読み込み直してください）');
  }
  // --- Info.dat をビルド（完全版・Beat Saber v2 Info） ---
  const b=infoJson||infoBase||{}, numv=(v,d)=>Number.isFinite(+v)?+v:d;
  const info={ _version:'2.1.0',
    _songName:b._songName||'', _songSubName:b._songSubName||'', _songAuthorName:b._songAuthorName||'', _levelAuthorName:b._levelAuthorName||'',
    _beatsPerMinute:BPM, _songTimeOffset:numv(b._songTimeOffset,0), _shuffle:numv(b._shuffle,0), _shufflePeriod:numv(b._shufflePeriod,0.5),
    _previewStartTime:numv(b._previewStartTime,12), _previewDuration:numv(b._previewDuration,10),
    _songFilename:'song.egg', _coverImageFilename:coverName||b._coverImageFilename||'',
    _environmentName:b._environmentName||(srcInfo()||{})._environmentName||'DefaultEnvironment', _allDirectionsEnvironmentName:b._allDirectionsEnvironmentName||(srcInfo()||{})._allDirectionsEnvironmentName||'GlassDesertEnvironment',
    _difficultyBeatmapSets:[{ _beatmapCharacteristicName:'Standard',
      _difficultyBeatmaps:diffFiles.map(d=>{ const nj=njsOffExport(d.dnm); return { _difficulty:d.dnm, _difficultyRank:_DIFF_RANK[d.dnm], _beatmapFilename:d.name,
        _noteJumpMovementSpeed:nj.njs, _noteJumpStartBeatOffset:nj.offset }; }) }] };
  const files2=[['Info.dat',JSON.stringify(info,null,2)], ...diffFiles.map(d=>[d.name,d.text])];
  // --- 書き込み ---
  if(dest){
    try{
      for(const [name,text] of files2){ const fh=await dest.getFileHandle(name,{create:true});
        const w=await fh.createWritable(); await w.write(text); await w.close(); }
      const listed=['Info.dat',...diffFiles.map(d=>d.name),coverName,eggWritten&&'song.egg'].filter(Boolean).join(' / ');
      showOk(tf('msg.exportedFolder','書き出しました: 「{folder}」に {list}{warn}',{folder:destLabel,list:listed,warn:eggWarn}));
    }catch(err){ showErr(tf('msg.exportFail','書き出し失敗: {err}',{err})); }
  } else {   // フォルダ未選択: 従来どおりダウンロード（Info.dat＋難易度のみ・song.egg等は不可）
    for(const [name,text] of files2){ const a=document.createElement('a');
      a.href=URL.createObjectURL(new Blob([text],{type:'application/json'})); a.download=name; a.click(); URL.revokeObjectURL(a.href); }
    stat('ダウンロードとして書き出しました（出力フォルダ未選択のため）');
  }
}
document.getElementById('saveBtn').addEventListener('click',()=>saveProject(false));
document.getElementById('saveAsBtn').addEventListener('click',()=>saveProject(true));
document.getElementById('openProjBtn').addEventListener('click',openProjectFile);
document.getElementById('exportBtn').addEventListener('click',exportMap);

// ---- picking ----
const raycaster=new THREE.Raycaster(), pointer=new THREE.Vector2();
raycaster.params.Line={threshold:0.03};   // 輪郭線の当たり判定が広すぎるのを防ぐ（既定値1は広大）
raycaster.layers.enableAll();             // ヘルパ(レイヤー1)もクリック判定の対象にする
function setPtr(e){ const r=cv.getBoundingClientRect(); pointer.x=((e.clientX-r.left)/r.width)*2-1; pointer.y=-((e.clientY-r.top)/r.height)*2+1;
  raycaster.setFromCamera(pointer,camera); }
function objUnder(e){ if(lightMode) return null;
  // ノーツとライトはワールド座標上で重なっているため、モードで拾う対象を必ず分ける（2026-07-18の表示改修）。
  if(e) setPtr(e); else raycaster.setFromCamera(pointer,camera);   // eなし=直近のマウス位置(pointer)でレイキャスト（Fキー等・イベント非依存）
  const hits=raycaster.intersectObjects(meshes.filter(m=>m.group.visible&&!objLockedN(m.obj)).map(m=>m.group),true);   // ロック中レーンは触れない
  // 壁は大きくて他を覆うので、壁以外(ノーツ等)を優先。壁しか無ければ壁を返す
  let wallHit=null, wallDist=1e9;
  for(const h of hits){ let o=h.object; while(o&&!o.userData.obj)o=o.parent;
    const obj=o&&o.userData.obj; if(!obj) continue;
    if(obj.kind==='wall'){ if(!wallHit){ wallHit=obj; wallDist=h.distance; } continue; }
    return obj; }
  if(wallHit){ // 床の方が手前なら「空クリック」扱い（壁の下の床を選んでも壁を拾わない）
    if(raycaster.ray.intersectPlane(floorPlane,_fv)){
      const fd=_fv.distanceTo(raycaster.ray.origin);
      if(fd<wallDist-0.05) return null; } }
  return wallHit; }

// ---- 編集モード（Eトグル・拍ロック・ゴースト） ----
let hoverBeat=null;
let placeMode=false, ghostCell=null, ghostKey='', lockBeat=0;
const floorPlane=new THREE.Plane(new THREE.Vector3(0,1,0),0);
const _fv=new THREE.Vector3();
const _noteGP=new THREE.Plane(new THREE.Vector3(0,0,1),0);   // ノーツ配置グリッド面(z=0・垂直)＝ゴーストの自由追従用の交差面（ヘルバ様指定 2026-07-14）
const _gv=new THREE.Vector3();
const ghost=new THREE.Group(); ghost.visible=false; editGroup.add(ghost);
// ゴースト用の共有マテリアル（毎回cloneせず使い回す）
const ghostNoteMats=[mat(0).clone(),mat(1).clone()];
ghostNoteMats.forEach(m=>{ m.transparent=true; m.opacity=0.42; });   // 配置前ゴースト=フィル＋ワイヤーフレームで「未配置」と分かるように（薄すぎ修正 2026-07-14: 0.18→0.42）
const ghostEdgeGeo=new THREE.EdgesGeometry(noteGeo);
const ghostEdgeMat=new THREE.LineBasicMaterial({color:0x9fe8ff,transparent:true,opacity:0.95});
const ghostArrowMat=new THREE.MeshBasicMaterial({map:arrowTex,transparent:true,opacity:0.85});
const ghostDotMat=new THREE.MeshBasicMaterial({map:dotTex,transparent:true,opacity:0.85});
const ghostBombMat=new THREE.MeshBasicMaterial({color:0x333344,transparent:true,opacity:0.72});
function refreshGhost(){ const key=brush.type+'_'+brush.c+'_'+brush.d; if(key===ghostKey) return; ghostKey=key;
  while(ghost.children.length) ghost.remove(ghost.children[0]);
  // 配置済みノーツ(buildNote)と同じ1/4厚の板にする＝ゴーストだけ分厚くて見た目が食い違うのを解消（ヘルバ様指定 2026-07-17）。
  // ボムは実物も薄くしないので等倍のまま。矢印/ドットもgroupの子なので一緒に潰れる（buildNoteと同じ振る舞い）
  ghost.scale.z=(brush.type==='note')?NOTE_THIN:1;
  if(brush.type==='note'){
    const box=new THREE.Mesh(noteGeo,ghostNoteMats[brush.c===0?0:1]);
    if(brush.d>=4&&brush.d<=7) box.rotation.z=-Math.PI/4;   // buildNoteと同符号（レーン軸反転の鏡映）＝ゴーストと実配置の向き一致（ヘルバ様報告）
    ghost.add(box);
    const wf=new THREE.LineSegments(ghostEdgeGeo,ghostEdgeMat);   // ワイヤーフレーム＝未配置ゴースト表示
    if(brush.d>=4&&brush.d<=7) wf.rotation.z=-Math.PI/4; ghost.add(wf);
    const gm=(brush.d===8?ghostDotMat:ghostArrowMat);
    const deg=(brush.d===8)?0:(DIR_ANGLE[brush.d]??0);   // 矢印角。attachNoteArrowMarksと同じ符号: 前面=-deg / 背面=+deg
    const mk=new THREE.Mesh(markGeo,gm); mk.position.z=-0.235;
    mk.rotation.set(0,Math.PI,-THREE.MathUtils.degToRad(deg)); ghost.add(mk);
    const mkb=new THREE.Mesh(markGeo,gm); mkb.position.z=0.235;
    mkb.rotation.set(0,0,THREE.MathUtils.degToRad(deg)); ghost.add(mkb);
  } else if(brush.type==='bomb'){
    ghost.add(new THREE.Mesh(bombGeo,ghostBombMat));
  }
  // 壁は wallGhost（床ドラッグ）を使うのでここでは作らない
}

// ---- 壁: グリッドで起点（列・段）→ドラッグで断面、グリッド外に引いて長さ ----
const wallGhost=new THREE.Mesh(new THREE.BoxGeometry(1,1,1),
  new THREE.MeshBasicMaterial({color:0xd03060,transparent:true,opacity:0.30,depthWrite:false}));
wallGhost.visible=false; noteRoot.add(wallGhost); tagHelper(wallGhost);
let wallDrag=null;        // {x0,y0} ドラッグ開始マス
let wallHoverCell=null;   // {x,y}  現在ホバー中のマス
let wallDurLive=1;        // 作成中の長さ（拍）
let wallStage=null;       // 配置モードの段階式壁: {wall,stage:'height'|'depth'} マウス追従で仮配置を調整中
const WALL_MIN_DUR=+(LANE/ZPB).toFixed(4);   // 奥行きの最小=1ボックス分（見た目でノーツ1マスと同じ深さ・ヘルバ様指定）
const _zNormal=new THREE.Vector3(0,0,1);     // 高さ調整用の縦平面（壁の深さに置く）法線
const _wallHPlane=new THREE.Plane(_zNormal,0);
// 段階式壁で「今どの軸を広げられるか」を示すゴースト矢印（ギズモとは別: 黄・四角錐・両矢印・常時前面）
const _up=new THREE.Vector3(0,1,0);
const wallDimArrows=new THREE.Group(); wallDimArrows.visible=false; noteRoot.add(wallDimArrows);
const _dimAxes={x:[],y:[],z:[]};
function makeDimArrow(){
  const m=new THREE.MeshBasicMaterial({color:0xffcc22,transparent:true,opacity:0.95,depthTest:false});
  const g=new THREE.Group();
  const shaft=new THREE.Mesh(new THREE.CylinderGeometry(0.028,0.028,0.20,6),m); shaft.position.y=0.10; g.add(shaft);
  const cone=new THREE.Mesh(new THREE.ConeGeometry(0.12,0.24,4),m); cone.position.y=0.30; g.add(cone);   // 四角錐=ギズモ(10角錐)と別形状
  g.traverse(c=>{ c.renderOrder=999; });
  return g;
}
for(const ax of ['x','y','z']){ for(const s of [1,-1]){ const a=makeDimArrow(); wallDimArrows.add(a); _dimAxes[ax].push({node:a,sign:s}); } }
wallDimArrows.traverse(c=>tagHelper(c));
function updateWallDimArrows(){
  if(!wallStage){ wallDimArrows.visible=false; return; }
  const w=wallStage.wall, m=meshes.find(mm=>mm.obj===w);
  if(!m){ wallDimArrows.visible=false; return; }
  const {hh,cx,cy,len}=wallDims(w), gz=m.group.position.z;
  wallDimArrows.position.set(cx,cy,gz+len/2);
  const half={x:w.w*LANE/2, y:hh*LAYER/2, z:len/2};
  const active=wallStage.stage==='width'?'x':wallStage.stage==='height'?'y':'z';
  for(const ax of ['x','y','z']){ const on=ax===active;
    for(const it of _dimAxes[ax]){ it.node.visible=on;
      if(on){ const dir=new THREE.Vector3(ax==='x'?it.sign:0, ax==='y'?it.sign:0, ax==='z'?it.sign:0);
        it.node.position.copy(dir.clone().multiplyScalar(half[ax]+0.10));
        it.node.quaternion.setFromUnitVectors(_up,dir); } } }
  wallDimArrows.visible=true;
}
function floorColBeat(){ if(!raycaster.ray.intersectPlane(floorPlane,_fv)) return null;
  const col=Math.max(0,Math.min(3,Math.floor(2-(_fv.x-NOTE_DX)/LANE)));   // レーン軸反転の逆変換（NOTE_DXを外してから）
  const beat=Math.max(0,snapV(viewBeat()+_fv.z/ZPB));
  return {col,beat}; }
function wallSpan(){
  const a=wallDrag, b=wallHoverCell||wallDrag;
  return { x0:Math.min(a.x0,b.x), x1:Math.max(a.x0,b.x),
           y0:Math.min(a.y0,b.y), y1:Math.max(a.y0,b.y) };
}
function updateWallGhost(){
  if(!placeMode||brush.type!=='wall'){ wallGhost.visible=false; return; }
  let x0,x1,y0,y1,len;
  if(wallDrag){ const s=wallSpan(); x0=s.x0;x1=s.x1;y0=s.y0;y1=s.y1; len=Math.max(snap,wallDurLive)*ZPB; }
  else if(wallHoverCell){ x0=x1=wallHoverCell.x; y0=y1=wallHoverCell.y; len=WALL_MIN_DUR*ZPB; }   // 配置前の仮ゴーストは最小(1ボックス)・ヘルバ様指定
  else { wallGhost.visible=false; return; }
  const w=(x1-x0+1), rows=(y1-y0+1);
  wallGhost.scale.set(w*LANE-0.04, rows*LAYER-0.04, len);
  wallGhost.position.set((1.5-(x0+x1)/2)*LANE+NOTE_DX, BASE_Y+y0*LAYER+(rows-1)*LAYER/2, (lockBeat-viewBeat())*ZPB+len/2);
  wallGhost.visible=true;
}
function selWalls(){ return [...selection].filter(o=>o.kind==='wall'); }
// 編集モードの入退室を一元化（E / 右クリック / Esc で終了）
function setPlaceMode(on,keepCam){
  if(placeMode===on) return;
  placeMode=on;
  if(on){ selection.clear(); gizmoMode=null;          // 編集モードに入ったら選択は解除
    lockBeat=snapV(hoverBeat??cur);
    // 回転中心をロック拍の深さへ移す。視線上に置くのでカメラ位置は変わらないが、注視点までの距離は変わる＝
    // 奥行き方向を向いた視点だと注視点が大きく飛び「カメラが動いた」ように見える。
    // keepCam=true（LIGHTING⇄NOTES切替での配置ツール復元など、ユーザーが視点変更を意図していない場面）では行わない（ヘルバ様報告 2026-07-18）
    if(!keepCam){
      const lockZ=(lockBeat-viewBeat())*ZPB;
      const dir=controls.target.clone().sub(camera.position);
      if(Math.abs(dir.z)>1e-4){ const t=(lockZ-camera.position.z)/dir.z;
        if(t>0.05){ controls.target.copy(camera.position).addScaledVector(dir,t); controls.update(); } } } }
  else { if(wallStage) cancelWallStage(); ghost.visible=false; ghostCell=null; wallHoverCell=null; wallGhost.visible=false; wallDrag=null; }
  refreshHoverVisuals();
  if(typeof updateModeButtons==='function') updateModeButtons();   // 配置/セレクト切替をツールバーへ反映
  stat(on?tf('msg.editModeOn','編集モード ON（拍 {beat} にロック）',{beat:lockBeat}):'編集モード OFF');
}

// 現在のレイ位置に基づいてゴースト/壁ゴーストを更新（キー切替時にも呼べる）
function refreshHoverVisuals(){
  if(!placeMode){ ghost.visible=false; ghostCell=null; wallHoverCell=null; wallGhost.visible=false; return; }
  if(brush.type==='wall'){
    ghost.visible=false; ghostCell=null;
    const cHit=raycaster.intersectObjects(cellPlanes)[0];
    if(cHit){ wallHoverCell=cHit.object.userData; }
    else if(!wallDrag) wallHoverCell=null;
    // ドラッグ中にグリッド外へ引いたら床の拍で長さを伸ばす
    if(wallDrag&&!cHit){ const p=floorColBeat(); if(p) wallDurLive=Math.max(snap,p.beat-lockBeat); }
    updateWallGhost();
  } else {
    wallHoverCell=null; wallGhost.visible=false;
    refreshGhost();
    // ライトと同様にゴーストが自由追従＝最寄りの4×3セルへスナップし、どこにでも配置可（旧: cellPlanesの直上のみ・黄色枠は廃止。ヘルバ様指定 2026-07-14）
    // 交差面はグリッドの実z（editGroup）に合わせる。_noteGPはワールドz=0固定なので、
    // 配置モード（lockBeat=viewBeat＝z0）では一致するが、編集モードではロック拍とズレる（ヘルバ様報告 2026-07-17）
    _noteGP.constant=-editGroup.position.z;
    if(raycaster.ray.intersectPlane(_noteGP,_gv)){
      const fx=1.5-(_gv.x-NOTE_DX)/LANE, fy=(_gv.y-BASE_Y)/LAYER;   // NOTE_DXを外してから列番号へ
      // 配置モード=最寄りセルへスナップ（拍は赤ライン固定なのでどこでも置ける）。
      // 編集モード=グリッドの枠内にいる時だけ掴む＝枠外では ghostCell=null になり、拍がマウスに追従できる（下のlockBeat追従）
      const inGrid=(fx>=-0.5&&fx<=3.5&&fy>=-0.5&&fy<=2.5);
      if(camMode==='place'||inGrid){
        const cx=Math.max(0,Math.min(3,Math.round(fx)));
        const cy=Math.max(0,Math.min(2,Math.round(fy)));
        ghostCell={x:cx,y:cy};
        const [px,py]=cellPos(cx,cy); ghost.position.set(px,py,-0.001);
        // 既存ノーツ/ボム/壁の上では消す＝そこをクリックすると「選択」になるので、置けるように見せると誤解のもと
        // （ライト側 lightGhost の「既存イベントの上では消す」と同じ流儀・ヘルバ様報告 2026-07-17）
        ghost.visible=!objUnder();
      } else { ghost.visible=false; ghostCell=null; }
    } else { ghost.visible=false; ghostCell=null; }
  }
}
cv.addEventListener('pointermove', e=>{
  if(box||orbitDrag) return;                 // 回転中はホバー更新を止める（黄ラインが暴れないように）
  // 別アプリ切替等でpointerupを取りこぼすとドラッグ状態が残留し、戻った後マウスを動かすだけで
  // オブジェクトが勝手に動く（ヘルバ様報告）。ボタンが押されていなければ残留ドラッグを終了する保険
  if(!(e.buttons&1)&&(scrubDrag||handleDrag||chainGizmoDrag||chainDrag)){ cancelTransientDrags(); return; }
  setPtr(e);
  if(wallStage){ applyWallStage(); return; }   // 段階式壁: マウス追従で高さ/奥行きを更新
  if(scrubDrag){ // 再生ヘッド: 固定ビュー上でマウス直下の拍へ（NLEルーラーと同じ絶対シーク。基準vwBは不変＝ズレも暴走もしない）
    if(raycaster.ray.intersectPlane(floorPlane,_fv)){
      cur=Math.max(0,snapV(viewBeat()+_fv.z/ZPB)); offset=beatToTimeTM(cur); }
    return; }
  if(handleDrag){ applyHandleDrag(); return; }
  if(chainGizmoDrag){ applyChainGizmoDrag(); return; }
  if(chainDrag){ applyChainDrag(e); return; }
  refreshHoverVisuals();
  refreshLightHover();
  if(lightMove){ applyLightMove(); return; }
  if(placeMode&&(ghostCell||wallHoverCell)) return;   // マス上ではロック維持（壁ブラシは ghostCell を使わず wallHoverCell が立つ）
  if(raycaster.ray.intersectPlane(floorPlane,_fv)){
    const b=snapV(viewBeat()+_fv.z/ZPB);
    hoverBeat=Math.max(0,Math.min(cur+20,Math.max(cur-20,b)));   // 有効範囲=描画範囲と同じ「ヘッド±20拍」（アンカー基準の旧クランプが右側不追従の原因だった）
  }
});
cv.addEventListener('mouseleave', ()=>{ hoverBeat=null; ghost.visible=false; ghostCell=null; lightHover=null; lightGhost.visible=false;
  if(!wallDrag){ wallHoverCell=null; wallGhost.visible=false; } });
// 別アプリ切替（ウィンドウblur/タブ非表示/pointercancel）で進行中のドラッグを全て終了。
// pointerupが届かず残留したドラッグが「戻った後に触ると勝手に移動する」原因だった（ヘルバ様報告）
function cancelTransientDrags(){
  try{ if(handleDrag) endHandleDrag(); }catch(_){ handleDrag=null; }
  try{ if(chainGizmoDrag) endChainGizmoDrag(); }catch(_){ chainGizmoDrag=null; }
  try{ if(chainDrag) endChainDrag(); }catch(_){ chainDrag=null; }
  scrubDrag=null; lightMove=null;
  if(wallDrag){ wallDrag=null; try{ updateWallGhost(); }catch(_){} }
  if(box){ box=null; try{ selrect.style.display='none'; }catch(_){} }
}
addEventListener('blur',cancelTransientDrags);
document.addEventListener('visibilitychange',()=>{ if(document.hidden) cancelTransientDrags(); });
addEventListener('pointercancel',cancelTransientDrags);

// ---- box select ----
const selrect=document.getElementById('selrect');
let box=null;
const mainEl=document.getElementById('main');
function mainPos(e){ const r=mainEl.getBoundingClientRect(); return {x:e.clientX-r.left, y:e.clientY-r.top}; }
function screenPosOf(group){ const v=group.position.clone();
  if(group.userData.obj&&(group.userData.obj.kind==='wall'||group.userData.obj.kind==='arc'||group.userData.obj.kind==='chain')){
    // 位置がz原点基準のオブジェクトは先頭位置で判定
    const o=group.userData.obj; const bb=o.kind==='wall'?o.beat:o.b;
    v.set(NOTE_DX,BASE_Y+LAYER,(bb-viewBeat())*ZPB); }   // ノーツ帯のXオフセット込み（0のままだと判定点だけ旧位置に残り、壁/アーク/チェーンが範囲選択で拾えない・2026-07-18）
  v.project(camera);
  const r=cv.getBoundingClientRect(); return { x:(v.x+1)/2*r.width, y:(-v.y+1)/2*r.height, in:v.z<1 }; }

function createClipAt(b,lk,top){   // bを含む1小節(4拍)クリップを空きレーンに作成→track。top=true:一番上寄り/false:一番下寄りに探す。ロック中レーンは避ける。空き無しなら上に新レーン追加。不可なら-1
  const start=Math.max(0,Math.floor(b/4)*4), len=4, N=laneCountOf(lk);
  const mk=tr=>{ const sec={id:'n'+(++_nid)+Math.random().toString(36).slice(2,6),beat:start,track:tr,lk,col:pickStripCol(),
      label:'Sheet',len,kind:'sheet',content:{notes:[],bombs:[],walls:[],arcs:[],chains:[],lights:[]}};
    sections.push(sec); relinkDiffEdges(); return tr; };
  for(let i=0;i<N;i++){ const tr=top?i:N-1-i;   // top=上から / bottom=下(Layer1)から
    if(layerLockS.has(lk+tr)) continue;          // ロック中レーンには作らない
    if(laneOverlaps(start,len,lk,tr)) continue;  // 他クリップと重ならない段のみ
    return mk(tr); }
  // 空きが無い（全て埋まり/ロック）→ 上に新レーンを追加してtrack0に作成
  if(N<LANE_MAX){
    if(lk==='n') notesLanes++; else lightLanes++;
    laneShiftAll(lk,1);   // 既存を1段下げ、track0を空ける（ソロ/ミュートはlaneShiftAll内でリセット）
    const shifted=new Set();   // ロックも1段下げて整合（新track0は非ロック）
    for(const key of layerLockS){ if(key[0]===lk) shifted.add(lk+(+key.slice(1)+1)); else shifted.add(key); }
    layerLockS.clear(); for(const k of shifted) layerLockS.add(k);
    return mk(0); }
  return -1;
}
function createNoteClipAt(b){ return createClipAt(b,'n',false); }   // 後方互換
// EDIT配置の対象クリップ決定ルール（ヘルバ様指定）: 無→作成／有→そのクリップ／重なり→①選択中②なければ一番下／全ロック→一番上に新規（空き無ければ上に新レーン）
function clipTrackForBeat(b,lk){
  const cover=sections.filter(s=>secLk(s)===lk&&s.kind!=='null'&&(s.beat||0)<=b+1e-6&&(s.beat||0)+(s.len||4)>b+1e-6);
  if(!cover.length) return createClipAt(b,lk,false);              // クリップ無し→作成（一番下寄り）
  const isLk=c=>layerLockS.has(lk+(c.track||0));
  const sel=cover.find(c=>layerSel.has(c.id)&&!isLk(c));          // ①選択中クリップを優先
  if(sel) return sel.track||0;
  const unlocked=cover.filter(c=>!isLk(c));
  if(unlocked.length) return unlocked.reduce((a,c)=>((c.track||0)>(a.track||0)?c:a)).track||0;   // ②一番下(track最大)
  return createClipAt(b,lk,true);                                // ③全ロック→一番上に新規
}
function noteTrackForBeat(b){ return clipTrackForBeat(b,'n'); }
// ペースト用トラック解決: コピー元のトラックがその拍でまだ有効（クリップがあり非ロック）ならそのまま使う。
// ロック済み/クリップ消失なら通常配置と同じ規則へフォールバック（clipTrackForBeat＝全ロックなら新規クリップを自動作成）。
// ヘルバ様指摘: 「ペースト先の一番下トラックがロックされていたら、新規トラックを作ってでも別の場所へ」
function pasteTrackFor(b,lk,preferTr){
  if(preferTr!=null&&!layerLockS.has(lk+preferTr)){
    const cov=sections.find(s=>secLk(s)===lk&&s.kind!=='null'&&(s.track||0)===preferTr&&(s.beat||0)<=b+1e-6&&(s.beat||0)+(s.len||4)>b+1e-6);
    if(cov) return preferTr;
  }
  return clipTrackForBeat(b,lk);
}
function placeAt(cell){
  if(inNullRange(snapV(lockBeat))){ stat('⚠ NULLノードの範囲には配置できません'); return; }
  const b=snapV(lockBeat);
  const tr=noteTrackForBeat(b);   // クリップが無い拍なら Layer1 の空きにクリップを自動生成
  if(tr<0){ stat('⚠ クリップを作れません（ノーツレーンが全て埋まっています）'); return; }
  if(!sigConnected('notes')){ stat('⚠ ノーツの配線が切断中です（ノードエディタで再接続してから）'); return; }
  snapshot();
  if(brush.type==='note'){
    const exist=notes.find(n=>Math.abs(n.beat-b)<1e-4&&n.x===cell.x&&n.y===cell.y);
    if(exist){ exist.c=brush.c; exist.d=brush.d; exist._tr=tr; refreshMesh(exist); selection=new Set([exist]); }
    else { const n={kind:'note',beat:b,x:cell.x,y:cell.y,c:brush.c,d:brush.d,_tr:tr,raw:null}; notes.push(n); addObj(n); selection=new Set([n]); }
  } else if(brush.type==='bomb'){
    const exist=bombs.find(n=>Math.abs(n.beat-b)<1e-4&&n.x===cell.x&&n.y===cell.y);
    if(exist){ undoStack.pop(); return; }   // 変化なし: 直前のスナップショットを捨てる
    const n={kind:'bomb',beat:b,x:cell.x,y:cell.y,_tr:tr,raw:null}; bombs.push(n); addObj(n); selection=new Set([n]);
  }
  gizmoMode=null;   // 置いた直後はギズモを出さない＝連続配置中にハンドルが次のクリックを奪わない（ギズモは既存をクリックで選択した時だけ）
  if(camMode==='place') selection.clear();   // 配置モードは置いた後に選択を残さない＝次を違う傾きで置ける（ヘルバ様指定）
}
function deleteNoteBombAt(e){   // 配置モードの右クリック: マウス下のノーツ/ボム/壁を削除（ヘルバ様指定）
  const o=objUnder(e);
  if(o&&(o.kind==='note'||o.kind==='bomb'||o.kind==='wall')){ snapshot(); removeObj(o); metaDirty=true; stat(tf('msg.deleted','削除しました')); return true; }
  return false;
}
// 配置モードの壁は段階式（ヘルバ様指定）:
//  ①クリック=一番小さい壁を仮配置→高さ調整へ ②マウス追従で高さ変動→クリックで確定→奥行き調整へ ③マウス追従で奥行き変動→クリックで確定=終了
function wallPlaceClick(e){
  if(wallStage){                                // 進行中: クリックで確定→次ステージ（横幅→高さ→奥行き→終了）
    if(wallStage.stage==='width'){ wallStage.stage='height'; applyWallStage(); stat(tf('msg.wallStageH','壁: 高さを調整（クリックで確定）')); }
    else if(wallStage.stage==='height'){ wallStage.stage='depth'; applyWallStage(); stat(tf('msg.wallStageD','壁: 奥行きを調整（クリックで確定）')); }
    else { const w=wallStage.wall; wallStage=null; wallDimArrows.visible=false; selection=new Set([w]); metaDirty=true; stat(tf('msg.wallDone','壁を確定しました')); }
    return;
  }
  const cHit=raycaster.intersectObjects(cellPlanes)[0];   // 新規: 一番小さい壁を仮配置
  if(!cHit) return;
  const {x,y}=cHit.object.userData;
  const wb=snapV(lockBeat);
  if(inNullRange(wb)){ stat('⚠ NULLノードの範囲には配置できません'); return; }
  const wtr=noteTrackForBeat(wb);
  if(wtr<0){ stat('⚠ クリップを作れません（ノーツレーンが全て埋まっています）'); return; }
  if(!sigConnected('notes')){ stat('⚠ ノーツの配線が切断中です（ノードエディタで再接続してから）'); return; }
  snapshot();
  const n={kind:'wall',beat:wb,x,y,dur:WALL_MIN_DUR,w:1,h:1,_tr:wtr,raw:null};   // 1ボックス分からスタート
  walls.push(n); addObj(n);
  wallGhost.visible=false; wallHoverCell=null;
  wallStage={wall:n, stage:'width', baseX:x, baseY:y};   // 起点マスを保持（横幅/高さは起点からの双方向スパン）
  updateWallDimArrows();
  stat(tf('msg.wallStageW','壁: 横幅を調整（クリックで確定）'));
}
// マウス追従で仮配置中の壁を更新（高さ=マス段 / 奥行き=床の拍）
function applyWallStage(){
  if(!wallStage) return;
  const w=wallStage.wall;
  if(wallStage.stage==='depth'){
    if(raycaster.ray.intersectPlane(floorPlane,_fv)){
      const b=Math.max(0,snapV(viewBeat()+_fv.z/ZPB));
      const nd=Math.max(WALL_MIN_DUR, +(b-w.beat).toFixed(4));
      if(Math.abs(nd-w.dur)>1e-4){ w.dur=nd; refreshMesh(w); }
    }
  } else {
    // 横幅/高さ: 壁の深さに縦平面を置き、マウスのX/Yを読む（グリッド外・再生ヘッド外でも柔軟に効く・ヘルバ様指定）
    const m=meshes.find(mm=>mm.obj===w);
    const wz=m?m.group.position.z:(w.beat-cur)*ZPB;
    _wallHPlane.set(_zNormal,-wz);
    if(raycaster.ray.intersectPlane(_wallHPlane,_fv)){
      if(wallStage.stage==='width'){
        const col=Math.max(0,Math.min(3, Math.round(1.5-(_fv.x-NOTE_DX)/LANE)));   // 起点からの双方向スパン（NOTE_DXを外してから）
        const x0=Math.min(wallStage.baseX,col), nw=Math.abs(col-wallStage.baseX)+1;
        if(x0!==w.x||nw!==w.w){ w.x=x0; w.w=nw; refreshMesh(w); }
      } else {   // height: 起点からの双方向スパン（最上段でも下へ伸ばせる・ヘルバ様指定）
        const layer=Math.max(0,Math.min(2, Math.round((_fv.y-BASE_Y)/LAYER)));
        const y0=Math.min(wallStage.baseY,layer), nh=Math.abs(layer-wallStage.baseY)+1;
        if(y0!==w.y||nh!==w.h){ w.y=y0; w.h=nh; refreshMesh(w); }
      }
    }
  }
  updateWallDimArrows();
}
// 仮配置中の壁を撤去（右クリック/Esc/モード離脱）
function cancelWallStage(){
  if(!wallStage) return;
  removeObj(wallStage.wall);
  if(undoStack.length) undoStack.pop();   // 仮配置時のスナップショットも捨てる
  wallStage=null; wallDimArrows.visible=false;
  stat(tf('msg.wallCancel','壁の配置を中止しました'));
}

cv.addEventListener('pointerdown', e=>{
  if(pieOpen) return;
  { const ae=document.activeElement; if(ae&&ae.blur&&/^(INPUT|TEXTAREA|SELECT)$/.test(ae.tagName||'')) ae.blur(); }   // 3Dビューをクリックしたら入力欄のフォーカスを外す＝以後の単キー(F色切替/S/W等)が確実に効く。入力欄にフォーカスが残るとkeydownが7339で全遮断され「配置中にFが効かない」が起きる（ヘルバ様報告 2026-07-14）
  selWatch(lightMode?'light':'note');   // 3Dの選択変化も1動作として履歴へ
  // チェーン曲線ギズモ
  // placeMode(常時武装)ではなくShiftの有無で門を作る＝素クリックはチェーン/アークの掴み・編集を通し、Shiftは選択/範囲選択へ落とす
  if(e.button===0&&!lightMode&&!e.shiftKey){ setPtr(e);
    const cgH=pickChainGizmo(e);
    if(cgH){ startChainGizmoDrag(cgH); return; }
    const chH=pickChainHandle(e);
    if(chH){ startChainDrag(chH,e); return; }
    const ep=pickCurveEndpoint(e);
    if(ep){
      selection=new Set([ep.obj]);
      if(ep.obj.kind==='chain'){   // 部位でモード決定: 頭=親選択(緑+全体移動) / 尾=修正モード(青+スライダー)（ヘルバ様指定）
        chainSelPart=(ep.role==='head')?'head':'child';
        gizmoMode=chainSelPart==='head'?'move':null;
        stat(chainSelPart==='child'
          ? tf('msg.chainEditChild','チェーン(子): スライダー=分割/詰め ・ ミニギズモ=頭/尾の移動')
          : tf('msg.chainEdit','チェーン: 頭ノーツ=XYZ 向き(黄)=XY 尾ノーツ=XYZ / 外枠矢印=全体移動'));
      } else if(ep.obj.kind==='arc'){   // アーク: 頭/尾どちらを掴んでも全体移動ギズモ+ミニギズモを併用（チェーンの「子」相当・部位モード分けは不要）
        gizmoMode='move';
        stat(tf('msg.arcEdit','アーク: 頭/尾ドラッグ=XYZ移動 ／ 端点上Alt+ホイール=向き ／ Alt+ホイール=mu・Ctrl+Alt=tmu・Shift+Alt=巻き方向'));
      } else { gizmoMode=null; syncGizmoForSelection(); }
      startChainDrag({role:ep.role,chain:ep.obj},e);
      return;
    } }
  // ギズモハンドル → ドラッグ開始
  if(e.button===0&&gizmo.visible){ setPtr(e);
    const gh=raycaster.intersectObjects(gizmoHandles.filter(g=>g.visible),true)[0];
    if(gh){
      // 手前に未選択オブジェクトが見えていれば、それの選択を優先（ギズモが隣ノーツに埋まって掴めてしまうのを防ぐ・ヘルバ様指定）
      let frontDist=1e9, frontObj=null;
      for(const h of (lightMode?[]:raycaster.intersectObjects(meshes.filter(m=>m.group.visible&&!objLockedN(m.obj)).map(m=>m.group),true))){   // ライト編集中はノーツを盾にしない（重なっているため）
        let ob=h.object; while(ob&&!ob.userData.obj)ob=ob.parent; const oo=ob&&ob.userData.obj; if(!oo) continue; frontObj=oo; frontDist=h.distance; break; }
      const blockedByNote=frontObj&&!selection.has(frontObj)&&frontDist<gh.distance;
      if(!blockedByNote){ let o=gh.object; while(o&&!o.userData.arrow)o=o.parent;
        if(o&&startHandleDrag(o.userData.arrow)) return; } } }
  // ペーストゴースト: 床クリックで確定（ギズモ/オブジェクト以外）
  if(pasteFollow&&e.button===0&&!lightMode&&!placeMode&&!e.shiftKey){ setPtr(e);
    const n=objUnder(e);
    if(!n){
      const cell=hoverGridCell();
      if(cell||raycaster.ray.intersectPlane(floorPlane,_fv)){ pasteFloorClick=true; return; } }
  }
  // 拍番号レーン: クリック=その拍へジャンプ／そのままドラッグ=スクラブ（NLEルーラーと同じ操作。赤ライン自体のドラッグは廃止）
  if(e.button===0){ setPtr(e);
    const nh=raycaster.intersectObject(numStrip)[0];
    if(nh){ if(playing) pause();
      if(vwB==null) vwB=viewBeat();                      // ビューを固定: 画面は動かず、ヘッドがクリック位置へ飛んでくる（NLEと同じ）
      curAnim=null;
      // 着地拍=黄ライン(hoverBeat)そのもの＝見えている値と必ず一致（帯と床の交差面の高さ差による半拍ズレを排除）
      cur=Math.max(0,(hoverBeat!=null)?hoverBeat:snapV(vwB+nh.point.z/ZPB)); offset=beatToTimeTM(cur);
      scrubDrag=true; return; } }                        // そのままドラッグ=固定ビュー上で絶対シーク（NLEルーラーと同じ。ビューは一切動かさない）
  // ペースト追従中の右クリック=取消（NLEの layerPaste と同じ流儀・ヘルバ様指定 2026-07-18）。
  // 削除や配置より手前で拾う＝ゴーストを消すだけで他の操作は起こさない
  if(e.button===2&&pasteFollow){ e.preventDefault(); cancelPasteFollow(); return; }
  if(e.button===2&&lightMove){ e.preventDefault(); cancelLightMove(); return; }   // ライトのペースト追従も同様に右クリックで取消
  // ライト編集モード: レーンへ配置 / 右クリックで削除（外れたら終了）
  if(lightMode){ setPtr(e); refreshLightHover();
    if(e.button===0&&lightMove){ lightMove=null; stat('ライト移動確定'); return; }   // ペースト追従の確定（数字の盾より前＝確定を邪魔しない）
    // 数字が盾になるのは「その奥に箱が無いとき」だけ。箱が有れば箱を優先＝真上寄りの角度で数字が箱に重なっても掴める
    // （ヘルバ様報告 2026-07-17: 盾が効きすぎて一切クリックできなかった）
    if(overLightNumRay()&&!lightUnder(e)) return;   // 数字だけの上＝選択/配置/削除/範囲選択の起点、どれも起こさない
    if(e.button===0&&e.shiftKey){
      const ex=lightUnder(e)||hoverLightEvent();
      if(ex){ lightSelection.has(ex)?lightSelection.delete(ex):lightSelection.add(ex);
        gizmoMode=lightSelection.size?'move':null; return; }   // Shift+クリック=追加/解除
      const p=mainPos(e); box={x0:p.x,y0:p.y,light:true,add:true}; return; }   // Shift=追加範囲選択
    if(e.button===0&&e.ctrlKey&&lightHover){ placeLight(); return; }               // Ctrl+左=強制配置＝配置済みライトの上にも重ねられる（選択に化けない逃げ道）
    if(e.button===0){
      const ex=lightUnder(e)||(lightHover?hoverLightEvent():null);   // 見えているチップを最優先（配置モードでも拾える）
      if(ex){ lightSelection=new Set([ex]); gizmoMode='move';                      // 配置済みライトの上=選択＋移動ギズモ（セレクトツール廃止・ヘルバ様指定）
        stat(tf('msg.lightSel','選択: {lane} 拍{beat} {desc}',{lane:(LIGHT_LANES[laneIdxByType[ex.et]]||{}).n||'',beat:ex.beat,desc:lightDesc(laneKind(ex.et),ex.i,ex.f,getLightChroma(ex))})); return; }
      if(lightHover){ placeLight(); return; }                                      // レーン上の空き=配置
      const p=mainPos(e); box={x0:p.x,y0:p.y,light:true}; return; }   // レーン外の左ドラッグ=範囲選択・クリックのみ=解除（NLEと同じ）
    if(e.button===2){ if(lightHover) deleteLightAt(); return; }   // 右=削除に統一（ヘルバ様指定）。何もない場所の右クリックでノーツモードへは戻さない
  }
  // 配置モード＋配置系ブラシ: 左=配置 / 右=削除。Shift付きは必ず下の選択・範囲選択へ落とす（以前はここで飲み込まれ、Shift範囲選択がブラシ武装中に効かなかった＝ヘルバ様報告）
  if(camMode==='place'&&!lightMode&&placeMode&&!e.shiftKey){
    if(e.button===0){ setPtr(e);
      // 段階式の壁を調整中は選択へ落とさない＝2回目以降のクリックが「今置いた壁の選択」に吸われて
      // ステージ（横幅→高さ→奥行き）が進まなくなる（ヘルバ様報告 2026-07-17）
      if(wallStage){ wallPlaceClick(e); return; }
      const n=objUnder(e);
      if(n){ selection=new Set([n]); syncGizmoForSelection();   // 配置済みノーツの上=選択（セレクトツール廃止・ヘルバ様指定）
        if(n.kind==='note'){ brush.c=n.c; brush.d=n.d; setColor(n.c,false); refreshPal(); }
        return; }
      if(brush.type==='wall'){ wallPlaceClick(e); }   // 段階式（仮配置→高さ→奥行き）
      else { refreshHoverVisuals(); if(ghostCell) placeAt(ghostCell); }
      return; }
    if(e.button===2){ if(wallStage){ cancelWallStage(); return; } deleteNoteBombAt(e); return; }   // 右クリック=（壁作成中は中止）/ 削除
  }
  if(e.button===0){
    // 段階式の壁を調整中は選択へ落とさない（上の配置モード側と同じ理由）
    if(wallStage&&placeMode&&!e.shiftKey){ setPtr(e); wallPlaceClick(e); return; }
    // 配置済みオブジェクトの上では配置しない＝クリックで選択（セレクトツール廃止・ヘルバ様指定）。空きの時だけブラシで配置する
    const _hit=(!e.shiftKey&&placeMode)?objUnder(e):null;
    // 壁は配置モードと同じ段階式（①クリックで仮配置→横幅 ②高さ ③奥行き）に統一。
    // 旧: 編集モードだけ床ドラッグ式で挙動が食い違っていた（ヘルバ様報告 2026-07-17）
    if(placeMode&&!_hit&&brush.type==='wall'&&!e.shiftKey){ setPtr(e); wallPlaceClick(e); return; }
    if(placeMode&&!_hit&&ghostCell&&!e.shiftKey){ placeAt(ghostCell); return; }
    if(e.shiftKey){
      const n=objUnder(e);
      if(n){ if(n.kind==='chain'&&!selection.has(n)){ const part=pickChainPart(e); chainSelPart=(part&&part.obj===n&&part.role==='head')?'head':'child'; }
        selection.has(n)?selection.delete(n):selection.add(n); syncGizmoForSelection(); }   // 選択があれば自動で移動モード
      else { const p=mainPos(e); box={x0:p.x,y0:p.y,add:true}; }   // Shift=追加選択
      return;
    }
    const n=objUnder(e);
    if(n){ selection=new Set([n]);
      if(pasteFollow) return;   // ゴースト配置中は選択を変えない
      if(n.kind==='chain'){
        const part=pickChainPart(e);   // どの部位を掴んだか: 頭=全体移動 / 子(リンク・尾)=調整モード（ヘルバ様指定）
        chainSelPart=(part&&part.obj===n&&part.role==='head')?'head':'child';   // 頭の箱を掴んだ時だけ親選択・他は全て修正モード（ヘルバ様指定）
        gizmoMode=chainSelPart==='child'?null:'move';
        stat(chainSelPart==='child'
          ? tf('msg.chainEditChild','チェーン(子): スライダー=分割/詰め ・ ミニギズモ=頭/尾の移動')
          : tf('msg.chainEdit','チェーン: 頭ノーツ=XYZ 向き(黄)=XY 尾ノーツ=XYZ / 外枠矢印=全体移動'));
      }
      else { gizmoMode='move';
        if(n.kind==='note'){ brush.c=n.c; brush.d=n.d; setColor(n.c,false); refreshPal(); } } }
    else { if(pasteFollow) return; const p=mainPos(e); box={x0:p.x,y0:p.y}; }   // 空き左ドラッグ=範囲選択
  } else if(e.button===2&&placeMode){          // 右=削除に統一（セレクトツール廃止で「配置モードを抜ける」行き先が無くなったため・ヘルバ様指定）
    if(wallStage){ cancelWallStage(); return; }
    deleteNoteBombAt(e);
  }
});
addEventListener('pointermove', e=>{
  if(box){ const p=mainPos(e);
    const x=Math.min(box.x0,p.x), y=Math.min(box.y0,p.y), w=Math.abs(p.x-box.x0), h=Math.abs(p.y-box.y0);
    Object.assign(selrect.style,{display:'block',left:x+'px',top:y+'px',width:w+'px',height:h+'px'}); }
});
addEventListener('pointerup', e=>{
  const wasHandleDrag=!!handleDrag;
  if(scrubDrag){ scrubDrag=null; if(camMode==='place'){ vwB=null; vwPlayD=null; } return; }   // 配置モード=拍ラベルのクリック/スクラブ後はヘッド追従へ復帰（ビュー固定を残さない・ヘルバ様指定）
  if(chainGizmoDrag){ endChainGizmoDrag(); return; }
  if(chainDrag){ endChainDrag(); return; }
  if(handleDrag){ endHandleDrag(); return; }
  if(pasteFloorClick&&!box&&!wasHandleDrag){ pasteFloorClick=false; confirmPasteFollow(); return; }
  pasteFloorClick=false;
  if(wallDrag){                                       // 壁: ドラッグ確定
    const wb=snapV(lockBeat);
    const wtr=noteTrackForBeat(wb);   // クリップが無い拍なら Layer1 の空きに自動生成
    if(wtr<0){ wallDrag=null; updateWallGhost(); stat('⚠ クリップを作れません（ノーツレーンが全て埋まっています）'); return; }
    if(!sigConnected('notes')){ wallDrag=null; updateWallGhost();
      stat('⚠ ノーツの配線が切断中です（ノードエディタで再接続してから）'); return; }
    const s=wallSpan();
    const rows=s.y1-s.y0+1;
    snapshot();
    const n={kind:'wall',beat:wb,x:s.x0,y:s.y0,dur:Math.max(snap,wallDurLive),
             w:s.x1-s.x0+1,h:rows,_tr:wtr,raw:null};
    walls.push(n); addObj(n); selection=new Set([n]);
    stat(tf('msg.wallInfo','壁: 列{cols} 段{rows} / {dur}拍',{cols:`${s.x0}${s.x1>s.x0?`-${s.x1}`:''}`,rows:`${s.y0}${s.y1>s.y0?`-${s.y1}`:''}`,dur:n.dur}));
    wallDrag=null; updateWallGhost();
    return;
  }
  if(box){ const p=mainPos(e);
    selWatch(box.light?'light':'note');   // 範囲選択の確定も1動作として履歴へ
    const x0=Math.min(box.x0,p.x), y0=Math.min(box.y0,p.y), x1=Math.max(box.x0,p.x), y1=Math.max(box.y0,p.y);
    if(x1-x0>4||y1-y0>4){
      if(box.light){                                     // ライトイベントの範囲選択（Shiftなし=置き換え/Shift=追加。NLEと同じ）
        if(!box.add) lightSelection.clear();
        let added=0; const r=cv.getBoundingClientRect(), v=new THREE.Vector3();
        const vb=viewBeat();   // チップの描画基準(drawの db=ev.beat-viewB)と必ず揃える。curで判定すると編集モード/ビュー固定中に
                               // vwB!=cur となり、枠を描いても当たり判定だけ (cur-viewBeat())*ZPB ぶんズレて何も選べなかった（ヘルバ様報告）
        for(const ev of lightEvents){ const li=laneIdxByType[ev.et]; if(li===undefined) continue;
          if(lightHiddenEv(ev)||!layerVisible('l',ev._tr||0)||objLockedL(ev)) continue;   // 見えていないライト(Chroma中のBOOST/ミュート/ソロ対象外)とロック中レーンは選ばない＝ノーツ側(m.group.visible/objLockedN)と同じ流儀
          const db=ev.beat-vb; if(db<-20||db>20) continue;
          v.set(LANE_X0+li*LANE_DX,0.03,db*ZPB); v.project(camera);
          const sx=(v.x+1)/2*r.width, sy=(-v.y+1)/2*r.height;
          if(v.z<1&&sx>=x0&&sx<=x1&&sy>=y0&&sy<=y1){ if(!lightSelection.has(ev)){ lightSelection.add(ev); added++; } } }
        stat(tf('msg.lightBoxSel','ライト範囲選択: +{added}（計{total}）',{added,total:lightSelection.size}));
      } else {
        if(!box.add) selection.clear();
        let added=0;
        for(const m of meshes){ if(!m.group.visible||objLockedN(m.obj)) continue; const s=screenPosOf(m.group);   // ロック中レーンは範囲選択からも除外
          if(s.in&&s.x>=x0&&s.x<=x1&&s.y>=y0&&s.y<=y1){ if(!selection.has(m.obj)){selection.add(m.obj); added++;} } }
        stat(tf('msg.boxSel','範囲選択: +{added}（計{total}）',{added,total:selection.size})); } }
    else if(!box.add){ if(box.light) lightSelection.clear(); else selection.clear(); }
    if(box.light) gizmoMode=lightSelection.size?'move':null;   // 範囲選択の結果にもギズモを出す（ノーツのsyncGizmoForSelectionと同じ流儀）
    else syncGizmoForSelection();
    box=null; selrect.style.display='none'; }
});
cv.addEventListener('contextmenu',e=>e.preventDefault());
// ---- wheel ----
let lastRotTime=0, lastRotTarget=null;
function tlScrub(e,invert){ e.preventDefault();   // Shift+ホイール=再生ヘッドをスナップ幅でスクラブ（全画面共通）。
  // invert=true は3Dビューのみ（環境設定「3Dビューのホイール操作を反転」）。2D側(NLE/Music)は従来通り常に非反転。
  const up=invert?(e.deltaY>=0):(e.deltaY<0);
  cur=Math.max(0,snapV(cur+(up?snap:-snap))); offset=beatToTimeTM(cur);
  if(playing) play();   // 再生中は止めず新位置から再スケジュール（A/Dと同じ流儀）
}
cv.addEventListener('wheel', e=>{ e.preventDefault();
  if(e.altKey&&lightMode){ // ライト: 強さ調整（Alt=±10 / Ctrl+Alt=±1）。ホバー中のイベント優先、なければブラシ
    const dir=(e.deltaY!==0?e.deltaY:e.deltaX)>0?-1:1;
    setPtr(e); refreshLightHover();
    const kind=lightHover?laneKind(LIGHT_LANES[lightHover.lane].t):'color';
    const now=performance.now();
    if(kind==='speed'){                                // 速度レーンは±1
      // 強さ(f)と同じく選択優先＝選択中のSPEEDライトを一括で増減（ヘルバ様指定 2026-07-18）
      let sp=[...lightSelection].filter(x=>laneKind(x.et)==='speed');
      if(!sp.length){ const hv=hoverLightEvent(); if(hv&&laneKind(hv.et)==='speed') sp=[hv]; }
      if(sp.length){ if(now-lastLightFTime>500) snapshot(); lastLightFTime=now;
        for(const ev of sp) ev.i=Math.max(0,Math.min(50,ev.i+dir));
        _flatDirty=true; metaDirty=true;
        stat(tf('msg.laserSpeed','レーザー速度: {v}',{v:sp[0].i})+(sp.length>1?` ×${sp.length}`:'')); }
      else { lightBrush.speed=Math.max(0,Math.min(50,lightBrush.speed+dir));
        updateLightUI(); stat(tf('msg.brushSpeed','ブラシ速度: {v}',{v:lightBrush.speed})); }
    } else {
      const step=dir*(e.ctrlKey?1:10);
      // 適用先＝選択中のライト全部（色と同じ流儀）→ 選択が無ければマウス下の1つ（ヘルバ様指定 2026-07-18）
      let targets=[...lightSelection].filter(x=>x.i>0&&laneKind(x.et)==='color');
      if(!targets.length){ const hv=hoverLightEvent(); if(hv&&hv.i>0&&laneKind(hv.et)==='color') targets=[hv]; }
      if(targets.length){
        if(now-lastLightFTime>500) snapshot(); lastLightFTime=now;
        for(const ev of targets) ev.f=Math.max(0,Math.min(2.0,(ev.f??1)+step/100));
        _flatDirty=true; metaDirty=true;
        stat(tf('msg.lightIntensity','ライト強さ: {v}',{v:Math.round(targets[0].f*100)})+(targets.length>1?` ×${targets.length}`:''));
      } else {
        lightBrush.f=Math.max(0,Math.min(2.0,lightBrush.f+step/100));
        const rg=document.getElementById('lfRange'); if(rg) rg.value=Math.round(lightBrush.f*100);
        const lv=document.getElementById('lfVal'); if(lv) lv.textContent=lightBrush.f.toFixed(2);
        stat(tf('msg.brushIntensity','ブラシ強さ: {v}',{v:Math.round(lightBrush.f*100)}));
      }
    }
    refreshLightHover();
    return; }
  if(e.altKey&&!lightMode){ // アーク: 端点上Alt+ホイール=向き(d/tc) / それ以外Alt+ホイール=mu / Ctrl+Alt=tmu / Shift+Alt=巻き方向m（チェーンのAlt+ホイール流儀に合わせた・ヘルバ様指定）
    const as=selArcs();
    if(as.length){
      const delta=(e.deltaY!==0?e.deltaY:e.deltaX); const dir=delta>0?-1:1;
      const part=(!e.ctrlKey&&!e.shiftKey)?pickArcPart(e):null;   // 端点の向き変更はCtrl/Shift無しの素のAlt+ホイールのみ（mu/tmu/mと衝突しないように）
      const a=(part&&part.obj&&as.includes(part.obj))?part.obj:null;
      if(a&&part.role==='head'){
        const now=performance.now(); if(now-lastRotTime>500||lastRotTarget!==a) snapshot();
        lastRotTime=now; lastRotTarget=a;
        a.d=rotStep(a.d,dir);   // アークの端点はドットも許容（実データにdot終端あり・チェーンの頭とは違う制約）
        _flatDirty=true; refreshMesh(a); updateChainOverlay();
        stat(tf('msg.arcHeadDir','頭の向き: {dir}',{dir:DIRICON[a.d]}));
      } else if(a&&part.role==='tail'){
        const now=performance.now(); if(now-lastRotTime>500||lastRotTarget!==a) snapshot();
        lastRotTime=now; lastRotTarget=a;
        a.tc=rotStep(a.tc??a.d,dir);
        _flatDirty=true; refreshMesh(a); updateChainOverlay();
        stat(tf('msg.arcTailDir','尾の向き: {dir}',{dir:DIRICON[a.tc]}));
      } else if(e.ctrlKey){
        tweakSelArcs(a2=>{ a2.tmu=Math.max(0.1,Math.min(10,Math.round((a2.tmu+(dir*0.1))*100)/100)); },
          tf('msg.arcTmu','アーク tmu={v}',{v:as[0].tmu}));
      } else if(e.shiftKey){
        tweakSelArcs(a2=>{ a2.m=((a2.m??0)+dir+3)%3; },
          tf('msg.arcWrap','巻き方向: {m}',{m:[t('ui.wrapAuto','自動'),t('ui.wrapCW','時計回り'),t('ui.wrapCCW','反時計回り')][as[0].m??0]}));
      } else {
        tweakSelArcs(a2=>{ a2.mu=Math.max(0.1,Math.min(10,Math.round((a2.mu+(dir*0.1))*100)/100)); },
          tf('msg.arcMu','アーク mu={v}',{v:as[0].mu}));
      }
      return; }
    // チェーン選択時のホイールは3つだけ（ヘルバ様指定 2026-07-12）:
    //   Ctrl+ホイール=分割数sc（別ハンドラ） / Ctrl+Alt+ホイール=squish / 頭・尾ノーツ上 Alt+ホイール=向き
    //   Shift系の組み合わせ（旧: Shift+Alt=曲率・Ctrl+Shift+Alt=縮小率）は廃止
    const cs=selChains();
    if(cs.length){
      const delta=(e.deltaY!==0?e.deltaY:e.deltaX); const dir=delta>0?-1:1;
      if(e.shiftKey){ /* Shift系は未割り当て */ }
      else if(e.ctrlKey){
        tweakSelChains(c=>{ c.s=Math.max(0.1,Math.min(2,Math.round((c.s+(dir*0.1))*100)/100)); },   // 範囲はスライダーと統一(0.1〜2)
          tf('msg.chainSquish','チェーン squish={v}',{v:cs[0].s}));
      } else {
        const part=pickChainPart(e);
        const ch=part?.obj?.kind==='chain'&&selection.has(part.obj)?part.obj:null;
        if(ch&&part.role==='head'){
          const now=performance.now();
          if(now-lastRotTime>500||lastRotTarget!==ch) snapshot();
          lastRotTime=now; lastRotTarget=ch;
          const step=delta>0?1:-1;   // 通常ノーツの Alt+ホイール回転と同じ向き
          ch.d=rotStepNoDot(ch.d,step);   // チェーン頭もドット(8)を除く8方向のみ（ヘルバ様指摘）
          _flatDirty=true;
          refreshMesh(ch);
          updateChainOverlay();
          stat(tf('msg.rotate','回転: {dir}{mult}',{dir:DIRICON[ch.d],mult:''}));
        }
      }
      return; }
  }
  if(e.ctrlKey&&!e.altKey&&!e.shiftKey&&!e.metaKey&&!lightMode){   // チェーン選択中: Ctrl+ホイール=分割数 sc（ヘルバ様指定）
    const cs=selChains();
    if(cs.length){
      const delta=(e.deltaY!==0?e.deltaY:e.deltaX); const dir=delta>0?-1:1;
      tweakSelChains(c=>{ c.sc=Math.max(2,Math.min(50,(c.sc??5)+dir)); },
        tf('msg.chainSc','チェーン 分割数 sc={v}',{v:cs[0].sc??5}));
      return; }
  }
  if(e.altKey&&!e.ctrlKey&&!e.metaKey&&!e.shiftKey){ // 向き回転（Alt+ホイール・カーソル直下が選択中ノーツなら選択全体を回転 / それ以外は配置済み・選択の有無に関わらずブラシ向きのみ）
    const delta=(e.deltaY!==0?e.deltaY:e.deltaX); const step=delta>0?1:-1;   // スクロール下=ROT順（下→左下→…→ドット＝プルダウンと同順・ドットは最後。ヘルバ様指定）
    const hov=objUnder(e);
    // カーソル直下が選択中ノーツの時だけ選択全体を回す＝「1個だけ回したいなら1個だけ選択してその上で」「複数なら複数選択してその上で」に統一（ヘルバ様指定 2026-09-22）。
    // 配置モード中でも既存ノーツをクリック選択できる（7058行目）が、そこで武装解除はされない＝選択に入っていないノーツの上や空き地では従来通りブラシ側だけが動く（配置中の巻き込み事故を防ぐ安全策はそのまま維持）
    const targets = (hov&&hov.kind==='note'&&selection.has(hov)) ? [...selection].filter(o=>o.kind==='note') : [];
    if(targets.length){ const now=performance.now();
      if(now-lastRotTime>500||lastRotTarget!==hov) snapshot();
      lastRotTime=now; lastRotTarget=hov;
      targets.forEach(n=>{ n.d=rotStep(n.d,step); refreshMesh(n); });
      brush.d=targets[targets.length-1].d; refreshPal();
      if(placeMode) refreshGhost();
      stat(tf('msg.rotate','回転: {dir}{mult}',{dir:DIRICON[targets[0].d],mult:targets.length>1?` ×${targets.length}`:''})); }
    else { brush.d=rotStep(brush.d,step); refreshPal();
      if(placeMode) refreshGhost();
      stat(tf('msg.brushDir','ブラシ向き: {dir}',{dir:DIRICON[brush.d]})); }
    return; }
  if(e.shiftKey&&!e.ctrlKey&&!e.altKey&&!e.metaKey){   // Shift+ホイール=ズーム（マウス位置に向かって寄る・ヘルバ様指定 2026-07-13）
    setPtr(e);
    let focus;
    if(raycaster.ray.intersectPlane(floorPlane,_fv))
      focus=new THREE.Vector3(Math.max(-12,Math.min(12,_fv.x)),0.4,Math.max(-36,Math.min(36,_fv.z)));
    else focus=controls.target.clone();
    const zk=Math.pow(e.deltaY>0?1.12:0.89,camZoomSpeed);
    camera.position.sub(focus).multiplyScalar(zk).add(focus);
    controls.target.sub(focus).multiplyScalar(zk).add(focus);
    return; }
  if(e.ctrlKey||e.altKey||e.metaKey) return;   // 他の修飾+ホイールは無効
  tlScrub(e,invert3DScroll);   // 素のホイール=タイムライン操作（スクラブ）（ヘルバ様指定 2026-07-13）。3Dビューのみ環境設定で向きを反転できる
}, {passive:false});

// ---- ギズモ（シャフト付きハンドル。ドラッグで連続移動/サイズ変更） ----
// 移動=円錐ハンドル / サイズ(S・壁)=立方体ハンドル
const gizmo=new THREE.Group(); gizmo.visible=false; scene.add(gizmo); tagHelper(gizmo);
const gizmoHandles=[];
{
  const defs=[
    {dir:[-1,0,0], axis:'x', sign:1,  color:0xff5566},   // レーン軸はcellPosで反転(x増=画面左)。矢印の向きと移動方向を一致させるため符号を反転
    {dir:[1,0,0],  axis:'x', sign:-1, color:0xff5566},
    {dir:[0,1,0],  axis:'y', sign:1,  color:0x55dd66},
    {dir:[0,-1,0], axis:'y', sign:-1, color:0x55dd66},
    {dir:[0,0,1],  axis:'z', sign:1,  color:0x4499ff},
    {dir:[0,0,-1], axis:'z', sign:-1, color:0x4499ff},
  ];
  for(const d of defs){
    const grp=new THREE.Group();
    const m=new THREE.MeshBasicMaterial({color:d.color});
    const shaft=new THREE.Mesh(new THREE.CylinderGeometry(0.018,0.018,0.24,8),m);
    shaft.position.y=0.12; grp.add(shaft);
    const cone=new THREE.Mesh(new THREE.ConeGeometry(0.075,0.2,10),m);
    cone.position.y=0.32; grp.add(cone);
    const cube=new THREE.Mesh(new THREE.BoxGeometry(0.13,0.13,0.13),m);
    cube.position.y=0.30; cube.visible=false; grp.add(cube);
    grp.quaternion.setFromUnitVectors(new THREE.Vector3(0,1,0),new THREE.Vector3(...d.dir));
    grp.scale.setScalar(0.58);   // 矢印を小さく（隣接ノーツへ埋まりにくく＝隣を選択しやすい・ヘルバ様指定）
    grp.userData.arrow=d; grp.children.forEach(c=>c.userData.arrow=d);
    grp.userData.cone=cone; grp.userData.cube=cube;
    gizmo.add(grp); gizmoHandles.push(grp);
  }
}
gizmoHandles.forEach(tagHelper);
let gizmoCenter=new THREE.Vector3(), gizmoHalf=new THREE.Vector3(), gizmoValid=false;   // 選択のAABB（矢印と全体枠が共有＝ズレない）
// ライトの選択チップを囲うギズモ。動かせるのはレーン(x)と拍(z)だけ＝段(y)は存在しないのでハンドルも出ない
const _LCHIP_H={x:LLANE*0.42, y:0.13, z:0.17};   // チップ1個ぶんの半径（矢印を箱に密着させる）。幅はレーンに追従＝隣へはみ出さない
function updateGizmoLight(){
  if(!lightSelection.size||box){ gizmo.visible=false; gizmoValid=false; return; }
  const vb=viewBeat();
  let mn=new THREE.Vector3(1e9,1e9,1e9), mx=new THREE.Vector3(-1e9,-1e9,-1e9), any=false;
  for(const ev of lightSelection){
    const li=laneIdxByType[ev.et]; if(li===undefined) continue;
    if(lightHiddenEv(ev)||!layerVisible('l',ev._tr||0)||objLockedL(ev)) continue;   // 見えない/ロック中は対象外（範囲選択と同じ流儀）
    any=true;
    const p=new THREE.Vector3(LANE_X0+li*LANE_DX, 0.02, (ev.beat-vb)*ZPB);
    mn.min(new THREE.Vector3(p.x-_LCHIP_H.x,p.y-_LCHIP_H.y,p.z-_LCHIP_H.z));
    mx.max(new THREE.Vector3(p.x+_LCHIP_H.x,p.y+_LCHIP_H.y,p.z+_LCHIP_H.z)); }
  if(!any){ gizmo.visible=false; gizmoValid=false; return; }
  const c=mn.clone().add(mx).multiplyScalar(0.5), half=mx.clone().sub(mn).multiplyScalar(0.5);
  gizmoCenter.copy(c); gizmoHalf.copy(half); gizmoValid=true;
  if(!gizmoMode){ gizmo.visible=false; return; }
  gizmo.visible=true;
  const off=0.05;
  gizmoHandles.forEach(g=>{ const d=g.userData.arrow;
    g.visible=handleUsable(d,false);
    g.userData.cone.visible=true; g.userData.cube.visible=false;   // ライトはサイズ変更が無い＝常に移動用の円錐
    g.position.set(c.x+d.dir[0]*(half.x+off), c.y+d.dir[1]*(half.y+off), c.z+d.dir[2]*(half.z+off)); });
}
// チップ種別ごとの実寸（中心と各辺）。ホバー枠をぴったり合わせる用＝毎フレームの再計算を避けてキャッシュ
const _CHIP_BB={};
function chipBB(kind){
  if(_CHIP_BB[kind]) return _CHIP_BB[kind];
  const g=CHIP_GEOS[kind]||CHIP_GEOS.on;
  if(!g.boundingBox) g.computeBoundingBox();
  const b=g.boundingBox;
  return _CHIP_BB[kind]={cx:(b.min.x+b.max.x)/2, cy:(b.min.y+b.max.y)/2, cz:(b.min.z+b.max.z)/2,
                         sx:b.max.x-b.min.x, sy:b.max.y-b.min.y, sz:b.max.z-b.min.z};
}
// マウス直下のノーツ/ライトを黄色枠で囲う。ドラッグ中や3D外は出さない（枠がチラついて邪魔になるため）
function updateHoverBox(){
  hoverBox.visible=false;
  if(hoverPane!=='main'||box||orbitDrag||panDrag||handleDrag||wallDrag||lightMove||pasteFollow) return;
  if(lightMode){
    const ev=lightUnder(null);   // 直近のマウス位置(pointer)でチップを拾う
    if(!ev) return;
    const li=laneIdxByType[ev.et]; if(li===undefined) return;
    // チップの実ジオメトリにぴったり＋わずかな余白。_LCHIP_H(ギズモ用の余裕込み)を使うと高さ/奥行きが3.8倍になり
    // 数字まで飲み込んで「一回り大きい枠」に見えなかった（ヘルバ様報告 2026-07-17）
    const b=chipBB(chipKindOf(ev.et,ev.i)), pad=0.03;
    hoverBox.rotation.z=0;
    hoverBox.position.set(LANE_X0+li*LANE_DX+b.cx, 0.02+b.cy, (ev.beat-viewBeat())*ZPB+b.cz);   // 0.02=チップ本体の設置Y
    hoverBox.scale.set((b.sx+pad)/0.465,(b.sy+pad)/0.465,(b.sz+pad)/0.465);
    hoverBox.visible=true; return;
  }
  const o=objUnder(null);
  if(!o) return;
  const m=meshes.find(x=>x.obj===o); if(!m||!m.group.visible) return;
  fitBoxTo(hoverBox,o,m);   // 選択枠と同じ密着計算
  hoverBox.visible=true;
}
function updateGizmo(){
  // 表示は常に選択物へ追従（ドラッグ計算は handleDrag.center 固定なので安全）
  // placeMode(ブラシ武装)は条件から外す＝セレクトツール廃止で常時武装のため、これを見ると選択してもギズモが一切出ない。
  // 出る/出ないは gizmoMode（下）が決める＝配置直後は出ず、既存をクリックで選択した時だけ出る（ヘルバ様指定）
  if(lightMode){ return updateGizmoLight(); }   // ライトはレーン(x)/拍(z)の2軸だけ動く＝専用の箱寄せ
  if(!selection.size||box){ gizmo.visible=false; gizmoValid=false; return; }
  const sizeShape=gizmoMode==='size'&&selWalls().length>0;
  let mn=new THREE.Vector3(1e9,1e9,1e9), mx=new THREE.Vector3(-1e9,-1e9,-1e9), any=false;
  for(const m of meshes){ const o=m.obj; if(!selection.has(o)||!m.group.visible) continue; any=true;
    if(o.kind==='wall'){ const {hh,cx,cy,len}=wallDims(o); const z=m.group.position.z;
      mn.min(new THREE.Vector3(cx-o.w*LANE/2, cy-hh*LAYER/2, z));
      mx.max(new THREE.Vector3(cx+o.w*LANE/2, cy+hh*LAYER/2, z+len)); }
    else if(o.kind==='note'||o.kind==='bomb'){ const p=m.group.position;
      const diag=o.kind==='note'&&o.d>=4&&o.d<=7;   // 斜めノーツは枠が45°回転→外接がsqrt2倍
      const hxy=0.2325*(diag?1.42:1), hz=0.2325*(o.kind==='note'?NOTE_THIN:1);   // 選択枠(selGeom 0.465)の実寸に一致＝矢印が箱に密着
      mn.min(new THREE.Vector3(p.x-hxy,p.y-hxy,p.z-hz)); mx.max(new THREE.Vector3(p.x+hxy,p.y+hxy,p.z+hz)); }
    else if(o.kind==='chain'){ const b=chainBounds(o), gz=m.group.position.z;
      mn.min(new THREE.Vector3(b.mn.x,b.mn.y,gz+b.mn.z)); mx.max(new THREE.Vector3(b.mx.x,b.mx.y,gz+b.mx.z)); }
    else { const b=arcBounds(o), gz=m.group.position.z;   // アーク=曲線全体のAABB
      mn.min(new THREE.Vector3(b.mn.x,b.mn.y,gz+b.mn.z)); mx.max(new THREE.Vector3(b.mx.x,b.mx.y,gz+b.mx.z)); } }
  if(!any){ gizmo.visible=false; gizmoValid=false; return; }
  const c=mn.clone().add(mx).multiplyScalar(0.5);
  const half=mx.clone().sub(mn).multiplyScalar(0.5);
  gizmoCenter.copy(c); gizmoHalf.copy(half); gizmoValid=true;   // 全体枠(groupSelBox)もこのAABBを使う＝矢印と一致
  if(!gizmoMode&&!pasteFollow){ gizmo.visible=false; return; }
  gizmo.visible=true;
  const off=0.05;   // 箱の面にほぼ密着（矢印を箱にくっつける・ヘルバ様指定）
  gizmoHandles.forEach(g=>{ const d=g.userData.arrow;
    g.visible=handleUsable(d,sizeShape);       // 操作できない方向は隠す
    g.userData.cone.visible=!sizeShape;
    g.userData.cube.visible=sizeShape;
    g.position.set(
      c.x+d.dir[0]*(half.x+off),
      c.y+d.dir[1]*(half.y+off),
      c.z+d.dir[2]*(half.z+off)); });
}
// チェーン選択中: 選択箱の上に曲率スライダーを浮かせる（Shift+Alt+ホイールのGUI版＝ヘルバ様指定）
const _ccpEl=document.getElementById('chainCpSlide');
const _ccpSc=_ccpEl&&_ccpEl.querySelector('.scR'), _ccpScV=_ccpEl&&_ccpEl.querySelector('.scV');
const _ccpSq=_ccpEl&&_ccpEl.querySelector('.sqR'), _ccpSqV=_ccpEl&&_ccpEl.querySelector('.sqV');
function updateChainCpSlide(){
  if(!_ccpEl) return;
  const cs=selChains();
  const show=cs.length&&chainSelPart==='child'&&!lightMode&&!box&&!pasteFollow&&gizmoValid;   // 子ノーツで選択した時だけ表示（ヘルバ様指定）。placeMode条件は撤去（常時武装のため）
  if(!show){ if(_ccpEl.style.display!=='none') _ccpEl.style.display='none'; return; }
  const sc=cs[0].sc??5;
  if(document.activeElement!==_ccpSc) _ccpSc.value=Math.max(3,Math.min(12,sc));
  _ccpScV.textContent=String(sc);
  const sq=cs[0].s??1;
  if(document.activeElement!==_ccpSq) _ccpSq.value=Math.max(0.1,Math.min(2,sq));
  _ccpSqV.textContent=(+sq).toFixed(2);
  const p=new THREE.Vector3(gizmoCenter.x, gizmoCenter.y+gizmoHalf.y+0.55, gizmoCenter.z);   // 選択AABB上辺の少し上（0.12は近すぎ=回転でガクつく→0.55へ戻し）
  p.project(camera);
  if(p.z>=1){ _ccpEl.style.display='none'; return; }
  const r=cv.getBoundingClientRect(), mr=mainEl.getBoundingClientRect();
  const sx=(p.x+1)/2*r.width+(r.left-mr.left), sy=(-p.y+1)/2*r.height+(r.top-mr.top);
  _ccpEl.style.display='flex';
  _ccpEl.style.left=Math.round(sx-_ccpEl.offsetWidth/2)+'px';
  _ccpEl.style.top=Math.round(sy-_ccpEl.offsetHeight)+'px';
}
{ // スライダー配線（snapshot=掴んだ時1回・input=即時反映・change=クリップ確定）
  const wire=(rng,apply)=>{ if(!rng) return;
    rng.addEventListener('pointerdown',()=>{ if(selChains().length) snapshot(); });
    rng.addEventListener('input',()=>{ const cs=selChains(); if(!cs.length) return;
      apply(cs,+rng.value);
      _flatDirty=true;
      cs.forEach(c=>refreshMesh(c));
      updateChainOverlay();
      if(typeof refreshChainPanel==='function') refreshChainPanel(); });
    rng.addEventListener('change',()=>{ flushFlatEdits(); metaDirty=true; }); };
  wire(_ccpSc,(cs,val)=>{ const v=Math.max(3,Math.min(12,Math.round(val)));   // スライダー範囲=3〜12（ヘルバ様指定）
    cs.forEach(c=>{ c.sc=v; }); _ccpScV.textContent=String(v); });
  wire(_ccpSq,(cs,val)=>{ const v=Math.max(0.1,Math.min(2,Math.round(val*100)/100));   // squish（実機フィールド）
    cs.forEach(c=>{ c.s=v; }); _ccpSqV.textContent=v.toFixed(2); });
}
// ---- アーク選択中: 選択箱の上に mu/tmu/巻き方向 パネルを浮かせる（チェーンのchainCpSlideと同じ流儀＝ヘルバ様指定） ----
const _aesEl=document.getElementById('arcEditSlide');
const _aesMu=_aesEl&&_aesEl.querySelector('.muR'), _aesMuV=_aesEl&&_aesEl.querySelector('.muV');
const _aesTmu=_aesEl&&_aesEl.querySelector('.tmuR'), _aesTmuV=_aesEl&&_aesEl.querySelector('.tmuV');
const _aesWrapBtn=_aesEl&&_aesEl.querySelector('.mBtn');
const WRAP_LABELS=()=>[t('ui.wrapAuto','自動'),t('ui.wrapCW','時計回り'),t('ui.wrapCCW','反時計回り')];
function updateArcEditSlide(){
  if(!_aesEl) return;
  const as=selArcs();
  const show=as.length&&!lightMode&&!box&&!pasteFollow&&gizmoValid;   // placeMode条件は撤去（常時武装のため）
  if(!show){ if(_aesEl.style.display!=='none') _aesEl.style.display='none'; return; }
  const mu=as[0].mu??1;
  if(document.activeElement!==_aesMu) _aesMu.value=Math.max(0.1,Math.min(3,mu));
  _aesMuV.textContent=(+mu).toFixed(2);
  const tmu=as[0].tmu??1;
  if(document.activeElement!==_aesTmu) _aesTmu.value=Math.max(0.1,Math.min(3,tmu));
  _aesTmuV.textContent=(+tmu).toFixed(2);
  if(_aesWrapBtn) _aesWrapBtn.textContent=WRAP_LABELS()[as[0].m??0];
  const p=new THREE.Vector3(gizmoCenter.x, gizmoCenter.y+gizmoHalf.y+0.55, gizmoCenter.z);
  p.project(camera);
  if(p.z>=1){ _aesEl.style.display='none'; return; }
  const r=cv.getBoundingClientRect(), mr=mainEl.getBoundingClientRect();
  const sx=(p.x+1)/2*r.width+(r.left-mr.left), sy=(-p.y+1)/2*r.height+(r.top-mr.top);
  _aesEl.style.display='flex';
  _aesEl.style.left=Math.round(sx-_aesEl.offsetWidth/2)+'px';
  _aesEl.style.top=Math.round(sy-_aesEl.offsetHeight)+'px';
}
{ const wire=(rng,apply)=>{ if(!rng) return;
    rng.addEventListener('pointerdown',()=>{ if(selArcs().length) snapshot(); });
    rng.addEventListener('input',()=>{ const as=selArcs(); if(!as.length) return;
      apply(as,+rng.value);
      _flatDirty=true;
      as.forEach(a=>{ extendClipForArc(a); refreshMesh(a); });
      updateChainOverlay(); });
    rng.addEventListener('change',()=>{ flushFlatEdits(); metaDirty=true; }); };
  wire(_aesMu,(as,val)=>{ const v=Math.max(0.1,Math.min(10,Math.round(val*100)/100));
    as.forEach(a=>{ a.mu=v; }); _aesMuV.textContent=v.toFixed(2); });
  wire(_aesTmu,(as,val)=>{ const v=Math.max(0.1,Math.min(10,Math.round(val*100)/100));
    as.forEach(a=>{ a.tmu=v; }); _aesTmuV.textContent=v.toFixed(2); });
  if(_aesWrapBtn) _aesWrapBtn.addEventListener('click',()=>{
    const as=selArcs(); if(!as.length) return;
    snapshot();
    as.forEach(a=>{ a.m=((a.m??0)+1)%3; });
    _flatDirty=true; as.forEach(a=>refreshMesh(a));
    _aesWrapBtn.textContent=WRAP_LABELS()[as[0].m??0];
    flushFlatEdits(); metaDirty=true;
    stat(tf('msg.arcWrap','巻き方向: {m}',{m:WRAP_LABELS()[as[0].m??0]}));
  });
}
// そのハンドルで1ステップでも操作できるか
function handleUsable(d,size){
  if(lightMode){   // ライトが動けるのは拍(z)＝画面の縦方向だけ。
    // レーン(x)は出さない＝レーンを跨ぐとet(ライト種別)が変わり L LASER が BACK に化けるため、ドラッグで起こさせない（ヘルバ様指定）。
    // 段(y)はライトに概念が無い。
    if(d.axis!=='z') return false;
    const sel=[...lightSelection].filter(ev=>!lightHiddenEv(ev)&&layerVisible('l',ev._tr||0)&&!objLockedL(ev));
    if(!sel.length) return false;
    for(const ev of sel){ if(d.sign<0&&ev.beat-snap<0) return false; }
    return true;
  }
  if(size){
    const ws=selWalls(); if(!ws.length) return false;
    // 伸ばす or 縮める、どちらかできれば表示
    return ws.some(o=>{
      if(d.axis==='x'){ const grow=d.sign>0? o.x+o.w-1<3 : o.x>0; return grow||o.w>1; }
      if(d.axis==='y'){ if(o.h>3) return false;
        const grow=d.sign>0? o.y+o.h-1<2 : o.y>0; return grow||o.h>1; }
      const grow=d.sign>0? true : o.beat>=snap; return grow||o.dur>snap;
    });
  }
  const sel=movables(); if(!sel.length) return false;
  for(const o of sel){
    if(o.kind==='chain'||o.kind==='arc'){   // チェーン/アーク=頭と尾の両方で判定
      if(d.axis==='x'){ if(o.x+d.sign<0||o.x+d.sign>3||o.tx+d.sign<0||o.tx+d.sign>3) return false; }
      else if(d.axis==='y'){ if(o.y+d.sign<0||o.y+d.sign>2||o.ty+d.sign<0||o.ty+d.sign>2) return false; }
      else { if(d.sign<0&&o.b-snap<0) return false; }
      continue; }
    if(d.axis==='x'){ const nx=o.x+d.sign, wEnd=o.kind==='wall'?o.w-1:0;
      if(nx<0||nx+wEnd>3) return false; }
    else if(d.axis==='y'){
      if(o.kind==='wall'){ if(o.h>3) return false;
        const ny=o.y+d.sign; if(ny<0||ny+o.h-1>2) return false; }
      else { const ny=o.y+d.sign; if(ny<0||ny>2) return false; } }
    else { if(d.sign<0&&o.beat-snap<0) return false; } }
  return true;
}

// レイと軸直線の最近接パラメータ（軸上の距離）
function axisParam(p,ld){
  const rO=raycaster.ray.origin, rD=raycaster.ray.direction;
  const w0=rO.clone().sub(p);
  const a=rD.dot(rD), b=rD.dot(ld), c=ld.dot(ld);
  const d=rD.dot(w0), e=ld.dot(w0);
  const den=a*c-b*b; if(Math.abs(den)<1e-8) return 0;
  return (a*e-b*d)/den;
}

// ---- ハンドルドラッグ（移動 / サイズ） ----
let handleDrag=null;   // {d(axis def), t0, size:boolean, orig:[[obj,{...}]]}
function clipRangeAt(lk,tr,b){   // その拍を含む同レーン（種別付き）のクリップ範囲
  const s=clipSectionAt(lk,tr,b);
  return s?{b0:s.beat||0,b1:(s.beat||0)+(s.len||4),sec:s}:null; }
function clipSectionAt(lk,tr,b){
  return sections.find(s2=>s2.kind!=='null'&&secLk(s2)===lk&&(s2.track||0)===(tr||0)&&b>=(s2.beat||0)-1e-6&&b<(s2.beat||0)+(s2.len||4)-1e-6)||null; }
function beatExtentOf(o){
  if(o.kind==='wall') return {min:o.beat,max:o.beat+(o.dur||snap)};
  if(o.kind==='arc'||o.kind==='chain') return {min:o.b,max:o.tb};
  return {min:o.beat??0,max:o.beat??0}; }
function shiftSectionContentBeats(sec,delta){
  if(!delta||!sec.content) return;
  const slk=secLk(sec), GK={notes:'n',bombs:'n',walls:'n',arcs:'n',chains:'n',lights:'l'};
  for(const key in _LCT){ if(GK[key]!==slk) continue;
    for(const it of (sec.content[key]||[])) for(const f of _LCT[key]) it[f]=(it[f]??0)+delta; } }
function trimSectionStart(sec,newBeat){
  const oldB=sec.beat||0, delta=newBeat-oldB;
  if(Math.abs(delta)<1e-6) return;
  shiftSectionContentBeats(sec,-delta);
  sec.beat=newBeat; sec.len=Math.max(snap,(sec.len||4)-delta); }
function trimSectionEnd(sec,newEnd){
  const b0=sec.beat||0, newLen=Math.max(snap,newEnd-b0);
  if(newLen>=(sec.len||4)-1e-6) return;
  sec.len=newLen; }
function neighborClip(sec,side){
  const tr=sec.track||0, lk=secLk(sec), b0=sec.beat||0, b1=b0+(sec.len||4);
  let best=null, bd=1e9;
  for(const s2 of sections){
    if(s2===sec||s2.kind==='null'||secLk(s2)!==lk||(s2.track||0)!==tr) continue;
    const sb=s2.beat||0, se=sb+(s2.len||4);
    if(side==='l'&&se<=b0+1e-6&&b0-se<bd){ bd=b0-se; best=s2; }
    if(side==='r'&&sb>=b1-1e-6&&sb-b1<bd){ bd=sb-b1; best=s2; } }
  return best; }
function extendClipToFit(sec,minB,maxB){
  if(!sec||sec.kind==='null') return false;
  let changed=false, b0=sec.beat||0, b1=b0+(sec.len||4);
  if(minB<b0-1e-6){
    let newB0=Math.max(0,minB);
    const ln=neighborClip(sec,'l');
    if(ln){ const lnEnd=(ln.beat||0)+(ln.len||4); if(newB0<lnEnd-1e-6) trimSectionEnd(ln,newB0); }
    const delta=b0-newB0;
    if(delta>1e-6){ sec.beat=newB0; sec.len=(sec.len||4)+delta; changed=true; }
  }
  if(maxB>b1-1e-6){
    let newEnd=Math.max(b1,maxB+snap*0.001);
    newEnd=Math.ceil(newEnd/snap)*snap||snap;
    const rn=neighborClip(sec,'r');
    if(rn&&newEnd>(rn.beat||0)+1e-6) trimSectionStart(rn,newEnd);
    const newLen=newEnd-b0;
    if(newLen>(sec.len||4)+1e-6){ sec.len=newLen; changed=true; }
  }
  return changed; }
function extendClipsForObjects(objs,homeMap){
  const groups=new Map();
  for(const o of objs){
    const sec=(homeMap&&homeMap.get(o))||clipSectionAt('n',o._tr,headBeat(o));
    if(!sec) continue;
    const {min,max}=beatExtentOf(o);
    const g=groups.get(sec.id);
    if(!g) groups.set(sec.id,{sec,min,max});
    else{ g.min=Math.min(g.min,min); g.max=Math.max(g.max,max); } }
  let any=false;
  for(const g of groups.values()) if(extendClipToFit(g.sec,g.min,g.max)) any=true;
  if(any){ _flatDirty=true; metaDirty=true; }
  return any; }
function extendClipsForDragOrig(orig){
  const map=new Map(), objs=[];
  for(const [o,o0] of orig){ objs.push(o); if(o0.clipSec) map.set(o,o0.clipSec); }
  return extendClipsForObjects(objs,map); }
function startHandleDrag(d){
  if(lightMode){   // ライト: 対象=選択中のライトイベント。レーン(x)/拍(z)だけを動かす
    const sel=[...lightSelection].filter(ev=>!lightHiddenEv(ev)&&layerVisible('l',ev._tr||0)&&!objLockedL(ev));
    if(!sel.length) return false;
    const ld=new THREE.Vector3(...d.dir), center=gizmoCenter.clone();
    handleDrag={d, ld, t0:axisParam(center,ld), size:false, center, dom:'light', light:true, pre:dumpDomain('light'),
      orig:sel.map(ev=>({ev, beat:ev.beat, lane:laneIdxByType[ev.et]??0, rng:clipRangeAt('l',ev._tr,ev.beat)}))};
    return true;
  }
  const size=gizmoMode==='size'&&selWalls().length>0;
  const targets=size?selWalls():movables();
  if(!targets.length) return false;
  const dom=lightMode?'light':'note';
  const ld=new THREE.Vector3(...d.dir);
  const center=gizmoCenter.clone();            // 基準点はドラッグ開始時に固定
  const t0=axisParam(center,ld);
  handleDrag={d, ld, t0, size, center, dom, pre:dumpDomain(dom),   // 履歴は確定時に「実際に変化した場合だけ」積む
    orig:targets.map(o=>[o,{beat:o.beat,x:o.x,y:o.y,dur:o.dur,w:o.w,h:o.h,b:o.b,tb:o.tb,tx:o.tx,ty:o.ty,   // b/tb/tx/ty=チェーン全体移動用
      rng:clipRangeAt('n',o._tr,headBeat(o)),clipSec:clipSectionAt('n',o._tr,headBeat(o))}])};
  return true;
}
function applyHandleDrag(){
  if(!handleDrag) return;
  const {d,ld,t0,size,center,orig}=handleDrag;
  const t=axisParam(center,ld);
  const unit=d.axis==='x'?LANE:d.axis==='y'?LAYER:snap*ZPB;   // レーン幅はライトも同じ(|LANE_DX|=LANE)
  let steps=Math.round((t-t0)/unit);           // ハンドル外向きが正
  if(handleDrag.light){   // ---- ライト: 拍(z)の移動のみ。レーン(et)はドラッグでは絶対に変えない（handleUsableでz以外は出さない） ----
    let s=steps;
    const ok=k=>orig.every(o=>{
      const nb=o.beat+k*d.sign*snap;   // 拍は元のクリップ範囲内まで（applyLightMoveと同じ規則＝箱の外へ逃がさない）
      return nb>=-1e-9&&(!o.rng||(nb>=o.rng.b0-1e-6&&nb<o.rng.b1-1e-6)); });
    while(s!==0&&!ok(s)) s-=Math.sign(s);
    for(const o of orig) o.ev.beat=Math.max(0,o.beat+s*d.sign*snap);
    lightEvents.sort((a,b)=>a.beat-b.beat);
    _flatDirty=true;
    stat(tf('msg.move','移動: {delta}',{delta:tf('msg.moveBeat','Δ拍 {n}',{n:s*d.sign*snap})}));
    return; }
  if(steps===0){ // 変化なし→元に戻す
    for(const [o,o0] of orig){
      if(o.kind==='chain'||o.kind==='arc'){ o.b=o0.b; o.tb=o0.tb; o.x=o0.x; o.y=o0.y; o.tx=o0.tx; o.ty=o0.ty; refreshMesh(o); continue; }
      o.beat=o0.beat; o.x=o0.x; o.y=o0.y;
      if(o.kind==='wall'){ o.dur=o0.dur; o.w=o0.w; o.h=o0.h; refreshMesh(o); }
      else syncPos(o); }
    return; }
  if(!size){ // ---- 移動 ----
    // barrier: 全員が収まる範囲にクランプ
    let s=steps;
    const ok=(k)=>{ for(const [o,o0] of orig){
      if(o.kind==='chain'||o.kind==='arc'){   // チェーン/アーク=頭と尾の両方が盤内・拍0以上
        const dx=d.axis==='x'?k*d.sign:0, dy=d.axis==='y'?k*d.sign:0, db=d.axis==='z'?k*d.sign*snap:0;
        if(o0.x+dx<0||o0.x+dx>3||o0.tx+dx<0||o0.tx+dx>3) return false;
        if(o0.y+dy<0||o0.y+dy>2||o0.ty+dy<0||o0.ty+dy>2) return false;
        if(o0.b+db<0) return false; continue; }
      const nx=o0.x+(d.axis==='x'?k*d.sign:0);
      const ny=o0.y+(d.axis==='y'?k*d.sign:0);
      const nb=o0.beat+(d.axis==='z'?k*d.sign*snap:0);
      const wEnd=o.kind==='wall'?o.w-1:0;
      const hEnd=o.kind==='wall'?Math.min(o.h,3-o0.y)-1:0;
      if(nx<0||nx+wEnd>3) return false;
      if(o.kind!=='wall'&&(ny<0||ny>2)) return false;
      if(o.kind==='wall'&&d.axis==='y'&&(o.h>3||ny<0||ny+hEnd>2)) return false;
      if(nb<0) return false; } return true; };
    while(s!==0&&!ok(s)) s-=Math.sign(s);
    for(const [o,o0] of orig){
      if(o.kind==='chain'||o.kind==='arc'){   // チェーン/アーク=頭・尾を同じ量だけ平行移動
        const dx=d.axis==='x'?s*d.sign:0, dy=d.axis==='y'?s*d.sign:0, db=d.axis==='z'?s*d.sign*snap:0;
        o.x=o0.x+dx; o.tx=o0.tx+dx; o.y=o0.y+dy; o.ty=o0.ty+dy; o.b=o0.b+db; o.tb=o0.tb+db;
        refreshMesh(o); continue; }
      o.x=o0.x+(d.axis==='x'?s*d.sign:0);
      if(o.kind!=='wall'||d.axis==='y') o.y=o0.y+(d.axis==='y'&&(o.kind!=='wall'||o.h<=3)?s*d.sign:0);
      o.beat=o0.beat+(d.axis==='z'?s*d.sign*snap:0);
      if(o.kind==='wall') refreshMesh(o); else syncPos(o); }
    extendClipsForDragOrig(orig);
    stat(tf('msg.move','移動: {delta}',{delta:d.axis==='z'?tf('msg.moveBeat','Δ拍 {n}',{n:s*d.sign*snap}):d.axis==='x'?tf('msg.moveCol','Δ列 {n}',{n:s*d.sign}):tf('msg.moveRow','Δ段 {n}',{n:s*d.sign})}));
  } else { // ---- サイズ（壁のみ）: 引いた側の面が動く ----
    for(const [o,o0] of orig){
      if(d.axis==='z'){
        if(d.sign>0){ o.dur=Math.max(snap,o0.dur+steps*snap); }
        else { const end=o0.beat+o0.dur;
          const nb=Math.max(0,Math.min(o0.beat-steps*snap,end-snap)); o.beat=nb; o.dur=end-nb; }
      } else if(d.axis==='x'){
        if(d.sign>0){ o.w=Math.max(1,Math.min(o0.w+steps,4-o0.x)); }
        else { const x1=o0.x+o0.w-1;
          const nx=Math.max(0,Math.min(o0.x-steps,x1)); o.x=nx; o.w=x1-nx+1; }
      } else { if(o0.h>3) continue;      // 全高壁は縦サイズ変更不可
        if(d.sign>0){ o.h=Math.max(1,Math.min(o0.h+steps,3-o0.y)); }
        else { const y1=o0.y+o0.h-1;
          const ny=Math.max(0,Math.min(o0.y-steps,y1)); o.y=ny; o.h=y1-ny+1; }
      }
      refreshMesh(o); }
    extendClipsForDragOrig(orig);
    stat(tf('msg.resize','サイズ変更: {axis} {sign}{steps}',{axis:d.axis,sign:steps>0?'+':'',steps}));
  }
}
function endHandleDrag(){ if(handleDrag){ const {orig,pre,dom,light}=handleDrag;
    const changed=light
      ? orig.some(o=>o.ev.beat!==o.beat||(laneIdxByType[o.ev.et]??0)!==o.lane)
      : orig.some(([o,o0])=>['beat','x','y','dur','w','h','b','tb','tx','ty'].some(f=>o[f]!==o0[f]));
    if(changed){ pushHist(dom,pre); flushFlatEdits(); metaDirty=true; }
    if(!light&&pasteFollow) syncPasteFollowOffsets(); }
  handleDrag=null; }

// ---- ギズモモード ----
// 配置済みをクリックで選択＝'move'（矢印ハンドル）が自動で出る。S=壁のサイズハンドル。Escで解除。
// ※toggleMoveMode(G=移動モードの手動トグル)は撤去（2026-07-17）。Gの割当は以前に廃止済みで呼び出し元ゼロ、
//   かつ「選択しただけでは何も出さない」という前提自体が現行仕様（選択でギズモが出る）と食い違っていた
let gizmoMode=null;    // null | 'move' | 'size'
function toggleSizeMode(){
  if(gizmoMode==='size'){ gizmoMode=null; stat('サイズモード OFF'); return; }
  if(!selWalls().length){ stat('S: 壁を選択してから'); return; }
  if(placeMode) setPlaceMode(false);
  gizmoMode='size'; stat('サイズモード（四角ハンドルをドラッグ / Esc解除）'); }

function movables(){ return [...selection].filter(o=>o.kind==='note'||o.kind==='bomb'||o.kind==='wall'||o.kind==='chain'||o.kind==='arc'); }   // チェーン/アークも全体移動可（ヘルバ様指定）

// ---- pie menu ----
const pieEl=document.getElementById('pie');
let pieOpen=false, pieItems=[], pieDefs=[], pieHot=-1, pieKey=null, pieOnCommit=null, lastMouse={x:300,y:300};
let pieCX=0,pieCY=0;
addEventListener('pointermove', e=>{ const p={x:e.clientX,y:e.clientY}; lastMouse=p;   // パイはfixed=viewport座標（全ペイン共通）
  if(pieOpen){ const dx=p.x-pieCX, dy=p.y-pieCY, dist=Math.hypot(dx,dy);
    const centerIdx=pieDefs.findIndex(d=>d.center);
    if(dist<=22){ if(centerIdx>=0) pieHot=centerIdx; }
    else { const a=(Math.atan2(dy,dx)*180/Math.PI+450)%360;
      let best=-1,bd=1e9; pieDefs.forEach((d,i)=>{ if(d.center)return;
        let diff=Math.abs(a-d.angle); if(diff>180)diff=360-diff; if(diff<bd){bd=diff;best=i;} });
      pieHot=best; }
    pieItems.forEach((el,i)=>el.classList.toggle('hot',i===pieHot)); }
});
function openPie(defs,currentVal,onCommit,key){ pieOpen=true; pieHot=-1; pieKey=key; pieOnCommit=onCommit; pieDefs=defs;
  pieEl.style.display='block'; pieCX=lastMouse.x; pieCY=lastMouse.y;
  pieEl.style.left=pieCX+'px'; pieEl.style.top=pieCY+'px';
  pieEl.querySelectorAll('.pieitem').forEach(el=>el.remove()); pieItems=[];
  const R=86;
  defs.forEach((d,i)=>{ const el=document.createElement('div'); el.className='pieitem';
    if(d.color){ el.classList.add('piecolor'); el.style.background=d.color; el.title=d.color; if(d.label) el.innerHTML=`<span>${d.label}</span>`; }   // 色スウォッチのパイ（ライトCパイ等・ヘルバ様指定）
    else if(d.icon){ el.classList.add('pieicon'); el.innerHTML=(TB_ICONS[d.icon]||'')+(d.label?`<span>${d.label}</span>`:''); }   // アイコン付きパイ（配置モード等）
    else el.textContent=d.label;
    if(d.center){ el.style.left='0px'; el.style.top='0px'; }
    else { const a=(d.angle-90)*Math.PI/180; el.style.left=Math.cos(a)*R+'px'; el.style.top=Math.sin(a)*R+'px'; }
    if(d.val===currentVal){ el.classList.add('hot'); pieHot=i; }
    pieEl.appendChild(el); pieItems.push(el); });
}
function closePie(commit){ if(commit&&pieHot>=0&&pieOnCommit) pieOnCommit(pieDefs[pieHot].val);
  pieOpen=false; pieKey=null; pieEl.style.display='none'; }
function confirmPasteFollow(){
  if(!pasteFollow) return;
  setFollowGhost(pasteFollow.items.map(it=>it.o),false);
  pasteFollow=null; pasteFloorClick=false;
  _flatDirty=true; flushFlatEdits();
  metaDirty=true;
  stat(tf('msg.pasteConfirm','貼り付け位置を確定しました'));
}
// ペースト追従の取消（Esc／3Dビューの右クリック共用）。貼り付けた実体ごと消す＝NLE側 cancelLayerPaste と同じ流儀
function cancelPasteFollow(){
  if(!pasteFollow) return false;
  pasteFloorClick=false;
  for(const it of pasteFollow.items) removeObj(it.o);
  pasteFollow=null; selection.clear();
  stat('貼り付けを取り消しました');
  return true;
}
function syncPasteFollowOffsets(){
  if(!pasteFollow||!pasteFollow.items.length) return;
  const anchor=pasteFollow.items.reduce((a,it)=>headBeat(it.o)<headBeat(a.o)?it:a).o;
  const ax=anchor.x, ay=anchor.y, at=headBeat(anchor);
  pasteFollow.ax=ax; pasteFollow.ay=ay; pasteFollow.at=at;
  for(const it of pasteFollow.items){
    const o=it.o;
    it.rel=headBeat(o)-at;
    it.relX=o.x-ax; it.relY=o.y-ay;
    if(o.kind==='arc'||o.kind==='chain'){ it.relT=o.tb-at; it.relTx=o.tx-ax; it.relTy=o.ty-ay; }
  }
}
function applyPasteFollowPosition(ax, ay, at){
  if(!pasteFollow) return false;
  const at2=Math.max(0,snapV(at));
  if(at2===pasteFollow.at&&ax===pasteFollow.ax&&ay===pasteFollow.ay) return false;
  pasteFollow.at=at2; pasteFollow.ax=ax; pasteFollow.ay=ay;
  for(const it of pasteFollow.items){
    const o=it.o;
    o.x=ax+it.relX; o.y=ay+it.relY;
    if(o.kind==='arc'||o.kind==='chain'){
      o.b=at2+it.rel; o.tb=at2+it.relT; o.tx=ax+it.relTx; o.ty=ay+it.relTy;
      refreshMesh(o);
    } else {
      o.beat=at2+it.rel;
      if(o.kind==='wall') refreshMesh(o); else syncPos(o);
    }
  }
  _flatDirty=true;
  const map=new Map(pasteFollow.items.map(it=>[it.o,it.clipSec||clipSectionAt('n',it.o._tr,headBeat(it.o))]));
  extendClipsForObjects(pasteFollow.items.map(it=>it.o),map);
  return true;
}
function hoverGridCell(){
  if(lightMode) return null;
  // ノーツとライトはワールド座標上で重なっているため、モードで拾う対象を必ず分ける（2026-07-18の表示改修）。
  const cHit=raycaster.intersectObjects(cellPlanes)[0];
  return cHit?cHit.object.userData:null;
}
const snapPieDefs=snapVals.map(([v,l],i)=>({label:l,val:v,angle:i*(360/snapVals.length)}));
// 配置モードのパイ（W長押し）: セレクト/ノーツ/ボム/壁（ヘルバ様指定・N/B/W単体ショートカットの置き換え）
// ※アイコンの先読みは TB_ICONS 定義後（下部）で行う＝ここで tbIcon を呼ぶと const TB_ICONS のTDZで失敗する
// セレクト枠は廃止（ヘルバ様指定）。ノーツを頂点(0°)に置き、時計回りに ノーツ→ボム→壁（ライトパイと同じ流儀・ヘルバ様指定 2026-07-18）
function placeModePieDefs(){ return [
  {label:t('pie.note','ノーツ'),   val:'note',   icon:'note',   angle:0},     // 上
  {label:t('pie.bomb','ボム'),     val:'bomb',   icon:'bomb',   angle:120},
  {label:t('pie.wall','壁'),       val:'wall',   icon:'wall',   angle:240},
]; }
function placeModeCurVal(){ return placeMode?brush.type:null; }   // 現在の配置状態（ハイライト用）
function commitPlaceModePie(val){
  setPlaceMode(true); setBrushType(val);   // setPlaceMode(true)は既ONならno-op・setBrushTypeで種別確定
}
function openPlaceModePie(){ if(!pieOpen) openPie(placeModePieDefs(),placeModeCurVal(),commitPlaceModePie,'w'); }
// ライトモードのパイ（W）: 選択/ON/OFF/フラッシュ/フェード/トランジション（ノーツのW配置パイのライト版・ヘルバ様指定 2026-07-13）
// セレクト枠は廃止（ヘルバ様指定）。オフを頂点(0°)に置き、時計回りに オフ→ライト→フラッシュ→フェード→トランジション
// ＝ツールバーの並びと一致させる（ヘルバ様指定 2026-07-18）
function lightPieDefs(){ return [
  {label:t('pie.lOff','オフ'),             val:0,        icon:'light_off',        angle:0},     // 上
  {label:t('pie.lOn','ライト'),            val:1,        icon:'light_on',         angle:72},
  {label:t('pie.lFlash','フラッシュ'),     val:2,        icon:'light_flash',      angle:144},
  {label:t('pie.lFade','フェード'),        val:3,        icon:'light_fade',       angle:216},
  {label:t('pie.lTrans','トランジション'),  val:4,        icon:'light_transition', angle:288},
]; }
function lightPieCurVal(){ return lightBrush.behav; }   // 現在の武装状態（ハイライト用）
function commitLightPie(val){
  setLightBehav(val); stat(tf('msg.lightBehav','ライト動作: {behav}',{behav:L_BEHAV_N[val]}));
}
function openLightPie(){ if(!pieOpen) openPie(lightPieDefs(),lightPieCurVal(),commitLightPie,'w'); }
document.addEventListener('pointerdown', e=>{ if(pieOpen){ e.stopPropagation(); e.preventDefault(); closePie(true); } }, true);
function setFollowGhost(objs,on){   // ペースト追従中(配置前)=半透明ゴースト。ノーツ本体は描画ループのフックで、他種はマテリアル差し替えで
  for(const o of objs){ if(!o) continue; o._ghost=on;
    if(o.kind==='note') continue;   // ノーツ本体は毎フレーム再設定されるため描画ループ側(o._ghost)で処理
    const m=meshes.find(x=>x.obj===o); if(!m) continue;
    m.group.traverse(c=>{ if(!c.isMesh) return;
      if(on){ if(!c.userData._gm){ c.userData._gm=c.material; c.material=c.material.clone(); c.material.transparent=true; c.material.opacity=0.3; c.material.depthWrite=false; } }
      else if(c.userData._gm){ c.material=c.userData._gm; c.userData._gm=null; } }); }
}

// ---- 3D編集のコピー&ペースト（Ctrl+C / Ctrl+V・再生ヘッドへ相対配置） ----
let clip3D=null;
function copySel3D(){
  if(lightMode){
    if(!lightSelection.size){ stat('コピー: ライトを選択してください'); return; }
    const evs=[...lightSelection]; const b0=Math.min(...evs.map(v=>v.beat));
    clip3D={kind:'light',evs:evs.map(v=>({beat:v.beat-b0,et:v.et,i:v.i,f:v.f,chroma:getLightChroma(v),_tr:v._tr??0}))};
    stat(tf('msg.copyLights','コピー: ライト {n}件',{n:evs.length}));
  } else {
    if(!selection.size){ stat('コピー: オブジェクトを選択してください'); return; }
    const objs=[...selection]; const b0=Math.min(...objs.map(headBeat));
    clip3D={kind:'obj',objs:objs.map(o=>{
      const c=JSON.parse(JSON.stringify({...o,raw:null}));
      if(o.kind==='arc'||o.kind==='chain'){ c.b=o.b-b0; c.tb=o.tb-b0; } else c.beat=o.beat-b0;
      return c; })};
    stat(tf('msg.copyObjs','コピー: {n}オブジェクト',{n:objs.length}));
  }
}
let pasteFollow=null;   // 貼り付け後のマウス追従 {at,ax,ay,items:[{o,rel,relT,relX,relY,relTx?,relTy?}]}
let pasteFloorClick=false;
function pasteSel3D(){
  if(!clip3D){ stat('貼り付ける内容がありません（Ctrl+Cでコピー）'); return; }
  if(pasteFollow){ setFollowGhost(pasteFollow.items.map(it=>it.o),false); pasteFollow=null; }   // 連続ペーストは前のを確定扱い（前バッチの半透明を戻す）
  snapshot(clip3D.kind==='light'?'light':'note');
  // 選択中のNLEクリップ（1個・種別一致）があれば、そのクリップへ放り込む（ヘルバ様指定＝別クリップへ移す手段）
  const selSec=(lk)=>{ if(layerSel.size!==1) return null;
    const s=sections.find(s2=>layerSel.has(s2.id));
    return (s&&s.kind!=='null'&&secLk(s)===lk)?s:null; };
  if(clip3D.kind==='light'){
    const tSec=selSec('l');
    const at=snapV(lightHover?lightHover.beat:cur);
    const added=clip3D.evs.map(v=>{ const beat=v.beat+at;
      const tr=tSec?(tSec.track||0):pasteTrackFor(beat,'l',v._tr);   // クリップ未選択時: 元トラックがロック中なら空きへ自動回避（新規クリップ作成もあり得る）
      const nv={beat,et:v.et,i:v.i,f:v.f,raw:null,_tr:tr};
      if(v.chroma) setLightChroma(nv,v.chroma); return nv; });
    lightEvents.push(...added); lightEvents.sort((a,b2)=>a.beat-b2.beat);
    if(tSec){ const mn=Math.min(...added.map(v=>v.beat)), mx=Math.max(...added.map(v=>v.beat));
      extendClipToFit(tSec,mn,mx); _flatDirty=true; metaDirty=true;
      stat(tf('msg.pasteIntoClip','クリップ「{label}」へ貼り付け',{label:tSec.label||'Sheet'})); }
    lightSelection.clear(); added.forEach(v=>lightSelection.add(v));
    if(lightMode&&lightHover){                             // そのままマウス追従（クリック確定/Esc取消）
      lightMove={b0:lightHover.beat, l0:lightHover.lane, pasted:added.slice(),   // pasted=この追従が貼り付け由来＝取消では実体ごと消す（ヘルバ様指定 2026-07-18）
        orig:added.map(ev=>({ev,beat:ev.beat,lane:laneIdxByType[ev.et]??0}))};
      stat(tf('msg.pasteLightsFollow','ライト {n}件を貼り付け — マウスで位置決め → クリックで確定 / 右クリック・Escで取消',{n:added.length}));
    } else stat(tf('msg.pasteLightsAt','ライト {n}件を拍{at}へ貼り付けました',{n:added.length,at}));
  } else {
    const tSec=selSec('n');
    const at=Math.max(0,snapV(hoverBeat!=null?hoverBeat:cur));
    const added=[];
    for(const c0 of clip3D.objs){
      const o=JSON.parse(JSON.stringify(c0));
      if(o.kind==='arc'||o.kind==='chain'){ o.b+=at; o.tb+=at; } else o.beat+=at;
      if(tSec) o._tr=tSec.track||0;   // 選択中クリップのレーンへ所属替え
      else o._tr=pasteTrackFor(headBeat(o),'n',o._tr);   // クリップ未選択時: 元トラックがロック中なら空きへ自動回避（新規クリップ作成もあり得る）
      arrOf(o.kind).push(o); addObj(o); added.push(o);
    }
    selection=new Set(added);
    const anchor=added.reduce((a,o)=>headBeat(o)<headBeat(a)?o:a);
    const ax=anchor.x, ay=anchor.y;
    pasteFollow={at,ax,ay,items:added.map(o=>({o,
      rel:headBeat(o)-at,
      relT:(o.kind==='arc'||o.kind==='chain')?o.tb-at:0,
      relX:o.x-ax, relY:o.y-ay,
      relTx:(o.kind==='arc'||o.kind==='chain')?o.tx-ax:0,
      relTy:(o.kind==='arc'||o.kind==='chain')?o.ty-ay:0,
      clipSec:tSec||clipSectionAt('n',o._tr,headBeat(o))}))};   // 確定/移動時のクリップ拡張先も選択クリップに固定
    if(tSec) extendClipsForObjects(added, new Map(added.map(o=>[o,tSec])));   // 置いた位置がクリップ外ならその場で拡張
    gizmoMode='move';
    setFollowGhost(added,true);
    stat(tSec
      ? tf('msg.pasteObjsIntoClip','{n}オブジェクトをクリップ「{label}」へ貼り付け — 移動 → 床クリック or Enterで確定 / Esc取消',{n:added.length,label:tSec.label||'Sheet'})
      : tf('msg.pasteObjsFollow','{n}オブジェクトを貼り付け — ギズモ/マウスで移動 → 床クリック or Enterで確定 / Esc取消',{n:added.length}));
  }
  metaDirty=true;
}
// Ctrl+X=カット（コピー＋削除・1操作扱い）。lightMode中はライト、それ以外はノーツ/壁/アーク/チェーンを対象（Ctrl+C/Vと同じ切替）
function cutSel3D(){
  if(lightMode){
    if(!lightSelection.size){ stat('カットするライトを選択してください'); return; }
    copySel3D();
    const c=lightSelection.size;
    snapshot();
    lightEvents=lightEvents.filter(ev=>!lightSelection.has(ev));
    lightSelection.clear(); _flatDirty=true; metaDirty=true;
    stat(tf('msg.lightCutN','ライトをカット ×{n}（Ctrl+Vで貼り付け）',{n:c}));
  } else {
    if(!selection.size){ stat('カットするオブジェクトを選択してください'); return; }
    copySel3D();
    const c=selection.size;
    snapshot();
    [...selection].forEach(o=>removeObj(o));
    selection.clear(); metaDirty=true;
    stat(tf('msg.cutN','カット ×{n}（Ctrl+Vで貼り付け）',{n:c}));
  }
}
// ---- arc / chain 作成（ChroMapper ArcPlacement / ChainPlacement 準拠） ----
function isColorNote(o){ return o&&o.kind==='note'; }
function createArcData(head, tail){
  let h=head, t=tail;
  if(h.beat>t.beat) [h,t]=[t,h];
  return { kind:'arc', b:h.beat, c:h.c, x:h.x, y:h.y, d:h.d, mu:1,
    tb:t.beat, tx:t.x, ty:t.y, tc:t.d, tmu:1, m:0, _tr:h._tr??0, raw:null };
}
function spawnArcsFromSelection(){
  const sel=[...selection].filter(isColorNote);
  sel.sort((a,b)=>a.beat-b.beat||a.y-b.y||a.x-b.x);
  if(!diffV3&&sel.length>1){ showErr(tf('m:アーク: このマップはv2形式のため非対応です','アーク: このマップはv2形式のため非対応です')); return 0; }
  if(sel.length<2){ showErr(tf('m:アーク: ノーツを2個以上選択してから実行してください（Ctrl+R）','アーク: ノーツを2個以上選択してから実行してください（Ctrl+R）')); return 0; }
  const reds=sel.filter(n=>n.c===0), blues=sel.filter(n=>n.c===1);
  const generated=[];
  for(const group of [reds,blues]){
    for(let i=1;i<group.length;i++){ generated.push(createArcData(group[i-1], group[i])); }
  }
  if(!generated.length){
    showErr(tf('m:アーク: 作成できるペアがありません（同色2個以上）','アーク: 作成できるペアがありません（同色2個以上）'));
    return 0;
  }
  snapshot();
  // 実機準拠: アークは「実在する2ノーツを繋ぐガイド」＝頭も尾もノーツはそのまま残す
  // （旧実装は尾ノーツをremoveObjで消費→「アークを作ると後ろのノーツが消える」バグ＝ヘルバ様報告）
  for(const a of generated) arcs.push(a);
  selection=new Set(generated);
  gizmoMode='move';
  rebuild();
  alignNoteGroupTracks(generated);
  _flatDirty=true; flushFlatEdits();
  stat(generated.length===1
    ? tf('m:アーク作成','アーク作成')
    : tf('m:アークを{n}個作成','アークを{n}個作成',{n:generated.length}));
  metaDirty=true;
  return generated.length;
}
function createArc(){ spawnArcsFromSelection(); }
function tryCreateChainData(head, tail){
  let h=head, t=tail;
  if(h.beat>t.beat) [h,t]=[t,h];
  if(h.d===8) return null;
  return { kind:'chain', b:h.beat, c:h.c, x:h.x, y:h.y, d:h.d,
    tb:t.beat, tx:t.x, ty:t.y, sc:5, s:1, _tr:h._tr??0, raw:null };
}
function spawnChainFromSelection(){
  const sel=[...selection].filter(isColorNote);
  sel.sort((a,b)=>a.beat-b.beat||a.y-b.y||a.x-b.x);
  if(!diffV3&&sel.length){ showErr(tf('m:チェーン: このマップはv2形式のため非対応です','チェーン: このマップはv2形式のため非対応です')); return 0; }
  // 1個変換は廃止＝同色ノーツ2個以上を選択して初めてチェーン化（ヘルバ様指定・2026-07-13）
  if(sel.length<2){ showErr(tf('m:チェーン: 同色ノーツを2個以上選択してください（Ctrl+T）','チェーン: 同色ノーツを2個以上選択してください（Ctrl+T）')); return 0; }
  const reds=sel.filter(n=>n.c===0), blues=sel.filter(n=>n.c===1);
  const generated=[], used=new Set();   // used=チェーンへ変換されて消費されるノーツ（頭・尾とも。幽霊ノーツ制度は廃止＝ヘルバ様指示）
  // 頭/尾の判別: 拍が違えば早い方が頭。同拍なら「矢印が相手を向いている方」が頭（実機の作法＝チェーンは頭の切る方向へ流れる。ヘルバ様指定）
  const orderChainPair=(a,b)=>{
    if(Math.abs((a.beat||0)-(b.beat||0))>1e-4) return a.beat<b.beat?[a,b]:[b,a];
    const score=(h,t)=>{ if(h.d===8) return -1e9;   // ドットは頭になれない
      const v=DIRV[h.d]||[0,0], dx=t.x-h.x, dy=t.y-h.y, len=Math.hypot(dx,dy)||1;
      return (v[0]*dx+v[1]*dy)/len; };   // 矢印方向と相手方向の一致度（cos）
    return score(a,b)>=score(b,a)?[a,b]:[b,a];
  };
  for(const group of [reds,blues]){
    for(let i=1;i<group.length;i++){
      const [h,t]=orderChainPair(group[i-1], group[i]);
      const chain=tryCreateChainData(h,t);
      if(chain){ generated.push(chain); used.add(h); used.add(t); }
    }
  }
  if(!generated.length){
    showErr(tf('m:チェーン: 作成できるペアがありません（同色2個以上・頭は●不可）','チェーン: 作成できるペアがありません（同色2個以上・頭は●不可）'));
    return 0;
  }
  snapshot();
  for(const n of used) removeObj(n);   // 選択ノーツをチェーンの頭/尾へ「変換」＝元ノーツは削除（隠して残さない）
  for(const c of generated) chains.push(c);
  selection=new Set(generated);
  chainSelPart='head'; gizmoMode='move';   // 作成直後=頭扱い（緑枠+全体移動）
  rebuild();
  alignNoteGroupTracks(generated);
  _flatDirty=true; flushFlatEdits();   // 作成直後にクリップへ反映（保存前に消えないように）
  stat(generated.length===1
    ? tf('m:チェーン作成','チェーン作成')
    : tf('m:チェーンを{n}個作成','チェーンを{n}個作成',{n:generated.length}));
  if(generated.length===1) stat(tf('msg.chainEdit','チェーン: 頭ノーツ=XYZ 向き(黄)=XY 尾ノーツ=XYZ'));
  metaDirty=true;
  return generated.length;
}
function createChain(){ spawnChainFromSelection(); }

function selChains(){ return [...selection].filter(o=>o.kind==='chain'); }
function selArcs(){ return [...selection].filter(o=>o.kind==='arc'); }
function syncGizmoForSelection(){
  const cs=selChains();
  // 範囲選択・ジャンプ等の経由は「頭で選択した」扱い（緑枠+全体移動ギズモ。子扱い=青枠+スライダーはクリック時のみ）
  chainSelPart='head';
  gizmoMode=selection.size?'move':null;
  if(cs.length===1&&cs.length===selection.size) stat(tf('msg.chainEdit','チェーン: 頭ノーツ=XYZ 向き(黄)=XY 尾ノーツ=XYZ / 外枠矢印=全体移動'));
}
function tweakSelArcs(mut, msg){
  const as=selArcs(); if(!as.length) return false;
  snapshot();
  as.forEach(mut);
  _flatDirty=true; flushFlatEdits();
  as.forEach(a=>{ extendClipForArc(a); refreshMesh(a); });
  metaDirty=true;
  if(msg) stat(msg);
  refreshArcPanel();
  return true;
}
function refreshArcPanel(){}   // 上部バーのアーク設定群は撤去済み（調整=選択箱上のarcEditSlideパネル＋ホイールに集約。チェーンと同じ流儀）
function tweakSelChains(mut, msg){
  const cs=selChains(); if(!cs.length) return false;
  snapshot();
  cs.forEach(mut);
  _flatDirty=true; flushFlatEdits();
  cs.forEach(c=>refreshMesh(c));
  metaDirty=true;
  if(msg) stat(msg);
  refreshChainPanel();
  updateChainOverlay();
  return true;
}
function refreshChainPanel(){}   // 上部バーのチェーン設定群は撤去済み（調整=選択箱上のスライダー＋ホイールに集約）

// タイムライン末尾拍: 曲(ovBeats)＋クリップ/ノーツ/ライトの最遠端。曲が無くてもNLEの内容で「曲末へ」が効く
function timelineEndBeat(){
  let end=ovBeats||0;
  for(const s of sections) end=Math.max(end,(s.beat||0)+(s.len||0));
  for(const n of notes) end=Math.max(end,n.beat||0);
  for(const e of lightEvents) end=Math.max(end,e.beat||0);
  return end;
}

// ---- keys ----
// 画面上ではブラウザのショートカットを抑止（リロード/保存/印刷/検索/ブックマーク/ダウンロード/ソース表示/Ctrl+数字のタブ切替）。exe化までの暫定。
// ※Ctrl+T(新規タブ)/Ctrl+N/Ctrl+W はブラウザ予約で、webページからは preventDefault できない（Chrome仕様）＝抑止不可。
addEventListener('keydown', e=>{
  if(!(e.ctrlKey||e.metaKey)||e.altKey) return;
  const tag=(e.target&&e.target.tagName)||''; if(/^(INPUT|TEXTAREA|SELECT)$/.test(tag)) return;   // 入力欄はコピペ等を通す
  const k=(e.key||'').toLowerCase();
  if('rspdfgjou'.includes(k)||/^[0-9]$/.test(k)) e.preventDefault();   // アプリ側の処理(伝播)は止めない＝ブラウザ既定動作のみ抑止
}, true);
addEventListener('keydown', e=>{
  if(e.target&&/^(INPUT|TEXTAREA|SELECT)$/.test(e.target.tagName||'')){   // フォーム入力中はショートカット無効
    if(e.key==='Escape'||e.key==='Tab') e.target.blur();
    if(e.key==='Tab') e.preventDefault();
    return; }
  if(e.key==='Tab') closeFloatUI();   // Tabのモード切替時、浮いているメニュー/カラーピッカーを閉じる（どの分岐でも）
  // ---- タイムライン再生系（全画面共通・どのペインにマウスがあっても効く） ----
  if(hit(e,'play')){ e.preventDefault(); playing?pause():play(); return; }   // Phase2: 実効バインドで判定（再割当対応）
  { const _mp=hit(e,'markerPrev'), _mn=hit(e,'markerNext'); if(_mp||_mn){ e.preventDefault(); if(!e.repeat) jumpMarker(_mp?-1:1); return; } }   // 前/次のマーカーへ（全画面共通）
  if(/^[1-5]$/.test(e.key)&&!e.ctrlKey&&!e.altKey&&!e.shiftKey&&!(lightMode&&hoverPane==='main')){   // 1〜5=難易度切替（LIGHTモードの3D上では1・2・3=色選択を優先）
    if(!e.repeat) switchDiffByIndex(+e.key-1); return; }
  { const _js=hit(e,'jumpStart'), _je=hit(e,'jumpEnd'), _fp=hit(e,'framePrev'), _fn=hit(e,'frameNext');
    const _ease4=(e.ctrlKey&&e.shiftKey&&(e.key==='ArrowLeft'||e.key==='ArrowRight'));   // 未登録=Shift+Ctrl+←/→=4拍イージング
    if(_js||_je||_fp||_fn||_ease4){ e.preventDefault(); if(playing) pause();
      if(_ease4){ const dir=e.key==='ArrowRight'?1:-1; seekEase(Math.max(0,cur+dir*4)); return; }   // Shift+Ctrl+←/→=4拍・イージング
      if(_js||_je){ const dir=_je?1:-1; const tgt=dir<0?0:timelineEndBeat();                        // スタート/末尾へ（曲無しでもNLEクリップ末尾へ・窓もスクロール）
        if(!e.repeat&&(dir<0||tgt>0)){ seekEase(tgt); tlViewB0=null; tlB0=Math.max(0,tgt-tlSpan*0.5); } return; }
      const dir=_fn?1:-1; cur=Math.max(0,snapV(cur+dir*snap)); offset=beatToTimeTM(cur); return; }        // 素の←/→=スナップ幅・即時
  }
  // F=色の巡回/反転は「ブラシの色」を変える操作＝どのペインにマウスがあっても効かせる（全画面共通）。
  // 下のNODE分岐より前に置く＝NLE/INFO上にマウスがあると効かなかった（ヘルバ様報告「Fがちょこちょこ効かない」2026-07-18）。
  // マウス下オブジェクトへの適用は3Dビューにマウスがある時だけ＝NLE上では常にブラシ色のみを変える
  if(lightMode&&hit(e,'lightCycle')){ if(!e.repeat){ if(chromaMode) cycleLightChroma(); else cycleLightBase(); } return; }
  if(!lightMode&&hit(e,'noteFlip')){ if(!e.repeat){
      const o=objUnder();   // NLE上等マウス位置が無い/拾えない時はnull（objUnderは直近のpointer位置で判定）
      // カーソル直下が選択中のノーツ/アーク/チェーンの時だけ選択全体の色を反転＝回転(Alt+ホイール)と同じ統一ルール（ヘルバ様指定 2026-09-22）。
      // それ以外（空き地・未選択・色を持たないオブジェクト・配置モード中の巻き込み）は従来通りブラシ色だけを反転
      const targets = (o&&o.c!=null&&(o.kind==='note'||o.kind==='arc'||o.kind==='chain')&&selection.has(o))
        ? [...selection].filter(x=>x.c!=null&&(x.kind==='note'||x.kind==='arc'||x.kind==='chain')) : [];
      if(targets.length){ snapshot();
        targets.forEach(n=>{ n.c=(n.c===0?1:0); refreshMesh(n); if(n.kind==='note') recolorLinkedSliders(n); });
        brush.c=targets[targets.length-1].c; setColor(brush.c,false);
        metaDirty=true;
        stat('ノーツの色を反転しました'+(targets.length>1?` ×${targets.length}`:'')); }
      else if(o&&o.c==null) stat('F: このオブジェクトに色はありません');
      else setColor(brush.c===0?1:0,false); } return; }
  if(hoverPane==='node'){                                                 // NODEペイン専用キー（NOTES系はここで遮断）
    if(nodeColMode==='info'){                                             // INFOノード画面のキー（NLEのクリップ操作はここで遮断）
      { const _sa=hit(e,'saveAs'),_sv=hit(e,'save'); if(_sa||_sv){ e.preventDefault(); saveProject(_sa); return; } }
      if(hit(e,'open')){ e.preventDefault(); openProjectFile(); return; }
      { const _rd=hit(e,'redo'),_un=hit(e,'undo'); if(_rd||_un){ e.preventDefault(); _rd?redo():undo(); return; } }
      if(hit(e,'deselect')){ e.preventDefault(); if(!e.repeat&&_inSel.size){ selWatch('info'); _inSel=new Set(); infoSelApply(); stat(t('msg.deselect','選択解除')); } return; }   // A=選択解除
      if(hit(e,'jumpHead')){ e.preventDefault(); if(!e.repeat) infoCenterView(); return; }   // .=全ノードの中央へ
      if(hit(e,'copy')){ e.preventDefault(); if(!e.repeat){
        if(_inSel.size){   // コピー時点の中身を複製して保持（元ノードを消してもペースト可能・Undoのid再利用にも安全）
          _infoClip={items:[..._inSel].map(key=>{
            if(key.startsWith('out:')){ const o=infoGraph.outs[key.slice(4)];
              return o?{kind:'out',x:o.x,y:o.y,folderName:o.folderName||''}:null; }
            const n=infoGraph.nodes[key];
            return n?{kind:'src',t:n.t,x:n.x,y:n.y,data:structuredClone(n.data),cover:_coverHandles[key]||null}:null;
          }).filter(Boolean)};
          stat(tf('msg.nodeCopied','ノードをコピーしました ×{n}（Ctrl+Vで複製）',{n:_infoClip.items.length})); }
        else stat('コピーするノードを選択してください'); } return; }
      if(hit(e,'cut')){ e.preventDefault(); if(!e.repeat){   // カット（コピー＋削除・1操作扱い）
        if(_inSel.size){
          _infoClip={items:[..._inSel].map(key=>{
            if(key.startsWith('out:')){ const o=infoGraph.outs[key.slice(4)];
              return o?{kind:'out',x:o.x,y:o.y,folderName:o.folderName||''}:null; }
            const n=infoGraph.nodes[key];
            return n?{kind:'src',t:n.t,x:n.x,y:n.y,data:structuredClone(n.data),cover:_coverHandles[key]||null}:null;
          }).filter(Boolean)};
          const n2=_infoClip.items.length;
          const pre=dumpDomain('info'); const sup=_infoSnapSup; _infoSnapSup=true;
          for(const key of [..._inSel]){ if(key.startsWith('out:')) deleteOutNode(key.slice(4));
            else if(infoGraph.nodes[key]) deleteSrcNode(key); }
          _infoSnapSup=sup;
          if(dumpDomain('info')!==pre) pushHist('info',pre);
          stat(tf('msg.nodeCut','ノードをカット ×{n}（Ctrl+Vで貼り付け）',{n:n2})); }
        else stat('カットするノードを選択してください'); } return; }
      if(hit(e,'paste')){ e.preventDefault(); if(!e.repeat){
        if(_infoClip&&_infoClip.items&&_infoClip.items.length){
          const pre=dumpDomain('info'); const sup=_infoSnapSup; _infoSnapSup=true;   // 一括ペースト=1ステップ
          const ns=new Set();
          for(const it of _infoClip.items){
            if(it.kind==='out'){ const oid=addOutNode(it.x+50,it.y+50);
              infoGraph.outs[oid].folderName=it.folderName; ns.add('out:'+oid); }
            else { const id=addSrcNode(it.t,it.x+50,it.y+50);
              infoGraph.nodes[id].data=structuredClone(it.data);
              if(it.cover) _coverHandles[id]=it.cover; ns.add(id); } }
          _infoClip.items.forEach(it=>{ it.x+=50; it.y+=50; });   // 連続ペーストで重ならないよう次回分をずらす
          _infoSnapSup=sup;
          if(dumpDomain('info')!==pre) pushHist('info',pre);
          _inSel=ns; infoSelApply(); layoutInfoNodes(); }
        else stat('クリップボードが空です（ノードをCtrl+Cでコピーしてから）'); } return; }
      if((hit(e,'del')||(e.key==='Delete'&&!e.ctrlKey&&!e.altKey&&!e.metaKey))){ e.preventDefault(); if(!e.repeat&&_inSel.size){
        const pre=dumpDomain('info'); const sup=_infoSnapSup; _infoSnapSup=true;   // 一括削除=1ステップ（最後のoutが残る等、実変化なしなら積まない）
        for(const key of [..._inSel]){ if(key.startsWith('out:')) deleteOutNode(key.slice(4));
          else if(infoGraph.nodes[key]) deleteSrcNode(key); }
        _infoSnapSup=sup;
        if(dumpDomain('info')!==pre) pushHist('info',pre); } return; }
      if(e.key==='Tab'){ e.preventDefault(); if(!e.repeat) setNodeColMode('nle'); return; }
      return; }
    if(ndView==='layers'){                                                // レイヤービューの編集キー
      { const _sa=hit(e,'saveAs'),_sv=hit(e,'save'); if(_sa||_sv){ e.preventDefault(); saveProject(_sa); return; } }
      if(hit(e,'open')){ e.preventDefault(); openProjectFile(); return; }
      { const _rd=hit(e,'redo'),_un=hit(e,'undo'); if(_rd||_un){ e.preventDefault(); _rd?redo('node'):undo('node'); return; } }
      if(hit(e,'deselect')){ e.preventDefault(); if(!e.repeat&&(layerSel.size||musicSelSet.size)){   // A=選択解除（クリップ＋Music）。下の修飾キー遮断より前に置く＝Ctrl+A等へ再割当しても効く
        selWatch('node'); layerSel=new Set(); musicSelSet=new Set(); stat(t('msg.deselect','選択解除')); } return; }
      if(hit(e,'copy')){ e.preventDefault();   // クリップをコピー（現在の難易度のみ=箱は難易度別）
        const sel=sections.filter(x=>layerSel.has(x.id)&&x.kind!=='null');
        if(!sel.length){ stat('コピーするクリップを選択してください'); return; }
        const base=Math.min(...sel.map(s=>s.beat||0));
        layerClipboard={items:sel.map(s=>({rel:(s.beat||0)-base,track:s.track||0,lk:secLk(s),len:s.len||4,label:s.label,col:s.col,colHex:s.colHex||null,
            content:structuredClone(s.content||{})}))};
        stat(tf('msg.clipCopy','クリップをコピー ×{n}',{n:sel.length})); return; }
      if(hit(e,'cut')){ e.preventDefault();   // カット（コピー＋削除）
        const sel=sections.filter(x=>layerSel.has(x.id)&&x.kind!=='null');
        if(!sel.length){ stat('カットするクリップを選択してください'); return; }
        const base=Math.min(...sel.map(s=>s.beat||0));
        layerClipboard={items:sel.map(s=>({rel:(s.beat||0)-base,track:s.track||0,lk:secLk(s),len:s.len||4,label:s.label,col:s.col,colHex:s.colHex||null,
            content:structuredClone(s.content||{})}))};
        const n2=sel.length;
        deleteLayerSel();
        stat(tf('msg.clipCut','クリップをカット ×{n}（Ctrl+Vで貼り付け）',{n:n2})); return; }
      if(hit(e,'paste')){ e.preventDefault(); if(!e.repeat) startLayerPaste(); return; }   // ゴースト追従ペースト（マウスで位置決め→クリックで確定 / Esc取消）
      if(hit(e,'nleMerge')){ e.preventDefault(); if(!e.repeat){ musicSelSet.size>=2?mergeMusicSel():mergeLayerSel(); } return; }   // マージ。Musicセグメント選択中はそちらを結合
      if(hit(e,'markerAdd')){ e.preventDefault(); if(!e.repeat) addMarkerAt(tlHoverBeat??cur); return; }   // カーソル位置にマーカー挿入（NLE）
      if(e.ctrlKey||e.altKey||e.metaKey||e.shiftKey) return;   // 未設定の修飾キー付きは無効化（NLE=素のキーのみ許可。文書化済みCtrl系は上で処理済み）
      if(hit(e,'nleLock')&&_ndMouseY>=LRULER){ if(!e.repeat){ const la=laneAtY(_ndMouseY); toggleLaneState('l',la.lk,la.gi); } return; }   // L=マウス下トラックをロック切替(on/off)
      if(hit(e,'nleMute')&&_ndMouseY>=LRULER){ if(!e.repeat){ const la=laneAtY(_ndMouseY); toggleLaneState('m',la.lk,la.gi); } return; }   // M=ミュート切替
      if(hit(e,'nleSolo')&&_ndMouseY>=LRULER){ if(!e.repeat){ const la=laneAtY(_ndMouseY); toggleLaneState('s',la.lk,la.gi); } return; }   // S=ソロ切替
      if(e.key==='r'||e.key==='R'){ if(!e.repeat){ layerRazor=!layerRazor; stat(layerRazor?'分割モード ON（クリップをクリックで分割）':'分割モード OFF'); } return; }
      // マーカー挿入は Ctrl+E（上のCtrl系ハンドラで処理）。旧Qは廃止（ヘルバ様指定）
      if(hit(e,'del')||e.key==='Delete'){ e.preventDefault();
        if(musicSelSet.size){
          if(musicSegs){ snapshot('node');
            musicSegs=musicSegs.filter((_,j)=>!musicSelSet.has(j));   // 選択セグメントを一括削除（余韻カット等）
            if(!musicSegs.length){ musicSegs=null; deleteMusic(); }
            else { metaDirty=true; stat('Musicセグメントを削除しました'); }
            musicSelSet=new Set(); }
          else deleteMusic();
        } else deleteLayerSel(); return; }
      if(hit(e,'nleCut')){ if(e.repeat) return;                      // C=カット: 選択ボックスをカーソル拍で分割
        if(tlHoverBeat==null){ stat('C: タイムライン上にマウスを置いてから'); return; }
        let did=false;
        const targets=sections.filter(s2=>layerSel.has(s2.id));               // カットが選択を解除する前に対象を確定
        if(musicSelSet.size&&cutMusicAt(tlHoverBeat)) did=true;               // Musicは選択中のセグメントのみカット
        for(const s of targets){ const b0=s.beat||0, L=s.len||4;
          if(tlHoverBeat>b0+1e-6&&tlHoverBeat<b0+L-1e-6){ splitSectionAt(s,tlHoverBeat); did=true; } }
        if(!did) stat('C: カーソル位置が選択ボックスの範囲内にありません');
        return; }
      if(hit(e,'snapPie')){ e.preventDefault(); if(!e.repeat&&!pieOpen) openPie(snapPieDefs,snap,setSnap,','); return; }   // スナップパイ（全画面共通）
      if(e.key==='Escape'){ if(pieOpen){ closePie(false); return; } if(layerPaste){ cancelLayerPaste(); return; } selWatch('node'); layerRazor=false; layerSel=new Set(); return; }
      if(hit(e,'jumpHead')){ if(!e.repeat){ tlViewB0=null; tlB0=Math.max(0,cur-tlSpan*0.5); } return; }   // .=再生ヘッドへジャンプ（窓をヘッド中心へ）
      if(e.key==='Tab'){ e.preventDefault(); if(!e.repeat) setNodeColMode(nodeColMode==='nle'?'info':'nle'); return; }   // Tab=NLE⇄INFO切替（他ペインと同じ流儀）
      return;
    }
    if((hit(e,'del')||(e.key==='Delete'&&!e.ctrlKey&&!e.altKey&&!e.metaKey))){
      if(ndMultiSel.size>1){ e.preventDefault(); deleteMultiSel(); }
      else if(ndSel){ e.preventDefault(); deleteSelNode(); } return; }
    if(hit(e,'deselect')){ e.preventDefault(); if(!e.repeat&&(ndSel||ndMultiSel.size)){ ndSel=null; ndMultiSel.clear(); stat(t('msg.deselect','選択解除')); } return; }   // A=選択解除
    if(hit(e,'copy')){ e.preventDefault(); copySelNode(); return; }
    if(hit(e,'paste')){ e.preventDefault(); pasteNode(); return; }
    if(hit(e,'jumpHead')){ e.preventDefault();          // アクティブラインのINPUTへワープ
      if(!e.repeat&&graphIO&&graphIO.in){
        ndCam.x=graphIO.in.nx-(ndW/ndCam.scale)*0.12;
        ndCam.y=graphIO.in.ny-(ndH/ndCam.scale)*0.35; }
      return; }
    { const _sa=hit(e,'saveAs'),_sv=hit(e,'save'); if(_sa||_sv){ e.preventDefault(); saveProject(_sa); return; } }
    if(hit(e,'open')){ e.preventDefault(); openProjectFile(); return; }
    { const _rd=hit(e,'redo'),_un=hit(e,'undo'); if(_rd||_un){ e.preventDefault(); _rd?redo('node'):undo('node'); return; } }
    if(e.key==='Tab'){ e.preventDefault(); if(!e.repeat) setNodeColMode(nodeColMode==='nle'?'info':'nle'); return; }   // Tab=NLE⇄INFO切替
    return;                                                               // それ以外（C=チェーン等）はNODEでは無効
  }
  if(e.key==='Tab'&&hoverPane==='pv'){ e.preventDefault(); setPvMode(pvMode==='preview'?'media':'preview'); return; }   // Tab=MEDIA⇄PREVIEW（pvペイン。ペイン切替はTab固定）
  if(hoverPane!=='node'&&hoverPane!=='pv'&&hit(e,'lightMode')){ e.preventDefault(); setLightMode(!lightMode); return; }   // NOTES⇄LIGHTING切替（既定Tab・再割当対応・Phase2）
  { const _sa=hit(e,'saveAs'), _sv=hit(e,'save'); if(_sa||_sv){ e.preventDefault(); saveProject(_sa); return; } }   // 保存 / 名前を付けて保存
  if(hit(e,'open')){ e.preventDefault(); openProjectFile(); return; }
  { const _rd=hit(e,'redo'), _un=hit(e,'undo'); if(_rd||_un){ e.preventDefault(); _rd?redo():undo(); return; } }
  if(hit(e,'copy')){ e.preventDefault(); copySel3D(); return; }
  if(hit(e,'paste')){ e.preventDefault(); pasteSel3D(); return; }
  if(hit(e,'cut')){ e.preventDefault(); if(!e.repeat) cutSel3D(); return; }
  if(hit(e,'markerAdd')){ e.preventDefault(); if(!e.repeat) addMarkerAt(hoverBeat??cur); return; }   // マーカー挿入（3D EDIT・NLEと統一）
  if(hit(e,'noteArc')&&!lightMode){ e.preventDefault(); if(!e.repeat) createArc(); return; }   // 選択2ノーツからアーク
  if(hit(e,'noteChain')&&!lightMode){ e.preventDefault(); if(!e.repeat) createChain(); return; }   // 選択2ノーツからチェーン
  if(e.ctrlKey||e.altKey||e.metaKey||e.shiftKey) return;   // 未設定の修飾キー付きショートカットは無効化（3D編集=素のキーのみ許可・カスタム割当時の競合防止。文書化済みCtrl系は上で処理済み）
  if(hit(e,'jumpHead')){ e.preventDefault(); if(!e.repeat){ // 再生ヘッドにジャンプ: カメラの角度・高さ・横位置は不変、タイムライン軸(Z)の平行移動のみ
    vwB=null;   // ビュー固定を解除してヘッド追従に戻る（ヘッド=z0）
    const dz=0-controls.target.z;
    camera.position.z+=dz; controls.target.z+=dz; controls.update(); } return; }
  if(hit(e,'snapPie')){ e.preventDefault(); if(!e.repeat&&!pieOpen) openPie(snapPieDefs,snap,setSnap,','); return; }
  if(e.key==='Escape'&&pieOpen){ closePie(false); return; }
  if(hit(e,'camMode')){ if(!e.repeat) toggleCamMode(); return; }   // Q=配置/編集モード切替（配置=カメラ追従+定位置ビュー・編集=カメラ自由）。ライトモードでも有効（ヘルバ様指定 2026-07-13）
  // A=選択解除（NOTES/LIGHTING 共通）。下のライトモード単キー遮断(/^[wasnbrtgv]$/)より前に置く＝ライト中もAが届く
  if(hit(e,'deselect')){ e.preventDefault(); if(!e.repeat){
      if(lightMode){ if(lightSelection.size){ selWatch('light'); lightSelection.clear(); } }
      else if(selection.size){ selWatch('note'); selection.clear(); }
      gizmoMode=null; stat(t('msg.deselect','選択解除')); } return; }
  // R=配置モードトグルは廃止（ヘルバ様指定。配置/編集はQで切替・配置種別はWパイ/ツールバー）
  // NOTES/LIGHTING 切替は Tab に一本化（旧・L単キー切替は廃止＝Lはレーンロック専用に。ヘルバ様指定 2026-07-15）
  // ※F(lightCycle/noteFlip)は上のNODE分岐より前へ移動済み＝全画面共通（2026-07-18）
  if(lightMode&&hit(e,'lightPie')){ if(!e.repeat&&!pieOpen) openLightPie(); return; }   // W=ライト用パイ（選択/ON/OFF/フラッシュ/フェード/トランジション・離して確定・ヘルバ様指定）
  if(lightMode&&hit(e,'lightColorPie')){ if(!e.repeat&&!pieOpen) openLightColorPie(); return; }   // C=ライト色パイ（左ノーツ→右ノーツ→クロマ登録色・離して確定・ヘルバ様指定 2026-07-13）
  if(lightMode&&/^[wasnbrtgv]$/i.test(e.key)){ return; }      // ライティング中はノーツ系＋旧ライト動作単体キー(N/B/R/T)＋移動(G)＋色反転(V廃止)を無効化＝動作選択はWパイ/ツールバー（Cは色パイに割当）
  if(hit(e,'noteWall')){ if(!e.repeat) toggleSizeMode(); return; }   // S=壁のサイズモード
  if(pasteFollow&&(e.key==='Enter'||e.code==='NumpadEnter')){ e.preventDefault(); confirmPasteFollow(); return; }
  if(e.key==='Escape'){
    if(wallStage){ cancelWallStage(); return; }
    if(cancelPasteFollow()) return;
    if(gizmoMode){ gizmoMode=null; stat('ギズモ OFF'); return; }
    if(lightMove){ cancelLightMove(); return; }
    if(lightMode){ setLightMode(false); return; }
    if(placeMode){ setPlaceMode(false); return; } return; }
  // N/B/W単体のブラシ切替は廃止＝W長押しの配置パイ（セレクト/ノーツ/ボム/壁）に集約（ヘルバ様指定）
  if(hit(e,'notePie')){ if(!e.repeat&&!pieOpen) openPlaceModePie(); return; }   // W=押した瞬間に配置パイ（離して確定・ヘルバ様指定＝長押し廃止）
  if(e.key==='c'||e.key==='C'){ if([...selection].filter(isColorNote).length>=2) createChain(); return; }   // チェーン=同色2個以上必須（1個変換は廃止・ヘルバ様指定2026-07-13）。<2個なら何もしない（Ctrl+Tも同条件）
  // V(ブラシ色反転)は廃止＝Fに集約（何も無い所でF=ブラシ色反転・ノーツ上でF=そのノーツ反転。ヘルバ様指定）
  // ※本体は上のNODE分岐より前へ移動済み（全画面共通・2026-07-18）
  // マーカー挿入は Ctrl+E（上のCtrl系ハンドラで処理）。旧Qは廃止（NLEと統一・ヘルバ様指定）
  if((hit(e,'del')||e.key==='Delete')&&lightMode&&lightSelection.size){ snapshot();
    const c=lightSelection.size;
    lightEvents=lightEvents.filter(ev=>!lightSelection.has(ev));
    lightSelection.clear(); stat(tf('msg.lightDelN','ライト削除 ×{n}',{n:c})); return; }
  if((hit(e,'del')||e.key==='Delete')&&selection.size){ snapshot();
    const c=selection.size; [...selection].forEach(o=>removeObj(o));
    stat(tf('msg.delN','削除 ×{n}',{n:c})); selection.clear(); }
});

// ---- loop ----
function resize(){ const r=cv.parentElement.getBoundingClientRect(); renderer.setSize(r.width,r.height);
  camera.aspect=r.width/r.height; camera.updateProjectionMatrix();
  ovResize(); specResize(); ndResize(); prResize(); vmResize(); }
addEventListener('resize',resize); resize();
setNdView('layers');   // 既定=レイヤー表示（ndW確定後にフィット＋ボタン状態を同期）
initScratchDiff();     // 難易度プルダウンを起動時から常時表示（標準5難易度・既定Hard）

// ============ 右インスペクタ: ノードの設定を集約（曲情報/難易度/カバー/出力） ============
let _inspCoverKey='';
function refreshInspector(){
  if(ndView!=='layers') return;                // レイヤー表示時のみ更新
  if(typeof refreshInfoCards==='function') refreshInfoCards();   // 各ノードカード（独立データ箱）の表示更新
  if(typeof refreshOutCards==='function') refreshOutCards();     // 書き出しノードの表示更新
  refreshChartInfo();
}
let _chartInfoKey='';
function refreshChartInfo(){   // 譜面データ: NLE/NOTES/LIGHTINGの実データを背景に直書き（Blender風・表示専用。書き出しには常時この本体が流れる）
  const el=document.getElementById('chartInfo'); if(!el) return;
  const nm2=(songNode&&songNode.name)||TL('ci.noAudio','（音源未読込）');
  const dur=audioBuf?`${Math.floor(songDur/60)}:${String(Math.floor(songDur%60)).padStart(2,'0')}`:'--:--';
  let html2=`<div>${TL('ci.song','曲')}<b>${nm2} ・ ${dur}</b></div><div>BPM<b>${BPM}</b></div>`
    +`<div style="display:flex;align-items:center;gap:9px;border:1px solid #43434a;border-radius:6px;background:rgba(43,43,43,.85);padding:5px 11px;margin-top:8px;min-width:150px;"><img src="icons/char_standard.svg" alt="Standard" style="width:20px;height:20px;flex:0 0 auto;"><span style="font-size:12.5px;color:#c8ccd4;">${TL('ui.dualStandard','二刀流（Standard）')}</span></div>`;   // 二刀流アイコンを横長の四角で囲む（設定ノードと統一・ヘルバ様指示）
  const curK=(currentDiffName||'').toLowerCase();
  for(const dnm of OUT_DIFFS){ const key2=dnm.toLowerCase()+'standard.dat';
    const st2=key2===curK?{notes,lightEvents}:projDiffs[key2];
    const nN=st2?(st2.notes||[]).length:0, nL=st2?(st2.lightEvents||[]).length:0;
    html2+=`<div${(nN||nL)?'':' class="dim"'}>${dnm==='ExpertPlus'?'Expert+':dnm}<b>${ICO_N_MINI} ${nN}　${ICO_L_MINI} ${nL}</b></div>`; }
  if(_chartInfoKey!==html2){ _chartInfoKey=html2; el.innerHTML=html2; }
}
// 出力フォルダ名は英数のみ（非ASCIIやWindows禁止文字が混ざるとBeat Saberが読み込めない）。各書き出しノードの入力時に自動除去
function sanitizeFolderName(v){ return v.replace(/[^A-Za-z0-9 \-_.()\[\]&'!+,]/g,''); }
// INFOのBPM行は廃止（BPM操作はMusicレーン左溝のステッパーに集約。MEDIAの音源ドロップ時は自動設定）
// （旧・静的カードのiCoverBtn/iOutBtn配線は廃止。全ノードは動的生成=renderInfoCards/renderOutCards内で配線）
// ---- INFO画面のノード化（Phase1・ヘルバ様指示）: 既存カード=ノード（フィールドの配線は無変更）。ドラッグ/パン/ズーム/右クリック追加削除＋OUTPUTへの配線表示 ----
// 各ノード=独立したデータ箱。書き出しノードに接続されている箱だけが「確定情報」としてアプリへ反映される
// （未接続=保管のみ・切断=右下表示等からも消える・繋ぎ替え=即差し替え。旧ノードシステムのaltIns/activeUidsと同じ思想）
const INFO_NODE_DEFS={meta:['曲情報','#e36ea8'],set:['設定','#9a9aa6'],cover:['カバー画像','#4dc8ff']};   // 曲情報=ピンク/設定=灰/カバー=青（ヘルバ様指示）
const INFO_SRCS=['meta','cover','set'];   // 書き出しノードの入力ポート順＝ピンク(曲情報)→青(カバー)→灰(設定)
function defInfoData(t){ return t==='meta'?{name:'',sub:'',artist:'',author:''}
  :t==='set'?{red:0xff274d,blue:0x3092ff,lred:0xff274d,lblue:0x3092ff,lredB:0xff6f9f,lblueB:0x6fdcff,env:'',diffs:{}}
  :{name:''}; }
function defaultInfoGraph(){ return {
  nodes:{m1:{t:'meta',x:24,y:16,data:defInfoData('meta')},
         s1:{t:'set',x:336,y:16,data:defInfoData('set')},
         c1:{t:'cover',x:24,y:206,data:defInfoData('cover')}},nseq:1,
  outs:{o1:{x:660,y:100,folderName:'',outDirName:'',outDirPath:''}},activeOut:'o1',oseq:1,
  edges:[{s:'m1',o:'o1'},{s:'s1',o:'o1'},{s:'c1',o:'o1'}],cam:{x:0,y:0,s:1,auto:1}}; }
function sanitizeInfoGraph(){
  if(!infoGraph.outs){   // 旧形式（out単一・edges=文字列配列）
    const p=(infoGraph.pos&&infoGraph.pos.out)||{x:800,y:110};
    infoGraph.outs={o1:{x:p.x,y:p.y,folderName:(graphIO&&graphIO.out&&graphIO.out.folderName)||'',outDirName:(graphIO&&graphIO.out&&graphIO.out.outDirName)||'',outDirPath:(graphIO&&graphIO.out&&graphIO.out.outDirPath)||''}};
    infoGraph.activeOut='o1'; infoGraph.oseq=1;
  }
  if(!infoGraph.nodes){   // 旧形式（タイプ単一カード）→ 現在のグローバル値を初期データにして各1個のノードへ移行
    const P=infoGraph.pos||{}, ib=infoBase||{};
    infoGraph.nodes={
      m1:{t:'meta',x:(P.meta&&P.meta.x)??24,y:(P.meta&&P.meta.y)??16,
        data:{name:ib._songName||'',sub:ib._songSubName||'',artist:ib._songAuthorName||'',author:ib._levelAuthorName||''}},
      s1:{t:'set',x:(P.set&&P.set.x)??400,y:(P.set&&P.set.y)??16,
        data:{red:RED,blue:BLUE,lred:LRED,lblue:LBLUE,lredB:LRED_B,lblueB:LBLUE_B,env:ib._environmentName||'',diffs:{...((graphIO&&graphIO.out&&graphIO.out.diffs)||{})}}},
      c1:{t:'cover',x:(P.cover&&P.cover.x)??24,y:(P.cover&&P.cover.y)??236,
        data:{name:(extraNodes.find(x=>x.kind==='cover')||{}).name||''}}};
    infoGraph.nseq=1;
    const cv=extraNodes.find(x=>x.kind==='cover'); if(cv&&cv.handle) _coverHandles.c1=cv.handle;   // 既存カバーの参照を引き継ぐ
    const map={meta:'m1',set:'s1',cover:'c1'};
    infoGraph.edges=(infoGraph.edges||[]).map(ed=>{
      if(typeof ed==='string') return map[ed]?{s:map[ed],o:'o1'}:null;
      if(ed&&map[ed.s]) return {s:map[ed.s],o:ed.o||'o1'};
      return ed; }).filter(Boolean);
    delete infoGraph.pos; delete infoGraph.hidden; delete infoGraph.clones; delete infoGraph.cseq;
  }
  for(const id in infoGraph.nodes){ const n=infoGraph.nodes[id];
    if(!n||!INFO_NODE_DEFS[n.t]){ delete infoGraph.nodes[id]; continue; }
    n.data=Object.assign(defInfoData(n.t),n.data||{}); }
  infoGraph.oseq=infoGraph.oseq||Object.keys(infoGraph.outs).length;
  infoGraph.nseq=infoGraph.nseq||Object.keys(infoGraph.nodes).length;
  if(!infoGraph.outs[infoGraph.activeOut]) infoGraph.activeOut=Object.keys(infoGraph.outs)[0];
  infoGraph.edges=(infoGraph.edges||[]).filter(ed=>ed&&typeof ed==='object'&&infoGraph.nodes[ed.s]&&infoGraph.outs[ed.o]);
  { const seen=new Set();   // 完全重複と「同out同タイプ2本」を除去（後勝ち=最後に繋いだものが有効。手編集/破損プロジェクト対策）
    for(let i=infoGraph.edges.length-1;i>=0;i--){ const ed=infoGraph.edges[i], k=ed.s+'>'+ed.o, kt=ed.o+'|'+(infoGraph.nodes[ed.s]||{}).t;
      if(seen.has(k)||seen.has(kt)) infoGraph.edges.splice(i,1); else { seen.add(k); seen.add(kt); } } }
  for(const id in _coverHandles) if(!infoGraph.nodes[id]) delete _coverHandles[id];   // 死んだidのランタイム参照を掃除（Undoでのid再採番に旧handleが憑依しない）
  for(const oid in _outHandles) if(!infoGraph.outs[oid]) delete _outHandles[oid];
  for(const key of [..._coverImgs.keys()]) if(key.startsWith('ig:')&&!infoGraph.nodes[key.slice(3)]){
    const c=_coverImgs.get(key); if(c&&c.bmp&&c.bmp.close) try{ c.bmp.close(); }catch(_){}
    _coverImgs.delete(key); }
}
const _coverHandles={};   // カバーノードid→画像handle（ランタイムのみ。名前はdataに保存）
let _coverB64={};   // カバーノードid→画像のbase64 dataURL（プロジェクトに埋め込んで保存＝再取得に頼らず確実に復元）
function blobToDataURL(blob){ return new Promise((res,rej)=>{ const r=new FileReader(); r.onload=()=>res(r.result); r.onerror=rej; r.readAsDataURL(blob); }); }
function dataURLToBlob(u){ const [h,b]=String(u).split(','); const mime=(h.match(/:(.*?);/)||[])[1]||'image/png'; const bin=atob(b); const a=new Uint8Array(bin.length); for(let i=0;i<bin.length;i++) a[i]=bin.charCodeAt(i); return new Blob([a],{type:mime}); }
async function refreshCoverB64(){   // 保存前に各カバー画像をbase64化（存在するノードのみ）
  const out={};
  for(const id in _coverHandles){ if(!infoGraph.nodes||!infoGraph.nodes[id]) continue;
    try{ const f=await _coverHandles[id].getFile(); if(f) out[id]=await blobToDataURL(f); }catch(e){} }
  _coverB64=out;
}
async function restoreCoversFromB64(pj){   // 読込時: 同梱base64からカバー画像を復元（再取得に頼らない）
  if(!pj||!pj.coverData) return; let any=false;
  for(const id in pj.coverData){
    try{ _coverB64[id]=pj.coverData[id];
      const blob=dataURLToBlob(pj.coverData[id]);
      const nm=(infoGraph.nodes&&infoGraph.nodes[id]&&infoGraph.nodes[id].data&&infoGraph.nodes[id].data.name)||'cover';
      _coverHandles[id]={name:nm,getFile:async()=>blob}; any=true;
      try{ await loadCoverPreview({id:'ig:'+id,handle:_coverHandles[id],name:nm}); }catch(_){}
    }catch(e){} }
  if(any){ if(typeof applyInfoGraph==='function') applyInfoGraph(); if(typeof refreshInfoCards==='function') refreshInfoCards(); }
}
let _infoSnapT=0,_infoSnapSup=false;   // INFOのUndoスナップショット（連続編集は600msで1回・複合操作は抑制フラグで1回）
function infoSnapshot(){ if(_infoSnapSup) return; snapshot('info'); }
function infoSnapBurst(){ if(_infoSnapSup) return; const now=performance.now(); if(now-_infoSnapT>600) snapshot('info'); _infoSnapT=now; }
function infoNodeT(id){ const n=infoGraph.nodes[id]; return n?n.t:null; }
function connectedNodeId(t,oid){ oid=oid||infoGraph.activeOut;   // そのoutに接続中の指定タイプのノード（最後に繋いだもの）
  for(let i=(infoGraph.edges||[]).length-1;i>=0;i--){ const ed=infoGraph.edges[i];
    if(ed.o===oid&&infoNodeT(ed.s)===t) return ed.s; } return null; }
function applyInfoGraph(){   // アクティブな書き出しに接続されたノードだけを確定情報としてアプリへ反映
  infoBase=infoBase||{};
  const mid=connectedNodeId('meta'), m=mid&&infoGraph.nodes[mid];
  infoBase._songName=m?(m.data.name||''):''; infoBase._songSubName=m?(m.data.sub||''):'';
  infoBase._songAuthorName=m?(m.data.artist||''):''; infoBase._levelAuthorName=m?(m.data.author||''):'';
  const sid=connectedNodeId('set'), s=sid&&infoGraph.nodes[sid];
  if(s){ RED=s.data.red>>>0; BLUE=s.data.blue>>>0; LRED=s.data.lred>>>0; LBLUE=s.data.lblue>>>0;
    LRED_B=(s.data.lredB!=null)?s.data.lredB>>>0:_briB(LRED); LBLUE_B=(s.data.lblueB!=null)?s.data.lblueB>>>0:_briB(LBLUE);   // ブースト色は独立保存（旧ファイルは派生でフォールバック）
    infoBase._environmentName=s.data.env||''; if(graphIO&&graphIO.out) graphIO.out.diffs={...(s.data.diffs||{})}; }
  else { RED=0xff274d; BLUE=0x3092ff; LRED=0xff274d; LBLUE=0x3092ff; LRED_B=_briB(LRED); LBLUE_B=_briB(LBLUE);
    infoBase._environmentName=''; if(graphIO&&graphIO.out) graphIO.out.diffs={}; }
  setNoteColStr(); applyModeDim();   // laserBoostCols()は撤去＝上でブースト色を独立設定済み
  const cid=connectedNodeId('cover'), c=cid&&infoGraph.nodes[cid];
  { let cv=extraNodes.find(x=>x.kind==='cover');   // 既存の右下表示/書き出しコード（extraNodesカバー）へミラー
    if(c&&(c.data.name||_coverHandles[cid])){
      if(!cv&&graphIO&&graphIO.out) cv=createExtra('cover',(graphIO.out.nx||0)-260,(graphIO.out.ny||0)+120);
      if(cv){ cv.name=c.data.name||''; cv.handle=_coverHandles[cid]||null;
        ensureEdges(); if(!graphEdges.some(e2=>e2.sig==='cover'&&e2.fromId===cv.id&&e2.toId==='out')) graphEdges.push({fromId:cv.id,toId:'out',sig:'cover'}); } }
    else if(cv){ cv.name=''; cv.handle=null; }
    _coverKey=''; _inspCoverKey='';
  }
  infoDirty=true; applyInfoChain(); metaDirty=true;
  if(typeof refreshInfoCards==='function') refreshInfoCards();
  // 環境が確定/変更されたらV2プレビューへ追従（曲読込・環境ノード変更）。
  // setEnvironmentは同名なら即return（行100）なので毎回呼んでも再ロードしない＝「消える」嵐は起きない。
  // try/catchは起動時の先行呼び出し(pv4On未初期化=TDZ)を無害に飲むため。
  try{ if(pv4On) pv4SyncEnv(); }catch(_e){}
}
// ---- 複数の書き出しノード: 最後に選択したものがアクティブ（書き出し対象）、他は休止=灰色（旧ノードのactiveUids/休止ライン方式） ----
const _outHandles={};   // oid→フォルダhandle（ランタイムのみ）
let _infoClip=null;     // Ctrl+Cでコピーしたノード {items:[{kind:'src',t,x,y,data,cover}|{kind:'out',x,y,folderName}]}（コピー時点の実体を保持）
function setActiveOut(oid){ const oNew=infoGraph.outs[oid]; if(!oNew) return;
  if(infoGraph.activeOut===oid){   // 既にアクティブ: ミラーだけ揃え直す（Undoには積まない）
    outDirHandle=_outHandles[oid]||null;
    if(graphIO&&graphIO.out){ graphIO.out.folderName=oNew.folderName||''; graphIO.out.outDirName=oNew.outDirName||''; graphIO.out.outDirPath=oNew.outDirPath||''; }
    refreshOutCards(); return; }
  infoSnapshot();   // アクティブ切替もUndo対象
  const cur=infoGraph.activeOut;
  if(cur&&infoGraph.outs[cur]){ _outHandles[cur]=outDirHandle;   // 現アクティブの状態を控える
    if(graphIO&&graphIO.out){ infoGraph.outs[cur].folderName=graphIO.out.folderName||''; infoGraph.outs[cur].outDirName=graphIO.out.outDirName||''; infoGraph.outs[cur].outDirPath=graphIO.out.outDirPath||''; } }
  infoGraph.activeOut=oid;
  const o=infoGraph.outs[oid];
  outDirHandle=_outHandles[oid]||null;   // 書き出し系の既存コードはgraphIO.out/outDirHandleを見るため、アクティブをミラー
  if(graphIO&&graphIO.out){ graphIO.out.folderName=o.folderName||''; graphIO.out.outDirName=o.outDirName||''; graphIO.out.outDirPath=o.outDirPath||''; }
  applyInfoGraph();   // アクティブoutが変われば確定情報（接続ノード）も変わる
  metaDirty=true; refreshOutCards(); drawInfoEdges();
}
function addOutNode(x,y,copyFrom){ infoSnapshot(); const sup=_infoSnapSup; _infoSnapSup=true;
  const oid='o'+(++infoGraph.oseq);
  const src=copyFrom&&infoGraph.outs[copyFrom];
  infoGraph.outs[oid]={x,y,folderName:src?(src.folderName||''):'',outDirName:'',outDirPath:''};   // フォルダ実体はコピーしない（選び直し）
  renderOutCards(); setActiveOut(oid); drawInfoEdges(); metaDirty=true; _infoSnapSup=sup; stat('書き出しノードを追加しました'); return oid; }
function deleteOutNode(oid){ if(!infoGraph.outs[oid]) return;
  if(Object.keys(infoGraph.outs).length<=1){ showErr('最後の書き出しノードは消せません'); return; }   // NOTES画面の注意書きと同じ赤トースト
  infoSnapshot(); const sup=_infoSnapSup; _infoSnapSup=true;
  delete infoGraph.outs[oid]; delete _outHandles[oid];
  infoGraph.edges=(infoGraph.edges||[]).filter(ed=>ed.o!==oid);
  if(infoGraph.activeOut===oid){ infoGraph.activeOut=null; setActiveOut(Object.keys(infoGraph.outs)[0]); }
  _inSel.delete('out:'+oid);
  renderOutCards(); drawInfoEdges(); metaDirty=true; _infoSnapSup=sup; stat('書き出しノードを削除しました'); }
// 出力フォルダ/カバー画像は「セッション中のみ」の実handleなので、アプリ再起動やプロジェクト再読込の直後は
// 名前は覚えていても実体が無くNGになる。カバーは「handleがあるように見えても実は権限が切れている」
// ケースを事前に判定できないため、設定済みなら毎回無条件で選び直す（1クリックでまとめて選び直せる）。
function needsReconnect(){
  if(!outDirHandle) return true;
  const cid=connectedNodeId('cover'), c=cid&&infoGraph.nodes[cid];
  return !!(c&&c.data.name&&!coverNativeOk(cid));
}
function coverNativeOk(cid){ const n=infoGraph.nodes[cid], h=_coverHandles[cid];   // 実ファイルに繋がっている（権限切れが無い）＝選び直し不要
  return !!(n&&n.data.nativePath&&h&&h.nativePath===n.data.nativePath); }
async function reconnectExportInputs(){
  let did=false;
  if(!outDirHandle){
    const oid=infoGraph.activeOut, pre=dumpDomain('info');
    try{ await pickOutFolder(); }catch(e){}
    const o=oid&&infoGraph.outs[oid]; if(o&&graphIO&&graphIO.out){ o.outDirName=graphIO.out.outDirName||''; o.outDirPath=graphIO.out.outDirPath||''; }
    _outHandles[oid]=outDirHandle;
    if(outDirHandle) did=true;
    if(dumpDomain('info')!==pre) pushHist('info',pre);
  }
  const cid=connectedNodeId('cover'), c=cid&&infoGraph.nodes[cid];
  if(c&&c.data.name&&!coverNativeOk(cid)){   // ブラウザhandleは権限切れを事前検知できないため常に選び直す（ネイティブで実ファイルに繋がっていれば不要）
    const pr=await pickCoverImage(c.data.nativePath);
    if(pr){ infoSnapshot(); c.data.name=pr.fh.name; c.data.nativePath=pr.path; _coverHandles[cid]=pr.fh; metaDirty=true; did=true; }
  }
  applyInfoGraph(); refreshInfoCards(); refreshOutCards();
  stat(did?t('m:書き出し設定を再接続しました','書き出し設定を再接続しました'):t('m:再接続する項目はありませんでした','再接続する項目はありませんでした'));
}
function readinessHTML(){ return exportReadiness().map(it=>{ const icon=it.ok?'✓':(it.req?'✕':'−'), col=it.ok?'#56ffc1':(it.req?'#ff5a6a':'#6a6a72');
  const tag=it.req?` <span style="font-size:9px;color:#ff8a94;border:1px solid #5a3038;border-radius:3px;padding:0 3px;">${TL('rd.req','必須')}</span>`:'';
  return `<div style="color:${it.ok?'#d8dce2':(it.req?'#e2b0b6':'#8a8a92')}"><span style="color:${col};font-weight:700;width:12px;text-align:center;">${icon}</span>${it.label}${tag}</div>`; }).join(''); }
function renderOutCards(){
  for(const el of [...infoWorldEl.querySelectorAll('.iGrp[data-out]')]) if(!infoGraph.outs[el.dataset.out]){
    const ex=el.querySelector('#iExport'); if(ex) document.getElementById('uiStash').appendChild(ex);   // 書き出しボタンはカードと道連れにしない（Undoでカードが消えても退避→refreshでアクティブへ戻る）
    el.remove(); }
  for(const oid in infoGraph.outs){ let el=infoWorldEl.querySelector(`.iGrp[data-out="${oid}"]`);
    if(!el){ el=document.createElement('div'); el.className='iGrp'; el.dataset.node='out:'+oid; el.dataset.out=oid;
      el.innerHTML=`<h3 data-i18n="node.export">${TL('node.export','書き出し')}</h3>
        <button class="iBtn folder oPick">📁 ${TL('ui.selectOutFolder','出力フォルダを選択')}</button>
        <div class="iRow"><label data-i18n="ui.outFolderName">${TL('ui.outFolderName','出力フォルダ名')}</label><input type="text" class="oName" data-i18n-ph="ph.folderName" placeholder="${TL('ph.folderName','半角英数のみ')}"></div>
        <label class="iRow" style="font-size:10.5px;color:#9a9aa2;" title="${TL('ui.forceEggTip','チェックすると次の書き出しでsong.eggを未変更でも強制的に再変換します（音源変換のやり直し用）')}"><input type="checkbox" class="oForceEgg" style="margin-right:5px;">${TL('ui.forceEgg','song.eggを強制再変換')}</label>
        <div class="oChk" style="padding:0 11px;font-size:11px;display:flex;flex-direction:column;gap:2px;"></div>
        <button class="iBtn oReconnect" style="display:none;margin:2px 11px 0;width:calc(100% - 22px);">🔌 ${TL('ui.reconnect','出力フォルダ/カバー画像を再接続')}</button>`;
      INFO_SRCS.forEach(k=>{ const pd=document.createElement('div'); pd.className='oPort'; pd.dataset.oport=oid+'|'+k;
        pd.innerHTML='<i></i>'; el.appendChild(pd); });   // 3色の入力ポート（カードの子・位置はrefreshで縦中央に追従）
      el.style.zIndex=String(++_inZTop);   // 新規生成は最前面に出す
      infoWorldEl.appendChild(el);
      const nameEl=el.querySelector('.oName');
      const applyN=()=>{ const o=infoGraph.outs[oid]; if(!o) return; infoSnapBurst(); const cln=sanitizeFolderName(nameEl.value);
        if(cln!==nameEl.value){ nameEl.value=cln; stat(t('m:出力フォルダ名は英数字のみ（日本語等はBeat Saberが読み込めないため自動除去）','出力フォルダ名は英数字のみ（日本語等はBeat Saberが読み込めないため自動除去）')); }
        o.folderName=cln.trim(); if(infoGraph.activeOut===oid&&graphIO&&graphIO.out) graphIO.out.folderName=o.folderName;
        metaDirty=true; };
      nameEl.addEventListener('input',ev=>{ if(!ev.isComposing) applyN(); });
      nameEl.addEventListener('compositionend',applyN); nameEl.addEventListener('blur',applyN);
      el.querySelector('.oPick').addEventListener('click',async()=>{ setActiveOut(oid);
        _pickOpen='outdir'; refreshOutCards();
        const pre=dumpDomain('info');   // キャンセル時に空のUndoステップを積まない
        try{ await pickOutFolder(); }catch(e){}
        _pickOpen=null;
        const o=infoGraph.outs[oid]; if(o&&graphIO&&graphIO.out){ o.outDirName=graphIO.out.outDirName||''; o.outDirPath=graphIO.out.outDirPath||''; }
        _outHandles[oid]=outDirHandle;
        if(dumpDomain('info')!==pre) pushHist('info',pre);
        metaDirty=true; refreshOutCards(); });
      el.querySelector('.oReconnect').addEventListener('click',()=>reconnectExportInputs());
    }
    const o=infoGraph.outs[oid]; el.style.left=o.x+'px'; el.style.top=o.y+'px'; el.style.display='flex';
  }
  refreshOutCards();
}
function refreshOutCards(){
  for(const el of infoWorldEl.querySelectorAll('.iGrp[data-out]')){ const oid=el.dataset.out, o=infoGraph.outs[oid]; if(!o) continue;
    const act=infoGraph.activeOut===oid;
    el.classList.toggle('outInactive',!act);
    el.classList.toggle('sel',_inSel.has('out:'+oid));
    el.querySelector('.oPick').textContent=(((act&&_pickOpen==='outdir')||o.outDirName)?'📂 ':'📁 ')+(o.outDirName||TL('ui.selectOutFolder','出力フォルダを選択'));
    const ne=el.querySelector('.oName'); if(document.activeElement!==ne) ne.value=o.folderName||'';
    el.querySelector('.oChk').innerHTML=act?readinessHTML():`<div style="color:#8a8a92;font-size:10px;">${TL('ui.outInactive','休止中（クリックでアクティブに）')}</div>`;
    el.querySelector('.oReconnect').style.display=(act&&needsReconnect())?'':'none';
    { const h2=el.offsetHeight||160;
      el.querySelectorAll('.oPort').forEach(pd=>{ const k=pd.dataset.oport.split('|')[1], dot=pd.querySelector('i');
        pd.style.top=(h2/2+(INFO_SRCS.indexOf(k)-1)*20-15)+'px';   // 縦中央に3つ（高さ変化に追従）
        const on=(infoGraph.edges||[]).some(ed=>ed.o===oid&&infoNodeT(ed.s)===k), col=INFO_NODE_DEFS[k][1];
        dot.style.background=on?col:'#1b1b1d';
        dot.style.border=on?'1.5px solid #141416':('3px solid '+col); }); }
    if(act){ const ex=document.getElementById('iExport'); if(ex&&ex.parentElement!==el) el.appendChild(ex); }   // 書き出しボタンはアクティブノードの最下段のみ
  }
}
// ---- ソースノード（曲情報/設定/カバー）の動的カード ----
function srcCardHTML(t){
  if(t==='meta') return `<h3 data-i18n="node.meta">${TL('node.meta','曲情報')}</h3>
    <div class="iRow"><label data-i18n="f.name">${TL('f.name','曲名')}</label><input type="text" data-f="name"></div>
    <div class="iRow"><label data-i18n="f.sub">${TL('f.sub','サブ')}</label><input type="text" data-f="sub"></div>
    <div class="iRow"><label data-i18n="f.artist">${TL('f.artist','アーティスト')}</label><input type="text" data-f="artist"></div>
    <div class="iRow"><label data-i18n="f.author">${TL('f.author','制作者')}</label><input type="text" data-f="author"></div>`;
  if(t==='set') return `<h3 data-i18n="node.set">${TL('node.set','設定')}</h3>
    <div class="iSub" style="padding:6px 11px 2px;">
      <div style="display:flex;align-items:center;gap:9px;border:1px solid #43434a;border-radius:6px;background:#2b2b2b;padding:6px 11px;">
        <img src="icons/char_standard.svg" alt="Standard" style="width:20px;height:20px;flex:0 0 auto;">
        <span style="font-size:11px;color:#c8ccd4;" data-i18n="ui.dualStandard">${TL('ui.dualStandard','二刀流（Standard）')}</span>
      </div></div>
    <div class="nDiffs" style="display:grid;grid-template-columns:auto;gap:3px 14px;padding:6px 11px 0;">`+
    OUT_DIFFS.map(d=>`<label class="iDiff"><input type="checkbox" data-d="${d}">${d==='ExpertPlus'?'Expert+':d}</label>`).join('')+`</div>`;
  return `<h3 data-i18n="node.cover">${TL('node.cover','カバー画像')}</h3>
    <button class="iBtn nPick" style="text-align:left">📁 ${TL('ui.selImage','画像を選択…')}</button>
    <img class="nThumb" style="width:calc(100% - 22px);height:auto;border-radius:6px;margin:0 11px;display:none;object-fit:contain;" alt="">
    <div class="nCovName" style="font-size:10px;color:#8a8a8a;padding:0 11px;">${TL('ui.noneSelected','（未選択）')}</div>`;
}
function renderInfoCards(){
  for(const el of [...infoWorldEl.querySelectorAll('.iGrp[data-t]')]) if(!infoGraph.nodes[el.dataset.node]) el.remove();
  for(const id in infoGraph.nodes){ const n=infoGraph.nodes[id];
    let el=infoWorldEl.querySelector(`.iGrp[data-node="${id}"]`);
    if(!el){ el=document.createElement('div'); el.className='iGrp'; el.dataset.node=id; el.dataset.t=n.t;
      el.innerHTML=srcCardHTML(n.t);
      const pd=document.createElement('div'); pd.className='nPort'; pd.dataset.port=id; pd.innerHTML='<i></i>';   // 出力ポート（カードの子=前後関係に従う）
      el.appendChild(pd);
      el.style.zIndex=String(++_inZTop);   // 新規生成（ペースト/追加/ドロップ）は最前面に出す
      infoWorldEl.appendChild(el);
      // フィールド→そのノードのdataへ（接続中なら確定情報として即反映）
      el.querySelectorAll('[data-f]').forEach(inp=>{
        const f=inp.dataset.f;
        const apply=()=>{ const nd2=infoGraph.nodes[id]; if(!nd2) return; infoSnapBurst(); nd2.data[f]=inp.value; metaDirty=true; applyInfoGraph(); };
        inp.addEventListener('input',ev=>{ if(!ev.isComposing) apply(); });
        inp.addEventListener('compositionend',apply); });
      el.querySelectorAll('.nDiffs input').forEach(cb=>{ cb.addEventListener('change',()=>{
        const nd2=infoGraph.nodes[id]; if(!nd2) return; infoSnapshot(); (nd2.data.diffs=nd2.data.diffs||{})[cb.dataset.d]=cb.checked?1:0;
        metaDirty=true; applyInfoGraph(); }); });
      const pk=el.querySelector('.nPick');
      if(pk) pk.addEventListener('click',async()=>{
        _pickOpen='cover'; refreshInfoCards();
        const cur2=infoGraph.nodes[id];
        const pr=await pickCoverImage(cur2&&cur2.data.nativePath);
        _pickOpen=null;
        if(pr){ const nd2=infoGraph.nodes[id]; if(nd2){ infoSnapshot(); nd2.data.name=pr.fh.name; nd2.data.nativePath=pr.path; _coverHandles[id]=pr.fh;
          metaDirty=true; applyInfoGraph(); } }
        refreshInfoCards(); });
    }
    el.style.left=n.x+'px'; el.style.top=n.y+'px'; el.style.display='flex';
  }
  refreshInfoCards();
}
function refreshInfoCards(){
  for(const el of infoWorldEl.querySelectorAll('.iGrp[data-t]')){ const id=el.dataset.node, n=infoGraph.nodes[id]; if(!n) continue;
    el.classList.toggle('sel',_inSel.has(id));
    el.classList.toggle('srcOn',connectedNodeId(n.t)===id);   // アクティブ書き出しへ接続中=確定
    el.querySelectorAll('[data-f]').forEach(inp=>{ if(document.activeElement===inp) return;
      const v=n.data[inp.dataset.f]??'';
      if(inp.tagName==='SELECT'&&v&&![...inp.options].some(o2=>o2.value===v)){ const o2=document.createElement('option'); o2.value=o2.textContent=v; inp.appendChild(o2); }
      if(inp.value!==v) inp.value=v; });
    el.querySelectorAll('.nDiffs input').forEach(cb=>{ cb.checked=!!(n.data.diffs&&n.data.diffs[cb.dataset.d]); });
    { const dot=el.querySelector('.nPort i');   // ポートドット: 接続=塗りつぶし／未接続=色リング（中は暗）
      if(dot){ const col=INFO_NODE_DEFS[n.t][1], on=(infoGraph.edges||[]).some(ed=>ed.s===id);
        dot.style.background=on?col:'#1b1b1d';
        dot.style.border=on?'1.5px solid #141416':('3px solid '+col); } }
    const pk=el.querySelector('.nPick');
    if(pk){ pk.textContent=((_pickOpen==='cover'||n.data.name||_coverHandles[id])?'📂':'📁')+' '+TL('ui.selImage','画像を選択…');
      const th=el.querySelector('.nThumb'), nm=el.querySelector('.nCovName');
      if(n.data.name||_coverHandles[id]){
        loadCoverPreview({id:'ig:'+id,handle:_coverHandles[id]||null,name:n.data.name});
        const c=_coverImgs.get('ig:'+id);
        if(c&&c.bmp){ const key=(c.key||'')+'';
          if(el.dataset.thumbKey!==key){ el.dataset.thumbKey=key;
            const cc=document.createElement('canvas'); cc.width=c.bmp.width; cc.height=c.bmp.height;
            cc.getContext('2d').drawImage(c.bmp,0,0); th.src=cc.toDataURL('image/png'); }
          th.style.display='block'; }
        nm.textContent=n.data.name||''; }
      else { th.style.display='none'; nm.textContent=TL('ui.noneSelected','（未選択）'); el.dataset.thumbKey=''; } }
  }
}
let infoGraph=defaultInfoGraph();
const infoWorldEl=document.getElementById('infoWorld'), infoSvg=document.getElementById('infoEdgeSvg'), infoPortSvg=document.getElementById('infoPortSvg'), inspEl=document.getElementById('inspcol');
function infoCamApply(){ const c=infoGraph.cam; infoWorldEl.style.transform=`translate(${c.x}px,${c.y}px) scale(${c.s})`; }
function infoCenterView(){   // 全ノードの中央へ（.キー / 初期表示）。ズーム率は維持
  const r=inspEl.getBoundingClientRect(); if(r.width<50||r.height<50) return;
  let x0=1e9,y0=1e9,x1=-1e9,y1=-1e9;
  for(const el of infoNodeEls()){ if(el.style.display==='none') continue;
    const p=el.dataset.out?infoGraph.outs[el.dataset.out]:infoGraph.nodes[el.dataset.node]; if(!p) continue;
    x0=Math.min(x0,p.x); y0=Math.min(y0,p.y);
    x1=Math.max(x1,p.x+(el.offsetWidth||280)); y1=Math.max(y1,p.y+(el.offsetHeight||120)); }
  if(x1<x0) return;
  infoGraph.cam.s=1;   // .=最初の状態と同じビュー（ズーム100%・ノード群の中心を画面中央へ）
  infoGraph.cam.x=Math.round((r.width-(x1-x0))/2-x0);
  infoGraph.cam.y=Math.round((r.height-(y1-y0))/2-y0);
  infoCamApply(); drawInfoEdges();
}
function infoAutoCenter(){   // 初回表示時のみ自動センター（ユーザー操作後は発動しない）
  if(!infoGraph.cam||!infoGraph.cam.auto) return;
  delete infoGraph.cam.auto; infoCenterView();
}
function infoNodeEls(){ return [...inspEl.querySelectorAll('.iGrp[data-node]')]; }
function layoutInfoNodes(){
  renderInfoCards();
  renderOutCards();
  infoCamApply(); drawInfoEdges();
}
function infoPortOf(id){   // ソースノード（インスタンス）の出力ポート（右辺中央）のワールド座標
  const n=infoGraph.nodes[id]; if(!n) return null;
  const el=inspEl.querySelector(`.iGrp[data-node="${id}"]`);
  return {x:n.x+(el?el.offsetWidth:340), y:n.y+(el?el.offsetHeight:120)/2};
}
function infoOutPortOf(oid,k){   // 書き出しノードの入力ポート（左辺・縦中央に3つ・色分け）
  const o=infoGraph.outs[oid]||{x:0,y:0};
  const el=infoWorldEl&&infoWorldEl.querySelector(`.iGrp[data-out="${oid}"]`);
  const h=(el&&el.offsetHeight)||160;
  return {x:o.x,y:o.y+h/2+(INFO_SRCS.indexOf(k)-1)*20};
}
function drawInfoEdges(){   // エッジ={s:ノードid,o:出力id}。同タイプは1つのoutに1本（繋ぎ替え=差し替え）。休止outへの線は薄く
  let under='', over='';   // under=ポートラベル（カードの下層）/ over=ドラッグ中のゴースト線のみ
  const edges=infoGraph.edges||[];
  // エッジは「出どころカードの子SVG」に描く=カードと同じ重なり順（前面ノードの線は前面・背面ノードの線は背面。全面前 or 全面後だと重なりで破綻するため）
  const bySrc={};
  for(const ed of edges) (bySrc[ed.s]=bySrc[ed.s]||[]).push(ed);
  for(const el of infoWorldEl.querySelectorAll('.iGrp[data-t]')){
    const id=el.dataset.node, n=infoGraph.nodes[id], list=bySrc[id];
    let svg=el.querySelector(':scope > .edgeSvg');
    if(!list||!n){ if(svg) svg.innerHTML=''; continue; }
    if(!svg){ svg=document.createElementNS('http://www.w3.org/2000/svg','svg'); svg.setAttribute('class','edgeSvg');
      svg.style.cssText='position:absolute;left:0;top:0;width:10px;height:10px;overflow:visible;pointer-events:none;';
      el.appendChild(svg); }
    let s2='';   // 座標はカード原点基準（world座標 - カード位置）
    for(const ed of list){ const pt=infoPortOf(ed.s); if(!pt) continue;
      const t=infoNodeT(ed.s), op=infoOutPortOf(ed.o,t), col=INFO_NODE_DEFS[t][1], act=ed.o===infoGraph.activeOut;
      const dx=Math.max(46,Math.abs(op.x-pt.x)/2);
      s2+=`<path d="M${pt.x-n.x},${pt.y-n.y} C${pt.x+dx-n.x},${pt.y-n.y} ${op.x-dx-n.x},${op.y-n.y} ${op.x-n.x},${op.y-n.y}" fill="none" stroke="${col}" stroke-width="2" opacity="${act?1:0.35}"/>`; }   // 切断=ポートをクリック（線自体は掴まない）
    svg.innerHTML=s2;
  }
  // 書き出しノードのポートラベル（線と同じ下層）
  for(const oid in infoGraph.outs){ const act=oid===infoGraph.activeOut;
    for(const k of INFO_SRCS){ const op=infoOutPortOf(oid,k);
      under+=`<text x="${op.x+9}" y="${op.y+3}" font-size="8.5" fill="${act?'#c8ccd4':'#7a7a82'}" style="pointer-events:none">${TL('node.'+k,INFO_NODE_DEFS[k][0])}</text>`; } }
  if(_inWire) over+=`<path d="M${_inWire.ax},${_inWire.ay} L${_inWire.x2},${_inWire.y2}" fill="none" stroke="${INFO_NODE_DEFS[_inWire.t][1]}" stroke-width="2" stroke-dasharray="5 4" style="pointer-events:none"/>`;
  infoSvg.innerHTML=under;
  infoPortSvg.innerHTML=over;
}
let _inDrag=null,_inPan=null,_inWire=null,_inZTop=10;
function infoWorldXY(e){ const r=inspEl.getBoundingClientRect(), c=infoGraph.cam;
  return {x:(e.clientX-r.left-c.x)/c.s, y:(e.clientY-r.top-c.y)/c.s}; }
inspEl.addEventListener('pointerdown',e=>{
  if(e.button===1&&!e.ctrlKey&&!e.altKey&&!e.metaKey){ e.preventDefault();   // パン=中ドラッグ（素/Shift併用可・Ctrl/Alt/Metaは無効。2D画面は素の中ボタンでスクロール）
    delete infoGraph.cam.auto;
    _inPan={x:e.clientX,y:e.clientY,cx:infoGraph.cam.x,cy:infoGraph.cam.y};
    try{inspEl.setPointerCapture(e.pointerId);}catch(_){} return; }
  if(e.button!==0) return;
  const port=e.target.closest&&e.target.closest('[data-port]');
  const oport=e.target.closest&&e.target.closest('[data-oport]');
  if(port){   // ソース側（出力）ポート: ドラッグ=接続／空きへ捨てる=はがす（Comfy/Blender/Fusion流）
    e.preventDefault(); const k=port.dataset.port, pt=infoPortOf(k);
    if(pt){ const pre=dumpDomain('info');   // 選択変更の前に控える（「選択も1動作」＝NLEと同じ流儀）
      _inSel=new Set([k]); infoSelApply(); refreshInfoCards();
      _inWire={mode:'src',k,t:infoNodeT(k),ax:pt.x,ay:pt.y,x2:pt.x,y2:pt.y,sx:e.clientX,sy:e.clientY,moved:false,pre}; drawInfoEdges();
      try{inspEl.setPointerCapture(e.pointerId);}catch(_){} } return; }
  if(oport){   // 書き出し側（入力）ポート: 既存の線を掴んだ瞬間に引き抜いて保持（空きへ捨てる=はがす／別ソースへ=繋ぎ直し）
    e.preventDefault(); const [oid,t]=oport.dataset.oport.split('|');
    const pre=dumpDomain('info');   // 引き抜き前の状態（確定時に変化があればUndoへ）
    const ed=(infoGraph.edges||[]).find(x2=>x2.o===oid&&infoNodeT(x2.s)===t);
    let ax,ay,held=null,heldIdx=-1;
    if(ed){ const sp=infoPortOf(ed.s); ax=sp?sp.x:0; ay=sp?sp.y:0; held=ed.s; heldIdx=infoGraph.edges.indexOf(ed);
      infoGraph.edges=(infoGraph.edges||[]).filter(x2=>x2!==ed); applyInfoGraph(); metaDirty=true; }
    else { const op=infoOutPortOf(oid,t); ax=op.x; ay=op.y; }
    const w=infoWorldXY(e);
    _inWire={mode:'in',oid,t,held,heldIdx,ax,ay,x2:w.x,y2:w.y,sx:e.clientX,sy:e.clientY,moved:false,pre}; drawInfoEdges();
    try{inspEl.setPointerCapture(e.pointerId);}catch(_){} return; }
  const h3=e.target.closest('h3'), nd=e.target.closest('.iGrp[data-node]');
  if(nd){ const key=nd.dataset.node, pre=dumpDomain('info');   // クリックで選択（Shift=追加/解除・選択済みノードはそのまま=グループ移動可）
    if(e.shiftKey){ _inSel.has(key)?_inSel.delete(key):_inSel.add(key); }
    else if(!_inSel.has(key)) _inSel=new Set([key]);
    infoSelApply();
    nd.style.zIndex=String(++_inZTop);                  // クリックしたノードを手前へ（重なり解決・ポートも一緒に前へ）
    { const sup=_infoSnapSup; _infoSnapSup=true;        // 選択＋アクティブ化を合わせて1ステップ（「選択も1動作」）
      if(nd.dataset.out) setActiveOut(nd.dataset.out);  // 書き出しノードはクリックでアクティブ化（他は休止=灰色）
      _infoSnapSup=sup;
      if(dumpDomain('info')!==pre) pushHist('info',pre); } }
  if(h3&&nd){ e.preventDefault();
    const grab=nd.dataset.node, keys=_inSel.has(grab)?[..._inSel]:[grab];
    _inDrag={sx:e.clientX,sy:e.clientY,items:keys.map(key=>{ const isOut=key.startsWith('out:');
      const p=isOut?infoGraph.outs[key.slice(4)]:infoGraph.nodes[key];
      return p?{key,isOut,ox:p.x,oy:p.y}:null; }).filter(Boolean)};   // 選択中なら全員まとめて移動
    try{inspEl.setPointerCapture(e.pointerId);}catch(_){} return; }
  if(!nd&&e.button===0){   // 空きから左ドラッグ=範囲選択（クリックのみ=解除）
    _inBand={x0:e.clientX,y0:e.clientY,x1:e.clientX,y1:e.clientY,add:e.shiftKey,moved:false,pre:dumpDomain('info')};
    try{inspEl.setPointerCapture(e.pointerId);}catch(_){} }
});
let _inSel=new Set();   // 選択ノード（複数可。'm1' / 'out:o1'）
function infoSelApply(){ for(const el of infoNodeEls()) el.classList.toggle('sel',_inSel.has(el.dataset.node)); }
let _inBand=null,_bandEl=null;   // 空きから左ドラッグ=範囲選択（NLE/3Dと同じマーキー）
function drawBand(){ if(!_inBand){ if(_bandEl) _bandEl.style.display='none'; return; }
  if(!_bandEl){ _bandEl=document.createElement('div');
    _bandEl.style.cssText='position:absolute;border:1px dashed var(--accent);background:rgba(129,96,227,.12);pointer-events:none;z-index:80;';
    inspEl.appendChild(_bandEl); }
  const r=inspEl.getBoundingClientRect();
  _bandEl.style.display='block';
  _bandEl.style.left=(Math.min(_inBand.x0,_inBand.x1)-r.left)+'px';
  _bandEl.style.top=(Math.min(_inBand.y0,_inBand.y1)-r.top)+'px';
  _bandEl.style.width=Math.abs(_inBand.x1-_inBand.x0)+'px';
  _bandEl.style.height=Math.abs(_inBand.y1-_inBand.y0)+'px';
}
inspEl.addEventListener('pointermove',e=>{
  if(_inPan){ infoGraph.cam.x=_inPan.cx+(e.clientX-_inPan.x); infoGraph.cam.y=_inPan.cy+(e.clientY-_inPan.y); infoCamApply(); drawInfoEdges(); return; }
  if(_inWire){ const w=infoWorldXY(e); _inWire.x2=w.x; _inWire.y2=w.y;
    if(Math.abs(e.clientX-_inWire.sx)+Math.abs(e.clientY-_inWire.sy)>4) _inWire.moved=true;
    drawInfoEdges(); return; }
  if(_inBand){ _inBand.x1=e.clientX; _inBand.y1=e.clientY;
    if(Math.abs(_inBand.x1-_inBand.x0)+Math.abs(_inBand.y1-_inBand.y0)>3) _inBand.moved=true;
    drawBand(); return; }
  if(_inDrag){ const s=infoGraph.cam.s, dx=(e.clientX-_inDrag.sx)/s, dy=(e.clientY-_inDrag.sy)/s;
    if(!_inDrag.snapped){ _inDrag.snapped=1; infoSnapshot(); }   // 移動もUndo対象（掴んだだけでは積まない）
    for(const it of _inDrag.items){ const p=it.isOut?infoGraph.outs[it.key.slice(4)]:infoGraph.nodes[it.key];
      if(p){ p.x=it.ox+dx; p.y=it.oy+dy; } }
    layoutInfoNodes(); metaDirty=true; }
});
addEventListener('pointerup',e=>{
  if(_inBand){ const b=_inBand; _inBand=null; drawBand();   // 範囲選択の確定（Shift=追加・クリックのみ=解除）
    if(b.moved){
      const x0=Math.min(b.x0,b.x1),x1=Math.max(b.x0,b.x1),y0=Math.min(b.y0,b.y1),y1=Math.max(b.y0,b.y1);
      const hit=new Set(b.add?[..._inSel]:[]);
      for(const el of infoNodeEls()){ const rc=el.getBoundingClientRect();
        if(rc.left<=x1&&rc.right>=x0&&rc.top<=y1&&rc.bottom>=y0) hit.add(el.dataset.node); }
      _inSel=hit; }
    else if(!b.add) _inSel=new Set();
    infoSelApply(); refreshOutCards(); refreshInfoCards();
    if(b.pre&&dumpDomain('info')!==b.pre) pushHist('info',b.pre);   // 選択の変化も1動作（NLEと同じ）
    _inDrag=null; _inPan=null; return; }
  if(_inWire){ const wi=_inWire; _inWire=null;
    const w=infoWorldXY(e);
    if(wi.mode==='src'){
      if(wi.moved){
        let target=null;   // 書き出しノード上/対応ポート付近 → 接続（同タイプ差し替え）
        for(const oid in infoGraph.outs){ const op=infoOutPortOf(oid,wi.t), o=infoGraph.outs[oid];
          const el=infoWorldEl.querySelector(`.iGrp[data-out="${oid}"]`);
          if((Math.hypot(w.x-op.x,w.y-op.y)<26)||(el&&w.x>=o.x-12&&w.x<=o.x+el.offsetWidth&&w.y>=o.y&&w.y<=o.y+el.offsetHeight)){ target=oid; break; } }
        if(target){
          if(!(infoGraph.edges||[]).some(ed=>ed.s===wi.k&&ed.o===target)){
            const rep=(infoGraph.edges||[]).some(ed=>ed.o===target&&infoNodeT(ed.s)===wi.t);
            infoGraph.edges=(infoGraph.edges||[]).filter(ed=>!(ed.o===target&&infoNodeT(ed.s)===wi.t));   // 同タイプは1本=差し替え
            infoGraph.edges.push({s:wi.k,o:target});
            applyInfoGraph(); metaDirty=true;
            stat(tf('msg.infoConnected','「{node}」を書き出し（{target}）へ接続{rep}しました',{node:INFO_NODE_DEFS[wi.t][0],target,rep:rep?t('word.replaced','（差し替え）'):''})); }
          else stat('既に接続されています'); }
        else {   // 空きへ捨てる=この口の線を全部はがす（Comfy/Blender/Fusion流）
          const cut=(infoGraph.edges||[]).filter(ed=>ed.s===wi.k);
          if(cut.length){ infoGraph.edges=(infoGraph.edges||[]).filter(ed=>ed.s!==wi.k);
            applyInfoGraph(); metaDirty=true;
            stat(tf('msg.infoUnplugN','「{node}」の配線を{cnt}はがしました',{node:INFO_NODE_DEFS[wi.t][0],cnt:cut.length>1?cut.length+'本':''})); } }
      }   // クリックのみ=何もしない
    } else {   // mode 'in'（書き出し側から引き抜いた線）
      if(!wi.moved){   // クリックのみ=引き抜きを取り消して元へ戻す（元の位置へ=並び順不変で空Undoを積まない）
        if(wi.held){ infoGraph.edges.splice(Math.min(Math.max(wi.heldIdx,0),infoGraph.edges.length),0,{s:wi.held,o:wi.oid}); applyInfoGraph(); metaDirty=true; } }
      else {
        let src=null;   // ソースノード上/そのポート付近 → そのソースへ繋ぎ直し
        for(const id in infoGraph.nodes){ const n=infoGraph.nodes[id];
          const el=infoWorldEl.querySelector(`.iGrp[data-node="${id}"]`); const pt2=infoPortOf(id);
          if((pt2&&Math.hypot(w.x-pt2.x,w.y-pt2.y)<26)||(el&&w.x>=n.x&&w.x<=n.x+el.offsetWidth&&w.y>=n.y&&w.y<=n.y+el.offsetHeight)){ src=id; break; } }
        if(src&&infoNodeT(src)===wi.t){
          infoGraph.edges=(infoGraph.edges||[]).filter(ed=>!(ed.o===wi.oid&&infoNodeT(ed.s)===wi.t));
          infoGraph.edges.push({s:src,o:wi.oid});
          applyInfoGraph(); metaDirty=true;
          stat(tf('msg.infoRewired','「{node}」を書き出し（{oid}）へ繋ぎ直しました',{node:INFO_NODE_DEFS[wi.t][0],oid:wi.oid})); }
        else if(src){ stat(tf('msg.infoTypeMismatch','タイプが違います（このポートは{node}用）',{node:INFO_NODE_DEFS[wi.t][0]}));
          if(wi.held) applyInfoGraph(); }
        else if(wi.held){ applyInfoGraph(); metaDirty=true; stat(tf('msg.infoUnplug','「{node}」の配線をはがしました',{node:INFO_NODE_DEFS[wi.t][0]})); }   // 空き=はがれたまま
      }
    }
    if(wi.pre&&dumpDomain('info')!==wi.pre) pushHist('info',wi.pre);   // 実際に配線が変わった時だけUndoへ
    drawInfoEdges(); _inDrag=null; _inPan=null; return; }
  _inDrag=null; _inPan=null; });
inspEl.addEventListener('wheel',e=>{ if(e.target.closest('select')) return; e.preventDefault();   // ズーム=ホイール（カーソル中心）
  if(e.ctrlKey||e.altKey||e.metaKey||e.shiftKey) return;   // 未設定の修飾+ホイールは無効（ズームは素のホイールのみ）
  const r=inspEl.getBoundingClientRect(), mx=e.clientX-r.left, my=e.clientY-r.top, c=infoGraph.cam;
  delete infoGraph.cam.auto;
  const k=e.deltaY<0?1.1:1/1.1, ns=Math.max(0.4,Math.min(2.2,c.s*k)), f=ns/c.s;
  c.x=mx-(mx-c.x)*f; c.y=my-(my-c.y)*f; c.s=ns; infoCamApply(); drawInfoEdges(); },{passive:false});
inspEl.addEventListener('contextmenu',e=>{
  if(/^(INPUT|TEXTAREA|SELECT)$/.test(e.target.tagName||'')) return;   // 入力欄はブラウザ標準メニュー（コピー/貼り付け）を通す
  e.preventDefault();
  const nd=e.target.closest('.iGrp[data-node]');
  if(nd) return;   // ノード上の右クリックメニューは廃止（複製=Ctrl+C/V・削除=X で統一）
  const w=infoWorldXY(e), wx=w.x, wy=w.y;
  showMenu(e.clientX,e.clientY,[
    ...Object.keys(INFO_NODE_DEFS).map(k=>[
      tf('ctx.addInfoNode','＋ {node} ノード',{node:INFO_NODE_DEFS[k][0]}),()=>addSrcNode(k,wx,wy)]),
    [t('ctx.addOutNode','＋ 書き出しノード'),()=>addOutNode(wx,wy)],
  ]);
});
function addSrcNode(t,x,y,copyFrom){   // 新規/複製=独立したデータ箱（複製は中身ごとコピー・カバーは画像参照もコピー）
  infoSnapshot();
  const id=t.slice(0,1)+(++infoGraph.nseq);
  const src=copyFrom&&infoGraph.nodes[copyFrom];
  infoGraph.nodes[id]={t,x,y,data:src?structuredClone(src.data):defInfoData(t)};
  if(t==='cover'&&copyFrom&&_coverHandles[copyFrom]) _coverHandles[id]=_coverHandles[copyFrom];
  _inSel=new Set([id]); layoutInfoNodes(); infoSelApply(); metaDirty=true;
  stat(tf('msg.infoNodeAdded','{node}ノードを{action}しました',{node:INFO_NODE_DEFS[t][0],action:copyFrom?TL('word.duplicated','複製'):TL('word.added','追加')})); return id; }
function deleteSrcNode(id){ const n=infoGraph.nodes[id]; if(!n) return;
  infoSnapshot();
  delete infoGraph.nodes[id]; delete _coverHandles[id];
  { const c=_coverImgs.get('ig:'+id); if(c&&c.bmp&&c.bmp.close) try{ c.bmp.close(); }catch(_){}
    _coverImgs.delete('ig:'+id); }   // デコード済みカバー画像も解放（複製/削除の繰り返しでのメモリリーク防止）
  infoGraph.edges=(infoGraph.edges||[]).filter(ed=>ed.s!==id);
  _inSel.delete(id);
  applyInfoGraph(); layoutInfoNodes(); metaDirty=true; stat('ノードを削除しました'); }
setInterval(()=>{ if(nodeColMode==='info') drawInfoEdges(); },400);   // カード高さの変化（カバー画像読込等）に追従
layoutInfoNodes(); applyInfoGraph();
// INFOモード時のショートカット表示（旧NODE流儀）。NLEに戻したら元の表示へ
const KEYSHTML_NLE=(document.querySelector('#nodeKeys .mkbody')||document.getElementById('nodeKeys')).innerHTML;
const KEYSHTML_NODE=[['新規ノード','🖱️ 右クリック'],['全ノードの中央へ','.']]
  .map(([d,k])=>`<div class="mkrow"><span class="mkd">${d}</span><span class="mk">${k}</span></div>`).join('');
document.getElementById('iExport').onclick=()=>{   // 必須項目（音源/ノーツ/フォルダー名/出力先）が揃うまで書き出しは止める
  const miss=exportReadiness().filter(x=>x.req&&!x.ok);
  if(miss.length){ showErr(tf('msg.exportMissing','書き出せません: {list} が足りません',{list:miss.map(m=>m.label.replace(/（.*/,'')).join('・')})); return; }
  const fEl=infoWorldEl.querySelector(`.iGrp[data-out="${infoGraph.activeOut}"] .oForceEgg`);
  exportMap(!!(fEl&&fEl.checked)); };
// ---- ノーツ色スウォッチ（設定グループ。クリック→カラーピッカー→3D/2Dへ即反映） ----
function noteSwSvg(col){ return `<svg viewBox="0 0 64 64"><rect x="8" y="8" width="48" height="48" rx="11" fill="${col}"/><path d="M21 23 H43 L32 34 Z" fill="#fff"/></svg>`; }
function laserSwSvg(col){ return `<svg viewBox="0 0 64 64"><rect x="8" y="8" width="48" height="48" rx="11" fill="${col}"/><rect x="28" y="16" width="8" height="32" rx="3" fill="#fff"/></svg>`; }   // 縦ビーム=レーザー
setInterval(refreshInspector,400);
// 重複チェックのチップ（左下・chartInfoの真上・400ms間隔で再スキャン）
{ const dupEl=document.getElementById('dupChip');
  dupEl.addEventListener('click',e=>{ const a=e.target.dataset.act;
    if(a==='np') dupJumpItem('n',-1); else if(a==='nn') dupJumpItem('n',1);
    else if(a==='lp') dupJumpItem('l',-1); else if(a==='ln') dupJumpItem('l',1); });
  let _dupKey='';
  setInterval(()=>{
    scanDups();
    const n=dupNoteSet.size, l=dupLightSet.size;   // 箇所(グループ数)ではなく重複している「個数」を表示（＝偶数になる）
    if(!n&&!l){ if(dupEl.style.display!=='none'){ dupEl.style.display='none'; _dupKey=''; } return; }
    const key=n+'|'+l;
    if(key!==_dupKey){ _dupKey=key;
      dupEl.innerHTML=(n?`⚠ 重複ノーツ <b>${n}</b><span class="dj" data-act="np">‹</span><span class="dj" data-act="nn">›</span>`:'')
        +(n&&l?'<span style="color:#5a5a5a;padding:0 4px">｜</span>':'')
        +(l?`⚠ 重複ライト <b>${l}</b><span class="dj" data-act="lp">‹</span><span class="dj" data-act="ln">›</span>`:'');
      dupEl.style.display='flex'; }
    dupEl.style.left='14px'; dupEl.style.bottom='14px'; dupEl.style.top='auto';   // 一番左下（#main=3D編集ペインの左下に固定。chartInfoは右インスペクタへ移設済みのため基準にしない）
  },400); }
function fmt(s){ s=s||0; return `${Math.floor(s/60)}:${Math.floor(s%60).toString().padStart(2,'0')}`; }
let pv4On=false, _PV4=null, _pv4Hist=-1;
async function setPv4Mode(v){
  if(v){
    if(!_PV4){ try{ _PV4=await import('../../preview-v4/preview-v4.js?v='+Date.now()); }
      catch(e){ showErr(tf('msg.v2EngineFail','V2エンジンの読込に失敗: {err}',{err:e&&e.message||e})); return; }
      _PV4.init(document.getElementById('pv4host')); } }
  pv4On=v;
  const h=document.getElementById('pv4host'); if(h) h.style.display=v?'block':'none';
  if(_PV4){ _PV4.setActive(v); if(v){ pv4SyncEnv(); pv4Push(); _PV4.setVisible(pvShowNotes,pvShowLights); if(_PV4.setStructVisible) _PV4.setStructVisible(pvShowStruct); if(_PV4.setAmbient) _PV4.setAmbient(pvShowAmbient); if(typeof applyPvSettings==='function') applyPvSettings(); } }   // preview設定(bloom/ambient等)を反映
  const b=document.getElementById('pvVisV4'); if(b) b.classList.toggle('on',v);
  pvFinderVis();
}
let pv4EnvOverride='';   // '' = 譜面の環境を自動（V2/ARC共通のステージ選択）
// ArcViewer対応の13環境（ARCのsupportedEnvironments順＝customenvironment index）。V2の書き出しJSONと同一集合。
const PV_ENVS=['DefaultEnvironment','OriginsEnvironment','TriangleEnvironment','NiceEnvironment','BigMirrorEnvironment','DragonsEnvironment','KDAEnvironment','MonstercatEnvironment','PanicEnvironment','TimbalandEnvironment','FitBeatEnvironment','LinkinParkEnvironment','KaleidoscopeEnvironment'];
function pv4EnvOf(){
  if(pv4EnvOverride) return pv4EnvOverride;
  const e=(infoBase&&infoBase._environmentName)||'';   // 曲(MEDIA)のステージは読まない＝設定ノードのenvのみ。無ければDefault
  return e||'DefaultEnvironment';
}
function pv4SyncEnv(){ if(_PV4&&_PV4.setEnvironment) _PV4.setEnvironment(pv4EnvOf()); }
function pvFillEnvSel(){   // ステージ選択ドロップダウン（pv4）
  const sel=document.getElementById('pvEnvSel'); if(!sel) return;
  if(!sel.dataset.filled){ sel.dataset.filled='1';
    const short=n=>n.replace(/Environment$/,'');
    sel.innerHTML='<option value="">自動（譜面の環境）</option>'+PV_ENVS.map(n=>`<option value="${n}">${short(n)}</option>`).join('');
    sel.onchange=()=>{ pv4EnvOverride=sel.value;   // '' = 自動
      if(pv4On) pv4SyncEnv(); };
  }
  sel.value=pv4EnvOverride;   // 現在の選択を反映
}
function pv4NjsOf(){ return njsOffCur().njs; }   // 現在の難易度の飛来速度（編集/取得済みnjsCfg→無ければ既定）をプレビューへ反映
function pv4Push(){   // 現難易度のフラット配列をV2へ（編集で再呼び出し）
  if(!_PV4) return;
  // 環境同期はここ（配置ごと）ではやらない＝毎ノート再ロードの「消える」嵐を防ぐため。
  // 環境の追従は applyInfoGraph(曲/環境確定時) と setPv4Mode(切替時) の pv4SyncEnv に一本化。
  _PV4.setData({notes,bombs,walls,arcs,chains,lights:lightEvents,bpm:BPM,njs:pv4NjsOf(),njsOffset:njsOffCur().offset,songDur,
    noteRed:RED,noteBlue:BLUE,laserRed:LRED,laserBlue:LBLUE,laserRedB:LRED_B,laserBlueB:LBLUE_B});   // ノーツ/レーザー色をV2へ同期
  _pv4Hist=undoStack.length+redoStack.length*1000;
}
function pvFinderVis(){ const f=document.getElementById('pvFinder');
  const ext=pv4On;
  if(f) f.style.display=ext?'none':'';
  const es=document.getElementById('pvEnvSel'); if(es) es.style.display='none'; }   // ステージ切替は当面削除（ヘルバ様指示）
function pv4Frame(){ if(!pv4On||!_PV4) return;
  const h=undoStack.length+redoStack.length*1000;
  if(h!==_pv4Hist) pv4Push();
  _PV4.frame(playing?aTime():beatToTimeTM(cur), playing); }
let _tickErrAt=0;
function tick(){   // 1フレームの例外で描画ループごと死なない（=アプリが固まらない）。エラーは表面化させて継続
  try{ _tick(); }
  catch(err){ console.error('tickエラー:',err);
    if(performance.now()-_tickErrAt>5000){ _tickErrAt=performance.now();
      try{ showErr(tf('msg.drawErr','描画エラーが発生しました（動作は継続）: {err}',{err:err&&err.message||err})); }catch(_){}}
    requestAnimationFrame(tick); }   // 本体末尾のRAF登録に到達していないので自前で継続
}
function _tick(){
  if(playing){ cur=timeToBeatTM(aTime());
    if(cur>prevPlayBeat){ let hit=false;
      for(const n of notes){ if(n.beat>prevPlayBeat&&n.beat<=cur&&layerVisible('n',n._tr||0)){ hit=true; break; } }   // ミュート/ソロ対象外のレーンは通過音を鳴らさない
      if(!hit) for(const c4 of chains){ if(c4.b>prevPlayBeat&&c4.b<=cur&&layerVisible('n',c4._tr||0)){ hit=true; break; } }   // チェーンは頭ノーツ通過で鳴る（ヘルバ様指摘: 無音だった）
      if(hit) blip();
      const mn=metroNode();
      if(mn&&mn.data&&mn.data.on&&Math.floor(cur)>Math.floor(prevPlayBeat)){   // 拍頭（整数拍）をまたいだ
        metroTick(); metroFlashMs=performance.now(); } }
    prevPlayBeat=cur;
    { const _mend=msegs().reduce((m,sg)=>Math.max(m,beatToTimeTM(sg.beat)+sg.dur),0);   // 曲末（最後のセグメント末尾）で自動リピート
      if(_mend>0&&aTime()>=_mend-0.03){ pause(); cur=0; offset=0; prevPlayBeat=-1; play(); } } }
  // ジャンプのイージング（停止中のみ。介入検知=前フレームと違うcurなら他操作が動かした→中断）
  if(playing) curAnim=null;
  else if(curAnim){
    if(cur!==curAnim.last) curAnim=null;
    else{ const p=Math.min(1,(performance.now()-curAnim.start)/curAnim.dur);
      cur=curAnim.from+(curAnim.to-curAnim.from)*(1-Math.pow(1-p,3));   // ease-out
      offset=beatToTimeTM(cur); curAnim.last=cur; if(p>=1) curAnim=null; } }
  // 音声出力レイテンシ補正 + 手動AVオフセット: 再生中は「耳に届いている時刻」に映像を合わせる
  const latB=playing?(((actx.outputLatency||actx.baseLatency||0)+avOffset/1000)*bpmAtBeat(cur)/60):0;   // 微小量の近似でOK（viewBeatと同じ理由）
  const curV=playing?Math.max(playStartB,cur-latB):cur;   // 補正は開始拍を下回らない（再生開始時に一瞬後退して見えるのを防止）
  // 3Dビューの原則（2026-07-14改）: 配置モード=再生中はビューがヘッドに追走＝世界がスクロール（vwB=nullの定点機構）。編集モード=カメラと再生ヘッドは非連動＝ビューは固定しヘッドだけが動く（ヘルバ様指定）
  if(vwB!=null&&playing&&camMode!=='edit'){ if(vwPlayD==null) vwPlayD=cur-vwB;
    vwB=Math.max(0,curV-vwPlayD); }             // 編集モードはvwB固定＝ヘッド非追従（配置モードはvwB=nullで別機構により追従）
  const viewB=(vwB!=null)?vwB:curV;             // 3Dワールドの表示アンカー（座標の基準。再生中は下の追走でvwBがヘッドに追随＝世界スクロール）
  let vLo=curV-24, vHi=curV+24;   // 両モード共通=再生ヘッド±24拍のみ描画（過去24拍超は消え、未来が順次現れる・ヘルバ様指定 2026-07-13）
  playFrame.position.z=(curV-viewB)*ZPB;        // 再生ヘッド（赤枠/床線/◆）はアンカー基準で画面内を移動（追従時はz=0）
  if(camMode==='place') lockBeat=viewBeat();   // 配置モード=赤の再生ラインに配置グリッドを追従（ノーツ/ライト共通＝ライトはplaceMode=falseだが同じ拍に置けるようlockBeatを更新・ヘルバ様指定 2026-07-13）
  // 編集モードはマウスの拍へ配置グリッドを追従。マス上にいる間は pointermove 側(placeMode&&ghostCell)で
  // hoverBeat が凍結されるので、そのまま拍が固定される＝マスのXY選びで拍が飛ばない。
  // ※旧実装は setPlaceMode(true) の瞬間にしか lockBeat を更新せず、セレクトツールで持ち替えて再ロックする前提だった。
  //   セレクト廃止で解除手段が消え「一度ロックしたら黄ラインもグリッドも動かない」状態になっていた（ヘルバ様報告 2026-07-17）
  else if(placeMode&&!lightMode&&!wallStage&&!ghostCell&&!wallHoverCell&&hoverBeat!=null) lockBeat=snapV(hoverBeat);   // 段階式の壁を調整中(wallStage)は拍を動かさない
  // 黄色ライン: 編集モード中はロック拍（=マウス追従）に表示、通常時はマウス追従
  if(camMode==='place'){ mouseLine.visible=false; }   // 配置モード=赤の再生ラインに固定配置。黄ラインは非表示（ヘルバ様指定 2026-07-13）
  else if(placeMode){ mouseLine.visible=true; mouseLine.position.z=(lockBeat-viewB)*ZPB; }
  else { const hb2=hoverBeat??tlHoverBeat;   // NLE/Musicホバー中も3D側に黄ラインを出す（双方向共有）
    mouseLine.visible=hb2!=null; mouseLine.position.z=((hb2??viewB)-viewB)*ZPB; }
  if(wallGhost.visible) updateWallGhost();
  editGroup.visible=placeMode;   // グループ自体は表示（cellPlanesのレイキャスト/ゴースト用）
  // 黄色の12マス枠は黄ライン（=マウス拍）に付ける＝どのマスへ置くのか見て分かる（ヘルバ様指定 2026-07-17）。
  // editGroup は placeMode 時 lockBeat の位置＝mouseLine と同じzなので、表示するだけで黄ラインに乗る。
  // 配置モードは「赤ライン＋自由追従ゴースト」で置く流儀なので従来どおり出さない（黄ライン自体も非表示）
  { const showGrid=(camMode!=='place');
    for(const g of editGridVis) g.visible=showGrid; }
  if(lightMode&&lightHover) lightGhost.position.z=(lightHover.beat-viewB)*ZPB;
  // レーン名は黄色ライン（マウス位置）に追従。ライン非表示時は再生ヘッド付近
  { const lblZ=(mouseLine.visible?mouseLine.position.z:0)-0.55;
    for(const sp of laneNameSprites) sp.position.z=lblZ; }
  editGroup.position.z=placeMode?(lockBeat-viewB)*ZPB:((hoverBeat??viewB)-viewB)*ZPB;
  // 配置モードはcellPlanesが毎フレーム赤ラインへ動くので、ゴーストもマウス直下で毎フレーム更新＝モード切替直後(マウス静止)でも即表示され、Fの色反転が見える（ヘルバ様報告の修正）
  if(placeMode&&camMode==='place'&&!box&&!orbitDrag&&!wallStage&&hoverPane==='main'){ raycaster.setFromCamera(pointer,camera); refreshHoverVisuals(); }
  if(lightMode&&camMode==='place'&&!box&&!orbitDrag&&hoverPane==='main'){ raycaster.setFromCamera(pointer,camera); refreshLightHover(); }   // ライトも配置モードは毎フレーム更新＝赤パネル(再生ヘッド)の拍にゴースト/配置が追従（ノーツと同仕様・ヘルバ様指定 2026-07-13）
  // objects
  updateGizmo();
  updateHoverBox();   // マウス直下のノーツ/ライトを黄色枠で囲う
  updateChainCpSlide();   // チェーン曲率スライダー（選択箱の上に追従）
  updateArcEditSlide();   // アークのmu/tmu/巻き方向パネル（選択箱の上に追従）
  updateChainOverlay();
  ensureSelPool(selection.size); let si=0;
  ensureDupPool(dupNoteSet.size+dupLightSet.size+dupChainCells.size); let di=0;   // 重複の黄色枠（ノーツ/ボム+チェーン頭尾+ライトチップ共用プール。チェーンは最大2マスぶん余分に確保）
  for(const m of meshes){ const o=m.obj;
    let head, tail;
    if(o.kind==='note'||o.kind==='bomb'){ head=o.beat; tail=o.beat; m.group.position.z=(o.beat-viewB)*ZPB;
      const dts=beatToTimeTM(curV)-beatToTimeTM(o.beat);
      if(o.kind==='note'){ const bm=m.group.userData.body;                    // 白枠（判定面）通過直後の一瞬だけ発光。LIGHT編集中は編集ビューのノーツを減光
        if(bm) bm.material=(playing&&dts>=0&&dts<0.16)?NOTE_MATS_HOT[o.c===0?0:1]:(o._ghost?NOTE_MATS_GHOST[o.c===0?0:1]:((objLockedN(o))?NOTE_MATS_DIM[o.c===0?0:1]:mat(o.c))); }   // 配置前(ペースト追従)=ゴースト半透明／LIGHT編集・ロックは減光
      { const gone=dts>=0.16;                                                 // 発光が終わったらプレビューからは消す（停止中も=通過済みは常に非表示。編集ビューには残る）
        if(m.group.userData._pvGone!==gone){ m.group.userData._pvGone=gone;
          m.group.traverse(c=>{ if(gone) c.layers.disable(5); else c.layers.enable(5); }); } } }
    else if(o.kind==='wall'){ head=o.beat; tail=o.beat+o.dur; m.group.position.z=(o.beat-viewB)*ZPB;
      { const gone=(curV-(o.beat+(o.dur||0)))>=0.5;                           // 壁は白枠を抜けてから半拍でプレビューから消す（停止中も。編集ビューには残る）
        if(m.group.userData._pvGone!==gone){ m.group.userData._pvGone=gone;
          m.group.traverse(c=>{ if(gone) c.layers.disable(5); else c.layers.enable(5); }); } } }
    else if(o.kind==='chain'){ head=o.b; tail=o.tb; m.group.position.z=(o.b-viewB)*ZPB;
      const dts=beatToTimeTM(curV)-beatToTimeTM(o.b);                                             // 頭ノーツ通過直後の一瞬だけ発光（ノーツと同じ演出・ヘルバ様指摘: 無反応だった）
      const bm=m.group.userData.body;
      if(bm) bm.material=(playing&&dts>=0&&dts<0.16)?NOTE_MATS_HOT[o.c===0?0:1]:(o._ghost?NOTE_MATS_GHOST[o.c===0?0:1]:((objLockedN(o))?NOTE_MATS_DIM[o.c===0?0:1]:mat(o.c))); }
    else { head=o.b; tail=o.tb; m.group.position.z=(o.b-viewB)*ZPB; }
    m.group.visible=tail>=vLo&&head<=vHi;
    if(!lightMode&&selection.has(o)&&m.group.visible){ const sb=selPool[si++]; sb.visible=true;   // LIGHTING中はノーツの選択枠を出さない（Undo等で選択が復活すると光レーンの上に浮く・2026-07-18）
      { const colHex=((o.kind==='chain'&&chainSelPart==='child')||o.kind==='arc')?0x55aaff:0x50ffb8;   // 子選択チェーン・アーク=青枠 / 他=緑枠
        sb.children[0].material.color.setHex(colHex); sb.children[1].material.color.setHex(colHex); }
      fitBoxTo(sb,o,m); }
    if(!lightMode&&(o.kind==='note'||o.kind==='bomb')&&dupNoteSet.has(o)&&m.group.visible&&di<dupPool.length){   // 重複=一回り大きい黄色枠（LIGHTING中は出さない）
      const db2=dupPool[di++]; db2.visible=true;
      db2.position.copy(m.group.position);
      db2.rotation.z=(o.kind==='note'&&o.d>=4&&o.d<=7)?Math.PI/4:0;
      db2.scale.set(1.3,1.3,o.kind==='note'?NOTE_THIN+0.18:1.3); }
    else if(!lightMode&&o.kind==='chain'&&dupNoteSet.has(o)&&m.group.visible){   // チェーン重複=衝突している頭/尾のマスに黄色枠（LIGHTING中は出さない）
      for(const cell of (dupChainCells.get(o)||[])){ if(di>=dupPool.length) break;
        const db2=dupPool[di++]; db2.visible=true;
        const [px,py]=cellPos(cell.x,cell.y);
        db2.position.set(px,py,m.group.position.z+(cell.beat-(o.b||0))*ZPB);
        db2.rotation.z=0;
        db2.scale.set(1.3,1.3,NOTE_THIN+0.18); } } }
  // 段階式壁の寸法矢印は、上のループで壁の group.z が (o.beat-viewB) へ更新された「後」に位置を取り直す。
  // pointermove時だけの更新では、viewB が動いたフレームで矢印だけ前の位置に取り残される（ヘルバ様報告「一瞬変な場所に←が出る」2026-07-18）
  if(wallStage) updateWallDimArrows();
  for(let i=si;i<selPool.length;i++) selPool[i].visible=false;
  // 2つ以上選択で全体を囲む枠（矢印と同じAABB＝ぴったり一致）。ライトも同じ枠を出す（ヘルバ様指定）＝
  // AABBは updateGizmoLight が gizmoCenter/gizmoHalf に入れているので、見る選択数だけモードで切り替える
  { const nSel=lightMode?lightSelection.size:selection.size;
    if(gizmoValid&&nSel>=2){ const pad=0.1;
      groupSelBox.position.copy(gizmoCenter);
      groupSelBox.scale.set(gizmoHalf.x*2+pad,gizmoHalf.y*2+pad,gizmoHalf.z*2+pad);
      groupSelBox.visible=true; }
    else groupSelBox.visible=false; }
  // beat lines + numbers
  let idx=0; const startB=Math.floor(vLo);
  for(let bn=startB; bn<=Math.ceil(vHi)&&idx<beatPool.length; bn++){ if(bn<vLo) continue; if(bn>vHi) break;
    const z=(bn-viewB)*ZPB;
    const b=beatPool[idx]; b.visible=true; b.position.set(NOTE_DX,0.015,z); const down=(((bn%4)+4)%4)===0;
    b.material.color.setHex(down?0x555555:0x2a2a2a); b.scale.z=down?2.4:1;
    const lb=laneBeatPool[idx]; lb.visible=true; lb.position.y=0.012; lb.position.z=z;
    lb.material.color.setHex(down?0x454545:0x232323);
    const s=numPool[idx]; if(bn>=0){ s.visible=true;
      const tx=numTex(bn);
      if(s.material.map!==tx){ const had=!!s.material.map; s.material.map=tx; if(!had) s.material.needsUpdate=true; }
      s.rotation.y=Math.PI;   // 常に通常視点（camera.x<0側）の向きで固定（反対側から見ても反転しない=ヘルバ様指示）
      s.position.set(-NUMX, 0.022, z); } else s.visible=false;
    idx++; }
  for(;idx<beatPool.length;idx++){ beatPool[idx].visible=false; numPool[idx].visible=false; laneBeatPool[idx].visible=false; }
  numStrip.position.x=-NUMX;   // 灰色バーも左右フリップしない（通常視点側=ノーツとライトの間）
  numStrip.position.z=playFrame.position.z;     // クリック判定帯も数字と同じくヘッド±20拍に追従（右側が押せなくなる回帰の修正）
  updateSpecBand(curV,viewB);   // 帯の位置もここで決める（拍と同じワールド座標に固定＝再生ヘッドには連動させない）。曲未解析時は元の単色のまま
  playDiamond.position.x=numStrip.position.x;   // ◆は常に拍番号レーンの上
  // 3Dビューのマーカー: NLEのレイヤークリップと完全同期（4サブレーンの薄板・クリップ色・S/M反映）
  let mi=0;
  if(sections.length){
    const mkSide=1;   // 常に拍番号の反対側で固定（視点によるフリップ廃止・通常視点=camera.x<0基準）
    for(const s of sections){ const t=s.track||0; if(t>=laneCountOf(secLk(s))) continue;
      if(!layerVisible(secLk(s),t)) continue;              // ミュート/ソロは3Dでは非表示
      const e0=s.beat||0, e1=e0+(s.len||4);
      if(e1<vLo||e0>vHi||mi>=markerPool.length) continue;
      const mp=markerPool[mi++]; mp.visible=true;
      mp.position.set(mkSide*(mkBaseX()+((laneCount()-1)/2-rowOf(secLk(s),t))*0.20),0,0);     // 上段レーンほど外側=NLEと同じ並び
      const col=stripColOf(s);                              // NLEのクリップボックスと同じ色
      const u=mp.userData; u.mat.color.set(col);
      const z0=Math.max((e0-viewB)*ZPB,(vLo-viewB)*ZPB), z1=Math.min((e1-viewB)*ZPB,(vHi-viewB)*ZPB);
      u.bar.position.z=(z0+z1)/2; u.bar.scale.z=Math.max(z1-z0,0.01);
      u.label.material.map=markNameTex(s.label);
      u.label.rotation.y=Math.PI;   // 常に通常視点（camera.x<0側）の向きで固定（反転しない）
      u.label.position.set(0,0.035,(z0+z1)/2);
    } }
  for(;mi<markerPool.length;mi++) markerPool[mi].visible=false;
  // タイムラインマーカー（NLEマーカー帯と同期・白◆+床ライン+名前）
  let tmi=0;
  for(const m of markers){ if(m.beat<vLo||m.beat>vHi||tmi>=tmPool.length) continue;
    const g=tmPool[tmi++]; g.visible=true;
    g.position.z=(m.beat-viewB)*ZPB;
    const tx=tmNameTex(m.name||'');
    const lb=g.userData.lb;
    if(lb.material.map!==tx){ const had=!!lb.material.map; lb.material.map=tx; if(!had) lb.material.needsUpdate=true; } }
  for(;tmi<tmPool.length;tmi++) tmPool[tmi].visible=false;
  // ライトイベント（形状=明るさエンベロープの立体チップ）
  // ブースト配色プレビュー: 各ライトを「自分の拍以前の最新Boost」で判定して固定表示＝マウスで色は変わらない（ヘルバ様指定 2026-07-13）。lightEventsは拍昇順なので通過順にブースト状態を更新
  let ei=0, _curBoost=false;
  const _lastByLane={};                        // 数字表示の間引き用（値変化 or 1拍以上空いた時だけ）
  for(const ev of lightEvents){
    const db=ev.beat-viewB; if(ev.beat>vHi) break;
    if(ev.et===5) _curBoost=(ev.i>0);          // Boostイベント通過＝以降のライトチップに反映（範囲外の前方Boostも含めて正しく積算）
    const pl=_lastByLane[ev.et];
    const numShow=!pl||pl.i!==ev.i||(pl.f??1)!==(ev.f??1)||ev.beat-pl.beat>=1;
    _lastByLane[ev.et]=ev;
    if(ev.beat<vLo) continue;
    if(lightHiddenEv(ev)) continue;             // Chroma中のBOOSTはレーンごと隠す（ヘルバ様指定）
    if(!layerVisible('l',ev._tr||0)) continue;   // ミュート中レーンのライトチップは表示しない
    const li=laneIdxByType[ev.et]; if(li===undefined) continue;
    ensureChips(ei+1); if(ei>=chipPool.length) break;
    const mch=chipPool[ei]; mch.visible=true;
    mch.position.set(LANE_X0+li*LANE_DX,0.02,db*ZPB);
    const kind=chipKindOf(ev.et,ev.i), colHex=chipColorOf(ev.et,ev.i,evChroma(ev),_curBoost), u=mch.userData;
    u.ev=ev;   // チップ→元イベントの逆引き（lightUnderのレイキャスト用。プールの使い回しがあるので毎フレーム貼り直す）
    u.body.geometry=CHIP_GEOS[kind]||CHIP_GEOS.on;
    const evSel=lightSelection.size>0&&lightSelection.has(ev);   // 必ずboolean（0だとthree.jsが描画してしまう）
    u.mat.color.setHex(colHex);
    u.mat.emissive.setHex(colHex).multiplyScalar(0.4);                            // 中身はそのまま見せる
    u.mat.opacity=(kind==='off'?0.6:1)*(objLockedL(ev)?0.4:1);                        // Noteモード中は暗く／ロック中レーンはさらに暗く
    u.edge.visible=evSel;                                                          // 選択=緑の輪郭線
    if(evSel) u.edge.geometry=chipEdges(kind);
    const num=numShow?chipNumOf(ev.et,ev):null;
    u.num.visible=num!==null;
    if(num!==null){ u.num.material.map=numSprTex(num); u.num.material.opacity=1; }
    mch.scale.setScalar(evSel?1.08:1);
    if(dupLightSet.has(ev)&&di<dupPool.length){   // 重複ライト=チップを包む黄色枠
      const db2=dupPool[di++]; db2.visible=true;
      db2.rotation.z=0; db2.position.set(mch.position.x,0.055,mch.position.z);
      db2.scale.set(1.55*LCHIP_K,0.2,0.5); }   // 幅(x)はレーン幅に追従＝チップと同じ係数。高さ/奥行きはチップ寸法が変わっていないので据え置き
    ei++;
  }
  for(let ci=ei;ci<chipPool.length;ci++) chipPool[ci].visible=false;
  for(;di<dupPool.length;di++) dupPool[di].visible=false;   // 重複枠の余りを隠す
  // snap subdivision lines
  let sj=0;
  if(snap<1){ const k0=Math.ceil(Math.max(0,curV-16)/snap), k1=Math.floor((curV+16)/snap);
    for(let k=k0;k<=k1&&sj<subPool.length;k++){ const b=k*snap;
      if(Math.abs(b-Math.round(b))<1e-6) continue;
      const m=subPool[sj]; m.visible=true; m.position.set(NOTE_DX,0.012,(b-viewB)*ZPB);
      const lm=laneSubPool[sj]; lm.visible=true; lm.position.y=0.012; lm.position.z=(b-viewB)*ZPB;
      sj++; } }
  for(;sj<subPool.length;sj++){ subPool[sj].visible=false; laneSubPool[sj].visible=false; }
  drawMeter();
  if(playing!==_lastPlaying){ _lastPlaying=playing; syncPlayIcons(); }
  if(pasteFollow&&!lightMode){            // ペースト追従: マウスの列・段・拍へ
    const at2=hoverBeat!=null?Math.max(0,snapV(hoverBeat)):pasteFollow.at;
    const cell=hoverGridCell();
    const ax2=cell?cell.x:pasteFollow.ax, ay2=cell?cell.y:pasteFollow.ay;
    applyPasteFollowPosition(ax2, ay2, at2); }
  if(nodeColMode!=='info'){ drawOverview(curV); drawSpecPane(curV); drawLayers(curV); }   // INFO表示中は nodepane/overview が display:none＝毎フレームの描画を丸ごとスキップ
  drawPRoll(curV);
  if(curTab==='bodyPv') pv4Frame();   // pv4エンジン（現行プレビュー）
  document.getElementById('time').textContent=`${fmt(beatToTimeTM(cur))} / ${fmt(songDur)} ・ beat ${cur.toFixed(2)} ・ ♪ ${notes.length}${selection.size?` ・ 選択${selection.size}`:''}`;
  // 診断HUD: FPS / フレーム時間 / 音声レイテンシ
  perfFrames++; const nowMs=performance.now();
  if(nowMs-perfLast>500){
    const fps=perfFrames/((nowMs-perfLast)/1000);
    const ft=1000/Math.max(fps,1);
    const lat=((actx.outputLatency||actx.baseLatency||0)*1000);
    const inf=renderer.info.render;
    const gpuShort=/SwiftShader/i.test(gpuName)?'⚠SwiftShader(CPU描画!)':gpuName.replace(/^ANGLE \(([^,]+),\s*([^,)]+).*/,'$2').slice(0,28);
    { const si=document.getElementById('songInfo');
      applyInfoChain();                                          // 書き出しと同じ最終値（infoBase+INFOノード合成=infoJson）を表示に使う
      const ij=infoJson||infoBase||{};
      const nm=ij._songName||'', ar=ij._songAuthorName||'';
      updateCoverThumb();
      const covOn=extraNodes.some(x=>x.kind==='cover'
        &&graphEdges.some(e2=>e2.sig==='cover'&&e2.fromId===x.id&&e2.toId==='out'));
      if(nm||ar||covOn){
        si.style.display='flex';
        const stl=document.getElementById('siTitle'), sar=document.getElementById('siArtist');
        stl.textContent=nm; stl.style.display=nm?'':'none';
        sar.textContent=ar; sar.style.display=ar?'':'none';
      } else si.style.display='none'; }
    { const okA=sigConnected('audio')&&audioBuf;                      // OUTPUTへ配線済みの曲だけ数える
      const eff=okA?Math.max(0,songDur-getSongOff()):0;
      updateDiffLabel(); }
    document.getElementById('perf').style.display='none';
    // 自動解像度スケーリング: 重ければ下げ、余裕があれば戻す（30fps死守）
    // 注: タブ非表示中はRAFが間引かれ偽の低fpsになるため自動降格しない（ft>250msはスロットリングとみなす）
    if(ft>30&&ft<250&&!document.hidden&&dprScale>0.5){ dprScale=Math.max(0.5,dprScale-0.25); applyDpr(); resize(); }
    else if(ft<11&&dprScale<1){ dprScale=Math.min(1,dprScale+0.25); applyDpr(); resize(); }
    perfFrames=0; perfLast=nowMs; }
  _lastHeadBeat=curV;   // 再生ヘッド拍を保持＝配置色ボックスのブースト判定に使う（ヘルバ様指定 2026-07-14）
  if(lightMode&&!chromaMode){ const _sw=document.getElementById('lcChromaSw');   // 配置位置がブースト中なら箱もブースト色へ自動追従（変化時のみDOM更新）
    if(_sw){ const _hx=currentLightPlaceHex(); if(_sw._bHx!==_hx){ _sw._bHx=_hx; _sw.innerHTML=chromaSwSvg(_hx); } } }
  controls.update(); clampCamera(); renderer.render(scene,camera); requestAnimationFrame(tick);   // 毎フレーム可動範囲へクランプ（どの操作経路でも確実）
}

// ---- ファイルメニュー ----
let _idbP=null;
function idbDB(){ if(_idbP) return _idbP;
  _idbP=new Promise(res=>{ const r=indexedDB.open('nodemapper',1);
    r.onupgradeneeded=()=>r.result.createObjectStore('kv');
    r.onsuccess=()=>res(r.result); r.onerror=()=>res(null); });
  return _idbP; }
async function idbGet(k){ const db=await idbDB(); if(!db) return null;
  return new Promise(res=>{ const t=db.transaction('kv').objectStore('kv').get(k);
    t.onsuccess=()=>res(t.result); t.onerror=()=>res(null); }); }
async function idbSet(k,v){ const db=await idbDB(); if(!db) return;
  return new Promise(res=>{ const t=db.transaction('kv','readwrite').objectStore('kv').put(v,k);
    t.onsuccess=()=>res(); t.onerror=()=>res(); }); }
async function idbDel(k){ const db=await idbDB(); if(!db) return;
  return new Promise(res=>{ const t=db.transaction('kv','readwrite').objectStore('kv')['delete'](k);
    t.onsuccess=()=>res(); t.onerror=()=>res(); }); }
// FileSystemHandleを直接IndexedDBへ保存する実装(recents/songHandles/libDirs)はWebView2埋め込み環境で
// 構造化クローン処理がネイティブクラッシュを起こす(保存直後にアプリ全体が落ちる不具合の原因)。
// 通常のChrome/Edgeでは問題ないが、この配布形態では機能を無効化する。過去のクラッシュ以前に
// 書き込まれてしまった残留データも起動時に一度だけ消しておく。
for(const k2 of ['recents','lastSongHandle','songHandles','libDirs']) idbDel(k2).catch(()=>{});
async function newProject(){
  closeFileMenu();
  if(!defaultFresh()&&!confirm(t('cf.newProject','現在の編集内容を破棄して、新規プロジェクトを作りますか？'))) return;
  resetAllState();   // 前ファイルの残留を全消し（フラット/_flatDirty/クリップ/ロック等）
  projFileHandle=null;
  files={}; handles={}; dirHandle=null;
  infoGraph=defaultInfoGraph(); layoutInfoNodes(); applyInfoGraph();
  diffV3=true;
  infoBase=null; infoJson=null;
  if(playing) pause();
  audioBuf=null; ovWave=null; songDur=0; BPM=120; cur=0; offset=0; prevPlayBeat=-1;
  specMag=null; specSrcCanvas=null; specForBuf=null; tempoParts=[];
  document.getElementById('diff').innerHTML=''; lineSrc.clear();   // 難易度リストを初期化
  newDefaultGraph();
  initScratchDiff();   // 標準5難易度で再スタート（プルダウンは常時表示）
  rebuild();
  showOk('新規プロジェクトを作成しました');
}
async function saveProjectCopy(){
  closeFileMenu();
  if(!sections.length){ showErr('保存対象がありません'); return; }
  await refreshCoverB64();   // カバー画像をbase64化してから同梱
  const text=buildProjectText();
  let fh;
  try{ fh=await showSaveFilePicker({suggestedName:'project_copy.nlmf',
    types:[{description:'Non-Linear Mapperプロジェクト',accept:{'application/octet-stream':['.nlmf']}}]}); }
  catch(e){ return; }
  try{ const w=await fh.createWritable(); await w.write(text); await w.close();
    showOk(tf('msg.copySaved','コピーを保存: {name}',{name:fh.name}));
  }catch(err){ showErr(tf('msg.saveFail','保存失敗: {err}',{err})); }
}
function closeFileMenu(){ document.getElementById('mFileMenu').style.display='none'; }
document.getElementById('mFileBtn').onclick=()=>{
  const m=document.getElementById('mFileMenu');
  m.style.display=m.style.display==='block'?'none':'block';
};
document.getElementById('mFileMenu').addEventListener('click',async e=>{
  const act=e.target.closest('button')?.dataset.act; if(!act) return;
  if(act==='new') newProject();
  else if(act==='open'){ closeFileMenu(); openProjectFile(); }
  else if(act==='save'){ closeFileMenu(); saveProject(false); }
  else if(act==='saveas'){ closeFileMenu(); saveProject(true); }
  else if(act==='savecopy') saveProjectCopy();
  else if(act==='loadsong'){ closeFileMenu(); openSongFile(); }   // Musicレーンの「音楽ファイルを読み込む」と同じ
  else if(act==='addfolder'){ closeFileMenu(); document.getElementById('libAddBtn').click(); }   // MEDIAの「フォルダを追加」と同じ（showDirectoryPicker→scanLibrary）
});

// ---- フローティングツールバー ----
const TB_ICONS={};
// 切る向き: 時計回り + ドット（d値, アイコン名, langキー, 既定ラベル）
const DIR_LIST=[   // 順: ↓↙←↖↑↗→↘[・]（ヘルバ様指定・ROTと一致）
  [1,'cut_down','dir.bottom','Bottom'],[6,'cut_downleft','dir.bottomleft','Bottom Left'],
  [2,'cut_left','dir.left','Left'],[4,'cut_upleft','dir.topleft','Top Left'],
  [0,'cut_up','dir.top','Top'],[5,'cut_upright','dir.topright','Top Right'],
  [3,'cut_right','dir.right','Right'],[7,'cut_downright','dir.bottomright','Bottom Right'],
  [8,'cut_any','dir.dot','Dot'],
];
const DIR_ICON_NAME={0:'cut_up',5:'cut_upright',3:'cut_right',7:'cut_downright',1:'cut_down',6:'cut_downleft',2:'cut_left',4:'cut_upleft',8:'cut_any'};
async function buildDirPanel(){
  // 方向プルダウン（アイコン+名前、選択中ハイライト）。言語切替時にも再構築される
  const dp=document.getElementById('tbDirPanel'); dp.innerHTML='';
  for(const [d,icon,k,def] of DIR_LIST){
    const row=document.createElement('div'); row.className='dirRow'; row.dataset.d=d;
    row.innerHTML=(await tbIcon(icon))+`<span>${t(k,def)}</span>`;
    row.onclick=()=>{ brush.d=d; refreshPal(); if(placeMode) refreshGhost();
      updateDirBtn(); togglePanel('tbModeNote','tbDirPanel'); stat(tf('msg.brushDir','ブラシ向き: {dir}',{dir:DIRICON[d]})); };
    dp.appendChild(row);
  }
  updateDirBtn();
}
function updateDirBtn(){ const nb=document.getElementById('tbModeNote');   // ノーツボタン自体を現在の切る向きアイコンへ更新（旧tbDirBtnは廃止＝メイン表示が向きに追従・ヘルバ様指摘）
  if(nb&&TB_ICONS[DIR_ICON_NAME[brush.d]]){
    let ic=TB_ICONS[DIR_ICON_NAME[brush.d]];
    // アイコンの紫はinline styleで入っており .modeon の属性セレクタでは白くならないため、配置ノーツ中はJSで白へ（紫背景で潰れる・ヘルバ様指定）
    if(placeMode&&brush.type==='note') ic=ic.replaceAll('#8160e3','#ffffff');
    nb.innerHTML=ic+'<span class="tbdrop">▾</span>'; }
  const dp=document.getElementById('tbDirPanel');
  if(dp) [...dp.children].forEach(r=>r.classList.toggle('on',+r.dataset.d===brush.d)); }
function updateColorBtn(){   // 1個のスウォッチ＝現在の配置色(赤/青)を表示・クリックでカラーパレット（ヘルバ様指定 2026-07-14）
  const sw=document.getElementById('tbColSw');
  if(sw) sw.innerHTML=chromaSwSvg(brush.c===0?cRED:cBLUE); }
// 配置モードボタンのアクティブ表示（現在のモード=紫点灯＝.modeon）。.on はtogglePanelが一括解除するため別クラス
function updateModeButtons(){
  const cur=placeMode?brush.type:null;
  for(const [id,val] of [['tbModeNote','note'],['tbModeBomb','bomb'],['tbModeWall','wall']]){
    const b=document.getElementById(id); if(b) b.classList.toggle('modeon',val===cur);
  }
  updateDirBtn();   // ノーツボタンの矢印色（アクティブ=白/非アクティブ=紫）をモード切替に追従
}
const ICON_V='3';   // アイコンを更新したらここを上げる（ブラウザキャッシュ対策）
async function tbIcon(name){ if(TB_ICONS[name]) return TB_ICONS[name];
  try{ const txt=await (await fetch('icons/'+name+'.svg?v='+ICON_V)).text();
    TB_ICONS[name]=txt.replace('style="color:#c5c5c5"',''); }
  catch(e){ TB_ICONS[name]='?'; }
  return TB_ICONS[name]; }
['select','note','bomb','wall','light_on','light_boost'].forEach(n=>tbIcon(n));   // W長押し配置パイ＋カラーピッカーのアイコンを先読み（tbIcon/ICON_V定義後＝TDZ回避・パイ/パネルは同期でTB_ICONSから即引く）
function jumpMarker(dir){   // 矢印方向の一番近いマーカーへ（マーカーが無ければ従来どおりボックス先頭へ）
  const beats=markers.length?markers.map(m=>m.beat):[...sections].map(x=>x.beat||0);
  if(!beats.length) return; if(playing) pause();
  beats.sort((a,b)=>a-b);
  let tgt=null;
  if(dir<0){ for(const b of beats){ if(b<cur-1e-3) tgt=b; } if(tgt===null) tgt=0; }
  else { tgt=beats.find(b=>b>cur+1e-3); if(tgt===undefined) return; }
  seekEase(tgt); }
async function buildToolbar(){
  const tr=document.getElementById('tbTransport');
  const defs=[
    ['tp_start','tb.start','スタートに戻る（Ctrl+←）',()=>{ seekEase(0); }],
    ['tp_prevkey','tb.prevkey','前のマーカーへ（Ctrl+[）',()=>jumpMarker(-1)],
    ['tp_play','tb.play','再生 / 一時停止（Space）',()=>{ playing?pause():play(); }],
    ['tp_nextkey','tb.nextkey','次のマーカーへ（Ctrl+]）',()=>jumpMarker(1)],
    ['tp_end','tb.end','曲末へ（Ctrl+→）',()=>{ const tgt=timelineEndBeat(); if(tgt>0) seekEase(tgt); }],
  ];
  for(const [icon,k,tip,fn] of defs){
    const b=document.createElement('button'); b.className='tbi'; b.id='tbi_'+icon;
    b.dataset.i18nT=k; b.title=t(k,tip); b.innerHTML=await tbIcon(icon); b.onclick=fn;
    tr.appendChild(b);
  }
  document.getElementById('tbSnapIcon').innerHTML=await tbIcon('snap');
  await buildDirPanel();
  // ライト動作ボタンのアイコン（ON/OFFプルダウン0/1＋FFTボタン2/3/4。横並びツールバー化）
  const behavIcons={0:'light_off',1:'light_on',2:'light_flash',3:'light_fade',4:'light_transition'};
  for(const ch of document.querySelectorAll('.lbBehavItem')){
    const b=+ch.dataset.b, ico=ch.querySelector('.lbIco');
    if(ico) ico.innerHTML=await tbIcon(behavIcons[b]);   // ラベルspan(data-i18n)は触らず＝loadLangがアイコンを消さない
  }
  setLightBehav(lightBrush.behav);   // アイコン付与後に現在behavの点灯＋ON/OFFボタンを同期
  try{ applyModeVis(); }catch(_){}   // 起動時のモード別表示＋BOOSTレーン表示を、保存済みchromaMode（既定ON=隠す）へ合わせる
  document.getElementById('tbArcBtn').innerHTML=await tbIcon('arc');
  document.getElementById('tbChainBtn').innerHTML=await tbIcon('chain');
  document.getElementById('tbArcBtn').onclick=()=>createArc();
  document.getElementById('tbChainBtn').onclick=()=>createChain();
  // 配置モードボタン（セレクト/ノーツ/ボム/壁）＝W長押しパイと同じ切替
  for(const [id,name,val] of [['tbModeBomb','bomb','bomb'],['tbModeWall','wall','wall']]){
    const b=document.getElementById(id); if(b){ b.innerHTML=await tbIcon(name); b.onclick=()=>commitPlaceModePie(val); }
  }
  // ノーツは「アイコン＋▾」の一体型プルダウン: クリックでノーツモード＋切る向きプルダウンを開く（ヘルバ様指定）
  { const nb=document.getElementById('tbModeNote');
    if(nb){ nb.innerHTML=(await tbIcon('note'))+'<span class="tbdrop">▾</span>';
      nb.onclick=()=>{ commitPlaceModePie('note'); togglePanel('tbModeNote','tbDirPanel'); }; } }
  updateDirBtn(); updateColorBtn(); updateModeButtons(); updateModeIndicator();
  try{ setCamMode('place'); }catch(_){}   // 起動時は配置モードから始める（ヘルバ様指定）
  document.getElementById('pvVisNotes').innerHTML=await tbIcon('note');
  document.getElementById('pvVisLights').innerHTML=await tbIcon('light_on');
  document.getElementById('pvVisStruct').innerHTML=await tbIcon('struct');
  document.getElementById('pvVisAmbient').innerHTML=await tbIcon('ambient');
  document.getElementById('pvVisNotes').onclick=()=>setPvShowNotes(!pvShowNotes);
  document.getElementById('pvVisLights').onclick=()=>setPvShowLights(!pvShowLights);
  document.getElementById('pvVisStruct').onclick=()=>setPvShowStruct(!pvShowStruct);
  document.getElementById('pvVisAmbient').onclick=()=>setPvShowAmbient(!pvShowAmbient);
  pvFinderVis();
  setPv4Mode(true);   // pv4固定（ARC/pv4切替ボタンは廃止・ARC先読みも停止）
  // 事前ロード（再生中の差し替え用）
  await tbIcon('tp_pause');
}
let _lastPlaying=null;
function syncPlayIcons(){
  const b=document.getElementById('tbi_tp_play');
  if(!b||!TB_ICONS.tp_pause) return;
  b.innerHTML=playing?TB_ICONS.tp_pause:TB_ICONS.tp_play;
}
function togglePanel(btnId,panelId){
  const pnl=document.getElementById(panelId), show=pnl.style.display!=='block';
  document.querySelectorAll('.tbpanel').forEach(x=>x.style.display='none');
  document.querySelectorAll('#maintb .tbi.on').forEach(x=>x.classList.remove('on'));
  if(show){ pnl.style.display='block'; document.getElementById(btnId).classList.add('on'); }
}
document.getElementById('tbSnapBtn').onclick=()=>togglePanel('tbSnapBtn','tbSnapPanel');
// ---- 難易度バー（プルダウン廃止→5ボタン均等・ON=難易度色。選択中クリック=転送/受信/削除メニュー。ヘルバ様設計2026-07-05） ----
let _dfMenuFor=null;   // 直前にメニューを開いた難易度（トグル閉じ判定）
function diffColOf(dn){ return {Easy:'#3ddc84',Normal:'#3092ff',Hard:'#ffd23d',Expert:'#ff9d3d',ExpertPlus:'#ff3b52'}[dn]||'#8a8a8a'; }   // 関数宣言=巻き上げ（起動時のinitScratchDiff→renderDiffBarがこの定義より先に走るため。constはTDZでモジュール評価ごと死ぬ）
function dispDiff(n){ return n==='ExpertPlus'?'Expert+':n; }
function diffOptOf(name){ const sel=document.getElementById('diff');
  return [...sel.options].find(o=>o.textContent===name||o.value.toLowerCase().startsWith(name.toLowerCase()+'standard'))||null; }
function diffIsCurrent(name){ const o=diffOptOf(name); return !!o&&o.value===document.getElementById('diff').value; }
function diffCountsOf(name){
  if(diffIsCurrent(name)) return {n:notes.length,l:lightEvents.length};
  const o=diffOptOf(name); if(!o) return {n:0,l:0};
  const st=projDiffs[o.value.toLowerCase()];
  return st?{n:(st.notes||[]).length,l:(st.lightEvents||[]).length}:{n:0,l:0};
}
function renderDiffBar(){
  const bar=document.getElementById('diffBar'); if(!bar) return;
  try{ syncSetQuick(); }catch(_e){}   // トップバー左（環境＋ノーツ色）は曲/難易度の有無に関わらず同期（早期returnより前）
  const sel=document.getElementById('diff');
  if(!sel.options.length){ bar.style.display='none'; return; }
  bar.style.display='flex';
  if(!bar.childElementCount){
    OUT_DIFFS.forEach((dn,i)=>{ const seg=document.createElement('div'); seg.className='dfSeg'; seg.dataset.dn=dn;
      seg.innerHTML=`<span class="dfName">${dn==='ExpertPlus'?'EXPERT+':dn.toUpperCase()}</span><span class="dfArr">▼</span>`;
      seg.addEventListener('click',()=>{ if(!diffOptOf(dn)) return;
        if(diffIsCurrent(dn)){
          if(_dfMenuFor===dn&&performance.now()-_menuHidAt<400){ _dfMenuFor=null; return; }   // 開いた状態で再度押した=閉じるだけ（トグル）
          openDiffMenu(dn,i,seg); _dfMenuFor=dn; }      // 選択中のボタン=プルダウン
        else switchDiffByIndex(i); });                  // 未選択のボタン=1回目のクリックで選択（切替）
      bar.appendChild(seg); });
  }
  const cur=sel.selectedOptions[0]&&sel.selectedOptions[0].textContent;
  for(const seg of bar.children){ const dn=seg.dataset.dn;
    seg.classList.toggle('on',dn===cur);
    seg.classList.toggle('dis',!diffOptOf(dn));
    seg.style.setProperty('--dfc',diffColOf(dn)); }
}
function openDiffMenu(dn,idx,seg){
  const sr=seg.getBoundingClientRect(), x=sr.left, y=sr.bottom+3;   // ボタンの左端に揃えて直下に開く（ファイルメニュー/スナップと同じ流儀）
  const others=OUT_DIFFS.filter(n2=>n2!==dn&&diffOptOf(n2));
  const again=items=>setTimeout(()=>showMenu(x,y,items),0);   // 上書き確認だけは実行直前に差し替え表示
  const guarded=(dst,payload,fn)=>{   // 上書きになる場合は注意喚起を挟む
    const c=diffCountsOf(dst), hit=payload==='lights'?c.l:(payload==='notes'?c.n:c.n+c.l);
    if(hit>0) again([[tf('ctx.overwrite','⚠ {diff}の既存の{kind}を置き換え — 実行する',{diff:dispDiff(dst),kind:payload==='lights'?t('word.lighting','ライティング'):payload==='notes'?t('word.notes','ノーツ'):t('word.content','内容')}),fn],[t('ctx.cancel','キャンセル'),()=>{}]]);
    else fn(); };
  const run=(s2,d2,payload)=>{ if(payload==='all'){ diffCopy(s2,d2,'notes'); diffCopy(s2,d2,'lights'); } else diffCopy(s2,d2,payload); };
  const sendSub=payload=>others.map(n2=>['→ '+dispDiff(n2),()=>guarded(n2,payload,()=>run(dn,n2,payload))]);   // 転送=→
  const recvSub=payload=>others.map(n2=>['← '+dispDiff(n2),()=>guarded(dn,payload,()=>run(n2,dn,payload))]);   // 受信=←
  showMenu(x,y,[
    [t('ctx.sendNotes','ノーツを転送'),sendSub('notes')],
    [t('ctx.recvNotes','ノーツを受信'),recvSub('notes')],
    ['---'],
    [t('ctx.sendLights','ライティングを転送'),sendSub('lights')],
    [t('ctx.recvLights','ライティングを受信'),recvSub('lights')],
    ['---'],
    [t('ctx.sendAll','丸ごと転送（ノーツ＋ライト）'),sendSub('all')],
    ['---'],
    [t('ctx.delAllNotes','全ノーツを削除'),[[tf('ctx.delAllNotesGo','⚠ {diff}の全ノーツを削除 — 実行する',{diff:dispDiff(dn)}),()=>diffClear(dn,'notes')],[t('ctx.cancel','キャンセル'),()=>{}]]],
    [t('ctx.delAllLights','全ライティングを削除'),[[tf('ctx.delAllLightsGo','⚠ {diff}の全ライティングを削除 — 実行する',{diff:dispDiff(dn)}),()=>diffClear(dn,'lights')],[t('ctx.cancel','キャンセル'),()=>{}]]],
    [t('ctx.delAll','含まれる内容を全て削除'),[[tf('ctx.delAllGo','⚠ {diff}のノーツとライティングを全て削除 — 実行する',{diff:dispDiff(dn)}),()=>{ diffClear(dn,'notes'); diffClear(dn,'lights'); }],[t('ctx.cancel','キャンセル'),()=>{}]]],
  ]);
}
// ---- BPMフィールド（難易度バーの右・Blender式: ホバーで‹›・中央クリック=その場入力。Musicレーン左溝から移設） ----
// BPM/プレビュー秒の配線は wireStepper で共通化（下部・langSel近く）
// ---- 設定クイック（難易度バー左: 環境＋ノーツ色）。設定ノードの env/red/blue を直接編集し applyInfoGraph で全体反映 ----
function quickSetNode(){   // アクティブ書き出しに接続中の設定ノード（無ければ最初の設定ノード）
  let id=connectedNodeId('set');
  if(!id){ for(const k in infoGraph.nodes){ if(infoGraph.nodes[k].t==='set'){ id=k; break; } } }
  return id?infoGraph.nodes[id]:null;
}
{ const sqEnvBtn=document.getElementById('sqEnvBtn'), sqEnvPanel=document.getElementById('sqEnvPanel');
  if(sqEnvBtn&&sqEnvPanel){ const short=n=>n.replace(/Environment$/,'');
    for(const n of PV_ENVS){ const row=document.createElement('div'); row.className='dirRow'; row.dataset.env=n;   // 既存の統一ドロップダウン(.tbpanel/.dirRow/togglePanel)を流用
      row.innerHTML=`<span>${short(n)}</span>`;
      row.onclick=()=>{ const nd=quickSetNode();
        if(nd){ infoSnapshot(); nd.data.env=(n==='DefaultEnvironment'?'':n); metaDirty=true; applyInfoGraph(); }
        togglePanel('sqEnvBtn','sqEnvPanel'); };
      sqEnvPanel.appendChild(row); }
    sqEnvBtn.onclick=()=>togglePanel('sqEnvBtn','sqEnvPanel'); }
  const sqPick=(ck,btn)=>{ if(!btn) return; btn.addEventListener('click',()=>{ const nd=quickSetNode(); if(!nd) return;
    const sr=btn.getBoundingClientRect(), nr=ndcv.getBoundingClientRect();
    ndColorEdit(hexOf(nd.data[ck]>>>0),hex=>{ infoSnapshot(); nd.data[ck]=parseInt(hex.slice(1,7),16)>>>0;
      metaDirty=true; applyInfoGraph(); syncSetQuick(); },{x:sr.left-nr.left,y:sr.bottom-nr.top,h:0},btn); }); };   // btn=trigger（再クリックでトグル閉じ）
  sqPick('red',document.getElementById('sqRed')); sqPick('blue',document.getElementById('sqBlue'));
  sqPick('lred',document.getElementById('lpLRed')); sqPick('lblue',document.getElementById('lpLBlue'));   // レーザー色をライト編集パネルへ移設（設定ノードのlred/lblueを直接編集＝INFOと同一データ）
}
function syncSetQuick(){   // トップバーの表示を「実効値」へ同期（renderDiffBar=RAFから毎フレーム。差分でのみ再描画）
  const btn=document.getElementById('sqEnvBtn'); if(!btn) return;
  let v=(infoBase&&infoBase._environmentName)||'';   // 確定情報（接続中の設定ノード由来＝applyInfoGraphが設定）
  if(!v){ const nd=quickSetNode(); if(nd) v=nd.data.env||''; }   // 未接続なら設定ノードの値
  if(!v) v='DefaultEnvironment';   // 実効環境名（正規化）
  const short=n=>n.replace(/Environment$/,'');
  const nm=document.getElementById('sqEnvName'); if(nm&&nm.textContent!==short(v)) nm.textContent=short(v);
  const panel=document.getElementById('sqEnvPanel');
  if(panel){ [...panel.children].forEach(r=>r.classList.toggle('on',r.dataset.env===v));
    btn.classList.toggle('on',panel.style.display==='block'); }   // ボタンのハイライト=パネル開閉に同期
  for(const [id,g] of [['sqRed',RED],['sqBlue',BLUE]]){ const b=document.getElementById(id); if(!b) continue;   // ライブのノーツ色（RED/BLUE=全体の真実）を表示
    const col=hexOf(g>>>0);
    if(b.dataset.col!==col){ b.dataset.col=col; b.style.background=col; } }   /* Edit(.colbtns)様式＝無地の色矩形（背景色を直接塗る） */
  for(const [id,g] of [['lpLRed',LRED],['lpLBlue',LBLUE]]){ const b=document.getElementById(id); if(!b) continue;   // ライト編集パネルのレーザー色スウォッチ（ライブLRED/LBLUE）
    const col=hexOf(g>>>0);
    if(b.dataset.col!==col){ b.dataset.col=col; b.innerHTML=laserSwSvg(col); } }
}
function diffStoreOf(name,create){   // 難易度の退避データ（現在の難易度も退避してから返す=常に最新）
  const o=diffOptOf(name); if(!o) return null;
  stashCurrentDiff();
  const key=o.value.toLowerCase();
  let st=projDiffs[key];
  if(!st&&create){
    const secs=structuredClone(sections);   // ボックス構造=全難易度一体（中身は空で複製）
    for(const s2 of secs) if(s2.content) for(const k of ['notes','bombs','walls','arcs','chains','lights']) s2.content[k]=[];
    st=projDiffs[key]={name:o.value,v3:true,base:EMPTY_V3(),notes:[],bombs:[],walls:[],arcs:[],chains:[],lightEvents:[],sections:secs};
  }
  return st;
}
function _diffApplyLive(D,payload){   // 対象が現在表示中の難易度ならライブ状態へ反映
  if(payload==='lights'){ lightEvents=D.lightEvents; lightSelection.clear(); }
  else { notes=D.notes; bombs=D.bombs; walls=D.walls; arcs=D.arcs; chains=D.chains; selection.clear(); }
  sections=structuredClone(D.sections||[]); relinkDiffEdges(); gizmoMode=null; rebuild();
}
function diffCopy(srcName,dstName,payload){   // payload: 'notes'（ボム/壁/アーク/チェーン込み）| 'lights'
  const S=diffStoreOf(srcName,true), D=diffStoreOf(dstName,true);
  if(!S||!D){ showErr('対象の難易度がありません'); return; }
  const dstCur=diffIsCurrent(dstName);
  if(dstCur) snapshot(payload==='lights'?'light':'note');   // 現在の難易度への受信はUndo可
  const flatK=payload==='lights'?['lightEvents']:['notes','bombs','walls','arcs','chains'];
  const kind=payload==='lights'?'l':'n';
  for(const k of flatK) D[k]=structuredClone(S[k]||[]);
  // 箱は難易度ごとに独立: 対象種（ノーツ/ライト）のクリップを、送り元のクリップ群で丸ごと差し替える
  D.sections=(D.sections||[]).filter(x2=>secLk(x2)!==kind);
  for(const ss of (S.sections||[])){ if(ss.kind==='null'||secLk(ss)!==kind) continue;
    const ds=structuredClone(ss); ds.id='n'+(++_nid)+Math.random().toString(36).slice(2,6);
    D.sections.push(ds); }
  if(dstCur) _diffApplyLive(D,payload);
  metaDirty=true; renderDiffBar();
  showOk(tf('msg.diffCopied','{src} の{kind}を {dst} へコピーしました{warn}',{src:dispDiff(srcName),kind:payload==='lights'?t('word.lighting','ライティング'):t('word.notes','ノーツ'),dst:dispDiff(dstName),warn:dstCur?'':t('word.offscreenNoUndo','　※画面外の難易度への操作はUndoできません')}));
}
function diffClear(dnName,payload){
  const D=diffStoreOf(dnName,true); if(!D){ showErr('対象の難易度がありません'); return; }
  const cur=diffIsCurrent(dnName);
  if(cur) snapshot(payload==='lights'?'light':'note');
  const flatK=payload==='lights'?['lightEvents']:['notes','bombs','walls','arcs','chains'];
  const contK=payload==='lights'?['lights']:['notes','bombs','walls','arcs','chains'];
  for(const k of flatK) D[k]=[];
  for(const ds of (D.sections||[])) if(ds.content) for(const k of contK) ds.content[k]=[];
  if(cur) _diffApplyLive(D,payload);
  metaDirty=true; renderDiffBar();
  showOk(tf('msg.diffCleared','{diff} の{kind}を全て削除しました{warn}',{diff:dispDiff(dnName),kind:payload==='lights'?t('word.lighting','ライティング'):t('word.notes','ノーツ'),warn:cur?'':t('word.offscreenNoUndo','　※画面外の難易度への操作はUndoできません')}));
}
function switchDiffByIndex(i){   // 1〜5キー: Easy〜Expert+（プルダウンの行クリックと同じ経路）
  const sel=document.getElementById('diff'); if(!sel||!sel.options.length) return;
  const name=OUT_DIFFS[i];
  const o=[...sel.options].find(o2=>o2.textContent===name||o2.value.toLowerCase().startsWith(name.toLowerCase()+'standard'));
  if(!o){ stat(tf('msg.diffNotInProject','難易度 {diff} はこのプロジェクトにありません',{diff:name==='ExpertPlus'?'Expert+':name})); return; }
  if(sel.value===o.value) return;
  sel.value=o.value; if(sel.onchange) sel.onchange(); updateDiffLabel();
}
function updateDiffLabel(){ renderDiffBar(); }   // 表示は状態駆動（RAFループからも呼ばれ、常に#diffBarへ同期）
// 切る向きプルダウンはノーツボタン直後のキャレット(tbDirCaret)で開く（旧tbDirBtnは廃止・buildToolbarで配線）
{ const sw=document.getElementById('tbColSw');   // 1個のスウォッチ＝クリックでカラーパレット（配置色の切替はパレット内 or F・ヘルバ様指定 2026-07-14）
  if(sw) sw.addEventListener('click',e=>{ pickHexAt(e.currentTarget, brush.c===0?cRED:cBLUE, hex=>setNoteColorHex(brush.c,hex)); }); }
// ライトブラシは横並びツールバー化（旧tbLightBtnの単一ドロップダウンは廃止・ヘルバ様指定）
addEventListener('pointerdown', e=>{                       // ツールバー外クリックでパネルを閉じる
  if(!e.target.closest||(!e.target.closest('#maintb')&&!e.target.closest('#setQuick'))){
    document.querySelectorAll('.tbpanel').forEach(x=>x.style.display='none');
    document.querySelectorAll('#maintb .tbi.on').forEach(x=>x.classList.remove('on')); }
  if(!e.target.closest||!e.target.closest('#mFileWrap')) closeFileMenu();
}, true);
// ---- ペインホバー追跡（Tabの対象） ----
// enterだけだと起動処理中（three.js初期化等）にイベントを取りこぼし、初回TabがNOTES/LIGHTに化ける
// → pointermoveでも常時更新して自己修復（どのタイミングでマウスが入っていても正しいペインを指す）
function paneOf(t){ if(!t||!t.closest) return null;
  return t.closest('#nodecol')?'node':t.closest('#pvpane')?'pv':t.closest('#main')?'main':null; }
addEventListener('pointermove',e=>{ const m=paneOf(e.target); if(m) hoverPane=m; },{passive:true});
[['pvpane','pv'],['nodecol','node'],['main','main']].forEach(([id,m])=>{
  const el=document.getElementById(id); if(el) el.addEventListener('pointerenter',()=>hoverPane=m); });
// ---- 設定モーダル ----
document.getElementById('mbSettings').onclick=()=>{
  { const el=document.getElementById('laneRatio'), lv=document.getElementById('laneRatioVal');   // 開くたび現在のレーン数へ同期
    if(el){ el.value=notesLanes; if(lv) lv.textContent=notesLanes+' : '+lightLanes; } }
  document.getElementById('settingsBg').style.display='flex'; };
document.getElementById('settingsClose').onclick=()=>{ document.getElementById('settingsBg').style.display='none'; };
document.querySelectorAll('#settingsBox .setTab').forEach(btn=>btn.addEventListener('click',()=>{   // タブで項目画面を切替（アプリ/音量/Preview/カメラ）
  const tab=btn.dataset.tab;
  document.querySelectorAll('#settingsBox .setTab').forEach(b=>b.classList.toggle('on',b===btn));
  document.querySelectorAll('#settingsBox .setPanel').forEach(p=>p.classList.toggle('on',p.dataset.panel===tab));
  if(tab==='keys'){ try{ renderKeyEditor(); }catch(_){} }   // ショートカット編集タブ＝表示時に描画
}));
// ---- ショートカット編集タブ（Phase1: 表示・取込・保存。実ハンドラへの反映=Phase2で置換） ----
let _keyCapture=null;   // {id} 取込中のアクション
function _kfConflict(id,b){   // 重複警告: 同カテゴリ or 共通との衝突のみ（別ペイン同士は許容）
  const a=ACT_BY_ID[id]; if(!a) return null;
  for(const o of ACTIONS){ if(o.id===id) continue;
    if(o.cat!==a.cat && o.cat!=='common' && a.cat!=='common') continue;
    if(sameBind(effBind(o.id),b)) return o.id; }
  return null;
}
function renderKeyEditor(){
  const host=document.getElementById('keyEditBody'); if(!host) return;
  host.innerHTML='';
  for(const [cat,catLabel] of ACT_CATS){
    const acts=ACTIONS.filter(a=>a.cat===cat); if(!acts.length) continue;
    const h=document.createElement('div'); h.textContent=catLabel;
    h.style.cssText='color:#8a8a92;font-weight:700;margin:18px 0 7px;font-size:11px;letter-spacing:.1em;text-transform:uppercase'; host.appendChild(h);
    for(const a of acts){
      const b=effBind(a.id), overridden=!!_keymap[a.id], capturing=_keyCapture&&_keyCapture.id===a.id;
      const row=document.createElement('div'); row.style.cssText='display:flex;align-items:center;gap:8px;padding:6px 0;font-size:12.5px';
      const lbl=document.createElement('span'); lbl.textContent=a.label; lbl.style.cssText='flex:1;color:#cfd6de';
      const cur=document.createElement('kbd'); cur.textContent=capturing?'キーを押す…':comboStr(b);
      cur.style.cssText='min-width:96px;text-align:center;background:'+(capturing?'#8160e3':'#2d2d2d')+';border:1px solid '+(_kfConflict(a.id,b)?'#ff8a94':'#000')+';border-radius:5px;padding:2px 8px;color:#fff;font-weight:700';
      if(_kfConflict(a.id,b)) cur.title='「'+(ACT_BY_ID[_kfConflict(a.id,b)]||{}).label+'」と重複しています';
      const chg=document.createElement('button'); chg.textContent=capturing?'取消':'変更'; chg.style.cssText='padding:3px 10px;font-size:11px';
      chg.onclick=()=>{ _keyCapture=capturing?null:{id:a.id}; renderKeyEditor(); };
      row.append(lbl,cur,chg);
      if(overridden){ const rs=document.createElement('button'); rs.textContent='既定'; rs.title='既定に戻す'; rs.style.cssText='padding:3px 8px;font-size:11px';
        rs.onclick=()=>{ delete _keymap[a.id]; saveKeymap(); renderKeyEditor(); }; row.append(rs); }
      host.appendChild(row);
    }
  }
}
addEventListener('keydown',e=>{   // 取込中: 押されたキーを捕捉しアプリのショートカットには流さない（capture段階で先取り）
  if(!_keyCapture) return;
  if(['Control','Alt','Shift','Meta'].includes(e.key)) return;   // 修飾単独は確定待ち
  e.preventDefault(); e.stopPropagation();
  if(e.key!=='Escape'){
    const b=comboFromEvent(e), a=ACT_BY_ID[_keyCapture.id];
    if(a&&sameBind(b,a.def)) delete _keymap[a.id]; else if(a) _keymap[a.id]=b;   // 既定と同じなら上書き解除
    saveKeymap();
  }
  _keyCapture=null; renderKeyEditor();
}, true);
{ const rb=document.getElementById('keysResetAll'); if(rb) rb.onclick=()=>{ _keymap={}; saveKeymap(); renderKeyEditor(); }; }
document.getElementById('settingsReset').onclick=async()=>{   // 全ての環境設定(bsnm_*)を初回起動時=settings.default.json の状態へ戻す
  if(!confirm(t('cf.resetPrefs','画面比率・音量・カメラ速度・ショートカット表示など、全ての環境設定を初回起動時の状態に戻します。よろしいですか？'))) return;
  let defs={};
  try{ defs=await (await fetch('config/settings.default.json?v='+Date.now(),{cache:'no-store'})).json(); }catch(e){}
  try{ for(let i=localStorage.length-1;i>=0;i--){ const k=localStorage.key(i); if(k&&k.indexOf('bsnm_')===0) localStorage.removeItem(k); } }catch(e){}   // 既存の個人設定を全消去
  try{ for(const k in defs) if(k.indexOf('bsnm_')===0) localStorage.setItem(k,defs[k]); }catch(e){}   // デフォルト値を適用
  try{ await fetch('__settings/save',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({data:defs})}); }catch(e){}   // settings.json も即確定（reload前にデバウンス待ちしない）
  location.reload();
};
document.getElementById('settingsBg').addEventListener('pointerdown',e=>{ if(e.target.id==='settingsBg') e.target.style.display='none'; });
// 音量（マスター/ミュージック/ノーツ音。localStorage保存、右フェーダー=マスターと同期）
let volCfg={m:50,mu:50,n:50,mt:50};   // 初期値は全て50（ヘルバ様指定）
try{ Object.assign(volCfg,JSON.parse(localStorage.getItem('bsnm_vol')||'{}')); }catch(e){}
if(volCfg.mt==null) volCfg.mt=50;   // 旧保存データ（mt無し）でも既定値を補完
function applyVolumes(){
  masterGain.gain.value=(volCfg.m/100)**2;
  gain.gain.value=(volCfg.mu/100)**2*0.35;
  hitGain.gain.value=(volCfg.n/100)**2;
  metroGain.gain.value=(volCfg.mt/100)**2*1.2;   // 従来の既定0.6相当（60%^2*1.2≈0.43、100%で1.2）
  const f=document.getElementById('vol'); if(f) f.value=volCfg.m;
  const db=document.getElementById('vmDb');
  if(db) db.textContent=volCfg.m<=0?'-∞':(20*Math.log10(volCfg.m/100)).toFixed(1);
}
function wireVol(id,valId,key){
  const el=document.getElementById(id), lv=document.getElementById(valId);
  el.value=volCfg[key]; lv.textContent=el.value;
  el.addEventListener('input',()=>{ volCfg[key]=+el.value; lv.textContent=el.value;
    localStorage.setItem('bsnm_vol',JSON.stringify(volCfg)); });   // 保存のみ・再起動で反映（applyVolumesは起動時に実行）
}
wireVol('volM','volMVal','m'); wireVol('volMu','volMuVal','mu'); wireVol('volN','volNVal','n'); wireVol('volMt','volMtVal','mt');
applyVolumes();
// UI文字サイズ（80〜150%、localStorage保存。Canvas描画以外のUIに適用）
let uiScale=parseFloat(localStorage.getItem('bsnm_uiscale')||'1');
function applyUiScale(){
  ['#menubar','#maintb','.modeLabel','#modeKeys','#nodeKeys','#statChip','#infoPanel','#pvVis','#settingsBox','#tabFolder']
    .forEach(sel=>document.querySelectorAll(sel).forEach(el=>el.style.zoom=uiScale));   // #ctxmenu は除外（position:fixed＋zoomで右クリックメニューの位置がズレるため）
}
{ const el=document.getElementById('uiSpd'), lv=document.getElementById('uiVal');
  el.value=Math.round(uiScale*100); lv.textContent=el.value;
  el.addEventListener('input',()=>{ lv.textContent=el.value;
    localStorage.setItem('bsnm_uiscale',el.value/100); });   // 保存のみ・再起動で反映（ドラッグ中に実サイズを変えない）
  applyUiScale(); }
// カメラ速度（現行速度=100%基準、localStorage保存）
let camRotSpeed=1, camZoomSpeed=1, camPanSpeed=1;
try{ const cs=JSON.parse(localStorage.getItem('bsnm_camspd')||'{}');
  camRotSpeed=cs.rot??1; camZoomSpeed=cs.zoom??1; camPanSpeed=cs.pan??1; }catch(e){}
function saveCamSpd(){ localStorage.setItem('bsnm_camspd',JSON.stringify({rot:camRotSpeed,zoom:camZoomSpeed,pan:camPanSpeed})); }
function wireSpd(id,valId,key,initVal){
  const el=document.getElementById(id), lv=document.getElementById(valId);
  el.value=Math.round(initVal*100); lv.textContent=el.value;
  el.addEventListener('input',()=>{ lv.textContent=el.value;   // 保存のみ・実速度(camRotSpeed等)は変えない＝再起動で反映
    let cs={}; try{ cs=JSON.parse(localStorage.getItem('bsnm_camspd')||'{}'); }catch(e){}
    cs[key]=el.value/100; localStorage.setItem('bsnm_camspd',JSON.stringify(cs)); });
}
wireSpd('rotSpd','rotVal','rot',camRotSpeed);
wireSpd('zoomSpd','zoomVal','zoom',camZoomSpeed);
wireSpd('panSpd','panVal','pan',camPanSpeed);
// 3Dビューのホイール（タイムラインスクラブ）方向反転。感覚に個人差があるため環境設定でON/OFF（ヘルバ様指定 2026-09-21）
let invert3DScroll=(localStorage.getItem('bsnm_invert3dscroll')==='1');
{ const el=document.getElementById('invert3DScroll'); if(el){ el.checked=invert3DScroll;
  el.addEventListener('change',()=>{ invert3DScroll=el.checked; localStorage.setItem('bsnm_invert3dscroll',invert3DScroll?'1':'0'); }); } }
// preview設定（bloom/ambient等。bsnm_pv4に%で保存=100%が既定・pv4へはrawでpush。Previewを開くと反映）
let pvCfg={str:100,rad:100,thr:100,amb:100,ems:100,refl:100};
try{ Object.assign(pvCfg,JSON.parse(localStorage.getItem('bsnm_pv4')||'{}')); }catch(e){}
const PV_BASE={str:0.85,rad:1.0,thr:0.32,amb:1.0,ems:1.0,refl:1.0};   // 100%時の実値（preview-v4の既定と一致）
function applyPvSettings(){ if(!_PV4) return;   // pv4未ロード時はスキップ（起動時にactivateフックが再適用）
  _PV4.setBloomStrength&&_PV4.setBloomStrength(PV_BASE.str*pvCfg.str/100);
  _PV4.setBloomRadius&&_PV4.setBloomRadius(PV_BASE.rad*pvCfg.rad/100);
  _PV4.setBloomThreshold&&_PV4.setBloomThreshold(PV_BASE.thr*pvCfg.thr/100);
  _PV4.setAmbientLevel&&_PV4.setAmbientLevel(pvCfg.amb/100);
  _PV4.setEmissionScale&&_PV4.setEmissionScale(pvCfg.ems/100);
  _PV4.setReflStrength&&_PV4.setReflStrength(pvCfg.refl/100); }
function wirePv(id,key){ const el=document.getElementById(id), lv=document.getElementById(id+'Val'); if(!el) return;
  el.value=pvCfg[key]; if(lv) lv.textContent=el.value;
  el.addEventListener('input',()=>{ pvCfg[key]=+el.value; if(lv) lv.textContent=el.value;
    try{ localStorage.setItem('bsnm_pv4',JSON.stringify(pvCfg)); }catch(e){}
    applyPvSettings();   // 保存＋即時反映（applyPvSettingsは_PV4未ロード時に自前でskip＝起動フックで再適用）
  }); }
wirePv('pvBloomStr','str'); wirePv('pvBloomRad','rad'); wirePv('pvBloomThr','thr');
wirePv('pvAmb','amb'); wirePv('pvEms','ems'); wirePv('pvRefl','refl');
// 環境設定の全スライダー: 値(100%等)をダブルクリックで数値入力（範囲内にクランプ→既存handlerで適用）
document.querySelectorAll('#settingsBox .slRow').forEach(row=>{
  const range=row.querySelector('input[type=range]'), valSpan=row.querySelector('.t span[id]');
  if(!range||!valSpan) return;
  valSpan.style.cursor='text'; valSpan.title='ダブルクリックで数値入力';
  valSpan.addEventListener('dblclick',()=>{
    if(valSpan.querySelector('input')) return;
    const inp=document.createElement('input'); inp.type='text'; inp.value=range.value;
    inp.style.cssText='width:46px;background:#1f1f1f;border:1px solid #8160e3;border-radius:4px;color:#eee;font:inherit;text-align:right;outline:none;';
    valSpan.textContent=''; valSpan.appendChild(inp); inp.focus(); inp.select();
    let done0=false;
    const done=ok=>{ if(done0) return; done0=true; const n=parseFloat(inp.value); inp.remove();
      if(ok&&isFinite(n)){ range.value=Math.max(+range.min||0,Math.min(+range.max||100,n));
        range.dispatchEvent(new Event('input',{bubbles:true})); range.dispatchEvent(new Event('change',{bubbles:true})); }
      if(!valSpan.textContent) valSpan.textContent=range.value; };   // handlerがvalSpanを更新しない場合の保険
    inp.addEventListener('keydown',e=>{ e.stopPropagation(); if(e.key==='Enter')done(true); if(e.key==='Escape')done(false); });
    inp.addEventListener('blur',()=>done(true));
  });
});
// レーン構成スライダー（ノーツ:ライト＝計6・プロジェクト状態を直接編集。既存のレーン増減を流用）
{ const el=document.getElementById('laneRatio'), lv=document.getElementById('laneRatioVal');
  if(el){ el.value=notesLanes; if(lv) lv.textContent=notesLanes+' : '+lightLanes;
    el.addEventListener('input',()=>{ const n=+el.value; if(lv) lv.textContent=n+' : '+(6-n); });   // ドラッグ中はラベルだけ
    el.addEventListener('change',()=>{ try{ localStorage.setItem('bsnm_laneratio',String(el.value)); }catch(e){} setLaneRatio(+el.value); }); } }   // 個人の初期設定として保存＋現プロジェクトへ適用
const langSel=document.getElementById('langSel'); langSel.value=langCode;
langSel.onchange=()=>{ langCode=langSel.value; localStorage.setItem('bsnm_lang',langCode); loadLang(); };
// ---- 数値ステッパー共通（BPM・プレビュー秒）: ‹›=±1 / Shift+‹›=±0.1 / 値クリック=手打ち ----
function wireStepper(el,{get,set,fmt,editFmt,prefix='',step=1,shiftStep=0.1}){   // editFmt=編集時の表示（単位を除く等）。無ければfmt
  if(!el) return; const v=el.querySelector('.bfV'); if(!v) return;
  const sync=()=>{ if(!v.querySelector('input')) v.textContent=prefix+fmt(get()); };
  el.querySelectorAll('.bfA').forEach(a=>a.addEventListener('click',e2=>{
    set(get()+(a.dataset.k==='up'?1:-1)*(e2.shiftKey?shiftStep:step)); sync(); }));   // ‹›=±step / Shift+‹›=±shiftStep（既定 ±1 / ±0.1）
  const startEdit=()=>{ if(v.querySelector('input')) return;   // 見出し/数値どちらのクリックでも編集。ラベルも消して入力欄を全幅に（Blender風）・欄幅は固定のまま
    const lbl=el.querySelector('.bfLbl'), fw=el.getBoundingClientRect().width;
    el.style.width=fw+'px';                                    // 欄幅を今の幅に固定（ラベルを隠しても縮まない）
    if(lbl) lbl.style.display='none';                          // 見出しを隠す
    v.style.flex='1'; v.style.width='auto'; v.style.marginLeft='0';   // 数値欄を全幅へ広げる
    const inp=document.createElement('input'); inp.type='text'; inp.value=(editFmt||fmt)(get());   // 編集中は単位を除いた数値だけ（秒など）
    inp.style.cssText='width:100%;box-sizing:border-box;background:#1f1f1f;border:1px solid var(--accent,#8160e3);border-radius:3px;color:#eee;font:inherit;text-align:center;outline:none;padding:0 4px;margin:0;';
    v.textContent=''; v.appendChild(inp); inp.focus(); inp.select();
    let done0=false;
    const done=ok=>{ if(done0) return; done0=true; const n=parseFloat(inp.value);
      if(ok&&isFinite(n)) set(n); inp.remove();
      el.style.width=''; if(lbl) lbl.style.display=''; v.style.flex=''; v.style.width=''; v.style.marginLeft='';   // 元に戻す
      sync(); };
    inp.addEventListener('keydown',e2=>{ e2.stopPropagation(); if(e2.key==='Enter')done(true); if(e2.key==='Escape')done(false); });
    inp.addEventListener('blur',()=>done(true)); };
  v.addEventListener('click',startEdit);
  const lbl=el.querySelector('.bfLbl'); if(lbl) lbl.addEventListener('click',startEdit);   // 見出しクリックでも入力（Blender風）
  el._sync=sync; sync();
}
// プレビュー秒を Info.dat(infoBase) へ書き込む（applyInfoChain→infoJson→書き出しに反映）
function setPreview(key,v){ v=Math.max(0,Math.round(v*100)/100); infoBase=infoBase||{}; infoBase[key]=v; applyInfoChain(); metaDirty=true; }
function refreshMusicHdr(){ ['bpmField','pvStart','pvDur','njsField','offField','leadInField'].forEach(id=>{ const el=document.getElementById(id); if(el&&el._sync) el._sync(); }); refreshChainPanel(); refreshArcPanel(); }
wireStepper(document.getElementById('bpmField'),{get:()=>BPM,set:setBPMv,fmt:x=>x.toFixed(2)});   // 見出し「BPM」は .bfLbl（フィールド内）に分離
wireStepper(document.getElementById('pvStart'),{get:()=>{ const x=(infoBase||{})._previewStartTime; return (x==null||x==='')?12:+x; },set:v=>setPreview('_previewStartTime',v),fmt:x=>x.toFixed(2)+' '+t('ui.secUnit','秒'),editFmt:x=>x.toFixed(2)});
wireStepper(document.getElementById('pvDur'),{get:()=>{ const x=(infoBase||{})._previewDuration; return (x==null||x==='')?10:+x; },set:v=>setPreview('_previewDuration',v),fmt:x=>parseFloat(x.toFixed(2))+' '+t('ui.secUnit','秒'),editFmt:x=>String(parseFloat(x.toFixed(2)))});   // プレビュー長は末尾の.00を省く（10.00→10）
wireStepper(document.getElementById('njsField'),{get:()=>njsOffCur().njs, set:v=>setNjsCur('njs',Math.max(0,Math.round(v*100)/100)), fmt:x=>String(parseFloat((+x).toFixed(2)))});   // 飛来速度NJS（難易度別・整数～小数）
wireStepper(document.getElementById('offField'),{get:()=>njsOffCur().offset, set:v=>setNjsCur('offset',Math.round(v*1000)/1000), fmt:x=>(+x).toFixed(3), step:0.01, shiftStep:0.001});   // 飛来オフセット（難易度別・0.000表示・‹›=±0.01・Shift=±0.001）
// 曲頭への無音追加（ms・全難易度共通）。songNode.offsetは負の秒数として保持し、
// getSongOff()経由でプレビュー再生にもそのまま反映される。書き出し時はexportMap()がffmpegで
// song.eggへ実際に焼き込む（追加方向のみ・Info.dat側の対応状況に依存しない確実な方式）。
function getLeadInMs(){ const o=songNode&&songNode.offset; return (isFinite(o)&&o<0)?Math.round(-o*1000):0; }
function setLeadInMs(ms){ if(!songNode) return; ms=Math.max(0,Math.round(ms));
  songNode.offset=ms>0?-(ms/1000):0; metaDirty=true;
  if(audioBuf) buildWaveData();
  if(pv4On&&typeof pv4Push==='function') pv4Push(); }
wireStepper(document.getElementById('leadInField'),{get:getLeadInMs, set:setLeadInMs, fmt:x=>Math.round(x)+' ms', editFmt:x=>String(Math.round(x)), step:10, shiftStep:1});
{ const b=document.getElementById('tempoDetectAllBtn'); if(b) b.addEventListener('click',()=>autoDetectAllTempoParts()); }
setInterval(refreshMusicHdr,300);   // BPM/プレビュー/NJS/オフセットは曲読込・難易度切替・マーカー転送など外部からも変わるため定期同期
// ---- 簡易レベルメーター ----
// varで宣言: 初期化時のresize()がこの定義より先に走ってもTDZにならない
var vmEl=null, vmg=null, vmW=0, vmH=0, vmHold=0;
function vmResize(){ vmEl=vmEl||document.getElementById('vmcv'); if(!vmEl) return;
  vmg=vmg||vmEl.getContext('2d');
  const r=vmEl.getBoundingClientRect();
  vmW=r.width; vmH=r.height; vmEl.width=vmW*devicePixelRatio; vmEl.height=vmH*devicePixelRatio;
  vmg.setTransform(devicePixelRatio,0,0,devicePixelRatio,0,0); }
function drawMeter(){
  if(!vmW||!vmg) return;
  analyser.getFloatTimeDomainData(vmData);
  let pk=0; for(let i=0;i<vmData.length;i+=2){ const a=Math.abs(vmData[i]); if(a>pk) pk=a; }
  vmHold=Math.max(pk,vmHold*0.96);
  vmg.clearRect(0,0,vmW,vmH); vmg.fillStyle='#101010'; vmg.fillRect(0,0,vmW,vmH);
  const toN=v=>{ const db=20*Math.log10(Math.max(1e-4,v)); return Math.max(0,Math.min(1,(db+50)/50)); };
  const topPad=5, mH=vmH-10, barX=2, barW=Math.max(6,vmW-22), bot=topPad+mH;
  // dB目盛り（0〜50 = 0〜-50dBFS）
  vmg.font='8px '+FONT; vmg.fillStyle='#7a7a7a'; vmg.textAlign='left'; vmg.textBaseline='middle';
  vmg.strokeStyle='#3a3a3a'; vmg.lineWidth=1;
  for(const d of [0,5,10,15,20,30,40,50]){
    const y=topPad+(d/50)*mH;
    vmg.beginPath(); vmg.moveTo(barX+barW+1,y); vmg.lineTo(barX+barW+4,y); vmg.stroke();
    vmg.fillText(String(d),barX+barW+5,y);
  }
  const yFor=db=>topPad+(-db/50)*mH;                 // dbは負値
  const lvlY=bot-toN(pk)*mH, gTop=yFor(-18), yTop=yFor(-9);
  vmg.fillStyle='#3ddc84'; vmg.fillRect(barX,Math.max(lvlY,gTop),barW,Math.max(0,bot-Math.max(lvlY,gTop)));
  if(lvlY<gTop){ vmg.fillStyle='#ffd23d'; vmg.fillRect(barX,Math.max(lvlY,yTop),barW,gTop-Math.max(lvlY,yTop)); }
  if(lvlY<yTop){ vmg.fillStyle='#ff4d4d'; vmg.fillRect(barX,lvlY,barW,yTop-lvlY); }
  const py=bot-toN(vmHold)*mH;
  vmg.fillStyle='#ddd'; vmg.fillRect(barX,Math.max(topPad,py),barW,1.5);
}
// ---- 初期化 ----
setPvMode('media'); setNodeMode('edit');   // 起動時はMEDIAを先に表示（ヘルバ様指示）
setNodeColMode('nle');   // 切替はTabのみ（ラベルクリックでの切替は廃止）
const _bootReady=buildToolbar().then(()=>{ updateMainModeLabel(); return loadLang(); });   // ツールバーのアイコン＋言語適用の完了を待てるようにPromiseを保持
if(!sections.length) newDefaultGraph();   // 起動直後はデフォルト盤面
vmResize(); applyModeDim();
// ---- ボリューム下ツール: BPM測定 / メトロノーム（既存機能への入口。アイコン=icons/bpm.svg, metronome.svg） ----
(async()=>{
  const bb=document.getElementById('vmBpmBtn'), mb=document.getElementById('vmMetroBtn');
  if(bb){ bb.innerHTML=await tbIcon('bpm'); bb.onclick=e=>runBpmEstimate(e); }
  if(mb){ mb.innerHTML=await tbIcon('metronome');
    const sync=()=>{ const n=metroNode(); mb.classList.toggle('on',!!(n&&n.data&&n.data.on)); };
    mb.onclick=()=>{ let n=metroNode();
      if(n){ n.data.on=n.data.on?0:1; } else { n=createExtra('metro',0,0); }
      metaDirty=true; sync(); stat(n.data.on?'メトロノーム ON':'メトロノーム OFF'); };
    sync(); setInterval(sync,1000); }   // プロジェクト読込等で外から状態が変わっても追従
  // BPMステッパーはMusicレーン左溝（drawOvGutter）へ移設
})();
// フォント読込完了後、代替フォントで焼けたCanvasテクスチャを作り直す
document.fonts.ready.then(()=>{
  [numTexCache,markNameTexCache,numSprTexCache,laneTexCache,tmNameTexCache].forEach(c=>{ for(const k in c) delete c[k]; });
  laneNameSprites.forEach((sp,i)=>{ sp.material.map=laneTex(LIGHT_LANES[i].n); sp.material.needsUpdate=true; });
});

// ---- Blender風スプリッタ: ペイン境界ドラッグでリサイズ（位置は自動保存→次回起動時に復元。localStorage=ブラウザプロファイル単位=ユーザーごと） ----
function saveSplits(){ localStorage.setItem('bsnm_split',JSON.stringify({
  v:Math.round(document.getElementById('pvpane').getBoundingClientRect().width),
  h:Math.round(document.getElementById('toprow').getBoundingClientRect().height)})); }
{ let sv={}; try{ sv=JSON.parse(localStorage.getItem('bsnm_split')||'{}'); }catch(e){}
  if(sv.v>0) document.getElementById('pvpane').style.width=Math.max(240,Math.min(innerWidth*0.6,sv.v))+'px';   // ウィンドウが小さくなっていても範囲内へクランプ
  if(sv.h>0) document.getElementById('toprow').style.height=Math.max(120,Math.min(innerHeight*0.7,sv.h))+'px';
  if(sv.v>0||sv.h>0) resize(); }
// ---- 起動カバーの解除: 初期化(ツールバー+言語)＋レイアウト確定後に暗幕を外す（FOUC防止）----
// 万一 buildToolbar/loadLang が失敗しても操作不能にならないよう、load・3.5秒のフォールバックも張る（idempotent）
function _bootReveal(){ const bc=document.getElementById('bootCover'); if(bc&&!bc._gone){ bc._gone=1; bc.style.opacity='0'; setTimeout(()=>{ try{ bc.remove(); }catch(_){}} ,240); } }
_bootReady.catch(()=>{}).then(()=>requestAnimationFrame(()=>requestAnimationFrame(()=>{ try{ resize(); }catch(_){} _bootReveal(); })));   // 2フレーム待ってレイアウト確定→表示
addEventListener('load',()=>setTimeout(_bootReveal,120));
setTimeout(_bootReveal,3500);
// exe版: ダブルクリックで渡されたファイルを開く。rAFはタブ非表示/最小化で発火しないため、
// タイマー/promiseベース（bootReady と load の両方、先に来た方）で確実に1回だけ呼ぶ。
_bootReady.catch(()=>{}).then(()=>{ try{ openFromNativeArg(); }catch(_){} });
addEventListener('load',()=>setTimeout(()=>{ try{ openFromNativeArg(); }catch(_){} },200));
setTimeout(()=>{ try{ openFromNativeArg(); }catch(_){} },1500);
function makeSplit(id, start, move){
  const el = document.getElementById(id);
  if(!el) return;
  el.addEventListener('pointerdown', e=>{
    e.preventDefault(); try{ el.setPointerCapture(e.pointerId); }catch(_){} el.classList.add('drag');
    const sx=e.clientX, sy=e.clientY, st=start();
    const mv=ev=>{ move(st, ev.clientX-sx, ev.clientY-sy); resize(); };
    const up=ev=>{ el.classList.remove('drag'); el.removeEventListener('pointermove',mv);
      el.removeEventListener('pointerup',up); el.removeEventListener('pointercancel',up);
      saveSplits(); };   // ドラッグを離した時に保存
    el.addEventListener('pointermove',mv); el.addEventListener('pointerup',up); el.addEventListener('pointercancel',up);
  });
}
makeSplit('splitV',
  ()=>document.getElementById('pvpane').getBoundingClientRect().width,
  (w,dx,dy)=>{ document.getElementById('pvpane').style.width=Math.max(240,Math.min(innerWidth*0.6,w+dx))+'px'; });
makeSplit('splitH',
  ()=>document.getElementById('toprow').getBoundingClientRect().height,
  (h,dx,dy)=>{ document.getElementById('toprow').style.height=Math.max(120,Math.min(innerHeight*0.7,h+dy))+'px'; });

let perfFrames=0, perfLast=performance.now();


  const rt = {
    THREE,
    OrbitControls,
    makeChamferBoxGeometry,
    EffectComposer,
    RenderPass,
    UnrealBloomPass,
    mergeGeometries,
  };
  try { rt.LANE = LANE; } catch (_) {}
  try { rt.LAYER = LAYER; } catch (_) {}
  try { rt.BASE_Y = BASE_Y; } catch (_) {}
  try { rt.ZPB = ZPB; } catch (_) {}
  try { rt.RED = RED; } catch (_) {}
  try { rt.BLUE = BLUE; } catch (_) {}
  try { rt.cRED = cRED; } catch (_) {}
  try { rt.cBLUE = cBLUE; } catch (_) {}
  try { rt.LRED = LRED; } catch (_) {}
  try { rt.LBLUE = LBLUE; } catch (_) {}
  try { rt.LRED_B = LRED_B; } catch (_) {}
  try { rt.LBLUE_B = LBLUE_B; } catch (_) {}
  try { rt.hexOf = hexOf; } catch (_) {}
  try { rt.FONT = FONT; } catch (_) {}
  try { rt.MAXANISO = MAXANISO; } catch (_) {}
  try { rt.DIRICON = DIRICON; } catch (_) {}
  try { rt.DIRV = DIRV; } catch (_) {}
  try { rt.ROT = ROT; } catch (_) {}
  try { rt.DIR_ANGLE = DIR_ANGLE; } catch (_) {}
  try { rt.cv = cv; } catch (_) {}
  try { rt.renderer = renderer; } catch (_) {}
  try { rt.dprScale = dprScale; } catch (_) {}
  try { rt.gpuName = gpuName; } catch (_) {}
  try { rt.scene = scene; } catch (_) {}
  try { rt.camera = camera; } catch (_) {}
  try { rt.controls = controls; } catch (_) {}
  try { rt.dl = dl; } catch (_) {}
  try { rt.LANG = LANG; } catch (_) {}
  try { rt.langCode = langCode; } catch (_) {}
  try { rt.TL = TL; } catch (_) {}
  try { rt.curTab = curTab; } catch (_) {}
  try { rt.pvMode = pvMode; } catch (_) {}
  try { rt.nodeMode = nodeMode; } catch (_) {}
  try { rt.nodeColMode = nodeColMode; } catch (_) {}
  try { rt.hoverPane = hoverPane; } catch (_) {}
  try { rt.KEYS_COMMON = KEYS_COMMON; } catch (_) {}
  try { rt.KEYS_NOTE = KEYS_NOTE; } catch (_) {}
  try { rt.KEYS_LIGHT = KEYS_LIGHT; } catch (_) {}
  try { rt.orbitDrag = orbitDrag; } catch (_) {}
  try { rt.panDrag = panDrag; } catch (_) {}
  try { rt.bgGrid = bgGrid; } catch (_) {}
  try { rt.floor = floor; } catch (_) {}
  try { rt.editGroup = editGroup; } catch (_) {}
  try { rt.cellPlanes = cellPlanes; } catch (_) {}
  try { rt.editFill = editFill; } catch (_) {}
  try { rt.mouseLine = mouseLine; } catch (_) {}
  try { rt.playFrame = playFrame; } catch (_) {}
  try { rt.playFill = playFill; } catch (_) {}
  try { rt.playFloorLine = playFloorLine; } catch (_) {}
  try { rt.NUMX = NUMX; } catch (_) {}
  try { rt.playDiamond = playDiamond; } catch (_) {}
  try { rt.scrubDrag = scrubDrag; } catch (_) {}
  try { rt.subPool = subPool; } catch (_) {}
  try { rt.beatPool = beatPool; } catch (_) {}
  try { rt.numTexCache = numTexCache; } catch (_) {}
  try { rt.numGeo = numGeo; } catch (_) {}
  try { rt.numPool = numPool; } catch (_) {}
  try { rt.numStripGeo = numStripGeo; } catch (_) {}
  try { rt.numStrip = numStrip; } catch (_) {}
  try { rt.markerPool = markerPool; } catch (_) {}
  try { rt.mkBaseX = mkBaseX; } catch (_) {}
  try { rt.markNameGeo = markNameGeo; } catch (_) {}
  try { rt.markNameTexCache = markNameTexCache; } catch (_) {}
  try { rt.tmPool = tmPool; } catch (_) {}
  try { rt.tmNameTexCache = tmNameTexCache; } catch (_) {}
  try { rt.LIGHT_LANES = LIGHT_LANES; } catch (_) {}
  try { rt.laneIdxByType = laneIdxByType; } catch (_) {}
  try { rt.LANE_DX = LANE_DX; } catch (_) {}
  try { rt.LANE_X0 = LANE_X0; } catch (_) {}
  try { rt.lightEvents = lightEvents; } catch (_) {}
  try { rt.lightGroup = lightGroup; } catch (_) {}
  try { rt.laneTexCache = laneTexCache; } catch (_) {}
  try { rt.laneAreaW = laneAreaW; } catch (_) {}
  try { rt.laneAreaCX = laneAreaCX; } catch (_) {}
  try { rt.laneFloor = laneFloor; } catch (_) {}
  try { rt.laneNameSprites = laneNameSprites; } catch (_) {}
  try { rt.laneBeatPool = laneBeatPool; } catch (_) {}
  try { rt.laneSubPool = laneSubPool; } catch (_) {}
  try { rt._flashBars = _flashBars; } catch (_) {}
  try { rt._fadeTri = _fadeTri; } catch (_) {}
  try { rt._transBow = _transBow; } catch (_) {}
  try { rt.CHIP_GEOS = CHIP_GEOS; } catch (_) {}
  try { rt.CHIP_EDGES = CHIP_EDGES; } catch (_) {}
  try { rt.numSprTexCache = numSprTexCache; } catch (_) {}
  try { rt.chipPool = chipPool; } catch (_) {}
  try { rt.lightMode = lightMode; } catch (_) {}
  try { rt.lightHover = lightHover; } catch (_) {}
  try { rt.lastLightFTime = lastLightFTime; } catch (_) {}
  try { rt.lightMove = lightMove; } catch (_) {}
  try { rt.pvShowNotes = pvShowNotes; } catch (_) {}
  try { rt.pvShowLights = pvShowLights; } catch (_) {}
  try { rt.pvShowStruct = pvShowStruct; } catch (_) {}
  try { rt.pvShowAmbient = pvShowAmbient; } catch (_) {}
  try { rt.lightSelection = lightSelection; } catch (_) {}
  try { rt.lightBrush = lightBrush; } catch (_) {}
  try { rt.getLightChroma = getLightChroma; } catch (_) {}
  try { rt.setLightChroma = setLightChroma; } catch (_) {}
  try { rt.applyLightChroma = applyLightChroma; } catch (_) {}
  try { rt.hexToRgb01 = hexToRgb01; } catch (_) {}
  try { rt.rgb01ToHex = rgb01ToHex; } catch (_) {}
  try { rt.L_BEHAV_N = L_BEHAV_N; } catch (_) {}
  try { rt._lgMat = _lgMat; } catch (_) {}
  try { rt._lgBody = _lgBody; } catch (_) {}
  try { rt._lgWire = _lgWire; } catch (_) {}
  try { rt._lgNum = _lgNum; } catch (_) {}
  try { rt.lightGhost = lightGhost; } catch (_) {}
  try { rt.ovWave = ovWave; } catch (_) {}
  try { rt.ovWaveLen = ovWaveLen; } catch (_) {}
  try { rt.ovBeats = ovBeats; } catch (_) {}
  try { rt.sections = sections; } catch (_) {}
  try { rt.SEC_COLORS = SEC_COLORS; } catch (_) {}
  try { rt.ovcv = ovcv; } catch (_) {}
  try { rt.ovg = ovg; } catch (_) {}
  try { rt.ovW = ovW; } catch (_) {}
  try { rt.ovH = ovH; } catch (_) {}
  try { rt.tlSpan = tlSpan; } catch (_) {}
  try { rt.tlFrozen = tlFrozen; } catch (_) {}
  try { rt.ovWin = ovWin; } catch (_) {}
  try { rt.tlViewB0 = tlViewB0; } catch (_) {}
  try { rt.tlB0 = tlB0; } catch (_) {}
  try { rt.TLGUT = TLGUT; } catch (_) {}
  try { rt.beatToX = beatToX; } catch (_) {}
  try { rt.xToBeat = xToBeat; } catch (_) {}
  try { rt.markers = markers; } catch (_) {}
  try { rt._mkSeq = _mkSeq; } catch (_) {}
  try { rt._mkRects = _mkRects; } catch (_) {}
  try { rt.ovPan = ovPan; } catch (_) {}
  try { rt.musicBeat = musicBeat; } catch (_) {}
  try { rt.musicDrag = musicDrag; } catch (_) {}
  try { rt.musicSegs = musicSegs; } catch (_) {}
  try { rt.musicSelSet = musicSelSet; } catch (_) {}
  try { rt.musicResize = musicResize; } catch (_) {}
  try { rt._ovEdgeHover = _ovEdgeHover; } catch (_) {}
  try { rt._ovClipHover = _ovClipHover; } catch (_) {}
  try { rt._musicBoxes = _musicBoxes; } catch (_) {}
  try { rt._EMPTY_SEGS = _EMPTY_SEGS; } catch (_) {}
  try { rt.PR_TAG_H = PR_TAG_H; } catch (_) {}
  try { rt.tgDrag = tgDrag; } catch (_) {}
  try { rt.ndcv = ndcv; } catch (_) {}
  try { rt.ndg = ndg; } catch (_) {}
  try { rt.ndW = ndW; } catch (_) {}
  try { rt.ndH = ndH; } catch (_) {}
  try { rt.ndCam = ndCam; } catch (_) {}
  try { rt.ndView = ndView; } catch (_) {}
  try { rt.ndDrag = ndDrag; } catch (_) {}
  try { rt.ND_W = ND_W; } catch (_) {}
  try { rt.SIGNALS = SIGNALS; } catch (_) {}
  try { rt.IOW = IOW; } catch (_) {}
  try { rt.graphIO = graphIO; } catch (_) {}
  try { rt.cutSet = cutSet; } catch (_) {}
  try { rt._nid = _nid; } catch (_) {}
  try { rt.graphEdges = graphEdges; } catch (_) {}
  try { rt.wireDrag = wireDrag; } catch (_) {}
  try { rt._ndMouse = _ndMouse; } catch (_) {}
  try { rt.edgesInited = edgesInited; } catch (_) {}
  try { rt.SIG_NAME = SIG_NAME; } catch (_) {}
  try { rt.SIGC = SIGC; } catch (_) {}
  try { rt.ENW = ENW; } catch (_) {}
  try { rt.extraNodes = extraNodes; } catch (_) {}
  try { rt.EN_DEF = EN_DEF; } catch (_) {}
  try { rt.NHEAD = NHEAD; } catch (_) {}
  try { rt.NROWH = NROWH; } catch (_) {}
  try { rt.NPADT = NPADT; } catch (_) {}
  try { rt._ndWidgets = _ndWidgets; } catch (_) {}
  try { rt._pickOpen = _pickOpen; } catch (_) {}
  try { rt.ndSel = ndSel; } catch (_) {}
  try { rt.ndMultiSel = ndMultiSel; } catch (_) {}
  try { rt.ndBoxSel = ndBoxSel; } catch (_) {}
  try { rt.hx2 = hx2; } catch (_) {}
  try { rt.altIns = altIns; } catch (_) {}
  try { rt.altOuts = altOuts; } catch (_) {}
  try { rt.altSongs = altSongs; } catch (_) {}
  try { rt.activeUids = activeUids; } catch (_) {}
  try { rt.songDeleted = songDeleted; } catch (_) {}
  try { rt.ndClip = ndClip; } catch (_) {}
  try { rt.OUT_DIFFS = OUT_DIFFS; } catch (_) {}
  try { rt._coverImgs = _coverImgs; } catch (_) {}
  try { rt.outDirHandle = outDirHandle; } catch (_) {}
  try { rt.songNode = songNode; } catch (_) {}
  try { rt._coverURL = _coverURL; } catch (_) {}
  try { rt._coverKey = _coverKey; } catch (_) {}
  try { rt.EN_FIELDS = EN_FIELDS; } catch (_) {}
  try { rt.EN_NUM = EN_NUM; } catch (_) {}
  try { rt.LGUT = LGUT; } catch (_) {}
  try { rt.MKRH = MKRH; } catch (_) {}
  try { rt.LRULER = LRULER; } catch (_) {}
  try { rt.LANE_MAX = LANE_MAX; } catch (_) {}
  try { rt.LDIV = LDIV; } catch (_) {}
  try { rt.notesLanes = notesLanes; } catch (_) {}
  try { rt.lightLanes = lightLanes; } catch (_) {}
  try { rt.laneScrN = laneScrN; } catch (_) {}
  try { rt.laneScrL = laneScrL; } catch (_) {}
  try { rt.STRIP_COLS = STRIP_COLS; } catch (_) {}
  try { rt.layerPan = layerPan; } catch (_) {}
  try { rt.layerDrag = layerDrag; } catch (_) {}
  try { rt.layerRazor = layerRazor; } catch (_) {}
  try { rt.layerSeek = layerSeek; } catch (_) {}
  try { rt.layerBand = layerBand; } catch (_) {}
  try { rt.layerSel = layerSel; } catch (_) {}
  try { rt.markerDrag = markerDrag; } catch (_) {}
  try { rt.layerResize = layerResize; } catch (_) {}
  try { rt.layerClipboard = layerClipboard; } catch (_) {}
  try { rt._ndEdgeHover = _ndEdgeHover; } catch (_) {}
  try { rt._ndClipHover = _ndClipHover; } catch (_) {}
  try { rt.tlHoverBeat = tlHoverBeat; } catch (_) {}
  try { rt.layerMuteS = layerMuteS; } catch (_) {}
  try { rt.layerSoloS = layerSoloS; } catch (_) {}
  try { rt.layerLockS = layerLockS; } catch (_) {}
  try { rt.objLockedN = objLockedN; } catch (_) {}
  try { rt.objLockedL = objLockedL; } catch (_) {}
  try { rt._lgBtns = _lgBtns; } catch (_) {}
  try { rt._clipSw = _clipSw; } catch (_) {}
  try { rt.layerVisible = layerVisible; } catch (_) {}
  try { rt._LCT = _LCT; } catch (_) {}
  try { rt._flatDirty = _flatDirty; } catch (_) {}
  try { rt._ndMouseY = _ndMouseY; } catch (_) {}
  try { rt.layerPaste = layerPaste; } catch (_) {}
  try { rt.MIR_D = MIR_D; } catch (_) {}
  try { rt.ctxEl = ctxEl; } catch (_) {}
  try { rt._menuHidAt = _menuHidAt; } catch (_) {}
  try { rt.prcv = prcv; } catch (_) {}
  try { rt.prg = prg; } catch (_) {}
  try { rt.prW = prW; } catch (_) {}
  try { rt.prH = prH; } catch (_) {}
  try { rt.prSeek = prSeek; } catch (_) {}
  try { rt.metaDirty = metaDirty; } catch (_) {}
  try { rt.arrowTex = arrowTex; } catch (_) {}
  try { rt.dotTex = dotTex; } catch (_) {}
  try { rt.markGeo = markGeo; } catch (_) {}
  try { rt.noteGeo = noteGeo; } catch (_) {}
  try { rt.NOTE_THIN = NOTE_THIN; } catch (_) {}
  try { rt.arrowMatS = arrowMatS; } catch (_) {}
  try { rt.dotMatS = dotMatS; } catch (_) {}
  try { rt.bombGeo = bombGeo; } catch (_) {}
  try { rt.chainHeadGeo = chainHeadGeo; } catch (_) {}
  try { rt.chainLinkGeo = chainLinkGeo; } catch (_) {}
  try { rt.bombMat = bombMat; } catch (_) {}
  try { rt.bombRingGeo = bombRingGeo; } catch (_) {}
  try { rt.bombRingMat = bombRingMat; } catch (_) {}
  try { rt.wallMat = wallMat; } catch (_) {}
  try { rt.wallEdgeMat = wallEdgeMat; } catch (_) {}
  try { rt.arcMats = arcMats; } catch (_) {}
  try { rt.selGeom = selGeom; } catch (_) {}
  try { rt.selEdge = selEdge; } catch (_) {}
  try { rt.selPool = selPool; } catch (_) {}
  try { rt.dupPool = dupPool; } catch (_) {}
  try { rt.groupSelBox = groupSelBox; } catch (_) {}
  try { rt.NOTE_MATS = NOTE_MATS; } catch (_) {}
  try { rt.NOTE_MATS_HOT = NOTE_MATS_HOT; } catch (_) {}
  try { rt.NOTE_MATS_DIM = NOTE_MATS_DIM; } catch (_) {}
  try { rt.NOTE_MATS_GHOST = NOTE_MATS_GHOST; } catch (_) {}
  try { rt.dupNoteSet = dupNoteSet; } catch (_) {}
  try { rt.dupLightSet = dupLightSet; } catch (_) {}
  try { rt.dupNoteBeats = dupNoteBeats; } catch (_) {}
  try { rt.dupLightBeats = dupLightBeats; } catch (_) {}
  try { rt.dupNoteCount = dupNoteCount; } catch (_) {}
  try { rt.dupLightCount = dupLightCount; } catch (_) {}
  try { rt.dupNoteList = dupNoteList; } catch (_) {}
  try { rt.dupLightList = dupLightList; } catch (_) {}
  try { rt._dupNoteIdx = _dupNoteIdx; } catch (_) {}
  try { rt._dupLightIdx = _dupLightIdx; } catch (_) {}
  try { rt.notes = notes; } catch (_) {}
  try { rt.bombs = bombs; } catch (_) {}
  try { rt.walls = walls; } catch (_) {}
  try { rt.arcs = arcs; } catch (_) {}
  try { rt.chains = chains; } catch (_) {}
  try { rt.meshes = meshes; } catch (_) {}
  try { rt.BUILDERS = BUILDERS; } catch (_) {}
  try { rt.BPM = BPM; } catch (_) {}
  try { rt.songDur = songDur; } catch (_) {}
  try { rt.cur = cur; } catch (_) {}
  try { rt.snap = snap; } catch (_) {}
  try { rt.brush = brush; } catch (_) {}
  try { rt.curAnim = curAnim; } catch (_) {}
  try { rt.vwB = vwB; } catch (_) {}
  try { rt.vwPlayD = vwPlayD; } catch (_) {}
  try { rt.selection = selection; } catch (_) {}
  try { rt.snapV = snapV; } catch (_) {}
  try { rt.HIST_MAX = HIST_MAX; } catch (_) {}
  try { rt.undoStack = undoStack; } catch (_) {}
  try { rt.redoStack = redoStack; } catch (_) {}
  try { rt.DOM_LABEL = DOM_LABEL; } catch (_) {}
  try { rt.pal = pal; } catch (_) {}
  try { rt.cRed = cRed; } catch (_) {}
  try { rt.cBlue = cBlue; } catch (_) {}
  try { rt.typeBtns = typeBtns; } catch (_) {}
  try { rt.lbBehavEl = lbBehavEl; } catch (_) {}
  try { rt.snapVals = snapVals; } catch (_) {}
  try { rt.snapsEl = snapsEl; } catch (_) {}
  try { rt.actx = actx; } catch (_) {}
  try { rt.masterGain = masterGain; } catch (_) {}
  try { rt.gain = gain; } catch (_) {}
  try { rt.analyser = analyser; } catch (_) {}
  try { rt.vmData = vmData; } catch (_) {}
  try { rt.audioBuf = audioBuf; } catch (_) {}
  try { rt.srcNs = srcNs; } catch (_) {}
  try { rt.playing = playing; } catch (_) {}
  try { rt.startedAt = startedAt; } catch (_) {}
  try { rt.offset = offset; } catch (_) {}
  try { rt.playStartB = playStartB; } catch (_) {}
  try { rt.avOffset = avOffset; } catch (_) {}
  try { rt.keyShow = keyShow; } catch (_) {}
  try { rt.hitGain = hitGain; } catch (_) {}
  try { rt.metroGain = metroGain; } catch (_) {}
  try { rt.metroFlashMs = metroFlashMs; } catch (_) {}
  try { rt.prevPlayBeat = prevPlayBeat; } catch (_) {}
  try { rt.files = files; } catch (_) {}
  try { rt.handles = handles; } catch (_) {}
  try { rt.dirHandle = dirHandle; } catch (_) {}
  try { rt.rawDiff = rawDiff; } catch (_) {}
  try { rt.diffV3 = diffV3; } catch (_) {}
  try { rt.currentDiffName = currentDiffName; } catch (_) {}
  try { rt.projDiffs = projDiffs; } catch (_) {}
  try { rt.infoText = infoText; } catch (_) {}
  try { rt.infoFileName = infoFileName; } catch (_) {}
  try { rt.projFileHandle = projFileHandle; } catch (_) {}
  try { rt.infoJson = infoJson; } catch (_) {}
  try { rt.infoBase = infoBase; } catch (_) {}
  try { rt.infoDirty = infoDirty; } catch (_) {}
  try { rt.EMPTY_V3 = EMPTY_V3; } catch (_) {}
  try { rt.libDirs = libDirs; } catch (_) {}
  try { rt._dragMedia = _dragMedia; } catch (_) {}
  try { rt._mediaGhostNd = _mediaGhostNd; } catch (_) {}
  try { rt._mediaGhostOv = _mediaGhostOv; } catch (_) {}
  try { rt._restoringLibs = _restoringLibs; } catch (_) {}
  try { rt.lineSrc = lineSrc; } catch (_) {}
  try { rt.AUDIO_EXTS = AUDIO_EXTS; } catch (_) {}
  try { rt.IMAGE_EXTS = IMAGE_EXTS; } catch (_) {}
  try { rt._libActiveCat = _libActiveCat; } catch (_) {}
  try { rt.LIB_CLIP_NOTES_ICO = LIB_CLIP_NOTES_ICO; } catch (_) {}
  try { rt.LIB_CLIP_LIGHT_ICO = LIB_CLIP_LIGHT_ICO; } catch (_) {}
  try { rt.ICO_N_MINI = ICO_N_MINI; } catch (_) {}
  try { rt.ICO_L_MINI = ICO_L_MINI; } catch (_) {}
  try { rt.LIB_FOLDER_ICO = LIB_FOLDER_ICO; } catch (_) {}
  try { rt.LIB_ALL_ICO = LIB_ALL_ICO; } catch (_) {}
  try { rt.LIB_WAVE_ICO = LIB_WAVE_ICO; } catch (_) {}
  try { rt._ENC = _ENC; } catch (_) {}
  try { rt._RAWSKIP = _RAWSKIP; } catch (_) {}
  try { rt._CKEYS = _CKEYS; } catch (_) {}
  try { rt.njsCfg = njsCfg; } catch (_) {}
  try { rt._DIFF_RANK = _DIFF_RANK; } catch (_) {}
  try { rt._DIFF_NJS = _DIFF_NJS; } catch (_) {}
  try { rt.raycaster = raycaster; } catch (_) {}
  try { rt.pointer = pointer; } catch (_) {}
  try { rt.hoverBeat = hoverBeat; } catch (_) {}
  try { rt.placeMode = placeMode; } catch (_) {}
  try { rt.ghostCell = ghostCell; } catch (_) {}
  try { rt.ghostKey = ghostKey; } catch (_) {}
  try { rt.lockBeat = lockBeat; } catch (_) {}
  try { rt.floorPlane = floorPlane; } catch (_) {}
  try { rt._fv = _fv; } catch (_) {}
  try { rt.ghost = ghost; } catch (_) {}
  try { rt.ghostNoteMats = ghostNoteMats; } catch (_) {}
  try { rt.ghostEdgeGeo = ghostEdgeGeo; } catch (_) {}
  try { rt.ghostEdgeMat = ghostEdgeMat; } catch (_) {}
  try { rt.ghostArrowMat = ghostArrowMat; } catch (_) {}
  try { rt.ghostDotMat = ghostDotMat; } catch (_) {}
  try { rt.ghostBombMat = ghostBombMat; } catch (_) {}
  try { rt.wallGhost = wallGhost; } catch (_) {}
  try { rt.wallDimArrows = wallDimArrows; rt._dimAxes = _dimAxes; } catch (_) {}
  try { rt.wallDrag = wallDrag; } catch (_) {}
  try { rt.wallHoverCell = wallHoverCell; } catch (_) {}
  try { rt.wallDurLive = wallDurLive; } catch (_) {}
  try { rt.selrect = selrect; } catch (_) {}
  try { rt.box = box; } catch (_) {}
  try { rt.mainEl = mainEl; } catch (_) {}
  try { rt.lastRotTime = lastRotTime; } catch (_) {}
  try { rt.lastRotTarget = lastRotTarget; } catch (_) {}
  try { rt.gizmo = gizmo; } catch (_) {}
  try { rt.gizmoHandles = gizmoHandles; } catch (_) {}
  try { rt.chainGizmoHandles = chainGizmoHandles; } catch (_) {}
  try { rt.selArcs = selArcs; } catch (_) {}
  try { rt.selChains = selChains; } catch (_) {}
  try { rt.chainOverlay = chainOverlay; } catch (_) {}
  try { rt.gizmoCenter = gizmoCenter; } catch (_) {}
  try { rt.gizmoHalf = gizmoHalf; } catch (_) {}
  try { rt.gizmoValid = gizmoValid; } catch (_) {}
  try { rt.handleDrag = handleDrag; } catch (_) {}
  try { rt.gizmoMode = gizmoMode; } catch (_) {}
  try { rt.pieEl = pieEl; } catch (_) {}
  try { rt.pieOpen = pieOpen; } catch (_) {}
  try { rt.pieItems = pieItems; } catch (_) {}
  try { rt.pieDefs = pieDefs; } catch (_) {}
  try { rt.pieHot = pieHot; } catch (_) {}
  try { rt.pieKey = pieKey; } catch (_) {}
  try { rt.pieOnCommit = pieOnCommit; } catch (_) {}
  try { rt.lastMouse = lastMouse; } catch (_) {}
  try { rt.pieCX = pieCX; } catch (_) {}
  try { rt.pieCY = pieCY; } catch (_) {}
  try { rt.snapPieDefs = snapPieDefs; } catch (_) {}
  try { rt.clip3D = clip3D; } catch (_) {}
  try { rt.pasteFollow = pasteFollow; } catch (_) {}
  try { rt._inspCoverKey = _inspCoverKey; } catch (_) {}
  try { rt._chartInfoKey = _chartInfoKey; } catch (_) {}
  try { rt.INFO_NODE_DEFS = INFO_NODE_DEFS; } catch (_) {}
  try { rt.INFO_SRCS = INFO_SRCS; } catch (_) {}
  try { rt._coverHandles = _coverHandles; } catch (_) {}
  try { rt._coverB64 = _coverB64; } catch (_) {}
  try { rt._infoSnapT = _infoSnapT; } catch (_) {}
  try { rt._infoSnapSup = _infoSnapSup; } catch (_) {}
  try { rt._outHandles = _outHandles; } catch (_) {}
  try { rt._infoClip = _infoClip; } catch (_) {}
  try { rt.infoGraph = infoGraph; } catch (_) {}
  try { rt.infoWorldEl = infoWorldEl; } catch (_) {}
  try { rt.infoSvg = infoSvg; } catch (_) {}
  try { rt.infoPortSvg = infoPortSvg; } catch (_) {}
  try { rt.inspEl = inspEl; } catch (_) {}
  try { rt._inDrag = _inDrag; } catch (_) {}
  try { rt._inPan = _inPan; } catch (_) {}
  try { rt._inWire = _inWire; } catch (_) {}
  try { rt._inZTop = _inZTop; } catch (_) {}
  try { rt._inSel = _inSel; } catch (_) {}
  try { rt._inBand = _inBand; } catch (_) {}
  try { rt._bandEl = _bandEl; } catch (_) {}
  try { rt.KEYSHTML_NLE = KEYSHTML_NLE; } catch (_) {}
  try { rt.KEYSHTML_NODE = KEYSHTML_NODE; } catch (_) {}
  try { rt.pv4On = pv4On; } catch (_) {}
  try { rt._PV4 = _PV4; } catch (_) {}
  try { rt._pv4Hist = _pv4Hist; } catch (_) {}
  try { rt.pv4EnvOverride = pv4EnvOverride; } catch (_) {}
  try { rt.PV_ENVS = PV_ENVS; } catch (_) {}
  try { rt._tickErrAt = _tickErrAt; } catch (_) {}
  try { rt._idbP = _idbP; } catch (_) {}
  try { rt.TB_ICONS = TB_ICONS; } catch (_) {}
  try { rt.DIR_LIST = DIR_LIST; } catch (_) {}
  try { rt.DIR_ICON_NAME = DIR_ICON_NAME; } catch (_) {}
  try { rt.ICON_V = ICON_V; } catch (_) {}
  try { rt._lastPlaying = _lastPlaying; } catch (_) {}
  try { rt._dfMenuFor = _dfMenuFor; } catch (_) {}
  try { rt.volCfg = volCfg; } catch (_) {}
  try { rt.uiScale = uiScale; } catch (_) {}
  try { rt.camRotSpeed = camRotSpeed; } catch (_) {}
  try { rt.camZoomSpeed = camZoomSpeed; } catch (_) {}
  try { rt.camPanSpeed = camPanSpeed; } catch (_) {}
  try { rt.pvCfg = pvCfg; } catch (_) {}
  try { rt.PV_BASE = PV_BASE; } catch (_) {}
  try { rt.langSel = langSel; } catch (_) {}
  try { rt.vmEl = vmEl; } catch (_) {}
  try { rt.vmg = vmg; } catch (_) {}
  try { rt.vmW = vmW; } catch (_) {}
  try { rt.vmH = vmH; } catch (_) {}
  try { rt.vmHold = vmHold; } catch (_) {}
  try { rt._bootReady = _bootReady; } catch (_) {}
  try { rt.perfFrames = perfFrames; } catch (_) {}
  try { rt.perfLast = perfLast; } catch (_) {}
  try { rt.laserBoostCols = laserBoostCols; } catch (_) {}
  try { rt.setNoteColStr = setNoteColStr; } catch (_) {}
  try { rt.rotStep = rotStep; } catch (_) {}
  try { rt.applyDpr = applyDpr; } catch (_) {}
  try { rt.tagHelper = tagHelper; } catch (_) {}
  try { rt.showErr = showErr; } catch (_) {}
  try { rt.showOk = showOk; } catch (_) {}
  try { rt.t = t; } catch (_) {}
  try { rt.tf = tf; } catch (_) {}
  try { rt.loadLang = loadLang; } catch (_) {}
  try { rt.setModeLabel = setModeLabel; } catch (_) {}
  try { rt.setPvMode = setPvMode; } catch (_) {}
  try { rt.setNodeMode = setNodeMode; } catch (_) {}
  try { rt.setNodeColMode = setNodeColMode; } catch (_) {}
  try { rt.renderModeKeys = renderModeKeys; } catch (_) {}
  try { rt.updateMainModeLabel = updateMainModeLabel; } catch (_) {}
  try { rt.renderMetaList = renderMetaList; } catch (_) {}
  try { rt.rotAround = rotAround; } catch (_) {}
  try { rt.numTex = numTex; } catch (_) {}
  try { rt.markNameTex = markNameTex; } catch (_) {}
  try { rt.tmNameTex = tmNameTex; } catch (_) {}
  try { rt.laneTex = laneTex; } catch (_) {}
  try { rt.chipKindOf = chipKindOf; } catch (_) {}
  try { rt.chipColorOf = chipColorOf; } catch (_) {}
  try { rt.chipNumOf = chipNumOf; } catch (_) {}
  try { rt.chipFootGeo = chipFootGeo; } catch (_) {}
  try { rt.chipRect = chipRect; } catch (_) {}
  try { rt.chipEdges = chipEdges; } catch (_) {}
  try { rt.numSprTex = numSprTex; } catch (_) {}
  try { rt.ensureChips = ensureChips; } catch (_) {}
  try { rt.laneKind = laneKind; } catch (_) {}
  try { rt.lightValue = lightValue; } catch (_) {}
  try { rt.lightDesc = lightDesc; } catch (_) {}
  try { rt.setLightMode = setLightMode; } catch (_) {}
  try { rt.refreshLightHover = refreshLightHover; } catch (_) {}
  try { rt.placeLight = placeLight; } catch (_) {}
  try { rt.hoverLightEvent = hoverLightEvent; } catch (_) {}
  try { rt.applyLightMove = applyLightMove; } catch (_) {}
  try { rt.cancelLightMove = cancelLightMove; } catch (_) {}
  try { rt.setLightBehavSmart = setLightBehavSmart; } catch (_) {}
  try { rt.flipLightColors = flipLightColors; } catch (_) {}
  try { rt.deleteLightAt = deleteLightAt; } catch (_) {}
  try { rt.applyModeDim = applyModeDim; } catch (_) {}
  try { rt.setPvShowNotes = setPvShowNotes; } catch (_) {}
  try { rt.setPvShowLights = setPvShowLights; } catch (_) {}
  try { rt.setPvShowStruct = setPvShowStruct; } catch (_) {}
  try { rt.setPvShowAmbient = setPvShowAmbient; } catch (_) {}
  try { rt.buildWaveData = buildWaveData; } catch (_) {}
  try { rt.ovResize = ovResize; } catch (_) {}
  try { rt.phRect = phRect; } catch (_) {}
  try { rt.crispVLine = crispVLine; } catch (_) {}
  try { rt.tlEnd = tlEnd; } catch (_) {}
  try { rt.tlWindow = tlWindow; } catch (_) {}
  try { rt.tlZoom = tlZoom; } catch (_) {}
  try { rt.drawOverview = drawOverview; } catch (_) {}
  try { rt.addMarkerAt = addMarkerAt; } catch (_) {}
  try { rt.markerMenuTop = markerMenuTop; } catch (_) {}
  try { rt.msegs = msegs; } catch (_) {}
  try { rt.cutMusicAt = cutMusicAt; } catch (_) {}
  try { rt.mergeMusicSel = mergeMusicSel; } catch (_) {}
  try { rt.musicHit = musicHit; } catch (_) {}
  try { rt.deleteMusic = deleteMusic; } catch (_) {}
  try { rt.createFullSongClip = createFullSongClip; } catch (_) {}
  try { rt.secAtPr = secAtPr; } catch (_) {}
  try { rt.addMarker = addMarker; } catch (_) {}
  try { rt.ndResize = ndResize; } catch (_) {}
  try { rt.ndToScreen = ndToScreen; } catch (_) {}
  try { rt.ndFromScreen = ndFromScreen; } catch (_) {}
  try { rt.ensureNodeIds = ensureNodeIds; } catch (_) {}
  try { rt.ensureLens = ensureLens; } catch (_) {}
  try { rt.ensureEdges = ensureEdges; } catch (_) {}
  try { rt.sigPath = sigPath; } catch (_) {}
  try { rt.sigConnected = sigConnected; } catch (_) {}
  try { rt.syncGraphFromFlat = syncGraphFromFlat; } catch (_) {}
  try { rt.compileGraphToFlat = compileGraphToFlat; } catch (_) {}
  try { rt.graphOp = graphOp; } catch (_) {}
  try { rt.createExtra = createExtra; } catch (_) {}
  try { rt.infoChain = infoChain; } catch (_) {}
  try { rt.applyInfoChain = applyInfoChain; } catch (_) {}
  try { rt.inNullRange = inNullRange; } catch (_) {}
  try { rt.timelineSections = timelineSections; } catch (_) {}
  try { rt.nodeRowsFor = nodeRowsFor; } catch (_) {}
  try { rt.nodeExtraH = nodeExtraH; } catch (_) {}
  try { rt.nodeGeomOf = nodeGeomOf; } catch (_) {}
  try { rt.portPosW = portPosW; } catch (_) {}
  try { rt.getSongOff = getSongOff; } catch (_) {}
  try { rt.allNodeIds = allNodeIds; } catch (_) {}
  try { rt.hsv2rgb = hsv2rgb; } catch (_) {}
  try { rt.rgb2hsv = rgb2hsv; } catch (_) {}
  try { rt.ndColorEdit = ndColorEdit; } catch (_) {}
  try { rt.activateLine = activateLine; } catch (_) {}
  try { rt.newDefaultGraph = newDefaultGraph; } catch (_) {}
  try { rt.defaultFresh = defaultFresh; } catch (_) {}
  try { rt.altAt = altAt; } catch (_) {}
  try { rt.copySelNode = copySelNode; } catch (_) {}
  try { rt.pasteNode = pasteNode; } catch (_) {}
  try { rt.deleteSelNode = deleteSelNode; } catch (_) {}
  try { rt.deleteMultiSel = deleteMultiSel; } catch (_) {}
  try { rt.loadCoverPreview = loadCoverPreview; } catch (_) {}
  try { rt.pickOutFolder = pickOutFolder; } catch (_) {}
  try { rt.ndInlineEdit = ndInlineEdit; } catch (_) {}
  try { rt.setBPMv = setBPMv; } catch (_) {}
  try { rt.estimateBPM = estimateBPM; } catch (_) {}
  try { rt.runBpmEstimate = runBpmEstimate; } catch (_) {}
  try { rt.portPosOf = portPosOf; } catch (_) {}
  try { rt.resizeAt = resizeAt; } catch (_) {}
  try { rt.portHit = portHit; } catch (_) {}
  try { rt.edgeHit = edgeHit; } catch (_) {}
  try { rt.ensureGraphIO = ensureGraphIO; } catch (_) {}
  try { rt.buildDefaultGraph = buildDefaultGraph; } catch (_) {}
  try { rt.openSongFile = openSongFile; } catch (_) {}
  try { rt.updateCoverThumb = updateCoverThumb; } catch (_) {}
  try { rt.openCoverFile = openCoverFile; } catch (_) {}
  try { rt.editExtraNode = editExtraNode; } catch (_) {}
  try { rt.rippleSection = rippleSection; } catch (_) {}
  try { rt.removeNodeMerge = removeNodeMerge; } catch (_) {}
  try { rt.nodeAt = nodeAt; } catch (_) {}
  try { rt.ioAt = ioAt; } catch (_) {}
  try { rt.songAt = songAt; } catch (_) {}
  try { rt.extraAt = extraAt; } catch (_) {}
  try { rt.laneDefN = laneDefN; } catch (_) {}
  try { rt.laneCount = laneCount; } catch (_) {}
  try { rt.secLk = secLk; } catch (_) {}
  try { rt.laneCountOf = laneCountOf; } catch (_) {}
  try { rt.rowOf = rowOf; } catch (_) {}
  try { rt.laneShiftAll = laneShiftAll; } catch (_) {}
  try { rt.laneHt = laneHt; } catch (_) {}
  try { rt.laneVP = laneVP; } catch (_) {}
  try { rt.laneTopOf = laneTopOf; } catch (_) {}
  try { rt.scrOf = scrOf; } catch (_) {}
  try { rt.setScr = setScr; } catch (_) {}
  try { rt.laneMaxScroll = laneMaxScroll; } catch (_) {}
  try { rt.laneAdd = laneAdd; } catch (_) {}
  try { rt.laneRemove = laneRemove; } catch (_) {}
  try { rt.setLaneRatio = setLaneRatio; } catch (_) {}
  try { rt.laneY = laneY; } catch (_) {}
  try { rt.laneAtY = laneAtY; } catch (_) {}
  try { rt.laneLabel = laneLabel; } catch (_) {}
  try { rt.hueOf = hueOf; } catch (_) {}
  try { rt.stripColOf = stripColOf; } catch (_) {}
  try { rt.pickStripCol = pickStripCol; } catch (_) {}
  try { rt.hexA = hexA; } catch (_) {}
  try { rt.lPPB = lPPB; } catch (_) {}
  try { rt.lBeatToX = lBeatToX; } catch (_) {}
  try { rt.lXToBeat = lXToBeat; } catch (_) {}
  try { rt.layerFit = layerFit; } catch (_) {}
  try { rt.drawNoteIco = drawNoteIco; } catch (_) {}
  try { rt.drawLightIco = drawLightIco; } catch (_) {}
  try { rt.roundRectND = roundRectND; } catch (_) {}
  try { rt.drawLayers = drawLayers; } catch (_) {}
  try { rt.laneOverlaps = laneOverlaps; } catch (_) {}
  try { rt.packLanes = packLanes; } catch (_) {}
  try { rt.clipAtLayer = clipAtLayer; } catch (_) {}
  try { rt.clipEdgeAt = clipEdgeAt; } catch (_) {}
  try { rt.compileLayersToFlat = compileLayersToFlat; } catch (_) {}
  try { rt.syncFlatToSections = syncFlatToSections; } catch (_) {}
  try { rt.flushFlatEdits = flushFlatEdits; } catch (_) {}
  try { rt.clipRef = clipRef; } catch (_) {}
  try { rt.splitSectionAt = splitSectionAt; } catch (_) {}
  try { rt.cutClipAtMarkers = cutClipAtMarkers; } catch (_) {}
  try { rt.mergeLayerSel = mergeLayerSel; } catch (_) {}
  try { rt.deleteLayerSel = deleteLayerSel; } catch (_) {}
  try { rt.shiftMusicSelBeat = shiftMusicSelBeat; } catch (_) {}
  try { rt.shiftSelLayersBeat = shiftSelLayersBeat; } catch (_) {}
  try { rt.toggleLaneState = toggleLaneState; } catch (_) {}
  try { rt.layerPasteFit = layerPasteFit; } catch (_) {}
  try { rt.startLayerPaste = startLayerPaste; } catch (_) {}
  try { rt.updateLayerPaste = updateLayerPaste; } catch (_) {}
  try { rt.commitLayerPaste = commitLayerPaste; } catch (_) {}
  try { rt.cancelLayerPaste = cancelLayerPaste; } catch (_) {}
  try { rt.syncLaneSb = syncLaneSb; } catch (_) {}
  try { rt.setNdView = setNdView; } catch (_) {}
  try { rt.sectionRange = sectionRange; } catch (_) {}
  try { rt.headBeat = headBeat; } catch (_) {}
  try { rt.inRegion = inRegion; } catch (_) {}
  try { rt.regionObjs = regionObjs; } catch (_) {}
  try { rt.extractRegion = extractRegion; } catch (_) {}
  try { rt.pasteFragment = pasteFragment; } catch (_) {}
  try { rt.mirrorRegion = mirrorRegion; } catch (_) {}
  try { rt.deleteRegionContents = deleteRegionContents; } catch (_) {}
  try { rt.showMenu = showMenu; } catch (_) {}
  try { rt.hideMenu = hideMenu; } catch (_) {}
  try { rt.closeFloatUI = closeFloatUI; } catch (_) {}
  try { rt.exportReadiness = exportReadiness; } catch (_) {}
  try { rt.prResize = prResize; } catch (_) {}
  try { rt.drawPRoll = drawPRoll; } catch (_) {}
  try { rt.prSeekTo = prSeekTo; } catch (_) {}
  try { rt.makeTex = makeTex; } catch (_) {}
  try { rt.makeSpikyBomb = makeSpikyBomb; } catch (_) {}
  try { rt.sanitizeFolderName = sanitizeFolderName; } catch (_) {}
  try { rt.makeChainHeadGeo = makeChainHeadGeometry; } catch (_) {}
  try { rt.makeChainLinkGeo = makeChainLinkGeometry; } catch (_) {}
  try { rt.ensureSelPool = ensureSelPool; } catch (_) {}
  try { rt.ensureDupPool = ensureDupPool; } catch (_) {}
  try { rt.mat = mat; } catch (_) {}
  try { rt.scanDups = scanDups; } catch (_) {}
  try { rt.dupJumpItem = dupJumpItem; } catch (_) {}
  try { rt.cellPos = cellPos; } catch (_) {}
  try { rt.buildNote = buildNote; } catch (_) {}
  try { rt.buildBomb = buildBomb; } catch (_) {}
  try { rt.wallDims = wallDims; } catch (_) {}
  try { rt.buildWall = buildWall; } catch (_) {}
  try { rt.buildArc = buildArc; } catch (_) {}
  try { rt.buildChain = buildChain; } catch (_) {}
  try { rt.addObj = addObj; } catch (_) {}
  try { rt.removeObjMesh = removeObjMesh; } catch (_) {}
  try { rt.refreshMesh = refreshMesh; } catch (_) {}
  try { rt.updateChainOverlay = updateChainOverlay; } catch (_) {}
  try { rt.syncPos = syncPos; } catch (_) {}
  try { rt.arrOf = arrOf; } catch (_) {}
  try { rt.removeObj = removeObj; } catch (_) {}
  try { rt.rebuild = rebuild; } catch (_) {}
  try { rt.viewBeat = viewBeat; } catch (_) {}
  try { rt.seekEase = seekEase; } catch (_) {}
  try { rt.pushHist = pushHist; } catch (_) {}
  try { rt.dumpDomain = dumpDomain; } catch (_) {}
  try { rt.restoreDomain = restoreDomain; } catch (_) {}
  try { rt.snapshot = snapshot; } catch (_) {}
  try { rt.undo = undo; } catch (_) {}
  try { rt.redo = redo; } catch (_) {}
  try { rt.resetHistory = resetHistory; } catch (_) {}
  try { rt.selKey = selKey; } catch (_) {}
  try { rt.selWatch = selWatch; } catch (_) {}
  try { rt.refreshPal = refreshPal; } catch (_) {}
  try { rt.recolorLinkedSliders = recolorLinkedSliders; } catch (_) {}
  try { rt.setColor = setColor; } catch (_) {}
  try { rt.setLightBehav = setLightBehav; } catch (_) {}
  try { rt.setLightColor = setLightColor; } catch (_) {}
  try { rt.updateLightUI = updateLightUI; } catch (_) {}
  try { rt.setBrushType = setBrushType; } catch (_) {}
  try { rt.setSnap = setSnap; } catch (_) {}
  try { rt.aTime = aTime; } catch (_) {}
  try { rt.play = play; } catch (_) {}
  try { rt.stopS = stopS; } catch (_) {}
  try { rt.pause = pause; } catch (_) {}
  try { rt.applyShowKeys = applyShowKeys; } catch (_) {}
  try { rt.blip = blip; } catch (_) {}
  try { rt.metroNode = metroNode; } catch (_) {}
  try { rt.metroTick = metroTick; } catch (_) {}
  try { rt.stashCurrentDiff = stashCurrentDiff; } catch (_) {}
  try { rt.relinkDiffEdges = relinkDiffEdges; } catch (_) {}
  try { rt.resetDiffSections = resetDiffSections; } catch (_) {}
  try { rt.ensureDiffSelect = ensureDiffSelect; } catch (_) {}
  try { rt.initScratchDiff = initScratchDiff; } catch (_) {}
  try { rt.fillDiffSelectFromInfo = fillDiffSelectFromInfo; } catch (_) {}
  try { rt.loadLineDiff = loadLineDiff; } catch (_) {}
  try { rt.getSongFile = getSongFile; } catch (_) {}
  try { rt._sniffMime = _sniffMime; } catch (_) {}
  try { rt._rd32be = _rd32be; } catch (_) {}
  try { rt._parseFlacPic = _parseFlacPic; } catch (_) {}
  try { rt._id3Pic = _id3Pic; } catch (_) {}
  try { rt._flacPic = _flacPic; } catch (_) {}
  try { rt._oggPic = _oggPic; } catch (_) {}
  try { rt._mp4FindAtom = _mp4FindAtom; } catch (_) {}
  try { rt._mp4Pic = _mp4Pic; } catch (_) {}
  try { rt.extractArtwork = extractArtwork; } catch (_) {}
  try { rt.applyArtwork = applyArtwork; } catch (_) {}
  try { rt.extractArtworkBatch = extractArtworkBatch; } catch (_) {}
  try { rt.scanLibrary = scanLibrary; } catch (_) {}
  try { rt.scanAssetLibrary = scanAssetLibrary; } catch (_) {}
  try { rt.saveClipToAsset = saveClipToAsset; } catch (_) {}
  try { rt.renameAssetClip = renameAssetClip; } catch (_) {}
  try { rt.deleteAssetClip = deleteAssetClip; } catch (_) {}
  try { rt.saveLibDirs = saveLibDirs; } catch (_) {}
  try { rt.applyLibFilter = applyLibFilter; } catch (_) {}
  try { rt.updateLibCatSel = updateLibCatSel; } catch (_) {}
  try { rt.libMarkColors = libMarkColors; } catch (_) {}
  try { rt.renderLibMark = renderLibMark; } catch (_) {}
  try { rt.addLibItem = addLibItem; } catch (_) {}
  try { rt.libLabels = libLabels; } catch (_) {}
  try { rt.libDisp = libDisp; } catch (_) {}
  try { rt.setLibLabel = setLibLabel; } catch (_) {}
  try { rt.renderLibList = renderLibList; } catch (_) {}
  try { rt.loadSongFromItem = loadSongFromItem; } catch (_) {}
  try { rt.dropInfoNodesFromItem = dropInfoNodesFromItem; } catch (_) {}
  try { rt.prepareMediaWave = prepareMediaWave; } catch (_) {}
  try { rt.prepareMediaFrag = prepareMediaFrag; } catch (_) {}
  try { rt.parseDiffFragment = parseDiffFragment; } catch (_) {}
  try { rt.fragFromContent = fragFromContent; } catch (_) {}
  try { rt.placeClipLine = placeClipLine; } catch (_) {}
  try { rt.addSongLine = addSongLine; } catch (_) {}
  try { rt.bulkLoadSongData = bulkLoadSongData; } catch (_) {}
  try { rt.firstFreeTrackIn = firstFreeTrackIn; } catch (_) {}
  try { rt.afterFolder = afterFolder; } catch (_) {}
  try { rt.resetAllState = resetAllState; } catch (_) {}
  try { rt.applyProject = applyProject; } catch (_) {}
  try { rt.tryAutoLoadSongNative = tryAutoLoadSongNative; } catch (_) {}
  try { rt.restoreLineAssets = restoreLineAssets; } catch (_) {}
  try { rt.applyOpenedProject = applyOpenedProject; } catch (_) {}
  try { rt.openProjectFile = openProjectFile; } catch (_) {}
  try { rt.loadDiff = loadDiff; } catch (_) {}
  try { rt.stat = stat; } catch (_) {}
  try { rt.buildDiffJsonFor = buildDiffJsonFor; } catch (_) {}
  try { rt._rawX = _rawX; } catch (_) {}
  try { rt.encArr = encArr; } catch (_) {}
  try { rt.decArr = decArr; } catch (_) {}
  try { rt.encSec = encSec; } catch (_) {}
  try { rt.decSec = decSec; } catch (_) {}
  try { rt._slimBase = _slimBase; } catch (_) {}
  try { rt.encDiff = encDiff; } catch (_) {}
  try { rt.decDiff = decDiff; } catch (_) {}
  try { rt.buildProjectText = buildProjectText; } catch (_) {}
  try { rt.rotateBakIdb = rotateBakIdb; } catch (_) {}
  try { rt.rotateBakDisk = rotateBakDisk; } catch (_) {}
  try { rt.saveProject = saveProject; } catch (_) {}
  try { rt.srcInfo = srcInfo; } catch (_) {}
  try { rt.srcNjsOf = srcNjsOf; } catch (_) {}
  try { rt.njsOffExport = njsOffExport; } catch (_) {}
  try { rt.njsOffCur = njsOffCur; } catch (_) {}
  try { rt.setNjsCur = setNjsCur; } catch (_) {}
  try { rt.exportMap = exportMap; } catch (_) {}
  try { rt.setPtr = setPtr; } catch (_) {}
  try { rt.objUnder = objUnder; } catch (_) {}
  try { rt.refreshGhost = refreshGhost; } catch (_) {}
  try { rt.floorColBeat = floorColBeat; } catch (_) {}
  try { rt.wallSpan = wallSpan; } catch (_) {}
  try { rt.updateWallGhost = updateWallGhost; } catch (_) {}
  try { rt.selWalls = selWalls; } catch (_) {}
  try { rt.setPlaceMode = setPlaceMode; } catch (_) {}
  try { rt.setCamMode = setCamMode; } catch (_) {}
  try { rt.toggleCamMode = toggleCamMode; } catch (_) {}
  try { rt.getCamMode = ()=>camMode; } catch (_) {}
  try { rt.getPlaceMode = ()=>placeMode; rt.getSel = ()=>[...selection]; rt.getWallStage = ()=>wallStage&&wallStage.stage; } catch (_) {}
  try { rt._getVwB = ()=>vwB; rt.getCur = ()=>cur; rt.getHandleDrag = ()=>handleDrag; } catch (_) {}
  try { rt.flyPlaceCam = flyPlaceCam; } catch (_) {}
  try { rt.refreshHoverVisuals = refreshHoverVisuals; } catch (_) {}
  try { rt.mainPos = mainPos; } catch (_) {}
  try { rt.screenPosOf = screenPosOf; } catch (_) {}
  try { rt.createClipAt = createClipAt; } catch (_) {}
  try { rt.createNoteClipAt = createNoteClipAt; } catch (_) {}
  try { rt.clipTrackForBeat = clipTrackForBeat; } catch (_) {}
  try { rt.noteTrackForBeat = noteTrackForBeat; } catch (_) {}
  try { rt.placeAt = placeAt; } catch (_) {}
  try { rt.tlScrub = tlScrub; } catch (_) {}
  try { rt.updateGizmo = updateGizmo; } catch (_) {}
  try { rt.handleUsable = handleUsable; } catch (_) {}
  try { rt.axisParam = axisParam; } catch (_) {}
  try { rt.clipRangeAt = clipRangeAt; } catch (_) {}
  try { rt.startHandleDrag = startHandleDrag; } catch (_) {}
  try { rt.applyHandleDrag = applyHandleDrag; } catch (_) {}
  try { rt.endHandleDrag = endHandleDrag; } catch (_) {}
  try { rt.toggleSizeMode = toggleSizeMode; } catch (_) {}
  try { rt.movables = movables; } catch (_) {}
  try { rt.openPie = openPie; } catch (_) {}
  try { rt.closePie = closePie; } catch (_) {}
  try { rt.openPlaceModePie = openPlaceModePie; } catch (_) {}
  try { rt.commitPlaceModePie = commitPlaceModePie; } catch (_) {}
  try { rt.placeModePieDefs = placeModePieDefs; } catch (_) {}
  try { rt.setFollowGhost = setFollowGhost; } catch (_) {}
  try { rt.copySel3D = copySel3D; } catch (_) {}
  try { rt.pasteSel3D = pasteSel3D; } catch (_) {}
  try { rt.cutSel3D = cutSel3D; } catch (_) {}
  try { rt.pickArcPart = pickArcPart; } catch (_) {}
  try { rt.pickCurveEndpoint = pickCurveEndpoint; } catch (_) {}
  try { rt.tweakSelArcs = tweakSelArcs; } catch (_) {}
  try { rt.movables = movables; } catch (_) {}
  try { rt.handleUsable = handleUsable; } catch (_) {}
  try { rt.pasteTrackFor = pasteTrackFor; } catch (_) {}
  try { rt.createArcData = createArcData; } catch (_) {}
  try { rt.spawnArcsFromSelection = spawnArcsFromSelection; } catch (_) {}
  try { rt.tryCreateChainData = tryCreateChainData; } catch (_) {}
  try { rt.spawnChainFromSelection = spawnChainFromSelection; } catch (_) {}
  try { rt.createArc = createArc; } catch (_) {}
  try { rt.createChain = createChain; } catch (_) {}
  try { rt.timelineEndBeat = timelineEndBeat; } catch (_) {}
  try { rt.resize = resize; } catch (_) {}
  try { rt.refreshInspector = refreshInspector; } catch (_) {}
  try { rt.refreshChartInfo = refreshChartInfo; } catch (_) {}
  try { rt.defInfoData = defInfoData; } catch (_) {}
  try { rt.defaultInfoGraph = defaultInfoGraph; } catch (_) {}
  try { rt.sanitizeInfoGraph = sanitizeInfoGraph; } catch (_) {}
  try { rt.blobToDataURL = blobToDataURL; } catch (_) {}
  try { rt.dataURLToBlob = dataURLToBlob; } catch (_) {}
  try { rt.refreshCoverB64 = refreshCoverB64; } catch (_) {}
  try { rt.restoreCoversFromB64 = restoreCoversFromB64; } catch (_) {}
  try { rt.infoSnapshot = infoSnapshot; } catch (_) {}
  try { rt.infoSnapBurst = infoSnapBurst; } catch (_) {}
  try { rt.infoNodeT = infoNodeT; } catch (_) {}
  try { rt.connectedNodeId = connectedNodeId; } catch (_) {}
  try { rt.applyInfoGraph = applyInfoGraph; } catch (_) {}
  try { rt.setActiveOut = setActiveOut; } catch (_) {}
  try { rt.addOutNode = addOutNode; } catch (_) {}
  try { rt.deleteOutNode = deleteOutNode; } catch (_) {}
  try { rt.readinessHTML = readinessHTML; } catch (_) {}
  try { rt.renderOutCards = renderOutCards; } catch (_) {}
  try { rt.refreshOutCards = refreshOutCards; } catch (_) {}
  try { rt.srcCardHTML = srcCardHTML; } catch (_) {}
  try { rt.renderInfoCards = renderInfoCards; } catch (_) {}
  try { rt.refreshInfoCards = refreshInfoCards; } catch (_) {}
  try { rt.infoCamApply = infoCamApply; } catch (_) {}
  try { rt.infoCenterView = infoCenterView; } catch (_) {}
  try { rt.infoAutoCenter = infoAutoCenter; } catch (_) {}
  try { rt.infoNodeEls = infoNodeEls; } catch (_) {}
  try { rt.layoutInfoNodes = layoutInfoNodes; } catch (_) {}
  try { rt.infoPortOf = infoPortOf; } catch (_) {}
  try { rt.infoOutPortOf = infoOutPortOf; } catch (_) {}
  try { rt.drawInfoEdges = drawInfoEdges; } catch (_) {}
  try { rt.infoWorldXY = infoWorldXY; } catch (_) {}
  try { rt.infoSelApply = infoSelApply; } catch (_) {}
  try { rt.drawBand = drawBand; } catch (_) {}
  try { rt.addSrcNode = addSrcNode; } catch (_) {}
  try { rt.deleteSrcNode = deleteSrcNode; } catch (_) {}
  try { rt.noteSwSvg = noteSwSvg; } catch (_) {}
  try { rt.laserSwSvg = laserSwSvg; } catch (_) {}
  try { rt.fmt = fmt; } catch (_) {}
  try { rt.setPv4Mode = setPv4Mode; } catch (_) {}
  try { rt.pv4EnvOf = pv4EnvOf; } catch (_) {}
  try { rt.pv4SyncEnv = pv4SyncEnv; } catch (_) {}
  try { rt.pvFillEnvSel = pvFillEnvSel; } catch (_) {}
  try { rt.pv4NjsOf = pv4NjsOf; } catch (_) {}
  try { rt.pv4Push = pv4Push; } catch (_) {}
  try { rt.pvFinderVis = pvFinderVis; } catch (_) {}
  try { rt.pv4Frame = pv4Frame; } catch (_) {}
  try { rt.tick = tick; } catch (_) {}
  try { rt._tick = _tick; } catch (_) {}
  try { rt.idbDB = idbDB; } catch (_) {}
  try { rt.idbGet = idbGet; } catch (_) {}
  try { rt.idbSet = idbSet; } catch (_) {}
  try { rt.newProject = newProject; } catch (_) {}
  try { rt.saveProjectCopy = saveProjectCopy; } catch (_) {}
  try { rt.closeFileMenu = closeFileMenu; } catch (_) {}
  try { rt.buildDirPanel = buildDirPanel; } catch (_) {}
  try { rt.updateDirBtn = updateDirBtn; } catch (_) {}
  try { rt.updateColorBtn = updateColorBtn; } catch (_) {}
  try { rt.updateModeButtons = updateModeButtons; } catch (_) {}
  try { rt.tbIcon = tbIcon; } catch (_) {}
  try { rt.jumpMarker = jumpMarker; } catch (_) {}
  try { rt.buildToolbar = buildToolbar; } catch (_) {}
  try { rt.syncPlayIcons = syncPlayIcons; } catch (_) {}
  try { rt.togglePanel = togglePanel; } catch (_) {}
  try { rt.diffColOf = diffColOf; } catch (_) {}
  try { rt.dispDiff = dispDiff; } catch (_) {}
  try { rt.diffOptOf = diffOptOf; } catch (_) {}
  try { rt.diffIsCurrent = diffIsCurrent; } catch (_) {}
  try { rt.diffCountsOf = diffCountsOf; } catch (_) {}
  try { rt.renderDiffBar = renderDiffBar; } catch (_) {}
  try { rt.openDiffMenu = openDiffMenu; } catch (_) {}
  try { rt.quickSetNode = quickSetNode; } catch (_) {}
  try { rt.syncSetQuick = syncSetQuick; } catch (_) {}
  try { rt.diffStoreOf = diffStoreOf; } catch (_) {}
  try { rt._diffApplyLive = _diffApplyLive; } catch (_) {}
  try { rt.diffCopy = diffCopy; } catch (_) {}
  try { rt.diffClear = diffClear; } catch (_) {}
  try { rt.switchDiffByIndex = switchDiffByIndex; } catch (_) {}
  try { rt.updateDiffLabel = updateDiffLabel; } catch (_) {}
  try { rt.paneOf = paneOf; } catch (_) {}
  try { rt.applyVolumes = applyVolumes; } catch (_) {}
  try { rt.wireVol = wireVol; } catch (_) {}
  try { rt.applyUiScale = applyUiScale; } catch (_) {}
  try { rt.saveCamSpd = saveCamSpd; } catch (_) {}
  try { rt.wireSpd = wireSpd; } catch (_) {}
  try { rt.applyPvSettings = applyPvSettings; } catch (_) {}
  try { rt.wirePv = wirePv; } catch (_) {}
  try { rt.wireStepper = wireStepper; } catch (_) {}
  try { rt.setPreview = setPreview; } catch (_) {}
  try { rt.refreshMusicHdr = refreshMusicHdr; } catch (_) {}
  try { rt.vmResize = vmResize; } catch (_) {}
  try { rt.drawMeter = drawMeter; } catch (_) {}
  try { rt.saveSplits = saveSplits; } catch (_) {}
  try { rt._bootReveal = _bootReveal; } catch (_) {}
  try { rt.makeSplit = makeSplit; } catch (_) {}

  installLightingEditor(rt);
  installNotesEditor(rt);
  installNlePanel(rt);
  installMediaPanel(rt);
  installInfoPanel(rt);
  installSaveSystem(rt);
  installExportSystem(rt);
  installHistorySystem(rt);
  installEditorScene(rt);
  installAudioEngine(rt);
  installPv4Bridge(rt);
  installPaneModes(rt);
  installChartSync(rt);
  installGraphLegacy(rt);
  installUiChrome(rt);
  installTickLoop(rt);
  installEditorRuntimeHelpers(rt);

  return rt;
}

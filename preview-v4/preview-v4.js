// ============================================================================
// Preview V2 — ArcViewer完全移植のthree.jsプレビューエンジン
// 正解=ArcViewerソースのみ（v2-port\spec-objects.md / spec-lights.md）。
// 座標系: ArcViewerはUnity左手系(+Z奥)。ここではZのみ反転して右手系化し
//         X/Yの視覚的意味を温存（threeZ = -unityZ）。回転(Z軸)は符号反転。
// エディタからは setData(譜面) と frame(sec,playing) だけ受け取る。
// 進捗: [x]ノーツ [x]ボム [x]壁 [x]チェーン [x]アーク  [ ]ライト [ ]環境
// ============================================================================
import * as THREE from 'three';
import { makeChamferBoxGeometry, NOTE_CORNER_CUT, CHAIN_HEAD_SIZE, CHAIN_LINK_SIZE, makeChainHeadGeometry, makeChainLinkGeometry } from '../js/three/chamfer-box.js';
import { chainLinkLayout } from '../js/notes/chain-bezier.js';
import { EffectComposer } from 'three/addons/postprocessing/EffectComposer.js';
import { RenderPass } from 'three/addons/postprocessing/RenderPass.js';
import { UnrealBloomPass } from 'three/addons/postprocessing/UnrealBloomPass.js';
import { Reflector } from 'three/addons/objects/Reflector.js';
import { mergeGeometries } from 'three/addons/utils/BufferGeometryUtils.js';   // ボムのトゲトゲ合成用
function makeSpikyBomb(R,sl,sr){   // 黒トゲトゲのボム: icosphere＋20本の四角錐トゲを1ジオメトリに合成
  const parts=[new THREE.IcosahedronGeometry(R,1)];
  const dirs=new THREE.DodecahedronGeometry(1,0), pos=dirs.attributes.position, seen=new Set(), up=new THREE.Vector3(0,1,0);
  for(let i=0;i<pos.count;i++){ const v=new THREE.Vector3().fromBufferAttribute(pos,i).normalize();
    const key=v.toArray().map(x=>x.toFixed(2)).join(','); if(seen.has(key)) continue; seen.add(key);
    const cone=new THREE.ConeGeometry(sr,sl,4).toNonIndexed();   // 非index化＝icosphereと揃えて合成可能に
    cone.applyMatrix4(new THREE.Matrix4().compose(v.clone().multiplyScalar(R*0.92+sl*0.5), new THREE.Quaternion().setFromUnitVectors(up,v), new THREE.Vector3(1,1,1)));
    parts.push(cone); }
  return mergeGeometries(parts);
}

// ---- 定数（spec-objects.md §2 / Previewer.unity シリアライズ値）----
const MOVE_Z=300, MOVE_TIME=0.975, ROT_ANIM_TIME=0.3, BEHIND_CAM_TIME=-1, FLOOR_OFFSET=-0.6;
const CHART_STRETCH=1.4;   // 譜面の奥行き間隔を伸ばす（詰まった譜面を見やすく）。位置Zのみ拡大しY放物線は素のzで計算＝軌道は自然
const GRID_X0=-0.9, LANE_W=0.6, ROW_H=0.55, START_Y_SPACING=0.6, WALL_HSCALE=0.6, CUT_PLANE=0; // 非リプレイ
const DIR_ANGLES={0:180,1:0,2:-90,3:90,4:-135,5:135,6:-45,7:45,8:0};
const DEFAULT_NJS={Easy:10,Normal:10,Hard:10,Expert:12,ExpertPlus:16};
const CAM_FOV=80, CAM_Y=1.7, CAM_Z=-2;                    // CameraUpdater: playerheight1.8-0.1, cameraposition-2

// イージング（Easings.cs）
const easeQuadInOut=t=>t<0.5?2*t*t:1-Math.pow(-2*t+2,2)/2;
const easeQuadOut=t=>1-(1-t)*(1-t);
const easeSineOut=t=>Math.sin(t*Math.PI/2);

// ---- three.js基盤 ----
let renderer=null, scene=null, camera=null, host=null, active=false, root=null, composer=null, bloom=null, reflector=null, reflOverlay=null;
let ambLight=null, dirLight=null, _ambientOn=false;   // 環境ライト（構造物を明るく＝動きを見やすく）。既定OFF
const _AMB_OFF=new THREE.Color(0x191a1c), _AMB_ON=new THREE.Color(0x4a4e54);   // structReflMatのuAmbient: 消灯時=暗灰 / 環境ライトON=やや暗めの灰（ヘルバ様指示で控えめに）
// preview設定（環境設定のpreviewタブから調整。デフォルト=現行チューニング値）
let _bloomStr=0.85, _bloomRad=1.0, _bloomThr=0.32, _ambLevel=1.0, _emsScale=1.0, _reflScale=1.0;
export function setAmbient(on){
  _ambientOn=!!on;
  if(ambLight) ambLight.intensity=on?2.0:0.5;
  if(dirLight) dirLight.intensity=on?0.85:0.2;
  if(structReflMat) structReflMat.uniforms.uAmbient.value.copy(on?_AMB_ON:_AMB_OFF).multiplyScalar(on?_ambLevel:1);   // 構造物シェーダの環境項を持ち上げる＝見えやすく（ON時は環境光レベルを乗算）
  _dirty=true;
}
// ---- preview設定API（環境設定のpreviewタブから呼ぶ。値=raw。未初期化時も変数を保持し、setup/次回描画で反映）----
export function setBloomStrength(v){ _bloomStr=v; if(bloom) bloom.strength=v; _dirty=true; }
export function setBloomRadius(v){ _bloomRad=v; if(bloom) bloom.radius=v; _dirty=true; }
export function setBloomThreshold(v){ _bloomThr=v; if(bloom) bloom.threshold=v; _dirty=true; }
export function setAmbientLevel(v){ _ambLevel=v; if(structReflMat&&_ambientOn) structReflMat.uniforms.uAmbient.value.copy(_AMB_ON).multiplyScalar(_ambLevel); _dirty=true; }
export function setEmissionScale(v){ _emsScale=v; _dirty=true; }
export function setReflStrength(v){ _reflScale=v; if(structReflMat) structReflMat.uniforms.uReflStrength.value=0.8*_reflScale; _dirty=true; }
// ---- Bloomfog反射（ArcViewer PlatformShader移植）: ライトのグローを別バッファへ→構造物がフレネル反射でサンプル ----
let bloomfogRT=null, bloomfogRTb=null, structReflMat=null, blurMat=null, fsScene=null, fsCam=null, bfW=0, bfH=0;
const BLOOMFOG_LAYER=2, BLOOMFOG_SCALE=0.5;
let showNotes=true, showLights=true, showStructs=true;
let jp={njs:16,rt:1,hjd:8,bpm:120};                       // ジャンプパラメータ
let objs=[];                                              // {kind,time,build,mesh,upd}
let mapData=null, curSec=0;

let COL_RED=0xff274d, COL_BLUE=0x3092ff;   // ノーツ色（エディタのRED/BLUEをsetDataで受け取り上書き。既定もエディタ既定に合わせる）
// レーザー色の上書き（エディタのLRED/LBLUE。null=環境パレットのまま）。値は線形RGB[0-1]
let LAS_RED=null, LAS_BLUE=null, LAS_RED_B=null, LAS_BLUE_B=null;
const srgb2lin=s=> s<=0.04045 ? s/12.92 : Math.pow((s+0.055)/1.055,2.4);
const hexToLin=h=> [srgb2lin((h>>16&255)/255), srgb2lin((h>>8&255)/255), srgb2lin((h&255)/255)];

export function init(hostEl){
  if(renderer) return;
  host=hostEl;
  renderer=new THREE.WebGLRenderer({antialias:true,alpha:false});
  renderer.setPixelRatio(Math.min(devicePixelRatio,2));
  renderer.toneMapping=THREE.ACESFilmicToneMapping;       // HDR発光をトーンマップ（ブルーム前提）
  renderer.toneMappingExposure=1.0;
  renderer.domElement.style.cssText='position:absolute;inset:0;width:100%;height:100%;';
  host.appendChild(renderer.domElement);
  scene=new THREE.Scene();
  scene.background=new THREE.Color(0x000000);   // 背景=黒（ヘルバ様指示・全ステージ確認済み）
  scene.fog=new THREE.Fog(0x000000, 40, 260);   // 遠景は黒へフェード（距離感は残す）
  camera=new THREE.PerspectiveCamera(CAM_FOV,1,0.05,9000);   // TopTrackLasers等の極遠器具に対応
  camera.position.set(0,CAM_Y,-CAM_Z);                    // Unity(0,1.7,-2)→threeはZ反転で(0,1.7,+2)。器具/ノーツと同じ座標系に揃える
  camera.lookAt(0,CAM_Y,-100);                            // Unity+Z(奥)= three-Z を見る
  // ArcViewerの構造物は暗い（Platform shaderで微反射のみ）。環境光は控えめに
  ambLight=new THREE.AmbientLight(0x2a3038,0.5); scene.add(ambLight);   // 構造物を表示（回転リング等が見える明るさ）。環境ライトONで増光
  dirLight=new THREE.DirectionalLight(0x556a80,0.2); dirLight.position.set(2,8,-3); scene.add(dirLight);
  setAmbient(_ambientOn);   // 環境ライトの現在状態を反映（既定OFF）
  root=new THREE.Group(); scene.add(root);                // オブジェクトはここに全部ぶら下げる
  // 床は撤去（ArcViewer準拠）。不透明な床面(幅7.2,Y=0.26)がリング構造の下半分を遮蔽し、
  // 「構造物が上方に片寄る／位置が違う」原因になっていた。ArcViewerは手前に不透明な床を持たず
  // リング枠の下半分まで見える。編集補助のレーン線のみ残す。
  // レーン目安線（4レーン境界・トラック上・環境非依存の編集補助）
  { const laneG=new THREE.Group(); scene.add(laneG);
    for(const bx of [-1.2,-0.6,0,0.6,1.2]){
      const g=new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(bx,0.27,2),new THREE.Vector3(bx,0.27,-120)]);
      laneG.add(new THREE.Line(g,new THREE.LineBasicMaterial({color:0xffffff,transparent:true,opacity:0.9,fog:true}))); } }   // レーン境界（白）
  buildStaticStage();
  // ブルーム（発光の滲み）: strength/radius/threshold（旧pv版準拠 1.15/0.55/0.32）
  composer=new EffectComposer(renderer);
  composer.addPass(new RenderPass(scene,camera));
  bloom=new UnrealBloomPass(new THREE.Vector2(1,1),_bloomStr,_bloomRad,_bloomThr);   // Bloomfog近似: 虚空へグローを広げる（strength/radius/threshold=preview設定で調整可・既定0.85/1.0/0.32）
  composer.addPass(bloom);
  setupBloomfog();
  resize(); addEventListener('resize',resize);
  // pv1/ARCへ切替→復帰で pv4host が display:none⇄block する際、復帰時に canvas/カメラの resize が
  // 取り残されて表示が崩れるのを防ぐ。host のサイズ変化を必ず拾って resize する。
  if(typeof ResizeObserver!=='undefined'){ try{ new ResizeObserver(()=>resize()).observe(host); }catch(e){} }
}

// ---- Bloomfog反射パイプライン ----
const FS_VERT=`varying vec2 vUv; void main(){ vUv=uv; gl_Position=vec4(position.xy,0.0,1.0); }`;
const BLUR_FRAG=`uniform sampler2D tDiffuse; uniform vec2 dir; varying vec2 vUv;
void main(){ vec4 s=vec4(0.0);
  s+=texture2D(tDiffuse,vUv+dir*-4.0)*0.05; s+=texture2D(tDiffuse,vUv+dir*-3.0)*0.09;
  s+=texture2D(tDiffuse,vUv+dir*-2.0)*0.12; s+=texture2D(tDiffuse,vUv+dir*-1.0)*0.15;
  s+=texture2D(tDiffuse,vUv)*0.18;
  s+=texture2D(tDiffuse,vUv+dir*1.0)*0.15; s+=texture2D(tDiffuse,vUv+dir*2.0)*0.12;
  s+=texture2D(tDiffuse,vUv+dir*3.0)*0.09; s+=texture2D(tDiffuse,vUv+dir*4.0)*0.05;
  gl_FragColor=s; }`;
// 構造物: 基本色=Bloomfogのフレネル反射（ArcViewer PlatformShader §フラグ 119-120 相当）＋弱いambient/base、遠景は黒フォグ
const STRUCT_VERT=`varying vec3 vWN; varying vec3 vVN; varying vec4 vClip; varying vec3 vWP;
void main(){ vec4 wp=modelMatrix*vec4(position,1.0); vWP=wp.xyz;
  vWN=normalize(mat3(modelMatrix)*normal); vVN=normalize(normalMatrix*normal);
  vClip=projectionMatrix*viewMatrix*wp; gl_Position=vClip; }`;
const STRUCT_FRAG=`uniform sampler2D bloomfogTex; uniform vec3 uBase; uniform vec3 uAmbient;
uniform float uReflStrength; uniform float uReflDist; uniform float uFogNear; uniform float uFogFar;
varying vec3 vWN; varying vec3 vVN; varying vec4 vClip; varying vec3 vWP;
void main(){ vec3 camDir=normalize(cameraPosition-vWP); float fres=clamp(dot(camDir,vWN),0.0,1.0);
  vec2 sUV=(vClip.xy/vClip.w)*0.5+0.5;
  vec2 rUV=sUV+vVN.xy*(fres*uReflDist);
  vec3 col=texture2D(bloomfogTex,rUV).rgb*(uReflStrength*(1.0-fres));   // 反射（グレージング角ほど強い＝フレネル）
  col+=uAmbient+uBase;
  float dist=length(cameraPosition-vWP);
  float fog=clamp((uFogFar-dist)/(uFogFar-uFogNear),0.0,1.0);
  gl_FragColor=vec4(col*fog,1.0); }`;
function setupBloomfog(){
  const rtOpt={depthBuffer:false,stencilBuffer:false};
  bloomfogRT=new THREE.WebGLRenderTarget(2,2,rtOpt);
  bloomfogRTb=new THREE.WebGLRenderTarget(2,2,rtOpt);
  fsScene=new THREE.Scene(); fsCam=new THREE.OrthographicCamera(-1,1,1,-1,0,1);
  blurMat=new THREE.ShaderMaterial({uniforms:{tDiffuse:{value:null},dir:{value:new THREE.Vector2()}},
    vertexShader:FS_VERT,fragmentShader:BLUR_FRAG,depthTest:false,depthWrite:false});
  fsScene.add(new THREE.Mesh(new THREE.PlaneGeometry(2,2),blurMat));
  structReflMat=new THREE.ShaderMaterial({
    uniforms:{ bloomfogTex:{value:bloomfogRT.texture},
      uBase:{value:new THREE.Color(0x000000)}, uAmbient:{value:new THREE.Color(0x191a1c)},   // 下地=黒・環境光=ニュートラル暗灰（初期の青みを排除。色はライト反射から）
      uReflStrength:{value:0.8}, uReflDist:{value:0.35}, uFogNear:{value:40.0}, uFogFar:{value:260.0} },
    vertexShader:STRUCT_VERT,fragmentShader:STRUCT_FRAG,side:THREE.DoubleSide,fog:false});
}
function renderBloomfog(){   // 毎フレーム: ライトのグロー→低解像度バッファ→横縦ブラー→構造物が反射サンプル
  if(!bloomfogRT||!structReflMat||!bfW) return;
  const oldTarget=renderer.getRenderTarget();
  camera.layers.set(BLOOMFOG_LAYER);                       // ライト器具だけ描く
  renderer.setRenderTarget(bloomfogRT);
  renderer.setClearColor(0x000000,1); renderer.clear(true,true,true);
  renderer.render(scene,camera);
  camera.layers.set(0);                                    // メイン層へ戻す
  const sp=2.0;
  blurMat.uniforms.tDiffuse.value=bloomfogRT.texture; blurMat.uniforms.dir.value.set(sp/bfW,0);
  renderer.setRenderTarget(bloomfogRTb); renderer.render(fsScene,fsCam);
  blurMat.uniforms.tDiffuse.value=bloomfogRTb.texture; blurMat.uniforms.dir.value.set(0,sp/bfH);
  renderer.setRenderTarget(bloomfogRT); renderer.render(fsScene,fsCam);
  renderer.setRenderTarget(oldTarget);
}

// ===================== DefaultEnvironment（ArcViewer実シーンをJSON化して忠実読込）=====================
// NLMEnvExport.cs で書き出した preview-v4/env/DefaultEnvironment.json（実メッシュ＋厳密world行列
// ＋LightHandler設定）を読み込む。近似は一切なし。座標系は envGroup.scale.z=-1 で一括反転。
let fixtures=[], structs=[], envGroup=null, envLoaded=false, envLoadToken=0;
let ringAnims=[], laserAnims=[], zoomAnims=[];   // 回転/ズームアニメ対象
let _dirty=true, _lastSec=NaN, fixturesByType={};   // ①停止中の再描画スキップ用 / ③ライト型別fixture
const _luQ=new THREE.Quaternion(), _luAxis=new THREE.Vector3();   // ②updateLightsの毎フレーム確保を撤廃（使い回し）
export function markDirty(){ _dirty=true; }   // 外部からの明示的な再描画要求（必要時）
let _renderCount=0;
export function _dbgStats(){ return {renderCount:_renderCount, dirty:_dirty}; }   // 診断用（停止中スキップの検証）
const OFF_COL=new THREE.Color().setRGB(0.196,0.196,0.302,THREE.LinearSRGBColorSpace); // 消灯時の薄紫（Laser.prefab OffColor）
function laserMat(){ return new THREE.MeshBasicMaterial({color:0x000000,transparent:true,fog:false,side:THREE.DoubleSide,depthWrite:false,blending:THREE.AdditiveBlending}); }   // 加算合成: 消灯(黒)＝何も足さない＝透明・点灯＝グロー加算
const Z=z=>-z;

let curEnvName='DefaultEnvironment';
const ENV_LIST=['DefaultEnvironment','BigMirrorEnvironment','TriangleEnvironment','NiceEnvironment',
  'KDAEnvironment','MonstercatEnvironment','DragonsEnvironment','OriginsEnvironment','PanicEnvironment',
  'TimbalandEnvironment','LinkinParkEnvironment','FitBeatEnvironment','KaleidoscopeEnvironment'];
export function environments(){ return ENV_LIST.slice(); }
export function setEnvironment(name){
  if(!ENV_LIST.includes(name)) name='DefaultEnvironment';   // v3環境等は既定へフォールバック
  if(name===curEnvName && envLoaded) return;
  curEnvName=name; applyEnvParams(name);
  if(mapData&&mapData.lights) parseLights(mapData.lights, mapData.bpm||120);   // ENV変更→リング/レーザーのチェーン再構築
  loadEnvironment(name);
}
function buildStaticStage(){ applyEnvParams(curEnvName); loadEnvironment(curEnvName); }
async function loadEnvironment(name){
  const myToken=++envLoadToken;   // 二重生成防止トークン（起動時 buildStaticStage と setEnvironment が競合するため）
  let j;
  try{ j=await fetch('preview-v4/env/'+name+'.json',{cache:'no-store'}).then(r=>r.json()); }
  catch(e){ console.warn('[v2] 環境JSON読込失敗',e); return; }
  if(myToken!==envLoadToken) return;   // 後から別のロードが始まった→この結果は捨てる（環境ダブり防止）
  // 既存環境を破棄（await後に・常に最新の1個だけ残す）
  if(envGroup){ scene.remove(envGroup);
    envGroup.traverse(o=>{ if(o.geometry) o.geometry.dispose(); if(o.material&&o.material!==structReflMat) o.material.dispose(); });   // 共有のstructReflMatは破棄しない
    envGroup=null; envLoaded=false; }
  fixtures=[]; structs=[]; ringAnims=[]; laserAnims=[]; zoomAnims=[];
  // メッシュ→BufferGeometry
  const geos={};
  for(const k in j.meshes){ const md=j.meshes[k];
    const g=new THREE.BufferGeometry();
    g.setAttribute('position',new THREE.Float32BufferAttribute(md.v,3));
    if(md.n&&md.n.length===md.v.length){ g.setAttribute('normal',new THREE.Float32BufferAttribute(md.n,3)); }
    g.setIndex(md.i);
    if(!(md.n&&md.n.length)) g.computeVertexNormals();
    geos[k]=g;
  }
  envGroup=new THREE.Group(); envGroup.scale.set(1,1,-1); scene.add(envGroup);   // Unity左手系→three右手系
  const structMat=structReflMat||new THREE.MeshStandardMaterial({color:0x141f30,emissive:0x0c1526,emissiveIntensity:0.35,roughness:1.0,metalness:0,side:THREE.DoubleSide,fog:true});   // 構造物=Bloomfog反射シェーダ(structReflMat)。未初期化時のみ旧材質
  // トラック上面も構造物と同じ反射材質(structReflMat)を使う（固定青の発光を廃止）

  // 階層をそのまま再構築（親index＋ローカルTRS）→ArcViewerと同じtransformを回転できる
  const objs=new Array(j.nodes.length);
  for(const node of j.nodes){
    let o;
    if(node.mesh && node.n!=='GlowLine' && geos[node.mesh]){
      const lit=!!node.light;
      const mat=lit?laserMat():structMat;   // トラックも他の構造物と同じ反射材質（固定青をやめる・ヘルバ様指示）。レーンは白線で見える
      o=new THREE.Mesh(geos[node.mesh], mat);
      if(lit){ const off=/Wire|Building|RingLight/i.test(node.n||'')?OFF_COL:null;
        o.layers.enable(BLOOMFOG_LAYER);   // ライト器具はBloomfog反射バッファにも写す
        fixtures.push({mesh:o,mat:o.material,type:node.light.type,emMult:node.light.em||1,off}); }
      else structs.push(o);                               // 非ライト＝構造物（表示トグル対象）
    } else o=new THREE.Object3D();                        // 空ノード or GlowLine（非表示）
    o.position.fromArray(node.t);
    o.quaternion.fromArray(node.r);
    o.scale.fromArray(node.s);
    o.userData.baseQ=o.quaternion.clone();               // 回転アニメの基準
    objs[node.i]=o;
    if(node.ring) ringAnims.push({obj:o,big:!!node.ring.big,id:node.ring.id});
    if(node.ringZoom) zoomAnims.push({obj:o,firstRingPos:node.ringZoom.firstRingPos});
    if(node.rotLaser) o.userData.rotLaser=node.rotLaser;
  }
  // 親子付け
  for(const node of j.nodes){ const o=objs[node.i];
    if(node.p>=0 && objs[node.p]) objs[node.p].add(o); else envGroup.add(o); }
  // rotLaserターゲット→laserAnims（グループ内index付き）
  for(const node of j.nodes){ if(!node.rotLaser) continue;
    node.rotLaser.targets.forEach((ti,li)=>{ const to=objs[ti]; if(!to) return;
      laserAnims.push({obj:to,baseQ:to.userData.baseQ,eventType:node.rotLaser.eventType,axis:node.rotLaser.axis,idx:li}); }); }
  // zoom: 子リング（SmallRing群）とその基準Z
  for(const za of zoomAnims){ za.rings=za.obj.children.filter(c=>c.userData&&c.userData.baseQ!==undefined);
    za.baseZ=za.rings.map(c=>c.position.z); }

  for(const m of structs) m.visible=showStructs;   // 再ロード時も構造物トグル状態を維持
  if(!showLights) for(const fx of fixtures) applyFixture(fx,null);   // ライト非表示状態も維持
  envLoaded=true;
  buildFixturesByType(); _dirty=true;   // ③型別グループを構築 / ①環境更新→次フレームで再描画
}
function buildFixturesByType(){ fixturesByType={};   // ③ライト型(et)ごとにfixtureを分類（updateLightsの5周走査を廃止）
  for(const fx of fixtures){ (fixturesByType[fx.type]||(fixturesByType[fx.type]=[])).push(fx); } }

function resize(){
  if(!renderer||!host) return;
  const r=host.getBoundingClientRect();
  if(r.width<2||r.height<2) return;
  renderer.setSize(r.width,r.height,false);
  camera.aspect=r.width/r.height; camera.updateProjectionMatrix();
  if(composer){ composer.setSize(r.width,r.height); composer.setPixelRatio(Math.min(devicePixelRatio,2)); }
  bfW=Math.max(2,Math.floor(r.width*BLOOMFOG_SCALE)); bfH=Math.max(2,Math.floor(r.height*BLOOMFOG_SCALE));
  if(bloomfogRT){ bloomfogRT.setSize(bfW,bfH); bloomfogRTb.setSize(bfW,bfH); }
  _dirty=true;
}
export function setActive(v){ active=v; if(v){ resize(); requestAnimationFrame(resize);
  try{ renderBloomfog(); if(composer) composer.render(); else if(renderer) renderer.render(scene,camera); }catch(e){} } }   // 復帰時: 即resize＋即1回描画（古いバッファを残さない）＋レイアウト確定後にもう一度resize
export function setVisible(notes,lights){ showNotes=notes; showLights=lights;
  if(root) root.visible=showNotes;
  if(!lights) for(const fx of fixtures) applyFixture(fx,null); _dirty=true; }   // 消灯
export function setStructVisible(v){ showStructs=v; for(const m of structs) m.visible=v; _dirty=true; }   // 構造物の表示非表示

// ===================== ジャンプ計算（BeatmapManager §4）=====================
function computeJump(njs,bpm,spawnOffset){
  const jd=(hjd)=>njs*2*(60/bpm*hjd);
  let defHJD=4; let guard=0;
  while(jd(defHJD)>35.998 && guard++<64) defHJD/=2;
  const HJD=Math.max(defHJD+(spawnOffset||0),0.25);
  const JD=jd(HJD);
  return {njs, bpm, hjd:JD/2, rt:JD/2/njs};
}

// ===================== グリッド座標・角度（§6）=====================
const OBJ_LIFT=-FLOOR_OFFSET+0.25;   // =0.85 ObjectSpaceToWorldSpace: grid原点→world（床から持ち上げ）
function gridPos(x,y){ return [GRID_X0+clamp(x,0,3)*LANE_W, OBJ_LIFT+clamp(y,0,2)*ROW_H]; }   // [worldX, worldY]
function objAngle(cutDir,angleOffset){
  let a=(DIR_ANGLES[clamp(cutDir,0,8)]??0)+(angleOffset||0);
  a%=360; if(a>180)a-=360; else if(a<-180)a+=360; return a;
}
function dirVec(angleDeg){ const r=angleDeg*Math.PI/180; return [Math.sin(r), -Math.cos(r)]; }
const clamp=(v,a,b)=>v<a?a:(v>b?b:v);
const samePlane=(a,b)=>{ const d=Math.abs(a-b); return Math.abs(d)<0.01||Math.abs(d-180)<0.01; };

// ===================== Z位置・Y放物線（JumpManager §5）=====================
function getZ(objTime, njs, rt, hjd){
  const jumpTime=curSec+rt;
  if(objTime<=jumpTime) return (objTime-curSec)*njs + CUT_PLANE;         // 等速接近
  return hjd + MOVE_Z*((objTime-jumpTime)/MOVE_TIME);                    // スポーン移動
}
function spawnParabola(target,base,hjd,t){
  const d2=hjd*hjd; const range=target-base;
  return clamp(-(range/d2)*t*t+target,-9999,9999);
}
function getObjectY(startY,targetY,z,hjd,objTime,rt){
  const jumpTime=curSec+rt;
  if(objTime>jumpTime) return startY;
  return spawnParabola(targetY,startY,hjd,z-CUT_PLANE);
}

// StartY: 同拍・同列で自分の下にあるノーツ数（再帰・§5.4）
function startYStack(n, sameBeat){
  if(n.y<=0) return 0;
  const below=sameBeat.filter(o=>o!==n && o.x===n.x && o.y<n.y);
  if(!below.length) return 0;
  return Math.max(...below.map(o=>startYStack(o,sameBeat)))+1;
}

// ===================== ライトエンジン（spec-lights）=====================
// 環境別カラーパレット（リニア0-1・spec-lights §5.3）。c1=赤系/c2=青系/w=白/b*=Boost。
const W=[1,1,1];
const PALETTES={
  DefaultEnvironment:{c1:[.85,.085,.085],c2:[.1882353,.675294,1],w:W,b1:[.85,.085,.085],b2:[.1882353,.675294,1],bw:W},
  TriangleEnvironment:{c1:[.85,.085,.085],c2:[.1882353,.675294,1],w:W,b1:[.85,.085,.085],b2:[.1882353,.675294,1],bw:W},
  NiceEnvironment:{c1:[.85,.085,.085],c2:[.1882353,.675294,1],w:W,b1:[.85,.085,.085],b2:[.1882353,.675294,1],bw:W},
  BigMirrorEnvironment:{c1:[.85,.085,.085],c2:[.1882353,.675294,1],w:W,b1:[.85,.085,.085],b2:[.1882353,.675294,1],bw:W},
  MonstercatEnvironment:{c1:[.85,.085,.085],c2:[.1882353,.675294,1],w:W,b1:[.85,.085,.085],b2:[.1882353,.675294,1],bw:W},
  PanicEnvironment:{c1:[.85,.085,.085],c2:[.1882353,.675294,1],w:W,b1:[.85,.085,.085],b2:[.1882353,.675294,1],bw:W},
  DragonsEnvironment:{c1:[.85,.085,.085],c2:[.1882353,.675294,1],w:W,b1:[.85,.085,.085],b2:[.1882353,.675294,1],bw:W},
  OriginsEnvironment:{c1:[.4910995,.6862745,.7],c2:[.03844783,.6862745,.9056604],w:W,b1:[.4910995,.6862745,.7],b2:[.03844783,.6862745,.9056604],bw:W},
  KDAEnvironment:{c1:[1,.3960785,.2431373],c2:[.7607844,.1254902,.8666667],w:W,b1:[1,.3960785,.2431373],b2:[.7607844,.1254902,.8666667],bw:W},
  TimbalandEnvironment:{c1:[.1,.5517647,1],c2:[.1,.5517647,1],w:W,b1:[.1,.5517647,1],b2:[.1,.5517647,1],bw:W},
  FitBeatEnvironment:{c1:[.8,.5594772,.5594772],c2:[.5594772,.5594772,.8],w:W,b1:[.8,.5594772,.5594772],b2:[.5594772,.5594772,.8],bw:W},
  LinkinParkEnvironment:{c1:[.7529412,.672753,.5925647],c2:[.6241197,.6890281,.709],w:W,b1:[.922,.5957885,.255394],b2:[.282353,.4586275,.6235294],bw:W},
  KaleidoscopeEnvironment:{c1:[.65882355,.1254902,.1254902],c2:[.47058824,.47058824,.47058824],w:W,b1:[.50196081,0,0],b2:[.49244517,0,.53725493],bw:W},
};
// 環境別パラメータ（spec-lights §12.2）: [laserCount,randomize,laserStep, sRing S/A/P/Max/StA/StS, bRing …, zoom S/C/F]
const ENVPARAMS={
  DefaultEnvironment:[4,1,0, 2,90,1,5,-45,3, 2,45,1,5,-45,0, 2,2,5],
  OriginsEnvironment:[5,1,0, 2,0,1,0,0,0, 2,90,1,3,-45,0, 0,5,5],
  TriangleEnvironment:[7,1,0, 2,90,1,7,45,4, 2,45,1,5,-45,0, 2,5,10],
  NiceEnvironment:[4,1,0, 2,90,1,5,-45,3, 2,45,1,5,-45,0, 2,1,5],
  BigMirrorEnvironment:[4,1,0, 2,90,1,5,-45,3, 2,45,1,5,-45,0, 2,2,5],
  DragonsEnvironment:[5,1,0, 3,90,.5,15,90,5, 2,45,1,5,-45,0, 4,.25,1.75],
  KDAEnvironment:[7,1,0, 0,0,0,0,0,0, 0,0,0,0,0,0, 0,0,0],
  MonstercatEnvironment:[5,1,0, 2,90,1,5,-45,3, 2,45,1,5,-45,0, 2,7,7],
  PanicEnvironment:[7,1,0, 2,90,1,20,0,5, 2,45,1,5,-45,0, 2,.25,1.5],
  TimbalandEnvironment:[10,0,25, 2,45,1,3,0,0, 2,0,1,0,0,0, 2,2,4],
  FitBeatEnvironment:[8,0,25, 3,90,.5,15,90,5, 2,90,1,5,45,0, 4,.25,1.75],
  LinkinParkEnvironment:[18,1,5, 2,90,1,5,-45,3, 2,45,1,5,-45,0, 2,2,5],
  KaleidoscopeEnvironment:[0,1,0, 6,90,.75,18,0,45, 6,90,.75,10,0,45, 4,1,3],
};
const FLIP_BACK_ENVS=['DragonsEnvironment','FitBeatEnvironment'];   // §4.3 バックレーザー赤青反転
let PAL=PALETTES.DefaultEnvironment, flipBack=false;
let ENV={ laserCount:4, randomize:true, laserStep:0,
  sRingSpeed:2,sRingAmt:90,sRingProp:1,sRingMaxStep:5,sRingStartAngle:-45,sRingStartStep:3,
  bRingSpeed:2,bRingAmt:45,bRingProp:1,bRingMaxStep:5,bRingStartAngle:-45,bRingStartStep:0,
  zoomSpeed:2,closeZoom:2,farZoom:5 };
const MIRROR_ENVS=['BigMirrorEnvironment'];   // 強い鏡面床
function applyEnvParams(name){
  PAL=PALETTES[name]||PALETTES.DefaultEnvironment;
  flipBack=FLIP_BACK_ENVS.includes(name);
  const p=ENVPARAMS[name]||ENVPARAMS.DefaultEnvironment;
  ENV={ laserCount:p[0]||1, randomize:!!p[1], laserStep:p[2],
    sRingSpeed:p[3],sRingAmt:p[4],sRingProp:p[5]||0.0001,sRingMaxStep:p[6],sRingStartAngle:p[7],sRingStartStep:p[8],
    bRingSpeed:p[9],bRingAmt:p[10],bRingProp:p[11]||0.0001,bRingMaxStep:p[12],bRingStartAngle:p[13],bRingStartStep:p[14],
    zoomSpeed:p[15],closeZoom:p[16],farZoom:p[17] };
}
const FLASH_I=1.2;
const cubicOut=t=>1-Math.pow(1-t,3);
const expoOut=t=>t>=1?1:1-Math.pow(2,-10*t);
// 決定的乱数（ロード時固定・シーク不変）
let _seed=1; function srand(){ _seed=(_seed*1103515245+12345)&0x7fffffff; return _seed/0x7fffffff; }
function seedReset(s){ _seed=s>>>0||1; }

// イベント: 各typeのソート済みリスト＋boost＋リング/レーザー速度
let LE={by:{0:[],1:[],2:[],3:[],4:[]}, boost:[], ringSpin:[], ringZoom:[], lspd:{12:[],13:[]}};

function parseLights(lights,bpm){
  LE={by:{0:[],1:[],2:[],3:[],4:[]}, boost:[], ringSpin:[], ringZoom:[], lspd:{12:[],13:[]}};
  const s2t=b=>b*60/bpm;
  for(const e of (lights||[])){
    const et=e.et, val=e.i??e.value??0, f=(e.f!=null?e.f:(e._floatValue!=null?e._floatValue:1));
    const t=s2t(e.beat!=null?e.beat:(e.b??0));
    if(et===5){ LE.boost.push({t,on:val>0}); continue; }   // v2 boost（type5）
    const cd=e.raw&&e.raw.customData&&e.raw.customData.color;   // クロマ色（実機Chroma仕様: raw.customData.color、0-1 float RGB）
    const ev={t,val,f,color:cd?cd.slice(0,3):null};
    if(et>=0&&et<=4) LE.by[et].push(ev);
    else if(et===8) LE.ringSpin.push(ev);
    else if(et===9) LE.ringZoom.push(ev);
    else if(et===12||et===13) LE.lspd[et].push(ev);
  }
  // v3独立boost配列があれば（mapData.boostEvents）
  if(mapData&&mapData.boostEvents) for(const b of mapData.boostEvents) LE.boost.push({t:s2t(b.b??b.beat),on:!!(b.o??b.on)});
  for(const k in LE.by) LE.by[k].sort((a,b)=>a.t-b.t);
  LE.boost.sort((a,b)=>a.t-b.t); LE.ringSpin.sort((a,b)=>a.t-b.t); LE.ringZoom.sort((a,b)=>a.t-b.t);
  LE.lspd[12].sort((a,b)=>a.t-b.t); LE.lspd[13].sort((a,b)=>a.t-b.t);
  // レーザー回転データ生成（本数分の開始角/方向・ロード時固定）
  seedReset(0x9e37);
  for(const et of [12,13]) for(const ev of LE.lspd[et]) populateRot(ev);
  // 右レーザー: 同時刻の左と共有
  for(const rev of LE.lspd[13]){ const lev=LE.lspd[12].find(l=>Math.abs(l.t-rev.t)<=0.001);
    if(lev&&lev.val!==0){ rev.rot=lev.rot; } }
  // リング回転チェーン初期化
  ringSpinInit();
}
function populateRot(ev){
  ev.rot=[]; const speed=ev.val*20; ev.speed=speed;
  const startAngle=srand()*360, unifiedDir=srand()>=0.5;
  for(let i=0;i<ENV.laserCount;i++){
    let d={dir:false,start:0};
    if(ev.val>0){ d.dir=ENV.randomize?(srand()>=0.5):unifiedDir;
      d.start=ENV.randomize?srand()*360:((startAngle+ENV.laserStep*(d.dir?1:-1)*i)%360);
      if(d.start<0)d.start+=360; }
    ev.rot.push(d);
  }
}
function ringSpinInit(){
  // Small/Big 各チェーン: TargetAngle=前TargetAngle±Rotation, Step=乱数[-max,max]
  LE.sRing=buildRingChain(LE.ringSpin,ENV.sRingAmt,ENV.sRingMaxStep,ENV.sRingStartAngle,ENV.sRingStartStep,ENV.sRingSpeed,ENV.sRingProp,0x1234);
  LE.bRing=buildRingChain(LE.ringSpin,ENV.bRingAmt,ENV.bRingMaxStep,ENV.bRingStartAngle,ENV.bRingStartStep,ENV.bRingSpeed,ENV.bRingProp,0x5678);
  // Zoom チェーン
  LE.zoom=[]; let parity=true, startStep=ENV.farZoom; // StartRingZoomParity=true→Far
  for(let i=0;i<LE.ringZoom.length;i++){ const e=LE.ringZoom[i];
    const far = i===0 ? false : !LE.zoom[i-1].far;
    const st = i===0 ? startStep : zoomStepAt(LE.zoom[i-1], e.t);
    const step = far?ENV.farZoom:ENV.closeZoom;
    LE.zoom.push({t:e.t,far,startStep:st,step,speed:ENV.zoomSpeed}); }
}
function buildRingChain(src,amt,maxStep,startAngle,startStep,speed,prop,seed){
  seedReset(seed); const out=[];
  for(let i=0;i<src.length;i++){ const e=src[i];
    const cw=srand()>=0.5; const rotation=amt; const step=(srand()*2-1)*maxStep;
    let sAngle,sStep,target;
    if(i===0){ sAngle=startAngle; sStep=startStep; target=startAngle+(cw?-rotation:rotation); }
    else { const p=out[i-1]; const pr=ringProgress(e.t-p.t,p.speed);
      sAngle=lerp(p.sAngle,p.target,pr); sStep=lerp(p.sStep,p.step,pr);
      target=p.target+(cw?-rotation:rotation); }
    out.push({t:e.t,sAngle,sStep,target,step,speed,prop}); }
  return out;
}
const ringProgress=(dt,speed)=>1-Math.pow(2,-(Math.max(0,dt)*speed*2));
function zoomStepAt(z,time){ const p=ringProgress(time-z.t,z.speed); return lerp(z.startStep,z.step,p); }

// value→色（§4）。返り値 {rgb:[r,g,b], a:強度}。et=イベントtype（バックレーザー反転判定用）
function eventColor(ev,next,et){
  if(!ev) return null;
  const boost=boostAt(curSec);
  const flip=(et===0&&flipBack);   // Dragons/FitBeatはバックレーザーの赤青反転
  let v=ev.val;
  const base=(vv,customColor)=>{
    if(customColor) return customColor.slice();   // クロマ色（カスタムRGB）は通常の赤/青/白より優先
    let blue=vv>=1&&vv<=4, red=vv>=5&&vv<=8;
    if(flip){ const t=blue; blue=red; red=t; }   // 値の色だけ入れ替え（白/Offは不変）
    if(blue) return (boost?(LAS_BLUE_B||PAL.b2):(LAS_BLUE||PAL.c2)).slice();   // エディタのレーザー色を優先
    if(red)  return (boost?(LAS_RED_B ||PAL.b1):(LAS_RED ||PAL.c1)).slice();
    if(vv>=9&&vv<=12) return (boost?PAL.bw:PAL.w).slice();  // White
    return null;                                  // Off
  };
  const isTrans=vv=>vv===4||vv===8||vv===12;
  const isFlash=vv=>vv===2||vv===6||vv===10;
  const isFade=vv=>vv===3||vv===7||vv===11;
  const rgb=base(v,ev.color); let a=(rgb?1:0)*(ev.f||1);
  if(isFlash(v)){ const d=curSec-ev.t; if(d<0.6) a*=lerp(FLASH_I,1,cubicOut(d/0.6)); return {rgb:rgb||[0,0,0],a}; }
  if(isFade(v)){ const d=curSec-ev.t; if(d>=1.5) a=0; else a*=lerp(FLASH_I,0,expoOut(d/1.5)); return {rgb:rgb||[0,0,0],a}; }
  // On/Off/Transition: 次がTransitionなら補間
  if(next&&isTrans(next.val)){
    const nb=base(next.val,next.color)||[0,0,0]; let na=(base(next.val,next.color)?1:0)*(next.f||1);
    let r=rgb||nb.slice(), aa=a;
    if(!rgb){ r=nb.slice(); aa=0; }   // Off→Transitionは遷移先色でα0起点
    const tt=(curSec-ev.t)/(next.t-ev.t);
    const cl=Math.max(0,Math.min(1,tt));
    return {rgb:[lerp(r[0],nb[0],cl),lerp(r[1],nb[1],cl),lerp(r[2],nb[2],cl)], a:lerp(aa,na,cl)};
  }
  return {rgb:rgb||[0,0,0], a};
}
function lastIdx(list,t){ let lo=0,hi=list.length-1,res=-1;
  while(lo<=hi){ const m=(lo+hi)>>1; if(list[m].t<=t){res=m;lo=m+1;}else hi=m-1;} return res; }
function boostAt(t){ const i=lastIdx(LE.boost,t); return i>=0?LE.boost[i].on:false; }

function updateLights(){
  // === 構造物の動き（リング回転/ズーム）はライトOFFでも動かす（構造物パラメータでありライトではない）===
  // リング回転（RingHandler: localEuler.z=angle・§8）
  { const idx=lastIdx(LE.ringSpin,curSec);
    for(const r of ringAnims){ const chain=r.big?LE.bRing:LE.sRing;
      const da=r.big?ENV.bRingStartAngle:ENV.sRingStartAngle, ds=r.big?ENV.bRingStartStep:ENV.sRingStartStep;
      const ang=ringAngle(chain,idx,curSec,r.id,da,ds);
      r.obj.rotation.set(0,0,ang*Math.PI/180); }   // base x,y=0（リングはZ回転のみ）
  }
  // リングズーム（RingZoomHandler: 子リングの localPosition.z=firstRingPos+step*i・§9）
  { const idx=lastIdx(LE.ringZoom,curSec);
    let step=ENV.farZoom;
    if(idx>=0){ const z=LE.zoom[idx]; step=lerp(z.startStep,z.step,ringProgress(curSec-z.t,z.speed)); }
    for(const za of zoomAnims) za.rings.forEach((ring,i)=>{ ring.position.z=za.firstRingPos+step*i; }); }
  // === ここから下はライト（色/レーザー回転）。ライトOFFなら省略 ===
  if(!showLights) return;
  // 各type: 現在イベント＋次イベント→色→そのtypeの器具へ
  for(const et of [0,1,2,3,4]){
    const list=LE.by[et]; const idx=lastIdx(list,curSec);
    const c=eventColor(idx>=0?list[idx]:null, idx>=0?list[idx+1]:null, et);
    const fxs=fixturesByType[et]; if(fxs) for(const fx of fxs) applyFixture(fx,c);   // ③型別＝全fixtureの5周走査を廃止
  }
  // レーザー回転（RotatingLaserHandler: target.localEuler.axis=angle・§7）
  for(const la of laserAnims){ const list=LE.lspd[la.eventType]; const idx=lastIdx(list,curSec);
    const ev=idx>=0?list[idx]:null; let ang=0;
    if(ev&&ev.rot&&ev.rot[la.idx%ENV.laserCount]){ const rd=ev.rot[la.idx%ENV.laserCount];
      ang=rd.start+(ev.speed*(curSec-ev.t))*(rd.dir?-1:1); }
    // base y=0前提: localEuler(baseX,ang,baseZ)=Rax(ang)*baseQ（axis 0=X,1=Y,2=Z）
    _luAxis.set(la.axis===0?1:0, la.axis===1?1:0, la.axis===2?1:0);   // ②使い回し
    _luQ.setFromAxisAngle(_luAxis, ang*Math.PI/180);
    la.obj.quaternion.copy(_luQ).multiply(la.baseQ);
  }
}
function ringAngle(chain,idx,t,ringId,defAngle,defStep){
  if(idx<0||!chain||!chain.length) return defAngle+defStep*ringId;
  // propを遡って「このリングに届いている最新イベント」を探す
  let cur=null;
  for(let i=Math.min(idx,chain.length-1);i>=0;i--){
    const infl=chain[i].t+(1/60)*ringId/(chain[i].prop||1);
    if(infl<=t){ cur=chain[i]; break; } }
  if(!cur) return defAngle+defStep*ringId;
  const infl=cur.t+(1/60)*ringId/(cur.prop||1);
  const p=ringProgress(t-infl,cur.speed);
  const angle=lerp(cur.sAngle,cur.target,p), step=lerp(cur.sStep,cur.step,p);
  return angle+step*ringId;
}
const EMISSION=1.35;   // HDR発光倍率（ARC実測比較で校正: ARCは繊細で暗い。過剰なネオン感を抑制）
function applyFixture(fx,c){
  if(!c||c.a<=0.001){
    fx.mat.color.setRGB(0,0,0,THREE.LinearSRGBColorSpace);   // 消灯=黒＝加算合成で透明（ライト枠が障害物にならない）
    return;
  }
  const inten=c.a*EMISSION*_emsScale*(fx.emMult||1);                       // HDR: bloomが拾って滲む（_emsScale=preview設定の発光倍率）
  fx.mat.color.setRGB(c.rgb[0]*inten, c.rgb[1]*inten, c.rgb[2]*inten, THREE.LinearSRGBColorSpace);
}

// ===================== 譜面差し替え =====================
export function setData(d){
  mapData=d;
  applyColors(d);                            // ノーツ/レーザー色をエディタの設定値に合わせる
  jp=computeJump(d.njs||16, d.bpm||120, d.njsOffset||0);   // NJS＋オフセットで飛来（接近速度/出現距離）を計算
  parseLights(d.lights, d.bpm||120);
  rebuild(); _dirty=true;
}
// エディタの色（RED/BLUE=ノーツ, LRED/LBLUE=レーザー, _B=BOOST派生）をV2へ反映
function applyColors(d){
  if(d.noteRed!=null){ COL_RED=d.noteRed>>>0; COL_BLUE=d.noteBlue>>>0;
    if(G){ G.matRed.color.setHex(COL_RED); G.matRed.emissive.setHex(COL_RED);
      G.matBlue.color.setHex(COL_BLUE); G.matBlue.emissive.setHex(COL_BLUE);
      G.matArcR.color.setHex(COL_RED); G.matArcB.color.setHex(COL_BLUE); } }
  if(d.laserRed!=null){ LAS_RED=hexToLin(d.laserRed>>>0); LAS_BLUE=hexToLin(d.laserBlue>>>0);
    LAS_RED_B =hexToLin((d.laserRedB ??d.laserRed )>>>0);
    LAS_BLUE_B=hexToLin((d.laserBlueB??d.laserBlue)>>>0); }
}

function clearObjs(){
  if(!root) return;
  for(const o of objs){ root.remove(o.grp);
    o.grp.traverse(c=>{ if(c.geometry&&c.userData.own) c.geometry.dispose(); }); }
  objs=[];
}

// 共有ジオメトリ/マテリアル
let G=null;
function sharedGeo(){
  if(G) return G;
  const noteMat=c=>new THREE.MeshStandardMaterial({color:c,emissive:c,emissiveIntensity:0.35,roughness:0.35,metalness:0.1});
  // ノーツはPV1(three.js版1)と同一方式を流用: 面取りキューブ＋canvasの矢印/ドットテクスチャ（自作の雑ジオメトリは廃止）
  const mkTex=draw=>{ const c=document.createElement('canvas'); c.width=c.height=128; const x=c.getContext('2d'); draw(x); const t=new THREE.CanvasTexture(c); t.anisotropy=4; return t; };
  const arrowTex=mkTex(x=>{ x.lineJoin='round'; x.lineCap='round'; x.lineWidth=8; x.strokeStyle='#fff'; x.fillStyle='#fff';
    x.beginPath(); x.moveTo(64,78); x.lineTo(112,112); x.lineTo(16,112); x.closePath(); x.stroke(); x.fill(); });
  const chainHeadArrowTex=mkTex(x=>{ x.lineJoin='round'; x.lineCap='round'; x.lineWidth=8; x.strokeStyle='#fff'; x.fillStyle='#fff';
    x.beginPath(); x.moveTo(64,32); x.lineTo(108,96); x.lineTo(20,96); x.closePath(); x.stroke(); x.fill(); });
  const dotTex=mkTex(x=>{ x.fillStyle='#fff'; x.beginPath(); x.arc(64,64,23,0,7); x.fill(); });
  const PV_CORNER_CUT=NOTE_CORNER_CUT;
  G={
    note:makeChamferBoxGeometry(0.46,0.46,0.46,PV_CORNER_CUT),
    chainHead:makeChainHeadGeometry(),
    chainLink:makeChainLinkGeometry(),
    bomb:makeSpikyBomb(0.2,0.11,0.065),   // 黒トゲトゲ
    mark:new THREE.PlaneGeometry(0.4,0.4),   // 矢印/ドットを貼る面（PV1のmarkGeo）
    chainHeadMark:new THREE.PlaneGeometry(0.4,0.18),
    matRed:noteMat(COL_RED), matBlue:noteMat(COL_BLUE),
    matBomb:new THREE.MeshStandardMaterial({color:0x0c0c0e,emissive:0x000000,metalness:0.55,roughness:0.4}),   // 黒（赤発光なし）
    matArrow:new THREE.MeshBasicMaterial({map:arrowTex,transparent:true}),   // PV1の矢印テクスチャ
    matChainHeadArrow:new THREE.MeshBasicMaterial({map:chainHeadArrowTex,transparent:true}),
    matDot:new THREE.MeshBasicMaterial({map:dotTex,transparent:true}),       // PV1のドットテクスチャ
    matArcR:new THREE.MeshBasicMaterial({color:COL_RED,transparent:true,opacity:0.6,depthWrite:false}),
    matArcB:new THREE.MeshBasicMaterial({color:COL_BLUE,transparent:true,opacity:0.6,depthWrite:false}),
    matWall:new THREE.MeshStandardMaterial({color:0xd0284a,transparent:true,opacity:0.25,emissive:0x501020,depthWrite:false}),
  };
  return G;
}

function rebuild(){
  clearObjs(); if(!mapData) return;
  const g=sharedGeo();
  const N=mapData.notes||[], B=mapData.bombs||[], W=mapData.walls||[], A=mapData.arcs||[], C=mapData.chains||[];

  // --- 同拍グルーピング（StartY・スナップ・フリップ用）---
  const notesAndBombs=[...N.map(n=>({...n,_bomb:false})),...B.map(b=>({...b,_bomb:true}))];
  const byBeat=new Map();
  for(const o of notesAndBombs){ const k=Math.round(o.beat*1000)/1000;
    if(!byBeat.has(k)) byBeat.set(k,[]); byBeat.get(k).push(o); }

  // --- ノーツ ---
  for(const raw of N){
    const [wx,wy]=gridPos(raw.x,raw.y);
    // DIR_ANGLES はBS/ArcViewer本家の「下向き矢印モデル」基準（下=0°,上=180°）。
    // 当ポートの矢印テクスチャは上向き▲基準のため 180-ang で画面角へ変換（変換しないと上下が鏡像＝ヘルバ様報告のEDIT⇔PREVIEW矢印逆バグ）
    const angle=(raw.d===8)?0:180-((raw.a!=null)?objAngle(raw.d,raw.a):objAngle(raw.d,0));
    const same=byBeat.get(Math.round(raw.beat*1000)/1000)||[];
    const stack=startYStack({x:raw.x,y:raw.y},same.filter(o=>!o._bomb));
    const startY=stack*START_Y_SPACING+FLOOR_OFFSET+OBJ_LIFT;
    // フリップ判定（同拍カラーノーツちょうど2個）
    let flipY=0, flipStartX=wx;
    const colorNotes=same.filter(o=>!o._bomb);
    if(colorNotes.length===2){
      const other=colorNotes.find(o=>o!==same.find(s=>s.x===raw.x&&s.y===raw.y&&s.c===raw.c))||colorNotes.find(o=>!(o.x===raw.x&&o.y===raw.y));
      const partner=colorNotes.find(o=>o.c!==raw.c);
      if(partner){ const fh=flipHeights(raw,partner);
        flipY=fh; if(fh!==0){ const [ox]=gridPos(partner.x,partner.y); flipStartX=ox; } }
    }
    const grp=new THREE.Group();
    const box=new THREE.Mesh(g.note, raw.c===0?g.matRed:g.matBlue); grp.add(box);
    const mk=new THREE.Mesh(g.mark, raw.d===8?g.matDot:g.matArrow);   // PV1同様: 矢印/ドットのテクスチャ面
    mk.position.z=0.24; grp.add(mk); grp.userData.mark=mk;   // +Z=プレイヤー側の面。grpのZ回転でカット方向へ
    grp.userData.box=box;
    root.add(grp);
    const isDot=raw.d===8;
    objs.push({kind:'note', time:raw.beat*60/jp.bpm, grp,
      x:wx,y:wy,startY,angle,flipY,flipStartX,isDot,
      upd(){ noteFrame(this); }});
  }

  // --- ボム ---
  for(const raw of B){
    const [wx,wy]=gridPos(raw.x,raw.y);
    const same=byBeat.get(Math.round(raw.beat*1000)/1000)||[];
    const stack=startYStack({x:raw.x,y:raw.y},same.filter(o=>o._bomb||!o._bomb));
    const startY=stack*START_Y_SPACING+FLOOR_OFFSET+OBJ_LIFT;
    const m=new THREE.Mesh(g.bomb,g.matBomb); root.add(m);
    objs.push({kind:'bomb', time:raw.beat*60/jp.bpm, grp:m, x:wx,y:wy,startY,
      upd(){ bombFrame(this); }});
  }

  // --- 壁 ---
  for(const raw of W){
    const [wx,wy]=gridPos(raw.x, raw.y);
    const width=(raw.w||1)*LANE_W, height=Math.max(1,raw.h||1)*WALL_HSCALE;
    const durTime=(raw.dur||0)*60/jp.bpm;
    const geo=new THREE.BoxGeometry(width,height,1); geo.userData={own:true};
    const m=new THREE.Mesh(geo,g.matWall); root.add(m);
    const edges=new THREE.LineSegments(new THREE.EdgesGeometry(geo),new THREE.LineBasicMaterial({color:0xff5577,transparent:true,opacity:0.5}));
    m.add(edges);
    objs.push({kind:'wall', time:raw.beat*60/jp.bpm, grp:m,
      cx:GRID_X0+ (raw.x)*LANE_W + (width-LANE_W)/2, cyBase:(raw.y||0)*WALL_HSCALE, height, width, durTime,
      upd(){ wallFrame(this); }});
  }

  // --- チェーン（エディタと同一仕様: 頭=切り口が進行方向・本体は反対側 / リンク=頭→尾の角度補間＋●）---
  for(const ch of C){
    const [hx,hy]=gridPos(ch.x,ch.y), [tx,ty]=gridPos(ch.tx,ch.ty);
    // コンパス方位（上=0・時計回り）。DIR_ANGLESはBS本家=180-コンパスなので変換
    const thetaH=(ch.d===8)?0:180-(DIR_ANGLES[clamp(ch.d,0,8)]??0);
    const dur=(ch.tb??ch.b??ch.beat) - (ch.b??ch.beat);
    const beat0=ch.b??ch.beat;
    const col=ch.c===0?g.matRed:g.matBlue;
    const { links }=chainLinkLayout(ch, hx, hy, tx, ty);
    const pushChainPart=(grp,beat,x,y,isDot,angle)=>{
      root.add(grp);
      objs.push({kind:'note', time:beat*60/jp.bpm, grp, x,y,
        startY:FLOOR_OFFSET+OBJ_LIFT, angle, flipY:0, flipStartX:x, isDot,
        upd(){ noteFrame(this); }});
    };
    const NOTE_MARK_RATIO=0.4/0.46;
    const CHAIN_HEAD_LIFT=CHAIN_HEAD_SIZE.h/2;
    const chainMark=(size,s2=1,isArrow=false)=>{
      if(isArrow&&s2===1) return { faceScale:1, markZ:0.235, aspect:1, markY:CHAIN_HEAD_LIFT, useHeadMark:true };
      const face=Math.min(size.w,size.h)*NOTE_MARK_RATIO*s2;
      return { faceScale:face/0.4, markZ:size.d*0.5*1.02, aspect:1, markY:0, useHeadMark:false };
    };
    const makePart=(geo,markMat,size,s2=1,isArrow=false,bothFaces=false)=>{
      const grp=new THREE.Group();
      const box=new THREE.Mesh(geo,col);
      if(s2!==1) box.scale.set(s2,s2,1);
      if(isArrow&&s2===1) box.position.y=CHAIN_HEAD_LIFT;
      grp.add(box);
      const {faceScale,markZ,aspect,markY=0,useHeadMark}=chainMark(size,s2,isArrow);
      const markGeo=useHeadMark?g.chainHeadMark:g.mark;
      const mk=new THREE.Mesh(markGeo,markMat);
      mk.position.set(0,markY,markZ);
      mk.scale.set(faceScale,isArrow&&!useHeadMark?faceScale*aspect:faceScale,1);
      if(isArrow) mk.rotation.set(0,Math.PI,0);
      grp.add(mk);
      if(bothFaces){
        const mk2=new THREE.Mesh(markGeo,markMat);
        mk2.position.set(0,markY,-markZ);
        if(isArrow) mk2.rotation.set(0,0,0);
        mk2.scale.set(faceScale,isArrow&&!useHeadMark?faceScale*aspect:faceScale,1);
        grp.add(mk2);
      }
      return grp;
    };
    { // 頭: エディタ基準図と同一。切り口(平面側)=セル中心が進行方向を向き、本体・面取りは反対側。
      //    grpは回転させず(角度0)、箱とマークへ直接適用（grp回転は箱で符号が逆に見える＋矢印が両面とも裏向きになるため）
      const headGrp=new THREE.Group();
      const thr=thetaH*Math.PI/180;
      const hbox=new THREE.Mesh(g.chainHead,col);
      if(ch.d!==8){
        hbox.rotation.z=-THREE.MathUtils.degToRad(thetaH+180);   // 出現CCW=+rotZ → 面取りコンパス=-rotZ=θ+180（本体=進行方向の後ろ）
        hbox.position.set(-Math.sin(thr)*CHAIN_HEAD_LIFT, -Math.cos(thr)*CHAIN_HEAD_LIFT, 0);   // 切り口=セル中心
      }
      headGrp.add(hbox);
      const hmk=new THREE.Mesh(ch.d===8?g.mark:g.chainHeadMark, ch.d===8?g.matDot:g.matChainHeadArrow);
      hmk.position.set(hbox.position.x, hbox.position.y, 0.235);   // カメラ側(+Z)に表示（旧実装は両面とも裏向きで矢印が見えなかった）
      hmk.rotation.z=-thr;   // 矢印apexコンパス=-rotZ=θ=進行方向
      headGrp.add(hmk);
      pushChainPart(headGrp, beat0, hx, hy, ch.d===8, 0);
    }
    for(const lk of links){
      const lb=beat0+dur*lk.t;
      pushChainPart(makePart(g.chainLink, g.matDot, CHAIN_LINK_SIZE, 1, false, true),   // リンクは実機同様の均一サイズ
        lb, lk.lx, lk.ly, true, lk.ang);   // 接線角（実機式。頭→尾補間は廃止＝ヘルバ様決定）
    }
  }

  // --- アーク（3次ベジェのチューブ）---
  for(const a of A){
    const b0=a.b??a.beat, tb=a.tb??b0;
    const [hx,hy]=gridPos(a.x,a.y), [tx,ty]=gridPos(a.tx,a.ty);
    const hAng=objAngle(a.d,0), tAng=objAngle(a.tc,0);
    const hoff=a.d===8?[0,0]:dirVec(hAng), toff=a.tc===8?[0,0]:dirVec(tAng);
    const CO=2.5;
    const hcx=hx+hoff[0]*(a.mu??1)*CO, hcy=hy+hoff[1]*(a.mu??1)*CO;
    const tcx=tx-toff[0]*(a.tmu??1)*CO, tcy=ty-toff[1]*(a.tmu??1)*CO;
    const durTime=(tb-b0)*60/jp.bpm;
    const length=durTime*jp.njs*CHART_STRETCH;            // z長（生成時のNJS基準）×譜面ストレッチ
    const p0=new THREE.Vector3(hx,hy,0), p1=new THREE.Vector3(hcx,hcy,0);
    const p2=new THREE.Vector3(tcx,tcy,length), p3=new THREE.Vector3(tx,ty,length);
    const cnt=clamp(Math.floor(60*durTime)+1,30,300);
    const pts=[];
    for(let i=0;i<cnt;i++){ let t=i/(cnt-1); t=easeQuadInOut(t);
      const it=1-t;
      pts.push(new THREE.Vector3(
        it*it*it*p0.x+3*it*it*t*p1.x+3*it*t*t*p2.x+t*t*t*p3.x,
        it*it*it*p0.y+3*it*it*t*p1.y+3*it*t*t*p2.y+t*t*t*p3.y,
        it*it*it*p0.z+3*it*it*t*p1.z+3*it*t*t*p2.z+t*t*t*p3.z)); }
    const curve=new THREE.CatmullRomCurve3(pts);
    const geo=new THREE.TubeGeometry(curve,Math.min(cnt,120),0.045,6,false); geo.userData={own:true};
    // Zを反転してから格納（root配下は全部 threeZ=-unityZ で描く）
    const posAttr=geo.attributes.position; for(let i=0;i<posAttr.count;i++) posAttr.setZ(i,-posAttr.getZ(i)); posAttr.needsUpdate=true; geo.computeVertexNormals();
    const m=new THREE.Mesh(geo, a.c===0?g.matArcR:g.matArcB); m.userData.own=true; root.add(m);
    objs.push({kind:'arc', time:b0*60/jp.bpm, grp:m,
      upd(){ arcFrame(this); }});
  }
}

// フリップ高さ（§7.3）
function flipHeights(first,partner){
  const OVER=0.45, UNDER=-0.15;
  if(first.c===partner.c) return 0;
  // firstが交差側か（赤は右側/青は左側にいると交差）
  if((first.c===0&&first.x<=partner.x)||(first.c===1&&first.x>=partner.x)) return 0;
  if(first.c===0) return first.y<partner.y?UNDER:OVER;
  return first.y>partner.y?OVER:UNDER;
}

// ===================== 毎フレーム更新 =====================
function noteFrame(o){
  const {njs,rt,hjd}=jp;
  const z=getZ(o.time,njs,rt,hjd);
  const jumpTime=curSec+rt;
  const jumpProgress=(jumpTime-o.time)/rt;                // 0=ジャンプイン,1=カット面
  let x=o.x, y=o.y+getYoffZero(); // playerHeightOffset=0
  // Y放物線
  y=getObjectY(o.startY,o.y,z,hjd,o.time,rt);
  // フリップ
  if(o.flipY!==0){
    if(jumpProgress<=0) x=o.flipStartX;
    else if(jumpProgress<0.5){
      x=lerp(o.flipStartX,o.x,easeQuadInOut(jumpProgress/0.5));
      y+=o.flipY*(0.5-Math.cos(jumpProgress*Math.PI*4)/2);
    }
  }
  o.grp.position.set(x,y,-z*CHART_STRETCH);
  // 回転スナップイン（Z軸・反転符号）
  let ang=o.angle;
  if(jumpProgress<=0) ang=0;
  else if(jumpProgress<ROT_ANIM_TIME) ang*=easeSineOut(jumpProgress/ROT_ANIM_TIME);
  o.grp.rotation.z=-ang*Math.PI/180;                      // threeZ反転に伴い角度反転
}
function bombFrame(o){
  const {njs,rt,hjd}=jp;
  const z=getZ(o.time,njs,rt,hjd);
  const y=getObjectY(o.startY,o.y,z,hjd,o.time,rt);
  o.grp.position.set(o.x,y,-z*CHART_STRETCH);
}
function wallFrame(o){
  const {njs,rt,hjd}=jp;
  const wallLength=Math.max(0.06,o.durTime*njs)*CHART_STRETCH;
  const frontZ=getZ(o.time,njs,rt,hjd)*CHART_STRETCH-0.25;
  const centerZ=frontZ+wallLength/2;
  o.grp.scale.z=wallLength;
  o.grp.position.set(o.cx, o.cyBase+o.height/2, -centerZ);
}
function arcFrame(o){
  const {njs,rt,hjd}=jp;
  const z=getZ(o.time,njs,rt,hjd);
  o.grp.position.set(0,0,-z*CHART_STRETCH);               // 形状固定・Z平行移動（NJS等速ぶん）×譜面ストレッチ
}
const lerp=(a,b,t)=>a+(b-a)*t;
const getYoffZero=()=>0;

// ===================== フレーム駆動・カリング =====================
export function frame(sec,playing){
  if(!active||!renderer) return;
  if(!(playing||_dirty||sec!==_lastSec)) return;   // ①停止中で無変化＝同じ絵→フルパイプライン(9〜10パス)を丸ごとスキップ
  curSec=sec;
  const spawnAhead=jp.rt+MOVE_TIME;                       // これより先はまだ出さない
  const despawn=BEHIND_CAM_TIME;                          // 通過後1秒まで残す
  try{
  for(const o of objs){
    const dt=o.time-curSec;
    // 継続系(壁/アーク)は緩め、ノーツ/ボムは範囲外で隠す
    let show = (o.kind==='wall'||o.kind==='arc')
      ? (dt<=spawnAhead+8 && dt>despawn-8)
      : (dt<=spawnAhead && dt>despawn);
    if(show){ o.grp.visible=true; o.upd(); }
    else o.grp.visible=false;
  }
  updateLights();
  }catch(e){ if(!frame._e){ frame._e=1; console.error('[v2dbg] frame描画エラー(以後省略):',e); } }   // ★診断: 配置時に毎フレーム例外→描画止まりで環境が消える説
  try{ renderBloomfog(); }catch(e){ if(!frame._be){ frame._be=1; console.error('[bloomfog]',e); } }   // 構造物へのライト反射
  if(composer) composer.render(); else renderer.render(scene,camera);
  _lastSec=sec; _dirty=false; _renderCount++;   // ①この時刻/状態は描画済み
}

export function dispose(){
  removeEventListener('resize',resize);
  clearObjs();
  if(renderer){ renderer.dispose(); renderer.domElement.remove(); renderer=null; }
  scene=null; camera=null; active=false;
}

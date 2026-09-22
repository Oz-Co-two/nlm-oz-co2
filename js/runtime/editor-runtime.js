/**
 * EditorRuntimeHelpers
 * RUNTIME HELPERS — shared utilities not yet domain-owned
 *
 * Object API for this domain. Methods forward to the editor runtime closure
 * (shared `let` state lives there for behavior fidelity).
 */
export class EditorRuntimeHelpers {
  /** @param {object} rt editor runtime from createEditorRuntime() */
  constructor(rt) {
    this.rt = rt;
  }

  /** Method names owned by this domain (for install / introspection). */
  static get methodNames() {
    return [
    '_diffApplyLive',
    '_flacPic',
    '_id3Pic',
    '_mp4FindAtom',
    '_mp4Pic',
    '_oggPic',
    '_parseFlacPic',
    '_rawX',
    '_rd32be',
    '_sniffMime',
    'addLibItem',
    'addMarker',
    'addMarkerAt',
    'addSongLine',
    'addSrcNode',
    'allNodeIds',
    'altAt',
    'applyArtwork',
    'applyHandleDrag',
    'axisParam',
    'blobToDataURL',
    'buildDefaultGraph',
    'cancelLayerPaste',
    'cellPos',
    'clipAtLayer',
    'clipEdgeAt',
    'clipRangeAt',
    'clipRef',
    'clipTrackForBeat',
    'closeFileMenu',
    'closeFloatUI',
    'closePie',
    'commitLayerPaste',
    'connectedNodeId',
    'copySel3D',
    'copySelNode',
    'createArc',
    'createChain',
    'createExtra',
    'crispVLine',
    'dataURLToBlob',
    'defaultFresh',
    'deleteAssetClip',
    'deleteLayerSel',
    'deleteMultiSel',
    'deleteMusic',
    'deleteSelNode',
    'deleteSrcNode',
    'diffColOf',
    'diffCountsOf',
    'diffIsCurrent',
    'diffOptOf',
    'diffStoreOf',
    'dispDiff',
    'drawBand',
    'dupJumpItem',
    'edgeHit',
    'editExtraNode',
    'endHandleDrag',
    'ensureDiffSelect',
    'ensureDupPool',
    'ensureGraphIO',
    'ensureLens',
    'ensureNodeIds',
    'ensureSelPool',
    'estimateBPM',
    'extraAt',
    'floorColBeat',
    'fmt',
    'fragFromContent',
    'getSongOff',
    'handleUsable',
    'headBeat',
    'hexA',
    'hideMenu',
    'hsv2rgb',
    'hueOf',
    'inNullRange',
    'inRegion',
    'ioAt',
    'jumpMarker',
    'lBeatToX',
    'loadCoverPreview',
    'loadLineDiff',
    'loadSongFromItem',
    'lPPB',
    'lXToBeat',
    'mainPos',
    'makeChainHeadGeo',
    'makeChainLinkGeo',
    'makeTex',
    'mat',
    'movables',
    'msegs',
    'ndFromScreen',
    'ndInlineEdit',
    'ndToScreen',
    'njsOffCur',
    'nodeAt',
    'nodeExtraH',
    'nodeGeomOf',
    'nodeRowsFor',
    'noteSwSvg',
    'noteTrackForBeat',
    'numSprTex',
    'openCoverFile',
    'openDiffMenu',
    'openPie',
    'pasteNode',
    'pasteSel3D',
    'pickOutFolder',
    'pickStripCol',
    'placeClipLine',
    'portHit',
    'portPosOf',
    'portPosW',
    'prResize',
    'prSeekTo',
    'pvFillEnvSel',
    'pvFinderVis',
    'quickSetNode',
    'readinessHTML',
    'refreshCoverB64',
    'refreshHoverVisuals',
    'refreshPal',
    'removeNodeMerge',
    'removeObjMesh',
    'renameAssetClip',
    'renderOutCards',
    'resetDiffSections',
    'resizeAt',
    'restoreCoversFromB64',
    'restoreLineAssets',
    'rgb2hsv',
    'rippleSection',
    'rotStep',
    'roundRectND',
    'rowOf',
    'sanitizeFolderName',
    'saveClipToAsset',
    'scanDups',
    'screenPosOf',
    'scrOf',
    'secAtPr',
    'secLk',
    'seekEase',
    'selKey',
    'setBPMv',
    'setBrushType',
    'setColor',
    'setFollowGhost',
    'setLibLabel',
    'setNdView',
    'setNjsCur',
    'setPtr',
    'setScr',
    'setSnap',
    'shiftMusicSelBeat',
    'shiftSelLayersBeat',
    'showMenu',
    'songAt',
    'srcCardHTML',
    'srcNjsOf',
    'startHandleDrag',
    'startLayerPaste',
    'stopS',
    'stripColOf',
    'syncLaneSb',
    'syncPlayIcons',
    'syncPos',
    'timelineEndBeat',
    'timelineSections',
    'toggleLaneState',
    'togglePanel',
    'toggleSizeMode',
    'updateColorBtn',
    'updateCoverThumb',
    'updateDirBtn',
    'updateGizmo',
    'updateLayerPaste',
    'updateLibCatSel',
    'viewBeat',
    'wallDims',
    'wallSpan'
    ];
  }

  _diffApplyLive(...args) { return this.rt._diffApplyLive(...args); }
  _flacPic(...args) { return this.rt._flacPic(...args); }
  _id3Pic(...args) { return this.rt._id3Pic(...args); }
  _mp4FindAtom(...args) { return this.rt._mp4FindAtom(...args); }
  _mp4Pic(...args) { return this.rt._mp4Pic(...args); }
  _oggPic(...args) { return this.rt._oggPic(...args); }
  _parseFlacPic(...args) { return this.rt._parseFlacPic(...args); }
  _rawX(...args) { return this.rt._rawX(...args); }
  _rd32be(...args) { return this.rt._rd32be(...args); }
  _sniffMime(...args) { return this.rt._sniffMime(...args); }
  addLibItem(...args) { return this.rt.addLibItem(...args); }
  addMarker(...args) { return this.rt.addMarker(...args); }
  addMarkerAt(...args) { return this.rt.addMarkerAt(...args); }
  addSongLine(...args) { return this.rt.addSongLine(...args); }
  addSrcNode(...args) { return this.rt.addSrcNode(...args); }
  allNodeIds(...args) { return this.rt.allNodeIds(...args); }
  altAt(...args) { return this.rt.altAt(...args); }
  applyArtwork(...args) { return this.rt.applyArtwork(...args); }
  applyHandleDrag(...args) { return this.rt.applyHandleDrag(...args); }
  axisParam(...args) { return this.rt.axisParam(...args); }
  blobToDataURL(...args) { return this.rt.blobToDataURL(...args); }
  buildDefaultGraph(...args) { return this.rt.buildDefaultGraph(...args); }
  cancelLayerPaste(...args) { return this.rt.cancelLayerPaste(...args); }
  cellPos(...args) { return this.rt.cellPos(...args); }
  clipAtLayer(...args) { return this.rt.clipAtLayer(...args); }
  clipEdgeAt(...args) { return this.rt.clipEdgeAt(...args); }
  clipRangeAt(...args) { return this.rt.clipRangeAt(...args); }
  clipRef(...args) { return this.rt.clipRef(...args); }
  clipTrackForBeat(...args) { return this.rt.clipTrackForBeat(...args); }
  closeFileMenu(...args) { return this.rt.closeFileMenu(...args); }
  closeFloatUI(...args) { return this.rt.closeFloatUI(...args); }
  closePie(...args) { return this.rt.closePie(...args); }
  commitLayerPaste(...args) { return this.rt.commitLayerPaste(...args); }
  connectedNodeId(...args) { return this.rt.connectedNodeId(...args); }
  copySel3D(...args) { return this.rt.copySel3D(...args); }
  copySelNode(...args) { return this.rt.copySelNode(...args); }
  createArc(...args) { return this.rt.createArc(...args); }
  createChain(...args) { return this.rt.createChain(...args); }
  createExtra(...args) { return this.rt.createExtra(...args); }
  crispVLine(...args) { return this.rt.crispVLine(...args); }
  dataURLToBlob(...args) { return this.rt.dataURLToBlob(...args); }
  defaultFresh(...args) { return this.rt.defaultFresh(...args); }
  deleteAssetClip(...args) { return this.rt.deleteAssetClip(...args); }
  deleteLayerSel(...args) { return this.rt.deleteLayerSel(...args); }
  deleteMultiSel(...args) { return this.rt.deleteMultiSel(...args); }
  deleteMusic(...args) { return this.rt.deleteMusic(...args); }
  deleteSelNode(...args) { return this.rt.deleteSelNode(...args); }
  deleteSrcNode(...args) { return this.rt.deleteSrcNode(...args); }
  diffColOf(...args) { return this.rt.diffColOf(...args); }
  diffCountsOf(...args) { return this.rt.diffCountsOf(...args); }
  diffIsCurrent(...args) { return this.rt.diffIsCurrent(...args); }
  diffOptOf(...args) { return this.rt.diffOptOf(...args); }
  diffStoreOf(...args) { return this.rt.diffStoreOf(...args); }
  dispDiff(...args) { return this.rt.dispDiff(...args); }
  drawBand(...args) { return this.rt.drawBand(...args); }
  dupJumpItem(...args) { return this.rt.dupJumpItem(...args); }
  edgeHit(...args) { return this.rt.edgeHit(...args); }
  editExtraNode(...args) { return this.rt.editExtraNode(...args); }
  endHandleDrag(...args) { return this.rt.endHandleDrag(...args); }
  ensureDiffSelect(...args) { return this.rt.ensureDiffSelect(...args); }
  ensureDupPool(...args) { return this.rt.ensureDupPool(...args); }
  ensureGraphIO(...args) { return this.rt.ensureGraphIO(...args); }
  ensureLens(...args) { return this.rt.ensureLens(...args); }
  ensureNodeIds(...args) { return this.rt.ensureNodeIds(...args); }
  ensureSelPool(...args) { return this.rt.ensureSelPool(...args); }
  estimateBPM(...args) { return this.rt.estimateBPM(...args); }
  extraAt(...args) { return this.rt.extraAt(...args); }
  floorColBeat(...args) { return this.rt.floorColBeat(...args); }
  fmt(...args) { return this.rt.fmt(...args); }
  fragFromContent(...args) { return this.rt.fragFromContent(...args); }
  getSongOff(...args) { return this.rt.getSongOff(...args); }
  handleUsable(...args) { return this.rt.handleUsable(...args); }
  headBeat(...args) { return this.rt.headBeat(...args); }
  hexA(...args) { return this.rt.hexA(...args); }
  hideMenu(...args) { return this.rt.hideMenu(...args); }
  hsv2rgb(...args) { return this.rt.hsv2rgb(...args); }
  hueOf(...args) { return this.rt.hueOf(...args); }
  inNullRange(...args) { return this.rt.inNullRange(...args); }
  inRegion(...args) { return this.rt.inRegion(...args); }
  ioAt(...args) { return this.rt.ioAt(...args); }
  jumpMarker(...args) { return this.rt.jumpMarker(...args); }
  lBeatToX(...args) { return this.rt.lBeatToX(...args); }
  loadCoverPreview(...args) { return this.rt.loadCoverPreview(...args); }
  loadLineDiff(...args) { return this.rt.loadLineDiff(...args); }
  loadSongFromItem(...args) { return this.rt.loadSongFromItem(...args); }
  lPPB(...args) { return this.rt.lPPB(...args); }
  lXToBeat(...args) { return this.rt.lXToBeat(...args); }
  mainPos(...args) { return this.rt.mainPos(...args); }
  makeChainHeadGeo(...args) { return this.rt.makeChainHeadGeo(...args); }
  makeChainLinkGeo(...args) { return this.rt.makeChainLinkGeo(...args); }
  makeTex(...args) { return this.rt.makeTex(...args); }
  mat(...args) { return this.rt.mat(...args); }
  movables(...args) { return this.rt.movables(...args); }
  msegs(...args) { return this.rt.msegs(...args); }
  ndFromScreen(...args) { return this.rt.ndFromScreen(...args); }
  ndInlineEdit(...args) { return this.rt.ndInlineEdit(...args); }
  ndToScreen(...args) { return this.rt.ndToScreen(...args); }
  njsOffCur(...args) { return this.rt.njsOffCur(...args); }
  nodeAt(...args) { return this.rt.nodeAt(...args); }
  nodeExtraH(...args) { return this.rt.nodeExtraH(...args); }
  nodeGeomOf(...args) { return this.rt.nodeGeomOf(...args); }
  nodeRowsFor(...args) { return this.rt.nodeRowsFor(...args); }
  noteSwSvg(...args) { return this.rt.noteSwSvg(...args); }
  noteTrackForBeat(...args) { return this.rt.noteTrackForBeat(...args); }
  numSprTex(...args) { return this.rt.numSprTex(...args); }
  openCoverFile(...args) { return this.rt.openCoverFile(...args); }
  openDiffMenu(...args) { return this.rt.openDiffMenu(...args); }
  openPie(...args) { return this.rt.openPie(...args); }
  pasteNode(...args) { return this.rt.pasteNode(...args); }
  pasteSel3D(...args) { return this.rt.pasteSel3D(...args); }
  pickOutFolder(...args) { return this.rt.pickOutFolder(...args); }
  pickStripCol(...args) { return this.rt.pickStripCol(...args); }
  placeClipLine(...args) { return this.rt.placeClipLine(...args); }
  portHit(...args) { return this.rt.portHit(...args); }
  portPosOf(...args) { return this.rt.portPosOf(...args); }
  portPosW(...args) { return this.rt.portPosW(...args); }
  prResize(...args) { return this.rt.prResize(...args); }
  prSeekTo(...args) { return this.rt.prSeekTo(...args); }
  pvFillEnvSel(...args) { return this.rt.pvFillEnvSel(...args); }
  pvFinderVis(...args) { return this.rt.pvFinderVis(...args); }
  quickSetNode(...args) { return this.rt.quickSetNode(...args); }
  readinessHTML(...args) { return this.rt.readinessHTML(...args); }
  refreshCoverB64(...args) { return this.rt.refreshCoverB64(...args); }
  refreshHoverVisuals(...args) { return this.rt.refreshHoverVisuals(...args); }
  refreshPal(...args) { return this.rt.refreshPal(...args); }
  removeNodeMerge(...args) { return this.rt.removeNodeMerge(...args); }
  removeObjMesh(...args) { return this.rt.removeObjMesh(...args); }
  renameAssetClip(...args) { return this.rt.renameAssetClip(...args); }
  renderOutCards(...args) { return this.rt.renderOutCards(...args); }
  resetDiffSections(...args) { return this.rt.resetDiffSections(...args); }
  resizeAt(...args) { return this.rt.resizeAt(...args); }
  restoreCoversFromB64(...args) { return this.rt.restoreCoversFromB64(...args); }
  restoreLineAssets(...args) { return this.rt.restoreLineAssets(...args); }
  rgb2hsv(...args) { return this.rt.rgb2hsv(...args); }
  rippleSection(...args) { return this.rt.rippleSection(...args); }
  rotStep(...args) { return this.rt.rotStep(...args); }
  roundRectND(...args) { return this.rt.roundRectND(...args); }
  rowOf(...args) { return this.rt.rowOf(...args); }
  sanitizeFolderName(...args) { return this.rt.sanitizeFolderName(...args); }
  saveClipToAsset(...args) { return this.rt.saveClipToAsset(...args); }
  scanDups(...args) { return this.rt.scanDups(...args); }
  screenPosOf(...args) { return this.rt.screenPosOf(...args); }
  scrOf(...args) { return this.rt.scrOf(...args); }
  secAtPr(...args) { return this.rt.secAtPr(...args); }
  secLk(...args) { return this.rt.secLk(...args); }
  seekEase(...args) { return this.rt.seekEase(...args); }
  selKey(...args) { return this.rt.selKey(...args); }
  setBPMv(...args) { return this.rt.setBPMv(...args); }
  setBrushType(...args) { return this.rt.setBrushType(...args); }
  setColor(...args) { return this.rt.setColor(...args); }
  setFollowGhost(...args) { return this.rt.setFollowGhost(...args); }
  setLibLabel(...args) { return this.rt.setLibLabel(...args); }
  setNdView(...args) { return this.rt.setNdView(...args); }
  setNjsCur(...args) { return this.rt.setNjsCur(...args); }
  setPtr(...args) { return this.rt.setPtr(...args); }
  setScr(...args) { return this.rt.setScr(...args); }
  setSnap(...args) { return this.rt.setSnap(...args); }
  shiftMusicSelBeat(...args) { return this.rt.shiftMusicSelBeat(...args); }
  shiftSelLayersBeat(...args) { return this.rt.shiftSelLayersBeat(...args); }
  showMenu(...args) { return this.rt.showMenu(...args); }
  songAt(...args) { return this.rt.songAt(...args); }
  srcCardHTML(...args) { return this.rt.srcCardHTML(...args); }
  srcNjsOf(...args) { return this.rt.srcNjsOf(...args); }
  startHandleDrag(...args) { return this.rt.startHandleDrag(...args); }
  startLayerPaste(...args) { return this.rt.startLayerPaste(...args); }
  stopS(...args) { return this.rt.stopS(...args); }
  stripColOf(...args) { return this.rt.stripColOf(...args); }
  syncLaneSb(...args) { return this.rt.syncLaneSb(...args); }
  syncPlayIcons(...args) { return this.rt.syncPlayIcons(...args); }
  syncPos(...args) { return this.rt.syncPos(...args); }
  timelineEndBeat(...args) { return this.rt.timelineEndBeat(...args); }
  timelineSections(...args) { return this.rt.timelineSections(...args); }
  toggleLaneState(...args) { return this.rt.toggleLaneState(...args); }
  togglePanel(...args) { return this.rt.togglePanel(...args); }
  toggleSizeMode(...args) { return this.rt.toggleSizeMode(...args); }
  updateColorBtn(...args) { return this.rt.updateColorBtn(...args); }
  updateCoverThumb(...args) { return this.rt.updateCoverThumb(...args); }
  updateDirBtn(...args) { return this.rt.updateDirBtn(...args); }
  updateGizmo(...args) { return this.rt.updateGizmo(...args); }
  updateLayerPaste(...args) { return this.rt.updateLayerPaste(...args); }
  updateLibCatSel(...args) { return this.rt.updateLibCatSel(...args); }
  viewBeat(...args) { return this.rt.viewBeat(...args); }
  wallDims(...args) { return this.rt.wallDims(...args); }
  wallSpan(...args) { return this.rt.wallSpan(...args); }
}

/** Register domain object on `rt.modules.helpers` and bind live impls. */
export function installEditorRuntimeHelpers(rt) {
  const inst = new EditorRuntimeHelpers(rt);
  rt.modules = rt.modules || {};
  rt.modules.helpers = inst;
  for (const name of EditorRuntimeHelpers.methodNames) {
    if (typeof rt[name] === 'function') inst[name] = rt[name];
  }
  return inst;
}

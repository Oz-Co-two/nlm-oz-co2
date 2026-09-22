/**
 * NlePanel
 * NLE — layers / music timeline / markers / lanes
 *
 * Object API for this domain. Methods forward to the editor runtime closure
 * (shared `let` state lives there for behavior fidelity).
 */
export class NlePanel {
  /** @param {object} rt editor runtime from createEditorRuntime() */
  constructor(rt) {
    this.rt = rt;
  }

  /** Method names owned by this domain (for install / introspection). */
  static get methodNames() {
    return [
    'compileLayersToFlat',
    'createFullSongClip',
    'cutClipAtMarkers',
    'cutMusicAt',
    'drawLayers',
    'drawOverview',
    'drawPRoll',
    'flushFlatEdits',
    'laneAdd',
    'laneAtY',
    'laneCount',
    'laneCountOf',
    'laneDefN',
    'laneHt',
    'laneLabel',
    'laneMaxScroll',
    'laneOverlaps',
    'laneRemove',
    'laneShiftAll',
    'laneTex',
    'laneTopOf',
    'laneVP',
    'laneY',
    'layerFit',
    'layerPasteFit',
    'markerMenuTop',
    'mergeLayerSel',
    'mergeMusicSel',
    'musicHit',
    'ndResize',
    'ovResize',
    'packLanes',
    'phRect',
    'sectionRange',
    'splitSectionAt',
    'syncFlatToSections',
    'tlEnd',
    'tlScrub',
    'tlWindow',
    'tlZoom'
    ];
  }

  compileLayersToFlat(...args) { return this.rt.compileLayersToFlat(...args); }
  createFullSongClip(...args) { return this.rt.createFullSongClip(...args); }
  cutClipAtMarkers(...args) { return this.rt.cutClipAtMarkers(...args); }
  cutMusicAt(...args) { return this.rt.cutMusicAt(...args); }
  drawLayers(...args) { return this.rt.drawLayers(...args); }
  drawOverview(...args) { return this.rt.drawOverview(...args); }
  drawPRoll(...args) { return this.rt.drawPRoll(...args); }
  flushFlatEdits(...args) { return this.rt.flushFlatEdits(...args); }
  laneAdd(...args) { return this.rt.laneAdd(...args); }
  laneAtY(...args) { return this.rt.laneAtY(...args); }
  laneCount(...args) { return this.rt.laneCount(...args); }
  laneCountOf(...args) { return this.rt.laneCountOf(...args); }
  laneDefN(...args) { return this.rt.laneDefN(...args); }
  laneHt(...args) { return this.rt.laneHt(...args); }
  laneLabel(...args) { return this.rt.laneLabel(...args); }
  laneMaxScroll(...args) { return this.rt.laneMaxScroll(...args); }
  laneOverlaps(...args) { return this.rt.laneOverlaps(...args); }
  laneRemove(...args) { return this.rt.laneRemove(...args); }
  laneShiftAll(...args) { return this.rt.laneShiftAll(...args); }
  laneTex(...args) { return this.rt.laneTex(...args); }
  laneTopOf(...args) { return this.rt.laneTopOf(...args); }
  laneVP(...args) { return this.rt.laneVP(...args); }
  laneY(...args) { return this.rt.laneY(...args); }
  layerFit(...args) { return this.rt.layerFit(...args); }
  layerPasteFit(...args) { return this.rt.layerPasteFit(...args); }
  markerMenuTop(...args) { return this.rt.markerMenuTop(...args); }
  mergeLayerSel(...args) { return this.rt.mergeLayerSel(...args); }
  mergeMusicSel(...args) { return this.rt.mergeMusicSel(...args); }
  musicHit(...args) { return this.rt.musicHit(...args); }
  ndResize(...args) { return this.rt.ndResize(...args); }
  ovResize(...args) { return this.rt.ovResize(...args); }
  packLanes(...args) { return this.rt.packLanes(...args); }
  phRect(...args) { return this.rt.phRect(...args); }
  sectionRange(...args) { return this.rt.sectionRange(...args); }
  splitSectionAt(...args) { return this.rt.splitSectionAt(...args); }
  syncFlatToSections(...args) { return this.rt.syncFlatToSections(...args); }
  tlEnd(...args) { return this.rt.tlEnd(...args); }
  tlScrub(...args) { return this.rt.tlScrub(...args); }
  tlWindow(...args) { return this.rt.tlWindow(...args); }
  tlZoom(...args) { return this.rt.tlZoom(...args); }
}

/** Register domain object on `rt.modules.nle` and bind live impls. */
export function installNlePanel(rt) {
  const inst = new NlePanel(rt);
  rt.modules = rt.modules || {};
  rt.modules.nle = inst;
  for (const name of NlePanel.methodNames) {
    if (typeof rt[name] === 'function') inst[name] = rt[name];
  }
  return inst;
}

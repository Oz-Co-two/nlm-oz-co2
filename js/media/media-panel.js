/**
 * MediaPanel
 * MEDIA — library browser / drag-drop / artwork
 *
 * Object API for this domain. Methods forward to the editor runtime closure
 * (shared `let` state lives there for behavior fidelity).
 */
export class MediaPanel {
  /** @param {object} rt editor runtime from createEditorRuntime() */
  constructor(rt) {
    this.rt = rt;
  }

  /** Method names owned by this domain (for install / introspection). */
  static get methodNames() {
    return [
    'applyLibFilter',
    'dropInfoNodesFromItem',
    'extractArtwork',
    'extractArtworkBatch',
    'getSongFile',
    'libDisp',
    'libLabels',
    'libMarkColors',
    'prepareMediaFrag',
    'prepareMediaWave',
    'renderLibList',
    'renderLibMark',
    'saveLibDirs',
    'scanAssetLibrary',
    'scanLibrary'
    ];
  }

  applyLibFilter(...args) { return this.rt.applyLibFilter(...args); }
  dropInfoNodesFromItem(...args) { return this.rt.dropInfoNodesFromItem(...args); }
  extractArtwork(...args) { return this.rt.extractArtwork(...args); }
  extractArtworkBatch(...args) { return this.rt.extractArtworkBatch(...args); }
  getSongFile(...args) { return this.rt.getSongFile(...args); }
  libDisp(...args) { return this.rt.libDisp(...args); }
  libLabels(...args) { return this.rt.libLabels(...args); }
  libMarkColors(...args) { return this.rt.libMarkColors(...args); }
  prepareMediaFrag(...args) { return this.rt.prepareMediaFrag(...args); }
  prepareMediaWave(...args) { return this.rt.prepareMediaWave(...args); }
  renderLibList(...args) { return this.rt.renderLibList(...args); }
  renderLibMark(...args) { return this.rt.renderLibMark(...args); }
  saveLibDirs(...args) { return this.rt.saveLibDirs(...args); }
  scanAssetLibrary(...args) { return this.rt.scanAssetLibrary(...args); }
  scanLibrary(...args) { return this.rt.scanLibrary(...args); }
}

/** Register domain object on `rt.modules.media` and bind live impls. */
export function installMediaPanel(rt) {
  const inst = new MediaPanel(rt);
  rt.modules = rt.modules || {};
  rt.modules.media = inst;
  for (const name of MediaPanel.methodNames) {
    if (typeof rt[name] === 'function') inst[name] = rt[name];
  }
  return inst;
}

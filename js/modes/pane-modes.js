/**
 * PaneModes
 * MODES — MEDIA/PREVIEW, NLE/INFO, NOTES/LIGHT
 *
 * Object API for this domain. Methods forward to the editor runtime closure
 * (shared `let` state lives there for behavior fidelity).
 */
export class PaneModes {
  /** @param {object} rt editor runtime from createEditorRuntime() */
  constructor(rt) {
    this.rt = rt;
  }

  /** Method names owned by this domain (for install / introspection). */
  static get methodNames() {
    return [
    'applyModeDim',
    'renderMetaList',
    'renderModeKeys',
    'setModeLabel',
    'setNodeColMode',
    'setNodeMode',
    'setPvMode',
    'setPvShowAmbient',
    'setPvShowStruct',
    'updateMainModeLabel'
    ];
  }

  applyModeDim(...args) { return this.rt.applyModeDim(...args); }
  renderMetaList(...args) { return this.rt.renderMetaList(...args); }
  renderModeKeys(...args) { return this.rt.renderModeKeys(...args); }
  setModeLabel(...args) { return this.rt.setModeLabel(...args); }
  setNodeColMode(...args) { return this.rt.setNodeColMode(...args); }
  setNodeMode(...args) { return this.rt.setNodeMode(...args); }
  setPvMode(...args) { return this.rt.setPvMode(...args); }
  setPvShowAmbient(...args) { return this.rt.setPvShowAmbient(...args); }
  setPvShowStruct(...args) { return this.rt.setPvShowStruct(...args); }
  updateMainModeLabel(...args) { return this.rt.updateMainModeLabel(...args); }
}

/** Register domain object on `rt.modules.modes` and bind live impls. */
export function installPaneModes(rt) {
  const inst = new PaneModes(rt);
  rt.modules = rt.modules || {};
  rt.modules.modes = inst;
  for (const name of PaneModes.methodNames) {
    if (typeof rt[name] === 'function') inst[name] = rt[name];
  }
  return inst;
}

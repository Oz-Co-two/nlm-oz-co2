/**
 * LightingEditor
 * LIGHTING — light events / chips / brush
 *
 * Object API for this domain. Methods forward to the editor runtime closure
 * (shared `let` state lives there for behavior fidelity).
 */
export class LightingEditor {
  /** @param {object} rt editor runtime from createEditorRuntime() */
  constructor(rt) {
    this.rt = rt;
  }

  /** Method names owned by this domain (for install / introspection). */
  static get methodNames() {
    return [
    'applyLightMove',
    'cancelLightMove',
    'chipColorOf',
    'chipEdges',
    'chipFootGeo',
    'chipKindOf',
    'chipNumOf',
    'chipRect',
    'deleteLightAt',
    'drawLightIco',
    'ensureChips',
    'flipLightColors',
    'hoverLightEvent',
    'laneKind',
    'laserBoostCols',
    'laserSwSvg',
    'lightDesc',
    'lightValue',
    'placeLight',
    'refreshLightHover',
    'setLightBehav',
    'setLightBehavSmart',
    'setLightColor',
    'setLightMode',
    'setPvShowLights',
    'updateLightUI'
    ];
  }

  applyLightMove(...args) { return this.rt.applyLightMove(...args); }
  cancelLightMove(...args) { return this.rt.cancelLightMove(...args); }
  chipColorOf(...args) { return this.rt.chipColorOf(...args); }
  chipEdges(...args) { return this.rt.chipEdges(...args); }
  chipFootGeo(...args) { return this.rt.chipFootGeo(...args); }
  chipKindOf(...args) { return this.rt.chipKindOf(...args); }
  chipNumOf(...args) { return this.rt.chipNumOf(...args); }
  chipRect(...args) { return this.rt.chipRect(...args); }
  deleteLightAt(...args) { return this.rt.deleteLightAt(...args); }
  drawLightIco(...args) { return this.rt.drawLightIco(...args); }
  ensureChips(...args) { return this.rt.ensureChips(...args); }
  flipLightColors(...args) { return this.rt.flipLightColors(...args); }
  hoverLightEvent(...args) { return this.rt.hoverLightEvent(...args); }
  laneKind(...args) { return this.rt.laneKind(...args); }
  laserBoostCols(...args) { return this.rt.laserBoostCols(...args); }
  laserSwSvg(...args) { return this.rt.laserSwSvg(...args); }
  lightDesc(...args) { return this.rt.lightDesc(...args); }
  lightValue(...args) { return this.rt.lightValue(...args); }
  placeLight(...args) { return this.rt.placeLight(...args); }
  refreshLightHover(...args) { return this.rt.refreshLightHover(...args); }
  setLightBehav(...args) { return this.rt.setLightBehav(...args); }
  setLightBehavSmart(...args) { return this.rt.setLightBehavSmart(...args); }
  setLightColor(...args) { return this.rt.setLightColor(...args); }
  setLightMode(...args) { return this.rt.setLightMode(...args); }
  setPvShowLights(...args) { return this.rt.setPvShowLights(...args); }
  updateLightUI(...args) { return this.rt.updateLightUI(...args); }
}

/** Register domain object on `rt.modules.lighting` and bind live impls. */
export function installLightingEditor(rt) {
  const inst = new LightingEditor(rt);
  rt.modules = rt.modules || {};
  rt.modules.lighting = inst;
  for (const name of LightingEditor.methodNames) {
    if (typeof rt[name] === 'function') inst[name] = rt[name];
  }
  return inst;
}

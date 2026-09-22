/**
 * InfoPanel
 * INFO — meta/set/cover/export graph
 *
 * Object API for this domain. Methods forward to the editor runtime closure
 * (shared `let` state lives there for behavior fidelity).
 */
export class InfoPanel {
  /** @param {object} rt editor runtime from createEditorRuntime() */
  constructor(rt) {
    this.rt = rt;
  }

  /** Method names owned by this domain (for install / introspection). */
  static get methodNames() {
    return [
    'addOutNode',
    'applyInfoChain',
    'applyInfoGraph',
    'defaultInfoGraph',
    'defInfoData',
    'deleteOutNode',
    'drawInfoEdges',
    'exportReadiness',
    'fillDiffSelectFromInfo',
    'infoAutoCenter',
    'infoCamApply',
    'infoCenterView',
    'infoChain',
    'infoNodeEls',
    'infoNodeT',
    'infoOutPortOf',
    'infoPortOf',
    'infoSelApply',
    'infoSnapBurst',
    'infoSnapshot',
    'infoWorldXY',
    'layoutInfoNodes',
    'refreshChartInfo',
    'refreshInfoCards',
    'refreshInspector',
    'refreshOutCards',
    'renderInfoCards',
    'sanitizeInfoGraph',
    'setActiveOut',
    'srcInfo'
    ];
  }

  addOutNode(...args) { return this.rt.addOutNode(...args); }
  applyInfoChain(...args) { return this.rt.applyInfoChain(...args); }
  applyInfoGraph(...args) { return this.rt.applyInfoGraph(...args); }
  defaultInfoGraph(...args) { return this.rt.defaultInfoGraph(...args); }
  defInfoData(...args) { return this.rt.defInfoData(...args); }
  deleteOutNode(...args) { return this.rt.deleteOutNode(...args); }
  drawInfoEdges(...args) { return this.rt.drawInfoEdges(...args); }
  exportReadiness(...args) { return this.rt.exportReadiness(...args); }
  fillDiffSelectFromInfo(...args) { return this.rt.fillDiffSelectFromInfo(...args); }
  infoAutoCenter(...args) { return this.rt.infoAutoCenter(...args); }
  infoCamApply(...args) { return this.rt.infoCamApply(...args); }
  infoCenterView(...args) { return this.rt.infoCenterView(...args); }
  infoChain(...args) { return this.rt.infoChain(...args); }
  infoNodeEls(...args) { return this.rt.infoNodeEls(...args); }
  infoNodeT(...args) { return this.rt.infoNodeT(...args); }
  infoOutPortOf(...args) { return this.rt.infoOutPortOf(...args); }
  infoPortOf(...args) { return this.rt.infoPortOf(...args); }
  infoSelApply(...args) { return this.rt.infoSelApply(...args); }
  infoSnapBurst(...args) { return this.rt.infoSnapBurst(...args); }
  infoSnapshot(...args) { return this.rt.infoSnapshot(...args); }
  infoWorldXY(...args) { return this.rt.infoWorldXY(...args); }
  layoutInfoNodes(...args) { return this.rt.layoutInfoNodes(...args); }
  refreshChartInfo(...args) { return this.rt.refreshChartInfo(...args); }
  refreshInfoCards(...args) { return this.rt.refreshInfoCards(...args); }
  refreshInspector(...args) { return this.rt.refreshInspector(...args); }
  refreshOutCards(...args) { return this.rt.refreshOutCards(...args); }
  renderInfoCards(...args) { return this.rt.renderInfoCards(...args); }
  sanitizeInfoGraph(...args) { return this.rt.sanitizeInfoGraph(...args); }
  setActiveOut(...args) { return this.rt.setActiveOut(...args); }
  srcInfo(...args) { return this.rt.srcInfo(...args); }
}

/** Register domain object on `rt.modules.info` and bind live impls. */
export function installInfoPanel(rt) {
  const inst = new InfoPanel(rt);
  rt.modules = rt.modules || {};
  rt.modules.info = inst;
  for (const name of InfoPanel.methodNames) {
    if (typeof rt[name] === 'function') inst[name] = rt[name];
  }
  return inst;
}

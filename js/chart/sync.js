/**
 * ChartSync
 * CHART SYNC — difficulties / flat↔sections
 *
 * Object API for this domain. Methods forward to the editor runtime closure
 * (shared `let` state lives there for behavior fidelity).
 */
export class ChartSync {
  /** @param {object} rt editor runtime from createEditorRuntime() */
  constructor(rt) {
    this.rt = rt;
  }

  /** Method names owned by this domain (for install / introspection). */
  static get methodNames() {
    return [
    'diffClear',
    'diffCopy',
    'loadDiff',
    'relinkDiffEdges',
    'renderDiffBar',
    'stashCurrentDiff',
    'switchDiffByIndex',
    'syncSetQuick'
    ];
  }

  diffClear(...args) { return this.rt.diffClear(...args); }
  diffCopy(...args) { return this.rt.diffCopy(...args); }
  loadDiff(...args) { return this.rt.loadDiff(...args); }
  relinkDiffEdges(...args) { return this.rt.relinkDiffEdges(...args); }
  renderDiffBar(...args) { return this.rt.renderDiffBar(...args); }
  stashCurrentDiff(...args) { return this.rt.stashCurrentDiff(...args); }
  switchDiffByIndex(...args) { return this.rt.switchDiffByIndex(...args); }
  syncSetQuick(...args) { return this.rt.syncSetQuick(...args); }
}

/** Register domain object on `rt.modules.sync` and bind live impls. */
export function installChartSync(rt) {
  const inst = new ChartSync(rt);
  rt.modules = rt.modules || {};
  rt.modules.sync = inst;
  for (const name of ChartSync.methodNames) {
    if (typeof rt[name] === 'function') inst[name] = rt[name];
  }
  return inst;
}

/**
 * GraphLegacy
 * LEGACY — old node-graph path (kept)
 *
 * Object API for this domain. Methods forward to the editor runtime closure
 * (shared `let` state lives there for behavior fidelity).
 */
export class GraphLegacy {
  /** @param {object} rt editor runtime from createEditorRuntime() */
  constructor(rt) {
    this.rt = rt;
  }

  /** Method names owned by this domain (for install / introspection). */
  static get methodNames() {
    return [
    'activateLine',
    'compileGraphToFlat',
    'ensureEdges',
    'graphOp',
    'newDefaultGraph',
    'sigConnected',
    'sigPath',
    'syncGraphFromFlat'
    ];
  }

  activateLine(...args) { return this.rt.activateLine(...args); }
  compileGraphToFlat(...args) { return this.rt.compileGraphToFlat(...args); }
  ensureEdges(...args) { return this.rt.ensureEdges(...args); }
  graphOp(...args) { return this.rt.graphOp(...args); }
  newDefaultGraph(...args) { return this.rt.newDefaultGraph(...args); }
  sigConnected(...args) { return this.rt.sigConnected(...args); }
  sigPath(...args) { return this.rt.sigPath(...args); }
  syncGraphFromFlat(...args) { return this.rt.syncGraphFromFlat(...args); }
}

/** Register domain object on `rt.modules.legacy` and bind live impls. */
export function installGraphLegacy(rt) {
  const inst = new GraphLegacy(rt);
  rt.modules = rt.modules || {};
  rt.modules.legacy = inst;
  for (const name of GraphLegacy.methodNames) {
    if (typeof rt[name] === 'function') inst[name] = rt[name];
  }
  return inst;
}

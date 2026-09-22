/**
 * HistorySystem
 * HISTORY — undo / redo domains
 *
 * Object API for this domain. Methods forward to the editor runtime closure
 * (shared `let` state lives there for behavior fidelity).
 */
export class HistorySystem {
  /** @param {object} rt editor runtime from createEditorRuntime() */
  constructor(rt) {
    this.rt = rt;
  }

  /** Method names owned by this domain (for install / introspection). */
  static get methodNames() {
    return [
    'dumpDomain',
    'pushHist',
    'redo',
    'resetHistory',
    'restoreDomain',
    'selWatch',
    'snapshot',
    'undo'
    ];
  }

  dumpDomain(...args) { return this.rt.dumpDomain(...args); }
  pushHist(...args) { return this.rt.pushHist(...args); }
  redo(...args) { return this.rt.redo(...args); }
  resetHistory(...args) { return this.rt.resetHistory(...args); }
  restoreDomain(...args) { return this.rt.restoreDomain(...args); }
  selWatch(...args) { return this.rt.selWatch(...args); }
  snapshot(...args) { return this.rt.snapshot(...args); }
  undo(...args) { return this.rt.undo(...args); }
}

/** Register domain object on `rt.modules.history` and bind live impls. */
export function installHistorySystem(rt) {
  const inst = new HistorySystem(rt);
  rt.modules = rt.modules || {};
  rt.modules.history = inst;
  for (const name of HistorySystem.methodNames) {
    if (typeof rt[name] === 'function') inst[name] = rt[name];
  }
  return inst;
}

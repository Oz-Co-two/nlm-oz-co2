/**
 * Pv4Bridge
 * PREVIEW — preview-v4 bridge
 *
 * Object API for this domain. Methods forward to the editor runtime closure
 * (shared `let` state lives there for behavior fidelity).
 */
export class Pv4Bridge {
  /** @param {object} rt editor runtime from createEditorRuntime() */
  constructor(rt) {
    this.rt = rt;
  }

  /** Method names owned by this domain (for install / introspection). */
  static get methodNames() {
    return [
    'applyPvSettings',
    'pv4EnvOf',
    'pv4Frame',
    'pv4NjsOf',
    'pv4Push',
    'pv4SyncEnv',
    'setPv4Mode'
    ];
  }

  applyPvSettings(...args) { return this.rt.applyPvSettings(...args); }
  pv4EnvOf(...args) { return this.rt.pv4EnvOf(...args); }
  pv4Frame(...args) { return this.rt.pv4Frame(...args); }
  pv4NjsOf(...args) { return this.rt.pv4NjsOf(...args); }
  pv4Push(...args) { return this.rt.pv4Push(...args); }
  pv4SyncEnv(...args) { return this.rt.pv4SyncEnv(...args); }
  setPv4Mode(...args) { return this.rt.setPv4Mode(...args); }
}

/** Register domain object on `rt.modules.pv4` and bind live impls. */
export function installPv4Bridge(rt) {
  const inst = new Pv4Bridge(rt);
  rt.modules = rt.modules || {};
  rt.modules.pv4 = inst;
  for (const name of Pv4Bridge.methodNames) {
    if (typeof rt[name] === 'function') inst[name] = rt[name];
  }
  return inst;
}

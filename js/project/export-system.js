/**
 * ExportSystem
 * EXPORT — Info.dat + difficulty dat
 *
 * Object API for this domain. Methods forward to the editor runtime closure
 * (shared `let` state lives there for behavior fidelity).
 */
export class ExportSystem {
  /** @param {object} rt editor runtime from createEditorRuntime() */
  constructor(rt) {
    this.rt = rt;
  }

  /** Method names owned by this domain (for install / introspection). */
  static get methodNames() {
    return [
    'buildDiffJsonFor',
    'exportMap',
    'njsOffExport'
    ];
  }

  buildDiffJsonFor(...args) { return this.rt.buildDiffJsonFor(...args); }
  exportMap(...args) { return this.rt.exportMap(...args); }
  njsOffExport(...args) { return this.rt.njsOffExport(...args); }
}

/** Register domain object on `rt.modules.export` and bind live impls. */
export function installExportSystem(rt) {
  const inst = new ExportSystem(rt);
  rt.modules = rt.modules || {};
  rt.modules.export = inst;
  for (const name of ExportSystem.methodNames) {
    if (typeof rt[name] === 'function') inst[name] = rt[name];
  }
  return inst;
}

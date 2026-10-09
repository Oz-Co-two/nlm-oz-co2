/**
 * GraphLegacy
 * 配線グラフ（sections を INPUT→OUTPUT の経路でつなぐデータ）。古いノード画面の処理は削除済みで、
 * 残っているのはレイヤー（NLE）画面・保存・読込が今も使う関数だけ。
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
    'ensureEdges',
    'newDefaultGraph',
    'sigConnected',
    'sigPath'
    ];
  }

  ensureEdges(...args) { return this.rt.ensureEdges(...args); }
  newDefaultGraph(...args) { return this.rt.newDefaultGraph(...args); }
  sigConnected(...args) { return this.rt.sigConnected(...args); }
  sigPath(...args) { return this.rt.sigPath(...args); }
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

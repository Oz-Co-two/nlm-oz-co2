/**
 * EditorScene
 * SCENE — Three.js editor viewport helpers
 *
 * Object API for this domain. Methods forward to the editor runtime closure
 * (shared `let` state lives there for behavior fidelity).
 */
export class EditorScene {
  /** @param {object} rt editor runtime from createEditorRuntime() */
  constructor(rt) {
    this.rt = rt;
  }

  /** Method names owned by this domain (for install / introspection). */
  static get methodNames() {
    return [
    'applyDpr',
    'markNameTex',
    'numTex',
    'resize',
    'rotAround',
    'tagHelper',
    'tmNameTex'
    ];
  }

  applyDpr(...args) { return this.rt.applyDpr(...args); }
  markNameTex(...args) { return this.rt.markNameTex(...args); }
  numTex(...args) { return this.rt.numTex(...args); }
  resize(...args) { return this.rt.resize(...args); }
  rotAround(...args) { return this.rt.rotAround(...args); }
  tagHelper(...args) { return this.rt.tagHelper(...args); }
  tmNameTex(...args) { return this.rt.tmNameTex(...args); }
}

/** Register domain object on `rt.modules.scene` and bind live impls. */
export function installEditorScene(rt) {
  const inst = new EditorScene(rt);
  rt.modules = rt.modules || {};
  rt.modules.scene = inst;
  for (const name of EditorScene.methodNames) {
    if (typeof rt[name] === 'function') inst[name] = rt[name];
  }
  return inst;
}

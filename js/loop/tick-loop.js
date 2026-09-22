/**
 * TickLoop
 * TICK — RAF game loop
 *
 * Object API for this domain. Methods forward to the editor runtime closure
 * (shared `let` state lives there for behavior fidelity).
 */
export class TickLoop {
  /** @param {object} rt editor runtime from createEditorRuntime() */
  constructor(rt) {
    this.rt = rt;
  }

  /** Method names owned by this domain (for install / introspection). */
  static get methodNames() {
    return [
    '_tick',
    'tick'
    ];
  }

  _tick(...args) { return this.rt._tick(...args); }
  tick(...args) { return this.rt.tick(...args); }
}

/** Register domain object on `rt.modules.tick` and bind live impls. */
export function installTickLoop(rt) {
  const inst = new TickLoop(rt);
  rt.modules = rt.modules || {};
  rt.modules.tick = inst;
  for (const name of TickLoop.methodNames) {
    if (typeof rt[name] === 'function') inst[name] = rt[name];
  }
  return inst;
}

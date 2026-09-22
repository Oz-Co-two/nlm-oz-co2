import { createEditorRuntime } from './runtime/create-runtime.js';
import { summarizeState } from './core/state.js';
import { VERSION } from './constants.js';

/**
 * Application bootstrap.
 * editor.html -> main.js -> createEditorRuntime() -> domain modules on rt.modules
 */
class App {
  constructor() {
    this.rt = createEditorRuntime();
    this.rt.panels = this.rt.modules || {};
    this._exposeDebug();
    this._start();
  }

  _exposeDebug() {
    try {
      const rt = this.rt;
      window._dbg = {
        version: VERSION,
        state: () => summarizeState(rt),
        rt,
        panels: rt.panels,
        save: () => (typeof rt.buildProjectText === 'function' ? rt.buildProjectText() : null),
        counts: () => summarizeState(rt),
        pv4Stats: () => (rt._PV4 && rt._PV4._dbgStats ? rt._PV4._dbgStats() : null),
      };
      window._cam = rt.camera;
      window._ctl = rt.controls;
    } catch (_) {}
  }

  _start() {
    if (typeof this.rt.tick === 'function') this.rt.tick();
  }
}

export const app = new App();

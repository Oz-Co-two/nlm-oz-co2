import { createEditorRuntime } from './runtime/create-runtime.js';
import { summarizeState } from './core/state.js';
import { VERSION, APP_VERSION } from './constants.js';

// 版番号をメニューバーの右端とタブ名に表示。exeではウィンドウタイトル（左上）にも出るので、
// 左右に分けて置く＝画面の右半分/左半分だけを切り取ったスクリーンショットでもどの版か分かる
try {
  const bar = document.getElementById('menubar');
  if (bar && !bar.querySelector('.mbVer')) {
    const v = document.createElement('span'); v.className = 'mbVer'; v.textContent = APP_VERSION;
    bar.appendChild(v);
  }
  document.title = 'Non-Linear Mapper ' + APP_VERSION;
} catch (_) {}

/**
 * Application bootstrap.
 * editor.html -> main.js -> createEditorRuntime() -> domain modules on rt.modules
 */
function isDevMode() {
  try { return !window.pywebview && new URLSearchParams(location.search).get('dev') === '1'; } catch (_) { return false; }
}

class App {
  constructor() {
    this.rt = createEditorRuntime();
    this.rt.panels = this.rt.modules || {};
    this._exposeDebug();
    this._start();
  }

  _exposeDebug() {
    // 開発用の窓口は「pywebview外（ブラウザ）かつURLに ?dev=1」の時だけ作る＝配布版exe・通常のブラウザ利用には置かない
    // （2026-09-28。ページ内でコードを動かせる者への新たな入口を配布物に残さないため。tools/cdp.py は ?dev=1 で開く）
    if (!isDevMode()) return;
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

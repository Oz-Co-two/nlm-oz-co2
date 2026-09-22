import { createEditorApp } from './editor-app.js';

/**
 * Public runtime factory (stable entry for main.js).
 * Implementation lives in `editor-app.js`; domain classes attach via install* there.
 */
export function createEditorRuntime() {
  return createEditorApp();
}

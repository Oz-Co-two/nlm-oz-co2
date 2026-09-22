/**
 * SaveSystem
 * SAVE — .nlmf project / codec / IndexedDB handles
 *
 * Object API for this domain. Methods forward to the editor runtime closure
 * (shared `let` state lives there for behavior fidelity).
 */
export class SaveSystem {
  /** @param {object} rt editor runtime from createEditorRuntime() */
  constructor(rt) {
    this.rt = rt;
  }

  /** Method names owned by this domain (for install / introspection). */
  static get methodNames() {
    return [
    '_slimBase',
    'afterFolder',
    'applyOpenedProject',
    'applyProject',
    'buildProjectText',
    'decArr',
    'decDiff',
    'decSec',
    'encArr',
    'encDiff',
    'encSec',
    'idbDB',
    'idbGet',
    'idbSet',
    'initScratchDiff',
    'newProject',
    'openProjectFile',
    'openSongFile',
    'parseDiffFragment',
    'resetAllState',
    'tryAutoLoadSongNative',
    'rotateBakDisk',
    'rotateBakIdb',
    'saveProject',
    'saveProjectCopy'
    ];
  }

  _slimBase(...args) { return this.rt._slimBase(...args); }
  afterFolder(...args) { return this.rt.afterFolder(...args); }
  applyOpenedProject(...args) { return this.rt.applyOpenedProject(...args); }
  applyProject(...args) { return this.rt.applyProject(...args); }
  buildProjectText(...args) { return this.rt.buildProjectText(...args); }
  decArr(...args) { return this.rt.decArr(...args); }
  decDiff(...args) { return this.rt.decDiff(...args); }
  decSec(...args) { return this.rt.decSec(...args); }
  encArr(...args) { return this.rt.encArr(...args); }
  encDiff(...args) { return this.rt.encDiff(...args); }
  encSec(...args) { return this.rt.encSec(...args); }
  idbDB(...args) { return this.rt.idbDB(...args); }
  idbGet(...args) { return this.rt.idbGet(...args); }
  idbSet(...args) { return this.rt.idbSet(...args); }
  initScratchDiff(...args) { return this.rt.initScratchDiff(...args); }
  newProject(...args) { return this.rt.newProject(...args); }
  openProjectFile(...args) { return this.rt.openProjectFile(...args); }
  openSongFile(...args) { return this.rt.openSongFile(...args); }
  parseDiffFragment(...args) { return this.rt.parseDiffFragment(...args); }
  resetAllState(...args) { return this.rt.resetAllState(...args); }
  tryAutoLoadSongNative(...args) { return this.rt.tryAutoLoadSongNative(...args); }
  rotateBakDisk(...args) { return this.rt.rotateBakDisk(...args); }
  rotateBakIdb(...args) { return this.rt.rotateBakIdb(...args); }
  saveProject(...args) { return this.rt.saveProject(...args); }
  saveProjectCopy(...args) { return this.rt.saveProjectCopy(...args); }
}

/** Register domain object on `rt.modules.save` and bind live impls. */
export function installSaveSystem(rt) {
  const inst = new SaveSystem(rt);
  rt.modules = rt.modules || {};
  rt.modules.save = inst;
  for (const name of SaveSystem.methodNames) {
    if (typeof rt[name] === 'function') inst[name] = rt[name];
  }
  return inst;
}

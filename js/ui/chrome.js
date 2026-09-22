/**
 * UiChrome
 * UI CHROME — toolbar / menus / settings / shortcuts / i18n
 *
 * Object API for this domain. Methods forward to the editor runtime closure
 * (shared `let` state lives there for behavior fidelity).
 */
export class UiChrome {
  /** @param {object} rt editor runtime from createEditorRuntime() */
  constructor(rt) {
    this.rt = rt;
  }

  /** Method names owned by this domain (for install / introspection). */
  static get methodNames() {
    return [
    '_bootReveal',
    'applyShowKeys',
    'applyUiScale',
    'applyVolumes',
    'buildDirPanel',
    'buildToolbar',
    'loadLang',
    'makeSplit',
    'ndColorEdit',
    'paneOf',
    'refreshMusicHdr',
    'saveCamSpd',
    'saveSplits',
    'setLaneRatio',
    'setPreview',
    'showErr',
    'showOk',
    'stat',
    't',
    'tbIcon',
    'tf',
    'updateDiffLabel',
    'wirePv',
    'wireSpd',
    'wireStepper',
    'wireVol'
    ];
  }

  _bootReveal(...args) { return this.rt._bootReveal(...args); }
  applyShowKeys(...args) { return this.rt.applyShowKeys(...args); }
  applyUiScale(...args) { return this.rt.applyUiScale(...args); }
  applyVolumes(...args) { return this.rt.applyVolumes(...args); }
  buildDirPanel(...args) { return this.rt.buildDirPanel(...args); }
  buildToolbar(...args) { return this.rt.buildToolbar(...args); }
  loadLang(...args) { return this.rt.loadLang(...args); }
  makeSplit(...args) { return this.rt.makeSplit(...args); }
  ndColorEdit(...args) { return this.rt.ndColorEdit(...args); }
  paneOf(...args) { return this.rt.paneOf(...args); }
  refreshMusicHdr(...args) { return this.rt.refreshMusicHdr(...args); }
  saveCamSpd(...args) { return this.rt.saveCamSpd(...args); }
  saveSplits(...args) { return this.rt.saveSplits(...args); }
  setLaneRatio(...args) { return this.rt.setLaneRatio(...args); }
  setPreview(...args) { return this.rt.setPreview(...args); }
  showErr(...args) { return this.rt.showErr(...args); }
  showOk(...args) { return this.rt.showOk(...args); }
  stat(...args) { return this.rt.stat(...args); }
  t(...args) { return this.rt.t(...args); }
  tbIcon(...args) { return this.rt.tbIcon(...args); }
  tf(...args) { return this.rt.tf(...args); }
  updateDiffLabel(...args) { return this.rt.updateDiffLabel(...args); }
  wirePv(...args) { return this.rt.wirePv(...args); }
  wireSpd(...args) { return this.rt.wireSpd(...args); }
  wireStepper(...args) { return this.rt.wireStepper(...args); }
  wireVol(...args) { return this.rt.wireVol(...args); }
}

/** Register domain object on `rt.modules.chrome` and bind live impls. */
export function installUiChrome(rt) {
  const inst = new UiChrome(rt);
  rt.modules = rt.modules || {};
  rt.modules.chrome = inst;
  for (const name of UiChrome.methodNames) {
    if (typeof rt[name] === 'function') inst[name] = rt[name];
  }
  return inst;
}

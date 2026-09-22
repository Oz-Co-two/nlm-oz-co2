/**
 * NotesEditor
 * NOTES — place / rebuild / arcs / chains / walls
 *
 * Object API for this domain. Methods forward to the editor runtime closure
 * (shared `let` state lives there for behavior fidelity).
 */
export class NotesEditor {
  /** @param {object} rt editor runtime from createEditorRuntime() */
  constructor(rt) {
    this.rt = rt;
  }

  /** Method names owned by this domain (for install / introspection). */
  static get methodNames() {
    return [
    'addObj',
    'arrOf',
    'buildArc',
    'buildBomb',
    'buildChain',
    'buildNote',
    'buildWall',
    'createClipAt',
    'createNoteClipAt',
    'deleteRegionContents',
    'drawNoteIco',
    'extractRegion',
    'makeSpikyBomb',
    'mirrorRegion',
    'objUnder',
    'pasteFragment',
    'placeAt',
    'rebuild',
    'recolorLinkedSliders',
    'refreshGhost',
    'refreshMesh',
    'regionObjs',
    'removeObj',
    'selWalls',
    'setNoteColStr',
    'setPlaceMode',
    'setPvShowNotes',
    'createArcData',
    'spawnArcsFromSelection',
    'spawnChainFromSelection',
    'tryCreateChainData',
    'updateWallGhost'
    ];
  }

  addObj(...args) { return this.rt.addObj(...args); }
  arrOf(...args) { return this.rt.arrOf(...args); }
  buildArc(...args) { return this.rt.buildArc(...args); }
  buildBomb(...args) { return this.rt.buildBomb(...args); }
  buildChain(...args) { return this.rt.buildChain(...args); }
  buildNote(...args) { return this.rt.buildNote(...args); }
  buildWall(...args) { return this.rt.buildWall(...args); }
  createClipAt(...args) { return this.rt.createClipAt(...args); }
  createNoteClipAt(...args) { return this.rt.createNoteClipAt(...args); }
  deleteRegionContents(...args) { return this.rt.deleteRegionContents(...args); }
  drawNoteIco(...args) { return this.rt.drawNoteIco(...args); }
  extractRegion(...args) { return this.rt.extractRegion(...args); }
  makeSpikyBomb(...args) { return this.rt.makeSpikyBomb(...args); }
  mirrorRegion(...args) { return this.rt.mirrorRegion(...args); }
  objUnder(...args) { return this.rt.objUnder(...args); }
  pasteFragment(...args) { return this.rt.pasteFragment(...args); }
  placeAt(...args) { return this.rt.placeAt(...args); }
  rebuild(...args) { return this.rt.rebuild(...args); }
  recolorLinkedSliders(...args) { return this.rt.recolorLinkedSliders(...args); }
  refreshGhost(...args) { return this.rt.refreshGhost(...args); }
  refreshMesh(...args) { return this.rt.refreshMesh(...args); }
  regionObjs(...args) { return this.rt.regionObjs(...args); }
  removeObj(...args) { return this.rt.removeObj(...args); }
  selWalls(...args) { return this.rt.selWalls(...args); }
  setNoteColStr(...args) { return this.rt.setNoteColStr(...args); }
  setPlaceMode(...args) { return this.rt.setPlaceMode(...args); }
  setPvShowNotes(...args) { return this.rt.setPvShowNotes(...args); }
  createArcData(...args) { return this.rt.createArcData(...args); }
  spawnArcsFromSelection(...args) { return this.rt.spawnArcsFromSelection(...args); }
  spawnChainFromSelection(...args) { return this.rt.spawnChainFromSelection(...args); }
  tryCreateChainData(...args) { return this.rt.tryCreateChainData(...args); }
  updateWallGhost(...args) { return this.rt.updateWallGhost(...args); }
}

/** Register domain object on `rt.modules.notes` and bind live impls. */
export function installNotesEditor(rt) {
  const inst = new NotesEditor(rt);
  rt.modules = rt.modules || {};
  rt.modules.notes = inst;
  for (const name of NotesEditor.methodNames) {
    if (typeof rt[name] === 'function') inst[name] = rt[name];
  }
  return inst;
}

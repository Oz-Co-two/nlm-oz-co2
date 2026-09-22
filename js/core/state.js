/**
 * Architectural state hub.
 *
 * Live mutable state is created inside the editor-app closure and exposed on the
 * runtime object (`rt`). This module documents the shape and helpers for panels.
 */

/** @typedef {object} EditorState */

/**
 * Keys commonly read/written across domains.
 * Actual values live on the runtime instance.
 */
export const STATE_KEYS = Object.freeze({
  modes: ['curTab', 'pvMode', 'nodeColMode', 'hoverPane', 'lightMode', 'placeMode', 'nodeMode'],
  chart: ['notes', 'bombs', 'walls', 'arcs', 'chains', 'lightEvents', 'BPM', 'cur', 'snap', 'playing'],
  nle: ['sections', 'markers', 'musicBeat', 'musicSegs', 'notesLanes', 'lightLanes', 'tlSpan'],
  project: ['projDiffs', 'graphIO', 'infoGraph', 'infoBase', 'graphEdges', 'extraNodes'],
  audio: ['audioBuf', 'songDur', 'actx'],
  preview: ['pv4On', '_PV4', 'pvShowNotes', 'pvShowLights', 'pvShowStruct', 'pvShowAmbient'],
});

/** Ensure `rt.modules` exists. */
export function ensureModules(rt) {
  rt.modules = rt.modules || {};
  return rt.modules;
}

/** Snapshot of high-level counts (debug / HUD). */
export function summarizeState(rt) {
  return {
    bpm: rt.BPM,
    cur: rt.cur,
    playing: !!rt.playing,
    notes: Array.isArray(rt.notes) ? rt.notes.length : -1,
    lights: Array.isArray(rt.lightEvents) ? rt.lightEvents.length : -1,
    sections: Array.isArray(rt.sections) ? rt.sections.length : -1,
    modules: rt.modules ? Object.keys(rt.modules) : [],
  };
}

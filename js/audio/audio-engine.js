/**
 * AudioEngine
 * AUDIO — playback / waveform / metronome
 *
 * Object API for this domain. Methods forward to the editor runtime closure
 * (shared `let` state lives there for behavior fidelity).
 */
export class AudioEngine {
  /** @param {object} rt editor runtime from createEditorRuntime() */
  constructor(rt) {
    this.rt = rt;
  }

  /** Method names owned by this domain (for install / introspection). */
  static get methodNames() {
    return [
    'aTime',
    'blip',
    'buildWaveData',
    'drawMeter',
    'metroNode',
    'metroTick',
    'pause',
    'play',
    'runBpmEstimate',
    'vmResize'
    ];
  }

  aTime(...args) { return this.rt.aTime(...args); }
  blip(...args) { return this.rt.blip(...args); }
  buildWaveData(...args) { return this.rt.buildWaveData(...args); }
  drawMeter(...args) { return this.rt.drawMeter(...args); }
  metroNode(...args) { return this.rt.metroNode(...args); }
  metroTick(...args) { return this.rt.metroTick(...args); }
  pause(...args) { return this.rt.pause(...args); }
  play(...args) { return this.rt.play(...args); }
  runBpmEstimate(...args) { return this.rt.runBpmEstimate(...args); }
  vmResize(...args) { return this.rt.vmResize(...args); }
}

/** Register domain object on `rt.modules.audio` and bind live impls. */
export function installAudioEngine(rt) {
  const inst = new AudioEngine(rt);
  rt.modules = rt.modules || {};
  rt.modules.audio = inst;
  for (const name of AudioEngine.methodNames) {
    if (typeof rt[name] === 'function') inst[name] = rt[name];
  }
  return inst;
}

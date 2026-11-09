// The sound of the landing page's sets, made in the browser (Web Audio), so the page needs no sound files: city hum
// and wind on the rooftop, rain and a neon buzz in the alley, desert wind and an engine, the deep's low rumble and
// bubbles. Off until the visitor turns it on (browsers allow sound only after a click). sound() gives
// { on, start(name), scene(name), stop(), levels(n) }; levels(n) are n numbers from 0 to 1 for the level bars.

function noise(ctx) {
  const buffer = ctx.createBuffer(1, ctx.sampleRate * 2, ctx.sampleRate);
  const data = buffer.getChannelData(0);
  for (let i = 0; i < data.length; i += 1) data[i] = Math.random() * 2 - 1;
  const src = ctx.createBufferSource();
  src.buffer = buffer; src.loop = true;
  return src;
}

// A sound made of a source, filters and a gain; wobble slowly moves a parameter, like wind rising and falling.
function voice(ctx, out, { source = 'noise', freq = 0, filters = [], gain, wobble }) {
  const src = source === 'noise' ? noise(ctx) : Object.assign(ctx.createOscillator(), { type: source });
  if (source !== 'noise') src.frequency.value = freq;
  let last = src;
  for (const [type, frequency, Q = 0.7] of filters) {
    const f = ctx.createBiquadFilter();
    Object.assign(f, { type }); f.frequency.value = frequency; f.Q.value = Q;
    last.connect(f); last = f;
  }
  const g = ctx.createGain(); g.gain.value = gain;
  last.connect(g); g.connect(out);
  const parts = [src];
  if (wobble) {
    const lfo = ctx.createOscillator(), depth = ctx.createGain();
    lfo.frequency.value = wobble.rate; depth.gain.value = wobble.depth;
    lfo.connect(depth);
    depth.connect(wobble.on === 'gain' ? g.gain : last.frequency);
    lfo.start(); parts.push(lfo);
  }
  src.start();
  return parts;
}

const MIX = {
  rooftop: [{ filters: [['lowpass', 380]], gain: 0.5 },
    { filters: [['bandpass', 900, 0.6]], gain: 0.08, wobble: { rate: 0.13, depth: 0.06, on: 'gain' } }],
  neon: [{ filters: [['highpass', 1200], ['lowpass', 7000]], gain: 0.16 },
    { filters: [['bandpass', 3200, 1.2]], gain: 0.05, wobble: { rate: 3.1, depth: 0.03, on: 'gain' } },
    { source: 'sawtooth', freq: 60, filters: [['lowpass', 260]], gain: 0.018 }],
  desert: [{ filters: [['bandpass', 520, 0.5]], gain: 0.22, wobble: { rate: 0.09, depth: 260 } },
    { source: 'sawtooth', freq: 48, filters: [['lowpass', 170]], gain: 0.06, wobble: { rate: 7, depth: 0.02, on: 'gain' } }],
  deep: [{ filters: [['lowpass', 220]], gain: 0.7, wobble: { rate: 0.07, depth: 0.25, on: 'gain' } },
    { source: 'sine', freq: 41, gain: 0.05 }],
};

export function sound() {
  let ctx = null, master = null, meter = null, bins = null, playing = [], bubbleTimer = 0;

  function bubbles() {   // now and then a short rising blip, in the deep only
    const o = ctx.createOscillator(), g = ctx.createGain(), at = ctx.currentTime;
    o.frequency.setValueAtTime(300 + Math.random() * 300, at); o.frequency.exponentialRampToValueAtTime(1200 + Math.random() * 600, at + 0.12);
    g.gain.setValueAtTime(0.0001, at); g.gain.exponentialRampToValueAtTime(0.05, at + 0.02); g.gain.exponentialRampToValueAtTime(0.0001, at + 0.16);
    o.connect(g); g.connect(master); o.start(at); o.stop(at + 0.2);
  }

  const api = {
    on: false,
    // Turn the sound on with a scene; it must be called from a click.
    start(name) {
      const Context = window.AudioContext || window.webkitAudioContext;
      if (!Context) return false;
      if (!ctx) {
        ctx = new Context();
        meter = ctx.createAnalyser(); meter.fftSize = 64; bins = new Uint8Array(meter.frequencyBinCount);
        master = ctx.createGain(); master.connect(meter); meter.connect(ctx.destination);
      }
      ctx.resume();
      api.on = true;
      api.scene(name);
      return true;
    },
    // Change to another scene's sound, faded across in a second.
    scene(name) {
      if (!api.on || !ctx) return;
      const at = ctx.currentTime, old = playing;
      master.gain.cancelScheduledValues(at);
      master.gain.setValueAtTime(master.gain.value, at);
      master.gain.linearRampToValueAtTime(0, at + 0.4);
      setTimeout(() => {
        old.forEach((n) => { try { n.stop(); } catch (e) { /* already stopped */ } });
        if (!api.on) return;
        playing = MIX[name].flatMap((v) => voice(ctx, master, v));
        clearInterval(bubbleTimer);
        if (name === 'deep') bubbleTimer = setInterval(() => { if (Math.random() > 0.5) bubbles(); }, 700);
        master.gain.setValueAtTime(0, ctx.currentTime);
        master.gain.linearRampToValueAtTime(0.9, ctx.currentTime + 0.8);
      }, 420);
    },
    stop() {
      api.on = false;
      clearInterval(bubbleTimer);
      if (!ctx) return;
      master.gain.setValueAtTime(master.gain.value, ctx.currentTime);
      master.gain.linearRampToValueAtTime(0, ctx.currentTime + 0.3);
      const old = playing; playing = [];
      setTimeout(() => { old.forEach((n) => { try { n.stop(); } catch (e) { /* already stopped */ } }); if (!api.on) ctx.suspend(); }, 350);
    },
    levels(n) {
      if (!api.on || !meter) return new Array(n).fill(0);
      meter.getByteFrequencyData(bins);
      const step = Math.floor(bins.length / n);
      return Array.from({ length: n }, (_, i) => Math.min(1, (bins[i * step] / 255) * 1.6));
    },
    close() { api.stop(); if (ctx) setTimeout(() => ctx.close(), 400); },
  };
  return api;
}

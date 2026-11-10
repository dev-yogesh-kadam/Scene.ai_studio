// The sound of the landing page's sets, made in the browser (Web Audio), so the page needs no sound files: city hum
// and wind on the rooftop, rain and a neon buzz in the alley, desert wind and an engine, the deep's low rumble and
// bubbles. Off until the visitor turns it on (browsers allow sound only after a click). sound() gives
// { on, start(name), scene(name), stop(), levels(n) }; levels(n) are n numbers from 0 to 1 for the level bars.

type Wobble = { rate: number; depth: number; on?: 'gain' };
type Voice = {
  source?: 'noise' | OscillatorType;
  freq?: number;
  filters?: [BiquadFilterType, number, number?][];
  gain: number;
  wobble?: Wobble;
};
type Source = AudioBufferSourceNode | OscillatorNode;

function noise(ctx: AudioContext) {
  const buffer = ctx.createBuffer(1, ctx.sampleRate * 2, ctx.sampleRate);
  const data = buffer.getChannelData(0);
  for (let i = 0; i < data.length; i += 1) data[i] = Math.random() * 2 - 1;
  const src = ctx.createBufferSource();
  src.buffer = buffer;
  src.loop = true;
  return src;
}

function oscillator(ctx: AudioContext, type: OscillatorType, freq: number) {
  const src = ctx.createOscillator();
  src.type = type;
  src.frequency.value = freq;
  return src;
}

// A sound made of a source, filters and a gain; wobble slowly moves a parameter, like wind rising and falling.
function voice(ctx: AudioContext, out: AudioNode, { source = 'noise', freq = 0, filters = [], gain, wobble }: Voice) {
  const src: Source = source === 'noise' ? noise(ctx) : oscillator(ctx, source, freq);
  let last: AudioNode = src;
  for (const [type, frequency, Q = 0.7] of filters) {
    const f = ctx.createBiquadFilter();
    f.type = type;
    f.frequency.value = frequency;
    f.Q.value = Q;
    last.connect(f);
    last = f;
  }
  const g = ctx.createGain();
  g.gain.value = gain;
  last.connect(g);
  g.connect(out);
  const parts: Source[] = [src];
  if (wobble) {
    const lfo = ctx.createOscillator(),
      depth = ctx.createGain();
    lfo.frequency.value = wobble.rate;
    depth.gain.value = wobble.depth;
    lfo.connect(depth);
    depth.connect(wobble.on === 'gain' ? g.gain : (last as BiquadFilterNode).frequency);
    lfo.start();
    parts.push(lfo);
  }
  src.start();
  return parts;
}

const MIX: Record<string, Voice[]> = {
  rooftop: [
    { filters: [['lowpass', 380]], gain: 0.5 },
    { filters: [['bandpass', 900, 0.6]], gain: 0.08, wobble: { rate: 0.13, depth: 0.06, on: 'gain' } },
  ],
  neon: [
    {
      filters: [
        ['highpass', 1200],
        ['lowpass', 7000],
      ],
      gain: 0.16,
    },
    { filters: [['bandpass', 3200, 1.2]], gain: 0.05, wobble: { rate: 3.1, depth: 0.03, on: 'gain' } },
    { source: 'sawtooth', freq: 60, filters: [['lowpass', 260]], gain: 0.018 },
  ],
  desert: [
    { filters: [['bandpass', 520, 0.5]], gain: 0.22, wobble: { rate: 0.09, depth: 260 } },
    {
      source: 'sawtooth',
      freq: 48,
      filters: [['lowpass', 170]],
      gain: 0.06,
      wobble: { rate: 7, depth: 0.02, on: 'gain' },
    },
  ],
  deep: [
    { filters: [['lowpass', 220]], gain: 0.7, wobble: { rate: 0.07, depth: 0.25, on: 'gain' } },
    { source: 'sine', freq: 41, gain: 0.05 },
  ],
};

const stopAll = (nodes: Source[]) =>
  nodes.forEach((n) => {
    try {
      n.stop();
    } catch {
      /* already stopped */
    }
  });

export function sound() {
  let graph: { ctx: AudioContext; master: GainNode; meter: AnalyserNode; bins: Uint8Array<ArrayBuffer> } | null = null,
    playing: Source[] = [],
    bubbleTimer: ReturnType<typeof setInterval> | undefined;

  function bubbles(ctx: AudioContext, master: GainNode) {
    // now and then a short rising blip, in the deep only
    const o = ctx.createOscillator(),
      g = ctx.createGain(),
      at = ctx.currentTime;
    o.frequency.setValueAtTime(300 + Math.random() * 300, at);
    o.frequency.exponentialRampToValueAtTime(1200 + Math.random() * 600, at + 0.12);
    g.gain.setValueAtTime(0.0001, at);
    g.gain.exponentialRampToValueAtTime(0.05, at + 0.02);
    g.gain.exponentialRampToValueAtTime(0.0001, at + 0.16);
    o.connect(g);
    g.connect(master);
    o.start(at);
    o.stop(at + 0.2);
  }

  const api = {
    on: false,
    // Turn the sound on with a scene; it must be called from a click.
    start(name: string) {
      const Context =
        window.AudioContext || (window as Window & { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
      if (!Context) return false;
      if (!graph) {
        const ctx = new Context();
        const meter = ctx.createAnalyser();
        meter.fftSize = 64;
        const master = ctx.createGain();
        master.connect(meter);
        meter.connect(ctx.destination);
        graph = { ctx, master, meter, bins: new Uint8Array(meter.frequencyBinCount) };
      }
      void graph.ctx.resume();
      api.on = true;
      api.scene(name);
      return true;
    },
    // Change to another scene's sound, faded across in a second.
    scene(name: string) {
      if (!api.on || !graph) return;
      const { ctx, master } = graph;
      const at = ctx.currentTime,
        old = playing;
      master.gain.cancelScheduledValues(at);
      master.gain.setValueAtTime(master.gain.value, at);
      master.gain.linearRampToValueAtTime(0, at + 0.4);
      setTimeout(() => {
        stopAll(old);
        if (!api.on) return;
        playing = MIX[name].flatMap((v) => voice(ctx, master, v));
        clearInterval(bubbleTimer);
        if (name === 'deep')
          bubbleTimer = setInterval(() => {
            if (Math.random() > 0.5) bubbles(ctx, master);
          }, 700);
        master.gain.setValueAtTime(0, ctx.currentTime);
        master.gain.linearRampToValueAtTime(0.9, ctx.currentTime + 0.8);
      }, 420);
    },
    stop() {
      api.on = false;
      clearInterval(bubbleTimer);
      if (!graph) return;
      const { ctx, master } = graph;
      master.gain.setValueAtTime(master.gain.value, ctx.currentTime);
      master.gain.linearRampToValueAtTime(0, ctx.currentTime + 0.3);
      const old = playing;
      playing = [];
      setTimeout(() => {
        stopAll(old);
        if (!api.on) void ctx.suspend();
      }, 350);
    },
    levels(n: number) {
      if (!api.on || !graph) return new Array<number>(n).fill(0);
      const { meter, bins } = graph;
      meter.getByteFrequencyData(bins);
      const step = Math.floor(bins.length / n);
      return Array.from({ length: n }, (_, i) => Math.min(1, (bins[i * step] / 255) * 1.6));
    },
    close() {
      api.stop();
      if (graph) {
        const { ctx } = graph;
        setTimeout(() => void ctx.close(), 400);
      }
    },
  };
  return api;
}

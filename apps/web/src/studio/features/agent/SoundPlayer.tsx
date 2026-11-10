// A sound as a player: a round play button, its waveform (drawn from the file the first time it is shown) that also
// shows how far it has played and can be clicked to jump, and its length. One sound plays at a time.

import { useEffect, useRef, useState } from 'react';
import { fileBytes } from '@scene/shared/api/library';
import { Icon } from '../../../common/components/Icon/Icon';
import { cx } from '../../../common/cx';
import { clock } from './shots';
import s from './Markdown.module.css';

const WAVE_BARS = 64;
const waves = new Map<string, number[]>(); // url -> the bar heights, once worked out
const drawn = Array.from({ length: WAVE_BARS }, (_, i) => 0.25 + 0.15 * Math.abs(Math.sin(i * 0.7)));
let playing: HTMLAudioElement | null = null;

type WithWebkit = Window & { webkitAudioContext?: typeof AudioContext };

/** The file's loudness in WAVE_BARS slices. */
async function heightsOf(url: string) {
  const data = await fileBytes(url);
  if (data.byteLength > 40e6) return null; // a very long sound keeps the drawn shape
  const Context = window.AudioContext || (window as WithWebkit).webkitAudioContext;
  if (!Context) return null;
  const context = new Context();
  const decoded = await context.decodeAudioData(data);
  void context.close();
  const samples = decoded.getChannelData(0);
  const step = Math.floor(samples.length / WAVE_BARS) || 1;
  const peaks = Array.from({ length: WAVE_BARS }, (_, i) => {
    let sum = 0;
    for (let j = i * step; j < (i + 1) * step && j < samples.length; j += 32) sum += samples[j] * samples[j];
    return Math.sqrt(sum / (step / 32));
  });
  const top = Math.max(...peaks) || 1;
  return peaks.map((p) => p / top);
}

export function SoundPlayer({ url, name = '' }: { url: string; name?: string }) {
  const audio = useRef<HTMLAudioElement>(null);
  const node = useRef<HTMLDivElement>(null);
  const [heights, setHeights] = useState(() => waves.get(url) || drawn);
  const [paused, setPaused] = useState(true);
  const [pos, setPos] = useState({ share: 0, time: 0 });
  const progress = () => {
    const a = audio.current;
    if (!a) return;
    setPos({
      share: a.duration ? a.currentTime / a.duration : 0,
      time: a.paused && !a.currentTime ? a.duration || 0 : a.currentTime,
    });
  };
  // The real waveform: the file read once when the player is first seen.
  useEffect(() => {
    if (waves.has(url) || !node.current || !('IntersectionObserver' in window)) return;
    const seen = new IntersectionObserver((entries) => {
      if (!entries.some((e) => e.isIntersecting)) return;
      seen.disconnect();
      heightsOf(url).then(
        (found) => {
          if (!found) return;
          waves.set(url, found);
          setHeights(found);
        },
        () => {}, // the drawn shape stays
      );
    });
    seen.observe(node.current);
    return () => seen.disconnect();
  }, [url]);
  const seek = (share: number) => {
    const a = audio.current;
    if (!a?.duration) return;
    a.currentTime = Math.max(0, Math.min(1, share)) * a.duration;
    progress();
  };
  const lit = Math.round(pos.share * WAVE_BARS);
  return (
    <div ref={node} className={s.wave}>
      <button
        type="button"
        className={s['wave-play']}
        aria-label={'Play ' + name}
        title={paused ? 'Play' : 'Pause'}
        onClick={() => {
          const a = audio.current;
          if (!a) return;
          if (a.paused) a.play().catch(() => {});
          else a.pause();
        }}
      >
        <Icon name={paused ? 'play' : 'pause'} />
      </button>
      <div
        className={s['wave-bars']}
        role="slider"
        aria-label="Position"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={Math.round(pos.share * 100)}
        tabIndex={0}
        onClick={(e) => {
          const r = e.currentTarget.getBoundingClientRect();
          seek((e.clientX - r.left) / r.width);
        }}
        onKeyDown={(e) => {
          const a = audio.current;
          if (!a || (e.key !== 'ArrowRight' && e.key !== 'ArrowLeft')) return;
          e.preventDefault();
          a.currentTime = Math.max(0, a.currentTime + (e.key === 'ArrowRight' ? 5 : -5));
          progress();
        }}
      >
        {heights.map((h, i) => (
          <i key={i} className={cx(i < lit && s.on)} style={{ height: `${Math.max(8, Math.round(h * 100))}%` }} />
        ))}
      </div>
      <span className={s['wave-time']}>{clock(pos.time)}</span>
      <audio
        ref={audio}
        src={url}
        preload="metadata"
        onLoadedMetadata={progress}
        onTimeUpdate={progress}
        onPlay={(e) => {
          if (playing && playing !== e.currentTarget) playing.pause();
          playing = e.currentTarget;
          setPaused(false);
        }}
        onPause={() => setPaused(true)}
        onEnded={(e) => {
          e.currentTarget.currentTime = 0;
          progress();
        }}
      />
    </div>
  );
}

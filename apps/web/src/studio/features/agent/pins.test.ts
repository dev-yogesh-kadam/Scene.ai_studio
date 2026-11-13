import { describe, expect, it } from 'vitest';
import type { ModelInfo, WorkflowRow } from '../jobs/jobForm';
import { aboutOf, bestResolution, clearKind, pinTabs, secondsOf, togglePin } from './pins';

const ROWS: WorkflowRow[] = [
  {
    id: 'video/h3_all_in_one',
    kind: 'video',
    title: 'H3 All In One',
    source: 'comfy',
    description: 'Long shots with a cast.',
  },
  { id: 'video/h3_chunk', kind: 'video', title: 'H3 Chunk', source: 'comfy' },
  {
    id: 'video/generation_video',
    kind: 'video',
    title: 'Generation video',
    source: 'generation',
    models: [
      { id: 'seedance_2_5', label: 'Seedance 2.5' },
      { id: 'kling_3_0_turbo', label: 'Kling 3.0 Turbo' },
    ],
  },
  {
    id: 'video/generation_lipsync',
    kind: 'video',
    title: 'Generation lip sync',
    source: 'generation',
    description: 'Makes the person in a video speak a voice track, made by the generation server.',
  },
  { id: 'image/image_t2i_flux3_klein', kind: 'image', title: 'Text to Image: FLUX 3 Klein', source: 'comfy' },
  {
    id: 'audio/generation_music',
    kind: 'audio',
    title: 'Generation music',
    source: 'generation',
    description: 'A background-music track, 10 to 120 seconds, made by the generation server.',
  },
  { id: 'video/broken', kind: 'video', title: 'Broken', error: 'unreadable' },
];

const SEEDANCE: ModelInfo = {
  model: 'seedance_2_5',
  name: 'Seedance 2.5',
  about:
    'Strong motion and character consistency in clips up to 15s. 4–15 s, first+last frame. 480p 9/9 credits per second.',
  resolutions: ['480p', '720p', '1080p', '2160p'],
  shapes: ['16:9'],
  sound: 'choice',
  frames: ['first', 'last'],
};

describe('the workflows for a chat', () => {
  it('are tabs by kind: models one by one, then the single-model tools, then ComfyUI by name', () => {
    const tabs = pinTabs(ROWS, { 'video/generation_video': [SEEDANCE] });
    expect(tabs.map((t) => t.label)).toEqual(['Image', 'Video', 'Audio']);
    const video = tabs[1];
    expect(video.models.map((m) => m.value)).toEqual([
      'video/generation_video#seedance_2_5',
      'video/generation_video#kling_3_0_turbo',
      'video/generation_lipsync',
    ]);
    expect(video.workflows.map((w) => w.title)).toEqual(['H3 All In One', 'H3 Chunk']); // a broken one is left out
    expect(video.models[0]).toMatchObject({
      title: 'Seedance 2.5',
      about: 'Strong motion and character consistency in clips up to 15s.',
      meta: ['4K', '4–15 s'],
      sound: true,
    });
    expect(video.models[1]).toMatchObject({ title: 'Kling 3.0 Turbo', meta: [], sound: false }); // no list: its name alone
    expect(tabs[2].models[0]).toMatchObject({ value: 'audio/generation_music', meta: ['10–120 s'] });
  });

  it('say no prices and read lengths and resolutions as people do', () => {
    expect(aboutOf('2K 18, 4K 36 credits per image.')).toBe('');
    expect(secondsOf({ seconds: { min: 3, max: 15 } }, '')).toBe('3–15 s');
    expect(secondsOf(null, 'Up to 22 s')).toBe('');
    expect(bestResolution(['1K', '2K', '4K'])).toBe('4K');
    expect(bestResolution(['480p', '1080p', '720p'])).toBe('1080p');
    expect(bestResolution(['2K', '1080p'])).toBe('2K');
  });

  it('are ticked one by one, and "Agent selects" clears a kind', () => {
    let pins = togglePin([], 'video/generation_video#seedance_2_5');
    pins = togglePin(pins, 'image/image_t2i_flux3_klein');
    expect(clearKind(pins, 'video')).toEqual(['image/image_t2i_flux3_klein']);
    expect(togglePin(pins, 'video/generation_video#seedance_2_5')).toEqual(['image/image_t2i_flux3_klein']);
  });
});

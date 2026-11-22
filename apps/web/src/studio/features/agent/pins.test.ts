import { describe, expect, it } from 'vitest';
import type { WorkflowRow } from '../jobs/jobForm';
import { aboutOf, clearKind, pinTabs, secondsOf, togglePin } from './pins';

const ROWS: WorkflowRow[] = [
  {
    id: 'video/@seedance_2_5',
    kind: 'video',
    title: 'Seedance 2.5',
    source: 'generation',
    provider: true,
    model: 'seedance_2_5',
    description: 'Strong motion and character consistency, 4 to 15 seconds. 9 credits per second at 480p.',
  },
  {
    id: 'video/@kling_3_0_turbo',
    kind: 'video',
    title: 'Kling 3.0 Turbo',
    source: 'generation',
    provider: true,
    model: 'kling_3_0_turbo',
  },
  {
    id: 'image/@nano-banana-pro',
    kind: 'image',
    title: 'Nano Banana Pro',
    source: 'generation',
    provider: true,
    model: 'nano-banana-pro',
  },
  {
    id: 'audio/@music',
    kind: 'audio',
    title: 'Music',
    source: 'generation',
    provider: true,
    model: 'music',
    description: 'A background-music track, 10 to 120 seconds.',
  },
  { id: 'video/@broken', kind: 'video', title: 'Broken', error: 'unreadable' },
];

describe('the workflows for a chat', () => {
  it('are tabs by kind, each model on its own in the order listed', () => {
    const tabs = pinTabs(ROWS);
    expect(tabs.map((t) => t.label)).toEqual(['Image', 'Video', 'Audio']);
    const video = tabs[1];
    expect(video.models.map((m) => m.value)).toEqual(['video/@seedance_2_5', 'video/@kling_3_0_turbo']); // a broken one is left out
    expect(video.models[0]).toMatchObject({
      title: 'Seedance 2.5',
      about: 'Strong motion and character consistency, 4 to 15 seconds.',
      meta: ['4–15 s'],
    });
    expect(video.models[1]).toMatchObject({ title: 'Kling 3.0 Turbo', about: '', meta: [] }); // no description: its name alone
    expect(tabs[2].models[0]).toMatchObject({ value: 'audio/@music', meta: ['10–120 s'] });
  });

  it('show the studio’s facts and the console’s marks when the listing has them', () => {
    const [video] = pinTabs([
      {
        id: 'video/@seedance_2_5',
        kind: 'video',
        title: 'Seedance 2.5',
        description: 'Strong motion, 4 to 15 seconds.',
        resolution: '1080p',
        seconds: { min: 4, max: 12 },
        sound: true,
        featured: true,
        new: true,
      },
    ]);
    expect(video.models[0]).toMatchObject({ meta: ['1080p', '4–12 s'], sound: true, featured: true, isNew: true });
  });

  it('say no prices and read lengths as people do', () => {
    expect(aboutOf('2K 18, 4K 36 credits per image.')).toBe('');
    expect(secondsOf('Clips of 3-15 s')).toBe('3–15 s');
    expect(secondsOf('Up to 22 s')).toBe('');
  });

  it('are ticked one by one, and "Agent selects" clears a kind', () => {
    let pins = togglePin([], 'video/@seedance_2_5');
    pins = togglePin(pins, 'image/@nano-banana-pro');
    expect(clearKind(pins, 'video')).toEqual(['image/@nano-banana-pro']);
    expect(togglePin(pins, 'video/@seedance_2_5')).toEqual(['image/@nano-banana-pro']);
  });
});

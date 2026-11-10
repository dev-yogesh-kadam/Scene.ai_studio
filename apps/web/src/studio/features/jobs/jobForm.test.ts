import { describe, expect, it } from 'vitest';
import { existingRef, inUse, jobSettings, newForm, warningsOf, type Workflow } from './jobForm';

const wf: Workflow = {
  id: 'video/h3',
  title: 'H3',
  description: '',
  controls: [
    { id: 'p', label: 'Prompt', role: 'prompt', default: '' },
    { id: 'd', label: 'Duration', role: 'duration', default: 5 },
    { id: 'cfg', label: 'CFG', default: 4 },
  ],
  options: [
    {
      id: 'mode',
      label: 'Mode',
      default: 'text',
      choices: [
        { id: 'text', label: 'Text' },
        { id: 'image', label: 'Image' },
      ],
    },
  ],
  refs: [
    { id: 'first', label: 'First frame', kind: 'image', optional: true, when: { mode: 'image' } },
    { id: 'voice', label: 'Voice', kind: 'audio', optional: true },
  ],
  slots: { first_frame: 'first' },
  size: { resolution: 720, orientation: 'landscape' },
  resolutions: [720, 1080],
  chain: true,
  seeded: true,
  confirm: [{ message: 'Long', when: { duration: 15, resolution: 1080 } }],
  hints: [],
};

describe('the one rule for a job', () => {
  it('starts from the workflow defaults, and keeps what was typed', () => {
    const form = newForm(wf, { prompt: 'a fox', projectId: 7 });
    expect(form.values).toEqual({ p: 'a fox', d: 5, cfg: 4 });
    expect(form.options).toEqual({ mode: 'text' });
    expect([form.resolution, form.orientation, form.name, form.projectId]).toEqual([720, 'landscape', 'h3', 7]);
  });

  it('describes the job as the studio takes it', () => {
    const form = { ...newForm(wf, { prompt: 'a fox' }), seed: ' 42 ', clips: 3 };
    expect(jobSettings(form)).toEqual({
      workflow: 'video/h3',
      name: 'h3',
      values: { p: 'a fox', d: 5, cfg: 4 },
      options: { mode: 'text' },
      resolution: 720,
      orientation: 'landscape',
      seed_mode: 'fixed',
      seed: 42,
      clips: 3,
      project_id: null,
      parent: null,
      refs: {},
      keep: undefined,
    });
    expect(jobSettings({ ...form, seed: '' })).toMatchObject({ seed_mode: 'random', seed: null });
    expect(jobSettings({ ...form, wf: { ...wf, chain: false } }).clips).toBe(1);
  });

  it('sends only the references the chosen mode reads', () => {
    const base = newForm(wf);
    const form = {
      ...base,
      refs: { first: existingRef({ comfy_name: 'f.png', name: 'Frame' }), voice: { assetId: 9, name: 'Voice' } },
    };
    expect(jobSettings(form).refs).toEqual({ voice: { asset_id: 9 } }); // "first" belongs to the image mode
    const imageMode = { ...form, options: { mode: 'image' } };
    expect(jobSettings(imageMode).refs).toEqual({
      first: { comfy_name: 'f.png', name: 'Frame' },
      voice: { asset_id: 9 },
    });
    expect(inUse(wf.refs[0], { mode: 'image' })).toBe(true);
  });

  it('finds the warnings that apply to the settings', () => {
    const form = newForm(wf);
    expect(warningsOf(form)).toEqual([]);
    expect(warningsOf({ ...form, resolution: 1080, values: { ...form.values, d: 15 } }).map((w) => w.message)).toEqual([
      'Long',
    ]);
  });
});

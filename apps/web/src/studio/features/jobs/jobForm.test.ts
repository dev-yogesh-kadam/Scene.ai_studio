import { describe, expect, it } from 'vitest';
import {
  existingRef,
  inUse,
  jobSettings,
  lengthChoices,
  newForm,
  offered,
  optionsShown,
  pickerEntries,
  warningsOf,
  type Workflow,
} from './jobForm';

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

// H3 All In One: Best upscale is offered with Upscale video or Sharpen first frame on, and a RESOLUTION field (not a
// size) is what its 1080 warning looks at.
const onOff = (id: string, def = 'off') => ({
  id,
  label: id,
  default: def,
  choices: [
    { id: 'off', label: 'Off' },
    { id: 'on', label: 'On' },
  ],
});
const h3: Workflow = {
  ...wf,
  id: 'video/h3_all_in_one',
  controls: [...wf.controls, { id: '501:value', label: 'RESOLUTION', role: 'resolution', default: 720 }],
  options: [
    onOff('upscale'),
    onOff('sharpen'),
    {
      id: 'best_upscale',
      label: 'Best upscale',
      default: '7b',
      when: [{ upscale: 'on' }, { sharpen: 'on' }],
      choices: [
        { id: '7b', label: 'Best (7B)' },
        { id: '3b', label: 'Fast (3B)' },
      ],
    },
    onOff('smooth'),
  ],
  size: null,
  confirm: [{ message: 'Use 720 + Upscale', when: { resolution: 1080 } }],
};

describe('options some choices leave out', () => {
  it.each([
    ['off', 'off', false],
    ['on', 'off', true],
    ['off', 'on', true],
    ['on', 'on', true],
  ])('Best upscale with Upscale video %s and Sharpen first frame %s is offered: %s', (upscale, sharpen, shown) => {
    const form = { ...newForm(h3), options: { upscale, sharpen, best_upscale: '7b', smooth: 'off' } };
    expect(offered(h3.options[2], form.options)).toBe(shown);
    expect(optionsShown(form).map((o) => o.id)).toEqual(
      shown ? ['upscale', 'sharpen', 'best_upscale', 'smooth'] : ['upscale', 'sharpen', 'smooth'],
    );
  });

  it('starts on the defaults: no upscale, no sharpening, 7B, no smooth motion', () => {
    expect(newForm(h3).options).toEqual({ upscale: 'off', sharpen: 'off', best_upscale: '7b', smooth: 'off' });
  });

  it('warns on a RESOLUTION field of 1080, as on a size', () => {
    const form = newForm(h3);
    expect(warningsOf(form)).toEqual([]);
    expect(warningsOf({ ...form, values: { ...form.values, '501:value': 1080 } }).map((w) => w.message)).toEqual([
      'Use 720 + Upscale',
    ]);
  });
});

// ---------------------------------------------------------------- the providers' models

describe("the providers' models", () => {
  it('are offered one by one, each a workflow of its own', () => {
    const entries = pickerEntries([
      { id: 'video/@seedance_2_5', kind: 'video', title: 'Seedance 2.5', source: 'generation', provider: true },
      { id: 'video/@kling_4_0', kind: 'video', title: 'Kling 4', source: 'generation', provider: true },
    ]);
    expect(entries).toEqual([
      { value: 'video/@seedance_2_5', label: 'Seedance 2.5' },
      { value: 'video/@kling_4_0', label: 'Kling 4' },
    ]);
  });

  it('offer 5, 10 and 15 seconds and the length set now', () => {
    expect(lengthChoices(5)).toEqual([5, 10, 15]);
    expect(lengthChoices(7)).toEqual([5, 7, 10, 15]);
  });
});

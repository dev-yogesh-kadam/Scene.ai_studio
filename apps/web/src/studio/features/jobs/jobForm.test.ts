import { describe, expect, it } from 'vitest';
import {
  existingRef,
  inUse,
  jobSettings,
  lengthChoices,
  newForm,
  offered,
  optionsShown,
  pickValue,
  pickerGroups,
  splitPick,
  warningsOf,
  withModel,
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

// ---------------------------------------------------------------- the generation server's models

const gen: Workflow = {
  ...wf,
  id: 'video/generation_video',
  title: 'Generation video',
  source: 'generation',
  options: [
    {
      id: 'model',
      label: 'Model',
      default: 'minimax_h3_max',
      top: true,
      choices: [
        { id: 'minimax_h3_max', label: 'MiniMax H3 Max' },
        { id: 'kling_3_0_standard', label: 'Kling 3.0 Standard' },
      ],
    },
  ],
  refs: [
    { id: 'first', label: 'First frame', kind: 'image', optional: true },
    { id: 'last', label: 'Last frame', kind: 'image', optional: true },
    { id: 'ref_1', label: 'Reference image 1', kind: 'image', optional: true, order: 1 },
    { id: 'ref_2', label: 'Reference image 2', kind: 'image', optional: true, order: 2 },
  ],
  slots: { first_frame: 'first', last_frame: 'last' },
  models: [
    {
      model: 'minimax_h3_max',
      name: 'MiniMax H3 Max',
      about: '',
      resolutions: ['480p'],
      shapes: ['16:9'],
      sound: 'always',
      frames: ['first', 'last'],
      seconds: { min: 5, max: 15 },
      references: 1,
    },
    {
      model: 'kling_3_0_standard',
      name: 'Kling 3.0 Standard',
      about: '',
      resolutions: ['720p'],
      shapes: ['16:9'],
      sound: 'fixed',
      frames: ['first'],
      seconds: { min: 3, max: 10 },
      references: 0,
    },
  ],
};

describe("the generation server's models", () => {
  it('are offered apart from the ComfyUI workflows, one by one', () => {
    const groups = pickerGroups([
      { id: 'video/h3', kind: 'video', title: 'H3', source: 'comfy' },
      {
        id: 'video/generation_video',
        kind: 'video',
        title: 'Generation video',
        source: 'generation',
        models: [
          { id: 'minimax_h3_max', label: 'MiniMax H3 Max' },
          { id: 'kling_4_0', label: 'Kling 4' },
        ],
      },
    ]);
    expect(groups.map((g) => g.label)).toEqual(['Workflows (ComfyUI)', 'Models (generation server)']);
    expect(groups[0].entries.map((e) => e.value)).toEqual(['video/h3']);
    expect(groups[1].entries.map((e) => e.value)).toEqual([
      'video/generation_video#minimax_h3_max',
      'video/generation_video#kling_4_0',
    ]);
    expect(splitPick('video/generation_video#kling_4_0')).toEqual(['video/generation_video', 'kling_4_0']);
    expect(splitPick('video/h3')).toEqual(['video/h3', null]);
    expect(pickValue(gen, { model: 'kling_3_0_standard' })).toBe('video/generation_video#kling_3_0_standard');
    expect(pickValue(wf, { mode: 'text' })).toBe('video/h3');
    // a generation workflow with no Model setting (lip sync, a voiceover …) is one model of its own
    const solo = pickerGroups([
      { id: 'video/generation_lipsync', kind: 'video', title: 'Generation lip sync', source: 'generation' },
    ]);
    expect(solo).toEqual([
      {
        label: 'Models (generation server)',
        entries: [{ value: 'video/generation_lipsync', label: 'Generation lip sync' }],
      },
    ]);
  });

  it("keep the length within the chosen model's range", () => {
    expect(lengthChoices(gen, { model: 'minimax_h3_max' }, 5)).toEqual([5, 10, 15]);
    expect(lengthChoices(gen, { model: 'kling_3_0_standard' }, 5)).toEqual([3, 5, 10]);
    expect(lengthChoices(wf, { mode: 'text' }, 7)).toEqual([5, 7, 10, 15]);
    const moved = withModel(gen, { model: 'minimax_h3_max' }, { d: 15 }, 'kling_3_0_standard');
    expect(moved).toEqual({ options: { model: 'kling_3_0_standard' }, values: { d: 10 } });
  });

  it("show only the model's own frames and references", () => {
    const h3 = { model: 'minimax_h3_max' };
    const kling = { model: 'kling_3_0_standard' };
    expect(gen.refs.filter((r) => inUse(r, h3, gen)).map((r) => r.id)).toEqual(['first', 'last', 'ref_1']);
    expect(gen.refs.filter((r) => inUse(r, kling, gen)).map((r) => r.id)).toEqual(['first']);
    expect(gen.refs.filter((r) => inUse(r, kling)).length).toBe(4); // without the workflow: the presets file alone
  });
});

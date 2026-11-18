import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { ProvidersPart } from './Providers';
import {
  checkWords,
  keyWords,
  manyWords,
  unlockWords,
  wholeOrNull,
  type CoverageData,
  type ProviderKey,
  type ProvidersData,
} from './providerWords';

const KEY: ProviderKey = {
  id: 7,
  provider_id: 3,
  label: 'studio A',
  last4: '1234',
  has_secret: true,
  active: true,
  priority: 0,
  max_concurrent: null,
  daily_cap: null,
  status: 'ok',
  cooldown_until: null,
  last_error: '',
  last_checked: 1,
  last_used: null,
  fixed: false,
  credits: { available: 91296 },
  alerts: [],
  mode: 'live',
  said_max_concurrent: 2,
};

const DATA: ProvidersData = {
  kinds: {
    scene_provider_v1: 'Scene provider (v1)',
    comfyui: 'ComfyUI',
    anthropic: 'Anthropic',
  },
  self_hosted: ['scene_provider_v1', 'comfyui'],
  providers: [
    {
      id: 1,
      kind: 'anthropic',
      kind_name: 'Anthropic',
      name: 'Anthropic',
      base_url: '',
      active: true,
      priority: 0,
      legacy: 'claude:anthropic',
      keys: [],
      models: 0,
      agent: true,
    },
  ],
  router: 'off',
  modes: ['off', 'shadow', 'on'],
  agent_provider: 1,
  testing: '',
};

const WITH_V1: ProvidersData = {
  ...DATA,
  providers: [
    ...DATA.providers,
    {
      id: 3,
      kind: 'scene_provider_v1',
      kind_name: 'Scene provider (v1)',
      name: 'Zoro',
      base_url: 'http://100.123.221.34:8189',
      active: true,
      priority: 0,
      legacy: '',
      keys: [KEY],
      models: 22,
      agent: false,
    },
  ],
};

const COVERAGE: CoverageData = {
  router: 'on',
  capabilities: [
    {
      capability: 'transcribe',
      words: 'Transcription',
      models: [
        {
          id: 'transcribe',
          name: 'Transcription',
          providers: ['Zoro'],
          keys: [{ label: 'A', mode: 'live', status: 'ok' }],
        },
      ],
      live: true,
      comfy: [{ id: 'audio/audio_transcribe', title: 'Transcribe Audio' }],
      comfyui_on: true,
      can_switch_off: true,
      why_not: '',
      state: 'both',
    },
    {
      capability: 'outpaint',
      words: 'Outpaint',
      models: [],
      live: false,
      comfy: [{ id: 'video/video_outpaint_wan_vace', title: 'Outpaint' }],
      comfyui_on: true,
      can_switch_off: false,
      why_not: 'No provider key offers it yet.',
      state: 'comfyui',
    },
    {
      capability: 'music',
      words: 'Music',
      models: [],
      live: false,
      comfy: [],
      comfyui_on: true,
      can_switch_off: false,
      why_not: 'x',
      state: 'none',
    },
  ],
};

// What was sent to the studio; each answer is the next of `answers`. What makes what (asked when the part shows) is
// answered with `coverage` and not counted, unless it is a change (PUT).
function serve(...answers: unknown[]) {
  return serveWith(COVERAGE, ...answers);
}

function serveWith(coverage: CoverageData, ...answers: unknown[]) {
  const sent: { url: string; method: string; body: Record<string, unknown> }[] = [];
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: string, init?: RequestInit) => {
      if (String(input).endsWith('/capabilities') && (init?.method ?? 'GET') === 'GET')
        return new Response(JSON.stringify(coverage), { status: 200, headers: { 'Content-Type': 'application/json' } });
      sent.push({
        url: String(input),
        method: init?.method ?? 'GET',
        body: JSON.parse(String(init?.body ?? '{}')) as Record<string, unknown>,
      });
      return new Response(JSON.stringify(answers.shift() ?? {}), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      });
    }),
  );
  return sent;
}

describe('the words of the Providers part', () => {
  it('says a check as the console shows it', () => {
    expect(checkWords({ ok: true, status: 'ok', error: '', models: 22, credits: 91296 })).toBe(
      'Works · 22 models · 91,296 credits',
    );
    expect(checkWords({ ok: false, status: 'invalid', error: 'This key was revoked.', models: 0 })).toBe(
      'It does not work: This key was revoked.',
    );
  });

  it('says a key: its status, a rest, a test key, its credits', () => {
    expect(keyWords(KEY)).toBe('Works · 91,296 credits');
    expect(
      keyWords({ ...KEY, status: 'rate_limited', cooldown_until: 1000 + 90, mode: 'test', credits: null }, 1000),
    ).toBe('Rate limited · resting 2 min · test key');
    expect(keyWords({ ...KEY, active: false })).toBe('Off · 91,296 credits');
  });

  it('reads a limit typed or left empty', () => {
    expect(wholeOrNull(' ')).toBeNull();
    expect(wholeOrNull('4')).toBe(4);
    expect(() => wholeOrNull('4.5')).toThrow('not a whole number');
  });
});

describe('the Providers part', () => {
  afterEach(() => vi.unstubAllGlobals());

  it('adds a key: the address once, then the check says it works and the key is never shown', async () => {
    const user = userEvent.setup();
    const sent = serve({
      ...WITH_V1,
      saved: true,
      check: { ok: true, status: 'ok', error: '', models: 22, credits: 91296 },
    });
    render(<ProvidersPart data={DATA} refresh={async () => undefined} />);
    await user.click(screen.getByRole('button', { name: 'Add key' }));
    await user.selectOptions(screen.getByLabelText('Provider'), 'new:scene_provider_v1');
    await user.type(screen.getByLabelText('Name'), 'Zoro');
    await user.type(screen.getByLabelText('Address'), 'http://100.123.221.34:8189');
    await user.type(screen.getByLabelText('Label'), 'studio A');
    await user.type(screen.getByLabelText('Key'), 'sa_live_alpha1234');
    await user.click(screen.getByRole('button', { name: 'Save' }));
    expect(sent[0]).toMatchObject({
      url: '/api/admin/providers/keys',
      method: 'POST',
      body: {
        kind: 'scene_provider_v1',
        name: 'Zoro',
        base_url: 'http://100.123.221.34:8189',
        label: 'studio A',
        secret: 'sa_live_alpha1234',
        save_anyway: false,
        max_concurrent: null,
        daily_cap: null,
      },
    });
    expect(screen.queryByTestId('add-key')).not.toBeInTheDocument(); // it worked: the form closes
    const card = screen.getByTestId('provider-3');
    expect(within(card).getByText('…1234')).toBeInTheDocument();
    expect(within(card).getByText('Works · 91,296 credits')).toBeInTheDocument();
    expect(document.body.textContent).not.toContain('sa_live_alpha1234');
  });

  it("a key that fails is not saved; it shows the provider's words, and Save anyway saves it", async () => {
    const user = userEvent.setup();
    const failing = { ok: false, status: 'invalid', error: 'This key is not known.', models: 0 };
    const sent = serve({ ...DATA, saved: false, check: failing }, { ...WITH_V1, saved: true, check: failing });
    render(<ProvidersPart data={WITH_V1} refresh={async () => undefined} />);
    await user.click(screen.getByRole('button', { name: 'Add key' }));
    await user.selectOptions(screen.getByLabelText('Provider'), '3');
    expect(screen.queryByLabelText('Address')).not.toBeInTheDocument(); // an existing provider: only the key
    await user.type(screen.getByLabelText('Key'), 'sa_live_wrong0000');
    await user.click(screen.getByRole('button', { name: 'Save' }));
    expect(screen.getByText('It does not work: This key is not known.')).toBeInTheDocument();
    expect(sent[0].body).toMatchObject({ provider_id: 3, save_anyway: false });
    await user.click(screen.getByRole('button', { name: 'Save anyway' }));
    expect(sent[1].body).toMatchObject({ provider_id: 3, save_anyway: true, secret: 'sa_live_wrong0000' });
  });

  it('switches the router and says what each position does', async () => {
    const user = userEvent.setup();
    const sent = serve({ ...DATA, router: 'shadow' });
    render(<ProvidersPart data={DATA} refresh={async () => undefined} />);
    expect(screen.getByTestId('router-words')).toHaveTextContent('Off: renders go the way they always did');
    await user.click(screen.getByRole('button', { name: 'Shadow' }));
    expect(sent[0]).toMatchObject({ url: '/api/admin/providers/router', method: 'PUT', body: { mode: 'shadow' } });
    expect(screen.getByTestId('router-words')).toHaveTextContent('Shadow: renders go the way they always did');
  });

  it('shows what a key unlocks', () => {
    serve();
    const unlocks = [
      { capability: 'text_to_video', words: 'Video', models: [{ id: 'seedance_2_5', name: 'Seedance 2.5' }] },
      { capability: 'speech', words: 'Voiceover', models: [{ id: 'speech', name: 'Speech' }] },
    ];
    const data = {
      ...WITH_V1,
      providers: [DATA.providers[0], { ...WITH_V1.providers[1], keys: [{ ...KEY, unlocks }] }],
    };
    render(<ProvidersPart data={data} refresh={async () => undefined} />);
    expect(screen.getByTestId('unlocks-7')).toHaveTextContent('Unlocks Video: Seedance 2.5 · Voiceover: Speech');
  });

  it('pastes several keys: each line is said, and a new provider is made once', async () => {
    const user = userEvent.setup();
    const ok = { ok: true, status: 'ok', error: '', models: 3 };
    const bad = { ok: false, status: 'invalid', error: 'This key is not known.', models: 0 };
    const sent = serve(
      {
        ...WITH_V1,
        saved: 1,
        provider_id: 3,
        results: [
          { line: 1, label: 'Video key', saved: true, check: ok },
          { line: 2, label: '', saved: false, check: bad },
        ],
      },
      {
        ...WITH_V1,
        saved: 1,
        provider_id: 3,
        results: [{ line: 1, label: 'Video key', saved: false, check: ok, words: 'Already here as Video key' }],
      },
    );
    render(<ProvidersPart data={DATA} refresh={async () => undefined} />);
    await user.click(screen.getByRole('button', { name: 'Add key' }));
    await user.selectOptions(screen.getByLabelText('Provider'), 'new:scene_provider_v1');
    await user.click(screen.getByRole('button', { name: 'Several keys' }));
    expect(screen.queryByLabelText('Label')).not.toBeInTheDocument(); // labels come with the lines
    await user.type(screen.getByLabelText('Address'), 'http://100.71.159.106:8189');
    await user.type(screen.getByLabelText('Keys'), 'Video key\tsa_live_alpha1234{enter}sa_live_wrong0000');
    await user.click(screen.getByRole('button', { name: 'Save' }));
    expect(sent[0]).toMatchObject({
      url: '/api/admin/providers/keys/many',
      method: 'POST',
      body: { kind: 'scene_provider_v1', base_url: 'http://100.71.159.106:8189', save_anyway: false },
    });
    expect(String(sent[0].body.text)).toContain('sa_live_wrong0000');
    const said = screen.getByTestId('paste-results');
    expect(said).toHaveTextContent('Line 1 · Video key: Saved · Works · 3 models');
    expect(said).toHaveTextContent('Line 2: It does not work: This key is not known.');
    await user.click(screen.getByRole('button', { name: 'Save anyway' }));
    expect(sent[1].body).toMatchObject({ provider_id: 3, save_anyway: true }); // to the provider just made
    expect(sent[1].body.kind).toBeUndefined();
  });

  it('says what makes what, and stops ComfyUI for one kind of work', async () => {
    const user = userEvent.setup();
    const after: CoverageData = {
      ...COVERAGE,
      capabilities: [
        { ...COVERAGE.capabilities[0], comfyui_on: false, state: 'provider' },
        ...COVERAGE.capabilities.slice(1),
      ],
    };
    const sent = serve(after);
    render(<ProvidersPart data={WITH_V1} refresh={async () => undefined} />);
    const transcribe = await screen.findByTestId('capability-transcribe');
    expect(transcribe).toHaveTextContent('Providers and ComfyUI');
    expect(screen.queryByTestId('capability-music')).not.toBeInTheDocument(); // nothing makes it: not listed
    const outpaint = screen.getByTestId('capability-outpaint');
    expect(within(outpaint).getByRole('button', { name: 'Stop using ComfyUI' })).toBeDisabled();
    expect(outpaint).toHaveTextContent('No provider key offers it yet.');
    expect(screen.getByTestId('what-makes-what')).toHaveTextContent('ComfyUI still makes 2 kinds of work');
    await user.click(within(transcribe).getByRole('button', { name: 'Stop using ComfyUI' }));
    expect(sent[0]).toMatchObject({
      url: '/api/admin/providers/capabilities/transcribe',
      method: 'PUT',
      body: { comfyui: false },
    });
    expect(await screen.findByText('Providers only')).toBeInTheDocument();
    expect(
      within(screen.getByTestId('capability-transcribe')).getByRole('button', { name: 'Use ComfyUI again' }),
    ).toBeEnabled();
  });
});

describe('the words of a paste and of what a key unlocks', () => {
  it('says each', () => {
    expect(
      unlockWords([
        {
          capability: 'image',
          words: 'Pictures',
          models: [
            { id: 'a', name: 'A' },
            { id: 'b', name: 'B' },
          ],
        },
      ]),
    ).toBe('Pictures: A, B');
    expect(unlockWords(undefined)).toBe('');
    const ok = { ok: true, status: 'ok', error: '', models: 1 };
    expect(manyWords({ line: 1, label: '', saved: false, check: ok, words: 'Already here as A' })).toBe(
      'Already here as A',
    );
    expect(manyWords({ line: 1, label: '', saved: true, check: { ...ok, ok: false, error: 'Down' } })).toBe(
      'Saved, though it does not work: Down',
    );
  });
});

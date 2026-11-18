import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { ClaudeOnThisPC } from './ClaudeConnection';
import { ProvidersPart } from './Providers';
import { signInWords, usageWords, type ClaudeStatus } from './claude';
import { type ProvidersData } from './providerWords';

const SIGNED_IN: ClaudeStatus = {
  mode: 'this_pc',
  online: true,
  claude_version: '2.1.322',
  signed_in: true,
  account: 'owner@example.com',
  plan: 'pro',
  session: { utilization: 0.27, resets_at: null },
  week: { utilization: 0.34, resets_at: null },
  running: 2,
  limit: 3,
  testing: 'Personal Claude subscription',
};
const SIGNED_OUT: ClaudeStatus = {
  mode: 'this_pc',
  online: false,
  signed_in: false,
  detail: 'Signed out. Press Sign in on Claude on this PC, in Servers & APIs → Providers.',
  session: null,
  week: null,
  running: 0,
  limit: 3,
};

const LOCAL = {
  id: 9,
  kind: 'claude_local',
  kind_name: 'Claude on this PC',
  name: 'Claude on this PC',
  base_url: '',
  active: true,
  priority: 0,
  legacy: 'claude:local',
  keys: [],
  models: 0,
  agent: true,
  keyless: true,
};
const DATA: ProvidersData = {
  kinds: { claude_local: 'Claude on this PC', anthropic: 'Anthropic', comfyui: 'ComfyUI' },
  self_hosted: ['comfyui'],
  keyless: ['claude_local'],
  providers: [
    LOCAL,
    {
      ...LOCAL,
      id: 1,
      kind: 'anthropic',
      kind_name: 'Anthropic',
      name: 'Anthropic',
      legacy: '',
      agent: false,
      keyless: false,
    },
  ],
  router: 'off',
  modes: ['off', 'shadow', 'on'],
  agent_provider: 9,
  testing: 'Personal Claude subscription',
};

function serve(...answers: unknown[]) {
  const sent: { url: string; method: string }[] = [];
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: string, init?: RequestInit) => {
      sent.push({ url: String(input), method: init?.method ?? 'GET' });
      return new Response(JSON.stringify(answers.shift() ?? {}), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      });
    }),
  );
  return sent;
}

describe('Claude on this PC', () => {
  afterEach(() => vi.unstubAllGlobals());

  it('signed in: the account, the plan and Claude Code; the usage; how many run; the pill', () => {
    render(
      <ClaudeOnThisPC
        name="Claude on this PC"
        inUse
        status={SIGNED_IN}
        testing="Personal Claude subscription"
        refresh={async () => undefined}
      />,
    );
    expect(screen.getByTestId('claude-signin')).toHaveTextContent(
      'Signed in as owner@example.com · Pro · Claude Code 2.1.322',
    );
    expect(screen.getByTestId('claude-usage')).toHaveTextContent('This 5-hour window: 27% · This week: 34%');
    expect(screen.getByText('2 of 3 running')).toBeInTheDocument();
    expect(screen.getByText('Personal Claude subscription')).toBeInTheDocument();
  });

  it('signed out: the reason and the fix, and no usage reported yet', () => {
    render(
      <ClaudeOnThisPC name="Claude on this PC" inUse status={SIGNED_OUT} testing="" refresh={async () => undefined} />,
    );
    expect(screen.getByTestId('claude-signin')).toHaveTextContent('Signed out. Press Sign in');
    expect(screen.getByTestId('claude-usage')).toHaveTextContent('Usage shows after the first call');
  });

  it('Check asks again and shows what it found', async () => {
    const user = userEvent.setup();
    const sent = serve({ connection: {}, status: SIGNED_OUT, test: SIGNED_IN });
    const refresh = vi.fn(async () => undefined);
    render(<ClaudeOnThisPC name="Claude on this PC" inUse status={SIGNED_OUT} testing="" refresh={refresh} />);
    await user.click(screen.getByRole('button', { name: 'Check' }));
    expect(sent[0]).toMatchObject({ url: '/api/admin/claude-connection/test', method: 'POST' });
    expect(await screen.findByText('Checked: it works.')).toBeInTheDocument();
    expect(screen.getByTestId('claude-signin')).toHaveTextContent('Signed in as owner@example.com');
    expect(refresh).toHaveBeenCalled();
  });

  it('Sign in opens the claude.com page and sends the code it shows', async () => {
    const user = userEvent.setup();
    const opened = vi.fn();
    vi.stubGlobal('open', opened);
    const LINK = 'https://claude.com/cai/oauth/authorize?code=true&state=s1';
    const sent = serve({ link: LINK }, { connection: {}, status: SIGNED_IN });
    const refresh = vi.fn(async () => undefined);
    render(<ClaudeOnThisPC name="Claude on this PC" inUse status={SIGNED_OUT} testing="" refresh={refresh} />);
    expect(screen.queryByRole('button', { name: 'Sign out' })).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Sign in' }));
    expect(sent[0]).toMatchObject({ url: '/api/admin/claude-connection/signin', method: 'POST' });
    expect(opened).toHaveBeenCalledWith(LINK, '_blank', 'noopener');
    const box = await screen.findByTestId('claude-signin-code');
    expect(within(box).getByRole('link')).toHaveAttribute('href', LINK);
    await user.type(within(box).getByLabelText('Code'), 'good-code#s1');
    await user.click(within(box).getByRole('button', { name: 'Sign in' }));
    expect(sent[1]).toMatchObject({ url: '/api/admin/claude-connection/signin/code', method: 'POST' });
    expect(await screen.findByText('Signed in as owner@example.com.')).toBeInTheDocument();
    expect(screen.queryByTestId('claude-signin-code')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Switch account' })).toBeInTheDocument();
    expect(refresh).toHaveBeenCalled();
  });

  it('signed in: Switch account and Sign out', async () => {
    const user = userEvent.setup();
    vi.stubGlobal('confirm', () => true);
    const sent = serve({ connection: {}, status: SIGNED_OUT });
    render(
      <ClaudeOnThisPC name="Claude on this PC" inUse status={SIGNED_IN} testing="" refresh={async () => undefined} />,
    );
    await user.click(screen.getByRole('button', { name: 'Sign out' }));
    expect(sent[0]).toMatchObject({ url: '/api/admin/claude-connection/signout', method: 'POST' });
    expect(await screen.findByText('Signed out.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Sign in' })).toBeInTheDocument();
  });

  it('not in use: says how to pick it, with no Check', () => {
    render(<ClaudeOnThisPC name="Claude on this PC" inUse={false} testing="" refresh={async () => undefined} />);
    expect(screen.getByText(/Not in use/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Check' })).not.toBeInTheDocument();
  });

  it('in the Providers: a choice of The agent uses, one card with no key field, and not in Add key', async () => {
    const user = userEvent.setup();
    render(<ProvidersPart data={DATA} claude={SIGNED_IN} refresh={async () => undefined} />);
    const picker = screen.getByLabelText('The agent uses');
    expect(within(picker).getByRole('option', { name: 'Claude on this PC (Claude on this PC)' })).toBeInTheDocument();
    const card = screen.getByTestId('claude-on-this-pc');
    expect(within(card).queryByRole('textbox')).not.toBeInTheDocument();
    expect(within(card).queryByLabelText('Key')).not.toBeInTheDocument();
    expect(within(card).queryByRole('button', { name: 'Remove' })).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Add key' }));
    const providers = within(screen.getByTestId('add-key')).getByLabelText('Provider');
    expect(within(providers).queryByRole('option', { name: /Claude on this PC/ })).not.toBeInTheDocument();
  });

  it('words: a passed reset time is not shown; a plan name is capitalized', () => {
    expect(signInWords({ online: true, plan: 'max' })).toBe('Signed in · Max');
    expect(usageWords({ session: { utilization: 0, resets_at: null }, week: null })).toBe('This 5-hour window: 0%');
    expect(usageWords({ session: { utilization: 0.5, resets_at: 1 } })).toMatch(
      /^This 5-hour window: 50% \(resets \d\d:\d\d\)$/,
    );
  });
});

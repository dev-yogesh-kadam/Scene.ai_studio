import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { ClaudeConnectionCard, type ConnectionData } from './ClaudeConnection';

const BRIDGE: ConnectionData = {
  connection: {
    mode: 'lufi_bridge',
    bridge_url: 'http://100.64.0.7:8765',
    has_bridge_key: true,
    has_api_key: false,
    fixed: [],
    testing: 'Testing on a personal Claude subscription',
  },
  status: { mode: 'lufi_bridge', online: true, claude_version: '2.1.3', signed_in: true, running: 1, limit: 4 },
};

// What was sent to the studio; each answer is the next of `answers`.
function serve(...answers: unknown[]) {
  const sent: { url: string; method: string; body: Record<string, unknown> }[] = [];
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: string, init?: RequestInit) => {
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

describe('the Claude connection card', () => {
  afterEach(() => vi.unstubAllGlobals());

  it('says how the connection is, that it is testing, and shows no key', () => {
    render(<ClaudeConnectionCard data={BRIDGE} refresh={async () => undefined} />);
    expect(screen.getByTestId('claude-status')).toHaveTextContent(
      'LUFI bridge · Claude Code 2.1.3 · signed in · 1 of 4 calls running',
    );
    expect(screen.getAllByText('Testing on a personal Claude subscription').length).toBeGreaterThan(0);
    expect(screen.getByLabelText('Bridge address')).toHaveValue('http://100.64.0.7:8765');
    const key = screen.getByLabelText('Bridge key');
    expect(key).toHaveValue('');
    expect(key).toHaveAttribute('placeholder', 'Kept unless you type a new one');
  });

  it('says why it does not work', () => {
    render(
      <ClaudeConnectionCard
        data={{ ...BRIDGE, status: { mode: 'lufi_bridge', online: false, detail: 'The bridge key is wrong.' } }}
        refresh={async () => undefined}
      />,
    );
    expect(screen.getByTestId('claude-status')).toHaveTextContent('Not working: The bridge key is wrong.');
  });

  it('switching is one change: pick the API key, paste it, save; a blank key is not sent', async () => {
    const after: ConnectionData = {
      connection: { ...BRIDGE.connection, mode: 'api_key', has_api_key: true, testing: '' },
      status: { mode: 'api_key', online: true, key_works: true, claude_version: '2.1.3', running: 0 },
    };
    const sent = serve(after);
    const refresh = vi.fn(async () => undefined);
    const user = userEvent.setup();
    render(<ClaudeConnectionCard data={BRIDGE} refresh={refresh} />);
    await user.click(screen.getByRole('button', { name: 'Anthropic API key' }));
    await user.type(screen.getByLabelText('Anthropic API key'), 'sk-ant-new');
    await user.click(screen.getByRole('button', { name: 'Save' }));
    expect(sent[0]).toEqual({
      url: '/api/admin/claude-connection',
      method: 'PUT',
      body: { mode: 'api_key', api_key: 'sk-ant-new' },
    });
    expect(await screen.findByText('Saved: in use from the next call.')).toBeInTheDocument();
    expect(screen.getByTestId('claude-status')).toHaveTextContent('Anthropic API key · Claude Code 2.1.3 · key works');
    expect(screen.getByLabelText('Anthropic API key')).toHaveValue(''); // never kept on the page
    expect(refresh).toHaveBeenCalled();
  });

  it('the bridge keeps its key when the field is left blank', async () => {
    const sent = serve(BRIDGE);
    const user = userEvent.setup();
    render(<ClaudeConnectionCard data={BRIDGE} refresh={async () => undefined} />);
    await user.click(screen.getByRole('button', { name: 'Save' }));
    expect(sent[0].body).toEqual({ mode: 'lufi_bridge', bridge_url: 'http://100.64.0.7:8765' });
  });

  it('Test says whether it works', async () => {
    const sent = serve({
      ...BRIDGE,
      test: { ...BRIDGE.status, online: false, detail: 'Claude on LUFI is signed out.' },
    });
    const user = userEvent.setup();
    render(<ClaudeConnectionCard data={BRIDGE} refresh={async () => undefined} />);
    await user.click(screen.getByRole('button', { name: 'Test' }));
    expect(sent[0]).toMatchObject({ url: '/api/admin/claude-connection/test', method: 'POST' });
    expect(await screen.findByText('It does not work: Claude on LUFI is signed out.')).toBeInTheDocument();
  });

  it('a setting the environment fixes is shown, not changed here', () => {
    render(
      <ClaudeConnectionCard
        data={{ ...BRIDGE, connection: { ...BRIDGE.connection, fixed: ['claude_bridge_key'] } }}
        refresh={async () => undefined}
      />,
    );
    const key = screen.getByLabelText('Bridge key');
    expect(key).toBeDisabled();
    expect(key).toHaveAttribute('placeholder', 'Set by SCENE_CLAUDE_BRIDGE_KEY');
  });
});

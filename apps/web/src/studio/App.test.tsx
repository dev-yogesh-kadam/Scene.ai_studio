import { render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { App, createRouter, makeQueryClient } from './App';

// The studio's answers, by path; anything else is a 404.
function serve(answers: Record<string, { status?: number; body: unknown }>) {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: string) => {
      const path = String(input).split('?')[0];
      const found = answers[path] ?? { status: 404, body: { detail: 'Not Found' } };
      return new Response(JSON.stringify(found.body), {
        status: found.status ?? 200,
        headers: { 'Content-Type': 'application/json' },
      });
    }),
  );
}

// A live connection that never opens: the shell polls instead.
class QuietSocket {
  static OPEN = 1;
  readyState = 0;
  onopen = null;
  onmessage = null;
  onclose = null;
  send() {}
  close() {}
}

const ADA = { id: 1, email: 'ada@example.com', name: 'Ada', role: 'admin', credits: 1250, created: 0, mfa_enabled: 0 };

function open(path: string) {
  history.replaceState(null, '', path);
  return render(<App client={makeQueryClient()} router={createRouter()} />);
}

describe('the studio', () => {
  beforeEach(() => vi.stubGlobal('WebSocket', QuietSocket));
  afterEach(() => vi.unstubAllGlobals());

  it('asks someone who is not signed in to sign in', async () => {
    serve({
      '/api/auth/me': { status: 401, body: { detail: 'Not signed in.' } },
      '/api/auth/state': { body: { first_run: false, signup_open: true } },
    });
    open('/library');
    expect(await screen.findByRole('heading', { name: 'Welcome back' })).toBeInTheDocument();
    const card = document.querySelector<HTMLElement>('.auth-card')!; // the landing's sections below have their own buttons
    expect(within(card).getByRole('button', { name: 'Create an account' })).toBeInTheDocument();
  });

  it('opens Create account at /signup', async () => {
    serve({
      '/api/auth/me': { status: 401, body: {} },
      '/api/auth/state': { body: { first_run: true, signup_open: true } },
    });
    open('/signup');
    expect(await screen.findByRole('heading', { name: 'Set up Scene.ai' })).toBeInTheDocument();
  });

  it('draws the shell for a signed-in user: pages, balance, queue and account', async () => {
    serve({
      '/api/auth/me': { body: ADA },
      '/api/jobs': {
        body: {
          jobs: [
            { id: 'a', status: 'running' },
            { id: 'b', status: 'done' },
          ],
        },
      },
      '/api/status': { body: { page: 5 } },
      '/api/announcement': { body: {} },
    });
    open('/home');
    const sidebar = await screen.findByRole('complementary', { name: 'Scene.ai' });
    expect(within(sidebar).getByRole('link', { name: 'Home' })).toHaveClass('on');
    expect(within(sidebar).getByRole('link', { name: 'All projects' })).toBeInTheDocument();
    expect(await within(sidebar).findByText('1 job in the queue')).toBeInTheDocument();
    expect(within(sidebar).queryByText(/render server/i)).toBeNull(); // there is none: every model is a provider's
    expect(screen.getByTitle(/Credits pay for generations/)).toHaveTextContent('1,250credits');
    expect(screen.getByRole('button', { name: /^Ada ?: your account$/ })).toHaveTextContent('Ada');
    expect(document.title).toBe('Home · Scene.ai');
  });

  it('moves an address with no page to All projects', async () => {
    serve({ '/api/auth/me': { body: ADA }, '/api/jobs': { body: { jobs: [] } }, '/api/announcement': { body: {} } });
    open('/nowhere');
    await waitFor(() => expect(location.pathname).toBe('/projects'));
  });
});

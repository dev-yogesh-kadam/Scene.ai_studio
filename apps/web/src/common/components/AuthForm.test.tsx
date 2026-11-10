import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { AuthForm } from './AuthForm';

// What was sent to the studio, and a signed-in user back.
function serve() {
  const sent: { url: string; body: Record<string, unknown> }[] = [];
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: string, init?: RequestInit) => {
      sent.push({ url: String(input), body: JSON.parse(String(init?.body ?? '{}')) as Record<string, unknown> });
      return new Response(JSON.stringify({ id: 2, email: 'b@example.com', name: 'B' }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      });
    }),
  );
  return sent;
}

async function fill(user: ReturnType<typeof userEvent.setup>) {
  await user.type(screen.getByLabelText('Email'), 'b@example.com');
  await user.type(screen.getByLabelText('Password'), 'long enough');
}

describe('the sign-up form', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    history.replaceState(null, '', '/');
  });

  it('asks for the invite code when the studio wants one, filled in from ?invite=, and sends it', async () => {
    history.replaceState(null, '', '/signup?invite=OPEN-SESAME');
    const sent = serve();
    const user = userEvent.setup();
    render(
      <AuthForm
        mode="register"
        onMode={() => undefined}
        info={{ first_run: false, signup_open: true, invite_required: true }}
        onSignedIn={() => undefined}
      />,
    );
    const code = screen.getByLabelText('Invite code');
    expect(code).toHaveValue('OPEN-SESAME');
    expect(code).toBeRequired();
    await fill(user);
    await user.click(screen.getByRole('button', { name: 'Create account' }));
    expect(sent[0]).toMatchObject({
      url: '/api/auth/register',
      body: { invite: 'OPEN-SESAME', email: 'b@example.com' },
    });
  });

  it('has no invite code field, and sends none, when the studio asks for none', async () => {
    const sent = serve();
    const user = userEvent.setup();
    render(
      <AuthForm
        mode="register"
        onMode={() => undefined}
        info={{ first_run: false, signup_open: true }}
        onSignedIn={() => undefined}
      />,
    );
    expect(screen.queryByLabelText('Invite code')).toBeNull();
    await fill(user);
    await user.click(screen.getByRole('button', { name: 'Create account' }));
    expect(sent[0].body).not.toHaveProperty('invite');
  });

  it('says new accounts are closed when they are, and offers no way to make one', () => {
    render(
      <AuthForm
        mode="login"
        onMode={() => undefined}
        info={{ first_run: false, signup_open: false }}
        onSignedIn={() => undefined}
        closedNote="New accounts are closed on this studio. Ask its admin for access."
      />,
    );
    expect(screen.getByRole('note')).toHaveTextContent('New accounts are closed');
    expect(screen.queryByRole('button', { name: 'Create an account' })).toBeNull();
  });
});

// The admin console: a site of its own beside the studio, on its own port, with its own sign-in (email, password, and
// the second step when it is on). Only an admin (or a staff role) can sign in. One section per address.

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useCallback, useEffect, useState } from 'react';
import { RouterProvider, createBrowserRouter } from 'react-router';
import { api, setOnUnauthorized } from '../common/api';
import { AuthForm, type AuthMode } from '../common/components/AuthForm';
import { OverlayHost } from '../common/components/OverlayHost';
import { SignInSet } from '../common/landing/SignInSet';
import { LinkClicks } from '../common/LinkClicks';
import { ConsoleShell } from './ConsoleShell';
import { FIRST, SECTIONS } from './sectionList';
import type { ConsoleUser } from './sections/shared/context';

const here = () => location.pathname.replace(/\/+$/, '') || '/';

function Root() {
  const [user, setUser] = useState<ConsoleUser | null | undefined>(undefined);
  const [message, setMessage] = useState('');

  useEffect(() => {
    api<ConsoleUser>('/api/console/me').then(
      (me) => {
        if (here() === '/signin' || here() === '/') history.replaceState(null, '', FIRST);
        setUser(me);
      },
      () => setUser(null),
    );
    // A call refused for want of a sign-in (it ran out, or the account stopped being an admin) leads back to signing in.
    const ended = () =>
      setUser((was) => {
        if (was) setMessage('Your sign-in to the console ended. Sign in again.');
        return null;
      });
    setOnUnauthorized((path) => {
      if (path !== '/api/console/login') ended();
    });
    window.addEventListener('scene:signed-out', ended);
    return () => {
      setOnUnauthorized(null);
      window.removeEventListener('scene:signed-out', ended);
    };
  }, []);

  const signOut = useCallback(async () => {
    await api('/api/console/logout', { method: 'POST' }).catch(() => {});
    setMessage('');
    setUser(null);
  }, []);

  if (user === undefined) return null;
  if (!user) return <ConsoleSignIn message={message} onSignedIn={setUser} />;
  return <ConsoleShell user={user} onSignOut={() => void signOut()} />;
}

/** Sign in: email and password, then the authenticator code when the account has two-step sign-in on. */
function ConsoleSignIn({ message, onSignedIn }: { message: string; onSignedIn: (user: ConsoleUser) => void }) {
  const [mode, setMode] = useState<AuthMode>('login');
  // A section's address opened before signing in is where signing in lands.
  const [wanted] = useState(() =>
    SECTIONS.some((s) => '/' + s.id === '/' + (here().split('/')[1] || '')) ? here() : FIRST,
  );
  useEffect(() => {
    document.title = 'Admin console · Scene.ai';
    if (here() !== '/signin') history.replaceState(null, '', '/signin');
  }, []);
  return (
    <SignInSet
      scene="deep"
      heading={
        <>
          Admin
          <br />
          <b>console.</b>
        </>
      }
      sub="The queue, the render server, users, credits and pricing of the studio. For its admins only."
      points={['Its own address, apart from the studio', 'Its own sign-in', 'Every change goes into the audit log']}
      tag={mode === 'code' ? 'Two-step' : 'Admin sign-in'}
    >
      {message && mode === 'login' && <p className="error notice">{message}</p>}
      <AuthForm
        mode={mode}
        onMode={setMode}
        info={{ first_run: false, signup_open: false }}
        loginPath="/api/console/login"
        copy={{
          title: 'Admin sign-in',
          sub: 'With the email and password of an admin account of the studio.',
          codeSub: 'Enter the 6-digit code your authenticator app shows for Scene.ai, or one of your recovery codes.',
          emailAutocomplete: 'username',
        }}
        onSignedIn={(user) => {
          history.replaceState(null, '', wanted);
          onSignedIn(user as unknown as ConsoleUser);
        }}
      />
    </SignInSet>
  );
}

const router = createBrowserRouter([
  {
    path: '*',
    element: (
      <>
        <LinkClicks />
        <Root />
      </>
    ),
  },
]);

// A section shows what is true now: asked each time it opens or is drawn again, and once only.
const client = new QueryClient({ defaultOptions: { queries: { refetchOnWindowFocus: false, retry: false } } });

export function App() {
  return (
    <QueryClientProvider client={client}>
      <RouterProvider router={router} />
      <OverlayHost />
    </QueryClientProvider>
  );
}

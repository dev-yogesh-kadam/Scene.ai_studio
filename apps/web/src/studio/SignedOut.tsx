// What someone who is not signed in sees: the landing page at the site's address, Create account at /signup, and Sign
// in at /signin or at any page of the studio (an old link, or a session that ran out).

import { useQuery } from '@tanstack/react-query';
import { useEffect } from 'react';
import { useLocation, useNavigate } from 'react-router';
import type { Me } from '@scene/shared/types/api';
import { api } from '../common/api';
import type { AuthInfo } from '../common/components/AuthForm';
import { promptOf, withPrompt } from '../common/landing/words';
import { tabTitle } from '../common/format';
import { AuthPage } from './pages/auth/AuthPage';
import { LandingPage, SignInBelow } from './pages/landing/LandingPage';
import { LANDING } from './pages';
import { here } from './place';

export function SignedOut({ onSignedIn }: { onSignedIn: (user: Me) => void }) {
  const location = useLocation();
  const navigate = useNavigate();
  const at = here(location.pathname);
  const state = useQuery({
    queryKey: ['auth-state'],
    queryFn: () => api<AuthInfo>('/api/auth/state'),
    retry: false,
  });
  useEffect(() => {
    tabTitle();
  }, []);

  // Signing in lands on All projects; a prompt typed on the landing page lands on Home, where it waits in the prompt box.
  // The studio is shown once the move has happened: a page loads its file first, and the sign-in address, still
  // current until then, is not one of the studio's (it would send the user to All projects instead).
  const signedIn = (user: Me) => {
    const prompt = promptOf(location.search);
    void Promise.resolve(navigate(prompt ? withPrompt('/home', prompt) : LANDING, { replace: true })).then(() =>
      onSignedIn(user),
    );
  };
  if (state.isPending) return null; // drawn once the studio says whether new accounts are open
  const shown = state.data ?? { first_run: false, signup_open: false }; // shown anyway when it can't say
  if (at === '/') return <LandingPage signupOpen={shown.signup_open} />;
  return (
    <AuthPage
      key={at === '/signup' ? 'register' : 'login'}
      info={shown}
      start={at === '/signup' && shown.signup_open ? 'register' : 'login'}
      onSignedIn={signedIn}
      below={(openForm) => (
        <SignInBelow
          signupOpen={shown.signup_open}
          open={openForm}
          // A prompt picked further down waits for after signing in (it fills Home's prompt box); the form comes up to get there.
          pick={(text) => {
            void navigate(withPrompt(location.pathname, text), { replace: true });
            openForm(shown.signup_open ? 'register' : 'login');
          }}
        />
      )}
    />
  );
}

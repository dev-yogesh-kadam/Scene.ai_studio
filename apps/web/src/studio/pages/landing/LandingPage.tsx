// The landing page: what a visitor who is not signed in sees at the site's address. Everything it shows is something
// the studio does; the pictures are drawn by the page itself (landingScenes), so it needs no media files.

import { useLayoutEffect } from 'react';
import { useNavigate } from 'react-router';
import { LandingRoot } from '../../../common/landing/LandingRoot';
import { withPrompt } from '../../../common/landing/words';
import { Monitor } from './Monitor';
import { Sections, type Door } from './Sections';
import { classesOf } from '../../../common/cx';
import css0 from '../../../common/landing/Landing.module.css';
import css1 from '../../../common/landing/Landing4.module.css';
import css2 from '../../../common/landing/Landing6.module.css';
import css3 from './Monitor.module.css';
import css4 from './Sections.module.css';
import css5 from './Shared.module.css';
const css = classesOf(css0, css1, css2, css3, css4, css5);

export function LandingPage({ signupOpen }: { signupOpen: boolean }) {
  const navigate = useNavigate();
  useLayoutEffect(() => {
    window.scrollTo(0, 0);
  }, []);
  const signIn: Door = (cls = '') => (
    <a className={css('la-btn ' + cls)} href="/signin">
      Sign in
    </a>
  );
  const join: Door = signupOpen
    ? (cls = '') => (
        <a className={css('la-btn ' + cls)} href="/signup">
          Create an account
        </a>
      )
    : signIn;
  const start = (text: string) => void navigate(withPrompt(signupOpen ? '/signup' : '/signin', text));
  return (
    <LandingRoot>
      <Monitor join={join} signupOpen={signupOpen} start={start} />
      <Sections join={join} signIn={signIn} signupOpen={signupOpen} start={start} />
    </LandingRoot>
  );
}

/** The landing's sections under the sign-in form, their buttons leading back up to the form (`open`), and a prompt
 *  picked there waiting for after signing in (`pick`). */
export function SignInBelow({
  signupOpen,
  open,
  pick,
}: {
  signupOpen: boolean;
  open: (to: 'login' | 'register') => void;
  pick: (text: string) => void;
}) {
  const toForm =
    (to: 'login' | 'register', label: string): Door =>
    (cls = '') => (
      <button type="button" className={css('la-btn ' + cls)} onClick={() => open(to)}>
        {label}
      </button>
    );
  const signIn = toForm('login', 'Sign in');
  const join = signupOpen ? toForm('register', 'Create an account') : signIn;
  return <Sections join={join} signIn={signIn} signupOpen={signupOpen} start={pick} />;
}

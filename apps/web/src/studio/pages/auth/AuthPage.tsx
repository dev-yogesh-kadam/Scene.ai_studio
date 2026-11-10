// Sign in and create account: the landing page's monitor held on the desert scene, with the form on its slate.

import { useState, type ReactNode } from 'react';
import type { Me } from '@scene/shared/types/api';
import { AuthForm, type AuthInfo, type AuthMode } from '../../../common/components/AuthForm';
import { SignInSet } from '../../../common/landing/SignInSet';

const POINTS = [
  'Turn a prompt and a few reference images into video',
  'Chain clips into longer scenes that stay consistent',
  'Keep your characters, outfits and voices to reuse',
];

const TAGS: Record<AuthMode, string> = { login: 'Sign in', register: 'New account', code: 'Two-step' };

export function AuthPage({
  info,
  start,
  onSignedIn,
  below,
}: {
  info: AuthInfo;
  start: AuthMode;
  onSignedIn: (user: Me) => void;
  below?: (openForm: (to: AuthMode) => void) => ReactNode; // the landing's sections, whose buttons lead up to the form
}) {
  const [mode, setMode] = useState<AuthMode>(start);
  const openForm = (to: AuthMode) => {
    setMode(to);
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };
  return (
    <SignInSet
      scene="desert"
      home="/"
      heading={
        <>
          Direct
          <br />
          your <b>scene.</b>
        </>
      }
      sub="Write the shot. The studio makes the takes, keeps the same faces from shot to shot, and cuts them together."
      points={POINTS}
      tag={TAGS[mode]}
      below={below?.(openForm)}
    >
      <AuthForm mode={mode} onMode={setMode} info={info} onSignedIn={onSignedIn} />
    </SignInSet>
  );
}

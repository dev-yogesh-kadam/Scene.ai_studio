// Sign in, create an account, and the second step (a code from an authenticator app). Used by the studio's sign-in
// pages and, with its own address, by the admin console's.

import {
  cloneElement,
  isValidElement,
  useEffect,
  useId,
  useRef,
  useState,
  type FormEvent,
  type ReactNode,
} from 'react';
import type { Me } from '@scene/shared/types/api';
import { ApiError, api } from '../api';
import { classesOf } from '../cx';
import css0 from './AuthForm.module.css';
const css = classesOf(css0);

export type AuthMode = 'login' | 'register' | 'code';
export type AuthInfo = { first_run: boolean; signup_open: boolean };

const FIELDS = ['input', 'select', 'textarea'];

/** A caption over a form's field. Over one input, select or text box, the caption is its label (htmlFor), so the
 *  field is named by it; over anything else (buttons, several fields) it is a caption only. */
export function Field({ label, children }: { label: ReactNode; children: ReactNode }) {
  const made = useId();
  const one =
    isValidElement<{ id?: string }>(children) && typeof children.type === 'string' && FIELDS.includes(children.type);
  const id = one ? children.props.id || made : undefined;
  return (
    <div className="field">
      {id ? (
        <label className="label" htmlFor={id}>
          {label}
        </label>
      ) : (
        <div className="label">{label}</div>
      )}
      {one && !children.props.id ? cloneElement(children, { id }) : children}
    </div>
  );
}

export function AuthForm({
  mode,
  onMode,
  info,
  onSignedIn,
  loginPath = '/api/auth/login',
  registerPath = '/api/auth/register',
  copy = {},
}: {
  mode: AuthMode;
  onMode: (mode: AuthMode) => void;
  info: AuthInfo;
  onSignedIn: (user: Me) => void;
  loginPath?: string;
  registerPath?: string;
  /** The words of the sign-in, where they differ (the admin console's). */
  copy?: { title?: string; sub?: string; codeSub?: string; emailAutocomplete?: string };
}) {
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const second = useRef<{ email: string; password: string } | null>(null); // the password was right; a code is asked for
  const first = useRef<HTMLInputElement>(null);
  const register = mode === 'register';
  const [shownMode, setShownMode] = useState(mode);
  if (shownMode !== mode) {
    // another form: no error from the last one, and its button ready
    setShownMode(mode);
    setError('');
    setBusy(false);
  }

  useEffect(() => {
    first.current?.focus();
  }, [mode]);

  const send = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const form = new FormData(e.currentTarget);
    const value = (name: string) => String(form.get(name) ?? '');
    setBusy(true);
    try {
      if (mode === 'code') {
        onSignedIn(await api<Me>(loginPath, { method: 'POST', json: { ...second.current, code: value('code') } }));
        return;
      }
      const user = await api<Me>(register ? registerPath : loginPath, {
        method: 'POST',
        json: { name: value('name'), email: value('email'), password: value('password') },
      });
      onSignedIn(user);
    } catch (err) {
      const body = err instanceof ApiError ? (err.body as { mfa_required?: boolean } | null) : null;
      if (mode === 'login' && body?.mfa_required) {
        second.current = { email: value('email'), password: value('password') };
        onMode('code');
        return;
      }
      setError((err as Error).message);
      setBusy(false);
      if (mode === 'code') first.current?.select();
    }
  };

  if (mode === 'code') {
    return (
      <>
        <h1>Two-step sign-in</h1>
        <p className="muted">
          {copy.codeSub ??
            'Enter the 6-digit code your authenticator app shows for Scene.ai. Lost the phone? Use one of your recovery codes.'}
        </p>
        <form onSubmit={(e) => void send(e)}>
          <Field label="Code">
            <input
              ref={first}
              name="code"
              type="text"
              inputMode="numeric"
              autoComplete="one-time-code"
              required
              maxLength={20}
              placeholder="123456"
            />
          </Field>
          <p className="error notice">{error}</p>
          <button className="btn primary block" type="submit" disabled={busy}>
            Sign in
          </button>
        </form>
        <div className={css('auth-switch muted')}>
          <button
            type="button"
            onClick={() => {
              second.current = null;
              onMode('login');
            }}
          >
            Back
          </button>
        </div>
      </>
    );
  }

  return (
    <>
      <h1>
        {register ? (info.first_run ? 'Set up Scene.ai' : 'Create your account') : (copy.title ?? 'Welcome back')}
      </h1>
      <p className="muted">
        {!register
          ? (copy.sub ?? 'Sign in to your studio.')
          : info.first_run
            ? 'Create the first account. It becomes the admin of this installation.'
            : 'It takes a few seconds.'}
      </p>
      <form onSubmit={(e) => void send(e)} key={mode}>
        {register && (
          <Field label="Name">
            <input ref={first} name="name" type="text" autoComplete="name" placeholder="Your name" />
          </Field>
        )}
        <Field label="Email">
          <input
            ref={register ? undefined : first}
            name="email"
            type="email"
            autoComplete={copy.emailAutocomplete ?? 'email'}
            required
            placeholder="you@company.com"
          />
        </Field>
        <Field label="Password">
          <input
            name="password"
            type="password"
            required
            minLength={register ? 8 : undefined}
            autoComplete={register ? 'new-password' : 'current-password'}
            placeholder={register ? 'At least 8 characters' : 'Your password'}
          />
        </Field>
        <p className="error notice">{error}</p>
        <button className="btn primary block" type="submit" disabled={busy}>
          {register ? 'Create account' : 'Sign in'}
        </button>
      </form>
      {info.signup_open && (
        <div className={css('auth-switch muted')}>
          {register ? 'Already have an account? ' : 'New here? '}
          <button type="button" onClick={() => onMode(register ? 'login' : 'register')}>
            {register ? 'Sign in' : 'Create an account'}
          </button>
        </div>
      )}
    </>
  );
}

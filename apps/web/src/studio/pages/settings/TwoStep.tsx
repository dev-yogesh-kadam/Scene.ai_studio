// Two-step sign-in: after the password, a code from an authenticator app (Google Authenticator, 1Password, Authy…).

import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useRef, useState, type FormEvent, type ReactNode } from 'react';
import { api } from '../../../common/api';
import { Field } from '../../../common/components/AuthForm';
import { NoticeLine, type Notice } from './SettingsPage';
import { classesOf } from '../../../common/cx';
import css0 from '../../../common/components/Shared.module.css';
import css1 from '../../../common/components/Shared2.module.css';
import css2 from '../../../common/components/Shared3.module.css';
import css3 from '../create/CreatePage.module.css';
import css4 from './TwoStep.module.css';
const css = classesOf(css0, css1, css2, css3, css4);

type State = { enabled: boolean; recovery_left?: number };
type Step = { adding: { secret: string; uri: string } } | { saved: string[] } | null;

const formValue = (e: FormEvent<HTMLFormElement>, name: string) =>
  String(new FormData(e.currentTarget).get(name) ?? '');

function PasswordInput() {
  return <input name="password" type="password" autoComplete="current-password" aria-label="Your password" required />;
}

function CodeInput({ focus = false }: { focus?: boolean }) {
  const input = useRef<HTMLInputElement>(null);
  useEffect(() => {
    if (focus) input.current?.focus();
  }, [focus]);
  return (
    <input
      ref={input}
      name="code"
      type="text"
      inputMode="numeric"
      autoComplete="one-time-code"
      required
      maxLength={20}
      placeholder="123456"
    />
  );
}

export function TwoStep() {
  const client = useQueryClient();
  const state = useQuery({ queryKey: ['mfa'], queryFn: () => api<State>('/api/auth/mfa') });
  const [step, setStep] = useState<Step>(null);
  const [notice, setNotice] = useState<Notice>(null);
  const fail = (err: unknown) => setNotice({ ok: false, text: (err as Error).message });
  const show = (next: Step) => {
    setNotice(null);
    setStep(next);
  };
  const reload = () => {
    show(null);
    void client.invalidateQueries({ queryKey: ['mfa'] });
  };
  const run = (work: (e: FormEvent<HTMLFormElement>) => Promise<void>) => (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    work(e).catch(fail);
  };

  let body: ReactNode;
  if (step && 'adding' in step) {
    body = (
      <>
        <p>In your authenticator app, add an account and type in this key (on this phone, the link opens the app):</p>
        <div className={css('secret')}>{step.adding.secret.match(/.{1,4}/g)?.join(' ')}</div>
        <p className="small">
          <a href={step.adding.uri}>Open in the authenticator app</a>
        </p>
        <form
          onSubmit={run(async (e) => {
            const done = await api<{ recovery_codes: string[] }>('/api/auth/mfa/enable', {
              method: 'POST',
              json: { code: formValue(e, 'code') },
            });
            show({ saved: done.recovery_codes });
          })}
        >
          <Field label="The code the app shows now">
            <CodeInput focus />
          </Field>
          <button className="btn primary" style={{ marginTop: 12 }} type="submit">
            Confirm and turn on
          </button>
        </form>
      </>
    );
  } else if (step && 'saved' in step) {
    body = (
      <>
        <p>
          On. Keep these recovery codes somewhere safe: each signs you in once if you lose your phone. They are not
          shown again.
        </p>
        <div className={css('secret recovery-codes')}>
          {step.saved.map((x) => (
            <span key={x}>{x}</span>
          ))}
        </div>
        <div className="row" style={{ marginTop: 12 }}>
          <button
            className="btn"
            onClick={() =>
              void navigator.clipboard
                .writeText(step.saved.join('\n'))
                .then(() => setNotice({ ok: true, text: 'Copied.' }))
            }
          >
            Copy codes
          </button>
          <button className="btn" onClick={reload}>
            Done
          </button>
        </div>
      </>
    );
  } else if (state.isPending) {
    body = <p className="muted">Loading…</p>;
  } else if (state.data?.enabled) {
    body = (
      <>
        <p>
          {'On. '}
          <span className="muted">{`${state.data.recovery_left} recovery codes left.`}</span>
        </p>
        <form
          onSubmit={run(async (e) => {
            await api('/api/auth/mfa/disable', {
              method: 'POST',
              json: { password: formValue(e, 'password'), code: formValue(e, 'code') },
            });
            reload();
          })}
        >
          <div className={css('grid2')}>
            <Field label="Your password">
              <PasswordInput />
            </Field>
            <Field label="A code from the app, or a recovery code">
              <CodeInput />
            </Field>
          </div>
          <button className="btn quiet danger" style={{ marginTop: 12 }} type="submit">
            Turn off
          </button>
        </form>
      </>
    );
  } else if (state.data) {
    body = (
      <>
        <p>
          Off. Turn it on and signing in also asks for a code from an app on your phone, so a stolen password is not
          enough.
        </p>
        <form
          onSubmit={run(async (e) => {
            show({
              adding: await api<{ secret: string; uri: string }>('/api/auth/mfa/setup', {
                method: 'POST',
                json: { password: formValue(e, 'password') },
              }),
            });
          })}
        >
          <Field label="Your password">
            <PasswordInput />
          </Field>
          <button className="btn" style={{ marginTop: 12 }} type="submit">
            Turn on
          </button>
        </form>
      </>
    );
  }

  return (
    <div className={css('card')}>
      <div className={css('card-head')}>
        <h2>Two-step sign-in</h2>
      </div>
      {state.isError && !step ? null : body}
      <NoticeLine notice={state.isError && !step ? { ok: false, text: state.error.message } : notice} />
    </div>
  );
}

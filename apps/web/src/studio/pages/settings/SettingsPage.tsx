// Settings: the signed-in user's own account. Installation settings are in the admin console.

import { useState, type FormEvent } from 'react';
import { api } from '../../../common/api';
import { Field } from '../../../common/components/AuthForm';
import { creditsText } from '../../../common/format';
import { consoleAddress, useUser } from '../../session';
import { TwoStep } from './TwoStep';
import { classesOf } from '../../../common/cx';
import css0 from '../../../common/components/Shared.module.css';
import css1 from '../../../common/components/Shared2.module.css';
import css2 from '../../../common/components/Shared3.module.css';
import css3 from '../../../common/components/Shared4.module.css';
import css4 from '../create/CreatePage.module.css';
const css = classesOf(css0, css1, css2, css3, css4);

export type Notice = { ok: boolean; text: string } | null;

export function NoticeLine({ notice }: { notice: Notice }) {
  return <p className={'notice' + (notice ? (notice.ok ? ' ok' : ' error') : '')}>{notice?.text ?? ''}</p>;
}

export default function SettingsPage() {
  const user = useUser();
  const [notice, setNotice] = useState<Notice>(null);

  const changePassword = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const form = e.currentTarget;
    const data = new FormData(form);
    try {
      await api('/api/auth/password', { method: 'PUT', json: { current: data.get('current'), new: data.get('new') } });
      setNotice({ ok: true, text: 'Password changed. Other devices were signed out.' });
      form.reset();
    } catch (err) {
      setNotice({ ok: false, text: (err as Error).message });
    }
  };

  return (
    <>
      <div className={css('page-head')}>
        <h1>Settings</h1>
      </div>
      <div className={css('narrow')}>
        <div className={css('card')}>
          <div className={css('card-head')}>
            <h2>Account</h2>
          </div>
          <p>
            {user.name}
            <span className="muted">{` · ${user.email} · ${user.role} · ${creditsText(user.credits)}`}</span>
          </p>
          <form onSubmit={(e) => void changePassword(e)}>
            <div className={css('grid2')}>
              <Field label="Current password">
                <input name="current" type="password" autoComplete="current-password" required />
              </Field>
              <Field label="New password">
                <input name="new" type="password" autoComplete="new-password" required minLength={8} />
              </Field>
            </div>
            <NoticeLine notice={notice} />
            <button className="btn" style={{ marginTop: 12 }} type="submit">
              Change password
            </button>
          </form>
        </div>
        <TwoStep />
        {user.console && (
          <div className={css('card')}>
            <div className={css('card-head')}>
              <h2>Administration</h2>
            </div>
            <p className="muted">
              Users, credits, the model providers and every job are managed in the admin console. It is a site of its
              own, with its own sign-in.
            </p>
            <a className="btn" style={{ marginTop: 12 }} href={consoleAddress(user)} target="_blank" rel="noopener">
              Open admin console
            </a>
          </div>
        )}
      </div>
    </>
  );
}

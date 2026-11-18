// The console's Settings section: who can sign up, credits, the announcement every user sees, phone alerts, and what
// goes to Langfuse.

import { useState } from 'react';
import { api } from '../../../common/api';
import { Field } from '../../../common/components/AuthForm';
import { Segmented } from '../../../common/components/Segmented';
import { PhoneCard, type Phone } from '../system/Health';
import { useNotice, useSection } from '../shared/context';
import { Loaded, Notice, stamp } from '../shared/ui';
import { classesOf } from '../../../common/cx';
import css0 from '../../../common/components/Shared.module.css';
import css1 from '../../../common/components/Shared2.module.css';
import css2 from '../../../common/components/Shared3.module.css';
import css3 from '../shared/Console.module.css';
import css4 from '../../../studio/pages/create/CreatePage.module.css';
const css = classesOf(css0, css1, css2, css3, css4);

type Current = {
  allow_signup: boolean;
  signup_testing?: boolean; // a personal Claude subscription is in use: sign-up is closed whatever is chosen here
  signup_credits: number;
  daily_cap: number;
  admin_mfa: boolean;
  langfuse_words: boolean;
  langfuse_owns_words: boolean;
  langfuse_grade_share: number;
};
type News = { text?: string; level?: string; until?: number };

const putSettings = (json: unknown) => api('/api/admin/settings', { method: 'PUT', json });

function Accounts({
  current,
  admins,
}: {
  current: Current;
  admins: { name: string; mfa_enabled: boolean | number }[];
}) {
  const [signup, setSignup] = useState(current.allow_signup);
  const [welcome, setWelcome] = useState(String(current.signup_credits));
  const [cap, setCap] = useState(String(current.daily_cap));
  const [mfa, setMfa] = useState(current.admin_mfa);
  const { notice, run } = useNotice();
  const without = admins.filter((a) => !a.mfa_enabled);
  return (
    <div className={css('card narrow')}>
      <div className={css('card-head')}>
        <h2>Accounts</h2>
      </div>
      <p className="muted small">
        The render servers and the agent&apos;s model servers are set in Servers &amp; APIs.
      </p>
      <label className="check" style={{ marginTop: 0 }}>
        <input type="checkbox" checked={signup} onChange={(e) => setSignup(e.target.checked)} />
        Anyone who can open this site may create an account
      </label>
      <p className="muted small" style={{ margin: '6px 0 0 25px' }}>
        {signup
          ? 'When config.json sets an invite code (signup_invite), the sign-up form also asks for it; a link with ?invite=CODE fills it in.'
          : 'Closed (as on a new studio): nobody can make an account, and the sign-in page says so.'}
      </p>
      {current.signup_testing && (
        <p className="notice error" style={{ margin: '6px 0 0 25px' }}>
          Closed for now whatever is chosen here: the agent runs on a personal Claude subscription (Claude on this PC,
          Servers &amp; APIs → Providers). This choice is used again once Anthropic, with an API key, is picked.
        </p>
      )}
      <label className="check">
        <input type="checkbox" checked={mfa} onChange={(e) => setMfa(e.target.checked)} />
        Admins must use two-step sign-in to open the admin console
      </label>
      <p className="muted small" style={{ margin: '6px 0 0 25px' }}>
        {without.length
          ? `Without it now: ${without.map((a) => a.name).join(', ')}. They keep using the studio but can't sign in to this console until they turn it on in the studio's Settings.`
          : 'Every admin has two-step sign-in.'}
      </p>
      <h3>Credits</h3>
      <Field label="Credits for a new account">
        <input type="number" min={0} step={1} value={welcome} onChange={(e) => setWelcome(e.target.value)} />
      </Field>
      <Field label="Daily spending limit per user">
        <input type="number" min={0} step={50} value={cap} onChange={(e) => setCap(e.target.value)} />
      </Field>
      <p className="muted small" style={{ marginTop: 6 }}>
        The most credits one user may spend in 24 hours. 0 means no limit. Admins have none, and a user can be given
        their own limit (Users, select the user).
      </p>
      <p className="muted small" style={{ marginTop: 8 }}>
        What each kind of work costs is set in the Pricing section.
      </p>
      <Notice notice={notice} />
      <button
        className="btn primary"
        style={{ marginTop: 12 }}
        onClick={() =>
          void run(async () => {
            await putSettings({ allow_signup: signup, signup_credits: welcome, daily_cap: cap || 0, admin_mfa: mfa });
            return 'Saved.';
          })
        }
      >
        Save
      </button>
    </div>
  );
}

/** The message every user sees at the top of the studio. */
function Announcement({ current }: { current: News }) {
  const [text, setText] = useState(current.text || '');
  const [level, setLevel] = useState(current.level || 'info');
  const [hours, setHours] = useState('4');
  const { notice, run } = useNotice();
  const send = (body: unknown) =>
    run(async () => {
      const shown = await api<News>('/api/admin/announcement', { method: 'PUT', json: body });
      if (!shown.text) setText('');
      return shown.text
        ? shown.until
          ? `Showing to everyone until ${stamp(shown.until)}.`
          : 'Showing to everyone until you remove it.'
        : 'Removed.';
    });
  return (
    <div className={css('card narrow')}>
      <div className={css('card-head')}>
        <h2>Announcement</h2>
        {current.text ? <span className={css('pill done')}>Showing</span> : null}
      </div>
      <p className="muted small">
        A short message every user sees at the foot of the studio, on every page. Each person can close it for their
        session.
      </p>
      <Field label="Message">
        <textarea
          rows={2}
          maxLength={300}
          placeholder="For example: Renders are down for maintenance until 6 pm."
          value={text}
          onChange={(e) => setText(e.target.value)}
        />
      </Field>
      <div className={css('grid2')}>
        <div className="field">
          <div className="label">Kind</div>
          <Segmented
            choices={[
              { id: 'info', label: 'News' },
              { id: 'warning', label: 'Warning' },
            ]}
            current={level}
            onPick={setLevel}
          />
        </div>
        <Field label="Show for">
          <select value={hours} onChange={(e) => setHours(e.target.value)}>
            <option value="1">1 hour</option>
            <option value="4">4 hours</option>
            <option value="24">1 day</option>
            <option value="168">1 week</option>
            <option value="0">Until I remove it</option>
          </select>
        </Field>
      </div>
      <Notice notice={notice} />
      <div className="row" style={{ marginTop: 12 }}>
        <button className="btn primary" onClick={() => void send({ text, level, hours: Number(hours) })}>
          Publish
        </button>
        {current.text && (
          <button className="btn quiet danger" onClick={() => void send({ text: '' })}>
            Remove
          </button>
        )}
      </div>
    </div>
  );
}

/** What goes to Langfuse with the agent's calls, when one is set in Servers & APIs (docs/langfuse.md). */
function Langfuse({ current }: { current: Current }) {
  const [words, setWords] = useState(current.langfuse_words);
  const [owns, setOwns] = useState(!!current.langfuse_owns_words);
  const [share, setShare] = useState(String(current.langfuse_grade_share));
  const { notice, run } = useNotice();
  return (
    <div className={css('card narrow')}>
      <div className={css('card-head')}>
        <h2>Langfuse</h2>
      </div>
      <p className="muted small">
        Langfuse itself is set in Servers &amp; APIs. Each call of the agent&apos;s models, and each render, goes to it
        in the background.
      </p>
      <label className="check" style={{ marginTop: 0 }}>
        <input type="checkbox" checked={words} onChange={(e) => setWords(e.target.checked)} />
        Send the words: what was asked, the answers, the reasons of a grade
      </label>
      <p className="muted small" style={{ margin: '6px 0 0 25px' }}>
        Off: only names, models, tokens, costs and times are sent. Saving a call to a dataset needs it on.
      </p>
      <label className="check">
        <input type="checkbox" checked={owns} onChange={(e) => setOwns(e.target.checked)} />
        Keep the words in Langfuse only
      </label>
      <p className="muted small" style={{ margin: '6px 0 0 25px' }}>
        A call&apos;s words file is deleted here once Langfuse has it, and the agent&apos;s session events older than 30
        days go to Langfuse and are kept here only in short. Works only while a Langfuse is set and the words are sent
        (docs/observability.md).
      </p>
      <Field label="Turns graded by the fast model (%)">
        <input type="number" min={0} max={100} step={1} value={share} onChange={(e) => setShare(e.target.value)} />
      </Field>
      <p className="muted small" style={{ marginTop: 6 }}>
        This share of the agent&apos;s turns is graded by the fast model (did it follow its skill, is the reply clear,
        are the steps sensible) and sent as the score “claude-grade”. 0 is off. Not charged to anyone.
      </p>
      <Notice notice={notice} />
      <button
        className="btn primary"
        style={{ marginTop: 12 }}
        onClick={() =>
          void run(async () => {
            await putSettings({ langfuse_words: words, langfuse_owns_words: owns, langfuse_grade_share: share || 0 });
            return 'Saved.';
          })
        }
      >
        Save
      </button>
    </div>
  );
}

export default function Settings() {
  const query = useSection('settings', [], async () => {
    const [current, admins, news, alerts] = await Promise.all([
      api<Current>('/api/admin/settings'),
      api<{ admins: { name: string; mfa_enabled: boolean | number }[] }>('/api/admin/admins'),
      api<News>('/api/admin/announcement'),
      api<{ phone: Phone }>('/api/admin/alerts'),
    ]);
    return { current, admins: admins.admins, news, phone: alerts.phone };
  });
  return (
    <Loaded query={query}>
      {(d) => (
        <>
          <Accounts current={d.current} admins={d.admins} />
          <Announcement key={d.news.text ?? ''} current={d.news} />
          <PhoneCard key={JSON.stringify(d.phone)} phone={d.phone} />
          <Langfuse current={d.current} />
        </>
      )}
    </Loaded>
  );
}

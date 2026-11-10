// The console's Moderation section: what was made lately, flagged first when its prompt has a listed word, each item
// marked fine or removed; the verdicts so far; the prompts refused before they were made; and the word list.
// See backend/scene/moderation.py.

import { useState } from 'react';
import { api } from '../../../common/api';
import { Field } from '../../../common/components/AuthForm';
import { Segmented } from '../../../common/components/Segmented';
import { useConsole, useFilters, useNotice, useSection } from '../shared/context';
import { Loaded, Notice, Person, Table, Thumb, ago, failed, number, stamp, sure } from '../shared/ui';
import { classesOf } from '../../../common/cx';
import css0 from '../../../common/components/Shared2.module.css';
import css1 from '../../../common/components/Shared3.module.css';
import css2 from './Moderation.module.css';
import css3 from '../shared/Console.module.css';
import css4 from '../../../studio/pages/create/CreatePage.module.css';
const css = classesOf(css0, css1, css2, css3, css4);

const MODES = [
  { id: 'off', label: 'Off' },
  { id: 'flag', label: 'Flag for review' },
  { id: 'refuse', label: 'Refuse the job' },
];

type ItemRow = {
  id: number;
  kind: string;
  name: string;
  user_name: string;
  user_email: string;
  created: number;
  prompt?: string;
  words: string[];
};
type Verdict = {
  created: number;
  verdict: string;
  user_name?: string;
  user_email?: string;
  words: string;
  prompt: string;
  by_name: string;
};
type Data = { show: string; mode: string; words: string[]; flagged: number; items: (ItemRow & Verdict)[] };

function Words({ d }: { d: Data }) {
  const { refresh } = useConsole();
  const [words, setWords] = useState(d.words.join('\n'));
  const [mode, setMode] = useState(d.mode);
  const { notice, run } = useNotice();
  return (
    <div className={css('card')}>
      <div className={css('card-head')}>
        <h2>Words</h2>
        <span className={css('pill ' + (d.mode === 'off' ? 'cancelled' : 'running'))}>
          {MODES.find((m) => m.id === d.mode)?.label}
        </span>
      </div>
      <p className="muted small">
        Prompts with these words (whole words, any case) are flagged, or refused before anything is made: the person is
        told to change the words and gets the credits back. A refused prompt is listed under Refused.
      </p>
      <Field label="Words and phrases">
        <textarea
          rows={6}
          placeholder="One word or phrase a line"
          value={words}
          onChange={(e) => setWords(e.target.value)}
        />
      </Field>
      <div className="field">
        <div className="label">When a prompt has one</div>
        <Segmented choices={MODES} current={mode} onPick={setMode} />
      </div>
      <Notice notice={notice} />
      <button
        className="btn primary"
        style={{ marginTop: 12 }}
        onClick={() =>
          void run(async () => {
            await api('/api/admin/moderation/settings', { method: 'PUT', json: { words, mode } });
            await refresh();
          })
        }
      >
        Save
      </button>
    </div>
  );
}

function ItemCard({ i }: { i: ItemRow }) {
  const { refresh } = useConsole();
  const [busy, setBusy] = useState(false);
  const decide = async (verdict: string) => {
    if (
      verdict === 'removed' &&
      !(await sure(`Remove "${i.name}" from ${i.user_name}'s library? It can't be brought back.`))
    )
      return;
    setBusy(true);
    try {
      await api('/api/admin/moderation/' + i.id, { method: 'POST', json: { verdict } });
      await refresh();
    } catch (e) {
      failed(e);
      setBusy(false);
    }
  };
  return (
    <div className={css('mod-item' + (i.words.length ? ' flagged' : ''))}>
      <a
        className={css('thumb-box')}
        href={`/api/admin/library/${i.id}/file`}
        target="_blank"
        rel="noreferrer"
        title={'Open ' + i.name}
      >
        <Thumb item={i} />
      </a>
      <div className={css('mod-body')}>
        <div className="row">
          <b>{i.name}</b>
          {i.words.map((w) => (
            <span key={w} className={css('pill failed')}>
              {w}
            </span>
          ))}
        </div>
        <div className="muted small">{`${i.user_name} · ${i.user_email} · ${ago(i.created)}`}</div>
        {i.prompt && <p className={css('small mod-prompt')}>{i.prompt}</p>}
        <div className="row">
          <button className="btn small" disabled={busy} onClick={() => void decide('fine')}>
            Fine
          </button>
          <button className="btn small quiet danger" disabled={busy} onClick={() => void decide('removed')}>
            Remove
          </button>
        </div>
      </div>
    </div>
  );
}

function Body({ d }: { d: Data }) {
  if (d.show === 'review')
    return (
      <div className={css('card')}>
        <div className={css('card-head')}>
          <h2>{`To review (${number(d.items.length)})`}</h2>
          {d.flagged > 0 && <span className={css('pill failed')}>{`${d.flagged} flagged`}</span>}
        </div>
        <p className="muted small">
          What was made in the last 30 days and has no verdict yet, flagged items first. Fine takes an item off this
          list; Remove deletes it from its owner&apos;s library.
        </p>
        {d.items.length ? (
          <div className={css('mod-list')}>
            {d.items.map((i) => (
              <ItemCard key={i.id} i={i} />
            ))}
          </div>
        ) : (
          <p className="muted">Nothing to review.</p>
        )}
      </div>
    );
  if (d.show === 'done')
    return (
      <div className={css('card')}>
        <div className={css('card-head')}>
          <h2>Decided</h2>
        </div>
        <Table
          head={['When', 'Verdict', 'Whose', 'Words', 'Prompt', 'By']}
          rows={d.items.map((m) => [
            stamp(m.created),
            <span key="v" className={css('pill ' + (m.verdict === 'removed' ? 'failed' : 'done'))}>
              {m.verdict === 'removed' ? 'Removed' : 'Fine'}
            </span>,
            m.user_name ? <Person key="p" name={m.user_name} email={m.user_email} /> : '',
            m.words,
            <span key="t" className="small">
              {m.prompt.slice(0, 160)}
            </span>,
            m.by_name,
          ])}
          empty="No verdicts yet."
        />
      </div>
    );
  return (
    <div className={css('card')}>
      <div className={css('card-head')}>
        <h2>Refused prompts</h2>
      </div>
      <Table
        head={['When', 'Who', 'Words', 'Prompt']}
        rows={d.items.map((m) => [
          stamp(m.created),
          m.user_name ? <Person key="p" name={m.user_name} email={m.user_email} /> : '',
          <span key="w" className={css('pill failed')}>
            {m.words}
          </span>,
          <span key="t" className="small">
            {m.prompt.slice(0, 200)}
          </span>,
        ])}
        empty="None refused."
      />
    </div>
  );
}

export default function Moderation() {
  const [s, set] = useFilters<{ show: string }>('moderation');
  const query = useSection('moderation', [s.show], () => api<Data>('/api/admin/moderation?show=' + s.show));
  return (
    <Loaded query={query}>
      {(d) => (
        <>
          <div className={css('toolbar')}>
            <Segmented
              choices={[
                { id: 'review', label: 'To review' },
                { id: 'done', label: 'Decided' },
                { id: 'refused', label: 'Refused prompts' },
              ]}
              current={s.show}
              onPick={(show) => set({ show })}
            />
          </div>
          <div className={css('grid-2')}>
            <Body d={d} />
            <Words key={d.words.join('\n') + d.mode} d={d} />
          </div>
        </>
      )}
    </Loaded>
  );
}

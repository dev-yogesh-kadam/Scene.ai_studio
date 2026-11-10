// The console's give-or-take-credits window. `people` is the list to choose from; one person skips the choice. And the
// same credits to every account that is not disabled: for a launch, a holiday, or an apology after an outage.

import { useState } from 'react';
import { api } from '../../../common/api';
import { Field } from '../../../common/components/AuthForm';
import { Modal } from '../../../common/components/Dialog';
import { Segmented } from '../../../common/components/Segmented';
import { number, say } from '../shared/ui';
import { classesOf } from '../../../common/cx';
import css0 from '../../../common/components/Shared2.module.css';
import css1 from '../../../common/components/Shared3.module.css';
import css2 from './CreditsDialog.module.css';
import css3 from '../shared/Console.module.css';
const css = classesOf(css0, css1, css2, css3);

type Person = { id: number; name: string; email: string; credits: number };

function Chips({ amounts, onPick }: { amounts: number[]; onPick: (n: number) => void }) {
  return (
    <div className={css('chips')}>
      {amounts.map((n) => (
        <button key={n} type="button" className="btn small" onClick={() => onPick(n)}>
          {number(n)}
        </button>
      ))}
    </div>
  );
}

export function CreditsDialog({
  people,
  onClose,
  after,
}: {
  people: Person[];
  onClose: () => void;
  after: () => void;
}) {
  const [mode, setMode] = useState<'give' | 'take'>('give');
  const [person, setPerson] = useState<Person | null>(people.length === 1 ? people[0] : null);
  const [amount, setAmount] = useState('500');
  const [note, setNote] = useState('');
  const [error, setError] = useState('');
  const [sending, setSending] = useState(false);
  const value = Math.max(0, Math.floor(Number(amount) || 0));
  const now = person ? person.credits : 0;
  const next = mode === 'give' ? now + value : Math.max(0, now - value);
  const warned =
    mode === 'take' && person && value > now && now > 0
      ? `They only have ${number(now)}, so the balance goes to 0.`
      : '';
  const save = async () => {
    if (!person) return;
    setSending(true);
    try {
      await api('/api/admin/users/' + person.id, {
        method: 'PUT',
        json: { add_credits: mode === 'give' ? value : -value, note },
      });
      after();
    } catch (e) {
      setError((e as Error).message);
      setSending(false);
    }
  };
  return (
    <Modal onClose={onClose}>
      <h2>Give or take credits</h2>
      <p className="muted">
        The change is applied at once and recorded, with its reason, in the credit log and the audit log.
      </p>
      {people.length > 1 && (
        <Field label="User">
          <select
            value={person?.id ?? ''}
            onChange={(e) => setPerson(people.find((p) => String(p.id) === e.target.value) || null)}
          >
            <option value="">Choose a user</option>
            {people.map((p) => (
              <option key={p.id} value={p.id}>{`${p.name} · ${p.email}`}</option>
            ))}
          </select>
        </Field>
      )}
      <div className="field">
        <Segmented
          choices={[
            { id: 'give', label: 'Give credits' },
            { id: 'take', label: 'Take credits' },
          ]}
          current={mode}
          onPick={setMode}
        />
      </div>
      <Field label="Amount">
        <input
          type="number"
          min={1}
          step={1}
          value={amount}
          style={{ width: '100%' }}
          onChange={(e) => setAmount(e.target.value)}
        />
        <Chips amounts={[100, 500, 1000, 5000]} onPick={(n) => setAmount(String(n))} />
      </Field>
      <Field label="Reason">
        <input
          type="text"
          maxLength={200}
          placeholder='Shown in the credit log, for example "Launch bonus"'
          value={note}
          onChange={(e) => setNote(e.target.value)}
        />
      </Field>
      <div className={css('balance')}>
        <span className="muted">
          {person ? `${person.name} has ${number(now)} now` : 'Choose a user to see their balance'}
        </span>
        {person ? (
          <span>
            <span className="muted">New balance </span>
            <b>{number(next)}</b>
          </span>
        ) : null}
      </div>
      <p className="error notice">{error || warned}</p>
      <div className={css('dialog-buttons')}>
        <button className="btn" onClick={onClose}>
          Cancel
        </button>
        <button
          className="btn primary"
          disabled={sending || !person || value < 1 || (mode === 'take' && now === 0) || !note.trim()}
          onClick={() => void save()}
        >
          {mode === 'give' ? `Give ${number(value)} credits` : `Take ${number(Math.min(value, now))} credits`}
        </button>
      </div>
    </Modal>
  );
}

export function EveryoneDialog({ onClose, after }: { onClose: () => void; after: () => void }) {
  const [amount, setAmount] = useState('200');
  const [note, setNote] = useState('');
  const [error, setError] = useState('');
  const [sending, setSending] = useState(false);
  const value = Math.max(0, Math.floor(Number(amount) || 0));
  const save = async () => {
    setSending(true);
    try {
      const done = await api<{ amount: number; accounts: number }>('/api/admin/credits/everyone', {
        method: 'POST',
        json: { amount: Math.floor(Number(amount)), note },
      });
      after();
      void say(`Gave ${number(done.amount)} credits to ${done.accounts} account${done.accounts === 1 ? '' : 's'}.`);
    } catch (e) {
      setError((e as Error).message);
      setSending(false);
    }
  };
  return (
    <Modal onClose={onClose}>
      <h2>Give everyone credits</h2>
      <p className="muted">
        Every account that is not disabled gets the same amount, with your reason in its credit history. This can&apos;t
        be undone in one step.
      </p>
      <Field label="Amount for each account">
        <input
          type="number"
          min={1}
          step={1}
          value={amount}
          style={{ width: '100%' }}
          onChange={(e) => setAmount(e.target.value)}
        />
        <Chips amounts={[100, 200, 500, 1000]} onPick={(n) => setAmount(String(n))} />
      </Field>
      <Field label="Reason">
        <input
          type="text"
          maxLength={200}
          placeholder={'For example "Sorry for Tuesday\'s outage"'}
          value={note}
          onChange={(e) => setNote(e.target.value)}
        />
      </Field>
      <p className="error notice">{error}</p>
      <div className={css('dialog-buttons')}>
        <button className="btn" onClick={onClose}>
          Cancel
        </button>
        <button className="btn primary" disabled={sending || value < 1 || !note.trim()} onClick={() => void save()}>
          {`Give everyone ${number(value)} credits`}
        </button>
      </div>
    </Modal>
  );
}

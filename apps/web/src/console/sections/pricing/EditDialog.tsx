// A window for the fields of one row of the Pricing section. A number left empty is sent as null.

import { useState, type ReactNode } from 'react';
import { Field } from '../../../common/components/AuthForm';
import { Modal } from '../../../common/components/Dialog';
import { sure } from '../shared/ui';
import { classesOf } from '../../../common/cx';
import css0 from '../../../common/components/Shared.module.css';
import css1 from '../../../common/components/Shared2.module.css';
import css2 from '../../../common/components/Shared3.module.css';
const css = classesOf(css0, css1, css2);

export type EditField = {
  id: string;
  label: string;
  type: 'text' | 'number' | 'check' | 'choice';
  hint?: string;
  choices?: { id: string; label: string }[];
};
export type Values = Record<string, unknown>;
export type Editing = {
  title: string;
  about?: string | null;
  fields: EditField[];
  values: Values;
  save: (values: Values) => Promise<unknown>;
  remove?: () => Promise<unknown>;
};

export function EditDialog({ editing, onClose }: { editing: Editing; onClose: () => void }) {
  const { title, about, fields, values, save, remove } = editing;
  const [state, setState] = useState<Values>(() =>
    Object.fromEntries(fields.map((f) => [f.id, f.type === 'check' ? !!values[f.id] : (values[f.id] ?? '')])),
  );
  const [error, setError] = useState('');
  const set = (id: string, value: unknown) => setState((was) => ({ ...was, [id]: value }));
  const read = () =>
    Object.fromEntries(
      fields.map((f) => [
        f.id,
        f.type === 'number' ? (String(state[f.id]).trim() === '' ? null : Number(state[f.id])) : state[f.id],
      ]),
    );
  const run = (work: Promise<unknown>) => work.then(onClose, (e: Error) => setError(e.message));
  const control = (f: EditField): ReactNode => {
    if (f.type === 'check')
      return (
        <label key={f.id} className="check">
          <input type="checkbox" checked={!!state[f.id]} onChange={(e) => set(f.id, e.target.checked)} />
          {f.label}
        </label>
      );
    return (
      <Field key={f.id} label={f.label}>
        {f.type === 'choice' ? (
          <select value={String(state[f.id])} onChange={(e) => set(f.id, e.target.value)}>
            {f.choices?.map((c) => (
              <option key={c.id} value={c.id}>
                {c.label}
              </option>
            ))}
          </select>
        ) : (
          <input
            type={f.type}
            min={0}
            step="any"
            style={{ width: '100%' }}
            placeholder={f.hint || ''}
            value={String(state[f.id])}
            onChange={(e) => set(f.id, e.target.value)}
          />
        )}
      </Field>
    );
  };
  return (
    <Modal onClose={onClose}>
      <h2>{title}</h2>
      {about && <p className="muted">{about}</p>}
      <div className={css('grid2')}>{fields.filter((f) => f.type !== 'check').map(control)}</div>
      {fields.filter((f) => f.type === 'check').map(control)}
      <p className="error notice">{error}</p>
      <div className={css('dialog-buttons')}>
        {remove && (
          <button
            className="btn quiet danger"
            style={{ marginRight: 'auto' }}
            onClick={() => {
              void sure("Delete this? It can't be undone.").then((yes) => {
                if (yes) void run(remove());
              });
            }}
          >
            Delete
          </button>
        )}
        <button className="btn" onClick={onClose}>
          Cancel
        </button>
        <button className="btn primary" onClick={() => void run(save(read()))}>
          Save
        </button>
      </div>
    </Modal>
  );
}

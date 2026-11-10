// The NeuralCore's smaller windows: a note of the memory changed by hand (its whole JSON), or deleted; and what an
// asset sheet brought in.

import { useState } from 'react';
import type { MemoryLeaf } from '@scene/shared/api/kit';
import { Field } from '../../../common/components/AuthForm';
import { ask, openDialog } from '../../../common/components/Dialog';
import { ago } from '../../../common/format';
import { KIT } from './kit';
import { classesOf } from '../../../common/cx';
import css0 from '../../../common/components/Shared2.module.css';
import css1 from '../../../common/components/Shared3.module.css';
const css = classesOf(css0, css1);

/** Resolves true when the note was saved or deleted. */
export function editLeaf(
  leaf: MemoryLeaf,
  { save, remove }: { save: (value: unknown) => Promise<unknown>; remove: () => Promise<unknown> },
) {
  return openDialog<boolean>((close) => <Leaf leaf={leaf} save={save} remove={remove} close={close} />);
}

function Leaf({
  leaf,
  save,
  remove,
  close,
}: {
  leaf: MemoryLeaf;
  save: (value: unknown) => Promise<unknown>;
  remove: () => Promise<unknown>;
  close: (done?: boolean) => void;
}) {
  const [text, setText] = useState(() => JSON.stringify(leaf.value, null, 2));
  const [error, setError] = useState('');
  const keep = async () => {
    let value: unknown;
    try {
      value = JSON.parse(text);
    } catch {
      setError('That is not JSON: text goes in "quotes".');
      return;
    }
    try {
      await save(value);
      close(true);
    } catch (e) {
      setError((e as Error).message);
    }
  };
  const drop = async () => {
    if (!(await ask({ title: `Delete ${leaf.path}?`, danger: true, confirm: 'Delete' }))) return;
    try {
      await remove();
      close(true);
    } catch (e) {
      setError((e as Error).message);
    }
  };
  return (
    <>
      <h2>{leaf.path}</h2>
      <p className="muted">
        {`Kept by ${leaf.writer || 'someone'} ${leaf.updated ? ago(leaf.updated) : ''}. Every agent tab of this module reads it from here: your change wins.`}
      </p>
      <Field label="Value (JSON)">
        <textarea rows={10} className="mono" value={text} onChange={(e) => setText(e.target.value)} />
      </Field>
      <p className="error notice">{error}</p>
      <div className={css('dialog-buttons')}>
        <button className="btn danger" onClick={() => void drop()}>
          Delete
        </button>
        <span style={{ flex: 1 }} />
        <button className="btn" onClick={() => close()}>
          Cancel
        </button>
        <button className="btn primary" onClick={() => void keep()}>
          Save
        </button>
      </div>
    </>
  );
}

type Sheet = {
  added: { new?: boolean }[];
  looks: unknown[];
  failed: { row: number; name: string; reason: string }[];
  left_out: { row: number; name?: string; reason: string }[];
};

export function sheetDone(done: Sheet) {
  const fresh = done.added.filter((a) => a.new).length;
  const problems = [
    ...done.failed.map((f) => `Row ${f.row}, “${f.name}”: ${f.reason}`),
    ...done.left_out.map((f) => `Row ${f.row}${f.name ? `, “${f.name}”` : ''}: left out, ${f.reason}`),
  ];
  return openDialog((close) => (
    <>
      <h2>{`Brought into the ${KIT}`}</h2>
      <p>
        {`${fresh} new ${fresh === 1 ? 'entry' : 'entries'}` +
          (done.added.length > fresh ? `, ${done.added.length - fresh} already here` : '') +
          (done.looks.length ? `, ${done.looks.length} linked as looks of another` : '') +
          '.'}
      </p>
      {problems.length ? (
        <ul>
          {problems.map((line) => (
            <li key={line}>{line}</li>
          ))}
        </ul>
      ) : null}
      <div className={css('dialog-buttons')}>
        <button className="btn primary" onClick={() => close()}>
          OK
        </button>
      </div>
    </>
  ));
}

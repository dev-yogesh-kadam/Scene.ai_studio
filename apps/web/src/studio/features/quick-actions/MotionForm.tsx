// The form of one motion template in Quick actions: its fields, the video it is laid over (the one selected on the
// canvas), and Render. Motion graphics are drawn from HTML templates and rendered on the studio's own machine; they are
// priced by the second of video, like everything else that is made.

import { useQueryClient } from '@tanstack/react-query';
import { useEffect, useState } from 'react';
import { motionEstimate, motionRender, type MotionField, type MotionTemplate } from '@scene/shared/api/make';
import { Field } from '../../../common/components/AuthForm';
import { Icon } from '../../../common/components/Icon/Icon';
import { cx } from '../../../common/cx';
import type { Item } from '../../../common/media/item';
import { JOBS } from '../../live';
import s from './QuickActions.module.css';
import { classesOf } from '../../../common/cx';
import css0 from '../../../common/components/Shared.module.css';
import css1 from '../../../common/components/Shared3.module.css';
const css = classesOf(css0, css1);

const capital = (text: unknown) => String(text)[0].toUpperCase() + String(text).slice(1);

/** What a render would cost, shown on its button: '' while nothing can be priced yet (the form is not filled in). */
export function useMotionCost(body: unknown) {
  const [cost, setCost] = useState('');
  const key = JSON.stringify(body);
  useEffect(() => {
    let live = true;
    const timer = setTimeout(() => {
      motionEstimate(JSON.parse(key) as unknown).then(
        (quote) => live && setCost(quote.credits ? quote.credits + ' cr' : 'Free'),
        () => live && setCost(''),
      );
    }, 300);
    return () => {
      live = false;
      clearTimeout(timer);
    };
  }, [key]);
  return cost;
}

/** Sending a render: its button says so, then the note says it will appear on the canvas, or why it didn't go. */
export function useRender() {
  const client = useQueryClient();
  const [sending, setSending] = useState(false);
  const [note, setNote] = useState({ text: '', ok: false });
  const send = async (body: unknown) => {
    setNote({ text: '', ok: false });
    setSending(true);
    try {
      await motionRender(body);
      void client.invalidateQueries({ queryKey: JOBS });
      setNote({ text: 'Rendering. It will appear on the canvas.', ok: true });
    } catch (e) {
      setNote({ text: (e as Error).message, ok: false });
    }
    setSending(false);
  };
  return { sending, note, setNote, send };
}

export function Sending() {
  return (
    <>
      <i className={css('cell-mark stepping')} /> Sending…
    </>
  );
}

function Input({
  field,
  value,
  onChange,
  onEnter,
}: {
  field: MotionField;
  value: unknown;
  onChange: (v: unknown) => void;
  onEnter: () => void;
}) {
  if (field.type === 'choice')
    return (
      <select aria-label={field.label} value={String(value)} onChange={(e) => onChange(e.target.value)}>
        {(field.choices ?? []).map((c) => (
          <option key={String(c)} value={String(c)}>
            {field.names?.[String(c)] || (typeof c === 'number' ? c + (field.unit || '') : capital(c))}
          </option>
        ))}
      </select>
    );
  return (
    <input
      type="text"
      maxLength={field.max || 200}
      placeholder={field.placeholder || ''}
      value={String(value ?? '')}
      aria-label={field.label}
      onChange={(e) => onChange(e.target.value)}
      onKeyDown={(e) => {
        if (e.key === 'Enter') onEnter();
      }}
    />
  );
}

export function MotionForm({
  template,
  source,
  project,
  onBack,
}: {
  template: MotionTemplate;
  source: Item | null; // the video selected on the canvas, or null
  project: number | null;
  onBack: () => void;
}) {
  const [values, setValues] = useState<Record<string, unknown>>(() =>
    Object.fromEntries(template.fields.map((f) => [f.id, f.default ?? ''])),
  );
  const over = template.needs === 'video' ? (source && source.kind === 'video' ? source : null) : null;
  const cost = useMotionCost({ template: template.id, values, source: over ? over.id : null });
  const render = useRender();
  const blocked = render.sending || (template.needs === 'video' && !over);
  const go = () => {
    if (blocked) return;
    void render.send({ template: template.id, values, source: over ? over.id : null, project_id: project });
  };
  return (
    <div className={s.quick}>
      <div className={s['quick-head']}>
        <button className="icon-btn" title="Back to quick actions" aria-label="Back to quick actions" onClick={onBack}>
          <Icon name="back" />
        </button>
        <b>{template.title}</b>
      </div>
      <div className={s['quick-body']}>
        <p className="muted small">{template.description}</p>
        {template.needs === 'video' && (
          <div className={cx(s['quick-source'], !over && s.missing)}>
            {over ? (
              <>
                Over <b>{over.name}</b>
              </>
            ) : (
              'Select a video on the canvas. This is laid over it.'
            )}
          </div>
        )}
        {template.fields.map((f) => (
          <Field key={f.id} label={f.label}>
            <Input
              field={f}
              value={values[f.id]}
              onChange={(v) => setValues((was) => ({ ...was, [f.id]: v }))}
              onEnter={go}
            />
          </Field>
        ))}
        <p className={cx(render.note.ok ? 'notice ok' : 'error notice', s.notice, render.note.ok && s.ok)}>
          {render.note.text}
        </p>
      </div>
      <div className={s['quick-foot']}>
        <button className={cx('btn generate', s.generate)} disabled={blocked} onClick={go}>
          <span>{render.sending ? <Sending /> : 'Render'}</span>
          <span className="cost">{cost}</span>
        </button>
      </div>
    </div>
  );
}

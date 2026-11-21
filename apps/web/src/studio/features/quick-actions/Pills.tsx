// The few settings under a Quick action's form, as small choices beside Generate: length, resolution, orientation, the
// choices a presets file keeps in view, and the workflow's other options. A choice that changes the price says what
// each option costs ("1080p · 200 cr"). "All settings" opens the full form on the Create page.

import { useNavigate } from 'react-router';
import { byRole, lengthChoices, offered, type Quote } from '../jobs/jobForm';
import { short } from './refs';
import type { ActionForm } from './useActionForm';
import { toCreate } from '../../handoff';
import s from './QuickActions.module.css';

const ORIENTATIONS = ['landscape', 'portrait', 'square'];
const capital = (text: string) => text[0].toUpperCase() + text.slice(1);

type Choice = { id: string | number; label: string };

function Pill({
  name,
  choices,
  current,
  onPick,
  priced,
  quote,
}: {
  name: string;
  choices: Choice[];
  current: unknown;
  onPick: (value: string) => void;
  priced?: 'resolution' | 'quality';
  quote: Quote | null;
}) {
  const prices = (priced && quote?.choices?.[priced]) || {};
  return (
    <select
      className={s.opt}
      title={name}
      aria-label={name}
      value={String(current)}
      onChange={(e) => onPick(e.target.value)}
    >
      {choices.map((c) => (
        <option key={String(c.id)} value={String(c.id)}>
          {c.label + (prices[String(c.id)] != null ? ` · ${prices[String(c.id)]} cr` : '')}
        </option>
      ))}
    </select>
  );
}

export function Pills({ action }: { action: ActionForm }) {
  const navigate = useNavigate();
  const { form, setForm, quote } = action;
  const wf = form.wf;
  if (!wf) return <div className={s['quick-pills']} />;
  const value = (id: string, v: unknown) => setForm((was) => ({ ...was, values: { ...was.values, [id]: v } }));
  const option = (id: string, v: string) => setForm((was) => ({ ...was, options: { ...was.options, [id]: v } }));
  const sizes = wf.resolutions.map((r) => ({ id: r, label: r + 'p' }));
  const dur = byRole(wf, 'duration');
  const res = byRole(wf, 'resolution');
  return (
    <div className={s['quick-pills']}>
      {dur && (
        <Pill
          name="Length"
          choices={lengthChoices(Number(form.values[dur.id])).map((d) => ({
            id: d,
            label: d + ' s',
          }))}
          current={form.values[dur.id]}
          onPick={(d) => value(dur.id, Number(d))}
          quote={quote}
        />
      )}
      {wf.size && (
        <>
          <Pill
            name="Resolution"
            choices={sizes}
            current={form.resolution}
            onPick={(r) => setForm((was) => ({ ...was, resolution: Number(r) }))}
            priced="resolution"
            quote={quote}
          />
          <Pill
            name="Orientation"
            choices={ORIENTATIONS.map((o) => ({ id: o, label: capital(o) }))}
            current={form.orientation}
            onPick={(o) => setForm((was) => ({ ...was, orientation: o }))}
            quote={quote}
          />
        </>
      )}
      {res && (
        <Pill
          name="Resolution"
          choices={sizes}
          current={form.values[res.id]}
          onPick={(r) => value(res.id, Number(r))}
          priced="resolution"
          quote={quote}
        />
      )}
      {/* choices a presets file keeps in view, such as the aspect ratio of a workflow that has no orientation */}
      {wf.controls
        .filter((c) => c.primary && c.choices && !c.role)
        .map((c) => (
          <Pill
            key={c.id}
            name={c.label}
            choices={c.choices!.map((x) => ({
              id: x,
              label: c.choices!.every((y) => typeof y === 'string') ? String(x) : `${short(c.label)}: ${x}`,
            }))}
            current={form.values[c.id]}
            onPick={(x) => value(c.id, typeof c.default === 'number' ? Number(x) : x)}
            quote={quote}
          />
        ))}
      {wf.options
        .filter((o) => !o.top && offered(o, form.options))
        .map((o) => (
          <Pill
            key={o.id}
            name={o.label}
            choices={o.choices.map((c) => ({ id: c.id, label: `${o.label}: ${c.label}` }))}
            current={form.options[o.id]}
            onPick={(id) => option(o.id, id)}
            priced={o.id === 'quality' ? 'quality' : undefined}
            quote={quote}
          />
        ))}
      {form.kind !== 'upscaler' && (
        <a
          className={s.opt}
          href="/create"
          title="Open the full form on the Create page"
          onClick={(e) => {
            e.preventDefault();
            toCreate(navigate, { from: '/canvas' });
          }}
        >
          All settings
        </a>
      )}
    </div>
  );
}

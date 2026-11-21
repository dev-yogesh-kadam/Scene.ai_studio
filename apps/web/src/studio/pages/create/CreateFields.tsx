// The fields of the Create form for the chosen workflow: the prompt, the choices it depends on, size and length, a
// long video, the seed, everything else the workflow exposes (labelled with the node's own title), name and project.

import { useRef, useState, type ReactNode } from 'react';
import type { ProjectRow } from '@scene/shared/types/api';
import { api } from '../../../common/api';
import { Field } from '../../../common/components/AuthForm';
import { askText } from '../../../common/components/Dialog';
import { Segmented } from '../../../common/components/Segmented';
import { byRole, lengthChoices, optionsShown, type Control, type JobForm } from '../../features/jobs/jobForm';
import s from './CreatePage.module.css';
import { classesOf } from '../../../common/cx';
import css0 from '../../../common/components/Shared.module.css';
import css1 from '../../../common/components/Shared2.module.css';
import { userPrefs } from '../../userPrefs';
const css = classesOf(css0, css1);

type Props = {
  form: JobForm;
  onChange: (form: JobForm) => void;
  projects: ProjectRow[];
  onProjects: (projects: ProjectRow[]) => void;
  onError: (e: unknown) => void;
};

export function CreateFields({ form, onChange, projects, onProjects, onError }: Props) {
  const wf = form.wf;
  const [moreOpen, setMoreOpen] = useState(false);
  const set = (patch: Partial<JobForm>) => onChange({ ...form, ...patch });
  const setValue = (id: string, value: unknown) => onChange({ ...form, values: { ...form.values, [id]: value } });
  const special = new Set<string>();
  const parts: ReactNode[] = [];

  const promptControl = byRole(wf, 'prompt');
  if (promptControl) {
    special.add(promptControl.id);
    parts.push(
      <PromptField key="prompt" form={form} control={promptControl} onValue={(v) => setValue(promptControl.id, v)} />,
    );
  }

  // A choice can change which reference boxes the workflow reads; the boxes follow the form.
  const choice = (o: JobForm['wf']['options'][number]) => (
    <Field key={o.id} label={o.label}>
      <Segmented
        choices={o.choices}
        current={form.options[o.id]}
        onPick={(id) => set({ options: { ...form.options, [o.id]: String(id) } })}
      />
      <div className="hint">{o.choices.find((c) => c.id === form.options[o.id])?.hint || ''}</div>
    </Field>
  );
  // An option some choices leave out is not shown under them (Best upscale needs Upscale video or Sharpen first frame).
  const shown = optionsShown(form);
  parts.unshift(...shown.filter((o) => o.top).map(choice)); // what the whole form depends on comes first
  const groups: ReactNode[] = shown.filter((o) => !o.top).map(choice);
  const sizes = wf.resolutions.map((r) => ({ id: r, label: String(r) }));
  if (wf.size) {
    special.add(byRole(wf, 'width')?.id ?? '').add(byRole(wf, 'height')?.id ?? '');
    groups.push(
      <Field key="resolution" label="Resolution">
        <Segmented choices={sizes} current={form.resolution ?? 0} onPick={(r) => set({ resolution: Number(r) })} />
      </Field>,
      <Field key="orientation" label="Orientation">
        <Segmented
          choices={['landscape', 'portrait', 'square'].map((o) => ({ id: o, label: o[0].toUpperCase() + o.slice(1) }))}
          current={form.orientation ?? ''}
          onPick={(o) => set({ orientation: o })}
        />
      </Field>,
    );
  }
  const res = byRole(wf, 'resolution');
  if (res) {
    special.add(res.id);
    groups.push(
      <Field key="res-edge" label="Resolution (short edge)">
        <div className="row">
          <Segmented choices={sizes} current={Number(form.values[res.id])} onPick={(r) => setValue(res.id, r)} />
          <NumberInput
            control={res}
            value={form.values[res.id]}
            onValue={(v) => setValue(res.id, v)}
            style={{ width: 90 }}
          />
        </div>
      </Field>,
    );
  }
  const dur = byRole(wf, 'duration');
  if (dur) {
    special.add(dur.id);
    groups.push(
      <Field key="duration" label={form.clips > 1 ? 'Length of each clip' : 'Duration'}>
        <div className="row">
          <Segmented
            choices={lengthChoices(Number(form.values[dur.id])).map((d) => ({
              id: d,
              label: d + ' s',
            }))}
            current={Number(form.values[dur.id])}
            onPick={(d) => setValue(dur.id, d)}
          />
          <NumberInput
            control={dur}
            value={form.values[dur.id]}
            onValue={(v) => setValue(dur.id, v)}
            min={1}
            style={{ width: 80 }}
          />
        </div>
      </Field>,
    );
  }
  if (wf.chain && dur) {
    const total = form.clips * Number(form.values[dur.id]);
    groups.push(
      <Field key="clips" label="Long video (number of clips)">
        <Segmented
          choices={[1, 2, 3, 4, 6].map((n) => ({ id: n, label: n === 1 ? 'Off' : '× ' + n }))}
          current={form.clips}
          onPick={(n) => set({ clips: n })}
        />
        <div className="hint">
          {form.clips > 1
            ? `${form.clips} clips are made one after another, each starting on the last frame of the one before, then joined: about ${total} s in total.`
            : 'Make a longer video as several chained clips. Faster and steadier than one long clip.'}
        </div>
      </Field>,
    );
  }
  const seed = byRole(wf, 'seed');
  if (seed) special.add(seed.id);
  if (wf.seeded) {
    groups.push(
      <Field key="seed" label="Seed">
        <input
          type="number"
          min={0}
          max={4294967295}
          step={1}
          placeholder="Random"
          value={form.seed}
          onChange={(e) => set({ seed: e.target.value })}
        />
        <div className="hint">
          Empty: a new random seed on every Generate. A number: that seed again, so the same settings give the same
          picture.
        </div>
      </Field>,
    );
  }
  parts.push(
    <div key="groups" className={css('grid2')}>
      {groups}
    </div>,
  );

  // Everything else the workflow exposes. Controls a presets file marks as primary stay in view.
  const extra: ReactNode[] = [];
  const main: ReactNode[] = [];
  for (const c of wf.controls.filter((x) => !special.has(x.id))) {
    (c.primary ? main : extra).push(
      <ControlField key={c.id} control={c} value={form.values[c.id]} onValue={(v) => setValue(c.id, v)} />,
    );
  }
  if (main.length)
    parts.push(
      <div key="main" className={css('grid2')}>
        {main}
      </div>,
    );
  parts.push(
    <div key="name" className={css('grid2')}>
      <Field label="Name">
        <input type="text" value={form.name} onChange={(e) => set({ name: e.target.value })} />
      </Field>
      <Field label="Project">
        <select
          value={form.projectId ?? ''}
          onChange={async (e) => {
            if (e.target.value === 'new') {
              const name = await askText({ title: 'Name of the new project', confirm: 'Create' });
              if (!name) return;
              try {
                const created = await api<ProjectRow>('/api/projects', { method: 'POST', json: { name } });
                onProjects([...projects, created]);
                set({ projectId: created.id });
              } catch (err) {
                onError(err);
              }
              return;
            }
            const projectId = Number(e.target.value) || null;
            userPrefs.setStudio({ project: projectId || null });
            set({ projectId });
          }}
        >
          <option value="">No project</option>
          {projects.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name}
            </option>
          ))}
          <option value="new">New project…</option>
        </select>
      </Field>
    </div>,
  );
  // Settings most people leave alone stay folded away.
  if (extra.length) {
    parts.push(
      <details key="more" className={s.more} open={moreOpen} onToggle={(e) => setMoreOpen(e.currentTarget.open)}>
        <summary>{`More settings (${extra.length})`}</summary>
        <div className={css('grid2')}>{extra}</div>
      </details>,
    );
  }
  return <div>{parts}</div>;
}

function PromptField({ form, control, onValue }: { form: JobForm; control: Control; onValue: (v: string) => void }) {
  const file = useRef<HTMLInputElement>(null);
  return (
    <div className="field">
      <div className="label">
        Prompt
        <button type="button" className="btn small quiet" onClick={() => file.current?.click()}>
          Load .txt
        </button>
        <input
          ref={file}
          type="file"
          accept=".txt,text/plain"
          hidden
          onChange={async (e) => {
            const chosen = e.target.files?.[0];
            if (chosen) onValue((await chosen.text()).trim());
          }}
        />
      </div>
      <textarea
        placeholder={control.label}
        value={String(form.values[control.id] ?? '')}
        onChange={(e) => onValue(e.target.value)}
      />
      {form.clips > 1 && (
        <div className="hint">
          One prompt is used for every clip. To give each clip its own prompt, separate them with a line containing only
          ---
        </div>
      )}
    </div>
  );
}

function NumberInput({
  control,
  value,
  onValue,
  ...extra
}: {
  control: Control;
  value: unknown;
  onValue: (v: string) => void;
  min?: number;
  max?: number;
  style?: React.CSSProperties;
}) {
  return (
    <input
      type="number"
      value={value == null ? '' : String(value)}
      step={control.type === 'int' ? 1 : 'any'}
      {...extra}
      onChange={(e) => onValue(e.target.value)}
    />
  );
}

function ControlField({
  control: c,
  value,
  onValue,
}: {
  control: Control;
  value: unknown;
  onValue: (v: unknown) => void;
}) {
  if (c.type === 'bool') {
    return (
      <label className="check">
        <input type="checkbox" checked={!!value} onChange={(e) => onValue(e.target.checked)} />
        {c.label}
      </label>
    );
  }
  let input: ReactNode;
  if (c.choices && c.choices.length > 4) {
    input = (
      <select value={String(value)} onChange={(e) => onValue(e.target.value)}>
        {c.choices.map((x) => (
          <option key={String(x)} value={String(x)}>
            {x}
          </option>
        ))}
      </select>
    );
  } else if (c.choices) {
    input = (
      <Segmented
        choices={c.choices.map((x) => ({ id: x, label: String(x) }))}
        current={value as string | number}
        onPick={onValue}
      />
    );
  } else if (c.type === 'text') {
    input = <textarea value={String(value ?? '')} onChange={(e) => onValue(e.target.value)} />;
  } else if (c.type === 'string') {
    input = <input type="text" value={String(value ?? '')} onChange={(e) => onValue(e.target.value)} />;
  } else {
    input = <NumberInput control={c} value={value} onValue={onValue} />;
  }
  return <Field label={c.label}>{input}</Field>;
}

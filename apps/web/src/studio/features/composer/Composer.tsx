// The quick composer on Home and in the Canvas panel: a prompt, the few settings that matter most, and Generate.
// Everything else uses the workflow's own defaults; the Create page has the full form.

import { useQueryClient } from '@tanstack/react-query';
import { forwardRef, useCallback, useEffect, useImperativeHandle, useRef, useState } from 'react';
import { Link } from 'react-router';
import { api } from '../../../common/api';
import { ask } from '../../../common/components/Dialog';
import { creditsText } from '../../../common/format';
import type { Item } from '../../../common/media/item';
import { JOBS } from '../../live';
import { useUser } from '../../session';
import {
  byRole,
  estimate,
  lengthChoices,
  loadCatalog,
  loadWorkflow,
  newForm,
  optionsShown,
  pickValue,
  pickerGroups,
  splitPick,
  withModel,
  submitJob,
  warningsOf,
  type JobForm,
  type Quote,
  type WorkflowRow,
} from '../jobs/jobForm';
import { classesOf } from '../../../common/cx';
import css0 from '../../../common/components/Shared3.module.css';
import css1 from './Composer.module.css';
import { userPrefs } from '../../userPrefs';
const css = classesOf(css0, css1);

const KIND_LABEL: Record<string, string> = { video: 'Video', image: 'Image', audio: 'Audio' };

export type ComposerHandle = {
  focus: () => void;
  setPrompt: (text: string) => void;
  setWorkflow: (id: string) => void; // a starter prompt picks the workflow it was priced with
};

type Props = {
  startFrom?: Item | null; // the library item a new video should start on (the canvas selection)
  projectId?: number | null; // the project new work is filed under
  onQueued?: () => void; // a job was added to the queue
  initialPrompt?: string; // put into the prompt box once the first workflow is loaded (Home's waiting first prompt)
};

export const Composer = forwardRef<ComposerHandle, Props>(function Composer(
  { startFrom = null, projectId = null, onQueued = () => {}, initialPrompt = '' },
  ref,
) {
  const client = useQueryClient();
  const credits = useUser().credits;
  const [catalog, setCatalog] = useState<WorkflowRow[]>([]);
  const [form, setForm] = useState<JobForm | null>(null);
  const [useStart, setUseStart] = useState(true);
  const [seenStart, setSeenStart] = useState(startFrom);
  const [note, setNote] = useState('');
  const [quote, setQuote] = useState<Quote | null>(null);
  const [sending, setSending] = useState(false);
  const [off, setOff] = useState(false);
  const promptBox = useRef<HTMLTextAreaElement>(null);
  // What is typed is the box's own: it stays when the workflow changes, and can be typed before one is loaded.
  const [text, setText] = useState(initialPrompt);
  const prompt = form && byRole(form.wf, 'prompt');
  if (seenStart !== startFrom) {
    setSeenStart(startFrom); // a new selection: offer to start on it again
    setUseStart(true);
  }
  const firstFrame = form && form.wf.refs.find((r) => r.id === form.wf.slots.first_frame);

  // `picked`: a workflow's id, or a generation server model as "<workflow id>#<model>" (jobForm.pickValue).
  const select = useCallback(async (picked: string) => {
    const [id, model] = splitPick(picked);
    const wf = await loadWorkflow(id);
    const made = newForm(wf);
    setForm(model ? { ...made, ...withModel(wf, made.options, made.values, model) } : made);
    setNote('');
  }, []);

  useEffect(() => {
    loadCatalog()
      .then((list) => {
        const usable = list.workflows.filter((w) => !w.error && KIND_LABEL[w.kind]); // an upscaler has no prompt to type here
        setCatalog(usable);
        if (!usable.length) {
          setOff(true);
          setNote('No workflows yet. Save a ComfyUI workflow into the workflows folder, then reload.');
          return;
        }
        // The workflow the user picked last (or the studio's default, when one is set). With neither, none is picked
        // for them: they choose it in the Workflow cell.
        const kind = userPrefs.studio().kind || 'video';
        const last = userPrefs.studio().workflows[kind] || list.default || '';
        if (usable.some((w) => w.id === splitPick(last)[0])) return select(last);
      })
      .catch((e: Error) => setNote(e.message));
  }, [select]);

  useImperativeHandle(ref, () => ({
    focus: () => promptBox.current?.focus(),
    setPrompt: setText,
    setWorkflow: (id: string) => void select(id).catch((e: Error) => setNote(e.message)),
  }));

  // The job: the form, what is typed in the prompt box, and the project new work is filed under.
  const settingsOf = useCallback(
    (f: JobForm): JobForm => {
      const box = byRole(f.wf, 'prompt');
      return { ...f, projectId: projectId ?? null, values: box ? { ...f.values, [box.id]: text } : f.values };
    },
    [projectId, text],
  );

  // The price, after every change and when the balance changes.
  const key = form && JSON.stringify({ ...form, wf: form.wf.id, projectId, credits, text });
  useEffect(() => {
    if (!form) return;
    const timer = setTimeout(() => {
      estimate(settingsOf(form)).then(
        (q) => {
          setQuote(q);
          setNote(
            q.credits > q.balance ? `You have ${creditsText(q.balance)}. This needs ${creditsText(q.credits)}.` : '',
          );
        },
        (e: Error) => setNote(e.message),
      );
    }, 150);
    return () => clearTimeout(timer);
    // `key` stands for what the price depends on
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  const short = quote ? quote.credits > quote.balance : false;
  const generate = async () => {
    setNote('');
    if (!form || short || sending) return;
    if (prompt && !text.trim()) return setNote('Write a prompt first.');
    const item = useStart && firstFrame ? startFrom : null;
    if (form.wf.refs.some((r) => !r.optional && !(item && r.id === firstFrame?.id))) {
      return setNote('This workflow needs reference files. Add them on the Create page.');
    }
    const hits = warningsOf({ ...form, clips: 1 });
    if (
      hits.length &&
      !(await ask({
        title: 'Generate anyway?',
        confirm: 'Generate',
        message: hits.map((h) => h.message).join('\n') + `\n\nEstimated time: ${quote?.text || 'unknown'}`,
      }))
    )
      return;
    setSending(true);
    try {
      let job = settingsOf(form);
      if (item && firstFrame) {
        const made = await api<{ comfy_name: string; name: string }>(`/api/library/${item.id}/reference`, {
          method: 'POST',
        });
        job = { ...job, refs: { [firstFrame.id]: { existing: made.comfy_name, name: made.name } } };
      }
      await submitJob(job);
      void client.invalidateQueries({ queryKey: JOBS });
      onQueued();
    } catch (e) {
      setNote((e as Error).message);
    }
    setSending(false);
  };

  // `priced`: "resolution" or "quality", for a choice that changes the price: each option then says what it costs.
  const cell = (
    name: string,
    choices: { id: string | number; label: string }[],
    current: unknown,
    onPick: (value: string) => void,
    priced?: 'resolution' | 'quality',
  ) => {
    const prices = (priced && quote?.choices?.[priced]) || {};
    return (
      <label key={name} className={css('cell')}>
        <span>{name}</span>
        <select value={String(current)} onChange={(e) => onPick(e.target.value)}>
          {choices.map((c) => (
            <option key={String(c.id)} value={String(c.id)}>
              {c.label + (prices[String(c.id)] != null ? ` · ${prices[String(c.id)]} cr` : '')}
            </option>
          ))}
        </select>
      </label>
    );
  };

  // The Workflow cell: ComfyUI's workflows and the generation server's models, two groups never mixed. Another model
  // of the workflow in use keeps the form and only changes the model.
  const picked = (value: string) => {
    const [id, model] = splitPick(value);
    if (form && model && form.wf.id === id)
      setForm({ ...form, ...withModel(form.wf, form.options, form.values, model) });
    else void select(value).catch((err: Error) => setNote(err.message));
  };
  const cells = [
    catalog.length > 0 && (
      <label key="Workflow" className={css('cell')}>
        <span>Workflow</span>
        <select
          value={form ? pickValue(form.wf, form.options) : ''}
          onChange={(e) => e.target.value && picked(e.target.value)}
        >
          {!form && (
            <option value="" disabled>
              Choose a model…
            </option>
          )}
          {pickerGroups(catalog, (w) => `${KIND_LABEL[w.kind] || w.kind} · ${w.title}`).map((g) => (
            <optgroup key={g.label} label={g.label}>
              {g.entries.map((e) => (
                <option key={e.value} value={e.value}>
                  {e.label}
                </option>
              ))}
            </optgroup>
          ))}
        </select>
      </label>
    ),
  ];
  if (form) {
    const wf = form.wf;
    const set = (patch: Partial<JobForm>) => setForm({ ...form, ...patch });
    const sizes = wf.resolutions.map((r) => ({ id: r, label: String(r) }));
    if (wf.size) {
      cells.push(cell('Resolution', sizes, form.resolution, (r) => set({ resolution: Number(r) }), 'resolution'));
      cells.push(
        cell(
          'Orientation',
          ['landscape', 'portrait', 'square'].map((o) => ({ id: o, label: o[0].toUpperCase() + o.slice(1) })),
          form.orientation,
          (o) => set({ orientation: o }),
        ),
      );
    }
    const res = byRole(wf, 'resolution');
    if (res)
      cells.push(
        cell(
          'Resolution',
          sizes,
          form.values[res.id],
          (r) => set({ values: { ...form.values, [res.id]: Number(r) } }),
          'resolution',
        ),
      );
    const dur = byRole(wf, 'duration');
    if (dur) {
      const lengths = lengthChoices(wf, form.options, Number(form.values[dur.id]));
      cells.push(
        cell(
          'Length',
          lengths.map((d) => ({ id: d, label: d + ' s' })),
          form.values[dur.id],
          (d) => set({ values: { ...form.values, [dur.id]: Number(d) } }),
        ),
      );
    }
    for (const o of optionsShown(form).filter((o) => !(wf.source === 'generation' && o.id === 'model'))) {
      cells.push(
        cell(
          o.label,
          o.choices,
          form.options[o.id],
          (id) => set({ options: { ...form.options, [o.id]: id } }),
          o.id === 'quality' ? 'quality' : o.id === 'resolution' ? 'resolution' : undefined,
        ),
      );
    }
  }

  return (
    <div className={css('composer' + (off ? ' off' : ''))} role="group" aria-label="Composer">
      <div className={css('composer-start')}>
        {startFrom && firstFrame && (
          <label className="check">
            <input type="checkbox" checked={useStart} onChange={(e) => setUseStart(e.target.checked)} />
            {(startFrom.kind === 'video' ? 'Continue from the end of ' : 'Start on ') + startFrom.name}
          </label>
        )}
      </div>
      <textarea
        ref={promptBox}
        rows={2}
        aria-label="Prompt"
        placeholder="Describe the shot"
        value={text}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) void generate();
        }}
      />
      <div className={css('composer-foot')}>
        <div className={css('readout')}>
          {cells}
          {form && (
            <Link className={css('cell link')} to="/create" title="Open the full form on the Create page">
              <span>More</span>
              All settings
            </Link>
          )}
        </div>
        <button
          className="btn generate"
          title={`${quote?.text ? quote.text + ' · ' : ''}Generate (Ctrl or ⌘ + Enter)`}
          disabled={short || sending}
          onClick={() => void generate()}
        >
          <span>{sending ? 'Sending…' : 'Generate'}</span>
          <span className="cost">{quote ? creditsText(quote.credits) : ''}</span>
        </button>
      </div>
      <p className="error notice">{note}</p>
    </div>
  );
});

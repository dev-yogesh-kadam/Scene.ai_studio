// The Create page: pick a workflow, fill its form, queue a generation.

import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useCallback, useEffect, useRef, useState } from 'react';
import { Link, useLocation } from 'react-router';
import type { ProjectRow } from '@scene/shared/types/api';
import { itemsPage, oneItem } from '@scene/shared/api/items';
import { api } from '../../../common/api';
import { openDialog } from '../../../common/components/Dialog';
import { Segmented } from '../../../common/components/Segmented';
import { EmptyState, ErrorBanner, Skeleton } from '../../../common/components/States';
import { creditsText } from '../../../common/format';
import { seedOf, type Item } from '../../../common/media/item';
import { JobList } from '../../features/jobs/JobList';
import {
  byRole,
  estimate,
  existingRef,
  loadCatalog,
  loadWorkflow,
  newForm,
  submitJob,
  warningsOf,
  type Catalog,
  type JobForm,
  type Quote,
  type Warning,
} from '../../features/jobs/jobForm';
import { KeepField, type Keep } from '../../features/kit/KeepField';
import { MediaCard } from '../../features/media/MediaCard';
import { handoffOf, type Handoff, type Prefill } from '../../handoff';
import { JOBS, useJobs } from '../../live';
import { useUser } from '../../session';
import { CreateFields } from './CreateFields';
import { References } from './References';
import s from './CreatePage.module.css';
import { classesOf } from '../../../common/cx';
import css0 from '../../../common/components/Shared2.module.css';
import css1 from '../../../common/components/Shared3.module.css';
import css2 from '../../../common/components/Shared4.module.css';
import css3 from '../Shared.module.css';
import css4 from './CreatePage.module.css';
import css5 from '../projects/ProjectsPage.module.css';
import { userPrefs } from '../../userPrefs';
const css = classesOf(css0, css1, css2, css3, css4, css5);

const KIND_LABEL: Record<string, string> = { video: 'Video', image: 'Image', audio: 'Audio' };
type Saved = NonNullable<Item['settings']> & {
  seed_mode?: string;
  seed?: number | null;
  resolution?: number;
  orientation?: string;
  name?: string;
  clips?: number;
};

/** The form for `wf` with a library item's settings loaded (Re-run, Reuse seed). */
function withSaved(form: JobForm, saved: Saved): JobForm {
  const wf = form.wf;
  const next = { ...form, values: { ...form.values }, options: { ...form.options }, refs: { ...form.refs } };
  for (const c of wf.controls) if (saved.values && c.id in saved.values) next.values[c.id] = saved.values[c.id];
  // The prompt is also kept on its own: it carries over from a workflow whose prompt box had another id.
  const prompted = byRole(wf, 'prompt');
  if (prompted && saved.prompt && !(saved.values && prompted.id in saved.values))
    next.values[prompted.id] = saved.prompt;
  for (const o of wf.options) {
    const was = saved.options?.[o.id];
    if (was && o.choices.some((c) => c.id === was)) next.options[o.id] = was;
  }
  if (wf.size) {
    next.resolution = saved.resolution || next.resolution;
    next.orientation = saved.orientation || next.orientation;
  }
  next.seed = saved.seed_mode === 'fixed' && saved.seed != null ? String(saved.seed) : ''; // set by "Reuse seed" only
  next.name = saved.name || next.name;
  next.clips = wf.chain ? Number(saved.clips) || 1 : 1;
  for (const r of wf.refs) {
    const old = saved.refs?.[r.id];
    if (old?.comfy_name) next.refs[r.id] = existingRef({ comfy_name: old.comfy_name, name: old.name || '' });
  }
  return next;
}

/** What the address hands over (handoff.ts): the item to re-run is fetched by its id before the form is drawn. */
export default function CreatePage() {
  const { search } = useLocation();
  const handoff = handoffOf(search);
  const rerunId = handoff.rerun;
  const item = useQuery({
    queryKey: ['library', 'item', rerunId],
    queryFn: () => oneItem<Item>(rerunId ?? 0),
    enabled: !!rerunId,
  });
  if (rerunId && item.isPending) return null;
  // a new hand-off (Re-run from the list under the form) draws the form anew; one that is gone opens it empty
  return <CreateForm key={search} handoff={handoff} rerun={item.data} />;
}

function CreateForm({ handoff, rerun }: { handoff: Handoff; rerun?: Item }) {
  const client = useQueryClient();
  // Reuse seed: the result's own seed, so the picture stays the same with the settings changed.
  const reuseSeed = rerun && handoff.reuseSeed ? seedOf(rerun) : null;
  const [kind, setKind] = useState(() =>
    rerun ? rerun.workflow.split('/')[0] : handoff.prefill ? 'video' : userPrefs.studio().kind || 'video',
  );
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [projects, setProjects] = useState<ProjectRow[]>([]);
  const known = useRef<Set<number>>(new Set()); // the projects there are: one used last may have been deleted since
  const [form, setForm] = useState<JobForm | null>(null);
  const [error, setError] = useState('');
  const [quote, setQuote] = useState<Quote | null>(null);
  const [quoteError, setQuoteError] = useState('');
  const [sending, setSending] = useState(false);
  const [keep, setKeep] = useState<Keep>(undefined);
  const [kept, setKept] = useState(0); // counts Generates: the keep field empties after each
  const prefill = useRef<Prefill | undefined>(handoff.prefill);
  const first = useRef(true);
  const showError = useCallback((e: unknown) => setError((e as Error)?.message || String(e)), []);
  const jobs = useJobs();
  const credits = useUser().credits; // a new balance prices the form again

  // Choose a workflow: its defaults, then what was handed over (Re-run's settings, Use as first frame's reference).
  const select = useCallback(
    async (id: string, saved?: Saved) => {
      const wf = await loadWorkflow(id);
      userPrefs.setStudio({ workflows: { [wf.id.split('/')[0]]: id } });
      const last = userPrefs.studio().project;
      const projectId = last && known.current.has(last) ? last : null;
      let next = newForm(wf, { projectId, parent: rerun ? rerun.id : null });
      if (saved) next = withSaved(next, saved);
      setError('');
      const given = prefill.current;
      if (given) {
        prefill.current = undefined;
        const slot = wf.refs.find((r) => r.id === wf.slots[given.slot]);
        if (slot)
          next = { ...next, refs: { ...next.refs, [slot.id]: existingRef(given.ref) }, parent: given.parent || null };
        else setError('This workflow has no first-frame slot. Pick one that has, such as MiniMax H3.');
      }
      setForm(next);
    },
    [rerun],
  );

  const load = useCallback(async (wanted?: string, saved?: Saved) => {
    const [list, found] = await Promise.all([loadCatalog(), api<{ projects: ProjectRow[] }>('/api/projects')]);
    setCatalog(list);
    setProjects(found.projects);
    known.current = new Set(found.projects.map((p) => p.id));
    return { list, wanted, saved };
  }, []);

  // Which workflow to show for the kind: the one asked for, the one used last, or the studio's default. Work made with
  // a workflow that has since been merged into another is run again with the one that replaced it.
  const pickFor = useCallback(
    (list: Catalog, forKind: string, wanted?: string, saved?: Saved) => {
      const usable = list.workflows.filter((w) => w.kind === forKind && !w.error);
      if (!usable.length) return setForm(null);
      const want = wanted || userPrefs.studio().workflows[forKind] || list.default;
      const pick =
        usable.find((w) => w.id === want) || usable.find((w) => (w.replaces || []).includes(want)) || usable[0];
      const same = pick.id === want || (pick.replaces || []).includes(want);
      select(pick.id, same ? saved : undefined).catch(showError);
    },
    [select, showError],
  );

  useEffect(() => {
    if (!first.current) return;
    first.current = false;
    // Re-run: a new seed. Reuse seed: the result's own seed, so the picture stays the same with the settings changed.
    const saved = rerun
      ? ({
          ...rerun.settings,
          seed_mode: reuseSeed != null ? 'fixed' : 'random',
          seed: reuseSeed,
        } as Saved)
      : undefined;
    load(rerun?.workflow, saved).then(({ list }) => pickFor(list, kind, rerun?.workflow, saved), showError);
  }, [reuseSeed, kind, load, pickFor, rerun, showError]);

  // The price, again after every change (and when the credits or the library change).
  const priced = form && { ...form, keep };
  const priceKey = JSON.stringify(priced && { ...priced, wf: priced.wf.id, refs: Object.keys(priced.refs), credits });
  useEffect(() => {
    if (!priced) return;
    const timer = setTimeout(() => {
      estimate(priced).then(
        (q) => {
          setQuote(q);
          setQuoteError('');
        },
        (e: Error) => setQuoteError(e.message),
      );
    }, 150);
    return () => clearTimeout(timer);
    // priceKey stands for what the price depends on
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [priceKey]);

  const generate = async (confirmed = false): Promise<void> => {
    setError('');
    if (!form) return;
    const prompt = byRole(form.wf, 'prompt');
    if (prompt && !String(form.values[prompt.id] || '').trim()) return showError(new Error('Write a prompt first.'));
    const hits = warningsOf(form);
    if (hits.length && !confirmed) return askToConfirm(hits);
    setSending(true);
    try {
      await submitJob({ ...form, keep });
      setKept((k) => k + 1); // kept once: the next one is not kept unless asked again
      void client.invalidateQueries({ queryKey: JOBS });
    } catch (e) {
      showError(e);
    }
    setSending(false);
  };

  const askToConfirm = async (hits: Warning[]): Promise<void> => {
    const answer = await openDialog<'go' | { set: Record<string, unknown> }>((close) => (
      <>
        <h2>Before you start</h2>
        <ul>
          {hits.map((h) => (
            <li key={h.message}>{h.message}</li>
          ))}
        </ul>
        <p className="muted" style={{ marginTop: 10 }}>
          {'Estimated time: ' + (quote?.text || 'unknown')}
        </p>
        <div className={css('dialog-buttons')}>
          <button className="btn" onClick={() => close()}>
            Cancel
          </button>
          {hits
            .filter((h) => h.alt)
            .map((h) => (
              <button key={h.alt!.label} className="btn" onClick={() => close({ set: h.alt!.set })}>
                {h.alt!.label}
              </button>
            ))}
          <button className="btn generate" onClick={() => close('go')}>
            Generate anyway
          </button>
        </div>
      </>
    ));
    if (answer === 'go') return generate(true);
    if (answer && form) {
      // the alternative a warning offers: its settings put into the form
      const next = { ...form, values: { ...form.values }, options: { ...form.options } };
      for (const [key, value] of Object.entries(answer.set)) {
        if (key in next.options) next.options[key] = String(value);
        else if (byRole(form.wf, key)) next.values[byRole(form.wf, key)!.id] = value;
        else if (key !== 'clips' || form.wf.chain) Object.assign(next, { [key]: value });
      }
      setForm(next);
    }
  };

  const chooseKind = (k: string) => {
    setKind(k);
    userPrefs.setStudio({ kind: k });
    if (catalog) pickFor(catalog, k);
  };

  const items = catalog ? catalog.workflows.filter((w) => w.kind === kind) : [];
  const usable = items.filter((w) => !w.error);
  const note = !catalog
    ? ''
    : !usable.length
      ? items.length
        ? items[0].error
        : `No ${kind} workflows yet. Save a ComfyUI workflow into the workflows/${kind} folder, then press Refresh.`
      : form
        ? form.wf.description +
          (form.wf.approximate ? ' Some node settings were guessed because the render server is offline.' : '')
        : '';
  const short = quote ? quote.credits > quote.balance : false;

  return (
    <>
      <div className={css('page-head')}>
        {handoff.from === '/canvas' && (
          <Link className="btn" to="/canvas" title="Back to the canvas of this project">
            ← Canvas
          </Link>
        )}
        <h1>Create</h1>
        <div>
          {catalog && (
            <Segmented
              choices={catalog.kinds.map((k) => ({ id: k, label: KIND_LABEL[k] || k }))}
              current={kind}
              onPick={chooseKind}
            />
          )}
        </div>
      </div>
      <div className={s.create}>
        <div className={css('card ' + s['create-form'])}>
          <div className={css('card-head')}>
            <h2>Workflow</h2>
            <select
              aria-label="Workflow"
              style={{ maxWidth: 320 }}
              className={items.length ? '' : 'hidden'}
              value={form?.wf.id ?? ''}
              onChange={(e) => select(e.target.value).catch(showError)}
            >
              {items.map((w) => (
                <option key={w.id} value={w.id} disabled={!!w.error}>
                  {w.title + (w.error ? ' (not readable yet)' : '')}
                </option>
              ))}
            </select>
            <button
              className="btn small quiet"
              title="Look for new workflow files"
              onClick={() => load().then(({ list }) => pickFor(list, kind, form?.wf.id), showError)}
            >
              Refresh
            </button>
          </div>
          <p className="muted">{note}</p>
          <div className={form && usable.length ? '' : 'hidden'}>
            {form && (
              <>
                <CreateFields
                  form={form}
                  onChange={setForm}
                  projects={projects}
                  onProjects={setProjects}
                  onError={showError}
                />
                <References form={form} onChange={setForm} />
                <details className={s.tips + (form.wf.hints.length ? '' : ' hidden')}>
                  <summary>Tips</summary>
                  <ul>
                    {form.wf.hints.map((h) => (
                      <li key={h}>{h}</li>
                    ))}
                  </ul>
                </details>
                <KeepField
                  kindMade={form.wf.id.split('/')[0]}
                  inProject={!!form.projectId}
                  onChange={setKeep}
                  resetKey={kept}
                />
              </>
            )}
            <p className="error notice">{error}</p>
            <div className={s['generate-bar']}>
              <div className={s.estimate}>
                {quoteError ||
                  (quote && (
                    <>
                      <b>{quote.text}</b>
                      <span className={short ? 'error' : ''}>
                        {short
                          ? ` · this needs ${creditsText(quote.credits)} and you have ${creditsText(quote.balance)}`
                          : ` · you have ${creditsText(quote.balance)}`}
                      </span>
                    </>
                  ))}
              </div>
              <button className="btn generate" disabled={sending} onClick={() => void generate(false)}>
                <span>{sending ? 'Uploading…' : 'Generate'}</span>
                <span className="cost">{quote ? creditsText(quote.credits) : ''}</span>
              </button>
            </div>
          </div>
        </div>
        <div>
          <div className={css('card')}>
            <div className={css('card-head')}>
              <h2>Queue</h2>
            </div>
            <JobList jobs={jobs} limit={5} />
          </div>
          <div className={css('card')}>
            <div className={css('card-head')}>
              <h2>Latest</h2>
              <Link className="btn small quiet" to="/library">
                Open library
              </Link>
            </div>
            <Latest />
          </div>
        </div>
      </div>
    </>
  );
}

const LATEST = 4; // the newest results shown under the form

function Latest() {
  const latest = useQuery({
    queryKey: ['library', 'latest'],
    queryFn: () => itemsPage<Item>({ limit: LATEST }).then((a) => a.items),
  });
  const items = latest.data;
  return (
    <div className={css('media-grid compact')}>
      {latest.isError ? (
        <ErrorBanner error={latest.error} onRetry={() => void latest.refetch()} wide />
      ) : items?.length ? (
        items.map((i) => <MediaCard key={i.id} item={i} />)
      ) : items ? (
        <EmptyState wide>Your finished work shows up here.</EmptyState>
      ) : (
        <Skeleton count={LATEST} />
      )}
    </div>
  );
}

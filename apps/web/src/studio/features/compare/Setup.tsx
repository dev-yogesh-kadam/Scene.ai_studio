// The left side of the compare board: a test set up. Prompts are rows (a shot made by every workflow), the ticked
// workflows are columns; the same pictures go to every prompt; quality, takes per cell, and for videos the size, shape
// and length; one seed for every cell for a fair comparison.

import { useQuery } from '@tanstack/react-query';
import { useEffect, useMemo, useRef } from 'react';
import { bulkWorkflows, type BulkWorkflow } from '@scene/shared/api/bulk';
import { Field } from '../../../common/components/AuthForm';
import { askText } from '../../../common/components/Dialog';
import { Segmented } from '../../../common/components/Segmented';
import { cx, mergeModules } from '../../../common/cx';
import s1 from './Compare.module.css';
import s2 from './Compare2.module.css';

const s = mergeModules(s1, s2);

const KINDS = [
  { id: 'image', label: 'Images' },
  { id: 'video', label: 'Videos' },
];
const QUALITY = [
  { id: 'draft', label: 'Draft' },
  { id: 'final', label: 'Final' },
];
const SIZES = [
  { id: 480, label: '480p' },
  { id: 720, label: '720p' },
  { id: 1080, label: '1080p' },
];
const SHAPES = [
  { id: 'landscape', label: 'Landscape' },
  { id: 'portrait', label: 'Portrait' },
  { id: 'square', label: 'Square' },
];
const TAKES = [1, 2, 3, 4].map((n) => ({ id: n, label: String(n) }));
export const MOST_PICTURES = 6;
export const MOST_PROMPTS = 20;
export const MOST_JOBS = 400;

export const short = (title: string) => String(title || '').replace(/^(Text|Image) to (Image|Video): /, '');

export type Test = {
  kind: string;
  prompts: string[];
  pictures: File[];
  quality: string;
  resolution: number;
  orientation: string;
  duration: number;
  takes: number;
  sameSeed: boolean;
  picked: Record<string, string[]>; // the workflows ticked, per kind
  filter: string;
};

export const NEW_TEST: Test = {
  kind: 'image',
  prompts: [''],
  pictures: [],
  quality: 'final',
  resolution: 720,
  orientation: 'landscape',
  duration: 5,
  takes: 1,
  sameSeed: true,
  picked: {},
  filter: '',
};

export const usable = (w: BulkWorkflow, pictures: number) =>
  !w.error && !w.needs_other.length && w.needs_pictures <= pictures;
const why = (w: BulkWorkflow, pictures: number) =>
  w.error
    ? 'Not readable'
    : w.needs_other.length
      ? `Needs ${w.needs_other.join(', ')}`
      : w.needs_pictures > pictures
        ? `Needs ${w.needs_pictures} picture${w.needs_pictures === 1 ? '' : 's'}`
        : w.pictures
          ? `${w.pictures} picture slot${w.pictures === 1 ? '' : 's'}`
          : 'Prompt only';

export function useWorkflows(kind: string) {
  return useQuery({ queryKey: ['bulk', 'workflows', kind], queryFn: () => bulkWorkflows(kind), staleTime: Infinity });
}

type Props = {
  test: Test;
  set: (change: Partial<Test>) => void;
  starting: boolean;
  notice: string;
  onStart: (ready: BulkWorkflow[]) => void;
};

export function Setup({ test, set, starting, notice, onStart }: Props) {
  const list = useWorkflows(test.kind);
  const workflows = useMemo(() => list.data ?? [], [list.data]);
  const picked = new Set(test.picked[test.kind] ?? []);
  const ready = workflows.filter((w) => picked.has(w.id) && usable(w, test.pictures.length));
  const prompts = test.prompts.filter((p) => p.trim()).length;
  const total = prompts * ready.length * test.takes;
  const files = useRef<HTMLInputElement>(null);
  const boxes = useRef<(HTMLTextAreaElement | null)[]>([]);
  const added = useRef(false);
  useEffect(() => {
    if (!added.current) return;
    added.current = false;
    boxes.current[test.prompts.length - 1]?.focus(); // a prompt added: its box takes the focus
  }, [test.prompts.length]);
  const pick = (ids: string[]) => set({ picked: { ...test.picked, [test.kind]: ids } });
  const thumbs = useMemo(() => test.pictures.map((file) => URL.createObjectURL(file)), [test.pictures]);
  useEffect(() => () => thumbs.forEach((url) => URL.revokeObjectURL(url)), [thumbs]);

  const paste = async () => {
    // many prompts at once: one per line
    const text = await askText({ title: 'Paste prompts, one per line:', confirm: 'Add', maxLength: 20000 });
    if (!text) return;
    const lines = text
      .split(/\r?\n/)
      .map((l) => l.trim())
      .filter(Boolean);
    const next = [...test.prompts.filter((x) => x.trim()), ...lines].slice(0, MOST_PROMPTS);
    set({ prompts: next.length ? next : [''] });
  };

  const shown = workflows.filter((w) => !test.filter || w.title.toLowerCase().includes(test.filter.toLowerCase()));
  return (
    <>
      <Segmented className={s.kinds} choices={KINDS} current={test.kind} onPick={(kind) => set({ kind })} />
      <div className={s['board-group']}>
        <div className={s['board-label']}>
          <span>{`Prompts · ${test.prompts.length} of ${MOST_PROMPTS}`}</span>
          <span className="row">
            <button className="btn small quiet" type="button" onClick={() => void paste()}>
              Paste many
            </button>
            <button
              className="btn small"
              type="button"
              disabled={test.prompts.length >= MOST_PROMPTS}
              onClick={() => {
                added.current = true;
                set({ prompts: [...test.prompts, ''] });
              }}
            >
              + Prompt
            </button>
          </span>
        </div>
        <p className={cx('hint', s.hint)}>Each prompt is a row of the board, a shot made by every workflow.</p>
        {test.prompts.map((p, i) => (
          <div key={i} className={s['board-prompt']}>
            <span className={s['board-shot']}>{`Shot ${i + 1}`}</span>
            <textarea
              ref={(box) => {
                boxes.current[i] = box;
              }}
              rows={2}
              placeholder={i ? 'Another prompt' : 'What to make'}
              value={p}
              onChange={(e) => set({ prompts: test.prompts.map((x, n) => (n === i ? e.target.value : x)) })}
            />
            {test.prompts.length > 1 && (
              <button
                className="icon-btn"
                type="button"
                aria-label={`Remove shot ${i + 1}`}
                title="Remove"
                onClick={() => set({ prompts: test.prompts.filter((_, n) => n !== i) })}
              >
                ×
              </button>
            )}
          </div>
        ))}
      </div>
      <div className={s['board-group']}>
        <div className={s['board-label']}>
          <span>{`Workflows · ${picked.size} ticked`}</span>
          <span className="row">
            <button
              className="btn small quiet"
              type="button"
              onClick={() =>
                pick([
                  ...new Set([...picked, ...workflows.filter((w) => usable(w, test.pictures.length)).map((w) => w.id)]),
                ])
              }
            >
              All
            </button>
            <button className="btn small quiet" type="button" onClick={() => pick([])}>
              None
            </button>
          </span>
        </div>
        <input
          type="search"
          className="search"
          placeholder="Find a workflow"
          value={test.filter}
          onChange={(e) => set({ filter: e.target.value })}
        />
        <div className={s['board-checks']}>
          {shown.map((w) => (
            <label key={w.id} className={cx(s['bulk-check'], !usable(w, test.pictures.length) && s.off)}>
              <input
                type="checkbox"
                checked={picked.has(w.id)}
                disabled={!!w.error}
                onChange={(e) => pick(e.target.checked ? [...picked, w.id] : [...picked].filter((id) => id !== w.id))}
              />
              <span className={s['bulk-name']} title={w.title}>
                {short(w.title)}
              </span>
              <span className="muted small">{why(w, test.pictures.length)}</span>
            </label>
          ))}
        </div>
      </div>
      <div className={s['board-group']}>
        <div className={s['board-label']}>
          <span>{`Pictures · ${test.pictures.length} of ${MOST_PICTURES}`}</span>
        </div>
        <div className={s['bulk-pictures']}>
          {test.pictures.map((file, i) => (
            <div key={i} className={s['bulk-picture']} title={`Picture ${i + 1}: ${file.name}`}>
              <img src={thumbs[i]} alt={file.name} />
              <button
                className={cx('icon-btn', s.remove)}
                type="button"
                aria-label={'Remove ' + file.name}
                onClick={() => set({ pictures: test.pictures.filter((_, n) => n !== i) })}
              >
                ×
              </button>
            </div>
          ))}
          {test.pictures.length < MOST_PICTURES && (
            <button className={s['bulk-add']} type="button" title="Add pictures" onClick={() => files.current?.click()}>
              +
            </button>
          )}
          <input
            ref={files}
            type="file"
            accept="image/*"
            multiple
            className="hidden"
            onChange={(e) => {
              set({ pictures: [...test.pictures, ...(e.target.files ?? [])].slice(0, MOST_PICTURES) });
              e.target.value = '';
            }}
          />
        </div>
        <p className={cx('hint', s.hint)}>
          The same pictures for every prompt: picture 1 in each workflow&apos;s first picture slot, and so on.
        </p>
      </div>
      <div className={cx(s['board-group'], s['board-grid2'])}>
        <Field label="Quality">
          <Segmented choices={QUALITY} current={test.quality} onPick={(quality) => set({ quality })} />
        </Field>
        <Field label="Takes per cell">
          <Segmented choices={TAKES} current={test.takes} onPick={(takes) => set({ takes })} />
        </Field>
        {test.kind === 'video' && (
          <>
            <Field label="Size">
              <Segmented choices={SIZES} current={test.resolution} onPick={(resolution) => set({ resolution })} />
            </Field>
            <Field label="Shape">
              <Segmented choices={SHAPES} current={test.orientation} onPick={(orientation) => set({ orientation })} />
            </Field>
            <Field label="Length (seconds)">
              <input
                type="number"
                min={1}
                max={20}
                value={test.duration}
                onChange={(e) => set({ duration: Number(e.target.value) || 5 })}
              />
            </Field>
          </>
        )}
      </div>
      <label className="check">
        <input type="checkbox" checked={test.sameSeed} onChange={(e) => set({ sameSeed: e.target.checked })} />
        One seed for every cell (a fair comparison; each take gets its own)
      </label>
      <div className={s['board-go']}>
        <div className={s['board-count']}>
          <b>
            {`${prompts} prompt${prompts === 1 ? '' : 's'} × ${ready.length} workflow${ready.length === 1 ? '' : 's'}` +
              (test.takes > 1 ? ` × ${test.takes} takes` : '')}
          </b>
          <span>{` = ${total} render${total === 1 ? '' : 's'}`}</span>
        </div>
        <p className={cx('notice', (notice || list.error) && 'error')}>{notice || list.error?.message || ''}</p>
        <button
          className="btn primary block"
          disabled={!total || total > MOST_JOBS || starting}
          onClick={() => onStart(ready)}
        >
          {starting
            ? 'Starting…'
            : total > MOST_JOBS
              ? `At most ${MOST_JOBS} renders in one run`
              : `Run the test · ${total} render${total === 1 ? '' : 's'}`}
        </button>
      </div>
    </>
  );
}

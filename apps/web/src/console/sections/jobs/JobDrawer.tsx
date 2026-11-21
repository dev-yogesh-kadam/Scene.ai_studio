// One job in the console: what it was asked to make, what became of it, and what can be done with it.

import { useQuery } from '@tanstack/react-query';
import { api } from '../../../common/api';
import { useConsole } from '../shared/context';
import { Drawer } from '../shared/Drawer';
import { Facts, Pill, Section, Thumb, bytes, failed, itemUrl, span, stamp, sure } from '../shared/ui';
import { classesOf } from '../../../common/cx';
import css0 from '../../../common/components/Shared3.module.css';
import css1 from './JobDrawer.module.css';
import css2 from '../shared/Console.module.css';
const css = classesOf(css0, css1, css2);

type Job = {
  id: string;
  name: string;
  user_name: string;
  user_email: string;
  status: string;
  error?: string;
  explained?: string;
  cost: number;
  workflow: string;
  summary?: string;
  credits_reserved?: boolean;
  credits_consumed?: boolean;
  seconds_requested?: number;
  server?: string;
  output_size?: number;
  created: number;
  started: number | null;
  finished: number | null;
  est_seconds?: number;
  settings: {
    values?: Record<string, unknown>;
    options?: Record<string, unknown>;
    resolution?: number;
    orientation?: string;
    clips?: number;
    seed_mode?: string;
    refs?: Record<string, { name?: string; comfy_name?: string }>;
  };
  items: { id: number; kind: string; name: string; filename: string }[];
};

function Body({ j, close }: { j: Job; close: () => void }) {
  const { refresh, go } = useConsole();
  const st = j.settings;
  const values = Object.entries(st.values || {});
  const promptText = values.find(([, v]) => typeof v === 'string' && v.length > 20)?.[1] as string | undefined;
  const active = ['queued', 'running'].includes(j.status);
  const after = () => {
    close();
    void refresh();
  };
  const retry = (free: boolean) =>
    api(`/api/admin/jobs/${j.id}/retry`, { method: 'POST', json: { free } }).then(() => {
      close();
      go('jobs', { status: 'active' });
    }, failed);
  const held = j.credits_reserved
    ? ' (held)'
    : j.credits_consumed
      ? ' (used)'
      : j.status === 'done' || active
        ? ''
        : ' (refunded)';
  return (
    <>
      <div className={css('drawer-title')}>
        <div>
          <b>{j.name}</b>
          <div className="muted">{`${j.user_name} · ${j.user_email}`}</div>
        </div>
        <Pill status={j.status} />
      </div>
      {j.error && (
        <div className={css('alert critical static')}>
          <span className={css('alert-level')}>Error</span>
          <span className={css('alert-text')}>
            {j.explained ? (
              <span>
                <b>{j.explained}</b>
                <div className="muted small">{j.error}</div>
              </span>
            ) : (
              j.error
            )}
          </span>
        </div>
      )}
      <div className="row">
        {active && (
          <button
            className="btn small danger"
            onClick={() => {
              void sure(`Cancel "${j.name}"? The user's credits are refunded.`).then((yes) => {
                if (yes) void api('/api/admin/jobs/' + j.id, { method: 'DELETE' }).then(after, failed);
              });
            }}
          >
            Cancel this job
          </button>
        )}
        {j.status === 'queued' && (
          <button
            className="btn small"
            onClick={() => void api(`/api/admin/jobs/${j.id}/front`, { method: 'POST' }).then(after, failed)}
          >
            Move to the front
          </button>
        )}
        {['failed', 'cancelled'].includes(j.status) && (
          <>
            <button
              className="btn small primary"
              title="Its first run was refunded, so this is charged like a new job"
              onClick={() => {
                void sure(
                  `Run "${j.name}" again for ${j.user_name}? It costs them ${j.cost} credits, as a new job would.`,
                ).then((yes) => {
                  if (yes) void retry(false);
                });
              }}
            >
              {`Run again (${j.cost} credits)`}
            </button>
            <button
              className="btn small"
              title="For a failure that was the studio's fault"
              onClick={() => {
                void sure(`Run "${j.name}" again for ${j.user_name} at no charge?`).then((yes) => {
                  if (yes) void retry(true);
                });
              }}
            >
              Run again free
            </button>
          </>
        )}
      </div>
      <Section title="Details">
        <Facts
          pairs={[
            ['Workflow', j.workflow],
            ['Settings', j.summary],
            ['Credits', String(j.cost) + held],
            ['Length asked for', j.seconds_requested ? span(j.seconds_requested) : null],
            ['Made by', j.server],
            ['Output size', j.output_size ? bytes(j.output_size) : null],
            ['Added', stamp(j.created)],
            ['Waited in queue', j.started ? span(j.started - j.created) : 'Not started'],
            ['Time to make', j.finished && j.started ? span(j.finished - j.started) : null],
            ['Estimated', j.est_seconds ? span(j.est_seconds) : 'No estimate'],
            ['Job id', j.id],
          ]}
        />
      </Section>
      {promptText && (
        <Section title="Prompt">
          <p className={css('prose')}>{promptText}</p>
        </Section>
      )}
      <Section title="Options">
        <Facts
          pairs={[
            ...Object.entries(st.options || {}).map(([k, v]) => [k, String(v)] as const),
            ['Resolution', st.resolution && `${st.resolution}p ${st.orientation || ''}`],
            ['Clips', (st.clips ?? 0) > 1 ? String(st.clips) : null],
            ['Seed', st.seed_mode],
            ...values.filter(([, v]) => v !== promptText).map(([k, v]) => ['Setting ' + k, String(v)] as const),
          ]}
        />
      </Section>
      {Object.keys(st.refs || {}).length > 0 && (
        <Section title="References">
          <Facts
            pairs={Object.entries(st.refs || {}).map(([slot, r]) => ['Slot ' + slot, r.name || r.comfy_name] as const)}
          />
        </Section>
      )}
      {j.items.length > 0 && (
        <Section title="Result">
          <div className={css('thumbs')}>
            {j.items.map((i) => (
              <a
                key={i.id}
                className={css('thumb-box')}
                href={itemUrl(i.id)}
                target="_blank"
                rel="noreferrer"
                title={'Open ' + i.filename}
              >
                <Thumb item={i} />
              </a>
            ))}
          </div>
        </Section>
      )}
    </>
  );
}

export function JobDrawer({ id, onClose }: { id: string; onClose: () => void }) {
  const query = useQuery({ queryKey: ['console', 'job', id], queryFn: () => api<Job>('/api/admin/jobs/' + id) });
  return (
    <Drawer title="Job" onClose={onClose}>
      {(close) =>
        query.error ? (
          <p className="error">{query.error.message}</p>
        ) : query.data ? (
          <Body j={query.data} close={() => close()} />
        ) : (
          <p className="muted">Loading…</p>
        )
      }
    </Drawer>
  );
}

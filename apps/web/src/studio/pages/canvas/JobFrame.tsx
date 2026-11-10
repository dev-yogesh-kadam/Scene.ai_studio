// A frame for work in progress, where its result will land: it develops like a print in a tray (the grain clears as
// the steps go by), with a clock of how long it has been at it, a paper plane or a clapperboard looping under it, and a
// reel that fills in. A job that failed stays a day where its result would have been, saying why.

import { memo, useEffect, useState } from 'react';
import { Clapper, Flight, Reel, Run } from '../../../common/components/Film/Film';
import { openDialog } from '../../../common/components/Dialog';
import { cx } from '../../../common/cx';
import type { CanvasJob } from './arrange';
import type { Spot } from './geometry';
import s from './Frame.module.css';
import { classesOf } from '../../../common/cx';
import css0 from './JobFrame.module.css';
const css = classesOf(css0);

const elapsed = (job: CanvasJob, now: number) => {
  const sec = Math.max(0, Math.round(now / 1000 - (job.started || now / 1000)));
  return String(Math.floor(sec / 60)).padStart(2, '0') + ':' + String(sec % 60).padStart(2, '0');
};

/** The time now, moving every second while `on`. */
function useClock(on: boolean) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!on) return;
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [on]);
  return now;
}

export const JobFrame = memo(function JobFrame({
  job,
  spot,
  byAgent,
  admin,
}: {
  job: CanvasJob;
  spot: Spot;
  byAgent: boolean;
  admin: boolean;
}) {
  const waiting = job.status === 'queued';
  const now = useClock(job.status === 'running');
  if (job.status === 'failed') return <FailedFrame job={job} spot={spot} admin={admin} />;
  // The pick comes from the job's id, so a frame keeps its own while it is drawn again.
  const clapper = [...job.id].reduce((n, c) => n + c.charCodeAt(0), 0) % 2 === 1;
  const done = job.steps ? (Math.max(job.clip, 1) - 1 + job.step / job.steps) / Math.max(job.clips, 1) : 0;
  return (
    <div
      className={cx(s.frame, s.developing, waiting && s.waiting, byAgent && s['by-agent'])}
      style={{ left: spot.x, top: spot.y }}
      title={job.name}
    >
      <div className={s.shot} style={{ height: spot.h, ['--developed' as string]: done.toFixed(3) }}>
        <div className={s['shot-wait']}>
          {/* how long it has been at it; no percentage */}
          <span>{waiting ? 'queued' : elapsed(job, now)}</span>
          {clapper ? <Clapper className={s.film} /> : <Flight className={s.film} />}
        </div>
        {!waiting && <Run className={s.run} />}
      </div>
      <Reel share={done} count={32} className={s.reel} />
      <div className={s.slate}>
        <b>{job.workflow.split('/')[0]}</b>
        {/* words only while it waits (its place in the queue); while it runs, the clock and the animation are enough */}
        <span>
          {waiting ? (job.waiting_for_server ? 'waiting for the render server' : `position ${job.position}`) : ''}
        </span>
      </div>
    </div>
  );
});

function FailedFrame({ job, spot, admin }: { job: CanvasJob; spot: Spot; admin: boolean }) {
  const details = () => void failedDetails(job, admin);
  return (
    <div
      className={cx(s.frame, s.failed)}
      style={{ left: spot.x, top: spot.y }}
      title="Open for the details"
      role="button"
      tabIndex={0}
      onClick={details}
      onKeyDown={(e) => {
        if (e.key === 'Enter') details();
      }}
    >
      <div className={cx(s.shot, s['failed-shot'])} style={{ height: spot.h }}>
        <b>Didn&apos;t work</b>
        <span>{job.reason || 'Something went wrong while it was being made.'}</span>
        <span className={s['failed-credits']}>{job.cost ? `Your ${job.cost} credits came back.` : ''}</span>
      </div>
      <div className={s.slate}>
        <b>{job.workflow.split('/')[0]}</b>
        <span>{job.name}</span>
      </div>
    </div>
  );
}

/** What a failed job was asked to make and what became of it. An admin also sees the render server's own words. */
function failedDetails(job: CanvasJob, admin: boolean) {
  const st = (job.settings ?? {}) as {
    resolution?: number;
    orientation?: string;
    options?: Record<string, string>;
    workflow_title?: string;
    prompt?: string;
  };
  const when = (t: number | null) =>
    t ? new Date(t * 1000).toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' }) : '';
  const ran = job.started && job.finished ? Math.max(0, Math.round(job.finished - job.started)) : null;
  const chosen = [
    st.resolution && `${st.resolution}p`,
    st.orientation,
    ...Object.entries(st.options || {}).map(([k, v]) => `${k}: ${v}`),
  ]
    .filter(Boolean)
    .join(' · ');
  const facts = (
    [
      ['Model', st.workflow_title || job.workflow],
      ['Prompt', st.prompt],
      ['Settings', chosen || job.summary],
      ['Asked at', when(job.created)],
      ['Stopped at', when(job.finished)],
      ['Ran for', ran == null ? '' : ran < 90 ? `${ran} s` : `${Math.round(ran / 60)} min`],
      ['Credits', job.cost ? `${job.cost} charged, all ${job.cost} given back` : 'Free'],
    ] as [string, string | undefined][]
  ).filter(([, v]) => v);
  return openDialog(
    (close) => (
      <>
        <h2>Didn&apos;t work</h2>
        <p className={css('failed-reason')}>{job.reason || 'Something went wrong while it was being made.'}</p>
        <dl className={css('failed-facts')}>
          {facts.flatMap(([k, v]) => [<dt key={k + ':k'}>{k}</dt>, <dd key={k + ':v'}>{v}</dd>])}
        </dl>
        {admin && job.error ? (
          <details className={css('failed-raw')}>
            <summary>What the render server said</summary>
            <pre>{job.error}</pre>
          </details>
        ) : null}
        <div className="row" style={{ justifyContent: 'flex-end', marginTop: 16 }}>
          <button className="btn" onClick={() => close()}>
            Close
          </button>
        </div>
      </>
    ),
    { className: css('failed-dialog'), label: "Why it didn't work" },
  );
}

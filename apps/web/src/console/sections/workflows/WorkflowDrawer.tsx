// One workflow: who it is offered to, its resolutions, a test run, what it lacks, and its versions.

import { useState } from 'react';
import { api } from '../../../common/api';
import { Segmented } from '../../../common/components/Segmented';
import { Drawer } from '../shared/Drawer';
import { useConsole, useSection } from '../shared/context';
import { Facts, Section, Table, ago, number, span, stamp } from '../shared/ui';
import { ResolutionSwitches } from './ResolutionSwitches';
import { AUDIENCE, CHANGE, Tag, succeeded, type Report, type Version, type Workflow } from './workflowData';
import { classesOf } from '../../../common/cx';
import css0 from '../shared/Console.module.css';
const css = classesOf(css0);

const List = ({ changes }: { changes: string[] }) => (
  <ul className="small">
    {changes.map((c, i) => (
      <li key={i}>{c}</li>
    ))}
  </ul>
);

const Lines = ({ changes }: { changes: string[] }) =>
  changes.length > 12 ? (
    <details>
      <summary className="small">{`${changes.length} changes`}</summary>
      <List changes={changes} />
    </details>
  ) : (
    <List changes={changes} />
  );

export function WorkflowDrawer({
  workflow: w,
  report,
  onClose,
}: {
  workflow: Workflow;
  report: Report;
  onClose: () => void;
}) {
  const { refresh } = useConsole();
  const [audience, setAudience] = useState(w.audience);
  const [notice, setNotice] = useState({ text: '', ok: false });
  const [testing, setTesting] = useState(false);
  const history = useSection('workflows', ['history', w.id], () =>
    api<{ versions: Version[] }>('/api/admin/workflows/history?workflow=' + encodeURIComponent(w.id)).then(
      (found) => found.versions,
      (): Version[] => [],
    ),
  );
  const fail = (e: Error) => setNotice({ text: e.message, ok: false });
  const offer = (value: string) =>
    api('/api/admin/workflows/audience', { method: 'PUT', json: { workflow: w.id, audience: value } }).then(() => {
      setAudience(value);
      return refresh();
    }, fail);
  const test = async () => {
    setTesting(true);
    try {
      const job = await api<{ name: string }>('/api/admin/workflows/test', {
        method: 'POST',
        json: { workflow: w.id },
      });
      setNotice({
        text: `"${job.name}" is first in the queue, free. It runs once the render server answers, and the result goes to your library.`,
        ok: true,
      });
    } catch (e) {
      fail(e as Error);
    }
    setTesting(false);
  };
  const versions = history.data;
  const everyKind = report.resolutions_off?.[w.kind] || [];
  return (
    <Drawer title={w.title} onClose={onClose}>
      {() =>
        !versions ? (
          <p className="muted">Loading…</p>
        ) : (
          <>
            <Section title="Offered to">
              <Segmented choices={AUDIENCE} current={audience} onPick={(v) => void offer(v)} />
              <p className="muted small">
                Admins only: you and the other admins see it on Create and the agent can use it for you; users
                don&apos;t, until you offer it to everyone.
              </p>
            </Section>
            {w.kind !== 'audio' && (
              <Section title="Resolutions">
                <ResolutionSwitches
                  id={w.id}
                  off={w.resolutions_off}
                  onError={(text) => setNotice({ text, ok: false })}
                />
                <p className="muted small">
                  {`Untick one to switch it off for this workflow (768p counts as 720p). ${
                    everyKind.length
                      ? `Off for every ${w.kind} workflow: ${everyKind.map((t) => t + 'p').join(', ')}. `
                      : ''
                  }A job asked at one that is off is made at the next one down (or up, when none is lower) and says so. Only workflows that take a resolution change.`}
                </p>
              </Section>
            )}
            <Section title="Try it">
              <p className="muted small">
                Runs it once with its own settings and a sample prompt, as you: free, first in the queue, and even under
                maintenance.
              </p>
              <button className="btn primary" disabled={!!w.error || testing} onClick={() => void test()}>
                Test run
              </button>
              <p className={'notice' + (notice.text ? (notice.ok ? ' ok' : ' error') : '')}>{notice.text}</p>
            </Section>
            {w.missing && (w.missing.files.length > 0 || w.missing.nodes.length > 0) && (
              <Section title="Missing on the render server">
                <p className="muted small">{`As its node list said ${report.nodes_saved ? ago(report.nodes_saved) : 'last time'}. A job would fail with "value not in list" or an unknown node.`}</p>
                {w.missing.files.length > 0 && (
                  <Table
                    head={['Model file', 'Node', 'Input']}
                    rows={w.missing.files.map((f) => [f.file, `${f.node} · ${f.type}`, f.input])}
                  />
                )}
                {w.missing.nodes.length > 0 && <p>{'Node types not installed: ' + w.missing.nodes.join(', ')}</p>}
              </Section>
            )}
            <Section title="About it">
              <Facts
                pairs={[
                  ['File', w.file],
                  ['Type', w.kind],
                  ['Presets file', w.presets ? 'Yes' : 'No'],
                  [
                    'Price',
                    w.example ? `${number(w.example)} credits ${w.kind === 'image' ? 'an image' : 'for 5 s'}` : 'Free',
                  ],
                  ['Jobs', number(w.jobs)],
                  ['Succeeded', succeeded(w)],
                  ['Average time', span(w.avg_seconds)],
                  ['Last used', w.last_used ? ago(w.last_used) : ''],
                ]}
              />
            </Section>
            <Section title={`Versions (${versions.length})`}>
              {versions.length ? (
                versions.map((v, i) => (
                  <div key={i} className={css('version')}>
                    <div className="row">
                      <Tag of={CHANGE[v.change] || ['done', v.change]} />
                      <span className="muted small">{stamp(v.seen)}</span>
                      {v.file && <span className="muted small">{v.file}</span>}
                    </div>
                    {v.changes.length ? (
                      <Lines changes={v.changes} />
                    ) : (
                      <p className="muted small">
                        {v.change === 'first'
                          ? 'As it was when the record began.'
                          : v.change === 'updated'
                            ? 'Only spacing or order changed.'
                            : ''}
                      </p>
                    )}
                  </div>
                ))
              ) : (
                <p className="muted">None kept yet.</p>
              )}
            </Section>
          </>
        )
      }
    </Drawer>
  );
}

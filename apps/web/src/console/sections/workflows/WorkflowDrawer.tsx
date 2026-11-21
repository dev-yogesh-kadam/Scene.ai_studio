// One workflow (one provider model): who it is offered to, its resolutions, a test run, and how it has done.

import { useState } from 'react';
import { api } from '../../../common/api';
import { Segmented } from '../../../common/components/Segmented';
import { Drawer } from '../shared/Drawer';
import { useConsole } from '../shared/context';
import { Facts, Section, ago, number, span } from '../shared/ui';
import { ResolutionSwitches } from './ResolutionSwitches';
import { AUDIENCE, succeeded, type Report, type Workflow } from './workflowData';

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
        text: `"${job.name}" is first in the queue, free. Its provider makes it, and the result goes to your library.`,
        ok: true,
      });
    } catch (e) {
      fail(e as Error);
    }
    setTesting(false);
  };
  const everyKind = report.resolutions_off?.[w.kind] || [];
  return (
    <Drawer title={w.title} onClose={onClose}>
      {() => (
        <>
          <Section title="Offered to">
            <Segmented choices={AUDIENCE} current={audience} onPick={(v) => void offer(v)} />
            <p className="muted small">
              Admins only: you and the other admins see it on Create and the agent can use it for you; users don&apos;t,
              until you offer it to everyone.
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
              Runs it once with its own settings and a sample prompt, as you: free in studio credits (the provider's own
              credits are still spent), first in the queue, and even under maintenance.
            </p>
            <button className="btn primary" disabled={testing} onClick={() => void test()}>
              Test run
            </button>
            <p className={'notice' + (notice.text ? (notice.ok ? ' ok' : ' error') : '')}>{notice.text}</p>
          </Section>
          <Section title="About it">
            <Facts
              pairs={[
                ['Model', w.model],
                ['Type', w.kind],
                ['What it does', w.description],
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
        </>
      )}
    </Drawer>
  );
}

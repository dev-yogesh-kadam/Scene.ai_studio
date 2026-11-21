// The console's Workflows section: every model the providers offer (each a workflow of its own), who each is offered
// to, its resolutions, how it has done, and a test run.

import { useState } from 'react';
import { api } from '../../../common/api';
import { Segmented } from '../../../common/components/Segmented';
import { useFilters, useSection } from '../shared/context';
import { Facts, Loaded, Table, ago, failed, number } from '../shared/ui';
import { ResolutionSwitches } from './ResolutionSwitches';
import { WorkflowDrawer } from './WorkflowDrawer';
import { PILL, Tag, needsAttention, succeeded, type Report } from './workflowData';
import { classesOf } from '../../../common/cx';
import css0 from '../../../common/components/Shared2.module.css';
import css1 from '../../../common/components/Shared3.module.css';
import css2 from '../shared/Console.module.css';
import css3 from '../../../studio/pages/create/CreatePage.module.css';
const css = classesOf(css0, css1, css2, css3);

const SHOW = [
  { id: '', label: 'All' },
  { id: 'attention', label: 'Need attention' },
  { id: 'admins', label: 'Admins only' },
  { id: 'off', label: 'Off' },
];

/** Whether new models start for admins only, and how many there are of each state. */
function Offering({ report }: { report: Report }) {
  const [hold, setHold] = useState(report.new_admins_only);
  const change = (on: boolean) => {
    setHold(on);
    api('/api/admin/workflows/settings', { method: 'PUT', json: { new_admins_only: on } }).catch((e: Error) => {
      failed(e);
      setHold(!on);
    });
  };
  return (
    <div className={css('card')}>
      <div className={css('card-head')}>
        <h2>Models offered</h2>
      </div>
      <p className="muted small">
        Each model a provider key unlocks is a workflow of its own. Add or remove keys in Servers &amp; APIs.
      </p>
      <Facts
        pairs={[
          ['Workflows', number(report.workflows.length)],
          ['Need attention (no price yet)', number(report.workflows.filter(needsAttention).length)],
          ['Offered to admins only', number(report.workflows.filter((w) => w.audience === 'admins').length)],
          ['Switched off', number(report.workflows.filter((w) => w.audience === 'off').length)],
        ]}
      />
      <label className="check">
        <input type="checkbox" checked={hold} onChange={(e) => change(e.target.checked)} />
        New models start for admins only, until you offer them to everyone
      </label>
    </div>
  );
}

export default function Workflows() {
  const [s, set] = useFilters<{ show: string }>('workflows');
  const [opened, setOpened] = useState<string | null>(null);
  const query = useSection('workflows', ['list'], () => api<Report>('/api/admin/workflows'));
  return (
    <Loaded query={query}>
      {(report) => {
        const shown = report.workflows.filter((w) =>
          s.show === 'attention' ? needsAttention(w) : s.show ? w.audience === s.show : true,
        );
        const open = report.workflows.find((w) => w.id === opened);
        return (
          <>
            <Offering report={report} />
            <div className={css('card')}>
              <div className={css('card-head')}>
                <h2>Resolutions for everyone</h2>
              </div>
              <p className="muted small">
                Untick a resolution to switch it off for every workflow of that type. A workflow can switch off more of
                its own (select it below). A job asked at one that is off is made at the next one allowed, and the reply
                says so.
              </p>
              <Table
                head={['Type', 'On']}
                rows={['video', 'image', 'upscaler'].map((kind) => [
                  kind,
                  <ResolutionSwitches key={kind} id={kind} off={report.resolutions_off?.[kind]} />,
                ])}
              />
            </div>
            <div className={css('card')}>
              <div className={css('card-head')}>
                <h2>Workflows</h2>
                <Segmented choices={SHOW} current={s.show} onPick={(show) => set({ show })} />
              </div>
              <Table
                head={['Workflow', 'Type', 'Offered to', 'Price', 'Jobs', 'Succeeded', 'Last used']}
                rows={shown.map((w) => [
                  <div key="t">
                    {w.title}
                    <div className="muted small">{w.model || w.id}</div>
                  </div>,
                  w.kind,
                  <Tag key="a" of={PILL[w.audience]} />,
                  w.example ? (
                    number(w.example) + ' cr'
                  ) : (
                    <span key="f" className={css('pill failed')}>
                      Free
                    </span>
                  ),
                  number(w.jobs),
                  succeeded(w),
                  w.last_used ? ago(w.last_used) : '',
                ])}
                onRow={(i) => setOpened(shown[i].id)}
                empty="None."
              />
              <p className="muted small" style={{ marginTop: 10 }}>
                Price: an image, or 5 seconds of video or sound. Select a workflow for a test run and who it is offered
                to.
              </p>
            </div>
            {open && <WorkflowDrawer key={open.id} workflow={open} report={report} onClose={() => setOpened(null)} />}
          </>
        );
      }}
    </Loaded>
  );
}

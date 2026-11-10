// The console's Workflows section: what the render PC changed lately, who each workflow is offered to, what it needs
// that the render server lacks, its versions and what changed in each, and a test run. See backend/scene/versions.py.

import { useState } from 'react';
import { api } from '../../../common/api';
import { Segmented } from '../../../common/components/Segmented';
import { useConsole, useFilters, useSection } from '../shared/context';
import { Facts, Loaded, Table, ago, failed, number, secondsSince, stamp } from '../shared/ui';
import { ResolutionSwitches } from './ResolutionSwitches';
import { WorkflowDrawer } from './WorkflowDrawer';
import { CHANGE, PILL, Tag, lacking, needsAttention, succeeded, type Report, type Workflow } from './workflowData';
import { classesOf } from '../../../common/cx';
import css0 from '../../../common/components/Shared2.module.css';
import css1 from '../../../common/components/Shared3.module.css';
import css2 from '../shared/Console.module.css';
import css3 from './Workflows.module.css';
import css4 from '../../../studio/pages/create/CreatePage.module.css';
const css = classesOf(css0, css1, css2, css3, css4);

const SHOW = [
  { id: '', label: 'All' },
  { id: 'attention', label: 'Need attention' },
  { id: 'admins', label: 'Admins only' },
  { id: 'off', label: 'Off' },
];

function Health({ w }: { w: Workflow }) {
  if (w.error)
    return (
      <div>
        <span className={css('pill failed')}>Can&apos;t be read</span>
        <div className="error small">{w.error}</div>
      </div>
    );
  const lack = lacking(w);
  return lack ? <span className={css('pill failed')}>{lack}</span> : <span className={css('pill done')}>Ready</span>;
}

function Changes({ report, open }: { report: Report; open: (id: string) => void }) {
  const [hold, setHold] = useState(report.new_admins_only);
  const known = new Map(report.workflows.map((w) => [w.id, w]));
  const name = (id: string) => {
    const w = known.get(id);
    return w ? (
      <button className={css('link-button')} onClick={() => open(id)}>
        {w.title}
      </button>
    ) : (
      <span className="muted">{id}</span>
    );
  };
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
        <h2>Changes from the render PC</h2>
      </div>
      {report.drops.length ? (
        report.drops.map((d) => (
          <div key={d.seen} className={css('drop')}>
            <div className="row">
              <b>{stamp(d.seen)}</b>
              <span className="muted small">
                {[
                  d.new.length && `${d.new.length} new`,
                  d.updated.length && `${d.updated.length} updated`,
                  d.removed.length && `${d.removed.length} removed`,
                ]
                  .filter(Boolean)
                  .join(' · ')}
              </span>
            </div>
            <div className={css('drop-names')}>
              {(['new', 'updated', 'removed'] as const).flatMap((kind) =>
                d[kind].map((id) => (
                  <span key={kind + id} className={css('drop-name')}>
                    <Tag of={CHANGE[kind]} />
                    {name(id)}
                  </span>
                )),
              )}
            </div>
          </div>
        ))
      ) : (
        <p className="muted">
          {report.since ? `No changes since the record began, ${stamp(report.since)}.` : 'No record yet.'}
        </p>
      )}
      <label className="check">
        <input type="checkbox" checked={hold} onChange={(e) => change(e.target.checked)} />
        New workflows start for admins only, until you offer them to everyone
      </label>
    </div>
  );
}

function Nodes({ report }: { report: Report }) {
  const { refresh } = useConsole();
  const [asking, setAsking] = useState(false);
  const fetchList = async () => {
    setAsking(true);
    try {
      await api('/api/admin/workflows/nodes', { method: 'POST' });
      await refresh();
    } catch (e) {
      failed(e);
    }
    setAsking(false);
  };
  const saved = report.nodes_saved;
  return (
    <div className={css('card')}>
      <div className={css('card-head')}>
        <h2>Compared with the render server</h2>
        <button className="btn small" disabled={asking} onClick={() => void fetchList()}>
          {asking ? 'Asking…' : 'Refresh now'}
        </button>
      </div>
      <p className="muted small">
        {saved
          ? `What each workflow needs is checked against the render server's node list from ${stamp(saved)} (${ago(saved)}). It is fetched again by itself when the server answers and the list is over 6 hours old.`
          : 'There is no node list from the render server yet: it is fetched once the server answers.'}
      </p>
      {!!saved && secondsSince(saved) > 3 * 86400 && (
        <p className="notice error">
          This list is old. Models and nodes installed on the render PC since then show as missing here until it is
          fetched again: start the render server and press Refresh now.
        </p>
      )}
      <Facts
        pairs={[
          ['Workflows', number(report.workflows.length)],
          ['Need attention', number(report.workflows.filter(needsAttention).length)],
          ['Offered to admins only', number(report.workflows.filter((w) => w.audience === 'admins').length)],
          ['Switched off', number(report.workflows.filter((w) => w.audience === 'off').length)],
        ]}
      />
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
            <div className={css('grid-2')}>
              <Changes report={report} open={setOpened} />
              <Nodes report={report} />
            </div>
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
                head={['Workflow', 'Type', 'Offered to', 'Health', 'Price', 'Jobs', 'Succeeded', 'Changed']}
                rows={shown.map((w) => [
                  <div key="t">
                    {w.title}
                    <div className="muted small">{w.file}</div>
                  </div>,
                  w.kind,
                  <Tag key="a" of={PILL[w.audience]} />,
                  <Health key="h" w={w} />,
                  w.example ? (
                    number(w.example) + ' cr'
                  ) : (
                    <span key="f" className={css('pill failed')}>
                      Free
                    </span>
                  ),
                  number(w.jobs),
                  succeeded(w),
                  w.changed ? ago(w.changed) : '',
                ])}
                onRow={(i) => setOpened(shown[i].id)}
                empty="None."
              />
              <p className="muted small" style={{ marginTop: 10 }}>
                {`Workflow files are read from ${report.folder}. Price: an image, or 5 seconds of video or sound. Select a workflow for its versions, a test run and who it is offered to.`}
              </p>
            </div>
            {open && <WorkflowDrawer key={open.id} workflow={open} report={report} onClose={() => setOpened(null)} />}
          </>
        );
      }}
    </Loaded>
  );
}

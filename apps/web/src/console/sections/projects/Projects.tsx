// The console's Projects section: every user's projects, their modules and their NeuralCore (the entries the agent and
// the canvas use by name), and their latest items.

import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { api } from '../../../common/api';
import { Still } from '../../../common/components/Still';
import { Drawer } from '../shared/Drawer';
import { useFilters, useSection } from '../shared/context';
import { Facts, Loaded, Person, SearchBox, Section, Table, Thumb, ago, bytes, number, stamp } from '../shared/ui';
import { classesOf } from '../../../common/cx';
import css0 from '../../../common/components/Shared2.module.css';
import css1 from '../../../common/components/Shared3.module.css';
import css2 from './Projects.module.css';
import css3 from '../shared/Console.module.css';
import css4 from '../../../studio/pages/create/CreatePage.module.css';
const css = classesOf(css0, css1, css2, css3, css4);

const TYPE: Record<string, string> = {
  character: 'Character',
  location: 'Location',
  prop: 'Prop',
  voice: 'Voice',
  style: 'Style',
  other: 'Other',
};

type Row = {
  id: number;
  name: string;
  ref: string;
  user_name: string;
  user_email: string;
  modules: number;
  kit: number;
  items: number;
  bytes: number;
  jobs: number;
  last_job: number | null;
};
type Detail = {
  project: { name: string; user_name: string; user_email: string; created: number };
  modules: { name: string; items: number; jobs: number; created: number }[];
  kit: {
    id: number;
    kind: string;
    name: string;
    named?: boolean | number;
    type: string;
    always?: boolean | number;
    origin?: string;
    about?: string;
    use_note?: string;
  }[];
  items: { id: number; kind: string; name: string }[];
};

function Body({ d }: { d: Detail }) {
  const p = d.project;
  const always = d.kit.filter((k) => k.always);
  return (
    <>
      <div className={css('drawer-title')}>
        <div>
          <b>{p.name}</b>
          <div className="muted">{`${p.user_name} · ${p.user_email}`}</div>
        </div>
      </div>
      <Section title="About it">
        <Facts
          pairs={[
            ['Made', stamp(p.created)],
            ['Modules', number(d.modules.length)],
            [
              'NeuralCore entries',
              `${number(d.kit.length)}${always.length ? ` · ${always.length} always attached` : ''}`,
            ],
          ]}
        />
      </Section>
      {d.modules.length > 0 && (
        <Section title="Modules">
          <Table
            head={['Module', 'Items', 'Jobs', 'Made']}
            rows={d.modules.map((m) => [m.name, number(m.items), number(m.jobs), ago(m.created)])}
          />
        </Section>
      )}
      <Section title={`NeuralCore (${d.kit.length})`}>
        {d.kit.length ? (
          <div className={css('kit-list')}>
            {d.kit.map((k) => (
              <div key={k.id} className={css('kit-entry')}>
                {k.kind === 'image' ? (
                  <Still url={`/api/admin/assets/${k.id}/file`} kind="image" name={k.name} />
                ) : (
                  <div className={css('kit-kind')}>{k.kind}</div>
                )}
                <div>
                  <b>{k.named ? k.name : <span className="muted">Not named yet</span>}</b>
                  <div className="muted small">
                    {[
                      TYPE[k.type] || k.type,
                      k.always && 'always attached',
                      k.origin === 'upload' && 'dropped into a job',
                    ]
                      .filter(Boolean)
                      .join(' · ')}
                  </div>
                  {k.about && <div className="small">{k.about}</div>}
                  {k.use_note && <div className="muted small">{'Use: ' + k.use_note}</div>}
                </div>
              </div>
            ))}
          </div>
        ) : (
          <p className="muted">NeuralCore is empty.</p>
        )}
      </Section>
      <Section title="Latest items">
        {d.items.length ? (
          <div className={css('thumbs')}>
            {d.items.map((i) => (
              <div key={i.id} className={css('thumb-box')} title={i.name}>
                <Thumb item={i} />
              </div>
            ))}
          </div>
        ) : (
          <p className="muted">Nothing made in it yet.</p>
        )}
      </Section>
    </>
  );
}

function ProjectDrawer({ id, onClose }: { id: number; onClose: () => void }) {
  const query = useQuery({
    queryKey: ['console', 'project', id],
    queryFn: () => api<Detail>('/api/admin/projects/' + id),
  });
  return (
    <Drawer title="Project" onClose={onClose}>
      {() =>
        query.error ? (
          <p className="error">{query.error.message}</p>
        ) : query.data ? (
          <Body d={query.data} />
        ) : (
          <p className="muted">Loading…</p>
        )
      }
    </Drawer>
  );
}

export default function Projects() {
  const [s, set] = useFilters<{ q: string }>('projects');
  const [open, setOpen] = useState<number | null>(null);
  const query = useSection('projects', [s.q], () =>
    api<{ projects: Row[] }>('/api/admin/projects?q=' + encodeURIComponent(s.q)).then((a) => a.projects),
  );
  return (
    <Loaded query={query}>
      {(found) => (
        <div className={css('card')}>
          <div className={css('card-head')}>
            <h2>Projects</h2>
            <SearchBox placeholder="Project, person, email or id" value={s.q} onChange={(q) => set({ q })} />
          </div>
          <Table
            head={['Project', 'Owner', 'Modules', 'NeuralCore', 'Items', 'Space', 'Jobs', 'Last job']}
            rows={found.map((p) => [
              <Person key="p" name={p.name} email={p.ref} />,
              <Person key="o" name={p.user_name} email={p.user_email} />,
              number(p.modules),
              number(p.kit),
              number(p.items),
              bytes(p.bytes),
              number(p.jobs),
              p.last_job ? ago(p.last_job) : 'never',
            ])}
            onRow={(i) => setOpen(found[i].id)}
            empty={s.q ? 'No project matches.' : 'No projects yet.'}
          />
          <p className="muted small" style={{ marginTop: 10 }}>
            Counts take in each project&apos;s modules, which share its NeuralCore. Select a project for its NeuralCore
            and latest items.
          </p>
          {open !== null && <ProjectDrawer id={open} onClose={() => setOpen(null)} />}
        </div>
      )}
    </Loaded>
  );
}

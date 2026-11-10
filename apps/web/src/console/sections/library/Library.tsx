// The console's Library section: every user's work, by kind, person and project; a row opens the item.

import { api } from '../../../common/api';
import { Segmented } from '../../../common/components/Segmented';
import { openViewer } from '../../../common/media/Viewer';
import type { Item } from '../../../common/media/item';
import { useConsole, useFilters, useSection } from '../shared/context';
import { Loaded, Pager, Person, SearchBox, Table, bytes, failed, number, stamp, sure } from '../shared/ui';
import { classesOf } from '../../../common/cx';
import css0 from '../../../common/components/Shared2.module.css';
import css1 from '../../../common/components/Shared3.module.css';
import css2 from '../shared/Console.module.css';
const css = classesOf(css0, css1, css2);

type Row = Item & { user_name: string; user_email: string; settings: NonNullable<Item['settings']> };
type Data = {
  items: Row[];
  total: number;
  owners: { id: number; name: string; items: number }[];
  projects: { id: number; name: string; user_id: number; user_name: string }[];
};
type Filter = { kind: string; q: string; owner: string; project: string; offset: number };
const KIND: Record<string, string> = { video: 'Video', image: 'Image', audio: 'Audio' };

export default function Library() {
  const { refresh } = useConsole();
  const [s, set] = useFilters<Filter>('library');
  const query = useSection('library', [s.kind, s.q, s.owner, s.project, s.offset], () =>
    api<Data>(
      '/api/admin/library?' +
        new URLSearchParams({ kind: s.kind, q: s.q, owner: s.owner, project: s.project, offset: String(s.offset) }),
    ),
  );
  const open = (item: Row) =>
    openViewer(item, {
      base: '/api/admin/library',
      owner: true,
      actions: [
        {
          label: 'Delete from their library',
          danger: true,
          run: (close) => {
            void sure(`Delete "${item.name}" from ${item.user_name}'s library? This can't be undone.`).then((yes) => {
              if (!yes) return;
              void api('/api/admin/library/' + item.id, { method: 'DELETE' }).then(() => {
                close();
                void refresh();
              }, failed);
            });
          },
        },
      ],
    });
  return (
    <Loaded query={query}>
      {(data) => {
        // Projects belong to one user, so the project list follows the chosen user.
        const projects = data.projects.filter((p) => !s.owner || String(p.user_id) === s.owner);
        return (
          <>
            <div className={css('toolbar')}>
              <Segmented
                choices={[
                  { id: '', label: 'All' },
                  { id: 'video', label: 'Videos' },
                  { id: 'image', label: 'Images' },
                  { id: 'audio', label: 'Audio' },
                ]}
                current={s.kind}
                onPick={(kind) => set({ kind, offset: 0 })}
              />
              <select
                className={css('filter')}
                aria-label="User"
                value={s.owner}
                onChange={(e) => set({ owner: e.target.value, project: '', offset: 0 })}
              >
                <option value="">All users</option>
                {data.owners.map((u) => (
                  <option key={u.id} value={String(u.id)}>{`${u.name} (${u.items})`}</option>
                ))}
              </select>
              <select
                className={css('filter')}
                aria-label="Project"
                value={s.project}
                onChange={(e) => set({ project: e.target.value, offset: 0 })}
              >
                <option value="">All projects</option>
                <option value="none">Not in a project</option>
                {projects.map((p) => (
                  <option key={p.id} value={String(p.id)}>
                    {s.owner ? p.name : `${p.name} · ${p.user_name}`}
                  </option>
                ))}
              </select>
              <SearchBox
                placeholder="Search name, prompt or user"
                value={s.q}
                onChange={(q) => set({ q, offset: 0 })}
              />
              <span
                className={css('muted small push')}
              >{`${number(data.total)} item${data.total === 1 ? '' : 's'}`}</span>
            </div>
            <div className={css('card')}>
              <Table
                head={['Name', 'Type', 'User', 'Project', 'Workflow', 'Settings', 'Size', 'Made']}
                rows={data.items.map((item) => [
                  <b key="n">{item.name}</b>,
                  KIND[item.kind] || item.kind,
                  <Person key="p" name={item.user_name} email={item.user_email} />,
                  item.project_name || (
                    <span key="m" className="muted">
                      None
                    </span>
                  ),
                  item.settings.workflow_title || item.workflow.split('/')[1].replace(/_/g, ' '),
                  <span key="s" className="small">
                    {item.summary}
                  </span>,
                  bytes(item.size),
                  stamp(item.created),
                ])}
                onRow={(i) => open(data.items[i])}
                empty="No items match."
              />
            </div>
            <p className="muted small" style={{ marginTop: 10 }}>
              Select a row to watch the item and see its prompt and details.
            </p>
            <Pager total={data.total} offset={s.offset} onOffset={(offset) => set({ offset })} />
          </>
        );
      }}
    </Loaded>
  );
}

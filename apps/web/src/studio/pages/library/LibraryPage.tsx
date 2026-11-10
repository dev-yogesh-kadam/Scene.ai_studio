// The Library page: everything the user has made, with search. Three views: All (every item), Projects (a folder for
// each project, opened to its items) and Not in a project (items that belong to none).

import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useState } from 'react';
import type { ProjectRow } from '@scene/shared/types/api';
import { api } from '../../../common/api';
import { ask, askText, tell } from '../../../common/components/Dialog';
import { Segmented } from '../../../common/components/Segmented';
import { Still } from '../../../common/components/Still';
import { EmptyState, ErrorBanner, Skeleton } from '../../../common/components/States';
import { ago, initials } from '../../../common/format';
import { MediaCard } from '../../features/media/MediaCard';
import { LoadMore, useLibraryPages } from '../../features/media/useLibraryPages';
import { classesOf } from '../../../common/cx';
import css0 from '../../../common/components/Shared2.module.css';
import css1 from '../../../common/components/Shared3.module.css';
import css2 from '../../../common/components/Shared4.module.css';
import css3 from '../Shared.module.css';
import css4 from '../projects/ProjectsPage.module.css';
const css = classesOf(css0, css1, css2, css3, css4);

type Project = ProjectRow & {
  items: number;
  updated?: number;
  cover_id?: number | null;
  cover_kind?: string;
  parent_name?: string | null;
};

const VIEWS = [
  { id: 'all', label: 'All' },
  { id: 'projects', label: 'Projects' },
  { id: 'none', label: 'Not in a project' },
] as const;
type View = (typeof VIEWS)[number]['id'];
const KINDS = [
  { id: '', label: 'All' },
  { id: 'video', label: 'Videos' },
  { id: 'image', label: 'Images' },
  { id: 'audio', label: 'Audio' },
];

export const useProjects = () =>
  useQuery({
    queryKey: ['projects'],
    queryFn: () => api<{ projects: Project[] }>('/api/projects').then((a) => a.projects),
  });

export default function LibraryPage() {
  const client = useQueryClient();
  const [tab, setTab] = useState<View>('all');
  const [openId, setOpenId] = useState<number | null>(null); // the project opened from the Projects view
  const [kind, setKind] = useState('');
  const [typed, setTyped] = useState('');
  const [q, setQ] = useState('');
  const projectsQuery = useProjects();
  const projects = projectsQuery.data ?? [];
  const open = openId != null ? (projects.find((p) => p.id === openId) ?? null) : null; // renamed, counted again, or deleted

  useEffect(() => {
    const timer = setTimeout(() => setQ(typed), 250);
    return () => clearTimeout(timer);
  }, [typed]);

  const project = tab === 'none' ? ('none' as const) : tab === 'projects' && open ? open.id : undefined;
  const folders = tab === 'projects' && !open;
  // an opened project shows its modules' items too
  const filter = { kind, q, project, modules: tab === 'projects' && !!open };
  const items = useLibraryPages(['library', 'page', filter], filter, !folders && !projectsQuery.isPending);

  const changed = () => {
    void client.invalidateQueries({ queryKey: ['projects'] });
    void client.invalidateQueries({ queryKey: ['library'] });
  };
  const run = (action: () => Promise<unknown>) => action().then(changed, (e: Error) => tell(e.message));
  const pick = (id: View) => {
    setTab(id);
    setOpenId(null);
  };

  return (
    <>
      <div className={css('page-head')}>
        <h1>Library</h1>
        <input
          type="text"
          placeholder="Search Library…"
          style={{ maxWidth: 260 }}
          value={typed}
          onChange={(e) => setTyped(e.target.value)}
        />
      </div>
      <p className="muted" style={{ margin: '0 0 14px' }}>
        Everything you have made, in one place. Reuse what is here instead of rebuilding it.
      </p>
      <div className="row" style={{ marginBottom: 14, gap: 12, flexWrap: 'wrap' }}>
        <div>
          <Segmented choices={VIEWS} current={tab} onPick={pick} />
        </div>
        {/* What kind of item is shown applies to items, not to the folders of the Projects view. */}
        <div>{!folders && <Segmented choices={KINDS} current={kind} onPick={setKind} />}</div>
      </div>
      <div className="row" style={{ marginBottom: 16 }}>
        {tab === 'projects' && open ? (
          <>
            <button className="btn small quiet" onClick={() => setOpenId(null)}>
              ← Projects
            </button>
            <b>{open.name}</b>
            <span className={css('slate-text')}>{open.items === 1 ? '1 item' : `${open.items} items`}</span>
            <span style={{ flex: 1 }} />
            <button
              className="btn small"
              onClick={() =>
                void askText({ title: 'Project name', value: open.name, confirm: 'Rename' }).then(
                  (name) => name && void run(() => api('/api/projects/' + open.id, { method: 'PUT', json: { name } })),
                )
              }
            >
              Rename
            </button>
            <button
              className="btn small quiet danger"
              onClick={() =>
                void ask({
                  title: `Delete "${open.name}"?`,
                  danger: true,
                  confirm: 'Delete project',
                  message: `Its ${open.items} items, its modules and its NeuralCore are deleted with it, for good. This can't be undone.`,
                }).then(
                  (sure) =>
                    sure &&
                    void run(async () => {
                      await api('/api/projects/' + open.id, { method: 'DELETE' });
                      setOpenId(null);
                    }),
                )
              }
            >
              Delete project
            </button>
          </>
        ) : tab === 'projects' ? (
          <button
            className="btn small"
            onClick={() =>
              void askText({ title: 'Name of the new project', confirm: 'Create' }).then(
                (name) => name && void run(() => api('/api/projects', { method: 'POST', json: { name } })),
              )
            }
          >
            New project
          </button>
        ) : null}
      </div>
      {folders ? (
        <Folders projects={projects} q={q} onOpen={(p) => setOpenId(p.id)} />
      ) : (
        <div className={css('media-grid')}>
          {items.isError ? (
            <ErrorBanner error={items.error} onRetry={() => void items.refetch()} wide />
          ) : !items.items ? (
            <Skeleton count={12} />
          ) : items.items.length ? (
            <>
              {items.items.map((item) => (
                <MediaCard key={item.id} item={item} manage projects={projects} onChanged={changed} />
              ))}
              <LoadMore pages={items} />
            </>
          ) : (
            <EmptyState wide>
              {q || project || kind ? 'Nothing matches.' : 'Nothing here yet. Make something on the Create page.'}
            </EmptyState>
          )}
        </div>
      )}
    </>
  );
}

/** The folders of the Projects view: the newest item of a project is its cover. */
function Folders({ projects, q, onOpen }: { projects: Project[]; q: string; onOpen: (p: Project) => void }) {
  const words = q.trim().toLowerCase();
  const shown = projects.filter((p) => !p.parent_id && (!words || p.name.toLowerCase().includes(words)));
  return (
    <div className={css('project-grid')}>
      {shown.length ? (
        shown.map((p) => (
          <button key={p.id} className={css('project')} onClick={() => onOpen(p)}>
            <div className={css('project-cover')}>
              {p.cover_id ? (
                <Still url={`/api/library/${p.cover_id}/file`} kind={p.cover_kind || 'image'} name={p.name} />
              ) : (
                initials(p.name)
              )}
            </div>
            <b>{p.name}</b>
            <span className={css('slate-text')}>
              {[p.items === 1 ? '1 item' : `${p.items} items`, ago(p.updated || p.created)].join(' · ')}
            </span>
          </button>
        ))
      ) : (
        <EmptyState wide>{words ? 'No project matches.' : 'No projects yet. Use New project.'}</EmptyState>
      )}
    </div>
  );
}

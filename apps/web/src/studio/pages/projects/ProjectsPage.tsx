// The All projects page: every project as a card with its newest item as the thumbnail. Opening one goes to its page.

import { useQueryClient } from '@tanstack/react-query';
import { useState, type KeyboardEvent, type MouseEvent } from 'react';
import { useNavigate } from 'react-router';
import { api } from '../../../common/api';
import { ask, tell } from '../../../common/components/Dialog';
import { Icon } from '../../../common/components/Icon/Icon';
import { Spill } from '../../../common/components/Spill';
import { Still } from '../../../common/components/Still';
import { ago, initials } from '../../../common/format';
import { projectDialog } from '../../features/projects/projectDialog';
import { placePath } from '../../place';
import { useProjects } from '../library/LibraryPage';
import s from './projects.module.css';
import { classesOf } from '../../../common/cx';
import css0 from '../../../common/components/Shared2.module.css';
import css1 from '../../../common/components/Shared4.module.css';
import css2 from './ProjectsPage.module.css';
import css3 from './projects.module.css';
import { userPrefs } from '../../userPrefs';
import { EmptyState, ErrorBanner, Skeleton } from '../../../common/components/States';
const css = classesOf(css0, css1, css2, css3);

type Project = NonNullable<ReturnType<typeof useProjects>['data']>[number] & {
  owner_name?: string | null;
  role: string;
  members?: number;
  modules?: number;
};

/** The newest item is the thumbnail. A project with nothing in it yet shows its initials. */
export function Cover({ p }: { p: { cover_id?: number | null; cover_kind?: string; name: string } }) {
  return p.cover_id ? (
    <Still url={`/api/library/${p.cover_id}/file`} kind={p.cover_kind || 'image'} name={p.name} />
  ) : (
    <>{initials(p.name)}</>
  );
}

export default function ProjectsPage() {
  const navigate = useNavigate();
  const client = useQueryClient();
  const query = useProjects();
  const [typed, setTyped] = useState('');
  const words = typed.trim().toLowerCase();
  const projects = ((query.data ?? []) as Project[])
    .filter((p) => !p.parent_id)
    .sort((a, b) => (b.updated || b.created) - (a.updated || a.created));
  const lit = projects.find((p) => p.cover_id && p.cover_kind !== 'audio'); // the cover of the one worked on last
  const reload = () => void client.invalidateQueries({ queryKey: ['projects'] });

  // A project opens on its page (its kit and its modules); "Open all work" opens the canvas of everything.
  const open = (p: Project | null) => {
    if (p) return void navigate(placePath('/project', p));
    userPrefs.setStudio({ project: null });
    void navigate('/canvas');
  };
  const create = async () => {
    const made = await projectDialog();
    if (made) open(made as Project); // a new project opens straight away
  };
  const rename = async (p: Project) => {
    if (await projectDialog({ project: p })) reload();
  };
  const remove = async (p: Project) => {
    const sure = await ask({
      title: `Delete "${p.name}"?`,
      danger: true,
      confirm: 'Delete project',
      message: `Its ${p.items} items, its modules and its NeuralCore are deleted with it, for good. This can't be undone.`,
    });
    if (sure) await api('/api/projects/' + p.id, { method: 'DELETE' }).then(reload, (e: Error) => tell(e.message));
  };
  const act = (fn: () => void) => (e: MouseEvent) => {
    e.stopPropagation(); // a button on a card must not also open the card
    fn();
  };

  let body;
  if (query.isError) body = <ErrorBanner error={query.error} onRetry={() => void query.refetch()} />;
  else if (!query.data)
    body = (
      <div className={s['pcard-grid']}>
        <Skeleton count={6} />
      </div>
    );
  else if (!projects.length) {
    body = (
      <div className={css('empty first')}>
        <h2>Create your first project</h2>
        <p>A project keeps the shots and the canvas of one piece of work together.</p>
        <button className="btn primary" onClick={() => void create()}>
          Create your first project
        </button>
      </div>
    );
  } else {
    const shown = projects.filter((p) => p.name.toLowerCase().includes(words));
    body = shown.length ? (
      <div className={s['pcard-grid']}>
        {shown.map((p) => (
          <div key={p.id} className={s.pcard} onClick={() => open(p)}>
            <div
              className={s['pcard-cover']}
              role="button"
              tabIndex={0}
              aria-label={'Open ' + p.name}
              onKeyDown={(e: KeyboardEvent) => (e.key === 'Enter' || e.key === ' ') && (e.preventDefault(), open(p))}
            >
              <Cover p={p} />
              {p.owner_name ? (
                <span
                  className={css(s['proj-badge'] + ' shared')}
                  title={`${p.owner_name}'s project, shared with you as ${p.role}`}
                  aria-hidden="true"
                >
                  <Icon name="people" />
                  Shared
                </span>
              ) : p.members ? (
                <span
                  className={css(s['proj-badge'] + ' shared')}
                  title={`Shared with ${p.members} ${p.members === 1 ? 'person' : 'people'}`}
                  aria-hidden="true"
                >
                  <Icon name="people" />
                  {String(p.members + 1)}
                </span>
              ) : null}
            </div>
            <div className={s['pcard-info']}>
              <b title={p.name}>{p.name}</b>
              {p.owner_name && (
                <span className="muted small">{`${p.owner_name}'s · ${p.role[0].toUpperCase() + p.role.slice(1)}`}</span>
              )}
              <span>
                {[p.modules ? `${p.modules + 1} modules` : '', p.items === 1 ? '1 item' : `${p.items} items`]
                  .filter(Boolean)
                  .join(' · ')}
              </span>
              <span className="muted small">{ago(p.updated || p.created)}</span>
            </div>
            {/* Rename for its owner or a manager; Delete for its owner only (the server says the same: sharing.py). */}
            {(p.role === 'owner' || p.role === 'manager') && (
              <div className={s['pcard-actions']}>
                <button
                  className="icon-btn"
                  title="Rename"
                  aria-label={'Rename ' + p.name}
                  onClick={act(() => void rename(p))}
                >
                  <Icon name="pencil" />
                </button>
                {p.role === 'owner' && (
                  <button
                    className="icon-btn"
                    title="Delete"
                    aria-label={'Delete ' + p.name}
                    onClick={act(() => void remove(p))}
                  >
                    <Icon name="trash" />
                  </button>
                )}
              </div>
            )}
          </div>
        ))}
      </div>
    ) : (
      <EmptyState>{`No project matches "${words}".`}</EmptyState>
    );
  }

  return (
    <>
      <Spill id={lit?.cover_id} kind={lit?.cover_kind} />
      <div className={css('page-head')}>
        <h1>All projects</h1>
        <div className={'row' + (projects.length ? '' : ' hidden')}>
          <input
            type="text"
            style={{ width: 240 }}
            placeholder="Search projects"
            aria-label="Search projects"
            value={typed}
            onChange={(e) => setTyped(e.target.value)}
          />
          <button className="btn" title="Everything you have made, in or out of a project" onClick={() => open(null)}>
            Open all work
          </button>
          <button className="btn primary" onClick={() => void create()}>
            New project
          </button>
        </div>
      </div>
      <div>{body}</div>
    </>
  );
}

// A project's page: on the left its cover, its analytics, its details and what can be done with it; on the right its
// modules. A module is a canvas of its own, with its own agent tabs, inside the project; the project's own canvas is
// the first one, "Main". The page is /project/<project's id>; opening a module goes to its canvas.

import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useState, type KeyboardEvent, type MouseEvent } from 'react';
import { Link, useNavigate } from 'react-router';
import { api } from '../../../common/api';
import { ask, tell } from '../../../common/components/Dialog';
import { Icon } from '../../../common/components/Icon/Icon';
import { Spill } from '../../../common/components/Spill';
import { Still } from '../../../common/components/Still';
import { ago, initials, tabTitle } from '../../../common/format';
import { projectDialog } from '../../features/projects/projectDialog';
import { shareDialog } from '../../features/share/shareDialog';
import { useCrumbs } from '../../layout/crumbs';
import { placePath, usePlaceId } from '../../place';
import { useUser } from '../../session';
import s from '../projects/projects.module.css';
import { classesOf } from '../../../common/cx';
import css0 from '../../../common/components/Shared.module.css';
import css1 from '../../../common/components/Shared2.module.css';
import css2 from '../../../common/components/Shared3.module.css';
import css3 from '../../../common/components/Shared4.module.css';
import css4 from '../Shared.module.css';
import css5 from './ProjectPage.module.css';
import css6 from '../projects/ProjectsPage.module.css';
import css7 from '../projects/projects.module.css';
import { userPrefs } from '../../userPrefs';
import { EmptyState, ErrorBanner, Skeleton } from '../../../common/components/States';
const css = classesOf(css0, css1, css2, css3, css4, css5, css6, css7);

// What the user's role in the project lets them do (the server checks it too: sharing.py).
const RANK: Record<string, number> = { viewer: 1, creator: 2, manager: 3, owner: 4 };
export const may = (role: string | null | undefined, need: string) => RANK[role || 'owner'] >= RANK[need];

// A module with nothing in it yet gets a colour of its own, from its number, instead of an empty frame.
const TINTS = [
  ['#ef6b8a', '#d12f7c'],
  ['#6b8bef', '#3f4fd1'],
  ['#3fbf9a', '#14876a'],
  ['#f0a25a', '#d0612b'],
  ['#a77bef', '#6a3fd1'],
  ['#4fb8e8', '#1f78b8'],
];

type Member = { user_id: number; name: string; email: string; role: string };
type Module = {
  id: number;
  ref: string;
  name: string;
  main?: boolean;
  items: number;
  created: number;
  updated?: number;
  cover_id?: number | null;
  cover_kind?: string;
};
type Detail = {
  project: Module & { role: string; members: Member[]; parent_ref?: string | null };
  modules: Module[];
};

export default function ProjectPage() {
  const id = usePlaceId() || Number(new URLSearchParams(location.search).get('id')) || 0;
  const navigate = useNavigate();
  const client = useQueryClient();
  const user = useUser();
  const [typed, setTyped] = useState('');
  const [deleting, setDeleting] = useState(false); // while it is being deleted it is not asked for again
  const detail = useQuery({
    queryKey: ['library', 'project', id],
    queryFn: () => api<Detail>('/api/projects/' + id),
    enabled: !deleting,
  });
  const data = detail.data;
  const reload = () => void client.invalidateQueries({ queryKey: ['library', 'project', id] });

  useCrumbs(data ? [{ label: 'Projects', href: '/projects' }, { label: data.project.name }] : null);
  useEffect(() => {
    if (!data) return;
    tabTitle(data.project.name);
    // a module's address, or an old one, shows the project's id
    const path = placePath('/project', data.project);
    if (path !== location.pathname) history.replaceState(history.state, '', path + location.search);
  }, [data]);

  if (detail.isError) {
    return (
      <div className={css('empty')}>
        <ErrorBanner error={detail.error} onRetry={() => void detail.refetch()} />
        <Link className="btn" to="/projects">
          All projects
        </Link>
      </div>
    );
  }
  if (!data)
    return (
      <>
        <Spill />
        <div className={css('media-grid')}>
          <Skeleton count={6} />
        </div>
      </>
    );
  const p = data.project;
  const modules = data.modules.length - 1; // the first is the project's own canvas
  const words = typed.trim().toLowerCase();
  const shown = data.modules
    .map((m, i) => [m, i] as const)
    .filter(([m]) => !words || m.name.toLowerCase().includes(words));

  // A module opens on its canvas; the project's own canvas is "Main".
  const open = (module: Module) => {
    userPrefs.setStudio({ project: module.id });
    void navigate(placePath('/canvas', module, p.ref));
  };
  const addModule = async () => {
    const made = await projectDialog({ parent: p, count: data.modules.length });
    if (made) open(made as Module);
  };
  const share = async () => {
    if (await shareDialog({ projectId: p.id, projectName: p.name, me: user.id })) reload();
  };
  const act = (fn: () => void) => (e: MouseEvent) => {
    e.stopPropagation();
    fn();
  };
  const fact = (label: string, value: string) => (
    <div className={s['proj-fact']}>
      <span>{label}</span>
      <b>{value}</b>
    </div>
  );

  return (
    <>
      <Spill id={p.cover_id} kind={p.cover_kind} />
      <div className={s['proj-page']}>
        <aside className={s['proj-side']}>
          <div className={s['proj-cover']}>
            {p.cover_id ? (
              <Still url={`/api/library/${p.cover_id}/file`} kind={p.cover_kind || 'image'} name={p.name} />
            ) : (
              <span>{initials(p.name)}</span>
            )}
            <div className={s['proj-title']}>
              <h1>{p.name}</h1>
              <span>{`${modules} ${modules === 1 ? 'module' : 'modules'} · ${p.items} items`}</span>
            </div>
          </div>
          <Link className={s['proj-analytics']} to={placePath('/analytics', p)}>
            <span className={s['proj-analytics-icon']}>
              <Icon name="bars" />
            </span>
            <span className="grow">
              <b>View analytics</b>
              <span className="muted small">Spend, generations, modules</span>
            </span>
            <span className={s['proj-arrow']} aria-hidden="true">
              →
            </span>
          </Link>
          <div className={s['proj-facts']}>
            {fact(
              'Created',
              new Date(p.created * 1000).toLocaleDateString([], { day: 'numeric', month: 'short', year: 'numeric' }),
            )}
            {fact('Last updated', p.updated ? ago(p.updated) : 'Nothing made yet')}
            {fact('Modules', String(modules))}
            {fact('Items', String(p.items))}
          </div>
          {/* Who is in the project: its owner first, then the people it is shared with, and Add for a manager or the owner. */}
          <div className={s['proj-owner']}>
            <div className={'row ' + s['proj-members-head']}>
              <span className="muted small grow">{`Members · ${p.members.length}`}</span>
              <button
                className="btn small quiet"
                onClick={() => void share()}
                title={may(p.role, 'manager') ? 'Add people to this project' : 'See who is in this project'}
              >
                <Icon name="people" />
                {may(p.role, 'manager') ? 'Add' : 'View'}
              </button>
            </div>
            {p.members.slice(0, 6).map((m) => (
              <div key={m.user_id} className={s['proj-person']}>
                <span className={css('avatar')}>{initials(m.name || m.email)}</span>
                <span className="grow">
                  <b>{m.name + (m.user_id === user.id ? ' (you)' : '')}</b>
                  <span className="muted small">{m.email}</span>
                </span>
                <span className={css('owner-tag' + (m.role === 'owner' ? '' : ' member'))}>
                  {m.role[0].toUpperCase() + m.role.slice(1)}
                </span>
              </div>
            ))}
            {p.members.length > 6 && (
              <button className="btn small quiet" onClick={() => void share()}>
                {`and ${p.members.length - 6} more`}
              </button>
            )}
          </div>
          <div className={s['proj-side-actions']}>
            {may(p.role, 'manager') && (
              <button
                className="btn block"
                onClick={() => void projectDialog({ project: p }).then((ok) => ok && reload())}
              >
                <Icon name="pencil" />
                Edit details
              </button>
            )}
            {may(p.role, 'owner') && (
              <button
                className="btn block"
                onClick={(e) => {
                  e.currentTarget.disabled = true;
                  api<Module>(`/api/projects/${p.id}/duplicate`, { method: 'POST' }).then(
                    (copy) => navigate(placePath('/project', copy)),
                    (err: Error) => tell(err.message),
                  );
                }}
              >
                <Icon name="frame" />
                Duplicate project
              </button>
            )}
            {may(p.role, 'owner') && (
              <button
                className="btn block quiet danger"
                onClick={() =>
                  void ask({
                    title: `Delete "${p.name}"?`,
                    danger: true,
                    confirm: 'Delete project',
                    message: `Its ${modules} ${modules === 1 ? 'module' : 'modules'}, its ${p.items} items and its NeuralCore are deleted with it, for good. This can't be undone.`,
                  }).then(
                    (sure) =>
                      sure &&
                      (setDeleting(true),
                      void api('/api/projects/' + p.id, { method: 'DELETE' }).then(
                        () => {
                          void navigate('/projects');
                          client.removeQueries({ queryKey: ['library', 'project', id] });
                        },
                        (e: Error) => {
                          setDeleting(false);
                          return tell(e.message);
                        },
                      )),
                  )
                }
              >
                <Icon name="trash" />
                Delete project
              </button>
            )}
          </div>
        </aside>
        <div className={s['proj-main']}>
          <section className={s['proj-section']}>
            <div className={css('section-head')}>
              <h2>Modules</h2>
              <span style={{ flex: 1 }} />
              <input
                type="text"
                className={s['proj-search']}
                placeholder="Search modules…"
                aria-label="Search modules"
                value={typed}
                onChange={(e) => setTyped(e.target.value)}
              />
              {/* a viewer only looks */}
              <button
                className={'btn primary add-module' + (may(p.role, 'creator') ? '' : ' hidden')}
                onClick={() => void addModule()}
              >
                <Icon name="plus" />
                Add module
              </button>
            </div>
            <div className={s['pcard-grid'] + ' ' + s['proj-modules']}>
              {shown.length ? (
                shown.map(([m, number]) => (
                  <div key={m.id} className={s.pcard} onClick={() => open(m)}>
                    {/* the cover is the card's button; Rename and Delete sit beside it, not in it */}
                    <div
                      className={s['pcard-cover']}
                      role="button"
                      tabIndex={0}
                      aria-label={'Open ' + m.name}
                      onKeyDown={(e: KeyboardEvent) =>
                        (e.key === 'Enter' || e.key === ' ') && (e.preventDefault(), open(m))
                      }
                    >
                      {m.cover_id ? (
                        <Still url={`/api/library/${m.cover_id}/file`} kind={m.cover_kind || 'image'} name={m.name} />
                      ) : (
                        <span
                          className={s['proj-tint']}
                          data-label={m.main ? 'MAIN' : 'M ' + String(number).padStart(2, '0')}
                          style={{
                            background: `linear-gradient(160deg, ${TINTS[number % TINTS.length][0]}, ${TINTS[number % TINTS.length][1]})`,
                          }}
                        />
                      )}
                      {m.main && <span className={s['proj-badge']} data-label="Main" />}
                    </div>
                    <div className={s['pcard-info']}>
                      <b title={m.name}>{m.name}</b>
                      <span className="muted small">{`${m.items === 1 ? '1 item' : `${m.items} items`} · ${ago(m.updated || m.created)}`}</span>
                    </div>
                    {may(p.role, 'manager') && (
                      <div className={s['pcard-actions']}>
                        <button
                          className="icon-btn"
                          title="Rename"
                          aria-label={'Rename ' + m.name}
                          onClick={act(
                            () =>
                              void projectDialog({ project: m, module: true, canvas: m.main }).then(
                                (ok) => ok && reload(),
                              ),
                          )}
                        >
                          <Icon name="pencil" />
                        </button>
                        {!m.main && (
                          <button
                            className="icon-btn"
                            title="Delete"
                            aria-label={'Delete ' + m.name}
                            onClick={act(
                              () =>
                                void ask({
                                  title: `Delete "${m.name}"?`,
                                  danger: true,
                                  confirm: 'Delete module',
                                  message: `Its ${m.items} ${m.items === 1 ? 'item is' : 'items are'} deleted with it, for good, with its canvas and agent tabs. This can't be undone.`,
                                }).then(
                                  (sure) =>
                                    sure &&
                                    void api('/api/projects/' + m.id, { method: 'DELETE' }).then(reload, (e: Error) =>
                                      tell(e.message),
                                    ),
                                ),
                            )}
                          >
                            <Icon name="trash" />
                          </button>
                        )}
                      </div>
                    )}
                  </div>
                ))
              ) : (
                <EmptyState wide>No module matches.</EmptyState>
              )}
            </div>
          </section>
        </div>
      </div>
    </>
  );
}

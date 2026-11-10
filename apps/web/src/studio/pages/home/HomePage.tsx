// The Home page: a bar to start something, the projects worked on lately, and the best work made on the studio, as an
// admin picked it for everyone (the console's Home page section). Until anything is picked, the user's own latest work.

import { useQuery } from '@tanstack/react-query';
import { useEffect, useRef, useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router';
import { itemsPage } from '@scene/shared/api/items';
import { api } from '../../../common/api';
import { Segmented } from '../../../common/components/Segmented';
import { Spill } from '../../../common/components/Spill';
import { Still } from '../../../common/components/Still';
import { EmptyState, ErrorBanner, Skeleton } from '../../../common/components/States';
import { promptOf } from '../../../common/landing/words';
import { ago, initials } from '../../../common/format';
import type { Item } from '../../../common/media/item';
import { openViewer } from '../../../common/media/Viewer';
import { Composer, type ComposerHandle } from '../../features/composer/Composer';
import { Starters } from './Starters';
import { toCreate } from '../../handoff';
import { placePath } from '../../place';
import { useProjects } from '../library/LibraryPage';
import s from './HomePage.module.css';
import { classesOf } from '../../../common/cx';
import css0 from '../../../common/components/Shared2.module.css';
import css1 from '../../../common/components/Shared3.module.css';
import css2 from '../Shared.module.css';
import css3 from '../projects/ProjectsPage.module.css';
import css4 from '../projects/projects.module.css';
import { userPrefs } from '../../userPrefs';
const css = classesOf(css0, css1, css2, css3, css4);

const RECENT = 8; // projects shown
const MADE = 60; // finished items shown

type Showcase = { sections: string[]; items: (Item & { section?: string })[] };

export default function HomePage() {
  const navigate = useNavigate();
  const location = useLocation();
  const composer = useRef<ComposerHandle>(null);
  // Someone who has made nothing yet is offered starter prompts, priced (the list is the one Home shows below).
  const own = useQuery({
    queryKey: ['library', 'home', ''],
    queryFn: () => itemsPage<Item>({ limit: MADE }).then((a) => a.items),
  });
  const fresh = own.data?.length === 0;
  const [queued, setQueued] = useState(false);
  // A prompt typed on the landing page before signing up is waiting in the prompt box (it came in the address).
  const [waiting] = useState(() => promptOf(location.search));
  const projects = (useProjects().data ?? [])
    .filter((p) => !p.parent_id)
    .sort((a, b) => (b.updated || b.created) - (a.updated || a.created))
    .slice(0, RECENT);
  const showcase = useQuery({
    queryKey: ['showcase'],
    queryFn: () => api<Showcase>('/api/showcase').catch((): Showcase => ({ sections: [], items: [] })),
    staleTime: Infinity, // a new result changes the user's own work, never the showcase
  }).data;

  const openProject = (project: (typeof projects)[number] & { modules?: number }) => {
    if (project.modules) return void navigate(placePath('/project', project)); // a project with modules opens on its page
    userPrefs.setStudio({ project: project.id });
    void navigate(placePath('/canvas', project));
  };

  return (
    <>
      {showcase?.items.length ? null : <OwnLight />}
      <div className={s['home-hero']}>
        <h1>What are you making today?</h1>
      </div>
      <div className={s['home-bar']}>
        <Composer ref={composer} initialPrompt={waiting} onQueued={() => setQueued(true)} />
        <p className={'notice ok ' + s['home-note']}>
          {queued && (
            <>
              {'Added to the queue. '}
              {/* The job is filed under no project, so the canvas opens on everything, not on the last project. */}
              <Link to="/canvas" onClick={() => userPrefs.setStudio({ project: null })}>
                Watch it on the Canvas
              </Link>
            </>
          )}
        </p>
      </div>
      {fresh && !queued && (
        <Starters
          onPick={(workflow, prompt) => {
            composer.current?.setWorkflow(workflow);
            composer.current?.setPrompt(prompt);
            composer.current?.focus();
          }}
        />
      )}
      {/* Recent projects: left out completely until the user has made one. */}
      <section className={s['home-section'] + (projects.length ? '' : ' hidden')}>
        {projects.length > 0 && (
          <>
            <div className={css('section-head')}>
              <h2>Recent projects</h2>
              <Link className="btn small quiet" to="/projects">
                See all
              </Link>
            </div>
            <div className={css('project-grid')}>
              {projects.map((p) => (
                <button key={p.id} className={css('project')} onClick={() => openProject(p)}>
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
              ))}
            </div>
          </>
        )}
      </section>
      {showcase &&
        (showcase.items.length ? (
          <Picked showcase={showcase} />
        ) : (
          <OwnWork onRerun={(item) => toCreate(navigate, { rerun: item })} />
        ))}
    </>
  );
}

/** The newest picture or video of the user's own lights the top of the page. */
function OwnLight() {
  const newest = useQuery({
    queryKey: ['library', 'home', ''],
    queryFn: () => itemsPage<Item>({ limit: MADE }).then((a) => a.items),
  }).data?.find((i) => i.kind !== 'audio');
  return <Spill id={newest?.id} kind={newest?.kind} />;
}

const KINDS = [
  { id: '', label: 'All' },
  { id: 'video', label: 'Videos' },
  { id: 'image', label: 'Images' },
  { id: 'audio', label: 'Audio' },
];

/** The user's own latest work, until an admin picks work for everyone's Home. */
function OwnWork({ onRerun }: { onRerun: (item: Item) => void }) {
  const [kind, setKind] = useState('');
  const query = useQuery({
    queryKey: ['library', 'home', kind],
    queryFn: () => itemsPage<Item>({ kind, limit: MADE }).then((a) => a.items),
  });
  const items = query.data;
  return (
    <section className={s['home-section']}>
      <div className={css('section-head')}>
        <h2>Created on Scene.ai</h2>
        <div>
          <Segmented choices={KINDS} current={kind} onPick={setKind} />
        </div>
        <Link className="btn small quiet" to="/library">
          Open library
        </Link>
      </div>
      <div className={items?.length || query.isPending ? s['made-grid'] : ''}>
        {query.isError ? (
          <ErrorBanner error={query.error} onRetry={() => void query.refetch()} />
        ) : !items ? (
          <Skeleton count={8} />
        ) : items.length ? (
          items.map((item) => (
            <button
              key={item.id}
              className={s.made}
              data-picture
              title={item.name}
              style={item.context?.width ? { aspectRatio: `${item.context.width}/${item.context.height}` } : undefined}
              onClick={() =>
                openViewer(item, {
                  actions: /^(edit|upload)\//.test(item.workflow)
                    ? []
                    : [{ label: 'Re-run', run: (close) => (close(), onRerun(item)) }],
                })
              }
            >
              <Still
                url={`/api/library/${item.id}/file`}
                kind={item.kind}
                name={item.name}
                width={item.context?.width}
                height={item.context?.height}
              />
              <span>{item.name}</span>
            </button>
          ))
        ) : (
          <EmptyState>
            {kind
              ? 'Nothing of this kind yet.'
              : 'Nothing made yet. Describe a shot in the bar above and it will appear here.'}
          </EmptyState>
        )}
      </div>
    </section>
  );
}

/** The work an admin picked for every user's Home page, under its sections' tabs. Its videos play, without sound,
 *  while they are on screen, and stop once scrolled away. */
function Picked({ showcase }: { showcase: Showcase }) {
  const [section, setSection] = useState('');
  const grid = useRef<HTMLDivElement>(null);
  const tabs = showcase.sections.filter((n) => showcase.items.some((i) => i.section === n));
  const current = tabs.includes(section) ? section : '';
  const items = showcase.items.filter((i) => !current || i.section === current);
  const first = items.find((i) => i.kind !== 'audio');

  useEffect(() => {
    const playing = new IntersectionObserver(
      (entries) =>
        entries.forEach((e) => {
          const video = e.target as HTMLVideoElement;
          if (e.isIntersecting) {
            video.preload = 'auto';
            video.play().catch(() => {});
          } else video.pause();
        }),
      { rootMargin: '120px 0px' },
    );
    if (grid.current) for (const v of grid.current.getElementsByTagName('video')) playing.observe(v);
    return () => playing.disconnect();
  }, [current, showcase]);

  return (
    <>
      <Spill id={first?.id} kind={first?.kind} base="/api/showcase" />
      <section className={s['home-section']}>
        <div className={css('section-head')}>
          <h2>Made on Scene.ai</h2>
          <div>
            {tabs.length > 0 && (
              <Segmented
                choices={[{ id: '', label: 'All' }, ...tabs.map((n) => ({ id: n, label: n }))]}
                current={current}
                onPick={setSection}
              />
            )}
          </div>
        </div>
        <div ref={grid} className={s['made-grid'] + ' ' + s['showcase-grid-home']}>
          {items.map((item) => {
            const url = `/api/showcase/${item.id}/file`;
            return (
              <button
                key={item.id}
                className={s.made}
                data-picture
                title={item.name}
                style={
                  item.context?.width ? { aspectRatio: `${item.context.width}/${item.context.height}` } : undefined
                }
                onClick={() => openViewer(item, { base: '/api/showcase' })}
              >
                {item.kind === 'video' ? (
                  <video
                    src={url}
                    poster={`/api/showcase/${item.id}/poster`}
                    muted
                    loop
                    playsInline
                    preload="none"
                    aria-label={item.name}
                  />
                ) : (
                  <img src={url} alt={item.name} loading="lazy" decoding="async" draggable={false} />
                )}
                <span>{item.name}</span>
              </button>
            );
          })}
        </div>
      </section>
    </>
  );
}

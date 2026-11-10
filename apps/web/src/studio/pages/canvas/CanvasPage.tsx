// The Canvas page: every finished item as a frame on an endless board, each row a shot, and the panel on the right
// that makes new work (Quick actions, the Agent, NeuralCore, Bulk generation). The canvas shows one project, the one
// its address names; its name is shown and opens the project's page. Keys (keys.tsx, the sheet "?" opens): 1 fits
// everything, 0 is 100%, Enter opens the selected frame, Delete deletes it (asking first), D downloads, Escape lets go,
// the arrow keys move the selected frames, Ctrl or ⌘ + J the panel.

import { useQuery, useQueryClient } from '@tanstack/react-query';
import {
  Suspense,
  lazy,
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  type CSSProperties,
} from 'react';
import { useNavigate } from 'react-router';
import { listProjects } from '@scene/shared/api/projects';
import { cx } from '../../../common/cx';
import { tabTitle } from '../../../common/format';
import type { Item } from '../../../common/media/item';
import { QuickActions } from '../../features/quick-actions/QuickActions';
import { KitPanel } from '../../features/kit/KitPanel';
import { BulkTab } from '../../features/compare/BulkTab';
import type { AgentHandle } from '../../features/agent/AgentTabs';
import { Panel, usePanel } from '../../features/panel/Panel';
import { shareDialog } from '../../features/share/shareDialog';
import { placePath, usePlaceId } from '../../place';
import { agentModule } from '../../routes';
import { useUser } from '../../session';
import { nudge } from './arrange';
import { Board } from './Board';
import { Camera } from './camera';
import { rowName } from './geometry';
import { Lost, Minimap } from './Overlay';
import { Selection } from './Selection';
import { Shelf } from './Shelf';
import { ProjectBar, ToolNote, Tools, ViewBar } from './Toolbar';
import { useCanvasActions, useNote } from './useCanvasActions';
import { canvasKeys, useCanvasLayout } from './useCanvasLayout';
import { removeItems, shortcutSheet } from './keys';
import { CanvasTip } from './Tip';
import s from './Board.module.css';

// The agent is a file of its own (routes.tsx asks for it with the canvas's); what is put in its message before it is
// there waits for it.
const AgentTabs = lazy(() => agentModule().then((found) => ({ default: found.AgentTabs })));

const typing = (target: EventTarget | null) =>
  target instanceof Element && !!target.closest('input, textarea, select, dialog, [contenteditable]');

export default function CanvasPage() {
  const project = usePlaceId();
  const user = useUser();
  const admin = user.role === 'admin';
  const navigate = useNavigate();
  const client = useQueryClient();
  const [camera] = useState(() => new Camera());
  const root = useRef<HTMLDivElement>(null);
  const agent = useRef<AgentHandle | null>(null);
  const waiting = useRef<Item[]>([]); // for the agent's message, until the agent is there
  const agentHandle = useCallback((handle: AgentHandle | null) => {
    agent.current = handle;
    if (!handle || !waiting.current.length) return;
    for (const item of waiting.current) handle.attach(item);
    waiting.current = [];
    handle.focus();
  }, []);
  const { arranged, items, change, error } = useCanvasLayout(project);
  const projects = useQuery({ queryKey: ['projects'], queryFn: () => listProjects().then((found) => found.projects) });
  const here = projects.data?.find((p) => p.id === project) ?? null;
  const [selected, setSelected] = useState<Set<number>>(() => new Set());
  const [spotlight, setSpotlight] = useState({ id: 0, n: 0 });
  const [agentJobs, setAgentJobs] = useState<Set<string>>(() => new Set());
  const [full, setFull] = useState(false);
  const [resizing, setResizing] = useState(false);
  const [dropping, setDropping] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [library, setLibrary] = useState(false);
  const [picking, setPicking] = useState<{ give: (item: Item) => void } | null>(null);
  const { note, say } = useNote();
  const room = useCallback(() => root.current?.clientWidth || 9999, []);
  const panel = usePanel(admin, room);
  const { downloader, rerun, reuseSeed, pickTake, open, download, keep, upload } = useCanvasActions({
    project,
    items,
    arranged,
    change,
    select: setSelected,
    say,
  });

  // the address names this project and module, to keep or send; the browser tab, its name. Read from a fresh list:
  // a module made a moment ago is not in the one kept from before.
  const fresh = !!projects.data && !projects.isFetching;
  useEffect(() => {
    if (!fresh) return;
    if (here) {
      const path = placePath('/canvas', here);
      if (path !== location.pathname) history.replaceState(history.state, '', path + location.search);
    }
    tabTitle(here?.name ?? 'Canvas');
  }, [here, fresh]);

  const chosen = useMemo(() => items.filter((i) => selected.has(i.id)), [items, selected]);
  const one = chosen.length === 1 ? chosen[0] : null;
  const marks = useMemo(
    () =>
      arranged ? [...arranged.spots.entries()].map(([key, spot]) => ({ key, x: spot.x, y: spot.y, h: spot.h })) : [],
    [arranged],
  );

  // The camera: what is on the canvas, and how much the panel covers. The page fits everything when it opens, and again
  // when the panel opens, closes, changes tab or width.
  const fitted = useRef(false);
  useLayoutEffect(() => {
    camera.update(marks, panel.open && !full ? panel.width + 12 : 0);
  }, [camera, marks, panel.open, panel.width, full]);
  useLayoutEffect(() => {
    if (!arranged || fitted.current) return;
    fitted.current = true;
    camera.fit();
  }, [arranged, camera]);
  useLayoutEffect(() => {
    if (fitted.current) camera.fit();
  }, [camera, panel.open, panel.tab]);

  const showPanel = panel.show;
  useEffect(() => {
    if (!panel.open || panel.tab !== 'agent') agent.current?.setFull(false); // full screen is the agent's
  }, [panel.open, panel.tab]);

  const stopPicking = useCallback(() => {
    setPicking(null);
    say('');
  }, [say]);
  /** "From canvas" in a panel's + menu: what is selected, or, with nothing selected, the next frame clicked. */
  const pick = useCallback(
    (onPick: (list: Item[]) => void) => {
      const list = items.filter((i) => selected.has(i.id));
      if (list.length) return onPick(list);
      setPicking({ give: (item) => onPick([item]) });
      say('Click a frame to use it', false, true);
    },
    [items, selected, say],
  );
  const addToChat = useCallback(
    (list: Item[]) => {
      if (!(panel.open && panel.tab === 'agent')) showPanel(true, 'agent');
      if (!agent.current) return void waiting.current.push(...list);
      for (const item of list) agent.current.attach(item);
      agent.current.focus();
    },
    [panel.open, panel.tab, showPanel],
  );

  // Glide to one item and select it, with a ring that shows which one it is. Made a moment ago, it may not be drawn yet:
  // the canvas's items are fetched again first.
  const placed = useRef(arranged);
  useLayoutEffect(() => {
    placed.current = arranged;
  });
  const focusItem = useCallback(
    async (id: number) => {
      if (!placed.current?.spots.get(id)) {
        await client.refetchQueries({ queryKey: canvasKeys.items(project) }).catch(() => {});
        await new Promise((done) => requestAnimationFrame(done)); // drawn with what came
      }
      const spot = placed.current?.spots.get(id);
      if (!spot)
        return say(
          project
            ? 'That one is not in this project. Pick All work to see it.'
            : 'That one is no longer in the library.',
          true,
        );
      camera.focus(spot);
      setSelected(new Set([id]));
      setSpotlight((was) => ({ id, n: was.n + 1 }));
    },
    [camera, client, project, say],
  );
  const locate = useCallback(
    (id: number) => {
      const rows = arranged?.layout.rows ?? [];
      const row = rows.find((r) => r.keys.includes(id));
      if (!row) return null;
      return { shot: rowName(rows, row), take: arranged?.spots.get(id)?.takeNo || row.keys.indexOf(id) + 1 };
    },
    [arranged],
  );

  // Keys over the whole page.
  const keys = useRef({ chosen, one, picking, arranged, panel });
  useLayoutEffect(() => {
    keys.current = { chosen, one, picking, arranged, panel };
  });
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const k = keys.current;
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'j') {
        e.preventDefault();
        return k.panel.show(!k.panel.open);
      }
      if (typing(e.target) || e.metaKey || e.ctrlKey) return;
      if (e.key === '1') camera.fit(true);
      else if (e.key === '0') camera.zoomTo(1);
      else if (e.key === 'Escape' && k.picking) stopPicking();
      else if (e.key === 'Escape' && k.chosen.length) setSelected(new Set());
      else if (e.key === 'Enter' && k.one) open(k.one);
      else if ((e.key === 'Delete' || e.key === 'Backspace') && k.chosen.length)
        void removeItems(k.chosen, project, client, say);
      else if (e.key === '?') void shortcutSheet();
      else if (e.key.toLowerCase() === 'd' && !e.altKey && !e.repeat) download(k.chosen);
      else if (e.key.startsWith('Arrow') && k.chosen.length && k.arranged) {
        const moved = nudge(
          k.arranged.layout,
          k.chosen.map((i) => i.id),
          e.key as 'ArrowUp',
        );
        if (!moved) return;
        e.preventDefault();
        change(moved);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [camera, stopPicking, open, download, change, project, client, say]);

  const hint = error
    ? error.message
    : marks.length
      ? ''
      : 'Use the panel on the right to make a shot. Everything you make lands here.';
  const style = { '--panel-w': panel.width + 'px' } as CSSProperties;
  return (
    <div
      ref={root}
      className={s.canvas}
      style={style}
      data-panel={panel.open || undefined}
      data-full={full || undefined}
      data-resizing={resizing || undefined}
      data-dropping={dropping || undefined}
      data-picking={picking ? '' : undefined}
    >
      {arranged ? (
        <Board
          camera={camera}
          arranged={arranged}
          items={items}
          selected={selected}
          spotlight={spotlight}
          agentJobs={agentJobs}
          admin={admin}
          onSelect={setSelected}
          onLayout={change}
          onRename={(row, name) =>
            change({
              ...arranged.layout,
              rows: arranged.layout.rows.map((r) => (r.id === row.id ? { ...r, name } : r)),
            })
          }
          onPickTake={pickTake}
          onClickFrame={(item) => {
            if (!picking) return false;
            stopPicking();
            picking.give(item);
            return true;
          }}
          onOpen={open}
          onAttach={(item) => addToChat([item])}
          onDragging={setDragging}
          onFiles={(files) => void upload(files)}
          onDropping={setDropping}
        />
      ) : (
        <div className={s['canvas-stage']} />
      )}
      <ProjectBar
        name={
          here
            ? here.parent_name
              ? `${here.parent_name} › ${here.name}`
              : here.canvas_name
                ? `${here.name} › ${here.canvas_name}`
                : here.name
            : 'All work'
        }
        count={items.length}
        linked={!!here}
        onName={() => here && void navigate(placePath('/project', here))}
        onShare={() =>
          here &&
          void shareDialog({
            projectId: here.parent_id || here.id,
            projectName: here.parent_name || here.name,
            me: user.id,
          })
        }
      />
      <Tools libraryOpen={library} onFiles={(files) => void upload(files)} onLibrary={() => setLibrary(!library)} />
      {library && (
        <Shelf
          project={project}
          onClose={() => setLibrary(false)}
          onOpen={open}
          onMoved={(item) => setSelected(new Set([item.id]))}
          note={say}
        />
      )}
      <ToolNote text={note.text} error={note.error} onCancel={picking ? stopPicking : undefined} />
      {arranged && (
        <Selection
          camera={camera}
          chosen={chosen}
          spots={arranged.spots}
          project={project}
          hidden={dragging}
          onOpen={open}
          onRerun={rerun}
          onReuseSeed={reuseSeed}
          onDownload={download}
          onKeep={(item) => void keep(item)}
        />
      )}
      <ViewBar
        camera={camera}
        panelOpen={panel.open}
        onFit={() => camera.fit(true)}
        onPanel={() => panel.show(!panel.open)}
      />
      <Minimap camera={camera} marks={marks} selected={selected} />
      <CanvasTip />
      <p className={cx('muted', s['canvas-hint'], !hint && 'hidden')}>{hint}</p>
      <Lost camera={camera} any={marks.length > 0} onBack={() => camera.fit(true)} />
      <Panel
        tab={panel.tab}
        admin={admin}
        width={panel.width}
        onTab={(tab) => panel.show(true, tab)}
        onClose={() => panel.show(false)}
        onResize={panel.resize}
        onResized={(w) => {
          panel.keep(w);
          camera.fit();
        }}
        onResizing={setResizing}
        tabs={{
          quick: (
            <QuickActions
              project={project}
              startFrom={one && one.kind !== 'audio' ? one : null}
              pick={pick}
              focus={panel.tab === 'quick' ? panel.focus : 0}
            />
          ),
          agent: (
            <Suspense>
              <AgentTabs
                ref={agentHandle}
                project={project}
                selection={chosen}
                pick={pick}
                onUploaded={() => void client.invalidateQueries({ queryKey: canvasKeys.items(project) })}
                onJobs={(ids) => setAgentJobs(new Set(ids))}
                onFocus={(id) => void focusItem(id)}
                locate={locate}
                onFull={setFull}
                focus={panel.tab === 'agent' ? panel.focus : 0}
              />
            </Suspense>
          ),
          kit: (
            <KitPanel
              project={project}
              selected={one}
              active={panel.open && panel.tab === 'kit'}
              focus={panel.tab === 'kit' ? panel.focus : 0}
            />
          ),
          bulk: (
            <BulkTab
              project={project}
              active={panel.open && panel.tab === 'bulk'}
              focus={panel.tab === 'bulk' ? panel.focus : 0}
            />
          ),
        }}
      />
      {/* downloads go through this link: one click for each file */}
      <a ref={downloader} hidden />
    </div>
  );
}

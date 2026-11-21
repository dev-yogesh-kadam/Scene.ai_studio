// The NeuralCore tab of the canvas panel: the memory of the module open now, as a tree in the manner of Frameo's: the
// cast (this module's entries, with their controls), the assets (every file of the module, by its record) and the notes
// the agent and its skills keep. "You" is what the agent remembers of the user everywhere. Pictures are described in
// the background as they come in: while some wait, it looks again a few times.

import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useRef, useState } from 'react';
import {
  castEntries,
  coreMemory,
  deleteState,
  forget,
  importSheet,
  orderEntries,
  putState,
  remembered,
  changeEntry,
  removeEntry,
  type CastEntry,
  type MemoryLeaf,
} from '@scene/shared/api/kit';
import { ask, tell } from '../../../common/components/Dialog';
import { Icon } from '../../../common/components/Icon/Icon';
import { addMenu } from '../../../common/components/Popover';
import { Segmented } from '../../../common/components/Segmented';
import { cx, mergeModules } from '../../../common/cx';
import { ago } from '../../../common/format';
import type { Item } from '../../../common/media/item';
import { prefs } from '../../../common/prefs';
import { cardDialog } from './CardDialog';
import { editLeaf, sheetDone } from './dialogs';
import { KIT, KIT_TYPES, addToKitDialog } from './kit';
import { ModuleMemory, YouView } from './MemoryView';
import s1 from './Kit.module.css';
import s2 from './Kit2.module.css';
import { classesOf } from '../../../common/cx';
import css0 from '../../../common/components/Shared3.module.css';

const s = mergeModules(s1, s2);
const css = classesOf(css0);

const FIND_KEY = 'scene.kit.type';
const LOOK_AGAIN = 15000; // while pictures wait to be described, this often (a few times)

type Props = {
  project: number;
  selected: Item | null; // the one canvas item selected
  active: boolean; // the tab is showing: what the agent has just made or kept shows at once
  focus: number;
};

export function KitPanel({ project, selected, active, focus }: Props) {
  const client = useQueryClient();
  const [scope, setScope] = useState<'module' | 'you'>('module');
  const [filter, setFilter] = useState(() => prefs.get(FIND_KEY));
  const [search, setSearch] = useState('');
  const [fetching, setFetching] = useState(false); // an asset sheet's pictures are being fetched
  const looks = useRef(0);
  const searchBox = useRef<HTMLInputElement>(null);
  const upload = useRef<HTMLInputElement>(null);
  const sheet = useRef<HTMLInputElement>(null);
  const cast = useQuery({
    queryKey: ['kit', project],
    queryFn: () => castEntries(project),
    enabled: !!project && active && scope === 'module',
    refetchInterval: (query) => {
      const waiting = (query.state.data ?? []).some((e) => !e.about && (e.kind === 'image' || e.kind === 'video'));
      if (!waiting) looks.current = 0;
      return waiting && looks.current++ < 4 ? LOOK_AGAIN : false;
    },
  });
  const memory = useQuery({
    queryKey: ['core', 'memory', project],
    queryFn: () => coreMemory(project),
    enabled: !!project && active && scope === 'module',
  });
  const you = useQuery({
    queryKey: ['remembered', project],
    queryFn: () => remembered(project),
    enabled: !!project && active && scope === 'you',
  });
  const loadedAt = Math.max(cast.dataUpdatedAt, memory.dataUpdatedAt, scope === 'you' ? you.dataUpdatedAt : 0);
  const stamp = fetching ? 'fetching the sheet’s pictures…' : loadedAt ? 'refreshed ' + ago(loadedAt / 1000) : '';
  useEffect(() => {
    if (focus && active) searchBox.current?.focus();
  }, [focus, active]);

  const reload = () =>
    Promise.all([
      client.invalidateQueries({ queryKey: ['kit', project] }),
      client.invalidateQueries({ queryKey: ['core', 'memory', project] }),
      client.invalidateQueries({ queryKey: ['remembered', project] }),
    ]);
  const entries = cast.data ?? [];
  const fail = (e: unknown) => void tell((e as Error).message);

  const change = async (entry: CastEntry, json: Partial<CastEntry>) => {
    try {
      await changeEntry(entry.id, json);
    } catch (e) {
      fail(e);
    }
    void reload();
  };
  const remove = async (entry: CastEntry) => {
    const sure = await ask({
      title: `Take “${entry.name}” out of the cast?`,
      danger: true,
      confirm: 'Take it out',
      message: 'The agent will no longer know it by this name in this module.',
    });
    if (!sure) return;
    try {
      await removeEntry(entry.id);
    } catch (e) {
      fail(e);
    }
    void reload();
  };
  // Drop an entry before another: the whole cast is saved in its new order.
  const move = async (entry: CastEntry, target: CastEntry | null) => {
    const list = entries.filter((e) => e.id !== entry.id);
    const at = target ? list.findIndex((e) => e.id === target.id) : list.length;
    list.splice(at < 0 ? list.length : at, 0, entry);
    client.setQueryData(['kit', project], list);
    try {
      client.setQueryData(
        ['kit', project],
        (
          await orderEntries(
            project || null,
            list.map((e) => e.id),
          )
        ).entries,
      );
    } catch (e) {
      fail(e);
    }
  };
  const added = (made: unknown) => made && void reload();
  const openAdd = (anchor: HTMLElement) =>
    addMenu(anchor, [
      {
        icon: 'upload',
        label: 'Upload a file',
        hint: 'picture, video, sound or script',
        run: () => upload.current?.click(),
      },
      {
        icon: 'grid',
        label: selected ? `“${selected.name}” from the canvas` : 'Select an item on the canvas first',
        run: () => void (selected && addToKitDialog({ project, item: selected }).then(added)),
      },
      { icon: 'book', label: 'Paste a script', run: () => void addToKitDialog({ project, script: true }).then(added) },
      {
        icon: 'queue',
        label: 'Import an asset sheet',
        hint: 'CSV: type, name, image link, notes',
        run: () => sheet.current?.click(),
      },
    ]);
  const bringSheet = async (file: File) => {
    setFetching(true);
    try {
      const done = await importSheet(file, project || null);
      void reload();
      void sheetDone(done);
    } catch (e) {
      fail(e);
    }
    setFetching(false);
  };
  const tree = {
    edit: (leaf: MemoryLeaf) =>
      void editLeaf(leaf, {
        save: (value) => putState(project, leaf.path, value),
        remove: () => deleteState(project, leaf.path),
      }).then((done) => done && void reload()),
  };

  const words = search.trim().toLowerCase();
  const shown = entries.filter(
    (e) =>
      (!filter || e.type === filter) && (!words || `${e.name} ${e.about} ${e.use_note}`.toLowerCase().includes(words)),
  );
  return (
    <div className={cx(s['kit-panel'], s['memory-panel'])}>
      <div className={s['memory-head']}>
        <b>Memory</b>
        <span style={{ flex: 1 }} />
        <span className={css('slate-text')}>{stamp}</span>
        <button className="icon-btn" title="Refresh" aria-label="Refresh" onClick={() => void reload()}>
          ↻
        </button>
        {!!project && scope === 'module' && (
          <button
            className="btn small primary"
            type="button"
            title="Add to the cast"
            onClick={(e) => openAdd(e.currentTarget)}
          >
            <Icon name="plus" />
            Add
          </button>
        )}
        <input
          ref={upload}
          type="file"
          hidden
          accept="image/*,video/*,audio/*,.heic,.heif,.avif,.txt,.md,.docx,.pdf,.srt,.json,.svg"
          onChange={(e) => {
            const file = e.target.files?.[0];
            e.target.value = '';
            if (file) void addToKitDialog({ project, file }).then(added);
          }}
        />
        <input
          ref={sheet}
          type="file"
          hidden
          accept=".csv,.tsv,text/csv"
          onChange={(e) => {
            const file = e.target.files?.[0];
            e.target.value = '';
            if (file) void bringSheet(file);
          }}
        />
      </div>
      <div className={s['kit-views']}>
        <Segmented
          className={s['views-seg']}
          choices={[
            { id: 'module', label: 'This module', hint: 'What this module keeps' },
            { id: 'you', label: 'You', hint: 'What the agent remembers of you in this module' },
          ]}
          current={scope}
          onPick={setScope}
        />
      </div>
      <div className={s['kit-body']}>
        {scope === 'you' && !project ? (
          <p className="small muted">Memory belongs to a module: open a project first.</p>
        ) : scope === 'you' ? (
          <YouView
            found={you.data}
            error={you.error?.message}
            onForget={(key) => void forget(project, key).then(() => reload(), fail)}
          />
        ) : (
          <ModuleMemory
            project={project}
            memory={memory.data}
            error={memory.error?.message}
            entries={cast.data}
            onEdit={tree.edit}
            cast={{
              shown,
              tools:
                entries.length > 3 ? (
                  <div className={s['kit-tools']}>
                    <input
                      ref={searchBox}
                      type="search"
                      className={s['kit-search']}
                      placeholder="Search by name or what it shows"
                      aria-label={`Search the ${KIT}`}
                      value={search}
                      onChange={(e) => setSearch(e.target.value)}
                    />
                    <select
                      className={s['kit-filter']}
                      aria-label="Type"
                      value={filter}
                      onChange={(e) => {
                        setFilter(e.target.value);
                        prefs.set(FIND_KEY, e.target.value);
                      }}
                    >
                      <option value="">All types</option>
                      {KIT_TYPES.map((t) => (
                        <option key={t.id} value={t.id}>
                          {t.label}
                        </option>
                      ))}
                    </select>
                  </div>
                ) : null,
              onChange: (entry, json) => void change(entry, json),
              onRemove: (entry) => void remove(entry),
              onCard: (entry) => void cardDialog(entry, entries).then((saved) => saved && void reload()),
              onMove: (entry, target) => void move(entry, target),
            }}
          />
        )}
      </div>
    </div>
  );
}

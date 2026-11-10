// The library drawer: everything the user has made or brought in, to bring onto this canvas. A click on work of
// another project moves it here; on work already here, opens it.

import { useQueryClient } from '@tanstack/react-query';
import { useEffect, useState } from 'react';
import { Link } from 'react-router';
import { moveItem } from '@scene/shared/api/canvas';
import { Segmented } from '../../../common/components/Segmented';
import { Still } from '../../../common/components/Still';
import { cx } from '../../../common/cx';
import type { Item } from '../../../common/media/item';
import { LoadMore, useLibraryPages } from '../../features/media/useLibraryPages';
import { canvasKeys } from './useCanvasLayout';
import s from './Shelf.module.css';
import { classesOf } from '../../../common/cx';
import css0 from './Shared.module.css';
const css = classesOf(css0);

const KINDS = [
  { id: '', label: 'All' },
  { id: 'image', label: 'Images' },
  { id: 'video', label: 'Videos' },
  { id: 'audio', label: 'Audio' },
];

type Props = {
  project: number;
  onClose: () => void;
  onOpen: (item: Item) => void;
  onMoved: (item: Item) => void; // it is on this canvas now: selected there
  note: (text: string, error?: boolean) => void;
};

export function Shelf({ project, onClose, onOpen, onMoved, note }: Props) {
  const client = useQueryClient();
  const [kind, setKind] = useState('');
  const [q, setQ] = useState('');
  const [typed, setTyped] = useState(''); // asked of the server a moment after the typing stops
  useEffect(() => {
    const timer = setTimeout(() => setTyped(q), 250);
    return () => clearTimeout(timer);
  }, [q]);
  // The server finds the words in the prompt too; the drawer searches names, so it keeps only those (and asks for
  // more pages while what it keeps does not reach the end of the drawer).
  const all = useLibraryPages(['library', 'shelf', kind, typed], { kind, q: typed });
  const failed = all.error?.message;
  useEffect(() => {
    if (failed) note(failed, true);
  }, [failed, note]);
  const words = q.toLowerCase().split(/\s+/).filter(Boolean);
  const shown = (all.items ?? []).filter(
    (i) => (!kind || i.kind === kind) && words.every((w) => i.name.toLowerCase().includes(w)),
  );
  const bring = async (item: Item) => {
    try {
      await moveItem(item.id, project);
      await client.invalidateQueries({ queryKey: canvasKeys.items(project) });
      await client.invalidateQueries({ queryKey: ['library', 'shelf'] });
      onMoved(item);
      note(`${item.name} is on the canvas.`);
    } catch (e) {
      note((e as Error).message, true);
    }
  };
  return (
    <div className={css(cx('float', s['canvas-library']))} role="dialog" aria-label="Library">
      <div className={s['library-head']}>
        <b>Library</b>
        <span style={{ flex: 1 }} />
        <Link className="btn small quiet" to="/library">
          Open page
        </Link>
        <button className="icon-btn" aria-label="Close the library" title="Close" onClick={onClose}>
          ×
        </button>
      </div>
      <Segmented choices={KINDS} current={kind} onPick={setKind} className={s.kinds} />
      <input
        type="search"
        className="search"
        placeholder="Search by name"
        aria-label="Search the library"
        value={q}
        onChange={(e) => setQ(e.target.value)}
      />
      <div className={s['library-grid']}>
        {shown.length ? (
          shown.map((item) => {
            const here = !project || item.project_id === project;
            return (
              <button
                key={item.id}
                type="button"
                className={cx(s['library-tile'], here && s.here)}
                title={
                  here
                    ? 'Open it'
                    : `In ${item.project_name || 'no project'}. Click to move it to this project's canvas.`
                }
                onClick={() => (here ? onOpen(item) : void bring(item))}
              >
                <span className={s['library-thumb']}>
                  <Still
                    url={`/api/library/${item.id}/file`}
                    kind={item.kind}
                    name={item.name}
                    width={item.context?.width}
                    height={item.context?.height}
                  />
                </span>
                <span className={s['library-name']}>{item.name}</span>
                <span className={s['library-where']}>
                  {here ? (project ? 'On this canvas' : item.project_name || 'No project') : '+ Add to canvas'}
                </span>
              </button>
            );
          })
        ) : (
          <p className="muted small">
            {all.items
              ? all.items.length || kind || typed
                ? 'Nothing matches.'
                : 'Your library is empty.'
              : 'Loading…'}
          </p>
        )}
        <LoadMore pages={all} />
      </div>
    </div>
  );
}

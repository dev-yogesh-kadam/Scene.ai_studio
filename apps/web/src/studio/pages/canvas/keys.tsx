// The canvas's keyboard (U1): the sheet "?" opens, listing every key, and Delete, which asks first and then deletes the
// selected frames' items from the library (and so from the canvas).

import type { QueryClient } from '@tanstack/react-query';
import { api } from '../../../common/api';
import { ask, openDialog } from '../../../common/components/Dialog';
import type { Item } from '../../../common/media/item';
import { canvasKeys } from './useCanvasLayout';
import s from './keys.module.css';

const KEYS: [string, string][] = [
  ['Enter', 'Open the selected frame'],
  ['Delete', 'Delete the selected frames (asks first)'],
  ['Arrow keys', 'Move the selected frames'],
  ['D', 'Download the selected frames'],
  ['Escape', 'Let go of the selection'],
  ['1', 'Fit everything on the screen'],
  ['0', 'Zoom to 100%'],
  ['Ctrl or ⌘ + J', 'Show or hide the panel'],
  ['?', 'This list'],
];

export function shortcutSheet() {
  return openDialog<void>(
    (close) => (
      <>
        <h2>Keyboard shortcuts</h2>
        <dl className={s.keys}>
          {KEYS.map(([key, what]) => (
            <div key={key}>
              <dt>
                <kbd>{key}</kbd>
              </dt>
              <dd>{what}</dd>
            </div>
          ))}
        </dl>
        <div className="row">
          <span className="grow" />
          <button type="button" className="btn primary" onClick={() => close()} autoFocus>
            Done
          </button>
        </div>
      </>
    ),
    { label: 'Keyboard shortcuts' },
  );
}

/** Delete the chosen frames' items, once the user says so; `say` tells how it went. */
export async function removeItems(
  chosen: Item[],
  project: number,
  client: QueryClient,
  say: (text: string, error?: boolean) => void,
) {
  if (!chosen.length) return;
  const one = chosen.length === 1;
  const sure = await ask({
    title: one ? `Delete "${chosen[0].name}"?` : `Delete ${chosen.length} items?`,
    message: `${one ? 'It is' : 'They are'} deleted from the library and this canvas, for good. This can't be undone.`,
    confirm: 'Delete',
    danger: true,
  });
  if (!sure) return;
  const failed: string[] = [];
  for (const item of chosen)
    await api('/api/library/' + item.id, { method: 'DELETE' }).catch(() => failed.push(item.name));
  await client.invalidateQueries({ queryKey: canvasKeys.items(project) });
  if (failed.length) say(`Not deleted: ${failed.join(', ')}. Only your own work can be deleted.`, true);
  else say(one ? 'Deleted.' : `${chosen.length} items deleted.`);
}

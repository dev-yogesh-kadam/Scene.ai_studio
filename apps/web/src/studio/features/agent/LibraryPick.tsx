// The library picker: a library item (something made or uploaded, in any project) for a message.

import { useEffect, useState } from 'react';
import { itemsPage } from '@scene/shared/api/items';
import { openDialog } from '../../../common/components/Dialog';
import type { Item } from '../../../common/media/item';
import s from '../kit/Kit.module.css';
import { classesOf } from '../../../common/cx';
import css0 from '../../../common/components/Shared2.module.css';
import css1 from '../../../common/components/Shared3.module.css';
import css2 from '../Shared.module.css';
const css = classesOf(css0, css1, css2);

const SHOWN = 60; // the newest that match

function Picker({ close }: { close: (item?: Item | null) => void }) {
  const [q, setQ] = useState('');
  const [found, setFound] = useState<{ list?: Item[]; error?: string }>({});
  useEffect(() => {
    let live = true;
    const timer = setTimeout(() => {
      itemsPage<Item>({ q, limit: SHOWN }).then(
        (answer) => live && setFound({ list: answer.items }),
        (e: Error) => live && setFound({ error: e.message }),
      );
    }, 250);
    return () => {
      live = false;
      clearTimeout(timer);
    };
  }, [q]);
  return (
    <>
      <h2>From your library</h2>
      <input
        type="search"
        placeholder="Search your library…"
        aria-label="Search your library"
        autoFocus
        value={q}
        onChange={(e) => setQ(e.target.value)}
      />
      <div className={css('asset-grid ' + s['library-pick-grid'])}>
        {found.error ? (
          <p className="error">{found.error}</p>
        ) : found.list?.length ? (
          found.list.map((item) => (
            <button key={item.id} type="button" className={css('asset')} onClick={() => close(item)}>
              <div className={css('asset-thumb')}>
                {item.kind === 'audio' ? (
                  <span className="note">♪</span>
                ) : (
                  <img src={`/api/library/${item.id}/poster`} alt={item.name} loading="lazy" />
                )}
              </div>
              <div className={css('asset-name')}>{item.name}</div>
              <div className="muted">{item.project_name || item.kind}</div>
            </button>
          ))
        ) : found.list ? (
          <p className="muted">{q.trim() ? 'Nothing in your library matches that.' : 'Your library is empty.'}</p>
        ) : null}
      </div>
      <div className={css('dialog-buttons')}>
        <button className="btn" onClick={() => close()}>
          Close
        </button>
      </div>
    </>
  );
}

/** Resolves with a library item the user picks, or null. */
export const pickLibraryItem = () => openDialog<Item>((close) => <Picker close={close} />);

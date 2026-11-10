// Pick from every user's library: search it, choose the section, and add as many as wanted; each is copied at once.

import { useRef, useState } from 'react';
import { api } from '../../../common/api';
import { Modal } from '../../../common/components/Dialog';
import { Segmented } from '../../../common/components/Segmented';
import { Still } from '../../../common/components/Still';
import { openViewer } from '../../../common/media/Viewer';
import type { Item } from '../../../common/media/item';
import { useSection } from '../shared/context';
import { SearchBox, failed } from '../shared/ui';
import { BASE, type Data } from './showcaseData';
import { classesOf } from '../../../common/cx';
import css0 from '../../../common/components/Shared2.module.css';
import css1 from '../../../common/components/Shared3.module.css';
import css2 from '../shared/Console.module.css';
import css3 from './PickDialog.module.css';
import css4 from './Shared.module.css';
import css5 from '../../../studio/pages/projects/ProjectsPage.module.css';
const css = classesOf(css0, css1, css2, css3, css4, css5);

type Found = Item & { user_name: string };
const KINDS = [
  { id: 'video', label: 'Videos' },
  { id: 'image', label: 'Images' },
];

export function PickDialog({
  data,
  section,
  onClose,
}: {
  data: Data;
  section: string;
  onClose: (changed: boolean) => void;
}) {
  const [kind, setKind] = useState('video');
  const [q, setQ] = useState('');
  const [into, setInto] = useState(section);
  const [added, setAdded] = useState(() => new Set(data.items.map((i) => i.from)));
  const [adding, setAdding] = useState<number | null>(null);
  const changed = useRef(false);
  const query = useSection('showcase', ['pick', kind, q], () =>
    api<{ items: Found[] }>('/api/admin/library?' + new URLSearchParams({ kind, q })),
  );
  const add = async (id: number) => {
    setAdding(id);
    try {
      await api(BASE, { method: 'POST', json: { item_id: id, section: into } });
      setAdded((was) => new Set(was).add(id));
      changed.current = true;
    } catch (e) {
      failed(e);
    }
    setAdding(null);
  };
  const found = query.data?.items;
  return (
    <Modal className={css('showcase-dialog')} onClose={() => onClose(changed.current)}>
      <h2>Add to the Home page</h2>
      <div className={css('toolbar')}>
        <Segmented choices={KINDS} current={kind} onPick={setKind} />
        <SearchBox placeholder="Search name, prompt or user" value={q} onChange={setQ} />
        <span className={css('push')} />
        <span className="muted small">Into</span>
        <select className={css('filter')} aria-label="Section" value={into} onChange={(e) => setInto(e.target.value)}>
          <option value="">No section (All only)</option>
          {data.sections.map((n) => (
            <option key={n} value={n}>
              {n}
            </option>
          ))}
        </select>
      </div>
      <div className={css('showcase-pick')}>
        {query.error && <p className="error">{query.error.message}</p>}
        {found &&
          (found.length ? (
            found.map((item) => {
              const on = added.has(item.id);
              return (
                <div key={item.id} className={css('showcase-pick-item')}>
                  <button
                    type="button"
                    className={css('showcase-thumb')}
                    title="Watch it"
                    onClick={() => openViewer(item, { base: '/api/admin/library', owner: true })}
                  >
                    <Still url={`/api/admin/library/${item.id}/file`} kind={item.kind} name={item.name} />
                  </button>
                  <b title={item.name}>{item.name}</b>
                  <span className="muted small">{item.user_name}</span>
                  <button
                    className={'btn small' + (on ? '' : ' primary')}
                    disabled={on || adding === item.id}
                    onClick={() => void add(item.id)}
                  >
                    {on ? 'On the Home page' : 'Add'}
                  </button>
                </div>
              );
            })
          ) : (
            <div className={css('empty')}>Nothing matches.</div>
          ))}
      </div>
      <div className={css('dialog-buttons')}>
        <button className="btn" onClick={() => onClose(changed.current)}>
          Done
        </button>
      </div>
    </Modal>
  );
}

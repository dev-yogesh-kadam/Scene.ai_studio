// The Home page: the best work, picked here, that every user sees under "Made on Scene.ai" (backend/scene/showcase.py).
// Sections of the admin's naming (Shorts & Reels, Microdrama, Ads…) are the tabs over it; the order here is its order.

import { useState } from 'react';
import { api } from '../../../common/api';
import { Segmented } from '../../../common/components/Segmented';
import { useConsole, useSection } from '../shared/context';
import { Loaded, failed, sure } from '../shared/ui';
import { ItemCard } from './ItemCard';
import { PickDialog } from './PickDialog';
import { BASE, moved, type Data, type ShowItem } from './showcaseData';
import { classesOf } from '../../../common/cx';
import css0 from '../../../common/components/Shared2.module.css';
import css1 from '../../../common/components/Shared3.module.css';
import css2 from '../shared/Console.module.css';
import css3 from './Showcase.module.css';
import css4 from '../../../studio/pages/projects/ProjectsPage.module.css';
const css = classesOf(css0, css1, css2, css3, css4);

function Sections({ data, save }: { data: Data; save: (sections: string[]) => void }) {
  const [fresh, setFresh] = useState('');
  const add = () => {
    if (fresh.trim()) {
      save([...data.sections, fresh.trim()]);
      setFresh('');
    }
  };
  return (
    <div className={css('card showcase-sections')}>
      <div className={css('showcase-sections-head')}>
        <b>Sections</b>
        <span className="muted small">
          The tabs over the work on the Home page, in this order. &quot;All&quot; is always first.
        </span>
      </div>
      <div className={css('chips')}>
        {data.sections.map((name, i) => (
          <span key={name} className={css('showcase-chip')}>
            <button
              type="button"
              className="icon-btn small"
              title="Earlier"
              disabled={i === 0}
              onClick={() => save(moved(data.sections, i, -1))}
            >
              ←
            </button>
            <span>
              {name}
              <i className="muted">{` · ${data.items.filter((it) => it.section === name).length}`}</i>
            </span>
            <button
              type="button"
              className="icon-btn small"
              title="Later"
              disabled={i === data.sections.length - 1}
              onClick={() => save(moved(data.sections, i, 1))}
            >
              →
            </button>
            <button
              type="button"
              className="icon-btn small"
              title="Remove the section (its work stays, under All)"
              onClick={() => {
                void sure(`Remove the section "${name}"? Its work stays on the Home page, under All.`).then((yes) => {
                  if (yes) save(data.sections.filter((x) => x !== name));
                });
              }}
            >
              ×
            </button>
          </span>
        ))}
        <span className={css('showcase-new')}>
          <input
            type="text"
            className="search"
            placeholder="New section, e.g. Microdrama"
            maxLength={40}
            value={fresh}
            onChange={(e) => setFresh(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') add();
            }}
          />
          <button className="btn small" onClick={add}>
            Add section
          </button>
        </span>
      </div>
    </div>
  );
}

export default function Showcase() {
  const { refresh } = useConsole();
  const [section, setSection] = useState('');
  const [picking, setPicking] = useState(false);
  const query = useSection('showcase', ['list'], () => api<Data>(BASE));
  return (
    <Loaded query={query}>
      {(data) => {
        // Every change is saved at once: the sections and the whole order, with each item's name, section and prompt switch.
        const save = (sections: string[], items: ShowItem[]) => {
          api(BASE, {
            method: 'PUT',
            json: {
              sections,
              items: items.map((i) => ({ key: i.key, name: i.name, section: i.section, show_prompt: i.show_prompt })),
            },
          }).then(refresh, failed);
        };
        const remove = (item: ShowItem) => {
          void sure(`Take "${item.name}" off the Home page?`).then((yes) => {
            if (yes) api(`${BASE}/${item.key}`, { method: 'DELETE' }).then(refresh, failed);
          });
        };
        const shown = data.items.filter((i) => !section || i.section === section);
        return (
          <>
            <p className="muted" style={{ margin: '0 0 14px' }}>
              Every user sees this work on their Home page, under &quot;Made on Scene.ai&quot;. The file is copied when
              you add it, so it stays even if its owner deletes it. The owner&apos;s name is never shown.
            </p>
            <Sections data={data} save={(sections) => save(sections, data.items)} />
            <div className={css('toolbar')} style={{ marginTop: 16 }}>
              <Segmented
                choices={[
                  { id: '', label: `All · ${data.items.length}` },
                  ...data.sections.map((n) => ({ id: n, label: n })),
                ]}
                current={section}
                onPick={setSection}
              />
              <span className={css('muted small push')}>{`${data.items.length} of ${data.limit}`}</span>
              <button
                className="btn primary small"
                disabled={data.items.length >= data.limit}
                onClick={() => setPicking(true)}
              >
                Add from library
              </button>
            </div>
            {shown.length ? (
              <div className={css('showcase-grid')}>
                {shown.map((item) => {
                  const at = data.items.indexOf(item);
                  return (
                    <ItemCard
                      key={item.key}
                      item={item}
                      sections={data.sections}
                      first={at === 0}
                      last={at === data.items.length - 1}
                      onChange={(changes) =>
                        save(
                          data.sections,
                          data.items.map((x) => (x === item ? { ...x, ...changes } : x)),
                        )
                      }
                      onMove={(by) => save(data.sections, moved(data.items, at, by))}
                      onRemove={() => remove(item)}
                    />
                  );
                })}
              </div>
            ) : (
              <div className={css('empty')}>
                {data.items.length
                  ? 'Nothing in this section yet.'
                  : 'Nothing on the Home page yet: users see their own latest work there. Add the best from the library.'}
              </div>
            )}
            {picking && (
              <PickDialog
                data={data}
                section={section}
                onClose={(changed) => {
                  setPicking(false);
                  if (changed) void refresh();
                }}
              />
            )}
          </>
        );
      }}
    </Loaded>
  );
}

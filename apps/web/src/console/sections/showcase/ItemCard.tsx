// One piece of work on the Home page: what it is called, its section, whether its prompt shows, and its place.

import { useRef } from 'react';
import { Icon } from '../../../common/components/Icon/Icon';
import { Still } from '../../../common/components/Still';
import { openViewer } from '../../../common/media/Viewer';
import { BASE, viewed, type ShowItem } from './showcaseData';
import { classesOf } from '../../../common/cx';
import css0 from '../shared/Console.module.css';
import css1 from './ItemCard.module.css';
import css2 from './Shared.module.css';
const css = classesOf(css0, css1, css2);

export function ItemCard({
  item,
  sections,
  first,
  last,
  onChange,
  onMove,
  onRemove,
}: {
  item: ShowItem;
  sections: string[];
  first: boolean;
  last: boolean;
  onChange: (changes: Partial<ShowItem>) => void;
  onMove: (by: number) => void;
  onRemove: () => void;
}) {
  const sent = useRef(item.name);
  // The name is saved when it is done being typed: on leaving the box, or Enter.
  const rename = (value: string) => {
    const name = value.trim();
    if (name && name !== sent.current) {
      sent.current = name;
      onChange({ name });
    }
  };
  return (
    <div className={css('showcase-item')}>
      <button
        type="button"
        className={css('showcase-thumb')}
        title="Watch it as users do"
        style={item.width ? { aspectRatio: `${item.width}/${item.height}` } : undefined}
        onClick={() => openViewer(viewed(item), { base: BASE })}
      >
        <Still url={`${BASE}/${item.key}/file`} kind={item.kind} name={item.name} />
        {item.kind === 'video' && (
          <span className={css('showcase-kind')}>
            <Icon name="video" />
          </span>
        )}
      </button>
      <input
        key={item.name}
        type="text"
        className={css('showcase-name')}
        defaultValue={item.name}
        maxLength={80}
        aria-label="Name"
        onBlur={(e) => rename(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter') rename(e.currentTarget.value);
        }}
      />
      <select
        className={css('filter')}
        aria-label="Section"
        value={sections.includes(item.section) ? item.section : ''}
        onChange={(e) => onChange({ section: e.target.value })}
      >
        <option value="">No section (All only)</option>
        {sections.map((n) => (
          <option key={n} value={n}>
            {n}
          </option>
        ))}
      </select>
      <label
        className={css('showcase-check')}
        title={item.prompt ? 'Users see the prompt when they open it' : 'It has no prompt'}
      >
        <input
          type="checkbox"
          checked={item.show_prompt !== false}
          disabled={!item.prompt}
          onChange={(e) => onChange({ show_prompt: e.target.checked })}
        />
        Show the prompt
      </label>
      <div className={css('showcase-row')}>
        <button className="btn small" title="Show it earlier" disabled={first} onClick={() => onMove(-1)}>
          ←
        </button>
        <button className="btn small" title="Show it later" disabled={last} onClick={() => onMove(1)}>
          →
        </button>
        <span className={css('push')} />
        <button className="btn small danger" onClick={onRemove}>
          Remove
        </button>
      </div>
    </div>
  );
}

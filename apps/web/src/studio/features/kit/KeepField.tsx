// "Keep the result in NeuralCore as …": a name and a type given before Generate, so what is made goes into the
// project's kit under that name when it is done (a character sheet made by hand, a location plate). A picture can be
// kept as any type but a voice; a sound only as a voice. Shown only for a job in a project that makes one of those.

import { useEffect, useRef, useState } from 'react';
import { KIT, KIT_TYPES } from './kit';
import { classesOf } from '../../../common/cx';
import css0 from './KeepField.module.css';
const css = classesOf(css0);

export type Keep = { as: string; name: string } | undefined;

export function keepTypes(kindMade: string, inProject: boolean) {
  if (!inProject) return [];
  return kindMade === 'audio'
    ? ['voice']
    : kindMade === 'image'
      ? ['character', 'location', 'prop', 'outfit', 'style']
      : [];
}

/** `resetKey` changes after each Generate: kept once, the next one is not kept unless asked again. */
export function KeepField({
  kindMade,
  inProject,
  onChange,
  resetKey,
}: {
  kindMade: string;
  inProject: boolean;
  onChange: (keep: Keep) => void;
  resetKey: number;
}) {
  const types = keepTypes(kindMade, inProject);
  const [on, setOn] = useState(false);
  const [name, setName] = useState('');
  const [chosen, setChosen] = useState('');
  const [seenReset, setSeenReset] = useState(resetKey);
  if (seenReset !== resetKey) {
    setSeenReset(resetKey);
    setOn(false);
    setName('');
  }
  const as = types.includes(chosen) ? chosen : types[0];
  const nameInput = useRef<HTMLInputElement>(null);
  useEffect(() => {
    onChange(on && name.trim() && types.length ? { as, name: name.trim() } : undefined);
    // `types` follows kindMade and inProject, which are listed
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [on, name, as, kindMade, inProject, onChange]);
  if (!types.length) return null;
  return (
    <div className={css('keep-field')}>
      <label className={css('check keep-check')}>
        <input
          type="checkbox"
          checked={on}
          onChange={(e) => {
            setOn(e.target.checked);
            if (e.target.checked) setTimeout(() => nameInput.current?.focus());
          }}
        />
        <span>{`Keep the result in the ${KIT}`}</span>
      </label>
      <div className={css('keep-row' + (on ? '' : ' hidden'))}>
        <input
          ref={nameInput}
          type="text"
          className={css('keep-name')}
          maxLength={60}
          placeholder="Name, e.g. Maya"
          aria-label={`Name in the ${KIT}`}
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
        <select className={css('keep-type')} aria-label="Type" value={as} onChange={(e) => setChosen(e.target.value)}>
          {types.map((t) => (
            <option key={t} value={t}>
              {KIT_TYPES.find((x) => x.id === t)?.label}
            </option>
          ))}
        </select>
      </div>
    </div>
  );
}

// The kit of a project (NeuralCore): everything it is made from, by name (characters, locations, props, outfits, voices,
// styles and scripts). The agent knows each entry by its name and what it shows; an entry that is "always on" goes into
// every shot that has a slot for it. Here: the types, an entry's thumbnail, and the dialogs to add one and to pick one.

import { useEffect, useRef, useState } from 'react';
import { api } from '../../../common/api';
import { Field } from '../../../common/components/AuthForm';
import { openDialog, tell } from '../../../common/components/Dialog';
import { Icon } from '../../../common/components/Icon/Icon';
import { KIT } from '../../words';
import { classesOf } from '../../../common/cx';
import css0 from '../../../common/components/Shared2.module.css';
import css1 from '../../../common/components/Shared3.module.css';
import css2 from '../Shared.module.css';
import kit1 from './Kit.module.css';
import kit2 from './Kit2.module.css';
const css = classesOf(css0, css1, css2, kit1, kit2);

export { KIT };

export const KIT_TYPES = [
  { id: 'character', label: 'Character' },
  { id: 'location', label: 'Location' },
  { id: 'prop', label: 'Prop' },
  { id: 'outfit', label: 'Outfit' },
  { id: 'voice', label: 'Voice' },
  { id: 'style', label: 'Style' },
  { id: 'script', label: 'Script' },
  { id: 'other', label: 'Other' },
];

export type KitEntry = {
  id: number;
  name: string;
  type: string;
  kind: string;
  always?: boolean | number;
  [key: string]: unknown;
};

export const kitUrl = (entry: { id: number }) => `/api/kit/${entry.id}/file`;

// The type of an entry made from a file dropped into a reference slot with this label (as the server reads it).
const SLOT_TYPES: [string, RegExp][] = [
  ['character', /character|main character|second person|\bperson\b/i],
  ['location', /background|location/i],
  ['outfit', /outfit|costume|clothing/i],
  ['prop', /\bprop\b|product/i],
  ['voice', /voice/i],
  ['style', /\bstyle\b/i],
];
export const typeForSlot = (label: string) => (SLOT_TYPES.find(([, words]) => words.test(label || '')) || ['other'])[0];

export function KitThumb({ entry }: { entry: KitEntry }) {
  // a picture's or a clip's poster: a small still made once by the server, not the file itself
  if (entry.kind === 'image' || entry.kind === 'video')
    return <img src={`/api/kit/${entry.id}/poster`} alt="" loading="lazy" draggable={false} />;
  return (
    <span className={css('kit-glyph')}>
      <Icon name={entry.kind === 'audio' ? 'audio' : 'book'} />
    </span>
  );
}

export function TypeSelect({ value, onChange }: { value: string; onChange: (type: string) => void }) {
  return (
    <select className={css('kit-type')} aria-label="Type" value={value} onChange={(e) => onChange(e.target.value)}>
      {KIT_TYPES.map((t) => (
        <option key={t.id} value={t.id}>
          {t.label}
        </option>
      ))}
    </select>
  );
}

type AddArgs = {
  project?: number;
  file?: File | null;
  item?: { id: number; name: string } | null;
  script?: boolean;
  type?: string;
};

/** Add a file, a canvas item or a script to a project's kit. Resolves with the new entry, or null if it is closed. */
export async function addToKitDialog({
  project = 0,
  file = null,
  item = null,
  script = false,
  type = '',
}: AddArgs = {}) {
  if (!project) {
    // a NeuralCore belongs to a project: there is none for all work
    await tell(
      `The ${KIT} belongs to a project.`,
      `Open a project from All projects and keep its characters, places and props there; each module keeps its own.`,
    );
    return null;
  }
  const guess = type || (script ? 'script' : file && /^audio\//.test(file.type) ? 'voice' : 'character');
  const start = (file ? file.name.replace(/\.[^.]+$/, '') : item ? item.name : '').slice(0, 60);
  return openDialog<KitEntry>((close) => (
    <AddToKit project={project} file={file} item={item} script={script} guess={guess} start={start} close={close} />
  ));
}

function AddToKit({
  project,
  file,
  item,
  script,
  guess,
  start,
  close,
}: {
  project: number;
  file: File | null;
  item: { id: number; name: string } | null;
  script: boolean;
  guess: string;
  start: string;
  close: (entry?: KitEntry | null) => void;
}) {
  const [name, setName] = useState(start);
  const [type, setType] = useState(guess);
  const [always, setAlways] = useState(false);
  const [words, setWords] = useState('');
  const [error, setError] = useState('');
  const nameInput = useRef<HTMLInputElement>(null);
  useEffect(() => {
    nameInput.current?.focus();
    nameInput.current?.select();
  }, []);

  const save = async () => {
    if (!name.trim()) {
      setError('Give it a name: the agent finds it by this name.');
      nameInput.current?.focus();
      return;
    }
    try {
      let made: KitEntry;
      if (file) {
        const data = new FormData();
        data.append('file', file, file.name);
        data.append('name', name);
        data.append('type', type);
        data.append('project_id', String(project || ''));
        if (always) data.append('always', '1');
        made = await api<KitEntry>('/api/kit', { method: 'POST', body: data });
      } else {
        made = await api<KitEntry>('/api/kit', {
          method: 'POST',
          json: { project_id: project || null, name, type, always, ...(item ? { item: item.id } : { text: words }) },
        });
      }
      close(made);
    } catch (e) {
      setError((e as Error).message);
    }
  };

  return (
    <>
      <h2>{script ? `Add a script to the ${KIT}` : `Add to the ${KIT}`}</h2>
      <p className="muted">
        The agent finds it by its name in every tab of this project, and Quick actions offers it in the slots it fits.
      </p>
      <Field label="Name">
        <input
          ref={nameInput}
          type="text"
          maxLength={60}
          value={name}
          placeholder={script ? 'Ep 135' : 'Violet'}
          onChange={(e) => setName(e.target.value)}
        />
      </Field>
      <Field label="Type">
        <TypeSelect value={type} onChange={setType} />
      </Field>
      {script && (
        <Field label="Script">
          <textarea
            rows={10}
            placeholder="Paste the script here."
            value={words}
            onChange={(e) => setWords(e.target.value)}
          />
        </Field>
      )}
      {!script && (
        <label className="check">
          <input type="checkbox" checked={always} onChange={(e) => setAlways(e.target.checked)} />
          <span>Always on: put it into every shot that has a place for it</span>
        </label>
      )}
      <p className="error notice">{error}</p>
      <div className={css('dialog-buttons')}>
        <button className="btn" onClick={() => close()}>
          Cancel
        </button>
        <button className="btn primary" onClick={() => void save()}>
          Add
        </button>
      </div>
    </>
  );
}

/** Pick an entry of the project's kit for a reference slot that takes `kind` (image, video or audio). Resolves with the
 *  entry, or null. */
export async function pickFromKit(kind: string, project = 0) {
  const fits = ({ image: ['image', 'video'], video: ['video'], audio: ['audio', 'video'] } as Record<string, string[]>)[
    kind
  ] || [kind];
  let entries: KitEntry[];
  try {
    entries = (await api<{ entries: KitEntry[] }>('/api/kit?project=' + (project || 0))).entries.filter((e) =>
      fits.includes(e.kind),
    );
  } catch (e) {
    await tell((e as Error).message);
    return null;
  }
  return openDialog<KitEntry>((close) => (
    <>
      <h2>{`From the ${KIT}`}</h2>
      {entries.length ? (
        <div className={css('asset-grid')}>
          {entries.map((entry) => (
            <button key={entry.id} type="button" className={css('asset')} onClick={() => close(entry)}>
              <div className={css('asset-thumb')}>
                <KitThumb entry={entry} />
              </div>
              <div className={css('asset-name')}>{entry.name}</div>
              <div className="muted">{entry.type}</div>
            </button>
          ))}
        </div>
      ) : (
        <p className="muted">
          {`Nothing in this module's ${KIT} fits here yet. Add characters, locations and voices in the ${KIT} tab of the canvas.`}
        </p>
      )}
      <div className={css('dialog-buttons')}>
        <button className="btn" onClick={() => close()}>
          Close
        </button>
      </div>
    </>
  ));
}

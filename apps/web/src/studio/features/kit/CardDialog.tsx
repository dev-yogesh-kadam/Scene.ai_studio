// The card of a NeuralCore entry: what it shows (the model's words, or the user's), how to use it, and how it fits
// with the rest: the entry it is a look (or a time of day) of, from which scene, a location's palette, a character's
// relatives.

import { useState } from 'react';
import { changeEntry, type CastEntry } from '@scene/shared/api/kit';
import { Field } from '../../../common/components/AuthForm';
import { openDialog } from '../../../common/components/Dialog';
import s1 from './Kit.module.css';
import s2 from './Kit2.module.css';
import { classesOf, mergeModules } from '../../../common/cx';
import css0 from '../../../common/components/Shared2.module.css';
import css1 from '../../../common/components/Shared3.module.css';

const s = mergeModules(s1, s2);
const css = classesOf(css0, css1);

const HAS_LOOKS = ['character', 'location', 'prop']; // the types whose entries have looks (a location's: times of day)

type Kin = { to: number; relation: string; blood: boolean };

/** Opens the card; resolves true when it was saved. */
export function cardDialog(entry: CastEntry, entries: CastEntry[]) {
  return openDialog<boolean>((close) => <Card entry={entry} entries={entries} close={close} />);
}

function Card({ entry, entries, close }: { entry: CastEntry; entries: CastEntry[]; close: (saved?: boolean) => void }) {
  const type = entry.type;
  const [about, setAbout] = useState(entry.about || '');
  const [use, setUse] = useState(entry.use_note || '');
  const [lookOf, setLookOf] = useState(String(entry.look_of || 0));
  const [variant, setVariant] = useState(entry.variant || '');
  const [scene, setScene] = useState(entry.from_scene ? String(entry.from_scene) : '');
  const [palette, setPalette] = useState(entry.palette || '');
  const [kin, setKin] = useState<(Kin & { n: number })[]>(() => (entry.relations || []).map((r, n) => ({ ...r, n })));
  const [error, setError] = useState('');
  const looks = HAS_LOOKS.includes(type);
  const bases = entries.filter((e) => e.id !== entry.id && e.type === type && !e.look_of);
  const people = entries.filter((e) => e.id !== entry.id && e.type === 'character' && !e.look_of);
  const kinShown = type === 'character' && people.length > 0;

  const links = () =>
    !looks
      ? {}
      : {
          look_of: Number(lookOf) || 0,
          variant,
          ...(type === 'character' ? { from_scene: Number(scene) || 0 } : {}),
          ...(type === 'location' ? { palette } : {}),
          ...(kinShown && lookOf === '0'
            ? {
                relations: kin
                  .map(({ to, relation, blood }) => ({ to, relation: relation.trim(), blood }))
                  .filter((r) => r.to && r.relation),
              }
            : {}),
        };
  const save = async () => {
    try {
      await changeEntry(entry.id, { about, use_note: use, ...links() });
      close(true);
    } catch (e) {
      setError((e as Error).message);
    }
  };
  const setOne = (n: number, change: Partial<Kin>) =>
    setKin((list) => list.map((k) => (k.n === n ? { ...k, ...change } : k)));
  return (
    <>
      <h2>{entry.name}</h2>
      <p className="muted">
        What it shows is written by the agent&apos;s model when it is added. Correct it here: your words win.
      </p>
      <Field label="What it shows">
        <textarea rows={5} maxLength={600} value={about} onChange={(e) => setAbout(e.target.value)} />
      </Field>
      <Field label="How to use it">
        <textarea
          rows={3}
          maxLength={600}
          placeholder='When and how to use it, e.g. "only in the night scenes".'
          value={use}
          onChange={(e) => setUse(e.target.value)}
        />
      </Field>
      {looks && (
        <div className={s['kit-links']}>
          <h3>How it fits together</h3>
          {bases.length > 0 && (
            <Field label={type === 'location' ? 'A time of day of' : 'A look of'}>
              <select value={lookOf} onChange={(e) => setLookOf(e.target.value)}>
                <option value="0">— an entry of its own —</option>
                {bases.map((e) => (
                  <option key={e.id} value={String(e.id)}>
                    {e.name}
                  </option>
                ))}
              </select>
            </Field>
          )}
          <Field label={type === 'location' ? 'Time of day' : 'The look'}>
            <input
              maxLength={40}
              value={variant}
              placeholder={
                type === 'location' ? 'night, dawn, golden hour…' : 'torn sleeve, battle armour, as a child…'
              }
              onChange={(e) => setVariant(e.target.value)}
            />
          </Field>
          {type === 'character' && (
            <Field label="Starts in scene">
              <input
                type="number"
                min={0}
                max={10000}
                value={scene}
                placeholder="any"
                onChange={(e) => setScene(e.target.value)}
              />
            </Field>
          )}
          {type === 'location' && (
            <Field label="Palette">
              <input
                maxLength={200}
                value={palette}
                placeholder="cold steel-blue shadows, warm sodium highlights, muted and filmic"
                onChange={(e) => setPalette(e.target.value)}
              />
            </Field>
          )}
          {kinShown && (
            <div>
              <Field label="Relatives">
                <div className={s['kit-kin']}>
                  {kin.map((k) => (
                    <div key={k.n} className={s['kit-kin-row']}>
                      <select value={String(k.to)} onChange={(e) => setOne(k.n, { to: Number(e.target.value) })}>
                        <option value="0">Who…</option>
                        {people.map((e) => (
                          <option key={e.id} value={String(e.id)}>
                            {e.name}
                          </option>
                        ))}
                      </select>
                      <span className="muted">is their</span>
                      <input
                        maxLength={30}
                        value={k.relation}
                        placeholder="mother, brother, mother-in-law…"
                        aria-label="How they are related"
                        onChange={(e) => setOne(k.n, { relation: e.target.value })}
                      />
                      <select
                        aria-label="By blood or in-law"
                        value={k.blood ? 'blood' : 'law'}
                        onChange={(e) => setOne(k.n, { blood: e.target.value === 'blood' })}
                      >
                        <option value="blood">blood</option>
                        <option value="law">in-law</option>
                      </select>
                      <button
                        type="button"
                        className="icon-btn"
                        aria-label="Remove this relative"
                        onClick={() => setKin((list) => list.filter((x) => x.n !== k.n))}
                      >
                        ×
                      </button>
                    </div>
                  ))}
                </div>
              </Field>
              <button
                type="button"
                className="btn small"
                onClick={() =>
                  setKin((list) => [
                    ...list,
                    { to: 0, relation: '', blood: true, n: Math.max(0, ...list.map((x) => x.n)) + 1 },
                  ])
                }
              >
                Add a relative
              </button>
            </div>
          )}
        </div>
      )}
      <p className="error notice">{error}</p>
      <div className={css('dialog-buttons')}>
        <button className="btn" onClick={() => close()}>
          Cancel
        </button>
        <button className="btn primary" onClick={() => void save()}>
          Save
        </button>
      </div>
    </>
  );
}

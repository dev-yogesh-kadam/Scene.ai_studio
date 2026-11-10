// The references of a Quick action's form. An image model's picture references are a strip (REF 1, REF 2 …, one
// empty box until the model's maximum) with chips that type each one's name into the prompt; other workflows show
// their slots (the first few, the required and the filled ones; "More references" for the rest). A box's "+" menu
// takes a file from this computer, the NeuralCore or the canvas; a file can also be dropped on it, and × empties it.

import { useRef, useState } from 'react';
import { addMenu, type AddRow } from '../../../common/components/Popover';
import { Icon } from '../../../common/components/Icon/Icon';
import { thumbUrl } from '../../../common/components/Still';
import { cx } from '../../../common/cx';
import type { Item } from '../../../common/media/item';
import type { Slot } from '../jobs/jobForm';
import { KIT, pickFromKit } from '../kit/kit';
import { short, type Ref } from './refs';
import type { ActionForm } from './useActionForm';
import s from './QuickActions.module.css';
import { classesOf } from '../../../common/cx';
import css0 from '../../../common/components/Shared3.module.css';
const css = classesOf(css0);

const ACCEPT: Record<string, string> = { image: 'image/*', video: 'video/*', audio: 'audio/*,video/*' };
const KIND_WORD: Record<string, string> = { image: 'Image', video: 'Video', audio: 'Audio' };
const SHOWN = 3; // reference boxes in view before "More references" is pressed

export type Pick = (onPick: (items: Item[]) => void) => void;

type BoxProps = {
  slot: Slot;
  current: Ref | undefined;
  label: string;
  title: string;
  ref_?: boolean; // a picture reference (REF n) rather than a slot
  menu: (file: () => void) => AddRow[];
  onFile: (file: File) => void;
  onClear: () => void;
  clearLabel: string;
  onSeconds?: (seconds: number) => void; // the slot an upscale is priced by: its video's length is read
};

function Box({ slot, current, label, title, ref_, menu, onFile, onClear, clearLabel, onSeconds }: BoxProps) {
  const file = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);
  const shown = current && (current.shown || (ref_ ? 'image' : slot.kind)); // a cast item can be a video for a picture
  return (
    <div className={cx(s.slot, ref_ && s['ref-slot'])}>
      <div className={s['slot-label']} title={slot.label}>
        {label}
      </div>
      <div className={s['slot-frame']}>
        <button
          type="button"
          className={cx(
            s['slot-box'],
            current ? s.filled : ref_ && s['ref-empty'],
            current?.cast && s.cast,
            over && s.over,
          )}
          data-slot={slot.id}
          title={title}
          aria-haspopup="menu"
          onClick={(e) =>
            addMenu(
              e.currentTarget,
              menu(() => file.current?.click()),
            )
          }
          onDragOver={(e) => {
            e.preventDefault();
            setOver(true);
          }}
          onDragLeave={() => setOver(false)}
          onDrop={(e) => {
            e.preventDefault();
            setOver(false);
            if (e.dataTransfer.files[0]) onFile(e.dataTransfer.files[0]);
          }}
        >
          {!current ? (
            <Icon name="plus" />
          ) : shown === 'image' ? (
            <img src={thumbUrl(current.url)} alt="" />
          ) : shown === 'video' ? (
            <video src={current.url + '#t=0.1'} muted preload="metadata" />
          ) : (
            <span>♪</span>
          )}
        </button>
        {current && (
          <button type="button" className={s['slot-clear']} title="Remove" aria-label={clearLabel} onClick={onClear}>
            ×
          </button>
        )}
      </div>
      {ref_ && slot.tag ? (
        <div className={cx(s['slot-tag'], !current && s.muted)} title={`The prompt calls this reference ${slot.tag}`}>
          {slot.tag}
        </div>
      ) : null}
      <input
        ref={file}
        type="file"
        accept={ACCEPT[ref_ ? 'image' : slot.kind]}
        hidden
        onChange={(e) => {
          if (e.target.files?.[0]) onFile(e.target.files[0]);
          e.target.value = '';
        }}
      />
      {onSeconds && current?.file ? (
        <video
          hidden
          preload="metadata"
          src={current.url}
          onLoadedMetadata={(e) => {
            if (Number.isFinite(e.currentTarget.duration)) onSeconds(e.currentTarget.duration);
          }}
        />
      ) : null}
    </div>
  );
}

/** The "+" menu of a box: the computer, the project's kit, or what is selected on the canvas. */
function rows(word: string, upload: () => void, fromKit: () => void, fromCanvas: (() => void) | null): AddRow[] {
  return [
    { icon: 'upload', label: 'Upload', hint: word, run: upload },
    { icon: 'memory', label: `From the ${KIT}`, hint: 'By name', run: fromKit },
    ...(fromCanvas ? [{ icon: 'target' as const, label: 'From canvas', hint: 'Selected item', run: fromCanvas }] : []),
  ];
}

export function Source({ action, project, pick }: { action: ActionForm; project: number; pick: Pick | null }) {
  const { form, setForm, refs, slots } = action;
  const wf = form.wf;
  if (!wf) return null;
  const fromKit = async (slot: Slot) => {
    const asset = await pickFromKit(slot.kind, project);
    if (asset) action.setRef(slot, { assetId: asset.id, name: asset.name, url: `/api/kit/${asset.id}/file` });
  };
  const fromCanvas = (slot: Slot, why: (item: Item) => string) =>
    pick &&
    (() =>
      pick((list) => {
        if (!action.dropItem(slot.id, list[0])) action.showError(new Error(why(list[0])));
      }));

  if (form.kind === 'image') {
    const filled = slots.filter((x) => refs[x.id]).length;
    const said = form.refNote ? <p className={cx('small muted', s['ref-note'])}>{form.refNote}</p> : null;
    if (!slots.length) return said ? <div className="field">{said}</div> : null; // words only
    const boxes = slots.slice(0, filled < slots.length ? filled + 1 : filled); // one empty box, until the maximum
    return (
      <div className="field">
        <div className="label">
          References<span className={css('slate-text')}>{` · up to ${slots.length}`}</span>
        </div>
        <div className={cx(s.slots, s['ref-strip'])}>
          {boxes.map((slot, i) => {
            const current = refs[slot.id];
            return (
              <Box
                key={slot.id}
                slot={slot}
                current={current}
                ref_
                label={(current ? `REF ${i + 1}` : 'REFERENCE') + (slot.required ? ' *' : '')}
                title={current ? current.name : `Add a reference picture: upload, from the ${KIT} or from the canvas`}
                menu={(upload) =>
                  rows(
                    'Image',
                    upload,
                    () => void fromKit(slot),
                    fromCanvas(slot, (item) => `${item.name} can't be a reference: it is not a picture or a video.`),
                  )
                }
                onFile={(file) => (current ? action.setRef(slot, file) : action.addRef(file))}
                onClear={() => action.remove(i)}
                clearLabel={`Remove REF ${i + 1}`}
              />
            );
          })}
        </div>
        {said}
      </div>
    );
  }

  const all = wf.refs.filter(
    (r) => !r.when || Object.entries(r.when).every(([k, v]) => ([] as string[]).concat(v).includes(form.options[k])),
  );
  if (!all.length) return null;
  // A workflow can have many optional slots; the first few, the required ones and the filled ones stay in view.
  const shown = all.filter((r, i) => form.allRefs || i < SHOWN || !r.optional || refs[r.id]);
  const more = all.length - shown.length;
  const upSlot = form.kind === 'upscaler' ? wf.refs.find((r) => r.kind === 'video') : undefined;
  return (
    <div className="field">
      <div className="label">Source</div>
      <div className={s.slots}>
        {shown.map((slot) => {
          const current = refs[slot.id];
          return (
            <Box
              key={slot.id}
              slot={slot}
              current={current}
              label={short(slot.label) + (slot.optional ? '' : ' *')}
              title={
                current
                  ? current.name + (current.cast ? `, always on in this project's ${KIT}` : '')
                  : `Add a file: upload, from the ${KIT} or from the canvas`
              }
              menu={(upload) =>
                rows(
                  KIND_WORD[slot.kind] || 'File',
                  upload,
                  () => void fromKit(slot),
                  fromCanvas(
                    slot,
                    (item) => `${item.name} can't go in "${short(slot.label)}": it takes another kind of file.`,
                  ),
                )
              }
              onFile={(file) => action.setRef(slot, file)}
              onClear={() => action.setRef(slot, null)}
              clearLabel={`Remove ${current?.name ?? ''}`}
              onSeconds={upSlot?.id === slot.id ? (sec) => action.setSeconds(slot.id, sec) : undefined}
            />
          );
        })}
      </div>
      {(more > 0 || form.allRefs) && all.length > SHOWN && (
        <button
          type="button"
          className="btn small quiet"
          style={{ marginTop: 6 }}
          onClick={() => setForm((was) => ({ ...was, allRefs: !was.allRefs }))}
        >
          {form.allRefs ? 'Fewer references' : `More references (${more})`}
        </button>
      )}
    </div>
  );
}

/** How this model's prompt names the references, and a chip per reference that types its name where the cursor is. */
export function RefHint({ action, onToken }: { action: ActionForm; onToken: (token: string) => void }) {
  const { form, refs, slots } = action;
  const naming = form.wf?.ref_naming ?? {};
  const tokens = naming.tokens ?? [];
  const filled = slots.filter((x) => refs[x.id]).length;
  const chips = tokens.length ? slots.slice(0, filled).map((_, i) => tokens[i] || '') : [];
  if (form.kind !== 'image' || !slots.length || (!naming.hint && !chips.length)) return null;
  return (
    <div className={s['ref-hint']}>
      {naming.hint && <span className="small muted">{naming.hint}</span>}
      {chips.map((token, i) => (
        <button
          key={i}
          type="button"
          className={s['ref-chip']}
          title={`Type ${token} into the prompt`}
          onClick={() => onToken(token)}
        >
          {`+ REF ${i + 1}: ${token}`}
        </button>
      ))}
    </div>
  );
}

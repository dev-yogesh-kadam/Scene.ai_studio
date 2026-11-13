// The reference boxes of the Create form: drop a file on one, click it, or pick from the project's NeuralCore. A list of
// references shows the filled boxes and one empty one, up to its maximum.

import { useRef, useState, type DragEvent, type MouseEvent } from 'react';
import { KIT, addToKitDialog, pickFromKit, typeForSlot } from '../../features/kit/kit';
import { inUse, type JobForm, type RefValue, type Slot } from '../../features/jobs/jobForm';
import { thumbUrl } from '../../../common/components/Still';
import s from './CreatePage.module.css';
import { classesOf } from '../../../common/cx';
import css0 from './CreatePage.module.css';
import css1 from './References.module.css';
const css = classesOf(css0, css1);

const ACCEPT = { image: 'image/*', video: 'video/*', audio: 'audio/*,video/*' };

/** The form with `slot` set to `value` (a File, a reference, or null to empty it). In a list of references the ones
 *  after a removed one move up. */
export function withRef(form: JobForm, slot: Slot, value: File | RefValue | null): JobForm {
  const refs = { ...form.refs };
  const old = refs[slot.id];
  if (old?.file && old.url) URL.revokeObjectURL(old.url);
  if (value instanceof File) refs[slot.id] = { file: value, name: value.name, url: URL.createObjectURL(value) };
  else if (value) refs[slot.id] = value;
  else delete refs[slot.id];
  if (!value && slot.order) {
    const listed = form.wf.refs.filter((r) => r.order);
    const kept = listed.map((r) => refs[r.id]).filter(Boolean);
    for (const r of listed) delete refs[r.id];
    kept.forEach((ref, i) => (refs[listed[i].id] = ref));
  }
  return { ...form, refs };
}

export function References({ form, onChange }: { form: JobForm; onChange: (form: JobForm) => void }) {
  const wf = form.wf;
  const filled = wf.refs.filter((r) => r.order && form.refs[r.id]).length;
  const shown = wf.refs.filter((r) => inUse(r, form.options, wf) && (!r.order || r.order <= filled + 1));
  if (!shown.length) return <div />;
  const set = (slot: Slot, value: File | RefValue | null) => onChange(withRef(form, slot, value));
  return (
    <div className={s['form-section']}>
      <h2>References</h2>
      <p className="muted">{`All optional unless marked with *. Drop a file on a box, click it, or pick one from this project's ${KIT}.`}</p>
      <div className={s.refs}>
        {shown.map((slot) => (
          <RefBox
            key={slot.id}
            slot={slot}
            current={form.refs[slot.id]}
            projectId={form.projectId}
            onSet={(v) => set(slot, v)}
          />
        ))}
      </div>
    </div>
  );
}

function RefBox({
  slot,
  current,
  projectId,
  onSet,
}: {
  slot: Slot;
  current?: RefValue;
  projectId: number | null;
  onSet: (value: File | RefValue | null) => void;
}) {
  const file = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);
  const stop = (fn: () => void) => (e: MouseEvent) => {
    e.stopPropagation();
    fn();
  };
  const chooseSaved = async () => {
    const asset = await pickFromKit(slot.kind, projectId || 0);
    if (asset) onSet({ assetId: asset.id, name: asset.name, kind: asset.kind, url: `/api/kit/${asset.id}/file` });
  };
  let content;
  if (!current) {
    content = slot.default
      ? `Uses ${slot.default} unless you add a file`
      : { image: 'Drop an image', video: 'Drop a video', audio: 'Drop audio or video' }[slot.kind];
  } else if (slot.kind === 'image') {
    content = <img src={thumbUrl(current.url ?? '')} alt="" />;
  } else if (slot.kind === 'video') {
    content = <video src={current.url} muted preload="metadata" />;
  } else {
    content = <span className="note">♪</span>;
  }
  return (
    <div
      className={css(s.ref + (current ? ' filled' : '') + (over ? ' over' : ''))}
      title={slot.label}
      onClick={() => file.current?.click()}
      onDragOver={(e: DragEvent) => {
        e.preventDefault();
        setOver(true);
      }}
      onDragLeave={() => setOver(false)}
      onDrop={(e: DragEvent) => {
        e.preventDefault();
        setOver(false);
        if (e.dataTransfer.files[0]) onSet(e.dataTransfer.files[0]);
      }}
    >
      <div className={s['ref-label']}>{slot.label + (slot.optional ? '' : ' *')}</div>
      {slot.tag && (
        <div className={css('slot-tag')} title={`The prompt calls this reference ${slot.tag}`}>
          {'In the prompt: ' + slot.tag}
        </div>
      )}
      <div className={s['ref-body']}>{content}</div>
      {current && <div className={s['ref-name']}>{current.name}</div>}
      <div className={s['ref-actions']}>
        {!current && (
          <button
            type="button"
            className="btn small quiet"
            title={`Pick from this project's ${KIT}`}
            onClick={stop(() => void chooseSaved())}
          >
            {KIT}
          </button>
        )}
        {current?.file && (
          <button
            type="button"
            className="btn small quiet"
            title={`Keep this file in this project's ${KIT} under a name`}
            onClick={stop(
              () => void addToKitDialog({ project: projectId || 0, file: current.file, type: typeForSlot(slot.label) }),
            )}
          >
            {`Add to ${KIT}`}
          </button>
        )}
      </div>
      {current && (
        <button type="button" className={css('remove')} title="Remove" onClick={stop(() => onSet(null))}>
          ×
        </button>
      )}
      <input
        ref={file}
        type="file"
        accept={ACCEPT[slot.kind]}
        hidden
        onChange={(e) => {
          if (e.target.files?.[0]) onSet(e.target.files[0]);
          e.target.value = '';
        }}
      />
    </div>
  );
}

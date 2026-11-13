// The form of one Quick action: the model, what it does, its modes, the references, the prompt (and any other text a
// presets file keeps in view), keeping the result in the NeuralCore, and at the foot the few settings and Generate.

import { useEffect, useRef } from 'react';
import { Icon } from '../../../common/components/Icon/Icon';
import { Segmented } from '../../../common/components/Segmented';
import { cx } from '../../../common/cx';
import { byRole, chosenModel, offered, pickValue, pickerGroups } from '../jobs/jobForm';
import { KeepField } from '../kit/KeepField';
import { Pills } from './Pills';
import { RefHint, Source, type Pick } from './RefSlots';
import { short } from './refs';
import type { ActionForm as Action } from './useActionForm';
import s from './QuickActions.module.css';
import { classesOf } from '../../../common/cx';
import css0 from '../../../common/components/Shared3.module.css';
const css = classesOf(css0);

const PLACEHOLDER: Record<string, string> = { image: 'Describe the image', audio: 'Describe the music' };

type Props = {
  action: Action;
  label: string;
  project: number;
  pick: Pick | null;
  focus: number; // changes when the panel asks the form to take the focus
  onBack: () => void;
};

export function ActionForm({ action, label, project, pick, focus, onBack }: Props) {
  const { form, setForm, quote } = action;
  const wf = form.wf;
  const prompt = useRef<HTMLTextAreaElement>(null);
  useEffect(() => {
    if (focus) prompt.current?.focus();
  }, [focus]);

  // Type a reference's name into the prompt where the cursor is.
  const insertToken = (token: string) => {
    const box = prompt.current;
    const text = action.text;
    const at = box?.selectionStart ?? text.length;
    const end = box?.selectionEnd ?? at;
    const before = text.slice(0, at);
    const pad = before && !/\s$/.test(before) ? ' ' : '';
    action.setText(before + pad + token + text.slice(end));
    requestAnimationFrame(() => {
      if (!box) return;
      box.focus();
      box.selectionStart = box.selectionEnd = at + pad.length + token.length;
    });
  };

  return (
    <div className={s.quick}>
      <div className={s['quick-head']}>
        <button className="icon-btn" title="Back to quick actions" aria-label="Back to quick actions" onClick={onBack}>
          <Icon name="back" />
        </button>
        <b>{label}</b>
      </div>
      <div className={s['quick-body']}>
        {(wf || form.catalog.length > 0) && (
          <div className={cx('field', s.field)}>
            <div className="label">
              Model
              <span style={{ flex: 1 }} />
              <span className={css('slate-text')}>{wf ? (quote?.text ?? '') : ''}</span>
            </div>
            {/* Two groups, never mixed: ComfyUI's workflows and the generation server's models. */}
            <select
              aria-label="Model"
              value={wf ? pickValue(wf, form.options) : ''}
              onChange={(e) => e.target.value && void action.selectWorkflow(e.target.value)}
            >
              {!wf && (
                <option value="" disabled>
                  Choose a model…
                </option>
              )}
              {pickerGroups(form.catalog, (w) => w.title.replace(/^Text to Image:\s*/i, '')).map((g) => (
                <optgroup key={g.label} label={g.label}>
                  {g.entries.map((e) => (
                    <option key={e.value} value={e.value}>
                      {e.label}
                    </option>
                  ))}
                </optgroup>
              ))}
            </select>
            {wf?.ref_naming?.license && <div className={s['ref-license']}>{wf.ref_naming.license}</div>}
          </div>
        )}
        {wf && <p className="muted small">{chosenModel(wf, form.options)?.about || wf.description}</p>}
        {wf?.options
          .filter((o) => o.top && offered(o, form.options) && !(wf.source === 'generation' && o.id === 'model'))
          .map((o) => (
            <div key={o.id} className="field">
              <div className="label">{o.label}</div>
              <Segmented
                choices={o.choices}
                current={form.options[o.id]}
                onPick={(id) => setForm((was) => ({ ...was, options: { ...was.options, [o.id]: String(id) } }))}
              />
              <div className="hint">{o.choices.find((c) => c.id === form.options[o.id])?.hint || ''}</div>
            </div>
          ))}
        <Source action={action} project={project} pick={pick} />
        {(!wf || byRole(wf, 'prompt')) && (
          <div className="field">
            <div className="label">Prompt</div>
            <textarea
              ref={prompt}
              rows={5}
              aria-label="Prompt"
              placeholder={PLACEHOLDER[form.kind] || 'Describe the shot'}
              value={action.text}
              onChange={(e) => action.setText(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) void action.generate();
              }}
            />
            <RefHint action={action} onToken={insertToken} />
          </div>
        )}
        {wf?.controls
          .filter((c) => c.primary && c.type === 'text' && !c.role)
          .map((c) => (
            <div key={c.id} className="field">
              <div className="label">{short(c.label)}</div>
              <textarea
                rows={5}
                aria-label={short(c.label)}
                placeholder={c.label}
                value={String(form.values[c.id] ?? '')}
                onChange={(e) => setForm((was) => ({ ...was, values: { ...was.values, [c.id]: e.target.value } }))}
              />
            </div>
          ))}
        {wf && (
          <KeepField
            kindMade={wf.id.split('/')[0]}
            inProject={!!project}
            onChange={action.setKeep}
            resetKey={action.kept}
          />
        )}
        <p className={cx('error notice', s.notice)}>{action.note}</p>
      </div>
      <div className={s['quick-foot']}>
        <Pills action={action} />
        <button
          className={cx('btn generate', s.generate)}
          title="Generate (Ctrl or ⌘ + Enter)"
          disabled={action.blocked}
          onClick={() => void action.generate()}
        >
          <span>{action.sending ? 'Sending…' : label}</span>
          <span className="cost">{quote ? quote.credits + ' cr' : ''}</span>
        </button>
      </div>
    </div>
  );
}

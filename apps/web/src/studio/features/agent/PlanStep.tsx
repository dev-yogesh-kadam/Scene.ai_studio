// One step of a plan waiting for approval (or one that was turned down), as a numbered row: its prompt on one line with
// edit and open beside it, and the assets it uses under it. Opened, the whole prompt, the step's settings as pills, why
// the agent chose them, and a way to leave it out.

import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { Icon } from '../../../common/components/Icon/Icon';
import { Still } from '../../../common/components/Still';
import { cx } from '../../../common/cx';
import { KIT } from '../../words';
import { changeStep, toggleSkip } from './actions';
import type { AgentChat } from './chat';
import { SoundPlayer } from './SoundPlayer';
import { Settings } from './StepSettings';
import { linksOf, tagsOf } from './shots';
import type { Run, Step } from './types';
import s from './PlanStep.module.css';
import { classesOf } from '../../../common/cx';
import css0 from '../../../common/components/Shared.module.css';
import css1 from '../../../common/components/Shared3.module.css';
const css = classesOf(css0, css1);

export function Tags({ step }: { step: Step }) {
  return (
    <div className={s['step-tags']}>
      {tagsOf(step).map((t) => (
        <span key={t}>{t}</span>
      ))}
    </div>
  );
}

/** A whole prompt, opened: each part of its structure (SCENE CONTEXT, ACTION, CAMERA…) on its own, its heading picked
 *  out. A prompt that does not follow the structure is shown as it is. */
function PromptSections({ prompt }: { prompt: string }) {
  const parts: { head: string; text: string }[] = [];
  for (const line of String(prompt || '').split('\n')) {
    const head = line.match(/^\s*([A-Z][A-Z &/]{2,40}):\s*(.*)$/);
    if (head) parts.push({ head: head[1], text: head[2] });
    else if (parts.length) parts[parts.length - 1].text += (parts[parts.length - 1].text ? '\n' : '') + line;
    else parts.push({ head: '', text: line });
  }
  return (
    <div className={s['prompt-sections']}>
      {parts
        .filter((p) => p.head || p.text.trim())
        .map((p, i) => (
          <div key={i} className={s['prompt-section']}>
            {p.head && <b>{p.head}</b>}
            <p>{p.text.trim()}</p>
          </div>
        ))}
    </div>
  );
}

type Shown = { url: string; kind: string; name: string; role: string; saved?: boolean };

/** A bigger look at an asset a step uses, while the pointer is on it. Fixed to the page, so the log does not cut it off. */
function UsePreview({ anchor, use }: { anchor: HTMLElement; use: Shown }) {
  const box = useRef<HTMLDivElement>(null);
  const place = () => {
    const node = box.current;
    if (!node) return;
    const r = anchor.getBoundingClientRect();
    const w = node.offsetWidth;
    const h = node.offsetHeight;
    node.style.left = Math.max(8, Math.min(window.innerWidth - w - 8, r.left)) + 'px';
    node.style.top = (r.top - h - 8 >= 8 ? r.top - h - 8 : Math.min(window.innerHeight - h - 8, r.bottom + 8)) + 'px';
  };
  useLayoutEffect(place);
  return createPortal(
    <div ref={box} className={s['use-preview']} role="tooltip">
      {use.kind === 'audio' ? (
        <SoundPlayer url={use.url} name={use.name} />
      ) : (
        <img
          src={use.kind === 'image' || use.saved ? use.url : use.url.replace(/\/file$/, '/poster')}
          alt={use.name}
          onLoad={place}
        />
      )}
      <div className={s['use-preview-words']}>
        <b>{use.name}</b>
        <span>{use.role}</span>
      </div>
    </div>,
    document.body,
  );
}

/** The assets a step uses as a row of small squares: the picture it starts on first, then the cast, places and props. */
function Refs({ step }: { step: Step }) {
  const [over, setOver] = useState<{ anchor: HTMLElement; use: Shown } | null>(null);
  const shown: Shown[] = [
    ...(step.start
      ? [{ url: `/api/library/${step.start.id}/file`, kind: 'image', name: step.start.name, role: 'first frame' }]
      : []),
    ...(step.uses || []).map((use) => ({
      url: use.asset ? `/api/kit/${use.asset}/file` : `/api/library/${use.id}/file`,
      kind: use.kind || 'image',
      name: use.name,
      role: use.label.toLowerCase().split(' (')[0] + (use.cast ? ' · cast' : ''),
      saved: !!use.asset,
    })),
  ];
  if (!shown.length) return null;
  return (
    <div className={s['approval-refs']}>
      {shown.map((u, i) => (
        <span
          key={i}
          className={cx(s['approval-ref'], u.kind === 'audio' && s.sound)}
          aria-label={`${u.name}: ${u.role}`}
          onMouseEnter={(e) => setOver({ anchor: e.currentTarget, use: u })}
          onMouseLeave={() => setOver(null)}
        >
          {u.kind === 'image' ? (
            <Still url={u.url} kind="image" name={u.name} />
          ) : u.kind === 'audio' ? (
            <Icon name="music" />
          ) : (
            <img src={u.saved ? u.url : u.url.replace(/\/file$/, '/poster')} alt={u.name} loading="lazy" />
          )}
        </span>
      ))}
      {over && <UsePreview anchor={over.anchor} use={over.use} />}
    </div>
  );
}

function PromptEdit({ chat, run, step, index }: { chat: AgentChat; run: Run; step: Step; index: number }) {
  const [text, setText] = useState(step.prompt ?? '');
  const box = useRef<HTMLTextAreaElement>(null);
  useEffect(() => box.current?.focus(), []);
  return (
    <div className={s['approval-edit']}>
      <textarea
        ref={box}
        className={s['agent-prompt-edit']}
        rows={Math.min(14, Math.max(6, String(step.prompt).split('\n').length + 2))}
        aria-label="Prompt"
        value={text}
        onChange={(e) => setText(e.target.value)}
      />
      <div className="row">
        <span style={{ flex: 1 }} />
        <button className="btn small quiet" onClick={() => chat.patch(step, { editing: false })}>
          Cancel
        </button>
        <button
          className="btn small primary"
          onClick={() => {
            chat.patch(step, { editing: false });
            if (text.trim() && text.trim() !== step.prompt) void changeStep(chat, run, index, { prompt: text.trim() });
          }}
        >
          Save
        </button>
      </div>
    </div>
  );
}

export function PlanStep({ chat, run, step }: { chat: AgentChat; run: Run; step: Step }) {
  const proposed = run.state === 'proposed';
  const index = run.steps.indexOf(step);
  const editable = proposed && !!step.settings && !step.updating;
  const links = linksOf(step);
  // Opened, the row is headed by the step's name, its whole prompt under it.
  const line = step.open ? step.name : step.prompt || [step.name, step.facts].filter(Boolean).join(' · ');
  const toggle = () => chat.patch(step, { open: !step.open });
  const needed = run.steps.some((x, i) => i !== index && !x.skipped && x.after && x.after.step === index);
  const label = step.open ? 'Show less' : 'Show the whole step';
  return (
    <li className={cx(s['approval-row'], step.skipped && s.skipped, step.open && s.open, step.updating && s.updating)}>
      <span className={s['approval-num']}>
        {step.updating ? <i className={css('cell-mark stepping')} /> : String(index + 1)}
      </span>
      <div className={s['approval-body']}>
        {step.editing ? (
          <PromptEdit chat={chat} run={run} step={step} index={index} />
        ) : (
          <div className={s['approval-line']}>
            <p className={s['approval-prompt']} title={step.open ? '' : step.name} onClick={toggle}>
              {line}
            </p>
            <span className={s['approval-tools']}>
              {editable && step.prompt && (
                <button
                  type="button"
                  className="icon-btn small"
                  title="Edit the prompt"
                  aria-label="Edit the prompt"
                  onClick={() => chat.patch(step, { editing: true, open: false })}
                >
                  <Icon name="pencil" />
                </button>
              )}
              <button
                type="button"
                className="icon-btn small"
                title={label}
                aria-label={label}
                aria-expanded={!!step.open}
                onClick={toggle}
              >
                <Icon name={step.open ? 'shrink' : 'expand'} />
              </button>
            </span>
          </div>
        )}
        {step.open && !step.editing && (
          <div className={s['approval-more']}>
            <div className={s['approval-name']}>
              {proposed && step.menu ? <Settings chat={chat} run={run} step={step} /> : <Tags step={step} />}
              {proposed && run.steps.length > 1 && (
                // Leave a shot out of the plan, or put it back. A shot that a later one starts on cannot be left out.
                <button
                  type="button"
                  className={cx('btn small quiet', s['step-skip'])}
                  disabled={needed || chat.working}
                  title={
                    needed
                      ? 'A later shot starts on this one'
                      : step.skipped
                        ? 'Put it back in the plan'
                        : 'Leave this shot out of the plan'
                  }
                  onClick={() => toggleSkip(chat, run, step)}
                >
                  {step.skipped ? 'Include' : 'Skip'}
                </button>
              )}
            </div>
            {step.prompt && (
              <div className={cx(s['agent-prompt'], s.open)}>
                <PromptSections prompt={step.prompt} />
              </div>
            )}
            {links.length > 0 && <div className={s['step-links']}>{links.join(' · ')}</div>}
            {step.keep && (
              <div className={s['step-keep']}>
                <Icon name="memory" />
                {`Kept in the ${KIT} as ${step.keep.tag === 'background' ? 'location' : step.keep.tag} “${step.keep.name}”`}
              </div>
            )}
            {/* Hindi or Hinglish words the video model would say wrong, as it is given them to say */}
            {step.phonetic && step.phonetic.length > 0 && (
              <div className={s['step-why']}>
                {'Said as: ' + step.phonetic.map((p) => `${p.word} → ${p.say}`).join(', ')}
              </div>
            )}
            {/* what the agent decided that the user did not say, and why */}
            {step.why && <div className={s['step-why']}>{step.why}</div>}
          </div>
        )}
        {step.skipped ? <span className={s['approval-left']}>Left out</span> : <Refs step={step} />}
        {step.error && <p className="small error">{'Not changed: ' + step.error}</p>}
      </div>
    </li>
  );
}

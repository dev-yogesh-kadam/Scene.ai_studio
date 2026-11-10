// The Quick actions tab of the canvas panel: pick what to make, then fill a short form for it. Images, videos and audio
// each open the same form, built from the workflows of that kind; an upscale takes the video selected on the canvas.
// Below them, motion graphics: whole videos of animated words, titles and overlays, rendered here.

import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { motionTemplates, type MotionTemplate } from '@scene/shared/api/make';
import { Icon, type IconName } from '../../../common/components/Icon/Icon';
import type { Item } from '../../../common/media/item';
import { ActionForm } from './ActionForm';
import { MotionForm } from './MotionForm';
import type { Pick } from './RefSlots';
import { NEW_SEQUENCE, SequenceForm, type Sequence } from './SequenceForm';
import { useActionForm, type Kind } from './useActionForm';
import s from './QuickActions.module.css';
import { classesOf } from '../../../common/cx';
import css0 from '../../../common/components/Shared3.module.css';
const css = classesOf(css0);

const ACTIONS: { id: Kind; label: string; icon: IconName }[] = [
  { id: 'image', label: 'Generate image', icon: 'image' },
  { id: 'video', label: 'Generate video', icon: 'video' },
  { id: 'audio', label: 'Generate audio', icon: 'audio' },
  { id: 'upscaler', label: 'Upscale video', icon: 'upscale' }, // takes the video selected on the canvas; no prompt
];

type Page =
  { at: 'home' } | { at: 'form'; kind: Kind } | { at: 'motion'; template: MotionTemplate } | { at: 'sequence' };

type Props = {
  project: number; // 0: all work
  startFrom: Item | null; // the one item selected on the canvas (not a sound)
  pick: Pick | null; // "From canvas" in a slot's + menu
  focus: number;
};

export function QuickActions({ project, startFrom, pick, focus }: Props) {
  const [page, setPage] = useState<Page>({ at: 'home' });
  const action = useActionForm({ project: project || null, startFrom });
  // the form of a whole motion video is kept, so its scenes are still there after a look at the other actions
  const [sequence, setSequence] = useState<Sequence>(NEW_SEQUENCE);
  const [about, setAbout] = useState('');
  const home = () => setPage({ at: 'home' });

  if (page.at === 'form')
    return (
      <ActionForm
        action={action}
        label={ACTIONS.find((a) => a.id === page.kind)!.label}
        project={project}
        pick={pick}
        focus={focus}
        onBack={home}
      />
    );
  if (page.at === 'motion')
    return <MotionForm template={page.template} source={startFrom} project={project || null} onBack={home} />;
  if (page.at === 'sequence')
    return (
      <SequenceForm
        state={sequence}
        setState={setSequence}
        about={about}
        setAbout={setAbout}
        project={project || null}
        onBack={home}
      />
    );
  return (
    <div className={s.quick}>
      <div className={s['quick-body']}>
        <h3>Create</h3>
        <p className="muted small">Make something new from a prompt and references.</p>
        <div className={s['quick-actions']}>
          {ACTIONS.map((a) => (
            <button
              key={a.id}
              className={s['quick-action']}
              onClick={() => {
                setPage({ at: 'form', kind: a.id });
                void action.open(a.id);
              }}
            >
              <Icon name={a.icon} />
              <b>{a.label}</b>
            </button>
          ))}
        </div>
        <h3 style={{ marginTop: 24 }}>Motion graphics</h3>
        <p className="muted small">
          Whole videos of animated words, titles and overlays, drawn and rendered here. Priced by the second.
        </p>
        <MotionCards
          onSequence={() => setPage({ at: 'sequence' })}
          onTemplate={(template) => setPage({ at: 'motion', template })}
        />
      </div>
    </div>
  );
}

function MotionCards({ onSequence, onTemplate }: { onSequence: () => void; onTemplate: (t: MotionTemplate) => void }) {
  const motion = useQuery({ queryKey: ['motion', 'templates'], queryFn: motionTemplates, staleTime: Infinity });
  if (motion.error) return <p className="error small">{motion.error.message}</p>;
  if (!motion.data) return <p className="muted small">Loading…</p>;
  const { ready, detail, templates } = motion.data;
  return (
    <div>
      {!ready && <p className="muted small">{detail}</p>}
      <div className={s['quick-actions']}>
        <button
          className={s['quick-action']}
          disabled={!ready}
          title="A whole video of animated words, written from what it is about"
          onClick={onSequence}
        >
          <Icon name="play" />
          <b>Motion video</b>
          <span className={css('slate-text')}>A whole video</span>
        </button>
        {templates.map((t) => (
          <button
            key={t.id}
            className={s['quick-action']}
            disabled={!ready}
            title={t.description}
            onClick={() => onTemplate(t)}
          >
            <Icon name={t.needs === 'video' ? 'video' : 'title'} />
            <b>{t.title}</b>
            <span className={css('slate-text')}>{t.needs === 'video' ? 'Over a video' : 'On its own'}</span>
          </button>
        ))}
      </div>
    </div>
  );
}

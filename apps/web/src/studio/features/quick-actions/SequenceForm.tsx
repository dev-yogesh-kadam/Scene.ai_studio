// A whole motion graphics video: say what it is about and the agent's model writes it as scenes (titles, statements,
// lists, figures, quotes), which can then be changed, moved, added to or written by hand. The scenes are kept while
// another action is looked at.

import { useState } from 'react';
import { writeScenes, type MotionScene } from '@scene/shared/api/make';
import { Icon } from '../../../common/components/Icon/Icon';
import { cx } from '../../../common/cx';
import { userPrefs } from '../../userPrefs';
import { Sending, useMotionCost, useRender } from './MotionForm';
import s from './QuickActions.module.css';
import { classesOf } from '../../../common/cx';
import css0 from '../../../common/components/Shared.module.css';
import css1 from '../../../common/components/Shared3.module.css';
import css2 from '../Shared.module.css';
const css = classesOf(css0, css1, css2);

// The kinds of scene a motion video is made of, and what each one's boxes are for. `first` is the box that comes first.
const SCENE_KINDS: { id: string; label: string; heading?: string; text?: string; items?: boolean; first?: string }[] = [
  { id: 'title', label: 'Title', heading: 'Heading', text: 'Line under it (optional)' },
  {
    id: 'statement',
    label: 'Statement',
    first: 'text',
    text: 'One sentence, shown large',
    heading: 'Small label above it (optional)',
  },
  { id: 'list', label: 'List', heading: 'Heading', items: true },
  { id: 'stat', label: 'Figure', heading: 'The figure, such as 42%', text: 'What it means' },
  { id: 'quote', label: 'Quote', first: 'text', text: 'The words', heading: 'Who said it (optional)' },
  { id: 'end', label: 'End', heading: 'Closing words', text: 'Line under it (optional)' },
];
const LOOKS = ['dark', 'light', 'warm', 'cool'];
const SHAPES = ['landscape', 'portrait', 'square'];
const MAX_SCENES = 12;
const capital = (text: string) => text[0].toUpperCase() + text.slice(1);

export type Sequence = { name: string; look: string; shape: string; scenes: MotionScene[] };
export const NEW_SEQUENCE: Sequence = { name: '', look: 'dark', shape: 'landscape', scenes: [] };

export function SequenceForm({
  state,
  setState,
  about,
  setAbout,
  project,
  onBack,
}: {
  state: Sequence;
  setState: (change: (was: Sequence) => Sequence) => void;
  about: string;
  setAbout: (text: string) => void;
  project: number | null;
  onBack: () => void;
}) {
  const [writing, setWriting] = useState(false);
  const render = useRender();
  const cost = useMotionCost({ scenes: state.scenes, look: state.look, shape: state.shape });
  const scenes = (change: (list: MotionScene[]) => MotionScene[]) =>
    setState((was) => ({ ...was, scenes: change([...was.scenes]) }));

  const write = async () => {
    render.setNote({ text: '', ok: false });
    const typed = about.trim();
    if (!typed) return render.setNote({ text: 'Say what the video is about first.', ok: false });
    if (writing) return;
    setWriting(true);
    try {
      const written = await writeScenes(typed, project, userPrefs.agent().model);
      setState(() => ({
        name: written.name,
        look: written.look,
        shape: written.shape,
        scenes: written.scenes.map((x) => ({ kind: x.kind, heading: x.heading, text: x.text, items: x.items })),
      }));
    } catch (e) {
      render.setNote({ text: (e as Error).message, ok: false });
    }
    setWriting(false);
  };

  const full = state.scenes.length >= MAX_SCENES;
  const pill = (name: string, key: 'look' | 'shape', choices: string[]) => (
    <select
      className={s.opt}
      title={name}
      aria-label={name}
      value={state[key]}
      onChange={(e) => setState((was) => ({ ...was, [key]: e.target.value }))}
    >
      {choices.map((c) => (
        <option key={c} value={c}>{`${name}: ${capital(c)}`}</option>
      ))}
    </select>
  );
  return (
    <div className={s.quick}>
      <div className={s['quick-head']}>
        <button className="icon-btn" title="Back to quick actions" aria-label="Back to quick actions" onClick={onBack}>
          <Icon name="back" />
        </button>
        <b>Motion video</b>
      </div>
      <div className={s['quick-body']}>
        <p className="muted small">
          A whole video of animated words: titles, statements, lists, figures and quotes, one scene after another.
        </p>
        <div className="field">
          <div className="label">
            About
            <span style={{ flex: 1 }} />
            <button
              type="button"
              className={css(cx('btn small agent', s.write))}
              disabled={writing}
              title={
                state.scenes.length
                  ? 'Have the scenes written again. This replaces the ones below.'
                  : 'Have the agent write the scenes of the video. Writing them costs nothing.'
              }
              onClick={() => void write()}
            >
              {writing ? (
                <>
                  <i className={css('cell-mark stepping')} />
                  Writing
                </>
              ) : state.scenes.length ? (
                'Write again'
              ) : (
                'Write scenes'
              )}
            </button>
          </div>
          <textarea
            rows={4}
            aria-label="What the video is about"
            placeholder="What is the video about? For example: a short intro for a coffee shop called Ember, warm and friendly"
            value={about}
            onChange={(e) => setAbout(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) void write();
            }}
          />
        </div>
        <div>
          {state.scenes.length ? (
            state.scenes.map((scene, i) => (
              <SceneCard key={i} scene={scene} i={i} count={state.scenes.length} scenes={scenes} />
            ))
          ) : (
            <p className="muted small" style={{ marginTop: 14 }}>
              No scenes yet. Have them written from what you typed above, or add them yourself.
            </p>
          )}
          <button
            type="button"
            className="btn small"
            style={{ marginTop: 10 }}
            disabled={full}
            title={full ? `A video has at most ${MAX_SCENES} scenes` : 'Add a scene at the end'}
            onClick={() =>
              scenes((list) => [
                ...list,
                { kind: list.length ? 'statement' : 'title', heading: '', text: '', items: [] },
              ])
            }
          >
            <Icon name="plus" />
            Add a scene
          </button>
        </div>
        <p className={cx(render.note.ok ? 'notice ok' : 'error notice', s.notice, render.note.ok && s.ok)}>
          {render.note.text}
        </p>
      </div>
      <div className={s['quick-foot']}>
        <div className={s['quick-pills']}>
          {pill('Look', 'look', LOOKS)}
          {pill('Shape', 'shape', SHAPES)}
        </div>
        <button
          className={cx('btn generate', s.generate)}
          disabled={!state.scenes.length || render.sending}
          onClick={() =>
            // the length of each scene is left to the server, which sets it from how much there is to read
            void render.send({
              scenes: state.scenes,
              look: state.look,
              shape: state.shape,
              name: state.name,
              project_id: project,
            })
          }
        >
          <span>{render.sending ? <Sending /> : 'Render'}</span>
          <span className="cost">{cost}</span>
        </button>
      </div>
    </div>
  );
}

function SceneCard({
  scene,
  i,
  count,
  scenes,
}: {
  scene: MotionScene;
  i: number;
  count: number;
  scenes: (change: (list: MotionScene[]) => MotionScene[]) => void;
}) {
  const kind = SCENE_KINDS.find((k) => k.id === scene.kind) ?? SCENE_KINDS[0];
  const set = (change: Partial<MotionScene>) =>
    scenes((list) => list.map((x, n) => (n === i ? { ...x, ...change } : x)));
  const move = (by: number) =>
    scenes((list) => {
      list.splice(i + by, 0, list.splice(i, 1)[0]);
      return list;
    });
  const box = (key: 'heading' | 'text', limit: number) =>
    kind[key] ? (
      <input
        key={key}
        type="text"
        maxLength={limit}
        placeholder={kind[key]}
        aria-label={kind[key]}
        value={scene[key]}
        onChange={(e) => set({ [key]: e.target.value })}
      />
    ) : null;
  return (
    <div className={s['scene-card']}>
      <div className={s['scene-top']}>
        <span className={css('slate-text')}>{i + 1}</span>
        <select
          className="small"
          aria-label="Kind of scene"
          value={scene.kind}
          onChange={(e) => set({ kind: e.target.value })}
        >
          {SCENE_KINDS.map((k) => (
            <option key={k.id} value={k.id}>
              {k.label}
            </option>
          ))}
        </select>
        <span style={{ flex: 1 }} />
        <button
          type="button"
          className="icon-btn"
          title="Move up"
          aria-label="Move up"
          disabled={i === 0}
          onClick={() => move(-1)}
        >
          ↑
        </button>
        <button
          type="button"
          className="icon-btn"
          title="Move down"
          aria-label="Move down"
          disabled={i === count - 1}
          onClick={() => move(1)}
        >
          ↓
        </button>
        <button
          type="button"
          className="icon-btn"
          title="Remove this scene"
          aria-label="Remove this scene"
          onClick={() => scenes((list) => list.filter((_, n) => n !== i))}
        >
          ×
        </button>
      </div>
      {kind.first === 'text' ? [box('text', 170), box('heading', 70)] : [box('heading', 70), box('text', 170)]}
      {kind.items && (
        <textarea
          rows={4}
          placeholder="One item on each line, up to 5"
          aria-label="Items"
          value={scene.items.join('\n')}
          onChange={(e) => set({ items: e.target.value.split('\n') })}
        />
      )}
    </div>
  );
}

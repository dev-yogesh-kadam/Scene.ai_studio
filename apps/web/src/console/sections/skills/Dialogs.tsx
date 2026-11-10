// The windows of the Skills section: a skill to make or change, and one the agent drafted in a chat, to publish.

import { useState } from 'react';
import { api } from '../../../common/api';
import { Field } from '../../../common/components/AuthForm';
import { Modal } from '../../../common/components/Dialog';
import { sure } from '../shared/ui';
import type { Skill } from './parseSkill';
import { classesOf } from '../../../common/cx';
import css0 from '../../../common/components/Shared2.module.css';
import css1 from '../../../common/components/Shared3.module.css';
import css2 from './Dialogs.module.css';
const css = classesOf(css0, css1, css2);

export type Draft = { id: string; title: string; desc: string; words: string; text: string; by_name?: string };
const path = (id: string) => '/api/admin/skills/' + encodeURIComponent(id);
const message = (e: unknown) => (e as Error).message;

/** A modal to make a new skill or change one. `imported`: the skill comes from a file, so it is saved as a new one (or
 *  over the skill that has its id). */
export function Editor({
  skill,
  imported = false,
  ids = [],
  onSaved,
  onClose,
}: {
  skill: Skill | null;
  imported?: boolean;
  ids?: string[];
  onSaved: () => void;
  onClose: () => void;
}) {
  const isNew = !skill || imported;
  const [id, setId] = useState(skill?.id ?? '');
  const [title, setTitle] = useState(skill?.title ?? '');
  const [desc, setDesc] = useState(skill?.desc ?? '');
  const [version, setVersion] = useState(skill?.version ?? '1');
  const [words, setWords] = useState(skill?.words ?? '');
  const [text, setText] = useState(skill?.text ?? '');
  const [error, setError] = useState('');
  const save = async () => {
    const payload = { id: id.trim(), title, desc, version, words, text };
    try {
      if (isNew && !ids.includes(payload.id)) await api('/api/admin/skills', { method: 'POST', json: payload });
      else if (imported) await api(path(payload.id), { method: 'PUT', json: payload });
      else await api(path(skill?.id ?? ''), { method: 'PUT', json: payload });
      onClose();
      onSaved();
    } catch (e) {
      setError(message(e));
    }
  };
  return (
    <Modal className={css('skill-editor')} onClose={onClose}>
      <h2>{imported ? 'Skill from a file' : isNew ? 'New skill' : 'Edit skill'}</h2>
      {imported && skill && (
        <p className="notice">
          {ids.includes(skill.id)
            ? `A skill with the id “${skill.id}” exists: saving replaces it.`
            : 'Look it over, add trigger words if the file had none, and save.'}
        </p>
      )}
      <p className="muted small" style={{ marginBottom: 14 }}>
        The id is the /command and the file name. Trigger words are a regular expression; the skill is given to the
        agent when a message matches them.
      </p>
      <Field label="Id">
        <input
          type="text"
          value={id}
          placeholder="short-film"
          spellCheck={false}
          disabled={!isNew}
          onChange={(e) => setId(e.target.value)}
        />
      </Field>
      <Field label="Title">
        <input type="text" value={title} onChange={(e) => setTitle(e.target.value)} />
      </Field>
      <Field label="Description">
        <input
          type="text"
          value={desc}
          placeholder="Use when… (one line, shown in the picker)"
          onChange={(e) => setDesc(e.target.value)}
        />
      </Field>
      <Field label="Trigger words (regular expression)">
        <input
          type="text"
          value={words}
          spellCheck={false}
          placeholder="\b(film|story|scene)\b"
          onChange={(e) => setWords(e.target.value)}
        />
      </Field>
      <Field label="Version">
        <input type="text" value={version} onChange={(e) => setVersion(e.target.value)} />
      </Field>
      <Field label="Steps the agent follows">
        <textarea rows={14} spellCheck={false} value={text} onChange={(e) => setText(e.target.value)} />
      </Field>
      <p className={'notice' + (error ? ' error' : '')}>{error}</p>
      <div className={css('dialog-buttons')}>
        <button type="button" className="btn" onClick={onClose}>
          Cancel
        </button>
        <button type="button" className="btn primary" onClick={() => void save()}>
          Save
        </button>
      </div>
    </Modal>
  );
}

/** A skill drafted in a chat ("make this a skill"): look it over, change what needs it, then publish it (admins only)
 *  or throw it away. Until it is published the agent never reads it. */
export function DraftReview({
  draft,
  canPublish,
  onDone,
  onClose,
}: {
  draft: Draft;
  canPublish: boolean;
  onDone: () => void;
  onClose: () => void;
}) {
  const [title, setTitle] = useState(draft.title);
  const [desc, setDesc] = useState(draft.desc);
  const [words, setWords] = useState(draft.words);
  const [text, setText] = useState(draft.text);
  const [error, setError] = useState('');
  const finish = async (work: Promise<unknown>) => {
    try {
      await work;
      onClose();
      onDone();
    } catch (e) {
      setError(message(e));
    }
  };
  const draftPath = '/api/admin/skills/drafts/' + encodeURIComponent(draft.id);
  return (
    <Modal className={css('skill-editor')} onClose={onClose}>
      <h2>Drafted skill</h2>
      <p className="muted small" style={{ marginBottom: 14 }}>
        {`Drafted in a chat${draft.by_name ? ' by ' + draft.by_name : ''}. It becomes /${draft.id} once published. Trigger words are optional.`}
      </p>
      <Field label="Title">
        <input type="text" value={title} onChange={(e) => setTitle(e.target.value)} />
      </Field>
      <Field label="Description">
        <input
          type="text"
          value={desc}
          placeholder="Use when… (one line, shown in the picker)"
          onChange={(e) => setDesc(e.target.value)}
        />
      </Field>
      <Field label="Trigger words (regular expression)">
        <input
          type="text"
          value={words}
          spellCheck={false}
          placeholder={'\b(film|story|scene)\b'}
          onChange={(e) => setWords(e.target.value)}
        />
      </Field>
      <Field label="Steps the agent follows">
        <textarea rows={14} spellCheck={false} value={text} onChange={(e) => setText(e.target.value)} />
      </Field>
      <p className={'notice' + (error ? ' error' : '')}>{error}</p>
      <div className={css('dialog-buttons')}>
        <button
          type="button"
          className="btn danger"
          onClick={() => {
            void sure(`Throw away the draft “${draft.title}”?`).then((yes) => {
              if (yes) void finish(api(draftPath, { method: 'DELETE' }));
            });
          }}
        >
          Discard
        </button>
        <button type="button" className="btn" onClick={onClose}>
          Cancel
        </button>
        {canPublish && (
          <button
            type="button"
            className="btn primary"
            onClick={() =>
              void finish(api(draftPath + '/publish', { method: 'POST', json: { title, desc, words, text } }))
            }
          >
            Publish
          </button>
        )}
      </div>
    </Modal>
  );
}

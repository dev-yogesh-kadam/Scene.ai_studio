// The project window: name a new project, or rename one.

import { useEffect, useRef, useState } from 'react';
import type { ProjectRow } from '@scene/shared/types/api';
import { api } from '../../../common/api';
import { Field } from '../../../common/components/AuthForm';
import { openDialog } from '../../../common/components/Dialog';
import { classesOf } from '../../../common/cx';
import css0 from '../../../common/components/Shared2.module.css';
import css1 from '../../../common/components/Shared3.module.css';
import css2 from './projectDialog.module.css';
const css = classesOf(css0, css1, css2);

type Named = { id: number; name: string; [key: string]: unknown };

/** project: the one to rename; leave it out to create a new one. parent: make a module inside that project instead
 *  (count: how many modules it has, for the default name); module: the one renamed is a module; canvas: rename a
 *  project's own canvas (the "Main canvas" module), not the project. Resolves to the saved project or module, or null. */
export function projectDialog({
  project,
  parent = null,
  count = 0,
  module = false,
  canvas = false,
}: { project?: Named; parent?: Named | null; count?: number; module?: boolean; canvas?: boolean } = {}) {
  const isModule = module || !!parent;
  return openDialog<ProjectRow>(
    (close) => (
      <ProjectForm project={project} parent={parent} count={count} module={isModule} canvas={canvas} close={close} />
    ),
    { className: css('project-dialog') },
  );
}

function ProjectForm({
  project,
  parent,
  count,
  module,
  canvas,
  close,
}: {
  project?: Named;
  parent: Named | null;
  count: number;
  module: boolean;
  canvas: boolean;
  close: (saved?: ProjectRow | null) => void;
}) {
  const today = new Date().toLocaleDateString([], { day: 'numeric', month: 'short' });
  const [name, setName] = useState(project ? project.name : parent ? 'Module ' + (count + 1) : 'Project ' + today);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  useEffect(() => {
    input.current?.select();
    // While a request is running the window cannot be closed, so its result is never lost.
    const dialog = input.current?.closest('dialog');
    const hold = (e: Event) => {
      if (input.current?.form?.dataset.busy) e.preventDefault();
    };
    dialog?.addEventListener('cancel', hold);
    return () => dialog?.removeEventListener('cancel', hold);
  }, []);

  return (
    <form
      method="dialog"
      data-busy={busy ? '1' : undefined}
      onSubmit={(e) => {
        e.preventDefault();
        setBusy(true);
        const save = project
          ? api('/api/projects/' + project.id + (canvas ? '/canvas' : ''), { method: 'PUT', json: { name } }).then(
              () => ({ ...project, name: name.trim() }) as ProjectRow,
            )
          : api<ProjectRow>('/api/projects', { method: 'POST', json: { name, parent_id: parent ? parent.id : null } });
        save.then(close, (err: Error) => {
          setError(err.message);
          setBusy(false);
        });
      }}
    >
      <h2>
        {project
          ? canvas
            ? 'Rename canvas'
            : module
              ? 'Rename module'
              : 'Rename project'
          : module
            ? `New module in ${parent?.name}`
            : 'New project'}
      </h2>
      <p className="muted">
        {project
          ? 'Its items and canvas stay as they are.'
          : module
            ? "A module is a canvas of its own, with its own agent tabs, using the project's NeuralCore."
            : 'A project keeps the shots and the canvas of one piece of work together.'}
      </p>
      <Field label="Name">
        <input ref={input} type="text" maxLength={60} required value={name} onChange={(e) => setName(e.target.value)} />
      </Field>
      <p className="error notice">{error}</p>
      <div className={css('dialog-buttons')}>
        <button className="btn" type="button" disabled={busy} onClick={() => close()}>
          Cancel
        </button>
        <button className="btn primary" type="submit" disabled={busy}>
          {project ? 'Save' : module ? 'Create module' : 'Create project'}
        </button>
      </div>
    </form>
  );
}

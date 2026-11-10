// The studio's own windows, in place of the browser's grey confirm() and alert() boxes (R4): built on <dialog>, so focus
// stays inside while it is open and Escape closes it.

import { useEffect, useLayoutEffect, useRef, useState, type ReactNode } from 'react';
import { markBusy } from '../busy';
import { showOverlay } from './OverlayHost';
import { classesOf } from '../cx';
import css0 from './Dialog.module.css';
import css1 from './Shared2.module.css';
import css2 from './Shared3.module.css';
const css = classesOf(css0, css1, css2);

export type Question = {
  title: string;
  message?: ReactNode;
  confirm?: string;
  cancel?: string | null; // null: only the confirming button (a notice)
  danger?: boolean;
};

/** A question before something that can't be undone. Resolves true for the confirming button, false for Cancel,
 *  Escape or a click beside it: ask({ title, message, confirm: 'Delete', danger: true }). */
export function ask(question: Question): Promise<boolean> {
  return new Promise((resolve) => {
    const take = showOverlay(
      <AskDialog
        {...question}
        onDone={(answer) => {
          resolve(answer);
          take();
        }}
      />,
    );
  });
}

/** A window of its own, shown at once: `render(close)` draws what is in it, and close(value) closes it with that
 *  answer. Resolves with the answer, or null when it is closed by Escape or without one. */
export function openDialog<T>(
  render: (close: (value?: T | null) => void) => ReactNode,
  { className = '', label }: { className?: string; label?: string } = {},
): Promise<T | null> {
  return new Promise((resolve) => {
    const take = showOverlay(
      <OwnDialog
        render={render}
        className={className}
        label={label}
        onDone={(answer: T | null) => {
          resolve(answer);
          take();
        }}
      />,
    );
  });
}

function OwnDialog<T>({
  render,
  className,
  label,
  onDone,
}: {
  render: (close: (value?: T | null) => void) => ReactNode;
  className: string;
  label?: string;
  onDone: (answer: T | null) => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const answer = useRef<T | null>(null);
  const [close] = useState(() => (value?: T | null) => {
    answer.current = value ?? null;
    dialog.current?.close();
  });
  const done = useRef(onDone);
  useLayoutEffect(() => {
    done.current = onDone;
  });
  useEffect(() => {
    const node = dialog.current;
    if (!node) return;
    node.showModal();
    const free = markBusy();
    const closed = () => done.current(answer.current);
    node.addEventListener('close', closed);
    return () => {
      free();
      node.removeEventListener('close', closed);
      if (node.open) node.close();
    };
  }, []);
  return (
    <dialog ref={dialog} className={className || undefined} aria-label={label}>
      {render(close)}
    </dialog>
  );
}

/** A line of text asked for, in place of prompt(): resolves with what was typed (trimmed), or null when cancelled or
 *  left empty. askText({ title: 'Project name', value: 'Old name', confirm: 'Rename' }) */
export function askText({
  title,
  value = '',
  confirm = 'OK',
  placeholder = '',
  maxLength = 120,
}: {
  title: string;
  value?: string;
  confirm?: string;
  placeholder?: string;
  maxLength?: number;
}) {
  return openDialog<string>(
    (close) => (
      <form
        method="dialog"
        onSubmit={(e) => {
          e.preventDefault();
          const typed = String(new FormData(e.currentTarget).get('text') ?? '').trim();
          close(typed || null);
        }}
      >
        <h2>{title}</h2>
        <input name="text" type="text" defaultValue={value} placeholder={placeholder} maxLength={maxLength} autoFocus />
        <div className={css('dialog-buttons')}>
          <button type="button" className="btn" onClick={() => close()}>
            Cancel
          </button>
          <button type="submit" className="btn primary">
            {confirm}
          </button>
        </div>
      </form>
    ),
    { className: css('ask-dialog'), label: title },
  );
}

/** A notice with one button, in place of alert(). */
export function tell(title: string, message?: ReactNode) {
  return ask({ title, message, confirm: 'OK', cancel: null }).then(() => undefined);
}

function AskDialog({
  title,
  message,
  confirm = 'OK',
  cancel = 'Cancel',
  danger = false,
  onDone,
}: Question & { onDone: (answer: boolean) => void }) {
  const dialog = useRef<HTMLDialogElement>(null);
  const yes = useRef<HTMLButtonElement>(null);
  const no = useRef<HTMLButtonElement>(null);
  const answer = useRef(false);

  useEffect(() => {
    const node = dialog.current;
    if (!node) return;
    node.showModal();
    (danger || !yes.current ? no.current : yes.current)?.focus(); // Enter on a dangerous question does nothing harmful
    const free = markBusy();
    const closed = () => onDone(answer.current);
    node.addEventListener('close', closed);
    return () => {
      free();
      node.removeEventListener('close', closed);
      if (node.open) node.close();
    };
  }, [danger, onDone]);

  return (
    <dialog
      ref={dialog}
      className={css('ask-dialog' + (danger ? ' danger' : ''))}
      aria-label={title}
      onClick={(e) => {
        if (e.target === dialog.current) dialog.current?.close(); // a click beside it
      }}
    >
      <h2>{title}</h2>
      {message ? <p className={css('ask-message')}>{message}</p> : null}
      <div className={css('dialog-buttons')}>
        {cancel !== null && (
          <button ref={no} className="btn" onClick={() => dialog.current?.close()}>
            {cancel}
          </button>
        )}
        <button
          ref={yes}
          className={'btn ' + (danger ? 'danger-solid' : 'primary')}
          onClick={() => {
            answer.current = true;
            dialog.current?.close();
          }}
        >
          {confirm}
        </button>
      </div>
    </dialog>
  );
}

/** A dialog of its own, shown while it is mounted. onClose fires on Escape or close(). */
export function Modal({
  children,
  onClose,
  className,
  label,
}: {
  children: ReactNode;
  onClose: () => void;
  className?: string;
  label?: string;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const close = useRef(onClose);
  useEffect(() => {
    close.current = onClose;
  }, [onClose]);
  useEffect(() => {
    const node = dialog.current;
    if (!node) return;
    node.showModal();
    const free = markBusy();
    const closed = () => close.current();
    node.addEventListener('close', closed);
    return () => {
      free();
      node.removeEventListener('close', closed);
      if (node.open) node.close();
    };
  }, []);
  return (
    <dialog ref={dialog} className={className} aria-label={label}>
      {children}
    </dialog>
  );
}

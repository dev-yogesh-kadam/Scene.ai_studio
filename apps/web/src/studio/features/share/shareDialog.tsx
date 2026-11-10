// Sharing a project: add people by email with a role, and see, change or remove who is in it. Opened from the project's
// page and from its canvas. The server decides what each role may do (sharing.py); this only offers what the user's
// own role lets them change.

import { Fragment, useEffect, useRef, useState, type ReactNode } from 'react';
import { api } from '../../../common/api';
import { ask, openDialog } from '../../../common/components/Dialog';
import { Icon } from '../../../common/components/Icon/Icon';
import { initials } from '../../../common/format';
import { classesOf } from '../../../common/cx';
import css0 from '../../../common/components/Shared2.module.css';
import css1 from '../../../common/components/Shared3.module.css';
import css2 from '../../../common/components/Shared4.module.css';
import css3 from './shareDialog.module.css';
const css = classesOf(css0, css1, css2, css3);

const EMAIL = /[^\s,;<>()"']+@[^\s,;<>()"']+\.[^\s,;<>()"']+/g;
const RANK: Record<string, number> = { viewer: 1, creator: 2, manager: 3, owner: 4 };

type Role = { id: string; label: string; about?: string };
type Member = { user_id: number; name: string; email: string; role: string };
type Info = { members: Member[]; roles: Role[]; role: string | null };
type Pending = { email: string; role: string };

/** Resolves true when anyone was added, changed or removed, so the page can show the new list. */
export function shareDialog({ projectId, projectName, me }: { projectId: number; projectName: string; me: number }) {
  return openDialog<boolean>(
    (close) => <Share projectId={projectId} projectName={projectName} me={me} close={close} />,
    { className: css('share-dialog'), label: 'People in ' + projectName },
  ).then((changed) => !!changed);
}

function Share({
  projectId,
  projectName,
  me,
  close,
}: {
  projectId: number;
  projectName: string;
  me: number;
  close: (changed?: boolean | null) => void;
}) {
  const [info, setInfo] = useState<Info>({ members: [], roles: [], role: null }); // role: the user's own, once known
  const [pending, setPending] = useState<Pending[]>([]); // typed or pasted, not added yet
  const [typed, setTyped] = useState('');
  const [error, setError] = useState<ReactNode>('');
  const [busy, setBusy] = useState(false);
  const [changed, setChanged] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  const changedNow = useRef(false); // for the click beside the window, which is heard outside React
  useEffect(() => {
    changedNow.current = changed;
  }, [changed]);

  useEffect(() => {
    input.current?.focus();
    // A click beside the window closes it, as a click outside a smaller dialog would.
    const dialog = input.current?.closest('dialog');
    const beside = (e: MouseEvent) => {
      if (e.target === dialog) close(changedNow.current);
    };
    dialog?.addEventListener('click', beside);
    api<Info>(`/api/projects/${projectId}/members`).then(setInfo, (e: Error) => setError(e.message));
    return () => dialog?.removeEventListener('click', beside);
  }, [projectId, close]);

  const mayManage = info.role != null && RANK[info.role] >= RANK.manager;
  const givable = info.roles.filter((r) => r.id !== 'manager' || info.role === 'owner'); // only the owner makes managers
  const looker = !!info.role && !mayManage; // only seeing who is in it: nothing to add (shown until that is known)

  const take = (text: string) => {
    const found = (text.match(EMAIL) || []).map((e) => e.toLowerCase().replace(/[.]+$/, ''));
    EMAIL.lastIndex = 0;
    if (!found.length) {
      setError(`"${text.trim()}" is not an email address.`);
      return pending;
    }
    setError('');
    const next = [...pending];
    for (const email of found) if (!next.some((p) => p.email === email)) next.push({ email, role: 'creator' });
    setPending(next);
    setTyped('');
    return next;
  };

  const add = async () => {
    const people = typed.trim() ? take(typed) : pending;
    if (!people.length) return;
    setBusy(true);
    try {
      const found = await api<{ members: Member[]; added: unknown[]; problems: { email: string; problem: string }[] }>(
        `/api/projects/${projectId}/members`,
        { method: 'POST', json: { people } },
      );
      setInfo((i) => ({ ...i, members: found.members }));
      if (found.added.length) setChanged(true);
      setPending(people.filter((p) => found.problems.some((x) => x.email === p.email))); // what could not be added stays
      setError(
        <>
          {found.problems.map((x) => (
            <div key={x.email}>{`${x.email}: ${x.problem}`}</div>
          ))}
        </>,
      );
    } catch (e) {
      setError((e as Error).message);
    }
    setBusy(false);
  };

  const change = async (member: Member, role: string) => {
    try {
      const done = await api<{ members: Member[] }>(`/api/projects/${projectId}/members/${member.user_id}`, {
        method: 'PUT',
        json: { role },
      });
      setInfo((i) => ({ ...i, members: done.members }));
      setChanged(true);
    } catch (e) {
      setError((e as Error).message);
    }
  };

  const remove = async (member: Member, leaving = false) => {
    const sure = await ask(
      leaving
        ? {
            title: `Leave ${projectName}?`,
            message: 'What you made there stays in the project. Its owner can add you again.',
            confirm: 'Leave',
            danger: true,
          }
        : {
            title: `Remove ${member.name}?`,
            message: 'They no longer see the project. What they made there stays in it.',
            confirm: 'Remove',
            danger: true,
          },
    );
    if (!sure) return;
    try {
      const done = await api<{ members: Member[] }>(`/api/projects/${projectId}/members/${member.user_id}`, {
        method: 'DELETE',
      });
      setChanged(true);
      if (leaving) return close(true);
      setInfo((i) => ({ ...i, members: done.members }));
    } catch (e) {
      setError((e as Error).message);
    }
  };

  const roleSelect = (current: string, onPick: (role: string) => void) => {
    const choices = givable.length ? givable : [{ id: 'creator', label: 'Creator' }];
    return (
      <select
        className={css('small share-role')}
        aria-label="Role"
        title={choices.find((r) => r.id === current)?.about || ''}
        value={current}
        onChange={(e) => onPick(e.target.value)}
      >
        {choices.map((r) => (
          <option key={r.id} value={r.id} title={r.about}>
            {r.label}
          </option>
        ))}
      </select>
    );
  };

  return (
    <>
      <div className={css('share-head')}>
        <h2>{'Add to ' + projectName}</h2>
        <button className="icon-btn" type="button" aria-label="Close" onClick={() => close(changed)}>
          ×
        </button>
      </div>
      <div className={css('share-adder' + (looker ? ' hidden' : ''))}>
        <label className="label">Email address(es)</label>
        <input
          ref={input}
          type="text"
          placeholder="Type or paste email addresses"
          autoComplete="off"
          aria-label="Email addresses"
          value={typed}
          onChange={(e) => setTyped(e.target.value)}
          onKeyDown={(e) => {
            if (['Enter', ',', ';', ' '].includes(e.key) && typed.trim()) {
              e.preventDefault();
              take(typed);
            } else if (e.key === 'Backspace' && !typed && pending.length) setPending(pending.slice(0, -1));
          }}
          onPaste={(e) => {
            const text = e.clipboardData.getData('text');
            if (EMAIL.test(text)) {
              e.preventDefault();
              take(text);
            }
            EMAIL.lastIndex = 0;
          }}
          onBlur={() => typed.trim() && take(typed)}
        />
        <div className={css('share-pending')}>
          {pending.length > 0 && (
            <div className="muted small">{pending.length === 1 ? '1 person' : `${pending.length} people`}</div>
          )}
          {pending.map((p) => (
            <div key={p.email} className={css('share-row')}>
              <span className={css('share-email grow')}>{p.email}</span>
              {roleSelect(p.role, (role) => setPending(pending.map((x) => (x === p ? { ...x, role } : x))))}
              <button
                className="icon-btn"
                type="button"
                aria-label={'Remove ' + p.email}
                onClick={() => setPending(pending.filter((x) => x !== p))}
              >
                ×
              </button>
            </div>
          ))}
        </div>
        <p className={css('share-note muted small')}>
          {'Selected people get added to the whole project '}
          <b>{projectName}</b>
          {', all its modules included. They need an account here.'}
        </p>
      </div>
      <div className="error notice">{error}</div>
      <div className={css('dialog-buttons')}>
        <button className="btn" type="button" onClick={() => close(changed)}>
          Cancel
        </button>
        <button
          className={'btn primary' + (looker ? ' hidden' : '')}
          type="button"
          disabled={busy || (!pending.length && !typed.trim())}
          onClick={() => void add()}
        >
          {pending.length > 1 ? `Add ${pending.length} people` : 'Add'}
        </button>
      </div>
      <h3 className={css('share-sub')}>In this project</h3>
      <div className={css('share-people')}>
        {info.members.map((m) => {
          const self = m.user_id === me;
          const canChange = mayManage && m.role !== 'owner' && !self && (info.role === 'owner' || m.role !== 'manager');
          const label = (info.roles.find((r) => r.id === m.role) || { label: 'Owner' }).label;
          return (
            <Fragment key={m.user_id}>
              <div className={css('share-row member')}>
                <span className={css('share-avatar')} aria-hidden="true">
                  {initials(m.name || m.email)}
                </span>
                <span className={css('grow share-who')}>
                  <b>{m.name + (self ? ' (you)' : '')}</b>
                  <span className="muted small">{m.email}</span>
                </span>
                {canChange ? (
                  roleSelect(m.role, (role) => void change(m, role))
                ) : (
                  <span className={css('share-badge' + (m.role === 'owner' ? ' owner' : ''))}>{label}</span>
                )}
                {canChange && (
                  <button
                    className="icon-btn"
                    type="button"
                    title="Remove from the project"
                    aria-label={'Remove ' + m.email}
                    onClick={() => void remove(m)}
                  >
                    <Icon name="trash" />
                  </button>
                )}
                {self && m.role !== 'owner' && (
                  <button className="btn small quiet" type="button" onClick={() => void remove(m, true)}>
                    Leave
                  </button>
                )}
              </div>
            </Fragment>
          );
        })}
      </div>
    </>
  );
}

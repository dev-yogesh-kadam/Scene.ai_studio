// The console's Roles section: the staff roles, what each may see and change in the console, and how many people have
// each. An admin changes a role, makes a new one or deletes one no one has. See backend/scene/staff.py.

import { useState } from 'react';
import { api } from '../../../common/api';
import { Field } from '../../../common/components/AuthForm';
import { useConsole, useNotice, useSection } from '../shared/context';
import { Loaded, Notice, number, sure } from '../shared/ui';
import { classesOf } from '../../../common/cx';
import css0 from '../../../common/components/Shared.module.css';
import css1 from '../../../common/components/Shared2.module.css';
import css2 from '../../../common/components/Shared3.module.css';
import css3 from './Roles.module.css';
import css4 from '../shared/Console.module.css';
import css5 from '../../../studio/pages/create/CreatePage.module.css';
const css = classesOf(css0, css1, css2, css3, css4, css5);

type Area = { id: string; label: string };
type Role = {
  id: string;
  label: string;
  about: string;
  read: string[];
  write: string[];
  built_in: boolean;
  fixed: boolean;
  people: number;
};

const FRESH: Role = {
  id: '',
  label: '',
  about: '',
  read: ['overview'],
  write: [],
  built_in: false,
  fixed: false,
  people: 0,
};

/** One role: its name and what it is for, then a row per area of the console: See, and Change (which needs See). */
function RoleCard({ role, areas }: { role: Role; areas: Area[] }) {
  const { refresh } = useConsole();
  const { notice, run } = useNotice();
  const [label, setLabel] = useState(role.label);
  const [about, setAbout] = useState(role.about);
  const [read, setRead] = useState(role.read);
  const [write, setWrite] = useState(role.write);
  const save = () =>
    run(async () => {
      await api('/api/admin/roles/' + (role.id || 'new'), { method: 'PUT', json: { label, about, read, write } });
      await refresh();
    });
  const remove = async () => {
    if (
      !(await sure(
        `Delete the role "${role.label}"?${role.built_in ? ' It is one the console comes with; it comes back only if you make it again.' : ''}`,
      ))
    )
      return;
    await run(async () => {
      await api('/api/admin/roles/' + role.id, { method: 'DELETE' });
      await refresh();
    });
  };
  return (
    <details className={css('card role-card')}>
      <summary className={css('card-head')}>
        <h2>{role.id ? role.label : 'New role'}</h2>
        {role.id && (
          <span className="muted small">{`${number(role.people)} ${role.people === 1 ? 'person' : 'people'}`}</span>
        )}
        {role.built_in && !role.fixed && <span className={css('pill')}>Built in</span>}
        {role.fixed && <span className={css('pill')}>Can&apos;t be changed</span>}
      </summary>
      <p className="muted small">
        {role.fixed
          ? role.about
          : 'What people with this role see in the console, and what they may change there. Roles and Settings are for admins only.'}
      </p>
      {!role.fixed && (
        <>
          <div className={css('grid2')}>
            <Field label="Name">
              <input type="text" value={label} maxLength={40} onChange={(e) => setLabel(e.target.value)} />
            </Field>
            <Field label="What it is for">
              <textarea rows={2} maxLength={300} value={about} onChange={(e) => setAbout(e.target.value)} />
            </Field>
          </div>
          <div className={css('role-grid')}>
            <span className="muted small">Area</span>
            <span className="muted small">See</span>
            <span className="muted small">Change</span>
            {areas.map((a) => (
              <RoleRow
                key={a.id}
                area={a}
                see={read.includes(a.id)}
                change={write.includes(a.id)}
                onSee={(on) => {
                  setRead((was) => (on ? [...was, a.id] : was.filter((x) => x !== a.id)));
                  if (!on) setWrite((was) => was.filter((x) => x !== a.id));
                }}
                onChange={(on) => {
                  setWrite((was) => (on ? [...was, a.id] : was.filter((x) => x !== a.id)));
                  if (on) setRead((was) => (was.includes(a.id) ? was : [...was, a.id]));
                }}
              />
            ))}
          </div>
        </>
      )}
      <Notice notice={notice} />
      {!role.fixed && (
        <div className="row" style={{ marginTop: 12 }}>
          <button className="btn primary" onClick={() => void save()}>
            {role.id ? 'Save' : 'Make the role'}
          </button>
          {role.id && (
            <button
              className="btn quiet danger"
              disabled={role.people > 0}
              title={role.people ? 'Give its people another role first' : ''}
              onClick={() => void remove()}
            >
              Delete
            </button>
          )}
        </div>
      )}
    </details>
  );
}

function RoleRow({
  area,
  see,
  change,
  onSee,
  onChange,
}: {
  area: Area;
  see: boolean;
  change: boolean;
  onSee: (on: boolean) => void;
  onChange: (on: boolean) => void;
}) {
  return (
    <>
      <span>{area.label}</span>
      <input type="checkbox" checked={see} aria-label={'See ' + area.label} onChange={(e) => onSee(e.target.checked)} />
      <input
        type="checkbox"
        checked={change}
        aria-label={'Change ' + area.label}
        onChange={(e) => onChange(e.target.checked)}
      />
    </>
  );
}

export default function Roles() {
  const query = useSection('roles', [], () => api<{ roles: Role[]; areas: Area[] }>('/api/admin/roles'));
  return (
    <Loaded query={query}>
      {(d) => (
        <>
          <p className="muted">
            Give your team the parts of the console their work needs. People get a role on the Users page.
          </p>
          {d.roles.map((r) => (
            <RoleCard key={r.id + JSON.stringify([r.read, r.write, r.label])} role={r} areas={d.areas} />
          ))}
          <RoleCard key={'new' + d.roles.length} role={FRESH} areas={d.areas} />
        </>
      )}
    </Loaded>
  );
}

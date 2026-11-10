// The console's Users section: everyone with an account, by name or email, and the drawer of one person.

import { useState } from 'react';
import { api } from '../../../common/api';
import { Segmented } from '../../../common/components/Segmented';
import { CreditsDialog } from '../credits/CreditsDialog';
import { useConsole, useFilters, useSection } from '../shared/context';
import { ExportLink, Loaded, SearchBox, Table, ago, number } from '../shared/ui';
import { UserDrawer, type StaffRole } from './UserDrawer';
import { allUsers } from './allUsers';
import { classesOf } from '../../../common/cx';
import css0 from '../../../common/components/Shared2.module.css';
import css1 from '../../../common/components/Shared3.module.css';
import css2 from '../shared/Console.module.css';
const css = classesOf(css0, css1, css2);

export type UserRow = {
  id: number;
  name: string;
  email: string;
  role: string;
  credits: number;
  spent: number;
  generations: number;
  jobs: number;
  last_job: number | null;
  created: number;
  disabled: number | boolean;
};

export default function Users() {
  const { user, refresh } = useConsole();
  const [s, set] = useFilters<{ q: string; show: string }>('users');
  const [open, setOpen] = useState<number | null>(null);
  const [giving, setGiving] = useState<UserRow | null>(null);
  const query = useSection('users', [s.q, s.show], async () => {
    const list = await allUsers<UserRow>({ q: s.q, show: s.show });
    const roles = user.role === 'admin' ? (await api<{ roles: StaffRole[] }>('/api/admin/roles')).roles : [];
    return { list, roles };
  });
  return (
    <Loaded query={query}>
      {({ list, roles }) => (
        <>
          <div className={css('toolbar')}>
            <SearchBox placeholder="Search name or email" value={s.q} onChange={(q) => set({ q })} />
            <Segmented
              choices={[
                { id: '', label: 'All' },
                { id: 'admins', label: 'Staff' },
                { id: 'no_credits', label: 'Out of credits' },
                { id: 'disabled', label: 'Disabled' },
              ]}
              current={s.show}
              onPick={(show) => set({ show })}
            />
            <span className="muted small" style={{ marginLeft: 'auto' }}>
              {`${list.length} user${list.length === 1 ? '' : 's'}`}
            </span>
            <ExportLink name="users" />
          </div>
          <div className={css('card')}>
            <Table
              head={['User', 'Role', 'Credits', 'Spent', 'Items', 'Jobs', 'Last job', 'Joined', '']}
              rows={list.map((u) => [
                <div key="u">
                  {u.name}
                  {u.disabled ? (
                    <span className={css('pill failed')} style={{ marginLeft: 6 }}>
                      Disabled
                    </span>
                  ) : null}
                  <div className="muted small">{u.email}</div>
                </div>,
                u.role,
                <b key="c">{number(u.credits)}</b>,
                number(u.spent),
                number(u.generations),
                number(u.jobs),
                ago(u.last_job),
                ago(u.created),
                <button
                  key="b"
                  className="btn small"
                  onClick={(e) => {
                    e.stopPropagation();
                    setGiving(u);
                  }}
                >
                  Credits
                </button>,
              ])}
              onRow={(i) => setOpen(list[i].id)}
              empty="No users match."
            />
          </div>
          <p className="muted small" style={{ marginTop: 10 }}>
            Select a user to see their jobs, credits and items, and to manage the account.
          </p>
          {open !== null && <UserDrawer id={open} roles={roles} onClose={() => setOpen(null)} />}
          {giving && (
            <CreditsDialog
              people={[giving]}
              onClose={() => setGiving(null)}
              after={() => {
                setGiving(null);
                void refresh();
              }}
            />
          )}
        </>
      )}
    </Loaded>
  );
}

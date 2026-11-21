// Who uses the space: finished work and assets by user, the largest files, and the reference files people added.

import { api } from '../../../common/api';
import { openViewer } from '../../../common/media/Viewer';
import type { Item } from '../../../common/media/item';
import { useConsole } from '../shared/context';
import { Person, Table, ago, bytes, failed, number, sure } from '../shared/ui';
import { classesOf } from '../../../common/cx';
import css0 from '../../../common/components/Shared2.module.css';
import css1 from '../../../common/components/Shared3.module.css';
import css2 from '../../../studio/pages/create/CreatePage.module.css';
const css = classesOf(css0, css1, css2);

type Largest = {
  id: number;
  name: string;
  kind: string;
  filename: string;
  size: number;
  created: number;
  user_name: string;
  user_email: string;
};
export type Storage = {
  people: { name: string; email: string; bytes: number; files: number; asset_bytes: number; asset_files: number }[];
  largest: Largest[];
  // the reference files people added (the uploads), by user; the name is the backend's
  render_server?: {
    total: number;
    by_user: { user_name: string; user_email: string; files: number; newest: number }[];
  };
};

export function StorageCards({ st }: { st: Storage }) {
  const { refresh } = useConsole();
  const open = (item: Largest) =>
    openViewer({ ...item, settings: {}, context: {}, workflow: '' } as Item, {
      base: '/api/admin/library',
      owner: true,
      actions: [
        {
          label: 'Delete from their library',
          danger: true,
          run: (close) => {
            void sure(
              `Delete "${item.name}" from ${item.user_name}'s library? This frees ${bytes(item.size)} and can't be undone.`,
            ).then((yes) => {
              if (!yes) return;
              void api('/api/admin/library/' + item.id, { method: 'DELETE' }).then(() => {
                close();
                void refresh();
              }, failed);
            });
          },
        },
      ],
    });
  const rs = st.render_server;
  return (
    <>
      <div className={css('card')}>
        <div className={css('card-head')}>
          <h2>Storage by user</h2>
          <span className="muted small">finished work and saved assets on this machine</span>
        </div>
        <Table
          head={['User', 'Finished work', 'Assets', 'Together']}
          rows={st.people.map((p) => [
            <Person key="p" name={p.name} email={p.email} />,
            `${bytes(p.bytes)} · ${number(p.files)} files`,
            `${bytes(p.asset_bytes)} · ${number(p.asset_files)}`,
            <b key="b">{bytes(p.bytes + p.asset_bytes)}</b>,
          ])}
          empty="No users."
        />
      </div>
      <div className={css('card')}>
        <div className={css('card-head')}>
          <h2>Largest files</h2>
          <span className="muted small">select one to watch it or delete it</span>
        </div>
        <Table
          head={['Item', 'User', 'Size', 'Made']}
          rows={st.largest.map((i) => [
            <b key="n">{i.name}</b>,
            <Person key="p" name={i.user_name} email={i.user_email} />,
            bytes(i.size),
            ago(i.created),
          ])}
          onRow={(n) => open(st.largest[n])}
          empty="Nothing made yet."
        />
      </div>
      {rs && (
        <div className={css('card')}>
          <div className={css('card-head')}>
            <h2>Reference files</h2>
            <span className="muted small">{`${number(rs.total)} reference files`}</span>
          </div>
          <p className="muted small">
            Pictures, videos and sounds people added as references, kept by the studio for their jobs and sent to the
            provider that makes each one.
          </p>
          {rs.by_user.length ? (
            <Table
              head={['User', 'Files', 'Newest']}
              rows={rs.by_user.map((u) => [
                <Person key="p" name={u.user_name} email={u.user_email} />,
                number(u.files),
                ago(u.newest),
              ])}
            />
          ) : (
            <p className="muted">None recorded yet.</p>
          )}
        </div>
      )}
    </>
  );
}

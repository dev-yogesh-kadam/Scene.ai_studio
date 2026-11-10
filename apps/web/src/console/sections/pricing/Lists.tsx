// The credit packages, and the servers with what they draw.

import { api } from '../../../common/api';
import { useConsole } from '../shared/context';
import { Table, number } from '../shared/ui';
import type { EditField, Editing } from './EditDialog';
import { rupees, trim, type Data } from './pricingData';
import { classesOf } from '../../../common/cx';
import css0 from '../../../common/components/Shared2.module.css';
import css1 from '../../../common/components/Shared3.module.css';
import css2 from '../shared/Console.module.css';
import css3 from '../../../studio/pages/create/CreatePage.module.css';
const css = classesOf(css0, css1, css2, css3);

const PACKAGE: EditField[] = [
  { id: 'name', label: 'Name', type: 'text', hint: 'Starter' },
  { id: 'price_inr', label: 'Price (₹)', type: 'number' },
  { id: 'credits', label: 'Credits', type: 'number' },
  { id: 'bonus_credits', label: 'Bonus credits', type: 'number' },
  { id: 'active', label: 'Offered for sale', type: 'check' },
];
const SERVER: EditField[] = [
  { id: 'name', label: 'Name', type: 'text' },
  { id: 'role', label: 'What it does', type: 'text' },
  { id: 'cpu', label: 'CPU', type: 'text' },
  { id: 'gpu', label: 'GPU', type: 'text' },
  { id: 'vram_gb', label: 'Video memory (GB)', type: 'number' },
  { id: 'idle_power_w', label: 'Idle power (W)', type: 'number', hint: 'Not measured yet' },
  { id: 'generation_power_w', label: 'Average power while generating (W)', type: 'number', hint: 'Not measured yet' },
  { id: 'max_power_w', label: 'Maximum power (W)', type: 'number', hint: 'Not measured yet' },
  { id: 'preferred_workflows', label: 'Preferred for', type: 'text', hint: 'video, image, audio' },
  { id: 'supported_workflows', label: 'Can also run', type: 'text', hint: 'image' },
  { id: 'purchase_price_inr', label: 'Purchase price (₹)', type: 'number' },
  { id: 'purchase_date', label: 'Purchase date', type: 'text', hint: '2026-01-31' },
  { id: 'life_months', label: 'Expected life (months)', type: 'number' },
  { id: 'salvage_value_inr', label: 'Salvage value (₹)', type: 'number' },
  { id: 'productive_hours', label: 'Expected productive hours', type: 'number' },
  { id: 'renders', label: 'Generation jobs are recorded against this server', type: 'check' },
  { id: 'active', label: 'In use', type: 'check' },
];

function useRowDialog(edit: (e: Editing) => void) {
  const { refresh } = useConsole();
  return <T extends { id: number; name: string }>(list: string, what: string, fields: EditField[], row?: T) =>
    edit({
      title: row ? row.name : 'New ' + what,
      fields,
      values: (row as unknown as Record<string, unknown>) || { active: true },
      save: (values) =>
        api(`/api/admin/pricing/${list}` + (row ? '/' + row.id : ''), {
          method: row ? 'PUT' : 'POST',
          json: values,
        }).then(refresh),
      remove: row ? () => api(`/api/admin/pricing/${list}/${row.id}`, { method: 'DELETE' }).then(refresh) : undefined,
    });
}

export function Packages({ data, edit }: { data: Data; edit: (e: Editing) => void }) {
  const open = useRowDialog(edit);
  return (
    <div className={css('card')}>
      <div className={css('card-head')}>
        <h2>Credit packages</h2>
        <button className="btn small primary" onClick={() => open('packages', 'package', PACKAGE)}>
          Add a package
        </button>
      </div>
      <Table
        head={['Package', 'Price', 'Credits', 'Bonus', 'Per 1,000 credits', 'Status']}
        rows={data.packages.map((p) => [
          <b key="n">{p.name}</b>,
          rupees(p.price_inr),
          number(p.credits),
          p.bonus_credits ? '+' + number(p.bonus_credits) : '',
          p.credits + p.bonus_credits ? rupees((1000 * p.price_inr) / (p.credits + p.bonus_credits)) : '',
          <span key="s" className={css('pill ' + (p.active ? 'done' : 'cancelled'))}>
            {p.active ? 'Offered' : 'Not offered'}
          </span>,
        ])}
        onRow={(i) => open('packages', 'package', PACKAGE, data.packages[i])}
        empty="No packages yet."
      />
      <p className="muted small" style={{ marginTop: 10 }}>
        Packages are kept here for when payments are added. Until then credits are given by an admin.
      </p>
    </div>
  );
}

export function Servers({ data, edit }: { data: Data; edit: (e: Editing) => void }) {
  const open = useRowDialog(edit);
  const none = (word: string) => <span className="muted">{word}</span>;
  return (
    <div className={css('card')}>
      <div className={css('card-head')}>
        <h2>Servers</h2>
        <button className="btn small primary" onClick={() => open('servers', 'server', SERVER)}>
          Add a server
        </button>
      </div>
      <Table
        head={[
          'Server',
          'Hardware',
          'Power while generating',
          'Electricity while generating',
          'Preferred for',
          'Status',
        ]}
        rows={data.servers.map((s) => [
          <div key="n">
            <b>{s.name}</b>
            <div className="muted small">{s.role}</div>
          </div>,
          <div key="h">
            {s.gpu + (s.vram_gb ? ` · ${trim(s.vram_gb)} GB` : '')}
            <div className="muted small">{s.cpu}</div>
          </div>,
          s.generation_power_w ? number(s.generation_power_w) + ' W' : none('Not measured'),
          s.generation_power_w
            ? rupees((s.generation_power_w / 1000) * data.electricity_inr_per_kwh) + ' an hour'
            : none('Not measured'),
          s.preferred_workflows || none('Not set'),
          <span key="s" className={css('pill ' + (s.active ? 'done' : 'cancelled'))}>
            {s.active ? (s.renders ? 'Renders jobs' : 'In use') : 'Not in use'}
          </span>,
        ])}
        onRow={(i) => open('servers', 'server', SERVER, data.servers[i])}
        empty="No servers yet."
      />
      <p className="muted small" style={{ marginTop: 10 }}>
        Electricity only: cooling, depreciation, storage and failed runs are not counted here. Replace an assumed power
        with one measured at the wall.
      </p>
    </div>
  );
}

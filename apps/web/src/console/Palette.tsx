// The console's search (Ctrl+K): the sections by name, and people, jobs, projects and workflows by name, email or id.

import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { api } from '../common/api';
import type { Section } from './sectionList';
import { useConsole } from './sections/shared/context';
import { classesOf } from '../common/cx';
import css0 from '../common/components/Shared.module.css';
import css1 from '../common/components/Shared2.module.css';
import css2 from '../common/components/Shared3.module.css';
import css3 from '../common/components/Shared4.module.css';
import css4 from '../common/landing/Landing2.module.css';
import css5 from './Palette.module.css';
import css6 from '../studio/pages/guide/GuidePage.module.css';
const css = classesOf(css0, css1, css2, css3, css4, css5, css6);

type Result = { kind: string; label: string; note?: string; run: () => void };
type Found = {
  users: { name: string; email: string; role: string; disabled?: boolean | number }[];
  jobs: { name: string; user_name: string; status: string }[];
  projects: { name: string; user_name: string; parent_id?: number | null }[];
  workflows: { id: string; title: string }[];
};

export function Palette({ mine, onClose }: { mine: Section[]; onClose: () => void }) {
  const { go } = useConsole();
  const [text, setText] = useState('');
  const [items, setItems] = useState<Result[]>([]);
  const [at, setAt] = useState(0);
  const box = useRef<HTMLInputElement>(null);
  const timer = useRef<ReturnType<typeof setTimeout>>(undefined);
  const asked = useRef(0);
  const leave = useRef(onClose);
  useLayoutEffect(() => {
    leave.current = onClose;
  });

  useEffect(() => {
    box.current?.focus();
    const key = (e: KeyboardEvent) => {
      if (e.key === 'Escape') leave.current();
    };
    document.addEventListener('keydown', key);
    return () => {
      document.removeEventListener('keydown', key);
      clearTimeout(timer.current);
    };
  }, []);

  const find = async (typed: string) => {
    const q = typed.trim();
    const low = q.toLowerCase();
    const sections = mine
      .filter((s) => low && s.label.toLowerCase().includes(low))
      .map((s) => ({ kind: 'Section', label: s.label, run: () => go(s.id) }));
    setItems(sections);
    setAt(0);
    if (q.length < 2) return;
    const ticket = ++asked.current; // a later search makes this one stale
    let found: Found;
    try {
      found = await api<Found>('/api/admin/search?q=' + encodeURIComponent(q));
    } catch {
      return;
    }
    if (ticket !== asked.current) return;
    const can = (id: string) => mine.some((s) => s.id === id);
    setItems([
      ...sections,
      ...found.users
        .filter(() => can('users'))
        .map((u) => ({
          kind: 'Person',
          label: u.name,
          note: u.email + (u.role !== 'user' ? ' · ' + u.role : '') + (u.disabled ? ' · disabled' : ''),
          run: () => go('users', { q: u.email, show: '' }),
        })),
      ...found.jobs
        .filter(() => can('jobs'))
        .map((j) => ({
          kind: 'Job',
          label: j.name,
          note: `${j.user_name} · ${j.status}`,
          run: () => go('jobs', { q: j.name, status: '', offset: 0 }),
        })),
      ...found.projects.map((p) => ({
        kind: p.parent_id ? 'Module' : 'Project',
        label: p.name,
        note: p.user_name,
        run: () => go('projects', { q: p.name }),
      })),
      ...found.workflows
        .filter(() => can('workflows'))
        .map((w) => ({ kind: 'Workflow', label: w.title, note: w.id, run: () => go('workflows', { show: '' }) })),
    ]);
  };

  const pick = (item: Result) => {
    onClose();
    item.run();
  };

  return createPortal(
    <div
      className={css('palette-shade')}
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className={css('palette')} role="dialog" aria-label="Search">
        <input
          ref={box}
          type="search"
          className={css('palette-input')}
          placeholder="Search people, jobs, projects, workflows, sections…"
          aria-label="Search"
          value={text}
          onChange={(e) => {
            const typed = e.target.value;
            setText(typed);
            clearTimeout(timer.current);
            timer.current = setTimeout(() => void find(typed), 180);
          }}
          onKeyDown={(e) => {
            if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
              e.preventDefault();
              const count = Math.max(items.length, 1);
              setAt((was) => (was + (e.key === 'ArrowDown' ? 1 : items.length - 1)) % count);
            }
            if (e.key === 'Enter' && items[at]) pick(items[at]);
          }}
        />
        <div className={css('palette-list')} role={items.length ? 'listbox' : undefined} aria-label="Found">
          {items.length ? (
            items.map((item, i) => (
              <button
                key={item.kind + item.label + (item.note ?? '')}
                className={css('palette-item' + (i === at ? ' on' : ''))}
                role="option"
                aria-selected={i === at}
                onMouseEnter={() => setAt(i)}
                onClick={() => pick(item)}
              >
                <span className={css('palette-kind')}>{item.kind}</span>
                <span className="grow">{item.label}</span>
                {item.note && <span className="muted small">{item.note}</span>}
              </button>
            ))
          ) : (
            <p className="muted small" style={{ padding: '10px 12px' }}>
              {text.trim().length < 2 ? "Type a name, an email or a job's id." : 'Nothing found.'}
            </p>
          )}
        </div>
      </div>
    </div>,
    document.body,
  );
}

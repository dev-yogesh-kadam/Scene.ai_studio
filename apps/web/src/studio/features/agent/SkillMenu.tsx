// Skills: the square box opens a picker with a search field; typing /name anywhere in the message filters the same list
// inline. In the box you type in its own field; with /name the message drives the filter, and the field mirrors it.

import { useQuery } from '@tanstack/react-query';
import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router';
import { skillsList } from '@scene/shared/api/agent';
import { Icon } from '../../../common/components/Icon/Icon';
import { cx } from '../../../common/cx';
import { userPrefs } from '../../userPrefs';
import s from './Skill.module.css';

type Skill = { id: string; title: string; desc?: string };
// The skills used lately: the user's, kept on the server (userPrefs).
const recentIds = (): string[] => userPrefs.studio().skills;
export const pushRecent = (id: string) =>
  userPrefs.setStudio({ skills: [id, ...recentIds().filter((x) => x !== id)].slice(0, 5) });

export const useSkills = () =>
  useQuery({ queryKey: ['skills', 'list'], queryFn: () => skillsList<Skill>().catch(() => []), staleTime: Infinity });

/** The skills to show for a query, in groups. No query: recently used, then the rest. */
function groupsOf(all: Skill[], query: string) {
  const q = query.trim().toLowerCase();
  if (q) {
    // The closest first: a name that starts with what was typed, then one that has it, then a title, then a description.
    const rank = (x: Skill) =>
      x.id.startsWith(q)
        ? 0
        : x.id.includes(q)
          ? 1
          : x.title.toLowerCase().includes(q)
            ? 2
            : (x.desc || '').toLowerCase().includes(q)
              ? 3
              : 9;
    return [{ label: 'Results', skills: all.filter((x) => rank(x) < 9).sort((a, b) => rank(a) - rank(b)) }];
  }
  const recent = recentIds()
    .map((id) => all.find((x) => x.id === id))
    .filter((x): x is Skill => !!x);
  return [
    ...(recent.length ? [{ label: 'Recently used', skills: recent }] : []),
    { label: 'All skills', skills: all.filter((x) => !recent.includes(x)) },
  ];
}

export type SkillKey = (e: { key: string; preventDefault: () => void }) => boolean;

type Props = {
  mode: 'box' | 'slash';
  search: string;
  onSearch: (text: string) => void;
  onPick: (id: string) => void;
  onClose: () => void;
  onKeys: (key: SkillKey | null) => void; // the message box hands its keys here while /name is typed
  outside: (target: Node) => boolean; // whether a press there leaves the menu open
};

export function SkillMenu({ mode, search, onSearch, onPick, onClose, onKeys, outside }: Props) {
  const navigate = useNavigate();
  const all = useSkills().data ?? [];
  const groups = groupsOf(all, search);
  const rows = groups.flatMap((g) => g.skills);
  const [at, setAt] = useState(0);
  const here = Math.min(at, Math.max(0, rows.length - 1));
  const field = useRef<HTMLInputElement>(null);
  const menu = useRef<HTMLDivElement>(null);
  const item = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    if (mode === 'box') field.current?.focus(); // with /name the message keeps focus, so you go on typing there
  }, [mode]);
  // In braces: Chrome's scrollIntoView now returns a Promise, and an effect must return nothing or a cleanup.
  useEffect(() => {
    item.current?.scrollIntoView({ block: 'nearest' });
  }, [here]);
  useEffect(() => {
    const press = (e: PointerEvent) => {
      if (menu.current?.contains(e.target as Node) || outside(e.target as Node)) return;
      onClose();
    };
    document.addEventListener('pointerdown', press, true);
    return () => document.removeEventListener('pointerdown', press, true);
  }, [onClose, outside]);
  const key = (e: { key: string; preventDefault: () => void }) => {
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setAt(Math.min(rows.length - 1, here + 1));
      return true;
    }
    if (e.key === 'ArrowUp') {
      e.preventDefault();
      setAt(Math.max(0, here - 1));
      return true;
    }
    if ((e.key === 'Enter' || e.key === 'Tab') && rows[here]) {
      e.preventDefault();
      onPick(rows[here].id);
      return true;
    }
    if (e.key === 'Escape') {
      e.preventDefault();
      onClose();
      return true;
    }
    return false;
  };
  useEffect(() => {
    onKeys(key);
    return () => onKeys(null);
  });
  let i = 0;
  return (
    <div ref={menu} className={s['agent-skillmenu']} role="listbox">
      <div className={s['skillmenu-head']}>
        <Icon name="search" />
        <input
          ref={field}
          className={s['skillmenu-search']}
          type="text"
          placeholder="Search all skills…"
          value={search}
          onChange={(e) => {
            onSearch(e.target.value);
            setAt(0);
          }}
          onKeyDown={key}
        />
      </div>
      <div className={s['skillmenu-list']}>
        {groups.map((g) => (
          <div key={g.label}>
            <div className={s['skillmenu-label']}>{g.label}</div>
            {!g.skills.length && <div className={cx(s['skillmenu-empty'], 'muted small')}>No matches.</div>}
            {g.skills.map((x) => {
              const idx = i++;
              return (
                <button
                  key={x.id}
                  ref={idx === here ? item : undefined}
                  type="button"
                  className={cx(s['skillmenu-item'], idx === here && s.on)}
                  role="option"
                  aria-selected={idx === here}
                  onMouseEnter={() => setAt(idx)}
                  onMouseDown={(e) => {
                    e.preventDefault();
                    onPick(x.id);
                  }}
                >
                  <span className={s['skillmenu-mark']}>
                    <Icon name="skill" />
                  </span>
                  <span className={s['skillmenu-text']}>
                    <b>{x.title}</b>
                    <span className={s['skillmenu-desc']}>{x.desc || '/' + x.id}</span>
                  </span>
                  <code className={s['skillmenu-id']}>{'/' + x.id}</code>
                </button>
              );
            })}
          </div>
        ))}
        <a
          className={cx(s['skillmenu-item'], s['skillmenu-foot'])}
          href="/skills"
          onMouseDown={(e) => {
            e.preventDefault();
            void navigate('/skills');
            onClose();
          }}
        >
          <span className={s['skillmenu-mark']}>
            <Icon name="grid" />
          </span>
          <span className={s['skillmenu-text']}>
            <b>See all skills</b>
          </span>
        </a>
      </div>
    </div>
  );
}

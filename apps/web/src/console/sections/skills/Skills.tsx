// The admin console's Skills section: create, edit and delete the recipes the agent follows. Skills are Markdown files
// on the server; a change takes effect on the next agent message, with no restart.

import { useRef, useState, type ChangeEvent } from 'react';
import { api } from '../../../common/api';
import { useConsole, useSection } from '../shared/context';
import { Loaded, Table, failed, say, sure } from '../shared/ui';
import { DraftReview, Editor, type Draft } from './Dialogs';
import { parseSkill, type Skill } from './parseSkill';
import { classesOf } from '../../../common/cx';
import css0 from '../../../common/components/Shared2.module.css';
import css1 from '../../../common/components/Shared3.module.css';
import css2 from './Skills.module.css';
import css3 from '../../../studio/pages/create/CreatePage.module.css';
const css = classesOf(css0, css1, css2, css3);

type Waiting = { drafts: Draft[]; can_publish: boolean };
type Opened = { skill: Skill | null; imported?: boolean; ids?: string[] };
const clip = (s: string) => (s && s.length > 48 ? s.slice(0, 48) + '…' : s || '');

export default function Skills() {
  const { refresh } = useConsole();
  const [opened, setOpened] = useState<Opened | null>(null);
  const [draft, setDraft] = useState<Draft | null>(null);
  const picker = useRef<HTMLInputElement>(null);
  const query = useSection('skills', [], async () => {
    const [list, waiting] = await Promise.all([
      api<{ skills: Skill[] }>('/api/admin/skills'),
      // drafts are shown when they can be read
      api<Waiting>('/api/admin/skills/drafts').catch((): Waiting => ({ drafts: [], can_publish: false })),
    ]);
    return { list: list.skills, waiting };
  });
  const del = async (skill: Skill) => {
    if (!(await sure(`Delete the skill “${skill.title}” (/${skill.id})? This cannot be undone.`))) return;
    await api('/api/admin/skills/' + encodeURIComponent(skill.id), { method: 'DELETE' }).then(refresh, failed);
  };
  return (
    <Loaded query={query}>
      {({ list, waiting }) => {
        // A .md file opens in the editor filled in, to look over and save. A skill with the same id is replaced.
        const chosen = async (e: ChangeEvent<HTMLInputElement>) => {
          const file = e.target.files?.[0];
          e.target.value = '';
          if (!file) return;
          if (file.size > 200000) {
            void say('That file is too large for a skill (200 KB at most).');
            return;
          }
          setOpened({ skill: parseSkill(await file.text(), file.name), imported: true, ids: list.map((s) => s.id) });
        };
        return (
          <>
            <div className={css('card')}>
              <div className={css('card-head')}>
                <h2 style={{ flex: 1 }}>Skills</h2>
                <button
                  className="btn small"
                  title="Add a skill from a Markdown file"
                  onClick={() => picker.current?.click()}
                >
                  Upload .md
                </button>
                <input
                  ref={picker}
                  type="file"
                  accept=".md,.markdown,.txt,text/markdown,text/plain"
                  className="hidden"
                  aria-label="Skill file"
                  onChange={(e) => void chosen(e)}
                />
                <button className="btn primary small" onClick={() => setOpened({ skill: null })}>
                  New skill
                </button>
              </div>
              <p className="muted small" style={{ margin: '-6px 0 16px' }}>
                Recipes the agent follows for a kind of work. Saved as files on the server; a change takes effect on the
                next message, no restart needed. Users call one by typing /id or from the skills box.
              </p>
              <Table
                head={['Skill', 'Command', 'Version', 'Trigger words', '']}
                rows={list.map((s) => [
                  <div key="t">
                    <b>{s.title}</b>
                    {s.desc && <div className="muted small">{s.desc}</div>}
                  </div>,
                  <code key="c">{'/' + s.id}</code>,
                  'v' + s.version,
                  <code key="w" className="small muted">
                    {clip(s.words)}
                  </code>,
                  <div key="a" className={css('skill-row-actions')}>
                    <button className="btn small" onClick={() => setOpened({ skill: s })}>
                      Edit
                    </button>
                    <button className="btn small danger" onClick={() => void del(s)}>
                      Delete
                    </button>
                  </div>,
                ])}
                empty="No skills yet. Add one with “New skill”."
              />
            </div>
            {waiting.drafts.length > 0 && (
              <div className={css('card')}>
                <div className={css('card-head')}>
                  <h2 style={{ flex: 1 }}>{`Drafts waiting (${waiting.drafts.length})`}</h2>
                </div>
                <p className="muted small" style={{ margin: '-6px 0 16px' }}>
                  Skills the agent drafted in a chat when someone asked “make this a skill”. The agent uses one only
                  once an admin publishes it.
                </p>
                <Table
                  head={['Draft', 'Drafted by', '']}
                  rows={waiting.drafts.map((d) => [
                    <div key="t">
                      <b>{d.title}</b>
                      {d.desc && <div className="muted small">{d.desc}</div>}
                    </div>,
                    d.by_name || '—',
                    <div key="a" className={css('skill-row-actions')}>
                      <button className="btn small" onClick={() => setDraft(d)}>
                        {waiting.can_publish ? 'Review' : 'View'}
                      </button>
                    </div>,
                  ])}
                />
              </div>
            )}
            {opened && <Editor {...opened} onSaved={() => void refresh()} onClose={() => setOpened(null)} />}
            {draft && (
              <DraftReview
                draft={draft}
                canPublish={waiting.can_publish}
                onDone={() => void refresh()}
                onClose={() => setDraft(null)}
              />
            )}
          </>
        );
      }}
    </Loaded>
  );
}

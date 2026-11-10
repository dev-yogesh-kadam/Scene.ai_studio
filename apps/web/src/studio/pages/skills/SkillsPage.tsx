// The Skills page: every recipe the agent can follow, read-only. Skills are files on the server; this shows what each
// one is for, when it fires, and the steps it gives the agent.

import { useQuery } from '@tanstack/react-query';
import type { Skill } from '@scene/shared/types/api';
import { api } from '../../../common/api';
import { Icon } from '../../../common/components/Icon/Icon';
import s from './SkillsPage.module.css';
import { classesOf } from '../../../common/cx';
import css0 from '../../../common/components/Shared2.module.css';
import css1 from '../../../common/components/Shared3.module.css';
import css2 from '../../../common/components/Shared4.module.css';
import css3 from './SkillsPage2.module.css';
import { EmptyState, ErrorBanner, Skeleton } from '../../../common/components/States';
const css = classesOf(css0, css1, css2, css3);

type FullSkill = Skill & { words?: string; version?: string | number; text?: string };

/** A skill's trigger regex, turned into a few plain example words for the card. */
export function triggerWords(pattern: string) {
  const inner = pattern.match(/\(([^)]*)\)/)?.[1] ?? pattern;
  return inner
    .replace(/\\b|\\w\*|\?|\.\*/g, '')
    .split('|')
    .map((w) => w.replace(/[^a-z0-9 .-]/gi, '').trim())
    .filter(Boolean)
    .slice(0, 8);
}

export default function SkillsPage() {
  const skills = useQuery({
    queryKey: ['skills'],
    queryFn: () => api<{ skills: FullSkill[] }>('/api/skills').then((answer) => answer.skills),
  });
  return (
    <>
      <div className={css('page-head')}>
        <h1>Skills</h1>
      </div>
      <p className={css('page-sub')}>
        Recipes the agent follows for a kind of work. One is used on its own when your message matches it, or you can
        call one yourself by typing <code>/skill-id</code> at the start of a message in the agent panel.
      </p>
      <div className={css('card')}>
        <div className={s['skills-list']}>
          {skills.isPending ? (
            <Skeleton count={5} shape="line" />
          ) : skills.isError ? (
            <ErrorBanner
              error={new Error('Could not load skills: ' + skills.error.message)}
              onRetry={() => void skills.refetch()}
            />
          ) : !skills.data.length ? (
            <EmptyState>No skills yet.</EmptyState>
          ) : (
            skills.data.map((skill) => {
              const words = triggerWords(skill.words || '');
              return (
                <details key={skill.id} className={s['skill-item']}>
                  <summary>
                    <span className={s['skill-mark']} aria-hidden="true">
                      <Icon name="skill" />
                    </span>
                    <span className={s['skill-name']}>{skill.title}</span>
                    <code className={s['skill-id']}>{'/' + skill.id}</code>
                    <span className={css(s['skill-ver'] + ' slate-text')}>{'v' + skill.version}</span>
                  </summary>
                  {words.length > 0 && (
                    <div className={s['skill-triggers']}>
                      <span className={css('slate-text')}>Fires on: </span>
                      {words.map((w) => (
                        <span key={w} className={css('tag')}>
                          {w}
                        </span>
                      ))}
                    </div>
                  )}
                  <pre className={s['skill-text']}>{skill.text}</pre>
                </details>
              );
            })
          )}
        </div>
      </div>
    </>
  );
}

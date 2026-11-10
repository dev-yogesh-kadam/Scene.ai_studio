// Three prompts to start from, for someone who has made nothing yet (U6): each with its workflow and what it costs on
// it, so a first try is not guesswork with credits. A click puts the prompt and its workflow in the box above.

import { useQuery } from '@tanstack/react-query';
import { creditsText } from '../../../common/format';
import { byRole, estimate, loadCatalog, loadWorkflow, newForm } from '../../features/jobs/jobForm';
import s from './Starters.module.css';

const STARTERS = [
  {
    kind: 'image',
    title: 'A first picture',
    prompt:
      'A girl in a yellow raincoat on a rainy street at night, neon signs reflected in the puddles, 35mm film look',
  },
  {
    kind: 'image',
    title: 'A product shot',
    prompt: 'A glass perfume bottle on wet black stone, soft rim light, a thin mist behind it, studio photography',
  },
  {
    kind: 'video',
    title: 'A first clip',
    prompt: 'A slow dolly in on a lighthouse at dawn, waves breaking on the rocks below, mist drifting past the lamp',
  },
] as const;

type Priced = { kind: string; title: string; prompt: string; workflow: string; title_wf: string; credits: number };

/** Each starter on the studio's default workflow for its kind, priced as Generate would be. */
async function priced(): Promise<Priced[]> {
  const catalog = await loadCatalog();
  const out: Priced[] = [];
  for (const starter of STARTERS) {
    const usable = catalog.workflows.filter((w) => w.kind === starter.kind && !w.error);
    const row = usable.find((w) => w.id === catalog.default) ?? usable[0];
    if (!row) continue;
    const wf = await loadWorkflow(row.id);
    const form = newForm(wf);
    const box = byRole(wf, 'prompt');
    const quote = await estimate(box ? { ...form, values: { ...form.values, [box.id]: starter.prompt } } : form);
    out.push({ ...starter, workflow: row.id, title_wf: wf.title, credits: quote.credits });
  }
  return out;
}

export function Starters({ onPick }: { onPick: (workflow: string, prompt: string) => void }) {
  const starters = useQuery({ queryKey: ['starters'], queryFn: priced, staleTime: Infinity }).data;
  if (!starters?.length) return null;
  return (
    <section className={s.starters} aria-labelledby="starters-head">
      <h2 id="starters-head">New here? Start from one of these</h2>
      <div className={s.grid}>
        {starters.map((st) => (
          <button key={st.title} type="button" className={s.starter} onClick={() => onPick(st.workflow, st.prompt)}>
            <b>{st.title}</b>
            <span className={s.prompt}>{st.prompt}</span>
            <span className={s.price}>{`${st.title_wf} · ${creditsText(st.credits)}`}</span>
          </button>
        ))}
      </div>
    </section>
  );
}

// The two screens drawn on the landing page: the agent's plan and NeuralCore.

import { Rv } from '../../../common/landing/LandingRoot';
import * as scenes from '../../../common/landing/landingScenes';
import { Picture } from '../../../common/landing/Picture';
import { CORE } from './content';
import { classesOf } from '../../../common/cx';
import css0 from '../../../common/landing/Landing.module.css';
import css1 from '../../../common/landing/Landing3.module.css';
import css2 from '../../../common/landing/Landing4.module.css';
import css3 from '../../../common/landing/Landing5.module.css';
import css4 from '../../../common/landing/Landing6.module.css';
import css5 from './Monitor.module.css';
import css6 from './Sections.module.css';
import css7 from './Shared.module.css';
const css = classesOf(css0, css1, css2, css3, css4, css5, css6, css7);

export function PlanScreen({ d }: { d: number }) {
  return (
    <Rv d={d} className={css('la-screen')} aria-hidden="true">
      <div className={css('la-bar la-mono')}>
        <span>Agent 1</span>
        <span>Plans first</span>
      </div>
      <div className={css('la-you')}>
        A 20 second ad for our sneaker drop. Rooftop, golden hour, the same runner in every shot.
      </div>
      <div className={css('la-plan')}>
        <header>
          <b>Plan · 3 shots</b>
          <span>Nothing is made until you approve</span>
        </header>
        {scenes.info('rooftop').shots.map((shot) => (
          <div key={shot} className={css('la-row')}>
            <Picture name="rooftop" className={css('la-thumb')} />
            <span>{shot}</span>
            <em>60 cr</em>
          </div>
        ))}
        <footer>
          <span className={css('la-mono')}>Storyboard first</span>
          <span className={css('la-btn solid small')}>Approve · 180</span>
        </footer>
      </div>
    </Rv>
  );
}

/** NeuralCore as the panel shows it: the cast, places and voices kept once, and the agent's notes. */
export function CoreScreen() {
  return (
    <Rv className={css('la-screen la-core')} aria-hidden="true">
      <div className={css('la-bar la-mono')}>
        <span>NeuralCore</span>
        <span>Monsoon ad · Module 1</span>
      </div>
      {CORE.map(([group, items]) => (
        <div key={group} className={css('la-core-group')}>
          <span className={css('la-mono')}>{group}</span>
          {items.map(([scene, name, note]) => (
            <div key={name} className={css('la-core-item')}>
              <Picture name={scene} className={css('la-core-pic')} />
              <b>{name}</b>
              <span>{note}</span>
            </div>
          ))}
        </div>
      ))}
      <div className={css('la-core-note')}>
        <span className={css('la-mono')}>Note</span>
        Meera never takes the raincoat off. Keep the red umbrella in her left hand.
      </div>
    </Rv>
  );
}

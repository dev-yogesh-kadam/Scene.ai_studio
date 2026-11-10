// The landing below its monitor, from Why down to the footer. The sign-in pages show it under their form too; join,
// signIn and start make the buttons and take a prompt, so there they lead back up to the form. Everything it shows is
// something the studio does; the pictures are drawn by the page itself.

import type { ReactNode } from 'react';
import { Rv, useLandingBar, useNextSection } from '../../../common/landing/LandingRoot';
import { Picture } from '../../../common/landing/Picture';
import { AGENT, BENCH, FAQ, KIT, STEPS, TAKES, USES } from './content';
import { CoreScreen, PlanScreen } from './Screens';
import { classesOf } from '../../../common/cx';
import css0 from '../../../common/components/Shared.module.css';
import css1 from '../../../common/components/Shared2.module.css';
import css2 from '../../../common/components/Shared3.module.css';
import css3 from '../../../common/components/Shared4.module.css';
import css4 from '../../../common/landing/Landing.module.css';
import css5 from '../../../common/landing/Landing2.module.css';
import css6 from '../../../common/landing/Landing3.module.css';
import css7 from '../../../common/landing/Landing4.module.css';
import css8 from '../../../common/landing/Landing5.module.css';
import css9 from '../guide/GuidePage.module.css';
import css10 from './Sections.module.css';
const css = classesOf(css0, css1, css2, css3, css4, css5, css6, css7, css8, css9, css10);

export type Door = (cls?: string) => ReactNode;

// A row of a section's label: its number and name on the left, a note on the right.
const Label = ({ left, right }: { left: string; right: string }) => (
  <div className={css('la-label la-mono')}>
    <span>{left}</span>
    <span>{right}</span>
  </div>
);

function Bar({ join, signIn, signupOpen }: { join: Door; signIn: Door; signupOpen: boolean }) {
  const on = useLandingBar();
  return (
    <div className={css('la-bar-top' + (on ? ' on' : ''))}>
      <a className={css('la-brand')} href="/">
        <img src="/img/logo.svg?v=clapper" alt="" />
        Scene.ai
      </a>
      <nav className={css('la-doors')}>
        {signupOpen && signIn('quiet small')}
        {join('solid small')}
      </nav>
    </div>
  );
}

function Uses({ start }: { start: (text: string) => void }) {
  return (
    <div className={css('la-uses')}>
      {USES.map(([scene, title, prompt, sketch], i) => (
        <Rv
          as="button"
          key={title}
          d={i % 4}
          type="button"
          className={css('la-use')}
          title="Start with this prompt"
          onClick={() => start(prompt)}
        >
          <Picture name={scene} className={css('la-pic')} sketch={!!sketch} />
          <span className={css('la-use-body')}>
            <b>{title}</b>
            <span className={css('la-use-prompt')}>{`“${prompt}”`}</span>
            <span className={css('la-use-go la-mono')}>Start with this →</span>
          </span>
        </Rv>
      ))}
    </div>
  );
}

function Report() {
  return (
    <section className={css('la-wrap la-report')}>
      <Label left="03 · The take report" right="Shot 1 · Rooftop at dusk" />
      <div className={css('la-strip')}>
        {TAKES.map(([scene, take, length, note, look], i) => (
          <Rv key={take} d={i} className={css('la-take ' + look)}>
            <Picture name={scene} className={css('la-pic')} />
            <dl>
              <dt>Shot</dt>
              <dd>{`01 · ${take}`}</dd>
              <dt>Model</dt>
              <dd>MiniMax H3</dd>
              <dt>Length</dt>
              <dd>{length}</dd>
              <dt>Note</dt>
              <dd>{note}</dd>
            </dl>
          </Rv>
        ))}
      </div>
      <div className={css('la-steps')}>
        {STEPS.map(([title, text], i) => (
          <Rv key={title} d={i}>
            <b className={css('la-mono')}>{`0${i + 1}`}</b>
            <h3>{title}</h3>
            <p>{text}</p>
          </Rv>
        ))}
      </div>
    </section>
  );
}

function Agent() {
  return (
    <section className={css('la-wrap la-agent')}>
      <Label left="04 · The agent" right="Plans first, makes later" />
      <div className={css('la-split')}>
        <Rv>
          <h2>An assistant director that asks before it spends.</h2>
          <p>
            Tell it what you are making, in plain words. It plans the shots, prices them and waits for your nod; then it
            looks at every take and offers a retake when a face or a place is wrong.
          </p>
          <ul className={css('la-chips')}>
            {AGENT.map((t) => (
              <li key={t}>{t}</li>
            ))}
          </ul>
          <p className={css('la-note la-mono')}>The agent is open to invited accounts for now.</p>
        </Rv>
        <PlanScreen d={1} />
      </div>
    </section>
  );
}

function Memory() {
  return (
    <section className={css('la-wrap la-memory')}>
      <Label left="05 · NeuralCore" right="The studio remembers" />
      <div className={css('la-split')}>
        <CoreScreen />
        <Rv d={1}>
          <h2>Shot 1 and shot 40. The same Meera.</h2>
          <p>
            Say “keep her as Meera” once. Her face, her raincoat, the street and her voice are kept in the project, and
            every later shot of her uses them.
          </p>
          <p>
            Come back next week and the set is as you left it: the cast, the places, the notes, and what you liked and
            did not.
          </p>
        </Rv>
      </div>
    </section>
  );
}

function Bench() {
  return (
    <section className={css('la-wrap la-bench')}>
      <Label left="06 · After the take" right="The rest of the studio" />
      <Rv as="h2">From a take to a finished film.</Rv>
      <div className={css('la-bento')}>
        {BENCH.map(([tag, title, text], i) => (
          <Rv key={title} d={i % 3} className={css('la-tile')}>
            <span className={css('la-mono')}>{tag}</span>
            <h3>{title}</h3>
            <p>{text}</p>
          </Rv>
        ))}
      </div>
    </section>
  );
}

function Kit() {
  return (
    <section className={css('la-wrap la-kit')}>
      <Label left="07 · On the cart" right="The models" />
      <Rv as="h2">Everything on the cart.</Rv>
      <table>
        <tbody>
          {KIT.map(([kind, what, model, text]) => (
            <Rv as="tr" key={kind + what}>
              <td className={css('la-mono')}>{kind}</td>
              <th scope="row">{what}</th>
              <td className={css('la-model')}>{model}</td>
              <td>{text}</td>
            </Rv>
          ))}
        </tbody>
      </table>
    </section>
  );
}

function Price() {
  return (
    <section className={css('la-wrap la-price')}>
      <Label left="08 · Credits" right="Pay for what you make" />
      <div className={css('la-split')}>
        <Rv as="h2">You pay for the take, not the render time.</Rv>
        <Rv d={1}>
          <p>
            A flat price for a picture, a price per second for video and music. You see it before you press Generate.
          </p>
          <ul className={css('la-chips')}>
            {['Price shown first', 'Failed jobs refunded', 'Edits and titles free'].map((t) => (
              <li key={t}>{t}</li>
            ))}
          </ul>
        </Rv>
      </div>
    </section>
  );
}

export function Sections({
  join,
  signIn,
  signupOpen,
  start,
}: {
  join: Door;
  signIn: Door;
  signupOpen: boolean;
  start: (text: string) => void;
}) {
  const next = useNextSection();
  return (
    <>
      <Bar join={join} signIn={signIn} signupOpen={signupOpen} />
      <section ref={next} className={css('la-wrap la-manifesto')}>
        <Label left="01 · Why" right="Scene.ai" />
        <Rv as="p">
          Most AI video tools give you a slot machine. <em>Scene.ai gives you a set:</em> a cast that stays the same,
          takes you can keep or roll again, and a cut you can trust.
        </Rv>
      </section>
      <section className={css('la-wrap la-use-sec')}>
        <Label left="02 · What you can make" right="Pick one to start" />
        <Rv as="h2">Start from a shot, a script or an idea.</Rv>
        <Uses start={start} />
      </section>
      <Report />
      <Agent />
      <Memory />
      <Bench />
      <Kit />
      <Price />
      <section className={css('la-wrap la-faq')}>
        <Label left="09 · Questions" right="Before you start" />
        <div>
          {FAQ.map(([q, a]) => (
            <Rv as="details" key={q}>
              <summary>{q}</summary>
              <p>{a}</p>
            </Rv>
          ))}
        </div>
      </section>
      <section className={css('la-cut')}>
        <Rv as="h2">CUT.</Rv>
        <p>{signupOpen ? 'Your first scene is a sentence away.' : 'Welcome back. The set is as you left it.'}</p>
        <div className={css('la-doors center')}>
          {join('solid big')}
          {signupOpen && signIn('big')}
        </div>
      </section>
      <footer className={css('la-end la-mono')}>
        <span>Scene.ai</span>
        <span>A studio for video, pictures and music</span>
      </footer>
    </>
  );
}

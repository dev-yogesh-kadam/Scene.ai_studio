// The Guide: how the studio works, from a first project to a finished video. Reached from the Guide button at the top
// right of every page but the canvas, and from the menu. One page; its contents list follows as you read.

import { useEffect, useRef, useState } from 'react';
import { Icon } from '../../../common/components/Icon/Icon';
import { KIT } from '../../words';
import s from './GuidePage.module.css';
import { classesOf } from '../../../common/cx';
import css0 from '../../../common/components/Shared.module.css';
import css1 from '../../../common/components/Shared2.module.css';
import css2 from '../../../common/components/Shared3.module.css';
import css3 from '../../../common/components/Shared4.module.css';
import css4 from '../../../common/landing/Landing2.module.css';
import css5 from './GuidePage.module.css';
const css = classesOf(css0, css1, css2, css3, css4, css5);

type Block = ['p' | 'tip', string] | ['steps' | 'list', string[]];

const SECTIONS: { id: string; title: string; body: Block[] }[] = [
  {
    id: 'start',
    title: 'Getting started',
    body: [
      [
        'p',
        'Scene.ai turns what you describe into pictures, videos, music and voice, and puts them together into finished videos. Work happens in projects: each project has its own canvas, agent conversations and its ' +
          KIT +
          '.',
      ],
      [
        'steps',
        [
          'Open Projects from the menu at the top left and make a project.',
          'Open its main canvas, or add a module for a separate part of the work, such as an episode.',
          'Ask the agent for what you want, or make something yourself from the panel beside the canvas.',
          'Ask the agent to put the shots in order and make the finished video.',
        ],
      ],
      [
        'tip',
        'Everything you make costs credits; your balance is at the top right. A job that fails or that you cancel gives its credits back.',
      ],
    ],
  },
  {
    id: 'projects',
    title: 'Projects and modules',
    body: [
      ['p', 'A project holds one piece of work. Its page shows its modules, what it has spent, and its details.'],
      [
        'p',
        "A module is a canvas of its own inside a project, with its own agent tabs: use one per episode, scene or version. Every module of a project shares the project's " +
          KIT +
          '.',
      ],
      [
        'list',
        [
          "Add module makes a new one; the project's own canvas is the main canvas.",
          'View analytics shows what the project spent and made, by day, by kind and by module.',
          'Duplicate project starts a copy with the same modules and ' + KIT + ', but none of what was made.',
          'Deleting a module deletes everything made in it; deleting a project deletes its modules, everything made in them and its ' +
            KIT +
            ". It can't be undone, so download what you want to keep first.",
        ],
      ],
    ],
  },
  {
    id: 'canvas',
    title: 'The canvas',
    body: [
      [
        'p',
        'The canvas shows everything made in a module as frames, one row per shot. The panel beside it makes the next thing: pick a frame and continue from it, upscale a video, or start a new shot.',
      ],
      [
        'list',
        [
          'Select a frame to see what it was made from and to use it as a reference.',
          'Quick actions make a picture, a video or a sound in a few clicks, or upscale a video.',
          'Drop a file onto the canvas to bring it in as a reference.',
        ],
      ],
    ],
  },
  {
    id: 'agent',
    title: 'The agent',
    body: [
      [
        'p',
        'The agent plans the work for you. Tell it what you want in plain words, attach frames from the canvas and say what each is for. It answers with a plan: each step, the model it uses and what it costs. Nothing runs until you approve it.',
      ],
      [
        'list',
        [
          'Approve runs the plan; you can change a step or ask again first.',
          "Skills are recipes the agent follows for longer work, such as a whole short film. Type / in the agent's box to pick one.",
          'The agent remembers the conversation in each tab; Compact shortens a long one so it stays quick.',
        ],
      ],
      [
        'tip',
        'Be specific about the look, the camera and the length. "A 5 second close-up of Anna laughing, warm evening light" works better than "Anna laughing".',
      ],
    ],
  },
  {
    id: 'kit',
    title: KIT,
    body: [
      [
        'p',
        'The ' +
          KIT +
          ' is what a project is made from: its characters, places, props, styles and voices. Keep a picture or a sound there once, give it a name, and use it in any module of the project.',
      ],
      [
        'list',
        [
          'Write @ and a name in a prompt, such as @Anna at @Bonfire Clearing, and the studio puts those references into the job.',
          'An entry marked always attached goes into every shot of the project, so a main character stays the same.',
          "The agent knows every entry by name and describes what it shows to models that can't see pictures.",
        ],
      ],
    ],
  },
  {
    id: 'create',
    title: 'Making things yourself',
    body: [
      [
        'p',
        'Create, and the panel beside the canvas, run one model at a time. Choose a workflow, write the prompt, fill the reference slots it asks for and pick the length, size and quality. The price is shown before you start.',
      ],
      [
        'list',
        [
          'For a long video, write one prompt per clip with a line of three dashes (---) between them: each clip starts on the last frame of the one before.',
          'Re-run in the library opens an item with the settings it was made with.',
          'Continue a video from its last frame to make the next shot match.',
        ],
      ],
    ],
  },
  {
    id: 'library',
    title: 'The library',
    body: [
      [
        'p',
        'The library holds everything you have made, in every project. Search by name or prompt, filter by kind or project, rate results with a thumbs up or down (the agent learns from them), and download or delete what you no longer need.',
      ],
    ],
  },
  {
    id: 'motion',
    title: 'Motion graphics',
    body: [
      [
        'p',
        "Motion graphics are videos of animated text and shapes: title cards, lower thirds, captions and whole explainer videos written as scenes. They are drawn on the studio's own machine, so they are quick, and you can edit each scene before it is rendered.",
      ],
    ],
  },
  {
    id: 'credits',
    title: 'Credits',
    body: [
      [
        'p',
        'Each job costs credits for what you asked for: a set price for a picture, a price per second for video, sound and motion graphics. A message to the agent costs what its model costs. The price is always shown before anything runs.',
      ],
      [
        'list',
        [
          'A failed or cancelled job gives its credits back.',
          "A project's analytics show where its credits went.",
          'When you run out, ask an admin for more.',
        ],
      ],
    ],
  },
  {
    id: 'help',
    title: 'When something goes wrong',
    body: [
      [
        'list',
        [
          "A job waiting a long time: the render server may be busy with other people's jobs; the queue at the top left shows where yours is.",
          'A job failed: its card says why in plain words, and its credits came back. Try a shorter clip or a lower quality.',
          'A banner at the top says the studio is under maintenance: new jobs start again when it is over.',
        ],
      ],
    ],
  },
];

function GuideBlock({ block: [kind, content] }: { block: Block }) {
  if (kind === 'p') return <p>{content as string}</p>;
  if (kind === 'tip') {
    return (
      <div className={s['guide-tip']}>
        <Icon name="bulb" />
        <span>{content as string}</span>
      </div>
    );
  }
  const items = (content as string[]).map((c) => <li key={c}>{c}</li>);
  return kind === 'steps' ? (
    <ol className={s['guide-steps']}>{items}</ol>
  ) : (
    <ul className={s['guide-list']}>{items}</ul>
  );
}

export default function GuidePage() {
  const article = useRef<HTMLElement>(null);
  const placed = useRef(new Map<string, HTMLElement>()); // each section, to scroll to it from the contents
  const [lit, setLit] = useState('');

  // The contents follow the reading: the section in view is marked.
  useEffect(() => {
    const seen = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) if (entry.isIntersecting) setLit(entry.target.id.slice('guide-'.length));
      },
      { rootMargin: '-20% 0px -70% 0px' },
    );
    if (article.current) for (const n of article.current.getElementsByClassName(s['guide-section'])) seen.observe(n);
    return () => seen.disconnect();
  }, []);

  return (
    <div className={s['guide-page']}>
      <nav className={s['guide-toc']} aria-label="Contents">
        <div className={css('nav-label')}>Contents</div>
        {SECTIONS.map((section) => (
          <a
            key={section.id}
            href={'#' + section.id}
            className={css(lit === section.id ? 'on' : '')}
            onClick={(e) => {
              e.preventDefault();
              placed.current.get(section.id)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
            }}
          >
            {section.title}
          </a>
        ))}
      </nav>
      <article ref={article} className={s['guide-body']}>
        <h1>Guide</h1>
        <p className={'muted ' + s['guide-lead']}>How Scene.ai works, from a first project to a finished video.</p>
        {SECTIONS.map((section) => (
          <section
            key={section.id}
            id={'guide-' + section.id}
            className={s['guide-section']}
            ref={(n) => {
              if (n) placed.current.set(section.id, n);
              else placed.current.delete(section.id);
            }}
          >
            <h2>{section.title}</h2>
            {section.body.map((block, i) => (
              <GuideBlock key={i} block={block} />
            ))}
          </section>
        ))}
      </article>
    </div>
  );
}

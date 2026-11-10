// Screenshots of pages, for the "same look" checks (not part of the test suites). The build runs in a studio of its own
// with the same account and, with a scenario, the same content made on the fake ComfyUI. Shots taken before a change
// and after it are compared by look-compare.py.
//
//   node tests/look.mjs <out folder> <path>...      e.g. /projects  console:/users  /canvas/{ref}
//
// LOOK_TAB=agent            the canvas panel's tab, as the page remembers it
// LOOK_SCENARIO=canvas      a project with shots, a shot with two takes and a NeuralCore entry; {ref} is its address
// LOOK_SELECT=Second        click the frame of that name before the screenshot
// LOOK_DUMP=aside          also writes the boxes of what is under that selector, to compare the builds
// LOOK_OUT=1               not signed in (the landing and sign-in pages); LOOK_CALM=1 the calm Motion setting; LOOK_FULL=1 the whole page
// LOOK_RUNS=talk            a conversation on the agent's board: talk, plan, ask, done
import { writeFileSync } from 'node:fs';
import { chromium } from '@playwright/test';
import { startFakeComfy } from './support/fake-comfy.mjs';
import { client, startStudio } from './support/studio.mjs';

const out = process.argv[2];
const pages = process.argv.slice(3);
const account = { email: 'look@local.test', name: 'Look', password: 'Look-test-2026-pass' };
const PORT = 8481;

async function seed(studio) {
  const me = client(studio.base);
  await me.call('/api/auth/login', { method: 'POST', json: account });
  const project = (await me.call('/api/projects', { method: 'POST', json: { name: 'Look film' } })).data;
  const workflow = (await me.call('/api/workflows')).data.workflows.find((w) => w.kind === 'image').id;
  const made = {};
  for (const [name, extra] of [
    ['First', {}],
    ['Second', {}],
    ['Take A', { shot_number: 1 }],
    ['Take B', { shot_number: 1 }],
  ]) {
    const form = new FormData();
    form.append('settings', JSON.stringify({ workflow, values: {}, name, project_id: project.id, ...extra }));
    const job = (await me.call('/api/jobs', { method: 'POST', body: form })).data;
    for (let i = 0; i < 120; i++) {
      const found = ((await me.call('/api/jobs')).data.jobs || []).find((j) => j.id === job.id);
      if (found && found.status === 'done') break;
      await new Promise((r) => setTimeout(r, 250));
    }
    const items = (await me.call(`/api/library?project=${project.id}`)).data.items;
    made[name] = items.find((i) => i.job_id === job.id)?.id;
  }
  await me.call('/api/kit', {
    method: 'POST',
    json: { project_id: project.id, name: 'Meera', type: 'character', item: made.First },
  });
  const runs = process.env.LOOK_RUNS && conversation(process.env.LOOK_RUNS, made);
  if (runs) {
    const put = (board, data) =>
      me.call(`/api/boards/${board}?project=${project.id}`, { method: 'PUT', json: { project: project.id, data } });
    await put('agent', {
      tabs: [{ id: 'look', name: 'Agent 1', created: 1, updated: 1, spent: null }],
      open: ['look'],
      active: 'look',
    });
    await put('agent-look', { runs });
  }
  return project;
}

function conversation(kind, made) {
  const base = {
    instruction: 'A red kite',
    parts: [{ text: 'A red kite' }],
    reply: '',
    activity: [],
    seconds: 0,
    chips: {},
    steps: [],
    total: 0,
    state: 'answered',
    at: 1700000000000,
    ui: {},
  };
  const step = (extra) => ({
    name: 'Kite',
    kind: 'image',
    credits: 40,
    prompt: 'A red kite over green hills',
    workflow_title: 'FLUX.2',
    settings: { workflow: 'image/flux' },
    current: { orientation: 'landscape', resolution: 720 },
    menu: { workflows: [], shapes: true, resolutions: [720, 1080], durations: [] },
    uses: [],
    ...extra,
  });
  if (kind === 'talk')
    return [
      {
        ...base,
        seconds: 12,
        activity: [{ type: 'activity', icon: 'book', text: 'Read the script', at: 3 }],
        reply: 'Here is **the plan**:\n\n- one\n- two\n\n```csv\nShot,Mood\n1,calm\n```',
        chips: {},
      },
    ];
  if (kind === 'plan')
    return [
      {
        ...base,
        state: 'proposed',
        total: 80,
        reply: 'Two shots.',
        steps: [step({ open: true }), step({ name: 'Hill', prompt: 'A green hill' })],
      },
    ];
  if (kind === 'ask')
    return [
      {
        ...base,
        reply: 'Two things.',
        questions: [
          { text: 'Which mood?', options: ['Calm', 'Bright'], details: ['Soft light', 'Hard light'], default: 'Calm' },
          { text: 'How long?', options: ['5s', '10s'] },
        ],
      },
    ];
  return [
    {
      ...base,
      state: 'approved',
      total: 40,
      reply: 'Made.',
      steps: [step({ job: 'gone', made: made.Second }), step({ name: 'Other', job: 'gone', made: made['Take A'] })],
    },
  ];
}

const browser = await chromium.launch();
const fake = process.env.LOOK_SCENARIO ? await startFakeComfy({ port: 8399, renderMs: 200 }) : null;
{
  const port = PORT;
  const studio = await startStudio({ port, consolePort: port + 9, comfyUrl: fake ? fake.url : undefined });
  try {
    await client(studio.base).call('/api/auth/register', { method: 'POST', json: account });
    const project = process.env.LOOK_SCENARIO ? await seed(studio) : null;
    const page = await browser.newPage({ viewport: { width: 1280, height: 800 } });
    if (process.env.LOOK_TAB)
      await page.addInitScript((tab) => localStorage.setItem('scene.panel.tab', tab), process.env.LOOK_TAB);
    if (process.env.LOOK_CALM) await page.addInitScript(() => localStorage.setItem('scene.motion', 'calm'));
    if (!process.env.LOOK_OUT) {
      await page.request.post(studio.base + '/api/auth/login', { data: account });
      await page.request.post(studio.console + '/api/console/login', { data: account }); // the first account: an admin
    }
    for (const asked of pages) {
      // "console:/users" is a section of the admin console, on its own port
      const path = asked.replace(/^console:/, '').replace('{ref}', project ? project.ref : '');
      await page.goto((asked.startsWith('console:') ? studio.console : studio.base) + path);
      await page.waitForTimeout(Number(process.env.LOOK_WAIT) || 1500);
      if (process.env.LOOK_SELECT) {
        await page.getByTitle(process.env.LOOK_SELECT, { exact: true }).first().click();
        await page.waitForTimeout(600);
      }
      const name =
        asked.replace(/[/:{}]/g, '_') +
        (process.env.LOOK_TAB || '') +
        (process.env.LOOK_SELECT ? '_sel' : '') +
        (process.env.LOOK_RUNS ? '_' + process.env.LOOK_RUNS : '');
      await page.screenshot({ path: `${out}/${name}.png`, fullPage: !!process.env.LOOK_FULL });
      if (process.env.LOOK_DUMP) {
        // every element under the selector with its box, to find what moved between the two builds
        const rows = await page.evaluate(
          (sel) =>
            [...document.querySelector(sel).querySelectorAll('*')]
              .map((n) => {
                const r = n.getBoundingClientRect();
                const c = getComputedStyle(n);
                return [
                  n.tagName,
                  Math.round(r.y * 10) / 10,
                  Math.round(r.height * 10) / 10,
                  c.fontSize,
                  c.marginTop,
                  c.paddingTop,
                  (n.childElementCount ? '' : n.textContent).slice(0, 24),
                ].join(' ');
              })
              .join('\n'),
          process.env.LOOK_DUMP,
        );
        writeFileSync(`${out}/${name}.txt`, rows);
      }
    }
  } finally {
    studio.stop();
  }
}
await browser.close();
await fake?.stop();

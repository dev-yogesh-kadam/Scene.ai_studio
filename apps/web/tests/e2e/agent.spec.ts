// How the agent's panel behaves (written against the build before the agent became React components, and kept for the
// rewrite). Conversations are put on their boards as the studio saves them; a reply from the model is answered here, on
// the network, so no language model is asked.

import { expect, test, type Page, type Route } from '@playwright/test';
import { seedCanvas, type Seeded } from './seed';
import { signIn } from './signin';
import { watch } from './watch';

let seeded: Seeded;

const run = (extra: Record<string, unknown>) => ({
  instruction: 'A red kite',
  parts: [{ text: 'A red kite' }],
  reply: '',
  thought: '',
  activity: [],
  seconds: 0,
  chips: {},
  memoryUsed: [],
  steps: [],
  total: 0,
  state: 'answered',
  at: 1_700_000_000_000,
  ui: {},
  llm: null,
  question: null,
  questions: [],
  continues: false,
  context: null,
  ...extra,
});

const step = (extra: Record<string, unknown> = {}) => ({
  name: 'Kite',
  kind: 'image',
  credits: 40,
  prompt: 'A red kite over green hills',
  workflow_title: 'FLUX.2',
  settings: { workflow: 'image/flux', values: {} },
  current: { orientation: 'landscape', resolution: 720 },
  menu: { workflows: [], shapes: true, resolutions: [720, 1080], durations: [] },
  uses: [],
  ...extra,
});

/** A conversation on the boards of a fresh project, and the panel open on it. */
async function openWith(page: Page, name: string, runs: unknown[]) {
  const place = (await (await page.request.post('/api/projects', { data: { name } })).json()) as {
    id: number;
    ref: string;
  };
  const id = 'tab1';
  const put = (board: string, data: unknown) =>
    page.request.put(`/api/boards/${board}?project=${place.id}`, { data: { project: place.id, data } });
  await put('agent', {
    tabs: [{ id, name: 'Agent 1', created: 1, updated: 1, spent: null }],
    open: [id],
    active: id,
  });
  await put('agent-' + id, { runs });
  await page.goto(`/canvas/${place.ref}`);
  await expect(
    page
      .getByRole('textbox', { name: 'Message' })
      .or(page.getByLabel('What to change in this plan'))
      .or(page.getByRole('group', { name: /A question from the agent|the check found/i })),
  ).toBeVisible({ timeout: 15_000 });
  return place;
}

/** Answers the next message to the agent with this reply, as lines of JSON. */
async function answerWith(page: Page, plan: Record<string, unknown>) {
  await page.route('**/api/agent/plan', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/x-ndjson',
      body:
        JSON.stringify({ type: 'status', text: 'Reading' }) +
        '\n' +
        JSON.stringify({ type: 'activity', icon: 'book', text: 'Read the script' }) +
        '\n' +
        JSON.stringify({ type: 'plan', steps: [], total: 0, activity: [], chips: {}, seconds: 2, ...plan }) +
        '\n',
    }),
  );
}

const box = (page: Page) => page.getByRole('textbox', { name: 'Message' });

test.beforeAll(async ({ browser }) => {
  const page = await browser.newPage();
  await signIn(page);
  seeded = await seedCanvas(page, 'Agent test');
  await page.close();
});

test.beforeEach(async ({ page }) => {
  await signIn(page);
  await page.addInitScript(() => localStorage.setItem('scene.panel.tab', 'agent'));
});

test('a saved conversation opens: its message, work, reply with bold, a list, a table and a named picture', async ({
  page,
}) => {
  const problems = watch(page);
  await openWith(page, 'Agent old', [
    run({
      seconds: 12,
      activity: [
        { type: 'activity', icon: 'book', text: 'Read the script', at: 3 },
        { type: 'thought', text: 'It wants a kite.', seconds: 4 },
      ],
      reply:
        'Here is **the plan**:\n\n- one\n- two\n\nThe kite: [[item:' +
        seeded.items.Second +
        ']]\n\n```csv\nShot,Mood\n1,calm\n```',
      chips: { ['item:' + seeded.items.Second]: { name: 'Second', kind: 'image' } },
    }),
  ]);
  await expect(page.getByText('A red kite', { exact: true })).toBeVisible();
  await expect(page.getByText('the plan', { exact: true })).toBeVisible();
  await expect(page.getByRole('listitem').filter({ hasText: 'two' })).toBeVisible();
  await expect(page.getByRole('cell', { name: 'calm' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Copy the table' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Copy the reply' })).toBeVisible();
  // the work folds: its title, and opened, its rows
  const work = page.getByRole('button', { name: /Worked 12s/ });
  await expect(work).toHaveAttribute('aria-expanded', 'false');
  await work.click();
  await expect(page.getByText('Read the script', { exact: true }).first()).toBeVisible();
  await expect(page.getByRole('button', { name: /Thought for 4s/ })).toBeVisible();
  expect(problems.filter((p) => !p.includes('/api/agent/status'))).toEqual([]);
});

test('a new conversation offers starters that fill the message box', async ({ page }) => {
  await openWith(page, 'Agent new', []);
  await expect(page.getByRole('heading', { name: 'What are we making?' })).toBeVisible();
  await page.getByRole('button', { name: /A product shot of a perfume bottle/ }).click();
  await expect(box(page)).toHaveText('A product shot of a perfume bottle turning on black glass');
});

test('a message goes to the agent, its work and reply show, and the box empties', async ({ page }) => {
  await answerWith(page, {
    reply: 'Done **thinking**.',
    activity: [{ type: 'activity', icon: 'book', text: 'Read the script' }],
  });
  await openWith(page, 'Agent send', []);
  await box(page).click();
  await page.keyboard.type('Hello agent');
  await page.keyboard.press('Enter');
  await expect(page.getByText('thinking', { exact: true })).toBeVisible({ timeout: 15_000 });
  await expect(page.getByText('Hello agent', { exact: true })).toBeVisible();
  await expect(box(page)).toHaveText('');
  // kept on its board, in the shape it was always saved in
  const place = (await (await page.request.get('/api/projects')).json()) as {
    projects: { id: number; name: string }[];
  };
  const id = place.projects.find((p) => p.name === 'Agent send')!.id;
  await expect
    .poll(async () => {
      const board = (await (await page.request.get(`/api/boards/agent-tab1?project=${id}`)).json()) as {
        data: { runs?: { instruction: string; reply: string; state: string; steps: unknown[] }[]; direction?: string };
      };
      return board.data.runs?.map((r) => [r.instruction, r.reply, r.state, r.steps.length]);
    })
    .toEqual([['Hello agent', 'Done **thinking**.', 'answered', 0]]);
});

test('the bulb, the workflows (sliders) and the retry switch: each is kept, and goes with the message', async ({
  page,
}) => {
  const problems = watch(page);
  const sent: Record<string, unknown>[] = [];
  await page.route('**/api/agent/plan', (route) => {
    sent.push(route.request().postDataJSON() as Record<string, unknown>);
    return route.fulfill({
      status: 200,
      contentType: 'application/x-ndjson',
      body:
        JSON.stringify({ type: 'plan', steps: [], total: 0, activity: [], chips: {}, seconds: 1, reply: 'Ok.' }) + '\n',
    });
  });
  await openWith(page, 'Agent knobs', []);

  // the bulb: explain more, per tab
  const bulb = page.getByRole('button', { name: /^Explain more: off/ });
  await expect(bulb).toHaveAttribute('aria-pressed', 'false');
  await bulb.click();
  await expect(page.getByRole('button', { name: /^Explain more: on/ })).toHaveAttribute('aria-pressed', 'true');

  // the sliders: the workflows this chat uses
  await page.getByRole('button', { name: 'Workflows for this chat: the agent chooses' }).click();
  const menu = page.getByRole('menu');
  await expect(menu.getByText('Workflows for this chat')).toBeVisible();
  const first = menu.getByRole('menuitemcheckbox').first();
  await expect(first).toHaveAttribute('aria-checked', 'false');
  await first.click();
  await expect(page.getByRole('menu').getByRole('menuitemcheckbox').first()).toHaveAttribute('aria-checked', 'true');
  await page.keyboard.press('Escape');
  await expect(page.getByRole('button', { name: 'Workflows for this chat: 1 chosen' })).toBeVisible();

  await box(page).click();
  await page.keyboard.type('Make it teach');
  await page.keyboard.press('Enter');
  await expect(page.getByText('Ok.', { exact: true })).toBeVisible({ timeout: 15_000 });
  expect(sent.at(-1)).toMatchObject({ explain: true });
  expect(sent.at(-1)!.workflows).toHaveLength(1);

  // the retry switch, under the permission: the user's, on the server
  const retry = async () =>
    ((await (await page.request.get('/api/agent/preferences')).json()) as { retry_once: boolean }).retry_once;
  expect(await retry()).toBe(false);
  await page.getByRole('button', { name: /Generation permission/ }).click();
  const item = page.getByRole('menuitemcheckbox', { name: /Retry a failed shot once by itself/ });
  await expect(item).toHaveAttribute('aria-checked', 'false');
  await item.click();
  await expect.poll(retry).toBe(true);
  await page.getByRole('button', { name: /Generation permission/ }).click();
  await expect(page.getByRole('menuitemcheckbox', { name: /Retry a failed shot/ })).toHaveAttribute(
    'aria-checked',
    'true',
  );
  await page.getByRole('menuitemcheckbox', { name: /Retry a failed shot/ }).click();
  await expect.poll(retry).toBe(false);
  expect(problems.filter((p) => !p.includes('/api/agent/status'))).toEqual([]);
});

test('a frame added to the message goes as a chip, and the message names it', async ({ page }) => {
  await page.route('**/api/agent/plan', async (route) => {
    const sent = route.request().postDataJSON() as { instruction: string; selection: number[] };
    await route.fulfill({
      status: 200,
      contentType: 'application/x-ndjson',
      body:
        JSON.stringify({
          type: 'plan',
          reply: `Got ${sent.instruction} / ${sent.selection.length}`,
          steps: [],
          total: 0,
        }) + '\n',
    });
  });
  await page.goto(`/canvas/${seeded.ref}`);
  await expect(box(page)).toBeVisible({ timeout: 15_000 });
  await page.getByRole('button', { name: 'Add Second to the chat' }).click({ force: true });
  await expect(page.getByRole('button', { name: 'Remove Second' })).toBeAttached();
  await page.keyboard.type('darker');
  await page.keyboard.press('Enter');
  await expect(page.getByText('Got @1 darker / 1')).toBeVisible({ timeout: 15_000 });
});

test('a plan waits above the box: a step opens, a step is left out, Stop turns it down', async ({ page }) => {
  await openWith(page, 'Agent plan', [
    run({
      state: 'proposed',
      total: 80,
      reply: 'Two shots.',
      steps: [step(), step({ name: 'Hill', prompt: 'A green hill' })],
    }),
  ]);
  await expect(page.getByRole('button', { name: 'Approve 2 image generations' })).toBeVisible();
  await expect(page.getByText('Waiting for your approval · 2 images')).toBeVisible();
  await expect(box(page)).toBeHidden(); // the plan's card has the box
  await expect(page.getByRole('button', { name: /Generate all/ })).toContainText('80');

  await page.getByRole('button', { name: 'Show the whole step' }).first().click();
  await expect(page.getByTitle('Aspect ratio')).toBeVisible();
  await page.getByRole('button', { name: 'Skip', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Approve 1 image generation' })).toBeVisible();
  await expect(page.getByText('Left out', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Include', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Approve 2 image generations' })).toBeVisible();

  await page.getByLabel('What to change in this plan').fill('make it blue');
  await expect(page.getByRole('button', { name: 'Send change' })).toBeVisible();
  await page.getByLabel('What to change in this plan').fill('');
  await page.getByRole('button', { name: /^Stop/ }).click();
  await expect(page.getByRole('button', { name: /Generation.*Cancelled/ })).toBeVisible();
  await expect(box(page)).toBeVisible();
});

test('questions are answered on a card above the box, by number or Enter', async ({ page }) => {
  await answerWith(page, { reply: 'Thanks.' });
  await openWith(page, 'Agent ask', [
    run({
      reply: 'Two things.',
      questions: [
        { text: 'Which mood?', options: ['Calm', 'Bright'], details: ['Soft light', 'Hard light'], default: 'Calm' },
        { text: 'How long?', options: ['5s', '10s'] },
      ],
    }),
  ]);
  const card = page.getByRole('group', { name: 'A question from the agent' });
  await expect(card).toContainText('Which mood?');
  await expect(card).toContainText('1 of 2');
  await expect(card).toContainText('REC');
  await expect(page.getByText('Asking 2 questions')).toBeVisible();
  await card.getByRole('radio', { name: /Bright/ }).click();
  await expect(card).toContainText('How long?');
  await card.getByRole('radio', { name: /10s/ }).click();
  const asked = page.waitForRequest('**/api/agent/plan');
  await card.getByRole('button', { name: /Submit/ }).click();
  // both answers go in one message
  const message = JSON.stringify((await asked).postDataJSON());
  expect(message).toContain('Bright');
  expect(message).toContain('10s');
  await expect(page.getByText('Thanks.', { exact: true })).toBeVisible({ timeout: 15_000 });
  await expect(page.getByText('Bright', { exact: true }).first()).toBeVisible();
});

test('what a plan made shows as results, with thumbs and a way to the canvas', async ({ page }) => {
  const id = seeded.items.Second;
  await openWith(page, 'Agent results', [
    run({ state: 'approved', total: 40, reply: 'Made.', steps: [step({ job: 'gone', made: id })] }),
  ]);
  await expect(page.getByTitle('Kite: show it on the canvas')).toBeVisible();
  await expect(page.getByText('· 1/1')).toBeVisible();
  const up = page.getByRole('button', { name: 'Thumbs up' });
  await expect(up).toHaveAttribute('aria-pressed', 'false');
  await page.getByRole('button', { name: 'How it was made' }).click({ force: true });
  await expect(page.getByRole('menu').getByText('A red kite over green hills')).toBeVisible();
});

test('a failed check asks about a retake on a card; Keep it ends it', async ({ page }) => {
  const id = seeded.items.Second;
  await openWith(page, 'Agent check', [
    run({
      state: 'approved',
      total: 40,
      reply: 'Made.',
      steps: [
        step({
          kind: 'video',
          job: 'gone',
          made: id,
          review: { passed: false, problem: 'The kite is green.' },
          retake: { prompt: 'A red kite', credits: 40, settings: {} },
        }),
      ],
    }),
  ]);
  const card = page.getByRole('group', { name: 'Shots the check found a problem with' });
  await expect(card).toContainText('The kite is green.');
  await expect(card.getByRole('button', { name: /Retake/ })).toContainText('40 cr');
  await card.getByRole('button', { name: /Keep it/ }).click();
  await expect(card).toBeHidden();
  await expect(page.getByText('Kept as it is.')).toBeVisible();
});

test('conversations are tabs: a new one, renamed, closed, and all kept in the history', async ({ page }) => {
  await openWith(page, 'Agent tabs', []);
  await expect(page.getByRole('tab', { name: /Agent 1/ })).toHaveAttribute('aria-selected', 'true');
  await expect(page).toHaveURL(/agent=AGTtab1/);
  await page.getByRole('button', { name: 'New conversation' }).click();
  const second = page.getByRole('tab', { name: /Agent 2/ });
  await expect(second).toHaveAttribute('aria-selected', 'true');
  await second.dblclick();
  const name = page.getByRole('textbox', { name: 'Name of the conversation' });
  await name.fill('Teaser');
  await name.press('Enter');
  await expect(page.getByRole('tab', { name: /Teaser/ })).toBeVisible();
  await page.getByRole('button', { name: 'Close Teaser' }).click();
  await expect(page.getByRole('tab', { name: /Teaser/ })).toHaveCount(0);
  await page.getByRole('button', { name: 'All conversations' }).click();
  const menu = page.getByRole('menu');
  await expect(menu.getByText('Teaser')).toBeVisible();
  await expect(menu.getByText(/closed/)).toBeVisible();
  await menu.getByRole('button', { name: 'Delete Teaser' }).click();
  await page
    .getByRole('dialog', { name: 'Delete "Teaser"?' })
    .getByRole('button', { name: 'Delete conversation' })
    .click();
  await page.getByRole('button', { name: 'All conversations' }).click();
  await expect(page.getByRole('menu').getByText('Teaser')).toHaveCount(0);
});

test('the permission and the model are chosen under the box, kept for the user, and / lists the skills', async ({
  page,
  browser,
}) => {
  const status = (route: Route) =>
    route.fulfill({
      json: {
        online: true,
        model: 'claude-a',
        models: ['claude-a', 'claude-b'],
        prices: { 'claude-b': 3 },
        efforts: { 'claude-a': { levels: ['low', 'high'], default: 'low' } },
      },
    });
  await page.route('**/api/agent/status', status);
  const kept = async () =>
    (await (await page.request.get('/api/agent/preferences')).json()) as {
      model: string | null;
      effort: Record<string, string>;
      permission: string;
    };
  const place = await openWith(page, 'Agent pick', []);
  await page.getByRole('button', { name: /Generation permission: Always ask/ }).click();
  await page.getByRole('menuitemradio', { name: /Allow all/ }).click();
  await expect(page.getByRole('button', { name: /Generation permission: Allow all/ })).toBeVisible();
  await expect.poll(async () => (await kept()).permission).toBe('all'); // the user's, on the server

  await page.getByRole('button', { name: /claude-a/ }).click();
  await page.getByRole('radio', { name: 'High' }).click();
  await expect.poll(async () => (await kept()).effort['claude-a']).toBe('high');
  await page.getByRole('button', { name: /claude-a/ }).click();
  await page.getByRole('menuitemradio', { name: /claude-b/ }).click();
  await expect(page.getByRole('button', { name: /claude-b/ })).toBeVisible();
  await expect.poll(async () => (await kept()).model).toBe('claude-b');
  expect(await page.evaluate(() => Object.keys(localStorage).filter((k) => k.startsWith('scene.agent')))).toEqual([]);

  // Another browser of the same user: the same choices
  const other = await browser.newPage();
  await signIn(other);
  await other.route('**/api/agent/status', status);
  await other.goto(`/canvas/${place.ref}`);
  await other.getByRole('complementary', { name: 'Make something' }).getByRole('button', { name: 'Agent' }).click();
  await expect(other.getByRole('button', { name: /Generation permission: Allow all/ })).toBeVisible({
    timeout: 15_000,
  });
  await expect(other.getByRole('button', { name: /claude-b/ })).toBeVisible();
  await other.close();
  // back as they were, for the tests after this one
  await page.request.put('/api/agent/preferences', {
    data: { permission: 'always', model: null, effort: { 'claude-a': 'low' } },
  });

  await box(page).click();
  await page.keyboard.type('/');
  await expect(page.getByRole('listbox')).toBeVisible();
  await expect(page.getByRole('option').first()).toBeVisible();
  await page.keyboard.press('Enter');
  await expect(box(page)).toContainText(/^\/[a-z0-9-]+/);
});

test('"ok" typed under a plan is the Approve button, and the plan goes to the studio', async ({ page }) => {
  await openWith(page, 'Agent ok', [
    run({ state: 'proposed', total: 0, reply: 'One shot.', steps: [step({ credits: 0 })] }),
  ]);
  const note = page.getByLabel('What to change in this plan');
  await note.fill('ok');
  await note.press('Enter');
  await expect(page.getByText('Waiting for your approval')).toBeHidden({ timeout: 15_000 });
});

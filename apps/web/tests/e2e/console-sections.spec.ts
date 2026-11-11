// How the admin console's sections behave (written against the build before they became React components, and kept for
// the rewrite): tables, filters, the drawer of a person or a job, dialogs, forms that save, and the search.

import { expect, test, type Cookie, type Locator, type Page } from '@playwright/test';
import { CONSOLE } from '../../playwright.config';
import { ACCOUNTS } from './accounts';
import { axe } from './axe';
import { done, makeImage, signIn } from './signin';

let kept: Cookie[] | null = null; // one sign-in for the file: the console allows only so many

async function open(page: Page, section: string) {
  if (kept) await page.context().addCookies(kept);
  else {
    const { email, password } = ACCOUNTS.admin;
    const answer = await page.request.post(CONSOLE + '/api/console/login', { data: { email, password } });
    expect(answer.ok()).toBe(true);
    kept = await page.context().cookies();
  }
  await page.goto(`${CONSOLE}/${section}`);
}

const main = (page: Page) => page.getByRole('main');
// A card of a section, by its heading (the heading sits in the card's head).
const card = (page: Page, title: string) =>
  main(page).getByRole('heading', { name: title, exact: true, level: 2 }).locator('xpath=../..');
// A form's box, by the words over it (they are not a <label> of it).
const box = (within: Locator, words: string) =>
  within
    .locator('.field')
    .filter({ has: within.page().getByText(words, { exact: true }) })
    .locator('input, textarea, select');

test.beforeAll(async ({ browser }) => {
  const page = await browser.newPage();
  await signIn(page);
  const job = await makeImage(page, { name: 'Console job' });
  await done(page, job.id);
  await page.close();
});

test("Users: search, the filter, a person's drawer, and credits given from it", async ({ page }) => {
  await open(page, 'users');
  await expect(main(page).getByText('e2e-user@local.test')).toBeVisible();
  await main(page).getByPlaceholder('Search name or email').fill('e2e-user');
  await expect(main(page).getByText('e2e-admin@local.test')).toBeHidden();
  await expect(main(page).getByText('1 user', { exact: true })).toBeVisible();
  await main(page).getByRole('button', { name: 'Out of credits' }).click();
  await expect(main(page).getByText('No users match.')).toBeVisible();
  await main(page).getByRole('button', { name: 'All', exact: true }).click();

  await main(page).getByText('e2e-user@local.test').click();
  const drawer = page.getByRole('dialog', { name: 'User' });
  await expect(drawer.getByText('Latest jobs')).toBeVisible();
  await expect(drawer.getByText('Daily spending limit')).toBeVisible();
  await drawer.getByRole('button', { name: 'Give or take credits' }).click();
  const dialog = page.locator('dialog[open]');
  await expect(dialog.getByRole('heading', { name: 'Give or take credits' })).toBeVisible();
  const go = dialog.getByRole('button', { name: 'Give 500 credits' });
  await expect(go).toBeDisabled(); // a reason is asked for
  await dialog.getByPlaceholder(/Shown in the credit log/).fill('A test');
  await expect(dialog.getByText('New balance')).toBeVisible();
  await go.click();
  await expect(dialog).toBeHidden();
  await expect(drawer.getByText('A test')).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(drawer).toBeHidden();
});

test("Jobs: by status, and a job's drawer with what it was", async ({ page }) => {
  await open(page, 'jobs');
  await expect(main(page).getByText('Nothing is running or waiting.')).toBeVisible();
  await main(page).getByRole('button', { name: 'Done', exact: true }).click();
  await main(page).getByText('Console job').first().click();
  const drawer = page.getByRole('dialog', { name: 'Job' });
  await expect(drawer.getByText('Render time')).toBeVisible();
  await expect(drawer.getByText('Job id')).toBeVisible();
  await drawer.getByRole('button', { name: 'Close' }).click();
  await expect(drawer).toBeHidden();
});

test('Credits: what happened, by reason, and the window for everyone', async ({ page }) => {
  await open(page, 'credits');
  await expect(main(page).getByText('Held by users now')).toBeVisible();
  await main(page).getByRole('button', { name: 'Charges' }).click();
  await expect(main(page).getByRole('cell', { name: 'Generation' }).first()).toBeVisible();
  await main(page).getByRole('button', { name: 'Give everyone credits' }).click();
  const dialog = page.locator('dialog[open]');
  await expect(dialog.getByRole('button', { name: 'Give everyone 200 credits' })).toBeDisabled();
  await dialog.getByRole('button', { name: 'Cancel' }).click();
  await expect(dialog).toBeHidden();
});

test('Audit log: search, and the seals hold', async ({ page }) => {
  await open(page, 'audit');
  await main(page).getByPlaceholder('Search person, action or target').fill('zzzz-nothing');
  await expect(main(page).getByText('No entries match.')).toBeVisible();
  await main(page).getByRole('button', { name: 'Check the seals' }).click();
  await expect(main(page).getByText(/sealed entries hold|No sealed entries yet/)).toBeVisible();
});

test('Settings: a save says so, and the announcement is published and removed', async ({ page }) => {
  await open(page, 'settings');
  await main(page).getByRole('button', { name: 'Save' }).first().click();
  await expect(main(page).getByText('Saved.').first()).toBeVisible();
  await main(page)
    .getByPlaceholder(/Renders are down for maintenance/)
    .fill('Back soon');
  await main(page).getByRole('button', { name: 'Publish' }).click();
  await expect(main(page).getByText(/Showing to everyone until/)).toBeVisible();
  await page.reload();
  await main(page).getByRole('button', { name: 'Remove', exact: true }).first().click();
  await expect(main(page).getByText('Removed.')).toBeVisible();
});

test('Roles: a new role made with what it may see, then deleted', async ({ page }) => {
  await open(page, 'roles');
  await main(page).getByText('New role').click();
  const card = main(page).locator('details[open]');
  await card.getByRole('textbox').first().fill('Tester');
  await card.getByRole('checkbox', { name: 'See Users' }).check();
  await card.getByRole('button', { name: 'Make the role' }).click();
  const made = main(page).locator('details', { hasText: 'Tester' });
  await expect(made).toBeVisible();
  await made.getByRole('heading', { name: 'Tester' }).click();
  await expect(made.getByRole('checkbox', { name: 'See Users' })).toBeChecked();
  await made.getByRole('button', { name: 'Delete' }).click();
  await page
    .locator('dialog[open]')
    .getByRole('button', { name: /^(OK|Delete|Yes)/ })
    .last()
    .click();
  await expect(main(page).locator('details', { hasText: 'Tester' })).toHaveCount(0);
});

test('Servers: a form opens to add one, and Cancel leaves it', async ({ page }) => {
  await open(page, 'endpoints');
  await main(page).getByRole('button', { name: 'Add' }).first().click();
  await expect(main(page).getByPlaceholder('Zoro, Kaggle…')).toBeVisible();
  await main(page).getByRole('button', { name: 'Cancel' }).click();
  await expect(main(page).getByPlaceholder('Zoro, Kaggle…')).toBeHidden();
});

test('Servers: the Claude connection card, and the bridge refused without its key', async ({ page }) => {
  await open(page, 'endpoints');
  const claude = card(page, 'Claude connection');
  // the test studio has no `claude` and no key: it says so, and nothing reaches Anthropic or LUFI
  await expect(claude.getByTestId('claude-status')).toContainText('Not working');
  await expect(claude.getByLabel('Anthropic API key')).toHaveValue('');
  await claude.getByRole('button', { name: 'LUFI bridge' }).click();
  await claude.getByLabel('Bridge address').fill('http://127.0.0.1:9');
  await claude.getByRole('button', { name: 'Save' }).click();
  await expect(claude.getByText('The LUFI bridge needs its address and its key.')).toBeVisible();
  await expect(main(page).getByText('Testing on a personal Claude subscription')).toHaveCount(0); // nothing changed
});

test('Moderation: what is made is listed, and the words are saved', async ({ page }) => {
  await open(page, 'moderation');
  await expect(main(page).getByRole('heading', { name: /To review/ })).toBeVisible();
  await main(page).getByRole('button', { name: 'Refused prompts' }).click();
  await expect(main(page).getByText('None refused.')).toBeVisible();
  await main(page).getByPlaceholder('One word or phrase a line').fill('forbiddenword');
  await main(page).getByRole('button', { name: 'Save' }).click();
  await expect(main(page).getByPlaceholder('One word or phrase a line')).toHaveValue('forbiddenword');
});

test('Sessions: the list, and its filter', async ({ page }) => {
  await open(page, 'sessions');
  await expect(main(page).getByRole('heading', { name: 'Claude sessions' })).toBeVisible();
  await expect(main(page).getByRole('button', { name: 'Watch side by side' })).toBeDisabled();
  await main(page).getByRole('button', { name: 'Idle', exact: true }).click();
  await expect(main(page).getByText(/No session matches|No agent tab/)).toBeVisible();
});

test('System: its cards, and Check now', async ({ page }) => {
  await open(page, 'system');
  for (const name of [
    'Alerts',
    'Maintenance',
    'Render server',
    'Agent model',
    'Scene.ai app',
    'Disk',
    'Backups',
    'Storage by user',
    'Records',
  ])
    await expect(main(page).getByRole('heading', { name, exact: true })).toBeVisible();
  // the studio's database is PostgreSQL: so named, and the steps to put a copy back are pg_restore's
  await expect(main(page).getByText(/ · PostgreSQL$/)).toBeVisible();
  await expect(main(page).getByText(/pg_restore -h localhost/)).toBeVisible();
  await expect(main(page).getByText(/SQLite|scene\.db/)).toHaveCount(0);
  await main(page).getByRole('button', { name: 'Check now' }).click();
  await expect(main(page).getByRole('button', { name: 'Check now' })).toBeEnabled();
});

test('System, Checks: each check a row, ok or its problem (the checks added to the answer here), and no axe problem', async ({
  page,
}) => {
  await page.route('**/api/admin/system', async (route) => {
    const real = await route.fetch();
    const now = Date.now() / 1000;
    const json = {
      ...((await real.json()) as Record<string, unknown>),
      checks: {
        database: { online: true, seconds: 0.002, detail: '' },
        render: { online: false, url: 'http://render:8188', since: now - 600, detail: '' },
        model: {
          mode: 'lufi_bridge',
          online: true,
          detail: '',
          claude_version: '2.1.3',
          signed_in: true,
          running: 1,
          limit: 4,
        },
        programs: {
          ffmpeg: { ready: true, detail: '' },
          motion: { ready: false, detail: 'Run npm install in motion/' },
        },
        disk: { folder: 'C:/Scene/Outputs', free: 50e9, total: 100e9 },
        backup: {
          folder: 'E:/b',
          last: now - 3600,
          check: { ok: true, detail: 'restored', when: now },
          restore_test: null,
        },
        langfuse: { in_use: false },
      },
    };
    await route.fulfill({ response: real, json });
  });
  await open(page, 'system');
  const checks = card(page, 'Checks');
  await expect(checks.getByText('2 problems')).toBeVisible();
  await expect(checks.getByRole('row', { name: /Render server.*Problem.*http:\/\/render:8188/ })).toBeVisible();
  await expect(checks.getByRole('row', { name: /Motion pages.*Run npm install in motion/ })).toBeVisible();
  await expect(
    checks.getByRole('row', { name: /Agent model.*OK.*LUFI bridge · Claude Code 2\.1\.3 · signed in · 1 of 4/ }),
  ).toBeVisible();
  await expect(checks.getByRole('row', { name: /Restore test.*Not run yet/ })).toBeVisible();
  await page.waitForLoadState('networkidle');
  expect(await axe(page, 'console system, checks')).toEqual([]);
});

test('System, Guardrails: the stop asks first, stops and starts again; a limit out of range is not saved', async ({
  page,
}) => {
  await open(page, 'system');
  const guard = card(page, 'Guardrails');
  await expect(guard.getByText('Running', { exact: true })).toBeVisible();
  await guard.getByLabel('What users are told while it is stopped').fill('Back at six.');
  await guard.getByRole('button', { name: 'Stop the studio' }).click();
  const question = page.getByRole('dialog', { name: 'Stop the whole studio?' });
  await question.getByRole('button', { name: 'Cancel' }).click();
  await expect(guard.getByText('Running', { exact: true })).toBeVisible();
  await guard.getByRole('button', { name: 'Stop the studio' }).click();
  await question.getByRole('button', { name: 'Stop the studio' }).click();
  await expect(guard.getByText('Stopped', { exact: true })).toBeVisible();
  await expect(guard.getByText('Back at six.').first()).toBeVisible();
  const shown = async () =>
    (await (await page.request.get(CONSOLE + '/api/admin/guardrails')).json()) as {
      stop: { text: string } | null;
      limits: Record<string, number>;
    };
  expect((await shown()).stop?.text).toBe('Back at six.');
  await card(page, 'Guardrails').getByRole('button', { name: 'Start the studio again' }).click();
  await expect(card(page, 'Guardrails').getByText('Running', { exact: true })).toBeVisible();
  expect((await shown()).stop).toBeNull();

  const sessions = card(page, 'Guardrails').getByLabel('Live agent sessions one user may hold');
  const before = (await shown()).limits.guard_sessions_per_user;
  await sessions.fill('99');
  await expect(card(page, 'Guardrails').getByText(/must be 1 to 50/)).toBeVisible();
  await expect(card(page, 'Guardrails').getByRole('button', { name: 'Save limits' })).toBeDisabled();
  await sessions.fill('4');
  await card(page, 'Guardrails').getByRole('button', { name: 'Save limits' }).click();
  await expect.poll(async () => (await shown()).limits.guard_sessions_per_user).toBe(4);
  // back as it was
  await page.request.put(CONSOLE + '/api/admin/guardrails', { data: { limits: { guard_sessions_per_user: before } } });
});

test('Settings, Langfuse: "keep the words in Langfuse only" is saved, and back', async ({ page }) => {
  await open(page, 'settings');
  const lf = card(page, 'Langfuse');
  const owns = lf.getByRole('checkbox', { name: 'Keep the words in Langfuse only' });
  await expect(owns).not.toBeChecked();
  await owns.check();
  await lf.getByRole('button', { name: 'Save' }).click();
  await expect(lf.getByText('Saved.')).toBeVisible();
  const kept = async () =>
    ((await (await page.request.get(CONSOLE + '/api/admin/settings')).json()) as { langfuse_owns_words: boolean })
      .langfuse_owns_words;
  expect(await kept()).toBe(true);
  await page.reload();
  await expect(card(page, 'Langfuse').getByRole('checkbox', { name: 'Keep the words in Langfuse only' })).toBeChecked();
  await card(page, 'Langfuse').getByRole('checkbox', { name: 'Keep the words in Langfuse only' }).uncheck();
  await card(page, 'Langfuse').getByRole('button', { name: 'Save' }).click();
  await expect.poll(kept).toBe(false);
});

test("Library and Projects: every user's work, with filters", async ({ page }) => {
  await open(page, 'library');
  await expect(main(page).getByText('Console job').first()).toBeVisible();
  await main(page).getByRole('button', { name: 'Videos' }).click();
  await expect(main(page).getByText('No items match.')).toBeVisible();
  await page.goto(`${CONSOLE}/projects`);
  await expect(main(page).getByRole('heading', { name: 'Projects', level: 2 })).toBeVisible();
  await main(page).getByPlaceholder('Project, person, email or id').fill('zzzz-nothing');
  await expect(main(page).getByText('No project matches.')).toBeVisible();
});

test('Search (Ctrl+K) finds a section and opens it', async ({ page }) => {
  await open(page, 'overview');
  await expect(main(page).getByRole('heading', { name: 'Overview', level: 1 })).toBeVisible();
  await page.keyboard.press('Control+k');
  const box = page.getByRole('searchbox', { name: 'Search' });
  await expect(box).toBeFocused();
  await box.fill('audit');
  await expect(page.getByRole('option', { name: /Audit log/ })).toBeVisible();
  await box.press('Enter');
  await expect(page).toHaveURL(/\/audit$/);
});

test('Overview: the live cards, and the period', async ({ page }) => {
  await open(page, 'overview');
  for (const name of [
    'Online now',
    'Queue right now',
    'Recent activity',
    'Most active users',
    'Workflows used',
    'Why jobs failed',
  ])
    await expect(main(page).getByRole('heading', { name })).toBeVisible();
  await expect(main(page).getByText('Items made per day')).toBeVisible();
  await expect(main(page).getByText('Credits spent per day')).toBeVisible();
});

test('Pricing: the cards, a workflow opened, a package added and deleted', async ({ page }) => {
  await open(page, 'pricing');
  for (const name of ['Rates', 'Quality and size', 'Workflows', 'Agent models', 'Credit packages', 'Servers'])
    await expect(main(page).getByRole('heading', { name, exact: true })).toBeVisible();
  await expect(main(page).getByText(/^Now: an image costs/)).toBeVisible();

  const dialog = page.locator('dialog[open]');
  const workflows = card(page, 'Workflows');
  await workflows.getByRole('row').nth(1).click();
  await expect(dialog.getByText('Leave a rate empty')).toBeVisible();
  await expect(dialog.getByText('Offered to users')).toBeVisible();
  await dialog.getByRole('button', { name: 'Cancel' }).click();
  await expect(dialog).toBeHidden();

  await main(page).getByRole('button', { name: 'Add a package' }).click();
  await expect(dialog.getByRole('heading', { name: 'New package' })).toBeVisible();
  await box(dialog, 'Name').fill('E2E pack');
  await box(dialog, 'Price (₹)').fill('100');
  await box(dialog, 'Credits').fill('1000');
  await box(dialog, 'Bonus credits').fill('0');
  await dialog.getByRole('button', { name: 'Save' }).click();
  const row = main(page).getByRole('row', { name: /E2E pack/ });
  await expect(row).toBeVisible();
  await expect(row.getByText('₹100', { exact: true }).first()).toBeVisible();

  await row.click();
  await dialog.getByRole('button', { name: 'Delete' }).click();
  await page
    .getByRole('dialog', { name: /Delete this/ })
    .getByRole('button', { name: 'OK' })
    .click();
  await expect(row).toBeHidden();
});

test("Workflows: the cards, the filter, and a workflow's drawer", async ({ page }) => {
  await open(page, 'workflows');
  for (const name of [
    'Changes from the render PC',
    'Compared with the render server',
    'Resolutions for everyone',
    'Workflows',
  ])
    await expect(main(page).getByRole('heading', { name, exact: true, level: 2 })).toBeVisible();
  const list = card(page, 'Workflows');
  await list.getByRole('button', { name: 'Off', exact: true }).click();
  await expect(list.getByText('None.')).toBeVisible();
  await list.getByRole('button', { name: 'All', exact: true }).click();
  await list.getByRole('row').nth(1).click();
  const drawer = page.locator('[role=dialog]');
  for (const name of ['Offered to', 'Try it', 'About it'])
    await expect(drawer.getByRole('heading', { name })).toBeVisible();
  await expect(drawer.getByRole('heading', { name: /^Versions \(/ })).toBeVisible();
  await expect(drawer.getByRole('button', { name: 'Test run' })).toBeVisible();
  await drawer.getByRole('button', { name: 'Admins only' }).click();
  await expect(drawer.getByRole('button', { name: 'Admins only' })).toHaveAttribute('aria-pressed', 'true');
  await drawer.getByRole('button', { name: 'Everyone' }).click();
  await expect(drawer.getByRole('button', { name: 'Everyone' })).toHaveAttribute('aria-pressed', 'true');
  await drawer.getByRole('button', { name: 'Close' }).click();
  await expect(drawer).toBeHidden();
});

test("Skills: new, edit, from a file, delete, and a draft (the skills folder is the repo's: the calls are answered here)", async ({
  page,
}) => {
  const sent: { method: string; url: string; body: unknown }[] = [];
  let list = [{ id: 'old-one', title: 'Old one', desc: 'About it', version: '2', words: '\\bold\\b', text: 'Steps' }];
  await page.route('**/api/admin/skills**', async (route) => {
    const request = route.request();
    const url = new URL(request.url()).pathname;
    if (request.method() === 'GET')
      return route.fulfill({
        json: url.endsWith('/drafts')
          ? {
              drafts: [{ id: 'drafted', title: 'A draft', desc: 'Drafted one', words: '', text: 'Do', by_name: 'Sam' }],
              can_publish: true,
            }
          : { skills: list },
      });
    sent.push({ method: request.method(), url, body: request.postDataJSON() });
    if (request.method() === 'POST' && url === '/api/admin/skills') list = [...list, request.postDataJSON()];
    if (request.method() === 'DELETE') list = list.filter((s) => !url.endsWith('/' + s.id));
    return route.fulfill({ json: { ok: true } });
  });
  await open(page, 'skills');
  await expect(main(page).getByRole('heading', { name: 'Skills', exact: true })).toBeVisible();
  await expect(main(page).getByText('/old-one')).toBeVisible();
  await expect(main(page).getByRole('heading', { name: 'Drafts waiting (1)' })).toBeVisible();

  const dialog = page.locator('dialog[open]');
  await main(page).getByRole('button', { name: 'New skill' }).click();
  await expect(dialog.getByRole('heading', { name: 'New skill' })).toBeVisible();
  await box(dialog, 'Id').fill('new-one');
  await box(dialog, 'Title').fill('New one');
  await box(dialog, 'Steps the agent follows').fill('Step');
  await dialog.getByRole('button', { name: 'Save' }).click();
  await expect(main(page).getByText('/new-one')).toBeVisible();
  expect(sent.at(-1)).toMatchObject({
    method: 'POST',
    url: '/api/admin/skills',
    body: { id: 'new-one', title: 'New one', version: '1', text: 'Step' },
  });

  await main(page)
    .getByRole('row', { name: /Old one/ })
    .getByRole('button', { name: 'Edit' })
    .click();
  await expect(dialog.getByRole('heading', { name: 'Edit skill' })).toBeVisible();
  await expect(box(dialog, 'Id')).toBeDisabled();
  await box(dialog, 'Title').fill('Older one');
  await dialog.getByRole('button', { name: 'Save' }).click();
  await expect(dialog).toBeHidden();
  expect(sent.at(-1)).toMatchObject({ method: 'PUT', url: '/api/admin/skills/old-one', body: { title: 'Older one' } });

  const chooser = page.waitForEvent('filechooser');
  await main(page).getByRole('button', { name: 'Upload .md' }).click();
  await (
    await chooser
  ).setFiles({ name: 'old-one.md', mimeType: 'text/markdown', buffer: Buffer.from('# From a file\nStep') });
  await expect(dialog.getByRole('heading', { name: 'Skill from a file' })).toBeVisible();
  await expect(dialog.getByText('exists: saving replaces it')).toBeVisible();
  await expect(box(dialog, 'Title')).toHaveValue('From a file');
  await dialog.getByRole('button', { name: 'Save' }).click();
  await expect(dialog).toBeHidden();
  expect(sent.at(-1)).toMatchObject({ method: 'PUT', url: '/api/admin/skills/old-one' });

  await main(page)
    .getByRole('row', { name: /A draft/ })
    .getByRole('button', { name: 'Review' })
    .click();
  await expect(dialog.getByRole('heading', { name: 'Drafted skill' })).toBeVisible();
  await expect(dialog.getByText('Drafted in a chat by Sam')).toBeVisible();
  await dialog.getByRole('button', { name: 'Publish' }).click();
  await expect(dialog).toBeHidden();
  expect(sent.at(-1)).toMatchObject({
    method: 'POST',
    url: '/api/admin/skills/drafts/drafted/publish',
    body: { title: 'A draft' },
  });

  await main(page)
    .getByRole('row', { name: /New one/ })
    .getByRole('button', { name: 'Delete' })
    .click();
  await page
    .getByRole('dialog', { name: /Delete the skill/ })
    .getByRole('button', { name: 'OK' })
    .click();
  await expect(main(page).getByText('/new-one')).toBeHidden();
  expect(sent.at(-1)).toMatchObject({ method: 'DELETE', url: '/api/admin/skills/new-one' });
});

test('Home page: a section, work added from the library, renamed and removed', async ({ page }) => {
  await open(page, 'showcase');
  await expect(main(page).getByText('Nothing on the Home page yet')).toBeVisible();
  await main(page).getByPlaceholder('New section, e.g. Microdrama').fill('Microdrama');
  await main(page).getByRole('button', { name: 'Add section' }).click();
  await expect(main(page).getByRole('button', { name: 'Microdrama', exact: true })).toBeVisible();

  await main(page).getByRole('button', { name: 'Add from library' }).click();
  const dialog = page.locator('dialog[open]');
  await expect(dialog.getByRole('heading', { name: 'Add to the Home page' })).toBeVisible();
  await dialog.getByRole('button', { name: 'Images' }).click();
  await dialog.getByPlaceholder('Search name, prompt or user').fill('Console job');
  await dialog.getByRole('button', { name: 'Add', exact: true }).first().click();
  await expect(dialog.getByRole('button', { name: 'On the Home page' }).first()).toBeDisabled();
  await dialog.getByRole('button', { name: 'Done' }).click();

  const name = main(page).getByLabel('Name');
  await expect(name).toHaveValue(/Console job/);
  await name.fill('The best one');
  await name.press('Enter');
  await expect(main(page).getByLabel('Name')).toHaveValue('The best one');
  await page
    .waitForResponse((r) => r.url().endsWith('/api/admin/showcase') && r.request().method() === 'GET')
    .catch(() => null);
  await page.reload();
  await expect(main(page).getByLabel('Name')).toHaveValue('The best one');

  await main(page).getByRole('button', { name: 'Remove', exact: true }).click();
  await page
    .getByRole('dialog', { name: /Take "The best one"/ })
    .getByRole('button', { name: 'OK' })
    .click();
  await expect(main(page).getByText('Nothing on the Home page yet')).toBeVisible();

  await main(page).getByTitle('Remove the section (its work stays, under All)').click();
  await page
    .getByRole('dialog', { name: /Remove the section/ })
    .getByRole('button', { name: 'OK' })
    .click();
  await expect(main(page).getByRole('button', { name: 'Microdrama', exact: true })).toBeHidden();
});

test('Agent: the models and what was asked of them', async ({ page }) => {
  await open(page, 'agent');
  await expect(main(page).getByRole('heading', { name: 'Models for each role' })).toBeVisible();
  await expect(main(page).getByRole('heading', { name: 'Latest runs' })).toBeVisible();
});

test('Search: a person found opens Users on them, and Escape closes it', async ({ page }) => {
  await open(page, 'overview');
  await expect(main(page).getByRole('heading', { name: 'Overview', level: 1 })).toBeVisible();
  await page
    .getByRole('button', { name: /Search/ })
    .first()
    .click();
  const search = page.getByRole('searchbox', { name: 'Search' });
  await search.fill('e2e-user');
  await expect(page.getByRole('option', { name: /e2e-user@local.test/ })).toBeVisible();
  await search.press('Enter');
  await expect(page).toHaveURL(/\/users$/);
  await expect(main(page).getByPlaceholder('Search name or email')).toHaveValue('e2e-user@local.test');
  await page.keyboard.press('Control+k');
  await expect(search).toBeFocused();
  await page.keyboard.press('Escape');
  await expect(search).toBeHidden();
});

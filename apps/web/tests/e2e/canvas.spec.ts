// The canvas and its panel in the React build: a frame for each result, and an agent plan approved there and carried
// out by the server (docs/r1-plan-runner-design.md) with the fake v1 provider. No language model is asked: the plan is
// one the agent left in the conversation, as it leaves every plan it makes.

import { expect, test, type Page } from '@playwright/test';
import { done, makeImage, signIn } from './signin';
import { watch } from './watch';

async function project(page: Page, name: string) {
  const made = await (await page.request.post('/api/projects', { data: { name } })).json();
  return made as { id: number; ref: string };
}

async function imageStep(page: Page, name: string, prompt: string) {
  const list = (await (await page.request.get('/api/workflows')).json()) as {
    workflows: { id: string; kind: string }[];
  };
  const workflow = list.workflows.find((w) => w.kind === 'image')!.id;
  const schema = (await (await page.request.get('/api/workflows/' + workflow)).json()) as {
    controls: { id: string; role?: string }[];
  };
  const promptId = schema.controls.find((c) => c.role === 'prompt')!.id;
  return { name, kind: 'image', credits: 0, prompt, settings: { workflow, name, values: { [promptId]: prompt } } };
}

test('a plan approved on the canvas is made by the studio, with the page open or not', async ({ page }) => {
  const problems = watch(page);
  await signIn(page, 'admin');
  const place = await project(page, 'Canvas plan');
  const step = await imageStep(page, 'Kite', 'A red kite over green hills');
  const before = ((await (await page.request.get('/api/auth/me')).json()) as { credits: number }).credits;
  const run = {
    instruction: 'A red kite',
    parts: [{ text: 'A red kite' }],
    reply: 'One shot.',
    thought: '',
    activity: [],
    seconds: 0,
    chips: {},
    memoryUsed: [],
    steps: [step],
    total: 0,
    state: 'proposed',
    at: Date.now(),
    ui: {},
    llm: null,
    question: null,
    questions: [],
    continues: false,
    context: null,
  };
  const saved = await page.request.put(`/api/boards/agent?project=${place.id}`, {
    data: { project: place.id, data: { runs: [run] } },
  });
  expect(saved.ok()).toBe(true);

  await page.goto(`/canvas/${place.ref}`);
  await expect(page.getByRole('toolbar', { name: 'Canvas tools' })).toBeVisible();
  await page.getByRole('button', { name: 'Agent' }).first().click();
  const generate = page.getByRole('button', { name: /^Generate/ });
  await expect(generate).toBeVisible();
  await generate.click();

  // The studio carries it out: the plan ends done, and its picture is made.
  await expect
    .poll(
      async () => {
        const plans = (await (await page.request.get(`/api/agent/plans?project=${place.id}`)).json()) as {
          plans: { state: string; steps: { made: number | null }[] }[];
        };
        return plans.plans[0] ? `${plans.plans[0].state}:${plans.plans[0].steps[0].made ? 'made' : '-'}` : 'none';
      },
      { timeout: 30_000 },
    )
    .toBe('done:made');
  const after = ((await (await page.request.get('/api/auth/me')).json()) as { credits: number }).credits;
  expect(after).toBeLessThan(before); // the reservation paid for it

  // The result is on the canvas, as a frame.
  await expect(page.getByTitle('Kite', { exact: true })).toBeVisible({ timeout: 15_000 });
  expect(problems.filter((p) => !p.includes('/api/agent/status'))).toEqual([]);
});

test('a frame dragged into another shot stays there, even when the page is left at once', async ({ page }) => {
  await signIn(page);
  const place = await project(page, 'Canvas drag');
  for (const name of ['First', 'Second']) {
    const job = await makeImage(page, { name, project_id: place.id });
    await done(page, job.id);
  }
  await page.goto(`/canvas/${place.ref}`);
  const frames = page.getByTitle(/^(First|Second)$/);
  await expect(frames).toHaveCount(2, { timeout: 15_000 });
  const board = async () =>
    (
      (await (await page.request.get(`/api/boards/canvas?project=${place.id}`)).json()) as {
        data: { rows?: { keys: (string | number)[] }[] };
      }
    ).data.rows ?? [];
  await expect.poll(async () => (await board()).filter((r) => r.keys.length).length).toBe(2);

  const [first, second] = [await frames.nth(0).boundingBox(), await frames.nth(1).boundingBox()];
  const top = first!.y < second!.y ? first! : second!;
  const low = first!.y < second!.y ? second! : first!;
  await page.mouse.move(low.x + low.width / 2, low.y + low.height / 2);
  await page.mouse.down();
  for (let i = 1; i <= 12; i++) {
    await page.mouse.move(
      low.x + low.width / 2 + ((top.width + 60) * i) / 12,
      low.y + low.height / 2 - ((low.y - top.y) * i) / 12,
    );
  }
  await page.mouse.up();
  await page.goto('/home'); // left at once: the move is saved as the page goes

  await expect.poll(async () => (await board()).filter((r) => r.keys.length).map((r) => r.keys.length)).toEqual([2]);
});

test('the arrow keys move the selected frame into the next shot and along it', async ({ page }) => {
  await signIn(page);
  const place = await project(page, 'Canvas keys');
  for (const name of ['One', 'Two']) {
    const job = await makeImage(page, { name, project_id: place.id });
    await done(page, job.id);
  }
  await page.goto(`/canvas/${place.ref}`);
  await expect(page.getByTitle(/^(One|Two)$/)).toHaveCount(2, { timeout: 15_000 });
  const rows = async () =>
    (
      (await (await page.request.get(`/api/boards/canvas?project=${place.id}`)).json()) as {
        data: { rows?: { keys: (string | number)[] }[] };
      }
    ).data.rows ?? [];
  await expect.poll(async () => (await rows()).length).toBe(2);
  await page.getByTitle('One', { exact: true }).click();
  await page.keyboard.press('ArrowDown');
  await expect.poll(async () => (await rows()).map((r) => r.keys.length)).toEqual([2]);
  const [was] = await rows();
  await page.keyboard.press('ArrowLeft');
  await expect.poll(async () => (await rows())[0].keys).toEqual([...was.keys].reverse());
});

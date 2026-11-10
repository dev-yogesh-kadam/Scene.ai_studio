// What the canvas tests start from: a project with two shots of their own, one numbered shot with two takes, and a
// NeuralCore entry made from the first picture (so that picture sits on the Characters board, not in a shot row).

import { expect, type Page } from '@playwright/test';
import { done, makeImage } from './signin';

export type Seeded = { id: number; ref: string; items: Record<string, number> };

export async function project(page: Page, name: string) {
  const answer = await page.request.post('/api/projects', { data: { name } });
  expect(answer.ok()).toBe(true);
  return (await answer.json()) as { id: number; ref: string };
}

export async function seedCanvas(page: Page, name: string): Promise<Seeded> {
  // Made once per run: a test file started again after a failure finds the project it made before.
  const known = (await (await page.request.get('/api/projects')).json()) as {
    projects: { id: number; ref: string; name: string }[];
  };
  const before = known.projects.find((p) => p.name === name);
  if (before) {
    const library = (await (await page.request.get(`/api/library?project=${before.id}`)).json()) as {
      items: { id: number; name: string }[];
    };
    const items = Object.fromEntries(library.items.map((i) => [i.name, i.id]));
    if (['First', 'Second', 'Take A', 'Take B'].every((n) => n in items))
      return { id: before.id, ref: before.ref, items };
  }
  const place = await project(page, name);
  const items: Record<string, number> = {};
  for (const [title, extra] of [
    ['First', {}],
    ['Second', {}],
    ['Take A', { shot_number: 1 }],
    ['Take B', { shot_number: 1 }],
  ] as const) {
    const job = await makeImage(page, { name: title, project_id: place.id, ...extra });
    await done(page, job.id);
    const library = (await (await page.request.get(`/api/library?project=${place.id}`)).json()) as {
      items: { id: number; job_id: string }[];
    };
    items[title] = library.items.find((i) => i.job_id === job.id)!.id;
  }
  const kit = await page.request.post('/api/kit', {
    data: { project_id: place.id, name: 'Meera', type: 'character', item: items.First },
  });
  expect(kit.ok()).toBe(true);
  return { ...place, items };
}

/** The canvas's saved layout (GET /api/boards/canvas). */
export async function canvasBoard(page: Page, projectId: number) {
  const answer = (await (await page.request.get(`/api/boards/canvas?project=${projectId}`)).json()) as {
    data: {
      rows?: { id: number; name: string; keys: (string | number)[]; shot?: number }[];
      count?: number;
      picks?: Record<string, { key: number | string; count: number }>;
    };
  };
  return answer.data;
}

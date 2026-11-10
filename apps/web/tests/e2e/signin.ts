// Signing in without the form: the browser's own session cookie, set by the sign-in route, as the form would.

import { expect, type Cookie, type Page } from '@playwright/test';
import { ACCOUNTS } from './accounts';

// The session of each account, kept between tests: the studio allows 20 sign-ins in 5 minutes from one address, and a
// run has more tests than that. A kept session the studio no longer knows (a password was changed) is signed in again.
const sessions = new Map<string, Cookie[]>();

export async function signIn(page: Page, who: keyof typeof ACCOUNTS = 'user') {
  const { email, password } = ACCOUNTS[who];
  const kept = sessions.get(email);
  if (kept) {
    await page.context().clearCookies();
    await page.context().addCookies(kept);
    const me = await page.request.get('/api/auth/me');
    if (me.ok() && ((await me.json()) as { email: string }).email === email) return;
  }
  const answer = await page.request.post('/api/auth/login', { data: { email, password } });
  expect(answer.ok(), `sign-in as ${email}: ${answer.status()} ${await answer.text()}`).toBe(true);
  sessions.set(email, await page.context().cookies());
}

/** A job through the API, the way the Create page sends one: the first image workflow with its defaults. */
export async function makeImage(page: Page, settings: Record<string, unknown> = {}) {
  const list = (await (await page.request.get('/api/workflows')).json()) as {
    workflows: { id: string; kind: string }[];
  };
  const workflow = list.workflows.find((w) => w.kind === 'image')!;
  const answer = await page.request.post('/api/jobs', {
    multipart: { settings: JSON.stringify({ workflow: workflow.id, values: {}, ...settings }) },
  });
  expect(answer.ok()).toBe(true);
  return (await answer.json()) as { id: string; credits: number };
}

/** Waits until the job is finished on the fake render server. */
export async function done(page: Page, id: string) {
  await expect
    .poll(
      async () => {
        const jobs = (await (await page.request.get('/api/jobs')).json()) as { jobs: { id: string; status: string }[] };
        return jobs.jobs.find((j) => j.id === id)?.status;
      },
      { timeout: 30_000 },
    )
    .toBe('done');
}

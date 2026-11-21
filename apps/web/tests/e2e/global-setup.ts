// Starts the fake v1 provider (every model the tests use is one of its models) and a studio of its own (React build,
// new database) before the tests, makes the accounts they sign in as, gives the studio the fake provider's key, and
// stops them after.

import { mkdirSync, writeFileSync } from 'node:fs';
import { addToStudio, startFakeV1 } from '../support/fake-v1.mjs';
import { client, startStudio } from '../support/studio.mjs';
import { PORT_BASE } from '../../playwright.config';
import { ACCOUNTS } from './accounts';

export const FAKE_V1_PORT = PORT_BASE + 198;

export default async function globalSetup() {
  const provider = await startFakeV1({ port: FAKE_V1_PORT });
  const studio = await startStudio({ port: PORT_BASE + 181, consolePort: PORT_BASE + 190 });
  for (const account of [ACCOUNTS.admin, ACCOUNTS.user]) {
    const browser = client(studio.base);
    const made = await browser.call('/api/auth/register', { method: 'POST', json: account });
    if (made.status !== 200) throw new Error(`Could not make ${account.email}: ${JSON.stringify(made.data)}`);
  }
  await addToStudio(studio, provider, ACCOUNTS.admin, client);
  return async () => {
    // What the studio printed (its tracebacks among it), for a test that failed: test-results/studio.log.
    mkdirSync('test-results', { recursive: true });
    writeFileSync('test-results/studio.log', studio.log());
    studio.stop();
    await provider.stop();
  };
}

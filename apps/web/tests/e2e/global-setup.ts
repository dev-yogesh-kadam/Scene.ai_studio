// Starts the fake ComfyUI and a studio of its own (React build, new database) before the tests, makes the accounts
// they sign in as, and stops both after.

import { startFakeComfy } from '../support/fake-comfy.mjs';
import { client, startStudio } from '../support/studio.mjs';
import { ACCOUNTS } from './accounts';

export default async function globalSetup() {
  const fake = await startFakeComfy({ port: 8299 });
  const studio = await startStudio({ port: 8281, consolePort: 8290, comfyUrl: fake.url });
  for (const account of [ACCOUNTS.admin, ACCOUNTS.user]) {
    const browser = client(studio.base);
    const made = await browser.call('/api/auth/register', { method: 'POST', json: account });
    if (made.status !== 200) throw new Error(`Could not make ${account.email}: ${JSON.stringify(made.data)}`);
  }
  return async () => {
    studio.stop();
    await fake.stop();
  };
}

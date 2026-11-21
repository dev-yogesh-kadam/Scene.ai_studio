// The smoke test run at every stop of the React migration, over HTTP only, against a studio of its own
// (support/studio.mjs) whose models are the fake v1 provider's (support/fake-v1.mjs): sign in, Home, Canvas, one image
// job made, the phone site, and the admin console on its own port with none of its files on the studio's.
//
//   node apps/web/tests/smoke/smoke.mjs                 the web app's build (build apps/web first)
//
// The accounts are made in the throwaway database: smoke-admin@local.test (the first account is the admin, who gives
// the studio the fake provider's key) and smoke-test@local.test (a user, which the test signs in as).

import { addToStudio, startFakeV1 } from '../support/fake-v1.mjs';
import { client, startStudio } from '../support/studio.mjs';

const PASSWORD = 'Smoke-test-2026-pass';

const results = [];
function check(name, ok, detail = '') {
  results.push({ name, ok: !!ok, detail });
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}${detail ? `  (${detail})` : ''}`);
}

let fake = null;
let studio = null;
try {
  fake = await startFakeV1();
  studio = await startStudio();
  console.log(`studio ${studio.base}, console ${studio.console}, data in ${studio.home}`);
  await run(studio, fake);
} catch (error) {
  check('the smoke test ran to the end', false, error.stack || String(error));
  if (studio) console.log(studio.log().slice(-4000));
} finally {
  studio?.stop();
  await fake?.stop();
}
const failed = results.filter((r) => !r.ok);
console.log(`\n${results.length - failed.length} passed, ${failed.length} failed`);
process.exit(failed.length ? 1 : 0);

async function run(studio, fake) {
  const admin = client(studio.base);
  const made = await admin.call('/api/auth/register', {
    method: 'POST',
    json: { email: 'smoke-admin@local.test', name: 'Smoke admin', password: PASSWORD },
  });
  check(
    'the first account (the admin) is made',
    made.status === 200 && made.data.role === 'admin',
    `status ${made.status}`,
  );
  await admin.call('/api/auth/logout', { method: 'POST' });
  await addToStudio(studio, fake, { email: 'smoke-admin@local.test', password: PASSWORD }, client);
  check('the admin gives the studio the fake provider', true);

  const anyone = client(studio.base);
  const user = await anyone.call('/api/auth/register', {
    method: 'POST',
    json: { email: 'smoke-test@local.test', name: 'Smoke test', password: PASSWORD },
  });
  check(
    'smoke-test@local.test is made as a user, not an admin',
    user.status === 200 && user.data.role === 'user',
    `role ${user.data.role}`,
  );
  await anyone.call('/api/auth/logout', { method: 'POST' });

  // Sign in
  const me = client(studio.base);
  const signinPage = await me.call('/signin');
  check('the sign-in page loads', signinPage.status === 200 && pageScript(signinPage.data), scriptOf(signinPage.data));
  const login = await me.call('/api/auth/login', {
    method: 'POST',
    json: { email: 'smoke-test@local.test', password: PASSWORD },
  });
  check('signs in', login.status === 200 && login.data.email === 'smoke-test@local.test', `status ${login.status}`);
  const who = await me.call('/api/auth/me');
  check('the session is kept', who.status === 200 && who.data.email === 'smoke-test@local.test');
  const credits = who.data.credits;

  // The page's own scripts load (the build's, named by their content)
  const script = scriptOf(signinPage.data);
  if (script) {
    const file = await me.call(script);
    check("the page's script loads", file.status === 200, script);
  }

  // Home
  const home = await me.call('/home');
  check('Home loads', home.status === 200 && pageScript(home.data));
  for (const path of ['/api/library', '/api/projects', '/api/showcase', '/api/status']) {
    const answer = await me.call(path);
    check(`Home's data: ${path}`, answer.status === 200, `status ${answer.status}`);
  }

  // Canvas, of a new project
  const project = await me.call('/api/projects', { method: 'POST', json: { name: 'Smoke test project' } });
  check('a project is made', project.status === 200 && project.data.id, `status ${project.status}`);
  const id = project.data.id;
  const ref = project.data.ref;
  const canvas = await me.call(ref ? `/canvas/${ref}` : '/canvas');
  check('Canvas loads', canvas.status === 200 && pageScript(canvas.data), ref ? `/canvas/${ref}` : '/canvas');
  for (const path of [
    `/api/library?all=1&project=${id}`,
    `/api/kit?project=${id}`,
    `/api/boards/canvas?project=${id}`,
    `/api/library/placement?project=${id}`,
  ]) {
    const answer = await me.call(path);
    check(`Canvas's data: ${path.split('?')[0]}`, answer.status === 200, `status ${answer.status}`);
  }

  // One image job: queued, then made by the fake provider
  const listed = await me.call('/api/workflows');
  const images = (listed.data.workflows || []).filter((w) => (w.kind || String(w.id).split('/')[0]) === 'image');
  check('there are image workflows', images.length > 0, `${images.length} image workflows`);
  let job = null;
  let tried = [];
  for (const workflow of images) {
    const form = new FormData();
    form.append(
      'settings',
      JSON.stringify({ workflow: workflow.id, values: {}, name: 'Smoke test image', project_id: id }),
    );
    const answer = await me.call('/api/jobs', { method: 'POST', body: form });
    tried.push(`${workflow.id}: ${answer.status}`);
    if (answer.status === 200) {
      job = { ...answer.data, workflow: workflow.id };
      break;
    }
  }
  check('an image job is accepted', job, job ? `${job.workflow}, ${job.credits} credits` : tried.join('; '));
  if (!job) return;
  const after = (await me.call('/api/auth/me')).data.credits;
  check('its price is taken from the balance', after === credits - job.credits, `${credits} -> ${after}`);
  const queue = await me.call('/api/jobs');
  const queued = (queue.data.jobs || []).find((j) => j.id === job.id);
  check(
    'the job is in the queue',
    queued && ['queued', 'running', 'done'].includes(queued.status),
    queued && queued.status,
  );

  const done = await waitFor(async () => {
    const jobs = (await me.call('/api/jobs')).data.jobs || [];
    const found = jobs.find((j) => j.id === job.id);
    return found && ['done', 'failed', 'cancelled'].includes(found.status) ? found : null;
  }, 120_000);
  check(
    'the job runs to "done" on the fake provider',
    done && done.status === 'done',
    done ? done.status : 'timed out',
  );
  const library = await me.call(`/api/library?project=${id}`);
  const items = Array.isArray(library.data) ? library.data : library.data.items || [];
  check('the image is in the library', items.length > 0, `${items.length} items`);
  if (items.length) {
    const file = await me.call(`/api/library/${items[0].id}/file`);
    check("the image's file is served", file.status === 200, `status ${file.status}`);
  }

  // The phone site
  const phone = await me.call('/m/');
  check(
    'the phone site loads at /m/',
    phone.status === 200 && /<div id="root"|expo/i.test(phone.data),
    `status ${phone.status}`,
  );

  // The admin console: its sign-in page on its own port, none of its files on the studio's
  const outside = client(studio.console);
  const consolePage = await outside.call('/signin');
  check(
    'the console sign-in page loads on its own port',
    consolePage.status === 200 && pageScript(consolePage.data),
    scriptOf(consolePage.data),
  );
  const consoleScript = scriptOf(consolePage.data);
  if (consoleScript) {
    const file = await outside.call(consoleScript);
    check("the console's script loads on its port", file.status === 200, consoleScript);
  }
  const studioSide = client(studio.base);
  const probes = [
    '/console.html',
    '/assets/js/console/main.js',
    '/v/1/assets/js/console/main.js',
    '/ASSETS/JS/CONSOLE/main.js',
    '/assets/js//console/main.js',
  ];
  for (const path of [...probes, ...consoleFiles(consolePage.data)]) {
    const answer = await studioSide.call(path);
    check(`console file is 404 on the studio's port: ${path}`, answer.status === 404, `status ${answer.status}`);
  }
}

// The page's own script: /_app/studio-<hash>.js.
function scriptOf(html) {
  if (typeof html !== 'string') return '';
  const found = html.match(/<script type="module"[^>]*src="([^"]+)"/);
  return found ? found[1] : '';
}

function pageScript(html) {
  return !!scriptOf(html);
}

// The files the console's page names (its script and stylesheet), which the studio's port must not serve.
function consoleFiles(html) {
  if (typeof html !== 'string') return [];
  return [...html.matchAll(/(?:src|href)="(\/[^"]+)"/g)]
    .map((m) => m[1])
    .filter((path) => path.startsWith('/_app/') || path.includes('/console'));
}

async function waitFor(test, ms) {
  const until = Date.now() + ms;
  for (;;) {
    const found = await test();
    if (found != null) return found;
    if (Date.now() > until) return null;
    await new Promise((r) => setTimeout(r, 500));
  }
}

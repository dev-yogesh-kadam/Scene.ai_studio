// Requests and bytes per page with a big library (not part of the test suites): a studio of its own with 500 items in
// one project, made from four real ones on the fake ComfyUI and copied in the database. Each page is opened fresh
// (no cache) and everything it asks for until the network is quiet is counted.
//
//   node tests/measure.mjs [items]        default 500; prints a table and writes tests/look/shots/measure.json
import { spawnSync } from 'node:child_process';
import { mkdirSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { chromium } from '@playwright/test';
import { startFakeComfy } from './support/fake-comfy.mjs';
import { REPO, client, startStudio } from './support/studio.mjs';

const COUNT = Number(process.argv[2]) || 500;
const account = { email: 'measure@local.test', name: 'Measure', password: 'Measure-test-2026-pass' };
const PORT = 8581;
const PYTHON =
  process.platform === 'win32' ? join(REPO, '.venv', 'Scripts', 'python.exe') : join(REPO, '.venv', 'bin', 'python');

async function seed(studio) {
  const me = client(studio.base);
  await me.call('/api/auth/login', { method: 'POST', json: account });
  const project = (await me.call('/api/projects', { method: 'POST', json: { name: 'Big film' } })).data;
  const workflow = (await me.call('/api/workflows')).data.workflows.find((w) => w.kind === 'image').id;
  for (const name of ['One', 'Two', 'Three', 'Four']) {
    const form = new FormData();
    form.append('settings', JSON.stringify({ workflow, values: {}, name, project_id: project.id }));
    const job = (await me.call('/api/jobs', { method: 'POST', body: form })).data;
    for (let i = 0; i < 120; i++) {
      const found = ((await me.call('/api/jobs')).data.jobs || []).find((j) => j.id === job.id);
      if (found && found.status === 'done') break;
      await new Promise((r) => setTimeout(r, 250));
    }
  }
  // The rest are copies of those four rows (the same files), each a little older than the last.
  const copy = `
import json, random, sys
from datetime import datetime, timedelta
import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
random.seed(7)
WORDS = "a slow dolly in over wet neon streets at night rain on the glass warm rim light from a shop sign cold blue fill her face half in shadow the camera drifts left as she turns to look back at the empty road behind".split()
db = psycopg.connect(sys.argv[1], row_factory=dict_row)
db.execute("SELECT set_config('app.user_id', 'all', false)")   # row-level security: every user's rows
rows = db.execute("SELECT * FROM generations ORDER BY id").fetchall()
first = min(r["created"] for r in rows)
for n in range(int(sys.argv[2]) - len(rows)):
    row = dict(rows[n % len(rows)])
    row.pop("id"); row.pop("search", None); row["job_id"] = None; row["name"] = "Copy {}".format(n + 1)
    row["created"] = first - (timedelta(seconds=n + 1) if isinstance(first, datetime) else n + 1)
    settings = row["settings"] if isinstance(row["settings"], dict) else json.loads(row["settings"])
    settings["prompt"] = "Shot {} of {}: {}".format(n, sys.argv[2], " ".join(random.sample(WORDS, 24)))
    row["settings"] = settings if isinstance(row["settings"], dict) else json.dumps(settings)
    values = [Jsonb(v) if isinstance(v, (dict, list)) else v for v in row.values()]
    db.execute("INSERT INTO generations ({}) VALUES ({})".format(",".join(row), ",".join(["%s"] * len(row))), values)
db.commit()
`;
  const done = spawnSync(PYTHON, ['-c', copy, studio.database, String(COUNT)], {
    encoding: 'utf8',
  });
  if (done.status !== 0) throw new Error(done.stderr);
  return project;
}

const fake = await startFakeComfy({ port: 8599, renderMs: 100 });
const studio = await startStudio({ port: PORT, consolePort: PORT + 9, comfyUrl: fake.url });
const browser = await chromium.launch();
const results = {};
try {
  await client(studio.base).call('/api/auth/register', { method: 'POST', json: account });
  const project = await seed(studio);
  for (const [name, path] of [
    ['Home', '/home'],
    ['Create', '/create'],
    ['Canvas', `/canvas/${project.ref}`],
    ['Library', '/library'],
  ]) {
    const context = await browser.newContext({ viewport: { width: 1280, height: 800 } });
    await context.request.post(studio.base + '/api/auth/login', { data: account });
    const page = await context.newPage();
    const seen = [];
    page.on('requestfinished', async (request) => {
      const sizes = await request.sizes().catch(() => null);
      const body = await (await request.response())?.body().catch(() => null);
      const url = new URL(request.url());
      seen.push({
        path: url.pathname + url.search,
        type: request.resourceType(),
        bytes: sizes?.responseBodySize ?? 0,
        raw: body?.length ?? 0,
      });
    });
    await page.goto(studio.base + path, { waitUntil: 'networkidle' });
    await page.waitForTimeout(1500);
    const sum = (rows) => rows.reduce((n, r) => n + r.bytes, 0);
    const api = seen.filter((r) => r.path.startsWith('/api/') && r.type !== 'image' && r.type !== 'media');
    const pictures = seen.filter((r) => r.type === 'image' || r.type === 'media');
    const scripts = seen.filter((r) => r.type === 'script');
    results[name] = {
      requests: seen.length,
      bytes: sum(seen),
      api: api.length,
      apiBytes: sum(api),
      apiRaw: api.reduce((n, r) => n + r.raw, 0),
      pictures: pictures.length,
      pictureBytes: sum(pictures),
      scripts: scripts.length,
      scriptBytes: sum(scripts),
      library: api.filter((r) => r.path.startsWith('/api/library')).map((r) => `${r.path} ${r.bytes}/${r.raw}`),
    };
    await context.close();
  }
} finally {
  studio.stop();
  await browser.close();
  await fake.stop();
}
const kb = (n) => (n / 1024).toFixed(1).padStart(8) + ' KB';
console.log(
  `${COUNT} items      requests       total   api   api data (sent / unpacked)  pictures  picture data  scripts`,
);
for (const [name, r] of Object.entries(results))
  console.log(
    `${name.padEnd(10)} ${String(r.requests).padStart(9)} ${kb(r.bytes)} ${String(r.api).padStart(5)} ${kb(r.apiBytes)} / ${kb(r.apiRaw)} ${String(r.pictures).padStart(9)} ${kb(r.pictureBytes)} ${kb(r.scriptBytes)}`,
  );
for (const [name, r] of Object.entries(results)) console.log(name, r.library.join(' | '));
mkdirSync('tests/look/shots', { recursive: true });
writeFileSync(process.env.MEASURE_OUT || 'tests/look/shots/measure.json', JSON.stringify(results, null, 2));

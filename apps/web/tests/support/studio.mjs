// Starts a studio of its own for the smoke and end-to-end tests: this working tree's backend, with a throwaway
// PostgreSQL database of its own (scripts/testdb.py makes it beside SCENE_TEST_DATABASE_URL's; stop() drops it), a
// folder of its own, ports of its own, and a render server address that is either nothing (jobs wait in the queue)
// or the fake ComfyUI (fake-comfy.mjs). Never the real render server, never anyone's real data.

import { spawn, spawnSync } from 'node:child_process';
import { mkdirSync, mkdtempSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

export const REPO = resolve(dirname(fileURLToPath(import.meta.url)), '../../../..');

const PYTHON =
  process.platform === 'win32' ? join(REPO, '.venv', 'Scripts', 'python.exe') : join(REPO, '.venv', 'bin', 'python');

// Test studios' ports start at SCENE_TEST_PORT_BASE (default 8100), so runs side by side (one per worktree) each get
// their own: the smoke test uses base+81 (studio), +90 (console), +99 (fake ComfyUI); Playwright +181, +190, +199.
export const PORT_BASE = Number(process.env.SCENE_TEST_PORT_BASE || 8100);

/**
 * Start the studio. Resolves when it answers. `stop()` ends it.
 * @param {{port?: number, consolePort?: number, comfyUrl?: string, dir?: string}} options
 */
export async function startStudio({
  port = PORT_BASE + 81,
  consolePort = PORT_BASE + 90,
  comfyUrl = 'http://127.0.0.1:9',
  dir,
} = {}) {
  const home = dir || mkdtempSync(join(tmpdir(), 'scene-smoke-'));
  const database = testDatabase('create');
  mkdirSync(home, { recursive: true });
  const config = join(home, 'config.json');
  writeFileSync(
    config,
    JSON.stringify(
      {
        host: '127.0.0.1',
        port,
        console_host: '127.0.0.1',
        console_port: consolePort,
        comfy_url: comfyUrl,
        storage_dir: join(home, 'storage'),
        secret_key_file: join(home, 'secret.key'),
        database_url: database,
        database_owner_url: '',
        backup_keep: 0,
        signups_per_day: 0,
        // Sign-up is closed and gives no credits on a fresh installation; the tests make several accounts with credits.
        allow_signup: true,
        signup_credits: 1000,
        // Claude by an API key (none): a studio open to several users. Claude on this PC, the default, is a personal
        // subscription (sign-up closed, the agent for admins), and would reach the real `claude` of this PC.
        claude_connection: 'api_key',
      },
      null,
      2,
    ),
  );
  // Only this config: none of the SCENE_* settings of whoever runs the tests.
  const env = Object.fromEntries(Object.entries(process.env).filter(([k]) => !k.startsWith('SCENE_')));
  env.SCENE_CONFIG = config;
  env.PYTHONUNBUFFERED = '1';
  const server = spawn(PYTHON, ['-m', 'scene'], { cwd: join(REPO, 'backend'), env, stdio: ['ignore', 'pipe', 'pipe'] });
  let log = '';
  server.stdout.on('data', (d) => (log += d));
  server.stderr.on('data', (d) => (log += d));
  const stop = () => {
    stopProcess(server);
    testDatabase('drop', database);
  };

  const base = `http://127.0.0.1:${port}`;
  const started = Date.now();
  for (;;) {
    if (server.exitCode !== null) {
      testDatabase('drop', database);
      throw new Error(`The studio stopped while starting:\n${log}`);
    }
    try {
      const answer = await fetch(`${base}/api/auth/state`);
      if (answer.ok) break;
    } catch {
      // not listening yet
    }
    if (Date.now() - started > 90_000) {
      stop();
      throw new Error(`The studio did not answer within 90 s:\n${log}`);
    }
    await new Promise((r) => setTimeout(r, 500));
  }
  return {
    base,
    console: `http://127.0.0.1:${consolePort}`,
    home,
    database,
    log: () => log,
    stop,
  };
}

/** Make (`create`: returns its address) or drop a throwaway database, with scripts/testdb.py. */
function testDatabase(command, address) {
  const done = spawnSync(PYTHON, [join(REPO, 'scripts', 'testdb.py'), command, ...(address ? [address] : [])], {
    encoding: 'utf8',
  });
  if (done.status !== 0) throw new Error(`scripts/testdb.py ${command} failed:\n${done.stderr || done.stdout}`);
  return done.stdout.trim();
}

function stopProcess(child) {
  if (child.exitCode !== null) return;
  if (process.platform === 'win32') spawnSync('taskkill', ['/PID', String(child.pid), '/T', '/F'], { stdio: 'ignore' });
  else child.kill('SIGTERM');
}

/** A tiny browser: keeps the session cookie, sends JSON, and says it is the same site, as the studio's pages do. */
export function client(base) {
  const cookies = new Map();
  async function call(path, { method = 'GET', json, body, headers = {} } = {}) {
    const sent = { ...headers, 'Sec-Fetch-Site': 'same-origin' };
    if (cookies.size) sent.Cookie = [...cookies].map(([k, v]) => `${k}=${v}`).join('; ');
    if (json !== undefined) {
      sent['Content-Type'] = 'application/json';
      body = JSON.stringify(json);
    }
    const response = await fetch(base + path, { method, body, headers: sent, redirect: 'manual' });
    for (const line of response.headers.getSetCookie()) {
      const [pair] = line.split(';');
      const cut = pair.indexOf('=');
      const name = pair.slice(0, cut).trim();
      const value = pair.slice(cut + 1).trim();
      if (value && !/max-age=0|expires=thu, 01 jan 1970/i.test(line)) cookies.set(name, value);
      else cookies.delete(name);
    }
    const type = response.headers.get('content-type') || '';
    const data = type.includes('json') ? await response.json() : await response.text();
    return { status: response.status, data, headers: response.headers };
  }
  return { call, cookies };
}

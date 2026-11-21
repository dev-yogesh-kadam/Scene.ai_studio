// A stand-in for a Scene Provider API v1 server (C:\Scene\provider-plan\02-provider-api-v1.md, with the first
// implementer's changes), for the smoke and end-to-end tests: every model the test studio offers is one of its models,
// and its jobs are made here. backend/tests/fake_v1.py is the same for the backend tests.
//
// Keys: LIVE_KEY and SETUP_KEY work (the test studio is given SETUP_KEY when it starts, so it has models from the
// first test; the console's Providers test adds LIVE_KEY itself); TEST_KEY works and stops each job at the quote
// (failed, "test_mode"); any other is 401 key_invalid. Models: Seedance 2.5 (text_to_video), Picture (image) and
// Speech. A job is running for a moment, then succeeded with one output (a PNG, an MP4 or a WAV, made here), or failed
// with "test_mode" for the test key. Nothing reaches a real provider.

import { execFileSync } from 'node:child_process';
import { randomUUID } from 'node:crypto';
import { mkdtempSync, readFileSync, rmSync } from 'node:fs';
import { createServer } from 'node:http';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { deflateSync } from 'node:zlib';
import { PORT_BASE, REPO } from './studio.mjs';

export const LIVE_KEY = 'sa_live_e2efake1234';
export const SETUP_KEY = 'sa_live_e2esetup4321';
export const TEST_KEY = 'sa_test_e2efake5678';
const RUN_MS = 800;

export const MODELS = [
  {
    id: 'seedance_2_5',
    name: 'Seedance 2.5',
    capability: 'text_to_video',
    best_for: 'Cinematic multi-shot scenes.',
    input_schema: {
      type: 'object',
      additionalProperties: false,
      required: ['prompt'],
      properties: {
        prompt: { type: 'string' },
        duration: { type: 'integer', minimum: 4, maximum: 15, default: 5 },
        resolution: { type: 'string', enum: ['480p', '720p'], default: '480p' },
        aspect_ratio: { type: 'string', enum: ['16:9', '9:16'], default: '16:9' },
        sound: { type: 'boolean', default: false },
        first_frame: { type: 'string', 'x-file': 'image' },
        reference_images: { type: 'array', maxItems: 9, items: { type: 'string', 'x-file': 'image' } },
      },
    },
    limits: { seconds: { min: 4, max: 15 }, max_reference_images: 9, frames: ['first', 'last'], sound: 'choice' },
    pricing: { unit: 'second', by: 'resolution', credits: { '480p': 13, '720p': 28 } },
    typical_seconds: 120,
    can_cancel: false,
  },
  {
    id: 'picture',
    name: 'Picture',
    capability: 'image',
    best_for: 'A picture from words, or from reference pictures.',
    input_schema: {
      type: 'object',
      additionalProperties: false,
      required: ['prompt'],
      properties: {
        prompt: { type: 'string' },
        aspect_ratio: { type: 'string', enum: ['1:1', '16:9', '9:16'], default: '1:1' },
        reference_images: { type: 'array', maxItems: 4, items: { type: 'string', 'x-file': 'image' } },
      },
    },
    limits: { max_reference_images: 4 },
    pricing: { unit: 'image', by: null, credits: 4 },
    typical_seconds: 10,
    can_cancel: false,
  },
  {
    id: 'speech',
    name: 'Speech',
    capability: 'speech',
    best_for: 'A voiceover.',
    input_schema: { type: 'object', required: ['text'], properties: { text: { type: 'string' } } },
    limits: {},
    pricing: { unit: 'job', by: null, credits: null },
    typical_seconds: 20,
    can_cancel: false,
  },
];

// What each model's output is: its type, file name and MIME type.
const OUTPUT = {
  text_to_video: { type: 'video', name: 'out.mp4', mime: 'video/mp4' },
  image: { type: 'image', name: 'out.png', mime: 'image/png' },
  speech: { type: 'audio', name: 'out.wav', mime: 'audio/wav' },
};
const outputOf = (model) => OUTPUT[MODELS.find((m) => m.id === model)?.capability] || OUTPUT.image;

/** @param {{port?: number}} options */
export async function startFakeV1({ port = PORT_BASE + 98 } = {}) {
  const jobs = new Map(); // id -> {model, test, started, idem}
  const seen = new Map(); // Idempotency-Key -> job id
  const calls = [];
  const work = mkdtempSync(join(tmpdir(), 'scene-fake-v1-'));
  const made = new Map(); // output type -> its bytes, made once
  let ffmpeg = null;

  const server = createServer(async (request, response) => {
    const url = new URL(request.url, `http://${request.headers.host}`);
    const body = await read(request);
    const send = (status, data, headers = {}) => {
      response.writeHead(status, {
        'Content-Type': 'application/json',
        'X-Request-Id': 'req_' + randomUUID().slice(0, 8),
        ...headers,
      });
      response.end(JSON.stringify(data));
    };
    const fail = (status, code, message) => send(status, { error: { code, message, details: {} } });
    const key = String(request.headers.authorization || '').replace(/^Bearer /, '');
    calls.push({ method: request.method, path: url.pathname, last4: key.slice(-4) });
    try {
      if (url.pathname === '/v1/health') return send(200, { ok: true, version: 'fake' });
      if (![LIVE_KEY, SETUP_KEY, TEST_KEY].includes(key)) return fail(401, 'key_invalid', 'This key is not known.');
      const mode = key === TEST_KEY ? 'test' : 'live';
      if (url.pathname === '/v1/whoami') {
        return send(200, {
          key: {
            id: 'key_' + key.slice(-4),
            label: 'e2e',
            mode,
            last4: key.slice(-4),
            scopes: ['*'],
            max_concurrent: 2,
          },
          provider: { name: 'Generation server', version: 'fake' },
          credits: { available: 91296, used_today: 0 },
          alerts: [],
          features: { webhooks: false, events: false },
        });
      }
      if (url.pathname === '/v1/models') return send(200, { ready: true, models: MODELS });
      if (url.pathname === '/v1/files' && request.method === 'POST') {
        return send(201, {
          id: 'file_' + randomUUID().slice(0, 8),
          name: 'f',
          mime: 'image/png',
          bytes: body.length,
          expires_at: null,
        });
      }
      if (url.pathname === '/v1/jobs' && request.method === 'POST') {
        const idem = String(request.headers['idempotency-key'] || '');
        if (!idem) return fail(400, 'invalid_request', 'Idempotency-Key is required.');
        if (seen.has(idem)) return send(202, view(seen.get(idem)), { 'Idempotent-Replayed': 'true' });
        const asked = safeJson(body);
        if (!MODELS.some((m) => m.id === asked.model)) return fail(400, 'invalid_request', 'No such model.');
        const id = 'job_' + randomUUID().slice(0, 8);
        jobs.set(id, { model: asked.model, test: mode === 'test', started: Date.now() });
        seen.set(idem, id);
        return send(202, view(id));
      }
      const found = url.pathname.match(/^\/v1\/jobs\/(job_[\w-]+)(\/cancel|\/outputs\/(\d+))?$/);
      if (found && jobs.has(found[1])) {
        if (found[2] === '/cancel') {
          jobs.get(found[1]).cancelled = true;
          return send(200, {
            id: found[1],
            status: 'cancelled',
            charged: true,
            message: 'The provider still finishes it.',
          });
        }
        if (found[3] !== undefined) {
          const out = outputOf(jobs.get(found[1]).model);
          response.writeHead(200, { 'Content-Type': out.mime });
          return response.end(media(out.type));
        }
        return send(200, view(found[1]));
      }
      return fail(404, 'not_found', 'No such thing.');
    } catch (error) {
      return fail(500, 'provider_error', String(error));
    }
  });

  function view(id) {
    const job = jobs.get(id);
    const done = Date.now() - job.started >= RUN_MS;
    const base = {
      id,
      model: job.model,
      test: job.test,
      quote: { credits: 65, source: done ? 'provider' : 'price_list' },
    };
    if (job.cancelled) return { ...base, status: 'cancelled', cost: { credits: 65 } };
    if (!done) return { ...base, status: 'running', progress: 0.5, message: 'Making it', cost: null };
    if (job.test) {
      return {
        ...base,
        status: 'failed',
        error: { code: 'test_mode', message: 'A test key stops at the quote.' },
        cost: { credits: 0 },
      };
    }
    const out = outputOf(job.model);
    return {
      ...base,
      status: 'succeeded',
      cost: { credits: 65 },
      outputs: [
        {
          type: out.type,
          url: `/v1/jobs/${id}/outputs/0`,
          mime: out.mime,
          name: out.name,
          bytes: media(out.type).length,
          seconds: out.type === 'image' ? null : 2,
        },
      ],
    };
  }

  // A real file of each type, so the studio can read it as it reads a provider's: a picture written here, a 2-second
  // video or sound made by the ffmpeg of the backend's Python (imageio-ffmpeg).
  function media(type) {
    if (made.has(type)) return made.get(type);
    let bytes;
    if (type === 'image') bytes = png();
    else {
      ffmpeg ??= execFileSync(join(REPO, '.venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python'), [
        '-c',
        'import imageio_ffmpeg; print(imageio_ffmpeg.get_ffmpeg_exe())',
      ])
        .toString()
        .trim();
      const out = join(work, `${randomUUID()}.${type === 'video' ? 'mp4' : 'wav'}`);
      const args =
        type === 'video'
          ? ['-f', 'lavfi', '-i', 'color=c=0x334455:s=320x180:d=2:r=24', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', out]
          : ['-f', 'lavfi', '-i', 'sine=frequency=440:duration=2', out];
      execFileSync(ffmpeg, ['-y', '-loglevel', 'error', ...args]);
      bytes = readFileSync(out);
    }
    made.set(type, bytes);
    return bytes;
  }

  await new Promise((resolve) => server.listen(port, '127.0.0.1', resolve));
  return {
    url: `http://127.0.0.1:${port}`,
    calls,
    stop: () =>
      new Promise((resolve) => {
        server.closeAllConnections?.();
        server.close(() => {
          rmSync(work, { recursive: true, force: true });
          resolve();
        });
      }),
  };
}

/**
 * Give a running test studio this fake as a provider, with SETUP_KEY: signs in to the console as `admin` and adds the
 * key, as Servers & APIs → Providers → Add key does. Its models are then offered in the studio.
 * @param {{console: string}} studio
 * @param {{url: string}} fake
 * @param {{email: string, password: string}} admin
 * @param {(base: string) => {call: Function}} client
 */
export async function addToStudio(studio, fake, admin, client) {
  const browser = client(studio.console);
  const signed = await browser.call('/api/console/login', { method: 'POST', json: admin });
  if (signed.status !== 200) throw new Error(`Could not sign in to the console: ${JSON.stringify(signed.data)}`);
  const added = await browser.call('/api/admin/providers/keys', {
    method: 'POST',
    json: { kind: 'scene_provider_v1', name: 'E2E models', base_url: fake.url, label: 'setup', secret: SETUP_KEY },
  });
  if (added.status !== 200 || !added.data.saved)
    throw new Error(`Could not add the fake provider: ${JSON.stringify(added.data)}`);
}

function read(request) {
  return new Promise((resolve) => {
    const parts = [];
    request.on('data', (part) => parts.push(part));
    request.on('end', () => resolve(Buffer.concat(parts)));
  });
}

function safeJson(buffer) {
  try {
    return JSON.parse(buffer.toString('utf8') || '{}');
  } catch {
    return {};
  }
}

// A 64x64 PNG of one colour, written by hand (no image library needed).
function png() {
  const size = 64;
  const raw = Buffer.alloc((size * 3 + 1) * size);
  for (let y = 0; y < size; y++) {
    raw[y * (size * 3 + 1)] = 0;
    for (let x = 0; x < size; x++) raw.set([0x33, 0x66, 0x99], y * (size * 3 + 1) + 1 + x * 3);
  }
  const chunk = (type, data) => {
    const length = Buffer.alloc(4);
    length.writeUInt32BE(data.length);
    const body = Buffer.concat([Buffer.from(type), data]);
    const crc = Buffer.alloc(4);
    crc.writeUInt32BE(crc32(body) >>> 0);
    return Buffer.concat([length, body, crc]);
  };
  const header = Buffer.alloc(13);
  header.writeUInt32BE(size, 0);
  header.writeUInt32BE(size, 4);
  header.set([8, 2, 0, 0, 0], 8);
  return Buffer.concat([
    Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]),
    chunk('IHDR', header),
    chunk('IDAT', deflateSync(raw)),
    chunk('IEND', Buffer.alloc(0)),
  ]);
}

function crc32(buffer) {
  let crc = ~0;
  for (const byte of buffer) {
    crc ^= byte;
    for (let k = 0; k < 8; k++) crc = (crc >>> 1) ^ (0xedb88320 & -(crc & 1));
  }
  return ~crc;
}

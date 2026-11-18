// A stand-in for a Scene Provider API v1 server (C:\Scene\provider-plan\02-provider-api-v1.md, with the first
// implementer's changes), for the end-to-end tests: the console's Providers adds a key to it, and a job of its models
// is made by it. backend/tests/fake_v1.py is the same for the backend tests.
//
// Keys: LIVE_KEY works; TEST_KEY works and stops each job at the quote (failed, "test_mode"); any other is 401
// key_invalid. Models: Seedance 2.5 (text_to_video) and Speech. A job is running for a moment, then succeeded with one
// output, or failed with "test_mode" for the test key. Nothing reaches a real provider.

import { randomUUID } from 'node:crypto';
import { createServer } from 'node:http';
import { PORT_BASE } from './studio.mjs';

export const LIVE_KEY = 'sa_live_e2efake1234';
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

/** @param {{port?: number}} options */
export async function startFakeV1({ port = PORT_BASE + 98 } = {}) {
  const jobs = new Map(); // id -> {model, test, started, idem}
  const seen = new Map(); // Idempotency-Key -> job id
  const calls = [];

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
      if (key !== LIVE_KEY && key !== TEST_KEY) return fail(401, 'key_invalid', 'This key is not known.');
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
          response.writeHead(200, { 'Content-Type': 'video/mp4' });
          return response.end(Buffer.alloc(64));
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
    return {
      ...base,
      status: 'succeeded',
      cost: { credits: 65 },
      outputs: [
        { type: 'video', url: `/v1/jobs/${id}/outputs/0`, mime: 'video/mp4', name: 'out.mp4', bytes: 64, seconds: 5 },
      ],
    };
  }

  await new Promise((resolve) => server.listen(port, '127.0.0.1', resolve));
  return {
    url: `http://127.0.0.1:${port}`,
    calls,
    stop: () => new Promise((resolve) => server.close(() => resolve())),
  };
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

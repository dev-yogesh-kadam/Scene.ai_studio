// A stand-in for ComfyUI, for the smoke and end-to-end tests: it answers the calls backend/scene/comfy/client.py makes,
// takes any workflow, and after a short wait says it is done, with one output file of the kind the workflow saves
// (a PNG for an image, an MP4 for a video, a WAV for a sound), made here. Nothing is rendered on a real server.

import { execFileSync } from 'node:child_process';
import { randomUUID } from 'node:crypto';
import { mkdtempSync, readFileSync, rmSync } from 'node:fs';
import { createServer } from 'node:http';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { deflateSync } from 'node:zlib';
import { REPO } from './studio.mjs';

const RENDER_MS = 1500; // how long a "render" takes

/** @param {{port?: number, renderMs?: number}} options */
export async function startFakeComfy({ port = 8199, renderMs = RENDER_MS } = {}) {
  const prompts = new Map(); // prompt_id -> {queued, kind, cancelled}
  const work = mkdtempSync(join(tmpdir(), 'scene-fake-comfy-'));
  const files = new Map(); // filename -> bytes
  let ffmpeg = null;

  const server = createServer(async (request, response) => {
    const url = new URL(request.url, `http://${request.headers.host}`);
    const body = await read(request);
    const send = (status, data, type = 'application/json') => {
      response.writeHead(status, { 'Content-Type': type });
      response.end(type === 'application/json' ? JSON.stringify(data) : data);
    };
    try {
      if (url.pathname === '/system_stats') {
        return send(200, {
          system: { os: 'fake', comfyui_version: 'fake', python_version: 'fake' },
          devices: [{ name: 'Fake GPU', type: 'cuda', vram_total: 24e9, vram_free: 20e9 }],
        });
      }
      if (url.pathname === '/queue' && request.method === 'GET') {
        const running = [...prompts.entries()].filter(([, p]) => !p.cancelled && Date.now() - p.queued < renderMs);
        return send(200, { queue_running: running.map(([id]) => [0, id]), queue_pending: [] });
      }
      if (url.pathname === '/queue' || url.pathname === '/interrupt') {
        const asked = safeJson(body);
        for (const id of asked.delete || []) if (prompts.has(id)) prompts.get(id).cancelled = true;
        if (asked.prompt_id && prompts.has(asked.prompt_id)) prompts.get(asked.prompt_id).cancelled = true;
        return send(200, {});
      }
      if (url.pathname === '/object_info') {
        return send(
          200,
          JSON.parse(readFileSync(join(REPO, 'backend', 'tests', 'fixtures', 'node_definitions.json'), 'utf8')),
        );
      }
      if (url.pathname === '/upload/image') {
        const name = (body.toString('latin1').match(/filename="([^"]+)"/) || [])[1] || `upload_${randomUUID()}.png`;
        return send(200, { name, subfolder: '', type: 'input' });
      }
      if (url.pathname === '/prompt' && request.method === 'POST') {
        const { prompt } = safeJson(body);
        if (!prompt || typeof prompt !== 'object')
          return send(400, { error: { message: 'no prompt' }, node_errors: {} });
        const id = randomUUID();
        prompts.set(id, { queued: Date.now(), kind: kindOf(prompt), cancelled: false });
        return send(200, { prompt_id: id, number: prompts.size, node_errors: {} });
      }
      if (url.pathname.startsWith('/history/')) {
        const id = decodeURIComponent(url.pathname.slice('/history/'.length));
        const found = prompts.get(id);
        if (!found || Date.now() - found.queued < renderMs) return send(200, {});
        if (found.cancelled) {
          return send(200, {
            [id]: {
              status: { status_str: 'error', completed: false, messages: [['execution_interrupted', {}]] },
              outputs: {},
            },
          });
        }
        const filename = `fake_${id}${{ image: '.png', video: '.mp4', audio: '.wav' }[found.kind]}`;
        if (!files.has(filename)) files.set(filename, make(found.kind));
        const key = found.kind === 'image' ? 'images' : found.kind === 'video' ? 'gifs' : 'audio';
        return send(200, {
          [id]: {
            status: { status_str: 'success', completed: true, messages: [] },
            outputs: { 9: { [key]: [{ filename, subfolder: '', type: 'output' }] } },
          },
        });
      }
      if (url.pathname === '/view') {
        const filename = url.searchParams.get('filename') || '';
        const type = url.searchParams.get('type');
        const bytes = files.get(filename) || (type === 'input' ? png() : null);
        if (!bytes) return send(404, { error: 'no such file' });
        const ext = filename.split('.').pop();
        return send(
          200,
          bytes,
          { png: 'image/png', mp4: 'video/mp4', wav: 'audio/wav' }[ext] || 'application/octet-stream',
        );
      }
      return send(404, { error: 'not here' });
    } catch (error) {
      return send(500, { error: String(error) });
    }
  });

  function make(kind) {
    if (kind === 'image') return png();
    ffmpeg ??= execFileSync(join(REPO, '.venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python'), [
      '-c',
      'import imageio_ffmpeg; print(imageio_ffmpeg.get_ffmpeg_exe())',
    ])
      .toString()
      .trim();
    const out = join(work, `${randomUUID()}.${kind === 'video' ? 'mp4' : 'wav'}`);
    const args =
      kind === 'video'
        ? ['-f', 'lavfi', '-i', 'color=c=0x334455:s=320x180:d=2:r=24', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', out]
        : ['-f', 'lavfi', '-i', 'sine=frequency=440:duration=2', out];
    execFileSync(ffmpeg, ['-y', '-loglevel', 'error', ...args]);
    return readFileSync(out);
  }

  await new Promise((resolve) => server.listen(port, '127.0.0.1', resolve));
  return {
    url: `http://127.0.0.1:${port}`,
    prompts,
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

// What a workflow saves, by the class of its save nodes.
function kindOf(prompt) {
  const classes = Object.values(prompt).map((node) => String(node?.class_type || ''));
  if (classes.some((c) => /video|vhs_|webm|mp4/i.test(c) && /save|combine|create/i.test(c))) return 'video';
  if (classes.some((c) => /saveaudio|audio.*save/i.test(c))) return 'audio';
  return 'image';
}

function read(request) {
  return new Promise((resolve) => {
    const parts = [];
    request.on('data', (d) => parts.push(d));
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

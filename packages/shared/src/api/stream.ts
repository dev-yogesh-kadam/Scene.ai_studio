// A call answered as it works, one JSON object per line (NDJSON): the agent's plans stream this way. `onLine` is called
// for each object as it arrives; the server's pings (sent while it is quiet, so the connection stays open) are skipped.
// Errors before the answer starts are thrown like request() throws them. Cancel it with an AbortSignal.

import { ApiError, reasonOf } from './client';

export type Line = { type?: string; [key: string]: unknown };

export async function requestLines(
  path: string,
  { json, signal }: { json?: unknown; signal?: AbortSignal } = {},
  onLine: (line: Line) => void = () => {},
  onUnauthorized: (() => void) | null = null,
) {
  const response = await fetch(path, {
    method: 'POST',
    credentials: 'same-origin',
    signal,
    body: JSON.stringify(json),
    headers: { 'Content-Type': 'application/json', Accept: 'application/x-ndjson' },
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    if (response.status === 401) onUnauthorized?.();
    throw new ApiError(response.status, reasonOf(response.status, body), body);
  }
  if (!response.body) return;
  await readLines(response.body, onLine);
}

/** Splits a stream of bytes into JSON lines. Exported for the tests. */
export async function readLines(stream: ReadableStream<Uint8Array>, onLine: (line: Line) => void) {
  const reader = stream.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  const take = (text: string) => {
    const line = text.trim();
    if (!line) return;
    const event = JSON.parse(line) as Line;
    if (event.type !== 'ping') onLine(event); // a sign of life while the server is quiet, nothing to show
  };
  for (;;) {
    const { value, done } = await reader.read();
    buffer += decoder.decode(value || new Uint8Array(), { stream: !done });
    let cut;
    while ((cut = buffer.indexOf('\n')) >= 0) {
      take(buffer.slice(0, cut));
      buffer = buffer.slice(cut + 1);
    }
    if (done) break;
  }
  take(buffer);
}

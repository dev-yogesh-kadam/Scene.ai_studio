import { describe, expect, it } from 'vitest';
import { readLines } from './stream';

function streamOf(...chunks: string[]) {
  const encoder = new TextEncoder();
  return new ReadableStream<Uint8Array>({
    start(controller) {
      for (const chunk of chunks) controller.enqueue(encoder.encode(chunk));
      controller.close();
    },
  });
}

async function linesOf(...chunks: string[]) {
  const seen: unknown[] = [];
  await readLines(streamOf(...chunks), (line) => seen.push(line));
  return seen;
}

describe('readLines', () => {
  it('reads one JSON object per line', async () => {
    expect(await linesOf('{"type":"a"}\n{"type":"b","n":2}\n')).toEqual([{ type: 'a' }, { type: 'b', n: 2 }]);
  });

  it('joins a line that arrives in pieces', async () => {
    expect(await linesOf('{"type":"pl', 'an","steps":[1,', '2]}\n')).toEqual([{ type: 'plan', steps: [1, 2] }]);
  });

  it('skips the pings and the empty lines', async () => {
    expect(await linesOf('{"type":"ping"}\n\n{"type":"done"}\n')).toEqual([{ type: 'done' }]);
  });

  it('reads a last line without a newline', async () => {
    expect(await linesOf('{"type":"a"}\n{"type":"end"}')).toEqual([{ type: 'a' }, { type: 'end' }]);
  });

  it('keeps a character split between two pieces', async () => {
    const bytes = new TextEncoder().encode('{"say":"café"}\n');
    const stream = new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(bytes.slice(0, 12)); // in the middle of "é"
        controller.enqueue(bytes.slice(12));
        controller.close();
      },
    });
    const seen: unknown[] = [];
    await readLines(stream, (line) => seen.push(line));
    expect(seen).toEqual([{ say: 'café' }]);
  });
});

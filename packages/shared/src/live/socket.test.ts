import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { PING, POLL, RECONNECT, SILENT, STATUS, startLive } from './socket';

// A WebSocket that opens when told to, and keeps what it was sent.
class FakeSocket {
  static OPEN = 1;
  static made: FakeSocket[] = [];
  readyState = 0;
  sent: string[] = [];
  closed = false;
  onopen: (() => void) | null = null;
  onmessage: ((event: { data: string }) => void) | null = null;
  onclose: (() => void) | null = null;
  constructor(public url: string) {
    FakeSocket.made.push(this);
  }
  open() {
    this.readyState = FakeSocket.OPEN;
    this.onopen?.();
  }
  say(message: unknown) {
    this.onmessage?.({ data: JSON.stringify(message) });
  }
  send(text: string) {
    this.sent.push(text);
  }
  close() {
    this.closed = true;
    this.readyState = 3;
  }
  drop() {
    this.readyState = 3;
    this.onclose?.();
  }
}

function start(page = () => '/home') {
  const heard: unknown[] = [];
  const pollJobs = vi.fn(() => Promise.resolve());
  const pollStatus = vi.fn(() => Promise.resolve());
  const onReconnect = vi.fn();
  const live = startLive({
    onMessage: (m) => heard.push(m),
    pollJobs,
    pollStatus,
    page,
    onReconnect,
    url: 'ws://studio/api/events',
    WebSocketImpl: FakeSocket as unknown as typeof WebSocket,
  });
  return { live, heard, pollJobs, pollStatus, onReconnect, socket: () => FakeSocket.made[FakeSocket.made.length - 1] };
}

describe('startLive', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    FakeSocket.made = [];
  });
  afterEach(() => vi.useRealTimers());

  it('says when it is back after a lost connection, not on the first one', () => {
    const { live, onReconnect, socket } = start();
    socket().open();
    expect(onReconnect).not.toHaveBeenCalled();
    socket().drop(); // the studio restarted
    vi.advanceTimersByTime(RECONNECT);
    socket().open();
    expect(onReconnect).toHaveBeenCalledTimes(1);
    live.stop();
  });

  it('passes on what the studio says and tells it the page', () => {
    const { live, heard, socket } = start();
    socket().open();
    expect(socket().sent).toEqual([JSON.stringify({ page: '/home' })]);
    socket().say({ jobs: [{ id: 'a' }], credits: 90 });
    expect(heard).toEqual([{ jobs: [{ id: 'a' }], credits: 90 }]);
    live.stop();
  });

  it('pings while it is open, and replaces a connection that went quiet', () => {
    const { live, pollJobs, socket } = start();
    const first = socket();
    first.open();
    vi.advanceTimersByTime(PING);
    expect(first.sent).toContain(JSON.stringify({ ping: 1 }));
    first.say({ jobs: [] }); // heard at PING
    vi.advanceTimersByTime(SILENT + PING);
    expect(first.closed).toBe(true);
    expect(socket()).not.toBe(first);
    expect(pollJobs).toHaveBeenCalled();
    live.stop();
  });

  it('connects again after the connection drops, and polls the jobs meanwhile', () => {
    const { live, pollJobs, socket } = start();
    const first = socket();
    first.open();
    first.drop();
    vi.advanceTimersByTime(POLL);
    expect(pollJobs).toHaveBeenCalledTimes(1);
    expect(FakeSocket.made).toHaveLength(2); // reconnected after RECONNECT, before POLL
    expect(RECONNECT).toBeLessThan(POLL);
    live.stop();
  });

  it('checks the status at once and then every STATUS ms', () => {
    const { live, pollStatus } = start();
    expect(pollStatus).toHaveBeenCalledTimes(1);
    vi.advanceTimersByTime(STATUS * 2);
    expect(pollStatus).toHaveBeenCalledTimes(3);
    live.stop();
  });

  it('stops for good: no reconnect, no polling', () => {
    const { live, pollJobs, socket } = start();
    socket().open();
    live.stop();
    expect(socket().closed).toBe(true);
    vi.advanceTimersByTime(60_000);
    expect(FakeSocket.made).toHaveLength(1);
    expect(pollJobs).not.toHaveBeenCalled();
  });
});

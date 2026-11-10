// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest';
import { MOST, startMonitoring, type Report } from './monitor';

describe('the browser tells the studio what went wrong', () => {
  let stop = () => {};
  afterEach(() => stop());

  it('an uncaught error and a rejection, with the page and the build, each message once', () => {
    const sent: Report[] = [];
    stop = startMonitoring({
      app: 'studio',
      build: 'studio-abc.js',
      page: () => '/home',
      sample: 0,
      send: (r) => sent.push(r),
    });
    const boom = new Error('x is undefined');
    dispatchEvent(new ErrorEvent('error', { message: boom.message, error: boom }));
    dispatchEvent(new ErrorEvent('error', { message: boom.message, error: boom }));
    const rejection = new Event('unhandledrejection') as PromiseRejectionEvent;
    Object.defineProperty(rejection, 'reason', { value: new Error('no answer') });
    dispatchEvent(rejection);
    expect(sent.map((r) => [r.kind, r.message, r.page, r.build])).toEqual([
      ['error', 'x is undefined', '/home', 'studio-abc.js'],
      ['rejection', 'no answer', '/home', 'studio-abc.js'],
    ]);
    expect(sent[0].stack).toContain('x is undefined');
  });

  it('at most MOST a page load, and nothing once stopped', () => {
    const send = vi.fn();
    stop = startMonitoring({ app: 'phone', build: '1', sample: 0, send });
    for (let n = 0; n < MOST + 10; n++) dispatchEvent(new ErrorEvent('error', { message: 'error ' + n }));
    expect(send).toHaveBeenCalledTimes(MOST);
    stop();
    dispatchEvent(new ErrorEvent('error', { message: 'later' }));
    expect(send).toHaveBeenCalledTimes(MOST);
  });
});

// What goes wrong in the browser, told to the studio (POST /api/client-errors, R2 and T5): uncaught errors and unhandled
// promise rejections, with the page and the build they happened on, and for a tenth of page views the Web Vitals
// (LCP, INP, CLS). Only while someone is signed in (the route takes no one else's); each message once per page load, at
// most MOST of them, and a report that fails is let go (it never reports itself).

export type MonitorOptions = {
  app: 'studio' | 'phone';
  build: string; // the build's stamp: which files the page runs
  page?: () => string; // the page's path (the phone site's own router may know it better than location)
  sample?: number; // the share of page views whose vitals are sent; 0.1 by default
  send?: (body: Report) => void; // for the tests
};

export type Report = {
  app: 'studio' | 'phone';
  kind: 'error' | 'rejection' | 'vital';
  message: string;
  stack?: string;
  page: string;
  build: string;
  value?: number;
};

export const MOST = 20;

function post(body: Report) {
  try {
    void fetch('/api/client-errors', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'same-origin',
      keepalive: true, // the page may be closing (the vitals are sent when it is hidden)
      body: JSON.stringify(body),
    }).catch(() => {}); // not told: nothing more to do, and never a report of a report
  } catch {
    // no fetch: nothing to tell
  }
}

/** Starts listening; the function it gives back stops. */
export function startMonitoring({ app, build, page, sample = 0.1, send = post }: MonitorOptions) {
  const where = () => (page ? page() : location.pathname);
  const told = new Set<string>();
  const tell = (kind: 'error' | 'rejection', message: string, stack = '') => {
    const key = kind + message;
    if (told.has(key) || told.size >= MOST) return;
    told.add(key);
    send({ app, kind, message: message.slice(0, 500), stack: stack.slice(0, 4000), page: where(), build });
  };
  const onError = (event: ErrorEvent) => {
    if (!event.message && !event.error) return; // a picture or a script that did not load: not an error of the code
    // the error's own words, not the browser's ("Uncaught Error: …"), so one error reads the same from any browser
    const error = event.error instanceof Error ? event.error : null;
    tell('error', error?.message || event.message || String(event.error), error?.stack ?? '');
  };
  const onRejection = (event: PromiseRejectionEvent) => {
    const reason = event.reason as { message?: string; stack?: string } | string | undefined;
    const message = typeof reason === 'string' ? reason : reason?.message || String(reason);
    tell('rejection', message, typeof reason === 'object' && reason ? (reason.stack ?? '') : '');
  };
  addEventListener('error', onError);
  addEventListener('unhandledrejection', onRejection);

  let stopped = false;
  if (Math.random() < sample) {
    // the measuring code only for the pages that are measured
    void import('web-vitals').then(({ onCLS, onINP, onLCP }) => {
      const vital = ({ name, value }: { name: string; value: number }) => {
        if (!stopped) send({ app, kind: 'vital', message: name, value, page: where(), build });
      };
      onLCP(vital);
      onINP(vital);
      onCLS(vital);
    });
  }
  return () => {
    stopped = true;
    removeEventListener('error', onError);
    removeEventListener('unhandledrejection', onRejection);
  };
}

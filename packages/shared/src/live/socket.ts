// The live connection to the studio (/api/events): where the user's jobs stand, their credits, and that the library
// changed, pushed as they happen. A connection can die without closing (the computer slept, the network changed), so
// it pings every PING ms, and one that has said nothing for SILENT ms is replaced. While it is down the jobs are polled
// instead. Framework-free: the web app's hook (and later the phone site's) puts what it hears into its own cache.

export const PING = 20_000;
export const SILENT = 50_000;
export const RECONNECT = 3_000;
export const POLL = 4_000; // the jobs, fetched this often while the connection is down
export const STATUS = 15_000; // the page version, checked this often

export type LiveMessage = {
  jobs?: unknown[];
  credits?: number | null;
  library_changed?: boolean;
  [key: string]: unknown;
};

export type LiveHandlers = {
  onMessage: (message: LiveMessage) => void;
  pollJobs: () => Promise<unknown>; // the jobs fetched over HTTP: when the connection is down or went quiet
  pollStatus: () => Promise<unknown>; // the page version, fetched every STATUS ms
  page?: () => string; // the page this tab shows, for the admin's list of who is online
  url?: string; // defaults to this site's /api/events
  WebSocketImpl?: typeof WebSocket; // for the tests
};

export type Live = { stop: () => void; sayPage: () => void };

export function startLive({
  onMessage,
  pollJobs,
  pollStatus,
  page,
  url,
  WebSocketImpl = WebSocket,
}: LiveHandlers): Live {
  let socket: WebSocket | null = null;
  let heard = 0; // when the connection last said anything
  let stopped = false;
  const timers: ReturnType<typeof setTimeout>[] = [];
  const address = url || (location.protocol === 'https:' ? 'wss://' : 'ws://') + location.host + '/api/events';
  const quietly = (work: () => Promise<unknown>) => work().catch(() => {}); // the next try comes on its own

  const sayPage = () => {
    if (page && socket && socket.readyState === WebSocketImpl.OPEN) socket.send(JSON.stringify({ page: page() }));
  };

  const connect = () => {
    if (stopped) return;
    socket = new WebSocketImpl(address);
    heard = Date.now();
    socket.onopen = sayPage;
    socket.onmessage = (event) => {
      heard = Date.now();
      try {
        onMessage(JSON.parse(String(event.data)) as LiveMessage);
      } catch {
        // a message that is not JSON: nothing to show
      }
    };
    socket.onclose = () => {
      if (!stopped) timers.push(setTimeout(connect, RECONNECT));
    };
  };

  connect();
  void quietly(pollStatus);
  timers.push(setInterval(() => void quietly(pollStatus), STATUS));
  timers.push(
    setInterval(() => {
      if (!socket || socket.readyState !== WebSocketImpl.OPEN) return;
      if (Date.now() - heard > SILENT) {
        // gone quiet: the jobs fetched now, and a new connection at once
        void quietly(pollJobs);
        const dead = socket;
        dead.onclose = null; // closing a dead connection may take long to say so: the new one does not wait for it
        dead.close();
        connect();
        return;
      }
      socket.send(JSON.stringify({ ping: 1 }));
    }, PING),
  );
  timers.push(
    setInterval(() => {
      if (!socket || socket.readyState !== WebSocketImpl.OPEN) void quietly(pollJobs);
    }, POLL),
  );

  return {
    sayPage,
    stop() {
      stopped = true;
      for (const timer of timers) {
        clearTimeout(timer);
        clearInterval(timer);
      }
      if (socket) {
        socket.onclose = null;
        socket.close();
        socket = null;
      }
    },
  };
}

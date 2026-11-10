// What keeps the console up to date: sections that follow the queue or the server asked again on their timing, unless
// the admin is in the middle of something, and the live connection (/api/console/events) with who is online, the queue,
// and alerts opening and closing.

import { useCallback, useEffect, useLayoutEffect, useRef, useState, type RefObject } from 'react';
import { isBusy } from '../common/busy';
import type { Section } from './sectionList';
import { useConsole } from './sections/shared/context';
import type { ToastNote } from './Toasts';

type Message = {
  online_users?: number;
  jobs?: { running: number; waiting: number } | boolean;
  news?: { level: string; text: string }[];
  alerts?: number;
};

export function useConsoleLive(shown: Section | undefined, body: RefObject<HTMLDivElement | null>) {
  const { refresh } = useConsole();
  const [people, setPeople] = useState<number | null>(null);
  const [bump, setBump] = useState(0);
  const [alerts, setAlerts] = useState(0);
  const [queue, setQueue] = useState<{ running: number; waiting: number } | null>(null);
  const [notes, setNotes] = useState<ToastNote[]>([]);
  const latest = useRef({ shown, refresh });
  const drawn = useRef(0);
  const seenAlerts = useRef(0);
  const nextNote = useRef(0);
  useLayoutEffect(() => {
    latest.current = { shown, refresh };
  });

  const inTheMiddle = useCallback(() => isBusy() || !!body.current?.contains(document.activeElement), [body]);
  const draw = useCallback(() => {
    drawn.current = Date.now();
    void latest.current.refresh().then(() => {
      drawn.current = Date.now();
    });
  }, []);

  // A section just opened counts as just drawn.
  useLayoutEffect(() => {
    drawn.current = Date.now();
  }, [shown]);

  useEffect(() => {
    const timer = setInterval(() => {
      const live = latest.current.shown?.live;
      if (live && !inTheMiddle() && !document.hidden && Date.now() - drawn.current >= live) draw();
    }, 1000);
    return () => clearInterval(timer);
  }, [draw, inTheMiddle]);

  useEffect(() => {
    let socket: WebSocket | null = null;
    let retry: ReturnType<typeof setTimeout> | undefined;
    const follow = (...ids: string[]) => {
      const id = latest.current.shown?.id;
      if (id && ids.includes(id) && !inTheMiddle()) draw();
    };
    const connect = () => {
      socket = new WebSocket(
        (window.location.protocol === 'https:' ? 'wss://' : 'ws://') + window.location.host + '/api/console/events',
      );
      socket.onmessage = (e) => {
        const message = JSON.parse(String(e.data)) as Message;
        if (message.online_users != null) {
          setPeople(message.online_users);
          setBump((b) => b + 1);
          follow('overview'); // it lists who is online
        }
        if (message.jobs) {
          if (typeof message.jobs === 'object') setQueue(message.jobs);
          follow('overview', 'jobs');
        }
        if (message.news?.length) {
          const fresh = message.news.map((n) => ({ ...n, id: ++nextNote.current }));
          setNotes((was) => [...was, ...fresh]);
        }
        if (message.alerts != null) {
          if (seenAlerts.current !== message.alerts) follow('overview', 'system');
          seenAlerts.current = message.alerts;
          setAlerts(message.alerts);
        }
      };
      socket.onclose = () => {
        retry = setTimeout(connect, 3000);
      };
    };
    connect();
    return () => {
      clearTimeout(retry);
      if (socket) {
        socket.onclose = null;
        socket.close();
      }
    };
  }, [draw, inTheMiddle]);

  const dismiss = useCallback((id: number) => setNotes((was) => was.filter((n) => n.id !== id)), []);
  return { people, bump, alerts, queue, notes, dismiss };
}

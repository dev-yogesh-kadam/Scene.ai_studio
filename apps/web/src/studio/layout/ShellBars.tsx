// The bars on top of every page, outside the shell (in <body>, as the classic page put them): an update to the studio,
// the admins' message to everyone, and "Viewing as" when an admin looks at the studio as this user.

import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { createPortal } from 'react-dom';
import type { Announcement as News } from '@scene/shared/types/api';
import { api } from '../../common/api';
import { Icon } from '../../common/components/Icon/Icon';
import { tabPrefs } from '../../common/prefs';
import { useStatus } from '../live';
import { useSession } from '../session';
import { classesOf } from '../../common/cx';
import css0 from '../../console/sections/overview/Cards.module.css';
import css1 from './ShellBars.module.css';
const css = classesOf(css0, css1);

/** A tab opened before the studio was updated runs the old page: it says so once, and Reload brings the new one. The
 *  version this tab loaded is the first one the server reports; a later, higher one is an update. */
export function UpdateBar() {
  const status = useStatus();
  const [loaded, setLoaded] = useState<number | null>(null);
  const [dismissed, setDismissed] = useState(false);
  if (status.page && loaded === null) setLoaded(status.page);
  const newer = loaded !== null && !!status.page && status.page > loaded;
  if (!newer || dismissed) return null;
  return createPortal(
    <div className={css('update-bar')} role="status">
      <span>Scene.ai has been updated.</span>
      <button className="btn small primary" onClick={() => location.reload()}>
        Reload
      </button>
      <button className="icon-btn" title="Later" aria-label="Later" onClick={() => setDismissed(true)}>
        ×
      </button>
    </div>,
    document.body,
  );
}

/** The message an admin set for everyone, floating at the top of the studio until it ends or is closed. Closing it
 *  hides that message for this browser session; a new message shows again. */
export function Announcement() {
  const [closed, setClosed] = useState(() => tabPrefs.get('scene.announce.closed'));
  const news = useQuery({
    queryKey: ['announcement'],
    queryFn: () => api<News>('/api/announcement'),
    refetchInterval: 60_000,
  }).data;
  const show = news?.text && closed !== news.text;
  return createPortal(
    <div className={css('announce-wrap')} role="status">
      {show && (
        <div className={css('announce ' + (news.level || ''))}>
          <Icon name={news.level === 'warning' ? 'bolt' : 'chat'} />
          <span>{news.text}</span>
          <button
            className="icon-btn"
            title="Close"
            aria-label="Close the message"
            onClick={() => {
              tabPrefs.set('scene.announce.closed', news.text || '');
              setClosed(news.text || '');
            }}
          >
            ×
          </button>
        </div>
      )}
    </div>,
    document.body,
  );
}

/** An admin viewing the studio as this user (from the admin console): read only, and said so on every page. */
export function ViewingBar() {
  const { user, signOut } = useSession();
  if (!user.viewing) return null;
  return createPortal(
    <div className={css('viewing-bar')} role="status">
      <span>
        <b>{`Viewing as ${user.name}`}</b>
        {` · read only · opened by ${user.viewing.by}`}
      </span>
      <button className="btn small" onClick={() => void signOut()}>
        Stop viewing
      </button>
    </div>,
    document.body,
  );
}

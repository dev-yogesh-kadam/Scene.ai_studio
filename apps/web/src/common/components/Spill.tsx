// The spill: a made item, far out of focus, lighting the top of a page. Given a library item's id and kind (and the
// address its files are under, when not the library), or nothing for the studio's own faint light. The picture is
// loaded first, so the light fades in instead of popping.

import { useEffect, useState, type CSSProperties } from 'react';
import { classesOf } from '../cx';
import css0 from './Spill.module.css';
const css = classesOf(css0);

export function Spill({
  id,
  kind,
  base = '/api/library',
}: {
  id?: number | null;
  kind?: string | null;
  base?: string;
}) {
  const url = id && kind !== 'audio' ? `${base}/${id}/${kind === 'video' ? 'poster' : 'file'}` : '';
  const [loaded, setLoaded] = useState('');
  const [failed, setFailed] = useState('');
  useEffect(() => {
    if (!url) return;
    const picture = new Image();
    picture.onload = () => setLoaded(url);
    picture.onerror = () => setFailed(url);
    picture.src = url;
  }, [url]);
  const ok = url && failed !== url;
  const wait = ok && loaded !== url; // the old light stays, fading, until the new picture is there
  const shown = ok ? loaded : '';
  return (
    <div
      className={css('spill' + (wait ? ' wait' : ''))}
      aria-hidden="true"
      style={{ '--spill-image': shown ? `url("${shown}")` : '' } as CSSProperties}
    />
  );
}

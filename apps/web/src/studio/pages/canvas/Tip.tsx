// The tip the canvas shows the first time a user opens it (U6), once: kept as seen on the server, so it is not shown
// again on another computer. It lets clicks through to the board, all but its own button.

import { useUserPrefs, userPrefs } from '../../userPrefs';
import s from './Tip.module.css';

const TIP = 'canvas-tip';

export function CanvasTip() {
  const { studio } = useUserPrefs();
  if (studio.seen.includes(TIP)) return null;
  return (
    <aside className={s.tip} aria-label="Tip">
      <b>Your work lands here</b>
      <p>
        Each finished picture or clip is a frame, a row for each shot. Drag frames to arrange them, click one to act on
        it, and ask the Agent on the right to plan a whole film. Press ? for the keys.
      </p>
      <button type="button" className="btn small" onClick={() => userPrefs.setStudio({ seen: [...studio.seen, TIP] })}>
        Got it
      </button>
    </aside>
  );
}

// The viewer: one made item large, in a screening room (the studio goes dark and the picture's own colours glow around
// it), with its prompt and details beside it and its buttons. Opened from a card, a frame or a take; it grows out of
// the picture that was pressed and goes back into it (fly.ts).

import { useEffect, useRef, useState } from 'react';
import { api } from '../api';
import { tell } from '../components/Dialog';
import { showOverlay } from '../components/OverlayHost';
import { Icon } from '../components/Icon/Icon';
import { Still } from '../components/Still';
import { flyFrom, pressedPicture, type Source } from './fly';
import { detailsOf, promptOf, type Item } from './item';
import { classesOf } from '../cx';
import css0 from '../components/Shared.module.css';
import css1 from '../components/Shared2.module.css';
import css2 from '../components/Shared3.module.css';
import css3 from '../components/Shared4.module.css';
import css4 from '../landing/Landing2.module.css';
import css5 from './Viewer.module.css';
import css6 from './Viewer2.module.css';
import css7 from '../../console/sections/overview/Overview.module.css';
import css8 from '../../studio/pages/guide/GuidePage.module.css';
const css = classesOf(css0, css1, css2, css3, css4, css5, css6, css7, css8);

export type ViewerAction = { label: string; danger?: boolean; run: (close: () => void) => void };

/** The takes of the stack the item is on: oldest first, the id of the one in use, and how to put another in use. */
export type Takes = { items: Item[]; chosen: number; choose: (item: Item) => void };

type Options = {
  base?: string;
  owner?: boolean;
  actions?: ViewerAction[];
  takes?: Takes | null;
  onChanged?: () => void; // the item was changed here (rated): the page shows it anew
};

/** Opens the viewer on `item`. base: where the files are served from. owner: say who made it (the admin console).
 *  actions: extra buttons, for the item opened. */
let viewing = false; // one viewer at a time: a quick second double click must not open another over the first

export function openViewer(item: Item, options: Options = {}) {
  if (viewing) return;
  viewing = true;
  const source = pressedPicture();
  const take = showOverlay(
    <Viewer
      item={item}
      source={source}
      onGone={() => {
        viewing = false;
        take();
      }}
      {...options}
    />,
  );
}

function Viewer({
  item,
  source,
  onGone,
  base = '/api/library',
  owner = false,
  actions = [],
  takes = null,
  onChanged,
}: Options & { item: Item; source: Source | null; onGone: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null);
  const mediaBox = useRef<HTMLDivElement>(null);
  const download = useRef<HTMLAnchorElement>(null);
  const trip = useRef<ReturnType<typeof flyFrom>>(null);
  const flyer = useRef<HTMLImageElement & HTMLCanvasElement>(null);
  const leaving = useRef(false);
  const [shown, setShown] = useState(item);
  const [chosen, setChosen] = useState(takes?.chosen ?? 0);
  const shownRef = useRef(shown);
  useEffect(() => {
    shownRef.current = shown;
  }, [shown]);
  useEffect(
    () => () => {
      viewing = false; // gone however it went, another may open
    },
    [],
  );

  // Esc, the close button and a click outside send the picture back to where it came from before the viewer closes
  // (when another take is shown, it just closes: the picture it came from is not that one).
  const leave = () => {
    if (leaving.current) return;
    leaving.current = true;
    const node = dialog.current;
    if (!node) return;
    if (shownRef.current !== item || !trip.current || !trip.current.back(() => node.close())) node.close();
  };

  useEffect(() => {
    const node = dialog.current;
    if (!node) return;
    if (!node.open) {
      // Once: this runs again when onGone changes, and a second flight on the same flyer left it half way.
      node.showModal();
      // The viewer itself takes the focus, not its close button: the Enter that opened it must not close it again.
      node.tabIndex = -1;
      node.focus();
      if (source && mediaBox.current && flyer.current)
        trip.current = flyFrom(node, mediaBox.current, source, flyer.current);
    }
    node.addEventListener('close', onGone);
    return () => node.removeEventListener('close', onGone);
  }, [onGone, source]);

  const url = `${base}/${shown.id}/file`;
  const glow = shown.kind === 'audio' ? '' : shown.kind === 'video' ? `${base}/${shown.id}/poster` : url;
  const promptText = promptOf(shown);
  const use = takes && shown.id !== chosen;

  return (
    <dialog
      ref={dialog}
      className={css('viewer')}
      aria-label="Viewer"
      onCancel={(e) => {
        e.preventDefault();
        leave();
      }}
      onClick={(e) => {
        // A click in the dark around the picture closes it, as a click outside a smaller dialog would.
        const target = e.target as HTMLElement;
        if (target === dialog.current || target === mediaBox.current) leave();
      }}
      onKeyDown={(e) => {
        const target = e.target as HTMLElement;
        if (e.repeat || e.metaKey || e.ctrlKey || e.altKey || target.closest('input, textarea, select')) return;
        if (e.key.toLowerCase() === 'd') {
          e.preventDefault();
          download.current?.click();
          return;
        }
        // ← and → go through the takes
        if (takes && (e.key === 'ArrowLeft' || e.key === 'ArrowRight') && !target.closest('video, audio')) {
          const at = takes.items.findIndex((t) => t.id === shown.id);
          const next = takes.items[at + (e.key === 'ArrowRight' ? 1 : -1)];
          if (next) {
            e.preventDefault();
            setShown(next);
          }
        }
      }}
    >
      <div
        className={css('viewer-glow')}
        aria-hidden="true"
        style={{ ['--spill-image' as string]: glow ? `url("${glow}")` : 'none' }}
      />
      <div className={css('viewer-grid')}>
        <div ref={mediaBox} className={css('viewer-media' + (takes ? ' with-takes' : ''))}>
          <Media key={shown.id} item={shown} url={url} />
          {takes && (
            <div className={css('viewer-takes')} role="listbox" aria-label="Takes">
              {takes.items.map((t, i) => (
                <button
                  key={t.id}
                  type="button"
                  role="option"
                  aria-selected={t.id === shown.id}
                  className={css(
                    'viewer-take' + (t.id === shown.id ? ' shown' : '') + (t.id === chosen ? ' chosen' : ''),
                  )}
                  title={t.id === chosen ? `Take ${i + 1}: in use` : `Take ${i + 1}`}
                  onClick={() => t.id !== shown.id && setShown(t)}
                >
                  <span className={css('viewer-take-pic')}>
                    <Still url={`${base}/${t.id}/file`} kind={t.kind} name={t.name} />
                  </span>
                  <span className={css('viewer-take-label')}>
                    {`Take ${i + 1}`}
                    {t.id === chosen && <b> · In use</b>}
                  </span>
                </button>
              ))}
            </div>
          )}
        </div>
        <aside className={css('viewer-panel')}>
          <div className={css('viewer-title')}>
            <h2>{shown.name}</h2>
            <button className="icon-btn" title="Close" aria-label="Close" onClick={leave}>
              ×
            </button>
          </div>
          <div className={css('viewer-scroll')}>
            {promptText && (
              <div className={css('viewer-section')}>
                <div className={css('label-row')}>
                  <h3>Prompt</h3>
                  <CopyButton text={promptText} />
                </div>
                <p className={css('prose')}>{promptText}</p>
              </div>
            )}
            <div className={css('viewer-section')}>
              <h3>Details</h3>
              <dl className={css('facts')}>
                {detailsOf(shown, { owner }).map(([k, v]) => (
                  <Fact key={k} label={k} value={v} />
                ))}
              </dl>
            </div>
          </div>
          <div className={css('viewer-actions')}>
            <a
              ref={download}
              className="btn primary"
              href={url + '?download=true'}
              download={shown.filename}
              title="Download (D)"
            >
              Download
            </a>
            {base === '/api/library' && !owner && shown.workflow && (
              <Thumbs key={shown.id} item={shown} onChanged={onChanged} />
            )}
            {use && (
              <button
                className="btn"
                title="Put this take on top and go on with it"
                onClick={() => {
                  setChosen(shown.id);
                  takes.choose(shown);
                }}
              >
                Use this take
              </button>
            )}
            {shown === item &&
              actions.map((a) => (
                <button
                  key={a.label}
                  className={'btn' + (a.danger ? ' danger' : '')}
                  onClick={() => a.run(() => dialog.current?.close())}
                >
                  {a.label}
                </button>
              ))}
          </div>
        </aside>
      </div>
      {source &&
        (item.kind === 'image' || item.kind === 'video') &&
        (source.pic instanceof HTMLImageElement ? (
          <img
            ref={flyer}
            className={css('viewer-flyer')}
            src={source.pic.currentSrc || source.pic.src}
            alt=""
            hidden
          />
        ) : (
          <canvas ref={flyer} className={css('viewer-flyer')} width={source.w} height={source.h} hidden />
        ))}
    </dialog>
  );
}

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <>
      <dt>{label}</dt>
      <dd>{value}</dd>
    </>
  );
}

function Media({ item, url }: { item: Item; url: string }) {
  if (item.kind === 'video') return <video src={url} controls autoPlay loop />;
  if (item.kind === 'audio') return <audio src={url} controls autoPlay />;
  if (item.kind === 'text') return <TextFile url={url} />;
  return <img src={url} alt={item.name} />;
}

/** A text is shown as it is: its first 200,000 characters. */
function TextFile({ url }: { url: string }) {
  const [text, setText] = useState('Loading…');
  useEffect(() => {
    fetch(url)
      .then((r) => (r.ok ? r.text() : Promise.reject(new Error(r.statusText))))
      .then((words) => setText(words.length > 200000 ? words.slice(0, 200000) + '\n…' : words))
      .catch(() => setText('This text could not be loaded.'));
  }, [url]);
  return <pre className={css('viewer-text')}>{text}</pre>;
}

function CopyButton({ text }: { text: string }) {
  const [label, setLabel] = useState('Copy');
  return (
    <button
      className="btn small quiet"
      onClick={() => {
        navigator.clipboard.writeText(text).then(
          () => setLabel('Copied'),
          () => setLabel('Copy failed'),
        );
        setTimeout(() => setLabel('Copy'), 1500);
      }}
    >
      {label}
    </button>
  );
}

/** The user's thumbs on their own result: the agent reuses what they liked and never what they turned down. */
function Thumbs({ item, onChanged }: { item: Item; onChanged?: () => void }) {
  const [rating, setRating] = useState(item.rating || 0);
  const rate = async (value: number) => {
    const before = rating;
    const next = before === value ? 0 : value;
    setRating(next);
    try {
      await api('/api/library/' + item.id, { method: 'PUT', json: { rating: next } });
      onChanged?.();
    } catch (e) {
      setRating(before);
      await tell((e as Error).message);
    }
  };
  const choices: [number, 'thumbup' | 'thumbdown', string][] = [
    [1, 'thumbup', 'Good: the agent will reuse it'],
    [-1, 'thumbdown', 'Not good: the agent will not use it'],
  ];
  return (
    <span className={css('rate viewer-rate')}>
      {choices.map(([value, glyph, tip]) => (
        <button
          key={value}
          type="button"
          className={css('icon-btn' + (rating === value ? ' on' + (value < 0 ? ' bad' : '') : ''))}
          title={tip}
          aria-label={tip}
          aria-pressed={rating === value}
          onClick={() => void rate(value)}
        >
          <Icon name={glyph} />
        </button>
      ))}
    </span>
  );
}

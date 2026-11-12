// The bars over the canvas: the project's name and how much is on it (top left, with Share), the balance, Fit, the zoom
// and the panel's button (top right), the tools on the left (upload, the library), and the note that says what they did.

import { useRef, useSyncExternalStore } from 'react';
import { CreditMark, Icon } from '../../../common/components/Icon/Icon';
import { cx } from '../../../common/cx';
import { useUser } from '../../session';
import type { Camera } from './camera';
import s from './Toolbar.module.css';
import { classesOf } from '../../../common/cx';
import css0 from '../../../common/components/Shared3.module.css';
import css1 from './Shared.module.css';
const css = classesOf(css0, css1);

const ACCEPT = 'image/*,video/*,audio/*,.heic,.heif,.avif,.docx,.pdf,.txt,.md,.srt,.json,.csv,.tsv,.svg';

export function ProjectBar({
  name,
  count,
  linked,
  onName,
  onShare,
}: {
  name: string;
  count: number;
  linked: boolean; // a project, not all work: its name opens its page, and it can be shared
  onName: () => void;
  onShare: () => void;
}) {
  return (
    <div className={css(cx('float', s['canvas-bar']))}>
      <b
        className={cx(s['canvas-project'], linked && s.linked)}
        title={linked ? 'Open the project: its NeuralCore and its modules' : 'Everything you have made'}
        onClick={linked ? onName : undefined}
      >
        {name}
      </b>
      <span className={css('slate-text')}>{count === 1 ? '1 item' : `${count} items`}</span>
      {linked && (
        <button className="btn small quiet" title="People in this project" onClick={onShare}>
          <Icon name="people" />
          Share
        </button>
      )}
    </div>
  );
}

export function ViewBar({
  camera,
  panelOpen,
  onFit,
  onPanel,
}: {
  camera: Camera;
  panelOpen: boolean;
  onFit: () => void;
  onPanel: () => void;
}) {
  const credits = useUser().credits;
  const zoom = useSyncExternalStore(camera.subscribe, camera.zoom);
  return (
    <div className={css(cx('float', s['canvas-view']))}>
      {/* the balance, at the top right like on every page; here it leads the tool bar */}
      <span className={s['canvas-credits']} title="Credits pay for generations. An admin can add more.">
        <CreditMark />
        <b>{Number(credits ?? 0).toLocaleString()}</b>
        {Number(credits) === 1 ? ' credit' : ' credits'}
      </span>
      <button className={cx('btn small quiet', s['canvas-zoom'])} title="Fit everything (1)" onClick={onFit}>
        Fit
      </button>
      <button
        className={cx('btn small quiet', s['canvas-zoom'])}
        title="Zoom out (or Ctrl + mouse wheel)"
        aria-label="Zoom out"
        onClick={() => camera.zoomTo(camera.cam.k / 1.25)}
      >
        −
      </button>
      <button
        className={cx('btn small quiet', s['canvas-zoom'])}
        title="Zoom to 100% (0)"
        onClick={() => camera.zoomTo(1)}
      >
        {zoom + '%'}
      </button>
      <button
        className={cx('btn small quiet', s['canvas-zoom'])}
        title="Zoom in (or Ctrl + mouse wheel)"
        aria-label="Zoom in"
        onClick={() => camera.zoomTo(camera.cam.k * 1.25)}
      >
        +
      </button>
      <button
        className="btn small quiet"
        title="Show or hide Quick action and the Agent (Ctrl or ⌘ + J)"
        aria-pressed={panelOpen}
        onClick={onPanel}
      >
        Panel
      </button>
    </div>
  );
}

export function Tools({
  libraryOpen,
  onFiles,
  onLibrary,
}: {
  libraryOpen: boolean;
  onFiles: (files: File[]) => void;
  onLibrary: () => void;
}) {
  const picker = useRef<HTMLInputElement>(null);
  return (
    <div
      className={css(cx('float', s['canvas-tools']))}
      role="toolbar"
      aria-label="Canvas tools"
      aria-orientation="vertical"
    >
      <button
        type="button"
        className={s['tool-btn']}
        aria-label="Upload an image, video or sound"
        data-tip="Upload image, video or audio"
        onClick={() => picker.current?.click()}
      >
        <Icon name="upload" />
      </button>
      <button
        type="button"
        className={cx(s['tool-btn'], libraryOpen && s.on)}
        aria-label="Library"
        data-tip="Library"
        onClick={onLibrary}
      >
        <Icon name="grid" />
      </button>
      <input
        ref={picker}
        type="file"
        accept={ACCEPT}
        multiple
        hidden
        onChange={(e) => {
          onFiles([...(e.target.files ?? [])]);
          e.target.value = '';
        }}
      />
    </div>
  );
}

/** What a tool did, or asks: "Uploaded. It is on the canvas.", "Click a frame to use it" (with Cancel). */
export function ToolNote({
  text,
  error,
  onCancel,
}: {
  text: string;
  error: boolean;
  onCancel?: () => void; // a frame is being asked for
}) {
  return (
    <div
      className={css(cx('float', s['canvas-tool-note'], error && s.error, !text && 'hidden'))}
      role="status"
      aria-live="polite"
    >
      {onCancel ? (
        <>
          <span>{text}</span>
          <button className="btn small quiet" onClick={onCancel}>
            Cancel
          </button>
        </>
      ) : (
        text
      )}
    </div>
  );
}

// A card for a finished image, video or sound (Library, Home): the picture and its name. Its actions wait on the picture
// until the pointer is on it (always shown on a touch screen): the next step as one clear button, Download, and the
// rest in a "…" menu. `manage` adds the library's own actions: move to a project, add to NeuralCore, delete.

import { useNavigate } from 'react-router';
import type { ProjectRow } from '@scene/shared/types/api';
import { api } from '../../../common/api';
import { ask, tell } from '../../../common/components/Dialog';
import { Icon, type IconName } from '../../../common/components/Icon/Icon';
import { popover } from '../../../common/components/Popover';
import { Still } from '../../../common/components/Still';
import { duration, when } from '../../../common/format';
import { seedOf, type Item } from '../../../common/media/item';
import { openViewer } from '../../../common/media/Viewer';
import { toCreate } from '../../handoff';
import { KIT, addToKitDialog } from '../kit/kit';
import { classesOf } from '../../../common/cx';
import css0 from '../../../common/components/Shared.module.css';
import css1 from '../../../common/components/Shared2.module.css';
import css2 from '../../../common/components/Shared3.module.css';
import css3 from '../../../console/sections/overview/Overview.module.css';
import css4 from './MediaCard.module.css';
import css5 from './MediaCard2.module.css';
const css = classesOf(css0, css1, css2, css3, css4, css5);

const MENU = { className: css('card-menu') };

type Project = ProjectRow & { parent_name?: string | null };

/** Open Create with this item as the first frame: an image as it is, a video's last frame. */
export async function asFirstFrame(item: Item, go: (ref: { comfy_name: string; name: string }) => void) {
  try {
    go(await api<{ comfy_name: string; name: string }>(`/api/library/${item.id}/reference`, { method: 'POST' }));
    return true;
  } catch (e) {
    await tell((e as Error).message);
    return false;
  }
}

export function MediaCard({
  item,
  manage = false,
  projects = [],
  onChanged = () => {},
}: {
  item: Item;
  manage?: boolean;
  projects?: Project[];
  onChanged?: () => void;
}) {
  const navigate = useNavigate();
  const fileUrl = `/api/library/${item.id}/file`;
  const sound = item.kind === 'audio'; // a sound can't be the first frame of a video
  const edited = /^(edit|upload)\//.test(item.workflow); // an edit or an upload: there is no form to re-run
  const next = item.kind === 'video' ? 'Continue' : 'Use as first frame';
  const project = projects.find((p) => p.id === item.project_id);
  const rerun = () => toCreate(navigate, { rerun: item });
  const firstFrame = (button?: HTMLButtonElement) => {
    if (button) button.disabled = true;
    return asFirstFrame(item, (ref) =>
      toCreate(navigate, { prefill: { slot: 'first_frame', ref, parent: item.id } }),
    ).then((ok) => {
      if (!ok && button) button.disabled = false;
      return ok;
    });
  };

  const remove = async () => {
    const sure = await ask({
      title: `Delete "${item.name}"?`,
      danger: true,
      confirm: 'Delete',
      message: "It is deleted from your library for good. This can't be undone.",
    });
    if (!sure) return;
    try {
      await api('/api/library/' + item.id, { method: 'DELETE' });
      onChanged();
    } catch (e) {
      await tell((e as Error).message);
    }
  };
  const move = async (projectId: number) => {
    try {
      await api('/api/library/' + item.id, { method: 'PUT', json: { project_id: projectId || null } });
      onChanged();
    } catch (e) {
      await tell((e as Error).message);
    }
  };

  const view = () =>
    openViewer(item, {
      onChanged,
      actions: [
        !edited && { label: 'Re-run', run: (close: () => void) => (close(), rerun()) },
        !edited &&
          seedOf(item) != null && {
            label: 'Reuse seed',
            run: (close: () => void) => (close(), toCreate(navigate, { rerun: item, reuseSeed: true })),
          },
        !sound && { label: next, run: (close: () => void) => void firstFrame().then((ok) => ok && close()) },
      ].filter((a) => !!a),
    });

  const moveMenu = (anchor: HTMLElement) =>
    popover(anchor, (close) => [
      <div key="title" className={css('pop-title')}>
        Move to project
      </div>,
      ...[{ id: 0, name: 'No project' } as Project, ...projects].map((p) => (
        <button
          key={p.id}
          type="button"
          className={css('pop-item')}
          role="menuitemradio"
          aria-checked={(item.project_id || 0) === p.id}
          onClick={() => {
            close();
            void move(p.id);
          }}
        >
          <span>
            <b>{p.parent_name ? `${p.parent_name} › ${p.name}` : p.name}</b>
          </span>
          {(item.project_id || 0) === p.id && <Icon name="check" />}
        </button>
      )),
    ]);

  const openMore = (button: HTMLButtonElement) => {
    const row = (glyph: IconName, label: string, run: () => void, cls = '', close: () => void) => (
      <button
        key={label}
        type="button"
        className={css('pop-item ' + cls)}
        role="menuitem"
        onClick={() => {
          close();
          run();
        }}
      >
        <Icon name={glyph} />
        {label}
      </button>
    );
    popover(
      button,
      (close) => [
        !edited && row('retry', 'Re-run with the same settings', rerun, '', close),
        manage &&
          row(
            'folder',
            project ? `Move from ${project.name}…` : 'Move to a project…',
            () => moveMenu(button),
            '',
            close,
          ),
        manage &&
          item.kind !== 'text' &&
          item.project_id &&
          row('memory', `Add to ${KIT}`, () => void addToKitDialog({ project: item.project_id || 0, item }), '', close),
        manage && <div key="sep" className={css('menu-sep')} />,
        manage && row('trash', 'Delete', () => void remove(), 'danger', close),
      ],
      MENU.className,
    );
  };

  const sub =
    [manage && project ? project.name : '', item.summary, item.seconds && 'took ' + duration(item.seconds)]
      .filter(Boolean)
      .join(' · ') || when(item.created);

  return (
    <div className={css('media')} role="article" aria-label={item.name}>
      <div className={css('thumb')} data-picture onClick={view}>
        <Still
          url={fileUrl}
          kind={item.kind}
          name={item.name}
          width={item.context?.width}
          height={item.context?.height}
        />
        <span className={css('kind')}>{item.kind}</span>
        {item.rating ? (
          <span
            className={css('rated' + (item.rating < 0 ? ' bad' : ''))}
            title={item.rating > 0 ? 'You liked it' : 'You turned it down'}
          >
            <Icon name={item.rating > 0 ? 'thumbup' : 'thumbdown'} />
          </span>
        ) : null}
        <div className={css('card-tools')}>
          <a
            className={css('card-tool')}
            href={fileUrl + '?download=true'}
            download={item.filename}
            title="Download"
            aria-label={`Download ${item.name}`}
            onClick={(e) => e.stopPropagation()}
          >
            <Icon name="download" />
          </a>
          {(!edited || manage) && (
            <button
              type="button"
              className={css('card-tool')}
              title="More"
              aria-label={`More for ${item.name}`}
              aria-haspopup="menu"
              onClick={(e) => {
                e.stopPropagation();
                openMore(e.currentTarget);
              }}
            >
              <Icon name="more" />
            </button>
          )}
        </div>
        {!sound && (
          <button
            type="button"
            className={css('card-go')}
            title={
              item.kind === 'video' ? 'Start a new video on the last frame of this one' : 'Start a video on this image'
            }
            onClick={(e) => {
              e.stopPropagation();
              void firstFrame(e.currentTarget);
            }}
          >
            <Icon name="forward" />
            {next}
          </button>
        )}
      </div>
      <div className={css('meta')}>
        <div className={css('title')} title={item.name}>
          {item.name}
        </div>
        <div className={css('sub')}>{sub}</div>
      </div>
    </div>
  );
}

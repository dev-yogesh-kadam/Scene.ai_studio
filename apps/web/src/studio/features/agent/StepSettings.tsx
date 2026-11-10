// The settings of a step waiting for approval, as pills: its model, shape, size and length. The server builds the step
// again and prices it.

import type { ReactNode } from 'react';
import { Icon, type IconName } from '../../../common/components/Icon/Icon';
import { popover, s as pop } from '../../../common/components/Popover';
import { cx } from '../../../common/cx';
import { changeStep } from './actions';
import type { AgentChat } from './chat';
import { SHAPES, secs } from './shots';
import type { Run, Step } from './types';
import s from './PlanStep.module.css';

/** A setting of a step: a pill that opens a menu of its choices. */
function Pill({
  label,
  glyph,
  title,
  open,
}: {
  label: string;
  glyph: IconName;
  title: string;
  open: (b: HTMLElement) => void;
}) {
  return (
    <button
      type="button"
      className={s['agent-pill']}
      title={title}
      aria-haspopup="menu"
      onClick={(e) => open(e.currentTarget)}
    >
      <Icon name={glyph} />
      <span>{label}</span>
      <span className={s['pill-caret']} aria-hidden="true">
        ⌄
      </span>
    </button>
  );
}

export function Settings({ chat, run, step }: { chat: AgentChat; run: Run; step: Step }) {
  const index = run.steps.indexOf(step);
  const menu = step.menu;
  if (!menu) return null;
  const current = step.current || {};
  const change = (what: Record<string, unknown>) => void changeStep(chat, run, index, what);
  const choose = (
    button: HTMLElement,
    items: { id: string | number; content: ReactNode }[],
    picked: unknown,
    onPick: (id: string | number) => void,
    className: string,
  ) =>
    popover(
      button,
      (close) =>
        items.map((item) => {
          const on = String(item.id) === String(picked);
          return (
            <button
              key={String(item.id)}
              type="button"
              role="menuitemradio"
              className={cx(pop['pop-choice'], on && pop.on)}
              aria-checked={on}
              onClick={() => {
                close();
                if (!on) onPick(item.id);
              }}
            >
              {item.content}
            </button>
          );
        }),
      className,
    );
  const shape = SHAPES.find((x) => x.id === current.orientation);
  const shown =
    menu.workflows.length > 1 ||
    (menu.shapes && current.orientation) ||
    (menu.resolutions.length && current.resolution) ||
    (menu.durations.length && current.duration);
  if (!shown) return null;
  return (
    <div className={s['agent-pills']}>
      {menu.workflows.length > 1 && (
        <Pill
          label={step.workflow_title ?? ''}
          glyph="bars"
          title="Model"
          open={(b) =>
            popover(
              b,
              (close) => (
                <>
                  <div className={pop['pop-title']}>All models</div>
                  {menu.workflows.map((w) => (
                    <button
                      key={w.id}
                      type="button"
                      role="menuitemradio"
                      className={cx(pop['pop-item'], w.id === step.settings?.workflow && pop.on)}
                      aria-checked={w.id === step.settings?.workflow}
                      onClick={() => {
                        close();
                        if (w.id !== step.settings?.workflow) change({ workflow: w.id });
                      }}
                    >
                      <Icon name={w.kind === 'image' ? 'image' : w.kind === 'audio' ? 'audio' : 'video'} />
                      <b>{w.title}</b>
                    </button>
                  ))}
                </>
              ),
              pop['pop-models'],
            )
          }
        />
      )}
      {menu.shapes && current.orientation && (
        <Pill
          label={shape ? shape.label : current.orientation}
          glyph="frame"
          title="Aspect ratio"
          open={(b) =>
            choose(
              b,
              SHAPES.map((x) => ({
                id: x.id,
                content: (
                  <>
                    <i className={cx(pop['shape-mark'], pop[x.id])} />
                    <span>{x.label}</span>
                  </>
                ),
              })),
              current.orientation,
              (id) => change({ orientation: id }),
              pop['pop-shapes'],
            )
          }
        />
      )}
      {menu.resolutions.length > 0 && current.resolution ? (
        <Pill
          label={current.resolution + 'p'}
          glyph="gem"
          title="Resolution"
          open={(b) =>
            choose(
              b,
              menu.resolutions.map((r) => ({ id: r, content: r + 'p' })),
              current.resolution,
              (r) => change({ resolution: r }),
              pop['pop-row'],
            )
          }
        />
      ) : null}
      {menu.durations.length > 0 && current.duration ? (
        <Pill
          label={secs(current.duration)}
          glyph="clock"
          title="Duration"
          open={(b) =>
            choose(
              b,
              menu.durations.map((d) => ({ id: d, content: d + 's' })),
              current.duration,
              (d) => change({ duration: d }),
              pop['pop-row'],
            )
          }
        />
      ) : null}
    </div>
  );
}

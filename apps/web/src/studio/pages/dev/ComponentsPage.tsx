// The component catalogue (D3), in development only (npm run dev, /dev/components): every shared control and state of
// the studio, in the dark theme and the light one side by side, so a change to one is seen everywhere at once. The
// two themes' values come from the one tokens source (packages/shared/tokens/tokens.json). Never in a production build.

import { useState, type CSSProperties, type ReactNode } from 'react';
import tokens from '@scene/shared/tokens.json';
import { BarList, ColumnChart, Meter, Sparkline } from '../../../common/components/Charts';
import { ask, tell } from '../../../common/components/Dialog';
import { Field } from '../../../common/components/AuthForm';
import { CreditMark, Icon } from '../../../common/components/Icon/Icon';
import { ICONS, type IconName } from '../../../common/components/Icon/icons';
import { addMenu } from '../../../common/components/Popover';
import { Segmented } from '../../../common/components/Segmented';
import { EmptyState, ErrorBanner, Skeleton } from '../../../common/components/States';
import s from './ComponentsPage.module.css';

/** A theme's tokens as the CSS variables of one panel (the page's own theme is left as it is). */
const themed = (values: Record<string, string>, scheme: 'dark' | 'light') =>
  ({
    ...Object.fromEntries(Object.entries({ ...tokens.web.dark, ...values }).map(([k, v]) => [`--${k}`, v])),
    colorScheme: scheme,
  }) as CSSProperties;

function Row({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className={s.row}>
      <h3>{title}</h3>
      <div className={s.items}>{children}</div>
    </section>
  );
}

function Catalogue() {
  const [pick, setPick] = useState('video');
  return (
    <>
      <Row title="Buttons">
        <button className="btn primary">Primary</button>
        <button className="btn">Button</button>
        <button className="btn quiet">Quiet</button>
        <button className="btn danger">Danger</button>
        <button className="btn danger-solid">Delete for good</button>
        <button className="btn small">Small</button>
        <button className="btn generate">
          Generate <CreditMark label="40" />
        </button>
        <button className="icon-btn" aria-label="More">
          <Icon name="menu" />
        </button>
        <button className="btn" disabled>
          Disabled
        </button>
      </Row>
      <Row title="Segmented">
        <Segmented
          choices={[
            { id: 'video', label: 'Video' },
            { id: 'image', label: 'Image' },
            { id: 'audio', label: 'Audio' },
          ]}
          current={pick}
          onPick={setPick}
        />
      </Row>
      <Row title="Fields">
        <Field label="Name">
          <input type="text" placeholder="A name" />
        </Field>
        <Field label="Kind">
          <select defaultValue="b">
            <option value="a">One</option>
            <option value="b">Two</option>
          </select>
        </Field>
        <Field label="Prompt">
          <textarea placeholder="Describe the shot" />
        </Field>
        <label className="check">
          <input type="checkbox" defaultChecked /> A choice
        </label>
      </Row>
      <Row title="Notices">
        <p className="notice ok">Saved.</p>
        <p className="notice">A notice.</p>
        <p className="error">Something went wrong.</p>
        <p className="muted">Muted words.</p>
      </Row>
      <Row title="States (EmptyState, Skeleton, ErrorBanner)">
        <EmptyState>Nothing here yet.</EmptyState>
        <div className={s.bones}>
          <Skeleton count={3} />
        </div>
        <ErrorBanner error={new Error('The studio could not be reached.')} onRetry={() => {}} />
      </Row>
      <Row title="Windows and menus">
        <button className="btn" onClick={() => void tell('A notice', 'With a line of words.')}>
          A notice
        </button>
        <button
          className="btn"
          onClick={() => void ask({ title: 'Delete "Fox"?', message: 'For good.', confirm: 'Delete', danger: true })}
        >
          A question
        </button>
        <button
          className="btn"
          onClick={(e) =>
            addMenu(e.currentTarget, [
              { icon: 'image', label: 'An item', run: () => {} },
              { icon: 'video', label: 'Another', run: () => {} },
            ])
          }
        >
          A menu
        </button>
      </Row>
      <Row title="Charts">
        <div className={s.chart}>
          <ColumnChart
            labels={['Mon', 'Tue', 'Wed', 'Thu', 'Fri']}
            series={[
              { name: 'Images', color: 'var(--series-1)', values: [3, 5, 2, 8, 6] },
              { name: 'Videos', color: 'var(--series-2)', values: [1, 2, 4, 1, 3] },
            ]}
            height={120}
          />
        </div>
        <Sparkline values={[2, 4, 3, 7, 5, 9]} />
        <div className={s.chart}>
          <BarList
            rows={[
              { label: 'FLUX.2', value: 12 },
              { label: 'H3', value: 7 },
            ]}
          />
          <Meter label="Storage" used={42} total={100} format={(n) => `${n} GB`} />
        </div>
      </Row>
      <Row title="Icons">
        {(Object.keys(ICONS) as IconName[]).map((name) => (
          <span key={name} className={s.icon} title={name}>
            <Icon name={name} />
          </span>
        ))}
      </Row>
    </>
  );
}

export default function ComponentsPage() {
  return (
    <div className={s.page}>
      <h1>Components</h1>
      <p className="muted">Development only. Every shared control in both themes; the tokens are in tokens.json.</p>
      <div className={s.themes}>
        <div className={s.theme} style={themed(tokens.web.dark, 'dark')}>
          <h2>Dark</h2>
          <Catalogue />
        </div>
        <div className={s.theme} style={themed(tokens.web.light, 'light')}>
          <h2>Light</h2>
          <Catalogue />
        </div>
      </div>
    </div>
  );
}

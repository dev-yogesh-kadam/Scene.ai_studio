// What makes the long landing page feel like one shot, for the landing itself and the sign-in pages over it: sections
// rise in as they come into view, the bar with the doors slides down once the first screen is passed, and the
// monitor's moving parts rest while it is out of sight. With the Motion setting on calm, or the system asking for less
// motion, everything simply stands in place.

import {
  createContext,
  useContext,
  useEffect,
  useRef,
  useState,
  type ComponentPropsWithoutRef,
  type CSSProperties,
  type ElementType,
  type ReactNode,
  type RefObject,
} from 'react';
import { calmNow } from './words';
import { classesOf } from '../cx';
import css0 from './Landing.module.css';
import css1 from './Landing3.module.css';
import css2 from './Landing4.module.css';
import css3 from './Landing5.module.css';
import css4 from './Landing6.module.css';
import css5 from './Landing8.module.css';
import css6 from './LandingRoot.module.css';
const css = classesOf(css0, css1, css2, css3, css4, css5, css6);

type Shared = { barOn: boolean; setBar: (on: boolean) => void; next: RefObject<HTMLElement | null>; moving: boolean };
const Page = createContext<Shared | null>(null);

function usePage() {
  const page = useContext(Page);
  if (!page) throw new Error('Landing parts go inside a LandingRoot');
  return page;
}

/** The whole page. `moving`: its sections rise in (not on the console's sign-in, which has none). */
export function LandingRoot({
  className,
  moving = true,
  children,
}: {
  className?: string;
  moving?: boolean;
  children: ReactNode;
}) {
  const [barOn, setBar] = useState(false);
  const next = useRef<HTMLElement>(null);
  const [calm] = useState(calmNow);
  const animated = moving && !calm;
  return (
    <Page.Provider value={{ barOn, setBar, next, moving: animated }}>
      <div className={css('la' + (className ? ' ' + className : '') + (animated ? ' la-anim' : ''))}>{children}</div>
    </Page.Provider>
  );
}

export const useLandingBar = () => usePage().barOn;
export const useSetBar = () => usePage().setBar;
/** Where the section after the monitor is to be remembered, for the cue that scrolls on to it. */
export const useNextSection = () => usePage().next;

/** Something that rises in as it comes into view; `d` is its place in a row, which delays it a little. */
export function Rv<T extends ElementType = 'div'>({
  as,
  d = 0,
  className,
  style,
  ...rest
}: { as?: T; d?: number } & ComponentPropsWithoutRef<T>) {
  const Tag: ElementType = as || 'div';
  const { moving } = usePage();
  const node = useRef<Element>(null);
  const [seen, setSeen] = useState(false);
  useEffect(() => {
    if (!moving || !node.current) return;
    const watch = new IntersectionObserver(
      (entries) => {
        if (entries.some((e) => e.isIntersecting)) {
          setSeen(true);
          watch.disconnect();
        }
      },
      { rootMargin: '0px 0px -8% 0px', threshold: 0.12 },
    );
    watch.observe(node.current);
    return () => watch.disconnect();
  }, [moving]);
  const delayed = d ? ({ ...style, '--d': `${d * 70}ms` } as CSSProperties) : style;
  return (
    <Tag
      ref={node}
      className={css((className ? className + ' ' : '') + 'la-rv' + (seen ? ' in' : ''))}
      style={delayed}
      {...rest}
    />
  );
}

/** The monitor at rest while out of sight, the bar over the page once it has gone by, and its layers leaning away from
 *  the pointer, nearer ones more (the CSS reads --px and --py). Returns whether it is out of sight. */
export function useMonitorLife(monitor: RefObject<HTMLElement | null>, active = true) {
  const { setBar } = usePage();
  const [off, setOff] = useState(false);
  useEffect(() => {
    const node = monitor.current;
    if (!node || !active) return;
    let raf = 0;
    const move = (e: PointerEvent) => {
      if (e.pointerType !== 'mouse' || raf) return;
      raf = requestAnimationFrame(() => {
        raf = 0;
        const box = node.getBoundingClientRect();
        node.style.setProperty('--px', (((e.clientX - box.left) / box.width) * 2 - 1).toFixed(3));
        node.style.setProperty('--py', (((e.clientY - box.top) / box.height) * 2 - 1).toFixed(3));
      });
    };
    const leave = () => {
      node.style.setProperty('--px', '0');
      node.style.setProperty('--py', '0');
    };
    if (!calmNow()) {
      node.addEventListener('pointermove', move);
      node.addEventListener('pointerleave', leave);
    }
    const watch = new IntersectionObserver(
      ([e]) => {
        setOff(!e.isIntersecting);
        setBar(e.intersectionRatio < 0.25);
      },
      { threshold: [0, 0.25] },
    );
    watch.observe(node);
    return () => {
      cancelAnimationFrame(raf);
      node.removeEventListener('pointermove', move);
      node.removeEventListener('pointerleave', leave);
      watch.disconnect();
    };
  }, [monitor, active, setBar]);
  return off;
}

/** The cue that scrolls on to what comes next: `reelEnd()` says where the reel ends when it is running, else the first
 *  section. */
export function Cue({ reelEnd }: { reelEnd?: () => number | null }) {
  const { next } = usePage();
  const onward = () => {
    const behavior = calmNow() ? 'auto' : 'smooth';
    const top = reelEnd?.() ?? null;
    if (top !== null) window.scrollTo({ top, behavior });
    else next.current?.scrollIntoView({ behavior });
  };
  return (
    <button type="button" className={css('la-cue la-mono')} onClick={onward}>
      Scroll
      <i />
    </button>
  );
}

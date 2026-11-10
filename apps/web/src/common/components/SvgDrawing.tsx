// A drawing the studio makes itself as SVG text (the landing's scenes), put on the page as elements. The text is parsed
// as XML (an SVG document runs no script when parsed this way) and only ever comes from the studio's own code, never
// from anyone's input. The page allows no inline style (CSP): a style="" written in the text is set through the style
// object instead (setProperty), which the policy allows, so the drawing looks the same.

import { useImperativeHandle, useLayoutEffect, useRef, type CSSProperties, type Ref } from 'react';

function parseSvg(text: string): Element | null {
  if (!text) return null;
  const doc = new DOMParser().parseFromString(text, 'image/svg+xml');
  const root = doc.documentElement;
  if (root.nodeName !== 'svg' || doc.getElementsByTagName('parsererror').length) return null;
  for (const el of doc.querySelectorAll('[style]')) {
    el.setAttribute('data-style', el.getAttribute('style') ?? '');
    el.removeAttribute('style');
  }
  const drawn = document.importNode(root, true);
  for (const el of drawn.querySelectorAll<SVGElement>('[data-style]')) {
    for (const rule of (el.getAttribute('data-style') ?? '').split(';')) {
      const at = rule.indexOf(':');
      if (at > 0) el.style.setProperty(rule.slice(0, at).trim(), rule.slice(at + 1).trim());
    }
    el.removeAttribute('data-style');
  }
  return drawn;
}

export function SvgDrawing({
  svg,
  className,
  style,
  ref,
  testId,
}: {
  svg: string;
  className?: string;
  style?: CSSProperties;
  testId?: string;
  ref?: Ref<HTMLDivElement>;
}) {
  const box = useRef<HTMLDivElement>(null);
  useImperativeHandle(ref, () => box.current as HTMLDivElement, []);
  useLayoutEffect(() => {
    const drawn = parseSvg(svg);
    box.current?.replaceChildren(...(drawn ? [drawn] : []));
  }, [svg]);
  return <div ref={box} className={className} style={style} data-testid={testId} aria-hidden="true" />;
}

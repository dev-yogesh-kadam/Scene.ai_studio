// A picture the studio draws: one of the landing scenes, filling its box.

import { useMemo, type CSSProperties } from 'react';
import { SvgDrawing } from '../components/SvgDrawing';
import * as scenes from './landingScenes';

export function Picture({
  name,
  className,
  sketch = false,
  style,
  testId,
}: {
  name: string;
  className?: string;
  sketch?: boolean;
  style?: CSSProperties;
  testId?: string;
}) {
  const svg = useMemo(() => scenes.svg(name, { sketch }), [name, sketch]);
  return <SvgDrawing svg={svg} className={className} style={style} testId={testId} />;
}

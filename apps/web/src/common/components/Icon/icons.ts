// The studio's line icons, as data: each is a list of [element, attributes], so they are drawn as elements, never as
// HTML text.

import { ICONS_A } from './iconsA';
import { ICONS_B } from './iconsB';

export type IconPart = ['path' | 'circle', Record<string, string>];

export const ICONS = { ...ICONS_A, ...ICONS_B };

export type IconName = keyof typeof ICONS;

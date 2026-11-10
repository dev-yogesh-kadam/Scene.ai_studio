// What the Home page section reads, and how an item is opened in the studio's viewer.

import type { Item } from '../../../common/media/item';

export type ShowItem = {
  key: string;
  from?: number;
  kind: string;
  name: string;
  section: string;
  show_prompt?: boolean;
  prompt?: string;
  workflow?: string;
  workflow_title?: string;
  added?: number;
  width?: number;
  height?: number;
  duration?: number;
};
export type Data = { sections: string[]; items: ShowItem[]; limit: number };
export const BASE = '/api/admin/showcase';

/** An item as the studio's viewer reads it (showcase.public on the server). */
export const viewed = (item: ShowItem) =>
  ({
    id: item.key,
    kind: item.kind,
    name: item.name,
    workflow: item.workflow || '',
    created: item.added,
    settings: {
      workflow_title: item.workflow_title,
      ...(item.show_prompt && item.prompt ? { prompt: item.prompt } : {}),
    },
    context: { width: item.width, height: item.height, duration: item.duration },
  }) as unknown as Item;

export function moved<T>(list: T[], at: number, by: number) {
  const next = [...list];
  const [item] = next.splice(at, 1);
  next.splice(Math.max(0, Math.min(next.length, at + by)), 0, item);
  return next;
}

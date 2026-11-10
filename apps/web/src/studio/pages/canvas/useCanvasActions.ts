// What the canvas does with its frames, apart from moving them: open one in the viewer (a stack opens with all its
// takes under it), re-run it or reuse its seed on Create, download, keep it in the NeuralCore, bring files in, and say
// what happened in the note at the bottom left.

import { useQueryClient } from '@tanstack/react-query';
import { useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router';
import { uploadFile } from '@scene/shared/api/canvas';
import { openViewer } from '../../../common/media/Viewer';
import { seedOf, type Item } from '../../../common/media/item';
import { addToKitDialog } from '../../features/kit/kit';
import type { Arranged } from './arrange';
import { stacked, type Key, type Layout, type Stack } from './geometry';
import { canvasKeys } from './useCanvasLayout';
import { toCreate } from '../../handoff';

export type Note = { text: string; error: boolean; stay: boolean };

/** The note at the bottom left: it goes after a moment (an error stays longer), unless it asks for something. */
export function useNote() {
  const [note, setNoteState] = useState<Note>({ text: '', error: false, stay: false });
  const timer = useRef<ReturnType<typeof setTimeout>>(undefined);
  const say = useCallback((text: string, error = false, stay = false) => {
    clearTimeout(timer.current);
    setNoteState({ text, error, stay });
    if (!stay && text) timer.current = setTimeout(() => setNoteState((n) => ({ ...n, text: '' })), error ? 6000 : 2500);
  }, []);
  useEffect(() => () => clearTimeout(timer.current), []);
  return { note, say };
}

const made = (item: Item) => !/^(edit|upload)\//.test(item.workflow);

export function useCanvasActions({
  project,
  items,
  arranged,
  change,
  select,
  say,
}: {
  project: number;
  items: Item[];
  arranged: Arranged | null;
  change: (layout: Layout) => void;
  select: (ids: Set<number>) => void;
  say: (text: string, error?: boolean, stay?: boolean) => void;
}) {
  const navigate = useNavigate();
  const client = useQueryClient();
  const downloader = useRef<HTMLAnchorElement>(null);

  const rerun = useCallback((item: Item) => toCreate(navigate, { rerun: item, from: '/canvas' }), [navigate]);
  const reuseSeed = useCallback(
    (item: Item) => toCreate(navigate, { rerun: item, reuseSeed: true, from: '/canvas' }),
    [navigate],
  );

  /** Put one take of a stack on top. It stays there until the user switches again or a new take comes. */
  const pickTake = useCallback(
    (stack: Stack, key: Key) => {
      if (!arranged) return;
      change({
        ...arranged.layout,
        picks: { ...arranged.layout.picks, [stack.key]: { key, count: stack.members.length } },
      });
    },
    [arranged, change],
  );

  const open = useCallback(
    (item: Item) => {
      const stack = arranged?.spots.get(item.id)?.stack;
      const byId = new Map(items.map((i) => [i.id, i]));
      const takes =
        arranged && stack && stack.members.length > 1
          ? {
              items: [...stack.members]
                .reverse()
                .map((id) => byId.get(id as number))
                .filter((i): i is Item => !!i), // oldest first
              chosen: stacked(arranged.layout, stack.key, stack.members)[0] as number,
              choose: (take: Item) => pickTake(stack, take.id),
            }
          : null;
      openViewer(item, {
        takes,
        actions: !made(item)
          ? []
          : [
              {
                label: 'Re-run',
                run: (close) => {
                  close();
                  rerun(item);
                },
              },
              ...(seedOf(item) != null
                ? [
                    {
                      label: 'Reuse seed',
                      run: (close: () => void) => {
                        close();
                        reuseSeed(item);
                      },
                    },
                  ]
                : []),
            ],
      });
    },
    [arranged, items, pickTake, rerun, reuseSeed],
  );

  const download = useCallback((list: Item[]) => {
    const link = downloader.current;
    if (!link) return;
    for (const item of list) {
      link.href = `/api/library/${item.id}/file?download=true`;
      link.download = item.filename;
      link.click();
    }
  }, []);

  const keep = useCallback(
    async (item: Item) => {
      if (await addToKitDialog({ project, item })) void client.invalidateQueries({ queryKey: canvasKeys.kit(project) });
    },
    [client, project],
  );

  /** Each file joins the library and this project, and lands on the canvas as a shot of its own, selected. */
  const upload = useCallback(
    async (files: File[]) => {
      const usable = files.filter((f) => /^(image|video|audio)\//.test(f.type));
      if (!usable.length) return say('Only images, videos and sound can be uploaded.', true);
      const ids: number[] = [];
      for (const [i, file] of usable.entries()) {
        say(
          usable.length > 1 ? `Uploading ${i + 1} of ${usable.length}: ${file.name}` : `Uploading ${file.name}…`,
          false,
          true,
        );
        try {
          ids.push((await uploadFile(file, project || null)).id);
        } catch (e) {
          return say((e as Error).message, true);
        }
      }
      await client.refetchQueries({ queryKey: canvasKeys.items(project) });
      select(new Set(ids));
      say(
        ids.length === 1 ? 'Uploaded. It is on the canvas.' : `${ids.length} files uploaded. They are on the canvas.`,
      );
    },
    [client, project, say, select],
  );

  return { downloader, rerun, reuseSeed, pickTake, open, download, keep, upload };
}

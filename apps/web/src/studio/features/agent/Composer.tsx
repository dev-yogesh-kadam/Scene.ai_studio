// What is under the conversation: the message box, "+" to attach a file, the suggestion of what is selected, the
// agent's status, and the buttons (fold the conversation, explain more, the workflows, skills, the model, the
// permission) with Send, which becomes Stop while the agent is thinking or its plan is being made.

import { forwardRef, useCallback, useImperativeHandle, useLayoutEffect, useRef, useState } from 'react';
import { uploadFile } from '@scene/shared/api/canvas';
import { Icon } from '../../../common/components/Icon/Icon';
import { addMenu } from '../../../common/components/Popover';
import { cx } from '../../../common/cx';
import type { Item } from '../../../common/media/item';
import { stopGeneration } from './actions';
import { MessageBox, Suggest, type BoxHandle, type Slash } from './Attachments';
import type { AgentChat } from './chat';
import { pickLibraryItem } from './LibraryPick';
import { ModelPicker, PermissionPicker, PinsPicker } from './Pickers';
import { SkillMenu, pushRecent, type SkillKey } from './SkillMenu';
import { useAgentStream } from './useAgentStream';
import s from './Composer.module.css';
import { classesOf } from '../../../common/cx';
import css0 from '../../../common/components/Shared3.module.css';
const css = classesOf(css0);

const READY = 'Ask the agent, or tell it what to make. Use + to attach a file.';

export type ComposerHandle = {
  attach: (item: Item) => void;
  focus: () => void;
  setText: (text: string) => void;
};

type Props = {
  chat: AgentChat;
  hidden: boolean; // a plan's or a question's card has the box
  selection: Item[];
  pick: ((onPick: (items: Item[]) => void) => void) | null;
};

export const Composer = forwardRef<ComposerHandle, Props>(function Composer({ chat, hidden, selection, pick }, ref) {
  const box = useRef<BoxHandle>(null);
  const skillsButton = useRef<HTMLButtonElement>(null);
  const upload = useRef<HTMLInputElement>(null);
  const keys = useRef<SkillKey | null>(null);
  const [ids, setIds] = useState<number[]>([]);
  const [menu, setMenu] = useState<{ mode: 'box' | 'slash'; search: string; slash: Slash | null } | null>(null);
  const { send } = useAgentStream(chat);
  useLayoutEffect(() => {
    chat.box = box.current;
  });
  useImperativeHandle(
    ref,
    () => ({
      attach: (item) => box.current?.attach(item),
      focus: () => box.current?.focus(),
      setText: (text) => box.current?.setText(text),
    }),
    [],
  );
  const offered = selection.filter((item) => !ids.includes(item.id)).slice(0, 8);
  const generating = chat.generating();
  const stopping = !!chat.pending || generating;
  const [tip, key] = chat.pending ? ['Stop', 'Esc'] : stopping ? ['Stop generation', ''] : ['Send message', '↵'];
  const closeMenu = useCallback(() => setMenu(null), []);
  const setKeys = useCallback((key: SkillKey | null) => {
    keys.current = key;
  }, []);
  const staysOpen = useCallback(
    (target: Node) => !!skillsButton.current?.contains(target) || !!box.current?.contains(target),
    [],
  );

  const useSkill = (id: string) => {
    if (menu?.mode === 'slash' && menu.slash) box.current?.skillHere(id, menu.slash);
    else box.current?.skillFirst(id);
    pushRecent(id);
    setMenu(null);
  };
  const attachAll = (list: Item[]) => {
    list.forEach((item) => box.current?.attach(item));
    box.current?.focus();
  };
  const uploadFiles = async (files: File[]) => {
    for (const file of files) {
      try {
        box.current?.attach((await uploadFile(file, chat.env.project() || null)) as unknown as Item);
      } catch (error) {
        chat.say(`${file.name}: ${(error as Error).message}`);
      }
    }
    if (files.length) {
      chat.env.onUploaded();
      box.current?.focus();
    }
  };
  return (
    <div
      className={cx(s['agent-composer'], stopping && s.waiting, hidden && 'hidden')}
      onClick={(e) => {
        if (e.target === e.currentTarget) box.current?.focus();
      }}
      onMouseDown={(e) => {
        // a click in the box while it waits would select words of the conversation above it
        if (stopping && !(e.target as Element).closest('button')) e.preventDefault();
      }}
    >
      {menu && (
        <SkillMenu
          mode={menu.mode}
          search={menu.search}
          onSearch={(search) => setMenu({ ...menu, search })}
          onPick={useSkill}
          onClose={closeMenu}
          onKeys={setKeys}
          outside={staysOpen}
        />
      )}
      <MessageBox
        ref={box}
        placeholder={stopping ? 'Waiting for response…' : READY}
        waiting={stopping}
        onEnter={send}
        onKey={(e) => menu?.mode === 'slash' && !!keys.current?.(e)}
        onIds={setIds}
        onSlash={(slash) => {
          if (!slash) {
            if (menu?.mode === 'slash') setMenu(null);
            return;
          }
          setMenu({ mode: 'slash', search: slash.query, slash });
        }}
      />
      <input
        ref={upload}
        type="file"
        accept="image/*,video/*,audio/*,.heic,.heif,.avif,.docx,.pdf,.txt,.md,.srt,.json,.csv,.tsv,.svg"
        multiple
        hidden
        onChange={(e) => {
          void uploadFiles([...(e.target.files ?? [])]);
          e.target.value = '';
        }}
      />
      <div className={s['agent-composer-bar']}>
        <button
          type="button"
          className={cx('icon-btn', s['agent-add'])}
          title="Attach"
          aria-label="Attach"
          aria-haspopup="menu"
          onClick={(e) =>
            addMenu(e.currentTarget, [
              { icon: 'upload', label: 'Upload media or files', run: () => upload.current?.click() },
              ...(pick ? [{ icon: 'grid' as const, label: 'Select from canvas', run: () => pick(attachAll) }] : []),
              {
                icon: 'book',
                label: 'From library',
                run: () => void pickLibraryItem().then((item) => item && attachAll([item])),
              },
            ])
          }
        >
          <Icon name="plus" />
        </button>
        <Suggest list={offered} hidden={chat.busy} onUse={() => attachAll(offered)} />
        <span style={{ flex: 1 }} />
        <span
          className={css(
            cx(s['agent-status'], 'slate-text', chat.status.hidden && 'hidden', chat.status.error && 'error'),
          )}
          title={chat.status.title}
        >
          {chat.status.text}
        </span>
        <PinsPicker chat={chat} />
        <button
          ref={skillsButton}
          type="button"
          className={cx('icon-btn', s['agent-skills'])}
          aria-haspopup="listbox"
          title="Skills — or type /name"
          aria-label="Skills"
          onClick={() => setMenu(menu?.mode === 'box' ? null : { mode: 'box', search: '', slash: null })}
        >
          <Icon name="skill" />
        </button>
        <ModelPicker chat={chat} />
        <PermissionPicker chat={chat} />
        <button
          type="button"
          className={cx(s['agent-send'], stopping && s.stopping)}
          aria-label={tip}
          onClick={() => (chat.pending ? chat.pending.stop() : generating ? void stopGeneration(chat) : send())}
        >
          {stopping ? <span className={s['stop-mark']} /> : <Icon name="arrowup" />}
          <span className={s['send-tip']} role="tooltip">
            {tip}
            {key && <kbd>{key}</kbd>}
          </span>
        </button>
      </div>
    </div>
  );
});

// The form of one Quick action (Generate image, video, audio; Upscale video): the workflows of that kind, the chosen
// one's settings and references, the price, and Generate. The form is kept while another action or the list is shown;
// another kind loads another list of workflows.

import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useCallback, useEffect, useRef, useState } from 'react';
import { asReference } from '@scene/shared/api/library';
import { castFor } from '@scene/shared/api/make';
import { api } from '../../../common/api';
import { ask } from '../../../common/components/Dialog';
import type { Item } from '../../../common/media/item';
import { JOBS } from '../../live';
import { useUser } from '../../session';
import {
  byRole,
  inUse,
  loadCatalog,
  loadWorkflow,
  pickValue,
  splitPick,
  withModel,
  type Quote,
  type Slot,
  type Workflow,
  type WorkflowRow,
} from '../jobs/jobForm';
import type { Keep } from '../kit/KeepField';
import { carryRefs, itemRef, missingRef, refSlots, removeRef, type Ref } from './refs';
import { userPrefs } from '../../userPrefs';

export type Kind = 'image' | 'video' | 'audio' | 'upscaler';

type Form = {
  kind: Kind;
  catalog: WorkflowRow[];
  wf: Workflow | null;
  values: Record<string, unknown>;
  options: Record<string, string>;
  resolution: number | null;
  orientation: string | null;
  refs: Record<string, Ref>; // what the user put in the slots (and the project's cast)
  allRefs: boolean;
  refNote: string;
};

const blank = (kind: Kind): Form => ({
  kind,
  catalog: [],
  wf: null,
  values: {},
  options: {},
  resolution: null,
  orientation: null,
  refs: {},
  allRefs: false,
  refNote: '',
});

const used = (form: Form) =>
  new Set((form.wf?.refs ?? []).filter((s) => inUse(s, form.options, form.wf)).map((s) => s.id));

export function useActionForm({ project, startFrom }: { project: number | null; startFrom: Item | null }) {
  const client = useQueryClient();
  const credits = useUser().credits;
  const [form, setForm] = useState<Form>(blank('video'));
  const [text, setText] = useState(''); // the prompt: kept when the workflow changes
  const [note, setNote] = useState('');
  const [quote, setQuote] = useState<Quote | null>(null);
  const [sending, setSending] = useState(false);
  const [keep, setKeep] = useState<Keep>(undefined);
  const [kept, setKept] = useState(0); // changes after each Generate: the next result is not kept unless asked again
  const files = useRef(new Set<string>()); // object URLs of files in slots, let go when the file leaves

  // An upscale works on the video selected on the canvas: it fills the workflow's video slot, and follows the
  // selection until a file is put there by hand.
  const upSlot = form.kind === 'upscaler' ? form.wf?.refs.find((r) => r.kind === 'video') : undefined;
  const refs = { ...form.refs };
  if (upSlot && (!refs[upSlot.id] || refs[upSlot.id].selection)) {
    if (startFrom && startFrom.kind === 'video')
      refs[upSlot.id] = {
        itemId: startFrom.id,
        name: startFrom.name,
        takes: 'video',
        shown: 'image',
        url: `/api/library/${startFrom.id}/poster`,
        selection: true,
      };
    else delete refs[upSlot.id];
  }
  const slots = refSlots(form.wf, form.kind, form.options);
  const needed = missingRef(slots, refs);

  const showError = useCallback((e: unknown) => setNote((e as Error).message || String(e)), []);

  // What the form holds now, for the steps that run after an await.
  const latest = useRef({ form, text });
  useEffect(() => {
    latest.current = { form, text };
  });

  // `picked`: a workflow's id, or a generation server model as "<workflow id>#<model>" (jobForm.pickValue).
  const selectWorkflow = useCallback(
    async (picked: string, catalog?: WorkflowRow[]) => {
      try {
        const [id, model] = splitPick(picked);
        const now = latest.current.form;
        if (model && now.wf?.id === id) {
          // another model of the same workflow: the references and the prompt stay, the length keeps to the model
          const next = withModel(now.wf, now.options, now.values, model);
          setForm((was) => ({ ...was, ...next }));
          userPrefs.setStudio({ workflows: { [now.kind]: picked } });
          return;
        }
        const wf = await loadWorkflow(id);
        const { form: was, text: typed } = latest.current;
        const defaults = Object.fromEntries(wf.options.map((o) => [o.id, o.default]));
        const fresh = Object.fromEntries(wf.controls.map((c) => [c.id, c.default]));
        const chosen = model ? withModel(wf, defaults, fresh, model) : { options: defaults, values: fresh };
        const options = chosen.options;
        const to = { wf, slots: refSlots(wf, was.kind, options) };
        // The picture references the user gave, in order, go with them to the new model, as many as it takes.
        const from =
          was.wf && was.kind === 'image'
            ? { wf: was.wf, slots: refSlots(was.wf, was.kind, was.options), refs: was.refs }
            : null;
        const carried = carryRefs(from, to, typed);
        for (const ref of Object.values(was.refs))
          if (ref.file && !carried.carried.includes(ref) && files.current.delete(ref.url)) URL.revokeObjectURL(ref.url);
        setText(carried.text);
        setForm({
          ...was,
          catalog: catalog ?? was.catalog,
          wf,
          refs: carried.refs,
          refNote: carried.note,
          allRefs: false,
          values: chosen.values,
          options,
          resolution: wf.size ? wf.size.resolution : null,
          orientation: wf.size ? wf.size.orientation : null,
        });
        userPrefs.setStudio({ workflows: { [was.kind]: pickValue(wf, options) } });
        setNote('');
      } catch (e) {
        showError(e);
      }
    },
    [showError],
  );

  /** Show the form for `kind`: the same kind keeps what is in it; another loads that kind's workflows. */
  const open = useCallback(
    async (kind: Kind) => {
      const was = latest.current.form;
      if (was.kind === kind && was.wf) return;
      const fresh = blank(kind);
      latest.current = { ...latest.current, form: fresh };
      setForm(fresh);
      setNote('');
      try {
        const list = await loadCatalog();
        const catalog = list.workflows.filter((w) => !w.error && w.kind === kind);
        latest.current.form = { ...latest.current.form, catalog };
        setForm((now) => ({ ...now, catalog }));
        if (!catalog.length) {
          setNote(`No ${kind} workflows yet. Save a ComfyUI workflow into the workflows/${kind} folder, then reload.`);
          return;
        }
        // The model the user picked last for this kind (or the studio's default, when one is set). With neither, none
        // is picked for them: they choose it in the Model list.
        const last = userPrefs.studio().workflows[kind] || list.default || '';
        const wanted = catalog.find((w) => w.id === splitPick(last)[0]);
        if (wanted) await selectWorkflow(last, catalog);
      } catch (e) {
        showError(e);
      }
    },
    [selectWorkflow, showError],
  );

  // The project's always-on NeuralCore entries go into the slots this workflow has for them; a slot the user filled
  // is left alone. Again when the NeuralCore changes.
  const kitChanged = useQuery({ queryKey: ['kit', project ?? 0], enabled: false }).dataUpdatedAt;
  const wfId = form.wf?.id;
  useEffect(() => {
    if (!wfId) return;
    let live = true;
    void castFor(project || 0, wfId)
      .then(
        (found) => found.fills,
        () => [],
      )
      .then((fills) => {
        if (!live) return;
        setForm((was) => {
          if (was.wf?.id !== wfId) return was;
          const next = Object.fromEntries(Object.entries(was.refs).filter(([, r]) => !r.cast));
          for (const f of fills)
            if (!next[f.slot])
              next[f.slot] = {
                assetId: f.asset,
                name: f.name,
                takes: f.kind,
                shown: f.item_kind,
                url: `/api/kit/${f.asset}/file`,
                cast: true,
              };
          return { ...was, refs: next };
        });
      });
    return () => {
      live = false;
    };
  }, [wfId, project, kitChanged]);

  const setRef = useCallback((slot: Slot, value: File | Ref | null) => {
    setForm((was) => {
      const next = { ...was.refs };
      const old = next[slot.id];
      if (old?.file && files.current.delete(old.url)) URL.revokeObjectURL(old.url);
      if (value instanceof File) {
        const url = URL.createObjectURL(value);
        files.current.add(url);
        next[slot.id] = { file: value, name: value.name, url };
      } else if (value) next[slot.id] = value;
      else delete next[slot.id];
      return { ...was, refs: next };
    });
  }, []);
  /** A video's length, read by the browser from its file: an upscale is priced by it. */
  const setSeconds = useCallback((slotId: string, seconds: number) => {
    setForm((was) =>
      was.refs[slotId] ? { ...was, refs: { ...was.refs, [slotId]: { ...was.refs[slotId], seconds } } } : was,
    );
  }, []);

  const settings = (extra: Record<string, { comfy_name: string; name: string }> = {}) => {
    const wf = form.wf!;
    const source = upSlot && refs[upSlot.id]; // the result is named after the video it is made from
    const sent: Record<string, unknown> = { ...extra };
    const inUseNow = used(form);
    for (const [id, r] of Object.entries(refs)) if (r.assetId && inUseNow.has(id)) sent[id] = { asset_id: r.assetId };
    const prompt = byRole(wf, 'prompt');
    return {
      workflow: wf.id,
      name: source ? `${source.name} upscaled` : wf.id.split('/')[1],
      values: prompt ? { ...form.values, [prompt.id]: text } : form.values,
      options: form.options,
      resolution: form.resolution,
      orientation: form.orientation,
      seed_mode: 'random',
      clips: 1,
      project_id: project,
      parent: source && source.itemId ? source.itemId : null, // an upscale joins the row of the video it is made from
      refs: sent,
      source_seconds: (source && source.seconds) || undefined,
      keep,
    };
  };

  // The price, a moment after the last change (and when the balance changes).
  const priced = form.wf ? JSON.stringify(settings()) : '';
  useEffect(() => {
    if (!priced) return;
    const timer = setTimeout(() => {
      api<Quote>('/api/estimate', { method: 'POST', json: JSON.parse(priced) as unknown }).then(
        (found) => {
          setQuote(found);
          setNote(found.credits > found.balance ? `You have ${found.balance} cr. This needs ${found.credits} cr.` : '');
        },
        (e: Error) => {
          setQuote(null);
          setNote(e.message);
        },
      );
    }, 150);
    return () => clearTimeout(timer);
  }, [priced, credits]);

  const lacking = !!quote && quote.credits > quote.balance;
  const blocked = !form.wf || !!needed || lacking || sending;

  const generate = async () => {
    setNote('');
    const wf = form.wf;
    if (!wf || blocked) return;
    if (byRole(wf, 'prompt') && !text.trim()) return setNote('Write a prompt first.');
    const missing = wf.refs.filter((r) => inUse(r, form.options, wf)).find((r) => !r.optional && !refs[r.id]);
    if (missing) return setNote(`Add a file for "${missing.label.split(' (')[0]}".`);
    const dur = byRole(wf, 'duration');
    const ctx: Record<string, unknown> = {
      ...form.options,
      resolution: form.resolution,
      orientation: form.orientation,
      clips: 1,
      duration: dur ? Number(form.values[dur.id]) : undefined,
    };
    const hits = wf.confirm.filter((c) =>
      Object.entries(c.when).every(([k, v]) => ([] as unknown[]).concat(v).some((x) => x === ctx[k])),
    );
    if (
      hits.length &&
      !(await ask({
        title: 'Generate anyway?',
        confirm: 'Generate',
        message: hits.map((h) => h.message).join('\n') + `\n\nEstimated time: ${quote?.text || 'unknown'}`,
      }))
    )
      return;
    setSending(true);
    try {
      const extra: Record<string, { comfy_name: string; name: string }> = {};
      const inUseNow = used(form);
      for (const [slot, r] of Object.entries(refs)) {
        // library items are sent to the render server now
        if (!r.itemId || !inUseNow.has(slot)) continue;
        const ref = await asReference(r.itemId, r.takes);
        extra[slot] = { comfy_name: ref.comfy_name, name: ref.name };
      }
      const data = new FormData();
      data.append('settings', JSON.stringify(settings(extra)));
      for (const [id, r] of Object.entries(refs))
        if (r.file && inUseNow.has(id)) data.append('ref:' + id, r.file, r.name);
      await api('/api/jobs', { method: 'POST', body: data });
      setKept((n) => n + 1);
      void client.invalidateQueries({ queryKey: JOBS });
    } catch (e) {
      showError(e);
    }
    setSending(false);
  };

  const remove = (index: number) => {
    if (!form.wf) return;
    const out = removeRef(form.wf, slots, form.refs, index, text);
    if (out.gone?.file && files.current.delete(out.gone.url)) URL.revokeObjectURL(out.gone.url);
    setText(out.text);
    setForm((was) => ({ ...was, refs: out.refs, refNote: out.note }));
  };
  /** Put a picture into the next free reference: REF n is always the n-th slot. */
  const addRef = (value: File | Ref) => {
    const slot = slots[slots.filter((s) => refs[s.id]).length];
    if (!slot) return;
    setForm((was) => ({ ...was, refNote: '' }));
    setRef(slot, value);
  };
  /** A frame from the canvas onto a slot; false when the slot can't take it. */
  const dropItem = (slotId: string, item: Item) => {
    const slot = form.wf?.refs.find((r) => r.id === slotId);
    const ref = slot && itemRef(slot, item);
    if (!slot || !ref) return false;
    setRef(slot, ref);
    return true;
  };

  useEffect(() => {
    const held = files.current;
    return () => held.forEach((url) => URL.revokeObjectURL(url));
  }, []);

  return {
    form,
    setForm,
    refs,
    slots,
    needed,
    text,
    setText,
    note: note || (needed && !lacking ? `Add ${needed} to generate.` : ''),
    quote,
    sending,
    blocked,
    kept,
    setKeep,
    open,
    selectWorkflow,
    setRef,
    setSeconds,
    addRef,
    remove,
    dropItem,
    generate,
    showError,
  };
}

export type ActionForm = ReturnType<typeof useActionForm>;

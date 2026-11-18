// The Providers part of Servers & APIs, in words and types: what the console is sent by /api/admin/providers
// (backend/scene/api/providers.py) and how a key's check and status are said. A key itself is never sent: only its
// label and last 4 characters.

export type ProviderKey = {
  id: number; // below 0: set by an environment variable (fixed), shown but not changed here
  provider_id: number;
  label: string;
  last4: string;
  has_secret: boolean;
  active: boolean;
  priority: number;
  max_concurrent: number | null;
  daily_cap: number | null;
  status: 'ok' | 'invalid' | 'no_credit' | 'rate_limited' | 'unknown';
  cooldown_until: number | null;
  last_error: string;
  last_checked: number | null;
  last_used: number | null;
  fixed: boolean;
  credits: { available?: number; used_today?: number } | null;
  alerts: string[];
  mode: string; // "live" or "test", as the provider said
  said_max_concurrent: number | null;
  unlocks?: Unlocked[]; // a Scene provider's key: the models it unlocks, by capability
};

/** One capability a key unlocks, with its models. */
export type Unlocked = { capability: string; words: string; models: { id: string; name: string }[] };

/** One line of a paste of several keys, as /keys/many answered it. */
export type ManyResult = { line: number; label: string; saved: boolean; check: Check; words?: string };

/** One capability of What makes what (/api/admin/providers/capabilities). */
export type Capability = {
  capability: string;
  words: string;
  models: { id: string; name: string; providers: string[]; keys: { label: string; mode: string; status: string }[] }[];
  live: boolean; // a live key makes it (not only test keys)
  comfy: { id: string; title: string }[];
  comfyui_on: boolean;
  can_switch_off: boolean;
  why_not: string;
  state: 'both' | 'provider' | 'comfyui' | 'none';
};

export type CoverageData = { router: string; capabilities: Capability[] };

export const STATE_WORDS: Record<Capability['state'], string> = {
  both: 'Providers and ComfyUI',
  provider: 'Providers only',
  comfyui: 'ComfyUI only',
  none: 'Nothing makes it',
};

/** "Video: Seedance 2.5, Kling 3 · Voiceover: Speech". */
export function unlockWords(unlocks: Unlocked[] | undefined): string {
  return (unlocks ?? []).map((u) => `${u.words}: ${u.models.map((m) => m.name).join(', ')}`).join(' · ');
}

/** "Saved", "Already here as Video key", or the check's words, for one pasted line. */
export function manyWords(r: ManyResult): string {
  if (r.words) return r.words;
  if (r.saved)
    return r.check.ok ? 'Saved · ' + checkWords(r.check) : 'Saved, though ' + checkWords(r.check).replace(/^It/, 'it');
  return checkWords(r.check);
}

export type Provider = {
  id: number;
  kind: string;
  kind_name: string;
  name: string;
  base_url: string;
  active: boolean;
  priority: number;
  legacy: string;
  keys: ProviderKey[];
  models: number;
  agent: boolean;
  keyless?: boolean; // no key and no address: Claude on this PC
};

export type Check = {
  ok: boolean;
  status: string;
  error: string;
  models: number;
  credits?: number | null;
  alerts?: string[];
};

export type ProvidersData = {
  kinds: Record<string, string>;
  self_hosted: string[];
  keyless?: string[]; // the kinds with no key (claude_local)
  built_in?: string[]; // the kinds the studio makes itself, one each, never added here (local_tools: On this PC)
  providers: Provider[];
  router: 'off' | 'shadow' | 'on';
  modes: string[];
  agent_provider: number | null;
  testing: string;
  check?: Check;
  saved?: boolean | number; // one key: whether it was saved; several: how many were
  results?: ManyResult[];
  provider_id?: number | null; // the provider a key was added to (made by the first key of a new one)
};

export const ROUTER_WORDS: Record<string, string> = {
  off: 'Off: renders go the way they always did (ComfyUI, and the generation server as a ComfyUI server).',
  shadow:
    'Shadow: renders go the way they always did; each job also notes which provider and key the router would have picked, to compare.',
  on: "On: the providers' models are offered and made through their providers; ComfyUI's workflows stay on the load balancer.",
};

export const STATUS_WORDS: Record<string, string> = {
  ok: 'Works',
  invalid: 'Invalid: paste a new key, or remove it',
  no_credit: 'Out of credit',
  rate_limited: 'Rate limited',
  unknown: 'Not checked yet',
};

const plural = (n: number, word: string) => `${n.toLocaleString('en-US')} ${word}${n === 1 ? '' : 's'}`;

/** "Works · 22 models · 91,296 credits", or "It does not work: <the provider's words>". */
export function checkWords(check: Check): string {
  if (!check.ok) return 'It does not work: ' + (check.error || 'no reason given');
  return [
    'Works',
    plural(check.models, 'model'),
    typeof check.credits === 'number' ? plural(check.credits, 'credit') : '',
    ...(check.alerts ?? []),
  ]
    .filter(Boolean)
    .join(' · ');
}

/** How one key is now, in a few words: its status, a cooldown's end, its mode and credits. */
export function keyWords(key: ProviderKey, now = Date.now() / 1000): string {
  const resting = key.cooldown_until && key.cooldown_until > now ? Math.ceil((key.cooldown_until - now) / 60) : 0;
  return [
    key.active ? (STATUS_WORDS[key.status] ?? key.status) : 'Off',
    resting ? `resting ${resting} min` : '',
    key.mode === 'test' ? 'test key' : '',
    typeof key.credits?.available === 'number' ? plural(key.credits.available, 'credit') : '',
  ]
    .filter(Boolean)
    .join(' · ');
}

/** The dot's colour class for a key. */
export function keyDot(key: ProviderKey): string {
  if (!key.active) return '';
  if (key.status === 'ok') return 'online';
  return key.status === 'unknown' ? '' : 'offline';
}

/** "Some value", or null when the field was left empty; throws on what is not a whole number. */
export function wholeOrNull(text: string): number | null {
  const t = text.trim();
  if (!t) return null;
  if (!/^\d+$/.test(t)) throw new Error(`"${t}" is not a whole number.`);
  return Number(t);
}

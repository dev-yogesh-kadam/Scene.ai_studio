// What the Pricing section reads, and how its numbers are written.

export const KINDS = [
  { id: 'image', label: 'Image' },
  { id: 'video', label: 'Video' },
  { id: 'audio', label: 'Audio' },
  { id: 'motion', label: 'Motion graphics' },
  { id: 'overlay', label: 'Motion graphics over a video' },
  { id: 'upscaler', label: 'Upscale' },
];
export const trim = (value: number) => Number(Number(value).toFixed(2)).toLocaleString();
export const rupees = (value: number) => '₹' + trim(value);

/** What the chosen resolution and quality multiply a price by. */
export const GROUPS = [
  {
    id: 'resolution',
    label: 'Resolution',
    keys: ['480', '720', '1080'],
    name: (k: string) => k + 'p',
    about: '768p counts as 720p. Pictures are not priced by size.',
  },
  {
    id: 'quality',
    label: 'Quality',
    keys: ['draft', 'final', 'low', 'medium', 'high'],
    name: (k: string) => k[0].toUpperCase() + k.slice(1),
    about: 'Draft and Final for most workflows; Low, Medium and High for some video ones.',
  },
];

type Own = Record<string, Record<string, number>>;
export type WorkflowRow = {
  id: string;
  title: string;
  kind: string;
  base?: number;
  per_second?: number;
  credits_per_second?: number | null;
  base_credits?: number | null;
  multiplier: number;
  own_factors?: Own;
  example: number;
  preferred_server?: string;
  enabled: boolean | number;
  admins_only?: boolean | number;
  // A generation workflow: its models (the generation server's) and the studio's price of each at each resolution.
  models?: { model: string; name: string; resolutions: string[]; prices?: Record<string, number> }[];
  model_prices?: Record<string, Record<string, number>>;
};
export type PackageRow = {
  id: number;
  name: string;
  price_inr: number;
  credits: number;
  bonus_credits: number;
  active: boolean | number;
};
export type ServerRow = {
  id: number;
  name: string;
  role: string;
  gpu: string;
  vram_gb: number;
  cpu: string;
  generation_power_w?: number;
  preferred_workflows?: string;
  active: boolean | number;
  renders?: boolean | number;
};
export type Data = {
  inr_per_1000_credits: number;
  electricity_inr_per_kwh: number;
  inr_per_usd: number;
  rates: Record<string, number>;
  per_job: string[];
  workflows: WorkflowRow[];
  packages: PackageRow[];
  servers: ServerRow[];
};
export type Factors = { factors: Own; suggested: Own; samples: Own; defaults: Own };

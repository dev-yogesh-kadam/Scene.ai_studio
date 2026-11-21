// What GET /api/admin/overview says.

export type Series = {
  active_users: number[];
  videos: number[];
  images: number[];
  done: number[];
  failed: number[];
  cancelled: number[];
  gpu_minutes: number[];
  credits: number[];
};
export type Period = {
  active_users: number;
  items: number;
  success_rate: number | null;
  gpu_seconds: number;
  credits: number;
  jobs: number;
  failed: number;
  avg_wait: number;
  avg_run: number;
  signups: number;
};
export type Running = {
  name: string;
  user_name: string;
  workflow: string;
  started: number;
  steps: number;
  step: number;
  clip: number;
  clips: number;
  node?: string;
};
export type Queue = {
  paused: boolean;
  running: Running | null;
  waiting_total: number;
  waiting: { id: string; name: string; user_name: string; created: number; priority?: number }[];
};
export type Health = {
  model: boolean | null;
  alerts: number;
  maintenance: boolean;
  disk_free: number;
  backups_on: boolean;
  last_backup: number | null;
};
export type EarnRow = {
  title: string;
  done: number;
  revenue_inr: number | null;
  electricity_inr: number | null;
  margin_inr: number | null;
};
export type Overview = {
  days: number;
  current: Period;
  previous: Period;
  series: Series;
  calendar: string[];
  totals: { users: number; items: number; credits_held: number };
  health: Health;
  queue: Queue;
  announcement: { text?: string };
  attention: { level: string; text: string; tab: string }[];
  online: {
    name: string;
    role: string;
    pages: string[];
    tabs: number;
    job?: { status: string; name: string } | null;
    since: number;
  }[];
  signups: {
    open: boolean;
    today: number;
    per_day?: number;
    recent: {
      id: number;
      name: string;
      email: string;
      ip?: string;
      jobs: number;
      disabled?: number | boolean;
      created: number;
    }[];
  };
  activity: { kind: string; who?: string; text: string; time: number }[];
  economics: {
    totals: { revenue_inr: number; electricity_inr: number; margin_percent: number };
    workflows: EarnRow[];
    unmeasured: string[];
  };
  top_users: { name: string; email: string; jobs: number; credits: number; gpu_seconds: number }[];
  top_workflows: { workflow: string; jobs: number; done: number; failed: number; avg_seconds: number }[];
  failures: { jobs: number; error?: string; last_seen: number }[];
};

// How the Claude connection is, in words: the Providers' "Claude on this PC" card, the agent's line under "The agent
// uses", the System section's Agent model card and its checks row all say it the same way. See
// backend/scene/claude_connection.py (status).

export type PlanWindow = { utilization: number | null; resets_at: number | null } | null;

export type ClaudeStatus = {
  mode?: string; // "this_pc" or "api_key"
  online?: boolean;
  detail?: string; // why it does not work, and the fix
  claude_version?: string;
  signed_in?: boolean | null; // Claude Code's sign-in on this PC
  account?: string; // the email Claude Code here is signed in as (Claude on this PC)
  plan?: string; // its subscription: pro, max ...
  session?: PlanWindow; // the plan's 5-hour window, as the last call reported it
  week?: PlanWindow; // the plan's week
  key_works?: boolean | null; // the API key
  running?: number; // calls answering now
  limit?: number | null; // the most at once
  testing?: string; // said while a personal Claude subscription is in use
};

export const MODE_NAMES: Record<string, string> = {
  this_pc: 'Claude on this PC',
  api_key: 'Anthropic API key',
};

const PLANS: Record<string, string> = { pro: 'Pro', max: 'Max', team: 'Team', enterprise: 'Enterprise', free: 'Free' };

/** "Pro", "Max" ...: a plan's name as Claude Code gives it, capitalized. */
export function planName(plan?: string): string {
  if (!plan) return '';
  return PLANS[plan.toLowerCase()] ?? plan[0].toUpperCase() + plan.slice(1);
}

/** "2 of 3 running", or "1 running" with no limit. */
export function runningWords(s: ClaudeStatus): string {
  const running = s.running ?? 0;
  return s.limit ? `${running} of ${s.limit} running` : `${running} running`;
}

/** "Claude on this PC · Claude Code 2.1.3 · signed in as name@… · Pro · 1 of 3 calls running": what works, at a glance. */
export function claudeWords(s: ClaudeStatus): string {
  const running = s.running ?? 0;
  return [
    MODE_NAMES[s.mode ?? ''] ?? 'Claude',
    s.claude_version ? 'Claude Code ' + s.claude_version : '',
    s.account ? 'signed in as ' + s.account : s.signed_in ? 'signed in' : '',
    planName(s.plan),
    s.key_works ? 'key works' : '',
    s.limit ? `${running} of ${s.limit} calls running` : `${running} call${running === 1 ? '' : 's'} running`,
  ]
    .filter(Boolean)
    .join(' · ');
}

/** Claude on this PC's status line: "Signed in as name@… · Pro · Claude Code 2.1.322", or why not and the fix. */
export function signInWords(s: ClaudeStatus): string {
  if (!s.online) return s.detail || 'Not checked yet: press Check.';
  return [
    s.account ? 'Signed in as ' + s.account : 'Signed in',
    planName(s.plan),
    s.claude_version ? 'Claude Code ' + s.claude_version : '',
  ]
    .filter(Boolean)
    .join(' · ');
}

const percent = (u: number | null) => (typeof u === 'number' ? `${Math.round(u * 100)}%` : '?');

/** "This 5-hour window: 27% (resets 14:10) · This week: 34% (resets Mon)", or that no call has said yet. */
export function usageWords(s: ClaudeStatus): string {
  const at = (when: number | null, how: Intl.DateTimeFormatOptions) =>
    typeof when === 'number' ? ` (resets ${new Date(when * 1000).toLocaleString('en-GB', how)})` : '';
  const parts = [
    s.session
      ? `This 5-hour window: ${percent(s.session.utilization)}${at(s.session.resets_at, { hour: '2-digit', minute: '2-digit' })}`
      : '',
    s.week ? `This week: ${percent(s.week.utilization)}${at(s.week.resets_at, { weekday: 'short' })}` : '',
  ].filter(Boolean);
  return parts.length ? parts.join(' · ') : 'Usage shows after the first call: Claude Code reports it as it answers.';
}

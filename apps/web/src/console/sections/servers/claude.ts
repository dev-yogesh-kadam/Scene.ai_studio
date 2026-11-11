// How the Claude connection is, in words: the Servers section's Claude connection card, the System section's Agent model
// card and its checks row all say it the same way. See backend/scene/claude_connection.py (status).

export type ClaudeStatus = {
  mode?: string; // "api_key" or "lufi_bridge"
  online?: boolean;
  detail?: string; // why it does not work
  claude_version?: string;
  signed_in?: boolean | null; // the bridge's Claude Code
  key_works?: boolean | null; // the API key
  running?: number;
  limit?: number | null; // the most calls the bridge runs at once
  bridge_version?: string;
  testing?: string; // said while the bridge is in use
};

export const MODE_NAMES: Record<string, string> = { api_key: 'Anthropic API key', lufi_bridge: 'LUFI bridge' };

/** "LUFI bridge · Claude Code 2.1.3 · signed in · 1 of 4 calls running": what works, at a glance. */
export function claudeWords(s: ClaudeStatus): string {
  const running = s.running ?? 0;
  return [
    MODE_NAMES[s.mode ?? ''] ?? 'Claude',
    s.claude_version ? 'Claude Code ' + s.claude_version : '',
    s.signed_in ? 'signed in' : '',
    s.key_works ? 'key works' : '',
    s.limit ? `${running} of ${s.limit} calls running` : `${running} call${running === 1 ? '' : 's'} running`,
  ]
    .filter(Boolean)
    .join(' · ');
}

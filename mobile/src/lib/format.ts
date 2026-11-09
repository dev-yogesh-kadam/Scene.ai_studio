// Numbers, times and sizes in short, friendly words.

/** "just now", "5 min ago", "3 h ago", "yesterday", "12 Oct". `seconds` is a Unix time in seconds, as the backend sends. */
export function timeAgo(seconds: number, now = Date.now() / 1000) {
  const gone = Math.max(0, now - seconds);
  if (gone < 45) return 'just now';
  if (gone < 3600) return `${Math.round(gone / 60)} min ago`;
  if (gone < 86400) return `${Math.round(gone / 3600)} h ago`;
  if (gone < 172800) return 'yesterday';
  return new Date(seconds * 1000).toLocaleDateString(undefined, { day: 'numeric', month: 'short' });
}

/** "about 40 s left", "about 3 min left". */
export function timeLeft(seconds: number | null | undefined) {
  if (seconds == null || !isFinite(seconds)) return null;
  if (seconds < 60) return `about ${Math.max(5, Math.round(seconds / 5) * 5)} s left`;
  if (seconds < 3600) return `about ${Math.round(seconds / 60)} min left`;
  return `about ${(seconds / 3600).toFixed(1)} h left`;
}

/** A clip's length: "0:07", "2:15". */
export function clipLength(seconds: number | null | undefined) {
  if (!seconds) return null;
  const s = Math.round(seconds);
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
}

export function fileSize(bytes: number | null | undefined) {
  if (!bytes) return null;
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`;
  if (bytes < 1024 ** 3) return `${(bytes / 1024 ** 2).toFixed(1)} MB`;
  return `${(bytes / 1024 ** 3).toFixed(2)} GB`;
}

export function credits(amount: number) {
  return `${amount.toLocaleString()} cr`;
}

export function initials(name: string) {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase())
    .join('');
}

/** The credit ledger's reasons (credits.py) in words. */
export function creditReason(reason: string) {
  const words: Record<string, string> = {
    welcome: 'Welcome credits',
    generation: 'Made',
    refund: 'Given back',
    agent: 'Agent messages',
    'admin grant': 'From an admin',
  };
  return words[reason] ?? reason.charAt(0).toUpperCase() + reason.slice(1);
}

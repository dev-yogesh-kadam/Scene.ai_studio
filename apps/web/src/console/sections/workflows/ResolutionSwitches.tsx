// Resolutions an admin switched off, for a kind or one workflow: a box for each, ticked while it is on. A job asked at
// one that is off is made at the next one allowed, and its reply says so. One stays on.

import { useState } from 'react';
import { api } from '../../../common/api';
import { useConsole } from '../shared/context';
import { say } from '../shared/ui';

const TIERS = ['480', '720', '1080'];

export function ResolutionSwitches({
  id,
  off,
  onError,
}: {
  id: string;
  off?: string[];
  onError?: (message: string) => void;
}) {
  const { refresh } = useConsole();
  const [now, setNow] = useState<string[]>(off || []);
  const flip = async (tier: string, on: boolean) => {
    const before = now;
    const next = on ? now.filter((t) => t !== tier) : [...now, tier];
    setNow(next);
    try {
      const saved = await api<{ off: string[] }>('/api/admin/workflows/resolutions', {
        method: 'PUT',
        json: { key: id, off: TIERS.filter((t) => next.includes(t)) },
      });
      setNow(saved.off);
      onError?.('');
      await refresh();
    } catch (e) {
      setNow(before);
      if (onError) onError((e as Error).message);
      else void say((e as Error).message);
    }
  };
  return (
    <div className="row">
      {TIERS.map((t) => (
        <label key={t} className="check" style={{ marginRight: 14 }}>
          <input type="checkbox" checked={!now.includes(t)} onChange={(e) => void flip(t, e.target.checked)} />
          {t + 'p'}
        </label>
      ))}
    </div>
  );
}

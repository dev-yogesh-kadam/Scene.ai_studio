// Where the plans the studio carries out stand, as the live connection says them (docs/r1-plan-runner-design.md): each
// fills in the job of its steps, so the results, the checks and the retakes follow. No plan runs on this page.

import { useQuery } from '@tanstack/react-query';
import { useEffect } from 'react';
import { PLANS } from '../../live';
import { applyPlans } from './actions';
import type { AgentChat } from './chat';
import type { ServerPlan } from './types';

export function usePlanProgress(chat: AgentChat) {
  const heard = useQuery<Map<number, ServerPlan>>({
    queryKey: PLANS,
    queryFn: () => new Map(),
    staleTime: Infinity,
    enabled: false,
  }).data;
  useEffect(() => {
    if (!heard) return;
    for (const [id, plan] of heard) chat.plans.set(id, plan);
    applyPlans(chat);
  }, [chat, heard]);
}

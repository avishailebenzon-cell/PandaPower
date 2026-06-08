/**
 * Polls the three WhatsApp agents' conversation lists and reports how many
 * conversations are currently *active* (open and not paused) — used to show a
 * blinking "live conversations" indicator in the bottom status bar.
 */

import { useEffect, useState } from "react";
import {
  talConversationsApi,
  eladConversationsApi,
  pandiConversationsApi,
  type ConversationSummary,
} from "@/api/conversationsApi";

export interface ActiveConversationsState {
  total: number;
  tal: number;
  elad: number;
  pandi: number;
}

const isActive = (c: ConversationSummary): boolean =>
  !c.auto_reply_paused && (c.status === "active" || c.status === "open");

const EMPTY: ActiveConversationsState = { total: 0, tal: 0, elad: 0, pandi: 0 };

export function useActiveConversations(pollMs = 8000): ActiveConversationsState {
  const [state, setState] = useState<ActiveConversationsState>(EMPTY);

  useEffect(() => {
    let cancelled = false;

    const tick = async () => {
      const [tal, elad, pandi] = await Promise.all([
        talConversationsApi.list().catch(() => [] as ConversationSummary[]),
        eladConversationsApi.list().catch(() => [] as ConversationSummary[]),
        pandiConversationsApi.list().catch(() => [] as ConversationSummary[]),
      ]);
      if (cancelled) return;
      const t = tal.filter(isActive).length;
      const e = elad.filter(isActive).length;
      const p = pandi.filter(isActive).length;
      setState({ total: t + e + p, tal: t, elad: e, pandi: p });
    };

    tick();
    const id = setInterval(tick, pollMs);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, [pollMs]);

  return state;
}

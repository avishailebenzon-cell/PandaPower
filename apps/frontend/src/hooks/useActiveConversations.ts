/**
 * Polls the three WhatsApp agents' conversation lists and reports how many
 * conversations are *live right now* — used for the blinking "live
 * conversations" indicator in the bottom status bar.
 *
 * "Live" means there was a real message exchanged recently (within
 * ACTIVE_WINDOW_MS) and the agent isn't paused. We deliberately do NOT count by
 * the conversation's status field: conversations are never marked "closed", so
 * a status-based count would only ever grow and never reflect reality (e.g. a
 * conversation that ended, or whose match was deleted, would linger forever).
 * Recency-based counting self-corrects — quiet conversations simply drop off.
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

// A conversation counts as "live" if its last message is this recent.
const ACTIVE_WINDOW_MS = 15 * 60 * 1000; // 15 minutes

const isActive = (c: ConversationSummary): boolean => {
  if (c.auto_reply_paused) return false;
  if (!c.last_message_at) return false;
  const ts = Date.parse(c.last_message_at);
  if (Number.isNaN(ts)) return false;
  return Date.now() - ts <= ACTIVE_WINDOW_MS;
};

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

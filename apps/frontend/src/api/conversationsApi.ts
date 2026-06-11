/**
 * Shared client for the WhatsApp-style conversation screens used by the three
 * agents — Tal (/admin/tal), Elad (/admin/elad) and Pandi (/admin/pandi-chat).
 *
 * The backend exposes an identical endpoint shape under each base path, so one
 * factory produces a typed client for any of them.
 */

const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";

export interface ChatMessage {
  id?: string;
  direction: "inbound" | "outbound";
  text: string | null;
  author?: "agent" | "human" | "candidate" | null;
  created_at?: string;
  /** "text" (default) | "file" | "image" | "audio" — "file" marks a transferred CV. */
  message_type?: string | null;
  /** view/download URL for an attached file (e.g. a CV sent to a client). */
  file_url?: string | null;
}

/** Why a WhatsApp wasn't delivered (mirrors the backend codes). */
export type DeliveryReason =
  | "no_phone"
  | "invalid_phone"
  | "not_configured"
  | "green_api_error"
  | "exception"
  | null;

export interface SendResult {
  text: string;
  delivered: boolean;
  delivery_reason?: DeliveryReason;
}

/** Human-readable Hebrew explanation for a non-delivery reason. */
export function deliveryReasonText(reason: DeliveryReason): string {
  switch (reason) {
    case "no_phone":
      return "אין מספר טלפון לנמען — ההודעה נשמרה אך לא נשלחה.";
    case "invalid_phone":
      return "מספר הטלפון אינו תקין — ההודעה נשמרה אך לא נשלחה. בדקו את המספר (לדוגמה: 050-1234567).";
    case "not_configured":
      return "חיבור ה-WhatsApp (Green API) אינו מוגדר — ההודעה נשמרה אך לא נשלחה.";
    case "green_api_error":
      return "Green API דחה את השליחה — ההודעה נשמרה אך לא נשלחה. ודאו שהמספר קיים בוואטסאפ.";
    case "exception":
      return "אירעה שגיאה בשליחה — ההודעה נשמרה אך לא נשלחה.";
    default:
      return "ההודעה לא נשלחה.";
  }
}

export interface ConversationSummary {
  id: string;
  candidate_name: string;
  job_title: string;
  status: string;
  auto_reply_paused: boolean;
  last_message?: string | null;
  last_message_at?: string | null;
  started_at?: string | null;
}

export interface ConversationDetail {
  id: string;
  candidate_name: string;
  job_title: string;
  status: string;
  auto_reply_paused: boolean;
  messages: ChatMessage[];
}

export interface ConversationsApi {
  list: () => Promise<ConversationSummary[]>;
  get: (id: string) => Promise<ConversationDetail>;
  send: (id: string, text: string) => Promise<SendResult>;
  pause: (id: string, paused: boolean) => Promise<{ auto_reply_paused: boolean }>;
  /** Operator-initiated close (closed=true) or reopen (closed=false). */
  close: (id: string, closed: boolean) => Promise<{ status: string; auto_reply_paused: boolean }>;
  generate: (id: string) => Promise<SendResult>;
}

/** Build a conversations client for a given backend base path (e.g. "/admin/tal"). */
export function makeConversationsApi(basePath: string): ConversationsApi {
  const url = (p: string) => `${API_BASE}${basePath}${p}`;
  return {
    async list() {
      const res = await fetch(url("/conversations"));
      if (!res.ok) throw new Error("Failed to list conversations");
      return res.json();
    },
    async get(id) {
      const res = await fetch(url(`/conversations/${id}`));
      if (!res.ok) throw new Error("Failed to load conversation");
      return res.json();
    },
    async send(id, text) {
      const res = await fetch(url(`/conversations/${id}/send`), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text }),
      });
      if (!res.ok) throw new Error("Failed to send message");
      return res.json();
    },
    async pause(id, paused) {
      const res = await fetch(url(`/conversations/${id}/pause`), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ paused }),
      });
      if (!res.ok) throw new Error("Failed to update pause state");
      return res.json();
    },
    async close(id, closed) {
      const res = await fetch(url(`/conversations/${id}/close`), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ closed }),
      });
      if (!res.ok) throw new Error("Failed to update conversation status");
      return res.json();
    },
    async generate(id) {
      const res = await fetch(url(`/conversations/${id}/generate`), {
        method: "POST",
      });
      if (!res.ok) throw new Error("Failed to generate reply");
      return res.json();
    },
  };
}

export const talConversationsApi = makeConversationsApi("/admin/tal");
export const eladConversationsApi = makeConversationsApi("/admin/elad");
export const pandiConversationsApi = makeConversationsApi("/admin/pandi-chat");
export const pandiusConversationsApi = makeConversationsApi("/admin/pandius-chat");

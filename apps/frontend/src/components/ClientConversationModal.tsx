/**
 * ClientConversationModal — view a single client's WhatsApp conversation with
 * an agent (Libi / Pandius) inline from the clients table, without leaving the
 * page. Read-only: it shows the message history, ordered chronologically.
 *
 * It reuses the existing endpoints:
 *   - fetchDetail(clientId) → { conversations: [{ id, ... }] }  (recent threads)
 *   - conversationsApi.get(conversationId) → { messages: ChatMessage[] }
 */

import { useQuery } from "@tanstack/react-query";
import { X } from "lucide-react";
import type { ChatMessage, ConversationsApi } from "@/api/conversationsApi";

function formatTime(iso?: string): string {
  if (!iso) return "";
  try {
    return new Date(iso).toLocaleString("he-IL", {
      day: "2-digit",
      month: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return "";
  }
}

interface Props {
  open: boolean;
  onClose: () => void;
  clientId: string;
  clientName: string;
  agentName: string;
  conversationsApi: ConversationsApi;
  /** Returns the client detail incl. its recent conversations (each with an id). */
  fetchDetail: (clientId: string) => Promise<{ conversations: any[] }>;
}

export function ClientConversationModal({
  open,
  onClose,
  clientId,
  clientName,
  agentName,
  conversationsApi,
  fetchDetail,
}: Props) {
  const query = useQuery({
    queryKey: ["client-conversation", clientId],
    enabled: open && !!clientId,
    queryFn: async (): Promise<ChatMessage[]> => {
      const detail = await fetchDetail(clientId);
      const convs = detail.conversations || [];
      if (convs.length === 0) return [];
      // Pull messages for every recent thread, then merge chronologically.
      const threads = await Promise.all(
        convs
          .filter((c) => c?.id)
          .map((c) =>
            conversationsApi
              .get(String(c.id))
              .then((d) => d.messages || [])
              .catch(() => [] as ChatMessage[])
          )
      );
      const all = threads.flat();
      all.sort((a, b) => {
        const ta = a.created_at ? new Date(a.created_at).getTime() : 0;
        const tb = b.created_at ? new Date(b.created_at).getTime() : 0;
        return ta - tb;
      });
      return all;
    },
  });

  if (!open) return null;

  const messages = query.data ?? [];

  return (
    <div
      dir="rtl"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
      onClick={onClose}
    >
      <div
        className="bg-gray-900 border border-gray-700 rounded-xl w-full max-w-lg max-h-[85vh] flex flex-col shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-gray-700">
          <div>
            <div className="text-white font-semibold">
              💬 שיחה של {agentName} עם {clientName}
            </div>
            <div className="text-xs text-gray-400">היסטוריית ההודעות (לקריאה בלבד)</div>
          </div>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-white p-1 rounded transition"
            aria-label="סגור"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto p-4 space-y-3 bg-gray-950">
          {query.isLoading ? (
            <div className="text-gray-400 text-center py-8">טוען שיחה…</div>
          ) : query.error ? (
            <div className="text-red-400 text-center py-8">
              שגיאה בטעינת השיחה: {String((query.error as Error).message)}
            </div>
          ) : messages.length === 0 ? (
            <div className="text-gray-400 text-center py-8">
              אין עדיין הודעות בשיחה הזו.
            </div>
          ) : (
            messages.map((m, i) => {
              const outbound = m.direction === "outbound";
              return (
                <div
                  key={m.id || i}
                  className={`flex ${outbound ? "justify-start" : "justify-end"}`}
                >
                  <div
                    className={`max-w-[80%] rounded-2xl px-3 py-2 text-sm whitespace-pre-wrap break-words ${
                      outbound
                        ? "bg-teal-700 text-white rounded-tr-sm"
                        : "bg-gray-700 text-gray-100 rounded-tl-sm"
                    }`}
                  >
                    <div className="text-[10px] opacity-70 mb-0.5">
                      {outbound ? agentName : clientName} · {formatTime(m.created_at)}
                    </div>
                    {m.message_type === "file" || m.message_type === "image" ? (
                      <a
                        href={m.file_url || "#"}
                        target="_blank"
                        rel="noreferrer"
                        className="underline"
                      >
                        📎 {m.text || "קובץ מצורף"}
                      </a>
                    ) : (
                      m.text || <span className="opacity-60">—</span>
                    )}
                  </div>
                </div>
              );
            })
          )}
        </div>
      </div>
    </div>
  );
}

export default ClientConversationModal;

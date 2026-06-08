/**
 * Pandi Client Conversations — REAL DATA ONLY.
 *
 * Pandi is the WhatsApp intake agent that talks to clients. This page
 * lists every real Pandi conversation in the system (from /admin/pandi/clients).
 *
 * Everything previously hardcoded (MOCK_REQUESTS, sample WhatsApp threads,
 * fake candidate offers) has been removed — the user explicitly asked for
 * "only real data from the system DB". When there are no real conversations
 * yet, an empty state shows the opening greeting Pandi sends to first-time
 * contacts.
 */

import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { MessageCircle } from "lucide-react";
import { fetchPandiClients, type PandiClient } from "@/api/pandi";

const PANDI_OPENING_GREETING =
  "היי, אני פנדי סוכנת גיוס בינה מלאכותית של פנדה-טק. " +
  "אני כאן כדי לעזור לך למצוא מועמד מתאים לתפקיד.";

function formatDate(iso?: string): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString("he-IL", {
      day: "2-digit",
      month: "2-digit",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

const INTAKE_STATUS_LABEL: Record<string, { label: string; cls: string }> = {
  not_started: { label: "טרם החל", cls: "bg-gray-700 text-gray-200" },
  in_progress: { label: "בתהליך", cls: "bg-yellow-900 text-yellow-200" },
  completed: { label: "הושלם", cls: "bg-green-900 text-green-200" },
};

export const PandiClientRequestPage = () => {
  const navigate = useNavigate();
  const [filter, setFilter] = useState<"all" | "active" | "inactive">("all");

  const clientsQuery = useQuery({
    queryKey: ["pandi-clients", filter],
    queryFn: () =>
      fetchPandiClients(
        filter === "all" ? undefined : filter === "active",
        100,
        0
      ),
    refetchInterval: 20000,
  });

  const clients = clientsQuery.data ?? [];

  return (
    <div dir="rtl" className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-3xl font-bold text-white flex items-center gap-2">
            <span>🐼</span> פנדי — שיחות עם לקוחות
          </h1>
          <p className="text-gray-400 mt-1">
            פנדי היא סוכנת WhatsApp חכמה שמטפלת בבקשות לקוחות לאיתור מועמדים. כל השיחות
            המוצגות כאן הן אמיתיות, מהדאטה-בייס של המערכת.
          </p>
        </div>
        <button
          onClick={() => navigate("/recruiting/pandi/conversations")}
          className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-teal-600 text-white hover:bg-teal-700 transition shrink-0"
        >
          <MessageCircle className="w-4 h-4" /> שיחות
        </button>
      </div>

      {/* Opening greeting card */}
      <div className="bg-gradient-to-l from-cyan-900/40 to-cyan-800/20 border border-cyan-700 rounded-lg p-4">
        <div className="text-xs text-cyan-300 mb-1">
          💬 הודעת פתיחה — פנדי שולחת אוטומטית למי שיוצר איתה קשר ראשוני:
        </div>
        <div className="text-white text-sm leading-relaxed">
          {PANDI_OPENING_GREETING}
        </div>
      </div>

      {/* Filter strip */}
      <div className="flex gap-2 items-center">
        <span className="text-sm text-gray-400">סינון:</span>
        {(["all", "active", "inactive"] as const).map((f) => (
          <button
            key={f}
            onClick={() => setFilter(f)}
            className={`px-3 py-1.5 text-sm rounded transition ${
              filter === f
                ? "bg-indigo-600 text-white"
                : "bg-gray-800 text-gray-300 hover:bg-gray-700"
            }`}
          >
            {f === "all" ? "הכל" : f === "active" ? "פעילים" : "לא פעילים"}
          </button>
        ))}
        <div className="text-xs text-gray-500 mr-auto">
          סה״כ {clients.length} לקוחות{clientsQuery.isFetching ? " (טוען…)" : ""}
        </div>
      </div>

      {/* Body */}
      {clientsQuery.isLoading ? (
        <div className="text-gray-400 text-center py-8">טוען נתוני אמת מבסיס הנתונים…</div>
      ) : clientsQuery.error ? (
        <div className="text-red-400 text-center py-8">
          שגיאה בטעינת לקוחות: {String((clientsQuery.error as Error).message)}
        </div>
      ) : clients.length === 0 ? (
        <EmptyState />
      ) : (
        <ClientsTable clients={clients} />
      )}
    </div>
  );
};

function ClientsTable({ clients }: { clients: PandiClient[] }) {
  return (
    <div className="bg-gray-800 rounded-lg border border-gray-700 overflow-hidden">
      <table className="w-full text-right text-sm">
        <thead className="bg-gray-700 border-b border-gray-600 text-gray-200">
          <tr>
            <th className="px-4 py-3 font-semibold">איש קשר</th>
            <th className="px-4 py-3 font-semibold">ארגון</th>
            <th className="px-4 py-3 font-semibold">טלפון</th>
            <th className="px-4 py-3 font-semibold">סטטוס Intake</th>
            <th className="px-4 py-3 font-semibold">פעיל?</th>
            <th className="px-4 py-3 font-semibold">הודעה ראשונה</th>
            <th className="px-4 py-3 font-semibold">פעילות אחרונה</th>
          </tr>
        </thead>
        <tbody>
          {clients.map((c) => {
            const status =
              INTAKE_STATUS_LABEL[c.intake_status] ||
              { label: c.intake_status || "לא ידוע", cls: "bg-gray-700 text-gray-200" };
            return (
              <tr key={c.id} className="border-b border-gray-700 hover:bg-gray-750">
                <td className="px-4 py-3 text-white font-semibold">
                  {c.contact_name || <span className="text-gray-500">—</span>}
                </td>
                <td className="px-4 py-3 text-gray-300">
                  {c.organization_name || <span className="text-gray-500">—</span>}
                </td>
                <td className="px-4 py-3 text-gray-300" dir="ltr">
                  {c.phone || "—"}
                </td>
                <td className="px-4 py-3">
                  <span className={`px-2 py-1 rounded text-xs font-semibold ${status.cls}`}>
                    {status.label}
                  </span>
                </td>
                <td className="px-4 py-3">
                  {c.is_active ? (
                    <span className="text-green-400">●</span>
                  ) : (
                    <span className="text-gray-600">○</span>
                  )}
                </td>
                <td className="px-4 py-3 text-gray-400 text-xs">{formatDate(c.first_message_at)}</td>
                <td className="px-4 py-3 text-gray-400 text-xs">{formatDate(c.last_message_at)}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function EmptyState() {
  return (
    <div className="bg-gray-800 border border-gray-700 rounded-lg p-8 text-center text-gray-300">
      <p className="text-lg mb-2">🐼 אין כרגע שיחות פעילות עם לקוחות</p>
      <p className="text-sm text-gray-400 max-w-xl mx-auto">
        לקוחות יופיעו כאן ברגע שיתחילו לתכתב עם פנדי דרך WhatsApp. ברגע שלקוח חדש יוצר
        קשר, פנדי שולחת לו את הודעת הפתיחה שלמעלה ומתחילה את תהליך ה-intake.
      </p>
    </div>
  );
}

export default PandiClientRequestPage;

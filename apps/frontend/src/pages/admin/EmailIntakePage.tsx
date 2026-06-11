import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { supabase } from "@/lib/supabase";
import { env } from "@/lib/env";

export function EmailIntakePage() {
  const { data: status } = useQuery({
    queryKey: ["email-status"],
    queryFn: () => fetch(`${env.API_BASE_URL}/admin/email/status`).then(r => r.json()),
    refetchInterval: 5000,
  });

  const PAGE_SIZE = 50;
  const [page, setPage] = useState(0);

  const { data: logs } = useQuery({
    queryKey: ["email-logs", page],
    queryFn: () =>
      fetch(
        `${env.API_BASE_URL}/admin/email/logs?limit=${PAGE_SIZE}&offset=${page * PAGE_SIZE}`
      ).then(r => r.json()),
    refetchInterval: 10000,
  });

  // Historical backfill progress (only shown when a backfill is active).
  const { data: backfill } = useQuery({
    queryKey: ["email-backfill"],
    queryFn: () =>
      fetch(`${env.API_BASE_URL}/admin/email/backfill-progress`).then(r => r.json()),
    refetchInterval: 10000,
  });

  const [liveEvents, setLiveEvents] = useState([]);

  useEffect(() => {
    const channel = supabase
      .channel("email-intake")
      .on(
        "postgres_changes",
        { event: "INSERT", schema: "public", table: "email_intake_log" },
        (payload) => {
          setLiveEvents((prev) => [payload.new, ...prev].slice(0, 5));
        }
      )
      .subscribe();

    return () => {
      channel.unsubscribe();
    };
  }, []);

  const statusColor = {
    success: "bg-green-900/30 text-green-300 border-green-700",
    error: "bg-red-900/30 text-red-300 border-red-700",
    skipped_no_cv: "bg-gray-800 text-gray-400 border-gray-700",
  };

  const statusIcon = {
    success: "✓",
    error: "✗",
    skipped_no_cv: "⊙",
  };

  return (
    <div className="min-h-screen bg-gray-900 p-8" dir="rtl">
      <div className="max-w-7xl mx-auto">
        {/* Header */}
        <div className="mb-8">
          <div className="bg-gradient-to-r from-indigo-900 via-gray-800 to-purple-900 rounded-lg p-6 border border-gray-700">
            <h1 className="text-4xl font-bold text-white mb-2">קליטת דוא"ל</h1>
            <p className="text-indigo-300">ניטור של דוא"לים נכנסים וחילוץ קורות חיים</p>
          </div>
        </div>

        {/* Status Cards */}
        <div className="grid grid-cols-4 gap-4 mb-8">
          <div className="bg-gray-800 p-6 rounded-lg border border-gray-700 hover:border-gray-600 transition-colors">
            <div className="text-xs text-gray-400 font-semibold mb-3 uppercase tracking-wide">סנכרון אחרון</div>
            <div className="text-3xl font-bold text-white">
              {status?.last_run_at ? new Date(status.last_run_at).toLocaleTimeString("he-IL") : "—"}
            </div>
          </div>
          <div className="bg-gray-800 p-6 rounded-lg border border-gray-700 hover:border-gray-600 transition-colors">
            <div className="text-xs text-gray-400 font-semibold mb-3 uppercase tracking-wide">דוא"לים היום</div>
            <div className="text-3xl font-bold text-indigo-300">{status?.emails_processed_today || 0}</div>
          </div>
          <div className="bg-gray-800 p-6 rounded-lg border border-gray-700 hover:border-gray-600 transition-colors">
            <div className="text-xs text-gray-400 font-semibold mb-3 uppercase tracking-wide">קורות חיים היום</div>
            <div className="text-3xl font-bold text-green-400">{status?.cv_files_extracted_today || 0}</div>
          </div>
          <div className="bg-gray-800 p-6 rounded-lg border border-gray-700 hover:border-gray-600 transition-colors">
            <div className="text-xs text-gray-400 font-semibold mb-3 uppercase tracking-wide">סה"כ קורות חיים</div>
            <div className="text-3xl font-bold text-purple-400">{status?.cv_files_extracted_total || 0}</div>
          </div>
        </div>

        {/* Historical Backfill Progress - shown only when backfill is active */}
        {backfill?.backfill_enabled && (
          <div className="bg-gradient-to-r from-amber-900/30 to-orange-900/30 rounded-lg border border-amber-700 p-6 mb-8">
            <div className="flex items-start justify-between mb-3">
              <div>
                <h2 className="text-xl font-bold text-amber-200 mb-1">
                  📥 סריקת היסטוריה פעילה
                </h2>
                <p className="text-xs text-amber-200/80">
                  המערכת סורקת אוטומטית את המיילים ההיסטוריים מתאריך{" "}
                  <span className="font-mono font-bold">
                    {backfill.backfill_start_date
                      ? new Date(backfill.backfill_start_date).toLocaleDateString("he-IL")
                      : "—"}
                  </span>
                  . תהליך זה ימשיך עד שכל המיילים יעובדו.
                </p>
              </div>
              <div className="text-right">
                <div className="text-3xl font-bold text-amber-200">
                  {backfill.progress_percent != null ? `${backfill.progress_percent}%` : "—"}
                </div>
                <div className="text-xs text-amber-200/60">
                  {backfill.days_remaining != null && backfill.days_remaining > 0
                    ? `נותרו ~${backfill.days_remaining} ימי מיילים`
                    : "התקדמות"}
                </div>
              </div>
            </div>

            {/* Progress bar */}
            <div className="w-full bg-gray-900/50 rounded-full h-3 overflow-hidden mb-3">
              <div
                className="bg-gradient-to-r from-amber-500 to-orange-400 h-full transition-all duration-500"
                style={{ width: `${backfill.progress_percent ?? 0}%` }}
              />
            </div>

            <div className="flex items-center justify-between text-xs text-amber-200/70">
              <div>
                <span className="font-mono">
                  עיבד עד:{" "}
                  {backfill.last_processed_at
                    ? new Date(backfill.last_processed_at).toLocaleString("he-IL")
                    : "טרם התחיל"}
                </span>
              </div>
              <button
                onClick={async () => {
                  if (
                    confirm(
                      "האם לבטל את סריקת ההיסטוריה? סריקת מיילים חדשים תמשיך כרגיל."
                    )
                  ) {
                    await fetch(`${env.API_BASE_URL}/admin/email/cancel-backfill`, {
                      method: "POST",
                    });
                  }
                }}
                className="text-xs px-3 py-1 bg-amber-900/50 hover:bg-amber-900/70 border border-amber-700 rounded text-amber-200 font-semibold"
              >
                ✕ בטל סריקה היסטורית
              </button>
            </div>
          </div>
        )}

        {/* Start Backfill — only shown when no backfill is currently active */}
        {backfill && !backfill.backfill_enabled && (
          <div className="bg-gray-800 rounded-lg border border-gray-700 p-4 mb-8 flex items-center justify-between">
            <div>
              <h3 className="text-sm font-bold text-white">סריקת היסטוריה</h3>
              <p className="text-xs text-gray-400">
                כעת מטופלים רק מיילים חדשים. להתחיל גם סריקה של מיילים ישנים?
              </p>
            </div>
            <button
              onClick={async () => {
                const dateStr = prompt(
                  "מאיזה תאריך להתחיל סריקה היסטורית? (פורמט: YYYY-MM-DD)",
                  "2021-05-01"
                );
                if (!dateStr) return;
                const r = await fetch(`${env.API_BASE_URL}/admin/email/start-backfill`, {
                  method: "POST",
                  headers: { "Content-Type": "application/json" },
                  body: JSON.stringify({ start_date: dateStr }),
                });
                const data = await r.json();
                if (r.ok) {
                  alert(`✓ סריקה התחילה מ-${dateStr}`);
                } else {
                  alert(`✗ ${data.detail}`);
                }
              }}
              className="px-4 py-2 bg-amber-700 hover:bg-amber-600 text-white text-sm font-semibold rounded-lg"
            >
              📥 התחל סריקת היסטוריה
            </button>
          </div>
        )}

        {/* Live Events */}
        <div className="bg-gray-800 rounded-lg border border-gray-700 p-6 mb-8">
          <h2 className="text-xl font-semibold text-white mb-4">עיבוד דוא"לים בזמן אמת</h2>
          <div className="space-y-2 max-h-96 overflow-y-auto">
            {liveEvents.length === 0 ? (
              <div className="text-sm text-gray-400 py-8 text-center">מחכה לדוא"לים...</div>
            ) : (
              liveEvents.map((event) => (
                <div
                  key={event.id}
                  className={`flex items-center p-4 rounded-lg text-sm gap-4 border transition-all ${
                    statusColor[event.status as keyof typeof statusColor] || statusColor.skipped_no_cv
                  }`}
                >
                  <span className="font-bold text-lg flex-shrink-0">
                    {statusIcon[event.status as keyof typeof statusIcon] || "?"}
                  </span>
                  <span className="text-gray-400 whitespace-nowrap text-xs flex-shrink-0">
                    {event.email_received_at
                      ? new Date(event.email_received_at).toLocaleTimeString("he-IL")
                      : "—"}
                  </span>
                  <div className="flex-1 min-w-0">
                    <div className="font-mono text-xs text-gray-300 truncate">
                      {event.email_from}
                    </div>
                    <div className="text-xs text-gray-400 truncate mt-1">
                      {event.email_subject}
                    </div>
                  </div>
                  {event.cv_files_extracted > 0 && (
                    <span className="text-xs px-3 py-1 bg-gray-700 text-indigo-300 rounded-full font-semibold flex-shrink-0">
                      {event.cv_files_extracted} CVs
                    </span>
                  )}
                </div>
              ))
            )}
          </div>
        </div>

        {/* History Table */}
        <div className="bg-gray-800 rounded-lg border border-gray-700 p-6 overflow-hidden">
          <h2 className="text-xl font-semibold text-white mb-4">היסטוריית קליטה</h2>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-700 bg-gray-900/50">
                  <th className="text-right py-4 px-4 text-gray-300 font-semibold">תאריך</th>
                  <th className="text-right py-4 px-4 text-gray-300 font-semibold">מ</th>
                  <th className="text-right py-4 px-4 text-gray-300 font-semibold">נושא</th>
                  <th className="text-right py-4 px-4 text-gray-300 font-semibold">סטטוס</th>
                  <th className="text-right py-4 px-4 text-gray-300 font-semibold">קורות חיים</th>
                </tr>
              </thead>
              <tbody>
                {logs?.data?.length === 0 ? (
                  <tr>
                    <td colSpan={5} className="text-center py-8 text-gray-400 text-sm">
                      עדיין לא נקלטו דוא"לים
                    </td>
                  </tr>
                ) : (
                  logs?.data?.map((log) => (
                    <tr key={log.id} className="border-b border-gray-700 hover:bg-gray-700/30 transition-colors">
                      <td className="py-4 px-4 text-xs text-gray-400">
                        {log.email_received_at
                          ? new Date(log.email_received_at).toLocaleString("he-IL")
                          : "—"}
                      </td>
                      <td className="py-4 px-4 font-mono text-xs text-gray-300">{log.email_from || "—"}</td>
                      <td className="py-4 px-4 truncate text-gray-300 max-w-xs">{log.email_subject || "—"}</td>
                      <td className="py-4 px-4">
                        <span className={`inline-flex items-center px-3 py-1 rounded-full text-xs font-semibold border ${
                          log.status === "success" ? "bg-green-900/30 text-green-300 border-green-700" :
                          log.status === "partial" ? "bg-yellow-900/30 text-yellow-300 border-yellow-700" :
                          log.status === "failed" ? "bg-red-900/30 text-red-300 border-red-700" :
                          log.status === "skipped_no_cv" ? "bg-gray-700/30 text-gray-300 border-gray-600" :
                          log.status === "processing" ? "bg-blue-900/30 text-blue-300 border-blue-700" :
                          "bg-gray-700/30 text-gray-300 border-gray-600"
                        }`}>
                          {log.status === "success" && "✓ בהצלחה"}
                          {log.status === "partial" && "◐ חלקי"}
                          {log.status === "failed" && "✗ כשל"}
                          {log.status === "skipped_no_cv" && "⊙ ללא CV"}
                          {log.status === "processing" && "⟳ מעובד"}
                        </span>
                      </td>
                      <td className="py-4 px-4 text-xs font-semibold text-indigo-300">{log.cv_files_extracted || 0}</td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>

          {/* Pagination */}
          <div className="flex items-center justify-between mt-4 pt-4 border-t border-gray-700">
            <button
              onClick={() => setPage((p) => Math.max(0, p - 1))}
              disabled={page === 0}
              className="px-4 py-2 text-sm font-semibold rounded-lg border border-gray-600 text-gray-200 hover:bg-gray-700 disabled:opacity-40 disabled:cursor-not-allowed"
            >
              → הקודם
            </button>
            <span className="text-xs text-gray-400">
              עמוד {page + 1}
              {logs?.data?.length ? ` · שורות ${page * PAGE_SIZE + 1}–${page * PAGE_SIZE + logs.data.length}` : ""}
            </span>
            <button
              onClick={() => setPage((p) => p + 1)}
              disabled={(logs?.data?.length ?? 0) < PAGE_SIZE}
              className="px-4 py-2 text-sm font-semibold rounded-lg border border-gray-600 text-gray-200 hover:bg-gray-700 disabled:opacity-40 disabled:cursor-not-allowed"
            >
              הבא ←
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

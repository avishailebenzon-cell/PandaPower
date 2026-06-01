import React from "react";
import { useQuery } from "@tanstack/react-query";

// CRITICAL: Get API base URL from environment - MUST use VITE_API_URL (not VITE_API_BASE)
const API_BASE = import.meta.env.VITE_API_URL || "";

interface TaskHeartbeat {
  task_name: string;
  label: string;
  last_run_at: string | null;
  last_status: string | null;
  consecutive_failures: number;
  expected_interval_seconds: number | null;
  seconds_since_last_run: number | null;
  is_stalled: boolean;
  last_error: string | null;
}

interface HeartbeatResponse {
  timestamp: string;
  overall_status: "healthy" | "degraded" | "error";
  summary: string;
  tasks: TaskHeartbeat[];
}

const fetchHeartbeat = async (): Promise<HeartbeatResponse> => {
  const response = await fetch(`${API_BASE}/admin/system/heartbeat`);
  if (!response.ok) throw new Error("Failed to fetch system heartbeat");
  return response.json();
};

function formatAgo(seconds: number | null): string {
  if (seconds === null || seconds === undefined) return "מעולם לא רץ";
  if (seconds < 60) return `לפני ${Math.round(seconds)} שניות`;
  if (seconds < 3600) return `לפני ${Math.round(seconds / 60)} דקות`;
  if (seconds < 86400) return `לפני ${(seconds / 3600).toFixed(1)} שעות`;
  return `לפני ${(seconds / 86400).toFixed(1)} ימים`;
}

function formatInterval(seconds: number | null): string {
  if (!seconds) return "-";
  if (seconds < 60) return `${seconds}ש'`;
  if (seconds < 3600) return `${Math.round(seconds / 60)} דק'`;
  return `${(seconds / 3600).toFixed(0)} שע'`;
}

function statusBadge(task: TaskHeartbeat): { text: string; cls: string } {
  if (task.is_stalled) return { text: "תקוע", cls: "bg-red-100 text-red-800 border-red-300" };
  if (task.consecutive_failures >= 3)
    return { text: "כשלים חוזרים", cls: "bg-red-100 text-red-800 border-red-300" };
  if (task.last_status === "failed" || task.last_status === "crashed")
    return { text: "כשל אחרון", cls: "bg-amber-100 text-amber-800 border-amber-300" };
  if (task.last_status === "skipped")
    return { text: "פעיל (דילג)", cls: "bg-slate-100 text-slate-700 border-slate-300" };
  return { text: "פעיל", cls: "bg-green-100 text-green-800 border-green-300" };
}

const overallStyles: Record<string, string> = {
  healthy: "bg-green-50 border-green-300 text-green-900",
  degraded: "bg-amber-50 border-amber-300 text-amber-900",
  error: "bg-red-50 border-red-300 text-red-900",
};

export const SystemHealthPage: React.FC = () => {
  const { data, isLoading, isError, dataUpdatedAt } = useQuery({
    queryKey: ["system-heartbeat"],
    queryFn: fetchHeartbeat,
    refetchInterval: 15000, // auto-refresh every 15s
  });

  return (
    <div className="p-6 max-w-5xl mx-auto" dir="rtl">
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-2xl font-bold text-slate-800">🩺 ניטור מערכת — תהליכים אוטומטיים</h1>
        <span className="text-xs text-slate-400">
          {dataUpdatedAt ? `עודכן ${new Date(dataUpdatedAt).toLocaleTimeString("he-IL")}` : ""}
        </span>
      </div>
      <p className="text-sm text-slate-500 mb-6">
        כל התהליכים רצים אוטומטית בתוך שירות ה-API (תמיד פעיל). תהליך מסומן כ"תקוע" אם לא רץ ביותר
        מפי-2 מהמרווח הצפוי שלו. דף זה מתרענן אוטומטית כל 15 שניות.
      </p>

      {isLoading && <div className="text-slate-500">טוען נתוני בריאות...</div>}
      {isError && (
        <div className="bg-red-50 border border-red-300 text-red-800 rounded-lg p-4">
          לא ניתן לטעון את נתוני הבריאות. ודא שה-backend פעיל.
        </div>
      )}

      {data && (
        <>
          <div className={`rounded-lg border p-4 mb-6 ${overallStyles[data.overall_status]}`}>
            <div className="font-semibold text-lg">
              {data.overall_status === "healthy"
                ? "✅ כל המערכת פעילה"
                : data.overall_status === "degraded"
                ? "⚠️ המערכת פעילה חלקית"
                : "🔴 בעיה במערכת"}
            </div>
            <div className="text-sm mt-1">{data.summary}</div>
          </div>

          <div className="overflow-x-auto bg-white rounded-lg border border-slate-200 shadow-sm">
            <table className="w-full text-sm">
              <thead className="bg-slate-50 text-slate-600">
                <tr>
                  <th className="text-right px-4 py-3 font-medium">תהליך</th>
                  <th className="text-right px-4 py-3 font-medium">סטטוס</th>
                  <th className="text-right px-4 py-3 font-medium">רץ לאחרונה</th>
                  <th className="text-right px-4 py-3 font-medium">מרווח צפוי</th>
                  <th className="text-right px-4 py-3 font-medium">כשלים רצופים</th>
                </tr>
              </thead>
              <tbody>
                {data.tasks.map((task) => {
                  const badge = statusBadge(task);
                  return (
                    <tr key={task.task_name} className="border-t border-slate-100 hover:bg-slate-50">
                      <td className="px-4 py-3">
                        <div className="font-medium text-slate-800">{task.label}</div>
                        <div className="text-xs text-slate-400">{task.task_name}</div>
                        {task.last_error && (
                          <div className="text-xs text-red-500 mt-1 max-w-md truncate" title={task.last_error}>
                            {task.last_error}
                          </div>
                        )}
                      </td>
                      <td className="px-4 py-3">
                        <span className={`inline-block px-2 py-1 rounded-full text-xs border ${badge.cls}`}>
                          {badge.text}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-slate-600">{formatAgo(task.seconds_since_last_run)}</td>
                      <td className="px-4 py-3 text-slate-600">{formatInterval(task.expected_interval_seconds)}</td>
                      <td className="px-4 py-3">
                        <span className={task.consecutive_failures > 0 ? "text-red-600 font-semibold" : "text-slate-400"}>
                          {task.consecutive_failures}
                        </span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
};

export default SystemHealthPage;

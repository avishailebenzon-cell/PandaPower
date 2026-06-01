import React, { useState } from "react";
import { useQuery } from "@tanstack/react-query";

// CRITICAL: Get API base URL from environment - MUST use VITE_API_URL (not VITE_API_BASE)
const API_BASE = import.meta.env.VITE_API_URL || "";

interface ReingestStatus {
  auto_enabled: boolean;
  partial_remaining: number;
  failed_remaining: number;
  recoverable_total: number;
  skipped_duplicate_person: number;
  cv_files_total: number;
  candidates_total: number;
}

const fetchStatus = async (): Promise<ReingestStatus> => {
  const res = await fetch(`${API_BASE}/admin/email/reingest-status`);
  if (!res.ok) throw new Error("Failed to fetch reingest status");
  return res.json();
};

export const ReingestPage: React.FC = () => {
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);

  const { data, refetch } = useQuery({
    queryKey: ["reingest-status"],
    queryFn: fetchStatus,
    refetchInterval: 10000,
  });

  const runBatch = async () => {
    setBusy(true); setMsg(null);
    try {
      const res = await fetch(`${API_BASE}/admin/email/reingest-missed`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ limit: 500 }),
      });
      const d = await res.json();
      if (!res.ok) throw new Error(d.detail || "failed");
      setMsg({ ok: true, text: "אצוות שחזור (500) רצה ברקע. עקוב אחרי המספרים שמתעדכנים למטה." });
      refetch();
    } catch (e: any) { setMsg({ ok: false, text: e.message }); }
    finally { setBusy(false); }
  };

  const toggleAuto = async (enabled: boolean) => {
    setBusy(true); setMsg(null);
    try {
      const res = await fetch(`${API_BASE}/admin/email/reingest-auto`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ enabled }),
      });
      const d = await res.json();
      if (!res.ok) throw new Error(d.detail || "failed");
      setMsg({ ok: true, text: enabled ? "שחזור אוטומטי הופעל — המערכת תשחזר את כל הבקלוג בהדרגה." : "שחזור אוטומטי כובה." });
      refetch();
    } catch (e: any) { setMsg({ ok: false, text: e.message }); }
    finally { setBusy(false); }
  };

  const Stat: React.FC<{ label: string; value: number | undefined; hl?: boolean }> = ({ label, value, hl }) => (
    <div className={`rounded-lg p-4 border ${hl ? "bg-amber-50 border-amber-300" : "bg-white border-slate-200"}`}>
      <div className="text-xs text-slate-500 mb-1">{label}</div>
      <div className={`text-2xl font-bold ${hl ? "text-amber-700" : "text-slate-800"}`}>
        {value != null ? value.toLocaleString() : "—"}
      </div>
    </div>
  );

  return (
    <div className="p-6 max-w-3xl mx-auto" dir="rtl">
      <h1 className="text-2xl font-bold text-slate-800 mb-2">♻️ שחזור קורות חיים אבודים</h1>
      <p className="text-sm text-slate-500 mb-6">
        קורות חיים רבים נשלחו במיילים (Jobnet/Drushim/AllJobs) אך לא נקלטו עקב שגיאות בעבר.
        כל המיילים עדיין קיימים ב-Outlook — כלי זה מושך אותם מחדש וקולט את הקבצים. שחזור הקבצים עצמו
        אינו עולה קרדיטי ConvertAPI.
      </p>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
        <Stat label="ניתנים לשחזור" value={data?.recoverable_total} hl />
        <Stat label="קבצי CV במערכת" value={data?.cv_files_total} />
        <Stat label="מועמדים" value={data?.candidates_total} />
        <Stat label="כפילויות שדולגו" value={data?.skipped_duplicate_person} />
      </div>
      <div className="text-xs text-slate-400 mb-6">
        partial: {data?.partial_remaining?.toLocaleString() ?? "—"} · failed: {data?.failed_remaining?.toLocaleString() ?? "—"}
        {" · "}שחזור אוטומטי: <b className={data?.auto_enabled ? "text-green-600" : "text-slate-500"}>{data?.auto_enabled ? "פעיל" : "כבוי"}</b>
        {" · "}סדר: מהחדש לישן · דילוג על אותו אדם (אימייל/טלפון)
      </div>

      <div className="bg-white border border-slate-200 rounded-lg p-4 shadow-sm space-y-3">
        <div className="font-semibold text-slate-700">פעולות</div>
        <div className="flex flex-wrap gap-3">
          <button onClick={runBatch} disabled={busy}
            className="bg-cyan-600 text-white px-4 py-2 rounded text-sm disabled:opacity-50 hover:bg-cyan-700">
            שחזר אצווה (500) — אימות
          </button>
          {data?.auto_enabled ? (
            <button onClick={() => toggleAuto(false)} disabled={busy}
              className="bg-red-100 text-red-700 px-4 py-2 rounded text-sm disabled:opacity-50 hover:bg-red-200 border border-red-300">
              עצור שחזור אוטומטי
            </button>
          ) : (
            <button onClick={() => toggleAuto(true)} disabled={busy}
              className="bg-amber-500 text-white px-4 py-2 rounded text-sm disabled:opacity-50 hover:bg-amber-600">
              הפעל שחזור אוטומטי מלא
            </button>
          )}
        </div>
        <p className="text-xs text-slate-400">
          מומלץ: הרץ אצווה אחת לאימות, ודא שהמספרים עולים, ואז הפעל שחזור אוטומטי לכל הבקלוג.
          המעקב המלא זמין גם ב-🩺 ניטור מערכת (שלב "שחזור קורות חיים אבודים").
        </p>
      </div>

      {msg && (
        <div className={`mt-4 rounded-lg p-3 text-sm border ${
          msg.ok ? "bg-green-50 text-green-800 border-green-300" : "bg-red-50 text-red-800 border-red-300"
        }`}>{msg.text}</div>
      )}
    </div>
  );
};

export default ReingestPage;

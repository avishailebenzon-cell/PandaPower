import React, { useState } from "react";
import { useQuery } from "@tanstack/react-query";

// CRITICAL: Get API base URL from environment - MUST use VITE_API_URL (not VITE_API_BASE)
const API_BASE = import.meta.env.VITE_API_URL || "";

interface ConvertApiStatus {
  enabled: boolean;
  mode: string | null;
  ocr_languages: string | null;
  has_secret: boolean;
  credits_remaining: number | null;
}

const fetchStatus = async (): Promise<ConvertApiStatus> => {
  const res = await fetch(`${API_BASE}/admin/convertapi/status`);
  if (!res.ok) throw new Error("Failed to fetch ConvertAPI status");
  return res.json();
};

export const ConvertApiPage: React.FC = () => {
  const [secret, setSecret] = useState("");
  const [mode, setMode] = useState("always");
  const [ocr, setOcr] = useState("en,he");
  const [limit, setLimit] = useState(500);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);

  const { data: status, refetch } = useQuery({
    queryKey: ["convertapi-status"],
    queryFn: fetchStatus,
    refetchInterval: 15000,
  });

  const post = async (path: string, body: any) => {
    const res = await fetch(`${API_BASE}/admin/convertapi/${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Request failed");
    return data;
  };

  const save = async () => {
    setBusy(true); setMsg(null);
    try {
      await post("configure", { secret: secret.trim() || undefined, mode, ocr_languages: ocr });
      setMsg({ ok: true, text: "ההגדרות נשמרו ✓" });
      setSecret("");
      refetch();
    } catch (e: any) {
      setMsg({ ok: false, text: e.message });
    } finally { setBusy(false); }
  };

  const test = async () => {
    setBusy(true); setMsg(null);
    try {
      const d = await post("test", {});
      setMsg({ ok: true, text: `החיבור תקין ✓ (${d.account || "valid"})` });
    } catch (e: any) {
      setMsg({ ok: false, text: e.message });
    } finally { setBusy(false); }
  };

  const reprocess = async () => {
    setBusy(true); setMsg(null);
    try {
      const d = await post("reprocess-failed", { limit });
      setMsg({ ok: true, text: `${d.reset} קבצים סומנו לעיבוד מחדש. ${d.note || ""}` });
    } catch (e: any) {
      setMsg({ ok: false, text: e.message });
    } finally { setBusy(false); }
  };

  const Badge: React.FC<{ on: boolean | null; label: string }> = ({ on, label }) => (
    <span className={`inline-block px-2 py-1 rounded-full text-xs border ${
      on ? "bg-green-100 text-green-800 border-green-300" : "bg-slate-100 text-slate-600 border-slate-300"
    }`}>{on ? "✓" : "✗"} {label}</span>
  );

  return (
    <div className="p-6 max-w-2xl mx-auto" dir="rtl">
      <h1 className="text-2xl font-bold text-slate-800 mb-2">📄 סריקת קורות חיים (ConvertAPI)</h1>
      <p className="text-sm text-slate-500 mb-6">
        חילוץ טקסט מקורות חיים דרך ConvertAPI — כולל OCR לקבצים סרוקים, תמונות (JPG/PNG), ו-DOC ישן,
        שהמנגנון המקומי לא הצליח לקרוא.
      </p>

      <div className="bg-white border border-slate-200 rounded-lg p-4 mb-6 shadow-sm">
        <div className="font-semibold text-slate-700 mb-3">סטטוס</div>
        <div className="flex flex-wrap gap-2">
          <Badge on={status?.has_secret ?? null} label="Secret מוגדר" />
          <Badge on={status?.enabled ?? null} label="פעיל" />
        </div>
        <div className="text-sm text-slate-500 mt-3">
          מצב: <b>{status?.mode === "always" ? "תמיד ConvertAPI" : status?.mode || "—"}</b>
          {" · "}שפות OCR: {status?.ocr_languages || "—"}
          {status?.credits_remaining != null && <> {" · "}קרדיט שנותר: {status.credits_remaining}</>}
        </div>
      </div>

      <div className="bg-white border border-slate-200 rounded-lg p-4 mb-6 shadow-sm space-y-3">
        <div className="font-semibold text-slate-700">הגדרה</div>
        <div>
          <label className="block text-sm text-slate-600 mb-1">ConvertAPI Secret</label>
          <input type="password" value={secret} onChange={(e) => setSecret(e.target.value)}
            placeholder={status?.has_secret ? "•••••• (כבר מוגדר — הזן כדי להחליף)" : "הדבק את ה-Secret"}
            className="w-full border border-slate-300 rounded px-3 py-2 text-sm" dir="ltr" />
        </div>
        <div className="flex gap-3">
          <div className="flex-1">
            <label className="block text-sm text-slate-600 mb-1">מצב</label>
            <select value={mode} onChange={(e) => setMode(e.target.value)}
              className="w-full border border-slate-300 rounded px-3 py-2 text-sm">
              <option value="always">תמיד ConvertAPI (איכות מקסימלית)</option>
              <option value="fallback">גיבוי בלבד (חוסך קרדיט)</option>
            </select>
          </div>
          <div className="w-40">
            <label className="block text-sm text-slate-600 mb-1">שפות OCR</label>
            <input value={ocr} onChange={(e) => setOcr(e.target.value)}
              className="w-full border border-slate-300 rounded px-3 py-2 text-sm" dir="ltr" />
          </div>
        </div>
        <div className="flex gap-3">
          <button onClick={save} disabled={busy}
            className="bg-cyan-600 text-white px-4 py-2 rounded text-sm disabled:opacity-50 hover:bg-cyan-700">
            {busy ? "שומר..." : "שמור הגדרות"}
          </button>
          <button onClick={test} disabled={busy || !status?.has_secret}
            className="bg-slate-200 text-slate-700 px-4 py-2 rounded text-sm disabled:opacity-50 hover:bg-slate-300">
            בדיקת חיבור
          </button>
        </div>
        <p className="text-xs text-slate-400">
          הערה: במצב "תמיד" כל קובץ CV צורך קרדיט אחד ב-ConvertAPI. אפשר לעבור ל"גיבוי בלבד" כדי לחסוך.
        </p>
      </div>

      <div className="bg-white border border-slate-200 rounded-lg p-4 mb-6 shadow-sm">
        <div className="font-semibold text-slate-700 mb-2">עיבוד מחדש של כשלונות עבר</div>
        <p className="text-sm text-slate-500 mb-3">
          מסמן קורות חיים שנכשלו בעבר לעיבוד מחדש דרך ConvertAPI. תהליך ה-parse יעבד אותם תוך דקות.
        </p>
        <div className="flex gap-3 items-end">
          <div className="w-32">
            <label className="block text-sm text-slate-600 mb-1">כמות מקסימלית</label>
            <input type="number" value={limit} onChange={(e) => setLimit(Number(e.target.value))}
              className="w-full border border-slate-300 rounded px-3 py-2 text-sm" dir="ltr" />
          </div>
          <button onClick={reprocess} disabled={busy || !status?.has_secret}
            className="bg-amber-500 text-white px-4 py-2 rounded text-sm disabled:opacity-50 hover:bg-amber-600">
            עבד מחדש כשלונות
          </button>
        </div>
      </div>

      {msg && (
        <div className={`rounded-lg p-3 text-sm border ${
          msg.ok ? "bg-green-50 text-green-800 border-green-300" : "bg-red-50 text-red-800 border-red-300"
        }`}>{msg.text}</div>
      )}
    </div>
  );
};

export default ConvertApiPage;

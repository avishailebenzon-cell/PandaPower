import React, { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";

// CRITICAL: Get API base URL from environment - MUST use VITE_API_URL (not VITE_API_BASE)
const API_BASE = import.meta.env.VITE_API_URL || "";

interface CompanyProfile {
  base_company_profile: string;
  base_facility_facts: string;
  extra: string;
  agents: string[];
}

const fetchProfile = async (): Promise<CompanyProfile> => {
  const res = await fetch(`${API_BASE}/admin/company-profile`);
  if (!res.ok) throw new Error("Failed to fetch company profile");
  return res.json();
};

export const CompanyProfilePage: React.FC = () => {
  const [extra, setExtra] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);

  const { data, refetch } = useQuery({
    queryKey: ["company-profile"],
    queryFn: fetchProfile,
  });

  // Seed the editable field once the server value arrives.
  useEffect(() => {
    if (data) setExtra(data.extra || "");
  }, [data]);

  const save = async () => {
    setBusy(true);
    setMsg(null);
    try {
      const res = await fetch(`${API_BASE}/admin/company-profile`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ extra }),
      });
      const body = await res.json();
      if (!res.ok) throw new Error(body.detail || "Request failed");
      setMsg({ ok: true, text: "התוכן נשמר ✓ — ייכנס לתוקף בשיחות הבאות של כל הסוכנים" });
      refetch();
    } catch (e: any) {
      setMsg({ ok: false, text: e.message });
    } finally {
      setBusy(false);
    }
  };

  const ReadOnlyBlock: React.FC<{ title: string; text?: string }> = ({ title, text }) => (
    <div className="bg-slate-50 border border-slate-200 rounded-lg p-4 mb-4">
      <div className="font-semibold text-slate-700 mb-2">{title}</div>
      <pre className="whitespace-pre-wrap text-sm text-slate-600 font-sans leading-relaxed">
        {text || "—"}
      </pre>
    </div>
  );

  return (
    <div className="p-6 max-w-3xl mx-auto" dir="rtl">
      <h1 className="text-2xl font-bold text-slate-800 mb-2">🏢 פרופיל החברה (מודול משותף)</h1>
      <p className="text-sm text-slate-500 mb-6">
        זהו הידע על פנדה-טק שמוזרק לכל הסוכנים במערכת
        {data?.agents?.length ? ` (${data.agents.join(", ")})` : ""}. החלק הקבוע מוצג לקריאה בלבד;
        ניתן להוסיף מידע נוסף בתיבת העריכה למטה — הוא יצורף לכל הסוכנים מיד, ללא צורך בפריסה מחדש.
      </p>

      <div className="bg-white border border-slate-200 rounded-lg p-4 mb-6 shadow-sm">
        <div className="font-semibold text-slate-700 mb-3">תוכן קבוע (לקריאה בלבד)</div>
        <ReadOnlyBlock title="מי זו פנדה-טק" text={data?.base_company_profile} />
        <ReadOnlyBlock title="מענה על ארגונים/מפעלים" text={data?.base_facility_facts} />
        <p className="text-xs text-slate-400">
          לשינוי התוכן הקבוע יש לערוך את הקוד (agents/company_profile.py). מומלץ להוסיף מידע דרך התיבה למטה.
        </p>
      </div>

      <div className="bg-white border border-slate-200 rounded-lg p-4 mb-6 shadow-sm space-y-3">
        <div className="font-semibold text-slate-700">מידע נוסף על החברה (ניתן לעריכה)</div>
        <p className="text-sm text-slate-500">
          כל מה שתכתבו כאן יצורף לידע של כל הסוכנים. שימושי להוספת עובדות על החברה, ארגונים/מפעלים נוספים,
          או הנחיות מענה — כדי שהסוכנים לא ימציאו מידע.
        </p>
        <textarea
          value={extra}
          onChange={(e) => setExtra(e.target.value)}
          rows={12}
          maxLength={8000}
          placeholder="למשל: פנדה-טק עובדת גם עם מפעל X באזור Y. אם מועמד שואל על Z — התשובה היא..."
          className="w-full border border-slate-300 rounded px-3 py-2 text-sm leading-relaxed"
        />
        <div className="flex items-center justify-between">
          <span className="text-xs text-slate-400">{extra.length} / 8000 תווים</span>
          <button
            onClick={save}
            disabled={busy}
            className="bg-cyan-600 text-white px-4 py-2 rounded text-sm disabled:opacity-50 hover:bg-cyan-700"
          >
            {busy ? "שומר..." : "שמור"}
          </button>
        </div>
      </div>

      {msg && (
        <div
          className={`rounded-lg p-3 text-sm border ${
            msg.ok
              ? "bg-green-50 text-green-800 border-green-300"
              : "bg-red-50 text-red-800 border-red-300"
          }`}
        >
          {msg.text}
        </div>
      )}
    </div>
  );
};

export default CompanyProfilePage;

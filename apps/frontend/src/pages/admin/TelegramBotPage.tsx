import React, { useState } from "react";
import { useQuery } from "@tanstack/react-query";

// CRITICAL: Get API base URL from environment - MUST use VITE_API_URL (not VITE_API_BASE)
const API_BASE = import.meta.env.VITE_API_URL || "";

interface TelegramStatus {
  configured: boolean;
  enabled: boolean;
  admin_chat_bound: boolean;
  bot_username: string | null;
  webhook_registered: boolean | null;
}

const fetchStatus = async (): Promise<TelegramStatus> => {
  const res = await fetch(`${API_BASE}/admin/telegram/status`);
  if (!res.ok) throw new Error("Failed to fetch Telegram status");
  return res.json();
};

export const TelegramBotPage: React.FC = () => {
  const [token, setToken] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);

  const { data: status, refetch } = useQuery({
    queryKey: ["telegram-status"],
    queryFn: fetchStatus,
    refetchInterval: 10000,
  });

  const configure = async () => {
    setBusy(true);
    setMsg(null);
    try {
      const res = await fetch(`${API_BASE}/admin/telegram/configure`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ bot_token: token.trim() }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Configuration failed");
      setMsg({ ok: true, text: `הבוט @${data.bot_username} חובר! ${data.next_step}` });
      setToken("");
      refetch();
    } catch (e: any) {
      setMsg({ ok: false, text: e.message || "שגיאה בהגדרה" });
    } finally {
      setBusy(false);
    }
  };

  const sendTest = async () => {
    setBusy(true);
    setMsg(null);
    try {
      const res = await fetch(`${API_BASE}/admin/telegram/test`, { method: "POST" });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Test failed");
      setMsg({ ok: true, text: "הודעת בדיקה נשלחה — בדוק את הטלגרם שלך 📲" });
    } catch (e: any) {
      setMsg({ ok: false, text: e.message || "שליחת הבדיקה נכשלה" });
    } finally {
      setBusy(false);
    }
  };

  const Badge: React.FC<{ on: boolean | null; label: string }> = ({ on, label }) => (
    <span
      className={`inline-block px-2 py-1 rounded-full text-xs border ${
        on
          ? "bg-green-100 text-green-800 border-green-300"
          : "bg-slate-100 text-slate-600 border-slate-300"
      }`}
    >
      {on ? "✓" : "✗"} {label}
    </span>
  );

  return (
    <div className="p-6 max-w-2xl mx-auto" dir="rtl">
      <h1 className="text-2xl font-bold text-slate-800 mb-2">🤖 בוט טלגרם — מנהל גיוס כרמית</h1>
      <p className="text-sm text-slate-500 mb-6">
        חבר בוט טלגרם כדי לדבר עם כרמית ישירות ולקבל התראות על התאמות שעוברות לטל, גיוסים, ותקלות בתהליכים.
      </p>

      {/* Status */}
      <div className="bg-white border border-slate-200 rounded-lg p-4 mb-6 shadow-sm">
        <div className="font-semibold text-slate-700 mb-3">סטטוס</div>
        <div className="flex flex-wrap gap-2">
          <Badge on={status?.configured ?? null} label="מוגדר" />
          <Badge on={status?.webhook_registered ?? null} label="Webhook רשום" />
          <Badge on={status?.admin_chat_bound ?? null} label="צ'אט מנהל משויך" />
          <Badge on={status?.enabled ?? null} label="פעיל" />
        </div>
        {status?.bot_username && (
          <div className="text-sm text-slate-500 mt-3">בוט: @{status.bot_username}</div>
        )}
      </div>

      {/* Setup steps */}
      <div className="bg-white border border-slate-200 rounded-lg p-4 mb-6 shadow-sm">
        <div className="font-semibold text-slate-700 mb-3">הגדרה</div>
        <ol className="list-decimal pr-5 text-sm text-slate-600 space-y-2 mb-4">
          <li>ב-Telegram, פתח שיחה עם <b>@BotFather</b> והרץ <code>/newbot</code> (או השתמש בבוט קיים).</li>
          <li>העתק את ה-<b>Token</b> שקיבלת והדבק אותו כאן למטה ולחץ "חבר בוט".</li>
          <li>אחרי החיבור — פתח את הבוט שלך בטלגרם ושלח <code>/start</code> כדי לשייך את הצ'אט שלך.</li>
          <li>לחץ "שלח הודעת בדיקה" לוודא שהכל עובד.</li>
        </ol>

        <label className="block text-sm text-slate-600 mb-1">Bot Token (מ-BotFather)</label>
        <input
          type="password"
          value={token}
          onChange={(e) => setToken(e.target.value)}
          placeholder="123456:ABC-DEF..."
          className="w-full border border-slate-300 rounded px-3 py-2 mb-3 text-sm"
          dir="ltr"
        />
        <div className="flex gap-3">
          <button
            onClick={configure}
            disabled={busy || !token.trim()}
            className="bg-cyan-600 text-white px-4 py-2 rounded text-sm disabled:opacity-50 hover:bg-cyan-700"
          >
            {busy ? "מחבר..." : "חבר בוט"}
          </button>
          <button
            onClick={sendTest}
            disabled={busy || !status?.admin_chat_bound}
            className="bg-slate-200 text-slate-700 px-4 py-2 rounded text-sm disabled:opacity-50 hover:bg-slate-300"
            title={status?.admin_chat_bound ? "" : "שלח /start לבוט קודם"}
          >
            שלח הודעת בדיקה
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

export default TelegramBotPage;

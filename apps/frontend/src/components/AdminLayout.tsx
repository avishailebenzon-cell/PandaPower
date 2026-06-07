/**
 * Admin Layout Component
 * For system administration and configuration
 */

import { Outlet, useNavigate } from "react-router-dom";
import { useAuth } from "@/hooks/useAuth";

export function AdminLayout() {
  const { user } = useAuth();
  const navigate = useNavigate();

  return (
    <div className="flex h-screen flex-col bg-slate-950" dir="rtl">
      {/* Admin Header */}
      <header className="h-14 border-b bg-slate-900 border-slate-700 px-6 flex items-center justify-between">
        <div className="text-sm text-slate-300">{user?.email || "לא מחובר"}</div>
        <div className="text-xl font-bold text-white">🔧 PandaPower - ניהול מערכת</div>
        <button
          onClick={() => navigate("/recruiting")}
          className="text-xs px-3 py-1 rounded bg-indigo-700 hover:bg-indigo-600 text-white transition"
        >
          👥 חטיבת גיוס
        </button>
      </header>

      <div className="flex flex-1 overflow-hidden">
        {/* Admin Sidebar */}
        <aside className="w-80 border-l bg-slate-900 border-slate-700 p-4 overflow-y-auto">
          <nav className="space-y-1 text-sm">
            {/* System Configuration */}
            <div className="pt-2 pb-1 px-3 font-semibold text-indigo-400 border-t border-slate-700">
              ⚙️ הגדרות מערכת
            </div>
            <li>
              <a href="/admin/integrations" className="block px-3 py-2 rounded text-slate-300 hover:bg-slate-800 transition">
                אינטגרציות חיצוניות
              </a>
            </li>
            <li>
              <a href="/admin/pipedrive-config" className="block px-3 py-2 rounded text-slate-300 hover:bg-slate-800 transition">
                🔗 הגדרות Pipedrive
              </a>
            </li>
            <li>
              <a href="/admin/security" className="block px-3 py-2 rounded text-slate-300 hover:bg-slate-800 transition">
                סיווג בטחוני
              </a>
            </li>
            <li>
              <a href="/admin/alerts" className="block px-3 py-2 rounded text-slate-300 hover:bg-slate-800 transition">
                🔔 התראות מערכת
              </a>
            </li>
            <li>
              <a href="/admin/system-health" className="block px-3 py-2 rounded text-slate-300 hover:bg-slate-800 transition">
                🩺 ניטור מערכת
              </a>
            </li>
            <li>
              <a href="/admin/usage" className="block px-3 py-2 rounded text-slate-300 hover:bg-slate-800 transition">
                💰 צריכת Anthropic
              </a>
            </li>
            <li>
              <a href="/admin/telegram-bot" className="block px-3 py-2 rounded text-slate-300 hover:bg-slate-800 transition">
                🤖 בוט טלגרם — כרמית
              </a>
            </li>

            {/* Pipedrive Data Display */}
            <div className="pt-4 pb-1 px-3 font-semibold text-green-400 border-t border-slate-700">
              📊 נתונים מ-Pipedrive
            </div>
            <li>
              <a href="/admin/pipedrive-employees" className="block px-3 py-2 rounded text-slate-300 hover:bg-slate-800 transition">
                👥 עובדים
              </a>
            </li>
            <li>
              <a href="/admin/pipedrive-clients" className="block px-3 py-2 rounded text-slate-300 hover:bg-slate-800 transition">
                🏢 לקוחות
              </a>
            </li>
            <li>
              <a href="/admin/pipedrive-potential-clients" className="block px-3 py-2 rounded text-slate-300 hover:bg-slate-800 transition">
                📋 לקוחות פוטנציאלים
              </a>
            </li>
            <li>
              <a href="/admin/pipedrive-organizations" className="block px-3 py-2 rounded text-slate-300 hover:bg-slate-800 transition">
                🏭 ארגונים
              </a>
            </li>
            <li>
              <a href="/admin/pipedrive-jobs" className="block px-3 py-2 rounded text-slate-300 hover:bg-slate-800 transition">
                💼 משרות
              </a>
            </li>

            {/* Pipeline Management */}
            <div className="pt-4 pb-1 px-3 font-semibold text-cyan-400 border-t border-slate-700">
              📊 ניהול צינור גיוס
            </div>
            <li>
              <a href="/admin/email-intake" className="block px-3 py-2 rounded text-slate-300 hover:bg-slate-800 transition">
                קליטת דוא"ל וקורות חיים
              </a>
            </li>
            <li>
              <a href="/admin/cv-upload" className="block px-3 py-2 rounded text-slate-300 hover:bg-slate-800 transition">
                📤 טעינת קורות חיים ידנית
              </a>
            </li>
            <li>
              <a href="/admin/cv-parsing" className="block px-3 py-2 rounded text-slate-300 hover:bg-slate-800 transition">
                ניתוח וחילוץ CV
              </a>
            </li>
            <li>
              <a href="/admin/convertapi" className="block px-3 py-2 rounded text-slate-300 hover:bg-slate-800 transition">
                📄 סריקת CV (ConvertAPI)
              </a>
            </li>
            <li>
              <a href="/admin/reingest" className="block px-3 py-2 rounded text-slate-300 hover:bg-slate-800 transition">
                ♻️ שחזור קורות חיים אבודים
              </a>
            </li>
            <li>
              <a href="/admin/job-match-status" className="block px-3 py-2 rounded text-slate-300 hover:bg-slate-800 transition">
                ניהול משרות וביצוע התאמות
              </a>
            </li>
            <li>
              <a href="/admin/skills" className="block px-3 py-2 rounded text-slate-300 hover:bg-slate-800 transition">
                ניהול כישורים וקטגוריות
              </a>
            </li>

            {/* AI Agents */}
            {/* Pandi was moved out of "Sales Agents / AI Agents" admin sections
                and now lives entirely in the Work area sidebar (Pandi is an
                operational agent, not admin tooling). The /admin/pandi and
                /admin/pandi-conversations URLs still work but render inside
                the Work-area shell. */}
            <div className="pt-4 pb-1 px-3 font-semibold text-pink-400 border-t border-slate-700">
              🤖 סוכנים AI
            </div>
            <li>
              <a href="/admin/agents" className="block px-3 py-2 rounded text-slate-300 hover:bg-slate-800 transition">
                ניהול סוכנים מיוחדים
              </a>
            </li>
            <li>
              <a href="/admin/whatsapp-agents" className="block px-3 py-2 rounded text-slate-300 hover:bg-slate-800 transition">
                📞 הגדרות WhatsApp (טל / אלעד / פנדי)
              </a>
            </li>

            {/* Reports & Analytics */}
            <div className="pt-4 pb-1 px-3 font-semibold text-emerald-400 border-t border-slate-700">
              📈 דוחות וניתוחים
            </div>
            <li>
              <a href="/admin/analytics" className="block px-3 py-2 rounded text-slate-300 hover:bg-slate-800 transition">
                דוחות ואנליטיקה
              </a>
            </li>

            {/* Work Areas - Recruiting */}
            <div className="pt-4 pb-1 px-3 font-semibold text-amber-400 border-t border-slate-700">
              👥 אזורי עבודה - גיוס
            </div>
            <li>
              <a href="/recruiting" className="block px-3 py-2 rounded text-slate-300 hover:bg-slate-800 transition font-semibold text-amber-300">
                ↪ חזרה למסכי העבודה
              </a>
            </li>
          </nav>
        </aside>

        {/* Admin Content */}
        <main className="flex-1 overflow-auto bg-slate-950 pb-20">
          <Outlet />
        </main>
      </div>

      {/* Admin Footer */}
      <footer className="h-8 border-t bg-slate-900 border-slate-700 px-6 flex items-center text-xs text-slate-500">
        ⚠️ אזור ניהול מערכת - הגדרות חיוניות בלבד
      </footer>
    </div>
  );
}

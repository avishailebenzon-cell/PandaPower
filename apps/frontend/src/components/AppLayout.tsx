import { Outlet } from "react-router-dom";
import { useAuth } from "@/hooks/useAuth";

export function AppLayout() {
  const { user } = useAuth();

  return (
    <div className="flex h-screen flex-col bg-gray-900" dir="rtl">
      <header className="h-14 border-b bg-gray-800 border-gray-700 px-6 flex items-center justify-between">
        <div className="text-sm text-white">{user?.email || "Not signed in"}</div>
        <div className="text-xl font-bold text-white">PandaPower</div>
      </header>

      <div className="flex flex-1 overflow-hidden">
        <main className="flex-1 overflow-auto bg-gray-900">
          <Outlet />
        </main>

        <nav className="w-64 border-l bg-gray-800 border-gray-700 p-4">
          <ul className="space-y-2 text-sm">
            <li><a href="/" className="block px-3 py-2 rounded text-white hover:bg-gray-700">לוח בקרה</a></li>
            <li><a href="/admin/integrations" className="block px-3 py-2 rounded text-white hover:bg-gray-700">אינטגרציות</a></li>
            <li><a href="/admin/pipedrive-config" className="block px-3 py-2 rounded text-white hover:bg-gray-700">🔗 הגדרת Pipedrive</a></li>

            <li className="pt-2 pb-1 px-3 font-semibold text-cyan-400 border-t border-gray-700">נתונים מ-Pipedrive</li>
            <li><a href="/admin/pipedrive-employees" className="block px-3 py-2 rounded text-white hover:bg-gray-700">👥 עובדים</a></li>
            <li><a href="/admin/pipedrive-clients" className="block px-3 py-2 rounded text-white hover:bg-gray-700">🏢 לקוחות</a></li>
            <li><a href="/admin/pipedrive-potential-clients" className="block px-3 py-2 rounded text-white hover:bg-gray-700">📋 לקוחות פוטנציאלים</a></li>
            <li><a href="/admin/pipedrive-organizations" className="block px-3 py-2 rounded text-white hover:bg-gray-700">🏭 ארגונים</a></li>
            <li><a href="/admin/pipedrive-jobs" className="block px-3 py-2 rounded text-white hover:bg-gray-700">💼 משרות</a></li>

            <li><a href="/admin/email-intake" className="block px-3 py-2 rounded text-white hover:bg-gray-700">קליטת דוא"ל</a></li>
            <li><a href="/admin/cv-parsing" className="block px-3 py-2 rounded text-white hover:bg-gray-700">ניתוח קורות חיים</a></li>
            <li><a href="/admin/cv-upload" className="block px-3 py-2 rounded text-white hover:bg-gray-700 transition-colors">📤 העלאה ידנית</a></li>
            <li><a href="/admin/candidates" className="block px-3 py-2 rounded text-white hover:bg-gray-700">מועמדים</a></li>
            <li><a href="/admin/agents" className="block px-3 py-2 rounded text-white hover:bg-gray-700">סוכנים</a></li>

            <li className="pt-2 pb-1 px-3 font-semibold text-blue-400 border-t border-gray-700">סוכנים בחיצוניים</li>
            <li><a href="/admin/pandi-conversations" className="block px-3 py-2 rounded text-white hover:bg-gray-700">💬 ליבי (בקשות לקוחות)</a></li>

            <li className="pt-2 pb-1 px-3 font-semibold text-purple-400 border-t border-gray-700">מנהלת גיוס</li>
            <li><a href="/admin/carmit" className="block px-3 py-2 rounded text-white hover:bg-gray-700">כרמית</a></li>

            <li><a href="/admin/recruiter" className="block px-3 py-2 rounded text-white hover:bg-gray-700">מנהלת גיוס (טל)</a></li>
            <li><a href="/admin/elad" className="block px-3 py-2 rounded text-white hover:bg-gray-700">מנהל מגייסים (אלעד)</a></li>

            <li className="pt-2 pb-1 px-3 font-semibold text-green-400 border-t border-gray-700">מחלקות גיוס</li>
            <li><a href="/admin/departments/naama" className="block px-3 py-2 rounded text-white hover:bg-gray-700">📊 נעמה (תוכנה)</a></li>
            <li><a href="/admin/departments/alik" className="block px-3 py-2 rounded text-white hover:bg-gray-700">📊 אליק (אלקטרוניקה)</a></li>
            <li><a href="/admin/departments/dganit" className="block px-3 py-2 rounded text-white hover:bg-gray-700">📊 דגנית (QA)</a></li>
            <li><a href="/admin/departments/ofir" className="block px-3 py-2 rounded text-white hover:bg-gray-700">📊 עופיר (סיסטמים)</a></li>
            <li><a href="/admin/departments/itai" className="block px-3 py-2 rounded text-white hover:bg-gray-700">📊 איתי (IT)</a></li>
            <li><a href="/admin/departments/lior" className="block px-3 py-2 rounded text-white hover:bg-gray-700">📊 ליאור (מכני)</a></li>
            <li><a href="/admin/departments/gc" className="block px-3 py-2 rounded text-white hover:bg-gray-700">📊 רון (שונות)</a></li>

            <li><a href="/admin/pandi" className="block px-3 py-2 rounded text-white hover:bg-gray-700">ניהול Pandi</a></li>
            <li><a href="/admin/analytics" className="block px-3 py-2 rounded text-white hover:bg-gray-700">דוחות ואנליטיקה</a></li>
            <li><a href="/admin/skills" className="block px-3 py-2 rounded text-white hover:bg-gray-700">כישורים</a></li>
            <li><a href="/admin/security" className="block px-3 py-2 rounded text-white hover:bg-gray-700">סיווג בטחוני</a></li>
          </ul>
        </nav>
      </div>

      <footer className="h-8 border-t bg-gray-800 border-gray-700 px-6 flex items-center text-xs text-white">
        מוכן
      </footer>
    </div>
  );
}

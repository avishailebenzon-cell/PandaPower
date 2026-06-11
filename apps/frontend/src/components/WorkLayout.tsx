/**
 * Work Layout Component
 * For recruiting department agents - focused on daily work
 */

import { Outlet, useNavigate } from "react-router-dom";
import { useAuth } from "@/hooks/useAuth";
import { useState } from "react";
import { RECRUITMENT_AGENTS, RECRUITERS } from "@/data/agents";

export function WorkLayout() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [showAgentsMenu, setShowAgentsMenu] = useState(true);
  const [showRecruitersMenu, setShowRecruitersMenu] = useState(true);
  const [showCarmitMenu, setShowCarmitMenu] = useState(true);
  const [showPandiMenu, setShowPandiMenu] = useState(false);

  return (
    <div className="flex h-screen flex-col bg-gray-900" dir="rtl">
      {/* Work Header - Professional Look */}
      <header className="h-16 border-b bg-gradient-to-r from-indigo-900 via-gray-800 to-purple-900 border-indigo-700 px-6 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="text-xs text-indigo-300 font-semibold">👤</span>
          <span className="text-sm text-indigo-200">{user?.email || "לא מחובר"}</span>
        </div>
        <div className="text-center flex-1">
          <h1 className="text-2xl font-bold bg-gradient-to-r from-indigo-400 to-purple-400 bg-clip-text text-transparent">
            🐼 חטיבת גיוס - PandaPower
          </h1>
          <p className="text-xs text-indigo-300 mt-1">מערכת ניהול גיוס משכללת</p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => navigate("/recruiting/whatsapp-conversations")}
            className="text-xs px-3 py-1 rounded bg-teal-600 hover:bg-teal-500 text-white transition"
          >
            💬 שיחות וואטסאפ
          </button>
          <button
            onClick={() => navigate("/admin")}
            className="text-xs px-3 py-1 rounded bg-slate-700 hover:bg-slate-600 text-slate-200 transition"
          >
            ⚙️ הגדרות
          </button>
        </div>
      </header>

      <div className="flex flex-1 overflow-hidden">
        {/* Work Sidebar - Agent Departments */}
        <aside className="w-72 border-l bg-gray-800 border-gray-700 p-4 overflow-y-auto">
          <div className="space-y-4">
            {/* Main Dashboard */}
            <div>
              <button
                onClick={() => navigate("/recruiting")}
                className="w-full text-right px-4 py-3 rounded-lg bg-indigo-700 hover:bg-indigo-600 text-white font-semibold transition text-sm"
              >
                📊 לוח בקרה ראשי
              </button>
              <button
                onClick={() => navigate("/admin/analytics")}
                className="w-full text-right px-4 py-2 mt-1 rounded-lg bg-emerald-700 hover:bg-emerald-600 text-white font-semibold transition text-sm"
              >
                📈 דוחות ואנליטיקה
              </button>
            </div>

            {/* Recruitment Manager */}
            <div>
              <div
                onClick={() => setShowCarmitMenu(!showCarmitMenu)}
                className="px-3 py-2 font-semibold text-purple-400 cursor-pointer hover:text-purple-300 transition flex items-center justify-between"
              >
                <span>👔 מנהלת גיוס</span>
                <span className="text-xs">{showCarmitMenu ? "▼" : "◀"}</span>
              </div>
              {showCarmitMenu && (
                <nav className="space-y-1 mt-2">
                  <a href="/admin/carmit" className="block px-3 py-2 rounded text-white hover:bg-gray-700 transition text-sm">
                    🤖 כרמית
                  </a>
                  <a href="/recruiting/match-flow" className="block px-3 py-2 rounded text-white hover:bg-gray-700 transition text-sm">
                    📊 Pipeline Flow
                  </a>
                </nav>
              )}
            </div>

            {/* Recruitment Department */}
            <div>
              <div
                onClick={() => setShowAgentsMenu(!showAgentsMenu)}
                className="px-3 py-2 font-semibold text-green-400 cursor-pointer hover:text-green-300 transition flex items-center justify-between"
              >
                <span>📋 מחלקת גיוס</span>
                <span className="text-xs">{showAgentsMenu ? "▼" : "◀"}</span>
              </div>

              {showAgentsMenu && (
                <nav className="space-y-1 mt-2">
                  {Object.values(RECRUITMENT_AGENTS).map((agent) => (
                    <button
                      key={agent.code}
                      onClick={() => navigate(`/recruiting/departments/${agent.code}`)}
                      className="w-full text-right px-4 py-2 rounded text-white hover:bg-gray-700 transition text-sm flex items-center justify-start gap-2"
                      title={agent.description}
                    >
                      <img
                        src={agent.avatar}
                        alt={agent.name}
                        onError={(e) => { e.currentTarget.src = agent.avatarFallback; }}
                        className="w-8 h-8 rounded-full flex-shrink-0 object-cover"
                      />
                      <div className="flex-1">
                        <div className="font-semibold text-sm">{agent.name}</div>
                        <div className="text-xs text-gray-400">{agent.title}</div>
                      </div>
                    </button>
                  ))}
                </nav>
              )}
            </div>

            {/* Recruitment Representatives */}
            <div>
              <div
                onClick={() => setShowRecruitersMenu(!showRecruitersMenu)}
                className="px-3 py-2 font-semibold text-blue-400 cursor-pointer hover:text-blue-300 transition flex items-center justify-between"
              >
                <span>👥 נציגי גיוס</span>
                <span className="text-xs">{showRecruitersMenu ? "▼" : "◀"}</span>
              </div>

              {showRecruitersMenu && (
                <nav className="space-y-1 mt-2">
                  {Object.values(RECRUITERS).map((recruiter) => (
                    <button
                      key={recruiter.code}
                      onClick={() => navigate(`/recruiting/${recruiter.code}`)}
                      className="w-full text-right px-4 py-2 rounded text-white hover:bg-gray-700 transition text-sm flex items-center justify-start gap-3"
                      title={recruiter.description}
                    >
                      <img
                        src={recruiter.avatar}
                        alt={recruiter.name}
                        onError={(e) => { e.currentTarget.src = recruiter.avatarFallback; }}
                        className="w-8 h-8 rounded-full flex-shrink-0 object-cover"
                      />
                      <div className="flex-1">
                        <div className="font-semibold text-sm">{recruiter.name}</div>
                        <div className="text-xs text-gray-400">{recruiter.title}</div>
                      </div>
                    </button>
                  ))}
                </nav>
              )}
            </div>

            {/* Sales Agents */}
            <div>
              <div
                onClick={() => setShowPandiMenu(!showPandiMenu)}
                className="px-3 py-2 font-semibold text-cyan-400 cursor-pointer hover:text-cyan-300 transition flex items-center justify-between"
              >
                <span>💬 סוכני מכירות</span>
                <span className="text-xs">{showPandiMenu ? "▼" : "◀"}</span>
              </div>
              {showPandiMenu && (
                <nav className="space-y-1 mt-2">
                  <a href="/admin/pandi-conversations" className="block px-3 py-2 rounded text-white hover:bg-gray-700 transition text-sm">
                    💬 פנדי (בקשות לקוחות)
                  </a>
                  <a href="/recruiting/dana" className="block px-3 py-2 rounded text-white hover:bg-gray-700 transition text-sm">
                    💼 דנה (הזנת משרות)
                  </a>
                </nav>
              )}
            </div>

          </div>
        </aside>

        {/* Work Content */}
        <main className="flex-1 overflow-auto bg-gray-900 pb-20">
          <Outlet />
        </main>
      </div>

      {/* Work Footer - Status */}
      <footer className="h-10 border-t bg-gray-800 border-gray-700 px-6 flex items-center text-xs text-gray-400 justify-between">
        <div>✅ מערכת מופעלת</div>
        <div className="flex gap-4">
          <span>📍 שעות עבודה: 08:00 - 20:00</span>
          <span>🌍 אזור זמן: ישראל</span>
        </div>
      </footer>
    </div>
  );
}

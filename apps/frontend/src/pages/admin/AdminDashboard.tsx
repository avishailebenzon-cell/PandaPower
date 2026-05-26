/**
 * Admin Dashboard - System administration and monitoring
 */

import React from 'react';
import { useNavigate } from 'react-router-dom';

interface AdminCard {
  title: string;
  description: string;
  icon: string;
  link: string;
  color: string;
  stats?: { label: string; value: string | number }[];
}

const ADMIN_SECTIONS: AdminCard[] = [
  {
    title: "קליטת דוא\"ל וקורות חיים",
    description: "ניהול קבלת אימיילים וחילוץ קורות חיים",
    icon: "📧",
    link: "/admin/email-intake",
    color: "from-blue-900 to-blue-800",
    stats: [
      { label: "אימיילים היום", value: 24 },
      { label: "קורות חיים", value: 18 },
    ],
  },
  {
    title: "ניתוח CV",
    description: "עיבוד וניתוח מסמכי קורות חיים",
    icon: "📄",
    link: "/admin/cv-parsing",
    color: "from-cyan-900 to-cyan-800",
    stats: [
      { label: "בעיבוד", value: 12 },
      { label: "הושלמו", value: 156 },
    ],
  },
  {
    title: "ניהול מועמדים",
    description: "קטלוג וניהול כל המועמדים",
    icon: "👥",
    link: "/admin/candidates",
    color: "from-purple-900 to-purple-800",
    stats: [
      { label: "סה\"כ מועמדים", value: 487 },
      { label: "פעילים", value: 234 },
    ],
  },
  {
    title: "ניהול כישורים",
    description: "קטגוריות כישורים ונורמליזציה",
    icon: "🎯",
    link: "/admin/skills",
    color: "from-green-900 to-green-800",
    stats: [
      { label: "כישורים", value: 139 },
      { label: "מנורמלים", value: 23 },
    ],
  },
  {
    title: "סיווג בטחוני",
    description: "הגדרות ודרגות חיזוקים בטחוניים",
    icon: "🔐",
    link: "/admin/security",
    color: "from-red-900 to-red-800",
    stats: [
      { label: "דרגות", value: 3 },
      { label: "משרות עם חיזוק", value: 45 },
    ],
  },
  {
    title: "אינטגרציות",
    description: "Azure, Pipedrive, ושירותים אחרים",
    icon: "🔗",
    link: "/admin/integrations",
    color: "from-orange-900 to-orange-800",
    stats: [
      { label: "מחוברים", value: 4 },
      { label: "סטטוס", value: "✓" },
    ],
  },
  {
    title: "ניהול סוכנים AI",
    description: "הגדרות ופרמטרים של סוכנים",
    icon: "🤖",
    link: "/admin/agents",
    color: "from-indigo-900 to-indigo-800",
    stats: [
      { label: "סוכנים פעילים", value: 3 },
      { label: "משימות בחודש", value: "1.2K" },
    ],
  },
  {
    title: "ניהול Pandi",
    description: "סוכן WhatsApp וניהול שיחות",
    icon: "💬",
    link: "/admin/pandi",
    color: "from-green-900 to-emerald-800",
    stats: [
      { label: "שיחות פעילות", value: 34 },
      { label: "מועמדים", value: 156 },
    ],
  },
  {
    title: "דוחות ואנליטיקה",
    description: "סטטיסטיקות וביצוע מערכת",
    icon: "📊",
    link: "/admin/analytics",
    color: "from-yellow-900 to-amber-800",
    stats: [
      { label: "שיעור הצלחה", value: "76%" },
      { label: "זמן ממוצע", value: "12 ימים" },
    ],
  },
];

export const AdminDashboard: React.FC = () => {
  const navigate = useNavigate();

  return (
    <div dir="rtl" className="min-h-screen bg-slate-950 p-8">
      <div className="max-w-7xl mx-auto">
        {/* Header */}
        <div className="mb-8">
          <h1 className="text-4xl font-bold text-white mb-2 flex items-center gap-3">
            <span>🔧</span> לוח ניהול מערכת
          </h1>
          <p className="text-slate-400">ניהול הגדרות ויישומים מרכזיים של מערכת PandaPower</p>
        </div>

        {/* System Status */}
        <div className="mb-8 p-4 rounded-lg bg-slate-900 border border-slate-700">
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
            <div className="text-center">
              <div className="text-sm text-slate-400 mb-1">מצב מערכת</div>
              <div className="text-2xl font-bold text-green-400">✓ פעילה</div>
            </div>
            <div className="text-center">
              <div className="text-sm text-slate-400 mb-1">משימות בתור</div>
              <div className="text-2xl font-bold text-blue-400">847</div>
            </div>
            <div className="text-center">
              <div className="text-sm text-slate-400 mb-1">משתמשים מחוברים</div>
              <div className="text-2xl font-bold text-purple-400">12</div>
            </div>
            <div className="text-center">
              <div className="text-sm text-slate-400 mb-1">שגיאות אחרונות</div>
              <div className="text-2xl font-bold text-red-400">0</div>
            </div>
          </div>
        </div>

        {/* Admin Sections Grid */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {ADMIN_SECTIONS.map((section) => (
            <button
              key={section.link}
              onClick={() => navigate(section.link)}
              className={`text-right p-6 rounded-lg bg-gradient-to-br ${section.color} border border-slate-700 hover:border-slate-500 transition cursor-pointer group shadow-lg`}
            >
              {/* Icon */}
              <div className="text-4xl mb-3 group-hover:scale-110 transition">{section.icon}</div>

              {/* Title and Description */}
              <h3 className="text-lg font-bold text-white mb-1">{section.title}</h3>
              <p className="text-sm text-slate-300 mb-4">{section.description}</p>

              {/* Stats */}
              {section.stats && (
                <div className="space-y-2">
                  {section.stats.map((stat, idx) => (
                    <div key={idx} className="flex items-center justify-between text-sm">
                      <span className="text-slate-300">{stat.label}</span>
                      <span className="font-bold text-white">{stat.value}</span>
                    </div>
                  ))}
                </div>
              )}

              {/* Hover Arrow */}
              <div className="text-slate-300 group-hover:text-white transition mt-4 flex items-center justify-end">
                <span className="text-sm">פתח →</span>
              </div>
            </button>
          ))}
        </div>

        {/* Return to Work */}
        <div className="mt-12 p-6 rounded-lg bg-indigo-900 border border-indigo-700 text-center">
          <div className="text-lg font-semibold text-white mb-2">🔄 חזרה לאזור העבודה</div>
          <p className="text-indigo-200 mb-4">אם אתה צריך לחזור לעבודה בחטיבות הגיוס</p>
          <button
            onClick={() => navigate("/recruiting")}
            className="px-6 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white font-semibold transition"
          >
            ↪ לחטיבות הגיוס
          </button>
        </div>
      </div>
    </div>
  );
};

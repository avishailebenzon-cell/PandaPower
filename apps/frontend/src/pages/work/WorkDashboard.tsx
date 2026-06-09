/**
 * Work Dashboard - Main page for recruiting department
 * Shows overview of all matches and pending work
 */

import React, { useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { RECRUITMENT_AGENTS, RECRUITERS } from '@/data/agents';

// CRITICAL: Get API base URL from environment - MUST use VITE_API_URL (not VITE_API_BASE)
// On Vercel VITE_API_URL points straight at the Render backend, so endpoints are
// addressed directly (NOT through the /api rewrite). The previous code hit
// /api/agents/... and /api/department-matches, which don't exist on the backend
// and 404'd — leaving every KPI on its zero fallback. These now use the same
// real endpoints the department pages use.
const API_BASE = import.meta.env.VITE_API_URL || '';

// Real per-department stats: totalMatches / inProgress / approved / rejected / approvalRate
const fetchDepartmentStats = async (agentCode: string) => {
  const response = await fetch(`${API_BASE}/admin/departments/${agentCode}/stats`);
  if (!response.ok) throw new Error('Failed to fetch department stats');
  return response.json();
};

// Real aggregate KPIs computed from the matches table (pending, active conversations, ...)
const fetchKpiSummary = async () => {
  const response = await fetch(`${API_BASE}/admin/analytics/kpi-summary?period=month`);
  if (!response.ok) throw new Error('Failed to fetch KPI summary');
  return response.json();
};

// Real active-jobs count (status='open'). Uses the lightweight paginated jobs
// endpoint (limit=1, read total) instead of the heavy /system-status endpoint,
// which periodically 500s on Render and left this card stuck on 0.
const fetchActiveJobsCount = async (): Promise<number> => {
  const response = await fetch(`${API_BASE}/admin/pipedrive/data/jobs?status=open&limit=1`);
  if (!response.ok) throw new Error('Failed to fetch active jobs count');
  const data = await response.json();
  return data.total ?? 0;
};

interface StatCard {
  label: string;
  value: number | string;
  unit?: string;
  color: string;
}

const StatCard: React.FC<StatCard> = ({ label, value, unit, color }) => (
  <div className={`bg-gradient-to-br ${color} rounded-lg p-4 text-white shadow-lg`}>
    <div className="text-sm text-gray-100 mb-1">{label}</div>
    <div className="text-3xl font-bold">{value}</div>
    {unit && <div className="text-xs text-gray-200 mt-1">{unit}</div>}
  </div>
);

export const WorkDashboard: React.FC = () => {
  const navigate = useNavigate();

  // RECRUITMENT_AGENTS is a Record (object keyed by code) — must convert to
  // an array before .map(). The previous code called .map directly on the
  // object and crashed the entire /recruiting route with "X.map is not a
  // function". The list is stable across renders so calling useQuery inside
  // the map is safe per React rules-of-hooks.
  const agentList = Object.values(RECRUITMENT_AGENTS);

  // Fetch real per-department stats for every agent (same endpoint the
  // department pages use). The list is stable so calling useQuery in a map is
  // safe per rules-of-hooks.
  const agentStatsQueries = agentList.map((agent) => ({
    agent,
    ...useQuery({
      queryKey: ['department-stats', agent.code],
      queryFn: () => fetchDepartmentStats(agent.code),
      refetchInterval: 15000, // Refresh every 15 seconds
      retry: 1,
    }),
  }));

  // Aggregate KPIs come from the analytics + system-status endpoints, which
  // compute them directly from the matches/jobs tables (real, not estimated).
  const { data: kpi } = useQuery({
    queryKey: ['work-kpi-summary'],
    queryFn: fetchKpiSummary,
    refetchInterval: 15000,
    retry: 1,
  });
  const { data: activeJobs = 0 } = useQuery({
    queryKey: ['work-active-jobs'],
    queryFn: fetchActiveJobsCount,
    refetchInterval: 15000,
    retry: 2,
  });

  // Map real per-department data for the agent cards.
  const allStatsData = agentStatsQueries.map((q) => ({
    code: q.agent.code,
    data: q.data,
    successRate: q.data?.approvalRate != null ? Math.round(q.data.approvalRate) : 0,
    matchesCreated: q.data?.totalMatches || 0,
  }));

  // Real aggregate values (fall back to 0 while loading — never to fabricated estimates).
  const totalPendingMatches = kpi?.pending_matches ?? 0;
  const totalConversations = kpi?.active_conversations ?? 0;
  const avgSuccessRate = allStatsData.length > 0
    ? Math.round(allStatsData.reduce((sum, item) => sum + (item.successRate || 0), 0) / allStatsData.length)
    : 0;

  return (
    <div dir="rtl" className="min-h-screen bg-gray-900 p-8">
      <div className="max-w-7xl mx-auto">
        {/* Header */}
        <div className="mb-8">
          <h1 className="text-4xl font-bold text-white mb-2">📊 לוח בקרה - חטיבת גיוס</h1>
          <p className="text-gray-400">סיכום מהיר של פעילות היום בחטיבות הגיוס</p>
        </div>

        {/* KPI Cards Grid */}
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-8">
          <StatCard
            label="התאמות מחכות"
            value={totalPendingMatches}
            unit="בחטיבות"
            color="from-blue-600 to-blue-800"
          />
          <StatCard
            label="שיחות פעילות"
            value={totalConversations}
            unit="כרגע"
            color="from-purple-600 to-purple-800"
          />
          <StatCard
            label="שיעור הצלחה ממוצע"
            value={`${avgSuccessRate}%`}
            unit="בחטיבות"
            color="from-green-600 to-green-800"
          />
          <StatCard
            label="משרות פעילות"
            value={activeJobs}
            unit="נמצאות בגיוס"
            color="from-amber-600 to-amber-800"
          />
        </div>

        {/* Main Content - Two Columns */}
        <div className="grid grid-cols-3 gap-6">
          {/* Recruitment Departments - Left Side (2 columns) */}
          <div className="col-span-2">
            <div className="bg-gray-800 rounded-lg border border-gray-700 p-6">
              <h2 className="text-xl font-bold text-white mb-6 flex items-center gap-2">
                <span>👥</span> חטיבות גיוס
              </h2>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {agentList.map((agent) => {
                  const statsItem = allStatsData.find(s => s.code === agent.code);
                  const stats = statsItem || { matchesCreated: 0, successRate: 0 };
                  const isLoading = agentStatsQueries.find(q => q.agent.code === agent.code)?.isLoading;

                  return (
                  <button
                    key={agent.code}
                    onClick={() => navigate(`/recruiting/departments/${agent.code}`)}
                    className={`text-right p-4 rounded-lg border hover:border-gray-500 bg-gray-900 hover:bg-gray-850 transition cursor-pointer group ${
                      (stats.matchesCreated || 0) > 0
                        ? 'animate-working-pulse border-cyan-500 shadow-lg'
                        : 'border-gray-700'
                    } ${isLoading ? 'opacity-60' : ''}`}
                    title={agent.description}
                    disabled={isLoading}
                  >
                    {/* Agent Header with Avatar */}
                    <div className="flex items-center gap-3 mb-3">
                      <img
                        src={agent.avatar}
                        alt={agent.name}
                        className={`w-12 h-12 rounded-full flex-shrink-0 group-hover:scale-110 transition border-2 border-gray-700`}
                      />
                      <div className="flex-1">
                        <h3 className="font-semibold text-white text-sm">{agent.name}</h3>
                        <p className="text-xs text-gray-400">{agent.department}</p>
                      </div>
                    </div>

                    {/* Agent Stats - Real Data */}
                    <div className="space-y-2">
                      <div className="flex items-center justify-between text-sm">
                        <span className="text-gray-400">סה"כ התאמות</span>
                        <span className="text-blue-400 font-semibold">
                          {isLoading ? '...' : stats.matchesCreated}
                        </span>
                      </div>
                      <div className="flex items-center justify-between text-sm">
                        <span className="text-gray-400">אושרו</span>
                        <span className="text-purple-400 font-semibold">
                          {isLoading ? '...' : statsItem?.data?.approved || 0}
                        </span>
                      </div>
                      <div className="flex items-center justify-between text-sm">
                        <span className="text-gray-400">שיעור אישור</span>
                        <span className="text-green-400 font-semibold">
                          {isLoading ? '...' : `${stats.successRate}%`}
                        </span>
                      </div>
                    </div>

                    {/* Progress Bar */}
                    <div className="mt-3 w-full bg-gray-700 rounded-full h-2">
                      <div
                        className="bg-gradient-to-r from-blue-500 to-purple-500 h-2 rounded-full transition-all"
                        style={{ width: `${Math.min((stats.matchesCreated || 0) * 5, 100)}%` }}
                      />
                    </div>
                  </button>
                );
                })}
              </div>
            </div>
          </div>

          {/* Recruiters - Right Side */}
          <div>
            <div className="bg-gray-800 rounded-lg border border-gray-700 p-6">
              <h2 className="text-xl font-bold text-white mb-6 flex items-center gap-2">
                <span>🎯</span> מנהלי מגייסים
              </h2>

              <div className="space-y-4">
                <div className="text-xs text-gray-500 p-3 bg-gray-900 rounded-lg">
                  ℹ️ נתונים אמיתיים מהדטאבייס - מתעדכן כל 15 שניות
                </div>
                {Object.values(RECRUITERS).map((recruiter) => {
                  return (
                  <button
                    key={recruiter.code}
                    onClick={() => navigate(`/recruiting/${recruiter.code}`)}
                    className="w-full text-right p-4 rounded-lg border border-gray-700 hover:border-gray-500 bg-gray-900 hover:bg-gray-850 transition cursor-pointer group"
                    title={recruiter.description}
                  >
                    {/* Recruiter Header */}
                    <div className="flex items-center gap-3 mb-3">
                      <img
                        src={recruiter.avatar}
                        alt={recruiter.name}
                        className="w-12 h-12 rounded-full flex-shrink-0 group-hover:scale-110 transition border-2 border-gray-700"
                      />
                      <div className="flex-1">
                        <h3 className="font-semibold text-white text-sm">{recruiter.name}</h3>
                        <p className="text-xs text-gray-400">{recruiter.title}</p>
                      </div>
                    </div>

                    {/* Recruiter Info - Click to view detailed stats */}
                    <div className="text-xs text-gray-400 text-center py-2">
                      הנתונים יופיעו בחלון הרשלי
                    </div>
                  </button>
                );
                })}
              </div>
            </div>
          </div>
        </div>

        {/* Bottom Section - Quick Actions */}
        <div className="mt-8 grid grid-cols-1 md:grid-cols-4 gap-4">
          <button
            onClick={() => navigate("/recruiting/departments/naama")}
            className="p-4 rounded-lg bg-gradient-to-br from-blue-900 to-blue-800 hover:from-blue-800 hover:to-blue-700 text-white transition text-center"
          >
            <div className="text-2xl mb-2">📋</div>
            <div className="font-semibold">הצג את הניסיון שלי</div>
            <div className="text-sm text-blue-200 mt-1">נעמה - תוכנה</div>
          </button>

          <button
            onClick={() => navigate("/recruiting/tal")}
            className="p-4 rounded-lg bg-gradient-to-br from-purple-900 to-purple-800 hover:from-purple-800 hover:to-purple-700 text-white transition text-center"
          >
            <div className="text-2xl mb-2">🎯</div>
            <div className="font-semibold">התאמות בהמתנה</div>
            <div className="text-sm text-purple-200 mt-1">לסקירה שלי</div>
          </button>

          <button
            onClick={() => navigate("/recruiting/conversations")}
            className="p-4 rounded-lg bg-gradient-to-br from-emerald-900 to-emerald-800 hover:from-emerald-800 hover:to-emerald-700 text-white transition text-center"
          >
            <div className="text-2xl mb-2">💬</div>
            <div className="font-semibold">שיחות</div>
            <div className="text-sm text-emerald-200 mt-1">כל השיחות</div>
          </button>

          <button
            onClick={() => navigate("/admin")}
            className="p-4 rounded-lg bg-gradient-to-br from-slate-700 to-slate-800 hover:from-slate-600 hover:to-slate-700 text-white transition text-center"
          >
            <div className="text-2xl mb-2">⚙️</div>
            <div className="font-semibold">הגדרות מערכת</div>
            <div className="text-sm text-slate-300 mt-1">לניהול בלבד</div>
          </button>
        </div>

        {/* CSS Animations for Working Agent Pulse */}
        <style>{`
          @keyframes working-pulse {
            0%, 100% {
              box-shadow: 0 0 0 0 rgba(34, 197, 233, 0.4),
                          0 0 0 0 rgba(34, 197, 233, 0.3),
                          inset 0 0 0 1px rgba(34, 197, 233, 0.3);
            }
            50% {
              box-shadow: 0 0 0 10px rgba(34, 197, 233, 0),
                          0 0 0 20px rgba(34, 197, 233, 0),
                          inset 0 0 0 1px rgba(34, 197, 233, 0.5);
            }
          }

          .animate-working-pulse {
            animation: working-pulse 2s infinite;
          }
        `}</style>
      </div>
    </div>
  );
};

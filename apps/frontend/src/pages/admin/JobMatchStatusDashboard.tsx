/**
 * Job & Match Status Dashboard
 * Real-time visibility into jobs, matches, agents, and system status
 * Replaces defunct Candidate Catalog screen
 */

import React, { useState, useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  BarChart,
  Bar,
  PieChart,
  Pie,
  Cell,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from "recharts";
import KPICard from "../../components/KPICard";

// API fetch configuration
const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";

// TypeScript Interfaces
interface SystemSummary {
  total_active_jobs: number;
  total_pending_candidates: number;
  total_matches_in_progress: number;
  priority_distribution: Record<string, number>;
}

interface CarmitStatus {
  status: "idle" | "processing";
  last_action: string;
  last_action_at: string;
  jobs_routed_today: number;
  jobs_routed_this_week: number;
  average_routing_confidence: number;
}

interface AgentStatus {
  agent_code: string;
  agent_name: string;
  domain: string;
  status: "idle" | "processing" | "waiting";
  current_task: string;
  current_job_id: string;
  progress: string;
  matches_found_today: number;
  matches_found_week: number;
  last_active_at: string;
  next_scheduled_check: string;
  workload: "light" | "medium" | "high";
  success_rate_today: number;
}

interface MatchInProgress {
  candidate_id: string;
  candidate_name: string;
  job_id: string;
  job_title: string;
  agent_handling: string;
  status: string;
  score: number;
  created_at: string;
  last_updated_at: string;
  next_review_at: string;
}

interface JobChange {
  job_id: string;
  job_title: string;
  change_type: string;
  changed_at: string;
  fields_changed: string[];
  matches_invalidated: number;
  rematch_status: string;
}

interface Activity {
  timestamp: string;
  type: string;
  agent_code?: string;
  candidate_name?: string;
  job_title?: string;
  match_score?: number;
  status?: string;
  priority?: number;
  routing_confidence?: number;
}

interface ChangeDetectionMetrics {
  matches_invalidated_today: number;
  rematches_triggered_today: number;
  total_job_changes_today: number;
}

interface SystemStatus {
  timestamp: string;
  system_summary: SystemSummary;
  carmit_status: CarmitStatus;
  agent_statuses: AgentStatus[];
  recent_activities: Activity[];
  matches_in_progress: MatchInProgress[];
  recent_job_changes: JobChange[];
  change_detection_metrics: ChangeDetectionMetrics;
}

// Fetch function
const fetchSystemStatus = async (): Promise<SystemStatus> => {
  // Always use real data - demo data disabled
  // Only use demo if explicitly requested via URL parameter (for testing)
  const isDemo = new URLSearchParams(window.location.search).get('demo') === 'true';
  const url = isDemo
    ? `${API_BASE}/admin/agent-matching/system-status?demo=true`
    : `${API_BASE}/admin/agent-matching/system-status`;

  try {
    const response = await fetch(url);
    if (!response.ok) {
      console.error(`API error: ${response.status} ${response.statusText}`);
      throw new Error(`Failed to fetch system status: ${response.statusText}`);
    }
    return response.json();
  } catch (error) {
    console.error("Failed to fetch system status:", error);
    throw error;
  }
};

// Color mapping utilities
const getWorkloadColor = (workload: string): string => {
  switch (workload) {
    case "light":
      return "bg-green-900";
    case "medium":
      return "bg-yellow-900";
    case "high":
      return "bg-red-900";
    default:
      return "bg-slate-900";
  }
};

const getStatusColor = (status: string): string => {
  switch (status) {
    case "found":
      return "bg-blue-600";
    case "carmit_approved":
      return "bg-purple-600";
    case "sent_to_recruiter":
      return "bg-cyan-600";
    case "recruiter_approved":
      return "bg-green-600";
    case "hired":
      return "bg-emerald-600";
    case "failed":
      return "bg-red-600";
    default:
      return "bg-slate-600";
  }
};

const getChangeTypeColor = (changeType: string): string => {
  switch (changeType) {
    case "priority_changed":
      return "text-yellow-400";
    case "specs_changed":
      return "text-orange-400";
    case "modified":
      return "text-cyan-400";
    default:
      return "text-slate-400";
  }
};

// Format timestamp
const formatTime = (timestamp: string): string => {
  const date = new Date(timestamp);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMins = Math.floor(diffMs / 60000);
  const diffHours = Math.floor(diffMs / 3600000);

  if (diffMins < 1) return "זה עתה";
  if (diffMins < 60) return `${diffMins} דקות`;
  if (diffHours < 24) return `${diffHours} שעות`;
  return date.toLocaleDateString("he-IL");
};

// Component: System Summary Section
const SystemSummarySection: React.FC<{ summary: SystemSummary }> = ({
  summary,
}) => {
  // Prepare priority distribution data for chart
  const priorityData = Object.entries(summary.priority_distribution).map(
    ([key, value]) => ({
      name: key.replace("priority_", "עדיפות "),
      value,
    })
  );

  const COLORS = ["#10b981", "#f59e0b", "#ef4444", "#6366f1", "#8b5cf6"];

  return (
    <div className="space-y-4">
      <h2 className="text-xl font-bold text-white">📊 סיכום מערכת</h2>

      {/* KPI Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <KPICard
          label="משרות פעילות"
          value={summary.total_active_jobs}
          color="bg-blue-900"
          metric="משרות"
        />
        <KPICard
          label="מועמדים ממתינים"
          value={summary.total_pending_candidates}
          color="bg-cyan-900"
          metric="מועמדים"
        />
        <KPICard
          label="התאמות בטיפול"
          value={summary.total_matches_in_progress}
          color="bg-purple-900"
          metric="התאמות"
        />
        <KPICard
          label="משרות עדיפות 1"
          value={summary.priority_distribution["priority_1"] || 0}
          color="bg-red-900"
          metric="דחופות"
        />
      </div>

      {/* Priority Distribution Chart */}
      <div className="bg-slate-800 rounded-lg p-4 border border-slate-700">
        <h3 className="text-sm font-semibold text-white mb-4">
          📈 התפלגות עדיפויות
        </h3>
        <ResponsiveContainer width="100%" height={300}>
          <PieChart>
            <Pie
              data={priorityData}
              cx="50%"
              cy="50%"
              labelLine={false}
              label={({ name, value }) => `${name}: ${value}`}
              outerRadius={80}
              fill="#8884d8"
              dataKey="value"
            >
              {COLORS.map((color, index) => (
                <Cell key={`cell-${index}`} fill={color} />
              ))}
            </Pie>
            <Tooltip formatter={(value) => `${value} משרות`} />
          </PieChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
};

// Component: Carmit Status Card
const CarmitStatusCard: React.FC<{ status: CarmitStatus }> = ({ status }) => {
  const isProcessing = status.status === "processing";

  return (
    <div className="bg-slate-800 rounded-lg p-6 border border-slate-700">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-xl font-bold text-white">👔 כרמית - מנהלת גיוס</h2>
        <div
          className={`px-3 py-1 rounded-full text-sm font-semibold ${
            isProcessing
              ? "bg-yellow-900 text-yellow-300"
              : "bg-green-900 text-green-300"
          }`}
        >
          {isProcessing ? "🔄 בעיבוד" : "✓ סרק"}
        </div>
      </div>

      <div className="space-y-3 text-sm">
        <div className="flex justify-between text-slate-300">
          <span>פעולה אחרונה:</span>
          <span className="text-white font-medium">{status.last_action}</span>
        </div>
        <div className="flex justify-between text-slate-300">
          <span>בוצעה ב:</span>
          <span className="text-white font-medium">
            {formatTime(status.last_action_at)}
          </span>
        </div>
        <div className="border-t border-slate-700 pt-3 mt-3">
          <div className="flex justify-between text-slate-300 mb-2">
            <span>משרות ניתבו היום:</span>
            <span className="text-white font-bold">
              {status.jobs_routed_today}
            </span>
          </div>
          <div className="flex justify-between text-slate-300 mb-2">
            <span>משרות ניתבו השבוע:</span>
            <span className="text-white font-bold">
              {status.jobs_routed_this_week}
            </span>
          </div>
          <div className="flex justify-between text-slate-300">
            <span>רמת ביטחון ממוצעת:</span>
            <span className="text-white font-bold">
              {(status.average_routing_confidence * 100).toFixed(0)}%
            </span>
          </div>
        </div>
      </div>
    </div>
  );
};

// Component: Agent Status Grid
const AgentStatusGrid: React.FC<{ agents: AgentStatus[] }> = ({ agents }) => {
  return (
    <div className="space-y-4">
      <h2 className="text-xl font-bold text-white">🤖 סוכנים - סטטוס זמן אמת</h2>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {agents.map((agent) => (
          <div
            key={agent.agent_code}
            className="bg-slate-800 rounded-lg p-4 border border-slate-700 space-y-3"
          >
            {/* Agent Header */}
            <div className="flex items-center justify-between">
              <div>
                <h3 className="text-lg font-bold text-white">
                  {agent.agent_name}
                </h3>
                <p className="text-xs text-slate-400">{agent.domain}</p>
              </div>
              <div
                className={`px-2 py-1 rounded text-xs font-semibold ${
                  agent.status === "idle"
                    ? "bg-green-900 text-green-300"
                    : agent.status === "processing"
                      ? "bg-yellow-900 text-yellow-300"
                      : "bg-blue-900 text-blue-300"
                }`}
              >
                {agent.status === "idle"
                  ? "סרק"
                  : agent.status === "processing"
                    ? "בטיפול"
                    : "ממתין"}
              </div>
            </div>

            {/* Current Task */}
            <div className="bg-slate-700 rounded p-2 text-xs text-slate-200">
              <div className="font-semibold text-slate-300 mb-1">
                📋 משימה נוכחית:
              </div>
              <div className="line-clamp-2">{agent.current_task}</div>
              {agent.progress && (
                <div className="text-slate-400 text-right mt-1">
                  {agent.progress}
                </div>
              )}
            </div>

            {/* Workload Indicator */}
            <div className="flex items-center gap-2">
              <div className="text-sm text-slate-300">עומס עבודה:</div>
              <div
                className={`px-2 py-1 rounded text-xs font-semibold ${getWorkloadColor(
                  agent.workload
                )} ${agent.workload === "light" ? "text-green-300" : agent.workload === "medium" ? "text-yellow-300" : "text-red-300"}`}
              >
                {agent.workload === "light"
                  ? "🟢 קל"
                  : agent.workload === "medium"
                    ? "🟡 בינוני"
                    : "🔴 כבד"}
              </div>
            </div>

            {/* Stats */}
            <div className="grid grid-cols-2 gap-2 text-xs">
              <div className="bg-slate-700 rounded p-2">
                <div className="text-slate-400">היום</div>
                <div className="text-white font-bold">
                  {agent.matches_found_today}
                </div>
              </div>
              <div className="bg-slate-700 rounded p-2">
                <div className="text-slate-400">השבוע</div>
                <div className="text-white font-bold">
                  {agent.matches_found_week}
                </div>
              </div>
            </div>

            {/* Success Rate */}
            <div className="flex items-center justify-between text-xs border-t border-slate-700 pt-2">
              <span className="text-slate-400">שיעור הצלחה:</span>
              <span className="text-green-400 font-bold">
                {(agent.success_rate_today * 100).toFixed(0)}%
              </span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};

// Component: Matches In Progress Section
const MatchesInProgressSection: React.FC<{
  matches: MatchInProgress[];
}> = ({ matches }) => {
  return (
    <div className="space-y-4">
      <h2 className="text-xl font-bold text-white">
        🎯 התאמות בטיפול ({matches.length})
      </h2>

      <div className="bg-slate-800 rounded-lg border border-slate-700 overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-slate-700 bg-slate-900">
              <th className="px-4 py-3 text-right font-semibold text-slate-300">
                מועמד
              </th>
              <th className="px-4 py-3 text-right font-semibold text-slate-300">
                משרה
              </th>
              <th className="px-4 py-3 text-right font-semibold text-slate-300">
                ניקוד
              </th>
              <th className="px-4 py-3 text-right font-semibold text-slate-300">
                סטטוס
              </th>
              <th className="px-4 py-3 text-right font-semibold text-slate-300">
                סוכן
              </th>
              <th className="px-4 py-3 text-right font-semibold text-slate-300">
                משך זמן
              </th>
            </tr>
          </thead>
          <tbody>
            {matches.slice(0, 10).map((match) => (
              <tr
                key={match.candidate_id}
                className="border-b border-slate-700 hover:bg-slate-700 transition"
              >
                <td className="px-4 py-3 text-slate-300">
                  {match.candidate_name}
                </td>
                <td className="px-4 py-3 text-slate-300">
                  {match.job_title}
                </td>
                <td className="px-4 py-3">
                  <span className="font-bold text-white">
                    {(match.score * 100).toFixed(0)}%
                  </span>
                </td>
                <td className="px-4 py-3">
                  <span
                    className={`px-2 py-1 rounded text-xs font-semibold text-white ${getStatusColor(match.status)}`}
                  >
                    {match.status}
                  </span>
                </td>
                <td className="px-4 py-3 text-slate-300">
                  {match.agent_handling}
                </td>
                <td className="px-4 py-3 text-slate-400">
                  {formatTime(match.created_at)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {matches.length > 10 && (
        <p className="text-sm text-slate-400 text-center">
          מוצגת הופעה של 10 התאמות ראשונות מתוך {matches.length}
        </p>
      )}
    </div>
  );
};

// Component: Job Changes Section
const JobChangesSection: React.FC<{ changes: JobChange[] }> = ({ changes }) => {
  if (!changes || changes.length === 0) {
    return (
      <div className="space-y-4">
        <h2 className="text-xl font-bold text-white">📝 שינויים במשרות</h2>
        <div className="bg-slate-800 rounded-lg p-6 border border-slate-700 text-center text-slate-400">
          אין שינויים בתקופה זו
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <h2 className="text-xl font-bold text-white">
        📝 שינויים במשרות ({changes.length})
      </h2>

      <div className="space-y-3">
        {changes.map((change) => (
          <div
            key={change.job_id}
            className="bg-slate-800 rounded-lg p-4 border border-slate-700 hover:border-slate-600 transition"
          >
            <div className="flex items-start justify-between mb-3">
              <div>
                <h3 className="font-semibold text-white">{change.job_title}</h3>
                <p className={`text-sm ${getChangeTypeColor(change.change_type)}`}>
                  {change.change_type}
                </p>
              </div>
              <span className="text-xs text-slate-400">
                {formatTime(change.changed_at)}
              </span>
            </div>

            <div className="space-y-2 text-sm">
              <div className="flex items-center gap-2 text-slate-300">
                <span className="font-medium">שינויים:</span>
                <span className="text-slate-400">
                  {change.fields_changed.join(", ")}
                </span>
              </div>
              <div className="flex items-center gap-2">
                <span className="font-medium text-slate-300">
                  התאמות שבוטלו:
                </span>
                <span
                  className={`font-bold ${
                    change.matches_invalidated > 0
                      ? "text-red-400"
                      : "text-slate-400"
                  }`}
                >
                  {change.matches_invalidated}
                </span>
              </div>
              <div className="flex items-center gap-2">
                <span className="font-medium text-slate-300">סטטוס ריתוב:</span>
                <span
                  className={`text-xs font-semibold px-2 py-1 rounded ${
                    change.rematch_status === "in_progress"
                      ? "bg-yellow-900 text-yellow-300"
                      : change.rematch_status === "completed"
                        ? "bg-green-900 text-green-300"
                        : "bg-slate-700 text-slate-300"
                  }`}
                >
                  {change.rematch_status}
                </span>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};

// Component: Change Detection Metrics
const ChangeDetectionMetricsSection: React.FC<{
  metrics: ChangeDetectionMetrics;
}> = ({ metrics }) => {
  return (
    <div className="space-y-4">
      <h2 className="text-xl font-bold text-white">🔍 מדדי זיהוי שינויים</h2>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <KPICard
          label="התאמות שבוטלו היום"
          value={metrics.matches_invalidated_today}
          color="bg-red-900"
          metric="בוטלו"
        />
        <KPICard
          label="ריתובים שהופעלו היום"
          value={metrics.rematches_triggered_today}
          color="bg-orange-900"
          metric="ריתובים"
        />
        <KPICard
          label="משרות שהשתנו היום"
          value={metrics.total_job_changes_today}
          color="bg-cyan-900"
          metric="שינויים"
        />
      </div>
    </div>
  );
};

// Main Component
const JobMatchStatusDashboard: React.FC = () => {
  const [lastUpdated, setLastUpdated] = useState<string>(new Date().toLocaleTimeString("he-IL"));

  // Fetch system status with polling
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["system-status"],
    queryFn: fetchSystemStatus,
    refetchInterval: 12000, // 12 seconds
    refetchOnWindowFocus: true,
    staleTime: 5000,
  });

  // Update last updated time when data changes
  useEffect(() => {
    if (data) {
      setLastUpdated(new Date().toLocaleTimeString("he-IL"));
    }
  }, [data]);

  return (
    <div className="flex-1 overflow-y-auto bg-slate-950 p-6" dir="rtl">
      {/* Page Header */}
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold text-white">
            ניהול משרות וביצוע התאמות
          </h1>
          <p className="text-slate-400 text-sm mt-1">
            עדכון אחרון: {lastUpdated}
            {data && ` | סה"כ {data.system_summary.total_active_jobs} משרות פעילות`}
          </p>
        </div>
        <button
          onClick={() => refetch()}
          className="px-4 py-2 bg-blue-600 hover:bg-blue-700 rounded-lg text-white text-sm font-medium transition"
        >
          🔄 רענן עכשיו
        </button>
      </div>

      {/* Loading State */}
      {isLoading && !data && (
        <div className="flex items-center justify-center h-96">
          <div className="text-center">
            <div className="animate-spin mb-4 inline-block">⏳</div>
            <p className="text-slate-400">טוען נתונים...</p>
          </div>
        </div>
      )}

      {/* Error State */}
      {error && (
        <div className="bg-red-900 border border-red-700 rounded-lg p-4 mb-6">
          <p className="text-red-200 font-semibold">שגיאה בטעינת נתונים</p>
          <p className="text-red-300 text-sm mt-1">
            {error instanceof Error ? error.message : "שגיאה לא ידועה"}
          </p>
          <button
            onClick={() => refetch()}
            className="mt-3 px-4 py-2 bg-red-700 hover:bg-red-600 rounded text-white text-sm transition"
          >
            נסה שוב
          </button>
        </div>
      )}

      {/* Dashboard Content */}
      {data && (
        <div className="space-y-8">
          {/* Section 1: System Summary */}
          <SystemSummarySection summary={data.system_summary} />

          {/* Section 2: Carmit Status */}
          <CarmitStatusCard status={data.carmit_status} />

          {/* Section 3: Agent Status Grid */}
          <AgentStatusGrid agents={data.agent_statuses} />

          {/* Section 4: Matches In Progress */}
          <MatchesInProgressSection matches={data.matches_in_progress} />

          {/* Section 5: Job Changes */}
          <JobChangesSection changes={data.recent_job_changes} />

          {/* Section 6: Change Detection Metrics */}
          <ChangeDetectionMetricsSection metrics={data.change_detection_metrics} />
        </div>
      )}
    </div>
  );
};

export default JobMatchStatusDashboard;

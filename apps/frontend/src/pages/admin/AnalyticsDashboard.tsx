import React, { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { agentNameHe } from "@/data/agents";
import {
  LineChart,
  Line,
  BarChart,
  Bar,
  FunnelChart,
  Funnel,
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
import AnalyticsChart from "../../components/AnalyticsChart";

interface KPISummary {
  total_hired: number;
  placement_rate: number;
  pending_matches: number;
  avg_time_to_hire_days: number;
  active_conversations: number;
  failed_matches: number;
  failure_rate: number;
}

interface RecruiterPerformanceMetric {
  recruiter_name: string;
  conversations_count: number;
  approvals_count: number;
  approval_rate: number;
  hires_count: number;
  hire_rate: number;
  avg_days_in_stage: number;
  queue_count: number;
  workload_pct: number;
}

interface MatchFunnel {
  found: number;
  carmit_approved: number;
  sent_to_recruiter: number;
  recruiter_approved: number;
  hired: number;
  failed: number;
  conversion_rate: number;
}

interface TimeToPlacementPoint {
  date: string;
  avg_days: number;
  hires_count: number;
  failed_count: number;
}

interface RejectionReasonMetric {
  rejection_stage: string;
  reason: string;
  count: number;
  percentage: number;
}

interface AgentPerformanceMetric {
  agent_code: string;
  matches_found: number;
  matches_approved: number;
  approval_rate: number;
  placements: number;
  placement_rate: number;
  avg_score: number;
}

// API fetch functions
const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";

const fetchKPISummary = async (period: string): Promise<KPISummary> => {
  const response = await fetch(`${API_BASE}/admin/analytics/kpi-summary?period=${period}`);
  if (!response.ok) throw new Error("Failed to fetch KPI summary");
  return response.json();
};

const fetchRecruiterPerformance = async (
  period: string
): Promise<{ data: RecruiterPerformanceMetric[] }> => {
  const response = await fetch(`${API_BASE}/admin/analytics/recruiter-performance?period=${period}`);
  if (!response.ok) throw new Error("Failed to fetch recruiter performance");
  return response.json();
};

const fetchMatchFunnel = async (period: string): Promise<MatchFunnel> => {
  const response = await fetch(`${API_BASE}/admin/analytics/match-funnel?period=${period}`);
  if (!response.ok) throw new Error("Failed to fetch match funnel");
  return response.json();
};

const fetchTimeToPlacement = async (days: number): Promise<{ data: TimeToPlacementPoint[] }> => {
  const response = await fetch(`${API_BASE}/admin/analytics/time-to-placement?days=${days}`);
  if (!response.ok) throw new Error("Failed to fetch time to placement");
  return response.json();
};

const fetchRejectionReasons = async (period: string): Promise<{ data: RejectionReasonMetric[] }> => {
  const response = await fetch(`${API_BASE}/admin/analytics/rejection-reasons?period=${period}`);
  if (!response.ok) throw new Error("Failed to fetch rejection reasons");
  return response.json();
};

const fetchAgentPerformance = async (): Promise<{ data: AgentPerformanceMetric[] }> => {
  const response = await fetch(`${API_BASE}/admin/analytics/agent-performance`);
  if (!response.ok) throw new Error("Failed to fetch agent performance");
  return response.json();
};

// Chart colors
const COLORS = ["#10b981", "#3b82f6", "#f59e0b", "#ef4444", "#8b5cf6"];

export const AnalyticsDashboard: React.FC = () => {
  const [selectedPeriod, setSelectedPeriod] = useState<"week" | "month" | "quarter" | "year">("month");
  const [expandedSections, setExpandedSections] = useState<Set<string>>(new Set());

  // React Query hooks
  const { data: kpiData } = useQuery({
    queryKey: ["analytics-kpi", selectedPeriod],
    queryFn: () => fetchKPISummary(selectedPeriod),
  });

  const { data: recruiterData } = useQuery({
    queryKey: ["recruiter-performance", selectedPeriod],
    queryFn: () => fetchRecruiterPerformance(selectedPeriod),
  });

  const { data: funnelData } = useQuery({
    queryKey: ["match-funnel", selectedPeriod],
    queryFn: () => fetchMatchFunnel(selectedPeriod),
  });

  const { data: timeToPlacementData } = useQuery({
    queryKey: ["time-to-placement"],
    queryFn: () => fetchTimeToPlacement(selectedPeriod === "year" ? 365 : selectedPeriod === "quarter" ? 90 : selectedPeriod === "week" ? 7 : 30),
  });

  const { data: rejectionData } = useQuery({
    queryKey: ["rejection-reasons", selectedPeriod],
    queryFn: () => fetchRejectionReasons(selectedPeriod),
  });

  const { data: agentData } = useQuery({
    queryKey: ["agent-performance"],
    queryFn: fetchAgentPerformance,
  });

  // Toggle expanded sections
  const toggleSection = (section: string) => {
    const newSet = new Set(expandedSections);
    if (newSet.has(section)) {
      newSet.delete(section);
    } else {
      newSet.add(section);
    }
    setExpandedSections(newSet);
  };

  // Prepare funnel data for Recharts
  const funnelChartData = funnelData
    ? [
        { value: funnelData.found, name: "מצאו" },
        { value: funnelData.carmit_approved, name: "אושרו" },
        { value: funnelData.sent_to_recruiter, name: "למגייסים" },
        { value: funnelData.recruiter_approved, name: "אושרו מגייסים" },
        { value: funnelData.hired, name: "הובאו" },
      ]
    : [];

  return (
    <div dir="rtl" className="min-h-screen bg-gray-900 p-8">
      <div className="max-w-7xl mx-auto">
        {/* Header */}
        <div className="mb-8">
          <h1 className="text-4xl font-bold text-white text-right">דוחות ואנליטיקה</h1>
          <p className="text-gray-400 text-right mt-2">
            ניתוח ביצועים של מגייסים והתאמות
          </p>
        </div>

        {/* Period Selector */}
        <div className="flex gap-2 mb-8 justify-end">
          {["week", "month", "quarter", "year"].map((period) => (
            <button
              key={period}
              onClick={() => setSelectedPeriod(period as any)}
              className={`px-4 py-2 rounded font-semibold transition-colors ${
                selectedPeriod === period
                  ? "bg-blue-600 text-white"
                  : "bg-gray-800 text-gray-300 hover:bg-gray-700"
              }`}
            >
              {period === "week"
                ? "שבוע"
                : period === "month"
                ? "חודש"
                : period === "quarter"
                ? "רבעון"
                : "שנה"}
            </button>
          ))}
        </div>

        {/* KPI Cards Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 mb-8">
          <KPICard
            label="הובאו"
            value={kpiData?.total_hired || 0}
            metric="מועמדים"
            color="bg-green-900"
          />
          <KPICard
            label="שיעור הצבה"
            value={`${((kpiData?.placement_rate || 0) * 100).toFixed(1)}%`}
            metric="מסך ההתאמות"
            color="bg-blue-900"
          />
          <KPICard
            label="ממתינים"
            value={kpiData?.pending_matches || 0}
            metric="התאמות"
            color="bg-yellow-900"
          />
          <KPICard
            label="ימים עד הצבה"
            value={kpiData?.avg_time_to_hire_days.toFixed(1) || "0"}
            metric="בממוצע"
            color="bg-purple-900"
          />
          <KPICard
            label="שיחות פעילות"
            value={kpiData?.active_conversations || 0}
            metric="בתהליך"
            color="bg-cyan-900"
          />
          <KPICard
            label="כישלו"
            value={kpiData?.failed_matches || 0}
            metric="התאמות"
            color="bg-red-900"
          />
        </div>

        {/* Charts Section - 3 columns */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 mb-8">
          {/* Match Funnel */}
          <AnalyticsChart title="משפך התאמות" height={400}>
            {funnelChartData.length > 0 ? (
              <ResponsiveContainer width="100%" height={400}>
                <FunnelChart data={funnelChartData}>
                  <Tooltip />
                  <Funnel
                    dataKey="value"
                    data={funnelChartData}
                    isAnimationActive
                  >
                    {funnelChartData.map((entry, index) => (
                      <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                    ))}
                    <Tooltip />
                  </Funnel>
                </FunnelChart>
              </ResponsiveContainer>
            ) : (
              <div className="text-center text-gray-400 h-96 flex items-center justify-center">
                טוען נתונים...
              </div>
            )}
          </AnalyticsChart>

          {/* Time-to-Placement Line Chart */}
          <AnalyticsChart title="זמן עד הצבה" height={400}>
            {timeToPlacementData?.data && timeToPlacementData.data.length > 0 ? (
              <ResponsiveContainer width="100%" height={400}>
                <LineChart data={timeToPlacementData.data}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#444" />
                  <XAxis dataKey="date" stroke="#999" style={{ fontSize: "12px" }} />
                  <YAxis stroke="#999" style={{ fontSize: "12px" }} />
                  <Tooltip />
                  <Legend />
                  <Line
                    type="monotone"
                    dataKey="avg_days"
                    stroke="#3b82f6"
                    name="ימים ממוצעים"
                    isAnimationActive={true}
                  />
                </LineChart>
              </ResponsiveContainer>
            ) : (
              <div className="text-center text-gray-400 h-96 flex items-center justify-center">
                טוען נתונים...
              </div>
            )}
          </AnalyticsChart>

          {/* Recruiter Comparison Bar Chart */}
          <AnalyticsChart title="השוואת מגייסים" height={400}>
            {recruiterData?.data && recruiterData.data.length > 0 ? (
              <ResponsiveContainer width="100%" height={400}>
                <BarChart data={recruiterData.data}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#444" />
                  <XAxis dataKey="recruiter_name" stroke="#999" style={{ fontSize: "12px" }} />
                  <YAxis stroke="#999" style={{ fontSize: "12px" }} />
                  <Tooltip />
                  <Legend />
                  <Bar dataKey="approval_rate" fill="#10b981" name="שיעור אישור" />
                  <Bar dataKey="hire_rate" fill="#3b82f6" name="שיעור הצבה" />
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <div className="text-center text-gray-400 h-96 flex items-center justify-center">
                טוען נתונים...
              </div>
            )}
          </AnalyticsChart>
        </div>

        {/* Detailed Tables Section */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-8">
          {/* Recruiter Workload Table */}
          <div className="bg-gray-800 rounded-lg border border-gray-700 p-4">
            <h3 className="text-lg font-semibold text-white text-right mb-4">
              עומס עבודה של מגייסים
            </h3>
            <div className="overflow-x-auto">
              <table className="w-full text-sm text-right">
                <thead className="bg-gray-700 text-gray-300">
                  <tr>
                    <th className="px-3 py-2">מגייס</th>
                    <th className="px-3 py-2">בתור</th>
                    <th className="px-3 py-2">שיעור אישור</th>
                    <th className="px-3 py-2">שיעור הצבה</th>
                  </tr>
                </thead>
                <tbody>
                  {recruiterData?.data ? (
                    recruiterData.data.map((recruiter, idx) => (
                      <tr
                        key={recruiter.recruiter_name}
                        className={idx % 2 === 0 ? "bg-gray-800" : "bg-gray-900"}
                      >
                        <td className="px-3 py-2 text-white">
                          {recruiter.recruiter_name === "tal" ? "טל" : "אלד"}
                        </td>
                        <td className="px-3 py-2 text-gray-300">
                          {recruiter.queue_count}
                        </td>
                        <td className="px-3 py-2 text-green-400">
                          {(recruiter.approval_rate * 100).toFixed(1)}%
                        </td>
                        <td className="px-3 py-2 text-blue-400">
                          {(recruiter.hire_rate * 100).toFixed(1)}%
                        </td>
                      </tr>
                    ))
                  ) : (
                    <tr>
                      <td colSpan={4} className="px-3 py-2 text-center text-gray-400">
                        טוען נתונים...
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>

          {/* Agent Performance Table */}
          <div className="bg-gray-800 rounded-lg border border-gray-700 p-4">
            <h3 className="text-lg font-semibold text-white text-right mb-4">
              ביצועי סוכנים
            </h3>
            <div className="overflow-x-auto">
              <table className="w-full text-sm text-right">
                <thead className="bg-gray-700 text-gray-300">
                  <tr>
                    <th className="px-3 py-2">סוכן</th>
                    <th className="px-3 py-2">נמצאו</th>
                    <th className="px-3 py-2">שיעור אישור</th>
                    <th className="px-3 py-2">שיעור הצבה</th>
                  </tr>
                </thead>
                <tbody>
                  {agentData?.data ? (
                    agentData.data.map((agent, idx) => (
                      <tr
                        key={agent.agent_code}
                        className={idx % 2 === 0 ? "bg-gray-800" : "bg-gray-900"}
                      >
                        <td className="px-3 py-2 text-white font-semibold">
                          {agentNameHe(agent.agent_code)}
                        </td>
                        <td className="px-3 py-2 text-gray-300">
                          {agent.matches_found}
                        </td>
                        <td className="px-3 py-2 text-green-400">
                          {(agent.approval_rate * 100).toFixed(1)}%
                        </td>
                        <td className="px-3 py-2 text-blue-400">
                          {(agent.placement_rate * 100).toFixed(1)}%
                        </td>
                      </tr>
                    ))
                  ) : (
                    <tr>
                      <td colSpan={4} className="px-3 py-2 text-center text-gray-400">
                        טוען נתונים...
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </div>

        {/* Rejection Analysis - Collapsible */}
        <div className="bg-gray-800 rounded-lg border border-gray-700 p-4">
          <button
            onClick={() => toggleSection("rejections")}
            className="w-full flex justify-between items-center text-right text-lg font-semibold text-white hover:text-gray-300 transition-colors"
          >
            <span>{expandedSections.has("rejections") ? "▼" : "◀"}</span>
            <span>נתוח סיבות דחייה</span>
          </button>

          {expandedSections.has("rejections") && (
            <div className="mt-4">
              <div className="overflow-x-auto">
                <table className="w-full text-sm text-right">
                  <thead className="bg-gray-700 text-gray-300">
                    <tr>
                      <th className="px-3 py-2">שלב</th>
                      <th className="px-3 py-2">סיבה</th>
                      <th className="px-3 py-2">כמות</th>
                      <th className="px-3 py-2">אחוז</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rejectionData?.data ? (
                      rejectionData.data.map((reason, idx) => (
                        <tr
                          key={`${reason.rejection_stage}-${reason.reason}`}
                          className={idx % 2 === 0 ? "bg-gray-800" : "bg-gray-900"}
                        >
                          <td className="px-3 py-2 text-gray-300">
                            {reason.rejection_stage}
                          </td>
                          <td className="px-3 py-2 text-gray-300">
                            {reason.reason}
                          </td>
                          <td className="px-3 py-2 text-red-400">
                            {reason.count}
                          </td>
                          <td className="px-3 py-2 text-red-400">
                            {reason.percentage.toFixed(1)}%
                          </td>
                        </tr>
                      ))
                    ) : (
                      <tr>
                        <td colSpan={4} className="px-3 py-2 text-center text-gray-400">
                          טוען נתונים...
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default AnalyticsDashboard;

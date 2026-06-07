import { useEffect, useState } from "react";
import { useQuery, useMutation } from "@tanstack/react-query";
import { env } from "@/lib/env";
import { agentNameHe } from "@/data/agents";

interface AgentStatus {
  agent_code: string;
  agent_name: string;
  status: string;
  current_task_description: string;
  matches_found_today: number;
  matches_found_this_week: number;
  last_active_at: string;
  next_scheduled_at: string;
}

interface Match {
  id: string;
  candidate_name: string;
  job_title: string;
  match_score: number;
  matched_by_agent_code: string;
  current_state: string;
  created_at: string;
}

const AGENTS = [
  { code: "naama", name: "נעמה", domain: "Software" },
  { code: "alik", name: "אליק", domain: "Electronics" },
  { code: "dganit", name: "דגנית", domain: "QA & Testing" },
  { code: "ofir", name: "אופיר", domain: "Systems & DevOps" },
  { code: "itai", name: "איתי", domain: "IT & Infrastructure" },
  { code: "lior", name: "ליאור", domain: "Mechanical" },
  { code: "gc", name: "כללי", domain: "General/Catch-all" },
  { code: "mani", name: "מני", domain: "Security Clearance (Level 1)" },
];

export function AgentManagementPage() {
  const [selectedAgent, setSelectedAgent] = useState<string>("all");
  const [filterState, setFilterState] = useState<string>("all");

  // Fetch agent status
  const { data: agentStats } = useQuery({
    queryKey: ["agent-stats"],
    queryFn: () =>
      fetch(`${env.API_BASE_URL}/admin/agents`).then(r => r.json()),
    refetchInterval: 10000, // Refresh every 10 seconds
  });

  // Fetch recent matches
  const { data: matches } = useQuery({
    queryKey: ["recent-matches", selectedAgent, filterState],
    queryFn: () => {
      const params = new URLSearchParams();
      if (selectedAgent !== "all") params.append("agent", selectedAgent);
      if (filterState !== "all") params.append("state", filterState);
      return fetch(
        `${env.API_BASE_URL}/admin/matches/recent?${params.toString()}`
      ).then(r => r.json());
    },
    refetchInterval: 5000,
  });

  // Trigger manual matching
  const triggerMatchMutation = useMutation({
    mutationFn: (agentCode: string) =>
      fetch(`${env.API_BASE_URL}/admin/agents/${agentCode}/match-now`, {
        method: "POST",
      }).then(r => r.json()),
    onSuccess: () => {
      // Refetch stats
      agentStats && agentStats.refetch && agentStats.refetch();
    },
  });

  const filteredMatches = (matches?.data || []).filter((match: Match) => {
    if (selectedAgent !== "all" && match.matched_by_agent_code !== selectedAgent)
      return false;
    if (filterState !== "all" && match.current_state !== filterState) return false;
    return true;
  });

  return (
    <div className="p-8 max-w-7xl mx-auto bg-gray-900 min-h-screen" dir="rtl">
      <div className="mb-8">
        <h1 className="text-3xl font-bold mb-2 text-white">ניהול סוכני גיוס</h1>
        <p className="text-white">
          ניהול 7 סוכנים מיוחדים לגיוס מועמדים לתפקידים
        </p>
      </div>

      {/* Agent Status Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-7 gap-3 mb-8">
        {AGENTS.map((agent) => {
          const stats = agentStats?.data?.find(
            (s: AgentStatus) => s.agent_code === agent.code
          );
          return (
            <div
              key={agent.code}
              onClick={() => setSelectedAgent(agent.code)}
              className={`p-4 rounded-lg border-2 cursor-pointer transition ${
                selectedAgent === agent.code
                  ? "bg-blue-900 border-blue-400"
                  : "bg-gray-800 border-gray-700 hover:border-blue-400"
              }`}
            >
              <div className="text-sm font-bold text-white mb-1">{agent.name}</div>
              <div className="text-xs text-gray-400 mb-2">{agent.domain}</div>
              <div className="flex items-center gap-2 mb-2">
                <div className={`w-2 h-2 rounded-full ${stats?.status === "active" ? "bg-green-500" : "bg-gray-500"}`} />
                <span className="text-xs text-white">
                  {stats?.matches_found_today || 0} היום
                </span>
              </div>
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  triggerMatchMutation.mutate(agent.code);
                }}
                disabled={triggerMatchMutation.isPending}
                className="w-full px-2 py-1 text-xs bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50"
              >
                הרץ עכשיו
              </button>
            </div>
          );
        })}
      </div>

      {/* Filter Bar */}
      <div className="mb-6 flex gap-2 flex-wrap">
        <button
          onClick={() => setFilterState("all")}
          className={`px-3 py-1 rounded text-sm font-semibold ${
            filterState === "all"
              ? "bg-blue-600 text-white"
              : "bg-gray-700 text-gray-300 hover:bg-gray-600"
          }`}
        >
          כל המצבים
        </button>
        {["found", "carmit_review", "tal_conversation", "elad_sent"].map((state) => (
          <button
            key={state}
            onClick={() => setFilterState(state)}
            className={`px-3 py-1 rounded text-sm font-semibold ${
              filterState === state
                ? "bg-blue-600 text-white"
                : "bg-gray-700 text-gray-300 hover:bg-gray-600"
            }`}
          >
            {state === "found" && "נמצא"}
            {state === "carmit_review" && "בדיקת כרמית"}
            {state === "tal_conversation" && "שיחת Tal"}
            {state === "elad_sent" && "נשלח ל-Elad"}
          </button>
        ))}
      </div>

      {/* All Agents Summary */}
      <div className="bg-gray-800 p-6 rounded-lg border border-gray-700 mb-8">
        <h2 className="text-lg font-semibold mb-4 text-white">סיכום סוכנים</h2>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div className="bg-gray-700 p-3 rounded">
            <div className="text-xs text-gray-400">סה"כ התאמות היום</div>
            <div className="text-2xl font-bold text-white">
              {agentStats?.data?.reduce((sum: number, s: AgentStatus) => sum + (s.matches_found_today || 0), 0) || 0}
            </div>
          </div>
          <div className="bg-gray-700 p-3 rounded">
            <div className="text-xs text-gray-400">סה"כ השבוע</div>
            <div className="text-2xl font-bold text-white">
              {agentStats?.data?.reduce((sum: number, s: AgentStatus) => sum + (s.matches_found_this_week || 0), 0) || 0}
            </div>
          </div>
          <div className="bg-gray-700 p-3 rounded">
            <div className="text-xs text-gray-400">סוכנים פעילים</div>
            <div className="text-2xl font-bold text-white">
              {agentStats?.data?.filter((s: AgentStatus) => s.status === "active").length || 0}
            </div>
          </div>
          <div className="bg-gray-700 p-3 rounded">
            <div className="text-xs text-gray-400">התאמות ממתינות</div>
            <div className="text-2xl font-bold text-white">
              {filteredMatches.filter((m: Match) => m.current_state === "found").length}
            </div>
          </div>
        </div>
      </div>

      {/* Recent Matches Table */}
      <div className="bg-white p-6 rounded-lg border">
        <h2 className="text-lg font-semibold mb-4">התאמות אחרונות</h2>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b bg-gray-50">
                <th className="text-left py-3 px-3">מועמד</th>
                <th className="text-left py-3 px-3">תפקיד</th>
                <th className="text-center py-3 px-3">סוכן</th>
                <th className="text-center py-3 px-3">ציון</th>
                <th className="text-center py-3 px-3">מצב</th>
                <th className="text-left py-3 px-3">תאריך</th>
              </tr>
            </thead>
            <tbody>
              {filteredMatches.length === 0 ? (
                <tr>
                  <td colSpan={6} className="text-center py-4 text-gray-500">
                    לא נמצאו התאמות
                  </td>
                </tr>
              ) : (
                filteredMatches.map((match: Match) => (
                  <tr key={match.id} className="border-b hover:bg-gray-50">
                    <td className="py-3 px-3 font-semibold text-gray-900">
                      {match.candidate_name}
                    </td>
                    <td className="py-3 px-3 text-gray-700">{match.job_title}</td>
                    <td className="py-3 px-3 text-center text-xs font-semibold">
                      {agentNameHe(match.matched_by_agent_code)}
                    </td>
                    <td className="py-3 px-3 text-center">
                      <div className="flex items-center gap-2 justify-center">
                        <div className="w-20 bg-gray-200 rounded h-2">
                          <div
                            className="bg-blue-600 h-full rounded"
                            style={{
                              width: `${match.match_score * 100}%`,
                            }}
                          />
                        </div>
                        <span className="text-xs font-mono">
                          {(match.match_score * 100).toFixed(0)}%
                        </span>
                      </div>
                    </td>
                    <td className="py-3 px-3 text-center">
                      <span className="px-2 py-1 text-xs rounded bg-blue-100 text-blue-700">
                        {match.current_state === "found" && "נמצא"}
                        {match.current_state === "carmit_review" && "כרמית"}
                        {match.current_state === "tal_conversation" && "Tal"}
                        {match.current_state === "elad_sent" && "Elad"}
                      </span>
                    </td>
                    <td className="py-3 px-3 text-xs text-gray-500">
                      {new Date(match.created_at).toLocaleDateString()}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

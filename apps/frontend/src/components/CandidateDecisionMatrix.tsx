/**
 * Candidate Decision Matrix
 * Shows all candidates that were evaluated with their match reasoning
 */

import { useState, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchAllCandidateMatches, type CandidateMatch } from "@/api/recruiter";
import { GeoMismatchBadge } from "@/components/GeoMismatchBadge";

const STATE_COLORS: Record<string, string> = {
  found: "bg-yellow-900",
  evaluated_but_rejected: "bg-gray-700",
  carmit_approved: "bg-green-900",
  carmit_rejected: "bg-red-900",
  sent_to_tal: "bg-blue-900",
  tal_conversation: "bg-indigo-900",
  tal_approved: "bg-green-700",
  tal_rejected: "bg-red-700",
};

const STATE_LABELS: Record<string, string> = {
  found: "🔍 התאמה (לבדיקת כרמית)",
  evaluated_but_rejected: "⚪ נבדק — לא התאים (<70)",
  carmit_approved: "✅ אושר ע״י כרמית",
  carmit_rejected: "❌ נדחה ע״י כרמית",
  sent_to_tal: "💬 טל",
  tal_conversation: "🗣️ בשיחה",
  tal_approved: "✓ אושר",
  tal_rejected: "✕ דחה",
};

const AGENT_NAMES: Record<string, string> = {
  naama: "נעמה",
  alik: "אליק",
  dganit: "דגנית",
  ofir: "אופיר",
  itai: "איתי",
  lior: "ליאור",
  gc: "כללי",
  mani: "מני",
};

interface Props {
  showTitle?: boolean;
  agentCode?: string; // If set, show only candidates evaluated by this agent
}

export function CandidateDecisionMatrix({ showTitle = true, agentCode }: Props) {
  const [selectedJobId, setSelectedJobId] = useState<string>("");
  const [expandedRows, setExpandedRows] = useState<Set<string>>(new Set());
  const [sortCol, setSortCol] = useState<"candidate" | "job" | "score">("score");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");

  const handleSort = (col: "candidate" | "job" | "score") => {
    if (sortCol === col) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortCol(col);
      setSortDir(col === "score" ? "desc" : "asc");
    }
  };

  const { data, isLoading, error } = useQuery({
    queryKey: ["candidate-decision-matrix", selectedJobId, agentCode],
    queryFn: () => fetchAllCandidateMatches(selectedJobId || undefined, agentCode, 500, 1),
    refetchInterval: 60000, // Refresh every minute
  });

  if (error) {
    return (
      <div className="bg-red-900/20 border border-red-700 rounded-lg p-4 text-red-200">
        שגיאה בטעינת הנתונים: {String((error as Error).message)}
      </div>
    );
  }

  const rawMatches = data?.matches || [];
  const jobs = data?.jobs || [];

  const matches = useMemo(() => {
    const sorted = [...rawMatches];
    const dir = sortDir === "asc" ? 1 : -1;
    sorted.sort((a, b) => {
      let cmp = 0;
      if (sortCol === "score") {
        cmp = (a.matchScore || 0) - (b.matchScore || 0);
      } else if (sortCol === "candidate") {
        cmp = (a.candidateName || "").localeCompare(b.candidateName || "", "he");
      } else if (sortCol === "job") {
        cmp = (a.jobTitle || "").localeCompare(b.jobTitle || "", "he");
      }
      return cmp * dir;
    });
    return sorted;
  }, [rawMatches, sortCol, sortDir]);

  const toggleRow = (matchId: string) => {
    const newExpanded = new Set(expandedRows);
    if (newExpanded.has(matchId)) {
      newExpanded.delete(matchId);
    } else {
      newExpanded.add(matchId);
    }
    setExpandedRows(newExpanded);
  };

  return (
    <div className="space-y-4" dir="rtl">
      {showTitle && (
        <div>
          <h2 className="text-2xl font-bold text-white">📋 מטריצת החלטות מועמדים</h2>
          <p className="text-sm text-gray-400">
            כל המועמדים שנבחנו עם תיאור התאמה / אי-התאמה לכל משרה
          </p>
        </div>
      )}

      {/* Job Filter */}
      <div className="flex items-center gap-4">
        <label className="text-sm text-gray-400">סנן לפי משרה:</label>
        <select
          value={selectedJobId}
          onChange={(e) => setSelectedJobId(e.target.value)}
          className="px-4 py-2 rounded bg-gray-800 text-white border border-gray-700 focus:border-blue-500 outline-none"
        >
          <option value="">🔄 כל המשרות ({matches.length} התאמות)</option>
          {jobs.map((job) => (
            <option key={job.id} value={job.id}>
              {job.title}
            </option>
          ))}
        </select>
      </div>

      {/* Loading state */}
      {isLoading ? (
        <div className="text-gray-400 text-center py-8">טוען...</div>
      ) : matches.length === 0 ? (
        <div className="bg-gray-800 border border-gray-700 rounded-lg p-8 text-center text-gray-400">
          אין התאמות להצגה
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-right text-sm bg-gray-800 rounded-lg border border-gray-700">
            <thead className="bg-gray-700 border-b border-gray-600">
              <tr>
                <th className="px-4 py-3 font-semibold text-gray-200 text-right">
                  <button
                    onClick={() => handleSort("candidate")}
                    className="flex items-center gap-1 hover:text-white transition"
                  >
                    מועמד
                    <span className="text-xs">
                      {sortCol === "candidate" ? (sortDir === "asc" ? "▲" : "▼") : "⇅"}
                    </span>
                  </button>
                </th>
                <th className="px-4 py-3 font-semibold text-gray-200 text-right">
                  <button
                    onClick={() => handleSort("job")}
                    className="flex items-center gap-1 hover:text-white transition"
                  >
                    משרה
                    <span className="text-xs">
                      {sortCol === "job" ? (sortDir === "asc" ? "▲" : "▼") : "⇅"}
                    </span>
                  </button>
                </th>
                <th className="px-4 py-3 font-semibold text-gray-200 text-right">שם לקוח</th>
                <th className="px-4 py-3 font-semibold text-gray-200 text-right">מספר משרה</th>
                <th className="px-4 py-3 font-semibold text-gray-200 text-right">סוכן</th>
                <th className="px-4 py-3 font-semibold text-gray-200 text-right">
                  <button
                    onClick={() => handleSort("score")}
                    className="flex items-center gap-1 hover:text-white transition"
                  >
                    ציון
                    <span className="text-xs">
                      {sortCol === "score" ? (sortDir === "asc" ? "▲" : "▼") : "⇅"}
                    </span>
                  </button>
                </th>
                <th className="px-4 py-3 font-semibold text-gray-200 text-right">מצב</th>
                <th className="px-4 py-3 font-semibold text-gray-200 text-right">תאריך</th>
                <th className="px-4 py-3 font-semibold text-gray-200 text-center">📝</th>
              </tr>
            </thead>
            {matches.map((match: CandidateMatch, idx: number) => {
                const isExpanded = expandedRows.has(match.id);
                const agentName = AGENT_NAMES[match.matchedByAgentCode] || match.matchedByAgentCode;
                const stateColor = STATE_COLORS[match.currentState] || "bg-gray-700";
                const stateLabel = STATE_LABELS[match.currentState] || match.currentState;

                return (
                  <tbody key={match.id}>
                    <tr className="border-b border-gray-700 hover:bg-gray-750 transition">
                      <td className="px-4 py-3 text-white font-semibold">{match.candidateName}</td>
                      <td className="px-4 py-3 text-gray-300">
                        <div className="flex flex-col gap-1.5">
                          <span>{match.jobTitle}</span>
                          <GeoMismatchBadge
                            mismatch={match.geographicMismatch}
                            reason={match.geographicMismatchReason}
                          />
                        </div>
                      </td>
                      <td className="px-4 py-3 text-gray-300">{match.organizationName || "—"}</td>
                      <td className="px-4 py-3 text-gray-400 font-mono">{match.pipedriveDealId ?? "—"}</td>
                      <td className="px-4 py-3 text-gray-300">{agentName}</td>
                      <td className="px-4 py-3 text-gray-300">
                        {Math.round((match.matchScore || 0) * 100)}%
                      </td>
                      <td className="px-4 py-3">
                        <span className={`px-2 py-1 rounded text-xs font-semibold text-white ${stateColor}`}>
                          {stateLabel}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-gray-400 text-xs">
                        {new Date(match.createdAt).toLocaleDateString("he-IL")}
                      </td>
                      <td className="px-4 py-3 text-center">
                        <button
                          onClick={() => toggleRow(match.id)}
                          className={`px-2 py-1 rounded text-sm transition ${
                            isExpanded
                              ? "bg-blue-700 text-white"
                              : "bg-gray-700 text-gray-300 hover:bg-gray-600"
                          }`}
                        >
                          {isExpanded ? "▼" : "▶"}
                        </button>
                      </td>
                    </tr>

                    {/* Expanded reasoning row */}
                    {isExpanded && (match.matchReasoning || match.geographicMismatch) && (
                      <tr className="bg-gray-750 border-b border-gray-700">
                        <td colSpan={9} className="px-4 py-4">
                          <div className="bg-gray-900 rounded p-4 border border-gray-600 space-y-3">
                            {match.geographicMismatch && (
                              <div className="flex items-start gap-2 text-sm text-red-300 font-semibold">
                                <span>📍 אין התאמה גיאוגרפית:</span>
                                <span className="font-normal">
                                  {match.geographicMismatchReason ||
                                    "המועמד אינו נמצא במיקום גיאוגרפי מתאים למשרה"}
                                </span>
                              </div>
                            )}
                            {match.matchReasoning && (
                              <p className="text-sm text-gray-300 leading-relaxed whitespace-pre-wrap">
                                {match.matchReasoning}
                              </p>
                            )}
                          </div>
                        </td>
                      </tr>
                    )}
                  </tbody>
                );
              })}
          </table>
        </div>
      )}

      {/* Summary */}
      {matches.length > 0 && (
        <div className="grid grid-cols-2 md:grid-cols-5 gap-3 text-sm bg-gray-800 rounded-lg p-4">
          <div>
            <span className="text-gray-400">סה״כ נבדקו:</span>
            <p className="text-xl font-bold text-white">{data?.total || 0}</p>
          </div>
          <div>
            <span className="text-gray-400">התאמות (≥70):</span>
            <p className="text-xl font-bold text-green-400">
              {matches.filter((m) => m.matchScore >= 0.7).length}
            </p>
          </div>
          <div>
            <span className="text-gray-400">נבדקו ולא התאימו:</span>
            <p className="text-xl font-bold text-gray-400">
              {matches.filter((m) => m.currentState === "evaluated_but_rejected").length}
            </p>
          </div>
          <div>
            <span className="text-gray-400">אושרו ע״י כרמית:</span>
            <p className="text-xl font-bold text-green-400">
              {matches.filter((m) => m.currentState === "carmit_approved").length}
            </p>
          </div>
          <div>
            <span className="text-gray-400">נדחו ע״י כרמית:</span>
            <p className="text-xl font-bold text-red-400">
              {matches.filter((m) => m.currentState === "carmit_rejected").length}
            </p>
          </div>
        </div>
      )}
    </div>
  );
}

export default CandidateDecisionMatrix;

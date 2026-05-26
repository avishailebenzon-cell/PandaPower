import { useEffect, useState } from "react";
import { useQuery, useMutation } from "@tanstack/react-query";
import { supabase } from "@/lib/supabase";
import { env } from "@/lib/env";

interface CandidateStats {
  total_candidates: number;
  candidates_with_parsed_cvs: number;
  candidates_with_normalized_skills: number;
  avg_skills_per_candidate: number;
}

interface Candidate {
  id: string;
  name: string;
  candidate_number: string;
  detected_language: string | null;
  key_skills: string[] | null;
  normalized_skills_count: number;
  confidence_score: number | null;
  created_at: string;
}

interface CandidateDetails {
  candidate_id: string;
  candidate_name: string;
  language: string;
  total_skills: number;
  normalized_skills: Array<{
    skill_name: string;
    skill_category: string;
    raw_skill_text: string;
    confidence_score: number;
    proficiency_level: string | null;
    years_of_experience: number | null;
  }>;
}

export function CandidateManagementPage() {
  const [selectedCandidate, setSelectedCandidate] = useState<CandidateDetails | null>(null);
  const [showDetailsModal, setShowDetailsModal] = useState(false);
  const [liveEvents, setLiveEvents] = useState<Candidate[]>([]);
  const [filterLanguage, setFilterLanguage] = useState<string>("all");

  // Fetch candidate statistics
  const { data: stats, refetch: refetchStats } = useQuery({
    queryKey: ["candidate-stats"],
    queryFn: () =>
      fetch(`${env.API_BASE_URL}/admin/candidates/stats`).then(r => r.json()),
    refetchInterval: 5000,
  });

  // Fetch candidate list
  const { data: candidates, refetch: refetchCandidates } = useQuery({
    queryKey: ["candidates-list"],
    queryFn: () =>
      fetch(`${env.API_BASE_URL}/admin/candidates/list?limit=100`).then(r => r.json()),
    refetchInterval: 10000,
  });

  // Manual trigger mutation
  const runNowMutation = useMutation({
    mutationFn: () =>
      fetch(`${env.API_BASE_URL}/admin/candidates/run-now`, { method: "POST" }).then(r => r.json()),
    onSuccess: () => {
      refetchStats();
      refetchCandidates();
    },
  });

  // צפה details mutation
  const viewDetailsMutation = useMutation({
    mutationFn: (candidateId: string) =>
      fetch(`${env.API_BASE_URL}/admin/candidates/${candidateId}`).then(r => r.json()),
    onSuccess: (data) => {
      setSelectedCandidate(data);
      setShowDetailsModal(true);
    },
  });

  // Subscribe to candidate changes
  useEffect(() => {
    const channel = supabase
      .channel("candidate-updates")
      .on(
        "postgres_changes",
        { event: "INSERT", schema: "public", table: "candidates" },
        (payload) => {
          const newCandidate = payload.new;
          setLiveEvents((prev) => [
            {
              id: newCandidate.id,
              name: newCandidate.name,
              detected_language: newCandidate.detected_language,
              key_skills: newCandidate.key_skills,
              normalized_skills_count: 0,
              confidence_score: null,
              created_at: newCandidate.created_at,
            },
            ...prev,
          ].slice(0, 5));
        }
      )
      .subscribe();

    return () => {
      channel.unsubscribe();
    };
  }, []);

  const filteredCandidates = candidates?.data?.filter((c: Candidate) => {
    if (filterLanguage === "all") return true;
    return c.detected_language === filterLanguage;
  }) || [];

  const languageCounts = candidates?.data?.reduce((acc: Record<string, number>, c: Candidate) => {
    const lang = c.detected_language || "unknown";
    acc[lang] = (acc[lang] || 0) + 1;
    return acc;
  }, {}) || {};

  return (
    <div className="p-8 max-w-7xl mx-auto bg-gray-900 min-h-screen" dir="rtl">
      <div className="mb-8">
        <h1 className="text-3xl font-bold mb-2 text-white">ניהול מועמדים</h1>
        <p className="text-white">ניהול מועמדים שנוצרו מ-CVs מנותחים עם כישורים מנורמלים</p>
      </div>

      {/* Status Cards */}
      <div className="grid grid-cols-4 gap-4 mb-8">
        <div className="bg-blue-50 p-4 rounded-lg border border-blue-200">
          <div className="text-xs text-blue-600 font-semibold">סה"כ מועמדים</div>
          <div className="text-3xl font-bold text-blue-700">{stats?.total_candidates || 0}</div>
        </div>
        <div className="bg-purple-50 p-4 rounded-lg border border-purple-200">
          <div className="text-xs text-purple-600 font-semibold">עם CVs מפוענחים</div>
          <div className="text-3xl font-bold text-purple-700">{stats?.candidates_with_parsed_cvs || 0}</div>
        </div>
        <div className="bg-green-50 p-4 rounded-lg border border-green-200">
          <div className="text-xs text-green-600 font-semibold">עם כישורים</div>
          <div className="text-3xl font-bold text-green-700">{stats?.candidates_with_normalized_skills || 0}</div>
        </div>
        <div className="bg-gray-50 p-4 rounded-lg border border-gray-200">
          <div className="text-xs text-gray-600 font-semibold">ממוצע כישורים</div>
          <div className="text-3xl font-bold text-gray-700">{stats?.avg_skills_per_candidate?.toFixed(1) || 0}</div>
        </div>
      </div>

      {/* Metrics */}
      <div className="grid grid-cols-2 gap-4 mb-8">
        <div className="bg-gray-800 p-4 rounded-lg border border-gray-700">
          <div className="text-xs text-white mb-2">התפלגות שפה</div>
          <div className="space-y-1 text-sm">
            {Object.entries(languageCounts).map(([lang, count]) => (
              <div key={lang} className="flex justify-between">
                <span className="text-white">{lang.toUpperCase()}</span>
                <span className="font-semibold text-white">{count}</span>
              </div>
            ))}
          </div>
        </div>
        <div className="bg-gray-800 p-4 rounded-lg border border-gray-700">
          <div className="text-xs text-white mb-1">לוח זמנים</div>
          <div className="text-sm font-mono text-white">כל 10 דקות</div>
          <div className="text-xs text-white mt-2">גודל אצווה: 20 מועמדים לכל הרצה</div>
        </div>
      </div>

      {/* Run Now Button */}
      <div className="mb-8">
        <button
          onClick={() => runNowMutation.mutate()}
          disabled={runNowMutation.isPending}
          className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 font-semibold"
        >
          {runNowMutation.isPending ? "מעבד..." : "הפעל עכשיו"}
        </button>
      </div>

      {/* Live Events */}
      <div className="bg-gray-800 p-6 rounded-lg border border-gray-700 mb-8">
        <h2 className="text-lg font-semibold mb-4 text-white">מועמדים חדשים</h2>
        <div className="space-y-2">
          {liveEvents.length === 0 ? (
            <div className="text-sm text-white py-4">מחכה למועמדים חדשים...</div>
          ) : (
            liveEvents.map((event) => (
              <div
                key={event.id}
                className="flex items-center p-3 rounded text-sm gap-4 bg-blue-900 border border-blue-700"
              >
                <span className="font-bold text-lg w-6 text-blue-400">✓</span>
                <div className="flex-1">
                  <div className="font-semibold text-white">{event.name}</div>
                  <div className="text-xs text-white">
                    {event.key_skills?.length || 0} כישורים גולמיים
                  </div>
                </div>
                {event.detected_language && (
                  <span className="text-xs px-2 py-1 bg-white rounded">
                    {event.detected_language.toUpperCase()}
                  </span>
                )}
              </div>
            ))
          )}
        </div>
      </div>

      {/* Filter */}
      <div className="mb-4 flex gap-2">
        <button
          onClick={() => setFilterLanguage("all")}
          className={`px-3 py-1 rounded text-sm font-semibold ${
            filterLanguage === "all"
              ? "bg-blue-600 text-white"
              : "bg-gray-200 text-gray-700 hover:bg-gray-300"
          }`}
        >
          All
        </button>
        {Object.keys(languageCounts).map((lang) => (
          <button
            key={lang}
            onClick={() => setFilterLanguage(lang)}
            className={`px-3 py-1 rounded text-sm font-semibold ${
              filterLanguage === lang
                ? "bg-blue-600 text-white"
                : "bg-gray-200 text-gray-700 hover:bg-gray-300"
            }`}
          >
            {lang.toUpperCase()} ({languageCounts[lang]})
          </button>
        ))}
      </div>

      {/* מועמדים Table */}
      <div className="bg-white p-6 rounded-lg border">
        <h2 className="text-lg font-semibold mb-4">מועמדים</h2>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b bg-gray-50">
                <th className="text-left py-3 px-3">מס' מועמד</th>
                <th className="text-left py-3 px-3">שם</th>
                <th className="text-left py-3 px-3">שפה</th>
                <th className="text-center py-3 px-3">כישורים גולמיים</th>
                <th className="text-center py-3 px-3">כישורים מנורמלים</th>
                <th className="text-center py-3 px-3">ביטחון</th>
                <th className="text-left py-3 px-3">נוצר</th>
                <th className="text-center py-3 px-3">פעולות</th>
              </tr>
            </thead>
            <tbody>
              {filteredCandidates.length === 0 ? (
                <tr>
                  <td colSpan={8} className="text-center py-4 text-gray-500 text-sm">
                    לא נמצאו מועמדים
                  </td>
                </tr>
              ) : (
                filteredCandidates.map((candidate: Candidate) => (
                  <tr key={candidate.id} className="border-b hover:bg-gray-50">
                    <td className="py-3 px-3 font-mono font-bold text-blue-600">
                      <span className="bg-blue-100 px-2 py-1 rounded text-xs">
                        {candidate.candidate_number}
                      </span>
                    </td>
                    <td className="py-3 px-3 font-semibold text-gray-900">
                      {candidate.name}
                    </td>
                    <td className="py-3 px-3 text-xs">
                      <span className="px-2 py-1 bg-gray-100 rounded">
                        {candidate.detected_language?.toUpperCase() || "unknown"}
                      </span>
                    </td>
                    <td className="py-3 px-3 text-center font-mono text-xs">
                      {candidate.key_skills?.length || 0}
                    </td>
                    <td className="py-3 px-3 text-center font-mono text-xs">
                      {candidate.normalized_skills_count}
                    </td>
                    <td className="py-3 px-3 text-center">
                      {candidate.confidence_score ? (
                        <div className="flex items-center gap-2 justify-center">
                          <div className="w-20 bg-gray-200 rounded h-2">
                            <div
                              className="bg-green-600 h-full rounded"
                              style={{ width: `${candidate.confidence_score * 100}%` }}
                            />
                          </div>
                          <span className="text-xs font-mono w-12">
                            {(candidate.confidence_score * 100).toFixed(0)}%
                          </span>
                        </div>
                      ) : (
                        <span className="text-gray-400">—</span>
                      )}
                    </td>
                    <td className="py-3 px-3 text-xs text-gray-500">
                      {new Date(candidate.created_at).toLocaleDateString()}
                    </td>
                    <td className="py-3 px-3 text-center">
                      <button
                        onClick={() => viewDetailsMutation.mutate(candidate.id)}
                        className="text-xs px-2 py-1 bg-blue-100 text-blue-700 rounded hover:bg-blue-200"
                      >
                        צפה
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Details Modal */}
      {showDetailsModal && selectedCandidate && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-lg max-w-2xl max-h-96 overflow-y-auto p-6">
            <div className="flex justify-between items-center mb-4">
              <h3 className="text-lg font-bold">{selectedCandidate.candidate_name}</h3>
              <button
                onClick={() => setShowDetailsModal(false)}
                className="text-gray-500 hover:text-gray-700 text-xl"
              >
                ✕
              </button>
            </div>

            <div className="space-y-4 text-sm">
              <div className="grid grid-cols-2 gap-4 text-xs">
                <div>
                  <span className="text-gray-600">שפה:</span>{" "}
                  <span className="font-mono font-semibold">{selectedCandidate.language.toUpperCase()}</span>
                </div>
                <div>
                  <span className="text-gray-600">Total Skills:</span>{" "}
                  <span className="font-mono font-semibold">{selectedCandidate.total_skills}</span>
                </div>
              </div>

              <div>
                <h4 className="font-semibold mb-2">כישורים מנורמלים</h4>
                <div className="space-y-2 text-xs max-h-48 overflow-y-auto">
                  {selectedCandidate.normalized_skills.length === 0 ? (
                    <div className="text-gray-500">עדיין אין כישורים מנורמלים</div>
                  ) : (
                    selectedCandidate.normalized_skills.map((skill, idx) => (
                      <div key={idx} className="bg-gray-50 p-2 rounded border">
                        <div className="flex justify-between items-start">
                          <div>
                            <div className="font-semibold text-gray-900">{skill.skill_name}</div>
                            <div className="text-gray-600">{skill.skill_category}</div>
                            <div className="text-gray-500 italic">{skill.raw_skill_text}</div>
                          </div>
                          <div className="text-right">
                            <div className="font-mono">
                              {(skill.confidence_score * 100).toFixed(0)}%
                            </div>
                            {skill.proficiency_level && (
                              <div className="text-gray-600">{skill.proficiency_level}</div>
                            )}
                            {skill.years_of_experience && (
                              <div className="text-gray-600">{skill.years_of_experience}y</div>
                            )}
                          </div>
                        </div>
                      </div>
                    ))
                  )}
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

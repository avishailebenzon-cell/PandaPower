import { useEffect, useState } from "react";
import { useQuery, useMutation } from "@tanstack/react-query";
import { supabase } from "@/lib/supabase";
import { env } from "@/lib/env";

interface CVסטטוס {
  pending: number;
  parsing: number;
  success: number;
  failed: number;
}

interface CVLog {
  cv_file_id: string;
  original_filename: string;
  parse_status: string;
  parse_duration_ms: number | null;
  detected_language: string | null;
  llm_tokens_used: number | null;
  parse_error: string | null;
}

interface CVResult {
  cv_file_id: string;
  original_filename: string;
  parse_status: string;
  detected_language: string | null;
  extraction_method: string | null;
  raw_text_length: number | null;
  llm_tokens_used: number | null;
  parse_duration_ms: number | null;
  extracted_fields: Record<string, any> | null;
  confidence_scores: Record<string, number> | null;
  extraction_notes: string | null;
}

// Maps every field Claude extracts → the DB column it lands in.
// Used in the modal so users can see exactly where each piece of data is stored.
const FIELD_TO_DB_COLUMN: Record<string, string> = {
  name: "candidates.name",
  full_name: "candidates.name",
  email: "candidates.email",
  phone: "candidates.phone",
  location: "candidates.location",
  city: "candidates.location",
  address: "candidates.location",
  summary: "candidates.summary",
  about: "candidates.summary",
  skills: "candidates.key_skills (+ candidate_skills via normalization)",
  technologies: "candidates.key_skills",
  experience: "candidates.experience_years",
  experience_years: "candidates.experience_years",
  years_of_experience: "candidates.experience_years",
  education: "candidates.education",
  degree: "candidates.education",
  languages: "candidates.languages",
  current_position: "candidates.current_position",
  current_title: "candidates.current_position",
  current_company: "candidates.current_company",
  position: "candidates.current_position",
  title: "candidates.current_position",
  company: "candidates.current_company",
  linkedin: "candidates.linkedin_url",
  linkedin_url: "candidates.linkedin_url",
  security_clearance: "candidates.clearance_level",
  clearance: "candidates.clearance_level",
  clearance_level: "candidates.clearance_level",
  geographical_location: "candidates.geographical_location",
  university_1st_degree: "candidates.university_1st_degree",
  university_2nd_degree: "candidates.university_2nd_degree",
  university_3rd_degree: "candidates.university_3rd_degree",
  certifications: "candidates.certifications",
  awards: "candidates.awards",
  publications: "candidates.publications",
  projects: "candidates.projects",
  references: "candidates.references",
  hobbies: "candidates.hobbies",
  birth_date: "candidates.birth_date",
  date_of_birth: "candidates.birth_date",
  gender: "candidates.gender",
  nationality: "candidates.nationality",
  marital_status: "candidates.marital_status",
  military_service: "candidates.military_service",
  driver_license: "candidates.driver_license",
};

function formatFieldValue(value: any): string {
  if (value === null || value === undefined) return "—";
  if (Array.isArray(value)) {
    if (value.length === 0) return "[]";
    // Pretty-print arrays of strings with bullets, arrays of objects as JSON
    if (typeof value[0] === "string") return value.map((v) => `• ${v}`).join("\n");
    return JSON.stringify(value, null, 2);
  }
  if (typeof value === "object") return JSON.stringify(value, null, 2);
  return String(value);
}

export function CVParsingPage() {
  const [selectedResult, setSelectedResult] = useState<CVResult | null>(null);
  const [showResultModal, setShowResultModal] = useState(false);
  const [liveEvents, setLiveEvents] = useState<CVLog[]>([]);
  const [signedUrl, setSignedUrl] = useState<string | null>(null);
  const [signedUrlLoading, setSignedUrlLoading] = useState(false);

  // Fetch CV parsing status
  const { data: status, refetch: refetchStatus } = useQuery({
    queryKey: ["cv-status"],
    queryFn: () =>
      fetch(`${env.API_BASE_URL}/admin/cv/status`).then(r => r.json()),
    refetchInterval: 5000,
  });

  // Fetch CV parsing logs
  const { data: logs, refetch: refetchLogs } = useQuery({
    queryKey: ["cv-logs"],
    queryFn: () =>
      fetch(`${env.API_BASE_URL}/admin/cv/logs?limit=50`).then(r => r.json()),
    refetchInterval: 10000,
  });

  // Manual trigger mutation
  const runNowMutation = useMutation({
    mutationFn: () =>
      fetch(`${env.API_BASE_URL}/admin/cv/run-now`, { method: "POST" }).then(r => r.json()),
    onSuccess: () => {
      refetchStatus();
      refetchLogs();
    },
  });

  // Re-parse all (or only failed) CVs - useful after prompt changes.
  const reparseAllMutation = useMutation({
    mutationFn: async (opts: { only_failed: boolean }) => {
      // First a dry run to show the user how many CVs will be affected.
      const preview = await fetch(`${env.API_BASE_URL}/admin/cv/reparse-all`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ confirm: false, only_failed: opts.only_failed }),
      }).then(r => r.json());

      const total = preview.previous_status_breakdown.success + preview.previous_status_breakdown.failed;
      const willReset = opts.only_failed
        ? preview.previous_status_breakdown.failed
        : total;

      if (willReset === 0) {
        throw new Error("אין CVs לעיבוד מחדש.");
      }

      const message = opts.only_failed
        ? `יסומנו ${willReset} CVs כשלים לעיבוד מחדש. להמשיך?`
        : `יסומנו ${willReset} CVs (כולל ${preview.previous_status_breakdown.success} שכבר הצליחו) לעיבוד מחדש עם הפרומפט החדש.\n\n` +
          `שים לב: זה ישתמש ב-Claude API מחדש (כ-${(willReset * 6000).toLocaleString()} tokens משוערים).\n\nלהמשיך?`;

      if (!confirm(message)) {
        throw new Error("cancelled");
      }

      const result = await fetch(`${env.API_BASE_URL}/admin/cv/reparse-all`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ confirm: true, only_failed: opts.only_failed }),
      }).then(r => r.json());

      return result;
    },
    onSuccess: (data) => {
      refetchStatus();
      refetchLogs();
      alert(`✓ ${data.marked_pending} CVs סומנו לעיבוד מחדש.\n${data.note}`);
    },
    onError: (err: Error) => {
      if (err.message !== "cancelled") {
        alert(`✗ שגיאה: ${err.message}`);
      }
    },
  });

  // retry mutation
  const retryMutation = useMutation({
    mutationFn: (cvId: string) =>
      fetch(`${env.API_BASE_URL}/admin/cv/retry/${cvId}`, { method: "POST" }).then(r => r.json()),
    onSuccess: () => {
      refetchStatus();
      refetchLogs();
    },
  });

  // view results mutation - fetches Claude analysis AND signed URL for the original file
  const viewResultsMutation = useMutation({
    mutationFn: async (cvId: string) => {
      const result = await fetch(`${env.API_BASE_URL}/admin/cv/results/${cvId}`).then(r => r.json());
      return { cvId, result };
    },
    onSuccess: ({ cvId, result }) => {
      setSelectedResult(result);
      setSignedUrl(null);
      setShowResultModal(true);
      // Fetch signed URL in background so the "View / Download original file" buttons work
      setSignedUrlLoading(true);
      fetch(`${env.API_BASE_URL}/admin/email/signed-url/${cvId}`, { method: "POST" })
        .then(r => r.json())
        .then(d => setSignedUrl(d.signed_url || null))
        .catch(() => setSignedUrl(null))
        .finally(() => setSignedUrlLoading(false));
    },
  });

  // Subscribe to CV file changes
  useEffect(() => {
    const channel = supabase
      .channel("cv-parsing")
      .on(
        "postgres_changes",
        { event: "UPDATE", schema: "public", table: "cv_files" },
        (payload) => {
          const updated = payload.new;
          if (updated.parse_status !== "pending") {
            setLiveEvents((prev) => [
              {
                cv_file_id: updated.id,
                original_filename: updated.original_filename,
                parse_status: updated.parse_status,
                parse_duration_ms: updated.parse_duration_ms,
                detected_language: updated.detected_language,
                llm_tokens_used: updated.llm_tokens_used,
                parse_error: updated.parse_error,
              },
              ...prev,
            ].slice(0, 5));
          }
        }
      )
      .subscribe();

    return () => {
      channel.unsubscribe();
    };
  }, []);

  const statusColor = {
    success: "bg-green-900/30 text-green-300 border-green-700",
    failed: "bg-red-900/30 text-red-300 border-red-700",
    parsing: "bg-blue-900/30 text-blue-300 border-blue-700",
    pending: "bg-gray-800 text-gray-400 border-gray-700",
  };

  const statusIcon = {
    success: "✓",
    failed: "✗",
    parsing: "⟳",
    pending: "◯",
  };

  // API returns an array directly, not a {data: [...]} envelope
  const logsList: CVLog[] = Array.isArray(logs) ? logs : (logs?.data ?? []);

  const avgTokens =
    logsList.length > 0
      ? Math.round(
          logsList.reduce((sum: number, log: CVLog) => sum + (log.llm_tokens_used || 0), 0) /
            logsList.length
        )
      : 0;

  const successRate =
    logsList.length > 0
      ? Math.round(
          (logsList.filter((log: CVLog) => log.parse_status === "success").length /
            logsList.length) *
            100
        )
      : 0;

  return (
    <div className="min-h-screen bg-gray-900 p-8" dir="rtl">
      <div className="max-w-7xl mx-auto">
        {/* Header */}
        <div className="mb-8">
          <div className="bg-gradient-to-r from-indigo-900 via-gray-800 to-purple-900 rounded-lg p-6 border border-gray-700">
            <h1 className="text-4xl font-bold text-white mb-2">ניתוח קורות חיים</h1>
            <p className="text-indigo-300">חילוץ נתונים מובנים מ-CV בעזרת Claude AI</p>
          </div>
        </div>

        {/* Status Cards */}
        <div className="grid grid-cols-5 gap-4 mb-8">
          <div className="bg-gray-800 p-6 rounded-lg border border-gray-700 hover:border-gray-600 transition-colors">
            <div className="text-xs text-gray-400 font-semibold mb-3 uppercase tracking-wide">בהמתנה</div>
            <div className="text-3xl font-bold text-indigo-300">{status?.pending || 0}</div>
          </div>
          <div className="bg-gray-800 p-6 rounded-lg border border-gray-700 hover:border-gray-600 transition-colors">
            <div className="text-xs text-gray-400 font-semibold mb-3 uppercase tracking-wide">בתהליך</div>
            <div className="text-3xl font-bold text-blue-400">{status?.parsing || 0}</div>
          </div>
          <div className="bg-gray-800 p-6 rounded-lg border border-gray-700 hover:border-gray-600 transition-colors">
            <div className="text-xs text-gray-400 font-semibold mb-3 uppercase tracking-wide">בהצלחה</div>
            <div className="text-3xl font-bold text-green-400">{status?.success || 0}</div>
          </div>
          <div className="bg-gray-800 p-6 rounded-lg border border-gray-700 hover:border-gray-600 transition-colors">
            <div className="text-xs text-gray-400 font-semibold mb-3 uppercase tracking-wide">כשל</div>
            <div className="text-3xl font-bold text-red-400">{status?.failed || 0}</div>
          </div>
          <div className="bg-gray-800 p-6 rounded-lg border border-gray-700 hover:border-gray-600 transition-colors">
            <div className="text-xs text-gray-400 font-semibold mb-3 uppercase tracking-wide">שיעור הצלחה</div>
            <div className="text-3xl font-bold text-purple-400">{successRate}%</div>
          </div>
        </div>

        {/* Metrics */}
        <div className="grid grid-cols-3 gap-4 mb-8">
          <div className="bg-gray-800 p-6 rounded-lg border border-gray-700 hover:border-gray-600 transition-colors">
            <div className="text-xs text-gray-400 font-semibold mb-3 uppercase tracking-wide">סה"כ מעובד</div>
            <div className="text-3xl font-bold text-white">
              {(status?.success || 0) + (status?.failed || 0)}
            </div>
          </div>
          <div className="bg-gray-800 p-6 rounded-lg border border-gray-700 hover:border-gray-600 transition-colors">
            <div className="text-xs text-gray-400 font-semibold mb-3 uppercase tracking-wide">ממוצע Tokens/CV</div>
            <div className="text-3xl font-bold text-indigo-300">{avgTokens}</div>
          </div>
          <div className="bg-gray-800 p-6 rounded-lg border border-gray-700 hover:border-gray-600 transition-colors">
            <div className="text-xs text-gray-400 font-semibold mb-3 uppercase tracking-wide">לוח זמנים</div>
            <div className="text-sm font-mono text-gray-300">כל 5 דקות</div>
          </div>
        </div>

        {/* Action Buttons */}
        <div className="bg-gray-800 border border-gray-700 rounded-lg p-4 mb-8">
          <div className="flex flex-wrap gap-3 items-center">
            <button
              onClick={() => runNowMutation.mutate()}
              disabled={runNowMutation.isPending}
              className="px-5 py-2 bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 text-white font-semibold rounded-lg text-sm"
            >
              {runNowMutation.isPending ? "מעבד..." : "▶ הפעל עכשיו"}
            </button>

            <button
              onClick={() => reparseAllMutation.mutate({ only_failed: true })}
              disabled={reparseAllMutation.isPending}
              className="px-4 py-2 bg-amber-700 hover:bg-amber-600 disabled:opacity-50 text-white font-semibold rounded-lg text-sm"
              title="סמן כל ה-CVs שנכשלו לעיבוד מחדש"
            >
              {reparseAllMutation.isPending ? "..." : "🔄 נסה שוב את הנכשלים"}
            </button>

            <button
              onClick={() => reparseAllMutation.mutate({ only_failed: false })}
              disabled={reparseAllMutation.isPending}
              className="px-4 py-2 bg-purple-700 hover:bg-purple-600 disabled:opacity-50 text-white font-semibold rounded-lg text-sm"
              title="סמן את כל ה-CVs (כולל אלה שכבר הצליחו) לעיבוד מחדש - שימושי אחרי שינוי פרומפט"
            >
              {reparseAllMutation.isPending ? "..." : "♻ עבד מחדש את כל ה-CVs"}
            </button>

            <div className="text-xs text-gray-400 mr-auto">
              <div>
                <span className="text-white font-semibold">{status?.pending || 0}</span> בהמתנה ·{" "}
                <span className="text-blue-400 font-semibold">{status?.parsing || 0}</span> בתהליך ·{" "}
                <span className="text-green-400 font-semibold">{status?.success || 0}</span> הצליחו
              </div>
              <div className="text-gray-500 mt-1">
                הסקנר רץ אוטומטית כל 3 דקות.
              </div>
            </div>
          </div>
        </div>

        {/* Live Events */}
        <div className="bg-gray-800 rounded-lg border border-gray-700 p-6 mb-8">
          <h2 className="text-xl font-semibold text-white mb-4">עיבוד קורות חיים בזמן אמת</h2>
          <div className="space-y-2 max-h-96 overflow-y-auto">
            {liveEvents.length === 0 ? (
              <div className="text-sm text-gray-400 py-8 text-center">מחכה לניתוח קורות חיים...</div>
            ) : (
              liveEvents.map((event) => (
                <div
                  key={event.cv_file_id}
                  className={`flex items-center p-4 rounded-lg text-sm gap-4 border transition-all ${
                    statusColor[event.parse_status as keyof typeof statusColor] || statusColor.pending
                  }`}
                >
                  <span className="font-bold text-lg flex-shrink-0">
                    {statusIcon[event.parse_status as keyof typeof statusIcon] || "?"}
                  </span>
                  <span className="font-mono text-xs text-gray-300 truncate flex-1">
                    {event.original_filename}
                  </span>
                  {event.detected_language && (
                    <span className="text-xs px-2 py-1 bg-gray-700 text-gray-300 rounded-full flex-shrink-0">
                      {event.detected_language.toUpperCase()}
                    </span>
                  )}
                  {event.parse_duration_ms && (
                    <span className="text-xs text-gray-400 flex-shrink-0">
                      {event.parse_duration_ms}ms
                    </span>
                  )}
                  {event.llm_tokens_used && (
                    <span className="text-xs text-indigo-300 flex-shrink-0">{event.llm_tokens_used} tokens</span>
                  )}
                  {event.parse_status === "failed" && (
                    <button
                      onClick={() => retryMutation.mutate(event.cv_file_id)}
                      disabled={retryMutation.isPending}
                      className="text-xs px-3 py-1 bg-amber-900/30 text-amber-300 border border-amber-700 rounded hover:bg-amber-900/50 disabled:opacity-50 transition-colors flex-shrink-0"
                    >
                      נסה שוב
                    </button>
                  )}
                </div>
              ))
            )}
          </div>
        </div>

        {/* History Table */}
        <div className="bg-gray-800 rounded-lg border border-gray-700 p-6 overflow-hidden">
          <h2 className="text-xl font-semibold text-white mb-4">היסטוריית עיבוד</h2>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-700 bg-gray-900/50">
                  <th className="text-right py-4 px-4 text-gray-300 font-semibold">שם קובץ</th>
                  <th className="text-right py-4 px-4 text-gray-300 font-semibold">סטטוס</th>
                  <th className="text-right py-4 px-4 text-gray-300 font-semibold">שפה</th>
                  <th className="text-right py-4 px-4 text-gray-300 font-semibold">משך</th>
                  <th className="text-right py-4 px-4 text-gray-300 font-semibold">Tokens</th>
                  <th className="text-right py-4 px-4 text-gray-300 font-semibold">שגיאה</th>
                  <th className="text-center py-4 px-4 text-gray-300 font-semibold">פעולות</th>
                </tr>
              </thead>
              <tbody>
                {logsList.length === 0 ? (
                  <tr>
                    <td colSpan={7} className="text-center py-8 text-gray-400 text-sm">
                      עדיין לא בוצע ניתוח קורות חיים
                    </td>
                  </tr>
                ) : (
                  logsList.map((log: CVLog) => (
                    <tr key={log.cv_file_id} className="border-b border-gray-700 hover:bg-gray-700/30 transition-colors">
                      <td className="py-4 px-4 font-mono text-xs max-w-xs truncate text-gray-300">
                        {log.original_filename}
                      </td>
                      <td className="py-4 px-4">
                        <span className={`inline-flex items-center px-3 py-1 rounded-full text-xs font-semibold border ${
                          log.parse_status === "success" ? "bg-green-900/30 text-green-300 border-green-700" :
                          log.parse_status === "failed" ? "bg-red-900/30 text-red-300 border-red-700" :
                          log.parse_status === "parsing" ? "bg-blue-900/30 text-blue-300 border-blue-700" :
                          "bg-gray-700/30 text-gray-300 border-gray-600"
                        }`}>
                          {log.parse_status === "success" ? "✓ בהצלחה" :
                           log.parse_status === "failed" ? "✗ כשל" :
                           log.parse_status === "parsing" ? "⟳ בתהליך" : "◯ בהמתנה"}
                        </span>
                      </td>
                      <td className="py-4 px-4 text-xs text-gray-400">
                        {log.detected_language ? log.detected_language.toUpperCase() : "—"}
                      </td>
                      <td className="py-4 px-4 text-xs text-gray-400">
                        {log.parse_duration_ms ? `${log.parse_duration_ms}ms` : "—"}
                      </td>
                      <td className="py-4 px-4 text-xs text-indigo-300">
                        {log.llm_tokens_used ? log.llm_tokens_used : "—"}
                      </td>
                      <td className="py-4 px-4 text-xs text-red-400 max-w-xs truncate">
                        {log.parse_error ? log.parse_error.substring(0, 40) : "—"}
                      </td>
                      <td className="py-4 px-4 text-center">
                        <div className="flex gap-2 justify-center">
                          {log.parse_status === "success" && (
                            <button
                              onClick={() => viewResultsMutation.mutate(log.cv_file_id)}
                              className="text-xs px-3 py-1 bg-indigo-900/30 text-indigo-300 border border-indigo-700 rounded hover:bg-indigo-900/50 transition-colors"
                            >
                              צפה
                            </button>
                          )}
                          {log.parse_status === "failed" && (
                            <button
                              onClick={() => retryMutation.mutate(log.cv_file_id)}
                              disabled={retryMutation.isPending}
                              className="text-xs px-3 py-1 bg-amber-900/30 text-amber-300 border border-amber-700 rounded hover:bg-amber-900/50 disabled:opacity-50 transition-colors"
                            >
                              נסה שוב
                            </button>
                          )}
                        </div>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>

        {/* Results Modal — show FULL Claude analysis with field→DB column mapping */}
        {showResultModal && selectedResult && (
          <div className="fixed inset-0 bg-black bg-opacity-70 flex items-center justify-center z-50 p-4" dir="rtl">
            <div className="bg-gray-800 rounded-lg max-w-5xl w-full max-h-[90vh] overflow-y-auto p-6 border border-gray-700 shadow-2xl">
              <div className="flex justify-between items-center mb-4 sticky top-0 bg-gray-800 pb-3 border-b border-gray-700">
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => setShowResultModal(false)}
                    className="text-gray-400 hover:text-gray-200 text-xl font-bold px-2"
                    title="סגור"
                  >
                    ✕
                  </button>
                  {/* View / Download original file (stored in Supabase Storage) */}
                  {signedUrlLoading && (
                    <span className="text-xs text-gray-400 px-3">טוען קישור...</span>
                  )}
                  {signedUrl && (
                    <>
                      <a
                        href={signedUrl}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-xs px-3 py-1.5 bg-indigo-900/40 text-indigo-200 border border-indigo-700 rounded hover:bg-indigo-900/60 transition-colors font-semibold"
                      >
                        👁 צפה בקובץ המקורי
                      </a>
                      <a
                        href={signedUrl}
                        download={selectedResult.original_filename}
                        className="text-xs px-3 py-1.5 bg-green-900/40 text-green-200 border border-green-700 rounded hover:bg-green-900/60 transition-colors font-semibold"
                      >
                        ⬇ הורד
                      </a>
                    </>
                  )}
                  {!signedUrlLoading && !signedUrl && (
                    <span className="text-xs text-amber-400 px-2" title="קובץ לא נמצא ב-Storage">
                      ⚠ קובץ לא זמין
                    </span>
                  )}
                </div>
                <h3 className="text-lg font-bold text-white truncate">{selectedResult.original_filename}</h3>
              </div>

              <div className="space-y-6 text-sm">
                {/* Metadata */}
                <div>
                  <h4 className="font-semibold text-indigo-300 mb-3">📊 מטא־דאטה של העיבוד</h4>
                  <div className="grid grid-cols-4 gap-3 text-xs bg-gray-900/50 p-4 rounded border border-gray-700">
                    <div>
                      <div className="text-gray-400 mb-1">שפה שזוהתה</div>
                      <div className="font-mono text-indigo-300 text-sm">{selectedResult.detected_language || "—"}</div>
                    </div>
                    <div>
                      <div className="text-gray-400 mb-1">שיטת חילוץ</div>
                      <div className="font-mono text-indigo-300 text-sm">{selectedResult.extraction_method || "—"}</div>
                    </div>
                    <div>
                      <div className="text-gray-400 mb-1">משך עיבוד</div>
                      <div className="font-mono text-indigo-300 text-sm">
                        {selectedResult.parse_duration_ms ? `${(selectedResult.parse_duration_ms / 1000).toFixed(1)}s` : "—"}
                      </div>
                    </div>
                    <div>
                      <div className="text-gray-400 mb-1">Tokens של Claude</div>
                      <div className="font-mono text-indigo-300 text-sm">{selectedResult.llm_tokens_used || "—"}</div>
                    </div>
                    <div>
                      <div className="text-gray-400 mb-1">גודל טקסט גולמי</div>
                      <div className="font-mono text-indigo-300 text-sm">
                        {selectedResult.raw_text_length ? `${selectedResult.raw_text_length.toLocaleString()} chars` : "—"}
                      </div>
                    </div>
                  </div>
                </div>

                {/* Extracted Fields - full table view with DB column mapping */}
                {selectedResult.extracted_fields && (
                  <div>
                    <h4 className="font-semibold text-indigo-300 mb-3">
                      🤖 שדות שזוהו על ידי Claude AI
                      <span className="text-xs text-gray-400 font-normal mr-2">
                        ({Object.keys(selectedResult.extracted_fields).length} שדות)
                      </span>
                    </h4>
                    <div className="bg-gray-900/50 rounded border border-gray-700 overflow-hidden">
                      <table className="w-full text-xs">
                        <thead>
                          <tr className="bg-gray-900 border-b border-gray-700">
                            <th className="text-right py-2 px-3 text-gray-300 font-semibold w-1/4">שדה (Claude)</th>
                            <th className="text-right py-2 px-3 text-gray-300 font-semibold w-1/4">עמודה ב-DB</th>
                            <th className="text-right py-2 px-3 text-gray-300 font-semibold">ערך שזוהה</th>
                          </tr>
                        </thead>
                        <tbody>
                          {Object.entries(selectedResult.extracted_fields).map(([key, value]) => {
                            const dbColumn = FIELD_TO_DB_COLUMN[key] || `candidates.${key}`;
                            const displayValue = formatFieldValue(value);
                            const confidence = selectedResult.confidence_scores?.[key];
                            return (
                              <tr key={key} className="border-b border-gray-700/50 hover:bg-gray-700/20">
                                <td className="py-2 px-3 font-mono text-indigo-300 align-top">{key}</td>
                                <td className="py-2 px-3 font-mono text-amber-300 text-xs align-top">
                                  {dbColumn}
                                </td>
                                <td className="py-2 px-3 text-gray-200 align-top">
                                  <div className="whitespace-pre-wrap break-words max-w-md">{displayValue}</div>
                                  {confidence != null && (
                                    <div className="mt-1 text-xs text-gray-500">
                                      ביטחון: {(confidence * 100).toFixed(0)}%
                                    </div>
                                  )}
                                </td>
                              </tr>
                            );
                          })}
                        </tbody>
                      </table>
                    </div>
                  </div>
                )}

                {/* Confidence scores chart */}
                {selectedResult.confidence_scores && Object.keys(selectedResult.confidence_scores).length > 0 && (
                  <div>
                    <h4 className="font-semibold text-indigo-300 mb-3">📈 ניקוד ביטחון לכל שדה</h4>
                    <div className="space-y-2 text-xs bg-gray-900/50 p-4 rounded border border-gray-700">
                      {Object.entries(selectedResult.confidence_scores).map(([key, score]) => {
                        const pct = (score as number) * 100;
                        const barColor = pct >= 80 ? "bg-green-600" : pct >= 50 ? "bg-amber-500" : "bg-red-500";
                        return (
                          <div key={key} className="flex items-center gap-3">
                            <span className="text-gray-300 w-32 font-mono">{key}</span>
                            <div className="flex-1 bg-gray-700 rounded h-4 overflow-hidden">
                              <div
                                className={`${barColor} h-full transition-all`}
                                style={{ width: `${pct}%` }}
                              />
                            </div>
                            <span className="w-12 text-right font-mono text-gray-300">{pct.toFixed(0)}%</span>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                )}

                {selectedResult.extraction_notes && (
                  <div>
                    <h4 className="font-semibold text-indigo-300 mb-2">📝 הערות מ-Claude</h4>
                    <p className="text-xs text-gray-300 bg-gray-900/50 p-3 rounded border border-gray-700 whitespace-pre-wrap">
                      {selectedResult.extraction_notes}
                    </p>
                  </div>
                )}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

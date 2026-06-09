/**
 * Candidates Database Page
 *
 * A full, searchable, paginated table of every candidate in the system
 * (the `candidates` table) with all their details. Clicking a row opens a
 * detail panel with the complete extracted CV data.
 */

import { useEffect, useState } from "react";
import { useQuery, keepPreviousData } from "@tanstack/react-query";
import { env } from "@/lib/env";

interface CandidateRow {
  id: string;
  name: string;
  email: string | null;
  phone: string | null;
  location: string | null;
  clearance_level: string | null;
  key_skills: string[] | null;
  years_of_experience: number | null;
  detected_language: string | null;
  overall_confidence_score: number | null;
  skill_readiness_status: string | null;
  cv_file_id: string | null;
  source_email_from: string | null;
  created_at: string;
}

interface DatabaseResponse {
  data: CandidateRow[];
  total: number;
  limit: number;
  offset: number;
}

const PAGE_SIZE = 50;

const READINESS_LABELS: Record<string, { label: string; cls: string }> = {
  READY: { label: "מוכן", cls: "bg-green-900 text-green-300 border-green-700" },
  REVIEW: { label: "בבדיקה", cls: "bg-amber-900 text-amber-300 border-amber-700" },
  INCOMPLETE: { label: "חסר", cls: "bg-slate-700 text-slate-300 border-slate-600" },
};

function fmtDate(iso: string | null): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleDateString("he-IL", {
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
    });
  } catch {
    return iso;
  }
}

export function CandidatesDatabasePage() {
  const [searchInput, setSearchInput] = useState("");
  const [search, setSearch] = useState("");
  const [language, setLanguage] = useState<string>("all");
  const [page, setPage] = useState(0);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  // Debounce search input
  useEffect(() => {
    const t = setTimeout(() => {
      setSearch(searchInput.trim());
      setPage(0);
    }, 350);
    return () => clearTimeout(t);
  }, [searchInput]);

  const { data, isLoading, isError, refetch, isFetching } = useQuery<DatabaseResponse>({
    queryKey: ["candidates-database", search, language, page],
    queryFn: () => {
      const params = new URLSearchParams({
        limit: String(PAGE_SIZE),
        offset: String(page * PAGE_SIZE),
      });
      if (search) params.set("search", search);
      if (language !== "all") params.set("language", language);
      return fetch(`${env.API_BASE_URL}/admin/candidates/database?${params}`).then((r) => {
        if (!r.ok) throw new Error("failed");
        return r.json();
      });
    },
    placeholderData: keepPreviousData,
  });

  const rows = data?.data || [];
  const total = data?.total || 0;
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <div className="p-8 max-w-[110rem] mx-auto" dir="rtl">
      <div className="mb-6">
        <h1 className="text-3xl font-bold text-white mb-1">📇 מאגר המועמדים</h1>
        <p className="text-slate-400 text-sm">
          כל המועמדים שנוצרו במערכת מתוך קורות החיים, עם כל הפרטים. לחיצה על שורה פותחת את הפרופיל המלא.
        </p>
      </div>

      {/* Toolbar */}
      <div className="flex flex-wrap items-center gap-3 mb-4">
        <input
          value={searchInput}
          onChange={(e) => setSearchInput(e.target.value)}
          placeholder="🔍 חיפוש לפי שם, אימייל או טלפון…"
          className="flex-1 min-w-[260px] px-4 py-2 rounded-lg bg-slate-800 border border-slate-700 text-white placeholder-slate-500 focus:outline-none focus:border-indigo-500"
        />
        <select
          value={language}
          onChange={(e) => {
            setLanguage(e.target.value);
            setPage(0);
          }}
          className="px-3 py-2 rounded-lg bg-slate-800 border border-slate-700 text-white text-sm"
        >
          <option value="all">כל השפות</option>
          <option value="he">עברית (he)</option>
          <option value="en">אנגלית (en)</option>
        </select>
        <button
          onClick={() => refetch()}
          className="px-3 py-2 rounded-lg bg-slate-800 border border-slate-700 text-slate-300 hover:bg-slate-700 text-sm"
        >
          🔄 רענן
        </button>
        <div className="text-sm text-slate-400 mr-auto">
          {isFetching ? "טוען…" : `סה"כ ${total.toLocaleString()} מועמדים`}
        </div>
      </div>

      {/* Table */}
      <div className="bg-slate-900 rounded-lg border border-slate-700 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm text-right">
            <thead>
              <tr className="bg-slate-800 text-slate-300 border-b border-slate-700">
                <th className="py-3 px-3 font-semibold">שם</th>
                <th className="py-3 px-3 font-semibold">אימייל</th>
                <th className="py-3 px-3 font-semibold">טלפון</th>
                <th className="py-3 px-3 font-semibold">מיקום</th>
                <th className="py-3 px-3 font-semibold">סיווג</th>
                <th className="py-3 px-3 font-semibold">ניסיון</th>
                <th className="py-3 px-3 font-semibold">כישורים</th>
                <th className="py-3 px-3 font-semibold">שפה</th>
                <th className="py-3 px-3 font-semibold text-center">ביטחון</th>
                <th className="py-3 px-3 font-semibold">סטטוס</th>
                <th className="py-3 px-3 font-semibold">נוצר</th>
              </tr>
            </thead>
            <tbody>
              {isLoading ? (
                <tr>
                  <td colSpan={11} className="text-center py-10 text-slate-400">
                    טוען מועמדים…
                  </td>
                </tr>
              ) : isError ? (
                <tr>
                  <td colSpan={11} className="text-center py-10 text-red-400">
                    שגיאה בטעינת המועמדים. נסה לרענן.
                  </td>
                </tr>
              ) : rows.length === 0 ? (
                <tr>
                  <td colSpan={11} className="text-center py-10 text-slate-400">
                    לא נמצאו מועמדים{search ? ` עבור "${search}"` : ""}.
                  </td>
                </tr>
              ) : (
                rows.map((c) => {
                  const readiness = c.skill_readiness_status
                    ? READINESS_LABELS[c.skill_readiness_status]
                    : null;
                  return (
                    <tr
                      key={c.id}
                      onClick={() => setSelectedId(c.id)}
                      className="border-b border-slate-800 hover:bg-slate-800/60 cursor-pointer transition"
                    >
                      <td className="py-2.5 px-3 font-semibold text-white whitespace-nowrap">
                        {c.name || "—"}
                      </td>
                      <td className="py-2.5 px-3 text-slate-300 ltr-text" dir="ltr">
                        {c.email || "—"}
                      </td>
                      <td className="py-2.5 px-3 text-slate-300 whitespace-nowrap" dir="ltr">
                        {c.phone || "—"}
                      </td>
                      <td className="py-2.5 px-3 text-slate-300 whitespace-nowrap">
                        {c.location || "—"}
                      </td>
                      <td className="py-2.5 px-3 text-slate-300 whitespace-nowrap">
                        {c.clearance_level || "—"}
                      </td>
                      <td className="py-2.5 px-3 text-slate-300 text-center">
                        {c.years_of_experience != null ? `${c.years_of_experience} שנים` : "—"}
                      </td>
                      <td className="py-2.5 px-3 text-slate-300 max-w-[220px]">
                        <div className="flex flex-wrap gap-1">
                          {(c.key_skills || []).slice(0, 3).map((s, i) => (
                            <span
                              key={i}
                              className="px-1.5 py-0.5 bg-slate-800 border border-slate-700 rounded text-[11px]"
                            >
                              {s}
                            </span>
                          ))}
                          {(c.key_skills?.length || 0) > 3 && (
                            <span className="text-[11px] text-slate-500">
                              +{(c.key_skills!.length - 3)}
                            </span>
                          )}
                          {!c.key_skills?.length && "—"}
                        </div>
                      </td>
                      <td className="py-2.5 px-3 text-xs">
                        <span className="px-2 py-0.5 bg-slate-800 rounded">
                          {c.detected_language?.toUpperCase() || "—"}
                        </span>
                      </td>
                      <td className="py-2.5 px-3 text-center">
                        {c.overall_confidence_score != null ? (
                          <div className="flex items-center gap-2 justify-center">
                            <div className="w-14 bg-slate-700 rounded h-1.5">
                              <div
                                className="bg-green-500 h-full rounded"
                                style={{ width: `${c.overall_confidence_score * 100}%` }}
                              />
                            </div>
                            <span className="text-[11px] font-mono text-slate-400 w-8">
                              {(c.overall_confidence_score * 100).toFixed(0)}%
                            </span>
                          </div>
                        ) : (
                          "—"
                        )}
                      </td>
                      <td className="py-2.5 px-3">
                        {readiness ? (
                          <span className={`px-2 py-0.5 rounded text-[11px] border ${readiness.cls}`}>
                            {readiness.label}
                          </span>
                        ) : (
                          "—"
                        )}
                      </td>
                      <td className="py-2.5 px-3 text-slate-400 text-xs whitespace-nowrap">
                        {fmtDate(c.created_at)}
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Pagination */}
      {total > PAGE_SIZE && (
        <div className="flex items-center justify-center gap-3 mt-4 text-sm">
          <button
            onClick={() => setPage((p) => Math.max(0, p - 1))}
            disabled={page === 0}
            className="px-3 py-1.5 rounded bg-slate-800 border border-slate-700 text-slate-300 disabled:opacity-40 hover:bg-slate-700"
          >
            ← הקודם
          </button>
          <span className="text-slate-400">
            עמוד {page + 1} מתוך {totalPages}
          </span>
          <button
            onClick={() => setPage((p) => (p + 1 < totalPages ? p + 1 : p))}
            disabled={page + 1 >= totalPages}
            className="px-3 py-1.5 rounded bg-slate-800 border border-slate-700 text-slate-300 disabled:opacity-40 hover:bg-slate-700"
          >
            הבא →
          </button>
        </div>
      )}

      {selectedId && (
        <CandidateDetailModal id={selectedId} onClose={() => setSelectedId(null)} />
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Detail modal — fetches the full candidate row + extracted CV data   */
/* ------------------------------------------------------------------ */

function CandidateDetailModal({ id, onClose }: { id: string; onClose: () => void }) {
  const { data: c, isLoading } = useQuery<any>({
    queryKey: ["candidate-detail", id],
    queryFn: () => fetch(`${env.API_BASE_URL}/admin/candidates/${id}`).then((r) => r.json()),
  });

  return (
    <div
      className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4"
      onClick={onClose}
      dir="rtl"
    >
      <div
        className="bg-slate-900 border border-slate-700 rounded-xl max-w-3xl w-full max-h-[85vh] overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between p-5 border-b border-slate-700 sticky top-0 bg-slate-900">
          <h2 className="text-xl font-bold text-white">
            {isLoading ? "טוען…" : c?.name || "מועמד"}
          </h2>
          <button
            onClick={onClose}
            className="text-slate-400 hover:text-white text-2xl leading-none px-2"
          >
            ×
          </button>
        </div>

        {isLoading || !c ? (
          <div className="p-10 text-center text-slate-400">טוען פרטי מועמד…</div>
        ) : (
          <div className="p-5 space-y-5">
            <Section title="פרטי קשר">              <Field label="אימייל" value={c.email} ltr />
              <Field label="טלפון" value={c.phone} ltr />
              <Field label="מיקום" value={c.location} />
              <Field label="שפה" value={c.detected_language?.toUpperCase()} />
            </Section>

            <Section title="פרופיל מקצועי">
              <Field label="סיווג בטחוני" value={c.clearance_level} />
              <Field
                label="שנות ניסיון"
                value={c.years_of_experience != null ? `${c.years_of_experience}` : null}
              />
              <Field
                label="ציון ביטחון"
                value={
                  c.overall_confidence_score != null
                    ? `${(c.overall_confidence_score * 100).toFixed(0)}%`
                    : null
                }
              />
              <Field label="סטטוס מוכנות" value={c.skill_readiness_status} />
            </Section>

            {c.key_skills?.length > 0 && (
              <div>
                <h3 className="text-sm font-semibold text-indigo-400 mb-2">כישורים</h3>
                <div className="flex flex-wrap gap-1.5">
                  {c.key_skills.map((s: string, i: number) => (
                    <span
                      key={i}
                      className="px-2 py-1 bg-slate-800 border border-slate-700 rounded text-xs text-slate-200"
                    >
                      {s}
                    </span>
                  ))}
                </div>
              </div>
            )}

            {Array.isArray(c.experiences) && c.experiences.length > 0 && (
              <div>
                <h3 className="text-sm font-semibold text-indigo-400 mb-2">ניסיון תעסוקתי</h3>
                <div className="space-y-2">
                  {c.experiences.map((exp: any, i: number) => (
                    <div
                      key={i}
                      className="bg-slate-800 border border-slate-700 rounded p-3 text-sm text-slate-200"
                    >
                      <div className="font-semibold">
                        {exp.title || exp.role || exp.position || "תפקיד"}
                      </div>
                      <div className="text-slate-400 text-xs">
                        {[exp.company, exp.duration || exp.dates].filter(Boolean).join(" · ")}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {c.top_education && (
              <Section title="השכלה">
                <Field label="תואר" value={c.top_education.degree} />
                <Field
                  label="מוסד"
                  value={c.top_education.institution || c.top_education.school}
                />
                <Field label="שנה" value={c.top_education.year} />
              </Section>
            )}

            {c.cv_details && (
              <Section title="מקור קורות החיים">
                <Field label="קובץ" value={c.cv_details.original_filename} />
                <Field label="התקבל מ-" value={c.cv_details.source_email_from} ltr />
                <Field
                  label="תאריך קבלה"
                  value={fmtDate(c.cv_details.source_email_received_at)}
                />
              </Section>
            )}

            {c.extracted_from_cv && (
              <details className="bg-slate-800 border border-slate-700 rounded">
                <summary className="px-4 py-2 cursor-pointer text-sm text-slate-300">
                  נתוני חילוץ מלאים (JSON)
                </summary>
                <pre
                  className="p-4 text-[11px] text-slate-400 overflow-x-auto"
                  dir="ltr"
                >
                  {JSON.stringify(c.extracted_from_cv, null, 2)}
                </pre>
              </details>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <h3 className="text-sm font-semibold text-indigo-400 mb-2">{title}</h3>
      <div className="grid grid-cols-2 gap-x-6 gap-y-2">{children}</div>
    </div>
  );
}

function Field({ label, value, ltr }: { label: string; value: any; ltr?: boolean }) {
  return (
    <div className="text-sm">
      <span className="text-slate-500">{label}: </span>
      <span className="text-slate-200" dir={ltr ? "ltr" : undefined}>
        {value || "—"}
      </span>
    </div>
  );
}

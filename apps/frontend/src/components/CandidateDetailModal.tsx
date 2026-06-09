/**
 * CandidateDetailModal — the canonical "CV summary" popup for a single
 * candidate. Fetches the full candidate row + extracted CV data from
 * /admin/candidates/:id and renders contact details, professional profile,
 * skills, experience, education and the raw extraction JSON.
 *
 * Shared so every screen that shows a candidate (the candidates database,
 * the recruiter match panels, …) opens the exact same summary.
 */

import { useQuery } from "@tanstack/react-query";
import { env } from "@/lib/env";

function fmtDate(iso: string | null): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleDateString("he-IL", {
      day: "2-digit",
      month: "2-digit",
      year: "numeric",
    });
  } catch {
    return iso;
  }
}

export function CandidateDetailModal({ id, onClose }: { id: string; onClose: () => void }) {
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
            <Section title="פרטי קשר">
              <Field label="אימייל" value={c.email} ltr />
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

export default CandidateDetailModal;

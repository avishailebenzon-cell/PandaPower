/**
 * MatchDetailModal — full breakdown of a single candidate-to-job match.
 *
 * Shows the "two extremes" of the AI's decision:
 *   • Strengths (why the candidate fits)
 *   • Gaps (why the candidate doesn't fit)
 * Plus match score, free-text reasoning, and a security-clearance comparison.
 *
 * Used by RecruitmentDepartment.tsx (every agent screen) and CarmitPage.tsx.
 */

import React from "react";
import type {
  DepartmentMatch,
  ClearanceMatch,
} from "@/api/recruitment-departments";

interface Props {
  match: DepartmentMatch | null;
  onClose: () => void;
}

const CLEARANCE_LABEL: Record<ClearanceMatch, string> = {
  match: "סיווג תואם",
  partial: "סיווג חלקי",
  mismatch: "סיווג לא תואם",
  unknown: "סיווג לא ידוע",
};

const CLEARANCE_COLOR: Record<ClearanceMatch, string> = {
  match: "bg-green-900 text-green-200 border-green-700",
  partial: "bg-yellow-900 text-yellow-200 border-yellow-700",
  mismatch: "bg-red-900 text-red-200 border-red-700",
  unknown: "bg-gray-700 text-gray-300 border-gray-600",
};

export function MatchDetailModal({ match, onClose }: Props) {
  if (!match) return null;

  const clearance = (match.clearanceMatch || "unknown") as ClearanceMatch;
  const scorePct = Math.round((match.matchScore || 0) * 100);

  return (
    <div
      className="fixed inset-0 bg-black/70 backdrop-blur-sm z-50 flex items-center justify-center p-4"
      onClick={onClose}
    >
      <div
        className="bg-gray-900 border border-gray-700 rounded-xl w-full max-w-3xl max-h-[90vh] overflow-y-auto shadow-2xl"
        onClick={(e) => e.stopPropagation()}
        dir="rtl"
      >
        {/* Header */}
        <div className="sticky top-0 bg-gray-900 border-b border-gray-700 px-6 py-4 flex items-start justify-between">
          <div>
            <h2 className="text-xl font-bold text-white">{match.candidateName}</h2>
            <p className="text-sm text-gray-400 mt-1">
              {match.jobTitle}
              {match.company && match.company !== "Unknown Company" ? ` · ${match.company}` : ""}
            </p>
          </div>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-white text-2xl leading-none px-2"
            aria-label="סגור"
          >
            ×
          </button>
        </div>

        {/* Body */}
        <div className="px-6 py-5 space-y-6">
          {/* Score + clearance badges row */}
          <div className="flex items-center gap-3 flex-wrap">
            <div className="flex items-center gap-2 px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg">
              <span className="text-xs text-gray-400">ציון התאמה</span>
              <span
                className={`font-bold text-lg ${
                  scorePct >= 80
                    ? "text-green-400"
                    : scorePct >= 70
                    ? "text-yellow-400"
                    : "text-orange-400"
                }`}
              >
                {scorePct}%
              </span>
            </div>

            <div
              className={`px-3 py-2 rounded-lg border text-sm font-semibold ${CLEARANCE_COLOR[clearance]}`}
            >
              {CLEARANCE_LABEL[clearance]}
            </div>
          </div>

          {/* Security-clearance comparison block */}
          <section className="bg-gray-800 border border-gray-700 rounded-lg p-4">
            <h3 className="text-sm font-semibold text-gray-300 mb-3">🔒 סיווג ביטחוני</h3>
            <div className="grid grid-cols-2 gap-4 text-sm">
              <div>
                <div className="text-gray-400 text-xs">המועמד</div>
                <div className="text-white font-semibold mt-1">
                  {match.candidateClearance || <span className="text-gray-500">לא צוין</span>}
                </div>
                {typeof match.candidateClearanceConfidence === "number" && (
                  <div className="text-xs text-gray-500 mt-1">
                    ביטחון בזיהוי: {Math.round(match.candidateClearanceConfidence * 100)}%
                  </div>
                )}
              </div>
              <div>
                <div className="text-gray-400 text-xs">דרישת המשרה</div>
                <div className="text-white font-semibold mt-1">
                  {match.requiredClearance || <span className="text-gray-500">ללא דרישה</span>}
                </div>
              </div>
            </div>
          </section>

          {/* Strengths */}
          <section>
            <h3 className="text-sm font-semibold text-green-300 mb-2 flex items-center gap-2">
              <span>✅ למה הוא מאוד מתאים</span>
              <span className="text-xs text-gray-500 font-normal">
                ({match.strengths?.length || 0} נקודות חוזק)
              </span>
            </h3>
            {match.strengths && match.strengths.length > 0 ? (
              <ul className="space-y-2">
                {match.strengths.map((s, i) => (
                  <li
                    key={i}
                    className="bg-green-900/20 border border-green-800/50 rounded-md px-3 py-2 text-sm text-green-100"
                  >
                    {s}
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-sm text-gray-500 italic">לא נשמרו נקודות חוזק עבור התאמה זו.</p>
            )}
          </section>

          {/* Gaps */}
          <section>
            <h3 className="text-sm font-semibold text-red-300 mb-2 flex items-center gap-2">
              <span>⚠️ למה הוא לא מתאים</span>
              <span className="text-xs text-gray-500 font-normal">
                ({match.gaps?.length || 0} פערים)
              </span>
            </h3>
            {match.gaps && match.gaps.length > 0 ? (
              <ul className="space-y-2">
                {match.gaps.map((g, i) => (
                  <li
                    key={i}
                    className="bg-red-900/20 border border-red-800/50 rounded-md px-3 py-2 text-sm text-red-100"
                  >
                    {g}
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-sm text-gray-500 italic">לא נשמרו פערים עבור התאמה זו.</p>
            )}
          </section>

          {/* Free-text reasoning */}
          {match.matchReasoning && (
            <section>
              <h3 className="text-sm font-semibold text-gray-300 mb-2">🧠 הסבר ה-AI</h3>
              <p className="bg-gray-800 border border-gray-700 rounded-md px-3 py-2 text-sm text-gray-200 whitespace-pre-wrap leading-relaxed">
                {match.matchReasoning}
              </p>
            </section>
          )}

          {/* What Carmit concluded — full picture for Tal before reaching out */}
          {match.carmitReview && (
            <section>
              <h3 className="text-sm font-semibold text-purple-300 mb-2">🛡️ מה כרמית אמרה על ההתאמה</h3>
              <p className="bg-purple-900/20 border border-purple-800/50 rounded-md px-3 py-2 text-sm text-purple-100 whitespace-pre-wrap leading-relaxed">
                {match.carmitReview}
              </p>
            </section>
          )}

          {/* Contact info */}
          {(match.email || match.phone) && (
            <section className="text-sm text-gray-300">
              <h3 className="text-sm font-semibold text-gray-300 mb-2">פרטי קשר</h3>
              <div className="flex flex-wrap gap-4">
                {match.email && <span>📧 {match.email}</span>}
                {match.phone && <span>📱 {match.phone}</span>}
              </div>
            </section>
          )}
        </div>

        {/* Footer */}
        <div className="sticky bottom-0 bg-gray-900 border-t border-gray-700 px-6 py-3 flex justify-end">
          <button
            onClick={onClose}
            className="px-4 py-2 bg-gray-700 hover:bg-gray-600 text-white rounded transition text-sm"
          >
            סגור
          </button>
        </div>
      </div>
    </div>
  );
}

/**
 * Compact security-clearance badge shown inside each match row.
 * Click handler is supplied by the row so the whole cell stays clickable.
 */
export function ClearanceBadge({ value }: { value: ClearanceMatch | undefined }) {
  const v: ClearanceMatch = value || "unknown";
  const config: Record<ClearanceMatch, { label: string; cls: string; icon: string }> = {
    match: { label: "סיווג תואם", cls: "bg-green-900 text-green-200", icon: "🟢" },
    partial: { label: "סיווג חלקי", cls: "bg-yellow-900 text-yellow-200", icon: "🟡" },
    mismatch: { label: "לא תואם", cls: "bg-red-900 text-red-200", icon: "🔴" },
    unknown: { label: "לא ידוע", cls: "bg-gray-700 text-gray-300", icon: "⚪" },
  };
  const c = config[v];
  return (
    <span
      className={`px-2 py-1 rounded text-xs font-semibold inline-flex items-center gap-1 ${c.cls}`}
      title={c.label}
    >
      <span>{c.icon}</span>
      <span>{c.label}</span>
    </span>
  );
}

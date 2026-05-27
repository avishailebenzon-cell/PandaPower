/**
 * RecruiterMatchesPanel — the canonical list of matches at any recruiter
 * (Tal or Elad) stage of the workflow. Used in three places so all three
 * stay in sync:
 *
 *   • CarmitPage  → "העברתי לטל" tab    (recruiter="tal")
 *   • CarmitPage  → "העברתי לאלעד" tab   (recruiter="elad")
 *   • TalPage     → standalone view      (recruiter="tal")
 *   • EladPageNew → standalone view      (recruiter="elad")
 *
 * Data comes from /admin/recruiter/matches?tab=tal-queue|tal-history|...
 * which filters matches by current_state. The state-machine groups are:
 *
 *   tal-queue:     sent_to_tal, tal_conversation
 *   tal-history:   tal_approved, tal_rejected
 *   elad-queue:    sent_to_elad, elad_conversation
 *   elad-history:  elad_approved, hired, placement_failed
 *
 * Everything shown is REAL — no mock data. Empty state is explicit.
 */

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  fetchRecruiterMatches,
  fetchRecruiterStatus,
  type Match,
} from "@/api/recruiter";

type Recruiter = "tal" | "elad";
type SubTab = "queue" | "history";

interface Props {
  recruiter: Recruiter;
  /** Optional override — if not given, an internal toggle lets the user switch. */
  initialSubTab?: SubTab;
  /** Show the queue + history toggle (default: true). */
  showSubTabs?: boolean;
  /** Show the small status-strip at top (default: true). */
  showStatusStrip?: boolean;
}

const STATE_LABELS: Record<string, { label: string; cls: string }> = {
  sent_to_tal: { label: "ממתינה לטל", cls: "bg-blue-900 text-blue-200" },
  tal_conversation: { label: "בשיחה עם טל", cls: "bg-indigo-900 text-indigo-200" },
  tal_approved: { label: "אושר ע״י טל", cls: "bg-green-900 text-green-200" },
  tal_rejected: { label: "נדחה ע״י טל", cls: "bg-red-900 text-red-200" },
  sent_to_elad: { label: "ממתינה לאלעד", cls: "bg-purple-900 text-purple-200" },
  elad_conversation: { label: "בשיחה עם אלעד", cls: "bg-fuchsia-900 text-fuchsia-200" },
  elad_approved: { label: "אושר ע״י אלעד", cls: "bg-emerald-900 text-emerald-200" },
  hired: { label: "🎉 הושמה", cls: "bg-emerald-700 text-white" },
  placement_failed: { label: "כשלון השמה", cls: "bg-red-900 text-red-200" },
};

function StateBadge({ state }: { state: string }) {
  const cfg = STATE_LABELS[state] || { label: state, cls: "bg-gray-700 text-gray-300" };
  return (
    <span className={`px-2 py-0.5 rounded text-xs font-semibold ${cfg.cls}`}>{cfg.label}</span>
  );
}

function formatDate(iso?: string): string {
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

export function RecruiterMatchesPanel({
  recruiter,
  initialSubTab = "queue",
  showSubTabs = true,
  showStatusStrip = true,
}: Props) {
  const [subTab, setSubTab] = useState<SubTab>(initialSubTab);
  const tabParam = `${recruiter}-${subTab}`; // tal-queue, elad-history, etc.

  const recruiterName = recruiter === "tal" ? "טל" : "אלעד";
  const counterparty = recruiter === "tal" ? "מועמד" : "לקוח";

  const matchesQuery = useQuery({
    queryKey: ["recruiter-matches", tabParam],
    queryFn: () => fetchRecruiterMatches(tabParam, 100, 1),
    refetchInterval: 20000,
  });

  const statusQuery = useQuery({
    queryKey: ["recruiter-status"],
    queryFn: fetchRecruiterStatus,
    refetchInterval: 20000,
    enabled: showStatusStrip,
  });

  const matches = matchesQuery.data?.matches ?? [];

  // Counts to surface in the optional status strip
  const inQueue =
    recruiter === "tal"
      ? (statusQuery.data?.pendingTal ?? 0) + (statusQuery.data?.inConversationTal ?? 0)
      : (statusQuery.data?.awaitingElad ?? 0) + (statusQuery.data?.inConversationElad ?? 0);

  return (
    <div dir="rtl" className="space-y-4">
      {/* Optional: tiny status strip with live counters */}
      {showStatusStrip && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-right">
          <StatusCell
            label={`בתור ל${recruiterName}`}
            value={inQueue}
            tone="blue"
          />
          <StatusCell
            label="הושמו"
            value={statusQuery.data?.hired ?? 0}
            tone="green"
          />
          <StatusCell
            label="כשלון"
            value={statusQuery.data?.failed ?? 0}
            tone="red"
          />
          <StatusCell
            label={`סה״כ בתצוגה`}
            value={matchesQuery.data?.total ?? 0}
            tone="gray"
          />
        </div>
      )}

      {/* Optional: queue/history toggle */}
      {showSubTabs && (
        <div className="inline-flex bg-gray-800 rounded-lg p-1 gap-1">
          <button
            onClick={() => setSubTab("queue")}
            className={`px-4 py-1.5 rounded text-sm font-semibold transition ${
              subTab === "queue"
                ? "bg-indigo-600 text-white"
                : "text-gray-300 hover:text-white"
            }`}
          >
            פעיל ({recruiter === "tal" ? "ממתינה / בשיחה" : "ממתינה / בשיחה"})
          </button>
          <button
            onClick={() => setSubTab("history")}
            className={`px-4 py-1.5 rounded text-sm font-semibold transition ${
              subTab === "history"
                ? "bg-indigo-600 text-white"
                : "text-gray-300 hover:text-white"
            }`}
          >
            היסטוריה (החלטות סופיות)
          </button>
        </div>
      )}

      {/* Body: loading / empty / list */}
      {matchesQuery.isLoading ? (
        <div className="text-gray-400 text-center py-8">טוען…</div>
      ) : matchesQuery.error ? (
        <div className="text-red-400 text-center py-8">
          שגיאה בטעינת הנתונים: {String((matchesQuery.error as Error).message)}
        </div>
      ) : matches.length === 0 ? (
        <EmptyState
          subTab={subTab}
          recruiterName={recruiterName}
          counterparty={counterparty}
        />
      ) : (
        <div className="bg-gray-800 rounded-lg border border-gray-700 overflow-hidden">
          <table className="w-full text-right text-sm">
            <thead className="bg-gray-700 border-b border-gray-600 text-gray-200">
              <tr>
                <th className="px-4 py-3 font-semibold">מועמד</th>
                <th className="px-4 py-3 font-semibold">משרה</th>
                <th className="px-4 py-3 font-semibold">ציון</th>
                <th className="px-4 py-3 font-semibold">מצב נוכחי</th>
                <th className="px-4 py-3 font-semibold">ימים במצב</th>
                <th className="px-4 py-3 font-semibold">עודכן</th>
              </tr>
            </thead>
            <tbody>
              {matches.map((m: Match) => (
                <tr
                  key={m.id}
                  className="border-b border-gray-700 hover:bg-gray-750 transition"
                >
                  <td className="px-4 py-3 text-white font-semibold">{m.candidateName}</td>
                  <td className="px-4 py-3 text-gray-300">{m.jobTitle}</td>
                  <td className="px-4 py-3 text-gray-300">
                    {Math.round((m.matchScore || 0) * 100)}%
                  </td>
                  <td className="px-4 py-3">
                    <StateBadge state={m.state} />
                  </td>
                  <td className="px-4 py-3 text-gray-300">{m.daysInStage} י׳</td>
                  <td className="px-4 py-3 text-gray-400">{formatDate(m.lastActivity)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function StatusCell({
  label,
  value,
  tone,
}: {
  label: string;
  value: number;
  tone: "blue" | "green" | "red" | "gray";
}) {
  const toneCls = {
    blue: "bg-blue-900/30 border-blue-700 text-blue-200",
    green: "bg-green-900/30 border-green-700 text-green-200",
    red: "bg-red-900/30 border-red-700 text-red-200",
    gray: "bg-gray-800 border-gray-700 text-gray-200",
  }[tone];
  return (
    <div className={`rounded-lg border px-3 py-2 ${toneCls}`}>
      <div className="text-xs opacity-80">{label}</div>
      <div className="text-xl font-bold">{value}</div>
    </div>
  );
}

function EmptyState({
  subTab,
  recruiterName,
  counterparty,
}: {
  subTab: SubTab;
  recruiterName: string;
  counterparty: string;
}) {
  return (
    <div className="bg-gray-800 border border-gray-700 rounded-lg p-8 text-center text-gray-300">
      {subTab === "queue" ? (
        <>
          <p className="text-lg mb-2">📭 אין כרגע התאמות בתור של {recruiterName}</p>
          <p className="text-sm text-gray-400">
            התאמות יופיעו כאן כשתהליך מכונת-המצבים יעביר אותן ל{recruiterName} לשיחה עם ה
            {counterparty}.
          </p>
        </>
      ) : (
        <>
          <p className="text-lg mb-2">🗂️ אין עדיין החלטות בהיסטוריה</p>
          <p className="text-sm text-gray-400">
            לאחר ש{recruiterName} תאשר או תדחה התאמות, הן יופיעו כאן.
          </p>
        </>
      )}
    </div>
  );
}

export default RecruiterMatchesPanel;

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

import { useState, useMemo, Fragment } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  fetchRecruiterMatches,
  fetchRecruiterStatus,
  performMatchAction,
  fetchMatchConversation,
  fetchMatchDetail,
  type Match,
} from "@/api/recruiter";
import { MatchDetailModal } from "@/components/MatchDetailModal";
import type { DepartmentMatch } from "@/api/recruitment-departments";

type Recruiter = "carmit" | "tal" | "elad";
type SubTab = "queue" | "history";
type SortKey = "candidate" | "job" | "score" | "state" | "days" | "updated";
type GroupKey = "none" | "candidate" | "job" | "state";

interface Props {
  recruiter: Recruiter;
  /** Optional override — if not given, an internal toggle lets the user switch. */
  initialSubTab?: SubTab;
  /** Show the queue + history toggle (default: true). */
  showSubTabs?: boolean;
  /** Show the small status-strip at top (default: true). */
  showStatusStrip?: boolean;
}

// Each status has its own colour. The two "in conversation" states are marked
// `live` — their badge pulses with a blinking dot so it's obvious, at a glance,
// that a real-time WhatsApp conversation is in progress.
const STATE_LABELS: Record<string, { label: string; cls: string; live?: boolean }> = {
  found: { label: "נמצאה התאמה", cls: "bg-yellow-900 text-yellow-200" },
  evaluated_but_rejected: { label: "נבדק — לא התאים (<70)", cls: "bg-gray-700 text-gray-300" },
  carmit_approved: { label: "אושרה על ידי כרמית", cls: "bg-green-900 text-green-200" },
  carmit_rejected: { label: "נדחתה על ידי כרמית", cls: "bg-red-900 text-red-200" },
  sent_to_tal: { label: "ממתינה לטל", cls: "bg-blue-900 text-blue-200" },
  tal_conversation: { label: "בשיחה עם טל", cls: "bg-indigo-600 text-white", live: true },
  tal_approved: { label: "אושר ע״י טל", cls: "bg-green-900 text-green-200" },
  tal_rejected: { label: "נדחה ע״י טל", cls: "bg-red-900 text-red-200" },
  sent_to_elad: { label: "ממתינה לאלעד", cls: "bg-purple-900 text-purple-200" },
  elad_conversation: { label: "בשיחה עם אלעד", cls: "bg-fuchsia-600 text-white", live: true },
  elad_approved: { label: "אושר ע״י אלעד", cls: "bg-emerald-900 text-emerald-200" },
  hired: { label: "🎉 הושמה", cls: "bg-emerald-700 text-white" },
  placement_failed: { label: "כשלון השמה", cls: "bg-red-900 text-red-200" },
};

function StateBadge({ state }: { state: string }) {
  const cfg = STATE_LABELS[state] || { label: state, cls: "bg-gray-700 text-gray-300" };
  if (cfg.live) {
    return (
      <span
        className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded text-xs font-semibold ring-1 ring-green-300/70 animate-live-glow ${cfg.cls}`}
        title="שיחה פעילה בזמן אמת"
      >
        <span className="relative flex h-2.5 w-2.5">
          <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-300 opacity-90" />
          <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-green-300" />
        </span>
        <span className="animate-blink">● {cfg.label}</span>
      </span>
    );
  }
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
  const [selectedMatchId, setSelectedMatchId] = useState<string | null>(null);
  const [showConversationModal, setShowConversationModal] = useState(false);
  const [showActionMenu, setShowActionMenu] = useState<string | null>(null);
  const [detailMatchId, setDetailMatchId] = useState<string | null>(null);

  const queryClient = useQueryClient();
  const tabParam = `${recruiter}-${subTab}`; // tal-queue, elad-history, etc.

  const recruiterName = recruiter === "carmit" ? "כרמית" : recruiter === "tal" ? "טל" : "אלעד";
  const counterparty = recruiter === "carmit" ? "התאמה" : recruiter === "tal" ? "מועמד" : "לקוח";

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

  const conversationQuery = useQuery({
    queryKey: ["match-conversation", selectedMatchId],
    queryFn: () => selectedMatchId ? fetchMatchConversation(selectedMatchId) : null,
    enabled: selectedMatchId !== null,
  });

  const detailQuery = useQuery({
    queryKey: ["match-detail", detailMatchId],
    queryFn: () => (detailMatchId ? fetchMatchDetail(detailMatchId) : null),
    enabled: detailMatchId !== null,
  });

  const actionMutation = useMutation({
    mutationFn: ({ matchId, action, notes }: { matchId: string; action: "activate" | "reject" | "wait"; notes?: string }) =>
      performMatchAction(matchId, action, notes),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["recruiter-matches"] });
      queryClient.invalidateQueries({ queryKey: ["recruiter-status"] });
      setShowActionMenu(null);
    },
  });

  const matches = matchesQuery.data?.matches ?? [];

  // ---- Sorting & grouping (client-side, over the loaded page) ----
  const [sortKey, setSortKey] = useState<SortKey>("updated");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");
  const [groupBy, setGroupBy] = useState<GroupKey>("none");

  const toggleSort = (key: SortKey) => {
    if (sortKey === key) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      setSortDir(key === "candidate" || key === "job" || key === "state" ? "asc" : "desc");
    }
  };

  const sortedMatches = useMemo(() => {
    const arr = [...matches];
    const dir = sortDir === "asc" ? 1 : -1;
    arr.sort((a, b) => {
      let cmp = 0;
      switch (sortKey) {
        case "candidate":
          cmp = (a.candidateName || "").localeCompare(b.candidateName || "", "he");
          break;
        case "job":
          cmp = (a.jobTitle || "").localeCompare(b.jobTitle || "", "he");
          break;
        case "score":
          cmp = (a.matchScore || 0) - (b.matchScore || 0);
          break;
        case "state":
          cmp = (STATE_LABELS[a.state]?.label || a.state).localeCompare(
            STATE_LABELS[b.state]?.label || b.state, "he");
          break;
        case "days":
          cmp = (a.daysInStage || 0) - (b.daysInStage || 0);
          break;
        case "updated":
          cmp = new Date(a.lastActivity || 0).getTime() - new Date(b.lastActivity || 0).getTime();
          break;
      }
      return cmp * dir;
    });
    return arr;
  }, [matches, sortKey, sortDir]);

  // Build grouped sections when grouping is active; otherwise one anonymous group.
  const groups = useMemo<{ key: string; label: string; rows: Match[] }[]>(() => {
    if (groupBy === "none") {
      return [{ key: "__all__", label: "", rows: sortedMatches }];
    }
    const map = new Map<string, Match[]>();
    for (const m of sortedMatches) {
      const k =
        groupBy === "candidate" ? m.candidateName || "—"
        : groupBy === "job" ? m.jobTitle || "—"
        : (STATE_LABELS[m.state]?.label || m.state || "—");
      if (!map.has(k)) map.set(k, []);
      map.get(k)!.push(m);
    }
    return Array.from(map.entries())
      .sort((a, b) => a[0].localeCompare(b[0], "he"))
      .map(([key, rows]) => ({ key, label: key, rows }));
  }, [sortedMatches, groupBy]);

  const renderRow = (m: Match) => (
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
      <td className="px-4 py-3">
        <MatchActionsMenu
          match={m}
          recruiter={recruiter}
          isOpen={showActionMenu === m.id}
          onToggle={() => setShowActionMenu(showActionMenu === m.id ? null : m.id)}
          onActivate={() => actionMutation.mutate({ matchId: m.id, action: "activate" })}
          onReject={() => {
            if (
              window.confirm(
                `האם אתה בטוח שברצונך למחוק את ההתאמה של ${m.candidateName}?\nפעולה זו אינה ניתנת לביטול.`
              )
            ) {
              actionMutation.mutate({ matchId: m.id, action: "reject" });
            }
          }}
          onConversation={() => {
            setSelectedMatchId(m.id);
            setShowConversationModal(true);
          }}
          onDetail={() => setDetailMatchId(m.id)}
          isLoading={actionMutation.isPending}
        />
      </td>
    </tr>
  );

  const SortHeader = ({ label, col }: { label: string; col: SortKey }) => (
    <th className="px-4 py-3 font-semibold">
      <button
        onClick={() => toggleSort(col)}
        className="inline-flex items-center gap-1 hover:text-white transition"
        title="מיון לפי עמודה זו"
      >
        <span>{label}</span>
        <span className="text-xs opacity-70">
          {sortKey === col ? (sortDir === "asc" ? "▲" : "▼") : "⇅"}
        </span>
      </button>
    </th>
  );

  // Counts to surface in the optional status strip
  const inQueue =
    recruiter === "carmit"
      ? (statusQuery.data?.pendingCarmit ?? 0) + (statusQuery.data?.carmitApproved ?? 0)
      : recruiter === "tal"
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
        <>
          {/* Group-by toolbar */}
          <div className="flex items-center gap-2 text-sm">
            <span className="text-gray-400">קבץ לפי:</span>
            {([
              { k: "none", label: "ללא" },
              { k: "candidate", label: "מועמד" },
              { k: "job", label: "משרה" },
              { k: "state", label: "מצב נוכחי" },
            ] as { k: GroupKey; label: string }[]).map(({ k, label }) => (
              <button
                key={k}
                onClick={() => setGroupBy(k)}
                className={`px-3 py-1 rounded text-sm transition ${
                  groupBy === k
                    ? "bg-indigo-600 text-white"
                    : "bg-gray-800 text-gray-300 hover:text-white"
                }`}
              >
                {label}
              </button>
            ))}
          </div>

          <div className="bg-gray-800 rounded-lg border border-gray-700 overflow-visible">
            <table className="w-full text-right text-sm">
              <thead className="bg-gray-700 border-b border-gray-600 text-gray-200">
                <tr>
                  <SortHeader label="מועמד" col="candidate" />
                  <SortHeader label="משרה" col="job" />
                  <SortHeader label="ציון" col="score" />
                  <SortHeader label="מצב נוכחי" col="state" />
                  <SortHeader label="ימים במצב" col="days" />
                  <SortHeader label="עודכן" col="updated" />
                  <th className="px-4 py-3 font-semibold">פעולות</th>
                </tr>
              </thead>
              <tbody>
                {groups.map((g) => (
                  <Fragment key={g.key}>
                    {groupBy !== "none" && (
                      <tr className="bg-gray-700/40">
                        <td colSpan={7} className="px-4 py-2 text-indigo-200 font-semibold">
                          {g.label} <span className="text-gray-400 font-normal">({g.rows.length})</span>
                        </td>
                      </tr>
                    )}
                    {g.rows.map(renderRow)}
                  </Fragment>
                ))}
              </tbody>
            </table>
          </div>

          {/* Conversation Modal */}
          {showConversationModal && selectedMatchId && (
            <ConversationModal
              conversation={conversationQuery.data}
              isLoading={conversationQuery.isLoading}
              onClose={() => {
                setShowConversationModal(false);
                setSelectedMatchId(null);
              }}
            />
          )}

          {/* Match-detail modal — the "why this match" view as produced by the
              recruiting agent (reasoning, strengths, gaps, clearance). */}
          {detailMatchId && (
            detailQuery.isLoading ? (
              <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
                <div className="bg-gray-800 rounded-lg p-8 text-center">
                  <p className="text-gray-300">טוען פרטי התאמה…</p>
                </div>
              </div>
            ) : (
              <MatchDetailModal
                match={(detailQuery.data as DepartmentMatch) ?? null}
                onClose={() => setDetailMatchId(null)}
              />
            )
          )}
        </>
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

// Action menu for each match row
function MatchActionsMenu({
  match,
  recruiter,
  isOpen,
  onToggle,
  onActivate,
  onReject,
  onConversation,
  onDetail,
  isLoading,
}: {
  match: Match;
  recruiter: string;
  isOpen: boolean;
  onToggle: () => void;
  onActivate: () => void;
  onReject: () => void;
  onConversation: () => void;
  onDetail: () => void;
  isLoading: boolean;
}) {
  const isInQueue = recruiter === "carmit"
    ? match.state === "found"
    : (match.state === `sent_to_${recruiter}` || match.state === `${recruiter}_conversation`);

  return (
    <div className="relative inline-block z-50">
      <button
        onClick={onToggle}
        className="px-2 py-1 rounded text-xs bg-gray-700 hover:bg-gray-600 text-gray-200 transition"
      >
        ⋮
      </button>
      {isOpen && (
        <div className="absolute left-0 top-full mt-1 bg-gray-700 border border-gray-600 rounded-lg shadow-xl z-[100] min-w-max">
          {isInQueue && (
            <>
              <button
                onClick={() => {
                  onActivate();
                }}
                disabled={isLoading}
                className="block w-full text-right px-4 py-2 hover:bg-green-900 text-green-200 text-sm disabled:opacity-50 border-b border-gray-600 whitespace-nowrap"
              >
                ✓ אקטיבציה של פנייה
              </button>
              <button
                onClick={() => {
                  onReject();
                }}
                disabled={isLoading}
                className="block w-full text-right px-4 py-2 hover:bg-red-900 text-red-200 text-sm disabled:opacity-50 border-b border-gray-600 whitespace-nowrap"
              >
                ✕ מחיקת התאמה
              </button>
            </>
          )}
          <button
            onClick={() => {
              onDetail();
              onToggle();
            }}
            disabled={isLoading}
            className="block w-full text-right px-4 py-2 hover:bg-indigo-900 text-indigo-200 text-sm disabled:opacity-50 border-b border-gray-600 whitespace-nowrap"
          >
            📄 פרטי ההתאמה
          </button>
          <button
            onClick={() => {
              onConversation();
              onToggle();
            }}
            disabled={isLoading}
            className="block w-full text-right px-4 py-2 hover:bg-blue-900 text-blue-200 text-sm disabled:opacity-50 whitespace-nowrap"
          >
            💬 הצג שיחה
          </button>
        </div>
      )}
    </div>
  );
}

// Conversation modal
function ConversationModal({
  conversation,
  isLoading,
  onClose,
}: {
  conversation: any;
  isLoading: boolean;
  onClose: () => void;
}) {
  if (isLoading) {
    return (
      <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
        <div className="bg-gray-800 rounded-lg p-8 text-center">
          <p className="text-gray-300">טוען שיחה...</p>
        </div>
      </div>
    );
  }

  if (!conversation) {
    return (
      <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
        <div className="bg-gray-800 rounded-lg p-8 text-center border border-gray-700">
          <p className="text-gray-300 mb-4">אין עדיין שיחה לתאום זה</p>
          <button
            onClick={onClose}
            className="px-4 py-2 bg-gray-700 hover:bg-gray-600 text-gray-200 rounded text-sm"
          >
            סגור
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <div className="bg-gray-800 rounded-lg border border-gray-700 w-full max-w-2xl max-h-[80vh] flex flex-col">
        {/* Header */}
        <div className="border-b border-gray-700 p-4 flex justify-between items-center">
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-white text-2xl"
          >
            ×
          </button>
          <h2 className="text-white font-semibold">שיחה</h2>
          <div className="text-sm text-gray-400">
            {new Date(conversation.startedAt).toLocaleDateString("he-IL")}
          </div>
        </div>

        {/* Messages */}
        <div className="flex-1 overflow-y-auto p-4 space-y-3">
          {conversation.messages && conversation.messages.length > 0 ? (
            conversation.messages.map((msg: any) => (
              <div
                key={msg.id}
                className={`flex ${msg.direction === "outbound" ? "justify-end" : "justify-start"}`}
              >
                <div
                  className={`rounded-lg px-3 py-2 max-w-xs ${
                    msg.direction === "outbound"
                      ? "bg-blue-900 text-blue-100"
                      : "bg-gray-700 text-gray-100"
                  }`}
                >
                  <p className="text-sm">{msg.text}</p>
                  <p className="text-xs opacity-70 mt-1">
                    {new Date(msg.createdAt).toLocaleTimeString("he-IL", {
                      hour: "2-digit",
                      minute: "2-digit",
                    })}
                  </p>
                </div>
              </div>
            ))
          ) : (
            <p className="text-center text-gray-400 text-sm">אין הודעות בשיחה זו</p>
          )}
        </div>

        {/* Footer */}
        <div className="border-t border-gray-700 p-4">
          {conversation.notes && (
            <p className="text-xs text-gray-400 mb-2">
              <strong>הערות:</strong> {conversation.notes}
            </p>
          )}
          <button
            onClick={onClose}
            className="w-full px-4 py-2 bg-gray-700 hover:bg-gray-600 text-gray-200 rounded text-sm"
          >
            סגור
          </button>
        </div>
      </div>
    </div>
  );
}

export default RecruiterMatchesPanel;

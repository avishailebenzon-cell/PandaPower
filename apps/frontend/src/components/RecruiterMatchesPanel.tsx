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

import { useState, useMemo, useEffect, Fragment } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  fetchRecruiterMatches,
  fetchRecruiterStatus,
  performMatchAction,
  setMatchFavorite,
  fetchMatchConversation,
  fetchMatchDetail,
  fetchFormattedCv,
  generateFormattedCv,
  approveFormattedCv,
  rejectFormattedCv,
  emailFormattedCv,
  type Match,
  type MatchAction,
} from "@/api/recruiter";
import { MatchDetailModal } from "@/components/MatchDetailModal";
import { CandidateDetailModal } from "@/components/CandidateDetailModal";
import { GeoMismatchBadge } from "@/components/GeoMismatchBadge";
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
  tal_handed_to_human: { label: "הועבר לגורם אנושי", cls: "bg-amber-800 text-amber-100" },
  tal_approved: { label: "אושר ע״י טל", cls: "bg-green-900 text-green-200" },
  tal_rejected: { label: "נדחה ע״י טל", cls: "bg-red-900 text-red-200" },
  sent_to_elad: { label: "ממתינה לאלעד", cls: "bg-purple-900 text-purple-200" },
  elad_conversation: { label: "בשיחה עם אלעד", cls: "bg-fuchsia-600 text-white", live: true },
  elad_handed_to_human: { label: "הועבר לגורם אנושי", cls: "bg-amber-800 text-amber-100" },
  elad_approved: { label: "אושר ע״י אלעד", cls: "bg-emerald-900 text-emerald-200" },
  hired: { label: "🎉 הושמה", cls: "bg-emerald-700 text-white" },
  placement_failed: { label: "כשלון השמה", cls: "bg-red-900 text-red-200" },
  company_employee_do_not_contact: { label: "🚫 עובד חברה - לא לפנות", cls: "bg-orange-900 text-orange-200" },
  company_client_do_not_contact: { label: "🚫 לקוח חברה - לא לפנות", cls: "bg-orange-900 text-orange-200" },
  deleted: { label: "🗑️ נמחקה", cls: "bg-gray-800 text-gray-400" },
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
  const [candidateDetailId, setCandidateDetailId] = useState<string | null>(null);
  const [favoritesOnly, setFavoritesOnly] = useState(false);
  const [formattedCvMatch, setFormattedCvMatch] = useState<Match | null>(null);
  const [page, setPage] = useState(1);
  const PAGE_SIZE = 100;

  const queryClient = useQueryClient();
  const tabParam = `${recruiter}-${subTab}`; // tal-queue, elad-history, etc.

  // Whenever the filter context changes the result set, jump back to page 1 so
  // we never sit on a now-out-of-range page (e.g. page 5 of a 2-page list).
  useEffect(() => {
    setPage(1);
  }, [tabParam, favoritesOnly]);

  const recruiterName = recruiter === "carmit" ? "כרמית" : recruiter === "tal" ? "טל" : "אלעד";
  const counterparty = recruiter === "carmit" ? "התאמה" : recruiter === "tal" ? "מועמד" : "לקוח";

  const matchesQuery = useQuery({
    queryKey: ["recruiter-matches", tabParam, favoritesOnly, page],
    queryFn: () => fetchRecruiterMatches(tabParam, PAGE_SIZE, page, favoritesOnly),
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
    mutationFn: ({ matchId, action, notes }: { matchId: string; action: MatchAction; notes?: string }) =>
      performMatchAction(matchId, action, notes),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["recruiter-matches"] });
      queryClient.invalidateQueries({ queryKey: ["recruiter-status"] });
      setShowActionMenu(null);
    },
  });

  const favoriteMutation = useMutation({
    mutationFn: ({ matchId, isStarred }: { matchId: string; isStarred: boolean }) =>
      setMatchFavorite(matchId, isStarred),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["recruiter-matches"] });
    },
  });

  const matches = matchesQuery.data?.matches ?? [];

  // ---- Pagination derived state ----
  const total = matchesQuery.data?.total ?? 0;
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const rangeStart = total === 0 ? 0 : (page - 1) * PAGE_SIZE + 1;
  const rangeEnd = Math.min(page * PAGE_SIZE, total);

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
      <td className="px-4 py-3">
        <div className="flex items-center gap-2">
          <button
            onClick={() =>
              favoriteMutation.mutate({ matchId: m.id, isStarred: !m.isStarred })
            }
            disabled={favoriteMutation.isPending}
            className={`text-lg leading-none transition disabled:opacity-50 ${
              m.isStarred
                ? "text-orange-400 hover:text-orange-300"
                : "text-gray-600 hover:text-orange-300"
            }`}
            title={m.isStarred ? "הסר ממועדפים" : "סמן כמועדף"}
            aria-label={m.isStarred ? "הסר ממועדפים" : "סמן כמועדף"}
          >
            {m.isStarred ? "★" : "☆"}
          </button>
          <button
            onClick={() => m.candidateId && setCandidateDetailId(m.candidateId)}
            disabled={!m.candidateId}
            className="text-white font-semibold hover:text-indigo-300 hover:underline transition disabled:cursor-default disabled:hover:text-white disabled:no-underline text-right"
            title={m.candidateId ? "הצג תקציר קורות חיים" : undefined}
          >
            {m.candidateName}
          </button>
          {m.isCompanyEmployee && (
            <span
              className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-bold bg-orange-500 text-white ring-1 ring-orange-300 whitespace-nowrap"
              title="מועמד זה הוא עובד חברה — מוצג לבקרה בלבד, לא יועבר לטל"
            >
              🏢 עובד חברה
            </span>
          )}
        </div>
      </td>
      <td className="px-4 py-3 text-gray-300">
        <div className="flex flex-col gap-1.5">
          <span>{m.jobTitle}</span>
          {m.isPlacement && (
            <span
              className="inline-flex items-center gap-1 self-start px-2 py-0.5 rounded-full text-[11px] font-bold text-red-200 bg-red-900/50 border border-red-500/40 animate-pulse"
              title="משרת השמה — אם יתקבל, העובד יהיה עובד של הלקוח ולא של פנדה-טק"
            >
              🔴 השמה{m.jobNumber ? ` ${m.jobNumber}` : ""}
            </span>
          )}
          <GeoMismatchBadge
            mismatch={m.geographicMismatch}
            reason={m.geographicMismatchReason}
          />
        </div>
      </td>
      <td className="px-4 py-3 text-gray-300">{m.company || "—"}</td>
      <td className="px-4 py-3 text-gray-300">{m.contactPersonName || "—"}</td>
      <td className="px-4 py-3 text-gray-400 font-mono">{m.pipedriveDealId ?? "—"}</td>
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
              actionMutation.mutate({ matchId: m.id, action: "delete" });
            }
          }}
          onMarkCompanyEmployee={() => {
            if (
              window.confirm(
                `לסמן את ${m.candidateName} כ"עובד חברה - לא לפנות"?\n` +
                  `כל ההתאמות של מועמד זה במערכת יועברו למצב זה ולא תתבצע אליו פנייה.`
              )
            ) {
              actionMutation.mutate({ matchId: m.id, action: "mark_company_employee" });
            }
          }}
          onMarkCompanyClient={() => {
            if (
              window.confirm(
                `לסמן את ${m.candidateName} כ"לקוח חברה - לא לפנות"?\n` +
                  `כל ההתאמות של מועמד זה במערכת יועברו למצב זה ולא תתבצע אליו פנייה.`
              )
            ) {
              actionMutation.mutate({ matchId: m.id, action: "mark_company_client" });
            }
          }}
          onHandToHuman={() => actionMutation.mutate({ matchId: m.id, action: "hand_to_human" })}
          onReturnFromHuman={() => actionMutation.mutate({ matchId: m.id, action: "return_from_human" })}
          onConversation={() => {
            setSelectedMatchId(m.id);
            setShowConversationModal(true);
          }}
          onDetail={() => setDetailMatchId(m.id)}
          onFormattedCv={() => setFormattedCvMatch(m)}
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
            label={total > 0 ? `מוצג ${rangeStart}–${rangeEnd} מתוך ${total}` : "סה״כ בתצוגה"}
            value={total}
            tone="gray"
          />
        </div>
      )}

      {/* Favorites filter — show only starred matches */}
      <div className="flex items-center">
        <button
          onClick={() => setFavoritesOnly((v) => !v)}
          className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded text-sm font-semibold transition border ${
            favoritesOnly
              ? "bg-orange-900/40 border-orange-600 text-orange-200"
              : "bg-gray-800 border-gray-700 text-gray-300 hover:text-white"
          }`}
          title="הצג רק התאמות שסומנו כמועדפים"
        >
          <span className={favoritesOnly ? "text-orange-400" : "text-gray-500"}>★</span>
          מועדפים בלבד
        </button>
      </div>

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
                  <th className="px-4 py-3 font-semibold">שם לקוח</th>
                  <th className="px-4 py-3 font-semibold">איש קשר לקוח</th>
                  <th className="px-4 py-3 font-semibold">מספר משרה</th>
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
                        <td colSpan={10} className="px-4 py-2 text-indigo-200 font-semibold">
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

          {/* Pagination — classic prev/next. The list can run to thousands of
              matches; we load one PAGE_SIZE page at a time from the server. */}
          {totalPages > 1 && (
            <div className="flex items-center justify-between text-sm">
              <span className="text-gray-400">
                מוצג {rangeStart}–{rangeEnd} מתוך {total}
              </span>
              <div className="flex items-center gap-2">
                <button
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                  disabled={page <= 1 || matchesQuery.isFetching}
                  className="px-3 py-1.5 rounded bg-gray-800 border border-gray-700 text-gray-200 hover:text-white disabled:opacity-40 disabled:cursor-not-allowed transition"
                >
                  ▶ הקודם
                </button>
                <span className="text-gray-300 px-2">
                  עמוד {page} מתוך {totalPages}
                </span>
                <button
                  onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                  disabled={page >= totalPages || matchesQuery.isFetching}
                  className="px-3 py-1.5 rounded bg-gray-800 border border-gray-700 text-gray-200 hover:text-white disabled:opacity-40 disabled:cursor-not-allowed transition"
                >
                  הבא ◀
                </button>
              </div>
            </div>
          )}

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

          {/* CV summary — opened by clicking a candidate's name. Same modal the
              candidates-database screen uses, so the summary is identical. */}
          {candidateDetailId && (
            <CandidateDetailModal
              id={candidateDetailId}
              onClose={() => setCandidateDetailId(null)}
            />
          )}

          {/* Panda-Tech CV review — generate / preview / approve before Elad
              delivers it to the client. */}
          {formattedCvMatch && (
            <FormattedCvModal
              match={formattedCvMatch}
              onClose={() => setFormattedCvMatch(null)}
            />
          )}
        </>
      )}
    </div>
  );
}

// Panda-Tech formatted-CV review modal — the human-in-the-loop gate. The client
// only ever receives a CV that a person has previewed and approved here.
function FormattedCvModal({ match, onClose }: { match: Match; onClose: () => void }) {
  const queryClient = useQueryClient();
  const cvQuery = useQuery({
    queryKey: ["formatted-cv", match.id],
    queryFn: () => fetchFormattedCv(match.id),
  });

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ["formatted-cv", match.id] });
    queryClient.invalidateQueries({ queryKey: ["recruiter-matches"] });
  };

  const genMutation = useMutation({
    mutationFn: (force: boolean) => generateFormattedCv(match.id, force),
    onSuccess: invalidate,
  });
  const approveMutation = useMutation({
    mutationFn: () => approveFormattedCv(match.id),
    onSuccess: invalidate,
  });
  const rejectMutation = useMutation({
    mutationFn: (reason?: string) => rejectFormattedCv(match.id, reason),
    onSuccess: invalidate,
  });
  const emailMutation = useMutation({
    mutationFn: (to: string) => emailFormattedCv(match.id, to),
    onSuccess: (res) => {
      if (res.success) window.alert("✓ קורות החיים נשלחו במייל");
      else window.alert("שליחת המייל נכשלה: " + (res.error || "שגיאה לא ידועה"));
    },
    onError: (e: unknown) => window.alert("שליחת המייל נכשלה: " + (e as Error).message),
  });

  const cv = cvQuery.data;
  const busy =
    genMutation.isPending || approveMutation.isPending ||
    rejectMutation.isPending || emailMutation.isPending;

  const statusLabel: Record<string, string> = {
    generated: "נוצר — ממתין לאישור",
    approved: "אושר ✓",
    rejected: "נדחה — דורש הפקה מחדש",
  };

  return (
    <div dir="rtl" className="fixed inset-0 bg-black/50 flex items-center justify-center z-[60] p-4">
      <div className="bg-gray-800 rounded-lg border border-gray-700 w-full max-w-4xl h-[88vh] flex flex-col">
        <div className="border-b border-gray-700 p-4 flex justify-between items-center">
          <button onClick={onClose} className="text-gray-400 hover:text-white text-2xl">×</button>
          <h2 className="text-white font-semibold">קורות חיים בפורמט פנדה-טק — {match.candidateName}</h2>
          <div className="text-sm">
            {cv?.status ? (
              <span className={`px-2 py-0.5 rounded text-xs font-semibold ${
                cv.status === "approved" ? "bg-emerald-900 text-emerald-200"
                : cv.status === "rejected" ? "bg-red-900 text-red-200"
                : "bg-yellow-900 text-yellow-200"
              }`}>{statusLabel[cv.status] || cv.status}</span>
            ) : (
              <span className="px-2 py-0.5 rounded text-xs bg-gray-700 text-gray-300">טרם הופק</span>
            )}
          </div>
        </div>

        {cv?.clientApproved && cv?.status !== "approved" && (
          <div className="bg-amber-900/40 border-b border-amber-700 text-amber-100 text-sm px-4 py-2">
            ⏳ הלקוח כבר ביקש את קורות החיים — לאחר אישורכם כאן הם יישלחו אליו אוטומטית.
          </div>
        )}
        {cv?.error && (
          <div className="bg-red-900/40 border-b border-red-700 text-red-100 text-sm px-4 py-2">
            {cv.error}
          </div>
        )}

        <div className="flex-1 overflow-hidden bg-gray-900">
          {cvQuery.isLoading ? (
            <div className="h-full flex items-center justify-center text-gray-400">טוען…</div>
          ) : cv?.previewUrl ? (
            <iframe title="preview" src={cv.previewUrl} className="w-full h-full" />
          ) : (
            <div className="h-full flex flex-col items-center justify-center text-gray-400 gap-3">
              <p>עדיין לא הופקו קורות חיים בפורמט פנדה-טק עבור מועמד זה.</p>
              <button
                onClick={() => genMutation.mutate(false)}
                disabled={busy}
                className="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 text-white rounded text-sm disabled:opacity-50"
              >
                {genMutation.isPending ? "מפיק…" : "הפק קורות חיים"}
              </button>
            </div>
          )}
        </div>

        <div className="border-t border-gray-700 p-4 flex items-center gap-2 justify-between">
          <div className="flex gap-2">
            <button
              onClick={() => genMutation.mutate(true)}
              disabled={busy}
              className="px-3 py-2 bg-gray-700 hover:bg-gray-600 text-gray-200 rounded text-sm disabled:opacity-50"
            >
              {genMutation.isPending ? "מפיק…" : "↻ הפק מחדש"}
            </button>
            <button
              onClick={() => {
                const reason = window.prompt("סיבת דחייה (לא חובה):") ?? undefined;
                rejectMutation.mutate(reason);
              }}
              disabled={busy || !cv?.path}
              className="px-3 py-2 bg-red-900 hover:bg-red-800 text-red-100 rounded text-sm disabled:opacity-50"
            >
              ✕ דחה
            </button>
            {cv?.previewUrl && (
              <a
                href={cv.previewUrl}
                download={`PandaTech_CV_${match.candidateName || match.id}.pdf`}
                target="_blank"
                rel="noopener noreferrer"
                className="px-3 py-2 bg-gray-700 hover:bg-gray-600 text-gray-200 rounded text-sm"
              >
                ⬇ הורד PDF
              </a>
            )}
            <button
              onClick={() => {
                const to = window.prompt("כתובת מייל לשליחת קורות החיים:");
                if (to && to.trim()) emailMutation.mutate(to.trim());
              }}
              disabled={busy || cv?.status !== "approved"}
              title={cv?.status !== "approved" ? "יש לאשר את קורות החיים לפני שליחה במייל" : "שלח במייל עם קובץ מצורף"}
              className="px-3 py-2 bg-blue-900 hover:bg-blue-800 text-blue-100 rounded text-sm disabled:opacity-50"
            >
              {emailMutation.isPending ? "שולח…" : "✉ שלח במייל"}
            </button>
          </div>
          <button
            onClick={() => approveMutation.mutate()}
            disabled={busy || !cv?.path || cv?.status === "approved"}
            className="px-5 py-2 bg-emerald-600 hover:bg-emerald-500 text-white font-semibold rounded text-sm disabled:opacity-50"
          >
            {approveMutation.isPending
              ? "מאשר…"
              : cv?.clientApproved
              ? "✓ אשר ושלח ללקוח"
              : "✓ אשר קורות חיים"}
          </button>
        </div>
      </div>
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
  onMarkCompanyEmployee,
  onMarkCompanyClient,
  onHandToHuman,
  onReturnFromHuman,
  onConversation,
  onDetail,
  onFormattedCv,
  isLoading,
}: {
  match: Match;
  recruiter: string;
  isOpen: boolean;
  onToggle: () => void;
  onActivate: () => void;
  onReject: () => void;
  onMarkCompanyEmployee: () => void;
  onMarkCompanyClient: () => void;
  onHandToHuman: () => void;
  onReturnFromHuman: () => void;
  onConversation: () => void;
  onDetail: () => void;
  onFormattedCv: () => void;
  isLoading: boolean;
}) {
  const isInQueue = recruiter === "carmit"
    ? match.state === "found"
    : (match.state === `sent_to_${recruiter}` || match.state === `${recruiter}_conversation`);
  // Handed to a human: the agent no longer contacts the candidate. Only Carmit
  // has no human-handoff stage. Toggleable from queue states and back.
  const isHandedToHuman = match.state === `${recruiter}_handed_to_human`;
  const canHandToHuman = recruiter !== "carmit" && isInQueue;

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
          {recruiter !== "carmit" && match.state !== "company_employee_do_not_contact" && (
            <button
              onClick={() => {
                onMarkCompanyEmployee();
              }}
              disabled={isLoading}
              className="block w-full text-right px-4 py-2 hover:bg-orange-900 text-orange-200 text-sm disabled:opacity-50 border-b border-gray-600 whitespace-nowrap"
            >
              🚫 עובד חברה - לא לפנות
            </button>
          )}
          {recruiter !== "carmit" && match.state !== "company_client_do_not_contact" && (
            <button
              onClick={() => {
                onMarkCompanyClient();
              }}
              disabled={isLoading}
              className="block w-full text-right px-4 py-2 hover:bg-orange-900 text-orange-200 text-sm disabled:opacity-50 border-b border-gray-600 whitespace-nowrap"
            >
              🚫 לקוח חברה - לא לפנות
            </button>
          )}
          {canHandToHuman && (
            <button
              onClick={() => {
                onHandToHuman();
                onToggle();
              }}
              disabled={isLoading}
              className="block w-full text-right px-4 py-2 hover:bg-amber-900 text-amber-200 text-sm disabled:opacity-50 border-b border-gray-600 whitespace-nowrap"
            >
              👤 הועבר לגורם אנושי
            </button>
          )}
          {isHandedToHuman && (
            <button
              onClick={() => {
                onReturnFromHuman();
                onToggle();
              }}
              disabled={isLoading}
              className="block w-full text-right px-4 py-2 hover:bg-amber-900 text-amber-200 text-sm disabled:opacity-50 border-b border-gray-600 whitespace-nowrap"
            >
              ↩ ביטול העברה לגורם אנושי
            </button>
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
          {recruiter === "elad" && (
            <button
              onClick={() => {
                onFormattedCv();
                onToggle();
              }}
              disabled={isLoading}
              className="block w-full text-right px-4 py-2 hover:bg-emerald-900 text-emerald-200 text-sm disabled:opacity-50 border-b border-gray-600 whitespace-nowrap"
            >
              🐼 קו״ח פנדה-טק (הפקה ואישור)
            </button>
          )}
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

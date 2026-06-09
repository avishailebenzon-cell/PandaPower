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
import { CandidateDetailModal } from "@/components/CandidateDetailModal";

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

// Column definitions drive both the header (with sort) and which are sortable.
interface ColumnDef {
  key: string;
  label: string;
  sortable: boolean;
  align?: "center";
}
const COLUMNS: ColumnDef[] = [
  { key: "name", label: "שם", sortable: true },
  { key: "email", label: "אימייל", sortable: true },
  { key: "phone", label: "טלפון", sortable: true },
  { key: "location", label: "מיקום", sortable: true },
  { key: "clearance_level", label: "סיווג", sortable: true },
  { key: "years_of_experience", label: "ניסיון", sortable: true, align: "center" },
  { key: "__skills", label: "כישורים", sortable: false },
  { key: "detected_language", label: "שפה", sortable: true },
  { key: "overall_confidence_score", label: "ביטחון", sortable: true, align: "center" },
  { key: "skill_readiness_status", label: "סטטוס", sortable: true },
  { key: "created_at", label: "נוצר", sortable: true },
];
const COL_COUNT = COLUMNS.length;

type SortOrder = "asc" | "desc";
type GroupBy = "none" | "clearance_level" | "location";

export function CandidatesDatabasePage() {
  const [searchInput, setSearchInput] = useState("");
  const [search, setSearch] = useState("");
  const [language, setLanguage] = useState<string>("all");
  const [page, setPage] = useState(0);
  const [sort, setSort] = useState<string>("created_at");
  const [order, setOrder] = useState<SortOrder>("desc");
  const [groupBy, setGroupBy] = useState<GroupBy>("none");
  const [selectedId, setSelectedId] = useState<string | null>(null);

  // Debounce search input
  useEffect(() => {
    const t = setTimeout(() => {
      setSearch(searchInput.trim());
      setPage(0);
    }, 350);
    return () => clearTimeout(t);
  }, [searchInput]);

  // Clicking a column header toggles its sort direction (and resets paging).
  const onSort = (col: string) => {
    if (sort === col) {
      setOrder((o) => (o === "asc" ? "desc" : "asc"));
    } else {
      setSort(col);
      setOrder("asc");
    }
    setPage(0);
  };

  const { data, isLoading, isError, refetch, isFetching } = useQuery<DatabaseResponse>({
    queryKey: ["candidates-database", search, language, page, sort, order],
    enabled: groupBy === "none",
    queryFn: () => {
      const params = new URLSearchParams({
        limit: String(PAGE_SIZE),
        offset: String(page * PAGE_SIZE),
        sort,
        order,
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
        <label className="flex items-center gap-2 text-sm text-slate-400">
          קבץ לפי:
          <select
            value={groupBy}
            onChange={(e) => {
              setGroupBy(e.target.value as GroupBy);
              setPage(0);
            }}
            className="px-3 py-2 rounded-lg bg-slate-800 border border-slate-700 text-white text-sm"
          >
            <option value="none">ללא קיבוץ</option>
            <option value="clearance_level">סיווג בטחוני</option>
            <option value="location">מיקום</option>
          </select>
        </label>
        <button
          onClick={() => refetch()}
          className="px-3 py-2 rounded-lg bg-slate-800 border border-slate-700 text-slate-300 hover:bg-slate-700 text-sm"
        >
          🔄 רענן
        </button>
        <div className="text-sm text-slate-400 mr-auto">
          {groupBy === "none" && (isFetching ? "טוען…" : `סה"כ ${total.toLocaleString()} מועמדים`)}
        </div>
      </div>

      {/* Duplicates safeguard banner */}
      <DuplicatesBanner onOpenCandidate={setSelectedId} />

      {groupBy === "none" ? (
        <>
          {/* Flat table */}
          <div className="bg-slate-900 rounded-lg border border-slate-700 overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-sm text-right">
                <SortableHead sort={sort} order={order} onSort={onSort} />
                <tbody>
                  {isLoading ? (
                    <StateRow text="טוען מועמדים…" />
                  ) : isError ? (
                    <StateRow text="שגיאה בטעינת המועמדים. נסה לרענן." error />
                  ) : rows.length === 0 ? (
                    <StateRow text={`לא נמצאו מועמדים${search ? ` עבור "${search}"` : ""}.`} />
                  ) : (
                    rows.map((c) => (
                      <CandidateRow key={c.id} c={c} onClick={() => setSelectedId(c.id)} />
                    ))
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
        </>
      ) : (
        <GroupedView
          groupBy={groupBy}
          search={search}
          language={language}
          sort={sort}
          order={order}
          onSort={onSort}
          onOpenCandidate={setSelectedId}
        />
      )}

      {selectedId && (
        <CandidateDetailModal id={selectedId} onClose={() => setSelectedId(null)} />
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Shared table pieces                                                 */
/* ------------------------------------------------------------------ */

function SortableHead({
  sort,
  order,
  onSort,
}: {
  sort: string;
  order: SortOrder;
  onSort: (col: string) => void;
}) {
  return (
    <thead>
      <tr className="bg-slate-800 text-slate-300 border-b border-slate-700">
        {COLUMNS.map((col) => {
          const active = col.sortable && sort === col.key;
          return (
            <th
              key={col.key}
              onClick={col.sortable ? () => onSort(col.key) : undefined}
              className={`py-3 px-3 font-semibold ${col.align === "center" ? "text-center" : ""} ${
                col.sortable ? "cursor-pointer select-none hover:text-white" : ""
              } ${active ? "text-indigo-400" : ""}`}
            >
              {col.label}
              {col.sortable && (
                <span className="text-[10px] mr-1">
                  {active ? (order === "asc" ? "▲" : "▼") : "↕"}
                </span>
              )}
            </th>
          );
        })}
      </tr>
    </thead>
  );
}

function StateRow({ text, error }: { text: string; error?: boolean }) {
  return (
    <tr>
      <td
        colSpan={COL_COUNT}
        className={`text-center py-10 ${error ? "text-red-400" : "text-slate-400"}`}
      >
        {text}
      </td>
    </tr>
  );
}

function CandidateRow({ c, onClick }: { c: CandidateRow; onClick: () => void }) {
  const readiness = c.skill_readiness_status ? READINESS_LABELS[c.skill_readiness_status] : null;
  return (
    <tr
      onClick={onClick}
      className="border-b border-slate-800 hover:bg-slate-800/60 cursor-pointer transition"
    >
      <td className="py-2.5 px-3 font-semibold text-white whitespace-nowrap">{c.name || "—"}</td>
      <td className="py-2.5 px-3 text-slate-300" dir="ltr">
        {c.email || "—"}
      </td>
      <td className="py-2.5 px-3 text-slate-300 whitespace-nowrap" dir="ltr">
        {c.phone || "—"}
      </td>
      <td className="py-2.5 px-3 text-slate-300 whitespace-nowrap">{c.location || "—"}</td>
      <td className="py-2.5 px-3 text-slate-300 whitespace-nowrap">{c.clearance_level || "—"}</td>
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
            <span className="text-[11px] text-slate-500">+{c.key_skills!.length - 3}</span>
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
}

/* ------------------------------------------------------------------ */
/* Grouped view — one collapsible section per clearance / location     */
/* ------------------------------------------------------------------ */

interface GroupInfo {
  key: string;
  count: number;
}
interface GroupsResponse {
  by: string;
  groups: GroupInfo[];
}

function GroupedView({
  groupBy,
  search,
  language,
  sort,
  order,
  onSort,
  onOpenCandidate,
}: {
  groupBy: Exclude<GroupBy, "none">;
  search: string;
  language: string;
  sort: string;
  order: SortOrder;
  onSort: (col: string) => void;
  onOpenCandidate: (id: string) => void;
}) {
  const [expanded, setExpanded] = useState<string | null>(null);

  const { data, isLoading, isError } = useQuery<GroupsResponse>({
    queryKey: ["candidates-groups", groupBy, search, language],
    queryFn: () => {
      const params = new URLSearchParams({ by: groupBy });
      if (search) params.set("search", search);
      if (language !== "all") params.set("language", language);
      return fetch(`${env.API_BASE_URL}/admin/candidates/database/groups?${params}`).then((r) => {
        if (!r.ok) throw new Error("failed");
        return r.json();
      });
    },
  });

  if (isLoading) return <div className="text-slate-400 py-10 text-center">טוען קיבוץ…</div>;
  if (isError) return <div className="text-red-400 py-10 text-center">שגיאה בטעינת הקיבוץ.</div>;

  const groups = data?.groups || [];

  return (
    <div className="space-y-2">
      <div className="text-sm text-slate-400 mb-1">
        {groups.length} קבוצות לפי {groupBy === "clearance_level" ? "סיווג בטחוני" : "מיקום"}
      </div>
      {groups.map((g) => {
        const isOpen = expanded === g.key;
        return (
          <div key={g.key} className="bg-slate-900 rounded-lg border border-slate-700 overflow-hidden">
            <button
              onClick={() => setExpanded(isOpen ? null : g.key)}
              className="w-full flex items-center justify-between px-4 py-3 hover:bg-slate-800/60 transition text-right"
            >
              <span className="flex items-center gap-2 text-white font-semibold">
                <span className="text-slate-500">{isOpen ? "▼" : "◀"}</span>
                {g.key}
              </span>
              <span className="text-xs px-2 py-0.5 rounded bg-indigo-900 text-indigo-300 border border-indigo-700">
                {g.count.toLocaleString()} מועמדים
              </span>
            </button>
            {isOpen && (
              <GroupRows
                groupBy={groupBy}
                groupKey={g.key}
                search={search}
                language={language}
                sort={sort}
                order={order}
                onSort={onSort}
                onOpenCandidate={onOpenCandidate}
              />
            )}
          </div>
        );
      })}
    </div>
  );
}

const GROUP_ROWS_LIMIT = 500;

function GroupRows({
  groupBy,
  groupKey,
  search,
  language,
  sort,
  order,
  onSort,
  onOpenCandidate,
}: {
  groupBy: Exclude<GroupBy, "none">;
  groupKey: string;
  search: string;
  language: string;
  sort: string;
  order: SortOrder;
  onSort: (col: string) => void;
  onOpenCandidate: (id: string) => void;
}) {
  const { data, isLoading } = useQuery<DatabaseResponse>({
    queryKey: ["candidates-group-rows", groupBy, groupKey, search, language, sort, order],
    queryFn: () => {
      const params = new URLSearchParams({
        limit: String(GROUP_ROWS_LIMIT),
        offset: "0",
        sort,
        order,
      });
      // "—" is the sentinel for empty/NULL values; filter for blank string.
      params.set(groupBy === "clearance_level" ? "clearance" : "location", groupKey === "—" ? "" : groupKey);
      if (search) params.set("search", search);
      if (language !== "all") params.set("language", language);
      return fetch(`${env.API_BASE_URL}/admin/candidates/database?${params}`).then((r) => {
        if (!r.ok) throw new Error("failed");
        return r.json();
      });
    },
  });

  const rows = data?.data || [];

  return (
    <div className="overflow-x-auto border-t border-slate-700">
      <table className="w-full text-sm text-right">
        <SortableHead sort={sort} order={order} onSort={onSort} />
        <tbody>
          {isLoading ? (
            <StateRow text="טוען…" />
          ) : rows.length === 0 ? (
            <StateRow text="אין מועמדים בקבוצה זו." />
          ) : (
            rows.map((c) => (
              <CandidateRow key={c.id} c={c} onClick={() => onOpenCandidate(c.id)} />
            ))
          )}
        </tbody>
      </table>
      {rows.length >= GROUP_ROWS_LIMIT && (
        <div className="text-xs text-amber-400 px-4 py-2">
          מוצגות {GROUP_ROWS_LIMIT} הראשונות בקבוצה. צמצם עם חיפוש כדי לראות את השאר.
        </div>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Duplicates safeguard banner                                         */
/* ------------------------------------------------------------------ */

interface DuplicateGroup {
  match_type: string;
  value: string;
  candidates: Array<{ id: string; name: string; phone: string | null; email: string | null }>;
}
interface DuplicatesResponse {
  total_candidates: number;
  duplicate_groups: DuplicateGroup[];
  group_count: number;
  redundant_records: number;
}

function DuplicatesBanner({ onOpenCandidate }: { onOpenCandidate: (id: string) => void }) {
  const [open, setOpen] = useState(false);
  const { data } = useQuery<DuplicatesResponse>({
    queryKey: ["candidates-duplicates"],
    queryFn: () =>
      fetch(`${env.API_BASE_URL}/admin/candidates/database/duplicates`).then((r) => r.json()),
  });

  if (!data) return null;
  const clean = data.group_count === 0;

  return (
    <div
      className={`mb-4 rounded-lg border px-4 py-2 text-sm ${
        clean
          ? "bg-green-950/40 border-green-800 text-green-300"
          : "bg-amber-950/40 border-amber-800 text-amber-300"
      }`}
    >
      <div className="flex items-center justify-between">
        <span>
          {clean
            ? `✅ אין כפילויות — נבדקו ${data.total_candidates.toLocaleString()} מועמדים (לפי אימייל/טלפון מנורמל).`
            : `⚠️ נמצאו ${data.group_count} קבוצות כפילות (${data.redundant_records} רשומות עודפות).`}
        </span>
        {!clean && (
          <button onClick={() => setOpen((o) => !o)} className="underline text-xs">
            {open ? "הסתר" : "הצג פרטים"}
          </button>
        )}
      </div>
      {!clean && open && (
        <div className="mt-2 space-y-2">
          {data.duplicate_groups.map((g, i) => (
            <div key={i} className="bg-slate-900/60 rounded p-2 border border-slate-700">
              <div className="text-xs text-slate-400 mb-1">
                התאמה לפי {g.match_type === "email" ? "אימייל" : "טלפון"}: {g.value}
              </div>
              <div className="flex flex-wrap gap-2">
                {g.candidates.map((c) => (
                  <button
                    key={c.id}
                    onClick={() => onOpenCandidate(c.id)}
                    className="text-xs px-2 py-1 rounded bg-slate-800 border border-slate-600 text-slate-200 hover:bg-slate-700"
                  >
                    {c.name} ↗
                  </button>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}


/**
 * Jobs List Page
 * Display all job openings synced from Pipedrive
 */

import React, { useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { PipedriveDataTable } from '@/components/PipedriveDataTable';
import { DataFilterPanel } from '@/components/DataFilterPanel';
import { SyncStatusIndicator } from '@/components/SyncStatusIndicator';
import { fetchJobs, runPlacementIngest, JobResponse } from '@/api/pipedrive-data';

export function JobsListPage() {
  const [page, setPage] = useState(1);
  const [limit, setLimit] = useState(50);
  const [search, setSearch] = useState('');
  const [status, setStatus] = useState('');
  const [placementFilter, setPlacementFilter] = useState<'' | 'placement'>('');
  const [sortBy, setSortBy] = useState('title');
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('asc');
  const [groupBy, setGroupBy] = useState<'' | 'company' | 'contact_person' | 'priority_label'>('');
  const [placementRunning, setPlacementRunning] = useState(false);
  const [placementMsg, setPlacementMsg] = useState<string | null>(null);

  const queryClient = useQueryClient();
  const isGrouped = groupBy !== '';

  const handleRunPlacement = async () => {
    setPlacementRunning(true);
    setPlacementMsg(null);
    try {
      const r = await runPlacementIngest(30);
      setPlacementMsg(
        `נסרקו ${r.scanned} מיילים, נמצאו ${r.placement_emails_found} משרות השמה. ` +
          `סה"כ משרות השמה במערכת: ${r.total_placement_jobs ?? '—'}.`
      );
      queryClient.invalidateQueries({ queryKey: ['pipedrive-jobs'] });
    } catch (e) {
      setPlacementMsg(`שגיאה בקליטה: ${(e as Error).message}`);
    } finally {
      setPlacementRunning(false);
    }
  };

  const { data, isLoading, error } = useQuery({
    queryKey: [
      'pipedrive-jobs',
      page,
      limit,
      search,
      status,
      placementFilter,
      sortBy,
      sortOrder,
      isGrouped,
    ],
    // When grouping, pull a large page so groups span the whole dataset.
    queryFn: () =>
      fetchJobs(
        isGrouped ? 1 : page,
        isGrouped ? 1000 : limit,
        search || undefined,
        status || undefined,
        sortBy,
        sortOrder,
        placementFilter === 'placement' ? true : undefined,
      ),
    staleTime: 5 * 60 * 1000,
  });

  const columns = [
    {
      key: 'pipedrive_deal_id',
      label: 'קוד משרה',
      sortable: false,
      width: '8%',
      render: (value: number | null, row: any) => (
        <span className="inline-flex items-center gap-1.5">
          <span
            className={`font-mono text-sm font-bold ${
              row.is_placement ? 'text-amber-400' : 'text-blue-400'
            }`}
          >
            {row.is_placement
              ? row.job_code || row.job_number || 'PL'
              : value
              ? `#${String(value).padStart(4, '0')}`
              : '-'}
          </span>
          {row.is_placement && (
            <span
              className="placement-badge"
              title="משרת השמה — נקלטה אוטומטית ממייל"
            >
              🔴 השמה
            </span>
          )}
        </span>
      ),
    },
    {
      key: 'title',
      label: 'כותרת המשרה',
      sortable: true,
      width: '14%',
    },
    {
      key: 'company',
      label: 'חברה',
      sortable: false,
      width: '9%',
      render: (value: string) => value || '-',
    },
    {
      key: 'contact_person',
      label: 'איש קשר',
      sortable: false,
      width: '8%',
      render: (value: string) => value || '-',
    },
    {
      key: 'location',
      label: 'מיקום',
      width: '8%',
      render: (value: string) => value || '-',
    },
    {
      key: 'security_clearance',
      label: 'סיווג בטחוני',
      width: '8%',
      render: (value: string) => value || '-',
    },
    {
      key: 'description',
      label: 'תיאור משרה',
      width: '12%',
      render: (value: string) => (
        <span className="text-xs text-gray-300" title={value || ''}>
          {value ? (value.length > 50 ? `${value.slice(0, 50)}...` : value) : '-'}
        </span>
      ),
    },
    {
      key: 'qualifications',
      label: 'פירוט המשרה',
      width: '12%',
      render: (value: string) => (
        <span className="text-xs text-gray-300" title={value || ''}>
          {value ? (value.length > 50 ? `${value.slice(0, 50)}...` : value) : '-'}
        </span>
      ),
    },
    {
      key: 'deadline',
      label: 'דדליין',
      sortable: true,
      width: '8%',
      render: (value: string) => value || '-',
    },
    {
      key: 'priority_label',
      label: 'עדיפות',
      sortable: true,
      width: '8%',
      render: (value: string, row: any) => {
        if (!value) return <span className="text-gray-500">-</span>;
        const priorityColors: Record<number, string> = {
          1: 'bg-red-700',
          2: 'bg-orange-700',
          3: 'bg-yellow-700',
          4: 'bg-blue-700',
          5: 'bg-gray-700',
        };
        const color = priorityColors[row.priority] || 'bg-gray-700';
        return (
          <span className={`px-2 py-1 rounded text-xs text-white ${color}`}>
            {value}
          </span>
        );
      },
    },
    {
      key: 'status',
      label: 'סטטוס',
      sortable: true,
      width: '8%',
      render: (value: string) => {
        const statusMap: Record<string, { label: string; color: string }> = {
          open: { label: 'פתוחה', color: 'bg-green-900' },
          filled: { label: 'תפוסה', color: 'bg-red-900' },
          on_hold: { label: 'מושהית', color: 'bg-yellow-900' },
          closed: { label: 'סגורה', color: 'bg-gray-700' },
        };
        const status_info = statusMap[value] || { label: value, color: 'bg-gray-700' };
        return (
          <span
            className={`px-3 py-1 rounded text-xs font-semibold text-white ${status_info.color}`}
          >
            {status_info.label}
          </span>
        );
      },
    },
  ];

  // Placement-specific columns — only meaningful for משרות השמה, shown when the
  // "placement only" filter is active so the regular Pipedrive view stays clean.
  if (placementFilter === 'placement') {
    columns.push(
      {
        key: 'placement_contact_phone',
        label: 'טלפון השמה',
        width: '8%',
        render: (value: string) =>
          value ? (
            <a href={`tel:${value}`} className="text-amber-400 font-mono text-sm" dir="ltr">
              {value}
            </a>
          ) : (
            <span className="text-gray-500">-</span>
          ),
      } as any,
      {
        key: 'placement_external_ref',
        label: 'מס׳ משרה חיצוני',
        width: '8%',
        render: (value: string) =>
          value ? (
            <span className="font-mono text-xs text-gray-300">{value}</span>
          ) : (
            <span className="text-gray-500">-</span>
          ),
      } as any
    );
  }

  const filterOptions = [
    {
      key: 'status',
      label: 'סטטוס משרה',
      type: 'select' as const,
      options: [
        { value: 'open', label: 'פתוחה' },
        { value: 'filled', label: 'תפוסה' },
        { value: 'on_hold', label: 'מושהית' },
        { value: 'closed', label: 'סגורה' },
      ],
    },
  ];

  if (error) {
    return (
      <div className="p-8 bg-gray-900 min-h-screen" dir="rtl">
        <div className="text-red-500 text-center">
          שגיאה בטעינת הנתונים: {(error as Error).message}
        </div>
      </div>
    );
  }

  return (
    <div className="p-8 bg-gray-900 min-h-screen" dir="rtl">
      {/* Blinking badge for placement jobs (משרות השמה) */}
      <style>{`
        .placement-badge {
          display: inline-flex;
          align-items: center;
          gap: 4px;
          font-size: 11px;
          font-weight: 700;
          color: #fca5a5;
          background: rgba(127, 29, 29, 0.5);
          border: 1px solid rgba(248, 113, 113, 0.4);
          border-radius: 9999px;
          padding: 1px 8px;
          white-space: nowrap;
          animation: placement-blink 1.2s ease-in-out infinite;
        }
        @keyframes placement-blink {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.3; }
        }
      `}</style>
      {/* Header */}
      <div className="space-y-2 mb-8">
        <h1 className="text-3xl font-bold text-white">משרות</h1>
        <p className="text-gray-400">
          רשימת כל המשרות הפתוחות המסונכרות מ-Pipedrive
        </p>
      </div>

      {/* Last Sync Info */}
      {data?.last_sync && (
        <div className="mb-6 p-4 bg-gray-800 border border-gray-700 rounded-lg">
          <div className="flex items-center justify-between">
            <span className="text-gray-300">סינכרון אחרון:</span>
            <SyncStatusIndicator
              lastSynced={data.last_sync}
              syncStatus="success"
            />
          </div>
        </div>
      )}

      {/* Group By Control */}
      <div className="mb-6 flex items-center gap-3">
        <label className="text-gray-300 text-sm font-semibold">קבץ לפי:</label>
        <select
          value={groupBy}
          onChange={(e) => {
            setGroupBy(e.target.value as typeof groupBy);
            setPage(1);
          }}
          className="px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white text-sm focus:outline-none focus:border-blue-500"
        >
          <option value="">ללא קיבוץ</option>
          <option value="company">חברה</option>
          <option value="contact_person">איש קשר</option>
          <option value="priority_label">עדיפות</option>
        </select>

        <span className="mx-2 h-5 w-px bg-gray-700" />
        <button
          type="button"
          onClick={() => {
            setPlacementFilter((p) => (p === 'placement' ? '' : 'placement'));
            setPage(1);
          }}
          className={`px-3 py-2 rounded-lg text-sm font-semibold border transition-colors ${
            placementFilter === 'placement'
              ? 'bg-red-900/40 border-red-500 text-red-200'
              : 'bg-gray-800 border-gray-700 text-gray-300 hover:border-red-500/60'
          }`}
          title="הצג רק משרות השמה שנקלטו אוטומטית ממייל"
        >
          🔴 משרות השמה בלבד
        </button>

        <button
          type="button"
          onClick={handleRunPlacement}
          disabled={placementRunning}
          className="px-3 py-2 rounded-lg text-sm font-semibold border bg-gray-800 border-gray-700 text-gray-300 hover:border-amber-500/60 disabled:opacity-50"
          title="סרוק עכשיו את המיילים האחרונים וקלוט משרות השמה חדשות"
        >
          {placementRunning ? '⏳ סורק…' : '⟳ סרוק משרות השמה עכשיו'}
        </button>
      </div>

      {placementMsg && (
        <div className="mb-4 text-sm text-amber-300 bg-amber-900/20 border border-amber-700/40 rounded-lg px-4 py-2">
          {placementMsg}
        </div>
      )}

      {/* Filters */}
      <div className="mb-6">
        <DataFilterPanel
          filters={filterOptions}
          onFilterChange={(key, value) => {
            if (key === 'status') {
              setStatus(value);
              setPage(1);
            }
          }}
          onReset={() => {
            setStatus('');
            setPage(1);
          }}
        />
      </div>

      {/* Data Table */}
      {isGrouped ? (
        <GroupedJobsTable
          columns={columns}
          data={data?.data || []}
          groupBy={groupBy as 'company' | 'contact_person' | 'priority_label'}
          isLoading={isLoading}
        />
      ) : (
        <PipedriveDataTable
          columns={columns}
          data={data?.data || []}
          total={data?.total || 0}
          page={page}
          limit={limit}
          totalPages={data?.total_pages || 0}
          isLoading={isLoading}
          searchPlaceholder="חיפוש לפי שם משרה או חברה..."
          onSearch={setSearch}
          onSort={(key, order) => {
            setSortBy(key);
            setSortOrder(order);
            setPage(1);
          }}
          onPageChange={setPage}
          onLimitChange={setLimit}
          lastSync={data?.last_sync}
        />
      )}
    </div>
  );
}

interface GroupedJobsTableProps {
  columns: Array<{ key: string; label: string; render?: (value: any, row: any) => React.ReactNode }>;
  data: any[];
  groupBy: 'company' | 'contact_person' | 'priority_label';
  isLoading?: boolean;
}

function GroupedJobsTable({ columns, data, groupBy, isLoading }: GroupedJobsTableProps) {
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({});

  if (isLoading) {
    return (
      <div className="px-4 py-8 text-center text-gray-400 bg-gray-800 border border-gray-700 rounded-lg">
        טוען...
      </div>
    );
  }

  if (data.length === 0) {
    return (
      <div className="px-4 py-8 text-center text-gray-400 bg-gray-800 border border-gray-700 rounded-lg">
        אין נתונים להצגה
      </div>
    );
  }

  // Build groups preserving insertion order
  const groups: Record<string, any[]> = {};
  for (const row of data) {
    const raw = row[groupBy];
    const key = raw === null || raw === undefined || raw === '' ? 'ללא ערך' : String(raw);
    if (!groups[key]) groups[key] = [];
    groups[key].push(row);
  }
  const groupKeys = Object.keys(groups).sort((a, b) => a.localeCompare(b, 'he'));

  return (
    <div className="space-y-3" dir="rtl">
      {groupKeys.map((groupKey) => {
        const rows = groups[groupKey];
        const isCollapsed = collapsed[groupKey];
        return (
          <div
            key={groupKey}
            className="bg-gray-800 border border-gray-700 rounded-lg overflow-hidden"
          >
            <button
              onClick={() =>
                setCollapsed((prev) => ({ ...prev, [groupKey]: !prev[groupKey] }))
              }
              className="w-full flex items-center justify-between px-4 py-3 bg-gray-900 hover:bg-gray-700 transition-colors"
            >
              <span className="flex items-center gap-2 font-semibold text-white">
                <span className="text-xs">{isCollapsed ? '▶' : '▼'}</span>
                {groupKey}
              </span>
              <span className="px-2 py-1 rounded text-xs bg-blue-700 text-white">
                {rows.length}
              </span>
            </button>
            {!isCollapsed && (
              <div className="overflow-x-auto">
                <table className="w-full text-right text-sm">
                  <thead className="bg-gray-900 border-b border-gray-700">
                    <tr>
                      {columns.map((column) => (
                        <th
                          key={column.key}
                          className="px-4 py-2 font-semibold text-gray-300 whitespace-nowrap"
                        >
                          {column.label}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((row, idx) => (
                      <tr
                        key={row.id || idx}
                        className="border-b border-gray-700 hover:bg-gray-700 transition-colors"
                      >
                        {columns.map((column) => (
                          <td key={column.key} className="px-4 py-3 text-gray-300">
                            {column.render
                              ? column.render(row[column.key], row)
                              : row[column.key] ?? '-'}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

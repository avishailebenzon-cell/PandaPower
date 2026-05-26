/**
 * Jobs List Page
 * Display all job openings synced from Pipedrive
 */

import React, { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { PipedriveDataTable } from '@/components/PipedriveDataTable';
import { DataFilterPanel } from '@/components/DataFilterPanel';
import { SyncStatusIndicator } from '@/components/SyncStatusIndicator';
import { fetchJobs, JobResponse } from '@/api/pipedrive-data';

export function JobsListPage() {
  const [page, setPage] = useState(1);
  const [limit, setLimit] = useState(50);
  const [search, setSearch] = useState('');
  const [status, setStatus] = useState('');
  const [sortBy, setSortBy] = useState('title');
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('asc');

  const { data, isLoading, error } = useQuery({
    queryKey: [
      'pipedrive-jobs',
      page,
      limit,
      search,
      status,
      sortBy,
      sortOrder,
    ],
    queryFn: () =>
      fetchJobs(page, limit, search || undefined, status || undefined, sortBy, sortOrder),
    staleTime: 5 * 60 * 1000,
  });

  const columns = [
    {
      key: 'pipedrive_deal_id',
      label: 'קוד משרה',
      sortable: false,
      width: '6%',
      render: (value: number | null) => (
        <span className="font-mono text-sm font-bold text-blue-400">
          {value ? `#${String(value).padStart(4, '0')}` : '-'}
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
    </div>
  );
}

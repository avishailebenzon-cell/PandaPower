/**
 * Organizations Page
 * Display all organizations synced from Pipedrive
 */

import React, { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { PipedriveDataTable } from '@/components/PipedriveDataTable';
import { DataFilterPanel } from '@/components/DataFilterPanel';
import { SyncStatusIndicator } from '@/components/SyncStatusIndicator';
import { fetchOrganizations, OrganizationResponse } from '@/api/pipedrive-data';

export function OrganizationsPage() {
  const [page, setPage] = useState(1);
  const [limit, setLimit] = useState(50);
  const [search, setSearch] = useState('');
  const [industry, setIndustry] = useState('');
  const [sortBy, setSortBy] = useState('name');
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('asc');

  const { data, isLoading, error } = useQuery({
    queryKey: [
      'pipedrive-organizations',
      page,
      limit,
      search,
      industry,
      sortBy,
      sortOrder,
    ],
    queryFn: () =>
      fetchOrganizations(
        page,
        limit,
        search || undefined,
        industry || undefined,
        sortBy,
        sortOrder
      ),
    staleTime: 5 * 60 * 1000,
  });

  const columns = [
    {
      key: 'pipedrive_org_id',
      label: 'קוד ארגון',
      sortable: false,
      width: '8%',
      render: (value: number | null) => (
        <span className="font-mono text-sm font-bold text-blue-400">
          {value ? `#${String(value).padStart(4, '0')}` : '-'}
        </span>
      ),
    },
    {
      key: 'name',
      label: 'שם הארגון',
      sortable: true,
      width: '16%',
    },
    {
      key: 'industry',
      label: 'ענף',
      sortable: true,
      width: '13%',
    },
    {
      key: 'size',
      label: 'גודל',
      width: '12%',
    },
    {
      key: 'location',
      label: 'מיקום',
      width: '13%',
    },
    {
      key: 'employee_count',
      label: 'מספר עובדים',
      sortable: true,
      width: '12%',
    },
    {
      key: 'contacts_count',
      label: 'אנשי קשר',
      width: '12%',
    },
    {
      key: 'sync_status',
      label: 'סטטוס סינכרון',
      width: '12%',
      // Custom render that ALSO reads `last_synced_at` from the row so the
      // indicator can compute a real color (🟢/🟡/🔴) — passing only the
      // status string makes it default to "לא סונכרן" because lastSynced is undefined.
      render: (value: string, row: any) => (
        <SyncStatusIndicator
          syncStatus={value || row?.sync_status || 'completed'}
          lastSynced={row?.last_synced_at || row?.pipedrive_last_synced_at || row?.created_at}
          className="text-xs"
        />
      ),
    },
  ];

  const filterOptions = [
    {
      key: 'industry',
      label: 'ענף',
      type: 'select' as const,
      options: [
        { value: 'technology', label: 'טכנולוגיה' },
        { value: 'finance', label: 'פיננסים' },
        { value: 'healthcare', label: 'בריאות' },
        { value: 'manufacturing', label: 'ייצור' },
        { value: 'retail', label: 'קמעונאות' },
        { value: 'other', label: 'אחר' },
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
        <h1 className="text-3xl font-bold text-white">ארגונים</h1>
        <p className="text-gray-400">
          רשימת כל הארגונים המסונכרים מ-Pipedrive
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
            if (key === 'industry') {
              setIndustry(value);
              setPage(1);
            }
          }}
          onReset={() => {
            setIndustry('');
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
        searchPlaceholder="חיפוש לפי שם ארגון..."
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

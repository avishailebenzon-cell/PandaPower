/**
 * Employees Page
 * Display all company employees synced from Pipedrive
 */

import React, { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { PipedriveDataTable } from '@/components/PipedriveDataTable';
import { SyncStatusIndicator } from '@/components/SyncStatusIndicator';
import { fetchEmployees, EmployeeResponse } from '@/api/pipedrive-data';

export function EmployeesPage() {
  const [page, setPage] = useState(1);
  const [limit, setLimit] = useState(50);
  const [search, setSearch] = useState('');
  const [sortBy, setSortBy] = useState('name');
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('asc');

  const { data, isLoading, error } = useQuery({
    queryKey: ['pipedrive-employees', page, limit, search, sortBy, sortOrder],
    queryFn: () =>
      fetchEmployees(page, limit, search || undefined, sortBy, sortOrder),
    staleTime: 5 * 60 * 1000, // 5 minutes
  });

  const columns = [
    {
      key: 'pipedrive_person_id',
      label: 'קוד',
      sortable: false,
      width: '7%',
      render: (value: number | null) => (
        <span className="font-mono text-sm font-bold text-blue-400">
          {value ? `#${String(value).padStart(4, '0')}` : '-'}
        </span>
      ),
    },
    {
      key: 'name',
      label: 'שם עובד',
      sortable: true,
      width: '14%',
    },
    {
      key: 'email',
      label: 'דוא"ל',
      width: '17%',
      render: (value: string) => value || '-',
    },
    {
      key: 'phone',
      label: 'טלפון',
      width: '10%',
      render: (value: string) => value || '-',
    },
    {
      key: 'company',
      label: 'חברה',
      width: '10%',
      render: (value: string) => value || '-',
    },
    {
      key: 'professional_domain',
      label: 'תחום מקצועי',
      width: '23%',
      render: (value: string) => {
        if (!value) return <span className="text-gray-500">-</span>;
        const domains = value.split(', ');
        return (
          <div className="flex flex-wrap gap-1" title={value}>
            {domains.slice(0, 3).map((d, i) => (
              <span key={i} className="px-2 py-0.5 rounded text-xs bg-blue-900 text-blue-200">
                {d}
              </span>
            ))}
            {domains.length > 3 && (
              <span className="px-2 py-0.5 rounded text-xs bg-gray-700 text-gray-300">
                +{domains.length - 3}
              </span>
            )}
          </div>
        );
      },
    },
    {
      key: 'security_clearance_level',
      label: 'סיווג בטחוני',
      width: '9%',
      render: (value: string) => {
        if (!value) return <span className="text-gray-500">-</span>;
        return (
          <span className="px-2 py-0.5 rounded text-xs bg-purple-900 text-purple-200">
            {value}
          </span>
        );
      },
    },
    {
      key: 'sync_status',
      label: 'סינכרון',
      width: '10%',
      render: (value: string, row: any) => (
        <SyncStatusIndicator
          syncStatus={value}
          lastSynced={row?.last_synced || row?.pipedrive_last_synced_at}
          className="text-xs"
        />
      ),
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
        <h1 className="text-3xl font-bold text-white">עובדי החברה</h1>
        <p className="text-gray-400">
          רשימת כל עובדי החברה המסונכרים מ-Pipedrive
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

      {/* Data Table */}
      <PipedriveDataTable
        columns={columns}
        data={data?.data || []}
        total={data?.total || 0}
        page={page}
        limit={limit}
        totalPages={data?.total_pages || 0}
        isLoading={isLoading}
        searchPlaceholder="חיפוש לפי שם או דוא״ל..."
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

/**
 * Reusable Pipedrive Data Table Component
 * Displays paginated data with search, sorting, and filtering
 */

import React, { useState } from 'react';
import { SyncStatusIndicator } from './SyncStatusIndicator';

interface Column {
  key: string;
  label: string;
  sortable?: boolean;
  render?: (value: any, row: any) => React.ReactNode;
  width?: string;
}

interface PipedriveDataTableProps {
  columns: Column[];
  data: any[];
  total: number;
  page: number;
  limit: number;
  totalPages: number;
  isLoading?: boolean;
  searchPlaceholder?: string;
  onSearch?: (search: string) => void;
  onSort?: (sortBy: string, sortOrder: 'asc' | 'desc') => void;
  onPageChange?: (page: number) => void;
  onLimitChange?: (limit: number) => void;
  lastSync?: string;
}

export function PipedriveDataTable({
  columns,
  data,
  total,
  page,
  limit,
  totalPages,
  isLoading = false,
  searchPlaceholder = 'חיפוש...',
  onSearch,
  onSort,
  onPageChange,
  onLimitChange,
  lastSync,
}: PipedriveDataTableProps) {
  const [searchTerm, setSearchTerm] = useState('');
  const [sortBy, setSortBy] = useState('');
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('asc');

  const handleSearch = (value: string) => {
    setSearchTerm(value);
    onSearch?.(value);
  };

  const handleSort = (columnKey: string) => {
    const newSortOrder = sortBy === columnKey && sortOrder === 'asc' ? 'desc' : 'asc';
    setSortBy(columnKey);
    setSortOrder(newSortOrder);
    onSort?.(columnKey, newSortOrder);
  };

  const handleLimitChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const newLimit = parseInt(e.target.value, 10);
    onLimitChange?.(newLimit);
  };

  return (
    <div className="space-y-4" dir="rtl">
      {/* Header Controls */}
      <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
        {/* Search Bar */}
        <div className="flex-1 max-w-sm">
          <input
            type="text"
            placeholder={searchPlaceholder}
            value={searchTerm}
            onChange={(e) => handleSearch(e.target.value)}
            className="w-full px-4 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:border-blue-500"
          />
        </div>

        {/* Sync Status */}
        {lastSync && (
          <div className="flex items-center gap-2">
            <span className="text-gray-400 text-sm">סינכרון אחרון:</span>
            <SyncStatusIndicator lastSynced={lastSync} syncStatus="success" />
          </div>
        )}
      </div>

      {/* Table */}
      <div className="overflow-x-auto bg-gray-800 border border-gray-700 rounded-lg">
        <table className="w-full text-right text-sm">
          <thead className="bg-gray-900 border-b border-gray-700">
            <tr>
              {columns.map((column) => (
                <th
                  key={column.key}
                  className={`px-4 py-3 font-semibold text-gray-300 whitespace-nowrap ${
                    column.width ? column.width : ''
                  } ${
                    column.sortable
                      ? 'cursor-pointer hover:bg-gray-800 transition-colors'
                      : ''
                  }`}
                  onClick={() =>
                    column.sortable && handleSort(column.key)
                  }
                  style={column.width ? { width: column.width } : {}}
                >
                  <div className="flex items-center justify-end gap-2">
                    {column.label}
                    {column.sortable && (
                      <span className="text-xs">
                        {sortBy === column.key
                          ? sortOrder === 'asc'
                            ? '▲'
                            : '▼'
                          : '▪'}
                      </span>
                    )}
                  </div>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {isLoading ? (
              <tr>
                <td
                  colSpan={columns.length}
                  className="px-4 py-8 text-center text-gray-400"
                >
                  טוען...
                </td>
              </tr>
            ) : data.length === 0 ? (
              <tr>
                <td
                  colSpan={columns.length}
                  className="px-4 py-8 text-center text-gray-400"
                >
                  אין נתונים להצגה
                </td>
              </tr>
            ) : (
              data.map((row, idx) => (
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
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Pagination Controls */}
      <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
        {/* Rows Per Page */}
        <div className="flex items-center gap-2">
          <label className="text-gray-400 text-sm">שורות בעמוד:</label>
          <select
            value={limit}
            onChange={handleLimitChange}
            className="px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white text-sm focus:outline-none focus:border-blue-500"
          >
            <option value={25}>25</option>
            <option value={50}>50</option>
            <option value={100}>100</option>
          </select>
        </div>

        {/* Page Info */}
        <div className="text-sm text-gray-400">
          דף <span className="font-semibold text-white">{page}</span> מתוך{' '}
          <span className="font-semibold text-white">{totalPages}</span> • סה״כ:{' '}
          <span className="font-semibold text-white">{total}</span>
        </div>

        {/* Pagination Buttons */}
        <div className="flex gap-2">
          <button
            onClick={() => onPageChange?.(Math.max(1, page - 1))}
            disabled={page === 1 || isLoading}
            className="px-4 py-2 bg-gray-700 hover:bg-gray-600 disabled:bg-gray-800 disabled:text-gray-600 rounded-lg text-white text-sm font-semibold transition-colors"
          >
            הקודם
          </button>
          <button
            onClick={() => onPageChange?.(Math.min(totalPages, page + 1))}
            disabled={page === totalPages || isLoading}
            className="px-4 py-2 bg-gray-700 hover:bg-gray-600 disabled:bg-gray-800 disabled:text-gray-600 rounded-lg text-white text-sm font-semibold transition-colors"
          >
            הבא
          </button>
        </div>
      </div>
    </div>
  );
}

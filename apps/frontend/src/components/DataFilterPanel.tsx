/**
 * Data Filter Panel Component
 * Advanced filtering options for Pipedrive data tables
 */

import React, { useState } from 'react';

interface FilterOption {
  key: string;
  label: string;
  type: 'select' | 'text' | 'date';
  options?: { value: string; label: string }[];
  placeholder?: string;
}

interface DataFilterPanelProps {
  filters: FilterOption[];
  onFilterChange?: (filterKey: string, value: string) => void;
  onReset?: () => void;
  isOpen?: boolean;
  onToggle?: (open: boolean) => void;
}

export function DataFilterPanel({
  filters,
  onFilterChange,
  onReset,
  isOpen = false,
  onToggle,
}: DataFilterPanelProps) {
  const [filterValues, setFilterValues] = useState<Record<string, string>>({});
  const [isExpanded, setIsExpanded] = useState(isOpen);

  const handleFilterChange = (filterKey: string, value: string) => {
    setFilterValues((prev) => ({
      ...prev,
      [filterKey]: value,
    }));
    onFilterChange?.(filterKey, value);
  };

  const handleReset = () => {
    setFilterValues({});
    onReset?.();
  };

  const handleToggle = () => {
    setIsExpanded(!isExpanded);
    onToggle?.(!isExpanded);
  };

  const activeFilterCount = Object.values(filterValues).filter(
    (v) => v !== ''
  ).length;

  return (
    <div className="space-y-2" dir="rtl">
      {/* Filter Button */}
      <button
        onClick={handleToggle}
        className="flex items-center gap-2 px-4 py-2 bg-gray-800 hover:bg-gray-700 border border-gray-700 rounded-lg text-white text-sm font-semibold transition-colors"
      >
        <span>🔍</span>
        <span>סינון</span>
        {activeFilterCount > 0 && (
          <span className="ml-2 px-2 py-0.5 bg-blue-600 rounded text-xs">
            {activeFilterCount}
          </span>
        )}
      </button>

      {/* Filter Panel */}
      {isExpanded && (
        <div className="space-y-3 p-4 bg-gray-800 border border-gray-700 rounded-lg">
          {filters.map((filter) => (
            <div key={filter.key} className="space-y-1">
              <label className="text-sm font-semibold text-gray-300">
                {filter.label}
              </label>

              {filter.type === 'select' && (
                <select
                  value={filterValues[filter.key] || ''}
                  onChange={(e) =>
                    handleFilterChange(filter.key, e.target.value)
                  }
                  className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded-lg text-white text-sm focus:outline-none focus:border-blue-500"
                >
                  <option value="">הכל</option>
                  {filter.options?.map((opt) => (
                    <option key={opt.value} value={opt.value}>
                      {opt.label}
                    </option>
                  ))}
                </select>
              )}

              {filter.type === 'text' && (
                <input
                  type="text"
                  placeholder={filter.placeholder || 'הזן ערך...'}
                  value={filterValues[filter.key] || ''}
                  onChange={(e) =>
                    handleFilterChange(filter.key, e.target.value)
                  }
                  className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded-lg text-white text-sm placeholder-gray-500 focus:outline-none focus:border-blue-500"
                />
              )}

              {filter.type === 'date' && (
                <input
                  type="date"
                  value={filterValues[filter.key] || ''}
                  onChange={(e) =>
                    handleFilterChange(filter.key, e.target.value)
                  }
                  className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded-lg text-white text-sm focus:outline-none focus:border-blue-500"
                />
              )}
            </div>
          ))}

          {/* Reset Button */}
          {activeFilterCount > 0 && (
            <button
              onClick={handleReset}
              className="w-full px-3 py-2 bg-gray-700 hover:bg-gray-600 rounded-lg text-white text-sm font-semibold transition-colors"
            >
              ביטול סינון
            </button>
          )}
        </div>
      )}
    </div>
  );
}

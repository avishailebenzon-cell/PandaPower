/**
 * StatusBar Component
 * Scrolling RTL status indicator for system components
 */

import React, { useEffect } from 'react';
import { useSystemStatus } from '@/hooks/useSystemStatus';

interface StatusItem {
  id: string;
  name: string;
  status: 'active' | 'idle' | 'processing' | 'offline';
  detail?: string;
}

const getStatusColor = (status: string): string => {
  switch (status) {
    case 'active':
      return 'bg-green-600';
    case 'processing':
      return 'bg-blue-600';
    case 'idle':
      return 'bg-yellow-600';
    case 'offline':
      return 'bg-red-600';
    default:
      return 'bg-gray-600';
  }
};

const getStatusText = (status: string): string => {
  switch (status) {
    case 'active':
      return '🟢 פעיל';
    case 'processing':
      return '🔵 בעיבוד';
    case 'idle':
      return '🟡 בהמתנה';
    case 'offline':
      return '🔴 לא פעיל';
    default:
      return '⚪ לא ידוע';
  }
};

export const StatusBar: React.FC = () => {
  const { statuses: statusItems } = useSystemStatus();

  // Double the status items for seamless scrolling
  const doubledStatus = [...statusItems, ...statusItems];

  return (
    <div className="fixed bottom-0 left-0 right-0 bg-gray-950 border-t-2 border-gray-800 py-2 px-4 z-40">
      <div className="relative overflow-hidden h-12">
        {/* Scrolling container */}
        <div
          className="flex gap-8 animate-scroll-rtl whitespace-nowrap absolute right-0"
          style={{
            animation: 'scroll-rtl 60s linear infinite',
          }}
        >
          {doubledStatus.map((item, index) => (
            <div
              key={`${item.id}-${index}`}
              className="flex items-center gap-3 flex-shrink-0 px-4"
            >
              {/* Status indicator dot */}
              <div className="flex items-center gap-2">
                <div
                  className={`w-3 h-3 rounded-full ${getStatusColor(
                    item.status
                  )} animate-pulse`}
                  title={item.name}
                />
              </div>

              {/* Status text */}
              <div className="flex flex-col gap-0.5">
                <span className="text-sm font-semibold text-white">
                  {item.name}
                </span>
                <span className="text-xs text-gray-400 flex items-center gap-1">
                  {getStatusText(item.status)}
                  {item.detail && (
                    <>
                      <span>•</span>
                      <span>{item.detail}</span>
                    </>
                  )}
                </span>
              </div>

              {/* Separator */}
              <div className="w-px h-8 bg-gray-700 ml-2" />
            </div>
          ))}
        </div>
      </div>

      {/* CSS Animation for RTL scrolling */}
      <style>{`
        @keyframes scroll-rtl {
          0% {
            transform: translateX(0);
          }
          100% {
            transform: translateX(-50%);
          }
        }

        .animate-scroll-rtl {
          animation: scroll-rtl 60s linear infinite;
        }

        /* Smooth scrolling */
        @media (prefers-reduced-motion: no-preference) {
          * {
            scroll-behavior: smooth;
          }
        }
      `}</style>
    </div>
  );
};

export default StatusBar;

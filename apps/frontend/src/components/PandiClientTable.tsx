/**
 * PandiClientTable Component
 * Table display for Pandi clients with action buttons
 */

import React from 'react';
import { PandiClient } from '@/api/pandi';

interface PandiClientTableProps {
  clients: PandiClient[];
  isLoading: boolean;
  onViewDetails: (client: PandiClient) => void;
  onGenerateInvite: (client: PandiClient) => void;
  onViewInvite: (client: PandiClient) => void;
}

export const PandiClientTable: React.FC<PandiClientTableProps> = ({
  clients,
  isLoading,
  onViewDetails,
  onGenerateInvite,
  onViewInvite,
}) => {
  const formatDate = (dateString?: string) => {
    if (!dateString) return 'לא זמין';
    const date = new Date(dateString);
    const now = new Date();
    const days = Math.floor((now.getTime() - date.getTime()) / (1000 * 60 * 60 * 24));

    if (days === 0) return 'היום';
    if (days === 1) return 'אתמול';
    if (days < 7) return `לפני ${days} ימים`;
    return date.toLocaleDateString('he-IL');
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'completed':
        return 'bg-green-900 text-green-200';
      case 'in_progress':
        return 'bg-blue-900 text-blue-200';
      case 'not_started':
        return 'bg-yellow-900 text-yellow-200';
      default:
        return 'bg-gray-700 text-gray-200';
    }
  };

  const getStatusLabel = (status: string) => {
    switch (status) {
      case 'completed':
        return '✓ הושלם';
      case 'in_progress':
        return '⏳ בתהליך';
      case 'not_started':
        return '○ לא התחיל';
      default:
        return status;
    }
  };

  if (isLoading) {
    return (
      <div className="flex justify-center items-center py-12">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
      </div>
    );
  }

  if (clients.length === 0) {
    return (
      <div className="text-center py-8 text-gray-400">
        <p>אין לקוחות להצגה</p>
      </div>
    );
  }

  return (
    <div className="overflow-x-auto" dir="rtl">
      <table className="w-full text-right text-sm">
        <thead>
          <tr className="border-b border-gray-700 bg-gray-800">
            <th className="px-4 py-3 font-semibold text-gray-300">שם</th>
            <th className="px-4 py-3 font-semibold text-gray-300">ארגון</th>
            <th className="px-4 py-3 font-semibold text-gray-300">טלפון</th>
            <th className="px-4 py-3 font-semibold text-gray-300">סטטוס</th>
            <th className="px-4 py-3 font-semibold text-gray-300">פעילות אחרונה</th>
            <th className="px-4 py-3 font-semibold text-gray-300">שיחות</th>
            <th className="px-4 py-3 font-semibold text-gray-300">פעולות</th>
          </tr>
        </thead>
        <tbody>
          {clients.map((client) => (
            <tr
              key={client.id}
              className="border-b border-gray-700 hover:bg-gray-700 transition"
            >
              {/* Name */}
              <td className="px-4 py-3 text-white font-semibold">
                {client.contact_name || 'לא זמין'}
              </td>

              {/* Organization */}
              <td className="px-4 py-3 text-gray-300">
                {client.organization_name || 'לא זמין'}
              </td>

              {/* Phone */}
              <td className="px-4 py-3 text-gray-300 font-mono">
                {client.phone || 'לא זמין'}
              </td>

              {/* Status Badge */}
              <td className="px-4 py-3">
                <span
                  className={`px-3 py-1 rounded text-xs font-bold ${getStatusColor(
                    client.intake_status
                  )}`}
                >
                  {getStatusLabel(client.intake_status)}
                </span>
              </td>

              {/* Last Activity */}
              <td className="px-4 py-3 text-gray-400 text-xs">
                {formatDate(client.last_message_at)}
              </td>

              {/* Conversation Count (placeholder) */}
              <td className="px-4 py-3 text-gray-400">
                <span className="bg-gray-700 px-2 py-1 rounded text-xs">
                  {Math.floor(Math.random() * 10) + 1}
                </span>
              </td>

              {/* Actions */}
              <td className="px-4 py-3">
                <div className="flex gap-2 justify-start">
                  <button
                    onClick={() => onViewDetails(client)}
                    className="px-3 py-1 rounded text-xs font-semibold bg-blue-600 hover:bg-blue-700 text-white transition"
                    title="הצג פרטים"
                  >
                    📋 פרטים
                  </button>
                  <button
                    onClick={() => onGenerateInvite(client)}
                    className="px-3 py-1 rounded text-xs font-semibold bg-green-600 hover:bg-green-700 text-white transition"
                    title="צור הזמנה"
                  >
                    🔗 הזמנה
                  </button>
                  <button
                    onClick={() => onViewInvite(client)}
                    className="px-3 py-1 rounded text-xs font-semibold bg-purple-600 hover:bg-purple-700 text-white transition"
                    title="הצג הזמנה קיימת"
                  >
                    👁️ הצג
                  </button>
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
};

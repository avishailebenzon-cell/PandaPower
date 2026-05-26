/**
 * ClientDetailModal Component
 * Displays detailed client profile with conversation history
 */

import React from 'react';
import { PandiClientDetail } from '@/api/pandi';

interface ClientDetailModalProps {
  isOpen: boolean;
  clientData: PandiClientDetail | null;
  isLoading: boolean;
  isError?: boolean;
  error?: Error | null;
  onClose: () => void;
  onRetry?: () => void;
}

export const ClientDetailModal: React.FC<ClientDetailModalProps> = ({
  isOpen,
  clientData,
  isLoading,
  isError = false,
  error = null,
  onClose,
  onRetry,
}) => {
  if (!isOpen) return null;

  const formatDate = (dateString?: string) => {
    if (!dateString) return 'לא זמין';
    return new Date(dateString).toLocaleDateString('he-IL');
  };

  const formatTime = (dateString?: string) => {
    if (!dateString) return '';
    const date = new Date(dateString);
    return date.toLocaleTimeString('he-IL', {
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  return (
    <div
      className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 overflow-y-auto"
      dir="rtl"
    >
      <div className="bg-gray-800 rounded-lg p-6 max-w-3xl w-full mx-4 my-8 border border-gray-700">
        {/* Header */}
        <div className="flex justify-between items-center mb-6">
          <h2 className="text-xl font-bold text-white">פרטי לקוח</h2>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-white text-2xl"
          >
            ×
          </button>
        </div>

        {isLoading ? (
          <div className="flex justify-center items-center py-12">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
            <p className="text-gray-400 mr-4">טוען פרטים...</p>
          </div>
        ) : isError ? (
          <div className="bg-red-900 border-r-4 border-red-600 rounded p-4 py-8 text-center">
            <p className="text-red-200 font-semibold mb-4">
              שגיאה בטעינת פרטי הלקוח
            </p>
            {error && (
              <p className="text-red-300 text-sm mb-4">
                {error.message}
              </p>
            )}
            <button
              onClick={onRetry}
              className="px-4 py-2 rounded font-semibold bg-red-700 hover:bg-red-600 text-white transition"
            >
              נסה שוב
            </button>
          </div>
        ) : clientData ? (
          <div className="space-y-6">
            {/* Client Info Card */}
            <div className="bg-gray-700 rounded-lg p-4 border border-gray-600">
              <h3 className="text-lg font-semibold text-white mb-4">
                פרטים כלליים
              </h3>
              <div className="grid grid-cols-2 gap-4 text-sm">
                <div>
                  <p className="text-gray-400">שם</p>
                  <p className="text-white font-semibold">
                    {clientData.contact.full_name || 'לא זמין'}
                  </p>
                </div>
                <div>
                  <p className="text-gray-400">מספר טלפון</p>
                  <p className="text-white font-semibold">
                    {clientData.client.phone || 'לא זמין'}
                  </p>
                </div>
                <div>
                  <p className="text-gray-400">ארגון</p>
                  <p className="text-white font-semibold">
                    {clientData.organization.name || 'לא זמין'}
                  </p>
                </div>
                <div>
                  <p className="text-gray-400">סטטוס</p>
                  <p className="text-white font-semibold">
                    <span
                      className={`px-2 py-1 rounded text-xs font-bold ${
                        clientData.client.is_active
                          ? 'bg-green-900 text-green-200'
                          : 'bg-gray-600 text-gray-200'
                      }`}
                    >
                      {clientData.client.is_active ? 'פעיל' : 'לא פעיל'}
                    </span>
                  </p>
                </div>
                <div>
                  <p className="text-gray-400">ההודעה הראשונה</p>
                  <p className="text-white font-semibold">
                    {formatDate(clientData.client.first_message_at)}
                  </p>
                </div>
                <div>
                  <p className="text-gray-400">פעילות אחרונה</p>
                  <p className="text-white font-semibold">
                    {formatDate(clientData.client.last_message_at)}
                  </p>
                </div>
              </div>
            </div>

            {/* Conversation Stats */}
            <div className="bg-gray-700 rounded-lg p-4 border border-gray-600">
              <h3 className="text-lg font-semibold text-white mb-4">
                סטטיסטיקת שיחות
              </h3>
              <div className="grid grid-cols-3 gap-4 text-center">
                <div className="bg-gray-800 rounded p-3">
                  <p className="text-gray-400 text-sm">מספר שיחות</p>
                  <p className="text-2xl font-bold text-blue-400">
                    {clientData.conversations.length}
                  </p>
                </div>
                <div className="bg-gray-800 rounded p-3">
                  <p className="text-gray-400 text-sm">סטטוס הנתיקה</p>
                  <p className="text-lg font-semibold text-white">
                    {clientData.client.intake_status === 'completed'
                      ? '✓ הושלם'
                      : clientData.client.intake_status === 'in_progress'
                      ? '⏳ בתהליך'
                      : '○ לא התחיל'}
                  </p>
                </div>
                <div className="bg-gray-800 rounded p-3">
                  <p className="text-gray-400 text-sm">שיטת זיהוי</p>
                  <p className="text-sm font-semibold text-white">
                    {clientData.client.identification_method === 'auto_phone_match'
                      ? 'התאמה טלפון'
                      : 'ידנית'}
                  </p>
                </div>
              </div>
            </div>

            {/* Recent Conversations */}
            <div className="bg-gray-700 rounded-lg p-4 border border-gray-600">
              <h3 className="text-lg font-semibold text-white mb-4">
                שיחות אחרונות (10 אחרונות)
              </h3>
              {clientData.conversations.length > 0 ? (
                <div className="space-y-3 max-h-96 overflow-y-auto">
                  {clientData.conversations.map((conv, idx) => (
                    <div
                      key={idx}
                      className="bg-gray-800 rounded p-3 border-r-4 border-blue-600"
                    >
                      <div className="flex justify-between items-start mb-2">
                        <p className="text-sm font-semibold text-white">
                          שיחה #{clientData.conversations.length - idx}
                        </p>
                        <p className="text-xs text-gray-400">
                          {formatDate(conv.started_at)}{' '}
                          {formatTime(conv.started_at)}
                        </p>
                      </div>
                      <p className="text-sm text-gray-300">
                        {conv.topic || 'ללא נושא'}
                      </p>
                      {conv.outcome && (
                        <p className="text-xs text-gray-400 mt-2">
                          תוצאה: {conv.outcome}
                        </p>
                      )}
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-gray-400 text-center py-4">
                  אין שיחות להצגה
                </p>
              )}
            </div>
          </div>
        ) : null}

        {/* Close Button */}
        <div className="flex justify-start gap-3 mt-6 pt-6 border-t border-gray-700">
          <button
            onClick={onClose}
            className="px-4 py-2 rounded font-semibold bg-gray-700 hover:bg-gray-600 text-white transition"
          >
            סגור
          </button>
        </div>
      </div>
    </div>
  );
};

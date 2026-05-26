/**
 * InviteGeneratorModal Component
 * Displays WhatsApp invite URL and prefilled message for copying
 */

import React, { useState } from 'react';
import { GenerateInviteResponse } from '@/api/pandi';

interface InviteGeneratorModalProps {
  isOpen: boolean;
  inviteData: GenerateInviteResponse | null;
  isLoading: boolean;
  onClose: () => void;
}

export const InviteGeneratorModal: React.FC<InviteGeneratorModalProps> = ({
  isOpen,
  inviteData,
  isLoading,
  onClose,
}) => {
  const [copiedField, setCopiedField] = useState<string | null>(null);

  if (!isOpen) return null;

  const handleCopy = (text: string, fieldName: string) => {
    navigator.clipboard.writeText(text);
    setCopiedField(fieldName);
    setTimeout(() => setCopiedField(null), 2000);
  };

  return (
    <div
      className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50"
      dir="rtl"
    >
      <div className="bg-gray-800 rounded-lg p-6 max-w-2xl w-full mx-4 border border-gray-700">
        {/* Header */}
        <div className="flex justify-between items-center mb-6">
          <h2 className="text-xl font-bold text-white">יצירת הזמנה ל-Pandi</h2>
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
            <p className="text-gray-400 mr-4">יוצר קישור הזמנה...</p>
          </div>
        ) : inviteData ? (
          <div className="space-y-6">
            {/* Invite URL Section */}
            <div>
              <label className="block text-sm font-semibold text-gray-300 mb-2">
                קישור הזמנה (לחץ לשיתוף ישיר)
              </label>
              <div className="flex gap-2">
                <a
                  href={inviteData.invite_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex-1 bg-gray-700 border border-gray-600 rounded px-3 py-2 text-white text-sm break-all hover:border-blue-500 transition"
                >
                  {inviteData.invite_url}
                </a>
                <button
                  onClick={() =>
                    handleCopy(inviteData.invite_url, 'invite_url')
                  }
                  className={`px-4 py-2 rounded font-semibold transition ${
                    copiedField === 'invite_url'
                      ? 'bg-green-600 text-white'
                      : 'bg-blue-600 hover:bg-blue-700 text-white'
                  }`}
                >
                  {copiedField === 'invite_url' ? '✓ הועתק' : 'העתק'}
                </button>
              </div>
            </div>

            {/* Prefilled Message Section */}
            <div>
              <label className="block text-sm font-semibold text-gray-300 mb-2">
                הודעה שהלקוח יוכל לשלוח
              </label>
              <div className="flex gap-2">
                <div className="flex-1 bg-gray-700 border border-gray-600 rounded px-3 py-2 text-white text-sm max-h-24 overflow-y-auto">
                  {inviteData.prefilled_message}
                </div>
                <button
                  onClick={() =>
                    handleCopy(inviteData.prefilled_message, 'prefilled')
                  }
                  className={`px-4 py-2 rounded font-semibold transition ${
                    copiedField === 'prefilled'
                      ? 'bg-green-600 text-white'
                      : 'bg-blue-600 hover:bg-blue-700 text-white'
                  }`}
                >
                  {copiedField === 'prefilled' ? '✓ הועתק' : 'העתק'}
                </button>
              </div>
            </div>

            {/* Admin Instructions Section */}
            <div>
              <label className="block text-sm font-semibold text-gray-300 mb-2">
                הוראות לשליחה ללקוח
              </label>
              <div className="flex gap-2">
                <div className="flex-1 bg-gray-700 border border-gray-600 rounded px-3 py-2 text-white text-sm max-h-32 overflow-y-auto whitespace-pre-wrap">
                  {inviteData.instructions_for_admin}
                </div>
                <button
                  onClick={() =>
                    handleCopy(inviteData.instructions_for_admin, 'instructions')
                  }
                  className={`px-4 py-2 rounded font-semibold transition ${
                    copiedField === 'instructions'
                      ? 'bg-green-600 text-white'
                      : 'bg-blue-600 hover:bg-blue-700 text-white'
                  }`}
                >
                  {copiedField === 'instructions' ? '✓ הועתק' : 'העתק'}
                </button>
              </div>
            </div>

            {/* Instructions */}
            <div className="bg-gray-700 border-r-4 border-blue-600 rounded p-4">
              <p className="text-sm text-gray-200">
                💡 <strong>טיפ:</strong> בחר את הקישור הראשון לשיתוף ישיר דרך
                WhatsApp, או העתק את הודעת הלקוח ושלח ידנית.
              </p>
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

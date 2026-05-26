/**
 * Sync Status Indicator Component
 * Displays sync status with color coding
 * 🟢 Green: Synced (< 1 hour ago)
 * 🟡 Yellow: Syncing (< 24 hours ago)
 * 🔴 Red: Failed or stale (> 24 hours)
 */

import React from 'react';

interface SyncStatusIndicatorProps {
  syncStatus: string;
  lastSynced?: string;
  className?: string;
}

export function SyncStatusIndicator({
  syncStatus,
  lastSynced,
  className = '',
}: SyncStatusIndicatorProps) {
  // Determine color based on sync status and time
  const getStatusInfo = () => {
    if (!lastSynced) {
      return { color: 'bg-red-900', text: 'לא סונכרן', icon: '🔴' };
    }

    const lastSyncDate = new Date(lastSynced);
    const now = new Date();
    const hoursSinceSync = (now.getTime() - lastSyncDate.getTime()) / (1000 * 60 * 60);

    if (syncStatus === 'failed') {
      return { color: 'bg-red-900', text: 'כשל', icon: '🔴' };
    }

    if (hoursSinceSync < 1) {
      return { color: 'bg-green-900', text: 'סונכרן', icon: '🟢' };
    }

    if (hoursSinceSync < 24) {
      return { color: 'bg-yellow-900', text: 'בתהליך סינכרון', icon: '🟡' };
    }

    return { color: 'bg-red-900', text: 'לא מעודכן', icon: '🔴' };
  };

  const statusInfo = getStatusInfo();
  const lastSyncText = lastSynced
    ? new Date(lastSynced).toLocaleString('he-IL')
    : 'לא זמין';

  return (
    <div
      className={`flex items-center gap-2 px-3 py-1 rounded-md ${statusInfo.color} text-white text-sm ${className}`}
      title={`סטטוס סינכרון: ${statusInfo.text}\nסינכרון אחרון: ${lastSyncText}`}
    >
      <span>{statusInfo.icon}</span>
      <span>{statusInfo.text}</span>
    </div>
  );
}

/**
 * Pipedrive Integration Configuration Page
 * Manage Pipedrive API credentials, field mappings, and sync schedules
 */

import React, { useState, useEffect, useMemo } from 'react';
import { useQuery, useMutation } from '@tanstack/react-query';
import { env } from '@/lib/env';

interface ConfigTab {
  id: 'credentials' | 'field-mapping' | 'sync-schedule' | 'sync-history';
  label: string;
  icon: string;
}

interface PipedriveConfig {
  is_active: boolean;
  api_domain: string;
  last_validated_at?: string;
  validation_error?: string;
}

interface SyncSchedule {
  entity_type: string;
  sync_interval_minutes: number;
  sync_direction: string;
  sync_enabled: boolean;
  sync_days: boolean[];  // ראשון-שישי [0-5]
  sync_time: string;      // HH:mm format
  last_sync_at?: string;
  last_sync_status?: string;
  next_scheduled_sync?: string;
  sync_count: number;
}

interface SyncHistoryLog {
  id: string;
  entity_type: string;
  sync_direction: string;
  status: string;
  records_processed: number;
  records_created: number;
  records_updated: number;
  records_failed: number;
  error_message?: string;
  started_at: string;
  completed_at: string;
  duration_ms: number;
}

interface FieldMapping {
  entity_type: string;
  pandapower_field: string;
  pipedrive_field_id: string;
  pipedrive_field_name: string;
  field_type: string;
  is_required: boolean;
}

const ENTITY_TYPES = [
  { id: 'deals', label: 'משרות (Deals)', icon: '💼' },
  { id: 'persons', label: 'אנשי קשר (Persons)', icon: '👤' },
  { id: 'organizations', label: 'ארגונים (Organizations)', icon: '🏢' },
];

const DEAL_FIELDS = [
  { pandapower: 'job_title', label: 'שם המשרה' },
  { pandapower: 'job_description', label: 'תיאור המשרה' },
  { pandapower: 'job_qualifications', label: 'דרישות' },
  { pandapower: 'job_location', label: 'מיקום' },
  { pandapower: 'deadline', label: 'תאריך סיום' },
  { pandapower: 'security_clearance', label: 'סיווג בטחוני' },
  { pandapower: 'priority', label: 'עדיפות' },
];

const PERSON_FIELDS = [
  { pandapower: 'contact_type_status', label: 'סוג איש קשר (לקוח, מועמד, וכו\')' },
  { pandapower: 'email', label: 'דוא"ל' },
  { pandapower: 'phone', label: 'טלפון' },
];

const ORGANIZATION_FIELDS = [
  { pandapower: 'name', label: 'שם הארגון' },
  { pandapower: 'website', label: 'אתר אינטרנט' },
];

const DAYS_OF_WEEK = [
  { id: 0, label: 'ראשון' },
  { id: 1, label: 'שני' },
  { id: 2, label: 'שלישי' },
  { id: 3, label: 'רביעי' },
  { id: 4, label: 'חמישי' },
  { id: 5, label: 'שישי' },
];

export const PipedriveConfigPage: React.FC = () => {
  const [activeTab, setActiveTab] = useState<ConfigTab['id']>('credentials');
  const [apiToken, setApiToken] = useState('');
  const [apiDomain, setApiDomain] = useState('https://api.pipedrive.com');
  const [selectedEntity, setSelectedEntity] = useState<string>('deals');
  const [testingConnection, setTestingConnection] = useState(false);
  const [activeSyncs, setActiveSyncs] = useState<Set<string>>(new Set());

  // Fetch current config
  const { data: config } = useQuery({
    queryKey: ['pipedrive-config'],
    queryFn: async () => {
      const response = await fetch(`${env.API_BASE_URL}/admin/pipedrive/config`);
      return response.json() as Promise<PipedriveConfig>;
    },
  });

  // Fetch sync schedules
  const { data: schedules = [] } = useQuery({
    queryKey: ['pipedrive-sync-schedules'],
    queryFn: async () => {
      const response = await fetch(`${env.API_BASE_URL}/admin/pipedrive/sync-schedules`);
      const data = await response.json();
      return data.schedules || [];
    },
  });

  // Fetch field mappings
  const { data: mappings = [] } = useQuery({
    queryKey: ['pipedrive-field-mappings', selectedEntity],
    queryFn: async () => {
      const response = await fetch(
        `${env.API_BASE_URL}/admin/pipedrive/field-mappings?entity_type=${selectedEntity}`
      );
      const data = await response.json();
      return data.mappings || [];
    },
  });

  // Fetch sync history for all entity types
  const { data: syncHistory = [] } = useQuery({
    queryKey: ['pipedrive-sync-history'],
    queryFn: async () => {
      const allLogs: SyncHistoryLog[] = [];

      for (const entity of ['persons', 'deals', 'organizations']) {
        const response = await fetch(
          `${env.API_BASE_URL}/admin/pipedrive/sync-history/${entity}`
        );
        if (response.ok) {
          const data = await response.json();
          allLogs.push(...(data.history || []));
        }
      }

      // Sort by started_at descending
      return allLogs.sort((a, b) =>
        new Date(b.started_at).getTime() - new Date(a.started_at).getTime()
      );
    },
    refetchInterval: 30000, // Refetch every 30 seconds
  });

  // Mutation: Update config
  const updateConfigMutation = useMutation({
    mutationFn: async () => {
      const response = await fetch(`${env.API_BASE_URL}/admin/pipedrive/config`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          api_token: apiToken,
          api_domain: apiDomain,
        }),
      });

      const data = await response.json();

      if (!response.ok) {
        // Extract error message from response
        const errorMessage = data.detail || data.message || 'Failed to update config';
        throw new Error(errorMessage);
      }
      return data;
    },
    onSuccess: () => {
      alert('✅ קונפיגורציה עודכנה בהצלחה');
    },
    onError: (error) => {
      alert(`❌ שגיאה: ${error instanceof Error ? error.message : String(error)}`);
    },
  });

  // Mutation: Test connection
  const testConnectionMutation = useMutation({
    mutationFn: async () => {
      const response = await fetch(`${env.API_BASE_URL}/admin/pipedrive/test-connection`);
      if (!response.ok) throw new Error('Connection test failed');
      return response.json();
    },
    onSuccess: (data) => {
      alert(`✅ חיבור הצליח!\nמשתמש: ${data.user}`);
    },
    onError: (error) => {
      alert(`❌ שגיאה בחיבור: ${error}`);
    },
  });

  // Mutation: Trigger sync
  const triggerSyncMutation = useMutation({
    mutationFn: async (entityType: string) => {
      setActiveSyncs(prev => new Set(prev).add(entityType));
      const response = await fetch(
        `${env.API_BASE_URL}/admin/pipedrive/sync-now/${entityType}`,
        { method: 'POST' }
      );
      if (!response.ok) throw new Error('Failed to trigger sync');
      // Simulate longer sync duration for better visibility (remove in production)
      await new Promise(resolve => setTimeout(resolve, 3000));
      return response.json();
    },
    onSuccess: () => {
      // Removed alert - using visual indicator instead
    },
    onError: (error) => {
      alert(`❌ שגיאה: ${error}`);
    },
    onSettled: (data, error, entityType) => {
      setActiveSyncs(prev => {
        const newSet = new Set(prev);
        newSet.delete(entityType);
        return newSet;
      });
    },
  });

  // Mutation: Update sync schedule
  const updateSyncScheduleMutation = useMutation({
    mutationFn: async (data: { entity_type: string; sync_days: boolean[]; sync_time: string; sync_interval_minutes: number; sync_direction: string }) => {
      const response = await fetch(
        `${env.API_BASE_URL}/admin/pipedrive/sync-schedule/${data.entity_type}`,
        {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            sync_days: data.sync_days,
            sync_time: data.sync_time,
            sync_interval_minutes: data.sync_interval_minutes,
            sync_direction: data.sync_direction,
          }),
        }
      );
      if (!response.ok) throw new Error('Failed to update sync schedule');
      return response.json();
    },
    onSuccess: () => {
      alert('✅ תזמון הסינכרון עודכן בהצלחה');
    },
    onError: (error) => {
      alert(`❌ שגיאה: ${error}`);
    },
  });

  // Compute syncScheduleState from schedules using useMemo to avoid re-render loops
  const syncScheduleState = useMemo(() => {
    // Default mock schedules if API returns empty
    const defaultSchedules: SyncSchedule[] = [
      {
        entity_type: 'deals',
        sync_interval_minutes: 30,
        sync_direction: 'bidirectional',
        sync_enabled: true,
        sync_days: [true, true, true, true, true, false],
        sync_time: '08:00',
        last_sync_at: new Date().toISOString(),
        last_sync_status: 'success',
        sync_count: 42,
      },
      {
        entity_type: 'persons',
        sync_interval_minutes: 30,
        sync_direction: 'bidirectional',
        sync_enabled: true,
        sync_days: [true, true, true, true, true, false],
        sync_time: '09:00',
        last_sync_at: new Date().toISOString(),
        last_sync_status: 'success',
        sync_count: 38,
      },
      {
        entity_type: 'organizations',
        sync_interval_minutes: 60,
        sync_direction: 'inbound',
        sync_enabled: true,
        sync_days: [true, false, true, false, true, false],
        sync_time: '10:00',
        last_sync_at: new Date().toISOString(),
        last_sync_status: 'success',
        sync_count: 12,
      },
    ];

    const schedulesToUse = schedules && schedules.length > 0 ? schedules : defaultSchedules;
    const newState: { [key: string]: { days: boolean[]; time: string } } = {};
    schedulesToUse.forEach((schedule: SyncSchedule) => {
      newState[schedule.entity_type] = {
        days: schedule.sync_days || [false, false, false, false, false, false],
        time: schedule.sync_time || '00:00',
      };
    });
    return newState;
  }, [schedules]);

  const tabs: ConfigTab[] = [
    { id: 'credentials', label: 'אישורים', icon: '🔑' },
    { id: 'field-mapping', label: 'מיפוי שדות', icon: '🗂️' },
    { id: 'sync-schedule', label: 'תזמון סינכרון', icon: '⏱️' },
    { id: 'sync-history', label: 'היסטוריית סינכרון', icon: '📋' },
  ];

  return (
    <div dir="rtl" className="min-h-screen bg-gray-900 p-8">
      <div className="max-w-7xl mx-auto">
        {/* Header */}
        <div className="mb-8">
          <h1 className="text-4xl font-bold text-white mb-2">
            🔗 הגדרת Pipedrive Integration
          </h1>
          <p className="text-gray-400">
            ניהול חיבור, מיפוי שדות, והגדרת תזמוני סינכרון עם Pipedrive CRM
          </p>
        </div>

        {/* Status Banner */}
        {config && (
          <div
            className={`p-4 rounded-lg mb-6 border ${
              config.is_active
                ? 'bg-green-900 border-green-700 text-green-200'
                : 'bg-red-900 border-red-700 text-red-200'
            }`}
          >
            <div className="flex items-center justify-between">
              <div>
                <div className="font-semibold flex items-center gap-2">
                  {config.is_active ? '✅ חיבור פעיל' : '❌ חיבור כבוי'}
                  {activeSyncs.size > 0 && (
                    <span className="text-sm bg-blue-700 text-blue-200 px-2 py-1 rounded flex items-center gap-1">
                      <span className="animate-spin">🔄</span>
                      סינכרון בתהליך
                    </span>
                  )}
                </div>
                {config.last_validated_at && (
                  <div className="text-sm mt-1">
                    בדיקה אחרונה: {new Date(config.last_validated_at).toLocaleString('he-IL')}
                  </div>
                )}
                {config.validation_error && (
                  <div className="text-sm mt-1">שגיאה: {config.validation_error}</div>
                )}
              </div>
              <button
                onClick={() => testConnectionMutation.mutate()}
                disabled={testConnectionMutation.isPending}
                className="px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:bg-gray-600 rounded font-semibold transition"
              >
                {testConnectionMutation.isPending ? '⏳ בדיקה...' : '🧪 בדוק חיבור'}
              </button>
            </div>
          </div>
        )}

        {/* Tab Navigation */}
        <div className="flex gap-2 mb-6 border-b border-gray-700 overflow-x-auto">
          {tabs.map(tab => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`px-4 py-3 font-semibold whitespace-nowrap transition border-b-2 ${
                activeTab === tab.id
                  ? 'text-blue-400 border-blue-600'
                  : 'text-gray-400 border-transparent hover:text-white'
              }`}
            >
              {tab.icon} {tab.label}
            </button>
          ))}
        </div>

        {/* Tab Content */}
        <div className="bg-gray-800 rounded-lg border border-gray-700 p-6">
          {/* Credentials Tab */}
          {activeTab === 'credentials' && (
            <div className="space-y-6">
              <div>
                <label className="block text-white font-semibold mb-2">API Token</label>
                <input
                  type="text"
                  value={apiToken}
                  onChange={e => setApiToken(e.target.value)}
                  placeholder="הכנס Pipedrive API token"
                  className="w-full px-4 py-2 rounded bg-gray-700 border border-gray-600 text-white placeholder-gray-400 focus:outline-none focus:border-blue-400 font-mono text-sm"
                />
                <p className="text-gray-400 text-sm mt-2">
                  ניתן להשיג מ: Settings → Personal Preferences → API
                </p>
              </div>

              <div>
                <label className="block text-white font-semibold mb-2">API Domain</label>
                <input
                  type="text"
                  value={apiDomain}
                  onChange={e => setApiDomain(e.target.value)}
                  placeholder="https://api.pipedrive.com"
                  className="w-full px-4 py-2 rounded bg-gray-700 border border-gray-600 text-white placeholder-gray-400 focus:outline-none focus:border-blue-400"
                />
              </div>

              <button
                onClick={() => updateConfigMutation.mutate()}
                disabled={updateConfigMutation.isPending || !apiToken}
                className="w-full px-6 py-3 bg-green-600 hover:bg-green-700 disabled:bg-gray-600 disabled:cursor-not-allowed text-white font-semibold rounded transition"
              >
                {updateConfigMutation.isPending ? '⏳ שומר...' : '💾 שמור הגדרות'}
              </button>
            </div>
          )}

          {/* Field Mapping Tab */}
          {activeTab === 'field-mapping' && (
            <div className="space-y-6">
              <div>
                <label className="block text-white font-semibold mb-3">בחר סוג ישות</label>
                <div className="grid grid-cols-3 gap-3">
                  {ENTITY_TYPES.map(entity => (
                    <button
                      key={entity.id}
                      onClick={() => setSelectedEntity(entity.id)}
                      className={`p-3 rounded border transition ${
                        selectedEntity === entity.id
                          ? 'bg-blue-900 border-blue-600 text-white'
                          : 'bg-gray-700 border-gray-600 text-gray-300 hover:bg-gray-600'
                      }`}
                    >
                      {entity.icon} {entity.label}
                    </button>
                  ))}
                </div>
              </div>

              <div className="border-t border-gray-700 pt-6">
                <h3 className="text-white font-semibold mb-4">שדות למיפוי</h3>

                {selectedEntity === 'deals' && (
                  <div className="space-y-3">
                    {DEAL_FIELDS.map(field => (
                      <div
                        key={field.pandapower}
                        className="p-3 bg-gray-700 rounded border border-gray-600"
                      >
                        <div className="flex items-center justify-between">
                          <div>
                            <div className="text-white font-semibold">{field.label}</div>
                            <div className="text-xs text-gray-400">{field.pandapower}</div>
                          </div>
                          <input
                            type="text"
                            placeholder="Pipedrive Field ID"
                            className="px-3 py-1 rounded bg-gray-600 border border-gray-500 text-white text-sm"
                          />
                        </div>
                      </div>
                    ))}
                  </div>
                )}

                {selectedEntity === 'persons' && (
                  <div className="space-y-3">
                    {PERSON_FIELDS.map(field => (
                      <div
                        key={field.pandapower}
                        className="p-3 bg-gray-700 rounded border border-gray-600"
                      >
                        <div className="flex items-center justify-between">
                          <div>
                            <div className="text-white font-semibold">{field.label}</div>
                            <div className="text-xs text-gray-400">{field.pandapower}</div>
                          </div>
                          <input
                            type="text"
                            placeholder="Pipedrive Field ID"
                            className="px-3 py-1 rounded bg-gray-600 border border-gray-500 text-white text-sm"
                          />
                        </div>
                      </div>
                    ))}
                  </div>
                )}

                {selectedEntity === 'organizations' && (
                  <div className="space-y-3">
                    {ORGANIZATION_FIELDS.map(field => (
                      <div
                        key={field.pandapower}
                        className="p-3 bg-gray-700 rounded border border-gray-600"
                      >
                        <div className="flex items-center justify-between">
                          <div>
                            <div className="text-white font-semibold">{field.label}</div>
                            <div className="text-xs text-gray-400">{field.pandapower}</div>
                          </div>
                          <input
                            type="text"
                            placeholder="Pipedrive Field ID"
                            className="px-3 py-1 rounded bg-gray-600 border border-gray-500 text-white text-sm"
                          />
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              <button className="w-full px-6 py-3 bg-green-600 hover:bg-green-700 text-white font-semibold rounded transition">
                💾 שמור מיפוי
              </button>
            </div>
          )}

          {/* Sync Schedule Tab */}
          {activeTab === 'sync-schedule' && (
            <div className="space-y-6">
              {/* Active Syncs Indicator */}
              {activeSyncs.size > 0 && (
                <div className="p-4 bg-blue-900 border border-blue-700 rounded-lg">
                  <div className="flex items-center gap-2 mb-2">
                    <span className="text-2xl animate-spin">🔄</span>
                    <span className="text-blue-200 font-semibold">סינכרון בעתיד!</span>
                  </div>
                  <p className="text-blue-300 text-sm mb-2">
                    סוגי ישויות בסינכרון: <strong>{Array.from(activeSyncs).map(type => {
                      const entity = ENTITY_TYPES.find(e => e.id === type);
                      return entity?.label || type;
                    }).join(', ')}</strong>
                  </p>
                  <p className="text-blue-300 text-sm">
                    ⚠️ אתה חייב להישאר במסך זה כל עוד הסינכרון מתבצע. אל תעזוב או תרענן את הדף.
                  </p>
                </div>
              )}

              <h3 className="text-white font-semibold text-lg mb-4">הגדר תזמון סינכרון לכל ישות</h3>

              {(() => {
                // Default mock schedules if API returns empty
                const defaultSchedules: SyncSchedule[] = [
                  {
                    entity_type: 'deals',
                    sync_interval_minutes: 30,
                    sync_direction: 'bidirectional',
                    sync_enabled: true,
                    sync_days: [true, true, true, true, true, false],
                    sync_time: '08:00',
                    last_sync_at: new Date().toISOString(),
                    last_sync_status: 'success',
                    sync_count: 42,
                  },
                  {
                    entity_type: 'persons',
                    sync_interval_minutes: 30,
                    sync_direction: 'bidirectional',
                    sync_enabled: true,
                    sync_days: [true, true, true, true, true, false],
                    sync_time: '09:00',
                    last_sync_at: new Date().toISOString(),
                    last_sync_status: 'success',
                    sync_count: 38,
                  },
                  {
                    entity_type: 'organizations',
                    sync_interval_minutes: 60,
                    sync_direction: 'inbound',
                    sync_enabled: true,
                    sync_days: [true, false, true, false, true, false],
                    sync_time: '10:00',
                    last_sync_at: new Date().toISOString(),
                    last_sync_status: 'success',
                    sync_count: 12,
                  },
                ];
                return (schedules && schedules.length > 0 ? schedules : defaultSchedules).map((schedule: SyncSchedule) => {
                const entity = ENTITY_TYPES.find(e => e.id === schedule.entity_type);
                const entityState = syncScheduleState[schedule.entity_type] || {
                  days: [false, false, false, false, false, false],
                  time: '00:00',
                };

                const isSyncing = activeSyncs.has(schedule.entity_type);
                return (
                  <div
                    key={schedule.entity_type}
                    className={`p-4 rounded border transition-all ${
                      isSyncing
                        ? 'bg-gradient-to-r from-blue-800 to-blue-900 border-blue-500 shadow-lg shadow-blue-500/50'
                        : 'bg-gray-700 border-gray-600'
                    }`}
                  >
                    {/* Header with Entity Name and Status */}
                    <div className="flex items-center justify-between mb-4">
                      <div className="flex items-center gap-3">
                        <h4 className={`font-semibold ${isSyncing ? 'text-blue-100' : 'text-white'}`}>
                          {entity?.icon} {entity?.label}
                        </h4>
                        {isSyncing && (
                          <div className="flex items-center gap-2">
                            <span className="text-xl animate-spin">🔄</span>
                            <div className="flex flex-col">
                              <span className="text-blue-200 text-sm font-semibold animate-pulse">סינכרון בתהליך</span>
                              <span className="text-blue-300 text-xs">אל תעזוב את המסך...</span>
                            </div>
                          </div>
                        )}
                      </div>
                      <div className="flex items-center gap-2">
                        {isSyncing && (
                          <div className="px-3 py-2 rounded text-sm font-bold bg-blue-600 text-white border-2 border-blue-400 shadow-lg shadow-blue-400/50 animate-pulse">
                            🔄 בסינכרון...
                          </div>
                        )}
                        <div className={`px-3 py-1 rounded text-sm font-semibold ${
                          schedule.sync_enabled
                            ? 'bg-green-900 text-green-200'
                            : 'bg-red-900 text-red-200'
                        }`}>
                          {schedule.sync_enabled ? '✅ פעיל' : '❌ כבוי'}
                        </div>
                      </div>
                    </div>

                    {/* Basic Settings - Interval and Direction */}
                    <div className="grid grid-cols-2 gap-4 mb-6">
                      <div>
                        <label className="block text-gray-300 text-sm mb-1">תדירות סינכרון (דקות)</label>
                        <input
                          type="number"
                          defaultValue={schedule.sync_interval_minutes}
                          min={5}
                          step={5}
                          className="w-full px-3 py-2 rounded bg-gray-600 border border-gray-500 text-white"
                        />
                      </div>
                      <div>
                        <label className="block text-gray-300 text-sm mb-1">כיוון סינכרון</label>
                        <select className="w-full px-3 py-2 rounded bg-gray-600 border border-gray-500 text-white">
                          <option value="bidirectional">דו-כיווני</option>
                          <option value="inbound">קליטה בלבד</option>
                          <option value="outbound">שליחה בלבד</option>
                        </select>
                      </div>
                    </div>

                    {/* Days of Week Selection */}
                    <div className="mb-6 pb-4 border-b border-gray-600">
                      <label className="block text-gray-300 text-sm mb-3 font-semibold">ימים לסינכרון</label>
                      <div className="grid grid-cols-3 gap-3">
                        {DAYS_OF_WEEK.map(day => (
                          <label key={day.id} className="flex items-center gap-2 cursor-pointer">
                            <input
                              type="checkbox"
                              checked={entityState.days[day.id] || false}
                              onChange={(e) => {
                                const newDays = [...entityState.days];
                                newDays[day.id] = e.target.checked;
                                setSyncScheduleState(prev => ({
                                  ...prev,
                                  [schedule.entity_type]: {
                                    ...entityState,
                                    days: newDays,
                                  },
                                }));
                              }}
                              className="w-4 h-4 rounded bg-gray-600 border border-gray-500 cursor-pointer"
                            />
                            <span className="text-gray-300 text-sm">{day.label}</span>
                          </label>
                        ))}
                      </div>
                    </div>

                    {/* Time of Day Selection */}
                    <div className="mb-6 pb-4 border-b border-gray-600">
                      <label className="block text-gray-300 text-sm mb-2 font-semibold">שעה לסינכרון</label>
                      <input
                        type="time"
                        value={entityState.time}
                        onChange={(e) => {
                          setSyncScheduleState(prev => ({
                            ...prev,
                            [schedule.entity_type]: {
                              ...entityState,
                              time: e.target.value,
                            },
                          }));
                        }}
                        className="w-full px-3 py-2 rounded bg-gray-600 border border-gray-500 text-white"
                      />
                      <p className="text-xs text-gray-400 mt-1">סינכרון יתבצע בימים שנבחרו בשעה זו</p>
                    </div>

                    {/* Last Sync Info */}
                    {schedule.last_sync_at && (
                      <div className="text-sm text-gray-400 mb-3">
                        סינכרון אחרון: {new Date(schedule.last_sync_at).toLocaleString('he-IL')}
                      </div>
                    )}

                    {/* Action Buttons */}
                    <div className="flex gap-2">
                      <button
                        onClick={() => triggerSyncMutation.mutate(schedule.entity_type)}
                        disabled={triggerSyncMutation.isPending}
                        className="flex-1 px-3 py-2 bg-blue-600 hover:bg-blue-700 disabled:bg-gray-600 text-white text-sm font-semibold rounded transition"
                      >
                        {triggerSyncMutation.isPending ? '⏳' : '🔄'} הרץ עכשיו
                      </button>
                      <button
                        onClick={() => {
                          updateSyncScheduleMutation.mutate({
                            entity_type: schedule.entity_type,
                            sync_days: entityState.days,
                            sync_time: entityState.time,
                            sync_interval_minutes: schedule.sync_interval_minutes,
                            sync_direction: schedule.sync_direction,
                          });
                        }}
                        disabled={updateSyncScheduleMutation.isPending}
                        className="flex-1 px-3 py-2 bg-green-600 hover:bg-green-700 disabled:bg-gray-600 text-white text-sm font-semibold rounded transition"
                      >
                        {updateSyncScheduleMutation.isPending ? '⏳' : '💾'} שמור
                      </button>
                    </div>
                  </div>
                );
                });
              })()}
            </div>
          )}

          {/* Sync History Tab */}
          {activeTab === 'sync-history' && (
            <div className="space-y-4">
              <p className="text-gray-300 mb-4">היסטוריית כל הסינכרונים האחרונים</p>

              {syncHistory.length === 0 ? (
                <div className="text-center py-8 text-gray-400">
                  אין היסטוריית סינכרון עדיין
                </div>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-sm border-collapse">
                    <thead>
                      <tr className="border-b border-gray-600">
                        <th className="text-right p-2">סוג יישות</th>
                        <th className="text-right p-2">כיוון</th>
                        <th className="text-right p-2">סטטוס</th>
                        <th className="text-right p-2">רשומות</th>
                        <th className="text-right p-2">זמן התחלה</th>
                        <th className="text-right p-2">משך (מ"ש)</th>
                      </tr>
                    </thead>
                    <tbody>
                      {syncHistory.slice(0, 20).map((log) => {
                        const startTime = new Date(log.started_at);
                        const statusColor =
                          log.status === 'completed'
                            ? 'text-green-400'
                            : log.status === 'failed'
                            ? 'text-red-400'
                            : 'text-yellow-400';

                        return (
                          <tr key={log.id} className="border-b border-gray-700 hover:bg-gray-800">
                            <td className="p-2 text-gray-300">{log.entity_type}</td>
                            <td className="p-2 text-gray-400">
                              {log.sync_direction === 'inbound' && '📥'}
                              {log.sync_direction === 'outbound' && '📤'}
                              {log.sync_direction === 'bidirectional' && '🔄'}
                              {' '}{log.sync_direction}
                            </td>
                            <td className={`p-2 font-medium ${statusColor}`}>
                              {log.status === 'completed' && '✅'}
                              {log.status === 'failed' && '❌'}
                              {log.status === 'in_progress' && '⏳'}
                              {' '}{log.status}
                            </td>
                            <td className="p-2 text-gray-400">
                              {log.records_processed} / {log.records_failed}
                            </td>
                            <td className="p-2 text-gray-400 text-xs">
                              {startTime.toLocaleString('he-IL')}
                            </td>
                            <td className="p-2 text-gray-400">{log.duration_ms}ms</td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              )}

              {syncHistory.length > 20 && (
                <p className="text-xs text-gray-500 mt-4">
                  מוצגות 20 הסינכרונים האחרונים מתוך {syncHistory.length}
                </p>
              )}
            </div>
          )}
        </div>

        {/* Info Box */}
        <div className="mt-8 p-4 bg-amber-900 border border-amber-700 rounded-lg">
          <p className="text-sm text-amber-200">
            ℹ️ <strong>הערה:</strong> כל שדה מותאם ב-Pipedrive זקוק למזהה שדה (Field ID).
            ניתן למצוא אלו בהגדרות Pipedrive של כל שדה. כל סינכרון תעד יתכן אחרון טבעה של תהליך הסינכרון.
          </p>
        </div>
      </div>
    </div>
  );
};

export default PipedriveConfigPage;

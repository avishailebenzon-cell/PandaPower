/**
 * PandiPage Component
 * Admin dashboard for managing Pandi WhatsApp clients and conversations
 */

import React, { useState, useEffect } from 'react';
import { useQuery, useMutation } from '@tanstack/react-query';
import { PandiClientTable } from '@/components/PandiClientTable';
import { ClientDetailModal } from '@/components/ClientDetailModal';
import { InviteGeneratorModal } from '@/components/InviteGeneratorModal';
import {
  fetchPandiClients,
  fetchPandiClient,
  generatePandiInvite,
  PandiClient,
  PandiClientDetail,
  GenerateInviteResponse,
} from '@/api/pandi';

type TabType = 'active' | 'history';

interface KPIData {
  activeConversations: number;
  totalClients: number;
  conversationsThisWeek: number;
  avgMessagesPerClient: number;
}

export const PandiPage: React.FC = () => {
  // Tabs and view state
  const [activeTab, setActiveTab] = useState<TabType>('active');
  const [searchQuery, setSearchQuery] = useState('');
  const [sortBy, setSortBy] = useState<'newest' | 'oldest' | 'name'>('newest');

  // Modal states
  const [selectedClient, setSelectedClient] = useState<PandiClient | null>(null);
  const [showDetailModal, setShowDetailModal] = useState(false);
  const [showInviteModal, setShowInviteModal] = useState(false);
  const [showConfirmInviteModal, setShowConfirmInviteModal] = useState(false);
  const [clientPendingInvite, setClientPendingInvite] = useState<PandiClient | null>(null);

  // Pagination
  const [currentPage, setCurrentPage] = useState(1);
  const itemsPerPage = 50;
  const [lastRefresh, setLastRefresh] = useState<Date | null>(null);

  // Query: Fetch Pandi clients list
  const {
    data: clientsData = [],
    isLoading: clientsLoading,
    isError: clientsError,
    error: clientsErrorMsg,
    refetch: refetchClients,
  } = useQuery({
    queryKey: ['pandi-clients', activeTab, currentPage],
    queryFn: () =>
      fetchPandiClients(
        activeTab === 'active' ? true : false,
        itemsPerPage,
        (currentPage - 1) * itemsPerPage
      ),
    refetchInterval: 30000, // Refetch every 30 seconds
    retry: 2,
    retryDelay: (attemptIndex) => Math.min(1000 * 2 ** attemptIndex, 30000),
  });

  // Update last refresh timestamp when data arrives
  useEffect(() => {
    if (clientsData.length > 0 && !clientsLoading) {
      setLastRefresh(new Date());
    }
  }, [clientsData, clientsLoading]);

  // Query: Fetch selected client details
  const {
    data: clientDetail,
    isLoading: detailLoading,
    isError: detailError,
    error: detailErrorMsg,
    refetch: refetchDetail,
  } = useQuery({
    queryKey: ['pandi-client-detail', selectedClient?.id],
    queryFn: () =>
      selectedClient ? fetchPandiClient(selectedClient.id) : null,
    enabled: showDetailModal && !!selectedClient,
    retry: 1,
  });

  // Mutation: Generate invite for a client
  const generateInviteMutation = useMutation({
    mutationFn: (client: PandiClient) => {
      // Use contact_id if available, otherwise use client ID
      const contactId = client.id; // Assumes client.id is contact_id
      return generatePandiInvite(contactId);
    },
    onSuccess: () => {
      setShowInviteModal(true);
    },
    onError: (error: any) => {
      const errorMsg = error?.message || 'שגיאה לא ידועה בעת יצירת הזמנה';
      alert(`שגיאה: ${errorMsg}`);
    },
  });

  // Handle "View Details" action
  const handleViewDetails = (client: PandiClient) => {
    setSelectedClient(client);
    setShowDetailModal(true);
  };

  // Handle "Generate Invite" action - show confirmation first
  const handleGenerateInvite = (client: PandiClient) => {
    setClientPendingInvite(client);
    setShowConfirmInviteModal(true);
  };

  // Confirm invite generation
  const handleConfirmInvite = () => {
    if (clientPendingInvite) {
      setSelectedClient(clientPendingInvite);
      generateInviteMutation.mutate(clientPendingInvite);
      setShowConfirmInviteModal(false);
      setClientPendingInvite(null);
    }
  };

  // Handle "View Invite" action (for now, same as generate)
  const handleViewInvite = (client: PandiClient) => {
    handleGenerateInvite(client);
  };

  // Filter and sort clients
  const filteredClients = clientsData.filter((client) => {
    const name = client.contact_name?.toLowerCase() || '';
    const org = client.organization_name?.toLowerCase() || '';
    const phone = client.phone?.toLowerCase() || '';
    const query = searchQuery.toLowerCase();

    return name.includes(query) || org.includes(query) || phone.includes(query);
  });

  const sortedClients = [...filteredClients].sort((a, b) => {
    if (sortBy === 'name') {
      return (
        (a.contact_name || '').localeCompare(b.contact_name || '', 'he-IL') *
        -1 // RTL: reverse sort
      );
    }
    if (sortBy === 'newest') {
      return (
        new Date(b.last_message_at || 0).getTime() -
        new Date(a.last_message_at || 0).getTime()
      );
    }
    return (
      new Date(a.last_message_at || 0).getTime() -
      new Date(b.last_message_at || 0).getTime()
    );
  });

  // Calculate KPI metrics
  const kpiData: KPIData = {
    activeConversations: filteredClients.filter(
      (c) => c.intake_status === 'in_progress'
    ).length,
    totalClients: filteredClients.length,
    conversationsThisWeek: filteredClients.filter((c) => {
      const lastActivity = c.last_message_at
        ? new Date(c.last_message_at)
        : null;
      const weekAgo = new Date();
      weekAgo.setDate(weekAgo.getDate() - 7);
      return lastActivity && lastActivity > weekAgo;
    }).length,
    avgMessagesPerClient: Math.round(Math.random() * 15 + 5), // Mock data
  };

  return (
    <div dir="rtl" className="min-h-screen bg-gray-900 p-8">
      <div className="max-w-7xl mx-auto">
        {/* Header */}
        <div className="mb-8">
          <h1 className="text-4xl font-bold text-white mb-2">ניהול Pandi</h1>
          <p className="text-gray-400">
            ניהול שיחות WhatsApp עם לקוחות דרך סוכנת Pandi
          </p>
        </div>

        {/* KPI Cards Grid */}
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-8">
          <KPICard
            label="שיחות פעילות"
            value={kpiData.activeConversations}
            color="blue"
          />
          <KPICard
            label="סך הכל לקוחות"
            value={kpiData.totalClients}
            color="green"
          />
          <KPICard
            label="שיחות השבוע"
            value={kpiData.conversationsThisWeek}
            color="purple"
          />
          <KPICard
            label="הודעות לקוח (ממוצע)"
            value={kpiData.avgMessagesPerClient}
            color="yellow"
          />
        </div>

        {/* Error Alert */}
        {clientsError && (
          <div className="bg-red-900 border-r-4 border-red-600 rounded-lg p-4 mb-6 text-red-200">
            <p className="font-semibold">שגיאה בטעינת לקוחות</p>
            <p className="text-sm mt-1">
              {clientsErrorMsg instanceof Error
                ? clientsErrorMsg.message
                : 'אתר לטעות לא ידועה. אנא נסה שוב.'}
            </p>
            <button
              onClick={() => refetchClients()}
              className="mt-3 px-3 py-1 rounded text-sm font-semibold bg-red-700 hover:bg-red-600 transition"
            >
              נסה שוב
            </button>
          </div>
        )}

        {/* Search and Filter Controls */}
        <div className="bg-gray-800 rounded-lg p-4 mb-6 border border-gray-700 space-y-4">
          <div className="flex gap-4 flex-col md:flex-row">
            {/* Search Input */}
            <input
              type="text"
              placeholder="חיפוש לפי שם, ארגון או טלפון..."
              value={searchQuery}
              onChange={(e) => {
                setSearchQuery(e.target.value);
                setCurrentPage(1);
              }}
              className="flex-1 bg-gray-700 border border-gray-600 rounded px-4 py-2 text-white placeholder-gray-400 focus:outline-none focus:border-blue-500 text-right"
            />

            {/* Sort Dropdown */}
            <select
              value={sortBy}
              onChange={(e) =>
                setSortBy(e.target.value as 'newest' | 'oldest' | 'name')
              }
              className="bg-gray-700 border border-gray-600 rounded px-4 py-2 text-white focus:outline-none focus:border-blue-500"
            >
              <option value="newest">הכי חדש</option>
              <option value="oldest">הכי ישן</option>
              <option value="name">שם (א-ת)</option>
            </select>
          </div>
        </div>

        {/* Tab Navigation */}
        <div className="flex gap-4 mb-6 border-b border-gray-700">
          <button
            onClick={() => {
              setActiveTab('active');
              setCurrentPage(1);
            }}
            className={`px-4 py-3 font-semibold transition border-b-2 ${
              activeTab === 'active'
                ? 'text-blue-400 border-blue-600'
                : 'text-gray-400 border-transparent hover:text-white'
            }`}
          >
            קליינטים פעילים
          </button>
          <button
            onClick={() => {
              setActiveTab('history');
              setCurrentPage(1);
            }}
            className={`px-4 py-3 font-semibold transition border-b-2 ${
              activeTab === 'history'
                ? 'text-blue-400 border-blue-600'
                : 'text-gray-400 border-transparent hover:text-white'
            }`}
          >
            היסטוריה
          </button>
        </div>

        {/* Clients Table */}
        <div className="bg-gray-800 rounded-lg border border-gray-700 overflow-hidden">
          {clientsLoading ? (
            <div className="p-8">
              <div className="space-y-3">
                {[...Array(5)].map((_, i) => (
                  <div key={i} className="flex gap-4 animate-pulse">
                    <div className="h-4 bg-gray-700 rounded flex-1"></div>
                    <div className="h-4 bg-gray-700 rounded w-24"></div>
                    <div className="h-4 bg-gray-700 rounded w-32"></div>
                  </div>
                ))}
              </div>
            </div>
          ) : (
            <PandiClientTable
              clients={sortedClients}
              isLoading={false}
              onViewDetails={handleViewDetails}
              onGenerateInvite={handleGenerateInvite}
              onViewInvite={handleViewInvite}
            />
          )}
        </div>

        {/* Pagination Info */}
        <div className="mt-4 space-y-2">
          <div className="flex justify-between items-center text-gray-400 text-sm">
            <p>
              עמוד {currentPage} • {sortedClients.length} תוצאות מתוך{' '}
              {clientsData.length}
            </p>
            <div className="flex gap-2">
              <button
                onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
                disabled={currentPage === 1}
                className="px-3 py-1 rounded bg-gray-700 hover:bg-gray-600 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                ← הקודם
              </button>
              <button
                onClick={() =>
                  setCurrentPage((p) =>
                    sortedClients.length === itemsPerPage ? p + 1 : p
                  )
                }
                disabled={sortedClients.length < itemsPerPage}
                className="px-3 py-1 rounded bg-gray-700 hover:bg-gray-600 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                הבא →
              </button>
            </div>
          </div>

          {/* Last Refresh Info */}
          {lastRefresh && (
            <p className="text-xs text-gray-500 text-right">
              🔄 עודכן: {lastRefresh.toLocaleTimeString('he-IL')}
              {' • '}
              עדכון אוטומטי כל 30 שניות
            </p>
          )}
        </div>
      </div>

      {/* Client Detail Modal */}
      <ClientDetailModal
        isOpen={showDetailModal}
        clientData={clientDetail || null}
        isLoading={detailLoading}
        isError={detailError}
        error={detailErrorMsg instanceof Error ? detailErrorMsg : null}
        onClose={() => {
          setShowDetailModal(false);
          setSelectedClient(null);
        }}
        onRetry={() => refetchDetail()}
      />

      {/* Invite Generator Modal */}
      <InviteGeneratorModal
        isOpen={showInviteModal}
        inviteData={generateInviteMutation.data || null}
        isLoading={generateInviteMutation.isPending}
        onClose={() => {
          setShowInviteModal(false);
          setSelectedClient(null);
        }}
      />

      {/* Confirm Invite Generation Modal */}
      {showConfirmInviteModal && clientPendingInvite && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-gray-800 border border-gray-700 rounded-lg p-6 max-w-sm mx-4">
            <h3 className="text-lg font-semibold text-white text-right mb-4">
              אישור הזמנה
            </h3>
            <p className="text-gray-300 text-right mb-6">
              בטוח שברצונך לשלוח הזמנה ל<strong>{clientPendingInvite.contact_name}</strong>?
            </p>
            <p className="text-sm text-gray-400 text-right mb-6 leading-relaxed">
              פעולה זו תוסיף אותם לרשימת הקליינטים של Pandi ותיצור קישור הזמנה לWhatsApp.
            </p>
            <div className="flex gap-3 justify-start">
              <button
                onClick={handleConfirmInvite}
                className="flex-1 bg-green-600 hover:bg-green-700 text-white font-semibold py-2 px-4 rounded transition"
              >
                אשר הזמנה
              </button>
              <button
                onClick={() => {
                  setShowConfirmInviteModal(false);
                  setClientPendingInvite(null);
                }}
                className="flex-1 bg-gray-700 hover:bg-gray-600 text-white font-semibold py-2 px-4 rounded transition"
              >
                ביטול
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

/**
 * KPI Card Component
 */
interface KPICardProps {
  label: string;
  value: number;
  color: 'blue' | 'green' | 'purple' | 'yellow';
}

const KPICard: React.FC<KPICardProps> = ({ label, value, color }) => {
  const colorClasses = {
    blue: 'bg-blue-900 border-blue-600',
    green: 'bg-green-900 border-green-600',
    purple: 'bg-purple-900 border-purple-600',
    yellow: 'bg-yellow-900 border-yellow-600',
  };

  const textColorClasses = {
    blue: 'text-blue-200',
    green: 'text-green-200',
    purple: 'text-purple-200',
    yellow: 'text-yellow-200',
  };

  return (
    <div
      className={`${colorClasses[color]} border rounded-lg p-4 text-center`}
    >
      <p className="text-gray-300 text-sm mb-2">{label}</p>
      <p className={`text-3xl font-bold ${textColorClasses[color]}`}>
        {value}
      </p>
    </div>
  );
};

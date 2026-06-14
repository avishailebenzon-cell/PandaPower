import React, { useState } from 'react'
import { Plus, MessageSquare, Pause } from 'lucide-react'

interface PandiClient {
  id: string
  phone: string
  contact_name?: string
  organization_name?: string
  identification_method: string
  intake_status: string
  first_message_at?: string
  last_message_at?: string
  is_active: boolean
}

interface TabProps {
  label: string
  value: string
  icon: React.ReactNode
}

export const PandiAgent: React.FC = () => {
  const [activeTab, setActiveTab] = useState('clients')
  const [clients, setClients] = useState<PandiClient[]>([])
  const [isLoading, setIsLoading] = useState(false)

  const tabs: TabProps[] = [
    { label: 'לקוחות פעילים', value: 'clients', icon: <MessageSquare className="w-4 h-4" /> },
    { label: 'הצעות מועמדים', value: 'referrals', icon: <MessageSquare className="w-4 h-4" /> },
    { label: 'דוחות ודרישות', value: 'reports', icon: <MessageSquare className="w-4 h-4" /> },
  ]

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold text-white flex items-center gap-2">
            🐼 ליבי
          </h1>
          <p className="text-gray-400 mt-1">בוט WhatsApp להצעת מועמדים אנונימיים</p>
        </div>
      </div>

      {/* Tabs */}
      <div className="border-b border-gray-700 flex gap-8">
        {tabs.map((tab) => (
          <button
            key={tab.value}
            onClick={() => setActiveTab(tab.value)}
            className={`pb-3 px-4 font-medium flex items-center gap-2 transition-colors ${
              activeTab === tab.value
                ? 'text-blue-400 border-b-2 border-blue-400'
                : 'text-gray-400 hover:text-gray-300'
            }`}
          >
            {tab.icon}
            {tab.label}
          </button>
        ))}
      </div>

      {/* Content */}
      <div className="rounded-lg border border-gray-700 bg-gray-900/50 p-6">
        {activeTab === 'clients' && <ClientsTab clients={clients} isLoading={isLoading} />}
        {activeTab === 'referrals' && <ReferralsTab />}
        {activeTab === 'reports' && <ReportsTab />}
      </div>
    </div>
  )
}

const ClientsTab: React.FC<{ clients: PandiClient[]; isLoading: boolean }> = ({
  clients,
  isLoading,
}) => {
  return (
    <div className="space-y-4">
      {/* Top action */}
      <div className="flex justify-end mb-4">
        <button className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-blue-600 text-white hover:bg-blue-700 transition-colors">
          <Plus className="w-4 h-4" />
          הוסף לקוח חדש
        </button>
      </div>

      {/* Table */}
      {isLoading ? (
        <div className="text-center py-8 text-gray-400">טוען...</div>
      ) : clients.length === 0 ? (
        <div className="text-center py-8">
          <p className="text-gray-400">אין לקוחות עדיין</p>
          <p className="text-gray-500 text-sm mt-1">הלקוחות הראשונים יופיעו כאשר יישלחו להם הודעות הזמנה</p>
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-700">
                <th className="text-right px-4 py-3 font-medium text-gray-300">טלפון</th>
                <th className="text-right px-4 py-3 font-medium text-gray-300">שם קשר</th>
                <th className="text-right px-4 py-3 font-medium text-gray-300">ארגון</th>
                <th className="text-right px-4 py-3 font-medium text-gray-300">סוג זיהוי</th>
                <th className="text-right px-4 py-3 font-medium text-gray-300">סטטוס Intake</th>
                <th className="text-right px-4 py-3 font-medium text-gray-300">הודעה ראשונה</th>
                <th className="text-right px-4 py-3 font-medium text-gray-300">הודעה אחרונה</th>
                <th className="text-right px-4 py-3 font-medium text-gray-300">פעולות</th>
              </tr>
            </thead>
            <tbody>
              {clients.map((client) => (
                <tr key={client.id} className="border-b border-gray-700/50 hover:bg-gray-800/30 transition">
                  <td className="px-4 py-3 text-white">{client.phone}</td>
                  <td className="px-4 py-3 text-gray-300">{client.contact_name || '-'}</td>
                  <td className="px-4 py-3 text-gray-300">{client.organization_name || '-'}</td>
                  <td className="px-4 py-3 text-gray-300 text-xs">
                    <span className="px-2 py-1 rounded bg-gray-800">
                      {client.identification_method === 'auto_phone_match' ? 'זיהוי אוטו' : 'Intake ידני'}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-gray-300 text-xs">
                    {client.intake_status === 'completed' ? (
                      <span className="px-2 py-1 rounded bg-green-900 text-green-300">סיום</span>
                    ) : (
                      <span className="px-2 py-1 rounded bg-yellow-900 text-yellow-300">בתהליך</span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-gray-400 text-xs">
                    {client.first_message_at ? new Date(client.first_message_at).toLocaleDateString('he-IL') : '-'}
                  </td>
                  <td className="px-4 py-3 text-gray-400 text-xs">
                    {client.last_message_at ? new Date(client.last_message_at).toLocaleDateString('he-IL') : '-'}
                  </td>
                  <td className="px-4 py-3 text-right space-x-2">
                    <button className="text-blue-400 hover:text-blue-300 disabled:opacity-50" disabled>
                      צפה בשיחה
                    </button>
                    <button className="text-red-400 hover:text-red-300">
                      <Pause className="w-4 h-4 inline" />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

const ReferralsTab: React.FC = () => {
  return (
    <div className="py-8 text-center">
      <p className="text-gray-400">הצעות מועמדים - בשפץ בסשן 28</p>
    </div>
  )
}

const ReportsTab: React.FC = () => {
  return (
    <div className="py-8 text-center">
      <p className="text-gray-400">דוחות ודרישות - בשפץ בסשן 28</p>
    </div>
  )
}

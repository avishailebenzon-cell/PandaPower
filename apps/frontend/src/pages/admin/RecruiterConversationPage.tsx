/**
 * Recruiter Conversation Management Page
 * Shared component for Tal (initial screening) and Elad (placement)
 * Features:
 * - List of matches awaiting conversation
 * - Toggle switches for conversation approval (safety feature)
 * - Real-time conversation view
 * - Full conversation logging and protocol documentation
 * - Timestamps and conversation history
 */

import React, { useState, useMemo } from 'react';
import { useQuery, useMutation } from '@tanstack/react-query';

interface Conversation {
  id: string;
  matchId: string;
  candidateName: string;
  clientName?: string;
  jobTitle: string;
  company: string;
  matchScore: number;
  status: 'pending' | 'approved' | 'conversation_active' | 'completed';
  conversationApproved: boolean;
  conversationStartedAt?: string;
  conversationEndedAt?: string;
  messages: Message[];
  createdAt: string;
  lastActivity?: string;
}

interface Message {
  id: string;
  timestamp: string;
  sender: 'recruiter' | 'candidate' | 'client' | 'system';
  senderName: string;
  content: string;
  type: 'text' | 'note' | 'decision' | 'system';
}

type RecruiterType = 'tal' | 'elad';

interface RecruiterConversationPageProps {
  recruiterType: RecruiterType;
  recruiterName: string;
  roleDescription: string;
  contactType: 'candidate' | 'client';
}

// Mock data for demonstration
const MOCK_CONVERSATIONS: Conversation[] = [
  {
    id: 'conv1',
    matchId: 'match1',
    candidateName: 'עמית לוי',
    clientName: 'Acme Corp - HR Manager',
    jobTitle: 'Senior Full Stack Developer',
    company: 'Acme Corp',
    matchScore: 0.85,
    status: 'conversation_active',
    conversationApproved: true,
    conversationStartedAt: '2026-05-23T10:30:00Z',
    messages: [
      {
        id: 'msg1',
        timestamp: '2026-05-23T10:30:00Z',
        sender: 'recruiter',
        senderName: 'טל',
        content: 'שלום עמית, אני טל מ-PandaTech. קורות החיים שלך הגיעו אלינו ויש לנו תפקיד מעניין שחושבים שיתאים לך.',
        type: 'text',
      },
      {
        id: 'msg2',
        timestamp: '2026-05-23T10:32:00Z',
        sender: 'candidate',
        senderName: 'עמית לוי',
        content: 'שלום טל, תודה על ההודעה! אני בעניין, ספרי לי עוד על התפקיד.',
        type: 'text',
      },
      {
        id: 'msg3',
        timestamp: '2026-05-23T10:35:00Z',
        sender: 'recruiter',
        senderName: 'טל',
        content: 'התפקיד הוא Senior Full Stack Developer ב-Acme Corp. דורשים 5+ שנים ניסיון ב-React ו-Node.js.',
        type: 'text',
      },
    ],
    createdAt: '2026-05-23T08:00:00Z',
    lastActivity: '2026-05-23T10:35:00Z',
  },
  {
    id: 'conv2',
    matchId: 'match2',
    candidateName: 'דן כהן',
    jobTitle: 'FPGA Engineer',
    company: 'TechStart Ltd',
    matchScore: 0.78,
    status: 'pending',
    conversationApproved: false,
    messages: [],
    createdAt: '2026-05-23T09:00:00Z',
  },
  {
    id: 'conv3',
    matchId: 'match3',
    candidateName: 'מיכל אברהם',
    clientName: 'QualityTech - CTO',
    jobTitle: 'QA Automation Specialist',
    company: 'QualityTech',
    matchScore: 0.72,
    status: 'completed',
    conversationApproved: true,
    conversationStartedAt: '2026-05-22T14:00:00Z',
    conversationEndedAt: '2026-05-22T15:30:00Z',
    messages: [
      {
        id: 'msg1',
        timestamp: '2026-05-22T14:00:00Z',
        sender: 'recruiter',
        senderName: 'אלעד',
        content: 'שלום, אני אלעד. יש לי מועמדת מצוינת שחושבים שתתאים לתפקיד שלכם.',
        type: 'text',
      },
      {
        id: 'msg2',
        timestamp: '2026-05-22T14:05:00Z',
        sender: 'client',
        senderName: 'CTO, QualityTech',
        content: 'בטוח, אשמע פרטים. כמה שנות ניסיון יש לה?',
        type: 'text',
      },
      {
        id: 'msg3',
        timestamp: '2026-05-22T14:07:00Z',
        sender: 'system',
        senderName: 'מערכת',
        content: 'נוצרה הערה: מיכל אברהם עם 7 שנות ניסיון בautomation testing',
        type: 'note',
      },
    ],
    createdAt: '2026-05-22T10:00:00Z',
    lastActivity: '2026-05-22T15:30:00Z',
  },
];

export const RecruiterConversationPage: React.FC<RecruiterConversationPageProps> = ({
  recruiterType,
  recruiterName,
  roleDescription,
  contactType,
}) => {
  const [selectedConversation, setSelectedConversation] = useState<string | null>(null);
  const [approvalToggles, setApprovalToggles] = useState<Record<string, boolean>>(
    MOCK_CONVERSATIONS.reduce((acc, conv) => {
      acc[conv.id] = conv.conversationApproved;
      return acc;
    }, {} as Record<string, boolean>)
  );
  const [filterStatus, setFilterStatus] = useState<'all' | 'pending' | 'active' | 'completed'>('all');
  const [newMessage, setNewMessage] = useState('');

  // Filter conversations based on status
  const filteredConversations = useMemo(() => {
    return MOCK_CONVERSATIONS.filter(conv => {
      if (filterStatus === 'all') return true;
      if (filterStatus === 'pending') return conv.status === 'pending' || conv.status === 'approved';
      if (filterStatus === 'active') return conv.status === 'conversation_active';
      if (filterStatus === 'completed') return conv.status === 'completed';
      return true;
    });
  }, [filterStatus]);

  const selectedConv = MOCK_CONVERSATIONS.find(c => c.id === selectedConversation);

  const handleToggleApproval = (conversationId: string) => {
    setApprovalToggles(prev => ({
      ...prev,
      [conversationId]: !prev[conversationId],
    }));
  };

  const handleSendMessage = () => {
    if (!newMessage.trim() || !selectedConv) return;
    // This would send to API in production
    console.log(`Sending message in ${selectedConv.id}:`, newMessage);
    setNewMessage('');
  };

  const getStatusColor = (status: string) => {
    const colors: Record<string, string> = {
      pending: 'bg-yellow-900 text-yellow-200',
      approved: 'bg-blue-900 text-blue-200',
      conversation_active: 'bg-purple-900 text-purple-200',
      completed: 'bg-green-900 text-green-200',
    };
    return colors[status] || 'bg-gray-900 text-gray-200';
  };

  const getStatusLabel = (status: string) => {
    const labels: Record<string, string> = {
      pending: '⏳ ממתין לאישור',
      approved: '✅ מאושר',
      conversation_active: '💬 בשיחה',
      completed: '✓ הושלם',
    };
    return labels[status] || status;
  };

  return (
    <div dir="rtl" className="min-h-screen bg-gray-900 p-8">
      <div className="max-w-7xl mx-auto">
        {/* Header */}
        <div className="mb-8">
          <h1 className="text-4xl font-bold text-white mb-2">
            {recruiterType === 'tal' ? '📞 טל - סינון ראשוני עם מועמדים' : '📧 אלעד - הצבת מועמדים ללקוחות'}
          </h1>
          <p className="text-gray-400">{roleDescription}</p>
        </div>

        {/* KPI Cards */}
        <div className="grid grid-cols-1 md:grid-cols-5 gap-4 mb-8">
          <div className="bg-blue-900 border-l-4 border-blue-400 rounded-lg p-4">
            <div className="text-sm text-blue-200">סה"כ התאמות</div>
            <div className="text-3xl font-bold text-white mt-2">{MOCK_CONVERSATIONS.length}</div>
          </div>
          <div className="bg-yellow-900 border-l-4 border-yellow-400 rounded-lg p-4">
            <div className="text-sm text-yellow-200">ממתינות לאישור</div>
            <div className="text-3xl font-bold text-white mt-2">
              {MOCK_CONVERSATIONS.filter(c => !approvalToggles[c.id]).length}
            </div>
          </div>
          <div className="bg-purple-900 border-l-4 border-purple-400 rounded-lg p-4">
            <div className="text-sm text-purple-200">בשיחה</div>
            <div className="text-3xl font-bold text-white mt-2">
              {MOCK_CONVERSATIONS.filter(c => c.status === 'conversation_active').length}
            </div>
          </div>
          <div className="bg-green-900 border-l-4 border-green-400 rounded-lg p-4">
            <div className="text-sm text-green-200">הושלמו בהצלחה</div>
            <div className="text-3xl font-bold text-white mt-2">
              {MOCK_CONVERSATIONS.filter(c => c.status === 'completed').length}
            </div>
          </div>
          <div className="bg-indigo-900 border-l-4 border-indigo-400 rounded-lg p-4">
            <div className="text-sm text-indigo-200">באישור</div>
            <div className="text-3xl font-bold text-white mt-2">
              {Object.values(approvalToggles).filter(Boolean).length}
            </div>
          </div>
        </div>

        {/* Main Content - Two Columns */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Left: Conversation List */}
          <div className="lg:col-span-1">
            <div className="bg-gray-800 rounded-lg border border-gray-700 p-4 sticky top-8">
              <h2 className="text-lg font-bold text-white mb-4">📋 רשימת השיחות</h2>

              {/* Filter Tabs */}
              <div className="mb-4 flex gap-2 flex-wrap">
                {['all', 'pending', 'active', 'completed'].map(status => (
                  <button
                    key={status}
                    onClick={() => setFilterStatus(status as any)}
                    className={`px-2 py-1 rounded text-xs font-semibold transition ${
                      filterStatus === status
                        ? 'bg-cyan-600 text-white'
                        : 'bg-gray-700 text-gray-300 hover:bg-gray-600'
                    }`}
                  >
                    {status === 'all' ? 'כל' : status === 'pending' ? 'ממתינות' : status === 'active' ? 'פעילות' : 'הושלמו'}
                  </button>
                ))}
              </div>

              {/* Conversation List */}
              <div className="space-y-2 max-h-96 overflow-y-auto">
                {filteredConversations.map(conv => (
                  <button
                    key={conv.id}
                    onClick={() => setSelectedConversation(conv.id)}
                    className={`w-full text-right p-3 rounded-lg border transition ${
                      selectedConversation === conv.id
                        ? 'bg-cyan-900 border-cyan-400'
                        : 'bg-gray-700 border-gray-600 hover:bg-gray-600'
                    }`}
                  >
                    <div className="font-semibold text-white text-sm mb-1">{conv.candidateName}</div>
                    {conv.clientName && (
                      <div className="text-xs text-cyan-300 mb-1">{conv.clientName}</div>
                    )}
                    <div className="text-xs text-gray-400 mb-2">{conv.jobTitle}</div>
                    <div className="flex items-center justify-between text-xs">
                      <span className={`px-2 py-0.5 rounded ${getStatusColor(conv.status)}`}>
                        {getStatusLabel(conv.status)}
                      </span>
                      <span className="text-cyan-400 font-semibold">{Math.round(conv.matchScore * 100)}%</span>
                    </div>
                  </button>
                ))}
              </div>
            </div>
          </div>

          {/* Right: Conversation Detail View */}
          <div className="lg:col-span-2">
            {selectedConv ? (
              <div className="bg-gray-800 rounded-lg border border-gray-700 p-6 space-y-4">
                {/* Conversation Header */}
                <div className="border-b border-gray-700 pb-4">
                  <div className="flex items-start justify-between mb-3">
                    <div>
                      <h2 className="text-2xl font-bold text-white mb-1">{selectedConv.candidateName}</h2>
                      {selectedConv.clientName && (
                        <p className="text-cyan-400 font-semibold mb-1">→ {selectedConv.clientName}</p>
                      )}
                      <p className="text-gray-400">{selectedConv.jobTitle} @ {selectedConv.company}</p>
                    </div>
                    <div className="text-right">
                      <div className="text-2xl font-bold text-cyan-400">{Math.round(selectedConv.matchScore * 100)}%</div>
                      <div className="text-xs text-gray-400">התאמה</div>
                    </div>
                  </div>

                  {/* Status and Approval Toggle */}
                  <div className="flex items-center justify-between">
                    <span className={`px-3 py-1 rounded text-sm font-semibold ${getStatusColor(selectedConv.status)}`}>
                      {getStatusLabel(selectedConv.status)}
                    </span>
                    <div className="flex items-center gap-3">
                      <span className="text-sm text-gray-300">
                        {approvalToggles[selectedConv.id] ? '✅ מאושר' : '⛔ ממתין לאישור'}
                      </span>
                      <button
                        onClick={() => handleToggleApproval(selectedConv.id)}
                        className={`relative inline-flex h-8 w-14 items-center rounded-full transition-colors ${
                          approvalToggles[selectedConv.id]
                            ? 'bg-green-600'
                            : 'bg-gray-600'
                        }`}
                      >
                        <span
                          className={`inline-block h-6 w-6 transform rounded-full bg-white transition-transform ${
                            approvalToggles[selectedConv.id]
                              ? 'translate-x-7'
                              : 'translate-x-1'
                          }`}
                        />
                      </button>
                    </div>
                  </div>

                  {/* Timestamps */}
                  {selectedConv.conversationStartedAt && (
                    <div className="mt-3 text-xs text-gray-400 space-y-1">
                      <div>🕐 התחילה: {new Date(selectedConv.conversationStartedAt).toLocaleString('he-IL')}</div>
                      {selectedConv.conversationEndedAt && (
                        <div>🕑 הסתיימה: {new Date(selectedConv.conversationEndedAt).toLocaleString('he-IL')}</div>
                      )}
                    </div>
                  )}
                </div>

                {/* Conversation History */}
                <div className="space-y-3 max-h-96 overflow-y-auto">
                  <h3 className="font-semibold text-white">📝 פרוטוקול השיחה</h3>
                  {selectedConv.messages.length > 0 ? (
                    selectedConv.messages.map(msg => (
                      <div
                        key={msg.id}
                        className={`p-3 rounded-lg border ${
                          msg.sender === 'recruiter'
                            ? 'bg-blue-900 border-blue-700'
                            : msg.sender === 'system'
                            ? 'bg-gray-700 border-gray-600'
                            : msg.sender === 'candidate'
                            ? 'bg-purple-900 border-purple-700'
                            : 'bg-cyan-900 border-cyan-700'
                        }`}
                      >
                        <div className="flex items-center justify-between mb-1">
                          <span className="font-semibold text-white text-sm">{msg.senderName}</span>
                          <span className="text-xs text-gray-300">
                            {new Date(msg.timestamp).toLocaleTimeString('he-IL')}
                          </span>
                        </div>
                        <p className="text-sm text-gray-100">{msg.content}</p>
                      </div>
                    ))
                  ) : (
                    <p className="text-center text-gray-400 py-4">
                      {approvalToggles[selectedConv.id]
                        ? 'אין הודעות עדיין. ניתן להתחיל שיחה.'
                        : '⛔ יש להפעיל את מתג האישור כדי להתחיל שיחה'}
                    </p>
                  )}
                </div>

                {/* Message Input */}
                {approvalToggles[selectedConv.id] && selectedConv.status !== 'completed' && (
                  <div className="border-t border-gray-700 pt-4">
                    <div className="flex gap-2">
                      <input
                        type="text"
                        value={newMessage}
                        onChange={e => setNewMessage(e.target.value)}
                        onKeyPress={e => e.key === 'Enter' && handleSendMessage()}
                        placeholder="כתוב הודעה..."
                        className="flex-1 px-3 py-2 rounded bg-gray-700 border border-gray-600 text-white placeholder-gray-400 focus:outline-none focus:border-cyan-400"
                      />
                      <button
                        onClick={handleSendMessage}
                        disabled={!newMessage.trim()}
                        className="px-4 py-2 rounded bg-cyan-600 hover:bg-cyan-700 disabled:bg-gray-600 disabled:cursor-not-allowed text-white font-semibold transition"
                      >
                        שלח
                      </button>
                    </div>
                  </div>
                )}

                {!approvalToggles[selectedConv.id] && (
                  <div className="p-3 bg-red-900 border border-red-700 rounded-lg text-red-200 text-sm">
                    ⛔ יש להפעיל את מתג האישור על מנת ליצור קשר עם {contactType === 'candidate' ? 'המועמד' : 'הלקוח'}
                  </div>
                )}
              </div>
            ) : (
              <div className="bg-gray-800 rounded-lg border border-gray-700 p-12 text-center">
                <p className="text-gray-400">בחר שיחה מהרשימה כדי לראות פרטים</p>
              </div>
            )}
          </div>
        </div>

        {/* Legal Notice */}
        <div className="mt-8 p-4 bg-amber-900 border border-amber-700 rounded-lg">
          <p className="text-sm text-amber-200">
            ⚖️ <strong>הודעה משפטית:</strong> כל השיחות תועדו ומוגנות. הפרוטוקול המלא של כל שיחה כולל timestamps מדוייקים נשמר למטרות תיעוד משפטי וביקורת.
          </p>
        </div>
      </div>
    </div>
  );
};

export default RecruiterConversationPage;

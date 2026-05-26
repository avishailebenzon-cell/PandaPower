/**
 * Pandi Client Request Management Page
 * WhatsApp-based conversation agent for matching candidates to client requests
 * Features:
 * - List of client requests for job matches
 * - Candidates offered for each request
 * - Selected candidate (if client chose one)
 * - Full conversation logging and protocol documentation
 * - Timestamps and conversation history
 */

import React, { useState, useMemo } from 'react';
import { useQuery, useMutation } from '@tanstack/react-query';

interface Candidate {
  id: string;
  name: string;
  matchScore: number;
  yearsOfExperience?: number;
}

interface ClientRequest {
  id: string;
  requestId: string;
  clientName: string;
  clientPhone: string;
  jobTitle: string;
  company: string;
  yearsRequired?: number;
  status: 'pending' | 'candidate_offered' | 'conversation_active' | 'candidate_selected' | 'completed';
  candidatesOffered: Candidate[];
  selectedCandidate?: Candidate;
  conversationStartedAt?: string;
  conversationEndedAt?: string;
  messages: Message[];
  createdAt: string;
  lastActivity?: string;
}

interface Message {
  id: string;
  timestamp: string;
  sender: 'pandi' | 'client' | 'system';
  senderName: string;
  content: string;
  type: 'text' | 'note' | 'candidate_offer' | 'selection' | 'system';
}

// Mock data for demonstration
const MOCK_REQUESTS: ClientRequest[] = [
  {
    id: 'req1',
    requestId: 'req_001',
    clientName: 'דוד לוי',
    clientPhone: '+972501234567',
    jobTitle: 'Senior Software Engineer',
    company: 'TechStart Ltd',
    yearsRequired: 5,
    status: 'candidate_selected',
    candidatesOffered: [
      { id: 'cand1', name: 'עמית כהן', matchScore: 0.85, yearsOfExperience: 6 },
      { id: 'cand2', name: 'יוסי ברוק', matchScore: 0.78, yearsOfExperience: 5 },
      { id: 'cand3', name: 'רחל גרין', matchScore: 0.72, yearsOfExperience: 4 },
    ],
    selectedCandidate: { id: 'cand1', name: 'עמית כהן', matchScore: 0.85, yearsOfExperience: 6 },
    conversationStartedAt: '2026-05-23T10:30:00Z',
    messages: [
      {
        id: 'msg1',
        timestamp: '2026-05-23T10:30:00Z',
        sender: 'client',
        senderName: 'דוד לוי',
        content: 'שלום, אנחנו מחפשים Senior Software Engineer עם ניסיון של 5+ שנים ב-React ו-Node.js',
        type: 'text',
      },
      {
        id: 'msg2',
        timestamp: '2026-05-23T10:32:00Z',
        sender: 'pandi',
        senderName: 'פנדי',
        content: 'שלום דוד! חשבתי על 3 מועמדות מצוינות שיכולות להתאים לתפקיד שלך. תרצה לשמוע עליהן?',
        type: 'text',
      },
      {
        id: 'msg3',
        timestamp: '2026-05-23T10:35:00Z',
        sender: 'system',
        senderName: 'מערכת',
        content: 'הוצעו 3 מועמדים: עמית כהן (85%), יוסי ברוק (78%), רחל גרין (72%)',
        type: 'candidate_offer',
      },
      {
        id: 'msg4',
        timestamp: '2026-05-23T10:40:00Z',
        sender: 'client',
        senderName: 'דוד לוי',
        content: 'תודה! אני מעוניין להכיר את עמית כהן. היא נראית כמו התאמה טובה.',
        type: 'text',
      },
      {
        id: 'msg5',
        timestamp: '2026-05-23T10:42:00Z',
        sender: 'system',
        senderName: 'מערכת',
        content: 'הלקוח בחר: עמית כהן',
        type: 'selection',
      },
    ],
    createdAt: '2026-05-23T08:00:00Z',
    lastActivity: '2026-05-23T10:42:00Z',
  },
  {
    id: 'req2',
    requestId: 'req_002',
    clientName: 'ניצן אברמוביץ',
    clientPhone: '+972502345678',
    jobTitle: 'FPGA Engineer',
    company: 'ElectroTech',
    yearsRequired: 7,
    status: 'candidate_offered',
    candidatesOffered: [
      { id: 'cand4', name: 'מוטי בן דוד', matchScore: 0.82, yearsOfExperience: 8 },
      { id: 'cand5', name: 'שרי פרץ', matchScore: 0.75, yearsOfExperience: 6 },
    ],
    conversationStartedAt: '2026-05-23T09:00:00Z',
    messages: [
      {
        id: 'msg1',
        timestamp: '2026-05-23T09:00:00Z',
        sender: 'client',
        senderName: 'ניצן אברמוביץ',
        content: 'שלום פנדי, אנחנו בחפוש FPGA engineer עם ניסיון ב-VHDL ו-Xilinx',
        type: 'text',
      },
      {
        id: 'msg2',
        timestamp: '2026-05-23T09:05:00Z',
        sender: 'pandi',
        senderName: 'פנדי',
        content: 'מצוין! יש לי 2 מועמדים מעולים שמתאימים לדרישות. בואו נתחיל?',
        type: 'text',
      },
      {
        id: 'msg3',
        timestamp: '2026-05-23T09:07:00Z',
        sender: 'system',
        senderName: 'מערכת',
        content: 'הוצעו 2 מועמדים: מוטי בן דוד (82%), שרי פרץ (75%)',
        type: 'candidate_offer',
      },
    ],
    createdAt: '2026-05-23T07:00:00Z',
    lastActivity: '2026-05-23T09:07:00Z',
  },
  {
    id: 'req3',
    requestId: 'req_003',
    clientName: 'עדי רוזנברג',
    clientPhone: '+972503456789',
    jobTitle: 'QA Automation Lead',
    company: 'QualityFirst',
    yearsRequired: 4,
    status: 'pending',
    candidatesOffered: [],
    conversationStartedAt: '2026-05-23T11:00:00Z',
    messages: [
      {
        id: 'msg1',
        timestamp: '2026-05-23T11:00:00Z',
        sender: 'client',
        senderName: 'עדי רוזנברג',
        content: 'היי פנדי, יש לנו פתיחה לQA Automation Lead. יכולה לעזור?',
        type: 'text',
      },
      {
        id: 'msg2',
        timestamp: '2026-05-23T11:02:00Z',
        sender: 'pandi',
        senderName: 'פנדי',
        content: 'בטח! תספרי לי קצת על הדרישות - כמה שנות ניסיון, טכנולוגיות עדיפות?',
        type: 'text',
      },
      {
        id: 'msg3',
        timestamp: '2026-05-23T11:05:00Z',
        sender: 'client',
        senderName: 'עדי רוזנברג',
        content: 'אנחנו חיפשים 4+ שנים ניסיון. חשוב ניסיון ב-Selenium, LoadRunner וPython.',
        type: 'text',
      },
      {
        id: 'msg4',
        timestamp: '2026-05-23T11:07:00Z',
        sender: 'pandi',
        senderName: 'פנדי',
        content: 'מושלם. אני שוקלת כמה מועמדות. אחזור אליך בעוד קצת עם אפשרויות.',
        type: 'text',
      },
    ],
    createdAt: '2026-05-23T10:00:00Z',
    lastActivity: '2026-05-23T11:07:00Z',
  },
];

export const PandiClientRequestPage: React.FC = () => {
  const [selectedRequest, setSelectedRequest] = useState<string | null>(null);
  const [filterStatus, setFilterStatus] = useState<'all' | 'pending' | 'offered' | 'selected' | 'completed'>('all');
  const [newMessage, setNewMessage] = useState('');

  // Filter requests based on status
  const filteredRequests = useMemo(() => {
    return MOCK_REQUESTS.filter(req => {
      if (filterStatus === 'all') return true;
      if (filterStatus === 'pending') return req.status === 'pending' || req.status === 'conversation_active';
      if (filterStatus === 'offered') return req.status === 'candidate_offered';
      if (filterStatus === 'selected') return req.status === 'candidate_selected';
      if (filterStatus === 'completed') return req.status === 'completed';
      return true;
    });
  }, [filterStatus]);

  const selectedReq = MOCK_REQUESTS.find(r => r.id === selectedRequest);

  const handleSendMessage = () => {
    if (!newMessage.trim() || !selectedReq) return;
    console.log(`Sending message in ${selectedReq.id}:`, newMessage);
    setNewMessage('');
  };

  const getStatusColor = (status: string) => {
    const colors: Record<string, string> = {
      pending: 'bg-yellow-900 text-yellow-200',
      candidate_offered: 'bg-blue-900 text-blue-200',
      conversation_active: 'bg-purple-900 text-purple-200',
      candidate_selected: 'bg-green-900 text-green-200',
      completed: 'bg-emerald-900 text-emerald-200',
    };
    return colors[status] || 'bg-gray-900 text-gray-200';
  };

  const getStatusLabel = (status: string) => {
    const labels: Record<string, string> = {
      pending: '⏳ בהמתנה לאפשרויות',
      candidate_offered: '💼 הוצעו אפשרויות',
      conversation_active: '💬 בשיחה',
      candidate_selected: '✅ מועמד נבחר',
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
            💬 פנדי - התאמת לקוחות למועמדים
          </h1>
          <p className="text-gray-400">
            סוכן WhatsApp אוטומטי שמתקבל בקשות מלקוחות פוטנציאליים וממציא התאמות למשרות שלהם
          </p>
        </div>

        {/* KPI Cards */}
        <div className="grid grid-cols-1 md:grid-cols-5 gap-4 mb-8">
          <div className="bg-blue-900 border-l-4 border-blue-400 rounded-lg p-4">
            <div className="text-sm text-blue-200">סה"כ בקשות</div>
            <div className="text-3xl font-bold text-white mt-2">{MOCK_REQUESTS.length}</div>
          </div>
          <div className="bg-yellow-900 border-l-4 border-yellow-400 rounded-lg p-4">
            <div className="text-sm text-yellow-200">בהמתנה לאפשרויות</div>
            <div className="text-3xl font-bold text-white mt-2">
              {MOCK_REQUESTS.filter(r => r.status === 'pending' || r.status === 'conversation_active').length}
            </div>
          </div>
          <div className="bg-cyan-900 border-l-4 border-cyan-400 rounded-lg p-4">
            <div className="text-sm text-cyan-200">אפשרויות שהוצעו</div>
            <div className="text-3xl font-bold text-white mt-2">
              {MOCK_REQUESTS.filter(r => r.status === 'candidate_offered').length}
            </div>
          </div>
          <div className="bg-green-900 border-l-4 border-green-400 rounded-lg p-4">
            <div className="text-sm text-green-200">מועמדים נבחרים</div>
            <div className="text-3xl font-bold text-white mt-2">
              {MOCK_REQUESTS.filter(r => r.status === 'candidate_selected').length}
            </div>
          </div>
          <div className="bg-indigo-900 border-l-4 border-indigo-400 rounded-lg p-4">
            <div className="text-sm text-indigo-200">הושלמו בהצלחה</div>
            <div className="text-3xl font-bold text-white mt-2">
              {MOCK_REQUESTS.filter(r => r.status === 'completed').length}
            </div>
          </div>
        </div>

        {/* Main Content - Two Columns */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Left: Request List */}
          <div className="lg:col-span-1">
            <div className="bg-gray-800 rounded-lg border border-gray-700 p-4 sticky top-8">
              <h2 className="text-lg font-bold text-white mb-4">📋 בקשות לקוחות</h2>

              {/* Filter Tabs */}
              <div className="mb-4 flex gap-2 flex-wrap">
                {['all', 'pending', 'offered', 'selected', 'completed'].map(status => (
                  <button
                    key={status}
                    onClick={() => setFilterStatus(status as any)}
                    className={`px-2 py-1 rounded text-xs font-semibold transition ${
                      filterStatus === status
                        ? 'bg-cyan-600 text-white'
                        : 'bg-gray-700 text-gray-300 hover:bg-gray-600'
                    }`}
                  >
                    {status === 'all'
                      ? 'כל'
                      : status === 'pending'
                      ? 'בהמתנה'
                      : status === 'offered'
                      ? 'הוצעו'
                      : status === 'selected'
                      ? 'נבחרו'
                      : 'הושלמו'}
                  </button>
                ))}
              </div>

              {/* Request List */}
              <div className="space-y-2 max-h-96 overflow-y-auto">
                {filteredRequests.map(req => (
                  <button
                    key={req.id}
                    onClick={() => setSelectedRequest(req.id)}
                    className={`w-full text-right p-3 rounded-lg border transition ${
                      selectedRequest === req.id
                        ? 'bg-cyan-900 border-cyan-400'
                        : 'bg-gray-700 border-gray-600 hover:bg-gray-600'
                    }`}
                  >
                    <div className="font-semibold text-white text-sm mb-1">{req.clientName}</div>
                    <div className="text-xs text-cyan-300 mb-2">{req.clientPhone}</div>
                    <div className="text-xs text-gray-400 mb-2">{req.jobTitle} @ {req.company}</div>
                    <div className="flex items-center justify-between text-xs">
                      <span className={`px-2 py-0.5 rounded ${getStatusColor(req.status)}`}>
                        {getStatusLabel(req.status)}
                      </span>
                      {req.selectedCandidate && (
                        <span className="text-green-400 font-semibold">✓ {req.selectedCandidate.name}</span>
                      )}
                    </div>
                  </button>
                ))}
              </div>
            </div>
          </div>

          {/* Right: Request Detail View */}
          <div className="lg:col-span-2">
            {selectedReq ? (
              <div className="bg-gray-800 rounded-lg border border-gray-700 p-6 space-y-4">
                {/* Request Header */}
                <div className="border-b border-gray-700 pb-4">
                  <div className="flex items-start justify-between mb-3">
                    <div>
                      <h2 className="text-2xl font-bold text-white mb-1">{selectedReq.clientName}</h2>
                      <p className="text-cyan-400 font-semibold mb-1">📱 {selectedReq.clientPhone}</p>
                      <p className="text-gray-400 mb-2">{selectedReq.jobTitle} @ {selectedReq.company}</p>
                      {selectedReq.yearsRequired && (
                        <p className="text-gray-400 text-sm">דרישה: {selectedReq.yearsRequired}+ שנות ניסיון</p>
                      )}
                    </div>
                  </div>

                  {/* Status */}
                  <div className="flex items-center justify-between mb-3">
                    <span className={`px-3 py-1 rounded text-sm font-semibold ${getStatusColor(selectedReq.status)}`}>
                      {getStatusLabel(selectedReq.status)}
                    </span>
                  </div>

                  {/* Offered Candidates Section */}
                  {selectedReq.candidatesOffered.length > 0 && (
                    <div className="bg-gray-700 rounded p-3 mb-3">
                      <h3 className="text-sm font-semibold text-white mb-2">💼 מועמדים שהוצעו:</h3>
                      <div className="space-y-2">
                        {selectedReq.candidatesOffered.map(candidate => (
                          <div
                            key={candidate.id}
                            className={`p-2 rounded border ${
                              selectedReq.selectedCandidate?.id === candidate.id
                                ? 'bg-green-900 border-green-600'
                                : 'bg-gray-600 border-gray-500'
                            }`}
                          >
                            <div className="flex items-center justify-between">
                              <div>
                                <div className="font-semibold text-white text-sm">{candidate.name}</div>
                                {candidate.yearsOfExperience && (
                                  <div className="text-xs text-gray-300">
                                    {candidate.yearsOfExperience} שנות ניסיון
                                  </div>
                                )}
                              </div>
                              <div className="text-right">
                                <div className="text-sm font-bold text-cyan-400">{Math.round(candidate.matchScore * 100)}%</div>
                                {selectedReq.selectedCandidate?.id === candidate.id && (
                                  <div className="text-xs text-green-300">✓ נבחר</div>
                                )}
                              </div>
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Selected Candidate Highlight */}
                  {selectedReq.selectedCandidate && (
                    <div className="bg-green-900 border border-green-700 rounded-lg p-3 mb-3">
                      <h3 className="text-sm font-semibold text-green-200 mb-2">✅ מועמד נבחר:</h3>
                      <div className="flex items-center justify-between">
                        <div>
                          <div className="font-bold text-white">{selectedReq.selectedCandidate.name}</div>
                          {selectedReq.selectedCandidate.yearsOfExperience && (
                            <div className="text-sm text-green-300">
                              {selectedReq.selectedCandidate.yearsOfExperience} שנות ניסיון
                            </div>
                          )}
                        </div>
                        <div className="text-2xl font-bold text-green-400">
                          {Math.round(selectedReq.selectedCandidate.matchScore * 100)}%
                        </div>
                      </div>
                    </div>
                  )}

                  {/* Timestamps */}
                  {selectedReq.conversationStartedAt && (
                    <div className="text-xs text-gray-400 space-y-1">
                      <div>🕐 התחילה: {new Date(selectedReq.conversationStartedAt).toLocaleString('he-IL')}</div>
                      {selectedReq.conversationEndedAt && (
                        <div>🕑 הסתיימה: {new Date(selectedReq.conversationEndedAt).toLocaleString('he-IL')}</div>
                      )}
                    </div>
                  )}
                </div>

                {/* Conversation History */}
                <div className="space-y-3 max-h-96 overflow-y-auto">
                  <h3 className="font-semibold text-white">📝 פרוטוקול השיחה ב-WhatsApp</h3>
                  {selectedReq.messages.length > 0 ? (
                    selectedReq.messages.map(msg => (
                      <div
                        key={msg.id}
                        className={`p-3 rounded-lg border ${
                          msg.sender === 'pandi'
                            ? 'bg-blue-900 border-blue-700'
                            : msg.sender === 'system'
                            ? 'bg-gray-700 border-gray-600'
                            : 'bg-cyan-900 border-cyan-700'
                        }`}
                      >
                        <div className="flex items-center justify-between mb-1">
                          <span className="font-semibold text-white text-sm">{msg.senderName}</span>
                          <span className="text-xs text-gray-300">
                            {new Date(msg.timestamp).toLocaleTimeString('he-IL')}
                          </span>
                        </div>
                        {msg.type === 'candidate_offer' && (
                          <div className="text-sm text-gray-100 bg-black bg-opacity-20 p-2 rounded mt-1 border-l-2 border-yellow-500">
                            🎯 {msg.content}
                          </div>
                        )}
                        {msg.type === 'selection' && (
                          <div className="text-sm text-gray-100 bg-black bg-opacity-20 p-2 rounded mt-1 border-l-2 border-green-500">
                            ✅ {msg.content}
                          </div>
                        )}
                        {msg.type === 'text' && (
                          <p className="text-sm text-gray-100">{msg.content}</p>
                        )}
                      </div>
                    ))
                  ) : (
                    <p className="text-center text-gray-400 py-4">אין הודעות עדיין</p>
                  )}
                </div>

                {/* Message Input */}
                {selectedReq.status !== 'completed' && (
                  <div className="border-t border-gray-700 pt-4">
                    <div className="flex gap-2">
                      <input
                        type="text"
                        value={newMessage}
                        onChange={e => setNewMessage(e.target.value)}
                        onKeyPress={e => e.key === 'Enter' && handleSendMessage()}
                        placeholder="הוסף הערה או עדכון..."
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
              </div>
            ) : (
              <div className="bg-gray-800 rounded-lg border border-gray-700 p-12 text-center">
                <p className="text-gray-400">בחר בקשה מהרשימה כדי לראות פרטים</p>
              </div>
            )}
          </div>
        </div>

        {/* Legal Notice */}
        <div className="mt-8 p-4 bg-amber-900 border border-amber-700 rounded-lg">
          <p className="text-sm text-amber-200">
            ⚖️ <strong>הודעה משפטית:</strong> כל השיחות ב-WhatsApp תועדו ומוגנות. הפרוטוקול המלא של כל שיחה כולל timestamps מדוייקים נשמר למטרות תיעוד משפטי וביקורת.
          </p>
        </div>
      </div>
    </div>
  );
};

export default PandiClientRequestPage;

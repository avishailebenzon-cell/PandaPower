/**
 * Carmit Orchestrator Dashboard
 * Comprehensive view of all matches, jobs, and decision workflows
 * Shows state transitions and routing decisions
 */

import React, { useState, useMemo, useCallback } from 'react';
import { useQuery } from '@tanstack/react-query';
import { updateMatchesStatus } from '../../api/matches';

interface Match {
  id: string;
  candidateName: string;
  candidateId: string;
  jobTitle: string;
  jobId: string;
  company: string;
  agentCode: string;
  matchScore: number;
  status: string;
  currentState: string;
  dateAdded: string;
  lastActivity?: string;
}

interface Job {
  id: string;
  title: string;
  company: string;
  department: string;
  assignedAgent?: string;
  assignedAgentName?: string;
  routingConfidence?: number;
  routingReasoning?: string;
  matchCount: number;
  dateAdded: string;
}

interface StateTransition {
  matchId: string;
  fromState: string;
  toState: string;
  timestamp: string;
  details?: string;
  gateResults?: Record<string, any>;
}

type TabType = 'all-matches' | 'all-jobs' | 'job-routing' | 'sent-to-tal' | 'sent-to-elad' | 'rejected';

const AGENT_NAMES: Record<string, string> = {
  naama: 'נעמה (תוכנה)',
  alik: 'אליק (אלקטרוניקה)',
  dganit: 'דגנית (בדיקות)',
  ofir: 'אופיר (מערכות)',
  itai: 'איתי (IT)',
  lior: 'ליאור (מכני)',
  gc: 'רון',
  mani: 'מני (התאמה)',
};

// Mock data - replace with API calls
const MOCK_MATCHES: Match[] = [
  {
    id: '1',
    candidateName: 'עמית לוי',
    candidateId: 'c1',
    jobTitle: 'Senior Full Stack Developer',
    jobId: 'j1',
    company: 'Acme Corp',
    agentCode: 'naama',
    matchScore: 0.85,
    status: 'carmit_approved',
    currentState: 'sent_to_tal',
    dateAdded: '2026-05-20',
    lastActivity: '2026-05-23T14:30:00Z',
  },
  {
    id: '2',
    candidateName: 'דן כהן',
    candidateId: 'c2',
    jobTitle: 'FPGA Engineer',
    jobId: 'j2',
    company: 'TechStart Ltd',
    agentCode: 'alik',
    matchScore: 0.78,
    status: 'found',
    currentState: 'found',
    dateAdded: '2026-05-23',
  },
  {
    id: '3',
    candidateName: 'מיכל אברהם',
    candidateId: 'c3',
    jobTitle: 'QA Automation Specialist',
    jobId: 'j3',
    company: 'QualityTech',
    agentCode: 'dganit',
    matchScore: 0.72,
    status: 'carmit_approved',
    currentState: 'sent_to_elad',
    dateAdded: '2026-05-21',
    lastActivity: '2026-05-23T10:15:00Z',
  },
  {
    id: '4',
    candidateName: 'אריאל בן זקן',
    candidateId: 'c4',
    jobTitle: 'DevOps Engineer',
    jobId: 'j4',
    company: 'CloudInfra',
    agentCode: 'ofir',
    matchScore: 0.65,
    status: 'carmit_rejected',
    currentState: 'carmit_rejected',
    dateAdded: '2026-05-22',
  },
];

const MOCK_JOBS: Job[] = [
  {
    id: 'j1',
    title: 'Senior Full Stack Developer',
    company: 'Acme Corp',
    department: 'Software',
    assignedAgent: 'naama',
    assignedAgentName: 'נעמה',
    routingConfidence: 0.92,
    routingReasoning: 'Perfect match for software team expertise',
    matchCount: 3,
    dateAdded: '2026-05-15',
  },
  {
    id: 'j2',
    title: 'FPGA Engineer',
    company: 'TechStart Ltd',
    department: 'Electronics',
    assignedAgent: 'alik',
    assignedAgentName: 'אליק',
    routingConfidence: 0.88,
    routingReasoning: 'Strong electronics specialization',
    matchCount: 2,
    dateAdded: '2026-05-16',
  },
];

const STATE_COLORS: Record<string, string> = {
  found: 'bg-yellow-900',
  carmit_approved: 'bg-green-900',
  carmit_rejected: 'bg-red-900',
  sent_to_tal: 'bg-blue-900',
  tal_conversation: 'bg-purple-900',
  tal_approved: 'bg-green-800',
  tal_rejected: 'bg-red-800',
  sent_to_elad: 'bg-indigo-900',
  hired: 'bg-emerald-900',
  placement_failed: 'bg-red-700',
};

const getStateEmoji = (state: string): string => {
  const stateEmojis: Record<string, string> = {
    found: '🔍',
    carmit_approved: '✅',
    carmit_rejected: '❌',
    sent_to_tal: '📞',
    tal_conversation: '💬',
    tal_approved: '👍',
    tal_rejected: '👎',
    sent_to_elad: '📧',
    hired: '🎉',
    placement_failed: '⛔',
  };
  return stateEmojis[state] || '📌';
};

const getStateLabel = (state: string): string => {
  const stateLabels: Record<string, string> = {
    found: 'נמצא על ידי סוכן',
    carmit_approved: 'אושר על ידי כרמית',
    carmit_rejected: 'נדחה על ידי כרמית',
    sent_to_tal: 'נשלח לטל',
    tal_conversation: 'בשיחה עם טל',
    tal_approved: 'אושר על ידי טל',
    tal_rejected: 'נדחה על ידי טל',
    sent_to_elad: 'נשלח לאלעד',
    hired: 'המועמד נשכר',
    placement_failed: 'ההצבה נכשלה',
  };
  return stateLabels[state] || state;
};

export const CarmitDashboard: React.FC = () => {
  const [activeTab, setActiveTab] = useState<TabType>('all-matches');
  const [expandedMatch, setExpandedMatch] = useState<string | null>(null);
  const [selectedMatches, setSelectedMatches] = useState<Set<string>>(new Set());
  const [isUpdating, setIsUpdating] = useState(false);
  const [updateMessage, setUpdateMessage] = useState<{ type: 'success' | 'error', text: string } | null>(null);

  // Filter matches based on active tab - moved up before use
  const filteredMatches = useMemo(() => {
    switch (activeTab) {
      case 'all-matches':
        return MOCK_MATCHES;
      case 'sent-to-tal':
        return MOCK_MATCHES.filter(m => m.currentState === 'sent_to_tal' || m.currentState === 'tal_conversation');
      case 'sent-to-elad':
        return MOCK_MATCHES.filter(m => m.currentState === 'sent_to_elad' || m.currentState === 'hired');
      case 'rejected':
        return MOCK_MATCHES.filter(m => m.currentState === 'carmit_rejected' || m.currentState === 'tal_rejected');
      default:
        return MOCK_MATCHES;
    }
  }, [activeTab]);

  const toggleMatchSelection = useCallback((matchId: string) => {
    setSelectedMatches(prev => {
      const newSet = new Set(prev);
      if (newSet.has(matchId)) {
        newSet.delete(matchId);
      } else {
        newSet.add(matchId);
      }
      return newSet;
    });
  }, []);

  const toggleAllMatches = useCallback(() => {
    if (selectedMatches.size === filteredMatches.length) {
      setSelectedMatches(new Set());
    } else {
      setSelectedMatches(new Set(filteredMatches.map(m => m.id)));
    }
  }, [filteredMatches, selectedMatches.size]);

  const handleBulkUpdate = useCallback(async (action: 'hired' | 'rejected') => {
    if (selectedMatches.size === 0) {
      setUpdateMessage({ type: 'error', text: 'בחר לפחות התאמה אחת' });
      return;
    }

    setIsUpdating(true);
    try {
      const result = await updateMatchesStatus(Array.from(selectedMatches), action);
      setUpdateMessage({
        type: 'success',
        text: `עודכנו ${result.updated_count} התאמות: ${action === 'hired' ? 'התקבלו לעבודה' : 'נדחו'}`,
      });
      setSelectedMatches(new Set());
      // Refresh data after 2 seconds
      setTimeout(() => {
        window.location.reload();
      }, 2000);
    } catch (error) {
      setUpdateMessage({
        type: 'error',
        text: `שגיאה בעדכון: ${error instanceof Error ? error.message : 'שגיאה לא ידועה'}`,
      });
    } finally {
      setIsUpdating(false);
    }
  }, [selectedMatches]);

  // Mock state transitions
  const stateTransitions: StateTransition[] = [
    {
      matchId: '1',
      fromState: 'found',
      toState: 'carmit_approved',
      timestamp: '2026-05-23T08:00:00Z',
      details: 'All 5 gates passed',
      gateResults: {
        pastRejection: { passed: true },
        alreadyDeclined: { passed: true },
        conflictOfInterest: { passed: true },
        clearanceMatch: { passed: true },
        qualityThreshold: { passed: true, score: 0.85 },
      },
    },
    {
      matchId: '1',
      fromState: 'carmit_approved',
      toState: 'sent_to_tal',
      timestamp: '2026-05-23T08:15:00Z',
      details: 'Sent to Tal for initial screening',
    },
  ];

  const renderMatchCard = (match: Match) => {
    const matchTransitions = stateTransitions.filter(t => t.matchId === match.id);
    const isExpanded = expandedMatch === match.id;
    const isSelected = selectedMatches.has(match.id);

    return (
      <div
        key={match.id}
        className={`border border-gray-700 rounded-lg p-4 mb-4 hover:border-gray-600 transition ${
          isSelected ? 'bg-blue-900 border-blue-500' : 'bg-gray-800'
        }`}
      >
        {/* Header */}
        <div className="flex items-start justify-between mb-3">
          <div className="flex items-start gap-3 flex-1">
            <input
              type="checkbox"
              checked={isSelected}
              onChange={() => toggleMatchSelection(match.id)}
              className="mt-1 w-5 h-5 cursor-pointer"
              title="בחר התאמה זו"
            />
            <div className="flex-1">
              <div className="flex items-center gap-2 mb-1">
                <h3 className="text-lg font-bold text-white">{match.candidateName}</h3>
                <span className={`px-2 py-1 rounded text-xs font-semibold text-white ${STATE_COLORS[match.currentState] || 'bg-gray-700'}`}>
                  {getStateEmoji(match.currentState)} {getStateLabel(match.currentState)}
                </span>
              </div>
              <p className="text-sm text-gray-300">{match.jobTitle} @ {match.company}</p>
              <p className="text-xs text-gray-400">סוכן: {AGENT_NAMES[match.agentCode] || match.agentCode}</p>
            </div>
          </div>
          <div className="text-right ml-4">
            <div className="text-2xl font-bold text-cyan-400">{Math.round(match.matchScore * 100)}%</div>
            <div className="text-xs text-gray-400">ניקוד התאמה</div>
          </div>
        </div>

        {/* Score Bar */}
        <div className="w-full bg-gray-700 rounded-full h-2 mb-3">
          <div
            className="bg-gradient-to-r from-cyan-500 to-blue-500 h-2 rounded-full"
            style={{ width: `${match.matchScore * 100}%` }}
          />
        </div>

        {/* Workflow Timeline */}
        {matchTransitions.length > 0 && (
          <div className="mb-3 p-3 bg-gray-900 rounded border border-gray-700">
            <p className="text-xs font-semibold text-gray-300 mb-2">📍 תהליך:</p>
            <div className="space-y-1">
              {matchTransitions.map((transition, idx) => (
                <div key={idx} className="text-xs text-gray-400">
                  <span className="text-cyan-400">{getStateEmoji(transition.fromState)}</span>
                  {' → '}
                  <span className="text-green-400">{getStateEmoji(transition.toState)}</span>
                  {' '}
                  <span className="text-gray-500">
                    {new Date(transition.timestamp).toLocaleString('he-IL')}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Expand Button */}
        <button
          onClick={() => setExpandedMatch(isExpanded ? null : match.id)}
          className="text-xs text-cyan-400 hover:text-cyan-300 font-semibold"
        >
          {isExpanded ? '▼ הסתר פרטים' : '▶ הצג פרטים מלאים'}
        </button>

        {/* Expanded Details */}
        {isExpanded && matchTransitions.length > 0 && (
          <div className="mt-3 pt-3 border-t border-gray-700 space-y-2">
            {matchTransitions.map((transition, idx) => (
              <div key={idx} className="text-xs bg-gray-900 p-2 rounded">
                <div className="font-semibold text-white mb-1">
                  {getStateLabel(transition.fromState)} → {getStateLabel(transition.toState)}
                </div>
                {transition.details && (
                  <div className="text-gray-300 mb-1">{transition.details}</div>
                )}
                {transition.gateResults && (
                  <div className="text-gray-400 space-y-1">
                    {Object.entries(transition.gateResults).map(([gate, result]: [string, any]) => (
                      <div key={gate}>
                        {result.passed ? '✅' : '❌'} {gate}: {result.score ? `${(result.score * 100).toFixed(0)}%` : 'passed'}
                      </div>
                    ))}
                  </div>
                )}
                <div className="text-gray-500 mt-1">
                  {new Date(transition.timestamp).toLocaleString('he-IL')}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    );
  };

  return (
    <div dir="rtl" className="min-h-screen bg-gray-900 p-8">
      <div className="max-w-7xl mx-auto">
        {/* Header */}
        <div className="mb-8">
          <h1 className="text-4xl font-bold text-white mb-2">🤖 כרמית - מנהל הסינון והתיעול</h1>
          <p className="text-gray-400">ניהול מלא של התאמות, משרות, ותיעול לסוכנים וגייסים</p>
        </div>

        {/* KPI Cards */}
        <div className="grid grid-cols-1 md:grid-cols-5 gap-4 mb-8">
          <div className="bg-blue-900 border-l-4 border-blue-400 rounded-lg p-4">
            <div className="text-sm text-blue-200">סה"כ התאמות</div>
            <div className="text-3xl font-bold text-white mt-2">{MOCK_MATCHES.length}</div>
          </div>
          <div className="bg-yellow-900 border-l-4 border-yellow-400 rounded-lg p-4">
            <div className="text-sm text-yellow-200">ממתינות לסינון</div>
            <div className="text-3xl font-bold text-white mt-2">
              {MOCK_MATCHES.filter(m => m.currentState === 'found').length}
            </div>
          </div>
          <div className="bg-green-900 border-l-4 border-green-400 rounded-lg p-4">
            <div className="text-sm text-green-200">אושרו</div>
            <div className="text-3xl font-bold text-white mt-2">
              {MOCK_MATCHES.filter(m => m.currentState === 'carmit_approved').length}
            </div>
          </div>
          <div className="bg-purple-900 border-l-4 border-purple-400 rounded-lg p-4">
            <div className="text-sm text-purple-200">שוגרו לטל</div>
            <div className="text-3xl font-bold text-white mt-2">
              {MOCK_MATCHES.filter(m => m.currentState.includes('tal')).length}
            </div>
          </div>
          <div className="bg-indigo-900 border-l-4 border-indigo-400 rounded-lg p-4">
            <div className="text-sm text-indigo-200">שוגרו לאלעד</div>
            <div className="text-3xl font-bold text-white mt-2">
              {MOCK_MATCHES.filter(m => m.currentState.includes('elad') || m.currentState === 'hired').length}
            </div>
          </div>
        </div>

        {/* Bulk Actions Bar */}
        {selectedMatches.size > 0 && (
          <div className="mb-6 p-4 bg-blue-900 border border-blue-700 rounded-lg">
            <div className="flex items-center justify-between flex-wrap gap-4">
              <div className="text-sm text-blue-200">
                ✓ נבחרו {selectedMatches.size} התאמות
              </div>
              <div className="flex gap-2 flex-wrap">
                <button
                  onClick={() => handleBulkUpdate('hired')}
                  disabled={isUpdating}
                  className="px-4 py-2 bg-green-600 hover:bg-green-700 disabled:bg-gray-600 text-white rounded font-semibold transition"
                >
                  {isUpdating ? 'מעדכן...' : '✓ התקבלו לעבודה'}
                </button>
                <button
                  onClick={() => handleBulkUpdate('rejected')}
                  disabled={isUpdating}
                  className="px-4 py-2 bg-red-600 hover:bg-red-700 disabled:bg-gray-600 text-white rounded font-semibold transition"
                >
                  {isUpdating ? 'מעדכן...' : '✗ נדחו'}
                </button>
                <button
                  onClick={() => setSelectedMatches(new Set())}
                  disabled={isUpdating}
                  className="px-4 py-2 bg-gray-600 hover:bg-gray-700 disabled:bg-gray-600 text-white rounded font-semibold transition"
                >
                  בטל
                </button>
              </div>
            </div>
            {updateMessage && (
              <div className={`mt-3 p-2 rounded text-sm ${
                updateMessage.type === 'success'
                  ? 'bg-green-900 text-green-200'
                  : 'bg-red-900 text-red-200'
              }`}>
                {updateMessage.text}
              </div>
            )}
          </div>
        )}

        {/* Tab Navigation with Select All */}
        <div className="mb-6 border-b border-gray-700 flex gap-2 flex-wrap items-center">
          {/* Select All Checkbox */}
          {(activeTab === 'all-matches' || activeTab === 'sent-to-tal' || activeTab === 'sent-to-elad' || activeTab === 'rejected') && filteredMatches.length > 0 && (
            <label className="flex items-center gap-2 px-4 py-3 text-sm text-gray-300 hover:text-white cursor-pointer border-b-2 border-transparent hover:border-gray-500">
              <input
                type="checkbox"
                checked={selectedMatches.size > 0 && selectedMatches.size === filteredMatches.length}
                onChange={toggleAllMatches}
                className="w-4 h-4"
                title="בחר את כל ההתאמות בלשונית זו"
              />
              <span>בחר הכל</span>
            </label>
          )}

          {/* Tabs */}
          {[
            { id: 'all-matches', label: '📊 כל ההתאמות' },
            { id: 'all-jobs', label: '💼 כל המשרות' },
            { id: 'job-routing', label: '🎯 תיעול משרות' },
            { id: 'sent-to-tal', label: '📞 שוגר לטל' },
            { id: 'sent-to-elad', label: '📧 שוגר לאלעד' },
            { id: 'rejected', label: '❌ נדחו' },
          ].map((tab) => (
            <button
              key={tab.id}
              onClick={() => {
                setActiveTab(tab.id as TabType);
                setSelectedMatches(new Set()); // Clear selection when switching tabs
              }}
              className={`pb-3 px-4 font-semibold transition whitespace-nowrap ${
                activeTab === tab.id
                  ? 'text-cyan-400 border-b-2 border-cyan-400'
                  : 'text-gray-400 hover:text-white'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>

        {/* Content Area */}
        <div>
          {/* All Matches */}
          {activeTab === 'all-matches' && (
            <div>
              <h2 className="text-xl font-bold text-white mb-4">כל ההתאמות שהתקבלו מהסוכנים</h2>
              {filteredMatches.length > 0 ? (
                filteredMatches.map(match => renderMatchCard(match))
              ) : (
                <div className="text-center py-8 text-gray-400">אין התאמות</div>
              )}
            </div>
          )}

          {/* All Jobs */}
          {activeTab === 'all-jobs' && (
            <div>
              <h2 className="text-xl font-bold text-white mb-4">כל המשרות שהתקבלו</h2>
              <div className="space-y-4">
                {MOCK_JOBS.map(job => (
                  <div key={job.id} className="bg-gray-800 border border-gray-700 rounded-lg p-4">
                    <div className="flex items-start justify-between mb-2">
                      <div>
                        <h3 className="text-lg font-bold text-white">{job.title}</h3>
                        <p className="text-sm text-gray-300">{job.company} • {job.department}</p>
                      </div>
                      <div className="text-right">
                        <div className="text-2xl font-bold text-green-400">{job.matchCount}</div>
                        <div className="text-xs text-gray-400">התאמות</div>
                      </div>
                    </div>
                    <div className="p-2 bg-gray-900 rounded text-sm text-gray-300">
                      📋 {job.dateAdded}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Job Routing */}
          {activeTab === 'job-routing' && (
            <div>
              <h2 className="text-xl font-bold text-white mb-4">חלוקת המשרות לסוכנים</h2>
              <div className="space-y-4">
                {MOCK_JOBS.filter(j => j.assignedAgent).map(job => (
                  <div key={job.id} className="bg-gray-800 border border-cyan-700 rounded-lg p-4">
                    <div className="flex items-start justify-between mb-3">
                      <div>
                        <h3 className="text-lg font-bold text-white">{job.title}</h3>
                        <p className="text-sm text-gray-300">{job.company}</p>
                      </div>
                      <div className="text-right">
                        <div className="text-2xl font-bold text-cyan-400">{Math.round((job.routingConfidence || 0) * 100)}%</div>
                        <div className="text-xs text-gray-400">ביטחון</div>
                      </div>
                    </div>
                    <div className="p-3 bg-blue-900 rounded mb-2">
                      <div className="font-semibold text-blue-200 mb-1">➜ שוגר לסוכן:</div>
                      <div className="text-lg font-bold text-white">{job.assignedAgentName}</div>
                    </div>
                    {job.routingReasoning && (
                      <div className="p-2 bg-gray-900 rounded text-sm text-gray-300">
                        💭 {job.routingReasoning}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Sent to Tal */}
          {activeTab === 'sent-to-tal' && (
            <div>
              <h2 className="text-xl font-bold text-white mb-4">התאמות שנשלחו לטל</h2>
              {filteredMatches.length > 0 ? (
                filteredMatches.map(match => renderMatchCard(match))
              ) : (
                <div className="text-center py-8 text-gray-400">אין התאמות</div>
              )}
            </div>
          )}

          {/* Sent to Elad */}
          {activeTab === 'sent-to-elad' && (
            <div>
              <h2 className="text-xl font-bold text-white mb-4">התאמות שנשלחו לאלעד</h2>
              {filteredMatches.length > 0 ? (
                filteredMatches.map(match => renderMatchCard(match))
              ) : (
                <div className="text-center py-8 text-gray-400">אין התאמות</div>
              )}
            </div>
          )}

          {/* Rejected */}
          {activeTab === 'rejected' && (
            <div>
              <h2 className="text-xl font-bold text-white mb-4">התאמות שנדחו</h2>
              {filteredMatches.length > 0 ? (
                filteredMatches.map(match => renderMatchCard(match))
              ) : (
                <div className="text-center py-8 text-gray-400">אין התאמות</div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default CarmitDashboard;

/**
 * Elad Recruiter Dashboard
 * Final placement stage - converting approved matches to hired
 */

import React, { useState, useEffect } from 'react';
import { useQuery, useMutation } from '@tanstack/react-query';
import {
  fetchDepartmentMatches,
  updateMatchStatus,
  DepartmentMatch,
} from '@/api/recruitment-departments';

type FilterStatus = 'all' | 'sent_to_elad' | 'elad_conversation' | 'hired' | 'placement_failed';

interface EladStats {
  totalMatches: number;
  inConversation: number;
  hired: number;
  failed: number;
  successRate: number;
}

export const EladPage: React.FC = () => {
  const [filterStatus, setFilterStatus] = useState<FilterStatus>('all');
  const [sortBy, setSortBy] = useState<'newest' | 'oldest' | 'score_high' | 'score_low'>('newest');
  const [selectedMatches, setSelectedMatches] = useState<Set<string>>(new Set());
  const [showConversationModal, setShowConversationModal] = useState(false);
  const [showPlacementModal, setShowPlacementModal] = useState(false);
  const [selectedMatch, setSelectedMatch] = useState<DepartmentMatch | null>(null);
  const [conversationNotes, setConversationNotes] = useState('');
  const [placementOutcome, setPlacementOutcome] = useState<'hired' | 'placement_failed' | null>(null);
  const [placementNotes, setPlacementNotes] = useState('');

  // Fetch matches for Elad
  const { data: matchesData = [], isLoading } = useQuery({
    queryKey: ['elad-matches', filterStatus],
    queryFn: () => {
      // Simulate fetching matches at sent_to_elad or later stage
      return fetchDepartmentMatches('elad', filterStatus === 'all' ? undefined : filterStatus, 100, 0);
    },
    refetchInterval: 30000,
    retry: 2,
  });

  // Calculate stats
  const stats: EladStats = {
    totalMatches: matchesData.length,
    inConversation: matchesData.filter((m) => m.status === 'elad_conversation').length,
    hired: matchesData.filter((m) => m.status === 'hired').length,
    failed: matchesData.filter((m) => m.status === 'placement_failed').length,
    successRate: matchesData.length > 0
      ? Math.round((matchesData.filter((m) => m.status === 'hired').length / matchesData.length) * 100)
      : 0,
  };

  // Record conversation
  const recordConversationMutation = useMutation({
    mutationFn: async (matchId: string) => {
      return updateMatchStatus('elad', matchId, 'elad_conversation', conversationNotes);
    },
    onSuccess: () => {
      setShowConversationModal(false);
      setConversationNotes('');
    },
  });

  // Record placement outcome
  const recordPlacementMutation = useMutation({
    mutationFn: async (matchId: string) => {
      if (!placementOutcome) return;
      return updateMatchStatus('elad', matchId, placementOutcome, placementNotes);
    },
    onSuccess: () => {
      setShowPlacementModal(false);
      setPlacementNotes('');
      setPlacementOutcome(null);
    },
  });

  const handleSelectMatch = (matchId: string) => {
    const newSelected = new Set(selectedMatches);
    if (newSelected.has(matchId)) {
      newSelected.delete(matchId);
    } else {
      newSelected.add(matchId);
    }
    setSelectedMatches(newSelected);
  };

  const handleSelectAll = () => {
    if (selectedMatches.size === matchesData.length) {
      setSelectedMatches(new Set());
    } else {
      setSelectedMatches(new Set(matchesData.map((m) => m.id)));
    }
  };

  const handleRecordConversation = (match: DepartmentMatch) => {
    setSelectedMatch(match);
    setShowConversationModal(true);
  };

  const handleRecordPlacement = (match: DepartmentMatch) => {
    setSelectedMatch(match);
    setShowPlacementModal(true);
  };

  // Sort matches
  const sortedMatches = [...matchesData].sort((a, b) => {
    if (sortBy === 'newest') return new Date(b.dateAdded).getTime() - new Date(a.dateAdded).getTime();
    if (sortBy === 'oldest') return new Date(a.dateAdded).getTime() - new Date(b.dateAdded).getTime();
    if (sortBy === 'score_high') return (b.matchScore || 0) - (a.matchScore || 0);
    if (sortBy === 'score_low') return (a.matchScore || 0) - (b.matchScore || 0);
    return 0;
  });

  return (
    <div dir="rtl" className="min-h-screen bg-gray-900 p-8">
      <div className="max-w-7xl mx-auto">
        {/* Header */}
        <div className="mb-8">
          <h1 className="text-4xl font-bold text-white mb-2">אלעד - שלב הצבה סופי</h1>
          <p className="text-gray-400">ניהול התאמות וקביעת תוצאות הצבה</p>
        </div>

        {/* KPI Cards */}
        <div className="grid grid-cols-1 md:grid-cols-5 gap-4 mb-8">
          <div className="bg-blue-900 border border-blue-600 rounded-lg p-4 text-center">
            <p className="text-gray-300 text-sm mb-2">סך ההתאמות</p>
            <p className="text-3xl font-bold text-blue-200">{stats.totalMatches}</p>
          </div>
          <div className="bg-cyan-900 border border-cyan-600 rounded-lg p-4 text-center">
            <p className="text-gray-300 text-sm mb-2">בשיחה</p>
            <p className="text-3xl font-bold text-cyan-200">{stats.inConversation}</p>
          </div>
          <div className="bg-green-900 border border-green-600 rounded-lg p-4 text-center">
            <p className="text-gray-300 text-sm mb-2">הצבות בהצלחה</p>
            <p className="text-3xl font-bold text-green-200">{stats.hired}</p>
          </div>
          <div className="bg-red-900 border border-red-600 rounded-lg p-4 text-center">
            <p className="text-gray-300 text-sm mb-2">הצבות שנכשלו</p>
            <p className="text-3xl font-bold text-red-200">{stats.failed}</p>
          </div>
          <div className="bg-purple-900 border border-purple-600 rounded-lg p-4 text-center">
            <p className="text-gray-300 text-sm mb-2">שיעור הצלחה</p>
            <p className="text-3xl font-bold text-purple-200">{stats.successRate}%</p>
          </div>
        </div>

        {/* Filters and Sort */}
        <div className="bg-gray-800 rounded-lg p-4 mb-6 border border-gray-700 space-y-4">
          <div className="flex gap-4 flex-col md:flex-row items-start md:items-center">
            {/* Status Filter */}
            <div className="flex gap-2 flex-wrap">
              {[
                { value: 'all', label: 'הכל' },
                { value: 'sent_to_elad', label: 'בהמתנה' },
                { value: 'elad_conversation', label: 'בשיחה' },
                { value: 'hired', label: 'הוצבו' },
                { value: 'placement_failed', label: 'נכשלו' },
              ].map((option) => (
                <button
                  key={option.value}
                  onClick={() => setFilterStatus(option.value as FilterStatus)}
                  className={`px-3 py-1 rounded text-sm font-semibold transition ${
                    filterStatus === option.value
                      ? 'bg-blue-600 text-white'
                      : 'bg-gray-700 text-gray-300 hover:bg-gray-600'
                  }`}
                >
                  {option.label}
                </button>
              ))}
            </div>

            {/* Sort */}
            <select
              value={sortBy}
              onChange={(e) => setSortBy(e.target.value as any)}
              className="bg-gray-700 border border-gray-600 rounded px-4 py-2 text-white focus:outline-none focus:border-blue-500 ml-auto"
            >
              <option value="newest">הכי חדש</option>
              <option value="oldest">הכי ישן</option>
              <option value="score_high">ציון גבוה</option>
              <option value="score_low">ציון נמוך</option>
            </select>
          </div>
        </div>

        {/* Matches Table */}
        <div className="bg-gray-800 rounded-lg border border-gray-700 overflow-hidden">
          {isLoading ? (
            <div className="p-8">
              <div className="space-y-3">
                {[...Array(5)].map((_, i) => (
                  <div key={i} className="flex gap-4 animate-pulse">
                    <div className="h-4 bg-gray-700 rounded flex-1"></div>
                    <div className="h-4 bg-gray-700 rounded w-24"></div>
                  </div>
                ))}
              </div>
            </div>
          ) : sortedMatches.length > 0 ? (
            <div className="overflow-x-auto">
              <table className="w-full text-right">
                <thead className="bg-gray-700 border-b border-gray-600">
                  <tr>
                    <th className="px-4 py-3 text-right">
                      <input
                        type="checkbox"
                        checked={selectedMatches.size === sortedMatches.length && sortedMatches.length > 0}
                        onChange={handleSelectAll}
                        className="cursor-pointer"
                      />
                    </th>
                    <th className="px-4 py-3 text-right font-semibold text-gray-200">מועמד</th>
                    <th className="px-4 py-3 text-right font-semibold text-gray-200">משרה</th>
                    <th className="px-4 py-3 text-right font-semibold text-gray-200">חברה</th>
                    <th className="px-4 py-3 text-right font-semibold text-gray-200">ציון התאמה</th>
                    <th className="px-4 py-3 text-right font-semibold text-gray-200">סטטוס</th>
                    <th className="px-4 py-3 text-right font-semibold text-gray-200">פעולות</th>
                  </tr>
                </thead>
                <tbody>
                  {sortedMatches.map((match) => (
                    <tr key={match.id} className="border-b border-gray-700 hover:bg-gray-750 transition">
                      <td className="px-4 py-3">
                        <input
                          type="checkbox"
                          checked={selectedMatches.has(match.id)}
                          onChange={() => handleSelectMatch(match.id)}
                          className="cursor-pointer"
                        />
                      </td>
                      <td className="px-4 py-3 text-white font-semibold">{match.candidateName}</td>
                      <td className="px-4 py-3 text-gray-300">{match.jobTitle}</td>
                      <td className="px-4 py-3 text-gray-400">{match.company}</td>
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-2">
                          <div className="w-16 bg-gray-700 rounded-full h-2">
                            <div
                              className={`h-2 rounded-full ${
                                match.matchScore >= 0.8
                                  ? 'bg-green-500'
                                  : match.matchScore >= 0.7
                                  ? 'bg-yellow-500'
                                  : 'bg-orange-500'
                              }`}
                              style={{ width: `${match.matchScore * 100}%` }}
                            ></div>
                          </div>
                          <span className="text-sm text-gray-300">{Math.round(match.matchScore * 100)}%</span>
                        </div>
                      </td>
                      <td className="px-4 py-3">
                        <span
                          className={`px-2 py-1 rounded text-xs font-semibold ${
                            match.status === 'hired'
                              ? 'bg-green-900 text-green-200'
                              : match.status === 'placement_failed'
                              ? 'bg-red-900 text-red-200'
                              : match.status === 'elad_conversation'
                              ? 'bg-cyan-900 text-cyan-200'
                              : 'bg-blue-900 text-blue-200'
                          }`}
                        >
                          {match.status === 'sent_to_elad' && 'בהמתנה'}
                          {match.status === 'elad_conversation' && 'בשיחה'}
                          {match.status === 'hired' && 'הוצב!'}
                          {match.status === 'placement_failed' && 'נכשל'}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-left">
                        {match.status === 'sent_to_elad' && (
                          <button
                            onClick={() => handleRecordConversation(match)}
                            className="px-3 py-1 bg-cyan-600 hover:bg-cyan-700 text-white text-sm font-semibold rounded transition"
                          >
                            שיחה
                          </button>
                        )}
                        {match.status === 'elad_conversation' && (
                          <button
                            onClick={() => handleRecordPlacement(match)}
                            className="px-3 py-1 bg-green-600 hover:bg-green-700 text-white text-sm font-semibold rounded transition"
                          >
                            הוצבה
                          </button>
                        )}
                        {(match.status === 'hired' || match.status === 'placement_failed') && (
                          <span className="text-gray-400 text-sm">סגור</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="p-8 text-center text-gray-400">
              <p>אין התאמות לטיפול כרגע</p>
            </div>
          )}
        </div>
      </div>

      {/* Conversation Modal */}
      {showConversationModal && selectedMatch && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-gray-800 border border-gray-700 rounded-lg p-6 max-w-sm mx-4">
            <h3 className="text-lg font-semibold text-white text-right mb-4">רישום שיחה</h3>
            <p className="text-gray-300 text-right mb-4">
              עבור <strong>{selectedMatch.candidateName}</strong> - {selectedMatch.jobTitle}
            </p>
            <textarea
              value={conversationNotes}
              onChange={(e) => setConversationNotes(e.target.value)}
              placeholder="סדר העבודה, דרישות נוספות, הערות..."
              className="w-full bg-gray-700 border border-gray-600 rounded p-3 text-white text-right placeholder-gray-500 mb-4"
              rows={4}
            />
            <div className="flex gap-3 justify-start">
              <button
                onClick={() => recordConversationMutation.mutate(selectedMatch.id)}
                disabled={recordConversationMutation.isPending}
                className="flex-1 bg-cyan-600 hover:bg-cyan-700 disabled:opacity-50 text-white font-semibold py-2 px-4 rounded transition"
              >
                שמור שיחה
              </button>
              <button
                onClick={() => setShowConversationModal(false)}
                className="flex-1 bg-gray-700 hover:bg-gray-600 text-white font-semibold py-2 px-4 rounded transition"
              >
                ביטול
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Placement Outcome Modal */}
      {showPlacementModal && selectedMatch && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-gray-800 border border-gray-700 rounded-lg p-6 max-w-sm mx-4">
            <h3 className="text-lg font-semibold text-white text-right mb-4">תוצאת הצבה</h3>
            <p className="text-gray-300 text-right mb-6">
              עבור <strong>{selectedMatch.candidateName}</strong>
            </p>

            <div className="space-y-3 mb-6">
              <label className="flex items-center gap-3 cursor-pointer text-right">
                <input
                  type="radio"
                  name="outcome"
                  value="hired"
                  checked={placementOutcome === 'hired'}
                  onChange={(e) => setPlacementOutcome(e.target.value as any)}
                  className="cursor-pointer"
                />
                <span className="text-white">הוצבה בהצלחה ✓</span>
              </label>
              <label className="flex items-center gap-3 cursor-pointer text-right">
                <input
                  type="radio"
                  name="outcome"
                  value="placement_failed"
                  checked={placementOutcome === 'placement_failed'}
                  onChange={(e) => setPlacementOutcome(e.target.value as any)}
                  className="cursor-pointer"
                />
                <span className="text-white">הצבה נכשלה ✗</span>
              </label>
            </div>

            <textarea
              value={placementNotes}
              onChange={(e) => setPlacementNotes(e.target.value)}
              placeholder="סיבות, הערות..."
              className="w-full bg-gray-700 border border-gray-600 rounded p-3 text-white text-right placeholder-gray-500 mb-4"
              rows={3}
            />

            <div className="flex gap-3 justify-start">
              <button
                onClick={() => recordPlacementMutation.mutate(selectedMatch.id)}
                disabled={!placementOutcome || recordPlacementMutation.isPending}
                className="flex-1 bg-green-600 hover:bg-green-700 disabled:opacity-50 text-white font-semibold py-2 px-4 rounded transition"
              >
                שמור תוצאה
              </button>
              <button
                onClick={() => setShowPlacementModal(false)}
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

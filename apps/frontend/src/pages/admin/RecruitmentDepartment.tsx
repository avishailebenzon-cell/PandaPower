/**
 * Recruitment Department Dashboard
 * Each agent (naama, alik, etc.) manages their own matches
 * Now with job filtering, grouping, and job display
 * Enhanced with agent profile and real-time CV monitoring
 */

import React, { useState, useMemo, useEffect } from 'react';
import { useQuery, useMutation } from '@tanstack/react-query';
import {
  fetchDepartmentMatches,
  fetchAssignedJobs,
  updateMatchStatus,
  getDepartmentStats,
  DepartmentMatch,
  AssignedJob,
} from '@/api/recruitment-departments';
import { useParams } from 'react-router-dom';
import { getAgent } from '@/data/agents';

type TabType = 'active' | 'history';
type GroupBy = 'none' | 'job' | 'status' | 'score';

interface DepartmentJob {
  jobId: string;
  jobTitle: string;
  company: string;
  matchCount: number;
  approvedCount: number;
}

export const RecruitmentDepartment: React.FC = () => {
  const { departmentCode } = useParams<{ departmentCode: string }>();
  const [activeTab, setActiveTab] = useState<TabType>('active');
  const [filterStatus, setFilterStatus] = useState<string>('all');
  const [filterJob, setFilterJob] = useState<string>('all');
  const [groupBy, setGroupBy] = useState<GroupBy>('none');
  const [sortBy, setSortBy] = useState<'newest' | 'oldest' | 'score_high' | 'score_low'>('newest');
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedMatches, setSelectedMatches] = useState<Set<string>>(new Set());
  const [showApproveModal, setShowApproveModal] = useState(false);
  const [showRejectModal, setShowRejectModal] = useState(false);
  const [selectedMatch, setSelectedMatch] = useState<DepartmentMatch | null>(null);
  const [rejectionReason, setRejectionReason] = useState('');
  const [newCVsCount, setNewCVsCount] = useState(0);
  const [lastCVCheck, setLastCVCheck] = useState<Date | null>(null);

  // Get agent details
  const agent = getAgent(departmentCode || '');

  // Fetch assigned jobs - what jobs does this agent have to work on?
  const { data: assignedJobsData = [] } = useQuery({
    queryKey: ['assigned-jobs', departmentCode],
    queryFn: () => fetchAssignedJobs(departmentCode || ''),
    refetchInterval: 10000, // Check every 10 seconds
    retry: 2,
  });

  // Fetch matches - with aggressive polling for new CVs
  const { data: matchesData = [], isLoading, refetch: refetchMatches } = useQuery({
    queryKey: ['department-matches', departmentCode, activeTab],
    queryFn: () =>
      fetchDepartmentMatches(
        departmentCode || '',
        activeTab === 'active' ? 'found' : undefined,
        100,
        0
      ),
    refetchInterval: 10000, // Check every 10 seconds for new CVs
    retry: 2,
  });

  // Track new CVs detected
  useEffect(() => {
    const newMatches = matchesData.filter(m => m.status === 'found');
    if (newMatches.length > newCVsCount) {
      setNewCVsCount(newMatches.length);
      setLastCVCheck(new Date());
    }
  }, [matchesData, newCVsCount]);

  // Get current active match (first match in "found" status)
  const currentActiveMatch = useMemo(() => {
    const foundMatches = matchesData.filter(m => m.status === 'found');
    return foundMatches.length > 0 ? foundMatches[0] : null;
  }, [matchesData]);

  // Extract unique jobs from matches
  const jobsList: DepartmentJob[] = useMemo(() => {
    const jobsMap = new Map<string, DepartmentJob>();

    matchesData.forEach((match) => {
      const key = `${match.jobId}-${match.jobTitle}`;
      if (!jobsMap.has(key)) {
        jobsMap.set(key, {
          jobId: match.jobId,
          jobTitle: match.jobTitle,
          company: match.company,
          matchCount: 0,
          approvedCount: 0,
        });
      }
      const job = jobsMap.get(key)!;
      job.matchCount++;
      if (match.status === 'approved') {
        job.approvedCount++;
      }
    });

    return Array.from(jobsMap.values()).sort((a, b) => b.matchCount - a.matchCount);
  }, [matchesData]);

  // Filter matches
  const filteredMatches = useMemo(() => {
    return matchesData.filter((match) => {
      const statusMatch = filterStatus === 'all' || match.status === filterStatus;
      const jobMatch = filterJob === 'all' || match.jobId === filterJob;
      const searchMatch =
        match.candidateName.toLowerCase().includes(searchQuery.toLowerCase()) ||
        match.jobTitle.toLowerCase().includes(searchQuery.toLowerCase()) ||
        match.company.toLowerCase().includes(searchQuery.toLowerCase());

      return statusMatch && jobMatch && searchMatch;
    });
  }, [matchesData, filterStatus, filterJob, searchQuery]);

  // Sort matches
  const sortedMatches = useMemo(() => {
    const sorted = [...filteredMatches];
    if (sortBy === 'newest') {
      sorted.sort((a, b) => new Date(b.dateAdded).getTime() - new Date(a.dateAdded).getTime());
    } else if (sortBy === 'oldest') {
      sorted.sort((a, b) => new Date(a.dateAdded).getTime() - new Date(b.dateAdded).getTime());
    } else if (sortBy === 'score_high') {
      sorted.sort((a, b) => (b.matchScore || 0) - (a.matchScore || 0));
    } else if (sortBy === 'score_low') {
      sorted.sort((a, b) => (a.matchScore || 0) - (b.matchScore || 0));
    }
    return sorted;
  }, [filteredMatches, sortBy]);

  // Group matches
  const groupedMatches = useMemo(() => {
    if (groupBy === 'none') {
      return [{ label: '', matches: sortedMatches }];
    }

    const groups = new Map<string, DepartmentMatch[]>();

    sortedMatches.forEach((match) => {
      let groupKey = '';
      if (groupBy === 'job') {
        groupKey = match.jobTitle;
      } else if (groupBy === 'status') {
        groupKey = match.status;
      } else if (groupBy === 'score') {
        if (match.matchScore >= 0.8) groupKey = 'ציון גבוה (80%+)';
        else if (match.matchScore >= 0.7) groupKey = 'ציון בינוני (70-80%)';
        else groupKey = 'ציון נמוך (<70%)';
      }

      if (!groups.has(groupKey)) {
        groups.set(groupKey, []);
      }
      groups.get(groupKey)!.push(match);
    });

    return Array.from(groups.entries()).map(([label, matches]) => ({ label, matches }));
  }, [sortedMatches, groupBy]);

  // Mutations
  const approveMutation = useMutation({
    mutationFn: (matchId: string) => updateMatchStatus(departmentCode || '', matchId, 'approved', ''),
    onSuccess: () => {
      setShowApproveModal(false);
      setSelectedMatch(null);
    },
  });

  const rejectMutation = useMutation({
    mutationFn: (matchId: string) =>
      updateMatchStatus(departmentCode || '', matchId, 'rejected', rejectionReason),
    onSuccess: () => {
      setShowRejectModal(false);
      setSelectedMatch(null);
      setRejectionReason('');
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
    if (selectedMatches.size === sortedMatches.length) {
      setSelectedMatches(new Set());
    } else {
      setSelectedMatches(new Set(sortedMatches.map((m) => m.id)));
    }
  };

  return (
    <div dir="rtl" className="min-h-screen bg-gray-900 p-8">
      <div className="max-w-7xl mx-auto">
        {/* Enhanced Agent Profile Card */}
        {agent && (
          <div className={`mb-8 bg-gradient-to-r ${agent.color} rounded-xl p-8 text-white shadow-2xl border-l-8 border-white`}>
            <div className="flex items-start gap-6 flex-col md:flex-row-reverse">
              {/* Agent Avatar - Large */}
              <div className="flex-shrink-0">
                <img
                  src={agent.avatar}
                  alt={agent.name}
                  className="w-32 h-32 rounded-full border-4 border-white shadow-lg"
                />
              </div>

              {/* Agent Info */}
              <div className="flex-1">
                <div className="mb-4">
                  <h1 className="text-5xl font-bold mb-2">{agent.emoji} {agent.name}</h1>
                  <p className="text-xl text-gray-100 mb-2">{agent.title}</p>
                  <p className="text-base text-gray-200">{agent.description}</p>
                </div>

                {/* Specializations */}
                <div className="mb-4">
                  <p className="text-sm text-gray-100 mb-2">📚 התמחויות:</p>
                  <div className="flex flex-wrap gap-2">
                    {agent.specialization.map((spec) => (
                      <span
                        key={spec}
                        className="px-3 py-1 rounded-full bg-white bg-opacity-20 text-sm font-semibold"
                      >
                        {spec}
                      </span>
                    ))}
                  </div>
                </div>

                {/* Experience & Contact */}
                <div className="flex gap-6 text-sm">
                  <span>⏱️ {agent.experience}</span>
                  {agent.email && <span>📧 {agent.email}</span>}
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Current Active Match */}
        {currentActiveMatch && (
          <div className="mb-8 bg-gradient-to-r from-amber-900 to-orange-900 rounded-xl p-6 text-white shadow-lg border-l-4 border-amber-400">
            <div className="flex items-center gap-4 flex-col md:flex-row-reverse">
              <div className="flex-1">
                <div className="text-sm text-amber-200 font-semibold mb-2">⚡ בעבודה כרגע</div>
                <div className="mb-3">
                  <p className="text-xs text-gray-200 mb-1">משרה:</p>
                  <p className="text-lg font-bold text-white">{currentActiveMatch.jobTitle}</p>
                  <p className="text-sm text-amber-100">{currentActiveMatch.company}</p>
                </div>
                <div>
                  <p className="text-xs text-gray-200 mb-1">מועמד בבדיקה:</p>
                  <p className="text-lg font-bold text-cyan-300">{currentActiveMatch.candidateName}</p>
                  <p className="text-xs text-gray-300 mt-1">ניקוד התאמה: <span className="font-semibold text-amber-300">{Math.round(currentActiveMatch.matchScore * 100)}%</span></p>
                </div>
              </div>
              <div className="bg-white bg-opacity-10 rounded-lg p-4 text-center">
                <div className="text-3xl font-bold text-amber-300">{Math.round(currentActiveMatch.matchScore * 100)}</div>
                <div className="text-xs text-amber-100 mt-1">ניקוד התאמה</div>
              </div>
            </div>
          </div>
        )}

        {/* Quick Stats */}
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-8">
          <div className="bg-blue-900 border-l-4 border-blue-400 rounded-lg p-4">
            <div className="text-sm text-blue-200">התאמות בתהליך</div>
            <div className="text-3xl font-bold text-white mt-2">
              {matchesData.filter(m => m.status === 'found').length}
            </div>
            <div className="text-xs text-blue-300 mt-1">חדשות וממתינות</div>
          </div>

          <div className="bg-green-900 border-l-4 border-green-400 rounded-lg p-4">
            <div className="text-sm text-green-200">אושרו</div>
            <div className="text-3xl font-bold text-white mt-2">
              {matchesData.filter(m => m.status === 'approved').length}
            </div>
            <div className="text-xs text-green-300 mt-1">התאמות מאושרות</div>
          </div>

          <div className="bg-red-900 border-l-4 border-red-400 rounded-lg p-4">
            <div className="text-sm text-red-200">דחויות</div>
            <div className="text-3xl font-bold text-white mt-2">
              {matchesData.filter(m => m.status === 'rejected').length}
            </div>
            <div className="text-xs text-red-300 mt-1">לא התאימו</div>
          </div>

          <div className="bg-yellow-900 border-l-4 border-yellow-400 rounded-lg p-4">
            <div className="text-sm text-yellow-200">שיעור הצלחה</div>
            <div className="text-3xl font-bold text-white mt-2">
              {matchesData.length > 0
                ? Math.round(
                    (matchesData.filter(m => m.status === 'approved').length / matchesData.length) *
                      100
                  )
                : 0}
              %
            </div>
            <div className="text-xs text-yellow-300 mt-1">מתוך הכל</div>
          </div>
        </div>

        {/* CV Monitoring Alert */}
        {lastCVCheck && (
          <div className="bg-indigo-900 border-l-4 border-indigo-400 rounded-lg p-4 mb-8 flex items-center justify-between">
            <div>
              <p className="text-indigo-200 font-semibold">🔍 מניטור CVs בזמן אמת</p>
              <p className="text-sm text-indigo-300 mt-1">
                בדיקה אחרונה: {lastCVCheck.toLocaleTimeString('he-IL')} • המערכת בדקה את בסיס הנתונים כל 10 שניות
              </p>
            </div>
            {newCVsCount > 0 && (
              <div className="text-right">
                <div className="text-2xl font-bold text-white animate-bounce">🆕 {newCVsCount}</div>
                <div className="text-xs text-indigo-300">CVs חדשים</div>
              </div>
            )}
          </div>
        )}

        {/* Header */}
        <div className="mb-8">
          <h2 className="text-3xl font-bold text-white mb-2">התאמות מועמדים למשרות</h2>
          <p className="text-gray-400">ניהול התאמות וקבלת החלטות על מועמדים</p>
        </div>

        {/* Assigned Jobs Overview */}
        <div className="mb-8 bg-gray-800 rounded-lg p-6 border border-gray-700">
          <h2 className="text-xl font-bold text-white mb-4">משרות שהוקצו לך ({assignedJobsData.length})</h2>
          {assignedJobsData.length === 0 ? (
            <div className="text-center py-8 text-gray-400">
              <p>🎯 אין עדיין משרות שהוקצו אליך מכרמית</p>
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {assignedJobsData.map((job) => (
                <div
                  key={job.id}
                  className={`rounded-lg p-4 border-l-4 cursor-pointer transition ${
                    filterJob === job.id
                      ? 'bg-blue-900 border-blue-400 shadow-lg'
                      : 'bg-gray-700 border-blue-500 hover:bg-gray-650'
                  }`}
                  onClick={() => setFilterJob(filterJob === job.id ? 'all' : job.id)}
                >
                  <div className="flex items-start justify-between mb-2">
                    <div className={`text-xs font-bold px-2 py-1 rounded ${
                      job.priority === 1 ? 'bg-red-600 text-white' :
                      job.priority === 2 ? 'bg-orange-600 text-white' :
                      job.priority === 3 ? 'bg-yellow-600 text-white' :
                      'bg-gray-600 text-gray-300'
                    }`}>
                      Priority {job.priority}
                    </div>
                  </div>
                  <h3 className="font-bold text-white text-right">{job.job_title}</h3>
                  {job.organization_name && (
                    <p className="text-sm text-gray-300 text-right mt-2">🏢 {job.organization_name}</p>
                  )}
                  {job.contact_person_name && (
                    <p className="text-sm text-gray-300 text-right">👤 {job.contact_person_name}</p>
                  )}
                  <div className="flex justify-between items-center text-right mt-3 gap-2 text-sm">
                    <span className="text-blue-300 font-semibold">{job.match_count} התאמות</span>
                    <span className="text-green-300">{job.found_count} חדשות</span>
                    <span className="text-cyan-300">{job.approved_count} אושרו</span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Selected Job Details */}
        {filterJob !== 'all' && assignedJobsData.length > 0 && (
          <div className="mb-8 bg-gradient-to-r from-blue-900 to-blue-800 rounded-lg p-6 border border-blue-600 shadow-lg">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-2xl font-bold text-white">
                🎯 Matches for Selected Job
              </h2>
              <button
                onClick={() => setFilterJob('all')}
                className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg transition"
              >
                ✕ Clear Selection
              </button>
            </div>

            {assignedJobsData
              .filter((job) => job.id === filterJob)
              .map((job) => (
                <div key={job.id} className="mb-4">
                  <div className="flex items-center justify-between mb-3">
                    <div>
                      <h3 className="text-xl font-bold text-white text-right">{job.job_title}</h3>
                      <p className="text-blue-200 text-sm text-right">Priority: {job.priority}</p>
                      {job.organization_name && (
                        <p className="text-blue-300 text-sm text-right">🏢 {job.organization_name}</p>
                      )}
                      {job.contact_person_name && (
                        <p className="text-blue-300 text-sm text-right">👤 {job.contact_person_name}</p>
                      )}
                    </div>
                    <div className={`text-xs font-bold px-3 py-1 rounded ${
                      job.priority === 1 ? 'bg-red-600 text-white' :
                      job.priority === 2 ? 'bg-orange-600 text-white' :
                      job.priority === 3 ? 'bg-yellow-600 text-white' :
                      'bg-gray-600 text-gray-300'
                    }`}>
                      P{job.priority}
                    </div>
                  </div>

                  {/* Match Stats */}
                  <div className="grid grid-cols-3 gap-3 mb-4">
                    <div className="bg-blue-800 rounded p-3 text-center">
                      <div className="text-2xl font-bold text-blue-300">{job.match_count}</div>
                      <div className="text-xs text-blue-200">Total Matches</div>
                    </div>
                    <div className="bg-green-800 rounded p-3 text-center">
                      <div className="text-2xl font-bold text-green-300">{job.approved_count}</div>
                      <div className="text-xs text-green-200">Approved</div>
                    </div>
                    <div className="bg-cyan-800 rounded p-3 text-center">
                      <div className="text-2xl font-bold text-cyan-300">{job.found_count}</div>
                      <div className="text-xs text-cyan-200">New</div>
                    </div>
                  </div>
                </div>
              ))}
          </div>
        )}

        {/* Filters */}
        <div className="bg-gray-800 rounded-lg p-4 mb-6 border border-gray-700 space-y-4">
          <div className="flex gap-4 flex-col md:flex-row items-start md:items-center flex-wrap">
            {/* Search */}
            <input
              type="text"
              placeholder="חיפוש מועמד, משרה..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="flex-1 min-w-200 bg-gray-700 border border-gray-600 rounded px-4 py-2 text-white placeholder-gray-400 focus:outline-none focus:border-blue-500 text-right"
            />

            {/* Status Filter */}
            <select
              value={filterStatus}
              onChange={(e) => setFilterStatus(e.target.value)}
              className="bg-gray-700 border border-gray-600 rounded px-4 py-2 text-white focus:outline-none focus:border-blue-500"
            >
              <option value="all">כל הסטטוסים</option>
              <option value="found">חדשות</option>
              <option value="approved">מאושרות</option>
              <option value="rejected">דחויות</option>
            </select>

            {/* Group By */}
            <select
              value={groupBy}
              onChange={(e) => setGroupBy(e.target.value as GroupBy)}
              className="bg-gray-700 border border-gray-600 rounded px-4 py-2 text-white focus:outline-none focus:border-blue-500"
            >
              <option value="none">לא לקבץ</option>
              <option value="job">קבץ לפי משרה</option>
              <option value="status">קבץ לפי סטטוס</option>
              <option value="score">קבץ לפי ציון</option>
            </select>

            {/* Sort */}
            <select
              value={sortBy}
              onChange={(e) => setSortBy(e.target.value as any)}
              className="bg-gray-700 border border-gray-600 rounded px-4 py-2 text-white focus:outline-none focus:border-blue-500"
            >
              <option value="newest">הכי חדש</option>
              <option value="oldest">הכי ישן</option>
              <option value="score_high">ציון גבוה</option>
              <option value="score_low">ציון נמוך</option>
            </select>
          </div>
        </div>

        {/* Real-time Matches Section */}
        <div className="mb-8">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-3">
              <h2 className="text-2xl font-bold text-white">
                {filterJob !== 'all' ? '🔍 Matches for Selected Job' : '📋 All Candidate Matches'}
              </h2>
              {lastCVCheck && (
                <div className="text-sm text-green-400 flex items-center gap-1">
                  <span className="animate-pulse">🔴</span> Live Updates
                </div>
              )}
            </div>
          </div>

          {filterJob !== 'all' && (
            <div className="bg-amber-900 border-l-4 border-amber-400 rounded-lg p-4 mb-4 text-amber-100 text-sm">
              📌 Showing matches for the selected job. New matches for this job will appear in real-time every 10 seconds.
            </div>
          )}
        </div>

        {/* Matches by Group */}
        {groupedMatches.map((group, groupIdx) => (
          <div key={groupIdx} className="mb-8">
            {group.label && (
              <h2 className="text-lg font-bold text-white mb-4 px-4 py-2 bg-gray-700 rounded">
                {group.label}
              </h2>
            )}

            {group.matches.length > 0 ? (
              <div className="bg-gray-800 rounded-lg border border-gray-700 overflow-hidden">
                <div className="overflow-x-auto">
                  <table className="w-full text-right">
                    <thead className="bg-gray-700 border-b border-gray-600">
                      <tr>
                        <th className="px-4 py-3 text-right">
                          <input
                            type="checkbox"
                            checked={
                              group.matches.length > 0 &&
                              group.matches.every((m) => selectedMatches.has(m.id))
                            }
                            onChange={() => {
                              const newSelected = new Set(selectedMatches);
                              group.matches.forEach((m) => {
                                if (newSelected.has(m.id)) {
                                  newSelected.delete(m.id);
                                } else {
                                  newSelected.add(m.id);
                                }
                              });
                              setSelectedMatches(newSelected);
                            }}
                            className="cursor-pointer"
                          />
                        </th>
                        <th className="px-4 py-3 text-right font-semibold text-gray-200">מועמד</th>
                        <th className="px-4 py-3 text-right font-semibold text-gray-200">משרה</th>
                        <th className="px-4 py-3 text-right font-semibold text-gray-200">חברה</th>
                        <th className="px-4 py-3 text-right font-semibold text-gray-200">ציון</th>
                        <th className="px-4 py-3 text-right font-semibold text-gray-200">סטטוס</th>
                        <th className="px-4 py-3 text-right font-semibold text-gray-200">פעולות</th>
                      </tr>
                    </thead>
                    <tbody>
                      {group.matches.map((match) => (
                        <tr
                          key={match.id}
                          className="border-b border-gray-700 hover:bg-gray-750 transition"
                        >
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
                              <span className="text-sm text-gray-300">
                                {Math.round(match.matchScore * 100)}%
                              </span>
                            </div>
                          </td>
                          <td className="px-4 py-3">
                            <span
                              className={`px-2 py-1 rounded text-xs font-semibold ${
                                match.status === 'approved'
                                  ? 'bg-green-900 text-green-200'
                                  : match.status === 'rejected'
                                  ? 'bg-red-900 text-red-200'
                                  : 'bg-yellow-900 text-yellow-200'
                              }`}
                            >
                              {match.status === 'found' && 'חדשה'}
                              {match.status === 'approved' && 'אושרה'}
                              {match.status === 'rejected' && 'דחויה'}
                            </span>
                          </td>
                          <td className="px-4 py-3 text-left">
                            {match.status === 'found' && (
                              <div className="flex gap-2">
                                <button
                                  onClick={() => {
                                    setSelectedMatch(match);
                                    setShowApproveModal(true);
                                  }}
                                  className="px-2 py-1 bg-green-600 hover:bg-green-700 text-white text-xs font-semibold rounded transition"
                                >
                                  אשר
                                </button>
                                <button
                                  onClick={() => {
                                    setSelectedMatch(match);
                                    setShowRejectModal(true);
                                  }}
                                  className="px-2 py-1 bg-red-600 hover:bg-red-700 text-white text-xs font-semibold rounded transition"
                                >
                                  דחה
                                </button>
                              </div>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            ) : (
              <div className="p-8 text-center bg-gray-800 rounded-lg border border-gray-700">
                {filterJob !== 'all' ? (
                  <div className="text-gray-300">
                    <p className="text-lg mb-2">🔍 No matches found yet for this job</p>
                    <p className="text-sm text-gray-400">
                      The system is actively searching for candidates. New matches will appear here as they are found. Check back soon!
                    </p>
                  </div>
                ) : (
                  <p className="text-gray-400">אין התאמות בקבוצה זו</p>
                )}
              </div>
            )}
          </div>
        ))}
      </div>

      {/* Approve Modal */}
      {showApproveModal && selectedMatch && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-gray-800 border border-gray-700 rounded-lg p-6 max-w-sm mx-4">
            <h3 className="text-lg font-semibold text-white text-right mb-4">אישור התאמה</h3>
            <p className="text-gray-300 text-right mb-6">
              בטוח שברצונך לאשר את {selectedMatch.candidateName} עבור {selectedMatch.jobTitle}?
            </p>
            <div className="flex gap-3 justify-start">
              <button
                onClick={() => approveMutation.mutate(selectedMatch.id)}
                disabled={approveMutation.isPending}
                className="flex-1 bg-green-600 hover:bg-green-700 disabled:opacity-50 text-white font-semibold py-2 px-4 rounded transition"
              >
                אשר
              </button>
              <button
                onClick={() => setShowApproveModal(false)}
                className="flex-1 bg-gray-700 hover:bg-gray-600 text-white font-semibold py-2 px-4 rounded transition"
              >
                ביטול
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Reject Modal */}
      {showRejectModal && selectedMatch && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-gray-800 border border-gray-700 rounded-lg p-6 max-w-sm mx-4">
            <h3 className="text-lg font-semibold text-white text-right mb-4">דחיית התאמה</h3>
            <p className="text-gray-300 text-right mb-4">
              {selectedMatch.candidateName} - {selectedMatch.jobTitle}
            </p>
            <textarea
              value={rejectionReason}
              onChange={(e) => setRejectionReason(e.target.value)}
              placeholder="סיבת הדחיה..."
              className="w-full bg-gray-700 border border-gray-600 rounded p-3 text-white text-right placeholder-gray-500 mb-4"
              rows={3}
            />
            <div className="flex gap-3 justify-start">
              <button
                onClick={() => rejectMutation.mutate(selectedMatch.id)}
                disabled={rejectMutation.isPending}
                className="flex-1 bg-red-600 hover:bg-red-700 disabled:opacity-50 text-white font-semibold py-2 px-4 rounded transition"
              >
                דחה
              </button>
              <button
                onClick={() => setShowRejectModal(false)}
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

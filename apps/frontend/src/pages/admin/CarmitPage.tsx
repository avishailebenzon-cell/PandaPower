/**
 * Carmit Recruitment Orchestrator Dashboard
 * Manages match routing, quality gate reviews, and job assignments to agents
 */

import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import KPICard from '@/components/KPICard';

interface Match {
  id: string;
  candidateName: string;
  jobTitle: string;
  score: number;
  currentState: string;
  gateResults?: Record<string, any>;
  createdAt: string;
  agent?: string;
}

interface Job {
  id: string;
  title: string;
  description: string;
  candidateCount: number;
  assignedAgent?: string;
  routingConfidence?: number;
  createdAt: string;
  priority?: number;
  status?: string;
  assigned_agent_name?: string;
  contact_person_name?: string;
  job_opening_date?: string;
  created_at?: string;
  updated_at?: string;
}

interface KPIMetrics {
  pendingReview: number;
  approvedMatches: number;
  rejectedMatches: number;
  jobsToRoute: number;
  totalMatches: number;
  approvalRate: number;
}

// Agent configuration
const AGENTS = [
  { code: 'alik', name: 'עליק' },
  { code: 'naama', name: 'נעמה' },
  { code: 'dganit', name: 'דגנית' },
  { code: 'ofir', name: 'אופיר' },
  { code: 'itai', name: 'איתי' },
  { code: 'lior', name: 'ליאור' },
  { code: 'gc', name: 'גיא קורדינטור' },
];

export const CarmitPage = () => {
  const queryClient = useQueryClient();
  const [activeTab, setActiveTab] = useState<'matches' | 'routing' | 'all-jobs'>('matches');
  const [selectedMatch, setSelectedMatch] = useState<Match | null>(null);
  const [selectedJob, setSelectedJob] = useState<Job | null>(null);
  const [showApprovalModal, setShowApprovalModal] = useState(false);
  const [showRejectionModal, setShowRejectionModal] = useState(false);
  const [rejectionReason, setRejectionReason] = useState('');
  const [filterAgent, setFilterAgent] = useState('all');
  const [sortBy, setSortBy] = useState<'newest' | 'score'>('newest');
  const [showOverrideModal, setShowOverrideModal] = useState(false);
  const [jobToOverride, setJobToOverride] = useState<any | null>(null);
  const [selectedNewAgent, setSelectedNewAgent] = useState('');
  const [overrideError, setOverrideError] = useState('');

  // Fetch KPI metrics
  const { data: metrics } = useQuery({
    queryKey: ['carmit-kpi'],
    queryFn: async () => {
      const response = await fetch('/admin/carmit/kpi-summary');
      if (!response.ok) throw new Error('Failed to fetch KPI');
      return response.json() as Promise<KPIMetrics>;
    },
    refetchInterval: 30000, // 30 seconds
  });

  // Fetch pending matches for review
  const { data: matchesData, isLoading: matchesLoading } = useQuery({
    queryKey: ['carmit-pending-matches', filterAgent, sortBy],
    queryFn: async () => {
      const params = new URLSearchParams();
      if (filterAgent !== 'all') params.append('filter_agent', filterAgent);
      params.append('sort', sortBy);
      const response = await fetch(`/admin/carmit/pending-review?${params}`);
      if (!response.ok) throw new Error('Failed to fetch matches');
      return response.json() as Promise<{ matches: Match[]; total: number }>;
    },
    refetchInterval: 15000, // 15 seconds
  });

  // Fetch jobs for routing
  const { data: jobsData, isLoading: jobsLoading } = useQuery({
    queryKey: ['carmit-jobs-to-route'],
    queryFn: async () => {
      const response = await fetch('/admin/carmit/jobs-to-route');
      if (!response.ok) throw new Error('Failed to fetch jobs');
      return response.json() as Promise<{ jobs: Job[]; total: number }>;
    },
    refetchInterval: 20000, // 20 seconds
  });

  // Fetch all jobs with assignments
  const { data: allJobsData, isLoading: allJobsLoading } = useQuery({
    queryKey: ['carmit-all-jobs-with-assignments'],
    queryFn: async () => {
      const response = await fetch('/admin/agent-matching/all-jobs-with-assignments?limit=500');
      if (!response.ok) throw new Error('Failed to fetch all jobs');
      return response.json() as Promise<{
        total: number;
        jobs: Array<{
          id: string;
          title: string;
          description?: string;
          priority: number;
          status: string;
          assigned_agent_code?: string;
          assigned_agent_name?: string;
          contact_person_name?: string;
          job_opening_date?: string;
          is_routed: boolean;
          created_at: string;
          updated_at?: string;
        }>;
        timestamp: string;
      }>;
    },
    refetchInterval: 30000, // 30 seconds
  });

  // Mutation to approve match
  const approveMutation = useMutation({
    mutationFn: async (matchId: string) => {
      const response = await fetch(`/admin/carmit/review-match/${matchId}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ force_approve: true }),
      });
      if (!response.ok) throw new Error('Failed to approve match');
      return response.json();
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['carmit-pending-matches'] });
      queryClient.invalidateQueries({ queryKey: ['carmit-kpi'] });
      setShowApprovalModal(false);
      setSelectedMatch(null);
    },
  });

  // Mutation to reject match
  const rejectMutation = useMutation({
    mutationFn: async (matchId: string) => {
      const response = await fetch(`/admin/carmit/review-match/${matchId}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          force_approve: false,
          override_reason: rejectionReason,
        }),
      });
      if (!response.ok) throw new Error('Failed to reject match');
      return response.json();
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['carmit-pending-matches'] });
      queryClient.invalidateQueries({ queryKey: ['carmit-kpi'] });
      setShowRejectionModal(false);
      setSelectedMatch(null);
      setRejectionReason('');
    },
  });

  // Mutation to route job
  const routeJobMutation = useMutation({
    mutationFn: async (jobId: string) => {
      const response = await fetch(`/admin/carmit/route-job/${jobId}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
      });
      if (!response.ok) throw new Error('Failed to route job');
      return response.json();
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['carmit-jobs-to-route'] });
      queryClient.invalidateQueries({ queryKey: ['carmit-kpi'] });
      setSelectedJob(null);
    },
  });

  // Mutation to override job assignment
  const overrideAssignmentMutation = useMutation({
    mutationFn: async ({
      jobId,
      newAgentCode,
    }: {
      jobId: string;
      newAgentCode: string;
    }) => {
      const response = await fetch('/admin/agent-matching/override-job-assignment', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          job_id: jobId,
          new_agent_code: newAgentCode,
          override_reason: 'manual_override',
        }),
      });
      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.error || 'Failed to override job assignment');
      }
      return response.json();
    },
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: ['carmit-all-jobs-with-assignments'],
      });
      setShowOverrideModal(false);
      setJobToOverride(null);
      setSelectedNewAgent('');
      setOverrideError('');
    },
    onError: (error) => {
      setOverrideError(error instanceof Error ? error.message : 'An error occurred');
    },
  });

  return (
    <div className="min-h-screen bg-gray-900 p-8" dir="rtl">
      {/* Header */}
      <div className="mb-8">
        <h1 className="text-4xl font-bold text-white mb-2">🎯 כרמית - מנהלת הגיוס</h1>
        <p className="text-gray-400">ניהול ניתוב משרות וביקורת התאמות איכות</p>
      </div>

      {/* KPI Cards Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
        <KPICard
          label="בדיקה ממתינה"
          value={metrics?.pendingReview || 0}
          metric="התאמות"
          color="blue"
        />
        <KPICard
          label="אושרו"
          value={metrics?.approvedMatches || 0}
          metric="התאמות"
          color="green"
        />
        <KPICard
          label="דחויות"
          value={metrics?.rejectedMatches || 0}
          metric="התאמות"
          color="red"
        />
        <KPICard
          label="שיעור אישור"
          value={`${Math.round((metrics?.approvalRate || 0) * 100)}%`}
          metric="מהסך הכל"
          color="purple"
        />
      </div>

      {/* Tab Navigation */}
      <div className="mb-6 flex gap-4 border-b border-gray-700 overflow-x-auto">
        <button
          onClick={() => setActiveTab('matches')}
          className={`px-6 py-3 font-semibold transition whitespace-nowrap ${
            activeTab === 'matches'
              ? 'text-blue-400 border-b-2 border-blue-400'
              : 'text-gray-400 hover:text-gray-200'
          }`}
        >
          📋 ביקורת התאמות
        </button>
        <button
          onClick={() => setActiveTab('routing')}
          className={`px-6 py-3 font-semibold transition whitespace-nowrap ${
            activeTab === 'routing'
              ? 'text-blue-400 border-b-2 border-blue-400'
              : 'text-gray-400 hover:text-gray-200'
          }`}
        >
          🎯 ניתוב משרות
        </button>
        <button
          onClick={() => setActiveTab('all-jobs')}
          className={`px-6 py-3 font-semibold transition whitespace-nowrap ${
            activeTab === 'all-jobs'
              ? 'text-blue-400 border-b-2 border-blue-400'
              : 'text-gray-400 hover:text-gray-200'
          }`}
        >
          📊 כל המשרות
        </button>
      </div>

      {/* Matches Review Tab */}
      {activeTab === 'matches' && (
        <div className="space-y-4">
          {/* Filters */}
          <div className="flex gap-4 mb-6">
            <div>
              <label className="block text-sm text-gray-400 mb-2">סנן לפי סוכן</label>
              <select
                value={filterAgent}
                onChange={(e) => setFilterAgent(e.target.value)}
                className="px-4 py-2 rounded bg-gray-800 text-white border border-gray-700 focus:border-blue-500 outline-none"
              >
                <option value="all">כל הסוכנים</option>
                <option value="alik">אליק</option>
                <option value="naama">נעמה</option>
                <option value="dganit">דגנית</option>
                <option value="ofir">אופיר</option>
                <option value="itai">איתי</option>
                <option value="lior">ליאור</option>
                <option value="gc">כללי</option>
              </select>
            </div>

            <div>
              <label className="block text-sm text-gray-400 mb-2">מיין ב</label>
              <select
                value={sortBy}
                onChange={(e) => setSortBy(e.target.value as 'newest' | 'score')}
                className="px-4 py-2 rounded bg-gray-800 text-white border border-gray-700 focus:border-blue-500 outline-none"
              >
                <option value="newest">החדשות ביותר</option>
                <option value="score">ציון גבוה</option>
              </select>
            </div>
          </div>

          {/* Matches List */}
          {matchesLoading ? (
            <div className="text-center py-8 text-gray-400">טוען...</div>
          ) : (matchesData?.matches.length || 0) > 0 ? (
            <div className="grid gap-4">
              {matchesData?.matches.map((match) => (
                <div
                  key={match.id}
                  className="bg-gray-800 border border-gray-700 rounded-lg p-6 hover:border-blue-500 transition"
                >
                  <div className="flex justify-between items-start mb-4">
                    <div>
                      <h3 className="text-lg font-semibold text-white">
                        {match.candidateName}
                      </h3>
                      <p className="text-sm text-gray-400">{match.jobTitle}</p>
                      <p className="text-xs text-gray-500 mt-1">סוכן: {match.agent}</p>
                    </div>
                    <div className="text-right">
                      <div className="text-2xl font-bold text-blue-400">
                        {(match.score * 100).toFixed(0)}%
                      </div>
                      <p className="text-xs text-gray-400">ציון התאמה</p>
                    </div>
                  </div>

                  {/* Score Progress Bar */}
                  <div className="mb-4 bg-gray-700 rounded-full h-2">
                    <div
                      className={`h-2 rounded-full transition ${
                        match.score >= 0.8
                          ? 'bg-green-500'
                          : match.score >= 0.7
                          ? 'bg-yellow-500'
                          : 'bg-red-500'
                      }`}
                      style={{ width: `${match.score * 100}%` }}
                    />
                  </div>

                  {/* Gate Results (if available) */}
                  {match.gateResults && (
                    <div className="mb-4 space-y-2">
                      <p className="text-sm font-semibold text-gray-300">תוצאות שערים:</p>
                      {Object.entries(match.gateResults).map(([gate, result]: [string, any]) => (
                        <div key={gate} className="flex items-center gap-2 text-xs">
                          <span className={result.passed ? '✅' : '❌'} />
                          <span className="text-gray-400 capitalize">{gate}</span>
                          {result.reason && (
                            <span className="text-gray-500">({result.reason})</span>
                          )}
                        </div>
                      ))}
                    </div>
                  )}

                  {/* Actions */}
                  <div className="flex gap-2">
                    <button
                      onClick={() => {
                        setSelectedMatch(match);
                        setShowApprovalModal(true);
                      }}
                      className="flex-1 px-4 py-2 bg-green-600 hover:bg-green-700 text-white rounded font-semibold transition text-sm"
                      disabled={approveMutation.isPending}
                    >
                      ✅ אישור
                    </button>
                    <button
                      onClick={() => {
                        setSelectedMatch(match);
                        setShowRejectionModal(true);
                      }}
                      className="flex-1 px-4 py-2 bg-red-600 hover:bg-red-700 text-white rounded font-semibold transition text-sm"
                      disabled={rejectMutation.isPending}
                    >
                      ❌ דחייה
                    </button>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="text-center py-8 text-gray-400">אין התאמות ממתינות לביקורת</div>
          )}
        </div>
      )}

      {/* Jobs Routing Tab */}
      {activeTab === 'routing' && (
        <div className="space-y-4">
          {jobsLoading ? (
            <div className="text-center py-8 text-gray-400">טוען...</div>
          ) : (jobsData?.jobs.length || 0) > 0 ? (
            <div className="grid gap-4">
              {jobsData?.jobs.map((job) => (
                <div
                  key={job.id}
                  className="bg-gray-800 border border-gray-700 rounded-lg p-6 hover:border-purple-500 transition"
                >
                  <div className="flex justify-between items-start mb-4">
                    <div className="flex-1">
                      <h3 className="text-lg font-semibold text-white">{job.title}</h3>
                      <p className="text-sm text-gray-400 mt-2">{job.description}</p>
                      <div className="mt-3 flex gap-4 text-sm text-gray-400">
                        <span>👥 {job.candidateCount} מועמדים זמינים</span>
                        {job.assignedAgent && (
                          <>
                            <span>📌 סוכן מוקצה: {job.assignedAgent}</span>
                            {job.routingConfidence && (
                              <span>
                                📊 ביטחון: {(job.routingConfidence * 100).toFixed(0)}%
                              </span>
                            )}
                          </>
                        )}
                      </div>
                    </div>
                  </div>

                  {/* Actions */}
                  <div className="flex gap-2">
                    {!job.assignedAgent ? (
                      <button
                        onClick={() => {
                          setSelectedJob(job);
                          routeJobMutation.mutate(job.id);
                        }}
                        className="flex-1 px-4 py-2 bg-purple-600 hover:bg-purple-700 text-white rounded font-semibold transition text-sm"
                        disabled={routeJobMutation.isPending}
                      >
                        🎯 ניתוב לסוכן
                      </button>
                    ) : (
                      <button
                        onClick={() => {
                          setSelectedJob(job);
                          routeJobMutation.mutate(job.id);
                        }}
                        className="flex-1 px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded font-semibold transition text-sm"
                        disabled={routeJobMutation.isPending}
                      >
                        🔄 ניתוב מחדש
                      </button>
                    )}
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="text-center py-8 text-gray-400">אין משרות לניתוב</div>
          )}
        </div>
      )}

      {/* All Jobs Tab */}
      {activeTab === 'all-jobs' && (
        <div className="space-y-4">
          {allJobsLoading ? (
            <div className="text-center py-8 text-gray-400">טוען...</div>
          ) : (allJobsData?.jobs.length || 0) > 0 ? (
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="border-b border-gray-700">
                    <th className="text-right px-4 py-3 text-gray-300 font-semibold">כותרת משרה</th>
                    <th className="text-right px-4 py-3 text-gray-300 font-semibold">עדיפות</th>
                    <th className="text-right px-4 py-3 text-gray-300 font-semibold">איש קשר</th>
                    <th className="text-right px-4 py-3 text-gray-300 font-semibold">תאריך פתיחה</th>
                    <th className="text-right px-4 py-3 text-gray-300 font-semibold">סוכן מוקצה</th>
                    <th className="text-right px-4 py-3 text-gray-300 font-semibold">סטטוס</th>
                    <th className="text-right px-4 py-3 text-gray-300 font-semibold">תאריך יצירה</th>
                    <th className="text-right px-4 py-3 text-gray-300 font-semibold">פעולות</th>
                  </tr>
                </thead>
                <tbody>
                  {allJobsData?.jobs.map((job) => (
                    <tr
                      key={job.id}
                      className="border-b border-gray-800 hover:bg-gray-800/50 transition"
                    >
                      <td className="px-4 py-3 text-white">{job.title}</td>
                      <td className="px-4 py-3 text-gray-400">
                        <span
                          className={`px-2 py-1 rounded text-sm font-semibold ${
                            job.priority === 1
                              ? 'bg-red-900 text-red-300'
                              : job.priority <= 2
                              ? 'bg-orange-900 text-orange-300'
                              : job.priority <= 3
                              ? 'bg-yellow-900 text-yellow-300'
                              : 'bg-gray-700 text-gray-300'
                          }`}
                        >
                          {job.priority}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-gray-400 text-sm">
                        {job.contact_person_name || '-'}
                      </td>
                      <td className="px-4 py-3 text-gray-400 text-sm">
                        {job.job_opening_date ? new Date(job.job_opening_date).toLocaleDateString('he-IL') : '-'}
                      </td>
                      <td className="px-4 py-3">
                        {job.assigned_agent_name ? (
                          <span className="px-2 py-1 bg-green-900 text-green-300 rounded text-sm font-semibold">
                            {job.assigned_agent_name}
                          </span>
                        ) : (
                          <span className="text-gray-500 text-sm">לא הוקצה</span>
                        )}
                      </td>
                      <td className="px-4 py-3 text-gray-400">
                        <span
                          className={`px-2 py-1 rounded text-sm ${
                            job.status === 'open'
                              ? 'bg-blue-900 text-blue-300'
                              : job.status === 'closed'
                              ? 'bg-gray-700 text-gray-300'
                              : 'bg-gray-600 text-gray-300'
                          }`}
                        >
                          {job.status}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-gray-400 text-sm">
                        {new Date(job.created_at).toLocaleDateString('he-IL')}
                      </td>
                      <td className="px-4 py-3">
                        <button
                          onClick={() => {
                            setJobToOverride(job);
                            setSelectedNewAgent('');
                            setOverrideError('');
                            setShowOverrideModal(true);
                          }}
                          className="px-3 py-1 bg-orange-600 hover:bg-orange-700 text-white rounded text-sm font-semibold transition"
                          title="עדכן סוכן"
                        >
                          ⚙️ עדכן
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="text-center py-8 text-gray-400">אין משרות</div>
          )}
        </div>
      )}

      {/* Approval Modal */}
      {showApprovalModal && selectedMatch && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-gray-800 border border-gray-700 rounded-lg p-6 max-w-md w-full mx-4">
            <h2 className="text-xl font-semibold text-white mb-4">אישור התאמה</h2>
            <p className="text-gray-400 mb-6">
              אתה עומד לאשר את ההתאמה של <span className="font-semibold">{selectedMatch.candidateName}</span> ל<span className="font-semibold">{selectedMatch.jobTitle}</span>
            </p>
            <div className="flex gap-2">
              <button
                onClick={() => {
                  approveMutation.mutate(selectedMatch.id);
                }}
                className="flex-1 px-4 py-2 bg-green-600 hover:bg-green-700 text-white rounded font-semibold transition"
                disabled={approveMutation.isPending}
              >
                ✅ אישור
              </button>
              <button
                onClick={() => setShowApprovalModal(false)}
                className="flex-1 px-4 py-2 bg-gray-700 hover:bg-gray-600 text-white rounded font-semibold transition"
              >
                ביטול
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Rejection Modal */}
      {showRejectionModal && selectedMatch && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-gray-800 border border-gray-700 rounded-lg p-6 max-w-md w-full mx-4">
            <h2 className="text-xl font-semibold text-white mb-4">דחיית התאמה</h2>
            <p className="text-gray-400 mb-4">
              אתה עומד לדחות את ההתאמה של <span className="font-semibold">{selectedMatch.candidateName}</span>
            </p>
            <textarea
              value={rejectionReason}
              onChange={(e) => setRejectionReason(e.target.value)}
              placeholder="הסיבה לדחיה..."
              className="w-full px-4 py-2 rounded bg-gray-700 text-white border border-gray-600 focus:border-red-500 outline-none resize-none h-24 mb-4"
            />
            <div className="flex gap-2">
              <button
                onClick={() => {
                  rejectMutation.mutate(selectedMatch.id);
                }}
                className="flex-1 px-4 py-2 bg-red-600 hover:bg-red-700 text-white rounded font-semibold transition"
                disabled={rejectMutation.isPending || !rejectionReason}
              >
                ❌ דחייה
              </button>
              <button
                onClick={() => {
                  setShowRejectionModal(false);
                  setRejectionReason('');
                }}
                className="flex-1 px-4 py-2 bg-gray-700 hover:bg-gray-600 text-white rounded font-semibold transition"
              >
                ביטול
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Override Job Assignment Modal */}
      {showOverrideModal && jobToOverride && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-gray-800 border border-gray-700 rounded-lg p-6 max-w-md w-full mx-4">
            <h2 className="text-xl font-semibold text-white mb-4">📋 עדכון הקצאת סוכן</h2>

            <div className="mb-4 p-3 bg-orange-900 border border-orange-700 rounded">
              <p className="text-orange-300 text-sm font-semibold">⚠️ זהירות!</p>
              <p className="text-orange-200 text-xs mt-2">
                פעולה זו תמחק את כל ההתאמות שיצר הסוכן הקודם עבור משרה זו ותחזור את המשרה להמתנה לסוכן החדש.
              </p>
            </div>

            <div className="mb-4">
              <p className="text-gray-300 mb-2 font-semibold">משרה:</p>
              <p className="text-white">{jobToOverride.title}</p>
            </div>

            <div className="mb-4">
              <p className="text-gray-300 mb-2 font-semibold">סוכן נוכחי:</p>
              <p className="text-white">
                {jobToOverride.assigned_agent_name || '❌ לא הוקצה'}
              </p>
            </div>

            <div className="mb-4">
              <label className="block text-gray-300 mb-2 font-semibold">בחר סוכן חדש:</label>
              <select
                value={selectedNewAgent}
                onChange={(e) => {
                  setSelectedNewAgent(e.target.value);
                  setOverrideError('');
                }}
                className="w-full px-4 py-2 rounded bg-gray-700 text-white border border-gray-600 focus:border-blue-500 outline-none"
              >
                <option value="">-- בחר סוכן --</option>
                {AGENTS.map((agent) => (
                  <option key={agent.code} value={agent.code}>
                    {agent.name} ({agent.code})
                  </option>
                ))}
              </select>
            </div>

            {overrideError && (
              <div className="mb-4 p-3 bg-red-900 border border-red-700 rounded">
                <p className="text-red-300 text-sm">{overrideError}</p>
              </div>
            )}

            <div className="flex gap-2">
              <button
                onClick={() => {
                  if (selectedNewAgent) {
                    overrideAssignmentMutation.mutate({
                      jobId: jobToOverride.id,
                      newAgentCode: selectedNewAgent,
                    });
                  } else {
                    setOverrideError('בחר סוכן מן הרשימה');
                  }
                }}
                className="flex-1 px-4 py-2 bg-orange-600 hover:bg-orange-700 text-white rounded font-semibold transition disabled:opacity-50"
                disabled={
                  overrideAssignmentMutation.isPending ||
                  !selectedNewAgent ||
                  selectedNewAgent === jobToOverride.assigned_agent_code
                }
              >
                {overrideAssignmentMutation.isPending
                  ? '⏳ מעדכן...'
                  : '✅ עדכן סוכן'}
              </button>
              <button
                onClick={() => {
                  setShowOverrideModal(false);
                  setJobToOverride(null);
                  setSelectedNewAgent('');
                  setOverrideError('');
                }}
                className="flex-1 px-4 py-2 bg-gray-700 hover:bg-gray-600 text-white rounded font-semibold transition"
                disabled={overrideAssignmentMutation.isPending}
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

export default CarmitPage;

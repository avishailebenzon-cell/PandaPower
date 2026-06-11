/**
 * Carmit Recruitment Orchestrator Dashboard
 * Manages match routing, quality gate reviews, and job assignments to agents
 */

import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import KPICard from '@/components/KPICard';
import { RecruiterMatchesPanel } from '@/components/RecruiterMatchesPanel';
import { CandidateDecisionMatrix } from '@/components/CandidateDecisionMatrix';
import { MatchDetailModal } from '@/components/MatchDetailModal';
import type { DepartmentMatch, ClearanceMatch } from '@/api/recruitment-departments';
import { agentNameHe } from '@/data/agents';

// Shape of each row from GET /admin/carmit/agent-matches.
// The backend returns enough candidate + match detail to populate both
// the table row and the two modals (candidate profile / match detail)
// without a follow-up fetch per click.
interface AgentMatchRow {
  id: string;
  candidate_id: string;
  candidate_name: string;
  candidate_email: string | null;
  candidate_phone: string | null;
  candidate_location: string | null;
  candidate_clearance: string | null;
  candidate_years: number | null;
  candidate_key_skills: string[];
  // top_education is a JSONB dict in DB (institution / degree / field / …) —
  // typed as `unknown` so the renderer must coerce it to a display string.
  candidate_top_education: unknown;
  candidate_experiences: unknown[];
  candidate_language: string | null;
  candidate_recommendation_score: number | null;
  job_id: string;
  job_title: string;
  job_description: string | null;
  // Client/organization name + 4-digit Pipedrive job number for the job.
  company_name: string | null;
  pipedrive_deal_id: number | null;
  required_clearance: string | null;
  clearance_match: ClearanceMatch;
  agent_code: string;
  match_score: number;
  current_state: string;
  match_reasoning: string;
  reasoning_preview: string;
  strengths: string[];
  gaps: string[];
  // Carmit's quality-gate ruling — null until she reviews. Explains WHY a
  // match was rejected/approved (decision_reasoning + the gates that failed).
  carmit_decision: {
    decision: 'approved' | 'rejected';
    reasoning: string;
    failed_gates: { gate: string; reason: string }[];
    decided_at: string | null;
  } | null;
  created_at: string;
  updated_at: string;
}

// Human-readable Hebrew labels for Carmit's quality gates. Keys match the
// gate names the carmit worker writes into match_state_history.details.
const GATE_LABELS_HE: Record<string, string> = {
  past_rejection: 'נדחה בעבר לתפקיד זה',
  already_declined: 'המועמד דחה בעבר',
  conflict_of_interest: 'ניגוד עניינים',
  clearance_match: 'התאמת סיווג ביטחוני',
  quality_threshold: 'סף ציון איכות',
  relevant_skills: 'כישורים רלוונטיים',
};

// Hebrew labels for match pipeline states. Mirrors the inline STATE_BADGES
// used in the non-grouped agent-matches table so the grouped view (and any
// other raw-state display) shows Hebrew instead of the DB enum value.
const STATE_LABELS_HE: Record<string, string> = {
  found: 'נמצא',
  carmit_approved: 'אושר ע״י כרמית',
  carmit_rejected: 'נדחה ע״י כרמית',
  sent_to_tal: 'ממתינה לטל',
  tal_conversation: 'בשיחה עם טל',
  tal_approved: 'אושר ע״י טל',
  tal_rejected: 'נדחה ע״י טל',
  sent_to_elad: 'ממתינה לאלעד',
  elad_conversation: 'בשיחה עם אלעד',
  elad_approved: 'אושר ע״י אלעד',
  hired: '🎉 הושמה',
  placement_failed: 'כשלון השמה',
};

const stateLabelHe = (state: string): string =>
  STATE_LABELS_HE[state] || state;

interface GateResult {
  passed: boolean;
  reason?: string;
}

interface CarmitDecision {
  match_id: string;
  candidate_name: string;
  job_title: string;
  company_name?: string | null;
  pipedrive_deal_id?: number | null;
  decision: 'approved' | 'rejected';
  match_score: number;
  gate_results: Record<string, GateResult>;
  reasoning: string;
  decided_at: string;
  candidate_id?: string;
  job_id?: string;
  // Current pipeline status of the match (backend /decisions returns these).
  current_state?: string;
  state_display?: string;
  state_label?: string;
}

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
  organization_name?: string;
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
  { code: 'naama', name: 'נעמה' },
  { code: 'alik', name: 'אליק' },
  { code: 'dganit', name: 'דגנית' },
  { code: 'ofir', name: 'אופיר' },
  { code: 'itai', name: 'איתי' },
  { code: 'lior', name: 'ליאור' },
  { code: 'gc', name: 'כללי' },
  { code: 'mani', name: 'מני' },
];

export const CarmitPage = () => {
  // CRITICAL: Define API_BASE at the top so all fetch calls use it consistently
  const API_BASE = import.meta.env.VITE_API_URL || '';

  const queryClient = useQueryClient();
  const [activeTab, setActiveTab] = useState<
    'candidate-matrix' | 'queue' | 'decisions' | 'agent-matches' | 'all-jobs' | 'sent-to-tal' | 'sent-to-elad'
  >('decisions');
  // Pagination state for the new "agent-matches" tab (≥70% from all 8 agents).
  const [agentMatchesPage, setAgentMatchesPage] = useState(0);
  const AGENT_MATCHES_PAGE_SIZE = 25;
  // Score-floor filter for the table. Stored as 0.0–1.0 (matches backend
  // min_score param). 0.70 is the default the user originally asked for.
  const [agentMatchesMinScore, setAgentMatchesMinScore] = useState(0.70);
  // Sort state. Backend accepts: score | candidate | job | agent | state |
  // clearance | date. Default: highest score first.
  type SortKey = 'score' | 'candidate' | 'job' | 'agent' | 'state' | 'clearance' | 'date';
  type SortDir = 'asc' | 'desc';
  const [agentMatchesSortBy, setAgentMatchesSortBy] = useState<SortKey>('score');
  const [agentMatchesSortDir, setAgentMatchesSortDir] = useState<SortDir>('desc');
  // Modal state for the agent-matches table:
  //  • selectedAgentMatchForDetail → match-detail modal (click on score %)
  //  • selectedAgentCandidate     → candidate-profile modal (click on name)
  const [selectedAgentMatchForDetail, setSelectedAgentMatchForDetail] = useState<DepartmentMatch | null>(null);
  const [selectedAgentCandidate, setSelectedAgentCandidate] = useState<AgentMatchRow | null>(null);
  const [selectedMatch, setSelectedMatch] = useState<CarmitDecision | null>(null);
  const [selectedJob, setSelectedJob] = useState<Job | null>(null);
  const [decisionFilter, setDecisionFilter] = useState<'all' | 'approved' | 'rejected'>('all');
  const [showOverrideModal, setShowOverrideModal] = useState(false);
  const [jobToOverride, setJobToOverride] = useState<any | null>(null);
  const [selectedNewAgent, setSelectedNewAgent] = useState('');
  const [overrideError, setOverrideError] = useState('');
  const [agentMatchesGroupBy, setAgentMatchesGroupBy] = useState<'none' | 'state' | 'agent' | 'clearance' | 'candidate'>('none');
  const [allJobsGroupBy, setAllJobsGroupBy] = useState<'none' | 'priority' | 'assigned_agent' | 'status'>('none');

  // Fetch KPI metrics
  const { data: metrics } = useQuery({
    queryKey: ['carmit-kpi'],
    queryFn: async () => {
      const response = await fetch(`${API_BASE}/admin/carmit/kpi-summary`);
      if (!response.ok) throw new Error('Failed to fetch KPI');
      return response.json() as Promise<KPIMetrics>;
    },
    refetchInterval: 30000, // 30 seconds
  });

  // Fetch Carmit's decisions (already-made decisions with gate results)
  const { data: decisionsData, isLoading: decisionsLoading } = useQuery({
    queryKey: ['carmit-decisions', decisionFilter],
    queryFn: async () => {
      const params = new URLSearchParams();
      params.append('decision_filter', decisionFilter);
      params.append('limit', '50');
      const response = await fetch(`${API_BASE}/admin/carmit/decisions?${params}`);
      if (!response.ok) throw new Error('Failed to fetch decisions');
      return response.json() as Promise<{ decisions: CarmitDecision[]; total: number }>;
    },
    refetchInterval: 15000, // 15 seconds
  });

  // Fetch jobs for routing
  const { data: jobsData, isLoading: jobsLoading } = useQuery({
    queryKey: ['carmit-jobs-to-route'],
    queryFn: async () => {
      const response = await fetch(`${API_BASE}/admin/carmit/jobs-to-route`);
      if (!response.ok) throw new Error('Failed to fetch jobs');
      return response.json() as Promise<{ jobs: Job[]; total: number }>;
    },
    refetchInterval: 20000, // 20 seconds
  });

  // Fetch the high-quality (≥70%) matches across ALL 8 recruitment agents
  // for the "התאמות מסוכני הגיוס" tab. Paginated via local agentMatchesPage state.
  const { data: agentMatchesData, isLoading: agentMatchesLoading, error: agentMatchesError } = useQuery({
    queryKey: ['carmit-agent-matches', agentMatchesPage, agentMatchesMinScore, agentMatchesSortBy, agentMatchesSortDir],
    queryFn: async () => {
      const offset = agentMatchesPage * AGENT_MATCHES_PAGE_SIZE;
      const url = `${API_BASE}/admin/carmit/agent-matches?limit=${AGENT_MATCHES_PAGE_SIZE}&offset=${offset}&min_score=${agentMatchesMinScore}&sort_by=${agentMatchesSortBy}&sort_dir=${agentMatchesSortDir}`;
      const r = await fetch(url);
      if (!r.ok) throw new Error('Failed to fetch agent matches');
      return r.json() as Promise<{
        matches: AgentMatchRow[];
        total: number;
        offset: number;
        limit: number;
        min_score: number;
      }>;
    },
    refetchInterval: 30000,
  });

  // Fetch all jobs with assignments
  const { data: allJobsData, isLoading: allJobsLoading } = useQuery({
    queryKey: ['carmit-all-jobs-with-assignments'],
    queryFn: async () => {
      const response = await fetch(`${API_BASE}/admin/agent-matching/all-jobs-with-assignments?limit=500`);
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
          organization_name?: string;
          pipedrive_deal_id?: number;
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


  // Mutation to route job
  const routeJobMutation = useMutation({
    mutationFn: async (jobId: string) => {
      const response = await fetch(`${API_BASE}/admin/carmit/route-job/${jobId}`, {
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
      const response = await fetch(`${API_BASE}/admin/agent-matching/override-job-assignment`, {
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
          onClick={() => setActiveTab('candidate-matrix')}
          className={`px-6 py-3 font-semibold transition whitespace-nowrap ${
            activeTab === 'candidate-matrix'
              ? 'text-blue-400 border-b-2 border-blue-400'
              : 'text-gray-400 hover:text-gray-200'
          }`}
          title="מטריצת החלטות כל המועמדים"
        >
          📊 כל המועמדים
        </button>
        <button
          onClick={() => setActiveTab('queue')}
          className={`px-6 py-3 font-semibold transition whitespace-nowrap ${
            activeTab === 'queue'
              ? 'text-blue-400 border-b-2 border-blue-400'
              : 'text-gray-400 hover:text-gray-200'
          }`}
          title="התאמות בהמתנה לבדיקת כרמית"
        >
          🔍 תור ביקורת כרמית
        </button>
        <button
          onClick={() => setActiveTab('decisions')}
          className={`px-6 py-3 font-semibold transition whitespace-nowrap ${
            activeTab === 'decisions'
              ? 'text-blue-400 border-b-2 border-blue-400'
              : 'text-gray-400 hover:text-gray-200'
          }`}
        >
          ✅ החלטות כרמית
        </button>
        <button
          onClick={() => setActiveTab('agent-matches')}
          className={`px-6 py-3 font-semibold transition whitespace-nowrap ${
            activeTab === 'agent-matches'
              ? 'text-blue-400 border-b-2 border-blue-400'
              : 'text-gray-400 hover:text-gray-200'
          }`}
          title="כל ההתאמות (70%+) מכל 8 סוכני הגיוס"
        >
          🎯 התאמות מסוכני הגיוס
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
        <button
          onClick={() => setActiveTab('sent-to-tal')}
          className={`px-6 py-3 font-semibold transition whitespace-nowrap ${
            activeTab === 'sent-to-tal'
              ? 'text-blue-400 border-b-2 border-blue-400'
              : 'text-gray-400 hover:text-gray-200'
          }`}
          title="התאמות שכרמית העבירה לטל לשיחה עם המועמד"
        >
          📤 העברתי לטל (לדבר עם מועמד)
        </button>
        <button
          onClick={() => setActiveTab('sent-to-elad')}
          className={`px-6 py-3 font-semibold transition whitespace-nowrap ${
            activeTab === 'sent-to-elad'
              ? 'text-blue-400 border-b-2 border-blue-400'
              : 'text-gray-400 hover:text-gray-200'
          }`}
          title="התאמות שעברו לאלעד לשיחה עם הלקוח"
        >
          📤 העברתי לאלעד (לדבר עם לקוח)
        </button>
      </div>

      {/* === מטריצת החלטות מועמדים === */}
      {activeTab === 'candidate-matrix' && (
        <CandidateDecisionMatrix showTitle={true} />
      )}

      {/* === תור ביקורת כרמית === */}
      {/* Matches waiting for Carmit review (found state) */}
      {activeTab === 'queue' && (
        <div className="space-y-4">
          <div>
            <h2 className="text-2xl font-bold text-white">🔍 תור ביקורת כרמית</h2>
            <p className="text-sm text-gray-400">
              התאמות שנמצאו על ידי סוכני הגיוס וממתינות לביקורת איכות של כרמית.
            </p>
          </div>
          <RecruiterMatchesPanel recruiter="carmit" showSubTabs={false} initialSubTab="queue" />
        </div>
      )}

      {/* Carmit Decisions Tab */}
      {activeTab === 'decisions' && (
        <div className="space-y-4">
          {/* Filters */}
          <div className="flex gap-4 mb-6">
            <div>
              <label className="block text-sm text-gray-400 mb-2">סנן לפי החלטה</label>
              <select
                value={decisionFilter}
                onChange={(e) => setDecisionFilter(e.target.value as 'all' | 'approved' | 'rejected')}
                className="px-4 py-2 rounded bg-gray-800 text-white border border-gray-700 focus:border-blue-500 outline-none"
              >
                <option value="all">כל ההחלטות</option>
                <option value="approved">✅ אושרו</option>
                <option value="rejected">❌ דחויות</option>
              </select>
            </div>
          </div>

          {/* Decisions List */}
          {decisionsLoading ? (
            <div className="text-center py-8 text-gray-400">טוען...</div>
          ) : (decisionsData?.decisions.length || 0) > 0 ? (
            <div className="grid gap-4">
              {decisionsData?.decisions.map((decision) => (
                <div
                  key={decision.match_id}
                  className="bg-gray-800 border border-gray-700 rounded-lg p-6 hover:border-purple-500 transition"
                >
                  {/* Header with Decision Badge and Current Status */}
                  <div className="flex justify-between items-start mb-4">
                    <div className="flex-1">
                      <div className="flex items-center gap-3 mb-2 flex-wrap">
                        <h3 className="text-lg font-semibold text-white">
                          {decision.candidate_name}
                        </h3>
                        <span className={`px-3 py-1 rounded font-semibold text-sm ${
                          decision.decision === 'approved'
                            ? 'bg-green-900 text-green-300'
                            : 'bg-red-900 text-red-300'
                        }`}>
                          {decision.decision === 'approved' ? '✅ אושרה' : '❌ דחויה'}
                        </span>
                        {/* Current Status Badge */}
                        <span className={`px-3 py-1 rounded text-xs font-medium ${
                          decision.state_label === 'waiting' ? 'bg-yellow-900 text-yellow-300' :
                          decision.state_label === 'with_tal' ? 'bg-blue-900 text-blue-300' :
                          decision.state_label === 'tal_reviewing' ? 'bg-cyan-900 text-cyan-300' :
                          decision.state_label === 'with_elad' ? 'bg-purple-900 text-purple-300' :
                          decision.state_label === 'hired' ? 'bg-emerald-900 text-emerald-300' :
                          decision.state_label === 'rejected_tal' ? 'bg-orange-900 text-orange-300' :
                          decision.state_label === 'rejected_elad' ? 'bg-red-900 text-red-300' :
                          'bg-gray-700 text-gray-300'
                        }`}>
                          {decision.state_display}
                        </span>
                      </div>
                      <p className="text-sm text-gray-400">
                        {decision.job_title}
                        {decision.company_name && (
                          <span className="text-gray-500"> · 🏢 {decision.company_name}</span>
                        )}
                        {decision.pipedrive_deal_id && (
                          <span className="text-gray-500"> · משרה #{decision.pipedrive_deal_id}</span>
                        )}
                      </p>
                    </div>
                    <div className="text-right">
                      <div className="text-2xl font-bold text-blue-400">
                        {(decision.match_score * 100).toFixed(0)}%
                      </div>
                      <p className="text-xs text-gray-400">ציון התאמה</p>
                    </div>
                  </div>

                  {/* Score Progress Bar */}
                  <div className="mb-4 bg-gray-700 rounded-full h-2">
                    <div
                      className={`h-2 rounded-full transition ${
                        decision.match_score >= 0.8
                          ? 'bg-green-500'
                          : decision.match_score >= 0.7
                          ? 'bg-yellow-500'
                          : 'bg-red-500'
                      }`}
                      style={{ width: `${decision.match_score * 100}%` }}
                    />
                  </div>

                  {/* Gate Results */}
                  <div className="mb-4 space-y-2">
                    <p className="text-sm font-semibold text-gray-300">📋 תוצאות שערים:</p>
                    <div className="grid grid-cols-2 gap-2">
                      {Object.entries(decision.gate_results).map(([gate, result]) => (
                        <div key={gate} className="flex items-start gap-2 text-xs bg-gray-900 p-2 rounded">
                          <span>{result.passed ? '✅' : '❌'}</span>
                          <div>
                            <p className="text-gray-300 font-medium">{GATE_LABELS_HE[gate] || gate.replace(/_/g, ' ')}</p>
                            {result.reason && (
                              <p className="text-gray-500 text-xs">{result.reason}</p>
                            )}
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>

                  {/* Decision Reasoning - Enhanced with detailed explanation */}
                  <div className="mb-4 space-y-3">
                    {/* Main Decision Reasoning */}
                    <div className={`border-l-4 p-3 rounded ${
                      decision.decision === 'approved'
                        ? 'bg-green-900/20 border-green-500'
                        : 'bg-red-900/20 border-red-500'
                    }`}>
                      <p className="text-sm font-semibold text-gray-300 mb-2">
                        {decision.decision === 'approved' ? '✅ סיבות האישור:' : '❌ סיבות הדחייה:'}
                      </p>
                      {decision.reasoning ? (
                        <p className="text-sm text-gray-300 leading-relaxed">{decision.reasoning}</p>
                      ) : (
                        <p className="text-sm text-gray-500 italic">לא צוינה הנמקה</p>
                      )}
                    </div>

                    {/* Gate-by-Gate Analysis */}
                    {Object.entries(decision.gate_results).length > 0 && (
                      <div className="bg-gray-900 border border-gray-700 p-3 rounded">
                        <p className="text-sm font-semibold text-gray-300 mb-3">📊 ניתוח שערים מפורט:</p>
                        <div className="space-y-2">
                          {Object.entries(decision.gate_results).map(([gate, result]) => (
                            <div key={gate} className={`p-2.5 rounded border ${
                              result.passed
                                ? 'bg-green-900/15 border-green-700/30 text-green-200'
                                : 'bg-red-900/15 border-red-700/30 text-red-200'
                            }`}>
                              <div className="flex items-start gap-2">
                                <span className="text-lg mt-0.5">{result.passed ? '✅' : '❌'}</span>
                                <div className="flex-1">
                                  <p className="font-semibold text-sm">
                                    {GATE_LABELS_HE[gate] || gate.replace(/_/g, ' ')}
                                  </p>
                                  {result.reason && (
                                    <p className="text-xs text-gray-300 mt-1">{result.reason}</p>
                                  )}
                                </div>
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>

                  {/* Decision Timestamp */}
                  <p className="text-xs text-gray-500">
                    🕐 הוחלט: {new Date(decision.decided_at).toLocaleDateString('he-IL')} {new Date(decision.decided_at).toLocaleTimeString('he-IL')}
                  </p>
                </div>
              ))}
            </div>
          ) : (
            <div className="text-center py-8 text-gray-400">
              {decisionFilter === 'all'
                ? 'אין החלטות עדיין'
                : decisionFilter === 'approved'
                ? 'אין התאמות אושרו עדיין'
                : 'אין התאמות דחויות עדיין'}
            </div>
          )}
        </div>
      )}

      {/* === התאמות מסוכני הגיוס === */}
      {/* All valid matches scored 70%+ from any of the 8 recruitment agents
          (Naama / Alik / Dganit / Ofir / Itai / Lior / GC / Mani). Sorted
          by score desc, paginated. Replaces the previous "ניתוב משרות" tab. */}
      {activeTab === 'agent-matches' && (
        <div className="space-y-4">
          <div className="flex items-end justify-between flex-wrap gap-3">
            <div>
              <h2 className="text-2xl font-bold text-white">🎯 התאמות מסוכני הגיוס</h2>
              <p className="text-sm text-gray-400">
                תצוגה מסוננת: רק התאמות בציון ≥70% שנוצרו על־ידי אחד מ-8 סוכני הגיוס
                (נעמה / אליק / דגנית / אופיר / איתי / ליאור / כללי / מני), בכל הסטטוסים. ממוין לפי ציון יורד.
                לכן מספרים כאן נמוכים מהמסך "העברתי לטל", שמציג את כל ההתאמות בסטטוס ללא סף ציון וללא סינון סוכן.
              </p>
            </div>
            <div className="text-sm text-gray-400">
              סה״כ {agentMatchesData?.total ?? 0} התאמות
            </div>
          </div>

          {/* Toolbar: score-floor filter & grouping. Lives above the loading/empty
              guard so the user always sees the controls. */}
          <div className="flex items-center gap-4 flex-wrap">
            <div className="flex items-center gap-3">
              <label className="text-sm text-gray-300 font-semibold">סינון לפי ציון:</label>
              <select
                value={agentMatchesMinScore}
                onChange={(e) => {
                  setAgentMatchesMinScore(parseFloat(e.target.value));
                  setAgentMatchesPage(0); // jumping to page 1 — the page count just changed
                }}
                className="bg-gray-800 border border-gray-700 text-gray-200 text-sm rounded px-3 py-1.5 focus:border-blue-500 outline-none"
              >
                <option value={0}>הכל</option>
                <option value={0.5}>50% ומעלה</option>
                <option value={0.6}>60% ומעלה</option>
                <option value={0.7}>70% ומעלה</option>
                <option value={0.8}>80% ומעלה</option>
                <option value={0.9}>90% ומעלה</option>
              </select>
            </div>

            <div className="flex items-center gap-3">
              <label className="text-sm text-gray-300 font-semibold">קיבוץ לפי:</label>
              <select
                value={agentMatchesGroupBy}
                onChange={(e) => setAgentMatchesGroupBy(e.target.value as 'none' | 'state' | 'agent' | 'clearance' | 'candidate')}
                className="bg-gray-800 border border-gray-700 text-gray-200 text-sm rounded px-3 py-1.5 focus:border-blue-500 outline-none"
              >
                <option value="none">ללא קיבוץ</option>
                <option value="candidate">שם מועמד</option>
                <option value="state">מצב</option>
                <option value="agent">סוכן</option>
                <option value="clearance">סיווג בטחוני</option>
              </select>
            </div>
          </div>

          {agentMatchesLoading ? (
            <div className="text-center py-12 text-gray-400">טוען…</div>
          ) : agentMatchesError ? (
            <div className="bg-red-900/30 border border-red-700 rounded-lg p-4 text-red-200">
              שגיאה: {String((agentMatchesError as Error).message)}
            </div>
          ) : (agentMatchesData?.matches.length ?? 0) === 0 ? (
            <div className="bg-gray-800 border border-gray-700 rounded-lg p-8 text-center text-gray-300">
              אין כרגע התאמות בטווח המבוקש.
            </div>
          ) : (
            <>
              {agentMatchesGroupBy === 'none' ? (
                <div className="bg-gray-800 rounded-lg border border-gray-700 overflow-hidden">
                <div className="overflow-x-auto">
                  <table className="w-full text-right text-sm">
                    <thead className="bg-gray-700 border-b border-gray-600 text-gray-200">
                      <tr>
                        {/* Clickable column headers — clicking the active column
                            toggles direction, clicking a different column resets
                            to that column's natural default (desc for score/date,
                            asc otherwise). */}
                        {(() => {
                          const cols: Array<{ key: SortKey; label: string; defaultDir: SortDir }> = [
                            { key: 'score',     label: 'ציון',           defaultDir: 'desc' },
                            { key: 'candidate', label: 'מועמד',          defaultDir: 'asc'  },
                            { key: 'job',       label: 'משרה',           defaultDir: 'asc'  },
                            { key: 'agent',     label: 'סוכן',           defaultDir: 'asc'  },
                            { key: 'state',     label: 'מצב',            defaultDir: 'asc'  },
                            { key: 'clearance', label: 'סיווג ביטחוני',  defaultDir: 'asc'  },
                            { key: 'date',      label: 'נוצר',           defaultDir: 'desc' },
                          ];
                          return cols.map((col) => {
                            const isActive = agentMatchesSortBy === col.key;
                            const arrow = !isActive ? '↕' : agentMatchesSortDir === 'asc' ? '▲' : '▼';
                            return (
                              <th key={col.key} className="px-4 py-3 font-semibold">
                                <button
                                  onClick={() => {
                                    if (isActive) {
                                      setAgentMatchesSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
                                    } else {
                                      setAgentMatchesSortBy(col.key);
                                      setAgentMatchesSortDir(col.defaultDir);
                                    }
                                    setAgentMatchesPage(0); // reset to first page
                                  }}
                                  className={`inline-flex items-center gap-1 hover:text-white transition ${
                                    isActive ? 'text-blue-300' : 'text-gray-200'
                                  }`}
                                  title={isActive ? 'הפוך כיוון מיון' : `מיין לפי ${col.label}`}
                                >
                                  <span>{col.label}</span>
                                  <span className="text-[10px] opacity-70">{arrow}</span>
                                </button>
                              </th>
                            );
                          });
                        })()}
                        {/* Client name + 4-digit Pipedrive job number — always
                            visible so the row is unambiguous. */}
                        <th className="px-4 py-3 font-semibold text-gray-200">שם לקוח</th>
                        <th className="px-4 py-3 font-semibold text-gray-200">מספר משרה</th>
                        {/* Non-sortable actions column — explicit "spec" button,
                            same affordance as the recruitment-agent screens. */}
                        <th className="px-4 py-3 font-semibold text-gray-200">מפרט</th>
                      </tr>
                    </thead>
                    <tbody>
                      {agentMatchesData!.matches.map((m) => {
                        const pct = Math.round(m.match_score * 100);
                        const scoreCls =
                          pct >= 90
                            ? 'bg-green-900 text-green-200'
                            : pct >= 80
                            ? 'bg-emerald-900 text-emerald-200'
                            : 'bg-yellow-900 text-yellow-200';
                        // Map backend clearance_match → indicator config.
                        const clrCfg: Record<ClearanceMatch, { icon: string; label: string; cls: string }> = {
                          match:    { icon: '🟢', label: 'תואם',     cls: 'border-green-700 text-green-200' },
                          partial:  { icon: '🟡', label: 'חלקי',     cls: 'border-yellow-700 text-yellow-200' },
                          mismatch: { icon: '🔴', label: 'לא תואם',  cls: 'border-red-700 text-red-200' },
                          unknown:  { icon: '⚪', label: 'לא ידוע',  cls: 'border-gray-600 text-gray-300' },
                        };
                        const cfg = clrCfg[m.clearance_match] || clrCfg.unknown;
                        // Build a DepartmentMatch-shaped object for the existing
                        // MatchDetailModal (it's the same modal used in agent screens).
                        const toDepartmentMatch = (): DepartmentMatch => ({
                          id: m.id,
                          candidateName: m.candidate_name,
                          candidateId: m.candidate_id,
                          jobId: m.job_id,
                          jobTitle: m.job_title,
                          company: m.company_name || 'Unknown Company',
                          phone: m.candidate_phone || undefined,
                          email: m.candidate_email || undefined,
                          status: m.current_state,
                          matchScore: m.match_score,
                          dateAdded: m.created_at,
                          lastActivity: m.updated_at,
                          matchReasoning: m.match_reasoning,
                          strengths: m.strengths,
                          gaps: m.gaps,
                          candidateClearance: m.candidate_clearance || undefined,
                          requiredClearance: m.required_clearance || undefined,
                          clearanceMatch: m.clearance_match,
                        });
                        return (
                          <tr key={m.id} className="border-b border-gray-700 hover:bg-gray-750 transition">
                            {/* Match score — clickable, opens MatchDetailModal */}
                            <td className="px-4 py-3">
                              <button
                                onClick={() => setSelectedAgentMatchForDetail(toDepartmentMatch())}
                                title="לפרטי ההתאמה (חוזקות, פערים, הסבר)"
                                className={`inline-block px-2 py-1 rounded text-xs font-bold cursor-pointer hover:ring-2 hover:ring-offset-1 hover:ring-offset-gray-800 hover:ring-white/40 transition ${scoreCls}`}
                              >
                                {pct}%
                              </button>
                            </td>
                            {/* Candidate name — clickable, opens candidate profile modal */}
                            <td className="px-4 py-3">
                              <button
                                onClick={() => setSelectedAgentCandidate(m)}
                                title="לפרופיל המועמד"
                                className="text-white font-semibold hover:text-blue-300 hover:underline transition text-right"
                              >
                                {m.candidate_name}
                              </button>
                            </td>
                            <td className="px-4 py-3 text-gray-300">{m.job_title}</td>
                            <td className="px-4 py-3 text-gray-300">
                              <span className="px-2 py-0.5 rounded bg-indigo-900/40 border border-indigo-700 text-indigo-200 text-xs font-semibold">
                                {agentNameHe(m.agent_code)}
                              </span>
                            </td>
                            <td className="px-4 py-3">
                              {(() => {
                                // Tiny inline state-badge. Kept local because the
                                // identical lookup in RecruiterMatchesPanel isn't
                                // exported and the badge is only used here.
                                const STATE_BADGES: Record<string, { label: string; cls: string }> = {
                                  found: { label: 'נמצא', cls: 'bg-gray-700 text-gray-200' },
                                  carmit_approved: { label: 'אושר ע״י כרמית', cls: 'bg-cyan-900 text-cyan-200' },
                                  carmit_rejected: { label: 'נדחה ע״י כרמית', cls: 'bg-red-900 text-red-200' },
                                  sent_to_tal: { label: 'ממתינה לטל', cls: 'bg-blue-900 text-blue-200' },
                                  tal_conversation: { label: 'בשיחה עם טל', cls: 'bg-indigo-900 text-indigo-200' },
                                  tal_approved: { label: 'אושר ע״י טל', cls: 'bg-green-900 text-green-200' },
                                  tal_rejected: { label: 'נדחה ע״י טל', cls: 'bg-red-900 text-red-200' },
                                  sent_to_elad: { label: 'ממתינה לאלעד', cls: 'bg-purple-900 text-purple-200' },
                                  elad_conversation: { label: 'בשיחה עם אלעד', cls: 'bg-fuchsia-900 text-fuchsia-200' },
                                  elad_approved: { label: 'אושר ע״י אלעד', cls: 'bg-emerald-900 text-emerald-200' },
                                  hired: { label: '🎉 הושמה', cls: 'bg-emerald-700 text-white' },
                                  placement_failed: { label: 'כשלון השמה', cls: 'bg-red-900 text-red-200' },
                                };
                                const stateCfg = STATE_BADGES[m.current_state] || { label: m.current_state, cls: 'bg-gray-700 text-gray-300' };
                                return (
                                  <span className={`px-2 py-0.5 rounded text-xs font-semibold ${stateCfg.cls}`}>
                                    {stateCfg.label}
                                  </span>
                                );
                              })()}
                              {/* Carmit's rejection reasoning — shown inline so the
                                  user understands WHY the match was rejected without
                                  opening a modal. Only rendered for rejected rows. */}
                              {m.carmit_decision?.decision === 'rejected' && (
                                <div className="mt-2 max-w-xs rounded border border-red-700/50 bg-red-900/20 p-2 text-[11px] text-red-200">
                                  <div className="font-semibold mb-1">❌ סיבת הדחייה של כרמית:</div>
                                  {m.carmit_decision.failed_gates.length > 0 ? (
                                    <ul className="space-y-1 list-disc pr-4">
                                      {m.carmit_decision.failed_gates.map((fg, i) => (
                                        <li key={i}>
                                          <span className="font-semibold">{GATE_LABELS_HE[fg.gate] || fg.gate}</span>
                                          {fg.reason ? <span className="text-red-300/90"> — {fg.reason}</span> : null}
                                        </li>
                                      ))}
                                    </ul>
                                  ) : (
                                    <p>{m.carmit_decision.reasoning || 'לא צוינה הנמקה'}</p>
                                  )}
                                </div>
                              )}
                            </td>
                            {/* Clearance column — two clearly labelled rows + outcome badge
                                so the user can tell at a glance what the candidate
                                has vs. what the job requires. */}
                            <td className="px-4 py-3 text-xs">
                              <div className="space-y-1">
                                <div className="flex items-center gap-1 text-gray-300">
                                  <span className="text-gray-500">👤 מועמד:</span>
                                  <span className="font-semibold">{m.candidate_clearance || 'לא צוין'}</span>
                                </div>
                                <div className="flex items-center gap-1 text-gray-300">
                                  <span className="text-gray-500">📋 נדרש:</span>
                                  <span className="font-semibold">{m.required_clearance || 'ללא דרישה'}</span>
                                </div>
                                <div className={`mt-1 inline-flex items-center gap-1 px-2 py-0.5 rounded border text-[10px] font-bold ${cfg.cls}`} title={`סטטוס סיווג: ${cfg.label}`}>
                                  <span>{cfg.icon}</span>
                                  <span>{cfg.label}</span>
                                </div>
                              </div>
                            </td>
                            <td className="px-4 py-3 text-xs text-gray-500">
                              {m.created_at ? new Date(m.created_at).toLocaleDateString('he-IL', {
                                day: '2-digit',
                                month: '2-digit',
                                year: 'numeric',
                              }) : '—'}
                            </td>
                            {/* Client name + Pipedrive job number */}
                            <td className="px-4 py-3 text-gray-300">{m.company_name || '—'}</td>
                            <td className="px-4 py-3 text-gray-400 font-mono">{m.pipedrive_deal_id ?? '—'}</td>
                            {/* Spec button — opens the same MatchDetailModal
                                (strengths / gaps / reasoning / clearance). */}
                            <td className="px-4 py-3">
                              <button
                                onClick={() => setSelectedAgentMatchForDetail(toDepartmentMatch())}
                                title="פרטי התאמה מלאים (חוזקות, פערים, הסבר)"
                                className="px-2 py-1 bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-semibold rounded transition"
                              >
                                מפרט
                              </button>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>

              {/* Pagination footer */}
              {(() => {
                const total = agentMatchesData!.total;
                const totalPages = Math.max(1, Math.ceil(total / AGENT_MATCHES_PAGE_SIZE));
                const firstIdx = agentMatchesPage * AGENT_MATCHES_PAGE_SIZE + 1;
                const lastIdx = Math.min(total, firstIdx + AGENT_MATCHES_PAGE_SIZE - 1);
                return (
                  <div className="flex items-center justify-between bg-gray-800 border border-gray-700 rounded-lg px-4 py-3">
                    <div className="text-sm text-gray-400">
                      מציג {firstIdx}–{lastIdx} מתוך {total}
                    </div>
                    <div className="flex items-center gap-2">
                      <button
                        onClick={() => setAgentMatchesPage((p) => Math.max(0, p - 1))}
                        disabled={agentMatchesPage === 0}
                        className="px-3 py-1.5 rounded text-sm font-semibold bg-gray-700 hover:bg-gray-600 text-white disabled:bg-gray-800 disabled:text-gray-600 disabled:cursor-not-allowed transition"
                      >
                        ◀ קודם
                      </button>
                      <span className="text-sm text-gray-300 px-3">
                        עמוד {agentMatchesPage + 1} מתוך {totalPages}
                      </span>
                      <button
                        onClick={() => setAgentMatchesPage((p) => p + 1)}
                        disabled={agentMatchesPage >= totalPages - 1}
                        className="px-3 py-1.5 rounded text-sm font-semibold bg-gray-700 hover:bg-gray-600 text-white disabled:bg-gray-800 disabled:text-gray-600 disabled:cursor-not-allowed transition"
                      >
                        הבא ▶
                      </button>
                    </div>
                  </div>
                );
              })()}
              </div>
              ) : (
                // Grouped view
                <div className="space-y-6">
                  {(() => {
                    const matches = agentMatchesData!.matches;
                    const groups: Record<string, typeof matches> = {};

                    matches.forEach(m => {
                      let groupKey = '';
                      if (agentMatchesGroupBy === 'state') {
                        groupKey = m.current_state || 'Unknown';
                      } else if (agentMatchesGroupBy === 'agent') {
                        groupKey = m.agent_code || 'Unknown';
                      } else if (agentMatchesGroupBy === 'clearance') {
                        groupKey = m.clearance_match || 'unknown';
                      } else if (agentMatchesGroupBy === 'candidate') {
                        groupKey = m.candidate_name || 'ללא שם';
                      }
                      if (!groups[groupKey]) groups[groupKey] = [];
                      groups[groupKey].push(m);
                    });

                    return Object.entries(groups).map(([groupName, groupMatches]) => (
                      <div key={groupName} className="bg-gray-800 rounded-lg border border-gray-700 p-4">
                        <h3 className="text-lg font-semibold text-white mb-4">
                          {agentMatchesGroupBy === 'state' && `מצב: ${stateLabelHe(groupName)}`}
                          {agentMatchesGroupBy === 'agent' && `סוכן: ${agentNameHe(groupName)}`}
                          {agentMatchesGroupBy === 'clearance' && `סיווג בטחוני: ${groupName}`}
                          {agentMatchesGroupBy === 'candidate' && `מועמד: ${groupName}`}
                          <span className="text-sm text-gray-400 ml-2">({groupMatches.length})</span>
                        </h3>
                        <div className="overflow-x-auto">
                          <table className="w-full text-right text-sm">
                            <thead className="bg-gray-700 border-b border-gray-600 text-gray-200">
                              <tr>
                                <th className="px-4 py-3 font-semibold">ציון</th>
                                <th className="px-4 py-3 font-semibold">מועמד</th>
                                <th className="px-4 py-3 font-semibold">משרה</th>
                                <th className="px-4 py-3 font-semibold">סוכן</th>
                                <th className="px-4 py-3 font-semibold">מצב</th>
                                <th className="px-4 py-3 font-semibold">סיווג ביטחוני</th>
                                <th className="px-4 py-3 font-semibold">נוצר</th>
                                <th className="px-4 py-3 font-semibold">שם לקוח</th>
                                <th className="px-4 py-3 font-semibold">מספר משרה</th>
                                <th className="px-4 py-3 font-semibold">מפרט</th>
                              </tr>
                            </thead>
                            <tbody>
                              {groupMatches.map((m) => {
                                const pct = Math.round(m.match_score * 100);
                                const scoreCls = pct >= 90 ? 'bg-green-900 text-green-200' : pct >= 80 ? 'bg-emerald-900 text-emerald-200' : 'bg-yellow-900 text-yellow-200';
                                const clrCfg: Record<ClearanceMatch, { icon: string; label: string; cls: string }> = {
                                  match: { icon: '🟢', label: 'תואם', cls: 'border-green-700 text-green-200' },
                                  partial: { icon: '🟡', label: 'חלקי', cls: 'border-yellow-700 text-yellow-200' },
                                  mismatch: { icon: '🔴', label: 'לא תואם', cls: 'border-red-700 text-red-200' },
                                  unknown: { icon: '⚪', label: 'לא ידוע', cls: 'border-gray-600 text-gray-300' },
                                };
                                const cfg = clrCfg[m.clearance_match] || clrCfg.unknown;
                                return (
                                  <tr key={m.id} className="border-b border-gray-700 hover:bg-gray-750 transition">
                                    <td className="px-4 py-3"><button onClick={() => setSelectedAgentMatchForDetail({ id: m.id, candidateName: m.candidate_name, candidateId: m.candidate_id, jobId: m.job_id, jobTitle: m.job_title, company: m.company_name || 'Unknown Company', phone: m.candidate_phone || undefined, email: m.candidate_email || undefined, status: m.current_state, matchScore: m.match_score, dateAdded: m.created_at, lastActivity: m.updated_at, matchReasoning: m.match_reasoning, strengths: m.strengths, gaps: m.gaps, candidateClearance: m.candidate_clearance || undefined, requiredClearance: m.required_clearance || undefined, clearanceMatch: m.clearance_match })} className={`inline-block px-2 py-1 rounded text-xs font-bold cursor-pointer ${scoreCls}`}>{pct}%</button></td>
                                    <td className="px-4 py-3"><button onClick={() => setSelectedAgentCandidate(m)} className="text-white font-semibold hover:text-blue-300 text-right">{m.candidate_name}</button></td>
                                    <td className="px-4 py-3 text-gray-300">{m.job_title}</td>
                                    <td className="px-4 py-3"><span className="px-2 py-0.5 rounded bg-indigo-900/40 border border-indigo-700 text-indigo-200 text-xs font-semibold">{agentNameHe(m.agent_code)}</span></td>
                                    <td className="px-4 py-3">
                                      <span className="px-2 py-0.5 rounded text-xs font-semibold bg-gray-700 text-gray-200">{stateLabelHe(m.current_state)}</span>
                                      {m.carmit_decision?.decision === 'rejected' && (
                                        <div className="mt-2 max-w-xs rounded border border-red-700/50 bg-red-900/20 p-2 text-[11px] text-red-200">
                                          <div className="font-semibold mb-1">❌ סיבת הדחייה של כרמית:</div>
                                          {m.carmit_decision.failed_gates.length > 0 ? (
                                            <ul className="space-y-1 list-disc pr-4">
                                              {m.carmit_decision.failed_gates.map((fg, i) => (
                                                <li key={i}>
                                                  <span className="font-semibold">{GATE_LABELS_HE[fg.gate] || fg.gate}</span>
                                                  {fg.reason ? <span className="text-red-300/90"> — {fg.reason}</span> : null}
                                                </li>
                                              ))}
                                            </ul>
                                          ) : (
                                            <p>{m.carmit_decision.reasoning || 'לא צוינה הנמקה'}</p>
                                          )}
                                        </div>
                                      )}
                                    </td>
                                    <td className="px-4 py-3 text-xs"><div className={`inline-flex items-center gap-1 px-2 py-0.5 rounded border font-bold ${cfg.cls}`}><span>{cfg.icon}</span><span>{cfg.label}</span></div></td>
                                    <td className="px-4 py-3 text-xs text-gray-500">{m.created_at ? new Date(m.created_at).toLocaleDateString('he-IL') : '—'}</td>
                                    <td className="px-4 py-3 text-gray-300 text-xs">{m.company_name || '—'}</td>
                                    <td className="px-4 py-3 text-gray-400 font-mono text-xs">{m.pipedrive_deal_id ?? '—'}</td>
                                    <td className="px-4 py-3"><button onClick={() => setSelectedAgentMatchForDetail({ id: m.id, candidateName: m.candidate_name, candidateId: m.candidate_id, jobId: m.job_id, jobTitle: m.job_title, company: m.company_name || 'Unknown Company', phone: m.candidate_phone || undefined, email: m.candidate_email || undefined, status: m.current_state, matchScore: m.match_score, dateAdded: m.created_at, lastActivity: m.updated_at, matchReasoning: m.match_reasoning, strengths: m.strengths, gaps: m.gaps, candidateClearance: m.candidate_clearance || undefined, requiredClearance: m.required_clearance || undefined, clearanceMatch: m.clearance_match })} title="פרטי התאמה מלאים" className="px-2 py-1 bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-semibold rounded transition">מפרט</button></td>
                                  </tr>
                                );
                              })}
                            </tbody>
                          </table>
                        </div>
                      </div>
                    ));
                  })()}
                </div>
              )}
            </>
          )}
        </div>
      )}

      {/* All Jobs Tab */}
      {activeTab === 'all-jobs' && (
        <div className="space-y-4">
          {/* Grouping dropdown for jobs */}
          <div className="flex items-center gap-3">
            <label className="text-sm text-gray-300 font-semibold">קיבוץ לפי:</label>
            <select
              value={allJobsGroupBy}
              onChange={(e) => setAllJobsGroupBy(e.target.value as 'none' | 'priority' | 'assigned_agent' | 'status')}
              className="bg-gray-800 border border-gray-700 text-gray-200 text-sm rounded px-3 py-1.5 focus:border-blue-500 outline-none"
            >
              <option value="none">ללא קיבוץ</option>
              <option value="priority">עדיפות</option>
              <option value="assigned_agent">סוכן מוקצה</option>
              <option value="status">סטטוס</option>
            </select>
          </div>

          {allJobsLoading ? (
            <div className="text-center py-8 text-gray-400">טוען...</div>
          ) : ((allJobsData?.jobs.length || 0) > 0) ? (
            allJobsGroupBy === 'none' ? (
              <div className="bg-gray-800 rounded-lg border border-gray-700 overflow-hidden">
                <div className="overflow-x-auto">
                  <table className="w-full">
                <thead>
                  <tr className="border-b border-gray-700">
                    <th className="text-right px-4 py-3 text-gray-300 font-semibold">כותרת משרה</th>
                    <th className="text-right px-4 py-3 text-gray-300 font-semibold">מספר משרה</th>
                    <th className="text-right px-4 py-3 text-gray-300 font-semibold">עדיפות</th>
                    <th className="text-right px-4 py-3 text-gray-300 font-semibold">ארגון</th>
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
                      <td className="px-4 py-3 text-gray-400 font-mono text-sm">{job.pipedrive_deal_id ?? '—'}</td>
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
                        {job.organization_name || '-'}
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
              </div>
            ) : (
              // Grouped view for jobs
              <div className="space-y-6">
                {(() => {
                  const jobs = allJobsData!.jobs;
                  const groups: Record<string, typeof jobs> = {};

                  jobs.forEach(job => {
                    let groupKey = '';
                    if (allJobsGroupBy === 'priority') {
                      groupKey = `עדיפות ${job.priority}`;
                    } else if (allJobsGroupBy === 'assigned_agent') {
                      groupKey = job.assigned_agent_name || 'לא הוקצה';
                    } else if (allJobsGroupBy === 'status') {
                      groupKey = job.status || 'Unknown';
                    }
                    if (!groups[groupKey]) groups[groupKey] = [];
                    groups[groupKey].push(job);
                  });

                  return Object.entries(groups).map(([groupName, groupJobs]) => (
                    <div key={groupName} className="bg-gray-800 rounded-lg border border-gray-700 p-4">
                      <h3 className="text-lg font-semibold text-white mb-4">
                        {groupName}
                        <span className="text-sm text-gray-400 ml-2">({groupJobs.length})</span>
                      </h3>
                      <div className="overflow-x-auto">
                        <table className="w-full text-sm">
                          <thead className="bg-gray-700 border-b border-gray-600 text-gray-300">
                            <tr>
                              <th className="text-right px-4 py-3 font-semibold">כותרת משרה</th>
                              <th className="text-right px-4 py-3 font-semibold">מספר משרה</th>
                              <th className="text-right px-4 py-3 font-semibold">עדיפות</th>
                              <th className="text-right px-4 py-3 font-semibold">ארגון</th>
                              <th className="text-right px-4 py-3 font-semibold">איש קשר</th>
                              <th className="text-right px-4 py-3 font-semibold">סוכן מוקצה</th>
                              <th className="text-right px-4 py-3 font-semibold">סטטוס</th>
                              <th className="text-right px-4 py-3 font-semibold">תאריך יצירה</th>
                              <th className="text-right px-4 py-3 font-semibold">פעולות</th>
                            </tr>
                          </thead>
                          <tbody>
                            {groupJobs.map((job) => (
                              <tr key={job.id} className="border-b border-gray-700 hover:bg-gray-750 transition">
                                <td className="px-4 py-3 text-white">{job.title}</td>
                                <td className="px-4 py-3 text-gray-400 font-mono text-xs">{job.pipedrive_deal_id ?? '—'}</td>
                                <td className="px-4 py-3"><span className={`px-2 py-1 rounded text-xs font-semibold ${job.priority === 1 ? 'bg-red-900 text-red-300' : job.priority <= 2 ? 'bg-orange-900 text-orange-300' : job.priority <= 3 ? 'bg-yellow-900 text-yellow-300' : 'bg-gray-700 text-gray-300'}`}>{job.priority}</span></td>
                                <td className="px-4 py-3 text-gray-300 text-sm">{job.organization_name || '-'}</td>
                                <td className="px-4 py-3 text-gray-300 text-sm">{job.contact_person_name || '-'}</td>
                                <td className="px-4 py-3">{job.assigned_agent_name ? (<span className="px-2 py-1 bg-green-900 text-green-300 rounded text-xs font-semibold">{job.assigned_agent_name}</span>) : (<span className="text-gray-500 text-xs">לא הוקצה</span>)}</td>
                                <td className="px-4 py-3"><span className={`px-2 py-1 rounded text-xs ${job.status === 'open' ? 'bg-blue-900 text-blue-300' : job.status === 'closed' ? 'bg-gray-700 text-gray-300' : 'bg-gray-600 text-gray-300'}`}>{job.status}</span></td>
                                <td className="px-4 py-3 text-gray-400 text-sm">{new Date(job.created_at).toLocaleDateString('he-IL')}</td>
                                <td className="px-4 py-3"><button onClick={() => { setJobToOverride(job); setSelectedNewAgent(''); setOverrideError(''); setShowOverrideModal(true); }} className="px-3 py-1 bg-orange-600 hover:bg-orange-700 text-white rounded text-xs font-semibold transition">⚙️ עדכן</button></td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  ));
                })()}
              </div>
            )
          ) : (
            <div className="text-center py-8 text-gray-400">אין משרות</div>
          )}
        </div>
      )}

      {/* === העברתי לטל === */}
      {/* All matches that have crossed Tal's stage of the state machine.
          Sub-tabs: queue (sent_to_tal + tal_conversation) vs history
          (tal_approved + tal_rejected). Shared component is also used on
          /recruiting/tal so both views always stay in sync. */}
      {activeTab === 'sent-to-tal' && (
        <div className="space-y-4">
          <div>
            <h2 className="text-2xl font-bold text-white">📤 העברתי לטל</h2>
            <p className="text-sm text-gray-400">
              כל ההתאמות בסטטוס "ממתינה לטל" (וכן בשיחה / נמסר לאדם) — ללא סף ציון וללא סינון לפי סוכן.
              זהו המספר המלא של התאמות שעברו לטל. מבוסס על מכונת המצבים.
            </p>
          </div>
          <RecruiterMatchesPanel recruiter="tal" />
        </div>
      )}

      {/* === העברתי לאלעד === */}
      {/* All matches that have reached Elad's stage (client-side placement).
          Sub-tabs: queue (sent_to_elad + elad_conversation) vs history
          (elad_approved + hired + placement_failed). */}
      {activeTab === 'sent-to-elad' && (
        <div className="space-y-4">
          <div>
            <h2 className="text-2xl font-bold text-white">📤 העברתי לאלעד</h2>
            <p className="text-sm text-gray-400">
              התאמות שעברו לאלעד להשמה אצל הלקוח (שיחה עם הלקוח). מבוסס על מכונת המצבים.
            </p>
          </div>
          <RecruiterMatchesPanel recruiter="elad" />
        </div>
      )}

      {/* Match-detail modal — opened by clicking the score % in the
          התאמות-מסוכני-הגיוס tab. Reuses the same modal the per-agent
          screens use so the UX is consistent across dashboards. */}
      <MatchDetailModal
        match={selectedAgentMatchForDetail}
        onClose={() => setSelectedAgentMatchForDetail(null)}
      />

      {/* Candidate-profile modal — opened by clicking the candidate name
          in the התאמות-מסוכני-הגיוס tab. All fields come straight from
          the agent-matches payload (no extra fetch). */}
      {selectedAgentCandidate && (
        <div
          className="fixed inset-0 bg-black/70 backdrop-blur-sm z-50 flex items-center justify-center p-4"
          onClick={() => setSelectedAgentCandidate(null)}
        >
          <div
            className="bg-gray-900 border border-gray-700 rounded-xl w-full max-w-2xl max-h-[90vh] overflow-y-auto shadow-2xl"
            onClick={(e) => e.stopPropagation()}
            dir="rtl"
          >
            <div className="sticky top-0 bg-gray-900 border-b border-gray-700 px-6 py-4 flex items-start justify-between">
              <div>
                <h2 className="text-xl font-bold text-white">👤 {selectedAgentCandidate.candidate_name}</h2>
                <p className="text-sm text-gray-400 mt-1">פרופיל מועמד</p>
              </div>
              <button
                onClick={() => setSelectedAgentCandidate(null)}
                className="text-gray-400 hover:text-white text-2xl leading-none px-2"
                aria-label="סגור"
              >
                ×
              </button>
            </div>

            <div className="px-6 py-5 space-y-5 text-sm">
              {/* Quick facts row */}
              <div className="grid grid-cols-2 gap-3">
                {selectedAgentCandidate.candidate_years != null && (
                  <div className="bg-gray-800 border border-gray-700 rounded p-3">
                    <div className="text-xs text-gray-400">שנות ניסיון</div>
                    <div className="text-white font-bold text-lg mt-1">{selectedAgentCandidate.candidate_years}</div>
                  </div>
                )}
                {selectedAgentCandidate.candidate_location && (
                  <div className="bg-gray-800 border border-gray-700 rounded p-3">
                    <div className="text-xs text-gray-400">מיקום</div>
                    <div className="text-white font-semibold mt-1">📍 {selectedAgentCandidate.candidate_location}</div>
                  </div>
                )}
                {selectedAgentCandidate.candidate_clearance && (
                  <div className="bg-gray-800 border border-gray-700 rounded p-3">
                    <div className="text-xs text-gray-400">סיווג ביטחוני</div>
                    <div className="text-white font-semibold mt-1">🔒 {selectedAgentCandidate.candidate_clearance}</div>
                  </div>
                )}
                {selectedAgentCandidate.candidate_language && (
                  <div className="bg-gray-800 border border-gray-700 rounded p-3">
                    <div className="text-xs text-gray-400">שפה</div>
                    <div className="text-white font-semibold mt-1">{selectedAgentCandidate.candidate_language}</div>
                  </div>
                )}
              </div>

              {/* Contact */}
              {(selectedAgentCandidate.candidate_email || selectedAgentCandidate.candidate_phone) && (
                <section>
                  <h3 className="text-sm font-semibold text-gray-300 mb-2">פרטי קשר</h3>
                  <div className="bg-gray-800 border border-gray-700 rounded p-3 space-y-1 text-gray-200">
                    {selectedAgentCandidate.candidate_email && <div>📧 {selectedAgentCandidate.candidate_email}</div>}
                    {selectedAgentCandidate.candidate_phone && <div>📱 {selectedAgentCandidate.candidate_phone}</div>}
                  </div>
                </section>
              )}

              {/* Skills */}
              {selectedAgentCandidate.candidate_key_skills.length > 0 && (
                <section>
                  <h3 className="text-sm font-semibold text-gray-300 mb-2">
                    כישורים מרכזיים ({selectedAgentCandidate.candidate_key_skills.length})
                  </h3>
                  <div className="flex flex-wrap gap-2">
                    {selectedAgentCandidate.candidate_key_skills.map((skill, i) => (
                      <span
                        key={i}
                        className="px-2 py-1 rounded bg-blue-900/40 border border-blue-700 text-blue-200 text-xs font-semibold"
                      >
                        {skill}
                      </span>
                    ))}
                  </div>
                </section>
              )}

              {/* Education — top_education is a JSONB dict
                  (institution / degree / field / start_year / end_year …).
                  We coerce it to display-friendly text here. */}
              {(() => {
                const raw = selectedAgentCandidate.candidate_top_education;
                if (!raw) return null;
                if (typeof raw === 'string') {
                  return (
                    <section>
                      <h3 className="text-sm font-semibold text-gray-300 mb-2">🎓 השכלה</h3>
                      <p className="bg-gray-800 border border-gray-700 rounded p-3 text-gray-200">{raw}</p>
                    </section>
                  );
                }
                if (typeof raw === 'object') {
                  const e = raw as Record<string, unknown>;
                  const degree = e.degree ? String(e.degree) : '';
                  const field = e.field ? String(e.field) : '';
                  const institution = e.institution ? String(e.institution) : '';
                  const years = [e.start_year, e.end_year].filter(Boolean).join('–');
                  const line1 = [degree, field].filter(Boolean).join(' ב-');
                  const line2 = [institution, years].filter(Boolean).join(' · ');
                  if (!line1 && !line2) return null;
                  return (
                    <section>
                      <h3 className="text-sm font-semibold text-gray-300 mb-2">🎓 השכלה</h3>
                      <div className="bg-gray-800 border border-gray-700 rounded p-3 text-gray-200">
                        {line1 && <div className="font-semibold">{line1}</div>}
                        {line2 && <div className="text-sm text-gray-400">{line2}</div>}
                      </div>
                    </section>
                  );
                }
                return null;
              })()}

              {/* Experience — each item is a JSONB dict with keys
                  position, company, duration, start_date, end_date,
                  description, location … We pick a few and render a card. */}
              {selectedAgentCandidate.candidate_experiences.length > 0 && (
                <section>
                  <h3 className="text-sm font-semibold text-gray-300 mb-2">
                    💼 ניסיון ({selectedAgentCandidate.candidate_experiences.length})
                  </h3>
                  <ul className="space-y-2">
                    {selectedAgentCandidate.candidate_experiences.slice(0, 5).map((exp, i) => {
                      if (typeof exp === 'string') {
                        return (
                          <li key={i} className="bg-gray-800 border border-gray-700 rounded p-3 text-gray-200">
                            {exp}
                          </li>
                        );
                      }
                      const e = (exp || {}) as Record<string, unknown>;
                      const position = e.position ? String(e.position) : (e.title ? String(e.title) : '');
                      const company = e.company ? String(e.company) : '';
                      const duration = e.duration
                        ? String(e.duration)
                        : [e.start_date, e.end_date].filter(Boolean).join('–');
                      const description = e.description ? String(e.description) : '';
                      return (
                        <li key={i} className="bg-gray-800 border border-gray-700 rounded p-3 text-gray-200">
                          <div className="font-semibold">
                            {position || '—'}
                            {company && <span className="text-gray-400 font-normal"> · {company}</span>}
                          </div>
                          {duration && <div className="text-xs text-gray-500 mt-0.5">{duration}</div>}
                          {description && <div className="text-sm text-gray-300 mt-1">{description}</div>}
                        </li>
                      );
                    })}
                    {selectedAgentCandidate.candidate_experiences.length > 5 && (
                      <li className="text-xs text-gray-500 italic">
                        ועוד {selectedAgentCandidate.candidate_experiences.length - 5}…
                      </li>
                    )}
                  </ul>
                </section>
              )}

              {/* The match this candidate is shown under — quick link to detail modal */}
              <section className="bg-gray-800/50 border border-gray-700 rounded p-3">
                <div className="text-xs text-gray-400 mb-1">בהתאמה זו</div>
                <div className="flex items-center justify-between gap-3">
                  <div className="text-gray-200">
                    <span className="font-semibold">{selectedAgentCandidate.job_title}</span>
                    <span className="text-gray-500 mx-2">·</span>
                    <span className="text-gray-400">סוכן: {agentNameHe(selectedAgentCandidate.agent_code)}</span>
                  </div>
                  <button
                    onClick={() => {
                      // Switch from candidate modal → match-detail modal
                      const m = selectedAgentCandidate;
                      setSelectedAgentCandidate(null);
                      setSelectedAgentMatchForDetail({
                        id: m.id,
                        candidateName: m.candidate_name,
                        candidateId: m.candidate_id,
                        jobId: m.job_id,
                        jobTitle: m.job_title,
                        company: m.company_name || 'Unknown Company',
                        phone: m.candidate_phone || undefined,
                        email: m.candidate_email || undefined,
                        status: m.current_state,
                        matchScore: m.match_score,
                        dateAdded: m.created_at,
                        lastActivity: m.updated_at,
                        matchReasoning: m.match_reasoning,
                        strengths: m.strengths,
                        gaps: m.gaps,
                        candidateClearance: m.candidate_clearance || undefined,
                        requiredClearance: m.required_clearance || undefined,
                        clearanceMatch: m.clearance_match,
                      });
                    }}
                    className="text-xs bg-blue-700 hover:bg-blue-600 text-white px-3 py-1.5 rounded font-semibold"
                  >
                    לפרטי ההתאמה →
                  </button>
                </div>
              </section>
            </div>

            <div className="sticky bottom-0 bg-gray-900 border-t border-gray-700 px-6 py-3 flex justify-end">
              <button
                onClick={() => setSelectedAgentCandidate(null)}
                className="px-4 py-2 bg-gray-700 hover:bg-gray-600 text-white rounded transition text-sm"
              >
                סגור
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

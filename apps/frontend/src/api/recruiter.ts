/**
 * Recruiter API client utilities
 * Fetch functions for recruiter dashboard endpoints
 */

const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";

export interface Match {
  id: string;
  candidateName: string;
  jobTitle: string;
  company: string;
  matchScore: number;
  status: string;
  state: string;
  createdAt: string;
  lastActivity?: string;
  candidateId: string;
  jobId: string;
  daysInStage: number;
}

export interface StatusMetrics {
  pendingTal: number;
  inConversationTal: number;
  awaitingElad: number;
  inConversationElad: number;
  hired: number;
  failed: number;
}

export interface MatchesResponse {
  matches: Match[];
  total: number;
  page: number;
  limit: number;
}

/**
 * Fetch recruiter status metrics
 */
export async function fetchRecruiterStatus(): Promise<StatusMetrics> {
  const response = await fetch(`${API_BASE}/admin/recruiter/status`);

  if (!response.ok) {
    throw new Error(`Failed to fetch recruiter status: ${response.statusText}`);
  }

  const data = await response.json();

  // Map snake_case from API to camelCase for frontend
  return {
    pendingTal: data.pending_tal,
    inConversationTal: data.in_conversation_tal,
    awaitingElad: data.awaiting_elad,
    inConversationElad: data.in_conversation_elad,
    hired: data.hired,
    failed: data.failed,
  };
}

/**
 * Fetch matches for recruiter queues
 */
export async function fetchRecruiterMatches(
  tab: string,
  limit: number = 50,
  page: number = 1
): Promise<MatchesResponse> {
  const params = new URLSearchParams({
    tab,
    limit: String(limit),
    page: String(page),
  });

  const response = await fetch(
    `${API_BASE}/admin/recruiter/matches?${params.toString()}`
  );

  if (!response.ok) {
    throw new Error(`Failed to fetch recruiter matches: ${response.statusText}`);
  }

  const data = await response.json();

  // Map snake_case to camelCase
  return {
    matches: (data.matches || []).map((match: any) => ({
      id: match.id,
      candidateName: match.candidate_name,
      jobTitle: match.job_title,
      company: match.company,
      matchScore: match.match_score,
      status: match.status,
      state: match.state,
      createdAt: match.created_at,
      lastActivity: match.last_activity,
      candidateId: match.candidate_id,
      jobId: match.job_id,
      daysInStage: match.days_in_stage,
    })),
    total: data.total,
    page: data.page,
    limit: data.limit,
  };
}

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
  pipedriveDealId?: number; // 4-digit Pipedrive job number
  matchScore: number;
  status: string;
  state: string;
  createdAt: string;
  lastActivity?: string;
  candidateId: string;
  jobId: string;
  daysInStage: number;
  geographicMismatch?: boolean;
  geographicMismatchReason?: string;
  isStarred?: boolean;
}

export interface StatusMetrics {
  pendingCarmit: number;
  carmitApproved: number;
  carmitRejected: number;
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

export interface ConversationMessage {
  id: string;
  direction: "inbound" | "outbound";
  text?: string;
  createdAt: string;
}

export interface ConversationInfo {
  id: string;
  matchId: string;
  recruiter: string;
  startedAt: string;
  endedAt?: string;
  status: string;
  messages: ConversationMessage[];
  notes?: string;
}

export interface CandidateMatch {
  id: string;
  candidateId: string;
  candidateName: string;
  jobId: string;
  jobTitle: string;
  organizationName?: string;
  pipedriveDealId?: number; // 4-digit Pipedrive job number
  matchScore: number;
  currentState: string;
  matchedByAgentCode: string;
  matchReasoning?: string;
  createdAt: string;
  evaluatedScoreRaw?: number;
  geographicMismatch?: boolean;
  geographicMismatchReason?: string;
}

export interface AllCandidateMatchesResponse {
  matches: CandidateMatch[];
  total: number;
  jobs: Array<{ id: string; title: string }>;
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
    pendingCarmit: data.pending_carmit,
    carmitApproved: data.carmit_approved,
    carmitRejected: data.carmit_rejected,
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
  page: number = 1,
  favoritesOnly: boolean = false
): Promise<MatchesResponse> {
  const params = new URLSearchParams({
    tab,
    limit: String(limit),
    page: String(page),
  });
  if (favoritesOnly) {
    params.set("favorites_only", "true");
  }

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
      pipedriveDealId: match.pipedrive_deal_id ?? undefined,
      matchScore: match.match_score,
      status: match.status,
      state: match.state,
      createdAt: match.created_at,
      lastActivity: match.last_activity,
      candidateId: match.candidate_id,
      jobId: match.job_id,
      daysInStage: match.days_in_stage,
      geographicMismatch: match.geographic_mismatch ?? false,
      geographicMismatchReason: match.geographic_mismatch_reason ?? undefined,
      isStarred: match.is_starred ?? false,
    })),
    total: data.total,
    page: data.page,
    limit: data.limit,
  };
}

export type MatchAction =
  | "activate"
  | "reject"
  | "wait"
  | "hand_to_human"
  | "return_from_human"
  | "mark_company_employee"
  | "mark_company_client";

/**
 * Perform an action on a match (activate, reject, wait, hand_to_human, return_from_human)
 */
export async function performMatchAction(
  matchId: string,
  action: MatchAction,
  notes?: string
): Promise<any> {
  const response = await fetch(`${API_BASE}/admin/recruiter/${matchId}/action`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      action,
      notes: notes || null,
    }),
  });

  if (!response.ok) {
    throw new Error(`Failed to perform match action: ${response.statusText}`);
  }

  return response.json();
}

/**
 * Star/unstar a match as a favorite. Works at any stage (Carmit/Tal/Elad).
 */
export async function setMatchFavorite(
  matchId: string,
  isStarred: boolean
): Promise<any> {
  const response = await fetch(
    `${API_BASE}/admin/recruiter/${matchId}/favorite`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ is_starred: isStarred }),
    }
  );

  if (!response.ok) {
    throw new Error(`Failed to set match favorite: ${response.statusText}`);
  }

  return response.json();
}

/**
 * Get conversation details for a match
 */
export async function fetchMatchConversation(
  matchId: string
): Promise<ConversationInfo> {
  const response = await fetch(
    `${API_BASE}/admin/recruiter/${matchId}/conversation`
  );

  if (!response.ok) {
    throw new Error(`Failed to fetch conversation: ${response.statusText}`);
  }

  const data = await response.json();

  return {
    id: data.id,
    matchId: data.matchId,
    recruiter: data.recruiter,
    startedAt: data.startedAt,
    endedAt: data.endedAt,
    status: data.status,
    messages: data.messages || [],
    notes: data.notes,
  };
}

/**
 * Fetch the full match breakdown (reasoning, strengths, gaps, clearance) for a
 * single match — the same "why this match" view the agent/Carmit screens show.
 * Returned in the DepartmentMatch shape so MatchDetailModal can render it.
 */
export async function fetchMatchDetail(matchId: string): Promise<import("./recruitment-departments").DepartmentMatch> {
  const response = await fetch(`${API_BASE}/admin/recruiter/${matchId}/detail`);

  if (!response.ok) {
    throw new Error(`Failed to fetch match detail: ${response.statusText}`);
  }

  const d = await response.json();

  return {
    id: d.id,
    candidateName: d.candidate_name,
    candidateId: d.candidate_id ?? undefined,
    jobId: d.job_id,
    jobTitle: d.job_title,
    company: d.company || "",
    phone: d.phone ?? undefined,
    email: d.email ?? undefined,
    status: "",
    matchScore: d.match_score,
    dateAdded: "",
    matchReasoning: d.match_reasoning ?? undefined,
    strengths: d.strengths || [],
    gaps: d.gaps || [],
    candidateClearance: d.candidate_clearance ?? undefined,
    requiredClearance: d.required_clearance ?? undefined,
    clearanceMatch: d.clearance_match || "unknown",
    geographicMismatch: d.geographic_mismatch ?? false,
    geographicMismatchReason: d.geographic_mismatch_reason ?? undefined,
    carmitReview: d.carmit_review ?? undefined,
  };
}

/**
 * List conversations for a recruiter
 */
export async function fetchRecruiterConversations(
  recruiter: "tal" | "elad",
  limit: number = 50,
  page: number = 1
): Promise<any> {
  const params = new URLSearchParams({
    recruiter,
    limit: String(limit),
    page: String(page),
  });

  const response = await fetch(
    `${API_BASE}/admin/recruiter/conversations/list?${params.toString()}`
  );

  if (!response.ok) {
    throw new Error(
      `Failed to fetch recruiter conversations: ${response.statusText}`
    );
  }

  return response.json();
}

/**
 * Fetch all candidate matches with reasoning (decision matrix)
 */
export async function fetchAllCandidateMatches(
  jobId?: string,
  agentCode?: string,
  limit: number = 100,
  page: number = 1
): Promise<AllCandidateMatchesResponse> {
  const params = new URLSearchParams({
    limit: String(limit),
    page: String(page),
  });

  if (jobId) {
    params.append("job_id", jobId);
  }

  if (agentCode) {
    params.append("agent_code", agentCode);
  }

  const response = await fetch(
    `${API_BASE}/admin/recruiter/all-candidate-matches?${params.toString()}`
  );

  if (!response.ok) {
    throw new Error(`Failed to fetch candidate matches: ${response.statusText}`);
  }

  const data = await response.json();

  // Map snake_case from API to camelCase for frontend
  return {
    matches: (data.matches || []).map((m: any) => ({
      id: m.id,
      candidateId: m.candidate_id,
      candidateName: m.candidate_name,
      jobId: m.job_id,
      jobTitle: m.job_title,
      organizationName: m.organization_name,
      pipedriveDealId: m.pipedrive_deal_id ?? undefined,
      matchScore: m.match_score,
      currentState: m.current_state,
      matchedByAgentCode: m.matched_by_agent_code,
      matchReasoning: m.match_reasoning,
      createdAt: m.created_at,
      evaluatedScoreRaw: m.evaluated_score_raw,
      geographicMismatch: m.geographic_mismatch ?? false,
      geographicMismatchReason: m.geographic_mismatch_reason ?? undefined,
    })),
    total: data.total,
    jobs: data.jobs || [],
  };
}

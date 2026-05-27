/**
 * Recruitment Departments API client utilities
 * Fetch functions for agent matches, status updates, and department stats
 */

const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";

export type ClearanceMatch = "match" | "partial" | "mismatch" | "unknown";

export interface DepartmentMatch {
  id: string;
  candidateName: string;
  candidateId?: string;
  jobId: string;
  jobTitle: string;
  company: string;
  phone?: string;
  email?: string;
  status: string;
  matchScore: number;
  dateAdded: string;
  lastActivity?: string;
  notes?: string;
  // Match-quality detail (already produced by the agent_matching worker)
  matchReasoning?: string;
  strengths?: string[];
  gaps?: string[];
  // Security-clearance comparison
  candidateClearance?: string;
  candidateClearanceConfidence?: number;
  requiredClearance?: string;
  clearanceMatch?: ClearanceMatch;
}

export interface AssignedJob {
  id: string;
  job_title: string;
  job_description?: string;
  assigned_agent_code: string;
  priority: number;
  status: string;
  match_count: number;
  approved_count: number;
  found_count: number;
  organization_name?: string;
  contact_person_name?: string;
  // ISO timestamps
  created_at?: string;        // תאריך הגעת המשרה
  assigned_at?: string;       // תאריך ההקצאה (≈ jobs.updated_at — best proxy)
  deadline?: string;          // דדליין (מ-Pipedrive)
  pipedrive_org_id?: number;
  pipedrive_person_id?: number;
}

export interface DepartmentStats {
  totalMatches: number;
  inProgress: number;
  approved: number;
  rejected: number;
  approvalRate: number;
}

/**
 * Fetch jobs assigned to a specific department/agent
 */
export async function fetchAssignedJobs(
  departmentCode: string
): Promise<AssignedJob[]> {
  const response = await fetch(
    `${API_BASE}/admin/departments/${departmentCode}/assigned-jobs`
  );

  if (!response.ok) {
    throw new Error(`Failed to fetch assigned jobs: ${response.statusText}`);
  }

  return response.json();
}

/**
 * Fetch matches for a specific department/agent
 */
export async function fetchDepartmentMatches(
  departmentCode: string,
  status?: string,
  limit: number = 100,
  offset: number = 0
): Promise<DepartmentMatch[]> {
  const params = new URLSearchParams();
  params.append("limit", String(limit));
  params.append("offset", String(offset));
  if (status) {
    params.append("status", status);
  }

  const response = await fetch(
    `${API_BASE}/admin/departments/${departmentCode}/matches?${params.toString()}`
  );

  if (!response.ok) {
    throw new Error(`Failed to fetch department matches: ${response.statusText}`);
  }

  return response.json();
}

/**
 * Update match status with notes
 */
export async function updateMatchStatus(
  departmentCode: string,
  matchId: string,
  newStatus: string,
  notes?: string
): Promise<any> {
  const response = await fetch(
    `${API_BASE}/admin/departments/${departmentCode}/matches/${matchId}/status`,
    {
      method: "PUT",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        status: newStatus,
        notes: notes || "",
      }),
    }
  );

  if (!response.ok) {
    throw new Error(`Failed to update match status: ${response.statusText}`);
  }

  return response.json();
}

/**
 * Get statistics for a department
 */
export async function getDepartmentStats(
  departmentCode: string
): Promise<DepartmentStats> {
  const response = await fetch(`${API_BASE}/admin/departments/${departmentCode}/stats`);

  if (!response.ok) {
    throw new Error(`Failed to fetch department stats: ${response.statusText}`);
  }

  return response.json();
}

/**
 * Approve a match (move to next stage)
 */
export async function approveMatch(
  departmentCode: string,
  matchId: string,
  notes?: string
): Promise<any> {
  return updateMatchStatus(departmentCode, matchId, "approved", notes);
}

/**
 * Reject a match
 */
export async function rejectMatch(
  departmentCode: string,
  matchId: string,
  rejectionReason?: string
): Promise<any> {
  return updateMatchStatus(departmentCode, matchId, "rejected", rejectionReason);
}

/**
 * Record conversation with candidate
 */
export async function recordConversation(
  departmentCode: string,
  matchId: string,
  conversationNotes: string
): Promise<any> {
  const response = await fetch(
    `${API_BASE}/admin/departments/${departmentCode}/matches/${matchId}/conversation`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        notes: conversationNotes,
        timestamp: new Date().toISOString(),
      }),
    }
  );

  if (!response.ok) {
    throw new Error(`Failed to record conversation: ${response.statusText}`);
  }

  return response.json();
}

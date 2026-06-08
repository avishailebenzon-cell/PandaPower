/**
 * Agent test-conversation client — injects a deliberate TEST match into the
 * matches table for Tal / Elad so the operator can exercise the full
 * activate → conversation pipeline against a test phone number.
 */

const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";

export interface CreateTestMatchPayload {
  recruiter: "tal" | "elad";
  phone: string;
  contact_name: string;
  job_title: string;
  /** The real candidate presented to the client (Elad bypass-Tal flow). */
  candidate_name?: string;
  organization_name?: string;
  job_location?: string;
  job_security_clearance?: string;
  candidate_clearance?: string;
  job_description?: string;
  job_qualifications?: string;
  match_score?: number;
  match_reasoning?: string;
}

export interface CreateTestMatchResult {
  match_id: string;
  recruiter: string;
  state: string;
  queue_path: string;
}

/** A real Carmit-approved match the operator can hand to Elad for a test. */
export interface ApprovedMatchItem {
  match_id: string;
  candidate_name: string;
  candidate_clearance?: string | null;
  job_title: string;
  organization_name?: string | null;
  job_location?: string | null;
  job_security_clearance?: string | null;
  job_description?: string | null;
  job_qualifications?: string | null;
  match_score: number; // 0-100
  match_reasoning?: string | null;
  current_state: string;
}

export async function listApprovedMatches(
  limit = 50
): Promise<ApprovedMatchItem[]> {
  const res = await fetch(
    `${API_BASE}/admin/agent-test/approved-matches?limit=${limit}`
  );
  if (!res.ok) {
    let detail = "Failed to load approved matches";
    try {
      detail = (await res.json()).detail || detail;
    } catch {
      /* ignore */
    }
    throw new Error(detail);
  }
  return res.json();
}

export async function createTestMatch(
  payload: CreateTestMatchPayload
): Promise<CreateTestMatchResult> {
  const res = await fetch(`${API_BASE}/admin/agent-test/create-match`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    let detail = "Failed to create test match";
    try {
      detail = (await res.json()).detail || detail;
    } catch {
      /* ignore */
    }
    throw new Error(detail);
  }
  return res.json();
}

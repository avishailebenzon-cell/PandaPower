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

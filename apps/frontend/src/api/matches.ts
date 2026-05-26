/**
 * Match API endpoints
 */

export interface StateHistoryEntry {
  from_state: string;
  to_state: string;
  created_at: string;
  details?: Record<string, any>;
}

export interface MatchHistoryResponse {
  matchId: string;
  candidateName: string;
  jobTitle: string;
  currentState: string;
  stateHistory: StateHistoryEntry[];
}

/**
 * Fetch complete state history for a match
 */
export async function fetchMatchHistory(matchId: string): Promise<MatchHistoryResponse> {
  const response = await fetch(`/api/admin/matches/${matchId}/history`);
  if (!response.ok) {
    throw new Error(`Failed to fetch match history: ${response.statusText}`);
  }
  return response.json();
}

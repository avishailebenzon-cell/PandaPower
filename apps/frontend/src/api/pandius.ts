/**
 * Pandius API client — candidate-facing WhatsApp agent.
 * Mirrors the Pandi client, over /admin/pandius/* endpoints.
 */

const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";

export interface PandiusClient {
  id: string;
  phone: string;
  candidate_name?: string | null;
  intake_status: string;
  cv_received: boolean;
  first_message_at?: string;
  last_message_at?: string;
  is_active: boolean;
}

export interface PandiusClientDetail {
  client: PandiusClient;
  contact: Record<string, any>;
  conversations: any[];
}

export async function fetchPandiusClients(
  isActive?: boolean,
  limit: number = 50,
  offset: number = 0
): Promise<PandiusClient[]> {
  const params = new URLSearchParams();
  if (isActive !== undefined) params.append("is_active", String(isActive));
  params.append("limit", String(limit));
  params.append("offset", String(offset));

  const response = await fetch(
    `${API_BASE}/admin/pandius/clients?${params.toString()}`
  );
  if (!response.ok) {
    throw new Error(`Failed to fetch Pandius clients: ${response.statusText}`);
  }
  return response.json();
}

export async function fetchPandiusClient(
  clientId: string
): Promise<PandiusClientDetail> {
  const response = await fetch(`${API_BASE}/admin/pandius/clients/${clientId}`);
  if (!response.ok) {
    throw new Error(`Failed to fetch Pandius client: ${response.statusText}`);
  }
  return response.json();
}

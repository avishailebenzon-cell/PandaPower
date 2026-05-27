/**
 * Pandi API client utilities
 * Fetch functions for Pandi client management endpoints
 */

const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";

export interface PandiClient {
  id: string;
  phone: string;
  contact_name?: string;
  organization_name?: string;
  identification_method: string;
  intake_status: string;
  first_message_at?: string;
  last_message_at?: string;
  is_active: boolean;
}

export interface GenerateInviteRequest {
  contact_id: string;
}

export interface GenerateInviteResponse {
  invite_url: string;
  prefilled_message: string;
  instructions_for_admin: string;
}

export interface PandiClientDetail {
  client: PandiClient;
  contact: Record<string, any>;
  organization: Record<string, any>;
  conversations: any[];
}

/**
 * Fetch list of Pandi clients with optional filters
 */
export async function fetchPandiClients(
  isActive?: boolean,
  limit: number = 50,
  offset: number = 0
): Promise<PandiClient[]> {
  const params = new URLSearchParams();
  if (isActive !== undefined) {
    params.append("is_active", String(isActive));
  }
  params.append("limit", String(limit));
  params.append("offset", String(offset));

  const response = await fetch(
    `${API_BASE}/admin/pandi/clients?${params.toString()}`
  );

  if (!response.ok) {
    throw new Error(`Failed to fetch Pandi clients: ${response.statusText}`);
  }

  return response.json();
}

/**
 * Fetch detailed Pandi client profile with conversation history
 */
export async function fetchPandiClient(clientId: string): Promise<PandiClientDetail> {
  const response = await fetch(`${API_BASE}/admin/pandi/clients/${clientId}`);

  if (!response.ok) {
    throw new Error(`Failed to fetch Pandi client: ${response.statusText}`);
  }

  return response.json();
}

/**
 * Generate WhatsApp invite for a contact
 */
export async function generatePandiInvite(
  contactId: string
): Promise<GenerateInviteResponse> {
  const response = await fetch(`${API_BASE}/admin/pandi/generate-invite`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ contact_id: contactId }),
  });

  if (!response.ok) {
    throw new Error(`Failed to generate invite: ${response.statusText}`);
  }

  return response.json();
}

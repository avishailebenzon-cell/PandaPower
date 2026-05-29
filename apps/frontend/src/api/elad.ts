/**
 * Elad Outreach API Client (Session 35)
 * Premium client outreach campaign management
 */

const API_BASE = import.meta.env.VITE_API_URL || '';

export interface Contact {
  id: string;
  full_name: string;
  email: string;
  phone: string;
  organization_name?: string;
  domain?: string;
  security_clearance_level?: string;
}

export interface Campaign {
  id: string;
  campaign_name: string;
  created_by_user_id: string;
  message_template: string;
  filters?: Record<string, unknown>;
  status: 'draft' | 'scheduled' | 'in_progress' | 'completed' | 'paused';
  total_contacts: number;
  sent_count: number;
  failed_count: number;
  created_at: string;
}

export interface PreviewMessage {
  contact: Contact;
  rendered_message: string;
}

export interface CampaignPreview {
  campaign: Campaign;
  preview_messages: PreviewMessage[];
}

export interface SendResponse {
  status: string;
  campaign_id: string;
  total_contacts: number;
  estimated_duration_seconds: number;
}

/**
 * List contacts available for outreach
 */
export async function fetchOutreachContacts(
  filters?: {
    organization_ids?: string[];
    domains?: string[];
    clearance_levels?: string[];
  },
  limit = 100,
  offset = 0
): Promise<Contact[]> {
  const params = new URLSearchParams();

  if (filters?.organization_ids) {
    filters.organization_ids.forEach(id => params.append('organization_ids', id));
  }
  if (filters?.domains) {
    filters.domains.forEach(d => params.append('domains', d));
  }
  if (filters?.clearance_levels) {
    filters.clearance_levels.forEach(c => params.append('clearance_levels', c));
  }

  params.append('limit', String(limit));
  params.append('offset', String(offset));

  const response = await fetch(
    `${API_BASE}/admin/elad/outreach/contacts?${params}`,
    { credentials: 'include' }
  );

  if (!response.ok) {
    throw new Error(`Failed to fetch contacts: ${response.statusText}`);
  }

  return response.json();
}

/**
 * Create new outreach campaign
 */
export async function createCampaign(data: {
  campaign_name: string;
  message_template: string;
  filters?: Record<string, unknown>;
  scheduled_start_at?: string;
}): Promise<Campaign> {
  const response = await fetch(
    `${API_BASE}/admin/elad/outreach/campaigns`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
      credentials: 'include'
    }
  );

  if (!response.ok) {
    throw new Error(`Failed to create campaign: ${response.statusText}`);
  }

  return response.json();
}

/**
 * Get campaign preview with contacts and rendered messages
 */
export async function previewCampaign(
  campaignId: string,
  limit = 10,
  offset = 0
): Promise<CampaignPreview> {
  const params = new URLSearchParams({
    limit: String(limit),
    offset: String(offset)
  });

  const response = await fetch(
    `${API_BASE}/admin/elad/outreach/campaigns/${campaignId}/preview?${params}`,
    { credentials: 'include' }
  );

  if (!response.ok) {
    throw new Error(`Failed to preview campaign: ${response.statusText}`);
  }

  return response.json();
}

/**
 * Send campaign
 */
export async function sendCampaign(campaignId: string): Promise<SendResponse> {
  const response = await fetch(
    `${API_BASE}/admin/elad/outreach/campaigns/${campaignId}/send`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ confirm: true }),
      credentials: 'include'
    }
  );

  if (!response.ok) {
    throw new Error(`Failed to send campaign: ${response.statusText}`);
  }

  return response.json();
}

/**
 * Get campaign details
 */
export async function fetchCampaign(campaignId: string): Promise<Campaign> {
  const response = await fetch(
    `${API_BASE}/admin/elad/outreach/campaigns/${campaignId}`,
    { credentials: 'include' }
  );

  if (!response.ok) {
    throw new Error(`Failed to fetch campaign: ${response.statusText}`);
  }

  return response.json();
}

/**
 * List campaigns
 */
export async function fetchCampaigns(limit = 20, offset = 0): Promise<Campaign[]> {
  const params = new URLSearchParams({
    limit: String(limit),
    offset: String(offset)
  });

  const response = await fetch(
    `${API_BASE}/admin/elad/outreach/campaigns?${params}`,
    { credentials: 'include' }
  );

  if (!response.ok) {
    throw new Error(`Failed to fetch campaigns: ${response.statusText}`);
  }

  return response.json();
}

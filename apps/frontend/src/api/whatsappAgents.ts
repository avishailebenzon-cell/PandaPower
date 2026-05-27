/**
 * WhatsApp-agents settings API client (Tal / Elad / Pandi Green-API config).
 * Mirrors the backend at apps/backend/src/pandapower/routers/admin/whatsapp_agents.py.
 *
 * Strict per-agent separation: every read and write targets one agent's
 * own `{code}.*` namespace in system_settings. No shared fields.
 */

const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";

export type WhatsAppAgentCode = "tal" | "elad" | "pandi";

export interface WhatsAppAgentConfig {
  agent_code: WhatsAppAgentCode;
  name: string;
  role: string;
  emoji: string;
  instance_id: string;
  token: string;
  whatsapp_number: string;
  webhook_secret: string;
  last_updated_at: string | null;
  is_configured: boolean;
}

export interface WhatsAppAgentConfigUpdate {
  instance_id: string;
  token: string;
  whatsapp_number: string;
  webhook_secret: string;
}

export async function fetchWhatsAppAgents(): Promise<WhatsAppAgentConfig[]> {
  const r = await fetch(`${API_BASE}/admin/whatsapp-agents/config`);
  if (!r.ok) throw new Error(`Failed to fetch WhatsApp agents config: ${r.statusText}`);
  const data = await r.json();
  return data.agents as WhatsAppAgentConfig[];
}

export async function saveWhatsAppAgent(
  agentCode: WhatsAppAgentCode,
  body: WhatsAppAgentConfigUpdate,
): Promise<WhatsAppAgentConfig> {
  const r = await fetch(`${API_BASE}/admin/whatsapp-agents/${agentCode}/config`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(`Failed to save ${agentCode} config: ${r.statusText}`);
  return r.json();
}

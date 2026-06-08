/**
 * WhatsApp-agents settings API client (Tal / Elad / Pandi Green-API config).
 * Mirrors the backend at apps/backend/src/pandapower/routers/admin/whatsapp_agents.py.
 *
 * Strict per-agent separation: every read and write targets one agent's
 * own `{code}.*` namespace in system_settings. No shared fields.
 */

const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";

export type WhatsAppAgentCode = "tal" | "elad" | "pandi" | "pandius";

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
  // Per-agent webhook URL the admin pastes into the Green API console.
  webhook_url: string;
  webhook_url_with_token: string;
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

// ============================================================================
// Per-bot CONVERSATIONS / DASHBOARD / BEHAVIOR / PLAYGROUND
// All scoped by agent_code in the URL — never share data across bots.
// ============================================================================

export interface ConversationListItem {
  id: string;
  started_at: string | null;
  last_message_at: string | null;
  status: string;
  contact_name: string | null;
  contact_phone: string | null;
  message_count: number;
}

export interface MessageItem {
  id: string;
  direction: "inbound" | "outbound" | string;
  message_type: string;
  text: string | null;
  created_at: string | null;
  llm_invoked: boolean;
}

export interface DashboardData {
  bot_code: string;
  total_conversations: number;
  active_conversations: number;
  messages_today: number;
  messages_this_week: number;
  inbound_this_week: number;
  outbound_this_week: number;
  avg_response_minutes: number | null;
  is_configured: boolean;
}

export interface QAPair {
  question: string;
  answer: string;
}

export interface BehaviorConfig {
  bot_code: string;
  name: string;
  role: string;
  system_prompt_addendum: string;
  qa_pairs: QAPair[];
}

export interface PlaygroundResult {
  bot_code: string;
  user_message: string;
  bot_reply: string;
  duration_ms: number;
  tokens_used: number;
  matched_qa: string | null;
  used_system_prompt: string;
}

export async function fetchConversations(bot: WhatsAppAgentCode) {
  const r = await fetch(`${API_BASE}/admin/whatsapp-agents/${bot}/conversations`);
  if (!r.ok) throw new Error(`Failed to fetch conversations: ${r.statusText}`);
  return r.json() as Promise<{ bot_code: string; total: number; conversations: ConversationListItem[] }>;
}

export async function fetchMessages(bot: WhatsAppAgentCode, conversationId: string) {
  const r = await fetch(
    `${API_BASE}/admin/whatsapp-agents/${bot}/conversations/${conversationId}/messages`,
  );
  if (!r.ok) throw new Error(`Failed to fetch messages: ${r.statusText}`);
  return r.json() as Promise<{ bot_code: string; conversation_id: string; messages: MessageItem[] }>;
}

export async function fetchDashboard(bot: WhatsAppAgentCode): Promise<DashboardData> {
  const r = await fetch(`${API_BASE}/admin/whatsapp-agents/${bot}/dashboard`);
  if (!r.ok) throw new Error(`Failed to fetch dashboard: ${r.statusText}`);
  return r.json();
}

export async function fetchBehavior(bot: WhatsAppAgentCode): Promise<BehaviorConfig> {
  const r = await fetch(`${API_BASE}/admin/whatsapp-agents/${bot}/behavior`);
  if (!r.ok) throw new Error(`Failed to fetch behavior: ${r.statusText}`);
  return r.json();
}

export async function saveBehavior(
  bot: WhatsAppAgentCode,
  body: { system_prompt_addendum: string; qa_pairs: QAPair[] },
): Promise<BehaviorConfig> {
  const r = await fetch(`${API_BASE}/admin/whatsapp-agents/${bot}/behavior`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(`Failed to save behavior: ${r.statusText}`);
  return r.json();
}

export async function runPlayground(
  bot: WhatsAppAgentCode,
  message: string,
  includeQa = true,
): Promise<PlaygroundResult> {
  const r = await fetch(`${API_BASE}/admin/whatsapp-agents/${bot}/playground`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, include_qa: includeQa }),
  });
  if (!r.ok) throw new Error(`Playground call failed: ${r.statusText}`);
  return r.json();
}

/**
 * Dana API client — AI sales agent that intakes new job deals into Pipedrive.
 */

const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";

export interface DanaMessage {
  id?: string;
  direction: "inbound" | "outbound";
  text: string;
  sent_at?: string;
}

export interface DanaConversationSummary {
  id: string;
  title?: string | null;
  status: string;
  pipedrive_deal_id?: number | null;
  created_at?: string;
  updated_at?: string;
}

export interface DanaConversationDetail {
  conversation: DanaConversationSummary & { job_context?: Record<string, unknown> };
  messages: DanaMessage[];
}

export async function createConversation(): Promise<{
  id: string;
  status: string;
  opening_message: string;
}> {
  const res = await fetch(`${API_BASE}/admin/dana/conversations`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
  });
  if (!res.ok) throw new Error("Failed to create conversation");
  return res.json();
}

export async function listConversations(): Promise<DanaConversationSummary[]> {
  const res = await fetch(`${API_BASE}/admin/dana/conversations`);
  if (!res.ok) throw new Error("Failed to list conversations");
  return res.json();
}

export async function getConversation(
  id: string
): Promise<DanaConversationDetail> {
  const res = await fetch(`${API_BASE}/admin/dana/conversations/${id}`);
  if (!res.ok) throw new Error("Failed to load conversation");
  return res.json();
}

export async function sendMessage(
  id: string,
  text: string
): Promise<{ text: string }> {
  const res = await fetch(
    `${API_BASE}/admin/dana/conversations/${id}/message`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
    }
  );
  if (!res.ok) throw new Error("Failed to send message");
  return res.json();
}

export async function uploadFile(
  id: string,
  file: File
): Promise<{ text: string }> {
  const formData = new FormData();
  formData.append("file", file);
  const res = await fetch(
    `${API_BASE}/admin/dana/conversations/${id}/upload`,
    { method: "POST", body: formData }
  );
  if (!res.ok) throw new Error("Failed to upload file");
  return res.json();
}

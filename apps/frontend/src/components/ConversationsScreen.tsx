/**
 * Reusable WhatsApp-style conversations screen, shared by the three agents
 * (Tal / Elad / Pandi). Right side: the list of contacts the agent is in touch
 * with (= list of conversations). Center: the chat bubbles for the selected
 * contact. The operator can write a reply *as the agent* and toggle a switch
 * that temporarily pauses the agent's AI auto-reply (human takeover). When the
 * toggle is turned back off, the agent resumes the thread on the next inbound
 * message.
 *
 * All agent-specific wording (title, the counterpart noun, the agent's name) is
 * injected via props; the behaviour is identical across agents.
 */

import React, { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Send, Loader2, ArrowRight, Pause, Play, Sparkles } from "lucide-react";
import type {
  ConversationsApi,
  ChatMessage,
  ConversationSummary,
} from "@/api/conversationsApi";
import { deliveryReasonText } from "@/api/conversationsApi";

// A conversation is "live" when its last message is recent (mirrors the bottom
// status-bar logic), so the green dot reflects real activity rather than just a
// never-closed 'active' status.
const LIVE_WINDOW_MS = 15 * 60 * 1000;
const isLive = (lastMessageAt?: string | null): boolean => {
  if (!lastMessageAt) return false;
  const ts = Date.parse(lastMessageAt);
  return !Number.isNaN(ts) && Date.now() - ts <= LIVE_WINDOW_MS;
};

export interface ConversationsScreenProps {
  api: ConversationsApi;
  /** e.g. "👩‍💼 שיחות של טל" */
  title: string;
  /** one-line description under the title */
  subtitle: string;
  /** where the "back" button goes, e.g. "/recruiting/tal" */
  backTo: string;
  /** label for the list column, e.g. "מועמדים" (Tal) / "לקוחות" (Elad/Pandi) */
  contactsLabel: string;
  /** agent name for the composer placeholder + pause button, e.g. "טל" */
  agentName: string;
  /** grammatical gender of the agent — drives Hebrew agreement ("f" = נקבה). */
  agentGender: "f" | "m";
}

export const ConversationsScreen: React.FC<ConversationsScreenProps> = ({
  api,
  title,
  subtitle,
  backTo,
  contactsLabel,
  agentName,
  agentGender,
}) => {
  const navigate = useNavigate();
  // Hebrew gender agreement for the agent's own state/actions.
  const isF = agentGender === "f";
  const pausedAdj = isF ? "מושבתת" : "מושבת"; // "X is paused"
  const resumeVerb = isF ? "שתמשיך" : "שימשיך"; // "...so X continues"
  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [contactName, setContactName] = useState<string>("");
  const [jobTitle, setJobTitle] = useState<string>("");
  const [paused, setPaused] = useState<boolean>(false);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  const refreshConversations = async () => {
    try {
      setConversations(await api.list());
    } catch (e) {
      console.error(e);
    }
  };

  useEffect(() => {
    refreshConversations();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [api]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // Poll for real-time updates: refresh the contact list, and (while a
  // conversation is open and the operator isn't mid-typing) pull new messages.
  useEffect(() => {
    const id = setInterval(() => {
      refreshConversations();
      if (activeId && !input.trim()) {
        api
          .get(activeId)
          .then((detail) => {
            setMessages(detail.messages);
            setPaused(detail.auto_reply_paused);
          })
          .catch(() => {});
      }
    }, 6000);
    return () => clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeId, input, api]);

  const openConversation = async (id: string) => {
    setActiveId(id);
    const detail = await api.get(id);
    setMessages(detail.messages);
    setContactName(detail.candidate_name);
    setJobTitle(detail.job_title);
    setPaused(detail.auto_reply_paused);
  };

  const handleSend = async () => {
    if (!activeId || !input.trim() || sending) return;
    const text = input.trim();
    setInput("");
    setMessages((prev) => [...prev, { direction: "outbound", text, author: "human" }]);
    setSending(true);
    try {
      const res = await api.send(activeId, text);
      if (!res.delivered) {
        setMessages((prev) => [
          ...prev,
          {
            direction: "outbound",
            text: "⚠️ " + deliveryReasonText(res.delivery_reason ?? null),
            author: "human",
          },
        ]);
      }
      refreshConversations();
    } catch (e) {
      setMessages((prev) => [
        ...prev,
        { direction: "outbound", text: "⚠️ שליחת ההודעה נכשלה.", author: "human" },
      ]);
    } finally {
      setSending(false);
    }
  };

  const togglePause = async () => {
    if (!activeId) return;
    const next = !paused;
    setPaused(next);
    try {
      await api.pause(activeId, next);
      refreshConversations();
    } catch (e) {
      setPaused(!next); // revert on failure
    }
  };

  const triggerAgent = async () => {
    if (!activeId || sending) return;
    setSending(true);
    try {
      const res = await api.generate(activeId);
      if (res.text) {
        setMessages((prev) => [
          ...prev,
          { direction: "outbound", text: res.text, author: "agent" },
        ]);
      }
      refreshConversations();
    } finally {
      setSending(false);
    }
  };

  return (
    <div className="p-6 space-y-4" dir="rtl">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold text-white flex items-center gap-2">{title}</h1>
          <p className="text-gray-400 mt-1">{subtitle}</p>
        </div>
        <button
          onClick={() => navigate(backTo)}
          className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-gray-700 text-white hover:bg-gray-600 transition"
        >
          חזרה <ArrowRight className="w-4 h-4" />
        </button>
      </div>

      <div className="flex gap-4 h-[calc(100vh-220px)]">
        {/* Conversation list (right side in RTL) */}
        <aside className="w-72 shrink-0 rounded-lg border border-gray-700 bg-gray-900/50 overflow-y-auto">
          <div className="p-3 text-xs font-semibold text-gray-400 border-b border-gray-700">
            {contactsLabel} ({conversations.length})
          </div>
          {conversations.length === 0 ? (
            <div className="p-4 text-sm text-gray-500">אין שיחות עדיין</div>
          ) : (
            conversations.map((c) => (
              <button
                key={c.id}
                onClick={() => openConversation(c.id)}
                className={`w-full text-right px-3 py-3 border-b border-gray-800 hover:bg-gray-800/50 transition ${
                  activeId === c.id ? "bg-gray-800" : ""
                }`}
              >
                <div className="text-sm text-white truncate flex items-center justify-between gap-1">
                  <span className="truncate">{c.candidate_name}</span>
                  {c.auto_reply_paused ? (
                    <Pause className="w-3 h-3 text-amber-400 shrink-0" />
                  ) : isLive(c.last_message_at) ? (
                    <span className="relative flex h-2 w-2 shrink-0" title="שיחה פעילה">
                      <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-75" />
                      <span className="relative inline-flex h-2 w-2 rounded-full bg-green-400" />
                    </span>
                  ) : null}
                </div>
                {c.job_title && (
                  <div className="text-xs text-gray-500 truncate">{c.job_title}</div>
                )}
                {c.last_message && (
                  <div className="text-xs text-gray-600 truncate mt-0.5">{c.last_message}</div>
                )}
              </button>
            ))
          )}
        </aside>

        {/* Chat (center) */}
        <section className="flex-1 flex flex-col rounded-lg border border-gray-700 bg-gray-900/50 overflow-hidden">
          {!activeId ? (
            <div className="flex-1 flex items-center justify-center text-gray-500">
              בחר שיחה מהרשימה כדי לראות אותה 💬
            </div>
          ) : (
            <>
              {/* Header with contact + pause toggle */}
              <div className="border-b border-gray-700 px-4 py-3 flex items-center justify-between bg-gray-900/70">
                <div>
                  <div className="text-white font-semibold flex items-center gap-2">
                    {contactName}
                    {paused ? (
                      <span className="inline-flex items-center gap-1 text-[11px] font-semibold px-2 py-0.5 rounded-full bg-amber-700/70 text-amber-100">
                        מושהה
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1.5 text-[11px] font-semibold px-2 py-0.5 rounded-full bg-green-600 text-white animate-live-glow ring-1 ring-green-300/70">
                        <span className="relative flex h-2 w-2">
                          <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-200 opacity-90" />
                          <span className="relative inline-flex h-2 w-2 rounded-full bg-green-100" />
                        </span>
                        <span className="animate-blink">בשיחה פעילה</span>
                      </span>
                    )}
                  </div>
                  {jobTitle && <div className="text-xs text-gray-400">{jobTitle}</div>}
                </div>
                <div className="flex items-center gap-2">
                  <button
                    onClick={triggerAgent}
                    disabled={sending || paused}
                    title={paused ? `${agentName} ${pausedAdj}` : `בקש מ${agentName} לענות עכשיו`}
                    className="inline-flex items-center gap-1 px-3 py-1.5 rounded-lg text-sm bg-teal-700 text-white hover:bg-teal-600 disabled:opacity-40"
                  >
                    <Sparkles className="w-4 h-4" /> תגובת {agentName}
                  </button>
                  <button
                    onClick={togglePause}
                    className={`inline-flex items-center gap-1 px-3 py-1.5 rounded-lg text-sm transition ${
                      paused
                        ? "bg-amber-600 text-white hover:bg-amber-500"
                        : "bg-gray-700 text-gray-200 hover:bg-gray-600"
                    }`}
                  >
                    {paused ? (
                      <>
                        <Play className="w-4 h-4" /> הפעל את {agentName}
                      </>
                    ) : (
                      <>
                        <Pause className="w-4 h-4" /> השבת את {agentName}
                      </>
                    )}
                  </button>
                </div>
              </div>

              {paused && (
                <div className="bg-amber-900/40 text-amber-200 text-xs px-4 py-2 border-b border-amber-800">
                  {agentName} {pausedAdj} זמנית — ההודעות שתכתוב יישלחו בשמ{isF ? "ה" : "ו"}. הפעל/י כדי {resumeVerb} את השיחה אוטומטית.
                </div>
              )}

              <div className="flex-1 overflow-y-auto p-4 space-y-3">
                {messages.map((m, i) => {
                  const isOutbound = m.direction === "outbound";
                  return (
                    <div
                      key={m.id || i}
                      className={`flex ${isOutbound ? "justify-start" : "justify-end"}`}
                    >
                      <div
                        className={`max-w-[75%] rounded-2xl px-4 py-2 text-sm whitespace-pre-wrap ${
                          isOutbound
                            ? "bg-teal-700 text-white rounded-bl-sm"
                            : "bg-gray-700 text-gray-100 rounded-br-sm"
                        }`}
                      >
                        {m.text}
                        {isOutbound && m.author === "human" && (
                          <div className="text-[10px] text-teal-200/80 mt-1">
                            ✍️ נכתב על ידך (בשם {agentName})
                          </div>
                        )}
                      </div>
                    </div>
                  );
                })}
                {sending && (
                  <div className="flex justify-start">
                    <div className="bg-teal-700/60 rounded-2xl px-4 py-2 text-white">
                      <Loader2 className="w-4 h-4 animate-spin" />
                    </div>
                  </div>
                )}
                <div ref={bottomRef} />
              </div>

              {/* Composer */}
              <div className="border-t border-gray-700 p-3 flex items-center gap-2">
                <input
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && handleSend()}
                  placeholder={`כתוב הודעה בשם ${agentName}...`}
                  disabled={sending}
                  className="flex-1 bg-gray-800 text-white rounded-lg px-4 py-2 outline-none focus:ring-2 focus:ring-teal-600"
                />
                <button
                  onClick={handleSend}
                  disabled={sending || !input.trim()}
                  className="p-2 rounded-lg bg-teal-600 hover:bg-teal-700 text-white disabled:opacity-50"
                >
                  <Send className="w-5 h-5" />
                </button>
              </div>
            </>
          )}
        </section>
      </div>
    </div>
  );
};

export default ConversationsScreen;

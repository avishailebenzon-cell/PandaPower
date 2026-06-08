import React, { useEffect, useRef, useState } from "react";
import { Plus, Send, Paperclip, Loader2, CheckCircle2 } from "lucide-react";
import {
  createConversation,
  listConversations,
  getConversation,
  sendMessage,
  uploadFile,
  type DanaMessage,
  type DanaConversationSummary,
} from "@/api/dana";

export const DanaPage: React.FC = () => {
  const [conversations, setConversations] = useState<DanaConversationSummary[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [messages, setMessages] = useState<DanaMessage[]>([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [status, setStatus] = useState<string>("open");
  const [dealId, setDealId] = useState<number | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  const refreshConversations = async () => {
    try {
      setConversations(await listConversations());
    } catch (e) {
      console.error(e);
    }
  };

  useEffect(() => {
    refreshConversations();
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const openConversation = async (id: string) => {
    setActiveId(id);
    const detail = await getConversation(id);
    setMessages(detail.messages);
    setStatus(detail.conversation.status);
    setDealId(detail.conversation.pipedrive_deal_id ?? null);
  };

  const startNew = async () => {
    const conv = await createConversation();
    await refreshConversations();
    await openConversation(conv.id);
  };

  const appendReply = (text: string) => {
    setMessages((prev) => [...prev, { direction: "outbound", text }]);
  };

  const handleSend = async () => {
    if (!activeId || !input.trim() || sending) return;
    const text = input.trim();
    setInput("");
    setMessages((prev) => [...prev, { direction: "inbound", text }]);
    setSending(true);
    try {
      const res = await sendMessage(activeId, text);
      appendReply(res.text);
      await openConversation(activeId); // refresh status/deal id
      refreshConversations();
    } catch (e) {
      appendReply("שגיאה בשליחת ההודעה. נסה שוב.");
    } finally {
      setSending(false);
    }
  };

  const handleFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file || !activeId) return;
    setMessages((prev) => [
      ...prev,
      { direction: "inbound", text: `📎 הועלה קובץ: ${file.name}` },
    ]);
    setSending(true);
    try {
      const res = await uploadFile(activeId, file);
      appendReply(res.text);
      await openConversation(activeId);
    } catch (err) {
      appendReply("שגיאה בעיבוד הקובץ. ודא שזה PDF/Word/תמונה ונסה שוב.");
    } finally {
      setSending(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  };

  return (
    <div className="p-6 space-y-4" dir="rtl">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold text-white flex items-center gap-2">
            💼 דנה
          </h1>
          <p className="text-gray-400 mt-1">
            סוכנת הזנת משרות — פותחת דיל חדש בפייפדרייב ומסנכרנת למערכת
          </p>
        </div>
        <button
          onClick={startNew}
          className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-teal-600 text-white hover:bg-teal-700 transition"
        >
          <Plus className="w-4 h-4" /> משרה חדשה
        </button>
      </div>

      <div className="flex gap-4 h-[calc(100vh-220px)]">
        {/* Conversation list */}
        <aside className="w-64 shrink-0 rounded-lg border border-gray-700 bg-gray-900/50 overflow-y-auto">
          <div className="p-3 text-xs font-semibold text-gray-400 border-b border-gray-700">
            שיחות
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
                <div className="text-sm text-white truncate flex items-center gap-1">
                  {c.status === "deal_created" && (
                    <CheckCircle2 className="w-3 h-3 text-green-400 shrink-0" />
                  )}
                  {c.title || "משרה חדשה"}
                </div>
                <div className="text-xs text-gray-500">
                  {c.status === "deal_created"
                    ? `דיל #${c.pipedrive_deal_id}`
                    : "בתהליך"}
                </div>
              </button>
            ))
          )}
        </aside>

        {/* Chat */}
        <section className="flex-1 flex flex-col rounded-lg border border-gray-700 bg-gray-900/50 overflow-hidden">
          {!activeId ? (
            <div className="flex-1 flex items-center justify-center text-gray-500">
              בחר שיחה קיימת או פתח משרה חדשה כדי להתחיל 💼
            </div>
          ) : (
            <>
              {status === "deal_created" && (
                <div className="bg-green-900/40 text-green-300 text-sm px-4 py-2 flex items-center gap-2 border-b border-green-800">
                  <CheckCircle2 className="w-4 h-4" />
                  הדיל נפתח בפייפדרייב{dealId ? ` (#${dealId})` : ""} וסונכרן למערכת.
                </div>
              )}
              <div className="flex-1 overflow-y-auto p-4 space-y-3">
                {messages.map((m, i) => (
                  <div
                    key={i}
                    className={`flex ${
                      m.direction === "outbound" ? "justify-start" : "justify-end"
                    }`}
                  >
                    <div
                      className={`max-w-[75%] rounded-2xl px-4 py-2 text-sm whitespace-pre-wrap ${
                        m.direction === "outbound"
                          ? "bg-teal-700 text-white rounded-bl-sm"
                          : "bg-gray-700 text-gray-100 rounded-br-sm"
                      }`}
                    >
                      {m.text}
                    </div>
                  </div>
                ))}
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
                  ref={fileRef}
                  type="file"
                  accept=".pdf,.doc,.docx,.png,.jpg,.jpeg,.tiff,.webp"
                  onChange={handleFile}
                  className="hidden"
                />
                <button
                  onClick={() => fileRef.current?.click()}
                  disabled={sending}
                  title="צרף קובץ (PDF / Word / תמונה)"
                  className="p-2 rounded-lg bg-gray-700 hover:bg-gray-600 text-gray-200 disabled:opacity-50"
                >
                  <Paperclip className="w-5 h-5" />
                </button>
                <input
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && handleSend()}
                  placeholder="כתוב הודעה לדנה..."
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

export default DanaPage;

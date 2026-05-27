/**
 * WhatsApp-agents Console — unified per-bot management surface.
 *
 * One top-level "active bot" picker (Tal / Elad / Pandi) drives every tab
 * below it. Strict per-bot isolation: every API call carries the bot's
 * code in the URL, and the layout colors itself by the active bot so the
 * admin can't confuse them.
 *
 * Tabs (mirroring what we have in the Pandoosh project):
 *   1. הגדרות      — Green-API credentials (preserved from earlier work)
 *   2. שיחות       — list of conversations + transcript drilldown
 *   3. התנהגות     — system-prompt addendum + predefined Q&A
 *   4. דאשבורד     — KPIs (conversations / messages / configured-status)
 *   5. מגרש משחקים — send a test message to the bot, see its reply
 */

import { useEffect, useMemo, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  fetchWhatsAppAgents,
  saveWhatsAppAgent,
  fetchConversations,
  fetchMessages,
  fetchDashboard,
  fetchBehavior,
  saveBehavior,
  runPlayground,
  type WhatsAppAgentConfig,
  type WhatsAppAgentConfigUpdate,
  type WhatsAppAgentCode,
  type ConversationListItem,
  type MessageItem,
  type DashboardData,
  type BehaviorConfig,
  type QAPair,
  type PlaygroundResult,
} from "@/api/whatsappAgents";

type TabId = "settings" | "conversations" | "behavior" | "dashboard" | "playground";

const TABS: { id: TabId; label: string; icon: string }[] = [
  { id: "settings", label: "הגדרות", icon: "🔧" },
  { id: "conversations", label: "שיחות", icon: "💬" },
  { id: "behavior", label: "התנהגות", icon: "🧠" },
  { id: "dashboard", label: "דאשבורד", icon: "📊" },
  { id: "playground", label: "מגרש משחקים", icon: "🧪" },
];

const BOT_COLORS: Record<WhatsAppAgentCode, { border: string; accent: string; bg: string }> = {
  tal: { border: "border-blue-500", accent: "text-blue-300", bg: "bg-blue-900/20" },
  elad: { border: "border-emerald-500", accent: "text-emerald-300", bg: "bg-emerald-900/20" },
  pandi: { border: "border-cyan-500", accent: "text-cyan-300", bg: "bg-cyan-900/20" },
};

function formatWhen(iso: string | null | undefined): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString("he-IL", {
      day: "2-digit",
      month: "2-digit",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return iso || "—";
  }
}

export const WhatsAppAgentsSettingsPage = () => {
  const agentsQ = useQuery({
    queryKey: ["whatsapp-agents"],
    queryFn: fetchWhatsAppAgents,
  });
  const [activeBot, setActiveBot] = useState<WhatsAppAgentCode>("tal");
  const [activeTab, setActiveTab] = useState<TabId>("settings");

  const agent = useMemo(
    () => (agentsQ.data ?? []).find((a) => a.agent_code === activeBot),
    [agentsQ.data, activeBot],
  );

  return (
    <div dir="rtl" className="p-6 space-y-6">
      <header>
        <h1 className="text-3xl font-bold text-white flex items-center gap-2">
          <span>📞</span> קונסול WhatsApp לסוכני AI
        </h1>
        <p className="text-gray-400 mt-1 max-w-3xl">
          הגדרה, מעקב והתאמה של 3 בוטים נפרדים. כל בוט אטום לחלוטין משאר הבוטים —
          שינוי טוקן, התנהגות או הגדרה אצל אחד לעולם לא ייגע באחרים.
        </p>
      </header>

      <BotPicker
        agents={agentsQ.data ?? []}
        active={activeBot}
        onChange={(c) => setActiveBot(c)}
      />

      <TabBar tabs={TABS} active={activeTab} onChange={(t) => setActiveTab(t)} />

      {agentsQ.isLoading || !agent ? (
        <div className="text-gray-400 text-center py-8">טוען…</div>
      ) : agentsQ.error ? (
        <div className="bg-red-900/30 border border-red-700 rounded-lg p-4 text-red-200">
          שגיאה: {String((agentsQ.error as Error).message)}
        </div>
      ) : (
        <TabBody bot={agent} tab={activeTab} />
      )}
    </div>
  );
};

// ============================================================================
// Bot picker (top of the page)
// ============================================================================
function BotPicker({
  agents,
  active,
  onChange,
}: {
  agents: WhatsAppAgentConfig[];
  active: WhatsAppAgentCode;
  onChange: (c: WhatsAppAgentCode) => void;
}) {
  return (
    <div className="flex gap-3 flex-wrap">
      {agents.map((a) => {
        const c = BOT_COLORS[a.agent_code];
        const isActive = a.agent_code === active;
        return (
          <button
            key={a.agent_code}
            onClick={() => onChange(a.agent_code)}
            className={`min-w-[220px] text-right px-4 py-3 rounded-lg border-2 transition ${
              isActive
                ? `${c.border} ${c.bg}`
                : "border-gray-700 bg-gray-800 hover:bg-gray-750"
            }`}
          >
            <div className={`text-lg font-bold ${isActive ? c.accent : "text-white"} flex items-center gap-2 justify-end`}>
              <span>{a.name}</span>
              <span>{a.emoji}</span>
            </div>
            <div className="text-xs text-gray-400 mt-1">{a.role}</div>
            <div className="mt-2">
              <span
                className={`text-xs font-semibold px-2 py-0.5 rounded ${
                  a.is_configured ? "bg-green-900 text-green-200" : "bg-yellow-900 text-yellow-200"
                }`}
              >
                {a.is_configured ? "🟢 מוגדר" : "🟡 לא מוגדר"}
              </span>
            </div>
          </button>
        );
      })}
    </div>
  );
}

function TabBar({
  tabs,
  active,
  onChange,
}: {
  tabs: typeof TABS;
  active: TabId;
  onChange: (id: TabId) => void;
}) {
  return (
    <div className="flex gap-2 border-b border-gray-700 overflow-x-auto">
      {tabs.map((t) => (
        <button
          key={t.id}
          onClick={() => onChange(t.id)}
          className={`px-4 py-2 font-semibold text-sm transition whitespace-nowrap ${
            active === t.id
              ? "text-blue-400 border-b-2 border-blue-400 -mb-px"
              : "text-gray-400 hover:text-gray-200"
          }`}
        >
          <span className="ml-1">{t.icon}</span>
          {t.label}
        </button>
      ))}
    </div>
  );
}

function TabBody({ bot, tab }: { bot: WhatsAppAgentConfig; tab: TabId }) {
  switch (tab) {
    case "settings":
      return <SettingsTab bot={bot} />;
    case "conversations":
      return <ConversationsTab bot={bot} />;
    case "behavior":
      return <BehaviorTab bot={bot} />;
    case "dashboard":
      return <DashboardTab bot={bot} />;
    case "playground":
      return <PlaygroundTab bot={bot} />;
  }
}

// ============================================================================
// TAB 1 — Settings (preserved from the original implementation)
// ============================================================================
function SettingsTab({ bot }: { bot: WhatsAppAgentConfig }) {
  const qc = useQueryClient();
  const [form, setForm] = useState<WhatsAppAgentConfigUpdate>({
    instance_id: bot.instance_id,
    token: bot.token,
    whatsapp_number: bot.whatsapp_number,
    webhook_secret: bot.webhook_secret,
  });
  const [statusMsg, setStatusMsg] = useState<string | null>(null);

  useEffect(() => {
    setForm({
      instance_id: bot.instance_id,
      token: bot.token,
      whatsapp_number: bot.whatsapp_number,
      webhook_secret: bot.webhook_secret,
    });
  }, [bot.agent_code]); // re-seed when user picks a different bot

  const save = useMutation({
    mutationFn: () => saveWhatsAppAgent(bot.agent_code, form),
    onSuccess: () => {
      setStatusMsg("✅ נשמר בהצלחה");
      qc.invalidateQueries({ queryKey: ["whatsapp-agents"] });
      setTimeout(() => setStatusMsg(null), 3000);
    },
    onError: (e: Error) => setStatusMsg(`❌ ${e.message}`),
  });

  const dirty =
    form.instance_id !== bot.instance_id ||
    form.token !== bot.token ||
    form.whatsapp_number !== bot.whatsapp_number ||
    form.webhook_secret !== bot.webhook_secret;

  return (
    <section className="bg-gray-800 border border-gray-700 rounded-lg p-5 space-y-4">
      <div className="text-sm text-gray-400">
        עודכן: {formatWhen(bot.last_updated_at)}
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <Field label={`📱 מספר WhatsApp של ${bot.name}`} value={form.whatsapp_number}
               onChange={(v) => setForm((f) => ({ ...f, whatsapp_number: v }))}
               help="לזיהוי אדם בלבד — לא נשלח ל-Green API." placeholder="+972501234567" dir="ltr" />
        <Field label="Green API Instance ID" value={form.instance_id}
               onChange={(v) => setForm((f) => ({ ...f, instance_id: v }))}
               help="מזהה המופע ב-Green API." placeholder="לדוגמה: 1101234567" dir="ltr" />
        <Field label="Green API Token" type="password" value={form.token}
               onChange={(v) => setForm((f) => ({ ...f, token: v }))}
               help="הטוקן הסודי." placeholder="••••••••••••••••" dir="ltr" />
        <Field label="Webhook Secret (אופציונלי)" type="password" value={form.webhook_secret}
               onChange={(v) => setForm((f) => ({ ...f, webhook_secret: v }))}
               help="לאימות הודעות נכנסות." dir="ltr" />
      </div>
      <div className="flex items-center justify-end gap-3 pt-3 border-t border-gray-700">
        {statusMsg && <span className="text-sm text-gray-300">{statusMsg}</span>}
        <button
          onClick={() => save.mutate()}
          disabled={!dirty || save.isPending}
          className={`px-5 py-2 rounded font-semibold text-sm transition ${
            !dirty || save.isPending
              ? "bg-gray-700 text-gray-500 cursor-not-allowed"
              : "bg-indigo-600 hover:bg-indigo-700 text-white"
          }`}
        >
          {save.isPending ? "שומר…" : `שמור הגדרות של ${bot.name}`}
        </button>
      </div>
    </section>
  );
}

// ============================================================================
// TAB 2 — Conversations
// ============================================================================
function ConversationsTab({ bot }: { bot: WhatsAppAgentConfig }) {
  const q = useQuery({
    queryKey: ["whatsapp-convs", bot.agent_code],
    queryFn: () => fetchConversations(bot.agent_code),
    refetchInterval: 20000,
  });
  const [selectedId, setSelectedId] = useState<string | null>(null);

  // Reset selection when switching bot
  useEffect(() => setSelectedId(null), [bot.agent_code]);

  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
      <div className="bg-gray-800 border border-gray-700 rounded-lg p-4 md:col-span-1">
        <div className="text-sm text-gray-400 mb-3">
          סה״כ {q.data?.total ?? 0} שיחות של {bot.name}
        </div>
        {q.isLoading ? (
          <div className="text-gray-400">טוען…</div>
        ) : (q.data?.conversations ?? []).length === 0 ? (
          <div className="text-sm text-gray-500 text-center py-6">
            🐼 אין עדיין שיחות עבור {bot.name}.
            {!bot.is_configured && (
              <div className="text-xs mt-2 text-yellow-400">
                ⚠️ Green API לא מוגדר — הגדר בטאב "הגדרות".
              </div>
            )}
          </div>
        ) : (
          <ul className="space-y-1 max-h-[60vh] overflow-y-auto">
            {q.data!.conversations.map((c) => (
              <ConversationRow
                key={c.id}
                conv={c}
                active={selectedId === c.id}
                onClick={() => setSelectedId(c.id)}
              />
            ))}
          </ul>
        )}
      </div>

      <div className="bg-gray-800 border border-gray-700 rounded-lg p-4 md:col-span-2">
        {selectedId ? (
          <TranscriptView bot={bot.agent_code} conversationId={selectedId} />
        ) : (
          <div className="text-gray-500 text-center py-12 text-sm">
            בחר שיחה מהרשימה כדי לצפות בתמליל המלא.
          </div>
        )}
      </div>
    </div>
  );
}

function ConversationRow({
  conv,
  active,
  onClick,
}: {
  conv: ConversationListItem;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <li>
      <button
        onClick={onClick}
        className={`w-full text-right px-3 py-2 rounded transition ${
          active ? "bg-gray-700 text-white" : "hover:bg-gray-750 text-gray-300"
        }`}
      >
        <div className="text-sm font-semibold">
          {conv.contact_name || conv.contact_phone || "ללא שם"}
        </div>
        <div className="text-xs text-gray-500 flex items-center justify-between mt-1">
          <span>{conv.message_count} הודעות</span>
          <span>{formatWhen(conv.last_message_at || conv.started_at)}</span>
        </div>
      </button>
    </li>
  );
}

function TranscriptView({ bot, conversationId }: { bot: WhatsAppAgentCode; conversationId: string }) {
  const q = useQuery({
    queryKey: ["whatsapp-messages", bot, conversationId],
    queryFn: () => fetchMessages(bot, conversationId),
  });

  if (q.isLoading) return <div className="text-gray-400">טוען תמליל…</div>;
  const msgs = q.data?.messages ?? [];
  if (msgs.length === 0) return <div className="text-gray-500 text-sm">אין הודעות לשיחה זו.</div>;

  return (
    <div className="space-y-2 max-h-[60vh] overflow-y-auto">
      {msgs.map((m) => (
        <MessageBubble key={m.id} msg={m} />
      ))}
    </div>
  );
}

function MessageBubble({ msg }: { msg: MessageItem }) {
  const inbound = msg.direction === "inbound";
  return (
    <div className={`flex ${inbound ? "justify-end" : "justify-start"}`}>
      <div
        className={`max-w-[80%] px-3 py-2 rounded-lg text-sm ${
          inbound
            ? "bg-gray-700 text-white"
            : "bg-emerald-900/40 border border-emerald-800 text-emerald-100"
        }`}
      >
        <div className="text-xs opacity-60 mb-1 flex items-center justify-between gap-3">
          <span>{inbound ? "המשתמש" : "🤖 הבוט"}</span>
          <span>{formatWhen(msg.created_at)}</span>
        </div>
        <div className="whitespace-pre-wrap">{msg.text || `(${msg.message_type})`}</div>
      </div>
    </div>
  );
}

// ============================================================================
// TAB 3 — Behavior (system prompt + Q&A)
// ============================================================================
function BehaviorTab({ bot }: { bot: WhatsAppAgentConfig }) {
  const qc = useQueryClient();
  const q = useQuery({
    queryKey: ["whatsapp-behavior", bot.agent_code],
    queryFn: () => fetchBehavior(bot.agent_code),
  });
  const [addendum, setAddendum] = useState("");
  const [qa, setQa] = useState<QAPair[]>([]);
  const [statusMsg, setStatusMsg] = useState<string | null>(null);

  // Seed from server whenever the bot or server data changes
  useEffect(() => {
    if (q.data) {
      setAddendum(q.data.system_prompt_addendum);
      setQa(q.data.qa_pairs);
    }
  }, [q.data?.bot_code, q.dataUpdatedAt]);

  const save = useMutation({
    mutationFn: () =>
      saveBehavior(bot.agent_code, { system_prompt_addendum: addendum, qa_pairs: qa }),
    onSuccess: () => {
      setStatusMsg("✅ נשמר");
      qc.invalidateQueries({ queryKey: ["whatsapp-behavior", bot.agent_code] });
      setTimeout(() => setStatusMsg(null), 3000);
    },
    onError: (e: Error) => setStatusMsg(`❌ ${e.message}`),
  });

  return (
    <div className="space-y-4">
      <section className="bg-gray-800 border border-gray-700 rounded-lg p-5">
        <h3 className="font-bold text-white mb-2">🧠 תוספת ל-System Prompt של {bot.name}</h3>
        <p className="text-sm text-gray-400 mb-3">
          הוראות נוספות שיתווספו לפרסונה של הבוט. שייכות אך ורק ל-{bot.name} ולא נוגעות בשאר.
        </p>
        <textarea
          value={addendum}
          onChange={(e) => setAddendum(e.target.value)}
          placeholder="לדוגמה: 'תמיד דבר בעברית. אם המשתמש מבקש מחיר, הפנה לאלעד.'"
          rows={6}
          className="w-full px-3 py-2 bg-gray-900 border border-gray-700 rounded text-white text-sm focus:border-indigo-500 outline-none"
        />
        <div className="text-xs text-gray-500 mt-1">{addendum.length}/4000 תווים</div>
      </section>

      <section className="bg-gray-800 border border-gray-700 rounded-lg p-5">
        <div className="flex items-center justify-between mb-2">
          <h3 className="font-bold text-white">📝 שאלות־ותשובות (Q&A מקוצרות)</h3>
          <button
            onClick={() => setQa((arr) => [...arr, { question: "", answer: "" }])}
            className="px-3 py-1.5 text-xs font-semibold bg-emerald-700 hover:bg-emerald-600 text-white rounded"
          >
            + הוסף Q&A
          </button>
        </div>
        <p className="text-sm text-gray-400 mb-3">
          התאמות מהירות — אם שאלת המשתמש מכילה את ה"שאלה", הבוט יחזיר את ה"תשובה" מיידית בלי
          להתייעץ עם המודל. עוזר לשמור תשובות עקביות לשאלות נפוצות.
        </p>
        {qa.length === 0 ? (
          <div className="text-sm text-gray-500 text-center py-4">אין עדיין Q&A עבור {bot.name}.</div>
        ) : (
          <ul className="space-y-2">
            {qa.map((pair, i) => (
              <li key={i} className="bg-gray-900 border border-gray-700 rounded-lg p-3 grid grid-cols-1 md:grid-cols-2 gap-3">
                <input
                  type="text"
                  placeholder="שאלה (לדוגמה: 'כמה עולה'?)"
                  value={pair.question}
                  onChange={(e) =>
                    setQa((arr) => arr.map((p, idx) => (idx === i ? { ...p, question: e.target.value } : p)))
                  }
                  className="px-3 py-2 bg-gray-800 border border-gray-700 rounded text-white text-sm"
                />
                <div className="flex gap-2">
                  <input
                    type="text"
                    placeholder="תשובה"
                    value={pair.answer}
                    onChange={(e) =>
                      setQa((arr) => arr.map((p, idx) => (idx === i ? { ...p, answer: e.target.value } : p)))
                    }
                    className="flex-1 px-3 py-2 bg-gray-800 border border-gray-700 rounded text-white text-sm"
                  />
                  <button
                    onClick={() => setQa((arr) => arr.filter((_, idx) => idx !== i))}
                    className="px-2 py-1 text-xs bg-red-900 hover:bg-red-800 text-red-200 rounded"
                    title="הסר"
                  >
                    ✕
                  </button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>

      <div className="flex items-center justify-end gap-3">
        {statusMsg && <span className="text-sm text-gray-300">{statusMsg}</span>}
        <button
          onClick={() => save.mutate()}
          disabled={save.isPending}
          className="px-5 py-2 bg-indigo-600 hover:bg-indigo-700 disabled:bg-gray-700 disabled:text-gray-500 text-white font-semibold rounded text-sm"
        >
          {save.isPending ? "שומר…" : `שמור התנהגות של ${bot.name}`}
        </button>
      </div>
    </div>
  );
}

// ============================================================================
// TAB 4 — Dashboard
// ============================================================================
function DashboardTab({ bot }: { bot: WhatsAppAgentConfig }) {
  const q = useQuery({
    queryKey: ["whatsapp-dashboard", bot.agent_code],
    queryFn: () => fetchDashboard(bot.agent_code),
    refetchInterval: 30000,
  });

  if (q.isLoading) return <div className="text-gray-400">טוען…</div>;
  if (q.error) return <ErrorBlock err={q.error as Error} />;
  const d = q.data!;

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <Stat label="סה״כ שיחות" value={d.total_conversations} tone="blue" />
        <Stat label="פעילות" value={d.active_conversations} tone="indigo" />
        <Stat label="הודעות היום" value={d.messages_today} tone="emerald" />
        <Stat label="הודעות השבוע" value={d.messages_this_week} tone="purple" />
      </div>
      <div className="grid grid-cols-2 gap-3">
        <Stat label="נכנסות (שבוע)" value={d.inbound_this_week} tone="cyan" />
        <Stat label="יוצאות (שבוע)" value={d.outbound_this_week} tone="orange" />
      </div>
      <div className={`p-4 rounded-lg border ${d.is_configured ? "bg-green-900/20 border-green-700" : "bg-yellow-900/20 border-yellow-700"}`}>
        <div className="font-semibold text-white">
          {d.is_configured ? "🟢 הבוט מחובר ל-Green API" : "🟡 הבוט לא מוגדר עדיין"}
        </div>
        <div className="text-sm text-gray-400 mt-1">
          {d.is_configured
            ? "Instance ID ו-Token הוזנו. כשהtwebhook יתחיל לקלוט הודעות הן יופיעו בטאב 'שיחות'."
            : 'יש להזין Instance ID ו-Token בטאב "הגדרות" כדי לחבר את הבוט ל-WhatsApp.'}
        </div>
      </div>
    </div>
  );
}

function Stat({
  label,
  value,
  tone,
}: {
  label: string;
  value: number | string;
  tone: "blue" | "indigo" | "emerald" | "purple" | "cyan" | "orange";
}) {
  const cls = {
    blue: "bg-blue-900/20 border-blue-700 text-blue-200",
    indigo: "bg-indigo-900/20 border-indigo-700 text-indigo-200",
    emerald: "bg-emerald-900/20 border-emerald-700 text-emerald-200",
    purple: "bg-purple-900/20 border-purple-700 text-purple-200",
    cyan: "bg-cyan-900/20 border-cyan-700 text-cyan-200",
    orange: "bg-orange-900/20 border-orange-700 text-orange-200",
  }[tone];
  return (
    <div className={`rounded-lg border px-4 py-3 ${cls}`}>
      <div className="text-xs opacity-80">{label}</div>
      <div className="text-2xl font-bold mt-1">{value}</div>
    </div>
  );
}

// ============================================================================
// TAB 5 — Playground
// ============================================================================
function PlaygroundTab({ bot }: { bot: WhatsAppAgentConfig }) {
  const [message, setMessage] = useState("");
  const [includeQa, setIncludeQa] = useState(true);
  const [result, setResult] = useState<PlaygroundResult | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const run = useMutation({
    mutationFn: () => runPlayground(bot.agent_code, message, includeQa),
    onSuccess: (r) => {
      setResult(r);
      setErr(null);
    },
    onError: (e: Error) => {
      setErr(e.message);
      setResult(null);
    },
  });

  // Clear result on bot switch
  useEffect(() => {
    setResult(null);
    setErr(null);
  }, [bot.agent_code]);

  return (
    <div className="space-y-4">
      <section className="bg-gray-800 border border-gray-700 rounded-lg p-5">
        <h3 className="font-bold text-white mb-2">🧪 בדיקת {bot.name} ללא WhatsApp</h3>
        <p className="text-sm text-gray-400 mb-3">
          שלח הודעת בדיקה — הבוט יענה כפי שהיה עונה ב-WhatsApp, עם הפרסונה וההתנהגות שהגדרת.
          לא נשלח לאף לקוח אמיתי.
        </p>
        <textarea
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          placeholder={`כתוב כאן הודעה כאילו אתה הלקוח של ${bot.name}…`}
          rows={3}
          className="w-full px-3 py-2 bg-gray-900 border border-gray-700 rounded text-white text-sm focus:border-indigo-500 outline-none"
        />
        <div className="flex items-center justify-between mt-3">
          <label className="flex items-center gap-2 text-sm text-gray-300">
            <input type="checkbox" checked={includeQa} onChange={(e) => setIncludeQa(e.target.checked)} />
            כלול Q&A מקוצרות (מסלול מהיר)
          </label>
          <button
            onClick={() => run.mutate()}
            disabled={!message.trim() || run.isPending}
            className="px-5 py-2 bg-indigo-600 hover:bg-indigo-700 disabled:bg-gray-700 disabled:text-gray-500 text-white font-semibold rounded text-sm"
          >
            {run.isPending ? "מריץ…" : `שלח אל ${bot.name}`}
          </button>
        </div>
      </section>

      {err && <ErrorBlock err={new Error(err)} />}

      {result && (
        <section className="bg-gray-800 border border-gray-700 rounded-lg p-5 space-y-4">
          {result.matched_qa && (
            <div className="bg-emerald-900/30 border border-emerald-700 rounded p-3 text-sm text-emerald-200">
              ⚡ הופעל מסלול Q&A מהיר — התאמה ל: "{result.matched_qa}"
            </div>
          )}

          <div>
            <div className="text-xs text-gray-500 mb-1">המשתמש:</div>
            <div className="bg-gray-900 rounded p-3 text-sm text-white whitespace-pre-wrap">
              {result.user_message}
            </div>
          </div>

          <div>
            <div className="text-xs text-gray-500 mb-1">תגובת הבוט:</div>
            <div className="bg-emerald-900/30 border border-emerald-800 rounded p-3 text-sm text-emerald-100 whitespace-pre-wrap">
              {result.bot_reply}
            </div>
          </div>

          <div className="text-xs text-gray-500 flex flex-wrap gap-4">
            <span>⏱️ {result.duration_ms} ms</span>
            <span>🔢 {result.tokens_used} tokens</span>
          </div>

          {result.used_system_prompt && (
            <details className="text-xs text-gray-400">
              <summary className="cursor-pointer hover:text-gray-200">צפה ב-System Prompt שנשלח</summary>
              <pre className="mt-2 p-3 bg-gray-900 rounded whitespace-pre-wrap text-gray-300">
                {result.used_system_prompt}
              </pre>
            </details>
          )}
        </section>
      )}
    </div>
  );
}

// ============================================================================
// Shared small primitives
// ============================================================================
function Field({
  label,
  value,
  onChange,
  help,
  placeholder,
  dir,
  type = "text",
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  help?: string;
  placeholder?: string;
  dir?: "ltr" | "rtl";
  type?: "text" | "password";
}) {
  return (
    <div>
      <label className="block text-sm font-semibold text-gray-300 mb-1">{label}</label>
      <input
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        dir={dir}
        autoComplete="off"
        className="w-full px-3 py-2 bg-gray-900 border border-gray-700 rounded text-white text-sm focus:border-indigo-500 outline-none"
      />
      {help && <p className="text-xs text-gray-500 mt-1">{help}</p>}
    </div>
  );
}

function ErrorBlock({ err }: { err: Error }) {
  return (
    <div className="bg-red-900/30 border border-red-700 rounded-lg p-4 text-red-200">
      שגיאה: {err.message}
    </div>
  );
}

export default WhatsAppAgentsSettingsPage;

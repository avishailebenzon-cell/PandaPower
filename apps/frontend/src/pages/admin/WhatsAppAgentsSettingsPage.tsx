/**
 * WhatsApp-agents settings — Green-API config for Tal / Elad / Pandi.
 *
 * Each agent has its OWN form, its OWN save button, and writes only to
 * its own `{code}.*` keys in system_settings. The forms are strictly
 * separated visually too, with per-agent borders/colors, so an admin
 * can't confuse one agent's credentials with another's.
 *
 * Fields per agent:
 *   • phone number     — informational only (human-readable identifier)
 *   • instance ID      — Green API instance id  ← required for connection
 *   • API token        — Green API token        ← required for connection
 *   • webhook secret   — for inbound message verification (optional)
 */

import { useEffect, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  fetchWhatsAppAgents,
  saveWhatsAppAgent,
  type WhatsAppAgentConfig,
  type WhatsAppAgentConfigUpdate,
  type WhatsAppAgentCode,
} from "@/api/whatsappAgents";

const AGENT_COLORS: Record<WhatsAppAgentCode, { border: string; accent: string }> = {
  tal: { border: "border-blue-700", accent: "text-blue-300" },
  elad: { border: "border-emerald-700", accent: "text-emerald-300" },
  pandi: { border: "border-cyan-700", accent: "text-cyan-300" },
};

function formatWhen(iso: string | null): string {
  if (!iso) return "מעולם לא נשמר";
  try {
    return new Date(iso).toLocaleString("he-IL", {
      day: "2-digit",
      month: "2-digit",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

export const WhatsAppAgentsSettingsPage = () => {
  const q = useQuery({
    queryKey: ["whatsapp-agents"],
    queryFn: fetchWhatsAppAgents,
  });

  return (
    <div dir="rtl" className="p-6 space-y-6">
      <div>
        <h1 className="text-3xl font-bold text-white flex items-center gap-2">
          <span>📞</span> הגדרות WhatsApp לסוכני AI
        </h1>
        <p className="text-gray-400 mt-1 max-w-3xl">
          חיבור ל-Green API עבור הסוכנים שמדברים דרך WhatsApp. לכל סוכן יש מופע נפרד לחלוטין —
          שינוי טוקן/מספר אצל סוכן אחד לעולם לא ייגע באחר.
        </p>
      </div>

      {q.isLoading ? (
        <div className="text-gray-400">טוען…</div>
      ) : q.error ? (
        <div className="bg-red-900/30 border border-red-700 rounded-lg p-4 text-red-200">
          שגיאה בטעינה: {String((q.error as Error).message)}
        </div>
      ) : (
        <div className="space-y-6">
          {(q.data ?? []).map((agent) => (
            <AgentCard key={agent.agent_code} agent={agent} />
          ))}
        </div>
      )}

      <InfoFooter />
    </div>
  );
};

function AgentCard({ agent }: { agent: WhatsAppAgentConfig }) {
  const queryClient = useQueryClient();
  const c = AGENT_COLORS[agent.agent_code];

  // Local form state — initialised from server, edited in isolation per card.
  const [form, setForm] = useState<WhatsAppAgentConfigUpdate>({
    instance_id: agent.instance_id,
    token: agent.token,
    whatsapp_number: agent.whatsapp_number,
    webhook_secret: agent.webhook_secret,
  });
  const [statusMsg, setStatusMsg] = useState<string | null>(null);

  // Re-seed when server data refreshes (e.g. after a successful save).
  useEffect(() => {
    setForm({
      instance_id: agent.instance_id,
      token: agent.token,
      whatsapp_number: agent.whatsapp_number,
      webhook_secret: agent.webhook_secret,
    });
  }, [agent]);

  const save = useMutation({
    mutationFn: () => saveWhatsAppAgent(agent.agent_code, form),
    onSuccess: () => {
      setStatusMsg(`✅ נשמר בהצלחה`);
      queryClient.invalidateQueries({ queryKey: ["whatsapp-agents"] });
      setTimeout(() => setStatusMsg(null), 3000);
    },
    onError: (e: Error) => setStatusMsg(`❌ שגיאה: ${e.message}`),
  });

  const dirty =
    form.instance_id !== agent.instance_id ||
    form.token !== agent.token ||
    form.whatsapp_number !== agent.whatsapp_number ||
    form.webhook_secret !== agent.webhook_secret;

  return (
    <section
      className={`bg-gray-800 border-r-4 ${c.border} border border-gray-700 rounded-lg p-5`}
    >
      {/* Header */}
      <div className="flex items-start justify-between mb-4 flex-wrap gap-2">
        <div>
          <h2 className={`text-xl font-bold ${c.accent} flex items-center gap-2`}>
            <span>{agent.emoji}</span>
            <span>{agent.name}</span>
            <span className="text-xs text-gray-500 font-normal">({agent.agent_code})</span>
          </h2>
          <p className="text-sm text-gray-400 mt-1">{agent.role}</p>
        </div>
        <div className="text-right">
          <span
            className={`px-3 py-1 rounded text-xs font-semibold ${
              agent.is_configured
                ? "bg-green-900 text-green-200"
                : "bg-yellow-900 text-yellow-200"
            }`}
          >
            {agent.is_configured ? "🟢 מוגדר" : "🟡 לא מוגדר"}
          </span>
          <div className="text-xs text-gray-500 mt-1">
            עודכן: {formatWhen(agent.last_updated_at)}
          </div>
        </div>
      </div>

      {/* Form — pure form fields, dispatched via this agent's own mutation. */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <Field
          id={`${agent.agent_code}-phone`}
          label={`📱 מספר WhatsApp של ${agent.name}`}
          help="לצורך זיהוי בלבד — מסייע לדעת לאיזה מספר הטוקן שייך."
          value={form.whatsapp_number}
          onChange={(v) => setForm((f) => ({ ...f, whatsapp_number: v }))}
          placeholder="+972501234567"
          dir="ltr"
        />
        <Field
          id={`${agent.agent_code}-instance`}
          label="Green API Instance ID"
          help="המזהה של המופע ב-Green API."
          value={form.instance_id}
          onChange={(v) => setForm((f) => ({ ...f, instance_id: v }))}
          placeholder="לדוגמה: 1101234567"
          dir="ltr"
        />
        <Field
          id={`${agent.agent_code}-token`}
          label="Green API Token"
          help="הטוקן הסודי של המופע. הוסתר אחרי שמירה."
          value={form.token}
          onChange={(v) => setForm((f) => ({ ...f, token: v }))}
          placeholder="••••••••••••••••"
          dir="ltr"
          type="password"
        />
        <Field
          id={`${agent.agent_code}-webhook`}
          label="Webhook Secret (אופציונלי)"
          help="לאימות הודעות נכנסות מ-Green API."
          value={form.webhook_secret}
          onChange={(v) => setForm((f) => ({ ...f, webhook_secret: v }))}
          placeholder=""
          dir="ltr"
          type="password"
        />
      </div>

      {/* Save row */}
      <div className="flex items-center justify-end gap-3 mt-5 pt-4 border-t border-gray-700">
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
          {save.isPending ? "שומר…" : `שמור הגדרות של ${agent.name}`}
        </button>
      </div>
    </section>
  );
}

function Field({
  id,
  label,
  help,
  value,
  onChange,
  placeholder,
  dir,
  type = "text",
}: {
  id: string;
  label: string;
  help?: string;
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  dir?: "ltr" | "rtl";
  type?: "text" | "password";
}) {
  return (
    <div>
      <label htmlFor={id} className="block text-sm font-semibold text-gray-300 mb-1">
        {label}
      </label>
      <input
        id={id}
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        dir={dir}
        className="w-full px-3 py-2 bg-gray-900 border border-gray-700 rounded text-white focus:border-indigo-500 outline-none text-sm"
        autoComplete="off"
      />
      {help && <p className="text-xs text-gray-500 mt-1">{help}</p>}
    </div>
  );
}

function InfoFooter() {
  return (
    <div className="bg-gray-800/50 border border-gray-700 rounded-lg p-4 text-sm text-gray-400 space-y-2">
      <div className="font-semibold text-gray-300">ℹ️ הערות חשובות:</div>
      <ul className="list-disc pr-5 space-y-1">
        <li>
          <strong className="text-gray-200">הפרדה מוחלטת:</strong> שמירה אצל סוכן אחד אף פעם לא
          תיגע בהגדרות של סוכן אחר. כל סוכן מתפעל מופע WhatsApp נפרד.
        </li>
        <li>
          <strong className="text-gray-200">מספר טלפון:</strong> השדה הוא לזיהוי אדם בלבד — לא
          נשלח ל-Green API. הטוקן הוא שמזהה את המופע מולם.
        </li>
        <li>
          <strong className="text-gray-200">סטטוס "מוגדר":</strong> נחשב מוגדר כאשר גם Instance
          ID וגם Token מאוכלסים — זה המינימום ל-Green API.
        </li>
      </ul>
    </div>
  );
}

export default WhatsAppAgentsSettingsPage;

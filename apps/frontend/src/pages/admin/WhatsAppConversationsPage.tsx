/**
 * Unified WhatsApp conversations hub. A row of agent buttons (Tal / Elad /
 * Pandi / Pandius) sits at the top; clicking one renders that agent's full
 * WhatsApp-style conversations screen below — the same component used on each
 * agent's dedicated "שיחות" page.
 */

import React, { useState } from "react";
import { ConversationsScreen } from "@/components/ConversationsScreen";
import type { ConversationsScreenProps } from "@/components/ConversationsScreen";
import {
  talConversationsApi,
  eladConversationsApi,
  pandiConversationsApi,
  pandiusConversationsApi,
} from "@/api/conversationsApi";
import { agentAvatar, agentAvatarFallback } from "@/data/agents";

type AgentKey = "tal" | "elad" | "pandi" | "pandius";

const AGENTS: Record<AgentKey, { label: string; props: ConversationsScreenProps }> = {
  tal: {
    label: "טל",
    props: {
      api: talConversationsApi,
      title: "שיחות של טל",
      subtitle:
        "כל השיחות של טל עם המועמדים. אפשר להתערב ולכתוב בשם טל, ולהשבית זמנית את התגובה האוטומטית.",
      backTo: "/recruiting/tal",
      contactsLabel: "מועמדים",
      agentName: "טל",
      agentGender: "f",
      agentCode: "tal",
    },
  },
  elad: {
    label: "אלעד",
    props: {
      api: eladConversationsApi,
      title: "שיחות של אלעד",
      subtitle:
        "כל השיחות של אלעד עם הלקוחות. אפשר להתערב ולכתוב בשם אלעד, ולהשבית זמנית את התגובה האוטומטית.",
      backTo: "/recruiting/elad",
      contactsLabel: "לקוחות",
      agentName: "אלעד",
      agentGender: "m",
      agentCode: "elad",
    },
  },
  pandi: {
    label: "פנדי",
    props: {
      api: pandiConversationsApi,
      title: "שיחות של פנדי",
      subtitle:
        "כל השיחות של פנדי עם הלקוחות. אפשר להתערב ולכתוב בשם פנדי, ולהשבית זמנית את התגובה האוטומטית.",
      backTo: "/recruiting/pandi",
      contactsLabel: "לקוחות",
      agentName: "פנדי",
      agentGender: "f",
      agentCode: "pandi",
    },
  },
  pandius: {
    label: "פנדיוס",
    props: {
      api: pandiusConversationsApi,
      title: "שיחות של פנדיוס",
      subtitle:
        "כל השיחות של פנדיוס עם המועמדים. אפשר להתערב ולכתוב בשם פנדיוס, ולהשבית זמנית את התגובה האוטומטית.",
      backTo: "/recruiting/pandius",
      contactsLabel: "מועמדים",
      agentName: "פנדיוס",
      agentGender: "m",
      agentCode: "pandius",
    },
  },
};

export const WhatsAppConversationsPage: React.FC = () => {
  const [selected, setSelected] = useState<AgentKey>("tal");

  return (
    <div className="p-6 space-y-4" dir="rtl">
      <div>
        <h1 className="text-2xl font-bold text-white">💬 שיחות וואטסאפ</h1>
        <p className="text-sm text-slate-400 mt-1">
          בחר סוכן כדי לצפות בשיחות הוואטסאפ שלו ולהגיב בשמו.
        </p>
      </div>

      {/* Agent selector */}
      <div className="flex flex-wrap gap-2">
        {(Object.keys(AGENTS) as AgentKey[]).map((key) => {
          const agent = AGENTS[key];
          const active = key === selected;
          return (
            <button
              key={key}
              onClick={() => setSelected(key)}
              className={`flex items-center gap-2 pl-4 pr-2 py-1.5 rounded-lg font-semibold text-sm transition ${
                active
                  ? "bg-teal-600 text-white shadow"
                  : "bg-slate-800 text-slate-300 hover:bg-slate-700"
              }`}
            >
              <img
                src={agentAvatar(key)}
                alt={agent.label}
                onError={(e) => {
                  const fb = agentAvatarFallback(key);
                  if (fb) e.currentTarget.src = fb;
                }}
                className={`w-7 h-7 rounded-full object-cover border ${
                  active ? "border-white/70" : "border-slate-600"
                }`}
              />
              {agent.label}
            </button>
          );
        })}
      </div>

      {/* Selected agent's conversations screen (remount on switch) */}
      <ConversationsScreen key={selected} {...AGENTS[selected].props} />
    </div>
  );
};

export default WhatsAppConversationsPage;

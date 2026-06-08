/** Tal's WhatsApp-style conversations screen (initial screening, candidates). */

import React from "react";
import { ConversationsScreen } from "@/components/ConversationsScreen";
import { talConversationsApi } from "@/api/conversationsApi";

export const TalConversationsPage: React.FC = () => (
  <ConversationsScreen
    api={talConversationsApi}
    title="👩‍💼 שיחות של טל"
    subtitle="כל השיחות של טל עם המועמדים. אפשר להתערב ולכתוב בשם טל, ולהשבית זמנית את התגובה האוטומטית."
    backTo="/recruiting/tal"
    contactsLabel="מועמדים"
    agentName="טל"
    agentGender="f"
  />
);

export default TalConversationsPage;

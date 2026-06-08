import React from "react";
import { ConversationsScreen } from "@/components/ConversationsScreen";
import { pandiusConversationsApi } from "@/api/conversationsApi";

export const PandiusConversationsPage: React.FC = () => (
  <ConversationsScreen
    api={pandiusConversationsApi}
    title="🐼 שיחות של פנדיוס"
    subtitle="כל השיחות של פנדיוס עם המועמדים. אפשר להתערב ולכתוב בשם פנדיוס, ולהשבית זמנית את התגובה האוטומטית."
    backTo="/recruiting/pandius"
    contactsLabel="מועמדים"
    agentName="פנדיוס"
    agentGender="m"
  />
);

export default PandiusConversationsPage;

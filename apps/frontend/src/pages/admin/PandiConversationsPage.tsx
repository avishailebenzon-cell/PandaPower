/** Pandi's WhatsApp-style conversations screen (client intake). */

import React from "react";
import { ConversationsScreen } from "@/components/ConversationsScreen";
import { pandiConversationsApi } from "@/api/conversationsApi";

export const PandiConversationsPage: React.FC = () => (
  <ConversationsScreen
    api={pandiConversationsApi}
    title="שיחות של ליבי"
    subtitle="כל השיחות של ליבי עם הלקוחות. אפשר להתערב ולכתוב בשם ליבי, ולהשבית זמנית את התגובה האוטומטית."
    backTo="/recruiting/pandi"
    contactsLabel="לקוחות"
    agentName="ליבי"
    agentGender="f"
    agentCode="pandi"
  />
);

export default PandiConversationsPage;

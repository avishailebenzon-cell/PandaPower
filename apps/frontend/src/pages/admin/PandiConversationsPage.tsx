/** Pandi's WhatsApp-style conversations screen (client intake). */

import React from "react";
import { ConversationsScreen } from "@/components/ConversationsScreen";
import { pandiConversationsApi } from "@/api/conversationsApi";

export const PandiConversationsPage: React.FC = () => (
  <ConversationsScreen
    api={pandiConversationsApi}
    title="שיחות של פנדי"
    subtitle="כל השיחות של פנדי עם הלקוחות. אפשר להתערב ולכתוב בשם פנדי, ולהשבית זמנית את התגובה האוטומטית."
    backTo="/recruiting/pandi"
    contactsLabel="לקוחות"
    agentName="פנדי"
    agentGender="f"
    agentCode="pandi"
  />
);

export default PandiConversationsPage;

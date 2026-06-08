/** Elad's WhatsApp-style conversations screen (placements, clients). */

import React from "react";
import { ConversationsScreen } from "@/components/ConversationsScreen";
import { eladConversationsApi } from "@/api/conversationsApi";

export const EladConversationsPage: React.FC = () => (
  <ConversationsScreen
    api={eladConversationsApi}
    title="🤝 שיחות של אלעד"
    subtitle="כל השיחות של אלעד עם הלקוחות. אפשר להתערב ולכתוב בשם אלעד, ולהשבית זמנית את התגובה האוטומטית."
    backTo="/recruiting/elad"
    contactsLabel="לקוחות"
    agentName="אלעד"
    agentGender="m"
  />
);

export default EladConversationsPage;

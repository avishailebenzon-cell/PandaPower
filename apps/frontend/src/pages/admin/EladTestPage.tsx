/** Elad test-conversation screen. */

import React from "react";
import { AgentTestPanel } from "@/components/AgentTestPanel";

export const EladTestPage: React.FC = () => (
  <AgentTestPanel recruiter="elad" agentName="אלעד" counterpart="לקוח" backTo="/recruiting/elad" />
);

export default EladTestPage;

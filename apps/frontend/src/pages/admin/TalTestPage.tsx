/** Tal test-conversation screen. */

import React from "react";
import { AgentTestPanel } from "@/components/AgentTestPanel";

export const TalTestPage: React.FC = () => (
  <AgentTestPanel recruiter="tal" agentName="טל" counterpart="מועמד" backTo="/recruiting/tal" />
);

export default TalTestPage;

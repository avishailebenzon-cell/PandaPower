import React from "react";

export interface MatchCardProps {
  matchId: string;
  candidateName: string;
  jobTitle: string;
  company: string;
  score: number; // 0-1
  status: string;
  daysInStage: number;
  lastActivity?: string;
  recruiter: "tal" | "elad";
  onAction: (action: "conversation" | "decision" | "placement") => void;
}

// Status label mappings
const STATUS_LABELS: Record<string, { hebrew: string; color: string }> = {
  carmit_approved: { hebrew: "אושר על ידי כרמית", color: "bg-green-900" },
  sent_to_tal: { hebrew: "ממתין לטל", color: "bg-yellow-900" },
  tal_conversation: { hebrew: "בשיחה עם טל", color: "bg-blue-900" },
  tal_approved: { hebrew: "אושר על ידי טל", color: "bg-green-800" },
  tal_rejected: { hebrew: "דחוי על ידי טל", color: "bg-red-900" },
  sent_to_elad: { hebrew: "ממתין לאלד", color: "bg-purple-900" },
  elad_conversation: { hebrew: "בשיחה עם אלד", color: "bg-blue-800" },
  elad_approved: { hebrew: "אושר על ידי אלד", color: "bg-green-700" },
  hired: { hebrew: "הובא", color: "bg-green-600" },
  placement_failed: { hebrew: "כישל", color: "bg-red-900" },
};

const MatchCard: React.FC<MatchCardProps> = ({
  matchId,
  candidateName,
  jobTitle,
  company,
  score,
  status,
  daysInStage,
  lastActivity,
  recruiter,
  onAction,
}) => {
  const statusInfo = STATUS_LABELS[status] || { hebrew: status, color: "bg-gray-600" };
  const scorePercentage = Math.round(score * 100);

  // Determine score color based on thresholds
  const getScoreColor = () => {
    if (score > 0.8) return "bg-green-500";
    if (score > 0.7) return "bg-yellow-500";
    return "bg-red-500";
  };

  // Determine which buttons to show based on recruiter and status
  const getAvailableActions = () => {
    const actions: Array<"conversation" | "decision" | "placement"> = [];

    if (recruiter === "tal") {
      if (status === "sent_to_tal" || status === "tal_conversation") {
        actions.push("conversation", "decision");
      }
    } else if (recruiter === "elad") {
      if (status === "sent_to_elad" || status === "elad_conversation") {
        actions.push("conversation");
        if (status === "elad_conversation") {
          actions.push("placement");
        }
      }
    }

    return actions;
  };

  const availableActions = getAvailableActions();

  return (
    <div className="bg-gray-800 p-4 rounded-lg border border-gray-700 hover:border-gray-500 transition-colors">
      {/* Header: Name and Status */}
      <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-3 mb-3">
        <div className="text-right flex-1">
          <h3 className="text-lg font-semibold text-white text-right">
            {candidateName}
          </h3>
          <p className="text-sm text-gray-400 text-right">
            {jobTitle} @ {company}
          </p>
        </div>
        <span className={`${statusInfo.color} text-white text-xs font-semibold px-3 py-1 rounded-full whitespace-nowrap`}>
          {statusInfo.hebrew}
        </span>
      </div>

      {/* Score Progress Bar */}
      <div className="mb-3">
        <div className="flex justify-between items-center mb-1">
          <span className="text-xs font-medium text-gray-400">ציון התאמה</span>
          <span className="text-sm font-bold text-gray-300">{scorePercentage}%</span>
        </div>
        <div className="w-full bg-gray-600 rounded-full h-2">
          <div
            className={`${getScoreColor()} h-2 rounded-full transition-all duration-300`}
            style={{ width: `${scorePercentage}%` }}
          />
        </div>
      </div>

      {/* Metadata: Days in Stage & Last Activity */}
      <div className="flex justify-between items-center mb-4 text-sm text-gray-400">
        <div className="text-right">
          <span className="font-medium">{daysInStage}</span> ימים בשלב
        </div>
        {lastActivity && (
          <div className="text-left">
            פעילות לפני {lastActivity}
          </div>
        )}
      </div>

      {/* Action Buttons */}
      <div className="flex gap-2 justify-end">
        {availableActions.map((action) => {
          const actionLabels: Record<string, string> = {
            conversation: "הוסף שיחה",
            decision: "הוסף החלטה",
            placement: "תוצאה סופית",
          };

          const actionColors: Record<string, string> = {
            conversation: "bg-blue-600 hover:bg-blue-700",
            decision: "bg-purple-600 hover:bg-purple-700",
            placement: "bg-green-600 hover:bg-green-700",
          };

          return (
            <button
              key={action}
              onClick={() => onAction(action)}
              className={`${actionColors[action]} text-white text-sm font-semibold px-3 py-2 rounded transition-colors`}
            >
              {actionLabels[action]}
            </button>
          );
        })}
      </div>

      {/* Match ID for debugging */}
      <div className="text-xs text-gray-600 mt-3 text-right">
        ID: {matchId.substring(0, 8)}...
      </div>
    </div>
  );
};

export default MatchCard;

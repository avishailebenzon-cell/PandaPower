import React, { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import MatchCard from "../../components/MatchCard";
import { MatchJourneyTimeline } from "../../components/MatchJourneyTimeline";
import {
  fetchRecruiterStatus,
  fetchRecruiterMatches,
  type Match,
  type StatusMetrics,
} from "@/api/recruiter";

interface ConversationModalState {
  show: boolean;
  matchId: string | null;
  recruiter: "tal" | "elad";
}

interface DecisionModalState {
  show: boolean;
  matchId: string | null;
  recruiter: "tal" | "elad";
}

interface PlacementModalState {
  show: boolean;
  matchId: string | null;
}

// Mock API calls for mutations
const recordConversation = async (
  matchId: string,
  recruiterName: "tal" | "elad",
  summary: string,
  date?: string
) => {
  const response = await fetch(
    `/api/admin/pipedrive/recruiter-workflow/record-conversation/${matchId}`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        recruiter_name: recruiterName,
        conversation_summary: summary,
        conversation_date: date,
      }),
    }
  );
  if (!response.ok) throw new Error("Failed to record conversation");
  return response.json();
};

const recordDecision = async (
  matchId: string,
  recruiterName: "tal" | "elad",
  decision: "accepted" | "rejected",
  reason: string
) => {
  const response = await fetch(
    `/api/admin/pipedrive/recruiter-workflow/record-decision/${matchId}`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        recruiter_name: recruiterName,
        decision,
        decision_reason: reason,
      }),
    }
  );
  if (!response.ok) throw new Error("Failed to record decision");
  return response.json();
};

const recordPlacement = async (
  matchId: string,
  outcome: "hired" | "placement_failed",
  notes: string
) => {
  const response = await fetch(
    `/api/admin/pipedrive/recruiter-workflow/record-placement/${matchId}`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ outcome, notes }),
    }
  );
  if (!response.ok) throw new Error("Failed to record placement");
  return response.json();
};

// Status Card Component
const StatusCard: React.FC<{ label: string; value: number; color: string }> = ({
  label,
  value,
  color,
}) => (
  <div className={`${color} p-4 rounded-lg border border-gray-700`}>
    <p className="text-gray-300 text-sm font-medium text-right">{label}</p>
    <p className="text-4xl font-bold text-white text-right mt-2">{value}</p>
  </div>
);

// Conversation Modal
const ConversationModal: React.FC<{
  state: ConversationModalState;
  onClose: () => void;
  onSubmit: (summary: string, date?: string) => void;
  isLoading: boolean;
}> = ({ state, onClose, onSubmit, isLoading }) => {
  const [summary, setSummary] = useState("");
  const [date, setDate] = useState("");

  if (!state.show || !state.matchId) return null;

  const handleSubmit = () => {
    if (!summary.trim()) {
      alert("אנא הוסף תיאור של השיחה");
      return;
    }
    onSubmit(summary, date || undefined);
    setSummary("");
    setDate("");
  };

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <div className="bg-gray-800 p-6 rounded-lg border border-gray-600 max-w-md w-full mx-4">
        <h2 className="text-xl font-bold text-white text-right mb-4">
          הוסף שיחה עם {state.recruiter === "tal" ? "טל" : "אלד"}
        </h2>

        <label className="block text-right text-gray-300 text-sm font-medium mb-2">
          תיאור השיחה
        </label>
        <textarea
          value={summary}
          onChange={(e) => setSummary(e.target.value)}
          placeholder="תאר את השיחה עם המועמד..."
          className="w-full bg-gray-700 text-white border border-gray-600 rounded p-2 text-right mb-4 focus:outline-none focus:border-blue-500"
          rows={4}
        />

        <label className="block text-right text-gray-300 text-sm font-medium mb-2">
          תאריך השיחה (אופציונלי)
        </label>
        <input
          type="date"
          value={date}
          onChange={(e) => setDate(e.target.value)}
          className="w-full bg-gray-700 text-white border border-gray-600 rounded p-2 mb-4 focus:outline-none focus:border-blue-500"
        />

        <div className="flex gap-2 justify-end">
          <button
            onClick={onClose}
            disabled={isLoading}
            className="px-4 py-2 rounded text-sm font-semibold bg-gray-700 hover:bg-gray-600 text-white disabled:opacity-50"
          >
            ביטול
          </button>
          <button
            onClick={handleSubmit}
            disabled={isLoading}
            className="px-4 py-2 rounded text-sm font-semibold bg-blue-600 hover:bg-blue-700 text-white disabled:opacity-50"
          >
            {isLoading ? "שומר..." : "שמור שיחה"}
          </button>
        </div>
      </div>
    </div>
  );
};

// Decision Modal
const DecisionModal: React.FC<{
  state: DecisionModalState;
  onClose: () => void;
  onSubmit: (decision: "accepted" | "rejected", reason: string) => void;
  isLoading: boolean;
}> = ({ state, onClose, onSubmit, isLoading }) => {
  const [decision, setDecision] = useState<"accepted" | "rejected">("accepted");
  const [reason, setReason] = useState("");

  if (!state.show || !state.matchId) return null;

  const handleSubmit = () => {
    if (!reason.trim()) {
      alert("אנא הסבר את ההחלטה");
      return;
    }
    onSubmit(decision, reason);
    setReason("");
    setDecision("accepted");
  };

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <div className="bg-gray-800 p-6 rounded-lg border border-gray-600 max-w-md w-full mx-4">
        <h2 className="text-xl font-bold text-white text-right mb-4">
          הוסף החלטה מ{state.recruiter === "tal" ? "טל" : "אלד"}
        </h2>

        <div className="mb-4 text-right">
          <label className="block text-gray-300 text-sm font-medium mb-3">
            בחר החלטה
          </label>
          <div className="flex flex-col gap-2">
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="radio"
                name="decision"
                value="accepted"
                checked={decision === "accepted"}
                onChange={(e) => setDecision("accepted")}
                className="cursor-pointer"
              />
              <span className="text-gray-300">✓ אישור</span>
            </label>
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="radio"
                name="decision"
                value="rejected"
                checked={decision === "rejected"}
                onChange={(e) => setDecision("rejected")}
                className="cursor-pointer"
              />
              <span className="text-gray-300">✗ דחיה</span>
            </label>
          </div>
        </div>

        <label className="block text-right text-gray-300 text-sm font-medium mb-2">
          נימוק
        </label>
        <textarea
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          placeholder="הסבר את ההחלטה..."
          className="w-full bg-gray-700 text-white border border-gray-600 rounded p-2 text-right mb-4 focus:outline-none focus:border-blue-500"
          rows={3}
        />

        <div className="flex gap-2 justify-end">
          <button
            onClick={onClose}
            disabled={isLoading}
            className="px-4 py-2 rounded text-sm font-semibold bg-gray-700 hover:bg-gray-600 text-white disabled:opacity-50"
          >
            ביטול
          </button>
          <button
            onClick={handleSubmit}
            disabled={isLoading}
            className={`px-4 py-2 rounded text-sm font-semibold text-white disabled:opacity-50 ${
              decision === "accepted"
                ? "bg-green-600 hover:bg-green-700"
                : "bg-red-600 hover:bg-red-700"
            }`}
          >
            {isLoading ? "שומר..." : "שמור החלטה"}
          </button>
        </div>
      </div>
    </div>
  );
};

// Placement Modal (Elad only)
const PlacementModal: React.FC<{
  state: PlacementModalState;
  onClose: () => void;
  onSubmit: (outcome: "hired" | "placement_failed", notes: string) => void;
  isLoading: boolean;
}> = ({ state, onClose, onSubmit, isLoading }) => {
  const [outcome, setOutcome] = useState<"hired" | "placement_failed">("hired");
  const [notes, setNotes] = useState("");

  if (!state.show || !state.matchId) return null;

  const handleSubmit = () => {
    onSubmit(outcome, notes);
    setNotes("");
    setOutcome("hired");
  };

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <div className="bg-gray-800 p-6 rounded-lg border border-gray-600 max-w-md w-full mx-4">
        <h2 className="text-xl font-bold text-white text-right mb-4">
          תוצאה סופית
        </h2>

        <div className="mb-4 text-right">
          <label className="block text-gray-300 text-sm font-medium mb-3">
            בחר תוצאה
          </label>
          <div className="flex flex-col gap-2">
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="radio"
                name="outcome"
                value="hired"
                checked={outcome === "hired"}
                onChange={(e) => setOutcome("hired")}
                className="cursor-pointer"
              />
              <span className="text-gray-300">✓ הובא</span>
            </label>
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="radio"
                name="outcome"
                value="placement_failed"
                checked={outcome === "placement_failed"}
                onChange={(e) => setOutcome("placement_failed")}
                className="cursor-pointer"
              />
              <span className="text-gray-300">✗ כישל</span>
            </label>
          </div>
        </div>

        <label className="block text-right text-gray-300 text-sm font-medium mb-2">
          הערות (אופציונלי)
        </label>
        <textarea
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          placeholder="הוסף הערות לגבי התוצאה..."
          className="w-full bg-gray-700 text-white border border-gray-600 rounded p-2 text-right mb-4 focus:outline-none focus:border-blue-500"
          rows={3}
        />

        <div className="flex gap-2 justify-end">
          <button
            onClick={onClose}
            disabled={isLoading}
            className="px-4 py-2 rounded text-sm font-semibold bg-gray-700 hover:bg-gray-600 text-white disabled:opacity-50"
          >
            ביטול
          </button>
          <button
            onClick={handleSubmit}
            disabled={isLoading}
            className={`px-4 py-2 rounded text-sm font-semibold text-white disabled:opacity-50 ${
              outcome === "hired"
                ? "bg-green-600 hover:bg-green-700"
                : "bg-red-600 hover:bg-red-700"
            }`}
          >
            {isLoading ? "שומר..." : "שמור תוצאה"}
          </button>
        </div>
      </div>
    </div>
  );
};

// Main RecruiterDashboard Component
export const RecruiterDashboard: React.FC = () => {
  const queryClient = useQueryClient();
  const [activeTab, setActiveTab] = useState<
    "tal-queue" | "tal-history" | "elad-queue" | "elad-history"
  >("tal-queue");
  const [conversationModal, setConversationModal] = useState<ConversationModalState>({
    show: false,
    matchId: null,
    recruiter: "tal",
  });
  const [decisionModal, setDecisionModal] = useState<DecisionModalState>({
    show: false,
    matchId: null,
    recruiter: "tal",
  });
  const [placementModal, setPlacementModal] = useState<PlacementModalState>({
    show: false,
    matchId: null,
  });
  const [selectedMatchForTimeline, setSelectedMatchForTimeline] = useState<string | null>(null);

  // React Query hooks
  const { data: statusMetrics = {} as StatusMetrics } = useQuery({
    queryKey: ["recruiter-status"],
    queryFn: fetchRecruiterStatus,
    refetchInterval: 10000,
  });

  const { data: matchesData = { matches: [], total: 0, page: 1, limit: 50 } } = useQuery({
    queryKey: ["recruiter-matches", activeTab],
    queryFn: () => fetchRecruiterMatches(activeTab, 50, 1),
    refetchInterval: 10000,
  });

  // Fetch match history when a match is selected
  const { data: matchHistory } = useQuery({
    queryKey: ["match-history", selectedMatchForTimeline],
    queryFn: async () => {
      if (!selectedMatchForTimeline) return null;
      const response = await fetch(`/api/admin/matches/${selectedMatchForTimeline}/history`);
      if (!response.ok) throw new Error("Failed to fetch match history");
      return response.json();
    },
    enabled: !!selectedMatchForTimeline,
  });

  const matches = matchesData.matches || [];

  // Mutations
  const conversationMutation = useMutation({
    mutationFn: ({
      matchId,
      recruiterName,
      summary,
      date,
    }: {
      matchId: string;
      recruiterName: "tal" | "elad";
      summary: string;
      date?: string;
    }) => recordConversation(matchId, recruiterName, summary, date),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["recruiter-matches"] });
      queryClient.invalidateQueries({ queryKey: ["recruiter-status"] });
      setConversationModal({ show: false, matchId: null, recruiter: "tal" });
    },
  });

  const decisionMutation = useMutation({
    mutationFn: ({
      matchId,
      recruiterName,
      decision,
      reason,
    }: {
      matchId: string;
      recruiterName: "tal" | "elad";
      decision: "accepted" | "rejected";
      reason: string;
    }) => recordDecision(matchId, recruiterName, decision, reason),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["recruiter-matches"] });
      queryClient.invalidateQueries({ queryKey: ["recruiter-status"] });
      setDecisionModal({ show: false, matchId: null, recruiter: "tal" });
    },
  });

  const placementMutation = useMutation({
    mutationFn: ({
      matchId,
      outcome,
      notes,
    }: {
      matchId: string;
      outcome: "hired" | "placement_failed";
      notes: string;
    }) => recordPlacement(matchId, outcome, notes),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["recruiter-matches"] });
      queryClient.invalidateQueries({ queryKey: ["recruiter-status"] });
      setPlacementModal({ show: false, matchId: null });
    },
  });

  // Event handlers
  const handleMatchAction = (
    matchId: string,
    recruiter: "tal" | "elad",
    action: "conversation" | "decision" | "placement"
  ) => {
    if (action === "conversation") {
      setConversationModal({ show: true, matchId, recruiter });
    } else if (action === "decision") {
      setDecisionModal({ show: true, matchId, recruiter });
    } else if (action === "placement") {
      setPlacementModal({ show: true, matchId });
    }
  };

  const handleConversationSubmit = (summary: string, date?: string) => {
    if (conversationModal.matchId) {
      conversationMutation.mutate({
        matchId: conversationModal.matchId,
        recruiterName: conversationModal.recruiter,
        summary,
        date,
      });
    }
  };

  const handleDecisionSubmit = (decision: "accepted" | "rejected", reason: string) => {
    if (decisionModal.matchId) {
      decisionMutation.mutate({
        matchId: decisionModal.matchId,
        recruiterName: decisionModal.recruiter,
        decision,
        reason,
      });
    }
  };

  const handlePlacementSubmit = (outcome: "hired" | "placement_failed", notes: string) => {
    if (placementModal.matchId) {
      placementMutation.mutate({
        matchId: placementModal.matchId,
        outcome,
        notes,
      });
    }
  };

  // Determine recruiter type from active tab
  const currentRecruiter = activeTab.includes("tal") ? "tal" : "elad";

  // Get selected match data
  const selectedMatch = matches.find(m => m.id === selectedMatchForTimeline);

  // Timeline Modal
  const TimelineModal = () => {
    if (!selectedMatchForTimeline || !selectedMatch) return null;

    return (
      <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 overflow-y-auto">
        <div className="bg-gray-900 p-6 rounded-lg border border-gray-700 max-w-2xl w-full mx-4 my-8">
          <div className="flex justify-between items-center mb-4">
            <button
              onClick={() => setSelectedMatchForTimeline(null)}
              className="text-gray-400 hover:text-white text-2xl"
            >
              ×
            </button>
            <h2 className="text-2xl font-bold text-white">מסלול התאמה</h2>
          </div>

          {matchHistory ? (
            <MatchJourneyTimeline
              currentState={selectedMatch?.state || "found"}
              stateHistory={matchHistory.stateHistory || []}
              candidateName={selectedMatch?.candidateName}
              jobTitle={selectedMatch?.jobTitle}
            />
          ) : (
            <div className="text-center py-8 text-gray-400">טוען...</div>
          )}

          <div className="flex justify-end mt-6">
            <button
              onClick={() => setSelectedMatchForTimeline(null)}
              className="px-4 py-2 rounded text-sm font-semibold bg-gray-700 hover:bg-gray-600 text-white"
            >
              סגור
            </button>
          </div>
        </div>
      </div>
    );
  };

  return (
    <div dir="rtl" className="min-h-screen bg-gray-900 p-8">
      <div className="max-w-7xl mx-auto">
        {/* Header */}
        <div className="mb-8">
          <h1 className="text-4xl font-bold text-white text-right">מנהל מגייסים</h1>
          <p className="text-gray-400 text-right mt-2">
            ניהול התאמות מועמדים ודעו"ת מגייסים
          </p>
        </div>

        {/* Status Cards Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 mb-8">
          <StatusCard
            label="ממתינים לטל"
            value={statusMetrics.pendingTal || 0}
            color="bg-yellow-900"
          />
          <StatusCard
            label="בשיחה עם טל"
            value={statusMetrics.inConversationTal || 0}
            color="bg-blue-900"
          />
          <StatusCard
            label="ממתינים לאלד"
            value={statusMetrics.awaitingElad || 0}
            color="bg-purple-900"
          />
          <StatusCard
            label="בשיחה עם אלד"
            value={statusMetrics.inConversationElad || 0}
            color="bg-blue-800"
          />
          <StatusCard
            label="הובאו"
            value={statusMetrics.hired || 0}
            color="bg-green-900"
          />
          <StatusCard
            label="כישלו"
            value={statusMetrics.failed || 0}
            color="bg-red-900"
          />
        </div>

        {/* Tab Navigation */}
        <div className="mb-6 border-b border-gray-700 flex gap-0 justify-end">
          {[
            { id: "tal-queue", label: "תור לטל" },
            { id: "tal-history", label: "היסטוריית טל" },
            { id: "elad-queue", label: "תור לאלד" },
            { id: "elad-history", label: "היסטוריית אלד" },
          ].map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id as any)}
              className={`px-4 py-3 text-right font-medium transition-colors ${
                activeTab === tab.id
                  ? "text-blue-400 border-b-2 border-blue-400"
                  : "text-gray-400 hover:text-gray-300"
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>

        {/* Match List */}
        <div className="space-y-4">
          {matches.length === 0 ? (
            <div className="text-center py-12 text-gray-400">
              אין התאמות לתצוגה בקטגוריה זו
            </div>
          ) : (
            matches.map((match) => (
              <div key={match.id} className="flex gap-2">
                <MatchCard
                  matchId={match.id}
                  candidateName={match.candidateName}
                  jobTitle={match.jobTitle}
                  company={match.company}
                  score={match.matchScore}
                  status={match.state}
                  daysInStage={Math.floor(
                    (Date.now() - new Date(match.createdAt).getTime()) / (1000 * 60 * 60 * 24)
                  )}
                  lastActivity={match.lastActivity}
                  recruiter={currentRecruiter}
                  onAction={(action) =>
                    handleMatchAction(match.id, currentRecruiter, action)
                  }
                />
                <button
                  onClick={() => setSelectedMatchForTimeline(match.id)}
                  className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded font-semibold transition text-sm whitespace-nowrap h-fit"
                  title="צפה במסלול ההתאמה המלא"
                >
                  📍 מסלול
                </button>
              </div>
            ))
          )}
        </div>

        {/* Timeline Modal */}
        <TimelineModal />

        {/* Modals */}
        <ConversationModal
          state={conversationModal}
          onClose={() => setConversationModal({ show: false, matchId: null, recruiter: "tal" })}
          onSubmit={handleConversationSubmit}
          isLoading={conversationMutation.isPending}
        />

        <DecisionModal
          state={decisionModal}
          onClose={() => setDecisionModal({ show: false, matchId: null, recruiter: "tal" })}
          onSubmit={handleDecisionSubmit}
          isLoading={decisionMutation.isPending}
        />

        <PlacementModal
          state={placementModal}
          onClose={() => setPlacementModal({ show: false, matchId: null })}
          onSubmit={handlePlacementSubmit}
          isLoading={placementMutation.isPending}
        />
      </div>
    </div>
  );
};

export default RecruiterDashboard;

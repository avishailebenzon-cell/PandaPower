/**
 * Match Journey Timeline Component
 * Displays the complete state machine journey from match found through final placement
 */

import React from 'react';

interface StateStep {
  state: string;
  label: string;
  icon: string;
  description: string;
  timestamp?: string;
  color: string;
}

interface MatchJourneyProps {
  currentState: string;
  stateHistory?: Array<{
    from_state: string;
    to_state: string;
    created_at: string;
    details?: Record<string, any>;
  }>;
  candidateName?: string;
  jobTitle?: string;
}

const STATE_STEPS: Record<string, StateStep> = {
  found: {
    state: 'found',
    label: 'התאמה נמצאה',
    icon: '🔍',
    description: 'הסוכן מצא התאמה פוטנציאלית',
    color: 'blue',
  },
  carmit_approved: {
    state: 'carmit_approved',
    label: 'אושרה על ידי כרמית',
    icon: '✅',
    description: 'כרמית אישרה את ההתאמה לאחר בדיקת 5 שערים',
    color: 'green',
  },
  carmit_rejected: {
    state: 'carmit_rejected',
    label: 'נדחתה על ידי כרמית',
    icon: '❌',
    description: 'כרמית דחתה את ההתאמה - לא עומדת בתנאים',
    color: 'red',
  },
  sent_to_tal: {
    state: 'sent_to_tal',
    label: 'הועברה לטל',
    icon: '📞',
    description: 'ההתאמה הועברה לטל לבדיקה ראשונית',
    color: 'yellow',
  },
  tal_conversation: {
    state: 'tal_conversation',
    label: 'שיחה עם טל',
    icon: '💬',
    description: 'טל מנהלת שיחה עם המועמד',
    color: 'cyan',
  },
  tal_approved: {
    state: 'tal_approved',
    label: 'אושר על ידי טל',
    icon: '👍',
    description: 'טל אישרה את המועמד - העביר טופס מועמד',
    color: 'green',
  },
  tal_rejected: {
    state: 'tal_rejected',
    label: 'נדחה על ידי טל',
    icon: '❌',
    description: 'טל דחתה את המועמד לאחר שיחה',
    color: 'red',
  },
  sent_to_elad: {
    state: 'sent_to_elad',
    label: 'הועבר לאלעד',
    icon: '👤',
    description: 'כרמית העבירה את ההתאמה לאלעד - הסוכן הממקם',
    color: 'purple',
  },
  elad_conversation: {
    state: 'elad_conversation',
    label: 'שיחה עם אלעד',
    icon: '💬',
    description: 'אלעד מנהל שיחה בנוגע להעברה ללקוח',
    color: 'cyan',
  },
  offer_sent: {
    state: 'offer_sent',
    label: 'הצעה נשלחה ללקוח',
    icon: '🤝',
    description: 'אלעד שלח את המועמד ללקוח דרך דוא"ל או WhatsApp',
    color: 'orange',
  },
  hired: {
    state: 'hired',
    label: 'התקבל לעבודה! 🎉',
    icon: '💼',
    description: 'המועמד התקבל לעבודה - סיום המשימה בהצלחה',
    color: 'green',
  },
  placement_failed: {
    state: 'placement_failed',
    label: 'ממקום נכשל',
    icon: '❌',
    description: 'ההממקום נכשל - המועמד דחה את ההצעה או הלקוח דחה',
    color: 'red',
  },
};

export const MatchJourneyTimeline: React.FC<MatchJourneyProps> = ({
  currentState,
  stateHistory = [],
  candidateName = 'מועמד',
  jobTitle = 'משרה',
}) => {
  // Define the standard flow sequence
  const standardFlow = [
    'found',
    'carmit_approved',
    'sent_to_tal',
    'tal_conversation',
    'tal_approved',
    'sent_to_elad',
    'elad_conversation',
    'offer_sent',
    'hired',
  ];

  // Alternative rejection paths
  const isRejected = ['carmit_rejected', 'tal_rejected', 'placement_failed'].includes(currentState);

  // Determine which steps are completed
  const completedStates = new Set(stateHistory.map(h => h.to_state));
  completedStates.add(currentState);

  // Get the next expected state based on current state
  const getNextState = (state: string): string | null => {
    const currentIndex = standardFlow.indexOf(state);
    if (currentIndex === -1 || currentIndex === standardFlow.length - 1) return null;
    return standardFlow[currentIndex + 1];
  };

  // Get step timeline (only show relevant steps)
  const getVisibleSteps = () => {
    if (isRejected) {
      // Show steps up to rejection
      if (currentState === 'carmit_rejected') {
        return ['found', 'carmit_approved', 'carmit_rejected'];
      } else if (currentState === 'tal_rejected') {
        return ['found', 'carmit_approved', 'sent_to_tal', 'tal_conversation', 'tal_approved', 'tal_rejected'];
      } else if (currentState === 'placement_failed') {
        return [...standardFlow.slice(0, standardFlow.indexOf('hired')), 'placement_failed'];
      }
    }
    // Show full journey
    return standardFlow;
  };

  const visibleSteps = getVisibleSteps();
  const currentStepIndex = visibleSteps.indexOf(currentState);

  return (
    <div className="bg-gray-800 border border-gray-700 rounded-lg p-6 mb-6" dir="rtl">
      {/* Header */}
      <div className="mb-6">
        <h2 className="text-2xl font-bold text-white mb-2">📍 מסלול ההתאמה המלא</h2>
        <p className="text-gray-400 text-sm">
          <span className="font-semibold">{candidateName}</span> עבור <span className="font-semibold">{jobTitle}</span>
        </p>
      </div>

      {/* Timeline */}
      <div className="space-y-4">
        {visibleSteps.map((stateKey, index) => {
          const step = STATE_STEPS[stateKey];
          const isCompleted = completedStates.has(stateKey);
          const isCurrentStep = stateKey === currentState;
          const isPastStep = index < currentStepIndex;
          const isNextStep = index === currentStepIndex + 1;

          // Get timestamp from history
          const stepHistoryEntry = stateHistory.find(h => h.to_state === stateKey);
          const timestamp = stepHistoryEntry?.created_at
            ? new Date(stepHistoryEntry.created_at).toLocaleDateString('he-IL', {
                month: 'short',
                day: 'numeric',
                hour: '2-digit',
                minute: '2-digit',
              })
            : null;

          return (
            <div key={stateKey} className="flex items-start gap-4">
              {/* Timeline dot and line */}
              <div className="flex flex-col items-center pt-1">
                <div
                  className={`w-10 h-10 rounded-full flex items-center justify-center font-bold text-lg transition ${
                    isCompleted
                      ? `bg-${step.color}-600 text-white`
                      : isCurrentStep
                      ? `bg-${step.color}-500 text-white animate-pulse`
                      : isNextStep
                      ? `bg-gray-700 text-gray-300 border-2 border-${step.color}-500`
                      : 'bg-gray-700 text-gray-500'
                  }`}
                >
                  {step.icon}
                </div>
                {index < visibleSteps.length - 1 && (
                  <div
                    className={`w-1 h-12 my-1 transition ${
                      isCompleted ? `bg-${step.color}-600` : 'bg-gray-700'
                    }`}
                  />
                )}
              </div>

              {/* Step content */}
              <div className="flex-1 pt-1">
                <div className="flex items-center justify-between mb-1">
                  <h3
                    className={`font-semibold text-lg transition ${
                      isCompleted
                        ? 'text-white'
                        : isCurrentStep
                        ? 'text-blue-400'
                        : isNextStep
                        ? 'text-gray-300'
                        : 'text-gray-500'
                    }`}
                  >
                    {step.label}
                  </h3>
                  {isCurrentStep && (
                    <span className="px-2 py-1 bg-blue-900 text-blue-200 text-xs rounded font-semibold">
                      🔄 שלב נוכחי
                    </span>
                  )}
                  {isPastStep && (
                    <span className="px-2 py-1 bg-green-900 text-green-200 text-xs rounded font-semibold">
                      ✅ הושלם
                    </span>
                  )}
                </div>

                <p className="text-gray-400 text-sm mb-2">{step.description}</p>

                {timestamp && (
                  <p className="text-gray-500 text-xs">⏰ {timestamp}</p>
                )}

                {/* Show gate details if available */}
                {stepHistoryEntry?.details?.gate_results && (
                  <div className="mt-3 bg-gray-900 rounded p-3 text-xs">
                    <p className="text-gray-300 font-semibold mb-2">תוצאות בדיקה:</p>
                    <div className="space-y-1">
                      {Object.entries(stepHistoryEntry.details.gate_results).map(
                        ([gateName, gateResult]: [string, any]) => (
                          <div key={gateName} className="flex items-center gap-2">
                            <span className={gateResult.passed ? '✅' : '❌'} />
                            <span className="text-gray-400">{gateName}</span>
                            {gateResult.reason && (
                              <span className="text-gray-500">({gateResult.reason})</span>
                            )}
                          </div>
                        )
                      )}
                    </div>
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {/* Footer with status */}
      <div className="mt-8 pt-6 border-t border-gray-700">
        <div
          className={`p-4 rounded-lg ${
            isRejected
              ? 'bg-red-900 text-red-100'
              : currentState === 'hired'
              ? 'bg-green-900 text-green-100'
              : 'bg-blue-900 text-blue-100'
          }`}
        >
          {isRejected && (
            <p>
              ❌ <span className="font-semibold">ההתאמה נדחתה</span> - המשוב שקיבלנו יישמר להמשך הניסיונות
            </p>
          )}
          {currentState === 'hired' && (
            <p>
              🎉 <span className="font-semibold">מזל טוב!</span> - המועמד התקבל לעבודה בהצלחה!
            </p>
          )}
          {!isRejected && currentState !== 'hired' && (
            <p>
              🔄 <span className="font-semibold">התהליך בהתקדמות</span> - השלב הבא: {STATE_STEPS[getNextState(currentState) || '']?.label}
            </p>
          )}
        </div>
      </div>
    </div>
  );
};

export default MatchJourneyTimeline;

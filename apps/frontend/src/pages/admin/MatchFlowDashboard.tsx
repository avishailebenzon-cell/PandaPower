/**
 * Match Flow Pipeline Dashboard
 * Visualizes matches through the recruitment pipeline:
 * Found → Carmit Approved → Tal Screening → Elad Placement → Hired/Rejected
 *
 * Shows:
 * - Visual funnel of match progression
 * - KPI cards for each stage
 * - Detailed tables for deep inspection
 * - Bottleneck detection & recommendations
 */

import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';

interface MatchFlowMetrics {
  stage_found: number;
  stage_carmit_approved: number;
  stage_sent_to_tal: number;
  stage_tal_conversation: number;
  stage_tal_accepted: number;
  stage_sent_to_elad: number;
  stage_hired: number;
  stage_rejected_tal: number;
  stage_rejected_elad: number;
  total_in_pipeline: number;
  total_completed: number;
  success_rate: number;
  avg_time_in_tal: number;
  avg_time_in_elad: number;
}

interface Match {
  id: string;
  candidate_name: string;
  job_title: string;
  match_score: number;
  current_state: string;
  created_at: string;
  updated_at: string;
  tal_summary?: string;
  carmit_review_notes?: string;
}

const STAGE_CONFIG = [
  { id: 'found', label: '🔍 התאמות טריות', color: 'bg-blue-600', textColor: 'text-blue-100' },
  { id: 'carmit_approved', label: '✅ אושר ע"י קרמית', color: 'bg-indigo-600', textColor: 'text-indigo-100' },
  { id: 'sent_to_tal', label: '👤 אצל טל', color: 'bg-purple-600', textColor: 'text-purple-100' },
  { id: 'tal_conversation', label: '💬 בשיחה עם טל', color: 'bg-pink-600', textColor: 'text-pink-100' },
  { id: 'tal_accepted', label: '🎯 אושר על ידי טל', color: 'bg-orange-600', textColor: 'text-orange-100' },
  { id: 'sent_to_elad', label: '🏢 אצל אלעד', color: 'bg-amber-600', textColor: 'text-amber-100' },
  { id: 'hired', label: '🎉 התקבל לעבודה', color: 'bg-green-600', textColor: 'text-green-100' },
];

const REJECTION_STAGES = [
  { id: 'rejected_tal', label: '❌ דחוי על ידי טל', color: 'bg-red-600', textColor: 'text-red-100' },
  { id: 'rejected_elad', label: '❌ דחוי על ידי אלעד', color: 'bg-red-700', textColor: 'text-red-100' },
];

export function MatchFlowDashboard() {
  const [expandedStage, setExpandedStage] = useState<string | null>(null);
  const [showRejections, setShowRejections] = useState(false);

  // Fetch metrics
  const { data: metrics, isLoading: metricsLoading } = useQuery<MatchFlowMetrics>({
    queryKey: ['match-flow-metrics'],
    queryFn: async () => {
      const response = await fetch(`${import.meta.env.VITE_API_URL}/admin/matches/flow-metrics`);
      if (!response.ok) throw new Error('Failed to fetch metrics');
      return response.json();
    },
    refetchInterval: 30000, // Refresh every 30s
  });

  // Fetch matches for expanded stage
  const { data: stageMatches, isLoading: matchesLoading } = useQuery<Match[]>({
    queryKey: ['stage-matches', expandedStage],
    queryFn: async () => {
      if (!expandedStage) return [];
      const response = await fetch(
        `${import.meta.env.VITE_API_URL}/admin/matches/by-stage/${expandedStage}`
      );
      if (!response.ok) throw new Error('Failed to fetch matches');
      return response.json();
    },
    enabled: !!expandedStage,
  });

  if (metricsLoading) {
    return <div className="p-8 text-center text-gray-400">⏳ טוען...</div>;
  }

  if (!metrics) {
    return <div className="p-8 text-center text-red-400">❌ שגיאה בטעינת נתונים</div>;
  }

  // Calculate flow percentages
  const getPercentage = (stage: number) => {
    if (metrics.total_in_pipeline === 0) return 0;
    return Math.round((stage / metrics.total_in_pipeline) * 100);
  };

  // Detect bottlenecks
  const detectBottleneck = (): { stage: string; reason: string } | null => {
    if (metrics.stage_sent_to_tal > metrics.stage_tal_accepted * 2) {
      return { stage: 'טל', reason: 'הרבה matches ממתינים לסקירה (2:1 ratio)' };
    }
    if (metrics.stage_tal_accepted > metrics.stage_sent_to_elad * 2) {
      return { stage: 'אלעד', reason: 'הרבה candidates מחכים להצבה' };
    }
    return null;
  };

  const bottleneck = detectBottleneck();

  return (
    <div className="min-h-screen bg-gray-900 p-8" dir="rtl">
      <div className="max-w-7xl mx-auto">
        {/* Header */}
        <div className="mb-8">
          <h1 className="text-4xl font-bold text-white mb-2">📊 Flow דרך Pipeline</h1>
          <p className="text-gray-400">
            ביקורת real-time של כל matches דרך שלבי הגיוס
          </p>
        </div>

        {/* KPI Cards */}
        <div className="grid grid-cols-4 gap-4 mb-8">
          <div className="bg-gradient-to-br from-blue-900 to-blue-800 rounded-lg p-6 border border-blue-700">
            <div className="text-blue-200 text-sm font-semibold">סה"כ ב-Pipeline</div>
            <div className="text-4xl font-bold text-white mt-2">{metrics.total_in_pipeline}</div>
            <div className="text-xs text-blue-300 mt-2">
              {metrics.total_completed} {metrics.total_completed === 1 ? 'הצליח' : 'הצליחו'}
            </div>
          </div>

          <div className="bg-gradient-to-br from-green-900 to-green-800 rounded-lg p-6 border border-green-700">
            <div className="text-green-200 text-sm font-semibold">Success Rate</div>
            <div className="text-4xl font-bold text-white mt-2">
              {(metrics.success_rate * 100).toFixed(1)}%
            </div>
            <div className="text-xs text-green-300 mt-2">מ-total completed</div>
          </div>

          <div className="bg-gradient-to-br from-purple-900 to-purple-800 rounded-lg p-6 border border-purple-700">
            <div className="text-purple-200 text-sm font-semibold">ממוצע בטל</div>
            <div className="text-4xl font-bold text-white mt-2">
              {metrics.avg_time_in_tal.toFixed(1)}d
            </div>
            <div className="text-xs text-purple-300 mt-2">ימים בסקירה</div>
          </div>

          <div className="bg-gradient-to-br from-orange-900 to-orange-800 rounded-lg p-6 border border-orange-700">
            <div className="text-orange-200 text-sm font-semibold">ממוצע באלעד</div>
            <div className="text-4xl font-bold text-white mt-2">
              {metrics.avg_time_in_elad.toFixed(1)}d
            </div>
            <div className="text-xs text-orange-300 mt-2">ימים בהצבה</div>
          </div>
        </div>

        {/* Bottleneck Alert */}
        {bottleneck && (
          <div className="bg-yellow-900/30 border border-yellow-700 rounded-lg p-4 mb-8 flex gap-4 items-start">
            <div className="text-3xl">⚠️</div>
            <div className="flex-1">
              <h3 className="font-bold text-yellow-300">Bottleneck בשלב {bottleneck.stage}</h3>
              <p className="text-yellow-200 text-sm mt-1">{bottleneck.reason}</p>
              <p className="text-yellow-300 text-xs mt-2">💡 כדאי להתערב או להעיף resources</p>
            </div>
          </div>
        )}

        {/* Funnel Visualization */}
        <div className="bg-gray-800 rounded-lg border border-gray-700 p-8 mb-8">
          <h2 className="text-xl font-bold text-white mb-6">🔄 Pipeline Flow</h2>

          <div className="space-y-4">
            {STAGE_CONFIG.map((stage, idx) => {
              const stageValue = metrics[`stage_${stage.id}` as keyof MatchFlowMetrics] as number;
              const percentage = getPercentage(stageValue);
              const isExpanded = expandedStage === stage.id;

              return (
                <div key={stage.id}>
                  {/* Funnel Bar */}
                  <button
                    onClick={() => setExpandedStage(isExpanded ? null : stage.id)}
                    className="w-full text-left transition-opacity hover:opacity-80"
                  >
                    <div className="flex items-center gap-4 mb-2">
                      <div className="flex-1 flex items-center gap-3">
                        <span className="text-white font-semibold w-40">{stage.label}</span>
                        <div className="relative flex-1 h-10 bg-gray-700 rounded overflow-hidden">
                          <div
                            className={`${stage.color} h-full flex items-center justify-center transition-all`}
                            style={{ width: `${Math.max(percentage, 5)}%` }}
                          >
                            <span className={`${stage.textColor} font-bold text-sm`}>
                              {stageValue > 0 && `${stageValue}`}
                            </span>
                          </div>
                        </div>
                      </div>
                      <div className="text-right">
                        <div className="text-white font-bold w-12 text-center">{percentage}%</div>
                        <div className="text-gray-400 text-xs">{stageValue}</div>
                      </div>
                    </div>
                  </button>

                  {/* Expanded Details */}
                  {isExpanded && (
                    <div className="bg-gray-700/50 rounded p-4 mt-2 border border-gray-600">
                      {matchesLoading ? (
                        <div className="text-center text-gray-400">⏳ טוען...</div>
                      ) : stageMatches && stageMatches.length > 0 ? (
                        <div className="space-y-2 max-h-96 overflow-y-auto">
                          {stageMatches.map((match) => (
                            <div
                              key={match.id}
                              className="bg-gray-800 p-3 rounded border border-gray-600 hover:border-gray-500 transition-colors"
                            >
                              <div className="flex justify-between items-start">
                                <div className="flex-1">
                                  <div className="font-semibold text-white">
                                    {match.candidate_name} → {match.job_title}
                                  </div>
                                  <div className="flex gap-2 mt-1">
                                    <span className="text-xs bg-indigo-900/40 text-indigo-300 px-2 py-1 rounded">
                                      Score: {(match.match_score * 100).toFixed(0)}%
                                    </span>
                                    <span className="text-xs bg-gray-600 text-gray-200 px-2 py-1 rounded">
                                      {new Date(match.created_at).toLocaleDateString('he-IL')}
                                    </span>
                                  </div>
                                  {match.tal_summary && (
                                    <div className="text-xs text-gray-300 mt-2 italic">
                                      טל: {match.tal_summary}
                                    </div>
                                  )}
                                </div>
                                <div className="text-right">
                                  <span className="text-xs text-gray-400">
                                    {Math.floor(
                                      (new Date().getTime() - new Date(match.updated_at).getTime()) /
                                        (1000 * 60 * 60 * 24)
                                    )}d
                                  </span>
                                </div>
                              </div>
                            </div>
                          ))}
                        </div>
                      ) : (
                        <div className="text-center text-gray-400 py-4">אין matches בשלב זה</div>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>

        {/* Rejections Section */}
        <div className="bg-gray-800 rounded-lg border border-gray-700 p-8">
          <button
            onClick={() => setShowRejections(!showRejections)}
            className="text-xl font-bold text-white mb-6 hover:text-red-400 transition-colors flex items-center gap-2"
          >
            {showRejections ? '▼' : '▶'} ❌ דחויים ({metrics.stage_rejected_tal + metrics.stage_rejected_elad})
          </button>

          {showRejections && (
            <div className="grid grid-cols-2 gap-4">
              {REJECTION_STAGES.map((stage) => {
                const stageValue = metrics[`stage_${stage.id}` as keyof MatchFlowMetrics] as number;

                return (
                  <button
                    key={stage.id}
                    onClick={() => setExpandedStage(expandedStage === stage.id ? null : stage.id)}
                    className="bg-red-900/20 border border-red-700 rounded-lg p-4 hover:bg-red-900/30 transition-colors text-left"
                  >
                    <div className="text-red-300 font-semibold">{stage.label}</div>
                    <div className="text-3xl font-bold text-red-400 mt-2">{stageValue}</div>
                  </button>
                );
              })}
            </div>
          )}

          {showRejections && expandedStage && expandedStage.startsWith('rejected') && (
            <div className="mt-6 bg-gray-700/50 rounded p-4 border border-gray-600">
              {matchesLoading ? (
                <div className="text-center text-gray-400">⏳ טוען...</div>
              ) : stageMatches && stageMatches.length > 0 ? (
                <div className="space-y-2 max-h-96 overflow-y-auto">
                  {stageMatches.map((match) => (
                    <div
                      key={match.id}
                      className="bg-gray-800 p-3 rounded border border-red-700/50"
                    >
                      <div className="font-semibold text-white">
                        {match.candidate_name} → {match.job_title}
                      </div>
                      {match.carmit_review_notes && (
                        <div className="text-xs text-red-300 mt-2">
                          סיבה: {match.carmit_review_notes}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              ) : (
                <div className="text-center text-gray-400 py-4">אין דחויים בקטגוריה זו</div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

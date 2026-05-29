/**
 * Candidate Recommendations Modal
 * Shows job and contact recommendations for a candidate
 * Match score ≥80% only, max 5 of each
 */

import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';

interface JobMatch {
  job_id: string;
  job_title: string;
  match_score: number;
  match_details: Record<string, any>;
  priority?: number;
}

interface ContactMatch {
  contact_id: string;
  contact_name: string;
  contact_status: string;
  professional_domain?: string;
  match_score: number;
  match_details: Record<string, any>;
}

interface CandidateRecommendations {
  candidate_id: string;
  candidate_name: string;
  candidate_domain?: string;
  candidate_clearance?: string;
  job_matches: JobMatch[];
  contact_recommendations: ContactMatch[];
  generated_at: string;
}

interface Props {
  candidateId: string;
  candidateName: string;
  onClose: () => void;
}

export function CandidateRecommendationsModal({ candidateId, candidateName, onClose }: Props) {
  const [expandedTab, setExpandedTab] = useState<'jobs' | 'contacts'>('jobs');

  const { data, isLoading, error } = useQuery<CandidateRecommendations>({
    queryKey: ['candidate-recommendations', candidateId],
    queryFn: async () => {
      const response = await fetch(
        `${import.meta.env.VITE_API_URL}/admin/candidates/${candidateId}/recommendations`
      );
      if (!response.ok) {
        throw new Error('Failed to fetch recommendations');
      }
      return response.json();
    },
  });

  const getMatchColor = (score: number) => {
    if (score >= 0.95) return 'bg-green-900 text-green-200';
    if (score >= 0.90) return 'bg-emerald-900 text-emerald-200';
    if (score >= 0.85) return 'bg-cyan-900 text-cyan-200';
    return 'bg-blue-900 text-blue-200';
  };

  const getMatchEmoji = (score: number) => {
    if (score >= 0.95) return '🎯';
    if (score >= 0.90) return '⭐';
    if (score >= 0.85) return '✨';
    return '👍';
  };

  const getDetailBadge = (detail: any, key: string) => {
    const value = detail[key];
    if (!value) return null;

    let bgColor = 'bg-gray-700';
    if (key.includes('match') && value === 'exact') bgColor = 'bg-green-800';
    else if (key.includes('match') && value === 'strong') bgColor = 'bg-emerald-800';
    else if (key.includes('match') && value === 'synonym') bgColor = 'bg-cyan-800';
    else if (key.includes('compatibility') && value === true) bgColor = 'bg-green-800';
    else if (key.includes('compatibility') && value === false) bgColor = 'bg-red-800';

    return (
      <span key={key} className={`${bgColor} px-2 py-1 rounded text-xs font-semibold text-white`}>
        {typeof value === 'string' ? value : JSON.stringify(value)}
      </span>
    );
  };

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <div className="bg-gray-900 rounded-lg border border-gray-700 max-w-4xl w-full max-h-96 overflow-y-auto shadow-2xl">
        {/* Header */}
        <div className="sticky top-0 bg-gray-800 border-b border-gray-700 p-4 flex justify-between items-center">
          <div>
            <h2 className="text-2xl font-bold text-white flex items-center gap-2">
              🎯 המלצות עבור {candidateName}
            </h2>
            {data && (
              <p className="text-sm text-gray-400 mt-1">
                {data.candidate_domain && `תחום: ${data.candidate_domain}`}
                {data.candidate_clearance && ` | סיווג: ${data.candidate_clearance}`}
              </p>
            )}
          </div>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-white text-2xl leading-none"
          >
            ✕
          </button>
        </div>

        {/* Loading State */}
        {isLoading && (
          <div className="p-8 text-center text-gray-300">
            <div className="inline-block animate-spin">⏳</div> טוען המלצות...
          </div>
        )}

        {/* Error State */}
        {error && (
          <div className="p-8 bg-red-900/20 border-t border-red-700 text-red-300">
            ❌ שגיאה בטעינת המלצות: {(error as Error).message}
          </div>
        )}

        {/* Content */}
        {data && (
          <div className="p-4">
            {/* Tabs */}
            <div className="flex gap-2 mb-6 border-b border-gray-700">
              <button
                onClick={() => setExpandedTab('jobs')}
                className={`px-4 py-2 font-semibold transition-colors ${
                  expandedTab === 'jobs'
                    ? 'text-indigo-400 border-b-2 border-indigo-400'
                    : 'text-gray-400 hover:text-gray-300'
                }`}
              >
                💼 משרות ({data.job_matches.length})
              </button>
              <button
                onClick={() => setExpandedTab('contacts')}
                className={`px-4 py-2 font-semibold transition-colors ${
                  expandedTab === 'contacts'
                    ? 'text-indigo-400 border-b-2 border-indigo-400'
                    : 'text-gray-400 hover:text-gray-300'
                }`}
              >
                👥 לקוחות ({data.contact_recommendations.length})
              </button>
            </div>

            {/* Jobs Tab */}
            {expandedTab === 'jobs' && (
              <div className="space-y-3">
                {data.job_matches.length === 0 ? (
                  <p className="text-gray-400 text-center py-4">
                    ❌ לא נמצאו משרות תואמות (≥80%)
                  </p>
                ) : (
                  data.job_matches.map((job) => (
                    <div
                      key={job.job_id}
                      className="bg-gray-800 border border-gray-700 rounded-lg p-4 hover:border-indigo-500/50 transition-colors"
                    >
                      <div className="flex justify-between items-start mb-2">
                        <div className="flex-1">
                          <h3 className="font-semibold text-white text-lg">{job.job_title}</h3>
                        </div>
                        <div className={`${getMatchColor(job.match_score)} px-3 py-1 rounded-lg font-bold text-center`}>
                          <span className="text-lg">{getMatchEmoji(job.match_score)}</span>
                          <div className="text-sm">{(job.match_score * 100).toFixed(0)}%</div>
                        </div>
                      </div>

                      {/* Match Details */}
                      <div className="flex flex-wrap gap-2">
                        {Object.keys(job.match_details)
                          .filter((key) => job.match_details[key])
                          .map((key) => getDetailBadge(job.match_details, key))}
                      </div>

                      {job.priority && (
                        <p className="text-xs text-gray-400 mt-2">
                          עדיפות: {job.priority}
                        </p>
                      )}
                    </div>
                  ))
                )}
              </div>
            )}

            {/* Contacts Tab */}
            {expandedTab === 'contacts' && (
              <div className="space-y-3">
                {data.contact_recommendations.length === 0 ? (
                  <p className="text-gray-400 text-center py-4">
                    ❌ לא נמצאו לקוחות תואמים (≥80%)
                  </p>
                ) : (
                  data.contact_recommendations.map((contact) => (
                    <div
                      key={contact.contact_id}
                      className="bg-gray-800 border border-gray-700 rounded-lg p-4 hover:border-indigo-500/50 transition-colors"
                    >
                      <div className="flex justify-between items-start mb-2">
                        <div className="flex-1">
                          <h3 className="font-semibold text-white text-lg">{contact.contact_name}</h3>
                          <div className="flex gap-2 mt-1">
                            <span className="inline-block px-2 py-1 bg-purple-900/40 text-purple-300 rounded text-xs font-semibold">
                              {contact.contact_status === 'client' ? '🏢 לקוח' : '💡 לקוח פוטנציאלי'}
                            </span>
                            {contact.professional_domain && (
                              <span className="inline-block px-2 py-1 bg-gray-700 text-gray-200 rounded text-xs">
                                {contact.professional_domain}
                              </span>
                            )}
                          </div>
                        </div>
                        <div className={`${getMatchColor(contact.match_score)} px-3 py-1 rounded-lg font-bold text-center`}>
                          <span className="text-lg">{getMatchEmoji(contact.match_score)}</span>
                          <div className="text-sm">{(contact.match_score * 100).toFixed(0)}%</div>
                        </div>
                      </div>

                      {/* Match Details */}
                      <div className="flex flex-wrap gap-2">
                        {Object.keys(contact.match_details)
                          .filter((key) => contact.match_details[key] !== undefined)
                          .map((key) => getDetailBadge(contact.match_details, key))}
                      </div>
                    </div>
                  ))
                )}
              </div>
            )}

            {/* Footer */}
            <div className="mt-4 pt-4 border-t border-gray-700 text-xs text-gray-400 text-center">
              ✅ הניתוח בוצע בהצלחה • {new Date(data.generated_at).toLocaleString('he-IL')}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

/**
 * Match Timeline Chart
 * Shows progression of matches through pipeline stages over time
 *
 * Visualization: Line chart showing count of matches in each stage per day/week
 * Helps identify:
 * - Flow velocity (how fast matches move through stages)
 * - Bottleneck formation (stage where flow slows)
 * - Success trend (hired matches increasing over time)
 */

import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';

interface TimelineDataPoint {
  date: string;
  stage: string;
  count: number;
}

interface TimelineChartProps {
  timeRange?: 'week' | 'month' | 'quarter';
}

export function MatchTimelineChart({ timeRange = 'month' }: TimelineChartProps) {
  const [selectedMetric, setSelectedMetric] = useState<'count' | 'progression'>('count');

  // Fetch timeline data
  const { data: timelineData, isLoading } = useQuery<TimelineDataPoint[]>({
    queryKey: ['match-timeline', timeRange],
    queryFn: async () => {
      const response = await fetch(
        `${import.meta.env.VITE_API_URL}/admin/matches/timeline?range=${timeRange}`
      );
      if (!response.ok) throw new Error('Failed to fetch timeline');
      return response.json();
    },
    refetchInterval: 60000, // Refresh every minute
  });

  if (isLoading) {
    return <div className="p-4 text-gray-400">⏳ טוען נתוני זמן אמת...</div>;
  }

  if (!timelineData || timelineData.length === 0) {
    return <div className="p-4 text-gray-400">אין נתונים לתקופה זו</div>;
  }

  // Group data by date
  const dateGroups = new Map<string, Map<string, number>>();
  timelineData.forEach((point) => {
    if (!dateGroups.has(point.date)) {
      dateGroups.set(point.date, new Map());
    }
    dateGroups.get(point.date)!.set(point.stage, point.count);
  });

  // Prepare chart data
  const chartData = Array.from(dateGroups.entries()).map(([date, stages]) => ({
    date: new Date(date).toLocaleDateString('he-IL'),
    found: stages.get('found') || 0,
    carmit_approved: stages.get('carmit_approved') || 0,
    sent_to_tal: stages.get('sent_to_tal') || 0,
    tal_conversation: stages.get('tal_conversation') || 0,
    tal_accepted: stages.get('tal_accepted') || 0,
    sent_to_elad: stages.get('sent_to_elad') || 0,
    hired: stages.get('hired') || 0,
    rejected: (stages.get('rejected_tal') || 0) + (stages.get('rejected_elad') || 0),
  }));

  // Render simple ASCII chart (no external charting library needed)
  const renderAsciiChart = () => {
    if (chartData.length === 0) return null;

    // Find max value for scaling
    let maxValue = 0;
    chartData.forEach((point) => {
      const total = Object.values(point).reduce((sum, val) => (typeof val === 'number' ? sum + val : sum), 0);
      if (total > maxValue) maxValue = total;
    });

    const chartHeight = 15;
    const scale = maxValue / chartHeight;

    return (
      <div className="font-mono text-xs text-gray-300 overflow-x-auto">
        {/* Y-axis labels */}
        <div className="flex">
          <div className="w-12 text-right pr-2">
            {Array.from({ length: chartHeight + 1 }, (_, i) => {
              const value = Math.round((chartHeight - i) * scale);
              return (
                <div key={i} className="h-8 flex items-center justify-end">
                  {value}
                </div>
              );
            })}
          </div>

          {/* Chart bars */}
          <div className="flex gap-1 flex-1">
            {chartData.map((point, idx) => (
              <div key={idx} className="flex flex-col gap-0 relative">
                {/* Bar */}
                <div className="flex flex-col items-center">
                  {Array.from({ length: chartHeight }, (_, i) => {
                    const value = Math.round((chartHeight - 1 - i) * scale);
                    const pointTotal = (point.hired || 0) + (point.sent_to_elad || 0) + (point.tal_accepted || 0) + (point.sent_to_tal || 0) + (point.carmit_approved || 0) + (point.found || 0);
                    const filled = pointTotal >= value;
                    return (
                      <div
                        key={i}
                        className={`w-6 h-2 ${
                          filled ? 'bg-gradient-to-t from-green-500 to-blue-500' : 'bg-gray-700'
                        } border border-gray-600`}
                      />
                    );
                  })}
                </div>

                {/* X-axis label */}
                <div className="text-center text-xs text-gray-400 mt-1 w-6 truncate">
                  {point.date.split('/')[0]}
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    );
  };

  // Render stage progression table
  const renderProgressionTable = () => {
    return (
      <div className="overflow-x-auto">
        <table className="w-full text-xs text-gray-300">
          <thead>
            <tr className="border-b border-gray-600">
              <th className="text-left py-2 px-2 text-gray-400">תאריך</th>
              <th className="text-center py-2 px-2">🔍 Found</th>
              <th className="text-center py-2 px-2">✅ Carmit</th>
              <th className="text-center py-2 px-2">👤 Tal</th>
              <th className="text-center py-2 px-2">💬 Conv</th>
              <th className="text-center py-2 px-2">🎯 Approved</th>
              <th className="text-center py-2 px-2">🏢 Elad</th>
              <th className="text-center py-2 px-2">🎉 Hired</th>
              <th className="text-center py-2 px-2">❌ Rejected</th>
            </tr>
          </thead>
          <tbody>
            {chartData.map((point, idx) => (
              <tr key={idx} className="border-b border-gray-700 hover:bg-gray-700/50">
                <td className="py-2 px-2 text-gray-400">{point.date}</td>
                <td className="text-center">{point.found}</td>
                <td className="text-center">{point.carmit_approved}</td>
                <td className="text-center">{point.sent_to_tal}</td>
                <td className="text-center">{point.tal_conversation}</td>
                <td className="text-center text-green-400 font-semibold">{point.tal_accepted}</td>
                <td className="text-center text-yellow-400">{point.sent_to_elad}</td>
                <td className="text-center text-green-500 font-bold">{point.hired}</td>
                <td className="text-center text-red-400">{point.rejected}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  };

  return (
    <div className="bg-gray-800 rounded-lg border border-gray-700 p-6 mb-8">
      <div className="flex justify-between items-center mb-6">
        <h2 className="text-xl font-bold text-white">📈 Timeline: Match Progression</h2>
        <div className="flex gap-2">
          <button
            onClick={() => setSelectedMetric('count')}
            className={`px-3 py-1 rounded text-sm font-semibold ${
              selectedMetric === 'count'
                ? 'bg-indigo-600 text-white'
                : 'bg-gray-700 text-gray-300 hover:bg-gray-600'
            }`}
          >
            📊 Chart
          </button>
          <button
            onClick={() => setSelectedMetric('progression')}
            className={`px-3 py-1 rounded text-sm font-semibold ${
              selectedMetric === 'progression'
                ? 'bg-indigo-600 text-white'
                : 'bg-gray-700 text-gray-300 hover:bg-gray-600'
            }`}
          >
            📋 Table
          </button>
        </div>
      </div>

      {selectedMetric === 'count' ? renderAsciiChart() : renderProgressionTable()}

      {/* Insights */}
      <div className="mt-6 grid grid-cols-3 gap-4">
        <div className="bg-green-900/20 border border-green-700 rounded p-3">
          <div className="text-green-400 text-sm font-semibold">Latest Success</div>
          <div className="text-green-300 text-2xl font-bold mt-1">
            {chartData[chartData.length - 1]?.hired || 0}
          </div>
          <div className="text-xs text-green-400 mt-1">hired this period</div>
        </div>

        <div className="bg-blue-900/20 border border-blue-700 rounded p-3">
          <div className="text-blue-400 text-sm font-semibold">In Pipeline</div>
          <div className="text-blue-300 text-2xl font-bold mt-1">
            {(chartData[chartData.length - 1]?.found || 0) +
              (chartData[chartData.length - 1]?.carmit_approved || 0) +
              (chartData[chartData.length - 1]?.sent_to_tal || 0)}
          </div>
          <div className="text-xs text-blue-400 mt-1">active matches</div>
        </div>

        <div className="bg-orange-900/20 border border-orange-700 rounded p-3">
          <div className="text-orange-400 text-sm font-semibold">Conversion</div>
          <div className="text-orange-300 text-2xl font-bold mt-1">
            {chartData.length > 0
              ? (
                  (chartData[chartData.length - 1]?.hired || 0) /
                  (chartData[chartData.length - 1]?.found || 1) *
                  100
                ).toFixed(0)
              : 0}
            %
          </div>
          <div className="text-xs text-orange-400 mt-1">found to hired</div>
        </div>
      </div>

      {/* Legend */}
      <div className="mt-6 pt-4 border-t border-gray-700 text-xs text-gray-400">
        <div className="grid grid-cols-2 gap-2">
          <div>🔍 Found: New matches from matching engine</div>
          <div>✅ Carmit: Approved for Tal screening</div>
          <div>👤 Tal: With talent screener</div>
          <div>💬 Conv: In conversation with candidate</div>
          <div>🎯 Approved: Ready for client placement</div>
          <div>🏢 Elad: With placement specialist</div>
          <div>🎉 Hired: Successfully placed</div>
          <div>❌ Rejected: Not a fit</div>
        </div>
      </div>
    </div>
  );
}

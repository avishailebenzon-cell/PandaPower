/**
 * StatusBar Component
 * Seamless, gap-free scrolling RTL status ticker for system components.
 */

import React from 'react';
import { useSystemStatus } from '@/hooks/useSystemStatus';

interface StatusItem {
  id: string;
  name: string;
  status: 'active' | 'idle' | 'processing' | 'offline';
  detail?: string;
}

const getStatusColor = (status: string): string => {
  switch (status) {
    case 'active':
      return 'bg-green-600';
    case 'processing':
      return 'bg-blue-600';
    case 'idle':
      return 'bg-yellow-600';
    case 'offline':
      return 'bg-red-600';
    default:
      return 'bg-gray-600';
  }
};

const getStatusText = (status: string): string => {
  switch (status) {
    case 'active':
      return '🟢 פעיל';
    case 'processing':
      return '🔵 בעיבוד';
    case 'idle':
      return '🟡 בהמתנה';
    case 'offline':
      return '🔴 לא פעיל';
    default:
      return '⚪ לא ידוע';
  }
};

const StatusEntry: React.FC<{ item: StatusItem }> = ({ item }) => (
  <div className="flex items-center gap-3 flex-shrink-0 px-4">
    <div
      className={`w-3 h-3 rounded-full ${getStatusColor(item.status)} animate-pulse`}
      title={item.name}
    />
    <div className="flex flex-col gap-0.5">
      <span className="text-sm font-semibold text-white">{item.name}</span>
      <span className="text-xs text-gray-400 flex items-center gap-1">
        {getStatusText(item.status)}
        {item.detail && (
          <>
            <span>•</span>
            <span>{item.detail}</span>
          </>
        )}
      </span>
    </div>
    <div className="w-px h-8 bg-gray-700 ml-2" />
  </div>
);

export const StatusBar: React.FC = () => {
  const { statuses: statusItems } = useSystemStatus();

  if (statusItems.length === 0) return null;

  // Repeat the items enough times that a single track is guaranteed to be
  // wider than the viewport — this is what keeps the ticker free of any
  // "dead space" when there are only a handful of items. Two identical
  // tracks then animate together by exactly one track-width (-100%), so the
  // second track seamlessly takes over the moment the first scrolls off.
  const REPEATS = 4;
  const track = Array.from({ length: REPEATS }).flatMap(() => statusItems);

  return (
    <div className="fixed bottom-0 left-0 right-0 bg-gray-950 border-t-2 border-gray-800 py-2 px-4 z-40">
      <div className="relative overflow-hidden h-12 flex">
        {/* Two adjacent identical tracks animating in lockstep → no gap */}
        {[0, 1].map((trackIdx) => (
          <div
            key={trackIdx}
            className="flex items-center flex-shrink-0 animate-marquee"
            aria-hidden={trackIdx === 1}
          >
            {track.map((item, index) => (
              <StatusEntry key={`${trackIdx}-${item.id}-${index}`} item={item} />
            ))}
          </div>
        ))}
      </div>

      <style>{`
        @keyframes marquee {
          from { transform: translateX(0); }
          to { transform: translateX(-100%); }
        }

        .animate-marquee {
          animation: marquee 40s linear infinite;
          will-change: transform;
        }

        .animate-marquee:hover {
          animation-play-state: paused;
        }
      `}</style>
    </div>
  );
};

export default StatusBar;

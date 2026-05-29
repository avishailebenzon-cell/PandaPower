/**
 * Conversations Page
 * Display all conversations with recruiters (Tal/Elad)
 */

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchRecruiterConversations } from "@/api/recruiter";

type RecruiterTab = "tal" | "elad";

interface ConversationListItem {
  id: string;
  matchId: string;
  candidateName: string;
  jobTitle: string;
  startedAt: string;
  endedAt?: string;
  status: string;
  notes?: string;
}

export function ConversationsPage() {
  const [recruiter, setRecruiter] = useState<RecruiterTab>("tal");
  const [page, setPage] = useState(1);
  const limit = 20;

  const conversationsQuery = useQuery({
    queryKey: ["recruiter-conversations", recruiter, page],
    queryFn: () => fetchRecruiterConversations(recruiter, limit, page),
    refetchInterval: 30000,
  });

  const conversations = conversationsQuery.data?.conversations ?? [];
  const total = conversationsQuery.data?.total ?? 0;
  const totalPages = Math.ceil(total / limit);

  const recruiterName = recruiter === "tal" ? "טל" : "אלעד";
  const recruiterEmoji = recruiter === "tal" ? "👩‍💼" : "🤝";

  return (
    <div dir="rtl" className="p-6 space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-3xl font-bold text-white flex items-center gap-2">
          <span>{recruiterEmoji}</span> שיחות עם {recruiterName}
        </h1>
        <p className="text-gray-400 mt-1">
          {recruiter === "tal"
            ? "כל השיחות של טל עם מועמדים בשלב הסינון הראשוני"
            : "כל השיחות של אלעד עם לקוחות לגבי הצעות עבודה"}
        </p>
      </div>

      {/* Recruiter Tabs */}
      <div className="inline-flex bg-gray-800 rounded-lg p-1 gap-1">
        <button
          onClick={() => {
            setRecruiter("tal");
            setPage(1);
          }}
          className={`px-4 py-1.5 rounded text-sm font-semibold transition ${
            recruiter === "tal"
              ? "bg-indigo-600 text-white"
              : "text-gray-300 hover:text-white"
          }`}
        >
          👩‍💼 טל
        </button>
        <button
          onClick={() => {
            setRecruiter("elad");
            setPage(1);
          }}
          className={`px-4 py-1.5 rounded text-sm font-semibold transition ${
            recruiter === "elad"
              ? "bg-indigo-600 text-white"
              : "text-gray-300 hover:text-white"
          }`}
        >
          🤝 אלעד
        </button>
      </div>

      {/* Content */}
      {conversationsQuery.isLoading ? (
        <div className="text-gray-400 text-center py-8">טוען שיחות...</div>
      ) : conversationsQuery.error ? (
        <div className="text-red-400 text-center py-8">
          שגיאה בטעינת השיחות
        </div>
      ) : conversations.length === 0 ? (
        <div className="bg-gray-800 border border-gray-700 rounded-lg p-8 text-center text-gray-300">
          <p className="text-lg mb-2">📭 אין שיחות</p>
          <p className="text-sm text-gray-400">
            לא קיימות שיחות עדיין עם {recruiterName}
          </p>
        </div>
      ) : (
        <>
          {/* Conversations Grid */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {conversations.map((conv: ConversationListItem) => (
              <ConversationCard key={conv.id} conversation={conv} />
            ))}
          </div>

          {/* Pagination */}
          {totalPages > 1 && (
            <div className="flex justify-center gap-2 mt-6">
              <button
                onClick={() => setPage(Math.max(1, page - 1))}
                disabled={page === 1}
                className="px-4 py-2 rounded bg-gray-700 hover:bg-gray-600 disabled:opacity-50 text-gray-200 text-sm"
              >
                ← הקודם
              </button>
              <span className="px-4 py-2 text-gray-300 text-sm">
                עמוד {page} מתוך {totalPages}
              </span>
              <button
                onClick={() => setPage(Math.min(totalPages, page + 1))}
                disabled={page === totalPages}
                className="px-4 py-2 rounded bg-gray-700 hover:bg-gray-600 disabled:opacity-50 text-gray-200 text-sm"
              >
                הבא →
              </button>
            </div>
          )}
        </>
      )}
    </div>
  );
}

function ConversationCard({
  conversation,
}: {
  conversation: ConversationListItem;
}) {
  const isActive = conversation.status === "active";
  const startDate = new Date(conversation.startedAt);
  const daysAgo = Math.floor(
    (Date.now() - startDate.getTime()) / (1000 * 60 * 60 * 24)
  );

  return (
    <div className="bg-gray-800 border border-gray-700 rounded-lg p-4 hover:border-gray-600 transition">
      {/* Header */}
      <div className="flex justify-between items-start mb-3">
        <div className="flex-1">
          <h3 className="text-white font-semibold text-sm">{conversation.candidateName}</h3>
          <p className="text-gray-400 text-xs">{conversation.jobTitle}</p>
        </div>
        <span
          className={`px-2 py-0.5 rounded text-xs font-semibold ${
            isActive
              ? "bg-green-900 text-green-200"
              : "bg-gray-700 text-gray-300"
          }`}
        >
          {isActive ? "פעילה" : "סגורה"}
        </span>
      </div>

      {/* Details */}
      <div className="space-y-1.5 mb-3">
        <p className="text-xs text-gray-400">
          <span className="opacity-70">התחילה:</span>{" "}
          {startDate.toLocaleDateString("he-IL")}
          {daysAgo === 0 && " (היום)"}
          {daysAgo === 1 && " (אתמול)"}
          {daysAgo > 1 && ` (${daysAgo} ימים)`}
        </p>
        {conversation.notes && (
          <p className="text-xs text-gray-300">
            <span className="opacity-70">הערות:</span> {conversation.notes.substring(0, 100)}
            {conversation.notes.length > 100 ? "..." : ""}
          </p>
        )}
      </div>

      {/* Footer */}
      <div className="flex gap-2">
        <a
          href={`/recruiting/tal`}
          className="flex-1 px-3 py-1.5 rounded bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-semibold text-center transition"
        >
          עבור לדף
        </a>
      </div>
    </div>
  );
}

export default ConversationsPage;

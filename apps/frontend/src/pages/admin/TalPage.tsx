/**
 * Tal Recruiter Page — initial screening (talks with the candidate).
 *
 * Shows the same data as the "העברתי לטל" tab on Carmit's page so both
 * views always stay in sync. All data is real (driven by matches.current_state
 * via /admin/recruiter/matches); no mock content lives here anymore.
 */

import { useNavigate } from "react-router-dom";
import { MessageCircle, FlaskConical } from "lucide-react";
import { RecruiterMatchesPanel } from "@/components/RecruiterMatchesPanel";

export const TalPage = () => {
  const navigate = useNavigate();
  return (
    <div dir="rtl" className="p-6 space-y-6">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-3xl font-bold text-white flex items-center gap-2">
            <span>👩‍💼</span> טל — סוכנת ראשונית
          </h1>
          <p className="text-gray-400 mt-1">
            סינון ראשוני של מועמדים בוואטסאפ. טל מנהלת שיחות וואטסאפ עם מועמדים בחלק הראשון של תהליך הגיוס לאחר הנחיה של מנהל הגיוס כרמית.
          </p>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <button
            onClick={() => navigate("/recruiting/tal/test")}
            className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-amber-600 text-white hover:bg-amber-500 transition"
          >
            <FlaskConical className="w-4 h-4" /> שיחת בדיקה
          </button>
          <button
            onClick={() => navigate("/recruiting/tal/conversations")}
            className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-teal-600 text-white hover:bg-teal-700 transition"
          >
            <MessageCircle className="w-4 h-4" /> שיחות
          </button>
        </div>
      </div>

      <RecruiterMatchesPanel recruiter="tal" />
    </div>
  );
};

export default TalPage;

/**
 * Tal Recruiter Page — initial screening (talks with the candidate).
 *
 * Shows the same data as the "העברתי לטל" tab on Carmit's page so both
 * views always stay in sync. All data is real (driven by matches.current_state
 * via /admin/recruiter/matches); no mock content lives here anymore.
 */

import { RecruiterMatchesPanel } from "@/components/RecruiterMatchesPanel";

export const TalPage = () => {
  return (
    <div dir="rtl" className="p-6 space-y-6">
      <div>
        <h1 className="text-3xl font-bold text-white flex items-center gap-2">
          <span>👩‍💼</span> טל — סוכנת ראשונית
        </h1>
        <p className="text-gray-400 mt-1">
          סינון ראשוני של מועמדים. טל מנהלת שיחות עם מועמדים בחלק הראשון של תהליך הגיוס.
        </p>
      </div>

      <RecruiterMatchesPanel recruiter="tal" />
    </div>
  );
};

export default TalPage;

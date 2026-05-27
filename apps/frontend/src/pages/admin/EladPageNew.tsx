/**
 * Elad Recruiter Page — final placement (talks with the client).
 *
 * Shows the same data as the "העברתי לאלעד" tab on Carmit's page so both
 * views always stay in sync. All data is real (driven by matches.current_state
 * via /admin/recruiter/matches); no mock content lives here anymore.
 */

import { RecruiterMatchesPanel } from "@/components/RecruiterMatchesPanel";

export const EladPageNew = () => {
  return (
    <div dir="rtl" className="p-6 space-y-6">
      <div>
        <h1 className="text-3xl font-bold text-white flex items-center gap-2">
          <span>🤝</span> אלעד — הצבות
        </h1>
        <p className="text-gray-400 mt-1">
          הצבת מועמדים אצל לקוחות. אלעד מנהל שיחות עם הלקוחות בשלב הסיום של תהליך הגיוס.
        </p>
      </div>

      <RecruiterMatchesPanel recruiter="elad" />
    </div>
  );
};

export default EladPageNew;

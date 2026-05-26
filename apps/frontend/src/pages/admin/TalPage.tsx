/**
 * Tal Recruiter Page
 * Initial screening with candidates
 * Uses generic RecruiterConversationPage component
 */

import RecruiterConversationPage from './RecruiterConversationPage';

export const TalPage = () => {
  return (
    <RecruiterConversationPage
      recruiterType="tal"
      recruiterName="טל"
      roleDescription="סינון ראשוני של מועמדים - טל מנהלת שיחות עם מועמדים בחלק הראשון של תהליך הגיוס"
      contactType="candidate"
    />
  );
};

export default TalPage;

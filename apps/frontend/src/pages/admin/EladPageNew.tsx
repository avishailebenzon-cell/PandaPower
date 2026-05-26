/**
 * Elad Recruiter Page
 * Final placement with clients
 * Uses generic RecruiterConversationPage component
 */

import RecruiterConversationPage from './RecruiterConversationPage';

export const EladPageNew = () => {
  return (
    <RecruiterConversationPage
      recruiterType="elad"
      recruiterName="אלעד"
      roleDescription="הצבת מועמדים ללקוחות - אלעד מנהלת שיחות עם לקוחות בשלב הסיום של תהליך הגיוס"
      contactType="client"
    />
  );
};

export default EladPageNew;

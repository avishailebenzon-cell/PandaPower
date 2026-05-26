-- Enable RLS on all business logic tables
ALTER TABLE candidates ENABLE ROW LEVEL SECURITY;
ALTER TABLE cv_files ENABLE ROW LEVEL SECURITY;
ALTER TABLE candidate_skills ENABLE ROW LEVEL SECURITY;
ALTER TABLE organizations ENABLE ROW LEVEL SECURITY;
ALTER TABLE contacts ENABLE ROW LEVEL SECURITY;
ALTER TABLE jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE matches ENABLE ROW LEVEL SECURITY;
ALTER TABLE match_state_history ENABLE ROW LEVEL SECURITY;
ALTER TABLE agent_logs ENABLE ROW LEVEL SECURITY;
ALTER TABLE whatsapp_conversations ENABLE ROW LEVEL SECURITY;
ALTER TABLE whatsapp_messages ENABLE ROW LEVEL SECURITY;
ALTER TABLE telegram_users ENABLE ROW LEVEL SECURITY;
ALTER TABLE telegram_messages ENABLE ROW LEVEL SECURITY;
ALTER TABLE email_intake_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE synonym_dictionary ENABLE ROW LEVEL SECURITY;
ALTER TABLE agent_runtime_state ENABLE ROW LEVEL SECURITY;

-- Business tables: authenticated users with role in (admin, manager, recruiter) can SELECT/INSERT/UPDATE/DELETE
-- viewer role can SELECT only

-- Helper function to check user role
CREATE OR REPLACE FUNCTION has_recruiter_role()
RETURNS boolean AS $$
BEGIN
  RETURN EXISTS (
    SELECT 1 FROM users
    WHERE id = auth.uid()
    AND role IN ('admin', 'manager', 'recruiter')
    AND is_active = TRUE
  );
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

CREATE OR REPLACE FUNCTION has_viewer_role()
RETURNS boolean AS $$
BEGIN
  RETURN EXISTS (
    SELECT 1 FROM users
    WHERE id = auth.uid()
    AND role = 'viewer'
    AND is_active = TRUE
  );
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Candidates
CREATE POLICY candidates_select_authenticated
ON candidates FOR SELECT
TO authenticated
USING (has_recruiter_role() OR has_viewer_role());

CREATE POLICY candidates_insert_authenticated
ON candidates FOR INSERT
TO authenticated
WITH CHECK (has_recruiter_role());

CREATE POLICY candidates_update_authenticated
ON candidates FOR UPDATE
TO authenticated
USING (has_recruiter_role())
WITH CHECK (has_recruiter_role());

CREATE POLICY candidates_delete_authenticated
ON candidates FOR DELETE
TO authenticated
USING (has_recruiter_role());

-- CV Files
CREATE POLICY cv_files_select_authenticated
ON cv_files FOR SELECT
TO authenticated
USING (has_recruiter_role() OR has_viewer_role());

CREATE POLICY cv_files_insert_authenticated
ON cv_files FOR INSERT
TO authenticated
WITH CHECK (has_recruiter_role());

CREATE POLICY cv_files_update_authenticated
ON cv_files FOR UPDATE
TO authenticated
USING (has_recruiter_role())
WITH CHECK (has_recruiter_role());

-- Candidate Skills
CREATE POLICY candidate_skills_select_authenticated
ON candidate_skills FOR SELECT
TO authenticated
USING (has_recruiter_role() OR has_viewer_role());

CREATE POLICY candidate_skills_insert_authenticated
ON candidate_skills FOR INSERT
TO authenticated
WITH CHECK (has_recruiter_role());

CREATE POLICY candidate_skills_update_authenticated
ON candidate_skills FOR UPDATE
TO authenticated
USING (has_recruiter_role())
WITH CHECK (has_recruiter_role());

-- Jobs
CREATE POLICY jobs_select_authenticated
ON jobs FOR SELECT
TO authenticated
USING (has_recruiter_role() OR has_viewer_role());

CREATE POLICY jobs_insert_authenticated
ON jobs FOR INSERT
TO authenticated
WITH CHECK (has_recruiter_role());

CREATE POLICY jobs_update_authenticated
ON jobs FOR UPDATE
TO authenticated
USING (has_recruiter_role())
WITH CHECK (has_recruiter_role());

-- Contacts
CREATE POLICY contacts_select_authenticated
ON contacts FOR SELECT
TO authenticated
USING (has_recruiter_role() OR has_viewer_role());

CREATE POLICY contacts_insert_authenticated
ON contacts FOR INSERT
TO authenticated
WITH CHECK (has_recruiter_role());

CREATE POLICY contacts_update_authenticated
ON contacts FOR UPDATE
TO authenticated
USING (has_recruiter_role())
WITH CHECK (has_recruiter_role());

-- Organizations
CREATE POLICY organizations_select_authenticated
ON organizations FOR SELECT
TO authenticated
USING (has_recruiter_role() OR has_viewer_role());

CREATE POLICY organizations_insert_authenticated
ON organizations FOR INSERT
TO authenticated
WITH CHECK (has_recruiter_role());

CREATE POLICY organizations_update_authenticated
ON organizations FOR UPDATE
TO authenticated
USING (has_recruiter_role())
WITH CHECK (has_recruiter_role());

-- Matches
CREATE POLICY matches_select_authenticated
ON matches FOR SELECT
TO authenticated
USING (has_recruiter_role() OR has_viewer_role());

CREATE POLICY matches_insert_authenticated
ON matches FOR INSERT
TO authenticated
WITH CHECK (has_recruiter_role());

CREATE POLICY matches_update_authenticated
ON matches FOR UPDATE
TO authenticated
USING (has_recruiter_role())
WITH CHECK (has_recruiter_role());

-- Match State History
CREATE POLICY match_state_history_select_authenticated
ON match_state_history FOR SELECT
TO authenticated
USING (has_recruiter_role() OR has_viewer_role());

CREATE POLICY match_state_history_insert_authenticated
ON match_state_history FOR INSERT
TO authenticated
WITH CHECK (has_recruiter_role());

-- Agent Logs
CREATE POLICY agent_logs_select_authenticated
ON agent_logs FOR SELECT
TO authenticated
USING (has_recruiter_role() OR has_viewer_role());

CREATE POLICY agent_logs_insert_authenticated
ON agent_logs FOR INSERT
TO authenticated
WITH CHECK (has_recruiter_role());

-- WhatsApp Conversations & Messages
CREATE POLICY whatsapp_conversations_select_authenticated
ON whatsapp_conversations FOR SELECT
TO authenticated
USING (has_recruiter_role() OR has_viewer_role());

CREATE POLICY whatsapp_conversations_insert_authenticated
ON whatsapp_conversations FOR INSERT
TO authenticated
WITH CHECK (has_recruiter_role());

CREATE POLICY whatsapp_conversations_update_authenticated
ON whatsapp_conversations FOR UPDATE
TO authenticated
USING (has_recruiter_role())
WITH CHECK (has_recruiter_role());

CREATE POLICY whatsapp_messages_select_authenticated
ON whatsapp_messages FOR SELECT
TO authenticated
USING (has_recruiter_role() OR has_viewer_role());

CREATE POLICY whatsapp_messages_insert_authenticated
ON whatsapp_messages FOR INSERT
TO authenticated
WITH CHECK (has_recruiter_role());

-- Telegram Users & Messages
CREATE POLICY telegram_users_select_authenticated
ON telegram_users FOR SELECT
TO authenticated
USING (has_recruiter_role());

CREATE POLICY telegram_users_insert_authenticated
ON telegram_users FOR INSERT
TO authenticated
WITH CHECK (has_recruiter_role());

CREATE POLICY telegram_users_update_authenticated
ON telegram_users FOR UPDATE
TO authenticated
USING (has_recruiter_role())
WITH CHECK (has_recruiter_role());

CREATE POLICY telegram_messages_select_authenticated
ON telegram_messages FOR SELECT
TO authenticated
USING (has_recruiter_role() OR has_viewer_role());

CREATE POLICY telegram_messages_insert_authenticated
ON telegram_messages FOR INSERT
TO authenticated
WITH CHECK (has_recruiter_role());

-- Email Intake Log
CREATE POLICY email_intake_log_select_authenticated
ON email_intake_log FOR SELECT
TO authenticated
USING (has_recruiter_role() OR has_viewer_role());

CREATE POLICY email_intake_log_insert_authenticated
ON email_intake_log FOR INSERT
TO authenticated
WITH CHECK (has_recruiter_role());

CREATE POLICY email_intake_log_update_authenticated
ON email_intake_log FOR UPDATE
TO authenticated
USING (has_recruiter_role())
WITH CHECK (has_recruiter_role());

-- Synonym Dictionary
CREATE POLICY synonym_dictionary_select_authenticated
ON synonym_dictionary FOR SELECT
TO authenticated
USING (TRUE);

CREATE POLICY synonym_dictionary_modify_admin_only
ON synonym_dictionary FOR INSERT
TO authenticated
WITH CHECK (
  EXISTS (
    SELECT 1 FROM users
    WHERE id = auth.uid()
    AND role = 'admin'
    AND is_active = TRUE
  )
);

CREATE POLICY synonym_dictionary_update_admin_only
ON synonym_dictionary FOR UPDATE
TO authenticated
USING (
  EXISTS (
    SELECT 1 FROM users
    WHERE id = auth.uid()
    AND role = 'admin'
    AND is_active = TRUE
  )
)
WITH CHECK (
  EXISTS (
    SELECT 1 FROM users
    WHERE id = auth.uid()
    AND role = 'admin'
    AND is_active = TRUE
  )
);

-- System Settings
CREATE POLICY system_settings_select_admin_only
ON system_settings FOR SELECT
TO authenticated
USING (
  EXISTS (
    SELECT 1 FROM users
    WHERE id = auth.uid()
    AND role = 'admin'
    AND is_active = TRUE
  )
);

CREATE POLICY system_settings_update_admin_only
ON system_settings FOR UPDATE
TO authenticated
USING (
  EXISTS (
    SELECT 1 FROM users
    WHERE id = auth.uid()
    AND role = 'admin'
    AND is_active = TRUE
  )
)
WITH CHECK (
  EXISTS (
    SELECT 1 FROM users
    WHERE id = auth.uid()
    AND role = 'admin'
    AND is_active = TRUE
  )
);

-- Agent Runtime State
CREATE POLICY agent_runtime_state_select_authenticated
ON agent_runtime_state FOR SELECT
TO authenticated
USING (has_recruiter_role() OR has_viewer_role());

CREATE POLICY agent_runtime_state_update_authenticated
ON agent_runtime_state FOR UPDATE
TO authenticated
USING (has_recruiter_role())
WITH CHECK (has_recruiter_role());

-- Users table (standard auth)
ALTER TABLE users ENABLE ROW LEVEL SECURITY;

CREATE POLICY users_select_self
ON users FOR SELECT
TO authenticated
USING (id = auth.uid());

CREATE POLICY users_select_admin
ON users FOR SELECT
TO authenticated
USING (
  EXISTS (
    SELECT 1 FROM users
    WHERE id = auth.uid()
    AND role = 'admin'
    AND is_active = TRUE
  )
);

CREATE POLICY users_update_admin
ON users FOR UPDATE
TO authenticated
USING (
  EXISTS (
    SELECT 1 FROM users
    WHERE id = auth.uid()
    AND role = 'admin'
    AND is_active = TRUE
  )
)
WITH CHECK (
  EXISTS (
    SELECT 1 FROM users
    WHERE id = auth.uid()
    AND role = 'admin'
    AND is_active = TRUE
  )
);

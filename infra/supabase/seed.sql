-- Seed data for PandaPower

-- Synonym Dictionary — security_clearance category
INSERT INTO synonym_dictionary (category, canonical_value, synonyms, language, match_type, case_sensitive, weight, notes, is_active) VALUES
  ('security_clearance', 'top_secret', ARRAY['סודי ביותר', 'סבג"ב', 'ס.ב.ג', 'סיווג גבוה ביותר', 'סיווג בטחוני גבוה ביותר', 'סודי גבוה ביותר', 'TS', 'Top Secret', 'TS/SCI'], 'both', 'substring', FALSE, 1.0, 'Highest security clearance level', TRUE),
  ('security_clearance', 'secret', ARRAY['סודי', 'סיווג סודי', 'סיווג בטחוני סודי', 'Secret', 'S clearance'], 'both', 'substring', FALSE, 1.0, 'Secret level clearance', TRUE),
  ('security_clearance', 'confidential', ARRAY['שמור', 'סיווג שמור', 'Confidential', 'C clearance'], 'both', 'substring', FALSE, 0.9, 'Confidential level clearance', TRUE),
  ('security_clearance', 'highest', ARRAY['סיווג הגבוה ביותר', 'סיווג מקסימלי', 'Highest clearance'], 'both', 'substring', FALSE, 1.0, 'Generic highest clearance', TRUE),
  ('security_clearance', 'clearance_general', ARRAY['בעל סיווג', 'מסווג', 'יש סיווג', 'Cleared', 'Has clearance', 'Security clearance'], 'both', 'substring', FALSE, 0.7, 'Has some clearance but level unknown', TRUE),
  ('security_clearance', 'none', ARRAY['אין סיווג', 'לא מסווג', 'No clearance'], 'both', 'substring', FALSE, 1.0, 'No security clearance', TRUE);

-- Synonym Dictionary — domain category
INSERT INTO synonym_dictionary (category, canonical_value, synonyms, language, match_type, case_sensitive, weight, notes, is_active) VALUES
  ('domain', 'software', ARRAY['תוכנה', 'Software', 'Backend', 'Frontend', 'Full Stack', 'Fullstack', 'Developer', 'Software Engineer', 'מפתח/ת תוכנה'], 'both', 'substring', FALSE, 1.0, 'Software engineering domain', TRUE),
  ('domain', 'electronics', ARRAY['אלקטרוניקה', 'Electronics', 'FPGA', 'VHDL', 'Verilog', 'PCB', 'אנלוגי', 'Analog', 'RF', 'embedded', 'אמבדד'], 'both', 'substring', FALSE, 1.0, 'Electronics/embedded systems domain', TRUE),
  ('domain', 'qa', ARRAY['QA', 'Quality Assurance', 'Test', 'Tester', 'Testing', 'בדיקות', 'בודק/ת תוכנה'], 'both', 'substring', FALSE, 1.0, 'QA and testing domain', TRUE),
  ('domain', 'systems', ARRAY['הנדסת מערכת', 'Systems Engineering', 'Systems Engineer'], 'both', 'substring', FALSE, 1.0, 'Systems engineering domain', TRUE),
  ('domain', 'it', ARRAY['IT', 'DevOps', 'SysAdmin', 'Network', 'תשתיות', 'מערכות מידע', 'סיסטם'], 'both', 'substring', FALSE, 1.0, 'IT/Infrastructure domain', TRUE),
  ('domain', 'mechanical', ARRAY['הנדסת מכונות', 'Mechanical Engineering', 'Mechanical Engineer', 'תכן מכאני'], 'both', 'substring', FALSE, 1.0, 'Mechanical engineering domain', TRUE);

-- System Settings — Azure configuration
INSERT INTO system_settings (setting_key, setting_value, is_secret, description) VALUES
  ('azure.tenant_id', '""'::jsonb, TRUE, 'Azure AD tenant ID'),
  ('azure.app_client_id', '""'::jsonb, TRUE, 'Azure AD application client ID'),
  ('azure.client_secret', '""'::jsonb, TRUE, 'Azure AD client secret'),
  ('azure.target_mailbox', '"jobs@pandatech.co.il"'::jsonb, FALSE, 'Target mailbox for email intake'),
  ('azure.polling_interval_seconds', '120'::jsonb, FALSE, 'Email polling interval in seconds'),
  ('azure.backfill_start_date', '"2021-05-01"'::jsonb, FALSE, 'Start date for historical email backfill');

-- System Settings — Pipedrive configuration
INSERT INTO system_settings (setting_key, setting_value, is_secret, description) VALUES
  ('pipedrive.api_token', '""'::jsonb, TRUE, 'Pipedrive API token'),
  ('pipedrive.api_domain', '""'::jsonb, FALSE, 'Pipedrive API domain'),
  ('pipedrive.bot_user_id', '""'::jsonb, FALSE, 'Pipedrive Bot user ID'),
  ('pipedrive.field_mappings', 'null'::jsonb, FALSE, 'Custom field mappings for deals, persons, and organizations'),
  ('pipedrive.priority_value_mapping', '{"עדיפות גיוס 1": 1, "עדיפות גיוס 2": 2, "עדיפות גיוס 3": 3, "עדיפות גיוס 4": 4, "עדיפות גיוס 5": 5}'::jsonb, FALSE, 'Mapping of Pipedrive priority values to internal priority integers');

-- System Settings — Resend configuration
INSERT INTO system_settings (setting_key, setting_value, is_secret, description) VALUES
  ('resend.api_key', '""'::jsonb, TRUE, 'Resend email API key'),
  ('resend.from_email', '""'::jsonb, FALSE, 'Default sender email address');

-- System Settings — Green API configuration (WhatsApp)
INSERT INTO system_settings (setting_key, setting_value, is_secret, description) VALUES
  ('green_api.instance_id_tal', '""'::jsonb, FALSE, 'Green API instance ID for Tal (WhatsApp outreach agent)'),
  ('green_api.token_tal', '""'::jsonb, TRUE, 'Green API token for Tal'),
  ('green_api.instance_id_elad', '""'::jsonb, FALSE, 'Green API instance ID for Elad (client outreach agent)'),
  ('green_api.token_elad', '""'::jsonb, TRUE, 'Green API token for Elad');

-- System Settings — Anthropic configuration
INSERT INTO system_settings (setting_key, setting_value, is_secret, description) VALUES
  ('anthropic.api_key', '""'::jsonb, TRUE, 'Anthropic Claude API key');

-- System Settings — Telegram configuration
INSERT INTO system_settings (setting_key, setting_value, is_secret, description) VALUES
  ('telegram.bot_token', '""'::jsonb, TRUE, 'Telegram bot token from BotFather'),
  ('telegram.bot_username', '""'::jsonb, FALSE, 'Telegram bot username'),
  ('telegram.webhook_secret', '""'::jsonb, TRUE, 'Telegram webhook secret for authentication'),
  ('telegram.bootstrap_admin_chat_id', '""'::jsonb, FALSE, 'Initial admin chat ID for bot setup'),
  ('telegram.deep_link_base_url', '"https://app.pandapower.io"'::jsonb, FALSE, 'Base URL for deep links in Telegram buttons');

-- System Settings — Forms configuration
INSERT INTO system_settings (setting_key, setting_value, is_secret, description) VALUES
  ('forms.candidate_intake_url', '""'::jsonb, FALSE, 'Google Form URL for candidate intake');

-- System Settings — Agent configuration
INSERT INTO system_settings (setting_key, setting_value, is_secret, description) VALUES
  ('agents.rotation_enabled', 'true'::jsonb, FALSE, 'Enable agent rotation to balance workload'),
  ('agents.max_concurrent_sub_agents', '2'::jsonb, FALSE, 'Maximum number of concurrent sub-agents');

-- System Settings — WhatsApp configuration
INSERT INTO system_settings (setting_key, setting_value, is_secret, description) VALUES
  ('whatsapp.sending_hours', '{"timezone":"Asia/Jerusalem","schedule":{"sun":[9,18],"mon":[9,18],"tue":[9,18],"wed":[9,18],"thu":[9,18],"fri":[9,12],"sat":null}}'::jsonb, FALSE, 'Allowed hours for sending WhatsApp messages by day of week');

-- System Settings — Conflicts configuration
INSERT INTO system_settings (setting_key, setting_value, is_secret, description) VALUES
  ('conflicts.groups', '[["IAI","ELTA","Rafael"]]'::jsonb, FALSE, 'Groups of conflicting organizations (candidate cannot match to multiple)');

-- Agent Runtime State — initialize all agents
INSERT INTO agent_runtime_state (agent_code, status) VALUES
  ('carmit', 'idle'),
  ('alik', 'idle'),
  ('naama', 'idle'),
  ('dganit', 'idle'),
  ('ofir', 'idle'),
  ('itai', 'idle'),
  ('lior', 'idle'),
  ('gc', 'idle'),
  ('tal', 'idle'),
  ('elad', 'idle'),
  ('mani', 'idle'),
  ('dana', 'idle');

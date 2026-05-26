-- Phase 10: Add Pandi configuration to system_settings
-- These settings configure the Pandi bot instance and defaults

-- Assume system_settings table exists (created in earlier migrations)
-- This migration adds Pandi-specific configuration rows

INSERT INTO system_settings (key, value, description, updated_at)
VALUES
  -- Green API integration
  ('pandi.instance_id', '', 'Green API instance ID for Pandi bot (set manually after instance creation)', NOW()),
  ('pandi.token', '', 'Green API API token for Pandi bot (set manually after instance creation)', NOW()),
  ('pandi.whatsapp_number', '', 'WhatsApp number for Pandi bot in E.164 format (e.g., +972501234567)', NOW()),
  ('pandi.webhook_secret', '', 'Secret for validating incoming webhooks from Green API', NOW()),

  -- Messaging defaults
  ('pandi.default_monthly_limit', '100', 'Default monthly message quota for new Pandi clients', NOW()),
  ('pandi.quota_warning_threshold', '0.80', 'Warn client when quota usage exceeds this percentage (0..1)', NOW()),
  ('pandi.intake_timeout_hours', '24', 'Hours to wait for intake response before marking as failed_no_response', NOW()),

  -- Onboarding messages
  ('pandi.message_greeting', 'שלום! אני פנדי, הבוט החכם של PandaTech 🐼. נראה שהגעת אליי לראשונה. אשמח להכיר! מה שמך?', 'Initial greeting message for new clients', NOW()),
  ('pandi.message_company_ask', 'נעים מאוד {name}. מאיזה חברה אתה?', 'Follow-up: ask for company', NOW()),
  ('pandi.message_role_ask', 'ומה תפקידך ב{company}?', 'Follow-up: ask for role', NOW()),
  ('pandi.message_referrer_ask', 'האם מישהו ספציפי מ-PandaTech המליץ לך להגיע אליי? אם כן, מה שמו?', 'Follow-up: ask for referrer', NOW()),

  -- Anonymization
  ('pandi.anonymization_enabled', 'true', 'Enforce candidate_number-only anonymization in Pandi communications', NOW()),

  -- Quotas and limits
  ('pandi.max_candidates_per_response', '5', 'Maximum candidates to present in single response', NOW()),

  -- LLM configuration
  ('pandi.llm_model', 'claude-sonnet-4-5', 'Claude model for Pandi conversations and matching', NOW()),
  ('pandi.llm_temperature', '0.7', 'Temperature for LLM responses (0..1)', NOW())
ON CONFLICT(key) DO NOTHING;

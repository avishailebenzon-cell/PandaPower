-- Create email_intake_log table
CREATE TABLE email_intake_log (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  outlook_message_id TEXT UNIQUE,
  email_subject TEXT,
  email_from TEXT,
  email_received_at TIMESTAMPTZ,
  attachments_count INT,
  cv_files_extracted INT,
  status TEXT,
  error_message TEXT,
  processing_started_at TIMESTAMPTZ,
  processing_completed_at TIMESTAMPTZ,
  processing_duration_ms INT,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_email_log_status ON email_intake_log(status, created_at DESC);
CREATE INDEX idx_email_log_outlook_id ON email_intake_log(outlook_message_id);
CREATE INDEX idx_email_log_created ON email_intake_log(created_at DESC);

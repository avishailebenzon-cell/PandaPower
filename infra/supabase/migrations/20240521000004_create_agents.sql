-- Create agent_logs table
CREATE TABLE agent_logs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  agent_code TEXT NOT NULL,
  action TEXT NOT NULL,
  related_match_id UUID REFERENCES matches(id),
  related_job_id UUID REFERENCES jobs(id),
  related_candidate_id UUID REFERENCES candidates(id),
  input_payload JSONB,
  output_payload JSONB,
  reasoning TEXT,
  llm_model TEXT,
  tokens_used INT,
  duration_ms INT,
  status TEXT,
  error_message TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_agent_logs_agent ON agent_logs(agent_code, created_at);
CREATE INDEX idx_agent_logs_match ON agent_logs(related_match_id);
CREATE INDEX idx_agent_logs_job ON agent_logs(related_job_id);
CREATE INDEX idx_agent_logs_candidate ON agent_logs(related_candidate_id);
CREATE INDEX idx_agent_logs_created ON agent_logs(created_at DESC);

-- Create agent_runtime_state table
CREATE TABLE agent_runtime_state (
  agent_code TEXT PRIMARY KEY,
  status TEXT,
  current_task_description TEXT,
  current_job_id UUID REFERENCES jobs(id),
  current_candidate_id UUID REFERENCES candidates(id),
  matches_found_today INT DEFAULT 0,
  matches_found_this_week INT DEFAULT 0,
  matches_found_this_month INT DEFAULT 0,
  last_active_at TIMESTAMPTZ,
  next_scheduled_at TIMESTAMPTZ
);

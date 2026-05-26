-- Create candidates table
CREATE TABLE candidates (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  full_name_he TEXT,
  full_name_en TEXT,
  email TEXT,
  phone TEXT,
  city TEXT,
  country TEXT DEFAULT 'IL',

  -- CV analysis
  cv_summary TEXT,
  primary_domain TEXT,
  secondary_domains TEXT[],
  years_experience NUMERIC(4,1),

  -- Security clearance
  security_clearance_level TEXT,
  security_clearance_confidence NUMERIC(3,2),
  security_clearance_evidence TEXT[],

  -- Languages
  languages JSONB,

  -- Meta
  is_active BOOLEAN DEFAULT TRUE,
  inactive_reason TEXT,
  pipedrive_person_id BIGINT,

  -- Audit
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW(),
  first_seen_at TIMESTAMPTZ,
  last_cv_at TIMESTAMPTZ
);

CREATE INDEX idx_candidates_email ON candidates(LOWER(email));
CREATE INDEX idx_candidates_phone ON candidates(phone);
CREATE INDEX idx_candidates_domain ON candidates(primary_domain);
CREATE INDEX idx_candidates_active ON candidates(is_active);

-- Create cv_files table
CREATE TABLE cv_files (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  candidate_id UUID REFERENCES candidates(id) ON DELETE CASCADE,
  file_hash CHAR(64) UNIQUE NOT NULL,
  original_filename TEXT,
  storage_path TEXT NOT NULL,
  mime_type TEXT,
  file_size_bytes BIGINT,
  source TEXT,
  source_email_id TEXT,
  source_email_from TEXT,
  source_email_received_at TIMESTAMPTZ,

  -- Analysis results
  raw_text TEXT,
  parse_method TEXT,
  parse_duration_ms INT,
  parse_status TEXT DEFAULT 'pending',
  parse_error TEXT,
  detected_language TEXT,

  -- LLM analysis
  llm_analysis JSONB,
  llm_model TEXT,
  llm_tokens_used INT,

  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_cv_files_candidate ON cv_files(candidate_id);
CREATE INDEX idx_cv_files_hash ON cv_files(file_hash);
CREATE INDEX idx_cv_files_status ON cv_files(parse_status);

-- Create candidate_skills table
CREATE TABLE candidate_skills (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  candidate_id UUID REFERENCES candidates(id) ON DELETE CASCADE,
  skill_name TEXT NOT NULL,
  raw_skill_text TEXT,
  years_in_skill NUMERIC(4,1),
  proficiency TEXT,
  source_cv_id UUID REFERENCES cv_files(id),

  UNIQUE(candidate_id, skill_name)
);

CREATE INDEX idx_skills_candidate ON candidate_skills(candidate_id);
CREATE INDEX idx_skills_name ON candidate_skills(skill_name);

-- Session 35: Elad Premium Client Outreach Campaign System

CREATE TABLE elad_outreach_campaigns (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  campaign_name TEXT NOT NULL,
  created_by_user_id UUID NOT NULL REFERENCES users(id),
  message_template TEXT NOT NULL,  -- Template with {placeholders}
  filters JSONB,  -- {organization_ids: [], domains: [], clearance_levels: []}
  status TEXT DEFAULT 'draft',  -- draft | scheduled | in_progress | completed | paused
  scheduled_start_at TIMESTAMPTZ,
  started_at TIMESTAMPTZ,
  completed_at TIMESTAMPTZ,
  total_contacts INT DEFAULT 0,
  sent_count INT DEFAULT 0,
  failed_count INT DEFAULT 0,
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE elad_outreach_messages (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  campaign_id UUID NOT NULL REFERENCES elad_outreach_campaigns(id) ON DELETE CASCADE,
  contact_id UUID NOT NULL REFERENCES contacts(id),
  pandi_client_id UUID REFERENCES pandi_clients(id),  -- Link if already Pandi client
  message_text TEXT NOT NULL,  -- Rendered message with values substituted
  green_api_chat_id TEXT,  -- phone@c.us format
  green_api_message_id TEXT UNIQUE,
  status TEXT DEFAULT 'pending',  -- pending | sent | failed | bounced | no_whatsapp
  sent_at TIMESTAMPTZ,
  error_message TEXT,
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_elad_outreach_campaign ON elad_outreach_messages(campaign_id);
CREATE INDEX idx_elad_outreach_status ON elad_outreach_messages(status);
CREATE INDEX idx_elad_outreach_contact ON elad_outreach_messages(contact_id);

-- Enable RLS
ALTER TABLE elad_outreach_campaigns ENABLE ROW LEVEL SECURITY;
ALTER TABLE elad_outreach_messages ENABLE ROW LEVEL SECURITY;

-- RLS Policies: Admins only
CREATE POLICY "Admins can view campaigns" ON elad_outreach_campaigns
  FOR SELECT USING (
    EXISTS (
      SELECT 1 FROM user_roles ur
      WHERE ur.user_id = auth.uid() AND ur.role_name IN ('admin', 'superadmin')
    )
  );

CREATE POLICY "Admins can create campaigns" ON elad_outreach_campaigns
  FOR INSERT WITH CHECK (
    EXISTS (
      SELECT 1 FROM user_roles ur
      WHERE ur.user_id = auth.uid() AND ur.role_name IN ('admin', 'superadmin')
    )
  );

CREATE POLICY "Admins can update campaigns" ON elad_outreach_campaigns
  FOR UPDATE USING (
    EXISTS (
      SELECT 1 FROM user_roles ur
      WHERE ur.user_id = auth.uid() AND ur.role_name IN ('admin', 'superadmin')
    )
  );

CREATE POLICY "Admins can view messages" ON elad_outreach_messages
  FOR SELECT USING (
    EXISTS (
      SELECT 1 FROM user_roles ur
      WHERE ur.user_id = auth.uid() AND ur.role_name IN ('admin', 'superadmin')
    )
  );

CREATE POLICY "Admins can create messages" ON elad_outreach_messages
  FOR INSERT WITH CHECK (
    EXISTS (
      SELECT 1 FROM user_roles ur
      WHERE ur.user_id = auth.uid() AND ur.role_name IN ('admin', 'superadmin')
    )
  );

CREATE POLICY "Admins can update messages" ON elad_outreach_messages
  FOR UPDATE USING (
    EXISTS (
      SELECT 1 FROM user_roles ur
      WHERE ur.user_id = auth.uid() AND ur.role_name IN ('admin', 'superadmin')
    )
  );

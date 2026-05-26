-- Phase 10: Create Pandi helper views
-- These views provide convenient data access for dashboards and API responses

-- v_referrals_with_context: Referrals with all related data joined
CREATE OR REPLACE VIEW v_referrals_with_context AS
SELECT
  r.id,
  r.candidate_id,
  r.candidate_number,
  r.pandi_client_id,
  r.conversation_id,
  r.job_context,
  r.matched_job_id,
  r.presented_at,
  r.status,
  r.status_updated_at,
  -- Candidate info (internal only)
  c.full_name_he AS candidate_name_internal,
  c.primary_domain AS candidate_domain,
  c.years_experience AS candidate_years,
  c.security_clearance_level AS candidate_clearance,
  -- Client info
  pc.phone AS client_phone,
  ct.full_name AS client_name,
  o.name AS client_org_name,
  -- Job info (if matched to internal job)
  j.title AS matched_job_title,
  j.pipedrive_deal_id AS matched_job_pipedrive_id,
  -- Audit
  r.created_at,
  r.updated_at
FROM candidate_referrals r
JOIN candidates c ON c.id = r.candidate_id
JOIN pandi_clients pc ON pc.id = r.pandi_client_id
JOIN contacts ct ON ct.id = pc.contact_id
LEFT JOIN organizations o ON o.id = ct.organization_id
LEFT JOIN jobs j ON j.id = r.matched_job_id;

-- v_pandi_active_conversations: Active conversations per client
CREATE OR REPLACE VIEW v_pandi_active_conversations AS
SELECT
  pc.id AS pandi_client_id,
  pc.phone,
  ct.full_name AS client_name,
  o.name AS client_org_name,
  COUNT(conv.id) FILTER (WHERE conv.status NOT IN ('closed_idle', 'closed_by_quota', 'closed_by_admin')) AS active_conversations,
  COUNT(conv.id) AS total_conversations,
  MAX(conv.last_activity_at) AS last_activity_at,
  MAX(conv.started_at) AS most_recent_conversation_started_at
FROM pandi_clients pc
JOIN contacts ct ON ct.id = pc.contact_id
LEFT JOIN organizations o ON o.id = ct.organization_id
LEFT JOIN pandi_conversations conv ON conv.pandi_client_id = pc.id
WHERE pc.is_active = TRUE
GROUP BY pc.id, pc.phone, ct.full_name, o.name;

-- v_pandi_quota_status: Quota usage summary per client per month
CREATE OR REPLACE VIEW v_pandi_quota_status AS
SELECT
  q.id,
  q.pandi_client_id,
  q.month,
  pc.phone AS client_phone,
  ct.full_name AS client_name,
  q.monthly_limit,
  COALESCE(q.increase_approved_amount, 0) AS increase_approved_amount,
  (q.monthly_limit + COALESCE(q.increase_approved_amount, 0)) AS total_available,
  q.messages_used,
  ROUND(
    (q.messages_used::numeric / NULLIF(q.monthly_limit + COALESCE(q.increase_approved_amount, 0), 0)) * 100,
    1
  ) AS usage_percentage,
  -- Quota state determination
  CASE
    WHEN q.increase_requested_at IS NOT NULL AND q.increase_approved_at IS NULL THEN 'pending_approval'
    WHEN q.messages_used >= (q.monthly_limit + COALESCE(q.increase_approved_amount, 0)) THEN 'exhausted'
    WHEN q.messages_used >= 0.8 * (q.monthly_limit + COALESCE(q.increase_approved_amount, 0)) THEN 'warning'
    ELSE 'ok'
  END AS quota_state,
  -- Increase request info
  q.increase_requested_at,
  q.increase_requested_amount,
  q.increase_approved_at,
  q.increase_approved_by_user_id,
  q.increase_approved_amount,
  -- Audit
  q.created_at,
  q.updated_at
FROM pandi_message_quotas q
JOIN pandi_clients pc ON pc.id = q.pandi_client_id
JOIN contacts ct ON ct.id = pc.contact_id;

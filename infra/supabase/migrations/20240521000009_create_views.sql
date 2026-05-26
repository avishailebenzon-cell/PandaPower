-- Create v_active_matches view
CREATE VIEW v_active_matches AS
SELECT
  m.id,
  m.candidate_id,
  m.job_id,
  m.match_score,
  m.match_reasoning,
  m.matched_by_agent_code,
  m.current_state,
  m.state_updated_at,
  m.carmit_review_notes,
  m.carmit_blocked_reason,
  m.tal_summary,
  m.elad_sent_at,
  m.created_at,
  m.updated_at,
  c.full_name_he AS candidate_name,
  c.email AS candidate_email,
  c.primary_domain AS candidate_domain,
  c.security_clearance_level AS candidate_clearance,
  j.title AS job_title,
  j.classification_level,
  j.priority,
  j.pipedrive_deal_id,
  o.name AS client_name,
  o.org_type AS client_type
FROM matches m
JOIN candidates c ON c.id = m.candidate_id AND c.is_active = TRUE
JOIN jobs j ON j.id = m.job_id AND j.is_active = TRUE
LEFT JOIN organizations o ON o.id = j.client_org_id;

-- Create v_agent_stats view
CREATE VIEW v_agent_stats AS
SELECT
  matched_by_agent_code AS agent_code,
  COUNT(*) FILTER (WHERE created_at::date = CURRENT_DATE) AS today,
  COUNT(*) FILTER (WHERE created_at >= date_trunc('week', NOW())) AS this_week,
  COUNT(*) FILTER (WHERE created_at >= date_trunc('month', NOW())) AS this_month,
  COUNT(*) FILTER (WHERE created_at >= date_trunc('quarter', NOW())) AS this_quarter,
  COUNT(*) FILTER (WHERE created_at >= date_trunc('year', NOW())) AS this_year,
  COUNT(*) FILTER (WHERE current_state = 'elad_done') AS completed,
  COUNT(*) AS all_time
FROM matches
WHERE matched_by_agent_code IS NOT NULL
GROUP BY matched_by_agent_code;

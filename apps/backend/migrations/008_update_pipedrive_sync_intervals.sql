-- Migration: Update Pipedrive Sync Intervals to Hours
-- Date: 2026-06-02
-- Description: Convert sync intervals from minutes to hours for better performance
-- - persons (contacts): 60 minutes -> 1440 minutes (24 hours)
-- - organizations: 60 minutes -> 1440 minutes (24 hours)
-- - deals (jobs): 30 minutes -> 240 minutes (4 hours)

UPDATE pipedrive_sync_schedule
SET sync_interval_minutes = CASE
  WHEN entity_type = 'persons' THEN 1440
  WHEN entity_type = 'organizations' THEN 1440
  WHEN entity_type = 'deals' THEN 240
  ELSE sync_interval_minutes
END,
updated_at = NOW()
WHERE entity_type IN ('persons', 'organizations', 'deals');

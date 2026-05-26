-- Migration: Add Sync Schedule Timing Fields
-- Date: 2026-05-24
-- Description: Add sync_days (weekly schedule) and sync_time (time of day) to sync schedule configuration

-- Add columns to pipedrive_sync_schedule table
ALTER TABLE IF EXISTS pipedrive_sync_schedule
ADD COLUMN IF NOT EXISTS sync_days BOOLEAN[] DEFAULT ARRAY[true, true, true, true, true, false, false]::BOOLEAN[],
ADD COLUMN IF NOT EXISTS sync_time TEXT DEFAULT '02:00'; -- Default to 2:00 AM UTC

-- Add comment for documentation
COMMENT ON COLUMN pipedrive_sync_schedule.sync_days IS 'Days of week when sync is enabled: [Monday, Tuesday, Wednesday, Thursday, Friday, Saturday, Sunday]';
COMMENT ON COLUMN pipedrive_sync_schedule.sync_time IS 'Time of day to perform sync in HH:MM format (24-hour). Example: "14:30" for 2:30 PM UTC';

-- Update existing schedules with default values
UPDATE pipedrive_sync_schedule
SET sync_days = ARRAY[true, true, true, true, true, false, false]::BOOLEAN[],
    sync_time = '02:00'
WHERE sync_days IS NULL OR sync_time IS NULL;

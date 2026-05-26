"""Database schema setup helpers for Supabase."""
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

SCHEMA_MIGRATIONS = {
    "jobs": """
    CREATE TABLE IF NOT EXISTS jobs (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        pipedrive_deal_id INT UNIQUE,
        job_title TEXT NOT NULL,
        job_description TEXT,
        job_qualifications TEXT,
        job_location TEXT,
        job_security_clearance TEXT,
        deadline DATE,
        priority TEXT,
        classification_level TEXT,
        person_id INT,
        org_id INT,
        stage_id INT,
        status TEXT DEFAULT 'open',
        pipedrive_last_synced_at TIMESTAMPTZ,
        created_at TIMESTAMPTZ DEFAULT NOW(),
        updated_at TIMESTAMPTZ DEFAULT NOW()
    );
    CREATE INDEX IF NOT EXISTS idx_jobs_pipedrive_id ON jobs(pipedrive_deal_id);
    CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
    CREATE INDEX IF NOT EXISTS idx_jobs_person_id ON jobs(person_id);
    CREATE INDEX IF NOT EXISTS idx_jobs_job_title ON jobs(job_title);
    """,
    "pipedrive_config": """
    CREATE TABLE IF NOT EXISTS pipedrive_config (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        api_token TEXT NOT NULL,
        api_domain TEXT DEFAULT 'https://api.pipedrive.com',
        bot_user_id TEXT,
        is_active BOOLEAN DEFAULT false,
        last_validated_at TIMESTAMPTZ,
        validation_error TEXT,
        created_at TIMESTAMPTZ DEFAULT NOW(),
        updated_at TIMESTAMPTZ DEFAULT NOW()
    );
    """,
    "system_settings": """
    CREATE TABLE IF NOT EXISTS system_settings (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        setting_key TEXT UNIQUE NOT NULL,
        setting_value TEXT,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
        updated_at TIMESTAMP WITH TIME ZONE DEFAULT now()
    );
    """,
    "email_intake_log": """
    CREATE TABLE IF NOT EXISTS email_intake_log (
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
    CREATE INDEX IF NOT EXISTS idx_email_log_status ON email_intake_log(status, created_at DESC);
    CREATE INDEX IF NOT EXISTS idx_email_log_outlook_id ON email_intake_log(outlook_message_id);
    CREATE INDEX IF NOT EXISTS idx_email_log_created ON email_intake_log(created_at DESC);
    """,
    "cv_files": """
    CREATE TABLE IF NOT EXISTS cv_files (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        file_hash TEXT UNIQUE NOT NULL,
        original_filename TEXT,
        storage_path TEXT NOT NULL,
        mime_type TEXT,
        file_size_bytes INTEGER,
        source TEXT DEFAULT 'outlook',
        source_email_id TEXT,
        source_email_from TEXT,
        source_email_received_at TIMESTAMPTZ,
        parse_status TEXT DEFAULT 'pending',
        created_at TIMESTAMPTZ DEFAULT NOW()
    );
    CREATE INDEX IF NOT EXISTS idx_cv_files_parse_status ON cv_files(parse_status);
    CREATE INDEX IF NOT EXISTS idx_cv_files_email_id ON cv_files(source_email_id);
    """,
    "pipedrive_field_mappings": """
    CREATE TABLE IF NOT EXISTS pipedrive_field_mappings (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        field_type TEXT NOT NULL,
        field_category TEXT NOT NULL,
        pandapower_field_name TEXT NOT NULL,
        pipedrive_field_key TEXT NOT NULL,
        pipedrive_field_id INT,
        pipedrive_field_name TEXT,
        field_data_type TEXT,
        is_active BOOLEAN DEFAULT true,
        validation_notes TEXT,
        created_at TIMESTAMPTZ DEFAULT NOW(),
        updated_at TIMESTAMPTZ DEFAULT NOW(),
        UNIQUE(field_type, pandapower_field_name)
    );
    CREATE INDEX IF NOT EXISTS idx_pipedrive_mappings_field_type ON pipedrive_field_mappings(field_type);
    CREATE INDEX IF NOT EXISTS idx_pipedrive_mappings_active ON pipedrive_field_mappings(is_active);

    INSERT INTO pipedrive_field_mappings (field_type, field_category, pandapower_field_name, pipedrive_field_key, pipedrive_field_name, is_active)
    VALUES
        ('deal', 'rejection', 'rejection_reasons', 'rejection_reasons_field', 'Rejection Reasons', true),
        ('person', 'clearance', 'clearance_level', 'clearance_level_field', 'Clearance Level', true),
        ('person', 'status', 'declining_status', 'declining_status_field', 'Declining Status', true),
        ('deal', 'job', 'required_clearance', 'required_clearance_field', 'Required Clearance', true)
    ON CONFLICT DO NOTHING;
    """,
    "pipedrive_sync_schedule": """
    CREATE TABLE IF NOT EXISTS pipedrive_sync_schedule (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        entity_type TEXT UNIQUE NOT NULL,
        sync_interval_minutes INT DEFAULT 30,
        sync_direction TEXT DEFAULT 'bidirectional',
        sync_enabled BOOLEAN DEFAULT true,
        filter_by_contact_type TEXT,
        filter_by_status TEXT,
        sync_days BOOLEAN[],
        sync_time TEXT,
        last_sync_at TIMESTAMPTZ,
        last_sync_status TEXT,
        next_scheduled_sync TIMESTAMPTZ,
        sync_count INT DEFAULT 0,
        created_at TIMESTAMPTZ DEFAULT NOW(),
        updated_at TIMESTAMPTZ DEFAULT NOW()
    );
    CREATE INDEX IF NOT EXISTS idx_pipedrive_sync_entity ON pipedrive_sync_schedule(entity_type);
    """,
    "pipedrive_sync_log": """
    CREATE TABLE IF NOT EXISTS pipedrive_sync_log (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        entity_type TEXT NOT NULL,
        sync_direction TEXT DEFAULT 'bidirectional',
        status TEXT NOT NULL,
        records_processed INT DEFAULT 0,
        records_created INT DEFAULT 0,
        records_updated INT DEFAULT 0,
        records_failed INT DEFAULT 0,
        error_message TEXT,
        started_at TIMESTAMPTZ DEFAULT NOW(),
        completed_at TIMESTAMPTZ,
        duration_ms INT,
        created_at TIMESTAMPTZ DEFAULT NOW()
    );
    CREATE INDEX IF NOT EXISTS idx_pipedrive_sync_log_entity ON pipedrive_sync_log(entity_type);
    CREATE INDEX IF NOT EXISTS idx_pipedrive_sync_log_status ON pipedrive_sync_log(status);
    CREATE INDEX IF NOT EXISTS idx_pipedrive_sync_log_started ON pipedrive_sync_log(started_at DESC);
    """,
    "matches": """
    CREATE TABLE IF NOT EXISTS matches (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        candidate_id UUID REFERENCES candidates(id) ON DELETE CASCADE,
        job_id UUID REFERENCES jobs(id) ON DELETE CASCADE,
        match_score NUMERIC(5,2),
        match_reasoning TEXT,
        matched_by_agent_code TEXT,
        current_state TEXT NOT NULL DEFAULT 'found',
        state_updated_at TIMESTAMPTZ DEFAULT NOW(),
        state_updated_by_agent TEXT,
        carmit_review_notes TEXT,
        carmit_blocked_reason TEXT,
        tal_conversation_id UUID,
        tal_summary TEXT,
        tal_decision_reason TEXT,
        elad_sent_to_client_id UUID,
        elad_sent_at TIMESTAMPTZ,
        pipedrive_note_id BIGINT,
        is_valid BOOLEAN DEFAULT TRUE,
        invalidated_at TIMESTAMPTZ,
        invalidation_reason TEXT,
        invalidated_by TEXT,
        last_job_spec_check_at TIMESTAMPTZ,
        job_spec_hash_at_match_creation TEXT,
        created_at TIMESTAMPTZ DEFAULT NOW(),
        updated_at TIMESTAMPTZ DEFAULT NOW(),
        UNIQUE(candidate_id, job_id)
    );
    CREATE INDEX IF NOT EXISTS idx_matches_state ON matches(current_state);
    CREATE INDEX IF NOT EXISTS idx_matches_job ON matches(job_id);
    CREATE INDEX IF NOT EXISTS idx_matches_candidate ON matches(candidate_id);
    CREATE INDEX IF NOT EXISTS idx_matches_score ON matches(match_score DESC);
    CREATE INDEX IF NOT EXISTS idx_matches_created ON matches(created_at DESC);
    CREATE INDEX IF NOT EXISTS idx_matches_is_valid ON matches(is_valid);
    CREATE INDEX IF NOT EXISTS idx_matches_matched_by_agent ON matches(matched_by_agent_code);
    """,
    "agent_runtime_state": """
    CREATE TABLE IF NOT EXISTS agent_runtime_state (
        agent_code TEXT PRIMARY KEY,
        status TEXT DEFAULT 'idle',
        current_task_description TEXT,
        current_job_id UUID REFERENCES jobs(id) ON DELETE SET NULL,
        matches_found_today INT DEFAULT 0,
        matches_found_week INT DEFAULT 0,
        matches_found_month INT DEFAULT 0,
        last_active_at TIMESTAMPTZ,
        next_scheduled_at TIMESTAMPTZ,
        last_modified_at TIMESTAMPTZ DEFAULT NOW()
    );
    CREATE INDEX IF NOT EXISTS idx_agent_runtime_status ON agent_runtime_state(status);
    CREATE INDEX IF NOT EXISTS idx_agent_runtime_last_active ON agent_runtime_state(last_active_at DESC);
    """,
    "agent_logs": """
    CREATE TABLE IF NOT EXISTS agent_logs (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        agent_code TEXT NOT NULL,
        action TEXT NOT NULL,
        related_job_id UUID REFERENCES jobs(id) ON DELETE SET NULL,
        related_candidate_id UUID REFERENCES candidates(id) ON DELETE SET NULL,
        related_match_id UUID REFERENCES matches(id) ON DELETE SET NULL,
        input_payload JSONB,
        output_payload JSONB,
        error_message TEXT,
        milestone TEXT,
        created_at TIMESTAMPTZ DEFAULT NOW()
    );
    CREATE INDEX IF NOT EXISTS idx_agent_logs_agent ON agent_logs(agent_code);
    CREATE INDEX IF NOT EXISTS idx_agent_logs_action ON agent_logs(action);
    CREATE INDEX IF NOT EXISTS idx_agent_logs_created ON agent_logs(created_at DESC);
    CREATE INDEX IF NOT EXISTS idx_agent_logs_job ON agent_logs(related_job_id);
    CREATE INDEX IF NOT EXISTS idx_agent_logs_candidate ON agent_logs(related_candidate_id);
    CREATE INDEX IF NOT EXISTS idx_agent_logs_match ON agent_logs(related_match_id);
    """,
    "job_changes": """
    CREATE TABLE IF NOT EXISTS job_changes (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        job_id UUID NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
        change_type TEXT NOT NULL,
        changed_by TEXT,
        changed_at TIMESTAMPTZ DEFAULT NOW(),
        previous_values JSONB,
        new_values JSONB,
        fields_changed TEXT[],
        job_spec_hash_before TEXT,
        job_spec_hash_after TEXT,
        affected_matches_count INT,
        created_at TIMESTAMPTZ DEFAULT NOW()
    );
    CREATE INDEX IF NOT EXISTS idx_job_changes_job ON job_changes(job_id);
    CREATE INDEX IF NOT EXISTS idx_job_changes_created ON job_changes(created_at DESC);
    """,
}


async def apply_migrations(supabase_client: Any) -> dict[str, Any]:
    """Apply all pending database migrations."""
    results = {}

    # Try to execute SQL directly using psycopg2
    import psycopg2
    from psycopg2 import sql as psycopg2_sql

    db_connection = None
    try:
        # Get Supabase connection details from environment or configuration
        from pandapower.core.config import Settings
        settings = Settings()

        # Construct database URL from Supabase credentials
        # For Supabase, the database host is: {project_id}.c.supabase.co
        project_id = "xknzpurparakylocrnld"  # From SUPABASE_URL
        db_host = f"{project_id}.c.supabase.co"
        db_port = 5432
        db_name = "postgres"
        db_user = "postgres"

        # Try to get password from environment - if not available, skip SQL execution
        db_password = os.environ.get("SUPABASE_DB_PASSWORD")

        if not db_password:
            # Fallback: Try extracting from Supabase service role key (not ideal but sometimes works)
            logger.warning("SUPABASE_DB_PASSWORD not set. Migrations will require manual execution.")
            for table_name in SCHEMA_MIGRATIONS.keys():
                results[table_name] = "requires manual SQL execution - SUPABASE_DB_PASSWORD not set"
            return results

        # Connect to database
        db_connection = psycopg2.connect(
            host=db_host,
            port=db_port,
            database=db_name,
            user=db_user,
            password=db_password,
            sslmode="require"
        )

        cursor = db_connection.cursor()

        # Execute each migration
        for table_name, migration_sql in SCHEMA_MIGRATIONS.items():
            try:
                cursor.execute(migration_sql)
                db_connection.commit()
                results[table_name] = "success"
                logger.info(f"Migration executed successfully for {table_name}")
            except Exception as e:
                db_connection.rollback()
                results[table_name] = f"failed - {str(e)}"
                logger.error(f"Migration failed for {table_name}: {str(e)}")

        cursor.close()

    except Exception as e:
        logger.error(f"Failed to establish database connection: {str(e)}")
        for table_name in SCHEMA_MIGRATIONS.keys():
            if table_name not in results:
                results[table_name] = f"failed - {str(e)}"

    finally:
        if db_connection:
            try:
                db_connection.close()
            except:
                pass

    return results


async def init_system_settings(supabase_client: Any) -> None:
    """Initialize default system settings."""
    default_settings = {
        "azure.tenant_id": "",
        "azure.app_client_id": "",
        "azure.client_secret": "",
        "azure.target_mailbox": "",
        "azure.last_seen_message_received_at": "null",
        "azure.backfill_start_date": "2021-05-01",
    }

    for key, value in default_settings.items():
        try:
            supabase_client.table("system_settings").upsert(
                {
                    "setting_key": key,
                    "setting_value": f'"{value}"' if value != "null" else "null",
                },
                on_conflict="setting_key",
            ).execute()
            logger.info(f"Initialized setting: {key}")
        except Exception as e:
            logger.warning(f"Failed to initialize setting {key}: {e}")

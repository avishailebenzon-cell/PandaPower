#!/usr/bin/env python3
"""
Apply a single SQL migration file to Supabase.
This uses psycopg2 to connect directly to the database.
"""
import sys
import os
from pathlib import Path
import logging

# Add the backend to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from pandapower.core.config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def apply_migration_via_direct_connection(migration_file: str) -> bool:
    """Apply a migration using direct psycopg2 connection."""
    try:
        import psycopg2
    except ImportError:
        logger.error("psycopg2 not installed. Installing it...")
        os.system("pip install psycopg2-binary")
        import psycopg2

    try:
        # Extract project ID from Supabase URL
        supabase_url = settings.SUPABASE_URL
        project_id = supabase_url.split("//")[1].split(".")[0]

        # Try to get database password from environment
        db_password = os.getenv("SUPABASE_DB_PASSWORD")
        if not db_password:
            # Try using the service role key as fallback
            db_password = settings.SUPABASE_SERVICE_ROLE_KEY
            logger.warning("SUPABASE_DB_PASSWORD not set, using SERVICE_ROLE_KEY")

        db_url = f"postgresql://postgres:{db_password}@db.{project_id}.supabase.co:5432/postgres"

        logger.info(f"Connecting to Supabase database: {project_id}")
        conn = psycopg2.connect(db_url)
        conn.autocommit = True
        cursor = conn.cursor()

        logger.info(f"Connected successfully")

        # Read migration file
        migration_path = Path(migration_file)
        if not migration_path.exists():
            logger.error(f"Migration file not found: {migration_file}")
            return False

        sql_content = migration_path.read_text()
        logger.info(f"Applying migration: {migration_path.name}")

        # Execute the migration
        cursor.execute(sql_content)
        logger.info(f"✓ Migration applied successfully: {migration_path.name}")

        cursor.close()
        conn.close()
        return True

    except Exception as e:
        logger.error(f"Error applying migration: {e}")
        return False


def apply_migration_via_supabase_client(migration_file: str) -> bool:
    """Apply a migration using Supabase Python client."""
    try:
        from supabase import create_client
        import asyncio

        # Create Supabase client
        supabase = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)

        # Read migration file
        migration_path = Path(migration_file)
        if not migration_path.exists():
            logger.error(f"Migration file not found: {migration_file}")
            return False

        sql_content = migration_path.read_text()
        logger.info(f"Applying migration: {migration_path.name}")

        # Execute the SQL via RPC (if available) or direct query
        # Note: This approach won't work with standard Supabase client for raw SQL
        # We'll need to use the REST API directly or psycopg2

        logger.info("Supabase Python client doesn't support raw SQL execution")
        logger.info("Please use direct psycopg2 connection instead")
        return False

    except Exception as e:
        logger.error(f"Error: {e}")
        return False


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python apply_single_migration.py <migration_file>")
        print("Example: python apply_single_migration.py ../../../infra/supabase/migrations/20260525000004_add_override_job_assignment_rpc.sql")
        sys.exit(1)

    migration_file = sys.argv[1]
    success = apply_migration_via_direct_connection(migration_file)
    sys.exit(0 if success else 1)

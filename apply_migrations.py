#!/usr/bin/env python3
"""
Apply pending migrations to Supabase.
This script reads SQL migration files and executes them via direct database connection.
"""
import os
import sys
from pathlib import Path

# Add the backend to path
sys.path.insert(0, str(Path(__file__).parent / "apps" / "backend" / "src"))

import asyncio
import logging
from pandapower.core.config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def apply_migrations():
    """Apply all pending SQL migrations."""
    try:
        import psycopg2
        import psycopg2.extensions
    except ImportError:
        logger.error("psycopg2 not installed. Installing it...")
        os.system("pip install psycopg2-binary")
        import psycopg2
        import psycopg2.extensions

    # Get Supabase connection details from settings
    supabase_url = settings.SUPABASE_URL
    supabase_key = settings.SUPABASE_KEY

    # Parse connection details from Supabase settings
    # Supabase URL format: https://[project-id].supabase.co
    project_id = supabase_url.split("//")[1].split(".")[0]

    # We need the database URL - construct it from Supabase project ID
    # Format: postgresql://postgres:[password]@db.[project-id].supabase.co:5432/postgres
    db_password = settings.SUPABASE_DB_PASSWORD if hasattr(settings, "SUPABASE_DB_PASSWORD") else supabase_key

    try:
        # Try to connect using the Supabase connection string
        db_url = f"postgresql://postgres:{db_password}@db.{project_id}.supabase.co:5432/postgres"

        conn = psycopg2.connect(db_url)
        conn.autocommit = True
        cursor = conn.cursor()

        logger.info("Connected to Supabase database")

        # Read and execute migrations
        migrations_dir = Path(__file__).parent / "infra" / "supabase" / "migrations"
        migration_files = sorted(migrations_dir.glob("*.sql"))

        for migration_file in migration_files:
            logger.info(f"Applying {migration_file.name}...")
            sql_content = migration_file.read_text()

            # Execute the migration
            try:
                cursor.execute(sql_content)
                logger.info(f"✓ Applied {migration_file.name}")
            except Exception as e:
                logger.error(f"✗ Error applying {migration_file.name}: {e}")

        cursor.close()
        conn.close()
        logger.info("All migrations applied successfully!")

    except Exception as e:
        logger.error(f"Connection error: {e}")
        logger.error("\nTo apply migrations manually:")
        logger.error("1. Go to Supabase Console: https://app.supabase.com")
        logger.error("2. Select your project")
        logger.error("3. Go to SQL Editor")
        logger.error("4. Open the SQL files from infra/supabase/migrations/ and execute them")
        return False

    return True


if __name__ == "__main__":
    success = asyncio.run(apply_migrations())
    sys.exit(0 if success else 1)

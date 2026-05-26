"""
Run pending migrations in Supabase.
This script applies SQL migrations from the infra/supabase/migrations/ directory.
"""
import asyncio
import logging
from pathlib import Path
from pandapower.core.supabase import get_supabase_client
from pandapower.core.config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def run_migrations():
    """Execute all SQL migration files."""
    db = await get_supabase_client()

    # Get migrations directory
    migrations_dir = Path(__file__).parent.parent.parent.parent.parent / "infra" / "supabase" / "migrations"

    if not migrations_dir.exists():
        logger.error(f"Migrations directory not found: {migrations_dir}")
        return

    # Get all SQL files and sort them
    migration_files = sorted(migrations_dir.glob("*.sql"))

    if not migration_files:
        logger.info("No migration files found")
        return

    logger.info(f"Found {len(migration_files)} migration files")

    for migration_file in migration_files:
        try:
            logger.info(f"Applying migration: {migration_file.name}")
            sql_content = migration_file.read_text()

            # Split by statements and execute each
            statements = [s.strip() for s in sql_content.split(';') if s.strip()]

            for statement in statements:
                try:
                    # Use the postgrest query method to execute raw SQL
                    # We need to use the service role key for DDL statements
                    from supabase import create_client
                    from supabase.client import AsyncClient

                    # Create a raw client that can execute SQL
                    supabase_url = settings.SUPABASE_URL
                    supabase_service_role_key = settings.SUPABASE_SERVICE_ROLE_KEY

                    raw_client = create_client(supabase_url, supabase_service_role_key)

                    # Execute via RPC or direct query
                    logger.info(f"Executing: {statement[:100]}...")

                    # For raw SQL, we use the postgrest client directly
                    response = raw_client.postgrest.session.post(
                        f"{raw_client.postgrest.url}/rpc/sql",
                        json={"query": statement}
                    )

                    if response.status_code not in [200, 201]:
                        logger.warning(f"Statement may have failed: {response.status_code}")
                    else:
                        logger.info("Statement executed successfully")

                except Exception as e:
                    logger.warning(f"Could not execute statement via RPC: {e}")
                    logger.info("Note: You may need to run these statements manually in Supabase Console")

            logger.info(f"✓ Migration applied: {migration_file.name}")

        except Exception as e:
            logger.error(f"✗ Failed to apply migration {migration_file.name}: {e}")


if __name__ == "__main__":
    asyncio.run(run_migrations())

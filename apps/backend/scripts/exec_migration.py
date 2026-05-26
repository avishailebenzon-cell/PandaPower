"""Execute the organizations migration via direct postgres connection.

Tries the Supabase pooler (port 6543) first, then direct connection (port 5432).
"""

import asyncio
import sys
import os
import re
from urllib.parse import urlparse

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from pandapower.core.config import settings


def get_db_password_from_jwt() -> str:
    """Cannot extract DB password from JWT - need to ask user"""
    return None


async def main():
    # Parse Supabase URL to get project ref
    parsed = urlparse(settings.SUPABASE_URL)
    project_ref = parsed.hostname.split(".")[0]

    print(f"Project ref: {project_ref}")
    print(f"Database host options:")
    print(f"  - Pooler: aws-0-eu-central-1.pooler.supabase.com:6543")
    print(f"  - Direct: db.{project_ref}.supabase.co:5432")
    print()
    print("To complete the migration manually, run this SQL in Supabase SQL Editor:")
    print()
    print("=" * 70)
    print(open("migrations/003_add_organization_pipedrive_fields.sql").read())
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())

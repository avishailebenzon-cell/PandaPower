#!/usr/bin/env python3
"""
Aggressive backfill runner for email history ingestion.

GOAL: Process entire email archive (2021-05-02 → present) to bootstrap
candidate pool with 1000+ baseline candidates. Then system maintains via
regular 2-minute schedule.

Usage:
  cd apps/backend
  python3 scripts/run_backfill.py

Expected output:
  ~50 emails/run × 30 CV parse batch × 4 concurrent CV analyzers
  = Thousands of candidates within hours, not days
"""

import sys
import asyncio
import logging
from datetime import datetime

sys.path.insert(0, 'src')

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def run_backfill():
    """Run aggressive email ingest + CV parsing backfill."""
    from pandapower.core.supabase import get_supabase_client
    from pandapower.workers.email_ingest import EmailIngestWorker
    from pandapower.workers.cv_parse import CVParseWorker
    from pandapower.workers.candidate_creation import CandidateCreationWorker
    from pandapower.integrations.azure import AzureGraphClient
    from pandapower.integrations.supabase_storage import SupabaseStorageManager
    from pandapower.integrations.claude_api import AnthropicClient
    from pandapower.core.config import settings

    supabase = await get_supabase_client()

    # Load Azure settings from database
    settings_response = await supabase.table("system_settings").select(
        "setting_key, setting_value"
    ).in_(
        "setting_key",
        [
            "azure.tenant_id",
            "azure.app_client_id",
            "azure.client_secret",
            "azure.target_mailbox",
        ],
    ).execute()

    settings_dict = {}
    for row in settings_response.data or []:
        key = row["setting_key"].split(".")[-1]
        value = row["setting_value"].strip('"') if isinstance(row["setting_value"], str) else row["setting_value"]
        settings_dict[key] = value

    if not all(k in settings_dict for k in ["tenant_id", "app_client_id", "client_secret", "target_mailbox"]):
        logger.error("❌ Azure settings not fully configured in system_settings table")
        return

    # Step 1: Ingest emails (large batch for backfill)
    logger.info("="*80)
    logger.info("STEP 1: EMAIL INGEST (batch_size=50, aggressive backfill)")
    logger.info("="*80)

    azure_client = AzureGraphClient(
        tenant_id=settings_dict["tenant_id"],
        client_id=settings_dict["app_client_id"],
        client_secret=settings_dict["client_secret"],
        target_mailbox=settings_dict["target_mailbox"],
    )
    storage_manager = SupabaseStorageManager(supabase)
    email_worker = EmailIngestWorker(supabase, azure_client, storage_manager)

    # Run ingest in a loop until caught up
    run_count = 0
    total_emails = 0
    while True:
        run_count += 1
        result = await email_worker.ingest_recent_emails(batch_size=50)

        processed = result.get('total_processed', 0)
        total_emails += processed
        cv_extracted = result.get('cv_files_extracted', 0)

        logger.info(f"Run {run_count}: {processed} emails, {cv_extracted} CVs extracted")

        # Stop if no more emails
        if processed < 50:
            logger.info(f"✅ Email ingest caught up: {total_emails} total emails processed")
            break

        # Safety: max 100 runs (~5000 emails)
        if run_count > 100:
            logger.info(f"⚠️  Max runs reached (safety limit): {total_emails} emails processed")
            break

    # Step 2: Parse pending CVs (large batch)
    logger.info("\n" + "="*80)
    logger.info("STEP 2: CV PARSING (batch_size=30, timeout=60s)")
    logger.info("="*80)

    claude_client = AnthropicClient(settings.ANTHROPIC_API_KEY)
    cv_worker = CVParseWorker(
        supabase,
        storage_manager,
        claude_client,
        batch_size=30,
        parse_timeout=60,
    )

    run_count = 0
    total_parsed = 0
    while True:
        run_count += 1
        result = await cv_worker.parse_pending_cvs()

        parsed = result.get('success', 0)
        failed = result.get('failed', 0)
        total_parsed += parsed

        logger.info(f"Run {run_count}: {parsed} parsed, {failed} failed")

        # Stop if no more CVs
        if parsed < 30:
            logger.info(f"✅ CV parsing caught up: {total_parsed} total CVs parsed")
            break

        # Safety: max 50 runs (~1500 CVs)
        if run_count > 50:
            logger.info(f"⚠️  Max runs reached (safety limit): {total_parsed} CVs parsed")
            break

    # Step 3: Create candidates (normalizes skills, calculates confidence)
    logger.info("\n" + "="*80)
    logger.info("STEP 3: CANDIDATE CREATION (normalizes skills, confidence scoring)")
    logger.info("="*80)

    cand_worker = CandidateCreationWorker(supabase)
    result = await cand_worker.create_candidates_from_parsed_cvs()

    logger.info(f"✅ Candidates created: {result.get('total_created', 0)}")
    logger.info(f"✅ Skills normalized: {result.get('skills_normalized', 0)}")

    await claude_client.close()

    # Summary
    logger.info("\n" + "="*80)
    logger.info("BACKFILL COMPLETE")
    logger.info("="*80)
    logger.info(f"Emails processed: {total_emails}")
    logger.info(f"CVs parsed: {total_parsed}")
    logger.info(f"Candidates created: {result.get('total_created', 0)}")
    logger.info("\nNext: Monitor dashboard for matching activity")
    logger.info("System will now maintain via 2-min email schedule + 10-min Carmit routing")


if __name__ == "__main__":
    asyncio.run(run_backfill())

import asyncio
import logging
from datetime import datetime
from typing import Any

from pandapower.workers.celery_app import app
from pandapower.core.supabase import get_supabase_client
from pandapower.core.config import settings
from pandapower.integrations.azure import AzureGraphClient
from pandapower.integrations.claude_api import AnthropicClient
from pandapower.integrations.supabase_storage import SupabaseStorageManager
from pandapower.workers.email_ingest import EmailIngestWorker
from pandapower.workers.cv_parse import CVParseWorker
from pandapower.workers.candidate_creation import CandidateCreationWorker
from pandapower.workers.skill_normalization import SkillNormalizationWorker
from pandapower.workers.candidate_scoring import CandidateScoringWorker
from pandapower.workers.agent_matching import AgentMatchingWorker
from pandapower.workers.carmit import CarmitOrchestrator
from pandapower.integrations.pipedrive import PipedriveClient

logger = logging.getLogger(__name__)


async def _ingest_emails_async(batch_size: int = 20) -> dict[str, Any]:
    """Async implementation of email ingest.

    Args:
        batch_size: Number of messages to fetch per API call (20 is optimal for backfill)
    """
    try:
        supabase_client = await get_supabase_client()

        # Fetch Azure settings from system_settings table
        settings_response = await supabase_client.table("system_settings").select(
            "setting_key, setting_value"
        ).in_(
            "setting_key",
            [
                "azure.tenant_id",
                "azure.app_client_id",
                "azure.client_secret",
                "azure.target_mailbox",
                "azure.backfill_start_date",
                "azure.last_seen_message_received_at",
            ],
        ).execute()

        settings_dict = {}
        for row in settings_response.data or []:
            key = row["setting_key"].split(".")[-1]
            value = row["setting_value"].strip('"') if isinstance(row["setting_value"], str) else row["setting_value"]
            settings_dict[key] = value

        if not all(k in settings_dict for k in ["tenant_id", "app_client_id", "client_secret", "target_mailbox"]):
            logger.warning("Azure settings not fully configured, skipping email ingest")
            return {"status": "skipped", "reason": "Azure settings not configured"}

        # Detect if we're in backfill mode
        # Backfill mode is active when:
        # 1. backfill_start_date is set AND
        # 2. last_seen is null (not yet started) OR we're still processing historical emails
        is_backfill = False
        if settings_dict.get("backfill_start_date") and settings_dict.get("backfill_start_date") != "null":
            # Only consider it backfill if last_seen is not set yet or is set to null
            last_seen_value = settings_dict.get("last_seen_message_received_at", "null")
            is_backfill = last_seen_value == "null" or last_seen_value is None
            if is_backfill:
                logger.info(f"Backfill mode detected: will process more emails per run for faster historical scanning")

        azure_client = AzureGraphClient(
            tenant_id=settings_dict["tenant_id"],
            client_id=settings_dict["app_client_id"],
            client_secret=settings_dict["client_secret"],
            target_mailbox=settings_dict["target_mailbox"],
        )

        storage_manager = SupabaseStorageManager(supabase_client)
        worker = EmailIngestWorker(supabase_client, azure_client, storage_manager, is_backfill=is_backfill)
        result = await worker.ingest_recent_emails(batch_size=batch_size)

        return {
            "status": "completed",
            "total_processed": result.get("total_processed", 0),
            "cv_files_extracted": result.get("cv_files_extracted", 0),
            "duplicates_found": result.get("duplicates_found", 0),
            "backfill_progress": result.get("backfill_progress"),
        }

    except Exception as e:
        logger.error(f"Email ingest task failed: {e}", exc_info=True)
        return {"status": "failed", "error": str(e)}


@app.task(bind=True, max_retries=3)
def ingest_emails_task(self, batch_size: int = 20) -> dict[str, Any]:
    """Celery task to ingest emails every 2 minutes.

    During backfill mode (when azure.backfill_start_date is set):
    - Processes up to 500 emails per run
    - Uses higher concurrency (10 concurrent downloads/uploads)
    - Aims for 15k-30k emails/hour to complete 5+ year backfill quickly

    During incremental mode (normal operation):
    - Processes up to 100 emails per run
    - Uses conservative concurrency (3 concurrent downloads/uploads)
    - Focuses on recent emails to avoid Celery task timeouts

    The mode is auto-detected based on system_settings.
    """
    logger.info(f"Starting email ingest task with batch_size={batch_size}")
    try:
        # Run the async function in a new event loop
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(_ingest_emails_async(batch_size=batch_size))
            logger.info(f"Email ingest completed: {result}")
            return result
        finally:
            loop.close()
    except Exception as e:
        logger.error(f"Email ingest task failed: {e}", exc_info=True)
        # Retry with exponential backoff
        retry_in = 2 ** self.request.retries
        raise self.retry(exc=e, countdown=retry_in)


async def _parse_cvs_async() -> dict[str, Any]:
    """Async implementation of CV parsing."""
    try:
        # Check if API key is configured
        if not settings.ANTHROPIC_API_KEY:
            logger.warning("ANTHROPIC_API_KEY not configured, skipping CV parsing")
            return {"status": "skipped", "reason": "ANTHROPIC_API_KEY not configured"}

        supabase_client = await get_supabase_client()
        claude_client = AnthropicClient(settings.ANTHROPIC_API_KEY)
        storage_manager = SupabaseStorageManager(supabase_client)

        worker = CVParseWorker(
            supabase_client,
            storage_manager,
            claude_client,
            batch_size=settings.CV_PARSE_BATCH_SIZE,
            parse_timeout=settings.CV_PARSE_TIMEOUT_SECONDS,
        )

        result = await worker.parse_pending_cvs()
        await claude_client.close()

        return {
            "status": "completed",
            "total_processed": result.get("total_processed", 0),
            "success": result.get("success", 0),
            "failed": result.get("failed", 0),
            "tokens_used": result.get("tokens_used", 0),
        }

    except Exception as e:
        logger.error(f"CV parsing task failed: {e}", exc_info=True)
        return {"status": "failed", "error": str(e)}


@app.task(bind=True)
def parse_cv_task(self) -> dict[str, Any]:
    """Celery task to parse pending CVs every 5 minutes."""
    logger.info("Starting CV parse task")
    try:
        # Run the async function in a new event loop
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(_parse_cvs_async())
            logger.info(f"CV parsing completed: {result}")
            return result
        finally:
            loop.close()
    except Exception as e:
        logger.error(f"CV parse task wrapper failed: {e}", exc_info=True)
        return {"status": "failed", "error": str(e)}


async def _create_candidates_async() -> dict[str, Any]:
    """Async implementation of candidate creation from parsed CVs."""
    try:
        supabase_client = await get_supabase_client()
        worker = CandidateCreationWorker(supabase_client)
        result = await worker.create_candidates_from_parsed_cvs(limit=20)

        return {
            "status": "completed",
            "total_processed": result.get("total_processed", 0),
            "created": result.get("created", 0),
            "skipped_low_confidence": result.get("skipped_low_confidence", 0),
            "errors": result.get("errors", []),
        }

    except Exception as e:
        logger.error(f"Candidate creation task failed: {e}", exc_info=True)
        return {"status": "failed", "error": str(e)}


@app.task(bind=True)
def create_candidates_task(self) -> dict[str, Any]:
    """Celery task to create candidates from parsed CVs every 10 minutes."""
    logger.info("Starting candidate creation task")
    try:
        # Run the async function in a new event loop
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(_create_candidates_async())
            logger.info(f"Candidate creation completed: {result}")
            return result
        finally:
            loop.close()
    except Exception as e:
        logger.error(f"Candidate creation task wrapper failed: {e}", exc_info=True)
        return {"status": "failed", "error": str(e)}


async def _normalize_skills_async() -> dict[str, Any]:
    """Async implementation of skill normalization."""
    try:
        supabase_client = await get_supabase_client()

        # Get Claude client if API key is configured
        claude_client = None
        if settings.ANTHROPIC_API_KEY:
            claude_client = AnthropicClient(settings.ANTHROPIC_API_KEY)

        worker = SkillNormalizationWorker(supabase_client, claude_client)
        result = await worker.normalize_candidates_skills(limit=30)

        if claude_client:
            await claude_client.close()

        return {
            "status": "completed",
            "total_processed": result.get("total_processed", 0),
            "skills_normalized": result.get("skills_normalized", 0),
            "candidates_updated": result.get("candidates_updated", 0),
            "errors": result.get("errors", []),
        }

    except Exception as e:
        logger.error(f"Skill normalization task failed: {e}", exc_info=True)
        return {"status": "failed", "error": str(e)}


@app.task(bind=True)
def normalize_skills_task(self) -> dict[str, Any]:
    """Celery task to normalize candidate skills every 15 minutes."""
    logger.info("Starting skill normalization task")
    try:
        # Run the async function in a new event loop
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(_normalize_skills_async())
            logger.info(f"Skill normalization completed: {result}")
            return result
        finally:
            loop.close()
    except Exception as e:
        logger.error(f"Skill normalization task wrapper failed: {e}", exc_info=True)
        return {"status": "failed", "error": str(e)}


async def _score_candidates_async() -> dict[str, Any]:
    """Async implementation of candidate scoring."""
    try:
        supabase_client = await get_supabase_client()
        worker = CandidateScoringWorker(supabase_client)
        result = await worker.score_candidates_by_skills(limit=50)

        return {
            "status": "completed",
            "total_processed": result.get("total_processed", 0),
            "candidates_scored": result.get("candidates_scored", 0),
            "ready_candidates": result.get("ready_candidates", 0),
            "review_candidates": result.get("review_candidates", 0),
            "incomplete_candidates": result.get("incomplete_candidates", 0),
            "avg_score": result.get("avg_score", 0),
            "errors": result.get("errors", []),
        }

    except Exception as e:
        logger.error(f"Candidate scoring task failed: {e}", exc_info=True)
        return {"status": "failed", "error": str(e)}


@app.task(bind=True)
def score_candidates_task(self) -> dict[str, Any]:
    """Celery task to score candidates based on skills every hour."""
    logger.info("Starting candidate scoring task")
    try:
        # Run the async function in a new event loop
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(_score_candidates_async())
            logger.info(f"Candidate scoring completed: {result}")
            return result
        finally:
            loop.close()
    except Exception as e:
        logger.error(f"Candidate scoring task wrapper failed: {e}", exc_info=True)
        return {"status": "failed", "error": str(e)}


async def _match_job_candidates_async(job_id: str, agent_code: str) -> dict[str, Any]:
    """Async implementation of agent-based job matching."""
    try:
        if not settings.ANTHROPIC_API_KEY:
            logger.warning("ANTHROPIC_API_KEY not configured, skipping job matching")
            return {"status": "skipped", "reason": "ANTHROPIC_API_KEY not configured"}

        supabase_client = await get_supabase_client()
        claude_client = AnthropicClient(settings.ANTHROPIC_API_KEY)

        worker = AgentMatchingWorker(supabase_client, claude_client)
        result = await worker.find_matches_for_job(job_id, agent_code)

        await claude_client.close()

        return {
            "status": "completed",
            "total_candidates_evaluated": result.get("total_candidates_evaluated", 0),
            "matches_found": result.get("matches_found", 0),
            "tokens_used": result.get("tokens_used", 0),
            "duration_ms": result.get("duration_ms", 0),
            "errors": result.get("errors", []),
        }

    except Exception as e:
        logger.error(f"Job matching task failed: {e}", exc_info=True)
        return {"status": "failed", "error": str(e)}


@app.task(bind=True)
def match_job_candidates_task(self, job_id: str, agent_code: str) -> dict[str, Any]:
    """Celery task to match candidates to a job using agent."""
    logger.info(f"Starting job matching task for job {job_id} with agent {agent_code}")
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(_match_job_candidates_async(job_id, agent_code))
            logger.info(f"Job matching completed: {result}")
            return result
        finally:
            loop.close()
    except Exception as e:
        logger.error(f"Job matching task wrapper failed: {e}", exc_info=True)
        return {"status": "failed", "error": str(e)}


async def _match_candidate_jobs_async(candidate_id: str, agent_code: str) -> dict[str, Any]:
    """Async implementation of agent-based candidate matching."""
    try:
        if not settings.ANTHROPIC_API_KEY:
            logger.warning("ANTHROPIC_API_KEY not configured, skipping candidate matching")
            return {"status": "skipped", "reason": "ANTHROPIC_API_KEY not configured"}

        supabase_client = await get_supabase_client()
        claude_client = AnthropicClient(settings.ANTHROPIC_API_KEY)

        worker = AgentMatchingWorker(supabase_client, claude_client)
        result = await worker.find_matches_for_candidate(candidate_id, agent_code)

        await claude_client.close()

        return {
            "status": "completed",
            "total_jobs_evaluated": result.get("total_jobs_evaluated", 0),
            "matches_found": result.get("matches_found", 0),
            "tokens_used": result.get("tokens_used", 0),
            "duration_ms": result.get("duration_ms", 0),
            "errors": result.get("errors", []),
        }

    except Exception as e:
        logger.error(f"Candidate matching task failed: {e}", exc_info=True)
        return {"status": "failed", "error": str(e)}


@app.task(bind=True)
def match_candidate_jobs_task(self, candidate_id: str, agent_code: str) -> dict[str, Any]:
    """Celery task to match jobs to a candidate using agent."""
    logger.info(f"Starting candidate matching task for candidate {candidate_id} with agent {agent_code}")
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(_match_candidate_jobs_async(candidate_id, agent_code))
            logger.info(f"Candidate matching completed: {result}")
            return result
        finally:
            loop.close()
    except Exception as e:
        logger.error(f"Candidate matching task wrapper failed: {e}", exc_info=True)
        return {"status": "failed", "error": str(e)}


async def _check_new_jobs_for_assignment_async() -> dict[str, Any]:
    """Async implementation: Check for new unassigned jobs and assign to agents."""
    try:
        supabase_client = await get_supabase_client()

        # Find unassigned jobs (assigned_agent_code is NULL) - ORDER BY PRIORITY
        response = await supabase_client.table("jobs").select(
            "id, title, description, qualifications, required_domain, is_active, priority"
        ).eq("is_active", True).is_("assigned_agent_code", None).order("priority", desc=True).limit(20).execute()

        unassigned_jobs = response.data or []
        if not unassigned_jobs:
            logger.info("No unassigned jobs found")
            return {
                "status": "completed",
                "jobs_processed": 0,
                "jobs_assigned": 0,
                "errors": [],
            }

        logger.info(f"Found {len(unassigned_jobs)} unassigned jobs")

        # For each unassigned job, determine the best agent
        claude_client = AnthropicClient(settings.ANTHROPIC_API_KEY)
        jobs_assigned = 0
        errors = []

        for job in unassigned_jobs:
            try:
                # Simple domain-based routing for now (enhanced later with Claude)
                agent_code = _determine_agent_for_job(job)

                # Update job with assigned agent
                await supabase_client.table("jobs").update({
                    "assigned_agent_code": agent_code,
                    "carmit_routing_reasoning": f"Auto-assigned based on job domain: {job.get('required_domain', 'general')}"
                }).eq("id", job["id"]).execute()

                job_priority = job.get("priority", 5)
                logger.info(
                    f"Job {job['title']} - Priority {job_priority} - assigned to agent {agent_code}"
                )
                jobs_assigned += 1

                # Update agent runtime state to indicate it's now processing this job
                try:
                    await supabase_client.table("agent_runtime_state").update({
                        "status": "processing",
                        "current_task_description": f"Matching candidates for job: {job['title']}",
                        "current_job_id": job["id"],
                        "last_active_at": datetime.utcnow().isoformat(),
                    }).eq("agent_code", agent_code).execute()
                except Exception as e:
                    logger.warning(f"Failed to update agent runtime state for {agent_code}: {e}")

                # Trigger matching task for this job
                from pandapower.workers.tasks import match_job_candidates_task
                match_job_candidates_task.delay(job["id"], agent_code)

            except Exception as e:
                logger.error(f"Failed to assign job {job['id']}: {e}")
                errors.append({"job_id": job["id"], "error": str(e)})

        await claude_client.close()

        return {
            "status": "completed",
            "jobs_processed": len(unassigned_jobs),
            "jobs_assigned": jobs_assigned,
            "errors": errors,
        }

    except Exception as e:
        logger.error(f"Job assignment batch failed: {e}", exc_info=True)
        return {"status": "failed", "error": str(e)}


@app.task(bind=True)
def check_new_jobs_for_assignment_task(self) -> dict[str, Any]:
    """Celery task: Check for unassigned jobs and route to agents every 10 minutes."""
    logger.info("Starting automatic job assignment task")
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(_check_new_jobs_for_assignment_async())
            logger.info(f"Job assignment completed: {result}")
            return result
        finally:
            loop.close()
    except Exception as e:
        logger.error(f"Job assignment task wrapper failed: {e}", exc_info=True)
        return {"status": "failed", "error": str(e)}


async def _check_new_candidates_for_assignment_async() -> dict[str, Any]:
    """Async implementation: Check for new candidates and match them to jobs."""
    try:
        supabase_client = await get_supabase_client()

        # Find recently created candidates without matches
        response = await supabase_client.table("candidates").select(
            "id, name, key_skills, detected_language, location"
        ).eq("deleted_at", None).limit(10).execute()

        candidates = response.data or []
        if not candidates:
            logger.info("No candidates to match")
            return {
                "status": "completed",
                "candidates_processed": 0,
                "matching_tasks_triggered": 0,
                "errors": [],
            }

        logger.info(f"Found {len(candidates)} candidates to match against jobs")

        matching_tasks_triggered = 0
        errors = []

        for candidate in candidates:
            try:
                # Determine appropriate agent for this candidate's skills
                agent_code = _determine_agent_for_candidate(candidate)

                # Trigger matching task
                from pandapower.workers.tasks import match_candidate_jobs_task
                match_candidate_jobs_task.delay(candidate["id"], agent_code)

                logger.info(f"Matching task triggered for {candidate['name']} with agent {agent_code}")
                matching_tasks_triggered += 1

            except Exception as e:
                logger.error(f"Failed to trigger matching for candidate {candidate['id']}: {e}")
                errors.append({"candidate_id": candidate["id"], "error": str(e)})

        return {
            "status": "completed",
            "candidates_processed": len(candidates),
            "matching_tasks_triggered": matching_tasks_triggered,
            "errors": errors,
        }

    except Exception as e:
        logger.error(f"Candidate assignment batch failed: {e}", exc_info=True)
        return {"status": "failed", "error": str(e)}


@app.task(bind=True)
def check_new_candidates_for_assignment_task(self) -> dict[str, Any]:
    """Celery task: Check for new candidates and trigger matching every 15 minutes."""
    logger.info("Starting automatic candidate assignment task")
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(_check_new_candidates_for_assignment_async())
            logger.info(f"Candidate assignment completed: {result}")
            return result
        finally:
            loop.close()
    except Exception as e:
        logger.error(f"Candidate assignment task wrapper failed: {e}", exc_info=True)
        return {"status": "failed", "error": str(e)}


def _determine_agent_for_job(job: dict) -> str:
    """Simple heuristic to determine which agent should handle a job.

    Based on job domain/title. Enhanced in later phase with Claude routing.
    """
    required_domain = job.get("required_domain", "").lower()
    title = job.get("title", "").lower()
    description = job.get("description", "").lower()

    # Simple keyword matching for agent routing
    if any(word in required_domain or word in title for word in ["fpga", "verilog", "vhdl", "pcb", "rf", "analog", "electronics", "hardware"]):
        return "alik"
    elif any(word in required_domain or word in title for word in ["python", "java", "c++", "cloud", "microservice", "backend", "software"]):
        return "naama"
    elif any(word in required_domain or word in title for word in ["qa", "test", "selenium", "loadrunner", "automation"]):
        return "dganit"
    elif any(word in required_domain or word in title for word in ["devops", "linux", "networking", "container", "docker", "kubernetes"]):
        return "ofir"
    elif any(word in required_domain or word in title for word in ["infrastructure", "windows", "helpdesk", "network", "it"]):
        return "itai"
    elif any(word in required_domain or word in title for word in ["cad", "solidworks", "fea", "mechanical", "manufacturing"]):
        return "lior"
    else:
        return "gc"  # Default to general catch-all


def _determine_agent_for_candidate(candidate: dict) -> str:
    """Simple heuristic to determine which agent should handle candidate matching.

    Based on candidate skills. Enhanced in later phase with Claude analysis.
    """
    skills = candidate.get("key_skills", []) or []
    skills_text = " ".join(skills).lower()

    # Simple keyword matching
    if any(word in skills_text for word in ["fpga", "verilog", "vhdl", "pcb", "rf", "analog"]):
        return "alik"
    elif any(word in skills_text for word in ["python", "java", "c++", "aws", "azure", "cloud"]):
        return "naama"
    elif any(word in skills_text for word in ["selenium", "qa", "test", "loadrunner"]):
        return "dganit"
    elif any(word in skills_text for word in ["linux", "devops", "docker", "kubernetes", "networking"]):
        return "ofir"
    elif any(word in skills_text for word in ["windows", "ad", "exchange", "infrastructure"]):
        return "itai"
    elif any(word in skills_text for word in ["cad", "solidworks", "autocad", "mechanical"]):
        return "lior"
    else:
        return "gc"  # Default to general


# ==================== Phase 5: Carmit Orchestrator ====================

async def _carmit_route_jobs_async() -> dict[str, Any]:
    """Async implementation of job routing via Carmit orchestrator."""
    try:
        supabase_client = await get_supabase_client()

        # Check if Pipedrive is configured
        if not settings.PIPEDRIVE_API_TOKEN:
            logger.warning("Pipedrive not configured, skipping job routing")
            return {"status": "skipped", "reason": "Pipedrive not configured"}

        # Initialize clients
        claude_client = AnthropicClient(settings.ANTHROPIC_API_KEY)
        pipedrive_client = PipedriveClient(
            settings.PIPEDRIVE_API_TOKEN,
            settings.PIPEDRIVE_API_DOMAIN,
        )

        # Create orchestrator
        orchestrator = CarmitOrchestrator(
            supabase_client=supabase_client,
            anthropic_client=claude_client,
            pipedrive_client=pipedrive_client,
            settings={
                "CARMIT_MATCH_SCORE_THRESHOLD": settings.CARMIT_MATCH_SCORE_THRESHOLD,
                "CARMIT_CLEARANCE_LEVELS": settings.CARMIT_CLEARANCE_LEVELS,
            },
        )

        # Get unassigned jobs - ORDER BY PRIORITY (highest priority first)
        # Priority 1 = highest, Priority 5 = lowest
        jobs_response = await supabase_client.table("jobs").select("*").eq(
            "status", "open"
        ).is_("assigned_agent_code", None).order("priority", desc=True).limit(10).execute()

        jobs = jobs_response.data or []
        if not jobs:
            logger.info("No unassigned jobs found")
            return {"status": "success", "jobs_routed": 0}

        # Route each job (in priority order)
        routed_count = 0
        for job in jobs:
            try:
                result = await orchestrator.route_job_to_agent(job["id"])
                routed_count += 1
                job_priority = job.get("priority", 5)
                job_title = job.get("job_title", "Unknown")
                logger.info(
                    f"Routed job {job['id']} ({job_title}) - Priority {job_priority} - "
                    f"to agent {result['assigned_agent_code']} (confidence: {result['confidence']:.2f})"
                )
            except Exception as e:
                logger.error(f"Failed to route job {job['id']}: {str(e)}")
                continue

        # Cleanup (handle event loop issues in Celery context)
        try:
            await claude_client.close()
        except (RuntimeError, Exception) as e:
            logger.debug(f"Error closing Claude client: {e}")

        try:
            await pipedrive_client.close()
        except (RuntimeError, Exception) as e:
            logger.debug(f"Error closing Pipedrive client: {e}")

        return {"status": "success", "jobs_routed": routed_count}

    except Exception as e:
        logger.error(f"Job routing async failed: {str(e)}", exc_info=True)
        return {"status": "failed", "error": str(e)}


async def _carmit_review_matches_async() -> dict[str, Any]:
    """Async implementation of match review via Carmit orchestrator."""
    try:
        supabase_client = await get_supabase_client()

        # Check if Pipedrive is configured
        if not settings.PIPEDRIVE_API_TOKEN:
            logger.warning("Pipedrive not configured, skipping match review")
            return {"status": "skipped", "reason": "Pipedrive not configured"}

        # Initialize clients
        claude_client = AnthropicClient(settings.ANTHROPIC_API_KEY)
        pipedrive_client = PipedriveClient(
            settings.PIPEDRIVE_API_TOKEN,
            settings.PIPEDRIVE_API_DOMAIN,
        )

        # Create orchestrator
        orchestrator = CarmitOrchestrator(
            supabase_client=supabase_client,
            anthropic_client=claude_client,
            pipedrive_client=pipedrive_client,
            settings={
                "CARMIT_MATCH_SCORE_THRESHOLD": settings.CARMIT_MATCH_SCORE_THRESHOLD,
                "CARMIT_CLEARANCE_LEVELS": settings.CARMIT_CLEARANCE_LEVELS,
            },
        )

        # Get matches awaiting review
        matches_response = await supabase_client.table("matches").select("*").eq(
            "current_state", "found"
        ).limit(20).execute()

        matches = matches_response.data or []
        if not matches:
            logger.info("No matches awaiting review")
            return {"status": "success", "matches_reviewed": 0}

        # Review each match
        reviewed_count = 0
        approved_count = 0
        rejected_count = 0

        for match in matches:
            try:
                result = await orchestrator.review_match(match["id"])
                reviewed_count += 1

                if result["decision"] == "approved":
                    approved_count += 1
                    logger.info(f"Match {match['id']} approved")
                else:
                    rejected_count += 1
                    logger.info(f"Match {match['id']} rejected: {result['reasoning']}")

            except Exception as e:
                logger.error(f"Failed to review match {match['id']}: {str(e)}")
                continue

        # Cleanup
        await claude_client.close()
        await pipedrive_client.close()

        return {
            "status": "success",
            "matches_reviewed": reviewed_count,
            "approved": approved_count,
            "rejected": rejected_count,
        }

    except Exception as e:
        logger.error(f"Match review async failed: {str(e)}", exc_info=True)
        return {"status": "failed", "error": str(e)}


@app.task(bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_backoff_max=600, retry_jitter=True, max_retries=3)
def carmit_route_jobs_task(self) -> dict[str, Any]:
    """Celery task: Route jobs to agents every 10 minutes.

    Auto-retries up to 3 times with exponential backoff (max 10 min between
    retries) on any exception — keeps the pipeline self-healing across
    transient Supabase / Anthropic / Pipedrive blips.
    """
    logger.info("Starting Carmit job routing task")
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(_carmit_route_jobs_async())
            logger.info(f"Carmit job routing completed: {result}")
            return result
        finally:
            loop.close()
    except Exception as e:
        logger.error(f"Carmit job routing task wrapper failed: {e}", exc_info=True)
        return {"status": "failed", "error": str(e)}


@app.task(bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_backoff_max=600, retry_jitter=True, max_retries=3)
def carmit_review_matches_task(self) -> dict[str, Any]:
    """Celery task: Review matches via quality gates every 15 minutes.

    Auto-retries with exponential backoff on transient failures.
    """
    logger.info("Starting Carmit match review task")
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(_carmit_review_matches_async())
            logger.info(f"Carmit match review completed: {result}")
            return result
        finally:
            loop.close()
    except Exception as e:
        logger.error(f"Carmit match review task wrapper failed: {e}", exc_info=True)
        return {"status": "failed", "error": str(e)}


# ============================================================================
# Carmit → Tal handoff
# ----------------------------------------------------------------------------
# This is the missing link in the pipeline. carmit_review_matches_task flips
# matches from "found" → "carmit_approved"; nothing then moves them on to
# "sent_to_tal" so Tal's queue was always empty. The legacy RecruiterWorkflow-
# Manager.send_match_to_recruiter() exists but is wired only to a manual API
# call (and uses sync supabase calls that don't work with our async client).
#
# This task does the minimum needed: bulk-flip carmit_approved matches to
# sent_to_tal and write an audit row, using the same defensive history-write
# helper used by Carmit's review. Pipedrive activity creation is intentionally
# deferred — it's nice-to-have but not blocking, and the previous code's
# sync .execute() calls were broken anyway.
# ============================================================================

async def _carmit_handoff_to_tal_async(batch_size: int = 20) -> dict[str, Any]:
    """Move carmit_approved matches → sent_to_tal so Tal's queue fills up.

    Returns {status, handed_off, errors}. Picks the oldest carmit_approved
    matches first so nothing starves.
    """
    try:
        supabase_client = await get_supabase_client()

        # Find approved matches that haven't been handed off yet.
        resp = await (
            supabase_client.table("matches")
            .select("id, candidate_id, job_id, matched_by_agent_code, match_score")
            .eq("current_state", "carmit_approved")
            .eq("is_valid", True)
            .order("updated_at", desc=False)  # oldest first
            .limit(batch_size)
            .execute()
        )
        matches = resp.data or []
        if not matches:
            return {"status": "success", "handed_off": 0}

        # Reuse Carmit's defensive history writer so the audit row schema
        # matches what _carmit_review_matches_async already produces.
        from pandapower.workers.carmit import CarmitOrchestrator
        orchestrator = CarmitOrchestrator(
            supabase_client=supabase_client,
            anthropic_client=None,   # not used by handoff path
            pipedrive_client=None,   # ditto
            settings={
                "CARMIT_MATCH_SCORE_THRESHOLD": settings.CARMIT_MATCH_SCORE_THRESHOLD,
                "CARMIT_CLEARANCE_LEVELS": settings.CARMIT_CLEARANCE_LEVELS,
            },
        )

        handed_off = 0
        errors: list[str] = []
        now = datetime.utcnow().isoformat()
        for m in matches:
            mid = str(m["id"])
            try:
                # 1) Flip state.
                await supabase_client.table("matches").update({
                    "current_state": "sent_to_tal",
                    "updated_at": now,
                }).eq("id", mid).execute()

                # 2) Best-effort audit row via Carmit's defensive helper.
                await orchestrator._store_match_review(
                    match_id=mid,
                    from_state="carmit_approved",
                    to_state="sent_to_tal",
                    gate_results={},  # no new gates run at handoff
                    reasoning="Auto-handoff: Carmit-approved match forwarded to Tal",
                )

                # 3) Lightweight agent log so the activity timeline shows it.
                try:
                    await supabase_client.table("agent_logs").insert({
                        "agent_code": "carmit_orchestrator",
                        "action": "handoff_to_tal",
                        "related_match_id": mid,
                        "related_candidate_id": m.get("candidate_id"),
                        "related_job_id": m.get("job_id"),
                        "output_payload": {
                            "from_state": "carmit_approved",
                            "to_state": "sent_to_tal",
                            "match_score": float(m.get("match_score") or 0.0),
                        },
                        "created_at": now,
                    }).execute()
                except Exception as log_err:
                    # Don't let logging block the handoff.
                    logger.debug(f"agent_logs insert failed for handoff {mid}: {str(log_err)[:120]}")

                handed_off += 1
            except Exception as e:
                errors.append(f"{mid}: {str(e)[:200]}")
                logger.warning(f"Handoff failed for match {mid}: {e}")

        logger.info(f"Carmit→Tal handoff: handed_off={handed_off} errors={len(errors)}")
        return {"status": "success", "handed_off": handed_off, "errors": errors}

    except Exception as e:
        logger.error(f"Carmit→Tal handoff async failed: {str(e)}", exc_info=True)
        return {"status": "failed", "error": str(e)}


@app.task(bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_backoff_max=600, retry_jitter=True, max_retries=3)
def carmit_handoff_to_tal_task(self) -> dict[str, Any]:
    """Celery task: Hand off Carmit-approved matches to Tal's queue.

    Scheduled to run every 10 minutes (see celery_app.py beat schedule),
    intentionally faster than the 15-minute review cadence so newly-approved
    matches reach Tal within roughly one review cycle.
    """
    logger.info("Starting Carmit → Tal handoff task")
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(_carmit_handoff_to_tal_async())
            logger.info(f"Carmit → Tal handoff completed: {result}")
            return result
        finally:
            loop.close()
    except Exception as e:
        logger.error(f"Carmit → Tal handoff task wrapper failed: {e}", exc_info=True)
        return {"status": "failed", "error": str(e)}


# ============================================================================
# Pipeline watchdog
# ----------------------------------------------------------------------------
# Detects matches that have been stuck in a transient state for "too long"
# and re-kicks the appropriate task so the pipeline self-heals after worker
# restarts, transient crashes, or any other gap in scheduling. Runs every
# 30 minutes (see celery_app.py beat schedule).
#
# What "stuck" means:
#   • found            — Carmit's review should have processed it within
#                        ~15 min of creation; if it's still "found" after
#                        2 h, re-run review.
#   • carmit_approved  — handoff fires every 10 min; if still approved
#                        after 1 h, re-run handoff.
#
# We don't touch "sent_to_tal" / "tal_*" / "elad_*" / "hired" — those are
# manual-recruiter states, not stale-by-time-alone.
# ============================================================================

async def _pipeline_watchdog_async() -> dict[str, Any]:
    """Detect and re-kick stuck matches. Best-effort; never raises."""
    from datetime import timedelta, timezone

    try:
        supabase_client = await get_supabase_client()
        now = datetime.now(timezone.utc)

        # Threshold for "found" stragglers — 2 h since last update.
        found_cutoff = (now - timedelta(hours=2)).isoformat()
        approved_cutoff = (now - timedelta(hours=1)).isoformat()

        # Count stragglers in each state.
        stuck_found_resp = await (
            supabase_client.table("matches")
            .select("id", count="exact")
            .eq("current_state", "found")
            .eq("is_valid", True)
            .lte("updated_at", found_cutoff)
            .execute()
        )
        stuck_approved_resp = await (
            supabase_client.table("matches")
            .select("id", count="exact")
            .eq("current_state", "carmit_approved")
            .eq("is_valid", True)
            .lte("updated_at", approved_cutoff)
            .execute()
        )

        stuck_found = getattr(stuck_found_resp, "count", None) or 0
        stuck_approved = getattr(stuck_approved_resp, "count", None) or 0

        actions: list[str] = []
        # If anything's stuck, re-trigger the appropriate task. We use the
        # async helpers directly (not .delay()) so the watchdog itself does
        # the catch-up work in one shot — no second hop through the queue.
        if stuck_found > 0:
            logger.warning(f"Watchdog: {stuck_found} matches stuck in 'found' > 2h — re-running review")
            await _carmit_review_matches_async()
            actions.append(f"re-ran review ({stuck_found} stuck)")
        if stuck_approved > 0:
            logger.warning(f"Watchdog: {stuck_approved} matches stuck in 'carmit_approved' > 1h — re-running handoff")
            await _carmit_handoff_to_tal_async()
            actions.append(f"re-ran handoff ({stuck_approved} stuck)")

        if not actions:
            logger.info("Watchdog: pipeline healthy, no stuck matches")

        return {
            "status": "ok",
            "stuck_found": stuck_found,
            "stuck_carmit_approved": stuck_approved,
            "actions": actions,
            "checked_at": now.isoformat(),
        }

    except Exception as e:
        # Watchdog must never crash the worker — log and move on.
        logger.error(f"Pipeline watchdog failed: {e}", exc_info=True)
        return {"status": "failed", "error": str(e)[:300]}


@app.task(bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_backoff_max=600, max_retries=3)
def pipeline_watchdog_task(self) -> dict[str, Any]:
    """Celery task: self-heal stuck matches every 30 min."""
    logger.info("Starting pipeline watchdog")
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(_pipeline_watchdog_async())
            logger.info(f"Pipeline watchdog completed: {result}")
            return result
        finally:
            loop.close()
    except Exception as e:
        logger.error(f"Pipeline watchdog wrapper failed: {e}", exc_info=True)
        return {"status": "failed", "error": str(e)}


# ============================================================================
# Phase 6: Pipedrive Live Integration Tasks
# ============================================================================


async def _pipedrive_field_sync_async() -> dict[str, Any]:
    """Async: Validate and sync Pipedrive custom field mappings."""
    try:
        from pandapower.workers.pipedrive_field_sync import PipedriveFieldMapper

        if not settings.PIPEDRIVE_API_TOKEN:
            return {"status": "skipped", "reason": "PIPEDRIVE_API_TOKEN not configured"}

        supabase_client = await get_supabase_client()
        pipedrive_client = PipedriveClient(
            settings.PIPEDRIVE_API_TOKEN,
            settings.PIPEDRIVE_API_DOMAIN,
        )

        mapper = PipedriveFieldMapper(pipedrive_client, supabase_client)

        # Validate all fields
        validation_results = await mapper.validate_all_fields()

        if not validation_results["all_valid"]:
            logger.warning(f"Field validation issues: {validation_results['errors']}")

        # Sync field mappings
        sync_results = await mapper.sync_field_mappings()

        return {
            "status": "success",
            "validation": validation_results,
            "sync": sync_results,
        }

    except Exception as e:
        logger.error(f"Pipedrive field sync async failed: {str(e)}", exc_info=True)
        return {"status": "failed", "error": str(e)}


async def _pipedrive_historical_import_async() -> dict[str, Any]:
    """Async: Import historical rejection data from Pipedrive."""
    try:
        from pandapower.workers.pipedrive_historical_import import (
            PipedriveHistoricalImporter,
        )

        if not settings.PIPEDRIVE_API_TOKEN:
            return {"status": "skipped", "reason": "PIPEDRIVE_API_TOKEN not configured"}

        supabase_client = await get_supabase_client()
        pipedrive_client = PipedriveClient(
            settings.PIPEDRIVE_API_TOKEN,
            settings.PIPEDRIVE_API_DOMAIN,
        )

        importer = PipedriveHistoricalImporter(pipedrive_client, supabase_client)
        results = await importer.import_all_deal_rejections(limit=1000)

        logger.info(f"Historical rejection import completed: {results}")
        return {"status": "success", **results}

    except Exception as e:
        logger.error(f"Pipedrive historical import async failed: {str(e)}", exc_info=True)
        return {"status": "failed", "error": str(e)}


async def _bidirectional_sync_async() -> dict[str, Any]:
    """Async: Sync data bidirectionally between Pipedrive and PandaPower."""
    try:
        from pandapower.workers.pipedrive_bidirectional_sync import BidirectionalSyncManager

        if not settings.PIPEDRIVE_API_TOKEN:
            return {"status": "skipped", "reason": "PIPEDRIVE_API_TOKEN not configured"}

        supabase_client = await get_supabase_client()
        pipedrive_client = PipedriveClient(
            settings.PIPEDRIVE_API_TOKEN,
            settings.PIPEDRIVE_API_DOMAIN,
        )

        sync_manager = BidirectionalSyncManager(pipedrive_client, supabase_client)

        # Sync from Pipedrive to PandaPower
        pd_to_pp = await sync_manager.sync_pipedrive_to_pandapower(minutes_back=30)

        # Sync from PandaPower to Pipedrive
        pp_to_pd = await sync_manager.sync_pandapower_to_pipedrive()

        return {
            "status": "success",
            "pipedrive_to_pandapower": pd_to_pp,
            "pandapower_to_pipedrive": pp_to_pd,
        }

    except Exception as e:
        logger.error(f"Bidirectional sync async failed: {str(e)}", exc_info=True)
        return {"status": "failed", "error": str(e)}


@app.task(bind=True)
def pipedrive_field_sync_task(self) -> dict[str, Any]:
    """Celery task: Sync Pipedrive field mappings every 60 minutes."""
    logger.info("Starting Pipedrive field sync task")
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(_pipedrive_field_sync_async())
            logger.info(f"Pipedrive field sync completed: {result}")
            return result
        finally:
            loop.close()
    except Exception as e:
        logger.error(f"Pipedrive field sync task wrapper failed: {e}", exc_info=True)
        return {"status": "failed", "error": str(e)}


@app.task(bind=True)
def pipedrive_historical_import_task(self) -> dict[str, Any]:
    """Celery task: Import historical rejection data every 4 hours."""
    logger.info("Starting Pipedrive historical import task")
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(_pipedrive_historical_import_async())
            logger.info(f"Pipedrive historical import completed: {result}")
            return result
        finally:
            loop.close()
    except Exception as e:
        logger.error(f"Pipedrive historical import task wrapper failed: {e}", exc_info=True)
        return {"status": "failed", "error": str(e)}


@app.task(bind=True)
def bidirectional_sync_task(self) -> dict[str, Any]:
    """Celery task: Bidirectional sync with Pipedrive every 30 minutes."""
    logger.info("Starting bidirectional sync task")
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(_bidirectional_sync_async())
            logger.info(f"Bidirectional sync completed: {result}")
            return result
        finally:
            loop.close()
    except Exception as e:
        logger.error(f"Bidirectional sync task wrapper failed: {e}", exc_info=True)
        return {"status": "failed", "error": str(e)}


async def _pipedrive_sync_scheduler_async() -> dict[str, Any]:
    """
    Async: tick of the user-driven Pipedrive sync scheduler.
    Reads pipedrive_sync_schedule table; runs any entity sync that is due NOW
    based on user-defined intervals, days, and time windows.
    """
    try:
        if not settings.PIPEDRIVE_API_TOKEN:
            return {"status": "skipped", "reason": "PIPEDRIVE_API_TOKEN not configured"}

        from pandapower.workers.pipedrive_sync_scheduler import run_due_syncs
        result = await run_due_syncs()
        return result

    except Exception as e:
        logger.error(f"Pipedrive sync scheduler async failed: {str(e)}", exc_info=True)
        return {"status": "failed", "error": str(e)}


@app.task(bind=True)
def pipedrive_sync_scheduler_task(self) -> dict[str, Any]:
    """
    Celery task: tick the Pipedrive sync scheduler every minute.

    The task itself is fast and idempotent - it consults
    pipedrive_sync_schedule and only fires the actual sync workers
    when a schedule is due based on user-configured settings.
    """
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(_pipedrive_sync_scheduler_async())
            if result.get("status") == "ran":
                logger.info(f"Pipedrive sync scheduler tick: {result}")
            return result
        finally:
            loop.close()
    except Exception as e:
        logger.error(f"Pipedrive sync scheduler task failed: {e}", exc_info=True)
        return {"status": "failed", "error": str(e)}


# ===========================================================================
# Telegram notifications (Carmit bot) — match→Tal / hire events + daily summary
# ===========================================================================

async def _set_setting(sb, key: str, value: str) -> None:
    """Upsert one system_settings row (best-effort)."""
    try:
        await sb.table("system_settings").upsert(
            {"setting_key": key, "setting_value": value, "updated_at": datetime.utcnow().isoformat()},
            on_conflict="setting_key",
        ).execute()
    except Exception as e:
        logger.debug(f"_set_setting failed for {key}: {e}")


async def _get_setting(sb, key: str) -> Any:
    try:
        r = await sb.table("system_settings").select("setting_value").eq(
            "setting_key", key
        ).limit(1).execute()
        if r.data and r.data[0].get("setting_value") is not None:
            val = r.data[0]["setting_value"]
            if isinstance(val, str):
                val = val.strip().strip('"').strip()
            return val or None
    except Exception as e:
        logger.debug(f"_get_setting failed for {key}: {e}")
    return None


async def _notify_telegram_async() -> dict[str, Any]:
    """Notify the admin (Telegram) about matches that newly entered 'sent_to_tal'
    or 'hired', using an updated_at watermark so each transition fires once.

    Skips quietly if the Telegram bot isn't configured. On first run after
    configuration it sets the watermark to 'now' (no backlog blast)."""
    try:
        from pandapower.integrations.telegram_client import get_telegram_config, notify_admin_telegram

        supabase_client = await get_supabase_client()
        cfg = await get_telegram_config(supabase_client)
        if not cfg.get("bot_token") or not cfg.get("admin_chat_id"):
            return {"status": "skipped", "reason": "telegram not configured"}

        WATERMARK_KEY = "telegram.notify_watermark"
        watermark = await _get_setting(supabase_client, WATERMARK_KEY)
        now_iso = datetime.utcnow().isoformat()

        # First-time baseline: don't blast historical matches.
        if not watermark:
            await _set_setting(supabase_client, WATERMARK_KEY, now_iso)
            return {"status": "completed", "notified": 0, "note": "watermark initialized"}

        resp = await (
            supabase_client.table("matches")
            .select("id, candidate_id, job_id, match_score, current_state, updated_at")
            .in_("current_state", ["sent_to_tal", "hired"])
            .gt("updated_at", watermark)
            .order("updated_at", desc=False)
            .limit(50)
            .execute()
        )
        rows = resp.data or []

        notified = 0
        max_ts = watermark
        for m in rows:
            ts = m.get("updated_at")
            if ts and ts > max_ts:
                max_ts = ts

            # Resolve human-readable names (best-effort).
            cand_name = str(m.get("candidate_id") or "")
            job_name = str(m.get("job_id") or "")
            try:
                if m.get("candidate_id"):
                    c = await supabase_client.table("candidates").select("name").eq(
                        "id", m["candidate_id"]
                    ).limit(1).execute()
                    if c.data and c.data[0].get("name"):
                        cand_name = c.data[0]["name"]
            except Exception:
                pass
            try:
                if m.get("job_id"):
                    j = await supabase_client.table("jobs").select("job_title, title").eq(
                        "id", m["job_id"]
                    ).limit(1).execute()
                    if j.data:
                        job_name = j.data[0].get("job_title") or j.data[0].get("title") or job_name
            except Exception:
                pass

            state = m.get("current_state")
            if state == "sent_to_tal":
                score = m.get("match_score")
                score_txt = f" (ציון {round(float(score))})" if score is not None else ""
                text = (
                    f"🔔 <b>התאמה חדשה עברה לטל</b>\n"
                    f"👤 {cand_name}\n"
                    f"💼 {job_name}{score_txt}"
                )
            else:  # hired
                text = (
                    f"🎉 <b>גיוס הושלם!</b>\n"
                    f"👤 {cand_name}\n"
                    f"💼 {job_name}"
                )

            if await notify_admin_telegram(text, sb=supabase_client):
                notified += 1

        if max_ts != watermark:
            await _set_setting(supabase_client, WATERMARK_KEY, max_ts)

        return {"status": "completed", "notified": notified, "scanned": len(rows)}

    except Exception as e:
        logger.error(f"Telegram notify task failed: {e}", exc_info=True)
        return {"status": "failed", "error": str(e)}


async def _telegram_daily_summary_async() -> dict[str, Any]:
    """Send a once-per-day Hebrew digest to the admin's Telegram chat.

    Guarded by telegram.last_summary_date + a target UTC hour (06:00 ≈ 09:00
    Israel). Skips quietly if not configured / already sent today / too early."""
    try:
        from pandapower.integrations.telegram_client import get_telegram_config, notify_admin_telegram

        supabase_client = await get_supabase_client()
        cfg = await get_telegram_config(supabase_client)
        if not cfg.get("bot_token") or not cfg.get("admin_chat_id"):
            return {"status": "skipped", "reason": "telegram not configured"}

        now = datetime.utcnow()
        today = now.date().isoformat()
        last = await _get_setting(supabase_client, "telegram.last_summary_date")
        if last == today:
            return {"status": "skipped", "reason": "already sent today"}
        if now.hour < 6:  # ~09:00 Israel; wait until then
            return {"status": "skipped", "reason": "before summary hour"}

        today_start = datetime(now.year, now.month, now.day).isoformat()

        async def _count(table: str, **filters) -> int:
            try:
                q = supabase_client.table(table).select("id", count="exact")
                for k, v in filters.items():
                    if k.endswith("__gte"):
                        q = q.gte(k[:-5], v)
                    else:
                        q = q.eq(k, v)
                r = await q.execute()
                return r.count if getattr(r, "count", None) else 0
            except Exception:
                return 0

        emails_today = await _count("email_intake_log", status="success", processing_completed_at__gte=today_start)
        found_today = await _count("matches", current_state="found", created_at__gte=today_start)
        tal_today = await _count("agent_logs", action="handoff_to_tal", created_at__gte=today_start)
        hired_today = await _count("matches", current_state="hired", updated_at__gte=today_start)

        # Stalled processes from heartbeats.
        stalled: list[str] = []
        try:
            hb = await supabase_client.table("scheduler_heartbeats").select(
                "task_name, last_run_at, expected_interval_seconds"
            ).execute()
            for row in (hb.data or []):
                lr = row.get("last_run_at")
                interval = row.get("expected_interval_seconds") or 0
                if lr and interval:
                    try:
                        last_dt = datetime.fromisoformat(lr.replace("Z", "+00:00")).replace(tzinfo=None)
                        if (now - last_dt).total_seconds() > 2 * interval:
                            stalled.append(row.get("task_name"))
                    except Exception:
                        pass
        except Exception:
            pass

        health_line = "✅ כל התהליכים תקינים" if not stalled else f"⚠️ תקועים: {', '.join(stalled)}"
        text = (
            f"📊 <b>סיכום יומי — {today}</b>\n\n"
            f"📧 מיילים שנסרקו היום: {emails_today}\n"
            f"🆕 התאמות חדשות: {found_today}\n"
            f"🔔 עברו לטל: {tal_today}\n"
            f"🎉 גיוסים שהושלמו: {hired_today}\n\n"
            f"{health_line}"
        )

        sent = await notify_admin_telegram(text, sb=supabase_client)
        if sent:
            await _set_setting(supabase_client, "telegram.last_summary_date", today)
            return {"status": "completed", "sent": True}
        return {"status": "skipped", "reason": "send failed"}

    except Exception as e:
        logger.error(f"Telegram daily summary failed: {e}", exc_info=True)
        return {"status": "failed", "error": str(e)}

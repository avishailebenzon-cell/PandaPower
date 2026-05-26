"""Phase 6-7: Pipedrive Live Integration Admin Endpoints."""

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from pandapower.core.config import settings, get_settings
from pandapower.core.supabase import get_supabase_client
from pandapower.integrations.claude_api import AnthropicClient
from pandapower.integrations.pipedrive import PipedriveClient
from pandapower.workers.pipedrive_setup import (
    validate_pipedrive_setup,
    print_setup_checklist,
)
from pandapower.workers.pipedrive_field_sync import PipedriveFieldMapper
from pandapower.workers.pipedrive_historical_import import PipedriveHistoricalImporter
from pandapower.workers.pipedrive_recruiter_workflow import RecruiterWorkflowManager
from pandapower.workers.pipedrive_bidirectional_sync import BidirectionalSyncManager

router = APIRouter(prefix="/admin/pipedrive", tags=["pipedrive"])
logger = logging.getLogger(__name__)


async def get_pipedrive_client() -> PipedriveClient:
    """Get Pipedrive client with configured token."""
    if not settings.PIPEDRIVE_API_TOKEN:
        raise HTTPException(
            status_code=400,
            detail="PIPEDRIVE_API_TOKEN not configured in .env"
        )
    return PipedriveClient(settings.PIPEDRIVE_API_TOKEN, settings.PIPEDRIVE_API_DOMAIN)


@router.get("/setup/status")
async def check_pipedrive_setup() -> dict[str, Any]:
    """Check Pipedrive configuration status.
    
    Returns validation status and setup checklist.
    """
    try:
        status = await validate_pipedrive_setup()
        checklist = print_setup_checklist(status)
        
        return {
            "status": "success",
            "setup_status": status.to_dict(),
            "checklist": checklist,
            "ready_for_production": status.is_ready_for_production(),
        }
    except Exception as e:
        logger.error(f"Error checking Pipedrive setup: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/fields/validate")
async def validate_pipedrive_fields(
    pipedrive_client: PipedriveClient = Depends(get_pipedrive_client),
    supabase_client: Any = Depends(get_supabase_client),
) -> dict[str, Any]:
    """Validate that all required custom fields exist in Pipedrive.
    
    Returns validation results for deal, person, and organization fields.
    """
    try:
        mapper = PipedriveFieldMapper(pipedrive_client, supabase_client)
        results = await mapper.validate_all_fields()
        
        return {
            "status": "success",
            "validation_results": results,
        }
    except Exception as e:
        logger.error(f"Error validating fields: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/fields/sync")
async def sync_field_mappings(
    pipedrive_client: PipedriveClient = Depends(get_pipedrive_client),
    supabase_client: Any = Depends(get_supabase_client),
) -> dict[str, Any]:
    """Sync Pipedrive custom fields to database mapping table.
    
    Returns count of synced fields by type.
    """
    try:
        mapper = PipedriveFieldMapper(pipedrive_client, supabase_client)
        results = await mapper.sync_field_mappings()
        
        return {
            "status": "success",
            "sync_results": results,
        }
    except Exception as e:
        logger.error(f"Error syncing field mappings: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/historical-import/rejections")
async def import_historical_rejections(
    limit: int = 1000,
    pipedrive_client: PipedriveClient = Depends(get_pipedrive_client),
    supabase_client: Any = Depends(get_supabase_client),
) -> dict[str, Any]:
    """Import historical rejection data from Pipedrive deals.
    
    Query parameters:
        limit: Maximum number of deals to process (default: 1000)
    
    Returns import results with counts and any errors.
    """
    try:
        importer = PipedriveHistoricalImporter(pipedrive_client, supabase_client)
        results = await importer.import_all_deal_rejections(limit=limit)
        
        return {
            "status": "success",
            "import_results": results,
        }
    except Exception as e:
        logger.error(f"Error importing historical rejections: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/historical-import/deal/{deal_id}")
async def get_deal_rejection_summary(
    deal_id: str,
    pipedrive_client: PipedriveClient = Depends(get_pipedrive_client),
    supabase_client: Any = Depends(get_supabase_client),
) -> dict[str, Any]:
    """Get rejection summary for a specific deal.
    
    Path parameters:
        deal_id: Pipedrive deal ID
    
    Returns rejection summary and notes.
    """
    try:
        importer = PipedriveHistoricalImporter(pipedrive_client, supabase_client)
        results = await importer.import_deal_rejection_summary(deal_id)
        
        return results
    except Exception as e:
        logger.error(f"Error getting deal rejection summary: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/recruiter-workflow/send-to-recruiter/{match_id}")
async def send_match_to_recruiter(
    match_id: str,
    recruiter_name: str,  # 'tal' or 'elad'
    recruiter_id: str = None,
    pipedrive_client: PipedriveClient = Depends(get_pipedrive_client),
    supabase_client: Any = Depends(get_supabase_client),
) -> dict[str, Any]:
    """Send a Carmit-approved match to a recruiter.
    
    Path parameters:
        match_id: PandaPower match ID
        
    Query parameters:
        recruiter_name: 'tal' or 'elad'
        recruiter_id: Pipedrive user ID (optional)
    """
    try:
        manager = RecruiterWorkflowManager(pipedrive_client, supabase_client)
        result = await manager.send_match_to_recruiter(
            match_id=match_id,
            recruiter_name=recruiter_name.lower(),
            recruiter_id=recruiter_id,
        )
        
        return result
    except Exception as e:
        logger.error(f"Error sending match to recruiter: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/recruiter-workflow/record-conversation/{match_id}")
async def record_recruiter_conversation(
    match_id: str,
    recruiter_name: str,
    conversation_summary: str,
    conversation_date: str = None,
    pipedrive_client: PipedriveClient = Depends(get_pipedrive_client),
    supabase_client: Any = Depends(get_supabase_client),
) -> dict[str, Any]:
    """Record a recruiter conversation with candidate.
    
    Path parameters:
        match_id: PandaPower match ID
        
    Query parameters:
        recruiter_name: 'tal' or 'elad'
        conversation_summary: Summary of conversation
        conversation_date: Date of conversation (ISO format, optional)
    """
    try:
        manager = RecruiterWorkflowManager(pipedrive_client, supabase_client)
        result = await manager.record_recruiter_conversation(
            match_id=match_id,
            recruiter_name=recruiter_name.lower(),
            conversation_summary=conversation_summary,
            conversation_date=conversation_date,
        )
        
        return result
    except Exception as e:
        logger.error(f"Error recording conversation: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/recruiter-workflow/record-decision/{match_id}")
async def record_recruiter_decision(
    match_id: str,
    recruiter_name: str,
    decision: str,  # 'accepted' or 'rejected'
    decision_reason: str,
    pipedrive_client: PipedriveClient = Depends(get_pipedrive_client),
    supabase_client: Any = Depends(get_supabase_client),
) -> dict[str, Any]:
    """Record a recruiter's decision on a candidate.
    
    Path parameters:
        match_id: PandaPower match ID
        
    Query parameters:
        recruiter_name: 'tal' or 'elad'
        decision: 'accepted' or 'rejected'
        decision_reason: Explanation for decision
    """
    try:
        manager = RecruiterWorkflowManager(pipedrive_client, supabase_client)
        result = await manager.record_recruiter_decision(
            match_id=match_id,
            recruiter_name=recruiter_name.lower(),
            decision=decision.lower(),
            decision_reason=decision_reason,
        )
        
        return result
    except Exception as e:
        logger.error(f"Error recording decision: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/recruiter-workflow/record-placement/{match_id}")
async def record_placement_outcome(
    match_id: str,
    outcome: str,  # 'hired' or 'placement_failed'
    notes: str,
    pipedrive_client: PipedriveClient = Depends(get_pipedrive_client),
    supabase_client: Any = Depends(get_supabase_client),
) -> dict[str, Any]:
    """Record final placement outcome.
    
    Path parameters:
        match_id: PandaPower match ID
        
    Query parameters:
        outcome: 'hired' or 'placement_failed'
        notes: Final notes
    """
    try:
        manager = RecruiterWorkflowManager(pipedrive_client, supabase_client)
        result = await manager.record_placement_outcome(
            match_id=match_id,
            outcome=outcome.lower(),
            notes=notes,
        )
        
        return result
    except Exception as e:
        logger.error(f"Error recording placement outcome: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sync/bidirectional")
async def trigger_bidirectional_sync(
    pipedrive_client: PipedriveClient = Depends(get_pipedrive_client),
    supabase_client: Any = Depends(get_supabase_client),
) -> dict[str, Any]:
    """Trigger bidirectional sync between Pipedrive and PandaPower.
    
    Syncs:
    - Pipedrive → PandaPower: deals, persons, organizations
    - PandaPower → Pipedrive: match decisions, candidate info
    """
    try:
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
        logger.error(f"Error during bidirectional sync: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sync/status")
async def get_sync_status(
    pipedrive_client: PipedriveClient = Depends(get_pipedrive_client),
) -> dict[str, Any]:
    """Get synchronization status information.
    
    Returns rate limit info, last sync times, and connection status.
    """
    try:
        # Test API connectivity
        response = await pipedrive_client._make_request("GET", "/v1/user")
        
        return {
            "status": "success",
            "connected": response.get("success", False),
            "rate_limit_remaining": pipedrive_client.rate_limit_remaining,
            "rate_limit_reset": pipedrive_client.rate_limit_reset,
            "api_user": response.get("data", {}).get("email") if response.get("success") else None,
        }
    except Exception as e:
        logger.error(f"Error getting sync status: {e}")
        raise HTTPException(status_code=500, detail=str(e))

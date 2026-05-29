"""
Pipedrive Integration Configuration Router
Endpoints for managing Pipedrive API configuration, field mappings, and sync schedules
"""

from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from pydantic import BaseModel
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
import logging
import asyncio

from pandapower.core.supabase import get_supabase_client
from pandapower.core.config import settings
from pandapower.integrations.pipedrive_client import PipedriveClient
from pandapower.workers.pipedrive_sync import sync_pipedrive_contacts
from pandapower.workers.pipedrive_incremental_sync import sync_pipedrive_contacts_incremental
from pandapower.workers.pipedrive_deals_sync import sync_pipedrive_deals

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/pipedrive", tags=["pipedrive-config"])


# ============================================================================
# PYDANTIC MODELS
# ============================================================================

class PipedriveConfigUpdate(BaseModel):
    """Update Pipedrive configuration"""
    api_token: str
    api_domain: Optional[str] = "https://api.pipedrive.com"
    bot_user_id: Optional[str] = None


class FieldMapping(BaseModel):
    """Field mapping between PandaPower and Pipedrive"""
    entity_type: str  # 'deal', 'person', 'organization'
    pandapower_field: str  # e.g., 'job_title'
    pipedrive_field_id: str  # numeric ID
    pipedrive_field_name: str
    field_type: str
    is_required: bool = False
    custom_field_mapping: Optional[Dict[str, str]] = None  # for select fields


class SyncScheduleUpdate(BaseModel):
    """Update sync schedule for an entity type"""
    sync_interval_minutes: int
    sync_direction: str = "bidirectional"  # 'inbound', 'outbound', 'bidirectional'
    sync_enabled: bool = True
    filter_by_contact_type: Optional[str] = None  # for persons: 'client', 'potential_client', 'candidate', 'employee'
    filter_by_status: Optional[str] = None
    sync_days: Optional[List[bool]] = None  # Days of week: [Mon, Tue, Wed, Thu, Fri, Sat, Sun]
    sync_time: Optional[str] = None  # Time in HH:MM format (24-hour)


class ConfigResponse(BaseModel):
    """Pipedrive configuration response"""
    is_active: bool
    api_domain: str
    last_validated_at: Optional[datetime]
    validation_error: Optional[str]


class SyncScheduleResponse(BaseModel):
    """Sync schedule response"""
    entity_type: str
    sync_interval_minutes: int
    sync_direction: str
    sync_enabled: bool
    sync_days: Optional[List[bool]] = None  # Days of week: [Mon, Tue, Wed, Thu, Fri, Sat, Sun]
    sync_time: Optional[str] = None  # Time in HH:MM format
    last_sync_at: Optional[datetime]
    last_sync_status: Optional[str]
    next_scheduled_sync: Optional[datetime]
    sync_count: int


# ============================================================================
# ENDPOINTS
# ============================================================================

@router.get("/config", response_model=ConfigResponse)
async def get_pipedrive_config():
    """Get current Pipedrive configuration"""
    db = await get_supabase_client()

    try:
        response = await db.table("pipedrive_config").select("*").order("created_at", desc=True).limit(1).execute()

        if not response.data:
            return ConfigResponse(
                is_active=False,
                api_domain="https://api.pipedrive.com",
                last_validated_at=None,
                validation_error="No configuration found"
            )

        config = response.data[0]
        return ConfigResponse(
            is_active=config.get("is_active", False),
            api_domain=config.get("api_domain", "https://api.pipedrive.com"),
            last_validated_at=config.get("last_validated_at"),
            validation_error=config.get("validation_error")
        )
    except Exception as e:
        logger.error(f"Error fetching Pipedrive config: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/config")
async def update_pipedrive_config(config: PipedriveConfigUpdate):
    """Update Pipedrive API configuration and validate connection"""
    db = await get_supabase_client()

    try:
        # Test connection with provided credentials
        pipedrive = PipedriveClient(
            api_token=config.api_token,
            api_domain=config.api_domain or "https://api.pipedrive.com"
        )

        # Test API connection by fetching user info
        user_info = await pipedrive._make_request_with_retry("GET", "/v1/users/me")

        if not user_info or "data" not in user_info:
            raise ValueError("Invalid API token or connection failed")

        # Update configuration in database
        config_data = {
            "api_token": config.api_token,
            "api_domain": config.api_domain or "https://api.pipedrive.com",
            "bot_user_id": config.bot_user_id,
            "is_active": True,
            "last_validated_at": datetime.utcnow().isoformat(),
            "validation_error": None,
            "updated_at": datetime.utcnow().isoformat(),
        }

        # Upsert configuration - try to update existing, or insert if not exists
        # First check if config exists
        existing = await db.table("pipedrive_config").select("*").limit(1).execute()

        if existing.data:
            # Update existing record
            await db.table("pipedrive_config").update(config_data).eq("id", existing.data[0]["id"]).execute()
        else:
            # Insert new record
            await db.table("pipedrive_config").insert(config_data).execute()

        logger.info("Pipedrive configuration updated successfully")

        return {
            "status": "success",
            "message": "Pipedrive configuration validated and saved",
            "is_active": True
        }

    except Exception as e:
        logger.error(f"Error updating Pipedrive config: {str(e)}")

        # Save failed attempt
        try:
            db = await get_supabase_client()
            config_data = {
                "api_token": config.api_token,
                "api_domain": config.api_domain or "https://api.pipedrive.com",
                "bot_user_id": config.bot_user_id,
                "is_active": False,
                "last_validated_at": datetime.utcnow().isoformat(),
                "validation_error": str(e),
                "updated_at": datetime.utcnow().isoformat(),
            }
            existing = await db.table("pipedrive_config").select("*").limit(1).execute()
            if existing.data:
                await db.table("pipedrive_config").update(config_data).eq("id", existing.data[0]["id"]).execute()
            else:
                await db.table("pipedrive_config").insert(config_data).execute()
        except:
            pass

        raise HTTPException(status_code=400, detail=f"Configuration validation failed: {str(e)}")


@router.get("/field-mappings")
async def get_field_mappings(entity_type: Optional[str] = None):
    """Get all field mappings, optionally filtered by entity type"""
    db = await get_supabase_client()

    try:
        query = db.table("pipedrive_field_mappings").select("*")

        if entity_type:
            query = query.eq("entity_type", entity_type)

        response = await query.execute()

        return {
            "mappings": response.data,
            "count": len(response.data)
        }
    except Exception as e:
        logger.error(f"Error fetching field mappings: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/field-mappings")
async def create_field_mapping(mapping: FieldMapping):
    """Create or update a field mapping"""
    db = await get_supabase_client()

    try:
        mapping_data = {
            "entity_type": mapping.entity_type,
            "pandapower_field": mapping.pandapower_field,
            "pipedrive_field_id": mapping.pipedrive_field_id,
            "pipedrive_field_name": mapping.pipedrive_field_name,
            "field_type": mapping.field_type,
            "is_required": mapping.is_required,
            "custom_field_mapping": mapping.custom_field_mapping,
            "updated_at": datetime.utcnow().isoformat(),
        }

        # Upsert - check if mapping exists with same entity_type and pandapower_field
        existing = await db.table("pipedrive_field_mappings").select("id").eq("entity_type", mapping.entity_type).eq("pandapower_field", mapping.pandapower_field).execute()

        if existing.data:
            # Update existing record
            await db.table("pipedrive_field_mappings").update(mapping_data).eq("id", existing.data[0]["id"]).execute()
        else:
            # Insert new record
            await db.table("pipedrive_field_mappings").insert(mapping_data).execute()

        logger.info(f"Field mapping created: {mapping.entity_type}.{mapping.pandapower_field}")

        return {
            "status": "success",
            "message": f"Field mapping for {mapping.entity_type}.{mapping.pandapower_field} created"
        }
    except Exception as e:
        logger.error(f"Error creating field mapping: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/field-mappings/{entity_type}/{field_name}")
async def delete_field_mapping(entity_type: str, field_name: str):
    """Delete a field mapping"""
    db = await get_supabase_client()

    try:
        await db.table("pipedrive_field_mappings").delete().eq("entity_type", entity_type).eq("pandapower_field", field_name).execute()

        logger.info(f"Field mapping deleted: {entity_type}.{field_name}")

        return {
            "status": "success",
            "message": f"Field mapping for {entity_type}.{field_name} deleted"
        }
    except Exception as e:
        logger.error(f"Error deleting field mapping: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sync-schedules")
async def get_sync_schedules(entity_type: Optional[str] = None):
    """Get sync schedules for all or specific entity types"""
    db = await get_supabase_client()

    try:
        query = db.table("pipedrive_sync_schedule").select("*")

        if entity_type:
            query = query.eq("entity_type", entity_type)

        response = await query.execute()

        return {
            "schedules": response.data,
            "count": len(response.data)
        }
    except Exception as e:
        logger.error(f"Error fetching sync schedules: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sync-schedules/{entity_type}")
@router.put("/sync-schedules/{entity_type}")
async def update_sync_schedule(entity_type: str, schedule: SyncScheduleUpdate):
    """Update sync schedule for an entity type"""
    db = await get_supabase_client()

    try:
        # Validate sync_time format if provided
        if schedule.sync_time:
            parts = schedule.sync_time.split(":")
            if len(parts) != 2:
                raise ValueError("sync_time must be in HH:MM format")
            try:
                hour = int(parts[0])
                minute = int(parts[1])
                if not (0 <= hour <= 23 and 0 <= minute <= 59):
                    raise ValueError("Invalid time values")
            except ValueError as e:
                raise ValueError(f"Invalid sync_time format: {str(e)}")

        # Validate sync_days if provided
        if schedule.sync_days:
            if len(schedule.sync_days) not in [6, 7]:
                raise ValueError("sync_days must have 6 or 7 boolean values (Sun-Fri or Sun-Sat)")

        # Calculate next sync time
        next_sync = datetime.utcnow() + timedelta(minutes=schedule.sync_interval_minutes)

        schedule_data = {
            "sync_interval_minutes": schedule.sync_interval_minutes,
            "sync_direction": schedule.sync_direction,
            "sync_enabled": schedule.sync_enabled,
            "filter_by_contact_type": schedule.filter_by_contact_type,
            "filter_by_status": schedule.filter_by_status,
            "next_scheduled_sync": next_sync.isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
        }

        # Add optional fields if provided
        if schedule.sync_days is not None:
            schedule_data["sync_days"] = schedule.sync_days
        if schedule.sync_time is not None:
            schedule_data["sync_time"] = schedule.sync_time

        await db.table("pipedrive_sync_schedule").update(schedule_data).eq("entity_type", entity_type).execute()

        logger.info(f"Sync schedule updated for {entity_type}: every {schedule.sync_interval_minutes} minutes")

        return {
            "status": "success",
            "message": f"Sync schedule for {entity_type} updated",
            "next_scheduled_sync": next_sync.isoformat()
        }
    except ValueError as e:
        logger.error(f"Validation error updating sync schedule: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error updating sync schedule: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sync-now/{entity_type}")
async def trigger_sync_now(entity_type: str, background_tasks: BackgroundTasks):
    """Manually trigger a sync for a specific entity type"""
    db = await get_supabase_client()

    try:
        # Validate entity_type
        if entity_type not in ["persons", "organizations", "deals"]:
            raise ValueError(f"Invalid entity_type: {entity_type}")

        # Get sync schedule
        response = await db.table("pipedrive_sync_schedule").select("*").eq("entity_type", entity_type).single().execute()
        schedule = response.data

        if not schedule:
            raise ValueError(f"No sync schedule found for {entity_type}")

        # Log sync start
        sync_log_id = None
        log_response = await db.table("pipedrive_sync_log").insert({
            "entity_type": entity_type,
            "sync_direction": schedule.get("sync_direction", "bidirectional"),
            "status": "in_progress",
            "started_at": datetime.utcnow().isoformat()
        }).execute()

        if log_response.data:
            sync_log_id = log_response.data[0]["id"]

        # Trigger background sync based on entity_type
        if entity_type == "persons":
            background_tasks.add_task(_run_sync_task, sync_pipedrive_contacts, sync_log_id)
        elif entity_type == "deals":
            background_tasks.add_task(_run_sync_task, sync_pipedrive_deals, sync_log_id)
        else:
            logger.warning(f"Sync not yet implemented for {entity_type}")

        return {
            "status": "success",
            "message": f"Sync for {entity_type} triggered (running in background)",
            "sync_log_id": sync_log_id
        }
    except Exception as e:
        logger.error(f"Error triggering sync: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sync-incremental/{entity_type}")
async def trigger_incremental_sync(entity_type: str, background_tasks: BackgroundTasks, minutes_back: int = 60):
    """Trigger an incremental (delta) sync - only fetches recently modified contacts"""
    db = await get_supabase_client()

    try:
        if entity_type != "persons":
            raise ValueError(f"Incremental sync only supported for persons, not {entity_type}")

        # Log sync start
        sync_log_id = None
        log_response = await db.table("pipedrive_sync_log").insert({
            "entity_type": entity_type,
            "sync_direction": "inbound",
            "status": "in_progress",
            "started_at": datetime.utcnow().isoformat()
        }).execute()

        if log_response.data:
            sync_log_id = log_response.data[0]["id"]

        # Trigger background incremental sync
        background_tasks.add_task(
            _run_incremental_sync_task,
            sync_pipedrive_contacts_incremental,
            minutes_back,
            sync_log_id
        )

        return {
            "status": "success",
            "message": f"Incremental sync triggered (fetching last {minutes_back} minutes of changes)",
            "sync_log_id": sync_log_id,
            "minutes_back": minutes_back
        }
    except Exception as e:
        logger.error(f"Error triggering incremental sync: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


async def _run_sync_task(sync_func, sync_log_id: Optional[str] = None):
    """Run sync task and update log"""
    db = await get_supabase_client()
    try:
        result = await sync_func()
        logger.info(f"Sync completed successfully: {result}")

        if sync_log_id:
            update_data = {
                "status": "completed",
                "completed_at": datetime.utcnow().isoformat(),
                "total_records": result.get("total", 0),
                "created_count": (result.get("employees", 0) +
                                 result.get("clients", 0) +
                                 result.get("potential_clients", 0)),
                "failed_count": len(result.get("errors", []))
            }
            await db.table("pipedrive_sync_log").update(update_data).eq("id", sync_log_id).execute()

    except Exception as e:
        logger.error(f"Sync task failed: {str(e)}")
        if sync_log_id:
            try:
                await db.table("pipedrive_sync_log").update({
                    "status": "failed",
                    "completed_at": datetime.utcnow().isoformat(),
                    "error_message": str(e)
                }).eq("id", sync_log_id).execute()
            except Exception as log_error:
                logger.error(f"Failed to update sync log: {str(log_error)}")


async def _run_incremental_sync_task(sync_func, minutes_back: int, sync_log_id: Optional[str] = None):
    """Run incremental sync task and update log"""
    db = await get_supabase_client()
    try:
        result = await sync_func(minutes_back=minutes_back)
        logger.info(f"Incremental sync completed successfully: {result}")

        if sync_log_id:
            update_data = {
                "status": "completed",
                "completed_at": datetime.utcnow().isoformat(),
                "total_records": result.get("total", 0),
                "created_count": (result.get("employees", 0) +
                                 result.get("clients", 0) +
                                 result.get("potential_clients", 0)),
                "failed_count": len(result.get("errors", []))
            }
            await db.table("pipedrive_sync_log").update(update_data).eq("id", sync_log_id).execute()

    except Exception as e:
        logger.error(f"Incremental sync task failed: {str(e)}")
        if sync_log_id:
            try:
                await db.table("pipedrive_sync_log").update({
                    "status": "failed",
                    "completed_at": datetime.utcnow().isoformat(),
                    "error_message": str(e)
                }).eq("id", sync_log_id).execute()
            except Exception as log_error:
                logger.error(f"Failed to update sync log: {str(log_error)}")


@router.get("/sync-history/{entity_type}")
async def get_sync_history(entity_type: str, limit: int = 10):
    """Get sync history for an entity type"""
    db = await get_supabase_client()

    try:
        response = await db.table("pipedrive_sync_log").select("*").eq("entity_type", entity_type).order("started_at", desc=True).limit(limit).execute()

        return {
            "history": response.data,
            "count": len(response.data)
        }
    except Exception as e:
        logger.error(f"Error fetching sync history: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/test-connection")
async def test_pipedrive_connection():
    """Test Pipedrive API connection with current configuration"""
    db = await get_supabase_client()

    try:
        # Get current config
        response = await db.table("pipedrive_config").select("*").order("created_at", desc=True).limit(1).execute()

        if not response.data:
            raise ValueError("No Pipedrive configuration found")

        config = response.data[0]

        if not config.get("is_active"):
            raise ValueError("Pipedrive configuration is not active")

        # Test connection
        pipedrive = PipedriveClient(
            api_token=config.get("api_token"),
            api_domain=config.get("api_domain", "https://api.pipedrive.com")
        )

        user_info = await pipedrive._make_request_with_retry("GET", "/v1/users/me")

        return {
            "status": "success",
            "message": "Connection to Pipedrive successful",
            "user": user_info.get("data", {}).get("name", "Unknown") if user_info else "Unknown"
        }
    except Exception as e:
        logger.error(f"Error testing Pipedrive connection: {str(e)}")
        raise HTTPException(status_code=400, detail=f"Connection test failed: {str(e)}")

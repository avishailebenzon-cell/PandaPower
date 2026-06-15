"""
Pipedrive Data Display API
Endpoints for displaying synced Pipedrive data: employees, clients, organizations, jobs
"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Optional, List, Dict
from datetime import datetime, timedelta
import logging

from pandapower.core.supabase import get_supabase_client
from pandapower.core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/pipedrive/data", tags=["pipedrive-data"])


# In-memory cache for organization names (refreshed every hour)
_org_name_cache: Dict[int, str] = {}
_org_cache_expiry: Optional[datetime] = None


async def _get_organizations_cache() -> Dict[int, str]:
    """Get pipedrive_org_id -> name mapping from database cache (no API calls)"""
    global _org_name_cache, _org_cache_expiry

    now = datetime.utcnow()
    if _org_cache_expiry and now < _org_cache_expiry and _org_name_cache:
        return _org_name_cache

    try:
        db = await get_supabase_client()
        response = await db.table("organizations").select("id, name").execute()
        orgs = response.data or []

        # Convert UUID id to pipedrive_org_id (reverse the deterministic UUID)
        # For now, we'll use a simpler approach: build a map from the database
        cache = {}
        for org in orgs:
            if org.get("id") and org.get("name"):
                # Store by the org id from the database (which is UUID)
                # But we'll also try to map back to pipedrive_org_id if needed
                cache[org["id"]] = org.get("name", "")

        _org_name_cache = cache
        _org_cache_expiry = now + timedelta(hours=1)
        logger.info(f"Refreshed organizations cache from DB: {len(cache)} orgs")
        return cache

    except Exception as e:
        logger.error(f"Failed to refresh org cache from DB: {e}")
        return _org_name_cache  # Return stale cache on error


# ============================================================================
# PYDANTIC MODELS
# ============================================================================

class PaginatedResponse(BaseModel):
    """Generic paginated response"""
    data: List[dict]
    count: int
    total: int
    page: int
    limit: int
    total_pages: int
    last_sync: Optional[datetime]


# ============================================================================
# HELPERS
# ============================================================================

async def _fetch_contacts_by_status(
    contact_status: str,
    page: int,
    limit: int,
    search: Optional[str],
    sort_by: str,
    sort_order: str,
) -> PaginatedResponse:
    """
    Fetch contacts from the existing `contacts` table, filtered by contact_status.

    contact_status values:
    - 'employee' (עובדים)
    - 'client' (לקוחות)
    - 'potential_client' (לקוחות פוטנציאלים)
    - 'candidate' (מועמדים)
    """
    db = await get_supabase_client()

    try:
        offset = (page - 1) * limit

        # Map sort_by to actual column name (contacts.full_name not name)
        sort_column_map = {
            "name": "full_name",
            "email": "email",
            "created_at": "created_at",
        }
        sort_column = sort_column_map.get(sort_by, "full_name")

        # Build count query
        count_query = db.table("contacts").select("id", count="exact").eq(
            "contact_status", contact_status
        )

        if search:
            count_query = count_query.or_(
                f"full_name.ilike.%{search}%,email.ilike.%{search}%"
            )

        count_result = await count_query.execute()
        total = count_result.count if hasattr(count_result, "count") else 0

        # Build data query - include all relevant person fields including org link
        query = db.table("contacts").select(
            "id, pipedrive_person_id, full_name, email, phone, "
            "organization_id, pipedrive_org_id, contact_status, professional_domain, "
            "security_clearance_level, "
            "pipedrive_last_synced_at, created_at, updated_at"
        ).eq("contact_status", contact_status)

        if search:
            query = query.or_(f"full_name.ilike.%{search}%,email.ilike.%{search}%")

        # Apply sorting and pagination
        query = query.order(sort_column, desc=(sort_order == "desc"))
        response = await query.range(offset, offset + limit - 1).execute()

        rows = response.data or []

        # Resolve company names from organizations table (FK by UUID)
        org_uuids = {row["organization_id"] for row in rows if row.get("organization_id")}
        org_name_by_uuid: Dict[str, str] = {}
        if org_uuids:
            try:
                orgs_resp = await db.table("organizations").select(
                    "id, name"
                ).in_("id", list(org_uuids)).execute()
                for org in (orgs_resp.data or []):
                    org_name_by_uuid[org["id"]] = org.get("name", "")
            except Exception as e:
                logger.warning(f"Could not resolve org names for contacts: {e}")

        # Normalize data: rename full_name -> name for the frontend
        normalized = []
        for row in rows:
            org_uuid = row.get("organization_id")
            company_name = org_name_by_uuid.get(org_uuid, "") if org_uuid else ""
            normalized.append({
                "id": row.get("id"),
                "pipedrive_person_id": row.get("pipedrive_person_id"),
                "name": row.get("full_name"),
                "full_name": row.get("full_name"),
                "email": row.get("email"),
                "phone": row.get("phone"),
                "organization_id": row.get("organization_id"),
                "pipedrive_org_id": row.get("pipedrive_org_id"),
                "company_name": company_name,
                "company": company_name,  # alias for jobs-like display
                "contact_status": row.get("contact_status"),
                "professional_domain": row.get("professional_domain"),
                "security_clearance_level": row.get("security_clearance_level"),
                "sync_status": "synced",
                "pipedrive_last_synced_at": row.get("pipedrive_last_synced_at"),
                "last_synced": row.get("pipedrive_last_synced_at"),
                "created_at": row.get("created_at"),
                "updated_at": row.get("updated_at"),
            })

        # Get last sync timestamp
        sync_log = await db.table("pipedrive_sync_log")\
            .select("completed_at")\
            .eq("entity_type", "persons")\
            .order("completed_at", desc=True)\
            .limit(1)\
            .execute()

        last_sync = sync_log.data[0]["completed_at"] if sync_log.data else None

        total_pages = (total + limit - 1) // limit if total > 0 else 1

        return PaginatedResponse(
            data=normalized,
            count=len(normalized),
            total=total,
            page=page,
            limit=limit,
            total_pages=total_pages,
            last_sync=last_sync,
        )

    except Exception as e:
        logger.error(f"Error fetching contacts ({contact_status}): {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# ENDPOINTS
# ============================================================================

@router.get("/employees", response_model=PaginatedResponse)
async def get_employees(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=1000),
    search: Optional[str] = None,
    sort_by: str = Query("name", regex="^(name|email|created_at)$"),
    sort_order: str = Query("asc", regex="^(asc|desc)$"),
):
    """Get all company employees (עובדים) from contacts table"""
    return await _fetch_contacts_by_status(
        contact_status="employee",
        page=page,
        limit=limit,
        search=search,
        sort_by=sort_by,
        sort_order=sort_order,
    )


@router.get("/clients", response_model=PaginatedResponse)
async def get_clients(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=1000),
    search: Optional[str] = None,
    status: Optional[str] = None,
    sort_by: str = Query("name", regex="^(name|email|created_at)$"),
    sort_order: str = Query("asc", regex="^(asc|desc)$"),
):
    """Get all clients (לקוחות) from contacts table"""
    return await _fetch_contacts_by_status(
        contact_status="client",
        page=page,
        limit=limit,
        search=search,
        sort_by=sort_by,
        sort_order=sort_order,
    )


@router.get("/potential-clients", response_model=PaginatedResponse)
async def get_potential_clients(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=1000),
    search: Optional[str] = None,
    interest_level: Optional[str] = None,
    sort_by: str = Query("name", regex="^(name|email|created_at)$"),
    sort_order: str = Query("asc", regex="^(asc|desc)$"),
):
    """Get all potential clients (לקוחות פוטנציאלים) from contacts table"""
    return await _fetch_contacts_by_status(
        contact_status="potential_client",
        page=page,
        limit=limit,
        search=search,
        sort_by=sort_by,
        sort_order=sort_order,
    )


@router.get("/organizations", response_model=PaginatedResponse)
async def get_organizations(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=1000),
    search: Optional[str] = None,
    industry: Optional[str] = None,
    sort_by: str = Query("name", regex="^(name|created_at)$"),
    sort_order: str = Query("asc", regex="^(asc|desc)$"),
):
    """Get all organizations synced from Pipedrive.

    The organizations table currently has only id/name/created_at columns,
    so we surface `created_at` as the per-row "last synced" timestamp (every
    row was written by the sync job, so that's the most recent moment we
    know it existed in Pipedrive). The frontend turns it into a 🟢/🟡/🔴
    badge based on age.
    """
    db = await get_supabase_client()

    try:
        offset = (page - 1) * limit

        count_query = db.table("organizations").select("id", count="exact")
        if search:
            count_query = count_query.ilike("name", f"%{search}%")
        count_result = await count_query.execute()
        total = count_result.count if hasattr(count_result, "count") else 0

        query = db.table("organizations").select("id, name, created_at")
        if search:
            query = query.ilike("name", f"%{search}%")
        query = query.order(sort_by, desc=(sort_order == "desc"))
        response = await query.range(offset, offset + limit - 1).execute()

        # Augment each row so the SyncStatusIndicator has a real timestamp +
        # the implicit "synced from Pipedrive" status. `created_at` is the row's
        # write-time, which equals its last sync (we don't yet store updates
        # separately on the organizations table).
        rows = response.data or []
        for r in rows:
            ts = r.get("created_at")
            r["last_synced_at"] = ts
            r["pipedrive_last_synced_at"] = ts  # alias for callers that look for this
            r["sync_status"] = "completed" if ts else "unknown"

        # Top-of-page banner: most recent completed run for organizations.
        # NOTE: many organizations sync runs stay 'in_progress' (bug to fix
        # separately). To avoid forever showing "never synced", we look at
        # 'completed' first and fall back to the freshest row's created_at.
        last_sync = None
        try:
            sync_log = await db.table("pipedrive_sync_log")\
                .select("completed_at")\
                .eq("entity_type", "organizations")\
                .eq("status", "completed")\
                .order("completed_at", desc=True)\
                .limit(1)\
                .execute()
            if sync_log.data and sync_log.data[0].get("completed_at"):
                last_sync = sync_log.data[0]["completed_at"]
        except Exception as e:
            logger.debug(f"sync_log lookup failed: {e}")

        if not last_sync:
            # Fallback: newest row in the organizations table itself.
            try:
                newest = await db.table("organizations")\
                    .select("created_at")\
                    .order("created_at", desc=True)\
                    .limit(1)\
                    .execute()
                if newest.data:
                    last_sync = newest.data[0].get("created_at")
            except Exception:
                pass

        total_pages = (total + limit - 1) // limit if total > 0 else 1

        return PaginatedResponse(
            data=rows,
            count=len(rows),
            total=total,
            page=page,
            limit=limit,
            total_pages=total_pages,
            last_sync=last_sync,
        )

    except Exception as e:
        logger.error(f"Error fetching organizations: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# Priority id -> human-readable label (also used by frontend)
PRIORITY_LABELS = {
    1: "עדיפות גיוס 1",
    2: "עדיפות גיוס 2",
    3: "עדיפות גיוס 3",
    4: "עדיפות גיוס 4",
    5: "עדיפות גיוס 5",
}


@router.get("/jobs", response_model=PaginatedResponse)
async def get_jobs(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=1000),
    search: Optional[str] = None,
    status: Optional[str] = None,
    sort_by: str = Query("title", regex="^(title|job_title|created_at|posted_date|priority|deadline)$"),
    sort_order: str = Query("asc", regex="^(asc|desc)$"),
):
    """Get all jobs synced from Pipedrive with full field mapping"""
    db = await get_supabase_client()

    try:
        offset = (page - 1) * limit

        # Map frontend sort keys to actual DB columns
        sort_column_map = {
            "title": "job_title",
            "job_title": "job_title",
            "posted_date": "created_at",
            "created_at": "created_at",
            "priority": "priority",
            "deadline": "deadline",
        }
        sort_column = sort_column_map.get(sort_by, "job_title")

        # Count query
        count_query = db.table("jobs").select("id", count="exact")
        if search:
            count_query = count_query.ilike("job_title", f"%{search}%")
        if status:
            count_query = count_query.eq("status", status)
        count_result = await count_query.execute()
        total = count_result.count if hasattr(count_result, "count") else 0

        # Data query - fetch all relevant fields
        query = db.table("jobs").select(
            "id, pipedrive_deal_id, job_title, job_description, job_qualifications, "
            "job_location, job_security_clearance, deadline, priority, classification_level, "
            "status, person_id, org_id, stage_id, "
            "created_at, updated_at, pipedrive_last_synced_at"
        )
        if search:
            query = query.ilike("job_title", f"%{search}%")
        if status:
            query = query.eq("status", status)
        query = query.order(sort_column, desc=(sort_order == "desc"))
        response = await query.range(offset, offset + limit - 1).execute()

        rows = response.data or []

        # Resolve company names from organizations table (by pipedrive_org_id -> UUID)
        org_pipedrive_ids = {row["org_id"] for row in rows if row.get("org_id")}
        org_map: Dict[int, str] = {}
        if org_pipedrive_ids:
            # Convert pipedrive ids to our deterministic UUIDs
            import uuid as _uuid
            _ORG_NS = _uuid.UUID("12345678-1234-5678-1234-567812345678")
            uuid_to_pdid: Dict[str, int] = {}
            for pdid in org_pipedrive_ids:
                u = str(_uuid.uuid5(_ORG_NS, f"pipedrive_org:{pdid}"))
                uuid_to_pdid[u] = pdid
            try:
                orgs_resp = await db.table("organizations").select(
                    "id, name"
                ).in_("id", list(uuid_to_pdid.keys())).execute()
                for org in (orgs_resp.data or []):
                    pdid = uuid_to_pdid.get(org["id"])
                    if pdid:
                        org_map[pdid] = org.get("name", "")
            except Exception as e:
                logger.warning(f"Could not resolve org names from DB: {e}")

        # Note: we no longer fall back to Pipedrive API calls here
        # Organizations should be synced by the scheduled sync job.
        # If an org is missing from the DB, show blank instead of calling API.
        if len(org_map) < len(org_pipedrive_ids):
            logger.debug(f"Missing {len(org_pipedrive_ids) - len(org_map)} org names in database")

        # Resolve contact names for person_ids
        person_pipedrive_ids = {row["person_id"] for row in rows if row.get("person_id")}
        person_name_by_pid: Dict[int, str] = {}
        if person_pipedrive_ids:
            try:
                persons_resp = await db.table("contacts").select(
                    "pipedrive_person_id, full_name"
                ).in_("pipedrive_person_id", list(person_pipedrive_ids)).execute()
                for c in (persons_resp.data or []):
                    person_name_by_pid[c["pipedrive_person_id"]] = c.get("full_name", "")
            except Exception as e:
                logger.warning(f"Could not resolve contact names: {e}")

        # Normalize data for the frontend
        normalized = []
        for row in rows:
            org_id = row.get("org_id")
            company_name = org_map.get(org_id, "") if org_id else ""
            priority_raw = row.get("priority")
            try:
                priority_num = int(priority_raw) if priority_raw is not None and priority_raw != "" else None
            except (ValueError, TypeError):
                priority_num = None
            priority_label = PRIORITY_LABELS.get(priority_num) if priority_num else None

            person_id = row.get("person_id")
            contact_name = person_name_by_pid.get(person_id, "") if person_id else ""

            normalized.append({
                "id": row.get("id"),
                "pipedrive_deal_id": row.get("pipedrive_deal_id"),
                "pipedrive_id": str(row.get("pipedrive_deal_id")) if row.get("pipedrive_deal_id") else None,

                # Title
                "title": row.get("job_title"),
                "job_title": row.get("job_title"),

                # Description / qualifications
                "description": row.get("job_description"),
                "job_description": row.get("job_description"),
                "qualifications": row.get("job_qualifications"),
                "job_qualifications": row.get("job_qualifications"),

                # Company / organization
                "company": company_name,
                "org_id": org_id,

                # Contact person (linked to deal)
                "contact_person": contact_name,
                "contact_name": contact_name,
                "person_id": person_id,

                # Location
                "location": row.get("job_location"),
                "job_location": row.get("job_location"),

                # Security clearance
                "security_clearance": row.get("job_security_clearance"),
                "job_security_clearance": row.get("job_security_clearance"),

                # Deadline
                "deadline": row.get("deadline"),

                # Priority
                "priority": priority_num,
                "priority_label": priority_label,

                # Status
                "status": row.get("status") or "open",
                "classification_level": row.get("classification_level"),
                "department": None,

                # Meta
                "posted_date": row.get("created_at"),
                "candidates_count": 0,
                "sync_status": "synced",
                "last_synced": row.get("pipedrive_last_synced_at"),
                "created_at": row.get("created_at"),
                "updated_at": row.get("updated_at"),
            })

        sync_log = await db.table("pipedrive_sync_log")\
            .select("completed_at")\
            .eq("entity_type", "deals")\
            .order("completed_at", desc=True)\
            .limit(1)\
            .execute()

        last_sync = sync_log.data[0]["completed_at"] if sync_log.data else None
        total_pages = (total + limit - 1) // limit if total > 0 else 1

        return PaginatedResponse(
            data=normalized,
            count=len(normalized),
            total=total,
            page=page,
            limit=limit,
            total_pages=total_pages,
            last_sync=last_sync,
        )

    except Exception as e:
        logger.error(f"Error fetching jobs: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

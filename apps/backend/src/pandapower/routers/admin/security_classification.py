"""
Admin API endpoints for security classification configuration.

Manages security level synonyms and keywords for CV analysis.
The keywords here are loaded by the CV parser and fed to Claude so it can
detect clearance levels in candidate CVs.
"""

import json
import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from pandapower.core.supabase import get_supabase_client

# Key under which user-saved defaults live in system_settings.
# When present, this takes precedence over the hardcoded DEFAULT_SECURITY_LEVELS.
USER_DEFAULTS_KEY = "security.user_saved_defaults"
USER_DEFAULTS_TIMESTAMP_KEY = "security.user_saved_defaults_updated_at"

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin/security", tags=["admin", "security"])


class SecurityLevel(BaseModel):
    """Security classification level."""
    id: Optional[str] = None
    name: str
    name_he: str
    level: int  # 1-6 progressively higher clearance
    keywords: list[str]
    description: Optional[str] = None


class SecurityLevelUpdate(BaseModel):
    """Replace all keywords for a security level."""
    keywords: list[str]
    description: Optional[str] = None


class KeywordRequest(BaseModel):
    """Single-keyword add/remove request."""
    keyword: str


class ClassificationRequest(BaseModel):
    """Request for classifying free text."""
    text: str


# Default 6-level system tuned for Israeli recruitment.
# These are the SEED keywords; users can add/remove via the admin UI.
DEFAULT_SECURITY_LEVELS = [
    {
        "name": "Level 1",
        "name_he": "רמה 1",
        "level": 1,
        "keywords": [
            # Hebrew
            "רמה 1", "סיווג רמה 1", "סיווג בסיסי", "אישור ביטחוני בסיסי",
            "בסיסי", "מתחילים",
            # English
            "level 1", "basic clearance", "entry-level clearance", "tier 1",
            "general operations",
        ],
        "description": "אישור ביטחוני בסיסי לפעילויות כלליות (entry/junior)",
    },
    {
        "name": "Level 2",
        "name_he": "רמה 2",
        "level": 2,
        "keywords": [
            # Hebrew
            "רמה 2", "סיווג רמה 2", "ביטחוני 2", "ביניים", "פעילויות רגישות",
            # English
            "level 2", "tier 2", "intermediate clearance", "sensitive operations",
            "mid-level clearance",
            # IDF tech units (default to L2)
            "ממר\"ם", "ממרם", "Mamram", "Tikshuv",
        ],
        "description": "אישור ביטחוני ביניים לפעילויות רגישות",
    },
    {
        "name": "Level 3",
        "name_he": "רמה 3",
        "level": 3,
        "keywords": [
            # Hebrew
            "רמה 3", "סיווג רמה 3", "סודי", "סיווג סודי", "סודי ביותר",
            "אישור סודי", "מתקדם", "בכיר", "גישה מוגבלת",
            # English
            "level 3", "tier 3", "confidential", "secret", "advanced clearance",
            "restricted access", "senior clearance",
        ],
        "description": "אישור סודי לגישה מוגבלת",
    },
    {
        "name": "Level 4",
        "name_he": "רמה 4",
        "level": 4,
        "keywords": [
            # Hebrew
            "רמה 4", "סיווג רמה 4", "סודי ביותר", "אבטחה גבוהה",
            "מערכות קריטיות", "אישור גבוה",
            # English
            "level 4", "tier 4", "high security clearance", "critical systems",
            "high clearance",
            # IDF intelligence units (default to L4)
            "8200", "יחידה 8200", "Unit 8200", "9900", "יחידה 9900", "Unit 9900",
            "81", "יחידה 81", "Unit 81",
        ],
        "description": "אישור אבטחה גבוה למערכות קריטיות",
    },
    {
        "name": "Level 5",
        "name_he": "רמה 5",
        "level": 5,
        "keywords": [
            # Hebrew
            "רמה 5", "סיווג רמה 5", "סודי מאוד", "סיווג גבוה",
            "מידע מסווג", "מידע סווג", "רמה עליונה",
            # English
            "level 5", "tier 5", "top secret", "TS", "classified information",
            "top-level clearance",
            # Specialized IDF (Talpiot, Havatzalot etc. - elite tracks)
            "תלפיות", "Talpiot", "חבצלות", "Havatzalot",
        ],
        "description": "אישור מאוד גבוה למידע מסווג",
    },
    {
        "name": "Level 6",
        "name_he": "רמה 6",
        "level": 6,
        "keywords": [
            # Hebrew
            "רמה 6", "סיווג רמה 6", "סוד עליון", "רמה הגבוהה ביותר",
            "ברמה הגבוהה ביותר", "סיווג מירבי",
            # English
            "level 6", "tier 6", "TS/SCI", "TS-SCI", "SCI",
            "ultra-sensitive", "maximum clearance", "compartmented",
        ],
        "description": "סיווג מירבי - מידע ברגישות עליונה",
    },
]


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


async def _upsert_level(supabase, payload: dict) -> None:
    """UPDATE if a row with this `name` exists, otherwise INSERT.

    Works around the lack of a UNIQUE constraint on security_levels.name
    (which would make .upsert(on_conflict='name') unusable).
    """
    name = payload["name"]
    existing = await supabase.table("security_levels").select("id").eq(
        "name", name
    ).limit(1).execute()
    if existing.data:
        await supabase.table("security_levels").update(payload).eq(
            "name", name
        ).execute()
    else:
        await supabase.table("security_levels").insert(payload).execute()


async def _load_user_saved_defaults(supabase) -> tuple[Optional[list[dict]], Optional[str]]:
    """Return (levels_list, saved_at_iso) from system_settings, or (None, None)
    if the user has never saved their own defaults yet.
    """
    try:
        resp = await supabase.table("system_settings").select("setting_value").eq(
            "setting_key", USER_DEFAULTS_KEY
        ).limit(1).execute()
        if not resp.data:
            return None, None
        raw_value = resp.data[0].get("setting_value")
        if not raw_value or raw_value == "null":
            return None, None
        # setting_value is stored as a JSON-encoded string
        if isinstance(raw_value, str):
            levels = json.loads(raw_value)
        else:
            levels = raw_value
        if not isinstance(levels, list) or not levels:
            return None, None

        # Fetch the saved-at timestamp (best-effort)
        ts_resp = await supabase.table("system_settings").select("setting_value").eq(
            "setting_key", USER_DEFAULTS_TIMESTAMP_KEY
        ).limit(1).execute()
        saved_at = None
        if ts_resp.data:
            ts_raw = ts_resp.data[0].get("setting_value")
            if isinstance(ts_raw, str):
                saved_at = ts_raw.strip('"')

        return levels, saved_at
    except Exception as e:
        logger.warning(f"Could not load user-saved security defaults: {e}")
        return None, None


def _effective_defaults_sync(user_saved: Optional[list[dict]]) -> list[dict]:
    """Pick the right defaults: user-saved (if present) else hardcoded."""
    if user_saved:
        return user_saved
    return DEFAULT_SECURITY_LEVELS


async def _save_setting(supabase, key: str, value: str) -> None:
    """Upsert a single key/value into system_settings. Schema-aware."""
    existing = await supabase.table("system_settings").select("setting_key").eq(
        "setting_key", key
    ).limit(1).execute()
    payload = {
        "setting_key": key,
        "setting_value": value,
        "updated_at": datetime.utcnow().isoformat(),
    }
    if existing.data:
        await supabase.table("system_settings").update(payload).eq(
            "setting_key", key
        ).execute()
    else:
        await supabase.table("system_settings").insert(payload).execute()


# ─────────────────────────────────────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────────────────────────────────────


@router.get("/levels", response_model=list[SecurityLevel])
async def list_security_levels(supabase=Depends(get_supabase_client)) -> list[SecurityLevel]:
    """List all security classification levels (from DB; falls back to defaults)."""
    try:
        response = await supabase.table("security_levels").select("*").order("level").execute()
        if response.data:
            return [SecurityLevel(**level) for level in response.data]
        # DB is empty - seed it lazily so user immediately sees something to edit.
        logger.info("security_levels table empty - seeding defaults")
        for level_data in DEFAULT_SECURITY_LEVELS:
            try:
                await _upsert_level(supabase, level_data)
            except Exception as e:
                logger.warning(f"Could not seed level {level_data['name']}: {e}")
        return [SecurityLevel(**level) for level in DEFAULT_SECURITY_LEVELS]

    except Exception as e:
        logger.warning(f"Could not fetch security levels from database: {e}, using defaults")
        return [SecurityLevel(**level) for level in DEFAULT_SECURITY_LEVELS]


@router.get("/levels/{level_name}", response_model=SecurityLevel)
async def get_security_level(
    level_name: str, supabase=Depends(get_supabase_client)
) -> SecurityLevel:
    """Get a specific security level with its keywords."""
    try:
        response = await supabase.table("security_levels").select("*").eq(
            "name", level_name
        ).limit(1).execute()
        if response.data:
            return SecurityLevel(**response.data[0])
    except Exception as e:
        logger.warning(f"DB lookup failed for level '{level_name}': {e}")

    for level in DEFAULT_SECURITY_LEVELS:
        if level["name"] == level_name:
            return SecurityLevel(**level)

    raise HTTPException(status_code=404, detail=f"Security level '{level_name}' not found")


@router.post("/levels/{level_name}")
async def update_security_level(
    level_name: str,
    update: SecurityLevelUpdate,
    supabase=Depends(get_supabase_client),
) -> dict:
    """Replace ALL keywords for a security level.

    For incremental edits prefer /levels/{name}/keywords/add or /remove.
    """
    try:
        # Deduplicate + normalize whitespace
        cleaned = sorted({kw.strip() for kw in update.keywords if kw and kw.strip()})

        # Upsert (insert if missing, update if present) keyed by name
        existing = next((lv for lv in DEFAULT_SECURITY_LEVELS if lv["name"] == level_name), None)
        payload = {
            "name": level_name,
            "name_he": existing["name_he"] if existing else level_name,
            "level": existing["level"] if existing else 0,
            "keywords": cleaned,
            "description": update.description or (existing["description"] if existing else None),
        }
        await _upsert_level(supabase, payload)

        return {
            "status": "updated",
            "level_name": level_name,
            "keywords_count": len(cleaned),
        }

    except Exception as e:
        logger.error(f"Failed to update security level: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/levels/{level_name}/keywords/add")
async def add_keyword(
    level_name: str,
    req: KeywordRequest,
    supabase=Depends(get_supabase_client),
) -> dict:
    """Add a single keyword to a security level (idempotent)."""
    keyword = req.keyword.strip()
    if not keyword:
        raise HTTPException(status_code=400, detail="keyword must not be empty")

    try:
        # Get current level
        current = await get_security_level(level_name, supabase)
        new_keywords = sorted(set(current.keywords + [keyword]))

        await _upsert_level(supabase, {
            "name": current.name,
            "name_he": current.name_he,
            "level": current.level,
            "keywords": new_keywords,
            "description": current.description,
        })

        return {
            "status": "added" if keyword not in current.keywords else "already_exists",
            "level_name": level_name,
            "keyword": keyword,
            "total_keywords": len(new_keywords),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to add keyword: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/levels/{level_name}/keywords/remove")
async def remove_keyword(
    level_name: str,
    req: KeywordRequest,
    supabase=Depends(get_supabase_client),
) -> dict:
    """Remove a single keyword from a security level."""
    keyword = req.keyword.strip()
    if not keyword:
        raise HTTPException(status_code=400, detail="keyword must not be empty")

    try:
        current = await get_security_level(level_name, supabase)
        if keyword not in current.keywords:
            return {
                "status": "not_found",
                "level_name": level_name,
                "keyword": keyword,
                "total_keywords": len(current.keywords),
            }

        new_keywords = [k for k in current.keywords if k != keyword]

        await _upsert_level(supabase, {
            "name": current.name,
            "name_he": current.name_he,
            "level": current.level,
            "keywords": new_keywords,
            "description": current.description,
        })

        return {
            "status": "removed",
            "level_name": level_name,
            "keyword": keyword,
            "total_keywords": len(new_keywords),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to remove keyword: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/test-classification")
async def test_security_classification(
    request: ClassificationRequest,
    supabase=Depends(get_supabase_client),
) -> dict:
    """Test what security level a text would be classified as.

    Returns the HIGHEST matching level and all matched keywords per level.
    """
    try:
        try:
            levels_response = await supabase.table("security_levels").select("*").execute()
            levels = levels_response.data if levels_response.data else DEFAULT_SECURITY_LEVELS
        except Exception as e:
            logger.warning(f"Falling back to default levels: {e}")
            levels = DEFAULT_SECURITY_LEVELS

        text_lower = request.text.lower()
        matches = {}

        # Case-insensitive substring search — matches Hebrew + English equally.
        for level in levels:
            keywords = level.get("keywords") or []
            matching_keywords = [kw for kw in keywords if kw.lower() in text_lower]
            if matching_keywords:
                matches[level["name"]] = {
                    "matched_keywords": matching_keywords,
                    "match_count": len(matching_keywords),
                    "level": level.get("level", 0),
                }

        if matches:
            highest = max(matches.items(), key=lambda x: x[1]["level"])
            detected_level = highest[0]
            detected_level_num = highest[1]["level"]
        else:
            detected_level = "Unclassified"
            detected_level_num = 0

        return {
            "text_preview": request.text[:200] + ("..." if len(request.text) > 200 else ""),
            "detected_level": detected_level,
            "detected_level_number": detected_level_num,
            "matches": matches,
            "total_matched_levels": len(matches),
        }

    except Exception as e:
        logger.error(f"Failed to test classification: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/initialize-defaults")
async def initialize_default_levels(supabase=Depends(get_supabase_client)) -> dict:
    """Initialize / RESET security levels table to defaults.

    If the user has previously called `/save-as-defaults`, those user-saved
    levels are restored. Otherwise the built-in hardcoded defaults are used.
    """
    try:
        user_saved, saved_at = await _load_user_saved_defaults(supabase)
        effective = _effective_defaults_sync(user_saved)
        source = "user_saved" if user_saved else "built_in"

        for level_data in effective:
            # Strip DB-only fields before upsert
            payload = {k: v for k, v in level_data.items() if k not in ("id",)}
            await _upsert_level(supabase, payload)

        return {
            "status": "initialized",
            "source": source,
            "saved_at": saved_at,
            "levels_count": len(effective),
            "total_keywords": sum(len(lv.get("keywords", [])) for lv in effective),
        }

    except Exception as e:
        logger.error(f"Failed to initialize security levels: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/save-as-defaults")
async def save_current_as_defaults(supabase=Depends(get_supabase_client)) -> dict:
    """Snapshot the CURRENT security_levels table state as the user's saved
    defaults.

    From now on, /initialize-defaults will restore THIS snapshot instead of the
    built-in hardcoded defaults. Useful when the user has carefully curated
    their own keyword lists and wants `Reset` to bring them back to *this* state.
    """
    try:
        # Pull every level row from the live table.
        resp = await supabase.table("security_levels").select("*").order("level").execute()
        levels = resp.data or []
        if not levels:
            raise HTTPException(
                status_code=400,
                detail="security_levels table is empty - nothing to save. Add some keywords first.",
            )

        # Strip DB-managed fields (id, timestamps) before saving.
        cleaned = []
        for lv in levels:
            cleaned.append({
                "name": lv.get("name"),
                "name_he": lv.get("name_he"),
                "level": lv.get("level"),
                "keywords": lv.get("keywords") or [],
                "description": lv.get("description"),
            })

        now_iso = datetime.utcnow().isoformat()
        await _save_setting(supabase, USER_DEFAULTS_KEY, json.dumps(cleaned, ensure_ascii=False))
        await _save_setting(supabase, USER_DEFAULTS_TIMESTAMP_KEY, f'"{now_iso}"')

        return {
            "status": "saved",
            "saved_at": now_iso,
            "levels_count": len(cleaned),
            "total_keywords": sum(len(lv["keywords"]) for lv in cleaned),
            "message": (
                "Snapshot saved. Future 'Reset to defaults' will restore THIS state. "
                "To revert to built-in factory defaults, call /reset-saved-defaults."
            ),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to save as defaults: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/reset-saved-defaults")
async def reset_saved_defaults(supabase=Depends(get_supabase_client)) -> dict:
    """Forget the user-saved defaults. Future Resets will use built-in factory defaults.

    This does NOT touch the live security_levels table - only the snapshot.
    """
    try:
        await _save_setting(supabase, USER_DEFAULTS_KEY, "null")
        await _save_setting(supabase, USER_DEFAULTS_TIMESTAMP_KEY, "null")
        return {
            "status": "cleared",
            "message": "User-saved defaults removed. Reset will now restore built-in factory defaults.",
        }
    except Exception as e:
        logger.error(f"Failed to reset saved defaults: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/defaults-status")
async def get_defaults_status(supabase=Depends(get_supabase_client)) -> dict:
    """Tell the UI whether user-saved defaults exist and when they were saved.

    Used by the frontend to display a `Saved on YYYY-MM-DD HH:MM` indicator
    next to the Reset button.
    """
    try:
        user_saved, saved_at = await _load_user_saved_defaults(supabase)
        if user_saved:
            return {
                "has_user_defaults": True,
                "saved_at": saved_at,
                "levels_count": len(user_saved),
                "total_keywords": sum(len(lv.get("keywords") or []) for lv in user_saved),
                "source_for_reset": "user_saved",
            }
        return {
            "has_user_defaults": False,
            "saved_at": None,
            "levels_count": len(DEFAULT_SECURITY_LEVELS),
            "total_keywords": sum(len(lv["keywords"]) for lv in DEFAULT_SECURITY_LEVELS),
            "source_for_reset": "built_in",
        }
    except Exception as e:
        logger.error(f"Failed to get defaults status: {e}")
        raise HTTPException(status_code=500, detail=str(e))

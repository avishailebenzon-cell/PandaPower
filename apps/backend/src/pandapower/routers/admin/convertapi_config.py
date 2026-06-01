"""Admin config for ConvertAPI CV text extraction.

Endpoints:
  POST /admin/convertapi/configure         - save secret / mode / ocr languages
  GET  /admin/convertapi/status            - enabled, mode, has_secret, credits
  POST /admin/convertapi/test              - validate the secret
  POST /admin/convertapi/reprocess-failed  - flip failed CVs back to 'pending'
"""

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from pandapower.core.supabase import get_supabase_client
from pandapower.integrations.convertapi_client import (
    ConvertApiClient,
    bust_config_cache,
    get_convertapi_config,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin/convertapi", tags=["admin-convertapi"])


async def _upsert(sb, key: str, value: str) -> None:
    await sb.table("system_settings").upsert(
        {"setting_key": key, "setting_value": value, "updated_at": datetime.utcnow().isoformat()},
        on_conflict="setting_key",
    ).execute()


class ConfigureRequest(BaseModel):
    secret: Optional[str] = None
    mode: Optional[str] = None            # "always" | "fallback"
    ocr_languages: Optional[str] = None   # e.g. "en,he"
    enabled: Optional[bool] = None


@router.post("/configure")
async def configure(req: ConfigureRequest) -> dict:
    sb = await get_supabase_client()

    if req.secret:
        secret = req.secret.strip()
        # Validate the secret before storing.
        client = ConvertApiClient(secret)
        try:
            await client.get_user()
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"ConvertAPI rejected the secret: {e}")
        finally:
            await client.close()
        await _upsert(sb, "convertapi.secret", secret)

    if req.mode:
        if req.mode not in ("always", "fallback"):
            raise HTTPException(status_code=400, detail="mode must be 'always' or 'fallback'")
        await _upsert(sb, "convertapi.mode", req.mode)
    if req.ocr_languages:
        await _upsert(sb, "convertapi.ocr_languages", req.ocr_languages)
    if req.enabled is not None:
        await _upsert(sb, "convertapi.enabled", "true" if req.enabled else "false")

    bust_config_cache()
    return {"status": "configured"}


@router.get("/status")
async def status() -> dict:
    sb = await get_supabase_client()
    cfg = await get_convertapi_config(sb)
    has_secret = bool(cfg.get("secret"))

    credits = None
    if has_secret:
        client = ConvertApiClient(cfg["secret"])
        try:
            user = await client.get_user()
            credits = user.get("SecondsLeft") or user.get("ConversionsLeft") or user.get("CreditsLeft")
        except Exception as e:
            logger.debug(f"convertapi status probe failed: {e}")
        finally:
            await client.close()

    return {
        "enabled": bool(cfg.get("enabled")),
        "mode": cfg.get("mode"),
        "ocr_languages": cfg.get("ocr_languages"),
        "has_secret": has_secret,
        "credits_remaining": credits,
    }


@router.post("/test")
async def test() -> dict:
    sb = await get_supabase_client()
    cfg = await get_convertapi_config(sb)
    if not cfg.get("secret"):
        raise HTTPException(status_code=400, detail="No ConvertAPI secret configured")
    client = ConvertApiClient(cfg["secret"])
    try:
        user = await client.get_user()
        return {"status": "ok", "account": user.get("FullName") or user.get("Email") or "valid"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Test failed: {e}")
    finally:
        await client.close()


class ReprocessRequest(BaseModel):
    limit: int = 500


@router.post("/reprocess-failed")
async def reprocess_failed(req: ReprocessRequest) -> dict:
    """Flip failed CVs back to 'pending' so the always-on parse stage re-extracts
    them via ConvertAPI. Returns how many were reset."""
    sb = await get_supabase_client()
    limit = max(1, min(req.limit, 5000))
    try:
        # Fetch the newest failed CV ids (bounded).
        resp = await sb.table("cv_files").select("id").eq(
            "parse_status", "failed"
        ).order("created_at", desc=True).limit(limit).execute()
        ids = [r["id"] for r in (resp.data or [])]
        if not ids:
            return {"status": "ok", "reset": 0, "note": "no failed CVs found"}

        await sb.table("cv_files").update(
            {"parse_status": "pending", "parse_error": None}
        ).in_("id", ids).execute()

        return {"status": "ok", "reset": len(ids),
                "note": "תהליך ה-parse יעבד אותם מחדש דרך ConvertAPI בדקות הקרובות"}
    except Exception as e:
        logger.error(f"reprocess-failed failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

"""ConvertAPI integration for CV text extraction.

ConvertAPI (convertapi.com) is a managed document-conversion service with proper
OCR and broad format coverage — no local system binaries (tesseract / libreoffice).
We route CV text extraction through it because the local extractor stack fails on
scanned/image PDFs, legacy .doc, and image CVs on Render.

Config (env first, then system_settings, cached ~5 min):
  CONVERTAPI_SECRET (env)  OR  system_settings: convertapi.secret
  convertapi.enabled   - "true"/"false" (default: enabled if a secret exists)
  convertapi.mode      - "always" | "fallback"  (default: "always")
  convertapi.ocr_languages - e.g. "en,he" (default)
"""

from __future__ import annotations

import asyncio
import base64
import logging
import time
from typing import Optional

import httpx

from pandapower.core.config import settings

logger = logging.getLogger(__name__)

CONVERTAPI_BASE = "https://v2.convertapi.com"
_TIMEOUT = 120.0

# Formats ConvertAPI can take to /txt. Images go through OCR automatically.
_FORMAT_MAP = {
    "pdf": "pdf",
    "docx": "docx",
    "doc": "doc",
    "rtf": "rtf",
    "odt": "odt",
    "txt": "txt",
    "jpg": "jpg",
    "jpeg": "jpg",
    "png": "png",
    "tiff": "tiff",
    "tif": "tiff",
    "webp": "webp",
}

# Sources for which we enable OCR (scanned/image content).
_OCR_SOURCES = {"pdf", "jpg", "png", "tiff", "webp"}


def convertapi_src_token(file_format: str, filename: Optional[str] = None) -> Optional[str]:
    """Map our detected format (or filename extension) to a ConvertAPI source token."""
    if file_format and file_format in _FORMAT_MAP:
        return _FORMAT_MAP[file_format]
    if filename and "." in filename:
        ext = filename.rsplit(".", 1)[-1].lower()
        if ext in _FORMAT_MAP:
            return _FORMAT_MAP[ext]
    return None


class ConvertApiClient:
    """Thin async client over the ConvertAPI REST API."""

    def __init__(self, secret: str):
        self.secret = secret
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=_TIMEOUT)
        return self._client

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def to_text(
        self, content: bytes, src_format: str, ocr_languages: str = "en,he",
        max_retries: int = 3,
    ) -> str:
        """Convert a document/image to plain text. Raises on failure."""
        client = await self._get_client()
        url = f"{CONVERTAPI_BASE}/convert/{src_format}/to/txt"
        params = {"Secret": self.secret, "StoreFile": "false"}
        if src_format in _OCR_SOURCES and ocr_languages:
            # Presence of OcrLanguage enables OCR on scanned/image inputs.
            params["OcrLanguage"] = ocr_languages

        files = {"File": (f"cv.{src_format}", content)}

        last_err: Optional[Exception] = None
        for attempt in range(max_retries):
            try:
                resp = await client.post(url, params=params, files=files)
                if resp.status_code >= 500:
                    last_err = RuntimeError(f"ConvertAPI {resp.status_code}: {resp.text[:200]}")
                    await asyncio.sleep(2 ** attempt)
                    continue
                if resp.status_code >= 400:
                    raise RuntimeError(f"ConvertAPI {resp.status_code}: {resp.text[:300]}")

                data = resp.json()
                out_files = data.get("Files") or []
                if not out_files:
                    raise RuntimeError(f"ConvertAPI returned no files: {str(data)[:200]}")

                file_data = out_files[0].get("FileData")
                if file_data:
                    return base64.b64decode(file_data).decode("utf-8", errors="replace")

                # Fallback: response provided a URL instead of inline data.
                file_url = out_files[0].get("Url")
                if file_url:
                    r2 = await client.get(file_url)
                    return r2.text
                raise RuntimeError("ConvertAPI response missing FileData/Url")

            except httpx.TimeoutException as e:
                last_err = e
                await asyncio.sleep(2 ** attempt)
                continue

        raise RuntimeError(f"ConvertAPI conversion failed after {max_retries} attempts: {last_err}")

    async def html_to_pdf(self, html: str, max_retries: int = 3) -> bytes:
        """Render an HTML document to a PDF and return the raw PDF bytes.

        Used to produce the branded "Panda-Tech format" CV from an HTML
        template. ConvertAPI's html/to/pdf runs a Chromium engine, so RTL and
        Hebrew web fonts render correctly with no local system libraries. Raises
        on failure so the caller can fall back / surface the error.
        """
        client = await self._get_client()
        url = f"{CONVERTAPI_BASE}/convert/html/to/pdf"
        params = {"Secret": self.secret, "StoreFile": "false"}
        files = {"File": ("cv.html", html.encode("utf-8"), "text/html")}

        last_err: Optional[Exception] = None
        for attempt in range(max_retries):
            try:
                resp = await client.post(url, params=params, files=files)
                if resp.status_code >= 500:
                    last_err = RuntimeError(f"ConvertAPI {resp.status_code}: {resp.text[:200]}")
                    await asyncio.sleep(2 ** attempt)
                    continue
                if resp.status_code >= 400:
                    raise RuntimeError(f"ConvertAPI {resp.status_code}: {resp.text[:300]}")

                data = resp.json()
                out_files = data.get("Files") or []
                if not out_files:
                    raise RuntimeError(f"ConvertAPI returned no files: {str(data)[:200]}")

                file_data = out_files[0].get("FileData")
                if file_data:
                    return base64.b64decode(file_data)

                file_url = out_files[0].get("Url")
                if file_url:
                    r2 = await client.get(file_url)
                    return r2.content
                raise RuntimeError("ConvertAPI response missing FileData/Url")

            except httpx.TimeoutException as e:
                last_err = e
                await asyncio.sleep(2 ** attempt)
                continue

        raise RuntimeError(f"ConvertAPI html→pdf failed after {max_retries} attempts: {last_err}")

    async def get_user(self) -> dict:
        """Account info (used to validate the secret + report remaining credits)."""
        client = await self._get_client()
        resp = await client.get(f"{CONVERTAPI_BASE}/user", params={"Secret": self.secret})
        if resp.status_code >= 400:
            raise RuntimeError(f"ConvertAPI /user {resp.status_code}: {resp.text[:200]}")
        return resp.json()

    async def get_usage(self) -> dict:
        """Normalized usage snapshot for the conversion plan.

        ConvertAPI's /user returns (for conversion-based plans):
          ConversionsTotal     – plan limit for the period (e.g. 15000)
          ConversionsConsumed  – used so far (can exceed total → overage)
          SecondsLeft          – negative when over (for second-based plans)

        Returns:
          {
            "total": int|None,        # plan limit
            "consumed": int,          # used so far
            "remaining": int|None,    # total - consumed (negative = overage)
            "used_pct": float|None,   # consumed / total (1.0 == exactly at limit)
            "over_limit": bool,       # consumed >= total
          }
        """
        user = await self.get_user()
        total = user.get("ConversionsTotal")
        consumed = user.get("ConversionsConsumed")
        if consumed is None:
            # Some plans report only seconds; derive consumed from total - left.
            secs_left = user.get("SecondsLeft")
            if total is not None and secs_left is not None:
                consumed = total - secs_left
            else:
                consumed = 0
        remaining = (total - consumed) if total is not None else None
        used_pct = (consumed / total) if (total and total > 0) else None
        over_limit = bool(total is not None and consumed >= total)
        return {
            "total": total,
            "consumed": consumed,
            "remaining": remaining,
            "used_pct": used_pct,
            "over_limit": over_limit,
        }


# ---------------------------------------------------------------------------
# Cached config (env first, then system_settings).
# ---------------------------------------------------------------------------

_CONFIG_CACHE: dict = {}
_CONFIG_CACHE_AT: float = 0.0
_CONFIG_TTL = 300.0  # seconds


def bust_config_cache() -> None:
    global _CONFIG_CACHE_AT
    _CONFIG_CACHE_AT = 0.0


async def get_convertapi_config(sb=None) -> dict:
    """Return {secret, enabled, mode, ocr_languages}. Cached ~5 min.

    Never raises — on any failure returns a disabled config so the caller falls
    back to local extraction.
    """
    global _CONFIG_CACHE, _CONFIG_CACHE_AT
    now = time.monotonic()
    if _CONFIG_CACHE and (now - _CONFIG_CACHE_AT) < _CONFIG_TTL:
        return _CONFIG_CACHE

    cfg = {
        "secret": settings.CONVERTAPI_SECRET or None,
        "enabled": None,
        "mode": "always",
        "ocr_languages": "en,he",
        # Hard stop: once consumed/total reaches this fraction we STOP using
        # ConvertAPI (fall back to free local extractors) to avoid overage
        # charges. 0.98 leaves a small safety margin to cover the usage-cache
        # lag. Set to a value >1 to allow overage on purpose.
        "max_usage_pct": 0.98,
        # Early-warning threshold: email the admin once usage crosses this
        # fraction, BEFORE the hard stop, so there's time to upgrade the plan.
        "warn_usage_pct": 0.90,
        # $ per conversion, for the cost dashboard. Set to your real plan price
        # (plan price / monthly conversions) via convertapi.cost_per_conversion.
        "cost_per_conversion": 0.005,
    }
    try:
        if sb is None:
            from pandapower.core.supabase import get_supabase_client
            sb = await get_supabase_client()
        r = await sb.table("system_settings").select(
            "setting_key, setting_value"
        ).like("setting_key", "convertapi.%").execute()
        for row in (r.data or []):
            field = (row.get("setting_key") or "").split(".", 1)[-1]
            val = row.get("setting_value")
            if isinstance(val, str):
                val = val.strip().strip('"').strip()
            if not val or val == "null":
                continue
            if field == "secret":
                cfg["secret"] = val
            elif field == "enabled":
                cfg["enabled"] = val.lower() != "false"
            elif field == "mode":
                cfg["mode"] = val
            elif field == "ocr_languages":
                cfg["ocr_languages"] = val
            elif field == "max_usage_pct":
                try:
                    cfg["max_usage_pct"] = float(val)
                except (TypeError, ValueError):
                    pass
            elif field == "warn_usage_pct":
                try:
                    cfg["warn_usage_pct"] = float(val)
                except (TypeError, ValueError):
                    pass
            elif field == "cost_per_conversion":
                try:
                    cfg["cost_per_conversion"] = float(val)
                except (TypeError, ValueError):
                    pass
    except Exception as e:
        logger.debug(f"[convertapi] config read failed (non-fatal): {e}")

    # enabled defaults to True when a secret exists, unless explicitly disabled.
    if cfg["enabled"] is None:
        cfg["enabled"] = bool(cfg["secret"])

    _CONFIG_CACHE = cfg
    _CONFIG_CACHE_AT = now
    return cfg


# ---------------------------------------------------------------------------
# Usage budget guard (avoid plan overage).
# ---------------------------------------------------------------------------

_USAGE_CACHE: Optional[dict] = None
_USAGE_CACHE_AT: float = 0.0
_USAGE_TTL = 60.0  # seconds — short so we react quickly as the limit nears.


def bust_usage_cache() -> None:
    global _USAGE_CACHE_AT
    _USAGE_CACHE_AT = 0.0


async def get_convertapi_usage(secret: str, *, force: bool = False) -> Optional[dict]:
    """Return a normalized usage snapshot, cached ~60s. None on failure.

    Cached so we don't hit /user on every single CV — at most once a minute.
    """
    global _USAGE_CACHE, _USAGE_CACHE_AT
    now = time.monotonic()
    if not force and _USAGE_CACHE is not None and (now - _USAGE_CACHE_AT) < _USAGE_TTL:
        return _USAGE_CACHE

    client = ConvertApiClient(secret)
    try:
        usage = await client.get_usage()
    except Exception as e:
        logger.warning(f"[convertapi] usage check failed (assuming OK): {e}")
        return None
    finally:
        await client.close()

    _USAGE_CACHE = usage
    _USAGE_CACHE_AT = now
    return usage


async def convertapi_within_budget(cfg: dict) -> tuple[bool, Optional[dict]]:
    """Decide whether ConvertAPI may be used without exceeding the plan.

    Returns (allowed, usage_snapshot). Fails OPEN (allowed=True) if we can't
    read usage — we never want a transient usage-check error to halt the whole
    pipeline. The hard protection is the explicit over-limit check below.
    """
    secret = cfg.get("secret")
    if not secret:
        return False, None

    usage = await get_convertapi_usage(secret)
    if usage is None:
        return True, None  # fail open on read error

    max_pct = cfg.get("max_usage_pct", 0.98)
    used_pct = usage.get("used_pct")
    if used_pct is None:
        # No total reported → can't reason about a percentage; allow.
        return True, usage

    allowed = used_pct < max_pct
    return allowed, usage

"""Shared "render + deliver Panda-Tech CV" primitives used by Elad and Pandi.

Both agents end their flow the same way: once a client is interested in a
specific candidate, we render the candidate's structured data into the branded
**Panda-Tech format** PDF and deliver that file (never the raw upload) over
WhatsApp. This module owns the two reusable, *candidate-centric* steps so the
logic lives in one place:

  • :func:`render_and_upload_cv` — build HTML → ConvertAPI ``html/to/pdf`` →
    upload to Supabase storage. No ``matches`` dependency.
  • :func:`send_cv_file_via` — sign the stored object and push it to a chat via
    an already-configured Green API client.

Elad layers its human-approval gate and ``matches.formatted_cv_*`` bookkeeping
on top of these (see :mod:`pandapower.agents.recruiter_chat.cv_formatter` and
``elad_flow.send_cv_file``). Pandi calls them directly (auto-send).
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


async def render_and_upload_cv(
    supabase,
    cand_row: dict,
    iron_number: str,
    *,
    folder: str | None = None,
) -> dict:
    """Render the Panda-Tech CV for a candidate row and upload it to storage.

    Args:
        supabase: async Supabase client.
        cand_row: candidate fields consumed by ``build_cv_html`` (name,
            extracted_from_cv, key_skills, experiences, top_education,
            clearance_level, years_of_experience, ...).
        iron_number: the client-facing identifier shown on the CV (Elad's
            ``iron_number`` / Pandi's ``candidate_number``). Also used to name
            the stored object.
        folder: storage sub-folder (default: the iron number). Pass the
            candidate id to keep one stable path per candidate.

    Returns:
        ``{"ok": bool, "path": str|None, "error": str|None}``.
    """
    # Imported lazily to avoid a circular import at module load time
    # (cv_formatter imports elad_flow).
    from pandapower.agents.recruiter_chat.cv_formatter import build_cv_html, _load_branding

    branding = await _load_branding(supabase)
    html_doc = build_cv_html(cand_row or {}, iron_number or "", branding)

    from pandapower.integrations.convertapi_client import (
        ConvertApiClient,
        get_convertapi_config,
    )
    cfg = await get_convertapi_config(supabase)
    secret = cfg.get("secret")
    if not secret:
        return {"ok": False, "path": None, "error": "ConvertAPI secret not configured"}

    client = ConvertApiClient(secret)
    try:
        pdf_bytes = await client.html_to_pdf(html_doc)
    except Exception as e:
        logger.error(f"[cv_delivery] render failed for {iron_number}: {e}")
        return {"ok": False, "path": None, "error": f"render failed: {e}"}
    finally:
        await client.close()

    safe_iron = (iron_number or "cv").replace("/", "_")
    storage_path = f"formatted/{folder or safe_iron}/panda_cv_{safe_iron}.pdf"
    try:
        from pandapower.integrations.supabase_storage import SupabaseStorageManager
        storage = SupabaseStorageManager(supabase)
        try:
            await storage.supabase.storage.from_(storage.bucket_name).remove([storage_path])
        except Exception:
            pass  # first generation — nothing to remove
        await storage.upload_file(storage_path, pdf_bytes, "application/pdf")
    except Exception as e:
        logger.error(f"[cv_delivery] upload failed for {iron_number}: {e}")
        return {"ok": False, "path": None, "error": f"upload failed: {e}"}

    return {"ok": True, "path": storage_path, "error": None}


async def signed_cv_url(supabase, storage_path: str) -> str | None:
    """Create a 7-day signed URL for a stored CV object (or None on failure)."""
    if not storage_path:
        return None
    try:
        from pandapower.integrations.supabase_storage import SupabaseStorageManager
        storage = SupabaseStorageManager(supabase)
        return await storage.create_signed_url(storage_path, expires_in_seconds=604800)
    except Exception as e:
        logger.error(f"[cv_delivery] signed URL failed for {storage_path}: {e}")
        return None


async def send_cv_file_via(
    supabase,
    green_api,
    chat_id: str,
    storage_path: str,
    filename: str,
    *,
    signed_url: str | None = None,
) -> bool:
    """Sign a stored CV object and send it to a chat via a Green API client.

    The caller owns the Green API client (so per-agent credentials are honoured)
    and the resolved ``chat_id``. Pass ``signed_url`` to reuse an already-signed
    URL (e.g. when the caller also records a file message); otherwise we sign.
    """
    if not (green_api and chat_id and storage_path):
        return False
    if signed_url is None:
        signed_url = await signed_cv_url(supabase, storage_path)
    if not signed_url:
        return False

    res = await green_api.send_file(chat_id, signed_url, filename or "PandaTech_CV.pdf")
    return bool(res.get("success"))

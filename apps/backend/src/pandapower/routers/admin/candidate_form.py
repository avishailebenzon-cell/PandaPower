"""Admin routes for the candidate-form → Pipedrive note sync.

The sync normally runs on a nightly, self-gated schedule. These endpoints let
an admin trigger it on demand and run a one-shot "newest N rows only" pass
(used to back-fill the most recent submissions after the job was dormant).
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel

from pandapower.core.supabase import get_supabase_client
from pandapower.workers.candidate_form_sync import (
    FORCE_RUN_KEY,
    PROCESS_NEWEST_KEY,
    sync_candidate_form,
)
from pandapower.workers.tasks import _set_setting

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin/candidate-form", tags=["admin", "candidate-form"])


class RunRequest(BaseModel):
    # If set, process ONLY the newest N rows, then skip the older backlog.
    newest: Optional[int] = None


@router.post("/run")
async def run_now(req: RunRequest):
    """Run the candidate-form sync immediately (bypasses the night/2-day gate).

    Pass {"newest": 10} to process only the 10 most recent submissions.
    Requires Pipedrive API credit; returns the sync result dict.
    """
    sb = await get_supabase_client()
    await _set_setting(sb, FORCE_RUN_KEY, "true")
    if req.newest and req.newest > 0:
        await _set_setting(sb, PROCESS_NEWEST_KEY, str(int(req.newest)))
    result = await sync_candidate_form()
    return result

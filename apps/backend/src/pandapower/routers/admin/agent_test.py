"""Agent test conversations — inject a deliberate TEST match for Tal / Elad.

The operator enters a test phone number (simulating a candidate for Tal, or a
client for Elad) plus the match details. We insert a self-contained TEST row
into the matches table (candidate_id / job_id stay NULL; the phone + display
fields live on the match via is_test / test_phone / test_meta). The row then
appears in the agent's normal queue and flows through Activate → conversation
exactly like a real match — the only difference is the WhatsApp goes to the
test number.

Pandi is intentionally excluded: she receives inbound external messages, so a
test is just messaging her number directly.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from pandapower.core.supabase import get_supabase_client

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin/agent-test", tags=["admin", "test"])

VALID_RECRUITERS = ("tal", "elad")
STATE_BY_RECRUITER = {"tal": "sent_to_tal", "elad": "sent_to_elad"}


class CreateTestMatchRequest(BaseModel):
    recruiter: str = Field(..., description="tal or elad")
    phone: str = Field(..., description="Test destination phone (candidate for Tal, client for Elad)")
    contact_name: str = Field(..., min_length=1, max_length=120)
    job_title: str = Field(..., min_length=1, max_length=200)
    # For the Elad "bypass-Tal" flow: the real candidate being presented to the
    # client. Tal's counterpart IS the candidate, so she leaves this empty and
    # the candidate is taken from contact_name. Elad's counterpart is the client,
    # so the candidate is a separate person carried here.
    candidate_name: Optional[str] = Field(None, max_length=120)
    organization_name: Optional[str] = Field(None, max_length=200)
    job_location: Optional[str] = Field(None, max_length=200)
    job_security_clearance: Optional[str] = Field(None, max_length=80)
    candidate_clearance: Optional[str] = Field(None, max_length=80)
    job_description: Optional[str] = Field(None, max_length=4000)
    job_qualifications: Optional[str] = Field(None, max_length=4000)
    match_score: int = Field(90, ge=0, le=100)
    match_reasoning: Optional[str] = Field(None, max_length=4000)


class CreateTestMatchResponse(BaseModel):
    match_id: str
    recruiter: str
    state: str
    queue_path: str  # where the row now appears in the UI


@router.post("/create-match", response_model=CreateTestMatchResponse)
async def create_test_match(
    body: CreateTestMatchRequest,
    supabase=Depends(get_supabase_client),
) -> CreateTestMatchResponse:
    if body.recruiter not in VALID_RECRUITERS:
        raise HTTPException(status_code=400, detail="recruiter must be 'tal' or 'elad'")

    from pandapower.core import phone as phone_utils

    if not phone_utils.is_valid(body.phone):
        raise HTTPException(
            status_code=400,
            detail=(
                "מספר טלפון לא תקין. הזינו מספר ישראלי תקין, למשל 050-1234567 "
                "או +972501234567 (השליחה תיכשל בשקט אם המספר חסר ספרות)."
            ),
        )
    # Store the canonical international form so delivery resolves consistently.
    digits = phone_utils.to_international(body.phone)

    state = STATE_BY_RECRUITER[body.recruiter]
    test_meta = {
        "contact_name": body.contact_name,
        "candidate_name": body.candidate_name,
        "job_title": body.job_title,
        "organization_name": body.organization_name,
        "job_location": body.job_location,
        "job_security_clearance": body.job_security_clearance,
        "candidate_clearance": body.candidate_clearance,
        "job_description": body.job_description,
        "job_qualifications": body.job_qualifications,
    }

    row = {
        "current_state": state,
        "match_score": round(body.match_score / 100.0, 2),
        "match_reasoning": body.match_reasoning or f"שורת בדיקה עבור {body.recruiter}",
        "matched_by_agent_code": "test",
        "is_valid": True,
        "is_test": True,
        "test_phone": digits,
        "test_meta": test_meta,
        "created_at": datetime.utcnow().isoformat(),
        "updated_at": datetime.utcnow().isoformat(),
    }

    try:
        res = await supabase.table("matches").insert(row).execute()
        if not res.data:
            raise HTTPException(status_code=500, detail="Insert returned no row")
        match_id = res.data[0]["id"]
    except HTTPException:
        raise
    except Exception as e:
        msg = str(e)
        logger.error(f"Failed to create test match: {msg}", exc_info=True)
        if "is_test" in msg or "test_phone" in msg or "test_meta" in msg or "PGRST204" in msg:
            raise HTTPException(
                status_code=500,
                detail="חסרות עמודות הבדיקה (is_test/test_phone/test_meta). יש להריץ את מיגרציה 015.",
            )
        raise HTTPException(status_code=500, detail=f"Failed to create test match: {msg[:200]}")

    queue_path = f"/recruiting/{body.recruiter}"
    return CreateTestMatchResponse(
        match_id=str(match_id),
        recruiter=body.recruiter,
        state=state,
        queue_path=queue_path,
    )


# States that represent a match Carmit has already cleared. For the Elad test
# flow we let the operator pick one of these and hand it straight to Elad,
# bypassing Tal (we pretend Tal approved it too) — so they can test Elad's
# client-facing conversation against a real candidate+job from the pool.
APPROVED_SOURCE_STATES = ("carmit_approved", "tal_approved", "sent_to_tal", "tal_conversation")


class ApprovedMatchItem(BaseModel):
    match_id: str
    candidate_name: str
    candidate_clearance: Optional[str] = None
    job_title: str
    organization_name: Optional[str] = None
    job_location: Optional[str] = None
    job_security_clearance: Optional[str] = None
    job_description: Optional[str] = None
    job_qualifications: Optional[str] = None
    match_score: int = 0  # 0-100
    match_reasoning: Optional[str] = None
    current_state: str


@router.get("/approved-matches", response_model=list[ApprovedMatchItem])
async def list_approved_matches(
    limit: int = 50,
    supabase=Depends(get_supabase_client),
) -> list[ApprovedMatchItem]:
    """Real matches Carmit already approved — the pool Elad can test against.

    The operator picks one here, attaches a dummy client phone, and we seed a
    test row for Elad from this match's real candidate + job details.
    """
    limit = max(1, min(limit, 100))
    try:
        res = await supabase.table("matches").select(
            "id, current_state, match_score, match_reasoning, "
            "candidates(name, clearance_level), "
            "jobs(job_title, job_description, job_qualifications, "
            "job_location, job_security_clearance, organization_name)"
        ).in_("current_state", list(APPROVED_SOURCE_STATES)).eq(
            "is_valid", True
        ).order("created_at", desc=True).limit(limit).execute()
    except Exception as e:
        logger.error(f"Failed to list approved matches: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="שליפת ההתאמות שכרמית אישרה נכשלה")

    items: list[ApprovedMatchItem] = []
    for row in res.data or []:
        # Skip test rows — only real Carmit-approved matches make sense to seed from.
        cand = row.get("candidates") or {}
        job = row.get("jobs") or {}
        if not isinstance(cand, dict) or not isinstance(job, dict):
            continue
        name = cand.get("name")
        title = job.get("job_title")
        if not name or not title:
            continue
        try:
            score = int(round(float(row.get("match_score") or 0) * 100))
        except Exception:
            score = 0
        items.append(
            ApprovedMatchItem(
                match_id=str(row["id"]),
                candidate_name=name,
                candidate_clearance=cand.get("clearance_level"),
                job_title=title,
                organization_name=job.get("organization_name"),
                job_location=job.get("job_location"),
                job_security_clearance=job.get("job_security_clearance"),
                job_description=job.get("job_description"),
                job_qualifications=job.get("job_qualifications"),
                match_score=score,
                match_reasoning=row.get("match_reasoning"),
                current_state=row.get("current_state", "unknown"),
            )
        )
    return items

"""
Match History Router
Provides endpoints for viewing match state machine history and journey
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from datetime import datetime
from typing import List, Optional, Any

from pandapower.core.supabase import get_supabase_client

router = APIRouter(prefix="/admin/matches", tags=["admin"])


class StateHistoryEntry(BaseModel):
    from_state: str
    to_state: str
    created_at: str
    details: Optional[dict] = None


class MatchHistoryResponse(BaseModel):
    matchId: str
    candidateName: str
    jobTitle: str
    currentState: str
    stateHistory: List[StateHistoryEntry]


class StateTransitionInfo(BaseModel):
    state: str
    label: str
    icon: str
    description: str
    timestamp: Optional[str] = None
    isCompleted: bool
    isCurrent: bool


@router.get("/{match_id}/history", response_model=MatchHistoryResponse)
async def get_match_history(match_id: str, db: Session = Depends(get_db)):
    """
    Get complete state history for a match
    Returns the journey of the match through all states
    """
    
    # Get match details
    match = db.execute(
        select(Matches).where(Matches.id == match_id)
    ).scalar_one_or_none()
    
    if not match:
        raise HTTPException(status_code=404, detail="Match not found")
    
    # Get candidate name
    candidate = db.execute(
        select(Candidates).where(Candidates.id == match.candidate_id)
    ).scalar_one_or_none()
    candidate_name = candidate.name if candidate else "Unknown"
    
    # Get job title
    job = db.execute(
        select(Jobs).where(Jobs.id == match.job_id)
    ).scalar_one_or_none()
    job_title = job.title if job else "Unknown"
    
    # Get state history (ordered by timestamp)
    state_history = db.execute(
        select(MatchStateHistory)
        .where(MatchStateHistory.match_id == match_id)
        .order_by(MatchStateHistory.created_at.asc())
    ).scalars().all()
    
    # Format state history entries
    history_entries = []
    for entry in state_history:
        history_entries.append(
            StateHistoryEntry(
                from_state=entry.from_state,
                to_state=entry.to_state,
                created_at=entry.created_at.isoformat() if entry.created_at else "",
                details=entry.details or {}
            )
        )
    
    return MatchHistoryResponse(
        matchId=match_id,
        candidateName=candidate_name,
        jobTitle=job_title,
        currentState=match.current_state or "found",
        stateHistory=history_entries
    )


@router.get("/{match_id}/state-summary")
async def get_match_state_summary(match_id: str, db: Session = Depends(get_db)):
    """
    Get summary of match state with next expected transitions
    """
    
    match = db.execute(
        select(Matches).where(Matches.id == match_id)
    ).scalar_one_or_none()
    
    if not match:
        raise HTTPException(status_code=404, detail="Match not found")
    
    current_state = match.current_state or "found"
    
    # Define state machine flow
    STATE_FLOW = {
        "found": {
            "label": "התאמה נמצאה",
            "icon": "🔍",
            "next": ["carmit_approved", "carmit_rejected"],
            "description": "הסוכן מצא התאמה פוטנציאלית"
        },
        "carmit_approved": {
            "label": "אושרה על ידי כרמית",
            "icon": "✅",
            "next": ["sent_to_tal"],
            "description": "כרמית אישרה את ההתאמה לאחר בדיקת 5 שערים"
        },
        "carmit_rejected": {
            "label": "נדחתה על ידי כרמית",
            "icon": "❌",
            "next": [],
            "description": "כרמית דחתה את ההתאמה"
        },
        "sent_to_tal": {
            "label": "הועברה לטל",
            "icon": "📞",
            "next": ["tal_conversation"],
            "description": "ההתאמה הועברה לטל לבדיקה ראשונית"
        },
        "tal_conversation": {
            "label": "שיחה עם טל",
            "icon": "💬",
            "next": ["tal_approved", "tal_rejected"],
            "description": "טל מנהלת שיחה עם המועמד"
        },
        "tal_approved": {
            "label": "אושר על ידי טל",
            "icon": "👍",
            "next": ["sent_to_elad"],
            "description": "טל אישרה את המועמד"
        },
        "tal_rejected": {
            "label": "נדחה על ידי טל",
            "icon": "❌",
            "next": [],
            "description": "טל דחתה את המועמד"
        },
        "sent_to_elad": {
            "label": "הועבר לאלעד",
            "icon": "👤",
            "next": ["elad_conversation"],
            "description": "כרמית העבירה את ההתאמה לאלעד"
        },
        "elad_conversation": {
            "label": "שיחה עם אלעד",
            "icon": "💬",
            "next": ["offer_sent"],
            "description": "אלעד מנהל שיחה בנוגע להעברה ללקוח"
        },
        "offer_sent": {
            "label": "הצעה נשלחה ללקוח",
            "icon": "🤝",
            "next": ["hired", "placement_failed"],
            "description": "אלעד שלח את המועמד ללקוח"
        },
        "hired": {
            "label": "התקבל לעבודה!",
            "icon": "💼",
            "next": [],
            "description": "המועמד התקבל לעבודה"
        },
        "placement_failed": {
            "label": "ממקום נכשל",
            "icon": "❌",
            "next": [],
            "description": "הממקום נכשל"
        }
    }
    
    current_info = STATE_FLOW.get(current_state, {})
    next_states = current_info.get("next", [])
    
    return {
        "matchId": match_id,
        "currentState": current_state,
        "stateLabel": current_info.get("label", "Unknown"),
        "stateIcon": current_info.get("icon", "❓"),
        "stateDescription": current_info.get("description", ""),
        "nextStates": next_states,
        "isTerminal": len(next_states) == 0,
        "isFinal": current_state in ["hired", "placement_failed", "carmit_rejected", "tal_rejected"]
    }


@router.post("/{match_id}/transition")
async def record_state_transition(
    match_id: str,
    to_state: str,
    details: Optional[dict] = None,
    db: Session = Depends(get_db)
):
    """
    Record a state transition for a match
    (Used internally by workflow endpoints)
    """
    
    match = db.execute(
        select(Matches).where(Matches.id == match_id)
    ).scalar_one_or_none()
    
    if not match:
        raise HTTPException(status_code=404, detail="Match not found")
    
    from_state = match.current_state or "found"
    
    # Create state history entry
    history_entry = MatchStateHistory(
        match_id=match_id,
        from_state=from_state,
        to_state=to_state,
        details=details or {},
        created_at=datetime.utcnow()
    )
    
    db.add(history_entry)
    
    # Update match current state
    match.current_state = to_state
    
    db.commit()
    db.refresh(match)
    
    return {
        "success": True,
        "matchId": match_id,
        "fromState": from_state,
        "toState": to_state,
        "timestamp": history_entry.created_at.isoformat()
    }

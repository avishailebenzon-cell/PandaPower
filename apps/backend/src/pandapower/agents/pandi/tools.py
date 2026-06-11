"""
Pandi Tools - LLM tool definitions for candidate search and management
"""

from typing import Any


def get_pandi_tools() -> list:
    """
    Get list of tools available to Pandi LLM.

    Returns:
        List of tool definitions for Claude
    """
    return [
        {
            "name": "update_job_context",
            "description": "Update the job requirements based on what the client has shared. Merge with existing context — don't overwrite if no new info.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "Job title (e.g., Backend Developer, Systems Engineer)",
                    },
                    "qualifications": {
                        "type": "string",
                        "description": "Required qualifications, experience, and skills",
                    },
                    "location": {
                        "type": "string",
                        "description": "Work location or remote preference",
                    },
                    "security_clearance": {
                        "type": "string",
                        "enum": [
                            "none",
                            "confidential",
                            "secret",
                            "top_secret",
                            "highest",
                            "unknown",
                        ],
                        "description": "Required security clearance level",
                    },
                    "must_have": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of must-have skills or requirements",
                    },
                    "nice_to_have": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of nice-to-have skills",
                    },
                    "soft_skills_notes": {
                        "type": "string",
                        "description": "Notes about cultural fit, team dynamics, personality traits",
                    },
                    "other_notes": {
                        "type": "string",
                        "description": "Any other important information the client emphasized",
                    },
                },
                "required": [],
            },
        },
        {
            "name": "search_candidates",
            "description": "Search the candidate database for matches to the job context. Returns a shortlist of 3-5 anonymized candidate profiles (iron number + capability summary, NO personal details) with match reasoning and scoring. Present ALL returned candidates to the client as a shortlist so they can choose.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "context_summary": {
                        "type": "string",
                        "description": "Summary of what we're looking for",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max candidates to return for the shortlist (default 5, present 3-5)",
                        "default": 5,
                    },
                },
                "required": ["context_summary"],
            },
        },
        {
            "name": "mark_client_interested",
            "description": "Record that the client is interested in a specific candidate. Updates referral status to client_interested. Call this when the client picks a candidate from the shortlist, BEFORE asking them to confirm sending the full CV.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "candidate_number": {
                        "type": "string",
                        "description": "Candidate number (e.g., C000123)",
                    },
                    "interest_reason": {
                        "type": "string",
                        "description": "Why the client is interested (optional)",
                    },
                },
                "required": ["candidate_number"],
            },
        },
        {
            "name": "send_candidate_cv",
            "description": "Send the chosen candidate's FULL CV to the client in Panda-Tech format. ONLY call this after the client has EXPLICITLY confirmed (positive answer) that they want to receive the full CV of this specific candidate. The system renders the branded Panda-Tech CV and delivers it automatically over WhatsApp.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "candidate_number": {
                        "type": "string",
                        "description": "Candidate number the client confirmed (e.g., C000123)",
                    },
                    "confirmation_note": {
                        "type": "string",
                        "description": "Short note on the client's confirmation (optional)",
                    },
                },
                "required": ["candidate_number"],
            },
        },
        {
            "name": "check_referral_history",
            "description": "Check if a candidate has been offered to this client before.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "candidate_number": {
                        "type": "string",
                        "description": "Candidate number (e.g., C000123)",
                    },
                },
                "required": ["candidate_number"],
            },
        },
        {
            "name": "request_quota_increase",
            "description": "Request an increase to the client's monthly message quota.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "additional_messages": {
                        "type": "integer",
                        "description": "Number of additional messages requested (default 50)",
                        "default": 50,
                    },
                    "reason": {
                        "type": "string",
                        "description": "Reason for the increase request",
                    },
                },
                "required": [],
            },
        },
        {
            "name": "transfer_to_recruitment",
            "description": "Transfer a client interaction to the manual recruitment team (mark as transferred_to_recruitment).",
            "input_schema": {
                "type": "object",
                "properties": {
                    "summary": {
                        "type": "string",
                        "description": "Summary of conversation to hand off to team",
                    },
                },
                "required": ["summary"],
            },
        },
        {
            "name": "identify_client",
            "description": "Check if a client already exists in the database by phone number. Used during opening phase to determine if this is a known or new client.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "phone": {
                        "type": "string",
                        "description": "Phone number in E.164 format (e.g., +972501234567)",
                    },
                },
                "required": ["phone"],
            },
        },
        {
            "name": "create_client",
            "description": "Create a new client in the database and sync to Pipedrive. Call this after collecting client details (name, email, company, role).",
            "input_schema": {
                "type": "object",
                "properties": {
                    "phone": {
                        "type": "string",
                        "description": "Phone number in E.164 format",
                    },
                    "full_name": {
                        "type": "string",
                        "description": "Full name of the client (first + last)",
                    },
                    "email": {
                        "type": "string",
                        "description": "Email address",
                    },
                    "company_name": {
                        "type": "string",
                        "description": "Company or organization name",
                    },
                    "role": {
                        "type": "string",
                        "description": "Job title or role at company",
                    },
                },
                "required": ["phone", "full_name", "email"],
            },
        },
    ]


# Tool implementation stubs (Session 28 placeholders)
# Session 30: Real implementations moved to candidate_matching.py

async def update_job_context_impl(
    conversation_id: str, **kwargs: Any
) -> dict:
    """Implementation placeholder for update_job_context."""
    return {"status": "success", "updated_fields": list(kwargs.keys())}


async def search_candidates_impl(
    context_summary: str, limit: int = 3
) -> dict:
    """
    Search for candidates (DEPRECATED: Session 28 mock implementation).

    Session 30: Real implementation moved to CandidateMatchingEngine in candidate_matching.py
    This function is kept for backward compatibility only.

    Returns mock candidates for testing.
    """
    mock_candidates = [
        {
            "candidate_number": "C000001",
            "match_score": 92,
            "domain": "תוכנה",
            "years_experience": 7,
            "security_clearance": "סודי",
            "location": "מרכז",
            "languages": ["עברית (שפת אם)", "אנגלית (שוטף)"],
            "top_skills": [
                "Python (7y)",
                "Django (5y)",
                "PostgreSQL (6y)",
                "AWS (3y)",
            ],
            "summary": "Backend engineer with strong Python and system design experience. Worked at 2 startups, good fit for flat org culture. Has valid security clearance.",
            "reasoning": "7+ years backend experience matches 5+ requirement. Startup background aligns with culture expectations. Valid security clearance.",
        },
        {
            "candidate_number": "C000002",
            "match_score": 85,
            "domain": "תוכנה",
            "years_experience": 6,
            "security_clearance": "סודי",
            "location": "צפון",
            "languages": ["עברית (שפת אם)", "אנגלית (טוב)"],
            "top_skills": [
                "Kubernetes (3y)",
                "Go (4y)",
                "gRPC (2y)",
                "DevOps (3y)",
            ],
            "summary": "Infrastructure/DevOps engineer with strong system thinking. Worked at one large tech company. Slightly different stack but strong fundamentals.",
            "reasoning": "System design + DevOps experience covers technical requirements. Security clearance confirmed. Different primary language (Go vs Python) is gap but manageable.",
        },
        {
            "candidate_number": "C000003",
            "match_score": 78,
            "domain": "תוכנה",
            "years_experience": 5,
            "security_clearance": "סודי",
            "location": "מרכז",
            "languages": ["עברית (שפת אם)", "אנגלית"],
            "top_skills": [
                "Python (5y)",
                "FastAPI (3y)",
                "React (2y)",
                "Docker (4y)",
            ],
            "summary": "Full-stack developer with Python backend experience. Less pure backend focus but solid fundamentals. Valid security clearance.",
            "reasoning": "Python experience but primary background is full-stack. Could work for role but may need ramp-up in pure backend patterns. Clearance OK.",
        },
    ]

    return {
        "status": "success",
        "candidates": mock_candidates[:limit],
        "total_found": len(mock_candidates),
    }


async def mark_client_interested_impl(
    candidate_number: str, interest_reason: str = None
) -> dict:
    """Implementation placeholder for marking client as interested."""
    return {
        "status": "success",
        "candidate_number": candidate_number,
        "message": f"עדכנתי שאתה מעוניין ב-{candidate_number}. צוות הגיוס שלנו יחזור אליך בקרוב עם פרטים נוספים.",
    }


async def check_referral_history_impl(candidate_number: str) -> dict:
    """Implementation placeholder for checking referral history."""
    return {
        "status": "success",
        "candidate_number": candidate_number,
        "previous_offers": 0,
        "previous_decline": False,
    }


async def request_quota_increase_impl(
    additional_messages: int = 50, reason: str = None
) -> dict:
    """Implementation placeholder for quota increase request."""
    return {
        "status": "success",
        "message": f"הבקשה שלך להגדלת מכסה ב-{additional_messages} הודעות נשלחה לאדמין. נעדכן אותך כשתאושר!",
    }


async def transfer_to_recruitment_impl(summary: str) -> dict:
    """Implementation placeholder for transferring to manual recruitment."""
    return {
        "status": "success",
        "message": "העברתי את הטיפול לצוות הגיוס שלנו. הם יצרו אתך קשר בקרוב.",
        "summary_saved": True,
    }

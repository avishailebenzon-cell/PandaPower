"""Pandius LLM tool definitions — candidate intake + job lookup."""


def get_pandius_tools() -> list:
    """Tools available to Pandius. Deliberately small to keep the agent terse."""
    return [
        {
            "name": "identify_candidate",
            "description": (
                "Check if this job seeker already exists in our database. Call "
                "once at the start of the conversation. You do NOT pass the phone "
                "number — the system already knows it from WhatsApp and supplies "
                "it automatically."
            ),
            "input_schema": {
                "type": "object",
                "properties": {},
            },
        },
        {
            "name": "save_candidate",
            "description": (
                "Store the job seeker as a contact with status 'מועמד לחברה' "
                "(candidate) and sync to Pipedrive. Call once you have their full "
                "name and email. You do NOT pass the phone number — the system "
                "supplies it automatically from WhatsApp."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "first_name": {"type": "string", "description": "First name"},
                    "last_name": {"type": "string", "description": "Last/family name"},
                    "email": {"type": "string", "description": "Email address"},
                },
                "required": ["first_name", "last_name", "email"],
            },
        },
        {
            "name": "search_open_jobs",
            "description": (
                "Search PandaTech's currently open positions to find ones that "
                "could fit this candidate. Returns a short list of open jobs."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "What the candidate is looking for — role, domain, skills, location.",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max jobs to return (default 8)",
                        "default": 8,
                    },
                },
                "required": ["query"],
            },
        },
        {
            "name": "transfer_to_recruitment",
            "description": "Hand off this candidate to the human recruitment team.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "summary": {
                        "type": "string",
                        "description": "Short summary of the candidate and why we're handing off.",
                    },
                },
                "required": ["summary"],
            },
        },
    ]

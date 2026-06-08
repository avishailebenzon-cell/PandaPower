"""Dana Tools — LLM tool definitions for job-deal intake."""

from .prompts.system import PIPELINES


def get_dana_tools() -> list:
    """Tools available to Dana while collecting + creating a job deal."""
    return [
        {
            "name": "update_job_context",
            "description": (
                "Save/merge the job details collected so far. Call this after every "
                "meaningful detail the user shares or after parsing an attached file. "
                "Only include fields you have new info for — existing values are kept."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "pipeline": {
                        "type": "string",
                        "enum": PIPELINES,
                        "description": "The recruitment pipeline (must be one of the five exact names).",
                    },
                    "job_title": {"type": "string", "description": "Job title."},
                    "job_description": {"type": "string", "description": "Job description."},
                    "job_qualifications": {"type": "string", "description": "Role requirements/qualifications."},
                    "job_location": {"type": "string", "description": "Job location."},
                    "job_security_clearance": {
                        "type": "string",
                        "description": "Required clearance, e.g. 'רמה 1' / 'רמה 2' / 'רמה 3'. Optional.",
                    },
                    "deadline": {
                        "type": "string",
                        "description": "Last date to submit a candidate, format YYYY-MM-DD.",
                    },
                    "organization": {"type": "string", "description": "Client organization name."},
                    "person": {"type": "string", "description": "Contact person full name."},
                    "person_phone": {"type": "string", "description": "Contact person phone."},
                    "person_link": {
                        "type": "string",
                        "description": "How the contact is connected to the client (their role/relation).",
                    },
                },
                "required": [],
            },
        },
        {
            "name": "lookup_organization",
            "description": (
                "Check whether an organization already exists in Pipedrive before creating it. "
                "Uses fuzzy matching: a one-letter difference, or a company prefix like 'חברת', "
                "counts as the same org (e.g. 'חברת חשמל לישראל' == 'חברת חשמל'). "
                "Returns the matched org (id + name) or no match."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Organization name to look up."}
                },
                "required": ["name"],
            },
        },
        {
            "name": "lookup_person",
            "description": (
                "Check whether a contact person already exists in Pipedrive before creating them. "
                "Uses fuzzy matching (a one-letter difference counts as the same person). "
                "Returns the matched person (id + name) or no match."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Person full name to look up."}
                },
                "required": ["name"],
            },
        },
        {
            "name": "create_deal",
            "description": (
                "Create the new job deal in Pipedrive and sync it into PandaPower. "
                "Call ONLY after all required fields are collected and the user confirmed. "
                "Finds-or-creates the organization and the contact person, opens the deal in the "
                "chosen pipeline with all job custom fields, then triggers a Pipedrive→jobs sync."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "confirm": {
                        "type": "boolean",
                        "description": "Must be true — the user confirmed creating the deal.",
                    }
                },
                "required": ["confirm"],
            },
        },
    ]

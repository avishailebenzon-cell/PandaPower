"""
Phase 4B: Job Change Detection Module

Provides utilities for detecting when job specifications change and need re-evaluation.
Uses SHA256 hashing of critical job fields to determine if a job has changed.

When a job's specification hash changes:
1. All existing matches for that job become invalid (except protected states)
2. Re-matching is automatically triggered for the job
3. Change is recorded in job_changes history table
4. User is notified via system status endpoint
"""

import hashlib
import json
from typing import Dict, Any, Optional, List
from datetime import datetime


# Critical job fields that trigger re-matching if changed
CRITICAL_JOB_FIELDS = [
    "priority",
    "title",
    "description",
    "qualifications",
    "requirements",
    "location",
    "required_experience_years",
    "seniority_level",
    "salary_min",
    "salary_max",
]


def compute_job_spec_hash(job: Dict[str, Any]) -> str:
    """
    Compute a stable SHA256 hash of critical job specification fields.

    This hash is used to detect when a job's specification has changed.
    If the hash differs from the stored hash, re-matching is triggered.

    Args:
        job: Dictionary containing job data from database or sync source

    Returns:
        str: SHA256 hash of the job specification (64-char hex string)

    Example:
        >>> job = {"priority": 1, "title": "Senior Dev", "description": "..."}
        >>> hash1 = compute_job_spec_hash(job)
        >>> job["priority"] = 2
        >>> hash2 = compute_job_spec_hash(job)
        >>> hash1 != hash2  # True - change detected!
    """
    data_to_hash = {}

    for field in CRITICAL_JOB_FIELDS:
        value = job.get(field, "")

        # Normalize the value for consistent hashing
        if value is None:
            value = ""
        elif isinstance(value, str):
            # Normalize: lowercase, strip whitespace
            value = value.lower().strip()
        elif isinstance(value, (list, dict)):
            # For complex types, convert to sorted string representation
            value = str(sorted(value)).lower()
        elif isinstance(value, (int, float)):
            # Convert numbers to string for consistency
            value = str(value)

        data_to_hash[field] = value

    # Create deterministic JSON string with sorted keys
    hash_input = json.dumps(data_to_hash, sort_keys=True)

    # Compute SHA256 hash
    hash_object = hashlib.sha256(hash_input.encode())
    return hash_object.hexdigest()


def extract_changed_fields(
    old_job: Dict[str, Any],
    new_job: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Extract which fields changed between old and new job data.

    Only considers CRITICAL_JOB_FIELDS to determine what changed.

    Args:
        old_job: Previous job data
        new_job: Updated job data

    Returns:
        dict: {field_name: old_value} for all fields that changed

    Example:
        >>> old = {"priority": 2, "title": "Dev", "description": "old"}
        >>> new = {"priority": 1, "title": "Dev", "description": "new"}
        >>> extract_changed_fields(old, new)
        {"priority": 2, "description": "old"}
    """
    changed_fields = {}

    for field in CRITICAL_JOB_FIELDS:
        old_value = old_job.get(field)
        new_value = new_job.get(field)

        # Compare values: treat None and "" as equivalent for strings
        if old_value != new_value:
            # Normalize empty string and None to be equivalent
            if (old_value is None or old_value == "") and (new_value is None or new_value == ""):
                continue  # Not a real change

            changed_fields[field] = old_value

    return changed_fields


def detect_job_spec_change(
    old_hash: Optional[str],
    new_hash: str
) -> bool:
    """
    Determine if a job's specification has meaningfully changed.

    Args:
        old_hash: Previous hash (from jobs.job_spec_hash), or None if new job
        new_hash: Current hash (just computed)

    Returns:
        bool: True if job spec changed (hashes differ), False otherwise
    """
    # First job always "changed" from nothing to something
    if old_hash is None:
        return True

    # Otherwise, changed only if hashes differ
    return old_hash != new_hash


def build_change_summary(
    changed_fields: Dict[str, Any],
    previous_values: Optional[Dict[str, Any]] = None
) -> str:
    """
    Build a human-readable summary of what changed.

    Used for logging and user-facing messages.

    Args:
        changed_fields: Dict of {field_name: old_value} from extract_changed_fields()
        previous_values: Optional JSONB from database for comparison

    Returns:
        str: Human-readable summary like "priority: 2→1, description changed"
    """
    if not changed_fields:
        return "No changes detected"

    changes = []
    for field, old_value in changed_fields.items():
        changes.append(field)

    return f"Changed fields: {', '.join(changes)}"


# Constants for database interaction
class ChangeType:
    """Enumeration of job change types for job_changes table."""
    CREATED = "created"
    MODIFIED = "modified"
    PRIORITY_CHANGED = "priority_changed"
    SPECS_CHANGED = "specs_changed"
    QUALIFICATIONS_CHANGED = "qualifications_changed"
    LOCATION_CHANGED = "location_changed"
    MANUAL_REMATCH = "manual_rematch_request"


class ChangeSource:
    """Enumeration of who/what triggered the change."""
    PIPEDRIVE_SYNC = "pipedrive_sync"
    SYSTEM = "system"
    MANUAL_API = "manual_api"
    USER_ID = "user_id"  # Placeholder for actual user_id
    AGENT_CODE = "agent_code"  # Placeholder for actual agent code

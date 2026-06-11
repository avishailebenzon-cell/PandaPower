"""
Job change detection helpers.

When a job (Pipedrive deal) is re-synced, we want to know whether its
*specification* actually changed in a way that should invalidate existing
matches and trigger re-matching — as opposed to a no-op sync that only touched
bookkeeping fields (last_synced_at, etc.).

We do this with a stable hash over the spec-relevant fields. If the hash
differs from the previously stored `job_spec_hash`, the spec changed.

Used by:
- workers/pipedrive_deals_sync.py  (_sync_deal)
- workers/agent_matching.py         (trigger_job_rematching)
"""

import hashlib
import json
import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)


# Fields that define a job's "specification". A change to any of these means
# candidate matching may need to be re-evaluated. Bookkeeping/tracking fields
# (ids, timestamps, sync metadata, hashes) are deliberately excluded so that a
# routine re-sync does not look like a spec change.
SPEC_FIELDS = [
    "job_title",
    "job_description",
    "job_qualifications",
    "job_location",
    "job_security_clearance",
    "deadline",
    "priority",
]


def _normalize(value: Any) -> str:
    """Normalize a single field value to a stable string for hashing."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return str(value)


def compute_job_spec_hash(job: Dict[str, Any]) -> str:
    """Compute a stable SHA-256 hash over a job's spec-relevant fields.

    Accepts either a freshly-built deal_data dict or an existing job row;
    only SPEC_FIELDS are considered, so extra keys are ignored.
    """
    spec = {field: _normalize(job.get(field)) for field in SPEC_FIELDS}
    payload = json.dumps(spec, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def detect_job_spec_change(old_hash: str, new_hash: str) -> bool:
    """Return True if the spec hash changed (and an old hash existed)."""
    if not old_hash:
        # No prior hash recorded - treat as "no detectable change" so we don't
        # needlessly invalidate matches on the first hash-bearing sync.
        return False
    return old_hash != new_hash


def extract_changed_fields(
    existing_job: Dict[str, Any], new_data: Dict[str, Any]
) -> Dict[str, Any]:
    """Return {field: old_value} for each spec field whose value changed.

    The returned mapping holds the PREVIOUS values, matching the
    `previous_values` argument expected by
    AgentMatchingWorker.invalidate_matches_for_job_change.
    """
    changed: Dict[str, Any] = {}
    for field in SPEC_FIELDS:
        old_value = existing_job.get(field)
        new_value = new_data.get(field)
        if _normalize(old_value) != _normalize(new_value):
            changed[field] = old_value
    return changed

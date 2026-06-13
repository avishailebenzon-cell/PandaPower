"""Pipedrive write helpers for Dana.

Holds the PandaTech deal custom-field hashes, fuzzy de-duplication for
organizations/persons, pipeline-name resolution, and the find-or-create +
create-deal flow used by Dana's create_deal tool.
"""

from __future__ import annotations

import re
from typing import Any, Dict, Optional

import structlog

from pandapower.core.config import settings
from pandapower.agents.company_profile import DANA_NOTE_PREFIX
from pandapower.integrations.pipedrive_client import PipedriveClient

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Deal custom-field hashes (PandaTech workspace) — mirror pipedrive_deals_sync
# ---------------------------------------------------------------------------
FIELD_JOB_TITLE = "c616325e1187aaa05257f6d4cd9cc3626679b23f"
FIELD_JOB_DESCRIPTION = "9ed8654203d45357d76e8f83ca5a8584f5f8e2fb"
FIELD_JOB_QUALIFICATIONS = "5198dc3d914cb437bf95133a64809a30f69e3b02"
FIELD_JOB_LOCATION = "d04ed525f3ed45fb04383e07f281ad7338a30e4e"
FIELD_SECURITY_CLEARANCE = "9997b3547b9295447c03c98343a50f4d8d097361"
FIELD_DEADLINE = "a6a8a84e518fb22fc9920f3e714a2bfaf9f488b5"

# Required-clearance single-select option ids (match person clearance map).
CLEARANCE_OPTION_IDS = {
    "רמה 1": 145,
    "רמה 2": 146,
    "רמה 3": 147,
}

# Common Hebrew company prefixes/words that don't change org identity.
_ORG_STOPWORDS = ["חברת", "חברה", "בעמ", "בע\"מ", "בע''מ", "ltd", "ltd.", "inc", "inc."]


def get_pipedrive_client() -> PipedriveClient:
    """Build a Pipedrive client from configured settings."""
    return PipedriveClient(
        api_token=settings.PIPEDRIVE_API_TOKEN,
        api_domain=settings.PIPEDRIVE_API_DOMAIN,
    )


# ---------------------------------------------------------------------------
# Fuzzy matching
# ---------------------------------------------------------------------------
def _levenshtein(a: str, b: str) -> int:
    """Classic edit distance."""
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def _norm(text: str) -> str:
    """Lowercase, collapse whitespace, strip punctuation."""
    text = (text or "").strip().lower()
    text = re.sub(r"[\"'`.,;:()\-]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _norm_org(name: str) -> str:
    """Normalize an org name: drop company stopwords + punctuation."""
    norm = _norm(name)
    tokens = [t for t in norm.split() if t not in _ORG_STOPWORDS]
    return " ".join(tokens).strip() or norm


def names_match_person(a: str, b: str) -> bool:
    """Same person if normalized names are within one edit."""
    na, nb = _norm(a), _norm(b)
    if not na or not nb:
        return False
    return _levenshtein(na, nb) <= 1


def names_match_org(a: str, b: str) -> bool:
    """Same org under: one-letter diff, or one name contained in the other
    after stripping company stopwords (handles 'חברת חשמל' == 'חברת חשמל לישראל')."""
    na, nb = _norm_org(a), _norm_org(b)
    if not na or not nb:
        return False
    if _levenshtein(na, nb) <= 1:
        return True
    # containment of significant tokens (e.g. "חשמל" within "חשמל לישראל")
    sa, sb = set(na.split()), set(nb.split())
    if sa and sb and (sa.issubset(sb) or sb.issubset(sa)):
        return True
    return na in nb or nb in na


# ---------------------------------------------------------------------------
# Lookups (search Pipedrive, then apply Dana's fuzzy rules)
# ---------------------------------------------------------------------------
async def find_organization(client: PipedriveClient, name: str) -> Optional[Dict[str, Any]]:
    """Return an existing org {id, name} matching `name`, or None."""
    if not name:
        return None
    # Search with the most distinctive token to get candidates back.
    term = _norm_org(name).split()
    search_term = term[0] if term else name
    try:
        candidates = await client.search_organizations(search_term)
    except Exception as e:
        logger.warning("dana_org_search_failed", error=str(e))
        candidates = []
    for c in candidates:
        if names_match_org(name, c.get("name", "")):
            return {"id": c.get("id"), "name": c.get("name")}
    return None


async def find_person(client: PipedriveClient, name: str) -> Optional[Dict[str, Any]]:
    """Return an existing person {id, name} matching `name`, or None."""
    if not name:
        return None
    try:
        candidates = await client.search_persons(name)
    except Exception as e:
        logger.warning("dana_person_search_failed", error=str(e))
        candidates = []
    for c in candidates:
        if names_match_person(name, c.get("name", "")):
            return {"id": c.get("id"), "name": c.get("name")}
    return None


# ---------------------------------------------------------------------------
# Pipeline resolution
# ---------------------------------------------------------------------------
async def resolve_pipeline_id(client: PipedriveClient, pipeline_name: str) -> Optional[int]:
    """Map a pipeline display name to its Pipedrive pipeline_id (fuzzy)."""
    if not pipeline_name:
        return None
    try:
        pipelines = await client.get_pipelines()
    except Exception as e:
        logger.warning("dana_pipelines_fetch_failed", error=str(e))
        return None
    target = _norm(pipeline_name)
    # exact normalized match first
    for p in pipelines:
        if _norm(p.get("name", "")) == target:
            return p.get("id")
    # then fuzzy / containment
    for p in pipelines:
        pn = _norm(p.get("name", ""))
        if _levenshtein(pn, target) <= 2 or target in pn or pn in target:
            return p.get("id")
    return None


# ---------------------------------------------------------------------------
# Create the deal end-to-end
# ---------------------------------------------------------------------------
def build_deal_title(job_title: str, person: str, organization: str) -> str:
    """'#job title# אצל #contact# חברת #org#'."""
    parts = [job_title or "משרה"]
    if person:
        parts.append(f"אצל {person}")
    if organization:
        parts.append(f"חברת {organization}")
    return " ".join(parts)


async def create_job_deal(ctx: Dict[str, Any]) -> Dict[str, Any]:
    """
    Find-or-create org + person, open a deal in the chosen pipeline with all
    job custom fields. Returns a result dict with the new deal id + notes.
    """
    client = get_pipedrive_client()
    notes: list[str] = []
    try:
        # --- pipeline ---
        pipeline_id = await resolve_pipeline_id(client, ctx.get("pipeline", ""))
        if pipeline_id is None:
            return {
                "status": "error",
                "message": (
                    f"לא הצלחתי לזהות את הפייפליין '{ctx.get('pipeline')}' בפייפדרייב. "
                    "ודא שהשם תואם לאחד מהפייפליינים הקיימים."
                ),
            }

        # --- organization (find or create) ---
        org_id = None
        org_name = (ctx.get("organization") or "").strip()
        if org_name:
            existing_org = await find_organization(client, org_name)
            if existing_org:
                org_id = existing_org["id"]
                notes.append(f"הארגון כבר קיים: {existing_org['name']} (#{org_id}).")
            else:
                created = await client.create_organization(org_name)
                org_id = created.get("id")
                notes.append(f"נוצר ארגון חדש: {org_name} (#{org_id}).")

        # --- person (find or create) ---
        person_id = None
        person_name = (ctx.get("person") or "").strip()
        if person_name:
            existing_person = await find_person(client, person_name)
            if existing_person:
                person_id = existing_person["id"]
                notes.append(f"איש הקשר כבר קיים: {existing_person['name']} (#{person_id}).")
            else:
                created = await client.create_person(
                    name=person_name,
                    phone=ctx.get("person_phone") or None,
                )
                person_id = created.get("id")
                notes.append(f"נוצר איש קשר חדש: {person_name} (#{person_id}).")

        # --- deal custom fields ---
        custom: Dict[str, Any] = {
            FIELD_JOB_TITLE: ctx.get("job_title") or "",
            FIELD_JOB_DESCRIPTION: ctx.get("job_description") or "",
            FIELD_JOB_QUALIFICATIONS: ctx.get("job_qualifications") or "",
            FIELD_JOB_LOCATION: ctx.get("job_location") or "",
        }
        if ctx.get("deadline"):
            custom[FIELD_DEADLINE] = ctx["deadline"]
        clearance = (ctx.get("job_security_clearance") or "").strip()
        if clearance:
            opt = CLEARANCE_OPTION_IDS.get(clearance)
            custom[FIELD_SECURITY_CLEARANCE] = opt if opt is not None else clearance

        title = build_deal_title(
            ctx.get("job_title", ""), person_name, org_name
        )

        deal = await client.create_deal(
            title=title,
            pipeline_id=pipeline_id,
            person_id=person_id,
            org_id=org_id,
            custom_fields=custom,
        )
        deal_id = deal.get("id")
        notes.append(f"נפתח דיל חדש בפייפדרייב: '{title}' (#{deal_id}).")

        # Audit note: mark every Dana-created deal so it's traceable in Pipedrive
        if deal_id:
            try:
                await client.create_deal_note(
                    deal_id,
                    f"{DANA_NOTE_PREFIX}\nדיל זה נוצר על ידי דנה.",
                )
            except Exception as e:
                logger.warning(f"Failed to add Dana audit note to deal {deal_id}: {e}")

        return {
            "status": "success",
            "deal_id": deal_id,
            "deal_title": title,
            "pipeline_id": pipeline_id,
            "org_id": org_id,
            "person_id": person_id,
            "notes": notes,
        }
    finally:
        await client.close()

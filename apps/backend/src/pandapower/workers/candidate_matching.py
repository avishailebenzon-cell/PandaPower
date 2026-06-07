"""
Candidate matching engine: matches candidates to jobs and client contacts.

Matching logic:
1. Jobs: domain + security clearance + experience
2. Contacts: professional domain + clearance compatibility + status (client > potential)

Score formula:
- Domain match: 40 points (exact=40, contains=35, synonym=30)
- Security clearance: 35 points (must be >= required; higher gets bonus)
- Experience: 15 points (matched to role seniority)
- Location (if applicable): 10 points

Final score: weighted sum / 100
Minimum threshold: 80%
"""

import logging
from typing import Any, Optional
from enum import Enum

logger = logging.getLogger(__name__)


class SecurityLevel(Enum):
    """Security clearance levels.

    IMPORTANT: in the Israeli scheme רמה 1 is the HIGHEST clearance and רמה 3
    the lowest. The enum *value* encodes rank (higher value = higher clearance),
    so the numbered levels are inverted: LEVEL_1 = 3, LEVEL_2 = 2, LEVEL_3 = 1.
    """
    NONE = 0
    LEVEL_3 = 1
    LEVEL_2 = 2
    LEVEL_1 = 3

    @staticmethod
    def from_string(level_str: str) -> "SecurityLevel":
        """Convert string to SecurityLevel."""
        if not level_str:
            return SecurityLevel.NONE
        level_str = level_str.lower().strip()
        if "1" in level_str or "רמה 1" in level_str:
            return SecurityLevel.LEVEL_1
        if "2" in level_str or "רמה 2" in level_str:
            return SecurityLevel.LEVEL_2
        if "3" in level_str or "רמה 3" in level_str:
            return SecurityLevel.LEVEL_3
        return SecurityLevel.NONE

    def can_fulfill(self, required: "SecurityLevel") -> bool:
        """Check if this level can fulfill a requirement."""
        return self.value >= required.value


# Domain synonyms mapping for matching
DOMAIN_SYNONYMS = {
    "תוכנה": {"python", "java", "c++", "javascript", "typescript", "go", "rust", "nodejs", "fullstack", "backend", "frontend", "devops"},
    "software": {"python", "java", "c++", "javascript", "typescript", "go", "rust", "nodejs", "fullstack", "backend", "frontend"},
    "python": {"backend", "fullstack", "devops", "data engineering"},
    "java": {"backend", "fullstack", "enterprise"},
    "frontend": {"javascript", "typescript", "react", "vue", "angular"},
    "react": {"frontend", "javascript", "typescript", "fullstack"},
    "qa": {"testing", "automation", "selenium", "loadrunner"},
    "testing": {"qa", "automation", "quality assurance"},
    "אלקטרוניקה": {"fpga", "vhdl", "verilog", "pcb", "rf design", "embedded"},
    "electronics": {"fpga", "embedded", "hardware", "pcb design"},
    "סיסטמים": {"linux", "windows", "devops", "infrastructure", "networking", "administration"},
    "systems": {"linux", "devops", "infrastructure", "sysadmin"},
    "it": {"support", "helpdesk", "infrastructure", "networking", "windows", "administration"},
}


class CandidateMatchingEngine:
    """Matches candidates to jobs and client contacts."""

    def __init__(self, supabase_client: Any, threshold: float = 0.80):
        self.supabase = supabase_client
        self.threshold = threshold

    async def find_job_matches(self, candidate: dict) -> list[dict]:
        """Find jobs that match a candidate (≥80% match score)."""
        try:
            # Get all active jobs
            jobs_response = await self.supabase.table("jobs").select(
                "id, title, required_domain, required_security_clearance, "
                "qualifications, location, client_org_id, priority"
            ).eq("is_active", True).execute()

            jobs = jobs_response.data or []
            matches = []

            candidate_domain = (candidate.get("primary_domain") or "").lower().strip()
            candidate_clearance = SecurityLevel.from_string(
                candidate.get("security_clearance_level", "")
            )
            # Support both field names for years of experience
            candidate_years = candidate.get("years_of_experience") or candidate.get("years_experience") or 0

            for job in jobs:
                score, details = self._score_job_match(
                    candidate_domain=candidate_domain,
                    candidate_clearance=candidate_clearance,
                    candidate_years=candidate_years,
                    job=job,
                )

                if score >= self.threshold:
                    matches.append({
                        "job_id": job["id"],
                        "job_title": job["title"],
                        "match_score": round(score, 2),
                        "match_details": details,
                        "priority": job.get("priority"),
                    })

            # Sort by score descending, limit to top 5
            matches.sort(key=lambda x: x["match_score"], reverse=True)
            return matches[:5]

        except Exception as e:
            logger.error(f"Error finding job matches: {e}", exc_info=True)
            return []

    async def find_contact_recommendations(self, candidate: dict) -> list[dict]:
        """Find client/potential client contacts to recommend candidate to."""
        try:
            # Query only client/potential_client contacts
            contacts_response = await self.supabase.table("contacts").select(
                "id, full_name, contact_status, professional_domain, "
                "security_clearance_level, organization_id"
            ).in_("contact_status", ["client", "potential_client"]).execute()

            contacts = contacts_response.data or []
            matches = []

            candidate_domain = (candidate.get("primary_domain") or "").lower().strip()
            candidate_secondary = [d.lower().strip() for d in (candidate.get("secondary_domains") or [])]
            candidate_clearance = SecurityLevel.from_string(
                candidate.get("security_clearance_level", "")
            )

            # Build full domain set
            all_domains = {candidate_domain} | set(candidate_secondary)
            all_domains.discard("")

            for contact in contacts:
                score, details = self._score_contact_match(
                    candidate_domains=all_domains,
                    candidate_clearance=candidate_clearance,
                    contact=contact,
                )

                if score >= self.threshold:
                    matches.append({
                        "contact_id": contact["id"],
                        "contact_name": contact.get("full_name", "Unknown"),
                        "contact_status": contact.get("contact_status"),
                        "professional_domain": contact.get("professional_domain"),
                        "match_score": round(score, 2),
                        "match_details": details,
                    })

            # Sort by score descending, limit to top 5
            matches.sort(key=lambda x: x["match_score"], reverse=True)
            return matches[:5]

        except Exception as e:
            logger.error(f"Error finding contact matches: {e}", exc_info=True)
            return []

    def _score_job_match(
        self,
        candidate_domain: str,
        candidate_clearance: SecurityLevel,
        candidate_years: float,
        job: dict,
    ) -> tuple[float, dict]:
        """Score a candidate-job match. Returns (score 0-1, details dict)."""
        score = 0.0
        details = {}

        # 1. Domain matching (40 points)
        job_domain = (job.get("required_domain") or "").lower().strip()
        domain_score = self._match_domains(candidate_domain, job_domain)
        score += domain_score * 40
        details["domain_match"] = "exact" if domain_score == 1.0 else (
            "strong" if domain_score >= 0.8 else "weak"
        )

        # 2. Security clearance (35 points)
        job_clearance_str = job.get("required_security_clearance", "")
        job_clearance = SecurityLevel.from_string(job_clearance_str)

        if job_clearance == SecurityLevel.NONE:
            # No clearance required
            clearance_score = 1.0
            details["clearance_match"] = "not_required"
        elif candidate_clearance.can_fulfill(job_clearance):
            # Candidate has required clearance
            clearance_score = 1.0 if candidate_clearance.value == job_clearance.value else 0.9
            details["clearance_match"] = "meets" if clearance_score == 1.0 else "exceeds"
        else:
            # Candidate doesn't have required clearance - auto-fail
            clearance_score = 0.0
            details["clearance_match"] = "insufficient"

        score += clearance_score * 35

        # 3. Experience matching (15 points)
        qualifications = (job.get("qualifications") or "").lower()
        if not qualifications:
            experience_score = 0.5  # No data, assume neutral
        elif candidate_years >= 5:
            experience_score = 1.0 if "senior" in qualifications or "lead" in qualifications else 0.8
        elif candidate_years >= 2:
            experience_score = 0.8 if "mid" in qualifications else 0.7
        else:
            experience_score = 0.9 if "junior" in qualifications or "entry" in qualifications else 0.5

        score += experience_score * 15
        details["experience_match"] = f"{candidate_years} years" if candidate_years else "unknown"

        # 4. Location (10 points) - simplified, not yet matching
        score += 10  # Neutral for now

        # Normalize to 0-1
        final_score = score / 100
        return final_score, details

    def _score_contact_match(
        self,
        candidate_domains: set,
        candidate_clearance: SecurityLevel,
        contact: dict,
    ) -> tuple[float, dict]:
        """Score a candidate-contact match. Returns (score 0-1, details dict)."""
        score = 0.0
        details = {}

        # 1. Professional domain matching (50 points)
        contact_domains = {d.lower().strip() for d in (contact.get("professional_domain") or "").split(",")}
        contact_domains.discard("")

        domain_match = len(candidate_domains & contact_domains) > 0
        if domain_match:
            domain_score = 1.0
            details["domain_match"] = "strong"
        else:
            # Try synonym matching
            any_synonym_match = False
            for cd in candidate_domains:
                if cd in DOMAIN_SYNONYMS:
                    if contact_domains & DOMAIN_SYNONYMS[cd]:
                        any_synonym_match = True
                        break
            domain_score = 0.8 if any_synonym_match else 0.0
            details["domain_match"] = "synonym" if any_synonym_match else "none"

        score += domain_score * 50

        # 2. Security clearance compatibility (30 points)
        contact_clearance_str = contact.get("security_clearance_level", "")
        contact_clearance = SecurityLevel.from_string(contact_clearance_str)

        if contact_clearance == SecurityLevel.NONE:
            clearance_score = 1.0
            details["clearance_compatibility"] = "none_required"
        elif candidate_clearance.can_fulfill(contact_clearance):
            clearance_score = 1.0 if candidate_clearance.value == contact_clearance.value else 0.9
            details["clearance_compatibility"] = True
        else:
            clearance_score = 0.0
            details["clearance_compatibility"] = False

        score += clearance_score * 30

        # 3. Contact status (20 points)
        contact_status = contact.get("contact_status", "").lower()
        status_score = 1.0 if contact_status == "client" else 0.8
        details["contact_status"] = contact_status
        score += status_score * 20

        # Normalize to 0-1
        final_score = score / 100
        return final_score, details

    @staticmethod
    def _match_domains(candidate: str, job: str) -> float:
        """
        Match two domain strings.
        Returns: 1.0 = exact, 0.8+ = strong, 0.5-0.8 = partial, <0.5 = weak/none
        """
        if not candidate or not job:
            return 0.0

        candidate = candidate.lower().strip()
        job = job.lower().strip()

        # Exact match
        if candidate == job:
            return 1.0

        # Substring match (either direction)
        if candidate in job or job in candidate:
            return 0.85

        # Synonym check
        for key, synonyms in DOMAIN_SYNONYMS.items():
            if candidate == key.lower() and job in synonyms:
                return 0.8
            if job == key.lower() and candidate in synonyms:
                return 0.8

        # No match
        return 0.0

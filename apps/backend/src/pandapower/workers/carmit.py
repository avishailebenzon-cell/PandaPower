import asyncio
import json
import logging
from datetime import datetime
from typing import Any
from uuid import UUID

from pandapower.integrations.claude_api import AnthropicClient
from pandapower.integrations.pipedrive import PipedriveClient

logger = logging.getLogger(__name__)

# Clearance level hierarchy
# NOTE: kept for backward-compat / settings override only. The clearance gate
# now ranks via recruitment_departments._clearance_rank, which understands the
# Hebrew hierarchy (רמה 1 is the HIGHEST clearance, רמה 3 the lowest).
CLEARANCE_LEVELS = {
    None: 0,
    "none": 0,
    "ללא": 0,
    "ללא סווג": 0,
    "ללא סיווג": 0,
    # רמה 1 is the highest → highest rank (inverted numbering)
    "רמה 3": 1,
    "רמה 2": 2,
    "רמה 1": 3,
    "רמה 3 + שוס": 4,
    "רמה 2 + שוס": 5,
    "רמה 1 + שוס": 6,
    "secret": 1,
    "top secret": 2,
    "ts/sci": 3,
}


class CarmitOrchestrator:
    """Carmit Orchestrator: Central AI manager for job routing and match review.

    Responsibilities:
    1. Route jobs to specialized agents using Claude Opus
    2. Review matches against quality gates before recruiter handoff
    3. Integrate with Pipedrive to enrich decisions
    4. Maintain complete audit trail of all decisions
    """

    def __init__(
        self,
        supabase_client: Any,
        anthropic_client: AnthropicClient,
        pipedrive_client: PipedriveClient,
        settings: Any = None,
    ):
        """Initialize Carmit Orchestrator.

        Args:
            supabase_client: Supabase async client
            anthropic_client: Claude API client (uses Opus model)
            pipedrive_client: Pipedrive CRM client
            settings: Configuration object with thresholds
        """
        self.supabase = supabase_client
        self.claude = anthropic_client
        self.pipedrive = pipedrive_client
        self.settings = settings or {}

        # Configuration - aligned to 0.70 to match the agent's own passing bar
        # (agent_matching sets is_passing / state="found" at score >= 70). A
        # higher Carmit bar silently killed every 70-79 match the agent had
        # already green-lit; keeping one consistent threshold avoids that
        # dead zone. Override via CARMIT_MATCH_SCORE_THRESHOLD if needed.
        self.match_score_threshold = self.settings.get("CARMIT_MATCH_SCORE_THRESHOLD", 0.70)
        self.clearance_levels = self.settings.get("CARMIT_CLEARANCE_LEVELS", CLEARANCE_LEVELS)

        # Agent specialties (from Phase 4)
        self.agent_specialties = {
            "alik": {"name": "אליק", "domain": "Electronics", "skills": ["FPGA", "VHDL", "PCB", "RF", "Analog"]},
            "naama": {"name": "נעמה", "domain": "Software Development (פיתוח תוכנה)", "skills": ["Python", "Java", "C++", "C#", ".NET", "WPF", "Cloud", "Microservices", "Machine Learning", "Real-time / Embedded software", "פיתוח תוכנה", "מפתח/ת תוכנה", "מהנדס/ת תוכנה"]},
            "dganit": {"name": "דגנית", "domain": "QA", "skills": ["Testing", "Selenium", "LoadRunner", "Automation"]},
            "ofir": {"name": "אופיר", "domain": "Systems", "skills": ["Linux", "Networking", "DevOps", "Container"]},
            "itai": {"name": "איתי", "domain": "IT", "skills": ["Infrastructure", "Windows", "Helpdesk", "Networks"]},
            "lior": {"name": "ליאור", "domain": "Mechanical", "skills": ["CAD", "SOLIDWORKS", "FEA", "Manufacturing"]},
            "gc": {"name": "כללי", "domain": "General", "skills": ["All other domains"]},
            "mani": {"name": "מני", "domain": "Security Clearance", "skills": ["רמה 1", "Level 1 Clearance"]},
        }

    async def route_job_to_agent(self, job_id: str) -> dict[str, Any]:
        """Route a job to the best-fit specialized agent.

        Args:
            job_id: Job ID to route

        Returns:
            {agent_code, confidence, reasoning, timestamp}
        """
        try:
            logger.info(f"Starting job routing for job_id={job_id}")

            # Get job details
            job = await self._get_job(job_id)
            if not job:
                raise ValueError(f"Job not found: {job_id}")

            # Get candidate pool stats
            candidate_stats = await self._get_candidate_pool_stats()

            # Build context for Claude Opus
            # Extract required_skills from qualifications and description
            qualifications_text = job.get("job_qualifications", "") or ""
            description_text = job.get("job_description", "") or ""
            combined_text = f"{qualifications_text} {description_text}"

            # Simple skill extraction: look for common skill keywords
            required_skills = []
            if combined_text:
                # Extract tech keywords (this is a simple heuristic)
                tech_keywords = ["Python", "Java", "C++", "C#", "JavaScript", "SQL", "Linux",
                               "Windows", "Docker", "Kubernetes", "AWS", "Azure", "React",
                               "Node", "DevOps", "FPGA", "VHDL", "PCB", "CAD", "Selenium"]
                for skill in tech_keywords:
                    if skill.lower() in combined_text.lower():
                        required_skills.append(skill)

            job_context = {
                "job_title": job.get("job_title", ""),
                "job_description": job.get("job_description", ""),
                "job_qualifications": job.get("job_qualifications", ""),
                "priority": job.get("priority", 5),
                "required_skills": required_skills or ["General Technical Skills"],
                "seniority_level": "Not specified",
                "candidate_pool": candidate_stats,
            }

            # Call Claude Opus for routing decision
            routing_decision = await self._call_claude_for_routing(job_context)

            # Store routing decision in agent_logs
            await self._store_routing_decision(
                job_id=job_id,
                agent_code=routing_decision["agent_code"],
                confidence=routing_decision["confidence"],
                reasoning=routing_decision["reasoning"],
            )

            # Update job with assigned agent
            await self._update_job_routing(
                job_id=job_id,
                agent_code=routing_decision["agent_code"],
                confidence=routing_decision["confidence"],
                reasoning=routing_decision["reasoning"],
            )

            result = {
                "job_id": str(job_id),
                "assigned_agent_code": routing_decision["agent_code"],
                "assigned_agent_name": self.agent_specialties[routing_decision["agent_code"]]["name"],
                "confidence": routing_decision["confidence"],
                "reasoning": routing_decision["reasoning"],
                "timestamp": datetime.utcnow().isoformat(),
            }

            logger.info(f"Job routed successfully: {result}")
            return result

        except Exception as e:
            logger.error(f"Job routing failed for job_id={job_id}: {str(e)}", exc_info=True)
            raise

    async def review_match(self, match_id: str) -> dict[str, Any]:
        """Review a match against quality gates.

        Args:
            match_id: Match ID to review

        Returns:
            {match_id, new_state, gate_results, decision, timestamp}
        """
        try:
            logger.info(f"Starting match review for match_id={match_id}")

            # Get match details
            match = await self._get_match(match_id)
            if not match:
                raise ValueError(f"Match not found: {match_id}")

            candidate_id = match.get("candidate_id")
            job_id = match.get("job_id")

            # Get candidate and job details
            candidate = await self._get_candidate(candidate_id)
            job = await self._get_job(job_id)

            # Apply quality gates
            gate_results = {}
            gates_passed = True

            # GATE 1: Past rejection check
            logger.debug(f"GATE 1: Checking past rejections for candidate={candidate_id}, job={job_id}")
            rejection_gate = await self._check_past_rejection_gate(candidate_id, job_id)
            gate_results["past_rejection"] = rejection_gate
            if not rejection_gate["passed"]:
                gates_passed = False
                logger.info(f"Match failed past rejection gate: {rejection_gate['reason']}")

            # GATE 2: Already declined check
            logger.debug(f"GATE 2: Checking if candidate already declined")
            declined_gate = await self._check_already_declined_gate(candidate_id, job_id)
            gate_results["already_declined"] = declined_gate
            if not declined_gate["passed"]:
                gates_passed = False
                logger.info(f"Match failed already declined gate: {declined_gate['reason']}")

            # GATE 3: Conflict of interest
            logger.debug(f"GATE 3: Checking conflict of interest")
            conflict_gate = await self._check_conflict_of_interest_gate(candidate, job)
            gate_results["conflict_of_interest"] = conflict_gate
            if not conflict_gate["passed"]:
                gates_passed = False
                logger.info(f"Match failed conflict gate: {conflict_gate['reason']}")

            # GATE 4: Security clearance matching
            logger.debug(f"GATE 4: Checking security clearance")
            clearance_gate = await self._check_clearance_gate(candidate, job)
            gate_results["clearance_match"] = clearance_gate
            if not clearance_gate["passed"]:
                gates_passed = False
                logger.info(f"Match failed clearance gate: {clearance_gate['reason']}")

            # GATE 5: Quality score threshold
            logger.debug(f"GATE 5: Checking quality score threshold")
            score_gate = await self._check_quality_score_gate(match)
            gate_results["quality_threshold"] = score_gate
            if not score_gate["passed"]:
                gates_passed = False
                logger.info(f"Match failed quality score gate: {score_gate['reason']}")

            # GATE 6: Relevant skills matching
            logger.debug(f"GATE 6: Checking relevant skills for job")
            skills_gate = await self._check_relevant_skills_gate(candidate, job, match)
            gate_results["relevant_skills"] = skills_gate
            if not skills_gate["passed"]:
                gates_passed = False
                logger.info(f"Match failed skills gate: {skills_gate['reason']}")

            # Determine final decision
            if gates_passed:
                new_state = "carmit_approved"
                decision_reasoning = "כל מבחני האיכות עברו בהצלחה"
            else:
                new_state = "carmit_rejected"
                failed_gates = [k for k, v in gate_results.items() if not v["passed"]]
                decision_reasoning = f"נכשל במבחנים: {', '.join(failed_gates)}"

            # Store gate results in match_state_history
            await self._store_match_review(
                match_id=match_id,
                from_state="found",
                to_state=new_state,
                gate_results=gate_results,
                reasoning=decision_reasoning,
            )

            # Update match state (persist the rejection reason on the row too)
            await self._update_match_state(
                match_id,
                new_state,
                blocked_reason=decision_reasoning if new_state == "carmit_rejected" else None,
            )

            # If rejected, write note to Pipedrive
            if new_state == "carmit_rejected":
                await self._write_rejection_note_to_pipedrive(
                    match=match,
                    candidate=candidate,
                    job=job,
                    gate_results=gate_results,
                    reasoning=decision_reasoning,
                )

            result = {
                "match_id": str(match_id),
                "new_state": new_state,
                "decision": "approved" if gates_passed else "rejected",
                "gate_results": gate_results,
                "reasoning": decision_reasoning,
                "timestamp": datetime.utcnow().isoformat(),
            }

            logger.info(f"Match review completed: {result}")
            return result

        except Exception as e:
            logger.error(f"Match review failed for match_id={match_id}: {str(e)}", exc_info=True)
            raise

    # ==================== Helper Methods: Claude Integration ====================

    async def _call_claude_for_routing(self, job_context: dict) -> dict[str, Any]:
        """Call Claude Opus for job routing decision.

        Args:
            job_context: Job details and candidate pool context

        Returns:
            {agent_code, confidence, reasoning}
        """
        # Build routing prompt
        agents_list = "\n".join([
            f"- {code} ({data['name']}, {data['domain']}): {', '.join(data['skills'])}"
            for code, data in self.agent_specialties.items()
        ])

        prompt = f"""You are an expert recruiter routing a job to the specialized agent whose DOMAIN best matches the JOB itself.

JOB TO ROUTE (the job text is authoritative — it may be in Hebrew or English):
Job Title: {job_context['job_title']}
Description: {job_context['job_description']}
Qualifications: {job_context['job_qualifications']}
Detected Skills (hint only, may be incomplete): {', '.join(job_context['required_skills'])}
Seniority Level: {job_context['seniority_level']}

AVAILABLE AGENTS:
{agents_list}

TASK:
1. Read the job title, description and qualifications and determine the job's PRIMARY professional domain.
2. Select the SINGLE best-fit agent for that domain (not a tie - pick one clearly).
3. Explain your reasoning in 1-2 sentences, referencing the JOB's own content.
4. Rate confidence 0.0-1.0 (how well this agent's domain fits the job).

CRITICAL ROUTING RULES:
- Route based ONLY on the JOB's own requirements and domain. Do NOT consider who is currently in the candidate database — agents own domains, not the current candidate mix.
- A software-development job (Hebrew: "מפתח/ת", "פיתוח תוכנה", "מהנדס/ת תוכנה"; English: developer, software engineer; languages like Python/Java/C++/C#/.NET; cloud/microservices/ML) goes to naama (Software) — even if the job also mentions team leadership or project coordination.
- Reserve gc (General) ONLY for jobs that genuinely fall outside every specialist domain (e.g. pure procurement, office administration, budgeting, logistics, non-technical business operations). Engineering and development roles must NEVER go to gc.
- The Hebrew job title alone is usually enough to identify the domain — read it carefully.

Return ONLY valid JSON (no markdown, no extra text):
{{
  "agent_code": "string (one of: alik, naama, dganit, ofir, itai, lior, gc)",
  "confidence": 0.0-1.0,
  "reasoning": "string (1-2 sentences)"
}}"""

        try:
            # Call Claude Opus (self.claude.model should be "claude-opus-4-1")
            messages = [{"role": "user", "content": prompt}]
            system = "You are an expert recruiter routing jobs to specialized agents. Return ONLY valid JSON."

            response = await self.claude._make_request_with_retry(messages, system)

            # Extract content
            if not response.get("content"):
                raise ValueError("No content in Claude response")

            response_text = response["content"][0]["text"]

            # Parse JSON
            decision = self.claude._extract_json(response_text)

            # Validate response
            if "agent_code" not in decision or "confidence" not in decision:
                raise ValueError(f"Missing required fields in Claude response: {decision}")

            agent_code = decision.get("agent_code", "").lower()
            if agent_code not in self.agent_specialties:
                logger.warning(f"Claude returned invalid agent code: {agent_code}, defaulting to 'gc'")
                agent_code = "gc"

            confidence = float(decision.get("confidence", 0.5))
            reasoning = decision.get("reasoning", "No reasoning provided")

            return {
                "agent_code": agent_code,
                "confidence": min(max(confidence, 0.0), 1.0),  # Clamp 0.0-1.0
                "reasoning": reasoning,
            }

        except Exception as e:
            logger.error(f"Claude routing failed: {str(e)}, defaulting to 'gc'")
            return {
                "agent_code": "gc",
                "confidence": 0.5,
                "reasoning": f"Defaulted to general agent due to routing error: {str(e)}",
            }

    # ==================== Helper Methods: Quality Gates ====================

    async def _check_past_rejection_gate(self, candidate_id: str, job_id: str) -> dict[str, Any]:
        """GATE 1: Check if candidate was previously rejected for this job or similar.

        Args:
            candidate_id: Candidate ID
            job_id: Job ID

        Returns:
            {passed: bool, reason: str}
        """
        try:
            # Query match_state_history for past rejections
            response = await self.supabase.table("match_state_history").select("*").eq(
                "candidate_id", candidate_id
            ).eq("job_id", job_id).eq("to_state", "carmit_rejected").execute()

            if response.data and len(response.data) > 0:
                latest_rejection = response.data[-1]
                reason = f"Candidate previously rejected for this role on {latest_rejection.get('created_at')}"
                return {"passed": False, "reason": reason}

            return {"passed": True, "reason": None}

        except Exception as e:
            logger.error(f"Past rejection gate check failed: {str(e)}")
            # Default to passing on error
            return {"passed": True, "reason": None}

    async def _check_already_declined_gate(self, candidate_id: str, job_id: str) -> dict[str, Any]:
        """GATE 2: Check if candidate already declined this job.

        Args:
            candidate_id: Candidate ID
            job_id: Job ID

        Returns:
            {passed: bool, reason: str}
        """
        try:
            # Check candidate declining_status
            response = await self.supabase.table("candidates").select("declining_status").eq(
                "id", candidate_id
            ).single().execute()

            candidate = response.data if response.data else {}
            declining_status = candidate.get("declining_status", [])

            if isinstance(declining_status, list) and str(job_id) in [str(j) for j in declining_status]:
                return {"passed": False, "reason": "Candidate previously declined this job"}

            return {"passed": True, "reason": None}

        except Exception as e:
            logger.error(f"Already declined gate check failed: {str(e)}")
            return {"passed": True, "reason": None}

    async def _check_conflict_of_interest_gate(self, candidate: dict, job: dict) -> dict[str, Any]:
        """GATE 3: Check for conflict of interest (same company, competitor, etc).

        Args:
            candidate: Candidate object
            job: Job object

        Returns:
            {passed: bool, reason: str}
        """
        try:
            candidate_company = candidate.get("current_company", "").lower()
            job_company = job.get("company", "").lower()

            # Check if candidate currently works at job company
            if candidate_company == job_company and candidate_company:
                return {"passed": False, "reason": f"Candidate currently employed at {candidate_company}"}

            # Check for known competitors (simplified check)
            competitors = {
                "company_a": ["company_b", "company_c"],
                "company_b": ["company_a", "company_c"],
            }

            if candidate_company in competitors and job_company in competitors.get(candidate_company, []):
                return {"passed": False, "reason": f"Competitor conflict: {candidate_company} vs {job_company}"}

            return {"passed": True, "reason": None}

        except Exception as e:
            logger.error(f"Conflict of interest gate check failed: {str(e)}")
            return {"passed": True, "reason": None}

    async def _check_clearance_gate(self, candidate: dict, job: dict) -> dict[str, Any]:
        """GATE 4: Check if candidate's security clearance matches job requirement.

        Args:
            candidate: Candidate object
            job: Job object

        Returns:
            {passed: bool, reason: str}
        """
        try:
            raw_candidate_clearance = candidate.get("clearance_level")
            job_required_clearance = job.get("job_security_clearance") or "none"

            # Rank via the canonical Hebrew-aware ranker (רמה 1 = highest).
            # Falls back to the local dict for any value it can't parse.
            from pandapower.routers.admin.recruitment_departments import _clearance_rank
            required_level = _clearance_rank(job_required_clearance)
            if required_level is None:
                required_level = self.clearance_levels.get(str(job_required_clearance).lower(), 0)

            # If the job has no real clearance requirement, everyone passes.
            if required_level == 0:
                return {"passed": True, "reason": "No clearance required for this role"}

            # UNKNOWN candidate clearance (null / empty) is NOT proof of an
            # insufficient clearance — CV extraction frequently fails to capture
            # it. Auto-rejecting these silently killed otherwise-strong matches.
            # Defer to a human: pass the gate so the match reaches Tal, who can
            # ask the candidate to confirm their actual clearance.
            cand_str = str(raw_candidate_clearance).strip() if raw_candidate_clearance is not None else ""
            if not cand_str:
                return {
                    "passed": True,
                    "reason": (
                        f"Candidate clearance unknown; job requires "
                        f"{job_required_clearance} — deferring to human review (Tal)."
                    ),
                }

            candidate_level = _clearance_rank(cand_str)
            if candidate_level is None:
                candidate_level = self.clearance_levels.get(cand_str.lower(), 0)

            if candidate_level < required_level:
                return {
                    "passed": False,
                    "reason": f"Insufficient clearance: candidate {cand_str} < required {job_required_clearance}",
                }

            return {"passed": True, "reason": f"Clearance match: {cand_str} >= {job_required_clearance}"}

        except Exception as e:
            logger.error(f"Clearance gate check failed: {str(e)}")
            return {"passed": False, "reason": f"Clearance check error: {str(e)}"}

    async def _check_quality_score_gate(self, match: dict) -> dict[str, Any]:
        """GATE 5: Check if match score meets minimum threshold.

        Args:
            match: Match object with match_score

        Returns:
            {passed: bool, reason: str}
        """
        try:
            score = float(match.get("match_score", 0.0))

            if score < self.match_score_threshold:
                return {
                    "passed": False,
                    "reason": f"Score {score:.2f} below threshold {self.match_score_threshold:.2f}",
                }

            return {"passed": True, "reason": f"Score {score:.2f} meets threshold"}

        except Exception as e:
            logger.error(f"Quality score gate check failed: {str(e)}")
            return {"passed": True, "reason": None}

    @staticmethod
    def _collect_candidate_skills(candidate: dict) -> list[str]:
        """Gather every skill signal we have for a candidate.

        The denormalized ``key_skills`` array is frequently empty even for
        strong candidates — the rich CV data actually lives under
        ``extracted_from_cv.extracted_fields`` (technical_skills / soft_skills).
        Relying on ``key_skills`` alone is what produced the false
        "Candidate has no recorded skills" rejections.
        """
        skills: list[str] = []

        def _extend(value: Any) -> None:
            if isinstance(value, list):
                skills.extend(str(s) for s in value if s)
            elif isinstance(value, str) and value.strip():
                skills.append(value)

        _extend(candidate.get("key_skills"))

        extracted = candidate.get("extracted_from_cv") or {}
        if isinstance(extracted, dict):
            fields = extracted.get("extracted_fields") or {}
            if isinstance(fields, dict):
                _extend(fields.get("technical_skills"))
                _extend(fields.get("soft_skills"))
                # Technologies named inside experience entries are skills too.
                for exp in fields.get("experience") or []:
                    if isinstance(exp, dict):
                        _extend(exp.get("technologies"))

        # De-dupe case-insensitively while preserving order.
        seen: set[str] = set()
        unique: list[str] = []
        for s in skills:
            key = s.strip().lower()
            if key and key not in seen:
                seen.add(key)
                unique.append(s.strip())
        return unique

    @staticmethod
    def _normalize_token(text: str) -> str:
        """Lowercase and strip punctuation so 'C#', 'c #', 'C-Sharp' align."""
        import re
        return re.sub(r"[^a-z0-9֐-׿]+", "", text.lower())

    def _skills_overlap_job_text(self, skills: list[str], job_text: str) -> bool:
        """Normalized, bidirectional overlap between skills and job text.

        Far more forgiving than the old raw ``skill in job_text`` substring
        check: both sides are normalized (punctuation stripped, lowercased),
        and we match whole normalized skill tokens against the normalized
        job text. Short tokens (<=2 chars) are ignored to avoid noise.
        """
        norm_job = self._normalize_token(job_text)
        if not norm_job:
            return False
        for skill in skills:
            norm_skill = self._normalize_token(skill)
            if len(norm_skill) >= 3 and norm_skill in norm_job:
                return True
        return False

    async def _check_relevant_skills_gate(
        self, candidate: dict, job: dict, match: dict
    ) -> dict[str, Any]:
        """GATE 6: Backstop check that the candidate has relevant skills.

        Design note: ``match_score`` is produced by Claude in agent_matching,
        which ALREADY performs a full semantic evaluation of the candidate's
        skills against the job qualifications. This gate must therefore be a
        lightweight backstop — not a second, cruder opinion that overrides the
        LLM. It only hard-rejects when there is genuinely no skill signal AND
        the LLM score is also weak.
        """
        try:
            skills = self._collect_candidate_skills(candidate)
            job_text = " ".join(
                str(job.get(k, "") or "")
                for k in ("job_qualifications", "job_description", "job_title")
            )

            try:
                score = float(match.get("match_score", 0.0) or 0.0)
            except (TypeError, ValueError):
                score = 0.0
            score_ok = score >= self.match_score_threshold

            # No skill signal anywhere = a data-extraction gap, not proof of
            # irrelevance. Defer to the LLM score rather than auto-rejecting.
            if not skills:
                if score_ok:
                    return {
                        "passed": True,
                        "reason": (
                            "No explicit skills list, but the match score "
                            f"({score:.2f}) clears the bar — deferring to the "
                            "LLM evaluation."
                        ),
                    }
                return {
                    "passed": False,
                    "reason": "No skills recorded and match score below threshold",
                }

            # Positive confirmation: a normalized skill overlaps the job text.
            if self._skills_overlap_job_text(skills, job_text):
                return {
                    "passed": True,
                    "reason": "Relevant skills confirmed against job requirements",
                }

            # No literal overlap, but the LLM already judged skills-vs-quals
            # semantically (Hebrew/English, synonyms, paraphrase). Trust it.
            if score_ok:
                return {
                    "passed": True,
                    "reason": (
                        "No literal keyword overlap, but the match score "
                        f"({score:.2f}) clears the bar — deferring to the LLM "
                        "evaluation."
                    ),
                }

            return {
                "passed": False,
                "reason": (
                    "No relevant skills found and score below threshold. "
                    f"Candidate skills: {', '.join(skills[:3])}"
                ),
            }

        except Exception as e:
            logger.error(f"Skills gate check failed: {str(e)}")
            # Fail open: a bug in this backstop should not block the pipeline.
            return {"passed": True, "reason": f"Skills check error (passed open): {str(e)}"}

    # ==================== Helper Methods: Database Operations ====================

    async def _get_job(self, job_id: str) -> dict:
        """Get job by ID from database."""
        try:
            response = await self.supabase.table("jobs").select("*").eq("id", job_id).single().execute()
            return response.data or {}
        except Exception as e:
            logger.error(f"Failed to get job {job_id}: {str(e)}")
            return {}

    async def _get_candidate(self, candidate_id: str) -> dict:
        """Get candidate by ID from database."""
        try:
            response = await self.supabase.table("candidates").select("*").eq("id", candidate_id).single().execute()
            return response.data or {}
        except Exception as e:
            logger.error(f"Failed to get candidate {candidate_id}: {str(e)}")
            return {}

    async def _get_match(self, match_id: str) -> dict:
        """Get match by ID from database."""
        try:
            response = await self.supabase.table("matches").select("*").eq("id", match_id).single().execute()
            return response.data or {}
        except Exception as e:
            logger.error(f"Failed to get match {match_id}: {str(e)}")
            return {}

    async def _get_candidate_pool_stats(self) -> dict:
        """Get candidate pool statistics for routing context."""
        try:
            response = await self.supabase.table("candidates").select("*").execute()
            candidates = response.data or []

            # Analyze skills distribution
            all_skills = []
            for candidate in candidates:
                skills = candidate.get("key_skills", [])
                if isinstance(skills, list):
                    all_skills.extend(skills)

            # Get top domains
            from collections import Counter
            skill_counts = Counter(all_skills)
            top_domains = [skill for skill, _ in skill_counts.most_common(5)]

            return {
                "total": len(candidates),
                "top_domains": top_domains,
            }
        except Exception as e:
            logger.error(f"Failed to get candidate pool stats: {str(e)}")
            return {"total": 0, "top_domains": []}

    async def _store_routing_decision(
        self,
        job_id: str,
        agent_code: str,
        confidence: float,
        reasoning: str,
    ) -> None:
        """Store routing decision in agent_logs table."""
        try:
            await self.supabase.table("agent_logs").insert({
                "related_job_id": str(job_id),
                "agent_code": agent_code,
                "action": "route_job",
                "milestone": "job_routed_to_agent",
                "output_payload": {
                    "confidence": confidence,
                    "timestamp": datetime.utcnow().isoformat(),
                },
                "reasoning": reasoning,
                "status": "success",
            }).execute()
        except Exception as e:
            logger.error(f"Failed to store routing decision: {str(e)}")
            raise

    async def _update_job_routing(
        self,
        job_id: str,
        agent_code: str,
        confidence: float,
        reasoning: str,
    ) -> None:
        """Update job with assigned agent."""
        try:
            # Just update the assigned agent - store reasoning in agent_logs instead
            await self.supabase.table("jobs").update({
                "assigned_agent_code": agent_code,
            }).eq("id", str(job_id)).execute()
        except Exception as e:
            logger.error(f"Failed to update job routing: {str(e)}")
            raise

    async def _store_match_review(
        self,
        match_id: str,
        from_state: str,
        to_state: str,
        gate_results: dict,
        reasoning: str,
    ) -> None:
        """Store match review results in match_state_history — best-effort.

        Production's match_state_history schema is narrower than this code
        was written for (notably the JSONB ``details`` column is missing —
        PGRST204). Rather than blowing up the whole review loop, we try a
        rich insert first and progressively drop columns the schema doesn't
        know about. If even the bare minimum fails we just log and continue
        so the caller can still flip current_state — keeping audit history
        is nice-to-have, but advancing the pipeline is critical.
        """
        # Production schema (verified) requires `reasoning` NOT NULL as a
        # plain text column, but does NOT have the JSONB `details` column
        # this code was originally written for. We include BOTH so we work
        # against either schema.
        full_row = {
            "match_id": str(match_id),
            "from_state": from_state,
            "to_state": to_state,
            "reasoning": reasoning or "(no reasoning recorded)",
            "details": {
                "gate_results": gate_results,
                "decision_reasoning": reasoning,
                "timestamp": datetime.utcnow().isoformat(),
            },
            "created_at": datetime.utcnow().isoformat(),
        }

        # Each attempt drops one more potentially-missing column. Mirrors
        # the pattern used in routers/webhooks.py:_log_inbound_message.
        # Order matters: `details` first (production doesn't have it),
        # then `created_at` (likely server-default).
        attempts: list[list[str]] = [
            [],                          # full row
            ["details"],                 # drop JSONB details (PGRST204 in prod)
            ["details", "created_at"],   # drop server-default-eligible column too
        ]
        for drop in attempts:
            payload = {k: v for k, v in full_row.items() if k not in drop}
            try:
                await self.supabase.table("match_state_history").insert(payload).execute()
                return
            except Exception as e:
                msg = str(e)[:200]
                # PGRST204 / 42703 = column missing. Anything else (network /
                # permission / table absent) → no point retrying; log and bail.
                if "does not exist" in msg or "schema cache" in msg or "PGRST204" in msg:
                    continue
                logger.warning(
                    f"match_state_history insert failed for {match_id} ({from_state}→{to_state}): {msg}"
                )
                return
        logger.info(
            f"match_state_history unavailable — skipped audit row for {match_id} "
            f"({from_state}→{to_state}); current_state will still be updated"
        )

    async def _update_match_state(
        self, match_id: str, new_state: str, blocked_reason: str | None = None
    ) -> None:
        """Update match state (and, on rejection, the human-readable reason).

        Persisting ``carmit_blocked_reason`` on the row means single-record
        reads and dashboards no longer have to join match_state_history to
        learn why a match was rejected. Best-effort on the reason column so a
        narrower production schema never blocks the state transition.
        """
        payload = {
            "current_state": new_state,
            "updated_at": datetime.utcnow().isoformat(),
        }
        if blocked_reason:
            payload["carmit_blocked_reason"] = blocked_reason
        try:
            await self.supabase.table("matches").update(payload).eq(
                "id", str(match_id)
            ).execute()
        except Exception as e:
            # If the reason column is rejected by the schema, retry without it
            # rather than losing the state transition.
            if blocked_reason:
                logger.warning(
                    f"Match update with blocked_reason failed ({e}); "
                    "retrying without it"
                )
                try:
                    await self.supabase.table("matches").update({
                        "current_state": new_state,
                        "updated_at": datetime.utcnow().isoformat(),
                    }).eq("id", str(match_id)).execute()
                    return
                except Exception as e2:
                    logger.error(f"Failed to update match state: {str(e2)}")
                    raise
            logger.error(f"Failed to update match state: {str(e)}")
            raise

    async def _write_rejection_note_to_pipedrive(
        self,
        match: dict,
        candidate: dict,
        job: dict,
        gate_results: dict,
        reasoning: str,
    ) -> None:
        """Write rejection note to Pipedrive deal."""
        try:
            # Get failed gates
            failed_gates = [k for k, v in gate_results.items() if not v["passed"]]
            failed_details = "\n".join([
                f"  - {gate}: {gate_results[gate].get('reason', 'No details')}"
                for gate in failed_gates
            ])

            note_text = f"""❌ Carmit Orchestrator - Match Rejected

Candidate: {candidate.get('name', 'Unknown')}
Position: {job.get('job_title', 'Unknown')}
Match Score: {match.get('match_score', 0):.2f}

Failed Gates:
{failed_details}

Decision Reasoning: {reasoning}

Timestamp: {datetime.utcnow().isoformat()}
Status: Do not retry before review period expires"""

            # Get Pipedrive deal ID from job
            deal_id = job.get("pipedrive_deal_id")
            if deal_id:
                await self.pipedrive.write_note_to_deal(str(deal_id), note_text)
                logger.info(f"Wrote rejection note to Pipedrive deal {deal_id}")

        except Exception as e:
            logger.error(f"Failed to write rejection note to Pipedrive: {str(e)}")
            # Don't raise - rejection note is informational

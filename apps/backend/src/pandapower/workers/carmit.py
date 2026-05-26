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
CLEARANCE_LEVELS = {
    None: 0,
    "none": 0,
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

        # Configuration
        self.match_score_threshold = self.settings.get("CARMIT_MATCH_SCORE_THRESHOLD", 0.70)
        self.clearance_levels = self.settings.get("CARMIT_CLEARANCE_LEVELS", CLEARANCE_LEVELS)

        # Agent specialties (from Phase 4)
        self.agent_specialties = {
            "alik": {"name": "אליק", "domain": "Electronics", "skills": ["FPGA", "VHDL", "PCB", "RF", "Analog"]},
            "naama": {"name": "נעמה", "domain": "Software", "skills": ["Python", "Java", "C++", "Cloud", "Microservices"]},
            "dganit": {"name": "דגנית", "domain": "QA", "skills": ["Testing", "Selenium", "LoadRunner", "Automation"]},
            "ofir": {"name": "אופיר", "domain": "Systems", "skills": ["Linux", "Networking", "DevOps", "Container"]},
            "itai": {"name": "איתי", "domain": "IT", "skills": ["Infrastructure", "Windows", "Helpdesk", "Networks"]},
            "lior": {"name": "ליאור", "domain": "Mechanical", "skills": ["CAD", "SOLIDWORKS", "FEA", "Manufacturing"]},
            "gc": {"name": "GC", "domain": "General", "skills": ["All other domains"]},
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

            # Determine final decision
            if gates_passed:
                new_state = "carmit_approved"
                decision_reasoning = "All quality gates passed"
            else:
                new_state = "carmit_rejected"
                failed_gates = [k for k, v in gate_results.items() if not v["passed"]]
                decision_reasoning = f"Failed gates: {', '.join(failed_gates)}"

            # Store gate results in match_state_history
            await self._store_match_review(
                match_id=match_id,
                from_state="found",
                to_state=new_state,
                gate_results=gate_results,
                reasoning=decision_reasoning,
            )

            # Update match state
            await self._update_match_state(match_id, new_state)

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

        candidate_summary = (
            f"{job_context['candidate_pool']['total']} candidates total, "
            f"with top expertise in: {', '.join(job_context['candidate_pool']['top_domains'])}"
        )

        prompt = f"""You are an expert recruiter routing jobs to specialized agents.

CONTEXT:
Job Title: {job_context['job_title']}
Description: {job_context['job_description']}
Required Skills: {', '.join(job_context['required_skills'])}
Seniority Level: {job_context['seniority_level']}
Candidate Pool: {candidate_summary}

AVAILABLE AGENTS:
{agents_list}

TASK:
1. Analyze the job requirements against agent specialties
2. Select the SINGLE best-fit agent (not a tie - pick one clearly)
3. Explain your reasoning in 1-2 sentences
4. Rate confidence 0.0-1.0 (how well this agent fits the job)

CONSTRAINTS:
- Be deterministic and reproducible
- Explain your logic clearly
- Rate confidence realistically (0.8+ for good matches, 0.6+ for okay matches)
- If no perfect fit, pick the closest domain match

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
            candidate_clearance = str(candidate.get("clearance_level", "none")).lower()
            job_required_clearance = str(job.get("required_clearance", "none")).lower()

            # Get clearance levels
            candidate_level = self.clearance_levels.get(candidate_clearance, 0)
            required_level = self.clearance_levels.get(job_required_clearance, 0)

            if candidate_level < required_level:
                return {
                    "passed": False,
                    "reason": f"Insufficient clearance: candidate {candidate_clearance} < required {job_required_clearance}",
                }

            return {"passed": True, "reason": f"Clearance match: {candidate_clearance} >= {job_required_clearance}"}

        except Exception as e:
            logger.error(f"Clearance gate check failed: {str(e)}")
            return {"passed": True, "reason": None}

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
        """Store match review results in match_state_history."""
        try:
            await self.supabase.table("match_state_history").insert({
                "match_id": str(match_id),
                "from_state": from_state,
                "to_state": to_state,
                "details": {
                    "gate_results": gate_results,
                    "decision_reasoning": reasoning,
                    "timestamp": datetime.utcnow().isoformat(),
                },
                "created_at": datetime.utcnow().isoformat(),
            }).execute()
        except Exception as e:
            logger.error(f"Failed to store match review: {str(e)}")
            raise

    async def _update_match_state(self, match_id: str, new_state: str) -> None:
        """Update match state."""
        try:
            await self.supabase.table("matches").update({
                "current_state": new_state,
                "updated_at": datetime.utcnow().isoformat(),
            }).eq("id", str(match_id)).execute()
        except Exception as e:
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

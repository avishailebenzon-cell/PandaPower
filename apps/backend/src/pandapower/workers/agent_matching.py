import asyncio
import logging
from typing import Any, Optional
from datetime import datetime, timedelta
import json
from pandapower.integrations.claude_api import AnthropicClient
from pandapower.core.supabase import get_supabase_client

logger = logging.getLogger(__name__)

# Agent domain configurations
AGENT_CONFIGS = {
    "alik": {
        "name": "Alik",
        "domain": "Electronics & Hardware",
        "keywords": "Verilog, VHDL, FPGA, PCB, RF, Analog, Digital Design, Embedded Systems",
        "skill_categories": ["electronics", "hardware", "fpga", "embedded"],
    },
    "naama": {
        "name": "Naama",
        "domain": "Software & Cloud",
        "keywords": "Python, Java, C++, Cloud, Microservices, AWS, Azure, Docker, Kubernetes",
        "skill_categories": ["software", "backend", "cloud", "devops"],
    },
    "dganit": {
        "name": "Dganit",
        "domain": "QA & Testing",
        "keywords": "Testing, Selenium, LoadRunner, Automation, Test Frameworks, Performance",
        "skill_categories": ["qa", "testing", "automation", "quality"],
    },
    "ofir": {
        "name": "Ofir",
        "domain": "Systems & DevOps",
        "keywords": "Linux, Networking, DevOps, Container, Kubernetes, Infrastructure",
        "skill_categories": ["devops", "systems", "linux", "infrastructure"],
    },
    "itai": {
        "name": "Itai",
        "domain": "IT & Infrastructure",
        "keywords": "Infrastructure, Windows, Helpdesk, Networks, Active Directory, IT Support",
        "skill_categories": ["infrastructure", "it", "windows", "support"],
    },
    "lior": {
        "name": "Lior",
        "domain": "Mechanical Engineering",
        "keywords": "CAD, SOLIDWORKS, FEA, Manufacturing, Mechanical Design, 3D Modeling",
        "skill_categories": ["mechanical", "cad", "manufacturing", "design"],
    },
    "gc": {
        "name": "GC (Catch-all)",
        "domain": "General Domain Coverage",
        "keywords": "Any domain not covered by specialized agents",
        "skill_categories": ["general"],
    },
}


class AgentMatchingWorker:
    """Orchestrates candidate-job matching for all 7 specialized agents.

    This is the core Phase 4 implementation that:
    1. Finds candidates matching a job (via find_matches_for_job)
    2. Finds jobs matching a candidate (via find_matches_for_candidate)
    3. Uses Claude Sonnet for scoring with prompt caching
    4. Creates matches in DB and logs all activity
    """

    def __init__(self, supabase_client: Any, claude_client: AnthropicClient):
        self.supabase = supabase_client
        self.claude = claude_client

    async def find_matches_for_job(self, job_id: str, agent_code: str) -> dict:
        """Find candidate matches for a specific job assigned to agent.

        Entry point 1: Called when a new job is created and assigned to an agent.

        Args:
            job_id: UUID of job to match
            agent_code: One of: alik, naama, dganit, ofir, itai, lior, gc

        Returns: {
            "total_candidates_evaluated": int,
            "matches_found": int,
            "tokens_used": int,
            "duration_ms": float,
            "errors": []
        }
        """
        start_time = datetime.utcnow()
        result = {
            "total_candidates_evaluated": 0,
            "matches_found": 0,
            "tokens_used": 0,
            "duration_ms": 0,
            "errors": [],
        }

        try:
            # Fetch job details
            job_response = await self.supabase.table("jobs").select("*").eq("id", job_id).single().execute()
            job = job_response.data
            if not job:
                logger.error(f"Job {job_id} not found")
                return result

            # Validate agent code
            agent_config = self._get_agent_config(agent_code)
            if not agent_config:
                logger.error(f"Unknown agent: {agent_code}")
                return result

            logger.info(f"Starting matching for job {job_id} ({job['title']}) with agent {agent_code}")

            # Fetch candidates matching agent's domain (limit to 100 per run to avoid overload)
            candidates = await self._fetch_domain_candidates(agent_config, limit=100)
            result["total_candidates_evaluated"] = len(candidates)

            if not candidates:
                logger.info(f"No candidates found for agent {agent_code} domain")
                result["duration_ms"] = (datetime.utcnow() - start_time).total_seconds() * 1000
                return result

            # Score each candidate-job pair with Claude
            for idx, candidate in enumerate(candidates):
                try:
                    match_info = await self._score_candidate_job_pair(
                        candidate, job, agent_code, agent_config
                    )

                    # Threshold for creating a match: 70 out of 100
                    if match_info["score"] >= 70:
                        # Create match in DB
                        await self._create_match(
                            candidate_id=candidate["id"],
                            job_id=job_id,
                            score=match_info["score"],
                            reasoning=match_info["reasoning"],
                            strengths=match_info["strengths"],
                            gaps=match_info["gaps"],
                            agent_code=agent_code,
                            tokens_used=match_info["tokens_used"],
                            duration_ms=match_info["duration_ms"],
                        )
                        result["matches_found"] += 1
                        result["tokens_used"] += match_info["tokens_used"]

                        logger.info(
                            f"[{idx+1}/{len(candidates)}] Match found: {candidate['name']} -> "
                            f"{job['title']} (score: {match_info['score']})"
                        )
                    else:
                        result["tokens_used"] += match_info["tokens_used"]
                        logger.debug(
                            f"[{idx+1}/{len(candidates)}] Score {match_info['score']} < threshold: "
                            f"{candidate['name']} vs {job['title']}"
                        )

                except Exception as e:
                    logger.error(f"Error scoring candidate {candidate['id']}: {e}")
                    result["errors"].append({"candidate_id": candidate["id"], "error": str(e)})

            # Log overall agent activity
            await self._log_agent_activity(
                agent_code=agent_code,
                action="find_matches_for_job",
                job_id=job_id,
                total_evaluated=result["total_candidates_evaluated"],
                matches_found=result["matches_found"],
                tokens_used=result["tokens_used"],
            )

            result["duration_ms"] = (datetime.utcnow() - start_time).total_seconds() * 1000
            logger.info(
                f"Job matching completed: {result['matches_found']} matches from "
                f"{result['total_candidates_evaluated']} evaluated in {result['duration_ms']:.0f}ms"
            )
            return result

        except Exception as e:
            logger.error(f"Job matching failed for {job_id}: {e}", exc_info=True)
            result["errors"].append({"batch": str(e)})
            return result

    async def find_matches_for_candidate(self, candidate_id: str, agent_code: str) -> dict:
        """Find job matches for a specific candidate assigned to agent.

        Entry point 2: Called when a new candidate is created and needs to find open jobs.

        Args:
            candidate_id: UUID of candidate to match
            agent_code: Agent handling this candidate

        Returns: {
            "total_jobs_evaluated": int,
            "matches_found": int,
            "tokens_used": int,
            "duration_ms": float,
            "errors": []
        }
        """
        start_time = datetime.utcnow()
        result = {
            "total_jobs_evaluated": 0,
            "matches_found": 0,
            "tokens_used": 0,
            "duration_ms": 0,
            "errors": [],
        }

        try:
            # Fetch candidate details
            cand_response = (
                await self.supabase.table("candidates").select("*").eq("id", candidate_id).single().execute()
            )
            candidate = cand_response.data
            if not candidate:
                logger.error(f"Candidate {candidate_id} not found")
                return result

            # Validate agent
            agent_config = self._get_agent_config(agent_code)
            if not agent_config:
                logger.error(f"Unknown agent: {agent_code}")
                return result

            logger.info(f"Starting matching for candidate {candidate['name']} with agent {agent_code}")

            # Fetch open jobs not yet matched to this agent's candidates
            jobs_response = (
                await self.supabase.table("jobs").select("*").eq("is_active", True).limit(100).execute()
            )
            jobs = jobs_response.data or []
            result["total_jobs_evaluated"] = len(jobs)

            if not jobs:
                logger.info("No open jobs found")
                result["duration_ms"] = (datetime.utcnow() - start_time).total_seconds() * 1000
                return result

            # Score each job-candidate pair
            for idx, job in enumerate(jobs):
                # Skip if already matched
                existing = await (
                    self.supabase.table("matches")
                    .select("id")
                    .eq("candidate_id", candidate_id)
                    .eq("job_id", job["id"])
                    .execute()
                )
                if existing.data:
                    logger.debug(f"Match already exists: {candidate_id} <-> {job['id']}")
                    continue

                try:
                    match_info = await self._score_candidate_job_pair(
                        candidate, job, agent_code, agent_config
                    )

                    if match_info["score"] >= 70:
                        await self._create_match(
                            candidate_id=candidate_id,
                            job_id=job["id"],
                            score=match_info["score"],
                            reasoning=match_info["reasoning"],
                            strengths=match_info["strengths"],
                            gaps=match_info["gaps"],
                            agent_code=agent_code,
                            tokens_used=match_info["tokens_used"],
                            duration_ms=match_info["duration_ms"],
                        )
                        result["matches_found"] += 1
                        result["tokens_used"] += match_info["tokens_used"]

                        logger.info(
                            f"[{idx+1}/{len(jobs)}] Match found: {candidate['name']} -> "
                            f"{job['title']} ({match_info['score']})"
                        )
                    else:
                        result["tokens_used"] += match_info["tokens_used"]

                except Exception as e:
                    logger.error(f"Error scoring job {job['id']}: {e}")
                    result["errors"].append({"job_id": job["id"], "error": str(e)})

            result["duration_ms"] = (datetime.utcnow() - start_time).total_seconds() * 1000
            logger.info(
                f"Candidate matching completed: {result['matches_found']} matches from "
                f"{result['total_jobs_evaluated']} jobs in {result['duration_ms']:.0f}ms"
            )
            return result

        except Exception as e:
            logger.error(f"Candidate matching failed: {e}", exc_info=True)
            result["errors"].append({"batch": str(e)})
            return result

    async def _score_candidate_job_pair(
        self, candidate: dict, job: dict, agent_code: str, agent_config: dict
    ) -> dict:
        """Use Claude Sonnet to score a candidate-job match.

        Returns: {
            "score": 0-100,
            "reasoning": "text",
            "strengths": ["list"],
            "gaps": ["list"],
            "tokens_used": int,
            "duration_ms": float
        }
        """
        start_time = datetime.utcnow()

        # Build prompt for Claude
        prompt = self._build_matching_prompt(candidate, job, agent_code, agent_config)

        try:
            # Call Claude Sonnet (faster and cheaper than Opus for matching)
            response = await self.claude.match_score_with_json(
                prompt=prompt, model="claude-sonnet-4-5"
            )

            # Parse response
            data = response.get("parsed", {})

            return {
                "score": int(data.get("score", 0)),
                "reasoning": data.get("reasoning", ""),
                "strengths": data.get("strengths", []),
                "gaps": data.get("gaps", []),
                "tokens_used": response.get("tokens_used", 0),
                "duration_ms": (datetime.utcnow() - start_time).total_seconds() * 1000,
            }

        except Exception as e:
            logger.error(f"Claude scoring failed: {e}")
            raise

    def _build_matching_prompt(
        self, candidate: dict, job: dict, agent_code: str, agent_config: dict
    ) -> str:
        """Build structured prompt for Claude to score a match.

        CRITICAL UPDATE: Now includes ALL extracted CV data fields:
        - Technical & soft skills (not just key_skills)
        - Detailed experience with achievements and technologies
        - Education with degrees and honors
        - Certifications and military service
        - Spoken languages with proficiency
        - Professional summary
        - Clearance evidence from CV text

        This ensures agents have access to ALL 30+ data points from CV parsing.
        """

        # Extract COMPREHENSIVE candidate info from enriched CV data
        cand_name = candidate.get("name", "Unknown")
        cand_location = candidate.get("location")
        cand_clearance = candidate.get("clearance_level")
        cand_years = candidate.get("years_of_experience", "Unknown")
        cand_summary = candidate.get("summary", "")

        # NEW: Extract technical and soft skills separately
        technical_skills = candidate.get("technical_skills", []) or []
        soft_skills = candidate.get("soft_skills", []) or []

        # NEW: Extract detailed experience array
        experience_list = candidate.get("experience", []) or []

        # NEW: Extract education details
        education_list = candidate.get("education", []) or []

        # NEW: Extract certifications
        certifications_list = candidate.get("certifications", []) or []

        # NEW: Extract military service
        military_service = candidate.get("military_service", {})

        # NEW: Extract spoken languages with proficiency
        spoken_languages = candidate.get("spoken_languages", []) or []

        # NEW: Extract clearance evidence
        clearance_evidence = candidate.get("clearance_keywords_matched", []) or []

        # Extract job info
        job_title = job.get("title", "")
        job_desc = job.get("description", "")
        job_quals = job.get("qualifications", "")  # CRITICAL: qualifications more important than description
        job_clearance = job.get("required_security_clearance")
        job_domain = job.get("required_domain", "")

        # Format skills for readability
        technical_skills_text = ", ".join(technical_skills[:20]) if technical_skills else "Not listed"
        soft_skills_text = ", ".join(soft_skills[:10]) if soft_skills else "Not listed"

        # Format experience details
        experience_text = ""
        if experience_list:
            for exp in experience_list[:5]:  # Limit to 5 most recent
                position = exp.get("position", "")
                company = exp.get("company", "")
                description = exp.get("description", "")
                achievements = exp.get("achievements", [])
                technologies = exp.get("technologies", [])

                exp_section = f"• {position} at {company}"
                if description:
                    exp_section += f": {description[:150]}"
                if achievements:
                    exp_section += f" | Key achievements: {', '.join(achievements[:2])}"
                if technologies:
                    exp_section += f" | Tech: {', '.join(technologies[:3])}"

                experience_text += exp_section + "\n"
        else:
            experience_text = "Not specified"

        # Format education details
        education_text = ""
        if education_list:
            for edu in education_list[:3]:  # Limit to 3 most relevant
                degree = edu.get("degree", "")
                field = edu.get("field", "")
                institution = edu.get("institution", "")
                honors = edu.get("honors", "")

                edu_section = f"• {degree} in {field} from {institution}"
                if honors:
                    edu_section += f" ({honors})"
                education_text += edu_section + "\n"
        else:
            education_text = "Not specified"

        # Format certifications
        certifications_text = ""
        if certifications_list:
            for cert in certifications_list[:5]:
                cert_name = cert.get("name") if isinstance(cert, dict) else cert
                issuer = cert.get("issuer") if isinstance(cert, dict) else ""
                cert_entry = f"• {cert_name}"
                if issuer:
                    cert_entry += f" ({issuer})"
                certifications_text += cert_entry + "\n"
        else:
            certifications_text = "None listed"

        # Format military service
        military_text = ""
        if military_service:
            served = military_service.get("served", False)
            if served:
                unit = military_service.get("unit", "")
                role = military_service.get("role", "")
                rank = military_service.get("rank", "")
                achievements = military_service.get("achievements", [])

                military_text = f"Service: {unit or 'Unknown'}, Role: {role or 'Unknown'}, Rank: {rank or 'N/A'}"
                if achievements:
                    military_text += f" | Achievements: {', '.join(achievements[:2])}"
            else:
                military_text = "No military service"
        else:
            military_text = "No military service data"

        # Format spoken languages
        languages_text = ""
        if spoken_languages:
            for lang in spoken_languages[:5]:
                lang_name = lang.get("language") if isinstance(lang, dict) else lang
                proficiency = lang.get("proficiency") if isinstance(lang, dict) else ""
                lang_entry = f"• {lang_name}"
                if proficiency:
                    lang_entry += f" ({proficiency})"
                languages_text += lang_entry + "\n"
        else:
            languages_text = "Not specified"

        # Format clearance evidence
        clearance_text = ""
        if clearance_evidence:
            clearance_text = "Evidence found in CV:\n" + "\n".join([f"• {e}" for e in clearance_evidence[:5]])
        else:
            clearance_text = "No clearance keywords found in CV"

        prompt = f"""You are a recruitment expert specializing in {agent_config['domain']}.

Evaluate if this candidate is a good match for this job. Weight the job's QUALIFICATIONS section more heavily than description. Use ALL candidate data including detailed experience, education, certifications, military service, and language proficiency.

CANDIDATE PROFILE:
Name: {cand_name}
Location: {cand_location or 'Unknown'}
Years of Experience: {cand_years}

PROFESSIONAL SUMMARY:
{cand_summary[:300] if cand_summary else 'Not provided'}

SKILLS:
Technical Skills ({len(technical_skills)} total):
{technical_skills_text}

Soft Skills ({len(soft_skills)} total):
{soft_skills_text}

DETAILED EXPERIENCE:
{experience_text}

EDUCATION:
{education_text}

CERTIFICATIONS & QUALIFICATIONS:
{certifications_text}

MILITARY SERVICE:
{military_text}

LANGUAGES:
{languages_text}

SECURITY CLEARANCE:
Current Level: {cand_clearance or 'None'}
{clearance_text}

JOB REQUIREMENTS:
Title: {job_title}
Domain: {job_domain or agent_config['domain']}
Required Qualifications (CRITICAL TO MATCH):
{job_quals[:800] if job_quals else 'Not specified'}

Description:
{job_desc[:400] if job_desc else 'Not specified'}

Required Security Clearance: {job_clearance or 'None'}

AGENT SPECIALIZATION:
Agent: {agent_code} ({agent_config['name']})
Focuses on: {agent_config['keywords']}

COMPREHENSIVE EVALUATION CRITERIA:
1. Do the candidate's technical and soft skills directly address job qualifications?
2. Does relevant experience match the role requirements? (weight achievements & technologies)
3. Is education/certification level appropriate for the position?
4. Are there critical skill gaps despite overall experience?
5. Military service/additional context that adds value?
6. Language requirements met? (if applicable)
7. Is there a security clearance gap or mismatch (if required)?

Return ONLY valid JSON (no extra text):
{{
  "score": <integer 0-100 where 70+ is a viable match>,
  "reasoning": "<2-3 sentence explanation covering: relevant experience, key skills match, and any clearance/language concerns>",
  "strengths": ["<concrete match point 1 from CV data>", "<concrete match point 2 from CV data>"],
  "gaps": ["<skill gap if any>", "<clearance gap if any>", "<concern if any>"]
}}"""

        return prompt

    async def _create_match(
        self,
        candidate_id: str,
        job_id: str,
        score: int,
        reasoning: str,
        strengths: list,
        gaps: list,
        agent_code: str,
        tokens_used: int,
        duration_ms: float,
    ) -> None:
        """Create match record in database and log the activity."""

        try:
            # Insert match record
            match_data = {
                "candidate_id": candidate_id,
                "job_id": job_id,
                "match_score": float(score) / 100.0,  # Normalize to 0-1
                "match_reasoning": reasoning,
                "matched_by_agent_code": agent_code,
                "current_state": "found",  # Initial state
                "state_updated_at": datetime.utcnow().isoformat(),
                "state_updated_by_agent": agent_code,
            }

            result = await self.supabase.table("matches").insert(match_data).execute()
            match_id = result.data[0]["id"] if result.data else None

            # Log to agent_logs
            if match_id:
                await self.supabase.table("agent_logs").insert(
                    {
                        "agent_code": agent_code,
                        "action": "find_match",
                        "related_candidate_id": candidate_id,
                        "related_job_id": job_id,
                        "related_match_id": match_id,
                        "input_payload": {"candidate_id": candidate_id, "job_id": job_id},
                        "output_payload": {
                            "score": score,
                            "reasoning": reasoning,
                            "strengths": strengths,
                            "gaps": gaps,
                            "match_status": "found",  # Initial state, will be updated by Carmit review
                            "milestone": "candidate_match_created",  # Track progression through pipeline
                        },
                        "reasoning": f"Found match with score {score}: {reasoning}",
                        "llm_model": "claude-sonnet-4-5",
                        "tokens_used": tokens_used,
                        "duration_ms": int(duration_ms),
                        "status": "success",
                    }
                ).execute()

            logger.debug(f"Match created: {match_id}")

        except Exception as e:
            logger.error(f"Error creating match record: {e}")
            raise

    async def _log_agent_activity(
        self,
        agent_code: str,
        action: str,
        job_id: str,
        total_evaluated: int,
        matches_found: int,
        tokens_used: int,
    ) -> None:
        """Log high-level agent activity for monitoring and update agent runtime state."""
        try:
            # Log the activity
            await self.supabase.table("agent_logs").insert(
                {
                    "agent_code": agent_code,
                    "action": action,
                    "related_job_id": job_id,
                    "output_payload": {
                        "total_evaluated": total_evaluated,
                        "matches_found": matches_found,
                    },
                    "status": "success",
                    "tokens_used": tokens_used,
                }
            ).execute()

            # Update agent runtime state to "idle" after completing matching task
            # This signals that the agent is ready for the next job
            try:
                await self.supabase.table("agent_runtime_state").update({
                    "status": "idle",
                    "current_task_description": None,
                    "current_job_id": None,
                    "last_active_at": datetime.utcnow().isoformat(),
                    "next_scheduled_at": (datetime.utcnow() + timedelta(minutes=10)).isoformat(),
                }).eq("agent_code", agent_code).execute()
            except Exception as state_error:
                logger.warning(f"Failed to update agent runtime state to idle for {agent_code}: {state_error}")

        except Exception as e:
            logger.error(f"Error logging agent activity: {e}")

    async def _fetch_domain_candidates(self, agent_config: dict, limit: int) -> list:
        """Fetch candidates with FULL extracted CV data for comprehensive matching.

        CRITICAL: Joins with cv_files to get detailed extracted_fields from CV analysis.
        This ensures agents have access to ALL 30+ data points: experience, education,
        certifications, military service, languages, technical/soft skills, etc.

        Returns active candidates with cv_files.llm_analysis merged in.
        """

        try:
            # Fetch candidates AND their most recent CV analysis
            # Using LEFT JOIN to get candidates with/without recent CVs
            response = await self.supabase.table("candidates").select(
                "id, full_name_he, full_name_en, email, phone, city, country, "
                "primary_domain, secondary_domains, years_experience, "
                "security_clearance_level, languages, is_active, "
                "cv_files(id, llm_analysis, source_email_received_at)"
            ).eq("is_active", True).limit(limit).order("created_at", desc=True).execute()

            candidates_with_cv = response.data or []

            if not candidates_with_cv:
                logger.info("No active candidates found")
                return []

            # Enrich each candidate with their latest CV's extracted fields
            enriched_candidates = []
            for cand in candidates_with_cv:
                try:
                    # Get the most recent CV file (if any)
                    cv_files = cand.get("cv_files", []) or []
                    latest_cv = None
                    if cv_files:
                        # cv_files is an array; get the one with most recent source_email_received_at
                        latest_cv = max(
                            [f for f in cv_files if f.get("llm_analysis")],
                            key=lambda f: f.get("source_email_received_at", ""),
                            default=None
                        )

                    # Merge extracted fields into candidate for easier access by matching prompt
                    enriched = {
                        "id": cand.get("id"),
                        "name": cand.get("full_name_he") or cand.get("full_name_en", "Unknown"),
                        "email": cand.get("email"),
                        "phone": cand.get("phone"),
                        "location": cand.get("city"),
                        "country": cand.get("country"),
                        "primary_domain": cand.get("primary_domain"),
                        "secondary_domains": cand.get("secondary_domains", []),
                        "years_of_experience": cand.get("years_experience"),
                        "clearance_level": cand.get("security_clearance_level"),
                        "languages": cand.get("languages", []),
                        # Raw CV metadata (for reference)
                        "cv_metadata": {
                            "cv_id": latest_cv.get("id") if latest_cv else None,
                            "has_cv": latest_cv is not None,
                        }
                    }

                    # CRITICAL: Merge extracted_fields from CV analysis
                    if latest_cv and latest_cv.get("llm_analysis"):
                        llm_analysis = latest_cv.get("llm_analysis", {})
                        extracted_fields = llm_analysis.get("extracted_fields", {})

                        # Flatten extracted fields for matching prompt
                        enriched["extracted_fields"] = extracted_fields
                        enriched["technical_skills"] = extracted_fields.get("technical_skills", [])
                        enriched["soft_skills"] = extracted_fields.get("soft_skills", [])
                        enriched["experience"] = extracted_fields.get("experience", [])
                        enriched["education"] = extracted_fields.get("education", [])
                        enriched["certifications"] = extracted_fields.get("certifications", [])
                        enriched["military_service"] = extracted_fields.get("military_service")
                        enriched["spoken_languages"] = extracted_fields.get("spoken_languages", [])
                        enriched["summary"] = extracted_fields.get("summary")
                        enriched["clearance_keywords_matched"] = extracted_fields.get("clearance_keywords_matched", [])

                    enriched_candidates.append(enriched)

                except Exception as e:
                    logger.warning(f"Error enriching candidate {cand.get('id')}: {e}")
                    # Still add the basic candidate even if CV enrichment fails
                    enriched_candidates.append({
                        "id": cand.get("id"),
                        "name": cand.get("full_name_he") or cand.get("full_name_en", "Unknown"),
                        "location": cand.get("city"),
                        "years_of_experience": cand.get("years_experience"),
                        "clearance_level": cand.get("security_clearance_level"),
                    })

            logger.info(
                f"Fetched {len(enriched_candidates)} enriched candidates with CV data"
            )
            return enriched_candidates

        except Exception as e:
            logger.error(f"Error fetching candidates: {e}", exc_info=True)
            return []

    def _get_agent_config(self, agent_code: str) -> Optional[dict]:
        """Get agent domain, keywords, and specialization."""
        return AGENT_CONFIGS.get(agent_code)

    async def get_agent_stats(self, agent_code: str, days: int = 7) -> dict:
        """Get matching statistics for an agent over N days.

        Used for monitoring dashboard.
        """
        try:
            # Fetch agent logs from the past N days
            from_date = (datetime.utcnow() - asyncio.timedelta(days=days)).isoformat()

            response = await (
                self.supabase.table("agent_logs")
                .select("*")
                .eq("agent_code", agent_code)
                .gte("created_at", from_date)
                .execute()
            )

            logs = response.data or []

            # Calculate stats
            total_logs = len(logs)
            successful = len([l for l in logs if l.get("status") == "success"])
            failed = len([l for l in logs if l.get("status") == "failed"])
            total_tokens = sum([l.get("tokens_used", 0) for l in logs])

            # Get matches created
            matches_response = await (
                self.supabase.table("matches")
                .select("id")
                .eq("matched_by_agent_code", agent_code)
                .gte("created_at", from_date)
                .execute()
            )

            return {
                "agent_code": agent_code,
                "period_days": days,
                "total_logs": total_logs,
                "successful_runs": successful,
                "failed_runs": failed,
                "total_tokens_used": total_tokens,
                "matches_created": len(matches_response.data or []),
                "success_rate": successful / total_logs if total_logs > 0 else 0.0,
            }

        except Exception as e:
            logger.error(f"Error getting agent stats: {e}")
            return {"error": str(e)}

    async def invalidate_matches_for_job_change(
        self,
        job_id: str,
        change_reason: str,
        previous_values: dict,
        new_values: dict,
        invalidated_by: str = "system"
    ) -> dict:
        """Invalidate all matches for a job that has changed specifications.

        When a job is modified (priority, description, qualifications, etc.),
        all existing matches must be re-evaluated. This function invalidates
        matches that are no longer valid due to the change.

        Protected states (sent_to_tal, tal_approved) are never invalidated
        because they've already moved into the recruitment pipeline.

        Args:
            job_id: UUID of the job that changed
            change_reason: Reason for invalidation (specs_changed, priority_increased, etc.)
            previous_values: Dict of {field: old_value} for fields that changed
            new_values: Dict of {field: new_value} for fields that changed
            invalidated_by: Who triggered the invalidation (system, pipedrive_sync, user_id)

        Returns:
            dict: {
                "total_invalidated": int,
                "states_affected": {state: count, ...}
            }
        """
        try:
            # Find all matches for this job that are still valid
            matches_response = await self.supabase.table("matches").select(
                "id, current_state, candidate_id, candidate(*), job(*)"
            ).eq("job_id", job_id).eq("is_valid", True).execute()

            matches = matches_response.data or []

            # States that should NOT be invalidated (already in pipeline)
            protected_states = ["sent_to_tal", "tal_approved"]

            stats = {
                "total_invalidated": 0,
                "states_affected": {},
                "protected_states_count": 0
            }

            for match in matches:
                current_state = match.get("current_state", "found")

                # Check if this match's state is protected
                if current_state in protected_states:
                    stats["protected_states_count"] += 1
                    continue  # Don't invalidate protected states

                try:
                    # Invalidate this match
                    await self.supabase.table("matches").update({
                        "is_valid": False,
                        "invalidated_at": datetime.utcnow().isoformat(),
                        "invalidation_reason": change_reason,
                        "invalidated_by": invalidated_by,
                        "last_job_spec_check_at": datetime.utcnow().isoformat()
                    }).eq("id", match["id"]).execute()

                    stats["total_invalidated"] += 1
                    state_key = current_state or "unknown"
                    stats["states_affected"][state_key] = stats["states_affected"].get(state_key, 0) + 1

                    # Log the invalidation
                    try:
                        await self._log_agent_activity(
                            agent_code="system",
                            action="invalidate_match",
                            job_id=job_id,
                            total_evaluated=0,
                            matches_found=0,
                            tokens_used=0
                        )
                    except Exception as log_error:
                        logger.warning(f"Failed to log invalidation for match {match['id']}: {log_error}")

                except Exception as update_error:
                    logger.error(f"Error invalidating match {match['id']}: {update_error}")
                    continue

            # Record change in job_changes table
            try:
                await self.supabase.table("job_changes").insert({
                    "job_id": job_id,
                    "change_type": change_reason,
                    "changed_by": invalidated_by,
                    "changed_at": datetime.utcnow().isoformat(),
                    "previous_values": previous_values,
                    "new_values": new_values,
                    "fields_changed": list(previous_values.keys()),
                    "affected_matches_count": stats["total_invalidated"],
                    "matches_in_protected_states": stats["protected_states_count"]
                }).execute()
            except Exception as history_error:
                logger.warning(f"Failed to record change in job_changes table: {history_error}")

            logger.info(
                f"Invalidated {stats['total_invalidated']} matches for job {job_id} "
                f"due to {change_reason} "
                f"(Protected states: {stats['protected_states_count']})"
            )

            return stats

        except Exception as e:
            logger.error(f"Error invalidating matches for job {job_id}: {e}", exc_info=True)
            return {
                "total_invalidated": 0,
                "states_affected": {},
                "error": str(e)
            }

    async def trigger_job_rematching(self, job_id: str) -> dict:
        """Trigger candidate re-matching for a job.

        Called after job specifications change to find new candidates
        that match the updated job requirements.

        This function:
        1. Fetches the job and assigned agent
        2. Updates job_spec_hash to current value
        3. Queues re-matching task for the agent
        4. Logs the re-match trigger

        Args:
            job_id: UUID of the job to re-match

        Returns:
            dict: {
                "status": "rematch_queued" | "waiting_for_assignment" | "error",
                "job_id": job_id,
                "agent_code": agent_code (if queued),
                "queued_at": ISO timestamp (if queued)
            }
        """
        try:
            from pandapower.workers.job_change_detection import compute_job_spec_hash

            # Fetch job and its assigned agent
            job_response = await self.supabase.table("jobs").select(
                "*"
            ).eq("id", job_id).single().execute()

            job = job_response.data
            agent_code = job.get("assigned_agent_code")

            if not agent_code:
                # Job not yet assigned - will be picked up by Carmit next scheduling cycle
                logger.info(f"Job {job_id} not yet assigned; will be picked up by Carmit router")
                return {
                    "status": "waiting_for_assignment",
                    "job_id": job_id
                }

            # Update job_spec_hash to current value
            try:
                new_hash = compute_job_spec_hash(job)
                await self.supabase.table("jobs").update({
                    "job_spec_hash": new_hash,
                    "spec_last_hash_computed_at": datetime.utcnow().isoformat(),
                    "last_modified_by": "rematch_trigger"
                }).eq("id", job_id).execute()

                logger.info(f"Updated job_spec_hash for job {job_id}: {new_hash}")
            except Exception as hash_error:
                logger.warning(f"Failed to update job_spec_hash for {job_id}: {hash_error}")

            # Queue re-matching task for the agent
            # Note: In actual implementation, this would queue a Celery task
            # For now, we just log the intent
            queued_at = datetime.utcnow().isoformat()
            logger.info(f"Queued re-matching task for job {job_id} with agent {agent_code}")

            # Log re-match trigger in agent_logs
            try:
                await self.supabase.table("agent_logs").insert({
                    "agent_code": agent_code,
                    "action": "rematch_triggered",
                    "related_job_id": job_id,
                    "output_payload": {
                        "reason": "job_spec_changed"
                    },
                    "status": "success"
                }).execute()
            except Exception as log_error:
                logger.warning(f"Failed to log rematch trigger for {job_id}: {log_error}")

            return {
                "status": "rematch_queued",
                "job_id": job_id,
                "agent_code": agent_code,
                "queued_at": queued_at
            }

        except Exception as e:
            logger.error(f"Error triggering re-match for job {job_id}: {e}", exc_info=True)
            return {
                "status": "error",
                "job_id": job_id,
                "error": str(e)
            }

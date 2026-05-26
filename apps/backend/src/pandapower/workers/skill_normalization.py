"""
Skill Normalization Worker - Maps extracted skills to canonical skill taxonomy.

Phase 10: Normalizes raw skills from CVs to a canonical skill library
using Claude AI for intelligent matching, with fallback to similarity matching.
"""

import logging
from typing import Any, Optional
from uuid import UUID

logger = logging.getLogger(__name__)


class SkillNormalizationWorker:
    """Worker for normalizing skills to canonical taxonomy."""

    def __init__(self, supabase_client: Any, claude_client: Optional[Any] = None):
        """Initialize skill normalization worker.

        Args:
            supabase_client: Supabase client instance
            claude_client: Optional Claude API client for intelligent normalization
        """
        self.supabase = supabase_client
        self.claude = claude_client
        self._skill_cache = None  # Cache of canonical skills

    async def normalize_candidates_skills(self, limit: int = 20) -> dict:
        """Normalize skills for candidates without normalized skills.

        Process candidates that have key_skills but no normalized skills yet.

        Args:
            limit: Maximum number of candidates to process

        Returns:
            Dict with metrics: {
                'total_processed': int,
                'skills_normalized': int,
                'candidates_updated': int,
                'errors': list
            }
        """
        result = {
            "total_processed": 0,
            "skills_normalized": 0,
            "candidates_updated": 0,
            "errors": [],
        }

        try:
            # Load canonical skills once
            await self._load_skill_cache()

            # Find candidates with skills but no normalized skills yet
            response = await self.supabase.table("candidates").select(
                "id, name, key_skills, detected_language"
            ).is_("deleted_at", "null").limit(limit).execute()

            candidates = response.data or []
            result["total_processed"] = len(candidates)

            logger.info(f"Processing {len(candidates)} candidates for skill normalization")

            for candidate in candidates:
                try:
                    normalized_count = await self._normalize_candidate_skills(candidate)
                    if normalized_count > 0:
                        result["candidates_updated"] += 1
                    result["skills_normalized"] += normalized_count
                except Exception as e:
                    error_msg = f"Failed to normalize skills for {candidate['id']}: {str(e)}"
                    logger.error(error_msg)
                    result["errors"].append({
                        "candidate_id": candidate["id"],
                        "error": error_msg,
                    })

            logger.info(
                f"Skill normalization complete",
                total=result["total_processed"],
                normalized=result["skills_normalized"],
                candidates_updated=result["candidates_updated"],
                errors=len(result["errors"]),
            )

            return result

        except Exception as e:
            logger.error(f"Skill normalization batch failed: {e}", exc_info=True)
            result["errors"].append({"error": str(e)})
            return result

    async def _normalize_candidate_skills(self, candidate: dict) -> int:
        """Normalize skills for a single candidate.

        Args:
            candidate: Candidate record with key_skills

        Returns:
            Number of skills normalized
        """
        candidate_id = candidate["id"]
        raw_skills = candidate.get("key_skills", [])
        language = candidate.get("detected_language", "en")

        if not raw_skills:
            return 0

        normalized_count = 0

        for raw_skill in raw_skills:
            try:
                # Find or map the skill
                canonical_skill_id = await self._map_skill_to_canonical(
                    raw_skill, language
                )

                if canonical_skill_id:
                    # Create candidate_skills record with both FK and denormalized columns
                    canonical_skill = self._skill_cache.get(str(canonical_skill_id), {})
                    await self.supabase.table("candidate_skills").insert({
                        "candidate_id": str(candidate_id),
                        "skill_id": str(canonical_skill_id),
                        "raw_skill_text": raw_skill,
                        "skill_name": canonical_skill.get("name", raw_skill),  # Denormalized
                        "skill_category": canonical_skill.get("category", "Unknown"),  # Denormalized
                        "confidence_score": 0.85,  # Default confidence
                        "normalization_method": "claude_ai" if self.claude else "similarity_matching",
                    }).execute()

                    normalized_count += 1

                    logger.debug(
                        f"Normalized skill",
                        candidate_id=candidate_id,
                        raw_skill=raw_skill,
                        skill_id=canonical_skill_id,
                    )

            except Exception as e:
                logger.warning(
                    f"Failed to normalize skill '{raw_skill}' for candidate {candidate_id}: {e}"
                )
                continue

        return normalized_count

    async def _map_skill_to_canonical(self, raw_skill: str, language: str) -> Optional[UUID]:
        """Map a raw skill to a canonical skill ID.

        Strategy chain:
        1. Check existing mappings table (cheap, exact match)
        2. Use Claude for semantic matching against the canonical library
        3. Use string similarity (fallback for typos / aliases)
        4. AUTO-DISCOVER: if nothing matched but the skill looks legitimate,
           create a new canonical skill so the next CV that mentions it benefits.

        Returns:
            Canonical skill UUID or None if we couldn't even auto-discover.
        """
        # 1. Existing mapping?
        existing_mapping = await self._find_existing_mapping(raw_skill)
        if existing_mapping:
            return existing_mapping

        # 2. Claude semantic matching
        if self.claude:
            mapped_skill_id = await self._map_skill_with_claude(raw_skill, language)
            if mapped_skill_id:
                await self._save_skill_mapping(raw_skill, mapped_skill_id, language, "claude_ai", 0.95)
                return mapped_skill_id

        # 3. String similarity
        mapped_skill_id = self._map_skill_with_similarity(raw_skill)
        if mapped_skill_id:
            await self._save_skill_mapping(raw_skill, mapped_skill_id, language, "similarity_matching", 0.75)
            return mapped_skill_id

        # 4. AUTO-DISCOVERY: the library doesn't know this skill yet. If it
        #    looks legitimate (passes basic sanity check), add it as a new
        #    canonical skill so the next CV mentioning it gets normalized.
        if self._is_likely_real_skill(raw_skill):
            new_skill_id = await self._auto_discover_skill(raw_skill, language)
            if new_skill_id:
                await self._save_skill_mapping(
                    raw_skill, new_skill_id, language, "auto_discovered", 0.80
                )
                return new_skill_id

        logger.warning(f"Could not map skill: '{raw_skill}' (language: {language})")
        return None

    @staticmethod
    def _is_likely_real_skill(raw_skill: str) -> bool:
        """Quick sanity check: is this string plausibly a skill name?

        Rejects:
        - Empty / very short strings
        - Pure numbers
        - Long sentence-like strings (probably a description, not a skill)
        - Generic noise ('etc', 'misc', '...')
        """
        s = (raw_skill or "").strip()
        if len(s) < 2 or len(s) > 80:
            return False
        if s.lower() in {"etc", "misc", "other", "various", "...", "n/a", "none"}:
            return False
        if s.isdigit():
            return False
        # Skill phrases are typically 1-5 words; longer = probably not a skill name
        if len(s.split()) > 6:
            return False
        # Reject things that are clearly sentences
        if any(c in s for c in (".", "!", "?")):
            return False
        return True

    async def _auto_discover_skill(
        self, raw_skill: str, language: str
    ) -> Optional[UUID]:
        """Insert a new canonical skill discovered during CV parsing.

        Uses Claude (if available) to classify the skill into an existing
        category and produce a clean canonical name + Hebrew translation.
        Falls back to "Auto-Discovered" category if Claude isn't available.
        """
        canonical_name, name_he, category = await self._classify_new_skill(raw_skill, language)
        if not canonical_name:
            canonical_name = raw_skill.strip()
        if not category:
            category = "Auto-Discovered"

        # Don't create duplicates: a Claude classification might collapse to
        # an existing skill we just missed earlier.
        for sid, info in self._skill_cache.items():
            if info["name"].lower() == canonical_name.lower():
                return UUID(sid)

        try:
            resp = await self.supabase.table("skills").insert({
                "name": canonical_name,
                "name_he": name_he,
                "category": category,
                "description": f"Auto-discovered from CV (raw text: '{raw_skill}')",
                "aliases": [raw_skill] if raw_skill.lower() != canonical_name.lower() else [],
                "popularity_score": 30,  # New skills start low (0-100 scale); will rise as more CVs use them
            }).execute()

            if resp.data:
                new_id = resp.data[0]["id"]
                # Update the in-memory cache so subsequent skills in this batch
                # can match against the new entry.
                self._skill_cache[new_id] = {
                    "name": canonical_name,
                    "category": category,
                    "aliases": [raw_skill] if raw_skill.lower() != canonical_name.lower() else [],
                }
                logger.info(
                    f"[auto-discovery] Added new canonical skill: '{canonical_name}' "
                    f"(category={category}, raw='{raw_skill}')"
                )
                return UUID(new_id)
        except Exception as e:
            # Race: another worker may have just inserted the same skill.
            msg = str(e).lower()
            if "duplicate" in msg or "unique" in msg:
                # Refresh cache lookup
                try:
                    again = await self.supabase.table("skills").select("id").eq(
                        "name", canonical_name
                    ).limit(1).execute()
                    if again.data:
                        return UUID(again.data[0]["id"])
                except Exception:
                    pass
            logger.warning(f"[auto-discovery] Failed to insert '{canonical_name}': {e}")

        return None

    async def _classify_new_skill(
        self, raw_skill: str, language: str
    ) -> tuple[Optional[str], Optional[str], Optional[str]]:
        """Use Claude to produce (canonical_name, name_he, category) for a new skill.

        Returns (None, None, None) if Claude isn't available or fails. The
        caller falls back to raw_skill + "Auto-Discovered" category in that case.
        """
        if not self.claude:
            return None, None, None

        # Build list of categories that already exist - we want Claude to
        # prefer an existing category over inventing a new one.
        existing_categories = sorted({info.get("category") for info in self._skill_cache.values() if info.get("category")})
        category_list = "\n".join(f"  - {c}" for c in existing_categories)

        prompt = f"""You are a recruitment taxonomy classifier. Given a raw skill string
extracted from a CV, produce a clean canonical version + Hebrew translation +
the best-fitting category from the list below.

Raw skill ({language}): "{raw_skill}"

Existing categories (prefer one of these):
{category_list}

Return ONLY this JSON (no markdown):
{{
  "extracted_fields": {{
    "canonical_name": "Cleaned English name, properly cased (e.g. 'Python', 'PCB Design')",
    "name_he": "Hebrew translation, or null if the skill name itself is in English (like a tool name)",
    "category": "One of the existing categories above, or a NEW category if none fits"
  }},
  "confidence_scores": {{ "canonical_name": 0.9 }}
}}

Rules:
- If the raw skill is gibberish/noise/very generic, return null for canonical_name.
- Tool names (Altium, MATLAB, Linux) keep their original spelling.
- Hebrew names should be the natural Hebrew rendering, not transliteration.
"""

        try:
            response = await self.claude.parse_cv_structured(prompt, language)
            fields = (response or {}).get("extracted_fields") or {}
            canonical = fields.get("canonical_name")
            name_he = fields.get("name_he")
            category = fields.get("category")

            # Validate
            if canonical:
                canonical = str(canonical).strip()
                if not canonical or canonical.lower() in ("null", "none"):
                    canonical = None
            if name_he:
                name_he = str(name_he).strip()
                if not name_he or name_he.lower() in ("null", "none"):
                    name_he = None
            if category:
                category = str(category).strip()

            return canonical, name_he, category
        except Exception as e:
            logger.debug(f"[auto-discovery] Claude classification failed: {e}")
            return None, None, None

    async def _find_existing_mapping(self, raw_skill: str) -> Optional[UUID]:
        """Check if we already have a mapping for this raw skill.

        Args:
            raw_skill: Raw skill text

        Returns:
            Canonical skill ID or None
        """
        try:
            response = await self.supabase.table("skill_mappings").select(
                "canonical_skill_id"
            ).eq("raw_skill_text", raw_skill).eq("is_active", True).limit(1).execute()

            if response.data:
                return UUID(response.data[0]["canonical_skill_id"])
        except Exception as e:
            logger.debug(f"Error checking existing mapping: {e}")

        return None

    async def _map_skill_with_claude(self, raw_skill: str, language: str) -> Optional[UUID]:
        """Use Claude to intelligently map a skill.

        Args:
            raw_skill: Raw skill text
            language: Language code

        Returns:
            Best matching canonical skill ID or None
        """
        if not self.claude:
            return None

        try:
            # Build the skill list for Claude
            skill_names = [s["name"] for s in self._skill_cache.values()]
            skill_options = "\n".join([f"- {name}" for name in skill_names[:50]])  # Top 50

            prompt = f"""Map this skill from a CV to the closest canonical skill.

Raw skill (from {language} CV): "{raw_skill}"

Available canonical skills:
{skill_options}

Return ONLY the exact canonical skill name that best matches, or "NO_MATCH" if no good match.
Focus on semantic meaning, not exact string matching."""

            response = await self.claude.parse_cv_structured(prompt, language)

            # Extract the response - it should be a simple skill name
            if isinstance(response, dict) and "extracted_fields" in response:
                skill_name = response.get("extracted_fields", {}).get("name")
            else:
                skill_name = str(response).strip().strip('"')

            if skill_name and skill_name != "NO_MATCH":
                # Find the matching skill in cache
                for skill_id, skill_info in self._skill_cache.items():
                    if skill_info["name"].lower() == skill_name.lower():
                        return UUID(skill_id)

        except Exception as e:
            logger.debug(f"Claude skill mapping failed for '{raw_skill}': {e}")

        return None

    def _map_skill_with_similarity(self, raw_skill: str) -> Optional[UUID]:
        """Use string similarity to match a skill.

        Simple string similarity approach - finds canonical skill with
        highest similarity score.

        Args:
            raw_skill: Raw skill text

        Returns:
            Best matching canonical skill ID or None
        """
        from difflib import SequenceMatcher

        max_similarity = 0
        best_match_id = None
        threshold = 0.6

        raw_lower = raw_skill.lower()

        for skill_id, skill_info in self._skill_cache.items():
            skill_name = skill_info["name"].lower()
            aliases = [a.lower() for a in skill_info.get("aliases", [])]

            # Check against skill name
            similarity = SequenceMatcher(None, raw_lower, skill_name).ratio()

            # Check against aliases
            for alias in aliases:
                alias_similarity = SequenceMatcher(None, raw_lower, alias).ratio()
                similarity = max(similarity, alias_similarity)

            if similarity > max_similarity:
                max_similarity = similarity
                best_match_id = UUID(skill_id) if similarity > threshold else None

        return best_match_id

    async def _save_skill_mapping(
        self,
        raw_skill: str,
        canonical_skill_id: UUID,
        language: str,
        method: str,
        confidence: float,
    ) -> None:
        """Save a skill mapping for future use.

        Args:
            raw_skill: Raw skill text
            canonical_skill_id: Canonical skill UUID
            language: Language code
            method: Mapping method ('claude_ai', 'similarity_matching', etc.)
            confidence: Confidence score (0-1)
        """
        try:
            await self.supabase.table("skill_mappings").insert({
                "raw_skill_text": raw_skill,
                "canonical_skill_id": str(canonical_skill_id),
                "source_language": language,
                "mapping_method": method,
                "confidence_score": confidence,
            }).execute()

            logger.debug(f"Saved skill mapping: '{raw_skill}' -> {canonical_skill_id}")

        except Exception as e:
            logger.warning(f"Failed to save skill mapping: {e}")

    async def _load_skill_cache(self) -> None:
        """Load all canonical skills into memory cache."""
        if self._skill_cache is not None:
            return

        try:
            response = await self.supabase.table("skills").select(
                "id, name, category, aliases"
            ).eq("is_active", True).execute()

            self._skill_cache = {}
            for skill in response.data or []:
                self._skill_cache[skill["id"]] = {
                    "name": skill["name"],
                    "category": skill["category"],
                    "aliases": skill.get("aliases", []),
                }

            logger.info(f"Loaded {len(self._skill_cache)} canonical skills")

        except Exception as e:
            logger.error(f"Failed to load skill cache: {e}")
            self._skill_cache = {}

import asyncio
import json
import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

ANTHROPIC_API_BASE = "https://api.anthropic.com/v1"
MAX_RETRIES = 3
INITIAL_BACKOFF = 1  # seconds


class AnthropicClient:
    def __init__(self, api_key: str):
        """Initialize Claude API client."""
        self.api_key = api_key
        self.http_client = httpx.AsyncClient(timeout=120.0)
        self.model = "claude-opus-4-1"

    async def close(self):
        """Close HTTP client."""
        await self.http_client.aclose()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    def get_token_count(self, text: str) -> int:
        """Estimate token count for text (rough approximation)."""
        # Anthropic uses ~4 characters per token on average
        return len(text) // 4 + 100  # Add buffer for system prompt

    def _build_extraction_prompt(self, raw_text: str, language: str, security_keywords: dict = None) -> tuple[str, str]:
        """Build a comprehensive extraction prompt covering 30+ CV fields.

        Built to be aggressive about extraction: infer when context is clear,
        normalize formats (phones, dates), separate technical vs soft skills,
        capture military service and clearance with synonym matching.
        """

        # Build security classification guide from keywords (DB-driven, so the
        # user can add synonyms via the admin UI without code changes).
        security_guide = ""
        if security_keywords:
            security_guide = "\n\n# SECURITY CLEARANCE DETECTION (CRITICAL)\n"
            security_guide += "Search the CV text for ANY of these synonyms (case-insensitive, Hebrew + English):\n\n"
            for level in sorted(security_keywords.keys(), key=lambda x: int(x) if str(x).isdigit() else 0):
                keywords = security_keywords[level]
                keyword_list = " | ".join(f'"{kw}"' for kw in keywords)
                security_guide += f"  Level {level}: {keyword_list}\n"
            security_guide += (
                "\nRules:\n"
                "- Return the HIGHEST level that has at least one keyword match.\n"
                "- Match is case-insensitive and language-agnostic (Hebrew + English).\n"
                "- ALSO match common phrases: 'cleared to {level}', 'TS/SCI', 'סיווג ביטחוני', 'אישור ביטחוני',\n"
                "  'צה\"ל - יחידה X', 'IDF Unit 8200/9900/81/Mamram' (intelligence units imply clearance).\n"
                "- IDF intelligence units (8200, 9900, 81, Mamram, סייבר) → at least Level 2.\n"
                "- If no match, return null. NEVER guess clearance from job titles alone.\n"
            )

        system_prompt = (
            "You are an EXPERT CV/Resume parser with deep knowledge of Israeli hi-tech "
            "and security recruitment. You extract comprehensive structured data from "
            "Hebrew and English CVs.\n\n"
            "PRINCIPLES:\n"
            "- Extract MAXIMUM information. Be thorough — every detail matters.\n"
            "- If a field has clear evidence in the text, extract it. If unclear, return null with 0.0 confidence.\n"
            "- Infer from context (e.g., +972 prefix → Israeli, .il email domain → Israel).\n"
            "- Normalize phones to E.164 (+972XXXXXXXXX for Israel).\n"
            "- Normalize dates to YYYY-MM-DD or YYYY when only year is known.\n"
            "- For skills: SEPARATE technical from soft skills, and split spoken languages.\n"
            "- For experience: ORDER from most recent to oldest. Include description/achievements when present.\n"
            "- For education: ORDER by degree (PhD > MSc > BSc > diploma).\n"
            "- For Hebrew names: also provide English transliteration when possible.\n"
            "- Israeli military service is ALWAYS relevant — capture unit, role, rank, dates.\n\n"
            "CRITICAL — EMAIL & PHONE EXTRACTION RULES:\n"
            "- Return ONLY the candidate's OWN personal contact details.\n"
            "- The CV may include footers, signatures, or watermarks from job-board\n"
            "  platforms (jobnet, alljobs, drushim, AllJob, JobMaster, Drushim, LinkedIn,\n"
            "  Workable, Greenhouse, Lever, Comeet, etc) — IGNORE ANY contact info from those.\n"
            "- The CV may say \"Sent via\", \"Forwarded by\", \"Powered by\", \"Application\n"
            "  submitted through\" — IGNORE contact details that appear in those phrases.\n"
            "- Emails like info@..., jobs@..., careers@..., hr@..., noreply@..., recruitment@...\n"
            "  are ROLE mailboxes — they are NEVER the candidate. Return null instead.\n"
            "- The candidate's real email is usually personal: gmail.com, walla.co.il,\n"
            "  hotmail.com, or a private domain. It typically appears in the CV header,\n"
            "  contact section, or right next to the candidate's name.\n"
            "- If the only email you can find is a platform/role mailbox, RETURN null —\n"
            "  do NOT fall back to it. Better to leave email empty than to mis-attribute.\n"
            "- Same rule applies to phone numbers: ignore platform support lines.\n\n"
            "OUTPUT: Return ONLY valid JSON, no markdown fences, no commentary."
            + security_guide
        )

        user_prompt = f"""Extract ALL available information from this CV.

DETECTED LANGUAGE: {language}

CV TEXT:
\"\"\"
{raw_text}
\"\"\"

Return ONLY this JSON structure (every field is REQUIRED — use null/[]/{{}} when not found):

{{
  "extracted_fields": {{
    "name": "string (full name as written) or null",
    "name_en": "string (English transliteration if name is Hebrew) or null",
    "name_he": "string (Hebrew form if name is in English and Hebrew context exists) or null",

    "email": "string (lowercase) or null",
    "phone": "string (+972XXXXXXXXX format for Israeli) or null",
    "alt_phone": "string (secondary phone if any) or null",
    "linkedin_url": "string (full URL) or null",
    "github_url": "string (full URL) or null",
    "portfolio_url": "string (personal website) or null",

    "location": "string (city, region) or null",
    "city": "string or null",
    "country": "string (default 'Israel' if Hebrew or +972) or null",
    "willing_to_relocate": true/false or null,
    "remote_preference": "string ('remote'|'hybrid'|'onsite') or null",

    "birth_date": "string (YYYY-MM-DD) or null",
    "gender": "string ('male'|'female'|'other') or null",
    "marital_status": "string ('single'|'married'|'divorced') or null",
    "nationality": "string or null",
    "driver_license": "string (license type/category) or null",

    "summary": "string (1-3 sentence professional summary) or null",
    "current_position": "string (current job title) or null",
    "current_company": "string (current employer) or null",
    "years_of_experience": "integer (total years of professional experience) or null",
    "expected_salary": "string (e.g. '25K NIS', '$120K') or null",
    "availability": "string (e.g. 'immediate', '2 weeks', '1 month') or null",

    "technical_skills": ["array of technical/hard skills - languages, frameworks, tools"],
    "soft_skills": ["array of soft skills - leadership, communication, etc."],
    "spoken_languages": [
      {{
        "language": "string (e.g. 'Hebrew', 'English', 'Russian')",
        "proficiency": "string ('native'|'fluent'|'professional'|'conversational'|'basic')"
      }}
    ],

    "experience": [
      {{
        "position": "string (job title)",
        "company": "string",
        "location": "string (city) or null",
        "start_date": "string (YYYY-MM or YYYY)",
        "end_date": "string (YYYY-MM or YYYY, or 'present')",
        "duration": "string (human-readable, e.g. '2020-2023')",
        "description": "string (job responsibilities summary) or null",
        "achievements": ["array of key achievements, if listed"],
        "technologies": ["array of technologies used in this role"]
      }}
    ],

    "education": [
      {{
        "degree": "string ('PhD'|'MSc'|'MBA'|'BSc'|'BA'|'Diploma'|other)",
        "field": "string (e.g. 'Computer Science')",
        "institution": "string (university/college name)",
        "location": "string or null",
        "start_year": "integer or null",
        "end_year": "integer or null",
        "honors": "string (e.g. 'cum laude', 'magna cum laude') or null",
        "thesis": "string (thesis title for graduate degrees) or null",
        "gpa": "number or null"
      }}
    ],

    "certifications": [
      {{
        "name": "string (certification name)",
        "issuer": "string (issuing organization)",
        "issue_date": "string (YYYY-MM or YYYY) or null",
        "expiry_date": "string or null",
        "credential_id": "string or null"
      }}
    ],

    "military_service": {{
      "served": true/false,
      "country": "string (default 'Israel' for IDF) or null",
      "branch": "string ('IDF', 'IAF', 'Navy', etc.) or null",
      "unit": "string (e.g. '8200', '9900', 'Mamram', 'Talpiot') or null",
      "role": "string (e.g. 'Software Developer', 'Intelligence Officer') or null",
      "rank": "string (e.g. 'Captain', 'Lieutenant') or null",
      "start_year": "integer or null",
      "end_year": "integer or null",
      "achievements": ["string array of notable achievements"]
    }} or null,

    "clearance_level": "integer (1-6 based on detection rules above) or null",
    "clearance_keywords_matched": ["array of exact keywords found in text that triggered the classification"],

    "projects": [
      {{
        "name": "string",
        "description": "string",
        "technologies": ["array"],
        "url": "string or null"
      }}
    ],

    "awards": [
      {{
        "name": "string",
        "issuer": "string or null",
        "year": "integer or null",
        "description": "string or null"
      }}
    ],

    "publications": [
      {{
        "title": "string",
        "venue": "string (journal/conference)",
        "year": "integer or null",
        "url": "string or null"
      }}
    ],

    "volunteer_work": [
      {{
        "organization": "string",
        "role": "string",
        "duration": "string or null"
      }}
    ],

    "references": [
      {{
        "name": "string",
        "title": "string or null",
        "company": "string or null",
        "contact": "string or null"
      }}
    ]
  }},

  "confidence_scores": {{
    "name": 0.0,
    "email": 0.0,
    "phone": 0.0,
    "location": 0.0,
    "current_position": 0.0,
    "current_company": 0.0,
    "years_of_experience": 0.0,
    "technical_skills": 0.0,
    "soft_skills": 0.0,
    "spoken_languages": 0.0,
    "experience": 0.0,
    "education": 0.0,
    "certifications": 0.0,
    "military_service": 0.0,
    "clearance_level": 0.0,
    "projects": 0.0
  }},

  "extraction_notes": "string — describe any ambiguities, assumptions, or text quality issues. Mention if the CV is partial/truncated."
}}
"""

        return (system_prompt, user_prompt)

    def _extract_json(self, response_text: str) -> dict[str, Any]:
        """Extract and parse JSON from a Claude response.

        Tolerates common LLM quirks:
        - leading/trailing prose ("Here is the JSON: ...")
        - markdown code fences (```json ... ```)
        - braces inside string values (uses bracket-counting, not naive rfind)
        """
        text = response_text.strip()

        # Strip markdown code fences if present
        if text.startswith("```"):
            # ```json\n{...}\n```
            lines = text.split("\n", 1)
            if len(lines) > 1:
                text = lines[1]
            if text.endswith("```"):
                text = text[: -3].strip()

        # Find the first '{' - this is where the JSON object starts
        json_start = text.find("{")
        if json_start == -1:
            raise ValueError(f"No JSON found in response: {response_text[:300]}")

        # Walk forward, counting braces, ignoring those inside strings, to find
        # the matching closing brace. This is more robust than rfind('}'), which
        # breaks when the response has trailing prose with extra braces.
        depth = 0
        in_string = False
        escape = False
        json_end = -1
        for i, ch in enumerate(text[json_start:], start=json_start):
            if escape:
                escape = False
                continue
            if ch == "\\" and in_string:
                escape = True
                continue
            if ch == '"':
                in_string = not in_string
                continue
            if in_string:
                continue
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    json_end = i + 1
                    break

        if json_end == -1:
            # No matching close brace found - fall back to old behavior
            json_end = text.rfind("}") + 1

        json_str = text[json_start:json_end]

        try:
            return json.loads(json_str)
        except json.JSONDecodeError as e:
            # Provide more context for debugging
            preview = json_str[:500] if len(json_str) < 500 else json_str[:250] + " ... " + json_str[-250:]
            raise ValueError(
                f"Invalid JSON in response: {str(e)}. JSON preview: {preview}"
            )

    async def _make_request_with_retry(
        self,
        messages: list[dict[str, str]],
        system: str,
    ) -> dict[str, Any]:
        """Make API request with exponential backoff retry."""
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }

        payload = {
            "model": self.model,
            # Expanded prompt extracts 30+ fields w/ deep experience arrays - needs room
            "max_tokens": 8192,
            "system": system,
            "messages": messages,
        }

        for attempt in range(MAX_RETRIES):
            try:
                logger.debug(f"Claude API request attempt {attempt + 1}/{MAX_RETRIES}")

                response = await self.http_client.post(
                    f"{ANTHROPIC_API_BASE}/messages",
                    headers=headers,
                    json=payload,
                )

                # Handle rate limiting
                if response.status_code == 429:
                    retry_after = int(response.headers.get("retry-after", 60))
                    if attempt < MAX_RETRIES - 1:
                        logger.warning(
                            f"Rate limited by Claude API, retrying after {retry_after}s"
                        )
                        await asyncio.sleep(retry_after)
                        continue
                    raise Exception(
                        f"Rate limited by Claude API after {MAX_RETRIES} attempts"
                    )

                # Handle server errors
                if response.status_code in (503, 504):
                    if attempt < MAX_RETRIES - 1:
                        backoff = INITIAL_BACKOFF * (2**attempt)
                        logger.warning(
                            f"Claude API server error {response.status_code}, retrying after {backoff}s"
                        )
                        await asyncio.sleep(backoff)
                        continue

                # Handle other HTTP errors
                if response.status_code >= 400:
                    error_detail = response.text
                    if response.status_code in (400, 401, 403):
                        # Don't retry authentication/validation errors
                        raise Exception(
                            f"Claude API error {response.status_code}: {error_detail}"
                        )
                    # Server errors might be retriable
                    if attempt < MAX_RETRIES - 1 and response.status_code >= 500:
                        backoff = INITIAL_BACKOFF * (2**attempt)
                        logger.warning(f"Claude API error, retrying after {backoff}s")
                        await asyncio.sleep(backoff)
                        continue
                    raise Exception(
                        f"Claude API error {response.status_code}: {error_detail}"
                    )

                # Success
                data = response.json()
                logger.debug(f"Claude API request succeeded")
                return data

            except (httpx.TimeoutException, httpx.ConnectError) as e:
                if attempt < MAX_RETRIES - 1:
                    backoff = INITIAL_BACKOFF * (2**attempt)
                    logger.warning(f"Claude API timeout/connection error, retrying after {backoff}s")
                    await asyncio.sleep(backoff)
                    continue
                raise Exception(f"Claude API connection error after {MAX_RETRIES} attempts: {str(e)}")

            except Exception as e:
                logger.error(f"Claude API request failed: {str(e)}")
                raise

        raise Exception("Max retries exceeded")

    async def parse_cv_structured(self, raw_text: str, language: str, security_keywords: dict = None) -> dict[str, Any]:
        """
        Parse CV text using Claude API and return structured extraction.

        Args:
            raw_text: Extracted CV text
            language: Detected language ('he', 'en', or 'mixed')
            security_keywords: Optional dict of {level: [keywords]} for security classification

        Returns:
            Dictionary with extracted_fields, confidence_scores, and metadata
        """
        try:
            system_prompt, user_prompt = self._build_extraction_prompt(raw_text, language, security_keywords)

            messages = [
                {
                    "role": "user",
                    "content": user_prompt,
                }
            ]

            # Make request
            response = await self._make_request_with_retry(messages, system_prompt)

            # Extract content
            if not response.get("content"):
                raise ValueError("No content in Claude response")

            response_text = response["content"][0].get("text", "")
            if not response_text:
                raise ValueError("Empty text in Claude response")

            # Parse JSON
            parsed = self._extract_json(response_text)

            # Add metadata
            usage = response.get("usage", {})
            parsed["api_response_tokens"] = {
                "prompt_tokens": usage.get("input_tokens", 0),
                "completion_tokens": usage.get("output_tokens", 0),
                "total_tokens": usage.get("input_tokens", 0) + usage.get("output_tokens", 0),
            }

            logger.info(
                f"CV parsed successfully",
                tokens_used=parsed["api_response_tokens"]["total_tokens"],
                language=language,
            )

            return parsed

        except Exception as e:
            logger.error(f"CV parsing failed: {str(e)}")
            raise

    async def match_score_with_json(self, prompt: str, model: str = "claude-sonnet-4") -> dict[str, Any]:
        """Score a candidate-job match and return structured JSON result.

        Used by agent matching worker for Phase 4.

        Args:
            prompt: The matching prompt containing candidate and job details
            model: Claude model to use (default: claude-sonnet-4)

        Returns:
            {
                "parsed": {
                    "score": 0-100,
                    "reasoning": "text",
                    "strengths": ["list"],
                    "gaps": ["list"]
                },
                "tokens_used": int
            }
        """
        system_prompt = """You are an expert recruitment evaluator. Your task is to score candidate-job matches.
Respond ONLY with valid JSON, no additional text."""

        messages = [{"role": "user", "content": prompt}]

        try:
            # Override model for this request
            original_model = self.model
            self.model = model

            response = await self._make_request_with_retry(messages, system_prompt)

            # Extract content
            if not response.get("content"):
                raise ValueError("No content in Claude response")

            response_text = response["content"][0].get("text", "")
            if not response_text:
                raise ValueError("Empty text in Claude response")

            # Parse JSON
            parsed = self._extract_json(response_text)

            # Extract token usage
            usage = response.get("usage", {})
            tokens_used = usage.get("input_tokens", 0) + usage.get("output_tokens", 0)

            logger.debug(f"Match scored with {tokens_used} tokens")

            return {"parsed": parsed, "tokens_used": tokens_used}

        except Exception as e:
            logger.error(f"Match scoring failed: {str(e)}")
            raise
        finally:
            self.model = original_model

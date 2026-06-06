"""
CV parsing worker for both email intake and manual uploads
Extracts text from PDF/DOCX and parses with Claude API
"""

import logging
import time
from datetime import datetime
from pathlib import Path

from celery import shared_task

from pandapower.core.supabase import get_supabase_client
from pandapower.core.config import settings
from pandapower.integrations.anthropic_client import AnthropicClient

import structlog as _structlog
logger = _structlog.get_logger(__name__)


def extract_text_from_pdf(file_path: str) -> str:
    """Extract text from PDF file"""
    try:
        import PyPDF2

        text = ""
        with open(file_path, "rb") as f:
            pdf_reader = PyPDF2.PdfReader(f)
            for page in pdf_reader.pages:
                text += page.extract_text() + "\n"
        return text
    except Exception as e:
        logger.error(f"Error extracting text from PDF: {str(e)}")
        raise


def extract_text_from_docx(file_path: str) -> str:
    """Extract text from DOCX file"""
    try:
        from docx import Document

        doc = Document(file_path)
        text = ""
        for paragraph in doc.paragraphs:
            text += paragraph.text + "\n"
        return text
    except Exception as e:
        logger.error(f"Error extracting text from DOCX: {str(e)}")
        raise


def extract_text_from_file(file_path: str) -> str:
    """
    Extract text from CV file (PDF or DOCX)

    Args:
        file_path: Path to the CV file

    Returns:
        Extracted text content
    """
    file_ext = Path(file_path).suffix.lower()

    if file_ext == ".pdf":
        return extract_text_from_pdf(file_path)
    elif file_ext in [".docx", ".doc"]:
        return extract_text_from_docx(file_path)
    else:
        raise ValueError(f"Unsupported file type: {file_ext}")


@shared_task(bind=True, max_retries=3, queue="cv-parsing")
def parse_manual_cv_upload(self, cv_file_id: str, category_id: str):
    """
    Parse manually uploaded CV

    Steps:
    1. Extract text from PDF/DOCX
    2. Parse with Claude API
    3. Create candidate with pre-selected category
    4. Link to category skills

    Args:
        cv_file_id: UUID of cv_files entry
        category_id: UUID of candidate_categories entry
    """
    import asyncio

    async def _parse():
        db = get_supabase_client()
        claude_client = AnthropicClient(api_key=settings.ANTHROPIC_API_KEY)

        # Get CV file entry
        cv_file_response = (
            await db.table("cv_files")
            .select("*")
            .eq("id", cv_file_id)
            .single()
            .execute()
        )
        cv_file = cv_file_response.data
        file_path = cv_file["file_path"]

        logger.info(f"Parsing CV file: {cv_file['original_filename']}", cv_file_id=cv_file_id)

        # Update status to parsing
        await db.table("cv_files").update({
            "parse_status": "parsing",
            "parse_started_at": datetime.utcnow().isoformat(),
        }).eq("id", cv_file_id).execute()

        # Extract text from file
        raw_text = extract_text_from_file(file_path)
        logger.info(f"Extracted {len(raw_text)} characters from CV", cv_file_id=cv_file_id)

        # Parse with Claude
        start_time = time.time()
        extraction = await claude_client.extract_cv_data(raw_text)
        parse_duration_ms = int((time.time() - start_time) * 1000)

        logger.info(
            f"CV parsed in {parse_duration_ms}ms",
            cv_file_id=cv_file_id,
            tokens_used=extraction.get("tokens_used", 0),
        )

        # Get category for context
        category_response = (
            await db.table("candidate_categories")
            .select("*")
            .eq("id", category_id)
            .single()
            .execute()
        )
        category = category_response.data

        # Check for duplicate candidate (same email + category)
        if extraction.get("email"):
            existing_response = (
                await db.table("candidates")
                .select("id")
                .eq("email", extraction["email"])
                .eq("category_id", category_id)
                .execute()
            )
            if existing_response.data:
                logger.warning(
                    f"Candidate already exists with email {extraction['email']}",
                    cv_file_id=cv_file_id,
                    existing_candidate_id=existing_response.data[0]["id"],
                )
                # Link to existing candidate instead of creating new
                candidate_id = existing_response.data[0]["id"]
            else:
                # Create new candidate
                candidate_data = {
                    "full_name": extraction.get("full_name", "Unknown"),
                    "email": extraction.get("email"),
                    "phone": extraction.get("phone"),
                    "location": extraction.get("location"),
                    "key_skills": extraction.get("skills", []),
                    "experience_years": extraction.get("years_of_experience"),
                    "category_id": category_id,
                    "intake_method": "manual_upload",
                    "intake_source": cv_file["original_filename"],
                    "extraction_confidence": extraction.get("confidence_score", 0.0),
                    "extraction_notes": extraction.get("notes"),
                    "created_at": datetime.utcnow().isoformat(),
                }

                candidate_response = (
                    await db.table("candidates")
                    .insert(candidate_data)
                    .execute()
                )
                candidate_id = candidate_response.data[0]["id"]
                logger.info(f"Created new candidate", candidate_id=candidate_id)
        else:
            # No email, create candidate anyway
            candidate_data = {
                "full_name": extraction.get("full_name", "Unknown"),
                "phone": extraction.get("phone"),
                "location": extraction.get("location"),
                "key_skills": extraction.get("skills", []),
                "experience_years": extraction.get("years_of_experience"),
                "category_id": category_id,
                "intake_method": "manual_upload",
                "intake_source": cv_file["original_filename"],
                "extraction_confidence": extraction.get("confidence_score", 0.0),
                "extraction_notes": extraction.get("notes"),
                "created_at": datetime.utcnow().isoformat(),
            }

            candidate_response = (
                await db.table("candidates")
                .insert(candidate_data)
                .execute()
            )
            candidate_id = candidate_response.data[0]["id"]
            logger.info(f"Created candidate without email", candidate_id=candidate_id)

        # Update CV file with results
        await db.table("cv_files").update({
            "parse_status": "success",
            "parse_duration_ms": parse_duration_ms,
            "parse_completed_at": datetime.utcnow().isoformat(),
            "llm_tokens_used": extraction.get("tokens_used", 0),
            "detected_language": extraction.get("detected_language"),
            "candidate_id": candidate_id,
            "extracted_fields": extraction.get("extracted_fields"),
        }).eq("id", cv_file_id).execute()

        logger.info(
            f"Manual CV parsed successfully",
            cv_file_id=cv_file_id,
            candidate_id=candidate_id,
            category_id=category_id,
            category_name=category["name"],
            duration_ms=parse_duration_ms,
        )

        return {
            "cv_file_id": cv_file_id,
            "candidate_id": candidate_id,
            "category_name": category["name"],
            "status": "success",
            "duration_ms": parse_duration_ms,
        }

    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        return loop.run_until_complete(_parse())
    except Exception as e:
        logger.error(
            f"CV parsing failed: {str(e)}",
            exc_info=True,
            cv_file_id=cv_file_id,
        )

        db = get_supabase_client()

        async def _mark_failed():
            await db.table("cv_files").update({
                "parse_status": "failed",
                "parse_error": str(e),
                "parse_completed_at": datetime.utcnow().isoformat(),
            }).eq("id", cv_file_id).execute()

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            loop.run_until_complete(_mark_failed())
        except Exception as mark_err:
            logger.error(f"Failed to mark CV as failed: {str(mark_err)}")

        # Retry up to 3 times with exponential backoff
        if self.request.retries < self.max_retries:
            countdown = 60 * (2 ** self.request.retries)  # 60s, 120s, 240s
            logger.info(
                f"Retrying CV parsing",
                cv_file_id=cv_file_id,
                retry_count=self.request.retries + 1,
                countdown=countdown,
            )
            raise self.retry(exc=e, countdown=countdown)

        # Final failure
        logger.error(
            f"CV parsing failed after {self.max_retries} retries",
            cv_file_id=cv_file_id,
        )

        return {"status": "failed", "error": str(e), "cv_file_id": cv_file_id}


@shared_task(bind=True, max_retries=3, queue="cv-parsing")
def parse_email_cv_upload(self, cv_file_id: str):
    """
    Parse CV from email intake (no pre-selected category)

    Steps:
    1. Extract text from PDF/DOCX
    2. Parse with Claude API
    3. Create candidate without category (will be assigned later by Carmit)

    Args:
        cv_file_id: UUID of cv_files entry
    """
    import asyncio

    async def _parse():
        db = get_supabase_client()
        claude_client = AnthropicClient(api_key=settings.ANTHROPIC_API_KEY)

        # Get CV file entry
        cv_file_response = (
            await db.table("cv_files")
            .select("*")
            .eq("id", cv_file_id)
            .single()
            .execute()
        )
        cv_file = cv_file_response.data
        file_path = cv_file["file_path"]

        logger.info(f"Parsing email CV: {cv_file['original_filename']}", cv_file_id=cv_file_id)

        # Update status to parsing
        await db.table("cv_files").update({
            "parse_status": "parsing",
            "parse_started_at": datetime.utcnow().isoformat(),
        }).eq("id", cv_file_id).execute()

        # Extract text from file
        raw_text = extract_text_from_file(file_path)

        # Parse with Claude
        start_time = time.time()
        extraction = await claude_client.extract_cv_data(raw_text)
        parse_duration_ms = int((time.time() - start_time) * 1000)

        # Check for duplicate candidate by email
        if extraction.get("email"):
            existing_response = (
                await db.table("candidates")
                .select("id")
                .eq("email", extraction["email"])
                .execute()
            )
            if existing_response.data:
                logger.warning(
                    f"Candidate already exists with email {extraction['email']}",
                    cv_file_id=cv_file_id,
                )
                candidate_id = existing_response.data[0]["id"]
            else:
                # Create new candidate
                candidate_data = {
                    "full_name": extraction.get("full_name", "Unknown"),
                    "email": extraction.get("email"),
                    "phone": extraction.get("phone"),
                    "location": extraction.get("location"),
                    "key_skills": extraction.get("skills", []),
                    "experience_years": extraction.get("years_of_experience"),
                    "intake_method": "email",
                    "intake_source": cv_file.get("email_subject", "Email"),
                    "extraction_confidence": extraction.get("confidence_score", 0.0),
                    "created_at": datetime.utcnow().isoformat(),
                }

                candidate_response = (
                    await db.table("candidates")
                    .insert(candidate_data)
                    .execute()
                )
                candidate_id = candidate_response.data[0]["id"]
        else:
            # Create candidate without email
            candidate_data = {
                "full_name": extraction.get("full_name", "Unknown"),
                "phone": extraction.get("phone"),
                "location": extraction.get("location"),
                "key_skills": extraction.get("skills", []),
                "experience_years": extraction.get("years_of_experience"),
                "intake_method": "email",
                "extraction_confidence": extraction.get("confidence_score", 0.0),
                "created_at": datetime.utcnow().isoformat(),
            }

            candidate_response = (
                await db.table("candidates")
                .insert(candidate_data)
                .execute()
            )
            candidate_id = candidate_response.data[0]["id"]

        # Update CV file with results
        await db.table("cv_files").update({
            "parse_status": "success",
            "parse_duration_ms": parse_duration_ms,
            "parse_completed_at": datetime.utcnow().isoformat(),
            "llm_tokens_used": extraction.get("tokens_used", 0),
            "detected_language": extraction.get("detected_language"),
            "candidate_id": candidate_id,
            "extracted_fields": extraction.get("extracted_fields"),
            "upload_method": "email",
        }).eq("id", cv_file_id).execute()

        logger.info(
            f"Email CV parsed successfully",
            cv_file_id=cv_file_id,
            candidate_id=candidate_id,
        )

        return {
            "cv_file_id": cv_file_id,
            "candidate_id": candidate_id,
            "status": "success",
            "duration_ms": parse_duration_ms,
        }

    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        return loop.run_until_complete(_parse())
    except Exception as e:
        logger.error(f"Email CV parsing failed: {str(e)}", exc_info=True, cv_file_id=cv_file_id)

        db = get_supabase_client()

        async def _mark_failed():
            await db.table("cv_files").update({
                "parse_status": "failed",
                "parse_error": str(e),
                "parse_completed_at": datetime.utcnow().isoformat(),
            }).eq("id", cv_file_id).execute()

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            loop.run_until_complete(_mark_failed())
        except Exception as mark_err:
            logger.error(f"Failed to mark CV as failed: {str(mark_err)}")

        # Retry with exponential backoff
        if self.request.retries < self.max_retries:
            countdown = 60 * (2 ** self.request.retries)
            raise self.retry(exc=e, countdown=countdown)

        return {"status": "failed", "error": str(e), "cv_file_id": cv_file_id}

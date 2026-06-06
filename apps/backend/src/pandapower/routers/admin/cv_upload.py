"""
Manual CV upload endpoint for admins
Allows uploading single or multiple CVs with category selection
"""

import logging
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, Depends
from fastapi.responses import JSONResponse

from pandapower.core.supabase import get_supabase_client
from pandapower.workers.cv_parsing import parse_manual_cv_upload

import structlog as _structlog
logger = _structlog.get_logger(__name__)

router = APIRouter(prefix="/admin/cv", tags=["cv-upload"])

# Allowed file extensions
ALLOWED_EXTENSIONS = {".pdf", ".doc", ".docx"}
MAX_FILE_SIZE = 20 * 1024 * 1024  # 20MB


@router.post("/upload")
async def upload_cv_manual(
    category_id: str = Form(...),
    files: list[UploadFile] = File(...),
) -> JSONResponse:
    """
    Manual CV upload endpoint

    - Accepts single or multiple files
    - Validates file types (PDF, DOCX, DOC)
    - Queues async parsing tasks
    - Returns batch_id for tracking

    Args:
        category_id: UUID of candidate category
        files: List of CV files to upload

    Returns:
        {
            "batch_id": "uuid",
            "uploaded_count": 15,
            "files": [
                {"filename": "john.pdf", "file_id": "uuid"}
            ],
            "category_id": "uuid",
            "category_name": "Backend Developer - Level 1"
        }
    """

    db = get_supabase_client()

    try:
        # Validate category exists
        try:
            category_response = (
                await db.table("candidate_categories")
                .select("*")
                .eq("id", category_id)
                .single()
                .execute()
            )
            category = category_response.data
        except Exception:
            raise HTTPException(status_code=404, detail="Category not found")

        uploaded_files = []
        batch_id = str(uuid.uuid4())
        errors = []

        # Create temporary directory for batch
        temp_dir = Path(f"/tmp/cv_uploads/{batch_id}")
        temp_dir.mkdir(parents=True, exist_ok=True)

        for file in files:
            try:
                # Validate file extension
                file_ext = Path(file.filename).suffix.lower()
                if file_ext not in ALLOWED_EXTENSIONS:
                    errors.append(
                        f"{file.filename}: Invalid file type '{file_ext}'. "
                        f"Only {', '.join(ALLOWED_EXTENSIONS)} supported."
                    )
                    continue

                # Validate file size
                file_content = await file.read()
                if len(file_content) > MAX_FILE_SIZE:
                    errors.append(
                        f"{file.filename}: File too large "
                        f"({len(file_content) // 1024 // 1024}MB). "
                        f"Maximum 20MB."
                    )
                    continue

                # Save to temp location
                file_path = temp_dir / file.filename
                with open(file_path, "wb") as f:
                    f.write(file_content)

                # Create entry in database
                cv_file_insert = {
                    "original_filename": file.filename,
                    "file_path": str(file_path),
                    "file_extension": file_ext,
                    "file_size_bytes": len(file_content),
                    "upload_method": "manual",
                    "category_id": category_id,
                    "batch_id": batch_id,
                    "parse_status": "pending",
                    "created_at": datetime.utcnow().isoformat(),
                }

                cv_file_response = (
                    await db.table("cv_files")
                    .insert(cv_file_insert)
                    .execute()
                )
                cv_file_id = cv_file_response.data[0]["id"]

                uploaded_files.append({
                    "filename": file.filename,
                    "file_id": cv_file_id,
                    "size_mb": len(file_content) / 1024 / 1024,
                })

                # Queue async parsing task
                parse_manual_cv_upload.apply_async(
                    args=[cv_file_id, category_id],
                    queue="cv-parsing",
                    priority=5,  # Medium priority
                )

                logger.info(
                    f"CV file queued for parsing",
                    cv_file_id=cv_file_id,
                    filename=file.filename,
                    category_id=category_id,
                    batch_id=batch_id,
                )

            except Exception as e:
                logger.error(
                    f"Error processing file {file.filename}: {str(e)}",
                    exc_info=True,
                )
                errors.append(f"{file.filename}: {str(e)}")
                continue

        # Check if any files were uploaded
        if len(uploaded_files) == 0:
            raise HTTPException(
                status_code=400,
                detail=f"No valid files uploaded. Errors: {'; '.join(errors)}"
            )

        response_data = {
            "batch_id": batch_id,
            "uploaded_count": len(uploaded_files),
            "files": uploaded_files,
            "category_id": category_id,
            "category_name": category["name"],
            "total_attempted": len(files),
            "errors": errors if errors else None,
        }

        logger.info(
            f"CV batch upload initiated",
            batch_id=batch_id,
            file_count=len(uploaded_files),
            category_id=category_id,
        )

        return JSONResponse(response_data, status_code=202)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"CV upload error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/categories")
async def get_candidate_categories():
    """
    Get all available candidate categories

    Returns:
    {
        "categories": [
            {
                "id": "uuid",
                "name": "Backend Developer - Level 1",
                "description": "...",
                "level": 1,
                "skills": ["Python", "Node.js", ...]
            }
        ]
    }
    """
    db = get_supabase_client()

    try:
        response = (
            await db.table("candidate_categories")
            .select("*")
            .eq("is_active", True)
            .order("level")
            .execute()
        )

        return {"categories": response.data}

    except Exception as e:
        logger.error(f"Error fetching categories: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/upload-status/{batch_id}")
async def get_upload_status(batch_id: str):
    """
    Get status of uploaded batch

    Returns:
    {
        "batch_id": "uuid",
        "total_files": 15,
        "processing": 3,
        "success": 10,
        "failed": 2,
        "files": [
            {
                "filename": "john.pdf",
                "parse_status": "success",
                "candidate_id": "uuid",
                "created_at": "2026-05-23T10:30:00Z"
            }
        ]
    }
    """
    db = get_supabase_client()

    try:
        response = (
            await db.table("cv_files")
            .select("*")
            .eq("batch_id", batch_id)
            .execute()
        )

        files = response.data

        return {
            "batch_id": batch_id,
            "total_files": len(files),
            "processing": sum(1 for f in files if f["parse_status"] == "parsing"),
            "success": sum(1 for f in files if f["parse_status"] == "success"),
            "failed": sum(1 for f in files if f["parse_status"] == "failed"),
            "files": files,
        }

    except Exception as e:
        logger.error(f"Error fetching upload status: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/recent-uploads")
async def get_recent_uploads(limit: int = 10):
    """
    Get recent batch uploads with status summary

    Returns:
    {
        "uploads": [
            {
                "batch_id": "uuid",
                "category_name": "Backend Developer - Level 1",
                "total_files": 15,
                "processing": 3,
                "success": 10,
                "failed": 2,
                "created_at": "2026-05-23T10:30:00Z"
            }
        ]
    }
    """
    db = get_supabase_client()

    try:
        # Get distinct batch IDs from recent uploads
        response = (
            await db.table("cv_files")
            .select("batch_id,category_id,parse_status,created_at")
            .eq("upload_method", "manual")
            .order("created_at", descending=True)
            .limit(limit * 20)  # Get more to filter by batch
            .execute()
        )

        # Group by batch_id and compute stats
        batches = {}
        for file in response.data:
            batch_id = file["batch_id"]
            if batch_id not in batches:
                batches[batch_id] = {
                    "batch_id": batch_id,
                    "category_id": file["category_id"],
                    "created_at": file["created_at"],
                    "total": 0,
                    "processing": 0,
                    "success": 0,
                    "failed": 0,
                }

            batches[batch_id]["total"] += 1
            if file["parse_status"] == "parsing":
                batches[batch_id]["processing"] += 1
            elif file["parse_status"] == "success":
                batches[batch_id]["success"] += 1
            elif file["parse_status"] == "failed":
                batches[batch_id]["failed"] += 1

        # Get category names
        batch_list = list(batches.values())[:limit]

        for batch in batch_list:
            try:
                cat_response = (
                    await db.table("candidate_categories")
                    .select("name")
                    .eq("id", batch["category_id"])
                    .single()
                    .execute()
                )
                batch["category_name"] = cat_response.data["name"]
            except:
                batch["category_name"] = "Unknown"

        return {"uploads": batch_list}

    except Exception as e:
        logger.error(f"Error fetching recent uploads: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

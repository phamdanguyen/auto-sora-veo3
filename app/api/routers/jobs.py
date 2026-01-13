"""
Jobs Router
Implements: Single Responsibility Principle (SRP)

This router handles all job-related endpoints:
- CRUD operations
- Job execution (retry, cancel)
- File uploads
- Bulk actions
"""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime
from ...core.services.job_service import JobService
from ...core.services.task_service import TaskService
from ...core.domain.job import Job
from ..dependencies import get_job_service, get_task_service
from sqlalchemy.orm import Session
from ..dependencies import get_db

import logging
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/jobs", tags=["jobs"])

# ========== Schemas ==========
class JobCreate(BaseModel):
    """Schema for creating a new job"""
    prompt: str
    duration: int = 5
    aspect_ratio: str = "16:9"
    image_path: Optional[str] = None


class JobUpdate(BaseModel):
    """Schema for updating a job"""
    prompt: Optional[str] = None
    duration: Optional[int] = None
    aspect_ratio: Optional[str] = None
    image_path: Optional[str] = None


class JobResponse(BaseModel):
    """Schema for job response"""
    id: int
    prompt: str
    image_path: Optional[str] = None
    duration: int
    aspect_ratio: str
    status: str
    progress: int
    error_message: Optional[str] = None
    video_url: Optional[str] = None
    local_path: Optional[str] = None
    video_id: Optional[str] = None
    account_id: Optional[int] = None
    task_state: Optional[str] = None
    progress_message: Optional[str] = None
    retry_count: int
    created_at: datetime
    updated_at: Optional[datetime] = None

    @staticmethod
    def from_domain(job: Job) -> "JobResponse":
        """Convert domain Job to API response"""
        return JobResponse(
            id=job.id.value,
            prompt=job.spec.prompt,
            image_path=job.spec.image_path,
            duration=job.spec.duration,
            aspect_ratio=job.spec.aspect_ratio,
            status=job.progress.status.value,
            progress=job.progress.progress,
            error_message=job.progress.error_message,
            video_url=job.result.video_url if job.result else None,
            local_path=job.result.local_path if job.result else None,
            video_id=job.result.video_id if job.result else None,
            account_id=job.account_id.value if hasattr(job.account_id, "value") else job.account_id,
            task_state=str(job.task_state) if job.task_state else None,
            progress_message=None,
            retry_count=job.progress.retry_count if job.progress else 0,
            created_at=job.created_at,
            updated_at=job.updated_at
        )


class BulkActionRequest(BaseModel):
    """Schema for bulk actions"""
    action: str  # "delete", "retry", "cancel"
    job_ids: List[int]


# ========== Endpoints ==========
@router.post("/", response_model=JobResponse)
async def create_job(
    data: JobCreate,
    service: JobService = Depends(get_job_service)
):
    """
    Create a new job

    Args:
        data: Job creation data (prompt, duration, aspect_ratio, image_path)
        service: JobService instance (injected)

    Returns:
        Created job details

    Raises:
        HTTPException 400: If validation fails
    """
    try:
        job = await service.create_job(
            prompt=data.prompt,
            duration=data.duration,
            aspect_ratio=data.aspect_ratio,
            image_path=data.image_path
        )
        return JobResponse.from_domain(job)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/", response_model=List[JobResponse])
async def list_jobs(
    skip: int = 0,
    limit: int = 100,
    category: Optional[str] = None,
    service: JobService = Depends(get_job_service)
):
    """
    List jobs with optional category filter

    Args:
        skip: Number of jobs to skip (pagination)
        limit: Maximum number of jobs to return
        category: Filter by category ("active", "history", or None for all)
        service: JobService instance (injected)

    Returns:
        List of jobs
    """
    jobs = await service.list_jobs(skip, limit, category)
    return [JobResponse.from_domain(job) for job in jobs]


@router.get("/{job_id}", response_model=JobResponse)
async def get_job(
    job_id: int,
    service: JobService = Depends(get_job_service)
):
    """
    Get job by ID

    Args:
        job_id: Job ID
        service: JobService instance (injected)

    Returns:
        Job details

    Raises:
        HTTPException 404: If job not found
    """
    job = await service.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return JobResponse.from_domain(job)


@router.put("/{job_id}", response_model=JobResponse)
async def update_job(
    job_id: int,
    data: JobUpdate,
    service: JobService = Depends(get_job_service)
):
    """
    Update job

    Args:
        job_id: Job ID
        data: Job update data
        service: JobService instance (injected)

    Returns:
        Updated job details

    Raises:
        HTTPException 404: If job not found
    """
    try:
        job = await service.update_job(
            job_id=job_id,
            prompt=data.prompt,
            duration=data.duration,
            aspect_ratio=data.aspect_ratio,
            image_path=data.image_path
        )
        return JobResponse.from_domain(job)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete("/{job_id}")
async def delete_job(
    job_id: int,
    service: JobService = Depends(get_job_service)
):
    """
    Delete job

    Args:
        job_id: Job ID
        service: JobService instance (injected)

    Returns:
        Success status

    Raises:
        HTTPException 404: If job not found
    """
    success = await service.delete_job(job_id)
    if not success:
        raise HTTPException(status_code=404, detail="Job not found")
    return {"ok": True}


@router.post("/{job_id}/retry")
async def retry_job(
    job_id: int,
    service: JobService = Depends(get_job_service),
    task_service: TaskService = Depends(get_task_service)
):
    """
    Retry failed job

    Resets the job to PENDING status and starts execution.

    Args:
        job_id: Job ID
        service: JobService instance (injected)
        task_service: TaskService instance (injected)

    Returns:
        Success status

    Raises:
        HTTPException 400: If job cannot be retried
    """
    try:
        # Reset job status
        job = await service.retry_job(job_id)

        # Start job execution via task manager
        await task_service.start_job(job_id)

        return {"ok": True}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{job_id}/cancel")
async def cancel_job(
    job_id: int,
    service: JobService = Depends(get_job_service)
):
    """
    Cancel running job

    Args:
        job_id: Job ID
        service: JobService instance (injected)

    Returns:
        Success status

    Raises:
        HTTPException 400: If job cannot be cancelled
    """
    try:
        await service.cancel_job(job_id)
        return {"ok": True}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/bulk_action")
async def bulk_job_action(
    req: BulkActionRequest,
    service: JobService = Depends(get_job_service),
    task_service: TaskService = Depends(get_task_service)
):
    """
    Perform bulk action on multiple jobs

    Args:
        req: Bulk action request (action type and job IDs)
        service: JobService instance (injected)

    Returns:
        Action results

    Raises:
        HTTPException 400: If action is invalid
    """
    if req.action == "delete":
        count = await service.bulk_delete_jobs(req.job_ids)
        return {"ok": True, "deleted": count}

    elif req.action == "retry":
        results = []
        for job_id in req.job_ids:
            try:
                await service.retry_job(job_id)
                results.append({"job_id": job_id, "ok": True})
            except Exception as e:
                results.append({"job_id": job_id, "ok": False, "error": str(e)})
        return {"ok": True, "results": results}

    elif req.action == "cancel":
        results = []
        for job_id in req.job_ids:
            try:
                await service.cancel_job(job_id)
                results.append({"job_id": job_id, "ok": True})
            except Exception as e:
                results.append({"job_id": job_id, "ok": False, "error": str(e)})
        return {"ok": True, "results": results}

    elif req.action in ["start", "start_selected", "start_all"]:
        results = []
        for job_id in req.job_ids:
            try:
                await task_service.start_job(job_id)
                results.append({"job_id": job_id, "ok": True})
            except Exception as e:
                logger.error(f"Failed to start job {job_id}: {e}")
                results.append({"job_id": job_id, "ok": False, "error": str(e)})
        return {"ok": True, "results": results}

    else:
        logger.warning(f"Invalid bulk action: {req.action}")
        raise HTTPException(status_code=400, detail=f"Invalid action: {req.action}")


@router.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    """
    Upload file (image) for job

    Saves the file to data/uploads/ and returns the file path.

    Args:
        file: Uploaded file

    Returns:
        File path

    Raises:
        HTTPException 400: If upload fails
    """
    import shutil
    import os
    from pathlib import Path

    try:
        # Create uploads directory
        upload_dir = Path("data/uploads")
        upload_dir.mkdir(parents=True, exist_ok=True)

        # Generate unique filename
        import uuid
        file_ext = os.path.splitext(file.filename)[1]
        unique_filename = f"{uuid.uuid4()}{file_ext}"
        file_path = upload_dir / unique_filename

        # Save file
        with file_path.open("wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        return {
            "ok": True,
            "path": str(file_path),
            "filename": unique_filename
        }
    except Exception as e:
        logger.error(f"Failed to upload file: {e}")
        raise HTTPException(status_code=400, detail=f"Upload failed: {str(e)}")


# ========== Complex Endpoints (TODO) ==========
# These endpoints require integration with worker/task manager

@router.post("/{job_id}/tasks/{task_name}/run")
async def run_job_task(job_id: int, task_name: str, db: Session = Depends(get_db)):
    """
    Run specific task for a job

    TODO: Implement using TaskService
    """
    # Import the old implementation via deprecated path
    from ...legacy.endpoints import run_job_task as old_run_job_task
    return await old_run_job_task(job_id, task_name, db)


@router.post("/{job_id}/open_folder")
def open_job_folder(job_id: int, db: Session = Depends(get_db)):
    """
    Open job folder in file explorer

    Opens the folder containing the downloaded video.

    TODO: Migrate to use JobService
    """
    # Import the old implementation for now
    from ...legacy.endpoints import open_job_folder as old_open_job_folder
    return old_open_job_folder(job_id, db)


@router.post("/{job_id}/open_video")
def open_job_video(job_id: int, db: Session = Depends(get_db)):
    """
    Open video in default media player

    TODO: Migrate to use JobService
    """
    # Import the old implementation for now
    from ...legacy.endpoints import open_job_video as old_open_job_video
    return old_open_job_video(job_id, db)

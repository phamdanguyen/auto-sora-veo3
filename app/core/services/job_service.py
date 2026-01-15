"""
Job Service - Business logic cho Job management
Implements: Single Responsibility Principle (SRP)
"""
from typing import Optional, List
from ..repositories.job_repo import JobRepository
from ..repositories.account_repo import AccountRepository
from ..domain.job import Job, JobSpec, JobProgress, JobResult, JobStatus, JobId
import logging

logger = logging.getLogger(__name__)

class JobService:
    """Service xử lý job business logic"""

    def __init__(
        self,
        job_repo: JobRepository,
        account_repo: AccountRepository
    ):
        self.job_repo = job_repo
        self.account_repo = account_repo

    async def create_job(
        self,
        prompt: str,
        duration: int,
        aspect_ratio: str,
        image_path: Optional[str] = None
    ) -> Job:
        """
        Create new job

        Business rules:
        - Prompt cannot be empty
        - Duration must be 5, 10, or 15
        - Job starts in DRAFT status
        """
        # Validate inputs (done in JobSpec)
        spec = JobSpec(
            prompt=prompt,
            image_path=image_path,
            duration=duration,
            aspect_ratio=aspect_ratio
        )

        # Create job
        job = Job(
            id=JobId(0),  # Will be set by DB
            spec=spec,
            progress=JobProgress(
                status=JobStatus.DRAFT,
                progress=0
            ),
            result=JobResult()
        )

        created = await self.job_repo.create(job)
        self.job_repo.commit()
        return created

    async def get_job(self, job_id: int) -> Optional[Job]:
        """Get job by ID"""
        return await self.job_repo.get_by_id(job_id)

    async def list_jobs(
        self,
        skip: int = 0,
        limit: int = 100,
        category: Optional[str] = None
    ) -> List[Job]:
        """
        List jobs với category filter

        Args:
            category: "active" (not done), "history" (done/failed/cancelled), or None (all)
        """
        if category == "active":
            status_filter = [
                JobStatus.DRAFT, JobStatus.PENDING, JobStatus.PROCESSING,
                JobStatus.SENT_PROMPT, JobStatus.GENERATING, JobStatus.DOWNLOAD
            ]
        elif category == "history":
            status_filter = [
                JobStatus.COMPLETED, JobStatus.DONE,
                JobStatus.FAILED, JobStatus.CANCELLED
            ]
        else:
            status_filter = None

        return await self.job_repo.get_all(skip, limit, status_filter)

    async def update_job(
        self,
        job_id: int,
        prompt: Optional[str] = None,
        duration: Optional[int] = None,
        aspect_ratio: Optional[str] = None,
        image_path: Optional[str] = None
    ) -> Job:
        """Update job fields"""
        job = await self.job_repo.get_by_id(job_id)
        if not job:
            raise ValueError(f"Job {job_id} not found")

        # Update spec
        if prompt or duration or aspect_ratio or image_path is not None:
            job.spec = JobSpec(
                prompt=prompt or job.spec.prompt,
                duration=duration or job.spec.duration,
                aspect_ratio=aspect_ratio or job.spec.aspect_ratio,
                image_path=image_path if image_path is not None else job.spec.image_path
            )

        updated = await self.job_repo.update(job)
        self.job_repo.commit()
        return updated

    async def delete_job(self, job_id: int) -> bool:
        """Delete job"""
        success = await self.job_repo.delete(job_id)
        if success:
            self.job_repo.commit()
        return success

    async def bulk_delete_jobs(self, job_ids: List[int]) -> int:
        """Delete multiple jobs"""
        count = await self.job_repo.bulk_delete(job_ids)
        self.job_repo.commit()
        return count

    async def retry_job(self, job_id: int) -> Job:
        """
        Retry failed job

        Business rules:
        - Job must be in FAILED or CANCELLED status
        - Reset to PENDING status
        - Clear error message
        - Reset retry count
        """
        job = await self.job_repo.get_by_id(job_id)
        if not job:
            raise ValueError(f"Job {job_id} not found")

        if job.progress.status not in [JobStatus.FAILED, JobStatus.CANCELLED]:
            raise ValueError(f"Cannot retry job in status {job.progress.status}")

        # Reset job
        job.progress = JobProgress(
            status=JobStatus.PENDING,
            progress=0,
            error_message=None,
            retry_count=0,
            max_retries=job.progress.max_retries
        )

        updated = await self.job_repo.update(job)
        self.job_repo.commit()
        return updated

    async def cancel_job(self, job_id: int) -> Job:
        """
        Cancel running job

        Business rules:
        - Job must be in active status (PENDING, PROCESSING, etc.)
        - Set status to CANCELLED
        - Set error message
        """
        job = await self.job_repo.get_by_id(job_id)
        if not job:
            raise ValueError(f"Job {job_id} not found")

        active_statuses = [
            JobStatus.PENDING, JobStatus.PROCESSING,
            JobStatus.SENT_PROMPT, JobStatus.GENERATING, JobStatus.DOWNLOAD
        ]

        if job.progress.status not in active_statuses:
            raise ValueError(f"Cannot cancel job in status {job.progress.status}")

        # Cancel job
        job.progress.status = JobStatus.CANCELLED
        job.progress.error_message = "Cancelled by user"

        updated = await self.job_repo.update(job)
        self.job_repo.commit()
        return updated

    async def open_job_folder(self, job_id: int) -> bool:
        """
        Open folder containing job video
        """
        import os
        import subprocess
        
        job = await self.job_repo.get_by_id(job_id)
        if not job or not job.result.local_path:
            raise ValueError(f"Job {job_id} has no file")

        file_path = job.result.local_path
        folder_path = os.path.dirname(os.path.abspath(file_path))
        
        if not os.path.exists(folder_path):
             raise ValueError("Folder not found")

        if os.name == 'nt':
            subprocess.run(['explorer', '/select,', os.path.abspath(file_path)])
        elif os.name == 'posix':
            subprocess.run(['xdg-open', folder_path])
            
        return True

    async def open_job_video(self, job_id: int) -> bool:
        """
        Open video file in default player
        """
        import os
        import subprocess
        
        job = await self.job_repo.get_by_id(job_id)
        if not job or not job.result.local_path:
            raise ValueError(f"Job {job_id} has no file")

        file_path = os.path.abspath(job.result.local_path)
        
        if not os.path.exists(file_path):
             raise ValueError("File not found")

        try:
            os.startfile(file_path) # Windows only
        except AttributeError:
            # Mac/Linux
            if os.name == 'posix':
                 subprocess.run(['xdg-open', file_path])
            else:
                 subprocess.run(['open', file_path])
                 
        return True

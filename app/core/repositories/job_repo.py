"""
Job Repository

Implementation of repository pattern for Job aggregate

Implements:
- DIP: Implements abstract BaseRepository
- SRP: Single responsibility (Job data access)
- ISP: Provides specific methods for job queries
"""

from typing import Optional, List
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from .base import BaseRepository
from ..domain.job import Job, JobId, JobStatus
from ...models import Job as JobModel


class JobRepository(BaseRepository[Job]):
    """
    Repository cho Job aggregate

    Handles:
    - CRUD operations
    - Job-specific queries (by status, pending, stale, etc.)
    - Conversion between domain models and ORM models
    """

    async def get_by_id(self, id: int) -> Optional[Job]:
        """
        Lấy job theo ID

        Args:
            id: Job ID

        Returns:
            Job domain model or None
        """
        orm_job = self.session.query(JobModel).filter_by(id=id).first()
        return Job.from_orm(orm_job) if orm_job else None

    async def get_all(
        self,
        skip: int = 0,
        limit: int = 100,
        status_filter: Optional[List[JobStatus]] = None
    ) -> List[Job]:
        """
        Lấy danh sách jobs với filter

        Args:
            skip: Records to skip
            limit: Max records to return
            status_filter: List of statuses to filter by

        Returns:
            List of Job domain models
        """
        query = self.session.query(JobModel)

        if status_filter:
            status_values = [s.value for s in status_filter]
            query = query.filter(JobModel.status.in_(status_values))

        orm_jobs = (
            query
            .order_by(JobModel.id.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )
        return [Job.from_orm(job) for job in orm_jobs]

    async def get_pending_jobs(self) -> List[Job]:
        """
        Lấy jobs đang pending hoặc cần hydrate

        Used for queue hydration on startup

        Returns:
            List of pending Job domain models
        """
        orm_jobs = (
            self.session.query(JobModel)
            .filter(JobModel.status.in_(["pending", "download"]))
            .order_by(JobModel.created_at.asc())
            .all()
        )
        return [Job.from_orm(job) for job in orm_jobs]

    async def get_active_jobs(self) -> List[Job]:
        """
        Lấy jobs đang active (đang chạy)

        Returns:
            List of active Job domain models
        """
        active_statuses = [
            JobStatus.PENDING.value,
            JobStatus.PROCESSING.value,
            JobStatus.SENT_PROMPT.value,
            JobStatus.GENERATING.value,
            JobStatus.DOWNLOAD.value
        ]

        orm_jobs = (
            self.session.query(JobModel)
            .filter(JobModel.status.in_(active_statuses))
            .order_by(JobModel.updated_at.desc())
            .all()
        )
        return [Job.from_orm(job) for job in orm_jobs]

    async def get_stale_jobs(self, cutoff_minutes: int = 15) -> List[Job]:
        """
        Lấy jobs bị stuck (stale)

        Jobs that are:
        - In active status
        - Not updated for more than cutoff_minutes

        Args:
            cutoff_minutes: Minutes before considering job stale

        Returns:
            List of stale Job domain models
        """
        cutoff = datetime.utcnow() - timedelta(minutes=cutoff_minutes)

        orm_jobs = (
            self.session.query(JobModel)
            .filter(
                JobModel.status.in_([
                    "processing", "sent_prompt", "generating", "download"
                ]),
                JobModel.updated_at < cutoff
            )
            .all()
        )
        return [Job.from_orm(job) for job in orm_jobs]

    async def get_failed_jobs(self) -> List[Job]:
        """
        Lấy jobs failed

        Returns:
            List of failed Job domain models
        """
        orm_jobs = (
            self.session.query(JobModel)
            .filter(JobModel.status == JobStatus.FAILED.value)
            .order_by(JobModel.updated_at.desc())
            .all()
        )
        return [Job.from_orm(job) for job in orm_jobs]

    async def get_completed_jobs(
        self,
        skip: int = 0,
        limit: int = 100
    ) -> List[Job]:
        """
        Lấy jobs completed/done

        Args:
            skip: Records to skip
            limit: Max records to return

        Returns:
            List of completed Job domain models
        """
        orm_jobs = (
            self.session.query(JobModel)
            .filter(JobModel.status.in_([
                JobStatus.COMPLETED.value,
                JobStatus.DONE.value
            ]))
            .order_by(JobModel.updated_at.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )
        return [Job.from_orm(job) for job in orm_jobs]

    async def create(self, job: Job) -> Job:
        """
        Tạo job mới

        Args:
            job: Job domain model

        Returns:
            Created job with ID populated
        """
        orm_job = JobModel(**job.to_orm_dict())
        self.session.add(orm_job)
        self.flush()  # Get auto-generated ID
        return Job.from_orm(orm_job)

    async def update(self, job: Job) -> Job:
        """
        Cập nhật job

        Updates all fields from domain model

        Args:
            job: Job domain model

        Returns:
            Updated job

        Raises:
            ValueError: If job not found
        """
        orm_job = self.session.query(JobModel).filter_by(id=job.id.value).first()
        if not orm_job:
            raise ValueError(f"Job {job.id.value} not found")

        # Update all fields from domain model
        for key, value in job.to_orm_dict().items():
            setattr(orm_job, key, value)

        self.flush()
        return Job.from_orm(orm_job)

    async def update_status(
        self,
        job_id: int,
        status: JobStatus,
        error_message: Optional[str] = None
    ) -> Job:
        """
        Update only job status (optimized)

        Args:
            job_id: Job ID
            status: New status
            error_message: Optional error message

        Returns:
            Updated job

        Raises:
            ValueError: If job not found
        """
        orm_job = self.session.query(JobModel).filter_by(id=job_id).first()
        if not orm_job:
            raise ValueError(f"Job {job_id} not found")

        orm_job.status = status.value
        orm_job.error_message = error_message
        orm_job.updated_at = datetime.utcnow()

        self.flush()
        return Job.from_orm(orm_job)

    async def update_progress(
        self,
        job_id: int,
        progress: int
    ) -> Job:
        """
        Update only job progress (optimized)

        Args:
            job_id: Job ID
            progress: Progress percentage (0-100)

        Returns:
            Updated job

        Raises:
            ValueError: If job not found
        """
        orm_job = self.session.query(JobModel).filter_by(id=job_id).first()
        if not orm_job:
            raise ValueError(f"Job {job_id} not found")

        orm_job.progress = progress
        orm_job.updated_at = datetime.utcnow()

        self.flush()
        return Job.from_orm(orm_job)

    async def delete(self, id: int) -> bool:
        """
        Xóa job

        Args:
            id: Job ID

        Returns:
            True if deleted, False if not found
        """
        orm_job = self.session.query(JobModel).filter_by(id=id).first()
        if orm_job:
            self.session.delete(orm_job)
            return True
        return False

    async def bulk_delete(self, ids: List[int]) -> int:
        """
        Xóa nhiều jobs

        Args:
            ids: List of job IDs to delete

        Returns:
            Number of jobs deleted
        """
        count = self.session.query(JobModel).filter(
            JobModel.id.in_(ids)
        ).delete(synchronize_session=False)
        return count

    async def bulk_update_status(
        self,
        ids: List[int],
        status: JobStatus
    ) -> int:
        """
        Update status cho nhiều jobs

        Args:
            ids: List of job IDs
            status: New status

        Returns:
            Number of jobs updated
        """
        count = self.session.query(JobModel).filter(
            JobModel.id.in_(ids)
        ).update(
            {
                "status": status.value,
                "updated_at": datetime.utcnow()
            },
            synchronize_session=False
        )
        return count

    async def count_by_status(self, status: JobStatus) -> int:
        """
        Count jobs by status

        Args:
            status: Job status

        Returns:
            Number of jobs
        """
        return self.session.query(JobModel).filter_by(status=status.value).count()

    async def count_active_jobs(self) -> int:
        """
        Count active jobs

        Returns:
            Number of active jobs
        """
        active_statuses = [
            JobStatus.PENDING.value,
            JobStatus.PROCESSING.value,
            JobStatus.SENT_PROMPT.value,
            JobStatus.GENERATING.value,
            JobStatus.DOWNLOAD.value
        ]
        return self.session.query(JobModel).filter(
            JobModel.status.in_(active_statuses)
        ).count()

    async def get_job_by_video_id(self, video_id: str) -> Optional[Job]:
        """
        Get job by video_id

        Args:
            video_id: Video ID

        Returns:
            Job domain model or None
        """
        orm_job = self.session.query(JobModel).filter_by(video_id=video_id).first()
        return Job.from_orm(orm_job) if orm_job else None

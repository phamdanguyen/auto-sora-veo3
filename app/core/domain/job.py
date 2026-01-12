"""
Job Domain Models

Implements Interface Segregation Principle (ISP):
- Tách Job thành nhiều concerns: Spec, Progress, Result
- Code chỉ depend vào interface cần thiết

Value Objects:
- JobId: Identity
- JobSpec: Job specification (immutable)
- JobProgress: Progress tracking
- JobResult: Job result

Aggregate Root:
- Job: Root entity managing all job concerns
"""

from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime
from enum import Enum


class JobStatus(str, Enum):
    """
    Job status enum
    Defines valid job states and transitions
    """
    DRAFT = "draft"
    PENDING = "pending"
    PROCESSING = "processing"
    SENT_PROMPT = "sent_prompt"
    GENERATING = "generating"
    DOWNLOAD = "download"
    COMPLETED = "completed"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"

    def is_terminal(self) -> bool:
        """Check if status is terminal (cannot transition)"""
        return self in [
            JobStatus.DONE,
            JobStatus.FAILED,
            JobStatus.CANCELLED
        ]

    def is_active(self) -> bool:
        """Check if status is active (job is running)"""
        return self in [
            JobStatus.PENDING,
            JobStatus.PROCESSING,
            JobStatus.SENT_PROMPT,
            JobStatus.GENERATING,
            JobStatus.DOWNLOAD
        ]


@dataclass(frozen=True)
class JobId:
    """
    Value Object cho Job ID
    Immutable, validated identity
    """
    value: int

    def __post_init__(self):
        if self.value < 0:  # Allow 0 for new jobs
            raise ValueError("Job ID cannot be negative")

    def __str__(self) -> str:
        return str(self.value)


@dataclass(frozen=True)
class JobSpec:
    """
    Value Object cho Job Specification
    Immutable - once created, cannot be changed

    Implements ISP: Chỉ chứa specification fields
    """
    prompt: str
    image_path: Optional[str]
    duration: int  # seconds
    aspect_ratio: str  # "16:9", "9:16", "1:1"

    def __post_init__(self):
        # Validate prompt
        if not self.prompt or not self.prompt.strip():
            raise ValueError("Prompt cannot be empty")

        # Validate duration
        if self.duration not in [5, 10, 15]:
            raise ValueError("Duration must be 5, 10, or 15 seconds")

        # Validate aspect ratio
        valid_ratios = ["16:9", "9:16", "1:1"]
        if self.aspect_ratio not in valid_ratios:
            raise ValueError(f"aspect_ratio must be one of {valid_ratios}")

    def get_orientation(self) -> str:
        """
        Get orientation for API calls

        Returns:
            "landscape", "portrait", or "square"
        """
        mapping = {
            "16:9": "landscape",
            "9:16": "portrait",
            "1:1": "square"
        }
        return mapping[self.aspect_ratio]

    def get_n_frames(self) -> int:
        """
        Calculate number of frames (assuming 30fps)

        Returns:
            Number of frames
        """
        return self.duration * 30


@dataclass
class JobProgress:
    """
    Value Object cho Job Progress tracking
    Mutable - can be updated as job progresses

    Implements ISP: Chỉ chứa progress fields
    """
    status: JobStatus
    progress: int  # 0-100
    error_message: Optional[str] = None
    retry_count: int = 0
    max_retries: int = 3

    def __post_init__(self):
        # Validate progress
        if not (0 <= self.progress <= 100):
            raise ValueError("Progress must be between 0 and 100")

        # Validate retry count
        if self.retry_count < 0:
            raise ValueError("retry_count cannot be negative")
        if self.max_retries < 0:
            raise ValueError("max_retries cannot be negative")

    def can_retry(self) -> bool:
        """Check if job can be retried"""
        return (
            self.status == JobStatus.FAILED
            and self.retry_count < self.max_retries
        )

    def increment_retry(self) -> 'JobProgress':
        """
        Create new JobProgress with incremented retry count

        Returns:
            New JobProgress instance
        """
        return JobProgress(
            status=JobStatus.PENDING,
            progress=0,
            error_message=None,
            retry_count=self.retry_count + 1,
            max_retries=self.max_retries
        )

    def mark_failed(self, error: str) -> 'JobProgress':
        """
        Mark job as failed

        Returns:
            New JobProgress instance
        """
        return JobProgress(
            status=JobStatus.FAILED,
            progress=self.progress,
            error_message=error,
            retry_count=self.retry_count,
            max_retries=self.max_retries
        )

    def update_progress(self, progress: int, message: Optional[str] = None) -> 'JobProgress':
        """
        Update progress percentage

        Returns:
            New JobProgress instance
        """
        return JobProgress(
            status=self.status,
            progress=progress,
            error_message=message or self.error_message,
            retry_count=self.retry_count,
            max_retries=self.max_retries
        )


@dataclass
class JobResult:
    """
    Value Object cho Job Result
    Mutable - populated as job completes

    Implements ISP: Chỉ chứa result fields
    """
    video_url: Optional[str] = None
    video_id: Optional[str] = None
    local_path: Optional[str] = None

    def is_complete(self) -> bool:
        """Check if job has complete result"""
        return self.local_path is not None

    def has_url(self) -> bool:
        """Check if job has video URL"""
        return self.video_url is not None


@dataclass
class Job:
    """
    Aggregate Root cho Job

    Manages all job concerns:
    - Specification
    - Progress
    - Result
    - Task state

    Implements:
    - SRP: Single responsibility (job management)
    - ISP: Composed from smaller value objects
    """
    id: JobId
    spec: JobSpec
    progress: JobProgress
    result: JobResult
    account_id: Optional[int] = None
    task_state: Optional[dict] = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)

    @staticmethod
    def from_orm(orm_job) -> 'Job':
        """
        Convert từ SQLAlchemy ORM model sang Domain model

        Implements Dependency Inversion: Domain không depend vào ORM
        """
        import json

        return Job(
            id=JobId(orm_job.id),
            spec=JobSpec(
                prompt=orm_job.prompt,
                image_path=orm_job.image_path,
                duration=orm_job.duration or 5,
                aspect_ratio=orm_job.aspect_ratio or "16:9"
            ),
            progress=JobProgress(
                status=JobStatus(orm_job.status),
                progress=orm_job.progress or 0,
                error_message=orm_job.error_message,
                retry_count=orm_job.retry_count or 0,
                max_retries=orm_job.max_retries or 3
            ),
            result=JobResult(
                video_url=orm_job.video_url,
                video_id=orm_job.video_id,
                local_path=orm_job.local_path
            ),
            account_id=orm_job.account_id,
            task_state=json.loads(orm_job.task_state) if orm_job.task_state else None,
            created_at=orm_job.created_at,
            updated_at=orm_job.updated_at
        )

    def to_orm_dict(self) -> dict:
        """
        Convert to dict for SQLAlchemy update

        Returns:
            Dict with ORM-compatible fields
        """
        import json

        return {
            "prompt": self.spec.prompt,
            "image_path": self.spec.image_path,
            "duration": self.spec.duration,
            "aspect_ratio": self.spec.aspect_ratio,
            "status": self.progress.status.value,
            "progress": self.progress.progress,
            "error_message": self.progress.error_message,
            "retry_count": self.progress.retry_count,
            "max_retries": self.progress.max_retries,
            "video_url": self.result.video_url,
            "video_id": self.result.video_id,
            "local_path": self.result.local_path,
            "account_id": self.account_id,
            "task_state": json.dumps(self.task_state) if self.task_state else None,
            "updated_at": datetime.utcnow()
        }

    def can_start(self) -> bool:
        """Check if job can be started"""
        return self.progress.status in [JobStatus.DRAFT, JobStatus.PENDING]

    def can_cancel(self) -> bool:
        """Check if job can be cancelled"""
        return self.progress.status.is_active()

    def can_retry(self) -> bool:
        """Check if job can be retried"""
        return self.progress.status in [JobStatus.FAILED, JobStatus.CANCELLED]

    def __str__(self) -> str:
        return f"Job(id={self.id}, status={self.progress.status.value}, progress={self.progress.progress}%)"

    def __repr__(self) -> str:
        return self.__str__()

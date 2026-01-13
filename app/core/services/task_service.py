"""
Task Service - Orchestrate job execution flow
Implements: Single Responsibility Principle (SRP)
"""
from typing import Optional, List
from ..repositories.job_repo import JobRepository
from ..repositories.account_repo import AccountRepository
from ..domain.job import Job, JobStatus
from ..task_manager import task_manager, TaskContext
import logging

logger = logging.getLogger(__name__)

class TaskService:
    """Service để orchestrate task execution"""

    def __init__(
        self,
        job_repo: JobRepository,
        account_repo: AccountRepository
    ):
        self.job_repo = job_repo
        self.account_repo = account_repo

    async def start_job(self, job_id: int) -> Job:
        """
        Start job execution

        Business rules:
        - Job must be in DRAFT or PENDING status
        - Must have available account with credits
        - Enqueue to task manager
        """
        job = await self.job_repo.get_by_id(job_id)
        if not job:
            raise ValueError(f"Job {job_id} not found")

        # Validate status
        if job.progress.status not in [JobStatus.DRAFT, JobStatus.PENDING]:
            raise ValueError(f"Cannot start job in status {job.progress.status}")

        # Check if we have available accounts
        # Note: Currently hardcoded to "sora" platform
        # Future: Add platform field to JobSpec domain model
        accounts = await self.account_repo.get_available_accounts(
            platform="sora",
            exclude_ids=[]
        )

        if not accounts:
            raise ValueError("No available accounts with credits")

        # Start job via task manager
        await task_manager.start_job(job)

        # Update job status
        job.progress.status = JobStatus.PENDING
        updated = await self.job_repo.update(job)
        self.job_repo.commit()

        return updated

    async def bulk_start_jobs(self, job_ids: List[int]) -> int:
        """Start multiple jobs"""
        count = 0
        for job_id in job_ids:
            try:
                await self.start_job(job_id)
                count += 1
            except Exception as e:
                logger.error(f"Failed to start job {job_id}: {e}")

        return count

    async def retry_job_task(self, job_id: int, task_name: str) -> Job:
        """
        Retry specific task in job (generate, poll, download)

        Business rules:
        - Reset task status to pending
        - Clear task error
        - Enqueue task
        """
        job = await self.job_repo.get_by_id(job_id)
        if not job:
            raise ValueError(f"Job {job_id} not found")

        if not job.task_state or "tasks" not in job.task_state:
            raise ValueError(f"Job {job_id} has no task state")

        if task_name not in job.task_state["tasks"]:
            raise ValueError(f"Task '{task_name}' not found in job")

        # Reset task
        job.task_state["tasks"][task_name]["status"] = "pending"
        if "last_error" in job.task_state["tasks"][task_name]:
            del job.task_state["tasks"][task_name]["last_error"]
        if "retry_count" in job.task_state["tasks"][task_name]:
            job.task_state["tasks"][task_name]["retry_count"] = 0

        job.task_state["current_task"] = task_name

        # Update job
        if job.progress.status in [JobStatus.FAILED, JobStatus.COMPLETED, JobStatus.DONE]:
            job.progress.status = JobStatus.PROCESSING
            job.progress.error_message = None

        updated = await self.job_repo.update(job)
        self.job_repo.commit()

        # Enqueue task
        task = TaskContext(
            job_id=job.id.value,
            task_type=task_name,
            input_data=self._get_task_input_data(job, task_name)
        )

        queue = getattr(task_manager, f"{task_name}_queue")
        await queue.put(task)

        return updated

    def _get_task_input_data(self, job: Job, task_name: str) -> dict:
        """Get input data for task based on task type"""
        if task_name == "generate":
            return {
                "prompt": job.spec.prompt,
                "duration": job.spec.duration,
                "account_id": job.account_id
            }
        elif task_name == "download":
            return {
                "video_url": job.result.video_url
            }
        elif task_name == "poll":
            return {
                "account_id": job.account_id,
                "poll_count": 0
            }
        else:
            return {}

"""
Generate Worker - Xử lý video generation tasks
Implements: Single Responsibility Principle (SRP)
"""
import asyncio
import logging
from typing import Optional
from .base import BaseWorker
from ..repositories.job_repo import JobRepository
from ..repositories.account_repo import AccountRepository
from ..drivers.factory import DriverFactory
from ..task_manager import task_manager, TaskContext
from ..domain.job import JobStatus

logger = logging.getLogger(__name__)

class GenerateWorker(BaseWorker):
    """Worker xử lý generate tasks"""

    def __init__(
        self,
        job_repo: JobRepository,
        account_repo: AccountRepository,
        driver_factory: DriverFactory,
        max_concurrent: int = 20,
        stop_event: Optional[asyncio.Event] = None
    ):
        super().__init__(max_concurrent, stop_event)
        self.job_repo = job_repo
        self.account_repo = account_repo
        self.driver_factory = driver_factory

    def get_queue(self):
        """Get generate queue"""
        return task_manager.generate_queue

    async def process_task(self, task: TaskContext):
        """
        Process một generate task

        Steps:
        1. Get job from DB
        2. Select available account
        3. Create driver
        4. Generate video
        5. Enqueue poll task
        """
        try:
            # 1. Get job
            job = await self.job_repo.get_by_id(task.job_id)
            if not job:
                logger.error(f"Job #{task.job_id} not found")
                return

            # 2. Select account (TODO: Extract to AccountSelector strategy)
            account = await self._select_account(task)
            if not account:
                # Re-queue if no account available
                logger.warning(f"No account available for Job #{task.job_id}, re-queuing...")
                await asyncio.sleep(10)
                await task_manager.generate_queue.put(task)
                return

            # 3. Create driver
            driver = self.driver_factory.create_driver(
                platform=account.platform,
                access_token=account.session.access_token,
                device_id=account.session.device_id,
                user_agent=account.session.user_agent,
                headless=True  # Ensure headless mode
            )

            try:
                # Start driver
                await driver.start()

                # 4. Generate video
                logger.info(f"[GENERATE] Job #{job.id.value} with Account #{account.id.value}")

                # Update job status
                job.progress.status = JobStatus.PROCESSING
                await self.job_repo.update(job)
                self.job_repo.commit()

                # Call driver
                result = await driver.generate_video(
                    prompt=job.spec.prompt,
                    duration=job.spec.duration,
                    aspect_ratio=job.spec.aspect_ratio,
                    image_path=job.spec.image_path
                )

                if result.success:
                    # 5. Enqueue poll task
                    logger.info(f"[OK] Job #{job.id.value} submitted! Task ID: {result.task_id}")

                    job.progress.status = JobStatus.GENERATING
                    job.task_state = {
                        "tasks": {
                            "generate": {
                                "status": "completed",
                                "task_id": result.task_id
                            },
                            "poll": {"status": "pending"}
                        },
                        "current_task": "poll"
                    }
                    await self.job_repo.update(job)
                    self.job_repo.commit()

                    # Enqueue poll
                    poll_task = TaskContext(
                        job_id=job.id.value,
                        task_type="poll",
                        input_data={
                            "task_id": result.task_id,
                            "account_id": account.id.value
                        }
                    )
                    await task_manager.poll_queue.put(poll_task)
                else:
                    # Generation failed
                    logger.error(f"[ERROR] Job #{job.id.value} failed: {result.error}")
                    job.progress.status = JobStatus.FAILED
                    job.progress.error_message = result.error
                    await self.job_repo.update(job)
                    self.job_repo.commit()

            finally:
                await driver.stop()

        except Exception as e:
            logger.error(f"[ERROR] Generate task failed for Job #{task.job_id}: {e}", exc_info=True)
            # Note: Retry logic handled by task_manager via max_retries in JobProgress

    async def _select_account(self, task: TaskContext):
        """
        Select available account

        Future improvement: Extract to AccountSelector strategy class
        to follow Open/Closed Principle and support multiple selection strategies
        """
        exclude_ids = task.input_data.get("exclude_account_ids", [])
        accounts = await self.account_repo.get_available_accounts(
            platform="sora",
            exclude_ids=exclude_ids
        )

        if not accounts:
            return None

        # Sort by last_used (LRU)
        from datetime import datetime
        accounts_sorted = sorted(
            accounts,
            key=lambda a: a.last_used or datetime.min
        )

        return accounts_sorted[0]

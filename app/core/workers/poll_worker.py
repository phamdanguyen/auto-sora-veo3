"""
Poll Worker - Poll video generation completion
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

class PollWorker(BaseWorker):
    """Worker để poll video completion"""

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
        """Get poll queue"""
        return task_manager.poll_queue

    async def process_task(self, task: TaskContext):
        """
        Poll video completion

        Steps:
        1. Get job from DB
        2. Get account and create driver
        3. Check if video ready
        4. If ready: enqueue download
        5. If not: re-queue poll with delay
        """
        try:
            # 1. Get job
            job = await self.job_repo.get_by_id(task.job_id)
            if not job:
                logger.error(f"Job #{task.job_id} not found")
                return

            # Extract task_id
            task_id = task.input_data.get("task_id")
            if not task_id:
                logger.error(f"Job #{job.id.value} missing task_id")
                return

            # 2. Get account and create driver
            account_id = task.input_data.get("account_id")
            if not account_id:
                logger.error(f"Job #{job.id.value} missing account_id")
                return

            account = await self.account_repo.get_by_id(account_id)
            if not account:
                logger.error(f"Account #{account_id} not found")
                return

            # Create API-only driver
            driver = self.driver_factory.create_driver(
                platform=account.platform,
                access_token=account.session.access_token,
                device_id=account.session.device_id,
                user_agent=account.session.user_agent
            )

            try:
                # Start driver
                await driver.start()

                # 3. Check completion
                logger.info(f"[POLL] Job #{job.id.value} checking task {task_id}...")

                video_data = await driver.wait_for_completion(
                    task_id=task_id,
                    timeout=10  # Short timeout per poll
                )

                if video_data:
                    # 4. Video ready! Enqueue download
                    logger.info(f"[OK] Job #{job.id.value} video ready!")

                    job.progress.status = JobStatus.DOWNLOAD
                    job.result.video_url = video_data.download_url
                    job.result.video_id = video_data.id

                    # Update task_state
                    if job.task_state:
                        job.task_state["tasks"]["poll"] = {"status": "completed"}
                        job.task_state["tasks"]["download"] = {"status": "pending"}
                        job.task_state["current_task"] = "download"

                    await self.job_repo.update(job)
                    self.job_repo.commit()

                    # Enqueue download
                    dl_task = TaskContext(
                        job_id=job.id.value,
                        task_type="download",
                        input_data={
                            "video_url": video_data.download_url,
                            "video_id": video_data.id
                        }
                    )
                    await task_manager.download_queue.put(dl_task)
                else:
                    # 5. Not ready, re-queue
                    logger.info(f"[WAIT] Job #{job.id.value} still generating...")
                    await asyncio.sleep(15)
                    await task_manager.poll_queue.put(task)

            finally:
                await driver.stop()

        except Exception as e:
            logger.error(f"[ERROR] Poll task failed for Job #{task.job_id}: {e}", exc_info=True)
            # Note: Retry logic handled by task_manager via max_retries in JobProgress

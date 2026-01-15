"""
Poll Worker - Xử lý video polling tasks
Implements: Single Responsibility Principle (SRP)
"""
import asyncio
import logging
import uuid
import random
import dataclasses
from .base import BaseWorker
from ..repositories.job_repo import JobRepository
from ..repositories.account_repo import AccountRepository
from ..drivers.factory import DriverFactory
from ..task_manager import task_manager, TaskContext
from ..domain.job import JobStatus
from ...database import SessionLocal

logger = logging.getLogger(__name__)

# Max polls before giving up
MAX_POLL_COUNT = 60  # 60 polls * ~20s = ~20 minutes max

class PollWorker(BaseWorker):
    """Worker để poll video completion"""

    def __init__(
        self,
        job_repo: JobRepository,
        account_repo: AccountRepository,
        driver_factory: DriverFactory,
        max_concurrent: int = 20,
        stop_event: asyncio.Event = None
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
        Process một poll task

        Steps:
        1. Get job & task_id
        2. Create driver with account credentials
        3. Check completion & Progress
        4. If ready: enqueue download
        5. If not: re-queue poll with delay
        """
        session = SessionLocal()
        job = None

        try:
            # Create fresh repositories for this task
            job_repo = JobRepository(session)
            account_repo = AccountRepository(session)

            # 1. Get job
            job = await job_repo.get_by_id(task.job_id)
            if not job:
                logger.error(f"Job #{task.job_id} not found")
                return

            # Extract task_id
            task_id = task.input_data.get("task_id")
            if not task_id:
                logger.error(f"Job #{job.id.value} missing task_id")
                # Mark job as failed
                job.progress.status = JobStatus.FAILED
                job.progress.error_message = "Missing task_id for polling"
                await job_repo.update(job)
                job_repo.commit()
                return

            # Check poll count to avoid infinite loop
            poll_count = task.input_data.get("poll_count", 0)
            if poll_count >= MAX_POLL_COUNT:
                logger.error(f"Job #{job.id.value} exceeded max poll count ({MAX_POLL_COUNT})")
                job.progress.status = JobStatus.FAILED
                job.progress.error_message = f"Video generation timeout after {MAX_POLL_COUNT} polls (~20 minutes)"
                await job_repo.update(job)
                job_repo.commit()
                return

            # 2. Get account and create driver
            account_id = task.input_data.get("account_id")
            if not account_id:
                logger.error(f"Job #{job.id.value} missing account_id")
                job.progress.status = JobStatus.FAILED
                job.progress.error_message = "Missing account_id for polling"
                await job_repo.update(job)
                job_repo.commit()
                return

            account = await account_repo.get_by_id(account_id)
            if not account:
                logger.error(f"Account #{account_id} not found")
                job.progress.status = JobStatus.FAILED
                job.progress.error_message = f"Account #{account_id} not found"
                await job_repo.update(job)
                job_repo.commit()
                return

            # Ensure Device ID exists (Sync with GenerateWorker)
            if not account.session.device_id:
                new_device_id = str(uuid.uuid4())
                account.session = dataclasses.replace(account.session, device_id=new_device_id)
                await account_repo.update(account)
                account_repo.commit()
                logger.info(f"Generated new Device ID for Account #{account.id.value}: {account.session.device_id}")

            # Create API-only driver
            driver = self.driver_factory.create_driver(
                platform=account.platform,
                access_token=account.session.access_token,
                device_id=account.session.device_id,
                user_agent=account.session.user_agent,
                api_mode=True,
                account_email=account.email
            )

            try:
                # Start driver
                await driver.start()

                # 3. Check completion & Progress
                logger.info(f"[POLL] Job #{job.id.value} checking task {task_id}... (poll #{poll_count + 1}/{MAX_POLL_COUNT})")

                # 3a. Explicitly Update Progress (Restore Progress Bar)
                try:
                    pending_tasks = await driver.get_pending_tasks()
                    logger.debug(f"[DEBUG] Got {len(pending_tasks) if pending_tasks else 0} pending tasks")
                    if pending_tasks:
                        for p_task in pending_tasks:
                            # Fuzzy or Exact match
                            match = False
                            if p_task.id == task_id:
                                match = True
                                logger.debug(f"[DEBUG] Matched task by ID: {task_id}")
                            elif not task_id and job.spec.prompt in (getattr(p_task, 'prompt', '') or ''):
                                match = True
                                logger.debug(f"[DEBUG] Matched task by prompt")

                            if match:
                                pct = int((p_task.progress_pct or 0) * 100)
                                current_pct = job.progress.progress if job.progress.progress is not None else -1
                                logger.debug(f"[DEBUG] Progress: current={current_pct}, new={pct}")

                                # Always update and log on first poll, or when progress changes
                                if current_pct < 0 or pct != current_pct:
                                    job.progress.progress = pct
                                    await job_repo.update(job)
                                    job_repo.commit()
                                    logger.info(f"[PROGRESS] Job #{job.id.value}: {pct}%")
                                else:
                                    logger.debug(f"[DEBUG] Progress unchanged, skipping update")
                                break
                    else:
                        # Task moved out of pending queue (processing)
                        # Set a default "processing" progress if not set yet
                        if job.progress.progress is None or job.progress.progress == 0:
                            job.progress.progress = 10  # Show some progress
                            await job_repo.update(job)
                            job_repo.commit()
                            logger.info(f"[PROGRESS] Job #{job.id.value}: Processing (10%)")
                except Exception as e:
                    logger.warning(f"[POLL] Failed to update progress: {e}")

                video_data = await driver.wait_for_completion(
                    task_id=task_id,
                    timeout=30  # Increased timeout to handle API lag between pending→drafts
                )

                if video_data:
                    # CRITICAL BUG FIX: Check if video actually succeeded or failed
                    if video_data.status == "failed" or not video_data.download_url:
                        # Video generation failed - mark job as FAILED, not DOWNLOAD
                        # Use detailed error if available
                        error_detail = video_data.error or video_data.status
                        error_msg = f"Video generation failed: {error_detail}"
                        logger.error(f"[FAILED] Job #{job.id.value}: {error_msg}")
                        
                        job.progress.status = JobStatus.FAILED
                        job.progress.error_message = error_msg
                        
                        # Update task_state
                        if not job.task_state:
                            job.task_state = {}
                        if "tasks" not in job.task_state:
                            job.task_state["tasks"] = {}
                        job.task_state["tasks"]["poll"] = {"status": "failed", "error": error_msg}
                        job.task_state["current_task"] = None
                        
                        await job_repo.update(job)
                        job_repo.commit()
                        return  # Don't enqueue download!
                    
                    # 4. Video ready! Enqueue download
                    logger.info(f"[OK] Job #{job.id.value} video ready!")

                    job.progress.status = JobStatus.DOWNLOAD
                    job.progress.progress = 100
                    job.result.video_url = video_data.download_url
                    job.result.video_id = video_data.id
                    job.result.generation_id = video_data.generation_id

                    # Update task_state - preserve existing data
                    if not job.task_state:
                         job.task_state = {}
                    if "tasks" not in job.task_state:
                        job.task_state["tasks"] = {}

                    job.task_state["tasks"]["poll"] = {"status": "completed"}
                    job.task_state["tasks"]["download"] = {"status": "pending"}
                    job.task_state["current_task"] = "download"

                    await job_repo.update(job)
                    job_repo.commit()

                    # Enqueue download
                    dl_task = TaskContext(
                        job_id=job.id.value,
                        task_type="download",
                        input_data={
                            "video_url": video_data.download_url,
                            "video_id": video_data.id,
                            "generation_id": video_data.generation_id
                        }
                    )
                    await task_manager.download_queue.put(dl_task)
                else:
                    # 5. Not ready, re-queue with incremented poll count
                    logger.info(f"[WAIT] Job #{job.id.value} still generating... (poll #{poll_count + 1}/{MAX_POLL_COUNT})")

                    # Increment poll count
                    task.input_data["poll_count"] = poll_count + 1

                    # Random sleep to avoid rate-limits
                    sleep_time = random.randint(15, 30)
                    logger.info(f"[POLL] Sleeping {sleep_time}s to avoid rate-limits...")
                    await asyncio.sleep(sleep_time)
                    await task_manager.poll_queue.put(task)

            finally:
                await driver.stop()

        except Exception as e:
            logger.error(f"[ERROR] Poll task failed for Job #{task.job_id}: {e}", exc_info=True)

            # Mark job as failed if we have it
            if job:
                try:
                    job.progress.status = JobStatus.FAILED
                    job.progress.error_message = f"Poll error: {str(e)}"
                    await job_repo.update(job)
                    job_repo.commit()
                except Exception as update_error:
                    logger.error(f"Failed to update job status after error: {update_error}")
        finally:
            session.close()

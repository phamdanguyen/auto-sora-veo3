"""
Generate Worker - Xử lý video generation tasks
Implements: Single Responsibility Principle (SRP)
"""
import asyncio
import logging
import uuid
import dataclasses
from datetime import datetime
from typing import Optional
from .base import BaseWorker
from ..repositories.job_repo import JobRepository
from ..repositories.account_repo import AccountRepository
from ..drivers.factory import DriverFactory
from ..task_manager import task_manager, TaskContext
from ..domain.job import JobStatus

logger = logging.getLogger(__name__)

# Max retries for re-queue scenarios
MAX_RETRY_COUNT = 5

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
        job = None
        driver = None

        try:
            # 1. Get job
            job = await self.job_repo.get_by_id(task.job_id)
            if not job:
                logger.error(f"Job #{task.job_id} not found")
                return

            # 2. Select account
            account = await self._select_account(task)
            if not account:
                # Re-queue if no account available
                retry_count = task.input_data.get("no_account_retry_count", 0)
                if retry_count >= 3:
                    logger.error(f"Job #{task.job_id} exceeded max retries (no account available)")
                    job.progress.status = JobStatus.FAILED
                    job.progress.error_message = "No available accounts after 3 retries"
                    await self.job_repo.update(job)
                    self.job_repo.commit()
                    self._remove_from_active_set(task.job_id)
                    return

                logger.warning(f"No account available for Job #{task.job_id}, re-queuing... (retry {retry_count + 1}/3)")
                task.input_data["no_account_retry_count"] = retry_count + 1
                await asyncio.sleep(10)
                await task_manager.generate_queue.put(task)
                return

            # 2a. Ensure Device ID exists (Critical for API consistency)
            if not account.session.device_id:
                new_device_id = str(uuid.uuid4())
                account.session = dataclasses.replace(account.session, device_id=new_device_id)
                await self.account_repo.update(account)
                self.account_repo.commit()
                logger.info(f"Generated new Device ID for Account #{account.id.value}: {account.session.device_id}")

            # 3. Create driver
            driver = self.driver_factory.create_driver(
                platform=account.platform,
                access_token=account.session.access_token,
                device_id=account.session.device_id,
                user_agent=account.session.user_agent,
                headless=True,
                api_mode=True, # [REVERTED] Use API Driver (curl_cffi) - faster and no Cloudflare issues
                account_email=account.email
            )

            try:
                # Start driver
                await driver.start()

                # 4. Generate video
                logger.info(f"[GENERATE] Job #{job.id.value} with Account #{account.id.value}")

                # Update job status to PROCESSING (single update before driver call)
                job.progress.status = JobStatus.PROCESSING
                job.account_id = account.id.value
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
                    # 5. Success - update task_state and enqueue poll
                    logger.info(f"[OK] Job #{job.id.value} submitted! Task ID: {result.task_id}")

                    # Update status to GENERATING
                    job.progress.status = JobStatus.GENERATING

                    # Update task_state - DO NOT OVERWRITE, UPDATE existing state
                    if not job.task_state:
                        job.task_state = {}
                    if "tasks" not in job.task_state:
                        job.task_state["tasks"] = {}

                    # Update generate task status (preserve existing fields like credits info)
                    if "generate" in job.task_state.get("tasks", {}):
                        # Update existing generate task
                        job.task_state["tasks"]["generate"].update({
                            "status": "completed",
                            "task_id": result.task_id,
                            "completed_at": datetime.now().isoformat()
                        })
                    else:
                        # Create new generate task entry
                        job.task_state["tasks"]["generate"] = {
                            "status": "completed",
                            "task_id": result.task_id,
                            "completed_at": datetime.now().isoformat()
                        }

                    # Init poll task
                    job.task_state["tasks"]["poll"] = {"status": "pending"}
                    job.task_state["current_task"] = "poll"

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

                    # Remove from active set on success
                    self._remove_from_active_set(task.job_id)

                else:
                    # Handle failures
                    error_msg = result.error or "Unknown error"
                    logger.warning(f"[WARNING] Job #{job.id.value} failed with error: {error_msg}")

                    # Check for retryable errors with limit - use parsed error_code
                    error_code = getattr(result, 'error_code', None)
                    
                    if error_code == "heavy_load" or "heavy_load" in str(error_msg):
                        retry_count = task.input_data.get("heavy_load_retry_count", 0)
                        if retry_count >= MAX_RETRY_COUNT:
                            logger.error(f"Job #{job.id.value} exceeded max retries (heavy_load)")
                            job.progress.status = JobStatus.FAILED
                            job.progress.error_message = f"Max retries exceeded: {error_msg}"
                            await self.job_repo.update(job)
                            self.job_repo.commit()
                            self._remove_from_active_set(task.job_id)
                            return

                        logger.warning(f"⚠️ Sora Heavy Load detected. Re-queuing Job #{job.id.value} in 15 seconds... (retry {retry_count + 1}/{MAX_RETRY_COUNT})")
                        task.input_data["heavy_load_retry_count"] = retry_count + 1
                        await asyncio.sleep(15)
                        await task_manager.generate_queue.put(task)
                        return

                    if error_code == "too_many_concurrent_tasks":
                        retry_count = task.input_data.get("concurrent_retry_count", 0)
                        if retry_count >= MAX_RETRY_COUNT:
                            logger.error(f"Job #{job.id.value} exceeded max retries (too_many_concurrent)")
                            job.progress.status = JobStatus.FAILED
                            job.progress.error_message = f"Max retries exceeded: {error_msg}"
                            await self.job_repo.update(job)
                            self.job_repo.commit()
                            self._remove_from_active_set(task.job_id)
                            return

                        logger.warning(f"⚠️ Account #{account.id.value} maxed out (3 concurrent). Switching account... (retry {retry_count + 1}/{MAX_RETRY_COUNT})")

                        # Exclude this account for this attempt
                        exclude_ids = task.input_data.get("exclude_account_ids", [])
                        if account.id.value not in exclude_ids:
                            exclude_ids.append(account.id.value)
                        task.input_data["exclude_account_ids"] = exclude_ids
                        task.input_data["concurrent_retry_count"] = retry_count + 1

                        await asyncio.sleep(5)
                        await task_manager.generate_queue.put(task)
                        return

                    # Check for Account-level errors
                    account_invalid = False
                    status_reason = "error"

                    if "phone_number_required" in str(error_msg) or "phone_number_required" in str(getattr(result, 'error_code', '')):
                        account_invalid = True
                        status_reason = "phone_required"
                    elif "quota" in str(error_msg).lower() or "credit" in str(error_msg).lower():
                        account_invalid = True
                        status_reason = "no_credits"
                    elif "unauthorized" in str(error_msg).lower() or "token" in str(error_msg).lower():
                        account_invalid = True
                        status_reason = "expired"

                    if account_invalid:
                        retry_count = task.input_data.get("account_switch_retry_count", 0)
                        if retry_count >= MAX_RETRY_COUNT:
                            logger.error(f"Job #{job.id.value} exceeded max retries (account switching)")
                            job.progress.status = JobStatus.FAILED
                            job.progress.error_message = f"Max retries exceeded: {error_msg}"
                            await self.job_repo.update(job)
                            self.job_repo.commit()
                            self._remove_from_active_set(task.job_id)
                            return

                        logger.warning(f"⚠️ Account #{account.id.value} encountered error ({status_reason}). Switching account... (retry {retry_count + 1}/{MAX_RETRY_COUNT})")

                        # Exclude this account
                        exclude_ids = task.input_data.get("exclude_account_ids", [])
                        if account.id.value not in exclude_ids:
                            exclude_ids.append(account.id.value)
                        task.input_data["exclude_account_ids"] = exclude_ids
                        task.input_data["account_switch_retry_count"] = retry_count + 1

                        # Reset job status for retry
                        job.progress.status = JobStatus.PENDING
                        await self.job_repo.update(job)
                        self.job_repo.commit()

                        await task_manager.generate_queue.put(task)
                        return

                    # Generic retry logic for transient errors (network, server errors, etc.)
                    # This handles all other errors that are not specific retryable cases above
                    api_retry_count = task.input_data.get("api_retry_count", 0)
                    if api_retry_count < 3:
                        logger.warning(f"⚠️ Job #{job.id.value} API error, retrying... (attempt {api_retry_count + 1}/3): {error_msg}")
                        task.input_data["api_retry_count"] = api_retry_count + 1
                        await asyncio.sleep(10)  # Wait before retry
                        await task_manager.generate_queue.put(task)
                        return

                    # If not retryable error after all retries, fail job permanently
                    logger.error(f"[ERROR] Job #{job.id.value} failed permanently after 3 API retries: {result.error}")
                    job.progress.status = JobStatus.FAILED
                    job.progress.error_message = f"API failed after 3 retries: {result.error}"
                    await self.job_repo.update(job)
                    self.job_repo.commit()
                    self._remove_from_active_set(task.job_id)

            finally:
                if driver:
                    await driver.stop()

        except Exception as e:
            logger.error(f"[ERROR] Generate task failed for Job #{task.job_id}: {e}", exc_info=True)

            # Cleanup: Mark job as failed if we have it
            if job:
                try:
                    job.progress.status = JobStatus.FAILED
                    job.progress.error_message = f"Internal error: {str(e)}"
                    await self.job_repo.update(job)
                    self.job_repo.commit()
                except Exception as update_error:
                    logger.error(f"Failed to update job status after error: {update_error}")

            # Always remove from active set
            self._remove_from_active_set(task.job_id)

    def _remove_from_active_set(self, job_id: int):
        """Remove job from active set if exists"""
        try:
            if hasattr(task_manager, '_active_job_ids'):
                task_manager._active_job_ids.discard(job_id)
        except Exception as e:
            logger.warning(f"Failed to remove job {job_id} from active set: {e}")

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

        # Sort by last_used (LRU) - Randomize top 3 to avoid race conditions
        from datetime import datetime
        import random
        accounts_sorted = sorted(
            accounts,
            key=lambda a: a.last_used or datetime.min
        )

        # Pick random from top 3 to reduce race conditions when parallel workers pick accounts
        candidate_pool = accounts_sorted[:3]
        selected = random.choice(candidate_pool)

        return selected

"""
Worker Manager - Orchestrate multiple workers
"""
import asyncio
import logging
from typing import List, Optional
from .generate_worker import GenerateWorker
from .poll_worker import PollWorker
from .download_worker import DownloadWorker
from ..repositories.job_repo import JobRepository
from ..repositories.account_repo import AccountRepository
from ..drivers.factory import DriverFactory

logger = logging.getLogger(__name__)

class WorkerManager:
    """Manager để start/stop tất cả workers"""

    def __init__(
        self,
        job_repo: JobRepository,
        account_repo: AccountRepository,
        driver_factory: DriverFactory
    ):
        self.job_repo = job_repo
        self.account_repo = account_repo
        self.driver_factory = driver_factory

        self.stop_event = asyncio.Event()

        # Create workers
        self.generate_worker = GenerateWorker(
            job_repo=job_repo,
            account_repo=account_repo,
            driver_factory=driver_factory,
            max_concurrent=20,
            stop_event=self.stop_event
        )

        self.poll_worker = PollWorker(
            job_repo=job_repo,
            account_repo=account_repo,
            driver_factory=driver_factory,
            max_concurrent=20,
            stop_event=self.stop_event
        )

        self.download_worker = DownloadWorker(
            job_repo=job_repo,
            max_concurrent=5,
            stop_event=self.stop_event
        )

        self._tasks: List[asyncio.Task] = []

    async def start_all(self):
        """Start all workers"""
        logger.info("[WORKER MANAGER] Starting all workers...")

        self.stop_event.clear()

        # Start each worker in background task
        self._tasks = [
            asyncio.create_task(self.generate_worker.start(), name="generate_worker"),
            asyncio.create_task(self.poll_worker.start(), name="poll_worker"),
            asyncio.create_task(self.download_worker.start(), name="download_worker")
        ]

        logger.info("[WORKER MANAGER] All workers started")

    async def stop_all(self):
        """Stop all workers"""
        logger.info("[WORKER MANAGER] Stopping all workers...")

        # Signal stop
        self.stop_event.set()

        # Stop each worker
        await asyncio.gather(
            self.generate_worker.stop(),
            self.poll_worker.stop(),
            self.download_worker.stop(),
            return_exceptions=True
        )

        # Cancel background tasks
        for task in self._tasks:
            if not task.done():
                task.cancel()

        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()

        logger.info("[WORKER MANAGER] All workers stopped")


# Global worker manager (sẽ init trong main.py)
worker_manager: Optional[WorkerManager] = None

def init_worker_manager(
    job_repo: JobRepository,
    account_repo: AccountRepository,
    driver_factory: DriverFactory
) -> WorkerManager:
    """Initialize global worker manager"""
    global worker_manager
    worker_manager = WorkerManager(job_repo, account_repo, driver_factory)
    return worker_manager


def get_worker_manager() -> Optional[WorkerManager]:
    """Get global worker manager"""
    return worker_manager

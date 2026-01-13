"""
Download Worker - Download completed videos
Implements: Single Responsibility Principle (SRP)
"""
import asyncio
import logging
import os
from typing import Optional
from .base import BaseWorker
from ..repositories.job_repo import JobRepository
from ..task_manager import task_manager, TaskContext
from ..domain.job import JobStatus
import aiohttp

logger = logging.getLogger(__name__)

class DownloadWorker(BaseWorker):
    """Worker để download videos"""

    def __init__(
        self,
        job_repo: JobRepository,
        max_concurrent: int = 5,
        stop_event: Optional[asyncio.Event] = None
    ):
        super().__init__(max_concurrent, stop_event)
        self.job_repo = job_repo

    def get_queue(self):
        """Get download queue"""
        return task_manager.download_queue

    async def process_task(self, task: TaskContext):
        """
        Download video

        Steps:
        1. Get job from DB
        2. Download video file
        3. Verify file
        4. Update job as completed
        """
        try:
            # 1. Get job
            job = await self.job_repo.get_by_id(task.job_id)
            if not job:
                logger.error(f"Job #{task.job_id} not found")
                return

            download_url = task.input_data.get("video_url")
            if not download_url:
                logger.error(f"Job #{job.id.value} missing download_url")
                return

            # 2. Download video
            logger.info(f"[DOWNLOAD] Job #{job.id.value} from {download_url}")

            download_dir = "data/downloads"
            os.makedirs(download_dir, exist_ok=True)

            filename = f"{download_dir}/sora_{job.id.value}_{job.result.video_id}.mp4"

            async with aiohttp.ClientSession() as session:
                async with session.get(download_url) as response:
                    if response.status == 200:
                        total_size = 0
                        with open(filename, 'wb') as f:
                            async for chunk in response.content.iter_chunked(8192):
                                f.write(chunk)
                                total_size += len(chunk)

                        # 3. Verify file
                        if total_size < 10000:
                            raise Exception(f"File too small: {total_size} bytes")

                        # 4. Update job
                        logger.info(f"[OK] Downloaded {filename} ({total_size:,} bytes)")

                        job.progress.status = JobStatus.DONE
                        job.progress.progress = 100
                        job.result.local_path = f"/downloads/{os.path.basename(filename)}"

                        # Update task_state
                        if job.task_state:
                            job.task_state["tasks"]["download"] = {"status": "completed"}
                            job.task_state["current_task"] = "completed"

                        await self.job_repo.update(job)
                        self.job_repo.commit()
                    else:
                        raise Exception(f"HTTP {response.status}")

        except Exception as e:
            logger.error(f"[ERROR] Download task failed for Job #{task.job_id}: {e}", exc_info=True)
            # Mark job as failed
            try:
                job = await self.job_repo.get_by_id(task.job_id)
                if job:
                    job.progress.status = JobStatus.FAILED
                    job.progress.error_message = str(e)
                    await self.job_repo.update(job)
                    self.job_repo.commit()
            except Exception as update_error:
                logger.error(f"Failed to update job status: {update_error}")

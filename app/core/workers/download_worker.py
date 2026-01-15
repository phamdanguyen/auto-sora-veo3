import asyncio
import logging
import os
import json
from typing import Optional
from .base import BaseWorker
from ..repositories.job_repo import JobRepository
from ..repositories.account_repo import AccountRepository
from ..task_manager import task_manager, TaskContext
from ..domain.job import JobStatus
from ...database import SessionLocal
import aiohttp
from ..watermark_remover import WatermarkRemover
from ..drivers.api_client import SoraApiClient
from ..sentinel import get_sentinel_token

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
        2. Attempt to remove watermark (Post -> Get Clean URL)
        3. Download video file (Clean or Original)
        4. Verify file
        5. Update job as completed
        """
        session = SessionLocal()
        job = None

        try:
            # Create fresh repository for this task
            job_repo = JobRepository(session)
            account_repo = AccountRepository(session)

            # 1. Get job
            job = await job_repo.get_by_id(task.job_id)
            if not job:
                logger.error(f"Job #{task.job_id} not found")
                return

            download_url = task.input_data.get("video_url")
            video_id = task.input_data.get("video_id") or job.result.video_id
            generation_id = task.input_data.get("generation_id") or (job.result.generation_id if job.result else None)
            
            if not download_url:
                logger.error(f"Job #{job.id.value} missing download_url")
                job.progress.status = JobStatus.FAILED
                job.progress.error_message = "Missing download_url"
                await job_repo.update(job)
                job_repo.commit()
                return

            # 2. Watermark Removal Attempt
            clean_url = None
            if video_id and job.account_id:
                try:
                    account = await account_repo.get_by_id(job.account_id)
                    if account and account.session.access_token:
                        logger.info(f"[WATERMARK] Attempting to remove watermark for Job #{job.id.value}...")
                        
                        # Prepare API Client
                        api_client = SoraApiClient(
                            access_token=account.session.access_token,
                            user_agent=account.session.user_agent or "Mozilla/5.0",
                            cookies=account.session.cookies,
                            account_email=account.email,
                            device_id=account.session.device_id
                        )
                        
                        # Get Sentinel Token
                        sentinel_token = "{}"
                        try:
                            token_data = get_sentinel_token(flow="sora_2_create_post")
                            sentinel_token = json.dumps(json.loads(token_data) if isinstance(token_data, str) else token_data)
                        except Exception as st_err:
                            logger.warning(f"[WATERMARK] Sentinel gen failed: {st_err}")
                            # Proceed? Might fail but api_client handles it? 
                            # Actually process_video needs it.
                            pass

                        # Call WatermarkRemover
                        clean_url = await WatermarkRemover.process_video(
                            video_id=video_id,
                            api_client=api_client,
                            sentinel_token=sentinel_token,
                            title=job.spec.prompt[:50] + "..." if job.spec.prompt else "Sora Video",
                            description=job.spec.prompt or "",
                            generation_id=generation_id
                        )
                        if clean_url:
                            logger.info(f"[WATERMARK] Success! Switching download to clean URL.")
                            download_url = clean_url
                        else:
                            logger.warning(f"[WATERMARK] Failed to get clean URL. Fallback to original.")
                    
                except Exception as wm_e:
                    logger.warning(f"[WATERMARK] Error during removal process: {wm_e}")
                    # Continue with original URL

            # 3. Download video
            logger.info(f"[DOWNLOAD] Job #{job.id.value} from {download_url}")

            download_dir = "data/downloads"
            os.makedirs(download_dir, exist_ok=True)

            filename = f"{download_dir}/sora_{job.id.value}_{video_id or 'unknown'}.mp4"

            async with aiohttp.ClientSession() as http_session:
                async with http_session.get(download_url) as response:
                    if response.status == 200:
                        total_size = 0
                        with open(filename, 'wb') as f:
                            async for chunk in response.content.iter_chunked(8192):
                                f.write(chunk)
                                total_size += len(chunk)

                        # 4. Verify file
                        if total_size < 10000:
                            raise Exception(f"File too small: {total_size} bytes")

                        # 5. Update job
                        logger.info(f"[OK] Downloaded {filename} ({total_size:,} bytes)")

                        job.progress.status = JobStatus.DONE
                        job.progress.progress = 100
                        job.result.local_path = f"/downloads/{os.path.basename(filename)}"

                        # Update task_state - preserve existing data
                        if not job.task_state:
                            job.task_state = {}
                        if "tasks" not in job.task_state:
                            job.task_state["tasks"] = {}

                        job.task_state["tasks"]["download"] = {"status": "completed"}
                        job.task_state["current_task"] = "completed"
                        
                        # Record if clean
                        if clean_url:
                             job.task_state["is_clean_video"] = True

                        await job_repo.update(job)
                        job_repo.commit()
                    else:
                        raise Exception(f"HTTP {response.status}")

        except Exception as e:
            logger.error(f"[ERROR] Download task failed for Job #{task.job_id}: {e}", exc_info=True)

            # Mark job as failed if we have it
            if job:
                try:
                    job.progress.status = JobStatus.FAILED
                    job.progress.error_message = f"Download error: {str(e)}"
                    await job_repo.update(job)
                    job_repo.commit()
                except Exception as update_error:
                    logger.error(f"Failed to update job status after error: {update_error}")
        finally:
            session.close()


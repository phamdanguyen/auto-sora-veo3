import asyncio
import logging
import os
import sys
import unittest
from unittest.mock import MagicMock, patch, AsyncMock
from datetime import datetime

# Adjust path to include the root directory so 'app' can be imported
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

from app import models, database
from app.core.task_manager import task_manager, TaskContext
from app.core.worker_v2 import (
    process_single_generate_task,
    process_single_poll_task,
    process_single_download_task,
)

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("IntegrationTest")

class TestFullFlow(unittest.TestCase):
    def setUp(self):
        # Setup in-memory DB or simple session mock
        self.db = MagicMock()
        
        # Mock Job
        self.job = models.Job(
            id=999,
            prompt="A cyberpunk cat walking in Tokyo rain",
            duration="5s",
            status="pending",
            account_id=1,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            task_state=None
        )
        
        # Mock Account
        self.account = models.Account(
            id=1,
            email="test@sora.com",
            password="encrypted_pass",
            status="live",
            proxy=None,
            cookies={}
        )

        # Mock DB queries
        self.db.query.return_value.filter.return_value.first.side_effect = self._db_query_side_effect
    
    def _db_query_side_effect(self, *args, **kwargs):
        # Simple side effect to return job or account
        # We need to trace which query called me, but for now simple heuristic
        # If we are mocking the `filter` result:
        return self.job # Defaults to returning job, logic inside distinct mocks handled via context

    async def test_full_lifecycle(self):
        logger.info("🎬 STARTING FULL INTEGRATION TEST 🎬")

        # ==================================================================================
        # PHASE 1: GENERATE
        # ==================================================================================
        logger.info("\n--- PHASE 1: GENERATE ---")
        
        # 1. Start Job via Task Manager
        # We mock validate_job_status_transition to avoid DB validation logic during test
        task_manager._validate_job_status_transition = MagicMock(return_value=True)
        await task_manager.start_job(self.job)
        
        self.assertEqual(self.job.status, "processing")
        self.assertEqual(task_manager.generate_queue.qsize(), 1)
        logger.info("✅ Job started and added to Generate Queue.")

        # 2. Process Generate Task
        task = await task_manager.generate_queue.get()
        
        # MOCK SORA DRIVER for Generation
        with patch("app.core.worker_v2.SoraDriver") as MockDriver, \
             patch("app.core.worker_v2.database.SessionLocal", return_value=self.db), \
             patch("app.core.worker_v2.decrypt_password", return_value="password"), \
             patch("app.core.worker_v2.account_manager") as mock_am:
             
            # Configure Account Manager Mocks to be Awaitable
            mock_am.get_free_account = AsyncMock(return_value=self.account)
            mock_am.mark_account_busy = AsyncMock()
            mock_am.mark_account_free = AsyncMock()
            
            # Configure Mock Driver
            driver_instance = MockDriver.return_value
            driver_instance.login = AsyncMock()
            driver_instance.stop = AsyncMock()
            
            # Simulate Successful Submission
            driver_instance.submit_video = AsyncMock(return_value={
                "submitted": True,
                "credits_before": 10,
                "credits_after": 9
            })
            
            # Configure Account Query
            # We need precise control over DB queries in worker
            self.db.query.return_value.filter.return_value.first.side_effect = [self.job, self.account]

            logger.info("Running Generate Worker...")
            await process_single_generate_task(task)
            
            # Assertions
            self.assertEqual(task_manager.poll_queue.qsize(), 1)
            logger.info("✅ Generate Task Completed. Job moved to Poll Queue.")

        # ==================================================================================
        # PHASE 2: POLL
        # ==================================================================================
        logger.info("\n--- PHASE 2: POLL ---")
        
        poll_task = await task_manager.poll_queue.get()
        
        # MOCK SORA DRIVER for Polling
        with patch("app.core.worker_v2.SoraDriver") as MockDriver, \
             patch("app.core.worker_v2.database.SessionLocal", return_value=self.db), \
             patch("app.core.worker_v2.decrypt_password", return_value="password"):
             
            driver_instance = MockDriver.return_value
            driver_instance.login = AsyncMock()
            driver_instance.stop = AsyncMock()
            
            # Simulate "Completed" status
            driver_instance.check_video_status = AsyncMock(return_value="completed")
            
            # Simulate Public Link retrieval
            test_link = "https://sora.chatgpt.com/share/test-video-123"
            driver_instance.get_video_public_link = AsyncMock(return_value=test_link)

            # DB Queries: Job, Account
            self.db.query.return_value.filter.return_value.first.side_effect = [self.job, self.account]
            
            logger.info("Running Poll Worker...")
            await process_single_poll_task(poll_task)
            
            # Assertions
            # Should have added to Download Queue
            self.assertEqual(task_manager.download_queue.qsize(), 1)
            logger.info(f"✅ Poll Task Completed. Job moved to Download Queue with link: {test_link}")

        # ==================================================================================
        # PHASE 3: DOWNLOAD
        # ==================================================================================
        logger.info("\n--- PHASE 3: DOWNLOAD ---")
        
        dl_task = await task_manager.download_queue.get()
        
        # MOCK SORA DRIVER & DOWNLOADER
        # Need to verify it uses ThirdPartyDownloader
        with patch("app.core.worker_v2.SoraDriver") as MockDriver, \
             patch("app.core.worker_v2.database.SessionLocal", return_value=self.db), \
             patch("app.core.third_party_downloader.ThirdPartyDownloader") as MockDownloader:
             
            driver_instance = MockDriver.return_value
            driver_instance.start = AsyncMock()
            driver_instance.stop = AsyncMock()
            
            # Mock ThirdPartyDownloader
            downloader_instance = MockDownloader.return_value
            downloader_instance.download_from_public_link = AsyncMock(return_value=(
                "/abspath/to/data/downloads/video_test.mp4", 
                1024*1024
            ))

            # DB Queries: Job
            self.db.query.return_value.filter.return_value.first.side_effect = [self.job]
            
            logger.info("Running Download Worker...")
            await process_single_download_task(dl_task)
            
            # Assertions
            self.assertEqual(self.job.status, "completed")
            self.assertEqual(self.job.video_url, "https://sora.chatgpt.com/share/test-video-123")
            # worker converts abs path to web path
            self.assertEqual(self.job.local_path, "/downloads/video_test.mp4") 
            
            logger.info("✅ Download Task Completed.")
            logger.info("🎉 FULL LIFECYCLE SUCCESS!")

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    test = TestFullFlow()
    test.setUp()
    loop.run_until_complete(test.test_full_lifecycle())

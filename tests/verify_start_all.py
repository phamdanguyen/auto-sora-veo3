import asyncio
import logging
import sys
import os
import unittest
from unittest.mock import MagicMock, AsyncMock, patch

# Configure Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("VerifyStartAll")

# Adjust path to include the root directory
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

from app import models, schemas
from app.api import endpoints
from app.core.task_manager import task_manager

class TestStartAll(unittest.TestCase):
    def setUp(self):
        self.db = MagicMock()
        
    async def test_start_all_action(self):
        logger.info("🧪 Testing Start All Action...")
        
        # 1. Setup Mock Jobs
        job1 = models.Job(id=1, status="draft", prompt="Job 1")
        job2 = models.Job(id=2, status="pending", prompt="Job 2")
        job3 = models.Job(id=3, status="processing", prompt="Job 3") # Should be ignored
        
        # Mock DB Query
        # When querying for draft/pending, return job1 and job2
        self.db.query.return_value.filter.return_value.all.return_value = [job1, job2]
        
        # Mock task_manager.start_job
        task_manager.start_job = AsyncMock()
        
        # 2. Call the endpoint handler directly (bypassing FastAPI routing for unit test)
        req = endpoints.BulkActionRequest(action="start_all")
        
        await endpoints.bulk_job_action(req, self.db)
        
        # 3. Verify
        # Should have called start_job for job1 and job2
        self.assertEqual(task_manager.start_job.call_count, 2)
        
        # Verify calls
        calls = task_manager.start_job.call_args_list
        called_job_ids = [c[0][0].id for c in calls]
        self.assertIn(1, called_job_ids)
        self.assertIn(2, called_job_ids)
        self.assertNotIn(3, called_job_ids)
        
        logger.info("✅ Verified: start_job called for Draft and Pending jobs.")
        logger.info("✅ Verified: Processing job was ignored.")

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    test = TestStartAll()
    test.setUp()
    loop.run_until_complete(test.test_start_all_action())

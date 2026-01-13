
import asyncio
import logging
import sys
import os
from datetime import datetime, timedelta

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app import models  # Helper to register models
from app.core.domain.job import JobStatus
from app.core.repositories.job_repo import JobRepository
from app.core.repositories.account_repo import AccountRepository
from app.core.workers.manager import init_worker_manager
from app.core.drivers.factory import driver_factory
from app.core.drivers.base import BaseDriver
from app.core.drivers.abstractions import VideoResult, VideoData, VideoGenerationDriver

# --- 1. SETUP MOCK DRIVER ---
class MockSoraDriver(VideoGenerationDriver):
    """
    Simulates Sora interactions without browser.
    """
    def __init__(self, **kwargs):
        pass

    async def start(self) -> None:
        pass

    async def stop(self) -> None:
        pass

    async def login(self, **kwargs) -> bool:
        return True

    async def generate_video(self, prompt: str, duration: int = 5, aspect_ratio: str = "16:9", image_path: str = None) -> VideoResult:
        # Return a fake task ID
        print(f"DEBUG: MOCK generate_video called with prompt='{prompt}'")
        return VideoResult(success=True, task_id="fake_task_123")

    async def wait_for_completion(self, task_id: str, timeout: int = 300, poll_interval: int = 10) -> VideoData:
        print(f"DEBUG: MOCK wait_for_completion called for task_id={task_id}")
        return VideoData(
            id="fake_video_123",
            download_url="http://fake.url/video.mp4",
            status="completed",
            progress_pct=100
        )

    # Implement other abstract methods to satisfy ABC
    async def get_credits(self):
        from app.core.drivers.abstractions import CreditsInfo
        return CreditsInfo(credits=100)
        
    async def upload_image(self, image_path: str):
        from app.core.drivers.abstractions import UploadResult
        return UploadResult(success=True, file_id="fake_file_id")

    async def get_pending_tasks(self):
        return []

    async def save_storage_state(self, path: str):
        pass
        
    async def load_storage_state(self, path: str):
        pass


# --- 1b. Mock Download Worker ---
from app.core.workers.download_worker import DownloadWorker
from app.core.domain.job import JobStatus

class MockDownloadWorker(DownloadWorker):
    async def process_task(self, task):
        print(f"DEBUG: MockDownloadWorker processing job {task.job_id}")
        job = await self.job_repo.get_by_id(task.job_id)
        if job:
            job.progress.status = JobStatus.DONE
            job.progress.progress = 100
            job.result.local_path = "/downloads/fake_video.mp4"
            if job.task_state:
                job.task_state["tasks"]["download"] = {"status": "completed"}
                job.task_state["current_task"] = "completed"
            await self.job_repo.update(job)
            self.job_repo.commit()
            print(f">>> Mock Download Complete for Job {task.job_id}")

# --- 2. TEST SCRIPT ---
async def test_migration_flow():
    print(">>> STARTING E2E MIGRATION TEST")
    
    # A. Setup In-Memory Database
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    # B. Seed Database with Account
    account = models.Account(
        email="test@example.com",
        password="password",
        platform="sora",
        login_mode="auto",
        credits_remaining=100
    )
    session.add(account)
    session.commit()
    print(f">>> Seeded Account ID: {account.id}")

    # C. Register Mock Driver
    # Overwrite the 'sora' driver with our mock
    driver_factory.register("sora", MockSoraDriver)
    print(">>> Registered MockSoraDriver")

    # D. Initialize Components
    job_repo = JobRepository(session)
    account_repo = AccountRepository(session)
    
    # Initialize Worker Manager
    manager = init_worker_manager(job_repo, account_repo, driver_factory)
    
    # Monkey-patch DownloadWorker to avoid network calls
    manager.download_worker = MockDownloadWorker(job_repo)
    print(">>> Injected MockDownloadWorker")
    
    # E. Create a Job
    # We can use the Repo or Service. Let's use Repo directly for simplicity or JobService if convenient.
    # To properly simulate "User creates job", we insert a PENDING job.
    # Using raw model insert to mimic API reception
    job = models.Job(
        prompt="A beautiful sunset over a futuristic city",
        status="pending", # legacy status field, mapped to Domain JobStatus using repo
        created_at=datetime.utcnow()
    )
    session.add(job)
    session.commit()
    job_id = job.id
    print(f">>> Created Job ID: {job_id} [PENDING]")

    # E2. Inject Task into Queue (Simulate API)
    from app.core.task_manager import task_manager, TaskContext
    task = TaskContext(
        job_id=job_id,
        task_type="generate",
        input_data={"account_id": None} # Or allow auto-select
    )
    await task_manager.generate_queue.put(task)
    print(">>> Injected Task into Generate Queue")

    # F. Start Manager
    # This starts get_worker -> which starts processing
    await manager.start_all()
    print(">>> Worker Manager Started")

    # G. Wait for Processing
    # We poll the DB for status change
    max_retries = 10
    success = False
    
    for i in range(max_retries):
        await asyncio.sleep(2) # Wait for worker to pick up
        
        session.expire_all()
        refreshed_job = session.query(models.Job).filter_by(id=job_id).first()
        print(f"    Check {i+1}: Status = {refreshed_job.status}, Progress = {refreshed_job.progress}%")
        
        if refreshed_job.status == JobStatus.DONE.value:
            print(">>> Job Completed Successfully!")
            success = True
            break
        elif refreshed_job.status == "failed":
            print(f">>> Job Failed! Error: {refreshed_job.error_message}")
            break
            
    # H. Stop Manager
    await manager.stop_all()
    print(">>> Worker Manager Stopped")
    
    if not success:
        print(">>> TEST FAILED: Job did not complete in time.")
        sys.exit(1)
    
    # Verify Video ID
    if refreshed_job.video_id != "fake_video_123":
        print(f">>> TEST FAILED: Video ID mismatch. Got {refreshed_job.video_id}")
        sys.exit(1)

    print(">>> E2E MIGRATION TEST PASSED")

if __name__ == "__main__":
    # Configure logging to see worker output
    logging.basicConfig(level=logging.INFO)
    asyncio.run(test_migration_flow())

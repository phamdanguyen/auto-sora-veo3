
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.orm import Session
from app import models, database, schemas
import json
import datetime

def create_mock_job_for_download():
    db = database.SessionLocal()
    try:
        # Find a live account (using credits_remaining)
        account = db.query(models.Account).filter(models.Account.credits_remaining > 0).first()
        if not account:
            # Fallback to any account if no credits, just for connection test
            account = db.query(models.Account).first()
            if not account:
                print("No account found!")
                return

        print(f"Using Account #{account.id} ({account.email})")

        # Try to find existing mock job to reset
        job = db.query(models.Job).filter(models.Job.prompt == "Test Download Flow - Non Existent Video").first()
        
        if job:
             print(f"Reseting existing Mock Job #{job.id}...")
             job.status = "processing"
             job.error_message = None
             job.task_state=json.dumps({
                 "tasks": {
                     "generate": {"status": "completed"}, 
                     "download": {"status": "pending"}
                 },
                 "resolution_retries": 0
             })
             db.commit()
             db.refresh(job)
             print(f"Reset Job #{job.id} to processing.")
             return

        # Create Job
        job = models.Job(
             prompt="Test Download Flow - Watermark Removal",
             status="processing", # MUST be processing to be picked up by worker manager loop
             account_id=account.id,
             created_at=datetime.datetime.utcnow(),
             # Use a real sample video (small MP4). 
             # Note: WatermarkRemover might expect it to have a specific watermark or just process any video.
             # Ideally use one that is accessible. 
             video_url="https://filesamples.com/samples/video/mp4/sample_640x360.mp4",
             video_id="mock_video_id_123", # Add mock ID to trigger "attempt"
             task_state=json.dumps({
                 "tasks": {
                     "generate": {"status": "completed", "progress": 100},
                     "download": {"status": "pending", "progress": 0}
                 },
                 "resolution_retries": 0
             })
        )
        db.add(job)
        db.commit()
        db.refresh(job)
        print(f"Created Mock Job #{job.id}. Worker should pick it up shortly.")
        
    finally:
        db.close()

if __name__ == "__main__":
    create_mock_job_for_download()

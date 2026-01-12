
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
        # Find a live account
        account = db.query(models.Account).filter(models.Account.status == 'live').first()
        if not account:
            print("No live account found!")
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
             prompt="Test Download Flow - Non Existent Video",
             status="processing",
             account_id=account.id,
             created_at=datetime.datetime.utcnow(),
             task_state=json.dumps({
                 "tasks": {
                     "generate": {"status": "completed"}, # Trick worker into thinking it's ready
                     "download": {"status": "pending"}
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

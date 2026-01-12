from app import models, database
from sqlalchemy.orm import Session

def inspect_job(job_id):
    db = database.SessionLocal()
    try:
        job = db.query(models.Job).filter(models.Job.id == job_id).first()
        if job:
            print(f"Job #{job.id}")
            print(f"Status: {job.status}")
            print(f"Error: {job.error_message}")
            import json
            print(f"Error: {job.error_message}")
            print(f"Task State: {json.dumps(json.loads(job.task_state), indent=2)}")
            print(f"Account ID: {job.account_id}")
            print(f"Created At: {job.created_at}")
            
            try:
                account = db.query(models.Account).filter(models.Account.id == 3).first()
                if account:
                    print(f"\n--- Debug Account ---")
                    print(f"Account Email: {account.email}")
            except Exception as e:
                print(f"Error fetching account: {e}")
        else:
            print(f"Job #{job_id} not found")
            print(f"Job #{job_id} not found")
    finally:
        db.close()

if __name__ == "__main__":
    inspect_job(4)

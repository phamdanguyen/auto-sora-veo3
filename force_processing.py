import sys
import os

# Add parent dir to path to find app module
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app import models, database

def force_processing(job_id=4):
    db = database.SessionLocal()
    try:
        job = db.query(models.Job).filter(models.Job.id == job_id).first()
        if job:
            print(f"Job #{job_id} current status: {job.status}")
            job.status = "processing"
            job.error_message = None # Clear error
            
            # Ensure generate task is marked as completed in task_state so scanner picks it up
            # (Scanner logic: if no URL, checks if generate is submitted/completed)
            import json
            if job.task_state:
                state = json.loads(job.task_state)
                # Ensure generate status is 'completed'
                state["tasks"]["generate"]["status"] = "completed"
                # Clear others for a fresh start
                state["tasks"]["poll"]["status"] = "pending"
                state["tasks"]["download"]["status"] = "blocked"
                job.task_state = json.dumps(state)
            
            db.commit()
            print(f"✅ Forced Job #{job_id} to 'processing'")
        else:
            print(f"❌ Job #{job_id} not found")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    force_processing()

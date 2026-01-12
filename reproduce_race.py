import requests
import threading
import time

BASE_URL = "http://127.0.0.1:8000/api"

def create_job(prompt):
    res = requests.post(f"{BASE_URL}/jobs/", json={
        "prompt": prompt,
        "duration": 5,
        "aspect_ratio": "16:9",
        "login_mode": "auto"
    })
    return res.json()

def start_job(job_id):
    # Simulate start via bulk action
    print(f"Starting job {job_id}...")
    res = requests.post(f"{BASE_URL}/jobs/bulk_action", json={
        "action": "start_selected",
        "job_ids": [job_id]
    })
    print(f"Start result for {job_id}: {res.status_code}")

def test_race_condition():
    # 1. Create a job
    job = create_job("Race Test Job")
    if "id" not in job:
        print(f"Error creating job: {job}")
        return
    job_id = job["id"]
    print(f"Created Job #{job_id}")

    # 2. Fire 2 threads to start it simultaneously
    t1 = threading.Thread(target=start_job, args=(job_id,))
    t2 = threading.Thread(target=start_job, args=(job_id,))
    
    t1.start()
    t2.start()
    
    t1.join()
    t2.join()
    
    # 3. Check logs manually or check duplicate via side effect?
    # Hard to check side effect without inspecting internal state logs.
    print("Race test done. Check logs for 'Skipping start_job' or 'Job is already active'.")

if __name__ == "__main__":
    test_race_condition()

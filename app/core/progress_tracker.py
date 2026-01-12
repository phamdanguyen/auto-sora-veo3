"""
Progress Tracker
Singleton service to track real-time progress of jobs across all workers.
Used for dashboard updates and monitoring.
"""
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Dict, Optional, List
import json

logger = logging.getLogger(__name__)

@dataclass
class JobProgress:
    job_id: int
    status: str  # queued, processing, generating, downloading, completed, failed
    progress_pct: float = 0.0  # 0-100
    account_id: Optional[int] = None
    started_at: Optional[str] = None
    updated_at: Optional[str] = None
    message: str = ""
    task_type: str = "init" # generate, poll, download
    eta_seconds: Optional[int] = None

class ProgressTracker:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ProgressTracker, cls).__new__(cls)
            cls._instance._jobs = {}
            cls._instance._initialized = True
        return cls._instance

    def __init__(self):
        if hasattr(self, "_initialized"): return
        self._jobs: Dict[int, JobProgress] = {}

    def update(self, job_id: int, status: str, progress: float = None, message: str = None, account_id: int = None):
        """Update job progress"""
        if job_id not in self._jobs:
            self._jobs[job_id] = JobProgress(
                job_id=job_id,
                status=status,
                started_at=datetime.utcnow().isoformat()
            )
        
        job = self._jobs[job_id]
        job.status = status
        job.updated_at = datetime.utcnow().isoformat()
        
        if progress is not None:
            job.progress_pct = progress
        if message:
            job.message = message
        if account_id:
            job.account_id = account_id
            
        # Log significant updates
        # logger.debug(f"📊 Job #{job_id} UPDATE: {status} ({job.progress_pct}%) - {message}")

    def get_job(self, job_id: int) -> Optional[dict]:
        if job_id in self._jobs:
            return asdict(self._jobs[job_id])
        return None

    def get_all_jobs(self) -> List[dict]:
        return [asdict(j) for j in self._jobs.values()]

    def remove_job(self, job_id: int):
        if job_id in self._jobs:
            del self._jobs[job_id]

# Global instance
tracker = ProgressTracker()

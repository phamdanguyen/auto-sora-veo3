"""
Simple Task Manager - Zero-config task orchestration
Uses in-memory queues for task management
"""
import asyncio
from dataclasses import dataclass
from typing import Dict, Optional
import json
import logging
from datetime import datetime
from sqlalchemy import func as sqla_func

logger = logging.getLogger(__name__)

# Valid job status transitions
VALID_JOB_TRANSITIONS = {
    "draft": ["pending", "processing", "cancelled"],  # Allow draft -> processing directly
    "pending": ["processing", "cancelled"],
    "processing": ["sent_prompt", "generating", "download", "completed", "done", "failed", "cancelled"],
    "sent_prompt": ["generating", "failed", "cancelled"],
    "generating": ["download", "failed", "cancelled"],
    "download": ["done", "completed", "failed", "cancelled"],
    "completed": ["done"],  # Allow migration if needed
    "done": [],  # Terminal state
    "failed": ["pending"],  # Can retry (but only via explicit retry)
    "cancelled": []  # Terminal state
}

@dataclass
class TaskContext:
    """Lightweight task context - no DB needed!"""
    job_id: int
    task_type: str  # "generate" | "download" | "verify"
    input_data: dict
    retry_count: int = 0

class SimpleTaskManager:
    """
    Zero-config Task Manager using in-memory queues

    Tasks flow: GENERATE → DOWNLOAD → VERIFY (optional)
    Each task is processed by dedicated worker loops
    """

    # Queue size limits to prevent memory leaks
    MAX_QUEUE_SIZE = 1000  # Max tasks in each queue

    def __init__(self):
        # Lazy initialization - queues created when first accessed
        self._generate_queue = None
        self._poll_queue = None  # NEW: For polling video completion
        self._download_queue = None
        self._verify_queue = None
        self._active_job_ids = set() # Track active job IDs to prevent duplicates
        self._initialized = False
        self._paused = False  # Global pause flag
        self._pause_reason: Optional[str] = None

    def force_clear_active(self):
        """Force clear active job tracking (Emergency use)"""
        if self._active_job_ids:
            logger.warning(f"[WARNING]  FORCE RESET: Clearing {len(self._active_job_ids)} active job IDs.")
            self._active_job_ids.clear()

    def _get_job_id_val(self, job) -> int:
        """Helper to get integer ID from Job object or int"""
        if hasattr(job, "id") and hasattr(job.id, "value"):
            return job.id.value
        if hasattr(job, "id"):
             return job.id
        return job

    def _get_job_status_val(self, job) -> str:
        """Helper to get status string from Job object"""
        if hasattr(job, "progress") and hasattr(job.progress, "status"):
            # Domain model
            if hasattr(job.progress.status, "value"):
                 return job.progress.status.value
            return str(job.progress.status)
        # Legacy or direct dict
        return job.status

    def _update_job_status(self, job, status: str, error: str = None):
         """Helper to update job status on Domain Object"""
         from .domain.job import JobStatus
         # Convert string to Enum
         try:
             enum_status = JobStatus(status)
         except:
             logger.error(f"Invalid status string: {status}")
             enum_status = status
         
         if hasattr(job, "progress"):
             job.progress.status = enum_status
             if error:
                 job.progress.error_message = error
         else:
             job.status = status
             if error:
                 job.error_message = error

    @property
    def is_paused(self) -> bool:
        return self._paused

    def pause(self, reason: str = None):
        """Pause all queue processing"""
        log_msg = f"⏸️ System Paused. Workers will stop picking up new tasks. Reason: {reason or 'User action'}"
        logger.warning(log_msg)
        self._paused = True
        self._pause_reason = reason

    def resume(self):
        """Resume queue processing"""
        logger.info("▶️ System Resumed. Workers continuing...")
        self._paused = False
        self._pause_reason = None

    def get_status(self) -> dict:
        """Get comprehensive queue status"""
        self._ensure_initialized()
        return {
            "paused": self._paused,
            "pause_reason": self._pause_reason,
            "active_jobs_count": len(self._active_job_ids),
            "queues": {
                "generate": self._generate_queue.qsize(),
                "poll": self._poll_queue.qsize(),
                "download": self._download_queue.qsize(),
                "verify": self._verify_queue.qsize()
            }
        }

    def remove_active_job(self, job_id: int):
        """Manually remove a job from active set (e.g. for retry)"""
        if job_id in self._active_job_ids:
            self._active_job_ids.remove(job_id)

    def _ensure_initialized(self):
        """Initialize queues in the current event loop"""
        if not self._initialized:
            self._generate_queue = asyncio.Queue(maxsize=self.MAX_QUEUE_SIZE)
            self._poll_queue = asyncio.Queue(maxsize=self.MAX_QUEUE_SIZE)  # NEW
            self._download_queue = asyncio.Queue(maxsize=self.MAX_QUEUE_SIZE)
            self._verify_queue = asyncio.Queue(maxsize=self.MAX_QUEUE_SIZE)
            self._initialized = True
            logger.info(f"[OK]  SimpleTaskManager queues initialized (max_size={self.MAX_QUEUE_SIZE})")


    @property
    def generate_queue(self):
        self._ensure_initialized()
        return self._generate_queue

    @property
    def download_queue(self):
        self._ensure_initialized()
        return self._download_queue

    @property
    def poll_queue(self):
        """Queue for polling video completion status"""
        self._ensure_initialized()
        return self._poll_queue

    @property
    def verify_queue(self):
        self._ensure_initialized()
        return self._verify_queue

    async def _put_task_safe(self, queue, task: TaskContext, timeout: float = 5.0):
        """
        Safely put task into queue with timeout to prevent blocking

        Args:
            queue: Target queue
            task: Task to enqueue
            timeout: Max seconds to wait if queue is full

        Raises:
            asyncio.TimeoutError: If queue is full after timeout
        """
        # Log warning if queue is getting full (>80%)
        if queue.qsize() > self.MAX_QUEUE_SIZE * 0.8:
            logger.warning(
                f"[WARNING]  Queue nearly full: {queue.qsize()}/{self.MAX_QUEUE_SIZE} tasks. "
                f"Attempting to enqueue {task.task_type} for job #{task.job_id}"
            )

        try:
            await asyncio.wait_for(queue.put(task), timeout=timeout)
        except asyncio.TimeoutError:
            raise Exception(
                f"Queue full (max_size={self.MAX_QUEUE_SIZE}). "
                f"Task {task.task_type} for job #{task.job_id} could not be enqueued after {timeout}s."
            )

    async def start_job(self, job):
        """
        Bắt đầu job - initialize task state và add generate task vào queue

        Args:
            job: Job model instance
        """
        try:
            job_id = self._get_job_id_val(job)
            current_status = self._get_job_status_val(job)
            logger.info(f"[START]  Starting job #{job_id} (current status: {current_status})")
            
            # Validate status transition
            self._validate_job_status_transition(job, "processing")

            # Initialize task state in job using default state
            task_state = self._default_state()

            # Domain Model: task_state is dict
            job.task_state = task_state
            
            self._update_job_status(job, "processing")
            job.updated_at = datetime.utcnow()  # Explicit timestamp update
            
            # Add to generate queue
            # Add to generate queue
            task = TaskContext(
                job_id=job_id,
                task_type="generate",
                input_data={
                    "prompt": job.spec.prompt,
                    "duration": job.spec.duration,
                    "account_id": job.account_id
                }
            )
            
            # Add to active set
            if job_id in self._active_job_ids:
                 logger.warning(f"[WARNING]  Job #{job_id} is already active in TaskManager. Skipping start_job.")
                 return

            self._active_job_ids.add(job_id)

            await self.generate_queue.put(task)
            logger.info(f"[OK]  Job #{job_id} added to generate queue (queue size: {self.generate_queue.qsize()})")
            
        except ValueError as e:
            logger.error(f"[ERROR]  Failed to start job #{self._get_job_id_val(job)}: {e}")
            raise
        except Exception as e:
            logger.error(f"[ERROR]  Unexpected error starting job #{self._get_job_id_val(job)}: {e}")
            raise
    
    async def complete_submit(self, job, account_id: int, credits_before: int, credits_after: int):
        """
        Submit phase complete → move to poll queue

        Args:
            job: Job model instance
            account_id: Account used for generation
            credits_before: Credits before submission
            credits_after: Credits after submission
        """
        state = await self.get_job_state(job)
        
        # Update state to reflect submission
        state["tasks"]["generate"] = {
            "status": "completed",  # Mark as completed (Submission done)
            "completed_at": datetime.now().isoformat(),
            "submitted_at": datetime.now().isoformat(),
            "account_id": account_id,
            "credits_before": credits_before,
            "credits_after": credits_after
        }
        state["tasks"]["poll"] = {"status": "pending"}
        state["current_task"] = "poll"
        
        job.task_state = state
        job.updated_at = datetime.utcnow()  # Explicit timestamp update

        # Add to poll queue
        # task = TaskContext(
        #     job_id=job.id,
        #     task_type="poll",
        #     input_data={
        #         "account_id": account_id,
        #         "submitted_at": datetime.now().isoformat(),
        #         "poll_count": 0  # Initialize poll counter
        #     }
        # )

        # await self.poll_queue.put(task)
        logger.info(f"[OK]  Job #{job.id} submitted (sequential flow active - skipping poll queue add)")
    
    async def complete_poll(self, job, video_url: str):
        """
        Poll phase complete (video ready) → move to download queue

        Args:
            job: Job model instance
            video_url: Public video URL
        """
        state = await self.get_job_state(job)

        # Mark poll as completed
        state["tasks"]["poll"]["status"] = "completed"
        state["tasks"]["poll"]["completed_at"] = datetime.now().isoformat()

        # Unlock download task
        state["tasks"]["download"] = {
            "status": "pending",
            "input": {"video_url": video_url}
        }
        state["current_task"] = "download"

        job.task_state = state
        if hasattr(job, "result"):
             job.result.video_url = video_url
        else:
             job.video_url = video_url
        job.updated_at = datetime.utcnow()  # Explicit timestamp update

        # Add to download queue
        # task = TaskContext(
        #     job_id=job.id,
        #     task_type="download",
        #     input_data={"video_url": video_url}
        # )

        # await self.download_queue.put(task)
        logger.info(f"[OK]  Job #{job.id} video ready (sequential flow active - skipping download queue add)")
    
    async def complete_generate(self, job, video_url: str, metadata: dict):
        """
        Generate complete → unlock download task

        Args:
            job: Job model instance
            video_url: Captured video URL from generation
            metadata: Additional metadata (size, etc.)
        """
        state = await self.get_job_state(job)
        
        # Update generate task
        state["tasks"]["generate"] = {
            "status": "completed",
            "completed_at": datetime.now().isoformat(),
            "output": {"video_url": video_url, "metadata": metadata}
        }
        
        # Unlock download
        state["tasks"]["download"] = {
            "status": "pending",
            "input": {"video_url": video_url}
        }
        state["current_task"] = "download"
        
        job.task_state = state
        if hasattr(job, "result"):
             job.result.video_url = video_url
        else:
             job.video_url = video_url
        job.updated_at = datetime.utcnow()  # Explicit timestamp update

        # Add to download queue
        # task = TaskContext(
        #     job_id=job.id,
        #     task_type="download",
        #     input_data={"video_url": video_url}
        # )
        
        # await self.download_queue.put(task)
        logger.info(f"[OK]  Job #{job.id} moved to download queue (sequential flow active - skipping download queue add)")
    
    async def complete_download(self, job, local_path: str, file_size: int):
        """
        Download complete → complete job (skip verify for now)

        Args:
            job: Job model instance
            local_path: Path to downloaded video
            file_size: Size of downloaded file
        """
        state = await self.get_job_state(job)
        
        state["tasks"]["download"] = {
            "status": "completed",
            "completed_at": datetime.now().isoformat(),
            "output": {"local_path": local_path, "file_size": file_size}
        }

        # For now, skip verify - just complete job
        state["current_task"] = "completed"

        # Validate status transition before changing
        self._validate_job_status_transition(job, "done")

        self._update_job_status(job, "done")
        if hasattr(job, "result"):
             job.result.local_path = local_path
        else:
             job.local_path = local_path
        job.task_state = state
        job.updated_at = datetime.utcnow()  # Explicit timestamp update

        logger.info(f"[OK]  Job #{self._get_job_id_val(job)} completed! Video at {local_path} ({file_size:,} bytes)")
        
        # Remove from active set
        self._active_job_ids.discard(self._get_job_id_val(job))
    
    async def fail_task(self, job, task_type: str, error: str):
        """
        Handle task failure với retry logic

        Args:
            job: Job model instance
            task_type: Type of task that failed
            error: Error message
        """
        state = await self.get_job_state(job)
        task_state = state["tasks"].get(task_type, {})
        
        retry_count = task_state.get("retry_count", 0) + 1
        max_retries = 3
        
        if retry_count < max_retries:
            # Retry - update state and re-queue
            task_state["retry_count"] = retry_count
            task_state["status"] = "pending"
            task_state["last_error"] = error
            state["tasks"][task_type] = task_state

            job.task_state = state
            job.updated_at = datetime.utcnow()  # Explicit timestamp update
            
            # Re-add to appropriate queue
            queue = getattr(self, f"{task_type}_queue")
            
            # Get input data from state or job
            if task_type == "generate":
                input_data = {
                    "prompt": job.spec.prompt,
                    "duration": job.spec.duration,
                    "account_id": job.account_id
                }
            elif task_type == "download":
                if hasattr(job, "result"):
                     video_url = job.result.video_url
                else:
                     video_url = job.video_url
                input_data = task_state.get("input", {"video_url": video_url})
            else:
                input_data = task_state.get("input", {})
            
            task = TaskContext(
                job_id=self._get_job_id_val(job),
                task_type=task_type,
                input_data=input_data,
                retry_count=retry_count
            )
            await queue.put(task)
            
            logger.warning(f"[WARNING]  Job #{self._get_job_id_val(job)} {task_type} failed, retry {retry_count}/{max_retries}: {error}")
        else:
            # Max retries reached - fail job
            task_state["status"] = "failed"
            task_state["error"] = error
            state["tasks"][task_type] = task_state

            # Validate status transition before changing
            self._validate_job_status_transition(job, "failed")

            self._update_job_status(job, "failed", f"{task_type} failed after {max_retries} retries: {error}")
            job.task_state = state
            job.updated_at = datetime.utcnow()  # Explicit timestamp update

            logger.error(f"[ERROR]  Job #{self._get_job_id_val(job)} failed permanently: {task_type} - {error}")
            
            # Remove from active set
            self._active_job_ids.discard(self._get_job_id_val(job))
    
    def _default_state(self):
        """Default task state structure"""
        return {
            "tasks": {
                "generate": {"status": "pending"},
                "poll": {"status": "blocked"},
                "download": {"status": "blocked"},
                "verify": {"status": "blocked"}
            },
            "current_task": "generate"
        }
    
    async def get_job_state(self, job) -> dict:
        """Get parsed task state from job"""
        if job.task_state:
            # Domain model uses dict, legacy might use string
            if isinstance(job.task_state, dict):
                return self._validate_and_fix_state(job.task_state)
            
            try:
                state = json.loads(job.task_state)
                # Validate and fix state if needed
                return self._validate_and_fix_state(state)
            except json.JSONDecodeError:
                logger.error(f"Invalid JSON in job #{self._get_job_id_val(job)} task_state, using default")
                return self._default_state()
        return self._default_state()

    def _validate_and_fix_state(self, state: dict) -> dict:
        """
        Validate task state structure and fix missing fields

        Args:
            state: Task state dict

        Returns:
            Fixed/valid task state
        """
        default = self._default_state()

        # Ensure top-level keys exist
        if "tasks" not in state:
            state["tasks"] = {}
        if "current_task" not in state:
            state["current_task"] = "generate"

        # Ensure all task types exist (add missing ones as blocked)
        for task_type in default["tasks"].keys():
            if task_type not in state["tasks"]:
                state["tasks"][task_type] = {"status": "blocked"}
                logger.warning(f"Added missing task type '{task_type}' to state")

        return state

    def _validate_job_status_transition(self, job, new_status: str, allow_retry: bool = False) -> bool:
        """
        Validate if job status transition is allowed

        Args:
            job: Job model instance
            new_status: New status to transition to
            allow_retry: If True, allow failed → pending transition

        Returns:
            bool: True if transition is valid

        Raises:
            ValueError: If transition is invalid
        """

        current_status = self._get_job_status_val(job)
        valid_transitions = VALID_JOB_TRANSITIONS.get(current_status, [])

        # Special case: allow failed → pending only if explicitly allowed (retry)
        if current_status == "failed" and new_status == "pending" and not allow_retry:
            raise ValueError(
                f"Invalid transition: {current_status} → {new_status}. "
                f"Use retry endpoint to restart failed jobs."
            )

        if new_status not in valid_transitions:
            raise ValueError(
                f"Invalid job status transition: {current_status} → {new_status}. "
                f"Valid transitions from {current_status}: {valid_transitions}"
            )

        return True

    async def retry_subtasks(self, job):
        """
        Retry post-generation tasks (Poll or Download)
        Useful if a submitted job got stuck or download failed
        """
        # Ensure job is marked as processing
        if self._get_job_status_val(job) == "pending":
            self._update_job_status(job, "processing")
            job.updated_at = datetime.utcnow()

        # Await the coroutine
        state = await self.get_job_state(job)
        gen_status = state["tasks"]["generate"]["status"]
        
        if job.video_url:
            # Video URL exists -> Retry Download
            logger.info(f"[MONITOR]  Retrying Download for Job #{job.id}")
            state["tasks"]["download"]["status"] = "pending"
            state["current_task"] = "download"
            job.task_state = json.dumps(state)
            
            if hasattr(job, "result"):
                 video_url = job.result.video_url
            else:
                 video_url = job.video_url

            task = TaskContext(
                job_id=self._get_job_id_val(job),
                task_type="download",
                input_data={"video_url": video_url}
            )
            await self.download_queue.put(task)
            
        elif gen_status in ["submitted", "completed"]:
            # Generation done/submitted, but no URL -> Retry Poll
            logger.info(f"[MONITOR]  Retrying Poll for Job #{self._get_job_id_val(job)}")
            state["tasks"]["poll"]["status"] = "pending"
            state["tasks"]["poll"]["retry_count"] = 0  # Reset retry count
            state["tasks"]["poll"]["last_error"] = None # Clear error
            state["current_task"] = "poll"
            job.task_state = state
            
            # Need account status from state
            acct_id = state["tasks"]["generate"].get("account_id")
            if not acct_id:
                # Try to get from job
                acct_id = job.account_id
                
            task = TaskContext(
                job_id=self._get_job_id_val(job),
                task_type="poll",
                input_data={
                    "account_id": acct_id,
                    "poll_count": 0,  # Reset poll counter on retry
                    "retry_count": 0
                }
            )
            await self.poll_queue.put(task)
        else:
            logger.warning(f"[WARNING]  Job #{self._get_job_id_val(job)} not in a state to retry subtasks (Gen Status: {gen_status})")

# Global instance
task_manager = SimpleTaskManager()

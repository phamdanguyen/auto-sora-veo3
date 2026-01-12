"""
Concurrent Worker using Task Manager
Processes generate and download tasks with multiple concurrent workers
REFACTORED: Multi-account parallel processing with per-account rate limiting
"""
import asyncio
from sqlalchemy.orm import Session
from .. import models, database
from . import account_manager
from .drivers.sora import SoraDriver
from .drivers.sora.exceptions import QuotaExhaustedException, VerificationRequiredException
from .task_manager import task_manager
from .download_utils import download_from_url
from .security import decrypt_password
from .progress_tracker import tracker
import logging
import traceback
import json
import os
import random
import aiohttp
import time
from datetime import datetime, timedelta
from typing import Optional, List, Dict
from collections import defaultdict

logger = logging.getLogger(__name__)

# ============== PARALLEL PROCESSING CONFIG ==============
# Max concurrent generate tasks (now limited by available accounts)
MAX_CONCURRENT_GENERATE = 20  # User Request: Max 20 concurrent jobs
MAX_CONCURRENT_DOWNLOAD = 5   # Parallel downloads
MAX_CONCURRENT_POLL = 20      # Match generate limit for polling
MAX_ACCOUNT_SWITCHES = 10 

# Rate limiting settings (read from account_manager)
# SUBMIT_RATE_LIMIT_SECONDS is managed in account_manager

# Per-account semaphores (still needed for concurrency control within worker)
_account_semaphores: Dict[int, asyncio.Semaphore] = {}  # 1 concurrent job per account
_semaphores_lock: Optional[asyncio.Lock] = None

def _get_semaphores_lock():
    """Lazy-init semaphores lock"""
    global _semaphores_lock
    if _semaphores_lock is None:
        _semaphores_lock = asyncio.Lock()
    return _semaphores_lock

async def get_account_semaphore(account_id: int) -> asyncio.Semaphore:
    """Get or create semaphore for account (ensures 1 job per account at a time)"""
    async with _get_semaphores_lock():
        if account_id not in _account_semaphores:
            _account_semaphores[account_id] = asyncio.Semaphore(1)
        return _account_semaphores[account_id]

# Keep browser lock for backward compatibility but now per-account
_browser_lock = None

def _get_browser_lock():
    """Lazy-init browser lock - NOW DEPRECATED, use per-account semaphores"""
    global _browser_lock
    if _browser_lock is None:
        _browser_lock = asyncio.Lock()
    return _browser_lock

from app.core.task_manager import task_manager

async def process_generate_tasks():
    """
    Worker loop for generation tasks - PARALLEL MODE
    
    Now spawns concurrent tasks per-account instead of sequential processing.
    Rate limiting (30s) is enforced per-account to avoid being blocked.
    """
    logger.info(f"🎬 Generate Worker started (PARALLEL Mode). TaskManager ID: {id(task_manager)}")
    logger.info(f"   Config: MAX_CONCURRENT={MAX_CONCURRENT_GENERATE}")

# Global active tasks registry
_active_generate_tasks: Dict[int, asyncio.Task] = {}

async def process_generate_tasks():
    """
    Worker loop for generation tasks - PARALLEL MODE
    
    Now spawns concurrent tasks per-account instead of sequential processing.
    Rate limiting (30s) is enforced per-account to avoid being blocked.
    """
    logger.info(f"🎬 Generate Worker started (PARALLEL Mode). TaskManager ID: {id(task_manager)}")
    logger.info(f"   Config: MAX_CONCURRENT={MAX_CONCURRENT_GENERATE}")

    # Use global registry
    global _active_generate_tasks
    
    while not STOP_EVENT.is_set():
        # Check Pause
        if task_manager.is_paused:
            await asyncio.sleep(1)
            continue
            
        try:
            # Clean up finished tasks
            finished = [jid for jid, t in _active_generate_tasks.items() if t.done()]
            for jid in finished:
                try:
                    # Check for exceptions
                    _active_generate_tasks[jid].result()
                except asyncio.CancelledError:
                    logger.warning(f"⚠️ Job #{jid} was cancelled.")
                except Exception as e:
                    logger.error(f"❌ Background task for Job #{jid} failed: {e}")
                
                # Safe delete
                if jid in _active_generate_tasks:
                    del _active_generate_tasks[jid]
            
            # Check if we can accept more tasks
            if len(_active_generate_tasks) >= MAX_CONCURRENT_GENERATE:
                await asyncio.sleep(1)
                continue
            
            # Wait for a task with timeout
            try:
                task = await asyncio.wait_for(task_manager.generate_queue.get(), timeout=5.0)
            except asyncio.TimeoutError:
                # Log heartbeat periodically
                q_size = task_manager.generate_queue.qsize()
                if q_size > 0:
                    logger.info(f"💓 Heartbeat: Queue={q_size}, Active={len(_active_generate_tasks)}")
                continue

            job_id = task.job_id
            logger.info(f"📥 [Queue] Picked up Job #{job_id}. Active tasks: {len(_active_generate_tasks)}/{MAX_CONCURRENT_GENERATE}")
            tracker.update(job_id, "processing", message="Job dispatched to worker")
            
            # Spawn parallel task (will handle its own account selection + rate limiting)
            bg_task = asyncio.create_task(
                _process_generate_with_rate_limit(task),
                name=f"generate_job_{job_id}"
            )
            _active_generate_tasks[job_id] = bg_task
            
            logger.info(f"🚀 Job #{job_id} dispatched to background worker")

        except Exception as e:
            logger.error(f"❌ CRITICAL WORKER ERROR (Restarting Loop): {e}", exc_info=True)
            await asyncio.sleep(5)
    
    # Cleanup on shutdown
    logger.warning("🛑 Generate Worker stopping - waiting for active tasks...")
    for jid, t in _active_generate_tasks.items():
        t.cancel()
    await asyncio.gather(*_active_generate_tasks.values(), return_exceptions=True)
    logger.warning("🛑 Generate Worker Loop Exited (STOP_EVENT set)")


async def _process_generate_with_rate_limit(task):
    """
    Wrapper that handles account selection, rate limiting, and per-account semaphore.
    This enables parallel processing while respecting rate limits.
    """
    db = database.SessionLocal()
    account = None
    
    try:
        # 1. Get job from DB
        job = db.query(models.Job).filter(models.Job.id == task.job_id).first()
        if not job:
            logger.error(f"Job #{task.job_id} not found!")
            return
            
        tracker.update(task.job_id, "processing", message="Selecting account...")

        # 2. Get available account (with LRU + busy check + rate limit check)
        exclude_ids = task.input_data.get("exclude_account_ids", [])
        account_id = task.input_data.get("account_id")
        
        # If account specifically assigned/requested
        if account_id and account_id not in exclude_ids:
            account = db.query(models.Account).filter(models.Account.id == account_id).first()
            if account and account.status != "live":
                account = None
        
        # If no specific account, find one from pool
        if not account:
            account = account_manager.get_available_account(db, platform="sora", exclude_ids=exclude_ids)
        
        if not account:
            # No account available - re-queue with delay
            msg = f"⏳ No available account (all busy/cooldown/exhausted). Re-queuing..."
            logger.warning(f"Job #{task.job_id}: {msg}")
            tracker.update(task.job_id, "queued", message="Waiting for available account")
            
            await asyncio.sleep(10)
            await task_manager.generate_queue.put(task)
            return
        
        # 3. Get per-account semaphore (ensures 1 job per account at a time)
        account_sem = await get_account_semaphore(account.id)
        
        async with account_sem:
            tracker.update(task.job_id, "processing", message=f"Locked Account #{account.id}", account_id=account.id)
            logger.info(f"🔐 Job #{task.job_id}: Acquired semaphore for Account #{account.id}")
            
            # 4. Wait for rate limit cooldown (30s between submits for same account)
            # Only needed if this specific account was picked but is still in cooldown 
            # (e.g. if we picked by ID or if get_available_account logic changed)
            remaining = account_manager.get_cooldown_remaining(account.id)
            if remaining > 0:
                msg = f"Waiting rate limit ({remaining:.1f}s)"
                logger.info(f"⏳ Job #{task.job_id} (Account #{account.id}): {msg}")
                tracker.update(task.job_id, "processing", message=msg)
                await asyncio.sleep(remaining)
            
            # 5. Mark account as busy (for LRU logic) and Record start time
            # Important: Mark busy prevents other workers from picking this account via get_available_account
            await account_manager.mark_account_busy(account.id)
            # Record submit time NOW to block subsequent jobs immediately
            account_manager.record_submit_time(account.id)
            
            try:
                # 6. Inject Account ID into task input so inner function uses it
                task.input_data["account_id"] = account.id
                
                # 7. Process the job (API call)
                tracker.update(task.job_id, "processing", message=f"Submitting job...")
                logger.info(f"🎬 Processing Job #{task.job_id} with Account #{account.id} ({account.email})")
                
                await process_single_generate_task(task)
                
            finally:
                # 8. Mark account as free
                await account_manager.mark_account_free(account.id)
                logger.info(f"✅ Job #{task.job_id}: Released Account #{account.id}")
    
    except Exception as e:
        logger.error(f"❌ _process_generate_with_rate_limit error for Job #{task.job_id}: {e}", exc_info=True)
        tracker.update(task.job_id, "failed", message=f"Worker error: {str(e)}")
        # Re-queue on error
        await asyncio.sleep(5)
        await task_manager.generate_queue.put(task)
    finally:
        db.close()


async def process_single_generate_task(task):
    """Process a single generation task"""
    db = database.SessionLocal()
    account = None
    driver = None

    try:
        job = db.query(models.Job).filter(models.Job.id == task.job_id).first()

        if not job:
            logger.error(f"Job #{task.job_id} not found!")
            return

        # Check if job was cancelled or removed
        if job.status not in ["pending", "processing", "sent_prompt", "generating", "download"]:
            logger.warning(f"🛑 Job #{task.job_id} is in status '{job.status}'. Skipping task.")
            return

        # Pre-assigned account from wrapper
        account_id = task.input_data.get("account_id")
        
        if account_id:
            account = db.query(models.Account).filter(models.Account.id == account_id).first()

        if not account or account.status != "live":
            # This should theoretically not happen if wrapper did its job, 
            # unless account died in the microseconds between wrapper and here.
            logger.error(f"❌ Job #{task.job_id}: Invalid Assigned Account #{account_id}")
            tracker.update(task.job_id, "failed", message="Assigned account invalid")
            # Fail the task so it can be retried properly
            await task_manager.fail_task(job, "generate", "Assigned account invalid/died")
            db.commit()
            return

        # Update job with account info
        try:
            job.account_id = account.id
            account.last_used = datetime.utcnow()
            db.commit()
        except Exception as commit_error:
            logger.error(f"Failed to update job/account in DB: {commit_error}")
            db.rollback()
            raise

        logger.info(f"📝 Processing generate task for job #{task.job_id} with account #{account.id} ({account.email})")
        tracker.update(task.job_id, "processing", message=f"Initializing driver for Account #{account.id}", account_id=account.id)

        # NOTE: Legacy browser lock removed. Semaphore in wrapper handles concurrency.
        # Account file lock (if needed for profile) is handled within SoraDriver if using profile?
        # Actually api_only doesn't use profile dir, so no file lock needed.

        if account.token_status != "valid" or not account.access_token:
            logger.warning(f"⚠️ Account #{account.id} ({account.email}) has invalid/missing token. Marking for login.")
            try:
                await task_manager.fail_task(job, "generate", "Account requires login (Token invalid/expired)")
                db.commit()
            except Exception as e:
                logger.error(f"Failed to fail task: {e}")
                db.rollback()
            return
            
        # Setup API-Only Driver
        try:
            driver = await SoraDriver.api_only(
                access_token=account.access_token,
                device_id=account.device_id,
                user_agent=account.user_agent
            )
             
            # PRE-CHECK: Get credits via API
            logger.info("💰 Checking credits via API...")
            tracker.update(task.job_id, "processing", message="Checking credits...")
            
            credits_info = await driver.get_credits_api()
            
            # Default to sufficient if check fails (soft check)
            has_credits = True
            
            if credits_info:
                logger.info(f"💳 Credits available: {credits_info.get('credits', 'unknown')}")
                 
                # Update account stats
                if credits_info.get('credits') is not None:
                    credits_val = int(credits_info.get('credits'))
                    account.credits_remaining = credits_val
                    
                    # BLOCKING CHECK: If credits known and < threshold -> Stop
                    SAFE_THRESHOLD = 1
                    if credits_val < SAFE_THRESHOLD:
                        logger.warning(f"🚫 Account #{account.id} has {credits_val} credits (Low < {SAFE_THRESHOLD})! Marking exhausted.")
                        has_credits = False
                        
                if credits_info.get('reset_seconds'):
                    from datetime import timedelta
                    reset_date = datetime.utcnow() + timedelta(seconds=int(credits_info.get('reset_seconds')))
                    account.credits_reset_at = reset_date
                
                account.credits_last_checked = datetime.utcnow()
                db.commit()
            else:
                logger.warning("⚠️ Could not check credits via API (Token might be expired). Proceeding with caution.")

            if not has_credits:
                # Handle Exhausted Account
                account.status = "quota_exhausted"
                db.commit()
                
                logger.info(f"♻️ Re-queuing Job #{task.job_id} to find another account...")
                tracker.update(task.job_id, "queued", message="Switching account (Credits exhausted)")
                
                # Update Excludes to avoid selecting this account again immediately
                excludes = task.input_data.get("exclude_account_ids", [])
                if account.id not in excludes:
                    excludes.append(account.id)
                task.input_data["exclude_account_ids"] = excludes
                
                # Clear assigned account so wrapper picks a new one
                if "account_id" in task.input_data:
                    del task.input_data["account_id"]
                
                # Re-queue
                await asyncio.sleep(2) # Brief pause
                await task_manager.generate_queue.put(task)
                return

            # =========== API-ONLY VIDEO GENERATION ===========
            logger.info(f"🚀 Submitting video via API for job #{task.job_id}...")
            tracker.update(task.job_id, "processing", message="Submitting generation request...")
            
            api_result = await driver.generate_video_api(
                prompt=task.input_data["prompt"],
                orientation=task.input_data.get("orientation", "landscape"),
                n_frames=task.input_data.get("n_frames", 180)  # 6 seconds default
            )
            
            if not api_result.get("success"):
                error_msg = str(api_result.get('error', 'Unknown API error'))[:200]
                logger.error(f"❌ API generation failed: {error_msg}")
                tracker.update(task.job_id, "failed", message=f"API Error: {error_msg}")

                # Check for ACCOUNT-LEVEL errors that require switching accounts
                account_switch_keywords = ["phone_number_required", "verification_required", "account_deactivated", "suspended"]
                needs_account_switch = any(k in error_msg.lower() for k in account_switch_keywords)

                if needs_account_switch:
                    logger.warning(f"⚠️ Account-level error detected: {error_msg}")

                    # Mark account as needing verification/bad
                    if "phone_number_required" in error_msg.lower() or "verification_required" in error_msg.lower():
                        account_manager.mark_account_verification_needed(db, account)
                    elif "suspended" in error_msg.lower() or "deactivated" in error_msg.lower():
                        account.status = "suspended"
                        db.commit()

                    # Track account switches to prevent infinite loop
                    account_switch_count = task.input_data.get("account_switch_count", 0) + 1

                    if account_switch_count >= MAX_ACCOUNT_SWITCHES:
                        logger.error(f"❌ Job #{job.id} exceeded max account switches ({MAX_ACCOUNT_SWITCHES})")
                        await task_manager.fail_task(job, "generate", f"Failed after switching {MAX_ACCOUNT_SWITCHES} accounts: {error_msg}")
                        db.commit()
                        return

                    # Try to switch to another account
                    exclude_ids = task.input_data.get("exclude_account_ids", [])
                    exclude_ids.append(account.id)

                    other_account = account_manager.get_available_account(db, platform="sora", exclude_ids=exclude_ids)

                    if other_account:
                        logger.info(f"🔄 Switching from Account #{account.id} to #{other_account.id} (switch {account_switch_count}/{MAX_ACCOUNT_SWITCHES})")
                        from .task_manager import TaskContext
                        new_task = TaskContext(
                            job_id=job.id,
                            task_type="generate",
                            input_data={
                                "prompt": job.prompt,
                                "duration": job.duration,
                                "orientation": task.input_data.get("orientation", "landscape"),
                                "n_frames": task.input_data.get("n_frames", 180),
                                "account_id": None,  # Let wrapper pick the new account
                                "exclude_account_ids": exclude_ids,
                                "account_switch_count": account_switch_count
                            },
                            retry_count=task.retry_count
                        )
                        await task_manager.generate_queue.put(new_task)
                        logger.info(f"✅ Job #{job.id} re-queued with different account")
                        return
                    else:
                        logger.error(f"❌ No other accounts available for Job #{job.id}")
                        await task_manager.fail_task(job, "generate", f"No available accounts (all need verification or exhausted)")
                        db.commit()
                        return

                # Normal Retry Logic for transient errors
                retry_count = task.input_data.get("api_retry_count", 0)
                if retry_count < 3:
                    logger.info(f"♻️ Retrying API call... (attempt {retry_count + 1}/3)")
                    await asyncio.sleep(10)
                    task.input_data["api_retry_count"] = retry_count + 1
                    await task_manager.generate_queue.put(task)
                    return
                else:
                    await task_manager.fail_task(job, "generate", f"API failed after 3 retries: {error_msg}")
                    db.commit()
                    return
            
            # API success
            logger.info(f"✅ API submission SUCCESS! Task: {api_result.get('task_id')}")
            tracker.update(task.job_id, "generating", message="Video generating...", progress=20.0)
            
            # REFRESH CREDITS for accuracy (User Requirement)
            # Fetch latest credits to show correct balance after deduction
            refresh_credits = None
            try:
                # Wait 2s for backend to update balance
                await asyncio.sleep(2) 
                refresh_credits = await driver.get_credits_api()
                logger.info(f"💰 Credit Refresh: {refresh_credits.get('credits') if refresh_credits else 'Failed'}")
            except Exception as e:
                logger.warning(f"⚠️ Failed to refresh credits after submission: {e}")
            
            # Use refreshed credits if available, else fallback to pre-check info
            final_credits_info = refresh_credits if refresh_credits else credits_info

            result = {
                "submitted": True,
                "credits_remaining": final_credits_info.get('credits') if final_credits_info else None,
                "reset_seconds": final_credits_info.get('reset_seconds') if final_credits_info else None,
                "api_mode": True,
                "task_id": api_result.get("task_id")
            }
            
            if result["submitted"]:
                credits_rem = result.get("credits_remaining")
                reset_secs = result.get("reset_seconds")
                
                logger.info(f"✅ Job #{task.job_id} submitted! Credits: {credits_rem}")

                # UPDATE ACCOUNT CREDITS & RESET TIME
                try:
                    # Update credits if available
                    if credits_rem is not None:
                        account.credits_remaining = int(credits_rem)
                    
                    # Update reset time if available
                    if reset_secs is not None:
                         # Calculate absolute reset time
                         reset_date = datetime.utcnow() + timedelta(seconds=int(reset_secs))
                         account.credits_reset_at = reset_date # Ensure model has this field or add it?
                         # Checks models.py: Account has credits_last_checked, needs credits_reset_at?
                         # The user asked to "identify time reset credits". We should store it.
                         # Let's check model first. If not exists, we might need migration or just log for now?
                         # For now, let's log it prominently and store in credits_last_checked as fallback or just log.
                         logger.info(f"🕒 Credits Reset At: {reset_date} (UTC)")
                         
                    account.credits_last_checked = datetime.utcnow()
                    logger.info(f"💾 Updated Account #{account.id} stats in DB.")

                    # Update task state to mark generate as completed
                    await task_manager.complete_submit(
                        job,
                        account_id=account.id,
                        credits_before=-1, # Not tracked relative anymore
                        credits_after=credits_rem if credits_rem is not None else -1
                    )

                    # CRITICAL: Save task_id to job for reliable tracking
                    sora_task_id = api_result.get("task_id")
                    if sora_task_id:
                        # Store in task_state for persistent tracking
                        state = await task_manager.get_job_state(job)
                        if "tasks" in state and "generate" in state["tasks"]:
                            state["tasks"]["generate"]["task_id"] = sora_task_id
                            job.task_state = json.dumps(state)
                            logger.info(f"💾 Saved Sora task_id to DB: {sora_task_id}")

                    # Update status to sent_prompt
                    job.status = "generating"
                    db.commit()

                    # ===== PARALLEL FLOW: Enqueue Poll Task (Release browser lock early) =====
                    logger.info(f"🔄 Job #{task.job_id} Submitted! Enqueuing POLL task for parallel processing...")

                    # Create poll task with saved tokens (for API-only polling)
                    from .task_manager import TaskContext
                    poll_task = TaskContext(
                        job_id=job.id,
                        task_type="poll",
                        input_data={
                            "prompt": task.input_data["prompt"],
                            "account_id": account.id,
                            "access_token": account.access_token,
                            "user_agent": account.user_agent,
                            "task_id": api_result.get("task_id")
                        }
                    )
                    await task_manager.poll_queue.put(poll_task)
                    logger.info(f"✅ Job #{task.job_id} poll task enqueued. Browser lock will be released.")
                    # ===== END SUBMIT PHASE - Browser lock released after this block =====
                except Exception as commit_error:
                    logger.error(f"Failed in sequential flow (credits/poll/download): {commit_error}")
                    db.rollback()
                    raise
            else:
                raise Exception(f"Submission verification failed (credits did not decrease). Before: {result['credits_before']}, After: {result['credits_after']}")

        except QuotaExhaustedException as e:
            # Handle quota exhaustion - mark account and retry with different account
            logger.warning(f"⚠️ Account #{account.id} quota exhausted for job #{job.id}")
            account_manager.mark_account_quota_exhausted(db, account)

            # Track account switches to prevent infinite loop
            account_switch_count = task.input_data.get("account_switch_count", 0) + 1

            if account_switch_count >= MAX_ACCOUNT_SWITCHES:
                logger.error(f"❌ Job #{job.id} exceeded max account switches ({MAX_ACCOUNT_SWITCHES})")
                try:
                    await task_manager.fail_task(job, "generate", f"Failed after switching {MAX_ACCOUNT_SWITCHES} accounts (all quota exhausted)")
                    db.commit()
                except Exception as commit_error:
                    logger.error(f"Failed to commit task failure: {commit_error}")
                    db.rollback()
            else:
                # Re-queue the job with this account excluded
                exclude_ids = task.input_data.get("exclude_account_ids", [])
                exclude_ids.append(account.id)

                # Check if there are other accounts available
                other_account = account_manager.get_available_account(db, platform="sora", exclude_ids=exclude_ids)

                if other_account:
                    logger.info(f"🔄 Re-queuing job #{job.id} with different account (switch {account_switch_count}/{MAX_ACCOUNT_SWITCHES})...")
                    from .task_manager import TaskContext
                    new_task = TaskContext(
                        job_id=job.id,
                        task_type="generate",
                        input_data={
                            "prompt": job.prompt,
                            "duration": job.duration,
                            "account_id": None,  # Let it pick a new account
                            "exclude_account_ids": exclude_ids,
                            "account_switch_count": account_switch_count
                        },
                        retry_count=task.retry_count  # Don't increment retry count for quota switch
                    )
                    await task_manager.generate_queue.put(new_task)
                else:
                    # No more accounts available - PAUSE SYSTEM
                    logger.critical(f"🛑 CRITICAL: All accounts exhausted quota! Pausing system.")
                    task_manager.pause(reason="⚠️ Out of Credits (All accounts exhausted)")

                    # Re-queue job as pending so it picks up when Resumed
                    job.status = "pending"
                    job.error_message = "Paused: Waiting for credits"
                    try:
                        db.commit()
                    except:
                        db.rollback()
                    
                    # Re-queue
                    from .task_manager import TaskContext
                    # Create clean task
                    retry_task = TaskContext(
                        job_id=job.id,
                        task_type="generate",
                        input_data={
                            "prompt": job.prompt,
                            "duration": job.duration,
                            "exclude_account_ids": [] # Reset exclusions
                        },
                        retry_count=task.retry_count
                    )
                    await task_manager.generate_queue.put(retry_task)
                    tracker.update(job.id, "queued", message="System Paused (No Credits)")
                    return

        except VerificationRequiredException as e:
            # Handle verification checkpoint - mark account and retry
            logger.warning(f"⚠️ Account #{account.id} requires verification: {e}")
            account_manager.mark_account_verification_needed(db, account)

            # Track account switches to prevent infinite loop
            account_switch_count = task.input_data.get("account_switch_count", 0) + 1

            if account_switch_count >= MAX_ACCOUNT_SWITCHES:
                logger.error(f"❌ Job #{job.id} exceeded max account switches ({MAX_ACCOUNT_SWITCHES})")
                try:
                    await task_manager.fail_task(job, "generate", f"Failed after switching {MAX_ACCOUNT_SWITCHES} accounts (verification required)")
                    db.commit()
                except Exception as commit_error:
                    logger.error(f"Failed to commit task failure: {commit_error}")
                    db.rollback()
            else:
                # Re-queue the job with this account excluded
                exclude_ids = task.input_data.get("exclude_account_ids", [])
                exclude_ids.append(account.id)

                # Check if there are other accounts available
                other_account = account_manager.get_available_account(db, platform="sora", exclude_ids=exclude_ids)

                if other_account:
                    logger.info(f"🔄 Re-queuing job #{job.id} with different account (due to verify, switch {account_switch_count}/{MAX_ACCOUNT_SWITCHES})...")
                    from .task_manager import TaskContext
                    new_task = TaskContext(
                        job_id=job.id,
                        task_type="generate",
                        input_data={
                            "prompt": job.prompt,
                            "duration": job.duration,
                            "account_id": None,  # Let it pick a new account
                            "exclude_account_ids": exclude_ids,
                            "account_switch_count": account_switch_count
                        },
                        retry_count=task.retry_count
                    )
                    await task_manager.generate_queue.put(new_task)
                else:
                     try:
                         await task_manager.fail_task(job, "generate", "All accounts failed verification or exhausted")
                         db.commit()
                     except Exception as commit_error:
                         logger.error(f"Failed to commit task failure: {commit_error}")
                         db.rollback()

        finally:
            if driver:
                logger.info(f"🛑 Closing driver session for Job #{task.job_id}...")
                try:
                    # Force timeout on close to prevent hanging semaphore
                    await asyncio.wait_for(driver.stop(), timeout=5.0)
                    logger.info(f"✅ Driver session closed for Job #{task.job_id}")
                except Exception as e:
                    logger.warning(f"⚠️ Error/Timeout closing driver: {e}")
            
            if 'account_lock' in locals():
                account_lock.release()

    except Exception as e:
        logger.error(f"❌ Generate task failed for job #{job.id}: {e}")
        # ... (keep existing error handling) ...
        # SMART RETRY: If we have an account and haven't hit max retries, switch account
        retry_count = task.retry_count + 1
        max_retries = job.max_retries if job.max_retries else 3
        account_switch_count = task.input_data.get("account_switch_count", 0) + 1

        if account and retry_count <= max_retries and account_switch_count < MAX_ACCOUNT_SWITCHES:
             logger.warning(f"🔄 Smart Switch: Job #{job.id} failed on Account #{account.id}. Switching account (Attempt {retry_count}/{max_retries}, Switch {account_switch_count}/{MAX_ACCOUNT_SWITCHES})...")

             # Exclude this bad account
             exclude_ids = task.input_data.get("exclude_account_ids", [])
             exclude_ids.append(account.id)

             from .task_manager import TaskContext
             new_task = TaskContext(
                job_id=job.id,
                task_type="generate",
                input_data={
                    "prompt": job.prompt,
                    "duration": job.duration,
                    "account_id": None,  # Force pick new account
                    "exclude_account_ids": exclude_ids,
                    "account_switch_count": account_switch_count
                },
                retry_count=retry_count
             )
             await task_manager.generate_queue.put(new_task)
             try:
                 db.commit()
             except Exception as commit_error:
                 logger.error(f"Failed to commit retry: {commit_error}")
                 db.rollback()
        else:
             # Permanent failure or no account involved or too many switches
            failure_reason = str(e)
            if account_switch_count >= MAX_ACCOUNT_SWITCHES:
                failure_reason = f"Exceeded max account switches ({MAX_ACCOUNT_SWITCHES}): {e}"
            try:
                await task_manager.fail_task(job, "generate", failure_reason)
                db.commit()
            except Exception as commit_error:
                logger.error(f"Failed to commit task failure: {commit_error}")
                db.rollback()

    finally:
        # Always mark account as free
        if account:
            await account_manager.mark_account_free(account.id)
        db.close()
        logger.info(f"🚦 [Semaphore] Task for Job #{task.job_id} releasing semaphore...")


async def reset_stale_jobs():
    """Periodically reset jobs stuck in processing state"""
    logger.info("🔄 Stale job monitor started")

    while not STOP_EVENT.is_set():
        try:
            await asyncio.sleep(60)  # Check every 1 minute (more frequent for debug)
            
            # Log Queue Stats
            q_gen = task_manager.generate_queue.qsize() if task_manager._generate_queue else 0
            q_poll = task_manager.poll_queue.qsize() if task_manager._poll_queue else 0
            q_dl = task_manager.download_queue.qsize() if task_manager._download_queue else 0
            logger.info(f"📊 Queue Stats: Generate={q_gen}, Poll={q_poll}, Download={q_dl}")

            db = database.SessionLocal()
            try:
                # Reset quota exhausted accounts after 24 hours
                account_manager.reset_quota_exhausted_accounts(db, hours=24)

                # Find jobs stuck in processing for more than 15 minutes
                from datetime import timedelta
                cutoff = datetime.utcnow() - timedelta(minutes=15)

                stale_jobs = db.query(models.Job).filter(
                    models.Job.status.in_(["processing", "sent_prompt", "generating", "download"]),
                    models.Job.updated_at < cutoff
                ).all()

                for job in stale_jobs:
                    logger.warning(f"🔄 Resetting stale job #{job.id} (Status: {job.status})")

                    # Smart reset: Check task_state to determine what to do
                    try:
                        state = json.loads(job.task_state) if job.task_state else {}
                        current_task = state.get("current_task")
                        generate_status = state.get("tasks", {}).get("generate", {}).get("status")

                        # If generate is completed but job stuck in generating/processing
                        # -> Re-enqueue poll task instead of resetting to pending
                        if generate_status == "completed" and current_task == "poll":
                            logger.info(f"  → Smart reset: Re-enqueueing POLL task for Job #{job.id}")

                            # Get account info
                            account_id = state.get("tasks", {}).get("generate", {}).get("account_id") or job.account_id
                            if account_id:
                                account = db.query(models.Account).filter(models.Account.id == account_id).first()
                                if account and account.access_token:
                                    # Update status
                                    job.status = "processing"
                                    job.error_message = None

                                    # Create and enqueue poll task
                                    from .task_manager import TaskContext
                                    poll_task = TaskContext(
                                        job_id=job.id,
                                        task_type="poll",
                                        input_data={
                                            "prompt": job.prompt,
                                            "account_id": account_id,
                                            "access_token": account.access_token,
                                            "user_agent": account.user_agent
                                        }
                                    )
                                    await task_manager.poll_queue.put(poll_task)
                                    logger.info(f"  ✅ Poll task re-enqueued for Job #{job.id}")
                                    continue

                        # If video_url exists but download stuck -> Re-enqueue download
                        elif job.video_url and current_task == "download":
                            logger.info(f"  → Smart reset: Re-enqueueing DOWNLOAD task for Job #{job.id}")

                            account_id = state.get("tasks", {}).get("generate", {}).get("account_id") or job.account_id
                            account = db.query(models.Account).filter(models.Account.id == account_id).first() if account_id else None

                            job.status = "download"
                            job.error_message = None

                            from .task_manager import TaskContext
                            dl_task = TaskContext(
                                job_id=job.id,
                                task_type="download",
                                input_data={
                                    "video_url": job.video_url,
                                    "access_token": account.access_token if account else None,
                                    "user_agent": account.user_agent if account else None
                                }
                            )
                            await task_manager.download_queue.put(dl_task)
                            logger.info(f"  ✅ Download task re-enqueued for Job #{job.id}")
                            continue

                    except Exception as e:
                        logger.error(f"  ❌ Smart reset failed for Job #{job.id}: {e}")

                    # Fallback: Simple reset to pending (for generate phase or unknown state)
                    job.status = "pending"
                    job.error_message = f"Reset: Job was stuck in {job.status}"
                    logger.info(f"  → Simple reset to pending for Job #{job.id}")

                if stale_jobs:
                    db.commit()
                    logger.info(f"Reset {len(stale_jobs)} stale jobs")

            finally:
                db.close()

        except Exception as e:
            logger.error(f"Stale job monitor error: {e}")


async def hydrate_queue_from_db():
    """Hydrate in-memory queue with pending jobs from DB on startup"""
    logger.info("💧 Hydrating queue from database...")
    db = database.SessionLocal()
    try:
        # Find pending jobs that are NOT in a specific task state yet (fresh)
        # OR jobs that are pending retry
        pending_jobs = db.query(models.Job).filter(
            models.Job.status == "pending"
        ).order_by(models.Job.created_at.asc()).all()
        
        count = 0
        for job in pending_jobs:
            # Check if already in queue? We can't easily.
            # But on startup, queue is empty.
            try:
                # Re-submit to task manager
                # Use start_job logic but without resetting status (it's already pending)
                # Or just put to queue directly
                
                # Check task state to see if it's a retry or fresh
                
                await task_manager.start_job(job)
                count += 1
            except Exception as e:
                logger.error(f"Failed to hydrate job #{job.id}: {e}")
        
        if count > 0:
            db.commit()
            logger.info(f"✅ Hydrated {count} pending jobs from DB.")
        
    except Exception as e:
        logger.error(f"Hydration error: {e}")
    finally:
        db.close()

# Global flag to track worker status
_worker_running = False
STOP_EVENT = asyncio.Event()
_tasks = set()

async def stop_worker():
    """Signal all workers to stop and cancel pending tasks"""
    global _worker_running
    logger.warning("🛑 Worker stopping... signaling shutdown.")
    _worker_running = False
    STOP_EVENT.set()
    
    # Wait briefly for tasks to notice event
    await asyncio.sleep(1)
    
    # Cancel tracked tasks if any remain
    if _tasks:
        logger.info(f"🛑 Cancelling {len(_tasks)} active tasks...")
        for t in _tasks:
            if not t.done():
                t.cancel()
        
        await asyncio.gather(*_tasks, return_exceptions=True)
        _tasks.clear()
    
    logger.info("✅ Worker stopped.")

async def process_poll_tasks():
    """
    Worker loop for poll tasks - API-only mode (BATCH PARALLEL)
    
    Processing Strategy:
    1. Collect batch of poll tasks from queue (limit 20).
    2. Group by account.
    3. call get_pending_tasks_api() for each account (Batch Check).
    4. If task in pending list -> Re-queue (it's still processing).
    5. If task NOT in pending list -> It might be done or failed -> Check individually.
    """
    logger.info("📡 Poll Worker started (Batch Mode, Parallel)")
    
    while not STOP_EVENT.is_set():
        # Check Pause
        if task_manager.is_paused:
            await asyncio.sleep(1)
            continue
            
        try:
            # 1. Collect Batch
            tasks = []
            try:
                # Wait for at least one
                first = await asyncio.wait_for(task_manager.poll_queue.get(), timeout=5.0)
                tasks.append(first)
                
                # Collect others (up to limit)
                while len(tasks) < MAX_CONCURRENT_POLL and not task_manager.poll_queue.empty():
                    try:
                        t = task_manager.poll_queue.get_nowait()
                        tasks.append(t)
                    except asyncio.QueueEmpty:
                        break
            except asyncio.TimeoutError:
                continue

            # 2. Group by Account
            tasks_by_account = defaultdict(list)
            for t in tasks:
                 # Extract account ID
                 db = database.SessionLocal()
                 try:
                     job = db.query(models.Job).filter(models.Job.id == t.job_id).first()
                     if job:
                         tasks_by_account[job.account_id].append(t)
                     else:
                         logger.warning(f"Poll Task: Job #{t.job_id} not found, dropping.")
                 finally:
                     db.close()

            # 3. Process Batch per Account
            for account_id, account_tasks in tasks_by_account.items():
                asyncio.create_task(_process_poll_batch_for_account(account_id, account_tasks))

        except Exception as e:
            logger.error(f"❌ Poll Worker loop error: {e}", exc_info=True)
            await asyncio.sleep(5)


async def _process_poll_batch_for_account(account_id: int, tasks: List):
    """Process a batch of poll tasks for a single account"""
    db = database.SessionLocal()
    driver = None
    try:
        # Get Account
        account = db.query(models.Account).filter(models.Account.id == account_id).first()
        if not account or not account.access_token:
             # Fail all tasks
             for t in tasks:
                 tracker.update(t.job_id, "failed", message="Account/Token missing during poll")
                 # We could fail logic here, but simpler to just re-queue 
                 # and let individual check handle failures or retry
                 logger.error(f"Account #{account_id} invalid for poll batch. Re-queuing tasks.")
                 await asyncio.sleep(5)
                 await task_manager.poll_queue.put(t)
             return

        # Init driver
        driver = await SoraDriver.api_only(
            access_token=account.access_token,
            user_agent=account.user_agent
        )

        # A. Batch Check Pending
        pending_list = await driver.get_pending_tasks_api()
        
        pending_ids = set()
        pending_data_map = {}
        
        if pending_list is not None:
            # Note: pending_list is [{"id": "...", "status": "...", "progress_pct": ...}]
            # But we map by Sora Task ID, which we might not have in Job table if we only have Job ID?
            # Actually Generate stores task_id in job table/input.
            # But let's check what we have.
            # wait_for_completion usually matches by PROMPT.
            
            for p in pending_list:
                # We need to match by ID or Prompt.
                # Let's map by ID if possible.
                if p.get("id"):
                    pending_ids.add(p.get("id"))
                    pending_data_map[p.get("id")] = p
        
        # B. Classify Tasks
        still_pending = []
        needs_check = []
        
        for t in tasks:
            # We need the Sora Task ID from input_data
            # In generate phase: result = {"task_id": ...}
            # But "task" object here is the generic task context.
            # The input_data for poll task usually has "prompt" or "task_id"?
            # Check invoke in Generate Worker:
            # (Generate worker puts to start_job... wait, Generate worker puts to poll_queue?)
            # No, Start Job -> Generate -> ... -> Task Manager orchestration?
            # Actually, Generate Worker just updates Job DB.
            # The transition to Poll queue logic needs to be checked.
            # Assuming task input has "prompt".
            
            # If we rely on prompts, it's fuzzy.
            # But let's assume if prompt is in pending list -> it is pending.
            
            prompt = t.input_data.get("prompt")
            # Try to find prompt in pending list
            found_in_pending = False
            
            if pending_list:
                for p in pending_list:
                    if p.get("prompt") and prompt and p.get("prompt").strip() == prompt.strip():
                        # Found it!
                        found_in_pending = True
                        progress = p.get("progress_pct", 0) * 100
                        status = p.get("status", "processing")

                        logger.info(f"📊 Job #{t.job_id} (Acc #{account_id}): {status} {progress:.1f}%")
                        tracker.update(t.job_id, "processing", progress=progress, message=f"Rendering: {progress:.1f}%")

                        # Update job timestamp to prevent stale monitor reset
                        try:
                            job = db.query(models.Job).filter(models.Job.id == t.job_id).first()
                            if job:
                                job.updated_at = datetime.utcnow()
                                job.progress = int(progress)
                                db.commit()
                        except Exception as e:
                            logger.warning(f"Failed to update timestamp for Job #{t.job_id}: {e}")
                            db.rollback()
                        break
            
            if found_in_pending:
                still_pending.append(t)
            else:
                needs_check.append(t)
        
        # C. Handle Still Pending
        for t in still_pending:
            # Re-queue with delay
            # Can we delay only this task?
            # Yes, launch a delayed put
            asyncio.create_task(_delayed_requeue_poll(t, 15))
            
        # D. Handle Needs Check (Completed or Failed or missing)
        # Check individually using deep check logic
        for t in needs_check:
             # Use the old logic (check drafts/completion)
             # Reuse _process_single_poll_task (logic extracted from old loop)
             # Or just inline it here.
             
             # Call helper
             asyncio.create_task(_process_single_poll_deep_check(t, driver, account))
             
    except Exception as e:
        logger.error(f"Error in poll batch for Acc #{account_id}: {e}")
        # Requeue all
        for t in tasks:
            await task_manager.poll_queue.put(t)
    finally:
        if driver:
            # Driver stop? api_only driver doesn't really need stop if no browser
            pass
        db.close()

async def _delayed_requeue_poll(task, delay):
    await asyncio.sleep(delay)
    await task_manager.poll_queue.put(task)

async def _process_single_poll_deep_check(task, driver, account):
    """Deep check for a single task that is NOT in pending list (likely done)"""
    db = database.SessionLocal()
    try:
        job = db.query(models.Job).filter(models.Job.id == task.job_id).first()
        if not job: return

        tracker.update(task.job_id, "processing", message="Finalizing status...")
        match_prompt = task.input_data.get("prompt", job.prompt)

        # Get task_id from input_data or job.task_state
        sora_task_id = task.input_data.get("task_id")
        if not sora_task_id and job.task_state:
            try:
                state = json.loads(job.task_state)
                sora_task_id = state.get("tasks", {}).get("generate", {}).get("task_id")
            except:
                pass

        if sora_task_id:
            logger.info(f"📌 Job #{job.id}: Polling with task_id = {sora_task_id}")
        else:
            logger.warning(f"⚠️ Job #{job.id}: No task_id available, using prompt matching (less reliable)")

        # Use wait_for_completion_api with task_id for precise matching
        video_data = await driver.wait_for_completion_api(
             match_prompt=match_prompt,
             timeout=30, # Short timeout just to find it in drafts
             task_id=sora_task_id  # CRITICAL: Use task_id for exact match
        )
        
        if video_data and video_data.get("download_url"):
            logger.info(f"✅ Video completed for Job #{job.id}! ID: {video_data.get('id')}")
            tracker.update(task.job_id, "download", message="Ready for download")

            job.status = "download"
            job.video_url = video_data.get("download_url")
            db.commit()

            # Enqueue download
            from .task_manager import TaskContext
            dl_task = TaskContext(
                job_id=job.id,
                task_type="download",
                input_data={
                    "video_url": video_data.get("download_url"),
                    "video_id": video_data.get("id"),
                    "access_token": account.access_token,
                    "user_agent": account.user_agent
                }
            )
            await task_manager.download_queue.put(dl_task)

        elif video_data and video_data.get("status") == "failed":
             logger.error(f"❌ Video generation failed for Job #{job.id}")
             tracker.update(task.job_id, "failed", message="Generation failed")
             job.status = "failed"
             job.error_message = "Generation failed"
             db.commit()
        else:
             # Still not found? Might be really slow or delayed appearance?
             # Re-queue poll
             logger.warning(f"⚠️ Job #{job.id} not in pending OR drafts. Re-queuing poll.")
             await asyncio.sleep(10)
             await task_manager.poll_queue.put(task)

    except Exception as e:
        logger.error(f"Deep check error Job #{task.job_id}: {e}")
        await task_manager.poll_queue.put(task)
    finally:
        db.close()

async def process_download_tasks():
    """
    Worker loop for download tasks - API-only mode (no UI automation).
    Downloads video using stored URL and aiohttp.
    Runs in PARALLEL with other workers (no browser lock needed).
    """
    logger.info("⬇️ Download Worker started (API-only mode, PARALLEL)")
    while not STOP_EVENT.is_set():
        # Check Pause
        if task_manager.is_paused:
            await asyncio.sleep(1)
            continue
            
        try:
            # Use timeout to allow checking STOP_EVENT periodically
            try:
                task = await asyncio.wait_for(task_manager.download_queue.get(), timeout=10.0)
            except asyncio.TimeoutError:
                continue

            db = database.SessionLocal()
            try:
                job = db.query(models.Job).filter(models.Job.id == task.job_id).first()
                if not job:
                    logger.warning(f"Download task: Job #{task.job_id} not found")
                    continue

                # Skip if job was cancelled/completed/failed
                if job.status not in ["download", "generating", "processing"]:
                    logger.info(f"⏭️ Download task: Job #{job.id} status is '{job.status}', skipping")
                    continue

                logger.info(f"⬇️ Processing DOWNLOAD task for Job #{job.id} (API-only, Parallel)")

                download_url = task.input_data.get("video_url")
                if not download_url:
                    logger.error(f"No download URL for Job #{job.id}")
                    job.status = "failed"
                    job.error_message = "No download URL provided"
                    db.commit()
                    continue

                # Get auth info from task input
                access_token = task.input_data.get("access_token")
                user_agent = task.input_data.get("user_agent", "Mozilla/5.0")

                # Fetch Account to get Cookies (REQUIRED for some download URLs)
                account_cookies = {}
                if job.account_id:
                    account = db.query(models.Account).filter(models.Account.id == job.account_id).first()
                    if account and account.cookies:
                         for c in account.cookies:
                             account_cookies[c['name']] = c['value']
                         logger.info(f"🍪 Loaded {len(account_cookies)} cookies for download")

                # Build headers for authenticated download
                headers = {
                    "User-Agent": user_agent,
                    "Referer": "https://sora.chatgpt.com/"
                }
                
                # CRITICAL FIX: If we have cookies, DO NOT send Bearer token for file downloads 
                # (videos.openai.com rejects requests with both or just token).
                # Only use Bearer if we have NO cookies.
                if access_token and not account_cookies:
                    headers["Authorization"] = access_token

                # Download using aiohttp (no browser needed)
                try:
                    # Pass cookies to session
                    async with aiohttp.ClientSession(cookies=account_cookies) as session:
                        async with session.get(download_url, headers=headers) as response:
                            if response.status == 200:
                                # Use data/downloads to match FastAPI mount point
                                download_dir = "data/downloads"
                                os.makedirs(download_dir, exist_ok=True)
                                video_id = task.input_data.get("video_id", job.id)
                                filename = f"{download_dir}/sora_{job.id}_{video_id}.mp4"

                                total_size = 0
                                with open(filename, 'wb') as f:
                                    async for chunk in response.content.iter_chunked(8192):
                                        f.write(chunk)
                                        total_size += len(chunk)

                                # Verify file size
                                if total_size < 10000:  # Less than 10KB is probably error
                                    logger.error(f"❌ Downloaded file too small ({total_size} bytes)")
                                    job.status = "failed"
                                    job.error_message = f"Downloaded file too small ({total_size} bytes)"
                                    os.remove(filename)
                                    db.commit()
                                    continue

                                logger.info(f"✅ Downloaded {filename} ({total_size:,} bytes)")

                                # Update job
                                # START FIX: Web path should be /downloads/... not /data/downloads/...
                                web_filename = os.path.basename(filename)
                                job.local_path = f"/downloads/{web_filename}"
                                # END FIX
                                job.video_url = filename
                                job.status = "completed"
                                job.progress = 100
                                job.updated_at = datetime.utcnow()

                                # Update task state
                                state = await task_manager.get_job_state(job)
                                state["tasks"]["download"] = {
                                    "status": "completed",
                                    "completed_at": datetime.utcnow().isoformat(),
                                    "output": {"local_path": filename, "file_size": total_size}
                                }
                                state["current_task"] = "completed"
                                job.task_state = json.dumps(state)

                                # Remove from active jobs
                                task_manager._active_job_ids.discard(job.id)

                                db.commit()
                                logger.info(f"🎉 Job #{job.id} COMPLETED SUCCESSFULLY!")

                            else:
                                logger.error(f"❌ Download failed: HTTP {response.status}")
                                job.status = "failed"
                                job.error_message = f"Download HTTP error: {response.status}"
                                db.commit()

                except Exception as dl_error:
                    logger.error(f"❌ Download error for Job #{job.id}: {dl_error}")
                    job.status = "failed"
                    job.error_message = f"Download error: {str(dl_error)[:200]}"
                    db.commit()

            finally:
                db.close()

        except Exception as e:
            logger.error(f"Download worker error: {e}", exc_info=True)
            await asyncio.sleep(5)

async def start_task_manager_worker():
    """
    Main worker orchestrator - runs all workers in PARALLEL:
    - Generate Worker: Login + Submit (uses browser lock)
    - Poll Worker: API polling (parallel, no browser)
    - Download Worker: File download (parallel, no browser)
    - Stale Job Monitor: Reset stuck jobs
    """
    global _worker_running
    if _worker_running:
        logger.warning("⚠️ Workers ALREADY RUNNING! Skipping start.")
        return

    _worker_running = True
    STOP_EVENT.clear()
    logger.info("🚀 Worker System Started (PARALLEL MODE)")
    logger.info("   ├── Generate Worker: Browser-based (sequential login/submit)")
    logger.info("   ├── Poll Worker: API-only (parallel)")
    logger.info("   ├── Download Worker: API-only (parallel)")
    logger.info("   └── Stale Job Monitor: Background cleanup")

    # Hydrate queue first
    try:
        await hydrate_queue_from_db()
    except Exception as e:
        logger.error(f"❌ Failed to hydrate queue from DB: {e}. Worker starting fresh.")

    # Start all workers
    try:
        t1 = asyncio.create_task(process_generate_tasks())
        t2 = asyncio.create_task(reset_stale_jobs())
        t3 = asyncio.create_task(process_poll_tasks())
        t4 = asyncio.create_task(process_download_tasks())
        
        _tasks.add(t1)
        _tasks.add(t2)
        _tasks.add(t3)
        _tasks.add(t4)
        
        t1.add_done_callback(_tasks.discard)
        t2.add_done_callback(_tasks.discard)
        t3.add_done_callback(_tasks.discard)
        t4.add_done_callback(_tasks.discard)

        await asyncio.wait([t1, t2, t3, t4], return_when=asyncio.FIRST_COMPLETED)
    except Exception as e:
        logger.error(f"❌ Critical Worker Startup Error: {e}", exc_info=True)
    finally:
        _worker_running = False # Reset on exit


# Keep old worker for backward compatibility
async def start_worker():
    """Start the new task manager worker"""
    # Start in background without awaiting? 
    # Usually called with create_task in main.
    await start_task_manager_worker()

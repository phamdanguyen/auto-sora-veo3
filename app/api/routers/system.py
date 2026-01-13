"""
System Router
Implements: Single Responsibility Principle (SRP)

This router handles system management endpoints:
- System reset
- Worker control (pause/resume)
- Queue status monitoring
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from ..dependencies import get_db
from ... import models

import logging
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/system", tags=["system"])


@router.post("/reset")
async def system_reset(db: Session = Depends(get_db)):
    """
    Emergency system reset

    Performs the following actions:
    1. Clear all busy accounts (release locks)
    2. Clear active job IDs from task manager
    3. Reset 'processing' jobs to 'pending' in database

    This is useful when the system gets stuck or accounts are locked.

    Args:
        db: Database session (injected)

    Returns:
        Success status with reset details
    """
    logger.warning("[WARNING] SYSTEM RESET TRIGGERED BY USER")

    # 1. Clear busy accounts
    from ...core import account_manager
    busy_count = len(account_manager.busy_accounts)
    account_manager.force_reset()
    logger.info(f"[RESET] Cleared {busy_count} busy accounts")

    # 2. Clear active jobs in task manager
    from ...core.task_manager import task_manager
    active_count = len(task_manager.active_jobs)
    task_manager.force_clear_active()
    logger.info(f"[RESET] Cleared {active_count} active jobs from task manager")

    # 3. Reset processing jobs to pending
    processing_jobs = db.query(models.Job).filter(
        models.Job.status.in_(['processing', 'sent_prompt', 'generating', 'download'])
    ).all()

    for job in processing_jobs:
        job.status = 'pending'
        job.progress = 0
        job.error_message = None
        logger.info(f"[RESET] Job {job.id} reset to pending")

    db.commit()

    return {
        "ok": True,
        "message": "System reset complete",
        "cleared_accounts": busy_count,
        "cleared_active_jobs": active_count,
        "reset_jobs": len(processing_jobs)
    }


@router.post("/pause")
async def pause_system():
    """
    Pause all workers

    Stops the task manager from processing new jobs.
    Running jobs will continue to completion.

    Returns:
        Success status
    """
    from ...core.task_manager import task_manager
    task_manager.pause(reason="Manual pause by user")
    logger.info("[SYSTEM] Task manager paused")

    return {"ok": True, "paused": True}


@router.post("/resume")
async def resume_system():
    """
    Resume all workers

    Resumes the task manager to process jobs from the queue.

    Returns:
        Success status
    """
    from ...core.task_manager import task_manager
    task_manager.resume()
    logger.info("[SYSTEM] Task manager resumed")

    return {"ok": True, "paused": False}


@router.get("/queue_status")
async def get_queue_status(db: Session = Depends(get_db)):
    """
    Get queue status and system statistics

    Provides real-time information about:
    - Task manager status (paused, active jobs, queue size)
    - Database statistics (completed, pending, failed, active jobs)
    - Account statistics

    Args:
        db: Database session (injected)

    Returns:
        System status dictionary
    """
    from ...core.task_manager import task_manager

    # Get task manager status
    status = task_manager.get_status()

    # Add database statistics
    completed_count = db.query(models.Job).filter(
        models.Job.status.in_(['completed', 'done'])
    ).count()

    pending_count = db.query(models.Job).filter(
        models.Job.status.in_(['pending', 'draft'])
    ).count()

    failed_count = db.query(models.Job).filter(
        models.Job.status == 'failed'
    ).count()

    processing_count = db.query(models.Job).filter(
        models.Job.status.in_(['processing', 'sent_prompt', 'generating', 'download'])
    ).count()

    # Get account statistics
    total_accounts = db.query(models.Account).count()
    accounts_with_credits = db.query(models.Account).filter(
        models.Account.credits_remaining > 0
    ).count()

    # Combine status
    status.update({
        "db_stats": {
            "completed": completed_count,
            "pending": pending_count,
            "failed": failed_count,
            "processing": processing_count
        },
        "accounts": {
            "total": total_accounts,
            "with_credits": accounts_with_credits
        }
    })

    return status


@router.post("/restart_workers")
async def restart_workers():
    """
    Restart all workers

    Stops and restarts the worker manager.
    This is useful for applying configuration changes or recovering from errors.

    Returns:
        Success status

    Note:
        Currently uses legacy worker_v2 system.
        Will be migrated to new WorkerManager in future update.
    """
    logger.warning("[SYSTEM] Worker restart requested")

    try:
        # Try to access worker manager if available
        from ...core.workers.manager import worker_manager

        if worker_manager:
            await worker_manager.stop_all()
            await worker_manager.start_all()
            return {"ok": True, "message": "Workers restarted"}
        else:
            return {"ok": False, "message": "Worker manager not initialized"}
    except ImportError:
        # Worker manager not yet fully integrated, using legacy worker_v2
        return {"ok": False, "message": "Worker manager not available - using legacy workers"}

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


@router.get("/license")
async def get_license_info():
    """
    Get detailed license information

    Returns license status including:
    - Current status (valid/expired/missing)
    - Expiration date
    - Days remaining
    - Expiry warnings (if within 7-14 days)
    - Hardware ID

    Returns:
        License status dictionary
    """
    from ...core.license_manager import LicenseManager

    try:
        status = LicenseManager.get_license_status()
        return {"ok": True, "license": status}
    except Exception as e:
        logger.error(f"Failed to get license info: {e}")
        return {"ok": False, "error": str(e)}


@router.post("/license/update")
async def update_license_key(key: str):
    """
    Update license key

    Validates and saves a new license key.

    Args:
        key: License key string

    Returns:
        Validation result and new license status
    """
    from ...core.license_manager import LicenseManager

    try:
        # Validate the key first
        is_valid, message, expiry = LicenseManager.validate_key(key)

        if is_valid:
            # Save the key
            LicenseManager.save_key(key)

            # Get new status
            status = LicenseManager.get_license_status()

            return {
                "ok": True,
                "message": "License key updated successfully",
                "expiration": expiry,
                "license": status
            }
        else:
            return {
                "ok": False,
                "error": message
            }
    except Exception as e:
        logger.error(f"Failed to update license key: {e}")
        return {"ok": False, "error": str(e)}


@router.get("/license/hardware_id")
async def get_hardware_id():
    """
    Get machine hardware ID

    Returns the current machine's hardware ID for license generation.
    This uses a composite hash of multiple hardware identifiers.

    Returns:
        Hardware ID string
    """
    from ...core.license_manager import LicenseManager

    try:
        hwid = LicenseManager.get_hardware_id()
        return {"ok": True, "hardware_id": hwid}
    except Exception as e:
        logger.error(f"Failed to get hardware ID: {e}")
        return {"ok": False, "error": str(e)}
